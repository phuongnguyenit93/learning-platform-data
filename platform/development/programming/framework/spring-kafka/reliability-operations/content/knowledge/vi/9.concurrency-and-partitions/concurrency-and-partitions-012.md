# Kiểm tra assignment sau deployment

Sau khi triển khai một phiên bản mới của dịch vụ Spring Kafka, cần xác nhận các consumer instance đã tham gia đúng consumer group và nhận đúng partition. Pod ở trạng thái `Running` hoặc `Ready` chưa chứng minh consumer đã được Kafka gán partition. Tương tự, số replica đang chạy không cho biết chính xác số consumer member hoặc cách partition được phân phối.

Kiểm tra assignment sau deployment giúp phát hiện sớm các lỗi như group ID bị thay đổi, concurrency không được áp dụng, số consumer vượt số partition, một số consumer không nhận partition, rebalance kéo dài hoặc một partition bị dồn tải. Việc kiểm tra nên kết hợp trạng thái deployment, trạng thái consumer group ở Kafka, log từ Spring Kafka và consumer lag.

## 1. Hiểu assignment cần kiểm tra

Kafka gán partition cho consumer member trong một consumer group. Với một topic và một group, mỗi partition được gán cho tối đa một member tại một thời điểm. Một member có thể nhận nhiều partition; một member cũng có thể chưa được gán partition nào.

Ví dụ topic `orders` có sáu partition và dịch vụ chạy ba replica, mỗi replica có một consumer:

```text
Deployment: order-service
Replicas: 3
Listener concurrency: 1
Group ID: order-service

Consumer A -> orders-0, orders-1
Consumer B -> orders-2, orders-3
Consumer C -> orders-4, orders-5
```

Assignment trên chỉ là ví dụ. Kafka có thể phân phối khác tùy partition assignor, subscription và thành viên hiện có. Điều cần xác nhận là mọi partition mong đợi đều được group sở hữu, không có partition bị gán trùng trong cùng group và tải được phân bố phù hợp.

Trong Spring Kafka, cần phân biệt:

- **Replica:** một process hoặc pod của ứng dụng.
- **Listener concurrency:** số consumer container con được tạo cho một listener endpoint trong mỗi process.
- **Consumer member:** một Kafka consumer tham gia group. Một listener có thể tạo nhiều member khi concurrency lớn hơn một.
- **Partition assignment:** tập partition mà Kafka giao cho từng member.

Với một listener endpoint dùng chung group ID, số member dự kiến thường được ước lượng bằng:

```text
expected members = số replica × listener concurrency
```

Đây là số member dự kiến khi tất cả replica và child container đều khởi động thành công. Nếu ứng dụng có nhiều listener endpoint, mỗi endpoint có thể có group ID, subscription và concurrency riêng; không cộng tất cả listener vào một con số nếu chúng không thuộc cùng group.

## 2. Xác nhận deployment đã hoàn tất

Trước khi kiểm tra Kafka, xác nhận Kubernetes đã triển khai xong phiên bản mong muốn. Ví dụ:

```bash
kubectl rollout status deployment/order-service
kubectl get deployment order-service
kubectl get pods -l app=order-service -o wide
```

Kiểm tra các thông tin sau:

- Số replica mong muốn bằng số pod sẵn sàng.
- Các pod đang chạy đúng image/tag mới.
- Không có pod liên tục restart hoặc bị readiness/liveness probe đánh lỗi.
- Các pod cũ đã kết thúc theo chính sách rollout, trừ khi deployment cố ý dùng surge.
- Các biến môi trường và ConfigMap/Secret cung cấp đúng `group.id`, topic và concurrency.

Trong thời gian rolling update, pod mới có thể tham gia group trước khi pod cũ rời group. Số member tạm thời có thể cao hơn số replica cấu hình. Đây là điều bình thường khi deployment dùng `maxSurge`; hãy chờ rollout ổn định rồi mới kết luận assignment cuối cùng.

Có thể xem log từ tất cả pod:

```bash
kubectl logs -l app=order-service --since=10m --prefix=true
```

Tùy phiên bản `kubectl`, tùy chọn `--prefix` có thể khác. Nếu không hỗ trợ, lấy log từng pod bằng tên pod. Khi có nhiều replica, prefix hoặc tên pod giúp xác định log assignment đến từ instance nào.

## 3. Kiểm tra consumer group ở Kafka

Công cụ `kafka-consumer-groups` là cách trực tiếp để quan sát trạng thái consumer group và offset. Chạy lệnh từ môi trường có Kafka client và kết nối đến đúng cluster:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --list
```

Xác nhận group ID của dịch vụ có trong danh sách. Sau đó xem trạng thái group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --state
```

