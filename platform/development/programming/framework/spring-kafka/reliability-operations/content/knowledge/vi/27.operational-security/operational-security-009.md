# Rotate credential không downtime

Trong **Spring Kafka Reliability Operations**, **rotate credential không downtime** là quá trình thay password, SASL secret, OAuth client credential, TLS certificate hoặc Kerberos key mà producer và consumer vẫn tiếp tục phục vụ workload trong suốt đợt thay đổi.

**Nguyên tắc:** broker/identity provider phải chấp nhận credential mới trước khi clients chuyển; Spring Kafka clients phải thực sự nạp credential mới; chỉ thu hồi credential cũ sau khi xác minh toàn bộ workload đã chuyển.

Một cách thường dùng là **blue/green principal rotation**: tạo principal mới, cấp đúng ACL, kiểm tra bằng client canary, rollout từng instance, quan sát traffic theo principal, rồi revoke principal cũ. Cách này tạo overlap window và rollback path rõ ràng.

## 1. Định nghĩa “không downtime”

Không downtime không nhất thiết có nghĩa mọi TCP connection và consumer session giữ nguyên. Khi thay credential, một số client có thể reconnect; consumer group có thể rebalance; producer có thể cần khởi tạo connection mới. Điều cần bảo đảm là không mất records và không làm dịch vụ vượt SLO.

| Workload | Mục tiêu |
|---|---|
| Consumer | Đủ capacity, offsets không bị bỏ qua, lag trong SLO |
| Producer | Publish thành công, retry có giới hạn |
| Transactional processor | Không collision transactional.id, commit đúng |
| Kafka Streams | Internal topics và state stores tiếp tục truy cập |
| Batch worker | Có checkpoint/pause-resume phù hợp |

Nếu yêu cầu không có bất kỳ rebalance hoặc connection reset nào, cần kiểm tra khả năng của auth mechanism và client. Rolling restart có thể giữ workload phục vụ nhưng vẫn có rebalance ngắn.

## 2. Vì sao đổi password trực tiếp gây outage?

Giả sử toàn bộ consumers dùng một username/password. Nếu broker đổi password trước khi application chuyển, connection hiện hữu có thể còn chạy nhưng reconnect/restart sẽ thất bại. Nếu application chuyển trước khi broker chấp nhận credential mới, client mới cũng thất bại.

Do đó, không thay đổi một phía trước khi phía còn lại sẵn sàng. Cần overlap credential hoặc principal mới.

## 3. Blue/green principal

~~~text
BLUE:  orders-reader-v1
GREEN: orders-reader-v2

Cả hai cùng được broker chấp nhận trong overlap window.
V2 có ACL tối thiểu tương đương V1.
~~~

~~~mermaid
flowchart TD
    A["Provision principal v2"] --> B["Copy least-privilege ACL"]
    B --> C["Test auth and workload operations"]
    C --> D["Roll out clients using v2"]
    D --> E["Observe all instances and jobs"]
    E --> F{"No client still uses v1?"}
    F -->|No| D
    F -->|Yes| G["Revoke v1"]
    G --> H["Verify v2-only operation"]
~~~

Ưu điểm là có thể rollback về v1 trước khi revoke, theo dõi client nào đã chuyển và thu hồi độc lập. Không cấp quyền rộng cho v2 để tiết kiệm thời gian.

## 4. Inventory trước khi rotate

Lập danh sách tất cả nơi dùng credential:

- Kafka consumers, groups, topics và replicas.
- Kafka producers, output topics và transactional IDs.
- KafkaTemplate/ProducerFactory/ConsumerFactory tùy chỉnh.
- KafkaAdmin/AdminClient.
- Kafka Streams, internal topics và state stores.
- Scheduled jobs, CronJobs và batch workers.
- Kafka Connect workers/connectors.
- CI/CD, migration và smoke-test tools.
- Monitoring clients và health checks.
- Disaster recovery/standby clusters.

Ghi principal, secret reference và version; không ghi password/token vào ticket hoặc spreadsheet. Đừng quên job chạy hàng đêm hoặc tool ngoài Kubernetes.

## 5. Chọn chiến lược theo mechanism

