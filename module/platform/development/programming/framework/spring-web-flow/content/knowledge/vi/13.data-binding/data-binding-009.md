# Truyền đối tượng hay truyền định danh qua ranh giới flow

Khi một flow gọi subflow, flow cha cần cung cấp dữ liệu để subflow thực hiện công việc. Có hai cách thường gặp: truyền trực tiếp một đối tượng đang có trong flow scope, hoặc chỉ truyền định danh rồi để subflow tự tải dữ liệu cần thiết. Chọn cách nào ảnh hưởng đến quyền sở hữu dữ liệu, khả năng cập nhật, tính nhất quán, bảo mật và cách kiểm thử.

Trong module **SPRING_WEB_FLOW**, ta dùng state, event, transition và subflow để mô hình hóa hành trình web nhiều bước, kết hợp form binding, validation, scope và Spring MVC. Bài học này tập trung vào hợp đồng dữ liệu tại ranh giới flow: khi nào truyền object, khi nào truyền ID, cách khai báo input/output, và cách tránh chia sẻ trạng thái ngoài ý muốn.

## 1. Ranh giới flow là ranh giới của hợp đồng dữ liệu

Giả sử một quy trình đặt chỗ có flow cha điều phối các bước: chọn dịch vụ, nhập thông tin, xác minh và xác nhận. Bước nhập thông tin được tách thành subflow `bookingEditor`. Flow cha có thể đã có đối tượng `booking` trong flow scope và cần đưa dữ liệu đó vào subflow.

Một subflow không nên phụ thuộc ngầm vào toàn bộ trạng thái nội bộ của flow cha. Thay vào đó, flow cha và subflow trao đổi qua một hợp đồng rõ ràng:

- **Input** cho biết subflow cần nhận dữ liệu nào để bắt đầu.
- **Output** cho biết subflow trả lại dữ liệu nào khi kết thúc.
- **Event kết thúc** cho biết subflow hoàn tất theo kết quả nào, chẳng hạn `bookingSaved` hoặc `bookingCancelled`.

Hợp đồng này giúp flow cha và subflow có thể thay đổi nội bộ mà ít ảnh hưởng lẫn nhau. Nó cũng làm rõ dữ liệu nào được chia sẻ, ai chịu trách nhiệm tải dữ liệu và ai được phép thay đổi dữ liệu.

## 2. Hai lựa chọn: truyền object và truyền ID

| Tiêu chí | Truyền object | Truyền ID |
|---|---|---|
| Dữ liệu qua ranh giới | Đối tượng hoặc DTO đã có | Khóa định danh của tài nguyên |
| Nơi lấy dữ liệu | Flow cha chuẩn bị và chuyển sang | Subflow gọi service/repository để tải |
| Tính mới của dữ liệu | Phụ thuộc thời điểm object được tạo hoặc tải | Có thể tải trạng thái mới nhất tại thời điểm subflow bắt đầu |
| Chia sẻ thay đổi | Có thể cùng tham chiếu một object trong cùng execution | Subflow thường thao tác trên dữ liệu được tải riêng |
| Khối lượng dữ liệu | Có thể lớn nếu object có nhiều quan hệ | Nhỏ, thường chỉ là một ID |
| Phụ thuộc | Subflow phụ thuộc kiểu và cấu trúc object | Subflow phụ thuộc hợp đồng ID và service tải dữ liệu |
| Trường hợp phù hợp | DTO nhỏ, dữ liệu đã được chuẩn bị và cần dùng ngay | Entity bền vững, dữ liệu cần tải mới hoặc cần kiểm tra quyền |

Không có lựa chọn đúng cho mọi flow. Hãy chọn theo mục đích của subflow và vòng đời dữ liệu.

### Truyền object

Truyền object phù hợp khi flow cha đã chuẩn bị một DTO nhỏ, dữ liệu đó chính là nội dung subflow cần xử lý và cả hai nằm trong cùng ứng dụng. Ví dụ, flow cha tạo `BookingDraft` từ dữ liệu người dùng nhập rồi chuyển draft cho subflow hiển thị và chỉnh sửa.

