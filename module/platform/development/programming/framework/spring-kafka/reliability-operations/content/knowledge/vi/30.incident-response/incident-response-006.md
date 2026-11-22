# Runbook khi consumer bị fenced

## Mục đích và phạm vi

Runbook này hướng dẫn điều tra và khôi phục khi consumer Kafka sử dụng Spring for Apache Kafka bị fencing, đặc biệt là lỗi `FencedInstanceIdException` liên quan đến static membership. Fencing là cơ chế bảo vệ ownership: khi Kafka xác định một instance cũ không còn là member hợp lệ, instance đó bị ngăn tiếp tục hoạt động dưới danh tính đã bị instance khác chiếm quyền.

Trong vận hành Spring Kafka, cụm từ “consumer bị fenced” thường được dùng cho trường hợp hai consumer cùng sử dụng một `group.instance.id`. Khi consumer mới đăng ký cùng static member ID, coordinator có thể fence consumer cũ. Tuy nhiên, log của ứng dụng cũng có thể chứa lỗi fencing từ transactional producer, chẳng hạn `ProducerFencedException`. Hai trường hợp có nguyên nhân và cách khắc phục khác nhau; phải xác định exception cụ thể trước khi thay đổi cấu hình.

Runbook áp dụng cho ứng dụng Spring Kafka chạy trên VM, container hoặc Kubernetes, gồm listener container thường và ứng dụng consume-process-produce có transaction. Cấu hình và event có thể khác nhau theo Kafka client, broker, Spring Kafka và group protocol. Luôn đối chiếu phiên bản thực tế trước khi áp dụng ví dụ.

## Hiểu đúng các loại fencing

### Consumer bị fence do trùng static member ID

Kafka hỗ trợ static membership thông qua `group.instance.id`. Giá trị này định danh ổn định một member của consumer group qua các lần restart. Khi một consumer khác tham gia group với cùng `group.instance.id`, coordinator chỉ có thể chấp nhận một member cho danh tính đó. Member cũ có thể bị fence và nhận `FencedInstanceIdException`.

Tình huống thường gặp:

- Hai pod cùng nhận một giá trị `group.instance.id` do cấu hình literal được dùng cho mọi replica.
- Hai tiến trình chạy đồng thời trong lúc rollout, failover hoặc thao tác restart thủ công và dùng chung một static member ID.
- Stateful workload tạo lại pod với danh tính cũ trong khi tiến trình cũ vẫn còn sống hoặc chưa rời group.
- Nhiều listener child container dùng cùng ID vì cấu hình static membership không tính đến `concurrency` hoặc cách Spring Kafka tạo ID cho child container.
- Hai môi trường hoặc hai ứng dụng vô tình dùng chung `group.id` và `group.instance.id`.

Với static membership, consumer có thể giữ vị trí trong group trong khoảng thời gian session timeout khi tạm thời mất kết nối. Điều này giúp giảm rebalance khi restart ngắn, nhưng yêu cầu mỗi logical member có ID duy nhất và vòng đời được quản lý rõ ràng.

### Transactional producer bị fence trong luồng consume-process-produce

Ứng dụng có thể consume một bản ghi, xử lý rồi publish kết quả trong Kafka transaction. Trong trường hợp này, lỗi `ProducerFencedException` thường chỉ ra transactional producer cũ đã bị một producer khác có cùng `transactional.id` thay thế, hoặc producer đang dùng epoch đã lỗi thời.

Nguyên nhân thường gặp:

- Nhiều application instance dùng chung `transactional.id` hoặc cùng `transactionIdPrefix` mà không có suffix duy nhất.
- Hai producer cùng cố gắng sở hữu một transactional ID sau rollout, failover hoặc chạy trùng tiến trình.
- Transactional producer cũ vẫn tiếp tục gửi/commit sau khi producer mới đã khởi tạo với cùng danh tính.

