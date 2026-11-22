# Propagation qua message trong Java Trace Context

**Propagation qua message** (*message context propagation*) là quá trình **đưa trace context của producer vào metadata của message** khi gửi qua broker, sau đó **khôi phục context đó tại consumer**. Nhờ vậy, hệ thống quan sát có thể liên kết các thao tác ở nhiều service, nhiều JVM, những thread khác nhau và những thời điểm xử lý khác nhau.

Trong Java, một giải pháp thông dụng là sử dụng **OpenTelemetry (OTel)** với chuẩn **W3C Trace Context**. Thư viện **TextMapPropagator** chuyển thông tin tracing thành các cặp key–value như **traceparent** và **tracestate**, ghi vào message headers, rồi giải mã khi consumer nhận.

**Cần phân biệt:** *propagation* chỉ nói về việc truyền ngữ cảnh. Nó không tự bảo đảm broker đã nhận message, không bảo đảm event được xử lý đúng một lần, không tự làm mọi dòng log có trace ID và cũng không bảo đảm span đã được export đến tracing backend.

## 1. Vì sao cần truyền trace context qua message?

Ở luồng đồng bộ, ứng dụng Java có thể giữ current Context trong phạm vi một lời gọi:

~~~text
HTTP request
  -> Server span
      -> Service span
          -> Repository span
~~~

Nhưng với giao tiếp bất đồng bộ:

~~~text
JVM A / producer               Message broker                JVM B / consumer
+---------------------+      +----------------------+     +----------------------+
| HTTP / work span    |      | Queue / Topic        |     | Message handler      |
| Producer span       |----->| Message body         |---->| Process span         |
| Inject trace data   |      | Trace metadata       |     | Extract trace data   |
+---------------------+      +----------------------+     +----------------------+
                                     |
                              Có thể trì hoãn,
                              retry, redelivery,
                              hoặc fan-out
~~~

ThreadLocal và OpenTelemetry Context của JVM A **không thể tự chạy xuyên network** đến JVM B. Consumer có thể làm việc sau vài giờ, khi producer span đã kết thúc.

Nếu không truyền context, tracing có thể ghi được hai phía nhưng không biết chúng có cùng nguồn. Nếu chỉ truyền **correlationId** dạng chuỗi trong payload, người vận hành có thể tìm log theo ID, nhưng tracing SDK **chưa tự biết quan hệ span**. Cần có một propagator và một carrier nhất quán.

### Lợi ích cụ thể

- Xác định request/operation nào phát sinh một message.
- Liên hệ việc publish với việc consume/process và xử lý lỗi.
- Quan sát fan-out, retry hoặc dead-letter mà không ghép log bằng thời điểm.
- Truy vấn và điều tra nguyên nhân qua nhiều service khi các spans được xuất.
- Không bắt buộc người tiêu thụ hiểu implementation tracing bên trong producer.

## 2. Trace context gồm những gì?

W3C Trace Context sử dụng hai field quan trọng:

| Field | Mục đích | Bắt buộc? |
| --- | --- | --- |
| **traceparent** | Định danh trace, định danh span phía gửi và trace flags | Cần khi truyền một trace context theo W3C |
| **tracestate** | Metadata tracing tùy chọn để các hệ tương tác | Không bắt buộc |

Giá trị traceparent minh họa:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Định dạng version 00:

~~~text
00 - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
|                    |                          |              |
version           trace-id                   parent-id     trace-flags
2 hex              32 hex                     16 hex        2 hex
~~~

- **trace-id** gồm 16 byte, được biểu diễn bằng 32 ký tự hexadecimal; toàn số 0 là không hợp lệ.
- **parent-id** gồm 8 byte, biểu diễn bằng 16 ký tự hexadecimal; toàn số 0 là không hợp lệ.
- **trace-flags** gồm 1 byte; bit sampled có thể báo ý định lấy mẫu, **không phải mệnh lệnh bắt buộc downstream lưu mọi span**.
- **tracestate** chỉ đi kèm nếu context có dữ liệu vendor-specific được cho phép.

Khi inject context của Producer span, parent-id trong traceparent mang **span ID của producer**. Ở phía consumer, context được extract đại diện một **remote SpanContext**. Nếu consumer tạo Process span mới, nó có **span ID mới**; không được dùng lại span ID của producer.

**Trace ID khác span ID.** Trace ID đại diện một trace, còn span ID đại diện một lần thực thi thao tác trong trace. Một message có message ID riêng, và message ID cũng không đồng nghĩa trace ID.

### Baggage khác trace context

W3C **Baggage** có thể truyền các cặp key–value bổ sung qua service boundaries. Nó không cần thiết để chỉ nối trace ID. Baggage có thể bị lan truyền qua nhiều hệ thống và tăng kích thước message headers; tuyệt đối không cho password, access token, email cá nhân hay thông tin thanh toán vào baggage nếu không có chính sách cho phép cụ thể.

## 3. Chọn carrier: metadata, không phải Java object

Một message thường có cấu trúc:

~~~text
Message
├── Headers / Properties
│   ├── traceparent = "00-...-...-01"
│   ├── tracestate  = "..."         (tùy chọn)
│   ├── messageId   = "msg-42"
│   └── contentType = "application/json"
└── Body
    └── {"orderId":"ord-7","event":"order_created"}
~~~

