# Đồng bộ dữ liệu form khi có nhiều yêu cầu liên tiếp

Trong một view-state của Spring Web Flow, người dùng có thể gửi nhiều yêu cầu Ajax liên tiếp: xem trước dữ liệu, kiểm tra một trường, tự động lưu bản nháp hoặc tải lại một phần màn hình. Mỗi yêu cầu có thể mang một phiên bản dữ liệu form khác nhau. Nếu request đến server chồng lấn, hoặc response trả về không theo thứ tự, giao diện và trạng thái flow có thể không còn phản ánh cùng một phiên bản dữ liệu.

Đồng bộ form vì vậy cần được thiết kế ở cả phía trình duyệt và phía server. Trình duyệt phải kiểm soát thứ tự gửi request và thứ tự áp dụng response; flow phải tiếp tục đúng execution và binding đúng dữ liệu của request; service nghiệp vụ phải bảo vệ các cập nhật quan trọng bằng quy tắc nhất quán, transaction và kiểm soát phiên bản khi cần.

Bài học thuộc chương **Ajax và phân mảnh** của module **Spring Web Flow**. Module này hướng dẫn mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi gặp lỗi.

## 1. Vì sao nhiều request liên tiếp dễ làm lệch dữ liệu?

Giả sử màn hình chỉnh sửa hồ sơ có chức năng xem trước địa chỉ. Người dùng thay đổi địa chỉ rồi nhấn “Xem trước”. Trong lúc request đầu chưa hoàn tất, họ sửa tiếp số điện thoại và nhấn “Lưu”.

Có thể xảy ra chuỗi sau:

1. Request A gửi phiên bản form thứ nhất, gồm địa chỉ mới.
2. Người dùng tiếp tục sửa form và gửi request B với phiên bản thứ hai.
3. B đến server trước A hoặc cả hai cùng được gửi tới một flow execution.
4. Server xử lý và trả về hai response.
5. Response của A đến sau B và thay thế một phần giao diện mới hơn bằng dữ liệu cũ.

Kết quả có thể là giao diện hiển thị dữ liệu cũ trong khi người dùng nghĩ dữ liệu mới đã được lưu. Hoặc request B dùng execution key cũ vì A đã làm flow tiến tới một trạng thái/snapshot mới. Tùy repository và cấu hình, request thứ hai có thể bị chặn, bị từ chối hoặc được xử lý từ một trạng thái lịch sử.

Cần phân biệt ba lớp trạng thái:

| Lớp trạng thái | Nội dung | Rủi ro khi request chồng lấn |
|---|---|---|
| DOM/form phía trình duyệt | Giá trị người dùng đang nhìn và chỉnh sửa | Response cũ ghi đè giá trị mới |
| Flow execution phía server | Model, scope, state và dữ liệu của lần chạy flow | Request dùng execution key cũ hoặc cập nhật không theo thứ tự mong muốn |
| Dữ liệu nghiệp vụ bền vững | Hồ sơ, đơn hàng, bản nháp trong database | Ghi đè cập nhật mới hơn hoặc thực hiện tác động trùng |

Một response Ajax cập nhật fragment không tự bảo đảm ba lớp trên đồng bộ. Ứng dụng cần quy định rõ request nào được phép chạy tiếp, dữ liệu nào được gửi và response nào còn hợp lệ để cập nhật giao diện.

## 2. Vòng đời của một Ajax request trong flow

Một Ajax request gửi event tới Spring Web Flow vẫn là một request đi qua tích hợp Spring MVC. FlowHandlerMapping nhận diện URL flow, FlowHandlerAdapter chuyển request cho FlowExecutor, rồi execution được khôi phục để binding dữ liệu, xử lý event và tạo kết quả render.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant B as Browser / Form
    participant M as Spring MVC
    participant W as FlowExecutor
    participant R as ExecutionRepository
    participant S as Service

    B->>M: Ajax request + flow URL + event + form data
    M->>W: Chuyển request tới flow
    W->>R: Khôi phục execution
    R-->>W: Trạng thái execution
    W->>W: Bind dữ liệu và xử lý event
    W->>S: Gọi service nếu cần
    S-->>W: Kết quả / validation
    W->>R: Lưu trạng thái tiếp theo
    W-->>M: Kết quả view hoặc fragment
    M-->>B: Ajax response
    B->>B: Kiểm tra response còn mới rồi cập nhật DOM
~~~

Các bước quan trọng:

- Request phải trỏ tới URL của flow execution hiện tại.
- Event gửi lên phải khớp với transition hoặc hành động được flow định nghĩa.
- Dữ liệu form được bind theo cấu hình model và binder của view-state.
- Flow xử lý event, có thể gọi action/service, rồi lưu trạng thái execution theo repository.
- View technology hoặc lớp tích hợp Ajax trả về nội dung cần render.
- Trình duyệt chỉ nên áp dụng response nếu response đó vẫn phù hợp với phiên bản form hiện tại.

Ajax chỉ thay đổi cách trình duyệt gửi request và nhận phần nội dung trả về. Nó không bỏ qua flow execution, binding, validation, security hay quy tắc lưu trạng thái của Web Flow.

## 3. Một flow mẫu có nhiều event trên cùng view-state

Giả sử màn hình sửa hồ sơ cho phép người dùng xem trước thông tin, kiểm tra dữ liệu và lưu. Các event có thể được xử lý tại cùng view-state hoặc chuyển sang state khác.

Ví dụ flow definition ở mức minh họa:

~~~xml
<view-state id="editProfile" view="profile/edit"
            model="profileForm">

    <binder>
        <binding property="displayName" />
        <binding property="email" />
        <binding property="phone" />
    </binder>

    <transition on="preview">
        <evaluate expression="profilePreviewService.create(profileForm)"
                  result="viewScope.preview" />
    </transition>

    <transition on="save" to="review">
        <evaluate expression="profileService.validate(profileForm, messageContext)" />
    </transition>

    <transition on="cancel" to="cancelled" />
</view-state>
~~~

Event preview xử lý yêu cầu xem trước tại màn hình hiện tại. Event save đưa flow sang bước xem lại nếu validation thành công theo logic của ứng dụng. Event cancel chuyển sang đường hủy.

Ví dụ cho thấy một view-state có thể nhận nhiều event. Tuy nhiên, nếu người dùng gửi preview và save gần như đồng thời, ứng dụng không nên mặc định hai event sẽ được gộp hoặc xử lý theo thứ tự người dùng nhấn. Mỗi request là một lần tương tác độc lập với flow execution; cần điều phối chúng.

Trong triển khai thực tế, hãy xác định rõ event nào chỉ đọc dữ liệu, event nào thay đổi model, event nào chuyển state và event nào thực hiện tác động nghiệp vụ. Không để một request xem trước vô tình chạy cùng logic lưu dữ liệu.

## 4. Gửi đúng dữ liệu form cho từng request

Một request Ajax có thể gửi toàn bộ form hoặc chỉ gửi các trường cần thiết. Lựa chọn này ảnh hưởng đến cách binding và cách server hiểu dữ liệu không xuất hiện trong request.

| Cách gửi | Ưu điểm | Rủi ro / điều kiện |
|---|---|---|
| Gửi toàn bộ form | Server có một bộ dữ liệu đầy đủ tại thời điểm gửi | Payload lớn hơn; response hoặc request cũ vẫn có thể cạnh tranh |
| Gửi một phần trường | Payload nhỏ, phù hợp kiểm tra một trường hoặc tải preview độc lập | Phải định nghĩa rõ trường bị thiếu nghĩa là “không đổi”, “rỗng” hay “không gửi” |
| Gửi DTO patch có version | Thể hiện rõ trường thay đổi và phiên bản cơ sở | Cần code merge và kiểm tra version ở server |

Ví dụ JSP dùng Spring form tag:

~~~jsp
<form:form id="profileForm"
           modelAttribute="profileForm"
           action="URL-flowExecutionUrl"
           method="post">

    <label for="displayName">Tên hiển thị</label>
    <form:input path="displayName" id="displayName" />

    <label for="email">Email</label>
    <form:input path="email" id="email" />

    <label for="phone">Điện thoại</label>
    <form:input path="phone" id="phone" />

    <button type="submit" name="_eventId_preview">Xem trước</button>
    <button type="submit" name="_eventId_save">Lưu</button>
</form:form>
~~~

URL-flowExecutionUrl trong ví dụ là vị trí mà view phải dùng URL execution được Web Flow cung cấp. Khi chuyển sang Ajax, request vẫn cần mang execution URL/key hiện hành, event ID và các trường form cần binding.

Nếu request chỉ gửi email, đừng giả định các trường displayName và phone sẽ tự giữ nguyên trong mọi cấu hình binding. Hãy xác định rõ semantics của partial update. Một DTO patch có thể dùng trạng thái riêng để phân biệt trường không được gửi với trường được gửi nhưng có giá trị rỗng.

