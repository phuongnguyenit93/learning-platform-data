# Phân biệt mã thông điệp, mã nghiệp vụ và mã truy vết

## 1. Vì sao cần nhiều loại mã?

Trong hệ thống message-driven, một message có thể đi qua nhiều channel, broker, consumer và dịch vụ. Một giao dịch nghiệp vụ cũng có thể tạo ra nhiều message; một message có thể được giao lại nhiều lần; và một request có thể đi qua nhiều service span trong distributed trace. Vì vậy, một mã duy nhất hiếm khi diễn tả đúng mọi khái niệm.

Ví dụ: khách hàng đặt đơn `ORD-2048`. Hệ thống tạo sự kiện `OrderPlaced`, sau đó phát lệnh giữ hàng, yêu cầu thanh toán và thông báo email. Những message này cùng liên quan đến một đơn hàng, nhưng mỗi message là một đơn vị trao đổi riêng. Chúng có thể cùng thuộc một workflow và được quan sát trong một trace, song mỗi khái niệm có vòng đời khác nhau.

Phân biệt đúng ID giúp:

- Chống xử lý trùng mà không bỏ sót sự kiện khác của cùng một đối tượng.
- Liên kết log, message và các bước xử lý trong một workflow.
- Truy vết request xuyên qua nhiều service và nhiều lần gọi downstream.
- Điều tra lỗi retry, redelivery, replay và xử lý sai thứ tự.
- Thiết kế payload/header ổn định khi producer và consumer được triển khai độc lập.

## 2. Các loại ID và phạm vi của chúng

| Loại mã | Nó định danh điều gì? | Vòng đời điển hình | Dùng chủ yếu cho |
| --- | --- | --- | --- |
| Framework message ID | Một message object/envelope do Spring tạo | Theo message object; có thể đổi khi tạo message mới | Nhận diện message trong phạm vi framework |
| Application message ID / event ID | Một message logic hoặc một sự kiện nghiệp vụ cụ thể | Ổn định khi retry/replay cùng một message logic | Deduplication, audit và liên kết lần giao |
| Business ID / aggregate ID | Đối tượng nghiệp vụ như đơn hàng, thanh toán, khách hàng | Tồn tại suốt vòng đời đối tượng | Tìm dữ liệu và áp dụng quy tắc nghiệp vụ |
| Correlation ID | Một request hoặc workflow gồm nhiều bước | Có thể kéo dài qua nhiều message/service | Liên kết các bước của cùng một luồng nghiệp vụ |
| Trace ID | Một distributed trace | Theo một lần thực thi được tracing ghi nhận | Gom các span trong một trace |
| Span ID | Một operation/span cụ thể trong trace | Thường mới cho mỗi span | Xác định một bước gọi hoặc xử lý |
| Causation ID | Message/sự kiện trực tiếp gây ra message hiện tại | Trỏ tới message cha gần nhất | Dựng quan hệ nguyên nhân giữa các message |
| Broker delivery tag/offset | Vị trí hoặc lần giao trong broker | Theo queue, partition, consumer session hoặc lần giao | Ack, commit offset và quản lý vị trí đọc |
| Idempotency key | Một ý định/thao tác cần tránh thực hiện lặp | Ổn định trong phạm vi retry của thao tác | Bảo vệ command/API khỏi tác động trùng |

Các tên `messageId`, `eventId`, `correlationId` hay `traceId` không tự có ngữ nghĩa thống nhất chỉ vì tên giống nhau. Hãy định nghĩa rõ ID nào do ai tạo, duy nhất trong phạm vi nào, giữ nguyên qua retry hay không và consumer dùng nó để làm gì.

## 3. Mã thông điệp: định danh envelope hoặc message logic

### 3.1. Framework message ID trong Spring

`org.springframework.messaging.Message<T>` có payload và `MessageHeaders`. Spring quản lý các header chuẩn như ID và timestamp; có thể đọc ID của message bằng `message.getHeaders().getId()` và thời điểm bằng `message.getHeaders().getTimestamp()`.

