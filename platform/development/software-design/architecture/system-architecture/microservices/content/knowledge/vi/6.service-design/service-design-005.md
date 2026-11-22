# Thiết kế dịch vụ không giữ trạng thái phiên cục bộ khi cần nhân bản

> Chủ đề: **Software Architecture → System Architecture → Microservices**  
> Nhóm kiến thức: **Thiết kế dịch vụ**

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao một service được triển khai thành nhiều **instance/replica** phải tránh phụ thuộc vào session nằm duy nhất trong bộ nhớ của một instance.
- Phân biệt **trạng thái của một request**, **trạng thái phiên**, **trạng thái nghiệp vụ**, **cache**, **trạng thái tác vụ** và **kết nối sống lâu**.
- Thiết kế hai cách phổ biến: xác thực mỗi request bằng token có thể kiểm chứng hoặc dùng **session store chia sẻ**.
- Chỉ ra cách Spring Boot lưu hoặc không lưu HttpSession, tại sao singleton và static map dễ trở thành trạng thái ẩn, và cách chuyển dữ liệu cần thiết sang nguồn dùng chung.
- Đảm bảo thao tác cập nhật dữ liệu vẫn đúng khi request được xử lý bởi các replica khác nhau, xảy ra retry, timeout, restart hoặc rolling deployment.
- Đề xuất các phép thử và tín hiệu quan sát để xác minh một service thật sự có thể nhân bản an toàn.

## 1. Tình huống mở đầu: một service, ba bản chạy

Hệ thống bán hàng có một Cart Service. Ban đầu service chạy trên một JVM và lưu giỏ hàng vào một Map trong RAM. Khi lượng truy cập tăng, đội ngũ triển khai ba replica:

~~~text
                        +---------------------+
Web/Mobile ------------>| Gateway /           |
                        | Load Balancer       |
                        +---+--------+--------+
                            |        |        |
                            v        v        v
                         +-----+  +-----+  +-----+
                         |  A  |  |  B  |  |  C  |
                         +-----+  +-----+  +-----+
                            Cart Service replicas
~~~

Lần gọi đầu đến A, ứng dụng lưu giỏ hàng của user-7 vào RAM của A. Lần gọi tiếp theo đến B, dữ liệu đó không tồn tại. Khi A được restart, phần dữ liệu của A biến mất hoàn toàn. Người dùng có thể thấy giỏ hàng lúc có, lúc không, dù tất cả container đều đang chạy bình thường.

~~~java
// Phản mẫu minh họa: dữ liệu chỉ nằm trong một tiến trình.
@Service
public class LocalCartStore {
    private final Map<String, List<CartItem>> carts =
        new ConcurrentHashMap<>();

    public void add(String userId, CartItem item) {
        carts.computeIfAbsent(userId, key -> new ArrayList<>())
             .add(item);
    }
}
~~~

ConcurrentHashMap giúp xử lý một số truy cập đồng thời ở **một JVM**; nó không đồng bộ qua ba JVM và không tự giải quyết tính nguyên tử của List bên trong. Lỗi có thể xuất hiện ngay trong một instance nếu nhiều thread đồng thời chỉnh sửa danh sách.

**Yêu cầu thiết kế:** bất kỳ replica khỏe nào cũng có thể xác thực và xử lý request hợp lệ mà không cần biết request trước của người dùng đã đến instance nào. Dữ liệu bền vững hoặc cần chia sẻ phải có một nguồn phù hợp bên ngoài bộ nhớ riêng của replica.

### 1.1. Service khác instance

- **Service:** thành phần logic cung cấp một năng lực và contract, ví dụ Cart Service.
- **Instance/replica:** một bản chạy cụ thể của service, ví dụ container A, B hoặc C.
- **Load balancer:** chọn một instance có thể nhận request theo cấu hình.
- **Session affinity:** cố gắng gắn các request của cùng client vào một instance.
- **State sharing:** cho phép nhiều instance thấy và cập nhật trạng thái cần thiết theo quy tắc nhất quán.

Tăng số replica không tạo thêm service nghiệp vụ. Một service có thể có ba process chạy cùng mã và cùng contract, nhưng mỗi process có RAM, thread, kết nối và vòng đời riêng.

## 2. Hiểu đúng từ “stateless”

Trong bài này, **stateless ở tầng instance/request handling** nghĩa là:

> Instance không cần bộ nhớ riêng lưu tích lũy thông tin của những request trước từ cùng người dùng để hiểu, xác thực và thực hiện request hiện tại.

Điều đó **không có nghĩa ứng dụng không được lưu dữ liệu**. Một đơn hàng, giao dịch thanh toán, cart hoặc workflow vẫn là trạng thái nghiệp vụ quan trọng, cần được lưu trong database hay cơ chế bền vững theo quyền sở hữu của dịch vụ.

| Loại dữ liệu | Ví dụ | Nơi có thể giữ | Yêu cầu khi scale |
| --- | --- | --- | --- |
| Trạng thái request ngắn hạn | Biến local, DTO, validation result | Bộ nhớ instance trong thời gian request | Không có request sau nào được phép phụ thuộc vào bộ nhớ đó. |
| Identity/session | User ID, session ID, thông tin đăng nhập | Credential kiểm chứng được hoặc shared session store | Replica khác xác thực được cùng người dùng. |
| Trạng thái nghiệp vụ | Cart, order, payment, reservation | Database/kho dữ liệu thuộc owner | Tồn tại qua restart và có kiểm soát ghi đồng thời. |
| Cache tăng tốc | Dữ liệu catalog đọc nhiều | Local/distributed cache có TTL/invalidation | Mất cache không làm mất nguồn sự thật hoặc phá bất biến. |
| Trạng thái job | Job ID, bước thực hiện, tiến độ | Durable queue, database, object storage | Worker mới có thể tiếp tục hoặc xử lý lại an toàn. |
| Trạng thái kết nối | Socket, stream buffer, heartbeat | Bộ nhớ instance sở hữu kết nối | Có quy tắc reconnect/resume nếu yêu cầu. |

