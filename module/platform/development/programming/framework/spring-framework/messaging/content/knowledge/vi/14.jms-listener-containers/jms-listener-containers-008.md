# Khôi phục kết nối bằng recoveryInterval hoặc BackOff trong Spring JMS

## 1. Vì sao listener cần cơ chế recovery?

Một JMS listener thường chạy trong thời gian dài. Listener container giữ các tài nguyên như Connection, Session và MessageConsumer để nhận message liên tục. Khi broker khởi động lại, mạng bị gián đoạn hoặc provider tạm thời không tạo được consumer, các tài nguyên này có thể mất hiệu lực.

Ứng dụng cần một cơ chế để thử thiết lập lại kết nối sau khi lỗi hạ tầng xảy ra. Spring JMS cung cấp cơ chế recovery trong `DefaultMessageListenerContainer`. Container có thể tạo lại connection và các tài nguyên nhận message sau khi listener setup thất bại.

Hai lựa chọn chính để điều khiển khoảng chờ giữa các lần thử:

- **recoveryInterval:** khoảng chờ cố định, tính bằng milliseconds.
- **BackOff:** chiến lược tính khoảng chờ cho từng lần thử, ví dụ fixed delay hoặc exponential backoff.

Mặc định, `DefaultMessageListenerContainer` thử recovery với khoảng cách 5 giây. Có thể giữ mặc định, thay bằng một khoảng cố định khác hoặc cấu hình BackOff tùy đặc điểm broker và yêu cầu vận hành.

Sau bài học, bạn cần có thể:

- Giải thích vì sao listener container phải khôi phục connection và consumer.
- Phân biệt recoveryInterval với BackOff.
- Cấu hình recovery cho listener khai báo bằng @JmsListener.
- Dùng FixedBackOff hoặc ExponentialBackOff để điều khiển retry delay.
- Hiểu ý nghĩa của BackOffExecution.STOP.
- Phân biệt recovery kết nối với retry xử lý message.
- Quan sát trạng thái recovering và kiểm thử broker restart.

## 2. DefaultMessageListenerContainer tự khôi phục như thế nào?

`DefaultMessageListenerContainer` là listener container của Spring JMS, thường được dùng cho message-driven POJO và endpoint `@JmsListener`. Container sử dụng JMS client API để tạo session/consumer và nhận message trong các tác vụ do executor quản lý.

Khi việc thiết lập listener thất bại, chẳng hạn không tạo được connection hoặc consumer, container có thể:

1. Ghi nhận lỗi setup.
2. Chờ theo recovery strategy đã cấu hình.
3. Thử thiết lập lại connection hoặc destination resource cần thiết.
4. Tạo lại session và consumer.
5. Tiếp tục nhận message khi broker và các tài nguyên đã sẵn sàng.

Luồng khái quát:

~~~text
Listener container đang nhận message
              |
              v
Connection / consumer gặp lỗi
              |
              v
Ghi nhận listener setup failure
              |
              v
Chờ recoveryInterval hoặc BackOff
              |
              v
Thử tạo lại JMS resources
          /           \
      Thất bại        Thành công
         |                |
         v                v
    Chờ lần sau       Tiếp tục nhận
~~~

Cơ chế này hữu ích khi broker chỉ tạm thời không khả dụng. Ví dụ, broker restart trong quá trình deploy hoặc kết nối mạng bị gián đoạn ngắn. Container có thể tự thiết lập lại tài nguyên nhận message khi hạ tầng hoạt động trở lại.

Recovery của container không sửa được nguyên nhân cấu hình sai. Nếu username/password sai, destination không tồn tại hoặc tài khoản không có quyền consume, việc thử lại liên tục sẽ tiếp tục thất bại cho tới khi cấu hình hoặc quyền được sửa.

## 3. recoveryInterval: khoảng chờ cố định

### 3.1 Ý nghĩa và giá trị mặc định

`DefaultMessageListenerContainer.setRecoveryInterval(long)` nhận khoảng chờ giữa các lần thử recovery, đơn vị milliseconds.

Giá trị mặc định là:

~~~text
5000 milliseconds = 5 seconds
~~~

