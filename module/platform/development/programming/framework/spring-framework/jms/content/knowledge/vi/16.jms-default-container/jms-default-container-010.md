# ErrorHandler và ExceptionListener trong DefaultMessageListenerContainer (Spring JMS)

> **Chủ đề cha:** Default container — Spring Framework JMS.  
> **Mục tiêu:** Phân biệt `org.springframework.util.ErrorHandler` và `jakarta.jms.ExceptionListener`; hiểu lỗi nghiệp vụ, lỗi chuyển đổi message, lỗi JMS/infrastructure và lỗi kết nối đi qua những kênh nào; cấu hình hai callback qua `DefaultJmsListenerContainerFactory` / `DefaultMessageListenerContainer`; thiết kế rollback, redelivery, DLQ, phục hồi kết nối và quan sát hệ thống mà không làm mất message.

**Ngữ cảnh phiên bản:** Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging 3.1, Java 17+ và ví dụ Apache ActiveMQ Artemis. API dùng `jakarta.jms` (không phải `javax.jms` của các stack Java EE/JMS cũ).

**Ý tưởng lớn:** Hai callback này chủ yếu giúp **phát hiện và báo cáo lỗi**. Chúng **không tự quyết định** JMS transaction có được commit, message được ACK hay retry bao nhiêu lần. Quyết định đó thuộc listener container, cấu hình session/transaction và policy broker.

## 1. Cùng gọi là "lỗi" nhưng nằm ở các tầng khác nhau

Trong Spring JMS, một message đi qua nhiều tầng:

~~~text
Producer -> Broker / Queue
               |
               v
      JMS Connection / Session / Consumer
               |
       DefaultMessageListenerContainer
               |
      JMS-to-Spring message conversion
               |
            @JmsListener
               |
          Business handler
               |
      JMS commit / rollback / ACK
~~~

Tùy nơi phát sinh, cùng một triệu chứng “listener không nhận được việc” có thể do những nguyên nhân rất khác nhau:

1. **Lỗi nghiệp vụ:** handler ném `IllegalStateException` do DB lỗi, dữ liệu không hợp lệ, API downstream timeout, invariant bị vi phạm.
2. **Lỗi convert/bind:** JSON không đúng schema, `@Header` thiếu, `MessageConverter` ném exception trước khi vào body handler.
3. **JMSException ở đường nhận:** tạo consumer/session, nhận message, giao dịch JMS hoặc các thao tác JMS API xảy ra lỗi.
4. **Lỗi kết nối bất đồng bộ:** provider phát hiện kết nối gặp sự cố và có thể thông báo qua `jakarta.jms.ExceptionListener` gắn trên `Connection`.
5. **Lỗi khởi tạo hoặc recovery:** broker unavailable, sai URL/credential, destination không tồn tại, session recreation, connection retry, resource exhaustion.
6. **Lỗi vận hành:** queue backlog, message hết TTL, poison message bị chuyển DLQ, listener đã stop, concurrency bằng 0, worker chết.
7. **Lỗi publisher:** `JmsTemplate.convertAndSend(...)` ném exception trên thread gửi, vốn không thuộc callback của một listener container độc lập.

Vì vậy, thiết kế chỉ có `ErrorHandler` hoặc chỉ có `ExceptionListener` là **chưa đủ** cho khả năng phục hồi. Trước hết phải phân loại lỗi và hiểu **thời điểm commit/rollback**.

## 2. So sánh nhanh ErrorHandler và ExceptionListener

| Tiêu chí | Spring `ErrorHandler` | Jakarta JMS `ExceptionListener` |
| --- | --- | --- |
| Kiểu interface | `org.springframework.util.ErrorHandler` | `jakarta.jms.ExceptionListener` |
| Phương thức | `handleError(Throwable t)` | `onException(JMSException ex)` |
| Phạm vi dữ liệu | `Throwable`, gồm nhiều lỗi runtime/adapter | `JMSException`, lỗi JMS-related được chuyển vào callback |
| Khi dùng trong Spring container | Theo dõi uncaught errors trong xử lý JMS message | Nhận thông báo về JMSException qua listener container theo API Spring |
| Khi gắn trực tiếp vào JMS Connection | Không phải callback `Connection` | Provider có thể gọi **bất đồng bộ** khi connection gặp sự cố |
| Có tự rollback JMS session? | **Không** | **Không** |
| Có tự đẩy message vào DLQ? | **Không** | **Không** |
| Có tự sửa kết nối? | **Không** | **Không** |
| Chỗ cấu hình trên Spring factory | `factory.setErrorHandler(...)` | `factory.setExceptionListener(...)` |
| Chỗ cấu hình trên container | `container.setErrorHandler(...)` | `container.setExceptionListener(...)` |
| Mục đích điển hình | Log, metric, alert cho lỗi xử lý message | Log, metric, alert cho JMS-related error |
| Bẫy hay gặp | Tưởng callback nhận lỗi rồi phải tự throw để rollback | Tưởng callback bắt mọi business exception hoặc mọi broker outage |

**Điều rất quan trọng:** `DefaultMessageListenerContainer` là một **polling message listener container** có cơ chế tự recovery. Callback `ExceptionListener` trên Spring container và callback bất đồng bộ do JMS provider thực hiện trên `Connection` là **hai ngữ cảnh API cần phân biệt**; không nên suy ra rằng cứ broker ngắt mạng thì mọi triển khai đều gọi đúng một callback ở đúng một thời điểm.

### 2.1. Chữ ký Java chính xác

~~~java
@FunctionalInterface
public interface ErrorHandler {
    void handleError(Throwable t);
}
~~~

Đây là **chữ ký được rút gọn để học**, không phải mã định nghĩa Spring mà ứng dụng cần copy. Spring đã cung cấp interface `org.springframework.util.ErrorHandler`.

~~~java
@FunctionalInterface
public interface ExceptionListener {
    void onException(JMSException exception);
}
~~~

Đây là **chữ ký rút gọn** của `jakarta.jms.ExceptionListener`, không phải code tự tạo interface trùng tên. `JMSException` thuộc `jakarta.jms`.

### 2.2. Vì sao khác nhau về tham số?

`Throwable` bao quát lỗi runtime trong listener và một số lỗi tầng adapter. `JMSException` là một checked exception chuyên biệt của JMS provider/API, thường có `getErrorCode()`, `getLinkedException()` và `getCause()` để truy vết.

Bạn không thể đưa mọi `IllegalArgumentException` nghiệp vụ vào `onException(JMSException)` mà không biến nó thành JMSException ở tầng của mình; làm vậy thường gây nhầm phân loại lỗi.

## 3. Luồng xử lý lỗi trong AbstractMessageListenerContainer

`DefaultMessageListenerContainer` kế thừa `AbstractPollingMessageListenerContainer` và `AbstractMessageListenerContainer`. Javadoc Spring 6.2 mô tả rằng lỗi do listener ném **không tự được propagate nguyên vẹn cho JMS provider** như trong một callback API thô; container xử lý acknowledgement/transaction và ghi nhận lỗi.

Khi một handler ném unchecked exception:

~~~text
Receive JMS Message
       |
       v
Invoke @JmsListener / MessageListener
       |
       +--> thành công --> commit/ack theo session policy
       |
       +--> lỗi
               |
               v
       rollback nếu transaction/ack mode yêu cầu
               |
               v
       Spring handleListenerException(Throwable)
               |
       +-------+--------+
       |                |
    ErrorHandler     Log mặc định nếu
    (nếu có)         không có handler