Ưu điểm là tránh một lần truy vấn chỉ để lấy lại dữ liệu đã có. Subflow có thể dùng trực tiếp object để bind form và trả dữ liệu đã thay đổi.

Tuy nhiên, object có thể là một tham chiếu dùng chung. Nếu flow cha và subflow cùng giữ tham chiếu đó, thay đổi trên object trong subflow có thể được nhìn thấy từ flow cha. Không nên dựa vào hành vi chia sẻ ngầm này như một hợp đồng output. Hãy quy định rõ subflow được phép sửa dữ liệu nào và trả kết quả nào khi kết thúc.

### Truyền ID

Truyền ID phù hợp khi dữ liệu thuộc về một bản ghi bền vững, có thể thay đổi bởi người dùng hoặc tiến trình khác, hoặc cần được kiểm tra quyền truy cập tại thời điểm subflow bắt đầu. Subflow nhận ID, gọi service để tải dữ liệu và làm việc với trạng thái hiện hành.

Cách này giảm lượng dữ liệu qua ranh giới, tránh mang theo một object cũ và tạo điểm tập trung để kiểm tra người dùng có quyền thao tác trên tài nguyên hay không. Đổi lại, subflow cần phụ thuộc vào service tải dữ liệu và phải xử lý trường hợp bản ghi không tồn tại, đã bị xóa hoặc không còn quyền truy cập.

## 3. Khai báo input khi truyền object vào subflow

Giả sử flow cha đã có `BookingDraft` trong `flowScope.bookingDraft`. Ta truyền đối tượng này vào subflow:

~~~xml
<subflow-state id="editBooking" subflow="bookingEditor">
    <input name="bookingDraft" value="flowScope.bookingDraft" />

    <transition on="bookingSaved" to="reviewBooking">
        <set name="flowScope.bookingDraft"
             value="currentEvent.attributes.bookingDraft" />
    </transition>

    <transition on="bookingCancelled" to="bookingOverview" />
</subflow-state>
~~~

Trong flow definition của subflow, khai báo input cùng tên:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      start-state="editDetails">

    <input name="bookingDraft" />

    <view-state id="editDetails" view="editBooking">
        <transition on="save" to="saveDraft" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <action-state id="saveDraft">
        <evaluate expression="bookingDraftAction.validateAndPrepare(flowScope.bookingDraft)" />
        <transition on="success" to="bookingSaved" />
        <transition on="invalid" to="editDetails" />
    </action-state>

    <end-state id="bookingSaved">
        <output name="bookingDraft" value="flowScope.bookingDraft" />
    </end-state>

    <end-state id="bookingCancelled" />
</flow>
~~~

Ví dụ minh họa cách truyền object vào flow và trả object qua output. Trong ứng dụng thực tế, biểu thức trong action cần dùng đúng bean và dữ liệu được khai báo trong flow scope. Cần kiểm tra hợp đồng input/output và cú pháp theo phiên bản Spring Web Flow mà dự án sử dụng.

Luồng dữ liệu có thể đọc như sau:

1. Flow cha lấy object từ `flowScope.bookingDraft`.
2. Mapping `input` đưa giá trị đó vào input `bookingDraft` của subflow.
3. Subflow sử dụng dữ liệu trong hành trình chỉnh sửa.
4. Khi lưu thành công, end-state `bookingSaved` xuất output `bookingDraft`.
5. Flow cha nhận output trong event kết thúc và cập nhật scope của mình bằng mapping tường minh.

Nếu subflow bị hủy, flow cha nhận event `bookingCancelled` và có thể bỏ qua output chỉnh sửa. Đây là lý do cần phân biệt kết quả lưu thành công với kết quả hủy.

## 4. Khai báo input khi chỉ truyền ID

Nếu flow cha chỉ cần chuyển mã đặt chỗ, input của subflow sẽ là `bookingId`:

~~~xml
<subflow-state id="editBooking" subflow="bookingEditor">
    <input name="bookingId" value="flowScope.bookingId" />

    <transition on="bookingSaved" to="showBooking">
        <set name="flowScope.savedBookingId"
             value="currentEvent.attributes.bookingId" />
    </transition>

    <transition on="bookingNotFound" to="bookingOverview" />
    <transition on="bookingCancelled" to="bookingOverview" />
</subflow-state>
~~~

Subflow khai báo input và tải dữ liệu bằng service:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      start-state="loadBooking">

    <input name="bookingId" />

    <action-state id="loadBooking">
        <evaluate expression="bookingLoader.load(flowScope.bookingId)" />

        <transition on="loaded" to="editDetails" />
        <transition on="notFound" to="bookingNotFound" />
        <transition on="forbidden" to="bookingNotFound" />
    </action-state>

    <view-state id="editDetails" view="editBooking">
        <transition on="save" to="saveBooking" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <action-state id="saveBooking">
        <evaluate expression="bookingUpdater.update(flowScope.booking)" />
        <transition on="saved" to="bookingSaved" />
        <transition on="conflict" to="editConflict" />
        <transition on="invalid" to="editDetails" />
    </action-state>

    <view-state id="editConflict" view="editConflict">
        <transition on="reload" to="loadBooking" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <end-state id="bookingSaved">
        <output name="bookingId" value="flowScope.booking.id" />
    </end-state>

    <end-state id="bookingNotFound" />
    <end-state id="bookingCancelled" />
</flow>
~~~

Trong ví dụ, `bookingLoader.load` và `bookingUpdater.update` là các action trả về Event với ID như `loaded`, `notFound`, `forbidden`, `saved`, `conflict` hoặc `invalid`. Action tải dữ liệu cần đặt object vào `flowScope.booking` sau khi tải thành công. Khi không tìm thấy bản ghi hoặc người dùng không có quyền, ví dụ đưa cả hai về cùng end-state `bookingNotFound` để tránh tiết lộ sự tồn tại của tài nguyên. Các state và bean này là minh họa; ứng dụng cần triển khai chúng theo service và chính sách bảo mật thực tế.

Nếu service dùng exception thay vì event cho trường hợp không tìm thấy hoặc không có quyền, flow cần có cơ chế xử lý exception tương ứng. Điều quan trọng là phân biệt rõ bản ghi không tồn tại, người dùng không được phép thao tác và lỗi kỹ thuật.

## 5. Trả output một cách tường minh

Output là phần dữ liệu subflow công bố khi kết thúc. Flow cha có thể dùng output để tiếp tục hành trình mà không cần biết subflow đã xử lý dữ liệu nội bộ như thế nào.

Ví dụ, subflow chỉ trả ID của bản ghi vừa lưu:

~~~xml
<end-state id="saved">
    <output name="bookingId" value="flowScope.booking.id" />
</end-state>
~~~

Flow cha ánh xạ giá trị output từ event kết thúc vào scope của mình:

~~~xml
<subflow-state id="editBooking" subflow="bookingEditor">
    <input name="bookingId" value="flowScope.bookingId" />

    <transition on="saved" to="showBooking">
        <set name="flowScope.bookingId"
             value="currentEvent.attributes.bookingId" />
    </transition>
</subflow-state>
~~~

Trong ví dụ, event kết thúc và output là hai phần khác nhau:

- Event `saved` mô tả kết quả nghiệp vụ của subflow.
- Output `bookingId` mang dữ liệu cần thiết để flow cha tiếp tục.

Nếu flow cha cần hiển thị dữ liệu mới nhất, nó có thể dùng ID này để gọi service tải lại bản ghi. Cách làm này giữ hợp đồng output nhỏ và tránh chuyển cả entity graph qua ranh giới flow.