Trên các phiên bản Kafka hỗ trợ, lệnh này hiển thị trạng thái group và thông tin coordinator. Trạng thái ổn định thường được hiển thị là `Stable`. Trong quá trình member tham gia hoặc rời group, có thể quan sát các trạng thái chuyển tiếp như `PreparingRebalance` hoặc `CompletingRebalance`. Tên trạng thái và tùy chọn CLI có thể thay đổi theo phiên bản Kafka; kiểm tra `kafka-consumer-groups.sh --help` nếu lệnh không được hỗ trợ.

Một group liên tục ở trạng thái rebalance cần được điều tra. Nguyên nhân có thể là pod restart liên tục, consumer không duy trì heartbeat, vượt `max.poll.interval.ms`, subscription thay đổi hoặc lỗi kết nối. Không nên lấy một lần quan sát đúng lúc deployment đang diễn ra làm kết luận group bị lỗi; hãy kiểm tra lại sau khi rollout kết thúc.

### Xem member và partition assignment

Với các phiên bản hỗ trợ tùy chọn `--members --verbose`, dùng:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose
```

Kết quả thường có các cột tương tự:

| Cột | Ý nghĩa |
|---|---|
| `CONSUMER-ID` | Định danh member hiện tại trong group. Giá trị có thể thay đổi sau khi consumer restart hoặc rebalance. |
| `HOST` | Địa chỉ host mà broker nhìn thấy cho member. |
| `CLIENT-ID` | Client ID dùng để nhận diện consumer trong log và metric. |
| `#PARTITIONS` | Số partition đang được gán cho member. |
| `ASSIGNMENT` | Danh sách topic-partition được gán cho member. |

Đây là bằng chứng trực tiếp để đối chiếu số member và assignment. Không dùng `CONSUMER-ID` làm định danh lâu dài cho pod vì consumer ID có thể thay đổi sau restart. Đối chiếu `HOST`, `CLIENT-ID`, log khởi động và tên pod để tìm đúng instance.

Nếu phiên bản Kafka không hỗ trợ `--members --verbose`, kiểm tra tài liệu của phiên bản đang chạy hoặc dùng Kafka AdminClient để gọi `describeConsumerGroups`. Đừng suy luận assignment chỉ từ số offset trong output mặc định.

### Xem offset và lag

Lệnh mô tả mặc định cho biết committed offset và lag theo partition:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service
```

Các cột thường gặp gồm `TOPIC`, `PARTITION`, `CURRENT-OFFSET`, `LOG-END-OFFSET`, `LAG`, `CONSUMER-ID`, `HOST` và `CLIENT-ID`.

| Cột | Cách đọc |
|---|---|
| `CURRENT-OFFSET` | Committed offset của group cho partition, thường là vị trí kế tiếp cần đọc. |
| `LOG-END-OFFSET` | Mốc cuối log của partition tại thời điểm truy vấn. |
| `LAG` | Chênh lệch offset giữa cuối log và committed offset. Đây là chỉ báo tiến độ, không phải lúc nào cũng bằng chính xác số record nghiệp vụ đang chờ. |
| `CONSUMER-ID` / `HOST` | Member đang sở hữu partition theo trạng thái group được trả về. |

Nếu group vừa mới khởi động hoặc chưa commit offset, một số trường có thể hiển thị `-`. Đừng xem giá trị đó là lag bằng 0. Hãy kiểm tra trạng thái group, member assignment và lần commit đầu tiên.

## 4. Đối chiếu assignment với replicas và concurrency

Giả sử deployment có bốn replica, listener concurrency bằng hai và topic có tám partition:

```text
Expected consumer members = 4 × 2 = 8
Available partitions = 8
```

Group có thể gán một partition cho mỗi member. Nếu topic chỉ có năm partition, tối đa năm member có partition và ba member còn lại sẽ idle đối với topic đó. Điều này không tự động có nghĩa ứng dụng bị lỗi.

| Replica | Concurrency | Member dự kiến | Partition của topic | Kỳ vọng |
|---:|---:|---:|---:|---|
| 2 | 1 | 2 | 6 | Hai member chia sáu partition. |
| 3 | 2 | 6 | 6 | Sáu member có thể nhận một partition mỗi member. |
| 4 | 2 | 8 | 5 | Tối đa năm member nhận partition; ba member idle. |
| 6 | 1 | 6 | 3 | Tối đa ba member nhận partition; ba member idle. |

Với nhiều topic trong cùng subscription, cần tính tổng partition mà group đang tiêu thụ và xem assignment thực tế. Với subscription khác nhau giữa các member, không thể chỉ dùng một phép chia đơn giản để dự đoán chính xác member nào nhận partition nào.

Nếu số member trong Kafka thấp hơn số dự kiến, kiểm tra:

- Có bao nhiêu pod thực sự sẵn sàng và đang chạy đúng phiên bản.
- Listener container có được tạo và khởi động thành công không.
- Giá trị `concurrency` thực tế trên listener endpoint.
- Group ID có giống nhau trên các replica cần chia tải không.
- Có lỗi xác thực, kết nối broker hoặc lỗi subscription trong log không.
- Một số replica có cấu hình khác hoặc endpoint bị disable theo profile không.

Nếu số member cao hơn dự kiến, kiểm tra rollout surge, pod cũ chưa kết thúc, nhiều listener endpoint cùng group và các process chạy ngoài Kubernetes. Đối chiếu member với host/client ID trước khi xóa hoặc restart instance.

## 5. Kiểm tra assignment trong log Spring Kafka

Kafka CLI cho biết trạng thái broker nhìn thấy. Log ứng dụng giúp nối member đó với listener container và pod cụ thể. Có thể bật log phù hợp cho package Spring Kafka trong thời gian điều tra:

```yaml
logging:
  level:
    org.springframework.kafka.listener: INFO
    org.springframework.kafka.core: INFO
