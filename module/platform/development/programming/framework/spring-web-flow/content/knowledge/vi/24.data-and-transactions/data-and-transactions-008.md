# End-state có commit và kết thúc không commit

Trong chương **Dữ liệu và giao dịch**, bài này giải thích cách chọn điểm kết thúc một flow có ghi dữ liệu: khi nào cần commit thay đổi, khi nào cần kết thúc mà không commit, và ranh giới nào thuộc về Spring Web Flow hay transaction của service. Một flow đặt hàng có thể kết thúc thành công sau khi xác nhận, nhưng cũng có thể kết thúc vì người dùng hủy hoặc dữ liệu không còn hợp lệ. Hai kết quả này không nên có cùng chính sách lưu dữ liệu.

Spring Web Flow điều phối quy trình qua state, event, transition và end-state. Khi ứng dụng dùng flow-managed persistence, end-state có thể xác định persistence context của flow được commit hay không. Đây là cơ chế gắn với persistence context được quản lý trong flow; nó không tự động điều khiển mọi transaction mà service hoặc hệ thống bên ngoài đã thực hiện.

## 1. Phân biệt kết thúc flow và commit dữ liệu

`end-state` xác định flow đã hoàn tất một nhánh nghiệp vụ. Commit xác định các thay đổi thuộc transaction/persistence context liên quan có được ghi nhận hay bị hủy. Hai khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Kết thúc flow | Chấm dứt lần thực thi flow hiện tại hoặc kết thúc subflow để trả kết quả cho flow cha. | Người dùng xác nhận hoặc hủy quy trình. |
| Commit | Xác nhận các thay đổi đang được quản lý trong transaction/persistence context tương ứng. | Lưu trạng thái đơn hàng đã xác nhận. |
| Rollback | Hủy các thay đổi chưa commit trong transaction tương ứng. | Bỏ các cập nhật tạm khi người dùng hủy. |
| Đóng persistence context | Giải phóng context và tài nguyên liên quan khi vòng đời kết thúc. | Kết thúc context được tạo cho flow. |

Một flow có thể kết thúc mà không commit. Điều đó vẫn là một kết thúc hợp lệ: người dùng đã hủy, quy trình bị từ chối hoặc ứng dụng đã chọn nhánh dừng. Flow execution kết thúc; thay đổi chưa commit trong persistence context được quản lý sẽ không được lưu như nhánh commit.

Ngược lại, commit không có nghĩa mọi thao tác bên ngoài đều có thể hoàn tác hoặc mọi dữ liệu của flow đều được lưu tự động. Phạm vi commit phụ thuộc vào persistence context và transaction manager được cấu hình trong ứng dụng.

## 2. Flow-managed persistence và thuộc tính commit của end-state

Spring Web Flow hỗ trợ quản lý persistence context theo vòng đời flow thông qua phần tử `persistence-context`. Khi tính năng này được cấu hình với persistence provider và flow builder services tương thích, flow có một persistence context gắn với lần thực thi của nó. Thuộc tính `commit` trên end-state điều khiển việc commit context đó khi flow đi đến điểm kết thúc.

Ví dụ cấu trúc:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <persistence-context />

    <var name="booking" class="com.example.booking.Booking" />

    <view-state id="editBooking" view="booking/edit">
        <transition on="submit" to="reviewBooking" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <view-state id="reviewBooking" view="booking/review">
        <transition on="confirm" to="confirmed" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <end-state id="confirmed" commit="true" />
    <end-state id="cancelled" commit="false" />
