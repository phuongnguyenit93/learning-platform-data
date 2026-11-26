# Thiết kế tên sự kiện phản ánh ý định người dùng

Trong chương **Event và transition**, bài này tập trung vào cách đặt tên event để mô tả điều người dùng muốn thực hiện trong một hành trình Spring Web Flow. Với module **SPRING_WEB_FLOW**, flow được mô hình hóa bằng state, event, transition và subflow; vì vậy tên event là một phần của hợp đồng giữa giao diện và định nghĩa flow. Tên rõ ràng giúp đọc transition dễ hơn, kiểm thử đúng hành vi và thay đổi giao diện mà không làm mất ý nghĩa nghiệp vụ của luồng.

Một event trong Spring Web Flow là tín hiệu gửi đến flow execution hiện tại. Khi flow đang ở một state, engine tìm transition phù hợp với event đó rồi thực hiện hành động và chuyển state theo định nghĩa. Nếu event mang tên như một nút bấm hoặc một trang đích, người đọc khó biết ý định nghiệp vụ thực sự là gì.

## Event biểu đạt điều gì?

Hãy xét màn hình nhập địa chỉ giao hàng. Người dùng có thể lưu địa chỉ, sửa thông tin, hủy quy trình hoặc tiếp tục tới bước xem lại. Giao diện có thể hiển thị nút “Tiếp tục”, nhưng flow cần hiểu hành động cụ thể là lưu địa chỉ giao hàng trước khi đi tới màn hình xem lại.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| State | Vị trí hiện tại trong hành trình | **shippingDetails** |
| Event | Ý định hoặc tín hiệu được gửi tới flow | **saveShippingAddress** |
| Transition | Quy tắc phản ứng với event tại state hiện tại | Khi nhận **saveShippingAddress**, chuyển tới **reviewOrder** |
| Action | Công việc được thực hiện trong lúc xử lý transition hoặc state | Kiểm tra dữ liệu, tính phí vận chuyển, ghi nhận lựa chọn |
| View | Giao diện hiển thị cho state | **checkout/shipping** |

Event và transition có quan hệ nhưng không phải cùng một thứ. Event là đầu vào; transition là quy tắc được flow khai báo để xử lý đầu vào đó. Cùng một event chỉ có ý nghĩa khi được xét trong ngữ cảnh state hiện tại và các quy tắc của flow.

~~~mermaid
flowchart TD
    A["Người dùng thao tác trên form"] --> B["Gửi event ID"]
    B --> C["Flow execution hiện tại"]
    C --> D{"State hiện tại"}
    D --> E["Tìm transition có on khớp event"]
    E --> F["Chạy action / kiểm tra điều kiện"]
    F --> G["Chuyển state hoặc vào subflow"]
    G --> H["Render view tiếp theo"]
~~~

Tên event nên trả lời câu hỏi: **Người dùng đang yêu cầu flow làm việc gì?** Nó không cần trả lời nút nằm ở đâu, người dùng đã nhấn chuột hay flow sẽ hiển thị trang nào sau đó.

## Vì sao tên event cần phản ánh ý định?

Tên event là một phần của giao diện giữa view và flow definition. Một view phát event; flow nhận đúng event ID và tìm transition có thuộc tính **on** tương ứng. Khi tên mang ý nghĩa nghiệp vụ, người đọc có thể hiểu hành vi từ định nghĩa flow mà không cần mở giao diện để đoán.

Ví dụ, **saveShippingAddress** nói rõ người dùng muốn lưu địa chỉ giao hàng. Nếu transition đưa flow tới màn hình xem lại, ý nghĩa vẫn đúng: việc chuyển màn hình là kết quả của hành động lưu, không phải bản chất của event.

Tên event rõ ràng mang lại một số lợi ích:

- **Dễ đọc flow:** transition cho thấy hành động nghiệp vụ nào dẫn đến bước tiếp theo.
- **Dễ bảo trì giao diện:** có thể đổi chữ trên nút, thay JSP bằng Thymeleaf hoặc thay bố cục mà vẫn giữ event ID.
- **Dễ kiểm thử:** kịch bản kiểm thử có thể phát event theo ý định như **confirmOrder** hoặc **cancelCheckout**.
- **Giảm nhầm lẫn:** các hành động có hậu quả khác nhau như lưu bản nháp, gửi hồ sơ và hủy hồ sơ không bị gom vào một event chung.
- **Dễ trao đổi giữa các vai trò:** người viết flow, người làm giao diện và người kiểm thử có thể dùng chung một từ vựng nghiệp vụ.

Tên event không cần dài để mô tả toàn bộ quy trình. Nó cần đủ cụ thể để phân biệt các ý định có hành vi khác nhau.

## Quy tắc đặt tên thực dụng

Một quy ước phù hợp cho event do người dùng phát ra là **động từ + đối tượng nghiệp vụ + thông tin phân biệt khi cần**. Có thể dùng lower camel case để giữ định dạng nhất quán với ID thường gặp trong flow definition.

| Ý định | Event ID đề xuất | Vì sao rõ nghĩa |
|---|---|---|
| Lưu địa chỉ giao hàng | **saveShippingAddress** | Nêu hành động và đối tượng được lưu |
| Chỉnh sửa địa chỉ giao hàng | **editShippingAddress** | Phân biệt với lưu hoặc hủy |
| Xác nhận đơn hàng | **confirmOrder** | Nêu rõ quyết định xác nhận |
| Hủy quy trình đặt hàng | **cancelCheckout** | Cho biết phạm vi bị hủy |
| Thử thanh toán lại | **retryPayment** | Nêu hành động thử lại và đối tượng |
| Gửi hồ sơ đăng ký | **submitRegistration** | Phân biệt gửi chính thức với lưu bản nháp |
| Lưu bản nháp | **saveDraft** | Nêu rõ dữ liệu chưa được gửi chính thức |

Một số nguyên tắc giúp duy trì quy ước:

1. **Bắt đầu bằng động từ.** Dùng **saveProfile**, **submitApplication**, **cancelBooking** để thể hiện hành động.
2. **Gọi đúng đối tượng.** Nếu flow có nhiều loại địa chỉ, **saveAddress** có thể quá chung; **saveBillingAddress** và **saveShippingAddress** phân biệt được hai ý định.
3. **Giữ một ý nghĩa ổn định.** Một event ID không nên có lúc nghĩa là lưu, lúc khác lại nghĩa là xác nhận.
4. **Không gắn với chi tiết trình bày.** Tên event không nên phụ thuộc vị trí nút, tên trang, framework view hoặc thao tác chuột.
5. **Dùng cùng kiểu chữ.** Chọn lower camel case và giữ nguyên chữ hoa/thường ở mọi nơi khai báo và phát event.
6. **Chỉ thêm từ phân biệt khi có giá trị.** Tên quá dài khó đọc; tên quá ngắn lại khiến người bảo trì phải suy đoán.

Tên event là ID được đối chiếu theo giá trị chuỗi. Vì vậy **saveProfile** và **saveprofile** không nên được xem là hai cách viết có thể thay thế cho nhau. Hãy thống nhất cách viết trong flow definition, form và kiểm thử.

## Tránh đặt tên theo nút bấm hoặc trang đích

Một tên có thể hoạt động về mặt kỹ thuật nhưng vẫn gây khó hiểu về mặt thiết kế. Bảng sau minh họa cách chuyển từ tên mô tả giao diện sang tên thể hiện ý định:

| Tên yếu hoặc mơ hồ | Tên thể hiện ý định | Vấn đề được giải quyết |
|---|---|---|
| **clickNext** | **saveShippingAddress** | Không phụ thuộc thao tác chuột hay nút “Tiếp tục” |
| **button2** | **confirmOrder** | Không phụ thuộc thứ tự phần tử trên trang |
| **goToReview** | **saveShippingAddress** | Nêu hành động, không khóa event vào màn hình đích |
| **submit** | **submitRegistration** | Phân biệt loại hồ sơ được gửi |
| **success** | **confirmPayment** | Không nhầm kết quả hiển thị với ý định người dùng |
| **back** | **editShippingAddress** | Nêu rõ người dùng muốn quay lại để sửa nội dung nào |

