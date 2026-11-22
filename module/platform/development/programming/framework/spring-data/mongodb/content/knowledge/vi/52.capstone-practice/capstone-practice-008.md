# Tạo luồng truy cập reactive có xử lý lỗi và giới hạn tài nguyên

## 1. Bài toán capstone: API đơn hàng chịu tải nhưng vẫn kiểm soát được

Trong module **SPRING_DATA_MONGODB**, chúng ta học cách sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua **MongoTemplate** hoặc **repository**. Những kỹ năng truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu được kết hợp trong chương **Thực hành tổng hợp** để xây dựng một chức năng có thể vận hành thực tế.

Giả sử một hệ thống nhiều khách hàng doanh nghiệp (*multi-tenant*) cần API tra cứu đơn hàng đã thanh toán. Mỗi người dùng chỉ được xem đơn hàng thuộc tenant đã xác thực. Dữ liệu có thể lên tới hàng triệu document; có lúc nhiều người dùng đồng thời chuyển trang, trong khi MongoDB gặp chậm mạng hoặc replica set thay đổi primary.

Yêu cầu của hệ thống:

1. Dùng **Spring WebFlux** và **ReactiveMongoTemplate** để truy cập MongoDB bằng mô hình không chặn luồng xử lý trong lúc chờ I/O.
2. Luôn lọc theo tenant từ danh tính đã xác thực; không để client tự chọn tenant tùy ý.
3. Trả kết quả theo thứ tự ổn định và **giới hạn số document mỗi lần đọc**.
4. Dùng **keyset pagination** để tránh chi phí tăng theo độ sâu trang như skip/offset.
5. Phân loại lỗi tham số, lỗi database, timeout; trả HTTP status phù hợp mà không lộ thông tin nội bộ.
6. Giới hạn thời gian chờ, số thao tác đồng thời, tài nguyên pool và lượng dữ liệu giữ trong bộ nhớ.
7. Đo hành vi bằng Reactor StepVerifier, kiểm thử tích hợp và metrics khi tăng tải.

**Mục tiêu của bài** là một luồng hoàn chỉnh từ HTTP request đến MongoDB rồi trở lại client, có hợp đồng rõ ràng về an toàn dữ liệu và cách ứng xử khi thất bại. Code tập trung vào các API thông dụng của Spring Boot 3.x, Spring WebFlux, Spring Data MongoDB và Reactor trên Java 17 trở lên; khi dùng phiên bản khác phải kiểm tra API và configuration metadata tương ứng.

## 2. Tư duy reactive và giới hạn của nó

### 2.1. Mono và Flux không đồng nghĩa tài nguyên vô hạn

Trong Reactor:

| Kiểu | Kết quả logic | Ví dụ trong bài |
| --- | --- | --- |
| Mono<T> | 0 hoặc 1 phần tử, hoặc tín hiệu lỗi | Một trang OrderPage sau khi truy vấn |
| Flux<T> | 0 đến nhiều phần tử, hoặc tín hiệu lỗi | Dãy document MongoDB trả theo cursor |
| Subscription | Vòng đời tiêu thụ publisher | WebFlux điều phối khi nhận HTTP request |
| Backpressure | Downstream báo số phần tử đang sẵn sàng nhận | Giúp phối hợp tốc độ phát và tiêu thụ dữ liệu |
| Cancellation | Bên tiêu thụ ngừng nhận dữ liệu | Khi timeout hoặc client ngắt kết nối |

Reactive giúp tránh chặn một thread cho mỗi thao tác I/O, nhưng MongoDB connection pool, CPU, RAM, bandwidth và tốc độ ghi HTTP vẫn hữu hạn. Nếu người lập trình tạo 10.000 truy vấn MongoDB song song bằng flatMap không giới hạn hợp lý, API vẫn có thể hết connection và bộ nhớ.

Tránh gọi **block()** hoặc **subscribe()** thủ công trong WebFlux controller. Hãy trả Mono/Flux và để framework quản lý subscription. Không bọc một phương thức MongoTemplate đồng bộ trong Mono.just rồi cho rằng toàn bộ luồng đã trở thành non-blocking.

### 2.2. Thiết kế luồng của bài

~~~mermaid
flowchart LR
  A[GET /api/orders] --> B[Spring Security xác thực JWT]
  B --> C[Controller lấy tenant_id]
  C --> D[Validate status / size / cursor]
  D --> E[ReactiveMongoTemplate]
  E --> F[(MongoDB có compound index)]
  F --> G[Flux tối đa size + 1]
  G --> H[collectList với giới hạn]
  H --> I[OrderPage và nextCursor]
  I --> J[HTTP JSON]
~~~

Song song với luồng dữ liệu, lớp dịch vụ áp dụng timeout và chuyển các lỗi hạ tầng đã xác định sang lỗi HTTP phù hợp. Truy vấn luôn mang điều kiện tenant; pool MongoDB và concurrency của ứng dụng phải được giới hạn ngoài phạm vi riêng của một truy vấn.

## 3. Hợp đồng dữ liệu và API

### 3.1. Document mẫu

Collection **orders** dùng schema minh họa:

~~~javascript
{
  _id: ObjectId("65350f8453dbe413901c1211"),
  tenantId: "tenant-A",
  status: "PAID",
  createdAt: ISODate("2026-11-18T08:30:00.000Z"),
  totalCents: NumberLong("125000")
}
~~~

Quy tắc:

- tenantId được lấy từ identity của người gọi; mỗi order có một tenantId duy nhất.
- status thuộc tập PAID, PENDING, CANCELLED trong ví dụ.
- createdAt là BSON Date, có giá trị và **không được tùy tiện sửa sau khi tạo**.
- _id là ObjectId duy nhất; tổng tiền được lưu dưới dạng số nguyên cent để tránh phép tính tiền qua double.
- Dữ liệu thời gian sử dụng UTC; MongoDB Date lưu độ chính xác đến millisecond.

### 3.2. API tìm kiếm có giới hạn

~~~http
GET /api/orders?status=PAID&size=20
Authorization: Bearer <JWT_TOKEN>
Accept: application/json
~~~

Ví dụ phản hồi:

~~~json
{
  "items": [
    {
      "id": "65350f8453dbe413901c1211",
      "status": "PAID",
      "createdAt": "2026-11-18T08:30:00Z",
      "totalCents": 125000
    }
  ],
  "hasNext": true,
  "nextCursor": {
    "createdAt": "2026-11-18T08:30:00Z",
    "id": "65350f8453dbe413901c1211"
  }
}
~~~