Framework message ID nhận diện message object theo cơ chế của Spring. Khi tạo một message mới bằng `MessageBuilder`, chuyển đổi, sao chép hoặc dựng lại message, ID có thể được tạo lại tùy đường đi và cấu hình. Không dùng ID này làm khóa nghiệp vụ hoặc giả định nó sẽ ổn định qua mọi broker, adapter, serialization và lần replay.

Ví dụ, một producer tạo `Message<OrderPlaced>` rồi gửi qua channel. Nếu sau đó consumer tạo message mới để chuyển sang bước tiếp theo, message mới có thể có framework ID khác dù vẫn xử lý cùng đơn hàng.

### 3.2. Application message ID hoặc event ID

Application message ID là mã do ứng dụng định nghĩa cho một đơn vị message logic. Với sự kiện, tên `eventId` thường thể hiện rõ hơn. Mã này nên được tạo một lần khi sự kiện được hình thành và giữ nguyên khi cùng sự kiện đó được retry, redeliver hoặc replay.

Ví dụ, event `PaymentCaptured` có `eventId=evt-pay-9001`. Nếu broker giao lại event vì consumer chưa ack, lần giao lại vẫn mang `evt-pay-9001`. Consumer có thể nhận biết đây là cùng một sự kiện đã gặp trước đó.

Nếu một sự kiện mới được tạo cho cùng một đơn hàng, nó phải có event ID mới. `OrderPlaced`, `PaymentCaptured` và `OrderShipped` có thể cùng mang `orderId=ORD-2048`, nhưng không được dùng chung một `eventId` chỉ vì chúng nói về cùng đơn hàng.

Đối với message không phải event, có thể dùng `appMessageId` hoặc `commandId`. Hãy tránh tên chung chung nếu hệ thống có nhiều loại định danh; tài liệu hợp đồng nên chỉ rõ nó đại diện cho message logic nào.

### 3.3. ID do broker cấp

Một số broker có message ID, delivery tag, sequence number hoặc offset. Các giá trị này phục vụ giao nhận và lưu trữ trong phạm vi broker:

- RabbitMQ delivery tag gắn với channel/consumer delivery và dùng để acknowledgement; không phải ID nghiệp vụ ổn định.
- Kafka offset là vị trí record trong một partition; nó không phải event ID toàn cục và có thể khác giữa các partition.
- Broker message ID có thể được producer đặt hoặc broker tạo tùy giao thức và adapter.

Không lấy delivery tag hoặc offset làm idempotency key xuyên qua hệ thống. Khi message được publish lại hoặc chuyển sang broker khác, vị trí giao nhận có thể thay đổi. Hãy giữ một event/message ID của ứng dụng trong payload hoặc header để nhận diện logic message.

## 4. Mã nghiệp vụ: định danh đối tượng trong domain

Business ID xác định một đối tượng mà nghiệp vụ quan tâm, ví dụ:

- `orderId`: đơn hàng.
- `paymentId`: khoản thanh toán hoặc lần thanh toán.
- `customerId`: khách hàng.
- `invoiceId`: hóa đơn.
- `shipmentId`: lô giao hàng.
- `aggregateId`: aggregate mà sự kiện mô tả trong thiết kế domain-driven.

Business ID thường được đặt trong **payload**, vì nó là dữ liệu cần để consumer áp dụng quy tắc nghiệp vụ. Có thể sao chép một giá trị sang header nếu adapter cần định tuyến hoặc lọc, nhưng phải xác định một nguồn dữ liệu chuẩn và kiểm tra hai bản sao không mâu thuẫn.

Một đối tượng nghiệp vụ có thể phát sinh rất nhiều message trong suốt vòng đời. Vì vậy, business ID không thay thế message/event ID. Ví dụ:

| Event | `eventId` | `orderId` |
| --- | --- | --- |
| `OrderPlaced` | `evt-001` | `ORD-2048` |
| `PaymentRequested` | `evt-002` | `ORD-2048` |
| `PaymentCaptured` | `evt-003` | `ORD-2048` |
| `OrderShipped` | `evt-004` | `ORD-2048` |

Ở đây `orderId` liên kết các sự kiện về cùng một đơn hàng; mỗi `eventId` xác định một sự kiện riêng.

