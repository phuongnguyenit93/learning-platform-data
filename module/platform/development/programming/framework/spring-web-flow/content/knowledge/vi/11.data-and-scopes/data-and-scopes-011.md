# Bean theo scope flow, view và conversation

Trong Spring Web Flow, một hành trình nhiều bước cần giữ dữ liệu qua nhiều màn hình nhưng cũng phải giải phóng dữ liệu đúng lúc. Ví dụ, quy trình đặt chỗ có thể giữ bản nháp trong suốt flow, giữ danh sách lựa chọn tạm thời chỉ khi người dùng đang ở một màn hình, và chia sẻ ngữ cảnh đặt chỗ với subflow thanh toán. Spring Web Flow cung cấp các scope **flow**, **view** và **conversation** để biểu diễn ba vòng đời đó.

Bài này thuộc chương **Dữ liệu và scope** của module **SPRING_WEB_FLOW**. Bạn sẽ học cách chọn scope cho từng đối tượng, khởi tạo dữ liệu từ bean dịch vụ, chia sẻ ngữ cảnh với subflow và kiểm tra để dữ liệu của một flow execution không rò rỉ sang hành trình khác.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Phân biệt vòng đời của **flowScope**, **viewScope** và **conversationScope**.
- Lưu dữ liệu biểu mẫu và bản nháp ở phạm vi flow.
- Giữ trạng thái tạm thời chỉ phục vụ một view-state.
- Chia sẻ ngữ cảnh giữa flow cha và subflow trong cùng conversation.
- Phân biệt đối tượng dữ liệu trong scope của Web Flow với bean dịch vụ do Spring quản lý.
- Chọn dữ liệu phù hợp để lưu, tránh giữ tài nguyên không thể khôi phục trong flow execution.
- Kiểm thử việc khởi tạo, giữ lại và kết thúc dữ liệu theo từng scope.

## 1. Ba scope giải quyết ba vòng đời khác nhau

Một flow execution có thể đi qua nhiều view-state và gọi các subflow. Không phải dữ liệu nào cũng cần sống lâu như nhau. Hãy bắt đầu bằng câu hỏi: dữ liệu cần tồn tại đến thời điểm nào?

| Scope | Vòng đời | Trường hợp sử dụng |
|---|---|---|
| **viewScope** | Trong thời gian flow execution ở một view-state cụ thể; bị loại bỏ khi rời state đó. | Bộ lọc tạm, tab đang chọn, danh sách gợi ý hoặc trạng thái giao diện riêng của màn hình. |
| **flowScope** | Trong suốt flow execution hiện tại, từ khi flow bắt đầu đến khi flow kết thúc. | Bản nháp, dữ liệu biểu mẫu, kết quả lựa chọn cần dùng qua nhiều bước. |
| **conversationScope** | Trong suốt conversation do flow cấp cao nhất mở; được chia sẻ với các subflow thuộc conversation đó. | Ngữ cảnh chung mà flow cha và nhiều subflow cùng cần, chẳng hạn mã quy trình hoặc thông tin người dùng đã chọn. |

Có thể hình dung phạm vi lồng nhau như sau:

~~~mermaid
flowchart TD
    C[Conversation của flow gốc] --> F[Flow execution gốc]
    C --> S[Subflow execution]
    F --> FS[flowScope của flow gốc]
    F --> V[viewScope của view-state hiện tại]
    S --> SS[flowScope riêng của subflow]
    S --> SV[viewScope của view-state trong subflow]
    C --> CS[conversationScope dùng chung]
~~~

Mỗi flow execution có **flowScope** riêng. Khi flow cha gọi subflow, subflow có **flowScope** riêng của nó, nhưng vẫn nằm trong conversation của flow gốc nên có thể truy cập **conversationScope** dùng chung. Mỗi view-state đang hoạt động có **viewScope** riêng.

Một quy tắc dễ nhớ là: dữ liệu cần qua nhiều bước thuộc **flowScope**; dữ liệu chỉ phục vụ màn hình hiện tại thuộc **viewScope**; dữ liệu cần chia sẻ giữa flow gốc và các subflow trong cùng hành trình thuộc **conversationScope**.

## 2. Phân biệt scope của Web Flow với scope của Spring bean

