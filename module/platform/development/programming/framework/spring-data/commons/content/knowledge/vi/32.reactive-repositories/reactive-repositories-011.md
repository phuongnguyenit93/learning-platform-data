# Tránh block hoặc subscribe thủ công làm mất phạm vi điều phối

Trong một ứng dụng reactive, phương thức service thường trả về `Mono` hoặc `Flux` để caller tiếp tục điều phối toàn bộ công việc. Nếu service tự gọi `block()` hoặc mở một nhánh `subscribe()` độc lập, đường thực thi có thể bị tách khỏi publisher mà caller đang chờ.

Hậu quả không chỉ là vấn đề hiệu năng. Response có thể báo thành công trước khi ghi xong, lỗi không truyền về use case, cancellation không đến được công việc phụ, và transaction context không còn bao trùm những thao tác cần nguyên tử với nhau.

Bài học thuộc chương **Repository reactive** của module **SPRING_DATA_COMMONS**. Trọng tâm là sử dụng đúng abstraction CRUD reactive, ghép thao tác khi mở rộng repository hoặc xây dựng service, và áp dụng ranh giới giao dịch theo khả năng của từng store.

## 1. Phạm vi điều phối gồm những gì?

Giả sử một use case cần đổi tên sản phẩm và ghi lịch sử thay đổi. Yêu cầu là caller chỉ nhận thành công khi cả hai thao tác đã hoàn tất theo ranh giới được thiết kế.

Một pipeline được ghép đúng cho phép caller quản lý:

| Khía cạnh | Hợp đồng mong muốn |
| --- | --- |
| Completion | Kết quả trả về chờ các bước bắt buộc |
| Error | Lỗi của bước bắt buộc đi vào cùng chuỗi tín hiệu |
| Cancellation | Việc hủy được truyền qua các dependency đã ghép, theo khả năng source |
| Context | Metadata theo subscriber tiếp tục đi qua đường thực thi |
| Transaction | Những thao tác cần tham gia giao dịch nằm trong chuỗi được quản lý |
| Retry | Có thể xác định rõ đoạn công việc nào được thực hiện lại |
| Resource lifecycle | Thành phần sở hữu subscription biết khi nào công việc kết thúc |

Đây là **phạm vi điều phối của use case**. Nó không phải một thread duy nhất và cũng không tự đồng nghĩa với một transaction cơ sở dữ liệu.

Một pipeline có thể đổi thread nhưng vẫn giữ được quan hệ phụ thuộc. Ngược lại, hai subscription chạy trên cùng thread vẫn có thể là hai đường xử lý riêng.

### 1.1. Mô hình ghép chuỗi

```text
Caller/framework subscribe vào kết quả service
                    |
                    v
               Đọc sản phẩm
                    |
                    v
               Lưu tên mới
                    |
                    v
               Ghi lịch sử
                    |
                    v
            Phát kết quả cuối cùng
```

Lỗi hoặc completion của các bước bắt buộc được đưa về cùng publisher kết quả.

### 1.2. Mô hình mở nhánh ngoài ý muốn

```text
Caller subscribe vào publisher A
          |
          +--> Tạo subscription B để lưu dữ liệu
          |          |
          |          +--> Có vòng đời/lỗi riêng
          |
          +--> A báo kết quả cho caller
```

Nếu A không ghép completion của B, caller không có cơ sở để biết B đã hoàn tất. Với source bất đồng bộ, A có thể trả kết quả trước B. Với source đồng bộ, B có thể chạy ngay, nhưng quan hệ điều phối vẫn không tự được khôi phục chỉ nhờ thứ tự tình cờ đó.

## 2. Bối cảnh repository và mô hình ví dụ

Một repository dùng abstraction của Spring Data Commons:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, String> {
}
```

Mô hình đơn giản cho các ví dụ cập nhật:

```java
import org.springframework.data.annotation.Id;

public record Product(@Id String id, String name) {

    public Product withName(String newName) {
        return new Product(id, newName);
    }
}
```

Các ví dụ giả định sản phẩm đã tồn tại và được ánh xạ đúng theo store. Dự án thực tế cần cấu hình collection/table, driver, repository và transaction manager phù hợp; record này chưa trình bày đầy đủ mapping cho mọi kho dữ liệu.

Ta cũng dùng một cổng ứng dụng để ghi lịch sử:

```java
import reactor.core.publisher.Mono;

public interface RenameHistoryWriter {

