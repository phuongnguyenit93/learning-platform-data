# Mono, Flux và các kiểu reactive tương ứng

Một phương thức trả `Mono<PurchaseOrder>` không trả ngay một đơn hàng. Nó trả một publisher có thể cung cấp không có hoặc một đơn hàng, rồi kết thúc thành công hoặc báo lỗi. Một phương thức trả `Flux<PurchaseOrder>` mô tả một chuỗi có thể có nhiều đơn hàng. Nhầm các kiểu này với giá trị đã có sẵn dễ dẫn đến bỏ sót truy vấn chưa được thực thi, xử lý sai trường hợp rỗng hoặc làm tách thao tác dữ liệu khỏi luồng nghiệp vụ.

Trong chương **Kiểu kết quả truy vấn** của **SPRING_DATA_COMMONS**, bài này tập trung vào hợp đồng số lượng kết quả, tín hiệu reactive, cách kết hợp truy vấn và giới hạn hỗ trợ theo module lưu trữ. Các kiểu tương ứng trong RxJava và Kotlin được đối chiếu theo ý nghĩa, không được xem là những tên có thể thay thế tùy ý trên mọi repository.

## 1. Reactive là hợp đồng về tín hiệu, không chỉ một wrapper

Reactor cung cấp `Mono` và `Flux`, cùng tham gia mô hình Reactive Streams. Về mặt khái niệm, subscriber nhận subscription, yêu cầu dữ liệu và có thể quan sát:

```text
Mono<T> thành công có giá trị:
    onNext(value) -> onComplete

Mono<T> thành công nhưng rỗng:
    onComplete

Flux<T> thành công:
    onNext(a) -> onNext(b) -> ... -> onComplete

Có lỗi:
    ... -> onError(error)
```

Một publisher không phát cả `onComplete` rồi lại `onError` như hai kết quả cuối của cùng một subscription. Nếu có hủy subscription, không nên kỳ vọng subscriber vẫn nhận được tín hiệu hoàn tất như một lần xử lý thành công bình thường.

| Kiểu Reactor | Số giá trị có thể phát | Kết thúc thành công | Kết thúc lỗi |
| --- | --- | --- | --- |
| `Mono<T>` | `0` hoặc `1` | Có thể có một giá trị, hoặc rỗng | `onError` |
| `Flux<T>` | `0` đến nhiều giá trị | Hoàn tất sau chuỗi hữu hạn; một số nguồn có thể tiếp tục lâu dài | `onError`, có thể sau một số giá trị đã phát |
| `Mono<Void>` | Không có giá trị dữ liệu | Chỉ biểu đạt hoàn tất | `onError` |

Đối với một truy vấn repository thông thường, `Flux` thường biểu đạt tập kết quả hữu hạn. Bản thân kiểu `Flux` không cam kết nguồn luôn hữu hạn, luôn cold hoặc luôn truy cập cơ sở dữ liệu bằng một thuật toán cụ thể.

Reactive Streams không dùng `onNext(null)` để biểu đạt “không tìm thấy”. Một entity có trường cho phép null là vấn đề mapping khác với việc phát một phần tử null trong publisher.

## 2. Commons và Reactor không tự cung cấp driver reactive cho mọi store

Spring Data Commons cung cấp các abstraction repository reactive, chẳng hạn `ReactiveCrudRepository`, và metadata để module tích hợp xử lý phương thức. Reactor cung cấp kiểu publisher và các toán tử kết hợp. Module lưu trữ cùng driver mới quyết định cách truy cập dữ liệu thực tế.

Cần phân biệt:

```text
Interface repository reactive
          |
          v
Module Spring Data có hỗ trợ reactive
          |
          v
Driver / client reactive của kho dữ liệu
          |
          v
Thực thi truy vấn và ánh xạ kết quả
```

Các ví dụ chính trong bài dùng **Spring Data R2DBC** với một cơ sở dữ liệu và mapping phù hợp. Những chữ ký tương tự có thể có ở module reactive khác, nhưng keyword, kiểu trả về và transaction phải được xác nhận riêng.

Không đổi `JpaRepository` thành repository trả `Mono` rồi mặc định JPA trở thành non-blocking. Một lời gọi blocking vẫn là blocking nếu nó được chạy bên trong một `Mono` mà không có chiến lược thực thi phù hợp.

