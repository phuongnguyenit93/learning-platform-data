# Thiết kế action có thể được gọi lại an toàn

Spring Web Flow dùng state, event và transition để điều khiển một hành trình web nhiều bước. Trong đó, **action-state** thực thi một hoặc nhiều action rồi chuyển flow theo event mà action trả về. Ví dụ, sau khi người dùng xác nhận thông tin đặt chỗ, flow có thể vào action-state để giữ chỗ, ghi nhận kết quả và chuyển sang màn hình xác nhận.

Action-state có thể được vào lại khi flow có transition quay về, khi người dùng gửi lại một yêu cầu, khi ứng dụng khôi phục một flow execution hoặc khi tầng gọi dịch vụ thử lại sau lỗi mạng. Một action tạo tác dụng phụ như tạo đơn, giữ chỗ, trừ tiền hay gửi thông báo vì thế có thể được gọi nhiều lần cho cùng một ý định nghiệp vụ.

Thiết kế action an toàn khi được gọi lại nghĩa là cùng một lệnh nghiệp vụ có thể được xử lý lặp mà không tạo thêm tác dụng phụ ngoài dự kiến. Cách làm cốt lõi là tách action điều phối của Spring Web Flow khỏi logic nghiệp vụ, dùng mã định danh ổn định cho từng lệnh và bảo đảm tầng lưu trữ kiểm soát yêu cầu trùng.

## 1. Action-state thực thi action như thế nào?

Action-state là một state không hiển thị view. Khi flow đi vào state này, Spring Web Flow thực thi action được khai báo. Kết quả action là một event; các transition dựa vào event đó để quyết định state tiếp theo.

Ví dụ, flow đặt chỗ có thể có hành trình:

~~~text
Nhập thông tin
     |
     | submit
     v
Action-state: giữ chỗ
     |
     +---- success ------> Màn hình xác nhận
     |
     +---- rejected -----> Quay lại chỉnh sửa
     |
     +---- lỗi kỹ thuật -> Luồng xử lý lỗi / thử lại
~~~

Một action có thể được gọi lại trong các tình huống:

- Flow có transition quay lại action-state hoặc một nhánh điều khiển đưa flow vào state đó lần nữa.
- Người dùng gửi lặp một event do nhấn nút nhiều lần hoặc trình duyệt gửi lại request.
- Client, gateway hoặc tầng dịch vụ retry sau timeout. Máy chủ có thể đã xử lý xong nhưng phản hồi chưa đến được client.
- Flow execution được khôi phục hoặc tiếp tục và logic điều khiển khiến action được thực thi lại.
- Một luồng xử lý nền hoặc thao tác quản trị gọi lại cùng lệnh nghiệp vụ.

Không nên hiểu rằng mọi HTTP refresh đều tự động chạy lại action-state. Việc thực thi lại phụ thuộc flow execution, event và transition cụ thể. Tuy nhiên, action cần chịu được việc được gọi lại bởi bất kỳ đường đi hợp lệ nào, bởi vì hệ thống phân tán không thể luôn biết chắc một lần gọi trước đã hoàn tất hay chưa khi kết nối bị gián đoạn.

## 2. Idempotency là gì?

Một thao tác có tính **idempotent** khi thực hiện nhiều lần với cùng một ý định và cùng dữ liệu không làm thay đổi kết quả nghiệp vụ so với thực hiện một lần. Có thể biểu diễn khái niệm này bằng:

\[
f(f(x)) = f(x)
\]

Trong ứng dụng, điều đó có nghĩa lệnh giữ chỗ có cùng mã yêu cầu khi được gửi lại chỉ tạo một lần giữ chỗ; các lần gọi sau trả về kết quả đã ghi nhận.

Không phải mọi thao tác có vẻ giống nhau đều idempotent:

| Thao tác | Đặc tính khi gọi lặp | Cách xử lý |
|---|---|---|
| Đặt trạng thái đơn hàng thành **CONFIRMED** | Thường idempotent nếu chỉ cập nhật cùng trạng thái và không phát sinh tác dụng phụ lặp. | Có thể thực hiện lại, nhưng cần kiểm soát event hoặc thông báo đi kèm. |
| Tăng số lượng tồn kho thêm 1 | Không idempotent; mỗi lần gọi làm thay đổi số lượng. | Dùng mã lệnh duy nhất và ghi nhận lệnh đã áp dụng. |
| Tạo một lượt giữ chỗ mới | Không idempotent nếu mỗi lần gọi tạo một bản ghi mới. | Dùng idempotency key và ràng buộc duy nhất. |
| Trừ tiền từ tài khoản | Không idempotent nếu mỗi lần gọi tạo một giao dịch trừ tiền. | Dùng mã giao dịch ổn định và cơ chế chống trùng ở hệ thống thanh toán. |
| Đọc thông tin đặt chỗ | Thường không tạo tác dụng phụ. | Có thể gọi lại, lưu ý tính nhất quán dữ liệu. |