    Mono<Void> recordRename(
            String productId,
            String previousName,
            String newName
    );
}
```

`RenameHistoryWriter` là interface của ứng dụng, không phải API có sẵn của Spring Data. Implementation có thể dùng một reactive repository khác. Publisher trả về phải biểu diễn việc ghi thật, không tự subscribe rồi trả `Mono.empty()`.

Để đạt truy cập dữ liệu non-blocking, cần store module và driver reactive thực sự. Việc bọc một repository JPA blocking bằng `Mono` không tự biến nó thành repository reactive.

## 3. Vì sao `block()` trong đường reactive gây vấn đề?

### 3.1. Nó chuyển việc chờ thành chặn thread

Ví dụ cần tránh trong service reactive:

```java
public Mono<Product> rename(String id, String name) {
    Product current = products.findById(id).block();
    return products.save(current.withName(name));
}
```

Có nhiều vấn đề cùng lúc:

- `block()` tạo subscription để lấy kết quả đọc rồi chặn luồng gọi.
- Một truy vấn hoàn tất rỗng có thể dẫn đến `current == null`.
- Bước đọc bị tách khỏi pipeline ghi được trả về.
- Caller không còn điều khiển cả hai bước như một chuỗi duy nhất.

Trong ứng dụng WebFlux, các thread xử lý I/O cần phục vụ nhiều request. Blocking làm giảm khả năng phục vụ đồng thời. Một số thread được Reactor đánh dấu không cho blocking còn có thể khiến `block()` ném lỗi thay vì chờ như mong đợi.

Không mặc định rằng mọi thread hoặc mọi cấu hình đều có cùng cơ chế phát hiện. Thiết kế đúng không nên phụ thuộc việc môi trường có chặn hành vi này hay không.

### 3.2. `block()` không truyền quan hệ phụ thuộc qua kiểu trả về

Một phương thức trả `Mono<Product>` khiến caller kỳ vọng công việc nằm trong publisher đó. Nếu phần đọc đã bị thực hiện bằng `block()`, chữ ký không còn phản ánh toàn bộ đường thực thi.

Caller có thể tạo publisher nhưng một phần công việc đã xảy ra trước khi nó subscribe vào kết quả. Việc bỏ hoặc hủy publisher trả về không hoàn tác phần công việc đã làm trước đó.

Nếu `block()` được gọi bên trong một callback reactive, nó vẫn mở một subscription mới để chờ kết quả. Reactor Context của chuỗi hiện tại không tự trở thành context của subscription mới chỉ vì chúng chạy trên cùng thread.

### 3.3. `block()` có thể làm thao tác bị lặp

```java
Mono<Product> lookup = products.findById(id);

Product inspected = lookup.block();
return lookup;
```

Với publisher lạnh thông thường, `block()` đã tạo một subscription. Khi framework tiếp tục subscribe vào `lookup` được trả về, truy vấn có thể được thực hiện thêm lần nữa.

Nếu chỉ cần quan sát giá trị, đặt quan sát trong chuỗi:

```java
return products.findById(id)
        .doOnNext(product ->
                log.debug("Loaded product {}", product.id()));
```

`log` ở đây là logger của lớp. Callback chỉ quan sát; nó không được dùng để khởi chạy một thao tác repository khác rồi bỏ publisher của thao tác đó.

### 3.4. Đẩy sang scheduler không tự sửa phạm vi điều phối

Thêm `subscribeOn` vào một publisher đã được tạo sau khi mã blocking chạy không làm công việc trước đó trở nên lazy.

Ngay cả khi chuyển được thao tác blocking sang một thread phù hợp, vẫn cần xét subscription, lỗi và transaction của nó. Scheduler giải quyết nơi chạy; operator composition giải quyết quan hệ phụ thuộc.

## 4. Vì sao `subscribe()` thủ công trong service dễ tách use case?

### 4.1. Subscription phụ không được publisher ngoài chờ

Ví dụ sai:

```java
public Mono<Product> rename(String id, String name) {
    return products.findById(id)
            .map(current -> {
                Product changed = current.withName(name);
                products.save(changed).subscribe();
                return changed;
            });
}
```

Publisher ngoài phát `changed` mà không ghép completion của `save`. Nó có thể báo thành công trong lúc thao tác ghi chưa hoàn tất hoặc sẽ thất bại.

Việc `subscribe()` có thể thực hiện công việc ngay với một source đồng bộ không tạo ra một hợp đồng chờ đáng tin cậy cho driver bất đồng bộ. Phải diễn đạt dependency bằng pipeline.

### 4.2. Thêm error callback chỉ quan sát nhánh phụ

```java
products.save(changed).subscribe(
        saved -> log.debug("Saved {}", saved.id()),
        error -> log.error("Save failed", error)
);
```

Error callback giúp nhánh đó có nơi quan sát lỗi. Tuy nhiên, nó không tự chuyển lỗi về publisher của request đã phát thành công.

Nếu lưu là bước bắt buộc, logger không thay thế quan hệ phụ thuộc. Nếu lưu là công việc nền, cần có thành phần thực sự sở hữu vòng đời, chính sách retry và độ bền của công việc.

### 4.3. Tự subscribe rồi trả cùng publisher có thể thực hiện hai lần

```java
public Mono<Product> save(Product product) {
    Mono<Product> operation = products.save(product);
    operation.subscribe();
    return operation;
}
```

Caller hoặc WebFlux có thể subscribe tiếp vào publisher trả về. Với source lạnh, có thể có hai lần ghi, tùy hợp đồng source và cách store xử lý entity.

Không mặc định `save` lặp lại là idempotent. ID, optimistic version, insert/update và callback của store đều có thể ảnh hưởng kết quả.

### 4.4. Bỏ publisher cũng là một cách làm mất dependency

```java
public Mono<Void> remove(String id) {
    products.deleteById(id);
    return Mono.empty();
}
```

Không có subscription vào publisher xóa qua kết quả của phương thức này. Dạng phù hợp:

```java
public Mono<Void> remove(String id) {
    return products.deleteById(id);
}
```

Service xây dựng và trả chuỗi công việc; caller ở biên hệ thống sử dụng chuỗi đó.

## 5. Thay lời gọi tách nhánh bằng operator composition

### 5.1. Dùng `flatMap` cho một bước trả publisher

```java
return products.findById(id)
        .switchIfEmpty(Mono.error(new NoSuchElementException(
                "Product not found: " + id
        )))
        .flatMap(current -> products.save(current.withName(name)));