Ví dụ cấu trúc patch:

~~~java
public record ProfilePatch(
        Long version,
        boolean emailPresent,
        String email
) {}
~~~

Trong đó emailPresent=false có nghĩa request không yêu cầu thay đổi email; emailPresent=true với email rỗng có thể mang nghĩa xóa giá trị nếu nghiệp vụ cho phép. Cách biểu diễn này tránh nhập nhằng giữa absent và empty.

## 5. Tuần tự hóa request thay đổi cùng một execution

Với các request làm thay đổi cùng flow execution, cách đơn giản và dễ kiểm soát là chỉ cho phép một request đang xử lý tại một thời điểm trên cùng execution. Các request tiếp theo được xếp hàng và gửi sau khi request trước hoàn tất, đồng thời dùng thông tin execution mới nhất mà response trước cung cấp.

Ví dụ hàng đợi phía trình duyệt ở mức minh họa:

~~~javascript
let flowRequestQueue = Promise.resolve();

function enqueueFlowRequest(sendRequest) {
    flowRequestQueue = flowRequestQueue
        .catch(() => {
            // Cho phép hàng đợi tiếp tục sau khi request trước lỗi.
        })
        .then(() => sendRequest());

    return flowRequestQueue;
}
~~~

Mọi thao tác thay đổi state hoặc model của cùng flow execution đi qua một hàng đợi. Hàm gửi request cần đọc URL/execution token mới nhất tại thời điểm thực sự gửi, thay vì đóng cứng giá trị từ lúc người dùng mở trang.

Có thể áp dụng các chính sách khác nhau:

- **Preview:** Nếu mỗi preview thay thế preview trước, chỉ giữ yêu cầu mới nhất hoặc hủy yêu cầu cũ chưa hoàn tất.
- **Autosave:** Gom các thay đổi trong một khoảng ngắn rồi gửi một request; không gửi một request cho mỗi phím bấm.
- **Save/confirm:** Chặn gửi trùng, đợi request đang chạy và chỉ gửi sau khi dữ liệu mới nhất đã được đồng bộ.
- **Điều hướng sang state khác:** Hoàn tất hoặc hủy các request phụ thuộc state cũ trước khi chuyển bước.

Không phải mọi Ajax request đều cần tuần tự hóa. Request đọc dữ liệu độc lập và không thay đổi flow execution có thể chạy song song nếu không phụ thuộc trạng thái chung. Nhưng các request cùng sửa model, phát event hoặc làm flow chuyển state cần có chính sách điều phối rõ ràng.

## 6. Giữ response đúng thứ tự khi cập nhật fragment

Ngay cả khi server xử lý request đúng, response vẫn có thể đến trình duyệt không theo thứ tự gửi. Ví dụ request A mất 800 ms, request B mất 200 ms. B trả về trước, sau đó A trả về và ghi đè fragment mới bằng nội dung cũ.

Có thể dùng số thứ tự request hoặc version form ở phía client để loại response lỗi thời:

~~~javascript
let latestPreviewRequest = 0;

async function refreshPreview(sendRequest, renderFragment) {
    const requestNumber = ++latestPreviewRequest;
    const response = await sendRequest();

    if (requestNumber !== latestPreviewRequest) {
        return;
    }

    const fragment = await response.text();
    renderFragment(fragment);
}
~~~

Ví dụ trên chỉ bảo vệ thứ tự render của preview ở client. Nó không thay thế kiểm soát concurrency ở server. Nếu hai request đã cùng thay đổi flow execution, bỏ response cũ ở trình duyệt không thể hoàn tác tác động mà request đó đã thực hiện trên server.

Với thao tác cập nhật state hoặc dữ liệu nghiệp vụ, nên kết hợp:

1. Tuần tự hóa request cùng execution.
2. Dùng execution URL/key mới nhất.
3. Dùng version dữ liệu hoặc optimistic locking cho bản ghi bền vững.
4. Kiểm tra response trước khi thay fragment.
5. Hiển thị lỗi nếu server báo execution cũ hoặc dữ liệu đã thay đổi.

Không nên chỉ dùng thời gian response để quyết định response nào mới hơn. Thời gian mạng không phản ánh thứ tự nghiệp vụ. Số thứ tự request, version form hoặc version dữ liệu do server quản lý đáng tin cậy hơn.