Client dùng cặp khóa của phần tử cuối đã nhận để yêu cầu trang tiếp:

~~~http
GET /api/orders?status=PAID&size=20&afterCreatedAt=2026-11-18T08%3A30%3A00Z&afterId=65350f8453dbe413901c1211
Authorization: Bearer <JWT_TOKEN>
~~~

**Quan trọng:** response mẫu chỉ minh họa cấu trúc. Trong implementation dưới đây, nextCursor chỉ khác null khi còn ít nhất một document sau trang hiện tại. Vì tài liệu sẽ bị thay đổi theo thời gian, keyset giữ thứ tự ổn định của tập đang đọc nhưng không bảo đảm một snapshot bất biến giữa nhiều HTTP request.

Các giới hạn API:

| Quy tắc | Giá trị minh họa | Lý do |
| --- | --- | --- |
| size mặc định | 20 | Tránh vô tình truy xuất tập lớn |
| size tối đa | 100 | Chặn client ép server trả hàng nghìn bản ghi |
| Truy vấn thực tế | size + 1 | Xác định hasNext mà không count toàn collection |
| Thứ tự | createdAt DESC, _id DESC | Có khóa phụ duy nhất khi timestamp trùng |
| Mỗi request | Một trang | Giới hạn RAM và thời gian giữ tài nguyên |
| Deadline reactive | 3 giây trong bài | Hạn chế request chờ quá lâu |
| Cursor | afterCreatedAt và afterId phải cùng xuất hiện | Ngăn phân trang sai do thiếu một khóa |

Với hệ thống production, cân nhắc chuyển hai trường cursor thành **opaque token** được ký và gắn với tenant, filter, sort và hạn sử dụng. Bài này dùng cặp giá trị hiển thị để dễ hiểu thuật toán; việc thay đổi cursor do client gửi không thể vượt qua điều kiện tenant từ nguồn xác thực.

## 4. Chuẩn bị Spring Boot và MongoDB

### 4.1. Dependency

Các starter cần có theo chức năng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ giả định dự án đã có Spring Boot parent/BOM tương thích; không tự gắn phiên bản từng starter riêng lẻ khi đã dùng dependency management. Cần cấu hình JWT resource server theo issuer/audience của nhà cung cấp định danh; chỉ tin claim tenant_id nếu token đã được kiểm tra và quy ước tenant mapping đã được xác nhận.

### 4.2. Cấu hình kết nối

Ví dụ application.yml của Spring Boot 3.x:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}

server:
  shutdown: graceful
~~~

MONGODB_URI phải được cấp từ secret manager hoặc cơ chế cấu hình an toàn của môi trường chạy. Có thể chỉ định replica set, TLS và giới hạn pool trong URI. Không commit username/password thật. Cấu trúc thuộc tính cấu hình có thể khác ở Spring Boot 4; kiểm tra version thực tế trước khi áp dụng.

Ví dụ các option MongoDB **không chứa credential**:

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017/shop?replicaSet=rs0&tls=true&maxPoolSize=40&minPoolSize=4&maxConnecting=2&serverSelectionTimeoutMS=2500&connectTimeoutMS=1500
~~~

**maxPoolSize là giới hạn theo pool của mỗi MongoClient tới từng server**, không phải giới hạn toàn bộ cluster. Những con số trên là ứng viên để load test; phải kiểm tra tổng số pod và tài nguyên MongoDB. Nếu dùng driver hỗ trợ Client-Side Operation Timeout (CSOT) với timeoutMS, phải hiểu cách timeoutMS tương tác với những timeout cũ. Reactor timeout và driver timeout cần được phối hợp theo SLO.

### 4.3. Index phù hợp cho filter và sort

Chạy một lần trong quy trình provisioning/migration với account có quyền tạo index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_status_created_id" }
);
~~~

Giải thích:

1. tenantId và status là điều kiện equality, thu hẹp phạm vi cần đọc.
2. createdAt và _id tương ứng với sort DESC, giúp tránh sắp xếp một tập lớn.
3. _id là khóa phụ duy nhất để các order cùng createdAt có thứ tự xác định.

Nếu ứng dụng còn có query không lọc status hoặc sort theo trường khác, phải đo lại explain và cân nhắc index khác. Không tạo index mới trong mỗi HTTP request; tài khoản MongoDB runtime thường không cần quyền createIndex.

## 5. Lớp model và DTO

### 5.1. Order.java

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id ObjectId id,
    String tenantId,
    String status,
    Instant createdAt,
    long totalCents
) {}
~~~

Sử dụng Java record giúp ví dụ gọn. Trong hệ thống thực, MongoDB document phải có đủ các trường bắt buộc, đặc biệt createdAt và _id. Tránh để nullable sort key khi dùng keyset pagination; converter và schema validation cần đảm bảo type của dữ liệu đúng.

### 5.2. OrderView.java

~~~java
package example.orders;

import java.time.Instant;

public record OrderView(
    String id,
    String status,
    Instant createdAt,
    long totalCents
) {
    public static OrderView from(Order order) {
        return new OrderView(
            order.id().toHexString(),
            order.status(),
            order.createdAt(),
            order.totalCents()
        );
    }
}
~~~

DTO không chứa tenantId hoặc metadata nội bộ không cần đưa cho client. Tuy nhiên, **việc không trả tenantId không phải là cơ chế phân quyền**: query phải được lọc tenant ở phía server trước khi có dữ liệu để map.

### 5.3. OrderPage.java

~~~java
package example.orders;

import java.time.Instant;
import java.util.List;

public record OrderPage(
    List<OrderView> items,
    boolean hasNext,
    NextCursor nextCursor
) {
    public record NextCursor(Instant createdAt, String id) {}
}
~~~

Thiết kế dùng một Page response có số item tối đa 100, không cần trả totalPages/countDocuments trên từng lượt xem. Điều này tránh một count query tốn kém chỉ để biết liệu còn phần tử sau trang hiện tại hay không.

## 6. ReactiveMongoTemplate: truy vấn theo keyset và giới hạn bộ nhớ

### 6.1. Truy vấn của trang đầu và trang tiếp

Trang đầu:

~~~javascript
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(21);
~~~

Trang tiếp sau một document có createdAt = T và _id = I phải thỏa:

~~~text
createdAt < T
HOẶC
(createdAt = T VÀ _id < I)
~~~