```

`NoSuchElementException` thuộc `java.util`; ứng dụng có thể chọn exception miền thích hợp hơn.

`flatMap` ghép publisher lưu vào đường thực thi. Caller chờ kết quả lưu và nhận lỗi của nó qua cùng publisher.

Nếu dùng `map`:

```java
Mono<Mono<Product>> nested = products.findById(id)
        .map(current -> products.save(current.withName(name)));
```

kết quả là một publisher lồng bên trong publisher. `map` không tự subscribe publisher bên trong để hoàn tất thao tác lưu.

### 5.2. Chờ lịch sử rồi mới trả kết quả đã lưu

```java
return products.findById(id)
        .switchIfEmpty(Mono.error(new NoSuchElementException(
                "Product not found: " + id
        )))
        .flatMap(current ->
                products.save(current.withName(name))
                        .flatMap(saved -> history.recordRename(
                                        saved.id(),
                                        current.name(),
                                        saved.name()
                                )
                                .thenReturn(saved))
        );
```

`history` là `RenameHistoryWriter` đã giới thiệu ở trên. Vì nó trả `Mono<Void>`, dùng `thenReturn(saved)` để chờ completion thành công rồi giữ lại sản phẩm đã lưu làm kết quả.

Các tính chất của chuỗi này:

1. Không tìm thấy sản phẩm thì dừng bằng lỗi đã khai báo.
2. Lưu thất bại thì không đi tiếp theo nhánh thành công để ghi lịch sử.
3. Ghi lịch sử thất bại thì kết quả cuối cũng báo lỗi.
4. Chỉ phát kết quả thành công sau khi các bước được ghép đã hoàn tất theo hợp đồng source.
5. Giá trị trả về là entity mà `save` phát ra, thay vì mặc định dùng lại object ban đầu.

Điểm cuối quan trọng với store có thể trả một instance mới hoặc cập nhật metadata như ID/version.

**Chuỗi tuần tự chưa tự tạo tính nguyên tử.** Nếu lưu sản phẩm thành công rồi ghi lịch sử thất bại ngoài transaction chung, dữ liệu sản phẩm có thể đã thay đổi. Cần thêm ranh giới giao dịch khi yêu cầu nghiệp vụ đòi hỏi nguyên tử.

### 5.3. Chọn operator theo loại dependency

| Nhu cầu | Operator thường phù hợp |
| --- | --- |
| Chuyển một giá trị bằng hàm đồng bộ | `map` |
| Từ một giá trị gọi thao tác trả `Mono`/`Flux` | `flatMap` và các biến thể tương ứng |
| Bỏ kết quả bước đầu, chờ completion rồi chạy bước sau | `then` |
| Chờ một thao tác completion rồi trả một giá trị đã có | `thenReturn` |
| Chờ một publisher phụ nhưng giữ phần tử nguồn | `delayUntil` trong trường hợp phù hợp |
| Xử lý các phần tử Flux lần lượt | `concatMap` |
| Chờ nhiều thao tác độc lập hoàn tất, không cần giá trị | `Mono.when` |
| Kết hợp giá trị từ các source có phát phần tử | `zip` khi phù hợp với cardinality |

Đừng dùng `zip` như một cách chung để chờ nhiều `Mono<Void>`. Source hoàn tất rỗng không cung cấp giá trị tạo tuple; có thể khiến tổ hợp kết thúc sớm hoặc hủy những source khác.

Với hai thao tác độc lập chỉ cần completion:

```java
return Mono.when(
        products.deleteById(firstId),
        products.deleteById(secondId)
);
```

Nếu cần thứ tự:

```java
return products.deleteById(firstId)
        .then(products.deleteById(secondId));
