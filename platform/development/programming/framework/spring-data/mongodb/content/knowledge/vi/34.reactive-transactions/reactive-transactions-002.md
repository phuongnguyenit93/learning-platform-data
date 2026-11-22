# @Transactional trên phương thức trả về Publisher

> **Chương:** Giao dịch reactive  
> **Module:** `SPRING_DATA_MONGODB`

Trong Spring Data MongoDB, một service có thể trả về `Mono<T>` hoặc `Flux<T>` thay vì thực thi truy vấn và trả giá trị ngay. Khi cần ghi nhiều document một cách nguyên tử, developer thường thêm `@Transactional` vào phương thức reactive. Tuy nhiên, **chỉ thêm annotation không đảm bảo giao dịch sẽ hoạt động**: ứng dụng cần một `ReactiveMongoTransactionManager` đúng loại, các thao tác MongoDB phải chạy trong **cùng chuỗi reactive và Reactor Context**, và Publisher phải thật sự được **subscribe**.

Khác với transaction imperative thường gắn trạng thái vào `ThreadLocal`, Spring quản lý **reactive transaction** qua **Reactor Context**. Vì vậy các thao tác `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository` được compose trong Publisher mới có thể cùng tham gia session/transaction. Một lời gọi `subscribe()` tách rời, một thao tác blocking hoặc một transaction manager sai loại có thể làm mất tính nguyên tử mà code trông bề ngoài vẫn đúng.

Bài thuộc module `SPRING_DATA_MONGODB`: kết nối và ánh xạ document, thao tác MongoDB qua repository hoặc template, thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu. Chủ đề ở đây là **cách dùng `@Transactional` chính xác với các phương thức trả về Publisher**, không phải chỉ là giới thiệu cú pháp Reactor.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `@Transactional` reactive gắn với **subscription**, không tự commit ngay khi method trả về một `Mono`/`Flux`.
2. Phân biệt `ReactiveMongoTransactionManager` với `MongoTransactionManager` và Reactor Context với `ThreadLocal`.
3. Cấu hình transaction manager cho `ReactiveMongoTemplate` và các repository reactive dùng chung `ReactiveMongoDatabaseFactory`.
4. Viết một service trả `Mono<ReservationReceipt>`, thực hiện hai lệnh ghi MongoDB **theo thứ tự** và rollback khi lỗi.
5. Nhận biết các bẫy `subscribe()` bên trong service, `block()`, self-invocation, `onErrorResume` nuốt lỗi, xử lý trên nhiều scheduler và truy cập nhiều MongoClients.
6. Giải thích commit/rollback khi Publisher complete, error hoặc cancel; những giới hạn của `Flux` dài và `take(1)`.
7. So sánh `@Transactional` với `TransactionalOperator`, xác định ranh giới propagation và retry an toàn.
8. Viết kiểm thử tích hợp bằng `StepVerifier` trên MongoDB replica set, kiểm tra trạng thái BSON sau commit/rollback và các trường hợp cạnh tranh.

## 2. Publisher là kế hoạch thực thi, không phải kết quả đã ghi

Trong hệ reactive, `Publisher` là một nguồn phát tín hiệu `onNext`, `onComplete` hoặc `onError` khi có subscriber. Với Reactor, hai loại quen thuộc:

- `Mono<T>`: phát tối đa **một** giá trị `T` rồi kết thúc, hoặc kết thúc rỗng/lỗi.
- `Flux<T>`: phát **0..N** giá trị `T` rồi kết thúc, hoặc báo lỗi.

Code:

```java
Mono<OrderDocument> saved = reactiveMongoTemplate
    .insert(new OrderDocument("ORD-101", "TENANT-A", "NEW"));
```

thông thường **chưa gửi lệnh insert tới MongoDB** tại thời điểm Java vừa xây Publisher `saved`. I/O thực tế xảy ra khi Publisher được subscribe:

```java
saved.subscribe();
```

Nhưng câu trên chỉ dùng để giải thích nguyên tắc subscription; **không nên gọi `subscribe()` bên trong service nghiệp vụ trả Publisher**. Hãy trả Publisher để WebFlux, test `StepVerifier` hoặc caller điều phối subscription và lỗi đúng cách.

### 2.1. Ba thời điểm khác nhau

```text
Caller calls reserve(cmd)
      |
      v
Java method assembles Publisher
      |    (usually no MongoDB I/O yet)
      v
Caller receives Mono<ReservationReceipt>
      |
      +-- no subscription ------> no reactive database work
      |
      +-- subscription
              |
              v
       Reactive tx starts
              |
              v
       MongoDB operations execute
              |
          +---+----+
          |        |
       complete   error/cancel
          |        |
          v        v
        commit   rollback/cleanup
```

Thời điểm bắt đầu/kết thúc thực tế còn phụ thuộc interceptor, operator và lifecycle của Publisher. **Subscription là mốc điều phối reactive transaction**; completion của transactional Publisher phải đi qua transaction manager để commit thành công thì caller mới nên báo nghiệp vụ đã hoàn tất.

### 2.2. Code chạy ở lúc assembly vẫn có thể có side effect

```java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<String> createOrder() {
    System.out.println("Method invoked");
    return template.insert(new OrderDocument(
        "ORD-101", "TENANT-A", "NEW"))
        .map(OrderDocument::id);
}
```

`System.out.println(...)` là Java imperative, có thể chạy khi method **được gọi để tạo Publisher**, chứ không đợi tới subscription/transaction. Không đặt side effect không rollback được ở đó rồi cho rằng nó nằm trong transaction.

Khi cần trì hoãn cả phần tạo dữ liệu tới lúc subscribe:

```java
return Mono.defer(() -> {
    String id = java.util.UUID.randomUUID().toString();
    return template.insert(
            new OrderDocument(id, "TENANT-A", "NEW"))
        .map(OrderDocument::id);
});
```

Tuy nhiên, UUID mới tạo **mỗi lần subscribe** có thể phá idempotency nếu caller retry. Với nghiệp vụ nhạy cảm, giữ **operation ID ổn định từ yêu cầu** thay vì tạo ID mới trong mỗi attempt.

## 3. Reactive transaction dùng Reactor Context, không dùng ThreadLocal như imperative

Spring transaction imperative thường lấy transaction context đang gắn vào luồng gọi. Reactive execution có thể đổi thread qua `publishOn`/`subscribeOn` mà vẫn là một logical stream, vì vậy `ThreadLocal` không đủ để truyền transaction.

**Reactive transaction manager** truyền thông tin transaction/session qua `Reactor Context`. Spring Data MongoDB dùng context đó để liên kết các thao tác reactive với `ClientSession` phù hợp.

```text
HTTP request
  |
  v
@Transactional reactive proxy
  |
  +-- Reactor Context contains transactional state
  |
  +-- ReactiveMongoTemplate.updateFirst(...)
  |       -> joins transaction/session
  |
  +-- ReactiveMongoTemplate.insert(...)
  |       -> joins same transaction/session
  |
  +-- Publisher completion -> manager commits
  +-- Publisher error       -> manager rolls back
```

### 3.1. Chuyển scheduler không nhất thiết làm mất Reactor Context

Một hiểu nhầm là chỉ cần `publishOn(Schedulers.boundedElastic())` là giao dịch chắc chắn bị mất. Reactor Context có thể **được truyền qua các operator hỗ trợ đúng cách** dù có thay đổi thread.

Lỗi thực sự thường đến từ việc **tách khỏi chuỗi Publisher** (tự `subscribe()`, dùng cơ chế async ngoài Reactor, tạo Publisher mới không kết nối với context), dùng **client/template khác session**, hoặc gọi blocking API mà transaction manager reactive không điều phối.

### 3.2. Một Publisher khác không tự cùng transaction

```java
// PHẢN VÍ DỤ: nhánh bị detach.
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> process() {
    template.insert(new AuditDocument("A1"))
        .subscribe(); // subscription độc lập, không join chắc chắn

    return template.insert(new OrderDocument(
        "O1", "TENANT-A", "NEW")).then();
}
```

Một lệnh insert audit bị `subscribe()` ngay lập tức có thể chạy ngoài transaction của Publisher trả về, hoặc có lifetime độc lập. Khi order insert fail, audit vẫn có thể đã được ghi.

Cách đúng là compose:

```java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> process() {
    return template.insert(new AuditDocument("A1"))
        .then(template.insert(new OrderDocument(
            "O1", "TENANT-A", "NEW")))
        .then();
}
```

Khi hai thao tác dùng cùng transactional factory và chuỗi Publisher được subscribe đúng, chúng tham gia cùng giao dịch.

## 4. Cần những điều kiện nào để @Transactional reactive có hiệu lực?

| Điều kiện | Nếu sai sẽ gặp gì? |
| --- | --- |
| Có MongoDB deployment hỗ trợ transaction (replica set hoặc sharded cluster được hỗ trợ) | Standalone thường không hỗ trợ multi-document transaction |
| Có `ReactiveMongoTransactionManager` được cấu hình | Reactive method có thể không được quản lý đúng transaction |
| Method trả `Publisher`/reactive type phù hợp (`Mono`/`Flux`) | Không thể áp reactive transaction giống lời gọi synchronous |
| Lời gọi đi qua Spring transactional proxy | Self-invocation có thể bỏ qua interception |
| `ReactiveMongoTemplate`/repository cùng `ReactiveMongoDatabaseFactory`/session binding | Lệnh ở factory khác có thể nằm ngoài transaction |
| Caller subscribe và dùng terminal signal | Không subscribe thì pipeline không chạy; error/cancel cần được quan sát |
| Các lệnh MongoDB nằm trong cùng reactive chain | Detached subscriptions có thể commit/rollback độc lập |
| Trình tự thao tác trong cùng session được kiểm soát | Parallel DB operations trong transaction có thể không được hỗ trợ an toàn |
| Không xử lý lỗi theo cách biến failure thành complete trước transaction boundary | Transaction có thể commit thay vì rollback |

**Lưu ý:** `@Transactional` không bảo đảm mọi thao tác mạng nằm trong transaction. HTTP call, Kafka publish, gửi email, filesystem write và database khác không tự tham gia MongoDB transaction chỉ vì chúng xuất hiện trong cùng Reactor chain.

## 5. Cấu hình ReactiveMongoTransactionManager

