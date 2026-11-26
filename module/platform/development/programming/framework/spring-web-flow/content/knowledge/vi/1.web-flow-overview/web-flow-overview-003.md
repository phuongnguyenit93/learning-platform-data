# Flow, state, event và transition liên hệ với nhau thế nào?

> **Chương:** Bản đồ Web Flow  
> **Mục tiêu:** Đọc và thiết kế một hành trình web nhiều bước bằng bốn khái niệm cốt lõi của Spring Web Flow: **flow**, **state**, **event** và **transition**. Từ bản đồ này, hiểu được form binding, validation, scope, subflow và cách kiểm thử điều hướng.

## 1. Từ các màn hình rời rạc đến một quy trình

Giả sử một website cần tạo **đăng ký khóa học** qua bốn bước:

1. Người dùng nhập tên và email.
2. Chọn gói học.
3. Xem lại thông tin.
4. Xác nhận đăng ký.

Ở mỗi bước, người dùng có thể muốn **Tiếp tục**, **Quay lại** hoặc **Hủy**. Khi xác nhận, máy chủ phải gọi service lưu đăng ký; nếu gói học không còn khả dụng, cần đưa người dùng trở lại bước chọn gói.

Nếu biểu diễn từng bước bằng một controller và một URL độc lập, ứng dụng vẫn phải giữ được các quy tắc như “chỉ xác nhận sau khi nhập dữ liệu hợp lệ” và “đừng tạo đăng ký mới chỉ vì người dùng bấm quay lại”. **Spring Web Flow** tổ chức những quy tắc đó thành một mô hình điều hướng có cấu trúc.

Bốn khái niệm giải quyết bốn câu hỏi khác nhau:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Flow** | Người dùng đang thực hiện quy trình nào? | Đăng ký khóa học |
| **State** | Hiện giờ quy trình đang ở bước nào? | Chọn gói học |
| **Event** | Điều gì vừa xảy ra khiến quy trình phải xử lý? | Người dùng nhấn `next` |
| **Transition** | Từ state hiện tại, sự kiện đó dẫn đến đâu? | `choosePlan --next--> review` |

Hãy nhớ quan hệ bao trùm: **flow chứa các state; một state có thể xử lý các event; transition nối state nguồn với state đích dựa trên event hoặc điều kiện đã định nghĩa**.

## 2. Bản đồ quan hệ của bốn khái niệm

~~~mermaid
flowchart TD
    F["Flow: courseEnrollment"] --> S1["State: profile"]
    F --> S2["State: choosePlan"]
    F --> S3["State: review"]
    F --> S4["State: save"]
    F --> S5["State: completed"]
    S1 -->|"event next / transition"| S2
    S2 -->|"event next / transition"| S3
    S2 -->|"event back / transition"| S1
    S3 -->|"event confirm / transition"| S4
    S4 -->|"event success / transition"| S5
~~~

Một **state** không tự quyết định mọi đích đến. Nó khai báo những **transition** mà flow cho phép. Một **event** cũng không mang sẵn ý nghĩa “đi đến màn hình tiếp theo”: event chỉ có ý nghĩa khi được xử lý trong ngữ cảnh state hiện tại.

Ví dụ, cùng event `next`:

- Ở `profile`, `next` có thể dẫn đến `choosePlan`.
- Ở `choosePlan`, `next` có thể dẫn đến `review`.
- Ở `review`, nếu không khai báo transition `next`, event đó không được phép tự động đưa người dùng đến `save`.

Ngược lại, nhiều event khác nhau có thể dẫn tới cùng một đích: `cancel` ở các view-state có thể dẫn tới `cancelled`. Vì thế **đích chuyển trạng thái được xác định từ cặp (state hiện tại, event) và các điều kiện liên quan**, không chỉ từ tên event.

## 3. Flow là đơn vị mô tả cả hành trình

**Flow definition** mô tả một quy trình gồm các state, transition, dữ liệu cần thiết và điểm kết thúc. Định nghĩa đó có thể được đăng ký để Web Flow tìm thấy theo một **flow ID** như `courseEnrollment`.

**Flow execution** là một lần thực thi cụ thể của định nghĩa: người A đang ở `profile`, người B đã đến `review`. Cả hai có thể dùng chung định nghĩa, nhưng trạng thái và dữ liệu của họ độc lập.

~~~mermaid
flowchart LR
    D["Flow definition: courseEnrollment"] --> E1["Execution A"]
    D --> E2["Execution B"]
    E1 --> A["Current state: profile"]
    E2 --> B["Current state: review"]
