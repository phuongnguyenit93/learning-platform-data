# Không log password hoặc token

Trong một hệ thống Spring Kafka, log là công cụ quan trọng để điều tra lỗi kết nối broker, theo dõi producer và consumer, phân tích độ trễ, cũng như xử lý sự cố trong production. Tuy nhiên, log cũng có thể trở thành nơi rò rỉ thông tin xác thực nếu ứng dụng ghi password, access token, refresh token hoặc khóa bí mật ra đầu ra log.

Nguyên tắc vận hành là **không ghi secret vào log ở bất kỳ cấp độ nào**: `TRACE`, `DEBUG`, `INFO`, `WARN` hay `ERROR`. Secret không được xuất hiện trong thông điệp log, tham số, stack trace, header Kafka, dữ liệu message, log khởi động, bản dump cấu hình hoặc log của pipeline triển khai. Khi cần chẩn đoán, hãy ghi lại ngữ cảnh vận hành đã được chọn lọc và an toàn, chẳng hạn tên thao tác, topic, partition, offset, consumer group và mã tương quan không nhạy cảm.

## Vì sao password và token không được xuất hiện trong log?

Password và token là thông tin cho phép một cá nhân hoặc tiến trình chứng minh danh tính và thực hiện hành động được cấp quyền. Người có được secret có thể sử dụng nó để đăng nhập, gọi API, đọc hoặc ghi dữ liệu Kafka, hoặc truy cập một dịch vụ khác tùy theo phạm vi quyền của credential đó.

Log thường được sao chép và lưu ở nhiều nơi: máy chủ ứng dụng, container runtime, hệ thống tập trung log, nền tảng SIEM, công cụ giám sát, bản sao lưu và hệ thống hỗ trợ. Nhiều nhóm có quyền đọc log hơn nhóm được phép đọc secret. Log cũng có thể được lưu lâu hơn vòng đời của credential. Vì vậy, một dòng log vô tình chứa token có thể tạo ra một bản sao secret tồn tại ở nhiều hệ thống và khó thu hồi hoàn toàn.

Các hậu quả có thể gồm:

- **Mạo danh:** kẻ có token còn hiệu lực có thể gửi request dưới danh tính của service hoặc người dùng sở hữu token.
- **Truy cập dữ liệu trái phép:** credential Kafka có thể cho phép đọc topic, ghi message hoặc quản trị cluster ngoài phạm vi dự kiến.
- **Mở rộng phạm vi tấn công:** credential được tái sử dụng hoặc có quyền rộng có thể mở đường sang các dịch vụ khác.
- **Khó xử lý sự cố:** secret xuất hiện trong nhiều bản sao log khiến việc xác định phạm vi lộ lọt và loại bỏ dữ liệu trở nên phức tạp.

Việc log chỉ được truy cập nội bộ, nằm trong mạng riêng hoặc được bảo vệ bằng đăng nhập không làm cho hành vi ghi secret trở nên an toàn. Quyền đọc log và quyền sử dụng credential là hai loại quyền khác nhau; không nên cấp quyền sử dụng credential cho tất cả người cần điều tra log.

## Những secret thường gặp trong ứng dụng Spring Kafka

Không chỉ trường có tên `password` mới là secret. Khi vận hành Kafka, cần nhận diện toàn bộ dữ liệu có thể dùng để xác thực hoặc giải mã:

| Dữ liệu | Ví dụ | Cách xử lý trong log |
|---|---|---|
| Password SASL | Password trong `sasl.jaas.config` | Không ghi giá trị; không ghi toàn bộ chuỗi JAAS |
| Username hoặc principal | Tên tài khoản dịch vụ | Phân loại theo chính sách; nếu nhạy cảm thì dùng mã định danh thay thế |
| OAuth client secret | `client-secret` dùng lấy token | Không ghi giá trị hoặc nội dung cấu hình chứa nó |
| Access token / bearer token | JWT hoặc opaque token trong `Authorization` | Không ghi toàn bộ, một phần, hay header chứa token |
| Refresh token | Token dùng cấp access token mới | Không ghi; bảo vệ như credential dài hạn |
| Private key | Khóa riêng dùng cho TLS hoặc ký số | Không ghi nội dung khóa hoặc bản dump chứa khóa |
| Keystore / truststore password | `spring.kafka.ssl.key-store-password` | Không ghi giá trị cấu hình |
| API key hoặc credential của secret manager | Khóa truy cập dịch vụ bên ngoài | Không ghi vào log ứng dụng hoặc log triển khai |