Lỗi producer fencing không được sửa bằng cách đổi `group.instance.id`. Kiểm tra `transactional.id`, `spring.kafka.producer.transaction-id-prefix` và cách cấp suffix cho từng producer instance.

### Những lỗi dễ bị nhầm

| Dấu hiệu trong log | Ý nghĩa cần điều tra |
|---|---|
| `FencedInstanceIdException` | Static member ID của consumer đã bị member khác sử dụng trong cùng group |
| `ProducerFencedException` | Transactional producer ID/epoch đã bị producer mới thay thế |
| `CommitFailedException` | Commit không còn hợp lệ, thường do consumer không còn quyền sở hữu partition hoặc group đã thay đổi; cần tìm nguyên nhân trước đó |
| `RebalanceInProgressException` | Group đang rebalance; đây không tự nó chứng minh có duplicate static member ID |
| `Commit cannot be completed since the group has already rebalanced` | Commit đến sau khi group generation thay đổi; đối chiếu poll interval, rebalance và thời gian xử lý |

Không kết luận có fencing chỉ từ một thông báo rebalance hoặc commit thất bại. Xác định exception gốc và member/client ID liên quan.

## Dấu hiệu nhận biết và ảnh hưởng

Các dấu hiệu có thể xuất hiện:

- Log consumer có `FencedInstanceIdException`, thông tin về static member ID bị fence hoặc member instance không còn hợp lệ.
- Listener container dừng hoặc consumer không tiếp tục poll sau lỗi fencing; hành vi và event phát ra phụ thuộc phiên bản Spring Kafka.
- Một pod có thể ghi log bị fence trong khi pod khác với cùng danh tính vẫn tiếp tục tiêu thụ.
- Group member/assignment thay đổi gần thời điểm deployment, pod restart, scale hoặc failover.
- Lag tăng do một member dừng, partition phải được cấp lại hoặc consumer group phải ổn định lại.
- Với transactional producer fencing, log có `ProducerFencedException`, transaction abort hoặc lỗi khi commit transaction.

Fencing giúp ngăn hai tiến trình cùng tiếp tục thao tác dưới một danh tính mà Kafka yêu cầu phải duy nhất. Không cố vô hiệu hóa cơ chế fencing bằng cách lặp lại restart liên tục. Nếu duplicate owner vẫn tồn tại, instance mới có thể tiếp tục fence instance cũ và sự cố sẽ lặp lại.

## Nguyên tắc xử lý

1. Lấy exception gốc và phân biệt consumer fencing với transactional producer fencing.
2. Xác định cluster, `group.id`, `group.instance.id`, `client.id`, pod/host và timestamp của từng member.
3. Kiểm tra mọi replica và child container cùng group trước khi restart. Một lần restart đơn lẻ có thể che dấu duplicate owner nhưng không loại bỏ cấu hình trùng.
4. Bảo đảm danh tính consumer hoặc transactional producer duy nhất theo đúng phạm vi Kafka yêu cầu.
5. Không reset offset, xóa group, tăng concurrency hoặc đổi group ID như một cách chữa cháy nếu chưa đánh giá tác động tới xử lý dữ liệu.
6. Ghi lại cấu hình cũ và chỉ thay đổi một nguyên nhân trong mỗi lần can thiệp.

## Quy trình xử lý sự cố

### 1. Xác nhận exception và phạm vi

Thu thập các thông tin sau trước khi can thiệp:

| Thông tin | Cần xác định |
|---|---|
| Cluster và môi trường | Production/staging, bootstrap servers, namespace hoặc host |
| Consumer group | `group.id` chính xác và danh sách topic subscription |
| Exception | Class đầy đủ, stack trace và message đầu tiên tại thời điểm lỗi |
| Consumer identity | `group.instance.id`, `client.id`, consumer ID, pod/host và process start time |
| Listener | `@KafkaListener` ID, container factory, concurrency và replica count |
| Transaction | Có dùng Kafka transaction/EOS không; `transactional.id` hoặc `transactionIdPrefix` là gì |
| Thay đổi gần nhất | Deployment, scale, restart, failover, thay đổi cấu hình hoặc node replacement |
| Ảnh hưởng | Consumer nào dừng, lag, throughput, lỗi commit và tác động nghiệp vụ |