~~~

Định nghĩa flow không phải nơi chứa một biến `currentState` toàn cục cho mọi người dùng. **Flow execution** mới mang ngữ cảnh hiện tại của một lần chạy. Với ứng dụng web, execution có thể tiếp tục qua nhiều HTTP request bằng cơ chế quản lý trạng thái của Web Flow.

### 3.1. Một flow có điểm bắt đầu và các điểm kết thúc

Khi bắt đầu execution, framework chọn **start-state** (ngầm định hoặc được cấu hình) rồi thực thi cho tới khi gặp view-state cần chờ người dùng, hoặc khi flow kết thúc.

Một quy trình có thể có nhiều end-state, chẳng hạn:

- `completed`: đăng ký được xác nhận thành công.
- `cancelled`: người dùng chủ động hủy.
- `rejected`: quy trình bị từ chối theo một kết quả nghiệp vụ được mô hình hóa rõ ràng.

**End-state kết thúc flow execution**; nó không mặc định xóa bản ghi nghiệp vụ đã lưu, hoàn tác transaction hay hủy một booking đã được hệ thống bên ngoài chấp nhận.

### 3.2. Phạm vi của flow

Một flow cần quản lý cả **control state** (đang ở bước nào) và **data state** (người dùng đã nhập gì). Ví dụ, khi chuyển từ `profile` sang `choosePlan`, Web Flow cập nhật state hiện tại nhưng vẫn phải giữ tên và email đã nhập.

Dữ liệu dùng qua nhiều state thường phù hợp với `flowScope`; dữ liệu dành riêng một view có thể thuộc `viewScope`. Bài toán chọn scope liên quan tới vòng đời dữ liệu, còn flow/state/event/transition diễn tả việc điều khiển hành trình.

## 4. State là một bước có ý nghĩa trong flow

State biểu thị một trạng thái điều khiển mà flow đang ở hoặc đang thực hiện. Spring Web Flow có nhiều loại state với cách hoạt động khác nhau:

| Loại | Làm gì khi được kích hoạt? | Khi nào dừng/chuyển tiếp? |
| --- | --- | --- |
| **view-state** | Chuẩn bị và render view để tương tác với người dùng | Chờ event từ request sau; xử lý binding/validation theo cấu hình |
| **action-state** | Thực hiện một hoặc nhiều action phía server | Xử lý event/kết quả của action để chọn transition |
| **decision-state** | Đánh giá điều kiện để rẽ nhánh | Chuyển theo nhánh đúng/sai, không chờ một nút bấm |
| **subflow-state** | Gọi một flow con | Nhận kết quả khi flow con kết thúc rồi chuyển tiếp |
| **end-state** | Kết thúc flow đang thực thi | Không còn bước tiếp theo trong flow này |

Trong flow đăng ký khóa học:

- `profile`, `choosePlan`, `review` là **view-state**.
- `save` là **action-state**, nơi gọi service tạo đăng ký.
- `completed`, `cancelled` là **end-state**.

Điểm cần phân biệt: **không phải mọi state đều tương ứng với một màn hình**. `save` có thể chạy và chuyển tiếp hoàn toàn trên server mà người dùng không nhìn thấy một trang “save”.

### 4.1. View-state là điểm dừng để chờ request tiếp theo

Khi flow đến `choosePlan`, nó render giao diện, cung cấp ngữ cảnh tiếp tục execution và chờ event do người dùng gửi từ form. Request submit tiếp theo là một request HTTP mới. Web Flow khôi phục execution, xử lý event và transition hợp lệ.

~~~text
request A -> state profile -> render form, tạm dừng
request B -> event next -> transition -> state choosePlan -> render, tạm dừng
request C -> event next -> transition -> state review -> render, tạm dừng
request D -> event confirm -> transition -> action save -> end completed
~~~

Không cần giữ một HTTP request, thread hay transaction database mở trong suốt lúc người dùng đang suy nghĩ hoặc nhập form.

### 4.2. Action-state và decision-state có thể chuyển tiếp ngay

Ở **action-state**, một action gọi service có thể phát sinh kết quả `success`, `error` hoặc tên event khác theo cách action được cấu hình. Flow dùng kết quả đó để đi tiếp. Lỗi exception không được xử lý **không tự động** biến thành event `error`.

Ở **decision-state**, flow trực tiếp kiểm tra một biểu thức điều kiện; framework chọn nhánh và chuyển state mà không cần một request từ người dùng để “bấm next”.