### 2.1. Stateless HTTP chưa chắc đồng nghĩa stateless application

HTTP gửi request độc lập, nhưng ứng dụng có thể gắn một cookie tới bản ghi HttpSession nằm trong RAM server. Chính lớp ứng dụng tạo phụ thuộc giữa các request. Một API gắn nhãn REST hoặc trả JSON vẫn có thể lưu currentUser, cart hoặc checkout process trong singleton.

Stateless ở đây là **thuộc tính thiết kế của service**, không phải một chứng chỉ tự có vì đã dùng HTTP, REST, Spring hay Kubernetes.

### 2.2. Công thức tư duy cho request

~~~text
Kết quả xử lý request
  =
Input + danh tính đã được xác minh
      + quyền sử dụng tài nguyên
      + trạng thái nghiệp vụ ở nguồn sở hữu
      + quy tắc nghiệp vụ
      + các dependency rõ ràng
~~~

Không có thành phần bắt buộc là “RAM của instance xử lý request lần trước”.

### 2.3. Stateless không ngăn lỗi cập nhật đồng thời

Nếu A và B cùng đọc một cart và cập nhật, database cần bảo vệ transaction, version hoặc quy tắc ghi. Stateless chỉ giúp các replica không giữ session cục bộ; nó không tự ngăn lost update, race condition hay duplicate payment.

## 3. Những nơi trạng thái phiên cục bộ thường bị giấu

### 3.1. HttpSession chỉ tồn tại trong một container

~~~java
@GetMapping("/account")
public AccountView account(HttpSession session) {
    String userId = (String) session.getAttribute("userId");
    return accountService.findForUser(userId);
}
~~~

Nếu session được container lưu trong process, request từ B không đọc được phiên tạo ở A. Có thể vẫn giữ HttpSession nếu **backing session store được chia sẻ**; vấn đề là vị trí dữ liệu và khả năng truy cập giữa instances.

### 3.2. Mutable singleton hoặc static field

~~~java
@Service
public class CheckoutService {
    private String currentCustomerId;

    public void begin(String customerId) {
        this.currentCustomerId = customerId;
    }
}
~~~

Đây là lỗi ngay cả khi chỉ chạy một JVM: các thread có thể ghi đè dữ liệu người dùng của nhau. Trong Spring, một service singleton thường được chia sẻ cho mọi request. Không đặt user-specific state trong field mutable; hãy truyền identity và operation ID qua tham số và đọc dữ liệu từ nguồn hợp lệ.

### 3.3. In-memory cache biến thành nguồn sự thật

Nếu giỏ hàng chỉ lưu trong Redis local giả lập, Caffeine cache riêng hoặc Map, mất cache đồng nghĩa mất nghiệp vụ. Cache đúng nghĩa thường có thể được xóa và nạp lại từ database mà không ảnh hưởng tính đúng.

Một rate limiter local có thể hữu ích để bảo vệ process, nhưng nếu giới hạn là 100 request/phút cho **toàn dịch vụ**, ba instance tự đếm riêng có thể cho nhiều hơn dự kiến.

### 3.4. File tạm, lock, scheduler, background thread

Các triệu chứng khác:

- Upload tệp vào ổ đĩa A, request finalize đi vào B thì không tìm thấy tệp.
- Dùng synchronized để khóa cập nhật cùng một SKU; JVM B vẫn có thể cập nhật song song với A.
- Mỗi replica tự chạy scheduled job gửi hóa đơn, tạo ra N lần gửi.
- Giữ Future của một tác vụ dài trong Map của API; client đi vào replica khác không thể truy vấn kết quả.
- Registry WebSocket chỉ nằm trên A nhưng một worker ở C cố gửi trực tiếp sự kiện tới người dùng đang nối A.

Cần nhận diện chúng như các loại **state ẩn** và quyết định cách chia sẻ, checkpoint hoặc chấp nhận mất khi failover.

## 4. Mô hình A: mỗi request tự mang credential có thể xác minh

Với API, một hướng phổ biến là dùng **access token** do identity provider cấp. Mỗi request gửi token; bất kỳ replica nào cũng có thể xác minh và kiểm quyền theo chính sách được cấu hình nhất quán.

~~~text
+--------+       Login         +--------------------+
| Client | ------------------> | Identity Provider  |
+----+---+                     +---------+----------+
     |                                   |
     | <----------- Access Token --------+
     |
     | Authorization: Bearer <token>
     v
+--------------------+
| Load Balancer      |
+----+---------+-----+
     |         |
     v         v
  API A      API B  -----> Business Database
~~~

Request thứ nhất đến A, request thứ hai đến B vẫn có thể thành công vì B không đòi session RAM do A tạo. B sử dụng token hợp lệ và dữ liệu nghiệp vụ bền vững.

### 4.1. JWT có thể được kiểm tra cục bộ

JWT được ký phù hợp thường mang claims như subject, issuer, audience và thời hạn. Resource server kiểm tra chữ ký và các claims liên quan với khóa và trust policy đã cấu hình.

Cần hiểu:

- JWT **được ký** không mặc nhiên **được mã hóa**. Payload có thể đọc được; tránh đặt password, token bí mật hay PII không cần thiết.
- Chỉ kiểm chữ ký là chưa đủ. Phải xác minh issuer, audience, thời hạn, thuật toán được phép, quyền truy cập và điều kiện áp dụng.
- Token có thời hạn dài làm việc thu hồi sớm phức tạp; có thể dùng lifetime ngắn, revocation hoặc kiểm quyền hiện hành theo yêu cầu.
- Refresh token và login state có thể do identity provider quản lý. API stateless không có nghĩa toàn hệ thống không còn state.
- Kiểm chứng token phải nhất quán giữa replicas trong quá trình key rotation và rolling deploy.

### 4.2. Opaque token cũng có thể không cần local session

