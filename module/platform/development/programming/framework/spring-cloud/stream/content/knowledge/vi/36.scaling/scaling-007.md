# ProvisioningProvider và vòng đời tài nguyên của custom binder

Spring Cloud Stream cho phép ứng dụng xử lý sự kiện qua các hàm **Supplier**, **Function** và **Consumer**, trong khi binder chịu trách nhiệm kết nối các binding tới Kafka, RabbitMQ, Pulsar hoặc middleware khác. Khi một middleware chưa có binder phù hợp, có thể xây dựng **custom binder** dựa trên Binder SPI. Thành phần quan trọng đầu tiên của custom binder là **ProvisioningProvider**: nó biến tên destination logic trong cấu hình ứng dụng thành tham chiếu tới tài nguyên vật lý có thể gửi hoặc nhận message.

Ví dụ ứng dụng cấu hình destination là orders.created, nhưng middleware nội bộ cần tạo stream events/orders.created, subscription fulfillment và bốn shard dữ liệu. Custom binder phải quyết định khi nào tạo stream, khi nào xác minh nó tồn tại, cách ánh xạ group sang subscription, làm gì nếu nhiều instance cùng khởi động và tài nguyên nào được phép xóa khi ứng dụng dừng.

Bài học này tập trung vào **provisioning, quản lý quyền sở hữu tài nguyên và mở rộng nhiều instance**. Mã nguồn minh họa dùng một middleware giả định tên ExampleBus để làm rõ hợp đồng SPI. Các lời gọi Admin API là giao diện minh họa, **không phải class có sẵn trong Spring Cloud Stream**; khi làm với middleware thật, cần thay chúng bằng SDK/Admin Client và điều chỉnh theo phiên bản thư viện.

## 1. Tại sao custom binder cần ProvisioningProvider?

Spring Cloud Stream tách ba khái niệm:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Binding | Đầu vào/đầu ra của function trong ứng dụng | processOrder-in-0 |
| Destination logic | Tên người triển khai khai báo | orders.created |
| Tài nguyên vật lý | Topic, exchange, queue, stream hoặc subscription thật | tenant-a/orders.created; orders.created.fulfillment |

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: fulfillment
          binder: exampleBus
~~~

Các giá trị này chưa nói middleware có cần tạo queue hay không, tên queue chứa group thế nào hoặc tài nguyên có phải durable không. Đó là trách nhiệm của provisioning layer.

**ProvisioningProvider không xử lý payload nghiệp vụ.** Nó chuẩn bị hoặc tìm kiếm tài nguyên và trả về một đối tượng destination mà phần endpoint có thể sử dụng. Logic gửi record thuộc producer handler; logic nhận record thuộc consumer endpoint.

Nếu middleware đã có binder chính thức, nên dùng binder đó trước khi tự phát triển. Custom binder phù hợp khi cần kết nối middleware riêng, giao thức đặc biệt hoặc đặc tính tài nguyên không được binder hiện có hỗ trợ.

## 2. Vị trí của ProvisioningProvider trong Binder SPI

Một custom binder kiểu message-channel thường có các thành phần:

- **ProvisioningProvider**: tạo/kiểm tra destination cho producer và consumer.
- **Binder**: hiện thực contract liên kết input/output của Spring Cloud Stream tới middleware.
- **MessageHandler**: gửi dữ liệu từ output channel ra middleware.
- **MessageProducer**: nhận message từ middleware và đẩy vào input channel.
- **Binder configuration**: khởi tạo bean, connection/admin client và cấu hình binder.
- **META-INF/spring.binders**: cho framework biết tên binder và configuration class.

Luồng khởi tạo có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[application.yml] --> B[BindingService]
    B --> C{Chọn Binder}
    C --> D[bindProducer hoặc bindConsumer]
    D --> E[ProvisioningProvider]
    E --> F[Kiểm tra / tạo tài nguyên broker]
    F --> G[ProducerDestination hoặc ConsumerDestination]
    G --> H[createProducerMessageHandler / createConsumerEndpoint]
    H --> I[Start endpoint / Binding]
    I --> J[Trao đổi message]
~~~

**Thứ tự quan trọng:** endpoint chỉ nên bắt đầu gửi/nhận khi tài nguyên cần thiết đã có hoặc đã được xác minh. Nếu provisioning lỗi, không được báo binding khởi tạo thành công rồi âm thầm đánh rơi message.

Custom binder không nhất thiết phải dùng AbstractMessageChannelBinder nếu triển khai một dạng binder khác. Nhưng Spring Cloud Stream cung cấp lớp nền này để tái sử dụng lifecycle và tích hợp Spring Integration khi binding target là MessageChannel.

## 3. Hợp đồng ProvisioningProvider

Interface thuộc package:

~~~java
org.springframework.cloud.stream.provisioning.ProvisioningProvider
~~~

Nó có hai type parameter: một kiểu consumer properties và một kiểu producer properties. Với nhu cầu thông thường, có thể dùng các kiểu chung:

~~~java
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ProvisioningProvider;

public final class ExampleProvisioner
        implements ProvisioningProvider<
            ConsumerProperties, ProducerProperties> {

    @Override
    public ProducerDestination provisionProducerDestination(
            String name,
            ProducerProperties properties) {
        throw new UnsupportedOperationException("Not implemented");
    }

    @Override
    public ConsumerDestination provisionConsumerDestination(
            String name,
            String group,
            ConsumerProperties properties) {
        throw new UnsupportedOperationException("Not implemented");
    }
}
~~~

Hai method có vai trò khác nhau:

| Method | Tham số quan trọng | Kết quả |
|---|---|---|
| provisionProducerDestination | name, ProducerProperties | ProducerDestination |
| provisionConsumerDestination | name, group, ConsumerProperties | ConsumerDestination |

