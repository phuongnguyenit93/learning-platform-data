# Giữ thứ tự kết quả khi kết hợp nhiều thao tác bất đồng bộ

## 1. Vì sao thứ tự có thể thay đổi trong ứng dụng reactive?

Trong Spring Data R2DBC, repository trả về `Mono` hoặc `Flux`. Các publisher có thể thực hiện công việc bất đồng bộ và hoàn tất ở những thời điểm khác nhau. Khi kết hợp nhiều thao tác bằng Reactor, thứ tự kết quả phát ra có thể khác thứ tự phần tử đầu vào.

Ví dụ, ứng dụng nhận danh sách ID theo thứ tự `[10, 20, 30]` rồi tải từng khách hàng:

```java
Flux.fromIterable(List.of(10L, 20L, 30L))
        .flatMap(customerRepository::findById);
```

Nếu truy vấn ID `30` hoàn tất trước truy vấn ID `10`, `flatMap` có thể phát khách hàng `30` trước. Kết quả không được bảo đảm theo thứ tự `[10, 20, 30]`.

Điều này không phải lỗi của R2DBC hay database. Đây là hành vi của phép kết hợp publisher cho phép các inner publisher chạy đồng thời và phát kết quả khi chúng sẵn sàng.

Khi thứ tự có ý nghĩa nghiệp vụ, cần chọn đúng toán tử Reactor và phân biệt rõ thứ tự cần bảo vệ:

- Thứ tự bản ghi do database trả về.
- Thứ tự phần tử của publisher đầu vào.
- Thứ tự các inner publisher hoàn tất.
- Thứ tự phần tử cuối cùng được phát tới subscriber.
- Thứ tự các side effect hoặc câu lệnh ghi thực sự diễn ra.
- Thứ tự kết quả cần ghép với ID hoặc request ban đầu.

Các loại thứ tự này liên quan nhưng không đồng nghĩa. Một pipeline có thể phát kết quả đúng thứ tự đầu vào trong khi các thao tác bên trong vẫn chạy đồng thời.

## 2. Phân biệt thứ tự database và thứ tự Reactor

Reactor chỉ có thể giữ hoặc sắp xếp thứ tự các phần tử mà upstream phát ra. Nếu database không bảo đảm thứ tự hàng trả về, pipeline không thể tự biết thứ tự nghiệp vụ mà ứng dụng mong muốn.

Ví dụ:

```sql
SELECT id, name
FROM customer;
```

Không có `ORDER BY`, database không bảo đảm kết quả theo ID, thời điểm tạo hoặc thứ tự insert. Một lần chạy có thể tình cờ trả về theo thứ tự quen thuộc, nhưng kế hoạch thực thi, index, vacuum, phân vùng hoặc thay đổi dữ liệu có thể làm thứ tự thay đổi.

Nếu cần kết quả theo thời điểm tạo:

```sql
SELECT id, name, created_at
FROM customer
ORDER BY created_at ASC, id ASC;
```

`id` là tiêu chí phụ để tạo thứ tự xác định khi nhiều hàng có cùng `created_at`. Nếu chỉ viết `ORDER BY created_at`, các hàng trùng timestamp vẫn có thể xuất hiện theo thứ tự khác nhau giữa các lần truy vấn.

### 2.1. ORDER BY là nguồn bảo đảm thứ tự ở database

Khi thứ tự là yêu cầu của dữ liệu, hãy biểu đạt nó trong SQL hoặc query metadata:

- Sắp xếp theo một cột có ý nghĩa nghiệp vụ.
- Thêm tiêu chí phụ duy nhất hoặc đủ ổn định để phá hòa.
- Xác định rõ tăng dần (`ASC`) hay giảm dần (`DESC`).
- Khi phân trang, giữ cùng một quy tắc sắp xếp ở mọi trang.

Không dựa vào thứ tự vật lý của bảng, thứ tự insert hoặc thứ tự index được database chọn.

### 2.2. Derived query có sắp xếp

Spring Data R2DBC có thể dùng `Sort` trong các truy vấn hỗ trợ sorting:

```java
Flux<Customer> findByStatus(String status, Sort sort);
```

Sử dụng:

```java
Sort sort = Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("id"));

return customerRepository.findByStatus("ACTIVE", sort);
```

Các property trong `Sort` là tên thuộc tính entity; mapping metadata chuyển chúng thành tên cột SQL. Hãy xác nhận chữ ký method và khả năng sorting của phiên bản Spring Data R2DBC đang dùng.

Với SQL tường minh, đặt `ORDER BY` trực tiếp trong `@Query` hoặc `DatabaseClient`:

```java
@Query("""
    SELECT id, name, created_at
    FROM customer
    WHERE status = :status
    ORDER BY created_at ASC, id ASC
    """)
Flux<CustomerSummary> findActiveCustomersInOrder(
        @Param("status") String status);
```

## 3. Thứ tự của các toán tử Reactor

Các toán tử kết hợp publisher có chính sách khác nhau về concurrency và thứ tự phát kết quả.

