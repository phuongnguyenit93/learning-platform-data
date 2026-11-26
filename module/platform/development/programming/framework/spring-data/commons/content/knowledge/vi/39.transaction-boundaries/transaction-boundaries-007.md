# Giao dịch reactive dựa vào ngữ cảnh thay vì giả định gắn với luồng

Một chuỗi reactive có thể bắt đầu xử lý trên luồng nhận HTTP, tiếp tục trên luồng của driver và chạy bước chuyển đổi dữ liệu trên một scheduler khác. Ngược lại, một luồng có thể phục vụ nhiều yêu cầu khác nhau. Vì vậy, tên luồng không đủ để xác định các thao tác dữ liệu đang thuộc cùng giao dịch hay không.

Trong chương **Ranh giới giao dịch** của module **SPRING_DATA_COMMONS**, bài học này tập trung vào cách duy trì một đơn vị công việc reactive bằng ngữ cảnh thực thi và cấu trúc pipeline. Các abstraction Repository và CRUD giúp mô tả thao tác dữ liệu; việc phối hợp giao dịch còn phụ thuộc transaction manager, store module, driver và cách các publisher được nối với nhau.

## 1. Thay đổi cách xác định phạm vi giao dịch

### 1.1. Mô hình imperative thường gắn tài nguyên với luồng

Với giao dịch imperative của Spring, `PlatformTransactionManager` thường quản lý tài nguyên được liên kết với luồng thực thi. Trong phạm vi đó, các thành phần truy cập dữ liệu tương thích có thể tìm thấy tài nguyên giao dịch hiện hành.

Mô hình này không đồng nghĩa rằng tự tạo một luồng mới sẽ mang theo giao dịch của luồng cũ.

### 1.2. Mô hình reactive gắn trạng thái với ngữ cảnh subscriber

Với `ReactiveTransactionManager`, Spring sử dụng **Reactor Context** để duy trì trạng thái giao dịch thay vì dựa vào các thuộc tính thread-local. Các thao tác tham gia phải thực thi trong pipeline có ngữ cảnh giao dịch phù hợp. Đây là khác biệt cốt lõi được mô tả trong [cơ chế transaction khai báo của Spring](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).

Có thể đối chiếu như sau:

| Câu hỏi | Giao dịch imperative thường dùng | Giao dịch reactive |
| --- | --- | --- |
| Abstraction quản lý | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Nơi liên kết trạng thái | Thường là luồng hiện tại | Reactor Context của chuỗi subscriber |
| Phạm vi cần theo dõi | Lời gọi đồng bộ qua ranh giới transactional | Pipeline thực sự được subscribe và thực thi |
| Cùng một luồng có đủ chứng minh cùng giao dịch không? | Vẫn phải xét tài nguyên và cấu hình | Không |
| Đổi luồng có tự tạo giao dịch mới không? | Không; giao dịch hiện tại cũng không tự truyền sang luồng mới | Không; đổi scheduler trong pipeline Reactor thông thường không tự tách ngữ cảnh |

Từ đây có hai nguyên tắc thực hành:

- Không kết luận “cùng giao dịch” chỉ vì hai câu log có cùng tên luồng.
- Không kết luận “mất giao dịch” chỉ vì hai bước của pipeline có tên luồng khác nhau.

Cần kiểm tra ranh giới transactional, subscription, ngữ cảnh và tài nguyên truy cập dữ liệu thực tế.

## 2. Tách việc lắp ghép pipeline khỏi việc thực thi

Xét lời gọi:

```java
Mono<Reservation> result = reservationService.reserve(command);
```

Với pipeline dữ liệu lazy thông thường, lời gọi này chủ yếu tạo và trả về một mô tả công việc. Nó không có nghĩa là các câu lệnh cập nhật đã chạy và giao dịch đã commit.

```text
Lắp ghép pipeline
        |
        v
Trả về Mono hoặc Flux
        |
        v
Một subscriber đăng ký thực thi
        |
        v
Thiết lập hoặc tham gia giao dịch reactive
        |
        v
Thực hiện các thao tác dữ liệu trong phạm vi đó
        |
        v
Hoàn tất, lỗi hoặc hủy -> xử lý kết thúc giao dịch tương ứng
```