</flow>
```

Ví dụ giả định ứng dụng đã cấu hình persistence-context factory/provider phù hợp trong flow builder services. Chỉ thêm `<persistence-context />` khi ứng dụng thực sự dùng flow-managed persistence; phần tử này không thay thế cấu hình datasource, entity manager/session factory hoặc transaction manager.

Ở nhánh `confirmed`, `commit="true"` yêu cầu commit các thay đổi thuộc persistence context được quản lý khi flow kết thúc. Ở nhánh `cancelled`, `commit="false"` kết thúc flow mà không commit các thay đổi đó. Hãy ghi rõ giá trị commit ở từng end-state để ý định nghiệp vụ dễ đọc và dễ kiểm thử; không dựa vào giá trị mặc định ngầm định khi đọc hoặc nâng cấp cấu hình.

## 3. Mô hình hóa nhánh thành công và nhánh hủy

Giả sử người dùng tạo một bản nháp đặt lịch, cập nhật thông tin rồi xem lại trước khi xác nhận. Có hai kết quả chính:

- **Xác nhận:** thay đổi được chấp nhận và cần commit.
- **Hủy:** thay đổi chưa được xác nhận không được commit từ persistence context của flow.

Có thể mô hình hóa rõ hai nhánh ở transition:

```xml
<view-state id="reviewBooking" view="booking/review">
    <transition on="confirm" to="confirmed">
        <evaluate expression="bookingService.prepareConfirmation(flowScope.booking)" />
    </transition>
    <transition on="cancel" to="cancelled" />
</view-state>

<end-state id="confirmed" commit="true">
    <output name="bookingId" value="flowScope.booking.id" />
</end-state>

<end-state id="cancelled" commit="false">
    <output name="result" value="'CANCELLED'" />
</end-state>
```

`prepareConfirmation` trong ví dụ chỉ chuẩn bị thay đổi trong persistence context đang được quản lý. Nó không nên tự mở một transaction độc lập rồi commit trước khi flow đến end-state nếu mục tiêu là để end-state quyết định commit. Nếu service thực hiện một transaction riêng có commit, cần hiểu rằng `commit="false"` ở end-state không thể hoàn tác transaction đã hoàn tất đó.

Output của end-state là dữ liệu flow trả cho bên gọi hoặc flow cha. Output không tự tạo transaction và cũng không chứng minh một thao tác bên ngoài đã thành công. Với nhánh xác nhận, chỉ xuất `bookingId` sau khi dữ liệu đã ở trạng thái hợp lệ theo quy trình commit của ứng dụng.

## 4. Ranh giới với transaction của service

Trong ứng dụng Spring, service thường dùng `@Transactional` để quản lý transaction cho một đơn vị nghiệp vụ. Ví dụ:

```java
import org.springframework.transaction.annotation.Transactional;

public class BookingService {

