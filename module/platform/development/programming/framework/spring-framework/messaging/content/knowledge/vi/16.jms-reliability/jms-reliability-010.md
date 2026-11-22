# Phân biệt giao nhận thành công với bảo đảm hiệu ứng nghiệp vụ một lần

## 1. Ba kết quả khác nhau thường bị gọi chung là “gửi thành công”

Trong hệ thống messaging, câu “message đã gửi thành công” có thể chỉ ba việc khác nhau:

1. **Producer gửi được message:** lời gọi send kết thúc bình thường và JMS provider chấp nhận thao tác gửi theo cấu hình/provider contract.
2. **Consumer nhận và xác nhận message:** broker giao message cho consumer và acknowledgement hoặc transaction được hoàn tất.
3. **Nghiệp vụ tạo ra hiệu ứng đã commit:** dữ liệu quan trọng được ghi nhận, ví dụ đơn hàng chuyển trạng thái, số dư thay đổi hoặc một lệnh thanh toán được chấp nhận.

Ba kết quả này xảy ra ở những ranh giới khác nhau. Producer có thể gửi được message nhưng consumer chưa nhận. Consumer có thể nhận message nhưng xử lý thất bại. Consumer có thể commit database rồi mất kết nối trước khi JMS acknowledgement hoàn tất, khiến broker giao lại message.

Vì vậy, một API `send()` trả về thành công không chứng minh consumer đã xử lý xong; một acknowledgement không chứng minh mọi side effect bên ngoài đã commit; và một message chỉ được giao một lần cũng không tự bảo đảm một nghiệp vụ chỉ xảy ra một lần.

Trong bài này, **hiệu ứng nghiệp vụ một lần** có nghĩa là với cùng một định danh sự kiện logic, hệ thống ghi nhận thay đổi nghiệp vụ tối đa một lần trong system of record, kể cả khi message được gửi lại hoặc giao lại. Đây là mục tiêu có thể thiết kế bằng idempotency và transaction; nó khác với lời hứa “mạng chỉ giao đúng một bản sao”.

## 2. Các ranh giới trong một luồng JMS

Một luồng event thông thường có các bước:

~~~text
Producer service
    |
    | 1. send(eventId, payload)
    v
JMS provider / broker
    |
    | 2. deliver
    v
Consumer listener
    |
    | 3. validate + business processing
    v
Database transaction
    |
    | 4. commit business effect + inbox record
    v
Listener returns successfully
    |
    | 5. JMS acknowledgement / transaction commit
    v
Broker may remove message from pending delivery
~~~

Giữa các bước tồn tại failure window. Process có thể dừng, kết nối có thể đứt hoặc một transaction coordinator có thể trả kết quả không xác định. Thiết kế đúng phải xác định điều gì xảy ra nếu lỗi xuất hiện sau mỗi bước.

| Ranh giới | Điều đã được xác nhận | Điều chưa được xác nhận |
| --- | --- | --- |
| `send()` trả về bình thường | Provider đã chấp nhận thao tác gửi theo semantics của provider | Consumer đã nhận, xử lý hoặc commit nghiệp vụ |
| Broker giao message | Consumer/provider callback đã nhận được message | Consumer đã hoàn thành xử lý |
| JMS acknowledgement/commit | Provider có thể đánh dấu lần giao đã được xác nhận | Database hoặc API bên ngoài đã commit cùng lúc |
| Database commit | Thay đổi dữ liệu trong transaction database đã commit | JMS acknowledgement đã commit hoặc event tiếp theo đã được phát |
| Consumer ghi inbox và business data cùng transaction | Event ID và hiệu ứng database cùng commit hoặc rollback | Side effect bên ngoài database đã hoàn tất |

## 3. Producer send: thành công và kết quả không xác định

### 3.1. Send thành công không phải consumer acknowledgement

JMS producer gửi message tới một `Destination` qua `MessageProducer` hoặc API Spring như `JmsTemplate`. Khi lời gọi send trả về bình thường, producer biết thao tác gửi đã hoàn tất theo hợp đồng của API và provider. Nó không nhận được bằng chứng rằng consumer đã nhận hoặc xử lý message.

