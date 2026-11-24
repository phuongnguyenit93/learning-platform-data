# Giới hạn destination động và biểu thức có thể bị điều khiển

Spring Cloud Stream cho phép ứng dụng quyết định nơi gửi message tại thời điểm chạy. `StreamBridge` có thể tạo output binding động; header `spring.cloud.stream.sendto.destination` có thể yêu cầu framework gửi kết quả tới một destination; Spring Cloud Function có thể chọn function bằng header `spring.cloud.function.definition` hoặc biểu thức SpEL trong `spring.cloud.function.routing-expression`. Những khả năng này hữu ích cho router, tenant-aware event gateway và ứng dụng tích hợp nhiều broker.

Chính tính linh hoạt đó tạo ra ranh giới bảo mật. Nếu tên destination, tên function hoặc chuỗi biểu thức được lấy trực tiếp từ HTTP request, message header hay hệ thống bên ngoài, người gửi có thể tác động đến nơi message được publish hoặc đoạn xử lý được gọi. Một destination tùy ý có thể làm ứng dụng tạo topic/queue ngoài dự kiến, vượt ranh giới tenant, phát dữ liệu sang hệ thống không được phép hoặc tiêu thụ tài nguyên broker. Một biểu thức SpEL không đáng tin cậy có thể truy cập các đối tượng và khả năng mà người viết ứng dụng không định cung cấp cho bên ngoài.

Bài học này trình bày cách giới hạn destination động, kiểm soát function routing, bảo vệ SpEL, xác thực và phân quyền route, cấu hình binder/broker theo nguyên tắc quyền tối thiểu, ghi audit và kiểm thử các trường hợp đầu vào bị điều khiển. Nguyên tắc xuyên suốt là bên ngoài có thể yêu cầu một loại nghiệp vụ, còn ứng dụng tự ánh xạ yêu cầu đó sang destination hoặc function đã được cho phép.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách StreamBridge tạo và cache dynamic output binding.
- Sử dụng `spring.cloud.stream.dynamic-destinations` như một allowlist destination.
- Phân biệt giới hạn destination với xác thực và phân quyền người gọi.
- Nhận diện header có thể điều khiển output destination hoặc function routing.
- Phân biệt `spring.cloud.function.definition` với `spring.cloud.function.routing-expression`.
- Hiểu khác biệt giữa SpEL từ message header và SpEL từ application property.
- Dùng mapping cố định hoặc `MessageRoutingCallback` để định tuyến an toàn.
- Ngăn tenant tự chọn destination ngoài phạm vi được cấp quyền.
- Giới hạn quyền tạo topic/queue và quyền publish ở broker.
- Kiểm thử injection, route bypass, resource exhaustion và audit.

## 1. Dynamic destination là gì?

Trong Spring Cloud Stream, binding thông thường được khai báo trước trong cấu hình. Ví dụ `orders-out-0` gắn với destination `orders.events`. Với dynamic destination, ứng dụng có thể yêu cầu framework tạo binding output khi chạy mà không cần khai báo trước binding đó.

`StreamBridge` hỗ trợ mô hình này:

~~~java
@RestController
class EventIngressController {

    private final StreamBridge streamBridge;

    EventIngressController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/events")
    ResponseEntity<Void> publish(@RequestBody OrderEvent event) {
        streamBridge.send("orders.events", event);
        return ResponseEntity.accepted().build();
    }
}
~~~

Nếu tên được truyền vào `send` chưa phải binding đã tồn tại, StreamBridge có thể tạo output binding động và provision destination nếu binder hỗ trợ. Binding được cache để tái sử dụng ở các lần gửi sau. Cơ chế này tiện lợi khi destination thực sự chỉ được biết lúc chạy, nhưng cũng có nghĩa một giá trị đầu vào có thể ảnh hưởng tới tài nguyên messaging mà ứng dụng sử dụng.

### 1.1. Những điểm có thể bị điều khiển

| Điểm vào | Cách nó ảnh hưởng định tuyến |
|---|---|
| Đối số đầu tiên của `StreamBridge.send` | Chọn binding/destination output |
| Header `spring.cloud.stream.sendto.destination` | Yêu cầu framework resolve output destination |
| Header `spring.cloud.function.definition` | Chọn function hoặc composition cần gọi |
| Header `spring.cloud.function.routing-expression` | Cung cấp biểu thức SpEL để chọn function |
| Property `spring.cloud.function.definition` | Chọn function ở cấp ứng dụng |
| Property `spring.cloud.function.routing-expression` | Đặt biểu thức routing ở cấp ứng dụng |
| Binder type trong overload StreamBridge | Chọn binder dùng để tạo binding động khi nhiều binder có mặt |

Không phải tất cả giá trị trên đều mặc nhiên đến từ người dùng cuối. Tuy nhiên, nếu HTTP adapter chuyển header vào Message, producer bên ngoài có thể gửi header tùy ý, hoặc một hệ thống trung gian có thể sửa message, hãy xem các giá trị đó là đầu vào không đáng tin cậy cho tới khi được kiểm tra.

