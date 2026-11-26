# Tránh ghi sớm các chỉnh sửa còn đang chờ xác nhận

Trong chương **Dữ liệu và giao dịch**, bài này giải thích cách giữ các chỉnh sửa của người dùng ở trạng thái chờ xác nhận trong một hành trình Spring Web Flow, rồi chỉ ghi thay đổi nghiệp vụ chính thức tại thời điểm thích hợp. Với module **SPRING_WEB_FLOW**, state, event, transition và subflow tổ chức quy trình nhiều bước; form binding đưa dữ liệu từ request vào model; scope giữ bản nháp giữa các bước. Ranh giới giao dịch cần được thiết kế sao cho việc người dùng nhập, xem lại, quay lại hoặc hủy không vô tình làm thay đổi dữ liệu đã được xác nhận trong hệ thống.

Một quy trình đặt hàng là ví dụ dễ thấy. Người dùng có thể thay địa chỉ, chọn phương thức giao hàng và nhập mã khuyến mãi trước khi bấm “Xác nhận”. Nếu mỗi lần rời một màn hình ứng dụng đều cập nhật đơn hàng thật, đơn có thể bị thay đổi dù người dùng chưa đồng ý. Khi họ quay lại hoặc đóng trình duyệt, dữ liệu chính thức đã bị ghi một phần và rất khó xác định đâu là lựa chọn cuối cùng.

## Phân biệt bản nháp với thay đổi đã xác nhận

Trong flow nhiều bước, dữ liệu thường đi qua ba trạng thái có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Nơi giữ phù hợp |
|---|---|---|
| Bản nháp (draft) | Các giá trị người dùng đang nhập hoặc chỉnh sửa, có thể thay đổi hoặc bị hủy | DTO trong flow scope; hoặc kho draft riêng nếu cần lưu lâu dài |
| Đã kiểm tra (validated) | Dữ liệu đã qua kiểm tra tại một bước, nhưng vẫn có thể cần kiểm tra lại trước khi xác nhận | Bản nháp cùng kết quả kiểm tra có thời hạn |
| Đã xác nhận (committed) | Thay đổi nghiệp vụ đã được chấp nhận và ghi nhận chính thức | Aggregate và kho dữ liệu nghiệp vụ trong transaction |

Binding một form vào DTO không đồng nghĩa với ghi dữ liệu vào cơ sở dữ liệu. Tương tự, việc flow chuyển từ view-state nhập liệu sang view-state xem lại không có nghĩa nghiệp vụ đã hoàn tất.

~~~mermaid
flowchart TD
    A["Mở flow / tải dữ liệu hiện tại"] --> B["Tạo bản nháp"]
    B --> C["Nhập và chỉnh sửa form"]
    C --> D["Bind vào draft trong flow"]
    D --> E["Kiểm tra dữ liệu và hiển thị review"]
    E -->|"Quay lại sửa"| C
    E -->|"Hủy"| F["Bỏ draft"]
    E -->|"Xác nhận"| G["Service kiểm tra lại"]
    G --> H{"Điều kiện còn hợp lệ?"}
    H -->|"Không"| I["Trả lỗi hoặc yêu cầu cập nhật draft"]
    I --> E
    H -->|"Có"| J["Transaction ghi dữ liệu chính thức"]
    J --> K["Hoàn tất flow"]
~~~

Mô hình này tạo ra một ranh giới rõ ràng: các state nhập liệu chỉ thay đổi bản nháp; một thao tác xác nhận cuối gọi service nghiệp vụ để kiểm tra và ghi dữ liệu. Nếu người dùng hủy trước thời điểm đó, bản nháp có thể bị bỏ mà không cần hoàn tác các thay đổi trên aggregate chính.

## Vì sao không nên giữ transaction xuyên suốt flow?

Spring Web Flow thường xử lý một hành trình qua nhiều HTTP request. Người dùng có thể mất vài phút hoặc lâu hơn để đi qua các bước, đọc thông tin, sửa dữ liệu hay tạm rời trang. Một transaction cơ sở dữ liệu không nên được mở từ lúc bắt đầu flow và giữ đến khi người dùng bấm xác nhận.