| Cơ chế | Credential | Overlap thường dùng |
|---|---|---|
| SASL/SCRAM | Username/password | Principal mới và ACL song song |
| SASL/PLAIN | Username/password | User mới; luôn bảo vệ bằng TLS |
| OAuth/OAUTHBEARER | Client secret/key/token source | IdP chấp nhận credential cũ/mới cùng lúc |
| mTLS | Client certificate/private key | Trust CA/certificate cũ và mới |
| Kerberos/GSSAPI | Keytab/key version/ticket | Phối hợp KVNO, ticket renewal và rollout |
| Cloud IAM | Workload identity/role | Cấp identity mới và trust/policy overlap |

Không dùng cùng runbook cho SCRAM, OAuth, mTLS và Kerberos. Kiểm tra broker, IdP và Kafka client version.

## 6. SASL/SCRAM

Kafka SCRAM lưu credential verifier cho user/mechanism. Không giả định một principal luôn có thể giữ hai password đồng thời. Blue/green principal thường rõ ràng hơn:

~~~text
orders-reader-v1 -> READ orders.events; READ group orders-service
orders-reader-v2 -> READ orders.events; READ group orders-service
~~~

Tạo v2, cấp ACL tối thiểu, xác thực và thực hiện consume test. Sau đó chuyển client theo rolling rollout. Chỉ xóa v1 khi toàn bộ consumers, producers, jobs và tools đã chuyển.

Producer principal cần WRITE trên output topic. Transactional producer cần quyền với transactional ID. Consumer cần quyền group ngoài quyền topic.

## 7. Spring Boot SCRAM configuration

Ví dụ properties với placeholder không chứa secret:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    consumer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_ORDERS_READER_V2_JAAS
    producer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_ORDERS_WRITER_V2_JAAS
~~~

Các giá trị INJECTED_* chỉ là placeholder minh họa. Secret phải được cấp từ secret manager hoặc deployment mechanism được phê duyệt. Nếu dùng custom factories, xác minh từng factory nhận đúng client-specific properties; đừng chỉ sửa application.yml rồi giả định tất cả clients đã chuyển.

## 8. OAuth/OAUTHBEARER

Phân biệt client secret dùng để lấy token, access token trình với broker, refresh mechanism và issuer/audience/scope. Rotation thường gồm:

1. Tạo client secret/key mới tại IdP.
2. Cho phép credential cũ và mới cùng tồn tại nếu IdP hỗ trợ.
3. Cập nhật secret reference.
4. Xác minh callback/login handler lấy token mới.
5. Reconnect/recreate client theo khả năng Kafka client.
6. Kiểm tra broker chấp nhận token mới và scope đúng.
7. Theo dõi expiry và re-authentication.
8. Thu hồi secret cũ sau khi toàn fleet chuyển.

Không log access token, refresh token, client secret hoặc JWT claims. Chỉ ghi secret version và failure category. Không giả định cập nhật secret store sẽ làm callback handler đang chạy tự thay cấu hình.

## 9. mTLS certificate rotation

Một quy trình trust overlap:

~~~text
Broker/client trust:
  CA_OLD trusted
  CA_NEW trusted

Client fleet:
  some use CERT_OLD
  rolling rollout to CERT_NEW

After verification:
  remove CA_OLD
~~~

Thêm CA mới vào truststore trước khi clients dùng certificate mới. Phát hành certificate mới, xác minh principal mapping (DN/SAN) và ACL, cập nhật keystore, rollout từng instance, ép reconnect để kiểm tra SSLContext mới, rồi mới loại CA cũ.

Thay file trên disk không bảo đảm SSLContext của Kafka client hiện hữu tự reload. Nhiều client nạp SSL configuration khi khởi tạo; cần xác định refresh/recreate path. Không tắt hostname verification hoặc trust-all để chữa lỗi rotation.

## 10. Kerberos/GSSAPI

Kiểm tra client principal, keytab, broker SPN, realm, DNS, clock skew, ticket lifetime, KVNO và renewal. Một số hệ thống hỗ trợ nhiều key versions trong keytab cho overlap, nhưng chi tiết phụ thuộc KDC và công cụ quản lý.

Cần test:
- Broker service principal đã được cập nhật đúng.
- Client mới login bằng keytab mới.
- Ticket renewal hoạt động sau thời gian dài.
- Kafka client có cần re-login hoặc recreate không.
- Old key chỉ bị thu hồi khi không còn clients cần.

Không in keytab, ticket cache hoặc JAAS secrets.

## 11. ACL parity

Principal mới cần đúng quyền:

| Role | Resource | Quyền thường cần |
|---|---|---|
| Consumer | Topic | READ, DESCRIBE |
| Consumer | Group | READ |
| Producer | Topic | WRITE, đôi khi DESCRIBE |
| Transactional producer | Transactional ID | WRITE/DESCRIBE theo operation |
| Admin | Cluster/topic | Chỉ quyền admin được yêu cầu |

Quyền chính xác phụ thuộc broker authorizer, version, operation và prefix ACL. Kiểm tra effective ACL và deny policies. Không cấp superuser để làm health check chuyển UP.

## 12. Spring Kafka client lifecycle

Spring Kafka tạo KafkaConsumer/KafkaProducer thông qua factories và listener containers. Credentials thường được đọc khi client được tạo. Cập nhật Kubernetes Secret không tự bảo đảm client hiện hữu đổi credential.

Các thành phần cần xem:
- DefaultKafkaConsumerFactory và consumer instances.
- DefaultKafkaProducerFactory và producer instances.
- KafkaTemplate và ProducerFactory.
- KafkaListenerEndpointRegistry/listener containers.
- KafkaAdmin/AdminClient.
- Custom interceptors, callback handlers và SSLContext.
- Transaction manager và producer cache.

Không đóng raw KafkaConsumer/Producer từ thread tùy ý. Dùng lifecycle API của Spring hoặc rollout instance mới để thay client an toàn.

## 13. Rolling deployment cho consumer group

~~~text
A, B, C dùng credential v1

Roll A sang v2 -> đợi Ready và assignment
Roll B sang v2 -> đợi Ready và assignment
Roll C sang v2 -> đợi Ready và assignment

Xác minh không còn client v1
Revoke v1
~~~

Rolling restart có thể gây rebalance. Giảm tác động bằng capacity dự phòng, graceful shutdown, drain in-flight work, maxUnavailable phù hợp và theo dõi rebalance duration/lag. Cooperative sticky assignment có thể giảm partition movement nếu toàn group hỗ trợ, nhưng không loại bỏ mọi rebalance.

Với một consumer replica duy nhất, restart có thể tạo khoảng không có consumer. Cần thêm capacity hoặc blue/green deployment nếu muốn giữ workload liên tục.

## 14. Producer rollout và idempotence

Roll producer theo từng instance, quan sát send success, reconnect, latency, retries và producer errors. Nếu bật idempotence, để Kafka client quản lý producer identity/sequence theo lifecycle; không tự giả định producer mới kế thừa state cũ.

Với transactional producer, đặc biệt chú ý **transactional.id**. Hai producers đồng thời dùng cùng ID có thể fence nhau. Cấp quyền transactional ID cho principal mới trước rollout, tránh hai owners cùng dùng ID không tương thích, và theo dõi ProducerFencedException/transaction abort.

Không thay transactional ID prefix cùng lúc với credential rotation nếu không cần. Nếu buộc phải đổi, coi đó là thay đổi transaction ownership riêng và test kỹ.

## 15. Kafka Streams và internal resources

Principal mới cần quyền cho input/output topics, consumer group/application ID, repartition topics, changelog topics, transactional IDs và Admin operations nếu topology tạo internal topics.

Một ứng dụng có thể đọc input thành công nhưng fail khi ghi changelog hoặc tạo repartition topic. Test state restoration, processing và transaction commit bằng principal mới. Tránh kết hợp rotation với topology/application.id migration để dễ rollback.

## 16. Kubernetes Secret rollout

Environment variables thường chỉ được đọc khi process start. Mounted Secret volume có thể được cập nhật, nhưng ứng dụng/Kafka client không tự động reload nếu không có cơ chế hỗ trợ. SSLContext cũng có thể giữ certificate đã nạp.

Một cách rõ ràng là cập nhật secret version/reference trong Pod template để tạo ReplicaSet mới và rolling update:

~~~yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    spec:
      containers:
        - name: orders-service
          env:
            - name: KAFKA_CREDENTIAL_VERSION
              value: "v2"
~~~

Đây chỉ là fragment minh họa; secret value vẫn phải được inject qua Secret/secret manager. maxUnavailable=0 cần capacity và resource quota đủ cho maxSurge.

## 17. Readiness gate

Pod mới không nên Ready chỉ vì JVM đã start. Readiness cần phản ánh capability thật:

**Consumer:** credentials mới được load, authentication thành công, join group và có assignment theo trạng thái chấp nhận, fetch/processing path hoạt động khi có data.

