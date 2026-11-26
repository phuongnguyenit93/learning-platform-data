# Thiết kế bản nháp lưu bền và cơ chế tiếp tục theo nghiệp vụ

## 1. Vì sao cần bản nháp lưu bền?

Một hành trình Spring Web Flow thường kéo dài qua nhiều HTTP request. Người dùng có thể nhập thông tin, rời trang, đóng trình duyệt, hết phiên đăng nhập hoặc quay lại sau vài giờ. Nếu dữ liệu chỉ nằm trong bộ nhớ của flow execution, ứng dụng có thể không còn đủ thông tin để tiếp tục hành trình khi execution hoặc session hết hạn.

Với các nghiệp vụ như đặt chỗ, đăng ký hồ sơ, tạo đơn hàng hoặc khai báo nhiều bước, người dùng thường cần khả năng:

- Lưu phần thông tin đã nhập và tiếp tục sau.
- Đăng nhập lại rồi mở đúng bản nháp của mình.
- Tiếp tục từ một bước nghiệp vụ hợp lệ sau khi flow execution cũ không còn.
- Tránh mất dữ liệu khi request bị gửi lại hoặc hai tab cùng chỉnh sửa.
- Ngăn người dùng khác đoán ID bản nháp và truy cập dữ liệu.

Giải pháp là lưu **bản nháp nghiệp vụ** vào kho dữ liệu bền vững và dùng Spring Web Flow để điều phối giao diện, state và event. Flow execution có thể được tiếp tục nếu repository còn giữ trạng thái; nếu execution đã hết hạn, ứng dụng có thể tạo execution mới từ bản nháp đã lưu sau khi kiểm tra quyền và trạng thái nghiệp vụ.

Bài học này thuộc chương **Dữ liệu và giao dịch** của module **SPRING_WEB_FLOW**. Khi mô hình hóa hành trình nhiều bước bằng state, event, transition và subflow, cần phân biệt trạng thái điều phối của flow với dữ liệu nghiệp vụ cần tồn tại lâu dài. Việc tách hai loại trạng thái giúp tích hợp Spring MVC, quản lý phiên, xử lý giao dịch và phục hồi luồng có thể dự đoán.

## 2. Phân biệt flow execution với bản nháp nghiệp vụ

Hai loại dữ liệu này phục vụ hai mục đích khác nhau:

| Thành phần | Nội dung | Vòng đời |
| --- | --- | --- |
| Flow execution | State hiện tại, event, scope, dữ liệu điều phối và vị trí tiếp tục flow | Theo repository và chính sách lưu execution của Web Flow |
| Bản nháp nghiệp vụ | Dữ liệu người dùng đã nhập, chủ sở hữu, trạng thái nghiệp vụ, phiên bản và thời hạn | Theo chính sách nghiệp vụ, có thể tồn tại sau khi flow hoặc HTTP session kết thúc |

**FlowExecutionRepository** của Spring Web Flow quản lý việc lưu và khôi phục trạng thái execution theo cấu hình ứng dụng. Repository có thể dùng cơ chế lưu trữ phía máy chủ hoặc continuation theo cấu hình. Khả năng tiếp tục một execution phụ thuộc vào repository, session, execution key và thời hạn lưu trạng thái.

Bản nháp nghiệp vụ nên được lưu riêng trong cơ sở dữ liệu hoặc kho dữ liệu bền vững. Nó không biến mất chỉ vì flow execution không còn được lưu. Khi người dùng quay lại, ứng dụng có thể tải bản nháp, kiểm tra trạng thái và mở một flow execution mới để tiếp tục từ bước phù hợp.

Không nên coi flow execution key là ID bản nháp, hoặc coi việc còn execution key là bằng chứng người dùng có quyền truy cập. Execution key phục vụ định vị trạng thái flow; quyền truy cập bản nháp phải được xác minh ở tầng nghiệp vụ.