Nếu muốn container chờ 10 giây giữa các lần thử, cấu hình:

~~~java
container.setRecoveryInterval(10_000L);
~~~

`recoveryInterval` là lựa chọn đơn giản khi muốn một chu kỳ retry dễ dự đoán. Khoảng chờ không tăng dần theo số lần thất bại.

Phương thức này là cách tiện lợi để cấu hình một `FixedBackOff` với khoảng chờ tương ứng. Trong cấu hình thông thường, container tiếp tục thử recovery trong khi còn được chạy.

### 3.2 Cấu hình trực tiếp DefaultMessageListenerContainer

Ví dụ tạo container bằng Java configuration:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Configuration
public class ManualJmsContainerConfiguration {

    @Bean
    public DefaultMessageListenerContainer ordersContainer(
            ConnectionFactory connectionFactory,
            Destination ordersQueue,
            OrderMessageListener listener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestination(ordersQueue);
        container.setMessageListener(listener);
        container.setRecoveryInterval(10_000L);

        return container;
    }
}
~~~

`ConnectionFactory`, `Destination` và `OrderMessageListener` là các bean do ứng dụng hoặc JMS provider cung cấp. Ví dụ minh họa cấu hình một container thủ công; Spring application context quản lý lifecycle của bean.

### 3.3 Khi nào nên dùng recoveryInterval?

Dùng khoảng cố định khi:

- Broker có thời gian restart dự kiến ngắn.
- Muốn listener thử lại đều đặn và dễ dự đoán.
- Hệ thống chỉ có một số ít listener hoặc instance.
- Chưa cần giới hạn thời gian recovery bằng một chiến lược phức tạp.

Khoảng chờ quá ngắn có thể tạo nhiều lần kết nối thất bại, log dày và tải bổ sung lên broker đang gặp sự cố. Khoảng chờ quá dài làm consumer phục hồi chậm sau khi broker đã sẵn sàng.

Hãy chọn giá trị dựa trên thời gian phục hồi thông thường của broker, số instance cùng kết nối và mức độ trễ message mà hệ thống chấp nhận.

## 4. BackOff: điều khiển khoảng chờ theo từng lần thử

### 4.1 BackOff và BackOffExecution

Spring Core cung cấp abstraction `org.springframework.util.backoff.BackOff` để mô tả cách tính khoảng chờ giữa các lần thử.

Hai thành phần chính:

- `BackOff`: chiến lược tạo một lần thực thi backoff mới.
- `BackOffExecution`: theo dõi chuỗi khoảng chờ của một lần recovery; mỗi lần gọi `nextBackOff()` trả về thời gian chờ tiếp theo.

Nếu `nextBackOff()` trả về `BackOffExecution.STOP`, listener container không thực hiện thêm lần recovery theo chiến lược đó.

`BackOff` là abstraction chung của Spring Core. Nó không riêng cho JMS và cũng không phải retry policy của Spring Retry. `DefaultMessageListenerContainer` sử dụng abstraction này để tính thời gian chờ cho recovery.

### 4.2 FixedBackOff

`FixedBackOff` giữ nguyên khoảng chờ giữa các lần thử. Nó phù hợp khi muốn dùng abstraction BackOff nhưng vẫn cần lịch thử cố định.

Ví dụ:

~~~java
import org.springframework.util.backoff.FixedBackOff;

FixedBackOff backOff = new FixedBackOff(
        5_000L,
        FixedBackOff.UNLIMITED_ATTEMPTS
);
~~~

Đoạn code tạo chiến lược chờ 5 giây giữa các lần thử với số lần thử không giới hạn. Có thể dùng số lần thử hữu hạn khi muốn dừng recovery tự động sau một số lần nhất định.

Khác biệt thực tế giữa `setRecoveryInterval(5_000L)` và `setBackOff(new FixedBackOff(...))` nằm ở mức kiểm soát. recoveryInterval là API tiện lợi cho fixed delay; BackOff cho phép chọn thuật toán và giới hạn retry rõ ràng.

### 4.3 ExponentialBackOff

`ExponentialBackOff` tăng khoảng chờ sau mỗi lần thử. Khoảng chờ được nhân với multiplier cho tới khi đạt max interval.

