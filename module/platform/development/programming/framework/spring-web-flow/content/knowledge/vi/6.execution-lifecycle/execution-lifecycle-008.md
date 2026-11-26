# Hành động trên transition và điều kiện rời state

Trong module **SPRING_WEB_FLOW**, ta dùng state, event, transition và subflow để mô hình hóa một hành trình web nhiều bước. Khi một state nhận được event, Spring Web Flow cần quyết định có rời state hiện tại hay không, sẽ đi tới state nào và cần thực hiện công việc gì trong quá trình chuyển. Bài này tập trung vào ba điểm thường bị trộn lẫn: hành động gắn với transition, hành động vòng đời của state và điều kiện quyết định nhánh đi tiếp.

## 1. Event, transition và việc rời state

Một state mô tả bước hiện tại của flow, chẳng hạn `view-state` hiển thị biểu mẫu, `action-state` chạy một thao tác, `decision-state` chọn nhánh hoặc `subflow-state` gọi một flow con. Khi người dùng gửi biểu mẫu, nhấn nút hoặc flow con kết thúc, flow nhận được một **event**. Transition xác định event nào được chấp nhận và state đích nào sẽ được kích hoạt.

Ví dụ:

```xml
<view-state id="editBooking" view="booking/edit">
    <transition on="submit" to="reviewBooking" />
    <transition on="cancel" to="cancelled" />
</view-state>
```

`on="submit"` khớp với event có mã `submit`; `to` là ID của state đích. Trong biểu mẫu Spring Web Flow, nút gửi có thể phát event tương ứng bằng tên như `name="_eventId_submit"`. Mã event phải thống nhất giữa giao diện và định nghĩa flow. Nếu không có transition phù hợp, flow không thể tự đoán state đích; cần định nghĩa đầy đủ các event mà giao diện có thể gửi và xử lý những trường hợp không hợp lệ.

Một transition chỉ được thực hiện khi event khớp tiêu chí của nó và các bước binding/validation liên quan hoàn tất. Vì vậy, cần phân biệt:

- **Event matching** trả lời: người dùng hoặc flow con vừa phát event nào?
- **Binding** đưa dữ liệu gửi lên vào model của flow.
- **Validation** kiểm tra dữ liệu có hợp lệ để tiếp tục hay không.
- **Transition action** thực hiện công việc gắn với nhánh chuyển đã được chọn.
- **State exit/entry action** thực hiện công việc gắn với vòng đời của state nguồn hoặc state đích.

## 2. Hành động ở các điểm trong vòng đời

Spring Web Flow cho phép khai báo action tại nhiều thời điểm. Chọn đúng điểm giúp tránh chạy một thao tác quá nhiều lần hoặc chạy nó trên nhánh không liên quan.

| Vị trí | Thời điểm chạy | Công việc phù hợp |
|---|---|---|
| `<on-entry>` | Khi state được vào | Khởi tạo dữ liệu cho bước, lấy dữ liệu cần hiển thị, chiếm một khóa chỉnh sửa ngắn hạn |
| `<on-render>` | Mỗi lần view-state được render | Chuẩn bị dữ liệu trình bày cần làm mới theo lần render |
| `<on-exit>` | Khi flow thực sự rời state | Giải phóng tài nguyên gắn với state, đóng phiên chỉnh sửa, ghi nhận thời điểm kết thúc bước |
| Action nằm trong `<transition>` | Khi transition cụ thể được thực hiện | Ghi nhận thao tác gửi, lưu dấu vết của nhánh đã chọn, chuẩn bị dữ liệu cho bước kế tiếp |

Ví dụ về state action:

```xml
<view-state id="editBooking" view="booking/edit">
    <on-entry>
        <evaluate expression="bookingFlowAction.acquireEditLock(flowScope.booking.id)" />
    </on-entry>

    <on-exit>
        <evaluate expression="bookingFlowAction.releaseEditLock(flowScope.booking.id)" />
    </on-exit>
</view-state>
```

`on-entry` chạy khi người dùng bước vào màn hình chỉnh sửa. `on-exit` chạy khi họ rời state này qua một transition được chấp nhận. Vì `on-exit` gắn với state, nó áp dụng cho mọi đường rời khỏi `editBooking`, ví dụ gửi để xem lại hoặc hủy. Đây là vị trí thích hợp cho việc dọn dẹp chung của state.