Một số thuộc tính như `security.protocol` hoặc `sasl.mechanism` thường không phải secret. Chúng có thể hữu ích khi chẩn đoán cấu hình, nhưng vẫn cần tuân thủ chính sách phân loại thông tin của tổ chức. Không nên suy luận rằng mọi giá trị nằm cạnh một thuộc tính không nhạy cảm đều an toàn để ghi log.

Ví dụ, cấu hình có thể chứa thông tin đăng nhập SASL:

```properties
spring.kafka.properties.security.protocol=SASL_SSL
spring.kafka.properties.sasl.mechanism=PLAIN
spring.kafka.properties.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
```

Trong cấu hình trên, `KAFKA_PASSWORD` và giá trị sau khi được phân giải là secret. Không log nguyên dòng `sasl.jaas.config`, không log toàn bộ `KafkaProperties`, và không in toàn bộ `Environment` để kiểm tra cấu hình. Tên biến môi trường có thể được ghi nhận nếu chính sách cho phép, nhưng giá trị của biến phải được giữ kín.

## Các vị trí dễ vô tình ghi lộ secret

### Log cấu hình lúc khởi động

Một cách debug nguy hiểm là in toàn bộ object cấu hình:

```java
// Không an toàn: object có thể chứa password hoặc token.
log.debug("Kafka properties: {}", kafkaProperties);
```

Tương tự, không dump tất cả biến môi trường, system properties, command-line arguments hoặc cấu hình đã được bind vào bean. Những nguồn này có thể chứa secret được inject từ Kubernetes Secret, biến môi trường, CI/CD hoặc secret manager.

Thay vào đó, log một allowlist các trường phục vụ chẩn đoán và không chứa credential:

```java
log.info(
    "Kafka client configured: clientId={}, bootstrapServers={}, securityProtocol={}, saslMechanism={}",
    clientId,
    bootstrapServers,
    securityProtocol,
    saslMechanism
);
```

Chỉ đưa `bootstrapServers`, `clientId` và các trường tương tự vào log khi chúng không bị xem là thông tin nhạy cảm theo chính sách nội bộ. Không thêm username, password, JAAS config, token, private key hoặc giá trị cấu hình chưa được phân loại vào câu log này.

### Log message và header Kafka

Producer record và consumer record có thể chứa dữ liệu nghiệp vụ, thông tin cá nhân hoặc credential do hệ thống truyền qua header. Đặc biệt, một số ứng dụng đặt bearer token, API key hoặc thông tin định danh vào header để phục vụ xác thực ở tầng ứng dụng.

Không log trực tiếp toàn bộ `ProducerRecord`, `ConsumerRecord`, `Message<?>`, payload hoặc tập header:

```java
// Không an toàn: record có thể chứa payload và header nhạy cảm.
log.debug("Sending Kafka record: {}", record);

// Không an toàn: header có thể chứa Authorization hoặc API key.
log.debug("Received headers: {}", record.headers());
```

Nếu cần theo dõi luồng message, hãy chọn các trường kỹ thuật đã được cho phép:

```java
log.info(
    "Kafka message received: topic={}, partition={}, offset={}, keyPresent={}",
    record.topic(),
    record.partition(),
    record.offset(),
    record.key() != null
);
```

Ví dụ trên không ghi giá trị key, payload hoặc header. Nếu key là dữ liệu nhạy cảm, không log key; ngay cả khi key không phải secret, nó vẫn có thể chứa mã khách hàng, email hoặc định danh nghiệp vụ. Chỉ ghi `keyPresent` khi thông tin đó đủ để hỗ trợ chẩn đoán.

Khi cần trace message qua nhiều service, ưu tiên correlation ID hoặc trace ID được tạo và quản lý theo chuẩn của hệ thống. Không dùng access token, session ID, cookie hoặc một secret hiện có làm correlation ID.

### Log exception và stack trace

Stack trace hữu ích để xác định vị trí lỗi, nhưng không thể mặc định rằng mọi exception đều an toàn để ghi nguyên trạng. Exception message hoặc cause có thể chứa URL có credential, nội dung request, header, cấu hình xác thực hoặc dữ liệu đầu vào do bên ngoài kiểm soát.

Ví dụ sau có nguy cơ ghi toàn bộ dữ liệu nhạy cảm được gắn trong exception:

```java
// Chỉ dùng khi đã xác định exception và toàn bộ cause chain không chứa secret.
log.error("Kafka operation failed", exception);
```

