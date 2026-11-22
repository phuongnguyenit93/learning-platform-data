# JMSException và chuyển đổi sang ngoại lệ không kiểm tra của Spring

## 1. Vì sao bài này quan trọng?

Khi gọi API Jakarta Messaging (JMS) trực tiếp, nhiều thao tác như tạo `Session`, đọc `TextMessage` hoặc gửi thông điệp có thể ném `jakarta.jms.JMSException`. Đây là **checked exception**: Java buộc mã gọi phải `catch` hoặc khai báo `throws`. Trong ứng dụng dùng Spring JMS, `JmsTemplate` và các thành phần hỗ trợ thường chuyển các lỗi JMS checked mà chúng bắt được thành `org.springframework.jms.JmsException`, một **unchecked exception** kế thừa `RuntimeException`.

Việc chuyển đổi giúp tầng nghiệp vụ làm việc với API gọn hơn, song **không biến thao tác thất bại thành thành công**, không tự kích hoạt retry, cũng không đảm bảo message đã hay chưa đến broker. Cần hiểu ranh giới chuyển đổi để ghi log, retry và xử lý transaction đúng.

Sau bài này, bạn sẽ:
- Nhận diện `JMSException`, `JMSRuntimeException` và `JmsException` theo đúng package, kiểm tra checked/unchecked.
- Hiểu Spring chuyển đổi ngoại lệ tại đâu, cách dùng `JmsUtils.convertJmsAccessException` khi thật sự cần.
- Phân biệt loại lỗi gốc với loại lỗi Spring tương ứng, giữ `cause` và vendor error code để chẩn đoán.
- Áp dụng xử lý lỗi cho publisher/consumer mà không vô tình xác nhận một message chưa xử lý.

> Phạm vi: Jakarta Messaging (`jakarta.jms`) và Spring Framework 6.x / Spring Boot 3.x, Java 17+. Với mã Spring cũ dùng `javax.jms`, import/API phải được xem lại theo phiên bản; hai package không thay thế trực tiếp cho nhau.

## 2. JMSException của Jakarta Messaging là gì?

`jakarta.jms.JMSException` kế thừa `java.lang.Exception`, không kế thừa `RuntimeException`, nên là **checked exception**. Những API JMS cổ điển có thể khai báo `throws JMSException`; trình biên dịch kiểm tra rằng bên gọi đã xử lý hoặc khai báo nó.

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

class RawJmsReader {
    String readText(Session session) throws JMSException {
        TextMessage message = session.createTextMessage("hello");
        return message.getText();
    }
}
~~~

Đoạn trên chỉ minh họa cách API khai báo checked exception: mã không tạo broker hay `Session` thực tế, nên chưa phải chương trình chạy độc lập.

`JMSException` chứa thông tin hữu ích:
- `getMessage()`: mô tả lỗi; thông điệp và ngôn ngữ có thể do provider quyết định.
- `getErrorCode()`: mã lỗi riêng của provider, có thể là `null`; **không phải danh mục mã lỗi chung bảo đảm giữa mọi broker**.
- `getLinkedException()` và `setLinkedException(Exception)`: cơ chế liên kết exception lịch sử của JMS; khi điều tra, xem cả linked exception và chuỗi `Throwable.getCause()`, vì chúng không nhất thiết trùng nhau.

Ví dụ các ngoại lệ checked chuyên biệt:

| `jakarta.jms` | Ý nghĩa điển hình | Gợi ý xử lý |
|---|---|---|
| `InvalidDestinationException` | Destination không hợp lệ/không sử dụng được. | Kiểm tra tên, loại Queue/Topic, quyền và cấu hình broker. |
| `InvalidSelectorException` | JMS selector không hợp lệ. | Sửa biểu thức selector, kiểm tra property và cú pháp. |
| `JMSSecurityException` | Xác thực/phân quyền bị từ chối. | Kiểm tra credentials, ACL, cơ chế xác thực; tránh retry vô hạn. |
| `ResourceAllocationException` | Broker/provider không cấp được tài nguyên cần thiết. | Đánh giá quota, pool, áp lực tài nguyên; retry có giới hạn nếu thực sự tạm thời. |
| `MessageFormatException` | Truy cập/đọc message sai định dạng hoặc kiểu. | Sửa contract/schema và cách đọc payload. |
| `TransactionRolledBackException` | Transaction JMS bị rollback. | Xem nguyên nhân rollback và chính sách retry/duplicate. |