- **name** là tên destination logic do binding khai báo, không nhất thiết là tên tài nguyên vật lý.
- **group** là consumer group logic. Middleware có thể dùng nó tạo subscription, durable queue hoặc một dạng nhóm nhận khác.
- **properties** chứa cấu hình chung như partitionCount, requiredGroups, concurrency, partitioned, instanceCount và instanceIndex.
- **destination trả về** mô tả tài nguyên để phần producer/consumer endpoint kết nối.

Khi middleware báo lỗi không thể provision, provider nên ném **ProvisioningException** có ngữ cảnh nhưng không chứa password, token hoặc nội dung message. Không trả về destination giả nếu broker chưa sẵn sàng và nghiệp vụ yêu cầu tài nguyên phải tồn tại trước khi binding hoạt động.

## 4. ProducerDestination và ConsumerDestination

Hai interface destination cung cấp tham chiếu tới tên tài nguyên vật lý:

~~~java
public interface ConsumerDestination {
    String getName();
}

public interface ProducerDestination {
    String getName();
    String getNameForPartition(int partition);
}
~~~

ProducerDestination có thêm **getNameForPartition(int)** vì một số middleware biểu diễn mỗi partition bằng một destination vật lý khác. Ví dụ:

~~~text
orders.created
  -> events/orders.created-0
  -> events/orders.created-1
  -> events/orders.created-2
~~~

Với middleware có partition native, mọi record có thể gửi tới cùng một topic/stream name và truyền partition như metadata của transport. Khi đó getNameForPartition có thể trả về cùng tên, nếu producer handler thực sự truyền partition ID cho client SDK.

**Không nhầm việc trả tên giống nhau với việc hỗ trợ partition.** Nếu middleware không có partition native mà getNameForPartition luôn trả về tên chung, binder có thể gửi mọi record vào cùng tài nguyên và làm mất ý nghĩa phân vùng.

ConsumerDestination thường chỉ cung cấp tên tài nguyên consumer nhận. Cách phân partition hoặc subscription group phụ thuộc thiết kế của endpoint và middleware.

## 5. Thiết kế mapping tên logic sang tên vật lý

Giả sử ExampleBus phân biệt namespace và stream:

~~~text
Destination logic: orders.created
Namespace:        tenant-a
Stream vật lý:    tenant-a/events/orders.created
Group:            fulfillment
Subscription:     tenant-a/events/orders.created/fulfillment
~~~

Quy tắc ánh xạ nên:

1. **Deterministic**: cùng input và configuration luôn cho cùng tên.
2. **Stable**: không đổi tên khi Pod restart hoặc scale ngang.
3. **Collision-safe**: hai tenant hoặc hai môi trường không vô tình trỏ chung.
4. **Valid**: tên tuân thủ giới hạn ký tự, độ dài và quy tắc middleware.
5. **Observable**: có thể truy vết từ binding đến tài nguyên vật lý.
6. **Secure**: không cho phép tên tùy ý thoát khỏi namespace được cấp quyền.

Ví dụ một hàm chuyển tên minh họa:

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public final class DestinationNames {

    private static final Pattern VALID =
        Pattern.compile("[a-zA-Z0-9._-]{1,128}");

    private DestinationNames() {}

    public static String stream(String namespace, String logicalName) {
        requireValid(namespace);
        requireValid(logicalName);

        return namespace + "/events/" + logicalName;
    }

    public static String subscription(String stream, String group) {
        requireValid(group);
        return stream + "/" + group;
    }

    private static void requireValid(String value) {
        if (value == null || !VALID.matcher(value).matches()) {
            throw new IllegalArgumentException(
                "Invalid destination identifier"
            );
        }
    }
}
~~~

Đây là quy tắc tên minh họa, không phải quy tắc chính thức của Kafka, RabbitMQ hoặc Pulsar. Với broker thật, cần theo naming rules chính thức của SDK và hạ tầng. Không âm thầm trim hoặc thay thế ký tự nếu có nguy cơ làm hai tên hợp lệ khác nhau cùng ánh xạ vào một tài nguyên.

## 6. Ví dụ interface cho Admin API của middleware

Để tách phần SPI khỏi middleware SDK, định nghĩa một lớp adapter/admin interface do **chính ứng dụng tự tạo**:

~~~java
public interface ExampleBusAdmin {

    void ensureStream(String physicalName, int partitions);

    // Chỉ xác minh/tạo khi thiếu; không thay partition của stream đã có.
    void ensureStreamForConsumer(String physicalName);

    void ensureDurableSubscription(
        String physicalStream,
        String group
    );

    void verifyStream(String physicalName, int expectedPartitions);

    void verifyStreamExists(String physicalName);

    void verifyDurableSubscription(
        String physicalStream,
        String group
    );
}
~~~

Các method này là **giả định minh họa**:

- ensureStream tạo resource nếu thiếu, hoặc xác minh resource hiện có tương thích.
- ensureStreamForConsumer chỉ bảo đảm stream tồn tại và giữ nguyên partition topology đã có.
- ensureDurableSubscription tạo subscription/group bền vững nếu thiếu.
- verifyStream kiểm tra tài nguyên do hạ tầng provision sẵn.
- verifyStreamExists chỉ kiểm tra tồn tại khi consumer không biết partition count từ broker.
- verifyDurableSubscription xác minh consumer group đã được provision trong chế độ chỉ đọc.
- Mỗi operation phải có timeout và chính sách lỗi rõ ràng trong SDK thật.

Không phải broker nào cũng có khái niệm stream và subscription như nhau. Kafka consumer group được quản lý thông qua coordinator và metadata; RabbitMQ thường cần exchange, queue và binding; Pulsar dùng topic và subscription. Adapter thật phải phản ánh đúng broker model.

## 7. Viết một ProvisioningProvider hoàn chỉnh ở mức SPI

