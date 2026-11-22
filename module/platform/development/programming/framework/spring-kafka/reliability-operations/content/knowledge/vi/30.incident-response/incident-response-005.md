# Runbook: xử lý khi Spring Kafka consumer không start

## 1. Mục tiêu và phạm vi

Runbook này hướng dẫn xử lý sự cố khi một ứng dụng Spring Boot/Spring Kafka không khởi chạy được consumer hoặc listener không bắt đầu nhận bản tin. Mục tiêu là xác định chính xác consumer đang dừng ở giai đoạn nào, khôi phục hoạt động an toàn và giữ nguyên trạng thái offset của Kafka.

Trong Spring Kafka, cần phân biệt bốn trạng thái thường bị gọi chung là “consumer không start”:

1. **Ứng dụng không khởi động:** Spring ApplicationContext thất bại trước khi ứng dụng sẵn sàng.
2. **Ứng dụng đã chạy nhưng listener chưa chạy:** bean listener không được đăng ký, container bị tắt hoặc cấu hình `autoStartup` ngăn container khởi động.
3. **Listener container đang chạy nhưng chưa nhận partition:** consumer chưa tham gia group, không subscribe đúng topic hoặc chưa hoàn tất việc phân chia partition.
4. **Đã có partition nhưng không xử lý được bản tin:** consumer đã start; lỗi xảy ra trong poll, deserialize, listener hoặc xử lý nghiệp vụ.

Phân loại đúng trạng thái giúp tránh xử lý nhầm. Ví dụ, đổi `auto.offset.reset` không sửa được lỗi DNS; tăng `concurrency` không sửa được ACL; đổi `group.id` có thể tạo một consumer group mới và làm thay đổi tập bản tin được đọc.

## 2. Nguyên tắc ứng phó

- Ghi nhận thời điểm bắt đầu, môi trường, tên service, pod/instance, Kafka cluster, topic, consumer group và phiên bản vừa triển khai.
- Lưu log cùng thời điểm lỗi trước khi restart hoặc thay đổi cấu hình. Giữ lại exception gốc và toàn bộ chuỗi `Caused by`.
- Kiểm tra một instance trước. Nếu có nhiều replica, tránh restart đồng loạt vì thao tác đó có thể tạo rebalance trên toàn bộ consumer group.
- Thay đổi từng yếu tố một và ghi lại giá trị trước/sau. Ưu tiên khôi phục cấu hình đã biết là hoạt động tốt.
- Không tự ý đổi `group.id`, xóa consumer group, reset/seek offset, xóa topic hoặc bật/tắt auto-commit trong lúc điều tra.
- Không đưa password, SASL JAAS config, token, private key hoặc nội dung secret vào ticket, log chia sẻ hay lệnh chẩn đoán được lưu lại.

Nếu có nguy cơ mất dữ liệu, xử lý trùng bản tin hoặc ảnh hưởng nhiều service, báo người phụ trách Kafka/on-call trước khi thực hiện thao tác có thể thay đổi offset, ACL hoặc dữ liệu topic.

## 3. Phân loại nhanh sự cố

| Dấu hiệu | Trạng thái có khả năng | Việc cần kiểm tra đầu tiên |
|---|---|---|
| Pod liên tục restart; log có `Application run failed` hoặc lỗi tạo bean | Ứng dụng không khởi động | Exception gốc, cấu hình Spring, bean và listener container factory |
| Ứng dụng Ready nhưng không thấy log consumer khởi động | Listener chưa chạy | `@KafkaListener`, registry, `autoStartup`, profile và điều kiện tạo bean |
| Log có lỗi kết nối broker, DNS, TLS hoặc SASL | Không kết nối được Kafka | Bootstrap servers, network, TLS/SASL và secret đang được mount |
| Có log join group/rebalance nhưng không có partition được gán | Chưa có assignment | Topic/subscription, group, partition, ACL và trạng thái các member |
| Có partition assignment nhưng lag không giảm hoặc listener báo lỗi | Đã start, lỗi khi xử lý | Deserializer, exception handler, listener code, downstream dependency và thời gian xử lý |