Điều đó giải thích vì sao một request có thể đi qua nhiều state nội bộ trước khi trả response.

## 5. Event là tín hiệu, không phải đích đến

**Event** mô tả một việc vừa xảy ra trong ngữ cảnh flow, thường gồm một **event ID** và có thể kèm thông tin bổ sung. Nguồn phát event thường gặp:

1. **Người dùng:** nhấn nút `next`, `back`, `cancel` hoặc `confirm` trên form.
2. **Action phía server:** service/adaptor cho ra kết quả được ánh xạ thành event `success`, `unavailable`...
3. **Subflow:** flow con kết thúc bằng một outcome để flow cha tiếp tục.

Với form Web Flow, người dùng có thể gửi tên event thông qua tham số:

~~~http
POST /courseEnrollment?execution=e1s2 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId=next&planCode=STANDARD
~~~

`execution=e1s2` chỉ là khóa minh họa do Web Flow cấp để định vị execution. `_eventId=next` là event của tương tác. Một cách gửi event khác thường gặp là tên nút form `_eventId_next`.

**Phân biệt dữ liệu và event:** `planCode=STANDARD` là dữ liệu form; `next` là tín hiệu yêu cầu xử lý. Event không tự thay đổi model. Việc binding/validation và hành động của transition mới quyết định dữ liệu nào được cập nhật và có chuyển bước hay không.

### 5.1. Event có hợp lệ không phụ thuộc state hiện tại

Giả sử state `review` chỉ định nghĩa `edit`, `confirm` và `cancel`. Nếu client tự tạo request gửi `next`, flow không nên suy diễn rằng đó là `confirm`.

Không có transition phù hợp thì framework sẽ xử lý theo cơ chế lỗi/sự kiện chưa được xử lý và cấu hình liên quan; hành vi chi tiết tùy phiên bản. Thiết kế ứng dụng cần xử lý phù hợp và không để request lạ kích hoạt nghiệp vụ nhạy cảm.

Tên event `confirm` do client gửi **không phải bằng chứng người dùng có quyền xác nhận**. Action ghi dữ liệu vẫn phải xác thực, phân quyền, kiểm tra lại điều kiện nghiệp vụ và chống submit lặp.

## 6. Transition là quy tắc chuyển từ state này sang state khác

Một **transition** liên kết nguồn (state đang hoạt động), trigger (event/điều kiện tương ứng) và target (state đích). Trong XML Web Flow, mẫu đơn giản thường là:

~~~xml
<transition on="next" to="choosePlan"/>
~~~

Khi thẻ này nằm trong `view-state id="profile"`, nó có nghĩa:

> Nếu flow đang ở `profile` và xử lý event `next` thành công theo các điều kiện liên quan, chuyển sang `choosePlan`.

Nó **không** có nghĩa mọi event `next` trong toàn bộ flow đều đi đến `choosePlan`.

### 6.1. Một nguồn có thể có nhiều transition

~~~xml
<view-state id="choosePlan" view="enrollment/choose-plan" model="draft">
    <transition on="back" to="profile" bind="false"/>
    <transition on="next" to="review"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

Trong state này, mỗi event chọn một nhánh:

| State nguồn | Event | Transition được chọn | State đích |
| --- | --- | --- | --- |
| choosePlan | back | `on="back"` | profile |
| choosePlan | next | `on="next"` | review |
| choosePlan | cancel | `on="cancel"` | cancelled |
| choosePlan | confirm | Không khai báo | Không có đường đi confirm hợp lệ tại state này |

`bind="false"` thường được dùng cho thao tác chỉ điều hướng, như back/cancel, để tránh binding dữ liệu form không cần thiết trước khi rời state. Điều này có nghĩa **giá trị chưa submit của form hiện tại có thể không được lưu** khi người dùng nhấn back; đó là lựa chọn cần thống nhất với yêu cầu trải nghiệm.

### 6.2. Transition có thể có hành động bổ sung

Trong Web Flow, transition có thể chứa các hành động được thực thi trong lúc chuyển trạng thái:

~~~xml
<transition on="next" to="review">
    <evaluate expression="enrollmentService.prepareSummary(draft)"/>
</transition>
~~~

Ví dụ minh họa việc chuẩn bị dữ liệu tóm tắt ở thời điểm điều hướng. Nếu hành động chứa logic nghiệp vụ lớn, nhiều nhánh outcome hoặc xử lý lỗi, nên tách thành action-state/service rõ ràng để dễ đọc và kiểm thử.