## 7. Quản lý trạng thái đang gửi, debounce và autosave

Đối với thao tác người dùng, giao diện nên thể hiện rõ request đang xử lý. Điều này giảm khả năng người dùng nhấn nhiều lần và giúp họ hiểu dữ liệu đã được xác nhận hay chưa.

Các kỹ thuật thường dùng:

| Kỹ thuật | Cách hoạt động | Phù hợp với |
|---|---|---|
| Disable nút | Vô hiệu hóa nút trong khi request đang chạy | Save, confirm, submit |
| Debounce | Chờ người dùng ngừng thao tác một khoảng ngắn rồi mới gửi | Tìm kiếm, autosave, preview |
| Throttle | Giới hạn tần suất gửi request | Theo dõi thay đổi liên tục |
| Request queue | Xếp request theo thứ tự | Nhiều event phụ thuộc cùng flow execution |
| Cancel stale request | Hủy request cũ khi request mới thay thế | Preview hoặc autocomplete |
| Coalesce | Gộp nhiều thay đổi thành một payload mới nhất | Autosave nhiều trường |

Ví dụ trạng thái giao diện:

~~~javascript
async function saveForm(form, button, sendRequest) {
    if (button.disabled) {
        return;
    }

    button.disabled = true;
    button.textContent = "Đang lưu...";

    try {
        await sendRequest(new FormData(form));
        button.textContent = "Đã lưu";
    } catch (error) {
        button.textContent = "Thử lưu lại";
        throw error;
    } finally {
        button.disabled = false;
    }
}
~~~

Đây là ví dụ minh họa trạng thái nút. Ứng dụng thực tế cần xử lý cả lỗi validation, lỗi mạng, lỗi execution hết hạn và response fragment. Không hiển thị “Đã lưu” chỉ vì request đã được gửi; chỉ thông báo thành công sau khi server xác nhận cập nhật.

Với autosave, nên giữ trạng thái **dirty** cho form. Sau khi server xác nhận lưu phiên bản đang gửi, chỉ xóa dirty nếu người dùng chưa sửa thêm trong lúc request chạy. Nếu có thay đổi mới hơn, tiếp tục hàng đợi bằng payload mới.

## 8. Version dữ liệu và chống ghi đè cập nhật mới

Tuần tự hóa request ở trình duyệt chỉ bảo vệ một tab hoặc một client. Một người dùng có thể mở nhiều tab, hoặc hai thiết bị cùng sửa một hồ sơ. Server cần cơ chế phát hiện cập nhật dựa trên dữ liệu cũ.

Một cách phổ biến là optimistic locking bằng trường version:

~~~java
@Entity
public class Profile {

    @Id
    private Long id;

    @Version
    private Long version;

    private String displayName;
    private String email;
    private String phone;
}
~~~

Khi lưu, JPA kiểm tra version mà entity đã đọc. Nếu một transaction khác cập nhật trước, thao tác hiện tại có thể gặp optimistic locking exception thay vì âm thầm ghi đè dữ liệu mới.

Ứng dụng có thể trả về thông báo “Dữ liệu đã được thay đổi ở nơi khác” và yêu cầu người dùng tải lại hoặc hợp nhất thay đổi. Không nên tự động ghi đè bằng form cũ nếu chưa có chính sách merge.

Với API patch, có thể gửi version hiện tại trong payload hoặc dùng HTTP conditional request như ETag/If-Match ở lớp HTTP phù hợp. Dù dùng cách nào, server phải so sánh version đáng tin cậy trước khi ghi. Giá trị version do client gửi chỉ là điều kiện để kiểm tra, không phải bằng chứng rằng dữ liệu được phép sửa.

## 9. Idempotency và gửi trùng thao tác nghiệp vụ

Request có thể bị gửi lại vì người dùng nhấn đúp, trình duyệt retry, mạng chập chờn hoặc client không nhận được response dù server đã xử lý xong. Với preview, chạy lại thường ít nguy hiểm. Với tạo đơn, giữ chỗ hoặc thanh toán, gửi trùng có thể gây hậu quả nghiêm trọng.

Dùng idempotency key cho thao tác có tác động:

~~~java
@Transactional
public BookingResult confirmBooking(
        String idempotencyKey,
        ConfirmBookingCommand command) {

    return idempotencyStore.findResult(idempotencyKey)
            .orElseGet(() -> {
                BookingResult result = bookingService.confirm(command);
                idempotencyStore.store(idempotencyKey, result);
                return result;
            });
}
~~~