**Không serialize nguyên đối tượng java Span, Context hoặc Scope thành payload.** Những đối tượng đó thuộc process và thư viện Java. Chỉ nên chuyển **dạng truyền tải** do propagator hỗ trợ.

Ưu tiên đặt vào **headers/properties**, bởi:

1. Consumer không cần parse toàn bộ JSON body để lấy trace context.
2. Có thể đổi schema nghiệp vụ độc lập với tracing.
3. Broker/adapter có thể chuyển tiếp metadata theo contract.
4. Dữ liệu nghiệp vụ và thông tin quan sát có lifecycle, quyền truy cập khác nhau.

Nếu transport không có headers, có thể thiết kế envelope chứa một phần **metadata** riêng trong payload, với schema/version rõ ràng. Khi đó cả producer và consumer phải thống nhất nơi đọc/ghi; một propagator cấu hình cho broker headers sẽ không tự biết field custom trong JSON.

## 4. Vòng đời message: inject, publish, receive, extract, process

~~~text
PRODUCER
  Tạo/get current Context
           |
           v
  Tạo span Create/Send khi cần
           |
           v
  propagator.inject(context, carrier, setter)
           |
           v
  Gửi message kèm headers
           |
           v
        BROKER
  Lưu/chuyển metadata
           |
           v
       CONSUMER
  Lấy message, headers
           |
           v
  propagator.extract(root, carrier, getter)
           |
           v
  Lấy remote SpanContext nếu hợp lệ
           |
           v
  Chọn parent hoặc span links
           |
           v
  Tạo Process/Receive span
           |
           v
  Xử lý, ghi log, ack/nack
           |
           v
  End span, đóng Scope
~~~

Trong OpenTelemetry Java, API cốt lõi là:

~~~java
// Pseudocode; propagator, carrier, setter, getter và context được tạo trước.
propagator.inject(context, carrier, setter);
Context recovered = propagator.extract(Context.root(), carrier, getter);
~~~

**TextMapSetter** biết cách đặt key/value vào loại carrier thực tế. **TextMapGetter** biết cách lấy key/value. **TextMapPropagator** chịu trách nhiệm chuẩn tracing; không nên tự ghép chuỗi traceparent bằng các thao tác substring để thay thế nó.

Giao thức có thể chuyển một giá trị header qua nhiều lớp; hãy kiểm tra broker có giữ nguyên, chuẩn hóa hay loại bỏ metadata không. Việc producer tạo header không tự chứng minh consumer đã nhận nó.

## 5. Hai cách liên kết consumer với producer: parent và span link

Đây là điểm dễ gây nhầm nhất.

Trong HTTP đồng bộ, quan hệ parent–child thường diễn tả một chuỗi lời gọi. Messaging phức tạp hơn: một message có thể được phát cho nhiều subscriber, được xử lý lại nhiều lần, nằm trong batch hoặc được xử lý dưới một HTTP span đã tồn tại.

**Theo OpenTelemetry Messaging Semantic Conventions, span links là cách liên kết mặc định** giữa message creation context và các span Receive/Process. Links biểu diễn quan hệ nhân quả mà không ép mọi message vào một cây parent–child.

**Ngoại lệ:** đối với một message riêng lẻ, khi phù hợp với luồng hoạt động, Process span có thể dùng message creation context làm parent. Instrumentation cần xác định rõ lựa chọn này; không áp dụng parent–child một cách máy móc khi có nhiều nguồn.

| Trường hợp | Cách thường phù hợp | Vì sao |
| --- | --- | --- |
| Một message, một Process span, không có parent ambient cạnh tranh | Có thể dùng parent–child | Mô hình nhân quả đơn giản |
| Batch nhận nhiều message khác trace | Span links | Một span chỉ có một parent |
| Fan-out tới nhiều consumer | Span links | Các nhánh xử lý độc lập |
| Consumer đang ở trong HTTP SERVER span | Giữ parent ambient, link tới message creation context | Bảo toàn cả hai nguồn |
| Retry/redelivery/delay dài | Links thường thuận lợi | Có nhiều lần thực thi trên một message |
| SDK/agent có sẵn instrumentation | Theo semantic conventions của instrumentation | Tránh cấu trúc trace không nhất quán |

**Hệ quả quan trọng:** nếu dùng **span link**, consumer Process span **không nhất thiết có cùng trace ID** với producer. Sự liên hệ được thể hiện qua link. Do đó không dùng điều kiện “trace ID phải giống” làm tiêu chí thành công cho mọi hệ messaging.

Ví dụ runnable ở phần dưới **chọn parent–child cho một message duy nhất** để cho thấy remote parent được khôi phục như thế nào. Đó là ví dụ học tập cụ thể, **không phải khuyến nghị mặc định cho tất cả queue/batch**.

## 6. Các thành phần OpenTelemetry Java cần hiểu

| API/khái niệm | Vai trò |
| --- | --- |
| **Tracer** | Tạo span theo tên thao tác |
| **Span** | Một lần thực thi, có SpanContext và trạng thái |
| **SpanContext** | Trace ID, span ID, flags và tracestate |
| **Context** | Container ngữ cảnh trong Java, có thể giữ Span |
| **Scope** | Gắn Context/Span thành current trong khoảng xử lý |
| **TextMapPropagator** | Inject/extract metadata qua carrier |
| **TextMapSetter / TextMapGetter** | Adapter ghi/đọc metadata theo loại broker |
| **W3CTraceContextPropagator** | Triển khai format W3C traceparent/tracestate |
| **SpanKind.PRODUCER** | Một thao tác gửi/tạo message |
| **SpanKind.CONSUMER** | Một thao tác xử lý message |
| **SdkTracerProvider** | Tạo span trong SDK; chưa đồng nghĩa đã export |