~~~

Thứ tự cụ thể đối với từng loại exception, transaction manager và container subtype phải đọc theo API/source của phiên bản đang chạy. Quy tắc thiết kế **không thay đổi** là: callback quan sát lỗi **không được dùng như công tắc quyết định lại việc commit** sau khi container đã xử lý nó.

### 3.1. Lỗi JMSException có thể đi qua cả hai callback

Javadoc `AbstractMessageListenerContainer` cho biết khi `JMSException` phát sinh trong listener/invocation infrastructure và đi vào error dispatch của container, `ExceptionListener` được thông báo, **sau đó** `ErrorHandler` cũng có thể được gọi. Vì vậy:
- Không coi hai bộ đếm là hai loại lỗi loại trừ nhau.
- Một JMSException có thể tạo **hai log/metric events**.
- Để tránh đếm trùng, cần phân loại/ghép sự kiện theo context hoặc bảo đảm metric có nhãn.
- Không khẳng định mọi lỗi provider asynchronous đều chảy qua cùng đường dispatch như JMSException trong listener.

### 3.2. Khi chỉ có ErrorHandler

Nếu handler ném:

~~~java
throw new IllegalStateException("Database temporarily unavailable");
~~~

đây là unchecked application exception. Nó phù hợp với phạm vi `ErrorHandler`, **không phải** `jakarta.jms.ExceptionListener` theo chuẩn chỉ nhận `JMSException`. Một `ExceptionListener` đăng ký đúng vẫn có thể không được gọi trong kịch bản này, và đó **không phải** dấu hiệu cấu hình sai.

### 3.3. Nếu không cấu hình ErrorHandler

Spring container thường log exception theo default behavior, không làm JVM tự dừng chỉ vì một message handler ném unchecked exception. Điều này có thể khiến service nhìn “vẫn healthy” nhưng broker liên tục redeliver một poison message. Việc cài custom `ErrorHandler` hữu ích để ghi metric/alert, nhưng **không thay thế** cấu hình DLQ/transaction.

## 4. API ErrorHandler và trách nhiệm đúng

Trong Spring Framework:

~~~java
import org.springframework.util.ErrorHandler;

ErrorHandler handler = throwable -> {
    // Ghi log/metric/trace; xử lý nhanh, thread-safe.
};
~~~

Đây là mảnh Java, không phải app độc lập. Tham số `throwable` có thể là exception nghiệp vụ hoặc wrapper exception do Spring adapter sinh ra. Đừng chỉ phân loại theo class của outer exception; có thể cần duyệt `getCause()` một cách có giới hạn.

### 4.1. Những việc nên làm

- Ghi error category rõ (`CONVERSION`, `BUSINESS_TRANSIENT`, `BUSINESS_PERMANENT`, `JMS_API`).
- Ghi exception class, root cause và stack trace với sampling/hạn mức phù hợp.
- Tăng counter theo listener factory/endpoints hoặc destination được biết từ context.
- Đánh dấu tracer span/micrometer observation nếu hệ thống có.
- Alert khi tỉ lệ lỗi vượt ngưỡng, thay vì alert từng message.
- Bảo vệ handler khỏi tác vụ chậm: báo log/metric nhanh, không gọi API ngoài network một cách blocking.
- Giữ handler **thread-safe** vì nhiều JMS listeners có thể chia sẻ cùng factory/callback.
- Tránh log payload chứa PII, token hoặc dữ liệu người dùng; có thể log sanitized message metadata khi khả dụng.

### 4.2. Những việc không nên làm

- Không gọi `session.commit()`, `rollback()`, `acknowledge()` hoặc `close()` từ `ErrorHandler` khi không có contract quản lý session.
- Không tự gửi lại nguyên message dựa vào throwable mà không có JMS message/transaction context: dễ tạo duplicate.
- Không tự gọi `container.stop()` hay thoát JVM trong callback theo mọi loại exception.
- Không bắt hết lỗi trong listener rồi return bình thường chỉ để “không kích hoạt ErrorHandler”; điều đó có thể khiến transaction commit dù nghiệp vụ chưa xong.
- Không để `ErrorHandler` throw tiếp unchecked exception như một cơ chế “yêu cầu retry”: container đã có đường xử lý rollback, callback throw có thể chỉ gây lỗi phụ hoặc che mất root cause.
- Không dùng `ErrorHandler` làm global business exception mapper của REST/API/scheduled tasks; nó có phạm vi JMS listener container đã cấu hình.

### 4.3. Ví dụ callback chỉ quan sát

~~~java
@Bean
ErrorHandler listenerErrorHandler() {
    return ex -> {
        String category =
                ex instanceof IllegalArgumentException
                        ? "VALIDATION_OR_CONTRACT"
                        : "LISTENER_OR_ADAPTER";
        System.err.println("JMS_ERROR category=" + category
                + " class=" + ex.getClass().getSimpleName());
    };
}
~~~

Đây là **Spring @Bean method** chứ không phải chương trình Java độc lập. Cần imports `@Bean` và `ErrorHandler`; production thay stdout bằng structured logging và metrics. Không suy luận các lỗi wrapper là `IllegalArgumentException` chỉ dựa trên cause ngoài cùng.

## 5. API ExceptionListener theo Jakarta Messaging

`jakarta.jms.ExceptionListener` dành cho trường hợp JMS provider/connection phát hiện lỗi bất đồng bộ nghiêm trọng:

~~~java
import jakarta.jms.ExceptionListener;
import jakarta.jms.JMSException;

ExceptionListener listener = exception -> {
    // Callback từ JMS; làm việc nhanh và an toàn với thread.
    String code = exception.getErrorCode();
    Exception linked = exception.getLinkedException();
    // Log/metrics; không dựa vào connection đã lỗi.
};
~~~

JMS specification nêu:
- Provider có thể thông báo một **vấn đề của Connection** qua `Connection.getExceptionListener().onException(JMSException)` khi không có nơi nào khác phù hợp để báo lỗi.
- Nếu một lệnh JMS trên thread gọi đã ném exception **đồng bộ**, provider không được coi việc gọi callback bất đồng bộ là thay thế cho việc throw trên thread đó.
- Provider nên thử giải quyết sự cố kết nối trước khi báo callback.
- Các callback trên **cùng một Connection** được serialize bởi provider; **cùng một listener object gắn vào nhiều Connection** vẫn có thể được gọi đồng thời.
- Một callback xảy ra **không bảo đảm** connection vẫn dùng được để tiếp tục JMS operations.

### 5.1. Ví dụ gắn trên Connection do chính bạn sở hữu

~~~java
// Mảnh Java trong ứng dụng JMS trực tiếp, không dùng shared
// connection đang do Spring listener container quản lý.
Connection connection = connectionFactory.createConnection();
try {
    connection.setExceptionListener(ex -> {
        System.err.println("ASYNC_JMS_FAILURE code="
                + ex.getErrorCode());
    });

    connection.start();
    // Tạo Session/Consumer và dùng theo lifecycle của app.
} finally {
    connection.close();
}
~~~

Cần imports `jakarta.jms.Connection`, `ConnectionFactory`, `JMSException`; phương thức bao quanh phải khai báo hoặc catch `JMSException`. Đây là **mảnh code minh họa**, không phải class độc lập. `connection.setExceptionListener` phải được dùng **theo ownership**: đừng lấy shared `Connection` từ container hay pooling/caching wrapper rồi gán listener mới, vô tình ghi đè callbacks của hạ tầng.

