# Xử lý AuthorizationException

Trong vận hành producer của Spring Kafka, **AuthorizationException** cho biết Kafka đã nhận diện được danh tính của client nhưng từ chối một thao tác vì principal đó không có quyền cần thiết trên tài nguyên tương ứng. Lỗi thường xuất phát từ ACL hoặc chính sách phân quyền của cluster, chẳng hạn producer không có quyền ghi vào topic, không có quyền dùng idempotent producer ở cấp cluster hoặc không có quyền sử dụng transactional ID.

Đây là lỗi cấu hình bảo mật và quyền truy cập. Retry gửi tin nhắn liên tục không tự cấp thêm quyền. Ứng dụng cần nhận diện lỗi, giữ lại thông tin về sự kiện chưa gửi thành công, phát cảnh báo có đủ ngữ cảnh và phối hợp với đội quản trị Kafka để sửa đúng quyền.

## 1. AuthorizationException có nghĩa gì?

Kafka bảo vệ tài nguyên bằng cơ chế xác thực và phân quyền. Hai bước này trả lời hai câu hỏi khác nhau:

- **Authentication** xác định client là ai. Ví dụ, client xác thực bằng SASL/SCRAM, SASL/OAUTHBEARER hoặc TLS client certificate.
- **Authorization** xác định principal đã xác thực được phép làm gì trên tài nguyên nào. Kafka có thể cho phép principal đọc một topic nhưng từ chối ghi vào topic đó.

Khi nhận **AuthorizationException**, client thường đã vượt qua bước xác thực. Broker hoặc authorizer từ chối một thao tác vì không tìm thấy quyền ALLOW phù hợp, có quyền DENY áp dụng hoặc chính sách bảo mật của nền tảng không cho phép thao tác đó.

Ví dụ:

- Principal **User:billing-producer** được phép đọc topic **orders.created** nhưng chưa có quyền **WRITE**.
- Producer bật idempotence nhưng principal thiếu quyền **IDEMPOTENT_WRITE** trên cluster.
- Producer giao dịch dùng **transactional.id** thuộc phạm vi mà principal chưa được cấp quyền **WRITE**.
- Ứng dụng kết nối nhầm cluster hoặc dùng credential của môi trường khác, khiến principal và ACL thực tế không khớp.

AuthorizationException không đồng nghĩa với việc payload sai, topic đầy hoặc broker không khả dụng. Cần xác định thao tác và tài nguyên bị từ chối trước khi thay đổi cấu hình.

## 2. Những exception thường gặp

**org.apache.kafka.common.errors.AuthorizationException** là lớp cơ sở cho các lỗi phân quyền Kafka. Khi xử lý ở ứng dụng, hãy xem cả lớp exception cụ thể và cause chain vì Spring Kafka hoặc Kafka client có thể bọc lỗi gốc trong exception khác.

| Exception | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| **TopicAuthorizationException** | Principal không được phép thực hiện thao tác trên một hoặc nhiều topic | Kiểm tra topic đích, principal, ACL **WRITE** và tên topic thực tế |
| **ClusterAuthorizationException** | Principal bị từ chối một thao tác ở cấp cluster | Kiểm tra quyền cluster; với producer idempotent, kiểm tra **IDEMPOTENT_WRITE** |
| **TransactionalIdAuthorizationException** | Principal không được phép dùng transactional ID đã cấu hình | Kiểm tra transactional ID và ACL **WRITE** trên tài nguyên transactional ID |
| **GroupAuthorizationException** | Principal không được phép thao tác với consumer group | Kiểm tra group ACL; thường liên quan consumer hoặc ứng dụng vừa produce vừa consume |
| **AuthorizationException** | Lớp cơ sở hoặc thông tin lỗi chưa được phân loại cụ thể | Đọc cause chain và log broker để xác định resource và operation |

Một ứng dụng Spring có cả producer lẫn consumer có thể gặp lỗi group authorization dù mục tiêu đang điều tra là producer. Cần xác định listener, transaction flow hoặc thành phần nào đã phát sinh exception thay vì mặc định mọi lỗi authorization đều là quyền ghi topic.

