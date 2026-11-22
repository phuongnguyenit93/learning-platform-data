# Runbook khi authentication lỗi trong vận hành Spring Kafka

## 1. Mục tiêu và phạm vi

Runbook này hướng dẫn đội vận hành xử lý sự cố khi ứng dụng Spring Boot sử dụng Spring Kafka không thể xác thực với Kafka broker. Mục tiêu là xác định đúng lớp gây lỗi, khôi phục kết nối có kiểm soát, giữ lại bằng chứng phục vụ điều tra và tránh làm lộ credential trong lúc xử lý.

Trong Kafka, cần phân biệt ba lớp:

1. **Transport và TLS:** client có thiết lập được kết nối và xác minh certificate của broker hay không.
2. **Authentication:** broker có xác minh được danh tính client qua SASL hoặc mTLS hay không.
3. **Authorization:** principal đã xác thực có được phép thực hiện thao tác trên topic, consumer group hoặc tài nguyên Kafka hay không.

Một số lỗi xuất hiện gần nhau trong log nhưng cần cách xử lý khác nhau. Ví dụ, **SaslAuthenticationException** thường chỉ ra lỗi xác thực SASL; **SSLHandshakeException** xảy ra ở lớp TLS; **TopicAuthorizationException** hoặc **GroupAuthorizationException** thường cho biết principal đã được xác thực nhưng thiếu quyền. Không thay password hoặc cấp thêm ACL trước khi xác định đúng lớp lỗi.

Runbook áp dụng cho các cấu hình phổ biến:

- **SASL_SSL:** TLS mã hóa kết nối và SASL xác thực principal.
- **SASL_PLAINTEXT:** SASL không có lớp mã hóa TLS; chỉ dùng khi kiến trúc và chính sách cho phép, không phải lựa chọn production thông thường.
- **SSL:** TLS xác minh broker, có thể dùng mTLS để xác minh client.
- OAuth/OAUTHBEARER, SCRAM hoặc PLAIN tùy cơ chế mà Kafka cluster hỗ trợ.

## 2. Nhận diện và phân loại sự cố

### 2.1. Dấu hiệu thường gặp

| Dấu hiệu trong log hoặc triệu chứng | Lớp nghi ngờ | Ý nghĩa và hướng xử lý đầu tiên |
|---|---|---|
| SaslAuthenticationException | SASL authentication | Kiểm tra cơ chế SASL, principal, credential hoặc token |
| Authentication failed / Invalid username or password | SASL authentication | Xác minh secret version, trạng thái principal và credential ở broker |
| SSLHandshakeException | TLS | Kiểm tra truststore, certificate, hostname, thời hạn và yêu cầu mTLS |
| PKIX path building failed | TLS trust | Client không xây dựng được chuỗi CA tin cậy |
| No subject alternative DNS name matching | TLS hostname | Hostname kết nối không khớp SAN của certificate |
| Unexpected Kafka request of type ... during SASL handshake | Protocol/listener | Client và listener có thể đang dùng security protocol không tương thích |
| Unsupported SASL mechanism | SASL mechanism | Mechanism client yêu cầu chưa được listener/broker bật hoặc không khớp |
| TopicAuthorizationException | Authorization | Principal thiếu quyền trên topic hoặc thao tác tương ứng |
| GroupAuthorizationException | Authorization | Principal thiếu quyền với consumer group |
| Consumer liên tục rejoin hoặc producer retry sau khi credential đổi | Kết nối/client lifecycle | Một số instance có thể vẫn giữ credential hoặc client cũ |

Log của Spring Kafka thường bọc lỗi gốc trong nhiều exception như KafkaException, ListenerExecutionFailedException hoặc lỗi khởi tạo consumer. Hãy lần theo chuỗi Caused by đến exception sâu nhất và ghi nhận broker, client ID, thời điểm cùng thao tác bị lỗi. Không kết luận chỉ dựa trên dòng log đầu tiên.

### 2.2. Phân biệt authentication và authorization

Authentication trả lời câu hỏi “client là ai?”. Authorization trả lời câu hỏi “principal này được phép làm gì?”. Một client có thể xác thực thành công nhưng không được phép đọc topic, ghi topic hoặc tham gia consumer group.