| Toán tử | Chạy inner publisher | Thứ tự phát kết quả |
| --- | --- | --- |
| `map` | Đồng bộ theo từng phần tử upstream | Giữ thứ tự upstream |
| `flatMap` | Có thể chạy nhiều inner publisher đồng thời | Theo thời điểm inner publisher phát kết quả; có thể đảo thứ tự |
| `flatMapSequential` | Có thể subscribe nhiều inner publisher đồng thời | Giữ thứ tự inner publisher theo thứ tự phần tử upstream |
| `concatMap` | Xử lý inner publisher tuần tự, từng cái một | Giữ thứ tự upstream và không chồng lấn inner publisher |
| `concat` | Subscribe publisher lần lượt | Phát toàn bộ publisher trước rồi tới publisher sau |
| `merge` | Subscribe nhiều publisher đồng thời | Interleave theo thời điểm phát; không bảo đảm thứ tự đầu vào |
| `zip` | Subscribe các nguồn và ghép phần tử theo vị trí | Ghép phần tử thứ n của mỗi nguồn; không ghép theo thời điểm hoàn tất |
| `collectList` | Tiêu thụ upstream rồi gom vào List | Giữ thứ tự mà upstream đã phát ra |
| `sort` / `collectSortedList` | Phải thu thập dữ liệu trước khi sắp xếp | Theo comparator sau khi có đủ dữ liệu |

Chọn toán tử dựa trên điều cần bảo đảm. Nếu chỉ cần phát kết quả theo thứ tự đầu vào nhưng muốn chạy I/O đồng thời, `flatMapSequential` phù hợp. Nếu cả thứ tự thực thi của các thao tác cũng phải tuần tự, dùng `concatMap`.

## 4. flatMap: ưu tiên concurrency, không giữ thứ tự đầu vào

`flatMap` biến mỗi phần tử thành một publisher rồi hợp nhất các publisher con. Các inner publisher có thể được subscribe đồng thời; phần tử nào sẵn sàng trước có thể được phát trước.

Ví dụ:

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .flatMap(value -> Mono.delay(delayFor(value))
                .map(ignored -> value));
```

Nếu thời gian xử lý của phần tử 3 ngắn hơn phần tử 1, kết quả có thể là `3, 2, 1` dù nguồn phát `1, 2, 3`.

Trong ứng dụng R2DBC:

```java
Flux<Customer> customers = Flux.fromIterable(List.of(10L, 20L, 30L))
        .flatMap(customerRepository::findById);
```

Các truy vấn có thể hoàn tất theo thứ tự khác nhau. Đây là lựa chọn tốt khi thứ tự không quan trọng và muốn tận dụng concurrency, nhưng không phù hợp nếu caller yêu cầu kết quả theo thứ tự danh sách ID.

### 4.1. Giới hạn concurrency của flatMap

Có thể giới hạn số inner publisher chạy đồng thời:

```java
source.flatMap(this::asyncOperation, 8);
```

Tham số `8` giới hạn số inner publisher được subscribe đồng thời theo overload tương ứng. Việc giới hạn concurrency giúp kiểm soát số truy vấn đang chạy, áp lực connection pool và tải lên dịch vụ ngoài.

Giới hạn concurrency không tạo ra thứ tự. Kết quả vẫn được phát theo thời điểm inner publisher phát dữ liệu.

## 5. flatMapSequential: chạy đồng thời nhưng phát theo thứ tự nguồn

`flatMapSequential` cho phép subscribe các inner publisher sớm và chạy đồng thời, nhưng giữ thứ tự phát kết quả theo thứ tự inner publisher được tạo từ upstream.

Ví dụ:

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .flatMapSequential(value -> Mono.delay(delayFor(value))
                .map(ignored -> value));
```

Ngay cả khi inner publisher của `3` hoàn tất trước `1`, Reactor vẫn giữ kết quả của `3` lại cho tới khi kết quả của `1` và `2` được phát theo thứ tự. Subscriber nhận `1, 2, 3`.

Trong Spring Data R2DBC:

```java
List<Long> requestedIds = List.of(10L, 20L, 30L);

Flux<Customer> customers = Flux.fromIterable(requestedIds)
        .flatMapSequential(customerRepository::findById, 8);
```

Các truy vấn có thể chạy đồng thời tối đa theo giới hạn đã đặt, còn các customer tìm thấy được phát theo thứ tự ID đầu vào.

### 5.1. Kết quả rỗng ở một inner publisher

`findById` trả `Mono.empty()` nếu không tìm thấy. `flatMapSequential` không tạo placeholder cho ID đó; nó chỉ giữ thứ tự tương đối của các phần tử thực sự được phát.

Ví dụ đầu vào `[10, 20, 30]`, trong đó ID `20` không tồn tại, kết quả có thể chỉ gồm customer `10` rồi customer `30`. Nếu cần giữ cả vị trí của ID không tìm thấy, hãy phát một kiểu kết quả bao gồm cả ID và trạng thái tìm thấy thay vì để inner publisher hoàn tất rỗng.

### 5.2. flatMapSequential không tuần tự hóa side effect

Điểm quan trọng: `flatMapSequential` giữ thứ tự **phát kết quả**, không buộc các inner publisher hoàn tất lần lượt. Các truy vấn hoặc side effect bên trong vẫn có thể chạy đồng thời.

Nếu các thao tác ghi phụ thuộc vào nhau hoặc thứ tự thực thi là bắt buộc, `flatMapSequential` không thay thế `concatMap`.

## 6. concatMap: xử lý từng publisher theo thứ tự

`concatMap` chỉ xử lý inner publisher tiếp theo sau khi inner publisher hiện tại hoàn tất. Nó giữ thứ tự phần tử nguồn và tuần tự hóa việc subscribe/thực thi các inner publisher trong pipeline.

Ví dụ:

```java
Flux<Customer> customers = Flux.fromIterable(List.of(10L, 20L, 30L))
        .concatMap(customerRepository::findById);
```

Trình tự xử lý:

1. Truy vấn customer `10` và chờ publisher hoàn tất.
2. Sau đó truy vấn customer `20`.
3. Sau đó truy vấn customer `30`.

Nếu ID `20` không tồn tại, publisher của nó hoàn tất rỗng rồi pipeline tiếp tục với ID `30`.

### 6.1. Khi nào nên dùng concatMap?

Dùng `concatMap` khi:

- Thao tác sau phụ thuộc vào kết quả hoặc side effect của thao tác trước.
- Các câu lệnh ghi cần thực hiện tuần tự.
- Một dịch vụ ngoài không hỗ trợ nhiều request đồng thời.
- Muốn kiểm soát tải và tránh nhiều thao tác cùng tranh chấp một tài nguyên.
- Thứ tự xử lý là một phần của hợp đồng nghiệp vụ.

Ví dụ cập nhật tuần tự:

```java
Flux<Void> updates = Flux.fromIterable(commands)
        .concatMap(command -> orderRepository.applyCommand(command));
```

Publisher của từng command phải hoàn tất trước khi command tiếp theo bắt đầu. Điều này hữu ích nếu command sau cần nhìn thấy thay đổi do command trước thực hiện.

### 6.2. Đánh đổi về thông lượng

`concatMap` không chạy các inner publisher đồng thời. Nếu mỗi truy vấn mất 100 ms và có 10 truy vấn độc lập, tổng thời gian có thể gần bằng tổng thời gian của từng truy vấn, thay vì tận dụng concurrency.

Chỉ dùng tuần tự khi thứ tự hoặc giới hạn tài nguyên yêu cầu. Nếu thao tác độc lập và chỉ cần thứ tự output, `flatMapSequential` có thể giữ thứ tự trong khi vẫn tận dụng concurrency.

## 7. So sánh ba toán tử thường dùng

| Yêu cầu | `flatMap` | `flatMapSequential` | `concatMap` |
| --- | --- | --- | --- |
| Inner publisher chạy đồng thời | Có | Có, theo giới hạn | Không |
| Kết quả theo thứ tự đầu vào | Không bảo đảm | Có | Có |
| Side effect được tuần tự hóa | Không | Không | Có |
| Có thể phải buffer kết quả đến sớm | Có thể interleave trực tiếp | Có, nếu inner sau hoàn tất trước inner trước | Không cần buffer để chờ thứ tự inner sau |
| Thông lượng khi I/O độc lập | Thường cao | Cao, có thể bị chặn bởi inner chậm ở đầu | Thấp hơn do tuần tự |
| Dùng khi | Thứ tự không quan trọng | Cần output đúng thứ tự, vẫn muốn concurrency | Cần thứ tự thực thi/side effect |

Quy tắc thực tế:

- Không cần thứ tự: `flatMap`.
- Cần output theo thứ tự nguồn: `flatMapSequential`.
- Cần thực thi tuần tự: `concatMap`.

## 8. Kết hợp nhiều publisher độc lập

Không phải mọi bài toán kết hợp bất đồng bộ đều bắt đầu từ một `Flux` rồi dùng `flatMap`. Có thể cần phối hợp nhiều nguồn dữ liệu độc lập.

### 8.1. Mono.zip: ghép kết quả theo vị trí nguồn

Ví dụ một màn hình cần thông tin customer và số đơn hàng:

```java
Mono<CustomerDashboard> dashboard = Mono.zip(
        customerRepository.findById(customerId),
        orderRepository.countByCustomerId(customerId),
        (customer, orderCount) -> new CustomerDashboard(customer, orderCount)
);
```

Hai truy vấn có thể hoàn tất theo thứ tự bất kỳ. `Mono.zip` giữ kết quả theo vị trí publisher được truyền vào: tham số đầu tiên của combinator là customer, tham số thứ hai là order count. Nó không hoán đổi hai giá trị theo thời điểm hoàn tất.

Nếu một nguồn `Mono` hoàn tất rỗng, `Mono.zip` thường không thể tạo tuple và kết quả cũng hoàn tất rỗng; cần xử lý trường hợp thiếu dữ liệu trước hoặc sau khi zip theo yêu cầu nghiệp vụ.

### 8.2. Flux.zip ghép phần tử thứ n

Với nhiều `Flux`, `zip` ghép phần tử theo vị trí phát ra:

```java
Flux<Tuple2<Customer, OrderSummary>> paired = Flux.zip(
        customerFlux,
        orderSummaryFlux);
```

Phần tử đầu tiên của nguồn A được ghép với phần tử đầu tiên của nguồn B, phần tử thứ hai ghép với phần tử thứ hai, v.v. Việc hai nguồn phát ở tốc độ khác nhau không làm `zip` ghép theo ID hoặc theo thời điểm gần nhau.

`zip` thường hoàn tất khi một nguồn không còn phần tử để tạo tuple tiếp theo. Vì vậy, nếu hai luồng có số lượng hoặc thứ tự phần tử không tương ứng, dữ liệu có thể không được ghép đúng ý nghĩa.

Nếu cần ghép theo khóa nghiệp vụ, hãy ghép bằng ID/map hoặc thực hiện JOIN trong database, không dựa vào vị trí của hai `Flux`.

### 8.3. zipWhen khi thao tác thứ hai phụ thuộc kết quả thứ nhất

