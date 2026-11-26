# Hành động trả kết quả để cho phép hoặc chặn chuyển bước

Trong chương **Event và transition**, một flow không chỉ chuyển bước theo nút người dùng bấm. Có những bước cần gọi nghiệp vụ để kiểm tra điều kiện trước khi cho phép hành trình tiếp tục: xác minh đặt chỗ, kiểm tra hạn mức, xác nhận hồ sơ còn hợp lệ hoặc kiểm tra một yêu cầu có đủ điều kiện xử lý hay không.

Spring Web Flow hỗ trợ mô hình này bằng **action-state**. State này thực thi một hành động, nhận kết quả dưới dạng event rồi chọn transition tương ứng. Hành động có thể trả kết quả cho phép, từ chối hoặc báo dữ liệu đầu vào không hợp lệ. Nhờ vậy, quy tắc nghiệp vụ quyết định hướng đi của flow tại một điểm rõ ràng, thay vì để controller tự điều hướng qua nhiều màn hình.

Bài học thuộc module **SPRING_WEB_FLOW**, nơi ta dùng state, event, transition và subflow để mô hình hóa hành trình web nhiều bước. Trọng tâm ở đây là cách một hành động trả kết quả để cho phép hoặc chặn chuyển bước, cách nối kết quả đó với transition, và cách kiểm thử cả hai nhánh.

## 1. Hai loại event trong cùng một hành trình

Hãy hình dung người dùng gửi biểu mẫu đặt chỗ. Sau khi nhận biểu mẫu, hệ thống phải kiểm tra chính sách đặt chỗ trước khi cho người dùng đến màn hình xác nhận.

Trong tình huống này có hai event khác nhau:

1. **Event từ người dùng**: người dùng bấm nút Gửi. Ví dụ event có ID là `submit`.
2. **Event từ hành động nghiệp vụ**: hệ thống kiểm tra dữ liệu và trả về kết quả. Ví dụ `allowed`, `blocked` hoặc `invalid`.

Event đầu tiên đưa flow từ view-state sang action-state. Event thứ hai quyết định action-state sẽ chuyển đến state nào.

| Thành phần | Nguồn phát sinh | Vai trò |
|---|---|---|
| `submit` | Người dùng gửi form | Yêu cầu flow chạy bước kiểm tra |
| `allowed` | Hành động nghiệp vụ | Cho phép đi đến bước xác nhận |
| `blocked` | Hành động nghiệp vụ | Chuyển đến màn hình giải thích lý do từ chối |
| `invalid` | Hành động nghiệp vụ | Chuyển đến bước xử lý dữ liệu đầu vào không hợp lệ |

Không nên coi event `submit` là kết quả kiểm tra. Việc người dùng gửi form chỉ thể hiện ý định tiếp tục; nó chưa chứng minh yêu cầu đã đáp ứng điều kiện nghiệp vụ.

## 2. Action-state thực thi hành động và chọn transition theo kết quả

Một `action-state` là state dùng để thực thi một hoặc nhiều action mà không cần hiển thị view tại chính state đó. Sau khi action chạy, kết quả của nó được biểu diễn bằng một event. Spring Web Flow so khớp ID của event với thuộc tính `on` của các transition được khai báo trong action-state.

Ví dụ:

~~~xml
<action-state id="checkEligibility">
    <evaluate expression="eligibilityAction.check(flowScope.booking)" />

    <transition on="allowed" to="reviewBooking" />
    <transition on="blocked" to="notEligible" />
    <transition on="invalid" to="inputProblem" />
</action-state>
~~~

Trong ví dụ này:

- Flow gọi phương thức `check` của bean `eligibilityAction`.
- Đối tượng đặt chỗ được lấy từ `flowScope.booking`.
- Nếu kết quả có event ID là `allowed`, flow chuyển sang `reviewBooking`.
- Nếu kết quả có event ID là `blocked`, flow chuyển sang `notEligible`.
- Nếu kết quả có event ID là `invalid`, flow chuyển sang `inputProblem`.

