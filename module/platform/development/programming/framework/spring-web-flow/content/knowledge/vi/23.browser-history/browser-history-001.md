# Nút Back, Forward và việc tiếp tục từ snapshot cũ

> **Chương:** Lịch sử trình duyệt  
> **Bối cảnh:** Spring Web Flow (SWF) điều phối các hành trình web nhiều bước bằng state, event, transition, subflow và flow execution. Bài học giải thích chuyện gì xảy ra khi người dùng dùng lịch sử trình duyệt để quay về một màn hình cũ rồi tiếp tục thao tác.

## 1. Tình huống: người dùng quay lại nhưng máy chủ đã đi tiếp

Một quy trình đặt vé gồm ba trang:

1. **passenger**: nhập thông tin hành khách.
2. **seat**: chọn chỗ.
3. **review**: xem lại thông tin và nhấn xác nhận.

Người dùng đã tới `review`, sau đó nhấn **Back** trên trình duyệt để quay lại `seat`. Trang chọn chỗ xuất hiện như trước. Câu hỏi là: **flow trên máy chủ hiện vẫn ở review, hay đã trở lại seat?**

Không thể trả lời chỉ bằng việc quan sát trang trình duyệt. Back có thể hiển thị một trang đã lưu trong lịch sử hoặc bộ nhớ đệm của trình duyệt. Để xử lý một request mới, Spring Web Flow còn cần biết **flow execution** và **snapshot/continuation** mà request đang tham chiếu, nếu cơ chế lưu execution cho phép khôi phục snapshot đó.

Đây là điểm dễ gây lỗi: người dùng tưởng mình đã quay về một bước, nhưng request sau đó có thể dùng một ngữ cảnh cũ, đã hết hạn, hoặc không còn phù hợp với dữ liệu nghiệp vụ hiện tại.

## 2. Ba loại lịch sử cần phân biệt

| Thành phần | Ai quản lý? | Chứa gì? | Có tự hoàn tác nghiệp vụ không? |
| --- | --- | --- | --- |
| **Browser history** | Trình duyệt | Các mục lịch sử điều hướng, URL và trạng thái trang có thể được cache | Không |
| **Flow execution** | Spring Web Flow | State hiện tại, dữ liệu theo scope, ngữ cảnh điều hướng của một lần chạy | Không |
| **Execution snapshot/continuation** | Cơ chế repository của Web Flow, tùy cấu hình | Một trạng thái execution được lưu tại một thời điểm để có thể tiếp tục | Không |

Một **flow definition** có thể dùng cho nhiều execution. Mỗi execution lại có thể có nhiều snapshot nếu repository hỗ trợ và còn giữ chúng. Còn lịch sử của trình duyệt là lịch sử **các lần điều hướng HTTP**, không phải nhật ký transaction database.

Giả sử:

~~~text
Tab đang mở:
  Trang passenger  ->  Trang seat  ->  Trang review
                      [Back]          [Hiện tại]

Trong Web Flow:
  Execution E, snapshot S1: passenger
  Execution E, snapshot S2: seat
  Execution E, snapshot S3: review
~~~

Sơ đồ này minh họa một repository giữ được nhiều snapshot. Không phải mọi cấu hình đều giữ S1, S2 và S3. Một số execution key cũ có thể không còn khôi phục được.

**Kết luận nền tảng:** Back/Forward của trình duyệt thay đổi lịch sử và tài liệu đang hiển thị. Chúng **không tự gửi event** `back` hoặc `forward` vào Spring Web Flow.

## 3. Cách một request tiếp tục flow execution

Ứng dụng Spring MVC tích hợp Spring Web Flow thường định tuyến request của flow thông qua **FlowHandlerMapping**, **FlowHandlerAdapter** và **FlowExecutor**. Executor tạo hoặc khôi phục execution rồi xử lý event tương ứng với state hiện tại.

Ví dụ, request từ form ở trang chọn chỗ có thể có dạng:

~~~http
POST /booking?execution=e1s2 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId=next&seatCode=12A
~~~

Trong ví dụ:

- `/booking` là endpoint của flow.
- `execution=e1s2` là **khóa minh họa** để Web Flow định vị execution/snapshot, không phải ID do ứng dụng tự tạo.
- `_eventId=next` báo sự kiện mà người dùng đã phát ra.
- `seatCode=12A` là dữ liệu form cần binding, validation trước khi được chấp nhận.

