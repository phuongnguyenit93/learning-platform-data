# Sử dụng onErrorMap và onErrorResume theo ý nghĩa nghiệp vụ

Trong ứng dụng Spring Data R2DBC, lỗi từ database được truyền qua các publisher `Mono` và `Flux` dưới dạng error signal. Tầng Service cần quyết định lỗi đó có ý nghĩa gì đối với nghiệp vụ: dữ liệu đã tồn tại, bản ghi không còn ở phiên bản mong đợi, database tạm thời không truy cập được hay một ràng buộc dữ liệu đã bị vi phạm. Reactor cung cấp hai toán tử quan trọng để diễn đạt quyết định này: `onErrorMap` chuyển một lỗi thành lỗi khác, còn `onErrorResume` thay luồng lỗi bằng một publisher dự phòng.

Hai toán tử có mục đích khác nhau. Dùng `onErrorMap` khi muốn giữ thất bại nhưng chuyển nó sang loại exception có ý nghĩa ở tầng ứng dụng. Dùng `onErrorResume` khi nghiệp vụ có một cách phục hồi rõ ràng, chẳng hạn trả dữ liệu cache, dùng nguồn dự phòng hoặc trả một kết quả mặc định đã được chấp nhận. Nếu chỉ đổi tên lỗi thành exception nghiệp vụ, không nên biến nó thành kết quả thành công. Nếu không có phương án phục hồi hợp lệ, hãy để lỗi tiếp tục truyền tới tầng xử lý cao hơn.

## 1. Lỗi trong reactive pipeline

Publisher Reactor có thể phát ra ba loại signal chính:

- `onNext`: phát một giá trị.
- `onComplete`: kết thúc bình thường.
- `onError`: kết thúc bằng lỗi.

Một error signal là terminal: sau khi publisher phát lỗi, publisher đó không tiếp tục phát thêm giá trị hoặc completion. Các toán tử xử lý lỗi tạo ra một luồng mới ở phía sau, có thể đổi loại lỗi hoặc thay thế lỗi bằng một publisher khác.

Ví dụ một thao tác repository:

```java
Mono<CustomerEntity> customer = customerRepository.findById(customerId);
```

Publisher có thể:

- Phát một `CustomerEntity` rồi hoàn tất.
- Hoàn tất rỗng nếu không có bản ghi.
- Phát lỗi nếu database, driver hoặc quá trình mapping gặp sự cố.

Ba trường hợp này không tương đương nhau. `Mono.empty()` không phải lỗi, còn `Mono.error(...)` là lỗi. Vì vậy, `onErrorMap` và `onErrorResume` không xử lý trường hợp publisher hoàn tất rỗng; dùng `switchIfEmpty` cho trường hợp đó.

## 2. Phân biệt onErrorMap và onErrorResume

| Toán tử | Hành vi | Kết quả sau xử lý | Dùng khi |
|---|---|---|---|
| `onErrorMap` | Chuyển exception hiện tại thành exception khác | Vẫn là error signal | Đổi lỗi hạ tầng thành lỗi ứng dụng/nghiệp vụ và giữ nguyên nguyên nhân |
| `onErrorResume` | Chọn một publisher khác khi upstream phát lỗi | Có thể phát giá trị, hoàn tất rỗng hoặc tiếp tục lỗi | Có phương án dự phòng hợp lệ theo nghiệp vụ |
| `switchIfEmpty` | Thay publisher hoàn tất rỗng bằng publisher khác | Publisher thay thế chạy khi không có giá trị | Xử lý không tìm thấy dữ liệu khi repository trả `Mono.empty()` |

Ví dụ ngắn:

```java
// Vẫn thất bại, nhưng lỗi có tên và ý nghĩa ở tầng ứng dụng.
return repository.findById(id)
        .onErrorMap(DataAccessException.class,
                error -> new CustomerStorageException(id, error));

// Có fallback: nếu cache lỗi, đọc nguồn chính.
return cache.get(id)
        .onErrorResume(CacheAccessException.class,
                error -> repository.findById(id));
```

Không dùng `onErrorResume` chỉ để tránh phải khai báo exception. Việc biến lỗi thành `Mono.empty()` hoặc một giá trị mặc định có thể che giấu dữ liệu bị mất, lỗi database hoặc vi phạm quy tắc nghiệp vụ.

## 3. Dùng onErrorMap để chuyển lỗi persistence thành lỗi ứng dụng

### 3.1. Tách exception theo tầng

