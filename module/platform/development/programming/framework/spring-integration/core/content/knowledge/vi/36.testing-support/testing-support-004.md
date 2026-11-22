# TestUtils

## 1. Vai trò trong kiểm thử Spring Integration Core

Trong module **SPRING_INTEGRATION_CORE**, các thành phần như Message, MessageChannel, endpoint và Java DSL phối hợp để tạo thành luồng thông điệp. Khi kiểm thử, đôi lúc cần xác nhận một thành phần đã nhận đúng cấu hình bên trong, chẳng hạn dispatcher của channel đang dùng chính xác strategy được khai báo.

`org.springframework.integration.test.util.TestUtils` cung cấp các tiện ích phục vụ nhu cầu này. Chức năng nổi bật là đọc field, kể cả field private và đường dẫn lồng nhau, để viết assertion về cấu trúc của đối tượng. Lớp nằm trong artifact `spring-integration-test-support`. [Spring Integration: Testing support](https://docs.spring.io/spring-integration/reference/testing.html)

Ví dụ tình huống thực tế: một hệ thống nhận mã đơn hàng, chuẩn hóa chuỗi rồi gửi sang channel kết quả. Hai câu hỏi kiểm thử có mục tiêu riêng:

| Câu hỏi | Bằng chứng cần thu thập |
| --- | --- |
| Channel đầu vào nhận đúng strategy từ cấu hình Spring chưa? | So sánh đối tượng strategy bên trong dispatcher với bean đã cấu hình |
| Mã đơn hàng có được chuẩn hóa đúng không? | Gửi Message và kiểm tra payload, header của Message đầu ra |

Một assertion bằng TestUtils trả lời câu hỏi thứ nhất. Kết quả message đầu ra trả lời câu hỏi thứ hai. Duy trì cả hai khi cấu hình nội bộ đó có ý nghĩa đối với thiết kế.

Sau bài này, người học có thể đọc thuộc tính lồng nhau, chọn assertion phù hợp, kết hợp kiểm tra cấu hình với kiểm tra hành vi và nhận biết khi nào một test đang phụ thuộc quá sâu vào chi tiết triển khai.

## 2. Chuẩn bị dependency và chọn cách gọi API

Các ví dụ đầy đủ bên dưới lấy **Java 17+, Spring Integration 6.5.x, Spring Framework 6.2.x và JUnit Jupiter 5** làm nền minh họa. Đây là phạm vi của ví dụ, không phải yêu cầu đổi phiên bản của dự án đang học.

Trong ứng dụng đã có `spring-integration-core`, thêm các dependency kiểm thử sau. Đoạn XML giả định Spring Boot dependency management hoặc BOM của dự án đã quản lý phiên bản tương thích cho cả Spring và JUnit:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test-support</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu dự án chưa có dependency management, cần khai báo phiên bản tương thích và cấu hình test runner hỗ trợ JUnit Jupiter trước khi sử dụng. Khi đã có dependency tương đương từ starter kiểm thử, tránh khai báo lặp chỉ để làm giống ví dụ.

`spring-integration-test-support` chứa các tiện ích cơ bản; `spring-integration-test` cung cấp thêm hỗ trợ mock và cấu hình context cho integration test. Chỉ sử dụng TestUtils không đòi hỏi phải đặt `@SpringIntegrationTest` lên mọi lớp test. [Phân chia các module kiểm thử](https://docs.spring.io/spring-integration/reference/testing.html)

### Khác biệt phiên bản cần nhận biết

| API | Spring Integration 6.5.x | Từ Spring Integration 7.1 |
| --- | --- | --- |
| `getPropertyValue(root, path)` | Trả về `Object` | Có kiểu trả về generic |
| `getPropertyValue(root, path, Type.class)` | Có overload trả về generic | Deprecated, được đánh dấu để loại bỏ |

Đối chiếu chữ ký tại [Javadoc 6.5.x](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/test/util/TestUtils.html) và ghi chú deprecation tại [Javadoc TestUtils](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/test/util/TestUtils.html).

Bài dùng dạng hai tham số rồi assertion trên `Object`. Khi cần biến có kiểu cụ thể, có thể cast rõ ràng:

```java
Object actual = TestUtils.getPropertyValue(
        channel, "dispatcher.loadBalancingStrategy");

LoadBalancingStrategy strategy =
        (LoadBalancingStrategy) actual;
```

Cast chỉ kiểm tra khả năng gán kiểu tại thời điểm chạy, không chuyển đổi dữ liệu. Chẳng hạn, cast một `String` thành `Integer` không có tác dụng parse số.

Khi chuyển ví dụ sang Spring Integration 7.x, cần kiểm tra cả nền Spring Framework và JUnit của dòng đó; không giữ nguyên toàn bộ dependency chỉ vì câu lệnh TestUtils vẫn giống nhau. Spring Framework 7 yêu cầu JUnit Jupiter 6 trở lên cho `SpringExtension`. [Spring TestContext: hỗ trợ JUnit Jupiter](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)

## 3. Hiểu đúng getPropertyValue

Cách gọi cốt lõi:

```java
Object actual = TestUtils.getPropertyValue(root, propertyPath);
```

- `root`: đối tượng bắt đầu kiểm tra.
- `propertyPath`: đường đi tới field cần đọc.
- `actual`: giá trị đọc được, dùng cho assertion.

Ví dụ `"dispatcher.loadBalancingStrategy"` biểu diễn hai lần truy cập:

```text
DirectChannel
    └── dispatcher
            └── loadBalancingStrategy
```

Đây là truy cập field thông qua `DirectFieldAccessor`; đường dẫn không phải biểu thức SpEL và không phải chuỗi gọi phương thức. Không viết `"dispatcher.getLoadBalancingStrategy()"`. [Cơ chế của TestUtils](https://docs.spring.io/spring-integration/reference/testing.html)

Trong triển khai 6.5.0, field cuối có giá trị null được trả về dưới dạng null; field trung gian null làm việc đi tiếp thất bại với `IllegalArgumentException`. Tên field không tồn tại cũng gây lỗi truy cập thay vì mang nghĩa “không có kết quả”. [Mã nguồn getPropertyValue, phiên bản 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-test-support/src/main/java/org/springframework/integration/test/util/TestUtils.java)

Ví dụ, `dispatcher` tồn tại và `loadBalancingStrategy` bằng null là trạng thái khác với việc đối tượng gốc không có field `dispatcher`. Vì vậy, chỉ viết `assertNull` khi null thực sự là cấu hình được mong đợi.

Đường dẫn field là chuỗi nên trình biên dịch không bảo vệ được việc đổi tên hoặc thay đổi cấu trúc nội bộ. Mỗi đường dẫn nên gắn với một lý do kiểm thử cụ thể.

## 4. Ví dụ nhỏ: xác nhận strategy của DirectChannel

Ví dụ sau là một lớp test đầy đủ, không cần khởi động ApplicationContext:

```java
import org.junit.jupiter.api.Test;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dispatcher.LoadBalancingStrategy;
import org.springframework.integration.dispatcher.RoundRobinLoadBalancingStrategy;
import org.springframework.integration.test.util.TestUtils;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

class DirectChannelStructureTests {

    @Test
    void keepsTheConfiguredStrategyInstance() {
        LoadBalancingStrategy expected =
                new RoundRobinLoadBalancingStrategy();
        DirectChannel channel = new DirectChannel(expected);

        Object actual = TestUtils.getPropertyValue(
                channel, "dispatcher.loadBalancingStrategy");

        assertSame(expected, actual,
                "Dispatcher phải giữ đúng strategy đã truyền vào");
    }

    @Test
    void allowsAnExplicitlyAbsentStrategy() {
        DirectChannel channel = new DirectChannel(null);

        Object actual = TestUtils.getPropertyValue(
                channel, "dispatcher.loadBalancingStrategy");

        assertNull(actual,
                "Null tại field cuối là cấu hình được chủ động lựa chọn");
    }
}
```

Trong dòng 6.5.0, `DirectChannel` có field `dispatcher`, và constructor nhận `LoadBalancingStrategy` chuyển strategy vào dispatcher. Khi strategy là null, channel không áp dụng cân bằng tải. [Mã nguồn DirectChannel 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/DirectChannel.java)

Tên `loadBalancingStrategy` ở nấc tiếp theo được xác định bởi cấu trúc `UnicastingDispatcher`. Đây là chi tiết triển khai mà test chủ động phụ thuộc. [Mã nguồn UnicastingDispatcher 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/UnicastingDispatcher.java)

### Chọn assertion theo điều cần chứng minh

| Assertion | Ý nghĩa trong ví dụ |
| --- | --- |
| `assertNotNull(actual)` | Có strategy, chưa xác nhận strategy nào |
| `assertTrue(actual instanceof RoundRobinLoadBalancingStrategy)` | Strategy thuộc kiểu mong muốn |
| `assertSame(expected, actual)` | Dispatcher giữ đúng instance được cung cấp |
| `assertEquals(expected, actual)` | So sánh theo quy tắc equals của đối tượng |

Nếu lỗi cần phát hiện là “cấu hình vô tình tạo một strategy khác cùng loại”, `assertSame` thể hiện yêu cầu rõ hơn kiểm tra kiểu.

Ví dụ này giúp học API và đường dẫn field. Trong một ứng dụng thực, kiểm tra wiring từ cấu hình Spring thường có giá trị hơn việc chỉ xác nhận lại constructor của thư viện.

## 5. Ví dụ thực tế: kiểm tra wiring và hành vi của flow Java DSL

Luồng minh họa:

```text
rawOrders (DirectChannel)
    → transformer: trim + uppercase
    → normalizedOrders (QueueChannel)
```

Yêu cầu nghiệp vụ: payload `"  order-42  "` trở thành `"ORDER-42"`, giữ header `trackingId`. Yêu cầu cấu hình: channel đầu vào sử dụng chính bean `orderStrategy`.

Java DSL biểu diễn flow bằng `IntegrationFlow` được đăng ký thành Spring bean; hạ tầng Integration xử lý việc tạo và đăng ký các thành phần của flow. [Spring Integration: Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)

Lớp test đầy đủ:

```java
import java.util.Locale;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dispatcher.LoadBalancingStrategy;
import org.springframework.integration.dispatcher.RoundRobinLoadBalancingStrategy;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.test.util.TestUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(OrderFlowTests.Config.class)
class OrderFlowTests {

    @Autowired
    @Qualifier("rawOrders")
    DirectChannel rawOrders;

    @Autowired
    @Qualifier("normalizedOrders")
    QueueChannel normalizedOrders;

    @Autowired
    @Qualifier("orderStrategy")
    LoadBalancingStrategy orderStrategy;

    @Test
    void wiresTheDeclaredStrategyIntoTheInputChannel() {
        Object actual = TestUtils.getPropertyValue(
                rawOrders, "dispatcher.loadBalancingStrategy");

        assertSame(orderStrategy, actual,
                "rawOrders phải dùng bean orderStrategy");
    }

    @Test
    void normalizesPayloadAndPreservesTrackingId() {
        Message<String> request = MessageBuilder
                .withPayload("  order-42  ")
                .setHeader("trackingId", "trace-42")
                .build();

        assertTrue(rawOrders.send(request, 1_000));

        Message<?> reply = normalizedOrders.receive(1_000);
        assertNotNull(reply, "Phải nhận được message đã chuẩn hóa");
        assertEquals("ORDER-42", reply.getPayload());
        assertEquals("trace-42",
                reply.getHeaders().get("trackingId"));
        assertNull(normalizedOrders.receive(0),
                "Ví dụ đồng bộ này chỉ tạo một message đầu ra");
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        LoadBalancingStrategy orderStrategy() {
            return new RoundRobinLoadBalancingStrategy();
        }

        @Bean
        DirectChannel rawOrders(
                @Qualifier("orderStrategy")
                LoadBalancingStrategy strategy) {

            return new DirectChannel(strategy);
        }

        @Bean
        QueueChannel normalizedOrders() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow normalizeOrders(
                @Qualifier("rawOrders")
                DirectChannel input,
                @Qualifier("normalizedOrders")
                QueueChannel output) {

            return IntegrationFlow.from(input)
                    .<String, String>transform(
                            value -> value.trim()
                                    .toUpperCase(Locale.ROOT))
                    .channel(output)
                    .get();
        }
    }
}
```

`@SpringJUnitConfig` kết hợp việc tích hợp JUnit Jupiter với Spring TestContext và nạp cấu hình được chỉ định. Trong ví dụ này, `@EnableIntegration` cung cấp hạ tầng xử lý các bean Integration. [Spring TestContext support classes](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html), [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)

### Đọc kết quả test cho đúng

Test wiring chỉ đọc cấu trúc. Nó không gửi message, không chứng minh transformer tạo đúng payload và không chứng minh có cân bằng tải giữa nhiều subscriber.

Test hành vi gửi một message vào flow và kiểm tra đầu ra. Nó có thể vẫn thành công nếu ai đó thay `orderStrategy` bằng một instance mới cùng loại, vì flow này chỉ có một subscriber xử lý đầu vào. Đó là lý do assertion về identity có giá trị riêng khi yêu cầu wiring là quan trọng.

`QueueChannel` đầu ra giúp test giữ lại kết quả để nhận và assertion. Nó không tự làm phần transformer trước đó chạy bất đồng bộ. Trong cấu hình minh họa, việc dispatch qua `DirectChannel` xảy ra trên thread gửi. [Đặc tính thực thi của DirectChannel](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/DirectChannel.java)

Giá trị `1_000` ở lệnh receive là thời gian chờ tối đa theo mili giây, không phải yêu cầu luôn đợi một giây. Timeout của send cũng không phải deadline tổng quát có khả năng ngắt transformer đang chạy trên thread gọi.

Assertion `receive(0)` cuối phù hợp với flow đồng bộ cụ thể này. Với flow bất đồng bộ, queue đang rỗng ở một thời điểm chưa đủ chứng minh rằng sau đó không có message trùng lặp.

## 6. Tạo context nhỏ bằng createTestApplicationContext

Khi chỉ cần một môi trường kiểm thử nhỏ và đăng ký đối tượng theo chương trình, có thể dùng `TestUtils.createTestApplicationContext()`. Factory trả về `TestUtils.TestApplicationContext`, một mở rộng của `GenericApplicationContext`. [Javadoc TestUtils 6.5.x](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/test/util/TestUtils.html)

Ví dụ độc lập sau minh họa trình tự đăng ký, refresh, sử dụng và đóng context:

```java
import org.junit.jupiter.api.Test;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.test.util.TestUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SmallTestContextTests {

    @Test
    void registersAndUsesAQueueChannel() {
        try (var context =
                     TestUtils.createTestApplicationContext()) {

            context.registerChannel(
                    "testReplies", new QueueChannel());
            context.refresh();

            QueueChannel replies =
                    context.getBean("testReplies", QueueChannel.class);

            assertTrue(replies.send(
                    MessageBuilder.withPayload("accepted").build(),
                    1_000));

            Message<?> message = replies.receive(1_000);
            assertNotNull(message);
            assertEquals("accepted", message.getPayload());
        }
    }
}
```

Ở triển khai 6.5.0, factory đăng ký scheduler, conversion service và error channel cơ bản; context cần được refresh trước khi lấy bean như ví dụ. Error channel mặc định của factory ghi log, nên khi cần assertion về lỗi, hãy chủ động bố trí channel thu thập lỗi trong cấu hình test. [Mã nguồn factory và TestApplicationContext](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-test-support/src/main/java/org/springframework/integration/test/util/TestUtils.java)

Ví dụ này chỉ đăng ký một channel. Nếu muốn kiểm thử bean Java DSL và quá trình xử lý annotation, nên dùng cấu hình Spring có `@EnableIntegration` như phần trước hoặc tự đăng ký đầy đủ hạ tầng cần thiết. Không suy ra rằng factory này đã nạp cấu hình ứng dụng của mình.

Đóng context trong `try-with-resources` gắn vòng đời tài nguyên với từng test. Cách này đặc biệt hữu ích khi các bean tạo scheduler hoặc executor.

## 7. Tra cứu message history bằng locateComponentInHistory

Khi cần xác nhận message đã đi qua một thành phần được theo dõi, `locateComponentInHistory(history, componentName, startingIndex)` tìm entry tương ứng từ vị trí bắt đầu. Helper trả về `Properties` hoặc null nếu không tìm thấy trong phạm vi tìm kiếm hợp lệ. [Javadoc locateComponentInHistory](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/test/util/TestUtils.html)

Trước hết, bật theo dõi trong cấu hình của flow ở phần 5 bằng cách thêm import và annotation:

```java
import org.springframework.integration.config.EnableMessageHistory;

// Đặt cùng @Configuration và @EnableIntegration trên Config:
@EnableMessageHistory
```

Annotation được đặt lên lớp `Config`, không đặt lẻ trong thân phương thức. Cơ chế message history ghi dấu các thành phần được theo dõi vào header của message. [Spring Integration: Message History](https://docs.spring.io/spring-integration/reference/message-history.html)

Sau khi nhận được `reply` không null trong test hành vi, có thể bổ sung đoạn assertion sau. Đây là phần mở rộng của test ở phần 5:

```java
// Thêm các import này vào OrderFlowTests:
import java.util.Properties;
import org.springframework.integration.history.MessageHistory;
import static org.junit.jupiter.api.Assertions.assertFalse;

// Đặt đoạn dưới trong test, sau assertNotNull(reply):
MessageHistory history = reply.getHeaders()
        .get(MessageHistory.HEADER_NAME, MessageHistory.class);

assertNotNull(history, "Cấu hình test phải bật message history");
assertFalse(history.isEmpty());

Properties inputStep = TestUtils.locateComponentInHistory(
        history, "rawOrders", 0);

assertNotNull(inputStep,
        "History phải có channel đầu vào rawOrders");
assertEquals("rawOrders", inputStep.getProperty("name"));
```

TestUtils chỉ tìm trong history đã có; nó không bật tính năng theo dõi và không tạo entry còn thiếu.

Nếu giới hạn danh sách component được theo dõi, chỉ assertion những component nằm trong danh sách đó. Sự vắng mặt trong history khi chưa bật theo dõi không chứng minh message đã bỏ qua component. [Cấu hình tracked components](https://docs.spring.io/spring-integration/reference/message-history.html)

Nên kiểm tra ý nghĩa của dấu vết, chẳng hạn có channel bắt buộc, thay vì cố định toàn bộ timestamp hoặc tất cả vị trí của entry. Khi thêm một endpoint hợp lệ vào giữa flow, những assertion quá chặt về toàn bộ danh sách dễ tạo lỗi kiểm thử không liên quan tới yêu cầu nghiệp vụ.

## 8. Các tiện ích khác và phạm vi sử dụng

Ngoài đọc field và tạo context, TestUtils còn có một số helper đáng nhận biết:

| Helper | Tình huống có ích |
| --- | --- |
| `createTaskScheduler(poolSize)` | Tạo scheduler cho fixture kiểm thử cần lập lịch |
| `applySystemFileSeparator(path)` | Thay dấu `/` bằng dấu phân cách đường dẫn của hệ điều hành |
| `adjustLogLevels(...)`, `revertLogLevels(...)` | Điều chỉnh rồi khôi phục mức log trong môi trường kiểm thử tương thích |

Các tên và chữ ký được liệt kê trong [Javadoc TestUtils](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/test/util/TestUtils.html).

Về thiết kế fixture, hãy xác định rõ bên sở hữu tài nguyên. Scheduler được tạo riêng cho test cần được giải phóng khi test kết thúc; bean do context quản lý cần đi theo vòng đời context.

Helper thay dấu phân cách không thay thế kiểm tra đường dẫn hợp lệ, tồn tại hay quyền truy cập. Khi mục tiêu là thao tác đường dẫn trong mã ứng dụng, ưu tiên API `Path` phù hợp với nhu cầu.

Các helper đổi mức log có tham số gắn với Log4j2; cần kiểm tra backend và dependency của môi trường trước khi dùng. Việc đổi mức log cũng là thay đổi trạng thái có thể dùng chung giữa nhiều test, nên cần khôi phục ngay cả khi assertion thất bại. Với một bài chỉ học cách đọc cấu hình channel, không cần đưa thêm thay đổi logging vào fixture.

## 9. Giới hạn khi gặp proxy, endpoint và xử lý bất đồng bộ

### 9.1. Chọn đúng đối tượng gốc

Một tên bean endpoint có thể trỏ đến đối tượng quản lý vòng đời consumer, còn logic xử lý message nằm ở handler bên trong. Nếu đọc field của handler trên một endpoint khác loại, đường dẫn sẽ không có nghĩa.

Trước khi viết assertion, xác định:

1. Bean đang kiểm tra có vai trò channel, endpoint hay handler?
2. Kiểu đối tượng thực tế là gì?
3. Field cần đọc thuộc đối tượng nào trong cấu trúc đó?
4. Có API công khai nào diễn đạt cùng yêu cầu rõ hơn không?

Không mặc định mọi thành phần đều có field `handler`, `target` hoặc `dispatcher` giống nhau. Hạn chế dùng các tên sinh tự động từ Java DSL khi có thể đặt tên thành phần quan trọng một cách chủ động.

### 9.2. Không coi reflection là cơ chế tự tháo proxy

Nếu bean là AOP proxy, cấu trúc thấy được có thể khác đối tượng đích mà mình muốn kiểm tra. Cần xác định proxy và cách lấy target phù hợp với cơ chế Spring đang sử dụng; việc đó là bước riêng với đọc field bằng TestUtils.

Với proxy có target động hoặc target theo scope, lấy target có thể liên quan tới vòng đời khác với singleton thông thường. Nếu mục tiêu là hành vi của bean công khai, gửi message hoặc gọi API công khai thường diễn đạt yêu cầu tốt hơn việc truy sâu vào proxy.

### 9.3. Đọc field không chờ công việc hoàn thành

TestUtils không cung cấp cơ chế await cho flow. Nếu message đi qua executor, poller hoặc adapter bất đồng bộ, việc đọc một field ngay sau send có thể xảy ra trước khi xử lý xong.

Ưu tiên chờ theo tín hiệu có ý nghĩa: message đầu ra với timeout hữu hạn, latch do fixture sở hữu hoặc điều kiện có giới hạn thời gian. Khi đã có kết quả ổn định mới kiểm tra trạng thái liên quan.

Không dùng vòng lặp vô hạn gọi getPropertyValue. Cũng không dùng `Thread.sleep` như bằng chứng công việc đã hoàn tất: thời gian ngủ chỉ làm chậm test, không mô tả điều kiện thành công.

### 9.4. Giữ assertion cấu trúc gọn và có lý do

Một test khẳng định “bean dùng đúng strategy đã cấu hình” có lý do rõ ràng. Một test đọc gần như toàn bộ object graph rồi đóng băng mọi field khiến việc bảo trì khó hơn.

Với transformer, router, filter hoặc aggregator, bằng chứng chính vẫn nên gắn với hợp đồng của flow: payload nào được biến đổi, message nào được chuyển nhánh, message nào bị loại, nhóm nào tạo kết quả và lỗi được quan sát ở đâu. Chỉ thêm assertion nội bộ khi nó bảo vệ một quyết định cấu hình có ý nghĩa mà kiểm tra hành vi hiện tại chưa thể hiện.

## 10. Chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy class TestUtils | Thiếu test-support hoặc import sai | Kiểm tra artifact và package đầy đủ |
| Field không tồn tại | Sai đối tượng gốc, sai tên field hoặc cấu trúc đổi theo phiên bản | Xác định kiểu bean và đối chiếu đúng phiên bản |
| Lỗi tại một nấc trung gian | Đối tượng trung gian null | Kiểm tra cấu hình và thời điểm khởi tạo |
| Cast thất bại | Giá trị thực tế không thuộc kiểu giả định | Assertion kiểu trước khi sử dụng tiếp |
| Đọc field được nhưng assertion identity sai | Bean khác instance mong muốn | Xem lại wiring, qualifier và cách tạo đối tượng |
| Test wiring đạt, test hành vi lỗi | Cấu hình được gắn nhưng flow xử lý sai | Kiểm tra endpoint, dữ liệu đầu vào và channel kết quả |
| Không có history | Chưa bật theo dõi hoặc component không được theo dõi | Kiểm tra annotation và phạm vi tracking |
| Nhận message lúc được lúc không | Thiếu chờ hoàn tất hoặc fixture chia sẻ trạng thái | Chờ theo tín hiệu, cô lập dữ liệu và dọn tài nguyên |
| Cảnh báo deprecated khi dùng ba tham số | API của dòng 7.1 trở lên | Chuyển sang overload hai tham số theo API đang dùng |

Đừng giải quyết lỗi truy cập field bằng cách thử nhiều đường dẫn rồi chấp nhận đường dẫn nào không ném exception. Cách đó dễ che khuất thay đổi cấu trúc và làm mất ý nghĩa của test.

## 11. Bài tập thực hành

### Bài tập 1: phân biệt kiểm tra kiểu và identity

Trong cấu hình phần 5, thay `return new DirectChannel(strategy)` bằng:

```java
return new DirectChannel(
        new RoundRobinLoadBalancingStrategy());
```

Dự đoán trước khi chạy:

- Assertion `assertSame(orderStrategy, actual)` phải thất bại.
- Assertion chỉ kiểm tra kiểu round-robin vẫn có thể thành công.
- Test chuẩn hóa payload vẫn có thể thành công.

Giải thích được ba kết quả này cho thấy người học phân biệt được wiring với hành vi.

### Bài tập 2: sửa hành vi mà vẫn giữ wiring

Giữ cấu hình strategy, nhưng bỏ `trim()` khỏi transformer. Xác định assertion nào phát hiện lỗi và vì sao TestUtils không thể thay thế assertion payload trong tình huống này.

### Bài tập 3: theo dõi đường đi có chọn lọc

Bật message history, chỉ theo dõi `rawOrders`, rồi xác nhận entry đó tồn tại. Sau đó mở rộng để theo dõi thêm channel kết quả mà không cố định timestamp.

### Bài tập 4: đánh giá độ bền của một assertion

Chọn một field nội bộ đang được kiểm tra trong dự án. Viết ra yêu cầu thiết kế mà assertion đó bảo vệ. Nếu không diễn đạt được yêu cầu, cân nhắc chuyển sang kiểm tra qua public API hoặc message đầu ra.

## 12. Điểm cần ghi nhớ

TestUtils phù hợp khi cần quan sát một chi tiết cấu hình khó truy cập qua API công khai. Đường dẫn field phải đúng với kiểu đối tượng và phiên bản thư viện.

Một bộ kiểm thử hữu ích kết hợp bằng chứng về wiring với bằng chứng từ message đầu ra. Khi flow có executor, poller, gateway hoặc adapter ngoài tiến trình, cần thiết kế cách chờ và quan sát lỗi phù hợp; việc đọc field không thay thế các cơ chế đó.

Giữ các assertion nội bộ ngắn, có mục tiêu và gắn với quyết định cấu hình cần bảo vệ. Khi nâng cấp framework, những test này là nơi cần xem lại đường dẫn và mức độ phụ thuộc vào cấu trúc triển khai.
