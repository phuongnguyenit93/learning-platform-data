# Lưu state bằng MessageStore

## 1. Mục tiêu thực hành

Trong chương **Thực hành tổng hợp** của **SPRING_INTEGRATION_CORE**, bài này xây dựng một luồng tiếp nhận các sự kiện của đơn hàng, lưu nhóm thông điệp đang chờ và tiếp tục xử lý sau khi ứng dụng khởi động lại.

Sau bài thực hành, bạn có thể:

- Phân biệt lưu một `Message`, lưu `MessageGroup` và lưu metadata nghiệp vụ.
- Gắn `JdbcMessageStore` vào aggregator bằng Java DSL.
- Thiết kế correlation key ổn định và release strategy chịu được sự kiện gửi lặp.
- Kiểm tra trạng thái trên cơ sở dữ liệu qua hai application context độc lập.
- Quy định cách xử lý nhóm thiếu dữ liệu, thông điệp đến muộn và dữ liệu đã hoàn tất.
- Xác định phần nào cần transaction, distributed lock và idempotency khi triển khai thực tế.

Kiến thức cần có: `Message`, payload/header, `DirectChannel`, `QueueChannel`, gateway, filter và aggregator. Phần JDBC chỉ đóng vai trò lưu trạng thái tích hợp; trọng tâm vẫn là hành vi của các thành phần Spring Integration Core.

## 2. Bài toán: đơn hàng đang xử lý thì ứng dụng dừng

Một đơn hàng chỉ sẵn sàng hoàn tất khi nhận đủ ba xác nhận:

| Loại sự kiện | Ý nghĩa | Ví dụ reference |
| --- | --- | --- |
| `PAYMENT` | Thanh toán thành công | `PAY-101` |
| `STOCK` | Đã giữ hàng | `STOCK-101` |
| `SHIPMENT` | Đã tạo vận đơn | `SHIP-101` |

Các xác nhận có thể đến khác thứ tự, được gửi lại, hoặc cách nhau vài phút. Kịch bản quan trọng nhất:

1. Ứng dụng A nhận `PAYMENT` và `STOCK` cho `ORD-101`.
2. A dừng trước khi nhận `SHIPMENT`.
3. Ứng dụng B mở lại cùng cơ sở dữ liệu.
4. B nhận `SHIPMENT` và tạo kết quả chứa cả ba xác nhận.

Nếu nhóm thông điệp chỉ nằm trong bộ nhớ của A, B sẽ chỉ nhìn thấy xác nhận cuối cùng. Lưu state ở đây có nghĩa là lưu các thông điệp đang chờ cùng thông tin của nhóm để aggregator mới tiếp tục quyết định khi có dữ liệu đến.

Không giả định ứng dụng có thể tự hoàn thành mọi nhóm ngay khi mở lên. Trong luồng này, thông điệp mới kích hoạt đánh giá release; nhóm không còn nhận thông điệp cần một chính sách expiry riêng.

## 3. Chọn đúng loại store

Spring Integration có những hợp đồng lưu trữ phục vụ các nhu cầu khác nhau:

| Thành phần | Trạng thái được quản lý | Tình huống sử dụng |
| --- | --- | --- |
| `MessageStore` | Thông điệp theo message ID | Cất và lấy lại một thông điệp, chẳng hạn claim check |
| `MessageGroupStore` | Nhóm, thông điệp thành viên và metadata nhóm | Aggregator, resequencer |
| `ChannelMessageStore` | Các thao tác lưu/poll tối ưu cho channel | Hàng đợi của `QueueChannel` |
| `MetadataStore` | Cặp khóa–giá trị phục vụ metadata | Tiến độ tiếp nhận, khóa nhận diện sự kiện đã xử lý |
| Bảng nghiệp vụ | Sự thật nghiệp vụ do ứng dụng định nghĩa | Đơn hàng, thanh toán, kết quả đã hoàn tất |

