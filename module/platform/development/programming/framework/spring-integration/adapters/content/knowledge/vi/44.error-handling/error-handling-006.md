# Error flow xử lý bù trong Spring Integration Adapters

## 1. Bài toán: lỗi xảy ra sau khi hệ thống khác đã thay đổi trạng thái

Trong module **SPRING_INTEGRATION_ADAPTERS**, Spring Integration giúp kết nối hệ thống bằng **inbound/outbound adapter**, **gateway**, **poller** và **MessageChannel**. Một luồng có thể đọc file qua SFTP, ghi database, gọi HTTP của đối tác, phát sự kiện qua Kafka rồi gửi thông báo. Vấn đề xuất hiện khi **một hoặc nhiều bước đã thành công nhưng bước kế tiếp thất bại**.

Xét quy trình đặt hàng:

1. Nhận yêu cầu tạo đơn từ HTTP inbound gateway.
2. Giữ hàng trong database nội bộ: thành công.
3. Gọi HTTP API của đơn vị vận chuyển để tạo phiếu: thành công.
4. Gửi thông điệp xác nhận tới hệ thống thanh toán qua broker: thất bại.

Nếu chỉ log exception ở bước 4, hàng vẫn bị giữ và phiếu vận chuyển đã tồn tại, trong khi đơn chưa hoàn tất. Nếu retry toàn bộ luồng mà không kiểm tra trạng thái, hệ thống có thể **giữ hàng hai lần và tạo hai phiếu**.

**Error flow xử lý bù** là một luồng xử lý lỗi được thiết kế để **khôi phục tính nhất quán nghiệp vụ** bằng cách thực hiện các hành động bù có kiểm soát cho những tác động đã xảy ra, hoặc bằng cách chuyển quy trình sang trạng thái cần đối soát/thao tác thủ công khi không thể đảo ngược an toàn.

Ví dụ:

- Đã giữ hàng → **giải phóng phần hàng đã giữ** khi hủy đơn;
- Đã tạo phiếu vận chuyển → **gửi yêu cầu hủy phiếu** nếu phía vận chuyển hỗ trợ;
- Đã ghi nhận thanh toán → **tạo giao dịch hoàn tiền**, không xóa lịch sử thanh toán;
- Đã gửi email hoặc sự kiện Kafka → không thể “thu hồi” chắc chắn; có thể **gửi thông báo đính chính/sự kiện bù**.

Trong Spring Integration, error flow có thể bắt đầu từ **ErrorMessage** được gửi tới **errorChannel** hoặc kênh lỗi riêng. Nhưng **framework không tự động suy ra bước nào phải bù, không cung cấp rollback xuyên mọi hệ thống và không biến một ErrorMessage thành một saga bền vững**. Ứng dụng phải định nghĩa state, business keys, compensation commands và phương thức xác minh kết quả.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **retry**, **rollback**, **compensation**, **reconciliation** và **manual recovery**.
2. Nhận diện ranh giới transaction khi kết nối File/SFTP, HTTP, JMS/AMQP, Kafka và database.
3. Thiết kế error flow nhận **ErrorMessage** nhưng vẫn lưu đủ bối cảnh nghiệp vụ để xử lý bù.
4. Mô hình hóa một chuỗi bước kiểu **saga**, biết bước nào có thể đảo ngược và bước nào không.
5. Đảm bảo **idempotency**, retry hữu hạn, dữ liệu trạng thái bền vững và chống thực hiện bù hai lần.
6. Xử lý trường hợp **timeout nhưng chưa biết phía ngoài đã thành công hay thất bại**.
7. Lập chiến lược test, audit, cảnh báo và runbook cho lỗi xử lý bù.

## 2. Phân biệt retry, rollback và xử lý bù

Đây là ba cơ chế khác nhau, phục vụ ba loại vấn đề khác nhau.

| Cơ chế | Khi nào phù hợp? | Có đảo tác động đã commit ở hệ thống ngoài không? |
|---|---|---|
| **Retry** | Lỗi tạm thời, thao tác lặp an toàn | Không; có thể gây trùng nếu thiếu idempotency |
| **Rollback** | Các thao tác cùng một transaction chưa commit | Chỉ trong ranh giới transaction có hỗ trợ |
| **Compensation** | Một bước đã commit hoặc đã tạo side effect cần khắc phục | Có thể bằng nghiệp vụ bù, không nhất thiết khôi phục chính xác trạng thái trước |
| **Reconciliation** | Chưa biết kết quả thực hoặc state giữa hệ thống lệch nhau | Phát hiện khác biệt, dẫn tới retry/bù/điều chỉnh |
| **Manual intervention** | Không đủ thông tin hoặc không có bù tự động an toàn | Phụ thuộc quyết định có thẩm quyền và quy trình vận hành |

### 2.1. Retry không phải bù

Một HTTP outbound gateway gặp 503 trước khi phía đích xử lý có thể retry sau backoff. Nhưng nếu request đã tạo phiếu thành công rồi response bị mất, gửi lại POST có thể tạo phiếu thứ hai. Khi đó cần **idempotency key, API tra cứu trạng thái** hoặc cơ chế phát hiện yêu cầu trùng trước khi retry.

### 2.2. Rollback không vượt qua ranh giới tùy ý

Transaction JDBC có thể rollback các thay đổi chưa commit trong cùng nguồn dữ liệu. Nó **không tự rollback** một lời gọi HTTP đã được phía đối tác xử lý, file SFTP đã được đổi tên, email đã gửi hoặc Kafka record đã được một consumer khác đọc.

Ngay cả khi dùng transaction ở một broker, phạm vi atomicity chỉ gồm những tài nguyên được transaction đó quản lý đúng cách. **Không giả định @Transactional cho cả flow Spring Integration sẽ bao trùm tất cả adapter**.

### 2.3. Compensation là hành động nghiệp vụ mới

Giải phóng một lượng hàng đã giữ thường là **một giao dịch mới** và cần ghi audit mới. Hoàn tiền cũng là một giao dịch riêng, không xóa thanh toán cũ. Các hệ thống có thể có phí xử lý, delay hoặc hành động không đảo được; compensation có thể đạt trạng thái nhất quán nghiệp vụ **mà không hoàn nguyên y hệt lịch sử kỹ thuật**.

### 2.4. Không phải mọi lỗi đều cần bù

Nếu validation thất bại **trước mọi side effect**, chỉ cần trả lỗi hoặc cách ly dữ liệu. Nếu lỗi tạm thời và retry an toàn, không cần lập tức hủy đơn. Nếu thao tác ngoài có kết quả chưa rõ, cần đối soát trước khi bù — tránh hủy nhầm một hành động chưa xảy ra hoặc tạo hành động trái kỳ vọng.

## 3. Những ranh giới khiến bù trở nên cần thiết

| Adapter / gateway | Tác động có thể đã xảy ra | Bù có thể áp dụng | Giới hạn cần nhớ |
|---|---|---|---|
| **File inbound/outbound** | File đã được di chuyển, xóa, ghi đè | Khôi phục từ bản an toàn hoặc đưa về hàng chờ | File đã bị consumer khác đọc có thể không thu hồi được |
| **SFTP** | File đã tải, rename, delete hoặc upload một phần | Tạo file hủy, chuyển trạng thái hoặc upload bản sửa | Remote server có thể đã xử lý file trước khi bù |
| **HTTP** | Đã tạo đơn, booking, charge, request ngoài | Cancel, release, refund, update trạng thái | Timeout không xác định kết quả; API bù cần được đối tác hỗ trợ |
| **JMS** | Message đã gửi/ack, consumer đã xử lý | Gửi command bù hoặc nghiệp vụ mới | Không thể mặc định “unsend” message đã tiêu thụ |
| **AMQP** | Message đã tới queue, consumer có side effect | Event/command bù, DLQ cho lỗi xử lý | Ack/nack khác với undo một nghiệp vụ đã commit |
| **Kafka** | Record đã publish và được nhiều consumer đọc | Phát sự kiện điều chỉnh/đảo tác động | Không thể thu hồi chắc chắn record đã phát |
| **JDBC** | Row đã commit, transaction khác đã đọc | Giao dịch bù cập nhật trạng thái/giải phóng tài nguyên | Xóa dữ liệu có thể phá audit hoặc ràng buộc nghiệp vụ |

### 3.1. Không gộp hai loại lỗi

**Transport failure:** không kết nối được SFTP, broker ngắt, timeout HTTP. Hệ thống có thể chưa tạo tác động.

**Business inconsistency:** hai trong ba dịch vụ đã commit; dịch vụ cuối thất bại. Đây là trường hợp cần **quyết định tiếp tục, retry có kiểm soát hoặc bù**.

Nếu gom cả hai vào một error handler tự động gọi “cancelOrder” mỗi khi exception xuất hiện, hệ thống dễ hủy sai hoặc gây nhiều lỗi hơn.

### 3.2. Hiểu delivery semantics

Nhận một ErrorMessage **không đồng nghĩa source message chưa được acknowledge**. JMS/AMQP container, Kafka offset commit, File poller filter và JDBC transaction có cơ chế riêng. Error flow cần phối hợp với chúng: nếu muốn retry sau restart, phải có input hoặc recovery command được giữ bền vững.

## 4. Kiến trúc: forward flow, error flow và compensation flow

~~~mermaid
flowchart TD
    SRC["Inbound adapter/gateway"] --> COR["Correlation và validation"]
    COR --> S1["S1: Reserve inventory"]
    S1 --> SAVE1["Persist trạng thái STEP1_DONE"]
    SAVE1 --> S2["S2: Create delivery via HTTP"]
    S2 --> SAVE2["Persist trạng thái STEP2_DONE"]
    SAVE2 --> S3["S3: Publish confirmation"]
    S3 --> DONE["COMPLETED"]
    S1 -. "Lỗi" .-> ER["Error publisher nếu được cấu hình"]
    S2 -. "Lỗi" .-> ER
    S3 -. "Lỗi" .-> ER
    ER --> EC["errorChannel hoặc channel riêng"]
    EC --> CL["Classify + resolve sagaId"]
    CL --> DEC{"Retry, reconcile hay compensate?"}
    DEC -->|"Transient, safe"| RET["Retry có giới hạn"]
    DEC -->|"Outcome unknown"| QUERY["Query/reconcile external state"]
    DEC -->|"Cancel nghiệp vụ"| COMP["Durable compensation commands"]
    QUERY --> DEC
    COMP --> C2["C2: Cancel delivery nếu đã tạo"]
    C2 --> C1["C1: Release inventory"]
    C1 --> VERIFIED["COMPENSATED / verified"]
    RET --> S3
    COMP --> EX["Cần can thiệp nếu bù thất bại"]