### Phân biệt với lỗi xác thực

| Dấu hiệu | Authentication failure | Authorization failure |
|---|---|---|
| Danh tính client | Không xác thực được hoặc không thiết lập được danh tính | Đã có principal nhưng thao tác bị từ chối |
| Ví dụ | Sai mật khẩu SASL, truststore/certificate không hợp lệ, cơ chế SASL không khớp | Thiếu **WRITE** trên topic hoặc thiếu quyền trên transactional ID |
| Nơi kiểm tra đầu tiên | Credential, certificate, SASL mechanism, TLS và listener | Principal thực tế, ACL, resource, operation và host restriction |
| Cách khắc phục | Sửa cấu hình xác thực hoặc cấp credential hợp lệ | Cấp quyền tối thiểu cần thiết hoặc sửa resource/policy |

**AuthenticationException**, **SaslAuthenticationException** và **AuthorizationException** thuộc các nhóm lỗi khác nhau. Không nên phản ứng với lỗi xác thực bằng cách cấp thêm ACL; cũng không nên thay mật khẩu khi broker đã xác thực thành công và đang từ chối quyền.

## 3. Producer có thể gặp lỗi ở những thao tác nào?

### 3.1 Gửi record vào topic

Đối với producer thông thường, thao tác quan trọng nhất là ghi record vào topic. Principal cần quyền **WRITE** trên topic đích.

Nếu ứng dụng gửi tới **orders.created** nhưng ACL chỉ cho phép ghi **orders.updated**, broker có thể trả về **TopicAuthorizationException**. Lỗi cũng có thể xảy ra khi tên topic được tạo từ cấu hình môi trường, prefix hoặc tenant và giá trị thực tế khác với tên mà đội vận hành đã cấp quyền.

Cần ghi nhận chính xác:

- Bootstrap cluster hoặc alias môi trường mà producer đang kết nối.
- Topic thực tế sau khi áp dụng cấu hình và quy tắc đặt tên.
- Principal broker nhìn thấy.
- Operation bị từ chối và resource tương ứng.
- Host hoặc workload gửi request nếu chính sách ACL giới hạn host.

### 3.2 Producer idempotent

Idempotent producer giúp Kafka loại bỏ bản ghi trùng do retry nội bộ của producer trong phạm vi Kafka hỗ trợ. Khi tính năng này được bật, cluster có thể yêu cầu principal có quyền **IDEMPOTENT_WRITE** trên tài nguyên cluster.

Điểm này dễ bị bỏ sót: ứng dụng đã có **WRITE** trên topic nhưng vẫn có thể gặp **ClusterAuthorizationException** khi khởi tạo hoặc sử dụng producer idempotent nếu quyền ở cấp cluster chưa được cấp.

Một số phiên bản Kafka client bật idempotence mặc định. Vì vậy cần kiểm tra phiên bản client và cấu hình hiệu lực, không chỉ tìm thuộc tính **enable.idempotence** trong file YAML. Không nên tắt idempotence chỉ để che lỗi phân quyền; trước hết hãy xác nhận yêu cầu bảo mật và cấp quyền theo chính sách của nền tảng.

### 3.3 Transactional producer

Transactional producer dùng **transactional.id** để nhận diện giao dịch. Principal cần quyền phù hợp trên tài nguyên transactional ID, thường là operation **WRITE**, đồng thời cần quyền ghi vào các topic tham gia giao dịch. Nếu producer idempotent cần quyền cluster tương ứng, quyền đó cũng phải được kiểm tra.

Ví dụ, ứng dụng cấu hình **transactional.id** với prefix **billing-tx-**, nhưng ACL chỉ cấp cho một ID khác. Khi gọi **initTransactions()** hoặc thực hiện thao tác transaction, broker có thể từ chối với **TransactionalIdAuthorizationException**.

Cần kiểm tra:

- Giá trị **transactional.id** thực tế, bao gồm prefix và suffix do ứng dụng tạo.
- Resource pattern của ACL: **LITERAL** hay **PREFIXED**.
- Quyền **WRITE** trên transactional ID.
- Quyền **WRITE** trên từng topic được ghi trong transaction.
- Quyền cluster cần thiết nếu producer dùng idempotence.