Ví dụ sau ghép logic naming với Admin API. Nó chỉ hỗ trợ **named durable group**, không hỗ trợ anonymous consumer; giới hạn đó được cố ý nêu rõ để không vô tình giả định có queue tạm hoặc auto-delete.

~~~java
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ProvisioningException;
import org.springframework.cloud.stream.provisioning.ProvisioningProvider;

public final class ExampleBusProvisioningProvider
        implements ProvisioningProvider<
            ConsumerProperties, ProducerProperties> {

    private final ExampleBusAdmin admin;
    private final String namespace;
    private final boolean autoProvision;

    public ExampleBusProvisioningProvider(
            ExampleBusAdmin admin,
            String namespace,
            boolean autoProvision) {
        this.admin = admin;
        this.namespace = namespace;
        this.autoProvision = autoProvision;
    }

    @Override
    public ProducerDestination provisionProducerDestination(
            String name,
            ProducerProperties properties) {

        String physical = DestinationNames.stream(namespace, name);
        int partitions = properties.getPartitionCount();

        if (partitions < 1) {
            throw new ProvisioningException(
                "Producer partitionCount must be positive"
            );
        }

        try {
            String[] requiredGroups = properties.getRequiredGroups();
            if (autoProvision) {
                admin.ensureStream(physical, partitions);

                if (requiredGroups != null) {
                    for (String group : requiredGroups) {
                        admin.ensureDurableSubscription(physical, group);
                    }
                }
            }
            else {
                admin.verifyStream(physical, partitions);
                if (requiredGroups != null) {
                    for (String group : requiredGroups) {
                        admin.verifyDurableSubscription(physical, group);
                    }
                }
            }

            return new ExampleProducerDestination(physical, partitions);
        }
        catch (RuntimeException exception) {
            throw new ProvisioningException(
                "Producer destination provisioning failed: " + physical,
                exception
            );
        }
    }

    @Override
    public ConsumerDestination provisionConsumerDestination(
            String name,
            String group,
            ConsumerProperties properties) {

        if (group == null || group.isBlank()) {
            throw new ProvisioningException(
                "This binder requires a named durable group"
            );
        }

        String physical = DestinationNames.stream(namespace, name);

        try {
            if (autoProvision) {
                admin.ensureStreamForConsumer(physical);
                admin.ensureDurableSubscription(physical, group);
            }
            else {
                admin.verifyStreamExists(physical);
                admin.verifyDurableSubscription(physical, group);
            }

            return new ExampleConsumerDestination(physical, group);
        }
        catch (RuntimeException exception) {
            throw new ProvisioningException(
                "Consumer destination provisioning failed: " + physical,
                exception
            );
        }
    }
}
~~~

Các điểm thiết kế quan trọng:

- Provider không tự gửi hoặc nhận message.
- Admin API thực hiện thao tác idempotent: chạy lại vẫn cho kết quả tương thích.
- Không xóa stream hoặc subscription trong method provision.
- **autoProvision=false** dùng chế độ chỉ xác minh resource, phù hợp môi trường production khóa quyền tạo tài nguyên.
- **requiredGroups** giúp producer yêu cầu các group bền vững được chuẩn bị trước khi producer bắt đầu phát message.
- Consumer group được kiểm tra có tên vì ví dụ không hỗ trợ anonymous group.
- Lỗi admin được chuyển thành ProvisioningException, làm binding fail thay vì trả về một destination chưa có thật.

### Một ràng buộc cần sửa khi triển khai thực tế

Trong ví dụ, consumer dùng ensureStreamForConsumer thay vì tự áp đặt partitionCount bằng 1, bởi ConsumerProperties không tự xác định số partition vật lý của broker. Với middleware thật, **không được thu hẹp stream đang có bốn partition thành một partition**. Operation này phải phát hiện resource đã tồn tại và giữ nguyên partition count, hoặc truy vấn metadata trước khi tạo. Khi cần biết số partition, dùng broker metadata hoặc thuộc tính mở rộng do binder định nghĩa.

Nếu producer khởi tạo resource bốn partition trước, consumer chỉ cần xác minh stream tồn tại và tạo subscription thích hợp; không nên áp đặt partition count từ một giá trị mặc định không đáng tin.

## 8. Destination implementation trả về cho binder

Một triển khai tối giản cho môi trường native-partition:

~~~java
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;

public record ExampleProducerDestination(
    String physicalName,
    int partitionCount
) implements ProducerDestination {

    @Override
    public String getName() {
        return physicalName;
    }

    @Override
    public String getNameForPartition(int partition) {
        if (partition < 0 || partition >= partitionCount) {
            throw new IllegalArgumentException("Partition out of range");
        }

        // Middleware nhận partition bằng metadata riêng.
        return physicalName;
    }
}

public record ExampleConsumerDestination(
    String physicalName,
    String group
) implements ConsumerDestination {

    @Override
    public String getName() {
        return physicalName;
    }
}
~~~

Với ExampleBus, group được lưu trong ExampleConsumerDestination để endpoint đăng ký đúng durable subscription. **getName() không nhất thiết phải trả tên subscription**; nó trả tham chiếu destination mà binder cần. Endpoint sẽ dùng cả physicalName và group để tạo client, vì interface cung cấp thông tin tùy implementation.

Để giảm lỗi, destination objects nên immutable. Không nhét open connection, mutable admin state hoặc secret vào destination object nếu lifecycle không yêu cầu.

Nếu middleware tách partition thành nhiều queue vật lý, thay getNameForPartition bằng quy tắc tên partition phù hợp, ví dụ physicalName + "-p" + partition, đồng thời bảo đảm provisioning thực sự đã tạo đủ queue/stream tương ứng.

## 9. Tích hợp provider vào AbstractMessageChannelBinder

Với message-channel binder, Spring Cloud Stream hỗ trợ **AbstractMessageChannelBinder**. Nó có thể gọi provisioning provider trước khi tạo endpoint. Ví dụ skeleton:

~~~java
import org.springframework.cloud.stream.binder.AbstractMessageChannelBinder;
import org.springframework.cloud.stream.binder.ConsumerProperties;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ConsumerDestination;
import org.springframework.cloud.stream.provisioning.ProducerDestination;
import org.springframework.integration.core.MessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

public final class ExampleBusBinder
        extends AbstractMessageChannelBinder<
            ConsumerProperties,
            ProducerProperties,
            ExampleBusProvisioningProvider> {

    private final ExampleBusTransport transport;

    public ExampleBusBinder(
            ExampleBusProvisioningProvider provider,
            ExampleBusTransport transport) {
        super(null, provider);
        this.transport = transport;
    }

    @Override
    protected MessageHandler createProducerMessageHandler(
            ProducerDestination destination,
            ProducerProperties properties,
            MessageChannel errorChannel) {

        return message -> transport.publish(
            destination.getName(),
            message
        );
    }

    @Override
    protected MessageProducer createConsumerEndpoint(
            ConsumerDestination destination,
            String group,
            ConsumerProperties properties) {

        return new ExampleBusMessageProducer(
            transport,
            destination.getName(),
            group
        );
    }
}
~~~

**ExampleBusTransport** và **ExampleBusMessageProducer** là thành phần phải tự triển khai. Ví dụ chỉ thể hiện vị trí kết nối với SPI, không phải một binder có thể dùng ngay. ExampleBusMessageProducer cần hiện thực nhận message, chuyển sang Spring Message, quản lý thread/subscription, acknowledgment và stop/cleanup. Transport phải xử lý serialization, headers, retry/error channel, producer confirms và partition metadata theo middleware.

Trong Spring Integration, MessageProducer nên có lifecycle rõ ràng, thường bằng cách mở rộng MessageProducerSupport. Nếu producer của middleware mở socket/thread, cần khởi tạo khi endpoint start và đóng khi endpoint stop. Không tạo thread mỗi lần bind mà không có đường dừng tương ứng.

Phần provisioning nên được test độc lập trước khi ghép vào MessageHandler/MessageProducer; nếu không, lỗi tạo topic và lỗi deserialize/publish dễ bị nhầm.

## 10. Khai báo binder configuration và discovery

Một custom binder cần configuration class khởi tạo provider và binder, sau đó khai báo binder type để Spring Cloud Stream phát hiện.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExampleBusBinderConfiguration {

    @Bean
    ExampleBusProvisioningProvider exampleBusProvisioner(
            ExampleBusAdmin admin) {
        return new ExampleBusProvisioningProvider(
            admin,
            "tenant-a",
            true
        );
    }

    @Bean
    ExampleBusBinder exampleBusBinder(
            ExampleBusProvisioningProvider provisioner,
            ExampleBusTransport transport) {
        return new ExampleBusBinder(provisioner, transport);
    }
}
~~~

Trong thư viện binder, file **META-INF/spring.binders** chứa tên binder và configuration class:

~~~properties
exampleBus:\
com.example.stream.ExampleBusBinderConfiguration
~~~

Khi ứng dụng có nhiều binder, cấu hình binding phải chọn binder đúng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        routeOrder-in-0:
          destination: orders.created
          group: fulfillment
          binder: exampleBus
~~~

Khi dùng named binder, các cấu hình environment có thể tách biệt giữa các cluster, tenant hoặc account. Provider cần nhận namespace, credentials và Admin API đúng cho binder instance đó. Không chia sẻ một singleton admin client trỏ sang cluster khác giữa các binder context nếu không kiểm soát rõ phạm vi.

## 11. Vòng đời tài nguyên: từ deploy tới shutdown

Cần tách **vòng đời binding trong process** khỏi **vòng đời tài nguyên bền vững của broker**.

~~~mermaid
flowchart TD
    A[Deploy cấu hình] --> B[Provision / verify tài nguyên]
    B --> C[Create producer/consumer endpoint]
    C --> D[Start binding]
    D --> E[Trao đổi message]
    E --> F{Có sự kiện vòng đời?}
    F -->|Restart/scale/rebalance| G[Stop hoặc unbind endpoint cục bộ]
    G --> H[Resource bền vững vẫn tồn tại]
    H --> B
    F -->|Xóa tài nguyên có chủ đích| I[Quy trình cleanup bên ngoài]
    I --> J[Kiểm tra ownership, retention, consumer và dữ liệu]
    J --> K[Delete nếu được duyệt]
~~~

Đặt một điểm dừng rõ ràng giữa hai thế giới:

- **Binding stop/unbind**: dừng listener, producer, subscription client và giải phóng local threads/connections.
- **Broker resource cleanup**: xóa topic/queue/subscription trên broker theo ownership policy, không tự xảy ra chỉ vì ứng dụng shutdown.

Interface ProvisioningProvider chỉ có hai method provision. Nó **không cung cấp một callback xóa tài nguyên chung** cho mọi middleware. Vì thế, không nên xây thiết kế dựa trên giả định rằng Spring Cloud Stream tự xóa durable topic hoặc queue khi unbind.

Nếu tạo ephemeral resource theo chính sách broker (temporary queue, auto-delete subscription), broker có thể dọn resource khi điều kiện riêng của nó được đáp ứng. Đó là semantics của middleware, không phải quy tắc chung cho mọi custom binder.

## 12. Producer lifecycle và resource ownership

Khi output binding khởi động, provider thường:

1. Xác định physical destination từ logical name.
2. Kiểm tra producer properties, partitionCount và requiredGroups.
3. Tạo hoặc xác minh stream/exchange/topic.
4. Chuẩn bị durable group/queue nếu requiredGroups yêu cầu.
5. Trả về ProducerDestination.
6. Binder tạo producer MessageHandler và bắt đầu gửi message.

Khi producer dừng:

- Ngừng nhận message mới từ binding.
- Đợi hoặc flush các publish đang thực hiện trong thời hạn cho phép.
- Đóng producer client, connection, thread và callback.
- **Không xóa destination bền vững** vì các producer/consumer khác có thể đang sử dụng.

Nếu resource do Terraform, Helm hoặc một hệ thống provision bên ngoài tạo, custom binder không nên tự sửa metadata bất ngờ. Chế độ verify-only giúp phát hiện mismatch và báo lỗi sớm.

## 13. Consumer lifecycle, group và subscription

Với consumer có group, provider có thể tạo durable subscription hoặc queue để giữ backlog khi tất cả instance đang dừng. Đây là hành vi phù hợp với nhiều workload production.

Trong middleware giả định:

~~~text
Destination: tenant-a/events/orders.created
Group:       fulfillment
Resource:    durable subscription fulfillment
~~~

Khi Pod A và Pod B cùng tham gia group:

- Chỉ có một subscription logic chung cho group.
- Hai consumer client phối hợp hoặc competing-consume theo semantics broker.
- Mỗi instance không nên tạo một durable subscription riêng có tên ngẫu nhiên nếu chúng cần chia tải.
- Provisioning chạy lại ở mỗi instance phải tìm thấy cùng resource mà không phá cấu hình.

Nếu group không có tên, binder phải quy định cách tạo anonymous subscription. Nó có thể dùng tài nguyên ephemeral và xóa khi kết nối đóng, nhưng phải tài liệu hóa rõ khả năng mất backlog. Ví dụ ExampleBusProvisioningProvider ở phần trước cố ý từ chối anonymous group vì chưa thiết kế semantics đó.

## 14. Idempotent provisioning khi scale ngang

Khi Kubernetes scale từ 1 lên 10 Pod, có thể có 10 lời gọi provisionConsumerDestination đồng thời. Nếu method tạo tài nguyên bằng cách kiểm tra rồi tạo không có cơ chế xử lý race, các Pod có thể tranh chấp:

~~~text
Pod A: exists(topic)? no
Pod B: exists(topic)? no
Pod A: create(topic) -> OK
Pod B: create(topic) -> AlreadyExists
~~~

**AlreadyExists không nhất thiết là lỗi** nếu tài nguyên vừa tạo tương thích với yêu cầu. Provider nên thực hiện ensure semantics:

1. Gọi create-if-absent hoặc upsert theo khả năng SDK.
2. Nếu nhận AlreadyExists, đọc metadata hiện tại.
3. So sánh type, partitionCount, durability, ownership và retention.
4. Nếu tương thích, coi là thành công.
5. Nếu không tương thích, báo provisioning mismatch.
6. Không xóa rồi tạo lại để “sửa” mismatch khi có dữ liệu.

Một contract admin minh họa:

~~~java
public void ensureStream(String name, int partitions) {
    try {
        brokerAdmin.createStream(name, partitions);
    }
    catch (AlreadyExistsException ignored) {
        StreamInfo current = brokerAdmin.describeStream(name);

        if (current.partitions() < partitions) {
            throw new ResourceMismatchException(
                "Stream has fewer partitions than required"
            );
        }
    }
}
~~~

Các class brokerAdmin, AlreadyExistsException, StreamInfo và ResourceMismatchException là **kiểu minh họa của SDK adapter**, không phải API Spring Cloud Stream. Với một số broker, có thể mở rộng số partition theo cách an toàn; với broker khác, thay partition count có thể thay đổi phân phối key hoặc không được hỗ trợ. Hãy áp dụng policy của middleware thay vì tự thay đổi schema hoặc partition khi nhiều Pod cùng chạy.

## 15. Partition count và thay đổi quy mô

ProducerProperties chứa **partitionCount**. ConsumerProperties có các thuộc tính phục vụ partitioned consumer, concurrency và cấu hình instance. Tuy nhiên, ý nghĩa vật lý phụ thuộc binder.

| Middleware | Tài nguyên partition thường gặp | Điều cần lưu ý |
|---|---|---|
| Kafka | Một topic gồm nhiều partition native | Consumer group tự phân partition; tăng count thay đổi key mapping |
| RabbitMQ Binder | Các queue/đường routing theo partition trong một số cấu hình | Có thể phải chọn instanceIndex/instanceCount |
| Pulsar | Partitioned topic và subscription | Subscription type/assignment quyết định phân phối |
| Custom middleware | Stream shard, queue per partition hoặc partition native | Binder phải quy định mapping và chiến lược scale |

Nếu producer gửi dựa trên key ổn định, thay partition count có thể khiến cùng một key đi sang partition khác. Điều này ảnh hưởng ordering, stateful processing và consumer-local state. Không xem tăng partition như một thay đổi vô hại chỉ vì provisioning provider có thể tạo thêm tài nguyên.

Trong ví dụ ExampleBus, getNameForPartition trả cùng tên vì giả định native partition. Producer transport phải nhận được partition ID được binder tính toán; nếu không, ví dụ mới chỉ mô tả tài nguyên, chưa triển khai routing partition. Với middleware queue-per-partition, provider phải tạo hoặc xác minh đầy đủ tập queue và trả đúng partition name.

## 16. requiredGroups: chuẩn bị consumer trước khi consumer chạy

ProducerProperties hỗ trợ **requiredGroups**. Mục đích là bảo đảm các group chỉ định có tài nguyên nhận message ngay cả khi consumer của group chưa khởi động.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        produceOrder-out-0:
          destination: orders.created
          binder: exampleBus
          producer:
            required-groups:
              - fulfillment
              - analytics
            partition-count: 4
~~~

Nếu broker yêu cầu queue/subscription tồn tại trước để giữ message, provider phải gọi ensureDurableSubscription cho các group bắt buộc. Nếu middleware giữ backlog ở topic độc lập với subscription, requiredGroups có thể không cần tạo queue theo cách RabbitMQ; binder vẫn phải tài liệu hóa semantics.

