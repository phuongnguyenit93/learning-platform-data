# Phân quyền consume

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi một thành phần nhận và xử lý event, hệ thống cần xác định thành phần đó có được phép đọc topic, đăng ký listener hoặc truy cập dữ liệu mà event đề cập hay không. **Phân quyền consume** là việc giới hạn consumer theo danh tính, loại event, phạm vi dữ liệu và hành động nghiệp vụ được phép thực hiện.

Phân quyền cần được đặt đúng ranh giới. Application event nội bộ của Spring được dispatch trong cùng application context; Kafka consumer đọc message từ broker qua một kết nối có danh tính và quyền riêng. Spring Modulith giúp kiểm soát cấu trúc module và hợp đồng phụ thuộc, nhưng bản thân việc một listener đăng ký nhận event không phải là một cơ chế ACL. Khi event đi qua broker, cần kiểm soát quyền ở broker và tiếp tục kiểm tra quyền ở tầng ứng dụng trước khi thực hiện nghiệp vụ.

## 1. Xác định ai được consume event

Trước khi cấu hình quyền, cần xác định consumer là ai và event chứa dữ liệu nào. Một consumer có thể là listener trong module, một dịch vụ chạy riêng hoặc một ứng dụng tích hợp đọc Kafka topic.

| Loại consumer | Danh tính cần xác định | Ranh giới kiểm soát chính |
| --- | --- | --- |
| Listener nội bộ Spring Modulith | Module/ứng dụng đang chạy và thành phần listener | Ranh giới module, API được công khai và kiểm tra quyền nghiệp vụ trong handler |
| Kafka consumer service | Service principal hoặc certificate của workload | ACL của Kafka broker và authorization trong ứng dụng |
| Consumer đa tenant | Service identity cùng tenant context đã được xác thực | Quyền theo tenant và quyền truy cập từng tài nguyên |
| Consumer vận hành/analytics | Danh tính workload hoặc người dùng được cấp quyền | Topic được phép đọc, dữ liệu được phép xem và chính sách lưu giữ |

Không nên cấp quyền chỉ dựa trên tên class listener, tên pod hoặc giá trị group ID do client tự gửi. Hãy xác thực danh tính từ cơ chế đáng tin cậy như SASL/SCRAM, OAuth hoặc mTLS ở broker; sau đó ánh xạ danh tính đó sang quyền cụ thể.

## 2. Phân biệt authentication và authorization

Authentication xác minh consumer là ai. Authorization quyết định consumer đó được làm gì. Hai bước bổ trợ nhau:

- Authentication: Kafka xác thực service bằng SASL/SCRAM, OAuth hoặc TLS client certificate.
- Authorization: broker kiểm tra principal có quyền đọc topic và tham gia consumer group hay không.
- Application authorization: handler kiểm tra event có được phép xử lý trong ngữ cảnh nghiệp vụ hiện tại không.
- Data authorization: truy vấn và thao tác chỉ truy cập tenant, tài khoản hoặc tài nguyên mà consumer được phép xử lý.

Một kết nối Kafka được xác thực thành công không đồng nghĩa principal được đọc mọi topic. Tương tự, principal có quyền đọc topic cũng không có nghĩa mọi event trong topic đều được phép làm thay đổi mọi dữ liệu nghiệp vụ.

## 3. Phân quyền cho application events nội bộ

Với Spring application events trong cùng tiến trình, ApplicationEventPublisher gửi event đến các listener phù hợp đã đăng ký trong application context. Cơ chế dispatch thông thường không có ACL theo từng listener hoặc từng event type. Nếu hai listener tương thích cùng đăng ký nhận một event, cả hai có thể được gọi theo cấu hình dispatch.

Vì vậy, cần thiết kế quyền ở các lớp sau:

1. **Ranh giới module:** chỉ công khai event contract và API mà module khác được phép sử dụng.
2. **Ranh giới triển khai:** chỉ đóng gói và khởi tạo những listener thuộc ứng dụng có trách nhiệm nhận event.
3. **Quyền nghiệp vụ:** handler kiểm tra điều kiện và quyền truy cập trước khi đọc hoặc thay đổi dữ liệu.
4. **Quyền dữ liệu:** repository/query luôn giới hạn theo tenant, chủ sở hữu hoặc phạm vi tài nguyên.