```

Mức log cần điều chỉnh theo phiên bản và môi trường. DEBUG hoặc TRACE có thể tạo nhiều log, vì vậy chỉ bật tạm thời khi cần xem chi tiết poll, rebalance hoặc container lifecycle.

Spring Kafka cũng phát các application event liên quan đến partition assignment và revoke. Có thể lắng nghe `ConsumerPartitionAssignedEvent` và `ConsumerPartitionRevokedEvent` để ghi nhận thời điểm partition được giao hoặc thu hồi:

```java
@Component
public class KafkaAssignmentEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaAssignmentEvents.class);

    @EventListener
    public void onAssigned(ConsumerPartitionAssignedEvent event) {
        log.info("Kafka partitions assigned: container={}, partitions={}",
                event.getContainer(), event.getPartitions());
    }

    @EventListener
    public void onRevoked(ConsumerPartitionRevokedEvent event) {
        log.info("Kafka partitions revoked: container={}, partitions={}",
                event.getContainer(), event.getPartitions());
    }
}
```

Các event class thuộc Spring Kafka listener package; kiểm tra API của phiên bản đang dùng khi import hoặc triển khai. Event được phát trong quá trình điều phối consumer, vì vậy handler nên ngắn và tránh gọi database hoặc HTTP đồng bộ. Nếu cần gửi dữ liệu đi nơi khác, hãy đẩy một bản ghi nhỏ sang executor có giới hạn.

Một cách khác là cấu hình `ConsumerAwareRebalanceListener` trên `ContainerProperties` để quan sát callback `onPartitionsAssigned` và `onPartitionsRevoked`. Cách này hữu ích khi cần xử lý logic gắn trực tiếp với vòng đời assignment. Dù dùng application event hay rebalance listener, hãy giữ log đủ thông tin để liên hệ container với pod, group ID và thời điểm deployment.

Ví dụ log nên có các trường:

```text
event=partitions_assigned
application=order-service
pod=order-service-7c9f8b9d6f-abc12
group=order-service
partitions=orders-0,orders-1
```

Tên pod và group ID thường cần được đưa vào MDC hoặc cấu hình logging từ môi trường. `ConsumerPartitionAssignedEvent` cung cấp container và partition; ứng dụng cần bổ sung metadata deployment nếu muốn log có thể tìm kiếm theo pod.

## 6. Phân biệt assignment với khả năng xử lý dữ liệu

Một consumer có assignment không có nghĩa nó đang xử lý record thành công. Assignment chỉ cho biết Kafka đã giao partition cho member. Sau đó cần xác nhận consumer vẫn poll, listener hoàn tất công việc, offset tiến lên và lag không tăng bất thường.

Kiểm tra đồng thời:

- Group ở trạng thái ổn định sau deployment.
- Mỗi partition mong đợi xuất hiện trong assignment của group.
- Không có partition bị gán cho nhiều member trong cùng group.
- Các member được ánh xạ tới đúng pod và listener endpoint.
- `CURRENT-OFFSET` tiến lên khi có dữ liệu mới.
- `LAG` ổn định hoặc giảm theo tải dự kiến.
- Log không có lỗi deserialize, listener exception, commit failure hoặc poll timeout lặp lại.
- Metric throughput và thời gian xử lý phù hợp với baseline.

Nếu assignment đúng nhưng lag tăng, có thể consumer xử lý chậm hơn tốc độ producer, partition bị lệch tải hoặc dependency bị nghẽn. Nếu assignment thiếu, tập trung vào membership, subscription và rebalance trước. Nếu offset không tiến lên nhưng lag thấp, có thể topic đang không có dữ liệu mới; hãy xác nhận bằng log producer hoặc log end offset.

## 7. Kiểm tra khi có partition không được gán

Partition không xuất hiện trong assignment có thể là dấu hiệu group chưa hoàn tất rebalance, subscription không bao gồm topic đó hoặc group đang ở trạng thái không hoạt động. Hãy kiểm tra theo thứ tự:

1. Xác nhận topic và partition tồn tại trong cluster đang truy vấn.
2. Xác nhận đúng group ID và member subscription.
3. Chờ rebalance hoàn tất rồi chạy lại `--state` và `--members --verbose`.
4. Đối chiếu assignment của toàn bộ member để tìm partition bị thiếu.
5. Kiểm tra log consumer về lỗi subscribe, authorization, metadata hoặc rebalance.
6. Xem partition có bị pause bởi ứng dụng hoặc listener container hay không.

Một partition bị pause vẫn có thể thuộc assignment của consumer. Pause làm container tạm ngừng giao record từ partition đó cho listener, nhưng không đồng nghĩa partition đã được chuyển sang member khác. Hãy phân biệt `assigned` với `paused` khi quan sát.

Nếu có nhiều consumer hơn partition, một số member idle là bình thường. Không cần restart các member đó chỉ để buộc mọi pod có partition. Muốn tăng số member có thể làm việc song song, cần tăng partition một cách có chủ đích và đánh giá ảnh hưởng đến key ordering, dữ liệu hiện tại và hệ thống phụ thuộc.

## 8. Điều tra rebalance sau deployment

Deployment có thể tạo rebalance khi pod mới tham gia và pod cũ dừng. Một lần rebalance trong rollout là bình thường; rebalance lặp liên tục sau khi rollout hoàn tất là dấu hiệu cần điều tra.

Các nguyên nhân phổ biến:

| Nguyên nhân | Dấu hiệu cần tìm |
|---|---|
| Pod restart hoặc crash loop | Pod restart count tăng, log startup/shutdown lặp lại. |
| Consumer không gọi `poll()` đúng hạn | Log poll timeout hoặc vượt `max.poll.interval.ms`; listener xử lý lâu hoặc retry đồng bộ. |
| Mất heartbeat hoặc kết nối | Log heartbeat/session timeout, broker/network error. |
| Group ID hoặc subscription thay đổi | Member đăng ký group khác hoặc subscription topic khác giữa các replica. |
| Rolling update tạo nhiều member tạm thời | Số member tăng trong rollout rồi giảm khi pod cũ kết thúc. |
| Static member ID bị trùng | Log fencing hoặc xung đột `group.instance.id`. |

Đối chiếu timestamp giữa Kubernetes events, pod restart, Spring Kafka assignment/revoke events và Kafka group state. Nếu group chỉ chuyển trạng thái trong vài giây khi rollout rồi ổn định, đó có thể là hành vi dự kiến. Nếu group liên tục rời `Stable`, tìm nguyên nhân làm member thay đổi membership.

Với static membership, `group.instance.id` phải duy nhất cho từng member trong cùng group. Nếu mọi replica dùng cùng một ID, chúng có thể loại trừ lẫn nhau hoặc tạo lỗi fencing. Với listener concurrency lớn hơn một, mỗi child consumer cũng cần ID riêng nếu static membership được cấu hình. Hãy kiểm tra cách Spring Kafka của phiên bản đang chạy tạo ID cho child container.

## 9. Một quy trình kiểm tra sau mỗi deployment

Có thể dùng quy trình sau làm checklist vận hành cho dịch vụ `order-service`:

**Bước 1 — Xác nhận phiên bản ứng dụng.** Kiểm tra rollout đã hoàn tất, số replica sẵn sàng đúng và các pod đang chạy cùng image/tag mong muốn.

**Bước 2 — Xác nhận cấu hình listener.** Kiểm tra group ID, topic subscription và concurrency thực tế. Tính số member dự kiến cho từng consumer group.

**Bước 3 — Xác nhận group ổn định.** Dùng `kafka-consumer-groups --describe --group order-service --state`. Nếu group vẫn rebalance, chờ một khoảng hợp lý và xem log trước khi tiếp tục.

**Bước 4 — Xác nhận member và assignment.** Dùng `--members --verbose`, đối chiếu host/client ID với pod và xác nhận các partition mong đợi đã được gán.

**Bước 5 — Xác nhận tiến độ.** Dùng `--describe --group order-service` để xem committed offset, log end offset và lag theo partition. Chạy lại sau một khoảng thời gian để xác định offset có tiến lên hay không.

**Bước 6 — Xác nhận hành vi listener.** Kiểm tra log assignment/revoke, listener exception, commit failure, poll timeout và metric throughput. Đảm bảo không có lỗi lặp lại sau khi group đã ổn định.

**Bước 7 — Lưu bằng chứng triển khai.** Ghi lại image/tag, thời gian kiểm tra, group ID, số member, assignment, lag và cảnh báo còn tồn tại. Những dữ liệu này giúp so sánh khi triển khai lần sau.

## 10. Ví dụ lệnh kiểm tra tổng hợp

Với cluster thử nghiệm không bật xác thực, có thể chạy:

```bash
# 1. Xem trạng thái group
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --state