`zipWhen` phù hợp khi cần lấy một giá trị rồi gọi thêm một publisher dựa trên giá trị đó:

```java
Mono<CustomerDashboard> dashboard = customerRepository.findById(customerId)
        .zipWhen(customer -> orderRepository.countByCustomerId(customer.getId()))
        .map(tuple -> new CustomerDashboard(
                tuple.getT1(),
                tuple.getT2()));
```

Publisher thứ hai được tạo từ kết quả của publisher thứ nhất. Dùng `zipWhen` giúp thể hiện quan hệ phụ thuộc này rõ hơn việc tự quản lý tuple thủ công.

### 8.4. when chỉ chờ hoàn tất, không ghép giá trị

Nếu cần chạy nhiều thao tác và chỉ quan tâm tất cả hoàn tất:

```java
Mono<Void> completed = Mono.when(
        auditRepository.writeAudit(entry),
        metricsPublisher.recordEvent(event));
```

`Mono.when` phối hợp completion của các nguồn; nó không phát tuple kết quả của từng nguồn. Các nguồn có thể chạy đồng thời và thứ tự hoàn tất không được bảo đảm.

Nếu các thao tác cần cùng một transaction R2DBC, cần bảo đảm chúng tham gia cùng transaction context/ConnectionFactory. Nếu chỉ cần chờ hoàn tất, `when` không tự tạo transaction hoặc bảo đảm atomicity.

## 9. concat và merge cho nhiều publisher đã có sẵn

Khi có sẵn nhiều publisher:

```java
Mono<Customer> first = customerRepository.findById(10L);
Mono<Customer> second = customerRepository.findById(20L);
```

`Mono.concat(first, second)` subscribe lần lượt, đợi publisher đầu hoàn tất rồi mới xử lý publisher thứ hai:

```java
Flux<Customer> ordered = Flux.concat(first, second);
```

`Flux.merge(first, second)` subscribe nhiều publisher đồng thời và phát phần tử khi chúng sẵn sàng:

```java
Flux<Customer> merged = Flux.merge(first, second);
```

Nếu `second` hoàn tất trước, `merge` có thể phát customer thứ hai trước customer thứ nhất. `concat` giữ thứ tự publisher đầu vào.

Với nhiều nguồn độc lập mà cần concurrency nhưng output theo thứ tự nguồn, có thể cân nhắc `mergeSequential` nếu phù hợp với kiểu publisher và Reactor version. Toán tử này subscribe các nguồn nhưng phát kết quả theo thứ tự nguồn như cách kết hợp tuần tự về output.

## 10. Giữ thứ tự ID khi dùng findAllById

Một lỗi thường gặp là giả định repository trả các entity theo đúng thứ tự danh sách ID đầu vào:

```java
List<Long> ids = List.of(30L, 10L, 20L);

return customerRepository.findAllById(ids);
```

Không nên giả định kết quả là `30, 10, 20`. Database có thể trả theo index hoặc kế hoạch truy vấn; hợp đồng repository không nhất thiết bảo đảm giữ thứ tự đầu vào.

Nếu thứ tự yêu cầu là thứ tự `ids`, có thể thu thập kết quả thành map rồi phát lại theo danh sách ID:

```java
public Flux<Customer> findInRequestedOrder(List<Long> requestedIds) {
    return customerRepository.findAllById(requestedIds)
            .collectMap(Customer::getId)
            .flatMapMany(foundById -> Flux.fromIterable(requestedIds)
                    .map(foundById::get)
                    .filter(Objects::nonNull));
}
```

Đặc điểm của cách làm này:

- Kết quả được phát theo đúng thứ tự `requestedIds`.
- ID không tồn tại bị bỏ qua.
- Nếu danh sách đầu vào có ID lặp, entity tương ứng cũng được phát lặp theo vị trí yêu cầu.
- Tất cả entity tìm thấy được giữ trong bộ nhớ dưới dạng map trước khi phát lại.

Nếu cần báo rõ ID nào không tồn tại, dùng một kết quả bao gồm cả ID yêu cầu và entity tùy chọn:

```java
public record CustomerLookup(Long requestedId, Optional<Customer> customer) {
}

public Flux<CustomerLookup> findAllInRequestedOrder(List<Long> requestedIds) {
    return customerRepository.findAllById(requestedIds)
            .collectMap(Customer::getId)
            .flatMapMany(foundById -> Flux.fromIterable(requestedIds)
                    .map(id -> new CustomerLookup(
                            id,
                            Optional.ofNullable(foundById.get(id)))));
}
```

Với danh sách ID rất lớn, việc gom toàn bộ entity vào map tiêu tốn bộ nhớ. Khi đó, có thể chia danh sách thành các batch, dùng truy vấn SQL có thứ tự rõ ràng hoặc thiết kế query trả về thứ tự theo yêu cầu.

## 11. Đặt thứ tự tùy chỉnh ngay trong SQL

Nếu muốn database trả kết quả theo thứ tự ID đầu vào, có thể biểu diễn thứ tự trong SQL. Cách viết phụ thuộc hệ quản trị.

Ví dụ PostgreSQL dùng `unnest` cùng `WITH ORDINALITY`:

```sql
SELECT c.id, c.name
FROM unnest(ARRAY[30, 10, 20]::BIGINT[]) WITH ORDINALITY AS requested(id, position)
JOIN customer c ON c.id = requested.id
ORDER BY requested.position;
```