Các tên **flowScope**, **viewScope** và **conversationScope** là những phạm vi dữ liệu do Spring Web Flow quản lý trong một flow execution. Chúng được truy cập trong biểu thức của flow và trong ngữ cảnh view được Web Flow cung cấp.

Điều này khác với vòng đời bean trong Spring ApplicationContext. Ví dụ, một bean dịch vụ như **bookingService** thường là Spring bean singleton, có nhiệm vụ xử lý nghiệp vụ. Dữ liệu riêng của một lần đặt chỗ được trả về từ dịch vụ có thể được lưu vào **flowScope.booking**. Không nên biến dịch vụ thành đối tượng có trạng thái dùng chung chỉ để giữ dữ liệu của một người dùng.

Ví dụ:

~~~xml
<evaluate expression="bookingService.createDraft()"
          result="flowScope.booking"/>
~~~

Trong biểu thức trên:

- **bookingService** là bean do Spring quản lý và được gọi để tạo bản nháp.
- **createDraft()** trả về đối tượng dữ liệu của một hành trình.
- **flowScope.booking** giữ kết quả đó trong flow execution hiện tại.

Nếu có hai người dùng cùng khởi chạy flow, mỗi flow execution sẽ có đối tượng **booking** riêng. Bean dịch vụ có thể vẫn là singleton nếu nó không giữ trạng thái riêng của từng request hoặc người dùng.

Không nên lưu dữ liệu người dùng vào field mutable của một service singleton, chẳng hạn:

~~~java
// Ví dụ thiết kế không an toàn cho dữ liệu theo từng flow
@Service
public class BookingService {
    private BookingDraft currentBooking;
}
~~~

Các flow execution có thể chạy đồng thời. Nếu nhiều người dùng cùng ghi vào **currentBooking**, dữ liệu có thể ghi đè lẫn nhau. Hãy để service xử lý nghiệp vụ và trả về đối tượng dữ liệu; flow execution chịu trách nhiệm giữ đối tượng đó trong scope phù hợp.

## 3. Dùng flowScope cho dữ liệu xuyên suốt hành trình

Giả sử quy trình đặt chỗ có các bước:

1. Nhập thông tin khách và ngày nhận phòng.
2. Rà soát thông tin.
3. Chọn phương thức thanh toán trong một subflow.
4. Hoàn tất đặt chỗ.

Bản nháp phải tồn tại từ bước đầu đến khi quy trình kết thúc. Có thể khởi tạo bản nháp ở sự kiện **on-start** và lưu vào **flowScope**:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <on-start>
        <evaluate expression="bookingService.createDraft()"
                  result="flowScope.booking"/>
    </on-start>

    <view-state id="edit" view="booking/edit" model="booking">
        <transition on="continue" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review" model="booking">
        <transition on="change" to="edit"/>
        <transition on="pay" to="payment"/>
    </view-state>

    <subflow-state id="payment" subflow="payment">
        <input name="bookingId" value="flowScope.booking.id"/>
        <transition on="paid" to="completed"/>
        <transition on="cancel" to="review"/>
    </subflow-state>

    <end-state id="completed" view="booking/completed"/>
</flow>
~~~

**on-start** chạy khi flow execution bắt đầu. Kết quả của **bookingService.createDraft()** được đặt vào **flowScope.booking**, vì vậy view-state **edit** và **review** có thể cùng sử dụng bản nháp đó.

Thuộc tính **model="booking"** cho phép view-state dùng đối tượng **booking** làm model của biểu mẫu. Các trường trong JSP có thể binding vào những thuộc tính của đối tượng, ví dụ **guestName**, **checkInDate** hoặc **numberOfGuests**. Khi transition **change** đưa người dùng từ **review** về **edit**, dữ liệu vẫn nằm trong flow scope của execution đó.

Có thể khai báo flow variable bằng phần tử **var** nếu muốn Web Flow khởi tạo đối tượng theo lớp được chỉ định:

~~~xml
<var name="booking" class="com.example.booking.BookingDraft"/>
~~~

Biến flow được khai báo theo cách này thuộc **flowScope**. Cách khởi tạo bằng **evaluate** phù hợp khi cần gọi factory hoặc service để tạo dữ liệu ban đầu; **var** phù hợp với đối tượng có thể tạo trực tiếp bằng constructor mặc định. Chọn một cách khởi tạo rõ ràng để tránh vô tình tạo hai bản nháp cho cùng một flow.

