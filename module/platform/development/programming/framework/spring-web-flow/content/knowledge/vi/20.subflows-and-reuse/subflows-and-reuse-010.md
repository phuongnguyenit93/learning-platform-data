# Tránh phụ thuộc ngầm vào biến của flow cha

## Bối cảnh và mục tiêu

Bài học thuộc chương **Subflow và tái sử dụng** của module `SPRING_WEB_FLOW`. Spring Web Flow mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow. Subflow giúp tách một phần hành trình thành flow có thể gọi lại ở nhiều nơi, chẳng hạn nhập địa chỉ, xác minh danh tính hoặc xử lý thanh toán. Để tái sử dụng an toàn, flow con cần có ranh giới dữ liệu rõ ràng và không được dựa vào những biến nội bộ mà flow cha tình cờ đang giữ.

Một subflow có thể hoạt động trong cùng flow execution với flow cha, nhưng mỗi flow session có flowScope riêng. Các flow session cùng execution có thể chia sẻ conversationScope; HttpSession cũng có thể được nhiều flow execution trong cùng phiên người dùng truy cập. Những vùng chia sẻ này dễ tạo ra phụ thuộc ngầm: flow con đọc một biến mà hợp đồng gọi không thể hiện, hoặc ghi đè dữ liệu mà flow cha và các subflow khác đang sử dụng.

Sau bài học, bạn có thể:

- Giải thích vì sao subflow cần hợp đồng input/output độc lập với biến nội bộ của flow cha.
- Phân biệt flowScope riêng của từng flow session với conversationScope dùng chung.
- Thiết kế input, output và event kết thúc để flow con có thể tái sử dụng.
- Tránh chia sẻ object mutable và dữ liệu qua HttpSession một cách ngầm định.
- Kiểm thử subflow từ nhiều flow cha khác nhau mà không phụ thuộc thứ tự chạy hay trạng thái còn sót lại.

## 1. Phụ thuộc ngầm là gì?

Một flow có phụ thuộc ngầm khi nó cần một giá trị hoặc hành vi từ bên ngoài nhưng không khai báo rõ trong hợp đồng của nó. Với subflow, tình huống thường gặp là flow con được viết dựa trên giả định rằng flow cha đã đặt sẵn một biến có tên cụ thể trong scope dùng chung.

Ví dụ, flow cha đặt mã đơn hàng vào conversationScope:

```xml
<on-start>
    <evaluate expression="flowScope.order.id"
              result="conversationScope.currentOrderId"/>
</on-start>

<subflow-state id="payment" subflow="payment">
    <transition on="paid" to="confirmation"/>
</subflow-state>
```

Flow con sau đó tự đọc biến đó:

```xml
<on-start>
    <evaluate expression="orderService.load(conversationScope.currentOrderId)"
              result="flowScope.order"/>
</on-start>
```

Flow `payment` có vẻ chạy được, nhưng nó chỉ hoạt động khi được gọi từ một flow cha biết phải tạo `conversationScope.currentOrderId`. Nếu một flow khác gọi `payment` mà quên thiết lập biến, subflow có thể nhận null, dùng nhầm giá trị còn sót lại hoặc thất bại ở thời điểm khó truy vết.

Phụ thuộc ngầm không chỉ xuất hiện ở conversationScope. Nó còn có thể nằm trong:

- Thuộc tính của HttpSession do một controller hoặc flow khác ghi.
- Biến static hoặc trạng thái mutable trong một Spring singleton.
- Một bean dùng chung mà flow con giả định đã được khởi tạo theo một thứ tự cụ thể.
- Một key request, cookie hoặc tham số URL mà flow con tự đọc thay vì nhận qua contract.
- Một object được truyền bằng tham chiếu rồi bị sửa ở nhiều nơi mà không có quy ước quyền sở hữu.