~~~

Sơ đồ minh họa **một saga điều phối bằng ứng dụng**. Không phải Spring Integration tự sinh các bước C1/C2 từ S1/S2; business state và compensation commands phải được định nghĩa. Đường ErrorMessage cũng chỉ xuất hiện khi **exception được một error publisher thật sự bắt và gửi**, không phải mọi exception đồng bộ tự vào channel.

### 4.1. Tách ba mặt phẳng trách nhiệm

1. **Message transport:** inbound/outbound adapter, gateway, MessageChannel, poller, listener chuyển thông điệp.
2. **Business orchestration:** saga coordinator lưu bước đã hoàn tất, tác động ngoài và mục tiêu nghiệp vụ.
3. **Error/recovery control:** phân loại lỗi, chọn retry/reconciliation/compensation, theo dõi failures và kích hoạt vận hành.

Với tích hợp ngắn, coordinator có thể nằm trong một service/DB. Với quy trình kéo dài hoặc phân tán, có thể dùng state machine hoặc workflow engine chuyên dụng. Không cần mặc định triển khai một saga engine nếu bài toán chỉ là transaction DB cục bộ.

### 4.2. Orchestration và choreography

| Cách tổ chức | Mô tả | Ưu điểm | Cần chú ý |
|---|---|---|---|
| **Orchestration** | Coordinator ra lệnh cho từng bước và bước bù | Dễ theo dõi trạng thái tổng thể, thứ tự bù | Coordinator và state store phải đủ tin cậy |
| **Choreography** | Các service phản ứng sự kiện và phát sự kiện bù | Ít coupling tới một điều phối viên | Khó nhìn toàn cảnh, cần correlation và kiểm soát vòng sự kiện |

Spring Integration hỗ trợ xây luồng message cho cả hai, nhưng quy tắc saga và dữ liệu orchestration phải do ứng dụng thiết kế.

### 4.3. Bù theo thứ tự ngược khi có phụ thuộc

Nếu S1 giữ hàng và S2 tạo phiếu dựa trên hàng đó, khi hủy đơn thường **hủy phiếu (C2) trước**, rồi **giải phóng hàng (C1)**. Tuy nhiên không nên áp dụng quy tắc thứ tự ngược một cách máy móc: nếu có dependency, phí bù, deadline hoặc tác vụ không đảo được, cần policy từng bước.

## 5. Mô hình trạng thái bền vững cho xử lý bù

Một ErrorMessage chỉ tồn tại trong kênh thông điệp lúc đang xử lý; để phục hồi qua restart, cần lưu **saga state và các tác vụ bù** bền vững.

### 5.1. Trạng thái saga gợi ý

| State | Ý nghĩa |
|---|---|
| NEW | Đã nhận yêu cầu, chưa tạo side effect |
| RUNNING | Đang thực hiện forward steps |
| STEP_COMPLETED | Bước cụ thể đã xác nhận kết quả |
| RESULT_UNKNOWN | Một bước có timeout hoặc outcome chưa rõ |
| COMPENSATION_REQUIRED | Đã quyết định phải bù các bước đã hoàn tất |
| COMPENSATING | Các compensation commands đang chạy |
| COMPENSATION_RETRY | Một bù lỗi tạm thời và đang chờ retry |
| COMPENSATED | Các bù cần thiết đã được xác nhận hoàn tất |
| COMPLETED | Forward flow thành công theo hợp đồng |
| MANUAL_REVIEW | Không thể quyết định hoặc bù tự động an toàn |
| FAILED_TERMINAL | Dừng với trạng thái thất bại có kiểm soát/bằng chứng |

Không phải mọi saga cần tất cả trạng thái; điều bắt buộc là phân biệt **“đã nhận ErrorMessage”**, **“đã lên lịch bù”** và **“bù đã có hiệu lực”**.

### 5.2. Hồ sơ saga minh họa

~~~json
{
  "sagaId": "saga-order-274",
  "businessKey": "order-274",
  "tenantId": "tenant-B",
  "state": "COMPENSATION_REQUIRED",
  "version": 7,
  "steps": [
    {
      "name": "RESERVE_INVENTORY",
      "status": "SUCCEEDED",
      "resourceId": "reservation-R274"
    },
    {
      "name": "CREATE_DELIVERY",
      "status": "SUCCEEDED",
      "resourceId": "shipment-S274"
    },
    {
      "name": "PUBLISH_CONFIRMATION",
      "status": "FAILED",
      "resourceId": null
    }
  ],
  "error": {
    "stage": "PUBLISH_CONFIRMATION",
    "classification": "TRANSIENT",
    "correlationId": "import-batch-012",
    "attempt": 3
  }
}
~~~

Đây là schema nghiệp vụ minh họa, không phải kiểu dữ liệu có sẵn trong Spring Integration. Tham chiếu reservation/shipment phải được lấy từ **response thật của hệ thống đích hoặc từ kho dữ liệu đáng tin**, không bịa từ input khi chưa biết request đã thành công.

### 5.3. Bảng lưu compensation command

Một tác vụ bù nên có:

- commandId duy nhất và sagaId;
- tên step cần bù, target resourceId, operation và nguyên nhân;
- idempotency key ổn định;
- trạng thái PENDING/RUNNING/SUCCEEDED/RETRY/FAILED;
- attempt, deadline, nextAttemptAt và lastError đã lọc;
- version để chống hai worker thực thi đồng thời;
- người chịu trách nhiệm và bằng chứng xác nhận.

**Durability:** nếu ghi trạng thái saga và tạo command bù trong database, nên thực hiện trong một transaction khi cùng DB. Nếu cần chuyển command sang broker, có thể dùng **transactional outbox** để tránh trường hợp DB đã ghi nhưng command chưa được publish, hoặc ngược lại.

### 5.4. Không cho trạng thái cũ ghi đè trạng thái mới

Một HTTP callback đến muộn có thể thông báo S2 thành công sau khi coordinator đã quyết định bù. Cần dùng **state/version/expected status check** để xác định callback là thông tin xác minh hoặc sự kiện không còn hợp lệ. Không để callback cũ tự chuyển COMPENSATED về RUNNING hay tái cấp quyền/tạo phiếu mà không có quyết định mới.

## 6. ErrorMessage, MessagingException và bối cảnh quyết định bù

### 6.1. ErrorMessage đến từ đâu?

Trong Spring Integration, khi một **error handler** của poller, executor, gateway hoặc một endpoint được thiết kế để publish lỗi, ngoại lệ có thể được chuyển thành **ErrorMessage** gửi tới **errorChannel toàn cục** hoặc kênh lỗi riêng.

- **ErrorMessage** là một Spring Message có payload là **Throwable**.
- **MessagingException** là một ngoại lệ có thể giữ **failedMessage** tại vị trí thất bại.
- **ErrorMessage.getOriginalMessage()** có thể giữ một Message đầu vào nếu thành phần tạo ErrorMessage cung cấp; giá trị có thể null.
- **MessageHeaders.ERROR_CHANNEL** là header dùng để chọn điểm nhận lỗi khi thành phần publisher hỗ trợ; chỉ gắn header không tự bắt exception.

Lưu ý: một handler xử lý **đồng bộ trên DirectChannel** thường ném exception về sender. Lỗi đó **không tự được publish** tới errorChannel chỉ vì bean errorChannel tồn tại. Các adapter dùng JMS/AMQP/Kafka listener cũng có error handler ở container riêng.

### 6.2. Luồng lỗi không phải nguồn sự thật duy nhất

ErrorMessage trả lời được **“có Throwable nào được phát đi?”**, nhưng không phải lúc nào trả lời được **“bước nghiệp vụ nào đã commit?”**. Ví dụ HTTP timeout ở S2: failedMessage có thể là CreateShipmentCommand, nhưng điều đó không cho biết server vận chuyển đã tạo shipment hay chưa. Coordinator phải truy vấn trạng thái thật qua idempotency key hoặc tài nguyên bên ngoài.

Nếu thiết kế xử lý bù chỉ đọc exception.getMessage() rồi gọi cancel, quyết định sẽ thiếu dữ liệu và dễ làm hỏng nghiệp vụ.

### 6.3. Phân biệt failedMessage và originalMessage

~~~text
HTTP order request       -> M0 (OrderRequest)
Transformer              -> M1 (ReserveInventoryCommand)
Inventory reservation    -> OK
Transformer              -> M2 (CreateShipmentCommand)
HTTP outbound gateway    -> timeout

ErrorMessage.payload: MessagingException
  failedMessage: có thể là M2
ErrorMessage.originalMessage: M0, M1, M2 hoặc null
  tùy endpoint/error strategy đã truyền context nào
~~~

Không nên ép mọi originalMessage thành OrderRequest, cũng không dựa duy nhất vào việc failedMessage có mặt. **sagaId và businessKey phải được duy trì có chủ đích** trong headers hoặc state store; khi hai reference đều null, sử dụng metadata của task/flow hoặc nguồn sự kiện đã lưu.

### 6.4. Code minh họa đọc lỗi để điều phối

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class OrderSagaErrorRouter {

    private final SagaFailureService failures;

    public OrderSagaErrorRouter(SagaFailureService failures) {
        this.failures = failures;
    }

    @ServiceActivator(inputChannel = "orderErrors")
    public void onError(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Message<?> failed = cause instanceof MessagingException me
                ? me.getFailedMessage()
                : null;
        Message<?> original = error.getOriginalMessage();

        Object id = failed != null
                ? failed.getHeaders().get("sagaId")
                : null;
        if (id == null && original != null) {
            id = original.getHeaders().get("sagaId");
        }

        if (!(id instanceof String sagaId) || sagaId.isBlank()) {
            // Không có đủ context: lưu cảnh báo an toàn, xử lý thủ công.
            failures.recordUncorrelatedFailure(cause);
            return;
        }

        // Ghi lỗi bền vững. KHÔNG tự gọi tất cả API hủy trong observer.
        failures.recordAndScheduleDecision(sagaId, cause);
    }
}

interface SagaFailureService {
    void recordAndScheduleDecision(String sagaId, Throwable cause);
    void recordUncorrelatedFailure(Throwable cause);
}
~~~