Với output là object, hãy xác định rõ flow cha có được phép giữ và sửa object đó tiếp hay không. Nếu output là một DTO kết quả chỉ đọc, ghi rõ tính chất đó trong hợp đồng để tránh việc một flow vô tình sửa dữ liệu mà flow khác đang sử dụng.

## 6. Object được truyền có phải bản sao độc lập?

Khi truyền object trong cùng một flow execution, mapping thường chuyển giá trị object qua biểu thức, không tự động tạo một bản sao sâu (deep copy). Vì vậy, nếu hai scope cùng giữ tham chiếu đến một object mutable, thay đổi trên object có thể được nhìn thấy ở cả hai nơi.

Ví dụ:

~~~java
BookingDraft draft = new BookingDraft();
draft.setCustomerName("An");

// Subflow nhận chính object draft này.
BookingDraft receivedBySubflow = draft;

receivedBySubflow.setCustomerName("Binh");

// draft cũng quan sát thấy thay đổi vì cùng tham chiếu.
~~~

Đây là minh họa về ngữ nghĩa tham chiếu của Java. Trong Spring Web Flow, chi tiết lưu và khôi phục execution còn phụ thuộc repository và cách ứng dụng lưu trạng thái. Không nên giả định object luôn được giữ nguyên cùng identity sau một lần lưu snapshot, khôi phục hoặc chuyển qua môi trường phân tán.

Nếu cần cô lập thay đổi, hãy tạo một bản sao có chủ đích trước khi truyền:

~~~java
BookingDraft editableCopy = bookingDraft.copy();
~~~

Hoặc dùng constructor/copy mapper để tạo DTO riêng:

~~~java
BookingEditForm form = new BookingEditForm(
    booking.getCustomerName(),
    booking.getStartDate(),
    booking.getEndDate()
);
~~~

Subflow chỉnh sửa DTO. Khi người dùng lưu, service kiểm tra và áp dụng các trường được phép lên entity trong một giao dịch. Nếu người dùng hủy, bỏ DTO mà không cần khôi phục entity gốc.

Không nên dùng serialization/deserialization tùy tiện để clone entity có quan hệ phức tạp. Cách đó có thể sao chép nhầm dữ liệu không cần thiết, tạo object graph lớn hoặc làm mất ngữ nghĩa của proxy và quan hệ persistence. Dùng DTO hoặc copy constructor với các trường được chọn rõ ràng.

## 7. Chọn object, DTO hay ID theo tình huống

Có ba lựa chọn thực tế, không chỉ hai:

1. **Domain object/entity**: dùng khi subflow cần làm việc với object nghiệp vụ trong cùng ứng dụng và có quy tắc sở hữu, cập nhật rõ ràng. Cần cẩn trọng với entity được quản lý bởi persistence context, lazy relationship và trạng thái stale.
2. **DTO/command object**: dùng khi subflow cần dữ liệu để hiển thị hoặc chỉnh sửa nhưng không cần toàn bộ entity. DTO giúp giới hạn trường dữ liệu và tránh sửa trực tiếp entity đang được chia sẻ.
3. **ID**: dùng khi subflow nên tự tải dữ liệu, cần trạng thái mới nhất, cần kiểm tra quyền hoặc chỉ cần tham chiếu đến tài nguyên bền vững.

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Subflow chỉnh sửa vài trường của một bản nháp mới tạo | DTO hoặc bản sao object | Cô lập thay đổi trước khi xác nhận |
| Subflow cần đọc dữ liệu hiện hành của một đơn hàng đã lưu | ID | Tải trạng thái mới nhất và kiểm tra quyền |
| Flow cha và subflow cùng thao tác trên một đối tượng nhỏ, cùng một hành trình | Object nếu ownership rõ | Tránh tải lại không cần thiết |
| Subflow dùng trong nhiều quy trình khác nhau | ID hoặc DTO ổn định | Giảm phụ thuộc vào cấu trúc nội bộ của flow cha |
| Dữ liệu lớn với nhiều quan hệ lazy | ID | Tránh mang cả object graph qua flow |
| Tích hợp với service từ xa hoặc xử lý bất đồng bộ | ID hoặc message DTO | Không thể dựa vào tham chiếu object trong bộ nhớ |