Đừng kết luận consumer đã khỏe chỉ vì process đang chạy hoặc health endpoint trả về UP. Cần xác nhận listener container và consumer group thực sự hoạt động.

## 4. Thu thập bằng chứng trước khi sửa

### 4.1. Xác nhận phạm vi ảnh hưởng

Ghi lại các thông tin sau:

| Thông tin | Giá trị cần ghi |
|---|---|
| Service và môi trường | Tên ứng dụng, namespace, environment |
| Instance lỗi | Pod name, hostname hoặc instance ID |
| Thời điểm | Lần cuối consumer xử lý thành công và thời điểm lỗi đầu tiên |
| Kafka | Cluster/bootstrap servers và security protocol (không ghi secret) |
| Subscription | Topic hoặc topic pattern |
| Consumer group | Group ID thực tế sau khi áp dụng cấu hình |
| Thay đổi gần nhất | Release, config map, secret, certificate, ACL, network policy |
| Mức ảnh hưởng | Tất cả replica hay chỉ một replica; một topic hay nhiều topic |

So sánh một instance lỗi với instance đang hoạt động (nếu có). Tập trung vào image/version, active profile, biến môi trường, secret version, bootstrap servers, group ID và topic. Không in toàn bộ environment nếu trong đó có secret.

### 4.2. Đọc log đúng khoảng thời gian

Lấy log từ trước thời điểm startup đến sau khi lỗi xuất hiện. Tìm các nhóm thông điệp sau:

- `Application run failed`, `BeanCreationException`, `UnsatisfiedDependencyException`: lỗi khởi tạo Spring hoặc dependency.
- `Failed to start bean` hoặc lỗi liên quan `KafkaListenerEndpointRegistry`: lỗi khởi động listener container.
- `Bootstrap broker`, `Connection to node`, `disconnected`, `TimeoutException`: kết nối hoặc metadata broker.
- `UnknownHostException`, `ConnectException`: DNS hoặc đường mạng.
- `SslAuthenticationException`, `SSLHandshakeException`, `SaslAuthenticationException`: TLS/SASL hoặc thông tin xác thực.
- `TopicAuthorizationException`, `GroupAuthorizationException`, `ClusterAuthorizationException`: quyền Kafka.
- `UnknownTopicOrPartitionException`: tên topic, metadata hoặc topic chưa tồn tại.
- `SerializationException`, `RecordDeserializationException`: lỗi deserialize trong quá trình đọc bản tin.
- `Rebalance`, `Revoking previously assigned partitions`, `Successfully assigned`: trạng thái tham gia group và assignment.

Các dòng trên là dấu hiệu để khoanh vùng, không phải kết luận độc lập. Đọc exception đầu tiên và chuỗi nguyên nhân; lỗi xuất hiện cuối cùng đôi khi chỉ là hậu quả của lỗi cấu hình ban đầu.

Với Kubernetes, có thể lấy log và mô tả pod bằng các lệnh đọc sau (thay placeholder bằng tên thực tế):

```bash
kubectl logs <pod-name> -n <namespace> --since=20m --all-containers=true
kubectl describe pod <pod-name> -n <namespace>
```

Kiểm tra cả `Events`, trạng thái restart, readiness/liveness probe, image và volume mount. Nếu ứng dụng chạy ngoài Kubernetes, lấy log từ đúng process/instance và kiểm tra cơ chế restart tương ứng.

### 4.3. Kiểm tra trạng thái listener trong ứng dụng

Nếu ứng dụng đã chạy, kiểm tra listener container bằng `KafkaListenerEndpointRegistry`. Đoạn mã dưới đây chỉ đọc trạng thái container; có thể đặt trong một diagnostic component tạm thời hoặc dùng trong một endpoint nội bộ đã được bảo vệ.

