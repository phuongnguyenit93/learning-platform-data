# ConversationManager và quản lý các cuộc tương tác

Trong chương **Kiến trúc thực thi**, bài học này giải thích cách Spring Web Flow quản lý một cuộc tương tác web kéo dài qua nhiều request. Một hành trình như đặt lịch, đăng ký dịch vụ hoặc xử lý hồ sơ thường có nhiều màn hình, có thể gọi subflow và cần giữ dữ liệu nhất quán trong suốt quá trình. Nếu mỗi controller tự lưu trạng thái và tự quyết định bước tiếp theo, logic điều hướng nhanh chóng bị phân tán.

Spring Web Flow mô hình hóa hành trình bằng flow, state, event và transition. Bên cạnh việc điều phối các bước đó, framework còn cần một cơ chế quản lý vòng đời của cuộc tương tác. **ConversationManager** đảm nhiệm phần việc này: tạo, tìm, kết thúc và quản lý quyền truy cập vào conversation. Hiểu đúng vai trò của nó giúp ta chọn đúng scope cho dữ liệu, xử lý nhiều tab hoặc request đồng thời, và phục hồi luồng khi phiên làm việc hết hạn.

## 1. Vì sao cần quản lý conversation?

Hãy hình dung người dùng đặt một lịch hẹn trực tuyến:

1. Chọn dịch vụ và thời gian.
2. Nhập thông tin người tham gia.
3. Xác minh thông tin qua một subflow.
4. Xem lại toàn bộ lựa chọn.
5. Xác nhận và hoàn tất.

Mỗi bước có thể tương ứng với một request HTTP riêng. Người dùng có thể quay lại bước trước, tải lại trang, mở một subflow hoặc mở một hành trình khác trong tab mới. Ứng dụng cần giữ bản nháp của lịch hẹn xuyên suốt các bước, đồng thời biết khi nào hành trình đó bắt đầu và kết thúc.

Nếu lưu toàn bộ dữ liệu vào request, dữ liệu sẽ mất sau request hiện tại. Nếu đưa tất cả vào HTTP session, nhiều hành trình độc lập trong cùng một session có thể vô tình dùng chung dữ liệu. Nếu controller tự quản lý một bản đồ trạng thái, ứng dụng phải tự giải quyết việc định danh, hết hạn, truy cập đồng thời và dọn dẹp.

Conversation cung cấp một phạm vi có vòng đời rõ ràng cho một nhóm flow execution liên quan. Các flow execution trong cùng conversation có thể chia sẻ dữ liệu thuộc conversation scope. ConversationManager quản lý vòng đời và quyền truy cập vào phạm vi đó; flow engine vẫn chịu trách nhiệm thực thi state, phát event và áp dụng transition.

## 2. Phân biệt flow execution, conversation và ConversationManager

Ba khái niệm này liên quan với nhau nhưng giải quyết các vấn đề khác nhau.

| Thành phần | Trách nhiệm | Ví dụ trong hành trình đặt lịch |
|---|---|---|
| Flow | Định nghĩa cấu trúc hành trình: state, event, transition, action và subflow | Các bước chọn giờ, xác minh, xem lại |
| Flow execution | Một lần chạy cụ thể của flow; mang trạng thái thực thi cần được tiếp tục qua các request | Lần đặt lịch hiện tại của một người dùng |
| Conversation | Nhóm các flow execution liên quan, có chung conversation scope và vòng đời tương tác | Flow đặt lịch cùng subflow xác minh |
| FlowExecutionRepository | Lưu và khôi phục trạng thái của flow execution giữa các request | Khôi phục đúng state khi người dùng gửi request tiếp theo |
| ConversationManager | Tạo, tra cứu, kết thúc và điều phối truy cập vào conversation | Quản lý conversation chứa phạm vi dữ liệu dùng chung |

Có thể hình dung quan hệ ở mức kiến trúc như sau:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring MVC / FlowHandlerAdapter"]
    B --> C["FlowExecutor"]
    C --> D["Flow execution"]
    D --> E["Flow states và transitions"]
    D --> F["FlowExecutionRepository<br/>lưu và khôi phục execution"]
    D --> G["ConversationManager"]
    G --> H["Conversation"]
    H --> I["conversationScope"]
    E --> J["Subflow"]
    J --> I
~~~