Không mở rộng ACL thành quyền ghi mọi transactional ID chỉ để tránh lỗi. Hãy giới hạn theo prefix hoặc ID mà workload thực sự sử dụng.

## 4. Exception xuất hiện ở đâu trong Spring Kafka?

Producer gửi dữ liệu bất đồng bộ. Vì vậy lỗi authorization có thể xuất hiện theo hai đường:

1. **Lỗi đồng bộ khi gọi API**: lời gọi **KafkaTemplate.send(...)** có thể ném exception ngay nếu lỗi xảy ra trước khi record được đưa vào luồng gửi.
2. **Lỗi bất đồng bộ**: lời gọi **send(...)** trả về future, sau đó future hoàn tất với lỗi khi producer nhận phản hồi từ broker hoặc xử lý lỗi gửi.

Trong Spring Kafka 3.x, **KafkaTemplate.send(...)** trả về **CompletableFuture<SendResult<K, V>>**. Ở các phiên bản Spring Kafka cũ hơn, API future có thể là **ListenableFuture**; hãy dùng callback phù hợp với phiên bản đang chạy.

Không chỉ kiểm tra lớp ngoài cùng của exception. Kafka client và Spring Kafka có thể bọc exception gốc. Cần đi qua cause chain để tìm **AuthorizationException** hoặc lớp con.

### Ví dụ xử lý future với Spring Kafka 3.x

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.common.errors.AuthorizationException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        try {
            CompletableFuture<SendResult<String, OrderCreated>> future =
                    kafkaTemplate.send(
                            "orders.created",
                            event.orderId(),
                            event
                    );

            future.whenComplete((result, failure) -> {
                if (failure == null) {
                    // Broker đã xác nhận record theo cấu hình producer.
                    return;
                }

                AuthorizationException authorization =
                        findAuthorizationException(failure);

                if (authorization != null) {
                    // Ghi nhận lỗi cấu hình bảo mật và kích hoạt cảnh báo.
                    // Sự kiện cần được giữ lại qua outbox hoặc cơ chế phục hồi.
                    handleAuthorizationFailure(event, authorization);
                    return;
                }

                handleOtherPublishFailure(event, failure);
            });

        } catch (RuntimeException failure) {
            // Bao phủ các lỗi xảy ra ngay trong lời gọi send().
            AuthorizationException authorization =
                    findAuthorizationException(failure);

            if (authorization != null) {
                handleAuthorizationFailure(event, authorization);
            } else {
                handleOtherPublishFailure(event, failure);
            }
        }
    }

    private static AuthorizationException findAuthorizationException(
            Throwable failure) {

        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());

        for (Throwable current = failure;
             current != null && visited.add(current);
             current = current.getCause()) {

            if (current instanceof AuthorizationException authorization) {
                return authorization;
            }
        }

        return null;
    }

    private void handleAuthorizationFailure(
            OrderCreated event,
            AuthorizationException failure) {
        // Ghi log có cấu trúc, phát alert và lưu trạng thái gửi thất bại.
        // Không log credential hoặc toàn bộ payload nhạy cảm.
    }

    private void handleOtherPublishFailure(
            OrderCreated event,
            Throwable failure) {
        // Áp dụng chính sách cho lỗi gửi khác.
    }
}
~~~

Ví dụ minh họa cách nhận diện lỗi ở cả đường đồng bộ và bất đồng bộ. Các phương thức xử lý bên trong cần được triển khai theo cơ chế lưu trữ và giám sát của hệ thống. Nếu dùng transaction, cần đưa exception qua đúng ranh giới transaction để transaction được abort hoặc rollback theo cấu hình; không nuốt exception rồi báo thành công.

### Vì sao phải kiểm tra cả hai đường lỗi?