Spring `JmsTemplate` đơn giản hóa việc tạo và giải phóng JMS resources. Các thuộc tính QoS như delivery mode, priority và time-to-live có thể được cấu hình trên template; để các giá trị do template đặt thực sự ghi đè giá trị mặc định của provider, cần bật `explicitQosEnabled`. <Link ref="turn831759search2" title="Spring: Using JmsTemplate"/>

### 3.2. Persistent delivery cũng không phải exactly-once business effect

`DeliveryMode.PERSISTENT` yêu cầu provider lưu message theo durability semantics của JMS/provider. `NON_PERSISTENT` cho phép provider giảm chi phí lưu trữ và chấp nhận rủi ro mất message cao hơn khi provider gặp lỗi.

Persistent delivery giúp tăng khả năng message còn tồn tại sau sự cố broker, nhưng không chứng minh consumer đã xử lý. Nó cũng không phối hợp transaction broker với database nghiệp vụ. Cần xem thêm cấu hình storage, replication, acknowledgement của producer và failure policy của provider.

### 3.3. Retry send có thể tạo duplicate nghiệp vụ

Giả sử producer gửi event `OrderPlaced` tới broker. Broker đã nhận và lưu message, nhưng kết nối bị đứt trước khi producer nhận được kết quả. Producer không biết message đã được nhận hay chưa.

Nếu producer retry bằng một lệnh send mới, broker có thể nhận thêm một message có cùng ý nghĩa nghiệp vụ. Đây không nhất thiết là provider tự tạo duplicate: ứng dụng đã phát hai lần vì kết quả lần đầu không xác định.

Jakarta Messaging quy định provider không tạo bản sao thứ hai của một message đã được xác nhận theo semantics của provider. Tuy vậy, đặc tả cũng chỉ ra rằng lỗi xảy ra giữa thời điểm commit/send và lúc client nhận kết quả có thể khiến ứng dụng tạo ra các message trùng về mặt chức năng khi tự retry. <Link ref="turn831759search3" title="Jakarta Messaging 3.1: acknowledgement và duplicate production"/>

**Cách xử lý:** tạo `eventId` ổn định cho một sự kiện logic trước lần gửi đầu tiên. Mọi lần retry gửi cùng event phải giữ nguyên `eventId`. Không tạo event ID mới chỉ vì lần send trước timeout.

## 4. Consumer delivery và acknowledgement

JMS có thể giao lại message khi consumer chưa acknowledge, transaction rollback, Session recover hoặc kết nối/process gặp lỗi. Consumer vì vậy cần chấp nhận khả năng cùng một message được xử lý nhiều lần.

Các cơ chế chính:

- `AUTO_ACKNOWLEDGE`: provider tự xác nhận theo thời điểm quy định của API nhận đồng bộ hoặc callback bất đồng bộ.
- `CLIENT_ACKNOWLEDGE`: ứng dụng gọi `Message.acknowledge()`; acknowledgement áp dụng cho các message đã giao bởi cùng Session, không chỉ riêng message đang gọi.
- `DUPS_OK_ACKNOWLEDGE`: provider acknowledge lười; consumer phải chấp nhận duplicate.
- `SESSION_TRANSACTED`: `commit()` xác nhận các message đã nhận và commit message đã gửi trong Session; `rollback()` phục hồi input và hủy output của transaction.

Trong Jakarta Messaging, `JMSRedelivered` cho biết provider đánh dấu message có thể đã được giao trước đó. `JMSXDeliveryCount` là số lần giao theo provider; lần nhận đầu có giá trị 1 và giá trị từ 2 trở lên cho biết đã redeliver. Đây là metadata chẩn đoán, không phải khóa chống trùng nghiệp vụ. <Link ref="turn831759search3" title="Jakarta Messaging: JMSRedelivered và JMSXDeliveryCount"/>

Không nên dùng `JMSMessageID` làm business event ID. Message ID do provider quản lý và có thể khác nhau giữa hai lần producer gửi lại cùng một event logic. Business `eventId` phải do ứng dụng tạo và duy trì ổn định qua retry/replay.