`WITH ORDINALITY` gán vị trí cho từng ID trong mảng; `ORDER BY requested.position` trả kết quả theo đúng thứ tự đầu vào. Cú pháp và kiểu mảng phải phù hợp PostgreSQL driver. Khi dùng tham số bind, hãy xác nhận cách driver bind array.

Một số database có hàm riêng như `FIELD(...)` hoặc biểu thức `CASE`, nhưng không nên đưa cú pháp riêng vào repository dùng chung cho nhiều hệ quản trị mà không có lớp abstraction phù hợp.

Nếu thứ tự không phụ thuộc danh sách đầu vào mà phụ thuộc dữ liệu, `ORDER BY` theo cột nghiệp vụ thường rõ ràng và portable hơn.

## 12. flatMapSequential và xử lý nhiều truy vấn R2DBC

Ví dụ tải customer theo ID, cho phép tối đa 5 truy vấn đang hoạt động và giữ output theo thứ tự:

```java
public Flux<Customer> loadCustomers(List<Long> ids) {
    return Flux.fromIterable(ids)
            .flatMapSequential(customerRepository::findById, 5);
}
```

`5` là giới hạn concurrency của inner publisher. Nếu truy vấn đầu tiên chậm, kết quả của các truy vấn sau có thể hoàn tất nhưng phải chờ trong buffer cho đến khi kết quả đầu tiên được phát. Vì vậy, thứ tự output có thể tạo hiện tượng head-of-line blocking.

Điều chỉnh concurrency cần dựa trên:

- Kích thước connection pool.
- Khả năng xử lý đồng thời của database.
- Thời gian truy vấn và phân bố độ trễ.
- Số request cùng chạy trong ứng dụng.
- Bộ nhớ dành cho các kết quả đang chờ phát theo thứ tự.

Không nên đặt concurrency quá cao chỉ để tăng thông lượng. Nếu pool chỉ có 10 connection nhưng hàng trăm pipeline cùng mở nhiều truy vấn, các yêu cầu sẽ phải chờ acquire và làm tăng độ trễ.

### 12.1. Giới hạn concurrency của flatMapSequential

Có thể dùng overload:

```java
source.flatMapSequential(this::loadOne, maxConcurrency, prefetch);
```

- `maxConcurrency` giới hạn số inner publisher được subscribe đồng thời.
- `prefetch` điều khiển số phần tử được yêu cầu trước từ mỗi inner publisher theo semantics của toán tử.

Các tham số này ảnh hưởng áp lực tài nguyên và buffer. Hãy dùng giá trị vừa phải rồi đo thực tế thay vì chọn số lớn tùy ý.

## 13. Giữ thứ tự thực thi khi ghi nhiều bản ghi

Giả sử có các command cập nhật một đơn hàng theo trình tự:

1. Đánh dấu đã thanh toán.
2. Đóng đơn hàng.
3. Ghi nhận đã lưu kho.

Nếu các command phụ thuộc vào trạng thái do command trước tạo ra, không nên dùng `flatMap`:

```java
Flux.fromIterable(commands)
        .flatMap(orderRepository::applyCommand);
```

Các thao tác có thể chạy đồng thời và cạnh tranh trên cùng aggregate. Dùng `concatMap` để đảm bảo thao tác sau chỉ bắt đầu sau khi thao tác trước hoàn tất:

```java
Flux.fromIterable(commands)
        .concatMap(orderRepository::applyCommand);
```

Nếu mỗi command phải đọc trạng thái mới do command trước ghi, việc tuần tự hóa ở pipeline giúp thể hiện đúng phụ thuộc. Database vẫn cần constraint/version phù hợp nếu có request khác ngoài pipeline này cùng cập nhật đơn hàng.

### 13.1. flatMapSequential không bảo đảm thứ tự ghi

Đoạn sau có thể phát kết quả theo thứ tự command nhưng các câu lệnh ghi vẫn chạy đồng thời:

```java
Flux.fromIterable(commands)
        .flatMapSequential(orderRepository::applyCommand);
```

Nếu command thứ hai phụ thuộc việc command thứ nhất đã commit, dùng `concatMap`. Giữ thứ tự phát kết quả không đồng nghĩa database đã thực hiện các side effect theo cùng thứ tự.

## 14. Kết hợp thao tác trong cùng reactive transaction

Khi dùng `@Transactional`, các publisher trong cùng pipeline có thể tham gia một transaction reactive nếu chúng sử dụng cùng `ConnectionFactory` và transaction manager.