Ví dụ, module Order công bố OrderConfirmed. Listener của Inventory có thể giữ hàng; listener của Notification có thể gửi thông báo. Việc Inventory được nhận event không cho phép nó đọc toàn bộ hồ sơ khách hàng hoặc truy cập repository nội bộ của Customer. Nó chỉ nên dùng dữ liệu trong event và API được công khai cho use case đó.

Spring Modulith hỗ trợ xác định và kiểm tra cấu trúc module, nhưng module boundary không thay thế authorization. Nếu tất cả module chạy trong cùng process và cùng database credential, một lỗi code hoặc truy cập repository không phù hợp vẫn có thể vượt qua ý định kiến trúc. Khi cần ranh giới bảo mật mạnh hơn, cân nhắc tách workload hoặc dữ liệu sang security boundary riêng.

## 4. Phân quyền consume ở Kafka broker

Với Kafka, broker có thể kiểm tra principal được phép đọc topic nào và tham gia consumer group nào. Nguyên tắc là cấp quyền tối thiểu theo subscriber logic:

- Cấp quyền READ trên topic cần consume.
- Cấp quyền READ trên consumer group tương ứng để consumer tham gia group và commit offset theo cơ chế broker.
- Chỉ cấp DESCRIBE cho topic hoặc group khi client/operation và cấu hình broker thực sự cần.
- Không cấp quyền WRITE hoặc CREATE cho consumer chỉ cần đọc.
- Không dùng chung một principal cho nhiều service có phạm vi dữ liệu khác nhau nếu cần audit và thu hồi độc lập.

Ví dụ, service Inventory đọc orders.events bằng group inventory-service; Analytics đọc cùng topic bằng group analytics-projection. Hai service nên có principal và ACL riêng. Inventory không cần quyền đọc payments.private.events nếu use case của nó không yêu cầu.

Một lệnh ACL minh họa với Kafka CLI:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka.example.internal:9093 \
  --add \
  --allow-principal "User:inventory-service" \
  --operation READ \
  --topic orders.events \
  --group inventory-service
~~~

Đây là ví dụ cấu hình ACL; cú pháp và cách quản lý principal phụ thuộc phiên bản Kafka, authorizer và môi trường triển khai. Cần kiểm tra ACL thực tế sau khi áp dụng, kể cả quyền kế thừa từ wildcard hoặc nhóm quyền rộng hơn.

Không cấp ALL cho consumer chỉ vì muốn tránh lỗi permission. Quyền rộng có thể cho phép service đọc dữ liệu ngoài phạm vi, ghi topic, thay đổi cấu hình hoặc thực hiện thao tác quản trị mà workload không cần.

## 5. Consumer group cũng là một phần của quyền

Kafka quản lý quyền đọc topic và quyền sử dụng consumer group. Group ID không phải bằng chứng xác thực; client có thể khai báo group ID trong cấu hình. Broker phải kiểm tra principal có quyền sử dụng group đó.

Ví dụ:

| Principal | Topic READ | Group READ | Kết quả mong muốn |
| --- | --- | --- | --- |
| User:inventory-service | orders.events | inventory-service | Được đọc topic cho subscriber Inventory. |
| User:analytics-service | orders.events | analytics-projection | Được đọc cùng topic như subscriber độc lập. |
| User:inventory-service | payments.private.events | inventory-service | Bị từ chối nếu không được cấp quyền topic. |
| User:unknown-service | orders.events | inventory-service | Bị từ chối nếu principal không có quyền topic/group. |

Nếu nhiều instance của cùng Inventory service chạy đồng thời, chúng dùng cùng principal và group ID đã được cấp. Không tạo group ID mới cho mỗi pod nếu mục tiêu là chia tải trong một subscriber; việc đó có thể tạo các subscriber độc lập và làm event được xử lý lặp ở cấp ứng dụng.

Khi đổi group ID, cần cấp quyền cho group mới trước khi rollout. Khi thu hồi group cũ, xác minh không còn instance hợp lệ sử dụng nó. Tránh wildcard group rộng nếu mỗi workload cần một phạm vi consume riêng.

## 6. Cấu hình danh tính Kafka trong Spring