## 5. Vì sao acknowledgement không bảo đảm hiệu ứng nghiệp vụ một lần?

Xét listener cập nhật database rồi để container acknowledge message:

~~~text
1. Broker giao OrderPlaced
2. Consumer cập nhật database
3. Database COMMIT
4. Process dừng trước khi JMS transaction/ack hoàn tất
5. Broker giao lại OrderPlaced
~~~

Ở lần giao thứ hai, consumer không thể chỉ nhìn vào message và giả định chưa xử lý. Thay đổi database đã commit ở lần đầu. Nếu thực hiện lại, đơn hàng hoặc số dư có thể bị cập nhật hai lần.

Chiều ngược lại cũng có thể xảy ra nếu database và JMS không cùng transaction: message được acknowledge nhưng database rollback hoặc không commit. Khi đó broker không giao lại message dù nghiệp vụ chưa được ghi nhận.

Đây là vấn đề dual-write: một thao tác nghiệp vụ cần cập nhật hai resource độc lập, nhưng không có một transaction nguyên tử bao trùm cả hai.

Spring mô tả rõ rằng local JMS transaction chỉ bao phủ việc nhận/gửi qua JMS Session; thao tác database là resource độc lập. Khi database đã commit nhưng JMS commit thất bại, listener cần phát hiện duplicate. Nếu cần một transaction phối hợp nhiều resource, Spring hỗ trợ cấu hình transaction manager JTA với XA-capable ConnectionFactory và database resource phù hợp. <Link ref="turn831759search0" title="Spring: Processing Messages Within Transactions"/>

## 6. Idempotency: xử lý cùng event nhiều lần nhưng chỉ tạo một hiệu ứng

Idempotent operation là thao tác có kết quả nghiệp vụ tương đương khi được thực hiện lặp lại với cùng input logic.

Ví dụ:

- `setStatus(orderId, PAID)` có thể idempotent nếu chỉ đặt trạng thái về `PAID`.
- `balance = balance + amount` không idempotent nếu chạy lại cùng event.
- `createInvoice(eventId)` chỉ idempotent nếu database bảo đảm event ID hoặc invoice key duy nhất và duplicate không tạo invoice mới.

### 6.1. Event ID ổn định

Mỗi event logic cần một ID duy nhất, ví dụ UUID hoặc ID do domain tạo. ID này được lưu trong payload hoặc metadata của message và giữ nguyên khi retry.

Ví dụ payload:

~~~json
{
  "eventId": "evt-2026-000184",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "orderId": "ORD-184",
  "amountCents": 12500
}
~~~

ID phải xác định một sự kiện logic, không phải một lần truyền qua broker. Nếu producer retry event trên, `eventId` vẫn là `evt-2026-000184`.

### 6.2. Inbox/deduplication table

Consumer lưu event ID đã xử lý vào một bảng inbox có unique constraint. Bản ghi inbox và thay đổi nghiệp vụ phải được commit trong cùng transaction database.

Ví dụ schema:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE business_order (
    order_id VARCHAR(100) PRIMARY KEY,
    total_cents BIGINT NOT NULL
);
~~~

`consumer_name` nằm trong khóa để hai consumer logic khác nhau có thể xử lý cùng một event độc lập nếu đó là yêu cầu. Nếu event ID đã được xử lý bởi cùng consumer, unique constraint ngăn ghi inbox lần thứ hai.

### 6.3. Thứ tự xử lý trong transaction

Trong một transaction database:

1. Thử insert `(consumer_name, event_id)` vào inbox.
2. Nếu insert vi phạm unique constraint, event đã được xử lý; rollback transaction hiện tại và trả kết quả duplicate.
3. Nếu insert thành công, thực hiện thay đổi nghiệp vụ.
4. Commit inbox record và business data cùng nhau.

Nếu thay đổi nghiệp vụ thất bại, transaction rollback cả inbox record. Broker có thể redeliver và consumer thử lại. Nếu database commit thành công nhưng JMS acknowledgement bị mất, event được redeliver; inbox unique key nhận ra duplicate và consumer không áp dụng hiệu ứng lần nữa.