Đọc exception gốc trong log, không chỉ đọc dòng log cuối cùng của container. Nếu stack trace đi qua `KafkaConsumer.poll()` và có `FencedInstanceIdException`, tiếp tục theo nhánh consumer static membership. Nếu lỗi xuất hiện khi gửi/commit transaction và có `ProducerFencedException`, chuyển sang nhánh transactional producer ở bước 5.

### 2. Kiểm tra consumer group và member đang chạy

Từ máy có Kafka CLI và quyền truy cập cluster, chụp trạng thái group:

```bash
export BOOTSTRAP_SERVERS="broker-1:9092,broker-2:9092"
export GROUP_ID="orders-consumer-v1"

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --members \
  --verbose
```

Tùy phiên bản Kafka, các tùy chọn `--state`, `--members` và `--verbose` có thể khác nhau. Nếu CLI không hỗ trợ, dùng lệnh `--describe --group` cơ bản và lấy thông tin member từ log broker hoặc công cụ quản trị tương ứng.

Đối chiếu kết quả với log từng pod/process:

- Có bao nhiêu process đang chạy với cùng `group.instance.id`?
- Có hai pod/host cùng khai báo một static member ID tại cùng thời điểm không?
- Consumer nào bị fence và consumer nào tiếp tục giữ danh tính đó?
- Có member mới xuất hiện ngay sau deployment hoặc restart không?
- Một `group.id` có đang được nhiều service hoặc môi trường dùng chung ngoài dự kiến không?
- Số consumer thực tế có khớp với `replica count × listener concurrency` không?

Thông tin member trong CLI có thể không hiển thị trực tiếp toàn bộ `group.instance.id` tùy phiên bản và output. Dùng client log/config đã render để xác minh giá trị. Không suy ra ID từ `client.id` nếu chưa xác nhận cách ứng dụng tạo chúng.

Chụp trạng thái group nhiều lần để biết member nào xuất hiện/mất đi. Ghi lại timestamp và timezone nhằm đối chiếu rollout, orchestrator event và broker log.

### 3. Kiểm tra cách cấp `group.instance.id`

Tìm mọi nơi cấu hình consumer properties:

- `spring.kafka.consumer.properties` trong YAML/properties.
- `ConsumerConfig.GROUP_INSTANCE_ID_CONFIG` trong cấu hình `ConsumerFactory`.
- `DefaultKafkaConsumerFactory` hoặc `ConcurrentKafkaListenerContainerFactory` được khai báo thủ công.
- Biến môi trường, ConfigMap, Secret, Helm values hoặc tham số JVM.
- Cấu hình được tạo động từ hostname, pod name, StatefulSet ordinal hoặc application instance ID.

Đảm bảo mỗi member trong cùng group có `group.instance.id` riêng. Một giá trị literal giống nhau cho tất cả replica là cấu hình sai. ID phải ổn định cho cùng một logical member khi cần static membership, đồng thời không bị cấp cho hai process đang chạy cùng lúc.

Ví dụ cấu hình Spring Boot cho một consumer member trên mỗi pod:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-consumer-v1
      properties:
        "[group.instance.id]": "orders-${HOSTNAME}"
