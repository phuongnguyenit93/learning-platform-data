# MultiAction và lựa chọn phương thức xử lý theo cấu hình

Trong module **SPRING_WEB_FLOW**, `action-state` giúp flow thực hiện một thao tác rồi chọn state tiếp theo dựa trên kết quả. Khi một flow có nhiều thao tác liên quan, chẳng hạn tải, lưu, duyệt và hủy một booking, ta có thể gom các phương thức xử lý vào một lớp kế thừa `MultiAction`. Spring Web Flow cung cấp cơ chế chọn phương thức để flow gọi đúng thao tác theo cấu hình, đồng thời chuẩn hóa kết quả thành event cho transition.

Bài này trình bày cách tổ chức `MultiAction`, cách gọi một phương thức tường minh, cách chọn phương thức theo ID của state và cách thay bộ phân giải mặc định khi cần quy tắc riêng. Các ví dụ dùng cú pháp Spring Web Flow 2.x; hãy đối chiếu phiên bản thư viện của ứng dụng khi cấu hình dự án.

## 1. Vai trò của MultiAction trong action-state

`action-state` là một state thực thi một hoặc nhiều action khi được kích hoạt. Sau mỗi action, flow xem event kết quả có khớp transition đã khai báo hay không. Nếu action trả về event có transition tương ứng, flow đi tới state đích. Nếu nhiều action được khai báo trong cùng một `action-state`, chúng chạy theo thứ tự cho đến khi có kết quả khớp một transition; những action sau đó sẽ không chạy.

`MultiAction` là một triển khai `Action` của Spring Web Flow, cho phép một lớp đóng gói nhiều phương thức xử lý. Mỗi phương thức có thể truy cập `RequestContext` và phải có chữ ký:

```java
public Event tenPhuongThuc(RequestContext context) throws Exception
```

Ví dụ một lớp có thể cung cấp `load`, `save`, `approve` và `cancel`. Các phương thức có thể dùng chung service, truy cập `flowScope`, ghi message và trả về event. Nhờ đó, những thao tác thuộc cùng một nhóm nghiệp vụ được đặt cạnh nhau, trong khi flow definition vẫn quyết định lúc nào gọi chúng và kết quả nào dẫn tới state nào.

`MultiAction` không phải là một state mới và cũng không tự quyết định toàn bộ hành trình. `action-state` vẫn quản lý vị trí thực thi trong flow; `MultiAction` chỉ cung cấp một action có nhiều phương thức để flow gọi.

## 2. Tạo lớp MultiAction

Giả sử flow quản lý booking. Ta cần tải booking theo ID, lưu thay đổi và xử lý xung đột khi booking đã được người khác cập nhật. Lớp action có thể được viết như sau:

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.stereotype.Component;
import org.springframework.webflow.action.MultiAction;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

@Component("bookingAction")
public class BookingAction extends MultiAction {

    private final BookingService bookingService;

    public BookingAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public Event load(RequestContext context) throws Exception {
        Long bookingId = (Long) context.getFlowScope().get("bookingId");
        Booking booking = bookingService.findById(bookingId);

        if (booking == null) {
            return new Event(this, "notFound");
        }

        context.getFlowScope().put("booking", booking);
        return success();
    }

    public Event save(RequestContext context) throws Exception {
        Booking booking = (Booking) context.getFlowScope().get("booking");

        try {
            bookingService.save(booking);
            return success();
        } catch (BookingConflictException ex) {
            context.getMessageContext().addMessage(
                new MessageBuilder().error()
                    .defaultText("Booking đã được cập nhật ở nơi khác. Hãy tải lại dữ liệu.")
                    .build()
            );
            return error();
        }
    }

    public Event cancel(RequestContext context) throws Exception {
        Booking booking = (Booking) context.getFlowScope().get("booking");
        bookingService.cancel(booking.getId());
        return success();
    }
}
```

`BookingService` đại diện cho service nghiệp vụ do ứng dụng cung cấp. Lớp action điều phối dữ liệu vào/ra flow và ánh xạ kết quả nghiệp vụ thành event. Việc lưu booking, kiểm tra phiên bản dữ liệu và quản lý transaction thuộc service. `success()` và `error()` là các event tiện ích kế thừa từ `AbstractAction`; với kết quả riêng, có thể trả `new Event(this, "notFound")` hoặc một ID event khác.

Các phương thức được gọi bởi Web Flow cần là `public` và tuân thủ chữ ký của `MultiAction`. Không dùng chữ ký POJO tùy ý như `save(Booking booking)` cho phương thức của `MultiAction`; nếu muốn truyền tham số trực tiếp và nhận kiểu trả về linh hoạt, hãy cân nhắc một POJO action thông thường được gọi bằng biểu thức EL.

## 3. Gọi phương thức tường minh trong flow

Cách dễ đọc nhất là chỉ rõ tên phương thức trong biểu thức `evaluate`. Ví dụ, state `loadBooking` gọi `bookingAction.load`, còn state `saveBooking` gọi `bookingAction.save`:

```xml
<action-state id="loadBooking">
    <evaluate expression="bookingAction.load" />
    <transition on="success" to="editBooking" />
    <transition on="notFound" to="bookingNotFound" />