**Transition chỉ mô tả cách điều hướng; không bảo đảm một thao tác ghi đã thành công.** Nếu action có thể thất bại, thiết kế phải phân biệt outcome nghiệp vụ và exception, thay vì giả định một transition là transaction.

## 7. Ví dụ XML: cả bốn khái niệm làm việc cùng nhau

Đoạn XML sau là **ví dụ tập trung vào điều hướng** cho flow `courseEnrollment`. Giả định ứng dụng đã có `EnrollmentDraft`, `enrollmentService`, các view template và cấu hình tích hợp Spring MVC phù hợp. Một ứng dụng chạy thực tế còn cần validation, CSRF, xử lý lỗi, transaction và security đầy đủ.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <!-- Model có vòng đời theo một flow execution. -->
    <var name="draft" class="com.example.enrollment.EnrollmentDraft"/>

    <!-- State đầu tiên: người dùng nhập thông tin. -->
    <view-state id="profile" view="enrollment/profile" model="draft">
        <binder>
            <binding property="fullName" required="true"/>
            <binding property="email" required="true"/>
        </binder>
        <transition on="next" to="choosePlan"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <!-- Cùng event next, nhưng target khác state profile. -->
    <view-state id="choosePlan" view="enrollment/choose-plan" model="draft">
        <binder>
            <binding property="planCode" required="true"/>
        </binder>
        <transition on="back" to="profile" bind="false"/>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="enrollment/review">
        <transition on="edit" to="profile" bind="false"/>
        <transition on="confirm" to="save" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <!-- Chạy phía server, không cần một màn hình nhập liệu. -->
    <action-state id="save">
        <evaluate expression="enrollmentService.save(draft)"/>
        <transition on="success" to="completed"/>
    </action-state>

    <end-state id="completed" view="enrollment/completed"/>
    <end-state id="cancelled" view="enrollment/cancelled"/>
</flow>
~~~

### 7.1. Cách đọc quan hệ trong ví dụ

**Flow:** tập hợp toàn bộ state từ `profile` đến `completed`/`cancelled`.

**State:** `profile`, `choosePlan`, `review`, `save`, `completed`, `cancelled`.

**Event:** `next`, `back`, `cancel`, `edit`, `confirm`, `success`. Chúng có thể đến từ form hoặc kết quả action.

**Transition:** những dòng `<transition on="..." to="..."/>` nối các state. Một event được diễn giải trong đúng state có transition tương ứng.

Trong action-state `save`, ví dụ giả định lời gọi `evaluate` kết thúc bình thường và tạo outcome `success`. Để có các nhánh nghiệp vụ như `planUnavailable` hoặc `paymentRejected`, cần khai báo/cấu hình action trả outcome phù hợp rồi tạo transition tương ứng. **Một exception không được xử lý không tự tạo event `error`.**

### 7.2. Vì sao phải tách `review` và `save`?

`review` là một view-state chờ người dùng xác nhận. `save` là action-state gọi service ghi dữ liệu. Nếu gắn thao tác ghi vào việc render view `review`, việc tải lại trang hoặc quay lại rất dễ gây tác dụng phụ không mong muốn.

Tách hai state giúp test:

- `review + edit` chỉ điều hướng về profile.
- `review + cancel` kết thúc mà không gọi thao tác lưu.
- `review + confirm` mới chuyển tới save.
- `save + success` mới hoàn thành flow.

Tuy nhiên, action-state **không tự ngăn gửi trùng request**. Service vẫn cần bảo vệ bằng request ID ổn định, kiểm tra unique/transaction và idempotency phù hợp.

## 8. Diễn tiến thực tế: current state + event = chọn transition

Với dữ liệu hợp lệ và service lưu thành công, một execution có thể đi theo các bước:

| Lượt | State trước khi nhận event | Event | State sau khi xử lý | Dữ liệu cần giữ |
| --- | --- | --- | --- | --- |
| 0 | Chưa bắt đầu | start | profile | Tạo bản nháp `draft` |
| 1 | profile | next | choosePlan | `fullName`, `email` |
| 2 | choosePlan | next | review | Thêm `planCode` |
| 3 | review | edit | profile | Giữ bản nháp để sửa |
| 4 | profile | next | choosePlan | Cập nhật thông tin đã sửa |
| 5 | choosePlan | next | review | Giữ lựa chọn mới nhất |
| 6 | review | confirm | save → completed | Service lưu kết quả |