Ví dụ, nếu bắt đầu ở 1 giây, multiplier bằng 2 và giới hạn 30 giây, lịch chờ minh họa là:

| Lần recovery tiếp theo | Khoảng chờ |
|---|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| Các lần sau | Tối đa 30 giây |

Cách tăng dần giúp giảm tần suất thử kết nối khi broker ngừng hoạt động lâu. Khi broker phục hồi, listener vẫn thử lại theo lịch đã tính.

ExponentialBackOff của Spring Framework có các thuộc tính chính:

- `initialInterval`: khoảng chờ ban đầu.
- `multiplier`: hệ số tăng khoảng chờ.
- `maxInterval`: khoảng chờ tối đa.
- `maxElapsedTime`: tổng thời gian tích lũy tối đa trước khi dừng chuỗi retry.
- `maxAttempts`: số lần thử tối đa; API này có từ Spring Framework 6.1.

Nếu không cấu hình giới hạn elapsed time hoặc attempts, ExponentialBackOff mặc định có thể tiếp tục rất lâu. Với recovery production, hãy quyết định rõ có cần retry vô hạn hay cần dừng để báo động và can thiệp.

## 5. Cấu hình BackOff cho @JmsListener

Khi dùng annotation-driven listener, cấu hình recovery trên `DefaultJmsListenerContainerFactory`. Factory chuyển các thiết lập này vào `DefaultMessageListenerContainer` mà nó tạo ra.

### 5.1 Dùng recoveryInterval

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setRecoveryInterval(10_000L);
        factory.setConcurrency("2-6");

        return factory;
    }
}
~~~

Listener dùng factory:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "jmsListenerContainerFactory")
    public void receive(String payload) {
        // Chuyển payload tới service nghiệp vụ.
    }
}
~~~

Factory này cấu hình fixed recovery delay 10 giây. Khi container không thể thiết lập listener do lỗi kết nối, nó thử lại theo khoảng chờ đã đặt.

### 5.2 Dùng ExponentialBackOff

Khi cần tăng khoảng chờ theo số lần thất bại, có thể cấu hình `BackOff` trực tiếp:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.util.backoff.ExponentialBackOff;

@Configuration
@EnableJms
public class JmsRecoveryConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);

        ExponentialBackOff backOff =
                new ExponentialBackOff(1_000L, 2.0);

        backOff.setMaxInterval(30_000L);
        backOff.setMaxElapsedTime(5 * 60_000L);

        factory.setBackOff(backOff);

        return factory;
    }
}
~~~

Trong ví dụ:

- Lần chờ đầu tiên là 1 giây.
- Mỗi lần tiếp theo tăng theo hệ số 2.
- Khoảng chờ không vượt quá 30 giây.
- Khi tổng thời gian tích lũy đạt giới hạn 5 phút, BackOff có thể trả về `BackOffExecution.STOP` và container ngừng các lần recovery tiếp theo theo chiến lược này.

Đây là cấu hình Spring bean, không phải chương trình Java chạy độc lập. Nó cần một `ConnectionFactory` bean hợp lệ và dependency Spring JMS tương ứng.

### 5.3 Chọn một chiến lược cho mỗi factory

`setRecoveryInterval` là cách tiện lợi để tạo fixed backoff. `setBackOff` cho phép dùng chiến lược tùy chỉnh. Nếu cấu hình cả hai, thiết lập recovery interval có thể thay thế BackOff đã cấu hình; vì vậy hãy chọn một cơ chế rõ ràng cho mỗi listener factory.

Không cần đặt cả hai chỉ để “tăng độ an toàn”. Điều đó làm khó xác định lịch retry thực tế.

## 6. BackOffExecution.STOP và giới hạn recovery

### 6.1 Ý nghĩa của STOP

Một BackOff hữu hạn có thể quyết định rằng không nên tiếp tục thử sau một ngưỡng. Khi `BackOffExecution.nextBackOff()` trả về `BackOffExecution.STOP`, `DefaultMessageListenerContainer` không lên lịch thêm lần recovery theo execution đó.