`on-render` có thể chạy nhiều lần khi cùng một view được hiển thị lại, chẳng hạn sau một lần validation thất bại. Không đặt thao tác thanh toán, tạo đơn, gửi thông báo hoặc ghi nhận nghiệp vụ không thể lặp an toàn ở đây. Với các side effect chỉ được phép xảy ra một lần khi người dùng chọn một nhánh, hãy đặt chúng trên transition tương ứng hoặc trong service nghiệp vụ được gọi từ transition.

## 3. Gắn action vào transition

Action đặt bên trong `<transition>` chỉ thuộc về transition đó. Khi event `submit` chọn nhánh gửi biểu mẫu, action ghi nhận việc gửi được thực thi; khi event `cancel` chọn nhánh hủy, action ghi nhận hủy được thực thi. Hai action không bị gọi thay nhau chỉ vì chúng cùng nằm trong một state.

```xml
<view-state id="editBooking" view="booking/edit">
    <transition on="submit" to="routeBooking" bind="true" validate="true">
        <evaluate expression="bookingFlowAction.recordSubmission(flowScope.booking.id)" />
    </transition>

    <transition on="cancel" to="cancelled">
        <evaluate expression="bookingFlowAction.recordCancellation(flowScope.booking.id)" />
    </transition>
</view-state>
```

Trong ví dụ, `bind="true"` yêu cầu binding dữ liệu của biểu mẫu cho transition gửi; `validate="true"` yêu cầu kiểm tra dữ liệu trước khi tiếp tục. Khi dữ liệu không hợp lệ, flow giữ người dùng ở view hiện tại để hiển thị lỗi. Transition chưa hoàn tất nên không nên coi action của nhánh gửi là nơi thay thế cho validation của biểu mẫu.

Action trong transition thường gọi một Spring bean thông qua biểu thức. Bean có thể phối hợp với service để thực hiện nghiệp vụ, nhưng phần kiểm tra quy tắc miền, cập nhật dữ liệu và quản lý transaction nên thuộc service. Flow định nghĩa thời điểm gọi và nhánh điều hướng; service chịu trách nhiệm bảo đảm thao tác nghiệp vụ đúng và nhất quán.

Một action có thể trả kết quả cần dùng ở state tiếp theo. Hãy gán kết quả vào scope có vòng đời phù hợp:

```xml
<transition on="submit" to="reviewBooking" bind="true" validate="true">
    <evaluate expression="bookingFlowAction.createQuote(flowScope.booking)"
              result="flowScope.quote" />
</transition>
```

Ở đây `quote` cần tồn tại sau khi rời view-state nên được lưu trong `flowScope`. Nếu dữ liệu chỉ phục vụ một view, cân nhắc `viewScope`; dữ liệu trong scope này gắn với view-state hiện tại và không nên được dùng như dữ liệu lâu dài sau khi rời state.

## 4. Điều kiện rời state: event, validation và quyết định nghiệp vụ

Không phải mọi điều kiện đều nên được biểu diễn bằng cùng một cơ chế. Hãy chọn theo câu hỏi mà flow cần trả lời.

### 4.1. Chọn transition theo event

Nếu người dùng có các hành động rõ ràng như `submit`, `cancel` hoặc `back`, định nghĩa các transition tương ứng bằng thuộc tính `on`. Đây là lựa chọn tự nhiên cho điều hướng do người dùng khởi phát:

```xml
<view-state id="confirmBooking" view="booking/confirm">
    <transition on="confirm" to="completeBooking" />
    <transition on="back" to="editBooking" />
    <transition on="cancel" to="cancelled" />
</view-state>
```

### 4.2. Dùng binding và validation để chặn dữ liệu không hợp lệ

Với form, `bind` và `validate` trên transition cho phép kiểm soát việc đưa dữ liệu vào model và xác thực trước khi flow tiếp tục. Ví dụ, transition `submit` có thể yêu cầu cả hai bước:

```xml
<transition on="submit" to="reviewBooking" bind="true" validate="true">
    <evaluate expression="bookingFlowAction.prepareReview(flowScope.booking)" />
</transition>
```