Ngay cả cách cầu nối như sau cũng chỉ bọc một thao tác blocking:

```java
Mono<PurchaseOrder> result = Mono.fromCallable(
        () -> blockingRepository.findById(id).orElseThrow());
```

`fromCallable` có thể trì hoãn việc gọi, nhưng không tự thay đổi driver hoặc tự chuyển công việc sang một thread phù hợp. Khi phải tích hợp code blocking, đó là một quyết định về ranh giới thực thi, tài nguyên và transaction; nó không tương đương dùng reactive repository nguyên bản.

## 3. Mô hình và repository dùng trong ví dụ

Giả sử `PurchaseOrder` có các thuộc tính Java:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh đơn hàng |
| `tenantId` | `String` | Phạm vi tổ chức |
| `externalCode` | `String` | Mã từ hệ thống bên ngoài |
| `status` | `OrderStatus` | Trạng thái nghiệp vụ |
| `createdAt` | `Instant` | Thời điểm tạo |

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Giả định entity, accessor và cấu hình R2DBC đã được thiết lập phù hợp. Phần mapping được lược bỏ để tập trung vào kiểu kết quả.

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Mono<PurchaseOrder> findByTenantIdAndExternalCode(
            String tenantId,
            String externalCode);

    Flux<PurchaseOrder> findByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
            String tenantId,
            OrderStatus status);

    Mono<Long> countByTenantIdAndStatus(
            String tenantId,
            OrderStatus status);

    Mono<Boolean> existsByTenantIdAndExternalCode(
            String tenantId,
            String externalCode);
}
```

Repository cũng kế thừa các thao tác cơ sở như `findById`, `save`, `count`, `existsById` và `deleteById` theo hợp đồng reactive tương ứng. Việc interface có các kiểu Reactor không thay thế yêu cầu cấu hình đúng module, client và mapping.

## 4. Mono<T>: không có hoặc một kết quả

### 4.1. Không tìm thấy được biểu đạt bằng hoàn tất rỗng

```java
Mono<PurchaseOrder> order = repository.findById(id);
```

Với hợp đồng tìm theo id của `ReactiveCrudRepository`, nếu không có entity thì publisher hoàn tất mà không phát phần tử. Nó không cần phát `null`, cũng không tự phát một exception nghiệp vụ “không tìm thấy”.

Nếu tầng ứng dụng coi không tìm thấy là lỗi, cần diễn đạt chính sách đó:

```java
Mono<PurchaseOrder> requiredOrder = repository.findById(id)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Order not found")));
```

Đây là chuyển đổi từ một kết quả rỗng hợp lệ ở tầng repository sang một lỗi theo hợp đồng ứng dụng. Nó không biến mọi lỗi cơ sở dữ liệu thành “không tìm thấy”.

### 4.2. Mono không có nghĩa truy vấn tự lấy hàng đầu tiên

Xét:

```java
Mono<PurchaseOrder> findByTenantIdAndExternalCode(
        String tenantId, String externalCode);
```

Chữ ký yêu cầu tối đa một kết quả. Trong cơ chế truy vấn đơn kết quả của module ví dụ, nếu dữ liệu khớp nhiều entity thì có thể phát lỗi số lượng kết quả thay vì tự chọn một hàng bất kỳ.

Nếu cặp tenant và mã bên ngoài phải duy nhất, cần ràng buộc dữ liệu phù hợp trong store. `Mono` không tự tạo uniqueness.

Nếu yêu cầu thực sự là lấy một đơn mới nhất trong nhiều đơn, hãy diễn đạt giới hạn và thứ tự ở truy vấn, chẳng hạn với module hỗ trợ:

```java
Mono<PurchaseOrder> findFirstByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId, OrderStatus status);
```

Không thay một truy vấn có yêu cầu uniqueness bằng thao tác chọn phần tử đầu chỉ để che dữ liệu trùng.

### 4.3. Rỗng, false và số không là ba trường hợp khác nhau

| Publisher | Ý nghĩa khi thành công |
| --- | --- |
| `Mono<PurchaseOrder>` rỗng | Không có entity để phát |
| `Mono<Boolean>` phát `false` | Có một giá trị trả lời câu hỏi tồn tại, và giá trị đó là false |
| `Mono<Long>` phát `0L` | Có một kết quả đếm, và kết quả là không có hàng phù hợp |
| `Mono<Void>` hoàn tất | Thao tác hoàn tất nhưng không có giá trị dữ liệu |

Ví dụ `existsById` vẫn phát một giá trị boolean khi câu trả lời là false. `switchIfEmpty` không chạy chỉ vì giá trị boolean là false.

Tương tự, `count()` trả số không không phải một publisher rỗng. Không dùng “có phần tử hay không” để thay thế việc đọc giá trị đếm.

## 5. Flux<T>: nhiều kết quả và thứ tự

```java
Flux<PurchaseOrder> orders = repository
        .findByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                tenantId, OrderStatus.PAID);