Đây là quan hệ thứ tự từ điển cho cặp khóa sắp xếp giảm dần. Chỉ so sánh createdAt sẽ làm mất document có cùng timestamp; yêu cầu cả createdAt và _id cùng nhỏ hơn lại loại sai một số document hợp lệ.

~~~javascript
const lastCreatedAt = ISODate("2026-11-18T08:30:00.000Z");
const lastId = ObjectId("65350f8453dbe413901c1211");

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(21);
~~~

### 6.2. OrderReadService.java

Service sau chứa toàn bộ kiểm tra tham số, xây query, giới hạn số item và chuyển lỗi hạ tầng thành HTTP error. Các lớp model ở phần trước nằm trong cùng package **example.orders**.

~~~java
package example.orders;

import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeoutException;

import com.mongodb.MongoTimeoutException;
import org.bson.types.ObjectId;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderReadService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final Set<String> ALLOWED_STATUS =
        Set.of("PAID", "PENDING", "CANCELLED");
    private static final Duration READ_DEADLINE = Duration.ofSeconds(3);

    private final ReactiveMongoTemplate template;

    public OrderReadService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<OrderPage> findPage(
            String tenantId,
            String status,
            int size,
            String afterCreatedAt,
            String afterId) {

        if (tenantId == null || tenantId.isBlank()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Tenant scope is required"
            ));
        }
        if (status == null || !ALLOWED_STATUS.contains(status)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Unsupported order status"
            ));
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Page size must be between 1 and 100"
            ));
        }
        if ((afterCreatedAt == null) != (afterId == null)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Cursor requires both keys"
            ));
        }

        Instant cursorTime = null;
        ObjectId cursorId = null;
        if (afterCreatedAt != null) {
            if (!ObjectId.isValid(afterId)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid cursor id"
                ));
            }
            try {
                cursorTime = Instant.parse(afterCreatedAt);
            } catch (DateTimeParseException exception) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid cursor timestamp",
                    exception
                ));
            }
            cursorId = new ObjectId(afterId);
        }

        Query query = buildQuery(
            tenantId, status, size + 1, cursorTime, cursorId
        );

        return template.find(query, Order.class)
            // MongoDB đã giới hạn tối đa size+1, nên collectList có bound.
            .collectList()
            .map(rows -> toPage(rows, size))
            .timeout(READ_DEADLINE)
            .onErrorMap(TimeoutException.class, exception ->
                new ResponseStatusException(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "Order query exceeded the time budget",
                    exception
                )
            )
            .onErrorMap(MongoTimeoutException.class, exception ->
                new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Database temporarily unavailable",
                    exception
                )
            )
            .onErrorMap(DataAccessResourceFailureException.class, exception ->
                new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Database temporarily unavailable",
                    exception
                )
            );
    }

    private static Query buildQuery(
            String tenantId,
            String status,
            int fetchSize,
            Instant cursorTime,
            ObjectId cursorId) {

        Criteria scope = new Criteria().andOperator(
            Criteria.where("tenantId").is(tenantId),
            Criteria.where("status").is(status)
        );

        if (cursorTime != null) {
            Criteria older = new Criteria().orOperator(
                Criteria.where("createdAt").lt(cursorTime),
                new Criteria().andOperator(
                    Criteria.where("createdAt").is(cursorTime),
                    Criteria.where("_id").lt(cursorId)
                )
            );
            scope = new Criteria().andOperator(scope, older);
        }

        return Query.query(scope)
            .with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
            ))
            .limit(fetchSize);
    }

    private static OrderPage toPage(List<Order> rows, int size) {
        boolean hasNext = rows.size() > size;
        List<Order> visible = rows.subList(
            0, Math.min(rows.size(), size)
        );
        List<OrderView> items = visible.stream()
            .map(OrderView::from)
            .toList();

        OrderPage.NextCursor nextCursor = null;
        if (hasNext) {
            Order last = visible.get(visible.size() - 1);
            nextCursor = new OrderPage.NextCursor(
                last.createdAt(), last.id().toHexString()
            );
        }
        return new OrderPage(items, hasNext, nextCursor);
    }
}
~~~

**Tại sao size + 1?** Với size = 20, truy vấn tìm tối đa 21 document. Nếu nhận 21, trả 20 document và hasNext = true; nếu nhận 20 hoặc ít hơn, hasNext = false. Không cần đếm toàn bộ collection. Vì size được kiểm tra trước, collectList không giữ vô hạn document.

**Tại sao timeout đặt sau collectList?** Khi subscription không hoàn thành trong 3 giây, Reactor phát TimeoutException và hủy subscription đang chờ. Đây là giới hạn thời gian phía ứng dụng, không phải bằng chứng rằng MongoDB đã dừng mọi công việc trên server ngay thời điểm đó. Cần phối hợp với timeout/CSOT của driver, thời gian gateway và cancellation thực tế.

**Tại sao không tự retry trong service?** Lượt đọc được phép retry ở driver theo các điều kiện của retryable reads. Thêm retry ở Reactor chỉ nên làm sau khi đo tác động, phân loại lỗi có thể phục hồi và có ngân sách thời gian còn lại. Trong bài, ưu tiên một deadline rõ ràng và thông báo lỗi phù hợp.

**Tại sao không bắt mọi Exception để trả 503?** Lỗi ánh xạ dữ liệu, bug hoặc lỗi lập trình cần được phát hiện đúng là lỗi server. Chỉ chuyển các nhóm lỗi hạ tầng xác định sang 503/504; những lỗi không được phân loại sẽ đi qua cơ chế xử lý lỗi mặc định để phục vụ điều tra, với log nội bộ phù hợp và response không lộ thông tin nhạy cảm.

## 7. WebFlux controller: lấy tenant từ danh tính xác thực

### 7.1. OrderController.java

Ví dụ sử dụng Spring Security OAuth2 Resource Server với JWT đã được xác minh. Claim tenant_id phải được nhà cung cấp danh tính và hệ thống phân quyền chấp nhận như nguồn tenant hợp lệ.

~~~java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderReadService service;

    public OrderController(OrderReadService service) {
        this.service = service;
    }

    @GetMapping
    public Mono<OrderPage> list(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam String status,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String afterCreatedAt,
            @RequestParam(required = false) String afterId) {

        if (jwt == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED, "Authentication required"
            ));
        }

        String tenantId = jwt.getClaimAsString("tenant_id");
        return service.findPage(
            tenantId, status, size, afterCreatedAt, afterId
        );
    }
}
~~~