Không phải mọi từ như **next**, **back** hay **submit** đều sai trong mọi ứng dụng. Chúng chỉ phù hợp khi ý nghĩa thực sự đủ rõ trong phạm vi flow và không gây nhập nhằng với hành động khác. Khi có nhiều bước nghiệp vụ, tên cụ thể thường giúp giảm chi phí đọc hiểu.

Cũng nên phân biệt **nhãn giao diện** với **event ID**. Nhãn “Tiếp tục” có thể được dịch sang ngôn ngữ khác hoặc đổi thành “Xem lại đơn hàng”; event ID **saveShippingAddress** vẫn giữ nguyên vì ý định gửi tới flow không đổi. Không nên dùng chính câu chữ hiển thị trên nút làm event ID.

## Ví dụ: đặt tên event cho flow đặt hàng

Giả sử flow đặt hàng có hai màn hình chính. Người dùng nhập địa chỉ giao hàng, sau đó xem lại đơn hàng. Tại màn hình xem lại, họ có thể quay lại chỉnh sửa địa chỉ, xác nhận đơn hoặc hủy quy trình.

Ta bắt đầu bằng việc liệt kê ý định theo từng state:

| State hiện tại | Ý định của người dùng | Event ID | Kết quả mong đợi |
|---|---|---|---|
| **shippingDetails** | Lưu địa chỉ để xem lại đơn | **saveShippingAddress** | Chuyển tới **reviewOrder** |
| **shippingDetails** | Hủy quy trình đặt hàng | **cancelCheckout** | Kết thúc với outcome hủy |
| **reviewOrder** | Chỉnh sửa địa chỉ giao hàng | **editShippingAddress** | Quay lại **shippingDetails** |
| **reviewOrder** | Xác nhận đơn hàng | **confirmOrder** | Đi tới bước xử lý đơn |
| **reviewOrder** | Hủy quy trình đặt hàng | **cancelCheckout** | Kết thúc với outcome hủy |

Việc lặp lại **cancelCheckout** ở hai state là hợp lý nếu nó luôn mang cùng một ý nghĩa: người dùng muốn hủy toàn bộ quy trình đặt hàng. Nếu một nút chỉ muốn quay lại màn hình trước để sửa dữ liệu, hãy dùng **editShippingAddress** thay vì dùng chung **cancelCheckout**.

Flow definition có thể biểu diễn các transition chính như sau:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <view-state id="shippingDetails"
                view="checkout/shipping"
                model="checkout">
        <transition on="saveShippingAddress" to="reviewOrder" />
        <transition on="cancelCheckout" to="cancelled" />
    </view-state>

    <view-state id="reviewOrder" view="checkout/review">
        <transition on="editShippingAddress" to="shippingDetails" />
        <transition on="confirmOrder" to="processing" />
        <transition on="cancelCheckout" to="cancelled" />
    </view-state>

    <action-state id="processing">
        <evaluate expression="orderService.placeOrder(checkout)"
                  result="flowScope.order" />
        <transition to="completed" />
    </action-state>

    <end-state id="completed" />
    <end-state id="cancelled" />
</flow>
~~~

Định nghĩa trên cho thấy tên event gắn với ý định, còn thuộc tính **to** mô tả state đích. Nếu sau này màn hình xem lại được đổi tên hoặc được thay bằng một subflow, event **saveShippingAddress** vẫn có thể giữ nguyên miễn là ý nghĩa hành động không đổi.

Trong view JSP, nút gửi event có thể được khai báo như sau:

~~~jsp
<form:form modelAttribute="checkout"
           action="${flowExecutionUrl}"
           method="post">
    <form:label path="street">Địa chỉ</form:label>
    <form:input path="street" />

    <button type="submit" name="_eventId_saveShippingAddress">
        Tiếp tục
    </button>
    <button type="submit" name="_eventId_cancelCheckout">
        Hủy đặt hàng
    </button>
</form:form>
~~~

