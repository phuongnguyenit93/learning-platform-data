# Chọn scope theo thời gian sống và quyền sử dụng dữ liệu

## 1. Chọn scope bắt đầu từ vòng đời và người sở hữu dữ liệu

Trong Spring Web Flow, một hành trình có thể đi qua nhiều state và nhiều HTTP request. Dữ liệu được nhập ở màn hình đầu có thể còn cần ở màn hình xác nhận; một thông báo chỉ cần hiển thị ở màn hình kế tiếp; một giá trị khác chỉ có ý nghĩa trong lúc xử lý một request. Nếu đặt tất cả dữ liệu vào cùng một nơi, flow dễ giữ dữ liệu quá lâu, làm rò rỉ trạng thái giữa các hành trình hoặc khiến dữ liệu biến mất trước khi cần dùng.

Spring Web Flow cung cấp các scope để giới hạn vòng đời và phạm vi truy cập của dữ liệu trong một flow execution. Các scope thường dùng gồm:

- `requestScope`: dữ liệu chỉ cần trong request đang xử lý.
- `flashScope`: dữ liệu ngắn hạn cần chuyển tới view-state kế tiếp.
- `viewScope`: dữ liệu chỉ thuộc một view-state.
- `flowScope`: dữ liệu thuộc toàn bộ một flow execution.
- `conversationScope`: dữ liệu dùng chung trong một conversation, bao gồm flow cha và các subflow của conversation đó.

Bài học này thuộc chương **Dữ liệu và scope** của module **SPRING_WEB_FLOW**. Mục tiêu là chọn scope theo thời gian sống và quyền sử dụng dữ liệu khi thiết kế hành trình nhiều bước bằng state, event, transition và subflow. Việc chọn đúng scope hỗ trợ form binding, validation, tích hợp Spring MVC, kiểm thử và phục hồi flow khi có lỗi.

Hãy bắt đầu bằng hai câu hỏi:

1. **Dữ liệu cần tồn tại đến khi nào?** Một request, một view-state, toàn bộ flow hay cả conversation?
2. **Ai cần truy cập dữ liệu đó?** Chỉ xử lý hiện tại, một màn hình, flow hiện tại hay flow cha cùng subflow?

Chọn scope hẹp nhất đáp ứng được cả hai yêu cầu. Dữ liệu cần tồn tại lâu hơn hoặc được chia sẻ rộng hơn phải có lý do nghiệp vụ rõ ràng.

## 2. Vòng đời và phạm vi truy cập của từng scope

### 2.1. requestScope — trong một HTTP request

`requestScope` tồn tại trong thời gian xử lý một HTTP request. Khi request kết thúc, dữ liệu trong scope này không được giữ lại để dùng ở request tiếp theo.

Dùng scope này cho dữ liệu tạm chỉ phục vụ lần xử lý hiện tại, chẳng hạn:

- Giá trị trung gian được tính trong một action.
- Thông tin chẩn đoán hoặc kết quả phụ trợ chỉ dùng trong request.
- Dữ liệu tạm để chuẩn bị nội dung phản hồi hiện tại.

Không đặt bản nháp biểu mẫu cần đi qua nhiều màn hình vào `requestScope`. Mỗi lần người dùng bấm nút, trình duyệt thường gửi một request mới; dữ liệu chỉ có trong request trước sẽ không còn ở request sau nếu không được lưu vào scope có vòng đời dài hơn hoặc kho dữ liệu phù hợp.

### 2.2. flashScope — chuyển dữ liệu ngắn hạn tới view-state

`flashScope` dùng để chuyển dữ liệu ngắn hạn tới view-state kế tiếp. Dữ liệu trong scope này được làm sạch khi flow đi vào một view-state, vì vậy nó phù hợp với thông tin chỉ cần hiển thị một lần hoặc trong một lần chuyển màn hình.

Ví dụ:

- Thông báo “Đã lưu bản nháp”.
- Thông tin kết quả của một action cần hiển thị ngay sau action đó.
- Cảnh báo ngắn gọn sau khi xử lý một event.