</action-state>

<view-state id="editBooking" model="booking">
    <transition on="save" to="saveBooking" bind="true" validate="true" />
    <transition on="cancel" to="cancelBooking" bind="false" />
</view-state>

<action-state id="saveBooking">
    <evaluate expression="bookingAction.save" />
    <transition on="success" to="bookingSaved" />
    <transition on="error" to="editBooking" />
</action-state>

<action-state id="cancelBooking">
    <evaluate expression="bookingAction.cancel" />
    <transition on="success" to="bookingCancelled" />
</action-state>
```

Trong `editBooking`, transition `save` yêu cầu binding và validation trước khi flow chuyển sang `saveBooking`. Nếu dữ liệu không hợp lệ, flow ở lại view-state để hiển thị lỗi; action `save` chưa được gọi. Transition `cancel` đặt `bind="false"` vì thao tác hủy không cần bind các trường người dùng vừa sửa. Các event `success`, `error` và `notFound` phải khớp chính xác với kết quả action trả về.

Khi biểu thức là `bookingAction.save`, Web Flow gọi phương thức `save` trên `MultiAction`. Tên phương thức được nêu ngay trong flow definition nên người đọc có thể lần theo từ state tới code Java mà không cần suy ra quy tắc chọn hàm.

## 4. Chọn phương thức theo ID của action-state

`MultiAction` có `MethodResolver` để xác định phương thức cần gọi. Bộ phân giải mặc định `DefaultMultiActionMethodResolver` hoạt động theo thứ tự sau:

1. Nếu action đang được thực thi có thuộc tính `method` được chỉ định, dùng tên phương thức đó.
2. Nếu không có `method`, dùng ID của state hiện tại trong flow execution làm tên phương thức.

Nhờ quy tắc thứ hai, ta có thể để biểu thức chỉ tham chiếu bean action. ID của `action-state` sẽ là tên phương thức:

```xml
<action-state id="prepareReview">
    <evaluate expression="bookingAction" />
    <transition on="success" to="reviewBooking" />
    <transition on="error" to="editBooking" />
</action-state>
```

Khi state `prepareReview` chạy action `bookingAction` mà không chỉ định phương thức riêng, resolver mặc định tìm phương thức `prepareReview(RequestContext)` trên lớp `BookingAction`. Vì vậy, lớp action cần có phương thức tương ứng:

```java
public Event prepareReview(RequestContext context) throws Exception {
    Booking booking = (Booking) context.getFlowScope().get("booking");
    bookingService.prepareReview(booking);
    return success();
}
```

Cách này hữu ích khi quy ước đặt tên state và phương thức thống nhất. Tuy nhiên, nó tạo liên kết trực tiếp giữa ID state và tên phương thức Java. Nếu đổi `prepareReview` thành `reviewPreparation`, phải cập nhật đồng bộ cả state ID hoặc cấu hình method tương ứng. Khi muốn flow thể hiện rõ tên thao tác, biểu thức tường minh như `bookingAction.prepareReview` thường dễ bảo trì hơn.

## 5. Thay đổi quy tắc bằng MethodResolver

Khi quy tắc mặc định không phù hợp, có thể cung cấp một triển khai `MultiAction.MethodResolver` riêng. Resolver nhận `RequestContext` và trả về tên phương thức cần gọi. Ví dụ dưới đây chọn thao tác từ một giá trị đã được flow đưa vào `flowScope`, đồng thời chỉ cho phép hai lựa chọn đã định nghĩa:

```java
import org.springframework.webflow.action.MultiAction;
import org.springframework.webflow.execution.RequestContext;

public class BookingMethodResolver implements MultiAction.MethodResolver {