File `ReactiveMongoTransactionConfiguration.java`:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveMongoTransactionConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
```

Trong ví dụ, `factory` do ứng dụng/Spring Boot cung cấp theo cấu hình reactive MongoDB. Khi có nhiều factories, phải dùng `@Qualifier` và manager tương ứng; không để repository ở factory A trong khi transaction manager dùng factory B.

### 5.1. Reactive và imperative transaction managers khác nhau

| Thành phần | Imperative | Reactive |
| --- | --- | --- |
| Transaction manager | `MongoTransactionManager` | `ReactiveMongoTransactionManager` |
| Template | `MongoTemplate` | `ReactiveMongoTemplate` |
| Repository | `MongoRepository` | `ReactiveMongoRepository` |
| Kiểu return chính | Giá trị/`void` | `Mono<T>`, `Flux<T>`, các Publisher hỗ trợ |
| Context phổ biến | Thread-bound transaction | Reactor Context-bound transaction |
| Cách thực thi | Phương thức chạy tức thì | Publisher thực thi khi subscribe |
| Cách test | Gọi method + assert | `StepVerifier`/subscribe đến terminal signal |

Nếu một ứng dụng khai báo **cả hai transaction managers**, phải xác định rõ manager phù hợp cho từng đường gọi:

```java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserve(...) {
    // ReactiveMongoTemplate / ReactiveMongoRepository only
}
```

Không dùng `MongoTransactionManager` cho một reactive pipeline rồi mặc định nó quản lý được session theo Reactor Context. Cũng không gọi `MongoTemplate` blocking trong callback reactive để mong nó tự tham gia transaction reactive.

### 5.2. @EnableTransactionManagement và cấu hình Boot

Trong ứng dụng Spring có transaction infrastructure được kích hoạt (thường qua cấu hình/autoconfiguration phù hợp), Spring AOP tạo interceptor cho `@Transactional`. Khi triển khai thủ công, có thể cần `@EnableTransactionManagement` hoặc cấu hình tương ứng.

Tuy nhiên **không tự suy đoán** rằng chỉ thêm annotation và bean manager sẽ luôn chạy đúng trong mọi phiên bản Spring Boot. Kiểm tra context khởi tạo, bean tên gì, proxy được tạo chưa, loại manager nào được chọn và một integration test có thật sự rollback hai ghi MongoDB khi lỗi không.

### 5.3. URI và transaction deployment

Một MongoDB replica set thử nghiệm có URI dạng:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0
```

Các host là ví dụ. Để transaction thực thi, cluster phải hỗ trợ session, bầu primary và cấu hình phù hợp. Khi triển khai trên MongoDB Atlas/managed cluster, dùng connection URI, TLS và credentials chính thức của môi trường. Không mặc định một MongoDB chạy standalone hoặc một mock server đủ cho bài kiểm thử multi-document transaction.

## 6. Tình huống xuyên suốt: đặt chỗ và trừ tồn kho

Một dịch vụ bán hàng cần đặt trước một số lượng sản phẩm:

1. Tìm stock record theo `tenantId` và `stockId`, chỉ trừ nếu `available >= quantity`.
2. Lưu một reservation với `operationId` ổn định.
3. Nếu cả hai thành công, commit; nếu không, không để tồn kho bị trừ mà reservation không tồn tại.

Ví dụ:

```javascript
// Collection stock_items
{
  _id: "STOCK-101",
  tenantId: "TENANT-A",
  available: NumberLong(10)
}

// Collection reservations sau khi đặt thành công 3 sản phẩm
{
  _id: "RES-001",
  tenantId: "TENANT-A",
  stockId: "STOCK-101",
  quantity: NumberLong(3)
}
```

Kết quả mong đợi: stock còn `7` và tồn tại một reservation `RES-001`. Nếu insert reservation gặp duplicate key hoặc lỗi server, update stock phải được rollback trong cùng transaction.

### 6.1. Entity và DTO

File `StockDocument.java`:

```java
package com.example.shop.reservation;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "stock_items")
public record StockDocument(
    @Id String id,
    String tenantId,
    long available
) {}
```

File `ReservationDocument.java`:

```java
package com.example.shop.reservation;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "reservations")
public record ReservationDocument(
    @Id String id,
    String tenantId,
    String stockId,
    long quantity
) {}
```

File `ReserveCommand.java`:

```java
package com.example.shop.reservation;

public record ReserveCommand(
    String tenantId,
    String operationId,
    String stockId,
    long quantity
) {}
```

File `ReservationReceipt.java`:

```java
package com.example.shop.reservation;

public record ReservationReceipt(
    String operationId,
    String state
) {}
```

File `InsufficientStockException.java`:

```java
package com.example.shop.reservation;

public final class InsufficientStockException
        extends RuntimeException {
    public InsufficientStockException() {
        super("Stock không tồn tại hoặc không đủ số lượng");
    }
}
```

Giả định `tenantId` được suy ra hoặc xác minh bởi authentication/authorization, không tin giá trị tùy ý do client nhập. `operationId` là ID business ổn định để tránh việc retry cả HTTP request tạo một reservation hoàn toàn mới.

### 6.2. Service với @Transactional trả về Mono

File `ReservationService.java`:

```java
package com.example.shop.reservation;

import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReservationService {

    private final ReactiveMongoTemplate template;

    public ReservationService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager")
    public Mono<ReservationReceipt> reserve(
            ReserveCommand command) {

        return Mono.defer(() -> {
            validate(command);

            Query stockQuery = Query.query(
                Criteria.where("_id").is(command.stockId())
                    .and("tenantId").is(command.tenantId())
                    .and("available").gte(command.quantity()));

            Update decrement = new Update()
                .inc("available", -command.quantity());

            return template.updateFirst(
                    stockQuery, decrement, StockDocument.class)
                .flatMap(result -> {
                    if (result.getModifiedCount() != 1) {
                        return Mono.error(
                            new InsufficientStockException());
                    }

                    ReservationDocument reservation =
                        new ReservationDocument(
                            command.operationId(),
                            command.tenantId(),
                            command.stockId(),
                            command.quantity());

                    return template.insert(reservation)
                        .map(saved -> new ReservationReceipt(
                            saved.id(), "RESERVED"));
                });
        });
    }

    private static void validate(ReserveCommand command) {
        if (command == null
                || command.tenantId() == null
                || command.tenantId().isBlank()
                || command.operationId() == null
                || command.operationId().isBlank()
                || command.stockId() == null
                || command.stockId().isBlank()
                || command.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Yêu cầu đặt chỗ không hợp lệ");
        }
    }
}
```

Phương thức **trả về `Mono<ReservationReceipt>`** và được Spring transactional interceptor bao quanh. Các lệnh reactive MongoDB được compose trong một pipeline, sử dụng cùng `ReactiveMongoTemplate`/factory. Không có `subscribe()` hay `block()` bên trong.

### 6.3. Phân tích từng bước

| Bước | Lệnh | Nếu lỗi |
| --- | --- | --- |
| 1 | `Mono.defer` trì hoãn validate/khởi tạo query tới subscribe | `IllegalArgumentException` phát qua error signal, không tạo write |
| 2 | `updateFirst` trừ `available` với điều kiện đủ hàng và đúng tenant | MongoDB error làm Publisher lỗi |
| 3 | Kiểm tra `modifiedCount` | Không đủ hàng → `Mono.error`, transaction rollback |
| 4 | `insert` reservation với ID ổn định | Duplicate key/server error → rollback cả update stock |
| 5 | `map` tạo `ReservationReceipt` | Giá trị kết quả chỉ có ý nghĩa thành công sau khi transaction commit |

`flatMap` ở đây chỉ gọi insert **sau** khi `updateFirst` phát kết quả; không tạo hai thao tác DB chạy song song trong cùng session. Điều đó phù hợp với giới hạn thực thi transaction của MongoDB reactive driver.

### 6.4. Vì sao dùng điều kiện tại update?

Không nên thiết kế:

```java
// PHẢN VÍ DỤ ý tưởng: read available rồi update vô điều kiện.
template.findById(stockId, StockDocument.class)
    .flatMap(stock -> template.updateFirst(
        Query.query(Criteria.where("_id").is(stockId)),
        new Update().inc("available", -quantity),
        StockDocument.class));
```

Đoạn này chỉ minh họa một pattern sai và không phải phương thức hoàn chỉnh. Trong hệ thống có cập nhật cạnh tranh, kiểm tra `available >= quantity` **ngay trong lệnh update** an toàn hơn so với chỉ đọc rồi dùng một update không có precondition. Transaction vẫn có thể gặp write conflict và cần retry có kiểm soát, nhưng không vì vậy mà bỏ điều kiện kinh doanh.

### 6.5. Mẫu kết quả khi thành công hoặc bị lỗi

```text
Subscribe reserve(RES-001, qty=3)
    |
    v
BEGIN transaction
    |
    +-- stock_items: available 10 -> 7
    |
    +-- reservations: insert RES-001
    |
    v
COMMIT
    |
    v
Mono emits ReservationReceipt("RES-001", "RESERVED")
and successfully completes
```

Khi insert `RES-001` thất bại (ví dụ duplicate key):

```text
BEGIN transaction
    |
    +-- stock_items: available 10 -> 7 (chưa commit)
    |
    +-- reservations: duplicate key
    |
    v
ERROR -> ROLLBACK
    |
    v
stock_items.available stays 10
reservation insert from failed attempt is not committed
```

Với reactive transaction, transaction manager phát ra tín hiệu error khi không thể hoàn tất. **Đừng xây logic business thành công chỉ dựa trên việc `map(saved -> receipt)` đã chạy**; commit sau đó vẫn có thể thất bại hoặc chưa xác định kết quả.

## 7. Subscription là ranh giới: ai gọi và ai nhận lỗi?

### 7.1. WebFlux controller trả trực tiếp Mono

```java
package com.example.shop.reservation;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReservationController {

    private final ReservationService reservationService;

    public ReservationController(
            ReservationService reservationService) {
        this.reservationService = reservationService;
    }

    @PostMapping("/reservations")
    public Mono<ResponseEntity<ReservationReceipt>> reserve(
            @RequestBody ReserveCommand request) {

        // Tenant và quyền user cần được xác minh
        // bằng security layer trước khi gọi service.
        return reservationService.reserve(request)
            .map(ResponseEntity::ok);
    }
}
```

WebFlux subscribe vào Publisher phục vụ response. Controller không tự `subscribe()` vì như vậy dễ tạo subscription thứ hai và đánh mất propagation lỗi/response.

### 7.2. Unit/integration test phải subscribe

```java
StepVerifier.create(
        reservationService.reserve(
            new ReserveCommand(
                "TENANT-A", "RES-001", "STOCK-101", 3)))
    .expectNextMatches(receipt ->
        receipt.operationId().equals("RES-001")
            && receipt.state().equals("RESERVED"))
    .verifyComplete();
```

`verifyComplete()` giúp test chờ **completion**, không chỉ một giá trị `onNext`. Nếu commit failure được phát qua signal sau khi body tạo receipt, test vẫn có cơ hội bắt được lỗi; chỉ `expectNext` rồi `thenCancel()` là không đủ để chứng minh commit thành công.

### 7.3. Không có subscribe thì không có giao dịch hoàn tất

```java
// Phản ví dụ: xây Mono rồi bỏ quên.
Mono<ReservationReceipt> pipeline =
    reservationService.reserve(command);

// Không trả, không subscribe, không StepVerifier.
// Không nên mong dữ liệu đã được ghi.
```

Các test kiểu `assertThat(pipeline).isNotNull()` chỉ xác minh tạo được object Publisher, **không xác minh** lệnh MongoDB, session, commit hoặc rollback.