Sơ đồ thể hiện các trách nhiệm ở mức khái niệm; chi tiết gọi nội bộ phụ thuộc phiên bản và cấu hình Spring Web Flow.

**Flow execution** trả lời câu hỏi “lần chạy flow này đang ở state nào?”. **Conversation** trả lời câu hỏi “những lần chạy flow liên quan nào thuộc cùng một cuộc tương tác và chia sẻ dữ liệu nào?”. **ConversationManager** là abstraction quản lý conversation. Nó không quyết định người dùng được chuyển từ state này sang state khác; việc đó thuộc flow definition và flow engine.

FlowExecutionRepository cũng không đồng nghĩa với ConversationManager. Repository chịu trách nhiệm lưu/khôi phục flow execution. ConversationManager chịu trách nhiệm quản lý conversation mà các execution liên quan sử dụng. Trong kiến trúc Web Flow, repository phối hợp với conversation manager để gắn trạng thái thực thi vào đúng conversation.

## 3. Vòng đời của một conversation

Vòng đời thường gắn với flow gốc của một hành trình:

1. **Bắt đầu:** Khi một flow gốc được khởi chạy, framework tạo hoặc mở conversation tương ứng. Conversation có định danh riêng để framework tìm lại trong các request tiếp theo.
2. **Tiếp tục:** Mỗi request tiếp theo được định tuyến tới flow executor. Framework khôi phục flow execution, truy cập conversation tương ứng rồi xử lý event và transition.
3. **Chạy subflow:** Subflow tham gia vào cùng cuộc tương tác và có thể dùng dữ liệu trong conversation scope. Subflow vẫn có flow scope riêng cho trạng thái nội bộ của nó.
4. **Kết thúc bình thường:** Khi flow gốc kết thúc, conversation được kết thúc và tài nguyên gắn với nó có thể được giải phóng.
5. **Kết thúc bất thường:** Người dùng có thể đóng trình duyệt, session hết hạn hoặc request không thể tiếp tục conversation. Ứng dụng cần xử lý trường hợp không tìm thấy conversation và hướng người dùng tới một hành động có thể thực hiện, chẳng hạn bắt đầu lại hoặc khôi phục hồ sơ từ dữ liệu đã lưu bền vững.

Một subflow kết thúc thường chỉ trả event về flow gọi nó. Việc subflow hoàn tất không nhất thiết kết thúc conversation của flow gốc. Điều này cho phép một hành trình gọi nhiều subflow mà vẫn giữ dữ liệu dùng chung trong cùng phạm vi tương tác.

Conversation ID giúp framework xác định đúng conversation. Không nên coi ID này là bằng chứng xác thực hoặc quyền truy cập vào dữ liệu nghiệp vụ. Mọi thao tác đọc hoặc cập nhật hồ sơ, đơn hàng và tài nguyên của người dùng vẫn phải được kiểm tra quyền ở tầng nghiệp vụ.

## 4. ConversationManager làm gì?

ConversationManager cung cấp một điểm trừu tượng để framework quản lý conversation mà không buộc flow definition phụ thuộc trực tiếp vào cách lưu trữ cụ thể. Contract của manager xoay quanh các thao tác chính:

- Bắt đầu một conversation với thông tin tham số cần thiết.
- Tìm conversation theo định danh.
- Kết thúc conversation khi hành trình hoàn tất hoặc bị hủy.
- Phân tích định danh được mã hóa để lấy ConversationId.
- Cung cấp quyền truy cập tới đối tượng conversation; đối tượng này có cơ chế khóa và mở khóa để điều phối truy cập đồng thời.

Trong API của Spring Web Flow, các kiểu thường gặp quanh contract này là **ConversationManager**, **Conversation**, **ConversationId** và **ConversationParameters**. Hình dạng chi tiết của API và cách cấu hình implementation cần được đối chiếu với phiên bản Spring Web Flow mà ứng dụng đang sử dụng.

Một implementation cho ứng dụng web thường gắn conversation với HTTP session. Ví dụ, Spring Web Flow có implementation mang tên **SessionBindingConversationManager**. Cách triển khai này phù hợp khi vòng đời tương tác gắn với session của người dùng. Ứng dụng chỉ nên thay implementation khi có yêu cầu cụ thể về lưu trữ, phân phối session, giới hạn số conversation hoặc chính sách vòng đời.