Không dùng `flashScope` để giữ dữ liệu biểu mẫu qua nhiều bước. Nếu người dùng cần quay lại màn hình trước và tiếp tục chỉnh sửa bản nháp, dữ liệu đó cần ở `viewScope` hoặc `flowScope` tùy phạm vi.

### 2.3. viewScope — trong một view-state

`viewScope` được tạo khi flow đi vào một view-state và được kết thúc khi flow rời view-state đó. Dữ liệu phù hợp là dữ liệu gắn với một màn hình cụ thể, chẳng hạn:

- Bộ lọc hoặc lựa chọn tạm của màn hình tìm kiếm.
- Dữ liệu phụ trợ chỉ phục vụ một trang.
- Trạng thái hiển thị hoặc mô hình biểu mẫu không cần dùng sau khi rời màn hình.

Nếu flow rời view-state rồi quay lại, không nên giả định dữ liệu cũ trong `viewScope` vẫn còn. Khi dữ liệu cần được giữ qua nhiều màn hình, hãy dùng `flowScope` hoặc lưu vào nguồn dữ liệu bền vững.

### 2.4. flowScope — trong một flow execution

`flowScope` tồn tại từ khi một flow execution bắt đầu đến khi flow kết thúc. Đây là lựa chọn thường dùng cho dữ liệu nghiệp vụ tạm thời được tích lũy qua nhiều bước, ví dụ:

- Bản nháp đặt chỗ.
- Thông tin người nhận và địa chỉ giao hàng trong quy trình checkout.
- Kết quả lựa chọn sản phẩm trước khi xác nhận.
- Các giá trị cần có ở nhiều view-state của cùng một flow.

Mỗi flow execution có `flowScope` riêng. Hai người dùng chạy cùng flow definition, hoặc một người dùng mở hai tab tạo hai execution độc lập, không nên dùng chung bản nháp của nhau.

Flow scope không phải kho lưu trữ lâu dài. Khi flow kết thúc, scope này kết thúc. Nếu đơn hàng đã xác nhận cần được truy xuất ở lần đăng nhập sau, hãy lưu nó qua repository hoặc dịch vụ nghiệp vụ.

### 2.5. conversationScope — trong conversation cấp cao nhất

`conversationScope` tồn tại trong thời gian conversation cấp cao nhất của Web Flow. Flow cha và các subflow thuộc cùng conversation có thể dùng chung dữ liệu ở scope này.

Scope này phù hợp khi một giá trị thực sự cần được chia sẻ giữa nhiều flow trong cùng hành trình, ví dụ:

- Mã định danh hành trình cần dùng ở flow cha và subflow.
- Kết quả đã được chọn trong một subflow và còn cần cho bước tiếp theo của flow cha.
- Thông tin điều phối tạm thời được nhiều phần của cùng conversation sử dụng.

`conversationScope` rộng hơn `flowScope`. Vì vậy, không đưa mọi dữ liệu vào đây chỉ để tránh truyền tham số. Dữ liệu không cần chia sẻ giữa flow cha và subflow nên ở `flowScope` hoặc scope hẹp hơn. Khi flow cấp cao nhất kết thúc, conversation kết thúc và dữ liệu tạm trong conversation scope cũng hết vòng đời.

## 3. Bảng so sánh để chọn nhanh

| Scope | Vòng đời | Phạm vi sử dụng phù hợp | Ví dụ |
| --- | --- | --- | --- |
| `requestScope` | Một HTTP request | Lần xử lý hiện tại | Kết quả phụ trợ của action |
| `flashScope` | Chuyển tiếp ngắn tới view-state kế tiếp | Thông báo ngắn hạn | “Đã lưu thành công” |
| `viewScope` | Một view-state | Một màn hình | Bộ lọc tìm kiếm của trang |
| `flowScope` | Một flow execution | Các bước trong cùng flow | Bản nháp checkout |
| `conversationScope` | Conversation cấp cao nhất | Flow cha và các subflow cùng conversation | Mã tham chiếu hành trình |

Có thể dùng quy tắc lựa chọn sau:

~~~mermaid
flowchart TD
    A["Có dữ liệu cần lưu trong flow?"] --> B{"Chỉ cần trong request hiện tại?"}
    B -- "Có" --> C["requestScope"]
    B -- "Không" --> D{"Chỉ cần chuyển tới view-state kế tiếp?"}
    D -- "Có" --> E["flashScope"]
    D -- "Không" --> F{"Chỉ thuộc một view-state?"}
    F -- "Có" --> G["viewScope"]
    F -- "Không" --> H{"Nhiều flow trong cùng conversation cùng cần?"}
    H -- "Có" --> I["conversationScope"]
    H -- "Không" --> J["flowScope"]
~~~

Nếu dữ liệu cần tồn tại sau khi flow kết thúc, câu trả lời không phải là chọn scope rộng hơn. Hãy lưu dữ liệu vào cơ sở dữ liệu hoặc dịch vụ lưu trữ có vòng đời phù hợp.

## 4. Ví dụ: quy trình đặt chỗ nhiều bước

Giả sử một flow đặt chỗ gồm các bước nhập thông tin hành khách, chọn dịch vụ, xem lại và xác nhận. Bản nháp cần được giữ khi người dùng chuyển qua lại giữa các màn hình. Một thông báo xác nhận chỉ cần hiển thị ở trang kết quả. Bộ lọc tìm kiếm chỉ cần trong màn hình chọn dịch vụ.

Có thể phân chia như sau:

| Dữ liệu | Scope hoặc nơi lưu | Lý do |
| --- | --- | --- |
| `bookingDraft` | `flowScope` | Cần qua nhiều view-state trong cùng flow |
| Bộ lọc tạm trên trang chọn dịch vụ | `viewScope` | Chỉ có ý nghĩa ở màn hình đó |
| Thông báo “Đã lưu bản nháp” | `flashScope` | Chỉ cần hiển thị ở view-state kế tiếp |
| Kết quả tính toán chỉ dùng trong request | `requestScope` | Không cần giữ sau request |
| Mã hành trình được flow cha và subflow cùng dùng | `conversationScope` | Nhiều flow trong cùng conversation cần truy cập |
| Bản đặt chỗ đã xác nhận | Repository/cơ sở dữ liệu | Phải tồn tại sau khi flow kết thúc |

Ví dụ flow XML rút gọn:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">

    <var name="bookingDraft" class="com.example.booking.BookingDraft"/>

    <on-start>
        <evaluate
            expression="bookingService.createDraft(currentUser.id)"
            result="flowScope.bookingDraft"/>
    </on-start>

    <view-state id="passenger" view="booking/passenger">
        <transition on="next" to="services"/>
    </view-state>

    <view-state id="services" view="booking/services">
        <transition on="back" to="passenger"/>
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="confirm" to="complete"/>
        <transition on="edit" to="passenger"/>
    </view-state>

    <end-state id="complete"/>
</flow>
~~~

Trong ví dụ, `bookingDraft` được tạo khi flow bắt đầu và đặt vào `flowScope`. Các view-state có thể tiếp tục sử dụng bản nháp đó. Khi người dùng quay từ `review` về `passenger`, dữ liệu vẫn thuộc cùng flow execution nên không bị mất chỉ vì đã rời một view-state.

Nếu chỉ đặt `bookingDraft` trong `viewScope` của `passenger`, dữ liệu có thể không còn khi flow rời màn hình đó. Nếu đặt nó trong `requestScope`, dữ liệu không còn sau request đầu tiên. Cả hai đều không đáp ứng vòng đời của bản nháp nhiều bước.

## 5. Chia sẻ dữ liệu giữa flow cha và subflow

Subflow thường đại diện cho một phần hành trình có thể tái sử dụng, ví dụ chọn địa chỉ, xác minh thông tin hoặc chọn phương thức giao hàng. Khi thiết kế dữ liệu cho subflow, cần phân biệt dữ liệu thuộc riêng subflow với dữ liệu thuộc toàn bộ conversation.

