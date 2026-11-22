# Sao chép, bổ sung, loại bỏ và giới hạn header nhạy cảm

Trong Spring Messaging, header là metadata gắn với Message. Khi message đi qua nhiều handler hoặc được chuyển tiếp sang JMS, STOMP hay một service khác, ứng dụng thường cần sao chép một số header, bổ sung thông tin xử lý, loại bỏ metadata đã hết ý nghĩa và ngăn dữ liệu nhạy cảm đi qua ranh giới không được phép.

Các thao tác này cần có quy tắc rõ ràng. Sao chép toàn bộ header có thể vô tình mang theo channel nội bộ, session object, thông tin xác thực hoặc dữ liệu do client tự khai báo. Cách an toàn là xác định header nào thuộc contract của ứng dụng và chỉ chuyển tiếp những key được cho phép.

## 1. Nguyên tắc về tính bất biến

MessageHeaders triển khai Map<String, Object>, nhưng header của một message đã được tạo thường là immutable. Không sửa trực tiếp bằng put, remove hoặc clear:

~~~java
message.getHeaders().put("appCorrelationId", "corr-42");
~~~

Thao tác trên sẽ ném UnsupportedOperationException. Muốn thay đổi header, hãy tạo message mới bằng MessageBuilder hoặc dùng MessageHeaderAccessor.

Cách làm này giúp một thành phần không âm thầm thay đổi metadata mà thành phần khác đang đọc. Mỗi lần bổ sung hoặc loại bỏ header đều tạo ra một bước xử lý có thể kiểm tra và kiểm thử.

## 2. Sao chép header từ message hiện có

### 2.1. Dùng MessageBuilder.fromMessage

fromMessage tạo builder cho message mới, giữ payload và copy các header từ message nguồn:

~~~java
Message<String> forwarded = MessageBuilder
        .fromMessage(inbound)
        .build();
~~~

Đây là cách thuận tiện khi cần tạo một message mới có cùng payload và metadata. Tuy nhiên, nó cũng copy những header mà thành phần hiện tại có thể không nên chuyển tiếp, chẳng hạn replyChannel, errorChannel, simpSessionAttributes hoặc header nội bộ của một adapter.

Vì vậy, trước khi dùng fromMessage ở ranh giới giữa các service hoặc protocol, hãy xác định rõ header nào được phép tồn tại ở đích.

### 2.2. Dùng copyHeaders

copyHeaders(Map<String, ?>) copy các cặp key-value từ map vào builder. Giá trị từ map sẽ ghi đè header cùng tên đã có trong builder. Hai header hệ thống id và timestamp không bị ghi đè.

~~~java
Map<String, Object> extraHeaders = new HashMap<>();
extraHeaders.put("appSource", "order-service");
extraHeaders.put("appSchemaVersion", 2);

Message<String> enriched = MessageBuilder
        .fromMessage(inbound)
        .copyHeaders(extraHeaders)
        .build();
~~~

Trong ví dụ, appSource và appSchemaVersion được thêm vào message. Nếu message nguồn đã có một trong hai key này, giá trị từ extraHeaders sẽ thay thế giá trị cũ.

Dùng copyHeaders khi thành phần hiện tại là nguồn có thẩm quyền đối với những key đang ghi. Không dùng nó một cách tùy tiện với map nhận trực tiếp từ client hoặc từ một hệ thống không đáng tin cậy.

### 2.3. Dùng copyHeadersIfAbsent

copyHeadersIfAbsent(Map<String, ?>) chỉ copy những key chưa có giá trị. Header đã tồn tại trong builder được giữ nguyên.

~~~java
Message<String> enriched = MessageBuilder
        .fromMessage(inbound)
        .copyHeadersIfAbsent(extraHeaders)
        .build();
~~~

Cách này phù hợp khi bổ sung metadata mặc định. Ví dụ, một handler có thể đặt appSource nếu producer trước đó chưa cung cấp.

Cần phân biệt hai phương thức:

| Phương thức | Khi key đã tồn tại | Trường hợp phù hợp |
|---|---|---|
| copyHeaders(map) | Ghi đè giá trị cũ | Thành phần hiện tại sở hữu giá trị mới |
| copyHeadersIfAbsent(map) | Giữ nguyên giá trị cũ | Bổ sung giá trị mặc định |
| setHeader(name, value) | Ghi giá trị mới; nếu value là null thì xóa key | Cập nhật một header cụ thể |
| setHeaderIfAbsent(name, value) | Chỉ đặt khi key chưa có giá trị | Bổ sung một header đơn lẻ |

Lưu ý: copyHeaders không có nghĩa là mọi header đều được phép ghi đè. id và timestamp là các header hệ thống được Spring bảo vệ theo quy tắc của MessageBuilder.

## 3. Bổ sung và cập nhật header

### 3.1. setHeader

setHeader đặt hoặc thay giá trị của một header:

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-42")
        .setHeader("appCorrelationId", "corr-900")
        .setHeader("appSource", "checkout")
        .setHeader("appSchemaVersion", 2)
        .build();
~~~

Mỗi key nên có một ý nghĩa và kiểu dữ liệu ổn định. Ví dụ, appSchemaVersion luôn là Integer hoặc luôn là String theo contract đã chọn; không để producer lúc gửi số, lúc gửi chuỗi.

### 3.2. setHeaderIfAbsent

Nếu muốn thêm giá trị mặc định mà không thay thế giá trị đã có, dùng setHeaderIfAbsent:

~~~java
Message<String> message = MessageBuilder
        .fromMessage(inbound)
        .setHeaderIfAbsent("appSource", "unknown-producer")
        .build();
~~~

Điều này hữu ích khi nhiều handler cùng bổ sung metadata. Handler phía sau không ghi đè giá trị hợp lệ do handler phía trước đã đặt.

### 3.3. setHeader với null

Trong MessageBuilder và MessageHeaderAccessor, đặt giá trị null có nghĩa là loại bỏ header đó:

~~~java
Message<String> sanitized = MessageBuilder
        .fromMessage(inbound)
        .setHeader("appTemporaryFlag", null)
        .build();
~~~

Nếu cần thể hiện một giá trị nghiệp vụ thật sự là null, hãy đặt quy ước trong payload hoặc schema. Header map không phân biệt một key có giá trị null với một key đã bị loại bỏ theo cách có thể dùng như một contract ổn định.

## 4. Loại bỏ một hoặc nhiều header

### 4.1. Loại bỏ một key

Dùng removeHeader khi biết chính xác key cần xóa:

~~~java
Message<String> sanitized = MessageBuilder
        .fromMessage(inbound)
        .removeHeader("appInternalRoute")
        .build();
~~~

removeHeader phù hợp khi một header chỉ có ý nghĩa ở một tầng xử lý. Ví dụ, adapter nội bộ đã dùng xong appInternalRoute và không muốn chuyển metadata đó sang service tiếp theo.

### 4.2. Loại bỏ theo pattern

removeHeaders(String... headerPatterns) cho phép xóa nhiều key theo các pattern đơn giản. Spring hỗ trợ các dạng:

- xxx*: key bắt đầu bằng xxx.
- *xxx: key kết thúc bằng xxx.
- *xxx*: key có chứa xxx.
- xxx*yyy: key bắt đầu bằng xxx và kết thúc bằng yyy.

Ví dụ:

~~~java
Message<String> sanitized = MessageBuilder
        .fromMessage(inbound)
        .removeHeaders(
                "authorization",
                "cookie",
                "*token*",
                "*secret*",
                "appInternal*"
        )
        .build();
~~~

Các pattern giúp loại bỏ một nhóm header có quy ước tên chung. Hãy dùng chúng có chủ đích; một pattern quá rộng có thể xóa cả metadata cần thiết cho việc tracing hoặc correlation.

Tên header trong MessageHeaders là key của Map và cần được khớp theo đúng tên mà ứng dụng đang sử dụng. Đừng giả định mọi adapter đều tự chuẩn hóa chữ hoa/chữ thường giống nhau.

### 4.3. Loại bỏ header bằng MessageHeaderAccessor

MessageHeaderAccessor cung cấp API tương tự để chỉnh sửa header:

~~~java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(inbound);

accessor.removeHeader("appInternalRoute");
accessor.setHeaderIfAbsent("appSource", "order-service");