Điểm chung là người gọi không thể nhìn vào khai báo subflow để biết flow con cần dữ liệu gì, và người dùng subflow không thể xác định rõ kết quả nào sẽ được trả về.

## 2. Ranh giới scope giữa flow cha và flow con

Cần phân biệt các scope trước khi thiết kế cách truyền dữ liệu:

| Scope | Phạm vi | Ý nghĩa đối với subflow |
| --- | --- | --- |
| `requestScope` | Request hiện tại | Dữ liệu tạm của lần xử lý request; không phải kênh truyền trạng thái qua nhiều bước |
| `viewScope` | View state hiện tại | Dữ liệu phục vụ một màn hình trong flow session tương ứng |
| `flowScope` | Một flow session | Flow cha và mỗi subflow có flowScope riêng |
| `conversationScope` | Flow execution gốc | Các flow session thuộc cùng execution có thể cùng truy cập |
| HttpSession | Phiên người dùng Servlet | Có thể được nhiều execution và nhiều tab trong cùng phiên truy cập |

Khi flow cha gọi subflow, flow con có flow session riêng. Vì vậy, `flowScope.order` trong flow cha không tự động trở thành `flowScope.order` trong flow con. Tên biến giống nhau không làm cho hai vùng dữ liệu trở thành một.

Ngược lại, conversationScope được chia sẻ trong cùng flow execution. Nếu flow cha ghi `conversationScope.currentOrderId`, flow con có thể đọc nó. Đây là chia sẻ có thật, nhưng nếu việc đọc biến không được thể hiện trong input của subflow thì contract vẫn bị ẩn. Một người phát triển nhìn vào khai báo subflow sẽ không biết flow con cần `currentOrderId`.

HttpSession còn rộng hơn conversationScope: nhiều flow execution có thể cùng dùng một session. Dùng một key cố định như `session.currentOrder` làm kênh trao đổi giữa flow cha và con có thể gây xung đột giữa hai wizard mở ở hai tab.

Quy tắc thiết kế: dùng scope để quản lý vòng đời dữ liệu trong phạm vi đã xác định; dùng input/output để thể hiện dữ liệu đi qua ranh giới của subflow.

## 3. Khai báo input tường minh

Input là hợp đồng đầu vào của flow con. Mỗi input cần có tên ổn định, kiểu dữ liệu rõ ràng và quy tắc bắt buộc/tùy chọn phù hợp. Flow cha chịu trách nhiệm ánh xạ giá trị của nó vào input đó khi gọi subflow.

Ví dụ, subflow thanh toán chỉ cần mã đơn hàng:

**Flow cha:**

```xml
<subflow-state id="makePayment" subflow="payment">
    <input name="orderId" value="flowScope.orderId"/>

    <transition on="authorized" to="confirmation">
        <evaluate expression="currentEvent.attributes.paymentResult"
                  result="flowScope.paymentResult"/>
    </transition>

    <transition on="cancelled" to="editOrder"/>

    <transition on="declined" to="paymentProblem">
        <evaluate expression="currentEvent.attributes.reasonCode"
                  result="flowScope.paymentFailureCode"/>
    </transition>
</subflow-state>
```

**Flow con `payment`:**

```xml
<flow>
    <input name="orderId" type="long" required="true"/>

    <on-start>
        <evaluate expression="orderService.load(orderId)"
                  result="flowScope.order"/>
    </on-start>

    <!-- Các state nhập và xác nhận phương thức thanh toán -->

    <end-state id="authorized">
        <output name="paymentResult"
                value="flowScope.paymentResult"/>
    </end-state>

    <end-state id="cancelled"/>

    <end-state id="declined">
        <output name="reasonCode"
                value="flowScope.reasonCode"/>
    </end-state>
</flow>
```

Flow con khai báo `orderId` ngay tại đầu định nghĩa. Người đọc có thể biết subflow cần gì mà không cần tìm trong flow cha hoặc trong một biến dùng chung. Flow cha cũng thể hiện rõ giá trị nào được truyền vào.

