# Chọn scope theo vòng đời dữ liệu và cách sử dụng

Trong Spring, **bean scope** quyết định container tạo và cung cấp một instance theo phạm vi nào. Một bean có thể được dùng chung trong toàn bộ ứng dụng, được tạo mới theo mỗi lần yêu cầu, hoặc gắn với vòng đời của một HTTP request, một HTTP session hay một WebSocket session.

Chọn scope là một quyết định về **vòng đời dữ liệu và cách sử dụng đối tượng**. Nếu một service không giữ trạng thái riêng cho từng người dùng, scope mặc định `singleton` thường phù hợp. Nếu một đối tượng chứa dữ liệu chỉ có ý nghĩa trong một request, `request` có thể phù hợp. Nếu dữ liệu cần tồn tại qua nhiều request trong cùng phiên người dùng, có thể cân nhắc `session`. Với đối tượng cần một instance mới theo từng lần yêu cầu từ container, có thể dùng `prototype`.

Không nên chọn scope chỉ vì tên annotation nghe có vẻ hợp lý. Hãy xác định dữ liệu tồn tại bao lâu, ai được chia sẻ nó, những luồng nào có thể truy cập đồng thời và ai chịu trách nhiệm dọn dẹp tài nguyên.

## 1. Bean scope giải quyết bài toán gì?

Một ứng dụng Spring Boot có thể có nhiều bean cộng tác:

~~~text
HTTP request
     |
     v
OrderController
     |
     v
OrderService
     |
     +------> OrderRepository
     |
     +------> PricingService
~~~

Với scope mặc định `singleton`, mỗi bean definition thường được container tạo một instance và tái sử dụng trong suốt vòng đời của ApplicationContext. Nhiều request có thể cùng đi qua một `OrderService`, một `OrderRepository` và một `PricingService`.

Điều đó rất hiệu quả nếu các bean này chủ yếu chứa logic không trạng thái hoặc cấu hình bất biến. Nhưng nếu `OrderService` lưu dữ liệu của request hiện tại vào field, các request có thể ghi đè dữ liệu của nhau.

~~~java
@Service
public class UnsafeOrderService {
    private Long currentCustomerId;

    public void placeOrder(Long customerId) {
        this.currentCustomerId = customerId;
        // Xử lý tiếp dựa trên currentCustomerId...
    }
}
~~~

Nếu hai request chạy đồng thời trên cùng một singleton, request thứ hai có thể thay đổi `currentCustomerId` trong khi request thứ nhất chưa xử lý xong. Đây là lỗi chia sẻ trạng thái, không phải lỗi do Spring tiêm dependency sai.

Bean scope cho phép chọn vòng đời instance phù hợp hơn với nhu cầu. Tuy vậy, scope không tự giải quyết mọi vấn đề concurrency hoặc bảo mật; nó chỉ xác định phạm vi instance được chia sẻ.

### Scope khác với phạm vi component scan

Hai khái niệm thường bị nhầm:

| Khái niệm | Câu hỏi |
|---|---|
| Component scan | Spring tìm class ứng viên trong package nào để đăng ký bean? |
| Bean scope | Bean instance được tạo và tái sử dụng trong phạm vi vòng đời nào? |

Một class có thể được phát hiện qua `@ComponentScan` nhưng có scope `singleton`, `prototype` hoặc web scope. Ngược lại, đặt `@Scope("request")` lên class không làm nó tự được đăng ký nếu không có component scan, `@Bean` hoặc cơ chế đăng ký khác.

## 2. Các scope phổ biến của Spring

Spring Framework cung cấp những scope cơ bản sau. Web scope yêu cầu môi trường web phù hợp; không phải scope nào cũng có thể sử dụng trong mọi loại ApplicationContext.

| Scope | Vòng đời instance | Trường hợp thường dùng |
|---|---|---|
| `singleton` | Một instance cho mỗi bean definition trong một Spring container | Service stateless, repository, cấu hình, client dùng chung |
| `prototype` | Container tạo instance mới mỗi khi bean được yêu cầu theo cơ chế lookup tương ứng | Đối tượng có trạng thái riêng cho mỗi lần sử dụng |
| `request` | Một instance trong suốt một HTTP request | Metadata hoặc dữ liệu chỉ thuộc một request |
| `session` | Một instance trong suốt một HTTP session | Giỏ hàng hoặc trạng thái workflow kéo dài qua nhiều request |
| `application` | Một instance gắn với ServletContext của web application | Trạng thái dùng chung ở cấp ứng dụng servlet |
| `websocket` | Một instance cho mỗi WebSocket session | Trạng thái riêng của một kết nối WebSocket |