### 7.4. Nhiều subscriptions có thể thực hiện lại nghiệp vụ

Đa số Publisher do ReactiveMongoTemplate tạo là **cold**: mỗi subscription có thể tái thực thi thao tác.

```java
Mono<ReservationReceipt> publisher =
    reservationService.reserve(command);

// Nếu subscribe publisher này hai lần thì có hai attempt nghiệp vụ.
// Lần sau có thể gặp duplicate operationId.
```

Không dùng `cache()` trên một `Mono` như cơ chế idempotency production. Cache ở JVM không tồn tại xuyên instance/restart và không thay thế unique index/operationId. Với API đặt chỗ, phải có **idempotency key ổn định** và xử lý duplicate theo contract.

### 7.5. @Transactional không tự chạy với self-invocation

```java
@Service
public class ReservationFacade {

    public Mono<ReservationReceipt> entry(ReserveCommand cmd) {
        return reserveInternal(cmd); // lời gọi nội bộ qua this
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager")
    public Mono<ReservationReceipt> reserveInternal(
            ReserveCommand cmd) {
        // ...
    }
}
```

Trong cơ chế proxy-based `@Transactional` phổ biến, lời gọi nội bộ không đi qua transaction interceptor, nên annotation trên `reserveInternal` có thể **không có tác dụng**. Nên đặt method transaction ở một bean khác được Spring inject, và gọi thông qua bean proxy, hoặc dùng `TransactionalOperator` tường minh trong cùng class khi phù hợp.

Không sửa bằng cách tự gọi `this.reserveInternal(...)` rồi mong vì return type là `Mono` mà framework tự phát hiện transaction.

## 8. Complete, error và cancel: điều gì khiến transaction commit hoặc rollback?

Một reactive transaction không nhìn vào tên method “reserve” hay “delete” để quyết định kết quả. Nó quản lý transaction lifecycle dựa trên **terminal signals của Publisher** và **rollback rules**.

| Tín hiệu từ transactional Publisher | Hành vi cần hiểu |
| --- | --- |
| `onComplete` sau khi tất cả thao tác hợp lệ | Manager cố **commit** transaction |
| `Mono.empty()`/`Flux.empty()` hoàn tất bình thường | Vẫn là **completion**, không tự có nghĩa rollback |
| `onError` với RuntimeException/Error theo rollback rule mặc định | Manager **rollback/abort** transaction |
| `onError` với checked exception | Phụ thuộc rollback rule; phải kiểm tra/cấu hình `rollbackFor` khi cần |
| `cancel` từ subscriber | Với Spring reactive transaction hiện đại, cancellation thường dẫn tới **rollback** |
| Commit báo lỗi hoặc outcome chưa rõ | Không được báo business success chỉ vì body đã phát `onNext` |

**Chú ý:** Spring transaction có khái niệm **rollback rules**. Trong cấu hình thông dụng, unchecked exception và `Error` gây rollback theo mặc định; checked exception không được tự động coi là rollback ở mọi trường hợp. Nếu publisher phát một checked exception có ý nghĩa rollback, cần cấu hình rõ `@Transactional(rollbackFor=...)` hoặc chuyển thành một unchecked domain exception có chủ đích.

### 8.1. Lỗi đúng: để exception đi ra tới transaction boundary

Trong `ReservationService`, khi không đủ stock:

```java
if (result.getModifiedCount() != 1) {
    return Mono.error(new InsufficientStockException());
}
```

`InsufficientStockException` mở rộng `RuntimeException`. Khi signal đó đi qua transaction interceptor, transaction được rollback theo rule mặc định. Nếu trước đó có lệnh MongoDB khác trong cùng transaction, nó cũng không được commit riêng.

### 8.2. Bẫy onErrorResume bên trong method @Transactional

Phản ví dụ:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserveWrong(
        ReserveCommand command) {

    return updateStock(command)
        .then(insertReservation(command))
        .onErrorResume(error ->
            Mono.just(new ReservationReceipt(
                command.operationId(), "IGNORED_ERROR")));
}
```

Đây là pseudocode Java ở mức method (giả định `updateStock` trả `Mono<?>` và `insertReservation` trả `Mono<ReservationReceipt>`). Nếu insert reservation lỗi sau khi stock đã giảm, `onErrorResume` chuyển error thành một completion bình thường **trước khi transaction manager nhìn thấy**, nên transaction có thể **commit phần giảm stock**.

**Sửa:** nếu lỗi phải làm rollback, giữ error signal đi xuyên qua transactional boundary:

```java
return updateStock(command)
    .then(insertReservation(command))
    .onErrorMap(error ->
        new ReservationFailedException(
            "Không thể giữ hàng", error));
```

Trong đó `ReservationFailedException` là một `RuntimeException` do dự án định nghĩa. `onErrorMap` đổi loại exception nhưng vẫn giữ **error signal**, cho phép transaction rollback theo default rule.

### 8.3. Muốn trả fallback cho API thì đặt ngoài transaction

Một facade/controller ở ngoài proxy có thể chuyển lỗi thành response phù hợp:

```java
public Mono<ReservationResponse> tryReserve(
        ReserveCommand command) {

    return reservationService.reserve(command)
        .map(receipt ->
            new ReservationResponse(true, receipt.operationId()))
        .onErrorResume(InsufficientStockException.class,
            ex -> Mono.just(
                new ReservationResponse(false, null)));
}
```

Ở ví dụ này, `ReservationResponse` là DTO minh họa. Quan trọng là `reservationService.reserve(...)` được gọi **qua bean proxy**; recovery ở **ngoài** transactional Publisher nên error đã đi qua transaction interceptor để rollback trước khi facade biến thành response.

Đừng chuyển mọi lỗi (nhất là commit outcome unknown) thành `false` một cách máy móc. Một lỗi commit chưa xác định cần trạng thái chờ đối soát, không phải báo chắc chắn “chưa ghi”.

### 8.4. Mono.empty không có nghĩa rollback

```java
return template.updateFirst(query, update, StockDocument.class)
    .flatMap(result -> {
        if (result.getModifiedCount() == 0) {
            return Mono.empty();
        }
        return template.insert(reservation);
    });
```

Nếu `Mono.empty()` được trả về, transactional Publisher hoàn tất bình thường và manager có thể **commit** bất kỳ lệnh nào đã thành công trước đó. Nếu điều kiện không đủ stock được xem là lỗi cần rollback, phải dùng `Mono.error(...)` thay vì im lặng trả empty.

Trong trường hợp method chỉ đọc, `Mono.empty()` có thể là hợp đồng hợp lệ. Ý nghĩa business của empty và error cần được định nghĩa, không suy đoán từ framework.

### 8.5. Lỗi phát sau onNext vẫn có thể làm commit thất bại

```text
Transactional Mono:
  database statements succeed
  -> application maps to Receipt (onNext may occur)
  -> transaction manager attempts commit
  -> commit errors
  -> Publisher fails
```

Vì vậy không phát thông báo “đặt chỗ thành công” hay gọi external API trong `doOnNext(receipt -> ...)` nằm **bên trong** transactional chain trước completion. Với các side effects sau commit, dùng orchestration rõ ràng hoặc transactional outbox.

## 9. Cancel và Flux: nguy cơ rollback ngoài ý muốn

Reactive streams có tín hiệu **cancel** khi subscriber không muốn nhận thêm dữ liệu. Đối với Spring reactive transactions trong những phiên bản hiện đại (đặc biệt từ Spring Framework 5.3), **cancellation được xử lý theo hướng rollback** vì khi stream bị hủy, framework không thể chắc chắn toàn bộ công việc transactional đã hoàn tất.

### 9.1. Bẫy take(1)

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Flux<ReservationDocument> reserveBatch(
        Flux<ReserveCommand> commands) {

    return commands.concatMap(this::reserveOneWithinTransaction);
}
```

Giả sử một caller dùng:

```java
reservationService.reserveBatch(commands)
    .take(1);
```

`take(1)` thường **cancel upstream** sau phần tử đầu tiên. Nếu upstream transaction chưa complete, cancellation có thể dẫn tới **rollback**, dù subscriber đã nhận một `ReservationDocument` đầu tiên. Điều này rất nguy hiểm nếu UI tưởng rằng nhận một item nghĩa là dữ liệu đã commit.

**Không dùng `Flux.take(1)` trên một transaction thực hiện nhiều ghi để coi phần tử đầu tiên là confirmation.** Nếu cần nhiều lệnh ghi chung một transaction, một `Mono<BatchReceipt>` biểu diễn completion toàn bộ có thể là hợp đồng rõ hơn.

### 9.2. Flux dài giữ transaction mở lâu

```text
BEGIN TRANSACTION
    -> Flux emits 1st row
    -> Flux emits 2nd row
    -> ... streams for minutes ...
    -> complete -> COMMIT
```

Giao dịch càng lâu, càng dễ chịu lock/write conflict, timeout, memory/resource pressure và khó xử lý cancellation. Không đặt một dòng stream vô hạn, thay đổi kết quả liên tục hoặc file export kéo dài vào một MongoDB multi-document transaction rồi hy vọng nó tự scale.

Với reporting/export chỉ đọc, cần cân nhắc có thực sự cần transaction không, hay dùng snapshot read/consistency policy phù hợp. Với batch writes lớn, chia thành các transaction độc lập có ID/điểm checkpoint rõ thay vì giữ một transaction cho hàng trăm nghìn item.

### 9.3. Cancellation khác onError

`cancel` không nhất thiết phát một `onError` cho subscriber, nên các `doOnError` hook có thể không quan sát được việc hủy. Có thể dùng `doFinally(signalType -> ...)` để ghi metric theo terminal signal:

```java
return reservationService.reserve(command)
    .doFinally(signal ->
        metrics.recordTermination(signal.name()));
```

`metrics` trong ví dụ là service giám sát giả định. Không dựa vào `doFinally` để tự điều khiển commit/rollback hoặc làm side effect database độc lập. Nếu cần kiểm tra cancellation, dùng integration test có `StepVerifier`/timeout và xác minh lại BSON.

### 9.4. Timeout cũng có thể tạo cancellation

```java
reservationService.reserve(command)
    .timeout(java.time.Duration.ofSeconds(2));
```

Khi quá thời gian, `timeout` có thể **cancel upstream** và phát lỗi timeout cho downstream. Transaction manager cần xử lý cancellation/rollback; nhưng nếu timeout/connection lost xảy ra **tại pha commit**, client có thể không biết commit thực tế đã thành công hay chưa. Vì thế không được coi mọi timeout là chứng cứ chắc chắn đã rollback.

Đặt timeout nhất quán với transaction/session/network SLA; khi outcome commit không rõ, dùng operation ID và reconciliation.

## 10. Trình tự trong cùng session: tránh chạy MongoDB statements song song

Trong một MongoDB transaction, các operations qua cùng session **không nên chạy đồng thời**. Đây là giới hạn quan trọng của MongoDB Driver và giao dịch reactive.