- Dữ liệu chỉ phục vụ các state bên trong subflow nên thuộc `flowScope` của subflow.
- Dữ liệu flow cha cần nhận lại nên được truyền vào hoặc trả ra qua input/output mapping phù hợp.
- Dữ liệu thực sự cần được cả flow cha và subflow truy cập trong suốt conversation có thể đặt trong `conversationScope`.

Ví dụ, flow checkout có `bookingDraft` trong flow scope. Nó gọi subflow chọn địa chỉ. Subflow nhận mã khách hàng làm input và trả về địa chỉ đã chọn. Flow cha gán kết quả vào `bookingDraft.address`. Cách này thể hiện rõ dữ liệu nào thuộc trách nhiệm của subflow và dữ liệu nào được flow cha sở hữu.

Không nên chuyển toàn bộ đối tượng lớn vào conversation scope chỉ để tránh khai báo input/output mapping. Truyền dữ liệu tường minh giúp subflow dễ kiểm thử, tái sử dụng và ít phụ thuộc vào cấu trúc bên trong của flow cha.

## 6. Scope quyết định vòng đời, không quyết định quyền được phép xem dữ liệu

Một nhầm lẫn nguy hiểm là cho rằng dữ liệu nằm trong `flowScope` hoặc `conversationScope` thì chỉ người dùng hợp lệ mới có thể truy cập. Scope xác định nơi dữ liệu được giữ và thời gian dữ liệu tồn tại; nó **không thay thế cơ chế xác thực và phân quyền**.

Ví dụ, một flow có thể giữ `customerId` trong `flowScope`. Điều đó không chứng minh người đang gửi request có quyền xem hoặc sửa dữ liệu của khách hàng đó. Trước khi đọc hoặc cập nhật dữ liệu nghiệp vụ, service vẫn phải xác thực người dùng và kiểm tra quyền sở hữu tài nguyên.

Nên áp dụng các nguyên tắc sau:

- Lấy danh tính người dùng từ cơ chế xác thực của ứng dụng, không tin một `userId` do trình duyệt tự gửi lên.
- Kiểm tra quyền truy cập tại service hoặc tầng nghiệp vụ mỗi khi đọc, sửa, xác nhận hay hủy dữ liệu.
- Kiểm tra người dùng hiện tại có quyền thao tác trên booking/order được tham chiếu hay không.
- Không xem flow execution key, conversation ID hoặc tên scope là bằng chứng phân quyền.
- Không đưa mật khẩu, access token, bí mật tích hợp hoặc dữ liệu thanh toán nhạy cảm vào scope chỉ để tiện truy cập.
- Chỉ lưu dữ liệu tối thiểu cần thiết trong flow state; dữ liệu nhạy cảm hoặc lớn nên được quản lý ở nơi phù hợp và chỉ tham chiếu bằng ID.

Có thể phân biệt ba khái niệm:

| Khái niệm | Câu hỏi nó trả lời | Cơ chế |
| --- | --- | --- |
| Vòng đời | Dữ liệu tồn tại bao lâu? | Scope |
| Phạm vi truy cập trong flow | Phần nào của flow cần dữ liệu? | Scope, input/output mapping |
| Quyền nghiệp vụ | Người dùng hiện tại có được thao tác không? | Authentication, authorization, kiểm tra quyền sở hữu |

Nếu một subflow có thể truy cập `conversationScope`, điều đó chỉ có nghĩa subflow thuộc cùng conversation có thể dùng dữ liệu ở đó. Service vẫn cần kiểm tra quyền người dùng trước khi thực hiện hành động có ảnh hưởng đến dữ liệu thật.

## 7. Phân biệt scope của Web Flow với scope của Spring bean

Tên gọi có thể gây nhầm lẫn. Scope của Spring Web Flow dùng để quản lý dữ liệu của một flow execution hoặc conversation. Scope của Spring bean xác định vòng đời instance bean do container quản lý.