Ký hiệu thường thấy như `e1s2` cho phép hình dung conversation/execution và snapshot, nhưng **không nên phân tích chuỗi khóa để tự suy diễn thứ tự bước**. Giá trị thực tế, nơi đặt khóa trong URL/form và việc snapshot có thay đổi ở mỗi request đều phụ thuộc Web Flow và cấu hình.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant M as Spring MVC
    participant E as FlowExecutor
    participant R as Execution Repository
    U->>B: Nhấn Next ở trang seat
    B->>M: POST execution key + event + seatCode
    M->>E: Tiếp tục flow booking
    E->>R: Tra cứu/khôi phục execution
    R-->>E: State seat và dữ liệu đã lưu
    E->>E: Binding, validation, transition next
    E->>R: Lưu state/snapshot theo cấu hình
    E-->>M: View/redirect cho review
    M-->>B: HTTP response
    B-->>U: Trang review
~~~

Khi xử lý request, Web Flow phải đánh giá event **trong state được khôi phục**, không được tin rằng tên trang đang mở trên trình duyệt luôn phản ánh state mới nhất trên server.

## 4. Back/Forward khác với nút Back/Next trong flow

Hai nút có chữ “Back” có thể mang ý nghĩa hoàn toàn khác nhau.

### 4.1. Back của trình duyệt

Nút Back trên thanh công cụ của trình duyệt đi đến **mục lịch sử trước đó**. Hành vi phụ thuộc loại navigation, HTTP cache, Back/Forward Cache (bfcache), redirect và các đặc điểm của trình duyệt:

- Trình duyệt có thể hiển thị ngay một trang được lưu trong bfcache.
- Trình duyệt có thể phát GET để tải lại trang.
- Trình duyệt có thể cảnh báo khi phải gửi lại POST.
- Một trang cũ có thể giữ **URL chứa execution key cũ** hoặc form với action/hidden field từ lần render trước.

Chỉ khi có request mới gửi tới server, Web Flow mới có cơ hội khôi phục execution và xử lý event. Việc trang cũ được hiện ra trên màn hình **chưa đủ** để xác nhận trạng thái flow đã thay đổi.

### 4.2. Nút Back của ứng dụng

Nút Back do flow định nghĩa thường gửi event rõ ràng, ví dụ `back`:

~~~xml
<view-state id="seat" view="booking/seat" model="booking">
    <transition on="back" to="passenger" bind="false"/>
    <transition on="next" to="review"/>
</view-state>
~~~

Khi flow đang ở `seat` và nhận event `back` hợp lệ, transition đi đến `passenger`. Nút này hoạt động theo **bản đồ state** của ứng dụng, kể cả khi lịch sử trình duyệt có nhiều trang không liên quan.

Một form minh họa cách phát sự kiện:

~~~html
<!-- action và execution key thật phải được render từ ngữ cảnh Web Flow hiện tại. -->
<form method="post" action="/booking?execution=EXECUTION_KEY_HIEN_TAI">
  <button type="submit" name="_eventId_back">Quay lại bước trước</button>
  <button type="submit" name="_eventId_next">Tiếp tục</button>
</form>
~~~

Ví dụ dùng placeholder để biểu diễn ý tưởng, **không phải template hoàn chỉnh**. Trong sản phẩm thật, dùng URL hiện thời do Web Flow cung cấp và CSRF token theo Spring Security.

| Hành động | Điều gì quyết định trang tiếp theo? | Có chắc cập nhật flow execution không? |
| --- | --- | --- |
| Trình duyệt Back | Lịch sử điều hướng của trình duyệt | Không; còn tùy việc có request tới server hay không |
| Trình duyệt Forward | Mục lịch sử kế tiếp | Không; cùng giới hạn như Back |
| Nút Back trong flow | Transition `on="back"` của state hiện hành | Có, khi request và execution hợp lệ |
| Nút Next trong flow | Transition `on="next"`, binding/validation và điều kiện | Có nếu transition được chấp nhận |

Đừng gắn `window.history.back()` với ý nghĩa nghiệp vụ “đi về state trước”. Đó chỉ là thao tác lịch sử trình duyệt.

## 5. Snapshot là gì và khi nào một snapshot cũ còn dùng được?

Một snapshot hay continuation biểu diễn trạng thái của **một flow execution tại một thời điểm**: state đang hoạt động, dữ liệu scope và ngữ cảnh cần thiết để tiếp tục. Nếu repository còn giữ snapshot đó, một request tham chiếu đến khóa cũ có thể khôi phục chính trạng thái ấy.

Ví dụ về diễn tiến:

~~~mermaid
flowchart LR
    A["S1: passenger"] -->|"next"| B["S2: seat"]
    B -->|"next"| C["S3: review"]
    C -.->|"Browser Back: hiện lại trang seat"| V["Trang seat cũ"]
    V -.->|"submit với key S2"| R{"Repository còn S2?"}
    R -->|"Có"| Y["Khôi phục S2 rồi xử lý event"]
    R -->|"Không"| N["Không thể tiếp tục từ S2"]