```

Nếu không có entity phù hợp, `Flux` hoàn tất mà không phát phần tử. Nếu có nhiều entity, caller xử lý chuỗi phần tử mà không bắt buộc phải gom toàn bộ thành danh sách ngay từ đầu.

Kiểu `Flux` tự nó không tạo thứ tự nghiệp vụ. Trong ví dụ, thứ tự đến từ `OrderByCreatedAtAscIdAsc`. Không có sort rõ ràng thì không mặc định phần tử đầu là mới nhất hoặc có id nhỏ nhất.

Các toán tử chuyển đổi số lượng cần được hiểu đúng:

| Toán tử | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `flux.next()` | `Mono<T>` | Nhận phần tử đầu nếu có; không chứng minh nguồn chỉ có một phần tử |
| `flux.singleOrEmpty()` | `Mono<T>` | Chấp nhận không có hoặc một phần tử, lỗi nếu nhiều hơn một |
| `flux.collectList()` | `Mono<List<T>>` | Gom phần tử rồi phát một danh sách khi nguồn hoàn tất |
| `flux.hasElements()` | `Mono<Boolean>` | Trả lời có phần tử hay không |

Nếu chỉ cần kiểm tra tồn tại, một `existsBy...` được module hỗ trợ thường biểu đạt ý định repository rõ hơn việc tải entity để gọi `hasElements()`.

Nếu chỉ cần một số lượng, một `countBy...` phù hợp giúp store thực hiện phép đếm thay vì ứng dụng nhận mọi entity rồi đếm luồng ở phía client.

## 6. Mono<List<T>> khác Flux<T>

Hai kiểu có thể đưa dữ liệu tương tự đến caller nhưng có hợp đồng phát khác nhau:

```text
Flux<T>:
    T thứ nhất -> T thứ hai -> ... -> hoàn tất

Mono<List<T>>:
    chờ gom xong -> phát một List<T> -> hoàn tất
```

Ví dụ chuyển đổi ở tầng ứng dụng:

```java
Mono<List<PurchaseOrder>> listResult = repository
        .findByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                tenantId, OrderStatus.PAID)
        .collectList();
```

Nếu nguồn hoàn tất mà không có entity, `collectList()` phát một danh sách rỗng. Vì vẫn có một giá trị danh sách, đó không phải `Mono` rỗng.

Hệ quả của `collectList()`:

- Chỉ phát danh sách sau khi nguồn hoàn tất thành công.
- Cần giữ các phần tử đã gom trong bộ nhớ.
- Không phù hợp để gom một nguồn không kết thúc hoặc một tập dữ liệu quá lớn mà không có giới hạn thích hợp.

Không suy từ việc Reactor có thể tạo `Mono<List<T>>` rằng mọi derived repository method đều hỗ trợ trực tiếp chữ ký đó. Danh sách lồng trong wrapper là một hình dạng truy vấn phải được module xác nhận; ví dụ ở đây tạo nó bằng toán tử ở tầng ứng dụng.

## 7. Mono<Void>: hoàn tất không có dữ liệu

Thao tác cơ sở như `deleteById` trả một `Mono<Void>`:

```java
Mono<Void> deletion = repository.deleteById(id);
```

Publisher này không phát một phần tử `Void` hoặc `null` để báo thành công. Thành công được biểu đạt bằng hoàn tất; lỗi được biểu đạt bằng `onError`.

Vì không có `onNext`, phép map dưới đây không tạo ra thông báo thành công:

```java
// Không có phần tử để lambda map xử lý.
Mono<String> message = repository.deleteById(id)
        .map(ignored -> "Deletion completed");
