# AbstractAction và các phương thức tạo kết quả

> **Chương:** Action-state  
> **Module:** SPRING_WEB_FLOW

Trong module **SPRING_WEB_FLOW**, bạn học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; tổ chức form binding, validation, scope và phiên; tích hợp Spring Web Flow với Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Trong chương **Action-state**, một action thực hiện công việc phía máy chủ rồi trả về kết quả để flow quyết định bước tiếp theo. **AbstractAction** giúp viết loại action này theo một khuôn mẫu thống nhất, còn các phương thức tạo kết quả giúp biểu đạt rõ action đã thành công, thất bại hay đưa ra một quyết định nghiệp vụ.

Bài học đi từ hợp đồng của Action đến cách cài đặt **doExecute(RequestContext)**, cách tạo Event bằng các phương thức tiện ích, cách nối event với transition, cách truyền dữ liệu qua scope và cách kiểm thử từng nhánh kết quả.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của Action, AbstractAction, RequestContext và Event.
- Cài đặt một action bằng cách kế thừa AbstractAction và ghi đè doExecute.
- Chọn đúng success(), error(), yes(), no() hoặc result(String) theo ý nghĩa của kết quả.
- Ánh xạ event id do action trả về với transition của action-state.
- Truyền dữ liệu nghiệp vụ qua flow scope hoặc dịch vụ lưu trữ thay vì nhầm dữ liệu với event id.
- Xử lý riêng kết quả nghiệp vụ dự kiến và ngoại lệ kỹ thuật.
- Viết kiểm thử cho các nhánh kết quả của action.

## 1. Action nằm ở đâu trong một flow?

Spring Web Flow dùng **Action** để thực thi một công việc trong quá trình điều khiển flow. Công việc đó có thể kiểm tra điều kiện, gọi service, lưu dữ liệu, tính toán kết quả hoặc chuẩn bị dữ liệu cho view tiếp theo.

Một action được gọi trong ngữ cảnh của flow hiện tại. Ngữ cảnh này được biểu diễn bởi **RequestContext**, cho phép action truy cập dữ liệu của request, các scope, thông tin flow và message context. Sau khi xử lý, action trả về một **Event**. Event cho biết action vừa tạo ra kết quả nào; flow dùng id của event để chọn transition phù hợp.

Có thể hình dung chuỗi thực thi như sau:

~~~mermaid
flowchart TD
    A[Action-state được kích hoạt] --> B[Spring Web Flow gọi Action]
    B --> C[AbstractAction.execute]
    C --> D[doExecute RequestContext]
    D --> E[Tạo Event]
    E --> F{Event id}
    F -->|success| G[Transition thành công]
    F -->|error| H[Transition lỗi]
    F -->|yes / no| I[Nhánh quyết định]
    F -->|custom id| J[Transition nghiệp vụ riêng]
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| **Action** | Hợp đồng thực thi một thao tác và trả về Event. |
| **AbstractAction** | Lớp cơ sở cung cấp khuôn mẫu thực thi và các phương thức tiện ích tạo Event. |
| **RequestContext** | Cung cấp ngữ cảnh của lần thực thi hiện tại, bao gồm scope và thông tin request/flow. |
| **Event** | Mang id kết quả do action phát ra cùng nguồn tạo event. |
| **action-state** | Gọi action và chọn transition dựa trên event nhận được. |

Điểm cần nhớ là action không tự quyết định view tiếp theo. Action báo kết quả; định nghĩa flow mới quyết định kết quả đó dẫn đến state nào.

## 2. Hợp đồng của AbstractAction

Một action có thể được cài đặt trực tiếp theo giao diện Action, nhưng khi logic cần một lớp cơ sở có sẵn khuôn mẫu thì **AbstractAction** là lựa chọn thuận tiện.

Khi kế thừa AbstractAction, lớp con tập trung vào phương thức:

~~~java
protected Event doExecute(RequestContext context) throws Exception
~~~

Spring Web Flow gọi action thông qua hợp đồng thực thi của lớp cơ sở. Phần xử lý cụ thể nằm trong doExecute. Phương thức này nhận RequestContext và phải trả về một Event mô tả kết quả thực thi.

Một lớp action tối thiểu có cấu trúc:

~~~java
import org.springframework.webflow.action.AbstractAction;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public class CheckAction extends AbstractAction {

    @Override
    protected Event doExecute(RequestContext context) throws Exception {
        // Đọc dữ liệu từ context, thực hiện công việc,
        // sau đó trả về một Event.
        return success();
    }
}
~~~

Trong ví dụ này, success() tạo một event có id là **success**. Khi action được gọi thành công, action-state có thể chọn transition có event tương ứng.

Không cần tự viết lại toàn bộ cơ chế thực thi của Action. Hãy đặt logic nghiệp vụ trong doExecute và để lớp cơ sở xử lý phần khuôn mẫu mà nó cung cấp. Cách này giúp các action trong module có cấu trúc nhất quán, dễ đọc và dễ kiểm thử.

### RequestContext là đầu vào quan trọng

RequestContext đại diện cho ngữ cảnh của lần xử lý hiện tại. Một action thường dùng context để:

- Đọc dữ liệu flow đã chuẩn bị ở bước trước.
- Ghi kết quả trung gian vào flow scope hoặc scope thích hợp.
- Đọc tham số request khi đó thực sự là đầu vào của thao tác.
- Truy cập message context để phối hợp thông báo cho view.
- Làm việc với thông tin flow và conversation khi cần.

Ví dụ, lấy một đối tượng Booking từ flow scope:

~~~java
Booking booking =
    (Booking) context.getFlowScope().get("booking");
~~~

Nếu action tạo ra dữ liệu cần dùng ở state kế tiếp, có thể lưu dữ liệu đó vào scope phù hợp:

~~~java
context.getFlowScope().put("availabilityChecked", Boolean.TRUE);
~~~

Flow scope giữ dữ liệu trong vòng đời flow hiện tại, nên phù hợp với dữ liệu trung gian cần đi qua nhiều state. Nếu dữ liệu chỉ phục vụ một view, hãy cân nhắc view scope; nếu dữ liệu cần tồn tại lâu dài hoặc được dùng ngoài vòng đời flow, hãy lưu qua service và kho dữ liệu nghiệp vụ.

Không giữ dữ liệu của một lần chạy trong field có thể thay đổi của action bean. Action thường được Spring quản lý như một bean dùng chung; nhiều request hoặc flow có thể gọi cùng một instance. Đưa dữ liệu theo từng lần chạy vào RequestContext và scope của flow để tránh việc các phiên ghi đè dữ liệu của nhau.

## 3. Event và event id quyết định nhánh nào được chọn

**Event** là kết quả mà action trả về. Trong đó, **id** là tên kết quả mà flow dùng để tìm transition. Ví dụ:

- Event id **success** biểu thị action hoàn thành theo nhánh thành công.
- Event id **error** biểu thị action trả về nhánh lỗi đã được mô hình hóa.
- Event id **yes** hoặc **no** biểu thị một quyết định có hai khả năng.
- Một event id tùy chỉnh biểu thị kết quả nghiệp vụ cụ thể, chẳng hạn **available**, **unavailable** hoặc **requiresReview**.

Event id phải khớp với giá trị trong thuộc tính on của transition. Nếu action trả về event id không có transition tương ứng trong state hiện tại, flow không thể đi theo nhánh mong muốn. Vì vậy, tên event là một phần của hợp đồng giữa code Java và flow definition.

Ví dụ flow:

~~~xml
<action-state id="check">
    <evaluate expression="checkAction"/>
    <transition on="success" to="review"/>
    <transition on="error" to="problem"/>
</action-state>
~~~

Ở đây, action có thể trả về success hoặc error. Transition được chọn theo event id thực tế. Nếu code đổi sang event id **completed** mà XML vẫn chỉ khai báo **success**, hai phần không còn thống nhất.

Hãy thống nhất tên event trong code và flow definition. Tên event nên ngắn, có ý nghĩa, nhất quán về cách viết và thể hiện kết quả của action thay vì tên một thao tác giao diện.

## 4. Các phương thức tiện ích tạo kết quả

AbstractAction cung cấp những phương thức tiện ích để tạo Event. Các phương thức này giúp tránh phải khởi tạo Event trực tiếp cho những kết quả phổ biến.

| Phương thức | Event id được tạo | Khi nào nên dùng |
|---|---|---|
| **success()** | success | Công việc hoàn tất bình thường và flow cần đi theo nhánh thành công. |
| **error()** | error | Action muốn trả về nhánh lỗi đã được thiết kế trong flow. |
| **yes()** | yes | Kết quả là một quyết định đúng/có. |
| **no()** | no | Kết quả là một quyết định sai/không. |
| **result(String)** | Chuỗi được truyền vào | Cần một event id riêng có ý nghĩa nghiệp vụ. |