Ví dụ trên minh họa hợp đồng input/output; cần bổ sung model, view state, action và cấu hình service tương ứng trong ứng dụng. Kiểu `long` phải phù hợp kiểu ID thực tế của dự án.

### Chọn dữ liệu đầu vào nhỏ và ổn định

Ưu tiên truyền những dữ liệu tối thiểu mà subflow cần:

- ID của entity thay vì toàn bộ object lớn nếu flow con có thể tải dữ liệu từ service.
- Một command/DTO chuyên biệt thay vì một object chứa cả trạng thái nội bộ của flow cha.
- Giá trị đã được xác thực ở mức phù hợp, nhưng vẫn để flow con kiểm tra điều kiện riêng mà nó chịu trách nhiệm.
- Các tham số có ý nghĩa nghiệp vụ rõ ràng, không dùng tên chung như `data`, `context` hoặc `payload` nếu không có schema giải thích.

Nếu flow con cần nhiều giá trị, có thể dùng một DTO input có cấu trúc. Tuy nhiên, DTO cần có hợp đồng rõ ràng, chỉ chứa dữ liệu subflow được phép dùng và có quy tắc tương thích khi thay đổi.

## 4. Trả kết quả bằng output và end-state event

Output là hợp đồng kết quả của flow con. Flow con công bố dữ liệu khi kết thúc bằng một end state; flow gọi nhận event có ID tương ứng với end state và có thể đọc các output qua thuộc tính của event.

Trong ví dụ thanh toán:

- End state `authorized` tạo event `authorized` và công bố `paymentResult`.
- End state `cancelled` tạo event `cancelled`, không cần output nếu không có kết quả nào cần trả.
- End state `declined` tạo event `declined` và công bố `reasonCode`.

Flow cha định nghĩa transition tương ứng trên subflow state. Nhờ vậy, luồng thành công, hủy và từ chối đều có ý nghĩa rõ ràng. Đừng buộc flow cha suy đoán kết quả bằng cách đọc một biến conversationScope sau khi subflow kết thúc.

Output nên được thiết kế theo kết quả nghiệp vụ:

| Kết quả subflow | Event | Output có thể trả |
| --- | --- | --- |
| Thanh toán được chấp thuận | `authorized` | Mã giao dịch, trạng thái thanh toán hoặc DTO kết quả |
| Người dùng hủy | `cancelled` | Thường không cần output |
| Thanh toán bị từ chối | `declined` | Mã lý do an toàn để flow cha chọn thông báo phù hợp |
| Dịch vụ tạm thời không sẵn sàng | `unavailable` | Mã lỗi phân loại hoặc thông tin cho nhánh thử lại |

Không nên trả toàn bộ object nội bộ của flow con nếu flow cha chỉ cần một vài giá trị. Output càng nhỏ và có ý nghĩa, mức độ phụ thuộc giữa hai flow càng thấp.

### Xử lý output ở flow cha

Flow cha đọc output qua event attributes trong transition của subflow state, sau đó lưu vào scope thuộc quyền sở hữu của nó:

```xml
<transition on="authorized" to="confirmation">
    <evaluate expression="currentEvent.attributes.paymentResult"
              result="flowScope.paymentResult"/>
</transition>
```

Khi chuyển state, flow cha sử dụng `flowScope.paymentResult` của chính nó. Flow con không cần biết tên biến nội bộ mà cha dùng để lưu kết quả. Nếu ngày mai flow cha đổi tên biến thành `flowScope.completedPayment`, định nghĩa flow con không cần thay đổi.

## 5. conversationScope: chỉ dùng khi chia sẻ là chủ đích

conversationScope hữu ích khi nhiều flow session trong cùng execution thực sự cần truy cập một dữ liệu chung. Ví dụ, một correlation ID phục vụ truy vết toàn bộ hành trình hoặc một context nghiệp vụ được định nghĩa rõ là dùng chung giữa checkout và subflow.