~~~mermaid
flowchart TD
    A["Người dùng mở hành trình"] --> B["Spring Web Flow"]
    B --> C["Flow execution repository"]
    C --> D["Lưu/khôi phục state và continuation"]
    B --> E["BookingService"]
    E --> F["Kho bản nháp bền vững"]
    F --> G["Bản nháp, chủ sở hữu, trạng thái, version"]
    H["Người dùng quay lại"] --> I["Xác thực và kiểm tra quyền"]
    I --> F
    F --> J["Tạo hoặc tiếp tục flow phù hợp"]
    J --> B
~~~

Flow điều khiển hành trình; kho dữ liệu nghiệp vụ giữ nội dung cần phục hồi. Hai cơ chế phối hợp với nhau nhưng không thay thế nhau.

## 3. Thiết kế vòng đời của bản nháp

Trước khi triển khai, hãy xác định rõ các trạng thái nghiệp vụ và những chuyển đổi được phép. Một bản nháp đặt chỗ có thể có vòng đời:

| Trạng thái | Ý nghĩa | Hành động được phép |
| --- | --- | --- |
| **DRAFT** | Đang nhập, chưa xác nhận | Sửa, lưu, tiếp tục hoặc hủy |
| **SUBMITTED** | Đã gửi yêu cầu chính thức | Xem kết quả; không sửa như bản nháp |
| **CANCELLED** | Người dùng đã hủy | Xem thông tin hoặc tạo bản mới |
| **EXPIRED** | Quá thời hạn nghiệp vụ | Bắt đầu lại hoặc yêu cầu hỗ trợ theo chính sách |

Không để giao diện quyết định trạng thái chỉ bằng một hidden field. Trạng thái phải được quản lý bởi service/domain ở phía máy chủ. Mỗi command cần kiểm tra trạng thái hiện tại trước khi thay đổi.

Một cấu trúc dữ liệu bản nháp có thể gồm:

| Thuộc tính | Mục đích |
| --- | --- |
| **id** | Định danh bản nháp |
| **ownerId** | Chủ sở hữu được xác định từ ngữ cảnh xác thực |
| **status** | Trạng thái nghiệp vụ hiện tại |
| **version** | Phát hiện cập nhật đồng thời |
| **createdAt**, **updatedAt** | Theo dõi thời điểm tạo và lưu |
| **expiresAt** | Thời hạn bản nháp theo chính sách |
| Các trường nghiệp vụ | Dữ liệu đã nhập cần thiết để tiếp tục |
| **submittedAt** hoặc **completedAt** | Thời điểm hoàn tất nếu có |

Chỉ lưu dữ liệu cần để tiếp tục nghiệp vụ. Không lưu mật khẩu, access token, thông tin thẻ thanh toán hoặc bí mật tích hợp trong bản nháp. Nếu cần tham chiếu tới dữ liệu nhạy cảm, hãy dùng ID hoặc token an toàn được quản lý bởi hệ thống chuyên trách.

## 4. Lưu bản nháp theo các checkpoint nghiệp vụ

Không nhất thiết phải ghi cơ sở dữ liệu sau mỗi lần người dùng thay đổi một ký tự. Hãy xác định các checkpoint có ý nghĩa, chẳng hạn:

- Người dùng chọn “Lưu bản nháp”.
- Người dùng chuyển từ bước thông tin cá nhân sang bước dịch vụ.
- Người dùng hoàn tất một phần quan trọng của biểu mẫu.
- Flow sắp chuyển sang bước xác nhận và cần lưu trạng thái mới nhất.

Mỗi lần lưu nên là một giao dịch ngắn, hoàn tất trước khi phản hồi request. Không mở một transaction cơ sở dữ liệu rồi giữ nó trong suốt thời gian người dùng đọc form hoặc chờ xác nhận. Người dùng có thể dừng nhiều phút hoặc nhiều giờ; transaction dài sẽ giữ lock và tài nguyên kết nối không cần thiết.

Một luồng lưu điển hình:

1. Nhận form model đã được binding.
2. Xác thực cấu trúc và quy tắc nghiệp vụ.
3. Xác định người dùng hiện tại từ security context.
4. Tải bản nháp theo cả ID và chủ sở hữu.
5. Kiểm tra bản nháp còn ở trạng thái có thể sửa.
6. Áp dụng các trường được phép và lưu trong transaction.
7. Trả về version mới cùng thông tin cần hiển thị.

