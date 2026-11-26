# Giới hạn biểu thức ở logic điều phối dễ kiểm tra

Trong module **SPRING_WEB_FLOW**, biểu thức giúp flow đọc dữ liệu trong scope, gọi action, gán kết quả và chọn nhánh tiếp theo. Chúng làm cho định nghĩa flow ngắn gọn, nhưng nếu nhồi nhiều quy tắc nghiệp vụ vào một biểu thức EL, flow sẽ khó đọc, khó kiểm thử và khó phục hồi khi có lỗi. Nguyên tắc của bài này là giữ biểu thức ở mức điều phối: đọc một giá trị, gọi một thao tác có tên rõ ràng hoặc kiểm tra một điều kiện đơn giản; đặt quy tắc nghiệp vụ trong service Java có thể kiểm thử độc lập.

## 1. Biểu thức có vai trò gì trong Spring Web Flow?

Spring Web Flow dùng expression language (EL) để kết nối flow definition với dữ liệu và bean của ứng dụng. Tùy phiên bản và cấu hình `FlowBuilderServices`, ứng dụng có thể sử dụng dialect EL tương ứng. Vì vậy, cần dùng cú pháp phù hợp với expression parser đã cấu hình và tránh trộn các tính năng chỉ có ở một dialect khi dự án chưa bật dialect đó.

Biểu thức thường xuất hiện ở một số vị trí:

| Vị trí | Vai trò của biểu thức | Ví dụ |
|---|---|---|
| `<evaluate>` | Gọi action hoặc service, lấy kết quả | `bookingAction.load` |
| Thuộc tính `result` của `<evaluate>` | Lưu kết quả vào scope | `flowScope.booking` |
| `<set>` | Gán một giá trị vào scope | `flowScope.source` |
| `<if>` trong `decision-state` | Kiểm tra điều kiện để chọn state | `flowScope.manualReviewRequired` |
| Thuộc tính như `model` của `view-state` | Chỉ định dữ liệu gắn với view | `booking` |

Các biểu thức này giúp mô tả dữ liệu đi qua flow. Chúng không nên trở thành nơi triển khai một quy trình nghiệp vụ nhiều bước, tính toán phức tạp hoặc truy cập hạ tầng trực tiếp.

## 2. Ranh giới giữa điều phối và nghiệp vụ

Một flow nên trả lời những câu hỏi như: bước nào chạy trước, kết quả nào dẫn tới state nào, dữ liệu nào cần tồn tại qua các bước và khi nào hiển thị view. Service Java nên trả lời những câu hỏi như: booking có được duyệt không, giá cuối cùng là bao nhiêu, người dùng có quyền thực hiện thao tác không và dữ liệu có thể được cập nhật trong transaction hiện tại không.

Ví dụ, điều kiện sau dễ đọc và dễ kiểm tra:

```xml
<decision-state id="routeBooking">
    <if test="flowScope.manualReviewRequired"
        then="manualReview"
        else="confirmBooking" />
</decision-state>
```

Flow chỉ đọc một kết quả boolean đã được tính trước. Cách viết sau có thể chạy được với một expression parser phù hợp, nhưng làm flow gánh trách nhiệm nghiệp vụ:

```xml
<decision-state id="routeBooking">
    <if test="flowScope.booking.total &gt;= 10000000 and
              flowScope.booking.customer.riskScore &gt; 70 and
              bookingPolicy.hasNoManualReviewExemption(flowScope.booking.customer)"
        then="manualReview"
        else="confirmBooking" />
</decision-state>
```

Điều kiện dài có nhiều nhánh dữ liệu, gọi bean và chứa quy tắc chính sách. Khi chính sách thay đổi, người phát triển phải đọc EL trong XML và khó viết unit test tập trung cho từng trường hợp. Hãy chuyển quy tắc đó vào một service, để flow chỉ sử dụng kết quả.

Một cách phân chia trách nhiệm hữu ích:

- **Flow definition:** mô tả thứ tự state, event, transition, subflow và scope cần giữ.
- **Expression:** đọc hoặc ghi một giá trị, gọi một phương thức có tên rõ ràng, chuyển kết quả vào scope hoặc kiểm tra một điều kiện đơn giản.
- **Service nghiệp vụ:** kiểm tra quy tắc miền, quyền, trạng thái, tính toán và phối hợp thao tác dữ liệu.
- **Repository hoặc client hạ tầng:** truy cập database và hệ thống bên ngoài thông qua service.