Nếu chỉ gắn **whenComplete**, một exception ném trực tiếp từ **send()** có thể thoát ra trước khi callback được đăng ký. Ngược lại, nếu chỉ dùng **try/catch**, lỗi phát sinh sau khi producer gửi request sẽ nằm trong future và không được xử lý tại khối **catch**.

Trong cả hai trường hợp, logic phân loại lỗi nên dùng chung để tránh cách xử lý khác nhau giữa lỗi đồng bộ và bất đồng bộ.

## 5. Quy trình điều tra AuthorizationException

### Bước 1: Xác định đúng producer và cluster

Bắt đầu từ instance hoặc workload phát sinh lỗi. Xác định môi trường, bootstrap servers, tên ứng dụng, phiên bản Kafka client/Spring Kafka và thời điểm lỗi.

Đừng dựa vào tên service trong log để suy ra cluster. Một deployment có thể nhận cấu hình từ biến môi trường, ConfigMap, secret hoặc profile khác với cấu hình trong repository. Hãy xác minh giá trị hiệu lực của ứng dụng mà không in credential ra log.

### Bước 2: Tìm exception gốc và resource bị từ chối

Đọc toàn bộ cause chain và tên lớp exception cụ thể. Với **TopicAuthorizationException**, xác định danh sách topic liên quan. Với **ClusterAuthorizationException**, tìm thao tác cluster đang được thực hiện. Với **TransactionalIdAuthorizationException**, lấy transactional ID thực tế.

Thông tin cần có trước khi yêu cầu cấp quyền:

| Thông tin | Ví dụ |
|---|---|
| Workload | **billing-service** |
| Môi trường | **staging** |
| Cluster alias | **kafka-staging** |
| Principal | **User:billing-producer** |
| Resource type | **Topic** |
| Resource name | **orders.created** |
| Operation | **WRITE** |
| Client host/workload | Pod hoặc host phát request |
| Thời điểm | Timestamp kèm timezone |
| Exception | **TopicAuthorizationException** |

Ví dụ chỉ minh họa định dạng thông tin; hãy dùng giá trị thực tế lấy từ client và broker.

### Bước 3: Đối chiếu principal broker nhìn thấy

Principal trong cấu hình ứng dụng không nhất thiết giống chuỗi principal được authorizer sử dụng. Với SASL, principal phụ thuộc cơ chế xác thực và cấu hình mapping. Với TLS, principal có thể được xây dựng từ distinguished name của certificate hoặc principal builder.

Kiểm tra broker log để biết principal nào thực sự bị từ chối. Một log authorizer thường chứa thông tin tương tự:

~~~text
Principal = User:billing-producer
Operation = WRITE
Resource = Topic:LITERAL:orders.created
Result = DENIED
~~~

Đây là dạng minh họa, không phải thông điệp cố định của mọi phiên bản Kafka hoặc mọi nhà cung cấp. Broker log thực tế có thể dùng cách diễn đạt khác.

Nếu principal không khớp với ACL dự kiến, điều tra SASL mechanism, certificate, principal mapping, listener và credential của workload trước khi thay đổi ACL.

### Bước 4: Kiểm tra ACL và resource pattern

Đối chiếu quyền trên đúng cluster và resource. Kiểm tra:

- ACL có áp dụng cho đúng principal không?
- Resource name có đúng chính tả, prefix và quy tắc đặt tên không?
- ACL là **LITERAL** hay **PREFIXED**?
- Operation có đúng với thao tác bị từ chối không?
- ACL có host restriction khiến workload hiện tại không khớp không?
- Có ACL DENY phù hợp đang chặn thao tác không?
- Quyền được cấp trên cluster nào và listener nào?

Một ACL cho **orders.*** dưới dạng literal không tương đương với ACL prefix **orders.**. Tương tự, quyền trên topic cùng tên ở cluster staging không cấp quyền trên cluster production.

### Bước 5: Kiểm tra cấu hình producer có bật tính năng cần ACL riêng không

Nếu lỗi là cluster authorization, kiểm tra **enable.idempotence** và phiên bản Kafka client. Nếu producer dùng transaction, kiểm tra **transactional.id** và topic tham gia transaction.