Idempotency không có nghĩa là mọi lần gọi đều phải trả cùng mã HTTP hoặc cùng thông báo giao diện. Điều cần bảo đảm là cùng một lệnh không tạo thêm hiệu ứng nghiệp vụ và hệ thống có thể trả lại kết quả đã được ghi nhận.

## 3. Phân tách action điều phối và nghiệp vụ

Action của Spring Web Flow nên đảm nhiệm việc đọc dữ liệu từ flow context, gọi dịch vụ nghiệp vụ, đưa kết quả cần thiết vào scope và trả event để transition tiếp tục. Quy tắc giữ chỗ, chống trùng và lưu giao dịch nên nằm trong service/domain layer.

Cách phân tách này giúp logic nghiệp vụ được bảo vệ ngay cả khi nó được gọi từ một action-state khác, REST endpoint, tác vụ nền hoặc một ứng dụng khác. Nếu chỉ kiểm tra trùng trong action, một đường gọi khác có thể bỏ qua kiểm tra đó.

Ví dụ dưới đây dùng Action của Spring Web Flow để điều phối lệnh giữ chỗ:

~~~java
import org.springframework.webflow.execution.Action;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public class ReserveBookingAction implements Action {

    private final ReservationService reservationService;

    public ReserveBookingAction(ReservationService reservationService) {
        this.reservationService = reservationService;
    }

    @Override
    public Event execute(RequestContext context) {
        BookingCommand command =
                (BookingCommand) context.getFlowScope().get("bookingCommand");

        ReservationResult result = reservationService.reserve(command);
        context.getFlowScope().put("reservationResult", result);

        return new Event(this, result.isAccepted() ? "success" : "rejected");
    }
}
~~~

Action lấy lệnh đã được chuẩn bị trước đó trong flow scope, gọi ReservationService và trả event. Bản thân action không tự tạo bản ghi giữ chỗ, không tự gửi email và không tự gọi cổng thanh toán. Service phải bảo đảm lệnh có thể được gửi lại an toàn.

Khai báo action-state trong định nghĩa flow:

~~~xml
<action-state id="reserveBooking">
    <evaluate expression="reserveBookingAction.execute(flowRequestContext)"/>
    <transition on="success" to="bookingConfirmation"/>
    <transition on="rejected" to="editBooking"/>
</action-state>
~~~

Bean **reserveBookingAction** cần được đăng ký trong Spring application context mà flow có thể truy cập. **flowRequestContext** cung cấp context của lần thực thi flow hiện tại; action dùng nó để truy cập flow scope. Event **success** hoặc **rejected** quyết định transition tiếp theo.

Ví dụ này giả định **BookingCommand** đã chứa một idempotency key ổn định. Không tạo key mới ngay trong **execute()**, bởi action có thể được gọi lại và mỗi key mới sẽ khiến cùng một ý định bị xem như một lệnh khác.

## 4. Tạo idempotency key ổn định

**Idempotency key** là mã nhận diện một lệnh nghiệp vụ cụ thể. Với flow đặt chỗ, mỗi lần người dùng bắt đầu một ý định đặt chỗ mới cần có một key riêng. Mọi lần retry hoặc gửi lặp của chính ý định đó phải dùng lại key ban đầu.

Key có thể được tạo ở thời điểm bắt đầu lệnh, ví dụ khi người dùng bắt đầu bước xác nhận hoặc khi máy chủ tiếp nhận một yêu cầu tạo đặt chỗ. Key thường là UUID hoặc mã ngẫu nhiên đủ mạnh, nhưng điều quan trọng hơn định dạng là vòng đời của nó:

1. Tạo key một lần cho ý định nghiệp vụ mới.
2. Lưu key cùng command trong flow scope để các bước tiếp theo dùng lại.
3. Gửi key đến service nghiệp vụ trong mỗi lần thử thực hiện cùng command.
4. Lưu key bền vững ở tầng dữ liệu để chống trùng kể cả khi flow execution hết hạn hoặc ứng dụng khởi động lại.
5. Chỉ tạo key mới khi người dùng thực sự bắt đầu một ý định nghiệp vụ mới.

Ví dụ, command có thể có cấu trúc:

~~~java
public class BookingCommand {
    private String idempotencyKey;
    private String customerId;
    private String roomType;
    private String checkInDate;
    private String checkOutDate;

    // Constructors, getters and setters
}
~~~

Khi tạo command, ứng dụng gán key một lần rồi lưu command trong flow scope. Trong các request tiếp theo, action tiếp tục sử dụng cùng command. Nếu người dùng sửa dữ liệu làm thay đổi ý định nghiệp vụ sau khi đã xác nhận, ứng dụng cần xác định đó là command mới và cấp key mới theo quy tắc nghiệp vụ.

Không dùng các giá trị thay đổi theo từng lần gọi như timestamp hiện tại hoặc UUID tạo trong mỗi lần retry làm key. Cũng không dùng một key chung cho mọi lệnh của người dùng, vì như vậy các thao tác hợp lệ khác nhau có thể bị nhận nhầm là cùng một yêu cầu.

## 5. Bảo vệ thao tác ở tầng dữ liệu

Chỉ kiểm tra xem key đã tồn tại trước khi ghi dữ liệu là chưa đủ. Hai request đồng thời có thể cùng kiểm tra và đều thấy key chưa tồn tại, sau đó cùng tạo giao dịch. Đây là lỗi tranh chấp thường được gọi là race condition.

Hãy dùng ràng buộc duy nhất ở cơ sở dữ liệu làm lớp bảo vệ cuối cùng. Ví dụ bảng lưu trạng thái xử lý lệnh:

~~~sql
CREATE TABLE flow_operation (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    operation_type VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL,
    result_reference VARCHAR(120),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_flow_operation
        UNIQUE (operation_type, idempotency_key)
);
~~~

Các trường có ý nghĩa:

- **operation_type** phân biệt các loại lệnh, ví dụ **RESERVE_BOOKING** và **CANCEL_BOOKING**.
- **idempotency_key** nhận diện một ý định nghiệp vụ.
- **payload_hash** giúp phát hiện trường hợp cùng key nhưng dữ liệu command khác nhau.
- **status** lưu tiến trình xử lý, chẳng hạn **PENDING**, **COMPLETED** hoặc **FAILED**.
- **result_reference** tham chiếu kết quả nghiệp vụ đã tạo.

Quy trình xử lý ở service có thể mô tả như sau:

~~~text
Nhận command + idempotency key
              |
              v
     Tạo/chiếm bản ghi key
              |
       +------+------+
       |             |
       v             v
    Key mới       Key đã tồn tại
       |             |
       v             v
 Kiểm tra dữ liệu  So sánh payload
       |             |
       v         +---+----------------+
 Thực hiện       |                    |
 nghiệp vụ       v                    v
       |     Payload giống       Payload khác
       v          |                    |
 Lưu kết quả      v                    v
 cùng trạng thái Trả kết quả cũ     Từ chối xung đột
 trong transaction
~~~

Các bước này cần được triển khai bằng transaction và cơ chế đồng bộ phù hợp với cơ sở dữ liệu đang dùng:

1. Thử tạo bản ghi cho cặp **operation_type** và **idempotency_key**.
2. Nếu tạo thành công, thực hiện thay đổi nghiệp vụ và ghi kết quả cùng transaction.
3. Nếu key đã tồn tại, đọc bản ghi hiện có. Nếu payload giống và đã hoàn tất, trả lại kết quả đã lưu.
4. Nếu key đang được xử lý, áp dụng chính sách chờ, trả trạng thái đang xử lý hoặc cho phép truy vấn lại sau; không thực hiện song song một tác dụng phụ thứ hai.
5. Nếu payload khác, trả lỗi xung đột vì cùng key đang được dùng cho hai ý định khác nhau.

Ràng buộc unique xử lý được cuộc đua giữa các request. Chi tiết bắt lỗi duplicate key, transaction isolation và cách đọc lại bản ghi cần được triển khai theo database và framework cụ thể. Tránh mô hình kiểm tra bằng SELECT rồi INSERT mà không có unique constraint hoặc khóa phù hợp.

Với thay đổi dữ liệu nội bộ nằm trong cùng cơ sở dữ liệu, hãy ghi bản ghi operation, cập nhật nghiệp vụ và kết quả trong cùng transaction. Khi transaction rollback, cả thay đổi nghiệp vụ và dấu ghi nhận lệnh phải rollback cùng nhau. Khi commit thành công nhưng phản hồi bị mất, lần gọi lại sẽ tìm thấy key đã hoàn tất và trả lại kết quả cũ.