Không dùng `orderId` làm khóa dedup cho tất cả message của đơn hàng. Nếu làm vậy, sau `OrderPlaced`, consumer có thể nhầm `PaymentCaptured` và `OrderShipped` là bản trùng chỉ vì chúng có cùng `orderId`.

Business ID cũng không nhất thiết là khóa chính database. Có thể dùng ID công khai dạng opaque/UUID thay vì để lộ số thứ tự nội bộ. Tránh đưa thông tin nhạy cảm như email, số điện thoại hoặc mã định danh cá nhân vào ID chỉ để tiện tìm kiếm.

## 5. Correlation ID và Causation ID

### 5.1. Correlation ID

`correlationId` liên kết nhiều request/message cùng thuộc một workflow hoặc một hành trình nghiệp vụ. Ví dụ, một lần checkout tạo các message kiểm tra tồn kho, yêu cầu thanh toán và gửi email. Những message đó có thể giữ cùng `correlationId=checkout-2048` để log và dashboard nhóm chúng lại.

Correlation ID thường được giữ qua các bước downstream của cùng workflow, kể cả khi mỗi bước tạo ra message logic mới. Nó không nhất thiết bằng business ID: một đơn hàng có thể được chỉnh sửa, thanh toán lại hoặc giao nhiều lần qua các workflow khác nhau.

Correlation ID cũng không nhất thiết bằng trace ID. Một workflow nghiệp vụ dài có thể kéo dài qua nhiều request hoặc trace; ngược lại, một trace có thể bao gồm nhiều bước kỹ thuật trong một request. Hãy giữ correlation ID nếu cần theo dõi workflow dài hơn vòng đời của một trace.

### 5.2. Causation ID

`causationId` cho biết message hiện tại được tạo trực tiếp bởi message/sự kiện nào. Ví dụ:

- `OrderPlaced` có `eventId=evt-001`.
- Consumer xử lý nó và tạo `ReserveInventory` với `causationId=evt-001`.
- Khi kho phát `InventoryReserved`, sự kiện có thể ghi `causationId` trỏ tới command hoặc message đã kích hoạt kết quả đó, theo quy ước của hệ thống.

Correlation ID trả lời “các message nào thuộc cùng workflow?”; causation ID trả lời “message này phát sinh trực tiếp từ message nào?”. Hai trường này bổ sung cho nhau.

## 6. Trace ID và Span ID trong distributed tracing

Distributed tracing mô hình hóa một request hoặc luồng xử lý kỹ thuật thành trace gồm nhiều span. Mỗi trace có `traceId`; mỗi operation có `spanId`; span con có quan hệ parent với span gọi nó.

- **Trace ID:** gom các span thuộc cùng một trace, thường xuyên qua nhiều service.
- **Span ID:** định danh một operation như HTTP client call, consumer handler hoặc database call.
- **Parent span ID:** liên kết span hiện tại với span đã tạo nó.

W3C Trace Context định nghĩa header `traceparent` để truyền trace context qua các ranh giới dịch vụ. Header có cấu trúc gồm version, trace-id, parent-id và trace-flags. Trong hệ thống production, nên để OpenTelemetry/Micrometer Tracing và instrumentation của framework/client/broker quản lý việc tạo và truyền context.

Không tự tạo `traceparent` tùy ý hoặc chỉ sao chép trace ID mà bỏ parent/span semantics. Khi consumer bắt đầu xử lý message, instrumentation có thể tạo consumer span mới liên kết với context đã được inject. Cách nối trace phụ thuộc transport và instrumentation; message đi qua broker có thể được mô hình hóa theo producer/consumer span hoặc link tùy integration.

Trace ID phục vụ quan sát kỹ thuật, không nên là khóa nghiệp vụ, idempotency key hoặc mã định danh lâu dài của đơn hàng. Sampling, retention và backend tracing có thể khiến trace không còn tra cứu được sau một thời gian. Business ID và event ID vẫn cần tồn tại độc lập trong dữ liệu/log được phép lưu.

## 7. Quy tắc vòng đời: ID nào giữ nguyên, ID nào tạo mới?

