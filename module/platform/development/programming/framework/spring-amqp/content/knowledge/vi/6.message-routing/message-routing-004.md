# HeadersExchange và điều kiện x-match

Trong **Spring AMQP**, `DirectExchange` định tuyến theo routing key chính xác, `TopicExchange` sử dụng mẫu routing key, còn **`HeadersExchange` chọn queue dựa trên thuộc tính (headers) của AMQP message**. Cách này hữu ích khi một thông điệp cần được phân loại đồng thời theo nhiều tiêu chí, chẳng hạn định dạng tài liệu, quốc gia, mức ưu tiên hoặc nhóm khách hàng. Tham số **`x-match`** trong binding quyết định các điều kiện cần khớp **tất cả (`all`)** hay chỉ cần khớp **ít nhất một (`any`)**.

Bài thuộc chương **Định tuyến thông điệp** của module **SPRING_AMQP**. Bạn sẽ khai báo exchange, queue và binding, gửi message qua `RabbitTemplate`, nhận bằng `@RabbitListener`, dự đoán đường đi và quan sát kết quả. Phần cuối liên hệ định tuyến với xác nhận giao nhận, retry, dead-letter, giao dịch và giám sát để tránh hiểu sai mức độ tin cậy của hệ thống bất đồng bộ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích việc `HeadersExchange` đọc **AMQP message headers** thay vì routing key hoặc nội dung JSON.
- Phân biệt ý nghĩa của binding argument **`x-match: all`** và **`x-match: any`**.
- Khai báo hai dạng binding bằng `BindingBuilder` trong Spring AMQP.
- Dùng `RabbitTemplate.convertAndSend` để gửi message có headers và dùng `@RabbitListener` xử lý từ các queue.
- Xác định khi nào một message tới không queue nào, một queue hoặc nhiều queue.
- Chẩn đoán sai tên header, thiếu header, sai kiểu giá trị, sai vhost và lỗi không định tuyến được.

## 2. Các thành phần tham gia định tuyến theo headers

AMQP message có **body** (nội dung) và **properties** (thuộc tính). Trong properties có bảng **headers** gồm các cặp tên–giá trị do producer gắn khi gửi. Ví dụ:

~~~text
Body: "ORD-1001"
Message properties:
  headers:
    format       = "pdf"
    country      = "VN"
    priority     = "HIGH"
    customerTier = "VIP"
~~~

Các headers này **không phải trường trong JSON body**. Nếu body chứa chuỗi JSON với trường `country` nhưng phần AMQP headers không có `country`, broker không tự phân tích body để khớp điều kiện của `HeadersExchange`.

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] -->|"Body + AMQP headers"| E["HeadersExchange<br/>orders.by-header"]
    E -->|"x-match=all<br/>format=pdf AND country=VN"| Q1["orders.pdf-vn"]
    E -->|"x-match=any<br/>priority=HIGH OR customerTier=VIP"| Q2["orders.important"]
    Q1 --> L1["@RabbitListener PDF"]
    Q2 --> L2["@RabbitListener quan trọng"]
~~~

| Thành phần | Vai trò |
|---|---|
| **Producer** | Gửi body và headers vào exchange qua `RabbitTemplate` |
| **Headers exchange** | So khớp headers của message với các binding |
| **Binding** | Liên kết exchange đến queue kèm điều kiện header |
| **`x-match`** | Binding argument xác định chế độ so khớp `all` hoặc `any` |
| **Queue** | Chứa bản sao message được định tuyến đến nó |
| **Consumer** | Đọc và xử lý message từ queue, thường qua `@RabbitListener` |

**Hai điều rất quan trọng:** thứ nhất, **`x-match` nằm trong binding**, không phải header producer bắt buộc gửi. Thứ hai, **routing key bị bỏ qua khi định tuyến bằng headers exchange**; đổi routing key không làm thay đổi kết quả nếu headers và binding giữ nguyên.

## 3. Cơ chế `x-match`: `all` so với `any`

### 3.1. `x-match: all` — mọi điều kiện đều đúng

Giả sử binding của queue `orders.pdf-vn` là:

~~~yaml
x-match: all
format: pdf
country: VN
~~~

Điều kiện tương đương biểu thức:

~~~text
match = (headers["format"] == "pdf")
    AND (headers["country"] == "VN")
~~~