Message<String> sanitized = MessageBuilder.createMessage(
        inbound.getPayload(),
        accessor.getMessageHeaders()
);
~~~

getMutableAccessor tạo accessor có thể chỉnh sửa cho message hiện có và cố gắng giữ đúng loại accessor ban đầu để các thành phần phía sau tiếp tục hiểu metadata chuyên biệt.

Mặc định, khi gọi getMessageHeaders(), accessor hoàn tất việc xây dựng header và chuyển chúng sang trạng thái immutable. Nếu đặt setLeaveMutable(true), header vẫn mutable sau khi lấy MessageHeaders; khi hoàn tất bắt buộc gọi setImmutable(). Cơ chế để mutable chỉ nên dùng trong giai đoạn khởi tạo ngắn, thường trong cùng một thread, không nên để message mutable đi qua nhiều thread hoặc thành phần độc lập.

## 5. Giới hạn header nhạy cảm khi chuyển tiếp message

### 5.1. Vì sao không nên copy toàn bộ header?

Một message đầu vào có thể chứa nhiều loại metadata:

- Header nghiệp vụ như appCorrelationId, appEventId hoặc appSchemaVersion.
- Header nội bộ như replyChannel, errorChannel hoặc thông tin session.
- Header transport như destination, receipt hoặc correlation ID của broker.
- Header xác thực như authorization, cookie, access token hoặc API key.
- Header do client tự khai báo, chưa được server xác thực.

Khi chuyển message sang một service khác, một số header có thể không còn ý nghĩa. Một số khác có thể gây lộ thông tin nếu xuất hiện trong log, broker hoặc hệ thống tracing.

Đặc biệt, không đưa access token, refresh token, mật khẩu, cookie phiên, API key hoặc credential kết nối broker vào header nghiệp vụ để tiện truyền qua các service. Nếu một transport bắt buộc dùng thông tin xác thực ở tầng kết nối, hãy để cơ chế bảo mật của transport quản lý riêng và không copy thông tin đó vào message application.

### 5.2. Ưu tiên allowlist

Allowlist xác định chính xác những header được phép đi qua ranh giới. Đây là cách dễ kiểm soát khi message đến từ trình duyệt, API public, broker bên ngoài hoặc một service khác.

Ví dụ chỉ chuyển tiếp correlation ID, event ID và schema version:

~~~java
private static Map<String, Object> allowedHeaders(Message<?> inbound) {
    Map<String, Object> allowed = new HashMap<>();

    for (String name : List.of(
            "appCorrelationId",
            "appEventId",
            "appSchemaVersion"
    )) {
        Object value = inbound.getHeaders().get(name);
        if (value != null) {
            allowed.put(name, value);
        }
    }

    return allowed;
}
~~~

Tạo message đầu ra từ payload và map đã lọc:

~~~java
Message<?> outbound = MessageBuilder
        .withPayload(inbound.getPayload())
        .copyHeaders(allowedHeaders(inbound))
        .setHeader("appForwardedBy", "order-service")
        .build();
~~~

Message đầu ra chỉ nhận những key trong allowlist và header do service hiện tại tự đặt. Vì builder bắt đầu bằng withPayload, các header nội bộ không được chọn sẽ không bị mang theo. Spring tạo metadata hệ thống cho message mới theo cơ chế mặc định.

Nếu appCorrelationId hoặc appEventId đến từ nguồn bên ngoài, hãy kiểm tra độ dài, định dạng và kiểu dữ liệu trước khi đưa vào allowlist. Nếu appTenantId là giá trị do server xác lập, không lấy nó từ header client rồi chuyển tiếp như một dữ liệu đáng tin cậy.

### 5.3. Denylist chỉ là lớp lọc bổ sung

Trong một luồng nội bộ đã tin cậy, có thể copy message rồi loại bỏ những key nhạy cảm đã biết:

~~~java
Message<?> outbound = MessageBuilder
        .fromMessage(inbound)
        .removeHeaders(
                "authorization",
                "cookie",
                "set-cookie",
                "*token*",
                "*secret*",
                "appPrivate*"
        )
        .build();
~~~