Repository và driver làm việc với lỗi truy cập dữ liệu. Service nên diễn đạt lỗi theo ngôn ngữ nghiệp vụ hoặc hợp đồng của ứng dụng. Controller/API không cần biết tên exception cụ thể của driver PostgreSQL hay một hệ quản trị khác.

Ví dụ một số loại lỗi Spring thường gặp:

| Exception Spring | Ý nghĩa thường gặp | Cách xem xét ở tầng nghiệp vụ |
|---|---|---|
| `DuplicateKeyException` | Vi phạm khóa duy nhất hoặc khóa chính | Tài nguyên/mã định danh đã tồn tại |
| `DataIntegrityViolationException` | Vi phạm constraint dữ liệu | Dữ liệu không đáp ứng ràng buộc lưu trữ |
| `OptimisticLockingFailureException` | Entity được cập nhật dựa trên version cũ | Xung đột cập nhật đồng thời |
| `TransientDataAccessResourceException` | Lỗi tài nguyên truy cập dữ liệu có thể tạm thời | Có thể xem xét retry có giới hạn nếu thao tác an toàn |
| `DataAccessResourceFailureException` | Không truy cập được tài nguyên dữ liệu | Database/connection có vấn đề; thường cần truyền lỗi hoặc fallback rõ ràng |
| `DataAccessException` | Lớp cơ sở cho nhiều lỗi truy cập dữ liệu của Spring | Chỉ dùng khi cần xử lý nhóm lỗi rộng và đã xác định ý nghĩa |

Exception cụ thể được phát ra phụ thuộc driver, Spring Framework, Spring Data và đường truy cập dữ liệu. Hãy kiểm tra exception thực tế trong phiên bản ứng dụng, không giả định mọi lỗi từ database đều được chuyển thành cùng một subtype.

### 3.2. Tạo exception theo nghiệp vụ

Ví dụ khi email khách hàng đã tồn tại:

```java
public class EmailAlreadyRegisteredException extends RuntimeException {

    public EmailAlreadyRegisteredException(String email, Throwable cause) {
        super("Email is already registered: " + email, cause);
    }
}
```

Service có thể chuyển `DuplicateKeyException` thành exception nghiệp vụ:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<CustomerEntity> register(String email, String displayName) {
        CustomerEntity customer = new CustomerEntity(
                null, email, displayName, null);

        return repository.save(customer)
                .onErrorMap(DuplicateKeyException.class,
                        error -> new EmailAlreadyRegisteredException(email, error));
    }
}
```

Ở đây `onErrorMap` giữ nguyên tính chất thất bại. Nó chỉ thay exception persistence bằng exception mà Service/API hiểu được. Nguyên nhân gốc vẫn được giữ trong `cause`, hữu ích cho log, tracing và chẩn đoán.

Ví dụ giả định constraint vi phạm là unique email. Nếu bảng có nhiều unique constraint, không nên ánh xạ mọi `DuplicateKeyException` thành `EmailAlreadyRegisteredException` một cách mù quáng. Cần phân biệt constraint cụ thể bằng metadata/exception của driver hoặc thiết kế thao tác để biết chính xác điều kiện nào có thể gây lỗi. Nếu không phân biệt được, dùng một exception tổng quát hơn như `CustomerConflictException`.

### 3.3. Dùng predicate để chuyển một nhóm lỗi có chọn lọc

Ngoài overload theo class, `onErrorMap` có thể nhận predicate:

```java
return repository.save(customer)
        .onErrorMap(
                error -> error instanceof DataIntegrityViolationException,
                error -> new InvalidCustomerDataException(
                        "Customer data violates a storage constraint", error));