| Headers của message | Khớp `all`? | Vì sao |
|---|---|---|
| `format=pdf`, `country=VN` | Có | Cả hai đều đúng |
| `format=pdf`, `country=SG` | Không | Sai `country` |
| `format=pdf`, thiếu `country` | Không | Thiếu một điều kiện |
| `format=png`, `country=VN` | Không | Sai `format` |
| `format=pdf`, `country=VN`, `source=web` | Có | Header thêm không ảnh hưởng hai điều kiện đã khớp |

### 3.2. `x-match: any` — ít nhất một điều kiện đúng

Giả sử binding của queue `orders.important` là:

~~~yaml
x-match: any
priority: HIGH
customerTier: VIP
~~~

Biểu thức tương ứng:

~~~text
match = (headers["priority"] == "HIGH")
     OR (headers["customerTier"] == "VIP")
~~~

| Headers của message | Khớp `any`? | Vì sao |
|---|---|---|
| `priority=HIGH`, `customerTier=STANDARD` | Có | Điều kiện thứ nhất đúng |
| `priority=LOW`, `customerTier=VIP` | Có | Điều kiện thứ hai đúng |
| `priority=HIGH`, `customerTier=VIP` | Có | Cả hai đều đúng |
| `priority=LOW`, `customerTier=STANDARD` | Không | Không điều kiện nào đúng |
| Thiếu cả hai header | Không | Không có điều kiện được đáp ứng |

### 3.3. So khớp giá trị và sự tồn tại

- **Tên header phải đúng:** `customerTier` và `customer_tier` là hai khóa khác nhau. Đặt quy ước tên từ đầu để producer và consumer thống nhất.
- **Giá trị phải tương thích về nội dung và kiểu:** chuỗi `"10"` không nên coi là tương đương số `10`; `"VIP"` và `"vip"` khác nhau. Khi nhiều ngôn ngữ cùng publish, cần chuẩn hóa kiểu AMQP field table.
- **Header thiếu không thỏa phép so khớp bằng giá trị.** Kiểm tra header *có tồn tại* là loại điều kiện riêng; Spring AMQP cũng hỗ trợ cách khai báo như `where("region").exists()`.
- **Không so sánh dữ liệu trong body:** `HeadersExchange` không tự đọc `order.country` trong JSON.
- **Không biểu diễn phép lớn hơn, regex hay điều kiện JSON phức tạp** bằng `all`/`any`; những quy tắc đó nên đặt trong ứng dụng hoặc dùng một mô hình định tuyến phù hợp hơn.
- **Tránh dùng tiền tố `x-` cho headers nghiệp vụ** khi chưa nắm quy ước của broker. `x-match` là khóa điều khiển dành cho binding.

Với logic như `(A AND B) OR (C AND D)`, bạn có thể tạo hai **binding `all`** từ cùng exchange đến cùng queue. Các binding được xét độc lập; chỉ cần một binding khớp là queue nhận message. Nếu cả hai cùng khớp, một lần publish vẫn chỉ sinh **một bản sao cho queue đó**.

## 4. Ví dụ Spring AMQP: phân loại đơn hàng

Ví dụ dùng ứng dụng Spring Boot đã kết nối RabbitMQ. Với dự án Maven quản lý dependency qua Spring Boot, cần starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Cấu hình minh họa trong `application.yml`:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: lab
    password: lab123456
    listener:
      simple:
        acknowledge-mode: auto
~~~

Thay thông tin xác thực bằng môi trường của bạn. RabbitMQ phải đang chạy; tài khoản cần quyền khai báo, gửi và nhận trên đúng vhost. Ví dụ không yêu cầu cấu hình JSON converter vì body là một chuỗi.

### 4.1. Khai báo exchange, queue và binding

Yêu cầu:

- Queue **`orders.pdf-vn`** chỉ nhận đơn có `format=pdf` **và** `country=VN`.
- Queue **`orders.important`** nhận đơn có `priority=HIGH` **hoặc** `customerTier=VIP`.