Opaque token thường là một chuỗi tham chiếu; resource server cần tra cứu hoặc introspection từ hệ thống xác thực, có thể cache theo chính sách. Cả JWT và opaque token đều có thể hỗ trợ các replica API không giữ session riêng. Chọn mô hình dựa trên yêu cầu bảo mật, độ trễ, thu hồi, khả dụng và kiến trúc identity.

### 4.3. Ví dụ HTTP

~~~http
GET /v1/orders/ord-1001 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

Khi nhận request, replica:

1. Xác minh token đúng issuer/audience và thời hạn.
2. Xác định principal và quyền theo contract.
3. Kiểm tra **quyền đối với ord-1001**, không chỉ kiểm tra request đã đăng nhập.
4. Đọc Order database hoặc read model được phép dùng.
5. Trả response; không lưu currentUser vào static field hoặc local Map để lần sau dùng lại.

Nếu một người đổi orderId trong URL để xem đơn của người khác, service phải chặn bằng object-level authorization. Token hợp lệ không đồng nghĩa được truy cập mọi tài nguyên.

## 5. Mô hình B: giữ server-side session trong kho dùng chung

Một ứng dụng web truyền thống có thể muốn dùng cookie và server-side HttpSession. Khi đó có thể lưu session ở **shared store** như Redis hoặc database, thay vì memory process.

~~~text
Browser
  |
  | Cookie: SESSION=abc123
  v
Load Balancer
  +------> Service A -------+
  +------> Service B -------+----> Shared Session Store
  +------> Service C -------+         |
                                       +--> Expiry/logout
Business data -----------------------> Business Database
~~~

A và C đều tra cùng session ID trong store nên request không cần quay về instance tạo session. Cookie thông thường chỉ mang session identifier khó đoán; các thuộc tính phiên thật nằm server-side.

### 5.1. Những yêu cầu với shared session

- **TTL:** session hết hạn sau bao lâu? Có sliding expiration hay cố định?
- **Logout:** phải vô hiệu hóa session theo chính sách; không chỉ xóa UI phía client.
- **Session fixation:** nên đổi session ID khi đăng nhập hoặc nâng quyền theo cơ chế phù hợp.
- **Concurrent update:** hai request cùng sửa session object có thể ghi đè; shared store không đảm bảo mọi logic sửa object là atomic.
- **Serialization:** v1 và v2 đang rolling deploy phải đọc được cùng định dạng session.
- **Tính sẵn sàng:** nếu Redis lỗi, các replica có thể cùng bị ảnh hưởng; phải có thiết kế HA và xử lý lỗi phù hợp.
- **Bảo mật:** cookie Secure/HttpOnly/SameSite, TLS, CSRF protection với cookie authentication, quyền truy cập store và secret management.
- **Giới hạn dữ liệu:** tránh lưu entity JPA hoặc object nghiệp vụ lớn/thay đổi liên tục vào session.

Giữ session trên Redis không có nghĩa dùng Redis làm nguồn sự thật cho thanh toán, đơn hàng hay tồn kho. Những dữ liệu ấy vẫn thuộc database nghiệp vụ với transaction và tính bền vững phù hợp.

### 5.2. So sánh hai mô hình

| Khía cạnh | Token kiểm chứng trên mỗi request | Shared server-side session |
| --- | --- | --- |
| Phụ thuộc vào RAM replica cũ | Không | Không |
| Lưu trạng thái đăng nhập trên server API | Thường không cần với Bearer JWT | Có, trong kho chung |
| Logout/thu hồi sớm | Cần chính sách token/revocation phù hợp | Có thể vô hiệu hóa session trong store |
| Mỗi request tra shared store | JWT có thể tránh, opaque token có thể cần | Thường có |
| Rủi ro nguồn dùng chung | Identity/key policy và dữ liệu nghiệp vụ | Session store là dependency chung |
| Client thường thấy | Mobile/API/SPA theo mô hình bảo mật | Browser web session truyền thống |
| Điểm cần chú ý | Validation, expiry, credential theft, scopes | CSRF, cookie, TTL, serialization, concurrent writes |

Đây là hai cách hợp lý cho những điều kiện khác nhau. Không có quy tắc bắt buộc “mọi microservice phải dùng JWT”.

## 6. Vì sao sticky session không đủ để giải quyết bài toán

**Sticky session/session affinity** cố gửi các request của cùng client về một instance. Nó có thể tạm che lỗi session cục bộ:

~~~text
Client X -> Load Balancer -> A -> session trong RAM A
Client Y -> Load Balancer -> B -> session trong RAM B
~~~

Nhưng nếu A crash hoặc bị thay khi triển khai, session của X vẫn mất. Nếu lưu lượng X rất nặng, affinity còn khiến A chịu tải lệch. Message consumer, callback hoặc background job không nhất thiết tuân theo affinity.

Sticky session có thể hợp lý khi giữ kết nối sống lâu hoặc trong giai đoạn migration, nhưng **không phải cơ chế bảo vệ dữ liệu nghiệp vụ và khả năng phục hồi**. Cần chỉ rõ điều gì xảy ra khi người dùng reconnect sang node khác.

## 7. Thiết kế giỏ hàng không dựa vào RAM replica

Giả sử Cart Service nhận các thao tác đọc và cập nhật giỏ hàng:

~~~text
Client
 | POST /v1/carts/current/items
 v
Load Balancer
 |                 |
 v                 v
Cart Replica A   Cart Replica B
 |                 |
 +--------+--------+
          |
      Cart Database
      carts, cart_items,
      version, customer_id
~~~

Một lần thêm sản phẩm qua A phải được commit vào nguồn dùng chung. Request đọc qua B trả trạng thái được xác lập bởi các thao tác đã commit và semantics nhất quán của hệ thống. Cache có thể được thêm để tối ưu, nhưng không được tự quyết kết quả nghiệp vụ khi dữ liệu nguồn đã đổi.

### 7.1. Chọn quyền sở hữu và nguồn sự thật

