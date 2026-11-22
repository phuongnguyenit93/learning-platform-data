# Tính lũy đẳng, timeout và kiểm tra kết quả thao tác quản trị

Kafka Admin API cho phép ứng dụng tạo topic, tăng số partition, thay đổi cấu hình, quản lý ACL và kiểm tra trạng thái cluster. Các thao tác này thường được thực hiện qua AdminClient và trả kết quả bất đồng bộ. Trong môi trường phân tán, một request có thể đã được broker áp dụng nhưng response bị mất hoặc đến muộn. Vì vậy, ứng dụng không thể kết luận thao tác thất bại chỉ vì phía gọi nhận timeout.

Muốn quản trị an toàn, cần kết hợp ba nguyên tắc:

- **Xác định trạng thái mong muốn:** mô tả topic, partition, config hoặc ACL cần đạt.
- **Thực hiện thao tác có kiểm soát:** phân loại lỗi, đặt timeout và retry có giới hạn.
- **Đối soát trạng thái thực tế:** dùng các API describe để xác minh broker đã áp dụng gì trước khi gửi lại thao tác.

Đây là cách xây dựng hành vi lũy đẳng ở tầng ứng dụng. Không phải mọi Admin API đều có semantics lũy đẳng giống nhau; phải hiểu ý nghĩa từng thao tác và kiểm tra trạng thái cuối cùng.

## 1. Vì sao thao tác quản trị cần tính lũy đẳng?

Giả sử một automation gọi CreateTopics để tạo topic orders. Broker tạo topic thành công, nhưng response bị mất do kết nối mạng. Client nhận timeout và không biết topic đã được tạo hay chưa.

Nếu ứng dụng gửi lại request một cách mù quáng, broker có thể trả TopicExistsException. Đây không nhất thiết là lỗi nghiệp vụ: có thể request đầu đã thành công, hoặc topic đã tồn tại từ trước với cấu hình khác.

Tình huống tương tự xảy ra với các thao tác khác:

- CreatePartitions đã tăng partition nhưng response bị timeout.
- IncrementalAlterConfigs đã cập nhật config nhưng caller không nhận được kết quả.
- DeleteTopics đã yêu cầu xóa nhưng quá trình xóa chưa hoàn tất.
- Một request quản trị tác động đến nhiều topic, trong đó một số thành công và một số thất bại.

Sơ đồ tình huống timeout không xác định:

~~~mermaid
sequenceDiagram
    participant App as Admin application
    participant Broker as Kafka broker/controller

    App->>Broker: Create topic orders
    Broker->>Broker: Apply topic creation
    Broker--xApp: Response bị mất
    Note over App: Caller nhận timeout<br/>không biết thao tác đã áp dụng chưa
    App->>Broker: Describe topic orders
    Broker-->>App: Trạng thái thực tế
    App->>App: So sánh desired state với actual state
~~~

Timeout là kết quả về thời gian chờ của caller. Nó không phải bằng chứng rằng broker đã rollback thao tác.

## 2. Idempotency ở tầng Admin API là gì?

Một thao tác lũy đẳng có thể được gọi lại mà trạng thái cuối cùng vẫn như sau một lần thực hiện. Với quản trị Kafka, cách thiết kế hữu ích là mô tả trạng thái mong muốn rồi đối chiếu với trạng thái thực tế.

Ví dụ mong muốn:

- Topic orders tồn tại.
- Topic có 12 partition.
- Mỗi partition có replication factor bằng 3.
- min.insync.replicas bằng 2.

Thay vì chỉ gọi lệnh create mỗi lần chạy, ứng dụng kiểm tra trạng thái trước, thực hiện phần còn thiếu rồi đọc lại để xác nhận.