~~~java
import java.util.Map;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.HeadersExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderHeadersConfig {

    @Bean
    HeadersExchange orderHeadersExchange() {
        return new HeadersExchange("orders.by-header", true, false);
    }

    @Bean
    Queue pdfVnQueue() {
        return QueueBuilder.durable("orders.pdf-vn").build();
    }

    @Bean
    Queue importantQueue() {
        return QueueBuilder.durable("orders.important").build();
    }

    @Bean
    Binding pdfVnBinding(Queue pdfVnQueue,
                         HeadersExchange orderHeadersExchange) {
        return BindingBuilder.bind(pdfVnQueue)
                .to(orderHeadersExchange)
                .whereAll(Map.of("format", "pdf", "country", "VN"))
                .match();
    }

    @Bean
    Binding importantBinding(Queue importantQueue,
                             HeadersExchange orderHeadersExchange) {
        return BindingBuilder.bind(importantQueue)
                .to(orderHeadersExchange)
                .whereAny(Map.of("priority", "HIGH", "customerTier", "VIP"))
                .match();
    }
}
~~~

Hai lời gọi `whereAll(...).match()` và `whereAny(...).match()` tạo bindings có ý nghĩa:

~~~text
Exchange orders.by-header, type=headers
  -> orders.pdf-vn
     binding arguments: x-match=all, format=pdf, country=VN

  -> orders.important
     binding arguments: x-match=any, priority=HIGH, customerTier=VIP
~~~

`QueueBuilder.durable(...)` tạo queue durable. `HeadersExchange(..., true, false)` tạo exchange durable và không tự xóa. Spring AMQP có thể khai báo các bean này lên broker thông qua `RabbitAdmin` khi ứng dụng kết nối. Nếu broker đã có exchange cùng tên nhưng **khác loại** (ví dụ direct), việc khai báo sẽ thất bại; cần kiểm tra cấu hình hạ tầng trước.

### 4.2. Producer gửi headers bằng `RabbitTemplate`

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderHeadersPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderHeadersPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String orderId,
                        String format,
                        String country,
                        String priority,
                        String customerTier) {
        rabbitTemplate.convertAndSend(
                "orders.by-header",
                "", // Routing key không dùng để định tuyến headers exchange.
                orderId,
                message -> {
                    var props = message.getMessageProperties();
                    props.setHeader("format", format);
                    props.setHeader("country", country);
                    props.setHeader("priority", priority);
                    props.setHeader("customerTier", customerTier);
                    return message;
                });
    }
}
~~~

`convertAndSend(exchange, routingKey, body, messagePostProcessor)` chuyển body thành AMQP message rồi cho phép bổ sung các headers trước khi publish. Ở đây `""` chỉ là routing key rỗng minh họa. Thay nó bằng một chuỗi khác **không làm thay đổi kết quả định tuyến của headers exchange**.

Để phát bốn message mẫu, có thể dùng `CommandLineRunner` **chỉ trong môi trường lab**:

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderHeadersDemoRunner {

    @Bean
    CommandLineRunner publishDemo(OrderHeadersPublisher publisher) {
        return args -> {
            publisher.publish("ORD-1001", "pdf",  "VN", "LOW",  "STANDARD");
            publisher.publish("ORD-1002", "json", "VN", "HIGH", "STANDARD");
            publisher.publish("ORD-1003", "pdf",  "VN", "HIGH", "VIP");
            publisher.publish("ORD-1004", "pdf",  "SG", "LOW",  "STANDARD");
        };
    }
}
~~~

Vì runner gửi khi ứng dụng khởi động, mỗi lần restart sẽ phát lại các message đó. Khi hết thực hành cần bỏ hoặc tắt runner, thay bằng tác vụ publish theo hành động nghiệp vụ thật.

### 4.3. Consumer nhận từ hai queue

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderHeadersListeners {
    private static final Logger log =
            LoggerFactory.getLogger(OrderHeadersListeners.class);

    @RabbitListener(queues = "orders.pdf-vn")
    public void onPdfVn(String orderId,
                        @Header("format") String format,
                        @Header("country") String country) {
        log.info("PDF_VN order={} format={} country={}",
                orderId, format, country);
    }

    @RabbitListener(queues = "orders.important")
    public void onImportant(String orderId) {
        log.info("IMPORTANT order={}", orderId);
    }
}
~~~

Hai listener xử lý hai luồng công việc độc lập. Trong chế độ `acknowledge-mode: auto` của **Spring AMQP listener container**, thông thường message được ack sau khi phương thức listener chạy thành công. **Đây không phải** chế độ RabbitMQ broker auto-ack ngay khi giao message; nếu listener ném exception, hành vi reject/requeue/retry cần kiểm tra cấu hình.