Ở lượt 6, Web Flow có thể đi qua `save` rồi `completed` trong **cùng một request**. Lượt đó không đòi hỏi trình duyệt gửi riêng request `success`: kết quả `success` phát sinh từ action phía server.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant Browser as Trình duyệt
    participant Flow as FlowExecutor
    participant Service as EnrollmentService
    U->>Browser: Nhấn Confirm tại review
    Browser->>Flow: POST event=confirm, execution key
    Flow->>Flow: current=review; tìm transition confirm
    Flow->>Flow: chuyển sang action-state save
    Flow->>Service: save(draft)
    Service-->>Flow: hoàn tất thành công
    Flow->>Flow: nhận outcome success; chuyển completed
    Flow-->>Browser: phản hồi kết thúc flow
    Browser-->>U: Thấy trang kết quả
~~~

Sơ đồ diễn tả thứ tự logic. Trong ứng dụng thật, Web Flow có thể sử dụng redirect khi render view hoặc điều hướng theo cấu hình.

### 8.1. Nếu event được gửi ở state sai

Một request `confirm` gửi khi state vẫn là `profile` không có nghĩa flow được bỏ qua hai bước. Nó không khớp transition được khai báo ở `profile`. Đây là một lý do điều hướng phải phụ thuộc **state hiện tại** chứ không dựa vào URL hoặc tên nút đơn thuần.

### 8.2. Nếu validation thất bại

Giả sử người dùng ở `profile` gửi `next` nhưng email không hợp lệ. Khi validation được cấu hình đúng, việc chuyển sang `choosePlan` bị chặn, view hiện tại tiếp tục hiển thị thông báo lỗi cho người dùng sửa.

Do đó công thức “state + event → target” cần hiểu đầy đủ hơn:

~~~text
State hiện tại
    + Event được phát
    + Binding / validation / điều kiện / action liên quan
    = Transition được chấp nhận và state đích (hoặc tiếp tục ở state hiện tại)
~~~

**Event cho biết ý định; validation và điều kiện nghiệp vụ quyết định có được tiến bước hay không.**

## 9. Sự khác nhau giữa event người dùng và event nội bộ

Các event đều tham gia điều hướng nhưng khác nguồn và độ tin cậy:

| Tiêu chí | Event từ form | Outcome từ action | Kết quả từ subflow |
| --- | --- | --- | --- |
| Nguồn | HTTP request của trình duyệt | Java action/service hoặc adapter | Flow con kết thúc |
| Ví dụ | `next`, `back`, `confirm` | `success`, `unavailable` | `verified`, `cancelled` |
| Gắn với state nào? | View-state hiện tại | Action-state/transition đang thực thi | Subflow-state ở flow cha |
| Lưu ý | Client có thể gửi event tùy ý | Phải mô hình hóa outcome và exception | Cần hợp đồng input/output rõ ràng |

Không nên đặt tên event theo số thứ tự màn hình như `goPage3` nếu có thể dùng tên **ý định nghiệp vụ** như `confirm`, `changePlan`, `cancel`. Tên có nghĩa giúp bản đồ flow dễ đọc và giảm lệ thuộc vào cách thiết kế giao diện.

## 10. Decision-state: chuyển trạng thái nhờ điều kiện

Khi hướng đi phụ thuộc vào một điều kiện phía server, có thể khai báo `decision-state`:

~~~xml
<decision-state id="checkEligibility">
    <if test="enrollmentService.isEligible(draft)"
        then="review"
        else="notEligible"/>
</decision-state>
~~~

Nếu người dùng vừa hoàn thành `choosePlan` và flow chuyển tới `checkEligibility`, Web Flow đánh giá điều kiện rồi đi tiếp tới một trong hai state. Nó không cần chờ người dùng nhấn thêm nút.

Ở đây **`if` là nhánh dựa trên kết quả điều kiện**, còn transition `on="next"` là nhánh được kích hoạt bằng event. Cả hai đều là những cách điều khiển chuyển state, nhưng không nên lẫn lộn “người dùng phát event” và “máy chủ tính điều kiện”.

Kiểm tra `isEligible` lúc điều hướng giúp trải nghiệm tốt hơn, nhưng **không thay thế kiểm tra cuối ở service ngay trước commit**: điều kiện như chỗ trống hoặc giá có thể thay đổi sau khi hiển thị review.

## 11. Subflow-state: khi một state gọi cả một flow khác

