# Lựa chọn mức đồng thời để bảo vệ pool kết nối

Ứng dụng Spring Data R2DBC có thể phát sinh nhiều truy vấn database cùng lúc nhờ API reactive và non-blocking I/O. Tuy nhiên, số kết nối tới database luôn hữu hạn. Nếu một luồng xử lý tạo quá nhiều truy vấn đồng thời, các truy vấn sẽ tranh nhau connection trong pool, làm tăng thời gian chờ, gây timeout và có thể khiến toàn bộ ứng dụng chậm đi.

Vì vậy, thiết kế reactive cần kiểm soát mức đồng thời (*concurrency*) ở cả luồng xử lý và tầng kết nối. Các toán tử Reactor như `flatMap` cho phép giới hạn số publisher con đang hoạt động; connection pool giới hạn số kết nối vật lý được mượn cùng lúc; còn giới hạn toàn ứng dụng giúp tránh việc nhiều request độc lập cộng dồn thành tải vượt khả năng database.

Mục tiêu không phải tạo nhiều truy vấn nhất có thể. Mục tiêu là giữ số thao tác database đang hoạt động trong phạm vi pool và năng lực xử lý của database, đồng thời vẫn duy trì backpressure, thời gian phản hồi và mức sử dụng tài nguyên có thể dự đoán.

## 1. Vì sao cần giới hạn concurrency?

Giả sử một request cần lấy thông tin của 100 khách hàng. Một cách viết đơn giản là duyệt danh sách ID và gọi repository cho từng ID:

```java
return Flux.fromIterable(customerIds)
        .flatMap(customerRepository::findById);
```

`flatMap` có thể subscribe vào nhiều publisher con cùng lúc. Nếu không đặt giới hạn concurrency, số truy vấn đang chờ hoặc đang chạy có thể tăng theo kích thước danh sách và theo số request đồng thời của ứng dụng.

Giả sử có 40 request cùng thực hiện luồng trên, mỗi request chứa 100 ID. Hệ thống có thể tạo ra hàng nghìn thao tác đọc trong một khoảng thời gian ngắn. Nếu pool chỉ có 30 connection, các thao tác vượt quá số connection khả dụng phải chờ lấy connection. Thời gian chờ tăng, hàng đợi pool dài hơn và request có thể hết thời gian chờ trước khi truy vấn được thực thi.

Concurrency cần được giới hạn vì:

- **Pool có kích thước hữu hạn:** một connection chỉ có thể được mượn cho một phạm vi thao tác tại một thời điểm theo cách sử dụng thông thường.
- **Database có giới hạn tài nguyên:** quá nhiều truy vấn đồng thời có thể làm tăng CPU, I/O, lock contention và bộ nhớ.
- **Ứng dụng có nhiều request cùng lúc:** giới hạn trong một pipeline không đồng nghĩa giới hạn toàn hệ thống.
- **Backpressure cần được giữ xuyên suốt:** không nên tạo hàng loạt công việc chỉ để chúng xếp hàng chờ connection.
- **Timeout có thể cộng dồn:** request chờ pool, chờ query và chờ dịch vụ khác có thể vượt deadline của HTTP request.

## 2. Ba lớp kiểm soát concurrency

Để quản lý tài nguyên đúng cách, cần phân biệt ba lớp:

```text
Incoming requests
       |
       v
Application admission / bulkhead
(giới hạn công việc database toàn ứng dụng)
       |
       v
Reactive pipeline
(flatMap concurrency, concatMap, batching)
       |
       v
R2DBC Connection Pool
(max-size, acquire timeout, pending borrowers)
       |
       v
Database
(CPU, I/O, locks, max connections)
```

| Lớp | Cơ chế | Phạm vi kiểm soát |
|---|---|---|
| Luồng reactive | `flatMap` với concurrency, `concatMap`, batch | Số publisher con đang hoạt động trong một subscription |
| Ứng dụng | Bulkhead hoặc giới hạn admission theo loại công việc | Tổng công việc được phép đi vào một nhóm truy vấn trên một instance ứng dụng |
| Connection pool | `max-size`, thời gian chờ lấy connection | Số connection đồng thời được mượn từ một pool |
| Database | Giới hạn connection, workload, query plan | Năng lực tổng thể của hệ quản trị cơ sở dữ liệu |

Không có một lớp nào thay thế hoàn toàn các lớp còn lại. Pool là hàng rào cuối cùng cho connection, nhưng nếu mọi request đều tạo hàng trăm publisher rồi để chúng xếp hàng tại pool, ứng dụng vẫn tốn bộ nhớ và tăng độ trễ. Ngược lại, giới hạn `flatMap` trong một request không thể kiểm soát tổng số truy vấn của mọi request đang chạy.