### 10.1. Không dùng zip/when để chạy các lệnh ghi transactional song song

```java
// PHẢN VÍ DỤ: hai operations có thể chạy concurrently.
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> writeWrong() {
    return Mono.when(
        template.insert(new AuditDocument("A1")),
        template.insert(new OrderDocument("O1", "TENANT-A", "NEW"))
    );
}
```

`Mono.when` subscribe nhiều nguồn cùng lúc. Khi các nguồn cùng dùng một transaction/session, đây không phải một mẫu an toàn để thực hiện parallel database operations. Nó có thể dẫn tới lỗi driver/server hoặc kết quả khó dự đoán.

### 10.2. Đúng: nối các thao tác DB tuần tự

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> writeSequentially() {
    return template.insert(new AuditDocument("A1"))
        .then(template.insert(
            new OrderDocument("O1", "TENANT-A", "NEW")))
        .then();
}
```

`then(...)` đảm bảo insert thứ hai bắt đầu khi insert thứ nhất complete. Với `Flux`, `concatMap` thích hợp khi muốn thực thi các MongoDB writes tuần tự; không dùng `flatMap` mặc định với concurrency nhiều thao tác cùng session.

### 10.3. concatMap không biến transaction thành batch vô hạn

```java
return Flux.fromIterable(commands)
    .concatMap(cmd -> template.insert(
        new ReservationDocument(
            cmd.operationId(),
            cmd.tenantId(),
            cmd.stockId(),
            cmd.quantity())));
```

Các insert được thực thi tuần tự, nhưng nếu có hàng chục nghìn commands, transaction có thể quá dài và vượt giới hạn. Thiết kế batch size, checkpoint, idempotency/outbox theo nghiệp vụ; không cố gắng xử lý cả một migration lớn trong một transaction kéo dài.

### 10.4. publishOn không phải công cụ song song hóa transaction

`publishOn` đổi scheduler của các tín hiệu tiếp theo và Reactor Context thường vẫn được truyền qua operator tương thích, nhưng **không làm operations song song trở nên an toàn** trong transaction. Tránh tự mở thread, `CompletableFuture.supplyAsync` hoặc `subscribe()` bên trong transactional flow khi chúng làm mất liên kết session hoặc thực thi ngoài kiểm soát.

## 11. @Transactional và TransactionalOperator: chọn ranh giới phù hợp

Spring Framework cung cấp `TransactionalOperator` cho reactive code. Thay vì đặt annotation trên toàn bộ method, developer có thể **bao transaction quanh một Publisher cụ thể** bằng API chương trình.

### 11.1. Cấu hình TransactionalOperator

File `ReservationTransactionOperatorConfiguration.java`:

```java
package com.example.shop.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration(proxyBeanMethods = false)
public class ReservationTransactionOperatorConfiguration {