Khi validation có lỗi, hiển thị thông báo qua cơ chế message của Spring Web Flow và giữ nguyên state để người dùng sửa. Không dùng `on-exit` làm chốt kiểm tra hợp lệ: `on-exit` mô tả công việc khi state rời đi, không phải nơi thể hiện điều kiện cho phép rời state.

### 4.3. Dùng decision-state cho điều kiện boolean

Khi cần rẽ nhánh theo dữ liệu hoặc quy tắc nghiệp vụ, dùng `decision-state` và phần tử `<if>`. Điều kiện được đánh giá khi flow đi vào decision-state:

```xml
<decision-state id="routeBooking">
    <if test="flowScope.booking.total >= 10000000"
        then="manualReview"
        else="confirmBooking" />
</decision-state>
```

Ví dụ này đưa booking có tổng tiền từ ngưỡng đã đặt trở lên tới `manualReview`; trường hợp còn lại tới `confirmBooking`. Điều kiện phải dựa trên dữ liệu đã được binding và kiểm tra hợp lệ. Nếu quy tắc phức tạp, có thể gọi một service để tính kết quả trước rồi dùng kết quả đó trong decision-state, thay vì nhồi toàn bộ quy tắc vào biểu thức EL.

### 4.4. Dùng action-state khi cần action trả về event

Nếu quyết định cần gọi một thao tác, chẳng hạn kiểm tra tồn kho, rồi phân nhánh theo kết quả của thao tác, dùng `action-state`. Action trả về event có ID tương ứng với các transition:

```xml
<action-state id="checkAvailability">
    <evaluate expression="availabilityAction.check(flowScope.booking)" />
    <transition on="available" to="reviewBooking" />
    <transition on="soldOut" to="editBooking" />
</action-state>
```

Ví dụ Java rút gọn cho action:

```java
import org.springframework.webflow.execution.Event;

public class AvailabilityAction {
    private final BookingService bookingService;

    public AvailabilityAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public Event check(Booking booking) {
        String eventId = bookingService.isAvailable(booking)
                ? "available"
                : "soldOut";
        return new Event(this, eventId);
    }
}
```

Tên event do action trả về phải khớp với giá trị `on` trong các transition của `action-state`. Nếu action có thể trả về thêm kết quả như `serviceUnavailable`, hãy định nghĩa cách xử lý kết quả đó hoặc xử lý exception ở tầng phù hợp; không để một kết quả không có transition khiến flow rơi vào lỗi khó hiểu.

## 5. Ghép các cơ chế trong một hành trình

Đoạn flow dưới đây kết hợp state action, transition action và decision-state. Giả sử `flowScope.booking` đã được khởi tạo ở bước trước và các bean được đăng ký trong Spring context.

```xml
<view-state id="editBooking" view="booking/edit">
    <on-entry>
        <evaluate expression="bookingFlowAction.acquireEditLock(flowScope.booking.id)" />
    </on-entry>

    <transition on="submit" to="routeBooking" bind="true" validate="true">
        <evaluate expression="bookingFlowAction.recordSubmission(flowScope.booking.id)" />
    </transition>

    <transition on="cancel" to="cancelled">
        <evaluate expression="bookingFlowAction.recordCancellation(flowScope.booking.id)" />
    </transition>

    <on-exit>
        <evaluate expression="bookingFlowAction.releaseEditLock(flowScope.booking.id)" />
    </on-exit>
</view-state>

<decision-state id="routeBooking">
    <if test="flowScope.booking.total >= 10000000"
        then="manualReview"
        else="confirmBooking" />
</decision-state>

<view-state id="manualReview" view="booking/manual-review" />
<view-state id="confirmBooking" view="booking/confirm" />
<end-state id="cancelled" />
```

Khi người dùng gửi form, Web Flow binding và validation theo cấu hình của transition. Nếu hợp lệ, nhánh `submit` được chọn; action ghi nhận việc gửi và action `on-exit` của state nguồn được thực thi trong quá trình chuyển. Sau khi rời `editBooking`, flow vào `routeBooking`, đánh giá tổng tiền và chọn state đích. Với nhánh `cancel`, action ghi nhận hủy chạy và `on-exit` vẫn giải phóng khóa vì đây cũng là một lần rời `editBooking`.