Đừng suy luận rằng chỉ cần quyền **WRITE** trên topic là đủ cho mọi producer. Producer idempotent và transactional producer có thêm yêu cầu phân quyền.

### Bước 6: Sửa quyền qua quy trình quản trị

Nếu đã xác định thiếu ACL, gửi cho đội nền tảng thông tin principal, resource, operation, cluster, môi trường và bằng chứng lỗi. Đội có thẩm quyền sẽ cấp quyền theo quy trình quản trị của tổ chức.

Sau khi quyền được sửa, gửi lại một record kiểm thử có kiểm soát và xác nhận acknowledgement từ broker. Đồng thời kiểm tra log broker để chắc chắn thao tác không còn bị từ chối. Nếu ACL đã đúng nhưng lỗi tiếp tục, xác minh principal thực tế, cache/policy propagation và cluster endpoint trước khi thay đổi thêm.

## 6. Cấp quyền tối thiểu cho producer

Với Kafka sử dụng ACL authorizer tiêu chuẩn, các quyền thường cần xem xét như sau:

| Trường hợp | Resource | Operation thường cần |
|---|---|---|
| Producer gửi record vào topic có sẵn | Topic đích | **WRITE** |
| Producer dùng idempotence | Cluster | **IDEMPOTENT_WRITE** |
| Producer giao dịch | Transactional ID | **WRITE** |
| Producer giao dịch ghi record | Mỗi topic đích | **WRITE** |
| Ứng dụng tự tạo topic qua KafkaAdmin/AdminClient | Topic hoặc Cluster tùy thao tác tạo | **CREATE** theo quy tắc của cluster |

Bảng trên là hướng dẫn cho Kafka ACL authorizer tiêu chuẩn. Nền tảng Kafka managed có thể dùng IAM, RBAC hoặc policy riêng; khi đó phải theo đúng cơ chế phân quyền của nhà cung cấp.

Một producer chỉ gửi vào topic đã tồn tại thường không cần quyền quản trị cluster hoặc quyền tạo topic. Nên tạo topic qua quy trình quản trị của nền tảng. Không cấp **ALL** hoặc quyền **CREATE** rộng cho ứng dụng chỉ để xử lý lỗi publish.

### Ví dụ kiểm tra ACL bằng kafka-acls

Với cluster dùng Kafka ACL authorizer tiêu chuẩn, quản trị viên có thể liệt kê ACL liên quan bằng công cụ **kafka-acls.sh**:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --list \
  --topic orders.created \
  --principal User:billing-producer
~~~

Để cấp quyền ghi vào một topic cụ thể:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:billing-producer \
  --operation Write \
  --topic orders.created
~~~

Nếu producer cần idempotence và authorizer yêu cầu quyền cluster tương ứng, quản trị viên có thể cấp quyền trên cluster:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:billing-producer \
  --operation IdempotentWrite \
  --cluster
~~~

Với transactional producer, cấp quyền **Write** trên đúng transactional ID hoặc prefix mà workload sử dụng. Ví dụ cấp trên một ID cụ thể:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:billing-producer \
  --operation Write \
  --transactional-id billing-tx-01
~~~

Nếu ứng dụng tạo transactional ID với suffix thay đổi theo instance, đội nền tảng có thể dùng resource pattern **PREFIXED** phù hợp với quy tắc đặt tên và phiên bản Kafka đang vận hành. Hãy xác nhận phạm vi prefix trước khi áp dụng.

Các lệnh trên là ví dụ cho quản trị viên có quyền trên cluster. Thay bootstrap server, principal, topic và transactional ID bằng giá trị đã xác minh. Không đặt mật khẩu trực tiếp trong command line hoặc lưu credential quản trị vào repository. Nếu tổ chức quản lý ACL qua GitOps, giao diện cloud hoặc hệ thống IAM/RBAC, hãy dùng quy trình chính thức đó thay cho lệnh CLI.

Sau khi cấp quyền, liệt kê lại ACL và thực hiện kiểm thử từ đúng workload/principal. Việc lệnh cấp ACL trả về thành công chưa chứng minh producer thực tế đang dùng principal đó.