| Trạng thái | Owner | Nguyên tắc |
| --- | --- | --- |
| Định danh đăng nhập | Identity/Auth | Xác minh thông tin do nguồn tin cậy cấp; không tin userId client tự khai |
| Giỏ hàng | Cart capability | Store phù hợp với TTL/độ bền được nghiệp vụ chấp nhận |
| Đơn hàng | Order | Transaction, lịch sử chuyển trạng thái và phân quyền |
| Số lượng tồn/reservation | Inventory | Quy tắc đồng thời và chống bán vượt tồn |
| Payment attempt | Payment | Định danh giao dịch, idempotency, đối soát |
| Cấu hình người dùng | User/Profile | Store có owner và quyền truy cập rõ |
| Cache catalog | Catalog hoặc cache layer | Dữ liệu có thể nạp lại, TTL/invalidation |
| Job tạo báo cáo | Report/Job owner | ID, tiến độ, checkpoint và kết quả bền vững |

Stateless instance không cho phép tất cả service tự do ghi cùng bảng. **Data ownership** vẫn cần rõ, kể cả khi một service có nhiều replica truy cập cùng database.

### 7.2. Truyền identity theo request

Một API cập nhật giỏ có thể nhận:

~~~http
POST /v1/carts/current/items HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: add-cart-item-op-981
Content-Type: application/json

{
  "sku": "book-01",
  "quantity": 2
}
~~~

Service xác định customer từ token hoặc session đã xác minh, kiểm tra quyền, áp dụng nghiệp vụ, cập nhật database và trả kết quả. Header Idempotency-Key chỉ có tác dụng khi provider thực sự lưu/kiểm soát logical operation theo một contract rõ.

### 7.3. Đừng nhầm thêm 2 và đặt số lượng bằng 2

- POST add-items với quantity 2 có thể mang nghĩa **cộng thêm hai**. Retry mù có thể cộng hai lần.
- PUT item-quantity với quantity 2 có thể mang nghĩa **đặt số lượng bằng hai**. Lặp cùng operation thường ít gây tác dụng phụ hơn, nhưng vẫn cần xét concurrency và quyền.

Contract phải ghi chính xác ý nghĩa. Việc dùng động từ HTTP nào không tự tạo ra tính đúng khi nhiều replica xử lý.

## 8. Code minh họa Spring Boot: Bearer API không giữ HttpSession

Ví dụ sau giả định service đã có Spring Security và OAuth2 Resource Server tương thích với phiên bản Spring Boot dùng trong dự án.

### 8.1. SecurityFilterChain

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/v1/carts/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
~~~

Đây là **mẫu cho API sử dụng Bearer token trong Authorization header**, không dựa vào browser tự động gửi cookie xác thực. Với ứng dụng xác thực bằng cookie hoặc session, không sao chép cấu hình tắt CSRF một cách máy móc. Mẫu cũng chưa thể hiện mọi import, dependency, exception handler, audience validation hay ownership checks; những phần đó phải được xây dựng theo hệ thống thật.

Có thể cấu hình issuer đáng tin cậy:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
~~~

Địa chỉ trên là dữ liệu minh họa. Cần dùng issuer thật, HTTPS, key rotation và quy tắc audience/scope hợp lệ. Chỉ đặt SessionCreationPolicy.STATELESS không ngăn business code lưu state sai nơi.

### 8.2. Controller không dùng field mutable cho người dùng

~~~java
@RestController
@RequestMapping("/v1/carts")
public class CartController {

    private final CartApplicationService cartService;

    public CartController(CartApplicationService cartService) {
        this.cartService = cartService;
    }

    @GetMapping("/current")
    public CartView current(@AuthenticationPrincipal Jwt jwt) {
        return cartService.findForCustomer(jwt.getSubject());
    }

    @PostMapping("/current/items")
    public CartView addItem(
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody AddItemRequest input) {
        return cartService.addItem(
            jwt.getSubject(), input.sku(), input.quantity());
    }
}

public record AddItemRequest(String sku, int quantity) {}
~~~

CartApplicationService cần kiểm tra input, mapping subject → customer nếu cần, quyền ownership, transaction và quy tắc đồng thời. Trọng tâm là **dữ liệu người dùng đi theo request**, không được giữ trong field currentCustomerId của singleton.

### 8.3. Xử lý concurrency trong database

Một phản mẫu khi hai replica cùng cập nhật:

~~~text
t0: A đọc quantity=1, version=7
t1: B đọc quantity=1, version=7
t2: A ghi quantity=2
t3: B ghi quantity=2
~~~

Nếu A và B đều mang ý nghĩa cộng một, kết quả đúng phải là ba; cách đọc–sửa–ghi vừa nêu mất một cập nhật.

Có thể dùng optimistic locking theo version:

~~~sql
UPDATE cart_items
SET quantity = :newQuantity,
    version = version + 1
WHERE cart_id = :cartId
  AND sku = :sku
  AND version = :expectedVersion;
~~~

Nếu số hàng được cập nhật bằng 0, application phải xử lý xung đột, truy vấn lại và quyết định retry theo contract. Với một số thao tác tăng giảm, câu UPDATE nguyên tử tại database cũng có thể thích hợp hơn. Không dùng synchronized của một JVM để bảo vệ bản ghi được nhiều JVM truy cập.

## 9. Code minh họa Spring Session với Redis

Khi ứng dụng cần HttpSession phía server, Spring Session có thể thay việc lưu session trong bộ nhớ process bằng Redis shared store.

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
  data:
    redis:
      host: redis.internal.example.test
      port: 6379
      ssl:
        enabled: true

server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Đây là cấu hình minh họa và cần dependency Spring Session Redis, Redis client cũng như cấu hình theo phiên bản thực tế. Không sử dụng host hay chính sách mẫu như cấu hình production mặc định. Tất cả replica phải truy cập cùng store, có quản lý network/TLS, secret, HA, TTL và session serialization.

### 9.1. Điểm khó khi nhiều phiên bản cùng đọc session

Trong rolling deployment, replica A chạy v1, B chạy v2. Nếu session lưu một Java object chỉ đọc được bởi class của v1, B có thể lỗi giải mã. Nên giới hạn session vào dữ liệu tối thiểu và định dạng có chiến lược tương thích; tránh lưu entity domain phức tạp hoặc object graph phụ thuộc implementation.