```

Predicate giúp áp dụng quy tắc khi nhiều exception subtype cần được gom vào một loại lỗi ứng dụng. Chỉ gom các lỗi thực sự có cùng ý nghĩa nghiệp vụ. Không chuyển mọi `RuntimeException` thành lỗi validation; lỗi lập trình, lỗi cấu hình và lỗi database tạm thời cần được phân biệt.

### 3.4. Giữ nguyên cause

Khi tạo exception mới, truyền exception gốc làm `cause`:

```java
error -> new CustomerStorageException(customerId, error)
```

Tránh:

```java
error -> new CustomerStorageException(customerId)
```

ở trường hợp cần chẩn đoán nguyên nhân. Nếu bỏ cause, stack trace gốc và thông tin driver có thể bị mất. Tuy nhiên, không đưa message SQL, tên bảng nội bộ hoặc thông tin connection nhạy cảm trực tiếp vào HTTP response.

## 4. Dùng onErrorResume khi có phương án phục hồi

`onErrorResume` nhận exception và trả về một publisher khác. Publisher thay thế có thể phát một giá trị, hoàn tất rỗng hoặc tiếp tục phát lỗi.

### 4.1. Fallback sang cache hoặc nguồn đọc dự phòng

Ví dụ một endpoint đọc thông tin khách hàng ưu tiên cache; nếu cache gặp lỗi truy cập, Service đọc database:

```java
public Mono<CustomerView> findCustomer(Long id) {
    Mono<CustomerView> cacheOrDatabase = cacheRepository.findById(id)
            .switchIfEmpty(Mono.defer(() -> customerRepository.findById(id)
                    .map(CustomerView::fromEntity)));

    return cacheOrDatabase.onErrorResume(CacheAccessException.class,
            cacheError -> customerRepository.findById(id)
                    .map(CustomerView::fromEntity));
}
```

Ví dụ này minh họa hai trường hợp khác nhau:

- Cache phát lỗi truy cập: `onErrorResume` chuyển sang database.
- Cache hoàn tất rỗng: `switchIfEmpty` chuyển sang database.

Nếu cache trả dữ liệu, database không được gọi. `switchIfEmpty` được đặt trên publisher cache trước khi fallback lỗi được gắn vào, vì vậy database chỉ được gọi một lần cho mỗi nhánh fallback. Trong ứng dụng thật, cần xác định cách cập nhật lại cache sau khi đọc nguồn chính và ghi metric khi cache không sẵn sàng.

### 4.2. Trả kết quả mặc định khi nghiệp vụ cho phép

Một số dữ liệu phụ có thể có giá trị mặc định hợp lệ. Ví dụ, nếu dịch vụ lấy số liệu thống kê không sẵn sàng, giao diện có thể hiển thị trạng thái “chưa có dữ liệu” thay vì làm hỏng toàn bộ trang:

```java
public Mono<DashboardStats> loadOptionalStats() {
    return statsRepository.loadStats()
            .onErrorResume(StatsUnavailableException.class,
                    error -> Mono.just(DashboardStats.unavailable()));
}
```

Fallback này chỉ đúng nếu sản phẩm phân biệt rõ “không có số liệu” hoặc “số liệu tạm thời không sẵn sàng” với số liệu thực. Không trả một thống kê bằng 0 nếu người dùng có thể hiểu nhầm đó là số liệu chính xác.

### 4.3. Fallback bằng publisher rỗng

Có thể dùng `Mono.empty()` khi nghiệp vụ định nghĩa lỗi cụ thể có nghĩa là không có kết quả cần trả:

```java
return recommendationService.findFor(customerId)
        .onErrorResume(RecommendationUnavailableException.class,
                error -> Mono.empty());
```

Chỉ dùng cách này nếu tầng gọi hiểu rằng kết quả rỗng là trạng thái được chấp nhận. Nếu lỗi recommendation cần được quan sát, ghi metric hoặc thông báo cho người dùng, hãy thực hiện điều đó trước khi trả empty. Không chuyển lỗi database tùy ý thành empty vì nó làm mất khả năng phân biệt “không có dữ liệu” và “không đọc được dữ liệu”.

### 4.4. Fallback sang một publisher khác có thể vẫn thất bại

`onErrorResume` không bảo đảm hệ thống phục hồi thành công. Nếu publisher thay thế cũng phát lỗi, lỗi mới tiếp tục đi xuống pipeline:

```java
return primaryRepository.findById(id)
        .onErrorResume(PrimaryStoreUnavailableException.class,
                error -> replicaRepository.findById(id));