    @Bean("reservationTransactionalOperator")
    TransactionalOperator reservationTransactionalOperator(
            @Qualifier("reactiveMongoTransactionManager")
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
```

`ReactiveMongoTransactionManager` từ mục 5 đã được đăng ký trước; không tạo một transaction manager mới cho mỗi request.

### 11.2. Dùng operator thay cho annotation

File `ReservationWithOperatorService.java`:

```java
package com.example.shop.reservation;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReservationWithOperatorService {

    private final ReactiveMongoTemplate template;
    private final TransactionalOperator operator;

    public ReservationWithOperatorService(
            ReactiveMongoTemplate template,
            @Qualifier("reservationTransactionalOperator")
            TransactionalOperator operator) {
        this.template = template;
        this.operator = operator;
    }

    public Mono<ReservationReceipt> reserve(
            ReserveCommand command) {

        Mono<ReservationReceipt> work = Mono.defer(() -> {
            if (command == null
                    || command.tenantId() == null
                    || command.tenantId().isBlank()
                    || command.operationId() == null
                    || command.operationId().isBlank()
                    || command.stockId() == null
                    || command.stockId().isBlank()
                    || command.quantity() <= 0) {
                return Mono.error(new IllegalArgumentException(
                    "Yêu cầu không hợp lệ"));
            }

            Query query = Query.query(
                Criteria.where("_id").is(command.stockId())
                    .and("tenantId").is(command.tenantId())
                    .and("available").gte(command.quantity()));

            return template.updateFirst(
                    query,
                    new Update().inc(
                        "available", -command.quantity()),
                    StockDocument.class)
                .flatMap(result -> {
                    if (result.getModifiedCount() != 1) {
                        return Mono.error(
                            new InsufficientStockException());
                    }

                    return template.insert(
                        new ReservationDocument(
                            command.operationId(),
                            command.tenantId(),
                            command.stockId(),
                            command.quantity()))
                        .map(saved -> new ReservationReceipt(
                            saved.id(), "RESERVED"));
                });
        });

        return operator.transactional(work);
    }
}
```

Ví dụ đã kiểm tra các field cơ bản; trong production vẫn cần kiểm tra quyền tenant, idempotency và các giới hạn nghiệp vụ trước khi xử lý. Trọng tâm ở đây là **đổi cách xác định ranh giới transaction**: `operator.transactional(work)` thay cho `@Transactional`.

### 11.3. So sánh

| Tiêu chí | `@Transactional` trên method Publisher | `TransactionalOperator` |
| --- | --- | --- |
| Cách khai báo | Annotation ở API method | Bọc một Publisher bằng code |
| Ranh giới áp dụng | Publisher do method proxied trả về | Publisher cụ thể được gọi `transactional(...)` |
| Phụ thuộc AOP proxy | Có trong chế độ proxy-based phổ biến | Không cần proxy cho phần operator |
| Dễ dùng cho service thông thường | Có | Có, nhưng thêm object/cấu hình |
| Chỉ transaction một đoạn của pipeline | Cần tổ chức lại method/bean | Tường minh bằng cách chọn đoạn bọc |
| Session trong reactive pipeline | Reactor Context | Reactor Context |
| Tự bảo đảm exactly-once external side effects | Không | Không |
| Tự retry commit unknown / toàn body | Không được mặc định | Không được mặc định |

Không đặt cả hai trên cùng một workflow chỉ để “chắc chắn hơn” mà không biết propagation và transaction nesting. Có thể tạo transaction lồng, join transaction đang có, hoặc làm ranh giới khó đoán tùy cấu hình.

### 11.4. Chỉ bọc phần ghi; chạy tác vụ ngoài transaction sau commit

```java
Mono<ReservationReceipt> mongoWork =
    reservationMongoOperations.createReservation(command);

Mono<ReservationReceipt> committed =
    operator.transactional(mongoWork);

return committed.flatMap(receipt ->
    reportingCache.invalidate(receipt.operationId())
        .thenReturn(receipt));
```

Đây là pseudocode composition trong một service có `operator`, `reservationMongoOperations` và `reportingCache` được inject. `invalidate(...)` được đặt **sau** Publisher transactional, nên chỉ chạy khi transaction hoàn thành thành công. Nếu commit fail, chuỗi sẽ phát error và không gọi invalidate.

**Nhưng:** giữa commit thành công và invalidate vẫn có thể xảy ra process crash. Nếu cần bảo đảm một sự kiện chắc chắn được phát dù crash, hãy dùng **transactional outbox** và consumer idempotent thay vì coi thao tác sau-commit không có rủi ro.

### 11.5. TransactionalOperator.execute và callback có status

API programmatic còn cho phép `operator.execute(...)`:

```java
Flux<ReservationReceipt> result =
    operator.execute(transactionStatus ->
        reservationMongoOperations.createReservation(command)
            .flux());
```

Đây là pattern khái niệm; `reservationMongoOperations` trả một Publisher reactive phù hợp. `transactionStatus` có thể được dùng theo API Spring để điều khiển rollback có chủ đích trong trường hợp cần thiết, nhưng đừng biến domain failure thành completion im lặng nếu caller vẫn cần biết lỗi.

Với nghiệp vụ đơn giản, `operator.transactional(Mono)` thường dễ đọc hơn.

## 12. Transaction propagation và nested calls

Một vấn đề khác xuất hiện khi hai phương thức annotated gọi lẫn nhau:

```text
OrderService.placeOrder()        @Transactional (reactive)
    |
    +-- ReservationService.reserve()   @Transactional (reactive)
    |
    +-- PaymentRecordService.record()  @Transactional (reactive)
```

Nếu cả ba dùng **cùng reactive transaction manager/factory** và đều tham gia đúng Reactor Context, propagation mặc định `REQUIRED` có thể khiến các thao tác join **cùng logical transaction**. Nhưng không nên đoán từ tên annotation: cần kiểm tra call qua proxy, manager được chọn và behavior của framework version.

### 12.1. REQUIRED không phải transaction độc lập cho mỗi method

`@Transactional(propagation = Propagation.REQUIRED)` có nghĩa thường sẽ tham gia transaction hiện có nếu phù hợp; nếu không có, tạo transaction mới. Vì thế nếu `reserve()` được gọi bên trong transaction của `placeOrder()`, việc `reserve()` hoàn tất **không chứng minh đã commit độc lập**.

Nếu các method cùng nằm trong transaction ngoài và sau đó payment ghi lỗi, các thao tác reservation có thể bị rollback cùng nhau.

### 12.2. REQUIRES_NEW và NESTED phải xét hỗ trợ của MongoDB

`REQUIRES_NEW` yêu cầu phạm vi transaction độc lập khi transaction infrastructure hỗ trợ; điều đó có thể cần session/resource riêng và có tác động tới khả năng đọc dữ liệu chưa commit của transaction ngoài.

`NESTED` dựa vào khái niệm savepoint trong một số transaction managers; MongoDB multi-document transaction **không nên được mặc định coi là có savepoint JDBC tương đương**. Kiểm tra khả năng hỗ trợ propagation theo `ReactiveMongoTransactionManager` và phiên bản Spring Data đang dùng; không thêm `NESTED` chỉ vì thấy enum `Propagation.NESTED` tồn tại.

### 12.3. Đừng dùng transaction manager khác cho một nửa pipeline

```text
ReactiveMongoTemplate A ---> ReactiveMongoDatabaseFactory A
                             |
                             +-- ReactiveMongoTransactionManager A

ReactiveMongoTemplate B ---> ReactiveMongoDatabaseFactory B
                             |
                             +-- TransactionManager B or no manager
```

Nếu method annotated bằng manager A nhưng một nhánh ghi bằng template B, **không có bảo đảm** nhánh B được commit/rollback cùng A. Điều tương tự xảy ra khi vừa dùng reactive MongoDB vừa dùng R2DBC/PostgreSQL trong một method: một `@Transactional` không tự trở thành distributed transaction.

Nếu nghiệp vụ cần đồng bộ MongoDB với Kafka/HTTP/RDBMS, cân nhắc outbox, saga hoặc kiến trúc đảm bảo eventual consistency rõ ràng. Không suy luận mọi Publisher trong cùng `zip`/`flatMap` là một transaction đa hệ thống.

### 12.4. readOnly = true không tạo cơ chế cấp quyền read-only

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager",
    readOnly = true)
public Flux<OrderDocument> findOrders(...) {
    // ...
}
```

`readOnly` là một hint/đặc tả giao dịch cho framework và có thể ảnh hưởng handling, nhưng **không thay thế MongoDB RBAC**. Không dùng annotation đó như biện pháp ngăn code khác ghi collection. Với transaction MongoDB, đọc nhiều document từ secondary cũng không tự được cho phép chỉ nhờ readOnly; kiểm tra read preference/transaction support theo driver/server.

## 13. Dùng ReactiveMongoRepository bên trong @Transactional

Không bắt buộc mọi thao tác đều qua template. Repository reactive có thể tham gia cùng transaction nếu dùng đúng factory/manager/session:

```java
package com.example.shop.reservation;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReservationRepository
        extends ReactiveMongoRepository<
            ReservationDocument, String> {
}
```

Service minh họa:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserveViaRepository(
        ReserveCommand cmd) {

    return reactiveMongoTemplate.updateFirst(
            stockQuery(cmd),
            stockDecrement(cmd),
            StockDocument.class)
        .flatMap(result -> {
            if (result.getModifiedCount() != 1) {
                return Mono.error(
                    new InsufficientStockException());
            }
            return reservationRepository
                .save(new ReservationDocument(
                    cmd.operationId(),
                    cmd.tenantId(),
                    cmd.stockId(),
                    cmd.quantity()))
                .map(saved -> new ReservationReceipt(
                    saved.id(), "RESERVED"));
        });
}
```

Đoạn này là method trích từ một service có `reactiveMongoTemplate`, `reservationRepository`, `stockQuery`/`stockDecrement`, validation và manager đã được cấu hình. Trọng tâm: **reactive repository và reactive template cùng tham gia transaction khi dùng cùng factory/context**, không có chuyện repository tự tạo transaction khác chỉ vì thuộc interface riêng.

### 13.1. save không phải luôn insert

`ReactiveMongoRepository.save(...)` là thao tác save (có thể insert hoặc update tùy entity/ID/mapping). Với idempotency key, việc chỉ gọi `save` không phải cơ chế ngăn trùng theo đúng semantics “một reservation chỉ được tạo một lần”.

Nếu business yêu cầu **create-only**, nên chọn `insert` hoặc chiến lược unique conditional create và xử lý duplicate key rõ ràng; không mặc định `save` trên entity có ID đã tồn tại là lỗi.

Trong bài này, `ReservationService` mục 6 dùng `template.insert(...)` để thể hiện **chỉ được tạo mới**. Nếu thay bằng repository save, phải kiểm tra lại hợp đồng idempotency.

### 13.2. @Version và optimistic locking

Spring Data MongoDB hỗ trợ mapping `@Version` trong nhiều đường save/update phù hợp. Optimistic locking có thể giúp phát hiện cập nhật cạnh tranh, nhưng không thay điều kiện `available >= qty` khi trừ tồn kho, và không thay transaction nếu nghiệp vụ cần hai document được commit atomically.

Không chỉ dựa vào version ở DTO đã đọc rồi cập nhật `available` vô điều kiện. Cần bảo đảm điều kiện so khớp ở **statement MongoDB** và xử lý kết quả matched/modified.

## 14. Reactive transaction và external side effects

Một side effect như gửi email hoặc gọi thanh toán bên thứ ba **không rollback** khi MongoDB transaction abort:

```java
// PHẢN VÍ DỤ: external API được gọi trong transaction.
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> reserveAndNotify(
        ReserveCommand command) {

    return reactiveMongoTemplate.insert(
            new ReservationDocument(
                command.operationId(),
                command.tenantId(),
                command.stockId(),
                command.quantity()))
        .flatMap(saved -> webClient.post()
            .uri("/external-notify")
            .retrieve()
            .bodyToMono(Void.class));
}
```

Đây là đoạn phản ví dụ minh họa, không phải class biên dịch độc lập. External HTTP có thể thành công trước khi MongoDB commit và sau đó transaction abort. Khi callback/Pubisher được retry, HTTP có thể được gọi nhiều lần. Nếu remote call chậm, transaction mở lâu và dễ timeout.

### 14.1. Transactional outbox

Thiết kế an toàn hơn:

```text
Transactional Publisher:
  update stock_items
  insert reservations
  insert outbox(eventId, operationId, payloadRef)
         |
         v
     COMMIT MongoDB
         |
         v
Outbox worker reads committed events
         |
         +-- sends message / HTTP
         +-- marks dispatched with retry and deduplication
```

Nếu transaction rollback, reservation và outbox event đều không xuất hiện. Khi commit thành công mà process crash trước khi gửi, outbox vẫn còn để worker xử lý.

Lưu ý rằng outbox **không làm external delivery exactly-once một cách tự động**: dispatcher/consumer cần idempotency theo `eventId` và handling khi gửi thành công nhưng ACK bị mất.

### 14.2. Khi không cần outbox

Nếu side effect chỉ là invalidation cache có thể tự khôi phục và mất một lần invalidation không phá hợp đồng, có thể dùng xử lý sau-commit với rủi ro được chấp nhận. Nhưng các side effects bắt buộc như phát hóa đơn, yêu cầu thanh toán và cập nhật hệ thống ngoài cần mô hình giao hàng/đối soát rõ ràng, không chỉ gắn `doOnSuccess` bên trong Publisher transactional.

## 15. Retry một Publisher transactional: resubscribe không phải retry riêng commit

Reactor có `retry(...)` và `retryWhen(...)` để subscribe lại Publisher khi gặp lỗi. Nếu đặt operator này bên ngoài một phương thức `@Transactional` trả `Mono`, lần retry có thể **tạo một subscription mới** và theo đó là **một transaction attempt mới**.

Điều này **không tương đương** với gửi lại `commitTransaction` của transaction cũ. Với MongoDB, hai error labels quan trọng:

| Error label | Ý nghĩa | Hướng xử lý chính |
| --- | --- | --- |
| `TransientTransactionError` trong transactional body | Attempt hiện tại gặp lỗi tạm thời và không thể tiếp tục như bình thường | Có thể retry **toàn transaction** trên attempt mới với budget |
| `UnknownTransactionCommitResult` khi commit | Client không biết commit có thành công hay chưa | Retry **commit của cùng transaction/session**, không replay body |

### 15.1. RetryWhen nguy hiểm khi đặt vô điều kiện

```java
// PHẢN VÍ DỤ: không áp cho giao dịch ghi nhạy cảm.
return reservationService.reserve(command)
    .retryWhen(reactor.util.retry.Retry.max(3));
```

Khi commit thành công nhưng acknowledgment bị mất, Publisher có thể phát lỗi sau khi MongoDB đã áp dụng thay đổi. `retryWhen` trên toàn method sẽ subscribe lại để làm một **nghiệp vụ mới**, dẫn tới duplicate reservation hoặc các tác dụng phụ khác nếu idempotency thiếu.

### 15.2. Retry whole transaction chỉ khi đã phân loại

Khi lỗi body có `TransientTransactionError` và operation có thể chạy lại, một tầng điều phối có thể retry whole transaction với budget phù hợp. Nhưng với `UnknownTransactionCommitResult`:

1. Không dùng retry Publisher ở tầng ngoài để thay retry commit.
2. Khi còn giữ được session/transaction identity, cần xử lý **commit retry tại ranh giới transaction**, theo driver semantics.
3. Khi session đã mất hoặc deadline cạn, **reconcile theo operation ID** và trạng thái dữ liệu thực.

Với Spring `ReactiveMongoTransactionManager`, cần xem **cơ chế commit và cách exception được truyền** trong phiên bản đang chạy. `@Transactional` hoặc `TransactionalOperator` **không nên được mặc định coi như** một helper luôn retry chính commit giống callback API của MongoDB driver. Nếu business bắt buộc retry commit ở cùng session, thiết kế hook/layer session-aware có test tương ứng, thay vì tùy tiện lắp `retryWhen` ngoài publisher.

### 15.3. Phân loại error label mà không parse error message

Trong ứng dụng Spring Data, lỗi có thể được translate thành Spring `DataAccessException` với `MongoException` ở cause chain. Ví dụ helper:

```java
package com.example.shop.reservation;

import com.mongodb.MongoException;

public final class MongoTransactionErrorLabels {
    private MongoTransactionErrorLabels() {}

    public static boolean contains(
            Throwable error, String label) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof MongoException mongo
                    && mongo.hasErrorLabel(label)) {
                return true;
            }
        }
        return false;
    }
}
```

Helper này chỉ nhìn được nhãn nếu còn `MongoException` trong cause chain. Nó không biết **lỗi xảy ra tại pha body hay commit**, và không thể thực hiện retry commit nếu không sở hữu đúng session/transaction identity. Phân loại nhãn chỉ là **một phần** của retry strategy.

### 15.4. Khi commit chưa xác định, response không được nói “đã thất bại”

Một tình huống:

```text
reserve("RES-001")
  -> stock decremented inside transaction
  -> reservation inserted inside transaction
  -> commit sent
  -> MongoDB may have committed
  -> network ACK lost
  -> UnknownTransactionCommitResult
```

Không được kết luận “transaction đã rollback” và yêu cầu client tạo operation ID mới. API có thể trả trạng thái **`PENDING_CONFIRMATION`** kèm operation ID để đối soát. Đọc ledger/reservation từ nguồn có độ mới phù hợp (thường primary) và kiểm tra payload, nhưng **một lần không thấy record không luôn chứng minh transaction cũ sẽ không thể commit**.

### 15.5. Idempotency không tự có từ @Transactional

`ReservationDocument.id` trong ví dụ là operation ID; `_id` có unique index. Khi client retry cùng ID:

- Nếu lần trước đã commit, insert trùng có thể thất bại và transaction mới rollback update stock.
- Nhưng service minh họa chỉ phát lỗi duplicate; **nó chưa phải một API idempotent hoàn chỉnh**.
- Tầng điều phối cần đối chiếu trạng thái/payload cũ để trả receipt tương ứng hoặc đánh dấu cần reconciliation.
- Nếu request cùng operation ID nhưng quantity/stock khác, không được coi là retry tương đương.

Với HTTP/gateway retries, dùng idempotency key ổn định và một request fingerprint canonical. Không tạo reservation ID mới ở mỗi lần subscribe hoặc retry.

## 16. Không gọi API ngoài transaction và không mix imperative/ reactive

Đoạn sau là lỗi thiết kế:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> writeWithBlockingCall() {
    return Mono.fromRunnable(() -> {
        mongoTemplate.save(new AuditDocument("A1"));
    }).then(reactiveMongoTemplate.insert(
        new ReservationDocument(
            "R1", "TENANT-A", "S1", 1))).then();
}
```