### 9.2. Nếu shared session store lỗi thì sao?

Nếu Redis không khả dụng, nhiều replica có thể cùng không xác thực được. Cần health/metrics, timeout, giới hạn retry, khả năng failover và thông báo lỗi đúng security. **Không được bỏ kiểm tra đăng nhập để “degrade” khi không đọc được session.** Đặt thêm Redis là dịch chuyển state khỏi instance, không xóa bỏ mọi điểm lỗi chung.

## 10. Idempotency và timeout khi instance biến mất

Stateless instance giải quyết phụ thuộc phiên, nhưng còn bài toán **request đã commit mà response bị mất**.

~~~text
Client            Replica A              Database
  | POST /orders      |                      |
  |------------------>| BEGIN                |
  |                   | INSERT order         |
  |                   |--------------------->|
  |                   | COMMIT                |
  |                   |<---------------------|
  |  response lost    X crash                |
  | ...timeout...     |                      |
  |
  | retry POST /orders
  v
Replica B
~~~

B không có RAM từ A. Nếu dùng database và operation ID được lưu bền, B có thể biết request tương ứng đã thành công và trả cùng logical result, thay vì tạo đơn mới.

### 10.1. Thiết kế khóa thao tác logic

Một cách làm:

1. Client gửi Idempotency-Key cùng payload theo contract.
2. Service kiểm tra key trong phạm vi người dùng, operation type và TTL áp dụng.
3. Key chưa tồn tại: tạo record operation và thực hiện nghiệp vụ với transaction/unique constraint phù hợp.
4. Key đã tồn tại với cùng payload: trả lại kết quả hoặc trạng thái đang xử lý.
5. Key tồn tại nhưng payload khác: từ chối theo contract.
6. Hai replica nhận cùng key **đồng thời** phải được database/coordination xử lý an toàn.

Không tự tạo key mới mỗi lần retry một thao tác logic. Đối với thanh toán, cần cả idempotency và đối soát ở cổng ngoài nếu side effect đã xảy ra nhưng kết quả trả về không chắc chắn.

### 10.2. Local transaction không phải transaction xuyên dịch vụ

Nếu Cart/Order/Payment là các service khác nhau, mỗi bên có transaction cục bộ. Một process crash có thể làm trạng thái từng bên lệch thời điểm. Outbox, message idempotency, saga và reconciliation có thể cần thiết; một session store dùng chung không thay thế các cơ chế nhất quán nghiệp vụ đó.

## 11. Upload và lưu file khi scale

Nếu request đầu upload chunk vào ổ đĩa A, request sau đi vào B sẽ không thấy chunk đó:

~~~text
Chunk 1 -> A -> local disk A
Chunk 2 -> B -> local disk B
Finalize -> C -> không tìm thấy dữ liệu hoàn chỉnh
~~~

Hướng thiết kế có thể dùng object storage và uploadId chung:

- API phát uploadId và cấp signed URL có thời hạn nếu phù hợp.
- Client tải dữ liệu lên object storage hoặc shared upload service.
- Server lưu metadata, owner, kích thước, checksum, trạng thái và TTL của upload.
- Bất kỳ replica nào cũng có thể kiểm tra và finalize theo quyền hạn và dữ liệu đã commit.
- Dọn upload bỏ dở, quét nội dung và kiểm giới hạn theo chính sách.

Dùng local temporary file vẫn có thể phù hợp cho xử lý trong một request nếu mất file cùng request là chấp nhận được. Nhưng dữ liệu cần truy cập bởi request ở node khác hoặc sống qua restart phải được lưu phù hợp.

## 12. Background job và scheduler

Một tác vụ tạo báo cáo kéo dài năm phút không nên được lưu duy nhất bằng Future trong RAM của một API replica.

~~~text
Client -> POST /reports
              |
              v
           API A
              |
          create jobId
              |
              v
        Job Database / Queue
              |
       +------+------+
       |             |
     Worker 1      Worker 2
              |
              v
        Object Storage
              |
Client -> GET /reports/jobs/{jobId} -> API B -> Job Database
~~~

Client có thể hỏi tiến độ bằng bất kỳ replica nào. Nếu worker chết, task có thể được giao lại theo lease/ack và phải chịu được retry an toàn.

Một scheduler được khởi tạo trong mọi replica có thể chạy cùng tác vụ nhiều lần. Các lựa chọn gồm: scheduler riêng, distributed lock/lease được thiết kế đúng, hàng đợi phân công hoặc event-based workflow. Distributed lock có các rủi ro timeout, lease expiry và fencing; với tác vụ có side effect vẫn cần idempotency.

## 13. WebSocket, SSE và các kết nối sống lâu

WebSocket hoặc TCP connection cụ thể **luôn gắn với một instance trong lúc kết nối tồn tại**. Trạng thái socket, buffer và heartbeat có thể nằm cục bộ. Điều quan trọng là xác định phần state nào có thể mất khi reconnect và phần nào là trạng thái nghiệp vụ cần lưu.

Ví dụ người dùng nối WebSocket vào A; Order event được xử lý trên B. Nếu B chỉ phát vào danh sách socket trong RAM B, người dùng trên A có thể không nhận được. Có thể dùng broker/pub-sub để fan-out hoặc cơ chế routing event thích hợp.

Nếu sự kiện phải được nhận lại sau khi mất kết nối, pub/sub đơn giản chưa chắc đủ vì có thể không lưu lịch sử. Cần event log, cursor/sequence hoặc endpoint đồng bộ trạng thái từ nguồn bền vững.

### 13.1. Trạng thái kết nối và trạng thái nghiệp vụ khác nhau

- Socket object và heartbeat: có thể local, bị tạo lại khi reconnect.
- Identity/authorization: phải được kiểm tra khi thiết lập và theo policy suốt vòng đời kết nối.
- Notification nghiệp vụ quan trọng: cần lưu/đối soát nếu yêu cầu không được mất.
- Cursor hoặc lastEventId: giúp resume khi connection chuyển sang node khác.
- Presence/online status: thường là dữ liệu tạm có TTL và semantics riêng, không nên bị hiểu là bằng chứng tuyệt đối người dùng đang online.