```

Nếu replica cũng không truy cập được, caller vẫn nhận error signal. Không nên bọc fallback bằng một giá trị giả chỉ để endpoint luôn trả thành công.

## 5. Phân biệt không tìm thấy dữ liệu với lỗi truy cập dữ liệu

Trong Spring Data R2DBC, `findById` thường trả `Mono.empty()` khi không có bản ghi. Đây là hoàn tất bình thường, không phải exception. Muốn chuyển trường hợp này thành lỗi nghiệp vụ, dùng `switchIfEmpty`:

```java
public Mono<CustomerEntity> getRequiredCustomer(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

Nếu database không truy cập được, publisher phát lỗi và `switchIfEmpty` không chạy. Nếu muốn đổi lỗi persistence, có thể kết hợp:

```java
public Mono<CustomerEntity> getRequiredCustomer(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .onErrorMap(DataAccessException.class,
                    error -> new CustomerStorageException(id, error));
}
```

Trong ví dụ, lỗi `CustomerNotFoundException` không phải `DataAccessException`, nên được giữ nguyên. Lỗi truy cập dữ liệu được chuyển thành `CustomerStorageException`.

Không dùng `onErrorResume` để xử lý trường hợp không tìm thấy nếu repository đã biểu diễn nó bằng `Mono.empty()`. Dùng đúng toán tử giúp code thể hiện ý nghĩa rõ ràng.

## 6. Vị trí toán tử quyết định phạm vi xử lý lỗi

Mỗi toán tử chỉ quan sát lỗi từ phần pipeline nằm trước nó. Thứ tự các toán tử vì vậy có thể làm thay đổi hành vi.

### 6.1. Chuyển lỗi rồi mới fallback

```java
return repository.save(customer)
        .onErrorMap(DuplicateKeyException.class,
                error -> new EmailAlreadyRegisteredException(
                        customer.email(), error))
        .onErrorResume(EmailAlreadyRegisteredException.class,
                error -> Mono.error(new RegistrationConflictException(error)));
```

`onErrorMap` đổi `DuplicateKeyException` thành `EmailAlreadyRegisteredException`. Toán tử `onErrorResume` phía sau nhìn thấy exception đã được đổi và có thể xử lý nó.

Trong thực tế, nếu không có fallback, thường chỉ cần chuyển lỗi một lần ở ranh giới Service và để tầng API ánh xạ nó thành HTTP response. Không cần tạo thêm một lớp exception mới nếu không mang thêm ý nghĩa.

### 6.2. Fallback trước rồi mới map lỗi

```java
return primaryRepository.findById(id)
        .onErrorResume(PrimaryStoreUnavailableException.class,
                error -> replicaRepository.findById(id))
        .onErrorMap(DataAccessException.class,
                error -> new CustomerStorageException(id, error));
```

Toán tử fallback xử lý lỗi từ primary. Nếu replica phát lỗi `DataAccessException`, toán tử map ở phía sau vẫn nhìn thấy và chuyển lỗi đó thành lỗi ứng dụng. Đây là cách hữu ích khi muốn fallback cho một nguồn cụ thể nhưng vẫn chuẩn hóa lỗi còn lại.

### 6.3. Fallback có thể tạo lỗi mới

Nếu `onErrorMap` đặt trước `onErrorResume`, nó chỉ chuyển lỗi từ upstream trước nó. Nếu publisher fallback phát một lỗi mới, lỗi đó không đi ngược lại toán tử map đã chạy trước. Muốn chuẩn hóa cả lỗi từ nguồn chính và nguồn dự phòng, đặt một toán tử xử lý chung sau khi các nhánh đã được kết hợp.

### 6.4. Đặt xử lý lỗi bên trong hay bên ngoài flatMap

Xử lý lỗi bên trong `flatMap` chỉ ảnh hưởng publisher con tương ứng:

```java
return Flux.fromIterable(customerIds)
        .flatMap(id -> repository.findById(id)
                .onErrorResume(DataAccessException.class,
                        error -> Mono.empty()), 8);
```

Trong ví dụ, một ID gặp lỗi truy cập dữ liệu có thể bị bỏ qua trong khi các ID khác tiếp tục. Đây chỉ là hành vi đúng nếu nghiệp vụ chấp nhận kết quả thiếu.

Nếu đặt xử lý lỗi bên ngoài:

```java
return Flux.fromIterable(customerIds)
        .flatMap(repository::findById, 8)
        .onErrorResume(DataAccessException.class,
                error -> fallbackForWholeBatch());
```

một lỗi từ một publisher con có thể kết thúc luồng tổng và kích hoạt fallback cho toàn bộ batch. Chọn phạm vi dựa trên ý nghĩa nghiệp vụ: bỏ qua một phần tử, thay thế một nhóm dữ liệu hay thất bại toàn bộ request.

## 7. Giữ ranh giới transaction khi xử lý lỗi

Đây là điểm đặc biệt quan trọng với Spring Data R2DBC. Reactive transaction được điều phối quanh publisher được trả về từ phương thức transactional. Khi một lỗi thoát ra khỏi ranh giới transaction, transaction manager có thể rollback. Nhưng nếu `onErrorResume` bên trong pipeline đổi lỗi thành một kết quả bình thường, transaction có thể thấy publisher hoàn tất thành công và commit các thao tác đã thực hiện trước đó.

Ví dụ nguy hiểm:

```java
@Transactional
public Mono<OrderEntity> placeOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order))
            .onErrorResume(DataAccessException.class,
                    error -> Mono.just(order));
}
```

Nếu một thao tác ghi phát lỗi nhưng `onErrorResume` biến nó thành `Mono.just(order)` trước khi transaction hoàn tất, lỗi có thể không còn thoát tới transaction boundary. Tùy trạng thái rollback-only và nguyên nhân lỗi, transaction có thể không rollback như người viết mong đợi. Ngoài ra, trả về `order` chưa lưu có thể khiến caller hiểu nhầm đơn hàng đã được tạo.

Nếu nghiệp vụ yêu cầu toàn bộ thao tác thất bại khi một bước ghi lỗi, hãy để lỗi tiếp tục truyền ra ngoài:

```java
@Transactional
public Mono<OrderEntity> placeOrder(OrderEntity order) {
    return inventoryRepository.reserve(order)
            .then(orderRepository.save(order));
}
```

Sau khi transaction kết thúc và rollback, tầng gọi bên ngoài có thể chuyển exception thành response hoặc quyết định fallback không nằm trong transaction đó:

```java
public Mono<OrderResponse> placeOrderCommand(OrderEntity order) {
    return transactionalOrderService.placeOrder(order)
            .map(OrderResponse::fromEntity)
            .onErrorMap(OptimisticLockingFailureException.class,
                    error -> new OrderConflictException(order.id(), error));
}
```

Ở đây lỗi vẫn được giữ ở dạng error signal qua transaction boundary; việc chuyển exception diễn ra ở tầng điều phối bên ngoài. Nếu cần fallback có ghi dữ liệu, hãy thiết kế transaction mới hoặc luồng bù trừ riêng, không nuốt lỗi giữa một transaction đang cần rollback.

## 8. Xử lý lỗi theo từng nhóm nghiệp vụ

### 8.1. Vi phạm unique constraint

Ý nghĩa thường gặp: tài nguyên đã tồn tại hoặc yêu cầu xung đột với dữ liệu hiện có.

```java
return customerRepository.save(customer)
        .onErrorMap(DuplicateKeyException.class,
                error -> new EmailAlreadyRegisteredException(
                        customer.email(), error));
```

Tầng API có thể ánh xạ exception nghiệp vụ này thành `409 Conflict` hoặc lỗi validation theo hợp đồng. Nếu constraint vi phạm không chắc chắn là email, dùng loại exception tổng quát hơn.

Kiểm tra tồn tại trước khi insert có thể tạo thông báo thân thiện, nhưng không thay thế unique constraint. Hai request có thể cùng vượt qua bước kiểm tra trước khi một request ghi dữ liệu. Database constraint mới là hàng rào cuối cùng.

### 8.2. Optimistic locking conflict

Ý nghĩa: entity đã được một request khác cập nhật sau lần đọc hiện tại.

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .map(customer -> customer.rename(newName))
        .flatMap(repository::save)
        .onErrorMap(OptimisticLockingFailureException.class,
                error -> new CustomerConflictException(id, error));
```

Không tự động trả entity cũ hoặc coi update thành công. Client có thể cần tải lại dữ liệu, xem thay đổi mới và gửi lại thao tác theo quy tắc nghiệp vụ.

### 8.3. Database tạm thời không khả dụng

Ý nghĩa: hệ thống không thể hoàn thành thao tác do lỗi kết nối, timeout hoặc tài nguyên dữ liệu tạm thời.

```java
return repository.findById(id)
        .onErrorMap(DataAccessResourceFailureException.class,
                error -> new CustomerStoreUnavailableException(error));
```

Không đổi lỗi này thành `CustomerNotFoundException` vì dữ liệu chưa được đọc thành công. Nếu có replica/cache, có thể dùng `onErrorResume` cho một nguồn dự phòng đã được thiết kế. Nếu không, truyền lỗi để tầng API trả response lỗi dịch vụ phù hợp.

### 8.4. Lỗi dữ liệu không hợp lệ

Ý nghĩa: dữ liệu không đáp ứng quy tắc domain hoặc constraint của schema. Nếu có thể xác định chính xác constraint, chuyển sang lỗi nghiệp vụ tương ứng. Không chuyển mọi `DataIntegrityViolationException` thành lỗi của một trường cụ thể nếu database có nhiều constraint khác nhau.

### 8.5. Lỗi từ dịch vụ phụ trợ

Nếu dữ liệu phụ trợ không bắt buộc, fallback có thể hợp lý:

```java
return customerRepository.findById(id)
        .flatMap(customer -> loyaltyService.findPoints(customer.id())
                .onErrorResume(LoyaltyServiceUnavailableException.class,
                        error -> Mono.just(0L))
                .map(points -> new CustomerProfile(customer, points)));
```

Ví dụ chỉ đúng nếu `0` là giá trị mặc định được sản phẩm chấp nhận và không gây nhầm với số điểm thực. Có thể tốt hơn khi biểu diễn trạng thái `UNAVAILABLE` riêng thay vì giả lập giá trị số.

## 9. Retry và thứ tự với onErrorMap/onErrorResume

Retry là một quyết định riêng. `retryWhen` subscribe lại upstream khi lỗi phù hợp với chính sách retry. Chỉ retry lỗi tạm thời và thao tác có thể thực hiện lại an toàn.

Ví dụ:

```java
return repository.findById(id)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(TransientDataAccessResourceException.class::isInstance))
        .onErrorMap(DataAccessException.class,
                error -> new CustomerStorageException(id, error));