Tuy nhiên, việc dùng conversationScope nên được xem như một quyết định thiết kế công khai. Cần trả lời:

- Những flow nào được phép đọc giá trị?
- Flow nào được phép thay đổi?
- Giá trị được khởi tạo ở đâu và khi nào?
- Giá trị có thể null không?
- Khi subflow bị hủy hoặc lỗi, thay đổi đã ghi có cần hoàn tác không?
- Khi root flow kết thúc, dữ liệu có còn được tham chiếu ở nơi khác không?

Nếu một giá trị là bắt buộc để subflow hoạt động, hãy ưu tiên khai báo nó thành input. Nếu nhiều flow cần chia sẻ một đối tượng có vòng đời chung, có thể đặt đối tượng trong conversationScope nhưng cần ghi rõ hợp đồng chia sẻ và quyền cập nhật.

Ví dụ, correlation ID có thể được khởi tạo ở root flow và được nhiều flow con đọc. Nếu flow con cần nó như một phần hợp đồng của mình, cách truyền qua input vẫn làm yêu cầu rõ ràng hơn. conversationScope có thể được dùng cho thông tin truy vết dùng chung khi kiến trúc đã xác định rõ phạm vi.

Không dùng conversationScope chỉ để tránh phải khai báo input/output. Khi mọi flow đều có thể đọc và sửa mọi biến chung, việc thay đổi một flow có thể phá vỡ các flow khác mà không có lỗi cấu hình dễ nhận biết.

## 6. Tránh chia sẻ object mutable qua ranh giới subflow

Một input có thể là giá trị nguyên thủy, ID, DTO hoặc object nghiệp vụ. Khi truyền một object mutable, không nên mặc định rằng framework tạo một bản sao độc lập cho flow con. Tùy cách thực thi, biểu thức input có thể trả về chính object đang được flow cha giữ; nếu flow con sửa object đó, thay đổi có thể xuất hiện ở phía cha.

Ví dụ rủi ro:

```xml
<subflow-state id="editAddress" subflow="address">
    <input name="order" value="flowScope.order"/>
    <transition on="saved" to="review"/>
</subflow-state>
```

Nếu flow con nhận object `order` và sửa trực tiếp địa chỉ trên object đó trước khi người dùng xác nhận, flow cha có thể quan sát thay đổi ngay cả khi người dùng hủy subflow. Kết quả này làm mờ ranh giới quyền sở hữu và khiến rollback khó dự đoán.

Các lựa chọn an toàn hơn:

1. Truyền `orderId`; flow con tải dữ liệu cần thiết và tạo bản nháp riêng.
2. Truyền một DTO chỉ chứa field cần chỉnh sửa, rồi trả DTO đã xác nhận qua output.
3. Tạo bản sao có chủ đích trước khi gọi subflow nếu nghiệp vụ yêu cầu chỉnh sửa bản nháp.
4. Chỉ dùng object chung khi chia sẻ mutable state là chủ đích, có quy tắc cập nhật và kiểm thử rõ ràng.

Đặc biệt, không đưa entity đang được quản lý bởi persistence context vào nhiều flow rồi để các flow cùng sửa mà không xác định thời điểm commit. Subflow không thay thế transaction boundary. Flow cha nên quyết định thời điểm lưu thay đổi chính thức hoặc gọi service nghiệp vụ chịu trách nhiệm transaction.

## 7. Không dùng HttpSession làm kênh trao đổi riêng cho subflow

HttpSession thuộc phiên người dùng, không thuộc một flow execution cụ thể. Hai tab trình duyệt thường dùng cùng session cookie. Nếu mỗi lần gọi subflow đều ghi dữ liệu vào key cố định như `currentPayment`, execution ở tab này có thể ghi đè dữ liệu ở tab khác.

Ví dụ không nên dùng:

```java
request.getSession().setAttribute("currentOrder", order);
```

rồi để flow con đọc `currentOrder` mà không nhận input. Flow con sẽ phụ thuộc vào một giá trị được thiết lập ở đâu đó trong cùng phiên. Nếu có nhiều execution đồng thời, giá trị có thể không thuộc flow đang xử lý.

Nếu dữ liệu thật sự thuộc cấp người dùng, chẳng hạn locale hoặc tùy chọn giao diện, HttpSession có thể phù hợp. Nếu dữ liệu thuộc một hành trình, hãy giữ nó trong flowScope/conversationScope hoặc truyền qua input/output. Nếu buộc phải lưu một dữ liệu execution-specific ngoài flow, key phải được phân vùng theo execution và có quy tắc dọn dẹp; nhưng đó là một cơ chế lưu trữ riêng cần thiết kế, không phải cách thay thế contract của subflow.

## 8. Tách trách nhiệm để subflow có thể tái sử dụng

Một subflow dễ tái sử dụng khi nó tập trung vào một nhiệm vụ có ranh giới rõ ràng. Ví dụ, subflow `address` nên chịu trách nhiệm thu thập và xác thực địa chỉ. Nó không nên tự quyết định flow cha đang ở bước checkout nào, hoặc tự chuyển sang state `payment` của một flow cụ thể.

| Trách nhiệm | Thuộc về đâu |
| --- | --- |
| Quyết định khi nào cần thu thập địa chỉ | Flow cha |
| Cung cấp customer ID hoặc địa chỉ khởi tạo | Input của subflow |
| Hiển thị form, bind và validate địa chỉ | Subflow |
| Quyết định nhánh thành công/hủy/lỗi | End state của subflow và transition của flow cha |
| Lưu địa chỉ vào đơn hàng chính thức | Service nghiệp vụ hoặc flow cha theo transaction design |
| Chọn state kế tiếp sau khi địa chỉ được xác nhận | Flow cha |

Cùng một subflow có thể được gọi từ flow đăng ký, flow checkout và flow quản lý hồ sơ. Mỗi flow cha có thể ánh xạ input khác nhau và xử lý output theo nhu cầu riêng, trong khi flow con giữ một contract ổn định.

Ví dụ:

- Flow đăng ký truyền `accountId` và nhận `verifiedAddress`.
- Flow checkout truyền `orderId` và nhận `shippingAddress`.
- Flow hồ sơ truyền `customerId` và nhận `updatedAddress`.

Nếu ba flow cha cần cùng một khái niệm dữ liệu, có thể thống nhất DTO input/output hoặc dùng tên input chung. Nhưng không nên để flow con đoán nguồn gọi hoặc đọc biến riêng của một flow cha cụ thể.

## 9. Quản lý thay đổi contract

Subflow có thể được nhiều flow cha sử dụng. Vì vậy, thay đổi input/output cần được xem như thay đổi API nội bộ.

Khi thay đổi contract:

- Thêm input bắt buộc mới có thể làm các flow cha hiện tại không khởi chạy được.
- Đổi tên input hoặc output có thể làm binding của flow cha bị sai.
- Đổi kiểu dữ liệu có thể gây lỗi chuyển đổi hoặc lỗi expression.
- Đổi ID end state làm thay đổi event mà flow cha phải xử lý.
- Xóa một output có thể làm transition action ở flow cha không tìm thấy event attribute.

Nên ưu tiên thay đổi tương thích:

1. Thêm output tùy chọn nếu flow cha cũ không cần nó.
2. Nếu thêm input, cân nhắc giá trị mặc định hoặc cho phép tùy chọn trong giai đoạn chuyển tiếp.
3. Nếu cần đổi tên, hỗ trợ contract cũ trong một giai đoạn hoặc cập nhật đồng bộ mọi caller.
4. Ghi rõ ý nghĩa, kiểu, điều kiện null và vòng đời của mỗi input/output.
5. Có test cho từng flow cha đang sử dụng subflow.