### 5.2. ExceptionListener của Spring container và của Connection

Với Spring:

~~~java
factory.setExceptionListener(ex -> {
    // Spring listener-container JMSException notification.
});
~~~

API trên đặt callback mà container sử dụng theo Javadoc `AbstractMessageListenerContainer`, bao gồm JMSException từ registered listener/invocation infrastructure. Nó **không phải cam kết** rằng mọi lần socket bị đứt, mọi lần destination lookup fail, hoặc mọi asynchronous provider exception đều đi qua callback này giống hệt việc đặt `Connection.setExceptionListener` trên một connection do app sở hữu.

**Hãy quan sát thêm** recovery logs, broker connectivity health, failed receive/setup metrics và trạng thái containers. Không dùng số lần `onException` bằng 0 để khẳng định broker không từng lỗi.

## 6. Cấu hình trực tiếp trên DefaultMessageListenerContainer

Nếu tự tạo container Java bean thay vì `@JmsListener`:

~~~java
@Bean
DefaultMessageListenerContainer ordersContainer(
        ConnectionFactory connectionFactory,
        MessageListener ordersListener,
        ErrorHandler errorHandler,
        ExceptionListener exceptionListener) {

    var container = new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.in");
    container.setMessageListener(ordersListener);
    container.setSessionTransacted(true);
    container.setConcurrency("1");
    container.setErrorHandler(errorHandler);
    container.setExceptionListener(exceptionListener);
    return container;
}
~~~

Đây là **mảnh method** trong Spring `@Configuration`, cần imports:
- `jakarta.jms.ConnectionFactory`, `MessageListener`, `ExceptionListener`;
- `org.springframework.jms.listener.DefaultMessageListenerContainer`;
- `org.springframework.util.ErrorHandler`;
- `org.springframework.context.annotation.Bean`.

Container bean này tự tham gia Spring lifecycle. Đừng vừa tạo trực tiếp container như trên **vừa** thêm `@JmsListener` cùng queue rồi tưởng đó chỉ là một consumer: bạn sẽ có hai consumer cạnh tranh trên Queue.

### 6.1. Khi nào dùng container trực tiếp?

- Đã có code quản lý raw `jakarta.jms.MessageListener` và muốn tích hợp Spring lifecycle.
- Cần control cao về poll/cache/recovery/session/executor.
- Endpoint không phù hợp annotation mechanism.
- Muốn tách nhiều factories/listeners theo policy khác nhau.

Với `@JmsListener`, cách dễ dùng hơn là cấu hình **`DefaultJmsListenerContainerFactory`** cho annotation endpoint. Đây là phần chính của bài tập tiếp theo.

## 7. Cấu hình cho @JmsListener qua DefaultJmsListenerContainerFactory

`DefaultJmsListenerContainerFactory` kế thừa `AbstractJmsListenerContainerFactory` và có hai setter:

~~~java
factory.setErrorHandler(errorHandler);
factory.setExceptionListener(exceptionListener);
~~~

Các callback được áp cho `DefaultMessageListenerContainer` được tạo từ factory. Một factory có thể được nhiều `@JmsListener` sử dụng, nên:
- Một `ErrorHandler` có thể nhận lỗi từ nhiều endpoints.
- Một `ExceptionListener` có thể nhận JMSException từ nhiều containers.
- Nếu cần phân biệt rõ chính sách/budget/metric của hai nhóm, dùng **hai factories** hoặc thêm context được cung cấp đáng tin cậy.
- `@JmsListener(containerFactory = "someFactory")` quyết định factory thực sự dùng. Một bean `ErrorHandler` tồn tại trong context **không tự bảo đảm** factory đang dùng đã gắn handler đó.

Ví dụ cấu hình tường minh:

~~~java
@Configuration(proxyBeanMethods = false)
class JmsListenerFactoryConfiguration {

    @Bean("reliableListenerFactory")
    DefaultJmsListenerContainerFactory reliableListenerFactory(
            ConnectionFactory connectionFactory,
            ErrorHandler handler,
            ExceptionListener jmsExceptions) {

        var result = new DefaultJmsListenerContainerFactory();
        result.setConnectionFactory(connectionFactory);
        result.setSessionTransacted(true);
        result.setConcurrency("1-3");
        result.setErrorHandler(handler);
        result.setExceptionListener(jmsExceptions);
        return result;
    }
}
~~~

Đây là class Spring **minh họa**, cần imports `@Configuration`, `@Bean`, `ConnectionFactory`, `ExceptionListener`, `ErrorHandler` và `DefaultJmsListenerContainerFactory`. Với Spring Boot 3.5, có thể dùng `DefaultJmsListenerContainerFactoryConfigurer` để giữ các defaults của Boot; lab bên dưới làm như vậy.

### 7.1. Tránh hai lỗi injection phổ biến

1. **Nhiều ExceptionListener beans:** `@Qualifier` để chọn listener đúng factory; đừng để Spring chọn theo type khi có nhiều bean.
2. **Không dùng factory bạn vừa cấu hình:** nếu annotation ghi `containerFactory="jmsListenerContainerFactory"` nhưng bạn chỉ gắn callback trên bean `reliableListenerFactory`, endpoint vẫn không sử dụng callback mới.

Nếu hệ thống khai báo default `jmsListenerContainerFactory` và một factory tên khác, hãy kiểm tra ID/factory mapping qua config/integration tests thay vì đoán theo bean name.

## 8. DefaultJmsListenerContainerFactoryConfigurer của Spring Boot 3.5

Spring Boot tạo `JmsTemplate`, `ConnectionFactory` và một default factory khi đủ hạ tầng. Nếu bạn tự định nghĩa factory, có thể reuse Spring Boot settings qua:

~~~java
@Bean("observedListenerFactory")
DefaultJmsListenerContainerFactory observedListenerFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer,
        ErrorHandler handler,
        ExceptionListener jmsExceptions) {

    var factory = new DefaultJmsListenerContainerFactory();
    configurer.configure(factory,
        ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    factory.setErrorHandler(handler);
    factory.setExceptionListener(jmsExceptions);
    return factory;
}
~~~

Đây là **mảnh method Spring Boot 3.5**, cần imports:
- `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`
- `org.springframework.boot.jms.ConnectionFactoryUnwrapper`
- `org.springframework.jms.config.DefaultJmsListenerContainerFactory`
- `jakarta.jms.ConnectionFactory`, `jakarta.jms.ExceptionListener`
- `org.springframework.util.ErrorHandler`

**Thứ tự quan trọng:** gọi `configurer.configure(...)` **trước**, rồi override transaction, concurrency, handlers theo contract. `ConnectionFactoryUnwrapper.unwrapCaching(...)` là utility Boot 3.5 để tránh chuyển một wrapper caching vào listener container vốn đã tự quản lý cache/recovery. Đừng tự đoán rằng unwrap phù hợp mọi custom provider nếu ứng dụng có nhiều lớp wrapper chuyên biệt; kiểm thử cấu hình thật.

### 8.1. Tại sao cần sessionTransacted?

Nếu listener ném exception mà JMS session đang transacted, Spring container có thể rollback để broker giao lại message theo policy. Với default `AUTO_ACKNOWLEDGE` trên `DefaultMessageListenerContainer`, container có thể ACK **trước khi listener chạy**, nên exception không tự tạo reliable redelivery.

Cấu hình:

~~~java
factory.setSessionTransacted(true);
~~~

không gắn ErrorHandler với rollback theo quan hệ nhân quả. **Rollback là quyết định của container và transaction**, còn handler ghi lại lỗi.

## 9. Ma trận lỗi: callback nào được kỳ vọng?

| Tình huống | ErrorHandler | ExceptionListener | Kết quả giao nhận phụ thuộc |
| --- | --- | --- | --- |
| Handler ném `IllegalStateException` | Thường được gọi khi lỗi ra khỏi listener | Không phải đường chuẩn cho RuntimeException | JMS transaction/ACK và broker retry |
| Conversion `MessageConversionException` trước method | Có thể được gọi nếu lỗi đi vào listener container | Không tự là JMSException | Converter, transaction, DLQ |
| Header/argument resolver fail | Có thể qua listener error path | Không mặc định | Listener adapter, transaction |
| Handler trực tiếp ném `JMSException` | Spring có đường thông báo JMSException | Có thể được gọi theo Javadoc khi JMSException đi vào đường xử lý | Cách adapter wrap và container nhận lỗi |
| Container JMS session receive/commit exception | Tùy điểm phát sinh và error-dispatch | Tùy cơ chế notify của Spring/container | Recovery, session & broker |
| Broker mất kết nối đột ngột | Không đảm bảo được gọi cho mỗi outage | JMS provider có thể báo async; Spring container recovery là kênh riêng | Reconnect/backoff, broker health |
| `JmsTemplate.send(...)` trên thread khác ném `JmsException` | Không thuộc factory listener đó | Không thuộc factory listener đó | Caller retry/outbox |
| Poison message liên tục redeliver | Có thể gọi nhiều lần | Không nhất thiết | Max delivery attempts / DLQ |
| Lỗi disk/quota trên broker | Không bảo đảm | Không bảo đảm với mọi loại lỗi | Broker metrics/alerts |
| Lỗi `ErrorHandler` tự ném exception | Có thể gây lỗi phụ | Không nên dùng để đo phản hồi | Container logging/handling |

**Bảng là hướng quan sát, không phải một bảo đảm mọi path sẽ gọi đúng một callback.** Mỗi container implementation, JMS provider, error-wrapper và transaction manager có thể làm thay đổi thứ tự/đường dispatch. Test với stack thực tế.

### 9.1. Lỗi có root cause JMSException nhưng wrapper là RuntimeException

Một `JMSException` có thể được Spring chuyển thành unchecked `JmsException` hoặc bị bao bởi `ListenerExecutionFailedException`. Phân loại bằng duyệt cause chain (có giới hạn) thay vì chỉ `instanceof JMSException` với outer throwable:

~~~java
static boolean hasJmsCause(Throwable throwable) {
    for (int depth = 0; throwable != null && depth < 10;
            depth++, throwable = throwable.getCause()) {
        if (throwable instanceof jakarta.jms.JMSException) {
            return true;
        }
    }
    return false;
}
~~~

Đây là **mảnh static Java method**, không phải app độc lập. `getCause()` có thể chứa exception lồng sâu; tránh vòng lặp vô hạn khi một Throwable tùy biến trả cause bất thường. Nếu cần metadata JMS-specific, `JMSException.getLinkedException()` có thể chứa lỗi provider bổ sung ngoài `getCause()`.

## 10. Transaction và thứ tự commit/rollback quyết định retry

### 10.1. Với Session transacted

~~~text
Message được nhận trong JMS Session transacted
                    |
                    v
               Invoke listener
                 /      \
            Success      Exception
               |             |
               v             v
          JMS commit      JMS rollback
               |             |
          ACK/complete     Eligible for redelivery
                              |
                        ErrorHandler quan sát
~~~

Đây là giản đồ ý định. Nếu session commit/rollback chính nó lỗi, luồng phát sinh thêm JMSException, recovery và trạng thái broker cần đối soát. Callback không xác nhận rằng transaction chắc chắn đã kết thúc thành công.

**Quy tắc nghiệp vụ:** Nếu xử lý thất bại và muốn redelivery, hãy để exception đi ra khỏi listener để container thấy thất bại; đừng bắt exception rồi return như thành công.

~~~java
@JmsListener(destination = "invoices.commands")
public void onInvoice(String invoiceId) {
    invoiceService.createInvoice(invoiceId);
    // Nếu thất bại, ném exception để container rollback theo policy.
}
~~~

Mảnh code trên cần service và container được cấu hình transacted. Nó **không** là file Java độc lập.

### 10.2. Phản ví dụ nuốt lỗi

~~~java
@JmsListener(destination = "invoices.commands")
public void onInvoice(String invoiceId) {
    try {
        invoiceService.createInvoice(invoiceId);
    } catch (RuntimeException ex) {
        logger.error("Invoice failed", ex);
        // Return bình thường: container có thể commit message!
    }
}
~~~

Đây là **phản ví dụ có chủ đích**. Không nên dùng cho công việc không được phép mất. Một `ErrorHandler` của container **không được gọi** nếu lỗi đã bị handler nuốt và method trả về bình thường.

### 10.3. Vì sao vẫn cần idempotency?

Nếu:
1. Handler ghi DB thành công.
2. JVM chết trước khi JMS session commit.
3. Broker phát lại message.

...thì business side effect có thể lặp dù `ErrorHandler`/`ExceptionListener` được cấu hình hoàn hảo. Giải pháp: event ID ổn định, inbox/dedup với unique constraint, transaction DB rõ ràng, transactional outbox cho producer, reconciliation process và DLQ.

### 10.4. Session transacted không phải XA

`factory.setSessionTransacted(true)` là **local JMS transaction**. Nó không tự gộp DB transaction hoặc HTTP API vào một global transaction. Dùng `@Transactional` trên một service DB có thể đảm bảo transaction DB, nhưng sự đồng bộ hóa giữa hai commit phải được thiết kế/kiểm thử. Khi cần coordinated XA/JTA, phải dùng transaction manager/provider phù hợp và hiểu độ phức tạp recovery.

## 11. Broker retry, redelivery và DLQ khác ErrorHandler

Một `ErrorHandler` có thể ghi nhận mỗi lần listener thất bại, nhưng số lần **message được giao lại** phụ thuộc broker:

- Đối với JMS transacted session rollback, broker/provider quyết định redelivery delay, max attempts và hành vi chuyển dead-letter destination.
- `JMSRedelivered` và `JMSXDeliveryCount` có thể giúp phân biệt lần giao lại, song phải đọc từ raw JMS message hoặc metadata mapper phù hợp.
- Một message malformed JSON có thể không bao giờ vào handler; dù vậy converter exception vẫn phải được quan sát ở container.
- Redelivery nhiều lần tạo nhiều `ErrorHandler` invocations — đừng nghĩ có hai callback thì có hai message khác nhau.
- DLQ thường cần cấu hình trên broker (ActiveMQ Artemis address settings), không phải ở `ErrorHandler`.
- Nếu broker không có DLQ/max attempt hợp lý, poison message có thể lặp vô hạn và gây backlog.

### 11.1. Phân biệt retry nghiệp vụ và retry kết nối

| Cơ chế | Tác nhân | Ví dụ |
| --- | --- | --- |
| Redelivery do listener rollback | JMS provider/broker | Handler throw, session rollback, message được giao lại |
| Recovery do broker mất kết nối | Spring `DefaultMessageListenerContainer` | Recreate JMS connection/session/consumer |
| Retry gửi từ producer | Ứng dụng/outbox/job scheduler | `JmsTemplate.send` thất bại, cần đối soát |
| Retry nội bộ trong handler | Service HTTP/DB retry | Có thể làm tăng latency, giữ JMS Session lâu |
| DLQ/quarantine | Broker/ứng dụng theo hợp đồng | Quá số lần redelivery hoặc payload lỗi cố định |

Không nhầm recovery interval của container với redelivery delay của broker.

## 12. DefaultMessageListenerContainer tự recovery như thế nào?

Spring `DefaultMessageListenerContainer` hỗ trợ **self-recovery** khi broker tạm thời unavailable. Javadoc nêu:
- Cơ chế polling trên task executor.
- Có thể tự tạo lại connections/sessions/consumers khi gặp lỗi.
- `setRecoveryInterval(long)` mặc định là khoảng **5.000 ms**.
- `setBackOff(BackOff)` cho phép chính sách retry backoff linh hoạt.
- `setBackOff` và `setRecoveryInterval` có tương tác precedence; method được thiết lập sau có thể thay thế cấu hình trước theo API.

Ví dụ:

~~~java
factory.setRecoveryInterval(5_000L);
~~~

Lời gọi trên là mảnh cấu hình factory Spring JMS, không phải thiết lập số lần redelivery của một message. Với infrastructure lỗi nặng, nên dùng broker health, alerts, readiness/liveness, network timeout và resource quotas bên cạnh recovery loop.

**Đừng gọi `connection.close()` hoặc `container.start()` liên tục từ `ExceptionListener`** để “phục hồi nhanh”: container có lifecycle riêng. Tương tự đừng implement reconnect trong `ErrorHandler` khiến nhiều threads cạnh tranh tạo session/connection.

### 12.1. Khi nào phải stop container?

Chỉ trong các tình huống có chính sách điều hành riêng, ví dụ:
- Shutdown có kiểm soát.
- Tạm ngừng nhận để deploy schema không tương thích.
- Circuit breaker theo nghiệp vụ, đã đánh giá khả năng queue backlog/retention.
- Cần chờ sửa ACL/credential hoặc một lỗi cấu hình không thể tự hồi phục.

Không stop toàn bộ listener chỉ vì một message invalid nếu broker có DLQ/poison-handling thích hợp.

## 13. Lab Java 17+ Spring Boot 3.5: lỗi nghiệp vụ và hai callback

Lab dùng **một queue duy nhất** `lab.error-callbacks` và một `@JmsListener`. Message `task-1` bị từ chối **đúng một lần đầu** bằng `IllegalStateException`, sau đó được xử lý thành công khi được redeliver. Container được cấu hình **transacted**, nên retry dựa trên rollback JMS, không phải nhờ `ErrorHandler` tự gửi lại.

`ErrorHandler` tăng counter và phát tín hiệu test khi thấy lỗi runtime. `ExceptionListener` có counter riêng nhưng không bị kỳ vọng nhận lỗi nghiệp vụ không phải JMSException.

### 13.1. Maven project

Tạo dự án tại https://start.spring.io/:
- Maven, Java 17+, Spring Boot 3.5.x có patch được hỗ trợ.
- Group `com.example`.
- Artifact `jms-error-callback-demo`.
- Package `com.example.jmserrorlab`.
- Dependency Spring for Apache ActiveMQ Artemis (`spring-boot-starter-artemis`).

Thêm dependency broker embedded vào `pom.xml` do Initializr tạo (với Spring Boot BOM):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Không tự gắn version Artemis khác BOM khi chưa kiểm tra tương thích. Đây **không phải toàn bộ pom.xml**. Các file Java bên dưới có package name khớp project.

### 13.2. application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-error-callback-demo
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=lab.error-callbacks
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Lab không nhằm chứng minh data persistence; `persistent=false` chỉ phù hợp môi trường thử nghiệm. Không chạy cố ý ném exception trên queue production.

### 13.3. File 1 — CallbackState.java

Lưu `src/main/java/com/example/jmserrorlab/CallbackState.java`:

~~~java
package com.example.jmserrorlab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.jms.JMSException;
import org.springframework.stereotype.Component;

@Component
public class CallbackState {

    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger handlerErrors = new AtomicInteger();
    private final AtomicInteger jmsExceptions = new AtomicInteger();

    private final CountDownLatch failureObserved = new CountDownLatch(1);
    private final CountDownLatch completed = new CountDownLatch(1);

    private volatile String processed;

    public boolean shouldFailThisAttempt() {
        return attempts.incrementAndGet() == 1;
    }

    public void onHandlerError(Throwable error) {
        handlerErrors.incrementAndGet();
        failureObserved.countDown();
        // Chỉ quan sát, không rethrow, không quyết định rollback.
    }

    public void onJmsException(JMSException exception) {
        jmsExceptions.incrementAndGet();
        // Error path của JMS; không mở connection mới trong callback.
    }

    public void markProcessed(String body) {
        processed = body;
        completed.countDown();
    }

    public boolean awaitBoth(long timeout, TimeUnit unit)
            throws InterruptedException {
        long deadline = System.nanoTime() + unit.toNanos(timeout);
        long remaining = deadline - System.nanoTime();

        if (!failureObserved.await(
                Math.max(0L, remaining), TimeUnit.NANOSECONDS)) {
            return false;
        }

        remaining = deadline - System.nanoTime();
        return completed.await(
                Math.max(0L, remaining), TimeUnit.NANOSECONDS);
    }

    public int attempts() {
        return attempts.get();
    }

    public int handlerErrors() {
        return handlerErrors.get();
    }

    public int jmsExceptions() {
        return jmsExceptions.get();
    }

    public String processed() {
        return processed;
    }
}
~~~

`AtomicInteger` phù hợp callback threads; `CountDownLatch` giúp test đợi cả **một lỗi đã quan sát** và **một lần xử lý thành công**. `volatile processed` cho giá trị được xuất bản an toàn; lab không dùng latch để đảm bảo JMS transaction đã commit.

### 13.4. File 2 — ErrorCallbacksDemoApplication.java

Lưu `src/main/java/com/example/jmserrorlab/ErrorCallbacksDemoApplication.java`:

~~~java
package com.example.jmserrorlab;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ErrorCallbacksDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorCallbacksDemoApplication.class, args);
    }

    @Bean("observedListenerFactory")
    DefaultJmsListenerContainerFactory observedListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            CallbackState state) {

        var factory = new DefaultJmsListenerContainerFactory();

        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(
                        connectionFactory));

        factory.setSessionTransacted(true);
        factory.setConcurrency("1");
        factory.setErrorHandler(state::onHandlerError);
        factory.setExceptionListener(state::onJmsException);
        return factory;
    }

    @Bean
    ApplicationRunner demonstrate(
            JmsTemplate template,
            CallbackState state) {

        return args -> {
            template.convertAndSend(
                    "lab.error-callbacks", "task-1");

            if (!state.awaitBoth(12, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "No error callback or successful redelivery");
            }

            System.out.println("ATTEMPTS=" + state.attempts());
            System.out.println(
                    "HANDLER_ERRORS=" + state.handlerErrors());
            System.out.println("PROCESSED=" + state.processed());
            System.out.println(
                    "JMS_EXCEPTIONS=" + state.jmsExceptions());
        };
    }
}
~~~