~~~

Đây là **hai khả năng**, không phải một hành vi duy nhất trong mọi ứng dụng.

Nếu snapshot S2 còn hợp lệ, request có thể tiếp tục từ state `seat` ở thời điểm S2. Nếu snapshot đã bị loại bỏ, execution kết thúc, session hết hạn hoặc khóa không hợp lệ, Web Flow có thể báo lỗi không tìm thấy/không thể tiếp tục execution. Tên exception, cách render trang lỗi và chính sách phục hồi phụ thuộc phiên bản và cấu hình.

### 5.1. Snapshot không phải bản sao thời gian của database

Giả sử S2 chứa `seatCode=12A`, nhưng người khác đã đặt chỗ 12A trước khi người dùng nhấn Next từ trang cũ. Khôi phục S2 **không khôi phục ghế 12A về trạng thái còn trống** trong database.

Một service đặt vé phải kiểm tra lại tồn kho/chỗ ngồi ngay lúc ghi dữ liệu. Nếu thao tác cuối đã được commit từ một request trước, việc khôi phục S2 cũng **không rollback** tác vụ đó.

**Snapshot giữ trạng thái của flow, không phải transaction lịch sử của hệ thống.**

### 5.2. Snapshot cũ có thể tạo nhánh mới

Một người có thể:

1. Chọn ghế 12A → đến review với snapshot S3.
2. Back về trang chọn ghế mang khóa S2.
3. Chọn ghế 12B → submit và tạo snapshot khác, ví dụ S4.

S3 và S4 có thể đại diện cho hai nhánh từ một mốc cũ nếu cơ chế repository cho phép. Lịch sử trình duyệt có thể còn trang review hiển thị 12A; trang này **không nên được xem là nguồn sự thật** cho lựa chọn hiện thời.

Không nên giả định “snapshot có số lớn hơn là đúng” hoặc “chỉ snapshot mới nhất được chấp nhận”. Cần dựa vào contract của repository đã cấu hình và các quy tắc nhất quán ở tầng nghiệp vụ.

## 6. Hiểu đúng tình huống Back rồi Forward

Giả sử trình duyệt có lịch sử:

~~~text
[Passenger K1] -> [Seat K2] -> [Review K3]
                                     ^
                                    hiện tại
~~~

Người dùng nhấn Back để xem Seat K2, rồi Forward để trở lại Review K3:

~~~text
Back:     [Passenger K1] -> [Seat K2] <- [Review K3]
                                  ^
                                 đang xem

Forward:  [Passenger K1] -> [Seat K2] -> [Review K3]
                                               ^
                                              đang xem
~~~

Nếu hai trang được trả từ cache, **có thể chưa xảy ra request nào đến server**. Nếu trình duyệt tải lại, request có thể mang K2 hoặc K3, và kết quả tùy repository còn giữ snapshot tương ứng hay không.

Vì vậy, khi người dùng vừa Forward về Review K3:

- Dữ liệu hiển thị có thể là dữ liệu cũ.
- Giá, số chỗ hoặc quyền xác nhận có thể đã thay đổi.
- Snapshot K3 có thể không còn tồn tại.
- Một nhánh khác của flow có thể đã hoàn thành nghiệp vụ.

Không nên dùng việc hiện lại một trang review làm bằng chứng người dùng có thể `confirm` an toàn. Tại bước xác nhận, service cần kiểm tra lại mọi điều kiện trọng yếu.

### 6.1. Vì sao Forward đôi khi không còn mục để đi tới?

Lịch sử trình duyệt là một danh sách điều hướng. Khi đang ở mục cũ rồi thực hiện **một điều hướng mới**, trình duyệt thường loại phần lịch sử Forward không còn nằm trên nhánh mới. Đây là hành vi của trình duyệt, **không nhất thiết liên quan tới việc repository đã xóa snapshot tương ứng**.

Một trang cũ vẫn có thể tồn tại ở cache, bookmark hoặc tab khác. Vì vậy, “Forward đã biến mất” cũng không chứng minh execution cũ không thể được gửi lại.

## 7. Chuyển state qua event và lịch sử trình duyệt: ví dụ XML