`SimpleMessageStore` lưu trong bộ nhớ nên không giữ được state qua việc kết thúc JVM. Một persistent store cần lưu dữ liệu bên ngoài tiến trình; đồng thời vẫn phải xem xét cách payload và header được tuần tự hóa. [Tài liệu Message Store](https://docs.spring.io/spring-integration/reference/6.5/message-store.html).

Với JDBC, chọn `JdbcMessageStore` cho nhóm của aggregator. Khi cần lưu hàng đợi channel, dùng `JdbcChannelMessageStore` với query provider tương ứng cơ sở dữ liệu. Hai lựa chọn này phục vụ hai vai trò khác nhau trong cùng một hệ thống. [Tài liệu JDBC Message Store](https://docs.spring.io/spring-integration/reference/6.5/jdbc/message-store.html).

Một bean store tồn tại trong Spring context chưa làm cho luồng có tính bền vững. Aggregator phải thực sự được cấu hình sử dụng bean đó.

## 4. Hợp đồng trạng thái và luồng xử lý

Bài thực hành dùng các quy ước:

| Thuộc tính | Giá trị hoặc quy tắc |
| --- | --- |
| Correlation key | `order-assembly:v1:<orderId>` |
| Store region | `orders-assembly-v1` |
| Điều kiện release | Có đủ ba loại xác nhận; mỗi loại chỉ có một reference phân biệt |
| Sự kiện lặp giống nhau | Không làm nhóm hoàn tất sớm |
| Cùng loại nhưng khác reference | Giữ nhóm chưa hoàn tất để xử lý xung đột |
| Hoàn tất bình thường | Xóa thông điệp thành viên, giữ dấu nhóm đã hoàn tất |
| Nhóm quá hạn | Chuyển thông điệp sang discard channel, không tạo đơn hàng hoàn chỉnh |
| Kênh quan sát kết quả trong lab | `QueueChannel` trong bộ nhớ |

~~~mermaid
flowchart LR
    P["OrderPart"] --> G["Gateway một chiều"]
    G --> I["orderParts: DirectChannel"]
    I --> F{"Dữ liệu hợp lệ?"}
    F -->|Không| V["invalidParts"]
    F -->|Có| A["Aggregator"]
    A <-->|Lưu và đọc nhóm| S[("JdbcMessageStore")]
    A -->|Đủ điều kiện| O["completedOrders"]
    A -->|Expiry hoặc đến muộn| D["discardedParts"]
    R["Reaper được lập lịch"] -->|Kiểm tra tuổi nhóm| S
~~~

Bài này cố ý dùng output queue trong bộ nhớ để đọc kết quả trong kiểm thử. Khi kết quả đã được phát ra queue đó, việc restart sẽ làm mất kết quả chưa được nhận. Bài kiểm thử khôi phục vì vậy dừng ứng dụng ở thời điểm nhóm **chưa hoàn tất**.

Correlation key phải được tạo giống nhau giữa các lần chạy. Không đưa UUID ngẫu nhiên của lần khởi động vào key hoặc region. Trong hệ thống nhiều tenant, thêm tenant vào khóa và kiểm thử hai tenant có cùng `orderId`.

## 5. Chuẩn bị dự án thực hành

Ví dụ khóa bộ phiên bản minh họa ở Java 17, Spring Boot 3.5.0 và Spring Integration 6.5.0. Đây là baseline để tái hiện bài học; khi áp dụng vào dự án, dùng BOM tương thích của dự án. Spring Boot 3.5.0 quản lý Spring Integration 6.5.0 trong BOM của nó. [Khai báo dependency chính thức](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.5.0/spring-boot-project/spring-boot-dependencies/build.gradle).

Các file dưới đây là mã mẫu để người học tạo trong một dự án lab riêng.

### 5.1. Dependencies

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>message-store-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-integration</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. DataSource và schema

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none

spring.datasource.url=jdbc:h2:file:./target/message-store-lab/state;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=

spring.integration.jdbc.initialize-schema=never
spring.sql.init.mode=never
spring.sql.init.schema-locations=classpath:org/springframework/integration/jdbc/schema-h2.sql
~~~

Có hai cơ chế khởi tạo schema có thể xuất hiện trong ứng dụng Boot: khởi tạo SQL tổng quát và khởi tạo JDBC của Integration. Ví dụ chỉ sử dụng cơ chế SQL tổng quát khi kiểm thử yêu cầu `spring.sql.init.mode=always`; cơ chế còn lại được tắt để tránh tạo bảng hai lần.

Script trong JAR `spring-integration-jdbc` định nghĩa các bảng như:

| Bảng | Vai trò trong bài |
| --- | --- |
| `INT_MESSAGE` | Lưu dữ liệu thông điệp |
| `INT_MESSAGE_GROUP` | Lưu metadata nhóm |
| `INT_GROUP_TO_MESSAGE` | Liên kết nhóm với các thông điệp |
| `INT_LOCK` | Có thể phục vụ khóa JDBC khi mở rộng nhiều instance |

Tên cột và kiểu dữ liệu cần theo script của đúng phiên bản và đúng hệ quản trị. Không tự tạo một bảng payload đơn giản rồi kỳ vọng `JdbcMessageStore` sử dụng được. [Schema H2 của Spring Integration 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-h2.sql).

Trong kiểm thử restart, context đầu tiên tạo schema trên database mới; context thứ hai dùng `never`. Chạy lại script tạo bảng không có điều kiện trên database đã tồn tại sẽ gây lỗi. Với môi trường triển khai, quản lý DDL bằng migration và giữ lại dữ liệu giữa các lần phát hành.

### 5.3. Payload có thể tuần tự hóa

`src/main/java/vn/example/messagestore/OrderPart.java`:

~~~java
package vn.example.messagestore;

import java.io.Serial;
import java.io.Serializable;

public record OrderPart(
        String orderId,
        Kind kind,
        String reference) implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    public enum Kind {
        PAYMENT, STOCK, SHIPMENT
    }
}
~~~

`src/main/java/vn/example/messagestore/OrderSummary.java`:

~~~java
package vn.example.messagestore;

import java.util.Map;

public record OrderSummary(
        String orderId,
        Map<OrderPart.Kind, String> references) {
}
~~~

`OrderPart` được lưu vào JDBC nên triển khai `Serializable`. `OrderSummary` trong lab chỉ đi vào queue bộ nhớ. Nếu đổi sang store sử dụng Java serialization cho output, phải thiết kế khả năng tuần tự hóa của cả kiểu kết quả và toàn bộ dữ liệu bên trong.

Không đặt connection, entity proxy hoặc service bean vào payload. Một DTO nhỏ với ID và reference rõ ràng giúp việc khôi phục qua lần triển khai sau dễ kiểm soát hơn.

### 5.4. Điểm vào bằng gateway

`src/main/java/vn/example/messagestore/OrderGateway.java`:

~~~java
package vn.example.messagestore;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderParts")
public interface OrderGateway {

    void accept(OrderPart part);
}
~~~

Gateway trả về `void` vì đơn hàng có thể phải chờ các sự kiện khác rất lâu. Không giữ một HTTP request hoặc lời gọi gateway request–reply cho đến khi đủ tất cả xác nhận. Kết quả hoàn tất có điểm ra riêng là `completedOrders`.

`src/main/java/vn/example/messagestore/MessageStoreLabApplication.java`:

~~~java
package vn.example.messagestore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.integration.annotation.IntegrationComponentScan;

@SpringBootApplication
@IntegrationComponentScan
public class MessageStoreLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageStoreLabApplication.class, args);
    }
}
~~~

Ứng dụng không có runner tự gửi dữ liệu. Kiểm thử sẽ điều khiển chính xác thông điệp đến trước và sau khi context đóng.

## 6. Cấu hình aggregator dùng JdbcMessageStore

`src/main/java/vn/example/messagestore/OrderFlowConfiguration.java`:

~~~java
package vn.example.messagestore;

import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.sql.DataSource;