`singleton` là scope mặc định của bean Spring. Các scope `request`, `session`, `application` và `websocket` thường chỉ có ý nghĩa khi ứng dụng có web context và cơ chế scope tương ứng được đăng ký.

Một điểm quan trọng: singleton không có nghĩa “một instance duy nhất cho toàn JVM”. Nó có nghĩa một instance cho **mỗi bean definition trong một container**. Hai ApplicationContext riêng biệt có thể có hai singleton khác nhau; cùng một class cũng có thể được đăng ký thành hai bean definition và tạo hai instance.

## 3. Singleton: dùng chung một instance trong container

### 3.1. Cách hoạt động

Nếu không chỉ định scope, bean thường có scope singleton:

~~~java
@Service
public class TaxCalculator {
    public long calculate(long amount) {
        return amount / 10;
    }
}
~~~

Có thể khai báo rõ:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
public class DefaultPricingPolicy {
    // ...
}
~~~

`ConfigurableBeanFactory.SCOPE_SINGLETON` có giá trị là tên scope `singleton`. Tuy nhiên, với bean thông thường, không cần viết annotation chỉ để nhắc lại mặc định.

Spring tạo và giữ instance singleton trong container; khi bean khác inject nó, container cung cấp cùng instance tương ứng. Việc tạo thường diễn ra lúc ApplicationContext khởi tạo đối với singleton eager-init, nhưng có thể trì hoãn nếu bean được cấu hình lazy.

### 3.2. Khi nào singleton phù hợp?

Singleton phù hợp với những thành phần:

- Chứa logic nghiệp vụ nhưng không giữ trạng thái mutable theo từng request.
- Dùng chung cấu hình, serializer, mapper hoặc client có thể tái sử dụng an toàn.
- Là repository/service phối hợp với tài nguyên dùng chung.
- Có thể được nhiều thread gọi đồng thời mà vẫn đảm bảo tính đúng đắn.

Ví dụ, service stateless nhận dữ liệu qua tham số:

~~~java
@Service
public class DiscountService {
    public long calculate(long unitPrice, int quantity, int percent) {
        if (quantity < 0 || unitPrice < 0) {
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        }
        return unitPrice * quantity * (100 - percent) / 100;
    }
}
~~~

Mỗi lần gọi có dữ liệu riêng trong biến cục bộ. Không cần tạo một service mới cho từng request.

### 3.3. Singleton không tự động thread-safe

Singleton thường được chia sẻ giữa nhiều request và thread. Nếu bean chứa field mutable, cần kiểm soát truy cập đồng thời.

Không an toàn:

~~~java
@Service
public class SequenceService {
    private long sequence = 0;

    public long next() {
        return ++sequence;
    }
}
~~~

Phép tăng trên field không tự động atomic. Nếu nhiều thread gọi cùng lúc, có thể mất cập nhật.

Nếu thực sự cần bộ đếm chia sẻ trong một JVM, có thể dùng kiểu concurrency phù hợp:

~~~java
@Service
public class SequenceService {
    private final AtomicLong sequence = new AtomicLong();

    public long next() {
        return sequence.incrementAndGet();
    }
}
~~~

`AtomicLong` bảo vệ phép cập nhật nguyên tử trong phạm vi tiến trình/JVM này. Nếu ứng dụng chạy nhiều instance, mỗi instance vẫn có bộ đếm riêng; khi cần số thứ tự toàn hệ thống, phải dùng cơ chế chia sẻ như database sequence hoặc dịch vụ chuyên biệt.

Đừng chọn `prototype` chỉ để né thread safety nếu dữ liệu thực tế cần chia sẻ. Hãy xác định rõ ai sở hữu trạng thái và cơ chế đồng bộ phù hợp.

## 4. Prototype: tạo instance mới khi được yêu cầu

### 4.1. Cách khai báo

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    private String title;

    public void setTitle(String title) {
        this.title = title;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Mỗi lần yêu cầu bean prototype từ container, Spring tạo instance mới và thực hiện dependency injection cùng các bước khởi tạo cần thiết.

Ví dụ, nếu lấy qua ApplicationContext:

~~~java
ReportDraft first = context.getBean(ReportDraft.class);
ReportDraft second = context.getBean(ReportDraft.class);

System.out.println(first == second); // false
~~~

Hai lần lookup cho hai instance khác nhau (giả sử không có cơ chế khác thay đổi việc cung cấp bean).

### 4.2. Prototype không đồng nghĩa mỗi lần gọi service có instance mới

Một tình huống dễ gây hiểu nhầm:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    // ...
}

@Service
public class ReportService {
    private final ReportDraft draft;