Đây là các lớp lỗi **do API định nghĩa**, không phải toàn bộ lỗi thực tế. Provider có thể ném `JMSException` chung hoặc mã riêng; không được suy ra chắc chắn tính chất recoverable chỉ từ tên class.

### Một ngoại lệ cùng tên có thể thuộc hai package khác nhau

~~~text
jakarta.jms.InvalidDestinationException   -> checked, extends JMSException
org.springframework.jms.InvalidDestinationException
                                         -> unchecked, extends JmsException
~~~

Tương tự, `jakarta.jms.IllegalStateException` là một subclass của `JMSException`, khác với `java.lang.IllegalStateException`. Khi phải dùng cả API Jakarta và Spring trong một tệp, hãy ghi rõ package hoặc import có chủ ý để tránh nhầm tên.

## 3. Spring JmsException: phân cấp ngoại lệ không kiểm tra

Spring có lớp gốc trừu tượng `org.springframework.jms.JmsException`. Nó kế thừa `org.springframework.core.NestedRuntimeException` rồi đến `RuntimeException`:

~~~text
java.lang.Exception
  └─ java.lang.RuntimeException
       └─ org.springframework.core.NestedRuntimeException
            └─ org.springframework.jms.JmsException
                 ├─ InvalidDestinationException
                 ├─ InvalidSelectorException
                 ├─ JmsSecurityException
                 ├─ ResourceAllocationException
                 ├─ MessageFormatException
                 ├─ TransactionRolledBackException
                 └─ UncategorizedJmsException
~~~

Sơ đồ liệt kê một số lớp tiêu biểu, không phải toàn bộ cây kế thừa.

Điểm quan trọng:

1. **Unchecked không bắt buộc phải `catch` hoặc `throws`.** Service vẫn có thể chủ động `catch (JmsException ex)` để ghi log, phân loại và áp dụng retry policy.
2. **Spring giữ nguyên lỗi gốc làm cause** khi chuyển từ checked `JMSException`, giúp tiếp tục truy dấu stack trace và lỗi provider.
3. `JmsException.getErrorCode()` là phương thức tiện ích lấy mã lỗi khi root cause là `JMSException`. Kết quả có thể `null` nếu lỗi không có mã provider/JMS root cause.
4. Một `JmsException` **không nhất thiết** bắt nguồn từ `JMSException`. Ví dụ lỗi phân giải tên destination, chuyển đổi payload hoặc lỗi nội bộ framework có thể phát sinh trực tiếp từ tầng Spring.
5. `JmsException` không phải `org.springframework.dao.DataAccessException`; hai nhóm cùng là runtime nhưng dành cho các lớp tích hợp khác nhau.

**Lý do chuyển thành runtime:** tách cơ chế truy cập messaging ra khỏi chữ ký hàm nghiệp vụ. Thay vì bắt toàn bộ service `throws JMSException`, Spring cho phép lỗi lan truyền theo cơ chế runtime, còn logic phục hồi nằm ở ranh giới phù hợp.

### Đường đi điển hình của một lỗi

~~~text
Ứng dụng gọi publisher.publish(...)
            |
            v
       JmsTemplate
            |
            v
    Jakarta JMS provider
            |
            | ném jakarta.jms.JMSException (checked)
            v
   Spring catch JMSException
            |
            v
   convertJmsAccessException(...)
            |
            v
 org.springframework.jms.JmsException (runtime)
            |
            v
 Caller bắt JmsException hoặc để lỗi lan truyền
~~~

Đây là luồng **khi Spring bắt được checked JMSException**. Lỗi do chính listener code ném ra, lỗi chuyển đổi payload do Spring tạo, lỗi khi khởi động listener container và lỗi asynchronous kết nối có những con đường xử lý khác; đừng coi sơ đồ này áp dụng cho mọi throwable.

## 4. Spring chuyển đổi bằng cách nào?

Tiện ích công khai:

~~~java
org.springframework.jms.support.JmsUtils
    .convertJmsAccessException(jakarta.jms.JMSException ex)
~~~

Giá trị trả về là `org.springframework.jms.JmsException`. Phương thức chọn lớp Spring có ý nghĩa tương ứng khi nhận ra subtype Jakarta; nếu không có ánh xạ chuyên biệt, dùng dạng ngoại lệ Spring tổng quát như `UncategorizedJmsException`.

Một số ví dụ quan hệ ánh xạ thường gặp:

| Lỗi checked Jakarta | Dạng unchecked Spring |
|---|---|
| `jakarta.jms.InvalidDestinationException` | `org.springframework.jms.InvalidDestinationException` |
| `jakarta.jms.InvalidSelectorException` | `org.springframework.jms.InvalidSelectorException` |
| `jakarta.jms.JMSSecurityException` | `org.springframework.jms.JmsSecurityException` |
| `jakarta.jms.ResourceAllocationException` | `org.springframework.jms.ResourceAllocationException` |
| `jakarta.jms.MessageFormatException` | `org.springframework.jms.MessageFormatException` |
| `jakarta.jms.JMSException` chung không thuộc subtype chuyên biệt | `org.springframework.jms.UncategorizedJmsException` |

Tên class Spring có thể gần giống class Jakarta, nhưng không đồng nghĩa hai hệ exception có quan hệ kế thừa với nhau. Khi code cần `catch` loại Spring, phải import đúng `org.springframework.jms.*`.

**Khi dùng `JmsTemplate`, thường không cần gọi `JmsUtils` thủ công.** Các phương thức của template đã có cơ chế truy cập/cleanup và chuyển checked JMSException tại biên Spring. Gọi chuyển đổi thủ công chỉ hữu ích khi bạn trực tiếp thao tác API JMS checked bên ngoài template hoặc đang viết adapter riêng.

## 5. Ví dụ Java 17 chạy độc lập: chuyển checked sang unchecked

Thí nghiệm sau **không cần broker**: hàm giả lập một provider ném `InvalidDestinationException`; sau đó dùng đúng API Spring để chuyển đổi và kiểm tra class, mã lỗi, cause. Đây là thí nghiệm về **exception translation**, không phải kiểm thử kết nối JMS thực.

Cấu trúc:

~~~text
jms-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/TranslationDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-exception-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-jms:6.2.14'
    implementation 'jakarta.jms:jakarta.jms-api:3.1.0'
}

application {
    mainClass = 'example.TranslationDemo'
}
~~~

`src/main/java/example/TranslationDemo.java`:

~~~java
package example;

import jakarta.jms.JMSException;
import jakarta.jms.InvalidDestinationException;
import org.springframework.jms.JmsException;
import org.springframework.jms.support.JmsUtils;

public final class TranslationDemo {
    private TranslationDemo() {
    }

    // Mô phỏng lỗi do provider trả về; không kết nối broker.
    private static void rawJmsOperation() throws JMSException {
        throw new InvalidDestinationException(
                "Destination does not exist", "DEST-404");
    }

    public static void main(String[] args) {
        try {
            rawJmsOperation();
        } catch (JMSException checked) {
            JmsException translated =
                    JmsUtils.convertJmsAccessException(checked);

            System.out.println("checkedType="
                    + checked.getClass().getSimpleName());
            System.out.println("springType="
                    + translated.getClass().getName());
            System.out.println("isRuntime="
                    + (translated instanceof RuntimeException));
            System.out.println("errorCode="
                    + translated.getErrorCode());
            System.out.println("sameCause="
                    + (translated.getCause() == checked));
        }
    }
}
~~~

Chạy trong thư mục dự án với JDK 17+ và Gradle có hỗ trợ toolchain tương ứng. Nếu dự án có Gradle Wrapper, ưu tiên `./gradlew run --quiet`; nếu chưa có thì:

~~~bash
gradle run --quiet
~~~

Đầu ra chuẩn **dự kiến từ mã Java** (không tính thông báo riêng của Gradle):

~~~text
checkedType=InvalidDestinationException
springType=org.springframework.jms.InvalidDestinationException
isRuntime=true
errorCode=DEST-404
sameCause=true
~~~