| Kết quả | Việc cần làm |
|---|---|
| TLS handshake thất bại | Điều tra certificate, trust và hostname trước |
| TLS thành công, SASL thất bại | Điều tra SASL mechanism, JAAS, credential hoặc token |
| SASL thành công, request bị từ chối vì ACL | Kiểm tra principal và ACL tối thiểu cần thiết |
| CLI hoạt động nhưng ứng dụng lỗi | So sánh cấu hình, secret version, runtime và client properties của ứng dụng |
| Chỉ một số pod lỗi | So sánh image, secret version, thời điểm rollout và trạng thái từng pod |

### 2.3. Xác định phạm vi ảnh hưởng

Trước khi thay đổi cấu hình, xác định:

- Sự cố ảnh hưởng một ứng dụng, một nhóm pod, một broker listener hay toàn cluster.
- Chỉ producer, chỉ consumer, Kafka Admin hay tất cả client đều lỗi.
- Một principal hay nhiều principal bị ảnh hưởng.
- Lỗi bắt đầu sau lần deploy, rotation secret, thay certificate, đổi ACL, nâng cấp broker hoặc thay đổi mạng nào.
- Sự cố có làm mất dữ liệu, tăng lag, tăng retry, làm đầy queue nội bộ hoặc ảnh hưởng SLA hay không.

Ghi lại thời điểm bắt đầu, thời điểm phát hiện, môi trường, namespace, deployment, pod, client ID, principal (nếu log cho phép), bootstrap endpoint, broker được kết nối và correlation/request ID nếu có. Không ghi password, token, private key hoặc nội dung JAAS đầy đủ vào ticket.

## 3. Quy trình phản ứng ban đầu

### Bước 1 — Mở incident và giữ bằng chứng

Tạo hoặc cập nhật incident theo quy trình trực vận hành. Ghi nhận người xử lý, thời gian, phạm vi, dịch vụ bị ảnh hưởng và thay đổi gần nhất. Thu thập log trong khoảng thời gian có lỗi từ ứng dụng và broker nếu có quyền truy cập.

Khi thu thập log:

- Giới hạn khoảng thời gian và workload cần kiểm tra.
- Kiểm tra log có vô tình chứa username, password, token, JAAS config hoặc dữ liệu nhạy cảm hay không trước khi chia sẻ.
- Không bật debug toàn bộ Kafka hoặc TLS trên toàn cluster nếu chưa cần thiết.
- Nếu cần tăng log level, chỉ bật trong phạm vi nhỏ và thời gian ngắn; ghi lại thời điểm bật/tắt.
- Bảo vệ log incident theo chính sách truy cập và thời hạn lưu trữ của tổ chức.

### Bước 2 — Kiểm tra tình trạng ứng dụng

Xác định ứng dụng có đang chạy ổn định hay bị crash/restart. Kiểm tra readiness/liveness, số lần restart, deployment revision, image version và thời điểm pod được tạo.

Với Kubernetes, các lệnh sau giúp kiểm tra metadata và log mà không đọc giá trị Secret:

~~~bash
kubectl get pods -n <namespace> -l app=<application> -o wide
kubectl describe pod -n <namespace> <pod-name>
kubectl logs -n <namespace> <pod-name> --since=15m
kubectl logs -n <namespace> <pod-name> --previous
~~~

kubectl describe pod có thể hiển thị event và tham chiếu Secret; hãy rà soát output trước khi gửi ra ngoài. Log ứng dụng cũng cần được kiểm tra để chắc chắn không chứa credential.

So sánh pod lỗi với pod đang hoạt động nếu chỉ một phần replica bị ảnh hưởng. Kiểm tra rollout có hoàn tất không, pod có đang dùng cùng image và cấu hình dự kiến không, volume secret có được mount không, và service account có quyền đọc nguồn cấp secret không.

### Bước 3 — Kiểm tra mạng và TLS

Xác minh DNS, route, firewall và cổng listener từ đúng môi trường chạy ứng dụng. Với SASL_SSL, TLS handshake diễn ra trước SASL authentication. Nếu TLS chưa thành công, điều tra SASL ở bước này sẽ không giúp ích.

Kiểm tra các điểm:

1. Bootstrap hostname phân giải về địa chỉ dự kiến và cổng listener có thể truy cập.
2. Certificate broker còn hạn, chain được tin cậy và SAN chứa hostname client sử dụng.
3. Client dùng đúng truststore và truststore đang chứa CA hiện hành.
4. Nếu bật mTLS, client có certificate và private key phù hợp; broker tin CA cấp certificate client.
5. Sau bootstrap, hostname trong advertised listener của từng broker cũng phải hợp lệ với certificate.

Có thể dùng OpenSSL để kiểm tra handshake từ môi trường có công cụ:

~~~bash
openssl s_client -connect broker.example.com:9093 -servername broker.example.com -showcerts -verify_return_error
~~~

Kết quả của OpenSSL chỉ kiểm tra đường TLS từ máy chạy lệnh. Nó không xác nhận truststore riêng, JAAS, SASL hay cấu hình JVM của ứng dụng. Không tắt hostname verification hoặc dùng trust-all để làm cho phép thử thành công.

### Bước 4 — Xác định protocol và SASL mechanism

Đối chiếu cấu hình client với listener mà bootstrap endpoint trỏ tới. Kiểm tra tối thiểu:

- security.protocol: SASL_SSL, SASL_PLAINTEXT, SSL hoặc PLAINTEXT.
- sasl.mechanism: ví dụ SCRAM-SHA-512, SCRAM-SHA-256, PLAIN hoặc OAUTHBEARER.
- JAAS login module phù hợp với mechanism.
- Listener broker đã bật mechanism tương ứng.
- Nếu có nhiều listener, listener.security.protocol.map và advertised listener có đúng ánh xạ.

Client dùng SASL_SSL không thể kết nối đúng vào listener chỉ chấp nhận SSL hoặc SASL_PLAINTEXT. Tương tự, cơ chế SCRAM-SHA-512 ở client phải được cluster hỗ trợ và principal phải có credential SCRAM phù hợp. Đừng thử nhiều mechanism ngẫu nhiên trên production; xác minh cấu hình listener và cấu hình triển khai đang được phê duyệt.

### Bước 5 — Kiểm tra nguồn cấp credential

Kiểm tra metadata và trạng thái cấp phát:

- Secret có tồn tại trong namespace hoặc secret manager đúng không.
- Workload có tham chiếu đúng tên và key không.
- Service account hoặc workload identity có quyền đọc secret không.
- Secret version hoặc revision được rollout có đúng phiên bản đã phê duyệt không.
- Giá trị có bị thiếu, rỗng, chứa newline ngoài ý muốn hoặc bị thay đổi bởi template/escaping không.
- Có pod nào vẫn chạy với secret cũ do chưa được restart hoặc chưa nạp lại cấu hình không.

Không dùng kubectl get secret -o yaml, printenv, env, set, debug dump hay lệnh tương tự để in dữ liệu nhạy cảm vào terminal/log. Nếu cần xác minh biến đã được cấp mà không đọc giá trị, có thể kiểm tra sự hiện diện trong container:

~~~bash
kubectl exec -n <namespace> <pod-name> -- sh -c 'test -n "$KAFKA_USERNAME" && test -n "$KAFKA_PASSWORD" && echo "Kafka credential variables are present"'
~~~

Lệnh trên chỉ kiểm tra hai biến có giá trị hay không. Nó không chứng minh credential đúng hoặc principal còn hiệu lực. Với secret dạng file, kiểm tra file tồn tại, quyền truy cập và metadata như thời gian cập nhật; không in nội dung private key hoặc keystore password.

### Bước 6 — Xác minh principal và cơ chế xác thực

Khi đã xác nhận TLS và protocol đúng, đối chiếu principal với cơ chế đang dùng:

- **SCRAM:** username phải trỏ tới principal tồn tại; credential SCRAM phải được provision trên cluster đang kết nối. Kiểm tra rotation có tạo principal/credential mới nhưng workload vẫn dùng credential cũ hay không.
- **PLAIN:** username/password phải khớp với nguồn xác thực của broker. Chỉ sử dụng qua TLS trong môi trường cần bảo vệ credential trên đường truyền.
- **OAuth/OAUTHBEARER:** kiểm tra token còn hạn, issuer, audience, scope/claim cần thiết, clock skew, khả năng truy cập token endpoint và JWKS/introspection endpoint theo thiết kế.
- **mTLS:** kiểm tra certificate client được trình ra, chain và CA mà broker tin cậy; xác minh principal mapping nếu broker dùng certificate để tạo principal.