Transaction dài có thể giữ lock, chiếm connection, làm tăng nguy cơ deadlock và khiến tài nguyên cơ sở dữ liệu bị giữ trong thời gian người dùng không hoạt động. Ngoài ra, một transaction thường không thể sống an toàn qua nhiều request hoặc qua một lần deploy/restart ứng dụng.

Thay vào đó, mỗi lần gọi service cần ghi dữ liệu nên có transaction ngắn, rõ mục đích. Trong phần lớn hành trình, flow chỉ thao tác với DTO bản nháp. Ở bước xác nhận, service mở transaction, tải dữ liệu nghiệp vụ hiện tại, kiểm tra điều kiện, ghi thay đổi và commit.

| Thời điểm | Việc nên làm | Ranh giới transaction |
|---|---|---|
| Khởi chạy flow | Tải dữ liệu hiện tại và tạo draft | Transaction đọc ngắn nếu cần |
| Người dùng nhập form | Bind các trường cho phép vào draft | Không cần transaction ghi aggregate |
| Chuyển sang màn hình xem lại | Kiểm tra dữ liệu đầu vào và tính thông tin xem trước | Có thể gọi service đọc/tính toán ngắn |
| Quay lại hoặc hủy | Sửa draft hoặc bỏ draft | Không ghi aggregate chỉ vì điều hướng |
| Xác nhận cuối | Kiểm tra lại và ghi thay đổi chính thức | Một transaction nghiệp vụ ngắn |
| Gửi thông báo hoặc gọi dịch vụ ngoài | Phát sự kiện sau khi thay đổi được commit | Dùng cơ chế phát sự kiện tin cậy; không giữ transaction mở chờ mạng |

Không đặt **@Transactional** ở một phương thức điều phối toàn bộ flow rồi mong transaction được giữ qua các request. Đặt ranh giới ở service nghiệp vụ thực hiện một thao tác nhất quán. Cấu hình transaction thực tế còn phụ thuộc propagation, transaction manager và cách service được gọi qua Spring proxy.

## Giữ thay đổi chờ xác nhận trong flow scope

Một DTO dành riêng cho form giúp tách dữ liệu người dùng được phép sửa khỏi entity nghiệp vụ. DTO có thể chứa giá trị đề xuất, ID của aggregate và phiên bản mà người dùng đã xem khi bắt đầu chỉnh sửa.

Ví dụ:

~~~java
public class BookingDraft {
    private String bookingId;
    private long expectedVersion;

    private String recipient;
    private String addressLine;
    private String postalCode;
    private String deliveryMethod;
    private String promotionCode;

    public String getBookingId() {
        return bookingId;
    }

    public long getExpectedVersion() {
        return expectedVersion;
    }

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public String getAddressLine() {
        return addressLine;
    }

    public void setAddressLine(String addressLine) {
        this.addressLine = addressLine;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }

    public String getDeliveryMethod() {
        return deliveryMethod;
    }

    public void setDeliveryMethod(String deliveryMethod) {
        this.deliveryMethod = deliveryMethod;
    }

    public String getPromotionCode() {
        return promotionCode;
    }

    public void setPromotionCode(String promotionCode) {
        this.promotionCode = promotionCode;
    }
}
~~~

Đây là ví dụ rút gọn; constructor/factory của ứng dụng sẽ tạo DTO từ dữ liệu đã tải. Các trường như giá cuối cùng, trạng thái thanh toán, chủ sở hữu hoặc quyền phê duyệt không nên được tin từ request. Chúng phải được xác định lại từ dữ liệu và quy tắc phía server.