| Thao tác | Hành vi khi gọi lại | Cách làm an toàn |
|---|---|---|
| CreateTopics | Có thể trả TopicExistsException nếu topic đã tồn tại | Describe topic và so sánh partition, replica, config |
| CreatePartitions | Không thể giảm partition; lặp lại số lượng hiện tại có thể bị từ chối | Đọc số partition hiện tại, chỉ tăng khi thấp hơn mục tiêu |
| IncrementalAlterConfigs với SET | Đặt config về cùng một giá trị mong muốn | Đọc lại config để xác minh |
| IncrementalAlterConfigs với DELETE | Xóa override để quay về giá trị mặc định | Xác minh trạng thái override/default |
| IncrementalAlterConfigs với APPEND | Có thể thêm phần tử vào cấu hình dạng danh sách | Không lặp mù; đọc danh sách trước và sau |
| DeleteTopics | Topic có thể đang trong quá trình xóa hoặc đã biến mất | Describe và xác nhận trạng thái cuối |
| CreateAcls | ACL binding có thể đã tồn tại | Describe ACL để so sánh binding thực tế |

Điểm quan trọng: **lũy đẳng của trạng thái mong muốn khác với lũy đẳng của request giao thức**. Ứng dụng phải xác minh kết quả thay vì giả định mọi request lặp đều an toàn.

## 3. AdminClient trả kết quả bất đồng bộ

Java AdminClient cung cấp các API quản trị trả về result object chứa KafkaFuture. Ví dụ:

~~~java
CreateTopicsResult result =
    admin.createTopics(List.of(new NewTopic("orders", 6, (short) 3)));

result.all().get();
~~~

Lời gọi createTopics trả về trước khi toàn bộ thao tác hoàn tất. Phương thức get chờ kết quả. Trong code production, nên dùng timeout rõ ràng và xử lý exception.

Một số API result có thể cung cấp future theo từng resource:

- CreateTopicsResult có map future theo topic.
- CreatePartitionsResult có map future theo topic.
- AlterConfigsResult hoặc IncrementalAlterConfigsResult có future theo ConfigResource.
- DeleteTopicsResult có future theo tên topic.

Khi thao tác trên nhiều resource, không giả định tất cả thành công hoặc tất cả thất bại cùng lúc. Một số resource có thể thành công trong khi resource khác lỗi. Hãy kiểm tra kết quả theo từng resource nếu cần phục hồi chính xác.

## 4. Phân biệt các loại timeout

Có nhiều lớp timeout trong AdminClient. Chúng có ý nghĩa khác nhau.

| Cấu hình | Phạm vi | Ý nghĩa |
|---|---|---|
| request.timeout.ms | Một request mạng | Thời gian client chờ response cho request trước khi xem request timeout |
| default.api.timeout.ms | Một thao tác Admin API | Timeout mặc định cho API nếu không truyền timeout riêng |
| Timeout truyền vào Future.get | Thread ứng dụng đang chờ | Giới hạn thời gian caller chờ kết quả future |
| retry.backoff.ms | Client retry | Khoảng chờ cơ sở giữa các lần retry |
| retry.backoff.max.ms | Client retry | Giới hạn trên cho backoff tăng dần ở các client hỗ trợ |
| transaction.timeout.ms | Kafka transaction | Không phải timeout của Admin API |

Không nhầm request timeout với API timeout. Một thao tác quản trị có thể phát sinh nhiều request hoặc cần thời gian coordinator/controller xử lý; default API timeout bao quát thời gian chờ của thao tác ở tầng client.

### 4.1. Timeout khi chờ Future.get()

Ví dụ:

~~~java
try {
    result.all().get(30, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    // Caller hết thời gian chờ.
}
~~~

Timeout ở Future.get không chứng minh request đã bị hủy ở broker. Request có thể vẫn được xử lý, hoặc đã thành công nhưng response chưa về.

Sau timeout, bước tiếp theo nên là đọc trạng thái thực tế bằng describe API. Chỉ gửi lại thao tác sau khi đã xác định trạng thái hiện tại và quy tắc retry cho thao tác đó.

### 4.2. Timeout của API và timeout của request

Có thể cấu hình AdminClient:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092
client.id=platform-admin
request.timeout.ms=30000
default.api.timeout.ms=60000
retry.backoff.ms=200
retry.backoff.max.ms=1000
~~~

Các giá trị là ví dụ. Cần chọn timeout dựa trên độ trễ mạng, tải controller, kích thước thao tác và SLA của automation.

Tăng timeout quá cao có thể khiến job treo lâu khi cluster không khỏe. Đặt timeout quá thấp có thể làm ứng dụng báo lỗi dù broker vẫn đang thực hiện thao tác.

## 5. Retry nội bộ của AdminClient và retry của ứng dụng

AdminClient có thể tự retry một số lỗi tạm thời theo protocol và cấu hình client. Ứng dụng không nên tạo thêm vòng retry không giới hạn bên ngoài mà không phân loại lỗi.

Phân nhóm thường gặp:

| Nhóm lỗi | Ví dụ | Hành động |
|---|---|---|
| Lỗi tạm thời | NetworkException, broker/controller unavailable, request timeout | Cho client retry; nếu kết quả cuối không rõ thì reconcile bằng describe |
| Trạng thái đã tồn tại | TopicExistsException | Describe và so sánh cấu hình mong muốn |
| Trạng thái không hợp lệ | InvalidPartitionsException, InvalidConfigurationException | Đọc trạng thái hiện tại, sửa desired state hoặc dừng |
| Quyền truy cập | AuthorizationException | Không retry liên tục; kiểm tra ACL/principal |
| Cấu hình sai | ConfigException, invalid request | Sửa input hoặc phiên bản client |
| Resource không tồn tại | UnknownTopicOrPartitionException | Xác minh resource name và trạng thái thao tác |
| Lỗi không xác định sau timeout | Caller không biết broker đã áp dụng chưa | Đọc trạng thái thực tế trước khi quyết định |

Retry chỉ phù hợp khi lỗi có khả năng tự phục hồi. Authorization failure hoặc cấu hình sai sẽ không tự biến mất sau vài lần thử.

Một vòng retry ứng dụng nên có:

- Số lần thử tối đa.
- Deadline tổng thể.
- Exponential backoff và jitter.
- Phân loại retriable/non-retriable.
- Reconciliation giữa các lần thử.
- Log và metric cho từng resource.

Không retry toàn bộ batch nếu chỉ một topic thất bại mà các topic khác đã được tạo thành công.

## 6. Mẫu xử lý CreateTopics an toàn

Mục tiêu không chỉ là gửi CreateTopics mà là bảo đảm topic đạt trạng thái mong muốn.

Ví dụ topic orders cần 6 partition và replication factor 3:

~~~java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.CreateTopicsResult;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.errors.TopicExistsException;

public class TopicProvisioner {

    public static void ensureTopic(
            AdminClient admin,
            String topicName,
            int expectedPartitions,
            short expectedReplicationFactor) throws Exception {

        NewTopic request = new NewTopic(
            topicName,
            expectedPartitions,
            expectedReplicationFactor
        );

        try {
            CreateTopicsResult result =
                admin.createTopics(List.of(request));

            result.all().get(30, TimeUnit.SECONDS);

        } catch (ExecutionException exception) {
            if (!hasCause(exception, TopicExistsException.class)) {
                throw exception;
            }
            // Topic đã tồn tại: cần kiểm tra actual state bên dưới.

        } catch (TimeoutException timeout) {
            // Kết quả chưa xác định. Không gửi create lặp ngay.
            // Đối soát bằng describe topic.
        }

        TopicDescription actual = admin
            .describeTopics(List.of(topicName))
            .allTopicNames()
            .get(30, TimeUnit.SECONDS)
            .get(topicName);

        if (actual.partitions().size() != expectedPartitions) {
            throw new IllegalStateException(
                "Partition count mismatch for " + topicName
            );
        }

        boolean replicationMatches = actual.partitions()
            .stream()
            .allMatch(partition ->
                partition.replicas().size() == expectedReplicationFactor
            );

        if (!replicationMatches) {
            throw new IllegalStateException(
                "Replication factor mismatch for " + topicName
            );
        }
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType) {

        Throwable current = error;

        while (current != null) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }

        return false;
    }
}
~~~