Giải thích từng dòng:
- `checkedType` vẫn là loại `jakarta.jms.InvalidDestinationException` ban đầu.
- `springType` là subclass runtime tương ứng của Spring.
- `isRuntime=true` xác nhận đây là exception không kiểm tra.
- `errorCode=DEST-404` cho thấy Spring có thể truy cập mã lỗi của `JMSException` gốc.
- `sameCause=true` nghĩa là exception Spring bọc **đúng đối tượng checked ban đầu** làm cause; conversion không làm biến mất stack trace gốc.

Đổi hàm `rawJmsOperation` thành `throw new JMSException("Transport failed", "PROVIDER-1");` để quan sát trường hợp không phải subclass chuyên biệt. Loại Spring sẽ là `UncategorizedJmsException` theo ánh xạ thông thường, nhưng mã lỗi và cause gốc vẫn phục vụ chẩn đoán.

## 6. Trong ứng dụng Spring, JmsTemplate đã làm phần lớn việc này

Ví dụ service gửi sự kiện (đoạn dưới giả định ứng dụng đã có `ConnectionFactory`, broker hoạt động và bean `JmsTemplate` được cấu hình):

~~~java
package example;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public final class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    public OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publishCreated(String orderId) {
        jmsTemplate.convertAndSend(
                "orders.created", "OrderCreated:" + orderId);
    }
}
~~~

Phương thức `publishCreated` **không khai báo `throws JMSException`**. Tại ranh giới Spring, `JmsTemplate` sẽ chuyển `JMSException` phát sinh trong thao tác mà nó quản lý thành `JmsException`. Code gọi có thể bắt exception Spring:

~~~java
try {
    publisher.publishCreated("42");
} catch (org.springframework.jms.InvalidDestinationException ex) {
    // Kiểm tra cấu hình destination/provider.
    throw ex;
} catch (org.springframework.jms.JmsException ex) {
    // Lỗi JMS khác: ghi nhận, phân loại và để chính sách retry quyết định.
    throw ex;
}
~~~

Đoạn `try/catch` này là **mảnh mã minh họa nằm trong một caller có biến `publisher`**, không phải chương trình độc lập. Việc rethrow giữ nguyên stack trace. Trong code production, bổ sung logging có correlation ID/event ID và xử lý ở đúng boundary thay vì thêm catch rỗng ở mọi tầng.

`JmsTemplate` cũng cho phép callback cấp thấp, nơi callback vẫn có thể khai báo `JMSException`:

~~~java
String value = jmsTemplate.execute(session -> {
    // Session.createTextMessage/getText khai báo JMSException.
    return session.createTextMessage("hello").getText();
});
~~~

Đoạn này nằm trong một method có biến `jmsTemplate`. Bên ngoài callback không cần `throws JMSException` vì template thực hiện bắt/chuyển checked JMSException. Kết quả `value` là `"hello"` nếu template lấy được session; **vẫn cần broker/ConnectionFactory** để chạy callback thực tế.

### Phân biệt hai kiểu “convert” trong JmsTemplate

Có hai khái niệm hoàn toàn khác nhau:

- `convertAndSend(...)` chuyển **payload Java** thành một JMS Message (qua `MessageConverter`) rồi gửi.
- `convertJmsAccessException(...)` chuyển **loại ngoại lệ checked** thành loại Spring unchecked.

Cùng có từ `convert` nhưng một thao tác với dữ liệu, thao tác còn lại xử lý lỗi. Ngoài ra, Spring có thể phát sinh `MessageConversionException` khi chuyển payload thất bại; lỗi đó không bắt buộc xuất phát từ một `jakarta.jms.JMSException`.

## 7. Khi nào phải chuyển ngoại lệ thủ công?

Nếu dùng API cổ điển `Connection`/`Session` trực tiếp trong adapter tự viết, code phải bắt hoặc khai báo `JMSException`. Ở tầng adapter giao tiếp với code Spring, có thể chuyển tại **một boundary duy nhất**:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import org.springframework.jms.JmsException;
import org.springframework.jms.support.JmsUtils;