### Những gì nên đặt trong flowScope

Nên lưu các dữ liệu có ý nghĩa trong suốt hành trình, chẳng hạn:

- Đối tượng biểu mẫu tổng hợp qua nhiều bước.
- Mã bản nháp hoặc mã giao dịch đang xử lý.
- Lựa chọn mà người dùng cần xem lại hoặc thay đổi ở bước trước.
- Kết quả kiểm tra nghiệp vụ cần dùng ở state tiếp theo.

Không nên đặt vào flow scope các đối tượng giữ tài nguyên sống như **HttpServletRequest**, **InputStream**, kết nối JDBC đang mở hoặc **EntityManager**. Những đối tượng này có vòng đời gắn với request hoặc tài nguyên bên ngoài; chúng không phù hợp với một flow execution có thể tạm dừng và được khôi phục sau đó.

Khi flow execution được lưu snapshot hoặc khôi phục từ repository, các đối tượng trong scope cần tương thích với cơ chế lưu trữ đang cấu hình. Trong môi trường cần tuần tự hóa execution, hãy dùng DTO có thể tuần tự hóa và tránh giữ proxy hoặc tài nguyên không thể tuần tự hóa. Một lựa chọn phổ biến là giữ mã định danh và dữ liệu cần thiết, rồi tải lại dữ liệu nghiệp vụ từ service khi tiếp tục flow.

## 4. Dùng viewScope cho trạng thái riêng của màn hình

Giả sử màn hình chọn phòng có danh sách loại phòng, bộ lọc tiện ích và tab đang chọn. Các thông tin này chỉ phục vụ màn hình chọn phòng. Nếu người dùng rời view-state để sang màn hình rà soát, chúng không cần tồn tại trong toàn bộ flow.

Có thể chuẩn bị dữ liệu cho view-state khi vào màn hình:

~~~xml
<view-state id="chooseRoom"
            view="booking/choose-room">

    <on-entry>
        <evaluate expression="roomService.loadAvailableFilters()"
                  result="viewScope.availableFilters"/>
        <set name="viewScope.selectedTab" value="'all'"/>
    </on-entry>

    <transition on="select" to="review"/>
    <transition on="back" to="edit"/>
</view-state>
~~~

Trong ví dụ, **availableFilters** và **selectedTab** thuộc **viewScope**. View có thể dùng chúng để hiển thị bộ lọc và tab đang chọn. Khi flow rời state **chooseRoom**, view scope của state đó kết thúc. Nếu người dùng quay lại state này sau đó, phần **on-entry** chạy lại và view scope mới được tạo.

Điều này đặc biệt hữu ích cho dữ liệu có thể tính lại, chẳng hạn danh sách tùy chọn hoặc trạng thái hiển thị. Ngược lại, nếu lựa chọn phòng của người dùng phải được giữ khi chuyển sang bước rà soát rồi quay lại, lựa chọn đó nên nằm trong **flowScope**, vì nó là dữ liệu nghiệp vụ của toàn hành trình.

Một view có thể sử dụng cả hai phạm vi:

- **viewScope.availableFilters**: danh sách bộ lọc chỉ cần khi chọn phòng.
- **flowScope.booking.selectedRoomId**: mã phòng đã chọn, cần giữ đến bước xác nhận.

Tách như vậy giúp tránh lưu dữ liệu giao diện tạm thời vào đối tượng nghiệp vụ và cũng tránh làm mất lựa chọn quan trọng khi người dùng chuyển state.

## 5. Dùng conversationScope để chia sẻ với subflow

Khi flow gốc gọi subflow, hai flow execution có **flowScope** độc lập. Nếu một dữ liệu thật sự cần được dùng chung giữa các flow trong cùng conversation, có thể lưu dữ liệu đó trong **conversationScope**.

Ví dụ, flow đặt chỗ tạo một ngữ cảnh dùng chung:

~~~xml
<on-start>
    <evaluate expression="bookingService.createDraft()"
              result="flowScope.booking"/>
    <evaluate expression="conversationContextFactory.create()"
              result="conversationScope.context"/>
</on-start>
~~~