## 3. Gọi service một lần, lưu kết quả rồi điều phối

Giả sử booking cần được phân loại để chuyển tới bước xác nhận hoặc duyệt thủ công. Tạo một service chứa chính sách:

```java
import java.math.BigDecimal;

public class BookingRoutingService {

    public boolean requiresManualReview(Booking booking) {
        if (booking == null) {
            throw new IllegalArgumentException("Booking is required");
        }

        boolean highValue = booking.getTotal().compareTo(
                new BigDecimal("10000000")) >= 0;
        boolean highRisk = booking.getCustomer().getRiskScore() > 70;

        return highValue || highRisk;
    }
}
```

Flow gọi service trong một `action-state`, lưu kết quả vào `flowScope`, rồi dùng `decision-state` để chọn nhánh:

```xml
<action-state id="classifyBooking">
    <evaluate expression="bookingRoutingService.requiresManualReview(flowScope.booking)"
              result="flowScope.manualReviewRequired" />
    <transition on="success" to="routeBooking" />
</action-state>

<decision-state id="routeBooking">
    <if test="flowScope.manualReviewRequired"
        then="manualReview"
        else="confirmBooking" />
</decision-state>

<view-state id="manualReview" view="booking/manual-review" />
<view-state id="confirmBooking" view="booking/confirm" />
```

Trong ví dụ, EL chỉ gọi một phương thức có tên thể hiện ý định và lưu kết quả boolean. `decision-state` không phải tự tính lại chính sách; nó chỉ định tuyến theo kết quả. Service có thể được unit test với booking giá trị cao, khách hàng rủi ro cao, trường hợp thông thường và dữ liệu không hợp lệ mà không cần khởi chạy flow.

Nếu phương thức cần phối hợp nhiều thao tác hoặc có nhiều nhánh lỗi, hãy đặt nó trong một action class rồi gọi action từ `<evaluate>`. Flow vẫn nhận kết quả qua event và scope. Không viết một chuỗi gọi service nối tiếp, phép tính lồng nhau và toán tử ba ngôi trong cùng một thuộc tính `expression`.

## 4. Dùng biểu thức đơn giản trong từng cấu trúc flow

### 4.1. `<evaluate>` để gọi một thao tác có tên rõ ràng

Một `<evaluate>` nên thể hiện một hành động dễ nhận biết. Ví dụ tải booking và lưu kết quả:

```xml
<action-state id="loadBooking">
    <evaluate expression="bookingService.findById(flowScope.bookingId)"
              result="flowScope.booking" />
    <transition on="success" to="editBooking" />
</action-state>
```

Tên phương thức `findById` cho biết thao tác đang làm gì; `result` cho biết kết quả sẽ được giữ ở đâu. Nếu không tìm thấy booking là một tình huống nghiệp vụ cần xử lý riêng, nên dùng một action trả event `notFound` hoặc một cơ chế kết quả rõ ràng để flow có transition tương ứng. Không dựa vào biểu thức dài để kiểm tra null, gọi lại repository và dựng thông báo trong cùng một chỗ.

### 4.2. `<set>` để gán dữ liệu nhỏ

`<set>` phù hợp với giá trị đơn giản phục vụ điều phối, ví dụ đánh dấu nguồn khởi tạo flow:

```xml
<on-entry>
    <set name="flowScope.source" value="'checkout'" />
</on-entry>
```

Giá trị chuỗi được đặt trong dấu nháy đơn bên trong thuộc tính XML. Có thể dùng `<set>` để gán một cờ hoặc một giá trị mặc định. Nếu cần chuẩn hóa dữ liệu, tính toán nhiều trường hoặc áp dụng quy tắc nghiệp vụ, hãy gọi service/action thay vì biến `<set>` thành một phép gán phức tạp.

### 4.3. `<if>` để chọn nhánh bằng một điều kiện dễ hiểu

Điều kiện trong `decision-state` nên ngắn và có thể đọc như một câu. Ví dụ:

```xml
<decision-state id="checkBooking">
    <if test="flowScope.booking != null and flowScope.booking.active"
        then="editBooking"
        else="bookingUnavailable" />
</decision-state>
```

Điều kiện trên kiểm tra hai trạng thái hiển nhiên của dữ liệu flow. Nếu điều kiện bắt đầu chứa nhiều quy tắc, nhiều lần gọi phương thức hoặc phụ thuộc vào dữ liệu ở nhiều hệ thống, hãy tính kết quả trong service trước đó. Với XML, các ký tự đặc biệt trong biểu thức cần được escape, chẳng hạn dùng `&gt;` thay cho `>` và `&amp;&amp;` nếu dialect yêu cầu toán tử `&&`.

### 4.4. Thuộc tính `model` để nối view với dữ liệu

Khai báo model của `view-state` nên chỉ định đối tượng mà view sẽ bind:

```xml
<view-state id="editBooking" view="booking/edit" model="booking">
    <transition on="save" to="saveBooking" bind="true" validate="true" />
</view-state>
```

Đặt dữ liệu `booking` vào scope phù hợp trước khi vào view. Để Web Flow thực hiện binding và validation theo cấu hình của view/transition. Không biến biểu thức model thành nơi tải dữ liệu, kiểm tra quyền và thay đổi trạng thái booking.

## 5. Đặt tên biến và biểu thức để dễ đọc

Tên biến trong scope là một phần của hợp đồng giữa các state. Tên rõ ràng giúp người đọc biết giá trị là dữ liệu gốc, kết quả tính toán hay cờ điều phối.

| Tên dễ hiểu | Vai trò |
|---|---|
| `flowScope.booking` | Booking đang được xử lý |
| `flowScope.bookingId` | Định danh dùng để tải booking |
| `flowScope.manualReviewRequired` | Kết quả chính sách dạng boolean |
| `flowScope.quote` | Báo giá được tạo ở bước trước |
| `flowScope.saveOutcome` | Kết quả thao tác lưu nếu flow cần giữ để hiển thị |

Nên đặt tên theo ý nghĩa nghiệp vụ, tránh các tên chung như `x`, `data`, `flag1` hoặc `result2`. Một số quy ước hữu ích:

1. Dùng tiền tố scope tường minh như `flowScope`, `viewScope` hoặc `requestScope` khi đọc/ghi trong EL.
2. Đặt tên boolean theo dạng câu hỏi hoặc trạng thái, ví dụ `isEligible` hay `manualReviewRequired`.
3. Dùng tên phương thức mô tả hành động, ví dụ `calculateQuote`, `loadBooking` hoặc `requiresManualReview`.
4. Đặt kết quả vào scope chỉ khi state tiếp theo thực sự cần dùng; dữ liệu chỉ phục vụ một lần gọi không cần tồn tại suốt flow.
5. Tránh dùng cùng một biến cho cả dữ liệu đầu vào và kết quả đã biến đổi nếu điều đó làm mất ý nghĩa ban đầu.

## 6. Chọn scope theo vòng đời, không theo sự tiện tay

Biểu thức có thể đọc và ghi các scope của Spring Web Flow. Chọn scope dựa trên nơi dữ liệu cần tồn tại:

| Scope | Khi nên dùng | Ví dụ |
|---|---|---|
| `requestScope` | Trong request hiện tại | Giá trị tạm để xử lý một lần gửi |
| `viewScope` | Trong một view-state | Trạng thái phụ của màn hình chỉnh sửa |
| `flowScope` | Qua nhiều state của flow hiện tại | Booking, quote, cờ điều phối |
| `conversationScope` | Xuyên suốt conversation có thể gồm flow cha và flow con | Ngữ cảnh dùng chung giữa các flow liên quan |
| `flashScope` | Chuyển dữ liệu tạm tới lần hiển thị kế tiếp | Thông báo hoàn tất |

Ví dụ, `manualReviewRequired` được tạo ở state `classifyBooking` và dùng ở `routeBooking`, vì vậy `flowScope` phù hợp. Một thông báo chỉ cần xuất hiện ở màn hình kế tiếp có thể dùng `flashScope`. Không giữ toàn bộ đối tượng lớn hoặc dữ liệu nhạy cảm trong scope dài hạn chỉ để tránh tải lại; thường nên giữ ID và lấy dữ liệu mới từ service ở bước cần thiết.