Đây là skeleton minh họa với Java hiện đại, giả định các phương thức của SagaFailureService được ứng dụng triển khai. Không có bean service, channel và tuyến publish lỗi thì đoạn code chưa tạo thành ứng dụng chạy độc lập.

**Điểm cần lưu ý:**

- Error handler phải ghi trạng thái bền vững hoặc chuyển sang recovery an toàn; **return không có nghĩa message nguồn được xử lý thành công**.
- Việc swallow hay throw exception ảnh hưởng các listener/poller/container khác nhau; phải thiết kế acknowledgment/transaction riêng.
- Không truyền Throwable nguyên vẹn vào database dưới dạng payload tùy ý. Chỉ lưu exception type, mô tả đã lọc, context và tham chiếu log/trace.
- Thao tác của listener **có thể được gọi lại**; phương thức recordAndScheduleDecision cần idempotent cho cùng saga và cùng failure.

### 6.5. Kênh toàn cục hay kênh riêng?

**errorChannel** mặc định thường là PublishSubscribeChannel có logging subscriber; không nên đặt mọi hành động có side effect vào subscriber toàn cục. Với quy trình đặt hàng, dùng một kênh riêng như **orderErrors** có chủ sở hữu và recovery policy rõ. Global errorChannel có thể ghi nhận/cảnh báo các lỗi không được định tuyến cụ thể.

Nếu có nhiều subscriber nhận cùng ErrorMessage, đừng để hai subscriber cùng tạo lệnh hủy shipment. **Một coordinator/recovery consumer duy nhất về mặt logic** nên sở hữu quyết định bù; các subscriber khác chỉ quan sát hoặc ghi metric.

## 7. Mô hình compensation command và thực thi

### 7.1. Mọi bước bù cần precondition

Không nên chỉ có hàm cancelShipment(String orderId). Cần kiểm tra:

1. Shipment đã được xác nhận tồn tại hoặc outcome unknown cần đối soát?
2. Shipment này có đúng thuộc saga và tenant không?
3. Đã gửi lệnh hủy trước đó chưa, có request ID trả về không?
4. Hủy có còn được phép theo trạng thái vận chuyển không?
5. Hủy thành công có nghĩa là phía đích đã nhận yêu cầu hay đã xác nhận hoàn tất?
6. Một callback đến trễ có thể thay đổi trạng thái sau khi lệnh hủy được gửi không?

### 7.2. Payload của compensation command

~~~json
{
  "commandId": "comp-saga-274-cancel-shipment",
  "sagaId": "saga-order-274",
  "operation": "CANCEL_SHIPMENT",
  "targetId": "shipment-S274",
  "expectedStep": "CREATE_DELIVERY",
  "idempotencyKey": "saga-order-274-CANCEL_SHIPMENT-v1",
  "attempt": 1,
  "status": "PENDING",
  "deadline": "2026-11-24T08:00:00Z"
}
~~~

Đây là dữ liệu nghiệp vụ minh họa, **không phải API mặc định** của Spring Integration. Nếu lệnh đi qua broker, phải bảo vệ quyền truy cập command channel; việc replay một command hủy không đúng đối tượng có thể gây tác động lớn.

### 7.3. Adapter riêng cho các lệnh bù

Có thể tạo một **IntegrationFlow** nhận các message chứa compensation command hoặc một service activator trên channel chuyên dụng:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

public record CompensationCommand(
        String commandId,
        String sagaId,
        String operation,
        String targetId,
        String idempotencyKey) {}

@Component
public class CompensationCommandHandler {

    private final CompensationCoordinator coordinator;