Đây là mã giả để minh họa ý tưởng. Trong triển khai thực tế, việc kiểm tra key, thực hiện nghiệp vụ và lưu kết quả phải có tính nguyên tử, thường được bảo vệ bằng unique constraint hoặc transaction thích hợp. Nếu chỉ tra cứu rồi ghi ở các bước không nguyên tử, hai request đồng thời vẫn có thể cùng thực hiện nghiệp vụ.

Flow event không tự biến thao tác nghiệp vụ thành idempotent. Hãy thiết kế idempotency ở service hoặc tầng persistence cho những hành động có thể được retry.

## 10. Validation và giữ dữ liệu khi render fragment

Khi server trả lỗi validation, fragment form cần giữ lại các giá trị hợp lệ mà người dùng đã nhập và hiển thị lỗi gắn đúng trường. Không khởi tạo lại form trong mỗi lần render nếu điều đó làm mất dữ liệu đang sửa.

Quy trình hợp lý:

1. Nhận request và bind các trường được phép.
2. Chạy conversion và validation.
3. Nếu lỗi, giữ model phù hợp với view-state và trả fragment form cùng thông báo.
4. Nếu hợp lệ, thực hiện event hoặc transition theo flow definition.
5. Chỉ cập nhật fragment liên quan và đồng bộ execution URL/key mới nhất cho request kế tiếp.

Cần phân biệt lỗi conversion và validation nghiệp vụ. Chuỗi không thể parse thành ngày là conversion error; ngày hợp lệ nhưng nằm ngoài thời gian cho phép là validation error. Cả hai cần được phản hồi mà không xóa dữ liệu hợp lệ ở các trường khác.

Với partial form submission, hãy xác định trường nào thực sự được gửi. Không bind một DTO thiếu trường như thể các trường không có trong request là giá trị null mới. Nếu dùng command object, mô hình hóa rõ patch semantics và kiểm tra allowlist.

## 11. Xử lý lỗi, timeout và execution key cũ

Một request Ajax có thể thất bại vì mạng, session hết hạn, flow đã kết thúc, execution key cũ hoặc server từ chối request đồng thời. Giao diện cần phân loại lỗi để phản hồi đúng.

| Tình huống | Hành vi nên có |
|---|---|
| Validation thất bại | Render lỗi tại form, giữ giá trị hợp lệ |
| Mạng timeout, chưa biết server đã xử lý chưa | Không tự gửi lại thao tác không idempotent; kiểm tra trạng thái hoặc dùng idempotency key |
| Execution key cũ | Yêu cầu đồng bộ lại view hoặc khởi động lại flow có kiểm soát |
| Session hết hạn | Yêu cầu đăng nhập lại và khởi tạo execution mới theo chính sách |
| Flow đã kết thúc | Điều hướng về trang kết quả hoặc entry point phù hợp |
| Request bị từ chối do truy cập đồng thời | Giữ dữ liệu chưa lưu ở client, tải trạng thái mới nhất và cho người dùng thử lại |
| Response fragment không hợp lệ | Giữ giao diện hiện tại, ghi nhận lỗi và cung cấp cách tải lại |

Flow execution repository và conversation manager có thể dùng cơ chế khóa hoặc kiểm soát truy cập để bảo vệ trạng thái dùng chung. Khi request đồng thời nhắm vào cùng execution/conversation, implementation và cấu hình có thể chặn, tuần tự hóa hoặc từ chối một request. Không nên dựa vào một hành vi cụ thể nếu chưa kiểm tra phiên bản và repository đang dùng.

Nếu server đã xử lý request nhưng response bị mất, client không thể kết luận thao tác chưa xảy ra. Đây là lý do cần idempotency, trạng thái thao tác và khả năng truy vấn kết quả để retry an toàn.

## 12. Bảo mật và tính toàn vẹn của Ajax form

Ajax không làm request đáng tin cậy hơn request thông thường. Mọi dữ liệu vẫn đến từ client và phải được kiểm tra ở server.

- Dùng POST cho thao tác thay đổi dữ liệu và giữ CSRF protection của Spring Security.
- Chỉ bind các trường được phép; không cho form cập nhật trực tiếp owner, role, trạng thái phê duyệt hoặc tenant.
- Kiểm tra quyền truy cập đối tượng trong service trước khi đọc hoặc ghi.
- Kiểm tra execution/session hợp lệ cho từng request.
- Không đưa dữ liệu nhạy cảm vào query string.
- Escape nội dung fragment trước khi chèn vào DOM; tránh dùng thao tác chèn HTML không an toàn với dữ liệu chưa được làm sạch.
- Không coi hidden field, execution key hoặc version do client gửi là bằng chứng quyền.
- Ghi log lỗi đủ để điều tra nhưng không ghi toàn bộ form chứa dữ liệu nhạy cảm.