**Producer:** authentication thành công, có thể publish vào topic cần thiết; nếu transactional thì transaction lifecycle hoạt động.

Một AdminClient describeCluster thành công không chứng minh producer có WRITE ACL hoặc consumer có READ/group ACL. Với topic idle, không nhất thiết chờ business record thật; dùng assignment và capability check phù hợp. Không gửi synthetic message vào production topic nếu không có thiết kế/cleanup.

Readiness failure thường đánh dấu Pod NotReady; liveness failure có thể restart process. Khi credential rotation lỗi, giữ readiness DOWN nếu dependency bắt buộc nhưng không làm liveness fail chỉ vì broker/secret sai. Restart loop với cùng config không sửa được credentials.

## 18. Health state theo capability

Có thể duy trì trạng thái riêng cho producer, consumer và admin, gồm operation, last-success timestamp và failure category. Không dùng một boolean Kafka chung nếu ứng dụng có nhiều roles.

Ví dụ state holder:

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public class KafkaCapabilityState {

    public record Snapshot(
            boolean available,
            String capability,
            String failureKind,
            Instant lastSuccess) {
    }

    private final AtomicReference<Snapshot> current =
        new AtomicReference<>(
            new Snapshot(false, "not_verified", "unknown", null)
        );

    public void success(String capability) {
        current.set(new Snapshot(
            true, capability, "none", Instant.now()
        ));
    }

    public void failure(String capability, String kind) {
        Snapshot previous = current.get();
        current.set(new Snapshot(
            false, capability, kind, previous.lastSuccess()
        ));
    }

    public Snapshot snapshot() {
        return current.get();
    }
}
~~~

Đây là ví dụ state-based, không tự thực hiện authentication. Integration phải cập nhật state sau operation thật và áp dụng freshness threshold để readiness không flapping. Không đưa credentials hoặc raw exception message vào health details.

## 19. Cutover theo từng client role

| Wave | Client | Xác minh |
|---|---|---|
| 0 | Admin/test client | Principal mới authenticate và ACL đúng |
| 1 | Producer canary | Send operation vào topic test |
| 2 | Consumer canary | Join test group, fetch/process |
| 3 | Một phần production producers | Send success, latency |
| 4 | Một phần production consumers | Assignment, lag, processing |
| 5 | Phần còn lại | Không còn client cũ |
| 6 | Revoke old identity | v2-only operation thành công |

Không dùng cùng production consumer group cho canary độc lập nếu không muốn canary nhận partitions production. Dùng test topic/group hoặc thiết kế canary rõ ràng.

## 20. Theo dõi overlap window

| Chỉ số | Câu hỏi |
|---|---|
| Auth success/failure theo principal | Clients mới xác thực được không? |
| Connection/reconnect count | Có reconnect storm không? |
| Group membership/assignment | Consumer capacity còn đủ không? |
| Rebalance count/duration | Rollout gây churn bao nhiêu? |
| Consumer lag | Workload có gián đoạn không? |
| Producer send success | Principal mới ghi được không? |
| Transaction abort/fencing | Có vấn đề identity/ownership không? |
| Retry/DLT backlog | Lỗi có chuyển sang recovery path không? |
| Readiness | Pod chỉ Ready sau capability check? |
| Old principal last seen | Còn workload nào dùng v1 không? |

Không chỉ nhìn Deployment rollout hoàn tất. Scheduled job hàng đêm, connector hoặc DR environment có thể chỉ reconnect sau khi credential cũ bị revoke.

## 21. Rollback criteria

Xác định trước các ngưỡng rollback:

- Authentication failure tăng trên principal mới.
- Producer send errors vượt SLO.
- Consumer group mất assignment quá thời gian cho phép.
- Lag vượt business threshold.
- Transaction fencing/abort tăng bất thường.
- Readiness không phục hồi.
- Một client phụ thuộc v1 chưa được inventory.

Nếu v1 vẫn an toàn và hợp lệ, rollback từng instance về v1 trước khi revoke. Không revoke v1 trong rollback window. Nếu v1 đã compromise, không giữ nó để rollback; cần identity thứ ba hoặc emergency rotation.

## 22. Điều kiện revoke credential cũ

Chỉ revoke v1 khi có bằng chứng:
1. Tất cả production pods dùng v2.
2. Scheduled/batch jobs đã chuyển.
3. Connect, Streams, admin tools và DR đã được kiểm tra.
4. Không còn auth activity từ v1 trong thời gian đủ bao phủ workload định kỳ.
5. Producer/consumer/transaction operations v2 ổn định.
6. ACL mới được xác minh.
7. Rollback window đã hết hoặc có phương án identity khác.
8. Security owner phê duyệt nếu quy trình yêu cầu.