```

Nếu cần một giá trị sau khi thao tác hoàn tất:

```java
Mono<String> message = repository.deleteById(id)
        .thenReturn("Deletion request completed");
```

Thông báo chỉ phản ánh hoàn tất theo hợp đồng của thao tác; nó không tự chứng minh trước đó có một hàng khớp hoặc cho biết số lượng bị xóa.

Hai nhầm lẫn khác cần tránh:

- `switchIfEmpty(...)` sau một `Mono<Void>` có thể chạy ngay cả khi thao tác đã thành công, vì thành công vẫn không có giá trị.
- `Mono.zip(...)` cần giá trị từ các nguồn để tạo tổ hợp; không dùng một nguồn `Mono<Void>` như một giá trị kết quả thông thường rồi kỳ vọng tuple luôn được phát.

Nếu cần nối các thao tác theo thứ tự, dùng toán tử dựa trên hoàn tất như `then(...)`. Nếu chỉ cần chờ nhiều nguồn hoàn tất mà không lấy giá trị, Reactor có các toán tử phù hợp như `Mono.when(...)`; chúng không tự áp đặt thứ tự nghiệp vụ giữa các nguồn.

## 8. Publisher thường trì hoãn thực thi, nhưng kiểu trả về chưa đủ để kết luận

Nhiều thao tác reactive repository tạo publisher có hành vi lazy/cold: công việc dữ liệu được kích hoạt theo subscription thay vì hoàn tất ngay ở dòng gọi Java.

```java
Mono<PurchaseOrder> pending = repository.findById(id);
```

Dòng trên chưa phải bằng chứng rằng truy vấn đã được gửi và kết quả đã được đọc. Nhưng cũng không kết luận mọi lỗi đều phải chờ subscription: lỗi metadata truy vấn có thể xảy ra khi repository khởi tạo; một số kiểm tra đối số có thể lỗi ngay khi gọi.

Cần phân biệt:

```text
Khởi tạo repository và phân giải phương thức
                     |
Gọi phương thức để lấy publisher
                     |
Subscription
                     |
Truy cập store, đọc và chuyển đổi kết quả
                     |
Hoàn tất hoặc lỗi
```

`Mono` hoặc `Flux` nói lên hình dạng tín hiệu, không bảo đảm mọi publisher đều cold, mỗi subscription luôn chia sẻ một kết quả hay thao tác luôn chỉ thực hiện một lần.

### 8.1. Hai subscription có thể là hai lần làm việc

Với một nguồn cold, subscribe lại có thể chạy lại truy vấn. Nếu nguồn là thao tác ghi, tác dụng dữ liệu cũng có thể được thực hiện lại theo implementation và trạng thái cụ thể.

Các toán tử như `retry` có thể đăng ký lại sau lỗi. Vì vậy retry một thao tác ghi cần tính đến idempotency và khả năng lần trước đã tác động dữ liệu trước khi lỗi được quan sát. Kiểu reactive không tạo bảo đảm “đúng một lần” cho mọi thao tác.

### 8.2. Giữ publisher trong luồng được quản lý

Mẫu sau tách thao tác lưu khỏi kết quả mà caller nhận:

```java
repository.save(order).subscribe();
return Mono.just("OK");
```

Caller có thể nhận `OK` trước khi lưu hoàn tất, còn lỗi của subscription tự tạo không còn đi theo cùng luồng trả về.

Hợp đồng gắn với kết quả lưu nên được nối trực tiếp:

```java
return repository.save(order)
        .map(saved -> "OK");
```

Trong một ứng dụng WebFlux điển hình, tầng xử lý trả publisher để framework quản lý subscription tại ranh giới thích hợp. Tầng service/repository nên kết hợp và trả publisher thay vì tự subscribe rải rác.

`block()` cũng là một ranh giới chờ đồng bộ, không phải toán tử làm truy vấn “reactive hơn”. Đặt nó trong luồng xử lý non-blocking có thể làm mất lợi ích của mô hình và vi phạm yêu cầu thực thi của thread đang dùng.

## 9. Kết hợp truy vấn bằng map, flatMap và then

### 9.1. map cho chuyển đổi đồng bộ một giá trị

```java
Mono<Long> orderId = repository.findById(id)
        .map(PurchaseOrder::getId);