Stateless ở mức request không đồng nghĩa cấm sử dụng bộ nhớ cho dữ liệu ngắn hạn, stream buffer hay connection state.

## 14. Bảo mật khi không giữ session RAM

### 14.1. Bearer token

- Xác minh issuer, audience, chữ ký, thuật toán tin cậy, expiry và quyền.
- Không log raw access token hoặc đặt token trong URL dễ rò rỉ.
- Cân nhắc thời hạn token, rotation, revocation và cách quyền cập nhật.
- Dùng HTTPS và giới hạn scope theo nguyên tắc tối thiểu.
- Kiểm authorization theo đối tượng: GET /orders/{id} không được trả đơn của khách khác.
- Không mặc định dữ liệu trong signed JWT là bí mật.
- Nếu SPA/browser, chọn cách xử lý credential theo thiết kế chống XSS/CSRF; tránh khuyến nghị một nơi lưu token chung cho mọi ứng dụng.

### 14.2. Cookie + session

- Cookie phải có session ID khó đoán; dùng Secure/HttpOnly và SameSite phù hợp.
- Thiết kế CSRF protection cho hành động thay đổi dữ liệu khi cookie được gửi tự động.
- Luân chuyển session ID sau đăng nhập/nâng quyền nếu thích hợp.
- Có logout, expiry, invalidation và xử lý concurrent sessions.
- Dữ liệu trong Redis/database session phải có quyền truy cập hạn chế và TLS.
- Nếu mất session store, từ chối an toàn thay vì tự cho phép unauthenticated access.

### 14.3. Không gắn quyền với địa chỉ replica

Một replica mới không có lịch sử của user, nhưng nó phải đánh giá **cùng chính sách authorization**. Không vì client đi qua gateway mà tự tin mọi request nội bộ đều đáng tin. Dịch vụ cần biết nguồn identity và trust boundary cho từng loại request.

## 15. Cấu hình và vận hành nhiều replica

### 15.1. Cấu hình nhất quán

Tất cả replica cùng version contract cần thống nhất:

- Issuer/audience, key discovery, quyền và cấu hình token validation.
- Session store endpoint, namespace, TTL và serializer nếu dùng HttpSession chia sẻ.
- Database schema/migration tương thích.
- Cấu hình timeout, retry, feature flags và giới hạn tài nguyên theo chính sách.
- Correlation ID và tracing để theo dõi request qua các replica.

Một replica dùng key cũ hoặc lệch đồng hồ có thể trả 401 ngẫu nhiên khi load balancer chuyển traffic. Cần đo lỗi theo instance và version để phát hiện.

### 15.2. Health check không phải bảo đảm mọi nghiệp vụ khỏe

- **Liveness:** tiến trình có cần được restart hay không.
- **Readiness:** instance có nên nhận request mới không.
- **Dependency status:** DB, Redis, broker hoặc identity provider có đáp ứng năng lực cần thiết không.

Không nên khiến mọi replica restart liên tục chỉ vì một dependency dùng chung tạm chậm. Readiness cần được thiết kế theo khả năng phục vụ và tránh phản ứng dây chuyền.

### 15.3. Rolling deployment và graceful shutdown

~~~text
T0: A, B chạy phiên bản cũ
T1: C phiên bản mới khởi động và readiness đạt
T2: Load balancer thêm C
T3: A được drain, không nhận request mới
T4: Các request đang xử lý trên A hoàn tất hoặc kết thúc theo deadline
T5: B, C tiếp tục nhận request; không cần copy HttpSession RAM từ A
~~~

Dù không còn local session, rollout vẫn phải xử lý request in-flight, transaction sau commit, long-running job và tương thích schema/token/session giữa phiên bản cũ và mới. **Không có local session** là một điều kiện hỗ trợ scale, không tự động đảm bảo zero downtime.

## 16. Kế hoạch chuyển đổi một ứng dụng còn giữ session cục bộ

### Giai đoạn 1 — Kiểm kê state

Lập bảng các nơi đang lưu dữ liệu quá vòng đời request: HttpSession, static map, singleton, local cache, file tạm, queue RAM, scheduler, WebSocket registry. Ghi ai dùng, vòng đời, yêu cầu bền vững, nguồn sự thật và hành vi khi replica mất.

### Giai đoạn 2 — Định nghĩa identity/session

Chọn Bearer token được mỗi replica kiểm chứng hoặc shared session store nếu vẫn cần HttpSession. Ghi các yêu cầu logout, CSRF, credential rotation, permissions và compatibility.

### Giai đoạn 3 — Di chuyển business state

Chuyển cart, order, payment, progress sang kho dùng chung có ownership, transaction, concurrency control và TTL phù hợp. Tránh vừa lưu trong RAM vừa coi RAM là nguồn thật.

### Giai đoạn 4 — Di chuyển coordination

Đưa upload ra shared storage, job vào queue/worker có job ID, message quan trọng vào cơ chế bền vững. Đưa lock và counter toàn cụm đến nơi có semantics đúng. Định nghĩa idempotency cho các thao tác retry.

### Giai đoạn 5 — Chuẩn hóa contract và observability

Thiết lập cấu hình token/session tương thích; log service, instance, version, requestId, traceId và operationId khi phù hợp. Không log token hoặc dữ liệu nhạy cảm. Theo dõi lỗi/session lookup/retry theo replica.

### Giai đoạn 6 — Thử nhiều instance

Chạy ít nhất hai replica với load balancer có thể chuyển request giữa chúng. Buộc cùng user đọc/ghi qua replica khác, restart một replica và kiểm tra dữ liệu sau commit. Thử mixed-version rollout và dependency failure.

### Giai đoạn 7 — Rollout có giới hạn