| Khái niệm | Ví dụ | Mục đích |
| --- | --- | --- |
| Web Flow `flowScope` | `flowScope.bookingDraft` | Giữ dữ liệu của một flow execution |
| Web Flow `conversationScope` | `conversationScope.journeyId` | Chia sẻ dữ liệu trong một conversation |
| Spring bean `singleton` | `@Service BookingService` | Một instance bean trong một ApplicationContext |
| Spring bean `request` | Bean được khai báo request-scoped | Một instance trong HTTP request |
| Spring bean `session` | Bean được khai báo session-scoped | Một instance trong HTTP session |

Một service singleton có thể được nhiều flow execution gọi đồng thời. Vì vậy, service không nên giữ bản nháp hiện tại của người dùng trong field mutable. Hãy truyền bản nháp vào phương thức hoặc lưu nó trong scope phù hợp của flow.

HTTP session cũng không đồng nghĩa với `conversationScope`. Một session có thể chứa nhiều flow execution, chẳng hạn khi người dùng mở nhiều tab. Mỗi execution cần có trạng thái riêng; conversation scope là phạm vi dữ liệu của một conversation Web Flow cụ thể, có thể chia sẻ với các subflow của nó.

## 8. Những sai lầm thường gặp khi chọn scope

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt bản nháp nhiều bước trong `requestScope` | Dữ liệu mất ở request tiếp theo | Dùng `flowScope` |
| Đặt thông báo một lần trong `flowScope` | Thông báo cũ có thể còn lâu hơn cần thiết | Dùng `flashScope` |
| Đặt dữ liệu chỉ phục vụ một trang trong `conversationScope` | Dữ liệu tồn tại và được chia sẻ rộng hơn cần thiết | Dùng `viewScope` |
| Dùng `conversationScope` thay cho input/output mapping | Subflow phụ thuộc ngầm vào dữ liệu của flow cha | Truyền dữ liệu tường minh; chỉ chia sẻ conversation khi có lý do |
| Lưu dữ liệu nghiệp vụ lâu dài trong `flowScope` | Dữ liệu biến mất khi flow kết thúc | Lưu qua repository hoặc dịch vụ dữ liệu |
| Tin scope là cơ chế phân quyền | Người dùng có thể thao tác tài nguyên không thuộc quyền của họ nếu service không kiểm tra | Kiểm tra danh tính và quyền sở hữu ở tầng nghiệp vụ |
| Dùng field mutable trong service singleton để giữ dữ liệu hiện tại | Các request hoặc flow có thể ghi đè dữ liệu của nhau | Truyền dữ liệu qua tham số hoặc scope riêng của execution |

## 9. Kiểm thử vòng đời và quyền truy cập

Kiểm thử scope cần xác nhận dữ liệu còn tồn tại đúng thời điểm và không thể được sử dụng sai phạm vi.

### 9.1. Kiểm thử vòng đời

- Ghi dữ liệu vào `requestScope`, kết thúc request và xác nhận request sau không phụ thuộc giá trị cũ.
- Ghi thông báo vào `flashScope`, đi vào view-state kế tiếp và xác nhận thông báo được dùng đúng một lần theo vòng đời flash.
- Ghi dữ liệu vào `viewScope`, rời view-state và xác nhận dữ liệu của view không còn được giả định là tồn tại.
- Ghi bản nháp vào `flowScope`, đi qua nhiều transition và xác nhận dữ liệu vẫn còn cho đến khi flow kết thúc.
- Ghi giá trị vào `conversationScope`, gọi subflow và xác nhận các flow thuộc cùng conversation có thể dùng giá trị đó; kết thúc flow cấp cao nhất và xác nhận conversation kết thúc.

### 9.2. Kiểm thử cô lập nhiều execution

Khởi chạy hai flow execution từ cùng một flow definition. Gán hai bản nháp khác nhau, sau đó gửi event và chuyển state xen kẽ. Mỗi execution phải tiếp tục với đúng bản nháp của nó.

Bổ sung tình huống cùng một người dùng mở hai tab. Nếu hai tab đại diện cho hai execution độc lập, dữ liệu tạm của tab này không được ghi đè dữ liệu của tab kia.

### 9.3. Kiểm thử phân quyền