Framework thường quản lý việc tạo và truy cập conversation trong quá trình thực thi flow. Vì vậy, code nghiệp vụ thông thường nên làm việc với flow scope và conversation scope qua cơ chế của Web Flow, thay vì tự gọi ConversationManager ở mọi controller hoặc tự tạo một kho conversation riêng.

### Khóa truy cập và request đồng thời

Một người dùng có thể gửi hai request gần như cùng lúc: nhấn nút hai lần, mở cùng một flow ở hai tab hoặc tải lại trang trong lúc request trước chưa hoàn tất. Nếu hai request cùng sửa dữ liệu của một conversation, trạng thái có thể bị ghi đè hoặc chuyển bước không nhất quán.

Conversation hỗ trợ cơ chế khóa truy cập để framework điều phối việc thao tác trên cùng một conversation. Khóa giúp hạn chế hai request cùng cập nhật trạng thái thực thi trong cùng thời điểm. Tuy nhiên, khóa conversation không thay thế tính idempotent của nghiệp vụ. Ví dụ, thao tác tạo thanh toán hoặc đặt chỗ vẫn cần mã yêu cầu duy nhất, kiểm tra trạng thái và ràng buộc ở cơ sở dữ liệu để tránh thực hiện trùng.

## 5. Chọn scope đúng cho dữ liệu

ConversationManager quản lý conversation; dữ liệu được đặt vào scope phù hợp với vòng đời mà ứng dụng mong muốn. Chọn scope sai là nguyên nhân phổ biến gây mất dữ liệu hoặc chia sẻ dữ liệu ngoài ý muốn.

| Scope | Vòng đời và phạm vi | Dữ liệu phù hợp |
|---|---|---|
| requestScope | Một request HTTP | Thông tin tạm chỉ dùng khi xử lý request |
| viewScope | Khi một view-state đang hoạt động | Dữ liệu riêng của màn hình hiện tại |
| flashScope | Dữ liệu tạm chuyển tiếp tới lần hiển thị kế tiếp theo luồng | Thông báo hoàn tất hoặc lỗi ngắn hạn |
| flowScope | Trong một flow execution | Biểu mẫu hoặc dữ liệu chỉ thuộc flow đó |
| conversationScope | Trong toàn bộ conversation, có thể được chia sẻ giữa flow gốc và subflow | Bản nháp đặt lịch dùng chung qua nhiều bước |
| sessionScope | Trong HTTP session, có thể bao phủ nhiều conversation | Tùy chọn hoặc thông tin dùng chung ở cấp phiên |

Ví dụ: thông tin đang nhập riêng trong subflow xác minh có thể nằm trong flowScope của subflow. Bản nháp đặt lịch mà flow gốc và subflow cùng cần đọc có thể nằm trong conversationScope. Thông tin đăng nhập hoặc dữ liệu dùng chung ở cấp phiên thuộc một cơ chế khác và không nên đưa vào conversationScope chỉ vì tiện truy cập.

Conversation scope không phải nơi lưu trữ bền vững. Khi session hoặc conversation hết hạn, dữ liệu trong scope có thể không còn. Nếu người dùng cần tiếp tục một hồ sơ sau nhiều giờ hoặc sau khi đăng nhập lại, hãy lưu bản nháp vào cơ sở dữ liệu bằng một định danh nghiệp vụ, rồi dùng flow để tải lại dữ liệu sau khi xác thực và kiểm tra quyền.

## 6. Ví dụ: chia sẻ bản nháp giữa flow gốc và subflow

Giả sử flow đặt lịch cần giữ một bản nháp xuyên suốt quá trình. Subflow xác minh người tham gia cần đọc bản nháp đó, nhưng chỉ flow gốc mới quyết định hoàn tất đặt lịch.

Đoạn flow dưới đây minh họa cách khởi tạo dữ liệu trong conversation scope và gọi subflow:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow" id="booking">

    <on-start>
        <set name="conversationScope.bookingDraft"
             value="bookingService.createDraft()" />
    </on-start>

    <view-state id="chooseSlot" view="booking/choose-slot">
        <transition on="continue" to="verifyGuest" />
    </view-state>

    <subflow-state id="verifyGuest" subflow="guest-verification">
        <transition on="verified" to="review" />
        <transition on="cancelled" to="chooseSlot" />
    </subflow-state>

    <view-state id="review" view="booking/review">
        <transition on="confirm" to="complete" />
    </view-state>

    <end-state id="complete" view="booking/complete" />