## 2. Rủi ro khi destination được chọn từ đầu vào

Giả sử một API nhận trường `destination` rồi gọi trực tiếp `streamBridge.send(destination, event)`. Nếu ứng dụng cho phép mọi tên destination, người gọi có thể yêu cầu gửi sang một topic hoặc queue mà API không được thiết kế để truy cập.

Các rủi ro thường gặp:

- **Publish trái phép:** người gọi gửi dữ liệu tới destination nội bộ, audit stream hoặc queue của dịch vụ khác.
- **Vượt tenant:** tenant A chọn tên destination của tenant B và đọc/ghi dữ liệu ngoài phạm vi của mình.
- **Tạo tài nguyên không kiểm soát:** nhiều tên khác nhau có thể làm binder provision topic/queue mới nếu broker và binder được cấp quyền.
- **Cạn tài nguyên:** tạo nhiều binding, cache entry, topic, queue hoặc metadata khiến ứng dụng và broker chịu tải lớn.
- **Rò rỉ dữ liệu:** event được chuyển tới destination có consumer hoặc chính sách retention khác với dự kiến.
- **Sai binder:** trong ứng dụng nhiều binder, lựa chọn binder động không được kiểm soát có thể gửi message sang cluster không đúng.
- **Audit khó truy vết:** tên destination tùy ý làm khó xác định owner, SLA, retention và quy trình xử lý lỗi.

Tên destination không phải chỉ là chuỗi định danh vô hại. Trong một số cấu hình, việc resolve tên có thể kích hoạt tạo binding và provision tài nguyên broker. Hãy xem destination như một quyền truy cập tài nguyên.

## 3. Allowlist destination động

Spring Cloud Stream có property `spring.cloud.stream.dynamic-destinations` để giới hạn tên destination được phép bind động. Nếu property được cấu hình, chỉ những destination có trong danh sách mới được bind động. Nếu không cấu hình, mặc định là cho phép bind bất kỳ destination nào.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.events
        - billing.events
        - audit.events
~~~

Khi đó, các tên ngoài danh sách không được tạo thành dynamic binding. Hãy cấu hình allowlist tường minh cho ứng dụng có dùng dynamic destination.

### 3.1. Allowlist là một lớp bảo vệ, không phải phân quyền người dùng

Allowlist trả lời câu hỏi: ứng dụng có được tạo binding động tới destination này hay không? Nó không trả lời câu hỏi: người dùng hiện tại có được phép publish tới destination đó hay không?

Nếu danh sách có `orders.events` và `billing.events`, mọi request đi qua cùng một service credential vẫn có thể yêu cầu hai destination đó nếu ứng dụng không kiểm tra quyền của principal. Vì vậy cần kết hợp:

1. Allowlist cấp ứng dụng.
2. Mapping route do server quản lý.
3. Authorization theo người dùng, tenant hoặc service identity.
4. Broker ACL/vhost/namespace policy.

Không dùng allowlist thay cho authorization.

### 3.2. Không xây allowlist từ dữ liệu request

Không nên đọc một danh sách tên destination từ request rồi đưa thẳng vào property hoặc resolver. Allowlist phải được quản lý bởi cấu hình tin cậy hoặc mã nguồn đã review.

Nếu hệ thống cần route theo tenant, đừng tạo tên destination từ một chuỗi tenantId bất kỳ. Hãy xác thực tenant từ identity đã xác minh, kiểm tra quyền của tenant, sau đó tra cứu destination đã đăng ký trong cấu hình hoặc registry tin cậy.

## 4. Giới hạn cache dynamic destination

StreamBridge cache các output binding động để tái sử dụng. Tài liệu Spring Cloud Stream hiện hành mô tả cache tự loại bỏ entry cũ với kích thước mặc định là 10. Có thể cấu hình kích thước bằng `spring.cloud.stream.dynamic-destination-cache-size`.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destination-cache-size: 8
~~~

Cache size giúp kiểm soát số binding đang được giữ trong cache và hạn chế tăng bộ nhớ do nhiều binding động. Khi vượt giới hạn, binding cũ có thể bị loại khỏi cache và phải được tạo lại ở lần gửi sau.

**Cache size không phải allowlist và không phải quota tạo destination.** Việc cache loại một binding khỏi bộ nhớ không đồng nghĩa topic/queue đã được xóa khỏi broker. Người gửi vẫn có thể yêu cầu nhiều tên khác nhau theo thời gian, làm tăng số tài nguyên broker hoặc số lần tạo binding. Vì vậy:

- Dùng `dynamic-destinations` để giới hạn tên được phép.
- Dùng cache size phù hợp với tập destination hữu hạn.
- Đặt quota hoặc policy ở broker nếu nền tảng hỗ trợ.
- Rate limit API và giới hạn số tenant/destination đã đăng ký.
- Theo dõi số binding động và số topic/queue được provision.