| Tình huống | Framework message ID | Event/app message ID | Business ID | Correlation ID | Trace/span |
| --- | --- | --- | --- | --- | --- |
| Tạo message object mới cho cùng event | Có thể mới | Giữ nguyên | Giữ nguyên | Giữ nguyên nếu cùng workflow | Context được instrumentation quản lý |
| Broker redeliver cùng message logic | Không giả định ổn định | Giữ nguyên | Giữ nguyên | Giữ nguyên | Context được adapter/instrumentation khôi phục nếu hỗ trợ |
| Tạo event mới cho cùng order | Mới | Mới | Giữ nguyên orderId | Có thể giữ nếu cùng workflow | Span mới; trace theo luồng thực thi |
| Bắt đầu workflow mới cho cùng order | Mới | Mới khi có message mới | Giữ nguyên orderId | Thường tạo mới | Thường là trace mới cho request mới |
| Consumer xử lý một bước downstream | Message mới nếu tạo envelope mới | ID mới cho message/event mới | Giữ ID đối tượng liên quan | Giữ nếu cùng workflow | Span mới trong trace/context phù hợp |
| Replay lịch sử event | Message/delivery metadata có thể mới | Giữ event ID gốc | Giữ business ID gốc | Giữ metadata gốc nếu có ý nghĩa | Replay có thể chạy trong trace mới; lưu liên kết replay riêng |

Quy tắc thực tế: ID của một đối tượng nghiệp vụ giữ nguyên khi đối tượng đó vẫn là cùng một đối tượng; event ID giữ nguyên khi đó vẫn là cùng một sự kiện logic; correlation ID giữ nguyên trong workflow được định nghĩa; trace/span tuân theo vòng đời quan sát của một lần thực thi; framework/broker IDs phục vụ cơ chế kỹ thuật tương ứng.

## 8. Dùng ID để chống xử lý trùng

At-least-once delivery có thể khiến consumer nhận cùng message nhiều lần. Cách chống trùng cần dựa trên ID đại diện cho **cùng một thao tác hoặc sự kiện logic**.

### 8.1. Event consumer

Một mẫu phổ biến là inbox/dedup table có unique constraint trên `(consumer_name, event_id)`:

1. Consumer nhận event và đọc `eventId` ổn định.
2. Trong cùng transaction database, thử ghi inbox record với consumer name và event ID.
3. Nếu insert thành công, thực hiện thay đổi nghiệp vụ và commit.
4. Nếu unique constraint báo event đã xử lý, bỏ qua tác động lặp và xác nhận message theo chính sách acknowledgement.

Phải ghi inbox record và thay đổi nghiệp vụ trong cùng transaction. Nếu ghi inbox trước rồi transaction nghiệp vụ rollback, lần giao lại có thể bị bỏ qua dù tác động chưa hoàn tất. Nếu commit nghiệp vụ trước rồi mới ghi inbox, crash ở giữa có thể gây tác động lặp.

### 8.2. Command/API idempotency

Đối với thao tác do client yêu cầu, dùng idempotency key cho **ý định thực hiện thao tác**. Ví dụ, client gửi yêu cầu tạo thanh toán với `Idempotency-Key: pay-attempt-77`; nếu request bị timeout và client retry cùng key, server trả lại kết quả đã lưu thay vì tạo thêm payment.

`orderId` không luôn đủ làm idempotency key. Một đơn hàng có thể có nhiều lần thử thanh toán hợp lệ. Key nên phân biệt từng thao tác, có phạm vi theo client/tenant và được lưu trong khoảng thời gian phù hợp với chính sách retry.

### 8.3. Không dedup bằng trace ID

Trace ID thường gom nhiều operation trong cùng một request. Nếu dùng trace ID làm dedup key, các message khác nhau cùng workflow có thể bị nhầm là một message. Trace ID cũng có thể đổi khi retry ở một request mới, nên không phải khóa idempotency ổn định.

## 9. Truyền ID trong Spring Messaging

Trong Spring, payload và headers có vai trò khác nhau:

- Đặt business ID trong payload DTO/record để consumer dùng trong logic nghiệp vụ.
- Đặt `eventId`, `correlationId`, `causationId` và `schemaVersion` trong custom headers nếu chúng là metadata của envelope và adapter có thể truyền chúng.
- Framework ID và timestamp có sẵn trong `MessageHeaders`; đọc chúng qua API thay vì tự đặt custom header trùng tên.
- Trace context nên được inject/extract bởi tracing instrumentation hoặc adapter hỗ trợ chuẩn trace context.