Không chỉ `SELECT` inbox rồi mới `INSERT` mà thiếu unique constraint. Hai consumer đồng thời có thể cùng thấy chưa tồn tại và cùng thực hiện hiệu ứng. Unique constraint là lớp bảo vệ cuối cùng; transaction và xử lý duplicate-key phải được thiết kế rõ ràng.

### 6.4. Giữ inbox bao lâu?

Không xóa inbox record sớm hơn khoảng thời gian mà event có thể được replay hoặc redeliver. Nếu xóa record rồi message cũ được replay, hiệu ứng có thể chạy lại.

Chính sách retention cần tính tới:

- Thời hạn lưu message và DLQ ở broker.
- Khả năng replay lịch sử hoặc khôi phục backup.
- Thời gian retry của producer và consumer.
- Yêu cầu kiểm toán và quy định lưu trữ.
- Quy mô bảng, index và quy trình partition/archive.

Với một số domain, có thể dùng business key/version làm ràng buộc duy nhất thay vì giữ inbox vô hạn. Cần đảm bảo khóa đó thực sự đại diện cho một hiệu ứng chỉ được áp dụng một lần.

## 7. Transactional outbox: tránh mất event giữa database và broker

Producer thường phải vừa cập nhật database vừa phát event. Nếu làm hai thao tác riêng:

- Database commit trước, publish thất bại: dữ liệu đã thay đổi nhưng event không được phát.
- Publish trước, database rollback: consumer thấy event cho thay đổi chưa commit.

Transactional outbox lưu event vào cùng database transaction với thay đổi nghiệp vụ.

~~~text
Producer transaction
    |
    +--> UPDATE business_order
    |
    +--> INSERT outbox_event(event_id, payload, status)
    |
    v
  COMMIT
    |
    v
Outbox publisher
    |
    +--> publish event to JMS
    |
    +--> mark outbox row as sent
    v
Consumer
    |
    +--> insert inbox event_id
    +--> apply business effect
    +--> commit database transaction
~~~

Nếu producer transaction rollback, cả business update và outbox row đều rollback. Nếu commit, publisher có thể tìm row chưa gửi và tiếp tục sau khi process restart.

### 7.1. Outbox publisher vẫn có thể phát lại

Publisher có thể gửi event thành công tới broker rồi process dừng trước khi đánh dấu outbox row là `SENT`. Khi restart, publisher thấy row chưa gửi và publish lại.

Đây là hành vi at-least-once có chủ đích. Publisher cần giữ nguyên `eventId`; consumer inbox/dedup bảo vệ hiệu ứng database khỏi bị áp dụng hai lần.

### 7.2. Claim và publish an toàn khi có nhiều publisher

Nếu nhiều instance cùng đọc outbox, cần cơ chế claim/lease hoặc row locking để tránh cùng xử lý một row đồng thời. Cần:

- Chọn batch có giới hạn.
- Đánh dấu trạng thái `PROCESSING` hoặc đặt lease có thời hạn.
- Publish và kiểm tra kết quả theo semantics provider.
- Chỉ đánh dấu `SENT` sau khi publish được xác nhận theo chính sách.
- Cho phép lease hết hạn để instance khác tiếp quản khi publisher chết.
- Giữ `eventId` ổn định qua mọi lần retry.

Không giữ database lock trong lúc chờ broker lâu nếu có thể tránh. Thiết kế claim/lease, retry và ordering phù hợp với tải và yêu cầu domain.

Transactional outbox là pattern cho tính nguyên tử giữa thay đổi database và việc ghi nhận ý định phát event. Nó không tự biến broker thành exactly-once và vẫn cần idempotent consumer. <Link ref="turn831759search7" title="AWS Prescriptive Guidance: Transactional outbox"/>

## 8. Local JMS transaction, XA/JTA và outbox khác nhau thế nào?