Spring Boot/Spring Kafka cấu hình kết nối và listener; cơ chế authentication/authorization thực tế được thực thi bởi Kafka client và broker. Ví dụ minh họa dùng SASL/SCRAM qua TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.example.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="inventory-service" password="INJECT_FROM_SECRET_MANAGER";
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Ví dụ chỉ minh họa cấu trúc cấu hình. Secret phải được cung cấp qua secret manager hoặc cơ chế bảo mật của môi trường; không commit mật khẩu vào repository, không ghi JAAS config có secret vào log và không đưa secret vào event header. Cấu hình serializer/deserializer cần giới hạn type mapping và trusted package theo hợp đồng consumer.

Listener khai báo topic và group:

~~~java
@Component
class OrderEventsConsumer {

    @KafkaListener(
        topics = "orders.events",
        groupId = "inventory-service"
    )
    void on(OrderConfirmedPayload event) {
        // Kiểm tra ngữ cảnh và quyền nghiệp vụ trước khi xử lý.
    }
}
~~~

Annotation KafkaListener xác định nơi nhận và group; nó không tự tạo ACL trên broker. Principal của Kafka client phải được cấp quyền ở broker. Nếu cấu hình group ID trong annotation, hãy bảo đảm ACL khớp với giá trị đó và tránh ghi đè ngoài dự kiến group ID ở consumer properties.

## 7. Kiểm tra quyền nghiệp vụ trong handler

Broker ACL giới hạn topic mà service được đọc, nhưng không thể thay thế quy tắc nghiệp vụ. Một event hợp lệ về mặt schema vẫn có thể không được phép áp dụng vào một tài khoản, tenant hoặc đơn hàng cụ thể.

Ví dụ, handler chỉ xử lý event thuộc tenant mà service được phép phục vụ:

~~~java
@Component
@RequiredArgsConstructor
class TenantOrderListener {

    private final TenantAccessPolicy accessPolicy;
    private final OrderProjectionService projections;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        accessPolicy.requireAllowedTenant(event.tenantId());
        projections.apply(event);
    }
}
~~~

TenantAccessPolicy là thành phần kiểm tra quyền do ứng dụng triển khai. Trong hệ thống đa tenant, không chỉ kiểm tra tenantId một lần ở listener rồi truy vấn không giới hạn. Các thao tác đọc/ghi phải tiếp tục ràng buộc tenantId hoặc ownership trong query và transaction để tránh lỗi IDOR hoặc truy cập chéo tenant.

Nếu consumer xử lý event theo service identity, hãy kiểm tra quyền của service đối với loại thao tác và dữ liệu. Không giả định người dùng đã kích hoạt event vẫn đang đăng nhập hoặc token của người dùng có thể được dùng an toàn khi event được xử lý bất đồng bộ nhiều phút sau đó.

## 8. Security context trong xử lý bất đồng bộ

Với ApplicationModuleListener hoặc listener bất đồng bộ, handler có thể chạy trên thread khác sau khi transaction của publisher đã commit. SecurityContext của request ban đầu không tự động trở thành danh tính đáng tin cậy cho listener.

Không nên dựa vào SecurityContextHolder để suy ra người dùng hiện tại trong mọi listener bất đồng bộ. Nếu nghiệp vụ cần biết ai khởi tạo hành động, event có thể mang actorId hoặc initiatedBy như dữ liệu audit. Giá trị đó giúp truy vết, nhưng không phải credential và không tự cấp quyền.

Đối với authorization, chọn rõ một trong hai mô hình:

- **Service authorization:** listener thực hiện công việc bằng quyền của service identity và kiểm tra quyền của service đối với tài nguyên.
- **Delegated authorization:** nếu nghiệp vụ thực sự cần giữ quyền của người dùng, dùng cơ chế delegation có thời hạn và kiểm tra được, chẳng hạn token trao đổi hoặc capability có phạm vi hẹp; không truyền access token dài hạn trong payload event.

Không truyền toàn bộ SecurityContext, session cookie hoặc bearer token trong event. Các thông tin này có thể bị lưu vào publication store, broker, dead-letter topic, log hoặc bản sao message và làm tăng rủi ro lộ credential.

## 9. Phân quyền theo event type và dữ liệu nhạy cảm