</flow>
~~~

Trong ví dụ:

- Khi flow gốc bắt đầu, service tạo bản nháp và đặt vào **conversationScope.bookingDraft**.
- State **chooseSlot** thu thập lựa chọn thời gian.
- Subflow **guest-verification** xử lý bước xác minh. Subflow có flow scope riêng, nhưng có thể đọc bản nháp trong conversation scope của cuộc tương tác chung.
- Khi subflow trả event **verified**, flow gốc tiếp tục tới bước xem lại.
- Khi người dùng xác nhận, flow gốc đi tới end-state và kết thúc hành trình.

Trong subflow, có thể tham chiếu bản nháp bằng biểu thức **conversationScope.bookingDraft**. Nếu cần dữ liệu chỉ dùng nội bộ cho subflow, hãy đặt dữ liệu đó trong flowScope của subflow. Nhờ vậy, ranh giới chia sẻ dữ liệu thể hiện rõ trong thiết kế.

Ví dụ trên chỉ minh họa cách tổ chức state và scope. Ứng dụng thực tế vẫn cần khai báo flow registry, cấu hình flow executor và tích hợp Spring MVC phù hợp với phiên bản đang dùng. Service tạo bản nháp cũng cần kiểm tra người dùng hiện tại và áp dụng quy tắc nghiệp vụ.

## 7. Thiết kế conversation an toàn và dễ bảo trì

Một conversation nên chứa dữ liệu tối thiểu cần thiết để tiếp tục hành trình. Một số nguyên tắc hữu ích:

- **Giữ dữ liệu có vòng đời ngắn:** Chỉ đặt vào conversation scope những gì cần được chia sẻ giữa các bước trong một hành trình.
- **Lưu tham chiếu thay vì đối tượng lớn:** Với hồ sơ hoặc đơn hàng đã tồn tại, ưu tiên lưu ID và tải dữ liệu qua service có kiểm tra quyền. Tránh giữ toàn bộ entity lớn hoặc đồ thị đối tượng trong session.
- **Không lưu bí mật nhạy cảm:** Không giữ mật khẩu, thông tin xác thực đầy đủ hoặc dữ liệu thẻ thanh toán trong conversation scope. Dùng token ngắn hạn hoặc cơ chế lưu trữ chuyên biệt khi nghiệp vụ yêu cầu.
- **Xác định rõ điểm kết thúc:** Flow gốc cần có đường hoàn tất và đường hủy hợp lý. Dọn dẹp dữ liệu tạm khi conversation kết thúc.
- **Xử lý hết hạn có chủ đích:** Nếu conversation không còn tồn tại, hiển thị thông báo dễ hiểu và hướng dẫn bắt đầu lại hoặc khôi phục từ bản nháp bền vững. Không để người dùng nhận stack trace hoặc trang lỗi chung chung.
- **Bảo vệ thao tác ghi:** Dùng kiểm tra quyền, transaction, ràng buộc dữ liệu và idempotency cho thao tác có tác động như giữ chỗ, tạo đơn hoặc thanh toán.
- **Cân nhắc triển khai nhiều node:** Nếu conversation dựa trên HTTP session, cần cấu hình session affinity hoặc cơ chế session dùng chung/replication phù hợp. Kiểm tra khả năng tuần tự hóa của dữ liệu nếu hạ tầng yêu cầu session được tuần tự hóa.
- **Đặt thời hạn phù hợp:** Conversation tồn tại quá lâu sẽ chiếm tài nguyên và giữ dữ liệu cũ. Thời hạn cần phù hợp với thời gian hoàn thành hành trình và chính sách bảo mật.

Không nên dùng ConversationManager như một kho dữ liệu nghiệp vụ thay thế database. Manager giải quyết vòng đời tương tác; dữ liệu cần tồn tại sau khi tương tác kết thúc phải được lưu qua tầng persistence của ứng dụng.

## 8. Kiểm thử vòng đời và tình huống lỗi

Kiểm thử chỉ xác nhận từng transition chạy đúng là chưa đủ. Cần kiểm tra dữ liệu có được giữ đúng phạm vi và conversation có được kết thúc đúng lúc hay không.