```java
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class KafkaListenerDiagnostics {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerDiagnostics(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void logListenerStates() {
        for (String id : registry.getListenerContainerIds()) {
            MessageListenerContainer container = registry.getListenerContainer(id);
            log.info("Kafka listener id={}, found={}, running={}",
                    id,
                    container != null,
                    container != null && container.isRunning());
        }
    }
}
```

Nếu registry không có ID listener mong đợi, điều tra việc đăng ký endpoint và tạo bean. Nếu có ID nhưng `running=false`, kiểm tra `autoStartup`, thao tác stop từ ứng dụng và lỗi lúc container start. Nếu `running=true`, tiếp tục kiểm tra kết nối, assignment và poll; trạng thái này chưa chứng minh consumer đã nhận partition.

Không công khai diagnostic endpoint ra Internet và không log các thuộc tính cấu hình chứa credential.

## 5. Quy trình điều tra theo thứ tự

### Bước 1 — Xác nhận ứng dụng có khởi động hoàn tất không

**Dấu hiệu:** process thoát, pod restart, readiness thất bại hoặc log dừng ở giai đoạn tạo ApplicationContext.

Kiểm tra:

1. Tìm exception đầu tiên trong log startup và đọc đầy đủ `Caused by`.
2. Xác nhận active Spring profile đúng với môi trường.
3. Kiểm tra các placeholder như `${KAFKA_BOOTSTRAP_SERVERS}`, `${KAFKA_GROUP_ID}` và tên topic có được cấp giá trị hay không.
4. Kiểm tra bean listener, dependency injection, `KafkaListenerContainerFactory` và cấu hình deserializer.
5. So sánh config map/secret/version hiện tại với bản triển khai gần nhất còn hoạt động.

Các nguyên nhân thường gặp:

- Thiếu biến môi trường hoặc placeholder không được resolve.
- Bean listener hoặc dependency của listener không tạo được.
- Tên `containerFactory` trong `@KafkaListener` không khớp bean factory đã khai báo.
- Cấu hình deserializer hoặc security không hợp lệ khiến bean/client khởi tạo thất bại.
- Cấu hình topic được kiểm tra khi startup và topic không tồn tại trong khi ứng dụng bật chế độ coi topic thiếu là lỗi fatal.

**Cách khôi phục:** sửa đúng giá trị cấu hình hoặc bean gây lỗi; nếu lỗi bắt đầu sau một release/config change, cân nhắc rollback về phiên bản cuối cùng đã chạy tốt. Sau đó triển khai một instance và xác nhận ApplicationContext khởi động hoàn tất trước khi mở rộng rollout.

### Bước 2 — Xác nhận listener endpoint đã được đăng ký và được phép start

**Dấu hiệu:** ứng dụng Ready nhưng listener ID không xuất hiện trong registry hoặc container không chạy.

Kiểm tra khai báo listener và cấu hình liên quan:

```java
@KafkaListener(
    id = "orders-listener",
    topics = "${app.kafka.orders-topic}",
    groupId = "${app.kafka.orders-group}"
)
public void consume(OrderEvent event) {
    // Xử lý bản tin
}
```

Đối chiếu các điểm sau:

- Class chứa `@KafkaListener` có được component scan và tạo thành bean không?
- Điều kiện `@Profile`, `@ConditionalOnProperty` hoặc feature flag có vô hiệu hóa bean ở môi trường đang lỗi không?
- Ứng dụng có bật cơ chế xử lý `@KafkaListener` và có đúng listener container factory không?
- Giá trị `topics`/`topicPattern`, `groupId` và `containerFactory` có được resolve đúng không?
- Có cấu hình `autoStartup=false` ở annotation, container factory hoặc cấu hình Spring Boot không?
- Có code vận hành nào đã gọi `stop()` trên container sau khi ứng dụng khởi động không?

Các cấu hình cần đối chiếu thường gồm:

```yaml
spring:
  kafka:
    listener:
      auto-startup: true
```

`auto-startup` có thể được ghi đè bởi profile, biến môi trường hoặc cấu hình triển khai. Kiểm tra giá trị hiệu lực trong process đang chạy thay vì chỉ đọc file YAML trong repository. Nếu listener được cố ý start thủ công, xác minh thành phần chịu trách nhiệm gọi `start()` đã chạy.