`mongoTemplate` ở đây là **imperative `MongoTemplate`**. Mặc dù code bọc nó trong một `Mono` để trì hoãn thực thi, nó **không tự tham gia MongoDB reactive transaction session**. Nó còn có thể block thread được dùng để phục vụ reactive chain.

**Đúng:** dùng `ReactiveMongoTemplate`/`ReactiveMongoRepository` phù hợp và một session/context duy nhất, hoặc tách thao tác blocking ra một workflow khác với consistency contract rõ. Chuyển blocking call sang `Schedulers.boundedElastic()` chỉ giải quyết một phần việc chiếm thread; **không làm nó tự tham gia transaction reactive**.

### 16.1. Cẩn trọng với WebClient trong transaction

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserveAndCharge(
        ReserveCommand cmd) {
    return webClient.post()
        .uri("/payments/charge")
        .retrieve()
        .bodyToMono(ChargeReceipt.class)
        .then(reservationService.reserve(cmd));
}
```

Đây là ví dụ phản thiết kế: dù `WebClient` là reactive, remote payment API **không nằm trong MongoDB transaction**. Nó có thể đã charge khách trước khi MongoDB rollback. Và nếu `reservationService.reserve` là một method transactional riêng, propagation/routing còn có thể làm ranh giới khó hiểu.

Thay vào đó, dùng payment workflow có idempotency, outbox/saga, trạng thái `PENDING`/`CONFIRMED` và compensation/đối soát phù hợp. Không cố đưa network call không rollback được vào transaction MongoDB.

### 16.2. Không tự tạo ClientSession khác trong flow

Khi dùng `ReactiveMongoTransactionManager`, để Spring Data điều phối session trên Reactor Context. Việc tự mở một `ClientSession` qua MongoDB driver và dùng nó cho một nhánh riêng không tự join cùng transaction của template. Chỉ sử dụng manual reactive driver session khi cố ý kiểm soát toàn bộ transaction lifecycle bằng API driver phù hợp và không trộn với manager đã sở hữu session.

### 16.3. Reactive transaction không trải qua Kafka/RDBMS chỉ vì cùng Publisher

`Flux`/`Mono` là cách tổ chức các thao tác async, không phải distributed transaction coordinator. Khi cùng một Publisher gọi MongoDB, Postgres R2DBC và Kafka:

- MongoDB manager quản lý MongoDB session thuộc factory của nó.
- R2DBC transaction manager quản lý kết nối SQL riêng nếu có.
- Kafka producer có giao dịch/ack riêng.

Không có atomicity liên hệ ba hệ thống nếu ứng dụng chưa xây cơ chế phù hợp. Với nghiệp vụ nhiều hệ thống, outbox và saga thường dễ vận hành hơn giả định một annotation có thể rollback tất cả.

## 17. Read-only, session và các truy vấn trong transaction

Với reactive MongoDB:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager",
    readOnly = true)
public Flux<StockDocument> listStocks(String tenantId) {
    return reactiveMongoTemplate.find(
        Query.query(Criteria.where("tenantId").is(tenantId)),
        StockDocument.class);
}
```

Đây là method minh họa trong một bean có template đã inject, không phải đoạn Java độc lập. Cần cân nhắc liệu **một transaction đa document có thật sự cần cho đọc danh sách** hay không. Với dữ liệu báo cáo lớn, có thể dùng read concern/snapshot/causal consistency theo yêu cầu thay vì giữ transaction mở tới khi stream hoàn tất.

### 17.1. Read preference và giao dịch

Transaction MongoDB có những giới hạn về read preference và session; trong thực tế, các operations của multi-document transaction cần hướng tới primary theo các điều kiện hỗ trợ. Không đặt một reporting template `secondaryPreferred` vào reactive transaction rồi mặc định rằng MongoDB sẽ chạy transaction read/write trên secondary.

### 17.2. Không nhầm transaction readOnly với unique constraints

`readOnly=true` không cấm nghiệp vụ ghi stock âm qua mọi đường writer. Điều kiện `available >= quantity`, unique index `reservationId`, authorization tenant và MongoDB schema validation là các cơ chế khác. Transaction đảm bảo phạm vi atomicity/consistency theo cấu hình, không tạo mọi ràng buộc nghiệp vụ tự động.

## 18. Khi nào không nên dùng @Transactional cho Publisher?

Không phải API reactive nào cũng cần multi-document transaction:

| Tình huống | Có nên dùng transaction? | Lý do |
| --- | --- | --- |
| Chỉ đọc một document theo ID | Thường không cần | Atomic read đơn lẻ đã có ý nghĩa riêng |
| `updateFirst` có condition trên một document | Thường không cần multi-document transaction | MongoDB hỗ trợ atomic single-document update |
| Trừ stock và tạo reservation ở **hai documents/collections** phải cùng thành bại | Thường nên cân nhắc | Cần atomicity đa document |
| Một API `Flux` stream hàng triệu kết quả báo cáo | Thường tránh transaction dài | Resource, cancellation và transaction lifetime |
| Import 100.000 records có checkpoint | Chia batch/transaction nhỏ khi cần | Dễ retry và tránh transaction quá dài |
| Gọi external payment API và ghi DB | Không thể chỉ dùng MongoDB transaction | Remote API không tham gia commit/rollback |
| Cần consistency khi đọc nhiều collections | Tùy hợp đồng snapshot/read concern | Transaction là một công cụ, không phải lựa chọn mặc định |

Nếu dữ liệu có thể mô hình trong một document mà vẫn đáp ứng nhu cầu, atomic single-document update thường đơn giản và hiệu quả hơn một transaction đa document. Đừng dùng transaction để sửa một thiết kế schema chưa phù hợp mà không đánh giá trade-off.

## 19. Kiểm thử tích hợp với StepVerifier trên replica set thật

Một unit test mock `ReactiveMongoTemplate` có thể kiểm tra service gọi `updateFirst` rồi `insert`, nhưng **không chứng minh** hai lệnh thực sự cùng session, cùng transaction hoặc server rollback phần update khi insert lỗi.

Để kiểm thử atomicity:

1. Cấu hình một MongoDB **replica set TEST** có hỗ trợ multi-document transactions, không chỉ standalone MongoDB.
2. Khởi tạo **collection trước khi transaction đầu tiên chạy**, đặc biệt nếu server/driver có giới hạn tạo collection ngầm trong transaction.
3. Dùng `@SpringBootTest` (hoặc test slice có import đúng manager/service) để đảm bảo transaction proxy thực sự được tạo.
4. Seed BSON ở ngoài transaction, sau đó gọi phương thức annotated qua bean được inject.
5. Dùng `StepVerifier.verifyComplete()` hoặc `expectError(...)` để chờ terminal signal.
6. **Đọc lại MongoDB sau đó** để xác minh kết quả, không chỉ assert giá trị trả về.

### 19.1. Phần chuẩn bị test

Ví dụ dưới đây dùng Java 17+, JUnit 5, Reactor Test và Spring Boot với MongoDB reactive config. Trước khi chạy phải cấu hình môi trường/profile test trỏ đến **database cô lập**, không phải development chung/production. Test profile cần khởi tạo `ReactiveMongoTransactionManager` ở mục 5.

File `ReservationReactiveTransactionIntegrationTest.java`:

```java
package com.example.shop.reservation;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ReservationReactiveTransactionIntegrationTest {

    @Autowired
    ReactiveMongoTemplate template;

    @Autowired
    ReservationService service;

    // Chỉ sử dụng trên test MongoDB database riêng.
    private Mono<Void> ensureCollections() {
        Mono<Void> stockReady =
            template.collectionExists(StockDocument.class)
                .flatMap(exists -> exists
                    ? Mono.<Void>empty()
                    : template
                        .createCollection(StockDocument.class)
                        .then());

        Mono<Void> reservationReady =
            template.collectionExists(ReservationDocument.class)
                .flatMap(exists -> exists
                    ? Mono.<Void>empty()
                    : template
                        .createCollection(ReservationDocument.class)
                        .then());

        return stockReady.then(reservationReady);
    }

    private static Query byId(String id) {
        return Query.query(Criteria.where("_id").is(id));
    }

    private Mono<Void> cleanup(String stockId, String operationId) {
        return template.remove(
                byId(operationId), ReservationDocument.class)
            .then(template.remove(
                byId(stockId), StockDocument.class))
            .then();
    }

    @Test
    void successCommitsStockAndReservationTogether() {
        String suffix = UUID.randomUUID().toString();
        String stockId = "STOCK-" + suffix;
        String operationId = "RES-" + suffix;

        try {
            StepVerifier.create(
                    ensureCollections().then(
                        template.insert(new StockDocument(
                            stockId, "TENANT-TEST", 10L))))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(service.reserve(
                    new ReserveCommand(
                        "TENANT-TEST", operationId, stockId, 3)))
                .assertNext(receipt -> {
                    assertThat(receipt.operationId())
                        .isEqualTo(operationId);
                    assertThat(receipt.state())
                        .isEqualTo("RESERVED");
                })
                .verifyComplete();

            StepVerifier.create(
                    template.findById(
                        stockId, StockDocument.class))
                .assertNext(stock ->
                    assertThat(stock.available()).isEqualTo(7L))
                .verifyComplete();

            StepVerifier.create(
                    template.findById(
                        operationId, ReservationDocument.class))
                .assertNext(reservation -> {
                    assertThat(reservation.stockId())
                        .isEqualTo(stockId);
                    assertThat(reservation.quantity())
                        .isEqualTo(3L);
                })
                .verifyComplete();
        } finally {
            StepVerifier.create(cleanup(stockId, operationId))
                .verifyComplete();
        }
    }

    @Test
    void duplicateReservationRollsBackEarlierStockUpdate() {
        String suffix = UUID.randomUUID().toString();
        String stockId = "STOCK-" + suffix;
        String operationId = "RES-" + suffix;

        try {
            StepVerifier.create(
                    ensureCollections()
                        .then(template.insert(new StockDocument(
                            stockId, "TENANT-TEST", 10L)))
                        .then(template.insert(
                            new ReservationDocument(
                                operationId, "TENANT-TEST",
                                stockId, 1L))))
                .expectNextCount(1)
                .verifyComplete();

            // update stock sẽ chạy trước, insert bị duplicate _id.
            StepVerifier.create(service.reserve(
                    new ReserveCommand(
                        "TENANT-TEST", operationId, stockId, 3)))
                .expectError()
                .verify();

            // Nếu transaction đúng, update stock đã rollback.
            StepVerifier.create(
                    template.findById(
                        stockId, StockDocument.class))
                .assertNext(stock ->
                    assertThat(stock.available())
                        .isEqualTo(10L))
                .verifyComplete();

            // Reservation cũ vẫn là 1, không bị ghi đè.
            StepVerifier.create(
                    template.findById(
                        operationId, ReservationDocument.class))
                .assertNext(reservation ->
                    assertThat(reservation.quantity())
                        .isEqualTo(1L))
                .verifyComplete();
        } finally {
            StepVerifier.create(cleanup(stockId, operationId))
                .verifyComplete();
        }
    }

    @Test
    void insufficientStockDoesNotCreateReservation() {
        String suffix = UUID.randomUUID().toString();
        String stockId = "STOCK-" + suffix;
        String operationId = "RES-" + suffix;

        try {
            StepVerifier.create(
                    ensureCollections().then(
                        template.insert(new StockDocument(
                            stockId, "TENANT-TEST", 1L))))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(service.reserve(
                    new ReserveCommand(
                        "TENANT-TEST", operationId, stockId, 3)))
                .expectError(InsufficientStockException.class)
                .verify();

            StepVerifier.create(
                    template.findById(
                        stockId, StockDocument.class))
                .assertNext(stock ->
                    assertThat(stock.available())
                        .isEqualTo(1L))
                .verifyComplete();

            StepVerifier.create(
                    template.findById(
                        operationId, ReservationDocument.class))
                .verifyComplete(); // Mono.empty: không có reservation.
        } finally {
            StepVerifier.create(cleanup(stockId, operationId))
                .verifyComplete();
        }
    }
}
```