Denylist hữu ích khi hệ thống đã có contract header tương đối ổn định và muốn loại bỏ một số nhóm cụ thể. Tuy nhiên, một header nhạy cảm mới có thể xuất hiện với tên chưa nằm trong danh sách. Vì vậy, denylist không thay thế allowlist khi chuyển dữ liệu qua ranh giới tin cậy.

Không dùng cách copy toàn bộ rồi chỉ xóa một vài key nếu nguồn đầu vào có thể tùy ý tạo header. Hãy giới hạn danh sách key được chấp nhận ngay từ đầu.

## 6. Native header cần được xử lý riêng

Một số adapter lưu header của protocol bên ngoài trong native header map, tách khỏi các processing header mà Spring sử dụng nội bộ. Ví dụ, STOMP frame có native headers riêng.

Vì vậy, gọi removeHeaders trên MessageBuilder chỉ xử lý các key ở lớp MessageHeaders tương ứng; không nên mặc định nó xóa mọi key nằm sâu trong native header map.

Với STOMP, dùng StompHeaderAccessor hoặc NativeMessageHeaderAccessor để thao tác native header:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(inbound);

accessor.removeNativeHeader("authorization");
accessor.removeNativeHeader("appPrivateToken");

Message<?> sanitized = MessageBuilder.createMessage(
        inbound.getPayload(),
        accessor.getMessageHeaders()
);
~~~

Nếu message được chuyển qua JMS, dùng các accessor/header mapper JMS tương ứng và kiểm tra mapping thật sự của provider. Không copy nguyên native header của STOMP sang JMS hoặc ngược lại: tên key, kiểu giá trị và ý nghĩa protocol có thể khác nhau.

Một allowlist ở lớp application vẫn cần thiết. Việc xóa native header nhạy cảm là lớp bảo vệ bổ sung cho adapter, không phải lý do để chuyển tiếp toàn bộ native header.

## 7. Quyền sở hữu và độ tin cậy của header

Không phải mọi header trong message đều có cùng mức độ tin cậy.

| Nguồn header | Cách xử lý |
|---|---|
| Spring tạo như id và timestamp | Để Spring quản lý; không dùng thay ID nghiệp vụ |
| Service hiện tại tạo | Có thể cập nhật nếu service sở hữu contract đó |
| Service nội bộ khác gửi | Kiểm tra schema, kiểu dữ liệu và quyền sở hữu trước khi ghi đè |
| WebSocket/HTTP client gửi | Xem là dữ liệu đầu vào chưa tin cậy; xác thực và validate |
| Broker hoặc protocol adapter gửi | Dùng accessor chuyên biệt và mapping đã xác định |
| Header xác thực/credential | Không đưa vào application header hoặc log; xử lý ở tầng security/transport |

Một header tên appTenantId hoặc appUserId không tự chứng minh người gửi thuộc tenant hoặc user đó. Server phải lấy danh tính từ SecurityContext hoặc principal đã xác thực và tự xác định giá trị được phép.

Tương tự, appRole, appPermission hoặc appIsAdmin do client gửi không được dùng để cấp quyền. Header là dữ liệu; quyền truy cập phải được quyết định bằng cơ chế xác thực và phân quyền ở server.

## 8. Giới hạn số lượng, kích thước và kiểu dữ liệu

Ngoài việc giới hạn key được copy, ứng dụng nên đặt giới hạn cho dữ liệu header đầu vào:

- Giới hạn số lượng header được chấp nhận.
- Giới hạn độ dài tên key và giá trị.
- Chỉ cho phép các kiểu dữ liệu có thể serialize ổn định.
- Từ chối object tùy ý, Spring bean, channel, servlet request hoặc entity lớn.
- Giới hạn tổng dung lượng metadata trước khi gửi qua broker hoặc WebSocket.
- Chuẩn hóa và validate định dạng ID, version, tenant và correlation.
- Loại bỏ hoặc từ chối key không nằm trong contract nếu nguồn gửi không được phép mở rộng header.

Giới hạn cụ thể phụ thuộc protocol và hạ tầng. JMS provider, STOMP broker, reverse proxy và ứng dụng có thể có ngưỡng khác nhau. Đừng giả định một giới hạn chung của Spring sẽ tự động bảo vệ mọi transport.