Một flow đăng ký có thể phải xác minh email hoặc số điện thoại. Nếu tác vụ xác minh được dùng ở nhiều nơi, nên cân nhắc tách thành **subflow**.

~~~xml
<subflow-state id="verifyContact" subflow="verifyContact">
    <input name="email" value="draft.email"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="profile"/>
</subflow-state>
~~~

Hình dung luồng cha ở `verifyContact` gọi flow con:

~~~mermaid
flowchart TD
    P["Flow cha: choosePlan"] --> VF["subflow-state: verifyContact"]
    VF --> A["Flow con: sendCode"]
    A --> B["Flow con: enterCode"]
    B -->|"mã hợp lệ"| V["Flow con: end verified"]
    B -->|"hủy"| C["Flow con: end cancelled"]
    V -->|"outcome verified"| R["Flow cha: review"]
    C -->|"outcome cancelled"| O["Flow cha: profile"]
~~~

**Flow con** có các state và event riêng của nó. Khi kết thúc ở `verified` hoặc `cancelled`, kết quả được dùng để chọn transition trong **subflow-state của flow cha**. Nếu cần trả dữ liệu, nên khai báo output của flow con và mapping tương ứng thay vì để flow cha/con tùy ý sửa dữ liệu chung.

Subflow giúp tái sử dụng một hành trình có đầu vào và đầu ra rõ ràng. Không cần tách subflow cho từng màn hình nếu điều đó khiến mô hình phức tạp hơn.

## 12. Binding, validation và scope liên hệ thế nào với bốn khái niệm?

**Flow/state/event/transition** điều khiển **đường đi**. **Binding/validation/scope** quyết định **dữ liệu nào được nhận, có đủ điều kiện đi tiếp không và tồn tại bao lâu**.

Một ví dụ:

~~~xml
<view-state id="profile" view="enrollment/profile" model="draft">
    <binder>
        <binding property="fullName" required="true"/>
        <binding property="email" required="true"/>
    </binder>
    <transition on="next" to="choosePlan"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

Khi form ở `profile` gửi event `next`, Web Flow có thể bind `fullName` và `email` vào `draft`, kiểm tra dữ liệu theo cấu hình rồi mới rời state. Nếu dữ liệu sai, flow thường giữ view-state và trả lỗi để sửa.

Khi form gửi `cancel`, transition có `bind="false"` giúp tránh xử lý dữ liệu form không cần thiết. Một số thao tác chuyển bước có thể cần bỏ validation nhưng vẫn bind dữ liệu; phải lựa chọn theo yêu cầu cụ thể thay vì dùng `bind="false"` cho mọi nút quay lại.

### 12.1. Scope của dữ liệu

| Scope | Mục đích | Ví dụ |
| --- | --- | --- |
| `requestScope` | Dữ liệu ngắn hạn trong một lần xử lý request | Kết quả tra cứu tạm |
| `flashScope` | Thông điệp tạm cho một chu kỳ điều hướng/render thích hợp | Cảnh báo cập nhật |
| `viewScope` | Dữ liệu cho view-state đang hoạt động | Danh sách lựa chọn chỉ dùng tại màn hình chọn gói |
| `flowScope` | Dữ liệu giữ qua các state của một execution | `draft` đăng ký |
| `conversationScope` | Ngữ cảnh chia sẻ qua conversation có flow/subflow | Dữ liệu chung giữa flow cha/con khi cần |

Không nên dùng một thuộc tính HTTP session chung tên `draft` cho tất cả flow execution: hai tab có thể gây ghi đè dữ liệu. Dữ liệu nghiệp vụ cần sống qua nhiều ngày phải được lưu bền vững bằng service/database chứ không phụ thuộc một flow execution chưa kết thúc.

### 12.2. Transition không thay thế kiểm tra ở service

State `save` có thể chỉ được chạm đến qua event `confirm`, nhưng service vẫn phải:

1. Xác thực và kiểm tra quyền đối với dữ liệu.
2. Validate lại toàn bộ bản nháp và điều kiện nghiệp vụ mới nhất.
3. Thực hiện transaction phù hợp.
4. Chống tạo bản ghi trùng nếu request bị retry.

Một client có thể giả mạo event; một quy trình hợp lệ trước đó cũng có thể trở nên lỗi thời khi tài nguyên thay đổi. **Bản đồ flow tổ chức điều hướng, còn service bảo vệ bất biến nghiệp vụ.**

## 13. Những điều dễ nhầm khi vẽ flow