Nếu nhiều client dùng cùng một principal cùng lỗi tại một thời điểm, ưu tiên kiểm tra thay đổi phía broker, credential store hoặc listener. Nếu chỉ một deployment lỗi sau rollout, ưu tiên kiểm tra secret reference, config binding và phiên bản image của deployment đó.

### Bước 7 — Phân biệt lỗi ACL

Nếu authentication đã thành công nhưng thao tác bị từ chối, kiểm tra ACL của đúng principal, topic và consumer group. Producer có thể cần quyền ghi topic; consumer có thể cần quyền đọc topic và quyền phù hợp với group; Admin client có thể cần quyền bổ sung theo lệnh quản trị.

Không cấp quyền * hoặc quyền quản trị toàn cluster chỉ để làm hết lỗi. Yêu cầu quyền phải chỉ rõ principal, resource, operation và lý do nghiệp vụ. Nếu principal mapping thay đổi, ACL cũ có thể không còn khớp dù certificate hoặc SASL credential vẫn hợp lệ.

## 4. Các nhánh xử lý theo cơ chế xác thực

### 4.1. SCRAM

Triệu chứng điển hình là SaslAuthenticationException hoặc broker ghi nhận xác thực SCRAM thất bại. Kiểm tra:

1. Client và listener cùng dùng đúng SCRAM mechanism.
2. JAAS login module là org.apache.kafka.common.security.scram.ScramLoginModule.
3. Username được phân giải từ nguồn secret đúng.
4. Principal tồn tại trên cluster và credential được tạo cho đúng SCRAM mechanism.
5. Sau rotation, tất cả instance đã nhận secret version mới và tạo lại Kafka client.
6. Credential cũ chưa bị thu hồi trước khi workload chuyển xong sang credential mới.

Ví dụ cấu hình Spring Boot (chỉ chứa placeholder):

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
~~~

Không log sasl.jaas.config. Nếu phải thay credential, ưu tiên tạo principal mới với quyền tối thiểu, triển khai và xác minh toàn bộ instance, sau đó mới thu hồi principal cũ khi nền tảng cho phép quy trình này.

### 4.2. PLAIN

PLAIN truyền thông tin xác thực trong payload SASL; cơ chế này không tự mã hóa password. Nếu ứng dụng dùng PLAIN, xác nhận listener đang dùng SASL_SSL và TLS handshake thành công trước khi kiểm tra credential. Kiểm tra username/password, nguồn xác thực broker và thời điểm cập nhật credential.

Nếu phát hiện PLAIN đang chạy trên kết nối không mã hóa trong môi trường production, ghi nhận đây là vấn đề cấu hình bảo mật cần xử lý theo quy trình thay đổi. Không tự ý đổi listener trong lúc incident nếu chưa đánh giá ảnh hưởng tới các client khác.

### 4.3. OAuth/OAUTHBEARER

Khi token bị từ chối, kiểm tra các nhóm nguyên nhân:

- Token đã hết hạn hoặc chưa có hiệu lực.
- Đồng hồ ứng dụng, broker hoặc identity provider lệch đáng kể.
- Issuer hoặc audience không đúng với cấu hình broker.
- Claim, scope hoặc role không đáp ứng chính sách.
- Token endpoint, JWKS endpoint hoặc introspection endpoint không truy cập được.
- Client secret dùng để lấy token sai, hết hạn hoặc bị thu hồi.
- Cơ chế refresh không chạy, token callback trả token cũ hoặc không cập nhật credential mới.

Không ghi token vào log để so sánh. Dùng metadata không nhạy cảm như exp, iss, aud, key ID và request ID nếu hệ thống cho phép, đồng thời bảo đảm các claim được trích xuất không tiết lộ dữ liệu cá nhân hoặc thông tin nội bộ không cần thiết. Nếu token endpoint lỗi, xác định rõ lỗi mạng, lỗi client authentication hay lỗi policy của identity provider.

Khi token có thời hạn ngắn, kiểm tra thời gian refresh và khả năng lấy token mới của từng Kafka client. Nếu callback hoặc provider tùy chỉnh bị lỗi, kiểm tra exception và metric của provider mà không dump token.