Cũng cần cân nhắc kiểu dữ liệu sau khi serialize. Một Integer trong Spring Message có thể trở thành String khi đi qua một adapter hoặc broker. Contract nên định nghĩa kiểu ở mỗi ranh giới và có kiểm thử cho mapping thực tế.

## 9. Một luồng xử lý header an toàn

Ví dụ một API gateway nhận message từ client rồi chuyển tới service nghiệp vụ:

~~~text
Client
  |
  | payload + headers do client gửi
  v
Inbound validation
  |
  | xác thực principal, validate key/value
  | chỉ giữ application headers được cho phép
  v
Application Message
  |
  | thêm appSource, appCorrelationId
  | bỏ header nội bộ/nhạy cảm
  v
Outbound adapter
  |
  | map sang JMS/STOMP theo contract
  v
Downstream service
~~~

Một thứ tự xử lý phù hợp:

1. Nhận message và xác định nguồn gửi.
2. Xác thực danh tính ở tầng security.
3. Kiểm tra key, kiểu dữ liệu, độ dài và tổng dung lượng header.
4. Chọn application header được phép bằng allowlist.
5. Bổ sung metadata do service hiện tại sở hữu.
6. Loại bỏ header nội bộ hoặc protocol không phù hợp với đích.
7. Map native header tại adapter đích.
8. Ghi log theo correlation/event ID, không log credential hoặc dữ liệu nhạy cảm.

Không chuyển nguyên MessageHeaders qua mọi service chỉ vì các service cùng dùng Spring. Mỗi ranh giới nên có contract riêng và chỉ nhận metadata cần thiết.

## 10. Kiểm thử sao chép và lọc header

Nên có unit test cho logic allowlist/denylist và integration test cho adapter.

Các tình huống quan trọng:

1. copyHeaders ghi đè một application header trùng tên như dự kiến.
2. copyHeadersIfAbsent giữ lại giá trị đã có.
3. setHeaderIfAbsent không ghi đè giá trị nguồn.
4. setHeader với null và removeHeader loại bỏ đúng key.
5. removeHeaders xử lý đúng các pattern được hỗ trợ.
6. id và timestamp không bị ghi đè bằng copyHeaders.
7. Header authorization, cookie, token và secret không xuất hiện trong message đầu ra.
8. Header không nằm trong allowlist bị loại bỏ khi qua ranh giới public.
9. replyChannel, errorChannel và session metadata không bị chuyển sang service không liên quan.
10. Native STOMP header nhạy cảm được xóa bằng accessor phù hợp.
11. Header tenant/user do client gửi không thể thay thế danh tính server đã xác thực.
12. Header sai kiểu, quá dài hoặc quá nhiều bị từ chối theo chính sách.
13. JMS/STOMP mapping giữ nguyên các application header hợp lệ và không mang theo protocol metadata không được phép.

Unit test chỉ xác nhận logic trong bộ nhớ. Để xác nhận native header và serialization, hãy chạy integration test với adapter/provider hoặc broker tương ứng.

## 11. Checklist trước khi chuyển tiếp message

- Payload có được giữ nguyên theo contract không?
- Header nào thực sự cần ở service đích?
- Header nào thuộc Spring nội bộ hoặc protocol nguồn?
- Có header xác thực, cookie, token, secret hoặc PII không?
- Nguồn gửi có được phép đặt header đó không?
- Dùng allowlist hay denylist phù hợp với ranh giới tin cậy?
- copyHeaders có thể ghi đè giá trị nào?
- Header cần map sang native protocol nào?
- Kiểu dữ liệu và kích thước có hợp lệ ở transport đích không?
- Log và tracing có vô tình ghi metadata nhạy cảm không?
- Có test chứng minh header không được phép đã bị loại bỏ không?

## 12. Tài liệu tham khảo

- [Spring Framework 6.1 — MessageBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework 6.1 — MessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework 6.1 — MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework 6.1 — NativeMessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html)
- [Spring Framework 6.1 — StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)

Một quy tắc thực tế dễ duy trì là: copy có chọn lọc, chỉ ghi đè header do thành phần hiện tại sở hữu, loại bỏ metadata nội bộ khi qua ranh giới và không để credential đi theo application message.