Ví dụ service:

~~~java
@Service
public class BookingDraftService {

    private final BookingDraftRepository repository;
    private final CurrentUserProvider currentUser;
    private final Clock clock;

    public BookingDraftService(
            BookingDraftRepository repository,
            CurrentUserProvider currentUser,
            Clock clock) {
        this.repository = repository;
        this.currentUser = currentUser;
        this.clock = clock;
    }

    @Transactional
    public DraftSnapshot saveDraft(
            String draftId,
            long expectedVersion,
            EditBookingDraftForm form) {

        String ownerId = currentUser.requireUserId();

        BookingDraft draft = repository
            .findByIdAndOwnerId(draftId, ownerId)
            .orElseThrow(DraftNotFoundException::new);

        if (!draft.isEditableAt(clock.instant())) {
            throw new DraftNotEditableException();
        }

        if (draft.getVersion() != expectedVersion) {
            throw new DraftConflictException();
        }

        draft.updateFrom(form);
        draft.touch(clock.instant());

        repository.saveAndFlush(draft);
        return DraftSnapshot.from(draft);
    }
}
~~~

Ví dụ giả định entity dùng optimistic locking và repository có truy vấn theo cả ID lẫn owner ID. Phương thức updateFrom chỉ áp dụng những trường được phép của form model; nó không sao chép toàn bộ request vào entity. Việc kiểm tra version tường minh giúp trả lỗi xung đột dễ hiểu; annotation @Version ở entity vẫn cần để cơ sở dữ liệu phát hiện race condition xảy ra giữa lúc đọc và lúc ghi.

## 5. Chống ghi đè khi nhiều tab hoặc nhiều request cùng sửa

Người dùng có thể mở cùng bản nháp ở hai tab. Tab A và tab B đều đọc version 4. Sau đó tab A lưu trước, tạo version 5. Nếu tab B tiếp tục ghi mà không kiểm tra version, dữ liệu mới của A có thể bị ghi đè.

Dùng optimistic locking để phát hiện trường hợp này:

~~~java
@Entity
public class BookingDraft {

    @Id
    private String id;

    private String ownerId;

    @Enumerated(EnumType.STRING)
    private DraftStatus status;

    @Version
    private long version;

    // Các trường dữ liệu nghiệp vụ và phương thức domain.
}
~~~

Form hoặc command gửi kèm version đã đọc. Khi lưu, service kiểm tra version mong đợi và cập nhật trong transaction. Nếu version không còn khớp, ứng dụng nên:

- Giữ bản nháp đã lưu trước đó.
- Thông báo rằng dữ liệu đã được cập nhật ở nơi khác.
- Cho phép tải lại dữ liệu mới và người dùng quyết định chỉnh sửa lại.
- Tránh tự động ghi đè mà không có quy tắc hợp nhất rõ ràng.

@Version không thay thế kiểm tra quyền sở hữu hoặc kiểm tra trạng thái. Nó chỉ giúp phát hiện xung đột cập nhật đồng thời.

Nếu nghiệp vụ cho phép nhiều người cùng chỉnh sửa, cần thiết kế chính sách cộng tác riêng, ví dụ khóa chỉnh sửa, phân vùng trường dữ liệu hoặc cơ chế hợp nhất. Không mặc định rằng một bản nháp có thể được nhiều người sửa an toàn chỉ vì mỗi request đều có transaction.

## 6. Tổ chức flow để lưu và tiếp tục bản nháp

Flow nên giữ ID bản nháp và các dữ liệu tạm cần thiết để điều phối. Nội dung bền vững được đọc và ghi qua service. Một form DTO nhỏ giúp giới hạn dữ liệu binding.

