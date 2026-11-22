# Runbook, phân quyền thao tác và kiểm tra sau thay đổi

Vận hành Kafka cluster không chỉ là chạy lệnh quản trị. Mỗi thay đổi có thể ảnh hưởng đồng thời đến availability, durability, ordering, consumer lag và khả năng phục hồi. Restart broker sai thứ tự có thể làm partition mất ISR; reassignment quá nhanh có thể làm nghẽn network và disk; thay ACL nhầm có thể chặn producer hoặc mở quyền đọc dữ liệu; thao tác nhầm trên KRaft metadata quorum có thể làm cluster mất khả năng bầu controller.

Runbook giúp operator thực hiện thay đổi theo một trình tự có thể kiểm tra và lặp lại: xác định phạm vi, phân quyền đúng người, thu thập baseline, đánh giá blast radius, thực hiện từng bước, quan sát trong quá trình, xác minh kết quả và rollback hoặc dừng khi có dấu hiệu bất thường. Bài này tập trung vào vận hành cluster Kafka ở môi trường có KRaft, gồm kiểm tra sức khỏe, rolling restart, thay đổi topic/config/ACL, partition reassignment, bảo trì broker/controller và quy trình sau thay đổi.

## 1. Mục tiêu và nguyên tắc vận hành

Một thao tác vận hành chỉ hoàn tất khi hệ thống đã trở lại trạng thái ổn định và có bằng chứng xác minh. Lệnh trả exit code 0 chưa đủ chứng minh thay đổi thành công; cần kiểm tra trạng thái cluster, partition, consumer và ứng dụng sau thao tác.

Nguyên tắc cơ bản:

1. **Least privilege:** tài khoản chỉ có quyền cần thiết cho nhiệm vụ và trong thời gian cần thiết.
2. **Separation of duties:** người yêu cầu, người phê duyệt và người thực hiện được phân vai rõ ràng với thay đổi có rủi ro.
3. **One change at a time:** thay đổi từng broker, từng controller hoặc từng nhóm partition có kiểm soát.
4. **Baseline before change:** lưu trạng thái trước thay đổi để so sánh.
5. **Observe before proceeding:** chỉ sang bước tiếp theo khi health checks đạt.
6. **Rollback is a planned action:** ghi rõ điều kiện dừng, cách khôi phục và giới hạn rollback trước khi chạy.
7. **Audit everything:** lưu người thực hiện, thời điểm, lệnh, kết quả, phê duyệt và ticket.
8. **Protect metadata and data:** bảo vệ cả dữ liệu record, credential, ACL, KRaft metadata và bản sao lưu.

Không chạy nhiều thao tác rủi ro cùng lúc chỉ để rút ngắn maintenance window. Kafka có replication nhưng replication không thay thế kế hoạch bảo trì.

## 2. Phân loại thay đổi và blast radius

Đánh giá thay đổi theo số resource bị ảnh hưởng, khả năng mất availability, khả năng mất dữ liệu và độ khó khôi phục.

| Mức | Ví dụ | Kiểm soát tối thiểu |
|---|---|---|
| Thấp | Describe topic, xem consumer group, đọc metrics | Operator read-only, ghi nhận kết quả |
| Trung bình | Thêm ACL cho một service, đổi quota/config động của một topic | Change ticket, peer review, snapshot cấu hình cũ, kiểm tra sau thay đổi |
| Cao | Tăng partition, reassignment, thay đổi retention/cleanup policy, rolling restart | Phê duyệt owner, đánh giá tác động, maintenance window, baseline, rollback/forward plan |
| Rất cao | Thay controller quorum, thay broker identity/storage, nâng cấp major version, khôi phục metadata | Phê duyệt cấp cao, runbook đã diễn tập, backup/restore plan, operator chuyên trách và giám sát liên tục |

Blast radius cần trả lời:

- Những topic, partition, consumer group, principal và ứng dụng nào bị ảnh hưởng?
- Có bao nhiêu replica sẽ di chuyển hoặc tạm thời offline?
- ISR có thể giảm dưới min.insync.replicas không?
- Thay đổi có làm thay đổi partition mapping hoặc ordering theo key không?
- Có ảnh hưởng controller quorum, broker registration hoặc metadata log không?
- Có tạo tải tăng thêm trên disk, network, CPU, controller hay KMS không?
- Nếu thao tác dừng giữa chừng, cluster ở trạng thái nào và bước tiếp theo là gì?

## 3. Vai trò và phân quyền thao tác

Không dùng một tài khoản admin chung cho mọi người và mọi ứng dụng. Phân tách quyền quản trị cluster khỏi quyền đọc/ghi dữ liệu ứng dụng.