## 7. Xử lý lỗi ở tầng ứng dụng

### Không retry vô hạn

Producer retry xử lý các lỗi có thể phục hồi ở tầng gửi. Authorization failure thường là lỗi không thể khắc phục bằng cách gửi lại cùng request khi ACL và principal vẫn giữ nguyên.

Nếu retry liên tục:

- Tăng request và log trên broker.
- Tạo nhiều cảnh báo trùng lặp.
- Làm đầy queue hoặc buffer phía ứng dụng.
- Che khuất nguyên nhân cấu hình ban đầu.
- Có thể khiến sự kiện bị mất nếu ứng dụng chỉ giữ trong bộ nhớ rồi process khởi động lại.

Hãy phân loại **AuthorizationException** thành lỗi cấu hình/phân quyền, dừng retry nhanh cho record đang thất bại và kích hoạt quy trình phục hồi đã thiết kế. Sau khi ACL được sửa và xác minh, ứng dụng có thể gửi lại record theo chính sách retry có giới hạn.

### Bảo toàn sự kiện chưa gửi thành công

Nếu sự kiện không được phép mất, không chỉ log exception rồi bỏ qua. Một số cách bảo toàn:

- **Transactional outbox**: lưu event trong database cùng transaction với thay đổi nghiệp vụ; publisher đọc các event chưa gửi và đánh dấu đã publish sau khi nhận acknowledgement.
- **Durable retry store**: ghi lại event cùng trạng thái, số lần thử, thời điểm lỗi và thông tin định tuyến.
- **Request failure**: nếu API đồng bộ phụ thuộc vào việc publish, trả kết quả lỗi theo hợp đồng API và cho phép caller retry an toàn bằng idempotency key.

Không nên dùng một danh sách trong bộ nhớ làm nơi lưu duy nhất cho event quan trọng. Khi service restart, dữ liệu trong bộ nhớ có thể mất. Nếu dùng outbox, cần bảo đảm việc đánh dấu trạng thái và publish có semantics chịu được việc publish thành công nhưng process dừng trước khi đánh dấu; publisher có thể gửi lại và consumer vẫn cần idempotency.

### Không nuốt exception trong transaction

Với transactional producer, lỗi authorization trong quá trình khởi tạo hoặc commit transaction phải được truyền tới ranh giới quản lý transaction để ứng dụng xử lý trạng thái giao dịch đúng. Không bắt exception rồi tiếp tục trả kết quả thành công. Khi transaction đã thất bại, không giả định các record đã gửi trong transaction được commit.

Đối với Kafka transaction, chỉ record thuộc transaction đã commit mới hiển thị cho consumer dùng **read_committed**. Quy trình phục hồi cần tuân theo trạng thái producer/transaction thực tế; không tự ý tiếp tục một transaction đã thất bại.

### Phân biệt lỗi authorization với lỗi nghiệp vụ

AuthorizationException là lỗi vận hành bảo mật. Không đưa record vào DLT nghiệp vụ chỉ vì broker từ chối producer gửi record đó: nếu producer không có quyền ghi vào topic đích, nó có thể cũng không có quyền ghi vào DLT. DLT phù hợp hơn với luồng consumer đã đọc được record nhưng xử lý nghiệp vụ thất bại, theo chính sách error handler.

Nếu cần lưu record thất bại, hãy dùng outbox hoặc kho phục hồi mà ứng dụng được phép ghi và đã được thiết kế cho tình huống này.

## 8. Quan sát, log và cảnh báo

Một hệ thống vận hành tốt cần cho biết lỗi xuất hiện ở producer nào, topic nào và principal nào mà không làm lộ credential hoặc dữ liệu nhạy cảm.

### Trường log nên có

| Trường | Mục đích |
|---|---|
| **service** và **environment** | Xác định workload và môi trường |
| **cluster_alias** | Phân biệt cluster đích |
| **principal** | Đối chiếu danh tính với ACL |
| **topic** | Xác định tài nguyên bị từ chối |
| **operation** | Biết cần quyền gì |
| **exception_class** | Phân loại lỗi |
| **event_id** hoặc correlation ID | Theo dõi event cần phục hồi |
| **timestamp** | Đối chiếu client và broker log |
| **attempt** | Biết số lần gửi đã thử |