Subflow thanh toán có thể dùng lại ngữ cảnh đó:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="bookingId"/>

    <on-start>
        <evaluate expression="paymentService.prepare(
                    bookingId, conversationScope.context)"
                  result="flowScope.payment"/>
    </on-start>

    <view-state id="selectMethod" view="payment/select">
        <transition on="submit" to="process"/>
        <transition on="cancel" to="cancel"/>
    </view-state>

    <action-state id="process">
        <evaluate expression="paymentService.charge(flowScope.payment)"/>
        <transition to="paid"/>
    </action-state>

    <end-state id="paid"/>
    <end-state id="cancel"/>
</flow>
~~~

Trong flow cha, phần tử **subflow-state** truyền **bookingId** bằng input mapping. Subflow nhận giá trị đầu vào đó, còn **conversationScope.context** là ngữ cảnh dùng chung của conversation. Đối tượng **payment** được lưu trong **flowScope** riêng của subflow vì nó chỉ thuộc quá trình thanh toán.

Cần cân nhắc trước khi đưa dữ liệu vào conversation scope. Dữ liệu ở đó tồn tại lâu hơn flow scope của một subflow và có thể được nhiều subflow cùng truy cập. Nếu chỉ cần truyền một vài giá trị từ flow cha sang subflow, input mapping và output mapping thường diễn đạt quan hệ phụ thuộc rõ hơn. Chỉ dùng conversation scope cho ngữ cảnh thực sự cần chia sẻ trong suốt conversation.

Conversation không đồng nghĩa với toàn bộ HTTP session. Hai flow gốc được khởi chạy độc lập có conversation riêng; không nên dùng **conversationScope** như một kho dữ liệu toàn cục cho mọi tab hoặc mọi người dùng. Khi flow gốc kết thúc, conversation kết thúc và dữ liệu thuộc phạm vi đó được giải phóng theo vòng đời của execution.

## 6. Chọn scope cho một quy trình thực tế

Với ví dụ đặt chỗ, có thể phân bổ dữ liệu như sau:

| Dữ liệu | Scope đề xuất | Lý do |
|---|---|---|
| Bản nháp đặt chỗ | **flowScope** | Cần qua các bước nhập, rà soát và thanh toán. |
| Tên khách, ngày nhận phòng | **flowScope** | Là dữ liệu nghiệp vụ người dùng có thể sửa trước khi xác nhận. |
| Tab đang chọn trên màn hình phòng | **viewScope** | Chỉ phục vụ giao diện của view-state chọn phòng. |
| Danh sách bộ lọc phòng có thể tính lại | **viewScope** | Có thể nạp lại khi người dùng vào màn hình. |
| Ngữ cảnh chung cho đặt chỗ và thanh toán | **conversationScope** | Flow gốc và subflow thanh toán cùng cần. |
| Kết quả riêng của subflow thanh toán | **flowScope** của subflow | Không cần tồn tại trong flow cha dưới dạng trạng thái nội bộ của subflow. |

Trước khi chọn scope, hãy tự hỏi:

1. Người dùng rời màn hình hiện tại thì dữ liệu còn cần không?
2. Dữ liệu có cần tồn tại qua nhiều state của cùng flow execution không?
3. Subflow khác có cần đọc hoặc cập nhật dữ liệu này không?
4. Khi flow kết thúc, dữ liệu có thể được giải phóng hoàn toàn không?
5. Đối tượng có thể được lưu snapshot hoặc khôi phục theo cơ chế triển khai không?

Nếu dữ liệu chỉ dùng để trình bày một view, hãy ưu tiên view scope. Nếu dữ liệu là một phần của quy trình hiện tại, hãy dùng flow scope. Nếu nhiều flow execution nằm trong cùng conversation cần dùng chung một ngữ cảnh, hãy cân nhắc conversation scope.

## 7. Kiểm thử vòng đời và tính cô lập của dữ liệu

Một cấu hình scope có thể hoạt động ở màn hình đầu nhưng sai khi người dùng quay lại, mở thêm subflow hoặc khởi chạy một flow mới. Vì vậy, kiểm thử nên bao phủ cả vòng đời thay vì chỉ xác nhận một view hiển thị được.