Chuyển traffic tăng dần theo chính sách vận hành. Theo dõi tỷ lệ đăng nhập lỗi, session lookup, cart consistency, duplicate operations, latency và shared-store saturation. Có đường rollback tương thích dữ liệu đã được ghi.

## 17. Kiểm thử bắt buộc để chứng minh có thể nhân bản

### 17.1. Request luân phiên giữa replicas

~~~text
Given:
  A, B, C đang phục vụ.
  User U có credential hợp lệ.
  Cart U ở store chung với version=3.

When:
  POST thêm item đi vào A.
  GET giỏ hàng đi vào B.
  POST cập nhật số lượng đi vào C.
  GET giỏ hàng đi vào A.

Then:
  Cả bốn request được xác thực/ủy quyền đúng.
  Những thao tác đã commit được phản ánh theo contract.
  Không có bước phụ thuộc vào RAM của instance trước.
~~~

### 17.2. Restart replica tạo phiên

Đăng nhập hoặc tạo phiên trên A. Kill A. Dùng cookie/token còn hợp lệ gọi một request tới B. Kỳ vọng B xác thực được (nếu policy và store cho phép) và đọc đúng dữ liệu. Kiểm thêm logout/expiry và quyền bị thu hồi.

### 17.3. Crash sau khi commit

~~~text
Given:
  POST /orders với Idempotency-Key K.
When:
  Replica A commit order và crash trước khi trả response.
  Client retry cùng logical operation qua Replica B.
Then:
  Không có đơn trùng do retry.
  B truy vấn hoặc trả được kết quả thao tác đã commit.
~~~

### 17.4. Cập nhật đồng thời

Cho A và B cập nhật cùng Cart hoặc reservation gần như đồng thời. Kiểm tra lost update, optimistic locking, business invariant, phiên bản trạng thái và số side effect thực tế. Đừng chỉ kiểm rằng cả hai HTTP request trả 200.

### 17.5. Shared session store không khả dụng

Ngắt Redis hoặc giảm năng lực store trong môi trường thử nghiệm. Kiểm tra không bỏ qua xác thực; timeout có giới hạn; không tạo retry storm; có cảnh báo và khi phục hồi session được xử lý theo policy. Nếu dùng JWT, thử key rotation và instance có cache key khác thời điểm.

### 17.6. Rolling deployment lệch phiên bản

Chạy A-v1 và B-v2 đồng thời. Chuyển request liên tục; kiểm token/session format, database schema, event payload và contract. Nếu session dùng object Java phức tạp, kiểm serialization giữa hai phiên bản.

### 17.7. Trạng thái job và upload

Khởi tạo job/upload ở A, tiếp tục qua B, rồi kill A. Kiểm tra job có thể resume/retry theo quy tắc và file vẫn có thể truy cập. Không chỉ test đường thành công trên một node.

## 18. Các chỉ số vận hành và chẩn đoán lỗi

| Nhóm tín hiệu | Quan sát phù hợp |
| --- | --- |
| Routing/load balance | Request/instance, skew tải, lỗi theo instance và version |
| Xác thực | Tỷ lệ 401/403 bất thường, token validation latency, session lookup failure |
| Shared session store | Latency Redis, timeouts, eviction, connections, failover, memory |
| Business state | Cart mất dữ liệu, duplicate orders/charges, lost update, inconsistent status |
| Retry | Attempt per operation, timeout rate, số idempotency hits, retry amplification |
| Background jobs | Backlog, lease expiry, dead-letter, job quá hạn, retry count |
| Deployment | Lỗi trong drain/restart, mixed-version compatibility |
| Capacity | P95/P99, CPU, thread pool, DB lock, kết nối và saturation |
| Security | Lỗi phân quyền đối tượng, thay đổi quyền và độ trễ hiệu lực |

Phân biệt **service-level** và **instance-level** metrics. Trung bình của cả service có thể che một replica lỗi cấu hình, trong khi một replica không khỏe chưa chắc làm service ngừng hoạt động.

### 18.1. Chẩn đoán từ triệu chứng

**Đăng nhập lúc được lúc không:** kiểm tra local session, cookie affinity, Redis TTL, trust key/issuer, clock skew và phân phối load balancer.

**Giỏ hàng biến mất sau khi scale:** tìm in-memory cart map, local cache thành nguồn sự thật, write chưa commit hoặc phiên bản đọc khác nhau.

**Số replica tăng nhưng throughput không tăng:** đo database contention, downstream dependency, queue và network hop. Tách session khỏi RAM không biến DB thành vô hạn.

**Job chạy N lần:** tìm scheduler khởi tạo trong N instance và thiếu mechanism ownership/lease.

**Chỉ người dùng nối một node nhận event:** xem WebSocket routing và hệ thống pub/sub/replay.

## 19. Những hiểu nhầm phổ biến

**“Stateless là không cần database.”** Không đúng. Business state vẫn cần lưu bền; stateless ở đây là không phụ thuộc vào phiên cục bộ giữa requests.

**“Dùng JWT chắc chắn làm ứng dụng stateless.”** Không đúng. Mã có thể vẫn lưu cart hoặc currentUser trong singleton. Token phải được kiểm chứng và phân quyền đúng.

**“Có Redis là hết lỗi session.”** Không đúng. Redis giải quyết nơi lưu chung, không tự xử lý concurrent writes, expiry, serialization, HA và bảo mật.

**“Sticky session đã đủ an toàn.”** Không đúng. Affinity không bảo vệ dữ liệu khi replica chết, bị thay hoặc có job/callback đến node khác.

**“ConcurrentHashMap đồng bộ giữa các Pod.”** Không đúng. Nó chỉ tồn tại trong JVM chứa nó.

**“Mọi cache local đều sai.”** Không đúng. Cache đọc có thể dùng hiệu quả nếu mất cache không phá tính đúng, có invalidation và nguồn sự thật.

**“Một lock synchronized bảo vệ cả cluster.”** Không đúng. Những replica khác có lock riêng; invariant chung nên được bảo vệ tại dữ liệu/coordination phù hợp.

**“Không còn session là không cần idempotency.”** Không đúng. Replica có thể crash sau khi đã commit, còn client retry ở node khác.