**Nhầm state với URL.** Một flow có thể đi qua nhiều view-state bằng cùng một endpoint flow và dùng execution key để tiếp tục. URL không phải tên state và không quyết định thay cho transition.

**Nhầm event với transition.** `next` chỉ là tín hiệu. `<transition on="next" to="review"/>` mới là quy tắc điều hướng cụ thể tại state chứa nó.

**Nhầm event với dữ liệu form.** `confirm` là ý định; `planCode` là dữ liệu. Cả hai xuất hiện trong request nhưng được xử lý khác nhau.

**Nhầm action-state với view-state.** Action-state chạy server logic và có thể chuyển tiếp ngay; nó không mặc nhiên render một trang.

**Nhầm lỗi exception với outcome nghiệp vụ.** Service ném exception không tự động đồng nghĩa event `error`. Cần lựa chọn chiến lược chuyển lỗi nghiệp vụ thành kết quả, xử lý exception và phản hồi phù hợp.

**Cho rằng event back luôn giữ dữ liệu chưa submit.** Nếu dùng `bind="false"`, giá trị người dùng vừa gõ vào form nhưng chưa được lưu trong model có thể bị bỏ. Cần thống nhất hành vi với yêu cầu sản phẩm.

**Dùng end-state như rollback.** Kết thúc bằng `cancelled` không tự đảo ngược transaction đã commit hoặc gọi hoàn tác ở hệ thống bên ngoài.

**Dựa vào transition để chống submit trùng.** Một event được xử lý hợp lệ vẫn có thể bị gửi lại do retry mạng. Service phải bảo đảm idempotency và ràng buộc dữ liệu.

## 14. Cách thiết kế flow trước khi viết XML

Khi nhận yêu cầu “đăng ký khóa học nhiều bước”, có thể triển khai việc mô hình hóa theo thứ tự:

1. **Xác định một flow chính.** Đặt tên diễn đạt quy trình nghiệp vụ, ví dụ `courseEnrollment`.
2. **Liệt kê các state.** Phân biệt màn hình người dùng (`profile`, `choosePlan`, `review`), action phía server (`save`) và kết thúc (`completed`, `cancelled`).
3. **Liệt kê event cho từng state.** Ví dụ, `profile` có `next`, `cancel`; `review` có `edit`, `confirm`, `cancel`.
4. **Vẽ transition cho mọi event hợp lệ.** Đặc biệt là back, cancel và trường hợp lỗi.
5. **Định nghĩa dữ liệu và scope.** Chọn nơi giữ bản nháp, field được bind, validation mỗi bước và validation cuối.
6. **Đánh dấu các bước nghiệp vụ.** Gọi service nào khi xác nhận, xử lý kết quả thất bại, transaction, idempotency và phân quyền.
7. **Xác định cách phục hồi.** Hành vi khi validation sai, execution hết hạn, tab cũ, submit lặp.
8. **Chuyển sơ đồ thành XML và viết test.** Mỗi đường đi quan trọng phải có một kịch bản kiểm thử.

Một sơ đồ có giá trị khi chỉ nhìn vào đó đã biết state nào phát sinh side effect, state nào chờ người dùng và event nào hợp lệ tại từng điểm.

## 15. Kiểm thử quan hệ state – event – transition

Một cách hiệu quả là tạo **bảng chuyển trạng thái** trước khi viết test:

| State ban đầu | Event/điều kiện | State/kết quả mong đợi |
| --- | --- | --- |
| Bắt đầu flow | start | profile |
| profile | next + dữ liệu hợp lệ | choosePlan |
| profile | next + email sai | Giữ profile, hiển thị lỗi |
| profile | cancel | cancelled |
| choosePlan | back | profile |
| choosePlan | next + planCode hợp lệ | review |
| choosePlan | confirm | Không được kích hoạt save |
| review | edit | profile |
| review | cancel | cancelled |
| review | confirm | save rồi completed khi thành công |
| save | Kết quả nghiệp vụ thất bại đã mô hình hóa | State xử lý lỗi được khai báo |
| completed | Gửi lại confirm cũ | Không tạo đăng ký thứ hai |

Pseudocode về một bài test flow:

~~~text
execution = startFlow("courseEnrollment")
assertCurrentState(execution, "profile")

execution = sendEvent(execution, "next", {
    fullName: "Nguyen An",
    email: "an@example.com"
})
assertCurrentState(execution, "choosePlan")

execution = sendEvent(execution, "back")
assertCurrentState(execution, "profile")
assertFlowValue(execution, "draft.email", "an@example.com")
~~~