Ví dụ minh họa flow:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="draftId" type="java.lang.String"/>

    <on-start>
        <evaluate
            expression="bookingDraftService.loadFormForCurrentUser(draftId)"
            result="flowScope.draftForm"/>
    </on-start>

    <view-state id="details"
                view="booking/details"
                model="draftForm">
        <transition on="saveAndContinue" to="saveAndReview"/>
        <transition on="saveForLater" to="saveDraft"/>
    </view-state>

    <action-state id="saveDraft">
        <evaluate
            expression="bookingDraftService.saveDraft(
                draftId,
                flowScope.draftForm.version,
                flowScope.draftForm)"/>
        <transition on="success" to="saved"/>
    </action-state>

    <action-state id="saveAndReview">
        <evaluate
            expression="bookingDraftService.saveDraft(
                draftId,
                flowScope.draftForm.version,
                flowScope.draftForm)"/>
        <transition on="success" to="review"/>
    </action-state>

    <view-state id="review" view="booking/review">
        <transition on="confirm" to="submit"/>
        <transition on="edit" to="details"/>
    </view-state>

    <action-state id="submit">
        <evaluate expression="bookingDraftService.submitDraft(draftId)"/>
        <transition on="success" to="completed"/>
    </action-state>

    <end-state id="saved"/>
    <end-state id="completed"/>
</flow>
~~~

Đây là ví dụ mô tả cấu trúc, cần điều chỉnh cú pháp expression, mapping form và cách xử lý validation theo phiên bản Web Flow của dự án. Các action-state tách event người dùng khỏi thao tác persistence. Trong triển khai thực tế, service cần nhận version mong đợi, trả kết quả hoặc phát sinh lỗi nghiệp vụ phù hợp; flow phải có nhánh xử lý validation và conflict.

## 7. Tiếp tục theo nghiệp vụ khi flow execution còn tồn tại

Khi người dùng quay lại và flow execution cũ vẫn còn trong repository, ứng dụng có thể tiếp tục execution đó theo cơ chế Web Flow. Execution key hoặc continuation được sử dụng để tìm trạng thái tương ứng, tùy cấu hình repository.

Tuy nhiên, trước khi xử lý request tiếp tục, ứng dụng vẫn cần bảo đảm:

- Người dùng đã xác thực và session còn hợp lệ.
- Bản nháp thuộc người dùng hiện tại hoặc người dùng có quyền truy cập.
- Trạng thái nghiệp vụ vẫn cho phép tiếp tục.
- Thời hạn bản nháp chưa hết.
- Các điều kiện có thể thay đổi từ lần lưu trước đã được kiểm tra lại.

Flow state có thể đã được lưu từ trước, trong khi bản nháp trong cơ sở dữ liệu đã thay đổi bởi một request khác hoặc một quy trình nền. Vì vậy, không nên tin tuyệt đối dữ liệu snapshot trong flow scope cho những quyết định nghiệp vụ quan trọng. Trước khi xác nhận, service cần tải hoặc kiểm tra lại trạng thái bền vững.

## 8. Khôi phục khi flow execution đã hết hạn

Nếu session hết hạn, execution bị xóa hoặc continuation không còn hợp lệ, người dùng có thể không tiếp tục được flow cũ. Đây không nhất thiết là mất bản nháp. Nếu bản nháp đã được lưu bền vững, ứng dụng có thể bắt đầu một flow execution mới.

Quy trình tiếp tục từ bản nháp:

1. Người dùng mở danh sách bản nháp hoặc liên kết tiếp tục.
2. Ứng dụng xác thực người dùng.
3. Service tải bản nháp bằng ID và owner ID; không chỉ tìm theo ID.
4. Service kiểm tra trạng thái, thời hạn và quyền tiếp tục.
5. Ứng dụng xác định state nghiệp vụ phù hợp để bắt đầu flow mới.
6. Flow mới tải form model từ bản nháp và tiếp tục hành trình.
7. Trước thao tác quan trọng, service kiểm tra lại version và trạng thái.

~~~mermaid
flowchart TD
    A["Người dùng chọn Tiếp tục bản nháp"] --> B{"Execution cũ còn hợp lệ?"}
    B -- "Có" --> C["Khôi phục flow execution"]
    B -- "Không" --> D["Xác thực người dùng"]
    D --> E["Tải bản nháp theo ID và owner"]
    E --> F{"Còn hạn và được phép tiếp tục?"}
    F -- "Không" --> G["Thông báo hết hạn hoặc không có quyền"]
    F -- "Có" --> H["Tạo flow execution mới"]
    H --> I["Nạp dữ liệu từ bản nháp"]
    C --> J["Kiểm tra trạng thái nghiệp vụ"]
    I --> J
    J --> K["Tiếp tục từ bước phù hợp"]