    @Override
    public String resolveMethod(RequestContext context) {
        String operation = (String) context.getFlowScope().get("bookingOperation");

        if ("approve".equals(operation)) {
            return "approve";
        }
        if ("reject".equals(operation)) {
            return "reject";
        }

        throw new IllegalStateException("Unsupported booking operation");
    }
}
```

Đăng ký resolver trên bean `MultiAction` thông qua thuộc tính `methodResolver`:

Đoạn cấu hình XML dưới đây là một cách đăng ký bean thay cho `@Component("bookingAction")` ở ví dụ Java phía trên. Trong một ứng dụng, chỉ dùng một cách đăng ký cho cùng bean để tránh trùng ID.

```xml
<bean id="bookingAction" class="com.example.flow.BookingAction">
    <constructor-arg ref="bookingService" />
    <property name="methodResolver">
        <bean class="com.example.flow.BookingMethodResolver" />
    </property>
</bean>
```

Sau đó flow có thể đặt lựa chọn vào scope trước khi gọi action:

```xml
<action-state id="dispatchBooking">
    <on-entry>
        <set name="flowScope.bookingOperation" value="'approve'" />
    </on-entry>
    <evaluate expression="bookingAction" />
    <transition on="success" to="bookingApproved" />
</action-state>
```

Trong ví dụ, resolver đọc `bookingOperation` và trả về `approve`, vì vậy `MultiAction` gọi `approve(RequestContext)`. Nếu flow cần xử lý `reject`, giá trị scope tương ứng phải được đặt theo một nhánh được kiểm soát. Không dùng trực tiếp một chuỗi tùy ý từ request làm tên phương thức: cách đó có thể khiến người dùng yêu cầu thực thi phương thức ngoài dự kiến. Luôn ánh xạ đầu vào vào một danh sách thao tác cho phép, và trả lỗi rõ ràng nếu không có lựa chọn hợp lệ.

Một resolver tùy chỉnh chỉ nên chứa quy tắc chọn phương thức. Quy tắc nghiệp vụ như người dùng có quyền duyệt hay booking có đủ điều kiện hay không vẫn phải được kiểm tra trong service hoặc trong phương thức action gọi service. Chọn được phương thức `approve` không có nghĩa thao tác duyệt chắc chắn được phép.

## 6. Kết quả action và transition

`MultiAction` trả về một `Event`. ID của event là tiêu chí để `action-state` chọn transition. Một số event thường dùng:

| Event ID | Ý nghĩa thường gặp | Hướng xử lý trong flow |
|---|---|---|
| `success` | Thao tác hoàn tất | Chuyển tới state kế tiếp |
| `error` | Có lỗi nghiệp vụ có thể hiển thị và cho phép xử lý tiếp | Quay lại view hoặc tới state thông báo lỗi |
| `notFound` | Không tìm thấy dữ liệu | Chuyển tới state báo không tồn tại |
| `conflict` | Dữ liệu đã thay đổi hoặc có xung đột | Tải lại, so sánh hoặc yêu cầu người dùng xác nhận |

Đây là quy ước do flow và ứng dụng thống nhất, không phải danh sách event bắt buộc của framework. Nếu một phương thức trả `new Event(this, "conflict")`, `action-state` phải có transition `on="conflict"` hoặc một cơ chế xử lý phù hợp. Nếu không có transition khớp, flow không thể tiếp tục theo nhánh mong muốn.

Ví dụ phương thức duyệt có thể trả về các event khác nhau:

```java
public Event approve(RequestContext context) throws Exception {
    Booking booking = (Booking) context.getFlowScope().get("booking");

    if (!bookingService.canApprove(booking)) {
        return new Event(this, "notAllowed");
    }

    bookingService.approve(booking.getId());
    return success();
}
```

Và flow khai báo đầy đủ các nhánh:

```xml
<action-state id="approve">
    <evaluate expression="bookingAction.approve" />
    <transition on="success" to="bookingApproved" />
    <transition on="notAllowed" to="approvalDenied" />