```

Retry được đặt trước `onErrorMap`, nên predicate nhìn thấy loại exception persistence gốc. Nếu map lỗi trước rồi mới retry, predicate cần hiểu exception nghiệp vụ mới hoặc kiểm tra cause. Đặt thứ tự rõ ràng giúp tránh vô tình retry cả lỗi không thể phục hồi.

Không retry vô hạn các lỗi như:

- Unique constraint đã bị vi phạm.
- Dữ liệu đầu vào không hợp lệ.
- Optimistic locking conflict mà chưa đọc lại trạng thái.
- Lỗi lập trình hoặc cấu hình sai.

Với thao tác ghi, retry cần đặc biệt cẩn thận. Nếu client không biết lần ghi trước đã commit hay chưa do mất kết nối sau khi database xử lý, việc gửi lại có thể tạo bản ghi trùng hoặc lặp side effect. Dùng idempotency key, unique constraint hoặc thiết kế thao tác idempotent khi nghiệp vụ cần retry an toàn.

`onErrorResume` có thể thay publisher lỗi bằng một publisher thành công trước khi `retryWhen` ở phía sau nhìn thấy lỗi. Khi đó retry không chạy. Nếu muốn retry nguồn chính trước rồi mới fallback, đặt retry trước fallback:

```java
return primaryRepository.findById(id)
        .retryWhen(transientReadRetry())
        .onErrorResume(PrimaryStoreUnavailableException.class,
                error -> replicaRepository.findById(id));