| Tình huống | Điều cần xác nhận |
|---|---|
| Khởi chạy flow gốc | **flowScope.booking** được tạo cho execution mới; **conversationScope.context** được khởi tạo một lần cho conversation. |
| Chuyển từ **edit** sang **review** | Dữ liệu bản nháp vẫn có trong flow scope. |
| Rời **chooseRoom** rồi quay lại | Dữ liệu view scope cũ không còn; trạng thái giao diện được tạo lại theo **on-entry**. |
| Gọi subflow thanh toán | Subflow có **flowScope** riêng nhưng đọc được ngữ cảnh conversation được chia sẻ. |
| Khởi chạy một flow gốc khác | Bản nháp và conversation context của flow mới độc lập với flow trước. |
| Kết thúc flow gốc | Conversation kết thúc; dữ liệu tạm không được giữ như trạng thái đang hoạt động. |
| Khôi phục execution từ snapshot | Dữ liệu cần thiết có thể được phục hồi theo cơ chế lưu trữ đã cấu hình. |

Trong kiểm thử tích hợp, hãy chạy hai flow execution với dữ liệu khác nhau rồi xác nhận mỗi execution chỉ đọc và cập nhật bản nháp của chính nó. Với subflow, xác nhận dữ liệu cần chia sẻ xuất hiện trong conversation scope, còn biến nội bộ của subflow không bị nhầm thành dữ liệu flow cha.

Cũng nên kiểm thử việc người dùng quay lại state cũ. Một lựa chọn nghiệp vụ đặt trong **flowScope** phải còn nguyên; một bộ lọc chỉ đặt trong **viewScope** có thể được khởi tạo lại. Đây là hành vi có chủ đích nếu vòng đời được chọn đúng.

## 8. Những lỗi thiết kế thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Dữ liệu biểu mẫu biến mất sau khi chuyển state | Đặt dữ liệu cần dùng lâu dài trong **viewScope**. | Chuyển dữ liệu nghiệp vụ sang **flowScope**. |
| Subflow không thấy dữ liệu của flow cha | Giả định **flowScope** được chia sẻ giữa hai flow execution. | Truyền input/output rõ ràng hoặc dùng **conversationScope** cho dữ liệu chung. |
| Người dùng này thấy dữ liệu của người dùng khác | Lưu dữ liệu theo từng hành trình vào field mutable của singleton hoặc vùng static. | Đưa dữ liệu vào scope của flow execution; giữ service stateless. |
| Dữ liệu giao diện cũ xuất hiện khi vào lại màn hình | Dùng scope rộng hơn vòng đời cần thiết. | Đưa trạng thái riêng của view vào **viewScope**. |
| Không khôi phục được flow execution | Đối tượng trong scope không phù hợp với cơ chế snapshot/serialization. | Giữ DTO và mã định danh có thể lưu; tải lại tài nguyên từ service. |
| Conversation chứa quá nhiều dữ liệu | Dùng conversation scope như một kho lưu trữ dài hạn. | Chỉ giữ ngữ cảnh dùng chung trong hành trình; lưu dữ liệu lâu dài ở tầng nghiệp vụ. |

Không nên đưa mật khẩu, token bí mật hoặc dữ liệu nhạy cảm không cần thiết vào scope chỉ vì scope thuận tiện. Scope là nơi giữ trạng thái thực thi, không thay thế cơ chế quản lý bí mật, phân quyền hoặc lưu trữ an toàn của ứng dụng.

## 9. Nguyên tắc sử dụng scope lâu dài

Hãy chọn scope nhỏ nhất đáp ứng đúng vòng đời dữ liệu. Điều đó giúp dữ liệu được giải phóng sớm, giảm trạng thái cần khôi phục và tránh việc các bước trong flow phụ thuộc vào những biến không còn cần thiết.

Giữ service bean tập trung vào nghiệp vụ và để Spring quản lý vòng đời bean. Dữ liệu của từng hành trình nên nằm trong scope của Spring Web Flow, với đối tượng dữ liệu rõ ràng và có thể khôi phục khi cần. Dùng **flowScope** cho bản nháp xuyên bước, **viewScope** cho trạng thái riêng của màn hình và **conversationScope** cho ngữ cảnh được chia sẻ giữa flow gốc với các subflow.

Khi thiết kế subflow, ưu tiên truyền dữ liệu đầu vào và kết quả đầu ra tường minh. Chỉ chia sẻ conversation scope khi các bước thực sự cần cùng một ngữ cảnh. Cách tổ chức này giúp mỗi flow có ranh giới dữ liệu rõ ràng, kiểm thử được và dễ bảo trì khi hành trình web phát triển thêm bước mới.