Xét flow `booking` dưới đây. Nó nhấn mạnh các event `next`, `back`, `edit`, `confirm`, `cancel`. Các thành phần Java, view và tích hợp MVC không được trình bày đầy đủ.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking" class="com.example.booking.BookingDraft"/>

    <view-state id="passenger" view="booking/passenger" model="booking">
        <binder>
            <binding property="fullName" required="true"/>
            <binding property="email" required="true"/>
        </binder>
        <transition on="next" to="seat"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="seat" view="booking/seat" model="booking">
        <binder>
            <binding property="seatCode" required="true"/>
        </binder>
        <transition on="back" to="passenger" bind="false"/>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="seat" bind="false"/>
        <transition on="confirm" to="reserve" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="reserve">
        <evaluate expression="bookingService.reserveOnce(booking)"/>
        <transition on="success" to="completed"/>
        <transition on="unavailable" to="seat"/>
    </action-state>

    <end-state id="completed" view="booking/completed"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

**Cách áp dụng ví dụ:**

- Nếu người dùng muốn quay từ `seat` về `passenger`, nút Back trong ứng dụng nên gửi event `back`. Flow dùng transition được khai báo để cập nhật state.
- Nếu người dùng muốn sửa từ `review`, event `edit` dẫn đến `seat`; đây là một đường đi hợp lệ trong định nghĩa flow.
- Nếu người dùng nhấn Back của trình duyệt, không có gì bảo đảm event `back` hoặc `edit` được gửi.
- `reserveOnce` là tên service minh họa cho thao tác có khả năng chống gọi lặp. Ví dụ giả định service/adaptor trả các outcome `success` hoặc `unavailable` tương ứng; khi triển khai phải cấu hình outcome và exception cụ thể.

Lưu ý: `bind="false"` giúp bỏ qua binding khi thao tác chỉ điều hướng, nhưng **cũng có nghĩa dữ liệu mới gõ vào form chưa submit có thể không được lưu**. Nếu sản phẩm cần giữ cả thay đổi chưa xác nhận khi nhấn Back, hãy thiết kế binding và validation phù hợp, không gắn `bind="false"` một cách máy móc.

## 8. Khi nào nên dùng event Back thay vì History Back?

Đối với một wizard nghiệp vụ có thứ tự, **nút Back của ứng dụng có event và transition rõ ràng thường dễ kiểm soát hơn**. Đặc biệt khi:

- Các bước có rẽ nhánh; “bước trước” theo nghiệp vụ có thể không phải trang HTTP trước đó.
- Có bước action-state hoặc decision-state không render trang.
- Người dùng có thể mở tab khác, truy cập URL trực tiếp hoặc đi qua redirect.
- Cần giữ bản nháp và quyết định có bind dữ liệu của form hiện tại hay không.
- Cần test đường `next → back → next` nhất quán với flow definition.

Tuy nhiên, người dùng vẫn sẽ sử dụng nút Back/Forward của trình duyệt. Ứng dụng cần **xử lý được** các request và màn hình cũ, thay vì kỳ vọng tất cả người dùng chỉ bấm nút điều hướng do mình cung cấp.

### 8.1. Không đồng bộ hai loại Back bằng cách phát event mù

Ví dụ, lắng nghe sự kiện trình duyệt quay về trang cũ rồi **tự động gửi event `back`** có thể làm flow lùi thêm một bước ngoài ý muốn. Trình duyệt có thể đã khôi phục một snapshot cũ, hoặc chỉ hiển thị trang cache mà flow server vẫn ở state mới.

Thay vì tự động nhân đôi hành động, hãy thiết kế đường phục hồi trang cũ theo execution key, kiểm tra state phù hợp khi submit và hướng người dùng về trạng thái hợp lệ nếu khóa không còn dùng được.

## 9. Bản nháp flowScope có giống dữ liệu đã lưu không?

Giữa các bước của flow, `flowScope` thường giữ dữ liệu bản nháp như tên, email, ghế đã chọn. Trong một snapshot cũ, `flowScope.booking.seatCode` có thể là `12A`; trong nhánh mới, nó là `12B`.

Điều này khác hẳn một **đặt vé bền vững** đã commit trong database:

| Dữ liệu | Nơi quản lý điển hình | Tác động khi khôi phục snapshot cũ |
| --- | --- | --- |
| Bản nháp đang nhập | `flowScope` | Có thể trở về giá trị trong snapshot nếu repository hỗ trợ |
| Thông báo hiển thị tại view | `flashScope`/`viewScope` | Phụ thuộc vòng đời scope và snapshot |
| Danh sách ghế trống hiện tại | Service/database | Không tự quay về trạng thái quá khứ |
| Vé đã đặt thành công | Database/giao dịch bên ngoài | Không tự bị hủy hay tạo lại chỉ vì Back |
| Session đăng nhập | Spring Security/session | Phụ thuộc phiên và chính sách xác thực hiện tại |