```

## 10. Logging và quan sát lỗi

Xử lý lỗi theo nghiệp vụ không có nghĩa là bỏ qua khả năng quan sát. Khi chuyển hoặc fallback, hãy cân nhắc:

- Ghi log ở một ranh giới phù hợp, tránh log cùng một lỗi nhiều lần ở mọi tầng.
- Giữ exception gốc làm cause khi chuyển loại lỗi.
- Gắn correlation ID, trace ID hoặc mã nghiệp vụ cần thiết vào log.
- Tạo metric cho số lần conflict, duplicate, fallback và database unavailable.
- Không log mật khẩu, token, dữ liệu cá nhân hoặc toàn bộ tham số SQL nhạy cảm.
- Phân biệt fallback thành công với thao tác chính thành công; cả hai có thể cần metric riêng.

Không nhất thiết phải log mọi lỗi ở toán tử `onErrorMap`. Nếu tầng trên cùng đã log exception, log lại ở Service có thể tạo bản ghi trùng. Hãy thống nhất nơi chịu trách nhiệm ghi log lỗi cuối cùng và nơi ghi metric cho các nhánh fallback.

## 11. Kiểm thử onErrorMap và onErrorResume

`StepVerifier` của `reactor-test` cho phép kiểm tra giá trị, completion và error signal của publisher. Cần kiểm tra cả trường hợp được chuyển lỗi, fallback thành công và fallback cũng thất bại.

### 11.1. Kiểm tra onErrorMap giữ lỗi và cause

```java
DuplicateKeyException persistenceError =
        new DuplicateKeyException("unique constraint violation");

when(repository.save(any(CustomerEntity.class)))
        .thenReturn(Mono.error(persistenceError));

StepVerifier.create(service.register("an@example.com", "An"))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(EmailAlreadyRegisteredException.class);
            assertThat(error.getCause()).isSameAs(persistenceError);
        })
        .verify();