Không tăng cache size để xử lý một luồng tên destination không giới hạn. Trước hết hãy xác định vì sao ứng dụng cần tạo destination mới.

## 5. Ưu tiên output binding khai báo sẵn

Nếu danh sách output destination đã biết khi triển khai, nên khai báo binding tĩnh. Cách này giúp review được binder, destination, serialization và producer properties trước khi ứng dụng chạy.

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      output-bindings: orders-out-0;billing-out-0
      bindings:
        orders-out-0:
          destination: orders.events
          binder: kafka
        billing-out-0:
          destination: billing.events
          binder: rabbit
~~~

Ứng dụng có thể gọi StreamBridge bằng binding name đã khai báo:

~~~java
streamBridge.send("orders-out-0", orderEvent);
streamBridge.send("billing-out-0", billingEvent);
~~~

Giá trị người dùng gửi vào chỉ nên là một route key như `orders` hoặc `billing`. Ứng dụng tra route key sang binding name đã biết; không dùng trực tiếp chuỗi request làm binding name.

Binding tĩnh không tự xác thực người dùng. Vẫn phải kiểm tra authorization trước khi gửi. Tuy nhiên, nó thu hẹp khả năng tạo destination ngoài dự kiến và làm cấu hình broker dễ kiểm soát hơn.

## 6. Mapping route bằng danh sách cố định

Một cách an toàn là định nghĩa tập route được phép trong code hoặc cấu hình tin cậy:

~~~java
@Component
class EventPublisher {

    private static final Map<String, String> BINDINGS = Map.of(
            "orders", "orders-out-0",
            "billing", "billing-out-0");

    private final StreamBridge streamBridge;
    private final DestinationAuthorizer authorizer;

    EventPublisher(
            StreamBridge streamBridge,
            DestinationAuthorizer authorizer) {
        this.streamBridge = streamBridge;
        this.authorizer = authorizer;
    }

    boolean publish(
            String routeKey,
            Principal principal,
            Object event) {

        String binding = BINDINGS.get(routeKey);
        if (binding == null) {
            throw new IllegalArgumentException("Unsupported route");
        }

        authorizer.requirePublishPermission(principal, routeKey);

        return streamBridge.send(binding, event);
    }
}
~~~

Trong ví dụ:

- `routeKey` chỉ có thể là một key đã định nghĩa.
- Binding name được lấy từ map do ứng dụng quản lý.
- Authorization được kiểm tra trước khi gửi.
- Người gọi không thể truyền trực tiếp một tên topic tùy ý.

Trong ứng dụng thực tế, có thể dùng enum thay cho String để biểu diễn route. Nếu route key được nhận từ URL hoặc JSON, hãy kiểm tra null, độ dài và tập giá trị hợp lệ; từ chối route không biết thay vì tự ghép tên destination.

### 6.1. Authorization phải gắn với principal

Ví dụ `DestinationAuthorizer` cần kiểm tra người gọi có quyền publish route tương ứng. Với multi-tenant:

- Lấy tenant từ token/session đã xác thực.
- Không coi tenantId trong payload hoặc header tự khai là danh tính đã xác minh.
- Kiểm tra tenant có sở hữu hoặc được cấp quyền dùng route đó.
- Ánh xạ tenant và route sang destination do server quản lý.
- Từ chối nếu không có quyền, kể cả destination nằm trong allowlist toàn ứng dụng.

Nếu một tenant cần destination riêng, hãy lưu mapping tenant-to-destination trong registry được kiểm soát và xác minh quyền truy cập registry. Không nối chuỗi từ input thành tên topic mà không qua bước xác thực và phân quyền.

## 7. StreamBridge trong ứng dụng có nhiều binder

Spring Cloud Stream hỗ trợ nhiều binder trong cùng ứng dụng, ví dụ Kafka và RabbitMQ. Khi dùng StreamBridge và có nhiều binder, có overload cho phép chỉ định binder type:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.events
        - billing.events
~~~

~~~java
streamBridge.send("orders.events", "kafka", orderEvent);
streamBridge.send("billing.events", "rabbit", billingEvent);
~~~

Các tên `kafka` và `rabbit` minh họa binder type đã đăng ký trong ứng dụng. Binder type nên được chọn từ mapping nội bộ đã review, không lấy từ request hoặc message header. Tên destination ở ví dụ cũng phải nằm trong `dynamic-destinations`.

Overload có binder type được dùng khi StreamBridge tạo dynamic binding. Nếu output binding đã được tạo trước bằng `spring.cloud.stream.output-bindings` hoặc binding đã được tạo dưới một binder khác, đối số binder type không thay đổi binder đã gắn với binding. Với output binding tĩnh, dùng `send(bindingName, data)` và cấu hình binder ngay trên binding.

Nếu người gọi có thể chọn cả destination lẫn binder, bề mặt tấn công rộng hơn: cùng một route key có thể được gửi sang cluster khác, nơi có retention, ACL, consumer hoặc dữ liệu nhạy cảm khác. Hãy map một route nghiệp vụ sang cặp destination/binder cố định.