# 2. Xem từng consumer member và assignment
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --members \
  --verbose

# 3. Xem offset và lag theo partition
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service
```

Với cluster bật SASL hoặc TLS, thêm `--command-config client.properties` theo cấu hình bảo mật của môi trường. Không đưa password hoặc secret trực tiếp vào command history; dùng file cấu hình được bảo vệ theo chính sách vận hành.

Nếu cần kiểm tra trên Windows, Kafka distribution thường cung cấp script `.bat` tương ứng, ví dụ `kafka-consumer-groups.bat`. Tùy phiên bản Kafka, tên script và các cờ được hỗ trợ có thể khác.

## 11. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Pod Ready nhưng không có member trong group | Listener container chưa start, group ID khác, lỗi kết nối hoặc authorization. | Kiểm tra log container, group ID, bootstrap servers và quyền đọc topic/group. |
| Member có mặt nhưng assignment rỗng | Số member lớn hơn partition, subscription không khớp hoặc group đang chuyển trạng thái. | Kiểm tra partition count, subscription và trạng thái group sau rebalance. |
| Số member cao hơn phép tính replica × concurrency | Rolling update surge, pod cũ chưa rời group, nhiều endpoint hoặc process khác dùng cùng group. | Đối chiếu host/client ID với pod và listener endpoint. |
| Partition bị thiếu trong assignment | Topic subscription sai, group chưa ổn định hoặc partition chưa được cập nhật metadata. | Kiểm tra topic, subscription, trạng thái group và log metadata. |
| Assignment đúng nhưng lag tăng | Consumer chậm, partition nóng hoặc dependency bị nghẽn. | Đo throughput, listener latency, retry, batch size và lag từng partition. |
| Rebalance lặp sau deploy | Pod restart, poll timeout, heartbeat failure hoặc static member ID trùng. | Đối chiếu timestamp log, cấu hình timeout và `group.instance.id`. |
| Consumer member thay đổi ID sau mỗi deploy | Consumer ID thường không ổn định qua restart. | Dùng host/client ID và log deployment để đối chiếu; không phụ thuộc consumer ID cố định. |

## 12. Nguyên tắc vận hành

- Kiểm tra trạng thái deployment và group sau khi rollout hoàn tất; không kết luận từ thời điểm group đang rebalance.
- Dùng đúng cluster và group ID khi chạy Kafka CLI.
- Đối chiếu số replica, listener concurrency và số member thực tế.
- Kiểm tra assignment theo từng member, không chỉ nhìn tổng số consumer.
- Xem offset và lag theo từng partition để xác nhận consumer thực sự tiến triển.
- Dùng log assignment/revoke của Spring Kafka để nối partition với pod và container.
- Phân biệt member idle hợp lệ khi consumer nhiều hơn partition với lỗi subscription hoặc group membership.
- Điều tra rebalance lặp bằng timestamp từ Kubernetes, ứng dụng và Kafka.
- Không dùng consumer ID làm định danh bền vững của pod; dùng metadata deployment và client/host để đối chiếu.
- Lưu bằng chứng assignment và lag sau deployment để làm baseline cho lần phát hành tiếp theo.

Kiểm tra assignment sau deployment cần xác nhận cả membership, phân phối partition và tiến độ xử lý. Khi kết hợp Kafka consumer group CLI, trạng thái Kubernetes và log Spring Kafka, đội vận hành có thể xác định replica nào đang tiêu thụ partition nào, phát hiện consumer idle ngoài dự kiến và tìm ra nguyên nhân rebalance trước khi ảnh hưởng kéo dài đến throughput hoặc độ tin cậy của dịch vụ.