## 6. Xử lý tác dụng phụ bên ngoài

Giao dịch cơ sở dữ liệu và lời gọi đến hệ thống bên ngoài thường không nằm trong cùng một transaction. Ví dụ, service ghi nhận đặt chỗ trong database rồi gọi cổng thanh toán hoặc gửi email. Nếu ứng dụng gửi email thành công nhưng gặp lỗi trước khi lưu trạng thái hoàn tất, lần retry có thể gửi email lần thứ hai.

Một số nguyên tắc giúp xử lý tình huống này:

- Nếu cổng thanh toán hỗ trợ idempotency key, gửi cùng key của giao dịch nghiệp vụ trong mọi lần retry.
- Với email, webhook hoặc thông điệp, ghi một bản ghi outbox trong cùng transaction với thay đổi nghiệp vụ.
- Worker đọc outbox và gửi thông điệp. Mỗi thông điệp có event id ổn định; consumer lưu event id đã xử lý để loại bỏ lần giao lại.
- Thiết kế trạng thái rõ ràng như **PENDING**, **SENT**, **FAILED** và chính sách retry có giới hạn.
- Có cơ chế đối soát hoặc xử lý thủ công cho các trường hợp không thể xác định chắc chắn hệ thống ngoài đã nhận yêu cầu hay chưa.

Mô hình transactional outbox:

~~~text
Spring Web Flow Action
          |
          v
   ReservationService
          |
          v
    Database transaction
       |           |
       v           v
  Booking row   Outbox row
       |           |
       +-----+-----+
             |
          COMMIT
             |
             v
       Outbox worker
             |
             v
     External service
             |
             v
   Consumer/provider deduplication
~~~

Outbox bảo đảm thay đổi nghiệp vụ và ý định gửi thông điệp được ghi nhận nguyên tử trong database. Worker có thể gửi lại thông điệp nếu không nhận được xác nhận. Vì vậy consumer hoặc dịch vụ đích vẫn cần deduplicate bằng event id hoặc idempotency key. Không nên tuyên bố hệ thống đạt exactly-once chỉ vì đã dùng outbox; thực tế thường là giao ít nhất một lần kết hợp xử lý lặp an toàn.

## 7. Phân biệt lỗi có thể retry và lỗi nghiệp vụ

Không phải mọi lỗi đều nên được thử lại. Action hoặc service cần phân loại kết quả để flow đưa ra transition phù hợp:

| Kết quả | Ví dụ | Hướng xử lý |
|---|---|---|
| Thành công | Giữ chỗ đã được ghi nhận. | Chuyển đến state xác nhận; lưu kết quả để lần gọi lại trả cùng kết quả. |
| Từ chối nghiệp vụ | Hết phòng hoặc dữ liệu không hợp lệ. | Trả event nghiệp vụ như **rejected**; cho phép người dùng sửa hoặc chọn phương án khác. |
| Đang xử lý | Key đã được một request khác chiếm và chưa có kết quả cuối. | Hiển thị trạng thái chờ hoặc cho phép truy vấn lại theo chính sách. |
| Lỗi tạm thời | Database tạm gián đoạn hoặc dịch vụ ngoài timeout. | Retry có giới hạn với cùng key và backoff. |
| Lỗi không thể retry | Cấu hình sai, dữ liệu vi phạm quy tắc cố định hoặc payload xung đột key. | Ghi log, trả lỗi thích hợp và yêu cầu xử lý nguyên nhân. |

Timeout không chứng minh thao tác thất bại. Dịch vụ đích có thể đã xử lý xong nhưng phản hồi bị mất. Trong tình huống không rõ kết quả, hãy truy vấn trạng thái theo key hoặc gửi lại cùng key đến dịch vụ có hỗ trợ idempotency. Không cấp key mới chỉ để vượt qua timeout, vì điều đó có thể tạo giao dịch thứ hai.

Retry nên có giới hạn số lần, khoảng chờ tăng dần và có jitter khi nhiều request có thể đồng loạt thử lại. Không retry vô hạn trong action-state vì có thể giữ flow execution và tài nguyên máy chủ quá lâu. Với tác vụ dài, nên chuyển sang xử lý bất đồng bộ và để flow hiển thị trạng thái đang xử lý.

## 8. Tránh đặt tác dụng phụ trong logic hiển thị

View-state dùng để hiển thị màn hình và nhận dữ liệu từ người dùng. Logic tạo dữ liệu hoặc thực hiện giao dịch nên nằm trong action-state hay service được gọi tại điểm chuyển trạng thái phù hợp.