Ví dụ mapping:

| Route key | Dynamic destination | Binder type |
|---|---|---|
| orders | orders.events | kafka |
| billing | billing.events | rabbit |
| audit | audit.events | kafka |

Không cho client truyền `binderType` hoặc tên cluster. Những giá trị này thuộc cấu hình vận hành của ứng dụng.

## 8. Header spring.cloud.stream.sendto.destination

Spring Cloud Stream có thể định tuyến output bằng header `spring.cloud.stream.sendto.destination`. Framework đọc tên trong header và cố gắng resolve hoặc tạo destination có tên đó.

Ví dụ đơn giản:

~~~java
@Bean
Function<OrderEvent, Message<OrderEvent>> routeOrder() {
    return event -> MessageBuilder.withPayload(event)
            .setHeader(
                    "spring.cloud.stream.sendto.destination",
                    "orders.events")
            .build();
}
~~~

Ví dụ trên dùng destination cố định. Rủi ro xuất hiện nếu giá trị header được lấy trực tiếp từ payload hoặc header bên ngoài:

~~~java
// Không an toàn: dữ liệu đầu vào điều khiển destination
@Bean
Function<OrderEvent, Message<OrderEvent>> unsafeRoute() {
    return event -> MessageBuilder.withPayload(event)
            .setHeader(
                    "spring.cloud.stream.sendto.destination",
                    event.requestedDestination())
            .build();
}
~~~

Không tạo header định tuyến từ trường do client tự khai. Hãy thay bằng giá trị server đã xác thực và tra cứu từ allowlist:

~~~java
@Bean
Function<OrderEvent, Message<OrderEvent>> safeRoute() {
    return event -> {
        String destination = switch (event.eventType()) {
            case "ORDER_CREATED" -> "orders.events";
            case "BILLING_REQUESTED" -> "billing.events";
            default -> throw new IllegalArgumentException("Unsupported event type");
        };

        return MessageBuilder.withPayload(event)
                .setHeader(
                        "spring.cloud.stream.sendto.destination",
                        destination)
                .build();
    };
}
~~~

Trong ví dụ thực tế, kiểm tra quyền của principal phải diễn ra trước khi function tạo output. Nếu function chỉ nhận message từ broker, dùng identity/service authorization phù hợp với nguồn message; không mặc định event type hợp lệ đồng nghĩa người phát có quyền route.

## 9. Function routing và hai header khác nhau

Spring Cloud Function có hai header routing quan trọng:

- `spring.cloud.function.definition`: tên một function hoặc một chuỗi composition, ví dụ `validateOrder|acceptOrder`.
- `spring.cloud.function.routing-expression`: biểu thức SpEL trả về function definition cần gọi.

Hai header này điều khiển function được gọi, không phải destination output. Chúng có thể xuất hiện trong message header khi adapter chuyển header HTTP hoặc message từ broker vào Spring Cloud Function.

Để dùng `RoutingFunction` trong Spring Cloud Stream, bật routing bằng property `spring.cloud.stream.function.routing.enabled=true` hoặc cấu hình `spring.cloud.function.routing-expression` ở application level. Khi bật routing theo message header, hãy kiểm tra header trước khi đưa message vào router.

~~~yaml
spring:
  cloud:
    stream:
      function:
        routing:
          enabled: true
~~~

### 9.1. Function definition header

Nếu một message mang header `spring.cloud.function.definition`, routing function có thể dùng giá trị đó để chọn function. Vì giá trị có thể chứa tên function hoặc composition, không nên cho client tự chọn bất kỳ function bean nào trong catalog.

Ví dụ rủi ro về thiết kế:

~~~text
HTTP header:
  spring.cloud.function.definition = function-name-from-client

RoutingFunction:
  tra cứu function trong FunctionCatalog
~~~

Nếu catalog có function quản trị, function ghi dữ liệu hoặc function chỉ dành cho luồng nội bộ, việc cho người dùng chọn tên function có thể làm lộ capability không được cấp.

### 9.2. Routing expression header

Header `spring.cloud.function.routing-expression` cho phép gửi biểu thức SpEL để chọn function. Ví dụ hợp lệ trong tài liệu:

~~~properties
spring.cloud.function.routing-expression=headers.function_name
~~~

Biểu thức này đọc header `function_name` từ message và trả về function definition. Nhưng nếu người gửi có thể tự đặt toàn bộ chuỗi expression, họ có thể cố điều khiển quá trình đánh giá biểu thức hoặc chọn function ngoài phạm vi cho phép.

Spring Cloud Function hiện đánh giá expression đến từ message header bằng `SimpleEvaluationContext`, có giới hạn hơn `StandardEvaluationContext`. Expression đặt qua application property hoặc system/environment property được đánh giá bằng `StandardEvaluationContext`, có khả năng đầy đủ hơn. Đây là khác biệt quan trọng, nhưng không nên xem `SimpleEvaluationContext` là bảo đảm an toàn cho mọi expression không đáng tin cậy.