Endpoint còn cần **SecurityWebFilterChain** yêu cầu authentication và JWT issuer/audience validation. Nếu yêu cầu bảo mật chưa cấu hình, việc có tham số Jwt trong method không tự bảo vệ được endpoint. Tránh cho phép client truyền tenantId từ URL rồi coi đó là danh tính đáng tin cậy.

### 7.2. Kỳ vọng HTTP status

| Tình huống | Status | Ý nghĩa |
| --- | --- | --- |
| Query hợp lệ, có hoặc không có bản ghi | 200 | Trả OrderPage; items có thể rỗng |
| Thiếu/sai status, size ngoài 1–100, cursor sai | 400 | Yêu cầu không hợp lệ |
| Không có danh tính hợp lệ | 401 | Spring Security/Controller từ chối |
| Không có tenant scope được phép | 403 | Không thể truy cập dữ liệu theo tenant |
| Reactor deadline hết | 504 trong ví dụ | API không hoàn thành trong ngân sách thời gian |
| Mongo timeout hoặc lỗi truy cập tài nguyên đã phân loại | 503 | Database tạm thời không sẵn sàng |
| Lỗi lập trình hoặc mapping chưa phân loại | 500 | Cần ghi log/điều tra ở server |

Do response của API này là **Mono chứa cả trang**, thông thường HTTP status được quyết định trước khi body được gửi. Đây là lợi thế thực tiễn khi cần trả mã lỗi rõ ràng. Nếu chuyển sang streaming trực tiếp, lỗi xuất hiện sau khi đã gửi byte đầu tiên sẽ có cách xử lý khác.

## 8. Một API có giới hạn tài nguyên phải giới hạn ở nhiều tầng

### 8.1. Các giới hạn bổ trợ nhau

| Giới hạn | Thiết lập trong bài | Nó bảo vệ gì? |
| --- | --- | --- |
| Số item trang | size tối đa 100 | Bộ nhớ response và kích thước dữ liệu |
| Fetch thực tế | Query.limit(size + 1) | Không đọc toàn bộ collection |
| Phân trang | createdAt và _id theo keyset | Giảm chi phí skip ở trang sâu |
| Thời gian | Mono.timeout(3 giây) | Không chờ vô hạn ở API |
| Connection pool | maxPoolSize, maxConnecting, minPoolSize | Bảo vệ số socket/khả năng xử lý MongoDB |
| Tần suất request | Rate limit/quota ở gateway hoặc ứng dụng | Ngăn một client tạo vô hạn request |
| Fan-out | flatMap với concurrency cụ thể | Chặn quá nhiều query độc lập cùng lúc |
| Lượng dữ liệu mỗi document | Schema, projection và giới hạn kích thước | Tránh response khổng lồ dù chỉ có vài item |

Giới hạn trang chưa đủ nếu mỗi document có các trường nhị phân lớn hoặc chứa mảng hàng nghìn phần tử. Với bài toán thực tế, nên dùng projection chỉ lấy trường cần hiển thị và tách nội dung GridFS/lịch sử lớn sang API riêng.

Trong trường hợp phải phân trang qua các khóa sort, projection phải **giữ đủ trường tạo cursor**, chẳng hạn createdAt và _id. Thứ tự có thể thay đổi nếu dữ liệu được sửa giữa các lần đọc; cursor không tự cung cấp snapshot isolation.

### 8.2. Cấu hình MongoDB pool theo tải

Ví dụ các option URI:

~~~text
maxPoolSize=40&minPoolSize=4&maxConnecting=2
~~~

MongoClient duy trì pool **theo từng server** trong topology. Nếu có 8 pod và mỗi pod được cấu hình maxPoolSize=40, riêng giới hạn tiềm năng đến một primary có thể lên tới 320 connection, ngoài kết nối monitoring và các service khác. Không coi maxPoolSize=40 là giới hạn chung toàn hệ thống.

Một ước lượng ban đầu có thể dùng Little's Law:

~~~text
Số connection đang sử dụng trung bình
≈ MongoDB operations/giây x Thời gian giữ connection trung bình (giây)
~~~

Ví dụ mỗi pod xử lý 120 thao tác MongoDB/giây, thời gian chiếm connection trung bình 50 ms, mức đồng thời trung bình xấp xỉ 6. Tuy nhiên burst, slow query, transaction và tải nền có thể khiến nhu cầu cao hơn nhiều. **Không dùng trực tiếp giá trị trung bình làm maxPoolSize**; phải load test, đo checkout wait và đối chiếu CPU/I/O của MongoDB.

### 8.3. Giới hạn fan-out bằng flatMap concurrency

Khi có nhiều order ID cần truy cập độc lập, có thể giới hạn số inner publisher đang chạy:

~~~java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Order> findSomeOrders(
        ReactiveMongoTemplate template,
        String authenticatedTenantId,
        List<ObjectId> ids) {

    if (ids.size() > 100) {
        return Flux.error(new IllegalArgumentException(
            "Too many requested ids"
        ));
    }

    return Flux.fromIterable(ids)
        .flatMap(id ->
            template.findOne(
                Query.query(Criteria.where("_id").is(id)
                    .and("tenantId").is(authenticatedTenantId)),
                Order.class
            ),
            8
        );
}
~~~

Ở đây, 8 là giới hạn số truy vấn độc lập đang được subscribe đồng thời trong đoạn pipeline, **không phải giới hạn pool**. Do flatMap có thể trả kết quả không theo thứ tự input, nếu cần giữ thứ tự hãy đánh giá flatMapSequential hoặc concatMap cùng sự đánh đổi latency. Trước khi phát ra 100 lệnh findOne, thường nên cân nhắc **một truy vấn theo tập _id** có điều kiện tenant và index phù hợp.

### 8.4. limitRate không phải giới hạn tổng số document

**limitRate(n)** điều chỉnh số phần tử downstream yêu cầu theo từng đợt; nó không bảo đảm toàn pipeline chỉ tạo tối đa n kết quả, không giới hạn số truy vấn độc lập theo cách flatMap(concurrency) và không thay thế Query.limit. Tương tự, **onBackpressureBuffer() không có giới hạn** có thể làm heap tăng khi producer nhanh hơn consumer.

Hệ thống phải có giới hạn từ database, concurrency và request rate. Backpressure chỉ là một cơ chế phối hợp tốc độ khi publisher và các thành phần liên quan tôn trọng tín hiệu yêu cầu.

## 9. Khi nào nên truyền trực tiếp Flux qua HTTP?

### 9.1. Streaming NDJSON và response dạng trang