Trong Java, **Span.fromContext(context)** dùng để lấy Span từ một Context đã có. **Span.current()** lấy span trong scope hiện hành. Hai thao tác khác nhau: một Context **đã extract** không tự trở thành current của thread trừ khi được attach hoặc dùng làm parent để tạo/activate span phù hợp.

## 7. Ví dụ Java 17+ hoàn chỉnh: propagation bằng message giả lập

Ví dụ này dùng **JDK 17+, Maven và OpenTelemetry SDK 1.45.0**. Thay vì cần chạy Kafka/RabbitMQ, ta biểu diễn một message bằng record gồm map headers và body. Nhờ vậy tập trung vào **inject/extract**, remote parent, Process span, scope và cách xử lý một traceparent không hợp lệ.

### 7.1. Cấu trúc dự án

~~~text
message-trace-propagation/
├── pom.xml
└── src/main/java/demo/MessageTraceDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
 <modelVersion>4.0.0</modelVersion>
 <groupId>demo</groupId>
 <artifactId>message-trace-propagation</artifactId>
 <version>1.0.0</version>
 <properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
 </properties>
 <dependencies>
  <dependency>
   <groupId>io.opentelemetry</groupId>
   <artifactId>opentelemetry-api</artifactId>
   <version>1.45.0</version>
  </dependency>
  <dependency>
   <groupId>io.opentelemetry</groupId>
   <artifactId>opentelemetry-context</artifactId>
   <version>1.45.0</version>
  </dependency>
  <dependency>
   <groupId>io.opentelemetry</groupId>
   <artifactId>opentelemetry-sdk</artifactId>
   <version>1.45.0</version>
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
    <version>3.5.1</version>
   </plugin>
  </plugins>
 </build>
</project>
~~~

Các version trong ví dụ đã được **biên dịch và chạy kiểm chứng**, không phải tuyên bố về phiên bản mới nhất. Trong dự án production, nên dùng dependency management/BOM phù hợp với framework đang triển khai.

### 7.3. MessageTraceDemo.java

~~~java
package demo;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import java.util.LinkedHashMap;
import java.util.Map;

public final class MessageTraceDemo {
    record Message(Map<String, String> headers, String body) {}

    private static final TextMapSetter<Map<String, String>> SETTER =
            (carrier, key, value) -> carrier.put(key, value);

    private static final TextMapGetter<Map<String, String>> GETTER =
            new TextMapGetter<>() {
                @Override
                public Iterable<String> keys(Map<String, String> carrier) {
                    return carrier.keySet();
                }
                @Override
                public String get(Map<String, String> carrier, String key) {
                    return carrier.get(key);
                }
            };

    public static void main(String[] args) {
        SdkTracerProvider provider = SdkTracerProvider.builder().build();
        OpenTelemetrySdk telemetry = OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .setPropagators(ContextPropagators.create(
                        W3CTraceContextPropagator.getInstance()))
                .build();
        try {
            Tracer tracer = telemetry.getTracer("demo-messaging");
            Span producer = tracer.spanBuilder("orders publish")
                    .setSpanKind(SpanKind.PRODUCER)
                    .startSpan();
            Map<String, String> headers = new LinkedHashMap<>();
            telemetry.getPropagators().getTextMapPropagator().inject(
                    Context.root().with(producer), headers, SETTER);
            Message message = new Message(Map.copyOf(headers), "order-7");
            String producerTraceId = producer.getSpanContext().getTraceId();
            String producerSpanId = producer.getSpanContext().getSpanId();
            producer.end();

            Context received = telemetry.getPropagators()
                    .getTextMapPropagator()
                    .extract(Context.root(), message.headers(), GETTER);
            var remoteParent = Span.fromContext(received).getSpanContext();
            Span consumer = tracer.spanBuilder("orders process")
                    .setParent(received)
                    .setSpanKind(SpanKind.CONSUMER)
                    .startSpan();
            try (Scope ignored = consumer.makeCurrent()) {
                System.out.println("headerInjected="
                        + message.headers().containsKey("traceparent"));
                System.out.println("parentRemote=" + remoteParent.isRemote());
                System.out.println("sameTrace="
                        + producerTraceId.equals(consumer.getSpanContext().getTraceId()));
                System.out.println("parentSpanMatched="
                        + producerSpanId.equals(remoteParent.getSpanId()));
                System.out.println("newConsumerSpan="
                        + !producerSpanId.equals(consumer.getSpanContext().getSpanId()));
                System.out.println("scopeTraceMatches="
                        + Span.current().getSpanContext().getTraceId()
                                .equals(producerTraceId));
                System.out.println("bodyUnchanged="
                        + "order-7".equals(message.body()));
            } finally {
                consumer.end();
            }

            Map<String, String> bad = Map.of(
                    "traceparent",
                    "00-00000000000000000000000000000000-0000000000000000-01");
            Context invalid = telemetry.getPropagators()
                    .getTextMapPropagator().extract(Context.root(), bad, GETTER);
            System.out.println("invalidRejected="
                    + !Span.fromContext(invalid).getSpanContext().isValid());
            System.out.println("contextCleared="
                    + !Span.current().getSpanContext().isValid());
        } finally {
            provider.close();
        }
    }
}
~~~