Spring Framework cảnh báo việc đánh giá SpEL từ nguồn không đáng tin cậy vốn nguy hiểm; `SimpleEvaluationContext` chỉ giới hạn một phần khả năng và không phải hàng rào an toàn tuyệt đối. Thiết kế tốt nhất là không cho người dùng gửi chuỗi expression. Hãy gửi route key có tập giá trị hữu hạn rồi để ứng dụng tự quyết định function.

### 9.3. Thứ tự ưu tiên routing

Theo Spring Cloud Function, với imperative function, thứ tự ưu tiên là:

1. `MessageRoutingCallback`.
2. Message headers nếu không có callback.
3. Application properties.

Điều này có nghĩa một header do message bên ngoài cung cấp có thể ghi đè routing expression ở application property nếu không có callback. Nếu cần routing do server kiểm soát, đăng ký callback để áp dụng policy cố định, hoặc loại bỏ/ghi đè các header routing không đáng tin cậy trước khi đến routing function.

Với reactive function, routing theo từng message header không áp dụng như imperative function; routing instructions được cung cấp ở application property vì unit of work là toàn stream. Không dựa vào sự khác biệt này để bỏ qua bảo vệ cấu hình.

## 10. Dùng MessageRoutingCallback để giới hạn function

`MessageRoutingCallback` cho phép ứng dụng quyết định function dựa trên message bằng code. Một callback an toàn dùng map route cố định thay vì diễn giải chuỗi do người gửi cung cấp:

~~~java
@Bean
MessageRoutingCallback secureRoutingCallback() {
    Map<String, String> allowedFunctions = Map.of(
            "ORDER_CREATED", "orderHandler",
            "PAYMENT_SETTLED", "paymentHandler");

    return message -> {
        String eventType = message.getHeaders()
                .get("event-type", String.class);

        String functionName = allowedFunctions.get(eventType);
        if (functionName == null) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        return functionName;
    };
}
~~~

Callback chỉ trả về tên function đã được map. Nó không parse chuỗi SpEL từ message. Vì callback được ưu tiên hơn header và application property cho imperative routing, nó giúp tập trung quyết định route trong code server.

Tuy nhiên, callback vẫn phải xác thực nguồn message và quyền nghiệp vụ nếu event type có thể được gửi bởi nhiều producer khác nhau. Route key hợp lệ không chứng minh producer có quyền phát event đó. Hãy dùng ACL ở broker và kiểm tra identity/tenant theo kiến trúc của hệ thống.

### 10.1. Xử lý route không hợp lệ

Không nên âm thầm bỏ message khi route không được phép. Spring Cloud Function có cơ chế xử lý unroutable message; default handler có thể ghi log rồi cho luồng tiếp tục, dẫn đến message bị bỏ. Với luồng nghiệp vụ quan trọng:

- Ghi nhận route không hợp lệ bằng metric và audit log.
- Đưa message vào quarantine/DLQ theo policy.
- Không retry vô hạn một route key không tồn tại.
- Không tự tạo function hoặc destination mới để “thử” xử lý.
- Trả lỗi phù hợp ở API ingress nếu route do request trực tiếp chọn.

## 11. Không parse SpEL từ dữ liệu bên ngoài

SpEL hỗ trợ truy cập property, gọi method, tạo object và tham chiếu bean trong các context phù hợp. Nếu ứng dụng gọi parser trực tiếp trên một chuỗi do client cung cấp, người gửi có thể điều khiển cách biểu thức được đánh giá.

Mẫu không an toàn:

~~~java
String expressionText = request.expression();
Expression expression = parser.parseExpression(expressionText);
Object result = expression.getValue(evaluationContext);
~~~

Vấn đề không chỉ nằm ở cú pháp. Expression có thể truy cập các object được expose qua root object, property accessor, method resolver, variable hoặc function. Một getter trông như truy cập property cũng có thể có side effect.

Không giải quyết bằng cách chỉ lọc một vài ký tự nguy hiểm. Ngôn ngữ biểu thức có cú pháp phong phú; denylist thường bỏ sót cách biểu diễn khác. Cũng không xem việc chuyển sang `SimpleEvaluationContext` là cách cho phép người dùng gửi expression tùy ý.

### 11.1. Dùng dữ liệu có kiểu thay cho expression

Thay vì nhận:

~~~json
{
  "routingExpression": "expression supplied by caller"
}
~~~

hãy nhận một route key:

~~~json
{
  "route": "orders"
}
~~~

Sau đó map route key sang binding/function cố định. Nếu nghiệp vụ thật sự cần rule do quản trị viên định nghĩa, hãy thiết kế một DSL giới hạn với grammar, kiểu dữ liệu, toán tử và quyền rõ ràng; không cho phép administrator nhập SpEL tùy ý nếu không có quy trình review và kiểm soát truy cập chặt chẽ.

### 11.2. Expression trong application property

