# Kiểm tra hostname verification

## Mục tiêu

Hostname verification là bước kiểm tra danh tính máy chủ trong kết nối TLS. Khi một ứng dụng Spring Kafka kết nối tới broker, client phải xác minh rằng chứng thư TLS mà broker gửi về thực sự được cấp cho hostname hoặc địa chỉ IP mà client đang kết nối.

Một kết nối TLS an toàn cần vượt qua hai kiểm tra độc lập:

1. **Xác minh chuỗi chứng thư (certificate chain):** chứng thư broker còn hiệu lực và được ký bởi CA mà client tin cậy.
2. **Xác minh hostname (endpoint identity):** tên máy chủ client sử dụng phải khớp với một định danh trong chứng thư broker, thường nằm trong Subject Alternative Name (SAN).

Truststore đúng chỉ chứng minh chứng thư thuộc một CA được tin cậy. Nó không chứng minh broker đang kết nối là broker mà ứng dụng mong đợi. Hostname verification bổ sung kiểm tra danh tính này và giúp ngăn kết nối TLS tới một máy chủ giả mạo có chứng thư được ký bởi CA mà client tin cậy.

Trong Kafka, kiểm tra này diễn ra ở phía client khi thiết lập TLS tới từng broker. Nó áp dụng khi dùng SSL và cả khi dùng SASL_SSL.

## Luồng kiểm tra khi Spring Kafka kết nối

Khi khởi tạo kết nối, Kafka client lấy hostname từ cấu hình bootstrap. Sau đó client nhận metadata của cluster; metadata chứa địa chỉ broker được công bố qua `advertised.listeners`. Client có thể mở thêm kết nối trực tiếp tới các hostname này để gửi hoặc nhận dữ liệu.

~~~mermaid
sequenceDiagram
    participant A as Spring Kafka client
    participant B as Kafka broker
    A->>B: Kết nối tới hostname trong bootstrap.servers
    B-->>A: Chứng thư TLS của broker
    A->>A: Kiểm tra CA chain và hostname trong SAN
    alt Cả hai kiểm tra thành công
        A->>B: Hoàn tất TLS và trao đổi Kafka protocol
        B-->>A: Metadata chứa advertised.listeners
        A->>B: Kết nối tới các broker trong metadata
    else Có kiểm tra thất bại
        A-->>B: Dừng TLS handshake
    end
~~~

Vì vậy, kết nối tới bootstrap server thành công chưa đủ để kết luận cấu hình hostname đúng cho toàn cluster. Một broker có thể công bố hostname khác, hoặc một broker riêng lẻ có chứng thư thiếu SAN phù hợp. Khi đó lỗi thường xuất hiện sau lúc client nhận metadata, lúc bắt đầu produce, consume hoặc thực hiện thao tác quản trị.

## Hostname phải khớp với SAN của chứng thư

Giả sử ứng dụng cấu hình:

~~~properties
spring.kafka.bootstrap-servers=broker-1.kafka.example.com:9093,broker-2.kafka.example.com:9093
~~~

Chứng thư mà broker-1 trả về cần có SAN phù hợp với `broker-1.kafka.example.com`; chứng thư broker-2 cần bao phủ `broker-2.kafka.example.com`. Nếu client kết nối bằng một DNS alias khác, alias đó cũng phải được đưa vào SAN của chứng thư tương ứng.

Ví dụ phần SAN của chứng thư broker-1:

~~~text
X509v3 Subject Alternative Name:
    DNS:broker-1.kafka.example.com
    DNS:kafka-bootstrap.example.com
    IP Address:10.20.0.11
~~~

Các quy tắc thực tế cần nhớ:

- Client kiểm tra hostname mà nó thực sự dùng để kết nối. Tên DNS trong cấu hình, tên broker được công bố trong metadata và tên trong SAN phải nhất quán.
- Nếu client kết nối bằng địa chỉ IP, chứng thư cần có SAN kiểu IP Address chứa đúng địa chỉ đó. Một mục `DNS:10.20.0.11` không thay thế cho SAN kiểu IP.
- Cổng kết nối không nằm trong SAN. SAN xác minh hostname hoặc địa chỉ IP, không xác minh số cổng.
- Nên đặt tên DNS trong SAN. Không dựa vào Common Name (CN) cũ để thay thế SAN vì cách xử lý CN có thể khác nhau giữa các TLS runtime.
- Wildcard như `*.kafka.example.com` chỉ phù hợp với một nhãn DNS ở vị trí wildcard; không nên giả định nó bao phủ các tên nhiều cấp như `broker-1.zone.kafka.example.com`. SAN tường minh cho từng broker thường dễ vận hành và kiểm tra hơn.
- Nếu dùng DNS alias, load balancer hoặc proxy TLS, phải kiểm tra tên mà client gửi tới endpoint và chứng thư thực tế endpoint đó trả về. Việc DNS phân giải thành đúng IP không tự làm hostname trong chứng thư trở nên hợp lệ.