Lưu ý: `id` trong `@KafkaListener` là ID của listener container. Nếu không khai báo `groupId` riêng, Spring Kafka có thể dùng `id` làm group ID theo thiết lập `idIsGroup`. Vì vậy, hãy xác nhận group ID hiệu lực; đừng suy ra group ID chỉ từ tên method hoặc tên bean.

**Cách khôi phục:** sửa điều kiện tạo bean, tên factory, topic/group placeholder hoặc cờ startup về giá trị đã được phê duyệt. Chỉ start lại container sau khi xác nhận cấu hình đúng và nguyên nhân container bị dừng.

### Bước 3 — Xác minh bootstrap servers và đường mạng tới Kafka

**Dấu hiệu:** listener đã start nhưng log liên tục báo disconnect, timeout hoặc không lấy được metadata.

Kiểm tra theo thứ tự:

1. `spring.kafka.bootstrap-servers` có đúng cluster của môi trường không; định dạng phải là danh sách `host:port`.
2. DNS của hostname broker có phân giải được từ đúng pod/container/host chạy ứng dụng không.
3. Network policy, firewall, security group, service mesh hoặc route có cho phép kết nối tới broker không.
4. Các broker được trả về trong metadata có thể truy cập từ runtime không. Kết nối được bootstrap address chưa chắc đã kết nối được mọi broker trong cluster.
5. Port và security protocol có khớp với listener của broker không.

Ví dụ kiểm tra DNS và TCP từ môi trường chạy ứng dụng (nếu image có các tiện ích tương ứng):

```bash
getent hosts <broker-host>
nc -vz <broker-host> <broker-port>
```

Nếu không có `getent` hoặc `nc`, dùng công cụ chẩn đoán được chuẩn hóa của môi trường. Không cài công cụ hoặc thay đổi network policy trực tiếp trên production chỉ để chạy thử.

**Cách khôi phục:** sửa bootstrap address, DNS, route hoặc rule mạng tại đúng lớp sở hữu. Sau thay đổi, kiểm tra kết nối từ instance bị lỗi và theo dõi log metadata/consumer trước khi rollout các replica còn lại.

### Bước 4 — Kiểm tra TLS, SASL và secret

**Dấu hiệu:** log có handshake failure, certificate error, authentication failure hoặc broker từ chối kết nối.

Đối chiếu:

- `security.protocol` có đúng `SSL`, `SASL_SSL`, `SASL_PLAINTEXT` hoặc cơ chế mà cluster yêu cầu không.
- SASL mechanism và JAAS configuration có khớp cấu hình broker không.
- Truststore/keystore có đúng file, định dạng, password reference và quyền đọc không.
- Certificate còn hạn, đúng hostname/SAN và chain tin cậy không.
- Secret được mount vào đúng container và phiên bản secret có đúng với release không.
- Thời gian hệ thống có chính xác để xác thực certificate không.

Không in giá trị `sasl.jaas.config`, password hoặc private key để so sánh. Chỉ xác minh tên secret, version, đường dẫn, quyền file và fingerprint/certificate metadata theo quy trình bảo mật của tổ chức.

**Cách khôi phục:** phối hợp với nhóm quản lý Kafka/identity để cấp lại hoặc mount đúng credential/certificate. Không tắt TLS hostname verification hoặc hạ security protocol như một biện pháp chữa cháy. Sau khi secret được cập nhật, restart đúng instance theo quy trình rollout để client nạp lại cấu hình.

### Bước 5 — Xác minh topic, consumer group và ACL

**Dấu hiệu:** kết nối broker thành công nhưng consumer không subscribe, không join group hoặc broker trả về lỗi authorization.

Kiểm tra tên topic chính xác, kể cả prefix/suffix theo môi trường. Xác minh topic tồn tại và có partition:

```bash
kafka-topics.sh \
  --bootstrap-server <bootstrap-server> \
  --describe \
  --topic <topic-name>
```