**Lưu ý:** GETTER và SETTER ở đây làm việc với **Map<String,String>**, một carrier giả lập. Message thật của Kafka, JMS, RabbitMQ có API khác. **Không được dùng lại map này nếu thư viện broker yêu cầu header values dạng byte[] hoặc properties với kiểu riêng.**

### 7.4. Biên dịch, chạy và đối chiếu output

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessageTraceDemo
~~~

**Stdout đã được kiểm chứng trên Java 17+ với OpenTelemetry 1.45.0:**

~~~text
headerInjected=true
parentRemote=true
sameTrace=true
parentSpanMatched=true
newConsumerSpan=true
scopeTraceMatches=true
bodyUnchanged=true
invalidRejected=true
contextCleared=true
~~~

Giải thích:

| Dòng kiểm tra | Ý nghĩa |
| --- | --- |
| headerInjected=true | Producer đã đưa traceparent vào headers |
| parentRemote=true | Extractor tạo SpanContext remote từ metadata nhận được |
| sameTrace=true | Với lựa chọn parent–child, consumer giữ trace ID của producer |
| parentSpanMatched=true | Span ID của remote parent đúng bằng producer span ID |
| newConsumerSpan=true | Consumer span là một span khác, không tái sử dụng span ID cũ |
| scopeTraceMatches=true | Span.current() đúng khi consumer span active |
| bodyUnchanged=true | Business payload không bị sửa bởi propagation |
| invalidRejected=true | Traceparent có trace-id/parent-id toàn 0 bị bỏ qua |
| contextCleared=true | Sau khi đóng scope, không còn span current có hiệu lực |

**Không in các ID ngẫu nhiên như một stdout cố định.** Mã kiểm tra quan hệ giữa chúng, vì trace ID/span ID do SDK tạo mới mỗi lần chạy.

Ví dụ này **không cài span processor/exporter**, nên nó **chưa gửi spans đến một tracing backend thật**. Đây là kiểm chứng trực tiếp của inject/extract, parent remote và current scope, không phải end-to-end telemetry export.

## 8. Thay Map bằng headers của Kafka, JMS hoặc RabbitMQ

Không sao chép nguyên Map demo vào mọi client. Các hệ thống messaging có carrier khác nhau:

| Hệ thống | Vị trí mang trace context | Lưu ý khi triển khai |
| --- | --- | --- |
| Kafka | Record headers | Key text, value thường dạng byte[] |
| RabbitMQ | Message properties/headers | Value có kiểu của client và protocol |
| JMS | Message string properties | API properties có quy tắc tên/kiểu |
| SQS/cloud queue | Message attributes/metadata | Có giới hạn size và số attributes |
| Custom event bus | Envelope metadata được version hóa | Hai bên phải thống nhất schema |

### Pseudocode cho Kafka

~~~text
producer:
  record = ProducerRecord(topic, body)
  inject(currentContext, record.headers, kafkaTextMapSetter)
  producer.send(record)

consumer:
  record = poll(...)
  recovered = extract(Context.root(), record.headers, kafkaTextMapGetter)
  createReceiveOrProcessSpan(recovered)
  handleBusinessData(record.value)
  ackOrCommitAccordingToPolicy
~~~

**Đây là pseudocode, không phải một chương trình Kafka hoàn chỉnh.** Một Kafka TextMapSetter cần mã hóa text header theo charset phù hợp; TextMapGetter phải giải mã và xử lý nhiều values cùng key theo policy.

Với JMS, có thể lưu traceparent bằng một string property. Với RabbitMQ, giá trị header có thể là byte array, string hoặc dạng có kiểu khác theo thư viện. **Không giả định API/binary encoding của các broker là như nhau.**

### Nếu broker không có headers?

Có thể dùng một **application envelope** đã version hóa:

~~~json
{
  "metadata": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  },
  "payload": {
    "event": "order_created",
    "orderId": "ord-7"
  }
}
~~~

Đây là **một thiết kế minh họa**, không phải field tiêu chuẩn có sẵn trong mọi messaging SDK. Khi dùng envelope, cả producer và consumer phải biết vị trí metadata; adapter của propagator cần đọc đúng nơi đó.

## 9. Producer: context nào phải được inject?

Không phải lúc nào current span cũng là một span phù hợp để đưa vào một message. Trong một HTTP request phát event:

~~~text
SERVER span: POST /orders
      |
      +-- Validate order
      |
      +-- PRODUCER span: send orders
                |
                +-- Inject creation context vào message
                |
                +-- Broker send / publish
~~~

Với một message, creation context có thể là Send span. Với batch nhiều message, một **Create span riêng cho từng message** có thể phù hợp để phân biệt nguồn, còn Send span mô tả thao tác gửi cả batch.

Để tránh lỗi:

- Inject khi có **valid context** thực sự muốn truyền.
- Không để hai interceptor/agent cùng inject hoặc ghi đè metadata khác nhau.
- Không tự tạo một trace ID tùy ý bằng string concat.
- Khi message đã chứa một creation context đã được chấp nhận, có quy tắc rõ về việc giữ lại hay thay thế.
- Không nhầm một lần inject thành bằng chứng broker đã ack.
- Khi gửi thất bại hoặc retry, tách rõ send attempt, message identity và business idempotency.