Trong flow, biến draft có thể được giữ xuyên suốt các view-state:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="bookingDraft"
         class="com.example.booking.BookingDraft" />

    <action-state id="loadDraft">
        <evaluate expression="bookingService.loadEditableDraft(bookingId)"
                  result="flowScope.bookingDraft" />
        <transition to="details" />
    </action-state>

    <view-state id="details"
                view="booking/details"
                model="bookingDraft">
        <binder>
            <binding property="recipient" />
            <binding property="addressLine" />
            <binding property="postalCode" />
            <binding property="deliveryMethod" />
            <binding property="promotionCode" />
        </binder>
        <transition on="review" to="review" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="details" />
        <transition on="confirm" to="commitBooking" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <action-state id="commitBooking">
        <evaluate expression="bookingCommandService.confirm(flowScope.bookingDraft)"
                  result="flowScope.confirmation" />
        <transition to="completed" />
    </action-state>

    <end-state id="completed" />
    <end-state id="cancelled" />
</flow>
~~~

Ví dụ cho thấy các view-state làm việc với **bookingDraft**; action-state cuối gọi service xác nhận. Trong ứng dụng thật, flow cần xử lý rõ các kết quả validation, lỗi nghiệp vụ và lỗi đồng thời trước khi đi tới end-state. Không được chuyển sang completed nếu service chưa xác nhận commit thành công.

**flowScope** giữ dữ liệu trong vòng đời của flow execution. Nó không tự làm dữ liệu trở nên bền vững qua mọi loại restart và cũng không thay thế repository hay kho lưu trữ draft. Nếu repository yêu cầu serialization, DTO cùng object graph phải phù hợp với cơ chế lưu snapshot. Nếu người dùng cần quay lại sau nhiều giờ hoặc nhiều ngày, cân nhắc lưu draft riêng trong cơ sở dữ liệu với quyền sở hữu và thời hạn rõ ràng.

## Chỉ ghi aggregate ở bước xác nhận cuối

Service xác nhận nên thực hiện toàn bộ kiểm tra cần thiết trong một transaction ngắn. Service tải aggregate mới nhất, xác minh người dùng có quyền thao tác, kiểm tra phiên bản, tính lại các giá trị quan trọng và lưu thay đổi.

Ví dụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookingCommandService {
    private final BookingRepository bookingRepository;
    private final ShippingService shippingService;
    private final PromotionService promotionService;

    public BookingCommandService(
            BookingRepository bookingRepository,
            ShippingService shippingService,
            PromotionService promotionService) {
        this.bookingRepository = bookingRepository;
        this.shippingService = shippingService;
        this.promotionService = promotionService;
    }

    @Transactional
    public Confirmation confirm(BookingDraft draft, String actorId) {
        Booking booking = bookingRepository
                .findById(draft.getBookingId())
                .orElseThrow(BookingNotFoundException::new);

        booking.assertCanBeEditedBy(actorId);
        booking.assertVersion(draft.getExpectedVersion());

        ShippingQuote quote = shippingService.quote(
                draft.getAddressLine(),
                draft.getPostalCode(),
                draft.getDeliveryMethod());

        Promotion promotion =
                promotionService.findApplicable(draft.getPromotionCode(), booking);

        booking.updatePendingDetails(
                draft.getRecipient(),
                draft.getAddressLine(),
                draft.getPostalCode(),
                draft.getDeliveryMethod(),
                quote,
                promotion);

        booking.confirm();
        bookingRepository.save(booking);

        return Confirmation.from(booking);
    }
}
~~~

Tên lớp và phương thức trong ví dụ là minh họa. Trong triển khai thật, **actorId** phải lấy từ ngữ cảnh xác thực phía server; không nhận danh tính người dùng từ DTO. **assertVersion** có thể được triển khai bằng kiểm tra phiên bản nghiệp vụ hoặc optimistic locking với trường **@Version** trên entity. Khi có thay đổi đồng thời, service cần trả kết quả xung đột để flow yêu cầu tải lại hoặc xác nhận lại dữ liệu.

Tất cả thao tác cần nhất quán trong cùng transaction phải tham gia cùng transaction manager. Nếu việc cập nhật booking, ghi lịch sử và tạo bản ghi outbox cùng nằm trong một cơ sở dữ liệu, chúng có thể được commit hoặc rollback cùng nhau. Nếu service gọi hệ thống ngoài qua HTTP, transaction cơ sở dữ liệu không thể tự rollback tác động đã xảy ra ở hệ thống đó.