Không dựa riêng vào Deployment hiện tại. Một process ngoài Kubernetes có thể vẫn dùng credential cũ.

## 23. Rotation khẩn cấp khi credential bị lộ

Rotation thông thường ưu tiên overlap. Khi credential đã compromise, ưu tiên giảm cửa sổ attacker sử dụng secret; có thể chấp nhận gián đoạn ngắn theo incident policy.

1. Xác định principal/secret và phạm vi client.
2. Tạo identity mới hoặc credential an toàn.
3. Cấp ACL tối thiểu.
4. Triển khai client mới theo blast radius.
5. Thu hồi credential bị compromise theo quyết định incident commander.
6. Theo dõi auth attempts từ identity cũ.
7. Kiểm tra broker audit logs.
8. Xác minh workload dùng identity mới.
9. Rotate các credentials liên quan có thể bị lộ.
10. Ghi incident và preventive actions.

Không kéo dài overlap chỉ để giữ availability khi secret cũ đang bị attacker sử dụng.

## 24. Logging và metrics an toàn

Structured log minh họa:

~~~text
event=kafka_credential_rotation
service=orders-service
client_type=consumer
principal=orders-reader-v2
credential_version=secret-v2
phase=canary
authentication=success
group_assignment=ready
~~~

Không log password, token, refresh token, JAAS config đầy đủ, private key, keytab hoặc keystore password.

Metrics gợi ý: rotation phase, auth success/failure, reconnect count, assignment count, consumer lag, producer send failures, transaction aborts, readiness state và old credential last-seen. Đây là custom metrics; principal labels cần cardinality thấp và được policy cho phép.

## 25. Integration test cho credential rotation

Dùng broker có authentication/ACL thật hoặc test environment tương đương:

1. Tạo principal v1/v2 và ACL tối thiểu cho cả hai.
2. Start producer/consumer bằng v1, xác minh operations.
3. Start canary client bằng v2.
4. Xác minh authentication, authorization và produce/consume thật.
5. Roll từng consumer instance sang v2.
6. Kiểm tra group assignment, lag và rebalance.
7. Roll producers sang v2, kiểm tra acknowledgements.
8. Kiểm tra transaction commit/fencing nếu có.
9. Xác nhận không còn client dùng v1.
10. Revoke v1 và ép/retry reconnect clients v2.
11. Xác minh v2-only operation tiếp tục.
12. Test rollback trước khi revoke v1.
13. Test emergency revoke riêng nếu threat model yêu cầu.

Không chỉ test handshake; cần test topic/group/transaction permissions. Broker test image có thể không hỗ trợ đầy đủ SCRAM/OAuth/Kerberos/ACL, nên ghi rõ giới hạn.

## 26. Integration test TLS và OAuth

**mTLS:**
- Trust cả CA cũ và mới trong overlap.
- Start client với certificate cũ.
- Chuyển canary sang certificate mới.
- Ép reconnect để kiểm tra SSLContext mới.
- Roll fleet.
- Loại CA cũ.
- Reconnect tất cả clients và xác minh chỉ cert mới được chấp nhận.
- Test expired/unknown CA và đảm bảo private key không log.

**OAuth:**
- Cấp token qua client credential cũ.
- Provision credential mới và overlap ở IdP.
- Xác minh callback lấy token mới.
- Kiểm tra broker chấp nhận token và claims.
- Test refresh trước/sau expiry.
- Revoke credential cũ.
- Xác minh client không còn phụ thuộc secret cũ.
- Test issuer/audience/scope sai và bảo đảm token không lộ.

Mock callback trả token không chứng minh broker SASL/OAUTHBEARER handshake hoạt động; cần integration với IdP/broker phù hợp.

## 27. Runbook rotation bình thường

**Chuẩn bị**
1. Inventory tất cả clients/principals/secret references.
2. Xác định mechanism và client lifecycle.
3. Chốt SLO, overlap duration, rollback window.
4. Provision identity mới.
5. Cấp ACL tối thiểu tương đương.
6. Test principal mới.
7. Chuẩn bị secret version, deployment và dashboards.