API ở phần 7 trả về **Mono<OrderPage>**. Server giữ tối đa size + 1 document để xác định hasNext, rồi trả một JSON object duy nhất. Cách này giúp gửi 400/503/504 **trước khi HTTP body bắt đầu**, vì lỗi truy vấn có thể được biết trước khi trang hoàn tất.

Nếu client cần tiêu thụ từng document ngay khi MongoDB phát ra, Spring WebFlux có thể truyền **NDJSON** (*Newline Delimited JSON*): mỗi dòng là một JSON object độc lập. Mô hình này có giá trị với xuất báo cáo có giới hạn, sự kiện hoặc dữ liệu chỉ đọc được tiêu thụ tuần tự.

| Tiêu chí | Mono<OrderPage> | Flux<OrderView> NDJSON |
| --- | --- | --- |
| Hình dạng HTTP | Một JSON object có items/hasNext | Nhiều JSON object, mỗi dòng một object |
| Bộ nhớ phía ứng dụng | O(size), tối đa số item đã giới hạn | Không cần thu toàn bộ stream; vẫn phụ thuộc buffer và downstream |
| Xử lý lỗi trước khi gửi body | Dễ gắn HTTP status | Được nếu lỗi xuất hiện trước byte đầu tiên |
| Xử lý lỗi sau khi bắt đầu gửi body | Không thường gặp do response được tạo sau truy vấn | Khó đổi HTTP status; client có thể nhận kết quả thiếu |
| Phân trang | Tích hợp cursor/hasNext rõ ràng | Cần giao thức resume/cursor riêng nếu muốn phát nhiều trang |
| Nhu cầu thực tế | UI danh sách, API cần thông báo lỗi rõ | Export có giới hạn, luồng dữ liệu được consumer xử lý dần |

**Không chọn stream trực tiếp chỉ vì thấy Flux trong service.** Một Mono chứa danh sách hữu hạn vẫn là một luồng reactive: MongoDB đọc bằng driver reactive, WebFlux không phải dùng một thread chặn trong lúc chờ I/O, và việc collectList đã có giới hạn bằng Query.limit.

### 9.2. Ví dụ endpoint NDJSON có giới hạn

Thêm phương thức này **trong OrderReadService** của phần 6, dùng các trường template và ALLOWED_STATUS đã khai báo:

~~~java
import java.time.Duration;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

public Flux<OrderView> streamLimited(
        String tenantId, String status, int size) {

    if (tenantId == null || tenantId.isBlank()) {
        return Flux.error(new ResponseStatusException(
            HttpStatus.FORBIDDEN, "Tenant scope is required"
        ));
    }
    if (status == null || !ALLOWED_STATUS.contains(status)) {
        return Flux.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Unsupported status"
        ));
    }
    if (size < 1 || size > MAX_PAGE_SIZE) {
        return Flux.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid stream size"
        ));
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    )
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    ))
    .limit(size)
    .cursorBatchSize(32);

    return template.find(query, Order.class)
        .map(OrderView::from)
        .limitRate(32)
        // Với Flux, timeout này giới hạn khoảng im lặng giữa các tín hiệu.
        .timeout(Duration.ofSeconds(2));
}
~~~

Trong **OrderStreamController.java**, có thể dùng:

~~~java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/orders")
public class OrderStreamController {

    private final OrderReadService service;

    public OrderStreamController(OrderReadService service) {
        this.service = service;
    }

    @GetMapping(value = "/stream",
                produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<OrderView> stream(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam String status,
            @RequestParam(defaultValue = "20") int size) {
        if (jwt == null) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED, "Authentication required"
            ));
        }
        return service.streamLimited(
            jwt.getClaimAsString("tenant_id"), status, size
        );
    }
}
~~~

Ví dụ client:

~~~bash
curl --no-buffer \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/orders/stream?status=PAID&size=20"
~~~

Mỗi dòng trả về là một OrderView, không có envelope gồm hasNext. Việc **cursorBatchSize(32)** là gợi ý kích thước batch đọc từ MongoDB, còn **limitRate(32)** điều chỉnh nhu cầu downstream của Reactor; chúng có vai trò khác nhau. Cả hai không thể thay thế điều kiện **Query.limit(size)** làm giới hạn tổng số bản ghi.

Một khác biệt rất quan trọng: với Flux, toán tử **timeout(Duration)** phát lỗi khi **khoảng chờ tín hiệu đầu tiên hoặc giữa hai tín hiệu** vượt ngưỡng; đây không phải deadline tổng thời gian toàn stream. Nếu cần giới hạn thời gian toàn HTTP request, phải thiết kế deadline ở gateway/server hoặc cơ chế tổng thời gian riêng, đồng thời kiểm thử cancellation.

### 9.3. Lỗi khi HTTP body đã bắt đầu

Giả sử server đã gửi 10 dòng NDJSON, sau đó MongoDB mất kết nối khi phát dòng 11. HTTP headers có thể đã được ghi; server không thể quay lại đổi HTTP 200 thành 503 một cách tin cậy. Client có thể nhận stream đứt giữa chừng.

Vì vậy:

- Đối với trang dữ liệu nghiệp vụ cần **all-or-error**, ưu tiên Mono<OrderPage> có giới hạn.
- Với stream dài, định nghĩa giao thức resume/checkpoint rõ ràng; consumer không mặc định mọi stream bị cắt vẫn thành công.
- Không dùng onErrorResume để âm thầm đổi lỗi database thành Flux.empty() hoặc một trang rỗng, vì như vậy che giấu mất dữ liệu.
- Log và metrics phải ghi nhận stream bị hủy, lỗi sau commit và số bản đã phát ra, không chỉ đếm HTTP status.
- Nếu client ngắt kết nối, WebFlux có thể hủy subscription; vẫn cần kiểm tra driver và cursor được giải phóng trong tình huống thực tế.

Nếu dùng NDJSON cho xuất nhiều trang, không thay thế toàn bộ giới hạn bằng một find không có limit. Hãy thiết kế batch hoặc cursor có checkpoint và tổng quota phù hợp với dữ liệu xuất.

## 10. Xử lý lỗi trong reactive pipeline

### 10.1. Ba nhóm lỗi cần phân biệt