Không nên cập nhật từng trường của aggregate ngay khi người dùng rời từng view-state, rồi hy vọng nút hủy sẽ đưa dữ liệu trở lại như cũ. Việc phục hồi sau khi commit cần một nghiệp vụ bù riêng và có thể không đảo ngược được mọi tác động.

## Khi cần tự động lưu bản nháp

Một số quy trình cần giữ dữ liệu nếu người dùng đóng trình duyệt hoặc mất kết nối. Trong trường hợp đó, có thể tự động lưu vào một kho draft riêng. Bản ghi draft có thể có các trường như:

| Trường | Mục đích |
|---|---|
| draftId | Định danh bản nháp |
| ownerId | Người dùng hoặc chủ thể sở hữu |
| aggregateId | Aggregate nghiệp vụ đang được chỉnh sửa |
| payload | Dữ liệu nháp đã được kiểm soát |
| status | PENDING, SUBMITTED, DISCARDED hoặc EXPIRED |
| expiresAt | Thời điểm bản nháp hết hạn |
| version | Phiên bản để kiểm soát cập nhật đồng thời |

Autosave vào bảng draft vẫn là một lần ghi cơ sở dữ liệu, nhưng nó không làm thay đổi aggregate đã xác nhận. Khi người dùng bấm xác nhận, service tải draft, kiểm tra lại quyền và trạng thái aggregate, rồi áp dụng các thay đổi vào aggregate trong transaction. Sau khi commit thành công, draft được đánh dấu đã gửi hoặc đóng theo cùng quy tắc nhất quán.

Cần tránh dùng một bảng draft như nơi lưu dữ liệu không có giới hạn. Hãy quy định thời hạn, quyền đọc/ghi, dọn dữ liệu hết hạn và cách xử lý hai tab cùng sửa một draft. Nếu dữ liệu nháp nhạy cảm, cần giới hạn field được lưu và bảo vệ dữ liệu theo chính sách của ứng dụng.

## Validation trước và trong lúc xác nhận

Validation ở từng bước giúp người dùng sửa lỗi sớm, nhưng kết quả đó có thể trở nên cũ khi họ tiếp tục hành trình. Giá, tồn kho, khuyến mãi, quyền sở hữu hoặc trạng thái booking có thể thay đổi giữa lúc xem lại và lúc bấm xác nhận.

Có thể chia kiểm tra thành ba lớp:

- **Kiểm tra form:** định dạng, trường bắt buộc, giới hạn độ dài và kiểu dữ liệu khi người dùng rời màn hình.
- **Kiểm tra nghiệp vụ trước xem lại:** tính báo giá, xác định vùng phục vụ, kiểm tra các lựa chọn có thể thực hiện tại thời điểm đó.
- **Kiểm tra cuối trong service:** xác minh lại quyền, trạng thái hiện tại, giá/tồn kho/khuyến mãi, phiên bản aggregate và các điều kiện cần thiết trước commit.

Ví dụ, flow có thể hiển thị phí giao hàng ước tính ở màn hình review. Khi người dùng xác nhận, service phải kiểm tra báo giá còn hiệu lực hoặc tính lại. Nếu phí thay đổi, flow có thể trả người dùng về màn hình review để họ chấp nhận mức mới. Không được âm thầm ghi một giá trị khác với nội dung người dùng đã xác nhận.

## Xử lý xung đột và gửi lặp

Trong hành trình dài, một người dùng khác hoặc một tiến trình nền có thể thay đổi aggregate trước khi flow hiện tại xác nhận. Đây là lý do cần lưu **expectedVersion** lúc tạo draft và kiểm tra lại ở thời điểm commit.

Nếu phiên bản đã thay đổi, service có thể phát sinh xung đột lạc quan. Flow nên thông báo dữ liệu đã được cập nhật, tải lại trạng thái mới và cho người dùng xem xét lại các thay đổi. Không nên tự ghi đè dữ liệu mới bằng bản nháp cũ.