    @Transactional
    public Booking confirm(Long bookingId) {
        Booking booking = repository.findById(bookingId)
                .orElseThrow(() -> new BookingNotFoundException(bookingId));

        booking.confirm();
        return booking;
    }
}
```

Khi phương thức `confirm` kết thúc bình thường, transaction do Spring transaction manager quản lý có thể được commit theo cấu hình propagation và transaction hiện tại. Nếu phương thức ném exception, hành vi rollback phụ thuộc loại exception và rollback rules. Đây là ranh giới transaction của service.

Thuộc tính `commit` của end-state không phải công tắc toàn cục cho mọi `@Transactional` trong ứng dụng. Nếu service đã commit transaction riêng trước khi flow đi đến end-state, sau đó flow kết thúc với `commit="false"`, thay đổi của service vẫn đã được commit. Tương tự, một service có `REQUIRES_NEW` có thể commit độc lập với transaction bao quanh flow.

Vì vậy, hãy chọn một chiến lược nhất quán:

1. Dùng flow-managed persistence khi muốn persistence context gắn với vòng đời flow và cần quyết định commit ở end-state.
2. Dùng transaction service cho từng thao tác nghiệp vụ độc lập, ngắn gọn và có ranh giới commit rõ ràng.
3. Nếu kết hợp hai cơ chế, xác định rõ persistence context/transaction nào được chia sẻ, propagation nào được sử dụng và thay đổi nào đã được commit trước khi flow kết thúc.

Không giữ một database transaction mở trong suốt thời gian người dùng suy nghĩ qua nhiều màn hình. Quy trình nhiều bước có thể kéo dài, người dùng có thể bỏ trang hoặc mất kết nối. Hãy giữ transaction ở ranh giới xử lý ngắn; nếu cần trạng thái tạm qua nhiều request, dùng draft/persistence context phù hợp và kiểm tra khả năng đồng thời.

## 5. Commit không hoàn tác được side effect bên ngoài

Rollback chỉ áp dụng cho thay đổi được quản lý bởi transaction có khả năng rollback. Nó không tự thu hồi email đã gửi, HTTP request đã gọi sang hệ thống khác, thông báo đã phát hoặc khoản tiền đã được cổng thanh toán thu.

Ví dụ, nếu flow gọi service gửi email xác nhận rồi sau đó kết thúc với `commit="false"`, email đã gửi vẫn có thể đến người nhận. Nếu flow gọi cổng thanh toán và giao dịch đã thành công, rollback database nội bộ không thể tự hoàn tiền.

Với side effect bên ngoài, nên:

- Chỉ gửi thông báo sau khi trạng thái nghiệp vụ được commit, hoặc ghi một outbox event trong cùng transaction rồi để worker phát thông báo.
- Dùng idempotency key cho yêu cầu thanh toán, tạo đơn và callback để request lặp không thực hiện nghiệp vụ hai lần.
- Với thao tác không thể rollback, thiết kế hành động bù (compensation) như hoàn tiền hoặc hủy đặt chỗ theo quy trình riêng.
- Ghi nhận trạng thái trung gian rõ ràng như `PENDING`, `CONFIRMED`, `CANCEL_REQUESTED` hoặc `REFUND_PENDING`.

Không gọi API bên ngoài trong một transaction database với giả định rollback sẽ đảo ngược cả hai hệ thống. Cần thiết kế nhất quán phân tán phù hợp, ví dụ outbox, saga hoặc thao tác bù.

## 6. Kết thúc không commit khác với lỗi và rollback do exception

End-state `commit="false"` là một nhánh kết thúc có chủ đích. Nó khác với exception xảy ra giữa quá trình xử lý:

| Tình huống | Cách flow kết thúc | Điều cần lưu ý |
| --- | --- | --- |
| Người dùng hủy | Đi đến end-state hủy với `commit="false"`. | Kết thúc bình thường nhưng không commit persistence context của flow. |
| Nghiệp vụ từ chối | Đi đến end-state từ chối với chính sách commit được xác định rõ. | Có thể cần lưu dấu vết từ chối trong một transaction service riêng. |
| Service ném exception | Exception được truyền qua cơ chế xử lý lỗi của flow/transaction. | Rollback phụ thuộc transaction manager và rollback rules; không nhất thiết đi qua end-state hủy. |
| Session hoặc execution hết hạn | Flow execution không còn được tiếp tục. | Cần chính sách dọn dẹp context và dữ liệu tạm; không giả định một end-state đã chạy. |
| Flow kết thúc thành công | Đi đến end-state commit phù hợp. | Chỉ các thay đổi trong transaction/context liên quan mới chịu tác động commit. |

Nếu cần lưu lại lý do hủy, hãy ghi nhận qua một service với transaction ngắn và độc lập, hoặc xuất kết quả hủy cho flow cha. Đừng đặt `commit="true"` ở nhánh hủy chỉ để lưu một thông báo nếu điều đó đồng thời commit cả các thay đổi nghiệp vụ chưa được xác nhận. Tách dữ liệu audit/draft khỏi thay đổi cần rollback.

## 7. Chọn chính sách commit cho nhiều end-state

Một flow thực tế có thể có nhiều kết quả hơn chỉ thành công và hủy:

```xml
<end-state id="confirmed" commit="true">
    <output name="result" value="'CONFIRMED'" />
    <output name="bookingId" value="flowScope.booking.id" />