**Không lưu toàn bộ entity đang attached với JPA, JDBC connection hoặc dữ liệu lớn vào flowScope.** Dùng DTO nhỏ gọn, ID và các lựa chọn cần thiết; trước commit, tra cứu lại dữ liệu nguồn và xác minh bất biến nghiệp vụ.

### 9.1. Điều kiện nghiệp vụ thay đổi sau khi snapshot được tạo

Giả sử người dùng có snapshot cũ với giá vé 1.200.000 đồng. Sau đó giá thay đổi. Nếu họ confirm từ một trang cũ, hệ thống phải dùng **chính sách giá hiện hành hoặc giá đã được khóa theo hợp đồng được lưu bền vững**. Không mặc định lấy số hiển thị từ HTML hoặc bản nháp snapshot làm giá được thanh toán.

Tương tự, kiểm tra quyền truy cập, số ghế còn lại, hạn mức đặt và dữ liệu người dùng phải được xác nhận lại ở điểm ghi.

## 10. Repository lưu snapshot quyết định điều gì?

Trong Spring Web Flow, **FlowExecutionRepository** quản lý việc lưu, lấy lại và tiếp tục flow execution. Cấu hình repository/snapshot ảnh hưởng đến:

1. Liệu có thể tiếp tục bằng **khóa cũ** hay chỉ bằng trạng thái hiện hành.
2. Có bao nhiêu snapshot được giữ cho mỗi execution.
3. Cách hệ thống giới hạn số execution/conversation trong một phiên.
4. Hành vi khi execution bị kết thúc, timeout hoặc khóa không hợp lệ.
5. Chi phí bộ nhớ, tuần tự hóa và đồng thời khi nhiều flow cùng tồn tại.

Một repository có cơ chế **continuation** có thể lưu các snapshot lịch sử để hỗ trợ Back/Forward. Nhưng dung lượng không vô hạn: snapshot cũ có thể bị loại khi vượt giới hạn. Các loại repository và giá trị mặc định thay đổi theo phiên bản/cấu hình; **không nên dựa vào một con số mặc định chưa được kiểm tra**.

### 10.1. Phải kiểm thử đúng cấu hình đang triển khai

Nếu môi trường phát triển dùng một repository hỗ trợ nhiều snapshot nhưng production cấu hình khác, hành vi Back có thể khác. Hãy xác nhận:

- Repository và chính sách snapshot thực tế.
- Cơ chế lưu session, replication hoặc session affinity trong môi trường nhiều node.
- Thời gian timeout và giới hạn lưu execution.
- Hành vi khi người dùng logout hoặc đổi quyền.
- Cơ chế khóa/đồng thời khi hai request cùng tiếp tục một execution.

Một test chỉ thao tác next ở một tab chưa đủ để xác nhận trải nghiệm với snapshot cũ.

## 11. Post/Redirect/Get và việc trang cũ xuất hiện trong lịch sử

Trong mô hình **Post/Redirect/Get (PRG)**, sau một POST xử lý form, server redirect sang một GET hiển thị trang kế tiếp. Nhờ đó, việc refresh GET thường tránh cảnh báo gửi lại POST ngay lập tức.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as FlowExecutor
    B->>F: POST next (snapshot S1)
    F->>F: Binding, validate, state mới
    F-->>B: Redirect tới URL execution mới
    B->>F: GET URL được redirect
    F-->>B: HTML view mới
~~~

Spring Web Flow có cơ chế điều hướng/redirect khi flow tạm dừng ở view-state, nhưng việc sử dụng redirect và URL cụ thể phải được kiểm tra theo cấu hình.

**PRG cải thiện lịch sử trình duyệt; nó không biến snapshot cũ thành an toàn và không chống ghi trùng.** Hai POST song song hoặc retry sau timeout vẫn có thể gọi thao tác nghiệp vụ nhiều lần.

### 11.1. Cache, bfcache và các trang có dữ liệu nhạy cảm

Browser Back/Forward Cache có thể khôi phục toàn bộ trạng thái trang ngay trên trình duyệt, kể cả giá trị input trong một số trường hợp. Với dữ liệu nhạy cảm, ứng dụng cần chính sách cache phù hợp và không giả định một trang cũ được khôi phục là đã được xác thực lại.

Các header cache và hành vi bfcache khác nhau giữa trình duyệt/phiên bản; phải kiểm thử trên các trình duyệt mục tiêu. Dù HTML cũ còn hiển thị, API hoặc action phía server vẫn phải yêu cầu xác thực và phân quyền hiện hành.