Ví dụ, nếu cấu hình giới hạn elapsed time 5 phút, sau khi chuỗi backoff đạt ngưỡng, container không tiếp tục thử vô hạn.

Điều này hữu ích khi:

- Cấu hình có thể sai vĩnh viễn như credential hoặc destination.
- Tổ chức muốn chuyển trạng thái sang cảnh báo và can thiệp.
- Cần giới hạn khoảng thời gian một listener được phép tự phục hồi.
- Muốn tránh retry kéo dài mà không có người vận hành biết.

### 6.2 STOP không có nghĩa broker đã bị xóa hoặc message đã mất

STOP chỉ điều khiển việc lên lịch recovery của listener container. Nó không xóa queue/topic, không xóa message trong broker và không tự thay đổi cấu hình ConnectionFactory.

Khi recovery đã dừng, hệ thống cần có cơ chế quan sát và hành động phù hợp, ví dụ cảnh báo, kiểm tra nguyên nhân, rồi khởi động lại container hoặc ứng dụng sau khi sửa cấu hình.

Nếu cần listener tự phục hồi trong suốt thời gian broker outage không xác định, hãy dùng chiến lược retry không giới hạn hoặc fixed recovery interval mặc định. Đổi lại, cần giám sát để phát hiện outage kéo dài.

## 7. Recovery kết nối khác với retry xử lý message

Đây là điểm cần phân biệt rõ.

### 7.1 Recovery kết nối và listener setup

`recoveryInterval` và `BackOff` của `DefaultMessageListenerContainer` điều khiển khoảng chờ giữa các lần thử thiết lập lại listener resources sau lỗi setup hoặc kết nối.

Ví dụ:

- Broker tạm thời không khả dụng.
- Connection bị đóng hoặc mất.
- Consumer không thể được tạo.
- Destination resource cần được phân giải lại sau lỗi setup.

Mục tiêu là khôi phục khả năng nhận message của container.

### 7.2 Retry xử lý nghiệp vụ

Nếu listener đã nhận được message nhưng method nghiệp vụ ném exception, đây là lỗi xử lý message. Việc message có được redeliver hay không phụ thuộc acknowledgement, transaction và broker policy.

Các thiết lập liên quan gồm:

- JMS session transaction, ví dụ `setSessionTransacted(true)`.
- Transaction manager được cấu hình cho listener container.
- Acknowledge mode.
- Broker redelivery policy, delivery count và dead-letter queue.
- ErrorHandler hoặc error flow của ứng dụng.

Ví dụ factory dùng transaction cho listener:

~~~java
factory.setSessionTransacted(true);
~~~

Khi xử lý thất bại trong session transaction, container có thể rollback theo transaction semantics; broker/provider có thể giao lại message. Cần kiểm tra policy redelivery thực tế của broker.

### 7.3 Không dùng recoveryInterval để retry business logic

Nếu một message chứa dữ liệu sai khiến listener liên tục lỗi, tăng recoveryInterval không phải cách sửa đúng. Container có thể vẫn kết nối bình thường; lỗi nằm ở payload hoặc service nghiệp vụ.

Hãy phân loại:

| Hiện tượng | Cơ chế cần xem xét |
|---|---|
| Broker tạm ngừng hoặc connection mất | recoveryInterval / BackOff |
| Không tạo được session hoặc consumer | Listener container recovery |
| Listener method ném exception | Transaction, acknowledgement, redelivery, error handling |
| Gửi message thất bại ở publisher | Retry phía producer hoặc provider client |
| Message hết TTL | Broker expiration policy |
| Broker chuyển message lỗi sang DLQ | Redelivery và dead-letter policy |

Một hệ thống có thể cần cả recovery kết nối lẫn redelivery message, nhưng hai cơ chế giải quyết hai loại lỗi khác nhau.

## 8. Kết hợp với failover và reconnect của JMS provider

JMS provider có thể cung cấp failover URI, reconnect, heartbeat hoặc connection retry riêng. Spring DMLC có cơ chế recovery của container. Hai lớp này có thể cùng tham gia khi broker mất kết nối.

Ví dụ:

~~~text
Spring listener container
        |
        v
Provider ConnectionFactory
        |
        v
JMS client / failover transport
        |
        v