</end-state>

<end-state id="cancelled" commit="false">
    <output name="result" value="'CANCELLED'" />
</end-state>

<end-state id="rejected" commit="false">
    <output name="result" value="'REJECTED'" />
</end-state>
```

Chính sách thường gặp:

| End-state | Commit | Lý do |
| --- | --- | --- |
| `confirmed` | `true` | Lưu thay đổi đã được người dùng xác nhận. |
| `cancelled` | `false` | Bỏ thay đổi tạm chưa được chấp nhận. |
| `rejected` | `false` | Không lưu các thay đổi nghiệp vụ không được chấp nhận. |
| `previewFinished` | Tùy mục đích | Nếu chỉ xem trước, không commit; nếu preview có ghi nhận nghiệp vụ, phải xác định transaction cụ thể. |

Đừng quyết định commit chỉ dựa trên tên end-state. Hãy xác định dữ liệu nào đã thay đổi, thay đổi đó thuộc persistence context nào và kết quả có cần được lưu không. Một nhánh `rejected` vẫn có thể cần lưu bản ghi audit, nhưng bản ghi đó nên được ghi bằng transaction riêng có chủ đích thay vì commit toàn bộ persistence context chứa thay đổi bị từ chối.

## 8. Subflow và chính sách commit

Subflow có flow execution và flow scope riêng, nhưng có thể hoạt động trong conversation của flow cha. Khi subflow kết thúc, flow cha nhận event tương ứng với end-state và các output được khai báo. Nếu dùng flow-managed persistence, cần xác định persistence context được tạo ở flow nào và phạm vi commit áp dụng ra sao trong cấu hình thực tế.

Ví dụ flow cha gọi subflow thanh toán:

```xml
<subflow-state id="payment" subflow="payment">
    <input name="bookingId" value="flowScope.booking.id" />
    <transition on="paid" to="confirmed">
        <evaluate expression="currentEvent.attributes.transactionId"
                  result="flowScope.transactionId" />
    </transition>
    <transition on="cancelled" to="cancelled" />