Kiểm tra consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-server> \
  --describe \
  --group <group-id>
```

Kết quả `--describe` giúp xem consumer member, partition được gán, current offset, log end offset và lag (tùy phiên bản Kafka). Nếu group chưa tồn tại, điều đó có thể đơn giản là consumer chưa từng join group; tiếp tục đối chiếu log và trạng thái listener.

Kiểm tra:

- Topic trong annotation có đúng topic thực tế không; nếu dùng `topicPattern`, regex có khớp tên topic sau khi áp dụng prefix không?
- Topic có partition và metadata hợp lệ không?
- Consumer group ID có bị thay đổi bởi profile, biến môi trường hoặc thuộc tính `groupId` của annotation không?
- Có member nào khác trong group đang giữ assignment hoặc liên tục join/leave gây rebalance không?
- Principal của ứng dụng có quyền đọc topic và tham gia consumer group theo ACL của cluster không?
- Nếu cluster dùng ACL, nhóm quản trị Kafka có thể kiểm tra quyền hiệu lực cho đúng principal, topic và group không?

Với lỗi authorization, phân biệt quyền trên topic với quyền trên group. Không cấp quyền rộng hoặc sửa ACL trực tiếp để thử; yêu cầu nhóm sở hữu cluster xác minh principal và cấp đúng quyền tối thiểu theo quy trình.

Nếu topic chưa tồn tại, xác minh đó là lỗi triển khai hay topic được tạo bởi một quy trình riêng. Chỉ tạo topic sau khi xác nhận tên, partition count, replication factor và cấu hình retention với người sở hữu dữ liệu. Nếu ứng dụng cấu hình `missingTopicsFatal=true`, topic thiếu có thể làm container fail khi start; không tắt kiểm tra này để che giấu lỗi provisioning.

### Bước 6 — Nếu container chạy nhưng chưa có partition assignment

**Dấu hiệu:** listener container báo running, consumer có thể kết nối broker nhưng group chưa có partition được gán.

Kiểm tra:

- Consumer thực sự subscribe đúng topic hoặc pattern.
- Topic có partition và các partition có thể được assign không.
- Group ID có đúng với group đang được theo dõi không.
- Có rebalance liên tục do pod restart, network chập chờn hoặc consumer rời group không.
- `group.instance.id` (nếu dùng static membership) có bị trùng giữa các replica không.
- `partition.assignment.strategy` có tương thích với cấu hình và phiên bản client của các member không.
- ACL có cho phép consumer đọc topic và group không.

Một consumer group có thể có nhiều member hơn số partition; khi đó một số member không được gán partition nhưng consumer group vẫn có thể hoạt động bình thường. So sánh số member với số partition trước khi kết luận lỗi.

**Cách khôi phục:** sửa subscription/group hoặc cấu hình member gây rebalance. Nếu nguyên nhân là một instance liên tục mất kết nối, xử lý instance đó trước. Không tăng concurrency theo phản xạ: số consumer hoạt động song song bị giới hạn bởi số partition có thể được assign.

### Bước 7 — Nếu đã có assignment nhưng không xử lý được bản tin

**Dấu hiệu:** consumer group hiển thị partition/member nhưng lag không giảm, log có lỗi deserialize hoặc listener liên tục thất bại.

Phân loại tiếp:

- **Deserialize:** kiểm tra key/value deserializer, schema/type, header, dữ liệu thực tế và cấu hình `ErrorHandlingDeserializer` nếu đang dùng. Một bản tin không tương thích có thể làm poll thất bại hoặc bị chuyển qua error handler tùy cấu hình.
- **Listener exception:** đọc exception từ method xử lý, kiểm tra validation, null handling và logic nghiệp vụ. Xác định error handler đang retry, recover, seek hay dừng container.
- **Downstream dependency:** kiểm tra database, HTTP service, lock hoặc connection pool mà listener cần. Consumer có thể đang chờ dependency thay vì không start.
- **Poll interval:** xử lý một batch quá lâu có thể vượt `max.poll.interval.ms`, khiến consumer rời group và bị rebalance. Đo thời gian xử lý và xem log rebalance trước khi chỉnh timeout.
- **Concurrency và partition:** xác minh số partition, số member và mức xử lý thực tế; nhiều thread hơn không làm tăng số partition được cấp.

Không tăng retry vô hạn hoặc bỏ qua exception để làm lag giảm trên dashboard. Trước khi thay đổi retry/DLT/error handler, xác định chính sách với bản tin lỗi, khả năng xử lý trùng và yêu cầu lưu giữ dữ liệu.

## 6. Các cấu hình dễ bị hiểu nhầm

| Cấu hình | Tác dụng | Không giải quyết được |
|---|---|---|
| `spring.kafka.bootstrap-servers` | Địa chỉ bootstrap để client lấy metadata Kafka | ACL sai, topic sai hoặc listener bị tắt |
| `spring.kafka.consumer.group-id` | Group ID mặc định của consumer | Không bảo đảm annotation không ghi đè group ID |
| `@KafkaListener(groupId = "...")` | Group ID áp dụng cho listener đó | Không phải ID của container |
| `@KafkaListener(id = "...")` | Định danh listener container; có thể được dùng làm group ID theo `idIsGroup` khi không khai báo `groupId` | Không chứng minh listener đã chạy |
| `spring.kafka.listener.auto-startup` / `autoStartup` | Cho phép hoặc ngăn listener container tự khởi động | Không sửa kết nối, xác thực hoặc topic |
| `spring.kafka.consumer.auto-offset-reset` | Chọn vị trí bắt đầu khi group không có offset hợp lệ | Không reset offset đã commit; không sửa lỗi start/kết nối |
| `spring.kafka.listener.concurrency` | Số consumer thread/container cho listener | Không tạo thêm partition và không tự sửa rebalance |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll theo cơ chế Kafka consumer | Không nên tăng nếu chưa đo thời gian xử lý và xác định nguyên nhân |

Đặc biệt, `auto.offset.reset=earliest` hoặc `latest` chỉ có tác dụng khi không có offset đã commit hợp lệ. `earliest` có thể khiến consumer đọc lại toàn bộ dữ liệu còn retention; `latest` có thể bỏ qua dữ liệu cũ đang tồn tại khi group bắt đầu mới. Không dùng thay đổi này như một bước khởi động lại consumer thông thường.

Thay đổi `group.id` tạo một consumer group khác. Group mới có offset riêng và sẽ tuân theo `auto.offset.reset`; điều này có thể gây đọc lại hoặc bỏ qua dữ liệu so với group cũ. Chỉ thực hiện khi có quyết định rõ ràng về semantics dữ liệu và kế hoạch rollback.

## 7. Trình tự khôi phục an toàn

1. Xác định nguyên nhân cụ thể từ log, trạng thái container và kết quả kiểm tra broker/topic/group.
2. Ghi lại cấu hình hiện tại và xác định chủ sở hữu của lớp cần sửa: ứng dụng, nền tảng triển khai, network, security hay Kafka.
3. Chọn thay đổi nhỏ nhất có thể khôi phục nguyên nhân; chỉ thay đổi một nhóm cấu hình mỗi lần.
4. Nếu cần sửa release hoặc config, dùng quy trình deploy/rollback chuẩn. Không sửa trực tiếp pod đang chạy nếu thay đổi đó không được lưu vào nguồn cấu hình chuẩn.
5. Triển khai hoặc restart một instance. Xác nhận ứng dụng Ready, listener container running, consumer join group và được assign partition.
6. Quan sát log, consumer group và lag trong một khoảng thời gian đủ để thấy consumer poll và xử lý bản tin.
7. Khi instance thử nghiệm ổn định, mới tiếp tục rollout các replica còn lại theo từng đợt.
8. Nếu lỗi quay lại, dừng rollout, lưu bằng chứng mới và rollback thay đổi vừa thực hiện theo quy trình.

Không xóa offset hoặc reset group để làm cho consumer “chạy lại”. Nếu nghiệp vụ yêu cầu replay, lập kế hoạch riêng: xác định phạm vi partition/offset, ước lượng lượng dữ liệu, đánh giá idempotency và được chủ sở hữu dữ liệu phê duyệt.

## 8. Tiêu chí xác nhận đã khôi phục

Chỉ đóng incident khi các điều kiện phù hợp với hệ thống đều được xác nhận:

- Ứng dụng khởi động ổn định và readiness đạt yêu cầu.
- Listener ID mong đợi xuất hiện trong registry và container ở trạng thái running.
- Consumer kết nối được broker, join đúng group và nhận partition như dự kiến.
- `kafka-consumer-groups --describe` cho thấy member/assignment hợp lý; lag giảm khi topic có dữ liệu mới và consumer có khả năng xử lý.
- Không còn lỗi DNS, kết nối, TLS/SASL, authorization hoặc deserialize lặp lại.
- Log ứng dụng hoặc metric nghiệp vụ xác nhận bản tin được xử lý thành công.
- Các replica khác vẫn khỏe; không có rebalance loop hoặc restart loop sau rollout.
- Không có thay đổi ngoài kế hoạch đối với group ID, offset, topic, ACL hoặc security protocol.

Nếu topic không có dữ liệu mới và lag bằng 0, không thể dùng việc lag không đổi để kết luận consumer bị treo. Hãy xác nhận assignment và một lần poll/heartbeat thành công theo log hoặc metric sẵn có.

## 9. Thông tin cần gửi khi escalation

Khi chuyển sự cố cho nhóm Kafka, platform hoặc security, gửi một gói thông tin ngắn gọn gồm:

1. Service, môi trường, pod/instance và thời điểm lỗi (kèm timezone).
2. Topic, group ID hiệu lực, Kafka cluster và phiên bản ứng dụng/client.
3. Trạng thái ApplicationContext, listener registry/container và consumer group.
4. Log startup liên quan, exception gốc cùng chuỗi `Caused by`; đã loại bỏ secret và dữ liệu nhạy cảm.
5. Kết quả `kafka-topics --describe` và `kafka-consumer-groups --describe` nếu được phép chạy.
6. Kết quả kiểm tra DNS/TCP/TLS/SASL phù hợp với lỗi.
7. Thay đổi gần nhất, các bước đã thử, kết quả từng bước và tình trạng rollback.
8. Mức ảnh hưởng: số replica, topic/partition bị ảnh hưởng, lag hoặc thời gian gián đoạn và tác động nghiệp vụ.

Yêu cầu nhóm nhận xử lý xác nhận rõ lớp đang lỗi (ứng dụng, mạng, xác thực, ACL, topic/group hay xử lý bản tin), hành động tiếp theo, người sở hữu và điều kiện hoàn tất.

## 10. Checklist thao tác nhanh

- [ ] Xác định ứng dụng có khởi động hoàn tất hay không.
- [ ] Lưu log startup và exception gốc trước khi restart.
- [ ] Xác nhận listener ID có trong `KafkaListenerEndpointRegistry` và container có running.
- [ ] Kiểm tra `autoStartup`, active profile, topic, group ID và container factory hiệu lực.
- [ ] Kiểm tra bootstrap servers, DNS, TCP và khả năng truy cập broker metadata.
- [ ] Kiểm tra TLS/SASL, certificate và secret mà không làm lộ credential.
- [ ] Kiểm tra topic, partition, consumer group, assignment và ACL.
- [ ] Nếu đã assign partition, kiểm tra deserialize, listener exception, downstream và poll interval.
- [ ] Khôi phục bằng một thay đổi có kiểm soát trên một instance trước.
- [ ] Xác nhận assignment, xử lý bản tin và lag trước khi rollout phần còn lại.
- [ ] Ghi lại nguyên nhân gốc, thay đổi, kết quả và mọi tác động đến dữ liệu/offset.