### 19.2. Cảnh báo khi chạy test

Test thực hiện insert/delete **trên database mà Spring cấu hình**. Phải áp profile/credentials chỉ cho **MongoDB test cô lập**, chuẩn bị replica set với session support và đảm bảo không có ứng dụng khác dùng database test đó. Cleanup xóa **chỉ theo ID ngẫu nhiên của test**, không gọi `dropDatabase` hay `deleteMany({})` trên môi trường dùng chung.

Ví dụ `ensureCollections()` được viết đơn giản cho bài học; nếu nhiều test chạy song song trên một database chưa có collection, thao tác check-then-create có thể race. Trong CI thực tế, nên tạo collection qua migration/test fixture trước khi chạy hoặc dùng database riêng theo job.

`@SpringBootTest` chỉ mang lại test tích hợp đúng nếu:

- Service được Spring scan và gọi qua transaction proxy.
- Reactive manager được tạo và repository/template cùng factory.
- Test connection thật sự tới MongoDB replica set hỗ trợ transaction.
- Transaction không bị vô hiệu hóa bởi một cấu hình test khác.

Nếu test chạy trên standalone và báo `Transaction numbers are only allowed on a replica set member or mongos`, đó là **vấn đề topology**, không phải chỉ thêm `retryWhen` là được.

### 19.3. Điều test chứng minh và điều chưa chứng minh

| Test | Chứng minh | Chưa chứng minh |
| --- | --- | --- |
| Success | Hai ghi cùng tồn tại sau completion | Mọi trường hợp network commit đều thành công |
| Duplicate rollback | Stock không giảm dù insert reservation lỗi | Idempotent HTTP API tự động trả receipt cũ |
| Insufficient stock | Không trừ tồn/không tạo reservation khi không đủ | Mọi kiểu cạnh tranh đều được retry tự động |

Muốn chứng minh behavior khi **cancel**, **failover**, `TransientTransactionError` hoặc `UnknownTransactionCommitResult`, cần thêm test có điều khiển riêng. Không tự coi ba test trên đã bao phủ transaction retry.

## 20. Kiểm thử cancellation, error recovery và concurrency

### 20.1. Test cancellation theo hành vi của phiên bản Spring đang chạy

Tạo một service test cố ý phát nhiều bản ghi trong một transaction và cancel upstream sau phần tử đầu tiên:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Flux<ReservationDocument> reserveTwo(
        ReservationDocument a,
        ReservationDocument b) {

    return Flux.just(a, b)
        .concatMap(template::insert);
}
```

Caller:

```java
StepVerifier.create(service.reserveTwo(a, b).take(1))
    .expectNextCount(1)
    .verifyComplete();
```

**Không lấy `verifyComplete` của Publisher đã `take(1)` làm bằng chứng transaction commit.** Với reactive transaction cancellation rollback semantics, upstream có thể bị hủy sau phần tử đầu và transaction bị rollback. Hãy đọc lại MongoDB sau khi cleanup để xác nhận document nào đã được commit. Không assert một hành vi timing cụ thể mà chưa kiểm soát được cancellation và cách TransactionalOperator xử lý nó trong phiên bản Spring thực tế.

### 20.2. Test nuốt lỗi onErrorResume

Viết một biến thể test service:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<String> wrongRecoveringMethod() {
    return template.updateFirst(query, update, StockDocument.class)
        .then(Mono.<String>error(
            new IllegalStateException("Failure after update")))
        .onErrorResume(ex -> Mono.just("RECOVERED"));
}
```

Trong code này `query`/`update` là biến đã xây ở scope phù hợp. Kiểm tra stock sau completion: nếu update khớp và không có lỗi commit, transaction có thể đã **commit update** vì signal cuối là success. Sau đó sửa method để propagate error và chứng minh stock được rollback.

Đây là một **test chứng minh anti-pattern**, không phải code nên đưa vào production.

### 20.3. Test concurrency và giới hạn parallel statements

Đừng kiểm tra parallel behavior bằng một phép thử may rủi rồi kết luận “`Mono.when` đôi lúc vẫn chạy được nên an toàn”. MongoDB transactions không hỗ trợ parallel operations trên cùng session theo cách tùy tiện; giữ thứ tự transaction bằng `then`/`concatMap` và kiểm tra luồng dữ liệu/nguy cơ race qua code review.

Khi nhiều **transaction khác nhau** cập nhật cùng stock đồng thời, server có thể phát write conflict; ứng dụng phải phân loại lỗi transaction và retry có giới hạn theo business semantics. Đừng đặt một vòng retry vô hạn chỉ để test chạy qua.

### 20.4. Test session/factory mismatch

Trong ứng dụng có hai `ReactiveMongoTemplate` trỏ hai factories, tạo test ghi vào hai collection bằng hai templates dưới **một** `@Transactional`. Xác minh không được **tự mặc định** cả hai ghi nằm trong cùng transaction. Mục tiêu test là phát hiện configuration sai, không phải biến hai MongoClients độc lập thành distributed transaction.

## 21. Chẩn đoán lỗi khi @Transactional không hoạt động

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Gọi method trả `Mono` nhưng MongoDB không có record | Không subscribe | Dùng WebFlux return Publisher hoặc `StepVerifier.verifyComplete()` |
| Chỉ một trong hai write rollback | Một thao tác nằm ngoài reactive chain hoặc dùng factory/client khác | Tìm `subscribe()` nội bộ, blocking MongoTemplate, bean `@Qualifier` sai |
| `@Transactional` tồn tại nhưng method vẫn không atomic | Chưa có reactive manager/proxy, self-invocation | Kiểm tra bean manager, AOP interception, integration test |
| Nhận lỗi kiểu transaction unsupported/transaction numbers | Kết nối standalone hoặc topology chưa hỗ trợ | Dùng replica set/sharded cluster hỗ trợ transactions |
| Transaction lỗi vì read preference | Dùng secondary routing không phù hợp giao dịch | Kiểm tra client/factory read preference và transaction options |
| Trong method có lỗi nhưng stock vẫn giảm | `onErrorResume` biến lỗi thành normal completion | Propagate unchecked error ra transactional boundary |
| Publisher đã phát receipt nhưng commit chưa chắc chắn | Tự gửi side effect trong `doOnNext` trước terminal completion | Chỉ xác nhận sau completion; dùng outbox khi cần |
| `take(1)` trả một item nhưng DB không có ghi | Cancel upstream khiến transaction rollback | Tránh hủy `Flux` transactional trước completion; đọc lại DB |
| `Mono.when`/`zip` khiến driver báo lỗi session/transaction | Các DB statements được chạy parallel trong cùng transaction | Dùng `then` hoặc `concatMap` tuần tự |
| `retryWhen` làm reservation bị thực hiện lại | Resubscribe toàn Publisher, có thể xảy ra sau commit unknown | Phân loại TTE/UTCR; idempotency và reconciliation |
| Một service có hai managers, dùng nhầm manager | Imperative và reactive manager lẫn nhau | Chỉ định `transactionManager="reactiveMongoTransactionManager"` |
| `save` không lỗi dù reservation ID đã tồn tại | `save` có thể update thay vì create-only | Dùng `insert` hoặc unique create logic đúng hợp đồng |
| Reactive app bị block/timeout bất thường | Gọi `MongoTemplate` blocking trên event loop | Dùng reactive driver/template; không trộn blocking MongoDB |
| Transaction mở quá lâu | `Flux` không kết thúc, chờ network/external service | Rút ngắn transaction; tách side effects và batch |
| Test mock xanh nhưng production rollback sai | Mock không xác minh session/server semantics | Chạy test thật trên MongoDB replica set và kiểm tra BSON |
| Trả “failed” cho thao tác đã commit | ACK commit bị mất; client retry whole workflow | Reconcile theo operation ID, không coi timeout là abort chắc chắn |

### 21.1. Quan sát Reactor Context một cách an toàn

Để debug propagation, có thể dùng `Mono.deferContextual(...)`:

```java
return Mono.deferContextual(contextView -> {
    diagnostics.recordContextPresent(
        !contextView.isEmpty());
    return reactiveMongoTemplate.findById(
        id, StockDocument.class);
});
```

Đây là ví dụ trong method với `diagnostics` và `id` có sẵn. **Reactor Context có dữ liệu không đồng nghĩa transaction tồn tại**; nhiều thư viện sử dụng context cho tracing/security. Không đọc các internal keys của Spring transaction rồi phụ thuộc vào cấu trúc không được công bố như API ổn định.

Một cách kiểm chứng tốt hơn là integration test có một write rồi một lệnh lỗi, sau đó đọc lại để xác nhận **tất cả đã rollback**. Logging context chỉ là tín hiệu phụ.

### 21.2. Theo dõi transaction lifecycle

Các metrics hữu ích:

- `reactive_tx_started_total`, `reactive_tx_committed_total`, `reactive_tx_rolled_back_total`.
- `reactive_tx_cancelled_total` phân biệt cancellation của HTTP client, timeout và `take`.
- `reactive_tx_duration_seconds`, số lượng active transactions, tỉ lệ write conflicts.
- `mongo_tx_commit_unknown_total` và reconciliation backlog theo operation type.
- Thời gian chờ server selection và độ trễ commit.
- Số lệnh MongoDB chạy ngoài transaction khi lẽ ra thuộc cùng nghiệp vụ (qua tracing/test/command monitoring).

Không gắn user ID/operation ID làm **nhãn metric có cardinality cao**. Với log/traces có kiểm soát, dùng correlation ID an toàn; không log raw session identifiers, token hay dữ liệu nhạy cảm.

### 21.3. Không bật debug log chứa bí mật

Log driver/MongoDB có thể mang tên collection, query hoặc giá trị tham số tùy cấu hình. Khi điều tra transactions, cần redaction, giới hạn truy cập và retention policy. Không bật debug toàn bộ MongoDB traffic trên production rồi vô tình ghi payload nhạy cảm.