Spring Boot configurer giữ các cấu hình JMS factory do Boot chuẩn bị. `factory.setSessionTransacted(true)` khiến lần xử lý thất bại đủ điều kiện rollback. Hai method references gắn **hai callback khác interface** vào cùng factory mà không nhầm tham số.

### 13.5. File 3 — RetryingTaskListener.java

Lưu `src/main/java/com/example/jmserrorlab/RetryingTaskListener.java`:

~~~java
package com.example.jmserrorlab;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class RetryingTaskListener {

    private final CallbackState state;

    public RetryingTaskListener(CallbackState state) {
        this.state = state;
    }

    @JmsListener(
            id = "retryingTaskListener",
            destination = "lab.error-callbacks",
            containerFactory = "observedListenerFactory")
    public void onTask(String task) {
        if (state.shouldFailThisAttempt()) {
            throw new IllegalStateException(
                    "Intentional failure on first delivery");
        }

        state.markProcessed(task);
    }
}
~~~

Đây là ứng dụng Java 17+ gồm **ba file Java độc lập theo class** và `application.properties`. Không có bean/listener khác cùng queue trong lab. `IllegalStateException` đầu tiên là lỗi cố ý **ở business method**, không phải `JMSException`. Nó phải đi qua đường `ErrorHandler`; không cần và không nên dựng giả một kết nối hỏng chỉ để callback thứ hai chạy.