```

Nếu không tìm thấy entity, lambda không được gọi và kết quả vẫn rỗng. Nếu mapping có thể không tạo ra giá trị, không trả null từ lambda như một cách biểu đạt rỗng; hãy dùng một cách kết hợp publisher phù hợp với hợp đồng đó.

### 9.2. flatMap khi bước tiếp theo trả publisher

Giả sử `prepareUpdatedOrder(...)` là hàm nghiệp vụ đồng bộ tạo entity đã điều chỉnh:

```java
Mono<PurchaseOrder> updated = repository.findById(id)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Order not found")))
        .flatMap(order -> repository.save(prepareUpdatedOrder(order)));
```

Dùng `map` cho lambda trả `repository.save(...)` sẽ tạo một publisher lồng bên trong publisher, thay vì nối thao tác lưu vào một chuỗi phẳng như mong muốn.

Với nhiều phần tử, `flatMap` có thể xử lý nhiều publisher con đồng thời và làm thứ tự phát khác thứ tự nguồn. Nếu nghiệp vụ cần xử lý lần lượt, có thể cần `concatMap` hoặc một chiến lược khác phù hợp. Đổi toán tử không làm store tự tăng khả năng kết nối hoặc tài nguyên.

### 9.3. then quan tâm đến hoàn tất, không giữ giá trị trước

```java
Mono<PurchaseOrder> secondResult = repository.save(firstOrder)
        .then(repository.save(secondOrder));
```

Luồng chờ bước đầu hoàn tất rồi tiếp tục bước sau, và trả kết quả của bước sau. Giá trị entity từ lần lưu đầu không được chuyển xuống như kết quả cuối.

Nếu bước sau cần dùng id hoặc dữ liệu từ entity đã lưu đầu, dùng `flatMap` để giữ mối liên hệ dữ liệu, thay vì `then` rồi cố đọc lại một biến bên ngoài.

Hai lần lưu được nối tuần tự chưa tự tạo transaction nguyên tử. Tính nguyên tử cần hạ tầng và ranh giới transaction reactive tương ứng.

## 10. Backpressure không phải giới hạn kết quả SQL

Reactive Streams cho phép subscriber biểu đạt nhu cầu nhận dữ liệu. Backpressure giúp phối hợp tốc độ giữa các thành phần hỗ trợ cơ chế đó, nhưng không đồng nghĩa:

- Mỗi yêu cầu một phần tử luôn tương ứng đúng một lần đọc mạng.
- Driver không có prefetch hoặc buffer.
- Cơ sở dữ liệu không phải quét hay sort nhiều hàng.
- Một `Flux` tự giới hạn tổng số entity phù hợp.

Ví dụ:

```java
Flux<PurchaseOrder> preview = repository
        .findByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                tenantId, OrderStatus.PAID)
        .take(10);
```

`take(10)` giới hạn số phần tử mà chuỗi downstream nhận và có thể hủy nguồn sau đó. Không coi nó như lời cam kết rằng mọi module đã thêm đúng `LIMIT 10` vào câu truy vấn hoặc driver chưa từng đọc thêm dữ liệu.

Nếu yêu cầu giới hạn thuộc truy vấn, cần biểu đạt qua `First`/`Top`, `Pageable`, `Limit` hoặc cơ chế store hỗ trợ. Việc hỗ trợ từng cách vẫn phải xem theo module.

Tương tự, `flux.sort(...)` có thể cần giữ dữ liệu để sắp xếp trước khi phát kết quả. Nếu muốn store sắp xếp, hãy dùng cơ chế sort của truy vấn thay vì mặc định toán tử trên luồng sẽ được đẩy xuống cơ sở dữ liệu.

## 11. Transaction reactive cần đúng hạ tầng và phạm vi

Các thao tác được kết hợp trong một publisher chưa mặc định cùng một transaction. Với một store hỗ trợ transaction reactive, có thể dùng một transaction manager reactive phù hợp và một ranh giới như `TransactionalOperator`.

Ví dụ minh họa, giả định `transactionalOperator` đã được cấu hình cho cùng nguồn dữ liệu:

```java
Mono<PurchaseOrder> work = repository.save(firstOrder)
        .then(repository.save(secondOrder));