Nếu framework đã có **OpenTelemetry instrumentation** cho Kafka/RabbitMQ/JMS, nó có thể tự tạo spans và inject headers. Kiểm tra trước khi cài thêm manual tracing để tránh **duplicated spans**.

## 10. Consumer: extract và xử lý đúng context

Một khung minh họa:

~~~java
// Pseudocode trong handler: carrier/getter/propagator/tracer đã tồn tại.
Context recovered =
        propagator.extract(Context.root(), carrier, getter);
Span process = tracer.spanBuilder("process message")
        .setParent(recovered)        // Chỉ nếu parent-child phù hợp.
        .setSpanKind(SpanKind.CONSUMER)
        .startSpan();
try (Scope scope = process.makeCurrent()) {
    processBusinessMessage();
} finally {
    process.end();
}
~~~

**Đây là đoạn minh họa, không phải class độc lập.** Scope chỉ nên tồn tại trong phạm vi xử lý; đóng scope rồi mới xử lý tiếp message khác trên cùng thread.

Để dùng **span link** khi creation context được extract:

~~~java
// Fragment minh họa; cần imports SpanBuilder/SpanContext và các biến đã khai báo.
SpanContext source = Span.fromContext(recovered).getSpanContext();
SpanBuilder builder = tracer.spanBuilder("process message")
        .setSpanKind(SpanKind.CONSUMER);
if (source.isValid()) {
    builder.addLink(source);
}
Span process = builder.startSpan();
~~~

Nếu thread hiện có một span ambient phù hợp, builder có thể giữ parent ambient và thêm link. Nếu muốn root độc lập, đặt **setNoParent()** theo chủ đích. Quan hệ parent/link phải theo nghiệp vụ và messaging semantic conventions, không chỉ dựa vào việc extractor trả về một Context.

### Context ở thread khác

Mã làm việc với ExecutorService hoặc CompletableFuture cần chuyển context tường minh:

~~~java
// Fragment minh họa trong method có executor và runTask().
Context captured = Context.current();
executor.execute(() -> {
    try (Scope scope = captured.makeCurrent()) {
        runTask();
    }
});
~~~

**ThreadLocal không tự propagate qua executor hoặc service khác.** Cần cơ chế context propagation của framework hoặc capture Context theo yêu cầu. Scope phải được mở/đóng trong đúng thread thực hiện tác vụ.

Nếu thread pool tái sử dụng worker cho message tiếp theo mà Scope/MDC cũ không được đóng, các log sau có thể dính trace ID của message trước.

## 11. Retry, redelivery và dead-letter queues

Trong các hệ thống **at-least-once delivery**, một message có thể được process nhiều lần.

~~~text
Message: msg-42, creation context P
      |
      +-- Attempt 1 -> Process span C1 -> timeout
      |
      +-- Attempt 2 -> Process span C2 -> retryable failure
      |
      +-- Attempt 3 -> Process span C3 -> success
~~~

Thông thường, **mỗi attempt là một thao tác thực thi mới** nên có span mới. Không tái sử dụng cùng một Span object cho ba lần xử lý. Các Process spans có thể có **links đến cùng message creation context**, giúp điều tra dù chúng ở các trace khác nhau.

Phân biệt:

- **Producer retry:** gửi lại sau lỗi network hoặc ack không rõ ràng, có thể dẫn đến duplicate message.
- **Consumer redelivery:** nhận lại message chưa ack hoặc đã bị nack.
- **DLQ:** chuyển message sang nơi xử lý sự cố. Có thể cần một span khác và metadata giữ quan hệ nguồn.
- **Delayed processing:** consumer chạy khi producer span đã kết thúc từ lâu; span link không đòi producer vẫn active.

**Trace ID không phải idempotency key.** Một trace có thể chứa nhiều message, còn một message có thể được xử lý nhiều lần. Chống duplicate cần message ID/business key, lưu dấu xử lý và transaction đúng thiết kế.

Khi một retry được tạo thành message mới, cần định nghĩa xem nó có giữ creation context của message ban đầu hay gắn context cho thao tác republish; không ép mọi message thành một ID chỉ vì muốn bảng trace trông liền mạch.

## 12. Batch, fan-out, fan-in và links

Một batch có thể chứa nhiều message từ **nhiều trace khác nhau**:

~~~text
message A: creation context A ----\
                                   \
                                    > Batch Process span
                                   /
message B: creation context B ----/
~~~

Một span chỉ có **một parent**, nhưng có thể có nhiều **links**. Vì vậy dùng parent của message đầu tiên để đại diện cả batch dễ làm mất quan hệ còn lại.

Quy trình hợp lý:

1. Extract **riêng** context của từng message trong batch.
2. Lấy SpanContext hợp lệ cho mỗi creation source.
3. Thêm links theo mức giới hạn/tính năng SDK và mức giá trị chẩn đoán.
4. Gắn attributes như destination, messaging system, số message khi có instrumentation phù hợp.
5. Xử lý dữ liệu nghiệp vụ mà không ghép nhầm trace context của hai message.
6. Kiểm thử kết quả ở tracing backend có hỗ trợ hiển thị links.

**Fan-out:** một message tới nhiều subscriber tạo các Process spans độc lập. Chúng có thể cùng link tới creation context mà không cần quan hệ parent với nhau.

**Fan-in:** nhiều message đóng góp cho một kết quả; một Process span xử lý tổng hợp có thể link nhiều sources. Khi tạo outgoing message mới, chọn creation context theo policy, không ghi đè mọi nguồn chỉ bằng một trace ID của message đầu tiên.