### 4.4. TLS client authentication (mTLS)

Nếu broker yêu cầu mTLS, client phải trình certificate hợp lệ. Kiểm tra certificate đang được mount, private key tương ứng, password/alias của keystore, certificate chain, thời hạn, Key Usage/Extended Key Usage và CA mà broker tin cậy.

Kiểm tra principal mapping trên broker nếu danh tính được suy ra từ subject hoặc SAN của certificate. Certificate hợp lệ về mặt TLS vẫn có thể map thành principal khác với principal được cấp ACL. Trong trường hợp đó, lỗi thao tác có thể là authorization thay vì handshake.

Không thay certificate client hàng loạt khi chưa xác nhận CA mới đã được broker tin cậy. Nếu đổi CA, triển khai trust cho CA mới theo giai đoạn chuyển tiếp trước khi chuyển client certificate.

## 5. Kiểm tra bằng Kafka CLI

Kafka CLI có thể giúp tách lỗi của ứng dụng khỏi lỗi của broker hoặc credential. Chỉ chạy từ môi trường được phép và dùng file cấu hình client đã được cấp qua secret store hoặc file mount có quyền truy cập giới hạn.

Ví dụ file cấu hình client tham chiếu placeholder (không điền credential thật vào tài liệu hoặc ticket):

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
ssl.truststore.location=/etc/kafka/tls/truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=<injected-at-runtime>
ssl.endpoint.identification.algorithm=https
~~~

Trong môi trường thật, file phải được tạo hoặc mount bằng quy trình quản lý secret; placeholder ở đây không phải giá trị hợp lệ để chạy lệnh. Giới hạn quyền đọc file và xóa file tạm theo chính sách sau khi sử dụng. Tránh đưa password vào command-line arguments vì có thể lộ qua process list, shell history hoặc log.

Có thể kiểm tra broker API và kết nối:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server broker.example.com:9093 --command-config /run/secrets/kafka/client.properties
~~~

Nếu cần kiểm tra producer/consumer, dùng cùng file cấu hình được bảo vệ:

~~~bash
kafka-console-producer.sh --bootstrap-server broker.example.com:9093 --producer.config /run/secrets/kafka/client.properties --topic <test-topic>
kafka-console-consumer.sh --bootstrap-server broker.example.com:9093 --consumer.config /run/secrets/kafka/client.properties --topic <test-topic> --group <test-group> --from-beginning
~~~

Chỉ sử dụng topic và group thử nghiệm được phê duyệt. Lệnh producer có thể ghi dữ liệu thật; lệnh consumer có thể tạo group hoặc ảnh hưởng offset tùy tham số. Không chạy trên topic production hoặc group của ứng dụng đang hoạt động nếu chưa đánh giá tác động.

Nếu CLI thành công nhưng Spring Kafka lỗi, so sánh:

- File cấu hình CLI với các property thực tế của Kafka client trong ứng dụng.
- Secret version, service account, mount path và quyền đọc file.
- Java runtime, truststore mặc định, hostname và DNS trong container.
- security.protocol, SASL mechanism, JAAS login module và endpoint.
- Client ID, principal mapping và ACL.
- Thời điểm client được tạo so với thời điểm secret được rotation.

Nếu cả CLI và ứng dụng cùng lỗi, tập trung điều tra broker listener, credential store, identity provider, CA hoặc thay đổi hạ tầng chung.

## 6. Khôi phục dịch vụ có kiểm soát

### 6.1. Chọn hành động theo nguyên nhân

| Nguyên nhân đã xác nhận | Hành động khôi phục |
|---|---|
| Secret reference sai hoặc thiếu | Sửa tham chiếu tới secret version được phê duyệt, rollout workload và xác minh |
| Credential đã hết hạn hoặc bị thu hồi | Provision credential mới, cập nhật secret store, rollout client và thu hồi credential cũ theo kế hoạch |
| SASL mechanism hoặc protocol sai | Khôi phục cấu hình listener/client đã được phê duyệt qua quy trình change |
| Certificate hoặc CA không hợp lệ | Cấp/cập nhật certificate hoặc truststore theo quy trình PKI, sau đó reload/restart client cần thiết |
| OAuth token endpoint hoặc issuer lỗi | Khôi phục luồng cấp token hoặc cấu hình identity provider; xác minh token mới |
| ACL thiếu | Cấp đúng quyền cho principal và resource sau khi xác nhận yêu cầu |
| Một số pod còn giữ client cũ | Rollout có kiểm soát để tạo client mới và kiểm tra từng replica |