~~~

Không nên cố tái tạo chính xác state UI cũ bằng cách đọc dữ liệu tùy ý từ URL. Bản nháp bền vững nên mô tả tiến trình nghiệp vụ, ví dụ DETAILS_COMPLETED hoặc WAITING_FOR_REVIEW, rồi flow mới chọn state dựa trên trạng thái đó. Cách này giúp thay đổi giao diện hoặc flow definition mà không làm dữ liệu bản nháp phụ thuộc vào ID state cũ.

Nếu flow definition thay đổi giữa hai lần người dùng quay lại, cần cân nhắc workflowVersion hoặc schemaVersion trong bản nháp. Khi phiên bản cũ không còn tương thích, service có thể chuyển đổi dữ liệu, yêu cầu người dùng xác nhận lại hoặc đưa bản nháp vào trạng thái cần hỗ trợ.

## 9. Hết hạn, dọn dẹp và chính sách lưu giữ

Bản nháp cần có thời hạn nghiệp vụ. Ví dụ, một báo giá có thể chỉ có hiệu lực trong 24 giờ; một đơn đăng ký có thể được giữ 30 ngày. Thời hạn cần được lưu ở server và kiểm tra khi tiếp tục hoặc submit.

Một tác vụ dọn dẹp có thể đánh dấu bản nháp quá hạn thành EXPIRED, sau đó xóa hoặc ẩn dữ liệu theo chính sách lưu giữ. Không nên chỉ dựa vào việc xóa HTTP session để dọn bản nháp, vì bản nháp bền vững có vòng đời độc lập.

Chính sách lưu giữ nên xác định:

- Thời gian bản nháp có thể được tiếp tục.
- Dữ liệu nào được giữ sau khi hết hạn.
- Khi nào xóa dữ liệu cá nhân không còn cần thiết.
- Cách xử lý bản nháp đã gửi hoặc đã hủy.
- Cách thông báo cho người dùng khi không thể tiếp tục.

Khi người dùng mở một bản nháp đã hết hạn, không khôi phục nó vào flow như thể vẫn hợp lệ. Hãy hiển thị trạng thái rõ ràng và cung cấp hành động phù hợp, ví dụ tạo yêu cầu mới hoặc liên hệ hỗ trợ.

## 10. Giao dịch khi xác nhận và tránh xử lý trùng

Lưu bản nháp và xác nhận nghiệp vụ là hai thao tác khác nhau. Người dùng có thể bấm xác nhận nhiều lần, trình duyệt gửi lại request hoặc mạng bị ngắt sau khi server đã xử lý nhưng trước khi phản hồi đến trình duyệt.

Service xác nhận cần có tính idempotent: cùng một yêu cầu xác nhận được gửi lặp lại không tạo nhiều đơn hàng hoặc nhiều khoản thanh toán. Có thể dùng một request ID/idempotency key được tạo và quản lý phía server, cùng ràng buộc duy nhất trong kho dữ liệu.

Ví dụ về nguyên tắc xử lý:

~~~java
@Transactional
public SubmissionResult submitDraft(
        String draftId,
        String idempotencyKey) {

    String ownerId = currentUser.requireUserId();

    SubmissionResult previous =
        submissionRepository.findByIdempotencyKey(idempotencyKey);

    if (previous != null) {
        return previous;
    }

    BookingDraft draft = repository
        .findByIdAndOwnerId(draftId, ownerId)
        .orElseThrow(DraftNotFoundException::new);

    draft.validateForSubmission();
    draft.markSubmitted(clock.instant());

    SubmissionResult result = submissionRepository
        .createForDraft(draft, idempotencyKey);

    return result;
}
~~~

Đây là ví dụ khái niệm. Trong triển khai thực tế, cần ràng buộc unique cho idempotency key và xử lý xung đột đồng thời trong transaction. Không chỉ dựa vào câu lệnh kiểm tra trước vì hai request có thể cùng kiểm tra “chưa tồn tại” rồi cùng tạo bản ghi.