Expression được đặt trong application property thường do developer hoặc operator quản lý và không trực tiếp đến từ người dùng cuối. Tuy nhiên, nguồn cấu hình có thể bị điều khiển nếu:

- Config Server hoặc kho cấu hình bị truy cập trái phép.
- Pipeline deployment cho phép người không có quyền sửa environment variable.
- Endpoint quản trị hoặc endpoint refresh cấu hình được expose không đúng cách.
- Secret/configuration management không phân quyền theo môi trường.

Hãy bảo vệ nguồn cấu hình và endpoint quản trị bằng authentication, authorization, network restriction và audit. Không cho người dùng cuối thay đổi property routing hoặc function definition.

## 12. Không tin header định tuyến từ broker bên ngoài

Một producer có thể tự gửi các header mang tên giống header framework. Nếu consumer nhận message từ topic mà nhiều producer có quyền ghi, header định tuyến phải được xem là dữ liệu không đáng tin cậy.

Các header cần chú ý:

| Header | Khả năng bị tác động |
|---|---|
| `spring.cloud.stream.sendto.destination` | Chọn output destination |
| `spring.cloud.function.definition` | Chọn function hoặc composition |
| `spring.cloud.function.routing-expression` | Chọn function qua SpEL |
| Header route/tenant do ứng dụng tự định nghĩa | Có thể tác động mapping nội bộ nếu code tin tưởng trực tiếp |

Biện pháp:

1. Không truyền nguyên vẹn các header routing bên ngoài qua ranh giới trust.
2. Xóa hoặc ghi đè header nhạy cảm tại ingress adapter nếu không được phép sử dụng.
3. Dùng header nghiệp vụ riêng có schema rõ ràng, rồi map qua allowlist.
4. Kiểm tra producer identity và quyền publish ở broker.
5. Không để payload quyết định trực tiếp destination hoặc function name.

Ví dụ loại bỏ header định tuyến trước khi chuyển message vào logic nội bộ:

~~~java
Message<OrderEvent> trustedMessage =
        MessageBuilder.fromMessage(incoming)
                .removeHeader("spring.cloud.stream.sendto.destination")
                .removeHeader("spring.cloud.function.definition")
                .removeHeader("spring.cloud.function.routing-expression")
                .build();
~~~

Tên API và khả năng sửa header phụ thuộc kiểu Message và phiên bản Spring Messaging. Trong một pipeline thực tế, hãy tạo message mới từ payload cùng danh sách header được phép thay vì sao chép toàn bộ header bên ngoài.

## 13. Phân quyền ở broker

Allowlist và mapping trong ứng dụng bảo vệ logic route. Broker vẫn cần enforce quyền ở tầng tài nguyên.

Ví dụ:

| Broker | Cần giới hạn |
|---|---|
| Kafka | ACL theo cluster/topic và quyền create/describe/write phù hợp |
| RabbitMQ | User theo vhost, configure/write/read permission trên exchange/queue |
| Pulsar | Tenant/namespace/topic authorization và quyền produce/consume |

Ứng dụng chỉ cần publish tới hai topic cố định không nên dùng credential có quyền tạo và ghi mọi topic/queue trong cluster. Nếu binder cần provision destination khi khởi động, cấp quyền provision đúng phạm vi và tách khỏi quyền runtime nếu kiến trúc hỗ trợ.

Với multi-tenant, cân nhắc:

- Credential hoặc service identity riêng theo tenant/namespace khi cần cách ly mạnh.
- Vhost RabbitMQ hoặc namespace Pulsar riêng.
- ACL Kafka giới hạn theo topic và principal.
- Không dùng một credential quản trị broker trong ứng dụng web-facing.
- Rotate credential và lưu trong secret manager.

Broker ACL là lớp bảo vệ cuối cùng khi ứng dụng bị lỗi hoặc một đường code bỏ qua mapping. Không dùng ACL rộng rồi kỳ vọng mọi controller luôn validate đúng.

## 14. Kiểm soát resource exhaustion

Dynamic destination có thể làm tăng số binding, topic, queue và metadata. Một người gửi nhiều tên khác nhau có thể tạo ra lượng lớn destination nếu binder và broker cho phép.

Các biện pháp:

- Cấu hình allowlist chính xác.
- Giới hạn độ dài và định dạng route key trước khi tra cứu.
- Không cho phép wildcard hoặc pattern nếu không có nhu cầu đã review.
- Rate limit theo principal và tenant.
- Giới hạn số destination được đăng ký cho mỗi tenant.
- Giới hạn concurrency và kích thước message.
- Đặt broker quota, topic/queue policy và quyền create.
- Theo dõi số binding, số destination và tốc độ tạo mới.
- Có quy trình dọn dẹp tài nguyên do ứng dụng quản lý, có kiểm tra owner.

Không xóa topic hoặc queue chỉ vì binding cache đã eviction. Vòng đời binding trong ứng dụng và vòng đời tài nguyên broker là hai khái niệm khác nhau.

## 15. Audit và observability cho routing

Khi ứng dụng định tuyến message, nên ghi lại quyết định routing bằng structured log hoặc audit event:

- Principal/service identity đã xác thực.
- Tenant đã được xác minh.
- Route key nhận từ request/message.
- Destination hoặc binding đã được ánh xạ.
- Binder type do ứng dụng chọn.
- Function name được gọi.
- Event ID/correlation ID.
- Kết quả authorization và publish attempt.

Không ghi password, token, payload nhạy cảm hoặc toàn bộ biểu thức SpEL vào log. Nếu cần điều tra một biểu thức cấu hình, ghi version/config source hoặc mã định danh cấu hình đã review thay vì log dữ liệu bí mật.

Metrics nên có cardinality hữu hạn:

- Số route bị từ chối theo route key hợp lệ/nhóm lỗi.
- Số publish theo binding đã đăng ký.
- Số dynamic binding hiện có.
- Số lần destination bị từ chối bởi allowlist.
- Số function route không hợp lệ.
- Số lỗi broker authorization/provisioning.

Không gắn user ID, tenant ID tự do hoặc destination tùy ý vào metric tag nếu số lượng có thể tăng không giới hạn. Dùng log/trace cho định danh cụ thể.

## 16. Ví dụ thiết kế ingress an toàn

Ví dụ dưới đây nhận một route key nghiệp vụ, kiểm tra quyền rồi gửi qua output binding đã khai báo:

~~~java
@RestController
@RequestMapping("/events")
class SecureEventController {

    private static final Map<String, String> OUTPUT_BINDINGS = Map.of(
            "orders", "orders-out-0",
            "billing", "billing-out-0");

    private final StreamBridge streamBridge;
    private final RouteAuthorizer routeAuthorizer;

    SecureEventController(
            StreamBridge streamBridge,
            RouteAuthorizer routeAuthorizer) {
        this.streamBridge = streamBridge;
        this.routeAuthorizer = routeAuthorizer;
    }