Trong đường xử lý có khả năng chứa credential, hãy phân loại lỗi và ghi thông tin đã được kiểm soát. Có thể giữ mã lỗi, loại exception và ngữ cảnh kỹ thuật an toàn; không nối trực tiếp request, header, cấu hình hoặc nội dung xác thực vào thông điệp log.

```java
try {
    kafkaTemplate.send(topic, payload).get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    log.error(
        "Kafka send interrupted: topic={}, errorType={}",
        topic,
        ex.getClass().getSimpleName()
    );
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    log.error(
        "Kafka send failed: topic={}, causeType={}",
        topic,
        cause == null ? "unknown" : cause.getClass().getSimpleName()
    );
}
```

Đây là một mẫu thận trọng cho trường hợp exception có thể mang dữ liệu nhạy cảm. Trong các luồng khác, stack trace vẫn có thể được ghi khi đội vận hành đã xác minh rằng message và cause chain không tiết lộ secret, đồng thời chính sách log cho phép. Nếu cần giữ stack trace để điều tra, hãy áp dụng bộ lọc hoặc cơ chế chuẩn hóa đã được kiểm chứng trước khi đưa dữ liệu vào hệ thống log.

### Log ở thư viện và mức DEBUG / TRACE

Spring Kafka và Kafka client có logger riêng. Khi tăng mức log lên `DEBUG` hoặc `TRACE`, lượng thông tin nội bộ được ghi ra có thể tăng đáng kể. Tùy phiên bản thư viện và đường thực thi, log có thể chứa chi tiết cấu hình, metadata, request hoặc dữ liệu liên quan đến giao thức.

Không bật DEBUG/TRACE diện rộng trong production chỉ để tìm một lỗi xác thực. Trước khi tăng log level:

1. Xác định logger cụ thể cần quan sát, thời gian bật và người chịu trách nhiệm.
2. Kiểm tra nội dung log thực tế trong môi trường thử nghiệm với dữ liệu giả.
3. Xác nhận logger không ghi credential, payload hoặc header nhạy cảm.
4. Giới hạn thời gian và phạm vi áp dụng; đưa logger về mức bình thường sau khi điều tra.

Không dựa vào giả định rằng thư viện sẽ luôn tự che password hoặc token. Hành vi log có thể thay đổi theo phiên bản, cấu hình và loại lỗi.

## Thiết kế log an toàn bằng allowlist

Giải pháp đáng tin cậy nhất là quyết định trước những trường nào được phép xuất hiện trong từng sự kiện log. Cách tiếp cận allowlist giúp giảm nguy cơ bỏ sót một tên secret mới hoặc một header mới được thêm vào ứng dụng.

Với hoạt động Kafka, các trường thường hữu ích và có thể được cân nhắc gồm:

- Tên thao tác: `publish`, `consume`, `retry`, `commit` hoặc `dead-letter`.
- Tên topic, partition và offset, nếu các metadata này không bị phân loại là nhạy cảm.
- Consumer group hoặc client ID đã được duyệt để ghi log.
- Trace ID hoặc correlation ID không chứa credential.
- Thời lượng, số lần retry, kết quả và mã lỗi đã chuẩn hóa.
- Loại exception, nếu tên lớp không làm lộ thông tin nhạy cảm.

Những trường cần loại khỏi log gồm password, token, authorization header, cookie, API key, private key, nội dung JAAS, secret đã phân giải, toàn bộ object cấu hình, payload chưa phân loại và header chưa được duyệt. Không log một phần token để “dễ nhận diện”; một đoạn token vẫn là dữ liệu xác thực có thể bị khai thác hoặc ghép với dữ liệu khác.

Một sự kiện log có cấu trúc có thể trông như sau:

```json
{
  "event": "kafka_consume_failed",
  "topic": "orders",
  "partition": 3,
  "offset": 18420,
  "consumerGroup": "order-projection",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errorCode": "BROKER_UNAVAILABLE",
  "durationMs": 1200
}
```

Ví dụ này chỉ minh họa metadata vận hành. Tên topic, consumer group và trace ID vẫn phải tuân theo quy tắc phân loại, quyền truy cập và chính sách lưu trữ log của tổ chức. Nếu một trường có thể tiết lộ khách hàng, quy trình kinh doanh hoặc cấu trúc nội bộ, hãy giảm độ chi tiết hoặc thay bằng định danh được kiểm soát.

## Che dữ liệu và lọc log