Với thao tác phụ thuộc, hãy nối bằng `flatMap` hoặc `then`:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> auditRepository.save(
                    new AuditEntry("ORDER_CREATED", saved.getId()))
                    .thenReturn(saved));
}
```

`flatMap` ở đây nối một publisher với publisher tiếp theo dựa trên kết quả đã lưu. Nó không làm hai thao tác độc lập chạy đồng thời.

Với nhiều thao tác độc lập:

```java
@Transactional
public Mono<Void> writeIndependentRecords(AuditEntry audit, MetricRecord metric) {
    return Mono.when(
            auditRepository.save(audit),
            metricRepository.save(metric));
}
```

`Mono.when` có thể subscribe hai thao tác cùng lúc. Tuy nhiên, nếu chúng tham gia cùng một R2DBC transaction, cả hai có thể dùng cùng một connection. Không phải mọi R2DBC driver đều cho phép nhiều statement thực thi đồng thời trên cùng connection; một số driver sẽ tuần tự hóa hoặc báo lỗi. Nếu cần thứ tự rõ ràng hoặc muốn tương thích rộng với driver, nối các thao tác bằng `then`/`concatMap`.

### 14.1. Thứ tự và transaction là hai yêu cầu khác nhau

- Transaction bảo đảm các thay đổi thuộc phạm vi được commit/rollback theo cùng lifecycle.
- `concatMap` bảo đảm inner publisher được xử lý lần lượt.
- `flatMapSequential` bảo đảm thứ tự phát output trong khi inner publisher có thể chạy đồng thời.
- `flatMap` cho phép interleave kết quả.

Transaction không tự tuần tự hóa mọi thao tác theo thứ tự nguồn. Muốn bảo đảm thứ tự thực thi, cần chọn toán tử phù hợp và hiểu khả năng của connection/driver.

## 15. parallel và sequential

Reactor có thể chia một `Flux` thành nhiều rail bằng `parallel()` và chạy chúng trên scheduler bằng `runOn()`:

```java
Flux<Integer> processed = Flux.range(1, 10)
        .parallel(4)
        .runOn(Schedulers.parallel())
        .map(this::cpuIntensiveOperation)
        .sequential();
```

`sequential()` gộp các rail thành một `Flux`, nhưng không khôi phục chắc chắn thứ tự ban đầu của các phần tử. Nó hợp nhất kết quả từ các rail theo cách phù hợp với việc xử lý song song; không nên coi nó như một toán tử sắp xếp theo index nguồn.

Nếu cần giữ thứ tự sau xử lý song song, có thể gắn index trước khi phân luồng rồi sắp xếp lại theo index sau khi hoàn tất:

```java
record IndexedResult<T>(long index, T value) {
}

Flux<Result> ordered = Flux.fromIterable(inputs)
        .index()
        .parallel(4)
        .runOn(Schedulers.parallel())
        .map(tuple -> new IndexedResult<>(
                tuple.getT1(),
                process(tuple.getT2())))
        .sequential()
        .sort(Comparator.comparingLong(IndexedResult::index))
        .map(IndexedResult::value);
```

`sort` phải thu thập các phần tử trước khi phát kết quả đã sắp xếp, nên cách này cần bộ nhớ tỷ lệ với số phần tử. Chỉ dùng khi tập dữ liệu hữu hạn và kích thước có thể kiểm soát. Nếu cần xử lý streaming với thứ tự, cân nhắc `concatMap` hoặc `flatMapSequential` ngay từ đầu.

`parallel()` thường phù hợp cho xử lý CPU-bound hơn là tạo concurrency tùy tiện cho R2DBC I/O. Không nên chạy nhiều truy vấn database trên các rail mà không tính đến pool và giới hạn driver.

## 16. Sort và collectSortedList: khi nào nên dùng?

Reactor có thể sắp xếp kết quả sau khi đã thu thập:

```java
Mono<List<Customer>> sorted = customerRepository.findAll()
        .collectSortedList(Comparator.comparing(Customer::getName));
```

Hoặc:

```java
Flux<Customer> sortedFlux = customerRepository.findAll()
        .sort(Comparator.comparing(Customer::getName));
```

Hai cách này cần giữ các phần tử để sắp xếp trước khi phát kết quả. Chúng không phù hợp với luồng vô hạn hoặc tập dữ liệu quá lớn.

Nếu database có thể sắp xếp, thường nên dùng `ORDER BY` vì database có thể tận dụng index và chỉ trả dữ liệu theo thứ tự cần thiết. Dùng Reactor sort khi thứ tự dựa trên logic Java không thể biểu đạt dễ dàng trong SQL hoặc dữ liệu đã nằm trong bộ nhớ với kích thước nhỏ.

Không dùng `sort` để sửa một pipeline `flatMap` khi chỉ cần giữ thứ tự đầu vào. `flatMapSequential` hoặc `concatMap` thể hiện ý định chính xác hơn và có thể tránh thu thập toàn bộ kết quả.

## 17. Giữ tương quan giữa kết quả và request ban đầu

Khi gọi dịch vụ ngoài hoặc repository, nên giữ khóa tương quan thay vì dựa vào vị trí nếu thứ tự có thể thay đổi.

Ví dụ:

```java
record CustomerResult(Long requestedId, Customer customer) {
}

Flux<CustomerResult> results = Flux.fromIterable(requestedIds)
        .flatMap(id -> customerRepository.findById(id)
                .map(customer -> new CustomerResult(id, customer)));
```

Kết quả có thể phát theo completion order, nhưng mỗi entity vẫn mang `requestedId` tương ứng. Caller có thể ghép theo ID bằng map mà không nhầm customer với request khác.

Nếu cần cả kết quả không tìm thấy:

```java
record CustomerLookupResult(Long requestedId, Optional<Customer> customer) {
}

Flux<CustomerLookupResult> results = Flux.fromIterable(requestedIds)
        .flatMap(id -> customerRepository.findById(id)
                .map(customer -> new CustomerLookupResult(
                        id, Optional.of(customer)))
                .defaultIfEmpty(new CustomerLookupResult(id, Optional.empty())));