Không đặt custom header tên `id` rồi giả định nó tương đương `MessageHeaders.ID`. Nên dùng tên có nghĩa cụ thể như `eventId`, `correlationId` hoặc `causationId` để tránh nhầm với header chuẩn của framework hoặc broker.

Khi tạo message mới, quyết định từng header:

1. Giữ `correlationId` nếu vẫn thuộc cùng workflow.
2. Tạo `eventId` mới nếu đây là event logic mới; giữ event ID cũ nếu chỉ retry/redeliver cùng event.
3. Đặt `causationId` trỏ tới message trực tiếp đã gây ra message mới.
4. Để framework tạo message ID mới cho envelope mới.
5. Để tracing instrumentation tạo span và truyền context phù hợp.

Không sao chép toàn bộ headers từ message cũ một cách máy móc. Các header nội bộ như reply channel, error channel, routing metadata hoặc transport-specific fields có thể không phù hợp khi chuyển sang destination khác.

## 10. Ví dụ Java 17 + Spring Messaging 6.2

Ví dụ tạo một message `PaymentCaptured`. Payload mang business IDs; custom headers mang event/workflow metadata; Spring tự quản lý framework message ID. `traceparent` trong ví dụ chỉ minh họa một giá trị W3C Trace Context đã được inject. Trong ứng dụng production, hãy để tracing instrumentation tạo và truyền header này.

Tạo Maven project với cấu trúc:

~~~text
message-id-demo/
  pom.xml
  src/main/java/com/example/messaging/MessageIdDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-id-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
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