```

Các ví dụ không khẳng định mọi connection hoặc transaction đều hỗ trợ nhiều lệnh đồng thời. Khi có ràng buộc dùng chung tài nguyên giao dịch, phải xét store và driver trước khi chọn chạy song song.

### 5.4. Operator quan sát không chờ tác vụ reactive do callback tạo ra

`doOnNext`, `doOnError` và `doFinally` hữu ích cho log, metric hoặc quan sát đồng bộ nhỏ. Chúng không tự ghép publisher trả về từ một thao tác repository trong callback.

Ví dụ cần tránh:

```java
.doFinally(signal -> history.recordRename(id, oldName, newName).subscribe())
```

Ngoài việc tách subscription, callback cuối còn có thể chạy khi chuỗi lỗi hoặc bị hủy. Nó không tương đương một bước ghi lịch sử thành công nằm trong use case.

Nếu việc ghi là bắt buộc, đặt nó trong nhánh nghiệp vụ được ghép và xác định rõ điều kiện chạy. Với tài nguyên tùy biến cần giải phóng bất đồng bộ, dùng cơ chế quản lý tài nguyên phù hợp; không tự phát sinh subscription dọn dẹp mà không có người sở hữu.

## 6. Giữ các thao tác trong transaction reactive

### 6.1. Một service hoàn chỉnh về luồng điều phối

Ví dụ sau dùng `TransactionalOperator` để bao quanh việc cập nhật và ghi lịch sử:

```java
import java.util.NoSuchElementException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;

@Service
public class RenameProductService {

    private final ProductRepository products;
    private final RenameHistoryWriter history;
    private final TransactionalOperator transactions;

    public RenameProductService(
            ProductRepository products,
            RenameHistoryWriter history,
            TransactionalOperator transactions
    ) {
        this.products = products;
        this.history = history;
        this.transactions = transactions;
    }

    public Mono<Product> rename(String id, String requestedName) {
        Mono<Product> work = Mono.defer(() -> {
            if (requestedName == null || requestedName.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "Product name is required"
                ));
            }

            String normalizedName = requestedName.strip();

            return products.findById(id)
                    .switchIfEmpty(Mono.error(new NoSuchElementException(
                            "Product not found: " + id
                    )))
                    .flatMap(current ->
                            products.save(current.withName(normalizedName))
                                    .flatMap(saved -> history.recordRename(
                                                    saved.id(),
                                                    current.name(),
                                                    saved.name()
                                            )
                                            .thenReturn(saved))
                    );
        });

        return transactions.transactional(work);
    }
}
```

`Mono.defer` đưa phần kiểm tra và tạo source trong ví dụ vào giai đoạn thực thi theo subscription. Nó không tự đổi thread và không làm một implementation blocking của `history` trở nên non-blocking.

Điều kiện để kỳ vọng hai thao tác ghi nguyên tử:

- Có `ReactiveTransactionManager` phù hợp và operator được cấu hình từ manager đó.
- Repository sản phẩm và implementation lịch sử sử dụng tài nguyên có thể cùng tham gia transaction.
- Implementation lịch sử trả publisher của thao tác thật và giữ context trong chuỗi.
- Không có một lời gọi tự subscribe tách thao tác ghi ra ngoài ranh giới.
- Store và cấu hình thực tế hỗ trợ phạm vi transaction được yêu cầu.

Nếu lịch sử được gửi qua HTTP tới một hệ thống khác, transaction của cơ sở dữ liệu sản phẩm không tự rollback được hệ thống đó. Khi cần phối hợp nhiều tài nguyên, phải chọn thiết kế tích hợp thích hợp.

### 6.2. Có thể dùng khai báo transaction, nhưng vẫn phải giữ chuỗi

Một phương án khác là khai báo `@Transactional` trên phương thức service trả publisher, với reactive transaction manager và hạ tầng proxy tương thích.

Dù chọn khai báo hay `TransactionalOperator`, nguyên tắc không đổi: công việc cần tham gia giao dịch phải là một phần của pipeline được quản lý.

Không thêm annotation rồi tiếp tục tự `subscribe()` trong thân use case và xem đó là bằng chứng transaction đã bao trùm mọi nhánh. Khi có nhiều manager, phải chọn rõ manager của tài nguyên liên quan.

### 6.3. Ghép đúng là điều kiện cần, không thay thế kiểm soát concurrency

Pipeline tuần tự không ngăn hai request cùng đọc một tên cũ rồi cùng cập nhật. Nếu miền cần phát hiện xung đột, có thể cần optimistic locking, version hoặc một thao tác cập nhật có điều kiện theo store.

Tương tự, một `onNext` từ `save` bên trong transaction chưa chứng minh transaction ngoài đã commit. Không gửi một tác động ngoài không thể thu hồi chỉ dựa vào callback đó.

## 7. Giữ lỗi trong cùng hợp đồng kết quả

### 7.1. Quan sát lỗi khác với phục hồi lỗi

```java
return service.rename(id, name)
        .doOnError(error -> log.warn("Rename failed for {}", id, error));