Mono<PurchaseOrder> transactionalWork = work
        .as(transactionalOperator::transactional);
```

Đây là ví dụ tổ chức phạm vi, không phải cấu hình đầy đủ của ứng dụng. Không suy rằng cùng một đoạn code tạo transaction đa kho dữ liệu hoặc bao phủ mọi dịch vụ bên ngoài.

Transaction reactive gắn với reactive context và vòng đời subscription theo cơ chế hạ tầng. Không áp dụng máy móc giả định transaction imperative dựa trên một thread cố định.

Nếu một bước tự gọi `subscribe()` để chạy một luồng khác, bước đó có thể thoát khỏi phạm vi kết hợp cần quản lý. Nếu một lỗi bị biến thành hoàn tất thành công bằng toán tử phục hồi, hành vi transaction cũng phải được đánh giá theo tín hiệu mà phạm vi transaction thực sự quan sát.

## 12. Xử lý lỗi khác với xử lý kết quả rỗng

Một truy vấn có thể kết thúc theo ba hướng có ý nghĩa khác nhau:

```text
Có dữ liệu
Không có dữ liệu nhưng truy vấn thành công
Truy vấn thất bại
```

Ví dụ mất kết nối, SQL không hợp lệ hoặc lỗi chuyển đổi dữ liệu thuộc nhóm thất bại. Không nên biến toàn bộ chúng thành “không tìm thấy”:

```java
// Làm mất sự khác biệt giữa lỗi hạ tầng và kết quả không có entity.
Mono<PurchaseOrder> hiddenFailure = repository.findById(id)
        .onErrorResume(error -> Mono.empty());