Không xóa group khi producer ngừng vì các message chưa được xử lý có thể đang nằm trong backlog. Nếu requiredGroups chứa tên không hợp lệ hoặc group trái policy, nên fail provisioning rõ ràng.

## 17. Auto-provision và verify-only trong production

Có hai mô hình vận hành chính:

**Binder tự provision**

- Đơn giản cho development và integration test.
- Binder có quyền tạo topic/queue/subscription.
- Scale nhiều Pod có thể gọi Admin API đồng thời.
- Cần xử lý idempotency, metadata mismatch và quota.

**Hạ tầng provision trước, binder chỉ verify**

- IaC hoặc đội platform tạo resources, ACL, quota và retention.
- Ứng dụng có thể dùng principal ít quyền hơn.
- Provider chỉ mô tả/xác minh resource tồn tại và tương thích.
- Lỗi thiếu resource cần được phát hiện trước rollout hoặc fail binding.

Đối với custom binder, **autoProvision là tùy chọn do bạn tự định nghĩa**, không phải một property chung bắt buộc của Spring Cloud Stream. Muốn cấu hình nó bằng YAML, phải tự viết lớp @ConfigurationProperties và ràng buộc provider theo prefix của binder.

Ví dụ cấu hình tự định nghĩa:

~~~yaml
app:
  example-bus:
    namespace: tenant-a
    auto-provision: false
~~~

Không dùng một property tự đặt trong bài rồi giả định framework tự hiểu nếu chưa có configuration class tương ứng.

## 18. Permission và bảo mật khi provisioning

Trong các tổ chức có quy định chặt về tài nguyên, một ứng dụng xử lý message không nên tự có quyền tạo hoặc xóa mọi queue/topic trong broker.

Tách quyền theo trách nhiệm:

| Principal | Quyền cần thiết |
|---|---|
| Infrastructure provisioner | Create/alter tài nguyên theo phạm vi được giao |
| Application producer | Publish/write destination được phép |
| Application consumer | Subscribe/read/ack group được phép |
| Observability agent | Read metrics/metadata |
| Cleanup operator | Delete có quy trình phê duyệt và audit |

Nếu dùng verify-only, ứng dụng thường chỉ cần quyền metadata describe cộng quyền read/write. Nếu SDK buộc cần quyền admin để kiểm tra resource, cần đánh giá chính sách bảo mật thay vì cấp quyền quản trị toàn cluster.

Credential không được ghi vào exception hoặc log. ProvisioningException nên chứa tên destination an toàn, operation và error code; không chứa token, password hoặc full connection string có embedded secret.

## 19. Provisioning timeout, retry và fail-fast

Một Admin API call có thể thất bại vì broker chưa sẵn sàng, permission sai, rate limit hoặc metadata chưa đồng bộ. Provider không nên chờ vô hạn trong startup.

Thiết kế nên có:

- Connection timeout.
- Request timeout cho create/describe.
- Retry hữu hạn với backoff chỉ cho lỗi tạm thời.
- Phân biệt AlreadyExists, NotFound, Unauthorized, QuotaExceeded và Timeout.
- Thời gian chờ tối đa cho eventual consistency sau create.
- Error message chứa operation, logical/physical destination và nguyên nhân không nhạy cảm.

Ví dụ chính sách:

| Lỗi | Hành vi đề xuất |
|---|---|
| AlreadyExists, metadata tương thích | Thành công |
| AlreadyExists nhưng type/partition sai | Fail với ResourceMismatch |
| Timeout tạm thời | Retry có giới hạn rồi fail |
| Authentication/authorization sai | Fail nhanh, không retry vô hạn |
| Quota đã hết | Fail và cảnh báo vận hành |
| Resource vẫn chưa visible sau create | Đợi bounded consistency rồi fail |
| Consumer group xung đột semantics | Fail rõ, không tự sửa hoặc xóa |

Một số binder hỗ trợ cơ chế thử kết nối lại; nhưng không nên dựa vào đó để chữa lỗi provision resource vĩnh viễn. Nếu topic name sai hoặc ACL thiếu quyền, retry mãi chỉ làm startup kéo dài.

## 20. Tài nguyên nào được dọn khi unbind?

Khi Spring Cloud Stream unbind, Binding được yêu cầu dừng endpoint. Contract của Binding yêu cầu **unbind idempotent** và target không còn nhận message sau khi unbind.

Không nên xóa các tài nguyên sau khi chỉ stop hoặc unbind:

- Topic Kafka có dữ liệu.
- RabbitMQ durable queue của consumer group đang giữ backlog.
- Pulsar durable subscription có unacked message.
- Stream/shard ExampleBus được nhiều Pod sử dụng.
- DLT/DLQ hoặc retry destination dùng bởi các service khác.

Những tài nguyên thường có thể giải phóng tại local endpoint:

- Consumer client/producer client.
- Network connection và channel.
- Poller thread, scheduler và thread pool do endpoint sở hữu.
- Listener callback, metrics registration và timer.
- Transient buffer/cache nếu không cần khôi phục.

Ngay cả với ephemeral resources, điều kiện xóa cần được thiết kế minh bạch. Một queue tạm có thể bị broker auto-delete khi không còn consumer; nếu tự xóa ngay khi một Pod scale down, nó có thể cắt đường nhận của Pod khác.

## 21. Ai chịu trách nhiệm cleanup?

Nên định nghĩa **resource ownership** theo vòng đời:

| Resource | Owner | Cleanup |
|---|---|---|
| Topic/stream production có retention | Platform/IaC | Quy trình thay đổi hạ tầng, có kiểm tra dữ liệu |
| Durable group queue/subscription | Service owner/Platform | Chỉ xóa khi ngừng dịch vụ có chủ đích |
| Retry queue và DLQ/DLT | Service owner | Theo retention/replay policy, không xóa cùng binding |
| Anonymous temporary consumer | Binder/broker theo policy | Auto-delete hoặc cleanup có kiểm soát |
| Local producer/consumer client | Binder endpoint | Close/stop khi unbind hoặc shutdown |