Điểm quan trọng là `releaseEditLock` là công việc chung của state nguồn, còn `recordSubmission` và `recordCancellation` là công việc riêng của từng nhánh. Nếu chỉ một nhánh cần thực hiện một side effect, đặt action trong transition của nhánh đó. Nếu mọi đường rời state đều cần dọn dẹp cùng một tài nguyên, đặt công việc ở `on-exit`.

## 6. Chọn scope cho dữ liệu được dùng bởi action

Action có thể đọc hoặc ghi dữ liệu trong các scope mà Spring Web Flow cung cấp. Chọn scope theo thời gian dữ liệu cần tồn tại:

| Scope | Vòng đời điển hình | Ví dụ |
|---|---|---|
| `requestScope` | Trong một request | Giá trị tạm chỉ dùng khi xử lý một lần gửi |
| `viewScope` | Trong vòng đời của view-state hiện tại | Bộ lọc hoặc trạng thái giao diện của một màn hình |
| `flowScope` | Trong suốt một flow execution | Booking đang được chỉnh sửa, dữ liệu cần qua nhiều state |
| `conversationScope` | Trong conversation chứa flow, có thể dùng chung qua flow con | Dữ liệu cần tồn tại xuyên suốt một hành trình gồm nhiều flow |
| `flashScope` | Dữ liệu tạm chuyển tiếp tới lần hiển thị kế tiếp | Thông báo sau khi hoàn tất một thao tác |

Ví dụ, booking cần được dùng ở cả màn hình chỉnh sửa, quyết định và xác nhận nên phù hợp với `flowScope`. Trạng thái chỉ phục vụ một màn hình nên đặt ở `viewScope`. Tránh đưa toàn bộ đối tượng lớn hoặc dữ liệu nhạy cảm vào session/conversation chỉ vì muốn giữ chúng lâu hơn; lưu khóa định danh và tải lại dữ liệu từ service khi phù hợp. Khi rời state, `viewScope` kết thúc theo vòng đời của view đó; vì vậy, action `on-exit` cần đọc dữ liệu từ scope vẫn còn hiệu lực tại thời điểm cleanup.

## 7. Xử lý lỗi và side effect an toàn

Các action trong flow có thể gọi database hoặc dịch vụ bên ngoài. Cần thiết kế chúng để lỗi không làm hành trình rơi vào trạng thái không thể phục hồi:

1. **Xác thực trước side effect.** Kiểm tra dữ liệu form và quy tắc nghiệp vụ trước khi tạo giao dịch, giữ chỗ hoặc thu tiền.
2. **Đặt transaction ở service nghiệp vụ.** Một action của flow nên gọi một thao tác service có ranh giới transaction rõ ràng, thay vì tự chia nhỏ cập nhật dữ liệu qua nhiều action XML.
3. **Thiết kế thao tác có thể lặp an toàn.** Người dùng có thể gửi lại request, tải lại trang hoặc khôi phục flow. Các thao tác như tạo đơn, giữ chỗ và gửi thông báo cần khóa idempotency hoặc cơ chế chống xử lý trùng phù hợp.
4. **Dọn dẹp có tính phòng thủ.** Action `on-exit` nên giải phóng đúng tài nguyên đã được cấp, chịu được trường hợp tài nguyên đã hết hạn hoặc đã được giải phóng, và không phụ thuộc vào một transition duy nhất.
5. **Xử lý exception có chủ đích.** Ghi log đủ ngữ cảnh, ánh xạ lỗi nghiệp vụ sang state hoặc thông báo phù hợp, và giữ dữ liệu người dùng cần để thử lại. Không hiển thị stack trace hay thông tin nội bộ cho người dùng.

Đặc biệt, không coi việc một transition được khai báo là bảo đảm action của nó luôn hoàn tất. Một action có thể phát sinh exception hoặc service có thể thất bại. Với thao tác không thể đảo ngược, hãy bảo đảm tính nhất quán ở tầng nghiệp vụ và có phương án xử lý khi flow cần tiếp tục sau lỗi.

## 8. Kiểm thử transition và state exit

Kiểm thử nên xác nhận cả state đích lẫn những action đã chạy. Chỉ kiểm tra trang cuối cùng có thể bỏ sót lỗi cleanup hoặc side effect bị gọi nhầm nhánh.

