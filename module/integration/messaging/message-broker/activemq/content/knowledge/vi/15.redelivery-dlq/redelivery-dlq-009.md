# Phân tích, sửa và phát lại DLQ với kiểm soát thông điệp lặp

> **Chương:** Gửi lại và DLQ  
> **Phạm vi:** Apache ActiveMQ Artemis và ActiveMQ Classic qua Java/JMS. Tập trung quy trình điều tra, quyết định sửa lỗi, lựa chọn cách **replay (redrive)** message từ Dead Letter Queue và bảo vệ trước tác động nghiệp vụ trùng lặp.

Một message đã vào Dead Letter Queue (DLQ) không tự trở thành “message an toàn để chạy lại”. Nó có thể chứa dữ liệu sai, đã được xử lý thành công ở hệ thống ngoài nhưng mất ACK, có destination cũ không còn phù hợp hoặc đã hết thời hạn nghiệp vụ. Nếu chỉ chọn “Move all to original queue”, có nguy cơ tạo một cơn bão lỗi lặp, chuyển message sang sai subscriber hoặc thực hiện lại lệnh thanh toán.

**Nguyên tắc của bài:** DLQ là **hàng chờ điều tra và quyết định**, không phải một queue retry vô hạn. Mỗi lần phát lại cần trả lời được **vì sao message lỗi, đã sửa gì, tác động trước đó là gì, replay về đâu, có thể lặp ở mức nào và làm sao biết khi nào phải dừng**.

## 1. Phân biệt retry tự động với phát lại DLQ

Giả sử worker xử lý queue **billing.payment.commands.v1** bị lỗi. Broker có thể thực hiện nhiều lần redelivery theo chính sách. Khi đạt điều kiện đưa vào DLQ, thông điệp không còn nằm trên đường xử lý bình thường của queue gốc.

~~~mermaid
flowchart LR
    P["Producer"] --> Q["Queue nghiệp vụ"]
    Q --> C["Consumer"]
    C -->|Xử lý thành công + ACK| OK["Hoàn tất"]
    C -->|Rollback / chưa ACK| R["Redelivery policy"]
    R -->|Còn lượt thử| Q
    R -->|Đạt ngưỡng| D["DLQ"]
    D --> I["Điều tra nguyên nhân"]
    I --> F["Khắc phục + duyệt"]
    F --> X["Replay có giới hạn"]
    X --> Q
~~~

| Thuật ngữ | Ai quyết định? | Message đang ở đâu? | Có cần con người/phê duyệt? |
|---|---|---|---|
| **Redelivery** | Broker/client theo ACK/transaction và policy | Thường vẫn thuộc queue/luồng nhận ban đầu | Không nhất thiết |
| **Đưa vào DLQ** | Chính sách dead-letter sau các lần xử lý thất bại | Queue riêng để cách ly | Cần quan sát và phân loại |
| **Replay / redrive** | Runbook hoặc công cụ quản trị | Chuyển từ DLQ về luồng xử lý được chọn | Nên có kiểm soát, đặc biệt với dữ liệu thật |
| **Reconcile** | Nghiệp vụ/đối soát | Có thể không cần gửi message nào | Bắt buộc khi kết quả side effect chưa rõ |

**DLQ không chứng minh rằng nghiệp vụ chưa từng thực thi thành công.** Consumer có thể đã ghi database hoặc gọi payment provider thành công nhưng mất kết nối trước JMS ACK. Vì vậy, replay phải được xem như một **lần delivery bổ sung có khả năng trùng**, không phải “lần đầu xử lý”.

Bài này không đi sâu cách tính lại số lần redelivery. Trọng tâm là những gì phải làm **sau khi message đã ở DLQ**.

## 2. Quy trình điều tra: đọc trước, chưa ACK hoặc xóa

Bước đầu tiên không phải **receive()** message bằng một consumer AUTO_ACKNOWLEDGE để “xem nội dung”. Khi receive trả về thành công, message có thể đã được xác nhận và biến mất khỏi DLQ. Để khảo sát, ưu tiên chức năng **browse/read-only** của console, management API hoặc **JMS QueueBrowser**.

### 2.1. Những dữ kiện phải giữ lại

Một phiếu điều tra DLQ tối thiểu gồm:

| Nhóm | Dữ liệu cần ghi | Vì sao cần |
|---|---|---|
| **Định danh nguồn** | Broker/node, tên DLQ, original address, original queue/subscription, thời điểm chuyển DLQ | Tránh phát lại vào sai đường nhận |
| **Thông tin JMS** | JMSMessageID, JMSTimestamp, JMSExpiration, JMSCorrelationID, JMSRedelivered, properties liên quan | Giải thích message và điều kiện xử lý |
| **Định danh nghiệp vụ** | commandId/eventId, orderId, paymentAttemptId, tenantId nếu phù hợp | Chống trùng và đối soát tác động |
| **Nguyên nhân** | Exception, error code, stack trace rút gọn, số lượt giao, version consumer/schema | Phân biệt lỗi tạm thời với lỗi dữ liệu |
| **Trạng thái side effect** | DB đã commit chưa? Đã charge/cấp hàng/gửi email chưa? | Quyết định có được phát lại |
| **Kế hoạch xử lý** | Sửa code hay dữ liệu, destination đích, số message, replay batch ID, người duyệt | Audit và rollback |
| **Bằng chứng sau replay** | Số đã chuyển, số xử lý thành công, số quay lại DLQ, kết quả nghiệp vụ | Đóng incident dựa trên thực tế |

**Tùy sản phẩm và phiên bản**, DLQ message có thể kèm thuộc tính nội bộ về address/queue gốc. Với Artemis, có những metadata nội bộ như **_AMQ_ORIG_ADDRESS** và **_AMQ_ORIG_QUEUE** trên các message được chuyển theo đường quản trị/broker thích hợp. Không mặc nhiên xem các property đó luôn tồn tại, giữ nguyên định dạng hay đi xuyên AMQP/bridge. Nếu metadata thiếu hoặc mơ hồ, xác định nguồn qua broker management, cấu hình routing và log trước khi replay.

**Không dùng JMSXDeliveryCount như một sự thật bất biến xuyên DLQ → replay**: ở một lần gửi message mới hoặc một queue khác, giá trị delivery có thể đổi/reset theo provider. Cần lưu **replayAttempt** riêng do ứng dụng quản trị và đối chiếu audit log.