### success()

Dùng success() khi action đã hoàn thành công việc và muốn flow tiếp tục theo nhánh thành công.

~~~java
protected Event doExecute(RequestContext context) throws Exception {
    bookingService.save(booking);
    return success();
}
~~~

Flow có thể khai báo:

~~~xml
<transition on="success" to="confirmation"/>
~~~

success() chỉ biểu đạt kết quả của action. Nó không tự lưu dữ liệu, không tự chuyển state và cũng không thay thế transaction của service. Việc lưu dữ liệu phải do service hoặc tầng nghiệp vụ chịu trách nhiệm.

### error()

Dùng error() khi action có một kết quả lỗi có thể được flow xử lý theo nhánh đã định nghĩa.

~~~java
protected Event doExecute(RequestContext context) throws Exception {
    if (!bookingPolicy.canConfirm(booking)) {
        return error();
    }
    return success();
}
~~~

Flow có thể định nghĩa:

~~~xml
<transition on="success" to="confirmation"/>
<transition on="error" to="cannotConfirm"/>
~~~

error() tạo một event có id là **error**. Đây là kết quả do action trả về, không đồng nghĩa với việc Java đã ném một exception. Một exception chưa được xử lý vẫn đi theo cơ chế xử lý exception của flow và ứng dụng.

Hãy dùng error() cho trường hợp action có thể chủ động biểu diễn bằng một nhánh lỗi. Với lỗi kỹ thuật bất ngờ như database mất kết nối hoặc lỗi lập trình, cần cân nhắc để exception được ghi nhận và xử lý ở tầng phù hợp. Không nên bắt mọi exception rồi trả error() một cách im lặng vì điều đó có thể che khuất nguyên nhân thật.

### yes() và no()

Hai phương thức này hữu ích khi action kiểm tra một điều kiện có hai kết quả. Chúng tạo event id lần lượt là **yes** và **no**.

~~~java
protected Event doExecute(RequestContext context) throws Exception {
    boolean eligible = eligibilityService.isEligible(customer);
    return eligible ? yes() : no();
}
~~~

Flow định nghĩa hai nhánh:

~~~xml
<action-state id="checkEligibility">
    <evaluate expression="eligibilityAction"/>
    <transition on="yes" to="continueApplication"/>
    <transition on="no" to="notEligible"/>
</action-state>
~~~

Dùng yes/no khi ý nghĩa quyết định thực sự là có hoặc không. Nếu kết quả có nhiều trạng thái, chẳng hạn cần bổ sung hồ sơ, bị từ chối hoặc chờ duyệt, hãy dùng các event id riêng để sơ đồ thể hiện đúng nghiệp vụ.

### result(String)

Khi kết quả không thuộc nhóm success, error, yes hoặc no, dùng result(String) để tạo event với id tùy chỉnh.

~~~java
protected Event doExecute(RequestContext context) throws Exception {
    if (inventoryService.isAvailable(booking)) {
        return result("available");
    }
    return result("unavailable");
}
~~~

Flow định nghĩa:

~~~xml
<action-state id="checkInventory">
    <evaluate expression="inventoryAction"/>
    <transition on="available" to="reviewBooking"/>
    <transition on="unavailable" to="chooseAnotherSlot"/>
</action-state>
~~~

Event id tùy chỉnh làm cho sơ đồ dễ hiểu hơn khi kết quả là một khái niệm nghiệp vụ. Với action kiểm tra kho, **available** và **unavailable** diễn đạt rõ điều kiện hơn một cặp yes/no chung chung.

Nếu cần tạo Event trực tiếp, có thể sử dụng constructor của Event với nguồn tạo event và id kết quả:

~~~java
return new Event(this, "requiresReview");
~~~

Trong phần lớn trường hợp, result(String) dễ đọc hơn vì thể hiện rõ đây là phương thức tạo kết quả của AbstractAction. Dù tạo bằng cách nào, event id vẫn phải khớp với transition mà flow mong đợi.

## 5. Ví dụ hoàn chỉnh: kiểm tra khả năng đặt chỗ