Đây là ví dụ kiểm tra topic đã tồn tại và xác minh số partition/replica. Trong triển khai thực tế, khi CreateTopics timeout, describe có thể cần được thử lại trong một deadline ngắn vì thao tác tạo có thể vẫn đang hoàn tất. Nếu topic chưa xuất hiện sau deadline, job cần báo trạng thái chưa xác định hoặc tiếp tục reconciliation theo chính sách; không tạo vòng create vô hạn.

Nếu replication factor thực tế khác mục tiêu, tăng replication factor không được thực hiện bằng CreateTopics. Cần lập kế hoạch replica reassignment riêng. Tương tự, partition count chỉ có thể tăng, không thể giảm bằng CreatePartitions.

### 6.1. validateOnly không thay thế reconciliation

CreateTopicsOptions có thể dùng validateOnly để kiểm tra request mà không tạo topic:

~~~java
CreateTopicsOptions options =
    new CreateTopicsOptions().validateOnly(true);

admin.createTopics(List.of(request), options);
~~~

ValidateOnly hữu ích để phát hiện một số lỗi request trước khi thực hiện. Nó không giữ chỗ tên topic, không ngăn thay đổi cluster giữa lúc validate và create, và không chứng minh thao tác thật sẽ thành công sau đó.

## 7. Tăng partition theo desired state

CreatePartitions chỉ tăng số partition. Một automation nên đọc số partition hiện tại rồi so sánh với mục tiêu.

~~~java
int currentCount = admin
    .describeTopics(List.of(topicName))
    .allTopicNames()
    .get(15, TimeUnit.SECONDS)
    .get(topicName)
    .partitions()
    .size();

if (currentCount < desiredCount) {
    admin.createPartitions(
        Map.of(topicName, NewPartitions.increaseTo(desiredCount))
    ).all().get(30, TimeUnit.SECONDS);
} else if (currentCount > desiredCount) {
    throw new IllegalStateException(
        "Kafka partitions cannot be reduced by CreatePartitions"
    );
}

// Đọc lại để xác minh số partition thực tế.
~~~

Nếu request tăng partition đã thành công nhưng response timeout, lần chạy sau sẽ đọc thấy số partition mới. Khi actual state bằng desired state, không cần gửi lại CreatePartitions.

Cần lưu ý việc tăng partition có thể làm thay đổi key-to-partition mapping với partitioner mặc định. Record cùng key được gửi sau khi tăng partition có thể đi vào partition khác, ảnh hưởng thứ tự theo key trên toàn topic. Hãy đánh giá tác động nghiệp vụ trước khi tăng partition.

## 8. Thay đổi config bằng IncrementalAlterConfigs

Với topic configuration, nên ưu tiên IncrementalAlterConfigs trong các phiên bản hỗ trợ thay vì thay toàn bộ config bằng AlterConfigs cũ.

Ví dụ đặt min.insync.replicas thành 2:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AlterConfigOp;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.common.config.ConfigResource;

ConfigResource resource = new ConfigResource(
    ConfigResource.Type.TOPIC,
    "orders"
);

AlterConfigOp setMinIsr = new AlterConfigOp(
    new ConfigEntry("min.insync.replicas", "2"),
    AlterConfigOp.OpType.SET
);

admin.incrementalAlterConfigs(
    Map.of(resource, List.of(setMinIsr))
).all().get(30, TimeUnit.SECONDS);
~~~

Các operation type:

| Operation | Ý nghĩa | Lưu ý lũy đẳng |
|---|---|---|
| SET | Đặt config về giá trị chỉ định | Thường phù hợp với desired-state reconciliation |
| DELETE | Xóa override để dùng giá trị mặc định | Xác minh effective/default config sau thao tác |
| APPEND | Thêm giá trị vào config dạng danh sách | Không lặp mù vì có thể thêm phần tử trùng |
| SUBTRACT | Loại giá trị khỏi config dạng danh sách | Đọc lại để xác nhận danh sách cuối |