### 2.2. Browse bằng Java/JMS mà không lấy mất message

Ví dụ QueueBrowser của JMS 1.1/2.x, dùng **javax.jms**; có thể dùng Artemis JMS client hoặc Classic JMS client tương ứng:

~~~java
import java.util.Enumeration;
import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.QueueBrowser;
import javax.jms.Session;

public final class DlqBrowse {
    public static void browse(ConnectionFactory factory)
            throws Exception {
        Connection connection = factory.createConnection();
        try {
            Session session = connection.createSession(
                false, Session.AUTO_ACKNOWLEDGE);
            try {
                connection.start();
                Queue dlq = session.createQueue("DLQ.billing.payment");
                QueueBrowser browser = session.createBrowser(dlq);
                try {
                    Enumeration<?> entries = browser.getEnumeration();
                    int inspected = 0;

                    while (entries.hasMoreElements() && inspected < 20) {
                        Message message = (Message) entries.nextElement();
                        System.out.println(
                            "JMSMessageID=" + message.getJMSMessageID()
                            + " commandId="
                            + message.getStringProperty("commandId"));
                        inspected++;
                    }
                } finally {
                    browser.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
~~~

**QueueBrowser không ACK hoặc loại message khỏi DLQ.** Tuy nhiên phép browse **không phải snapshot giao dịch**: các consumer/admin khác có thể xóa hoặc di chuyển message đồng thời, và provider có thể giới hạn cách phân trang. Dùng browser cho mẫu nhỏ; khi DLQ có hàng trăm nghìn message nên dùng management API, filter, thống kê và công cụ xuất metadata có giới hạn.

Không in toàn bộ body có thể chứa thông tin cá nhân, secrets hoặc dữ liệu thanh toán vào log. Khi cần lưu chứng cứ, dùng vị trí lưu có quyền phù hợp và hash/ID thay vì sao chép payload tràn lan.

## 3. Phân loại nguyên nhân trước khi sửa

Một DLQ chỉ cho biết **đường xử lý cũ đã thất bại**, không nói nguyên nhân thuộc producer, consumer, broker hay dữ liệu.

| Phân loại | Dấu hiệu | Hành động đúng | Có nên replay ngay? |
|---|---|---|---|
| **Transient dependency** | Database/API timeout, mất kết nối ngắn; dependency hiện đã khỏe | Xác minh downstream đã phục hồi và giới hạn tốc độ | Có thể, sau kiểm tra |
| **Bug consumer** | NullPointerException, sai parser, version deploy lỗi | Sửa code, test regression, deploy consumer tương thích | **Không** trước khi deploy bản sửa |
| **Schema không tương thích** | Thiếu trường, enum mới, JSON phiên bản cũ | Sửa compatibility hoặc migration dữ liệu có thẩm quyền | Chỉ sau validation |
| **Poison message** | Một message cố định khiến consumer fail lặp lại | Cách ly, xác định data contract, quyết định loại/sửa | Không bulk replay |
| **Sai routing/ACL** | Message vào sai queue, user không đủ quyền, thiếu subscription | Sửa topology/config/permission đúng phạm vi | Chỉ khi route đã chứng minh đúng |
| **Tác vụ đã thành công nhưng mất ACK** | DB/provider có kết quả; message vẫn redeliver rồi vào DLQ | Đối soát theo business key, ACK/đánh dấu hoàn tất có kiểm chứng | **Không phát lại side effect** |
| **Dữ liệu không còn hữu ích** | Order đã hủy, message quá hạn, schema hết hỗ trợ | Đánh giá đóng/từ chối có audit | Thường không |
| **DLQ do cấu hình sai** | Max-delivery quá thấp, lỗi bảo mật, DLQ loop | Sửa policy, xác định phạm vi ảnh hưởng | Sau khi kiểm thử |

### 3.1. Câu hỏi nghiệp vụ bắt buộc với message có side effect

Một command **ChargePayment(paymentAttemptId=pay-741)** nằm trong DLQ. Trước khi replay phải trả lời:

1. Payment provider đã ghi nhận **pay-741** chưa?
2. Nếu đã ghi nhận, kết quả là **SUCCEEDED / DECLINED / PENDING / UNKNOWN**?
3. Hệ thống database nội bộ đã lưu kết quả bền vững chưa?
4. Consumer đã có **idempotency key** tương thích với provider chưa?
5. Có consumer khác hoặc thao tác thủ công nào đang xử lý **pay-741** không?

Nếu không thể trả lời, **đặt vào trạng thái cần đối soát**, không bấm replay và hy vọng broker “không gửi hai lần”. Broker không biết một lệnh thanh toán đã có side effect bên ngoài.

## 4. Sửa đúng lớp lỗi: code, cấu hình hay dữ liệu?

Có ba kiểu thay đổi phổ biến; mỗi kiểu yêu cầu bằng chứng khác nhau.

### 4.1. Sửa lỗi ở consumer

Ví dụ consumer phiên bản cũ chỉ hiểu **schemaVersion=1**, trong khi producer gửi **schemaVersion=2**. Hướng ưu tiên là:

1. Xác nhận **contract** và lỗi parser bằng một payload đã khử dữ liệu nhạy cảm.
2. Phát hành consumer hỗ trợ version cũ và mới hoặc một chuyển đổi có schema rõ ràng.
3. Viết test với message gây lỗi đã xác định.
4. Kiểm tra canary consumer trên queue lab, không dùng DLQ thật làm nơi thử parser.
5. Chỉ replay sau khi metric/error rate cho thấy bản sửa đang hoạt động.

**Không sửa payload gốc để che giấu một lỗi consumer có thể tái phát với mọi message tương lai.** Nếu nguyên nhân là code, sửa code thường là cách tránh tạo DLQ mới.

### 4.2. Sửa cấu hình broker hoặc downstream

Các ví dụ: sai address DLQ, credential thiếu permission, connection pool hết capacity, redelivery interval gây quá tải, endpoint thanh toán đang ngừng phục vụ.

Sau khi sửa, chứng minh bằng **một message kiểm thử riêng** rằng consumer có thể hoàn tất transaction và ACK; sau đó replay **một message thật đã phê duyệt** và quan sát end-to-end. Nếu cùng lỗi vẫn còn, dừng ngay thay vì đẩy toàn bộ backlog trở lại queue.

### 4.3. Sửa một message sai dữ liệu

Chỉ sửa payload khi biết **giá trị đúng từ nguồn có thẩm quyền**. Ví dụ một phiên bản cũ thiếu **currency** nhưng order database xác nhận **VND**; có thể tạo message mới với currency đã phê duyệt.

Không suy đoán dữ liệu tài chính từ mặc định cấu hình hoặc từ tên queue. Với những lỗi **amountMinor** sai, không được tự “làm tròn và replay” nếu chưa có quyết định nghiệp vụ hoặc quy trình hoàn tiền/đối soát.

Khi sửa:

- Giữ **commandId/eventId/paymentAttemptId** nếu vẫn là cùng thao tác logic.
- Ghi **repairReason, repairVersion, replayOperationId**, định danh source message và người duyệt ở audit store.
- Tạo **message mới** bằng JMS API phù hợp; đừng giả định có thể sửa body hoặc protected headers của message đã nhận rồi gửi nguyên trạng.
- Không sao chép mù quáng **JMSMessageID**, **JMSRedelivered**, **JMSXDeliveryCount**, **JMSExpiration**, **JMSReplyTo**.
- Kiểm tra destination, schemaVersion, TTL, delivery mode và property routing trước khi phát.
- Không tiếp tục vô hạn khi cùng message quay lại DLQ; giới hạn replayAttempt ở **cấp nghiệp vụ/runbook**.

### 4.4. Trường hợp phải đóng message mà không replay

Một số message nên được xử lý bằng **từ chối có audit** hoặc **reconciliation** thay vì replay:

- Command trừ tiền đã hoàn tất thành công ở provider.
- Order đã hủy và command không còn hợp lệ.
- Dữ liệu chứa vi phạm schema không thể xác định nguồn thật.
- Message hết thời hạn xử lý, tác vụ đã được bù trừ hoặc thay thế.
- Payload chứa dữ liệu cần xóa theo quy định và không được phép giữ lâu hơn.

**Xóa một message DLQ** có thể hợp lý sau khi hoàn tất thủ tục, nhưng phải có bằng chứng quyết định và người duyệt. Không dùng bulk purge để “làm đẹp dashboard”.

## 5. Chọn chiến lược redrive: giữ message hay tạo message sửa?

Không phải tất cả thông điệp trong DLQ đều có thể chuyển về queue gốc bằng cùng một công cụ.

| Phương án | Khi phù hợp | Lợi thế | Nguy cơ |
|---|---|---|---|
| **Broker-native retry/move** theo ID được chọn | Payload đúng, lỗi consumer/downstream đã sửa | Giữ nhiều metadata và đường nguồn theo cơ chế broker | Có thể requeue sai nếu original route/queue không còn; semantics theo sản phẩm |
| **Consume DLQ + tạo message sửa + gửi đích mới trong JMS transaction** | Payload cần biến đổi theo contract có phê duyệt | Validation và audit rõ từng message | Tạo message mới, thay provider ID, phải quản lý TTL/ACL/routing |
| **Rebuild từ nguồn nghiệp vụ/outbox** | DLQ payload không đủ tin cậy hoặc message quá cũ | Dùng dữ liệu được xác minh và version mới | Có thể làm trùng side effect nếu không dùng business ID ổn định |
| **Không phát lại, chỉ reconcile/close** | Nghiệp vụ đã hoàn tất hoặc command không còn hợp lệ | Tránh gửi lặp không cần thiết | Phải lưu bằng chứng và có quy trình đóng |

### 5.1. Artemis: phân biệt original address với original queue

Artemis định tuyến qua **address** và queue liên kết. Nếu message gốc thuộc **MULTICAST topic** nhưng chỉ một subscription queue gặp lỗi rồi đưa vào DLQ, việc **publish lại vào address MULTICAST** có thể khiến **mọi subscription** nhận thêm một event, kể cả những nhóm đã xử lý thành công.

~~~text
Address orders.events.v1   [MULTICAST]
    ├── inventory.subscription     xử lý thành công
    └── notification.subscription  chuyển bản của mình vào DLQ

Replay ngây thơ: publish lại vào orders.events.v1
    ├── inventory nhận thêm event!    ← không mong muốn
    └── notification nhận thêm event
~~~

Vì vậy cần chọn một trong hai:

- **Retry về đúng original subscription queue** bằng chức năng quản trị broker có hỗ trợ và đã kiểm tra metadata.
- **Rebuild và phát vào address chung** chỉ khi *tất cả* downstream có idempotency phù hợp và đây là chủ đích vận hành.
- **Sửa bản sao riêng cho consumer lỗi** bằng một tuyến nhận được thiết kế cụ thể.

**Không coi original address = original queue** trong mọi topology. Với ANYCAST một queue đơn lẻ, việc gửi vào original JMS Queue đơn giản hơn nhưng vẫn phải xác minh queue/address binding.

### 5.2. Artemis và Classic khác nhau ở đâu?

**Artemis:** dùng address/queue, DLQ gắn với dead-letter-address; quản trị thường có chức năng browse, move/retry references theo message hoặc filter. Phải kiểm tra chức năng của **phiên bản** và scope trên queue cụ thể, đặc biệt với wildcard/multicast. Không tự đoán tên queue khi chỉ biết address.

**ActiveMQ Classic:** dead-letter strategy và destination thường được quản lý qua cấu hình, JMX/console; deployment có thể dùng **ActiveMQ.DLQ** chung hoặc một DLQ riêng theo policy. Với DLQ chung, không thể nhìn tên **ActiveMQ.DLQ** rồi suy ra mọi message có cùng nguồn. Cần xác minh metadata và destination đích trước khi move.

Nếu console báo đã “move” thành công, vẫn phải **đọc counters và kiểm tra consumer nghiệp vụ**, không coi thao tác quản trị thành công là ACK hoặc xử lý business hoàn tất.

## 6. Cấu hình Artemis cho bài lab DLQ có thể truy vết

Một cấu hình minh họa dành cho **broker lab** với queue ANYCAST và DLQ riêng:

~~~xml
<!-- Fragment trong phần <address-settings> của broker.xml -->
<address-settings>
    <address-setting match="billing.payment.commands.v1">
        <dead-letter-address>DLQ.billing.payment</dead-letter-address>
        <max-delivery-attempts>3</max-delivery-attempts>
        <redelivery-delay>2000</redelivery-delay>
    </address-setting>
</address-settings>
~~~

~~~xml
<!-- Fragment trong phần <addresses> của broker.xml -->
<addresses>
    <address name="billing.payment.commands.v1">
        <anycast>
            <queue name="billing.payment.commands.v1"
                   durable="true"/>
        </anycast>
    </address>

    <address name="DLQ.billing.payment">
        <anycast>
            <queue name="DLQ.billing.payment"
                   durable="true"/>
        </anycast>
    </address>
</addresses>
~~~

**Giải thích đúng phạm vi:**

- **max-delivery-attempts=3** là chính sách retry/delivery mà broker áp dụng trước khi dead-letter theo cấu hình; không dùng số này làm **số lần được phép replay thủ công**.
- **redelivery-delay=2000** là khoảng delay cấu hình (ms), không phải cam kết message luôn quay lại đúng sau 2 giây.
- **dead-letter-address** chỉ định đích dead letter. Tùy routing và bindings, phải có queue đích thực sự nhận được message; chỉ khai báo tên address chưa đủ để đảm bảo lưu vào DLQ.
- DLQ trong ví dụ là tài nguyên bền vững; phải có quyền truy cập hạn chế, retention, alert, dung lượng lưu trữ và người sở hữu.
- Những phiên bản Artemis có tính năng tự tạo tài nguyên DLQ nhưng ở đây **chủ động provision** nhằm tránh phụ thuộc mặc định/version.

**Không đặt DLQ về chính address nghiệp vụ** hoặc tạo vòng DLQ → cùng consumer lỗi không có điểm dừng. Nếu thao tác phát lại lỗi liên tục, message có thể quay về DLQ và số lần replay tăng; nên có **hard limit** độc lập với max-delivery-attempts.

## 7. Runbook phát lại có kiểm soát

Quy trình sau áp dụng cho **batch DLQ thực**, ngay cả khi chỉ có một message có vẻ đơn giản.

### 7.1. Các bước bắt buộc

1. **Khoanh vùng:** chọn đúng broker, DLQ, original queue/subscription, tenant và khoảng thời gian; không dùng wildcard quá rộng.
2. **Ngăn nguồn gây lỗi:** sửa code/config/downstream, xác minh phiên bản consumer đang chạy, tạm dừng luồng tạo thêm DLQ nếu cần.
3. **Đọc và lập danh sách** bằng browse/management, lọc theo business ID và loại lỗi. Không dùng consumer AUTO_ACK chỉ để đọc.
4. **Đối soát side effect:** xem DB/provider theo commandId/paymentAttemptId; đánh dấu **ALREADY_DONE / SAFE_TO_RETRY / NEEDS_REPAIR / UNKNOWN**.
5. **Phê duyệt:** lưu change/incident ID, owner, danh sách ID dự kiến, cách xử lý và cửa sổ thực hiện.
6. **Chọn phương án:** native retry đúng original queue, transform có validation hay reconcile/close không phát.
7. **Đặt rào chắn trùng lặp:** kiểm tra unique constraint/inbox, khóa idempotency của downstream, tình trạng replayer khác và replay limit.
8. **Dry-run:** validate schema, original destination, số lượng và điều kiện an toàn; không gọi send khi dry-run.
9. **Canary:** replay **1 message hoặc nhóm rất nhỏ**, kiểm tra kết quả nghiệp vụ và DLQ loop.
10. **Mở theo batch:** giới hạn tốc độ, batch size, concurrency và tổng số message; có ngưỡng dừng tự động.
11. **Đối chiếu số lượng:** số được chọn, đã replay, còn trong DLQ, đang xử lý, quay lại DLQ, đã hoàn tất, đã từ chối.
12. **Đóng incident:** lưu audit, chứng cứ sửa lỗi, kết quả, quyết định những message còn lại; không purge chung để che lỗi.

### 7.2. State machine cho mỗi message

~~~mermaid
stateDiagram-v2
    [*] --> QUARANTINED
    QUARANTINED --> INVESTIGATING: điều tra
    INVESTIGATING --> RECONCILING: tác động chưa rõ
    INVESTIGATING --> READY: dữ liệu / consumer đã sửa
    INVESTIGATING --> CLOSED_NO_REPLAY: không còn hợp lệ
    RECONCILING --> READY: xác nhận an toàn
    RECONCILING --> CLOSED_NO_REPLAY: đã xử lý thành công
    READY --> APPROVED: duyệt danh sách + ID
    APPROVED --> REPLAYING: chạy canary / batch
    REPLAYING --> VERIFIED: business success đã xác minh
    REPLAYING --> QUARANTINED: lỗi tiếp / giới hạn
    VERIFIED --> [*]
    CLOSED_NO_REPLAY --> [*]
~~~

Đây là **trạng thái vận hành tự thiết kế**, không phải JMS header hay bộ state có sẵn trong ActiveMQ. Nên lưu state vào một **replay ledger** bền vững để hai người vận hành không cùng phát lại một message.

### 7.3. Ngưỡng dừng ví dụ

Một batch được cấu hình trước có thể dừng khi:

- Bất kỳ command **đã xử lý** xuất hiện dấu hiệu phát sinh side effect lần hai.
- Message canary quay lại DLQ vì **cùng root cause**.
- Tỉ lệ lỗi vượt ngưỡng đã phê duyệt, hoặc latency/queue age của luồng live tăng mạnh.
- Số **replayAttempt** của một business ID đạt giới hạn.
- Xuất hiện mismatch giữa số message đã ACK khỏi DLQ và số message đã route thành công sang đích.
- Người điều hành phát hiện original queue/subscription không khớp hợp đồng định tuyến.

Ngưỡng cụ thể phải dựa trên loại nghiệp vụ và SLO. Không có một số lần replay an toàn chung cho mọi ActiveMQ workload.

## 8. Ví dụ Java/JMS: sửa rồi chuyển đúng một message trong transaction

Ví dụ dành cho **Artemis ANYCAST** ở mục 6. Bài lab giả định một bản ghi cũ **ChargePayment** thiếu trường **currency**, nhưng đơn hàng trong nguồn dữ liệu đáng tin cậy đã được xác minh có currency cần bổ sung. Code yêu cầu người vận hành truyền **currency đã được phê duyệt**; bản thân chương trình **không tự kiểm tra database gốc**.

**Giới hạn nghiêm ngặt:** không dùng trực tiếp với tiền thật; đây là ví dụ thao tác **đúng một message** để thấy cách preserve business ID, chọn message bằng selector, sửa payload, gửi message mới và ACK message DLQ bằng **một JMS transaction trong cùng broker/provider**.

### 8.1. Điều kiện trước khi chạy

- Artemis broker lab, hai queue ANYCAST **DLQ.billing.payment** và **billing.payment.commands.v1** đã tồn tại; tài khoản có quyền consume DLQ và send tới queue gốc.
- Dùng **artemis-jms-client** tương thích với **javax.jms** (JMS 2.x) và thư viện Jackson **jackson-databind**; nếu dự án dùng **jakarta.jms**, đổi client và import đồng bộ.
- Message DLQ là **TextMessage JSON**, có JMS property **commandId** dùng làm selector, và body chứa **type=ChargePayment**, **commandId** tương ứng, **schemaVersion=1**, thiếu **currency**.
- Business ID đã được đối soát: chưa có side effect cần ngăn, và **currency** được lấy từ nguồn đáng tin cậy.
- Không có một replayer khác cùng thao tác trên message được chọn; có audit replayOperationId riêng.
- Trước khi gửi, đã kiểm tra **_AMQ_DUPL_ID của lần phát gốc** và chính sách duplicate detection; không sao chép nguyên duplicate ID cũ vào message replay.

### 8.2. Chương trình mẫu

~~~java
import java.util.regex.Pattern;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;

import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ReplayOnePaymentDlq {
    private static final String DLQ = "DLQ.billing.payment";
    private static final String TARGET = "billing.payment.commands.v1";
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._:-]{1,80}");
    private static final Pattern CURRENCY =
        Pattern.compile("[A-Z]{3}");
    private static final ObjectMapper JSON = new ObjectMapper();

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: <approvedCommandId> <approvedCurrency> "
                + "<replayOperationId>");
        }

        String commandId = args[0];
        String approvedCurrency = args[1];
        String replayOperationId = args[2];

        requireMatch(commandId, SAFE_ID, "commandId");
        requireMatch(approvedCurrency, CURRENCY, "currency");
        requireMatch(replayOperationId, SAFE_ID, "operation ID");

        ConnectionFactory factory = new ActiveMQConnectionFactory(
            required("MQ_URL"));

        try (JMSContext ctx = factory.createContext(
                required("MQ_USER"),
                required("MQ_PASSWORD"),
                JMSContext.SESSION_TRANSACTED)) {

            Queue dlq = ctx.createQueue(DLQ);
            Queue destination = ctx.createQueue(TARGET);

            // Chỉ xử lý message có commandId đã được phê duyệt.
            // Không nối trực tiếp input tùy ý vào JMS selector.
            String selector = "commandId = '" + commandId + "'";
            JMSConsumer source = ctx.createConsumer(dlq, selector);

            try {
                Message original = source.receive(3000);
                if (original == null) {
                    System.out.println("No matching DLQ message");
                    return;
                }

                if (!(original instanceof TextMessage)) {
                    throw new IllegalStateException(
                        "DLQ item is not a TextMessage");
                }
                if (!commandId.equals(
                        original.getStringProperty("commandId"))) {
                    throw new IllegalStateException(
                        "DLQ commandId mismatch");
                }

                String oldMessageId = original.getJMSMessageID();
                String oldText = ((TextMessage) original).getText();
                JsonNode parsed = JSON.readTree(oldText);

                if (!(parsed instanceof ObjectNode)) {
                    throw new IllegalStateException(
                        "Expected JSON object");
                }

                ObjectNode data = (ObjectNode) parsed;

                if (!"ChargePayment".equals(
                        data.path("type").asText())) {
                    throw new IllegalStateException(
                        "Unexpected command type");
                }
                if (!commandId.equals(
                        data.path("commandId").asText())) {
                    throw new IllegalStateException(
                        "Payload commandId mismatch");
                }
                if (data.path("schemaVersion").asInt(-1) != 1) {
                    throw new IllegalStateException(
                        "Unsupported schema version");
                }
                if (data.hasNonNull("currency")) {
                    throw new IllegalStateException(
                        "Currency already exists; manual review required");
                }

                int previousReplays =
                    original.propertyExists("dlqReplayCount")
                    ? original.getIntProperty("dlqReplayCount")
                    : 0;

                if (previousReplays >= 2) {
                    throw new IllegalStateException(
                        "Replay budget exhausted");
                }

                data.put("currency", approvedCurrency);
                TextMessage repaired = ctx.createTextMessage(
                    JSON.writeValueAsString(data));

                // Business identity stays stable across redrive.
                repaired.setStringProperty("commandId", commandId);
                repaired.setIntProperty("schemaVersion", 1);

                // Audit identities; replayOperationId belongs to runbook.
                repaired.setIntProperty(
                    "dlqReplayCount", previousReplays + 1);
                repaired.setStringProperty(
                    "dlqReplayOperationId", replayOperationId);

                if (oldMessageId != null) {
                    repaired.setStringProperty(
                        "sourceDlqJmsMessageId", oldMessageId);
                }

                String correlation =
                    original.getJMSCorrelationID();
                if (correlation != null) {
                    repaired.setJMSCorrelationID(correlation);
                }

                // KHÔNG sao chép JMSMessageID, JMSReplyTo,
                // JMSRedelivered, JMSXDeliveryCount hay _AMQ_DUPL_ID.
                // TTL 1 ngày là ví dụ đã quyết định riêng cho lab.
                ctx.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .setTimeToLive(24L * 60 * 60 * 1000)
                   .send(destination, repaired);

                // Receive từ DLQ và send mới thuộc một JMS transaction.
                ctx.commit();

                System.out.println(
                    "Committed replay operation " + replayOperationId
                    + " for commandId " + commandId);
            } catch (Exception error) {
                ctx.rollback();
                throw error;
            } finally {
                source.close();
            }
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }

    private static void requireMatch(
            String value, Pattern pattern, String name) {
        if (!pattern.matcher(value).matches()) {
            throw new IllegalArgumentException(
                "Invalid " + name);
        }
    }
}
~~~

**Những điều mã đảm bảo trong phạm vi một broker/JMS transaction:**

1. Chỉ **receive** một message có **commandId** được phép, không quét toàn bộ DLQ.
2. Không thay đổi bản gốc trong chỗ; tạo **TextMessage mới** sau khi kiểm tra schema/type/business key.
3. Chỉ thêm **currency** khi thiếu và được người vận hành cung cấp giá trị đã xác minh.
4. Giữ **commandId**; gắn **dlqReplayOperationId** và số lần replay độc lập với bộ đếm redelivery.
5. **Send message sửa + ACK nguồn DLQ** trong cùng JMS session transacted; nếu xảy ra exception trước commit, rollback sẽ giữ message nguồn cho lần điều tra tiếp theo.
6. **JMSMessageID của message replay là ID mới**, không phải khóa nghiệp vụ; consumer vẫn phải idempotent.

**Điều mã không bảo đảm:**

- Không chứng minh currency do người vận hành nhập là đúng; phải có quy trình phê duyệt từ nguồn dữ liệu.
- Không tự kiểm tra side effect ở payment provider hoặc database.
- Không tránh được mọi kết quả **commit mơ hồ** khi mất kết nối; sau crash phải **đọc lại DLQ/queue đích và replay ledger**, không tự sinh operation ID mới rồi gửi thêm.
- Không thích hợp với **MULTICAST subscription** vì gửi vào JMS Queue đích có thể không tương đương thao tác native retry đúng subscription gốc.
- Không tự thiết lập một **replay ledger bền vững** hoặc khóa chống chạy hai công cụ đồng thời. Đó là phần cần bổ sung trước production.
- Không bảo toàn tự động mọi message property của source; những property nghiệp vụ khác (tenantId, eventId, trace context, routing key) phải được định nghĩa rõ và copy **theo allowlist**, không sao chép tràn lan.

### 8.3. Vì sao cố tình không sao chép _AMQ_DUPL_ID?

Trong Artemis, property **_AMQ_DUPL_ID** kích hoạt duplicate detection phía broker. Một bản command có thể đã từng được accept với duplicate ID cũ trước khi được đưa vào DLQ. Nếu gửi message sửa trở lại **cùng address** với **đúng duplicate ID cũ**, broker có thể nhận diện nó là bản gửi trùng và **không route bản replay**.

~~~text
Lần publish gốc:
  commandId       = cmd-1042
  _AMQ_DUPL_ID    = pub-1042
  → vào queue, xử lý lỗi, chuyển DLQ

Replay sửa:
  commandId       = cmd-1042          (GIỮ để dedupe nghiệp vụ)
  _AMQ_DUPL_ID    = pub-1042          (KHÔNG nên sao chép mù quáng)
  → có thể bị suppress vì cache đã thấy pub-1042
~~~

**Đừng sử dụng duplicate ID cũ như một “khóa chống lặp” cho replay.** Nếu một replay pipeline cần chống producer resend riêng, có thể cấp **một duplicate ID mới, ổn định cho chính replay operation** (ví dụ ghép operation ID và command ID), với kiểm tra rõ giao dịch và cache. Nhưng cơ chế đó vẫn không bảo đảm chống trùng nghiệp vụ mãi mãi. Phải lưu **commandId/eventId** và dùng inbox hoặc unique constraint tại consumer.

### 8.4. Cẩn thận với TTL và các header chỉ đọc

Khi phát lại, gửi **message mới**; JMS provider sẽ tạo **JMSMessageID** mới, và có thể cấp timestamp/expiration mới theo thiết lập producer. Đừng cố copy **JMSExpiration** của bản cũ: nếu đã hết hạn, message mới có thể hết hạn ngay. TTL phải là quyết định nghiệp vụ của đợt replay.

**JMSReplyTo** cũng có thể trỏ tới TemporaryQueue đã biến mất. Nếu tác vụ cần phản hồi sau replay, nên dùng **kênh kết quả bền vững** theo business ID, không tự đưa response vào một temporary destination đã chết.

**JMSXDeliveryCount** hoặc **JMSRedelivered** là metadata delivery được broker/provider quản lý. Không dùng chúng thay **dlqReplayCount** của quy trình vận hành.

## 9. Kiểm soát thông điệp lặp khi phát lại

Hai lớp chống trùng bổ sung cho nhau:

~~~mermaid
flowchart TD
    L["DLQ: commandId=cmd-1042"] --> G["Replay ledger: quyết định + quota"]
    G --> R["Move hoặc republish có kiểm soát"]
    R --> B["Broker routing / duplicate detection"]
    B --> C["Consumer nhận message"]
    C --> I{"commandId đã xử lý?"}
    I -->|Có| A["Không thực thi side effect; ACK an toàn"]
    I -->|Chưa| T["Ghi inbox + nghiệp vụ trong DB transaction"]
    T --> A
~~~

### 9.1. Replay ledger

Một bảng quản trị có thể thiết kế:

~~~sql
CREATE TABLE dlq_replay_operations (
    operation_id     TEXT PRIMARY KEY,
    source_broker    TEXT NOT NULL,
    source_queue     TEXT NOT NULL,
    target_queue     TEXT NOT NULL,
    business_id      TEXT NOT NULL,
    source_message_id TEXT,
    approved_by      TEXT NOT NULL,
    reason_code      TEXT NOT NULL,
    state            TEXT NOT NULL,
    attempt_count    INT NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX dlq_replay_by_business
    ON dlq_replay_operations (business_id, state);
~~~

**Tùy trường hợp**, nên có ràng buộc uniqueness cho **một operation active theo source message/business ID**, nhưng đừng dùng một unique key quá rộng làm cấm mọi replay hợp lệ về sau. Ví dụ một message đã được sửa và chạy lỗi lại có thể cần **operation mới** với approval mới sau khi phân tích nguyên nhân; lịch sử cũ phải được giữ để audit.

Để tránh hai replayer chạy đồng thời:

- Khóa theo **operation ID/source message ID** trong replay ledger bằng transaction DB và lease có hạn.
- Xác nhận **owner của lease** trước khi chạy.
- Luôn kiểm tra lại DLQ source message khi bắt đầu transaction JMS.
- Dùng **tốc độ/batch limit**, không chỉ unique key.
- Có quy tắc xử lý **IN_DOUBT** nếu DB ledger và JMS commit xảy ra ở hai hệ thống khác nhau.

**Một bảng replay ledger không làm transaction DB và transaction JMS thành một transaction nguyên tử.** Khi mất kết nối ở giữa, phải đối soát thay vì gửi lại ngay.

### 9.2. Business inbox / idempotency

Ví dụ một inbox dùng PostgreSQL:

~~~sql
CREATE TABLE processed_commands (
    consumer_name TEXT NOT NULL,
    command_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, command_id)
);
~~~

Trong transaction nghiệp vụ:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT processed_commands(consumer_name, command_id)
  ON CONFLICT DO NOTHING

  Nếu insert thành công:
      thực hiện tác động nghiệp vụ trong cùng transaction
  Nếu đã có:
      bỏ qua side effect; đọc kết quả đã lưu nếu cần
COMMIT DATABASE TRANSACTION

COMMIT JMS RECEIVE
~~~

Với side effect **ngoài database** (payment gateway, email provider), unique constraint này không tự làm side effect trở nên nguyên tử. Phải sử dụng **idempotency key downstream**, lưu trạng thái và reconciliation. Cùng một **commandId** được replay bao nhiêu lần cũng không được làm xuất hiện khoản thanh toán thứ hai nếu đó là cùng nghiệp vụ.

### 9.3. Điều gì xảy ra với Artemis duplicate detection?

Artemis có thể dùng **_AMQ_DUPL_ID** để chặn publish lặp ở ingress khi ID còn trong cache của address. Nó **không thay thế consumer idempotency** và không xử lý được mọi lần phát lại:

- Replay bằng message mới có thể dùng **duplicate ID mới**.
- Cache có giới hạn, có thể bị eviction hoặc thay đổi sau restart/HA.
- Chuyển queue trong broker và publish lại có thể đi qua cơ chế khác nhau.
- Consumer redelivery sau rollback không phải lần producer publish mới.
- Hai command có duplicate ID khác nhau vẫn có thể cùng yêu cầu **một hiệu ứng nghiệp vụ**.

Vì vậy **giữ business ID**, không cố giữ JMSMessageID, và không mặc định một cờ duplicate detection đủ bảo vệ production replay.

### 9.4. Replay loop: DLQ → original → DLQ

Một loop thường xảy ra khi code lỗi chưa được sửa hoặc payload được sửa sai:

~~~text
DLQ (attempt 0)
   → replay
Queue nghiệp vụ
   → consumer lỗi như cũ
DLQ (attempt 1)
   → replay tiếp
Queue nghiệp vụ
   → ...
~~~

Chặn bằng:

- **Hard limit** trên số **dlqReplayCount** hoặc replay ledger attempt per business ID.
- Gắn **repairVersion/deploymentVersion**, chỉ replay sau khi có thay đổi giải quyết root cause.
- Dừng batch khi canary quay lại DLQ vì cùng mã lỗi.
- Không “auto replay mọi DLQ sau N phút” đối với command có side effect.
- Duy trì đường điều tra thủ công cho **UNKNOWN / poison message**.

## 10. Bài lab kiểm chứng an toàn

### Lab A — Đưa một message lỗi có chủ đích vào DLQ

**Mục tiêu:** quan sát message từ queue gốc chuyển DLQ và thu thập metadata.

1. Trên broker lab cấu hình **max-delivery-attempts=3** và DLQ như mục 6.
2. Gửi **ChargePayment** với commandId **cmd-1042**, schemaVersion=1 và thiếu **currency**.
3. Consumer lab cố tình rollback khi thiếu currency, không gọi payment provider.
4. Chờ theo policy cho tới khi message chuyển DLQ.
5. Dùng **QueueBrowser** xem commandId/JMSMessageID, kiểm tra original route bằng management/log.
6. Ghi reason code, delivery count (nếu có) và trạng thái đã chứng minh chưa có side effect.

**Đạt:** phân biệt được message hiện ở DLQ với message đang redeliver trên queue gốc; không làm mất message khi điều tra.

### Lab B — Sửa rồi phát lại một message

**Mục tiêu:** kiểm tra send tới queue đích và ACK khỏi DLQ cùng thuộc một JMS transaction.

1. Xác nhận currency=**VND** bằng nguồn dữ liệu test đã định nghĩa.
2. Deploy consumer lab đã hỗ trợ currency và có inbox theo commandId.
3. Chạy **ReplayOnePaymentDlq** với commandId=**cmd-1042**, currency=**VND**, operationId mới.
4. Đọc **DLQ count** và **queue đích count** sau commit; kiểm tra một business outcome.
5. Ghi JMSMessageID mới, commandId giữ nguyên và replayOperationId.
6. Chạy lại cùng operation khi nguồn DLQ không còn: **No matching DLQ message**, không tự gửi thêm.

**Đạt:** không có message nguồn bị ACK trước khi việc send mới được commit; không có side effect bị nhân đôi.

### Lab C — Simulate lỗi trước commit

**Mục tiêu:** xác minh rollback khi send hoặc validation thất bại.

1. Chọn một message lab khác đã vào DLQ.
2. Thay target test bằng một đích không có permission hoặc chủ động ném exception trước **ctx.commit()**.
3. Quan sát transaction rollback; message vẫn còn ở DLQ.
4. Khôi phục cấu hình và chạy lại sau approval.

**Đạt:** khi transaction chưa commit, **không được báo replay thành công**, không được xóa nguồn DLQ chỉ vì app đã gọi receive.

### Lab D — Cùng commandId, hai lần replay

**Mục tiêu:** chứng minh không thể dựa vào JMSMessageID.

1. Tạo hai message lỗi trong DLQ với **hai JMSMessageID khác nhau**, nhưng cùng **commandId=cmd-1042**, trong sandbox.
2. Replay cả hai bằng hai operation ID được duyệt.
3. Consumer inbox có unique **(consumer_name, command_id)** và xử lý side effect trong cùng DB transaction.
4. Quan sát message có thể được giao nhiều lần nhưng database chỉ ghi **một hiệu ứng**.

**Đạt:** idempotency theo business ID; không dedupe chỉ bằng JMSMessageID.

### Lab E — Multicast subscription và đường replay

**Mục tiêu:** tránh phát lại sang các subscriber đã xử lý xong.

1. Tạo MULTICAST address **orders.events.v1** với hai subscription queue **inventory** và **notification**.
2. Cho **inventory** xử lý thành công, **notification** cố tình đưa message của mình vào DLQ.
3. So sánh thao tác quản trị retry **về đúng subscription queue** với cách publish lại event lên address MULTICAST (chỉ trên sandbox).
4. Ghi số message của từng queue và business ID.

**Đạt:** giải thích được vì sao publish lại vào address chung có thể tạo bản sao mới cho cả inventory; phân biệt **original address** với **original queue**.

### Lab F — Replay canary phát sinh DLQ loop

**Mục tiêu:** kiểm tra điều kiện dừng.

1. Giữ consumer lỗi chưa được sửa trong sandbox.
2. Replay **một message canary**, đo thời gian và xác định nó quay lại DLQ vì cùng exception.
3. Dừng batch theo rule, không tiếp tục replay phần còn lại.
4. Sửa consumer, kiểm tra test regression rồi thử một canary mới.

**Đạt:** công cụ không tạo vòng lặp vô hạn và có log trạng thái replayOperationId, failure reason, attempt budget.

## 11. Đối chiếu trước–sau để nghiệm thu replay

Một lần chuyển message thành công là **bước trung gian**, không phải đích cuối.

| Đối tượng đo | Trước | Sau canary | Sau batch | Tiêu chí đánh giá |
|---|---|---|---|---|
| DLQ pending | N | N − số đã lấy khỏi DLQ + số quay lại | Theo từng nhóm lỗi | Không có mất mát/biến động không giải thích được |
| Queue đích pending/delivering | Đã ghi baseline | Tăng hoặc được consumer xử lý | Trở về mức SLO | Không nghẽn luồng live |
| Lỗi xử lý cùng root cause | Baseline | Không tái hiện ở canary | Không bùng phát | Nếu tái hiện phải dừng |
| Inbox duplicate hit | Baseline | Có thể tăng | Có thể tăng | Mọi duplicate không tạo thêm side effect |
| Business outcome | Đã đối soát | Một outcome đúng | Mỗi business key có outcome đúng | Không double charge/double shipment |
| Replay attempt count | Theo ledger | Trong quota | Không vượt quota | Không có loop |
| Người duyệt, log, operation ID | Có trước chạy | Ghi đủ | Ghi đủ | Truy vết được từng message |

Không dùng phép cộng **DLQ giảm bao nhiêu = đã xử lý thành công bấy nhiêu**. Một message đã chuyển khỏi DLQ có thể còn in-flight ở queue đích, hoặc đã quay lại DLQ sau đó.

### 11.1. Số liệu nên đặt cạnh nhau

- **dlq_message_count** theo queue, nguyên nhân và tuổi message lớn nhất.
- **dlq_ingress_rate** và top error codes, không chỉ tổng backlog.
- **replay_selected / replay_committed / replay_failed / replay_in_doubt** theo operation.
- **replay_back_to_dlq** và tỉ lệ lỗi tái diễn.
- **business_id_duplicate_detected** từ inbox hoặc payment provider.
- **queue_age / delivering / ACK / DLQ** của luồng nhận sau replay.
- **consumer version / repair version** dùng xử lý canary.

Giữ **replay audit ledger** đủ lâu để đối soát sau incident; không lưu toàn bộ payload nhạy cảm nếu chỉ cần hash/ID/version.

## 12. Checklist thao tác production

- [ ] Đã biết **original address và original queue/subscription**, không suy diễn chỉ từ tên DLQ.
- [ ] Đã browse/read-only, chưa consume AUTO_ACK hoặc purge khi chưa phê duyệt.
- [ ] Đã phân loại lỗi và xác nhận đã sửa đúng lớp (**code/config/data**).
- [ ] Đã đối soát **business side effect**; các tác vụ UNKNOWN không bị replay tùy tiện.
- [ ] Có **business ID** ổn định để consumer dedupe; JMSMessageID chỉ dùng truy vết.
- [ ] Có người duyệt, danh sách ID, **replayOperationId**, replayAttempt budget, thời gian và owner.
- [ ] Có rào chắn hai replayer đồng thời và phương án xử lý **commit in doubt**.
- [ ] Chọn **native retry** hay **repaired republish** phù hợp loại message và routing; cẩn trọng MULTICAST.
- [ ] Không sao chép vô điều kiện **JMSMessageID, JMSReplyTo, JMSXDeliveryCount, JMSExpiration, _AMQ_DUPL_ID**.
- [ ] Khi sửa payload, có schema validation và giá trị thay thế từ **nguồn dữ liệu có thẩm quyền**.
- [ ] Với Artemis, không tái dùng **_AMQ_DUPL_ID** cũ để vô tình suppress bản replay.
- [ ] Khi chuyển một message giữa hai queue trong cùng broker, dùng transaction JMS/management operation có semantics đã thử.
- [ ] Không giả định transaction JMS là transaction với database/payment provider; vẫn cần inbox/idempotency.
- [ ] Đã chạy **canary**, quan sát nghiệp vụ và điều kiện dừng trước batch.
- [ ] Có giới hạn **batch size, concurrency, rate và max replay attempts**.
- [ ] Đã kiểm tra DLQ loop, queue đích, consumer version, error rate và duplicate side effect.
- [ ] Đã lưu bằng chứng outcome và quyết định rõ đối với message không replay.

**Kết luận:** Phát lại DLQ an toàn không phải là thao tác di chuyển message đơn thuần. Quy trình đúng là **đọc không phá hủy → xác định nguyên nhân → đối soát tác động nghiệp vụ → sửa có bằng chứng → phê duyệt và canary → replay có giới hạn → kiểm chứng kết quả**. Với ActiveMQ Artemis và Classic, phải xác minh destination gốc và semantics của thao tác quản trị; với Java/JMS, cần giữ **business ID** để chống lặp hiệu ứng, không dùng JMSMessageID hay duplicate detection cache như bảo đảm tuyệt đối. Chỉ đóng incident khi đã giải thích được **từng nhóm message**, bao gồm những message được xử lý thành công, những message không cần replay và những message còn cần điều tra.