## 12. Submit từ snapshot cũ: ba kết quả cần thiết kế

Hãy xét người dùng nhấn Back để về trang `seat` cũ rồi gửi `next`.

| Tình huống | Điều có thể xảy ra | Thiết kế ứng dụng nên làm |
| --- | --- | --- |
| **Snapshot vẫn được giữ** | Web Flow khôi phục `seat`, bind seatCode mới, chọn transition `next` | Kiểm tra dữ liệu theo state và xác nhận điều kiện nghiệp vụ khi ghi |
| **Snapshot đã bị loại hoặc execution không còn** | Request không thể tiếp tục flow cũ | Hiển thị thông báo hết hạn/trang không thể tiếp tục; cho bắt đầu lại hoặc phục hồi bản nháp bền vững |
| **Snapshot còn nhưng dữ liệu nghiệp vụ đã thay đổi** | Form cũ có thể vượt qua vài kiểm tra hình thức | Service đối chiếu dữ liệu mới nhất, trả lỗi có thể sửa hoặc yêu cầu người dùng xác nhận lại |

Không nên âm thầm lấy request submit cũ rồi **tạo execution mới ở bước cuối**, vì như vậy làm mất các điều kiện và quyền mà flow cũ đã thiết lập.

### 12.1. Tại sao không chỉ so sánh khóa “mới nhất”?

Snapshot cũ có thể được sử dụng hợp lệ để sửa một bước trong flow, tùy repository. Chặn mọi khóa cũ có thể làm hỏng trải nghiệm Back/Forward. Ngược lại, cho phép mọi khóa cũ là nguy hiểm nếu dữ liệu nghiệp vụ thay đổi.

Hướng giải quyết thường là: **để repository quyết định snapshot có thể khôi phục hay không**, còn service kiểm soát dữ liệu bền vững và các bất biến nghiệp vụ. Nếu sản phẩm yêu cầu một workflow chỉ cho phép “phiên bản mới nhất”, thiết kế token/version nghiệp vụ có nguồn lưu bền vững và kiểm tra rõ ràng ở service.

### 12.2. Thông báo phục hồi thân thiện

Thay vì hiển thị exception nội bộ hoặc đưa người dùng về trang trắng, một luồng lỗi có thể hiển thị:

> Phiên thực hiện thao tác này đã hết hiệu lực. Bạn có thể bắt đầu lại hoặc tiếp tục từ bản nháp gần nhất nếu đã lưu.

Chỉ cung cấp tùy chọn “tiếp tục từ bản nháp” khi thực sự có cơ chế lưu bản nháp bền vững và xác minh được người dùng có quyền truy cập bản nháp đó.

## 13. Đừng để Back làm lặp lại giao dịch đã commit

Rủi ro quan trọng nhất của snapshot cũ là **tái thực hiện tác dụng phụ**. Một người hoàn tất đặt vé rồi quay lại trang review cũ có thể gửi `confirm` lần nữa. Flow có thể không cho tiếp tục một execution đã kết thúc, nhưng **không được chỉ trông cậy vào điều đó** để bảo vệ nghiệp vụ.

Thiết kế một service đặt vé **idempotent** theo mã yêu cầu (request ID) duy nhất:

~~~text
reserveOnce(requestId, bookingDraft):
  xác thực và phân quyền người gọi
  bắt đầu transaction
  tìm booking đã có với requestId
  nếu đã tồn tại:
      trả booking hiện có / kết quả đã xử lý
  kiểm tra giá, hạn mức, ghế trống và dữ liệu hiện hành
  tạo booking mới gắn requestId
  commit
  trả booking mới
~~~

Mã giả trình bày nguyên tắc. Cần thêm **unique constraint** trên requestId (đúng phạm vi người dùng/tác vụ), kiểm soát cạnh tranh và xử lý xung đột transaction: một truy vấn “chưa tồn tại” rồi mới INSERT chưa đủ để ngăn hai request đồng thời.

Mã requestId phải được tạo theo nghiệp vụ và có vòng đời phù hợp; không nên dùng **execution key** như idempotency key bởi snapshot hoặc lần execution có thể thay đổi mà vẫn gắn với cùng một ý định đặt chỗ.

### 13.1. Hủy flow không tự hủy booking

Nếu người dùng đã commit booking và sau đó Back để nhấn Cancel trên trang cũ, transition `cancel` **chỉ kết thúc/điều hướng flow**. Để hủy booking thật sự cần một nghiệp vụ `cancelBooking` riêng, có kiểm tra quyền, trạng thái và chính sách hoàn tiền.