| Vai trò | Trách nhiệm | Quyền phù hợp |
|---|---|---|
| Requester / service owner | Nêu mục tiêu, topic/group và thời gian cần thay đổi | Không tự cấp quyền cluster |
| Change approver | Đánh giá rủi ro, cửa sổ bảo trì và rollback | Phê duyệt quy trình, không nhất thiết có quyền chạy lệnh |
| Kafka operator | Thực hiện thao tác cluster đã phê duyệt | Quyền Admin/Alter đúng resource và thời hạn |
| Security operator | Quản lý principal, credential, ACL và certificate | Quyền thay đổi bảo mật; không mặc định đọc payload |
| Application owner | Kiểm tra producer/consumer và nghiệp vụ | Quyền ứng dụng trên topic/group của mình |
| Observer / auditor | Theo dõi và kiểm tra bằng chứng | Read-only metrics, metadata và audit log |
| Break-glass administrator | Xử lý sự cố nghiêm trọng | Quyền cao có kiểm soát, phê duyệt khẩn cấp và audit đầy đủ |

Quy tắc:

- Mỗi service có principal riêng; không chia sẻ credential giữa producer, consumer và operator.
- Producer chỉ có WRITE/DESCRIBE trên topic cần gửi.
- Consumer chỉ có READ/DESCRIBE trên topic và READ trên group cần dùng.
- DLT recovery principal được cấp quyền riêng trên DLT; không mặc định đọc mọi topic.
- Với idempotent producer khi authorizer yêu cầu, cấp thêm quyền IdempotentWrite trên Cluster resource cho đúng principal; không cấp quyền quản trị cluster chỉ để bật idempotence.
- Operator dùng tài khoản cá nhân có MFA/SSO ở lớp truy cập quản trị nếu nền tảng hỗ trợ.
- Credential có thời hạn, được rotate và thu hồi khi nhân sự/service không còn cần quyền.
- Không đặt mật khẩu trong command line, shell history, ticket hoặc log.
- Quyền break-glass phải có thời gian hết hạn và được rà soát sau khi dùng.

ACL của Kafka kiểm soát quyền theo resource như topic, group, cluster và transactional ID. ACL không giới hạn field trong một record. Nếu consumer có READ trên topic, hãy giả định consumer có thể đọc toàn bộ key, value và headers của record trong topic đó.

## 4. Quy trình change management

Mỗi thay đổi cần một bản ghi đủ để người khác hiểu điều gì sẽ được làm và cách xác định thành công.

### 4.1. Change request

Ghi rõ:

- Mã ticket, người yêu cầu, owner nghiệp vụ và người phê duyệt.
- Cluster/environment, broker ID, controller role, topic, partition hoặc principal liên quan.
- Trạng thái hiện tại và mục tiêu mong muốn.
- Lý do thay đổi và tác động nếu không thực hiện.
- Blast radius và rủi ro durability/availability/security.
- Cửa sổ thực hiện, thời gian dự kiến và kênh liên lạc sự cố.
- Các bước thực hiện, health gate giữa các bước.
- Điều kiện dừng, rollback hoặc forward recovery.
- Người xác minh sau thay đổi và bằng chứng cần lưu.

### 4.2. Trước khi thực hiện

1. Xác nhận đúng cluster và môi trường.
2. Xác nhận change ticket đã được phê duyệt.
3. Kiểm tra không có incident hoặc maintenance khác đang diễn ra.
4. Thu thập health baseline.
5. Lưu cấu hình/topic/ACL/reassignment state có liên quan.
6. Kiểm tra dung lượng disk, network, CPU và khả năng nhận thêm replica.
7. Kiểm tra replication factor, ISR và min.insync.replicas của topic bị ảnh hưởng.
8. Xác nhận owner ứng dụng biết thời gian và hành vi dự kiến.
9. Chuẩn bị lệnh, file JSON/properties và checksum của file đầu vào.
10. Mở dashboard/log theo dõi trước khi bắt đầu.

### 4.3. Trong khi thực hiện

- Thực hiện đúng thứ tự đã phê duyệt.
- Ghi timestamp và kết quả từng bước.
- Không chạy bước kế tiếp nếu health gate chưa đạt.
- Theo dõi offline partition, under-replicated partition, ISR shrink, request latency, disk/network và consumer lag.
- Dừng nếu metric vượt ngưỡng hoặc xuất hiện lỗi mới chưa giải thích được.
- Không chỉnh thêm tham số ngoài change request để chữa một lỗi phụ mà chưa đánh giá blast radius.

### 4.4. Sau khi thực hiện

- Chạy đầy đủ post-change checks ở phần 7.
- So sánh với baseline trước thay đổi.
- Xác nhận producer/consumer và nghiệp vụ đầu cuối.
- Xác nhận không còn reassignment hoặc operation nền ngoài dự kiến.
- Lưu output, metrics snapshot, log, ACL/config diff và thời gian hoàn tất.
- Thông báo kết quả cho owner qua quy trình nội bộ.
- Đóng ticket hoặc mở follow-up nếu còn việc tồn đọng.

## 5. Baseline health checks trước mọi thay đổi

Các lệnh dưới đây là ví dụ cho Kafka CLI dạng Unix shell. Dùng đúng script extension và đường dẫn của bản cài đặt; trên Windows có thể dùng file .bat tương ứng. Mọi lệnh quản trị cần truyền file command config được bảo vệ khi cluster yêu cầu TLS/SASL.