final class RawSessionAdapter {
    String createPayload(Session session) {
        try {
            return session.createTextMessage("payload").getText();
        } catch (JMSException ex) {
            throw JmsUtils.convertJmsAccessException(ex);
        }
    }
}
~~~

Đây là ví dụ biên dịch được nếu dependencies đã có, nhưng cần một `Session` thật do caller cung cấp để chạy. Adapter chuyển lỗi, không tự tạo/kết thúc session; nơi tạo tài nguyên phải chịu trách nhiệm close/cleanup. Tránh vừa dùng `JmsTemplate` vừa tự tạo `Connection`/`Session` mới nếu không có yêu cầu đặc biệt, vì dễ sai transaction boundary và resource management.

**Không dùng `new RuntimeException(ex)` thay cho translation chuyên biệt một cách máy móc.** Cách bọc chung làm caller không thể catch các subtype Spring hữu ích và làm mất ngữ nghĩa phân loại. Khi chủ động đổi sang exception nghiệp vụ, ghi rõ lý do và giữ `cause`.

### JMSRuntimeException là một trường hợp khác

Kể từ JMS 2.0, Jakarta Messaging có API đơn giản hóa sử dụng `JMSContext`; một số thao tác ném `jakarta.jms.JMSRuntimeException` hoặc subtype của nó. Đây **đã là unchecked exception** từ API Jakarta, không phải `JMSException` và không phải `org.springframework.jms.JmsException`.

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSRuntimeException;

final class DirectContextExample {
    void sendDirectly(ConnectionFactory factory) {
        try (JMSContext context = factory.createContext()) {
            context.createProducer().send(
                    context.createQueue("orders.created"), "hello");
        } catch (JMSRuntimeException ex) {
            // Lỗi trực tiếp từ Jakarta JMSContext, chưa qua JmsTemplate.
            throw ex;
        }
    }
}
~~~

Đoạn này cần `ConnectionFactory`/broker thật. Không thể truyền `JMSRuntimeException` vào `JmsUtils.convertJmsAccessException(JMSException)` vì kiểu tham số khác nhau. Nếu dự án dùng trực tiếp `JMSContext`, hãy bắt đúng họ `JMSRuntimeException` hoặc một supertype phù hợp.

| API bạn gọi | Họ ngoại lệ cần chú ý | Ai chuyển đổi? |
|---|---|---|
| `jakarta.jms.Session` / API JMS cổ điển | `JMSException` (checked) | Caller xử lý, khai báo hoặc tự chuyển tại boundary. |
| `jakarta.jms.JMSContext` / API đơn giản hóa | `JMSRuntimeException` (unchecked) | Thông thường caller xử lý trực tiếp; không mặc nhiên là Spring `JmsException`. |
| `org.springframework.jms.core.JmsTemplate` | `JmsException` (unchecked) khi template chuyển lỗi checked; đồng thời có thể có lỗi runtime khác | Spring xử lý trong phạm vi các lời gọi mà template quản lý. |
| `@JmsListener` | Lỗi nghiệp vụ do listener ném, lỗi JMS/provider/container | Listener container và cấu hình transaction/error handling quyết định đường đi và redelivery. |

## 8. Thiết kế xử lý lỗi: phân loại trước khi retry

Việc một exception là unchecked **không** có nghĩa nên tự động retry mọi lần. Chọn chính sách dựa trên nguyên nhân thực tế, side effect và khả năng idempotent:

| Tình huống | Hướng xử lý ban đầu |
|---|---|
| Sai tên Queue/Topic, selector sai cú pháp | Sửa code/cấu hình; retry cùng input thường lặp lại lỗi. |
| Sai credentials/ACL | Sửa xác thực/phân quyền; không lặp nhanh vô hạn. |
| Broker tạm ngừng, pool/connection cạn, timeout | Có thể retry với backoff, jitter và giới hạn; kiểm tra lỗi cụ thể và tình trạng broker. |
| Payload không hợp lệ/schema không khớp | Tách message lỗi, cảnh báo; sửa schema/consumer, DLQ khi phù hợp. |
| Transaction rollback hoặc caller không rõ broker đã nhận message chưa | Chấp nhận khả năng giao lại/gửi lại; dùng message ID hoặc business key để chống xử lý trùng. |
| Provider ném lỗi không phân loại | Giữ error code/cause, quan sát và phân loại bằng bằng chứng vận hành trước khi thiết lập retry. |