Sau khi SET hoặc DELETE, cần describeConfigs để xác minh. Với DELETE, giá trị hiệu lực có thể đến từ default broker hoặc config kế thừa; phân biệt việc xóa override với việc giá trị hiệu lực biến mất.

### 8.1. Đọc lại config sau khi thay đổi

~~~java
Config actual = admin.describeConfigs(List.of(resource))
    .all()
    .get(15, TimeUnit.SECONDS)
    .get(resource);

String effectiveValue = actual.entries()
    .stream()
    .filter(entry -> entry.name().equals("min.insync.replicas"))
    .map(ConfigEntry::value)
    .findFirst()
    .orElse(null);

if (!"2".equals(effectiveValue)) {
    throw new IllegalStateException(
        "min.insync.replicas was not applied as expected"
    );
}
~~~

Một số config có thể được đánh dấu là default hoặc synonym. Nếu mục tiêu là xác minh override cụ thể, cần xem metadata config entry và config synonyms phù hợp với phiên bản Kafka thay vì chỉ so sánh value.

## 9. DeleteTopics và trạng thái xóa bất đồng bộ

DeleteTopics cũng có kết quả không xác định khi caller timeout. Topic có thể đã nhận yêu cầu xóa nhưng metadata chưa biến mất ngay lập tức.

Quy trình an toàn:

1. Gửi DeleteTopics.
2. Chờ future trong deadline.
3. Nếu timeout hoặc response không rõ, gọi DescribeTopics.
4. Nếu topic không còn tồn tại, xem thao tác đã đạt trạng thái mong muốn.
5. Nếu topic vẫn tồn tại, kiểm tra trạng thái controller, cấu hình delete.topic.enable, quyền và log broker.
6. Chỉ gửi lại yêu cầu theo chính sách retry có giới hạn.

Xóa topic là thao tác phá hủy dữ liệu. Automation nên yêu cầu tên resource chính xác, ghi audit log và kiểm tra danh sách topic trước khi xóa. Không coi UnknownTopicOrPartitionException là bằng chứng duy nhất của thành công nếu tên topic có thể bị gõ sai.

## 10. Nhiều resource có thể thành công một phần

Khi gọi một API trên nhiều topic hoặc ConfigResource, kết quả không nhất thiết nguyên tử trên toàn bộ danh sách.

Ví dụ tạo ba topic cùng lúc:

~~~java
CreateTopicsResult result = admin.createTopics(List.of(
    new NewTopic("orders", 6, (short) 3),
    new NewTopic("payments", 6, (short) 3),
    new NewTopic("shipments", 3, (short) 3)
));
~~~

Có thể orders và payments thành công trong khi shipments thất bại vì cấu hình hoặc quyền. Future tổng hợp result.all() có thể báo lỗi nếu một phần thất bại, nhưng không có nghĩa các topic thành công đã bị rollback.

Cách xử lý:

- Đọc future theo từng topic từ result.values().
- Ghi nhận trạng thái riêng cho từng resource.
- Reconcile từng resource với desired state.
- Chỉ retry resource thất bại hoặc còn trạng thái chưa xác định.
- Không xóa các resource đã thành công chỉ để giả lập rollback toàn batch nếu không có kế hoạch rõ ràng.

Admin API không phải transaction tổng quát cho nhiều loại thao tác quản trị. Nếu cần thay đổi nhiều resource, hãy thiết kế workflow có checkpoint và khả năng chạy lại.

## 11. Java AdminClient: cấu hình và quản lý lifecycle

Ví dụ tạo AdminClient:

~~~java
import java.time.Duration;
import java.util.Properties;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;

Properties props = new Properties();

props.put(
    AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
props.put(AdminClientConfig.CLIENT_ID_CONFIG, "platform-admin");
props.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, 30000);
props.put(AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, 60000);