Giả sử flow đặt chỗ có một state nhập thông tin. Sau khi người dùng gửi form, action kiểm tra xem khung giờ còn chỗ hay không. Nếu còn chỗ, flow đi đến màn hình xem lại; nếu hết chỗ, flow yêu cầu người dùng chọn khung giờ khác.

Service nghiệp vụ:

~~~java
public interface InventoryService {
    boolean isAvailable(Booking booking);
}
~~~

Action:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.webflow.action.AbstractAction;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

@Component("inventoryAction")
public class InventoryAction extends AbstractAction {

    private final InventoryService inventoryService;

    public InventoryAction(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Override
    protected Event doExecute(RequestContext context) throws Exception {
        Booking booking =
            (Booking) context.getFlowScope().get("booking");

        if (booking == null) {
            return result("invalidBooking");
        }

        boolean available = inventoryService.isAvailable(booking);

        context.getFlowScope().put("availabilityChecked", Boolean.TRUE);
        context.getFlowScope().put("bookingAvailable", available);

        return available ? result("available") : result("unavailable");
    }
}
~~~

Đoạn code sử dụng constructor injection để nhận InventoryService. Action đọc Booking từ flow scope, gọi service kiểm tra, lưu kết quả cần dùng ở state kế tiếp rồi trả về event tương ứng.

Flow definition:

~~~xml
<action-state id="checkInventory">
    <evaluate expression="inventoryAction"/>
    <transition on="available" to="reviewBooking"/>
    <transition on="unavailable" to="chooseAnotherSlot"/>
    <transition on="invalidBooking" to="repairBooking"/>
</action-state>
~~~

Đọc chuỗi thực thi:

1. Người dùng gửi form và flow đi đến action-state **checkInventory**.
2. Spring Web Flow gọi inventoryAction trong RequestContext hiện tại.
3. Action lấy Booking từ flow scope và gọi InventoryService.
4. Action lưu các dữ liệu trung gian cần thiết vào flow scope.
5. Action trả về Event có id **available**, **unavailable** hoặc **invalidBooking**.
6. Flow chọn transition có thuộc tính on khớp với event id và đi đến state tương ứng.

Ví dụ này cũng cho thấy event và dữ liệu là hai khái niệm riêng. Event id dùng để điều hướng. Các giá trị bookingAvailable và availabilityChecked được lưu trong flow scope để state khác đọc được. Không nên cố nhét toàn bộ đối tượng nghiệp vụ vào tên event.

## 6. Chọn kết quả theo ý nghĩa nghiệp vụ

Một action nên trả về kết quả phản ánh điều mà flow cần quyết định. Chọn event quá chung chung làm sơ đồ khó hiểu; tạo quá nhiều event cho chi tiết kỹ thuật nhỏ lại làm flow phức tạp không cần thiết.

Một số quy tắc chọn kết quả:

- Dùng **success** khi thao tác hoàn tất và flow có một nhánh thành công rõ ràng.
- Dùng **error** khi action chủ động báo một kết quả lỗi mà flow có thể xử lý.
- Dùng **yes/no** cho quyết định nhị phân đơn giản.
- Dùng **result(String)** khi nghiệp vụ có nhiều kết quả hoặc cần tên event cụ thể.
- Dùng exception cho lỗi kỹ thuật hoặc trạng thái bất thường cần cơ chế xử lý exception, ghi log và phục hồi thích hợp.

Ví dụ kiểm tra điều kiện đặt chỗ có thể dùng yes/no nếu flow chỉ cần biết còn chỗ hay không. Nếu flow phải phân biệt **available**, **soldOut**, **temporarilyUnavailable** và **invalidRequest**, event id riêng sẽ giúp transition biểu đạt đầy đủ hơn.

Đừng dùng event id như mã lỗi chi tiết hoặc thông điệp hiển thị cho người dùng. Event là tín hiệu điều khiển nội bộ. Nội dung thông báo nên được quản lý qua message context, message bundle hoặc dữ liệu view thích hợp.

## 7. Truyền dữ liệu cùng với kết quả action

Một action thường vừa trả về kết quả điều khiển, vừa tạo ra dữ liệu mà state tiếp theo cần sử dụng. Hãy quyết định rõ dữ liệu sẽ được lưu ở đâu.

### Dùng flow scope cho dữ liệu trong vòng đời flow

~~~java
AvailabilityResult availability =
    inventoryService.check(booking);

context.getFlowScope().put("availabilityResult", availability);

return availability.isAvailable()
    ? result("available")
    : result("unavailable");
~~~

State tiếp theo có thể đọc availabilityResult từ flow scope. Dữ liệu được giữ trong vòng đời flow hiện tại và có thể đi qua nhiều state.

### Dùng view scope cho dữ liệu gắn với một màn hình

Nếu kết quả chỉ phục vụ một view-state, có thể dùng view scope. Khi người dùng rời view-state, dữ liệu này không nên được xem như dữ liệu dùng chung cho toàn bộ hành trình.

### Dùng service và kho dữ liệu cho dữ liệu nghiệp vụ lâu dài

Nếu action lưu đơn đặt chỗ, thanh toán hoặc cập nhật hồ sơ, hãy thực hiện qua service và transaction phù hợp. Scope của flow chỉ quản lý dữ liệu trong quá trình điều hướng; nó không thay thế kho dữ liệu bền vững.

### Không coi Event là nơi lưu toàn bộ model

Event trả về chủ yếu giúp flow nhận biết kết quả. Khi state sau cần dữ liệu nghiệp vụ, hãy lưu dữ liệu đó vào scope phù hợp hoặc truy vấn lại từ service. Việc này làm cho hợp đồng giữa action và flow rõ ràng, đồng thời tránh phụ thuộc vào chi tiết không cần thiết của đối tượng Event.

## 8. Phân biệt kết quả nghiệp vụ với exception

Không phải mọi trường hợp không thành công đều là exception.

| Tình huống | Cách biểu đạt phù hợp |
|---|---|
| Khung giờ đã hết chỗ | Event nghiệp vụ như **unavailable** hoặc **no**. |
| Người dùng chưa đủ điều kiện | Event nghiệp vụ như **notEligible** hoặc **no**. |
| Dữ liệu đầu vào thiếu theo quy tắc của flow | Event có ý nghĩa như **invalidBooking**, hoặc để validation xử lý ở bước form phù hợp. |
| Dịch vụ bên ngoài tạm thời không khả dụng | Có thể phát sinh exception; xử lý theo cơ chế lỗi kỹ thuật của ứng dụng hoặc chuyển thành kết quả có kiểm soát nếu hợp đồng nghiệp vụ quy định rõ. |
| Lỗi lập trình hoặc trạng thái không thể xảy ra | Để lỗi được ghi nhận và xử lý như exception, không che giấu bằng một event thành công. |

Ví dụ, hết chỗ là kết quả nghiệp vụ bình thường. Action trả về unavailable để flow đề nghị người dùng chọn giờ khác. Ngược lại, database không thể kết nối có thể là lỗi kỹ thuật; ứng dụng cần log, áp dụng chính sách retry hoặc đưa người dùng đến trang lỗi phù hợp.

Nếu bắt exception, hãy chỉ bắt những loại mà action có thể xử lý có chủ đích. Ghi nhận nguyên nhân và giữ thông tin chẩn đoán cần thiết. Không trả success() sau khi một thao tác lưu dữ liệu thất bại, và không dùng error() như cách che mọi lỗi không phân loại.

## 9. Những lỗi thường gặp khi tạo kết quả

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Action chạy nhưng flow không đi đúng nhánh | Event id không khớp transition | So sánh chuỗi id trong Java với thuộc tính on trong XML. |
| Luôn đi nhánh success | Code luôn trả success() dù quyết định nghiệp vụ khác nhau | Trả event theo kết quả thật của service hoặc quy tắc nghiệp vụ. |
| Transition không tìm thấy event | result(String) dùng tên khác với flow definition | Chuẩn hóa tên event ở cả hai phía. |
| State tiếp theo không thấy dữ liệu | Action chỉ trả event mà chưa lưu dữ liệu vào scope | Ghi dữ liệu vào flow/view scope hoặc lưu qua service. |
| Dữ liệu của hai phiên bị lẫn | Action bean giữ dữ liệu request trong field dùng chung | Chuyển dữ liệu theo từng lần chạy vào RequestContext và scope. |
| Lỗi kỹ thuật bị biến thành nhánh nghiệp vụ chung | Catch exception quá rộng rồi trả error() | Chỉ chuyển lỗi đã phân loại; giữ log và cơ chế xử lý exception cho lỗi bất ngờ. |
| Action được gọi nhiều lần | Refresh, submit lặp hoặc flow tiếp tục lại | Kiểm tra hành vi request và thiết kế thao tác ghi có tính idempotent khi cần. |
| Flow báo lỗi dù action đã làm xong một phần | Service cập nhật dữ liệu trước khi action thất bại | Thiết kế transaction và cơ chế phục hồi ở tầng nghiệp vụ. |

Khi điều tra lỗi, hãy xác minh theo thứ tự: action có được gọi không, dữ liệu đầu vào có đúng không, service trả về gì, event id thực tế là gì và transition nào được chọn. Đừng chỉ nhìn trang cuối cùng rồi kết luận action đã trả kết quả sai.

## 10. Kiểm thử các phương thức tạo kết quả

Kiểm thử action nên xác nhận cả event id và tác động lên context. Với action kiểm tra chỗ, có thể dùng MockRequestContext trong bộ test của Spring Web Flow và mock InventoryService.

Ví dụ kiểm thử nhánh còn chỗ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.test.MockRequestContext;

class InventoryActionTest {