Khai báo biến môi trường trong shell vận hành:

~~~bash
export BS='kafka-1.example.internal:9093'
export ADMIN_CFG='/run/secrets/kafka-admin.properties'
~~~

Kiểm tra broker phản hồi API:

~~~bash
kafka-broker-api-versions.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG"
~~~

Kiểm tra metadata quorum KRaft:

~~~bash
kafka-metadata-quorum.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  describe --status

kafka-metadata-quorum.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  describe --replication
~~~

Kiểm tra topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --describe --topic orders.events
~~~

Kiểm tra consumer group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --describe --group orders-service
~~~

Kiểm tra cấu hình topic:

~~~bash
kafka-configs.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --entity-type topics \
  --entity-name orders.events \
  --describe
~~~

Ghi nhận ít nhất:

| Nhóm | Baseline cần lưu |
|---|---|
| Broker | Broker ID, listener, version, trạng thái API và log lỗi |
| KRaft | Active controller, leader ID, voters, high watermark và lag replication |
| Partition | Leader, replicas, ISR, offline partitions, under-replicated partitions |
| Consumer | Group state, member, assignment, current offset, log end offset, lag |
| Storage | Disk usage theo broker/log directory, tốc độ tăng dữ liệu |
| Runtime | CPU, heap, GC pause, network throughput, request handler idle |
| Application | Producer error/retry, send latency, consumer processing latency và lag |

Một cluster có thể trả lời CLI nhưng vẫn không khỏe: ví dụ ISR đang shrink, consumer lag tăng, disk gần đầy hoặc controller metadata replication bị tụt. Không chỉ kiểm tra broker process còn sống.

## 6. Health gate: điều kiện được phép tiếp tục

Đặt ngưỡng cụ thể theo SLA và baseline của cluster. Các tiêu chí tối thiểu thường gồm:

- Không có offline partition.
- Under-replicated partition bằng 0 hoặc đã được giải thích và chấp nhận trong change plan.
- ISR của các partition bị ảnh hưởng đáp ứng min.insync.replicas.
- Controller quorum có leader và đủ voter majority; metadata replication không tăng lag bất thường.
- Không có broker mất kết nối hoặc log directory offline ngoài kế hoạch.
- Disk còn đủ headroom cho retention, segment roll, reassignment và recovery.
- Producer error/retry và request latency không tăng vượt ngưỡng.
- Consumer lag ổn định hoặc giảm; không tăng liên tục ngoài dự kiến.
- Không có dấu hiệu GC pause, CPU throttling hoặc network saturation mới.

Nếu một health gate không đạt, dừng thao tác tại điểm an toàn gần nhất. Ghi lại trạng thái hiện tại trước khi quyết định rollback hoặc forward recovery.

## 7. Post-change checks dùng chung

Sau mọi thay đổi, kiểm tra theo cùng một bộ tiêu chí và so sánh với baseline.

| Hạng mục | Cách kiểm tra | Điều kiện đạt |
|---|---|---|
| Broker availability | broker API, logs, controller view | Broker dự kiến đều đăng ký và phản hồi |
| KRaft quorum | metadata quorum status/replication | Có leader, đủ voters, replication catch up |
| Partition health | topic describe, JMX metrics | Không có offline partition; ISR ổn định |
| Replica health | under-replicated partitions, ISR | Replica bắt kịp và không tiếp tục shrink |
| Producer | send rate, error rate, retry, latency | Không có lỗi mới; p95/p99 trong ngưỡng |
| Consumer | group describe, lag, processing rate | Group ổn định; lag theo kế hoạch |
| Storage | disk usage, log directory errors | Đủ dung lượng và không có I/O error |
| Security | ACL describe/list, authentication logs | Principal có đúng quyền mong muốn |
| Business flow | gửi/nhận event kiểm thử có kiểm soát | Event đến đúng consumer và nghiệp vụ xác nhận |
| Change record | diff, command output, metrics snapshot | Đủ bằng chứng và người xác minh |

Không dùng event kiểm thử chứa dữ liệu thật hoặc gửi vào topic production nếu change plan chưa chỉ rõ cách cô lập và xóa dữ liệu kiểm thử.

## 8. Runbook A: rolling restart broker

Rolling restart thường dùng khi thay cấu hình tĩnh, cập nhật JVM/bản vá hệ điều hành hoặc nâng cấp broker theo quy trình tương thích phiên bản.

### Điều kiện trước khi bắt đầu

- Có maintenance window và owner ứng dụng đã được thông báo.
- Cluster đang khỏe, không có offline partition và ISR đã ổn định.
- Không có reassignment, rolling restart hoặc upgrade khác đang chạy.
- Đã xác nhận replication factor và ISR của partition đặt trên broker mục tiêu.
- Có đủ broker khỏe để tiếp tục phục vụ replica và request.
- Với broker kết hợp controller trong KRaft, đánh giá cả tác động tới quorum; không áp dụng runbook broker-only một cách máy móc.