| Lỗi | Ví dụ | Chiến lược |
| --- | --- | --- |
| Lỗi yêu cầu | size=10000, cursor thiếu afterId, status không được phép | 400, không gửi query MongoDB |
| Lỗi truy cập | JWT thiếu, tenant_id không được phép | 401/403 trước khi truy vấn |
| Lỗi hạ tầng nhất thời | Không chọn được server, socket/connection pool lỗi | 503 hoặc 504, không lộ hostname/URI |
| Lỗi dữ liệu/mapping | Document thiếu createdAt, kiểu BSON sai | Ghi log đủ để điều tra; không nuốt lỗi thành danh sách rỗng |
| Lỗi nghiệp vụ | Thao tác không được phép theo trạng thái đơn | 4xx phù hợp theo hợp đồng |
| Lỗi ngoài dự kiến | Bug, NullPointerException | 500, có correlation ID để tra log |

Trong phần 6, service dùng **onErrorMap** cho TimeoutException, MongoTimeoutException và DataAccessResourceFailureException. Spring Data có thể dịch một số exception của driver sang loại DataAccessException; cần quan sát loại lỗi thực tế của ứng dụng khi cấu hình mapping và version thay đổi.

Khi một lỗi xảy ra trong pipeline, Reactor phát **onError**, một tín hiệu kết thúc; các toán tử phía sau không tiếp tục phát bản ghi bình thường. Để hiển thị lỗi theo hợp đồng HTTP, có thể dùng ResponseStatusException hoặc một cơ chế @RestControllerAdvice thống nhất.

### 10.2. Vì sao không trả danh sách rỗng khi database lỗi?

Ví dụ không nên triển khai:

~~~java
// Anti-pattern: che giấu lỗi database bằng kết quả hợp lệ rỗng.
return template.find(query, Order.class)
    .collectList()
    .onErrorReturn(List.of());
~~~

Client sẽ hiểu rằng không có đơn hàng nào dù thực tế server không truy cập được MongoDB. Điều này có thể gây sai lệch báo cáo hoặc khiến người dùng thực hiện thao tác bù sai. Danh sách rỗng chỉ hợp lệ nếu truy vấn thành công và không tìm được document.

### 10.3. Retry có kiểm soát

MongoDB Driver có cơ chế **retryable reads/writes** cho một số thao tác đủ điều kiện. Không nên thêm retry tùy tiện ở tầng Reactive vì retry ở HTTP client, gateway, service và driver có thể nhân số attempts.

Trong một read-only pipeline, nếu thật sự cần thử lại sau một số lỗi nhất thời:

~~~java
import java.time.Duration;
import com.mongodb.MongoSocketException;
import reactor.util.retry.Retry;

Retry limitedRetry = Retry.backoff(1, Duration.ofMillis(100))
    .maxBackoff(Duration.ofMillis(300))
    .filter(error -> error instanceof MongoSocketException);
~~~

Đây là **cấu hình chính sách retry** minh họa, chưa gắn vào service chính. Chỉ gắn retryWhen trước timeout toàn thao tác sau khi đã kiểm tra lỗi thực tế (có thể được Spring Data chuyển thành wrapper khác), độ an toàn khi chạy lại, và tổng deadline. Không retry lỗi auth, validation hoặc duplicate key.

Đối với ghi đơn hàng, timeout không chứng minh lệnh chưa thực hiện; phải dùng khóa nghiệp vụ/idempotency và xác minh trạng thái. Reactive MongoDB không tự bảo đảm các side effect bên ngoài như thanh toán hoặc email chỉ chạy một lần.

### 10.4. Timeout ở nhiều tầng

Ví dụ ngân sách giả định của một API có SLO dưới 4 giây:

~~~text
HTTP gateway deadline                 4000 ms
Toàn bộ MongoDB read tại service      3000 ms
Thời gian còn lại cho auth/serialize    1000 ms
~~~

Đây là **ví dụ để thảo luận**, không phải phép cộng bảo đảm. Thời gian authentication, network, queue và serialization biến động; phải đo p95/p99 thực tế và dự phòng phù hợp. Nếu MongoDB Java Driver được cấu hình **timeoutMS** theo CSOT, kiểm tra tác động với Reactors timeout và các option khác, tránh chọn nhiều timeout không nhất quán.

## 11. Kiểm thử tự động bằng Reactor StepVerifier

### 11.1. Kiểm tra giới hạn size + 1 và nextCursor

Ví dụ unit test dùng Mockito để giả lập ReactiveMongoTemplate; test này kiểm chứng logic phân trang, không thay thế MongoDB integration test.

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderReadServiceTest {

    @Mock
    ReactiveMongoTemplate template;

    private OrderReadService service;

    @BeforeEach
    void setUp() {
        service = new OrderReadService(template);
    }

    @Test
    void returnsBoundedPageAndNextCursor() {
        Instant timestamp = Instant.parse("2026-11-18T08:30:00Z");
        Order first = new Order(
            new ObjectId("65350f8453dbe413901c1213"),
            "tenant-A", "PAID", timestamp, 1000L
        );
        Order second = new Order(
            new ObjectId("65350f8453dbe413901c1212"),
            "tenant-A", "PAID", timestamp, 2000L
        );
        Order extra = new Order(
            new ObjectId("65350f8453dbe413901c1211"),
            "tenant-A", "PAID", timestamp, 3000L
        );

        when(template.find(any(Query.class), eq(Order.class)))
            .thenReturn(Flux.just(first, second, extra));

        StepVerifier.create(
                service.findPage("tenant-A", "PAID", 2, null, null))
            .assertNext(page -> {
                assertEquals(2, page.items().size());
                assertTrue(page.hasNext());
                assertEquals(second.id().toHexString(),
                    page.nextCursor().id());
            })
            .verifyComplete();

        ArgumentCaptor<Query> query =
            ArgumentCaptor.forClass(Query.class);
        verify(template).find(query.capture(), eq(Order.class));
        assertEquals(3, query.getValue().getLimit());
    }

    @Test
    void rejectsOversizedPageBeforeQuery() {
        StepVerifier.create(
                service.findPage("tenant-A", "PAID", 101, null, null))
            .expectErrorSatisfies(error ->
                assertInstanceOf(
                    org.springframework.web.server.ResponseStatusException.class,
                    error
                )
            )
            .verify();

        verifyNoInteractions(template);
    }
}
~~~

Trong ví dụ test, dữ liệu mock được đưa theo đúng thứ tự mong muốn để kiểm tra mapping; Mockito **không kiểm chứng MongoDB thực sự dùng index hoặc thực hiện sort**. Điều đó cần kiểm thử tích hợp với database.

### 11.2. Kiểm thử lỗi database và timeout