Không log password, SASL JAAS config, access token, private key hoặc toàn bộ payload chỉ để chẩn đoán authorization. Nếu event có dữ liệu cá nhân hoặc thông tin thanh toán, chỉ log ID/correlation ID đã được phép sử dụng.

### Cảnh báo nên theo dõi

- Số lượng authorization failure theo service, cluster và exception class.
- Số topic hoặc transactional ID bị từ chối.
- Số event đang chờ publish trong outbox/recovery store.
- Tuổi của event chưa publish lâu nhất.
- Thời gian từ lúc phát hiện lỗi tới khi ACL được sửa và publish phục hồi.
- Tỷ lệ gửi thành công sau khi khắc phục.

Một cảnh báo tốt phải chỉ ra principal, resource, operation và môi trường để đội nền tảng có thể xử lý. Tránh gửi alert chỉ với thông báo chung **Kafka send failed**.

## 9. Runbook xử lý production

Khi alert AuthorizationException xuất hiện, có thể dùng trình tự sau:

1. Xác định service, instance, môi trường và cluster alias phát sinh lỗi.
2. Thu thập exception cụ thể và cause chain từ producer.
3. Lấy topic hoặc transactional ID và operation bị từ chối.
4. Đối chiếu principal thực tế trong broker log.
5. Kiểm tra ACL, resource pattern, host restriction và ACL DENY.
6. Nếu producer idempotent, xác nhận **IDEMPOTENT_WRITE** trên cluster.
7. Nếu producer giao dịch, xác nhận quyền **WRITE** trên transactional ID và topic.
8. Yêu cầu đội có thẩm quyền sửa ACL theo nguyên tắc quyền tối thiểu.
9. Xác minh ACL sau khi thay đổi và gửi một record kiểm thử từ đúng workload.
10. Phát lại các event còn tồn trong outbox/recovery store theo thứ tự và idempotency policy của ứng dụng.
11. Theo dõi publish success, backlog, consumer lag và lỗi mới sau phục hồi.
12. Ghi lại nguyên nhân gốc, quyền đã thay đổi và cách ngăn lỗi tái diễn.

Không xóa backlog hoặc đánh dấu event đã publish chỉ để làm alert biến mất. Chỉ đóng sự cố khi đã xác nhận record cần thiết được publish và các trạng thái phục hồi được cập nhật đúng.

## 10. Kiểm thử trước khi phát hành

Kiểm thử authorization cần chạy trên môi trường có broker và authorizer tương đương production. Mock producer có thể giúp kiểm tra nhánh xử lý exception trong code, nhưng không chứng minh ACL trên broker hoạt động đúng.

Các kịch bản hữu ích:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Principal có **WRITE** trên topic | Producer gửi thành công và nhận acknowledgement |
| Principal thiếu **WRITE** trên topic | Producer nhận **TopicAuthorizationException**; event được giữ lại để phục hồi |
| Producer idempotent thiếu **IDEMPOTENT_WRITE** | Broker từ chối thao tác cluster; alert nêu rõ principal và cluster |
| Transactional ID không có quyền | Transaction khởi tạo hoặc thao tác tương ứng thất bại; ứng dụng không báo thành công |
| Principal dùng sai môi trường | Log và chẩn đoán chỉ ra cluster/principal thực tế |
| ACL được sửa sau sự cố | Producer gửi lại thành công; backlog được giải phóng theo chính sách |
| Broker trả lỗi khác authorization | Lỗi được phân loại theo nhánh retry/phục hồi tương ứng, không bị gắn nhầm là ACL |

Nên dùng principal kiểm thử có quyền hạn giới hạn và xác minh cả log phía client lẫn broker. Không thử nghiệm bằng cách thu hồi ACL của workload production đang phục vụ lưu lượng thật.

## 11. Các lỗi xử lý thường gặp