Nếu topic có replication factor bằng 1, partition đặt trên broker đang restart sẽ không có replica thay thế để tiếp tục phục vụ. Phải chấp nhận downtime trong change plan hoặc tăng replication factor trước theo một thay đổi riêng đã được kiểm tra.

### Thực hiện từng broker

1. Chọn một broker theo thứ tự đã được phê duyệt.
2. Xác nhận partition leader trên broker có replica ISR khỏe ở broker khác.
3. Nếu cần giảm leadership movement, dùng preferred leader election theo kế hoạch và theo dõi tải.
4. Dừng broker theo service manager/orchestrator chuẩn của môi trường.
5. Chờ broker process dừng sạch; kiểm tra log để xác định shutdown hoàn tất.
6. Thực hiện thay đổi đã phê duyệt, ví dụ cập nhật package hoặc cấu hình.
7. Khởi động broker và theo dõi startup log, registration và network listener.
8. Kiểm tra broker xuất hiện lại, log directory online và replica bắt đầu catch up.
9. Chờ under-replicated partition trở về baseline và ISR ổn định.
10. Chỉ sau khi health gate đạt mới chuyển sang broker tiếp theo.

### Dấu hiệu phải dừng

- Broker không register lại hoặc liên tục crash.
- Offline partition xuất hiện.
- ISR giảm ngoài dự kiến hoặc không phục hồi.
- Controller quorum mất majority hoặc không có leader.
- Disk/network/request latency vượt ngưỡng.
- Consumer lag tăng nhanh và không có xu hướng hồi phục.

Không restart broker thứ hai chỉ vì broker đầu tiên đã mở port. Cần chờ replica catch up và cluster trở lại health gate.

### Rollback

Nếu broker không khởi động với package/config mới, khôi phục package hoặc file cấu hình đã lưu theo quy trình hệ điều hành, rồi khởi động lại đúng broker đó. Không xóa log directory hoặc format storage để xử lý lỗi startup thông thường. Nếu lỗi liên quan metadata/version compatibility, dừng thao tác và gọi escalation path; rollback binary không phải lúc nào cũng an toàn sau khi metadata đã được nâng cấp.

## 9. Runbook B: bảo trì KRaft controller quorum

KRaft dùng metadata quorum để bầu controller và replicate metadata log. Controller voter cần majority để tiếp tục tiến triển. Với N voter, majority là floor(N/2) + 1; số voter còn khả dụng phải luôn đạt majority trong lúc bảo trì.

Quy tắc vận hành:

- Xác định controller-only hay combined broker/controller node.
- Xác nhận voter set, current leader và metadata replication trước thay đổi.
- Không dừng đồng thời nhiều voter nếu điều đó làm mất majority.
- Với ba voter, chỉ bảo trì một voter tại một thời điểm và chờ nó trở lại quorum trước khi tiếp tục.
- Với hai voter, một voter mất kết nối đã làm quorum không còn majority; cần kế hoạch riêng và không giả định có thể rolling restart an toàn.
- Không thay đổi voter membership hoặc cluster identity bằng cách sửa file metadata thủ công.
- Không chạy kafka-storage.sh format trên storage đang chứa metadata/log hiện hữu như một bước sửa lỗi.

Kiểm tra trước và sau mỗi controller:

~~~bash
kafka-metadata-quorum.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  describe --status

kafka-metadata-quorum.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  describe --replication
~~~

Chỉ tiếp tục sau khi leader, voter majority và metadata replication ổn định. Nếu quorum mất majority, tránh thao tác tiếp trên các voter còn lại; chuyển sang runbook phục hồi KRaft đã được diễn tập và escalation tới người chịu trách nhiệm cluster.

## 10. Runbook C: thay đổi topic configuration

Topic config có thể ảnh hưởng retention, compaction, durability, kích thước record và throughput. Trước khi thay đổi, lưu giá trị hiện tại và xác định cấu hình là dynamic hay cần restart theo phiên bản.

Xem cấu hình:

~~~bash
kafka-configs.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --entity-type topics \
  --entity-name orders.events \
  --describe
~~~

Ví dụ thay đổi retention:

~~~bash
kafka-configs.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --entity-type topics \
  --entity-name orders.events \
  --alter --add-config retention.ms=604800000
~~~

Ví dụ thay đổi min ISR:

~~~bash
kafka-configs.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --entity-type topics \
  --entity-name orders.events \
  --alter --add-config min.insync.replicas=2
~~~

Sau thay đổi:

1. Describe lại topic config và lưu diff.
2. Kiểm tra producer acks/idempotence và min ISR có tương thích.
3. Theo dõi ISR, produce errors, request latency và disk growth.
4. Với retention, quan sát dung lượng theo thời gian; xóa segment không diễn ra tức thời tại thời điểm đổi config.
5. Với cleanup.policy=compact hoặc delete, kiểm tra tác động tới semantics và consumer.

Rollback bằng cách đặt lại giá trị cũ hoặc xóa override để trở về default theo cách cấu hình đang dùng. Cần phân biệt explicit topic override với broker default; không xóa override nếu chưa ghi nhận giá trị broker default.