Các trường hợp nên có:

1. Mock Flux phát MongoTimeoutException và xác minh Mono trả ResponseStatusException có status 503.
2. Mock Flux không bao giờ hoàn thành bằng Flux.never(); dùng **StepVerifier.withVirtualTime** khi kiểm tra Duration timeout để không phải chờ thời gian thật.
3. Trả 0 document và xác nhận items rỗng, hasNext false, nextCursor null.
4. Trả đúng size document và xác nhận không có trang sau.
5. Trả size + 1 document và xác nhận nextCursor lấy từ phần tử cuối **được trả**, không phải phần tử dư.
6. Cursor thiếu một trong hai khóa hoặc ObjectId sai định dạng phải kết thúc 400 trước khi gọi MongoDB.
7. Khi order không có createdAt/id hợp lệ, test phát hiện vấn đề dữ liệu thay vì âm thầm tạo cursor sai.

Lưu ý: với thời gian ảo, publisher và toán tử thời gian phải được khởi tạo theo cách StepVerifier.withVirtualTime điều khiển scheduler đúng; không chỉ bao một Mono đã subscribe ở nơi khác rồi kỳ vọng thời gian ảo có tác dụng.

### 11.3. Integration test với MongoDB thật

Hãy dùng MongoDB test container hoặc replica set thử nghiệm tương thích với driver. Bộ dữ liệu cần có:

- Tenant A và tenant B có các đơn cùng trạng thái.
- Nhiều đơn có **cùng createdAt** nhưng _id khác.
- Đủ đơn để có ít nhất ba trang với size nhỏ.
- Ngày tháng qua ranh giới ngày UTC.
- Trường hợp collection rỗng và trạng thái hợp lệ không có kết quả.

Các phép thử quan trọng:

| Kiểm thử | Bằng chứng cần có |
| --- | --- |
| Bắt đầu từ trang đầu và duyệt hết bằng cursor | Mỗi ID thuộc tenant A xuất hiện đúng một lần trong tập dữ liệu tĩnh |
| Tenant A dùng cursor trỏ vị trí dữ liệu tenant B | Query vẫn không trả document của tenant B |
| Hai order có createdAt giống nhau | Thứ tự _id giảm dần, không bỏ sót khi qua trang |
| Giới hạn size | Mỗi response có tối đa size item; truy vấn lấy tối đa size + 1 |
| Truy vấn có compound index | explain cho thấy index phù hợp và không có blocking sort không cần thiết |
| MongoDB mất kết nối | 503/504 theo nhóm lỗi, không lộ URI/password |
| Client hủy stream NDJSON | Cancellation được chuyển xuống driver và tài nguyên được giải phóng |
| 50–100 request đồng thời | Heap, event-loop, pool wait và MongoDB CPU/I/O trong ngưỡng chấp nhận |
| JWT hết hạn/không có tenant claim | Từ chối trước khi query |

Kiểm thử dữ liệu được cập nhật khi đang phân trang phải ghi rõ hợp đồng nhất quán mong muốn. Nếu cần snapshot bất biến, keyset pagination một mình chưa đủ; cần cơ chế snapshot/watermark hoặc thiết kế dữ liệu phù hợp. Không mở transaction kéo dài qua nhiều lần HTTP request chỉ để giữ một trang danh sách không đổi.

## 12. Metrics và truy vết sự cố

### 12.1. Những chỉ số nên có

| Nhóm | Metrics | Câu hỏi |
| --- | --- | --- |
| HTTP | p50/p95/p99 latency, 4xx/5xx, request cancellation | Người dùng chịu ảnh hưởng bao nhiêu? |
| MongoDB command | duration, lỗi command, số command mỗi request | Query chậm hay retry/fan-out quá nhiều? |
| Connection pool | checked-out connections, checkout wait, checkout timeout | Pool có đang nghẽn không? |
| Server | CPU, I/O, connections, slow query, replication lag | Database còn năng lực phục vụ không? |
| Reactive | số subscription đang hoạt động, buffer, cancellation | Có stream chậm hoặc publisher không dừng? |
| Giới hạn ứng dụng | request bị rate limit, size bị từ chối, timeout | Các cơ chế bảo vệ có thực sự hoạt động không? |

MongoDB Java Driver cung cấp **ConnectionPoolListener** và **CommandListener**; có thể tích hợp hệ thống metrics/observability như Micrometer tùy stack. Không dùng nguyên tenantId, orderId hoặc JWT làm **metric tag có cardinality cao**. Không xuất raw query chứa dữ liệu cá nhân hoặc MongoDB URI chứa secret vào log.

### 12.2. Phân tích ví dụ quá tải

Giả sử quan sát được:

~~~text
HTTP p95:                2900 ms
MongoDB command p95:      170 ms
Pool checkout p95:       1800 ms
Checked-out connections: 40 / 40
MongoDB CPU:              40%
~~~

Đây là số liệu minh họa. Độ trễ chủ yếu nằm ở việc chờ connection; kiểm tra cursor/transaction chưa đóng, số subscription đồng thời, fan-out và headroom của MongoDB. Sau đó mới đánh giá tăng maxPoolSize từng bước.

Ngược lại:

~~~text
HTTP p95:                3400 ms
MongoDB command p95:     3000 ms
Pool checkout p95:         15 ms
MongoDB CPU:              95%
~~~

Nút thắt thiên về query/server. Tăng pool có thể làm server quá tải hơn. Hãy xem index, filter, sort, explain, độ lớn document và lượng request, rồi giảm concurrency/rate limit nếu cần.

### 12.3. Logging đủ để điều tra nhưng không rò bí mật

Một log vận hành cho phép:

~~~text
traceId=... operation=order_page status=timeout
size=20 elapsedMs=3000 queryShape=tenant_status_after_createdAt
~~~

Không đưa password, access token, toàn URI, raw document hoặc danh sách ID khách hàng vào log. Nếu cần hỗ trợ điều tra một tenant cụ thể, dùng cơ chế tương quan có kiểm soát và retention phù hợp, không tạo nhãn metric chứa giá trị tenant không giới hạn.