Không nên thay đổi âm thầm ý nghĩa của một input giữ nguyên tên. Ví dụ, `customerId` trước đây là ID người dùng nhưng sau đó lại được hiểu là ID tài khoản thanh toán. Dù flow vẫn khởi chạy, hành vi nghiệp vụ có thể sai.

## 10. Kiểm thử để phát hiện phụ thuộc ngầm

Kiểm thử subflow độc lập cần khởi chạy nó với đúng input contract và xác minh các output/end event. Sau đó, kiểm thử tích hợp từ nhiều flow cha khác nhau để phát hiện giả định bị ẩn.

| Ca kiểm thử | Cách thực hiện | Điều cần xác minh |
| --- | --- | --- |
| Thiếu input bắt buộc | Gọi subflow mà không cung cấp `orderId` | Flow không âm thầm lấy dữ liệu từ conversationScope hoặc HttpSession |
| Input sai kiểu | Truyền giá trị không chuyển được sang kiểu khai báo | Lỗi được phát hiện tại ranh giới input |
| Hai caller khác nhau | Gọi subflow từ checkout và profile | Subflow hoạt động với contract chung, không đọc biến riêng của caller |
| Output thành công | Kết thúc bằng end state thành công | Flow cha nhận đúng event và output |
| Nhánh hủy | Kết thúc bằng end state cancel | Flow cha nhận event hủy và không xử lý output thành công |
| Nhánh lỗi nghiệp vụ | Kết thúc bằng end state lỗi đã định nghĩa | Flow cha đi đúng nhánh phục hồi |
| FlowScope cô lập | Đặt biến cùng tên ở cha và con | Hai flowScope độc lập, không ghi đè nhau |
| Conversation có chủ đích | Đọc giá trị chia sẻ trong cùng execution | Chỉ những flow session thuộc execution đó nhìn thấy dữ liệu |
| Hai execution cùng HttpSession | Mở hai wizard ở hai tab | Dữ liệu của execution này không bị execution kia ghi đè |
| Hủy sau khi sửa bản nháp | Subflow sửa DTO rồi bị hủy | Dữ liệu chính thức của cha không bị thay đổi ngoài ý muốn |
| Thay đổi contract | Đổi tên input/output trong test fixture | Các caller không tương thích bị phát hiện |

Một cách kiểm tra hữu ích là chạy subflow từ một flow cha tối giản chỉ cung cấp đúng các input được khai báo. Nếu subflow chỉ hoạt động khi một flow cha cụ thể khởi tạo thêm conversationScope hoặc session attribute, đó là dấu hiệu phụ thuộc ngầm.

Có thể thêm kiểm thử với conversationScope rỗng, session mới và hai execution chạy song song. Không nên chỉ kiểm thử đường đi thành công trong một execution duy nhất, vì các lỗi chia sẻ dữ liệu thường chỉ xuất hiện khi có nhiều caller hoặc nhiều tab.

## 11. Quy trình tìm phụ thuộc ngầm trong một subflow hiện có

Khi cần tái sử dụng một subflow đang gắn chặt với flow cha, hãy kiểm tra theo trình tự:

1. Liệt kê mọi biến mà flow con đọc trong expression, action, validator và view.
2. Phân loại mỗi biến thuộc input, flowScope riêng, conversationScope, request, HttpSession hay service.
3. Với biến conversation/session, tìm nơi khởi tạo và mọi nơi có thể sửa nó.
4. Xác định dữ liệu nào là yêu cầu đầu vào thực sự; chuyển chúng thành input có tên và kiểu rõ ràng.
5. Xác định kết quả mà caller cần; chuyển chúng thành output trên end state phù hợp.
6. Thay việc đọc trực tiếp biến của caller bằng input; thay việc caller dò biến chung bằng output/event.
7. Với object mutable, xác định quyền sở hữu và quyết định truyền ID, DTO hay bản sao.
8. Chạy test subflow độc lập và test từ ít nhất hai flow cha.
9. Kiểm tra các nhánh cancel, decline, lỗi dịch vụ và execution bị gián đoạn.