`src/main/java/com/example/messaging/MessageIdDemo.java`:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public final class MessageIdDemo {
    private MessageIdDemo() {
    }

    public record PaymentCaptured(
            String paymentId,
            String orderId,
            BigDecimal amount,
            Instant capturedAt) {
    }

    public static void main(String[] args) {
        PaymentCaptured event = new PaymentCaptured(
                "PAY-9001",
                "ORD-2048",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z"));

        Message<PaymentCaptured> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", "evt-pay-9001")
                .setHeader("correlationId", "checkout-2048-run-1")
                .setHeader("causationId", "cmd-capture-9001")
                .setHeader("schemaVersion", 1)
                .setHeader("traceparent",
                        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
                .build();

        MessageHeaders headers = message.getHeaders();
        PaymentCaptured payload = message.getPayload();

        System.out.println("frameworkMessageIdPresent=" + (headers.getId() != null));
        System.out.println("eventId=" + headers.get("eventId"));
        System.out.println("paymentId=" + payload.paymentId());
        System.out.println("orderId=" + payload.orderId());
        System.out.println("correlationId=" + headers.get("correlationId"));
        System.out.println("causationId=" + headers.get("causationId"));
        System.out.println("traceparent=" + headers.get("traceparent"));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageIdDemo
~~~

Stdout:

~~~text
frameworkMessageIdPresent=true
eventId=evt-pay-9001
paymentId=PAY-9001
orderId=ORD-2048
correlationId=checkout-2048-run-1
causationId=cmd-capture-9001
traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Framework message ID không in giá trị cụ thể vì nó được framework tạo tự động và có thể khác giữa các lần chạy. Ví dụ cho thấy mỗi mã có vai trò riêng: `eventId` nhận diện sự kiện; `paymentId` và `orderId` nhận diện đối tượng nghiệp vụ; `correlationId` nhóm workflow; `causationId` chỉ message gây ra; `traceparent` mang trace context.

## 11. Logging, metrics và bảo mật

Log có cấu trúc nên ghi các ID phù hợp để điều tra:

- `eventId` hoặc `appMessageId` để tìm một message logic qua retry.
- `orderId`/`paymentId` để tìm lịch sử của đối tượng nghiệp vụ, theo chính sách quyền truy cập.
- `correlationId` để gom các bước của workflow.
- `traceId` và `spanId` để mở trace trong hệ thống observability.
- Broker partition/offset hoặc delivery metadata khi cần điều tra giao nhận.

Không nhất thiết ghi mọi ID ở mọi dòng log. Chọn tập trường nhất quán và tránh log payload nhạy cảm. Không đưa token, secret, dữ liệu cá nhân hoặc nội dung thanh toán vào header/log chỉ để tiện tìm kiếm.

Đối với metrics, tránh dùng `orderId`, `eventId`, `traceId` làm label có cardinality cao. Mỗi ID có thể tạo một time series riêng, làm hệ thống metrics tốn bộ nhớ và khó vận hành. Metrics nên dùng dimension giới hạn như service, destination, outcome, message type hoặc consumer group; dùng logs/traces để tra cứu ID cụ thể.

ID không phải bằng chứng xác thực. Một consumer không được tin `customerId`, `tenantId` hoặc routing header chỉ vì chúng nằm trong message. Xác thực nguồn gửi, quyền truy cập và quyền sở hữu đối tượng theo cơ chế bảo mật của hệ thống.

## 12. Lỗi thường gặp

- **Dùng orderId làm message ID:** nhiều event khác nhau của cùng đơn hàng bị xem là trùng.
- **Dùng framework message ID làm idempotency key:** message mới hoặc lần chuyển đổi có thể mang ID mới dù vẫn là cùng event logic.
- **Dùng trace ID làm correlation/business ID:** vòng đời tracing không đồng nhất với vòng đời nghiệp vụ.
- **Dùng correlation ID để dedup:** nhiều message hợp lệ cùng workflow bị loại nhầm.
- **Dùng Kafka offset hoặc RabbitMQ delivery tag làm ID toàn cục:** giá trị chỉ có ý nghĩa trong phạm vi broker/partition/channel tương ứng.
- **Tạo event ID mới mỗi lần retry:** consumer không nhận ra lần giao lại là cùng một event.
- **Giữ event ID cho một event mới:** hai sự kiện khác nhau bị dedup nhầm.
- **Copy toàn bộ headers khi tạo message mới:** metadata routing/reply/error hoặc ID cũ có thể bị mang sang sai ngữ cảnh.
- **Đưa business ID nhạy cảm vào log/metrics:** tăng nguy cơ lộ dữ liệu và cardinality.
- **Giả định trace context tự truyền qua mọi broker:** cần adapter và instrumentation hỗ trợ inject/extract context.

## 13. Checklist thiết kế ID cho message contract

1. Mã nào định danh message logic? Producer tạo ở thời điểm nào và có giữ nguyên qua retry/replay không?
2. Mã nào định danh đối tượng nghiệp vụ? Nó nằm trong payload và có ổn định theo vòng đời domain không?
3. Có cần `correlationId` cho một workflow dài hơn một request không?
4. Có cần `causationId` để dựng quan hệ event/command cha-con không?
5. Trace context được tạo và truyền bởi instrumentation nào? Broker adapter có inject/extract không?
6. Idempotency key có phân biệt nhiều thao tác hợp lệ trên cùng một business object không?
7. Consumer lưu dedup record trong cùng transaction với thay đổi nghiệp vụ chưa?
8. Broker delivery metadata có bị nhầm với ID ứng dụng không?
9. ID nào được phép ghi log, metric hoặc hiển thị cho người dùng?
10. Quy tắc tạo mới/giữ nguyên từng ID đã được ghi trong message contract chưa?

## 14. Ghi nhớ

Framework message ID nhận diện envelope/message object do Spring quản lý; application message ID hoặc event ID nhận diện một message logic và phải ổn định khi retry cùng message; business ID nhận diện đối tượng domain và có thể xuất hiện trong nhiều event; correlation ID nhóm các bước trong workflow; causation ID chỉ message trực tiếp tạo ra message hiện tại; trace ID/span ID phục vụ quan sát một lần thực thi phân tán; broker offset/delivery tag chỉ phục vụ giao nhận trong phạm vi broker. Hãy chọn ID theo đúng câu hỏi cần trả lời, quy định vòng đời của nó và truyền qua payload/header một cách nhất quán. Đừng dùng một loại ID thay cho tất cả.