### 13.6. Chạy

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với các điều kiện:
- broker embedded khởi động bình thường;
- queue test ban đầu trống;
- một listener duy nhất với concurrency `1`;
- redelivery policy của Artemis còn cho phép ít nhất lần thử thứ hai;
- không có sự cố connection trong lúc chạy;

...phần output do **ApplicationRunner** in ra dự kiến:

~~~text
ATTEMPTS=2
HANDLER_ERRORS=1
PROCESSED=task-1
JMS_EXCEPTIONS=0
~~~

Spring/JMS/Artemis có thể xuất thêm log riêng; không khẳng định toàn bộ stdout chỉ có bốn dòng. Nếu broker đã đặt delay redelivery lớn hơn 12 giây, `awaitBoth` có thể timeout — khi đó điều chỉnh **chính sách test** hoặc timeout, không tăng retry vô hạn ở production.

**Giải thích:**
1. Producer gửi `task-1` vào queue.
2. Lần gọi đầu tăng `attempts` lên 1, listener ném `IllegalStateException`.
3. Container session transacted thực hiện rollback theo policy, và Spring gọi `ErrorHandler` để báo lỗi.
4. Broker giao lại message; lần thứ hai tăng `attempts` lên 2, listener gọi `markProcessed`.
5. Sau khi cả hai latch được đánh dấu, runner in snapshot. Vì không tạo lỗi JMS-level, `ExceptionListener` không được kỳ vọng gọi.

**Giới hạn kiểm chứng:** `markProcessed` xảy ra **trong** handler, có thể **trước** khi container hoàn tất JMS commit. Lab chứng minh callback, rollback/redelivery flow dự kiến và trạng thái test trong RAM; **không chứng minh** message đã commit bền vững, exactly-once side effect hoặc provider failover. Muốn khẳng định commit cần kiểm tra broker queue state/transaction sau đó.

## 14. Cách test ExceptionListener mà không nhầm với business error

Không nên “thử ExceptionListener” bằng cách ném `RuntimeException` trong `@JmsListener`: đó là test ErrorHandler/rollback, không phải connection exception.

### 14.1. Test JMSException ở listener/infrastructure

Trong một test riêng, có thể dùng raw `jakarta.jms.MessageListener` hoặc adapter phù hợp phát ra `JMSException` tại đường container xử lý và xác minh:
- Spring gọi callback JMSException nếu path thực sự được container nhận dạng.
- Spring có thể gọi tiếp ErrorHandler cho cùng lỗi.
- Session rollback/recovery được kiểm tra riêng.
- Có log/metrics không đếm một lỗi thành hai incident business khác nhau.

**Không biến các lỗi thật thành fake `JMSException` ở production chỉ để tăng metric callback**. Callback phải phản ánh nguyên nhân gốc.

### 14.2. Test mất kết nối provider

Trong staging với broker **ngoài ứng dụng**:
1. Cấu hình connection factory, queue, consumer và container đang chạy.
2. Xác minh listener nhận một message bình thường.
3. Cho broker process ngừng trong môi trường test được phép, sau đó khởi động lại.
4. Ghi nhận provider logs, recovery logs của `DefaultMessageListenerContainer`, trạng thái registry, connection metrics và `ExceptionListener` callback nếu được gọi.
5. Đảm bảo consumer **trở lại** và xử lý message mới sau broker recovery; nếu cần khôi phục backlog thì bật broker persistence/retention phù hợp.
6. Nếu callback `ExceptionListener` không được gọi nhưng container reconnect được, đừng kết luận “Spring không xử lý sự cố”; kiểm tra kênh recovery riêng.
7. Nếu broker down lâu hơn retry budget/backoff, đánh giá readiness, alarms và failover policy.

**Không dùng Artemis embedded** để mô phỏng network outage độc lập khỏi JVM, vì broker bị dừng cùng process thường làm test mất ý nghĩa về connection recovery.

### 14.3. Phân biệt lỗi synchronous JMS call và async callback

~~~java
try {
    jmsTemplate.convertAndSend("orders.in", "order-1");
} catch (org.springframework.jms.JmsException ex) {
    // Lỗi synchronous ở thread gửi: xử lý/ghi trạng thái/outbox.
}
~~~

Đây là **mảnh code** trong một service có `JmsTemplate`. Lỗi trên thread gửi **không thuộc** listener container ErrorHandler. Jakarta Messaging yêu cầu exception được ném đồng bộ từ API call không được dùng `ExceptionListener` thay thế.

## 15. Quan sát, logging và metrics: đo đúng mà không đếm trùng

Một hệ thống cần đo tối thiểu bốn mặt:

| Nhóm quan sát | Chỉ số gợi ý | Vì sao |
| --- | --- | --- |
| Business listener | Attempts, success, failures theo exception category | Biết message thực sự xử lý thành công hay không |
| ErrorHandler | Listener callback errors, exception type, endpoint/factory | Phát hiện lỗi adapter/handler không xử lý |
| JMS infrastructure | JMSException callback, reconnect count, recovery duration | Phân biệt provider/connection vấn đề |
| Broker | Queue depth, oldest message age, redelivery, DLQ, expiry | Thấy hậu quả thực tế trên backlog |

`ErrorHandler` và `ExceptionListener` có thể cùng nhận một `JMSException`. Vì thế:
- Đặt nhãn rõ: `source=listener-error-handler` hoặc `source=jms-exception-listener`.
- Không cộng thẳng hai counters để suy ra số message lỗi.
- Để tính số **message attempts**, đếm ở listener/container và dùng JMS message ID/redelivery metadata khi phù hợp.
- Để tính số **business outcomes**, dựa trên idempotent DB records/success metrics, không dựa trên tổng callback errors.
- Với logs, ưu tiên error class, correlation ID/destination, timestamp, errorCode và linked exception; không dump toàn bộ JMS payload nếu chứa PII.
- Với một factory chia sẻ nhiều endpoints, ErrorHandler thường chỉ nhận `Throwable`, **không tự có tham số destination/message**. Nếu cần tách endpoint, dùng factory riêng, application tracing/MDC một cách đúng lifecycle hoặc instrumentation nơi có message context.

### 15.1. Phân loại exception có kiểm soát