Khi hoàn thành, người đọc định nghĩa subflow có thể biết yêu cầu đầu vào và kết quả đầu ra mà không cần mở flow cha để tìm biến nào đó được đặt trước.

## 12. Checklist thiết kế subflow

- [ ] Mọi dữ liệu bắt buộc từ caller được khai báo bằng input.
- [ ] Mỗi input có tên, kiểu và điều kiện bắt buộc/tùy chọn rõ ràng.
- [ ] Flow con không đọc biến flowScope riêng của flow cha.
- [ ] Không dùng conversationScope như một kho biến toàn cục không có hợp đồng.
- [ ] Mọi dữ liệu chia sẻ trong conversationScope có chủ sở hữu và quy tắc cập nhật rõ.
- [ ] Kết quả được công bố bằng output trên end state phù hợp.
- [ ] ID end state và transition event của flow cha khớp nhau.
- [ ] Có nhánh thành công, hủy và lỗi nghiệp vụ phù hợp.
- [ ] Object mutable được truyền qua ranh giới có quy tắc quyền sở hữu/copy rõ ràng.
- [ ] HttpSession không được dùng làm vùng lưu dữ liệu riêng cho một execution bằng key cố định.
- [ ] Flow con không phụ thuộc vào state hoặc tên biến riêng của caller.
- [ ] Có test độc lập, test nhiều caller và test hai execution song song.
- [ ] Thay đổi contract được đánh giá tác động tới mọi flow cha đang gọi subflow.

## 13. Bài tập thực hành

Có một subflow `address` ban đầu được viết riêng cho flow `checkout`. Flow con đọc `conversationScope.currentCustomerId`, sửa `conversationScope.currentOrder.address` và kết thúc bằng event `done`. Hãy refactor để subflow có thể được gọi từ cả flow đăng ký và flow quản lý hồ sơ.

1. Xác định dữ liệu đầu vào tối thiểu mà subflow cần trong mỗi trường hợp.
2. Thiết kế input contract với ID hoặc DTO phù hợp; không để flow con đọc trực tiếp biến của caller.
3. Thiết kế output cho địa chỉ đã xác nhận và các nhánh cancel/invalid.
4. Quyết định liệu có dữ liệu nào thực sự cần dùng chung trong conversationScope hay không; ghi rõ quyền đọc/ghi.
5. Đảm bảo hủy subflow không làm thay đổi dữ liệu chính thức của flow cha.
6. Viết test chạy subflow từ checkout và profile, test thiếu input, test cancel và test hai execution đồng thời trong cùng HttpSession.
7. Thử đổi tên một output và quan sát test nào phát hiện caller chưa được cập nhật.

**Tiêu chí hoàn thành:** subflow không còn dựa vào biến riêng của checkout; mọi dữ liệu cần thiết được thể hiện qua input; kết quả được trả bằng output và event; hai flow cha có thể gọi lại subflow với cùng contract; và kiểm thử chứng minh dữ liệu của các execution không bị trộn.

## Kết luận

Subflow chỉ thực sự có thể tái sử dụng khi nó khai báo rõ dữ liệu cần nhận và kết quả sẽ trả về. flowScope thuộc từng flow session; conversationScope có thể chia sẻ trong một execution nhưng cần được dùng có chủ đích; HttpSession rộng hơn và không phù hợp làm kênh trao đổi riêng giữa caller và subflow. Dùng input/output, event kết thúc rõ ràng, dữ liệu có quyền sở hữu và kiểm thử nhiều caller giúp giảm phụ thuộc ngầm, giữ flow độc lập và làm thay đổi trong tương lai dễ kiểm soát.