Nếu dữ liệu là một entity JPA/Hibernate, truyền entity qua nhiều state hoặc subflow có thể kéo theo vấn đề detached entity, lazy loading ngoài transaction và ghi đè dữ liệu mới bằng một object cũ. Thường nên truyền ID, tải entity trong service transaction, rồi chuyển dữ liệu cần thiết sang DTO để bind form.

## 8. Kiểm tra tính nhất quán và xung đột cập nhật

Truyền ID giúp subflow tải dữ liệu mới tại thời điểm bắt đầu, nhưng dữ liệu vẫn có thể bị người khác cập nhật trong lúc người dùng đang chỉnh sửa. Vì vậy, ID không tự giải quyết concurrency.

Một cách phổ biến là dùng optimistic locking với trường version:

~~~java
@Entity
public class Booking {

    @Id
    private Long id;

    @Version
    private long version;

    private String customerName;

    // Getter và setter
}
~~~

Khi tải bản ghi, service giữ version hiện tại trong DTO:

~~~java
public BookingEditForm loadForEditing(Long bookingId) {
    Booking booking = repository.findById(bookingId)
        .orElseThrow(BookingNotFoundException::new);

    authorizationService.checkCanEdit(booking);

    return new BookingEditForm(
        booking.getId(),
        booking.getVersion(),
        booking.getCustomerName()
    );
}
~~~

Khi lưu, service kiểm tra version và áp dụng thay đổi:

~~~java
public void update(BookingEditForm form) {
    Booking booking = repository.findById(form.getId())
        .orElseThrow(BookingNotFoundException::new);

    authorizationService.checkCanEdit(booking);

    if (booking.getVersion() != form.getVersion()) {
        throw new BookingConflictException();
    }

    booking.setCustomerName(form.getCustomerName());
}
~~~

Đây là ví dụ minh họa; trong ứng dụng thực tế, cần bảo đảm kiểm tra version và cập nhật diễn ra trong cùng transaction để tránh race condition. Nếu dùng JPA `@Version`, có thể dựa vào optimistic locking của persistence provider và xử lý `OptimisticLockException` hoặc exception đã được chuyển đổi tương ứng.

Khi có xung đột, subflow nên chuyển đến state giải thích rằng dữ liệu đã thay đổi và yêu cầu người dùng tải lại hoặc so sánh trước khi ghi đè. Không nên âm thầm dùng dữ liệu cũ để ghi đè cập nhật mới.

## 9. Bảo mật khi truyền ID hoặc object

ID không phải bằng chứng người dùng có quyền truy cập tài nguyên. Người dùng có thể sửa tham số, gửi ID của bản ghi khác hoặc dùng một execution key cũ. Vì vậy, service tải dữ liệu cần kiểm tra quyền theo principal hiện tại.

Tương tự, object được truyền từ flow cha không tự động đáng tin cậy. Dữ liệu đó có thể được tạo từ form người dùng, đã cũ hoặc đã bị thay đổi trong flow trước đó. Trước khi thực hiện thao tác quan trọng, service vẫn phải kiểm tra các quy tắc nghiệp vụ và quyền tương ứng.

Một số nguyên tắc:

- Chỉ đưa qua ranh giới flow những trường dữ liệu subflow thực sự cần.
- Không truyền password, access token hoặc thông tin xác thực trong object flow.
- Khi nhận ID, tải bản ghi qua service có kiểm tra quyền sở hữu/quyền thao tác.
- Không tin các trường nhạy cảm trong DTO như `ownerId`, `role`, `price` nếu người dùng có thể gửi chúng từ form.
- Dùng allowlist các trường được phép chỉnh sửa; không bind trực tiếp toàn bộ entity.
- Kiểm tra lại trạng thái nghiệp vụ ở thời điểm ghi, kể cả khi đã kiểm tra lúc bắt đầu subflow.