~~~java
// Mảnh function minh họa phân loại root cause ở Spring side.
static String classify(Throwable error) {
    Throwable current = error;
    for (int depth = 0; current != null && depth < 8;
            depth++, current = current.getCause()) {
        if (current instanceof jakarta.jms.JMSException) {
            return "JMS_API";
        }
        if (current instanceof
                org.springframework.jms.support.converter.MessageConversionException) {
            return "CONVERSION";
        }
    }
    return "BUSINESS_OR_ADAPTER";
}
~~~

Phân loại này chỉ là **điểm khởi đầu**, không phải taxonomy cuối cùng. `MessageConversionException` ở Spring Messaging/JMS có thể nằm ở những package khác nhau tùy converter; cần đọc actual exception stack trong tests. Đừng biến mọi lỗi thành “transient” chỉ vì nó được bọc `RuntimeException`.

### 15.2. Hạn chế cảnh báo tràn

Nếu broker redeliver một poison message 10.000 lần, gọi cảnh báo 10.000 lần sẽ gây alert fatigue. Nên:
- Dùng metric rate/threshold và grouping theo destination/exception class.
- Chỉ log full stack trace theo sampling/first N events.
- Giới hạn retries và chuyển DLQ.
- Có dashboard backlog/DLQ, không chỉ error count.
- Tạo một runbook duy nhất cho lỗi message invalid theo contract.

## 16. Các lỗi configuration thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng sửa |
| --- | --- | --- |
| Handler ném lỗi nhưng ErrorHandler không chạy | Lỗi bị catch và nuốt trong method | Để lỗi lan tới container khi cần rollback |
| Có ErrorHandler bean nhưng không thấy callback | Factory mà endpoint dùng chưa gắn bean này | Kiểm tra `containerFactory` và `factory.setErrorHandler` |
| ExceptionListener không chạy khi handler ném IllegalStateException | Đó là runtime business error, không phải JMSException | Dùng ErrorHandler |
| Có hai log cho một JMSException | Spring có thể gọi ExceptionListener rồi ErrorHandler | Gắn nhãn và tránh double count |
| Có ErrorHandler nhưng message mất | AUTO_ACK hoặc handler return bình thường | Dùng transacted Session và đúng exception propagation |
| Message bị xử lý liên tục | Rollback nhưng broker chưa có retry cap/DLQ | Cấu hình max delivery attempts/delay/DLQ |
| Broker mất kết nối mà callback không chạy như kỳ vọng | DMLC recovery dùng luồng riêng; provider async khác synchronous | Quan sát recovery logs/broker health |
| Một lỗi conversion làm cả queue nghẽn | Poison message redelivery và không có quarantine | Phân loại lỗi, DLQ, bounded retries |
| ErrorHandler tự gọi JMS send rồi lỗi tiếp | Callback không có transaction/message context rõ | Không tự redeliver trong callback |
| ExceptionListener thao tác trên Connection đã hỏng | Provider callback không bảo đảm Connection usable | Chỉ log/metrics, để container recovery |
| Không phân biệt endpoint nào lỗi | Một factory dùng chung handler, throwable thiếu metadata | Tách factories hoặc bổ sung instrumentation hợp lệ |
| Custom factory mất cấu hình Boot | Không qua Boot configurer hoặc override thứ tự sai | Dùng `DefaultJmsListenerContainerFactoryConfigurer` |
| App đang healthy nhưng backlog tăng | Listener stop, broker down, selector không khớp, poison message | Theo dõi registry, queue depth, consumer count |
| DB thao tác lặp sau retry | JMS rollback nhưng DB đã commit | Inbox/idempotency + outbox |
| Test failover trên embedded broker không rõ kết quả | Broker và app có cùng lifecycle | Dùng broker độc lập với persisted storage |
| Shutdown gây lỗi JMS | SIGTERM khi message in-flight, timeouts quá ngắn | Graceful shutdown, transaction, retry và broker retention |
| ExceptionListener được gọi mà không có log stack | Callback chỉ log errorCode, bỏ getLinkedException/causes | Structured log với data sanitization |

## 17. Phân biệt lỗi nghiệp vụ tạm thời và vĩnh viễn

Một app xử lý hóa đơn có thể gặp:

**Tạm thời:** database unavailable, external API timeout, broker reconnect, temporary rate limiting. Thường có thể retry với backoff, circuit breaker và ngưỡng.

**Vĩnh viễn:** payload sai schema không sửa được, enum/type ID không hỗ trợ, ID không hợp lệ, business constraint bị vi phạm không có đường hồi phục. Retry vô hạn là sai. Có thể chuyển DLQ/quarantine hoặc ghi nhận kết quả từ chối rõ ràng theo hợp đồng.

`ErrorHandler` quan sát lỗi; nhưng **khi quyết định message nào được commit/quarantine/retry**, nên dùng:
- Một domain-specific error policy trong business service.
- Transaction boundary đúng để việc gửi DLQ/rejection và ACK không tạo cửa sổ mất dữ liệu.
- Broker redelivery max attempts, DLQ policy và monitoring.
- Idempotency để tránh side effects lặp.
- Versioned message schemas và contract validation.

### Không tự “fix” bằng catch tất cả

~~~java
@JmsListener(destination = "orders.in")
public void handle(String payload) {
    try {
        process(payload);
    } catch (Exception ex) {
        // Đây là phản ví dụ nếu công việc chưa hoàn thành.
        return;
    }
}
~~~

Khi Spring container thấy method return bình thường, nó có thể commit local JMS Session. Hãy phân biệt trường hợp **từ chối message có kiểm soát và đã ghi durable outcome** với trường hợp **thất bại chưa xử lý xong**; trường hợp sau phải propagate lỗi theo retry policy.

## 18. Liên hệ với Spring Messaging / Spring Integration

Không nhầm các callback của JMS listener container với:
- `org.springframework.integration.channel.PublishSubscribeChannel` error channel hoặc Spring Integration `errorChannel`: xử lý lỗi theo message flow của Spring Integration, khác lifecycle của `DefaultMessageListenerContainer`.
- `org.springframework.amqp.rabbit.listener.RabbitListenerErrorHandler`: callback của RabbitMQ/AMQP, không phải Jakarta JMS.
- `@ControllerAdvice` hoặc web `ErrorController`: HTTP MVC exception handling.
- `CompletionListener` trên JMS asynchronous producer send: callback cho thành công/thất bại của **gửi bất đồng bộ**, không phải ErrorHandler của consumer.
- `JmsTemplate` send/receive exception path: thường ném Spring `JmsException` trên thread gọi, không qua listener container ErrorHandler.

Việc hiểu đúng layer giúp đặt log/metric/transaction ở nơi chúng thực sự có ý nghĩa.

## 19. Kế hoạch kiểm thử đáng tin cậy

### 19.1. Unit test cho callback

- Đưa `IllegalStateException` vào `ErrorHandler.handleError`: tăng counter đúng và không throw.
- Đưa `JMSException` vào `ExceptionListener.onException`: tăng counter, log errorCode/linked cause an toàn.
- Gọi callback đồng thời từ nhiều threads: metric thread-safe.
- Đưa exception wrapped nhiều lớp: phân loại root cause có giới hạn, không vô hạn.
- Không đưa dữ liệu nhạy cảm vào logs.
- Callback không thực hiện blocking network I/O hoặc self-reconnect.

### 19.2. Integration test theo lớp