Trong ứng dụng WebFlux, hạ tầng web thường đảm nhiệm subscription cuối cùng của publisher được trả về. Tầng dịch vụ nên trả lại pipeline cho bên gọi thay vì tự `subscribe()` để kích hoạt công việc rồi trả một giá trị thành công khác.

### 2.1. `Mono.defer` trì hoãn việc tạo công việc theo subscription

```java
Mono<Reservation> work = Mono.defer(() -> {
    // Tạo đối tượng và các bước xử lý cho lần subscription này.
    return buildReservationPipeline();
});
```

`buildReservationPipeline()` ở đây đại diện cho một hàm trả về pipeline nghiệp vụ, không phải lời gọi tự subscribe bên trong.

`defer` hữu ích khi việc tạo công việc cần diễn ra tại thời điểm thực thi hoặc khi mỗi subscription cần đối tượng mutable riêng. Nó không tự mở transaction; vẫn cần một ranh giới transactional phù hợp.

### 2.2. Một biến publisher không đồng nghĩa một lần thực thi

Nếu publisher là cold và có tác dụng ghi dữ liệu, subscribe hai lần có thể thực hiện nghiệp vụ hai lần. Mỗi lần thực thi có thể có một phạm vi giao dịch riêng nếu không tham gia giao dịch bao ngoài.

Vì thế, không subscribe một lần “để log” rồi trả publisher đó cho WebFlux subscribe lần nữa. Với thao tác cần chống lặp, phải có chiến lược idempotency hoặc ràng buộc nghiệp vụ tương ứng; transaction không tự nhận diện các subscription là cùng một yêu cầu.

## 3. Hiểu Reactor Context đủ để giữ đúng phạm vi

Reactor Context là dữ liệu ngữ cảnh gắn với subscriber. Nó không phải biến toàn cục, không phải một trường dùng chung của service và không phải một `ThreadLocal` do ứng dụng tự sao chép.

Context có tính bất biến: thao tác cập nhật tạo ra một context mới. `contextWrite` cung cấp ngữ cảnh cho phần upstream tương ứng tại thời điểm subscribe; `deferContextual` đọc context khi thực thi. Có thể xem mô hình truyền ngữ cảnh trong [tài liệu Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).

Ví dụ sau chỉ dùng metadata của yêu cầu để quan sát nguyên tắc đó:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> requestId = Mono.just("start")
        .publishOn(Schedulers.parallel())
        .flatMap(ignored -> Mono.deferContextual(context -> {
            String id = context.get("requestId");
            return Mono.just(id);
        }))
        .contextWrite(context -> context.put("requestId", "req-42"));