## 5. Bảng kết quả định tuyến

Với các binding đã cấu hình:

| Message | format | country | priority | customerTier | `orders.pdf-vn` (`all`) | `orders.important` (`any`) |
|---|---|---|---|---|---|---|
| ORD-1001 | pdf | VN | LOW | STANDARD | **Có** | Không |
| ORD-1002 | json | VN | HIGH | STANDARD | Không | **Có** |
| ORD-1003 | pdf | VN | HIGH | VIP | **Có** | **Có** |
| ORD-1004 | pdf | SG | LOW | STANDARD | Không | Không |
| ORD-1005 | pdf | VN | LOW | VIP | **Có** | **Có** |
| ORD-1006 | pdf | vn | LOW | STANDARD | Không | Không |

Giải thích:

1. **ORD-1001:** đúng `format=pdf` **và** `country=VN`, nên tới queue PDF-VN.
2. **ORD-1002:** không phải PDF nhưng có `priority=HIGH`, nên tới queue quan trọng.
3. **ORD-1003:** thỏa cả `all` và `any`, nên **mỗi queue** nhận một bản sao.
4. **ORD-1004:** sai điều kiện `country` và không có HIGH/VIP, nên không tới hai queue trên.
5. **ORD-1005:** `priority=LOW` nhưng `customerTier=VIP` vẫn đủ cho `any`.
6. **ORD-1006:** `"vn"` khác `"VN"`, cần chuẩn hóa giá trị nếu nghiệp vụ không phân biệt chữ hoa/chữ thường.

**Phân biệt hai kiểu nhân bản:** hai **queue khác nhau** có binding cùng khớp thì mỗi queue nhận một bản sao. Hai **consumer dùng chung một queue** thường chia nhau message, không phải consumer nào cũng nhận từng message. Hai **binding cùng trỏ vào một queue** cùng khớp cũng không khiến một message bị nhân đôi trong queue đó.

## 6. Kết hợp nhiều điều kiện phức tạp

Giả sử cần queue `orders.special` nhận đơn:

~~~text
(format=pdf AND country=VN)
         OR
(priority=HIGH AND customerTier=VIP)
~~~

Không thể biểu diễn nguyên vẹn phép toán trên bằng một binding `x-match=any` vì `any` là OR giữa **từng** điều kiện. Thay vào đó, tạo **hai binding `all` cùng trỏ đến `orders.special`**:

~~~java
@Bean
Binding specialForPdfVn(Queue specialQueue, HeadersExchange orderHeadersExchange) {
    return BindingBuilder.bind(specialQueue)
            .to(orderHeadersExchange)
            .whereAll(Map.of("format", "pdf", "country", "VN"))
            .match();
}

@Bean
Binding specialForHighVip(Queue specialQueue, HeadersExchange orderHeadersExchange) {
    return BindingBuilder.bind(specialQueue)
            .to(orderHeadersExchange)
            .whereAll(Map.of("priority", "HIGH", "customerTier", "VIP"))
            .match();
}
~~~

Trong ví dụ mở rộng, cần khai báo thêm bean `specialQueue` tương ứng, như `QueueBuilder.durable("orders.special").build()`. Việc một message khớp cả hai binding không tạo hai bản sao trong cùng queue.

Nếu cần điều kiện phức tạp hơn (so sánh số học, tham chiếu dữ liệu DB, hoặc các nhóm AND/OR lồng sâu), hãy xem xét lọc ở tầng ứng dụng hoặc thiết kế lại message contract, thay vì biến exchange thành một bộ máy quy tắc nghiệp vụ.

## 7. Quan sát trên RabbitMQ Management

Với RabbitMQ Management plugin đã bật (thường truy cập ở `http://localhost:15672`), có thể kiểm chứng như sau:

1. Khởi động RabbitMQ và Spring Boot; đảm bảo ứng dụng khai báo các queue, exchange và binding thành công.
2. Mở **Exchanges → orders.by-header**; xác nhận loại exchange là **headers**.
3. Trong phần bindings, kiểm tra `orders.pdf-vn` có `x-match=all`, `format=pdf`, `country=VN`; còn `orders.important` có `x-match=any`, `priority=HIGH`, `customerTier=VIP`.
4. Mở **Queues and Streams** (hoặc **Queues**) để xem hai queue. Khi consumer hoạt động, thông điệp có thể được xử lý và ack trước khi giao diện kịp refresh.
5. Đọc log của hai listener khi runner gửi bốn message. Kết quả kỳ vọng: 1001 xuất hiện ở PDF_VN; 1002 ở IMPORTANT; 1003 ở cả hai; 1004 không xuất hiện ở hai listener.
6. Nếu cần nhìn số message đang chờ, hãy dừng **consumer** nhưng giữ **producer và RabbitMQ** hoạt động, gửi lại message, rồi xem chỉ số Ready của từng queue. Với ứng dụng mẫu dùng chung runner/listener, cần tách thành hai ứng dụng hoặc điều khiển listener riêng; tắt toàn bộ ứng dụng đồng thời tắt cả producer.

| Chỉ số | Ý nghĩa trong queue |
|---|---|
| **Ready** | Message đang chờ giao cho consumer |
| **Unacked** | Message đã giao nhưng broker chưa nhận ack |
| **Total** | Tổng Ready và Unacked tại thời điểm thống kê |
| **Consumers** | Số consumer đang đăng ký với queue |

Management không lưu lại tất cả message từng được xử lý; message đã ack thường không còn trong queue. Chức năng **Get messages** có thể làm thay đổi trạng thái/ack message tùy thiết lập, nên ưu tiên xem số liệu và log khi chỉ cần quan sát.

## 8. Các lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Không message nào được định tuyến | Headers của message không khớp binding | Xem lại tất cả cặp key/value và `x-match` |
| `all` luôn sai dù một header đúng | Còn điều kiện khác sai hoặc thiếu | Kiểm tra **toàn bộ** headers bắt buộc |
| `any` cho phép quá nhiều message | Một điều kiện đã đúng là đủ | Cân nhắc `all` hoặc chỉnh lại thiết kế binding |
| Đổi routing key nhưng không thay kết quả | HeadersExchange bỏ qua routing key | Đổi headers hoặc chọn direct/topic exchange phù hợp |
| Body JSON chứa trường cần lọc nhưng queue không nhận | Thiếu AMQP header tương ứng | Đặt headers qua `MessagePostProcessor` hoặc converter tương ứng |
| Có dữ liệu giống nhau nhưng vẫn không khớp | Chữ hoa/thường, kiểu số/chuỗi, mã hóa khác | Chuẩn hóa schema header, log giá trị và kiểu thực tế |
| Exchange/queue không được khai báo | Thiếu quyền, sai vhost, tên trùng nhưng loại exchange khác | Xem log startup và Management, kiểm tra resource trên đúng vhost |
| Queue có Ready nhưng không được xử lý | Không có consumer hoặc listener gặp lỗi | Kiểm tra Consumers, Connections, log và listener config |
| Message đến cả hai queue nhưng nghiệp vụ một bên chưa hoàn tất | Hai consumer xử lý độc lập | Theo dõi trạng thái xử lý từng nhánh, retry/DLQ khi cần |

### Message không định tuyến được

Nếu không có binding nào phù hợp và không cấu hình cách định tuyến khác, message có thể bị broker loại như **unroutable**. `RabbitTemplate.convertAndSend(...)` kết thúc không lỗi **không chứng minh** message đã vào queue mong muốn.

- **Publisher confirms**: xác nhận broker xử lý publication theo cơ chế confirm; không chứng minh consumer đã hoàn tất nghiệp vụ.
- **Mandatory + publisher returns**: cho producer nhận biết các message không định tuyến được trong tình huống phù hợp.
- **Consumer ack**: xác nhận việc giao message ở phía tiêu thụ theo cấu hình; không thể thay thế kết quả nghiệp vụ được ghi bền vững.

Đừng nhầm ba tín hiệu này thành một bảo đảm duy nhất.

## 9. Định tuyến và độ tin cậy của xử lý bất đồng bộ

`HeadersExchange` **chỉ giải quyết việc chọn đích**. Hệ thống Spring AMQP cần thiết kế thêm:

- **Durability / persistence:** exchange và queue durable, cơ chế lưu message bền vững, thiết lập broker phù hợp. Durable queue một mình không đảm bảo không mất mọi message.
- **Retry có giới hạn:** xử lý lỗi tạm thời của consumer mà không tạo vòng requeue vô hạn.
- **Dead-letter (DLX/DLQ):** chuyển message không xử lý được đến luồng điều tra thích hợp; đây là một topology riêng, không tự xuất hiện khi khai báo headers exchange.
- **Idempotency:** consumer cần chịu được giao lại message. Dùng `eventId` hoặc khóa nghiệp vụ để tránh xử lý trùng.
- **Giao dịch:** ghi database và publish message không tự thành một giao dịch nguyên tử; mô hình **transactional outbox** thường hữu ích.
- **Quan sát:** theo dõi publish confirms/returns, Ready/Unacked, consumer rate, DLQ, log có `eventId` và correlation ID.

Ví dụ một message được định tuyến tới hai queue: consumer PDF hoàn tất, consumer xử lý ưu tiên gặp lỗi. Việc exchange làm đúng nhiệm vụ **không đồng nghĩa toàn bộ nghiệp vụ đã thành công**. Trạng thái cuối cùng cần được theo dõi theo từng nhánh và có cách thử lại hoặc xử lý bù phù hợp.

## 10. So sánh lựa chọn exchange

| Loại exchange | Điều kiện định tuyến | Khi nên cân nhắc |
|---|---|---|
| **DirectExchange** | Routing key chính xác | Một loại sự kiện hoặc tác vụ gắn một key rõ ràng |
| **TopicExchange** | Routing key theo mẫu `*`, `#` | Cấu trúc tên sự kiện phân cấp như `order.created.eu` |
| **FanoutExchange** | Không lọc theo routing key/headers | Phát cùng sự kiện cho mọi queue bind |
| **HeadersExchange** | So khớp AMQP headers theo `all` hoặc `any` | Phân loại theo nhiều metadata độc lập |

Nếu chỉ có một key đơn giản, direct hoặc topic exchange thường dễ theo dõi hơn. Chọn headers exchange khi thông tin phục vụ định tuyến **đã tồn tại ở dạng metadata**, có quy ước tên/kiểu nhất quán và các quy tắc AND/OR đơn giản phản ánh đúng nhu cầu nghiệp vụ.

## 11. Tự kiểm tra

Cho hai binding:

~~~text
orders.pdf-vn    : all(format=pdf, country=VN)
orders.important : any(priority=HIGH, customerTier=VIP)
~~~

**Câu 1.** Message có `format=pdf`, `country=VN`, `priority=LOW`, `customerTier=VIP` đi đến queue nào?

**Đáp án:** cả hai queue. Binding `all` đúng vì format/country đều khớp; binding `any` đúng nhờ VIP.

**Câu 2.** Message có `format=pdf` và `priority=HIGH` nhưng **thiếu country** đi đến queue nào?

**Đáp án:** chỉ `orders.important`. Binding `all` không thỏa vì thiếu `country=VN`; binding `any` thỏa nhờ HIGH.

**Câu 3.** Thêm `country=VN` vào JSON body nhưng không thêm AMQP header `country` có làm binding `all` khớp không?

**Đáp án:** không. HeadersExchange đọc message headers, không đọc field trong body.

**Câu 4.** Một message khớp cả hai queue có nghĩa cả hai listener đã xử lý nghiệp vụ thành công?

**Đáp án:** không. Định tuyến tới queue, consumer ack và hoàn tất nghiệp vụ là các mốc khác nhau.

**Câu 5.** Tại sao thay routing key thành `orders.pdf` không khiến message thiếu header đi vào `orders.pdf-vn`?

**Đáp án:** headers exchange bỏ qua routing key khi chọn queue; phải khớp binding headers.

## 12. Ghi nhớ

- **`HeadersExchange`** định tuyến theo bảng **AMQP headers** và binding arguments, không đọc body JSON và không xét routing key.
- **`x-match: all` = AND**, **`x-match: any` = OR** trên các điều kiện header. Trong Spring AMQP tương ứng với `whereAll(...).match()` và `whereAny(...).match()`.
- Một message có thể tới nhiều queue nếu nhiều binding khớp; nhiều consumer trên cùng queue thường chia nhau message.
- Định tuyến đúng là một bước của hệ thống đáng tin cậy; vẫn phải thiết kế confirms/returns, ack, retry/DLQ, idempotency, giao dịch và quan sát.
