# Triển khai phiên bản mới khi còn flow đang hoạt động

Người dùng đang ở bước xem lại đơn hàng của phiên bản A. Trong lúc họ đọc thông tin, đội vận hành triển khai phiên bản B, đổi tên state, thêm trường bắt buộc và thay DTO trong `flowScope`. Vài phút sau, người dùng bấm xác nhận trên trang cũ. Request đó sẽ chạy mã nào, đọc trạng thái nào và có còn hiểu event từ trang cũ không?

Đó là câu hỏi triển khai quan trọng của Spring Web Flow. Trong chương **Hiệu năng và vận hành** của module **SPRING_WEB_FLOW**, bài này trình bày cách duy trì hoặc kết thúc có kiểm soát những hành trình web nhiều bước qua state, event, transition và subflow khi thay phiên bản ứng dụng. Binding, validation, scope, phiên, tích hợp Spring MVC và phục hồi lỗi đều là một phần của hợp đồng triển khai.

## 1. Phân biệt ba khoảng thời gian

| Khoảng thời gian | Ví dụ | Ý nghĩa khi triển khai |
| --- | --- | --- |
| Request đang xử lý | Request xác nhận đang gọi dịch vụ | Cần cho phép hoàn tất hoặc xử lý kết quả chưa xác định |
| Flow đang hoạt động | Người dùng ở màn hình xem lại, chưa gửi request tiếp | Vẫn cần nơi tiếp nhận request trong tương lai |
| Dữ liệu nghiệp vụ tồn tại dài hạn | Bản nháp hoặc đơn đã được lưu | Cần đọc được qua các lần triển khai theo hợp đồng dữ liệu |

Một server không có request đang chạy vẫn có thể đang giữ hàng nghìn flow chờ người dùng. Ngược lại, một flow kết thúc không có nghĩa mọi tác vụ nghiệp vụ bên ngoài đã dừng.

Graceful shutdown thường cho request hiện tại một khoảng thời gian để hoàn tất và ngừng nhận request mới. Nó không tự giữ server sống đến khi tất cả người dùng hoàn thành các màn hình đang mở. Phạm vi xử lý request này được mô tả trong [Graceful Shutdown của Spring Boot](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).

Vì vậy cần tách hai thao tác:

- **Rút phiên bản cũ khỏi việc nhận flow mới**, trong khi vẫn phục vụ execution cũ.
- **Dừng tiến trình cũ**, sau khi execution đã hoàn tất hoặc đã có đường phục hồi phù hợp.

Nếu dừng tiến trình ngay sau khi request hiện tại xong, người dùng có thể mất điểm tiếp tục dù shutdown diễn ra hoàn toàn đúng kỹ thuật.

## 2. Flow execution phụ thuộc vào cả trạng thái và định nghĩa

Một request tiếp tục flow cần nhiều hơn cookie đăng nhập:

1. Phiên hoặc cơ chế xác định conversation còn hợp lệ.
2. Execution key còn trỏ đến trạng thái có thể tìm được.
3. Dữ liệu execution có thể được đọc hoặc giải tuần tự hóa.
4. Flow definition và state tương ứng vẫn tồn tại.
5. Event, action, model, view và subflow vẫn đáp ứng hợp đồng của màn hình cũ.
6. Dữ liệu nghiệp vụ và dịch vụ phía sau còn chấp nhận thao tác đó.

Repository của Web Flow chịu trách nhiệm lưu, khôi phục và loại bỏ execution theo key; xem [API FlowExecutionRepository](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/execution/repository/FlowExecutionRepository.html).

### Snapshot không phải một bản sao đóng gói đầy đủ của ứng dụng