Hành động xóa phải phân biệt tài nguyên **owned** bởi ứng dụng và **shared** giữa nhiều ứng dụng. Nếu có nhiều producer dùng chung topic, không producer nào được phép xóa topic chỉ vì nó ngừng hoạt động.

Để tránh orphan resources, có thể gắn labels/tags metadata như appName, environment, ownerTeam, provisionedBy, createdAt và retentionPolicy. Cleanup job phải đối chiếu với dữ liệu thực tế và bảo vệ backlog chưa xử lý trước khi xóa.

## 22. Mở rộng từ một tới nhiều instance

Giả sử triển khai app có một input group và chạy ba instance:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: fulfillment
          binder: exampleBus
          consumer:
            concurrency: 2
~~~

Nếu ExampleBus hỗ trợ competing consumers trong một durable subscription, cả ba instance có thể tham gia cùng group fulfillment và chia nhau message. Provider vẫn phải chạy idempotent trên từng instance.

Nếu ExampleBus yêu cầu mỗi consumer gắn vào một shard cụ thể, binder cần giải thích cách dùng **instanceCount** và **instanceIndex** để tránh trùng shard:

~~~yaml
spring:
  cloud:
    stream:
      instance-count: 3
      instance-index: 1
      bindings:
        processOrder-in-0:
          consumer:
            partitioned: true
~~~

Giá trị trên chỉ minh họa instance thứ hai (index 1 trong 0..2). Với RabbitMQ và middleware không có native partition assignment, index/count thường cần được quản lý rõ; với Kafka auto-rebalance, Kafka group coordinator thường quyết định assignment mà không cần cố định index.

**Concurrency không tự tạo thêm partition.** Nó điều chỉnh số consumer/worker đồng thời tùy binder. Partition provisioning và consumer assignment phải được thiết kế tương thích với thực tế middleware.

## 23. Lỗi scale thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Pod thứ hai fail startup | Provisioning không idempotent; AlreadyExists bị xem là lỗi | Chuyển sang ensure semantics, verify metadata |
| Consumer instance không nhận message | Sai group hoặc shard mapping | Kiểm tra group, instanceIndex, assignment |
| Message xử lý trùng sau scale down | Unacked record được giao lại | Ack/commit phù hợp và idempotency |
| Topic bị xóa khi một Pod dừng | Cleanup gắn nhầm vào unbind | Chỉ close local endpoints, tách ownership |
| Backlog biến mất sau restart | Dùng anonymous queue/subscription thay durable group | Khai báo group ổn định |
| Partitions không đủ throughput | Provisioner không tạo đủ shard hoặc không hỗ trợ tăng partition | Đánh giá scale strategy và partition topology |
| Producer phân vùng sai | getNameForPartition không khớp routing thực tế | Test key→partition và physical destinations |
| Multi-binder dùng sai namespace | Provider hoặc admin client chia sẻ config sai context | Tách binder instance/environment |
| Startup treo khi broker lỗi | Admin API không có timeout/retry limit | Đặt bounded timeout và fail policy |
| Mismatch tài nguyên bị âm thầm bỏ qua | Provider chỉ kiểm tra exists | Validate type, partition, retention và policy |

## 24. Kiểm thử ProvisioningProvider đơn lẻ

Đầu tiên unit test provider với mock ExampleBusAdmin. Kiểm tra nó tạo đúng tên, truyền group/partition và wrap exception đúng cách.

Ví dụ JUnit/Mockito:

~~~java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.stream.binder.ProducerProperties;
import org.springframework.cloud.stream.provisioning.ProducerDestination;

class ExampleBusProvisioningProviderTest {

    @Test
    void provisionsProducerAndRequiredGroup() {
        ExampleBusAdmin admin = mock(ExampleBusAdmin.class);

        ExampleBusProvisioningProvider provider =
            new ExampleBusProvisioningProvider(
                admin,
                "tenant-a",
                true
            );

        ProducerProperties properties = new ProducerProperties();
        properties.setPartitionCount(4);
        properties.setRequiredGroups("fulfillment");

        ProducerDestination destination =
            provider.provisionProducerDestination(
                "orders.created",
                properties
            );

        assertThat(destination.getName())
            .isEqualTo("tenant-a/events/orders.created");

        verify(admin).ensureStream(
            "tenant-a/events/orders.created", 4
        );

        verify(admin).ensureDurableSubscription(
            "tenant-a/events/orders.created", "fulfillment"
        );
    }
}
~~~

Các test khác nên kiểm tra:

- Consumer group thiếu tên bị từ chối nếu binder không hỗ trợ anonymous.
- AutoProvision=false chỉ verify và không create.
- AlreadyExists tương thích được xem là thành công.
- AlreadyExists không tương thích gây ProvisioningException.
- Destination name sai bị từ chối trước khi gọi broker.
- ProducerDestination.getNameForPartition xử lý partition ngoài phạm vi.
- Provider không gọi delete khi provision thất bại.

## 25. Integration test với nhiều instance

Unit test không phát hiện mọi vấn đề broker semantics. Cần Testcontainers hoặc môi trường integration với middleware thật để kiểm tra:

1. Hai Pod/test contexts cùng provision một destination đồng thời.
2. Cả hai nhận cùng physical destination và dùng chung durable group.
3. Thêm consumer thứ ba không tạo subscription tên khác.
4. Tạo message rồi stop tất cả consumer; backlog vẫn còn.
5. Khởi động lại consumer; message chưa ack được giao lại theo middleware policy.
6. Stop/unbind một instance; topic/queue/subscription vẫn tồn tại và instance khác tiếp tục hoạt động.
7. Tăng partition count theo policy; xác minh không làm mất dữ liệu hoặc sai routing.
8. Tạo resource trước bằng IaC; verify-only khởi động mà không yêu cầu create permission.
9. Cố tình cấu hình type hoặc retention sai; provider fail rõ ràng.
10. Broker không khả dụng khi startup; thời gian fail/retry có giới hạn.
11. Quota hoặc ACL bị từ chối; không tạo partial resource gây rác.
12. Xác minh DLT/DLQ vẫn tồn tại sau restart và scale down.
13. Kiểm tra số connection/thread sau nhiều lần bind/unbind để phát hiện leak.

Nếu custom binder không có Testcontainers module riêng, có thể dùng GenericContainer với image middleware hoặc môi trường ephemeral do CI cung cấp. Quan trọng là test đi qua SDK và hạ tầng provision thật; in-memory mock chỉ chứng minh control flow Java.

## 26. Quan sát provisioning và resource lifecycle

Custom binder nên cung cấp log/metrics cho cả provisioning và binding:

| Metric/log | Câu hỏi |
|---|---|
| provision_requests_total theo operation | Có bao nhiêu create/verify? |
| provision_duration_seconds | Admin API chậm tới đâu? |
| provision_conflicts_total | Bao nhiêu race AlreadyExists hoặc mismatch? |
| provision_failures_total theo error code | Lỗi ACL, timeout, quota hay validation? |
| binder_bindings_active | Có bao nhiêu binding endpoint đang chạy? |
| producer_publish_failures_total | Publish sau provisioning có hoạt động? |
| consumer_lag / unacked / subscription_backlog | Các consumer có tiến triển? |
| resource_orphans | Có tài nguyên còn tồn tại nhưng không ai sở hữu? |
| consumer_reconnect_total | Có reconnect storm sau rollout? |
| cleanup_requests_total | Ai đang thực hiện xóa tài nguyên? |

Không đặt tên destination gốc chưa chuẩn hóa thành metric label nếu có số lượng không giới hạn; có thể gây cardinality cao. Dùng app, binder, environment, errorCode và loại resource cho metric, còn tên resource cụ thể chỉ ghi log có kiểm soát.

Provisioning log nên ghi operation, physical name, group, kết quả, elapsed time và correlation/trace ID nếu có. Không log credential, message payload hoặc thông tin bảo mật nhạy cảm.

## 27. Quy trình triển khai và nâng cấp custom binder

Trước khi đưa custom binder vào production:

1. Quyết định resource owner: platform/IaC hay binder auto-provision.
2. Đặt naming convention và versioning rules ổn định.
3. Định nghĩa group semantics: durable, ephemeral, competing consumer, partition assignment.
4. Định nghĩa partition strategy và cách tăng/giảm partition.
5. Định nghĩa quyền create/describe/read/write/delete của từng principal.
6. Đặt timeout, bounded retry và error classification cho Admin API.
7. Đảm bảo create-if-absent idempotent và chống race khi scale.
8. Có chính sách cho metadata mismatch, không âm thầm tự xóa/tạo lại.
9. Không gắn delete bền vững với Binding.unbind.
10. Có quy trình cleanup riêng với ownership và retention approval.
11. Kiểm thử restart, scale, failover, backlog và replay.
12. Quan sát provisioning latency, failures, backlog và resource orphans.

Với upgrade binder, kiểm tra compatibility của Spring Cloud Stream API, Spring Integration API, middleware SDK và transport protocol. Nếu nâng cấp thay đổi naming hoặc partition strategy, cần migration plan; không đơn thuần deploy bản mới rồi để provider tự tạo tài nguyên khác khiến backlog cũ bị bỏ quên.

## 28. Tài liệu tham khảo

- [Spring Cloud Stream — Implementing Custom Binders](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-custom-binder-impl.html): hướng dẫn ProvisioningProvider, MessageProducer, MessageHandler, AbstractMessageChannelBinder, configuration và spring.binders.
- [Spring Cloud Stream — Binder SPI](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-api.html): bindProducer, bindConsumer và extension points.
- [Spring Cloud Stream — Binder Abstraction](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-binder-abstraction.html): ý nghĩa binding và destination.
- [ProvisioningProvider Javadoc](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-stream/latest/org/springframework/cloud/stream/provisioning/ProvisioningProvider.html): hợp đồng và các method của provisioning SPI.
- [ProducerDestination Javadoc](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-stream/latest/org/springframework/cloud/stream/provisioning/ProducerDestination.html): getName và getNameForPartition.
- [ConsumerDestination Javadoc](https://javadoc.io/doc/org.springframework.cloud/spring-cloud-stream/latest/org/springframework/cloud/stream/provisioning/ConsumerDestination.html): tham chiếu destination cho consumer.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): producer/consumer properties, partitionCount, requiredGroups, concurrency.
- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html): instanceCount/instanceIndex và binder-native partitioning.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html): Binding lifecycle, stop/start và quản lý binding.
- [Spring Cloud Stream — Using Existing RabbitMQ Destinations](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html): lựa chọn auto provisioning và existing infrastructure.

**Kết luận:** ProvisioningProvider chuyển destination logic của Spring Cloud Stream thành tài nguyên vật lý tương thích và trả lại tham chiếu cho binder tạo endpoint. Khi scale, method provision có thể được gọi đồng thời ở nhiều instance nên phải deterministic, idempotent và có kiểm tra metadata. Vòng đời endpoint (start, stop, unbind) cần được quản lý tách biệt với vòng đời topic, queue, subscription và DLQ bền vững. Một custom binder vận hành tốt không chỉ tạo được tài nguyên lần đầu, mà còn phải khởi động lại an toàn, giữ backlog khi Pod dừng, tránh tạo xung đột khi scale và chỉ xóa tài nguyên theo ownership policy có chủ đích.