    @Test
    void returnsAvailableWhenInventoryExists() throws Exception {
        InventoryService inventoryService = mockInventoryService();
        Booking booking = sampleBooking();

        when(inventoryService.isAvailable(booking)).thenReturn(true);

        InventoryAction action = new InventoryAction(inventoryService);
        MockRequestContext context = new MockRequestContext();
        context.getFlowScope().put("booking", booking);

        Event event = action.execute(context);

        assertEquals("available", event.getId());
        assertEquals(Boolean.TRUE,
            context.getFlowScope().get("availabilityChecked"));
        assertEquals(Boolean.TRUE,
            context.getFlowScope().get("bookingAvailable"));
    }
}
~~~

Trong test thực tế, thay mockInventoryService() và sampleBooking() bằng fixture hoặc mock tương ứng của dự án; thêm import Mockito cần thiết. Có thể viết test tương tự cho nhánh unavailable và invalidBooking.

Ngoài kiểm thử từng action, cần kiểm thử tích hợp flow để xác nhận event id thực sự chọn đúng transition. Kiểm thử action trả về **available** chưa chứng minh action-state đã chuyển đến **reviewBooking**; điều đó còn phụ thuộc flow definition.

Các trường hợp nên được bao phủ:

- Dữ liệu đầu vào hợp lệ và service trả kết quả thành công.
- Điều kiện nghiệp vụ không đạt.
- Đầu vào thiếu hoặc không hợp lệ.
- Service phát sinh lỗi kỹ thuật.
- Dữ liệu được lưu vào scope và được state sau đọc đúng.
- Event id có transition tương ứng trong flow.
- Gọi action nhiều lần không gây tác dụng phụ ngoài dự kiến.

## 11. Checklist khi xây dựng một AbstractAction

Trước khi đưa action vào flow, hãy rà soát:

- [ ] Action kế thừa đúng AbstractAction và ghi đè doExecute.
- [ ] doExecute luôn trả về một Event có ý nghĩa cho mọi kết quả được dự kiến.
- [ ] Event id được thống nhất với transition trong action-state.
- [ ] success/error/yes/no/result(String) được chọn đúng theo ý nghĩa nghiệp vụ.
- [ ] Dữ liệu trung gian được đặt trong scope phù hợp.
- [ ] Dữ liệu nghiệp vụ bền vững được xử lý qua service và transaction.
- [ ] Action bean không giữ dữ liệu của request trong field dùng chung.
- [ ] Kết quả nghiệp vụ và exception kỹ thuật được phân biệt rõ.
- [ ] Các nhánh chính và nhánh lỗi có kiểm thử.
- [ ] Flow tích hợp đã được kiểm tra để bảo đảm event dẫn đến đúng state.

## Kết luận

AbstractAction cung cấp khuôn mẫu để cài đặt action trong Spring Web Flow: lớp con xử lý nghiệp vụ trong doExecute(RequestContext) rồi trả về Event. Các phương thức success(), error(), yes(), no() và result(String) giúp biểu đạt kết quả rõ ràng; event id được action-state dùng để chọn transition. Khi kết hợp event với scope phù hợp, xử lý exception có chủ đích và kiểm thử cả action lẫn flow, bạn có thể xây dựng các bước xử lý dễ hiểu, dễ phục hồi và nhất quán trong hành trình web nhiều bước.