### Với publisher: lỗi không chứng minh message chưa được gửi

Giả sử request gửi bị timeout ngay sau khi broker đã nhận message nhưng trước khi client nhận xác nhận. Caller chỉ thấy lỗi, không thể khẳng định broker chắc chắn chưa nhận. Nếu retry ngay, có thể có hai bản message.

Cách bảo vệ phù hợp: gắn `eventId` ổn định, ghi trạng thái phát sự kiện trong outbox nếu cần bảo đảm publish sau commit DB, và để consumer có cơ chế idempotency/deduplication theo `eventId` hoặc business key. Spring translation chỉ đổi **kiểu lỗi**, không giải quyết bài toán duplicate delivery.

### Với consumer: đừng nuốt exception nếu muốn rollback

Ví dụ listener xử lý có lỗi nhưng catch rồi bỏ qua:

~~~java
@JmsListener(destination = "orders.created")
public void onMessage(String payload) {
    try {
        updateDatabase(payload);
    } catch (RuntimeException ex) {
        // Sai nếu coi message đã xử lý và không có chính sách bù/trả lại.
        System.err.println("Processing failed: " + ex.getMessage());
    }
}
~~~

Đây là ví dụ cố ý minh họa anti-pattern: `updateDatabase` do ứng dụng định nghĩa. Khi listener trả về bình thường, container có thể xác nhận/commit message tùy cấu hình, dù nghiệp vụ thất bại.

Nếu cần redelivery, nên cho lỗi lan ra listener container và cấu hình **session transaction, acknowledgement, retry/backoff, DLQ** đúng với broker. Chẳng hạn một `DefaultJmsListenerContainerFactory` được cấu hình `setSessionTransacted(true)` sẽ rollback JMS session khi listener thất bại, nhưng cần kiểm tra chính sách broker để biết message được phát lại bao nhiêu lần và lúc nào. Rollback JMS không tự động rollback dữ liệu trong DB khi hai nguồn tài nguyên không tham gia cùng transaction phù hợp.

Cũng đừng bắt `JmsException` ở publisher và giả định đã bắt được lỗi **phát sinh sau đó trong `@JmsListener`**: publisher và consumer xử lý bất đồng bộ, thường ở thread/process khác nhau.

## 9. Chẩn đoán đúng khi exception đã được Spring bọc

Trong log production, theo dõi cả lớp lỗi ở tầng Spring và nguyên nhân sâu hơn. Ví dụ:

~~~java
catch (org.springframework.jms.JmsException ex) {
    String type = ex.getClass().getName();
    String code = ex.getErrorCode(); // Có thể null.
    Throwable cause = ex.getCause();

    System.err.println("springType=" + type);
    System.err.println("providerCode=" + code);
    System.err.println("causeType="
            + (cause == null ? "(none)" : cause.getClass().getName()));

    // Quyết định retry hoặc rethrow ở boundary phù hợp.
    throw ex;
}
~~~

Đây là mảnh mã cho một `try/catch` khi gọi Spring JMS, không phải chương trình độc lập. Khi dùng logger thực, ưu tiên tham số hóa, ghi exception object để giữ stack trace, kèm correlation ID và destination nhưng tránh log trực tiếp payload nhạy cảm. Nếu error code chứa thông tin đặc thù broker, đừng sử dụng nó như contract nghiệp vụ đa broker.

Lưu ý về `getLinkedException()`:
- JMS API có cơ chế linked exception riêng. Nếu root cause là `JMSException`, bạn có thể đọc `((JMSException) cause).getLinkedException()` để điều tra.
- `getCause()` trên exception Spring thường trỏ tới `JMSException` đã được bọc; nếu có linked exception sâu bên trong thì không chắc nó tự xuất hiện ở cùng vị trí trong chuỗi causes Java.
- Cần giữ cả stack trace, error code, thời gian xảy ra lỗi và log broker để kết luận; chỉ đọc một `getMessage()` là chưa đủ.

### Có nên catch Exception hoặc RuntimeException chung?