Giá trị `on` phải khớp chính xác với event ID mà action trả về. Ví dụ, action trả `blocked` nhưng flow chỉ khai báo `on="denied"` thì không có transition tương ứng để xử lý kết quả đó. Khi thiết kế flow, nên liệt kê trước các kết quả hợp lệ của action rồi khai báo đầy đủ đường đi cho từng kết quả.

## 3. Viết action trả về Event

Trong Spring Web Flow, một action có thể trả về đối tượng `Event`. Event có nguồn phát sinh và một ID. Flow dùng ID để chọn transition.

Ví dụ, hành động kiểm tra điều kiện đặt chỗ có thể được viết như sau:

~~~java
import org.springframework.webflow.execution.Event;

public class EligibilityAction {

    private final BookingPolicy bookingPolicy;

    public EligibilityAction(BookingPolicy bookingPolicy) {
        this.bookingPolicy = bookingPolicy;
    }

    public Event check(Booking booking) {
        if (booking == null) {
            return new Event(this, "invalid");
        }

        if (bookingPolicy.isEligible(booking)) {
            return new Event(this, "allowed");
        }

        return new Event(this, "blocked");
    }
}
~~~

Trong ví dụ:

- `BookingPolicy` chứa quy tắc nghiệp vụ để xác định một đặt chỗ có đủ điều kiện hay không.
- `booking == null` là trường hợp đầu vào không hợp lệ.
- `isEligible` trả về `true` thì action phát event `allowed`.
- Nếu chính sách không chấp nhận đặt chỗ, action phát event `blocked`.

Bean có thể được khai báo trong cấu hình Spring:

~~~xml
<bean id="eligibilityAction"
      class="com.example.flow.EligibilityAction">
    <constructor-arg ref="bookingPolicy" />
</bean>
~~~

Tên package, lớp và bean trong ví dụ cần được thay bằng các thành phần thực tế của ứng dụng. Điểm quan trọng là phương thức được gọi trong biểu thức `evaluate` trả về một Event có ID tương ứng với các transition.

Một action có thể triển khai trực tiếp interface `org.springframework.webflow.execution.Action` và nhận `RequestContext` trong phương thức `execute`. Cách này hữu ích khi hành động cần đọc hoặc ghi dữ liệu trong flow scope, request scope hay message context:

~~~java
import org.springframework.webflow.execution.Action;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public class EligibilityFlowAction implements Action {

    @Override
    public Event execute(RequestContext context) {
        Booking booking =
            (Booking) context.getFlowScope().get("booking");

        if (booking == null) {
            return new Event(this, "invalid");
        }

        boolean eligible = checkPolicy(booking);

        return eligible
            ? new Event(this, "allowed")
            : new Event(this, "blocked");
    }

    private boolean checkPolicy(Booking booking) {
        // Gọi dịch vụ hoặc chính sách nghiệp vụ phù hợp.
        return booking.getAge() >= 18;
    }
}
~~~

Khi triển khai `Action`, có thể gọi action qua flow executor hoặc đăng ký bean để biểu thức trong flow gọi nó. Cần bảo đảm bean được Spring quản lý và có sẵn trong context mà flow sử dụng.

Với cả hai cách, hãy trả về một kết quả tường minh cho mọi trường hợp nghiệp vụ dự kiến. Không nên trả `null` khi không đủ điều kiện, vì flow sẽ không có event ID rõ ràng để chọn transition.

## 4. Nối event từ form với kết quả của action

Ta xây dựng flow đặt chỗ gồm form, bước kiểm tra, màn hình xác nhận và các màn hình phản hồi khi không được phép tiếp tục.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="bookingForm">

    <var name="booking" class="com.example.Booking" />

    <view-state id="bookingForm" view="bookingForm">
        <transition on="submit" to="checkEligibility" />
    </view-state>

    <action-state id="checkEligibility">
        <evaluate expression="eligibilityAction.check(flowScope.booking)" />
        <transition on="allowed" to="reviewBooking" />
        <transition on="blocked" to="notEligible" />
        <transition on="invalid" to="inputProblem" />
    </action-state>

    <view-state id="reviewBooking" view="reviewBooking">
        <transition on="confirm" to="complete" />
        <transition on="edit" to="bookingForm" />
    </view-state>

    <view-state id="notEligible" view="notEligible">
        <transition on="edit" to="bookingForm" />
    </view-state>

    <view-state id="inputProblem" view="inputProblem">
        <transition on="edit" to="bookingForm" />
    </view-state>

    <end-state id="complete" view="complete" />