Nếu bước xác nhận cần gọi hệ thống ngoài như cổng thanh toán hoặc gửi thông báo, không giữ transaction cơ sở dữ liệu mở trong lúc chờ mạng. Có thể lưu trạng thái yêu cầu và outbox event trong cùng transaction, sau đó worker xử lý tác vụ ngoài theo cơ chế retry/idempotency. Flow chỉ chuyển tới trạng thái hoàn tất khi kết quả nghiệp vụ đạt điều kiện tương ứng.

## 11. Bảo mật khi tiếp tục bản nháp

ID bản nháp không phải bí mật và cũng không phải bằng chứng quyền sở hữu. Một người dùng có thể sửa ID trong URL hoặc gửi request thủ công. Mọi thao tác đọc, lưu, tiếp tục, hủy và submit đều phải kiểm tra quyền ở service.

Các nguyên tắc quan trọng:

- Lấy ownerId từ danh tính đã xác thực ở server.
- Truy vấn bản nháp bằng cả ID và owner ID hoặc thực hiện authorization tương đương.
- Không tin owner ID, status, giá tiền hay bước hiện tại do client gửi.
- Dùng CSRF protection cho request thay đổi dữ liệu theo cấu hình bảo mật của ứng dụng.
- Không đưa dữ liệu cá nhân hoặc bí mật vào query string, execution key hoặc log.
- Kiểm tra quyền lại khi người dùng tiếp tục flow sau một khoảng thời gian dài.
- Không để flow key thay thế kiểm tra quyền truy cập bản nháp.

Với liên kết tiếp tục được gửi qua email, cần dùng token ngẫu nhiên khó đoán, có thời hạn, có thể thu hồi và chỉ cho phép hành động được giới hạn. Sau khi token được sử dụng, vẫn nên yêu cầu đăng nhập hoặc thực hiện bước xác minh phù hợp với mức độ nhạy cảm của nghiệp vụ.

## 12. Kiểm thử lưu bền và tiếp tục theo nghiệp vụ

Kiểm thử cần bao phủ cả flow execution và kho bản nháp.

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Lưu và tiếp tục bình thường | Lưu bản nháp, mở lại trong cùng phiên | Form được nạp với dữ liệu đã lưu |
| Tiếp tục sau khi session hết hạn | Giữ bản nháp trong DB, làm execution cũ không còn | Flow mới được tạo từ bản nháp sau kiểm tra quyền |
| Người dùng khác mở ID bản nháp | Đăng nhập bằng tài khoản khác | Không đọc hoặc sửa được bản nháp |
| Bản nháp hết hạn | expiresAt đã qua | Không cho tiếp tục hoặc submit |
| Hai tab cùng lưu | Cả hai đọc cùng version rồi lần lượt cập nhật | Lần ghi cũ nhận xung đột, không ghi đè âm thầm |
| Submit bị gửi lặp | Gửi cùng idempotency key nhiều lần | Chỉ có một kết quả nghiệp vụ |
| Flow definition đổi phiên bản | Bản nháp có workflow version cũ | Chuyển đổi hoặc xử lý tương thích theo chính sách |
| Lỗi hệ thống ngoài | Gateway lỗi sau khi ghi yêu cầu | Có thể retry an toàn, không tạo giao dịch trùng |

Nên có các nhóm kiểm thử riêng:

- **Unit test service:** kiểm tra quyền sở hữu, trạng thái, version, thời hạn và idempotency.
- **Flow test:** kiểm tra state, event, transition và hành vi gọi service lưu/tiếp tục.
- **Integration test repository:** xác nhận @Version, unique constraint và transaction thực sự hoạt động với cơ sở dữ liệu kiểm thử.
- **MVC/security test:** kiểm tra đăng nhập, CSRF và quyền truy cập khi mở liên kết tiếp tục.
- **Recovery test:** mô phỏng execution không còn, sau đó tạo flow mới từ bản nháp.

Đừng chỉ kiểm tra rằng trang được render. Cần xác nhận dữ liệu đúng chủ sở hữu, đúng version, trạng thái nghiệp vụ hợp lệ và các thao tác không bị thực hiện lặp.

## 13. Quy trình thiết kế cơ chế lưu và tiếp tục