    public ReportService(ReportDraft draft) {
        this.draft = draft;
    }
}
~~~

`ReportService` mặc định là singleton. Khi Spring tạo singleton này, nó resolve constructor và cung cấp một instance `ReportDraft` tại thời điểm đó. Service giữ instance trong field; các lần gọi `ReportService` tiếp theo vẫn dùng cùng `draft`.

Sơ đồ:

~~~text
ApplicationContext
       |
       | tạo singleton một lần
       v
ReportService
       |
       +---- ReportDraft instance A
                    |
          các lần gọi service
          vẫn tham chiếu A
~~~

Nếu cần một `ReportDraft` mới mỗi lần tạo báo cáo, cần yêu cầu instance ở thời điểm sử dụng:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<ReportDraft> draftProvider;

    public ReportService(ObjectProvider<ReportDraft> draftProvider) {
        this.draftProvider = draftProvider;
    }

    public ReportDraft newDraft() {
        return draftProvider.getObject();
    }
}
~~~

`ObjectProvider<T>` là abstraction của Spring cho phép lấy bean khi cần. Mỗi lần gọi `getObject()` với bean prototype, container cung cấp instance mới.

Có thể dùng factory Java thay cho ObjectProvider nếu object chỉ là dữ liệu thông thường và không cần Spring quản lý việc tạo hoặc scope. Scope prototype hữu ích khi muốn container thực hiện khởi tạo, inject dependency hoặc áp dụng các cơ chế Spring cho từng instance.

### 4.3. Container không tự quản lý đầy đủ việc hủy prototype

Với singleton, container có thể gọi callback hủy khi context đóng. Với prototype, Spring tạo, cấu hình và khởi tạo instance rồi giao cho client; nó không theo dõi toàn bộ vòng đời sử dụng của từng instance để tự gọi destruction callback khi đối tượng không còn được tham chiếu.

Nếu prototype giữ tài nguyên như file handle, socket hoặc stream, phía nhận instance phải chịu trách nhiệm đóng tài nguyên theo thiết kế phù hợp. Đây là một lý do không nên dùng prototype cho mọi object có trạng thái.

## 5. Request scope: một instance trong một HTTP request

### 5.1. Khi nào dùng request scope?

Một HTTP request có thể đi qua nhiều thành phần:

~~~text
HTTP request A
      |
      v
Controller
      |
      v
Service
      |
      v
Audit component
~~~

Nhiều thành phần có thể cần thông tin chung chỉ có ý nghĩa trong request hiện tại, chẳng hạn correlation ID, metadata đã chuẩn hóa hoặc một đối tượng context tạm thời.

Request-scoped bean cung cấp một instance trong suốt request. Request tiếp theo sẽ có instance khác.

### 5.2. Khai báo bằng @RequestScope

~~~java
package com.example.store.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {
    private final String requestId = UUID.randomUUID().toString();

    public String requestId() {
        return requestId;
    }
}
~~~

`@RequestScope` là annotation tiện lợi cho scope `request`. Trong cách sử dụng thông thường, nó dùng scoped proxy để có thể inject bean request-scoped vào bean có vòng đời dài hơn như singleton.

Một singleton service có thể nhận dependency đó qua constructor:

~~~java
@Service
public class AuditService {
    private final RequestMetadata metadata;

    public AuditService(RequestMetadata metadata) {
        this.metadata = metadata;
    }

    public void record(String action) {
        System.out.println(
                metadata.requestId() + " - " + action
        );
    }
}
~~~

`AuditService` là singleton, nhưng trường `metadata` được cung cấp thông qua proxy. Khi gọi `metadata.requestId()` trong một HTTP request đang hoạt động, proxy chuyển lời gọi tới instance phù hợp với request hiện tại.

### 5.3. Request scope cần web request đang hoạt động

Request scope phụ thuộc vào ngữ cảnh HTTP request được Spring quản lý. Nếu một tác vụ chạy ở background thread, scheduler hoặc message listener mà không có request context tương ứng, truy cập request-scoped bean có thể thất bại.

Không nên lưu request context rồi sử dụng tùy tiện sau khi request đã kết thúc. Nếu cần chuyển dữ liệu sang tác vụ nền, hãy truyền một command/event chứa những giá trị cần thiết:

~~~java
public record ProcessOrderCommand(
        Long orderId,
        String requestedBy,
        String correlationId
) {}
~~~

Tác vụ nền nhận dữ liệu rõ ràng qua message hoặc tham số. Cách này tránh phụ thuộc vào một request scope không còn tồn tại.

Request scope phù hợp khi nhiều thành phần trong cùng request cần dùng chung một trạng thái tạm thời. Nếu dữ liệu chỉ được một phương thức sử dụng, biến cục bộ hoặc tham số thường đơn giản hơn.