## 13. Các sai lầm dễ mắc khi làm capstone

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng Mono.just(mongoTemplate.find(...)) | Lệnh blocking đã chạy trước khi subscribe | Dùng ReactiveMongoTemplate và driver reactive |
| Gọi block() trong WebFlux controller | Chặn event-loop, giảm khả năng phục vụ | Trả Mono/Flux tới framework |
| Trả Flux vô hạn rồi collectList() | Heap tăng không giới hạn | Đặt Query.limit trước khi collect |
| Chỉ giới hạn limitRate | Tổng số document vẫn có thể vô hạn | Giới hạn query và quota ở nguồn |
| Dùng skip rất lớn | Trang sâu tốn nhiều công bỏ qua | Dùng keyset theo sort có khóa duy nhất |
| Chỉ dùng createdAt làm cursor | Mất document cùng timestamp | Thêm _id và điều kiện OR đúng |
| Lấy tenantId trực tiếp từ query parameter | Nguy cơ truy cập chéo tenant | Lấy từ danh tính xác thực/ủy quyền |
| Dùng onErrorReturn(empty page) cho mọi lỗi | Client hiểu database lỗi là không có đơn | Chuyển lỗi đúng loại HTTP |
| Retry mọi lỗi bằng retryWhen không giới hạn | Retry storm, chiếm pool, dễ trùng side effect | Phân loại lỗi, giới hạn attempts và deadline |
| Tăng maxPoolSize thay vì sửa query | MongoDB quá tải hơn | Đo command latency, explain và CPU |
| Dùng ResponseEntity sau khi NDJSON đã gửi nửa body | Không thể đổi status đã commit | Thiết kế giao thức lỗi/resume hoặc dùng trang bounded |
| Không kiểm thử cancellation | Cursor/connection có thể bị giữ lâu | Kiểm thử ngắt client, đo pool release |
| Biến mọi lỗi thành 503 | Che bug/mapping errors | Chỉ map lỗi hạ tầng được xác định |

## 14. Bài thực hành và tiêu chí nghiệm thu

### 14.1. Công việc cần hoàn thành

Từ một dự án Spring Boot dùng WebFlux và Spring Data MongoDB Reactive:

1. **Tạo dữ liệu:** ít nhất hai tenant, ba trạng thái đơn và nhiều document có createdAt giống nhau.
2. **Tạo index:** tenantId + status + createdAt DESC + _id DESC; xác nhận bằng getIndexes/explain.
3. **Xây API:** /api/orders nhận status, size và cặp afterCreatedAt/afterId; tenant lấy từ JWT đã được xác thực.
4. **Giới hạn:** size từ 1 đến 100, query lấy tối đa size + 1, một trang chỉ giữ tối đa 101 document.
5. **Xử lý lỗi:** 400 cho tham số, 401/403 cho danh tính/tenant, 503 cho lỗi tài nguyên database, 504 cho deadline ứng dụng.
6. **Kiểm thử:** viết StepVerifier và integration tests cho trang, cursor, trùng timestamp, chéo tenant, timeout và dữ liệu không tồn tại.
7. **Stream tùy chọn:** thêm NDJSON có limit, cursorBatchSize, limitRate và thử client disconnect.
8. **Giới hạn tải:** cấu hình MongoClient pool phù hợp, thử 10/50/100 request đồng thời và ghi p95/p99, checkout wait, command duration.
9. **Đánh giá kết quả:** so sánh với phiên bản dùng skip và phiên bản không có index, kiểm tra cả tính đúng dữ liệu.

### 14.2. Điều kiện PASS

| Điều kiện | Kỳ vọng |
| --- | --- |
| Không có truy vấn MongoDB khi request sai | Unit test verifyNoInteractions hoặc kiểm tra command metrics |
| Không lộ dữ liệu tenant khác | Tất cả response chỉ chứa document đúng tenant |
| Thứ tự ổn định trên tập dữ liệu tĩnh | Duyệt mọi trang không trùng/thiếu ID |
| Bộ nhớ có giới hạn | Không có collectList trên Flux không bị giới hạn |
| Lỗi rõ ràng | Timeout/DB failure không trở thành trang rỗng 200 |
| Không block event-loop | Không có block()/sleep/driver blocking trong WebFlux handler |
| Thời gian chờ hữu hạn | Request không treo vô hạn khi backend không phản hồi |
| Không nhân tải do retry | Không có vòng retry không giới hạn; đã xét retry mặc định của driver |
| Pool phù hợp workload | Checkout wait, MongoDB CPU/I/O và HTTP SLO đạt ngưỡng do nhóm đề ra |
| Quan sát được khi lỗi | Có metrics/log an toàn và correlation ID để điều tra |

### 14.3. Câu hỏi tự đánh giá

- Vì sao Mono<OrderPage> vẫn là một thiết kế reactive dù có collectList?
- Query.limit(size + 1) giải quyết bài toán nào mà limitRate không giải quyết?
- Vì sao MongoDB index cần chứa cả createdAt và _id với chiều sort phù hợp?
- Tại sao một response NDJSON đã gửi một phần không thể luôn trả lại mã 503 khi gặp lỗi?
- Khi Reactor timeout phát lỗi, có thể khẳng định MongoDB đã dừng xử lý mọi command không?
- maxPoolSize=40 trên tám pod có giới hạn tổng cluster ở 40 connections không?
- Vì sao cần JWT tenant claim đã được xác minh và truy vấn kèm tenantId?
- Khi nào retry có thể làm phát sinh đơn hàng/thanh toán trùng?

Một luồng reactive đáng tin cậy được xây dựng bằng **truy vấn đúng phạm vi, số lượng kết quả có giới hạn, quy tắc phân trang ổn định, timeout phù hợp, xử lý lỗi minh bạch và bộ pool được đo theo tải**. Cấu trúc Mono/Flux chỉ là một phần; tính đúng đắn nghiệp vụ và hành vi vận hành mới quyết định ứng dụng có thể triển khai an toàn hay không.

## 15. Tài liệu tham khảo

- [Spring Data MongoDB – Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/reactive-mongo.html): cấu hình và cách dùng MongoDB Reactive Driver.
- [Spring Data MongoDB – Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): Query, Criteria, sort, limit và timeout.
- [Spring Data MongoDB – Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html): repository reactive và truy cập dữ liệu.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): controller reactive, xử lý HTTP và streaming.
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, backpressure, cancellation, timeout và retry.
- [Reactor Test – StepVerifier](https://projectreactor.io/docs/test/release/reference/): kiểm thử publisher và virtual time.
- [MongoDB – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): thứ tự khóa và hiệu năng query.
- [MongoDB – cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/): hạn chế của offset pagination.
- [MongoDB Java Reactive Streams Driver](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/): driver reactive, cấu hình và kết nối.
- [MongoDB – Connection Pool Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): maxPoolSize, minPoolSize, maxConnecting và timeout.