## 3. Giới hạn số publisher đang hoạt động bằng Reactor

### 3.1. `flatMap` không giới hạn và có giới hạn

`flatMap` chuyển mỗi phần tử nguồn thành một publisher con rồi hợp nhất kết quả. Có thể truyền `concurrency` để giới hạn số publisher con được subscribe đồng thời:

```java
Flux<Customer> findCustomers(List<Long> ids) {
    return Flux.fromIterable(ids)
            .flatMap(customerRepository::findById, 8);
}
```

Trong ví dụ, một subscription chỉ cho phép tối đa 8 thao tác `findById` được hoạt động đồng thời qua `flatMap` tại vị trí này. Khi một publisher con hoàn tất, `flatMap` mới subscribe vào phần tử tiếp theo.

Có thể chỉ định cả `prefetch`:

```java
return Flux.fromIterable(ids)
        .flatMap(customerRepository::findById, 8, 1);
```

- `concurrency = 8`: số publisher con tối đa được subscribe đồng thời.
- `prefetch = 1`: số phần tử được yêu cầu trước từ mỗi publisher con trong cấu hình này.

Với publisher database thường phát một kết quả qua `Mono`, prefetch không phải giới hạn connection. Tham số concurrency mới là yếu tố trực tiếp giới hạn số thao tác con đang hoạt động ở điểm `flatMap` đó.

### 3.2. `concatMap` khi cần tuần tự

Nếu thao tác phải chạy lần lượt hoặc không cần đồng thời, dùng `concatMap`:

```java
return Flux.fromIterable(customerIds)
        .concatMap(customerRepository::findById);
```

`concatMap` chỉ subscribe publisher con tiếp theo sau khi publisher hiện tại hoàn tất. Cách này giữ số thao tác con đang hoạt động ở mức một và giữ thứ tự phát kết quả theo thứ tự đầu vào.

Nên dùng khi:

- Các bước phụ thuộc kết quả của bước trước.
- Cần kiểm soát tải chặt chẽ.
- Thao tác nằm trong một transaction dùng chung connection.
- Thứ tự thực hiện là một phần của nghiệp vụ.

Đổi lại, xử lý tuần tự có thể làm giảm throughput nếu các thao tác độc lập và database còn khả năng xử lý song song.

### 3.3. `flatMapSequential` khi cần giữ thứ tự đầu ra

`flatMapSequential` cho phép publisher con chạy đồng thời nhưng phát kết quả theo thứ tự của phần tử nguồn:

```java
return Flux.fromIterable(customerIds)
        .flatMapSequential(customerRepository::findById, 8, 1);
```

Toán tử này hữu ích khi thứ tự đầu ra quan trọng nhưng các truy vấn độc lập. Tuy nhiên, nếu một publisher đầu vào hoàn tất chậm, kết quả của các publisher sau có thể phải chờ trong bộ đệm. Vì vậy, giữ thứ tự có thể tăng lượng dữ liệu tạm giữ trong bộ nhớ.

### 3.4. So sánh các toán tử

| Toán tử | Số publisher con đồng thời | Thứ tự đầu ra | Trường hợp phù hợp |
|---|---:|---|---|
| `flatMap(mapper)` | Theo khả năng subscribe/prefetch mặc định, không phải giới hạn nghiệp vụ rõ ràng | Có thể xen kẽ | Chỉ khi mức đồng thời mặc định phù hợp và nguồn đã được kiểm soát |
| `flatMap(mapper, concurrency)` | Tối đa `concurrency` | Có thể xen kẽ | Truy vấn độc lập, cần giới hạn tải |
| `concatMap(mapper)` | 1 | Giữ thứ tự | Thao tác tuần tự hoặc cần kiểm soát chặt |
| `flatMapSequential(mapper, concurrency)` | Tối đa `concurrency` | Giữ thứ tự nguồn | Xử lý đồng thời nhưng cần thứ tự đầu ra |

Không nên dựa vào giá trị mặc định của toán tử để bảo vệ database. Hãy đặt concurrency rõ ràng ở vị trí tạo fan-out tới repository.

## 4. Giới hạn concurrency theo từng request không phải giới hạn toàn ứng dụng

Đây là điểm quan trọng khi thiết kế hệ thống có nhiều request đồng thời.

Giả sử mỗi request dùng:

```java
.flatMap(repository::findById, 8)
```

Giới hạn 8 chỉ áp dụng cho một subscription. Nếu 20 request chạy cùng lúc, mỗi request có thể có tối đa 8 publisher con tại vị trí đó. Tổng số publisher con đang hoạt động có thể đạt khoảng 160, trong khi pool có thể chỉ có 30 connection.