Không phải mọi consumer cần mọi event. Tách topic hoặc hợp đồng event theo phạm vi dữ liệu có thể giúp ACL rõ ràng hơn. Ví dụ orders.events chứa trạng thái đơn hàng đã được phép chia sẻ; payments.private.events chứa dữ liệu thanh toán giới hạn cho Payment và Accounting.

Các nguyên tắc thiết kế:

- Chỉ đưa vào topic những field consumer thực sự cần.
- Không phát số thẻ đầy đủ, CVV, access token hoặc bí mật xác thực.
- Dùng event DTO riêng cho consumer công khai và consumer nội bộ nếu mức độ dữ liệu khác nhau.
- Dùng tên topic và event type thể hiện rõ phạm vi dữ liệu.
- Cấp ACL theo topic cụ thể, không cấp quyền đọc toàn bộ namespace nếu không cần.
- Xác thực schema và event type trước khi gọi handler nghiệp vụ.

Một topic dùng chung có thể tiện cho fan-out, nhưng nếu chứa event có mức độ nhạy cảm khác nhau thì quyền READ trên topic sẽ cho phép consumer đọc toàn bộ record trong topic. Khi không thể phân quyền ở mức record tại broker, hãy tách topic theo security boundary hoặc thiết kế payload chỉ chứa dữ liệu mà tất cả subscriber được phép nhận.

## 10. Không tin metadata do producer tự khai báo

Các field như tenantId, actorId, role, scope hoặc header authorized=true có thể được producer ghi vào payload/header. Consumer không nên xem chúng là bằng chứng authorization chỉ vì chúng có mặt trong message.

Hãy xác minh:

- Principal producer đã được broker xác thực và có quyền ghi topic chưa?
- Event có được tạo từ nguồn tin cậy theo hợp đồng không?
- Tenant và business key có khớp với dữ liệu mà consumer được phép truy cập không?
- ActorId chỉ dùng cho audit hay được dùng trong một cơ chế delegated authorization có chữ ký/validation?
- Payload có thể bị sửa hoặc replay từ nguồn không tin cậy không?

Nếu cần chứng minh nguồn gốc event qua nhiều hệ thống, có thể dùng chữ ký số hoặc cơ chế integrity phù hợp với kiến trúc. Chữ ký giúp phát hiện sửa đổi và xác minh nguồn phát theo key được tin cậy; nó vẫn không thay thế việc kiểm tra consumer có quyền thực hiện hành động trên tài nguyên cụ thể.

## 11. Thu hồi quyền và quản lý vòng đời principal

Quyền consume cần được quản lý theo vòng đời service:

1. Tạo principal riêng cho workload.
2. Cấp ACL tối thiểu trên topic và group cần dùng.
3. Triển khai consumer và xác minh kết nối/assignment.
4. Theo dõi lỗi authorization và các lần truy cập bị từ chối.
5. Khi đổi topic hoặc group, cấp quyền mới rồi chuyển workload có kiểm soát.
6. Khi ngừng service, thu hồi ACL, credential và certificate không còn dùng.

Với credential có thể xoay vòng, hỗ trợ giai đoạn overlap ngắn để rollout không làm gián đoạn consumer. Sau khi tất cả instance dùng credential mới, thu hồi credential cũ. Không chia sẻ một mật khẩu giữa nhiều service vì sẽ khó xác định nguồn truy cập và thu hồi riêng.

Khi thu hồi ACL, cần lưu ý consumer đang chạy có thể giữ kết nối hoặc assignment cho đến lần xác thực/ủy quyền tiếp theo tùy broker và cơ chế bảo mật. Hãy xác minh hành vi của môi trường Kafka và có quy trình ngắt kết nối/restart khi cần để quyền bị thu hồi có hiệu lực như mong đợi.

## 12. Kiểm thử authorization

Kiểm thử phân quyền cần bao gồm cả trường hợp được phép và bị từ chối. Chỉ kiểm tra consumer đọc được message không chứng minh ACL đã tối thiểu; cần xác minh một principal không thể đọc topic hoặc group ngoài phạm vi.