Flow input là cơ chế truyền dữ liệu trong ứng dụng, không phải ranh giới bảo mật. Ranh giới bảo mật vẫn nằm ở xác thực, phân quyền và kiểm tra nghiệp vụ tại service.

## 10. Tính bền vững của object trong flow execution

Spring Web Flow có thể lưu snapshot execution để khôi phục flow giữa các request. Nếu ứng dụng dùng repository hoặc môi trường triển khai yêu cầu serialization, object nằm trong flow scope phải tương thích với cơ chế lưu trữ đó.

Đặc biệt, tránh đưa vào scope:

- Connection, stream hoặc tài nguyên hệ thống đang mở.
- Entity graph quá lớn hoặc proxy phụ thuộc persistence context.
- Đối tượng giữ tham chiếu đến service, request hoặc servlet container.
- Object không thể serialize trong cấu hình repository cần serialize.
- Dữ liệu nhạy cảm không cần thiết cho các bước tiếp theo.

Nếu phải giữ dữ liệu qua nhiều request, ưu tiên DTO nhỏ, có cấu trúc ổn định và chỉ chứa các giá trị cần thiết. Với tài nguyên bên ngoài, lưu ID hoặc handle có thể tải lại; mở và đóng tài nguyên trong một action ngắn thay vì giữ nó trong flow scope.

Khi dùng repository lưu execution ở session, các object vẫn cần có vòng đời hợp lý và không được giữ tài nguyên mở. Khi dùng môi trường cluster hoặc repository có lưu trữ bền vững, cần kiểm tra yêu cầu serialization, class compatibility và khả năng khôi phục sau khi ứng dụng được triển khai phiên bản mới.

## 11. Kiểm thử hợp đồng input/output

Kiểm thử ranh giới flow nên xác nhận cả dữ liệu đầu vào, kết quả đầu ra và quyền sở hữu dữ liệu.

| Kịch bản | Điều cần xác minh |
|---|---|
| Truyền object hợp lệ | Subflow nhận đúng dữ liệu cần thiết |
| Subflow chỉnh sửa bản sao DTO | Flow cha chỉ nhận thay đổi khi output được trả về và ánh xạ |
| Subflow bị hủy | Flow cha không áp dụng các thay đổi chưa xác nhận |
| Truyền ID không tồn tại | Subflow đi đến nhánh not-found phù hợp |
| Người dùng không có quyền với ID | Service từ chối và không tiết lộ dữ liệu trái phép |
| Dữ liệu thay đổi trong lúc chỉnh sửa | Xung đột version được phát hiện và xử lý |
| Output bị thiếu | Flow cha có nhánh xử lý hoặc hợp đồng yêu cầu output bắt buộc được kiểm tra |
| Execution được khôi phục | Object trong scope có thể được khôi phục theo repository đã cấu hình |

Ở mức unit test, kiểm thử service tải dữ liệu, kiểm tra quyền và cập nhật version. Ở mức flow test, khởi chạy flow cha, truyền input cho subflow, phát event kết thúc và kiểm tra output mà flow cha nhận được. Nếu dùng DTO copy, hãy xác minh thao tác hủy không làm thay đổi dữ liệu gốc.