## 11. Runbook D: tăng partition cho topic

Tăng partition có thể tăng parallelism và throughput, nhưng thay đổi partition count là thay đổi lâu dài. Kafka không hỗ trợ giảm partition count bằng thao tác thông thường. Khi key được hash để chọn partition, tăng partition có thể làm key cũ được định tuyến sang partition khác; ordering theo key qua thời điểm thay đổi có thể bị ảnh hưởng.

Trước khi tăng:

- Xác định consumer parallelism hiện tại và giới hạn downstream.
- Kiểm tra partition key distribution, hot key và mục tiêu throughput.
- Xác nhận topic có yêu cầu ordering nghiêm ngặt theo key không.
- Đánh giá ảnh hưởng tới state store, Streams task, schema và connector.
- Lập kế hoạch tăng partition theo từng bước và xác minh consumer assignment.

Ví dụ:

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --alter --topic orders.events \
  --partitions 24
~~~

Số partition mới phải lớn hơn số hiện tại. Sau thay đổi, describe topic, kiểm tra partition leader/replicas, consumer group assignment và lag. Không giả định tăng partition sẽ tự động tăng throughput nếu bottleneck nằm ở downstream database hoặc một hot key.

Rollback không phải giảm partition về số cũ. Nếu quyết định thiết kế không phù hợp, phương án thường là tạo topic mới với partition count mong muốn và migrate producer/consumer theo kế hoạch.

## 12. Runbook E: partition reassignment

Reassignment di chuyển replica giữa broker để cân bằng dung lượng, thay broker hoặc thay topology. Đây là thao tác có thể tạo nhiều disk/network I/O, ảnh hưởng latency và ISR nếu chạy quá nhanh.

### Chuẩn bị file reassignment

Ví dụ file JSON cho một partition:

~~~json
{
  "version": 1,
  "partitions": [
    {
      "topic": "orders.events",
      "partition": 0,
      "replicas": [2, 3, 4]
    }
  ]
}
~~~

Kiểm tra file, broker ID, replica placement, rack awareness và disk capacity trước khi execute. Mỗi partition cần đủ replica theo replication factor mong muốn và không đặt toàn bộ replica trên cùng failure domain.

### Execute và verify

~~~bash
kafka-reassign-partitions.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --reassignment-json-file reassignment.json \
  --execute
~~~

Theo dõi tiến độ:

~~~bash
kafka-reassign-partitions.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --reassignment-json-file reassignment.json \
  --verify
~~~

Chỉ xem là hoàn tất khi verify báo reassignment đã kết thúc và topic describe cho thấy replica/ISR đúng mục tiêu. Kiểm tra disk/network và request latency trong suốt quá trình.

Không chạy reassignment cho toàn cluster với tốc độ tối đa mà không đánh giá năng lực. Có thể chia thành nhiều batch nhỏ và điều chỉnh giới hạn replication throttle theo phiên bản/công cụ. Nếu cần hủy hoặc thay đổi reassignment, dùng quy trình và CLI được hỗ trợ bởi đúng phiên bản Kafka; không sửa ZooKeeper/KRaft metadata bằng tay.

## 13. Runbook F: preferred leader election

Sau broker restart hoặc reassignment, leader có thể không nằm trên replica được ưu tiên. Preferred leader election chuyển leadership về preferred replica khi replica đó đủ điều kiện.

Ví dụ chạy cho toàn bộ partition:

~~~bash
kafka-leader-election.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --election-type preferred \
  --all-topic-partitions
~~~

Có thể giới hạn theo topic/partition bằng các tùy chọn của CLI. Trước khi chạy, kiểm tra replica ISR và tải broker; election tạo leadership movement và có thể làm thay đổi request distribution. Sau khi chạy, describe topic và kiểm tra leader, ISR, request rate, network và consumer latency.

Preferred leader election không thay thế reassignment. Nó đổi leader trong replica set hiện có, không di chuyển replica sang broker khác.

## 14. Runbook G: thay đổi ACL

Trước khi thêm hoặc xóa ACL, xác định principal thực tế sau authentication, resource, operation và host restriction. Lưu danh sách ACL hiện tại để có thể khôi phục.

Liệt kê ACL:

~~~bash
kafka-acls.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --list
~~~

Thêm quyền WRITE cho producer trên một topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --add \
  --allow-principal User:orders-producer \
  --operation Write \
  --operation Describe \
  --topic orders.events
~~~

Thêm quyền READ cho consumer và group:

~~~bash
kafka-acls.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --operation Describe \
  --topic orders.events

kafka-acls.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --group orders-service
~~~

Sau khi thay đổi:

1. List ACL và đối chiếu với change request.
2. Thử authentication bằng đúng principal ứng dụng.
3. Producer thử gửi một record kiểm thử được phê duyệt.
4. Consumer thử subscribe/poll với group đúng.
5. Xác nhận principal khác không được cấp thêm quyền.
6. Kiểm tra authorization failure trong client/broker log.