| Case | Input/failure | Chứng minh |
| --- | --- | --- |
| Business fail-once | Handler throw lần 1 | ErrorHandler quan sát, session rollback, broker redelivery |
| Business success | Handler return | ACK/commit, queue backlog về trạng thái mong đợi |
| Broken payload | JSON/schema invalid | Conversion exception được báo, handler body không cần chạy |
| Missing required header | Annotation argument resolution fail | Container error handling, rollback/DLQ theo policy |
| JMSException path | JMS API exception được container thấy | ExceptionListener path được kiểm tra đúng |
| Broker unavailable at startup | Broker down | DMLC setup/recovery và alert, không suy callback thay recovery |
| Broker restart mid-processing | Container reconnect | Khôi phục xử lý sau restart, đối soát message IDs |
| Poison retry limit | Message luôn fail | DLQ sau số attempts theo broker config |
| Duplicate redelivery | Crash giữa DB commit và JMS commit | Idempotency ngăn side effect lặp |
| Graceful shutdown | SIGTERM khi job đang xử lý | In-flight handling theo shutdown budget, rollback nếu cần |
| Multiple factories | Two endpoints khác factory | Mỗi callback theo policy/factory mong đợi |
| Shared callback | Một handler được nhiều listeners dùng | Counter labels tránh double count |

### 19.3. Dùng environment nào?

- **Unit tests:** không cần broker.
- **Embedded Artemis lab:** phù hợp so sánh error callback và fail-once redelivery cơ bản; không chứng minh network failover.
- **Broker test độc lập:** phù hợp connection outages, persistence, HA, DLQ, quota, recovery.
- **Staging gần production:** xác minh toàn bộ retry delay, concurrency, transaction, DB idempotency và operational alerts.

Không phá kết nối thật ở production chỉ để xem callback có chạy không. Không chạy poison-message test trên queue có khách hàng đang dùng.

## 20. Checklist production

- Đã phân loại exception nghiệp vụ, conversion và JMS infrastructure chưa?
- `ErrorHandler` đã được gắn vào **đúng factory/container** mà `@JmsListener` dùng?
- `ExceptionListener` là `jakarta.jms.ExceptionListener`, không import nhầm class?
- Có hiểu sự khác biệt Spring container callback và provider-level asynchronous `Connection` callback?
- Có tránh đếm trùng khi một JMSException đi qua cả hai callbacks?
- `ErrorHandler` có thread-safe, nhanh, không ném lỗi thứ cấp và không leak payload nhạy cảm?
- `ExceptionListener` có tránh thao tác vào connection đang lỗi và chặn callback lâu?
- Listener có `sessionTransacted=true` hoặc transaction policy khác phù hợp SLA?
- Lỗi cần retry có được propagate ra khỏi handler, không bị nuốt?
- Có thiết lập broker redelivery delay, max attempts, DLQ/expiry và alert?
- Có tách retry của message và recovery interval của connection?
- Có kiểm thử DMLC reconnect từ broker độc lập, không chỉ embedded?
- Có idempotency khi DB đã commit nhưng JMS chưa?
- Có logs/metrics về listener errors, JMSExceptions, queue age, DLQ, consumer count?
- Có giám sát `JmsListenerEndpointRegistry` và trạng thái running/recovery của containers?
- Có dùng Boot factory configurer để không mất defaults quan trọng?
- Có tests cho conversion error trước method, header missing và rollback behavior?
- Có kiểm tra graceful shutdown/worker restart với message in-flight?
- Có ownership rõ cho Connection, Session và JMS resources?
- Có runbook xử lý broker outage, poison message và incident business failure?

## 21. Bài tập củng cố

1. Một `@JmsListener` ném `IllegalStateException`. Callback nào thích hợp? Vì sao `ExceptionListener` không phải mặc định nhận lỗi này?
2. So sánh chữ ký `ErrorHandler.handleError(Throwable)` và `ExceptionListener.onException(JMSException)` và hai package import.
3. Khi Spring container nhận `JMSException` từ đường listener invocation, vì sao có thể gọi cả hai callback? Làm thế nào tránh đếm trùng?
4. Vì sao `ErrorHandler` return bình thường **không có nghĩa** message được commit thành công? Ai quyết định transaction?
5. Handler bắt lỗi DB, log rồi return. Nguy cơ gì với JMS transaction? Sửa thế nào?
6. Broker down 20 giây nhưng không có `onException` callback, sau đó container reconnect. Có chứng minh listener “mù lỗi” không? Cần quan sát gì thêm?
7. `JmsTemplate.convertAndSend` trên HTTP thread ném Spring `JmsException`. Callback trong listener factory có được gọi chắc chắn không? Thiết kế handling trên producer.
8. Tại sao `setRecoveryInterval(5000)` không đồng nghĩa message sẽ redeliver sau 5 giây?
9. Viết factory bean có `setErrorHandler`, `setExceptionListener`, `setSessionTransacted(true)` và concurrency rõ ràng.
10. Nếu factory chung cho ba endpoints, ErrorHandler chỉ nhận `Throwable`. Làm sao biết queue nào lỗi mà không suy từ message body?
11. Chạy lab fail-once, giải thích tại sao `HANDLER_ERRORS=1` và `ATTEMPTS=2`. Callback nào làm message quay lại queue?
12. Thay `sessionTransacted(false)` trong lab, thử nhận xét thay đổi reliability theo `AUTO_ACKNOWLEDGE` của DMLC.
13. Dùng broker test độc lập để restart trong lúc message in-flight; mô tả các metrics và message IDs cần đối chiếu.
14. Dùng message malformed cố ý làm fail mọi lần; chọn policy max redelivery, DLQ và alert phù hợp.
15. Một callback JMS nhận lỗi và thử `connection.close()` ngay trong `onException`. Điều gì nguy hiểm trong hạ tầng do Spring quản lý?
16. Trong lab, ứng dụng in `PROCESSED=task-1`. Vì sao chưa đủ chứng minh JMS commit và exactly-once DB side effect?
17. Một message được Spring ErrorHandler nhận hai lần. Có chắc đây là hai event khác nhau không? Kiểm tra redelivery ID.
18. Khi Spring Boot custom factory dùng `configurer.configure(...)`, vì sao cần override settings **sau** lời gọi configurer?
19. Phân biệt một lỗi conversion xảy ra trước handler, một lỗi trong handler và một lỗi JMS connection sau khi handler đã chạy.
20. Viết runbook cho tình huống broker down nhưng readiness vẫn green, queue backlog tăng và ExceptionListener không in log.

## Tài liệu chính thức

- Spring Framework 6.2 — `AbstractMessageListenerContainer` Javadoc, `setErrorHandler`, `setExceptionListener`, `handleListenerException` và transactions: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc, recovery, default ACK, `setBackOff` và `setRecoveryInterval`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `AbstractJmsListenerContainerFactory`, factory setters: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html
- Spring Framework 6.2 — Message Listener Containers và transaction handling: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Receiving a Message: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Boot 3.5 — `DefaultJmsListenerContainerFactoryConfigurer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html
- Spring Boot 3.5 — How-to Messaging, `ConnectionFactoryUnwrapper`: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
- Jakarta Messaging 3.1 — `ExceptionListener` Javadoc: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/exceptionlistener
- Jakarta Messaging 3.1 Specification, mục **6.1.7 ExceptionListener**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Apache ActiveMQ Artemis — Message Redelivery and Undelivered Messages: https://artemis.apache.org/components/artemis/documentation/latest/undelivered-messages