Đối với nhiều bước đã tạo tài nguyên bền vững, cơ chế hoàn tác cần được thiết kế ở tầng service/transaction/saga, không trông đợi snapshot hoặc nút Back có khả năng “quay ngược thời gian”.

## 14. Hai tab cùng một flow execution

Một người có thể mở hai tab bằng cách nhân bản cùng trang review. Nếu cả hai tab dùng **cùng execution key**, chúng có thể cùng tham chiếu một snapshot. Tab A nhấn Confirm; tab B vẫn hiện review cũ rồi cũng nhấn Confirm.

~~~mermaid
flowchart TD
    E["Execution/snapshot review K3"] --> A["Tab A: Confirm"]
    E --> B["Tab B: Confirm"]
    A --> S["Service reserveOnce"]
    B --> S
    S --> D[("Unique requestId trong DB")]
    D --> R["Tối đa một booking cho cùng ý định"]
~~~

Web Flow/repository có cơ chế đồng thời riêng theo cấu hình, nhưng không thể thay thế ràng buộc unique và transaction khi hai request cùng thực hiện một nghiệp vụ.

Khác với hai tab có **hai flow execution độc lập**, việc cùng dùng một execution có thể tạo xung đột khi khôi phục snapshot và xử lý event. Cần kiểm thử trường hợp này để quyết định hiển thị kết quả đã có, cảnh báo trang lỗi thời hay mời làm mới.

## 15. Kiểm thử Browser Back/Forward và snapshot cũ

Kiểm thử nên kết hợp **flow-level test** với **integration/browser test**. Test flow bằng cách gửi event thường không mô phỏng được toàn bộ lịch sử và cache của trình duyệt.

| Kịch bản | Thao tác | Kết quả mong muốn |
| --- | --- | --- |
| Back trong flow | Ở `seat`, gửi event `back` | Chuyển sang `passenger` và giữ bản nháp phù hợp |
| Back của trình duyệt | Tới `review`, nhấn Browser Back | Có thể thấy `seat` cũ; không tự giả định server đã lùi state |
| Forward của trình duyệt | Sau Back, nhấn Forward | Không tự xác nhận nghiệp vụ; dữ liệu cũ được xử lý an toàn |
| Submit khóa cũ còn hợp lệ | Từ trang `seat` cũ, gửi `next` | Tùy repository, khôi phục state đúng rồi validation lại |
| Snapshot đã bị loại | Dùng khóa rất cũ sau khi vượt giới hạn snapshot | Thông báo không thể tiếp tục, không phát sinh side effect |
| Session đã hết hạn | Gửi form cũ sau timeout | Yêu cầu bắt đầu lại hoặc phục hồi bản nháp đúng quyền |
| Back sau completed | Hoàn tất rồi quay lại review cũ và confirm | Không tạo booking thứ hai |
| Hai tab một execution | Cả hai submit confirm gần như đồng thời | Một ý định không tạo hai booking |
| Dữ liệu ngoài thay đổi | Ghế đã bị người khác giữ trước | Service báo không còn chỗ, cho chọn lại |
| CSRF/auth thay đổi | Logout, rồi submit form cũ | Từ chối hành động theo chính sách bảo mật hiện hành |

### 15.1. Test flow transition (mã giả)

~~~text
execution = startFlow("booking")
assertState(execution, "passenger")

execution = send(execution, "next", validPassenger)
assertState(execution, "seat")

execution = send(execution, "back")
assertState(execution, "passenger")
assertFlowData(execution, "booking.email", validPassenger.email)
~~~

Đây là **pseudocode**, không phải API Java có thể biên dịch nguyên văn. Nó kiểm tra event `back` của flow, **chưa chứng minh Browser Back hoạt động đúng**.

### 15.2. Test trình duyệt thật

Với Playwright, Selenium hoặc công cụ kiểm thử browser được dự án sử dụng, cần:

1. Mở flow và đi qua các bước đến review.
2. Ghi nhận URL hiện tại và trạng thái render, không hardcode execution key.
3. Dùng thao tác **Back/Forward thật** của browser.
4. Submit từ trang cũ và kiểm tra phản hồi theo cấu hình repository.
5. Lặp lại với cache/bfcache, timeout, logout, nhiều tab và dữ liệu database thay đổi.
6. Xác minh số bản ghi thực tế sau double-submit/Back-confirm.

**Kết quả “hiện đúng giao diện” và “không ghi dữ liệu trùng” phải được kiểm tra riêng.**

## 16. Checklist thiết kế luồng tương tác hỗ trợ lịch sử trình duyệt

Trước khi đưa một flow nhiều bước vào môi trường thực tế, trả lời được các câu hỏi:

1. Mỗi view-state có event `back`/`edit` rõ ràng không? Đường đi quay lại có đúng quy trình nghiệp vụ không?
2. Event `back` có cần giữ dữ liệu mới nhập hay nên bỏ qua binding?
3. Repository hiện dùng có hỗ trợ snapshot/continuation không, giới hạn là bao nhiêu và timeout thế nào?
4. Browser Back/Forward có thể trả về cache hay phát GET/POST nào? Có trường hợp form giữ khóa cũ không?
5. Khi snapshot không thể khôi phục, người dùng được báo gì và đi tiếp thế nào?
6. Có dữ liệu nghiệp vụ nào có thể đổi giữa lúc render và confirm? Service có kiểm tra lại không?
7. Action ghi có idempotency key riêng và unique constraint phù hợp không?
8. Khi người dùng logout hoặc mất quyền, form cũ có còn thực hiện thao tác được không?
9. Khi session hết hạn, có bản nháp bền vững cho phép phục hồi đúng quyền hay không?
10. Đã kiểm thử trên browser mục tiêu và trong cấu hình repository/session tương đương production chưa?

## 17. Bài thực hành: một trang cũ, hai kết quả khác nhau

Cho flow `hotelReservation`:

~~~mermaid
flowchart LR
    D["dates"] -->|next| R["room"]
    R -->|next| V["review"]
    V -->|confirm| C["createReservation"]
    C -->|success| E((completed))
    C -->|unavailable| R
    R -->|back| D
    V -->|edit| R
~~~

Người dùng chọn phòng A ở trang room, đến review rồi nhấn Browser Back. Trang room cũ xuất hiện.

**Bài tập:**

1. Mô tả chính xác những gì Browser Back đã làm trên trình duyệt và những gì **chưa thể kết luận** về flow execution trên server.
2. Giả định repository **còn snapshot** của room. Nếu người dùng chọn phòng B và nhấn Next từ form cũ, vẽ nhánh execution mới và chỉ ra dữ liệu nào được cập nhật.
3. Giả định snapshot room đã bị loại. Nêu thông báo phù hợp và cách người dùng có thể bắt đầu lại hoặc khôi phục bản nháp.
4. Nếu người dùng Forward trở lại review phòng A rồi nhấn Confirm, cần kiểm tra lại những điều kiện nào?
5. Sau khi đặt phòng thành công, người dùng Back và gửi Confirm lần nữa. Thiết kế requestId/unique constraint để không tạo hai reservation.
6. Kiểm thử trường hợp hai tab cùng dùng một execution key. Tách kiểm thử điều hướng và kiểm thử số bản ghi thực tế.
7. Giải thích tại sao event `edit` trong flow an toàn về mặt mô hình hóa đường đi nhưng vẫn chưa đủ để bảo vệ giá phòng và tình trạng phòng trống.

**Gợi ý:** Hãy lập bảng gồm bốn cột: `Browser page`, `Execution key`, `State được repository khôi phục`, `Trạng thái nghiệp vụ trong database`. Với mỗi hành động, ghi rõ điều gì biết chắc và điều gì còn phụ thuộc cấu hình.

## 18. Câu hỏi tự kiểm tra và tổng kết

**Tự kiểm tra:**

1. Vì sao Browser Back không đồng nghĩa với việc phát event `back`?
2. Điều kiện nào khiến một khóa execution cũ có thể khôi phục được, và điều kiện nào khiến nó bị từ chối?
3. Snapshot cũ chứa `seatCode=12A` có khôi phục ghế 12A về trạng thái còn trống trong database không?
4. Vì sao sau khi quay Back rồi tạo nhánh mới, trang Forward cũ có thể không còn đáng tin?
5. PRG giúp tránh vấn đề nào, và vì sao vẫn phải có idempotency khi confirm?
6. Khi người dùng đã thanh toán rồi nhấn Cancel từ trang cũ, chuyện gì phải do service nghiệp vụ xử lý?
7. Test event `back` bằng FlowExecutor đã đủ thay thế kiểm thử Browser Back/Forward chưa?

Nút **Back/Forward** điều khiển **lịch sử trang của trình duyệt**, trong khi **state/event/transition** điều khiển **hành trình nghiệp vụ của Web Flow**. Một request gửi từ trang cũ có thể tiếp tục từ snapshot trước đó nếu repository còn hỗ trợ, hoặc phải được xử lý như một request không thể phục hồi. Ở cả hai trường hợp, **scope và snapshot chỉ bảo quản ngữ cảnh flow**; tính hợp lệ của dữ liệu, quyền thực hiện, transaction và idempotency phải được kiểm tra tại tầng service/database.