Khi thêm khả năng lưu bản nháp cho một flow, hãy thực hiện theo trình tự:

1. **Xác định dữ liệu cần phục hồi.** Phân biệt dữ liệu nghiệp vụ bền vững với dữ liệu điều phối UI tạm thời.
2. **Định nghĩa vòng đời bản nháp.** Chọn status, thời hạn, quyền tiếp tục và điều kiện submit.
3. **Thiết kế schema và version.** Lưu owner, version, thời điểm cập nhật và workflow/schema version nếu cần.
4. **Tạo service giao dịch ngắn.** Lưu từng checkpoint qua transaction riêng; không giữ transaction trong lúc người dùng suy nghĩ.
5. **Giới hạn dữ liệu đầu vào.** Dùng form model riêng, validate phía server và ánh xạ trường được phép.
6. **Bảo vệ truy cập.** Kiểm tra owner và quyền ở mọi thao tác với bản nháp.
7. **Tạo đường tiếp tục.** Nếu execution còn hợp lệ thì khôi phục; nếu không, tải bản nháp và tạo flow mới từ trạng thái nghiệp vụ.
8. **Xử lý đồng thời và gửi lặp.** Dùng optimistic locking, idempotency key và ràng buộc dữ liệu phù hợp.
9. **Định nghĩa chính sách hết hạn.** Đánh dấu, dọn dẹp và thông báo theo vòng đời nghiệp vụ.
10. **Kiểm thử phục hồi.** Bao gồm session hết hạn, execution mất, người dùng khác, hai tab và request submit lặp.

Ví dụ, một flow đặt chỗ lưu draftId và draftForm trong flow scope. Mỗi checkpoint gọi BookingDraftService để ghi dữ liệu vào cơ sở dữ liệu. Khi người dùng quay lại, service tải bản nháp theo ID và người dùng hiện tại. Nếu execution cũ đã hết hạn, flow mới được khởi chạy từ bản nháp và chọn state phù hợp theo trạng thái nghiệp vụ. Khi xác nhận, service kiểm tra version, quyền, thời hạn và idempotency trước khi tạo kết quả chính thức.

## 14. Tự kiểm tra

- FlowExecutionRepository và kho bản nháp có cùng nhiệm vụ không? Không. Repository của Web Flow lưu/khôi phục execution; kho bản nháp lưu dữ liệu nghiệp vụ cần tồn tại lâu dài.
- Vì sao không nên giữ transaction trong toàn bộ flow? Vì flow có thể chờ người dùng lâu, làm giữ connection và lock không cần thiết.
- Dữ liệu bản nháp nên được lưu khi nào? Tại các checkpoint nghiệp vụ đã xác định hoặc khi người dùng chủ động lưu.
- Làm sao ngăn hai tab ghi đè nhau? Dùng optimistic locking/version và xử lý xung đột rõ ràng.
- Có thể tiếp tục khi flow execution đã hết hạn không? Có, nếu bản nháp còn hợp lệ; xác thực người dùng, kiểm tra quyền và tạo execution mới từ dữ liệu bền vững.
- Chỉ biết ID bản nháp có đủ để truy cập không? Không. Service phải kiểm tra owner và quyền nghiệp vụ.
- Vì sao submit cần idempotency? Để request gửi lặp không tạo nhiều kết quả nghiệp vụ.
- Có nên tin state hoặc giá trị trong flow scope khi xác nhận không? Không cho các quyết định quan trọng; service cần kiểm tra lại dữ liệu bền vững và điều kiện hiện tại.
- Bản nháp hết hạn nên xử lý thế nào? Từ chối tiếp tục theo chính sách, thông báo rõ và cung cấp bước tiếp theo phù hợp.

Thiết kế bản nháp lưu bền tách vòng đời nghiệp vụ khỏi vòng đời của flow execution. Khi kết hợp transaction ngắn, kiểm tra quyền, optimistic locking, idempotency và cơ chế khởi tạo flow mới từ bản nháp, Spring Web Flow có thể hỗ trợ người dùng tiếp tục hành trình an toàn ngay cả khi phiên hoặc execution cũ không còn.