</flow>
~~~

Để dễ theo dõi, ví dụ giả định view `bookingForm` đã bind dữ liệu người dùng nhập vào đối tượng `booking` trong flow scope. Cấu hình binder, validator và view resolver cần được bổ sung theo công nghệ giao diện mà ứng dụng đang sử dụng.

Khi người dùng gửi form, view có thể phát event `submit` bằng một nút như sau:

~~~html
<form method="post">
    <!-- Các trường dữ liệu đã bind vào booking -->
    <button type="submit" name="_eventId_submit">
        Kiểm tra điều kiện
    </button>
</form>
~~~

Tên trường `_eventId_submit` phát event `submit`. Flow rời `bookingForm` và đi vào `checkEligibility`. Tại action-state, biểu thức `evaluate` gọi action. Event do action trả về sau đó chọn một trong ba transition.

### Luồng xử lý tổng thể

~~~mermaid
flowchart TD
    A["bookingForm<br/>Người dùng gửi form"] -->|"submit"| B["checkEligibility<br/>Chạy action"]
    B -->|"allowed"| C["reviewBooking<br/>Cho phép xác nhận"]
    B -->|"blocked"| D["notEligible<br/>Từ chối theo chính sách"]
    B -->|"invalid"| E["inputProblem<br/>Dữ liệu không hợp lệ"]
    C -->|"confirm"| F["complete<br/>Kết thúc"]
    C -->|"edit"| A
    D -->|"edit"| A
    E -->|"edit"| A
~~~

Sơ đồ cho thấy action-state là điểm kiểm tra tập trung. Người dùng không thể đi thẳng từ form đến bước xác nhận chỉ bằng cách gửi event `submit`; flow phải chạy action và nhận kết quả `allowed` mới đi đến `reviewBooking`.

## 5. Phân biệt kết quả nghiệp vụ và lỗi kỹ thuật

Không phải mọi trường hợp action không thể tiếp tục đều có cùng ý nghĩa. Cần phân biệt kết quả nghiệp vụ bình thường với lỗi khi thực thi.

| Tình huống | Cách biểu diễn phù hợp | Hướng xử lý |
|---|---|---|
| Đặt chỗ đáp ứng chính sách | Event `allowed` | Chuyển đến bước xác nhận |
| Đặt chỗ không đáp ứng chính sách | Event `blocked` | Hiển thị lý do hoặc hướng dẫn phù hợp |
| Thiếu đối tượng hoặc dữ liệu không hợp lệ | Event `invalid` | Quay lại bước nhập hoặc sửa dữ liệu |
| Dịch vụ nghiệp vụ không truy cập được | Exception phù hợp | Xử lý theo nhánh lỗi kỹ thuật hoặc cơ chế xử lý exception |
| Lỗi lập trình không dự kiến | Exception | Ghi log và để cơ chế xử lý lỗi của ứng dụng tiếp nhận |

Từ chối nghiệp vụ không nhất thiết là exception. Ví dụ, khách hàng chưa đủ điều kiện đặt chỗ là một kết quả hợp lệ của việc kiểm tra chính sách. Action nên trả event `blocked` để flow chuyển đến màn hình giải thích.

Ngược lại, nếu dịch vụ chính sách không thể kết nối cơ sở dữ liệu, đó là lỗi kỹ thuật. Không nên biến mọi exception thành kết quả `blocked`, vì người dùng có thể hiểu nhầm rằng yêu cầu của họ vi phạm chính sách trong khi hệ thống thực tế chưa kiểm tra được.

Với exception có thể dự đoán, flow có thể khai báo transition xử lý exception phù hợp:

~~~xml
<action-state id="checkEligibility">
    <evaluate expression="eligibilityAction.check(flowScope.booking)" />

    <transition on="allowed" to="reviewBooking" />
    <transition on="blocked" to="notEligible" />
    <transition on="invalid" to="inputProblem" />
    <transition
        on-exception="com.example.ServiceUnavailableException"
        to="serviceUnavailable" />