Tên tham số **_eventId_saveShippingAddress** phát event ID **saveShippingAddress**, khớp chính xác với **on="saveShippingAddress"** trong flow definition. URL thực thi do Web Flow cung cấp giúp request tiếp theo tiếp tục đúng flow execution. Khi có nhiều nút gửi từ cùng một form, mỗi nút nên phát đúng event tương ứng với ý định của nó.

## Phân biệt ý định, kết quả và tín hiệu kỹ thuật

Không phải mọi tín hiệu đi vào flow đều là ý định trực tiếp của người dùng. Khi thiết kế tên, hãy xác định nguồn phát và ý nghĩa của tín hiệu:

| Loại tín hiệu | Ví dụ | Cách hiểu |
|---|---|---|
| Ý định người dùng | **confirmOrder**, **cancelCheckout** | Người dùng yêu cầu thực hiện một hành động |
| Kết quả từ dịch vụ ngoài | **paymentAuthorized**, **paymentDeclined** | Một hệ thống khác trả về kết quả đã xảy ra |
| Tín hiệu kỹ thuật | **timeout**, **connectionLost** | Hạ tầng hoặc cơ chế thực thi phát hiện một tình huống |

Với event do người dùng phát ra, tên dạng động từ chủ động thường diễn tả ý định tốt hơn. Với tín hiệu kết quả từ hệ thống ngoài, tên như **paymentAuthorized** có thể phù hợp vì nó mô tả sự kiện đã xảy ra. Không cần ép mọi loại tín hiệu theo một mẫu tên duy nhất; điều quan trọng là tên phản ánh đúng nguồn phát và ý nghĩa.

Đặc biệt, event ID của Spring Web Flow không tự động đồng nghĩa với một domain event được phát lên hệ thống. **confirmOrder** trong flow là tín hiệu yêu cầu flow xử lý xác nhận. Domain event như **OrderConfirmed** thường biểu đạt sự thật rằng đơn hàng đã được xác nhận thành công. Chỉ phát domain event sau khi nghiệp vụ thực sự hoàn tất theo quy tắc của ứng dụng.

## Tên event và validation

Tên event thể hiện ý định, còn validation xác định dữ liệu có đáp ứng điều kiện để tiếp tục hay không. Không nên tạo các event như **validAddress**, **invalidAddress** chỉ để mô tả kết quả kiểm tra dữ liệu do form gửi lên.

Ví dụ, người dùng phát **saveShippingAddress**. Flow tiếp nhận yêu cầu lưu; validation kiểm tra mã bưu chính, địa chỉ và các trường bắt buộc. Nếu dữ liệu chưa hợp lệ, giao diện hiển thị lỗi và flow giữ người dùng ở bước nhập để sửa. Khi hợp lệ, transition mới đưa hành trình tới bước xem lại theo cấu hình.

Cách phân tách này giữ cho event ID ổn định khi quy tắc validation thay đổi. Việc thêm một trường bắt buộc không cần làm đổi ý định **saveShippingAddress** thành một event mới.

## Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhiều nút khác ý nghĩa cùng phát **submit** | Flow không phân biệt được lưu nháp và gửi chính thức | Đặt event riêng như **saveDraft** và **submitRegistration** |
| Event ID không khớp thuộc tính **on** | Không có transition mong muốn được chọn | Đối chiếu chính xác chuỗi ở view và flow |
| Tên event phụ thuộc chữ trên nút | Đổi ngôn ngữ hoặc nội dung giao diện có thể làm sai hợp đồng | Giữ event ID ổn định, dịch nhãn giao diện riêng |
| Dùng tên trang đích làm event | Thay đổi bố cục flow làm tên event mất ý nghĩa | Đặt tên theo hành động người dùng |
| Dùng một event cho cả quay lại và hủy | Hai hành động có hậu quả nghiệp vụ khác nhau bị nhập làm một | Phân biệt **editShippingAddress** và **cancelCheckout** |
| Xem event ID như quyền truy cập | Request tự tạo có thể gửi event không phù hợp | Kiểm tra trạng thái và quyền ở flow/service trước khi thực hiện nghiệp vụ |