**Canary/rollout**
8. Chuyển producer/consumer canary.
9. Xác minh authentication, ACL và operation thật.
10. Roll từng instance theo readiness/capacity.
11. Theo dõi assignment, lag, send errors, transactions.
12. Kiểm tra jobs/connectors/admin/DR.
13. Dừng rollout nếu vượt rollback threshold.

**Hoàn tất**
14. Xác minh không còn client dùng v1.
15. Giữ overlap đủ thời gian bao phủ jobs định kỳ.
16. Revoke old credential/ACL.
17. Xác minh v2-only sau reconnect.
18. Theo dõi business SLO và auth failures.
19. Ghi credential version và kết quả.

## 28. Runbook khi rotation gây lỗi

1. Dừng rollout tiếp theo.
2. Phân loại AuthN, AuthZ, TLS, OAuth, Kerberos hay network.
3. Kiểm tra secret version/mount và client có dùng config mới không.
4. Kiểm tra security.protocol, mechanism và broker listener.
5. Kiểm tra principal mapping và ACL topic/group/transactional ID.
6. Kiểm tra SSLContext/callback refresh/recreate.
7. Nếu v1 còn an toàn, rollback canary/instances về v1.
8. Không revoke v1 trong rollback window.
9. Nếu v1 compromise, dùng identity thứ ba theo incident plan.
10. Chạy lại canary operation trước khi tiếp tục.
11. Ghi root cause và biện pháp ngăn lặp.

Không cấp superuser hoặc tắt hostname verification để chữa tạm.

## 29. Anti-patterns

- Đổi password trên broker trước khi clients chuyển.
- Cập nhật Secret nhưng giả định Kafka clients tự reload.
- Revoke v1 khi rollout chưa xong.
- Bỏ sót CronJobs, connectors, DR và admin tools.
- Không cấp ACL group/transactional ID cho principal mới.
- Restart toàn fleet cùng lúc.
- Chạy hai transactional producers cùng transactional.id.
- Chỉ test SASL handshake mà không test operation.
- Dùng describeCluster làm readiness cho consumer.
- Không kiểm tra OAuth refresh hoặc Kerberos renewal.
- Không chờ stop/recreate lifecycle hoàn tất.
- Không có rollback window.
- Giữ credential compromise quá lâu để ưu tiên zero downtime.

## 30. Checklist trước khi revoke old credential

- [ ] Principal mới authenticate với đúng broker listener.
- [ ] ACL đúng cho topics, groups và transactional IDs.
- [ ] Producer clients đã chuyển, send success ổn định.
- [ ] Consumer clients đã chuyển, assignment ổn định.
- [ ] Kafka Streams/internal topics đã được kiểm tra.
- [ ] KafkaAdmin, connectors, jobs, tools và DR đã chuyển.
- [ ] OAuth refresh/Kerberos renewal hoạt động.
- [ ] TLS cert mới được dùng sau reconnect.
- [ ] Không còn old principal activity trong overlap window.
- [ ] Consumer lag và business SLO bình thường.
- [ ] Transaction fencing/abort không tăng.
- [ ] Rollback window đã kết thúc hoặc có identity thay thế.
- [ ] Security owner phê duyệt revoke nếu cần.
- [ ] Có audit record cho thời điểm thu hồi.

## 31. Kết luận

**Rotate credential không downtime** đòi hỏi broker hoặc identity provider chấp nhận credential mới trước khi clients chuyển, trong khi credential cũ còn hiệu lực đủ lâu cho rollout và rollback. Với SASL/SCRAM, blue/green principal thường tạo overlap rõ ràng; với mTLS, chuẩn bị trust CA mới trước khi rollout certificate; với OAuth/Kerberos, kiểm soát token/ticket renewal và client lifecycle.

Trong Spring Kafka, cập nhật Secret không tự thay credentials của KafkaConsumer, KafkaProducer, KafkaAdmin hoặc SSLContext đang chạy. Xác định đúng client lifecycle, rollout từng đợt theo readiness/capacity, xác minh **authentication lẫn authorization bằng operation thật**, rồi mới revoke identity cũ.

Trong suốt quá trình, theo dõi consumer group rebalance, lag, in-flight records, transaction abort/fencing và idempotency. Khi credential bị compromise, ưu tiên thu hồi theo incident policy thay vì kéo dài overlap để giữ availability. Rotation chỉ hoàn tất khi **mọi workload dùng credential mới, không còn phụ thuộc credential cũ và business processing vẫn đáp ứng SLO**.