import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    public static final String REGION = "orders-assembly-v1";

    public static String groupId(String orderId) {
        return "order-assembly:v1:" + orderId;
    }

    @Bean
    @DependsOnDatabaseInitialization
    public JdbcMessageStore orderGroupStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion(REGION);
        store.setTimeoutOnIdle(false);
        return store;
    }

    @Bean
    public DirectChannel orderParts() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel completedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel invalidParts() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel discardedParts() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow assembleOrderFlow(JdbcMessageStore orderGroupStore) {
        return IntegrationFlow.from("orderParts")
                .filter(OrderPart.class, OrderFlowConfiguration::valid,
                        f -> f.discardChannel("invalidParts"))
                .aggregate(a -> a
                        .messageStore(orderGroupStore)
                        .correlationStrategy(message -> groupId(
                                ((OrderPart) message.getPayload()).orderId()))
                        .releaseStrategy(OrderFlowConfiguration::ready)
                        .outputProcessor(OrderFlowConfiguration::summarize)
                        .expireGroupsUponCompletion(false)
                        .expireGroupsUponTimeout(false)
                        .sendPartialResultOnExpiry(false)
                        .minimumTimeoutForEmptyGroups(300_000)
                        .discardChannel("discardedParts"))
                .channel("completedOrders")
                .get();
    }

    private static boolean valid(OrderPart part) {
        return part.orderId() != null
                && !part.orderId().isBlank()
                && part.kind() != null
                && part.reference() != null
                && !part.reference().isBlank();
    }

    private static boolean ready(MessageGroup group) {
        Map<OrderPart.Kind, Set<String>> references =
                new EnumMap<>(OrderPart.Kind.class);

        for (Message<?> message : group.getMessages()) {
            OrderPart part = (OrderPart) message.getPayload();
            references.computeIfAbsent(part.kind(), key -> new HashSet<>())
                    .add(part.reference());
        }

        return references.keySet().equals(EnumSet.allOf(OrderPart.Kind.class))
                && references.values().stream()
                        .allMatch(values -> values.size() == 1);
    }

    private static OrderSummary summarize(MessageGroup group) {
        Map<OrderPart.Kind, String> references =
                new EnumMap<>(OrderPart.Kind.class);
        String orderId = null;

        for (Message<?> message : group.getMessages()) {
            OrderPart part = (OrderPart) message.getPayload();
            orderId = part.orderId();
            references.putIfAbsent(part.kind(), part.reference());
        }

        return new OrderSummary(orderId, Map.copyOf(references));
    }
}
~~~

Ba điểm quyết định trong cấu hình:

1. `.messageStore(orderGroupStore)` nối state của aggregator với JDBC.
2. `groupId(orderId)` đảm bảo các xác nhận của một đơn cùng đi vào một nhóm.
3. `ready()` kiểm tra dữ liệu nghiệp vụ thay vì chỉ đếm số `Message`.

Ví dụ `PAYMENT, PAYMENT, STOCK` có ba thông điệp nhưng thiếu `SHIPMENT`, nên không được release. Hai bản tin `PAYMENT` cùng reference vẫn nằm trong nhóm; kiểm tra trên tập reference giúp chúng không làm kết quả hoàn tất sai.

Nếu hai bản tin `PAYMENT` mang reference khác nhau, `ready()` trả về `false`. Lab giữ nhóm đó chờ expiry để quan sát xung đột, thay vì tự chọn một thanh toán. Trong hệ thống thật, có thể phát sự kiện xung đột và đưa nhóm sang quy trình xử lý riêng.

`summarize()` không dựa vào thứ tự lấy thông điệp từ store. Release strategy đã đảm bảo mỗi loại chỉ có một reference, nên việc gộp các bản tin lặp giống nhau cho kết quả xác định.

### Vòng đời nhóm trong cấu hình

- Khi mới nhận một phần: nhóm tồn tại, chưa complete và có thông điệp thành viên.
- Khi đủ dữ liệu: aggregator tạo `OrderSummary`, loại bỏ các thành viên đã xử lý và giữ metadata complete.
- Khi bản tin cùng key đến muộn: chuyển sang `discardedParts` trong lúc dấu complete còn tồn tại.
- Khi dấu complete được dọn: cùng key có thể tạo một nhóm mới.