Một bài kiểm thử quan trọng là thay đổi object trong subflow rồi kết thúc bằng event hủy. Flow cha phải giữ dữ liệu trước đó. Sau đó chạy lại với event lưu thành công và xác minh chỉ các trường được phép mới được áp dụng.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Truyền toàn bộ entity graph vào subflow | Scope nặng, phụ thuộc persistence và có thể gặp lazy loading | Truyền ID hoặc DTO tối thiểu |
| Nghĩ input object tự động được clone | Thay đổi trong subflow có thể ảnh hưởng object cha | Dùng bản sao rõ ràng nếu cần cô lập |
| Chỉ truyền ID nhưng không kiểm tra quyền | Người dùng có thể truy cập tài nguyên của người khác | Kiểm tra quyền trong service khi tải và cập nhật |
| Trả toàn bộ entity qua output | Flow cha phụ thuộc cấu trúc nội bộ của subflow | Trả ID hoặc DTO kết quả nhỏ |
| Subflow sửa object nhưng không có hợp đồng output | Kết quả phụ thuộc vào chia sẻ tham chiếu ngầm | Khai báo output và mapping rõ ràng |
| Dùng entity cũ để ghi đè dữ liệu mới | Mất cập nhật của người dùng khác | Dùng version/optimistic locking |
| Đưa service hoặc connection vào flow scope | Khó lưu và khôi phục execution | Chỉ lưu dữ liệu; lấy bean từ Spring và quản lý tài nguyên theo thao tác |
| Bind trực tiếp mọi trường của entity | Người dùng có thể sửa trường nhạy cảm | Dùng DTO và allowlist trường cập nhật |

## 13. Thực hành: tách subflow chỉnh sửa đặt chỗ

Hãy tạo một flow cha quản lý đặt chỗ và subflow `bookingEditor` để chỉnh sửa thông tin.

1. Trong flow cha, có `bookingId` và gọi subflow `bookingEditor`.
2. Trước tiên, triển khai phiên bản truyền ID: subflow nhận `bookingId`, tải dữ liệu qua service và kiểm tra quyền.
3. Tạo DTO `BookingEditForm` chỉ gồm các trường người dùng được phép sửa và một trường version.
4. Khi lưu, service kiểm tra version rồi cập nhật entity trong transaction.
5. Subflow trả output `bookingId` và event `saved` khi lưu thành công.
6. Khi người dùng hủy, subflow kết thúc bằng event `cancelled` mà không cập nhật entity.
7. Viết kiểm thử chứng minh dữ liệu không thay đổi khi hủy.
8. Tạo thêm phiên bản truyền object DTO từ flow cha để so sánh số lần tải dữ liệu và cách quản lý thay đổi.
9. Mở hai flow chỉnh sửa cùng một bản ghi, lưu từ flow thứ nhất rồi thử lưu từ flow thứ hai để quan sát optimistic locking.
10. Thử truyền một ID không thuộc người dùng hiện tại và xác minh service từ chối truy cập.

Sau khi thực hành, hãy tự trả lời:

- Khi nào truyền object giúp đơn giản hóa subflow?
- Vì sao mapping object không đồng nghĩa với deep copy?
- Truyền ID giúp kiểm tra dữ liệu và quyền truy cập tại thời điểm nào?
- DTO khác entity ở điểm nào khi dùng để bind form?
- Vì sao cần version khi người dùng có thể chỉnh sửa cùng một bản ghi đồng thời?
- Subflow nên trả toàn bộ object hay chỉ trả dữ liệu cần thiết cho flow cha?

## 14. Ghi nhớ

Ranh giới giữa flow cha và subflow cần một hợp đồng input/output rõ ràng. Truyền object phù hợp khi dữ liệu nhỏ, đã được chuẩn bị và quyền sở hữu thay đổi được xác định. Truyền ID phù hợp khi subflow cần tải trạng thái hiện hành, kiểm tra quyền hoặc chỉ cần tham chiếu đến tài nguyên bền vững. DTO là lựa chọn hữu ích khi subflow cần dữ liệu để hiển thị và chỉnh sửa mà không nên thao tác trực tiếp trên entity.

Đừng dựa vào việc object được chia sẻ ngầm hoặc giả định input tự tạo bản sao. Hãy ánh xạ output rõ ràng, kiểm tra quyền trong service, xử lý xung đột cập nhật và chỉ giữ dữ liệu cần thiết trong flow scope. Những nguyên tắc này giúp các flow trong **SPRING_WEB_FLOW** có thể tái sử dụng, kiểm thử độc lập và phối hợp an toàn qua các ranh giới dữ liệu.