## 6. Session scope: một instance trong suốt HTTP session

### 6.1. Session scope khác request scope

Một người dùng có thể gửi nhiều request trong cùng HTTP session:

~~~text
HTTP session của người dùng A
   |
   +-- Request 1: xem sản phẩm
   |
   +-- Request 2: thêm sản phẩm vào giỏ
   |
   +-- Request 3: cập nhật số lượng
   |
   +-- Request 4: xem giỏ hàng
~~~

Request scope tạo instance mới cho từng request. Session scope giữ instance trong suốt session, nên dữ liệu có thể tồn tại qua nhiều request.

Một ví dụ điển hình là giỏ hàng chưa được lưu thành đơn hàng. Tuy nhiên, nếu giỏ hàng cần tồn tại sau khi người dùng đăng xuất, đăng nhập trên thiết bị khác hoặc cần đồng bộ nhiều thiết bị, database hoặc một kho lưu trữ chia sẻ có thể phù hợp hơn session scope.

### 6.2. Khai báo @SessionScope

~~~java
package com.example.store.cart;

import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class ShoppingCart {
    private final Map<Long, Integer> quantities = new HashMap<>();

    public synchronized void add(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        quantities.merge(productId, quantity, Integer::sum);
    }

    public synchronized Map<Long, Integer> snapshot() {
        return Map.copyOf(quantities);
    }

    public synchronized void clear() {
        quantities.clear();
    }
}
~~~

`@SessionScope` là annotation tiện lợi cho scope `session`. Một service singleton có thể inject `ShoppingCart` qua constructor:

~~~java
@Service
public class CartService {
    private final ShoppingCart cart;

    public CartService(ShoppingCart cart) {
        this.cart = cart;
    }

    public void add(Long productId, int quantity) {
        cart.add(productId, quantity);
    }

    public Map<Long, Integer> view() {
        return cart.snapshot();
    }
}
~~~

Scoped proxy đảm bảo service dùng instance gắn với session hiện tại khi phương thức được gọi trong request có session hợp lệ.

Ví dụ trên dùng `synchronized` để minh họa việc bảo vệ thao tác trên state mutable. Một HTTP session vẫn có thể nhận nhiều request đồng thời, ví dụ người dùng mở nhiều tab. Nếu có các thao tác đọc-sửa-ghi phức tạp, cần xác định tính nguyên tử và chiến lược đồng bộ rõ ràng; chỉ dùng session scope không tự bảo vệ dữ liệu khỏi race condition.

### 6.3. Session scope cần cân nhắc dữ liệu và hạ tầng

Session thường tồn tại lâu hơn request, vì vậy cần quan tâm:

- **Dung lượng:** không lưu object đồ sộ hoặc dữ liệu không cần thiết trong session.
- **Bảo mật:** không dùng session bean như kho lưu secret hoặc thông tin nhạy cảm tùy tiện.
- **Thời hạn:** session có thể hết hạn; dữ liệu trong đó không phải lưu trữ bền vững.
- **Nhiều instance ứng dụng:** nếu load balancer phân phối request tới nhiều server, session cần sticky session hoặc cơ chế lưu session chia sẻ phù hợp.
- **Serialization:** một số session store cần dữ liệu có thể serialize hoặc có quy tắc lưu trữ riêng.
- **Đồng thời:** nhiều request trong cùng session có thể truy cập cùng trạng thái.

Nếu dữ liệu có giá trị nghiệp vụ lâu dài như đơn hàng, thanh toán hoặc quyền sở hữu tài sản, hãy lưu trong hệ thống dữ liệu bền vững và dùng session chỉ cho trạng thái tương tác phù hợp.

## 7. Application scope: gắn với ServletContext

`application` scope cung cấp một instance trong phạm vi `ServletContext` của web application. Nó có thể được dùng để chia sẻ một đối tượng giữa các request trong cùng servlet application.

~~~java
@Component
@ApplicationScope
public class ApplicationBanner {
    private final String message = "Store is running";

    public String message() {
        return message;
    }
}
~~~

`@ApplicationScope` là annotation tiện lợi của Spring cho web application scope.

Cần phân biệt application scope với singleton:

- `singleton` gắn với một bean definition trong một Spring container.
- `application` gắn với ServletContext của web application.

Trong ứng dụng đơn giản chỉ có một ApplicationContext gắn với một ServletContext, hai scope có thể cho kết quả sử dụng gần giống nhau. Nhưng trong ứng dụng có nhiều context hoặc cấu trúc servlet phức tạp, ranh giới của chúng có thể khác.