Giữ metadata sau hoàn tất giúp chặn bản tin muộn trong một khoảng thời gian. Xóa toàn bộ nhóm ngay sau release cho phép cùng key mở lại ngay. Chính sách này phải phù hợp với thời gian nguồn có thể gửi lại dữ liệu. [Vòng đời aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

## 7. Kiểm thử khôi phục, gửi lặp và expiry

Một kiểm thử chỉ gửi ba bản tin trong cùng context chưa chứng minh được state có thể khôi phục. Cần đóng context đầu tiên, tạo context thứ hai và đọc lại nhóm từ cùng database.

`src/test/java/vn/example/messagestore/MessageStoreRecoveryTest.java`:

~~~java
package vn.example.messagestore;

import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupStoreReaper;
import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static vn.example.messagestore.OrderPart.Kind.PAYMENT;
import static vn.example.messagestore.OrderPart.Kind.SHIPMENT;
import static vn.example.messagestore.OrderPart.Kind.STOCK;

class MessageStoreRecoveryTest {

    @TempDir
    Path tempDirectory;

    private String databaseUrl() {
        String path = tempDirectory.resolve("state").toAbsolutePath()
                .toString().replace('\\', '/');
        return "jdbc:h2:file:" + path + ";DB_CLOSE_ON_EXIT=FALSE";
    }

    private ConfigurableApplicationContext open(String initMode) {
        return new SpringApplicationBuilder(MessageStoreLabApplication.class)
                .web(WebApplicationType.NONE)
                .run(
                        "--spring.datasource.url=" + databaseUrl(),
                        "--spring.sql.init.mode=" + initMode,
                        "--lab.expiry.enabled=false");
    }

    @Test
    void resumesIncompleteGroupAfterContextRestart() {
        String key = OrderFlowConfiguration.groupId("ORD-101");

        try (ConfigurableApplicationContext first = open("always")) {
            OrderGateway gateway = first.getBean(OrderGateway.class);
            JdbcMessageStore store = first.getBean(JdbcMessageStore.class);
            QueueChannel output = first.getBean(
                    "completedOrders", QueueChannel.class);

            gateway.accept(new OrderPart("ORD-101", PAYMENT, "PAY-101"));
            gateway.accept(new OrderPart("ORD-101", STOCK, "STOCK-101"));

            assertThat(output.receive(0)).isNull();
            assertThat(store.getMessageGroup(key).size()).isEqualTo(2);
            assertThat(store.getMessageGroup(key).isComplete()).isFalse();
        }

        try (ConfigurableApplicationContext second = open("never")) {
            OrderGateway gateway = second.getBean(OrderGateway.class);
            JdbcMessageStore store = second.getBean(JdbcMessageStore.class);
            QueueChannel output = second.getBean(
                    "completedOrders", QueueChannel.class);
            QueueChannel discarded = second.getBean(
                    "discardedParts", QueueChannel.class);

            assertThat(store.getMessageGroup(key).size()).isEqualTo(2);

            gateway.accept(new OrderPart("ORD-101", SHIPMENT, "SHIP-101"));

            Message<?> message = output.receive(1_000);
            assertThat(message).isNotNull();
            OrderSummary summary = (OrderSummary) message.getPayload();

            assertThat(summary.orderId()).isEqualTo("ORD-101");
            assertThat(summary.references())
                    .containsEntry(PAYMENT, "PAY-101")
                    .containsEntry(STOCK, "STOCK-101")
                    .containsEntry(SHIPMENT, "SHIP-101")
                    .hasSize(3);

            assertThat(output.receive(0)).isNull();
            assertThat(store.getMessageGroup(key).size()).isZero();
            assertThat(store.getMessageGroup(key).isComplete()).isTrue();

            gateway.accept(new OrderPart("ORD-101", PAYMENT, "PAY-101"));

            assertThat(discarded.receive(1_000)).isNotNull();
            assertThat(output.receive(0)).isNull();
        }
    }

    @Test
    void duplicateKindDoesNotSatisfyMissingConfirmation() {
        try (ConfigurableApplicationContext context = open("always")) {
            OrderGateway gateway = context.getBean(OrderGateway.class);
            JdbcMessageStore store = context.getBean(JdbcMessageStore.class);
            QueueChannel output = context.getBean(
                    "completedOrders", QueueChannel.class);

            gateway.accept(new OrderPart("ORD-202", PAYMENT, "PAY-202"));
            gateway.accept(new OrderPart("ORD-202", PAYMENT, "PAY-202"));
            gateway.accept(new OrderPart("ORD-202", STOCK, "STOCK-202"));

            assertThat(output.receive(0)).isNull();
            assertThat(store.getMessageGroup(
                    OrderFlowConfiguration.groupId("ORD-202")).size())
                    .isEqualTo(3);

            gateway.accept(new OrderPart("ORD-202", SHIPMENT, "SHIP-202"));

            Message<?> message = output.receive(1_000);
            assertThat(message).isNotNull();
            OrderSummary summary = (OrderSummary) message.getPayload();

            assertThat(summary.references()).hasSize(3);
            assertThat(output.receive(0)).isNull();
        }
    }

    @Test
    void expiryDiscardsIncompleteGroupWithoutProducingSummary() {
        try (ConfigurableApplicationContext context = open("always")) {
            OrderGateway gateway = context.getBean(OrderGateway.class);
            JdbcMessageStore store = context.getBean(JdbcMessageStore.class);
            QueueChannel output = context.getBean(
                    "completedOrders", QueueChannel.class);
            QueueChannel discarded = context.getBean(
                    "discardedParts", QueueChannel.class);

            gateway.accept(new OrderPart("ORD-303", PAYMENT, "PAY-303"));

            MessageGroupStoreReaper reaper = new MessageGroupStoreReaper(store);
            reaper.setTimeout(0);
            reaper.setExpireOnDestroy(false);
            reaper.start();

            try {
                TransactionTemplate transaction = new TransactionTemplate(
                        context.getBean(PlatformTransactionManager.class));
                transaction.executeWithoutResult(status -> reaper.run());
            }
            finally {
                reaper.stop();
            }

            assertThat(output.receive(0)).isNull();
            assertThat(discarded.receive(1_000)).isNotNull();
            assertThat(store.getMessageGroup(
                    OrderFlowConfiguration.groupId("ORD-303")).size())
                    .isZero();
            assertThat(store.getMessageGroup(
                    OrderFlowConfiguration.groupId("ORD-303")).isComplete())
                    .isTrue();
        }
    }
}
~~~

Người học chạy:

~~~shell
mvn test
~~~

Mỗi phương thức kiểm thử có thư mục tạm riêng. Hai context trong kiểm thử thứ nhất dùng chung file database, nhưng không dùng chung bean store, channel hoặc bộ nhớ của aggregator. Các tham số truyền vào `run(...)` ghi đè cấu hình mặc định để kiểm soát việc tạo schema.

Kiểm thử thứ hai gọi gateway hai lần với cùng dữ liệu. Mỗi lần gọi tạo một thông điệp mới; đây là tình huống gửi lặp về nghiệp vụ, không phải tái sử dụng cùng một message ID.

Kiểm thử thứ ba đặt timeout bằng 0 để kích hoạt expiry ngay, không phải ngủ chờ hết thời gian thực. `MessageGroupStoreReaper` tạo thủ công phải được `start()` trước khi gọi `run()`. [Mã nguồn reaper 6.5.0](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/store/MessageGroupStoreReaper.java).

### Phạm vi chứng minh của kiểm thử

Kiểm thử restart trên chứng minh một nhóm chưa hoàn tất được đọc lại sau khi thay toàn bộ Spring context. Nó chưa chứng minh việc khôi phục sau sự cố giữa hai câu lệnh SQL, hai JVM xử lý đồng thời, hay giao dịch xuyên qua broker và HTTP.

Để thử restart tiến trình thật, dùng một chương trình gửi hai xác nhận vào database file, kết thúc JVM, rồi chạy chương trình khác với schema initialization tắt để gửi xác nhận cuối. Giữ nguyên package/class payload, JDBC URL, region và correlation strategy.

Không dùng `jdbc:h2:mem:...` nếu muốn kết quả thử nghiệm tồn tại sau khi JVM kết thúc. H2 file trong lab cũng cần được đóng context tuần tự; phần chạy nhiều instance nên dùng một database server phù hợp.

## 8. Dọn nhóm quá hạn sau restart

Có hai yêu cầu thời gian khác nhau:

- **Thời gian chờ dữ liệu:** một nhóm thiếu xác nhận không được tồn tại vô hạn.
- **Thời gian giữ dấu complete:** một nhóm đã hoàn tất vẫn cần chặn các bản tin gửi lại trong một khoảng thời gian.

Trong cấu hình lab:

| Tham số | Chính sách |
| --- | --- |
| `store.setTimeoutOnIdle(false)` | Tuổi nhóm tính từ khi tạo nhóm |
| Reaper timeout | 60 giây cho nhóm được xem xét expiry |
| Chu kỳ reaper | 5 giây |
| `minimumTimeoutForEmptyGroups` | Giữ dấu nhóm rỗng ít nhất 5 phút từ lần cập nhật |
| `sendPartialResultOnExpiry(false)` | Nhóm thiếu dữ liệu không được tạo summary thành công |
| `expireGroupsUponTimeout(false)` | Giữ dấu complete sau khi xử lý timeout |

Reaper kiểm tra dữ liệu đang lưu nên có thể tìm lại nhóm còn sót từ lần chạy trước. Một lịch hẹn trong bộ nhớ cho từng nhóm không tự trở thành lịch hẹn bền vững chỉ vì thông điệp đã được lưu JDBC.

Nếu bật `setTimeoutOnIdle(true)`, thời hạn dựa vào lần cập nhật gần nhất. Nguồn liên tục gửi lặp có thể làm nhóm tiếp tục được gia hạn. Chọn quy tắc theo SLA nghiệp vụ và dùng cùng một quy tắc khi kiểm thử. [Cách tính timeout trong group store](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/store/AbstractMessageGroupStore.java).

### Cấu hình lịch quét

Thêm file sau khi muốn chạy expiry tự động.

`src/main/java/vn/example/messagestore/ExpiryConfiguration.java`:

~~~java
package vn.example.messagestore;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupStoreReaper;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
@EnableScheduling
@ConditionalOnProperty(name = "lab.expiry.enabled", havingValue = "true")
public class ExpiryConfiguration {

    @Bean
    public MessageGroupStoreReaper orderGroupReaper(
            JdbcMessageStore orderGroupStore) {
        MessageGroupStoreReaper reaper =
                new MessageGroupStoreReaper(orderGroupStore);
        reaper.setTimeout(60_000);
        reaper.setExpireOnDestroy(false);
        return reaper;
    }

    @Bean
    public ExpiryTask expiryTask(
            MessageGroupStoreReaper orderGroupReaper,
            PlatformTransactionManager transactionManager) {
        return new ExpiryTask(
                orderGroupReaper,
                new TransactionTemplate(transactionManager));
    }

    public static class ExpiryTask {

        private final MessageGroupStoreReaper reaper;
        private final TransactionTemplate transaction;

        public ExpiryTask(MessageGroupStoreReaper reaper,
                          TransactionTemplate transaction) {
            this.reaper = reaper;
            this.transaction = transaction;
        }

        @Scheduled(fixedDelay = 5_000, initialDelay = 5_000)
        public void expire() {
            transaction.executeWithoutResult(status -> reaper.run());
        }
    }
}
~~~

Bật bằng `lab.expiry.enabled=true`. Các kiểm thử ở phần trước luôn truyền `false` để lịch nền không can thiệp vào dữ liệu đang kiểm tra.

Với timeout 60 giây và quét mỗi 5 giây, nhóm được xử lý ở một lần quét sau khi đủ tuổi; thời điểm còn phụ thuộc tải scheduler, thời gian transaction và thời gian khóa. Không diễn giải con số này thành một cam kết chính xác đến mili giây.

`setExpireOnDestroy(false)` giữ dữ liệu khi reaper bị dừng. Việc tắt ứng dụng trong bài kiểm thử khôi phục không được biến thành yêu cầu xả toàn bộ nhóm.

Transaction của `ExpiryTask` bao lấy lần quét trong lab. Khi số nhóm lớn, cần đánh giá thời gian giữ transaction, chia tải quét và chính sách xử lý từng nhóm. Phần ghi vào `discardedParts` vẫn là thao tác với queue bộ nhớ, nên không có rollback JDBC tương ứng.

Một lỗi từ phương thức `@Scheduled` không tự bảo đảm trở thành `ErrorMessage` trên `errorChannel` của luồng Integration. Cần cấu hình cơ chế báo lỗi của scheduler khi yêu cầu vận hành cần nhận lỗi qua một error flow.

### Dấu complete có thời hạn

Giữ metadata complete trong năm phút chỉ bảo vệ trong cửa sổ đó. Khi metadata đã bị xóa, một sự kiện cũ có thể mở lại nhóm. Nếu nguồn gửi lại sau nhiều ngày, dùng một cơ chế nhận diện kết quả nghiệp vụ đã xử lý với thời hạn phù hợp.

Bản ghi `orderId` duy nhất trong bảng kết quả, hoặc khóa idempotency có namespace và retention rõ ràng, thường là nơi thích hợp để bảo vệ tác động nghiệp vụ dài hạn. Không giữ vô hạn mọi nhóm chỉ để thay thế quy tắc này.

## 9. Transaction: state bền vững cần ranh giới rõ ràng

Cấu hình aggregator ở phần 6 chưa tự mở một transaction bao quanh mỗi lời gọi gateway. Nhiều thao tác JDBC có thể đã commit riêng nếu không có transaction bên ngoài.

Để xử lý một thông điệp đầu vào trong transaction JDBC, có thể đặt ranh giới tại application service gọi gateway:

~~~java
TransactionTemplate transaction = new TransactionTemplate(transactionManager);

transaction.executeWithoutResult(status ->
        gateway.accept(new OrderPart("ORD-404", PAYMENT, "PAY-404")));
~~~

Đoạn này giả định `transactionManager` quản lý đúng DataSource của `JdbcMessageStore`. Vì đầu vào dùng `DirectChannel`, phần xử lý đồng bộ của aggregator chạy trên thread gọi và tham gia transaction đó. Chuyển sang một executor hoặc ranh giới bất đồng bộ đòi hỏi xác định lại transaction tại consumer. [Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

Một kiểm thử rollback có ý nghĩa là gây lỗi sau khi thêm **một phần** của nhóm:

~~~java
String key = OrderFlowConfiguration.groupId("ORD-ROLLBACK");
int groupsBefore = store.getMessageGroupCount();

assertThrows(IllegalStateException.class, () ->
        transaction.executeWithoutResult(status -> {
            gateway.accept(new OrderPart(
                    "ORD-ROLLBACK", PAYMENT, "PAY-ROLLBACK"));
            throw new IllegalStateException("Lỗi sau khi thêm thông điệp");
        }));

assertThat(store.getMessageGroup(key).size()).isZero();
assertThat(store.getMessageGroupCount()).isEqualTo(groupsBefore);
~~~

Đoạn kiểm thử bổ sung cần import static `org.junit.jupiter.api.Assertions.assertThrows`; `store`, `gateway` và transaction được lấy từ context của test. Nhóm chưa đủ điều kiện release nên kiểm thử này tập trung vào rollback state, chưa phát sinh output.

### Khoảng trống giữa lưu state và tác động bên ngoài

Xét chuỗi:

~~~text
Nhận xác nhận cuối
    -> aggregator phát kết quả
    -> gọi API giao hàng
    -> cập nhật nhóm thành complete
~~~

Nếu API đã thành công nhưng transaction JDBC rollback, lần gửi lại có thể gọi API lần nữa. Nếu nhóm đã được ghi complete nhưng output chỉ còn trong bộ nhớ lúc JVM dừng, tác động cuối có thể chưa được thực hiện.

Một thiết kế mở rộng cho bài này:

1. Bao lấy xử lý đầu vào bằng transaction của DataSource.
2. Thay output queue bộ nhớ bằng handler ghi một outbox record trên cùng DataSource và cùng transaction.
3. Đặt unique constraint cho khóa tác động, chẳng hạn `order-completed:<orderId>`.
4. Worker đọc outbox, gửi ra hệ thống ngoài và ghi nhận tiến độ với chính sách retry.
5. Consumer hoặc API nhận hỗ trợ idempotency vì gửi lại vẫn có thể xảy ra.

Đây là thiết kế đề xuất cho bài toán đơn hàng. Độ bền của `MessageStore` là một phần của thiết kế; bảo đảm chỉ thực hiện một tác động nghiệp vụ còn phụ thuộc điểm commit, cách giao tiếp và cơ chế nhận diện lặp của bên nhận.

## 10. Mở rộng: lưu cả hàng đợi đầu vào

Store của aggregator chỉ giữ những thông điệp **đã đến aggregator**. Nếu có một `QueueChannel` bộ nhớ phía trước, thông điệp còn chờ trong queue đó vẫn có thể mất.

Có thể bổ sung queue JDBC cho bài tập mở rộng. Các bean sau đặt trong một lớp `@Configuration`; cần các import `Bean`, `DataSource`, `QueueChannel` và `DependsOnDatabaseInitialization` như phần trước, cùng:

~~~java
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.H2ChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
~~~

~~~java
@Bean
@DependsOnDatabaseInitialization
public JdbcChannelMessageStore inboxStore(DataSource dataSource) {
    JdbcChannelMessageStore store = new JdbcChannelMessageStore(dataSource);
    store.setRegion("orders-inbox-v1");
    store.setChannelMessageStoreQueryProvider(
            new H2ChannelMessageStoreQueryProvider());
    return store;
}

@Bean
public QueueChannel durableOrderInbox(JdbcChannelMessageStore inboxStore) {
    return new QueueChannel(
            new MessageGroupQueue(inboxStore, "order-inbox-v1"));
}
~~~

Queue cần consumer có poller. Với các import bổ sung `IntegrationFlow`, `Pollers` và `PlatformTransactionManager`:

~~~java
@Bean
public IntegrationFlow consumeDurableInbox(
        PlatformTransactionManager transactionManager) {
    return IntegrationFlow.from("durableOrderInbox")
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(250)
                            .maxMessagesPerPoll(1)
                            .transactional(transactionManager)))
            .channel("orderParts")
            .get();
}
~~~