    public CompensationCommandHandler(CompensationCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @ServiceActivator(inputChannel = "compensationCommands")
    public void handle(CompensationCommand command) {
        coordinator.executeUsingPersistedState(command);
    }
}

interface CompensationCoordinator {
    void executeUsingPersistedState(CompensationCommand command);
}
~~~

Trong một dự án Java thực tế, record và các public top-level type thường đặt ở file riêng theo quy tắc Java. Đây là các đoạn minh họa đặt chung cho dễ đọc, **không phải một tệp Java hoàn chỉnh**. Spring context phải có channel và producer gửi CompensationCommand đúng kiểu tới channel đó. Tên compensationCommands chỉ là quy ước ứng dụng.

### 7.4. Phân công công việc: handler mỏng, coordinator dày

Handler chỉ chuyển command tới coordinator. Coordinator nên:

- Đọc saga state và command state từ kho bền vững;
- Thực hiện claim/lease hoặc optimistic lock tránh hai worker xử lý cùng command;
- Kiểm tra precondition, tenant, resource và business deadline;
- Gọi đúng adapter bù (HTTP cancel, DB release, event producer...);
- Ghi kết quả đã xác minh hoặc trạng thái retry/unknown;
- Điều phối bước bù tiếp theo theo dependency;
- Phát event/audit an toàn sau thay đổi state.

Việc cấu hình Spring Integration **không tự tạo khóa phân tán hoặc transaction state**. Các bảo đảm đồng thời phải do storage/coordination layer cung cấp.

## 8. Idempotency và xử lý trùng lặp

Một thông điệp có thể bị gửi lại do retry, broker redelivery, consumer restart hoặc timeout. Compensation command cũng có thể được thực hiện lại. **Không có idempotency, bù hai lần có thể nguy hiểm ngang với forward action hai lần**.

### 8.1. Ví dụ bù không idempotent

Giả sử S1 trừ 5 đơn vị hàng tồn và C1 lại cộng 5. Nếu C1 chạy hai lần sau retry, tồn kho tăng 10 — sai. Thiết kế tốt dùng reservation ID:

~~~text
releaseReservation(reservationId):
    row = loadReservationForUpdate(reservationId)
    if row.status == RELEASED:
        return ALREADY_APPLIED
    if row.status != RESERVED:
        return REQUIRES_RECONCILIATION
    releaseQuantityExactlyOnce(row)
    markReservationReleased(row)
    commit
~~~

Đoạn trên là **mã giả**, giả định cùng transaction bảo vệ inventory và reservation state. Nếu inventory nằm ở hệ thống ngoài, cần API có idempotency key hoặc cơ chế tra cứu trạng thái.

### 8.2. Idempotency key ổn định

Định nghĩa key dựa trên **sagaId + loại bù + target ID hoặc step ID**, không tạo UUID mới mỗi lần retry cho cùng ý định. Bên nhận phải hiểu key trong phạm vi nào, lưu bao lâu và xử lý khi một key được dùng với payload khác.

### 8.3. Mức bảo đảm thực tế

“Exactly once” xuyên HTTP, SFTP, database và broker không thể được suy ra từ một Spring MessageChannel. Có thể đạt **hiệu ứng đúng một lần ở mức nghiệp vụ** bằng durable state, idempotent commands, deduplication và đối soát; bản thân message vẫn có thể được giao lại nhiều lần.

### 8.4. Bảo vệ event đến sai thứ tự

Một compensation có thể đến trước xác nhận forward step hoặc một sự kiện success cũ có thể tới sau khi đã bù. Dùng version/expected-state check; nếu outcome không thể xác định, tạm dừng tự động và chuyển sang reconciliation thay vì đoán.

## 9. Timeout và trạng thái chưa biết: điểm khó nhất

### 9.1. Ba kết quả cần phân biệt

Với lệnh CreateShipment gửi HTTP:

| Kết quả tại caller | Kết quả thật ở đối tác | Hành động phù hợp |
|---|---|---|
| 2xx có resource ID | Đã tạo theo contract | Lưu resource ID và bước thành công |
| 4xx nghiệp vụ rõ ràng | Bị từ chối nếu contract xác nhận không tạo | Không bù một shipment không tồn tại |
| Timeout/connection reset sau khi gửi | Có thể đã tạo hoặc chưa | Query bằng idempotency key, đối soát trước khi retry/bù |
| 5xx sau khi xử lý một phần | Phụ thuộc contract API | Cần trạng thái truy vấn hoặc reconciliation |

Không suy rằng timeout nghĩa là thất bại chắc chắn ở phía đích. Đây là nguyên nhân phổ biến dẫn tới **double charge**, **duplicate shipment** và bù sai đối tượng.

### 9.2. Quy trình reconciliation

~~~mermaid
flowchart TD
    E["HTTP outbound timeout"] --> U["Mark step RESULT_UNKNOWN"]
    U --> Q["Lookup external status by stable request key"]
    Q --> D{"Kết quả?"}
    D -->|"Đã tạo"| S["Lưu target ID, xác nhận STEP_SUCCEEDED"]
    D -->|"Chưa tạo, có bằng chứng"| R["Retry trong budget hoặc quyết định hủy"]
    D -->|"Vẫn không rõ"| M["MANUAL_REVIEW hoặc retry tra cứu có hạn"]
    S --> C{"Saga tiếp tục hay phải bù?"}
    C -->|"Tiếp tục"| F["Next forward step"]
    C -->|"Hủy"| B["Compensation command có target ID thật"]
~~~

Nếu đối tác không có API tra cứu/idempotency, không được tự bịa kết quả. Có thể dùng cơ chế điều tra thủ công, đối soát dữ liệu giao dịch/báo cáo hoặc thiết kế protocol mới trước khi tự động hóa bù.

### 9.3. Thời gian chờ có thể làm bù không còn hợp lệ

Một booking đã được tạo nhưng khi lệnh hủy đến, đối tác đã giao hàng. Lúc này “cancel” có thể không còn được phép; chính sách phải chuyển sang return/refund hoặc xử lý khác, không retry API cancel vĩnh viễn.

## 10. File và SFTP: bù thao tác trên tệp

### 10.1. File inbound không giống giao dịch database

File inbound adapter đọc file từ thư mục. Poller có thể dùng bộ lọc để tránh đọc lại một tệp đã chấp nhận, chẳng hạn các biến thể AcceptOnceFileListFilter hoặc persistent filter. Khi parse/ghi DB thất bại, một ErrorMessage **không tự reset filter**, không tự đưa file về inbox và cũng không bảo đảm file chưa bị một consumer khác đọc.

Các trạng thái nên được quản lý rõ:

| Trạng thái file | Ý nghĩa | Hành động khi lỗi |
|---|---|---|
| DETECTED | Đã nhìn thấy file, chưa xác nhận xử lý | Chờ file ổn định, khóa nếu cần |
| CLAIMED | Worker nhận trách nhiệm xử lý | Tránh nhiều poller cùng nhận |
| PARSED | Đã đọc/validate và xác lập business key | Giữ context để replay |
| IMPORTED | DB đã commit dữ liệu | Không nhập lại mù; kiểm tra idempotency |
| QUARANTINED | Dữ liệu lỗi được cách ly | Ghi nguyên nhân, owner, retention |
| ARCHIVED | Đã hoàn tất và lưu bản theo chính sách | Không tự tạo thêm một import |

Nếu file sai schema ngay từ đầu, **quarantine** thường thích hợp hơn compensation, vì chưa có tác động nghiệp vụ. Nếu một nửa file đã được ghi thành công, nên dùng transaction cho phạm vi ghi phù hợp hoặc **bù theo từng record/đợt** đã xác nhận, thay vì xóa toàn bộ file mà không biết dữ liệu nào đã lưu.

### 10.2. SFTP outbound và file đã được đối tác xử lý

Một outbound SFTP adapter có thể upload file rồi đổi tên sang vị trí “ready”. Khi message đã được công bố theo quy ước đối tác, **xóa remote file không có nghĩa đối tác chưa xử lý dữ liệu**. Compensation tùy contract:

- Nếu file còn ở staging và chưa được consumer đọc: có thể xóa file tạm/rename theo policy.
- Nếu đã publish: gửi **cancel/correction file** với transaction ID liên quan.
- Nếu không biết phía đối tác đã đọc chưa: đối soát với hệ thống bên kia trước khi bù.
- Nếu upload lỗi giữa chừng: xác minh remote checksum/size và trạng thái file tạm; tránh để partial file được nhận.

### 10.3. Error flow cho lỗi parse và lỗi remote session khác nhau

Lỗi SFTP authentication/timeout có thể phát sinh **trước khi có Spring Message**, nên failedMessage có thể null. Lỗi parse xảy ra sau khi file được đưa vào flow có thể có failedMessage với File hoặc payload đã chuyển đổi. Cần bổ sung flow ID, remote file reference, stage và correlation tại nguồn đáng tin cậy.

**Không gửi file bytes chứa dữ liệu nhạy cảm vào errorChannel để “đề phòng”**; dùng reference tới nơi lưu bền vững được kiểm soát.

## 11. HTTP gateway: cancel, refund và idempotent command

### 11.1. Request/response đồng bộ

HTTP inbound gateway thường có caller đang chờ response. Nếu bước xử lý lỗi, cần trả **HTTP status và error body** theo hợp đồng, không chỉ publish ErrorMessage ở nền. Ví dụ một lỗi validation chưa có side effect có thể trả 400; một failure tạm thời chưa biết trạng thái có thể cần mã/response biểu thị “đang xử lý” hoặc yêu cầu tra cứu trạng thái, tùy API contract.

Với quy trình dài, HTTP inbound có thể nhận request, ghi saga state và trả **202 Accepted cùng operationId** nếu API được thiết kế bất đồng bộ. Lỗi phát sinh về sau không thể trả lại trực tiếp trên HTTP request đã kết thúc; caller cần endpoint truy vấn, callback hoặc event kết quả.

### 11.2. HTTP outbound với thao tác không đảo hoàn toàn

| Forward action | Hành động bù nghiệp vụ | Đặc điểm |
|---|---|---|
| Create booking | Cancel booking | Chỉ còn hiệu lực trước thời điểm dịch vụ được thực hiện |
| Reserve stock | Release reservation | Cần reservationId và chống release trùng |
| Capture payment | Refund | Tạo giao dịch mới, có phí/thời gian và quy tắc tài chính |
| Issue invoice | Void/correcting invoice | Tuân thủ nghiệp vụ kế toán, không đơn giản DELETE |
| Create user | Deactivate/revoke grants | Phải xử lý phiên, token, quyền downstream |
| Send notification | Send correction notification | Không thể đảm bảo người nhận chưa thấy thông báo ban đầu |

**Refund không phải rollback database** và có thể cần phê duyệt kiểm soát, xác minh customer/payment reference hoặc hạn mức.

### 11.3. Đối tác cần contract idempotency

Nếu API ngoài hỗ trợ **Idempotency-Key** (theo quy ước của họ), client cần dùng **cùng key cho các lần retry của một ý định forward**. Hành động bù phải có **một key riêng ổn định cho ý định cancel/refund**, không dùng lại key tạo booking khi semantics khác.

Ví dụ cấu trúc yêu cầu bù minh họa:

~~~http
POST /api/shipments/shipment-S274/cancel HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: saga-order-274-cancel-shipment
Content-Type: application/json

{"reason":"ORDER_CANCELLED","sagaId":"saga-order-274"}
~~~

Endpoint và header chỉ là **hợp đồng giả định để minh họa**, không phải mọi HTTP service đều hỗ trợ endpoint cancel hay header idempotency. Token và credential thật không được ghi vào log hoặc ErrorMessage.

### 11.4. Phân biệt gửi lệnh bù với bù đã hoàn tất

HTTP 202 từ API cancel có thể chỉ nghĩa là **đã nhận yêu cầu hủy**, chưa chắc shipment đã bị hủy. State coordinator nên là COMPENSATION_PENDING_CONFIRMATION, tiếp tục poll/webhook theo contract cho tới trạng thái cuối. Chỉ đánh dấu COMPENSATED khi có căn cứ xác nhận thực tế.

## 12. JMS và AMQP: ack không xóa tác động nghiệp vụ

### 12.1. JMS inbound container

Với JMS inbound listener, transaction/acknowledgment mode quyết định source message được ack, rollback hay redelivery. Một service activator có thể ném exception, nhưng nếu error handler **bắt, ghi log rồi return bình thường**, container có thể nhìn thấy thành công và acknowledge theo cấu hình.

Quyết định chính:

- Nếu nghiệp vụ **chưa tạo tác động** và cần broker redeliver, cấu hình propagate/rollback đúng.
- Nếu đã **lưu saga state + compensation/retry command bền vững**, có thể có chính sách ack nguồn sau khi lưu an toàn, tránh redelivery vô hạn.
- Nếu đã tạo side effect ngoài broker, redelivery **không tự bù** side effect đó.
- Nếu message poison, cần retry limit và DLQ/quarantine thay vì lặp mãi.

**ErrorMessage được publish thành công không chứng minh JMS transaction rollback hoặc source message được giữ lại.**

### 12.2. AMQP/RabbitMQ

RabbitMQ có cơ chế ack, reject, nack, requeue và dead-letter exchange (DLX)/dead-letter queue (DLQ) theo cấu hình. Các thao tác này quản lý **delivery của message nguồn**, không tự hủy booking hoặc release inventory đã commit.

| Trạng thái flow | Lựa chọn cần thiết kế | Tại sao |
|---|---|---|
| Handler lỗi trước mọi side effect | Retry/requeue có giới hạn | Có thể xử lý lại message |
| Handler đã ghi DB nhưng trước ack | Dedupe/idempotent write khi redelivery | Tránh ghi trùng |
| Error event đã lưu trong durable recovery | Ack nguồn theo chính sách nếu commit đã chắc chắn | Tránh hai hệ thống cùng retry không phối hợp |
| Compensation failure | Lưu compensation command, retry riêng | Không nên requeue toàn bộ forward message một cách mù quáng |
| Message luôn sai schema | DLQ/quarantine | Giảm poison-message loop |

### 12.3. Tránh vòng lặp retry kép

Nếu application advice retry 3 lần và broker redelivery 5 lần, side effect có thể bị thực hiện nhiều lần nếu không chống trùng. Với compensation, nếu broker cũng redeliver lệnh cancel, idempotency phải bảo vệ cả **forward commands** và **compensation commands**.

### 12.4. Không đồng nhất DLQ với kho xử lý bù

DLQ thường dùng để cách ly message không xử lý được. Một saga đang ở trạng thái COMPENSATION_REQUIRED cần **state và kế hoạch xử lý bù**, không chỉ một bản sao message trong DLQ. Có thể đưa task vào queue để worker thực thi, nhưng vẫn cần xác định resource đã thay đổi, thứ tự và trạng thái bù.

## 13. Kafka: phát sự kiện bù thay vì “thu hồi” record

### 13.1. Kafka đã publish rồi thì sao?

Khi một Kafka record đã xuất hiện trên topic và consumer khác đã xử lý, không thể dựa vào việc xóa một ErrorMessage để “undo” mọi tác động. Thường dùng **một sự kiện mới** mô tả thay đổi nghiệp vụ:

~~~json
{
  "eventType": "OrderCancelled",
  "eventId": "event-order-274-cancel-v1",
  "sagaId": "saga-order-274",
  "orderId": "order-274",
  "reasonCode": "FULFILLMENT_FAILED",
  "previousEventReference": "event-order-274-created"
}
~~~

Consumer xử lý OrderCancelled theo contract và có thể tạo các hành động riêng để hoàn trả trạng thái. Không thể bảo đảm mọi consumer đã phản hồi trong cùng thời điểm chỉ từ việc producer nhận acknowledgment.

### 13.2. Kafka transaction có phạm vi

Kafka có cơ chế transaction đối với các thao tác producer và, trong những mô hình phù hợp, các offset của consumer. Nhưng điều này **không tự bao trùm JDBC database và HTTP API ngoài**. Nếu muốn giữ tính nhất quán giữa DB update và publish Kafka event, có thể dùng **transactional outbox** trong DB và worker phát sự kiện, với idempotency tại consumer.

### 13.3. Offset và error handler của container

Trong flow Kafka inbound, **Spring for Apache Kafka** có các cơ chế listener/container error handling (ví dụ CommonErrorHandler và DefaultErrorHandler theo phiên bản). Một ErrorMessage ở Spring Integration không tự điều khiển offset commit hay DLT. Khi handler dùng compensation:

1. Xác định lỗi có được container coi là thành công/được xử lý không;
2. Ghi saga state và command bù bền vững trước khi commit theo contract;
3. Dedupe record phát lại theo event ID và business key;
4. Không publish OrderCancelled hai lần gây bù kép không idempotent;
5. Kiểm thử restart, rebalance và callback tới muộn.

### 13.4. DLT khác compensation event

**Dead-letter topic (DLT)** chứa record không thể xử lý theo một chính sách. **Compensation event** là hành động nghiệp vụ có chủ đích (ví dụ hủy đơn). Một record ở DLT có thể cần manual review; nó không tự phát sự kiện OrderCancelled.

## 14. JDBC: state store, transaction và outbox

### 14.1. Lưu saga state phải atomic trong phạm vi có thể

Nếu một transaction cục bộ ghi:

- trạng thái saga COMPENSATION_REQUIRED;
- hai compensation commands PENDING;
- một outbox event để worker nhận;

thì nên commit chúng **cùng nhau trong một database transaction** nếu cùng DB, bảo đảm không có trạng thái “đã quyết định bù nhưng không lưu command”. Tuy nhiên HTTP cancel vẫn là thao tác ngoài transaction đó; worker phải gọi sau và ghi kết quả độc lập.

### 14.2. State transition theo version

Ví dụ câu lệnh minh họa:

~~~sql
UPDATE saga_instance
SET state = 'COMPENSATING',
    version = version + 1
WHERE saga_id = :sagaId
  AND state = 'COMPENSATION_REQUIRED'
  AND version = :expectedVersion;
~~~

Chỉ xem transition thành công khi số row được cập nhật đúng kỳ vọng. Đây là mẫu **optimistic concurrency**, không giải quyết toàn bộ vấn đề lease, liveness hay transaction isolation nếu hệ thống có nhiều worker.

### 14.3. Outbox là cầu nối, không phải phép màu exactly-once

Một outbox worker đọc command đã commit, gửi tới broker/HTTP, rồi đánh dấu đã phát. Nếu worker crash sau khi gửi nhưng trước khi ghi trạng thái, command có thể được gửi lại. Vì vậy **receiver idempotency** và **dedupe** vẫn cần thiết; outbox giải quyết một lớp mất message, không loại bỏ mọi duplicate.

### 14.4. JDBC polling adapter

Một JDBC inbound poller có thể lấy các record PENDING từ DB; cần bảo vệ claim/lock, timeout và retry state. Nếu poller đọc lệnh bù nhưng đánh dấu DONE trước khi phía đích xác nhận, dữ liệu dễ bị mất. Nên dùng trạng thái CLAIMED/RUNNING/RETRY và xác minh outcome trước khi SUCCEEDED.

### 14.5. Bù với các bước DB đã commit

Nếu đã tạo reservation và commit, giải phóng reservation là **một transaction mới**. Không xóa row reservation chỉ để mô phỏng chưa từng tồn tại: audit thường cần ghi nhận lúc giữ, lúc release và nguyên nhân. Khi transaction bù bị lỗi deadlock, có thể retry có giới hạn nếu logic idempotent.

## 15. Compensation failure: khi chính hành động bù thất bại

### 15.1. Không giả định bù luôn thành công

Một lệnh cancel shipment có thể gặp HTTP 503. Một lệnh release inventory có thể gặp database deadlock. Một giao dịch refund có thể bị từ chối do trạng thái thanh toán. Khi bù thất bại, cần **một vòng đời xử lý lỗi riêng**, không chỉ ném lại ErrorMessage và mong toàn bộ saga tự trở về trạng thái ban đầu.

### 15.2. State machine của từng command bù

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING: Worker claim
    RUNNING --> SUCCEEDED: Đã xác minh bù
    RUNNING --> RETRY: Lỗi transient
    RETRY --> RUNNING: Đến hạn và còn budget
    RUNNING --> RESULT_UNKNOWN: Timeout / chưa rõ kết quả
    RESULT_UNKNOWN --> RUNNING: Đối soát cho thấy chưa áp dụng
    RESULT_UNKNOWN --> SUCCEEDED: Đối soát xác nhận đã áp dụng
    RUNNING --> MANUAL_REVIEW: Không còn bù tự động an toàn
    RETRY --> MANUAL_REVIEW: Hết retry / deadline
    SUCCEEDED --> [*]
~~~

### 15.3. Chính sách khi bù lỗi

| Tình huống | Hướng xử lý |
|---|---|
| HTTP 503 từ endpoint cancel | Retry backoff có giới hạn, dùng cùng idempotency key |
| Timeout không rõ cancel đã thành công chưa | Query status, giữ RESULT_UNKNOWN |
| API thông báo shipment đã giao | Không retry cancel vô hạn; mở luồng return/refund/manual |
| DB release deadlock | Retry transaction mới có concurrency guard |
| Refund bị từ chối nghiệp vụ | Escalate tài chính/ops, không đổi thành COMPENSATED |
| Worker crash khi command RUNNING | Dùng lease expiry và idempotency để claim lại |
| Hết deadline đã cam kết | Alert owner, ghi external risk và compensating control |

### 15.4. Chỉ đánh dấu COMPENSATED khi có đủ bằng chứng

Một saga không được ghi COMPENSATED chỉ vì tất cả lệnh bù đã được **enqueue**, **publish** hoặc nhận HTTP 202. Cần bằng chứng xác nhận theo contract từng step; nếu một bước không thể bù, saga có thể kết thúc ở trạng thái MANUAL_REVIEW/FAILED_TERMINAL cùng hồ sơ nghiệp vụ.

### 15.5. Compensation của compensation?

Không nên mặc định tạo lệnh đảo hành động bù khi bù lỗi, vì có thể thành chuỗi luân phiên vô hạn. Nếu một khoản đã refund sai, sửa chữa có thể cần một giao dịch mới với approval riêng, không phải “tự charge lại” khách hàng. Chính sách tài chính và pháp lý phải được phân quyền rõ.

## 16. Case study: xử lý lỗi và bù trong quy trình giao hàng B2B

### 16.1. Bối cảnh nghiệp vụ

Doanh nghiệp A tiếp nhận đơn hàng từ đối tác B qua SFTP. File CSV chứa nhiều đơn với business key duy nhất trong phạm vi đối tác. Spring Integration đọc file, chuyển thành OrderCommand, lưu trạng thái, giữ hàng trong database, gọi HTTP của đơn vị vận chuyển C để tạo shipment và phát sự kiện OrderAccepted qua Kafka. Một dịch vụ khác có thể nhận OrderAccepted để tạo hóa đơn.

Yêu cầu:

1. Không tạo trùng đơn khi SFTP poller đọc lại file.
2. Nếu đơn không hợp lệ, cách ly record mà không tạo shipment.
3. Nếu shipment được tạo nhưng quy trình bị hủy, gửi lệnh cancel shipment trước khi release inventory theo policy.
4. Nếu publish Kafka bị lỗi tạm thời, **không lập tức hủy toàn bộ booking** nếu outbox có thể retry mà nghiệp vụ vẫn muốn tiếp tục.
5. Nếu kết quả HTTP CreateShipment không rõ, tra cứu trạng thái trước khi tạo lại hoặc bù.
6. Nếu compensation thất bại, phải có trạng thái rõ và người chịu trách nhiệm.

### 16.2. Thiết kế dữ liệu theo từng bước

| Bước | Forward action | Bằng chứng thành công | Compensation nếu cần |
|---|---|---|---|
| S0 | Nhận và validate file | file hash, batchId, orderId | Quarantine khi lỗi dữ liệu; chưa có side effect |
| S1 | Tạo đơn và giữ hàng tại DB | orderId, reservationId, commit | Release reservation/mark order cancelled |
| S2 | POST CreateShipment tới C | shipmentId hoặc status lookup xác nhận | CancelShipment theo contract C |
| S3 | Ghi outbox OrderAccepted | outbox event ID đã commit | Không xóa event đã phát; có thể phát OrderCancelled |
| S4 | Kafka publisher gửi event | broker acknowledgment và trạng thái outbox | Event bù/correction tùy consumer contract |

Một số ứng dụng có thể viết S1 và S3 trong cùng local DB transaction để bảo đảm ý định phát event được lưu cùng trạng thái đơn. HTTP S2 vẫn là ranh giới ngoài; phải quản lý riêng.

### 16.3. Kịch bản A — Lỗi validation khi chưa có side effect

File có mã sản phẩm không tồn tại. Transformer/validator ném exception trước khi tạo reservation. Error flow nên:

1. Tìm file/batch/record từ context;
2. Phân loại INVALID_INPUT;
3. Ghi trạng thái REJECTED và quarantine record/file theo quy tắc lô;
4. Trả thông tin lỗi cho B bằng kênh phù hợp;
5. Không tạo compensation command release/cancel vì **chưa có bước thành công để bù**.

Nếu một file chứa nhiều đơn và một đơn lỗi, contract phải xác định **all-or-nothing cho cả file** hay **partial acceptance theo từng order**. Compensation phải theo đơn vị nghiệp vụ đã cam kết, không tự xóa mọi đơn trong batch khi chỉ một dòng lỗi.

### 16.4. Kịch bản B — HTTP CreateShipment timeout

S1 đã giữ hàng. S2 gửi CreateShipment rồi timeout; có thể phía vận chuyển C đã tạo shipment. Error handler:

1. Ghi saga state RESULT_UNKNOWN ở S2;
2. Không gửi CreateShipment lặp với key mới;
3. Tra cứu C bằng request ID/idempotency key ổn định;
4. Nếu C xác nhận shipment đã tạo, lưu shipmentId và quyết định tiếp tục forward hoặc hủy;
5. Nếu C xác nhận chưa tạo, retry có giới hạn hoặc bù S1 theo policy;
6. Nếu C không thể trả lời, mở MANUAL_REVIEW, tránh vừa tạo trùng vừa cancel sai.

**Điểm kiểm tra:** kết quả của API tra cứu phải đủ tin cậy. Không dựa vào việc “không thấy trong cache” để khẳng định chưa tạo.

### 16.5. Kịch bản C — Shipment đã tạo nhưng nghiệp vụ hủy

S1 và S2 đều SUCCEEDED. Đơn bị hủy do đối tác B xác nhận không thể hoàn tất giao hàng. Coordinator tạo hai compensation commands:

~~~text
1. CANCEL_SHIPMENT(shipment-S274)
2. RELEASE_RESERVATION(reservation-R274)
~~~

Tùy quan hệ phụ thuộc, cần xác minh CANCEL_SHIPMENT trước khi release reservation để không giao thiếu hàng. Sau khi hai bước bù thành công, cập nhật trạng thái đơn CANCELLED và saga COMPENSATED. Nếu C báo đã giao hàng, chuyển sang quy trình return/refund có owner thay vì giả định cancel thành công.

### 16.6. Kịch bản D — Kafka tạm lỗi sau khi các bước trước thành công

Đơn đã tạo, shipment đã xác nhận và outbox OrderAccepted đang chờ gửi. Kafka producer timeout. Nếu business goal là **hoàn tất đơn và công bố event**, nên:

- Giữ saga ở trạng thái chờ publish hoặc hoàn tất nghiệp vụ với event pending theo contract;
- Cho outbox publisher retry idempotent;
- Ghi delay, retry budget, alert và consumer lag;
- Không tự hủy shipment chỉ vì Kafka lỗi vài phút nếu event có thể phát lại an toàn.

Nếu đã vượt thời hạn business và quyết định bắt buộc hủy đơn, mới kích hoạt compensation với nguyên nhân rõ. **Lỗi kỹ thuật ở bước cuối không mặc nhiên là yêu cầu hủy nghiệp vụ**.

### 16.7. Kịch bản E — CancelShipment thành công nhưng response mất

Lệnh bù gọi HTTP cancel và timeout sau khi C đã hủy thành công. Nếu worker gửi lặp với key khác, C có thể trả conflict hoặc tạo phí hủy lặp. Cần đánh dấu RESULT_UNKNOWN, tra trạng thái theo shipmentId/cancel key, xác nhận đã hủy rồi mới đánh dấu command SUCCEEDED.

### 16.8. Sơ đồ trình tự

~~~mermaid
sequenceDiagram
    participant S as SFTP poller
    participant I as Spring Integration flow
    participant DB as Saga state + Inventory DB
    participant P as Delivery API
    participant E as Error flow
    participant W as Compensation worker
    S->>I: File CSV / order-274
    I->>DB: Reserve inventory, record S1_SUCCEEDED
    DB-->>I: reservation-R274
    I->>P: CreateShipment with idempotency key
    P-->>I: shipment-S274
    I->>DB: Record S2_SUCCEEDED
    Note over I: Business cancellation arrives
    I->>DB: Persist COMPENSATION_REQUIRED and commands
    DB-->>E: Recovery work becomes available
    E->>W: CancelShipment command
    W->>P: Cancel shipment-S274
    P-->>W: Cancel confirmed
    W->>DB: Mark C2_SUCCEEDED
    E->>W: ReleaseReservation command
    W->>DB: Release reservation-R274 idempotently
    DB-->>W: Release confirmed
    W->>DB: Saga COMPENSATED + audit
~~~

Sơ đồ thể hiện đường **hủy do nghiệp vụ**; nếu lỗi phát sinh từ handler và có error publisher, ErrorMessage có thể kích hoạt việc ghi failure và quyết định bù. Quy trình saga **không cần bắt buộc mọi lệnh hủy phải bắt đầu từ ErrorMessage** — business cancellation cũng là một trigger chính đáng.

### 16.9. Bằng chứng hoàn tất

Một đơn được ghi COMPENSATED khi:

- Có business/saga ID và các bước forward đã xác nhận;
- Các compensation commands cần thiết đã được xử lý đúng đối tượng;
- C đã xác nhận shipment không còn hiệu lực hoặc có trạng thái bù thay thế hợp lệ;
- Inventory không còn reservation active sai;
- Audit thể hiện nguyên nhân hủy, người/cơ chế quyết định và các kết quả;
- Không còn task bù FAILED hoặc RESULT_UNKNOWN chưa xử lý.

## 17. Kiểm thử error flow và xử lý bù

### 17.1. Test mô hình và định tuyến lỗi

**Unit test** nên xác minh:

- Error handler nhận ErrorMessage, đọc Throwable và failedMessage nếu có;
- Khi failedMessage null, originalMessage vẫn có thể dùng để lấy sagaId;
- Khi cả hai thiếu sagaId, handler ghi lỗi không có correlation vào đường vận hành, **không chọn ngẫu nhiên một saga để hủy**;
- Lỗi trùng cùng sagaId không tạo nhiều compensation commands;
- Phân loại retry/compensate/manual dựa trên saga state, không dựa duy nhất exception class.

### 17.2. Test service activator nhận ErrorMessage

Ví dụ JUnit ở mức gọi phương thức, sử dụng service giả do test cung cấp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class SagaErrorRouterTest {

    @Test
    void capturesSagaIdFromFailedMessage() {
        AtomicReference<String> observedId = new AtomicReference<>();

        SagaFailureService fakeService = new SagaFailureService() {
            @Override
            public void recordAndScheduleDecision(
                    String sagaId, Throwable cause) {
                observedId.set(sagaId);
            }

            @Override
            public void recordUncorrelatedFailure(Throwable cause) {
                throw new AssertionError("Unexpected uncorrelated failure");
            }
        };

        Message<String> failed = MessageBuilder
                .withPayload("create-shipment")
                .setHeader("sagaId", "saga-order-274")
                .build();

        ErrorMessage error = new ErrorMessage(
                new MessageHandlingException(failed, "HTTP timeout"));

        new OrderSagaErrorRouter(fakeService).onError(error);

        assertEquals("saga-order-274", observedId.get());
    }
}
~~~

Ví dụ giả định các type OrderSagaErrorRouter và SagaFailureService đã được tách vào source file thích hợp như phần 6; đây là **unit test cho logic trích sagaId**, chưa kiểm chứng integration flow thật đã publish ErrorMessage. Trong production phải có test về durable write/idempotency.

### 17.3. Ma trận fault injection

| Điểm lỗi | Giả lập | Kỳ vọng |
|---|---|---|
| Parse trước S1 | CSV sai schema | Quarantine, không tạo bù |
| DB S1 trước commit | Deadlock/rollback | Không có reservation active; retry an toàn |
| DB S1 sau commit nhưng trước reply | Crash | Đối soát bằng reservationId/business key |
| HTTP S2 trước gửi | Connection failure xác định | Retry hoặc bù S1 theo policy |
| HTTP S2 sau gửi | Timeout chưa rõ outcome | RESULT_UNKNOWN; query C trước khi quyết định |
| Kafka S3/S4 | Broker unavailable | Outbox retry, không hủy tự động không cần thiết |
| CancelShipment | 503 | Retry cùng key, backoff, không release sai |
| CancelShipment | 202 Accepted | Chờ xác nhận, chưa đánh dấu SUCCEEDED |
| ReleaseInventory | Duplicate command | Idempotent no-op, không cộng tồn kho lần hai |
| Worker | Crash sau API cancel trước DB update | Claim lại, tra trạng thái, chống hủy trùng |
| Error channel | Không subscriber/handler lỗi | Bảo toàn failure trong kho bền vững hoặc báo blocker |
| Multi-worker | Hai worker claim cùng command | Chỉ một xử lý state transition hợp lệ |

### 17.4. Kiểm thử semantics của adapter

Một test chỉ assert ErrorMessage được nhận **chưa đủ**. Phải kiểm tra trạng thái File filter/SFTP remote file, HTTP side effect, JMS/AMQP ack/redelivery, Kafka offset/outbox và DB commit. Với adapter liên quan broker, sử dụng môi trường integration test phù hợp để xác minh behavior của container/transaction thật.

### 17.5. Test theo trạng thái đích

Các assert nên là kết quả nghiệp vụ:

- Không tạo trùng shipment khi retry cùng request;
- Không release inventory quá một lần;
- Không ghi COMPENSATED trước xác nhận từ C;
- Sau restart, các command PENDING/RETRY vẫn được xử lý;
- Không để các callback cũ hồi sinh bước đã được bù;
- Không phát hai event OrderCancelled có tác động trùng tại consumer;
- Các đơn không liên quan vẫn được xử lý bình thường.

## 18. Observability, audit và cảnh báo

### 18.1. Theo dõi hai luồng riêng

**Forward flow:** tỷ lệ đơn thành công, latency, retry, pending outbox, lỗi inbound/outbound.

**Compensation flow:** số saga COMPENSATION_REQUIRED, số command PENDING/RETRY/RESULT_UNKNOWN, độ trễ bù, thất bại vượt deadline và số trường hợp cần can thiệp.

Không gộp “một đơn gặp lỗi rồi đã bù thành công” vào nhóm “đơn hoàn tất thành công”: chúng là hai outcome nghiệp vụ khác nhau.

### 18.2. Metrics tham khảo

| Metric | Giá trị quan sát |
|---|---|
| saga_forward_completed_total | Số saga hoàn tất forward |
| saga_compensation_required_total | Số saga cần bù |
| saga_compensated_total | Số saga bù đã xác minh |
| saga_compensation_failed_total | Số trường hợp bù chưa thành công |
| compensation_command_retries_total | Chi phí retry trên từng loại bước |
| compensation_pending_age | Tuổi command đang pending |
| saga_result_unknown_count | Số thao tác ngoài chưa rõ outcome |
| saga_manual_review_count | Số trường hợp cần người xử lý |
| outbox_pending_count | Backlog event/command chưa phát |
| error_handler_failure_total | Lỗi ngay trong error handler |

Không dùng sagaId, orderId hoặc customerId làm **label có cardinality cao** trong metrics. Dùng trace/log để tìm từng case.

### 18.3. Log an toàn và correlation

Một log compensation nên có:

~~~text
flow=delivery-compensation
sagaId=saga-order-274
commandId=comp-saga-274-cancel-shipment
step=CANCEL_SHIPMENT
attempt=2
outcome=RETRY_SCHEDULED
errorCategory=TRANSIENT
correlationId=import-batch-012
~~~

Tránh log access token, API key, thông tin thanh toán, nội dung file cá nhân hoặc response payload chứa dữ liệu nhạy cảm. Giữ correlation xuyên inbound adapter, error flow, command worker và outbound gateway bằng headers/context được truyền có chủ đích.

### 18.4. Alert theo tác động

Cảnh báo đáng ưu tiên:

- Saga RESULT_UNKNOWN vượt thời gian được phép;
- Lệnh bù đã hết retry hoặc sát deadline;
- Có tiền đã capture nhưng refund chưa xử lý;
- Shipment đã được tạo nhưng booking chưa được quản lý nhất quán;
- Compensation queue không tiến triển dù không có exception;
- Mất kết nối recovery store/outbox hoặc error handler liên tục lỗi.

**Không có ErrorMessage mới không chứng minh recovery khỏe mạnh**: worker có thể dừng poll hoặc queue bị nghẽn. Cần last-successful-processing, backlog và health indicator.

### 18.5. Audit phải giải trình quyết định bù

Lưu trạng thái trước/sau, nguồn trigger, người hoặc policy quyết định, target IDs, commands, kết quả xác minh, lần retry, exception đã lọc và ngoại lệ thủ công. Có thể cần lưu chứng cứ tài chính/hợp đồng theo chính sách retention; không xóa transaction lịch sử chỉ vì đã bù.

## 19. Bảo mật và giới hạn trách nhiệm của compensation flow

### 19.1. Lệnh bù thường có đặc quyền

CancelShipment, RefundPayment, ReleaseReservation, RevokeCredential hoặc DeleteRemoteFile đều là **hành động thay đổi trạng thái**. Một error flow có thể nhận nhiều thông tin từ hệ thống ngoài; không được để dữ liệu lỗi do đối tác gửi tự quyết định **resource ID, tenant, số tiền hoặc quyền của command bù**.

Trước khi thực hiện:

1. Xác thực producer hoặc nguồn sự kiện lỗi;
2. Tìm saga trong trusted state store bằng ID đã kiểm tra;
3. Xác minh tenant, contract, resource owner và business transaction;
4. Lấy target ID và số tiền/số lượng từ bước đã được lưu, không lấy mù từ ErrorMessage payload;
5. Kiểm tra actor/service principal có đúng scope của adapter bù;
6. Ghi audit cho hành động và quyết định.

### 19.2. Ngăn confused deputy

Giả sử một HTTP client bên ngoài có thể gửi header sagaId và errorChannel tự do. Nếu hệ thống không xác minh mapping, client có thể làm error router kích hoạt hủy booking của tenant khác. Cần tách **user-supplied correlation** khỏi **trusted saga identity**, xác thực/mapping tại entry point và giới hạn error-channel routing.

### 19.3. Tách credential forward và compensation khi cần

Một API bù như refund có thể có quyền khác API charge. Không nên cấp credential hoàn tiền toàn cục cho mọi integration flow. Sử dụng service principal, OAuth scope và permission tối thiểu, áp dụng approver/limit với bù nhạy cảm và lưu credential trong secret manager.

### 19.4. Quyền vận hành thủ công

Manual recovery cần bảo vệ khỏi việc operator bấm retry/refund vô hạn. Có thể yêu cầu:

- Role phù hợp và xác thực nâng mức khi cần;
- Hiển thị saga state và side effects trước khi thao tác;
- Preview/dry-run kế hoạch thay đổi nếu hệ thống hỗ trợ;
- Giới hạn số tiền, thời hạn và thao tác rủi ro cao;
- Idempotency key không đổi cho cùng ý định;
- Phê duyệt hai người với tác vụ bù tài chính quan trọng;
- Audit và hậu kiểm.

### 19.5. Dữ liệu lưu trong ErrorMessage và kho bù

failedMessage/originalMessage có thể chứa dữ liệu khách hàng, token, khóa, nội dung file hoặc bản ghi thanh toán. ErrorMessage trong một channel nội bộ **không tự là nơi lưu dữ liệu an toàn**. Khi cần durable recovery, lưu tham chiếu và payload tối thiểu, mã hóa dữ liệu nhạy cảm, phân quyền đọc, thiết lập retention và không serialize tùy ý toàn bộ Throwable.

## 20. Runbook vận hành: từ ErrorMessage tới COMPENSATED

### Bước A — Định vị thất bại

1. Xác định adapter (File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC), flow và stage;
2. Kiểm tra exception ném trực tiếp hay đã được publish thành ErrorMessage;
3. Truy vết sagaId, businessKey, correlation ID qua failedMessage/originalMessage hoặc state store;
4. Không đọc hoặc xuất payload nhạy cảm ngoài phạm vi được phép;
5. Xác định có task/container/broker error handler nào đã retry trước đó không.

**Tiêu chí đầu ra:** biết xử lý dừng ở bước nào và nguồn dữ liệu nào cần tra cứu.

### Bước B — Kiểm tra forward side effects

1. S1 đã commit reservation chưa? Có reservationId thật không?
2. S2 đã tạo shipment chưa? Truy vấn C nếu outcome unknown.
3. S3 đã ghi outbox chưa? Có event đã publish hoặc đang chờ không?
4. Input SFTP/file đã được move, delete hoặc filter đánh dấu chưa?
5. Broker đã ack/commit offset hay có redelivery không?
6. Có callback đến muộn, worker khác hoặc lần retry đang xử lý cùng saga không?

**Tiêu chí đầu ra:** state bền vững cho biết những bước nào đã xác nhận thành công, bước nào unknown.

### Bước C — Chọn quyết định

| Tình huống | Hành động |
|---|---|
| Lỗi parse trước side effect | Quarantine, không bù |
| Transient và forward vẫn có thể hoàn tất | Retry có giới hạn, idempotent |
| HTTP timeout outcome unknown | Reconciliation trước retry/bù |
| Business cancellation sau nhiều bước thành công | Lập compensation commands phù hợp |
| Tác động không đảo được | Tác vụ điều chỉnh/hậu kiểm/manual |
| Không thể xác định trạng thái nguồn | Giữ MANUAL_REVIEW, không đoán |

**Tiêu chí đầu ra:** có quyết định dựa trên nghiệp vụ và state, không chỉ exception type.

### Bước D — Ghi và chạy lệnh bù

1. Persist trạng thái COMPENSATION_REQUIRED, commands và outbox trong phạm vi transaction phù hợp.
2. Worker claim command bằng lease/version hoặc cơ chế concurrency tương đương.
3. Kiểm tra quyền, precondition và idempotency key trước khi gửi outbound.
4. Ghi kết quả thực tế của API/DB/broker, phân biệt accepted và verified.
5. Retry hữu hạn với backoff cho transient failure.
6. Chuyển RESULT_UNKNOWN/FAILED tới owner nếu không còn tự động an toàn.
7. Kích hoạt bước bù tiếp theo khi dependency đã thỏa.

**Tiêu chí đầu ra:** từng command có trạng thái và bằng chứng, không chỉ một bản ghi lỗi đã được log.

### Bước E — Xác nhận và khép sự cố

1. Đối soát DB reservation/order, trạng thái shipment, outbox và các consumer liên quan.
2. Xác minh không còn side effects sai hoặc các sai lệch đều được quản lý.
3. Ghi saga COMPENSATED hoặc MANUAL_REVIEW/FAILED_TERMINAL phù hợp.
4. Tổng hợp số message bị ảnh hưởng, số lần retry/bù và thời gian phục hồi.
5. Phân tích vì sao forward flow thất bại và khả năng phòng ngừa.
6. Cập nhật test, alert, API contract hoặc quy trình vận hành để tránh lặp lại.

**Tiêu chí đầu ra:** trạng thái cuối có thể giải trình qua audit và kết quả từ hệ thống đích.

## 21. Những anti-pattern về error flow xử lý bù

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi ErrorMessage là saga state | Restart làm mất thông tin đã thành công | Durable saga store và compensation commands |
| Mọi exception đều kích hoạt cancel | Hủy cả nghiệp vụ còn retry an toàn | Phân loại lỗi, bước và business policy |
| Retry lại toàn bộ flow sau lỗi cuối | Lặp giữ hàng, tạo shipment, charge | Idempotency từng bước và state machine |
| Coi DB rollback là rollback HTTP/Kafka | Side effects ngoài còn tồn tại | Compensation cho ranh giới ngoài |
| Coi HTTP timeout nghĩa là chưa thực hiện | Tạo trùng/hủy sai | RESULT_UNKNOWN và reconciliation |
| Bù bằng DELETE mất lịch sử | Mất audit/vi phạm nghiệp vụ | Giao dịch bù mới, trạng thái rõ |
| Gửi lại ErrorMessage vào business input | Throwable sai payload contract | Tái tạo command đúng schema |
| Không giới hạn retry bù | Retry storm, phí API, nghẽn worker | Retry budget/backoff/deadline |
| Mỗi retry dùng một idempotency key mới | Endpoint nhận nhiều ý định giống nhau | Key ổn định cho cùng command |
| Chạy release inventory hai lần | Tồn kho bị cộng dư | Reservation state và deduplication |
| Đánh dấu bù thành công khi HTTP trả 202 | Thực tế yêu cầu còn pending | Chờ final status hoặc reconciliation |
| Hai subscriber của PublishSubscribeChannel cùng bù | Double compensation | Một coordinator sở hữu side effects |
| Chỉ dùng broker DLQ làm bằng chứng bù | Không biết forward steps đã commit gì | Saga state và grant/side effect references |
| Không tính ack/offset và transaction | Mất hoặc phát lặp message | Test source/broker semantics |
| Gọi refund khi thiếu business approval | Rủi ro gian lận và tài chính | Phân quyền, approval và audit |
| Không kiểm tra callback đến muộn | Hồi sinh state đã bù | Version, expected-state check |
| Quên compensation failure | Saga kẹt không ai nhận | Retry riêng, escalation và owner |
| Không phân biệt lỗi business với lỗi hạ tầng | Bù không cần thiết | Retry/reconcile trước khi cancel |
| Log toàn bộ failedMessage | Lộ secret/PII | Structured metadata, masking |
| Không monitor backlog bù | Worker dừng im lặng | Metrics last success, pending age, alerts |

## 22. Checklist thiết kế và triển khai

### A. Hợp đồng và bước nghiệp vụ

- [ ] Xác định mục tiêu nghiệp vụ và trạng thái cuối cho từng loại kết quả.
- [ ] Liệt kê side effects của mỗi File/SFTP/HTTP/broker/JDBC endpoint.
- [ ] Phân biệt bước có thể rollback, bù được, không đảo được và outcome unknown.
- [ ] Có business key/sagaId/correlationId ổn định.
- [ ] Mỗi forward action có precondition, response ID và idempotency nếu phù hợp.
- [ ] Có chính sách dependency và thứ tự bù theo nghiệp vụ.

### B. Error flow trong Spring Integration

- [ ] Biết exception nào throw đồng bộ và exception nào được publish.
- [ ] Có error channel/handler phù hợp với poller, gateway hoặc listener thực tế.
- [ ] Đọc ErrorMessage payload như Throwable; xử lý null failedMessage/originalMessage.
- [ ] Không cho header điều khiển hoặc target ID từ nguồn không tin cậy quyết định lệnh bù.
- [ ] Error observer không tự thực thi nhiều side effects thiếu state.
- [ ] Khi error handler lỗi, failure vẫn được phát hiện và có cơ chế bảo tồn.

### C. State, consistency và recovery

- [ ] Saga state và compensation commands được lưu bền vững.
- [ ] State transition có concurrency/version check.
- [ ] Có transactional outbox hoặc cơ chế tương đương khi state và message cần đồng bộ.
- [ ] Forward và compensation commands đều xử lý trùng an toàn.
- [ ] Timeout/outcome unknown có API tra cứu hoặc manual reconciliation.
- [ ] Retry có backoff, giới hạn, deadline và final disposition.
- [ ] Không đánh dấu COMPENSATED trước khi xác minh hành động bù.
- [ ] Có owner và SLA cho các saga MANUAL_REVIEW.

### D. Tương thích adapter

- [ ] File/SFTP có filter, durable reference, quarantine và replay policy.
- [ ] HTTP có response contract, idempotency, status lookup hoặc quy tắc unknown.
- [ ] JMS/AMQP có acknowledgment, redelivery, DLQ phù hợp.
- [ ] Kafka có offset/commit, DLT và event bù theo contract consumer.
- [ ] JDBC có transaction boundary, reservation state và outbox phù hợp.
- [ ] Không giả định một local transaction bao trùm hệ thống ngoài.

### E. Test và vận hành

- [ ] Test mỗi điểm failure trước/sau side effect.
- [ ] Test crash/restart, delivery trùng, event đến trễ và nhiều worker.
- [ ] Test compensation cũng gặp lỗi, HTTP 202 và timeout unknown.
- [ ] Test không bù sai tenant hoặc resource.
- [ ] Có log/trace/correlation, metrics, alert trên backlog và deadline.
- [ ] Có runbook, audit, phân quyền vận hành và chính sách dữ liệu nhạy cảm.

## 23. Câu hỏi tự kiểm tra

**Câu 1. Error flow xử lý bù khác errorChannel mặc định như thế nào?**

**Trả lời:** errorChannel là một MessageChannel nhận những ErrorMessage đã được publish. Error flow xử lý bù là **workflow nghiệp vụ do ứng dụng thiết kế** để xem các side effects, quyết định retry/reconciliation/compensation và xác minh hành động bù. Có errorChannel chưa đồng nghĩa có saga.

**Câu 2. Khi validation CSV thất bại trước khi ghi DB và gọi HTTP, có cần compensation không?**

**Trả lời:** Thông thường không, vì chưa có side effect nghiệp vụ. Nên reject/quarantine và thông báo lỗi dữ liệu. Nếu một phần batch đã xử lý thì cần xét trạng thái từng record.

**Câu 3. DB đã rollback nhưng HTTP đối tác trước đó đã tạo booking. Có thể coi toàn bộ nghiệp vụ đã rollback không?**

**Trả lời:** Không. Local transaction DB không bao trùm HTTP. Phải tìm booking đã tạo, quyết định có cần cancel và thực hiện API bù với quyền, resource ID và idempotency phù hợp.

**Câu 4. Một HTTP request CreateShipment timeout. Có nên gọi CancelShipment ngay?**

**Trả lời:** Không nên đoán đã tạo hay chưa. Đánh dấu RESULT_UNKNOWN, tra cứu theo request ID/idempotency key, rồi quyết định tiếp tục, retry hoặc bù theo kết quả tin cậy.

**Câu 5. Vì sao compensation command cần idempotency key ổn định?**

**Trả lời:** Worker hoặc broker có thể gửi lại cùng command. Key ổn định giúp tránh việc cancel/refund/release nhiều lần cho cùng ý định, cùng với state và dedupe của bên xử lý.

**Câu 6. Nếu release inventory được thực hiện hai lần và mỗi lần cộng 5 vào tồn kho, lỗi gì xảy ra?**

**Trả lời:** Tồn kho cộng dư 5 đơn vị. Cần lưu reservationId/status, dùng transaction/lock hoặc API idempotent để release chỉ có hiệu lực một lần.

**Câu 7. Khi Kafka publish event thất bại nhưng DB và HTTP đã thành công, luôn phải hủy nghiệp vụ không?**

**Trả lời:** Không. Nếu business goal vẫn còn hợp lệ và đã lưu outbox, có thể retry việc publish. Chỉ hủy khi policy/deadline nghiệp vụ yêu cầu; error kỹ thuật không tự đồng nghĩa business cancellation.

**Câu 8. Vì sao một sự kiện OrderCancelled không “xóa” event OrderCreated đã gửi trước?**

**Trả lời:** Event đã có thể được nhiều consumer xử lý. OrderCancelled là một sự kiện nghiệp vụ mới để các consumer điều chỉnh trạng thái theo contract, không phải thao tác thu hồi record cũ.

**Câu 9. ErrorMessage.getOriginalMessage() và MessagingException.getFailedMessage() có luôn chứa toàn bộ dữ liệu saga không?**

**Trả lời:** Không. Chúng có thể null hoặc chỉ chứa message tại điểm lỗi. Saga state bền vững và correlation ID mới là cơ sở để xác định các bước đã thành công.

**Câu 10. Chỉ cần một subscriber trên global errorChannel để xử lý bù mọi flow có an toàn không?**

**Trả lời:** Thường không phù hợp. Mỗi flow có business policy, side effect và retry khác nhau. Nên có coordinator/recovery riêng, còn global error channel phục vụ quan sát và phân tuyến tổng quát.

**Câu 11. Trong JMS/AMQP, việc publish ErrorMessage có nghĩa broker sẽ redeliver không?**

**Trả lời:** Không. Ack, nack, rollback và redelivery do container/broker cùng cách xử lý exception quyết định. Cần kiểm tra cụ thể và tránh ack trước khi recovery state được lưu an toàn.

**Câu 12. Nếu API cancel trả 202 Accepted, có thể đánh dấu command SUCCEEDED chưa?**

**Trả lời:** Chưa chắc. 202 có thể chỉ xác nhận đã nhận yêu cầu; phải đợi kết quả cuối hoặc truy vấn trạng thái theo contract trước khi kết luận bù hoàn tất.

**Câu 13. Vì sao cần lưu compensation commands trong database hoặc queue bền vững?**

**Trả lời:** ErrorMessage trên channel trong bộ nhớ không bảo đảm tồn tại sau restart. Kho bền vững cho phép retry, audit, kiểm soát concurrency và tiếp tục bù sau khi worker crash.

**Câu 14. Nếu một command bù có trạng thái RUNNING khi worker crash thì xử lý thế nào?**

**Trả lời:** Dùng lease/claim expiry, kiểm tra outcome thực tế và idempotency trước khi chạy lại. Không chỉ đổi ngay về PENDING rồi gửi lặp mà bỏ qua side effect trước crash.

**Câu 15. RefundPayment có thể được coi là thao tác undo y hệt charge không?**

**Trả lời:** Không. Refund thường là giao dịch mới, có lịch sử, phí, thời hạn, điều kiện và nghĩa vụ kế toán riêng; có thể cần approval.

**Câu 16. Khi nào nên chuyển sang MANUAL_REVIEW?**

**Trả lời:** Khi không xác minh được outcome, bù đã hết retry/deadline, phía đích không còn hỗ trợ cancel, thiếu quyền phê duyệt hoặc action mới có thể gây tác hại. Cần owner, tình trạng thực tế và kế hoạch xử lý.

**Câu 17. Có cần transaction cho state saga và outbox không?**

**Trả lời:** Nên commit atomically khi chúng cùng nằm trong một DB và được cập nhật cho cùng quyết định. Nhưng outbox vẫn có thể phát lại thông điệp khi crash, vì vậy receiver cần idempotency.

**Câu 18. Làm sao chứng minh một saga đã COMPENSATED?**

**Trả lời:** Cần trạng thái bù đã được xác minh tại tài nguyên liên quan, không còn command pending/unknown quan trọng, dữ liệu nhất quán theo policy và audit đầy đủ. Chỉ enqueue command hoặc ghi ErrorMessage là chưa đủ.

## 24. Kết luận

**Error flow xử lý bù** là cách biến một lỗi kỹ thuật trong luồng tích hợp thành **quyết định khôi phục nhất quán nghiệp vụ**. Trong Spring Integration, **MessageChannel**, **adapter/gateway**, **poller**, **ErrorMessage** và **errorChannel** giúp vận chuyển thông điệp và thông tin lỗi. Nhưng phần khó nhất vẫn do ứng dụng đảm nhiệm: **xác định bước đã commit, lưu state, chọn retry hay bù, thực thi command an toàn và xác minh kết quả**.

Ghi nhớ sáu nguyên tắc:

1. **Không phải lỗi nào cũng cần bù:** validation chưa có side effect khác timeout sau commit.
2. **Rollback không vượt ranh giới tự do:** DB transaction không tự undo HTTP, SFTP, JMS, AMQP hoặc Kafka đã có tác động.
3. **Không đoán kết quả unknown:** timeout cần đối soát trước khi retry hoặc cancel.
4. **Bù phải idempotent và bền vững:** lưu saga state, command ID, resource ID, retry budget và owner.
5. **Bù cũng có thể thất bại:** cần state MANUAL_REVIEW, cảnh báo và quy trình vận hành.
6. **Chỉ kết luận hoàn tất khi kiểm chứng:** một ErrorMessage, một HTTP 202 hay một command được enqueue không chứng minh nghiệp vụ đã nhất quán.

Khi liên kết đúng **ErrorMessage/errorChannel** với **saga coordination, transaction/outbox, idempotency, reconciliation và các error policy của từng adapter**, hệ thống Spring Integration có thể giảm lỗi mất thông điệp, xử lý trùng và side effects tồn dư khi kết nối các hệ thống ngoài.

### Hướng đọc tiếp

- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel, MessagePublishingErrorHandler và error strategy.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): xây dựng IntegrationFlow, MessageChannel và endpoint.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): ranh giới transaction, propagation và rollback.
- [Enterprise Integration Patterns — Compensating Action](https://www.enterpriseintegrationpatterns.com/): tham khảo nguyên lý xử lý bù trong hệ thống tích hợp.

Các đoạn Java, JSON, YAML, SQL và Mermaid trong bài là **ví dụ giáo dục**; tên channel, interface, API đối tác và schema saga đều cần điều chỉnh cho ứng dụng thật. Hãy đối chiếu phiên bản Spring Boot/Spring Integration, xác minh contract của adapter/container và chạy integration tests trước khi áp dụng trong production.
