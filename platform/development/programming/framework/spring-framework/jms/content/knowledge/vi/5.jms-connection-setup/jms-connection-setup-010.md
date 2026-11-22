# Đóng tài nguyên và dừng ứng dụng có kiểm soát trong Spring JMS

> **Ngữ cảnh:** Spring Framework JMS, Jakarta Messaging (`jakarta.jms`), ứng dụng Java 17+ và Spring Boot. Mục tiêu là dừng producer/consumer đúng thứ tự, cho các tác vụ đang xử lý cơ hội hoàn tất, bảo toàn trạng thái message khi lỗi, rồi giải phóng connection/session/consumer và tài nguyên liên quan.

## 1. “Dừng ứng dụng an toàn” có nghĩa là gì?

Một tiến trình JMS thường có cả **kết nối tới broker**, **session nhận/gửi**, **producer**, **consumer**, **listener container**, luồng xử lý nghiệp vụ, và các tài nguyên khác như DB, thread pool hoặc HTTP client. Đóng socket không đồng nghĩa công việc đang chạy đã hoàn tất.

Một lần dừng có kiểm soát cần đạt đồng thời ba kết quả:

1. **Không nhận thêm công việc mới vượt quá cửa sổ shutdown cho phép.** Producer nội bộ ngừng phát sinh message; listener container ngừng nhận tiếp khi được yêu cầu dừng.
2. **Xử lý rõ ràng những message đã nhận:** hoàn tất nghiệp vụ và commit/ack, hoặc rollback/để message đủ điều kiện được giao lại. Không tuyên bố “xử lý thành công” chỉ vì method vừa chạy được một phần.
3. **Giải phóng đúng chủ sở hữu:** đóng tài nguyên do ứng dụng tự tạo; để Spring và connection-pool đóng tài nguyên do họ quản lý. Việc đóng phải diễn ra sau khi không còn tác vụ nào cần chúng.

Khái niệm **graceful shutdown** không hứa “không mất message trong mọi tình huống” hoặc “exactly once”. Nó cung cấp một khoảng thời gian để kết thúc và thu hồi tài nguyên có trật tự. Nếu bị `kill -9`, mất điện, vượt thời gian orchestrator cho phép, broker/DB ngừng trước, hoặc network partition, ứng dụng vẫn phải có **retry/redelivery và idempotency**.

### Phân biệt những động từ thường bị dùng lẫn

| Động tác | Ý nghĩa | Điều không được suy ra |
| --- | --- | --- |
| **Pause / Stop delivery** | Ngăn kết nối hoặc listener nhận thêm message trong lúc tạm dừng | Không phải đóng hẳn connection; chưa chắc commit mọi message đã nhận |
| **Finish handler** | Mã nghiệp vụ kết thúc không lỗi | Chưa chứng minh dữ liệu ngoài JVM đã commit hoặc broker đã ack |
| **Ack / Commit** | Xác nhận với broker theo acknowledge mode hoặc transaction JMS | Không tự đồng bộ với transaction của DB hoặc HTTP side effect |
| **Rollback** | Hủy tác vụ JMS chưa commit; message có thể được giao lại | Không tự hoàn tác email đã gửi hoặc database transaction đã commit |
| **Close / Destroy** | Giải phóng session, consumer, connection, pool/container | Không thay được thiết kế retry, idempotency hay quy trình thoát khỏi sự cố |

## 2. Ai sở hữu tài nguyên nào?

### 2.1. Chuỗi tài nguyên JMS

~~~text
ConnectionFactory  --create--> Connection / JMSContext
                                    |
                                    +---> Session  --create--> MessageProducer
                                    |                 \-----> MessageConsumer / Listener
                                    |
                                    +---> (shared sessions, tùy provider/pool)
~~~

**`ConnectionFactory` là factory**, không phải đối tượng kết nối đã mở trong mọi trường hợp. Có thể là factory của provider, proxy, JNDI-managed object, cache hoặc connection pool. Chính sách đóng factory/pool phụ thuộc **chủ sở hữu**, không phải chỉ dựa vào kiểu Java.

| Kiểu sử dụng | Tài nguyên được tạo/giữ bởi ai? | Ai đóng và lúc nào? |
| --- | --- | --- |
| JMS API trực tiếp `factory.createConnection()` | Mã ứng dụng tự tạo connection | Ứng dụng gọi `close()` / try-with-resources |
| JMS API trực tiếp `factory.createContext()` | Ứng dụng tạo `JMSContext` | Ứng dụng gọi `context.close()` / try-with-resources |
| `Session`, `MessageProducer`, `MessageConsumer` tự tạo | Ứng dụng tạo con của connection/session | Đóng khi không cần; đóng session/connection sẽ đóng tài nguyên con |
| `JmsTemplate` + Spring-managed `ConnectionFactory` | Spring quản lý connection/session/producers dùng trong thao tác template | Caller **không** giữ và đóng session do template cung cấp |
| `@JmsListener` | Spring tạo và quản lý listener container, session và consumer | Container/`ApplicationContext` điều phối dừng và destroy |
| `CachingConnectionFactory` / pool do container quản lý | Spring/Boot/pool giữ connection để tái sử dụng | Gọi close trên handle được mượn theo hợp đồng; **pool** bị destroy khi bean chủ sở hữu đóng |
| Broker chạy bên ngoài | Hạ tầng/bộ phận vận hành broker sở hữu | Dừng **ứng dụng** không được tùy tiện tắt broker dùng chung |

**Quy tắc đơn giản:** Ai tạo tài nguyên thực và kiểm soát vòng đời của nó thì người đó chịu trách nhiệm đóng. Khi làm việc qua proxy/pool, `close()` trên một **handle** có thể chỉ hoàn trả về cache chứ chưa hủy socket vật lý; điều này là đúng thiết kế.

### 2.2. Khi đóng cha thì điều gì xảy ra với con?

Theo Jakarta Messaging:

- `Connection.close()` đóng các `Session`, `MessageProducer`, `MessageConsumer` và browser thuộc connection. Không cần gọi đóng từng session ngay trước connection chỉ để lặp lại công việc.
- `Session.close()` đóng consumer/producer tạo từ session; connection có thể vẫn tiếp tục sống cho session khác.
- `MessageConsumer.close()` ngừng delivery đến consumer đó, **không tự commit/ack/rollback** các message đang thuộc transaction hoặc acknowledgement của session.
- `JMSContext.close()` đóng session của context và các consumer/producer thuộc context; connection bên dưới cũng được đóng khi không còn context hoạt động nào cùng dùng nó, theo cách JMSContext quản lý connection.
- Đóng đã đóng lần nữa được chuẩn yêu cầu không gây lỗi cho connection/session; tuy vậy logic shutdown nên tránh gọi nhiều nơi lặp và tránh nhầm lẫn với proxy/pool.

**Không gọi `Connection.close()` hoặc `Session.close()` của chính listener từ trong `onMessage`.** Đặc tả cho phép nhà cung cấp hoặc ném `IllegalStateException` hoặc thực hiện đóng theo cách khác; hành vi đó không portable. Với Spring, yêu cầu dừng container thông qua lifecycle từ thread quản trị/lúc context đóng.

## 3. “Stop” khác “Close” thế nào trong JMS thuần?

### 3.1. `Connection.stop()` là tạm ngừng nhận

- Sau `connection.stop()`, delivery tới các consumer của connection tạm ngừng; `connection.start()` có thể cho phép nhận tiếp.
- Một lời gọi `stop()` phải chờ các `MessageListener` **đang thực thi** trở về trước khi hoàn tất; nó có thể block khi handler kéo dài.
- Gửi message qua connection vẫn có thể được thực hiện trong trạng thái stopped; không dùng `stop` như một cơ chế chặn producer.
- Với receive đồng bộ, timer timeout vẫn chạy; `receive(timeout)` có thể trả về `null` khi hết thời gian, kể cả trong thời gian dừng.
- `stop()` **không** hủy connection/session và không tự commit hoặc rollback giao dịch.

### 3.2. `Connection.close()` là kết thúc vòng đời

- `close()` chặn cho đến khi các listener đang chạy trở về và các receive còn chờ hoàn tất theo quy tắc Jakarta Messaging; việc timeout của hệ thống vận hành cần tính tới thời gian chờ đó.
- Một `receive()` đang chờ có thể trả message hoặc `null` khi close, tùy timing; **không** dùng “nhận `null`” như tín hiệu đóng chắc chắn.
- Close trong khi có **local transacted Session chưa commit** khiến transaction đó bị rollback; không làm tương tự như `commit()`.
- Close **không tự acknowledge** message của `CLIENT_ACKNOWLEDGE`.
- Sau close, sử dụng tiếp connection/session/consumer sẽ lỗi (ngoại lệ những cách gọi close lại được chuẩn cho phép); một số `Message` đã lấy vẫn đọc được dữ liệu, nhưng `acknowledge` từ session đóng không hợp lệ.

### 3.3. Không đóng connection trong listener callback

Giả sử handler đang xử lý `OrderPlaced`, tự gọi `connection.close()`. Caller có thể bị block chờ chính callback hoàn tất hoặc nhận exception theo provider; nguy cơ tạo logic khó dự đoán và khiến acknowledgement mất ngữ cảnh. Trường hợp muốn tự tắt consumer khi nhận một “control message”, hãy **báo yêu cầu ra thread quản trị**, để Spring lifecycle hoặc coordinator riêng quyết định stop; handler nên kết thúc theo transaction đang có.

## 4. Acknowledge và transaction quyết định số phận message đang xử lý

### 4.1. Những thời điểm dễ xảy ra trùng hoặc mất

~~~text
Message nằm trong broker
    |
    v
Consumer nhận ----------------------> Đang xử lý nghiệp vụ
    |                                      |
    |                                      +--> DB commit / gọi API / ghi file
    |                                      |
    |                                      v
    |                             JMS ACK hoặc JMS COMMIT
    |                                      |
    v                                      v
Còn chưa hoàn tất                       Broker coi là hoàn tất
~~~

Có hai tình huống lỗi kinh điển:

- **Xử lý nghiệp vụ xong nhưng chưa ack/commit JMS:** ứng dụng dừng đột ngột; broker có thể giao lại cùng message. Nếu hành động là gửi email hoặc trừ tiền, cần idempotency key để không thực hiện lần nữa.
- **Đánh dấu JMS thành công trước khi tác dụng phụ hoàn tất:** lỗi sau đó có thể khiến message không được giao lại dù business side effect chưa thành công. Với một số listener container/ack mode, điều này còn xảy ra sớm hơn bạn nghĩ.

### 4.2. Ảnh hưởng của acknowledge mode

| Chế độ | Điều cần biết khi shutdown |
| --- | --- |
| `AUTO_ACKNOWLEDGE` | Cách xác nhận của API và listener container có thể khác; với `DefaultMessageListenerContainer` của Spring, thông điệp có thể được ack trước khi listener chạy, nên lỗi/stop không có redelivery đáng tin như mong đợi |
| `CLIENT_ACKNOWLEDGE` | Ứng dụng gọi acknowledge; đóng session/connection **không tự acknowledge** message còn chưa xác nhận |
| `DUPS_OK_ACKNOWLEDGE` | Có thể xác nhận trễ và phát sinh duplicate; không dùng để hứa “exactly once” |
| **Transacted JMS Session** | Commit sau khi xử lý thành công; rollback khi xử lý thất bại hoặc session bị đóng trước commit. Spring listener có thể quản lý commit/rollback cho bạn |

Với công việc queue/durable topic cần tính tin cậy, **session transacted** của listener container thường là điểm khởi đầu hợp lý. Trong Spring:

~~~java
DefaultJmsListenerContainerFactory factory = new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setSessionTransacted(true);
~~~

Đây chỉ là **mảnh cấu hình** đặt trong `@Configuration` với `@Bean`, cần import đúng package; không phải file Java độc lập. Khi dùng Spring Boot, cân nhắc dùng Boot configurer để kế thừa converter/transaction/recovery settings trước khi tinh chỉnh.

### 4.3. JMS transaction không tự bao gồm database

Trong một listener có giao dịch JMS cục bộ:

1. App lấy message trong session giao dịch.
2. Handler gọi SQL hoặc dịch vụ ngoài.
3. Spring hoặc mã xử lý commit JMS khi handler thành công.

Nếu database commit thành công nhưng JVM mất trước JMS commit, broker có thể gửi lại. Ngược lại, nếu bạn cấu hình transaction độc lập thiếu đồng bộ, cũng có thể gặp trạng thái không nhất quán.

Giải pháp thường dùng: **idempotent consumer**, inbox/dedup table theo `messageId` hoặc business ID, transactional outbox cho chiều publish, cùng chính sách retry/DLQ; XA/JTA chỉ khi thật sự cần atomically phối hợp các tài nguyên và đã đánh giá chi phí.

**Vì vậy:** graceful shutdown cho handler thời gian hoàn tất, còn **idempotency** bảo vệ những lần shutdown không thể hoàn tất.

## 5. Quy trình shutdown theo thứ tự có chủ đích

Một phương án triển khai thực tế cho service vừa nhận request HTTP vừa tiêu thụ JMS:

1. **Nhận tín hiệu dừng:** SIGTERM, `ApplicationContext.close()`, vận hành deploy/scale down hoặc lệnh quản trị. Không dùng `SIGKILL`/`kill -9` nếu có thể.
2. **Chuyển sang trạng thái draining:** readiness có thể chuyển “not ready” để hệ thống ngừng phân phối yêu cầu mới theo chính sách, nhưng vẫn để liveness phù hợp cho tiến trình hoàn tất. Readiness của Kubernetes **không tự dừng JMS listener**.
3. **Ngừng tạo việc mới:** dừng scheduler/timer/poller, chặn hoặc xử lý có kiểm soát các request mới sẽ publish JMS. Không được phá `ConnectionFactory` khi vẫn còn producer cần gửi kết quả.
4. **Yêu cầu các JMS listener container dừng nhận:** Spring `SmartLifecycle`/`JmsListenerEndpointRegistry` có thể thực hiện khi đóng ApplicationContext. Đừng mở consumer mới trong lúc ngừng.
5. **Chờ in-flight handlers** trong budget đủ dài. Handler đang chạy phải thành công và commit, hoặc ném lỗi để rollback/retry. Nếu bị interrupt, khôi phục interrupt flag và không tiếp tục làm side effect.
6. **Giải phóng thành phần sở hữu tài nguyên:** sau khi các listener đã dừng mới destroy session/consumer, cache/pool và connection do Spring quản lý. Những callback shutdown tùy biến phải xếp đúng lifecycle order.
7. **Quan sát kết quả cuối:** ghi nhận số handler hoàn tất, duration, retry/DLQ, backlog và số connection còn mở; cho process thoát trong thời gian orchestrator cho phép.
8. **Khởi động replica kế tiếp:** broker còn message chưa hoàn tất để consumer khác nhận theo ack/transaction/retention. Không coi việc replica khác chạy là bằng chứng tác vụ cũ hoàn thành.

~~~text
          SIGTERM / Context close
                    |
           [không tạo task mới]
                    |
           [stop JMS consumers]
                    |
              +-----+------+
              |            |
      [handler hoàn tất]  [handler lỗi / hết budget]
              |            |
      [JMS commit/ack]   [rollback/redelivery theo policy]
              |            |
              +-----+------+
                    |
       [destroy listener / resources]
                    |
          [pool/connection cleanup]
                    |
               JVM exit
~~~

**Thứ tự không cứng cho mọi kiến trúc.** Nếu một consumer cần **publish reply** để hoàn tất công việc, producer/connection dùng cho reply phải còn hoạt động cho tới khi consumer xử lý xong. Nếu một HTTP endpoint là upstream gửi job mới, nên chặn HTTP writes trước khi dừng consumer hoặc có contract về thời điểm bàn giao việc. Mối quan hệ phụ thuộc thực tế quyết định pha stop.

## 6. Spring JMS quản lý dừng như thế nào?

### 6.1. `JmsTemplate`

`JmsTemplate` là adapter theo thao tác: dùng `ConnectionFactory` để lấy tài nguyên theo callback/gửi/nhận, rồi trả/giải phóng chúng theo chính sách. Với `JmsTemplate.convertAndSend`, bạn không nhận `Session` để quản lý thủ công.

Không viết:

~~~java
// Không phải hướng quản lý tài nguyên hợp lý:
session = obtainSessionSomehow();
jmsTemplate.convertAndSend("orders.in", "x");
session.close(); // Session này không phải session Spring dùng để send!
~~~

Đây là **phản ví dụ minh họa**, không phải mã biên dịch độc lập. `JmsTemplate` không phải đối tượng cần gọi `close()` sau mỗi `send()`; bean Spring sẽ quản lý lifecycle của nguồn kết nối liên quan.

Với `CachingConnectionFactory`, session/consumer có thể được cache để tái sử dụng. Một handle được close có thể trả vào cache. **Không gọi `cachingConnectionFactory.destroy()` khi ứng dụng vẫn có listener hoặc producer hoạt động**. Việc cache phù hợp cho template không có nghĩa phải chia cache đó cho listener container; `DefaultMessageListenerContainer` thường quản lý cache trong vòng đời của chính nó và tài liệu Spring cảnh báo rủi ro khi dùng external cache cho listener/dynamic scaling.

### 6.2. `@JmsListener` và listener container

`@JmsListener` là endpoint annotation. Khi có `@EnableJms`/auto-configuration phù hợp, Spring tạo `MessageListenerContainer` và `JmsListenerEndpointRegistry` quản lý các container của annotation. Một listener không thể tự biến việc đóng session thành dừng toàn bộ ứng dụng.

**`DefaultMessageListenerContainer`** là container thường dùng; nó giữ consumer tasks, có thể stop/restart và thực hiện recovery khi broker lỗi. Container tham gia lifecycle, và phiên bản `SmartLifecycle.stop(Runnable callback)` có ý nghĩa: callback chỉ được gọi sau khi việc xử lý listener thực sự dừng.

Ví dụ ngắn minh họa lookup (không gọi ở mỗi message):

~~~java
// Mảnh mã trong một lớp quản trị Spring, không phải trong @JmsListener handler.
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null && container.isRunning()) {
    container.stop();
}
~~~