Trong implementation chuẩn có serialization, flow session giữ flow ID, state ID và scope; tham chiếu định nghĩa/state được khôi phục lại. Có thể đối chiếu tại [FlowSessionImpl](https://github.com/spring-projects/spring-webflow/blob/main/spring-webflow/src/main/java/org/springframework/webflow/engine/impl/FlowSessionImpl.java).

Khi khôi phục, factory gắn lại định nghĩa flow và tra state theo ID; với subflow, nó còn tra định nghĩa của các session con. Cơ chế này thể hiện trong [FlowExecutionImplFactory.restoreFlowExecution](https://github.com/spring-projects/spring-webflow/blob/main/spring-webflow/src/main/java/org/springframework/webflow/engine/impl/FlowExecutionImplFactory.java).

Hệ quả vận hành: giữ được byte snapshot chưa bảo đảm tiếp tục được flow. Nếu phiên bản mới bỏ state `review`, đổi input của subflow hoặc không còn class DTO cũ, execution vẫn có thể không khôi phục hoặc không xử lý đúng.

Không dựa vào việc execution key có hình thức quen thuộc để kết luận nó tự gắn với một bản build. Việc chọn phiên bản ứng dụng/định nghĩa phục vụ execution cần được thiết kế và kiểm chứng.

## 3. Phân loại thay đổi theo rủi ro đối với flow cũ

| Thay đổi | Rủi ro chính | Điều kiện cần kiểm chứng |
| --- | --- | --- |
| Sửa chữ hoặc màu giao diện | Thường ít ảnh hưởng trạng thái | Trang đã mở vẫn gửi event và field hợp lệ |
| Thêm trường DTO tùy chọn | Giá trị cũ có thể thiếu/null | Đọc dữ liệu cũ và áp dụng mặc định đúng ý nghĩa |
| Thêm trường bắt buộc | Form cũ không gửi trường mới | Có bước bổ sung dữ liệu hoặc giữ hợp đồng cũ |
| Đổi tên state hoặc flow ID | Không tìm được điểm khôi phục | Giữ định nghĩa cũ hoặc có chiến lược phục hồi riêng |
| Đổi event `confirm` thành `submitOrder` | Trang cũ vẫn gửi event cũ | Tạm chấp nhận hợp đồng event cũ nếu semantics vẫn phù hợp |
| Đổi kiểu hoặc package của DTO | Lỗi đọc trạng thái | Kiểm thử serializer và classpath qua hai bản |
| Đổi output subflow | Flow cha không nhận đúng dữ liệu | Giữ hợp đồng cha/con theo phiên bản |
| Thay dịch vụ/transaction | Tác dụng phụ khác kỳ vọng | Xác nhận idempotency và kết quả nghiệp vụ |
| Migration database phá hợp đồng cũ | Instance cũ không đọc/ghi được | Mở rộng schema trước, thu hẹp sau khi hết mã cũ |
| Nâng major framework hoặc serializer | Dữ liệu nội bộ có thể không tương thích | Không giả định framework bảo đảm tương thích execution xuyên major |

Cùng state ID và cùng tên DTO chưa đủ chứng minh tương thích. Một thay đổi validation có thể khiến người dùng đang ở bước xác nhận bị từ chối vì dữ liệu trước đó chưa được yêu cầu nhập.

## 4. Chọn chiến lược trước khi bắt đầu rollout

Có bốn lựa chọn phổ biến; có thể phối hợp chúng theo từng loại thay đổi.

| Chiến lược | Khi phù hợp | Chi phí hoặc giới hạn |
| --- | --- | --- |
| Phiên bản mới tiếp tục được execution cũ | Thay đổi nhỏ, đã kiểm thử tương thích | Phải giữ hợp đồng đọc và xử lý dữ liệu cũ |
| Giữ nhóm instance cũ cho flow cũ | Thay đổi lớn, cần tránh đọc chéo phiên bản | Cần định tuyến và giữ tài nguyên trong thời gian chuyển tiếp |
| Giữ hai định nghĩa flow trong cùng ứng dụng | Mã và runtime có thể phục vụ đồng thời hai hợp đồng | Phải giữ cả action, DTO, subflow và view cần thiết |
| Dừng có kiểm soát, mở lại từ bản nháp | Không thể tiếp tục execution cũ hoặc có thời hạn bảo trì | Cần lưu bền vững và thông báo rõ cho người dùng |

“Rolling deployment” mô tả cách thay instance, không tự chọn một trong các hợp đồng này. Nếu request tiếp theo có thể rơi vào bất kỳ phiên bản nào, cả hai phía phải đáp ứng tương thích cần thiết hoặc có cơ chế định tuyến ngăn đọc chéo.

## 5. Chiến lược tương thích: kiểm tra cả hai chiều khi cần rollback

Nếu phiên bản B tiếp tục execution do A tạo, phải kiểm tra ít nhất chiều **A ghi → B đọc và xử lý**. Khi A và B cùng đọc/ghi một kho phiên, hoặc khi rollback đưa người dùng từ B về A, cần xem cả chiều **B ghi → A đọc và xử lý**.

Hai chiều không tự tương đương. B có thể hiểu dữ liệu A nhưng ghi ra giá trị enum hoặc dạng dữ liệu mà A không nhận ra.

### Tương thích serialization và tương thích nghiệp vụ khác nhau

Ví dụ DTO được lưu bằng Java serialization:

```java
import java.io.Serial;
import java.io.Serializable;

public final class CheckoutDraft implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String draftId;
    private int quantity;

    // Trường tùy chọn thêm ở B; A chưa có trường này.
    private String displayNote;

    public String getDraftId() {
        return draftId;
    }

    public int getQuantity() {
        return quantity;
    }

    public String getDisplayNote() {
        return displayNote == null ? "" : displayNote;
    }
}
```

`serialVersionUID` tường minh giúp kiểm soát nhận dạng serialization, nhưng không sửa được mọi thay đổi không tương thích. Đổi kiểu trường, bỏ class cần thiết hoặc thay giao thức serialization vẫn có thể gây lỗi. Tham khảo [Java SE Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html).

Khi đọc dữ liệu cũ, trường mới có thể mang giá trị mặc định của cơ chế serialization. Không trông đợi field initializer hoặc constructor của chính lớp `Serializable` luôn chạy như khi tạo đối tượng mới. Getter trên chỉ minh họa chuẩn hóa một ghi chú hiển thị tùy chọn; không nên áp dụng mặc định im lặng cho dữ liệu có ý nghĩa thanh toán hoặc pháp lý.

Nếu dùng Spring Session Redis, serializer là một phần của hợp đồng phiên. Tài liệu nêu Java serialization là mặc định và cho phép tùy biến serializer; việc đổi serializer không tự chuyển dữ liệu đã lưu sang định dạng mới. Xem [Redis Configurations của Spring Session](https://docs.spring.io/spring-session/reference/configuration/redis.html).

Đổi sang JSON cũng không tự giải quyết mọi vấn đề: còn tên class/type metadata, cấu trúc object, custom serializer, dữ liệu framework và quy tắc bỏ qua trường lạ. Cần kiểm tra chính đồ thị trạng thái mà hệ thống lưu.

## 6. Giữ flow cũ bằng định danh phiên bản riêng

Một lựa chọn là đăng ký các định nghĩa có ID riêng trong cấu hình hiện có:

```xml
<webflow:flow-registry id="flowRegistry"
                       flow-builder-services="flowBuilderServices">
    <webflow:flow-location
            id="checkout-v1"
            path="/WEB-INF/flows/checkout/v1/checkout-flow.xml" />
    <webflow:flow-location
            id="checkout-v2"
            path="/WEB-INF/flows/checkout/v2/checkout-flow.xml" />
</webflow:flow-registry>
```

Đây là đoạn cấu hình ghép vào application context đã khai báo namespace `webflow` và builder services phù hợp. Spring Web Flow cho phép đăng ký custom flow ID; xem phần cấu hình flow registry trong [Spring Web Flow Reference Guide](https://docs.spring.io/spring-webflow/docs/current/reference/index.html).

Quy ước vận hành có thể là:

```text
Bắt đầu hành trình mới         → checkout-v2
Tiếp tục execution checkout-v1 → giữ định nghĩa và hợp đồng v1
Mở lại bản nháp đã lưu         → khởi tạo execution mới theo chính sách hiện tại
```

`FlowDefinitionRegistry` là nơi chứa và tra định nghĩa, không phải cơ chế tự động migration execution; xem [API FlowDefinitionRegistry](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/definition/registry/FlowDefinitionRegistry.html).

### Những phần phải giữ cùng định nghĩa cũ

- State ID và event mà các trang cũ có thể gửi.
- Model/binding/validation cần cho dữ liệu cũ.
- Action bean, chữ ký phương thức và semantics của chúng.
- View và tài nguyên giao diện cần để render lại hoặc hiển thị lỗi.
- Subflow ID, input và output theo hợp đồng cũ.
- Class DTO mà snapshot cũ cần để đọc được dữ liệu.

Chỉ giữ hai XML nhưng cả hai cùng trỏ đến một action đã bị đổi hợp đồng vẫn chưa đủ. Nếu subflow v1 dùng một ID chung bị thay bằng nội dung v2, flow cha cũ vẫn có thể hỏng; cần giữ hoặc version hóa cả ranh giới đó.

ID riêng cũng không chứng minh dữ liệu nội bộ Web Flow qua một lần nâng major framework đọc được. Khi runtime không thể đọc trạng thái cũ, cần giữ runtime cũ hoặc dùng bản nháp bền vững làm điểm chuyển tiếp.

## 7. Rút phiên bản cũ khỏi flow mới nhưng vẫn cho flow cũ tiếp tục

Giả sử có hai nhóm instance A và B. Một quy trình chuyển tiếp có thể là:

1. B được triển khai và kiểm tra sẵn sàng với cấu hình, database và dịch vụ tương ứng.
2. Hành trình mới được dẫn sang B.
3. A ngừng nhận flow cấp cao nhất mới, nhưng tiếp tục nhận request của execution đã thuộc A.
4. Theo dõi số execution còn lại, lỗi tiếp tục flow và thời gian tồn tại.
5. Đến điều kiện kết thúc đã định, xử lý những execution còn lại qua chính sách bản nháp/phục hồi.
6. Sau đó mới dừng A và hoàn tất thu hẹp tài nguyên.

Cổng nhận flow mới và định tuyến execution cũ là logic ứng dụng/hạ tầng cần xây dựng; đây không phải một thuộc tính Web Flow tự động thực hiện toàn bộ quy trình.

### Định tuyến phải xảy ra trước khi đọc trạng thái không tương thích

Nếu A và B dùng chung session store nhưng không đọc được dữ liệu của nhau, một cookie định tuyến chỉ được đọc sau khi session đã deserialize là quá muộn. Điểm chọn nhóm phiên bản cần ở ranh giới thích hợp trước bước có nguy cơ đọc nhầm.

Có thể thiết kế nhóm phiên và định tuyến riêng, dùng namespace kho lưu riêng hoặc giữ tương thích serializer. Khi tách phiên, phải xử lý cả đăng nhập, đường dẫn cookie và trải nghiệm chuyển sang flow mới; không mặc định sao chép session giữa hai runtime là an toàn.

Metadata định tuyến không thay thế xác thực hoặc phân quyền. Không để tham số người dùng tự chọn một draft hoặc execution không thuộc quyền của họ.

### Sticky session chỉ giải quyết một phần

Sticky session có thể giúp request quay lại cùng nhóm/instance theo cấu hình, nhưng:

- Node bị dừng hoặc mất vẫn có thể làm mất state chỉ nằm trong bộ nhớ node.
- Cơ chế failover có thể đưa request đến một bản ứng dụng không tương thích.
- Session lưu ngoài chỉ giúp chia sẻ/lưu state; không tự cung cấp class và flow definition cũ.
- Hai tab thuộc cùng phiên có thể mở flow ở hai thời điểm, nên quy tắc định tuyến phải xử lý được tình huống thực tế đó.

Nếu affinity áp dụng toàn phiên, cần quyết định rõ người dùng còn phiên A sẽ mở flow mới ở A, chuyển toàn phiên theo cơ chế đã kiểm chứng hay dùng phạm vi phiên khác. Không hứa “flow mới luôn vào B” khi hạ tầng chỉ có thể ghim cả phiên vào A mà không có cách điều phối thêm.

### Không chặn nhầm subflow

Một execution cũ có thể cần khởi động subflow sau thời điểm ngừng nhận hành trình mới. Nếu admission control chặn mọi lần tạo flow session, hành trình cũ sẽ bị đứt giữa chừng. Chính sách cần phân biệt flow cấp cao nhất mới với session con thuộc execution đang được phép tiếp tục.

## 8. Đặt hạn kết thúc cho giai đoạn chuyển tiếp

Flow có thể tồn tại lâu vì người dùng bỏ tab hoặc liên tục gửi request giữ phiên sống. Không nên chờ vô hạn chỉ vì vẫn còn một execution không phát sinh thao tác nghiệp vụ.

Đặt chính sách dựa trên nhu cầu thật, chẳng hạn:

```text
Mốc chuyển traffic mới: T0
Hạn tiếp tục phiên bản cũ: T0 + 45 phút
Sau hạn: mở trang hướng dẫn, tải bản nháp đã lưu và bắt đầu execution mới
```

Khoảng 45 phút là ví dụ để minh họa quyết định vận hành, không phải mặc định của Web Flow. Cần chọn theo thời lượng hành trình, yêu cầu nghiệp vụ và khả năng lưu bản nháp.

Phân biệt idle timeout, tuổi tuyệt đối của execution và hạn phục vụ một bản triển khai. Nếu timeout được gia hạn theo request, việc polling có thể khiến phiên không hết hạn theo thời gian người vận hành kỳ vọng. Hạn tuyệt đối, nếu cần, phải được ứng dụng hoặc hạ tầng thực thi rõ ràng.

Không giảm session timeout đột ngột để ép “hết flow cũ” mà chưa kiểm tra ảnh hưởng đến xác thực, bản nháp và request đang xử lý.

## 9. Chuẩn bị bản nháp bền vững làm đường phục hồi

Một flow execution chứa trạng thái giao diện và điểm điều phối; bản nháp bền vững nên chứa dữ liệu nghiệp vụ đủ để mở lại hành trình theo hợp đồng mới.

Ví dụ dữ liệu bản nháp:

```json
{
  "draftId": "draft-7842",
  "schemaVersion": 2,
  "ownerId": "customer-51",
  "quantity": 2,
  "deliveryChoice": "STANDARD",
  "requestKey": "request-unique-for-this-intent",
  "submissionStatus": "NOT_SUBMITTED"
}
```

Các trường là quy ước của ứng dụng, không phải định dạng snapshot của Spring Web Flow. Khi lưu thật, cần kiểm soát phiên bản dữ liệu, cập nhật đồng thời và quyền sở hữu.

Đường phục hồi nên thực hiện:

1. Xác thực lại nếu cần, rồi kiểm tra quyền truy cập bản nháp.
2. Đọc và chuyển dữ liệu bản nháp bằng quy tắc schema của ứng dụng.
3. Kiểm tra lại giá, tồn kho và validation theo điều kiện hiện tại.
4. Đối chiếu kết quả yêu cầu đã gửi nếu có khả năng tác dụng phụ đã xảy ra.
5. Khởi tạo execution mới ở bước hợp lệ, yêu cầu người dùng xem lại thông tin cần thiết.

Không chép execution key cũ sang URL mới rồi coi đó là migration. Không sửa trực tiếp state ID trong snapshot để “nhảy qua” bước mới; cách đó có thể bỏ qua dữ liệu bắt buộc, on-entry hoặc điều kiện nghiệp vụ.

Nếu request trước triển khai đã có thể tạo đơn, cần kiểm tra trạng thái bằng mã yêu cầu và dùng cơ chế idempotency ở dịch vụ. Khôi phục màn hình hoặc rollback bản build không đảo ngược được đơn, thanh toán hay email đã gửi.

### Thông báo cần phản ánh đúng dữ liệu có thể khôi phục

Một thông báo phù hợp có thể là:

> Hệ thống vừa được cập nhật. Hãy mở lại bản nháp và kiểm tra thông tin trước khi tiếp tục.

Chỉ nói “dữ liệu đã được lưu” nếu có bằng chứng lưu thành công. Nếu dữ liệu chỉ tồn tại trong session không còn đọc được, cần thông báo đúng giới hạn thay vì hứa tiếp tục từ bước cũ.

Trang xử lý trường hợp execution không đọc được thường phải nằm ngoài chính flow đó, tại ranh giới tích hợp MVC/Web Flow. Flow chưa khôi phục được không thể tự chạy transition phục hồi bên trong nó. Cần kiểm tra hành vi của handler/adapter thực tế; xem [FlowHandlerAdapter](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/mvc/servlet/FlowHandlerAdapter.html).

## 10. Database và rollback phải được thiết kế cùng nhau

Khi A và B cùng hoạt động, schema dùng chung cần cho phép cả hai đọc/ghi trong thời gian chuyển tiếp.

Một chuỗi mở rộng rồi thu hẹp có thể là:

```text
Thêm cấu trúc dữ liệu tương thích
        ↓
Triển khai mã hiểu cả dữ liệu cũ và mới
        ↓
Chuyển dần hành trình mới, giữ hợp đồng cho hành trình cũ
        ↓
Xác nhận không còn mã/flow cần cấu trúc cũ
        ↓
Thu hẹp schema trong một đợt triển khai sau
```

Ví dụ, thêm cột tùy chọn rồi backfill có thể phù hợp hơn việc đổi tên và xóa cột đang được A sử dụng ngay trong cùng đợt. Quy tắc cụ thể phụ thuộc schema, transaction và yêu cầu nghiệp vụ.

Rollback cần trả lời riêng:

- A có đọc được trạng thái phiên mà B vừa ghi không?
- A có còn hiểu schema và dữ liệu mà B đã tạo không?
- Có thể tiếp tục để execution B ở B trong khi dừng nhận flow B mới không?
- Nếu không thể, người dùng B sẽ đi qua đường phục hồi nào?

Đưa traffic về A không đủ nếu A đã không đọc được cookie/session hoặc dữ liệu mới. Một lựa chọn có thể là dừng khởi tạo mới ở B nhưng giữ B phục vụ execution đã tồn tại, thay vì tắt B ngay. Lựa chọn này chỉ phù hợp khi lỗi của B vẫn cho phép tiếp tục các hành trình đó an toàn theo hợp đồng sản phẩm.

## 11. Kiểm thử bản A và bản B như một chuỗi thực thi

Unit test action hoặc test dùng `setCurrentState()` trong B không chứng minh B đọc được execution do A tạo. Cần giữ trạng thái thật qua hai artifact và thực hiện request tiếp theo bằng cơ chế session/repository giống môi trường triển khai.

| Kịch bản | Thao tác kiểm thử | Điều cần chứng minh |
| --- | --- | --- |
| Trang A còn mở, B nhận request | Dừng tại view ở A, gửi event sau khi chuyển sang B | Event/field cũ được xử lý hoặc phục hồi đúng |
| Snapshot A được B đọc | Lưu execution bằng A, khôi phục bằng B | Serializer, class, flow ID và state đều hợp lệ |
| Đang ở subflow A | Tạo session con, chuyển bản rồi hoàn tất | Flow cha nhận đúng output và tiếp tục đúng |
| Có lỗi binding trước triển khai | Giữ trang có giá trị thô bị từ chối | Hành vi sau cập nhật không mất dữ liệu ngoài cam kết |
| Back/refresh sau triển khai | Dùng URL/snapshot lịch sử | Không lỗi bất ngờ hoặc tạo tác dụng phụ trùng |
| B ghi rồi quay về A | Tiếp tục và lưu trạng thái ở B trước rollback | Tương thích ngược hoặc định tuyến tách biệt có hiệu lực |
| Node A mất đột ngột | Dừng node khi flow đang chờ | Failover hoặc đường bản nháp hoạt động đúng cam kết |
| Request xác nhận bị ngắt | Cắt kết nối khi kết quả có thể chưa rõ | Đối chiếu kết quả trước khi thử lại |
| Hết hạn phục vụ A | Qua mốc kết thúc đã đặt | Thông báo, tải bản nháp và flow mới hoạt động |

Nếu dùng Java serialization, nên chạy A và B với classpath riêng để tránh vô tình dùng cùng một class trong test rồi kết luận tương thích. Đồng thời kiểm tra đúng serializer session và repository, không chỉ serialize riêng một DTO nhỏ.

Các ca kiểm thử cũng cần cô lập dữ liệu và có cleanup phù hợp; giữ artifact A để kiểm tra tương thích không có nghĩa được dùng lại session của các ca không liên quan.

## 12. Theo dõi giai đoạn chuyển tiếp bằng chỉ số có ý nghĩa

Các chỉ số hữu ích gồm:

- Execution cấp cao nhất còn hoạt động theo phiên bản flow/bản triển khai.
- Tốc độ mở mới và tốc độ kết thúc theo phiên bản.
- Phân bố thời gian tồn tại và tuổi execution cũ nhất.
- Tỷ lệ lỗi tìm execution, giải tuần tự hóa, tra state và xử lý event.
- Tỷ lệ người dùng phải mở lại bản nháp, hoàn tất hoặc bỏ hành trình.
- Số lần gửi trùng bị chặn, kết quả submit chưa xác định và thời gian đối chiếu.
- Dung lượng session/snapshot, độ trễ kho phiên và bộ nhớ của nhóm instance cũ.

Có thể quan sát lifecycle bằng `FlowExecutionListener`, nhưng counter tăng lúc bắt đầu và giảm lúc end-state không tự là số execution chính xác: execution hết hạn, bị loại khỏi repository hoặc mất khi node chết có thể không đi qua đường kết thúc ứng dụng đang đếm. Cần đối soát với vòng đời kho lưu và chính sách hết hạn. Tham khảo [API FlowExecutionListener](https://docs.spring.io/spring-webflow/docs/current/api/org/springframework/webflow/execution/FlowExecutionListener.html).

Cũng phải phân biệt execution cấp cao nhất với session subflow để tránh đếm một hành trình nhiều lần. Không gắn raw session ID, execution key hoặc draft ID làm nhãn metric có số lượng giá trị không giới hạn; dùng log có correlation phù hợp khi cần điều tra một trường hợp.

### Đừng điều chỉnh giới hạn repository như một cách thay thế migration

Web Flow cho phép giới hạn số execution theo session và số snapshot lịch sử. Khi vượt số execution cho phép, execution cũ có thể bị loại; snapshot ảnh hưởng khả năng dùng lịch sử trình duyệt. Các giới hạn này được mô tả trong [Tuning Flow Execution Persistence](https://docs.spring.io/spring-webflow/docs/current/reference/index.html).

Giảm giới hạn giữa đợt rollout có thể làm tăng số người gặp URL cũ không còn dùng được. Tăng giới hạn vô hạn để giữ mọi flow cũng làm tăng chi phí lưu trữ/bộ nhớ. Chọn giới hạn theo khả năng vận hành và trải nghiệm đã kiểm thử, không dùng nó để che một hợp đồng phiên bản chưa được giải quyết.

## 13. Ví dụ một kế hoạch triển khai cụ thể

Giả sử flow v2 thêm lựa chọn giao hàng bắt buộc, còn v1 đang có người dùng tại `review`. Đội dự án chọn giữ v1 trong thời gian chuyển tiếp và lưu bản nháp cho ca còn lại.

| Giai đoạn | Hành động | Điều kiện chuyển tiếp |
| --- | --- | --- |
| Chuẩn bị | Thêm schema tương thích; giữ v1; kiểm thử v2 và đường bản nháp | Hai hợp đồng chạy được theo phạm vi đã chọn |
| Khởi động B | Kiểm tra routing, phiên, serializer và dependency | Request thử đi đúng phiên bản |
| Chuyển mở mới | Dẫn hành trình mới vào v2; không cho khởi tạo v1 mới ngoài chính sách | Không phát sinh v1 mới ngoài dự kiến |
| Phục vụ phần còn lại | Cho v1 tiếp tục; theo dõi lỗi và tuổi execution | Có đủ dữ liệu quan sát để quyết định kết thúc |
| Đến hạn | Đưa ca v1 còn lại qua trang mở lại bản nháp | Không tự gửi lại giao dịch chưa rõ kết quả |
| Dừng A/loại v1 | Chờ request cần xử lý xong; gỡ routing/tài nguyên cũ có kiểm soát | Không còn đường được phép phụ thuộc v1 |
| Thu hẹp | Xóa hợp đồng hoặc schema cũ ở đợt sau | Hết nhu cầu rollback/đọc dữ liệu cũ theo chính sách |

Các cột này là kế hoạch ứng dụng và vận hành, không phải một danh sách lệnh có thể áp dụng nguyên xi cho mọi hạ tầng.

## 14. Nguyên tắc ghi nhớ

Triển khai một ứng dụng Spring Web Flow thay đổi cả mã chạy và môi trường cần để tiếp tục một hành trình. Một lần triển khai đáng tin cần xác định rõ **execution cũ sẽ được ai phục vụ, dữ liệu nào còn đọc được, giới hạn chuyển tiếp là gì và người dùng sẽ phục hồi thế nào nếu không thể tiếp tục**.

Giữ một session store không thay thế tương thích phiên bản. Graceful shutdown không thay thế phục vụ flow đang chờ. Bản nháp bền vững không thay thế việc đối chiếu tác dụng phụ đã xảy ra. Khi từng ranh giới được thiết kế và kiểm thử rõ ràng, phiên bản mới mới có thể được đưa vào mà không biến những hành trình đang dở thành lỗi khó phục hồi.