Đoạn trên là **mã giả diễn tả kịch bản**, không phải API test có thể chạy nguyên văn. Khi triển khai cần dùng các công cụ kiểm thử phù hợp phiên bản Web Flow và kiểm tra thêm Spring MVC request binding, validator, exception, session, timeout, concurrency và idempotency của service.

### 15.1. Test đường đi khác với test nghiệp vụ

Một test xác nhận `review + confirm → save` chứng minh flow chọn đúng transition. Nó **chưa** chứng minh database chỉ ghi một bản ghi khi có hai request đồng thời. Cần test nghiệp vụ và transaction ở service/repository cho các bất biến đó.

### 15.2. Chẩn đoán khi một event không đi đến state mong đợi

Hãy kiểm tra theo thứ tự:

1. Flow execution hiện tại có phải lần chạy người dùng muốn tiếp tục không?
2. State hiện tại là gì và event được gửi có đúng tên không?
3. State đó có transition phù hợp không?
4. Binding hoặc validation có chặn việc rời state không?
5. Action/decision có trả outcome hay nhánh điều kiện như dự kiến không?
6. Service có ném exception hoặc trạng thái phiên đã hết hạn không?

Làm rõ sáu câu hỏi sẽ định vị được phần sai trong **flow**, **state**, **event** hay **transition**, thay vì sửa controller theo phỏng đoán.

## 16. Bài thực hành: tự vẽ một flow đặt lịch tư vấn

Hãy mô hình hóa quy trình **đặt lịch tư vấn** gồm: chọn ngày giờ, nhập thông tin liên hệ, xác minh số điện thoại, xem lại lịch và xác nhận.

Yêu cầu:

1. Đặt tên flow chính và vẽ ít nhất bốn view-state, một action-state, hai end-state.
2. Gắn event `next`, `back`, `cancel`, `confirm` vào đúng state, không dùng event để chỉ trực tiếp số thứ tự trang.
3. Tách bước xác minh thành một subflow có hai kết quả `verified` và `cancelled`. Nêu state đích của flow cha cho từng kết quả.
4. Xác định dữ liệu nào ở `flowScope`, dữ liệu nào chỉ cần `viewScope`.
5. Vẽ nhánh khi giờ đã chọn không còn trống lúc xác nhận; giải thích vì sao vẫn phải kiểm tra điều kiện trong transaction của service.
6. Viết bảng test cho ba tình huống: event confirm gửi sai state, validation lỗi ở trang liên hệ và người dùng submit confirm hai lần.

**Gợi ý tự kiểm tra:** Nếu bỏ một event ở một state, bạn có biết rõ điều gì sẽ xảy ra? Nếu người dùng nhấn Back nhưng giữ nguyên bản nháp, bạn có giải thích được vì sao dữ liệu vẫn còn? Nếu service thất bại, bạn có đường đi có thể test và có thông điệp phù hợp?

## 17. Tổng kết

**Flow** là toàn bộ hành trình; **state** là vị trí/bước của hành trình; **event** là tín hiệu phát sinh trong ngữ cảnh hiện tại; **transition** là quy tắc đưa flow từ state nguồn sang state đích khi tín hiệu và điều kiện cho phép. Một flow definition có thể được thực thi nhiều lần; mỗi flow execution giữ state và dữ liệu của một hành trình riêng.

Web Flow sử dụng những thành phần này để phối hợp các view-state, action-state, decision-state, subflow-state và end-state qua nhiều HTTP request. Binding, validation và scope giúp xử lý dữ liệu ở từng bước; Spring MVC tích hợp việc nhận request và render view; service đảm nhận phân quyền, transaction, tính hợp lệ cuối và chống ghi trùng.

**Câu hỏi ôn tập**

1. Tại sao cùng event `next` ở hai state khác nhau có thể dẫn tới hai đích khác nhau?
2. Phân biệt flow definition và flow execution bằng một tình huống hai người dùng đăng ký.
3. Nếu request gửi event `confirm` từ state `profile`, flow phải dựa vào thành phần nào để không đi thẳng tới save?
4. Event `success` từ action-state khác gì event `next` từ một form?
5. Khi một flow con kết thúc, kết quả đó được dùng ở state nào của flow cha?
6. Validation lỗi và không tìm thấy transition giống hay khác nhau ở điểm nào?
7. Vì sao một transition đúng chưa bảo đảm thao tác lưu dữ liệu an toàn khi bị retry?