    @PostMapping("/{route}")
    ResponseEntity<Void> publish(
            @PathVariable String route,
            Principal principal,
            @RequestBody EventEnvelope event) {

        String binding = OUTPUT_BINDINGS.get(route);
        if (binding == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unsupported route");
        }

        routeAuthorizer.requirePermission(principal, route, event);

        boolean accepted = streamBridge.send(binding, event);
        if (!accepted) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "Publish was not accepted");
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

Đây là ví dụ cấu trúc. `RouteAuthorizer` phải xác minh principal và quyền tenant theo dữ liệu đã xác thực. Nếu ứng dụng có nhiều binder, binding đã khai báo sẵn sẽ quyết định binder; không để client chọn binder type.

Giá trị trả về boolean của `StreamBridge.send` cho biết thao tác gửi được chấp nhận ở channel/binding theo API; không nên diễn giải nó thành bằng chứng consumer đích đã xử lý message hoặc side effect nghiệp vụ đã hoàn tất. Nếu API cần xác nhận giao nhận bền vững, hãy thiết kế acknowledgment phù hợp với binder và broker.

## 17. Kiểm thử bảo mật

Không chỉ kiểm tra trường hợp route hợp lệ. Cần kiểm thử cả những đầu vào cố gắng vượt giới hạn.

### 17.1. Kiểm thử dynamic destination

- Destination nằm trong allowlist được bind thành công.
- Destination ngoài allowlist bị từ chối.
- Tên rỗng, null, quá dài hoặc sai định dạng bị từ chối.
- Chuỗi có dấu phân cách, wildcard hoặc ký tự điều khiển không được biến thành route mới.
- Gửi nhiều tên khác nhau không làm tăng số binding ngoài dự kiến.
- Cache eviction không xóa hoặc tạo lại tài nguyên broker ngoài policy.

### 17.2. Kiểm thử function routing

- Header `spring.cloud.function.definition` không thể chọn function ngoài map.
- Header `spring.cloud.function.routing-expression` không được dùng để thực thi expression do client gửi.
- Function composition không thể gọi function nội bộ không được phép.
- Event type không biết bị reject hoặc quarantine.
- MessageRoutingCallback áp dụng mapping cố định.
- Reactive function không bị giả định có per-message routing header.

### 17.3. Kiểm thử tenant isolation

- Tenant A không thể publish vào binding của tenant B.
- Tenant ID trong payload không ghi đè tenant đã xác thực.
- Route hợp lệ nhưng principal không có quyền vẫn bị từ chối.
- Broker ACL từ chối publish ngoài phạm vi credential.
- Log/audit thể hiện principal và route đã được quyết định.

### 17.4. Kiểm thử cấu hình và vận hành

- `dynamic-destinations` được đặt tường minh trong profile production.
- Cache size phù hợp với số destination đã duyệt.
- Actuator/config endpoint không cho người dùng không có quyền thay đổi property routing.
- Credential của binder không có quyền quản trị broker nếu không cần.
- Alert phát hiện số destination/binding tăng bất thường.
- Message có header routing độc hại không làm thay đổi route.

## 18. Những lỗi thường gặp

1. **Để trống dynamic-destinations trong production**: mặc định cho phép mọi tên được bind động. Hãy cấu hình allowlist rõ ràng.
2. **Dùng request destination trực tiếp trong StreamBridge**: người gọi có thể chọn tài nguyên ngoài dự kiến. Hãy map route key sang binding cố định.
3. **Coi cache size là giới hạn bảo mật**: cache eviction không ngăn tạo tài nguyên broker mới. Hãy dùng allowlist, quota và ACL.
4. **Dùng regex thay allowlist**: một tên đúng pattern vẫn có thể là destination không được cấp quyền. Hãy dùng tập tên chính xác hoặc registry đã kiểm soát.
5. **Coi destination hợp lệ là người gọi có quyền**: allowlist là policy cấp ứng dụng, không phải authorization theo principal. Hãy kiểm tra quyền riêng.
6. **Tin tenantId trong payload**: client có thể tự khai tenant khác. Hãy lấy tenant từ identity đã xác thực.
7. **Cho client chọn binder type**: route có thể đi sang cluster khác. Hãy map binding và binder ở phía server.
8. **Chuyển nguyên header từ bên ngoài**: header routing có thể ảnh hưởng destination hoặc function. Hãy loại bỏ hoặc ghi đè header nhạy cảm.
9. **Cho client gửi function definition**: có thể chọn function hoặc composition ngoài luồng công khai. Hãy dùng callback và map hữu hạn.
10. **Đánh giá SpEL từ request**: expression có thể truy cập khả năng của context. Hãy dùng route key có kiểu và map cố định.
11. **Tin SimpleEvaluationContext là sandbox tuyệt đối**: đây chỉ là context giới hạn, không phải bảo đảm an toàn chung. Tránh expression không đáng tin cậy.
12. **Để application property bị sửa bởi người không có quyền**: property expression dùng evaluation context mạnh hơn. Hãy bảo vệ config và management endpoint.
13. **Im lặng bỏ route không hợp lệ**: message có thể mất mà không có audit. Hãy reject, quarantine hoặc xử lý lỗi rõ ràng.
14. **Cấp broker credential quá rộng**: lỗi route có thể ghi vào topic/queue ngoài ý muốn. Hãy dùng least privilege.
15. **Không kiểm thử resource exhaustion**: tên destination đa dạng có thể tạo nhiều binding và broker resource. Hãy rate limit, quota và alert.

## 19. Quy trình thiết kế routing an toàn

Khi xây dựng routing trong Spring Cloud Stream:

1. Liệt kê destination và function mà ứng dụng thực sự cần.
2. Ưu tiên output binding khai báo sẵn nếu tập destination hữu hạn.
3. Nếu cần dynamic destination, đặt `spring.cloud.stream.dynamic-destinations` thành allowlist.
4. Đặt cache size theo số binding hợp lệ và theo dõi eviction.
5. Nhận route key nghiệp vụ thay vì tên destination hoặc expression.
6. Ánh xạ route key sang binding, destination và binder bằng cấu hình/mã nguồn tin cậy.
7. Xác thực principal và tenant trước khi gửi.
8. Kiểm soát các header `sendto.destination`, `function.definition` và `function.routing-expression`.
9. Dùng MessageRoutingCallback nếu cần function routing theo message.
10. Không parse SpEL do người dùng hoặc hệ thống bên ngoài cung cấp.
11. Bảo vệ application properties, Config Server và management endpoints.
12. Giới hạn broker ACL, quyền provision và quota.
13. Ghi audit route, principal, binder và kết quả.
14. Kiểm thử route bypass, tenant isolation, expression injection và resource exhaustion.

## Kết luận

Dynamic destination và routing expression là các capability mạnh của Spring Cloud Stream, nhưng chúng mở rộng phạm vi ảnh hưởng của dữ liệu đầu vào. `StreamBridge.send` và header `spring.cloud.stream.sendto.destination` có thể làm framework resolve hoặc tạo output binding động. Header `spring.cloud.function.definition` và `spring.cloud.function.routing-expression` có thể tác động function được gọi; expression SpEL từ message header và application property được đánh giá trong các context khác nhau.

Hãy dùng destination allowlist, binding tĩnh khi có thể, route key có kiểu và mapping do server quản lý. Kiểm tra authorization theo principal/tenant; không tin header, payload hoặc expression từ bên ngoài. `dynamic-destination-cache-size` chỉ kiểm soát cache binding, không thay thế allowlist hoặc quota broker. Kết hợp broker ACL quyền tối thiểu, audit, rate limit và kiểm thử bảo mật để một yêu cầu định tuyến không thể mở rộng quyền truy cập hoặc tạo tài nguyên ngoài dự kiến.

## Tài liệu tham khảo

- [Spring Cloud Stream — StreamBridge and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Service Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-service-properties.html)
- [Spring Cloud Stream — Event Routing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)
- [Spring Cloud Function — Programming Model and Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Framework — SpEL Security Considerations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