Người dùng cũng có thể nhấn xác nhận nhiều lần, refresh trang hoặc trình duyệt gửi lại request. Một lệnh xác nhận cần có khóa idempotency hoặc cơ chế kiểm tra trạng thái để cùng một ý định không tạo nhiều đơn hàng, lần thanh toán hay hành động phê duyệt. Có thể lưu command ID duy nhất cùng kết quả xử lý trong transaction.

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| Hai người cùng sửa một booking | Bản nháp cũ ghi đè thay đổi mới | Optimistic locking/version check |
| Người dùng nhấn Confirm hai lần | Tạo hai giao dịch nghiệp vụ | Idempotency key và kiểm tra trạng thái |
| Giá thay đổi sau màn hình review | Người dùng xác nhận một giá khác | Tính lại, yêu cầu xác nhận lại khi cần |
| Draft hết hạn | Áp dụng dữ liệu không còn phù hợp | Kiểm tra expiry và yêu cầu tạo draft mới |
| Request gửi lại sau commit | Xử lý lặp một lệnh đã thành công | Trả lại kết quả đã ghi nhận cho cùng command ID |

## Tác động ngoài cơ sở dữ liệu và transaction outbox

Một transaction cơ sở dữ liệu chỉ kiểm soát các thay đổi tham gia transaction manager đó. Gửi email, gọi cổng thanh toán, đặt chỗ ở dịch vụ ngoài hoặc phát thông điệp trực tiếp tới broker không tự động được rollback khi transaction cơ sở dữ liệu thất bại.

Nếu service xác nhận booking cần phát sự kiện sau commit, có thể ghi một bản ghi outbox trong cùng transaction với aggregate. Một tiến trình riêng đọc outbox và gửi sự kiện tới broker; nó đánh dấu đã gửi hoặc retry theo chính sách. Cách này giúp tránh trường hợp aggregate đã commit nhưng thông điệp bị mất vì ứng dụng dừng giữa hai thao tác.

~~~mermaid
flowchart TD
    A["Flow gửi lệnh confirm"] --> B["Command service"]
    B --> C["Mở transaction"]
    C --> D["Kiểm tra và cập nhật aggregate"]
    D --> E["Ghi outbox event"]
    E --> F{"Commit transaction"}
    F -->|"Thành công"| G["Aggregate và outbox cùng tồn tại"]
    F -->|"Rollback"| H["Không có thay đổi chính thức"]
    G --> I["Outbox publisher"]
    I --> J["Broker / hệ thống ngoài"]
    J --> K["Consumer xử lý idempotent"]
~~~

Với quy trình thanh toán hoặc đặt chỗ nhiều hệ thống, có thể cần saga và hành động bù. Hủy một booking đã commit không giống rollback transaction ban đầu; nó là một nghiệp vụ mới có quy tắc riêng. Hãy mô hình hóa rõ trạng thái và hành động bù, thay vì dựa vào việc quay lại state trong flow để đảo ngược tác động ngoài.

## Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Đơn hàng thay đổi dù người dùng chưa xác nhận | Service ghi aggregate ở từng bước nhập | Chỉ bind vào draft; chuyển lệnh ghi chính thức tới bước confirm |
| Nút hủy không hoàn tác dữ liệu | Thay đổi đã commit ở request trước | Dùng draft hoặc thiết kế nghiệp vụ bù riêng |
| Transaction giữ connection quá lâu | Transaction bao trùm hành trình nhiều request | Tạo transaction ngắn tại service command |
| Dữ liệu review khác dữ liệu được ghi | Giá hoặc trạng thái không được kiểm tra lại | Tính lại và yêu cầu xác nhận lại khi dữ liệu quan trọng thay đổi |
| Hai tab ghi đè lẫn nhau | Không có kiểm soát phiên bản draft/aggregate | Dùng version hoặc optimistic locking |
| Một lần xác nhận tạo nhiều kết quả | Request bị gửi lặp mà command không idempotent | Dùng command ID hoặc idempotency key |
| Email đã gửi dù cập nhật DB rollback | Side effect ngoài transaction được gọi quá sớm | Dùng outbox hoặc phát sự kiện sau commit với cơ chế tin cậy |
| Draft tồn tại mãi | Không có thời hạn và tác vụ dọn dẹp | Đặt expiry, quyền sở hữu và chính sách cleanup |