Rollback bằng cách xóa đúng ACL vừa thêm hoặc khôi phục ACL snapshot đã lưu. Không xóa ACL rộng theo wildcard khi chỉ cần thu hồi một principal hoặc một resource.

## 15. Runbook H: thêm broker hoặc decommission broker

Thêm broker không tự động phân phối lại replica của topic cũ. Cần reassignment có kế hoạch để tận dụng broker mới.

Quy trình tổng quát:

1. Provision host/storage/network theo capacity plan.
2. Xác nhận broker ID duy nhất và cấu hình listener/advertised listener.
3. Với KRaft, dùng cluster ID hiện hữu và quy trình storage provisioning được hỗ trợ; không format nhầm thư mục chứa dữ liệu cũ.
4. Khởi động broker và xác nhận registration, API, log directory và metrics.
5. Tạo reassignment theo rack/failure domain và disk headroom.
6. Execute theo batch, throttle nếu cần và verify.
7. Xác nhận replica distribution và broker load sau di chuyển.

Decommission broker:

1. Xác nhận broker mục tiêu và toàn bộ partition replica đang nằm trên đó.
2. Xác nhận broker đích đủ disk/network capacity.
3. Tạo reassignment để di chuyển replica ra khỏi broker.
4. Theo dõi ISR và verify cho tới khi không còn replica cần giữ trên broker.
5. Kiểm tra topic, consumer và cluster health.
6. Chỉ dừng broker khi không còn replica/role cần thiết và change plan cho phép.
7. Thu hồi credential, DNS, monitoring target và tài nguyên host theo quy trình hạ tầng.

Không xóa log directory trước khi xác minh broker đã được loại khỏi topology và dữ liệu cần thiết đã có replica khỏe ở nơi khác.

## 16. Runbook I: thay đổi broker configuration

Broker config có thể là dynamic hoặc static. Dynamic config có thể áp dụng mà không restart, còn static config thường yêu cầu restart broker; phạm vi và khả năng thay đổi phụ thuộc tên config và phiên bản Kafka.

Describe cấu hình broker:

~~~bash
kafka-configs.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --entity-type brokers \
  --entity-name 1 \
  --describe
~~~

Ví dụ đặt dynamic config cho broker (chỉ dùng khi config được hỗ trợ dynamic trong version đang chạy):

~~~bash
kafka-configs.sh \
  --bootstrap-server "$BS" \
  --command-config "$ADMIN_CFG" \
  --entity-type brokers \
  --entity-default \
  --alter --add-config num.io.threads=16
~~~

Ví dụ này dùng entity default cho cấu hình có update mode cluster-wide. Nếu cấu hình là per-broker dynamic, dùng entity-name với broker ID thay cho entity-default. Chỉ chạy khi tài liệu cấu hình của đúng phiên bản Kafka xác nhận property hỗ trợ dynamic update và phạm vi áp dụng phù hợp. Sau khi alter, describe lại config, xác nhận effective value theo cơ chế precedence và theo dõi request handler idle/CPU. Với static config, lưu file cũ, thay đổi đúng node, rolling restart theo runbook A và kiểm tra từng broker.

Không copy nguyên file cấu hình của broker khác nếu listener, node ID, log directories, process roles hoặc advertised addresses khác nhau.

## 17. Runbook J: xử lý disk gần đầy

Disk pressure có thể làm broker ngừng ghi segment mới, replica fetch chậm, reassignment thất bại hoặc broker mất khả năng hoạt động.

Trình tự:

1. Xác định filesystem/log directory nào gần đầy và broker/partition nào chiếm dung lượng.
2. So sánh tốc độ tăng dữ liệu với retention, segment size và throughput hiện tại.
3. Kiểm tra partition reassignment, replica recovery, log cleaner và snapshot có làm tăng I/O.
4. Xác định topic có retention/compaction bất thường hoặc producer phát dữ liệu đột biến.
5. Tăng capacity hoặc di chuyển replica theo kế hoạch nếu cần.
6. Chỉ điều chỉnh retention sau khi xác nhận yêu cầu replay, compliance và downstream.
7. Kiểm tra dung lượng được giải phóng theo thời gian và broker vẫn khỏe.

Không xóa file log segment thủ công trong log directory đang được broker quản lý. Không xóa checkpoint, metadata log hoặc snapshot để giải phóng dung lượng. Dùng topic retention/config và quy trình storage migration được hỗ trợ.

## 18. Runbook K: thay đổi security principal hoặc credential

Credential rotation nên dùng overlap window để producer/consumer chuyển sang credential mới trước khi credential cũ bị thu hồi.

Quy trình tổng quát:

1. Tạo principal/credential mới hoặc cập nhật credential theo cơ chế được chọn.
2. Cấp ACL tối thiểu tương ứng với principal mới.
3. Cập nhật secret provider của một instance canary.
4. Xác minh TLS/SASL handshake, producer send và consumer poll.
5. Triển khai credential mới cho các instance còn lại theo từng nhóm.
6. Theo dõi authentication/authorization failure.
7. Thu hồi credential cũ sau khi xác nhận không còn client dùng.
8. Lưu audit và xác nhận không còn secret cũ trong config/log.