try (AdminClient admin = AdminClient.create(props)) {
    // Thực hiện create/describe/alter/delete và xác minh kết quả.
}
~~~

AdminClient có tài nguyên mạng và thread nền. Nên tái sử dụng một instance cho nhóm công việc quản trị có vòng đời phù hợp, sau đó đóng bằng try-with-resources hoặc close có timeout.

Không tạo AdminClient mới cho mỗi request HTTP nếu service có thể tái sử dụng một client thread-safe. Cần quản lý shutdown để các thao tác đang chờ có thời gian hoàn tất hoặc được ghi nhận là chưa xác định.

## 12. Timeout, deadline và backoff ở tầng ứng dụng

Một workflow quản trị nên có deadline tổng thể thay vì mỗi bước có thể retry vô hạn.

Ví dụ:

| Lần thử | Backoff minh họa |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,6 giây |
| 5 | 3,2 giây |

Thêm jitter để nhiều automation không đồng loạt retry khi controller vừa phục hồi. Backoff không thay thế timeout; mỗi lần chờ và gọi describe đều tiêu thụ ngân sách deadline.

Một workflow có thể gồm:

1. Đọc actual state.
2. Nếu đã đúng desired state, kết thúc thành công.
3. Nếu còn thiếu, gửi một thao tác phù hợp.
4. Chờ future trong timeout.
5. Nếu kết quả không rõ, describe lại.
6. Nếu trạng thái chưa đạt và lỗi có thể retry, backoff rồi thử lại trong giới hạn.
7. Nếu lỗi permanent hoặc hết deadline, báo trạng thái và resource cụ thể.

Không retry một thao tác chỉ vì exception không được nhận diện. Mặc định an toàn là giữ trạng thái chưa xác định và yêu cầu reconciliation hoặc can thiệp.

## 13. Mô hình kết quả thao tác quản trị

Thay vì chỉ trả về true/false, automation nên biểu diễn kết quả chi tiết:

| Trạng thái | Ý nghĩa |
|---|---|
| APPLIED | Đã xác minh actual state bằng desired state |
| ALREADY_SATISFIED | Resource đã ở trạng thái mong muốn trước thao tác |
| PARTIAL | Một số resource thành công, một số chưa đạt |
| RETRYABLE | Lỗi tạm thời đã được phân loại và còn ngân sách retry |
| UNKNOWN | Caller timeout và chưa xác minh được kết quả |
| REJECTED | Lỗi quyền, cấu hình hoặc request không hợp lệ |
| DRIFT | Resource tồn tại nhưng khác desired state và cần thay đổi riêng |

Trạng thái UNKNOWN rất quan trọng. Nó ngăn hệ thống báo thất bại giả hoặc gửi lại thao tác phá hủy chỉ vì response bị mất.

Một record audit nên chứa:

- Operation ID của workflow.
- Resource type và resource name.
- Desired state.
- Actual state trước và sau thao tác.
- Thời điểm, client ID và principal.
- Số lần thử và exception cuối.
- Trạng thái cuối cùng.

Không đưa password, token hoặc secret vào audit log.

## 14. Kiểm tra kết quả bằng describe API

Mỗi nhóm thao tác có API đọc trạng thái tương ứng:

| Thao tác | API xác minh |
|---|---|
| CreateTopics | describeTopics, describeConfigs |
| CreatePartitions | describeTopics |
| IncrementalAlterConfigs | describeConfigs |
| DeleteTopics | describeTopics |
| CreateAcls/DeleteAcls | describeAcls |
| Broker/config resource | describeConfigs với ConfigResource tương ứng |
| Cluster metadata | describeCluster, describeTopics hoặc API phù hợp |

Việc xác minh cần so sánh đúng thuộc tính mong muốn. Ví dụ topic tồn tại chưa có nghĩa topic đã đúng số partition, replication factor hoặc min ISR.

Khi kiểm tra replica assignment, không chỉ xem replication factor. Cần kiểm tra broker ID trong replicas, leader, ISR và rack placement nếu đó là yêu cầu của desired state.