```

Ví dụ trên chỉ an toàn khi `HOSTNAME` thực sự khác nhau giữa các pod/member và được truyền vào ứng dụng đúng như dự kiến. Với Kubernetes StatefulSet, hostname thường gắn với ordinal của pod nên có thể tạo danh tính ổn định qua lần restart của cùng ordinal. Với Deployment, pod mới thường có tên mới; ID theo hostname vẫn duy nhất nhưng không duy trì static identity qua lần thay pod. Chọn chiến lược theo mục tiêu vận hành và cách triển khai.

Nếu listener container dùng `concurrency > 1`, cần bảo đảm từng child consumer có ID duy nhất. Một số phiên bản Spring Kafka tự thêm hậu tố vào `group.instance.id` cho các child container của `ConcurrentMessageListenerContainer`; xác minh hành vi của đúng phiên bản đang chạy và kiểm tra giá trị cuối cùng ở Kafka client log. Không tự thêm hậu tố đồng thời với cơ chế của framework nếu điều đó tạo ra ID không nhất quán.

### 4. Xử lý duplicate static member ID

Khi đã xác định hai process dùng cùng `group.instance.id`:

1. Xác định process nào là owner dự kiến theo replica, StatefulSet ordinal hoặc quy tắc phân bổ instance.
2. Xác nhận process cũ đã dừng hoàn toàn hoặc được phép bị thay thế. Kiểm tra pod/process state, termination grace period và node/network partition.
3. Sửa nguồn cấu hình để mỗi member có ID duy nhất. Không chỉ sửa runtime của một pod nếu ConfigMap/Helm values hoặc biến môi trường vẫn tạo ra ID trùng ở lần rollout tiếp theo.
4. Nếu một logical member được khởi động lại, chỉ cho phép một process sở hữu ID đó tại một thời điểm. Đảm bảo orchestrator không chạy song song hai pod cùng ordinal/danh tính ngoài chủ đích.
5. Khởi động lại hoặc rollout có kiểm soát sau khi cấu hình đã sửa. Theo dõi log để xác nhận `FencedInstanceIdException` không tái diễn.
6. Xác nhận group trở lại `Stable`, partition được cấp đúng và lag bắt đầu phục hồi.

Nếu không cần static membership hoặc không thể bảo đảm ID ổn định/duy nhất, cân nhắc bỏ cấu hình `group.instance.id` để dùng dynamic membership. Kafka sẽ cấp member identity động; các lần member tham gia/rời group vẫn có thể gây rebalance nhưng không còn duplicate static ID theo cách này. Việc chuyển đổi cần rollout đồng bộ và đánh giá ảnh hưởng tới rebalance.

Không chỉ tăng `session.timeout.ms` để xử lý duplicate ID. Timeout dài hơn có thể kéo dài thời gian coordinator giữ member cũ sau khi mất kết nối; nó không làm hai process dùng cùng ID trở nên hợp lệ.

### 5. Nếu lỗi là `ProducerFencedException`

Chuyển sang nhánh này khi stack trace cho thấy transactional producer bị fence. Kiểm tra:

- Ứng dụng có bật transaction qua `spring.kafka.producer.transaction-id-prefix`, `KafkaTransactionManager`, `KafkaTemplate.executeInTransaction` hoặc cấu hình EOS không.
- Các pod/replica có dùng cùng `transactionIdPrefix` hay không.
- Mỗi producer instance có transactional ID/suffix duy nhất không.
- Một producer cũ có tiếp tục hoạt động sau khi instance mới khởi tạo với cùng transactional ID không.
- Có nhiều application deployment dùng cùng prefix trong cùng cluster không.

Ví dụ cấu hình prefix theo instance:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: "orders-${HOSTNAME}-"
```

Prefix phải duy nhất giữa các application instance có producer transaction đồng thời. Spring Kafka dùng prefix để tạo transactional ID cho producer; kiểm tra cơ chế suffix và cache của đúng phiên bản đang dùng. Không cấu hình một prefix literal giống nhau cho tất cả replica nếu các instance có thể tạo producer đồng thời.

Sau khi sửa:

1. Xác nhận không còn hai instance dùng chung transactional ID.
2. Dừng hoặc loại bỏ producer instance cũ theo quy trình deployment.
3. Tạo producer mới với prefix/ID hợp lệ.
4. Theo dõi lỗi begin/send/commit transaction, transaction abort và log fencing.
5. Kiểm tra cả kết quả publish lẫn offset của consumer để xác nhận luồng consume-process-produce vẫn nhất quán.

Không đổi `group.instance.id` để chữa `ProducerFencedException`. Hai danh tính này thuộc hai cơ chế khác nhau.

### 6. Kiểm tra rollout và orchestration

Nếu fencing trùng thời điểm deploy hoặc scale, kiểm tra:

- Rolling update có cho phép pod cũ và pod mới cùng chạy với một identity không.
- `maxSurge`, `maxUnavailable`, termination grace period và preStop hook có phù hợp không.
- Ứng dụng có đóng listener container và Kafka client đúng cách khi nhận SIGTERM không.
- Có node partition hoặc pod bị treo khiến orchestrator không xác định được process cũ đã kết thúc không.
- StatefulSet ordinal, volume identity, hostname và cấu hình static member có nhất quán không.
- Autoscaler có tạo nhiều replica hơn dự kiến hoặc dao động liên tục không.

Với static membership, thiết kế rollout sao cho không có hai process cùng lúc nhận một `group.instance.id`. Có thể cần điều chỉnh chiến lược rollout hoặc giới hạn surge cho workload đó. Chỉ dùng `maxSurge: 0` hay một chính sách cụ thể sau khi đánh giá yêu cầu availability và khả năng dừng member; đây không phải cấu hình chung cho mọi ứng dụng.

Nếu hệ thống cần thay thế nhanh một member nhưng process cũ có thể còn sống do network partition, fencing instance cũ là hành vi bảo vệ dự kiến. Xử lý nguyên nhân khiến process cũ không dừng hoặc không mất quyền truy cập, rồi xác nhận instance mới là owner duy nhất.

## Cấu hình và quyết định vận hành

### Khi nào nên dùng static membership

Static membership hữu ích khi member có danh tính ổn định và thường xuyên restart ngắn hạn, ví dụ workload có ordinal cố định. Nó có thể tránh rebalance trong một số lần restart khi member quay lại trước khi session timeout hết hạn.

Chỉ bật khi đáp ứng được các điều kiện:

- Mỗi logical member có ID duy nhất trong phạm vi group.
- ID ổn định qua lần restart của cùng logical member.
- Orchestrator ngăn hai process đồng thời sử dụng cùng ID ngoài tình huống failover có chủ đích.
- Có quy trình rollout, shutdown và thay thế member rõ ràng.
- Đội vận hành hiểu rằng member cũ có thể được giữ trong group cho tới khi hết session timeout.

Nếu các điều kiện này không được đảm bảo, dynamic membership thường đơn giản và dễ vận hành hơn.

### Khi nào cần xem xét session timeout

`session.timeout.ms` kiểm soát khoảng thời gian coordinator chờ member heartbeat trong classic group protocol. Với static member, timeout cũng ảnh hưởng thời gian member cũ được giữ lại khi tạm thời mất kết nối. Điều chỉnh giá trị này chỉ sau khi đã xem xét:

- Thời gian restart và thời gian khởi động lại ứng dụng.
- Độ trễ mạng, heartbeat và các khoảng dừng JVM.
- Thời gian failover mà hệ thống chấp nhận.
- Broker-side min/max session timeout.
- Group protocol và phiên bản Kafka client/broker.

Giá trị quá lớn có thể làm group chờ lâu khi member thực sự chết; giá trị quá nhỏ có thể khiến member bị loại trong các khoảng gián đoạn ngắn. Với group protocol mới, cách quản lý heartbeat/session có thể khác classic protocol; xác nhận tài liệu đúng phiên bản trước khi cấu hình.

## Xác nhận sau khi khắc phục

Theo dõi ít nhất qua một chu kỳ restart/rollout hoặc khoảng thời gian đủ dài để bao phủ tình huống đã gây lỗi. Xác nhận:

- Không còn `FencedInstanceIdException` hoặc `ProducerFencedException` tương ứng với lỗi đã xử lý.
- Mỗi `group.instance.id` đang hoạt động là duy nhất trong consumer group.
- Nếu dùng transaction, transactional ID/prefix được cấp riêng cho từng application instance.
- Consumer group giữ trạng thái `Stable`; member count và partition assignment đúng với replica/concurrency dự kiến.
- Listener container tiếp tục poll và xử lý record; không dừng ngoài dự kiến sau khi fencing.
- Consumer lag giảm hoặc ổn định ở mức chấp nhận được; throughput và độ trễ phục hồi.
- Không có lỗi commit hoặc transaction abort bất thường.
- Kết quả nghiệp vụ và dữ liệu đầu ra nhất quán; xử lý lại record (nếu có) không tạo tác dụng phụ trùng ngoài thiết kế.
- Một lần restart hoặc rollout thử nghiệm không làm phát sinh duplicate identity.

Ghi lại cấu hình identity cuối cùng, cách tạo ID theo pod/child container, số replica/concurrency, phiên bản Kafka/Spring Kafka, thời điểm rollout và metric trước/sau. Lưu lại log fencing ban đầu cùng bằng chứng xác nhận đã khắc phục.

## Khi nào cần chuyển cấp

Chuyển cấp cho đội Kafka/platform khi:

- `FencedInstanceIdException` vẫn lặp lại dù ứng dụng xác nhận ID duy nhất và chỉ có một process cho mỗi logical member.
- Nhiều consumer group hoặc nhiều service cùng bị fencing bất thường.
- Broker/coordinator có lỗi liên quan tới group membership, session hoặc coordinator failover.
- Không xác định được member đang giữ static identity do network partition hoặc node không thể truy cập.
- Cần thay đổi group protocol, broker-level timeout, transactional topology hoặc chính sách rollout dùng chung.

Chuyển cấp cho đội ứng dụng khi:

- `ProducerFencedException` xuất phát từ `transactional.id`/`transactionIdPrefix` trùng giữa các instance.
- Cấu hình Spring Boot, `ConsumerFactory`, listener container factory hoặc producer factory tạo identity sai.
- Container dừng hoặc không khởi động lại theo hành vi được mong đợi sau fencing.

Khi chuyển cấp, đính kèm cluster/environment, group ID, topic, exception đầy đủ, timestamp và timezone, Kafka broker/client version, Spring Kafka version, group protocol, `group.instance.id`, `client.id`, transactional ID/prefix (nếu có), pod/host/process start time, replica/concurrency, trạng thái group, log consumer/coordinator và các thay đổi deployment gần nhất. Che thông tin nhạy cảm trong log/config trước khi chia sẻ.

## Checklist thao tác nhanh

- [ ] Lấy exception gốc và phân biệt `FencedInstanceIdException` với `ProducerFencedException`.
- [ ] Ghi lại cluster, group ID, topic, client ID, pod/host và timestamp.
- [ ] Chụp trạng thái group, member, assignment và lag.
- [ ] Tìm mọi cấu hình `group.instance.id` trong ứng dụng, container factory và môi trường triển khai.
- [ ] Xác nhận không có hai process/child container dùng cùng static member ID.
- [ ] Kiểm tra rollout, restart, StatefulSet/Deployment, autoscaling và shutdown lifecycle.
- [ ] Nếu là producer fencing, xác nhận `transactional.id`/`transactionIdPrefix` duy nhất giữa các instance.
- [ ] Sửa nguồn cấu hình identity, rồi rollout có kiểm soát.
- [ ] Xác nhận group ổn định, container tiếp tục poll, lag phục hồi và transaction/offset đúng.
- [ ] Ghi lại cấu hình, bằng chứng trước/sau và chuyển cấp nếu fencing vẫn tái diễn.