Không nên gửi email, tạo đơn hàng hoặc trừ tiền trong logic render view. View có thể được render lại khi người dùng quay lại, refresh, validation thất bại hoặc flow tiếp tục. Nếu render view đồng thời tạo tác dụng phụ, một thao tác hiển thị có thể vô tình kích hoạt nghiệp vụ lần nữa.

Tương tự, các action chạy khi vào state hoặc khi bắt đầu flow cũng cần được xem là có khả năng được thực thi lại nếu luồng điều khiển quay lại hoặc flow được khởi tạo mới. Nếu action chỉ chuẩn bị dữ liệu đọc, việc gọi lại thường ít rủi ro. Nếu action ghi dữ liệu, cần áp dụng idempotency như với action-state.

## 9. Kiểm thử action được gọi lại

Kiểm thử một lần gọi thành công chưa đủ chứng minh action an toàn. Cần kiểm tra lặp, đồng thời và các điểm lỗi có thể xuất hiện giữa lúc thực hiện tác dụng phụ và lúc trả kết quả.

Các trường hợp nên có trong kiểm thử service và tích hợp flow:

1. **Gọi hai lần tuần tự cùng key và cùng payload.** Chỉ có một bản ghi nghiệp vụ; lần thứ hai trả kết quả đã lưu.
2. **Gọi đồng thời cùng key.** Database chỉ chấp nhận một operation; request còn lại nhận kết quả cũ hoặc trạng thái đang xử lý theo chính sách.
3. **Dùng cùng key nhưng payload khác.** Service từ chối xung đột và không thay đổi dữ liệu nghiệp vụ.
4. **Giả lập timeout sau khi commit.** Gọi lại cùng key và xác nhận không tạo giao dịch mới.
5. **Giả lập rollback trước commit.** Xác nhận không còn bản ghi operation hoàn tất hoặc thay đổi nghiệp vụ dở dang.
6. **Gọi lại action-state qua transition quay lại.** Xác nhận action trả kết quả cũ thay vì thực hiện tác dụng phụ lần nữa.
7. **Kiểm thử outbox được giao lặp.** Consumer xử lý một event id nhiều lần nhưng chỉ áp dụng hiệu ứng một lần.
8. **Kiểm thử lỗi nghiệp vụ và lỗi tạm thời.** Flow chuyển đúng state, retry đúng loại lỗi và giữ nguyên idempotency key.

Ngoài kết quả trả về, hãy kiểm tra số bản ghi được tạo, số lần trừ tiền giả lập, số thông điệp outbox và trạng thái operation. Với kiểm thử đồng thời, dùng nhiều transaction hoặc request độc lập để tái hiện cuộc đua ở database.

## 10. Checklist thiết kế action an toàn

Trước khi đưa một action có tác dụng phụ vào flow, hãy xác nhận:

- Lệnh nghiệp vụ có một idempotency key ổn định và được tạo đúng một lần cho một ý định.
- Key được lưu bền vững cùng loại operation; flow scope chỉ là nơi mang key qua các bước của flow.
- Database có unique constraint hoặc cơ chế khóa tương đương để xử lý request đồng thời.
- Cùng key và cùng payload trả về kết quả đã lưu; cùng key nhưng payload khác bị từ chối.
- Thay đổi nghiệp vụ và trạng thái operation được ghi trong transaction phù hợp.
- Tác dụng phụ ngoài database có cơ chế deduplication, outbox hoặc key do nhà cung cấp hỗ trợ.
- Lỗi được phân loại; retry có giới hạn và luôn dùng cùng key cho cùng command.
- View và logic render không thực hiện thao tác ghi không idempotent.
- Kiểm thử bao gồm gọi lặp, request đồng thời, timeout, rollback và flow re-entry.

## 11. Ghi nhớ

Action-state giúp Spring Web Flow đưa nghiệp vụ vào một bước điều phối rõ ràng và chuyển tiếp theo event. Tuy nhiên, action có thể được gọi lại khi flow đi vào state nhiều lần, request bị gửi lặp hoặc hệ thống retry sau sự cố. Vì vậy, không dựa vào giả định một action chỉ chạy đúng một lần.

Hãy để action điều phối context và event, còn service nghiệp vụ chịu trách nhiệm thực hiện lệnh idempotent. Dùng key ổn định, unique constraint, transaction và cơ chế deduplication cho tác dụng phụ bên ngoài. Khi đó, cùng một lệnh có thể được thử lại an toàn, flow có thể phục hồi sau lỗi và người dùng không vô tình tạo nhiều giao dịch cho một ý định duy nhất.