## 13. Messaging spans và ý nghĩa của Receive, Process

OpenTelemetry semantic conventions phân biệt nhiều loại operation:

| Operation | Ý nghĩa | SpanKind thông dụng theo quy ước |
| --- | --- | --- |
| **create** | Tạo context cho một message | PRODUCER |
| **send** | Gửi message hoặc batch | PRODUCER nếu Send context là creation context; trường hợp khác có thể CLIENT |
| **receive** | Chủ động pull message từ broker | CLIENT |
| **process** | Xử lý message trong callback/handler | CONSUMER |
| **settle** | Ack, nack, reject hoặc settlement | CLIENT |

Ví dụ một **poll** lấy 100 Kafka records có thể có Receive span cho thao tác poll và nhiều Process spans cho các record xử lý, tùy instrumentation. Không bắt buộc một người viết ứng dụng phải tạo tất cả bằng tay.

**Đừng tạo Process span quá sớm** khi thư viện chỉ prefetch hoặc cache message mà application code chưa nhận để xử lý. Hãy đặt span đúng ranh giới thao tác được quan sát.

Ack/nack là một hành động broker riêng; có thể được mô tả bằng settlement span. Trạng thái ack không được suy ra từ việc propagation thành công.

## 14. Trace context không tự trở thành trường trong Java logs

Sau khi extract thành công, có thể vẫn thấy log:

~~~text
INFO event=message_processed messageId=msg-42
~~~

nhưng không có traceId. Lý do là **OpenTelemetry Context** và **SLF4J MDC/Logback layout** không tự động là một.

Để correlation log và trace, cần cấu hình đúng logging instrumentation/bridge hoặc encoder có khả năng lấy trace/span context. Một log JSON dự kiến có thể như:

~~~json
{
  "level": "INFO",
  "event": "message_processed",
  "messageId": "msg-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "aabbccddeeff0011"
}
~~~

Đây là **dữ liệu minh họa**, không phải output của chương trình ví dụ. Khi Process span được tạo mới, spanId trên log phải thuộc **Process span**, không phải parent-id lấy từ header.

Các cách triển khai tùy stack:

- OpenTelemetry log instrumentation tương thích.
- Logback/Log4j 2 JSON encoder với trace/span context integration.
- Middleware gắn traceId/spanId vào MDC theo policy, luôn dọn scope.
- Truyền context đúng khi xử lý bất đồng bộ để logger nhìn được span hiện hành.

Nếu Process span sử dụng **links** thay vì cùng trace với producer, hai bên không bắt buộc có cùng traceId. Một tracing backend muốn hiển thị quan hệ này cần hỗ trợ links; chỉ truy vấn cùng traceId có thể bỏ sót các spans liên quan.

## 15. Sampling, exporter và dữ liệu không xuất hiện

Traceparent có sampled flag nhưng **không cam kết toàn bộ spans phải được export**. Các tình huống:

- Consumer đã extract context nhưng tracer là no-op.
- Sampler quyết định không ghi chi tiết span.
- SdkTracerProvider được tạo nhưng **không có exporter/span processor**.
- Span chưa end hoặc process dừng trước flush.
- Collector bị lỗi network, queue đầy hoặc backend không index dữ liệu.
- UI chỉ hiển thị parent–child, không cho tra cứu span links.
- Trace quá cũ đã ra khỏi retention.

Đừng sửa bằng cách thay sampled flag của mọi message thành 01; điều đó không giải quyết config exporter và có thể làm tăng chi phí/truy vết ngoài ý muốn.

Quy trình xác minh:

1. Headers có traceparent hợp lệ?
2. Extractor có remote SpanContext hợp lệ?
3. Tracer có tạo consumer span theo đúng parent/link?
4. Span được record, end và export?
5. Collector nhận không?
6. Backend truy vấn/hiển thị đúng mối quan hệ?

Ví dụ phần 7 chỉ xác minh **ba bước đầu và cleanup**, không có exporter/collector.

## 16. Bảo mật khi nhận trace context từ message bên ngoài

Traceparent là **metadata có format**, không có chữ ký chứng minh danh tính. Một đối tác có thể tự đặt một trace ID hợp lệ, và một client có thể gửi sampled flag để cố khiến service tăng chi phí tracing.

Nguyên tắc bảo vệ:

1. Chỉ xem metadata từ nguồn/broker/gateway được xác thực là **đáng tin theo chính sách**; một traceparent đúng cú pháp vẫn có thể do người ngoài tạo.
2. Không dùng traceId/spanId để xác thực, ủy quyền hoặc cho phép đọc log nội bộ.
3. Dùng propagator chuẩn kiểm tra format; header trace-id hoặc parent-id toàn 0 là không hợp lệ.
4. Có giới hạn header size, số header, nội dung được forward và ngân sách tracing.
5. Không log nguyên header không tin cậy khi bị reject; tránh log injection và lộ secrets.
6. Không truyền token, password, PII hoặc raw payload vào baggage/tracestate.
7. Quy định trust boundary giữa các tenant, đối tác và hệ nội bộ.
8. Có policy cho header sai, mất hoặc trùng; tạo context mới nếu cần thay vì dùng ID hỏng.
9. Không coi sampled flag bên ngoài là quyền yêu cầu hệ thống lưu mọi trace.
10. Áp dụng retention, phân quyền và chính sách dữ liệu cho traces và log storage.

Ví dụ invalid:

~~~text
traceparent: 00-00000000000000000000000000000000-0000000000000000-01
~~~

Hai ID đều toàn số 0, nên extractor chuẩn không được nhận như remote parent hợp lệ. Trong bài thử, invalidRejected=true xác nhận điều đó. Khi không có valid context, consumer có thể bắt đầu một root span mới hoặc theo chính sách khác đã định, không được “sửa” ID không hợp lệ bằng cách nối chuỗi tùy ý.

## 17. Hiệu năng, kích thước message và propagation overhead

Đối với mỗi message, propagation thêm một vài header ngắn. Nhưng tổng chi phí phụ thuộc:

- Broker giới hạn số header và số byte metadata.
- Baggage/tracestate dài làm tăng payload.
- Instrumentation tạo spans trên mọi send/receive/process.
- Trace sampling và lượng exporter data.
- Buffer/queue trong SDK và collector.
- Batch kích thước rất lớn với hàng nghìn span links.
- Log JSON có traceId/spanId lặp ở mỗi event.

Không tối ưu bằng cách dùng cùng một trace ID cho mọi message không liên quan chỉ để giảm cardinality. ID có tính duy nhất giúp trace đúng; nếu volume tăng cao, hãy chọn sampler, attributes, links và retention phù hợp.

**Không biến traceId thành label metric cho mỗi request/message.** Cardinality cực cao có thể làm hệ thống metrics tăng số time series; giữ traceId trong traces/logs để tra cứu sự kiện cụ thể, dùng labels mức thấp hơn cho metrics.

## 18. Bảng lỗi và chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Producer có trace, consumer mất trace | Không inject/extract hoặc headers không tới nơi | Kiểm tra tại cả hai đầu |
| Header có traceparent nhưng remote invalid | Format, encoding hoặc all-zero IDs | Dùng propagator chuẩn, kiểm tra chính sách |
| Span consumer có sai parent | Inject context không đúng thời điểm/span | Đối chiếu producer span ID và extracted parent |
| Consumer tái sử dụng producer span ID | Reuse Span object hoặc sao chép sai ID | Tạo span mới cho thao tác mới |
| Batch chỉ liên hệ message đầu | Ép một parent cho nhiều nguồn | Thêm links cho các sources |
| Consumer chạy trong HTTP span nhưng mất quan hệ HTTP | Dùng remote parent thay ambient parent không chủ đích | Chọn ambient parent + link nguồn message |
| Retry tạo nhiều spans nhưng khó liên hệ | Không giữ creation context/metadata | Giữ message context và retry attributes |
| Không có traceId trong log Java | Thiếu MDC/encoder/instrumentation | Cấu hình log correlation |
| Có span nhưng backend không thấy | Sampling/exporter/collector/retention | Kiểm tra từng lớp |
| Header bị gộp hoặc trùng | Adapter/các lớp trung gian xử lý headers khác nhau | Xác định policy và owner |
| Scope rò vào message sau | Không close scope đúng thread | try-with-resources/finally |
| Async worker không thấy context | Không chuyển Context qua thread boundary | Capture/attach Scope riêng |
| Header bị mất khi chuyển broker | Adapter hoặc proxy không preserve metadata | Kiểm tra envelope contract |
| Nhiều spans trùng nhau | Manual tracing và auto-instrumentation cùng tạo | Tránh double instrumentation |
| Link có nhưng query theo trace ID không thấy | Linked spans ở trace khác | Dùng UI/query hỗ trợ span links |
| Baggage có PII | Truyền field không kiểm soát | Allowlist và loại dữ liệu nhạy cảm |

### Trình tự điều tra từng bước

1. Xác nhận **valid producer span** tại thời điểm publish.
2. Kiểm tra headers trước khi gọi broker send.
3. Kiểm tra raw headers mà consumer nhận được trong môi trường test.
4. Xác nhận extractor trả valid remote SpanContext.
5. Kiểm tra parent/link policy và SpanKind.
6. Kiểm tra current span trong handler và scope cleanup.
7. Với async code, kiểm tra Context propagation qua executor/callback.
8. Kiểm tra exporter/collector và sampling.
9. Kiểm tra log encoder có xuất traceId/spanId nếu cần.
10. Với retry/batch/fan-out, kiểm tra message IDs, attempt và span links.

Không gộp **lỗi propagation**, **lỗi tạo span**, **lỗi exporter** và **lỗi UI hiển thị** thành một loại “mất trace”.

## 19. Bộ kiểm thử cần có trước production

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Một message bình thường | traceparent được inject/extract đúng |
| Một consumer parent–child (khi thiết kế cho phép) | Cùng traceId, span ID mới |
| Consumer dùng span link | Link tới message creation context |
| Header bị thiếu | Không crash, chọn context mới theo policy |
| Traceparent all-zero hoặc sai cú pháp | Không chấp nhận remote context sai |
| Kafka/JMS/RabbitMQ headers | Encode/decode đúng và không bị mất |
| Hai message trong batch | Có links tới cả hai nguồn phù hợp |
| Fan-out nhiều consumers | Mỗi consumer có process span độc lập |
| Retry/redelivery | Có attempt riêng, không reuse span |
| Message vào DLQ | Giữ mối quan hệ nguồn nếu contract cho phép |
| Handler exception | Scope vẫn close, span end hợp lý |
| Thread pool reuse | Không có current context cũ ở lần tiếp theo |
| CompletableFuture hoặc reactive hop | Truyền/attach Context đúng |
| Service có auto instrumentation | Không có spans/headers trùng do manual code |
| No exporter/unsampled | Phân biệt đúng propagation và export |
| Log correlation | Trường traceId/spanId có mặt khi được cấu hình |
| Baggage không an toàn | Không lan truyền qua trust boundary |
| End-to-end backend | Xem được spans, links và kết quả truy vấn |