```

`doOnError` quan sát nhưng không tự thay lỗi thành thành công. Caller vẫn nhận tín hiệu lỗi.

Ngược lại:

```java
history.recordRename(id, oldName, newName)
        .onErrorResume(error -> Mono.empty())
```

đã thay lỗi thành completion thành công. Nếu dùng đoạn này trong bước lịch sử bắt buộc, publisher ngoài có thể báo thành công dù chưa ghi lịch sử.

Với transaction, việc nuốt lỗi trước ranh giới quản lý có thể khiến hạ tầng không nhìn thấy lỗi đó và cho phép commit phần công việc khác, nếu tài nguyên chưa bị đánh dấu rollback. Không dùng `onErrorResume` như một cách chung để loại bỏ mọi lỗi.

### 7.2. Recovery phải là một quyết định nghiệp vụ

Nếu không tìm thấy dữ liệu có nghĩa là trả rỗng hoặc tạo mới, hãy biểu diễn nhánh đó tường minh. Nếu lịch sử chỉ là quan sát tùy chọn, cần công bố rõ chính sách khi thất bại.

Không trả lại một object có vẻ hợp lệ chỉ để response không lỗi khi thao tác lưu bắt buộc đã thất bại. Điều đó làm mất liên hệ giữa kết quả API và trạng thái bền vững.

Exception của service cũng cần được ánh xạ sang HTTP response bằng cơ chế của ứng dụng. Một `NoSuchElementException` không tự trở thành HTTP 404 chỉ nhờ nằm trong `Mono`.

### 7.3. Retry phải bao quanh đúng phần công việc

`retry` tạo subscription mới vào phần upstream của nó. Nếu phần đó chứa thao tác ghi, nó có thể được thực hiện lại.

Trước khi retry, cần biết:

- Lỗi là tạm thời hay lỗi nghiệp vụ không nên thử lại.
- Lần trước có thể đã ghi thành công một phần hoặc toàn bộ không.
- Ranh giới transaction nào được bắt đầu hoặc tham gia cho mỗi lần thử.
- Có cần tải lại entity và version không.
- Có command ID hoặc cơ chế idempotency phù hợp không.

Việc giữ mọi thao tác trong một pipeline giúp nhìn rõ phạm vi retry. Nó không tự biến mọi lần ghi thành an toàn khi lặp.

## 8. Context và cancellation đi cùng quan hệ phụ thuộc

### 8.1. Context gắn với subscriber, không chỉ với thread

Reactor Context có thể mang transaction context, correlation ID hoặc metadata do ứng dụng cung cấp. Khi ghép các publisher bằng operator đúng hợp đồng, context được truyền theo đường subscription.

Một lời gọi `subscribe()` mới trong callback không mặc nhiên sao chép Reactor Context của chuỗi ngoài. Vì vậy, một thao tác có thể mất metadata hoặc không tham gia transaction như dự kiến ngay cả khi log cho thấy cùng tên thread.

`ThreadLocal` và Reactor Context là hai cơ chế khác nhau. Nếu ứng dụng có công cụ context propagation bổ sung, cần biết chính xác nó truyền những gì; không mặc định mọi metadata đều được phục hồi.

Khi cần đọc metadata theo subscriber, có thể dùng `deferContextual` và cơ chế context được ứng dụng thiết kế. Tenant hoặc principal vẫn phải đến từ một nguồn đã xác thực; context không thay thế kiểm tra quyền.

### 8.2. Hủy chuỗi ngoài không tự quản lý nhánh đã tách

Nếu HTTP client ngắt kết nối, framework có thể hủy subscription của response. Các upstream được ghép có cơ hội nhận cancellation theo hợp đồng của chúng.

Một nhánh tự subscribe có `Disposable` và vòng đời riêng. Chuỗi ngoài không tự giữ handle đó để hủy nó. Công việc phụ có thể tiếp tục chạy sau khi request đã kết thúc.

Ngược lại, ngay cả khi ghép đúng, cancellation không chứng minh một lệnh ghi chưa từng tới server hoặc chưa commit. Hạ tầng transaction và driver xử lý theo khả năng thực tế; không coi hủy subscription là cơ chế hoàn tác phổ quát.

### 8.3. Timeout không chứng minh thao tác chưa xảy ra

Một operator timeout có thể báo lỗi và hủy upstream. Tại thời điểm đó, thao tác ngoài có thể đã chạy hoặc phản hồi đang trên đường về.

Nếu caller gọi lại command vì timeout, có thể tạo hiệu ứng lặp. Giữ một pipeline giúp truyền tín hiệu rõ ràng, còn khả năng chống lặp vẫn cần một hợp đồng idempotency và chiến lược dữ liệu thích hợp.

## 9. Công việc tùy chọn không nên trở thành fire-and-forget vô chủ

Đôi khi yêu cầu là response không cần chờ một việc phụ, chẳng hạn gửi thông báo. Điều đó không có nghĩa lời giải mặc định là gọi `subscribe()` trong service rồi bỏ handle.

Cần phân biệt ba chính sách:

| Chính sách | Cách thể hiện |
| --- | --- |
| Bước bắt buộc hoàn tất trước khi trả kết quả | Ghép vào pipeline và truyền lỗi theo hợp đồng |
| Bước có thể thất bại mà use case vẫn thành công | Khai báo recovery rõ ràng, có quan sát lỗi phù hợp |
| Bước phải được làm về sau, không cần chờ ngay | Giao cho thành phần quản lý công việc nền và độ bền cần thiết |

Nếu thông báo bắt buộc cuối cùng phải được gửi, có thể ghi một bản ghi công việc hoặc outbox trong transaction được hỗ trợ cùng dữ liệu chính. Worker đọc công việc bền vững và thực hiện retry theo chính sách.

```text
Use case:
    Cập nhật sản phẩm
    Ghi ý định gửi thông báo
    Commit trong cùng transaction có hiệu lực
                    |
                    v