Che dữ liệu (redaction) là lớp bảo vệ bổ sung khi hệ thống có nơi bắt buộc phải xử lý dữ liệu đầu vào chứa thông tin nhạy cảm. Ví dụ, một bộ lọc có thể loại bỏ các header `Authorization`, `Cookie` hoặc các trường có tên `password`, `access_token`, `refresh_token`, `client_secret` trước khi tạo log.

Tuy nhiên, redaction dựa trên tên trường hoặc biểu thức chính quy có thể bỏ sót secret nếu:

- Tên trường mới không nằm trong danh sách đã biết.
- Secret nằm trong chuỗi lồng nhau, JSON, URL, exception message hoặc payload nhị phân.
- Token được truyền qua một header tùy chỉnh.
- Định dạng credential thay đổi theo nhà cung cấp hoặc thư viện.

Vì vậy, hãy thiết kế luồng log để không nhận secret ngay từ đầu; chỉ dùng redaction như lớp phòng vệ bổ sung. Nếu cần một bộ lọc chung, hãy kiểm thử với nhiều dạng dữ liệu giả, bao gồm header viết hoa/thường khác nhau, JSON lồng nhau, chuỗi URL và exception có cause. Không ghi log dữ liệu gốc khi bộ lọc gặp lỗi; hành vi an toàn là loại bỏ trường không thể xử lý hoặc từ chối tạo sự kiện log chứa trường đó.

## Quản lý secret bên ngoài mã nguồn và log

Secret nên được cấp cho ứng dụng qua cơ chế quản lý secret phù hợp với môi trường triển khai, chẳng hạn secret manager hoặc Kubernetes Secret được bảo vệ. Không commit secret thật vào Git, file cấu hình mẫu, Docker image, script triển khai, lệnh chạy có thể bị lưu lịch sử hoặc log của CI/CD.

Trong ví dụ cấu hình, dùng placeholder:

```yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: PLAIN
      sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
```

Giá trị `KAFKA_SASL_JAAS_CONFIG` được cung cấp từ môi trường an toàn khi ứng dụng chạy. Không in biến này ra log để xác nhận rằng nó đã được nạp. Có thể kiểm tra trạng thái cấu hình bằng cách xác nhận bean hoặc client đã khởi tạo thành công, ghi mã trạng thái không nhạy cảm, hoặc thực hiện một health check được giới hạn quyền truy cập.

Đối với OAuth, không log request lấy token, client secret, access token hoặc refresh token. Chỉ ghi kết quả tổng quát như `authentication_succeeded`, `authentication_failed`, mã lỗi đã chuẩn hóa và thời gian xử lý. Đối với TLS, không log private key hoặc password của keystore. Nếu cần xác định chứng thư đang được dùng, hãy ghi fingerprint hoặc serial number công khai của certificate theo chính sách, không ghi private key.

## Bảo vệ hệ thống log

Ngăn secret đi vào log là biện pháp chính. Hệ thống log vẫn cần được bảo vệ vì metadata vận hành cũng có thể tiết lộ kiến trúc, tên dịch vụ, topic, nhóm tiêu thụ hoặc hoạt động của người dùng.

Các biện pháp vận hành nên bao gồm:

- **Phân quyền tối thiểu:** chỉ cấp quyền đọc log theo vai trò và nhu cầu công việc; kiểm soát riêng quyền truy vấn log production.
- **Giới hạn thời gian lưu:** xác định retention theo mục đích điều tra và yêu cầu pháp lý; tránh lưu vô thời hạn.
- **Bảo vệ khi truyền và lưu:** dùng kết nối mã hóa và cơ chế bảo vệ dữ liệu lưu trữ phù hợp.
- **Theo dõi truy cập:** lưu audit log cho thao tác truy vấn, tải xuống và chia sẻ log nhạy cảm.
- **Kiểm soát bản sao:** chú ý log được chuyển tiếp sang SIEM, hệ thống cảnh báo, ticket, chat, file đính kèm và bản sao lưu.
- **Tách quyền:** người cần đọc log để hỗ trợ vận hành không mặc nhiên được quyền lấy secret từ secret manager.

Không đưa dòng log chứa secret vào ticket, email, ảnh chụp màn hình hoặc cuộc trò chuyện hỗ trợ. Việc chia sẻ log giữa các nhóm cũng phải tuân theo chính sách phân loại dữ liệu.

## Kiểm chứng rằng ứng dụng không log secret