</action-state>
~~~

State `serviceUnavailable` cần được định nghĩa trong flow, thường là một view-state hiển thị thông báo và hướng dẫn người dùng thử lại sau. Chỉ khai báo các loại exception mà ứng dụng thực sự muốn xử lý tại flow này. Các lỗi không dự kiến vẫn cần được xử lý bởi cơ chế lỗi chung phù hợp.

Nếu action chủ động bắt một exception có thể phục hồi và muốn trả kết quả cho flow, hãy chuyển exception đó thành một event có ý nghĩa rõ ràng, chẳng hạn `temporarilyUnavailable`. Không nên bắt mọi exception rồi trả cùng một event chung, vì cách đó che mất nguyên nhân và làm khó việc theo dõi lỗi.

## 6. Khi nào dùng action-state, khi nào dùng decision-state?

Cả `action-state` và `decision-state` đều có thể dẫn flow đến nhiều nhánh, nhưng chúng giải quyết hai nhu cầu khác nhau.

- Dùng **action-state** khi cần thực thi hành động: gọi service, kiểm tra chính sách qua một thành phần nghiệp vụ, tra cứu dữ liệu hoặc thực hiện một bước xử lý rồi nhận event kết quả.
- Dùng **decision-state** khi chỉ cần đánh giá một điều kiện đã có trong context của flow để chọn nhánh tiếp theo.

Ví dụ decision-state:

~~~xml
<decision-state id="routeByAmount">
    <if test="flowScope.booking.total <= 1000"
        then="automaticReview"
        else="manualReview" />
</decision-state>
~~~

Decision-state đánh giá biểu thức điều kiện và chọn state theo kết quả. Nó phù hợp với điều kiện đơn giản, dễ đọc và không cần gọi một hành động nghiệp vụ riêng.

Nếu điều kiện cần truy cập nhiều nguồn dữ liệu, áp dụng chính sách phức tạp hoặc cần ghi nhận kết quả kiểm tra, hãy đóng gói logic trong service/action rồi dùng action-state. Không nên nhồi một biểu thức dài vào thuộc tính `test` chỉ để tránh tạo action.

| Tiêu chí | Action-state | Decision-state |
|---|---|---|
| Mục đích | Thực thi hành động và nhận event kết quả | Đánh giá điều kiện để chọn nhánh |
| Đầu vào | Dữ liệu flow và dịch vụ được gọi | Biểu thức điều kiện |
| Kết quả | Event ID như `allowed`, `blocked` | Nhánh `then` hoặc `else` |
| Ví dụ | Kiểm tra chính sách đặt chỗ qua service | So sánh tổng tiền với ngưỡng có sẵn |

## 7. Kết quả action không thay thế validation và phân quyền

Action-state là nơi điều phối kết quả nghiệp vụ trong flow. Tuy nhiên, cần đặt từng loại kiểm tra vào đúng lớp.

**Validation dữ liệu biểu mẫu** kiểm tra dữ liệu người dùng gửi lên có đúng định dạng và thỏa ràng buộc dữ liệu hay không. Ví dụ, trường tuổi phải là số hợp lệ hoặc ngày kết thúc không được trước ngày bắt đầu. Validation thường gắn với quá trình binding và submit của view-state.

**Kiểm tra điều kiện nghiệp vụ** quyết định yêu cầu có được phép đi tiếp theo chính sách hiện hành hay không. Ví dụ, đặt chỗ có nằm trong thời hạn nhận đăng ký hoặc tài khoản có đủ hạn mức hay không. Đây là loại kiểm tra phù hợp với action-state khi cần gọi service và trả kết quả để chọn transition.

**Phân quyền truy cập** xác định người dùng hiện tại có quyền thực hiện thao tác hoặc truy cập tài nguyên hay không. Không được xem event `allowed` là bằng chứng xác thực người dùng hoặc quyền truy cập dữ liệu. Service nghiệp vụ và các lớp bảo mật vẫn phải kiểm tra quyền ở nơi thích hợp, kể cả khi người dùng gọi endpoint ngoài flow hoặc gửi lại request cũ.