```

Chỉ phục hồi những loại lỗi mà nghiệp vụ có chính sách rõ ràng. `switchIfEmpty` xử lý hoàn tất không có giá trị; `onErrorResume` xử lý tín hiệu lỗi. Chúng không thể thay nhau chỉ vì đều có thể dẫn tới một publisher khác.

Một `try/catch` chỉ bao quanh lúc gọi phương thức lấy publisher không bắt được mọi lỗi sẽ được phát sau subscription. Lỗi reactive cần đi trong chuỗi và được quan sát ở ranh giới tiêu thụ phù hợp.

Với `Flux`, có thể đã có một số entity được phát trước khi nguồn báo lỗi. Nếu tầng ứng dụng đã xử lý tác dụng ngoài cho các entity đó, lỗi cuối không tự thu hồi mọi tác dụng đã diễn ra. Cần thiết kế xử lý theo hợp đồng transaction và idempotency thực tế.

## 13. Các kiểu reactive tương ứng trong hệ sinh thái khác

Các kiểu sau có thể có vai trò gần nhau nhưng không hoàn toàn đồng nhất:

| Nhu cầu | Reactor | RxJava 3 tiêu biểu | Kotlin coroutine tiêu biểu |
| --- | --- | --- | --- |
| Không có hoặc một giá trị | `Mono<T>` | `Maybe<T>` | Hàm `suspend` trả `T?` |
| Bắt buộc một giá trị khi thành công | `Mono<T>` cần hợp đồng bổ sung để xử lý rỗng | `Single<T>` | Hàm `suspend` trả kiểu không null với hợp đồng tương ứng |
| Nhiều giá trị | `Flux<T>` | `Flowable<T>`; `Observable<T>` có cơ chế khác về backpressure | `Flow<T>` |
| Chỉ hoàn tất hoặc lỗi | `Mono<Void>` | `Completable` | Hàm `suspend` trả `Unit` |

`Single` khác `Maybe`: không tìm thấy không thể được biểu đạt như một thành công không có phần tử trong hợp đồng `Single`. `Mono` tự nó vẫn cho phép rỗng, nên không xem `Mono<T>` luôn tương đương `Single<T>`.

`Flowable` có cơ chế backpressure của Reactive Streams; `Observable` không có cùng hợp đồng backpressure đó. `Flow` vận hành theo mô hình coroutine với cơ chế suspension và cancellation của Kotlin, không đơn thuần là một tên khác của `Flux`.

Spring Data Commons có các abstraction như `RxJava3CrudRepository` và `CoroutineCrudRepository`. Sự tồn tại của interface chung không bảo đảm mọi store, phiên bản hoặc derived query hỗ trợ đầy đủ các kiểu tương ứng.

Ví dụ chữ ký Kotlin trên một module đã xác nhận hỗ trợ coroutine repository:

```kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface PurchaseOrderRepository : CoroutineCrudRepository<PurchaseOrder, Long> {

    suspend fun findByTenantIdAndExternalCode(
        tenantId: String,
        externalCode: String
    ): PurchaseOrder?

    fun findByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
        tenantId: String,
        status: OrderStatus
    ): Flow<PurchaseOrder>
}
```

Đây là phương án khác với interface Java dùng Reactor, không phải phần khai báo thêm tùy ý trên cùng một repository. Khi chuyển hệ kiểu, cần giữ nguyên hợp đồng rỗng, lỗi, cardinality, cancellation và hỗ trợ của module.

## 14. Paging, projection và metadata vẫn phụ thuộc store

Một `Flux<PurchaseOrder>` không tự cung cấp tổng số hoặc số trang. Một tham số `Pageable` nếu được hỗ trợ có thể ảnh hưởng truy vấn nhưng không biến publisher của entity thành một `Page` có metadata đầy đủ.

Tương tự, không tự suy rằng một reactive repository chấp nhận mọi tổ hợp:

```text
Mono<Page<T>>
Mono<Slice<T>>
Mono<Window<T>>
```

Phải kiểm tra từng chữ ký theo module và loại truy vấn. Nếu ứng dụng cần nội dung cùng tổng, có thể phải phối hợp luồng lấy dữ liệu và truy vấn đếm riêng; khi đó cần tính cả chi phí và mức nhất quán giữa hai nguồn kết quả.

Projection cũng cần mapping đúng. Trả `Flux<OrderSummary>` không tự sửa một truy vấn chọn sai trường hoặc thiếu alias. Trường hợp projection có giá trị null không phù hợp có thể gây lỗi lúc chuyển đổi hoặc truy cập kết quả, tùy cơ chế module.

Auditing reactive nếu được module hỗ trợ cũng cần cấu hình riêng cho ngữ cảnh và metadata. Nó không tự thêm bộ lọc tenant, bảo đảm uniqueness hoặc sửa hợp đồng số lượng của truy vấn.

## 15. Kiểm chứng hợp đồng bằng tín hiệu thực tế

Một kiểm tra chỉ gọi phương thức rồi assert publisher khác null chưa chứng minh truy vấn đã chạy. Cần có subscription và quan sát giá trị, hoàn tất hoặc lỗi.

Ví dụ với `StepVerifier` của Reactor Test, giả định fixture và store test đã được chuẩn bị:

```java
// Mã không tồn tại: một giá trị false rồi hoàn tất.
StepVerifier.create(repository.existsByTenantIdAndExternalCode(
        "tenant-a", "missing-code"))
    .expectNext(false)
    .verifyComplete();

// Không có entity theo id: hoàn tất mà không phát phần tử.
StepVerifier.create(repository.findById(missingId))
    .verifyComplete();

// Phép đếm không khớp hàng nào: phát số không, không phải Mono rỗng.
StepVerifier.create(repository.countByTenantIdAndStatus(
        "empty-tenant", OrderStatus.PAID))
    .expectNext(0L)
    .verifyComplete();