Các trường hợp nên kiểm tra:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Principal hợp lệ, topic được cấp READ | Consumer subscribe và đọc được record. |
| Principal không có topic READ | Broker từ chối thao tác consume. |
| Principal có topic READ nhưng không có group READ | Consumer không thể sử dụng group bị giới hạn. |
| Consumer yêu cầu topic ngoài ACL | Broker từ chối; không có dữ liệu ngoài phạm vi được trả về. |
| Principal chỉ có READ | Không thể ghi topic hoặc thực hiện thao tác quản trị ngoài quyền. |
| Hai service có group riêng | Mỗi subscriber đọc theo offset riêng và không dùng chung quyền không cần thiết. |
| Tenant không được phép | Handler từ chối trước khi đọc/ghi tài nguyên tenant đó. |
| Tenant hợp lệ nhưng resource không thuộc quyền | Data authorization ngăn truy cập tài nguyên. |
| Event giả mạo role/authorized header | Consumer không dùng header đó làm bằng chứng quyền. |
| Secret bị xoay vòng/thu hồi | Consumer dùng credential mới; credential cũ bị từ chối theo quy trình. |
| Listener bất đồng bộ | Authorization không phụ thuộc SecurityContext request bị mất hoặc thread khác. |

Nên có integration test với broker cấu hình security thật hoặc môi trường kiểm thử tương đương. Unit test cho policy service vẫn hữu ích, nhưng không xác minh được ACL broker, principal mapping, TLS hoặc quyền consumer group.

## 13. Quan sát và điều tra lỗi authorization

Theo dõi lỗi xác thực và phân quyền riêng với lỗi deserialize hoặc lỗi nghiệp vụ. Các tín hiệu hữu ích gồm:

- Số lần authentication failure theo principal.
- Số lần authorization denied theo topic, group và operation.
- Consumer group không thể join hoặc commit offset do thiếu quyền.
- Các lần truy cập topic ngoài allowlist.
- Tenant/resource authorization denied trong handler.
- Credential sắp hết hạn hoặc certificate sắp hết hạn.
- Các lần thay đổi ACL, principal và group permission.

Log nên ghi principal đã được broker xác thực, topic, group, operation và mã lỗi authorization. Ở tầng ứng dụng, ghi eventId, eventType, tenantId đã được kiểm tra và policy decision; không ghi credential hoặc toàn bộ payload nhạy cảm.

Khi điều tra consumer không đọc được event, kiểm tra lần lượt authentication mechanism, principal broker nhìn thấy, ACL topic, ACL group, topic subscription, group ID và lỗi từ listener container. Nếu broker cho phép consume nhưng handler từ chối tenant/resource, điều tra policy ứng dụng riêng thay vì nới ACL topic một cách không cần thiết.

## 14. Checklist phân quyền consume

- Mỗi workload có principal riêng và cơ chế authentication đáng tin cậy.
- Broker ACL giới hạn READ trên đúng topic và consumer group.
- Consumer không có WRITE/CREATE/ALTER/ALL nếu không có yêu cầu rõ ràng.
- Group ID ổn định theo subscriber logic; các instance cùng subscriber dùng chung group.
- Topic chứa dữ liệu nhạy cảm được tách theo security boundary hoặc payload được tối thiểu hóa.
- Spring application events nội bộ được hiểu đúng là dispatch trong application context, không có ACL listener mặc định.
- Module boundary và public event contract được kiểm tra, nhưng không bị xem là authorization thay thế.
- Handler kiểm tra quyền nghiệp vụ và tenant/resource trước khi thực hiện side effect.
- SecurityContext bất đồng bộ không bị giả định là tự động được truyền an toàn.
- Actor/tenant metadata chỉ dùng theo mục đích đã xác định; không tin role hoặc authorized header do producer khai báo.
- Secret được quản lý ngoài source code và có quy trình rotate/revoke.
- Integration test bao phủ quyền cho phép, từ chối, group, topic, tenant và credential rotation.
- Audit log và dashboard theo dõi principal, topic, group và quyết định authorization.

Phân quyền consume cần kết hợp danh tính workload, ACL của broker và kiểm tra quyền nghiệp vụ trong consumer. Khi mỗi service chỉ đọc topic và group cần thiết, handler kiểm tra tenant/tài nguyên trước khi xử lý, còn event payload không mang credential hoặc quyền tự khai báo, giao tiếp bằng application events có thể mở rộng mà vẫn giữ được ranh giới bảo mật rõ ràng.