### 6.2. Triển khai credential hoặc cấu hình mới

Trước khi rollout:

1. Xác nhận secret version hoặc cấu hình mới đã được tạo và phê duyệt.
2. Kiểm tra quyền truy cập nguồn secret và file mount.
3. Xác định hành vi nạp lại cấu hình của Spring Boot và Kafka client đang dùng.
4. Chuẩn bị thứ tự rollout, tiêu chí thành công và cách quay lại phiên bản trước nếu còn hợp lệ.
5. Bảo đảm broker hoặc identity provider chấp nhận credential mới trong suốt giai đoạn chuyển tiếp.

Sau khi rollout:

1. Kiểm tra pod mới đã Ready và dùng đúng image/config revision.
2. Xác nhận log không còn lỗi TLS/SASL authentication.
3. Xác nhận producer gửi được một bản tin thử nghiệm vào tài nguyên được phê duyệt.
4. Xác nhận consumer đọc được bản tin thử nghiệm và group hoạt động bình thường.
5. Theo dõi retry, consumer lag, rebalance, throughput và error rate.
6. Xác minh tất cả replica đã chuyển sang secret version mới trước khi thu hồi credential cũ.

Không giả định file Secret được cập nhật sẽ làm Kafka client đang chạy tự nạp lại credential. Tùy cách cấu hình, Spring Boot có thể chỉ đọc property khi khởi tạo bean; Kafka client có thể giữ JAAS login module hoặc SSL context đã được tạo trước đó. Nếu chưa có cơ chế reload được kiểm thử, dùng rolling restart hoặc tái tạo bean/client theo quy trình triển khai.

### 6.3. Rollback

Rollback chỉ an toàn nếu credential hoặc certificate cũ vẫn còn hiệu lực và chưa bị thu hồi. Trước khi quay lại:

- Kiểm tra credential cũ có còn được broker hoặc identity provider chấp nhận không.
- Kiểm tra CA cũ còn trong truststore và chưa bị thu hồi.
- Kiểm tra ACL của principal cũ còn đúng và không vượt quyền.
- Xác nhận rollback không đưa một secret đã lộ trở lại hệ thống.
- Ghi nhận phiên bản cấu hình, secret reference và thời điểm rollback.

Nếu credential cũ đã bị thu hồi vì nghi ngờ lộ, không khôi phục nó để giảm thời gian gián đoạn. Cần hoàn tất cấp credential mới hoặc dùng phương án dự phòng đã được phê duyệt.

## 7. Tiêu chí xác nhận sự cố đã được xử lý

Chỉ đóng incident sau khi các điều kiện phù hợp với phạm vi sự cố đã đạt:

- TLS handshake thành công từ workload bị ảnh hưởng và hostname verification vẫn được bật.
- SASL hoặc mTLS authentication thành công với principal dự kiến.
- Producer/consumer thực hiện được thao tác được cấp quyền.
- Không còn lỗi authentication/authorization tăng bất thường trong cửa sổ theo dõi.
- Tất cả replica dùng đúng secret/certificate/config revision.
- Consumer lag và retry trở về mức vận hành chấp nhận được; không còn backlog tăng liên tục.
- Credential cũ được thu hồi đúng kế hoạch nếu rotation là một phần của khắc phục.
- Log và metric không để lộ secret; debug logging đã được tắt.

Với consumer, kiểm tra cả consumer group và offset/lag. Một consumer có thể đã xác thực thành công nhưng không đọc được dữ liệu do thiếu ACL, hoặc bị rebalance liên tục vì lỗi khác. Với producer, xác minh acknowledgment và kết quả ghi theo delivery semantics đang cấu hình; không chỉ dựa vào việc socket đã mở.

## 8. Khi nào cần nâng cấp mức độ incident

Nâng cấp hoặc gọi đúng đội phụ trách khi:

- Nhiều ứng dụng hoặc nhiều principal đồng thời không xác thực được.
- Broker listener, CA, secret manager hoặc identity provider có dấu hiệu lỗi diện rộng.
- Credential bị lộ, bị sử dụng trái phép hoặc có truy cập bất thường.
- Rotation làm gián đoạn nhiều workload hoặc không thể xác định credential nào còn hiệu lực.
- Có nguy cơ mất dữ liệu, vi phạm SLA, consumer lag vượt ngưỡng hoặc producer không thể ghi trong thời gian dài.
- Cần thay đổi listener, broker configuration, CA trust hoặc policy trên diện rộng.

Đầu mối phối hợp thường gồm đội Kafka/platform, đội quản lý danh tính hoặc PKI, đội ứng dụng và đội an ninh theo quy trình tổ chức. Khi chuyển giao, cung cấp timestamp, phạm vi, broker/listener, client ID, principal đã được phép chia sẻ, exception gốc, thay đổi gần nhất và các bước đã thực hiện. Không gửi credential, token hoặc private key qua kênh incident.

## 9. Mẫu ghi nhận incident

Có thể dùng mẫu sau để ghi lại quá trình xử lý:

~~~text
Incident ID:
Environment / Namespace:
Application / Deployment:
Affected pods:
First observed at (UTC):
Last known good time:
Kafka bootstrap endpoint / listener:
Client ID:
Authentication mechanism:
Principal (if permitted):
Observed exception / root cause:
Affected operations: produce / consume / admin
Scope: one pod / one application / multiple applications / cluster-wide
Recent changes: deploy / secret rotation / certificate / ACL / broker / network
Evidence references: application logs / broker logs / metrics / audit events
Confirmed cause:
Recovery action:
Validation results:
Credential or certificate retired:
Follow-up owner:
Incident closed at:
~~~

Chỉ ghi metadata cần thiết. Không đưa password, token, JAAS string, private key hoặc nội dung Secret vào mẫu.

## 10. Phòng ngừa tái diễn

Sau incident, xác định vì sao hệ thống phát hiện chậm hoặc vì sao thao tác khôi phục khó thực hiện. Các biện pháp thường hữu ích:

- Tách metric và alert cho TLS handshake failure, SASL authentication failure và authorization failure.
- Theo dõi tỷ lệ kết nối thất bại theo client ID, principal, listener và broker; tránh gắn secret vào label metric.
- Cảnh báo trước thời điểm credential/certificate hết hạn với đủ thời gian cấp mới và rollout.
- Tự động kiểm tra secret reference, quyền đọc và certificate metadata trong pipeline mà không in giá trị bí mật.
- Chuẩn hóa cấu hình Kafka client để producer, consumer và admin dùng cùng chính sách bảo mật.
- Kiểm thử rotation trên môi trường staging với cùng cơ chế cấp secret và vòng đời Kafka client như production.
- Duy trì credential dự phòng hoặc quy trình cấp lại đã được phê duyệt; không chia sẻ principal giữa nhiều ứng dụng.
- Thực hành runbook định kỳ, gồm cả tình huống OAuth provider lỗi, CA rotation và credential bị thu hồi khẩn cấp.
- Rà soát ACL theo owner và nhu cầu thực tế, loại bỏ quyền dư thừa sau thay đổi ứng dụng.

Một runbook hữu ích cần có owner, phiên bản, ngày rà soát, đường dẫn tới dashboard và quy trình escalation nội bộ. Cập nhật tài liệu sau mỗi sự cố hoặc thay đổi kiến trúc Kafka để các bước phản ánh đúng listener, cơ chế SASL, nguồn secret và công cụ đang vận hành.

## 11. Nguyên tắc xử lý cốt lõi

Khi authentication lỗi, hãy xác định đúng giai đoạn thất bại: TLS, SASL/mTLS hay authorization. Thu thập bằng chứng có kiểm soát, đối chiếu cấu hình và secret version, sau đó khôi phục theo từng thay đổi nhỏ có thể xác minh. Không in credential ra log, không tắt xác minh certificate, không cấp ACL rộng để che lỗi và không thu hồi credential cũ trước khi client đã chuyển sang credential mới trừ khi cần ứng phó việc lộ bí mật. Dịch vụ chỉ được coi là phục hồi khi workload thực hiện lại được thao tác Kafka cần thiết và các chỉ số vận hành đã ổn định.