Tạo người dùng A và B cùng truy cập một flow. Xác nhận:

- A chỉ đọc hoặc cập nhật booking mà A được phép thao tác.
- B không thể dùng ID hoặc execution key của A để truy cập dữ liệu của A.
- Thay đổi `customerId` trong dữ liệu đầu vào không vượt qua kiểm tra quyền sở hữu.
- Subflow không bỏ qua kiểm tra phân quyền chỉ vì dữ liệu nằm trong `conversationScope`.

### 9.4. Kiểm thử phục hồi

Kiểm tra hành vi khi session hết hạn, flow execution không còn tồn tại hoặc người dùng gửi lại một event cũ. Flow nên đưa ra thông báo có kiểm soát và hướng bắt đầu lại phù hợp. Không nên khôi phục một bản nháp nhạy cảm chỉ dựa trên dữ liệu do trình duyệt gửi lên.

## 10. Quy trình quyết định trước khi thêm một biến vào flow

Trước khi thêm biến hoặc đối tượng vào flow, hãy đi theo các bước sau:

1. **Xác định người sở hữu dữ liệu.** Dữ liệu thuộc một request, một màn hình, một flow execution, một conversation hay là dữ liệu nghiệp vụ bền vững?
2. **Xác định thời điểm cuối cùng cần dùng.** Sau request, sau view-state, sau flow hay sau khi conversation kết thúc?
3. **Xác định những thành phần cần truy cập.** Chỉ action hiện tại, view hiện tại, các state trong flow hay cả subflow?
4. **Chọn scope hẹp nhất.** Chỉ mở rộng phạm vi khi có yêu cầu chia sẻ cụ thể.
5. **Kiểm tra quyền nghiệp vụ.** Xác định service nào chịu trách nhiệm kiểm tra người dùng và quyền sở hữu.
6. **Đánh giá dữ liệu được giữ.** Loại bỏ bí mật, dữ liệu quá lớn và dữ liệu có thể truy vấn lại khi không cần thiết.
7. **Viết kiểm thử.** Kiểm tra vòng đời, cô lập nhiều execution, subflow và quyền truy cập.

Ví dụ, bản nháp đặt chỗ được giữ trong `flowScope`; bộ lọc của màn hình chọn dịch vụ ở `viewScope`; thông báo kết quả ở `flashScope`; mã hành trình chia sẻ giữa flow cha và subflow ở `conversationScope`; bản đặt chỗ đã xác nhận được lưu qua repository. Service kiểm tra người dùng hiện tại có quyền thao tác trên bản đặt chỗ trước khi cập nhật.

## 11. Tự kiểm tra

- Dữ liệu chỉ dùng trong một request nên đặt ở đâu? `requestScope`.
- Thông báo cần hiển thị ở view-state kế tiếp nên đặt ở đâu? `flashScope`.
- Bộ lọc chỉ phục vụ một màn hình nên đặt ở đâu? `viewScope`.
- Bản nháp cần đi qua nhiều state của cùng flow nên đặt ở đâu? Thường là `flowScope`.
- Dữ liệu được flow cha và subflow cùng sử dụng trong một conversation nên đặt ở đâu? `conversationScope`, nếu dữ liệu thực sự có vòng đời và phạm vi chia sẻ như vậy.
- Flow scope có đảm bảo người dùng sở hữu dữ liệu không? Không. Service phải kiểm tra quyền và quyền sở hữu.
- Đơn hàng đã xác nhận có nên chỉ lưu trong flow scope không? Không. Cần lưu qua kho dữ liệu bền vững.
- Hai execution có nên dùng chung bản nháp chỉ vì chúng chạy cùng flow definition không? Không. Mỗi execution phải giữ trạng thái riêng.

Chọn scope đúng giúp flow giữ dữ liệu vừa đủ lâu và chỉ trong phạm vi cần thiết. Kết hợp scope với kiểm tra quyền ở tầng nghiệp vụ giúp Spring Web Flow hỗ trợ các hành trình nhiều bước an toàn, dễ kiểm thử và dễ phục hồi hơn.