## 22. Đánh giá hiệu năng của reactive transactions

Reactive giúp ứng dụng sử dụng tài nguyên thread hiệu quả với I/O không chặn, nhưng **không làm transaction tự chạy nhanh hơn MongoDB**. Các thao tác vẫn được server xử lý theo transaction semantics và chịu chi phí snapshot, logging, replication, commit.

### 22.1. So sánh các cách ghi

| Bài toán | Cách thường phù hợp |
| --- | --- |
| Cập nhật một stock record có condition | Single-document atomic update, không nhất thiết transaction |
| Update stock và insert reservation phải cùng thành bại | Reactive transaction ngắn |
| Ghi hàng nghìn events không phụ thuộc nhau | Batch writes có checkpoint/idempotency, cân nhắc bulk |
| Phát event ra broker sau commit | Outbox và dispatcher, không đặt broker call trong transaction |
| Báo cáo Flux hàng triệu documents | Query với paging/stream và read consistency phù hợp, tránh transaction kéo dài |

### 22.2. Các yếu tố cần đo

1. Thời gian bắt đầu session/transaction, số operations bên trong.
2. Commit latency theo write concern đã chọn.
3. Write-conflict rate và số lần retry whole transaction.
4. Tỉ lệ cancellation khi client disconnect.
5. Memory/backpressure của một `Flux` dài.
6. Kích thước document, index của conditional update.
7. Connection pool saturation và server selection timeout.
8. Tỉ lệ commit outcome unknown và thời gian reconciliation.

Đừng tối ưu bằng cách thêm `parallel()` hoặc `flatMap(..., concurrency=16)` cho các statements bên trong **cùng session transaction**. Với DB transaction, đúng thứ tự và khả năng retry an toàn thường quan trọng hơn tối đa hóa concurrency trong một transaction.

### 22.3. Conditional update cần index phù hợp

Nếu stock được tìm bằng `_id`, MongoDB đã có index `_id`. Nhưng trong hệ thống dùng business key khác:

```javascript
db.stock_items.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_tenant_sku" }
)
```

Index này có thể giúp lookup/conditional update theo tenant+sku, đồng thời bảo vệ uniqueness business key. Nó **không** thay transaction cho hai document, và không tự xử lý retry/commit unknown.

## 23. Checklist trước khi merge mã

1. **Hợp đồng method:** method transactional trả `Mono<T>`/`Flux<T>` hoặc Publisher phù hợp.
2. **Reactive manager:** có `ReactiveMongoTransactionManager` đúng factory; không nhầm manager imperative.
3. **Proxy:** invocation đi qua Spring bean proxy; không phải self-invocation.
4. **Subscription:** Publisher được controller/caller/test subscribe, không bỏ quên.
5. **Không detached:** không có `subscribe()` bên trong transaction business method.
6. **Không blocking:** không gọi `block()`, blocking MongoTemplate hay ngoại API blocking trong reactive flow.
7. **Cùng factory:** repository/template tham gia cùng Reactor Context/session.
8. **Tuần tự:** các DB statements trong transaction được compose với `then`/`flatMap` tuần tự/`concatMap`.
9. **Không swallow error:** domain failure đi qua transaction boundary để rollback.
10. **Checked error rules:** nếu cần rollback cho checked exception, đã cấu hình `rollbackFor` hoặc domain exception phù hợp.
11. **Cancellation:** hiểu tác động `take`, timeout, disconnect và `Flux` dài.
12. **Receipt sau commit:** không gửi externally visible “đã thành công” trước terminal completion.
13. **Idempotency:** cùng operation ID dùng lại qua HTTP retries và resubscriptions có chủ đích.
14. **Không retry mù:** phân biệt TTE trong body với UTCR khi commit; không `retryWhen` mọi lỗi.
15. **Outbox:** external side effects cần giao hàng bền vững không nằm trong MongoDB transaction callback.
16. **Read preference:** transaction không bị route qua secondary không được hỗ trợ.
17. **Transaction scope:** không mở transaction trên streaming vô hạn hoặc chờ remote API.
18. **Test thật:** có MongoDB replica set test và kiểm tra dữ liệu sau commit/rollback.
19. **Test edge cases:** duplicate key, không đủ stock, cancellation, failover, concurrent writers, commit unknown.
20. **Quan sát:** logs/metrics phân biệt started/committed/rolledback/cancelled/unknown.

## 24. Bài tập thực hành

Một ứng dụng đặt phòng có collection `rooms` và `bookings`. API nhận `bookingId` ổn định, `roomId`, `tenantId` và khoảng ngày cần giữ phòng.

### Bài tập 1 — Phân biệt eager và lazy

Xét:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Booking> book(BookingRequest request) {
    audit.log("method invoked");
    return reactiveMongoTemplate.insert(
        new Booking(request.bookingId(), request.roomId()));
}
```

Giải thích:

1. `audit.log(...)` có thể chạy ở thời điểm nào?
2. Lệnh insert MongoDB thường thực thi khi nào?
3. Điều gì xảy ra nếu caller chỉ lưu Publisher vào biến rồi không subscribe?
4. Nếu hai subscriber cùng subscribe vào Publisher cold, có thể có mấy attempt đặt phòng?
5. Sửa code bằng `Mono.defer` khi cần trì hoãn tính toán, đồng thời giữ `bookingId` ổn định.

### Bài tập 2 — Viết service transactional

Yêu cầu trong **một** reactive MongoDB transaction:

- Conditional update `rooms.available >= requestedRooms`, trừ số phòng còn.
- Insert `bookings` với `bookingId` từ request.
- Trả `Mono<BookingReceipt>` khi thành công.
- Nếu không đủ phòng, phát unchecked error; nếu insert booking duplicate, rollback update rooms.

Viết với cả:

1. `@Transactional` trên method `Mono<BookingReceipt>`.
2. `TransactionalOperator.transactional(work)`.

Không dùng `subscribe()`/`block()`, không chạy hai MongoDB statements bằng `Mono.when` và không gửi email trong transaction.

### Bài tập 3 — Sửa anti-pattern

Đoạn code:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<BookingReceipt> bookWrong(BookingRequest req) {
    reactiveMongoTemplate.insert(
        new AuditEvent("start")).subscribe();

    return Mono.when(
        decrementAvailableRooms(req),
        insertBooking(req)
    )
    .thenReturn(new BookingReceipt(req.bookingId()))
    .onErrorResume(ex ->
        Mono.just(new BookingReceipt("ignored-error")));
}
```

Chỉ ra ít nhất **bốn lỗi**:

- Detached subscribe của audit.
- Two DB operations concurrent trong cùng transaction.
- `onErrorResume` che lỗi khiến transaction có thể commit partial update.
- Trả receipt “ignored-error” dù nghiệp vụ không thành công.
- Không xét retry/idempotency, duplicate booking ID.

Sửa bằng `then`/`flatMap` tuần tự, error propagation, idempotency key và outbox nếu cần audit/event durable.

### Bài tập 4 — Cancellation và WebFlux

Viết một method `@Transactional` trả `Flux<Booking>` tạo ba bookings tuần tự. Sau đó so sánh:

```java
StepVerifier.create(service.bookThree(requests))
    .expectNextCount(3)
    .verifyComplete();
```

với:

```java
StepVerifier.create(service.bookThree(requests).take(1))
    .expectNextCount(1)
    .verifyComplete();
```

Đọc lại MongoDB sau mỗi test. Nêu lý do không nên dùng việc nhận một phần tử làm bằng chứng transaction đã commit. Thiết kế lại API thành `Mono<BatchBookingReceipt>` khi cần all-or-nothing cho cả ba booking.

### Bài tập 5 — Retry và commit outcome unknown

Một lệnh booking gửi commit rồi mất kết nối:

```text
body writes complete
commitTransaction sent
acknowledgment lost
UnknownTransactionCommitResult
```

Giải thích tại sao đoạn sau nguy hiểm:

```java
service.book(request)
    .retryWhen(Retry.max(5));
```

Đề xuất cách dùng `bookingId`/unique key, retry commit trong đúng transaction/session khi driver/manager hỗ trợ, và reconciliation với trạng thái `PENDING_CONFIRMATION` nếu không thể kết luận outcome. Phân biệt với lỗi `TransientTransactionError` trong body, nơi có thể retry toàn transaction trên attempt mới nếu idempotent và còn budget.

### Bài tập 6 — Kiểm thử tích hợp

Tạo test environment replica set riêng và viết `StepVerifier` xác minh:

1. Book thành công: rooms giảm và bookings tồn tại.
2. Duplicate booking ID: rooms không giảm thêm.
3. Không đủ phòng: không tạo booking.
4. `onErrorResume` đặt sai trong method có thể làm commit update không mong muốn.
5. `take(1)`/cancel được xử lý theo transaction semantics thực tế.
6. Method gọi qua self-invocation không có bảo đảm proxy transaction.
7. Hai templates thuộc hai database factories không tự chung một transaction.
8. Lỗi commit chưa xác định cần test chuyên biệt với fault injection, không được tự suy từ một timeout tùy ý.

Không chạy failpoint hoặc `dropDatabase` trên production; chỉ test khi cluster và quyền đã được kiểm soát.

## 25. Tài liệu tham khảo

- Spring Framework — [Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, interception và rollback rules.
- Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionalOperator` và reactive transaction scope.
- Spring Framework — [Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): kiểm soát rollback cho unchecked/checked exceptions.
- Spring Data MongoDB — [Client Session & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `ReactiveMongoTransactionManager`, session và transactions.
- Spring Data MongoDB — [Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `ReactiveMongoTemplate` và Spring Data mapping.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscription, Reactor Context, error handling, cancellation và backpressure.
- Project Reactor Test — [StepVerifier](https://projectreactor.io/docs/test/release/reference/): kiểm thử Publisher đến terminal signal.
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/): topology, atomicity, giới hạn và session.
- MongoDB Java Reactive Streams Driver — [Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write-operations/transactions/): transaction session và driver behavior.

## Ghi nhớ

**`@Transactional` trên phương thức trả về `Mono` hoặc `Flux` tạo transaction scope khi Publisher được subscribe và được Spring quản lý qua Reactor Context, không phải lúc method vừa được gọi để lắp pipeline.** Các `ReactiveMongoTemplate`/repository operations cần nằm trong **cùng reactive chain, cùng factory/session và được thực thi tuần tự**. Completion khiến manager cố commit; lỗi theo rollback rule hoặc cancellation có thể khiến rollback. Tránh `subscribe()` nội bộ, `block()`, self-invocation, `Mono.when` cho DB statements trong cùng transaction và `onErrorResume` nuốt lỗi. Không dùng `retryWhen` vô điều kiện để replay toàn nghiệp vụ khi commit outcome chưa biết. Để đưa vào production, cần replica set, test `StepVerifier` đọc lại BSON sau commit/rollback, idempotency key, outbox khi có external side effects và monitoring cho lỗi/cancel/commit unknown.