Việc chia rõ ba lớp giúp flow dễ hiểu: view-state nhận dữ liệu, validation kiểm tra hình thức dữ liệu, action-state đánh giá điều kiện nghiệp vụ và hệ thống bảo mật thực thi quyền truy cập.

## 8. Quản lý dữ liệu và tác động phụ của action

Action có thể đọc dữ liệu từ flow scope, gọi service và ghi kết quả trở lại context. Ví dụ, action có thể lưu lý do từ chối để view `notEligible` hiển thị:

~~~java
public Event check(RequestContext context) {
    Booking booking =
        (Booking) context.getFlowScope().get("booking");

    if (booking == null) {
        context.getFlowScope().put(
            "eligibilityMessage",
            "Không tìm thấy thông tin đặt chỗ."
        );
        return new Event(this, "invalid");
    }

    EligibilityResult result = bookingPolicy.evaluate(booking);

    context.getFlowScope().put(
        "eligibilityMessage",
        result.getMessage()
    );

    return result.isAllowed()
        ? new Event(this, "allowed")
        : new Event(this, "blocked");
}
~~~

Ví dụ này minh họa việc dùng `RequestContext` để truy cập flow scope. Nếu triển khai theo interface `Action`, phương thức `execute` nhận context trực tiếp. Khi gọi một bean method bằng biểu thức EL, hãy chọn chữ ký phương thức phù hợp với đối số mà flow truyền vào.

Dữ liệu cần tồn tại trong suốt hành trình nhiều bước thường được đặt trong flow scope. Dữ liệu chỉ phục vụ một request có thể thuộc request scope. Không nên lưu toàn bộ đối tượng lớn hoặc dữ liệu nhạy cảm vào scope chỉ vì action cần đọc nó; hãy giữ dữ liệu cần thiết và tuân theo chính sách bảo vệ dữ liệu của ứng dụng.

Nếu action chỉ đọc và đánh giá chính sách, việc chạy lại thường ít rủi ro hơn. Nếu action thực hiện tác động phụ như giữ chỗ, trừ tiền, gửi thông báo hoặc tạo đơn hàng, cần xem xét các tình huống người dùng bấm gửi nhiều lần, refresh trang hoặc gửi lại request. Dùng giao dịch ở tầng nghiệp vụ và cơ chế chống xử lý trùng phù hợp, chẳng hạn mã yêu cầu duy nhất hoặc thao tác idempotent. Flow execution không tự bảo đảm một tác động nghiệp vụ chỉ xảy ra đúng một lần.

## 9. Kiểm thử kết quả và transition

Nên kiểm thử cả action riêng lẻ lẫn flow tích hợp. Kiểm thử action xác nhận từng tình huống nghiệp vụ trả đúng event ID. Kiểm thử flow xác nhận event đó dẫn đến đúng state.

Với `EligibilityAction`, các trường hợp tối thiểu gồm:

| Dữ liệu đầu vào | Kết quả mong đợi từ action |
|---|---|
| Đặt chỗ hợp lệ theo chính sách | Event `allowed` |
| Đặt chỗ không đạt chính sách | Event `blocked` |
| Đối tượng đặt chỗ là `null` | Event `invalid` |
| Service chính sách phát sinh lỗi dịch vụ đã dự kiến | Exception hoặc event lỗi đã được thiết kế rõ ràng |

Ở mức flow, cần kiểm tra các đường đi sau:

1. Gửi event `submit` từ `bookingForm`, action trả `allowed`, flow phải đến `reviewBooking`.
2. Gửi event `submit`, action trả `blocked`, flow phải đến `notEligible`.
3. Gửi event `submit`, action trả `invalid`, flow phải đến `inputProblem`.
4. Action phát sinh exception dịch vụ đã khai báo, flow phải đến state xử lý lỗi tương ứng.
5. Từ màn hình từ chối, event `edit` phải đưa người dùng về form theo transition đã định nghĩa.