```text
Request A: up to 8 database operations --+
Request B: up to 8 database operations --+
Request C: up to 8 database operations --+--> Pool max-size = 30
...                                      --+
Request T: up to 8 database operations --+
```

Pool vẫn giữ giới hạn connection vật lý, nhưng những thao tác còn lại sẽ chờ. Nếu tải đầu vào tiếp tục tăng, hàng đợi và thời gian chờ sẽ tăng theo.

Do đó, cần kết hợp:

- Giới hạn fan-out bên trong mỗi pipeline.
- Giới hạn tổng công việc database của một loại use case khi cần.
- Cấu hình pool phù hợp với ngân sách connection của database.
- Giới hạn request đầu vào hoặc trả lỗi quá tải khi hệ thống đã đạt ngưỡng.

Một bulkhead ở cấp ứng dụng có thể giới hạn số tác vụ cùng loại được phép chạy trên một instance. Các thư viện như Resilience4j cung cấp reactive bulkhead integration; nếu sử dụng, cần cấu hình giới hạn và chính sách từ chối/chờ phù hợp. Đừng nhầm bulkhead theo instance với giới hạn toàn cụm: nếu có nhiều instance, tổng concurrency vẫn là tổng của từng instance.

## 5. Cấu hình R2DBC connection pool

R2DBC connection pool quản lý việc tạo, cấp phát và tái sử dụng connection. Với Spring Boot, khi dependency pool và auto-configuration phù hợp có mặt, có thể cấu hình pool qua các thuộc tính `spring.r2dbc.pool.*`.

Ví dụ cấu hình minh họa:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:store}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 30
      max-idle-time: 20m
      max-life-time: 30m
      max-acquire-time: 2s
      max-create-connection-time: 3s
```

Các thuộc tính có thể khác nhau theo phiên bản Spring Boot và R2DBC Pool. Hãy kiểm tra configuration metadata/documentation của phiên bản dự án trước khi sao chép cấu hình vào production.

Ý nghĩa các thuộc tính thường gặp:

| Thuộc tính | Mục đích |
|---|---|
| `enabled` | Bật/tắt pool khi auto-configuration hỗ trợ |
| `initial-size` | Số connection ban đầu được tạo |
| `max-size` | Số connection tối đa trong pool |
| `max-idle-time` | Thời gian connection có thể ở trạng thái idle trước khi bị loại bỏ theo chính sách pool |
| `max-life-time` | Tuổi thọ tối đa của một connection |
| `max-acquire-time` | Thời gian tối đa chờ mượn connection |
| `max-create-connection-time` | Thời gian tối đa cho việc tạo connection mới |

Một số phiên bản còn cung cấp tùy chọn validation, retry khi acquire hoặc các giới hạn khác. Chỉ bật và đặt giá trị khi hiểu hành vi của driver/database và phiên bản thư viện đang dùng.

### 5.1. `max-size` là giới hạn connection, không phải giới hạn request

Nếu `max-size` là 30, pool chỉ cho phép tối đa 30 connection được cấp phát đồng thời từ pool đó. Nó không có nghĩa ứng dụng chỉ nhận 30 request hoặc chỉ có 30 publisher. Nhiều request có thể đang chờ acquire connection trong khi chỉ một số thao tác có connection để chạy.

### 5.2. Thời gian chờ acquire

`max-acquire-time` giới hạn thời gian một thao tác chờ lấy connection. Nếu hết thời gian mà pool không cấp được connection, publisher phát lỗi. Giá trị quá dài khiến request bị treo lâu khi pool bão hòa; giá trị quá ngắn có thể từ chối tải đột biến mà hệ thống vẫn có khả năng xử lý sau một khoảng chờ ngắn.

Chọn thời gian acquire dựa trên deadline của request và latency mục tiêu. Tổng thời gian chờ pool, thực thi query và xử lý response phải nằm trong ngân sách thời gian của request.

### 5.3. `initial-size` và `max-size`

`initial-size` ảnh hưởng số connection được tạo ban đầu, còn `max-size` là giới hạn pool. Không cần đặt initial-size bằng max-size trong mọi môi trường. Pool quá lớn có thể chiếm connection của database ngay cả khi tải thấp; pool quá nhỏ có thể làm các thao tác chờ trong giờ cao điểm.

### 5.4. Không tăng pool chỉ để xóa hàng đợi

Nếu pool bão hòa, tăng `max-size` có thể giúp trong ngắn hạn nhưng cũng có thể làm database chịu nhiều truy vấn đồng thời hơn mức nó xử lý tốt. Trước khi tăng, hãy kiểm tra query latency, CPU, I/O, lock wait, số connection thực tế và số truy vấn đang chạy. Tối ưu query hoặc giảm fan-out thường hiệu quả hơn việc chỉ tăng số connection.

## 6. Tính ngân sách connection cho toàn hệ thống

Pool phải được tính theo tổng số instance ứng dụng và các thành phần khác cùng dùng database.

Ví dụ:

- Database cho phép tối đa 200 connection.
- Cần dành 40 connection cho quản trị, migration, monitoring và các dịch vụ khác.
- Có 4 instance ứng dụng.
- Mỗi instance có một pool R2DBC.

Ngân sách tối đa cho ứng dụng là 160 connection. Nếu chia đều, mỗi instance có thể có `max-size` khoảng 40. Đây chỉ là ví dụ số học; trong thực tế cần chừa thêm headroom cho failover, scaling tạm thời, worker nền và các pool khác.

```text
Database connection budget = 200