Đổi `defaultRequestChannel` của gateway thành `durableOrderInbox` khi thực hiện biến thể này. Nếu giữ nguyên `orderParts`, gateway vẫn đi thẳng đến aggregator và không kiểm thử được queue mới.

Với channel store JDBC và transaction phù hợp, thao tác lấy khỏi queue cùng xử lý đồng bộ phía sau nằm trong một transaction; khi lỗi làm rollback, việc lấy thông điệp cũng được rollback. Một queue chỉ lưu bền nhưng bị poll ngoài transaction chưa cung cấp bảo đảm đó. [Cấu hình persistent channel](https://docs.spring.io/spring-integration/reference/6.5/channel/configuration.html).

Bài mở rộng cần thêm hai thử nghiệm:

- Tắt consumer, gửi thông điệp vào queue, mở lại ứng dụng và kiểm tra thông điệp vẫn được lấy.
- Gây lỗi ở consumer sau khi poll, kiểm tra thông điệp có thể được nhận lại khi rollback và không làm sai state của nhóm.

Query provider phải theo database đích. Đồng thời kiểm tra schema của channel store trong đúng phiên bản; không dùng cấu hình H2 nguyên trạng cho PostgreSQL.

## 11. Khi có nhiều instance cùng xử lý

Lưu state chung và khóa thao tác trên state giải quyết hai vấn đề khác nhau. Hai instance có thể cùng đọc một nhóm chưa hoàn tất, cùng thêm dữ liệu và cùng quyết định release nếu chỉ dùng khóa cục bộ.

Với hệ thống dùng chung JDBC store, có thể dùng `JdbcLockRegistry` dựa trên `DefaultLockRepository` để điều phối khóa theo group giữa các instance. [JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/6.5/jdbc/lock-registry.html).

Khi mở rộng cấu hình:

- Cấu hình một lock registry phân tán phù hợp cho aggregator qua `.lockRegistry(orderLocks)`.
- Với abstraction group store ở nhánh 6.5, xem xét cấu hình cùng cơ chế khóa cho các thao tác metadata qua `store.setLockRegistry(orderLocks)`.
- Giữ nhất quán database, table prefix, region của store, namespace correlation và cấu hình khóa giữa các instance cùng sở hữu luồng.
- Đảm bảo thời hạn lease của khóa phù hợp thời gian xử lý; kiểm tra cả trường hợp một instance mất kết nối hoặc dừng khi đang giữ khóa.
- Dùng kết quả nghiệp vụ có khóa duy nhất để kiểm soát tác động lặp sau retry.

Khóa không thay thế transaction: khóa giới hạn ai được thao tác đồng thời, còn transaction xác định những thay đổi nào commit cùng nhau.

Không chia sẻ tùy tiện một bean `MessageGroupStore` giữa nhiều aggregator có lifecycle khác nhau. Nên tách bean và region theo luồng, rồi lập lịch expiry đúng store thuộc luồng đó. Như vậy một reaper không vô tình áp dụng chính sách timeout của luồng này lên dữ liệu luồng khác.

Trong kiểm thử nhiều instance, dùng database server, gửi đồng thời nhiều sự kiện cùng key và đo số kết quả nghiệp vụ đã commit. Chỉ đếm log hoặc kiểm tra JVM không ném exception chưa đủ để kết luận đúng.

## 12. Payload, header và tương thích dữ liệu cũ

State được lưu hôm nay có thể phải được đọc bởi bản phát hành tuần sau. Hãy xác định trước:

| Thành phần | Quy tắc đề xuất cho bài toán |
| --- | --- |
| Payload | DTO nhỏ, chỉ chứa dữ liệu cần để hoàn tất nhóm |
| Header nghiệp vụ | ID, tenant, trace ID và giá trị có thể lưu ổn định |
| Class payload | Giữ khả năng đọc dữ liệu cũ hoặc có migration |
| Region/key | Thay đổi có kế hoạch, không tự thêm phiên bản ngẫu nhiên |
| Dữ liệu nhạy cảm | Lưu tối thiểu theo nhu cầu xử lý và retention |
| Kết quả hoàn tất | Có khóa nghiệp vụ riêng để chống lặp dài hạn |

Với serializer mặc định của JDBC store, khả năng lưu payload và khả năng giữ nguyên mọi header cần được đánh giá riêng. Một header trỏ tới channel hoặc tài nguyên đang sống trong JVM không phải là một địa chỉ bền vững qua restart.

Cơ chế đổi `replyChannel` thành tên qua registry có ích trong một số luồng, nhưng một temporary channel được đăng ký trong bộ nhớ không tự khôi phục ở JVM khác. Bài này dùng gateway một chiều và output channel cố định để không phụ thuộc một người gọi đang chờ.

Khi dùng Java serialization, `serialVersionUID` là một phần của hợp đồng tương thích; giữ cùng giá trị không bảo đảm mọi thay đổi cấu trúc hoặc ý nghĩa dữ liệu đều an toàn. Thử đọc dữ liệu tạo bởi bản cũ là một kiểm thử phát hành cần thiết.

Nếu chọn serializer khác, phải cấu hình cả chiều ghi và chiều đọc, rồi kiểm thử lại thông điệp thật sau restart. Việc đổi định dạng lưu mà không xử lý các bản ghi đang tồn tại sẽ khiến các nhóm cũ không thể tiếp tục.

## 13. Quan sát state và chẩn đoán

Trong lab có thể đọc trạng thái một nhóm bằng API:

~~~java
String key = OrderFlowConfiguration.groupId("ORD-101");

MessageGroup group = store.getMessageGroup(key);
System.out.println("size=" + group.size());
System.out.println("complete=" + group.isComplete());
System.out.println("created=" + group.getTimestamp());
System.out.println("lastModified=" + group.getLastModified());
~~~

Các biến `store` và `group` chỉ được dùng để quan sát tại thời điểm kiểm tra. Không sửa trực tiếp tập thông điệp của nhóm bên ngoài aggregator đang hoạt động.

Để xem số liệu tổng quan trong database H2:

~~~sql
SELECT REGION, COMPLETE, COUNT(*) AS GROUP_COUNT
FROM INT_MESSAGE_GROUP
WHERE REGION = 'orders-assembly-v1'
GROUP BY REGION, COMPLETE;

SELECT REGION, COUNT(*) AS STORED_MESSAGE_COUNT
FROM INT_MESSAGE
WHERE REGION = 'orders-assembly-v1'
GROUP BY REGION;

SELECT REGION, COUNT(*) AS MEMBERSHIP_COUNT
FROM INT_GROUP_TO_MESSAGE
WHERE REGION = 'orders-assembly-v1'
GROUP BY REGION;
~~~

`GROUP_KEY` trong bảng là khóa biểu diễn nội bộ của store; không giả định nó chính là chuỗi `order-assembly:v1:ORD-101` để viết câu SQL nghiệp vụ. Khi kiểm tra một nhóm cụ thể, ưu tiên API với correlation key gốc.

Với store lazy loading, việc duyệt toàn bộ `getMessages()` cho nhiều nhóm có thể gây thêm truy vấn và giải tuần tự payload. Dùng số đếm và metadata cho số liệu thường xuyên; chỉ đọc chi tiết nhóm khi cần điều tra.

Các số liệu nên theo dõi cho bài toán này:

- Số nhóm đang chờ và tuổi của nhóm lâu nhất.
- Số thông điệp/bản ghi và dung lượng dữ liệu lưu.
- Số nhóm expiry, sự kiện đến muộn và nhóm có reference xung đột.
- Thời gian thêm thông điệp, release và chờ khóa.
- Lỗi serialization/deserialization, lỗi SQL, rollback và retry.
- Số tác động nghiệp vụ đã commit và số lần bị chặn bởi idempotency.

### Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Restart xong không thấy nhóm cũ | Đổi database, region, key hoặc còn dùng store bộ nhớ | So sánh cấu hình thực tế và đọc nhóm trước khi gửi thêm |
| Ứng dụng báo thiếu bảng | Schema chưa tạo, sai DataSource hoặc prefix | Kiểm tra migration và thứ tự khởi tạo |
| Chạy lần hai báo bảng đã tồn tại | Chạy lại script tạo schema | Tắt khởi tạo ở lần mở lại database |
| Có ba bản tin nhưng kết quả sai | Chỉ đếm số message, không kiểm tra loại xác nhận | Đổi release strategy theo tập loại và hợp đồng nghiệp vụ |
| Nhóm không bao giờ release | Thiếu loại xác nhận hoặc có reference xung đột | Quan sát state, xử lý nguồn gửi và chính sách timeout |
| Store tăng mãi | Không có expiry, dấu complete giữ quá lâu hoặc nguồn gửi lặp mạnh | Định nghĩa retention, lập lịch quét và giới hạn tải |
| Có kết quả trước restart nhưng mất sau đó | Output channel còn ở bộ nhớ | Lưu output bền vững hoặc ghi outbox |
| Lỗi đọc payload cũ | DTO/serializer không tương thích | Thử đọc dữ liệu bản cũ và triển khai migration |
| Hai instance tạo hai tác động | Thiếu khóa hoặc idempotency, ranh giới commit chưa đúng | Kiểm thử đồng thời và bảo vệ kết quả bằng khóa nghiệp vụ |

## 14. Bài tập nâng cao và tiêu chí nghiệm thu

### 14.1. Những tình huống cần bổ sung

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Đảo thứ tự ba xác nhận | Vẫn tạo một summary đủ dữ liệu |
| Hai đơn hàng xen kẽ | Hai nhóm độc lập, không trộn reference |
| Gửi lặp `PAYMENT` nhiều lần | Không hoàn tất trước khi có `SHIPMENT` |
| Hai `PAYMENT` khác reference | Nhóm chưa release; có bằng chứng xung đột để xử lý |
| `orderId` rỗng | Vào `invalidParts`, không tạo nhóm hợp lệ |
| Restart sau hai xác nhận | Đọc lại được hai xác nhận rồi hoàn tất khi có bản tin thứ ba |
| Restart khi nhóm quá hạn | Reaper xử lý nhóm cũ sau khi bật lịch quét |
| Bản tin muộn khi dấu complete còn | Vào discard, không tạo summary mới |
| Bản tin cũ sau khi dấu complete bị dọn | Có thể tạo nhóm mới; idempotency nghiệp vụ vẫn bảo vệ tác động |
| Lỗi sau thêm một phần trong transaction | Không giữ phần thêm đã rollback |
| Hai instance cùng key | Kết quả đã commit tuân thủ quy tắc duy nhất của nghiệp vụ |

### 14.2. Yêu cầu triển khai mở rộng

1. Thêm `eventId` và thiết kế bước nhận diện gửi lặp trước aggregator; xác định rõ lúc ghi nhận ID và lúc commit state để tránh đánh dấu đã nhận nhưng chưa lưu được dữ liệu.
2. Tách `discardedParts` thành nơi xử lý timeout và nơi xử lý bản tin muộn nếu đội vận hành cần hai chính sách khác nhau.
3. Lưu các trường cần điều tra của nhóm bị timeout trước khi dọn thành viên.
4. Thay output bộ nhớ bằng outbox, gây lỗi tại các điểm commit và chứng minh retry không tạo tác động nghiệp vụ sai.
5. Thực hiện thử nghiệm tương thích: tạo nhóm bằng DTO phiên bản cũ, đọc bằng ứng dụng phiên bản mới.
6. Đo ảnh hưởng của một đơn có hàng nghìn bản tin gửi lặp; đề xuất giới hạn kích thước nhóm, giới hạn đầu vào và cơ chế loại lặp phù hợp.

### 14.3. Tiêu chí nghiệm thu

Bài thực hành đạt yêu cầu khi người học cung cấp được:

- Luồng Java DSL chỉ rõ store nào quản lý state của aggregator.
- Dữ liệu chứng minh nhóm chưa hoàn tất tồn tại qua việc đóng và mở lại context.
- Kiểm thử cho thấy bản tin lặp không thay thế một xác nhận còn thiếu.
- Chính sách timeout và thời gian giữ dấu complete với đơn vị thời gian rõ ràng.
- Kết quả phân biệt thông điệp không hợp lệ, nhóm quá hạn và bản tin đến muộn.
- Mô tả ranh giới transaction cùng cách xử lý output nếu tiến trình dừng.
- Phương án kiểm soát đồng thời và idempotency khi có nhiều instance.

Những kết quả này đánh giá đúng mục tiêu lưu state: aggregator có thể tiếp tục từ dữ liệu đã lưu, còn hành vi sau release được bảo vệ theo hợp đồng nghiệp vụ và ranh giới lưu trữ đã thiết kế.