Một cluster có thể dùng một chứng thư riêng cho từng broker hoặc một chứng thư có nhiều SAN. Dù chọn cách nào, mọi hostname mà client có thể kết nối tới đều phải được bao phủ bởi chứng thư do endpoint tương ứng trình bày.

## Kiểm tra bootstrap.servers và advertised.listeners

Có hai nguồn hostname cần kiểm tra:

**Bootstrap servers** là các địa chỉ ban đầu trong `spring.kafka.bootstrap-servers`. Client phải xác minh chứng thư của endpoint mà mỗi địa chỉ này dẫn tới.

**Advertised listeners** là các địa chỉ broker Kafka trả về trong metadata. Client sử dụng chúng cho các kết nối tiếp theo. Các hostname được công bố phải:

- Có thể phân giải DNS và truy cập được từ mạng chạy ứng dụng.
- Khớp với SAN trong chứng thư broker tương ứng.
- Dùng đúng listener và cổng mà client được phép truy cập.
- Nhất quán giữa các môi trường, chẳng hạn mạng nội bộ và mạng bên ngoài.

Ví dụ broker công bố listener:

~~~properties
listeners=SSL://0.0.0.0:9093
advertised.listeners=SSL://broker-1.kafka.example.com:9093
listener.security.protocol.map=SSL:SSL
~~~

Ở ví dụ này, `0.0.0.0` là địa chỉ bind trên máy broker; client không nên nhận địa chỉ bind này trong metadata. Client cần nhận hostname có thể truy cập như `broker-1.kafka.example.com`, và chứng thư broker phải chứa hostname đó trong SAN.

Nếu ứng dụng bootstrap qua `kafka-bootstrap.example.com` nhưng metadata lại trả về `broker-1.internal`, hai tên này đều có thể cần xuất hiện trong SAN của chứng thư endpoint liên quan. Cách giải quyết bền vững thường là cấu hình advertised listener dùng hostname mà client thực sự truy cập được và cấp chứng thư đúng cho hostname đó.

## Bật hostname verification trong Spring Boot

Kafka client có cấu hình `ssl.endpoint.identification.algorithm`. Giá trị `https` yêu cầu cơ chế endpoint identification theo quy tắc hostname của TLS/HTTPS. Dù ứng dụng đang dùng giao thức Kafka, tên thuật toán vẫn là `https`.

Với Kafka client từ phiên bản 2.0.0, giá trị mặc định của thuộc tính này là `https`. Các phiên bản cũ có thể có mặc định khác. Khai báo tường minh giúp cấu hình và ý định bảo mật dễ kiểm tra hơn, đồng thời tránh phụ thuộc vào mặc định của phiên bản thư viện.

Ví dụ cấu hình Spring Boot với TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker-1.kafka.example.com:9093
      - broker-2.kafka.example.com:9093
    security:
      protocol: SSL
    ssl:
      trust-store-location: classpath:kafka-truststore.p12
      trust-store-password: <KAFKA_TRUSTSTORE_PASSWORD>
      trust-store-type: PKCS12
    properties:
      "[ssl.endpoint.identification.algorithm]": https
~~~

Nếu dùng SASL trên TLS, đặt `security.protocol` thành `SASL_SSL` và cấu hình cơ chế SASL tương ứng. Thuộc tính hostname verification vẫn giữ giá trị `https`.

Trong file `application.properties`, có thể khai báo:

~~~properties
spring.kafka.properties[ssl.endpoint.identification.algorithm]=https
~~~

Cú pháp dấu ngoặc vuông giúp Spring Boot giữ nguyên tên Kafka property có nhiều dấu chấm khi bind vào map `spring.kafka.properties`.

Nếu tạo Kafka client bằng Java hoặc tự cấu hình factory, thêm thuộc tính vào cấu hình client:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.common.config.SslConfigs;

Map<String, Object> props = new HashMap<>();
props.put(
    SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG,
    "https"
);
~~~

Đảm bảo thuộc tính được áp dụng cho mọi client mà ứng dụng tự khởi tạo, gồm producer, consumer và AdminClient. Nếu cấu hình riêng Kafka Streams hoặc các factory tùy chỉnh, kiểm tra cấu hình của các client đó nữa. Một client dùng cấu hình khác có thể tiếp tục gặp lỗi dù producer hoặc consumer chính đã được sửa.

## Phân biệt truststore, keystore và hostname verification

Ba khái niệm này giải quyết các câu hỏi khác nhau:

| Thành phần | Vai trò | Câu hỏi được trả lời |
|---|---|---|
| Truststore của client | Chứa CA hoặc chứng thư tin cậy để xác minh chứng thư broker | Tôi có tin CA đã cấp chứng thư này không? |
| Hostname verification | So khớp hostname client kết nối với SAN trong chứng thư broker | Chứng thư này có được cấp cho đúng máy chủ tôi định kết nối không? |
| Keystore của client | Chứa chứng thư và private key của client, thường dùng trong mutual TLS | Client có thể chứng minh danh tính của chính nó với broker không? |

Hostname verification là kiểm tra danh tính **máy chủ** ở phía client. Trong mutual TLS, broker còn xác minh chứng thư **client**; việc xác minh client certificate không thay thế hostname verification của client đối với broker.

Khi gặp lỗi hostname mismatch, thêm CA vào truststore thường không giải quyết được vấn đề. Cần sửa hostname kết nối hoặc cấp lại chứng thư với SAN phù hợp.

## Kiểm tra chứng thư và endpoint

Thực hiện kiểm tra từ máy hoặc container có cùng đường mạng với ứng dụng Spring Kafka. Kiểm tra từ laptop quản trị có thể cho kết quả khác nếu DNS, proxy hoặc listener được phân chia theo mạng.

### 1. Xem SAN của chứng thư

Nếu có file chứng thư PEM:

~~~bash
openssl x509 -in broker-1.crt -noout -subject -issuer -ext subjectAltName
~~~

Đối chiếu toàn bộ mục DNS và IP với hostname hoặc địa chỉ mà client sử dụng. Kiểm tra đúng chứng thư leaf của broker, không chỉ chứng thư CA trong truststore.

Có thể dùng keytool để xem chứng thư:

~~~bash
keytool -printcert -file broker-1.crt
~~~

### 2. Kiểm tra TLS với đúng hostname

Với endpoint DNS:

~~~bash
openssl s_client \
  -connect broker-1.kafka.example.com:9093 \
  -servername broker-1.kafka.example.com \
  -verify_hostname broker-1.kafka.example.com \
  -verify_return_error \
  -CAfile ca.pem
~~~

Với endpoint được client gọi bằng địa chỉ IP:

~~~bash
openssl s_client \
  -connect 10.20.0.11:9093 \
  -verify_ip 10.20.0.11 \
  -verify_return_error \
  -CAfile ca.pem
~~~

Các tùy chọn `-verify_hostname` và `-verify_ip` giúp kiểm tra định danh endpoint; `-CAfile` cung cấp CA dùng để xác minh chuỗi chứng thư. Khi endpoint dùng SNI hoặc có proxy định tuyến theo SNI, `-servername` phải mang hostname mà client dự kiến gửi.

Lặp lại phép thử cho từng broker và từng hostname trong cấu hình. Một phép thử thành công tới bootstrap alias không chứng minh các broker trong metadata đều có chứng thư hợp lệ.

### 3. Kiểm tra DNS và metadata Kafka

Từ môi trường chạy ứng dụng, xác nhận hostname phân giải tới địa chỉ mong muốn và cổng broker có thể truy cập. Sau đó kiểm tra cấu hình `advertised.listeners` ở phía Kafka hoặc metadata mà client nhận được. Đối chiếu từng hostname metadata trả về với SAN của broker tương ứng.

### 4. Bật log TLS khi cần

Nếu kết quả từ OpenSSL và lỗi trong ứng dụng khác nhau, có thể bật log TLS của JVM trong một lần tái hiện có kiểm soát:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

Log handshake có thể rất dài và chứa thông tin hạ tầng nhạy cảm. Chỉ bật tạm thời, giới hạn nơi lưu log và tắt sau khi thu thập đủ bằng chứng. Không đưa log thô vào kênh công khai.

## Đọc lỗi thường gặp

| Dấu hiệu | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `No subject alternative DNS name matching ... found` | Hostname DNS đang dùng không có trong SAN của chứng thư | So sánh hostname trong lỗi với SAN; kiểm tra bootstrap và advertised listener |
| `No name matching IP address ... found` | Client kết nối bằng IP nhưng chứng thư thiếu SAN kiểu IP tương ứng | Dùng hostname DNS có trong SAN hoặc cấp chứng thư có IP SAN đúng |
| `PKIX path building failed` | Client không xây dựng được chuỗi chứng thư tới CA tin cậy | Kiểm tra truststore, CA trung gian, chain broker trình bày và thời hạn chứng thư |
| Chứng thư hết hạn hoặc chưa có hiệu lực | Thời gian hiệu lực của chứng thư không hợp lệ | Kiểm tra Not Before, Not After và đồng bộ thời gian hệ thống |
| Bootstrap kết nối được nhưng một node khác thất bại | Hostname hoặc chứng thư của một broker trong metadata không khớp | Kiểm tra từng địa chỉ trong advertised.listeners và chứng thư của từng broker |
| `Connection to node ... could not be established` | Lỗi kết nối tổng quát; riêng thông báo này chưa xác định nguyên nhân TLS | Đọc exception gốc, hostname và nguyên nhân sâu hơn trong log |