Reserved for other clients  = 40
Application budget          = 160

4 app instances
160 / 4 = 40 connections per instance (upper budget)
```

Công thức tham khảo:

\[
\text{Tổng connection tối đa}
= \sum_{i=1}^{N} \text{poolMaxSize}_i
+ \text{connection của client khác}
\]

Tổng này phải thấp hơn giới hạn database và nên có khoảng dự phòng. Nếu autoscaling cho phép tăng từ 4 lên 10 instance, cần tính theo số instance tối đa có thể chạy, không chỉ số instance hiện tại.

### 6.1. Dành headroom cho công việc khác

Không dành toàn bộ connection cho HTTP request. Database có thể cần connection cho:

- Migration hoặc tác vụ quản trị.
- Monitoring, backup và maintenance.
- Worker nền, scheduler hoặc consumer.
- Một dịch vụ khác dùng chung database.
- Kết nối dự phòng khi rollout hoặc autoscaling.

Pool của một ứng dụng không nhìn thấy các connection từ client khác. Việc phối hợp ngân sách cần được tính ở cấp hệ thống.

## 7. Ước lượng concurrency từ thời gian giữ connection

Một cách ước lượng ban đầu là dùng định luật Little cho số công việc đang hoạt động:

\[
L = \lambda \times W
\]

Trong đó:

- (L) là số thao tác trung bình đang được phục vụ.
- (λ) là tốc độ hoàn thành thao tác mỗi giây.
- (W) là thời gian trung bình một thao tác giữ tài nguyên, ở đây là thời gian connection được mượn.

Ví dụ, nếu hệ thống cần hoàn thành trung bình 300 query/giây và mỗi query giữ connection trung bình 40 ms (0,04 giây), số connection trung bình cần cho tải đó xấp xỉ:

\[
L = 300 \times 0.04 = 12
\]

Đây là ước lượng trung bình, không phải giá trị pool tối ưu. Cần thêm headroom cho peak load, biến động latency, query chậm, transaction dài và workload khác. Nếu connection bị giữ 200 ms thay vì 40 ms, cùng throughput đó cần mức concurrency trung bình lớn hơn nhiều.

Điểm cần đo là thời gian connection thực sự được mượn, không chỉ thời gian CPU của đoạn Java. Query chờ lock, transaction chờ thao tác bên ngoài hoặc stream kết quả dài có thể giữ connection lâu.

## 8. Chọn concurrency cho từng loại luồng xử lý

Không nên dùng một giá trị concurrency duy nhất cho mọi truy vấn. Các use case có đặc điểm khác nhau:

| Loại công việc | Cách điều khiển thường phù hợp |
|---|---|
| Đọc một bản ghi theo ID | Một repository call; không cần fan-out |
| Đọc nhiều ID độc lập trong một request | `flatMap(..., concurrency)` hoặc query `IN` theo nhóm |
| Ghi các bản ghi phụ thuộc nhau | `concatMap` hoặc nối tuần tự |
| Xử lý batch lớn | Chia batch, `concatMap` hoặc `flatMap` có giới hạn |
| Truy vấn trong cùng reactive transaction | Ưu tiên tuần tự nếu dùng chung connection; kiểm tra khả năng driver trước khi chạy đồng thời |
| Tác vụ nền có thể chạy dài | Bulkhead/worker concurrency riêng, không dùng chung ngân sách không giới hạn với HTTP |
| Công việc CPU sau khi đọc dữ liệu | Tách xử lý CPU khỏi thao tác database; chọn scheduler phù hợp và không giữ connection lâu |

### 8.1. Ưu tiên truy vấn theo nhóm thay vì fan-out từng ID

Nếu cần lấy bản ghi theo nhiều ID, một truy vấn `WHERE id IN (...)` thường tốt hơn việc gọi repository một lần cho mỗi ID:

```java
return customerRepository.findByIdIn(customerIds);
```

Điều này giảm số lần acquire connection và số câu SQL. Với tập ID lớn, chia thành batch để tránh giới hạn bind parameter và câu lệnh quá lớn.

### 8.2. Giới hạn concurrency cho batch

```java
return Flux.fromIterable(customerIds)
        .buffer(200)
        .concatMap(customerRepository::findByIdIn);