Cần `JmsListenerEndpointRegistry registry` được inject, và đúng import `org.springframework.jms.listener.MessageListenerContainer`. Endpoint cần khai báo `id="ordersListener"`. Cách này có thể dùng cho **tạm ngừng tiêu thụ** khi app vẫn sống; trong shutdown bình thường, để `ApplicationContext` và registry xử lý thay vì mỗi listener tự stop.

**Điểm tinh tế:** một lệnh `stop()` hoặc callback lifecycle không biến việc nhận thêm message thành giới hạn “cắt đúng tại một thời điểm toán học”. Có receive đang chạy gần ranh giới stop. `acceptMessagesWhileStopping` mặc định là `false` ở các Spring listener container liên quan; việc từ chối message trong pha stop có thể tác động retry count tùy broker. Bật `true` cho phép xử lý thêm message lúc đang dừng và **có thể kéo dài drain**, nên phải xem khả năng chấp nhận retry và thời gian shutdown. Với `DefaultJmsListenerContainerFactory`, không giả định mọi setting của container đều là setter của factory; xem API của phiên bản Spring đang chạy nếu muốn tùy chỉnh chi tiết.

### 6.3. `SmartLifecycle` và thứ tự stop

Spring gọi `SmartLifecycle` theo **phase**:

- Khi khởi động: phase nhỏ trước, lớn sau.
- Khi dừng: phase lớn trước, nhỏ sau.
- Với `stop(Runnable callback)`, coordinator có thể chờ callback để biết giai đoạn đó đã dừng, tối đa timeout đã cấu hình cho phase.
- Các bean có quan hệ phụ thuộc tường minh còn chịu ảnh hưởng của dependency order. Đừng đặt phase tùy tiện chỉ để “dừng nhanh” mà làm mất dependency cần thiết.

Ví dụ: nếu JMS handler đang cần database pool để hoàn tất transaction, hãy bảo đảm pool còn sống trong lúc listener đang drain. `@PreDestroy` của một bean nghiệp vụ **không** phải điểm duy nhất phù hợp để điều phối mọi in-flight consumer; callback destroy thường chạy sau các pha stop trong shutdown bình thường, và thứ tự phụ thuộc cấu hình Spring.

**Không sửa phase mặc định một cách mù quáng.** Khi cần tự điều phối thứ tự producer, scheduler, listener và resource pool, xác định rõ các dependency, kiểm chứng trong test shutdown rồi mới dùng `setPhase(...)` hoặc một `SmartLifecycle` riêng.

### 6.4. Spring Boot graceful shutdown không phải tính năng JMS tự động “đúng mọi hợp đồng”

Trong Spring Boot, closing `ApplicationContext` kích hoạt vòng đời stop/destroy của các bean, bao gồm JMS listener được quản lý. Property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

đặt **thời gian chờ mỗi phase**, **không phải thời gian tối đa duy nhất cho toàn bộ process**. Nếu có nhiều phase cần chờ và những bước cleanup khác, tổng thời gian thực tế có thể lớn hơn 30 giây.

Với Spring Boot 3.5, web server có cơ chế graceful shutdown khi đóng context. Property `server.shutdown` chủ yếu điều khiển **HTTP server**; không nên xem `server.shutdown=graceful` là cách giải quyết hết vấn đề JMS message/transaction. Dùng `spring.lifecycle.timeout-per-shutdown-phase` cùng cấu hình JMS listener/reliability.

### 6.5. JVM shutdown hook, tắt bằng IDE và tín hiệu hệ điều hành

Một Spring Boot process chạy theo cách thông thường đăng ký cơ chế đóng context khi JVM tắt. Ví dụ `Ctrl+C` ở terminal hoặc SIGTERM từ orchestrator có thể kích hoạt hook đó. Tắt cưỡng bức, JVM crash, mất điện hoặc công cụ IDE buộc kill process có thể bỏ qua pha dừng. **Không viết hệ thống phụ thuộc chỉ vào shutdown hook để cứu dữ liệu**; phải có phương án khôi phục từ broker/DB.

## 7. Lab Java 17 + Spring Boot 3.5: xem message in-flight khi dừng

Lab sau dùng **Apache ActiveMQ Artemis embedded**, một queue và listener có một consumer; mỗi message xử lý khoảng 4 giây. Khi dừng ngay sau khi bắt đầu một message, ta quan sát Spring có cơ hội chờ handler rồi kết thúc theo lifecycle. Đây là thí nghiệm về **thời điểm stop và transaction JMS**, không phải mô phỏng lỗi cưỡng bức hoặc đảm bảo exactly once.

### 7.1. Tạo dự án

Dùng https://start.spring.io/ chọn:

- Maven, Java, **Spring Boot 3.5.x**, Java 17+.
- Group `com.example`, artifact `jms-shutdown-lab`, package `com.example.jmsshutdown`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Thêm trong `pom.xml` do Spring Initializr tạo, trong `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Để Spring Boot parent/BOM quản lý version Artemis; ví dụ là Boot **3.5**, vì package cấu hình auto thay đổi giữa các major version. Embedded broker phục vụ local lab, không đại diện cho persistence/high-availability ở production.

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-shutdown-lab
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.in
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Không cần bật web server để thực hành một JMS listener; starter Artemis và listener threads cung cấp môi trường hoạt động cho lab. Với app web thực tế, cấu hình HTTP graceful shutdown theo phiên bản Boot riêng.

### 7.2. Code Java hoàn chỉnh

Lưu trong `src/main/java/com/example/jmsshutdown/JmsShutdownLabApplication.java`:

~~~java
package com.example.jmsshutdown;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsShutdownLabApplication.class, args);
    }

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();

        // Kế thừa cấu hình Boot đã tự chuẩn bị cho JMS.
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        // Rollback/redelivery nếu handler ném lỗi.
        factory.setSessionTransacted(true);

        // Chỉ một consumer để quan sát thứ tự trong lab.
        factory.setConcurrency("1");
        factory.setReceiveTimeout(1000L);
        return factory;
    }

    @Bean
    ApplicationRunner seedJobs(JmsTemplate template) {
        return args -> {
            for (int i = 1; i <= 3; i++) {
                String id = "job-" + i;
                template.convertAndSend("orders.in", id);
                System.out.println("PUBLISHED " + id);
            }
        };
    }

    @Component
    public static class OrdersWorker {

        @JmsListener(
                id = "ordersListener",
                destination = "orders.in",
                containerFactory = "ordersListenerFactory")
        public void handle(String jobId) {
            System.out.println("BEGIN " + jobId);

            try {
                TimeUnit.SECONDS.sleep(4);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                // Ném lỗi để session transacted không commit như thành công.
                throw new IllegalStateException(
                        "Interrupted while processing " + jobId, ex);
            }

            System.out.println("DONE " + jobId);
        }
    }
}
~~~

**Vì sao code có cấu trúc này?**

- `JmsTemplate` dùng `ConnectionFactory` do Boot cung cấp để gửi ba chuỗi vào queue.
- `ordersListenerFactory` sử dụng `DefaultJmsListenerContainerFactoryConfigurer` để giữ cài đặt cần thiết của Boot; ở Boot 3.5, `ConnectionFactoryUnwrapper.unwrapCaching` bỏ wrapper caching khi gắn với listener container, tránh dùng chung kiểu cache có giới hạn với consumer container.
- `setSessionTransacted(true)` làm cho handler được xem là hoàn tất về mặt JMS khi transaction của listener được commit; nếu ném exception, container xử lý rollback. Không biến nó thành transaction với một DB giả định.
- `setConcurrency("1")` chỉ để dễ quan sát. `setReceiveTimeout(1000L)` đặt receive timeout một giây, **không** phải timeout cho business handler hoặc deadline shutdown.
- Listener chỉ xử lý và trả về; không gọi `close()` trên session, connection hoặc broker. Spring sở hữu các tài nguyên đó trong đường đi này.

### 7.3. Chạy và quan sát

Từ thư mục dự án có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Ví dụ những dòng nghiệp vụ có thể xuất hiện, xen giữa log của Spring và Artemis:

~~~text
PUBLISHED job-1
PUBLISHED job-2
PUBLISHED job-3
BEGIN job-1
DONE job-1
BEGIN job-2
DONE job-2
BEGIN job-3
DONE job-3
~~~

**Đây là minh họa nội dung log, không phải stdout có thứ tự bảo đảm**: listener chạy ở thread khác, có thể in `BEGIN` trước một số `PUBLISHED`, và bạn chủ động dừng thì chỉ một phần job hoàn tất.

Thực hành:

1. Chạy app và quan sát log `BEGIN ...`.
2. Khi một job đang ngủ 4 giây, gõ `Ctrl+C` **một lần** để gửi tín hiệu dừng thông thường.
3. Quan sát handler có cơ hội in `DONE ...` trước khi JVM thoát, nếu shutdown hook và khoảng thời gian chờ được kích hoạt đúng. Không bảo đảm chính xác số message được bắt đầu trước khi listener ngừng nhận vì có race với polling.
4. Chạy lại app để thực nghiệm khác. Vì broker ở dạng embedded, **không mặc định có cùng backlog qua lần khởi động mới**; muốn thử recover/redelivery qua process restart thực tế, dùng broker ngoài đã cấu hình persistence.
5. Đọc broker metrics/log thay vì chỉ dựa vào output console để kết luận commit hoặc message loss.

**Kiểm tra đúng đắn:** Một lần có `DONE job-2` chỉ chứng minh handler đi tới dòng log đó. Nó chưa chứng minh tác dụng phụ DB đã thành công, cũng chưa đủ để xác nhận JMS commit nếu thread/process crash ngay sau log.

### 7.4. Thử lỗi có kiểm soát

Trong môi trường lab, thay dòng `TimeUnit.SECONDS.sleep(4)` bằng 8 giây, đặt shutdown phase timeout 2 giây và gửi `Ctrl+C`. Quan sát tình trạng listener/container shutdown và broker logs. Đây là thử nghiệm tình huống **vượt budget**, không nên suy đoán kết quả nhất quán trên mọi OS/JVM/provider; nếu còn message chưa commit hoặc broker nhúng bị hủy, xem lại trạng thái trên broker có persistence mới đánh giá được redelivery.

Nếu muốn kiểm thử retry production thực sự, chạy broker độc lập, thiết kế handler theo idempotency key, xác định redelivery policy, rồi thử graceful stop và hard kill ở môi trường test.

## 8. Dùng Jakarta Messaging API trực tiếp: try-with-resources

Khi tự dùng API JMS ngoài Spring, **đóng resource đã tạo** là trách nhiệm của mã ứng dụng. `JMSContext` và `Connection` đều là `AutoCloseable`, nên `try-with-resources` là cách diễn đạt ownership rõ ràng.

Ví dụ Java 17+, dùng Jakarta Messaging 3.x và `ConnectionFactory` provider đã cấu hình:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public final class DirectJmsSender {

    private DirectJmsSender() {}

    public static void sendOne(ConnectionFactory factory, String orderId) {
        try (JMSContext context =
                 factory.createContext(JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue("orders.in");
            context.createProducer().send(queue, orderId);

            // Commit trước khi context tự đóng.
            context.commit();
        }
    }
}
~~~

File `DirectJmsSender.java` này **biên dịch được khi có Jakarta Messaging API trên classpath**, nhưng không tự chạy như một app đầy đủ: cần provider `ConnectionFactory`, broker và code gọi `sendOne`. Dùng Java SE hoặc môi trường cho phép local JMS transaction; trong Jakarta EE managed web/EJB container, quy tắc session/transaction có thể khác.

Nếu `commit` chưa xảy ra mà context đóng, transaction JMS đang mở được rollback theo đặc tả. Vì vậy **không dùng close như một cách implicit commit**.

### 8.1. Nhận đồng bộ và luôn giới hạn thời gian chờ

~~~java
// Phương thức minh họa khác có ConnectionFactory đã được cung cấp.
public static String receiveOne(ConnectionFactory factory) {
    try (JMSContext context =
                 factory.createContext(JMSContext.SESSION_TRANSACTED)) {

        Queue queue = context.createQueue("orders.in");
        String payload = context.createConsumer(queue)
                .receiveBody(String.class, 3000);

        if (payload == null) {
            return null; // Hết timeout, chưa nhận message.
        }

        // Xử lý nghiệp vụ tại đây, ném lỗi khi không hoàn tất.
        context.commit();
        return payload;
    }
}
~~~

Đây là **phương thức minh họa** (không tự biên dịch nếu đứng riêng), cần imports của `ConnectionFactory`, `JMSContext` và `Queue`; thực tế nên dùng listener container cho service nhận liên tục. Timeout `3000` là thời gian chờ khi không có message, không phải deadline xử lý sau khi đã nhận.

Nếu code xử lý nghiệp vụ giữa `receiveBody` và `commit` ném exception, context được close, transaction chưa commit sẽ rollback. Đừng bắt exception rồi chỉ log và trả về bình thường trước `commit` nếu muốn broker xử lý retry một cách đúng đắn.

### 8.2. Nếu bạn dùng `Connection` và `Session` riêng

~~~java
// Mảnh code JMS API, các biến factory và destination cần có sẵn.
try (var connection = factory.createConnection()) {
    try (var session = connection.createSession(
            jakarta.jms.Session.SESSION_TRANSACTED)) {
        var producer = session.createProducer(destination);
        producer.send(session.createTextMessage("order-17"));
        session.commit();
        // session.close() được try-with-resources thực hiện.
    }
    // connection.close() được try-with-resources thực hiện.
}
~~~

Đây là **mảnh mã**, không phải một class độc lập: cần `factory`, `destination` và dependency Jakarta Messaging/provider. Khi connection close, con của nó cũng đóng; code nested `try` vẫn hữu ích nếu connection dự kiến còn sống để mở session khác.

**Không chia sẻ một `Session` / `JMSContext` cho nhiều thread tùy ý.** JMS có các quy tắc single-thread-of-control; nếu muốn nhiều worker, mỗi worker nên có tài nguyên/session do provider hoặc listener container phân phối đúng mô hình.

## 9. Caching, pooling và thứ tự dọn tài nguyên

### 9.1. `SingleConnectionFactory` và `CachingConnectionFactory`

Spring có wrapper tái sử dụng connection. Với `SingleConnectionFactory`, lời gọi `Connection.close()` trên handle có thể được bỏ qua bởi wrapper để giữ connection thật; factory cần được destroy/reset theo lifecycle. `CachingConnectionFactory` còn có thể cache session/producer/consumer. Vì vậy số lần code gọi `close()` không tương ứng một-một với số TCP connection bị ngắt.

**Khi app đang chạy:** code mượn resource qua Spring được trả về pool/cache theo giao kèo. **Khi app đang tắt:** Spring/container destroy chủ sở hữu pool/cache để release các connection vật lý cuối cùng. Cố đóng physical connection ở một method nghiệp vụ có thể làm các message đang xử lý khác thất bại.

### 9.2. Listener container và cache riêng

`DefaultMessageListenerContainer` có cơ chế cache theo vòng đời của nó. Khi dùng thêm external `CachingConnectionFactory` cho listener, có những hạn chế khi stop/restart và scaling; tài liệu Javadoc cảnh báo không nên mặc định dùng cùng một wrapper cache cho mọi đường đi. Dùng cấu hình chính thức của Spring Boot hoặc thiết kế tách riêng sender cache và listener container khi hệ thống cần kiểm soát rõ ownership.

### 9.3. Thread pool, database, scheduler

Dừng JMS chưa đủ nếu handler:

- Đẩy công việc sang một `ExecutorService` rồi trả về ngay.
- Gửi HTTP bất đồng bộ nhưng không chờ response/commit thật sự.
- Ghi database qua thread khác và xác nhận JMS trước khi transaction DB hoàn tất.
- Dùng stream/background callback còn chạy sau khi listener method trả về.

Nếu listener trả về sớm, Spring có thể commit/ack message **trước** khi các công việc hậu trường hoàn tất. Thiết kế lại để handler đợi kết quả đủ điều kiện thành công hoặc đưa bước bất đồng bộ sang một queue/outbox riêng có hợp đồng rõ ràng. Khi shutdown, cũng cần drain các executor/outstanding tasks theo phase hợp lý.

## 10. Deployment: SIGTERM, Kubernetes và time budget

### 10.1. Lập “ngân sách dừng” đủ lớn

Giả sử handler dài nhất bình thường 25 giây, listener có polling timeout khoảng 1 giây, cần ghi metrics và cleanup vài giây. Nếu `spring.lifecycle.timeout-per-shutdown-phase=5s` mà orchestrator giết process sau 10 giây, shutdown có thể không đủ thời gian.

Một policy minh họa:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=40s
~~~

và Kubernetes pod spec:

~~~yaml
spec:
  terminationGracePeriodSeconds: 75
  containers:
    - name: jms-consumer
      image: example/jms-consumer:v1
      # probes, resources, security và các cài đặt khác tùy môi trường
~~~

Đây chỉ là **đoạn spec minh họa để thảo luận budget**, chưa phải file Deployment YAML hoàn chỉnh. Thời gian grace của Kubernetes bao gồm nhiều bước (và có thể có `preStop`), còn property Spring tính theo **mỗi phase**, nên 75/40 giây trên chỉ là ví dụ, không phải công thức đúng cho mọi ứng dụng. Phải đo P95/P99 thực tế, xem số phase, tình huống broker chậm và bộ lọc load-balancer.

### 10.2. Readiness khác JMS consumer lifecycle

Kubernetes readiness false có thể đưa Pod ra khỏi luồng HTTP Service, nhưng broker JMS vẫn có thể đang giao message cho consumer nối trực tiếp. Muốn JMS thực sự ngừng nhận phải **stop listener/container** hoặc đóng connection đúng vòng đời. Không dùng preStop script chỉ để `sleep` và mặc định message đã drain.

Tình huống một pod vừa nhận HTTP vừa consume JMS cần điều phối hai đầu vào: từ chối HTTP job mới đúng lúc, ngừng scheduler producer, dừng listener, sau đó giữ DB/connection đủ lâu cho những công việc chưa hoàn tất. Lịch stop phải phản ánh dependency thật, không chỉ gọi `@PreDestroy` tùy tiện.

### 10.3. Không coi shutdown hook là tuyến phòng thủ duy nhất

Không có cơ chế graceful bảo đảm được khi container bị OOM-killed, node biến mất, process crash hoặc quá grace period. Phải kết hợp:
- Persistent broker khi yêu cầu lưu trữ đáng tin và policy phù hợp.
- Transacted receive/ack đúng lúc; backoff, retry budget, DLQ.
- Idempotent business handler.
- Observability và công cụ replay/quarantine.
- Thử nghiệm restart/cut network/kill trong staging.

## 11. Kịch bản lỗi và kỳ vọng đúng

| Tình huống | Hành vi cần kiểm tra |
| --- | --- |
| SIGTERM khi không có message | Listener dừng, session/connection được giải phóng, app thoát trong budget |
| SIGTERM khi handler đang xử lý | Handler có cơ hội xong; nếu không hoàn tất, transaction/ack quyết định redelivery |
| Mất broker giữa handler | Lỗi kết nối, commit thất bại và khả năng recovery theo provider; không suy đoán “đã xong” từ log |
| Handler ném exception trước JMS commit | Với transacted listener, rollback/redelivery theo broker policy |
| DB commit rồi JVM chết trước JMS commit | Message có thể quay lại; idempotency tránh side effect lặp |
| Handler chuyển việc sang async executor rồi trả về | JMS có thể được ack quá sớm; cần hợp đồng đợi/đưa công việc vào durable queue khác |
| Dừng sớm khi receive timeout dài | Có thể chậm chờ polling/stop; đo shutdown latency và chọn timeout phù hợp |
| Nhiều concurrent consumers đang shutdown | Số receive race/rejected delivery/retry attempts có thể thay đổi; kiểm tra DLQ và số lần giao lại |
| Gọi close trực tiếp trong listener | Không portable với Connection/Session; bỏ mẫu này |
| Tắt bằng `kill -9` | Không chạy hook; trông cậy transaction broker + idempotency |
| Cả broker và consumer cùng bị dừng | Xác định thứ tự hạ tầng và persistence; ứng dụng không tự dừng broker chia sẻ |
| Stop rồi khởi động lại container | Kiểm tra container recover và các connection cache đặc thù; không mặc định stop==destroy |

### Bộ kiểm thử chấp nhận

1. **Khởi động:** container nhận được message, connection tới đúng broker, queue tồn tại và converter tương thích.
2. **Normal finish:** gửi 10 message; mọi nghiệp vụ hoàn tất đúng một lần theo business ID nếu không có lỗi; broker backlog về 0.
3. **Graceful drain:** giữ một handler đang chạy, gửi SIGTERM, đo `drain_duration` và message commit/rollback.
4. **Forced kill:** tạo side effect rồi kill trước JMS commit trong staging; xác nhận message được nhận lại và handler idempotent.
5. **Long handler:** giả lập thao tác vượt phase timeout; quan sát hành vi stop, process exit và DLQ/retry.
6. **Concurrent shutdown:** với nhiều consumers, gửi hàng chục messages và stop; phân biệt số **delivery attempts** với **business completions**.
7. **External dependency failure:** DB đóng/chậm giữa handler; không commit JMS như thành công khi thao tác phụ thuộc thất bại.
8. **Restart:** producer/consumer version mới đọc backlog cũ; không đổi format/serialization khi chưa có compatibility plan.
9. **Resources:** sau dừng không còn thread, JMS session và connection do process sở hữu; broker không giữ connection ma quá lâu theo policy.
10. **Readiness/rollout:** một instance rời traffic nhận vào trong khi replica khác vẫn tiếp quản backlog, không tạo gap dài bất thường.

## 12. Quan sát, cảnh báo và cách chẩn đoán shutdown chậm

Đừng chỉ đọc dòng “Application stopped”. Ghi nhận các dữ liệu sau theo service/destination/instance:

- **Shutdown start/end timestamp** và nguyên nhân: SIGTERM, scale down, admin stop, lỗi nghiêm trọng.
- **Listener status:** số container running/stopping, active consumer count, active/pending tasks và concurrency cấu hình.
- **In-flight message count:** đang xử lý, đã xử lý thành công, commit/ack, rollback, redelivery, backlog và DLQ.
- **Tuổi message chờ và tốc độ xử lý:** queue depth, oldest message age, throughput và saturation trong lúc drain.
- **Transaction/side-effect:** DB commit latency, timeout, external API errors, khả năng lặp theo business ID.
- **Resource cleanup:** số connection/session còn mở, pool active/idle, executor thread còn sống, shutdown duration và lỗi cleanup.
- **Broker health:** connection lost, failover/recovery loop, session commit errors, redelivery count, poison message và retry policy.

Một vài câu chẩn đoán:

- **“Đã SIGTERM mà container vẫn nhận job mới”** → readiness không ảnh hưởng JMS; kiểm tra stop phase/registry, `acceptMessagesWhileStopping`, poll races và luồng publish nội bộ.
- **“Close mất 40 giây”** → listener đang chạy, receive timeout hoặc dependency bị treo; đo thời gian từng bước; đừng dùng `kill -9` làm workaround cho timeout chưa rõ.
- **“Sau deploy có email gửi hai lần”** → redelivery giữa side effect và JMS commit; áp dụng idempotency/inbox.
- **“Message biến mất dù handler lỗi”** → kiểm tra `AUTO_ACKNOWLEDGE` và loại listener container; dùng transacted session khi cần reliability.
- **“Đóng connection ở @PreDestroy nhưng handler ném JMSException”** → đã hủy resource khi listener còn cần; giao lifecycle cho container, sửa thứ tự phase/owner.
- **“Pool báo connection leak”** → kiểm tra code dùng JMS API trực tiếp đã close context/session chưa, factory pooling có destroy hook chưa, và liệu shutdown bị bỏ qua bởi kill cưỡng bức.

## 13. Những sai lầm phổ biến cần tránh

1. **Dùng `close()` để commit.** Close transacted session chưa commit phải rollback; commit tường minh hoặc để container quản lý.
2. **Đóng `Connection` trong `onMessage`.** Không portable, có thể block/throw; lifecycle nằm ngoài handler.
3. **Đóng resources của `JmsTemplate` thủ công.** Template quản lý session/connection theo callback và factory.
4. **Destroy `CachingConnectionFactory` trước khi listener dừng.** Cắt tài nguyên đang được dùng; cần đúng owner/phase.
5. **Tin `server.shutdown=graceful` đủ cho JMS.** Đây chủ yếu là cấu hình web server; JMS có listener container và transaction riêng.
6. **Nhầm `timeout-per-shutdown-phase` với timeout toàn process.** Cần budget tổng gồm mọi phase và orchestrator grace.
7. **Cho rằng listener method trả về = database/API đã hoàn tất.** Đừng fire-and-forget mà vẫn ack JMS ngay.
8. **Cho rằng stop sẽ ngăn tất cả message kể từ cùng một nanosecond.** Có in-flight và receive race; cần xử lý transaction và retry.
9. **Dùng AUTO_ACKNOWLEDGE cho job không được mất.** Kiểm tra semantics của Spring container; thường dùng transacted listener.
10. **Quên xử lý interrupt và deadline.** Handler bị cancel phải ngừng an toàn; nếu chưa thành công, ném lỗi để rollback thay vì log rồi tiếp tục commit.
11. **Dùng embedded broker demo để chứng minh persistence qua restart.** Broker nhúng bị dừng theo app; muốn test durability dùng broker độc lập.
12. **Cho rằng xử lý một lần trên broker = business effect một lần.** Phải idempotent trước redelivery, nhất là với DB/HTTP.
13. **Dừng hết các hệ thống phụ thuộc trước consumer.** DB, producer reply hoặc external resource phải còn sống tới khi in-flight handler xong.
14. **Không giám sát DLQ khi rolling deploy.** Một consumer mới lỗi schema có thể đưa backlog vào retry/DLQ dù shutdown “thành công”.
15. **Bật cache/pool không rõ ownership.** Pool, client và listener container có các vòng đời khác nhau; đo connection thật và đọc provider-specific docs.
16. **Chỉ kiểm thử Ctrl+C.** Phải thử SIGTERM, mất broker, force kill, timeout và restart có backlog trong staging.

## 14. Checklist khi review một dịch vụ Spring JMS

- **Nguồn kết nối:** factory nào thực sự tạo connection? Có caching/pooling và bean ownership rõ chưa?
- **Đường gửi:** những scheduler/request/worker nào có thể tiếp tục publish trong lúc draining?
- **Đường nhận:** listener container nào quản lý `@JmsListener`? Có nhận diện đúng endpoint IDs và phase không?
- **Reliability:** dùng `sessionTransacted`/ack mode nào? Khi lỗi xử lý ai rollback? Có DLQ/retry không?
- **Transactions:** DB side effect và JMS commit có thể tách nhau; idempotency key được lưu ở đâu?
- **In-flight:** handler tối đa thực tế bao lâu? Task có đẩy sang async executor rồi trả về sớm không?
- **Grace budget:** `spring.lifecycle.timeout-per-shutdown-phase`, HTTP stop, k8s termination grace và các phase có nhất quán?
- **Ordering:** producer, listener, executor, DB, HTTP client, JMS cache và metrics đóng theo phụ thuộc nào?
- **Portability:** có gọi `stop/close` trong listener callback, trông cậy provider-specific behavior không?
- **Operations:** có metrics drain, queue lag, DLQ, rollback, broker connection và runbook rollback rollout không?
- **Tests:** đã thử cả graceful stop lẫn process crash trước/sau side effect chưa?
- **Đổi phiên bản:** message trong backlog do phiên bản trước gửi còn đọc được sau deploy chứ?

## 15. Câu hỏi thực hành

1. Một listener ghi database rồi gửi HTTP, sau đó nhận SIGTERM khi HTTP đang đợi response. Vẽ ít nhất ba điểm có thể bị ngắt và xác định bước nào cần idempotency.
2. Phân tích sự khác nhau giữa `connection.stop()`, `connection.close()`, `session.close()` và `consumer.close()` khi message chưa ack.
3. Trong app có `JmsTemplate` và `@JmsListener` cùng dùng `ConnectionFactory`, giải thích vì sao không nên tự gọi `destroy` của factory ở một handler.
4. Cho handler mất tối đa 25 giây, shutdown phải chạy 2 phase, mỗi phase có timeout 30 giây. Hãy đề xuất `terminationGracePeriodSeconds` có dự phòng và nêu cách đo thực tế.
5. Chạy lab với 3 messages, gửi `Ctrl+C` sau một dòng `BEGIN`. Ghi lại log, tổng message đã commit và còn backlog trên broker ngoài (nếu cấu hình), rồi giải thích vì sao log chỉ là chỉ báo.
6. Thay transacted listener bằng `AUTO_ACKNOWLEDGE` trong môi trường test; cho handler ném exception. So sánh redelivery của `DefaultMessageListenerContainer` với kỳ vọng ban đầu.
7. Giả lập “handler trả về trước, executor còn chạy”. Giải thích lỗi contract và chỉnh thiết kế sao cho ack phản ánh hoàn tất thật sự.
8. Từ mô hình Kubernetes, chỉ ra vì sao readiness false không trực tiếp ngăn JMS consumer nhận thêm message; cần thêm bước nào?
9. Broker tạm mất giữa `DONE` log và JMS commit. Viết cách kiểm tra trạng thái thực bằng broker/DB metrics, tránh quyết định chỉ theo stdout.

## Nguồn chính thức để tra cứu

- Jakarta Messaging 3.1 Specification — connection stop/close, session/consumer close và transaction: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging API, `JMSContext` và `Session`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta/jms/jmscontext
- Spring Framework — Using Spring JMS, acknowledge và listener container: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework — `AbstractMessageListenerContainer` stop handling: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html
- Spring Framework — `SmartLifecycle` và callback shutdown: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- Spring Boot 3.5 — Graceful Shutdown và timeout theo phase: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- Spring Boot 3.5 — JMS messaging configuration: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