Cần test bằng **broker thật và agent thực tế** sau unit test carrier giả lập. Đặc biệt đối với link semantics, không chỉ so sánh traceId rồi kết luận thất bại.

## 20. Bài tập tự kiểm tra

**Bài 1.** Vì sao OpenTelemetry Context của JVM producer không tự có mặt ở JVM consumer?

**Đáp án:** Context/ThreadLocal thuộc process và thread. Broker chỉ truyền dữ liệu message; muốn consumer khôi phục trace phải inject metadata và extract.

**Bài 2.** Trong header traceparent, parent-id có phải ID của span consumer sẽ tạo không?

**Đáp án:** không. Nó biểu diễn span phía gửi; consumer tạo span ID mới và dùng nó làm parent khi thiết kế parent–child.

**Bài 3.** Một batch chứa hai message với hai trace IDs khác nhau. Một Process span có thể có hai parents không?

**Đáp án:** không. Một span chỉ có một parent; có thể thêm **span links** tới cả hai creation contexts.

**Bài 4.** Producer đã inject traceparent và consumer đã extract đúng, nhưng log không có traceId. Vì sao?

**Đáp án:** tracing context và logging MDC/encoder là các cơ chế khác nhau. Cần instrumentation/encoder để đưa trace/span ID vào log.

**Bài 5.** Một message được retry ba lần. Có nên dùng lại cùng một Span object cho cả ba lần không?

**Đáp án:** không. Mỗi processing attempt là một lần thực thi riêng, nên có span riêng; các spans có thể link cùng creation context.

**Bài 6.** Trace parent có sampled flag 01 nhưng backend không thấy span. Có phải propagation sai?

**Đáp án:** chưa chắc. Còn sampler, SDK, exporter, collector, flush và retention. Bit sampled không cam kết export.

**Bài 7.** Consumer Process span link đến producer span nhưng traceId khác. Có phải lỗi?

**Đáp án:** không nhất thiết. Span links có thể nối hai traces khác nhau; cần xem links trong backend.

**Bài 8.** Message chứa traceparent hợp lệ do đối tác bên ngoài gửi. Có được dùng traceId để xác thực đối tác không?

**Đáp án:** không. Header tracing không phải chứng thực danh tính. Authentication/authorization phải có cơ chế riêng.

## 21. Checklist triển khai propagation qua message

- [ ] Chọn chuẩn context propagation chung (thường là W3C Trace Context).
- [ ] Đọc/ghi traceparent và tracestate qua metadata của message.
- [ ] Có carrier adapter đúng API và encoding của broker.
- [ ] Không serialize nguyên Span/Context Java vào business payload.
- [ ] Chọn creation context chính xác khi publish.
- [ ] Kiểm tra auto instrumentation trước khi bổ sung thủ công.
- [ ] Tuân theo messaging span semantics: links là lựa chọn mặc định; parent–child khi phù hợp.
- [ ] Xử lý batch/fan-in/fan-out bằng links theo nhu cầu.
- [ ] Mỗi consumer processing attempt có span riêng.
- [ ] Scope attach/close đúng vòng đời, kể cả exception.
- [ ] Propagate Context khi qua thread pool/async boundary.
- [ ] Không dùng traceId làm message ID, idempotency key hay auth token.
- [ ] Không đưa secrets/PII vào baggage/tracestate.
- [ ] Có policy header sai/trùng/không đáng tin và giới hạn kích thước.
- [ ] Kiểm tra sampler, SDK exporter, collector và trace backend.
- [ ] Cấu hình log correlation nếu muốn thấy traceId/spanId trong Java logs.
- [ ] Test retry, DLQ, batch, fan-out, shutdown và thread reuse.
- [ ] Xác nhận đúng message được publish/ack; propagation không thay business semantics.
- [ ] Kiểm chứng quan hệ spans hoặc links ở hệ thống tracing cuối cùng.

## 22. Tài liệu tham khảo

- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent, tracestate, format và quy tắc hợp lệ.
- [OpenTelemetry Messaging Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/): message creation context, links, Create/Send/Receive/Process/Settle.
- [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): chuyển context qua service boundaries.
- [OpenTelemetry Java API](https://opentelemetry.io/docs/languages/java/api/): Tracer, Span, Context và Scope.
- [W3C Baggage](https://www.w3.org/TR/baggage/): quy ước các trường context bổ sung.

**Kết luận:** Propagation qua message là **inject context từ producer vào message metadata, rồi extract ở consumer để tạo quan hệ tracing đúng**. Điều này đặc biệt quan trọng khi broker khiến thời điểm, JVM và thread của các bước xử lý tách rời. Trong Java, dùng OpenTelemetry propagator và adapter phù hợp, **không tự ghép traceparent**, lựa chọn **span links hoặc parent–child theo messaging semantics**, dọn Scope đúng lúc, và kiểm chứng toàn tuyến từ headers đến backend. Propagation giúp quan sát quan hệ nhân quả; nó không thay thế idempotency, authorization hay trách nhiệm giao nhận message.