Nếu fragment chứa form hoặc nút mới, cần bảo đảm các event handler được gắn lại hoặc dùng event delegation. Việc thay DOM có thể loại bỏ handler gắn trực tiếp trên các phần tử cũ.

## 13. Kiểm thử đồng bộ form với nhiều request

Kiểm thử cần tái hiện đúng tình huống request và response chồng lấn, không chỉ kiểm tra từng event riêng lẻ.

| Kịch bản | Điều cần xác minh |
|---|---|
| Hai preview liên tiếp | Preview cũ không ghi đè preview mới |
| Autosave khi người dùng tiếp tục nhập | Thay đổi mới không bị đánh dấu đã lưu nhầm |
| Save khi preview đang chạy | Event save dùng dữ liệu mới nhất và execution hiện tại |
| Hai request cùng execution | Không có cập nhật state sai thứ tự hoặc dùng execution key cũ |
| Response trả về ngược thứ tự | Fragment cũ bị bỏ qua |
| Hai tab cùng sửa hồ sơ | Version conflict được phát hiện và xử lý |
| Double-click nút xác nhận | Nghiệp vụ không bị thực hiện hai lần |
| Mạng mất sau khi server xử lý | Retry không tạo tác động trùng |
| Validation lỗi một trường | Các trường hợp lệ vẫn giữ giá trị |
| Session hoặc execution hết hạn | Người dùng được hướng dẫn đồng bộ lại hoặc bắt đầu lại |

Một kiểm thử tích hợp có thể thực hiện theo trình tự:

1. Khởi chạy flow và mở view-state có form.
2. Gửi Ajax request A với dữ liệu phiên bản 1.
3. Trước khi A hoàn tất, sửa form và tạo request B với phiên bản 2.
4. Kiểm tra client queue có tuần tự hóa hai request nếu chúng cùng thay đổi execution.
5. Kiểm tra response A không thể thay thế fragment đã được cập nhật bởi B.
6. Xác nhận model phía server chứa phiên bản cuối cùng được chấp nhận.
7. Mở tab thứ hai, gửi cập nhật với version cũ và xác nhận optimistic locking hoặc quy tắc conflict hoạt động.
8. Gửi lại thao tác xác nhận với cùng idempotency key và xác nhận chỉ có một kết quả nghiệp vụ.

Nên kiểm thử cả ở cấp JavaScript/client, flow executor/repository và service/database. Một unit test cho hàm debounce không thể chứng minh execution repository xử lý request đồng thời đúng; một flow test không thể chứng minh response cũ không ghi đè DOM.

## 14. Quy trình thiết kế đồng bộ form

Khi một view-state có nhiều Ajax request, hãy xác định:

1. Event nào chỉ đọc, event nào cập nhật model và event nào chuyển state?
2. Request nào cần toàn bộ form, request nào chỉ cần một patch có semantics rõ ràng?
3. Các request nào cùng phụ thuộc vào một flow execution và cần được tuần tự hóa?
4. Response nào có thể cập nhật fragment và cách nhận biết response đã lỗi thời?
5. Execution URL/key mới nhất được lấy và cập nhật ở đâu?
6. Dữ liệu nghiệp vụ có cần version hoặc optimistic locking không?
7. Thao tác có thể retry có cần idempotency key không?
8. Validation, session timeout, stale execution và request lỗi được hiển thị thế nào?
9. Những fragment nào được thay thế và event handler của chúng được duy trì ra sao?
10. Kiểm thử có bao gồm nhiều tab, response đảo thứ tự và request trùng không?

Đồng bộ dữ liệu form khi có nhiều yêu cầu liên tiếp đòi hỏi kiểm soát cả request, response và phiên bản dữ liệu. Khi tuần tự hóa các event cùng execution, gửi đúng dữ liệu, loại response cũ, kiểm tra version ở tầng nghiệp vụ và xử lý retry an toàn, ứng dụng Spring Web Flow có thể cập nhật fragment Ajax mà vẫn giữ form, flow execution và dữ liệu lưu trữ nhất quán.