Worker có vòng đời riêng:
    Đọc công việc pending
    Gửi thông báo
    Ghi tiến độ, retry và theo dõi bản trùng
```

Đây là một ranh giới điều phối mới được thiết kế tường minh. Nó khác với một subscription bị bỏ quên trong request.

Nếu chỉ là metric có thể mất, một cơ chế quan sát nhẹ có thể đủ. Không làm một quy trình nghiệp vụ quan trọng phụ thuộc vào side effect quan sát mà không có hợp đồng thất bại.

## 10. Subscription và blocking hợp lệ ở đâu?

### 10.1. WebFlux thường là chủ sở hữu ở biên HTTP

Controller có thể trả thẳng kết quả service:

```java
@PatchMapping("/products/{id}/name")
public Mono<Product> rename(
        @PathVariable String id,
        @RequestBody RenameRequest request
) {
    return service.rename(id, request.name());
}

public record RenameRequest(String name) {
}
```

Các annotation thuộc Spring Web; ví dụ giả định controller được cấu hình trong WebFlux. Framework sử dụng publisher trả về để xử lý response, lỗi và cancellation.

Không thêm `subscribe()` vào controller chỉ để khởi chạy công việc. Cũng không cần `block()` để đổi kết quả sang một object rồi lại bọc bằng `Mono.just`.

### 10.2. Một ứng dụng standalone có thể sở hữu subscription tường minh

Một entry point chạy batch, consumer hoặc thành phần nền được thiết kế riêng có thể cần gọi `subscribe()`. Khi đó, thành phần này phải sở hữu:

- Handle hoặc cơ chế quản lý vòng đời công việc.
- Xử lý lỗi thay vì để lỗi biến mất khỏi quan sát.
- Chính sách kết thúc ứng dụng, chờ hoàn tất hoặc hủy có chủ đích.
- Giới hạn concurrency và tài nguyên.
- Retry, idempotency và độ bền theo yêu cầu.

Việc dispose subscription có nghĩa yêu cầu hủy, không phải bằng chứng mọi thao tác ghi đã được hoàn tác. Nếu worker cần phục hồi sau khi tiến trình dừng, phải có trạng thái bền vững ngoài handle trong bộ nhớ.

Quy tắc thực hành là **mỗi công việc phải có chủ sở hữu subscription rõ ràng**, không phải cấm tuyệt đối việc sử dụng API `subscribe()`.

### 10.3. Cầu nối sang mã imperative cần nằm ở ranh giới được thiết kế

Một chương trình dòng lệnh imperative có thể chủ động chờ kết quả ở entry point:

```java
Product result = service.rename(id, name)
        .block(Duration.ofSeconds(10));
```

`Duration` thuộc `java.time`. Ví dụ chỉ phù hợp khi entry point được phép chặn và không chạy trên event loop hoặc thread cấm blocking.

Không đưa cầu nối này vào giữa một service đã cam kết trả pipeline reactive. Timeout của `block` cũng không chứng minh thao tác ghi chưa xảy ra, nên chính sách gọi lại vẫn cần được thiết kế.

### 10.4. Adapter cho API blocking cũ khác với block một repository reactive

Nếu cần gọi một client blocking không thể thay ngay, có thể tạo một adapter lazy:

```java
Mono<LegacyResult> result = Mono.fromCallable(() ->
        legacyClient.lookup(id))
        .subscribeOn(Schedulers.boundedElastic());