Trong kiểm thử flow, hãy kiểm tra state hiện tại sau mỗi event thay vì chỉ xác nhận action đã được gọi. Mục tiêu là chứng minh kết quả nghiệp vụ thực sự điều khiển hành trình.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Event ID action trả về không khớp thuộc tính `on` | Flow không tìm được transition phù hợp | Thống nhất danh sách event ID giữa Java và flow XML |
| Chỉ xử lý nhánh thành công | Kết quả từ chối hoặc dữ liệu lỗi không có đường đi rõ ràng | Khai báo transition cho mọi kết quả nghiệp vụ dự kiến |
| Dùng exception cho mọi trường hợp từ chối | Log có nhiều lỗi giả và luồng xử lý khó đọc | Trả event cho kết quả nghiệp vụ bình thường |
| Bắt mọi exception và trả `blocked` | Che giấu lỗi hệ thống, người dùng nhận thông báo sai | Phân biệt từ chối nghiệp vụ với lỗi kỹ thuật |
| Đưa toàn bộ chính sách vào biểu thức EL | Flow XML khó đọc và khó kiểm thử | Đóng gói quy tắc trong service/action |
| Xem event `allowed` là kiểm tra bảo mật | Có thể bỏ sót kiểm tra quyền khi service được gọi từ đường khác | Kiểm tra xác thực và phân quyền tại tầng bảo mật/nghiệp vụ |
| Action có tác động phụ nhưng không chống xử lý trùng | Refresh hoặc gửi lại request có thể tạo thao tác lặp | Dùng giao dịch và cơ chế idempotency ở tầng nghiệp vụ |

Khi gặp lỗi không chuyển state, hãy kiểm tra lần lượt: action có thực sự được gọi không, kết quả trả về có phải Event hợp lệ không, event ID là gì, transition có `on` khớp không, và state đích đã được định nghĩa chưa. Nếu action phát sinh exception, kiểm tra loại exception và đường xử lý lỗi.

## 11. Thực hành: chặn một yêu cầu không đủ điều kiện

Tạo flow kiểm tra đặt chỗ với ba kết quả `allowed`, `blocked` và `invalid`.

1. Khai báo đối tượng `booking` trong flow scope.
2. Tạo bean `eligibilityAction` nhận một `Booking` và trả về Event.
3. Khai báo action-state `checkEligibility` với ba transition tương ứng.
4. Tạo view-state `reviewBooking`, `notEligible` và `inputProblem`.
5. Từ form, phát event `submit` để đi vào action-state.
6. Thử một đối tượng thỏa chính sách và xác nhận flow đến `reviewBooking`.
7. Thử một đối tượng không thỏa chính sách và xác nhận flow đến `notEligible`.
8. Thử trường hợp không có đối tượng và xác nhận flow đến `inputProblem`.
9. Đổi tạm event ID trong action thành một giá trị không được khai báo, quan sát lỗi không có transition phù hợp rồi khôi phục giá trị đúng.

Sau khi thực hành, hãy tự trả lời:

- Event `submit` khác event `allowed` ở điểm nào?
- Thành phần nào quyết định transition sau khi action hoàn thành?
- Vì sao từ chối nghiệp vụ thường nên là một Event thay vì exception?
- Khi nào nên dùng decision-state thay cho action-state?
- Vì sao action-state không thay thế kiểm tra phân quyền?

## 12. Ghi nhớ

Action-state cho phép Spring Web Flow thực thi một hành động rồi chọn transition theo event kết quả. Event từ người dùng như `submit` đưa flow đến bước xử lý; event do action trả về như `allowed`, `blocked` hoặc `invalid` quyết định state tiếp theo. Mỗi event ID cần có transition tương ứng và mọi kết quả nghiệp vụ dự kiến cần có đường đi rõ ràng.

Hãy dùng action-state khi cần gọi service hoặc thực hiện một bước nghiệp vụ có kết quả. Dùng decision-state cho điều kiện rẽ nhánh đơn giản đã có trong context. Tách kết quả nghiệp vụ khỏi exception kỹ thuật, giữ validation và phân quyền ở đúng lớp, đồng thời kiểm thử cả event trả về lẫn state đích. Cách tổ chức này giúp hành trình nhiều bước trong **SPRING_WEB_FLOW** rõ ràng, có thể kiểm thử và dễ phục hồi khi một bước không được phép tiếp tục.