```

Ở ví dụ này, `flatMap` có thể phát theo completion order nhưng mọi kết quả đều chứa ID gốc và trạng thái tìm thấy. Nếu caller còn yêu cầu thứ tự đầu vào, thay `flatMap` bằng `flatMapSequential`.

## 18. Backpressure, buffering và hiện tượng chờ đầu hàng

Khi dùng `flatMapSequential`, inner publisher sau có thể hoàn tất trước nhưng kết quả phải chờ inner publisher đứng trước. Reactor cần buffer các kết quả đến sớm.

Ví dụ:

- Truy vấn ID 1 mất 2 giây.
- Truy vấn ID 2 mất 50 ms.
- Truy vấn ID 3 mất 70 ms.
- Cả ID 2 và 3 hoàn tất trước ID 1.

Subscriber vẫn chưa nhận được ID 2 và 3 cho đến khi ID 1 có thể được phát theo thứ tự. Đây là **head-of-line blocking** ở lớp phát kết quả.

Để kiểm soát tài nguyên:

- Đặt `maxConcurrency` phù hợp với pool và tải database.
- Đặt `prefetch` vừa phải khi inner publisher phát nhiều phần tử.
- Chỉ giữ thứ tự nếu caller thực sự cần.
- Nếu thứ tự chỉ cần ở một bước cuối, cân nhắc giữ ID/index rồi ghép hoặc sắp xếp tại bước đó.
- Tránh gom toàn bộ luồng lớn thành List hoặc Map nếu có thể xử lý theo batch.

Backpressure giúp subscriber điều tiết nhu cầu phần tử, nhưng không xóa bỏ chi phí buffer do phải giữ thứ tự khi các inner publisher hoàn tất không đồng đều.

## 19. Error và cancellation khi kết hợp nhiều thao tác

Khi một inner publisher phát lỗi, toán tử kết hợp có thể truyền lỗi xuống và hủy các inner publisher còn lại theo chính sách mặc định. Điều này ảnh hưởng tới các thao tác đang chạy.

Ví dụ:

```java
Flux.fromIterable(ids)
        .flatMapSequential(customerRepository::findById, 8);
```

Nếu một truy vấn lỗi, pipeline có thể kết thúc bằng error signal và các truy vấn khác đang hoạt động bị cancel. Không nên giả định tất cả truy vấn đã được khởi chạy sẽ hoàn tất và phát kết quả.

Nếu nghiệp vụ cần thu thập lỗi riêng cho từng phần tử rồi tiếp tục, có thể chuyển lỗi thành một kiểu kết quả có phân loại bên trong mapper:

```java
record LookupOutcome(Long id, Customer customer, Throwable error) {
}

Flux<LookupOutcome> outcomes = Flux.fromIterable(ids)
        .flatMapSequential(id -> customerRepository.findById(id)
                .map(customer -> new LookupOutcome(id, customer, null))
                .onErrorResume(error -> Mono.just(
                        new LookupOutcome(id, null, error)))
                .defaultIfEmpty(new LookupOutcome(id, null, null)));
```

Ví dụ dùng `null` để minh họa một trong ba trạng thái; trong code domain thực tế, nên dùng `Optional`, sealed interface hoặc kiểu kết quả chuyên biệt để phân biệt not found với error rõ ràng.

Không nên nuốt mọi lỗi thành “không tìm thấy”. Lỗi kết nối, timeout và lỗi SQL cần được phân biệt với kết quả rỗng.

## 20. Ví dụ tổng hợp trong Spring Data R2DBC

Giả sử API nhận danh sách ID khách hàng, cần tải dữ liệu đồng thời, giữ thứ tự đầu vào và trả rõ ID không tồn tại:

```java
public record CustomerLookup(
        Long requestedId,
        Optional<Customer> customer) {
}

@Service
public class CustomerLookupService {

    private final CustomerRepository customerRepository;

    public CustomerLookupService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Flux<CustomerLookup> findInInputOrder(List<Long> ids) {
        return Flux.fromIterable(ids)
                .flatMapSequential(id -> customerRepository.findById(id)
                        .map(customer -> new CustomerLookup(
                                id, Optional.of(customer)))
                        .defaultIfEmpty(new CustomerLookup(
                                id, Optional.empty())),
                        8);
    }
}
```

Hành vi:

1. ID được nhận theo thứ tự của danh sách đầu vào.
2. Tối đa 8 truy vấn được subscribe đồng thời.
3. Kết quả của mỗi truy vấn gắn với ID đã yêu cầu.
4. Nếu ID không tồn tại, vẫn có một `CustomerLookup` với `Optional.empty()`.
5. Các kết quả được phát theo thứ tự danh sách ID ban đầu.

Nếu cần tuần tự hóa cả các truy vấn, đổi `flatMapSequential` thành `concatMap` và bỏ tham số concurrency. Nếu không cần thứ tự, có thể dùng `flatMap` để tránh chờ kết quả đầu hàng.

## 21. Kiểm thử thứ tự bằng StepVerifier

Có thể tạo các inner publisher hoàn tất theo thời gian ngược nhau để quan sát hành vi:

```java
private Mono<Integer> delayedValue(int value) {
    long delayMillis = (4L - value) * 100L;
    return Mono.delay(Duration.ofMillis(delayMillis))
            .map(ignored -> value);
}
```

`flatMap` không bảo đảm thứ tự:

```java
Flux<Integer> unordered = Flux.just(1, 2, 3)
        .flatMap(this::delayedValue);
```

Với các độ trễ đã chọn, kết quả thường hoàn tất theo `3, 2, 1`, nhưng không nên viết test dựa vào một lịch chạy chính xác của scheduler. Mục tiêu là xác nhận toán tử không có hợp đồng giữ thứ tự.

`flatMapSequential` giữ thứ tự:

```java
Flux<Integer> ordered = Flux.just(1, 2, 3)
        .flatMapSequential(this::delayedValue, 3);