**“Socket/WebSocket cũng phải hoàn toàn không có state.”** Không đúng. Connection-local state vẫn tồn tại; trạng thái quan trọng cần cơ chế reconnect/resume.

**“Thêm replica tự động tăng tính sẵn sàng.”** Không chắc. Có thể có điểm lỗi chung tại database, session store hoặc identity provider.

## 20. Bài tập ứng dụng

### Bài 1 — Lỗi phiên ngẫu nhiên khi chạy ba Pod

Một ứng dụng Spring Boot lưu HttpSession trong container và bật ba Pod. Client thỉnh thoảng bị đăng xuất khi chuyển request.

**Yêu cầu:** giải thích nguyên nhân, đề xuất hai hướng sửa, nêu cách kiểm thử sau thay đổi.

**Gợi ý:** Bearer API xác minh token tại mỗi replica hoặc shared Spring Session store nếu còn dùng HttpSession. Kiểm thử đăng nhập qua A, request tiếp theo qua B và restart A.

### Bài 2 — Tìm dữ liệu phiên ẩn

~~~java
@Service
public class RegistrationService {
    private final Map<String, RegistrationDraft> drafts =
        new ConcurrentHashMap<>();

    public void start(String userId, RegistrationDraft draft) {
        drafts.put(userId, draft);
    }

    public RegistrationDraft finish(String userId) {
        return drafts.remove(userId);
    }
}
~~~

**Yêu cầu:** tìm lỗi khi người dùng bắt đầu ở A và hoàn tất ở B, khi A restart và khi hai request cùng sửa draft. Đề xuất registrationId, ownership, TTL, version và shared store.

### Bài 3 — Payment bị timeout sau commit

Một Payment API xử lý thành công nhưng response mất. Client gửi lại tới replica khác.

**Yêu cầu:** thiết kế idempotency key, payment operation record và cách tra cứu kết quả. Giải thích vì sao token stateless không ngăn double charge.

### Bài 4 — Phân loại trạng thái

Hãy xác định cách xử lý cho: cache catalog, giỏ hàng khách, socket đang mở, báo cáo chạy năm phút, local lock cho tồn kho, rate limit toàn tenant và temporary upload file. Với mỗi mục, ghi rõ có được phép giữ cục bộ không, mất replica sẽ ra sao và nguồn sự thật nằm ở đâu.

### Bài 5 — Kế hoạch scale từ một lên ba replica

Ứng dụng hiện có login bằng cookie, cart RAM, file upload vào local disk và scheduled job trong process.

**Yêu cầu:** lập kế hoạch migration, thứ tự ưu tiên, các phép thử failover, điểm lỗi chung mới và tiêu chí rollback. Trình bày tại sao chỉ tăng replica count không giải quyết được từng lỗi.

### Bài 6 — Rolling deployment

Phiên bản v1 lưu một object UserSession có enum role. Phiên bản v2 thay class/enum. Hai phiên bản cùng đọc một Redis session trong lúc rolling deploy.

**Yêu cầu:** giải thích lỗi compatibility có thể xảy ra và đề xuất một định dạng phiên tối giản, có version hoặc cách triển khai expand/contract phù hợp.

## 21. Checklist trước khi nhân bản service

Checklist này giúp xác định các quyết định cần thực hiện; không thay thế thử nghiệm thực tế.

- [ ] Request có thể xác thực và kiểm quyền độc lập với instance phục vụ request trước.
- [ ] Không có currentUser, session hay cart nằm duy nhất trong mutable singleton/static Map.
- [ ] Nếu dùng HttpSession, mọi replica truy cập shared session store có TTL và security phù hợp.
- [ ] Business state có owner, nguồn lưu, transaction và cơ chế cập nhật đồng thời.
- [ ] Cache cục bộ có thể mất mà không phá tính đúng.
- [ ] Mỗi thao tác side effect có chiến lược retry/idempotency khi response mất.
- [ ] Không dùng local synchronized để thay thế cơ chế nhất quán toàn cụm.
- [ ] Rate limit/counter toàn service có semantics chia sẻ đúng.
- [ ] Upload, long-running job và event quan trọng có kho/queue hoặc checkpoint phục hồi được.
- [ ] WebSocket/SSE có cơ chế event distribution và reconnect/resume phù hợp.
- [ ] Token/cookie/session có bảo mật, expiry, authorization, CSRF/revocation theo kiến trúc thật.
- [ ] Cấu hình auth, schema và contract của các phiên bản cùng chạy tương thích.
- [ ] Readiness, graceful shutdown và rollback đã được định nghĩa.
- [ ] Kiểm thử luân phiên request giữa replicas, kill node và retry sau commit thành công.
- [ ] Database, Redis, broker và identity provider có capacity, monitoring và kế hoạch chịu lỗi.

## 22. Ghi nhớ

**Thiết kế hỗ trợ nhân bản là thiết kế để một instance mới có thể phục vụ request mà không cần “ký ức” riêng của instance cũ.** Có thể dùng token được kiểm chứng trên từng request hoặc session store chia sẻ; vẫn phải giữ business state trong nguồn được sở hữu rõ ràng.

Ba nguyên tắc cần nhớ:

1. **Phiên người dùng không được phụ thuộc vào RAM một replica.**
2. **Trạng thái nghiệp vụ cần tồn tại, được bảo vệ concurrency và có thể phục hồi.**
3. **Stateless chưa đủ để đúng:** cần authorization, idempotency, timeout, transaction, retry có kiểm soát và thử nghiệm failover.

Khi review một sơ đồ có load balancer trước ba container, hãy hỏi: **“Nếu request kế tiếp đi tới một instance mới hoàn toàn và instance cũ bị xóa ngay lúc này, hệ thống có còn biết người dùng là ai, quyền gì, thao tác đang ở đâu và phải tiếp tục ra sao không?”** Nếu câu trả lời được chứng minh bằng contract, dữ liệu bền và kiểm thử thực tế, service có nền tảng tốt để scale ngang.