```

Ví dụ chia ID thành các batch 200 và truy vấn tuần tự. Nếu cần xử lý song song, có thể dùng:

```java
return Flux.fromIterable(customerIds)
        .buffer(200)
        .flatMap(customerRepository::findByIdIn, 3);
```

Trong một subscription, tối đa 3 batch query được hoạt động đồng thời. Giá trị 200 và 3 chỉ là ví dụ; chọn theo giới hạn parameter, kích thước kết quả và pool budget.

### 8.3. Ghi dữ liệu theo thứ tự

Nếu nhiều thao tác ghi phụ thuộc thứ tự, dùng `concatMap`:

```java
return Flux.fromIterable(events)
        .concatMap(event -> repository.save(toEntity(event)));
```

Nếu các thao tác ghi độc lập, có thể dùng `flatMap` với giới hạn concurrency, nhưng cần xem xét unique constraint, transaction, thứ tự phát event và khả năng retry. Không tăng concurrency cho ghi chỉ để tăng tốc nếu database đang chịu lock contention.

## 9. Transaction reactive và connection pool

Transaction reactive thường gắn một connection với Reactor Context trong suốt phạm vi transaction. Điều này có nghĩa nhiều repository call trong cùng transaction thường sử dụng cùng connection, thay vì mỗi publisher con tự mượn một connection độc lập.

### 9.1. Không giả định truy vấn song song trong transaction

Ví dụ:

```java
@Transactional
public Flux<OrderLineEntity> loadAndProcess(List<Long> orderIds) {
    return Flux.fromIterable(orderIds)
            .flatMap(orderLineRepository::findByOrderId, 8);
}
```

Đoạn code có fan-out concurrency 8, nhưng các thao tác có thể cùng sử dụng một connection gắn với transaction. Nhiều R2DBC driver không hỗ trợ thực thi đồng thời nhiều statement trên cùng một connection theo cách mà `flatMap` tạo ra. Kết quả có thể là lỗi driver, queue nội bộ hoặc hành vi không như kỳ vọng.

Trong transaction dùng chung connection, nếu các thao tác cần thực hiện tuần tự, dùng:

```java
@Transactional
public Flux<OrderLineEntity> loadAndProcess(List<Long> orderIds) {
    return Flux.fromIterable(orderIds)
            .concatMap(orderLineRepository::findByOrderId);
}
```

Nếu cần xử lý song song, cân nhắc một truy vấn nhóm duy nhất hoặc chia công việc thành các transaction độc lập với giới hạn rõ ràng. Không tự mở nhiều subscription bên trong một transaction để né giới hạn connection.

### 9.2. Giữ transaction ngắn

Connection thường được giữ trong suốt transaction. Tránh:

- Gọi HTTP service bên ngoài khi transaction database đang mở.
- Chờ người dùng hoặc chờ message trong transaction.
- Thực hiện xử lý CPU dài trước khi commit.
- Giữ transaction mở trong khi stream dữ liệu không giới hạn tới client.

Hãy thực hiện thao tác cần database trong transaction ngắn, sau đó xử lý phần công việc độc lập bên ngoài transaction nếu quy tắc nhất quán cho phép.

### 9.3. Một pipeline có nhiều transaction độc lập

Nếu batch được xử lý trong các transaction riêng, mỗi batch có thể mượn một connection khác nhau. Khi đó, concurrency của `flatMap` cần nằm trong ngân sách pool và bulkhead của tác vụ. Cần xác định rõ yêu cầu atomicity: nếu batch thứ ba lỗi sau khi hai batch trước commit, hệ thống có chấp nhận trạng thái xử lý một phần hay cần một transaction lớn hơn.

## 10. Backpressure, prefetch và các toán tử không thay thế nhau

Backpressure cho phép subscriber điều tiết lượng dữ liệu yêu cầu từ publisher. Tuy nhiên, không phải mọi toán tử điều tiết demand đều trực tiếp giới hạn số truy vấn database đang hoạt động.

### 10.1. `limitRate`

`limitRate` điều chỉnh cách subscriber yêu cầu dữ liệu từ upstream theo từng lô. Nó hữu ích để điều tiết demand, nhưng không thay thế `flatMap` concurrency khi mỗi phần tử nguồn tạo ra một query publisher.

Ví dụ:

```java
Flux.fromIterable(ids)
        .limitRate(32)
        .flatMap(repository::findById);