```

Trong pipeline này, bước sau `publishOn` vẫn có thể đọc metadata của subscription. Tuy nhiên, key `requestId` chỉ là metadata minh họa; đặt một chuỗi có tên `transactionId` vào context cũng không tạo ra giao dịch cơ sở dữ liệu.

Trạng thái giao dịch thực được Spring và các thành phần truy cập dữ liệu phối hợp quản lý. Ứng dụng không nên tự dựng, sửa hoặc sao chép các key nội bộ để giả lập transaction propagation.

Cũng không nên thay toàn bộ context bằng một context rỗng chỉ để thêm metadata riêng, vì có thể loại bỏ thông tin mà thư viện khác cần. Khi thêm dữ liệu ứng dụng, hãy giữ lại context hiện hữu và sử dụng key tránh xung đột.

## 4. Chọn transaction manager đúng với store và API

Một phương thức trả `Mono` chưa chứng minh rằng toàn bộ thao tác bên trong dùng truy cập dữ liệu reactive.

Ví dụ, bọc một lời gọi JPA blocking bằng `Mono.fromCallable` không làm JPA trở thành repository reactive. `JpaTransactionManager` không tự trở thành transaction manager cho R2DBC chỉ vì giá trị trả về được bọc trong `Mono`.

| Thành phần thực thi | Hướng quản lý giao dịch cần đánh giá |
| --- | --- |
| JPA hoặc JDBC blocking | Transaction imperative với manager phù hợp |
| Spring Data R2DBC | Transaction reactive với manager quản lý đúng `ConnectionFactory` |
| Reactive MongoDB | Transaction manager reactive dành cho MongoDB cùng điều kiện triển khai hỗ trợ transaction |
| API HTTP hoặc email | Không tự tham gia transaction cục bộ của repository |
| Một store khác có repository reactive | Kiểm tra khả năng giao dịch và tích hợp của chính store đó |

Spring Data Commons cung cấp các abstraction dùng chung, không cam kết mọi store có cùng mức isolation, cùng phạm vi transaction hoặc cùng hỗ trợ giao dịch nhiều bản ghi.

### 4.1. Cấu hình minh họa với R2DBC

Các phần tiếp theo giả định:

1. Ứng dụng dùng Spring Data R2DBC và driver R2DBC thích hợp.
2. Cơ sở dữ liệu hỗ trợ các thao tác giao dịch cần dùng.
3. Các repository trong ví dụ cùng sử dụng một `ConnectionFactory` được quản lý nhất quán.
4. Entity, schema và repository scanning đã được cấu hình.

Một cấu hình transaction tối thiểu theo ý tưởng:

```java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveTransactionConfiguration {

    @Bean("reactiveTransactionManager")
    ReactiveTransactionManager reactiveTransactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            @Qualifier("reactiveTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

Đoạn cấu hình giả định ứng dụng chỉ có một `ConnectionFactory` phù hợp để inject tại đây. Nếu có nhiều factory, phải chỉ định chính xác factory và manager cho từng nhóm repository; không chọn dựa trên tên cơ sở dữ liệu trong suy nghĩ của người viết code.

Nếu môi trường đã tự cấu hình manager tương ứng, cần dùng hoặc điều chỉnh cấu hình sẵn có thay vì tạo bean trùng lặp không có chủ đích.

Với R2DBC, việc lấy connection phải đi qua hạ tầng có khả năng tham gia giao dịch. Tự lấy một connection độc lập bằng API thấp rồi sử dụng riêng có thể bỏ qua tài nguyên đang được Spring quản lý. Xem thêm [kiểm soát kết nối và giao dịch R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html#r2dbc-connection).

## 5. Giữ toàn bộ đơn vị công việc trong một pipeline

Giả sử nghiệp vụ giữ hàng cần:

1. Đọc tồn kho của sản phẩm.
2. Kiểm tra và giảm lượng tồn khả dụng.
3. Lưu tồn kho mới.
4. Tạo bản ghi giữ hàng.

Bất biến mong muốn: nếu thao tác tạo giữ hàng thất bại, không để lại riêng thay đổi giảm tồn của cùng lần thực thi đó.

Hai repository minh họa:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {
}
```

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ReservationRepository
        extends ReactiveCrudRepository<Reservation, Long> {
}
```

Domain giả định:

- `Inventory.reserve(quantity)` kiểm tra số lượng dương, từ chối nếu thiếu hàng rồi cập nhật đối tượng tồn kho.
- `Inventory.getId()` trả ID sản phẩm trong ví dụ đơn giản này.
- `Reservation.pending(productId, quantity)` tạo entity mới với chiến lược nhận diện entity mới phù hợp mapping của R2DBC.
- Entity và schema được ánh xạ cho cùng cơ sở dữ liệu.

Dịch vụ sử dụng `TransactionalOperator`:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReservationService {

    private final InventoryRepository inventory;
    private final ReservationRepository reservations;
    private final TransactionalOperator transactions;

    public ReservationService(
            InventoryRepository inventory,
            ReservationRepository reservations,
            TransactionalOperator transactions) {
        this.inventory = inventory;
        this.reservations = reservations;
        this.transactions = transactions;
    }

    public Mono<Reservation> reserve(ReserveCommand command) {
        return reservationWork(command)
                .as(transactions::transactional);
    }

    private Mono<Reservation> reservationWork(ReserveCommand command) {
        return Mono.defer(() -> {
            if (command.quantity() <= 0) {
                return Mono.error(new IllegalArgumentException(
                        "Số lượng giữ hàng phải dương"));
            }

            return inventory.findById(command.productId())
                    .switchIfEmpty(Mono.error(
                            new IllegalArgumentException(
                                    "Không tìm thấy tồn kho")))
                    .flatMap(item -> {
                        item.reserve(command.quantity());
                        return inventory.save(item);
                    })
                    .flatMap(savedInventory -> reservations.save(
                            Reservation.pending(
                                    savedInventory.getId(),
                                    command.quantity())));
        });
    }

    public record ReserveCommand(long productId, int quantity) {
    }
}
```

Các lớp entity không được triển khai đầy đủ ở đây; code tập trung vào quan hệ giữa repository, pipeline và ranh giới giao dịch.

Những điểm cần đọc đúng:

- `reservationWork` trả về công việc lazy cho mỗi subscription.
- `flatMap` nối publisher của từng thao tác vào cùng luồng xử lý.
- `.as(transactions::transactional)` bao quanh phần việc đọc, kiểm tra và ghi ở upstream.
- Dịch vụ không gọi `subscribe()` hoặc `block()`.
- Lỗi không bị đổi thành kết quả thành công bên trong phần việc được bao giao dịch.

`TransactionalOperator` là API theo chương trình được Spring cung cấp cho transaction reactive; xem [cách sử dụng operator](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html#tx-prog-operator).

### 5.1. Nguyên tử không thay thế kiểm soát cạnh tranh

Hai yêu cầu vẫn có thể cùng đọc một lượng tồn cũ nếu chưa có cơ chế kiểm soát cạnh tranh. Ví dụ cần bổ sung optimistic locking qua version được R2DBC hỗ trợ, cập nhật có điều kiện hoặc chiến lược phù hợp cơ sở dữ liệu.

Giả sử dùng optimistic locking, xung đột cập nhật phải làm thất bại đơn vị công việc và rollback thay đổi liên quan. Nếu cần retry, phải đọc và kiểm tra lại trong một lần thực thi mới; không dùng lại quyết định giảm tồn đã tính từ dữ liệu cũ.

Context giúp phối hợp phạm vi giao dịch; nó không tự tạo khóa hoặc nâng isolation cho mọi truy vấn.

## 6. Dùng `@Transactional` theo mô hình reactive

Có thể chọn annotation để diễn đạt ranh giới thay cho việc bọc `TransactionalOperator` trong phương thức `reserve` ở trên:

```java
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Transactional(transactionManager = "reactiveTransactionManager")
public Mono<Reservation> reserve(ReserveCommand command) {
    return reservationWork(command);
}
```

Đây là **phương án thay thế** cho phương thức public cùng tên trong ví dụ, dùng lại helper `reservationWork`; không thêm hai phương thức có cùng chữ ký vào cùng lớp.

Các điều kiện quan trọng:

- Lời gọi phải được hạ tầng transaction của Spring xử lý, thường thông qua Spring AOP proxy.
- Transaction manager được chọn phải hỗ trợ mô hình reactive của pipeline.
- Phương thức trả lại publisher chứa toàn bộ phần việc cần phối hợp.
- Các thao tác dữ liệu phải dùng thành phần có khả năng tham gia transaction đó.

Trong chế độ proxy thông thường, tự gọi một phương thức annotated bằng `this.reserve(...)` không tự đi qua proxy. Tự tạo service bằng `new` cũng không tự nhận xử lý transaction của Spring.

Không đặt annotation trên một phương thức `void`, tự subscribe bên trong rồi kỳ vọng manager reactive giữ giao dịch sống cho công việc đã tách ra.

Khi chọn giữa annotation và operator, ưu tiên cách giúp người đọc nhìn rõ ranh giới và dùng đúng manager. Không bọc thêm nhiều lớp transaction chỉ vì nghĩ rằng mỗi lớp sẽ làm bảo đảm mạnh hơn.

## 7. Những cách vô tình tách công việc khỏi giao dịch

### 7.1. Tự `subscribe()` trong service

```java
public Mono<Reservation> reserveIncorrectly(ReserveCommand command) {
    inventory.findById(command.productId())
            .flatMap(item -> inventory.save(item))
            .subscribe();

    return reservations.save(
            Reservation.pending(command.productId(), command.quantity()))
            .as(transactions::transactional);
}
```

Đoạn này chỉ minh họa lỗi cấu trúc, không triển khai đúng quy tắc giữ hàng. Nhánh được subscribe thủ công không mặc định là một phần của subscription mà transaction operator đang bao quanh. Nó còn tạo ra cuộc đua: bên gọi có thể nhận kết quả tạo giữ hàng trước khi nhánh còn lại hoàn tất.

Cách sửa là nối các bước bằng operator và trả một pipeline duy nhất như ví dụ chính. Việc tự truyền một context vào subscription thủ công cũng không tự giải quyết phối hợp hoàn tất, rollback và cancellation của hai subscription độc lập.

### 7.2. Tạo publisher trong `doOnNext` rồi bỏ qua

```java
return inventory.findById(productId)
        .doOnNext(item -> inventory.save(item));
```

`save(item)` trả về publisher, nhưng đoạn trên không nối publisher đó vào pipeline. Với thao tác lazy, việc ghi có thể không chạy. `doOnNext` phù hợp để quan sát tác dụng đồng bộ ngắn như ghi log; nó không thay `flatMap` cho thao tác bất đồng bộ cần được chờ và phối hợp.

```java
return inventory.findById(productId)
        .flatMap(inventory::save);
```

Việc có transaction bên ngoài không sửa được một thao tác chưa được đưa vào công việc thực thi.

### 7.3. Gọi `block()` để lấy kết quả trung gian

```java
Inventory item = inventory.findById(productId).block();
```

`block()` tạo một kiểu chờ đồng bộ và subscription để lấy kết quả. Trong service reactive, điều này có thể tách việc đọc khỏi chuỗi giao dịch mong muốn, giữ luồng chờ và thậm chí bị cấm trên một số luồng non-blocking.

Hãy biểu diễn bước tiếp theo bằng `flatMap`, `then` hoặc operator thích hợp. Không coi `block()` là cách mang Reactor Context trở lại một transaction imperative.

### 7.4. Chuyển JPA sang scheduler khác rồi mong tham gia R2DBC

```java
Mono.fromCallable(() -> jpaRepository.save(entity))
        .subscribeOn(Schedulers.boundedElastic());
```

Cách này có thể được dùng như một phần của chiến lược cô lập lời gọi blocking, nhưng không biến `jpaRepository` thành R2DBC repository và không làm lời gọi JPA tự tham gia transaction R2DBC trong Reactor Context.

Nếu ứng dụng buộc phải phối hợp hai kiểu truy cập, cần xác định ranh giới tài nguyên và cơ chế nhất quán riêng. Thay scheduler chỉ giải quyết vị trí thực thi một phần công việc, không tạo giao dịch nguyên tử liên tài nguyên.

## 8. Vị trí operator quyết định phần việc được bao quanh

Xét hai pipeline sau. `writeA`, `writeB` và `writeC` đại diện cho các publisher ghi dữ liệu lazy.

```java
writeA.then(writeB)
        .as(transactions::transactional)
        .then(writeC);
```

Nếu không có transaction bao ngoài, ranh giới được chỉ ra ở đây bao A và B; không nên coi C cũng nằm trong ranh giới đó chỉ vì C được viết trên cùng một biểu thức Java.

Nếu cả ba thao tác phải cùng một đơn vị công việc:

```java
writeA.then(writeB)
        .then(writeC)
        .as(transactions::transactional);
```

Ngoài vị trí operator, còn phải xét propagation và transaction đang có ở bên ngoài. Cùng cú pháp không có nghĩa mọi bối cảnh gọi đều tạo một giao dịch vật lý mới.

### 8.1. Nối tuần tự khi có phụ thuộc nghiệp vụ

Nếu B phụ thuộc A thành công, dùng `flatMap` để nhận giá trị hoặc `then` để chờ hoàn tất rồi chuyển bước.

Không chọn `zip` chỉ để viết gọn các lệnh ghi. Các nguồn có thể được subscribe đồng thời; một nguồn hoàn tất rỗng cũng có thể làm tổ hợp hoàn tất mà không có kết quả kết hợp như người viết mong đợi. Đặc biệt, `Mono<Void>` không phát giá trị để `zip` tạo một bộ kết quả thông thường.

Ngữ cảnh giao dịch chung cũng không bảo đảm driver cho phép chạy song song nhiều câu lệnh trên cùng connection. Với một nhóm cập nhật cần tuần tự, `concatMap` thường diễn đạt ý định rõ hơn `flatMap` có concurrency.

## 9. Xử lý error và cancellation theo đúng phạm vi

### 9.1. Đừng đổi lỗi thành hoàn tất quá sớm

```java
writeA.then(writeB)
        .onErrorResume(error -> Mono.empty())
        .as(transactions::transactional);
```

Ở đây, phần việc bên trong có thể che mất lỗi trước khi operator giao dịch quan sát được nó. Nếu tài nguyên chưa bị đánh dấu rollback-only, hoàn tất bình thường có thể khiến những thay đổi trước lỗi được commit.

Nếu cần hủy toàn bộ công việc, hãy để lỗi đi qua ranh giới giao dịch theo cơ chế rollback tương ứng, rồi mới chuyển lỗi thành phản hồi cho bên gọi ở tầng ngoài:

```java
writeA.then(writeB)
        .as(transactions::transactional)
        .onErrorResume(error -> mapToFailureResponse(error));
```

`mapToFailureResponse` trong ví dụ là một hàm trả publisher cùng kiểu phù hợp, diễn đạt kết quả thất bại cho tầng ngoài. Nó không được giả báo nghiệp vụ đã thành công. Với annotation, cũng cần xét quy tắc rollback được khai báo cho loại exception thay vì mặc định mọi kiểu lỗi có cùng quy tắc.

### 9.2. Hủy subscription không tương đương commit

Subscriber có thể hủy khi client ngắt kết nối, khi timeout hoặc khi operator phía sau chỉ lấy một phần dữ liệu. Spring mô tả rằng từ phiên bản 5.3, cancellation trong phạm vi `TransactionalOperator` dẫn tới rollback. Các operator như `take`, `next` hoặc `timeout` vì vậy cần được xét cùng ranh giới transaction. Xem [cancel signals trong transaction reactive](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html#tx-prog-operator-cancel).

Ví dụ:

```java
Flux<Reservation> transactionalResults = allWork
        .as(transactions::transactional);

Mono<Reservation> first = transactionalResults.next();
```

Nếu `next()` nhận phần tử đầu rồi hủy upstream trước khi toàn bộ công việc hoàn tất, không được suy ra transaction đã commit chỉ vì đã nhìn thấy một phần tử.

Với publisher nhiều phần tử, `onNext` của một kết quả không phải bằng chứng rằng toàn bộ transaction đã hoàn thành. Cần quan sát cả việc kết thúc phạm vi giao dịch và lỗi có thể xuất hiện ở giai đoạn cuối.

### 9.3. Retry cần chạy lại toàn bộ đơn vị công việc phù hợp

Khi cần retry lỗi tạm thời, phải cân nhắc vị trí retry so với ranh giới transaction. Với một thao tác không có transaction bao ngoài, việc retry publisher đã được bọc transaction có thể tạo lần thực thi mới sau khi lần trước kết thúc thất bại.

Không đặt retry một cách máy móc vào giữa một transaction đã lỗi rồi tiếp tục sử dụng trạng thái cũ. Cần giới hạn số lần, lọc lỗi được phép retry và tạo lại phần việc đọc, kiểm tra, ghi bằng cấu trúc lazy phù hợp.

Retry cũng không giải quyết sự không chắc chắn khi phía client mất kết nối sau khi server có thể đã commit. Đó còn là vấn đề nhận diện yêu cầu, idempotency và đối chiếu trạng thái nghiệp vụ.

## 10. Quan sát đúng vấn đề khi điều tra lỗi

| Hiện tượng | Giả thuyết cần kiểm tra | Bằng chứng nên tìm |
| --- | --- | --- |
| Không có dữ liệu được ghi | Publisher chưa được subscribe hoặc thao tác bị bỏ qua | Pipeline trả về, chỗ dùng `doOnNext`, subscription cuối |
| Chỉ một phần công việc rollback | Có nhánh riêng, operator đặt sai phạm vi hoặc tài nguyên khác | Cấu trúc pipeline, manager và factory thực tế |
| Log đổi tên luồng | Có scheduler hoặc callback driver | Context và ranh giới subscription; không kết luận chỉ từ tên luồng |
| Service trả thành công nhưng có lỗi ghi sau đó | Tự subscribe hoặc tạo tác vụ tách rời | Lời gọi `subscribe`, callback và log lỗi bất đồng bộ |
| Chỉ lấy kết quả đầu rồi thấy rollback | Downstream hủy nguồn transactional | `next`, `take`, timeout và terminal signals |
| Có `Mono` nhưng vẫn chặn luồng | Bên trong dùng API blocking | Loại repository và driver thực tế |
| Hai yêu cầu vẫn tranh chấp tồn kho | Chưa có cơ chế cạnh tranh phù hợp | Version, cập nhật có điều kiện, isolation và ràng buộc dữ liệu |

Có thể gắn correlation ID vào Context để nối log của một yêu cầu qua các bước. Tuy nhiên, cùng correlation ID chỉ cho biết quan hệ theo dõi mà ứng dụng đặt ra; nó không chứng minh rằng hai thao tác sử dụng cùng giao dịch hoặc cùng connection.

Các thao tác derived query, projection, phân trang, sắp xếp và auditing cũng phải được đánh giá theo cùng nguyên tắc: chúng là khả năng truy cập hoặc xử lý metadata của store, không phải cơ chế tự truyền giao dịch qua các subscription độc lập.

## 11. Tình huống thực hành để đọc ranh giới

Giả sử repository tồn kho và repository giữ hàng cùng dùng một tài nguyên R2DBC. Hãy giải thích kết quả mong muốn của các thay đổi sau trên ví dụ chính:

1. Bước lưu giữ hàng phát lỗi sau khi đã lưu tồn kho: cả hai thay đổi thuộc lần thực thi đó phải rollback nếu cùng transaction và lỗi dẫn tới rollback.
2. Thêm `publishOn` vào pipeline Reactor thông thường: không được kết luận giao dịch mất chỉ vì đổi luồng; vẫn phải kiểm tra toàn bộ phạm vi.
3. Thay `flatMap(reservations::save)` bằng `doOnNext` tạo publisher nhưng không dùng: thao tác ghi không còn được phối hợp như trước.
4. Subscribe publisher ghi dữ liệu hai lần: có nguy cơ chạy nghiệp vụ hai lần và cần đánh giá idempotency.
5. Chuyển một repository sang store khác: một context chung không tự tạo transaction phân tán.
6. Thêm `next()` sau một `Flux` transactional: cần xét việc hủy upstream và rollback thay vì chỉ kiểm tra phần tử đã nhận.

Mô hình cần giữ khi đọc code là: **công việc nào được trả về, subscription nào thực thi nó, ngữ cảnh giao dịch nào được cung cấp và tài nguyên nào thực sự tham gia**. Tên luồng là một dữ kiện quan sát; cấu trúc pipeline và hạ tầng transaction mới xác định phạm vi phối hợp của giao dịch reactive.