```

Các ví dụ cần import `reactor.test.StepVerifier` và dependency kiểm thử tương ứng. Chúng minh họa kiểm chứng hợp đồng, không phải cấu hình một ứng dụng test hoàn chỉnh.

Những trường hợp bổ sung có ý nghĩa:

- Có một entity: `Mono` phát đúng entity rồi hoàn tất.
- Nhiều entity với truy vấn đơn kết quả: xác nhận hành vi lỗi của module hoặc ràng buộc dữ liệu.
- `Flux` nhiều kết quả: xác nhận phạm vi lọc và thứ tự, không chỉ đếm phần tử.
- `Mono<Void>`: xác nhận hoàn tất, sau đó kiểm tra tác dụng dữ liệu trong phạm vi phù hợp.
- Lỗi store: được phát như lỗi, không bị biến thành kết quả rỗng ngoài ý định.
- Cancellation hoặc retry nếu ứng dụng dựa vào chúng: xác nhận các tác dụng quan trọng theo khả năng thực tế của stack.

Một test chỉ kiểm tra happy path có dữ liệu không đủ để phân biệt các hợp đồng rỗng, false, số không và hoàn tất không có giá trị.

## 16. Bài tập thực hành

### Bài 1: Chọn kiểu trả về

Chọn kiểu khởi đầu cho các yêu cầu trên module dùng Reactor đã xác nhận hỗ trợ:

1. Tìm đơn theo định danh, có thể không tồn tại.
2. Lấy nhiều đơn `PAID` theo thứ tự thời gian.
3. Đếm đơn `PAID` của một tenant.
4. Kiểm tra một mã ngoài đã xuất hiện chưa.
5. Xóa theo định danh và chỉ cần biết thao tác hoàn tất.

**Gợi ý:** lần lượt là `Mono<PurchaseOrder>`, `Flux<PurchaseOrder>`, `Mono<Long>`, `Mono<Boolean>` và `Mono<Void>`, với nguồn truy vấn hoặc phương thức cơ sở tương ứng được module hỗ trợ.

### Bài 2: Vì sao map không chạy sau delete?

Một service viết:

```java
return repository.deleteById(id)
        .map(ignored -> "done");
```

**Phân tích:** nguồn là `Mono<Void>`, thành công không phát giá trị cho `map`. Nếu cần phát thông báo sau hoàn tất, dùng `thenReturn("done")`. Không dùng việc lambda không chạy để kết luận thao tác xóa không thực hiện.

### Bài 3: Vì sao kiểm tra không thấy lỗi kết nối?

Test chỉ tạo `repository.findById(id)` rồi kết thúc.

**Phân tích:** publisher có thể chưa được subscribe, nên đường truy cập dữ liệu chưa chạy. Cần tiêu thụ và kiểm chứng tín hiệu. Điều đó không loại trừ khả năng một lỗi metadata khác đã được phát hiện sớm khi tạo repository.

### Bài 4: Flux và danh sách rỗng

Một truy vấn không có entity được chuyển bằng `collectList()`.

**Phân tích:** `Flux` nguồn hoàn tất không có phần tử, còn kết quả là một `Mono` phát danh sách rỗng rồi hoàn tất. `switchIfEmpty` sau `collectList()` không dùng để phát hiện danh sách rỗng, vì danh sách vẫn là một giá trị đã được phát.

### Bài 5: Phân biệt lấy đầu tiên và xác nhận duy nhất

Caller dùng `flux.next()` để tránh lỗi khi một truy vấn dự kiến duy nhất lại trả nhiều entity.

**Phân tích:** toán tử đã đổi hợp đồng thành chọn phần tử đầu. Nó không chứng minh dữ liệu duy nhất và có thể che một lỗi nghiệp vụ. Cần chọn rõ yêu cầu: lấy đầu với sort/limit phù hợp, hoặc kiểm tra số lượng và bảo đảm uniqueness.

## 17. Các điểm cần nhớ

- `Mono` biểu đạt không có hoặc một giá trị, `Flux` biểu đạt nhiều giá trị, còn `Mono<Void>` chỉ biểu đạt hoàn tất hoặc lỗi.
- Rỗng, false, số không, danh sách rỗng và hoàn tất không có giá trị là những hợp đồng khác nhau.
- Reactive repository cần module và driver phù hợp; bọc JPA blocking trong một publisher không tự tạo truy cập non-blocking.
- Giữ thao tác trong chuỗi publisher được quản lý, chọn đúng `map`, `flatMap`, `then` và phân biệt kết quả rỗng với tín hiệu lỗi.
- Backpressure không phải SQL limit, publisher không bảo đảm chỉ thực thi một lần và transaction cần hạ tầng reactive tương ứng.
- RxJava, coroutine, projection và các wrapper phân trang cần được xác nhận theo khả năng thực tế của từng module, không chỉ dựa vào sự giống nhau của kiểu kết quả.