Broker cluster
~~~

Cần xác định lớp nào chịu trách nhiệm cho từng tình huống:

- Provider có thể tự chuyển sang broker node khác trong cùng cluster.
- ConnectionFactory có thể thử reconnect theo cấu hình provider.
- DefaultMessageListenerContainer có thể tạo lại connection/session/consumer khi listener setup thất bại.
- BackOff của Spring điều khiển khoảng chờ giữa các lần container thử recovery.

Không giả định provider failover và Spring recovery có cùng lịch retry. Nếu cả hai đều retry quá nhanh, hệ thống có thể tạo nhiều lần kết nối thất bại. Nếu cả hai đều chờ quá lâu, thời gian phục hồi tổng thể tăng.

Hãy kiểm tra tài liệu provider và thử nghiệm broker restart hoặc failover thật. Tránh tạo nhiều lớp retry không có giới hạn hoặc không có metric.

## 9. Chọn recovery strategy theo tình huống

| Tình huống | Gợi ý cấu hình |
|---|---|
| Broker restart ngắn, ít listener | recoveryInterval cố định |
| Broker outage kéo dài, nhiều lần thử | ExponentialBackOff với maxInterval |
| Cần tự thử mãi cho tới khi broker hoạt động | FixedBackOff không giới hạn hoặc recoveryInterval |
| Cần giới hạn thời gian tự recovery | BackOff có maxElapsedTime hoặc maxAttempts |
| Provider đã có failover cluster | Phối hợp provider reconnect và Spring BackOff |
| Lỗi credential hoặc destination có thể là lỗi cấu hình | Giới hạn retry, cảnh báo và sửa cấu hình |

Không có một khoảng chờ phù hợp cho mọi ứng dụng. Hãy cân nhắc:

- Thời gian broker thường phục hồi.
- Số listener và số application instance.
- Mức tải khi tất cả instance cùng reconnect.
- Độ trễ message chấp nhận được.
- Thời gian tối đa hệ thống tự thử trước khi cần can thiệp.
- Provider có retry hoặc failover riêng hay không.

ExponentialBackOff mặc định không thêm random jitter. Nếu nhiều instance cùng khởi động và cùng gặp lỗi, lịch retry có thể tương tự nhau. Với hệ thống lớn, có thể dùng một BackOff tùy chỉnh có jitter để giảm việc nhiều client cùng reconnect tại một thời điểm.

## 10. Quan sát trạng thái recovery

Recovery tự động chỉ hữu ích khi đội vận hành biết listener đang hoạt động hay đang thử khôi phục.

Nên quan sát:

- Log của listener container khi connection hoặc consumer setup thất bại.
- Số lần recovery và thời gian kể từ lần kết nối thành công gần nhất.
- Số consumer đang hoạt động và số consumer được lập lịch.
- Queue depth hoặc subscription backlog.
- Connection state và lỗi do provider báo.
- Thời gian listener ở trạng thái recovering.
- Số message được redeliver sau khi kết nối phục hồi.

`DefaultMessageListenerContainer` cung cấp trạng thái như `isRecovering()` và thông tin consumer đang hoạt động qua các API tương ứng. Có thể expose thông tin qua JMX, actuator/custom metrics hoặc hệ thống giám sát của ứng dụng tùy cách triển khai.

Không log password, token hoặc connection string có chứa secret. Khi ghi nhận lỗi, giữ các thông tin đủ để xác định provider, destination, container và nguyên nhân mà không làm lộ credentials.

Một cảnh báo hữu ích có thể kích hoạt khi listener recovering lâu hơn ngưỡng vận hành, hoặc khi không có consumer active trong khi queue vẫn có backlog.

## 11. Kiểm thử recovery

Nên kiểm thử với JMS provider/broker thực tế hoặc Testcontainers có image phù hợp.

Các tình huống cần xác minh:

1. Broker hoạt động bình thường, listener nhận message.
2. Broker dừng sau khi listener đã chạy.
3. Container ghi nhận lỗi và thử lại theo recoveryInterval đã cấu hình.
4. Broker khởi động lại, container tạo lại connection/session/consumer.
5. Listener tiếp tục nhận message mới sau recovery.
6. BackOff tăng delay đúng theo cấu hình.
7. BackOff hữu hạn trả STOP và không còn thử recovery tiếp.
8. Container stop trong khi đang chờ recovery.
9. Provider failover và Spring recovery phối hợp đúng.
10. Listener method ném exception được xử lý theo transaction/redelivery policy riêng.

Với test có thời gian chờ, dùng Awaitility, latch hoặc cơ chế đồng bộ có timeout rõ ràng thay vì sleep dài tùy ý. Không chỉ kiểm tra log có dòng “reconnecting”; hãy xác minh listener thật sự nhận được message sau khi broker phục hồi.

Nên tách test recovery kết nối khỏi test redelivery. Một test dừng broker để kiểm tra DMLC reconnect; test khác cố tình làm listener thất bại trong transaction để kiểm tra message có được redeliver theo broker policy.

## 12. Các lỗi thường gặp

- **Đặt recoveryInterval quá ngắn:** tạo nhiều lần kết nối thất bại và tải bổ sung lên broker.
- **Đặt recoveryInterval quá dài:** listener phục hồi chậm dù broker đã sẵn sàng.
- **Nghĩ recoveryInterval là timeout xử lý message:** nó chỉ điều khiển khoảng chờ giữa các lần recovery.
- **Dùng BackOff hữu hạn mà không giám sát:** khi trả STOP, container không tự tiếp tục thử theo execution đó.
- **Cấu hình đồng thời setRecoveryInterval và setBackOff:** thiết lập recovery interval có thể ghi đè BackOff tùy thứ tự cấu hình.
- **Nhầm Spring BackOff với Spring Retry:** hai API và mục đích cấu hình khác nhau.
- **Cho rằng recovery sửa được credential sai:** cần sửa nguyên nhân xác thực hoặc quyền truy cập.
- **Cho rằng broker restart sẽ không có message redelivery:** message chưa acknowledge có thể được giao lại theo broker semantics.
- **Dùng recoveryInterval để xử lý poison message:** lỗi nghiệp vụ cần error handling, retry/redelivery và DLQ.
- **Không xét provider reconnect:** retry ở cả provider và Spring có thể chồng lặp.
- **Không theo dõi trạng thái listener:** ứng dụng có thể chạy nhưng consumer không hoạt động.
- **Không kiểm thử broker restart:** cấu hình startup thành công chưa chứng minh recovery runtime hoạt động.

## 13. Checklist cấu hình

Trước khi đưa JMS listener vào production, hãy kiểm tra:

- Listener dùng DefaultMessageListenerContainer hay container implementation nào?
- Recovery là fixed interval hay BackOff tùy chỉnh?
- Giá trị recoveryInterval tính bằng milliseconds có phù hợp không?
- Nếu dùng ExponentialBackOff, initialInterval, multiplier và maxInterval đã hợp lý chưa?
- Có cần maxElapsedTime hoặc maxAttempts để dừng recovery không?
- Khi BackOff trả STOP, ai nhận cảnh báo và khởi động lại listener?
- Provider có failover/reconnect riêng không?
- Recovery có bị lặp với retry của provider không?
- Lỗi setup được phân biệt với lỗi xử lý message chưa?
- Transaction và redelivery policy có được cấu hình riêng không?
- Có metric cho recovery, active consumer và queue backlog không?
- Integration test đã dừng/khởi động lại broker và xác minh listener nhận message trở lại chưa?

Khi cấu hình đúng recoveryInterval hoặc BackOff, DefaultMessageListenerContainer có thể tự khôi phục listener sau lỗi kết nối tạm thời với lịch thử lại phù hợp. Việc tách recovery hạ tầng khỏi redelivery nghiệp vụ giúp ứng dụng duy trì khả năng nhận message và xử lý lỗi theo đúng trách nhiệm của từng lớp.

## 14. Tài liệu tham khảo

- [DefaultMessageListenerContainer — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [DefaultJmsListenerContainerFactory — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [ExponentialBackOff — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/util/backoff/ExponentialBackOff.html)
- [FixedBackOff — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/util/backoff/FixedBackOff.html)
- [Receiving a Message — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)