```

`limitRate(32)` không nên được hiểu là bảo đảm chỉ có tối đa 32 query đang chạy. Đặt giới hạn rõ tại `flatMap`:

```java
Flux.fromIterable(ids)
        .flatMap(repository::findById, 8);
```

### 10.2. `publishOn` và `subscribeOn`

`publishOn` và `subscribeOn` điều khiển scheduler nơi một phần của pipeline được thực thi hoặc subscription được khởi tạo. Chúng không phải cơ chế giới hạn số connection database. Chuyển một pipeline sang scheduler khác không làm pool có thêm connection và không làm query chậm biến mất.

R2DBC driver thực hiện I/O theo mô hình reactive; không cần đưa mọi repository call lên `boundedElastic` như cách thường dùng để cô lập blocking JDBC. Nếu có thư viện blocking, hãy cô lập riêng đoạn blocking đó và không giữ connection database trong lúc chờ.

### 10.3. `parallel()` không phải giới hạn pool

`parallel(n)` chia luồng thành các rail để xử lý song song, thường kết hợp với `runOn`. Nó phù hợp hơn với một số tác vụ CPU-bound. Dùng `parallel()` để gọi database không tự động quản lý connection budget; nếu mỗi rail gọi repository, vẫn cần giới hạn và tính toán concurrency rõ ràng.

## 11. Xử lý pool saturation và timeout

Khi pool hết connection khả dụng, thao tác mới chờ acquire. Nếu chờ quá thời gian cho phép, publisher phát lỗi acquire timeout. Đây là dấu hiệu cần quan sát và điều chỉnh tải, không nên tự động retry vô hạn.

### 11.1. Phân biệt các loại thời gian

Một request có thể trải qua:

1. Thời gian chờ được phép bắt đầu công việc (admission/bulkhead).
2. Thời gian chờ connection từ pool.
3. Thời gian database thực thi query.
4. Thời gian ứng dụng map kết quả và tạo response.

Nếu chỉ đặt query timeout mà không giới hạn acquire time, request vẫn có thể chờ pool quá lâu trước khi query bắt đầu. Cần cấu hình deadline tổng thể và các timeout thành phần phù hợp.

### 11.2. Không retry acquire timeout một cách vô hạn

Retry có thể làm tình trạng quá tải nặng hơn vì mỗi request thất bại lại tạo thêm yêu cầu acquire. Nếu có retry, cần giới hạn số lần, backoff có jitter, phân biệt lỗi tạm thời với lỗi cấu hình và bảo đảm thao tác có thể thực hiện lại an toàn.

### 11.3. Từ chối tải khi đã quá giới hạn

Bulkhead có thể từ chối công việc mới khi đạt mức concurrency cho phép thay vì để mọi request xếp hàng. Tầng API có thể ánh xạ quá tải thành response phù hợp như `503 Service Unavailable` hoặc một lỗi giới hạn tài nguyên theo hợp đồng. Chọn chính sách chờ hay từ chối dựa trên latency budget và loại công việc.

## 12. Theo dõi mức sử dụng connection pool

Để chọn concurrency có cơ sở, cần theo dõi các chỉ số sau:

| Chỉ số | Điều cần quan sát |
|---|---|
| Allocated/active connections | Số connection đang được mượn |
| Idle connections | Số connection sẵn sàng được tái sử dụng |
| Pending acquire | Số thao tác đang chờ connection |
| Acquire latency | Thời gian từ lúc yêu cầu đến lúc nhận connection |
| Acquire timeout count | Số lần không lấy được connection trong thời hạn |
| Connection creation time | Thời gian tạo connection mới |
| Query latency | Thời gian thực thi từng nhóm query |
| Transaction duration | Thời gian giữ connection trong transaction |
| Database CPU/lock/I/O | Khả năng xử lý và điểm nghẽn ở database |

Các metric cụ thể và tên metric phụ thuộc phiên bản R2DBC Pool, Spring Boot và Micrometer. Cấu hình quan sát phải được xác nhận trong môi trường chạy thực tế.

### 12.1. Dấu hiệu cần giảm concurrency

- Pending acquire tăng liên tục.
- Acquire latency tăng dù query latency không tăng tương ứng.
- Acquire timeout xuất hiện trong giờ cao điểm.
- Active connection luôn sát `max-size`.
- Database CPU hoặc lock wait tăng khi tăng số truy vấn đồng thời.
- Throughput không tăng thêm dù concurrency cao hơn, trong khi latency tăng.

### 12.2. Dấu hiệu có thể tăng concurrency

- Pool còn nhiều connection idle.
- Pending acquire gần như không có.
- Database còn dư năng lực CPU/I/O.
- Query độc lập, thời gian giữ connection ngắn và latency ổn định.
- Thử nghiệm tải cho thấy tăng concurrency làm throughput tăng mà không gây tail latency đáng kể.

Không điều chỉnh pool chỉ dựa trên một chỉ số. Kết hợp metric ứng dụng, pool và database để hiểu nút thắt nằm ở đâu.

## 13. Ví dụ chọn concurrency theo pool budget

Giả sử một instance có pool `max-size = 30`. Ứng dụng còn các luồng khác như health check, request đọc đơn lẻ, worker nền và tác vụ quản trị. Nhóm xử lý batch không nên mặc định sử dụng toàn bộ 30 connection.

Một cách phân bổ minh họa:

| Nhóm công việc | Ngân sách concurrency minh họa |
|---|---:|
| Request thông thường | 12 |
| Batch đọc theo nhóm | 8 |
| Worker nền | 4 |
| Dự phòng/dao động tải | 6 |
| **Tổng** | **30** |

Đây không phải cấu hình tối ưu chung. Nó chỉ minh họa rằng các luồng khác nhau cùng chia sẻ pool và cần có ngân sách. Nếu 10 request batch cùng lúc, mỗi request dùng concurrency 8, nhóm batch có thể tạo nhu cầu 80 thao tác; giới hạn 8 trên từng request không bảo đảm tổng batch chỉ dùng 8 connection.

Nếu batch là workload nặng, nên có bulkhead giới hạn tổng số batch đang chạy trên instance, ví dụ tối đa 2 batch cùng lúc và mỗi batch tối đa 4 query đồng thời. Phần còn lại của pool dành cho traffic thông thường. Con số thực tế cần được điều chỉnh bằng load test và metrics.

## 14. Kiểm thử concurrency và pool

Unit test có thể xác nhận pipeline dùng toán tử và giới hạn mong muốn, nhưng không đủ để kết luận pool hoạt động đúng dưới tải. Nên có integration/load test trên database và driver gần với production.

### 14.1. Kiểm tra concurrency trong pipeline

Có thể dùng publisher giả lập với một phép đo số publisher con đang hoạt động để xác nhận `flatMap` không vượt quá concurrency cấu hình. Bài test này kiểm tra hành vi Reactor, không kiểm tra connection pool.

### 14.2. Kiểm tra pool saturation

Với pool có kích thước nhỏ trong môi trường test, chạy nhiều thao tác chậm có kiểm soát để xác nhận:

- Số connection active không vượt `max-size`.
- Thao tác vượt số connection chờ acquire.
- Acquire timeout phát sinh khi vượt thời hạn cấu hình.
- Connection được trả lại pool sau khi publisher hoàn tất hoặc lỗi.
- Cancel subscription không để connection bị giữ ngoài ý muốn.

Không tạo tải quá mức trên database dùng chung hoặc production chỉ để thử nghiệm. Dùng database test/container riêng với giới hạn rõ ràng.

### 14.3. Load test nhiều request đồng thời

Mô phỏng nhiều request cùng thực hiện một luồng có fan-out. Đo throughput, p50/p95/p99 latency, active/idle/pending connections, acquire timeout và database CPU/I/O. Thay đổi từng tham số một: per-request concurrency, bulkhead, pool max-size hoặc batch size.

### 14.4. Kiểm thử transaction

Nếu luồng có `@Transactional`, xác nhận các repository call sử dụng transaction context như mong muốn. Kiểm tra driver có hỗ trợ các thao tác đồng thời trên cùng connection hay không; nếu không, dùng `concatMap` hoặc một query nhóm. Kiểm tra rollback khi một bước phát lỗi.

## 15. Các lỗi thường gặp

### Dùng flatMap không giới hạn với danh sách lớn

Mỗi phần tử có thể tạo một truy vấn riêng, khiến nhiều publisher cùng chờ pool. Đặt concurrency rõ ràng hoặc chuyển sang query `IN`/batch.

### Nghĩ concurrency của flatMap là giới hạn toàn ứng dụng

Giới hạn chỉ áp dụng cho một subscription tại toán tử đó. Nhiều request có thể nhân tổng concurrency. Dùng bulkhead/admission control nếu cần giới hạn theo instance hoặc workload.

### Tăng max-size để xử lý mọi hàng đợi

Pool lớn hơn có thể làm database quá tải. Kiểm tra query latency, CPU, lock wait và connection budget trước khi tăng.

### Dùng limitRate thay cho flatMap concurrency

`limitRate` điều tiết demand upstream, không trực tiếp giới hạn số publisher con đang gọi database. Đặt concurrency ở `flatMap`.

### Dùng parallel() để tăng tốc truy vấn

Parallel rail không phải cơ chế quản lý pool. Dùng toán tử phù hợp với I/O và giới hạn số query đang hoạt động.

### Chạy nhiều query đồng thời trong cùng transaction

Các thao tác có thể dùng chung một connection gắn với transaction context. Driver có thể không hỗ trợ concurrent statement trên connection đó. Ưu tiên tuần tự hoặc kiểm tra rõ khả năng driver.

### Giữ transaction trong lúc gọi dịch vụ bên ngoài

Connection bị giữ lâu, làm giảm số connection khả dụng cho request khác. Giữ transaction ngắn và tách phần xử lý độc lập ra ngoài khi nghiệp vụ cho phép.

### Retry vô hạn khi acquire timeout

Retry không giới hạn tạo thêm tải và có thể làm pool saturation nặng hơn. Dùng deadline, giới hạn retry và backoff có kiểm soát.

### Chỉ quan sát số connection active

Active connection cao có thể bình thường nếu query nhanh và throughput tốt. Cần xem thêm pending acquire, acquire latency, query latency và database load.

## 16. Quy trình lựa chọn mức đồng thời

1. Xác định mỗi request tạo bao nhiêu truy vấn và query giữ connection trung bình bao lâu.
2. Tìm các fan-out trong pipeline, đặc biệt `flatMap` gọi Repository hoặc `DatabaseClient`.
3. Chọn `concatMap` nếu cần tuần tự; dùng `flatMap`/`flatMapSequential` với concurrency hữu hạn cho truy vấn độc lập.
4. Ưu tiên một query nhóm hoặc batch thay vì gọi database riêng cho từng ID.
5. Xác định pool max-size và ngân sách connection theo tổng số instance cùng các client khác.
6. Dành headroom cho request thông thường, worker nền, quản trị và dao động tải.
7. Dùng bulkhead nếu cần giới hạn tổng công việc của một workload trên mỗi instance.
8. Cấu hình acquire timeout và deadline theo latency budget.
9. Với reactive transaction, kiểm tra việc dùng chung connection và tránh concurrent statement nếu driver không hỗ trợ.
10. Theo dõi active/idle/pending connection, acquire latency, timeout, query latency và database resource.
11. Load test với nhiều request đồng thời, thay đổi một tham số mỗi lần.
12. Chọn concurrency tại điểm throughput còn tốt nhưng latency và pool pending vẫn nằm trong ngưỡng chấp nhận.

## 17. Checklist ghi nhớ

- [ ] Mọi `flatMap` tạo fan-out tới database có concurrency phù hợp.
- [ ] Dùng `concatMap` khi thao tác cần tuần tự hoặc dùng chung transaction connection.
- [ ] Dùng `flatMapSequential` khi cần chạy đồng thời nhưng giữ thứ tự kết quả.
- [ ] Không coi concurrency trong một subscription là giới hạn toàn ứng dụng.
- [ ] Dùng bulkhead/admission control cho workload cần giới hạn tổng trên mỗi instance.
- [ ] Pool `max-size` nằm trong ngân sách connection của toàn hệ thống.
- [ ] Ngân sách tính cả số instance tối đa và client khác dùng database.
- [ ] Acquire timeout phù hợp với deadline của request.
- [ ] Không tăng pool chỉ để che query chậm hoặc fan-out quá lớn.
- [ ] Ưu tiên query theo nhóm/batch khi phù hợp.
- [ ] Không dùng `limitRate`, `publishOn`, `subscribeOn` hoặc `parallel()` thay cho giới hạn query concurrency.
- [ ] Transaction reactive được giữ ngắn và không có concurrent statement ngoài khả năng driver.
- [ ] Có metric active, idle, pending, acquire latency và timeout.
- [ ] Đã load test với nhiều request và theo dõi database resource.

Concurrency trong Spring Data R2DBC cần được điều chỉnh từ trong pipeline ra tới connection pool và database. Giới hạn `flatMap` giúp một luồng không tạo quá nhiều thao tác con; bulkhead kiểm soát tổng tải của workload trên một instance; `max-size` bảo vệ số connection; còn metrics và load test cho biết hệ thống đang ở điểm cân bằng nào. Khi các giới hạn được tính cùng nhau, ứng dụng có thể khai thác I/O reactive mà không biến connection pool thành một hàng đợi quá tải.