## Kiểm thử ranh giới ghi dữ liệu

Kiểm thử cần chứng minh rằng các bước nhập liệu không làm thay đổi aggregate chính thức và chỉ lệnh xác nhận mới thực hiện commit.

Một bộ kịch bản tích hợp có thể gồm:

1. Khởi chạy flow, tải booking và tạo draft.
2. Gửi form với dữ liệu thay đổi; xác nhận draft được cập nhật nhưng repository của aggregate chưa nhận lệnh ghi.
3. Đi tới màn hình review rồi quay lại sửa; xác nhận các giá trị nháp vẫn được giữ.
4. Hủy flow; xác nhận aggregate chính thức không thay đổi.
5. Xác nhận flow; xác nhận service kiểm tra lại quyền, version và dữ liệu hiện tại rồi ghi aggregate.
6. Làm cho một điều kiện cuối thất bại; xác nhận transaction rollback và không có trạng thái xác nhận dở dang.
7. Gửi cùng command ID hai lần; xác nhận chỉ có một kết quả nghiệp vụ.
8. Thay đổi aggregate từ một transaction khác trước khi confirm; xác nhận xung đột được phát hiện và flow yêu cầu người dùng xem lại.
9. Kiểm tra outbox chỉ được commit cùng aggregate và publisher có thể retry mà không tạo tác động lặp.

Ở cấp service, có thể mock repository để xác nhận phương thức ghi chỉ được gọi trong lệnh confirm. Ở cấp tích hợp, nên dùng cơ sở dữ liệu kiểm thử để xác nhận rollback, optimistic locking và tính nguyên tử giữa aggregate với outbox. Mock đơn thuần không chứng minh được transaction manager thực sự rollback.

## Checklist thiết kế

Trước khi hoàn thiện một flow có chỉnh sửa dữ liệu nghiệp vụ, hãy rà soát:

- [ ] Form bind vào DTO bản nháp với danh sách field cho phép.
- [ ] Các view-state không ghi sớm aggregate chính thức.
- [ ] Flow không giữ một transaction cơ sở dữ liệu xuyên suốt nhiều request.
- [ ] Service xác nhận mở transaction ngắn và kiểm tra lại dữ liệu có thẩm quyền.
- [ ] Có kiểm soát quyền và phiên bản aggregate/draft.
- [ ] Có idempotency cho lệnh có thể được gửi lại.
- [ ] Hủy flow chỉ bỏ draft hoặc thực hiện nghiệp vụ bù đã thiết kế.
- [ ] Autosave, nếu có, ghi vào kho draft riêng với expiry và quyền sở hữu.
- [ ] Tác động ngoài cơ sở dữ liệu được xử lý bằng outbox hoặc quy trình bù phù hợp.
- [ ] Kiểm thử chứng minh không có ghi sớm, rollback đúng và không xử lý lặp.

## Ghi nhớ

- Form binding cập nhật model của flow; nó không nên tự động đồng nghĩa với việc commit aggregate nghiệp vụ.
- Giữ thay đổi đang chờ trong draft DTO thuộc flow scope hoặc kho draft riêng.
- Mỗi transaction nên ngắn và nằm ở service thực hiện một thao tác nghiệp vụ nhất quán, thường là bước xác nhận cuối.
- Kiểm tra lại quyền, version, giá, tồn kho và trạng thái hiện tại trước khi commit.
- Dùng idempotency cho lệnh có thể gửi lặp; dùng outbox hoặc saga khi có tác động tới hệ thống ngoài.
- Quay lại hoặc hủy một flow không tự rollback những thay đổi đã commit trước đó.

