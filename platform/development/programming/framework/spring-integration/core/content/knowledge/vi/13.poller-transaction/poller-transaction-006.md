# Retry quanh poller

## 1. Mục tiêu và bối cảnh

Trong module **SPRING_INTEGRATION_CORE**, luồng thông điệp được ghép từ Message, MessageChannel, endpoint, gateway và Java DSL. Bài này thuộc chương **Poller transaction**, tập trung vào cách thử lại một thao tác polling khi gặp lỗi tạm thời, đồng thời giữ đúng ranh giới transaction và ý nghĩa xử lý thông điệp.

Sau bài học, bạn có thể:

- Phân biệt lịch polling, retry trong một lần polling và redelivery từ nguồn.
- Chọn retry quanh poller hay retry tại một handler.
- Sắp xếp retry advice và transaction advice theo mục tiêu.
- Giải thích vì sao rollback không tự đưa mọi thông điệp trở lại nguồn.
- Thiết kế giới hạn thử lại, backoff, đường lỗi và cách kiểm chứng hành vi.

**Phạm vi ví dụ:** mã Java sử dụng API Spring Integration **6.5.x**, Spring Retry **2.0.x** và Java 17 trở lên. Ví dụ cần các thư viện Spring Integration Core và Spring Retry; ví dụ JDBC cần thêm Spring Integration JDBC, Spring JDBC và driver phù hợp. Phiên bản dependency nên do BOM của dự án quản lý. Không ghép nguyên các import Spring Retry trong bài với API retry của Spring Integration 7.x: nhánh 7.x đã chuyển cơ chế retry sang Spring Framework. Xem [tài liệu retry của nhánh 6.5](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html) và [API RequestHandlerRetryAdvice nhánh 7.x](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

## 2. Poller đang bao quanh thao tác nào?

Có hai tình huống thường gặp:

| Thành phần | Nguồn được poll | Hành động sau khi nhận |
|---|---|---|
| SourcePollingChannelAdapter | MessageSource, ví dụ nguồn JDBC hoặc nguồn tùy chỉnh | Gửi Message vào output channel |
| PollingConsumer | PollableChannel, ví dụ QueueChannel | Gọi MessageHandler của endpoint |

Một lần nhận và xử lý có thể hình dung như sau:

~~~text
receive()
   |
   +-- null ----------------------> không có dữ liệu, kết thúc lần nhận
   |
   +-- Message --> xử lý/gửi tiếp --> thành công hoặc ném exception
~~~

Poller advice thông thường bao quanh thao tác nhận và xử lý đồng bộ này. Khi advice thử lại, nó có thể gọi lại cả `receive()`. Đây là điểm khác với việc giữ nguyên Message rồi chỉ gọi lại một dịch vụ. Các loại endpoint được mô tả trong [Poller](https://docs.spring.io/spring-integration/reference/6.5/polling-consumer.html).

Ví dụ một luồng đơn hàng:

~~~text
Nguồn đơn hàng
   -> poller
   -> transformer chuẩn hóa
   -> filter kiểm tra điều kiện
   -> router chọn đối tác
   -> gateway gọi đối tác
   -> ghi kết quả
~~~

Nếu gateway lỗi và exception quay về poller trên cùng call stack, retry quanh poller có thể chạy lại các bước trước gateway. Điều này cần được đánh giá theo tác dụng phụ của từng bước, chẳng hạn ghi audit, giữ hàng hoặc tạo yêu cầu thanh toán. Tài liệu [Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/6.5/handler-advice.html) giải thích lý do cần khả năng đặt advice riêng trên endpoint.

### 2.1. Một nhịp scheduler có thể chứa nhiều lần nhận

`maxMessagesPerPoll` giới hạn số lần nhận có thông điệp trong một nhịp được lập lịch. Nó không phải số retry. Với poller đồng bộ thông thường của nhánh 6.5, advice chain thông thường được gắn vào polling task thực hiện một lần nhận và xử lý; vòng lặp của nhịp scheduler gọi task đó nhiều lần.

Bởi vậy, `maxMessagesPerPoll(10)` không tự biến mười thông điệp thành một transaction chung. Bài dùng `maxMessagesPerPoll(1)` để quan sát rõ từng đơn vị nhận và xử lý. Chi tiết này có thể đối chiếu trong [mã nguồn AbstractPollingEndpoint 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

## 3. Ba cơ chế thường bị nhầm lẫn

| Cơ chế | Ai kích hoạt lần tiếp theo? | Bộ đếm thuộc về đâu? | Có bảo đảm cùng Message không? |
|---|---|---|---|
| Lịch polling | Scheduler và Trigger | Nhịp lập lịch | Không |
| Retry quanh poller | Retry advice | Một lần thực thi được advice quản lý | Không tự bảo đảm; có thể receive lại |
| Redelivery | Broker, transactional store hoặc logic nguồn | Chính sách giao lại của nguồn | Phụ thuộc cơ chế nguồn và định danh nghiệp vụ |

Ví dụ cấu hình poller chạy sau mỗi một giây và retry tối đa ba attempt:

~~~text
Nhịp 1:
  attempt 1 -> lỗi tạm thời
  chờ 100 ms
  attempt 2 -> lỗi tạm thời
  chờ 200 ms
  attempt 3 -> thành công

Nhịp 2:
  một lần polling mới, có ngân sách retry mới
~~~

Trong Spring Retry 2.0.x, `maxAttempts = 3` tính cả lần đầu, tức tối đa hai lần thử lại. Không có lần ngủ sau attempt cuối. Hợp đồng đếm attempt được nêu trong [SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

Nếu cả ba attempt thất bại, scheduler vẫn có thể thực hiện nhịp sau. Với nguồn rollback được, cùng sự kiện có thể xuất hiện ở nhịp đó và lại nhận ngân sách ba attempt mới. Vì thế, giới hạn của một retry invocation chưa phải giới hạn tổng số lần xử lý một sự kiện.

Khi `receive()` trả về `null`, nguồn đang báo không có thông điệp. Đây không phải exception để policy thông thường retry. Không nên ném lỗi giả chỉ để buộc poller tiếp tục dò nguồn đang rỗng.

## 4. Chọn phạm vi retry

### 4.1. Retry quanh poller

Phù hợp khi lỗi xảy ra lúc truy cập nguồn hoặc khi cần thử lại toàn bộ đơn vị transactional gồm nhận và xử lý.

Ví dụ:

- Kết nối đọc nguồn bị gián đoạn ngắn trước khi lấy được dữ liệu.
- Deadlock làm transaction nhận và cập nhật đơn hàng phải rollback.
- Nguồn hỗ trợ giao lại, các bước đồng bộ có thể được thực hiện lại an toàn.

Advice dùng trong ví dụ là `RetryOperationsInterceptor`, một MethodInterceptor tổng quát của Spring Retry. Nó được đưa vào `Pollers...advice(...)`, không gắn lên handler.

### 4.2. Retry tại handler

Nếu chỉ muốn gọi lại một dịch vụ với Message đã nhận, cân nhắc `RequestHandlerRetryAdvice` tại endpoint đó. Trong nhánh 6.5, có thể cấu hình cùng kiểu RetryTemplate, nhưng cần một advice phù hợp với request handler:

~~~java
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

// Trong một phương thức @Bean:
RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
advice.setRetryTemplate(handlerRetryTemplate);
return advice;
~~~

`handlerRetryTemplate` là RetryTemplate dành riêng cho policy của thao tác dịch vụ. Trong Java DSL, advice này được cấu hình ở endpoint xử lý:

~~~java
.handle(partnerService, "submit", endpoint -> endpoint.advice(partnerRetry))
~~~

Ở đây `partnerService` là bean dịch vụ và `partnerRetry` là RequestHandlerRetryAdvice. Đặt `RequestHandlerRetryAdvice` vào poller không phải cách thay thế tương đương cho MethodInterceptor tổng quát; advice đó được thiết kế cho lời gọi xử lý Message.

### 4.3. Chỉ retry thao tác đọc

Nếu cần thử lại phần đọc nguồn nhưng muốn downstream chạy đúng một lần, có thể bọc lời gọi đọc của MessageSource bằng RetryTemplate rồi để lỗi downstream đi theo cơ chế riêng.

Spring Integration còn có nhóm `ReceiveMessageAdvice` dành cho thao tác receive. Tuy nhiên, interface này không tự bổ sung policy retry; việc chọn hoặc viết implementation vẫn phải đúng hợp đồng của nó. Khi phối hợp nhiều loại advice, cần kiểm tra phạm vi thực tế thay vì chỉ nhìn thứ tự tên bean.

| Nhu cầu | Điểm đặt ưu tiên |
|---|---|
| Khôi phục lỗi truy cập nguồn ngắn hạn | Quanh poller hoặc riêng thao tác đọc |
| Thử lại một HTTP call với cùng payload | Advice của handler/gateway thực hiện HTTP call |
| Rollback rồi nhận lại một đơn vị công việc | Poller retry bên ngoài transaction, kèm nguồn transactional |
| Chờ hàng phút hoặc hàng giờ | Cơ chế giao lại có lịch, retry queue hoặc bộ lập lịch bền vững |

## 5. Ví dụ Java DSL: nguồn lỗi hai lần rồi thành công

Ví dụ sau là một cấu hình Spring hoàn chỉnh cho tình huống **lỗi trước khi nguồn phát Message**. Nó chủ động giới hạn lỗi được retry, cấu hình backoff và cung cấp kênh riêng để nhận kết quả hoặc lỗi.

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.interceptor.RetryInterceptorBuilder;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class PollerRetryDemo {

    @Bean
    AtomicInteger sourceReadCounter() {
        return new AtomicInteger();
    }

    @Bean
    RetryOperationsInterceptor pollRetry() {
        Map<Class<? extends Throwable>, Boolean> retryable =
                Map.of(TransientDataAccessException.class, true);

        SimpleRetryPolicy policy =
                new SimpleRetryPolicy(3, retryable, true, false);

        ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
        backoff.setInitialInterval(100);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(1_000);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backoff);

        return RetryInterceptorBuilder.stateless()
                .retryOperations(template)
                .build();
    }

    @Bean
    MessageSource<String> demoSource(AtomicInteger sourceReadCounter) {
        AtomicBoolean emitted = new AtomicBoolean();

        return () -> {
            if (emitted.get()) {
                return null;
            }

            int attempt = sourceReadCounter.incrementAndGet();
            if (attempt <= 2) {
                throw new TransientDataAccessResourceException(
                        "Nguồn chưa sẵn sàng, lần đọc " + attempt);
            }

            emitted.set(true);
            return MessageBuilder.withPayload("order-1042")
                    .setHeader("eventId", "evt-1042")
                    .build();
        };
    }

    @Bean
    QueueChannel demoResults() {
        return new QueueChannel(10);
    }

    @Bean
    QueueChannel pollErrors() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow demoFlow(
            MessageSource<String> demoSource,
            RetryOperationsInterceptor pollRetry,
            @Qualifier("demoResults") QueueChannel demoResults,
            @Qualifier("pollErrors") QueueChannel pollErrors) {

        return IntegrationFlow
                .from(demoSource, endpoint -> endpoint
                        .id("demoSourcePoller")
                        .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                                .maxMessagesPerPoll(1)
                                .advice(pollRetry)
                                .errorChannel(pollErrors)))
                .transform(String.class, String::toUpperCase)
                .channel(demoResults)
                .get();
    }
}
~~~

Các quyết định cần đọc ra từ cấu hình:

- Policy cho phép tối đa ba attempt, chỉ retry TransientDataAccessException và các lớp con.
- `traverseCauses = true` cho phép tìm nguyên nhân phù hợp trong exception bọc; `defaultValue = false` loại các lỗi không nằm trong policy.
- Backoff lần lượt là 100 ms và 200 ms nếu hai attempt đầu cùng thất bại.
- Không khai báo recoverer, nên lỗi cuối cùng tiếp tục đi ra ngoài advice.
- `pollErrors` và `demoResults` là QueueChannel trong bộ nhớ, dung lượng nhỏ để phục vụ quan sát minh họa.
- AtomicBoolean chỉ ghi nhớ trạng thái phát dữ liệu của nguồn demo, không cung cấp rollback hay lưu bền.

Việc tạo interceptor bằng `RetryInterceptorBuilder.stateless().retryOperations(template)` được hỗ trợ trong [RetryInterceptorBuilder 2.0.x](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/interceptor/RetryInterceptorBuilder.html). Khi đã cung cấp RetryOperations tùy chỉnh, policy và backoff được cấu hình trong template đó.

Kết quả mong đợi là payload `ORDER-1042` trên `demoResults` và bộ đếm đọc bằng 3. Các nhịp polling sau trả về null.

**Giới hạn quan trọng:** nguồn demo đánh dấu đã phát trước khi downstream hoàn tất. Nếu transformer hoặc bước gửi tiếp thất bại sau đó, attempt mới sẽ thấy null. Ví dụ này chứng minh retry lỗi đọc nguồn, không chứng minh khả năng nhận lại Message khi xử lý thất bại.

## 6. Retry và transaction: thứ tự quyết định hành vi

Advice là các lớp bao quanh lời gọi. Với chuỗi advice thông thường, phần tử đầu nằm ngoài cùng. Hai cấu trúc sau có ý nghĩa khác nhau:

~~~text
A. Retry(Tx(receive + xử lý))

attempt 1: begin T1 -> lỗi -> rollback T1
backoff
attempt 2: begin T2 -> lỗi -> rollback T2
backoff
attempt 3: begin T3 -> thành công -> commit T3

B. Tx(Retry(receive + xử lý))

begin T
  attempt 1 -> lỗi
  backoff
  attempt 2 -> lỗi
  backoff
  attempt 3 -> thành công hoặc lỗi
commit/rollback T
~~~

Quy tắc bao quanh này được trình bày trong [Ordering Advices within Advice Chain](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/order.html).

### 6.1. Retry bên ngoài transaction

Khi một attempt phải rollback hoàn toàn trước attempt tiếp theo, thường chọn cấu trúc A:

~~~java
.advice(pollRetry, pollTransaction)
~~~

Với propagation REQUIRED và poller thread không có transaction bao ngoài, mỗi attempt tạo một transaction mới. Khi lỗi đáp ứng quy tắc rollback đi qua transaction advice, transaction kết thúc trước khi retry advice chờ backoff.

Hãy kiểm tra đồng thời ba điều kiện:

1. Exception thực sự đi ra khỏi phần transactional.
2. Transaction manager có quản lý các tài nguyên cần rollback.
3. Nguồn có thể nhận lại công việc sau rollback.

Retry advice đặt ngoài không tự bảo đảm transaction vật lý mới nếu đang có transaction ngoài cùng và REQUIRED chỉ tham gia transaction đó.

### 6.2. Transaction bên ngoài retry

Với cấu trúc B, việc chờ backoff diễn ra trong phạm vi transaction ngoài. Connection, lock hoặc trạng thái persistence có thể được giữ lâu hơn.

Nếu một thành phần tham gia đã đánh dấu rollback-only, một attempt sau thành công không xóa cờ đó. Lúc commit có thể phát sinh UnexpectedRollbackException. Không phải mọi exception đều tự đặt rollback-only; hành vi phụ thuộc transaction advice, tài nguyên và quy tắc rollback. Các điểm này được giải thích trong [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

Ngoài ra, nếu retry bắt lỗi rồi recoverer trả bình thường, transaction ngoài có thể thấy lời gọi thành công trong trường hợp chưa bị đánh dấu rollback-only. Vì vậy, không dùng việc “đã gửi lỗi sang một channel” làm bằng chứng transaction đã rollback.

### 6.3. Không dùng REQUIRES_NEW như một cách sửa tự động

REQUIRES_NEW có thể tách transaction, nhưng cũng thay đổi tính nguyên tử của luồng. Một bước con commit riêng rồi bước nhận thông điệp rollback có thể khiến bước con chạy lại khi giao lại.

Trước khi dùng, cần xác định kết quả nào phải commit cùng nhau, có transaction ngoài hay không và connection pool có đủ tài nguyên. Trong ví dụ poller tự khởi tạo transaction và không có transaction ngoài, REQUIRED đã đáp ứng mục tiêu mỗi attempt một transaction.

## 7. Ví dụ transactional: nhận từ JDBC-backed QueueChannel

Ví dụ này chọn PostgreSQL để thể hiện rõ một nguồn transactional. Mục tiêu là gắn việc lấy thông điệp ra khỏi channel và việc ghi kết quả vào cùng transaction cục bộ.

Điều kiện sử dụng:

- Có một DataSource dành cho PostgreSQL.
- Có thư viện Spring Integration JDBC, Spring JDBC, Spring TX và driver PostgreSQL.
- Đã khởi tạo schema message store từ script phù hợp trong Spring Integration JDBC.
- Có bảng nghiệp vụ `order_result`; `event_id` có unique constraint hoặc primary key.
- Queue store, JdbcTemplate và transaction manager dùng **cùng DataSource bean**.
- Luồng xử lý chạy đồng bộ, không có ExecutorChannel hoặc QueueChannel trung gian.

Ví dụ bảng nghiệp vụ:

~~~sql
CREATE TABLE order_result (
    event_id VARCHAR(100) PRIMARY KEY,
    order_code VARCHAR(100) NOT NULL
);
~~~

Các phương thức bean dưới đây đặt trong một lớp cấu hình có `@Configuration` và `@EnableIntegration`. Dùng lại bean `pollRetry` ở phần trước; không cần bật `demoFlow`, `demoSource` và các bean quan sát của demo trong ứng dụng JDBC.

~~~java
import java.time.Duration;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.MessageChannels;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.transaction.TransactionInterceptorBuilder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.interceptor.TransactionInterceptor;

// Các phương thức trong lớp cấu hình:

@Bean
JdbcChannelMessageStore ordersStore(DataSource dataSource) {
    JdbcChannelMessageStore store = new JdbcChannelMessageStore(dataSource);
    store.setChannelMessageStoreQueryProvider(
            new PostgresChannelMessageStoreQueryProvider());
    return store;
}

@Bean
QueueChannel orders(JdbcChannelMessageStore ordersStore) {
    return MessageChannels.queue(ordersStore, "orders")
            .getObject();
}

@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}

@Bean
TransactionInterceptor pollTransaction(
        PlatformTransactionManager transactionManager) {

    return new TransactionInterceptorBuilder()
            .transactionManager(transactionManager)
            .propagation(Propagation.REQUIRED)
            .timeout(5)
            .build();
}

@Bean
MessageHandler orderHandler(DataSource dataSource) {
    JdbcTemplate jdbc = new JdbcTemplate(dataSource);

    return message -> {
        String eventId = message.getHeaders().get("eventId", String.class);
        if (eventId == null) {
            throw new IllegalArgumentException("Thiếu eventId");
        }

        jdbc.update("""
                INSERT INTO order_result(event_id, order_code)
                VALUES (?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                eventId,
                message.getPayload().toString());
    };
}

@Bean
IntegrationFlow ordersFlow(
        @Qualifier("orders") QueueChannel orders,
        RetryOperationsInterceptor pollRetry,
        TransactionInterceptor pollTransaction,
        @Qualifier("orderHandler") MessageHandler orderHandler) {

    return IntegrationFlow.from(orders)
            .handle(orderHandler, endpoint -> endpoint
                    .id("ordersPollingConsumer")
                    .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                            .receiveTimeout(0)
                            .maxMessagesPerPoll(1)
                            .advice(pollRetry, pollTransaction)))
            .get();
}
~~~

Lưu ý khi đọc ví dụ:

- `timeout(5)` của transaction builder được tính bằng **giây**.
- `receiveTimeout(0)` là thời gian chờ nhận từ channel, tính bằng **mili giây**; 0 nghĩa là không chờ.
- Không khai báo recovery callback ở retry advice.
- PostgreSQL ON CONFLICT giúp thao tác tạo một dòng kết quả không tạo thêm dòng khi cùng eventId quay lại. Đây là quy tắc đơn giản cho ví dụ, giả định cùng eventId luôn đại diện cùng nội dung nghiệp vụ.
- `ON CONFLICT` không xử lý sự khác biệt payload của hai sự kiện dùng nhầm một eventId; hệ thống thực cần quyết định phát hiện hoặc từ chối trường hợp đó.

API tạo channel có message store nằm trong [MessageChannels 6.5.0](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/MessageChannels.html). API cấu hình advice nằm trong [TransactionInterceptorBuilder](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/transaction/TransactionInterceptorBuilder.html) và [PollerSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/PollerSpec.html).

### 7.1. Điều gì xảy ra khi ghi kết quả bị deadlock?

Giả sử PostgreSQL báo một lỗi được dịch thành TransientDataAccessException:

~~~text
retry advice
  -> begin transaction T1
  -> receive từ JDBC channel
  -> INSERT order_result bị deadlock
  -> exception truyền ra
  -> rollback T1: việc lấy message và thay đổi DB bị hoàn tác
  -> backoff ngoài T1
  -> begin transaction T2
  -> receive lại một công việc đang khả dụng
  -> xử lý thành công
  -> commit T2
~~~

Rollback cho phép công việc nhận dở quay lại trạng thái có thể được nhận. Trong môi trường nhiều consumer, không nên khẳng định attempt sau luôn lấy đúng cùng Message hoặc đúng cùng thứ tự: consumer khác có thể nhận trước, hoặc các quy tắc chọn dữ liệu có thể làm thay đổi thứ tự.

Yêu cầu schema, query provider và đặc điểm store được mô tả trong [JDBC Message Store](https://docs.spring.io/spring-integration/reference/6.5/jdbc/message-store.html).

### 7.2. Thông điệp đưa vào ví dụ

Producer có thể gửi một Message chứa String payload và eventId:

~~~java
orders.send(MessageBuilder.withPayload("ORDER-1042")
        .setHeader("eventId", "evt-1042")
        .build());
~~~

Trong ví dụ, payload và header được chọn đơn giản để phù hợp lưu trữ. Khi dùng serializer mặc định của JDBC store, payload và các header tùy chỉnh phải phù hợp với cơ chế serialization. Không đưa đối tượng tùy ý như connection hoặc service bean vào header để lưu bền.

### 7.3. Vì sao QueueChannel trong bộ nhớ không tương đương?

Với `new QueueChannel()`:

~~~text
receive A -> A bị lấy khỏi queue
handler lỗi
rollback transaction DB
retry receive -> có thể nhận B hoặc null
~~~

Transaction DB không tự đưa A trở lại queue trong bộ nhớ. Hậu quả có thể rất khó thấy: handler lỗi ở A, attempt sau nhận null và retry invocation kết thúc bình thường dù A chưa được xử lý.

Tương tự, rollback database không tự hoàn tác file đã chuyển, HTTP request đã gửi hoặc email đã phát. Đồng bộ callback sau transaction cũng không biến một tài nguyên không transactional thành tài nguyên có rollback. Vai trò đưa receive vào transaction được giải thích trong [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

## 8. Ranh giới thread và khả năng nhìn thấy lỗi

Retry advice chỉ bắt được exception đi qua phạm vi lời gọi mà nó bao quanh.

~~~mermaid
flowchart LR
    S["Nguồn transactional"] --> P["Poller: Retry bên ngoài Tx"]
    P --> D["DirectChannel"]
    D --> H["Handler đồng bộ"]
    H --> DB["Database trong cùng transaction"]
    P --> E["ExecutorChannel hoặc QueueChannel trung gian"]
    E --> W["Consumer ở thread khác"]
~~~

Hai nhánh trong sơ đồ minh họa hai cách đi tiếp khác nhau. Trong nhánh đồng bộ, exception có thể quay về poller. Trong nhánh bàn giao sang thread khác, poller thường chỉ quan sát được việc bàn giao.

Ví dụ:

~~~text
poller -> DirectChannel -> gọi đối tác thất bại
          exception quay về poller nếu không bị xử lý ở giữa

poller -> ExecutorChannel -> bàn giao thành công
                              |
                              +-> thread khác gọi đối tác thất bại
~~~

Ở ví dụ thứ hai, retry quanh poller không tự chạy lại do lỗi phát sinh muộn ở thread khác. Cần policy retry hoặc redelivery tại phía thực sự xử lý, cùng cơ chế báo lỗi phù hợp.

Nếu luồng có gateway được cấu hình biến lỗi thành phản hồi, filter loại bỏ Message, hoặc thành phần bắt exception và trả bình thường, poller cũng có thể thấy thành công. Với aggregator, việc nhận một phần và lưu trạng thái thành công không có nghĩa toàn bộ nhóm đã được tổng hợp và xử lý thành công; lỗi xảy ra khi nhóm hoàn tất cần được xét tại điểm đó.

Hành vi truyền exception giữa DirectChannel và các kênh bất đồng bộ được mô tả trong [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

## 9. Khi hết retry: rollback, báo lỗi và recovery

Cần quyết định rõ ba việc khác nhau:

1. Transaction hiện tại phải commit hay rollback?
2. Công việc có được nguồn giao lại hay không?
3. Lỗi được quan sát, lưu và xử lý ở đâu?

### 9.1. Để exception truyền ra

Trong cấu trúc Retry(Tx(...)), nếu không có recoverer và attempt cuối thất bại:

~~~text
attempt cuối lỗi
  -> transaction advice rollback
  -> retry advice ném lỗi cuối
  -> cơ chế xử lý lỗi của polling task nhận exception
  -> có thể phát ErrorMessage theo cấu hình error handler/error channel
~~~

Trong ví dụ JDBC, không cấu hình error channel riêng nên dùng cơ chế lỗi mặc định của Spring Integration. Trong demo phần 5, lỗi polling được đưa vào `pollErrors`.

Việc cấu hình error channel chỉ xác định nơi nhận thông báo lỗi. Nó không tự lên lịch xử lý lại, không tự tạo dead-letter queue và không tự giữ bản sao Message một cách bền vững.

### 9.2. Recovery trả bình thường có ý nghĩa nghiệp vụ

Recovery callback thường dùng để tạo kết quả thay thế hoặc chuyển thất bại sang một đường xử lý khác. Khi callback trả bình thường, bên ngoài có thể coi invocation đã được xử lý.

Vị trí recovery cần được xét cùng thứ tự advice:

| Cấu trúc | Recovery thông thường chạy ở đâu? | Cần chú ý |
|---|---|---|
| Retry(Tx(...)) | Sau khi transaction của attempt cuối kết thúc | Ghi bản ghi lỗi cần phạm vi lưu trữ/transaction riêng nếu yêu cầu bền vững |
| Tx(Retry(...)) | Trong transaction ngoài | Callback có thể góp phần tạo kết quả commit, hoặc vẫn thất bại vì rollback-only |

Recoverer của interceptor quanh poller cũng không đương nhiên nhận được Message nghiệp vụ như recoverer tại handler: lời gọi được advice có thể là polling task không có tham số Message. Nếu nguồn lỗi trước receive, thậm chí chưa tồn tại Message. Đừng ép mọi lỗi polling vào một cấu trúc giả định luôn có failedMessage.

### 9.3. Không tạo vòng lặp lỗi vô hạn

Một thiết kế dễ gặp:

~~~text
poller hết retry
  -> errorChannel
  -> gửi ngay về nguồn
  -> poller retry lại
  -> errorChannel
  -> ...
~~~

Cần một chính sách tổng thể theo eventId: số lần thất bại tích lũy, thời điểm xử lý tiếp, hạn chót và hành động cuối. Nếu cần lưu số lần thất bại qua các nhịp polling hoặc lần khởi động lại, thông tin đó phải nằm trong nguồn hoặc kho trạng thái thích hợp.

Đặc biệt, bộ đếm cập nhật trong chính transaction bị rollback sẽ mất cập nhật. Khi thiết kế bộ đếm bền vững, phải xác định rõ nó commit ở đâu và xử lý thế nào nếu cập nhật bộ đếm cũng thất bại.

## 10. Policy retry có giới hạn và có lý do

### 10.1. Phân loại lỗi theo khả năng thành công ở lần sau

| Lỗi | Hướng xử lý thường phù hợp | Điều kiện cần xem thêm |
|---|---|---|
| Deadlock, tranh chấp khóa tạm thời | Retry toàn đơn vị transactional | Rollback xong trước attempt tiếp theo |
| Lỗi kết nối nguồn ngắn hạn | Retry có backoff | Thời gian phục hồi nằm trong ngân sách |
| Timeout khi gọi dịch vụ ngoài | Retry có điều kiện | Có thể đối tác đã hoàn tất thao tác |
| Payload sai schema, thiếu eventId | Chuyển đường dữ liệu lỗi | Thử lại không sửa được payload |
| Sai thông tin xác thực hoặc cấu hình SQL | Báo lỗi cấu hình | Cần thay đổi cấu hình hoặc can thiệp |
| Message gây lỗi ổn định ở mọi lần | Cô lập theo chính sách | Không chặn vô hạn các Message khác |

Không dùng `Exception.class` cho mọi trường hợp chỉ vì cấu hình ngắn. Một lỗi được thư viện phân loại là transient vẫn cần được đánh giá theo ngân sách và tác dụng phụ của thao tác cụ thể.

### 10.2. Backoff là một phần của ngân sách thời gian

Với tối đa A attempt, nếu mỗi attempt có ngân sách T và thời gian chờ là b1 đến b(A-1):

~~~text
Thời gian chiếm luồng xấp xỉ
    <= A * T + b1 + b2 + ... + b(A-1) + chi phí phụ trợ
~~~

Đây chỉ là ước lượng khi từng attempt thực sự bị giới hạn thời gian. Transaction timeout không thay thế connect timeout, read timeout hoặc timeout của một thao tác I/O tùy ý.

Ví dụ ba attempt, mỗi attempt tối đa khoảng 800 ms, backoff 100 ms và 200 ms:

~~~text
3 * 800 + 100 + 200 = 2.700 ms, chưa tính chi phí phụ trợ
~~~

Nếu poller dùng fixedDelay một giây, nhịp tiếp theo trong cấu hình thực thi đồng bộ bắt đầu sau khi nhịp hiện tại xong và hết khoảng delay. Không kỳ vọng polling chính xác mỗi một giây khi một invocation đang mất gần ba giây.

Backoff chặn sẽ giữ luồng đang thực thi. Nếu nhiều poller dùng chung scheduler ít thread, một nguồn đang lỗi có thể làm các luồng khác chậm theo. Với thời gian chờ dài, cân nhắc cơ chế giao lại theo lịch thay vì giữ thread ngủ lâu. Jitter có thể giúp giảm các instance cùng thử lại một lúc, nhưng ví dụ ExponentialBackOffPolicy trong bài chưa bật ngẫu nhiên hóa.

### 10.3. Tránh nhân số lần gọi giữa nhiều tầng

Giả sử:

~~~text
HTTP client: tối đa 3 attempt
handler retry: tối đa 3 attempt
poller retry: tối đa 3 attempt
~~~

Trong đường đi xấu nhất, một lần polling có thể tạo tới `3 * 3 * 3 = 27` lần gọi HTTP nếu cả ba tầng đều bao quanh và lặp lại cùng thao tác đó. Redelivery ở nhịp sau còn có thể tăng tiếp.

Chọn một tầng chịu trách nhiệm chính cho mỗi loại lỗi, ghi rõ tổng ngân sách và tránh cấu hình nhiều policy độc lập mà không tính tác động cộng dồn.

## 11. Retry, redelivery và idempotency

Tình huống điển hình:

~~~text
attempt 1:
  POST tạo vận đơn -> đối tác đã tạo
  kết nối đứt trước khi phản hồi đến ứng dụng
  ứng dụng thấy timeout

attempt 2:
  POST tạo vận đơn lần nữa
~~~

Database rollback ở phía ứng dụng không xóa vận đơn đã tạo ở đối tác. Để kiểm soát trường hợp này, có thể dùng eventId làm idempotency key nếu API đối tác hỗ trợ, hoặc đối soát kết quả bằng định danh yêu cầu ổn định.

Đối với xử lý chỉ trong cùng database, có thể dùng unique constraint kết hợp thao tác ghi nghiệp vụ trong cùng transaction. Ví dụ `order_result` ở phần 7 chỉ tạo một kết quả cho mỗi eventId. Nếu nghiệp vụ còn nhiều cập nhật khác, dấu đã xử lý và các cập nhật đó cần cùng ranh giới nguyên tử.

Các định danh cần phân biệt:

| Định danh | Ý nghĩa |
|---|---|
| MessageHeaders.ID | Định danh của một Message trong Spring Messaging |
| eventId hoặc business key | Định danh ổn định của sự kiện hoặc thao tác nghiệp vụ |
| Retry attempt | Số lần thực thi trong một retry invocation |
| Delivery attempt | Số lần nguồn đã giao công việc theo chính sách nguồn |

Khi nguồn tạo một Message mới cho cùng sự kiện, MessageHeaders.ID có thể đổi. Không mặc định dùng nó để chống trùng nghiệp vụ qua mọi lần giao lại.

Stateful retry cho phép liên kết trạng thái retry giữa các lần gửi lại bằng một khóa ổn định, nhưng không tự làm broker hoặc nguồn giao lại. Cũng cần xem trạng thái retry có bền vững qua restart hay không. Trong bài, interceptor được tạo theo kiểu stateless; nó không duy trì giới hạn xuyên suốt các nhịp polling.

## 12. Kiểm chứng ví dụ và hành vi transactional

Các đoạn kiểm thử dưới đây là hướng dẫn thực hành; bài không giả định chúng đã được chạy trên môi trường dự án của bạn.

### 12.1. Kiểm tra nguồn lỗi tạm thời rồi phát một Message

Với lớp PollerRetryDemo ở phần 5 và JUnit Jupiter:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class PollerRetryDemoTest {

    @Test
    void retriesSourceFailuresBeforePublishing() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(PollerRetryDemo.class)) {

            QueueChannel results =
                    context.getBean("demoResults", QueueChannel.class);
            QueueChannel errors =
                    context.getBean("pollErrors", QueueChannel.class);
            AtomicInteger counter =
                    context.getBean("sourceReadCounter", AtomicInteger.class);

            Message<?> result = results.receive(5_000);

            assertNotNull(result);
            assertEquals("ORDER-1042", result.getPayload());
            assertEquals("evt-1042", result.getHeaders().get("eventId"));
            assertEquals(3, counter.get());
            assertNull(errors.receive(0));
        }
    }
}
~~~

Kiểm thử chờ kết quả trên channel với timeout hữu hạn. Nó không khẳng định chính xác thời gian backoff bằng đồng hồ thực. Giới hạn năm giây là thời gian chờ kiểm thử, không phải timeout của policy retry.

Đây là kiểm thử phạm vi retry đọc nguồn. Nó chưa kiểm chứng rollback, JDBC store hoặc việc gọi lại cùng Message sau lỗi downstream.

### 12.2. Các tình huống cần thử với database thật phù hợp

| Tình huống | Cách tạo lỗi có kiểm soát | Bằng chứng cần thu |
|---|---|---|
| Lỗi transient rồi thành công | Handler ném TransientDataAccessException hai lần đầu | Có rollback trước attempt sau; một kết quả cuối được commit |
| Lỗi luôn xảy ra | Handler luôn ném lỗi transient | Ba attempt trong invocation; công việc vẫn có thể được nhận lại sau rollback |
| Lỗi không retryable | Handler ném IllegalArgumentException | Một attempt trong invocation; đi đường lỗi |
| Phân biệt hai thứ tự advice | Đổi vị trí pollRetry và pollTransaction trong cấu hình thử nghiệm | Transaction bắt đầu/kết thúc và rollback-only có đúng kỳ vọng |
| Queue trong bộ nhớ | Nhận A rồi gây lỗi downstream | A không tự quay lại chỉ vì DB rollback |
| Ranh giới bất đồng bộ | Đưa handler lỗi sau ExecutorChannel | Lỗi không tự quay lại poller đã bàn giao xong |
| Giao lại cùng eventId | Gửi lại cùng sự kiện | Không tạo thêm order_result |
| Lỗi trước receive | Nguồn ném exception trước khi tạo Message | Đường lỗi không giả định luôn có failedMessage |

Để đếm đúng một retry invocation với scheduler đang chạy, nên kiểm soát lifecycle endpoint hoặc tạm dừng sau khi nhận lỗi kết thúc invocation. Nếu cứ để poller chạy, nhịp sau có thể làm bộ đếm vượt ba và khiến kết luận kiểm thử sai.

Khi đo transaction, có thể ghi nhận TransactionSynchronization hoặc sự kiện begin/commit/rollback từ transaction manager được bọc để quan sát. Chỉ kiểm tra `isActualTransactionActive()` là chưa đủ chứng minh các attempt thuộc các transaction khác nhau.

Không dùng một kiểm thử ngoài cùng `@Transactional` rồi suy ra transaction của scheduler thread: context transaction của test thread không tự truyền sang thread poller. Với SQL và khóa của PostgreSQL, nên kiểm thử trên PostgreSQL thay vì suy luận hoàn toàn từ một database có hành vi khác.

## 13. Quan sát và chẩn đoán

Một bản ghi quan sát hữu ích có thể chứa:

~~~text
endpoint=ordersPollingConsumer
eventId=evt-1042
retryInvocation=local-cycle-17
attempt=2
maxAttempts=3
exception=TransientDataAccessException
outcome=ROLLBACK
nextBackoffMs=200
~~~

Đây là định dạng gợi ý của ứng dụng, không phải log mặc định mà Spring tự bảo đảm sinh ra. Trước receive, eventId có thể chưa có; khi đó ưu tiên endpoint, thông tin nguồn và mã tương quan của lần polling.

Các chỉ số nên theo dõi gồm số invocation cần retry, số attempt, số invocation hết retry, thời gian xử lý gồm backoff, tuổi của công việc chưa xong và số lần giao lại theo eventId. Không đặt eventId làm nhãn metric có số lượng giá trị không giới hạn; dùng nó trong log hoặc trace để tra cứu.

| Biểu hiện | Khả năng cần kiểm tra |
|---|---|
| Cấu hình ba attempt nhưng log có hàng chục lần | Có nhiều nhịp poll, nhiều tầng retry hoặc redelivery |
| Retry báo thành công nhưng mất dữ liệu | Attempt mới receive null từ nguồn không rollback được |
| UnexpectedRollbackException sau khi handler thành công | Transaction dùng chung đã bị đánh dấu rollback-only |
| Không thấy retry khi handler lỗi | Lỗi ở thread khác, bị chuyển thành phản hồi hoặc bị bắt ở giữa |
| Các poller khác bị chậm | Backoff hoặc I/O đang chiếm scheduler thread |
| Cùng thao tác đối tác được thực hiện nhiều lần | Phạm vi retry rộng và thiếu idempotency |
| Có ErrorMessage nhưng công việc không chạy lại | Error channel chưa được gắn với chính sách giao lại |

## 14. Quy trình ra quyết định

Trước khi thêm retry quanh poller, hãy trả lời theo thứ tự:

1. **Thao tác nào được phép lặp?** Chỉ đọc nguồn, một handler hay cả đơn vị nhận và xử lý?
2. **Nguồn có thể giao lại bằng cách nào?** Rollback transactional receive, cơ chế broker hay logic ứng dụng?
3. **Tài nguyên nào cùng transaction?** Xác định transaction manager và các DataSource hoặc resource tham gia.
4. **Exception có quay về advice không?** Kiểm tra thread boundary và các thành phần chuyển lỗi thành kết quả.
5. **Attempt sau bắt đầu trong trạng thái nào?** Transaction trước đã kết thúc hay còn rollback-only?
6. **Thử lại bao lâu và bao nhiêu lần?** Tính cả retry ở client, handler, poller và các lần giao lại.
7. **Khi không thể thành công thì làm gì?** Lưu thất bại, cô lập, đối soát hoặc yêu cầu can thiệp theo chính sách cụ thể.
8. **Tác dụng phụ có chịu được thực hiện lại không?** Dùng định danh nghiệp vụ và idempotency ở đúng nơi.
9. **Bằng chứng kiểm chứng là gì?** Quan sát attempt, transaction, dữ liệu đã commit và trạng thái nguồn.

Retry quanh poller phù hợp khi phạm vi lặp khớp với đơn vị công việc có thể thực hiện lại. Để áp dụng đúng, cần xác định đồng thời lời gọi được advice bao quanh, khả năng rollback của nguồn và tác dụng phụ của các endpoint trong luồng.