Tại một ranh giới quyết định retry/logging, catch `JmsException` là cách phân loại lỗi Spring JMS thường tốt hơn catch mọi `RuntimeException`. Tuy nhiên, nếu mã còn gọi `JMSContext` trực tiếp, ngoại lệ `JMSRuntimeException` nằm ngoài họ đó. Catch quá rộng có thể làm che lỗi lập trình như `NullPointerException`; cần phân biệt lỗi hạ tầng với bug.

## 10. Các hiểu nhầm phổ biến

| Nhận định sai | Điều cần nhớ |
|---|---|
| “JMSException của Jakarta là RuntimeException.” | `JMSException extends Exception` (checked); `JMSRuntimeException` mới là kiểu unchecked của Jakarta. |
| “JmsException của Spring là checked.” | Spring `JmsException` kế thừa `NestedRuntimeException`, vì vậy unchecked. |
| “Dùng JmsTemplate thì phải throws JMSException.” | Các API Spring template thường cung cấp `JmsException` unchecked; caller không phải khai báo checked JMSException. |
| “Bất kỳ RuntimeException nào cũng là JmsException.” | Có nhiều họ runtime khác: `JMSRuntimeException` của Jakarta, lỗi chuyển đổi/validation nghiệp vụ, bug trong listener. |
| “Spring translation làm mất mã lỗi provider.” | Spring giữ cause; `JmsException.getErrorCode()` có thể lấy mã JMS khi có. |
| “Dùng catch (JmsException) là đã có retry.” | Catch chỉ xử lý luồng điều khiển; retry, backoff, số lần thử và DLQ phải được cấu hình hoặc thiết kế riêng. |
| “Đã ném exception nghĩa là broker chắc chắn không nhận message.” | Timeout hoặc lỗi mạng có thể khiến kết quả gửi không xác định; cần chống trùng. |
| “Nuốt exception trong @JmsListener không ảnh hưởng ACK.” | Trả về bình thường có thể dẫn đến ACK/commit theo mode; cần xem transaction và container configuration. |

## 11. Câu hỏi tự kiểm tra

1. Vì sao hàm gọi `Session.createTextMessage(...)` có thể cần `throws JMSException`, còn hàm gọi `JmsTemplate.convertAndSend(...)` thường không cần?
2. Có hai lớp `InvalidDestinationException`: một trong `jakarta.jms`, một trong `org.springframework.jms`. Lớp nào checked và lớp nào runtime?
3. Sau khi gọi `JmsUtils.convertJmsAccessException(ex)`, làm thế nào truy cập lại mã lỗi của provider và object ngoại lệ ban đầu?
4. `JMSRuntimeException` có phải subclass của Spring `JmsException` hay không?
5. Một lần send timeout. Vì sao không thể tự kết luận message chưa được broker chấp nhận?
6. Listener đã catch mọi lỗi, ghi log rồi return bình thường. Điều gì có thể xảy ra với acknowledgement/transaction?

**Đáp án gợi ý:**
1. API Jakarta JMS cổ điển khai báo checked exception; Spring template quản lý phần API checked và chuyển thành runtime `JmsException` khi bắt được.
2. `jakarta.jms.InvalidDestinationException` là checked; `org.springframework.jms.InvalidDestinationException` là unchecked.
3. `translated.getErrorCode()` và `translated.getCause()`; nếu cần, kiểm tra thêm `JMSException.getLinkedException()` của cause.
4. Không. Đây là hai cây ngoại lệ khác nhau; `JMSRuntimeException` đã là unchecked từ Jakarta.
5. Có thể broker đã nhận nhưng phản hồi bị mất; retry có nguy cơ duplicate, nên cần event ID/idempotency.
6. Container có thể coi lần xử lý đã thành công và xác nhận message; hành vi cụ thể tùy ack mode/transaction; không được mặc định có redelivery.

## 12. Tài liệu tham khảo

- [Jakarta Messaging 3.1 — JMSException API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/jms/jmsexception).
- [Jakarta EE Tutorial — Messaging exception handling](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html).
- [Spring Framework — JmsException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/JmsException.html).
- [Spring Framework — JmsUtils Javadoc (convertJmsAccessException)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/JmsUtils.html).
- [Spring Framework — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring Framework Reference — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