## 15. Bảo mật và quyền quản trị

AdminClient sử dụng principal được cấu hình qua security protocol, SASL hoặc SSL. Các thao tác cần quyền ACL phù hợp.

Ví dụ:

- Create topic cần quyền quản trị topic tương ứng.
- Alter topic config cần quyền thay đổi config.
- Delete topic cần quyền xóa.
- Describe topic/config cần quyền đọc metadata/config.
- Quản lý ACL cần quyền quản trị ACL.

AuthorizationException không phải lỗi transient để retry liên tục. Hãy ghi rõ principal, resource type/name và operation bị từ chối; không ghi credential vào log.

Nên cấp quyền tối thiểu cho automation. Một job chỉ cần tạo topic không nhất thiết phải có quyền xóa topic hoặc sửa ACL toàn cluster.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CreateTopics trả TopicExistsException | Topic đã tồn tại hoặc lần trước đã thành công | Describe và so sánh desired state |
| Future.get timeout nhưng topic vẫn xuất hiện | Broker áp dụng thao tác nhưng response đến muộn/mất | Xem timeout là UNKNOWN, reconcile |
| CreatePartitions lỗi khi retry | Partition count đã được tăng ở lần trước | Describe số partition trước khi gửi lại |
| Alter config báo thành công nhưng value không như mong đợi | Kiểm tra nhầm config override/default hoặc resource | DescribeConfigs và kiểm tra config entry/synonym |
| Một phần topic được tạo, phần còn lại lỗi | API xử lý theo resource, không có rollback batch | Kiểm tra future từng resource |
| DeleteTopics timeout | Quá trình xóa chưa hoàn tất hoặc response bị mất | Describe và kiểm tra controller/delete config |
| Retry mãi không thành công | Authorization hoặc invalid configuration | Phân loại non-retriable và dừng |
| Job quản trị treo lâu | Timeout quá cao hoặc retry không có deadline | Đặt API timeout, deadline tổng thể và backoff |
| APPEND config tạo phần tử lặp | Gửi lại thao tác dạng append sau timeout | Đọc danh sách hiện tại và tính phần tử còn thiếu |

## 17. Checklist xây dựng Admin workflow lũy đẳng

- [ ] Đã xác định desired state cho từng resource.
- [ ] Đã phân biệt request idempotency với desired-state idempotency.
- [ ] AdminClient dùng timeout rõ ràng và được đóng đúng lifecycle.
- [ ] Future được chờ bằng deadline có giới hạn.
- [ ] Timeout được xem là kết quả chưa xác định cho đến khi describe xác minh.
- [ ] TopicExistsException được xử lý bằng describe, không xem là thành công mù.
- [ ] CreatePartitions chỉ tăng partition khi actual count thấp hơn mục tiêu.
- [ ] Config SET/DELETE được xác minh; APPEND/SUBTRACT không retry mù.
- [ ] DeleteTopics được xác minh trước khi gửi lại.
- [ ] Kết quả được kiểm tra theo từng resource khi thao tác nhiều resource.
- [ ] Retry chỉ áp dụng cho lỗi transient và có backoff/jitter.
- [ ] Có trạng thái UNKNOWN/PARTIAL/DRIFT cho workflow.
- [ ] Audit log ghi operation, desired state, actual state và kết quả.
- [ ] Authorization failure không bị retry liên tục.
- [ ] Đã kiểm thử response timeout sau khi broker đã áp dụng thao tác.
- [ ] Đã kiểm thử một batch có resource thành công và resource thất bại.

Kafka Admin API cung cấp thao tác bất đồng bộ, nhưng ứng dụng quản trị phải chịu trách nhiệm về timeout, retry và xác minh trạng thái. Khi response bị mất, hãy xem kết quả là chưa xác định, đọc actual state bằng describe rồi mới quyết định bước tiếp theo. Thiết kế theo desired state, xử lý riêng từng resource và giới hạn retry giúp automation có thể chạy lại an toàn mà không tạo thay đổi ngoài ý muốn.