Không rotate đồng thời toàn bộ principal và certificate nếu chưa có cách xác định thành phần nào đang lỗi. Với mTLS, kiểm tra trust chain, SAN/hostname, expiry và truststore của cả client lẫn broker.

## 19. Rollback, forward recovery và điểm không thể đảo ngược

Không phải thay đổi nào cũng có rollback đơn giản.

| Thay đổi | Rollback khả thi | Lưu ý |
|---|---|---|
| Topic config dynamic | Đặt lại giá trị cũ hoặc xóa override | Phải lưu effective/default value |
| ACL | Xóa ACL mới hoặc khôi phục snapshot | Kiểm tra không xóa quyền khác |
| Broker dynamic config | Đặt lại giá trị trước đó | Xem precedence và version |
| Rolling restart/package | Khôi phục package/config nếu metadata compatibility cho phép | Không downgrade tùy tiện sau metadata upgrade |
| Partition reassignment | Có thể tạo reassignment mới về topology cũ | Dữ liệu đã copy vẫn tiêu tốn I/O; cần kiểm tra trạng thái hiện tại |
| Tăng partition count | Không có thao tác giảm partition thông thường | Có thể cần topic mới và migration |
| Retention giảm | Không khôi phục được record đã bị xóa | Xem là thay đổi có thể mất dữ liệu |
| Cleanup policy/compaction | Khó đảo ngược nếu dữ liệu cũ đã compact/xóa | Đánh giá semantics và backup |
| KRaft voter/metadata recovery | Phụ thuộc trạng thái quorum và metadata | Chỉ dùng runbook chuyên biệt đã diễn tập |

Rollback không có nghĩa là đảo ngược một lệnh ngay lập tức. Ví dụ, nếu reassignment đang chạy, phải xác định replica đã di chuyển tới đâu rồi mới lập kế hoạch mới. Nếu retention đã xóa dữ liệu, đặt lại retention không làm record quay lại.

## 20. Quy trình incident và escalation

Khi thao tác gây lỗi:

1. Dừng các bước tiếp theo của change.
2. Ghi thời điểm, lệnh cuối cùng, broker/topic/partition liên quan và output.
3. Xác định impact: offline partition, ISR, producer errors, consumer lag, controller quorum, disk/network.
4. Ưu tiên khôi phục availability và durability theo incident runbook.
5. Không xóa log, format storage, thay cluster ID hoặc sửa metadata thủ công để thử vận may.
6. Gọi người chịu trách nhiệm KRaft/cluster nếu quorum hoặc metadata log bất thường.
7. Gọi security operator nếu nghi ngờ credential/ACL bị lộ hoặc thay sai.
8. Sau phục hồi, thu thập timeline, metrics, logs và thay đổi để postmortem.

Escalate ngay khi:

- Offline partition xuất hiện hoặc ISR giảm dưới min ISR.
- KRaft quorum không còn majority hoặc leader không ổn định.
- Broker không khởi động sau thay đổi storage/metadata.
- Có dấu hiệu mất dữ liệu, log corruption hoặc disk I/O error.
- Authentication/authorization failure ảnh hưởng diện rộng.
- Consumer lag tăng liên tục và vượt recovery window.
- Không rõ trạng thái của reassignment hoặc operation nền.

## 21. Mẫu runbook để dùng cho thay đổi mới

~~~text
CHANGE ID:
CLUSTER / ENVIRONMENT:
REQUESTER:
APPROVER:
OPERATOR:
APPLICATION OWNER:

PURPOSE:
RESOURCES AFFECTED:
CURRENT STATE:
TARGET STATE:
BLAST RADIUS:
RISK LEVEL:
MAINTENANCE WINDOW:

PRE-CHECKS:
1.
2.
3.

EXECUTION:
1. Command/action:
   Expected result:
   Health gate:
2. Command/action:
   Expected result:
   Health gate:

STOP CONDITIONS:
1.
2.

ROLLBACK / FORWARD RECOVERY:
1.
2.

POST-CHECKS:
1. Broker and KRaft health:
2. Partition and ISR:
3. Producer and consumer:
4. Disk/network/runtime:
5. ACL/config diff:
6. Business validation:

EVIDENCE:
METRICS SNAPSHOT:
LOG REFERENCES:
RESULT:
VERIFIER:
COMPLETED AT:
FOLLOW-UP:
~~~

Mẫu này phải được điều chỉnh cho từng thao tác. Không dùng cùng một checklist rút gọn cho ACL change, partition reassignment và controller quorum maintenance vì blast radius khác nhau.

## 22. Lab: diễn tập thay đổi an toàn trên cluster thử nghiệm

Mục tiêu: kiểm tra health baseline, thay đổi topic config, thêm ACL, thực hiện reassignment nhỏ và hoàn thành post-change checks mà không tác động production.