## 7. Những biểu thức nên tránh

Các mẫu sau khiến flow khó bảo trì:

**Chuỗi điều kiện lồng nhau:**

```xml
<if test="flowScope.booking == null ? false :
          (flowScope.booking.cancelled ? false :
          (flowScope.booking.total &gt; 10000000 ? true :
          bookingPolicy.requiresExtraCheck(flowScope.booking)))"
    then="manualReview"
    else="confirmBooking" />
```

Hãy chuyển phép phân loại thành một phương thức service trả boolean hoặc một kết quả định tuyến rõ ràng.

**Gọi nhiều service trong một biểu thức:**

```xml
<evaluate expression="bookingService.load(flowScope.bookingId).customer.refreshRisk().calculateLimit()"
          result="flowScope.limit" />
```

Chuỗi gọi này che giấu nhiều bước, khiến lỗi ở từng bước khó xác định và có thể tạo side effect khó thấy. Hãy viết một phương thức điều phối trong service/action với tên mô tả, kiểm soát lỗi và transaction rõ ràng.

**Thực hiện side effect trong điều kiện:**

```xml
<if test="bookingService.reserveInventory(flowScope.booking)"
    then="confirmBooking"
    else="outOfStock" />
```

Điều kiện trong `decision-state` nên là phép kiểm tra có thể lặp lại an toàn. Gọi `reserveInventory` có side effect trong `test` làm cho việc đọc điều kiện đồng thời thay đổi trạng thái hệ thống. Thay vào đó, chạy thao tác giữ hàng trong `action-state`, nhận event `reserved` hoặc `unavailable`, rồi dùng transition để điều phối.

## 8. Bảo mật khi dùng EL

Biểu thức được đánh giá trong ngữ cảnh ứng dụng và có thể truy cập bean hoặc dữ liệu mà cấu hình cho phép. Vì vậy:

- Không nhận nguyên văn biểu thức EL/SpEL từ người dùng, query string hoặc dữ liệu lưu trữ rồi đánh giá nó như mã.
- Không dùng đầu vào người dùng làm tên bean, tên phương thức hoặc tên property để gọi động.
- Giữ các bean có thể truy cập từ flow ở phạm vi cần thiết; tránh đưa service quản trị hoặc đối tượng nhạy cảm vào ngữ cảnh không cần thiết.
- Kiểm tra quyền trong service nghiệp vụ tại thời điểm thực hiện thao tác. Việc một state hoặc biểu thức được truy cập không chứng minh người dùng có quyền thực hiện nghiệp vụ.
- Không đặt bí mật, token, thông tin thanh toán hoặc toàn bộ đối tượng xác thực vào scope chỉ để tiện tham chiếu trong EL.

Nếu cần lựa chọn thao tác theo dữ liệu, ánh xạ giá trị đầu vào vào một danh sách lựa chọn được phép trong Java. Ví dụ, `operation="approve"` có thể được ánh xạ tới một phương thức `approve` đã định nghĩa; một giá trị lạ phải bị từ chối. Không để dữ liệu bên ngoài quyết định tùy ý phương thức nào được gọi.

## 9. Xử lý lỗi mà không làm biểu thức phức tạp

EL không phải nơi thích hợp để bắt exception, retry hoặc phục hồi transaction. Đưa các thao tác có thể thất bại vào action/service và chuẩn hóa kết quả thành event mà flow có thể hiểu.

Ví dụ, action kiểm tra và lưu booking có thể trả event:

```java
public Event save(RequestContext context) throws Exception {
    Booking booking = (Booking) context.getFlowScope().get("booking");

    try {
        bookingService.save(booking);
        return success();
    } catch (BookingConflictException ex) {
        context.getMessageContext().addMessage(
            new MessageBuilder().error()
                .defaultText("Dữ liệu đã thay đổi. Hãy tải lại trước khi lưu.")
                .build()
        );
        return error();
    }
}
```

Flow định tuyến theo event:

```xml
<action-state id="saveBooking">
    <evaluate expression="bookingAction.save" />
    <transition on="success" to="bookingSaved" />
    <transition on="error" to="editBooking" />
</action-state>
```

Ở đây biểu thức chỉ gọi một action. Action xử lý tình huống xung đột đã biết và trả event `error`; lỗi kỹ thuật ngoài dự kiến cần được ghi log và xử lý theo cơ chế exception của ứng dụng. Các thao tác ghi dữ liệu nên có transaction ở service và cơ chế chống xử lý trùng nếu người dùng có thể gửi lại request.

## 10. Kiểm thử biểu thức và luồng điều phối

Tách quy tắc nghiệp vụ khỏi EL giúp kiểm thử ở hai cấp:

**Unit test cho service:** kiểm tra chính sách bằng dữ liệu đầu vào độc lập, không cần khởi chạy flow. Với `requiresManualReview`, hãy kiểm tra booking giá trị cao, khách hàng rủi ro cao, booking thông thường, dữ liệu thiếu và các ngưỡng ngay dưới/đúng/trên giới hạn.

**Flow test cho điều phối:** khởi chạy flow, đưa dữ liệu vào scope hoặc gửi event qua `MockExternalContext`, sau đó xác nhận state đích. Kiểm tra cả hai nhánh của `decision-state`, trường hợp kết quả chưa được khởi tạo, lỗi action và validation thất bại. Có thể dùng mock cho service để xác nhận flow gọi đúng phương thức và chỉ gọi một lần.

Một checklist kiểm thử hữu ích:

- Biểu thức đọc đúng scope và đúng tên property.
- Kết quả `<evaluate>` được ghi vào đúng scope qua `result`.
- `decision-state` chọn đúng nhánh với cả giá trị `true` và `false`.
- Dữ liệu null hoặc không hợp lệ được xử lý trước khi biểu thức truy cập property sâu.
- Validation thất bại giữ người dùng ở view-state và không kích hoạt action ghi dữ liệu.
- Lỗi nghiệp vụ tạo event và message phù hợp; lỗi kỹ thuật không bị biến thành thành công giả.
- Gửi lặp không tạo side effect trùng.
- Người dùng không thể điều khiển tên bean, tên phương thức hoặc nội dung expression được thực thi.

Khi kiểm tra lỗi EL, đọc thông báo lỗi cùng state và scope hiện tại. Các lỗi thường gặp gồm sai tên biến, đọc nhầm scope, property không tồn tại, kiểu dữ liệu không tương thích và cú pháp không được expression parser hiện tại hỗ trợ. Đặt biểu thức ngắn giúp xác định vị trí sai nhanh hơn.

## 11. Quy trình rà soát một biểu thức trước khi đưa vào flow

Trước khi giữ một biểu thức trong flow definition, hãy tự hỏi:

1. Nó có thể được đọc và hiểu trong một lần không? Nếu phải lần theo nhiều toán tử hoặc nhiều lời gọi, hãy tách ra.
2. Nó có chỉ đọc/ghi dữ liệu hoặc gọi một thao tác có tên rõ ràng không? Nếu nó tính chính sách nghiệp vụ, hãy chuyển vào service.
3. Kết quả có được lưu vào scope đúng vòng đời không? Chỉ giữ dữ liệu mà state tiếp theo cần dùng.
4. Nó có thể được đánh giá lại mà không gây side effect không? Điều kiện của `decision-state` nên là kiểm tra thuần.
5. Có thể unit test quy tắc mà không cần khởi chạy flow không? Nếu không, có thể ranh giới giữa EL và nghiệp vụ đang chưa rõ.
6. Dữ liệu người dùng có thể thay đổi tên bean, method hoặc expression không? Nếu có, cần giới hạn lựa chọn và kiểm tra ở phía Java.

Trong Spring Web Flow, biểu thức tốt giúp flow thể hiện rõ hành trình: action nào được gọi, kết quả được lưu ở đâu và state tiếp theo được chọn theo điều kiện nào. Giữ EL ngắn, đặt chính sách trong service và kiểm thử hai phần độc lập sẽ giúp flow dễ đọc, dễ thay đổi và dễ phục hồi khi một bước gặp lỗi.