- **Gửi hợp lệ:** phát event `submit`, xác nhận dữ liệu đã binding, validation thành công, action gửi được gọi và flow đi tới nhánh tiếp theo.
- **Validation thất bại:** gửi dữ liệu sai, xác nhận flow vẫn ở view-state hiện tại, message lỗi xuất hiện và action của transition thành công chưa chạy.
- **Hủy:** phát event `cancel`, xác nhận action ghi nhận hủy chạy, state nguồn được rời và tài nguyên được giải phóng.
- **Hai nhánh decision:** kiểm tra dữ liệu ở dưới và trên ngưỡng để bảo đảm cả `then` lẫn `else` dẫn tới đúng state.
- **Kết quả action-state:** giả lập action trả về từng event đã khai báo và xác nhận transition tương ứng được chọn; thử cả lỗi dịch vụ.
- **Thứ tự vòng đời:** dùng mock hoặc bộ ghi sự kiện để xác nhận action entry, exit và transition được gọi ở đúng thời điểm; bảo đảm `on-exit` không chạy khi validation giữ người dùng ở state hiện tại.
- **Gửi lặp:** phát lại event hoặc mô phỏng request lặp để xác nhận side effect không tạo bản ghi, đơn hàng hoặc thông báo trùng.

Có thể dùng bộ hỗ trợ kiểm thử của Spring Web Flow để khởi chạy flow, gửi event qua `MockExternalContext`, thay thế bean nghiệp vụ bằng mock và kiểm tra state hiện tại cùng dữ liệu trong scope. Với phần tích hợp Spring MVC, bổ sung kiểm thử request thực tế để xác nhận form phát đúng event ID và flow execution được tiếp tục đúng cách.

## 9. Lỗi thiết kế thường gặp

| Cách làm dễ gây lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt mọi side effect trong `on-entry` | Mỗi lần quay lại state có thể chạy lại thao tác | Chỉ để khởi tạo hoặc chuẩn bị dữ liệu; chuyển side effect theo nhánh vào transition phù hợp |
| Dùng `on-render` để lưu hoặc tạo giao dịch | Render lại sau validation có thể lặp thao tác | Chỉ dùng cho công việc phục vụ render; nghiệp vụ đặt trong action/ service có kiểm soát |
| Dùng `on-exit` để quyết định người dùng có được rời state | Cleanup bị trộn với điều kiện điều hướng | Dùng validation, decision-state hoặc action-state trước khi đi tới state đích |
| Đặt quy tắc miền dài trong EL | Khó kiểm thử và khó tái sử dụng | Đưa quy tắc vào service, để flow nhận kết quả và chọn nhánh |
| Dùng `viewScope` cho dữ liệu cần ở state kế tiếp | Dữ liệu biến mất khi view-state kết thúc | Chuyển dữ liệu cần giữ sang `flowScope` hoặc scope phù hợp |
| Không khai báo transition cho một event/kết quả action | Flow gặp lỗi không có nhánh xử lý | Liệt kê event có thể phát ra và kiểm thử từng kết quả |

## 10. Quy trình chọn đúng cơ chế

Khi thiết kế một state, hãy lần lượt trả lời các câu hỏi sau:

1. Người dùng hoặc flow con có thể phát những event nào? Khai báo transition theo từng event bằng `on`.
2. Dữ liệu gửi lên có cần binding và validation không? Cấu hình `bind` và `validate` trên transition tương ứng.
3. Công việc chỉ thuộc một nhánh hay áp dụng cho mọi lần rời state? Dùng action trong transition cho nhánh cụ thể, dùng `on-exit` cho cleanup chung.
4. Flow cần rẽ nhánh theo một biểu thức boolean hay theo kết quả của một thao tác? Dùng `decision-state` cho điều kiện, `action-state` cho action trả về event.
5. Dữ liệu cần tồn tại tới đâu? Chọn `viewScope`, `flowScope` hoặc scope khác theo vòng đời thực tế.
6. Nếu action thất bại hoặc request bị gửi lặp, flow có thể phục hồi an toàn không? Kiểm tra exception path, transaction và idempotency.

Khi các câu trả lời này được thể hiện rõ trong flow definition, transition trở thành ranh giới dễ đọc giữa một bước và bước tiếp theo. State action quản lý vòng đời của bước, transition action xử lý công việc riêng của nhánh, còn decision/action-state thể hiện điều kiện nghiệp vụ để hành trình tiếp tục đúng hướng.