Tên tốt không thay thế kiểm tra nghiệp vụ. Người dùng có thể tự gửi request với event ID bất kỳ; vì vậy các transition nhạy cảm như xác nhận thanh toán, hủy đơn hoặc phê duyệt phải được kiểm tra quyền và điều kiện ở phía máy chủ. Không được dựa vào việc nút có bị ẩn hay không để quyết định người dùng có được phép thực hiện hành động.

## Quy trình thiết kế và rà soát event ID

Khi bắt đầu một flow mới hoặc cải thiện flow hiện tại, có thể dùng quy trình sau:

1. **Liệt kê state.** Ghi lại các màn hình hoặc bước xử lý mà flow có thể đang đứng.
2. **Liệt kê ý định ở mỗi state.** Hỏi người dùng có thể yêu cầu điều gì tại bước này: lưu, sửa, xác nhận, hủy, thử lại hay gửi hồ sơ.
3. **Đặt tên cho từng ý định.** Dùng động từ và đối tượng nghiệp vụ; tránh tên nút hoặc tên trang.
4. **Kiểm tra sự khác biệt về hậu quả.** Nếu hai thao tác dẫn tới hành vi nghiệp vụ khác nhau, chúng cần event riêng.
5. **Ánh xạ event vào transition.** Đảm bảo ID phát từ view khớp chính xác với giá trị **on** trong flow definition.
6. **Rà soát nguồn phát.** Phân biệt event người dùng, kết quả từ dịch vụ ngoài và tín hiệu kỹ thuật.
7. **Kiểm thử các nhánh.** Thử lưu, sửa, hủy, xác nhận, dữ liệu không hợp lệ và request có event không được hỗ trợ.

Một bảng từ vựng event nhỏ được lưu cùng tài liệu thiết kế hoặc trong phần mô tả flow sẽ giúp nhóm duy trì quy ước khi thêm state và subflow. Bảng này nên ghi event ID, ý nghĩa, state có thể phát, nguồn phát và transition dự kiến.

## Kiểm thử hợp đồng giữa view và flow

Kiểm thử cần xác nhận cả hai đầu của hợp đồng event:

- View gửi đúng event ID khi người dùng chọn từng hành động.
- Flow có transition phù hợp tại state hiện tại.
- Event không bỏ qua validation hoặc kiểm tra quyền.
- Hai ý định khác nhau như sửa địa chỉ và hủy đơn đi tới nhánh xử lý khác nhau.
- Đổi nhãn hoặc ngôn ngữ giao diện không làm thay đổi event ID.
- Event không hợp lệ hoặc không được hỗ trợ được xử lý theo cơ chế lỗi đã thiết kế.

Ví dụ với flow đặt hàng, có thể kiểm tra rằng **saveShippingAddress** đưa người dùng tới màn hình xem lại khi dữ liệu hợp lệ; dữ liệu không hợp lệ hiển thị lỗi tại bước nhập; **editShippingAddress** quay lại bước địa chỉ; **cancelCheckout** kết thúc theo outcome hủy; và **confirmOrder** chỉ gọi dịch vụ đặt hàng sau khi các điều kiện nghiệp vụ được đáp ứng.

Khi lỗi xảy ra, hãy đối chiếu event ID thực tế trong request với thuộc tính **on** của state hiện tại. Nếu hai chuỗi không khớp, kiểm tra tên nút hoặc thành phần view phát event. Nếu chuỗi khớp nhưng hành vi sai, kiểm tra transition, action, điều kiện và trạng thái hiện tại. Cách lần theo này giúp xác định lỗi nằm ở hợp đồng giao diện-flow hay ở logic nghiệp vụ.

## Ghi nhớ

- Event ID do người dùng phát ra nên mô tả ý định như **saveShippingAddress**, **confirmOrder** hoặc **cancelCheckout**.
- Transition là quy tắc xử lý event tại state hiện tại; event không phải tên state đích.
- Giữ event ID ổn định, nhất quán về chữ hoa/thường và độc lập với nhãn giao diện.
- Phân biệt ý định người dùng với kết quả từ hệ thống ngoài và tín hiệu kỹ thuật.
- Validation, phân quyền và điều kiện nghiệp vụ vẫn phải được kiểm tra ở phía máy chủ; tên event chỉ làm rõ ý nghĩa của yêu cầu.