Kiểm chứng nên tập trung vào đầu ra log thực tế, vì chỉ xem mã nguồn không thể phát hiện mọi trường hợp thư viện hoặc exception ghi dữ liệu. Có thể dùng một secret giả có dấu hiệu nhận biết rõ trong môi trường kiểm thử, chạy các luồng khởi động, xác thực, gửi, nhận, retry và xử lý lỗi, sau đó kiểm tra log được thu thập.

Ví dụ về ý tưởng kiểm thử:

1. Tạo password và token giả như `TEST_ONLY_SECRET_7f31`.
2. Cấu hình client Kafka thử nghiệm bằng các giá trị giả đó.
3. Chạy ứng dụng với những log level được dùng trong production và một lần kiểm tra có kiểm soát ở mức DEBUG nếu cần.
4. Kích hoạt cả trường hợp thành công và thất bại, bao gồm lỗi xác thực và lỗi gửi message.
5. Tìm dấu hiệu secret giả trong log ứng dụng, log client, log container và log pipeline.
6. Xác nhận log vẫn có đủ metadata an toàn để chẩn đoán sự cố.

Trong kiểm thử tự động, có thể dùng appender thu log để xác nhận chuỗi secret giả không xuất hiện trong message hoặc phần throwable được ghi lại. Bài kiểm thử cần bao phủ cả các logger của ứng dụng và cấu hình logger thư viện có liên quan. Chỉ dùng credential giả trong kiểm thử; không sao chép password hoặc token production vào test fixture.

Ngoài kiểm thử, nên rà soát cấu hình log sau mỗi lần nâng phiên bản Spring Kafka hoặc Kafka client, thay đổi cơ chế xác thực, thêm interceptor, thay đổi header hoặc bổ sung hệ thống quan sát. Những thay đổi này có thể làm xuất hiện đường log mới.

## Khi phát hiện password hoặc token đã bị log

Hãy xem secret đã xuất hiện trong log là có khả năng bị lộ, kể cả khi chưa thấy dấu hiệu sử dụng trái phép. Quy trình xử lý nên bắt đầu bằng việc:

1. **Thu hồi hoặc xoay vòng credential:** vô hiệu hóa token, đổi password hoặc tạo credential mới theo cơ chế của hệ thống phát hành.
2. **Xác định phạm vi:** tìm các bản sao có thể chứa secret trong log tập trung, container, SIEM, cảnh báo, ticket, chat, file đính kèm và bản sao lưu.
3. **Giảm khả năng truy cập:** giới hạn quyền đọc và chia sẻ đối với các bản ghi liên quan trong khi xử lý.
4. **Loại bỏ dữ liệu theo quy trình:** xóa hoặc làm sạch bản ghi và bản sao khi nền tảng cho phép, đồng thời tuân thủ yêu cầu lưu trữ và quy trình ứng phó sự cố.
5. **Điều tra việc sử dụng:** kiểm tra audit log của Kafka, identity provider, API gateway hoặc dịch vụ phát hành credential để tìm hoạt động bất thường.
6. **Sửa nguồn phát sinh:** loại bỏ câu log không an toàn, bổ sung allowlist hoặc redaction, và thêm kiểm thử để ngăn tái diễn.

Chỉ xóa một dòng log trên máy ứng dụng không đủ nếu dữ liệu đã được chuyển tiếp hoặc sao lưu. Cũng không nên chỉ che secret trong bản log hiển thị mà giữ credential cũ còn hiệu lực. Thu hồi hoặc xoay vòng credential là bước cần thiết để chặn việc tiếp tục sử dụng dữ liệu đã lộ.

## Quy tắc thực hành khi viết log cho Spring Kafka

Trước khi thêm một câu log, hãy tự kiểm tra:

- Giá trị này có thể dùng để xác thực, cấp quyền hoặc giải mã không?
- Object được in có thể chứa header, payload, cấu hình hoặc exception lồng nhau không?
- Có thể thay giá trị đó bằng metadata đã được duyệt, mã lỗi hoặc ID tương quan không nhạy cảm không?
- Câu log có an toàn khi được gửi tới hệ thống tập trung và chia sẻ cho nhóm vận hành không?
- Mức DEBUG/TRACE có làm lộ thêm dữ liệu trong production không?

Một câu log tốt giúp trả lời **điều gì đã xảy ra, ở đâu và khi nào** mà không tiết lộ **credential dùng để truy cập hệ thống**. Trong vận hành Spring Kafka, hãy log trạng thái xác thực và metadata cần thiết; giữ password, token, khóa riêng và mọi secret ngoài log ở tất cả các cấp độ.