| Cơ chế | Resource được phối hợp | Bảo đảm chính | Giới hạn |
| --- | --- | --- | --- |
| Local transacted JMS Session | JMS input và output trong cùng Session | Commit/rollback message nhận và gửi cùng nhau | Không tự bao gồm JDBC hoặc HTTP |
| JDBC transaction | Các thay đổi trên database connection/resource đó | Business data và inbox/outbox row cùng commit | Không tự commit JMS broker |
| XA/JTA | Nhiều XA resource manager được enlist trong cùng global transaction | Coordinator quản lý commit/rollback đa resource | Cần XA-capable resources, transaction log, recovery và vận hành phức tạp hơn |
| Transactional outbox + idempotent inbox | DB transaction ở producer và consumer, cộng publisher/broker | Không mất ý định phát event; consumer chịu được publish/delivery lặp | Giao nhận thường at-least-once; cần vận hành publisher và retention |

### 8.1. Local JMS transaction

Với Spring listener container, `sessionTransacted=true` mở local JMS transaction cho mỗi listener invocation. Nếu listener ném exception ra ngoài, message receipt được rollback. Response gửi qua cùng `SessionAwareMessageListener` có thể thuộc cùng transaction JMS.

Những thao tác database vẫn độc lập. Nếu database commit nhưng JMS commit thất bại, broker có thể redeliver; consumer nên có duplicate detection. <Link ref="turn831759search0" title="Spring: listener transaction semantics"/>

### 8.2. XA/JTA

XA/JTA có thể phối hợp database và JMS nếu cả hai resource hỗ trợ XA và được đăng ký đúng với transaction coordinator. Điều này cung cấp unified commit semantics nhưng thêm chi phí transaction log, recovery và khả năng gặp heuristic outcome.

Không dùng XA chỉ vì muốn tránh thiết kế idempotency. Outbox/inbox thường dễ triển khai và vận hành hơn trong kiến trúc dịch vụ độc lập. Nếu nghiệp vụ đòi hỏi một atomic transaction thật sự qua nhiều resource, đánh giá XA dựa trên provider, database và hạ tầng thực tế.

## 9. Exactly-once delivery và exactly-once effect

### 9.1. Exactly-once delivery

Đây là tuyên bố về số lần message được giao qua transport. JMS có acknowledgement và transaction để quản lý trạng thái delivery, nhưng failure window vẫn có thể tạo redelivery trước khi provider biết message đã được xác nhận hay chưa.

Đặc tả JMS quy định provider không giao lại một message đã được acknowledge. Tuy nhiên, consumer vẫn có thể nhận lại message chưa acknowledge khi có failure; producer retry sau kết quả không xác định cũng có thể tạo event logic trùng.

### 9.2. Exactly-once business effect

Đây là tuyên bố về số lần thay đổi nghiệp vụ được commit. Với một event ID ổn định, consumer có thể đảm bảo database effect được áp dụng tối đa một lần bằng cách ghi inbox và business data trong cùng transaction với unique constraint.

Điều này không có nghĩa toàn hệ thống chỉ thực hiện đúng một lần mọi thao tác. Message có thể được gửi và giao nhiều lần; handler có thể chạy nhiều lần; chỉ có effect được bảo vệ bởi transaction/idempotency key mới được áp dụng một lần.

### 9.3. External side effects

Nếu consumer gọi payment gateway, gửi email, gọi HTTP service hoặc ghi file, database inbox transaction không thể tự rollback side effect bên ngoài.

Đối với external API, dùng idempotency key do domain tạo nếu nhà cung cấp hỗ trợ. Gửi cùng key cho mọi lần retry của cùng một thao tác logic. Nếu API không hỗ trợ idempotency, cần mô hình trạng thái, reconciliation và cơ chế bù trừ; không thể suy ra exactly-once chỉ từ JMS acknowledgement.

Ví dụ, ghi `payment_requested` trong database và phát command qua outbox; service thanh toán gọi provider với cùng idempotency key; sau đó ghi kết quả theo transaction riêng. Email có thể cần bảng notification/outbox với trạng thái và chính sách gửi lại, nhưng nhà cung cấp email không nhất thiết bảo đảm email chỉ được gửi một lần.

## 10. Ordering và concurrency cũng ảnh hưởng tới business effect