```

`LegacyResult` và `legacyClient` là kiểu/thành phần của hệ thống cũ. Adapter hoãn callable sang giai đoạn thực thi và bố trí nó trên scheduler phù hợp với công việc blocking trong ví dụ.

Điều này không biến client thành non-blocking và không tự tạo transaction chung với reactive repository. Cần giới hạn tài nguyên và xử lý overload theo thiết kế của ứng dụng.

Tránh dạng:

```java
Mono.just(legacyClient.lookup(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Ở dạng này, Java đã gọi `lookup` để tính đối số trước khi `Mono.just` được tạo; scheduler phía sau không di chuyển công việc đã chạy.

## 11. Xử lý nhiều phần tử mà vẫn giữ phạm vi điều phối

Giả sử có một `Flux<RenameRequestItem>` mô tả các yêu cầu đổi tên. Thay vì subscribe riêng trong một vòng lặp:

```java
requests.subscribe(request ->
        service.rename(request.id(), request.name()).subscribe());
```

hãy trả một pipeline bao trùm batch:

```java
return requests
        .concatMap(request ->
                service.rename(request.id(), request.name()))
        .then();
```

`RenameRequestItem` là kiểu yêu cầu của ứng dụng có các accessor `id()` và `name()`. `concatMap` giữ thứ tự thực thi theo phần tử nguồn và chờ bước trước hoàn tất trước khi subscribe bước sau.

Nếu các yêu cầu độc lập và được phép chạy đồng thời, có thể cân nhắc:

```java
return requests
        .flatMap(request ->
                service.rename(request.id(), request.name()), 4)
        .then();
```

Giá trị `4` là ví dụ giới hạn số publisher bên trong đang được xử lý đồng thời tại operator này. Nó không phải cấu hình tối ưu chung cho mọi connection pool hoặc store, cũng không tự tạo giới hạn tốc độ toàn hệ thống.

Cần quyết định trước:

- Một phần tử lỗi có làm batch dừng không?
- Các phần tử trước đó đã commit có được giữ lại không?
- Có cần kết quả theo từng phần tử để retry chọn lọc không?
- Có được xử lý đồng thời hai yêu cầu của cùng một sản phẩm không?
- Transaction bao quanh từng use case hay toàn batch?

Giữ một pipeline không có nghĩa toàn bộ batch tự trở thành một transaction. Không mở một transaction dùng chung rồi mặc định mọi driver hỗ trợ nhiều câu lệnh đồng thời trên cùng tài nguyên.

## 12. Kiểm chứng hành vi điều phối

Các tình huống dưới đây dành cho dự án thực hành. Chúng cần cấu hình repository, dữ liệu fixture và transaction manager thực tế; tài liệu này không khẳng định các ví dụ đã được chạy.

### 12.1. Kiểm tra lỗi của bước bắt buộc truyền về caller

Giả sử fixture có sản phẩm `p-01` với tên `Bàn phím`, và transaction manager quản lý đúng repository sản phẩm. Có thể thay writer lịch sử bằng một implementation báo lỗi để kiểm tra đường thất bại:

```java
RenameHistoryWriter failingHistory = (id, before, after) ->
        Mono.error(new IllegalStateException("History unavailable"));

RenameProductService testedService = new RenameProductService(
        products, failingHistory, transactions
);

StepVerifier.create(testedService.rename("p-01", "Bàn phím cơ"))
        .expectErrorMessage("History unavailable")
        .verify(Duration.ofSeconds(5));
```

Ví dụ dùng `reactor.test.StepVerifier` và `java.time.Duration`. Service được tạo trực tiếp trong bài kiểm tra này vì ranh giới giao dịch nằm ở operator được truyền vào, không dựa vào một annotation proxy trên instance vừa tạo.

Sau khi lỗi và rollback được xử lý, đọc lại bằng một lượt truy cập độc lập để kiểm tra trạng thái bền vững:

```java
StepVerifier.create(products.findById("p-01"))
        .expectNextMatches(product -> "Bàn phím".equals(product.name()))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

Kết quả mong đợi này phụ thuộc transaction thật bao quanh cập nhật. Chỉ nhìn thấy exception chưa đủ chứng minh dữ liệu đã rollback; cần xác minh trạng thái lưu trữ.

Nếu bài kiểm tra có transaction ngoài hoặc context khác bao quanh, phải bảo đảm ranh giới cần quan sát đã thực sự hoàn tất. Không để cơ chế rollback của test che giấu một lỗi điều phối trong use case.

### 12.2. Ma trận kiểm chứng

| Tình huống | Điều cần quan sát |
| --- | --- |
| Tạo publisher nhưng chưa subscribe | Chưa thực thi phần công việc lazy được mô tả trong source |
| Cả lưu sản phẩm và lịch sử thành công | Caller chỉ nhận kết quả sau các bước bắt buộc |
| Không tìm thấy sản phẩm | Không ghi dữ liệu và trả lỗi/nhánh rỗng theo chính sách |
| Thao tác lưu thất bại | Không ghi lịch sử theo nhánh thành công |
| Ghi lịch sử thất bại | Caller nhận lỗi; trạng thái lưu trữ phản ánh ranh giới transaction đã thiết kế |
| Caller hủy request | Các upstream được ghép nhận cancellation theo hợp đồng; không có nhánh phụ vô chủ |
| Retry sau lỗi | Biết rõ bước nào được gọi lại và kiểm soát hiệu ứng trùng |
| Có nhiều subscriber | Không mặc định một biến publisher chỉ thực thi một lần |
| Chạy batch với lỗi giữa chừng | Quan sát phần đã commit và chính sách đối với phần còn lại |

Một bộ đếm `doOnSubscribe` đo subscription đi qua vị trí đặt operator. Nó không tự chứng minh số câu lệnh mạng, số bản ghi thay đổi hoặc số transaction commit. Khi cần đo I/O, kết hợp với quan sát driver/store thích hợp.

## 13. Chẩn đoán và hướng sửa

| Hiện tượng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| API báo thành công nhưng dữ liệu chưa được lưu | Tự subscribe thao tác ghi rồi trả kết quả khác | Trả publisher ghi hoặc ghép bằng flatMap/then |
| Chỉ thấy lỗi trong log, caller vẫn thành công | Error nằm ở subscription phụ | Đưa bước bắt buộc vào pipeline trả về |
| Luồng I/O bị chặn hoặc block ném lỗi | Gọi block trong đường reactive | Ghép dependency hoặc thiết kế cầu nối đúng ở biên |
| Cùng dữ liệu bị ghi nhiều lần | Subscribe thủ công rồi framework subscribe tiếp | Xác định một chủ sở hữu ở biên và bỏ subscription thừa |
| Có Mono bên trong Mono | Dùng map cho một hàm trả publisher | Chọn flatMap hoặc operator làm phẳng phù hợp |
| Lịch sử không chạy dù đã gọi phương thức | Publisher lịch sử bị bỏ đi trong callback | Ghép completion với kết quả use case |
| Lịch sử thất bại nhưng cập nhật vẫn commit | Không có transaction chung hoặc lỗi đã bị nuốt | Kiểm tra manager, tài nguyên tham gia và chính sách recovery |
| Mất tenant/correlation ID | Subscription mới không có context mong đợi | Giữ chuỗi hoặc thiết kế truyền context có chủ đích |
| Request đã hủy nhưng nhánh ghi vẫn chạy | Subscription phụ có vòng đời riêng | Bỏ nhánh vô chủ hoặc chuyển sang worker được quản lý |
| Retry làm lặp tác động | Không xét resubscription và idempotency | Thiết kế lại phạm vi thử lại cùng chiến lược dữ liệu |

Khi đọc code, hãy lần theo publisher được trả về thay vì chỉ tìm thứ tự các câu lệnh Java. Câu hỏi quan trọng là: **completion và error của thao tác này có thật sự đi tới subscriber của use case hay không?**

## 14. Bài thực hành

1. Viết phiên bản đổi tên sản phẩm có `subscribe()` trong `map`, rồi mô tả vì sao response không chờ thao tác ghi.
2. Sửa bằng `flatMap`; thêm lịch sử và chờ completion bằng `thenReturn`.
3. Thêm transaction reactive được store hỗ trợ; tạo lỗi ở writer lịch sử và kiểm tra dữ liệu sau rollback.
4. Thử một nhánh recovery làm lịch sử hoàn tất rỗng, sau đó giải thích vì sao chính sách thành công của use case đã thay đổi.
5. Chuyển một batch từ các subscription lồng nhau sang `concatMap`; xác định chính sách lỗi từng phần tử.
6. Chọn một việc phụ cần làm về sau và mô tả nơi lưu công việc, chủ sở hữu, retry và khả năng chống trùng.
7. Chỉ ra vị trí biên duy nhất có quyền subscribe hoặc block tường minh trong kiến trúc thực hành của bạn.

## 15. Điểm cần ghi nhớ

- Service reactive nên trả một pipeline biểu diễn đầy đủ những bước bắt buộc của use case.
- `block()` mở subscription để chờ và chặn thread; dùng nó giữa đường reactive có thể tách thao tác khỏi context và ranh giới điều phối mong muốn.
- `subscribe()` trong callback tạo một vòng đời riêng nếu không có cơ chế quản lý tường minh.
- Dùng `flatMap`, `then`, `thenReturn` và các operator phù hợp để diễn đạt dependency.
- Ghép chuỗi giữ completion và error trong cùng hợp đồng; tính nguyên tử vẫn cần transaction và khả năng store tương ứng.
- Không nuốt lỗi của bước bắt buộc rồi báo thành công ngoài ý muốn.
- Context, cancellation, retry và resource lifecycle phải được xét cùng với chủ sở hữu subscription.
- Công việc nền quan trọng cần người quản lý và độ bền phù hợp; một subscription bị bỏ handle không phải một hàng đợi.
- Subscribe hoặc block tường minh có thể hợp lệ tại một ranh giới được thiết kế, với trách nhiệm vòng đời rõ ràng.