Application scope không phải một kho dữ liệu phân tán giữa nhiều JVM hoặc nhiều server. Nếu ứng dụng được triển khai thành ba instance, mỗi ServletContext có application-scoped object riêng. Dữ liệu dùng chung toàn cluster cần hệ thống chia sẻ như database, cache phân tán hoặc dịch vụ phù hợp.

Thông thường, service và cấu hình dùng chung trong một Spring Boot application nên dùng singleton. Chỉ chọn application scope khi thật sự cần ngữ nghĩa gắn với ServletContext.

## 8. WebSocket scope: một instance cho mỗi WebSocket session

WebSocket tạo kết nối hai chiều kéo dài giữa client và server. Một kết nối có thể nhận nhiều message trong suốt vòng đời session. Nếu cần trạng thái riêng cho từng kết nối, WebSocket scope có thể phù hợp.

Ví dụ khái niệm:

~~~java
@Component
@Scope(
        scopeName = "websocket",
        proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class WebSocketConversation {
    private String lastTopic;

    public void selectTopic(String topic) {
        this.lastTopic = topic;
    }

    public String lastTopic() {
        return lastTopic;
    }
}
~~~

Bean này được dự định dùng trong môi trường Spring WebSocket có đăng ký scope tương ứng, thường trong cấu hình messaging/WebSocket phù hợp. Nếu ứng dụng không bật hạ tầng WebSocket cần thiết, scope `websocket` có thể không được đăng ký và việc tạo bean sẽ thất bại.

WebSocket scope khác HTTP session scope: một người dùng có thể có nhiều WebSocket session, và mỗi kết nối có thể cần trạng thái riêng. Nếu ứng dụng cần chia sẻ dữ liệu giữa các kết nối hoặc nhiều server, phải dùng cơ chế lưu trữ/chia sẻ riêng.

## 9. Chọn scope theo vòng đời dữ liệu

Thay vì bắt đầu từ annotation, hãy bắt đầu bằng câu hỏi: **dữ liệu mà bean giữ phải tồn tại đến khi nào và được chia sẻ với ai?**

~~~text
Dữ liệu chỉ phục vụ một phép tính?
       |
       +-- Có --> Biến cục bộ / object Java thông thường
       |
       +-- Không
            |
            v
Dữ liệu có dùng chung an toàn trong app?
       |
       +-- Có --> Singleton
       |
       +-- Không
            |
            v
Cần instance mới mỗi lần container cấp?
       |
       +-- Có --> Prototype hoặc Factory
       |
       +-- Không
            |
            v
Dữ liệu gắn với ngữ cảnh web?
       |
       +-- Một HTTP request --> Request
       |
       +-- Một HTTP session --> Session
       |
       +-- ServletContext --> Application
       |
       +-- Một WebSocket session --> WebSocket
~~~

Đây là sơ đồ định hướng. Trong nhiều trường hợp, dữ liệu theo request nên được truyền qua tham số thay vì tạo request-scoped bean. Tương tự, prototype không phải giải pháp mặc định cho mọi object cần instance mới; factory Java thuần có thể đơn giản hơn.

### Bảng quyết định thực tế

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Service tính toán không lưu trạng thái request | Singleton | Có thể dùng chung an toàn |
| Repository hoặc client được cấu hình một lần và dùng đồng thời an toàn | Singleton | Tái sử dụng tài nguyên |
| Một đối tượng có state riêng cho mỗi lần tạo báo cáo | Prototype hoặc factory | Instance mới theo lần yêu cầu |
| Correlation metadata dùng trong một HTTP request | Request | Hết request là hết dữ liệu |
| Giỏ hàng tạm tồn tại qua nhiều request của cùng session | Session | Vòng đời trùng với phiên người dùng |
| Cấu hình hoặc object gắn với ServletContext | Application | Chia sẻ trong web application |
| Trạng thái riêng cho một kết nối WebSocket | WebSocket | Vòng đời theo kết nối |
| Dữ liệu đơn hàng cần tồn tại sau khi session hết hạn | Database | Cần tính bền vững, không phải bean scope |

## 10. Không dùng bean scope thay cho truyền dữ liệu qua tham số

Một lỗi thiết kế phổ biến là tạo request-scoped bean cho mọi dữ liệu request, dù dữ liệu chỉ cần ở một phương thức.

Ví dụ, thay vì:

~~~java
@Service
public class GreetingService {
    public String greet(String customerName) {
        return "Hello " + customerName;
    }
}
~~~

không cần tạo một bean request-scoped chỉ để giữ `customerName`. Tham số phương thức biểu đạt quan hệ rõ ràng hơn.

Nên phân biệt:

- **Dependency:** cộng tác viên ổn định mà class cần, như repository, gateway, policy.
- **Input data:** dữ liệu thay đổi theo lần gọi, như ID, quantity, command.
- **Stateful context:** trạng thái cần được chia sẻ giữa nhiều thành phần trong một phạm vi cụ thể, nếu thật sự có lý do.

Bean scope nên được dùng cho **vòng đời của đối tượng cộng tác**, không phải để biến mọi dữ liệu thành bean.

## 11. Scoped proxy: làm sao singleton sử dụng request/session bean?

Một service singleton được tạo lúc ApplicationContext khởi động, nhưng request/session bean chỉ có instance khi một request/session tương ứng đang hoạt động. Nếu inject trực tiếp target instance vào singleton, vòng đời không khớp.

Spring giải quyết bằng **scoped proxy**. Proxy có vòng đời dài hơn và được inject vào singleton; khi gọi phương thức, proxy tìm target bean thuộc scope hiện tại.

~~~text
ApplicationContext
      |
      v
Singleton AuditService
      |
      v
RequestMetadata proxy
      |
      +-- Request A --> RequestMetadata instance A
      |
      +-- Request B --> RequestMetadata instance B
~~~

`@RequestScope` và `@SessionScope` thường cấu hình scoped proxy mặc định. Có thể viết rõ bằng `@Scope`:

~~~java
@Component
@Scope(
        value = WebApplicationContext.SCOPE_REQUEST,
        proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class RequestData {
    // ...
}
~~~

Cần import các kiểu từ `org.springframework.web.context` và `org.springframework.context.annotation` tương ứng.

Hai proxy mode thường gặp:

| Proxy mode | Ý nghĩa |
|---|---|
| `ScopedProxyMode.TARGET_CLASS` | Tạo proxy dựa trên class (thường dùng CGLIB) |
| `ScopedProxyMode.INTERFACES` | Tạo proxy dựa trên interface |

Nếu dùng proxy class, class/method final hoặc các hạn chế của cơ chế proxy có thể ảnh hưởng khả năng tạo proxy. Nếu dùng interface proxy, consumer cần làm việc qua interface phù hợp.

Scoped proxy không có nghĩa request-scoped bean trở thành singleton. Proxy là đối tượng được chia sẻ; **target thực sự vẫn thay đổi theo scope**.

### Dùng ObjectProvider thay cho proxy

Có thể inject `ObjectProvider<RequestData>` vào singleton rồi gọi `getObject()` bên trong request đang hoạt động. Cách này làm thời điểm lấy bean rõ ràng, nhưng vẫn yêu cầu scope đang tồn tại. Chọn proxy hay provider tùy API muốn thể hiện; đừng dùng cả hai chỉ để tăng độ phức tạp.

## 12. Vòng đời bean và destruction callback theo từng scope

Scope ảnh hưởng đến thời điểm tạo và hủy bean. Một số khác biệt quan trọng:

| Scope | Tạo instance | Kết thúc vòng đời | Ghi chú về cleanup |
|---|---|---|---|
| Singleton | Thường khi context khởi tạo hoặc lần đầu nếu lazy | Khi context đóng | Container gọi callback hủy được quản lý |
| Prototype | Mỗi lần container yêu cầu bean | Sau khi giao cho client, client quản lý tiếp | Spring không tự theo dõi và gọi destruction callback đầy đủ |
| Request | Khi request cần bean lần đầu | Khi request hoàn tất | Web scope có thể gọi callback hủy |
| Session | Khi session cần bean lần đầu | Khi session hết hạn hoặc bị hủy | Cần chú ý session storage và cleanup |
| Application | Khi ServletContext cần bean | Khi web application kết thúc | Phụ thuộc lifecycle ServletContext |
| WebSocket | Khi WebSocket session cần bean | Khi WebSocket session đóng | Phụ thuộc hạ tầng WebSocket scope |

Một singleton chứa resource nên có cách đóng an toàn khi context shutdown. Một prototype giữ resource cần cơ chế đóng từ phía sử dụng, vì container không quản lý trọn vẹn phần kết thúc. Request/session scope có cleanup gắn với lifecycle web, nhưng không nên giả định callback sẽ chạy trong mọi sự cố process bị kill.

## 13. Những lỗi thường gặp khi chọn scope

### Lỗi 1: Đổi service sang prototype để tránh trạng thái dùng chung

Nếu service chứa trạng thái theo request, đổi thành prototype có thể làm giảm một số chia sẻ instance trong vài cấu hình, nhưng nó không giải quyết nguyên nhân gốc nếu service vẫn được inject vào một singleton. Singleton consumer chỉ nhận một prototype lúc được tạo.

Giải pháp tốt hơn thường là bỏ trạng thái request khỏi field, truyền dữ liệu qua tham số hoặc đặt state vào một abstraction có scope đúng.

### Lỗi 2: Nghĩ request scope bảo vệ dữ liệu khỏi mọi truy cập đồng thời

Một request thường được xử lý trên một thread tại một thời điểm trong mô hình servlet thông thường, nhưng async processing và việc chia sẻ đối tượng sang tác vụ khác có thể làm ngữ cảnh phức tạp. Request scope không phải khóa đồng bộ và không nên được dùng như cơ chế concurrency control.

### Lỗi 3: Dùng session scope làm database

Session có thể hết hạn, bị xóa, hoặc mất khi cấu hình triển khai không có session persistence phù hợp. Đơn hàng, thanh toán, quyền sở hữu và dữ liệu cần kiểm toán phải có nơi lưu trữ bền vững.

### Lỗi 4: Inject prototype trực tiếp vào singleton rồi mong instance mới mỗi lần

Prototype được tạo khi singleton được lắp ghép, không tự đổi mỗi lần gọi phương thức. Dùng `ObjectProvider` hoặc factory khi thật sự cần instance mới.

### Lỗi 5: Dùng application scope để chia sẻ giữa nhiều server

Application scope chỉ gắn với ServletContext của một web application, không phải toàn cluster. Cần database, distributed cache hoặc một dịch vụ chia sẻ nếu nhiều instance phải nhìn cùng dữ liệu.

### Lỗi 6: Request/session bean được truy cập ngoài web context

Một scheduler hoặc message listener không có HTTP request/session tương ứng có thể không truy cập được bean web-scoped. Truyền dữ liệu cần thiết vào tác vụ thay vì dựa vào ngữ cảnh web đã kết thúc.

### Lỗi 7: Chọn scope mà không xét thread safety

Scope xác định phạm vi instance, không đảm bảo các thao tác trên state mutable là an toàn. Singleton, session và application đều có thể được nhiều luồng truy cập đồng thời.

## 14. Kiểm thử bean theo scope

Scope cũng ảnh hưởng cách viết test. Với singleton service, unit test có thể tạo service trực tiếp hoặc dùng Spring context. Với request/session scope, test cần tạo ngữ cảnh web tương ứng.

Ví dụ, một test Spring MVC với `MockMvc` có thể gửi hai request và xác nhận dữ liệu request-scoped không bị dùng chung giữa chúng. Đối với session scope, có thể gửi nhiều request với cùng session và xác nhận state được giữ; sau đó dùng session khác để xác nhận state tách biệt.

Sơ đồ kiểm thử mong muốn:

~~~text
Request A (session S1)
    -> Request bean A
    -> Session bean S1

Request B (session S1)
    -> Request bean B
    -> Session bean S1

Request C (session S2)
    -> Request bean C
    -> Session bean S2
~~~

Kết quả:

- Request bean A và B khác nhau vì thuộc hai request.
- Session bean của A và B giống nhau vì cùng session S1.
- Session bean của C khác vì thuộc session S2.

Đây là cách kiểm tra đúng semantics của scope, không chỉ kiểm tra class có annotation `@RequestScope` hoặc `@SessionScope`.

Với prototype, test có thể lấy bean nhiều lần qua provider và xác nhận các instance khác nhau. Cần nhớ prototype destruction không được container tự quản lý đầy đủ; nếu test tạo resource, phải tự cleanup để tránh rò rỉ.

## 15. Chọn scope theo tình huống thực tế

### Tình huống A: PricingService chỉ tính toán

`PricingService` nhận giá và số lượng, trả về tổng tiền, không giữ dữ liệu giữa các lần gọi. Singleton là lựa chọn phù hợp. Tạo một instance mới cho mỗi HTTP request không mang lại lợi ích rõ ràng.

### Tình huống B: RequestMetadata giữ correlation ID

Correlation ID được xác định cho mỗi HTTP request và nhiều thành phần trong cùng request cần đọc. Request scope có thể phù hợp. Nếu chỉ một service cần ID, truyền nó qua command hoặc context object có thể đơn giản hơn.

### Tình huống C: ShoppingCart giữ các sản phẩm đang chọn

Giỏ hàng cần tồn tại qua nhiều request của một session người dùng. Session scope có thể phù hợp cho ứng dụng đơn giản, nhưng cần đánh giá concurrency, timeout, dung lượng và việc đồng bộ nhiều thiết bị. Nếu giỏ hàng là dữ liệu quan trọng hoặc cần bền vững, nên lưu ở database/cache phù hợp.

### Tình huống D: ReportDraft cần trạng thái riêng cho mỗi lần export

Nếu mỗi lần tạo báo cáo cần một builder độc lập và builder có dependency cần Spring khởi tạo, prototype hoặc factory có thể phù hợp. Nếu chỉ là một object dữ liệu đơn giản, tạo bằng constructor Java thường dễ hơn.

### Tình huống E: ApplicationBanner dùng chung trong servlet app

Nếu banner là giá trị bất biến, singleton thường đã đủ. Application scope chỉ nên chọn khi muốn gắn rõ vòng đời với ServletContext hoặc có lý do liên quan cấu trúc web context.

### Tình huống F: ConversationState gắn với một WebSocket

Nếu mỗi kết nối cần trạng thái riêng và ứng dụng có WebSocket scope đã đăng ký, websocket scope là một lựa chọn. Nếu client có thể reconnect và cần phục hồi trạng thái, phải lưu dữ liệu ở nơi bền vững hoặc chia sẻ phù hợp.

## 16. Checklist tư duy trước khi chọn scope

Trước khi thêm `@Scope`, hãy trả lời những câu hỏi sau:

1. **Dữ liệu có thực sự là state của bean không?** Nếu chỉ là tham số đầu vào, dùng method argument hoặc command.
2. **Ai cần chia sẻ state?** Một phương thức, một request, một session, một servlet application hay một WebSocket session?
3. **State tồn tại bao lâu?** Trong một lần gọi, một request, nhiều request, hay toàn vòng đời ứng dụng?
4. **Có nhiều thread cùng truy cập không?** Nếu có, cần thiết kế concurrency riêng.
5. **Dữ liệu có cần tồn tại sau khi process restart hoặc session hết hạn không?** Nếu có, bean scope không phải persistence.
6. **Ai đóng tài nguyên?** Đặc biệt với prototype hoặc tài nguyên ngoài container.
7. **Bean được inject vào consumer scope nào?** Singleton nhận prototype trực tiếp có thể giữ instance lâu hơn dự kiến; web scope cần proxy/provider.
8. **Ứng dụng có đúng context để dùng scope đó không?** Request/session/websocket cần hạ tầng tương ứng.

## 17. Bài tập tự áp dụng

Giả sử xây dựng một ứng dụng Spring Boot cho nền tảng học trực tuyến:

- `CourseCatalogService` đọc danh sách khóa học.
- `LearningProgressService` cập nhật tiến độ.
- `CurrentRequestInfo` giữ correlation ID của HTTP request.
- `LearningSession` giữ lựa chọn bài học đang xem trong một phiên tương tác.
- `ReportBuilder` tạo một báo cáo độc lập cho mỗi lần export.

Hãy chọn scope hoặc cơ chế tạo object cho từng thành phần và giải thích:

| Thành phần | Câu hỏi cần suy nghĩ |
|---|---|
| CourseCatalogService | Có giữ state riêng theo người dùng hay chỉ xử lý logic và truy cập dữ liệu? |
| LearningProgressService | Tiến độ học cần được lưu ở bean hay database? |
| CurrentRequestInfo | Dữ liệu có chỉ tồn tại trong một HTTP request không? |
| LearningSession | “Session” ở đây là HTTP session, phiên học nghiệp vụ hay một kết nối WebSocket? |
| ReportBuilder | Có cần Spring quản lý instance mới mỗi lần export không, hay factory Java là đủ? |

Tên `LearningSession` không tự quyết định scope. Một “phiên học” nghiệp vụ có thể tồn tại nhiều ngày và cần lưu trong database, trong khi HTTP session có thể hết hạn sau một khoảng không hoạt động. Hãy chọn theo **ngữ nghĩa vòng đời thực tế**, không chọn chỉ dựa vào tên class.

## Kết luận

Chọn bean scope là chọn **phạm vi chia sẻ và vòng đời instance**. Singleton phù hợp với đa số service stateless và thành phần dùng chung an toàn; prototype dành cho trường hợp cần instance mới khi container cấp; request/session/application/websocket gắn đối tượng với những phạm vi web tương ứng.

Trước khi thay scope, hãy xác định dữ liệu tồn tại bao lâu, ai truy cập nó, có thể truy cập đồng thời hay không và ai chịu trách nhiệm cleanup. Đừng dùng scope để thay cho tham số phương thức, database hoặc cơ chế đồng bộ. Khi scope phản ánh đúng vòng đời dữ liệu, object graph Spring Boot sẽ dễ hiểu hơn, tránh rò rỉ trạng thái giữa người dùng và có hành vi nhất quán trong môi trường chạy thực tế.