```

Test xác nhận lỗi vẫn là lỗi và cause được giữ nguyên. Trong code test thực tế, khai báo matcher và mock theo repository cụ thể của dự án.

### 11.2. Kiểm tra onErrorResume gọi fallback

```java
when(primaryRepository.findById(10L))
        .thenReturn(Mono.error(new PrimaryStoreUnavailableException()));
when(replicaRepository.findById(10L))
        .thenReturn(Mono.just(customer));

StepVerifier.create(service.findFromPrimaryOrReplica(10L))
        .expectNext(customer)
        .verifyComplete();

verify(replicaRepository).findById(10L);
```

Test xác nhận lỗi của nguồn chính kích hoạt publisher dự phòng và kết quả được phát ra bình thường.

### 11.3. Kiểm tra fallback không bắt lỗi ngoài phạm vi

Nếu fallback chỉ dành cho `CacheAccessException`, lỗi validation hoặc lỗi lập trình cần tiếp tục truyền ra. Hãy viết test để xác nhận các lỗi không nằm trong predicate không bị chuyển thành giá trị mặc định.

### 11.4. Kiểm tra empty riêng với error

```java
when(repository.findById(10L)).thenReturn(Mono.empty());

StepVerifier.create(service.getRequiredCustomer(10L))
        .expectError(CustomerNotFoundException.class)
        .verify();