</subflow-state>
```

Flow con có thể kết thúc bằng `paid` hoặc `cancelled` và xuất `transactionId` khi phù hợp. Không mặc định rằng `commit="false"` ở end-state của flow cha sẽ rollback transaction mà service thanh toán hoặc flow con đã commit độc lập. Kiểm tra transaction manager, persistence context factory và propagation của service trong cấu hình đang chạy.

Với thanh toán thật, service nên xác minh kết quả với nhà cung cấp và ghi nhận trạng thái giao dịch bằng transaction nghiệp vụ riêng. Subflow chỉ điều phối các bước và trả kết quả; end-state của flow cha không thể thay thế quy trình hoàn tiền hoặc bù trừ.

## 9. Kiểm thử commit và kết thúc không commit

Kiểm thử cần xác nhận trạng thái dữ liệu trong persistence store, không chỉ xác nhận flow đã đến đúng end-state.

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| Flow kết thúc ở `confirmed`, `commit="true"` | Thay đổi thuộc flow-managed persistence context được commit và đọc lại được từ transaction mới. |
| Flow kết thúc ở `cancelled`, `commit="false"` | Thay đổi chưa commit trong context được rollback/không xuất hiện trong dữ liệu bền vững. |
| Flow kết thúc ở `rejected` | Không có thay đổi nghiệp vụ bị từ chối được lưu ngoài những audit record được thiết kế riêng. |
| Service `@Transactional` đã commit trước end-state | Kiểm tra dữ liệu vẫn tồn tại dù end-state của flow đặt `commit="false"`. |
| Service ném exception | Xác nhận rollback theo transaction boundary và rollback rules thực tế. |
| Gọi API/email trước khi flow kết thúc | Xác nhận side effect không được coi là đã rollback cùng database. |
| Subflow kết thúc | Xác nhận output/event đúng và transaction/context của cha-con theo cấu hình. |
| Người dùng gửi event lặp | Xác nhận thao tác commit không tạo dữ liệu hoặc giao dịch trùng. |

Flow execution test có thể kiểm tra state, event và output. Để xác nhận commit/rollback, cần thêm integration test với database thử nghiệm và transaction manager thực tế. Sau khi flow kết thúc, mở một transaction mới hoặc dùng repository trong transaction mới để đọc lại dữ liệu; không kiểm tra bằng cùng persistence context còn giữ entity trong bộ nhớ.

Với nhánh không commit, test nên tạo thay đổi có thể quan sát được trước end-state, kết thúc bằng `commit="false"`, rồi xác nhận thay đổi đó không được lưu. Với nhánh commit, chạy cùng kịch bản nhưng kết thúc bằng `commit="true"` và xác nhận thay đổi được lưu. Bổ sung test cho service `REQUIRES_NEW` hoặc transaction độc lập nếu ứng dụng sử dụng propagation đó.

## 10. Lỗi thiết kế thường gặp

- **Cho rằng `commit="false"` rollback mọi thao tác của flow:** thuộc tính chỉ tác động đến flow-managed persistence context phù hợp; transaction service đã commit không bị đảo ngược.
- **Dùng end-state hủy để xử lý exception:** exception có thể đi qua exception handler và transaction rollback rules mà không đi đến end-state hủy.
- **Giữ transaction database mở qua nhiều màn hình:** thời gian chờ của người dùng có thể dài, làm giữ khóa và tài nguyên. Dùng transaction ngắn và trạng thái draft phù hợp.
- **Commit nhánh từ chối để lưu audit:** có thể vô tình lưu cả thay đổi nghiệp vụ bị từ chối. Tách audit sang transaction riêng.
- **Giả định rollback thu hồi email hoặc thanh toán:** side effect bên ngoài cần outbox, idempotency hoặc hành động bù.
- **Chỉ kiểm tra end-state trong test:** state đúng không chứng minh database đã commit hoặc rollback. Kiểm tra bằng transaction mới.
- **Không ghi rõ commit policy:** các nhánh thành công, hủy và từ chối khó được review. Đặt giá trị rõ ràng ở từng end-state khi dùng flow-managed persistence.

## 11. Quy trình thực hành

Với flow đặt lịch, triển khai theo thứ tự sau:

1. Xác định dữ liệu nào được sửa trong quá trình người dùng nhập và dữ liệu nào cần tồn tại lâu dài.
2. Chọn flow-managed persistence nếu cần persistence context gắn với vòng đời flow; cấu hình provider, transaction manager và flow builder services tương thích.
3. Tạo end-state `confirmed` với `commit="true"` và end-state `cancelled` với `commit="false"`.
4. Giữ các service transaction độc lập ở ranh giới ngắn; không để một service commit sớm nếu muốn end-state kiểm soát chính thay đổi đó.
5. Tách audit và side effect bên ngoài khỏi thay đổi cần rollback; dùng outbox/idempotency hoặc compensation khi cần.
6. Kiểm thử cả flow execution lẫn trạng thái database sau khi flow kết thúc.
7. Kiểm tra riêng nhánh exception, timeout, callback lặp và subflow để bảo đảm transaction boundary đúng như thiết kế.

Khi hoàn thành, mỗi end-state thể hiện rõ kết quả nghiệp vụ và chính sách commit tương ứng. Flow điều phối việc xác nhận, hủy hoặc từ chối; persistence context và transaction manager quyết định thay đổi dữ liệu nào được lưu; service chịu trách nhiệm với transaction nghiệp vụ độc lập; còn side effect bên ngoài được xử lý bằng cơ chế phù hợp thay vì kỳ vọng rollback database có thể đảo ngược chúng.