StepVerifier.create(ordered)
        .expectNext(1, 2, 3)
        .verifyComplete();
```

`concatMap` cũng giữ thứ tự và tuần tự hóa:

```java
Flux<Integer> sequential = Flux.just(1, 2, 3)
        .concatMap(this::delayedValue);

StepVerifier.create(sequential)
        .expectNext(1, 2, 3)
        .verifyComplete();
```

Ngoài test Reactor thuần, integration test R2DBC nên kiểm tra:

- Query có `ORDER BY` trả đúng thứ tự khi có giá trị sort trùng nhau.
- `findAllById` không bị giả định giữ thứ tự ID đầu vào.
- `flatMapSequential` giữ output khi truy vấn có độ trễ khác nhau.
- `concatMap` thực thi thao tác phụ thuộc theo thứ tự.
- Kết quả rỗng và lỗi của từng truy vấn được xử lý đúng.
- Concurrency không vượt giới hạn mong muốn và không làm cạn connection pool.

## 22. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Kết quả phát khác thứ tự ID đầu vào | Dùng `flatMap` với các inner publisher có độ trễ khác nhau | Dùng `flatMapSequential` hoặc `concatMap` |
| Kết quả SQL thay đổi thứ tự giữa các lần chạy | Query không có `ORDER BY` | Sắp xếp trong SQL và thêm tie-breaker ổn định |
| flatMapSequential vẫn chạy side effect đồng thời | Toán tử giữ thứ tự output nhưng subscribe inner publisher đồng thời | Dùng `concatMap` nếu cần tuần tự hóa side effect |
| concatMap quá chậm | Tất cả inner publisher được xử lý lần lượt | Dùng `flatMapSequential` nếu chỉ cần thứ tự output |
| Kết quả bị thiếu khi zip hai Flux | `zip` ghép theo vị trí và hoàn tất khi không còn tuple | Ghép theo ID/key hoặc dùng JOIN phù hợp |
| findAllById không theo thứ tự danh sách ID | Repository/database không cam kết thứ tự đầu vào | Reorder bằng map hoặc biểu đạt thứ tự trong SQL |
| Sort làm tăng bộ nhớ mạnh | `sort`/`collectSortedList` phải thu thập toàn bộ dữ liệu | Dùng ORDER BY hoặc xử lý theo batch |
| parallel().sequential() vẫn đảo thứ tự | `sequential()` chỉ gộp rail, không khôi phục index nguồn | Gắn index và sắp xếp lại, hoặc dùng toán tử giữ thứ tự từ đầu |
| Các thao tác ghi trong transaction chạy không như mong đợi | Nhiều publisher cạnh tranh trên cùng connection hoặc bị subscribe tách rời | Nối tuần tự và giữ một reactive pipeline |
| Truy vấn chậm làm các kết quả sau bị chờ | Head-of-line blocking của flatMapSequential | Cân nhắc thứ tự có thực sự cần; điều chỉnh concurrency và query |
| Lỗi một phần tử làm cả pipeline dừng | Error signal truyền ra ngoài mapper | Chuyển lỗi thành kết quả riêng nếu nghiệp vụ cho phép tiếp tục |

## 23. Quy trình chọn toán tử để giữ thứ tự

Khi kết hợp nhiều thao tác bất đồng bộ, hãy xác định yêu cầu theo thứ tự sau:

1. Database có cần trả hàng theo thứ tự nghiệp vụ không? Nếu có, dùng `ORDER BY` với tie-breaker rõ ràng.
2. Có cần giữ thứ tự phần tử đầu vào khi gọi nhiều publisher không?
3. Các thao tác có độc lập hay thao tác sau phụ thuộc side effect của thao tác trước?
4. Nếu chỉ cần output theo thứ tự nguồn và vẫn muốn concurrency, dùng `flatMapSequential` với giới hạn phù hợp.
5. Nếu cả việc thực thi phải tuần tự, dùng `concatMap` hoặc `concat`.
6. Nếu thứ tự không quan trọng, dùng `flatMap`/`merge` và giới hạn concurrency để kiểm soát tải.
7. Nếu ghép nhiều nguồn, xác định cần ghép theo vị trí (`zip`) hay theo khóa nghiệp vụ.
8. Nếu kết quả cần khớp với request gốc, giữ ID/index trong kiểu kết quả.
9. Tránh `sort` hoặc `collectList` trên luồng lớn nếu có thể giải quyết thứ tự ở database hoặc ngay trong toán tử kết hợp.
10. Kiểm thử thứ tự, lỗi, cancellation, concurrency và transaction bằng publisher có độ trễ khác nhau cùng database/driver thực tế.

Giữ thứ tự kết quả trong reactive pipeline là lựa chọn có chủ đích giữa concurrency, độ trễ và bộ nhớ. `flatMap` ưu tiên phát kết quả khi sẵn sàng; `flatMapSequential` cho phép chạy đồng thời nhưng phát theo thứ tự nguồn; `concatMap` tuần tự hóa cả việc xử lý inner publisher. Với Spring Data R2DBC, cần kết hợp các toán tử này với `ORDER BY` ở SQL, giữ khóa tương quan khi ghép kết quả và hiểu rõ ranh giới transaction để thứ tự dữ liệu, thứ tự phát và thứ tự side effect không bị nhầm lẫn.