**Chỉ tăng retries hoặc delivery timeout.** Những thiết lập này không tạo quyền ACL. Cần sửa principal hoặc policy trước khi thử gửi lại.

**Cấp quyền ALL cho principal của ứng dụng.** Cách này có thể làm hết lỗi trước mắt nhưng mở rộng phạm vi truy cập quá mức. Hãy cấp đúng operation trên đúng resource.

**Chỉ kiểm tra ACL topic.** Producer idempotent và transactional producer có yêu cầu phân quyền bổ sung ở cluster hoặc transactional ID.

**Chỉ xem tên principal trong cấu hình.** Principal thực tế có thể khác do SASL, TLS hoặc principal mapping. Hãy đối chiếu broker log.

**Chỉ bắt exception quanh callback.** Lỗi có thể xuất hiện đồng bộ ngay tại send(). Bao phủ cả hai đường và dùng logic phân loại chung.

**Log exception rồi bỏ event.** Producer failure có thể đồng nghĩa event chưa được Kafka nhận. Nếu event quan trọng, cần outbox hoặc cơ chế lưu phục hồi bền vững.

**Đưa lỗi producer vào DLT ngay lập tức.** Producer có thể không có quyền ghi DLT; DLT nghiệp vụ cũng không thay thế kho lưu event chưa publish.

**Khởi động lại service mà không sửa ACL.** Restart không thay đổi quyền của principal. Chỉ xem xét tái tạo producer/client nếu cần thiết sau khi policy hoặc credential được sửa và trạng thái client yêu cầu.

## 12. Checklist vận hành

**Nhận diện lỗi**

- [ ] Phân biệt authentication failure và authorization failure.
- [ ] Lấy exception gốc và toàn bộ cause chain.
- [ ] Xác định đúng cluster, topic, operation hoặc transactional ID.
- [ ] Đối chiếu principal broker nhìn thấy.

**Kiểm tra quyền**

- [ ] Producer có **WRITE** trên topic đích.
- [ ] Producer idempotent có quyền **IDEMPOTENT_WRITE** nếu authorizer yêu cầu.
- [ ] Transactional producer có quyền **WRITE** trên transactional ID và topic liên quan.
- [ ] Resource pattern, host restriction và ACL DENY đã được kiểm tra.
- [ ] Quyền được cấp trên đúng cluster và môi trường.

**Phục hồi ứng dụng**

- [ ] Có xử lý cho cả exception đồng bộ và future thất bại.
- [ ] Authorization failure không bị retry vô hạn.
- [ ] Event chưa publish được lưu trong outbox hoặc cơ chế phục hồi bền vững.
- [ ] Exception không bị nuốt trong transaction.
- [ ] Sau khi sửa ACL, event được phát lại theo chính sách idempotency.

**Quan sát và quy trình**

- [ ] Log có principal, resource, operation, cluster, timestamp và event/correlation ID.
- [ ] Credential và payload nhạy cảm không bị ghi vào log.
- [ ] Alert có hướng dẫn đội phụ trách kiểm tra ACL.
- [ ] Runbook xác định người có thẩm quyền sửa quyền và cách xác minh sau thay đổi.
- [ ] Có kiểm thử trên môi trường tương đương production.

## 13. Nguyên tắc xử lý

Khi producer của Spring Kafka gặp AuthorizationException, hãy coi đây là tín hiệu cho biết một danh tính đã xác thực đang thực hiện thao tác vượt quá quyền được cấp. Việc cần làm là xác định principal, resource và operation bị từ chối, sau đó sửa policy theo nguyên tắc quyền tối thiểu.

Ở phía ứng dụng, cần phát hiện lỗi ở cả đường đồng bộ và bất đồng bộ, phân loại cause chain, tránh retry vô hạn và bảo toàn event chưa publish. Ở phía nền tảng, cần xác minh principal thực tế, ACL và resource pattern trên đúng cluster, rồi cấp quyền phù hợp cho topic, cluster hoặc transactional ID. Chỉ sau khi kiểm thử từ đúng workload và xác nhận broker acknowledgement mới xem luồng publish đã phục hồi.