Không nên kết luận mọi lỗi `SSLHandshakeException` đều là hostname mismatch. `PKIX path building failed` thường liên quan tới chuỗi tin cậy; lỗi SAN cho biết endpoint identity không khớp. Phân biệt đúng hai nhóm giúp chọn cách sửa chính xác.

## Quy trình xử lý khi hostname mismatch

Khi ứng dụng báo hostname verification thất bại, xử lý theo trình tự sau:

1. **Lấy hostname chính xác từ lỗi.** Ghi nhận ứng dụng đang kết nối bằng DNS name hay IP, cổng nào và broker node nào.
2. **Xác định nguồn hostname.** Đối chiếu `spring.kafka.bootstrap-servers` trước; nếu lỗi xuất hiện sau khi nhận metadata, kiểm tra hostname trong `advertised.listeners`.
3. **Xem chứng thư endpoint thực tế.** Lấy leaf certificate mà broker trả về từ đúng mạng của ứng dụng và đọc SAN.
4. **Kiểm tra từng broker.** Không chỉ kiểm tra node bootstrap đầu tiên. Xác minh mọi hostname client có thể nhận từ metadata.
5. **Sửa cấu hình hoặc chứng thư.** Ưu tiên công bố hostname DNS ổn định mà client truy cập được; cấp chứng thư có SAN bao phủ hostname đó. Nếu có nhiều alias hợp lệ, đưa từng alias cần dùng vào SAN.
6. **Kiểm tra lại bằng TLS client và ứng dụng.** Chạy lại phép thử OpenSSL cho từng endpoint, sau đó khởi động hoặc tái kết nối Spring Kafka và xác nhận producer, consumer cùng AdminClient hoạt động.
7. **Ghi lại cấu hình chuẩn.** Lưu danh sách hostname được công bố, SAN tương ứng, CA phát hành và thời hạn chứng thư để lần gia hạn sau không làm mất hostname cần thiết.

Nếu cần đổi tên trong `advertised.listeners`, hãy xác nhận tên mới có thể phân giải và truy cập từ tất cả mạng client. Việc đổi hostname mà không cập nhật DNS hoặc chứng thư có thể chỉ chuyển lỗi sang một giai đoạn kết nối khác.

## Vì sao không nên tắt hostname verification

Có thể tắt endpoint identification bằng cách đặt giá trị thuộc tính thành chuỗi rỗng:

~~~properties
spring.kafka.properties[ssl.endpoint.identification.algorithm]=
~~~

Cấu hình này bỏ qua bước đối chiếu hostname của chứng thư. Việc xác minh chuỗi CA có thể vẫn diễn ra, nhưng client không còn kiểm tra chứng thư có thuộc đúng hostname mà nó kết nối hay không. Một máy chủ khác có chứng thư do CA được tin cậy cấp có thể vượt qua kiểm tra chain dù không phải endpoint mong đợi.

Chỉ cân nhắc tùy chọn này trong môi trường thử nghiệm cô lập, có thời hạn và có kế hoạch gỡ bỏ rõ ràng. Không dùng nó làm cách sửa lỗi trong production, không để lại trong cấu hình dùng chung và không xem nó là giải pháp cho lỗi SAN. Cách sửa phù hợp là đồng bộ hostname kết nối, advertised listener và SAN của chứng thư.

## Checklist vận hành

Trước khi đưa một Kafka client vào production hoặc sau khi thay đổi DNS, listener hay chứng thư, xác nhận:

- [ ] Kafka client có `ssl.endpoint.identification.algorithm=https`.
- [ ] Mọi hostname trong `bootstrap.servers` có trong SAN của endpoint tương ứng.
- [ ] Mọi hostname được trả về qua `advertised.listeners` có thể truy cập từ mạng ứng dụng và khớp SAN.
- [ ] Nếu client dùng IP, chứng thư có SAN kiểu IP Address đúng.
- [ ] Chứng thư còn hiệu lực và chuỗi CA được client truststore tin cậy.
- [ ] Producer, consumer, AdminClient và các client tùy chỉnh dùng cùng chính sách hostname verification.
- [ ] Các phép thử TLS được chạy từ môi trường mạng gần với ứng dụng.
- [ ] Không có cấu hình production nào đặt `ssl.endpoint.identification.algorithm` thành chuỗi rỗng.

Hostname verification giúp client xác nhận broker đang nói chuyện đúng là endpoint được định danh trong chứng thư. Vận hành ổn định đòi hỏi giữ nhất quán ba nơi: hostname client sử dụng, hostname Kafka công bố và SAN của chứng thư broker.