| Tình huống | Điều cần xác minh |
|---|---|
| Khởi chạy flow gốc | Conversation được tạo và bản nháp ban đầu xuất hiện đúng scope |
| Chuyển qua nhiều state | Dữ liệu conversation scope vẫn giữ nguyên qua các request |
| Gọi subflow | Subflow đọc được dữ liệu chia sẻ; flowScope của subflow vẫn độc lập |
| Subflow kết thúc | Event được trả về flow gọi; conversation của flow gốc vẫn dùng được |
| Kết thúc flow gốc | Conversation được kết thúc và dữ liệu tạm được giải phóng theo implementation |
| Hai request đồng thời | Trạng thái không bị cập nhật chồng chéo; thao tác nghiệp vụ không bị thực hiện trùng |
| Session hoặc conversation hết hạn | Ứng dụng xử lý trường hợp không tìm thấy conversation bằng luồng phục hồi phù hợp |
| Người dùng mở hai hành trình | Dữ liệu của hai conversation không bị trộn lẫn |
| Người dùng không có quyền | Biết conversation ID không cho phép truy cập dữ liệu nghiệp vụ của người khác |

Có thể kiểm thử flow qua flow executor với môi trường request giả lập, đồng thời mock service nghiệp vụ để kiểm tra event và dữ liệu. Với phần tích hợp, nên có kiểm thử chạy qua Spring MVC để xác nhận request được định tuyến, execution được khôi phục và session hết hạn được xử lý như mong đợi.

Đối với tình huống đồng thời, cần kiểm thử cả lớp flow lẫn lớp nghiệp vụ. Một test xác nhận request thứ hai phải chờ khóa chưa đủ để chứng minh thao tác đặt chỗ không bị trùng; cần kiểm tra thêm ràng buộc duy nhất hoặc cơ chế idempotency ở nơi ghi dữ liệu.

## 9. Khi nào cần thay ConversationManager?

Hãy bắt đầu bằng implementation được cấu hình sẵn của Spring Web Flow. Chỉ cân nhắc thay đổi khi có yêu cầu vận hành cụ thể, chẳng hạn:

- Cần chính sách lưu conversation khác với session hiện tại.
- Cần điều chỉnh giới hạn số conversation hoặc thời gian tồn tại.
- Cần tích hợp với cơ chế quản lý session của hạ tầng.
- Cần hành vi khóa hoặc quản lý vòng đời phù hợp với môi trường triển khai đặc thù.

Trước khi cấu hình implementation khác, cần kiểm tra API và điểm cấu hình của đúng phiên bản Spring Web Flow. Không nên tự xây một ConversationManager chỉ để lưu vài trường dữ liệu; trường hợp đó thường được giải quyết bằng scope hoặc service nghiệp vụ. Nếu yêu cầu là lưu bản nháp qua nhiều phiên đăng nhập, hãy thiết kế persistence cho bản nháp thay vì kéo dài conversation vô hạn.

## 10. Quy trình thiết kế và rà soát

Khi xây dựng một hành trình nhiều bước, có thể áp dụng trình tự sau:

1. Xác định flow gốc, các state, event và subflow.
2. Xác định dữ liệu nào chỉ thuộc một request, một view-state, một flow execution hay toàn bộ conversation.
3. Đặt dữ liệu dùng chung giữa flow gốc và subflow vào conversationScope; giữ dữ liệu nội bộ trong flowScope.
4. Để flow executor và repository quản lý việc tiếp tục flow execution qua request; để ConversationManager quản lý vòng đời conversation.
5. Xác định điểm hoàn tất, hủy và xử lý khi session/conversation hết hạn.
6. Kiểm thử nhiều tab, request đồng thời, quyền truy cập và việc dọn dẹp dữ liệu.
7. Chỉ thay implementation của ConversationManager khi yêu cầu lưu trữ hoặc vận hành chứng minh cần thiết.

ConversationManager là một phần hạ tầng quan trọng trong kiến trúc thực thi của Spring Web Flow. Khi phân biệt rõ conversation với flow execution và chọn scope theo đúng vòng đời dữ liệu, ứng dụng có thể tổ chức các hành trình nhiều bước và subflow mạch lạc hơn, đồng thời giảm lỗi do trạng thái bị chia sẻ sai hoặc mất giữa các request.