```

Test này xác nhận `switchIfEmpty` xử lý trường hợp không có bản ghi. Nó không phải test cho `onErrorResume`.

### 11.5. Kiểm thử transaction rollback

Với nghiệp vụ ghi nhiều bước, cần integration test trên database để xác nhận lỗi vẫn thoát khỏi transaction và dữ liệu được rollback. Unit test mock repository không chứng minh transaction manager thực hiện rollback đúng.

Nên có các trường hợp:

- Bước ghi thứ nhất thành công, bước thứ hai lỗi và toàn bộ transaction rollback.
- `onErrorMap` chuyển exception nhưng lỗi vẫn thoát transaction boundary.
- Một `onErrorResume` bên trong transaction biến lỗi thành completion; xác nhận hành vi commit/rollback thực tế để tránh che giấu lỗi.
- Fallback được đặt bên ngoài transaction và chỉ chạy sau khi transaction chính kết thúc.

## 12. Những lỗi thường gặp

### Dùng onErrorResume chỉ để đổi loại exception

Nếu không có phương án phục hồi, `onErrorMap` diễn đạt đúng hơn. Dùng `onErrorResume` với `Mono.error(new ...)` vẫn có thể làm được nhưng thường khó đọc và không thể hiện rõ ý định.

### Chuyển mọi lỗi thành một exception chung

Việc gom duplicate key, timeout, optimistic locking và lỗi lập trình thành một lỗi duy nhất làm mất khả năng xử lý khác nhau theo nghiệp vụ. Chỉ gom những lỗi có cùng ý nghĩa.

### Trả dữ liệu mặc định khi database lỗi

Một list rỗng hoặc số 0 có thể bị hiểu là dữ liệu thật. Chỉ fallback nếu sản phẩm xác định rõ trạng thái degraded và client có cách phân biệt.

### Nhầm Mono.empty với onError

Không có bản ghi là completion rỗng. Dùng `switchIfEmpty`; không dùng `onErrorResume` để xử lý trường hợp này.

### Đặt onErrorResume bên trong transaction

Nuốt lỗi trước transaction boundary có thể khiến transaction không rollback như dự định. Để lỗi thoát ra nếu nghiệp vụ cần rollback; đặt fallback ở ranh giới phù hợp.

### Retry sau khi đã fallback thành công

Nếu `onErrorResume` biến lỗi thành kết quả bình thường, `retryWhen` phía sau không thấy lỗi để retry. Đặt retry trước fallback nếu muốn thử lại nguồn chính trước.

### Bỏ cause khi tạo exception mới

Không giữ cause làm mất thông tin chẩn đoán. Truyền exception gốc vào constructor exception ứng dụng.

### Dùng fallback quá rộng

`onErrorResume(Throwable.class, ...)` hoặc predicate luôn đúng có thể nuốt lỗi lập trình, lỗi validation và lỗi cấu hình. Ưu tiên class/predicate cụ thể.

### Dùng subscribe trong nhánh fallback

Fallback phải trả về `Mono`/`Flux` để pipeline tổng hợp kiểm soát kết quả, lỗi và cancellation. Không tự `subscribe()` rồi trả một publisher rỗng.

## 13. Quy trình quyết định cách xử lý lỗi

Khi một thao tác R2DBC phát lỗi, có thể đi theo các bước:

1. Xác định đây là error signal hay publisher hoàn tất rỗng.
2. Phân loại lỗi theo exception thực tế và nguyên nhân gốc.
3. Xác định ý nghĩa nghiệp vụ: conflict, dữ liệu không hợp lệ, tài nguyên tạm thời không sẵn sàng hay lỗi không dự kiến.
4. Nếu cần giữ thất bại nhưng đổi ngôn ngữ exception, dùng `onErrorMap` và giữ cause.
5. Nếu có phương án thay thế được nghiệp vụ chấp nhận, dùng `onErrorResume` với class/predicate cụ thể.
6. Nếu không có fallback hợp lệ, để lỗi truyền lên tầng gọi.
7. Xử lý trường hợp không có bản ghi bằng `switchIfEmpty`.
8. Xem xét vị trí toán tử so với `flatMap`, `retryWhen` và transaction boundary.
9. Ghi metric/log phù hợp mà không làm lộ dữ liệu nhạy cảm.
10. Kiểm thử lỗi được chuyển, fallback thành công/thất bại, empty publisher và rollback transaction.

## 14. Bảng quyết định nhanh

| Tình huống | Hành động thường phù hợp |
|---|---|
| Unique constraint bị vi phạm | `onErrorMap` thành lỗi conflict/duplicate nghiệp vụ |
| Entity bị cập nhật bởi request khác | `onErrorMap` thành conflict; yêu cầu đọc lại hoặc hợp nhất |
| Database tạm thời không truy cập được, có replica phù hợp | Retry có giới hạn rồi `onErrorResume` sang replica |
| Cache lỗi nhưng database vẫn đọc được | `onErrorResume` sang database |
| Repository trả `Mono.empty()` | `switchIfEmpty` |
| Dữ liệu phụ trợ không bắt buộc và có trạng thái degraded rõ ràng | `onErrorResume` sang kết quả degraded |
| Lỗi validation hoặc lỗi lập trình | Để lỗi truyền ra hoặc chuyển thành lỗi ứng dụng tương ứng; không fallback tùy tiện |
| Một bước ghi trong transaction thất bại và phải rollback | Không nuốt lỗi bên trong transaction; để lỗi thoát boundary |
| Không có phương án phục hồi hợp lệ | Để error signal tiếp tục truyền tới tầng xử lý cao hơn |

## 15. Checklist ghi nhớ

- [ ] `onErrorMap` dùng để đổi exception nhưng vẫn giữ error signal.
- [ ] Exception mới giữ exception gốc làm `cause` khi cần chẩn đoán.
- [ ] `onErrorResume` chỉ dùng khi có publisher dự phòng mang ý nghĩa nghiệp vụ rõ ràng.
- [ ] Fallback giới hạn theo exception class hoặc predicate cụ thể.
- [ ] Không biến lỗi database thành empty/default nếu client có thể hiểu nhầm là dữ liệu thật.
- [ ] Phân biệt `Mono.empty()` với `onError`; dùng `switchIfEmpty` cho trường hợp không có bản ghi.
- [ ] Đặt toán tử đúng vị trí để xử lý đúng lỗi từ upstream, fallback và inner publisher.
- [ ] Retry chỉ áp dụng cho lỗi tạm thời và thao tác có thể thực hiện lại an toàn.
- [ ] Không nuốt lỗi bên trong transaction khi nghiệp vụ cần rollback.
- [ ] Bulk/custom SQL có xử lý lỗi riêng nếu không đi qua cùng cơ chế Repository.
- [ ] Log và metric phản ánh cả lỗi cuối cùng lẫn việc fallback đã được sử dụng.
- [ ] Có unit test bằng `StepVerifier` và integration test cho transaction rollback.

`onErrorMap` và `onErrorResume` giúp biến lỗi kỹ thuật thành hành vi có ý nghĩa với nghiệp vụ, nhưng chỉ khi ranh giới được chọn đúng. Hãy dùng `onErrorMap` để giữ thất bại dưới một exception phù hợp với ứng dụng; dùng `onErrorResume` khi thật sự có nguồn hoặc kết quả thay thế được chấp nhận; dùng `switchIfEmpty` cho dữ liệu không tồn tại. Đặc biệt, luôn xem xét vị trí xử lý lỗi so với transaction boundary để không vô tình biến một nghiệp vụ phải rollback thành một publisher hoàn tất bình thường.