</action-state>
```

Chú ý phân biệt hai quyết định: resolver chọn **phương thức nào sẽ chạy**; event kết quả quyết định **flow sẽ đi tới state nào**. Đây là hai bước độc lập. Phương thức `approve` có thể trả `success`, `notAllowed` hoặc `error`, và mỗi kết quả có thể dẫn tới một state khác.

## 7. MultiAction so với nhiều evaluate trong một action-state

Hai cách tổ chức này giải quyết hai nhu cầu khác nhau:

| Cách tổ chức | Mục đích | Điều cần chú ý |
|---|---|---|
| Một `MultiAction` với nhiều phương thức | Gom các thao tác liên quan vào một lớp action; chọn phương thức cần gọi | Chữ ký phương thức thống nhất; quản lý tên method và resolver |
| Nhiều `<evaluate>` trong một `action-state` | Chạy một chuỗi action theo thứ tự | Mỗi action được đánh giá; chuỗi dừng khi kết quả khớp transition đã khai báo |
| Nhiều bean action riêng | Tách từng thao tác hoặc nhóm trách nhiệm | Rõ ranh giới nhưng có thể tăng số lớp và bean |

Ví dụ một `action-state` chạy hai thao tác riêng:

```xml
<action-state id="prepareBooking">
    <evaluate expression="bookingService.checkPolicy(booking)" />
    <evaluate expression="bookingService.calculatePrice(booking)" />
    <transition on="success" to="reviewBooking" />