Idempotency ngăn cùng event tạo hiệu ứng trùng; nó không tự đảm bảo thứ tự nghiệp vụ.

Ví dụ `OrderCreated` và `OrderCancelled` có thể đến theo thứ tự khác nhau nếu nhiều consumer xử lý song song, publisher retry hoặc broker không bảo đảm ordering trong cấu hình đang dùng.

Các biện pháp thường dùng:

- Gắn aggregate ID và sequence/version vào event.
- Kiểm tra sequence kế tiếp trong transaction consumer.
- Dùng optimistic locking hoặc version condition khi update.
- Partition/route cùng aggregate tới cùng ordering key nếu broker hỗ trợ.
- Không giả định nhiều consumer trên một queue luôn hoàn tất theo thứ tự gửi.

Duplicate detection và ordering guard cần phối hợp: nếu event sequence 12 đã xử lý nhưng sequence 11 đến muộn, consumer cần chính sách chờ, từ chối/retry hoặc reconciliation tùy domain.

## 11. Retry, poison message và DLQ

Retry phù hợp với lỗi tạm thời như broker/database timeout, network interruption hoặc rate limit. Nó không giải quyết lỗi dữ liệu vĩnh viễn như schema sai, thiếu field bắt buộc hoặc event không hợp lệ.

Thiết kế retry nên có:

1. Phân loại transient error và permanent error.
2. Backoff tăng dần và jitter để tránh nhiều consumer retry cùng lúc.
3. Giới hạn số lần giao lại hoặc tổng thời gian retry.
4. DLQ cho message không thể xử lý sau chính sách retry.
5. Ghi event ID, delivery count, exception type và nguyên nhân vào log/trace.
6. Quy trình sửa dữ liệu hoặc code rồi replay từ DLQ.

Không bỏ qua message lỗi bằng cách acknowledge nếu nghiệp vụ chưa hoàn tất và không có quy trình bù trừ. Ngược lại, rollback vô hạn có thể khiến poison message chiếm consumer và làm backlog tăng.

Consumer idempotent giúp retry an toàn hơn, nhưng không thay thế retry policy. Cần đảm bảo inbox retention bao phủ thời gian message có thể quay lại từ DLQ/replay.

## 12. Ví dụ chạy được: inbox table ngăn áp dụng cùng event hai lần

Ví dụ dùng Java 17, JDBC và H2 để mô phỏng một event được giao hai lần. Mỗi lần xử lý mở một database transaction; inbox unique key và business update commit cùng nhau. Lần giao thứ hai vi phạm unique key và không tăng tổng tiền lần nữa.

Ví dụ này mô phỏng phần database/idempotency của consumer. Nó không khởi chạy JMS broker; trong ứng dụng thật, gọi `handle(event)` từ listener và để listener container acknowledge sau khi phương thức hoàn tất thành công.

Cấu trúc project:

~~~text
jms-idempotent-consumer/
  pom.xml
  src/main/java/com/example/messaging/IdempotentConsumerDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-idempotent-consumer</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <h2.version>2.3.232</h2.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>${h2.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/IdempotentConsumerDemo.java`:

~~~java
package com.example.messaging;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class IdempotentConsumerDemo {
    private static final String JDBC_URL =
            "jdbc:h2:mem:idempotency_demo;DB_CLOSE_DELAY=-1";

    private IdempotentConsumerDemo() {
    }

    private record OrderEvent(String eventId, String orderId, long amountCents) {
    }

    private enum Result {
        APPLIED, DUPLICATE
    }

    private static Connection openConnection() throws SQLException {
        return DriverManager.getConnection(JDBC_URL, "sa", "");
    }

    private static void initializeDatabase() throws SQLException {
        try (Connection connection = openConnection();
             Statement statement = connection.createStatement()) {
            statement.executeUpdate("CREATE TABLE inbox ("
                    + "event_id VARCHAR(100) PRIMARY KEY, "
                    + "processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
            statement.executeUpdate("CREATE TABLE business_orders ("
                    + "order_id VARCHAR(100) PRIMARY KEY, "
                    + "total_cents BIGINT NOT NULL)");
            statement.executeUpdate("INSERT INTO business_orders "
                    + "(order_id, total_cents) VALUES ('ORD-42', 0)");
        }
    }

    private static Result handle(OrderEvent event) throws SQLException {
        try (Connection connection = openConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement insert = connection.prepareStatement(
                        "INSERT INTO inbox (event_id) VALUES (?)")) {
                    insert.setString(1, event.eventId());
                    insert.executeUpdate();
                }

                try (PreparedStatement update = connection.prepareStatement(
                        "UPDATE business_orders "
                                + "SET total_cents = total_cents + ? "
                                + "WHERE order_id = ?")) {
                    update.setLong(1, event.amountCents());
                    update.setString(2, event.orderId());
                    if (update.executeUpdate() != 1) {
                        throw new SQLException("Order not found: " + event.orderId());
                    }
                }

                connection.commit();
                return Result.APPLIED;
            } catch (SQLException ex) {
                connection.rollback();
                if ("23505".equals(ex.getSQLState())) {
                    return Result.DUPLICATE;
                }
                throw ex;
            }
        }
    }

    private static long readOrderTotal(String orderId) throws SQLException {
        try (Connection connection = openConnection();
             PreparedStatement query = connection.prepareStatement(
                     "SELECT total_cents FROM business_orders WHERE order_id = ?")) {
            query.setString(1, orderId);
            try (ResultSet result = query.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("Order not found: " + orderId);
                }
                return result.getLong(1);
            }
        }
    }

    private static int inboxCount() throws SQLException {
        try (Connection connection = openConnection();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT COUNT(*) FROM inbox")) {
            result.next();
            return result.getInt(1);
        }
    }

    public static void main(String[] args) throws Exception {
        initializeDatabase();

        OrderEvent event = new OrderEvent("evt-1001", "ORD-42", 125);
        System.out.println("firstDelivery=" + handle(event));
        System.out.println("redelivery=" + handle(event));
        System.out.println("effectTotalCents=" + readOrderTotal("ORD-42"));
        System.out.println("inboxRows=" + inboxCount());
    }
}
~~~

Chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.IdempotentConsumerDemo
~~~

Stdout:

~~~text
firstDelivery=APPLIED
redelivery=DUPLICATE
effectTotalCents=125
inboxRows=1
~~~

Điều cần quan sát:

- Lần đầu, insert inbox thành công; business total tăng 125 cents; hai thay đổi commit cùng transaction.
- Lần giao lại dùng cùng `eventId`; unique primary key từ chối insert và transaction rollback; business total không tăng thêm.
- `inboxRows=1` cho thấy chỉ có một bản ghi xử lý cho event đó.

Demo dùng H2 in-memory để chạy độc lập và tạo output xác định. Dữ liệu sẽ mất khi JVM dừng; production cần database bền vững, backup phù hợp, unique constraint thật và retention inbox theo chính sách replay. Với nhiều consumer đồng thời, unique constraint vẫn là điểm phân xử; ứng dụng cần xử lý duplicate-key đúng theo database đang dùng.

## 13. Kiểm thử failure window

Không chỉ test đường thành công. Hãy mô phỏng ít nhất các tình huống sau:

| Failure point | Kết quả mong muốn | Cơ chế bảo vệ |
| --- | --- | --- |
| Producer crash trước khi ghi outbox transaction commit | Không có business update hoặc outbox row | Cùng database transaction |
| Producer crash sau commit, trước khi publish | Publisher tìm lại outbox row và publish sau | Outbox polling/CDC |
| Broker nhận event nhưng publisher crash trước khi đánh dấu sent | Publisher có thể publish lại cùng event ID | Consumer inbox/idempotency |
| Consumer crash trước database commit | Inbox và business update rollback; broker có thể redeliver | DB transaction + JMS rollback/ack policy |
| Database commit xong, consumer crash trước JMS ack | Broker redeliver; inbox nhận diện duplicate | Unique event ID trong inbox |
| Consumer nhận duplicate đồng thời trên hai instance | Chỉ một transaction insert inbox thành công | Unique constraint và transaction |
| External API xử lý thành công nhưng response timeout | Retry không tạo side effect thứ hai nếu provider hỗ trợ key | External idempotency key và reconciliation |
| Event poison bị retry nhiều lần | Không loop vô hạn; chuyển DLQ | Retry limit, backoff, DLQ |

Đặc biệt kiểm thử crash sau business commit nhưng trước acknowledgement. Đây là failure window thường bị bỏ sót khi chỉ test listener ném exception trước khi commit.

## 14. Observability: đo đúng điều cần biết

Không gộp mọi trạng thái thành một metric `messages_sent`. Nên theo dõi riêng:

- Producer send attempts, send successes, send exceptions và timeout/ambiguous outcomes.
- Outbox pending count, tuổi bản ghi cũ nhất, publish retries và thời gian từ DB commit tới broker publish.
- Consumer deliveries, successful acknowledgements/commits, rollbacks và redelivery count.
- Inbox duplicate count, unique constraint conflicts và business effects applied.
- Listener processing latency, database transaction latency và lỗi conversion/validation.
- Queue depth, message age, consumer lag và DLQ depth.
- External API idempotency conflict, timeout và reconciliation backlog.

Log/trace nên mang cùng `eventId`, `correlationId`, aggregate ID, sequence/version, destination và consumer name xuyên suốt producer, broker và consumer. Không ghi credential hoặc payload nhạy cảm.

Metric duplicate tăng không nhất thiết có nghĩa hệ thống lỗi: nó có thể là kết quả bình thường của retry/redelivery. Điều cần kiểm tra là duplicate có làm business effect tăng nhiều lần hay không.

## 15. Checklist thiết kế

1. `send()` đang xác nhận điều gì theo provider contract? Có producer confirm hoặc trạng thái outbox không?
2. Producer retry có giữ nguyên event ID của cùng một sự kiện logic không?
3. Message có dùng delivery mode và broker durability phù hợp không?
4. Consumer acknowledgement xảy ra trước hay sau business commit?
5. Listener container đang dùng AUTO, CLIENT, DUPS_OK hay transacted Session?
6. Có failure window giữa database commit và JMS ack không?
7. Inbox record và business update có cùng database transaction không?
8. Unique constraint có bảo vệ event ID trong trường hợp hai consumer chạy đồng thời không?
9. Inbox retention có bao phủ thời gian retry, DLQ và replay không?
10. Producer có dùng transactional outbox khi database update phải đi cùng event publication không?
11. Outbox publisher có thể publish lặp và consumer có xử lý được không?
12. External API có hỗ trợ idempotency key không? Nếu không, reconciliation/bù trừ ra sao?
13. Retry có backoff, giới hạn, DLQ và quy trình replay không?
14. Ordering theo aggregate có cần sequence/version guard không?
15. Có kiểm thử crash sau commit nhưng trước acknowledgement và publish confirmation không?
16. Dashboard có phân biệt send, delivery, ack, DB commit và business effect không?

## 16. Ghi nhớ

Giao nhận thành công và hiệu ứng nghiệp vụ một lần là hai cam kết khác nhau. Producer `send()` trả về bình thường chỉ xác nhận thao tác gửi theo provider contract; nó không chứng minh consumer đã xử lý. JMS acknowledgement/transaction quản lý việc broker xem message đã được nhận, nhưng không tự phối hợp với database hoặc external API. Retry sau một kết quả send không xác định có thể tạo event logic trùng; redelivery có thể khiến consumer nhận lại message chưa được acknowledge. Hãy gắn event ID ổn định, dùng inbox unique constraint và commit inbox cùng business data trong một database transaction. Dùng transactional outbox để lưu ý định phát event cùng business update; publisher có thể gửi lặp nên consumer vẫn cần idempotency. Với side effect ngoài database, dùng idempotency key của provider hoặc reconciliation. Thiết kế theo từng failure window và đo riêng send, delivery, acknowledgement, database commit và business effect.

### Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification — Message acknowledgement and duplicate delivery](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework 6.2 — Receiving a Message and Processing Messages Within Transactions](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2 — Using JmsTemplate and QoS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)