### Bước 1: tạo change record

Ghi cluster lab, topic, principal, operator, approver, mục tiêu và rollback. Xác định trước ngưỡng dừng.

### Bước 2: thu thập baseline

Chạy broker API versions, metadata quorum status/replication, topic describe, consumer group describe và topic config describe. Lưu output và metrics.

### Bước 3: thay đổi topic config

Đặt một retention.ms có thời hạn phù hợp lab. Describe lại và lưu diff. Thực hiện rollback bằng giá trị cũ hoặc xóa override đã thêm.

### Bước 4: thay đổi ACL

Tạo principal producer/consumer thử nghiệm, cấp quyền đúng topic/group. Xác minh producer gửi được, consumer đọc được và principal không được cấp quyền bị từ chối. Thu hồi ACL sau lab.

### Bước 5: reassignment một partition

Chọn partition có replica đủ khỏe, tạo JSON reassignment nhỏ, execute và verify. Theo dõi ISR, disk/network và leader.

### Bước 6: post-change checks

Kiểm tra broker availability, KRaft quorum, offline/under-replicated partitions, ISR, consumer lag, producer error và disk. So sánh với baseline.

### Bước 7: đóng change

Lưu command output, metrics snapshot, ACL/config diff, kết quả verify và bài học. Xác nhận mọi cấu hình lab đã được đưa về trạng thái dự kiến.

## 23. Checklist vận hành trước, trong và sau thay đổi

### Trước thay đổi

- Đúng cluster, đúng environment và đúng resource.
- Có owner, requester, approver và operator.
- Có change ticket, mục tiêu, blast radius và maintenance window.
- Baseline broker, KRaft, partition, ISR, consumer lag và disk đã lưu.
- Cấu hình/ACL/reassignment hiện tại đã được ghi nhận.
- Đã kiểm tra capacity và các operation đang chạy.
- Có lệnh, file input, rollback/forward plan và stop conditions.

### Trong thay đổi

- Thực hiện theo từng bước và từng node/resource có kiểm soát.
- Kiểm tra health gate sau mỗi bước.
- Theo dõi offline partition, under-replicated partition, ISR, quorum và lag.
- Theo dõi CPU, GC, disk, network và request latency.
- Dừng khi xuất hiện lỗi ngoài dự kiến.
- Ghi lại timestamp, command và kết quả.

### Sau thay đổi

- Broker và controller quorum ổn định.
- Không có offline partition ngoài kế hoạch.
- ISR và replica placement đạt mục tiêu.
- Reassignment hoàn tất hoặc đã có trạng thái rõ ràng.
- Producer/consumer và business flow hoạt động.
- ACL/config diff khớp change request.
- Disk, network, CPU, GC và latency trở về ngưỡng chấp nhận.
- Có bằng chứng, người xác minh và ticket closure/follow-up.

## 24. Ghi nhớ

| Thành phần | Nguyên tắc |
|---|---|
| Runbook | Có pre-check, execution, health gate, rollback và post-check |
| RBAC/ACL | Least privilege, principal riêng, audit và thời hạn |
| Rolling restart | Một broker tại một thời điểm; chờ ISR hồi phục |
| KRaft quorum | Giữ majority voter; không bảo trì nhiều voter đồng thời |
| Topic config | Lưu giá trị cũ và phân biệt override với default |
| Partition count | Tăng partition là thay đổi lâu dài, không giảm thông thường |
| Reassignment | Chia batch, theo dõi capacity và verify |
| ACL change | Xác minh đúng principal/resource/operation rồi test bằng client |
| Storage | Không xóa segment hoặc metadata file thủ công |
| Post-change | So sánh baseline và xác minh cả cluster lẫn business flow |
| Rollback | Biết rõ thay đổi nào đảo ngược được và thay đổi nào mất dữ liệu |

Vận hành Kafka an toàn là một quy trình có kiểm soát và có bằng chứng. Hãy phân quyền đúng vai trò, thu thập baseline trước khi thay đổi, thực hiện từng bước theo health gate, giữ KRaft quorum và ISR an toàn, rồi xác minh lại producer, consumer và luồng nghiệp vụ. Khi không đạt điều kiện tiếp tục, dừng và chuyển sang phương án phục hồi đã được chuẩn bị.

## 25. Tài liệu tham khảo

- Apache Kafka – [Operations](https://kafka.apache.org/42/operations/basic-kafka-operations/)
- Apache Kafka – [KRaft](https://kafka.apache.org/42/operations/kraft/)
- Apache Kafka – [Kafka CLI Tools](https://kafka.apache.org/42/operations/basic-kafka-operations/)
- Apache Kafka – [Topic Configs](https://kafka.apache.org/42/configuration/topic-configs/)
- Apache Kafka – [Broker Configs](https://kafka.apache.org/42/configuration/broker-configs/)
- Apache Kafka – [Authorization and ACLs](https://kafka.apache.org/42/security/authorization-and-acls/)
- Apache Kafka – [Monitoring](https://kafka.apache.org/42/operations/monitoring/)