</action-state>
```

Chuỗi trên là danh sách action được thực thi theo thứ tự. Nó không tự động trở thành một `MultiAction`. Ngược lại, một `MultiAction` có thể gom nhiều phương thức vào cùng một bean nhưng một lần thực thi vẫn chọn phương thức theo cấu hình hoặc resolver. Hãy chọn cách tổ chức dựa trên việc cần gom các phương thức hay cần phối hợp nhiều action trong cùng một state.

## 8. Quản lý dữ liệu, form và phạm vi trách nhiệm

Các phương thức của `MultiAction` nhận `RequestContext`, vì vậy có thể đọc/ghi các scope của flow:

- `requestScope` phù hợp với dữ liệu tạm của request hiện tại.
- `viewScope` phù hợp với dữ liệu chỉ tồn tại trong view-state hiện tại.
- `flowScope` phù hợp với đối tượng nghiệp vụ cần dùng qua nhiều state, chẳng hạn booking đang được chỉnh sửa.
- `conversationScope` dành cho dữ liệu cần chia sẻ trong conversation gồm flow cha và flow con.

Chỉ lưu vào scope dữ liệu flow thực sự cần giữ. Với đối tượng lớn hoặc dữ liệu nhạy cảm, có thể lưu ID rồi tải lại từ service ở bước tiếp theo. Khi thao tác cập nhật dữ liệu, service nên kiểm tra quyền, trạng thái hiện tại và phiên bản dữ liệu để tránh ghi đè thay đổi của người khác.

Với biểu mẫu, nên để `view-state` phụ trách binding và validation. Khi người dùng gửi event `save`, Web Flow binding dữ liệu vào model và chạy validation theo cấu hình transition. Nếu hợp lệ, flow mới chuyển tới `action-state` gọi `MultiAction.save`. Trong action, lấy model từ scope, gọi service và trả event kết quả. Tránh tự viết lại logic binding/validation trong từng phương thức `MultiAction` nếu Web Flow đã có thể xử lý ở view-state.

## 9. Xử lý ngoại lệ và thao tác lặp

Một phương thức `MultiAction` có thể gặp lỗi nghiệp vụ hoặc lỗi kỹ thuật. Hãy phân loại cách xử lý:

1. **Lỗi nghiệp vụ có thể phục hồi:** ví dụ booking đã được người khác cập nhật. Ghi message vào `MessageContext`, trả event như `error` hoặc `conflict`, rồi chuyển flow tới state cho phép người dùng xem lại hoặc thử lại.
2. **Dữ liệu không tồn tại:** trả event rõ ràng như `notFound` để flow hiển thị trạng thái phù hợp.
3. **Lỗi kỹ thuật ngoài dự kiến:** ghi log ở tầng phù hợp và để cơ chế xử lý exception của flow/application xử lý. Không biến mọi exception thành `success` hoặc che giấu lỗi khiến flow đi tiếp với dữ liệu không nhất quán.
4. **Thao tác có side effect:** đặt transaction trong service nghiệp vụ và thiết kế idempotency cho những thao tác có thể bị gửi lại do refresh, retry hoặc khôi phục flow execution.

Ví dụ `save` có thể bắt `BookingConflictException` vì đây là tình huống nghiệp vụ đã biết và trả `error` để người dùng quay lại chỉnh sửa. Nếu database mất kết nối hoặc một lỗi lập trình xảy ra, không nên bắt chung `Exception` rồi trả `error` mà không ghi nhận nguyên nhân. Hãy để lỗi kỹ thuật được quan sát và xử lý theo chính sách của ứng dụng.

`MultiAction` cũng không thay thế transaction. Nếu một phương thức gọi nhiều service và một bước thất bại sau khi bước trước đã ghi dữ liệu, service cần bảo đảm rollback hoặc có cơ chế bù trừ thích hợp. Flow chỉ nhận kết quả để điều hướng; tính nguyên tử của nghiệp vụ thuộc tầng xử lý dữ liệu.

## 10. Kiểm thử MultiAction và method selection

Kiểm thử nên xác nhận phương thức được chọn, event trả về và thay đổi trong context. Với một lớp action, có thể kiểm tra trực tiếp các phương thức bằng `MockRequestContext` và mock `BookingService`. Với toàn bộ flow, dùng bộ hỗ trợ kiểm thử Spring Web Flow để khởi chạy flow, gửi event và kiểm tra state hiện tại.

Các tình huống cần có:

- **Gọi tường minh:** cấu hình `<evaluate expression="bookingAction.save" />` và xác nhận phương thức `save` được gọi.
- **Chọn theo state ID:** gọi bean `MultiAction` mà không nêu method; xác nhận resolver mặc định tìm phương thức trùng ID của `action-state`.
- **Chọn bằng resolver riêng:** đưa `bookingOperation` hợp lệ vào scope và xác nhận resolver trả đúng tên phương thức.
- **Giá trị không hợp lệ:** thử một operation không nằm trong allowlist; xác nhận không có phương thức ngoài dự kiến được gọi và flow xử lý lỗi rõ ràng.
- **Event kết quả:** kiểm tra `success`, `error`, `notFound`, `conflict` hoặc `notAllowed` dẫn tới đúng state.
- **Business exception:** giả lập service ném `BookingConflictException`; xác nhận message được thêm và action trả event phù hợp.
- **Lỗi kỹ thuật:** giả lập lỗi không dự kiến; xác nhận lỗi không bị biến thành kết quả thành công giả.
- **Gửi lặp:** thực hiện lại event lưu hoặc duyệt để xác nhận service không tạo side effect trùng.

Khi kiểm thử flow, đừng chỉ kiểm tra state cuối. Hãy xác nhận service được gọi đúng số lần, dữ liệu được lưu vào đúng scope và validation thất bại không làm action-state được kích hoạt. Với custom resolver, kiểm thử riêng bảng ánh xạ operation sang method để mọi nhánh đều được bao phủ.

## 11. Lỗi thường gặp và cách chọn thiết kế

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Phương thức không có chữ ký `Event method(RequestContext)` | `MultiAction` không thể gọi phương thức theo hợp đồng | Dùng đúng chữ ký và trả `Event` |
| ID của action-state không trùng tên method khi dùng resolver mặc định | Không tìm được phương thức cần gọi | Đổi ID, nêu method tường minh hoặc cấu hình resolver |
| Tên event trả về không có transition tương ứng | Flow không có nhánh xử lý kết quả | Khai báo transition cho các event có thể phát ra |
| Dùng chuỗi request tùy ý làm tên method | Có thể gọi phương thức ngoài dự kiến | Ánh xạ qua allowlist trong resolver |
| Đưa quy tắc nghiệp vụ vào resolver | Khó kiểm thử và trộn chọn method với quyết định nghiệp vụ | Resolver chỉ chọn method; service kiểm tra quy tắc nghiệp vụ |
| Dùng `MultiAction` chỉ để gom các hàm không liên quan | Lớp action trở nên khó quản lý | Gom theo một nhóm trách nhiệm hoặc tách thành bean riêng |
| Bắt mọi exception và trả `success` | Flow tiếp tục dù nghiệp vụ có thể chưa hoàn tất | Phân loại lỗi, trả event phù hợp hoặc để lỗi kỹ thuật được xử lý ở tầng ứng dụng |

Hãy dùng `MultiAction` khi một nhóm thao tác cần cùng truy cập `RequestContext`, cùng phụ thuộc vào service hoặc cùng thuộc một mảng nghiệp vụ. Chọn phương thức tường minh khi cần flow dễ đọc và ít phụ thuộc vào tên state. Dùng resolver tùy chỉnh khi có quy tắc chọn method ổn định, có thể kiểm thử và được giới hạn bằng allowlist. Nếu mỗi thao tác có trách nhiệm độc lập hoặc cần tham số/kiểu trả về linh hoạt, một POJO action riêng thường đơn giản hơn.

Khi tách rõ việc chọn phương thức, thực thi nghiệp vụ và ánh xạ event, `MultiAction` giúp gom code Java mà vẫn giữ cho flow definition dễ theo dõi. `action-state` điều phối thời điểm thực thi, resolver chọn method, phương thức action gọi service và event kết quả đưa flow tới đúng state tiếp theo.
