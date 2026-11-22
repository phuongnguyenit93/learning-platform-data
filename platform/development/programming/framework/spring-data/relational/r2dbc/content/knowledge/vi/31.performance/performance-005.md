# Tối ưu mức đồng thời cùng kích thước pool

## 1. Hai giới hạn cần phối hợp

Trong ứng dụng Spring Data R2DBC, mức đồng thời của pipeline reactive và kích thước connection pool có quan hệ chặt chẽ nhưng là hai cấu hình khác nhau.

- **Mức đồng thời của pipeline** quyết định có bao nhiêu publisher hoặc thao tác được phép chạy cùng lúc trong một luồng xử lý. Reactor điều khiển điều này qua các operator như flatMap, flatMapSequential và concatMap.
- **Kích thước connection pool** quyết định có tối đa bao nhiêu R2DBC connection được mượn đồng thời từ pool của một instance ứng dụng.

Ví dụ, một luồng xử lý dùng flatMap với concurrency bằng 50 có thể cố gắng thực hiện đến 50 thao tác repository đồng thời. Nếu pool chỉ có 10 connection, một phần thao tác phải chờ connection được trả về. Ngược lại, pool có 50 connection không có nghĩa mọi pipeline đều cần mở 50 thao tác song song.

Tối ưu hiệu năng cần trả lời đồng thời ba câu hỏi:

1. Database có thể xử lý bao nhiêu thao tác cùng lúc mà vẫn giữ latency ổn định?
2. Ứng dụng có thể tạo ra bao nhiêu thao tác database đồng thời từ request, batch và background job?
3. Pool cần bao nhiêu connection để phục vụ mức tải đó mà không chiếm hết ngân sách connection của database?

R2DBC giúp I/O database không cần chiếm một thread chờ blocking cho mỗi thao tác. Điều đó không làm database có khả năng xử lý vô hạn truy vấn đồng thời. Database vẫn có giới hạn CPU, I/O, lock, memory, connection và throughput.

## 2. Luồng từ Reactor đến connection pool

Khi một repository publisher được subscribe, thao tác cần connection sẽ lấy connection từ ConnectionFactory. Nếu ứng dụng dùng connection pool, yêu cầu được gửi đến pool:

~~~text
HTTP requests / background jobs
              |
              v
       Reactive pipelines
              |
       flatMap concurrency
              |
              v
       Repository / Template
              |
              v
       R2DBC ConnectionFactory
              |
              v
        Connection pool
         /           \
        v             v
   Connection      Acquire queue
   available       wait for release
        |
        v
    R2DBC driver
        |
        v
      Database
~~~

Một số tình huống:

- Nếu còn connection rảnh, thao tác có thể mượn connection và tiếp tục.
- Nếu pool đã đạt max-size, yêu cầu mới phải chờ connection được trả về hoặc hết thời gian chờ.
- Nếu thao tác giữ connection lâu, những thao tác khác phải chờ lâu hơn.
- Nếu pool được đặt quá lớn, database có thể chịu quá nhiều session đồng thời và latency tăng.
- Nếu concurrency trong pipeline quá cao, queue trong pool có thể tăng dù số connection thực tế không đổi.

Vì vậy, tăng flatMap concurrency và tăng max-size cùng lúc không phải lúc nào cũng cải thiện throughput. Cần đo xem nút thắt nằm ở ứng dụng, pool hay database.

## 3. Reactor concurrency điều khiển số publisher đang hoạt động

Với Flux, operator flatMap có tham số concurrency để giới hạn số inner publisher được subscribe đồng thời.

Ví dụ:

~~~java
Flux<Order> savedOrders =
        Flux.fromIterable(commands)
                .flatMap(
                        command -> orderRepository.save(toOrder(command)),
                        8
                );
~~~

Trong ví dụ này, Reactor cho phép tối đa 8 inner publisher được subscribe cùng lúc từ Flux nguồn. Nếu mỗi inner publisher thực hiện một thao tác ghi R2DBC, tối đa 8 thao tác đó có thể đang được xử lý đồng thời trong subscription này.

Giá trị concurrency không phải số thread. R2DBC thực hiện I/O bất đồng bộ; nhiều thao tác có thể đang chờ database mà không cần một thread riêng bị block cho mỗi thao tác.

### 3.1. flatMap, flatMapSequential và concatMap

| Operator | Cách xử lý | Khi phù hợp |
|---|---|---|
| flatMap(mapper, concurrency) | Subscribe nhiều inner publisher đồng thời; kết quả có thể phát theo thứ tự hoàn tất | Các thao tác độc lập, không yêu cầu thứ tự đầu ra |
| flatMapSequential(mapper, concurrency) | Cho phép chạy đồng thời nhưng phát kết quả theo thứ tự nguồn | Cần giữ thứ tự đầu ra trong khi vẫn xử lý song song |
| concatMap(mapper) | Chờ inner publisher hiện tại hoàn tất rồi mới xử lý phần tử tiếp theo | Cần tuần tự hóa thao tác hoặc giữ thứ tự side effect |

Ví dụ tuần tự:

~~~java
Flux<Void> updates =
        Flux.fromIterable(commands)
                .concatMap(command ->
                        customerRepository.save(toCustomer(command))
                                .then()
                );
~~~

Ví dụ song song có giới hạn:

~~~java
Flux<Customer> updates =
        Flux.fromIterable(commands)
                .flatMap(
                        command -> customerRepository.save(toCustomer(command)),
                        6
                );
~~~

Không dùng concurrency cao nếu các thao tác phụ thuộc nhau. Nếu phải lấy ID của bản ghi trước để tạo bản ghi sau, hãy nối bằng flatMap hoặc then trong cùng một chuỗi thay vì chạy hai thao tác độc lập song song.

### 3.2. Concurrency và prefetch là hai tham số khác nhau

Một số operator nhận cả concurrency và prefetch:

~~~java
Flux<Customer> saved =
        commands.flatMap(
                command -> customerRepository.save(toCustomer(command)),
                8,
                1
        );
~~~

- concurrency giới hạn số inner publisher được subscribe đồng thời.
- prefetch điều khiển lượng phần tử được yêu cầu trước từ mỗi inner publisher trong những operator hỗ trợ tham số này.

Prefetch không phải kích thước connection pool và cũng không phải số thread. Tăng prefetch có thể tăng lượng dữ liệu đang được giữ trong pipeline, nhưng không tự tăng năng lực database.

Với Mono, flatMap thường dùng để nối một publisher phụ thuộc; không có tham số concurrency như phiên bản Flux. Muốn giới hạn nhiều thao tác độc lập, thường áp dụng operator trên Flux nguồn.

## 4. flatMap concurrency thường là giới hạn theo từng subscription

Đây là điểm dễ dẫn đến cấu hình quá tải. Concurrency truyền vào flatMap áp dụng cho một subscription của pipeline đó, không tự động giới hạn toàn bộ ứng dụng.

Giả sử mỗi request gọi:

~~~java
return Flux.fromIterable(request.items())
        .flatMap(item -> repository.save(toEntity(item)), 10)
        .then();
~~~

Một request có thể có tối đa 10 inner publisher đang hoạt động. Nếu có 20 request đồng thời cùng chạy pipeline, số thao tác database tiềm năng có thể lên đến khoảng 200, tùy thời điểm và thời gian sống của từng publisher.

Công thức ước lượng đơn giản:

~~~text
Tổng thao tác inner đang hoạt động
    <= số subscription đang chạy
       × concurrency mỗi subscription
~~~

Đây là giới hạn tiềm năng, không phải số thao tác chắc chắn luôn đồng thời. Publisher nguồn có thể phát chậm, request có thể kết thúc sớm hoặc một thao tác có thể không cần connection.

Nếu chỉ nhìn tham số flatMap bằng 10 và nghĩ ứng dụng chỉ chạy tối đa 10 query cùng lúc, bạn sẽ đánh giá thấp tải khi nhiều request hoặc background job cùng hoạt động.

### 4.1. Pool là giới hạn tài nguyên cuối cùng, không phải chính sách admission control hoàn chỉnh

Pool max-size giới hạn số connection được mượn cùng lúc từ pool. Khi hết connection, yêu cầu mới thường chờ trong hàng đợi acquire. Điều này ngăn pool tạo connection vô hạn, nhưng queue quá dài vẫn làm request tăng latency và có thể timeout.

Cần đặt giới hạn ở tầng tạo tải khi phù hợp:

- Giới hạn số item xử lý đồng thời trong một batch.
- Giới hạn concurrency của background worker.
- Giới hạn request hoặc workload theo bulkhead/rate limiter.
- Đặt deadline và timeout phù hợp cho thao tác.
- Trả backpressure hoặc từ chối tải vượt năng lực theo chính sách của ứng dụng.

Không nên để hàng nghìn publisher chờ pool trong thời gian dài rồi xem đó là khả năng scale. Một queue lớn chỉ chuyển tình trạng quá tải thành latency và memory pressure.

## 5. Connection pool trong R2DBC

R2DBC SPI định nghĩa ConnectionFactory để tạo connection. Connection pool là lớp quản lý các connection có thể tái sử dụng nhằm giảm chi phí tạo kết nối liên tục và giới hạn số session ứng dụng mở đến database.

Trong hệ sinh thái R2DBC, r2dbc-pool là implementation pool phổ biến. Spring Boot có thể cấu hình pool qua các property khi dependency pool tương ứng có trên classpath.

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-pool'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Dependency driver cần thay theo database ứng dụng đang sử dụng. Phiên bản nên được quản lý tương thích với Spring Boot và R2DBC SPI.

### 5.1. Cấu hình pool bằng application.yml

Ví dụ cấu hình ban đầu:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-acquire-time: 2s
      max-idle-time: 10m
      max-life-time: 30m
~~~

Ý nghĩa các thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| enabled | Bật cấu hình connection pool |
| initial-size | Số connection khởi tạo ban đầu theo khả năng cấu hình của pool |
| max-size | Số connection tối đa trong pool |
| max-acquire-time | Thời gian tối đa chờ mượn connection |
| max-idle-time | Thời gian connection có thể nhàn rỗi trước khi bị loại theo chính sách pool |
| max-life-time | Tuổi thọ tối đa của connection theo chính sách pool |

Tên property và khả năng bind phụ thuộc phiên bản Spring Boot/R2DBC pool. Hãy đối chiếu với dependency management và tài liệu của phiên bản dự án trước khi triển khai. Không copy nguyên cấu hình từ một version khác mà chưa xác nhận property có được hỗ trợ.

Các property khác của r2dbc-pool có thể gồm giới hạn thời gian tạo connection, validation depth, validation query và chu kỳ eviction. Chỉ bật thêm khi có mục tiêu vận hành cụ thể.

### 5.2. initial-size không phải max-size

initial-size là số connection pool cố gắng tạo ban đầu theo cấu hình. max-size là giới hạn tối đa pool được phép duy trì hoặc cấp phát theo semantics của pool.

Không đặt initial-size bằng max-size chỉ vì muốn mọi connection sẵn sàng ngay. Khởi tạo quá nhiều connection có thể tạo burst kết nối khi nhiều replica cùng khởi động. Với workload nhỏ hoặc môi trường scale-to-zero, initial-size thấp thường giảm chi phí startup.

### 5.3. Pool không phải cache kết quả query

Connection pool tái sử dụng connection, không lưu kết quả SELECT. Mỗi subscription cold vào repository vẫn có thể thực thi SQL mới. Pool giúp quản lý connection lifecycle và chi phí kết nối, không làm query lặp biến thành một query duy nhất.

## 6. Tính ngân sách connection trên toàn hệ thống

Không thể chọn max-size chỉ bằng cách nhìn một instance ứng dụng. Database có giới hạn connection tổng thể và nhiều thành phần có thể cùng sử dụng giới hạn đó:

- Các replica của ứng dụng R2DBC.
- Worker/background service.
- Công cụ migration.
- Monitoring và health check.
- Công cụ quản trị.
- Ứng dụng hoặc service khác dùng chung database.

Một cách lập ngân sách:

~~~text
Ngân sách cho ứng dụng R2DBC
    = max_connections của database
      - connection dành cho quản trị
      - connection của service khác
      - connection cho migration/monitoring
      - safety margin
~~~

Sau đó phân bổ cho số replica tối đa:

~~~text
max-size mỗi instance
    <= ngân sách dành cho ứng dụng
       / số replica tối đa
~~~

Ví dụ minh họa:

| Thành phần | Connection |
|---|---:|
| Database max_connections | 200 |
| Dành cho quản trị/monitoring | 15 |
| Service khác | 55 |
| Migration và công việc vận hành | 10 |
| Safety margin | 20 |
| Còn lại cho ứng dụng R2DBC | 100 |

Nếu deployment có thể scale tối đa 5 replica, ngân sách lý thuyết trung bình là 20 connection mỗi instance. Khi đó max-size 20 có thể là một điểm bắt đầu để đo tải, không phải kết luận rằng database chắc chắn xử lý tốt 100 connection hoạt động.

Phải tính theo số replica tối đa, bao gồm rolling deployment có thể tạm thời chạy cả phiên bản cũ và mới. Nếu autoscaling tăng replica từ 5 lên 10 mà pool max-size giữ nguyên, tổng connection potential cũng tăng gấp đôi.

### 6.1. Không dùng toàn bộ max_connections cho pool ứng dụng

Database cần connection cho admin, monitoring, backup, migration và các service khác. Nếu ứng dụng chiếm hết connection, thao tác vận hành hoặc service khác có thể không kết nối được.

Giữ một phần ngân sách dự phòng. Tỷ lệ dự phòng phụ thuộc hệ thống và tải; không có một con số đúng cho mọi database.

### 6.2. Nhiều pool trong cùng một ứng dụng

Nếu ứng dụng tạo nhiều ConnectionFactory, mỗi pool có max-size riêng. Tổng connection tiềm năng là tổng max-size của tất cả pool trên tất cả replica.

Ví dụ một instance có pool customer max-size 15 và pool order max-size 20. Nếu chạy 4 replica, tổng tiềm năng là:

~~~text
4 × (15 + 20) = 140 connections
~~~

Không chỉ nhìn pool chính trong application.yml. Hãy lập danh sách tất cả ConnectionFactory và pool được tạo trong cấu hình ứng dụng.

## 7. Dùng Little’s Law để ước lượng số thao tác đang chờ/đang chạy

Little’s Law mô tả quan hệ giữa throughput, thời gian ở trong hệ thống và số lượng công việc trung bình đang có mặt:

~~~text
L = λ × W
~~~

Trong đó:

- L: số thao tác trung bình đang ở trong hệ thống.
- λ: throughput, số thao tác mỗi giây.
- W: thời gian trung bình một thao tác ở trong hệ thống, tính bằng giây.

Ví dụ ứng dụng thực hiện 300 thao tác database mỗi giây và thời gian giữ connection trung bình là 40 ms:

~~~text
L = 300 × 0.040 = 12
~~~

Trung bình có khoảng 12 thao tác đang giữ connection. Đây là phép ước lượng trung bình dựa trên workload và thời gian đo, không phải khuyến nghị đặt pool bằng 12 trong mọi tình huống.

Nếu connection được giữ trong transaction 250 ms thay vì 40 ms:

~~~text
L = 300 × 0.250 = 75
~~~

Cùng throughput nhưng transaction dài hơn làm tăng số connection trung bình cần thiết. Đây là lý do giảm thời gian giữ connection thường hiệu quả hơn việc chỉ tăng pool.

### 7.1. Phải dùng thời gian giữ connection phù hợp

Thời gian query nhìn thấy trong log không phải lúc nào cũng bằng thời gian connection bị giữ. Connection có thể được giữ trong:

- Toàn bộ reactive transaction.
- Quá trình đọc một Flux nhiều hàng.
- Callback hoặc mapping nằm trong lifecycle truy cập dữ liệu.
- Các bước ứng dụng xen giữa hai query trong cùng transaction.
- Thời gian chờ một publisher downstream hoàn tất trước khi transaction đóng.

Hãy đo connection acquire/release và transaction duration nếu có thể. Nếu dùng thời gian SQL thuần để tính L nhưng transaction giữ connection lâu hơn, bạn sẽ đánh giá thấp nhu cầu connection.

### 7.2. Little’s Law không dự đoán burst hoặc p99

Công thức dùng giá trị trung bình trong một hệ thống ổn định. Nó không tự xác định pool cần bao nhiêu connection khi có burst, tail latency, lock contention hoặc traffic thay đổi đột ngột.

Dùng nó để có ước lượng ban đầu, sau đó kiểm chứng bằng load test và metrics. Không lấy kết quả trung bình làm giới hạn cứng cho production.

## 8. Database không nhất thiết nhanh hơn khi có nhiều connection hơn

Mỗi connection đồng thời có thể tiêu thụ tài nguyên database:

- Backend/session memory.
- CPU để parse, plan và thực thi query.
- Buffer/cache pressure.
- I/O và lock.
- Scheduler và context switching.
- Bộ nhớ cho sort, hash join hoặc transaction.
- Tài nguyên quản lý transaction và snapshot.

Khi số connection tăng vượt khả năng xử lý hữu ích, database có thể chuyển sang contention. Kết quả là throughput không tăng hoặc giảm, trong khi p95/p99 latency tăng.

Một pool lớn chỉ tăng số connection có thể được mượn. Nó không tự tăng CPU, IOPS, memory hoặc năng lực lock của database.

Có thể quan sát ba vùng:

~~~text
Throughput
   ^
   |                 _________
   |              __/
   |           __/
   |        __/
   |     __/
   |  __/
   +--------------------------------> concurrency
       tăng hữu ích    bão hòa / contention
~~~

Ở vùng đầu, tăng concurrency có thể giúp tận dụng database tốt hơn. Đến một điểm, throughput tiến gần giới hạn. Sau điểm đó, thêm concurrency chủ yếu làm queue và latency tăng.

Điểm bão hòa cần được đo trên workload thật. Nó phụ thuộc query, index, dữ liệu, hardware, database version và các workload khác cùng sử dụng database.

## 9. Chọn concurrency cho từng loại workload

Không phải mọi truy vấn đều có cùng chi phí. Một SELECT theo primary key có thể nhẹ hơn một truy vấn join, sort và aggregate trên bảng lớn. Một batch update có thể tạo lock lâu hơn một thao tác đọc ngắn.

Có thể phân loại:

| Workload | Hướng cấu hình |
|---|---|
| Lookup theo primary key | Có thể cho concurrency cao hơn sau khi đo |
| Query join/aggregate nặng | Concurrency thấp hơn để bảo vệ CPU và memory database |
| Ghi hàng loạt | Batch có giới hạn, tránh nhiều transaction ghi cùng vùng dữ liệu |
| Background polling | Giới hạn concurrency và tần suất |
| Streaming Flux dài | Giới hạn số stream, tránh giữ connection quá lâu |
| Transaction nhiều bước | Giữ số transaction đồng thời phù hợp với thời gian giữ connection |
| Job import/export | Chia batch, điều tiết tốc độ và có checkpoint |

Không đặt một giá trị flatMap concurrency duy nhất cho toàn ứng dụng rồi giả định mọi query đều có chi phí giống nhau. Hãy giới hạn theo workload và theo mức ưu tiên nghiệp vụ.

## 10. Điều chỉnh concurrency trong batch

Một batch xử lý nhiều bản ghi là nơi thường cần giới hạn concurrency rõ ràng.

Ví dụ:

~~~java
public Flux<Customer> importCustomers(Flux<CustomerInput> inputs) {
    return inputs.flatMap(
            input -> customerRepository.save(toCustomer(input)),
            8
    );
}
~~~

Tối đa 8 thao tác save từ subscription này được xử lý đồng thời. Giá trị 8 chỉ là ví dụ; cần đo với database, schema và kích thước batch thực tế.

Nếu cần xử lý tuần tự:

~~~java
public Flux<Customer> importCustomers(Flux<CustomerInput> inputs) {
    return inputs.concatMap(input ->
            customerRepository.save(toCustomer(input))
    );
}
~~~

Nếu cần gom batch trước khi ghi:

~~~java
public Flux<Customer> importCustomers(Flux<CustomerInput> inputs) {
    return inputs.buffer(100)
            .concatMap(batch ->
                    customerRepository.saveAll(
                            batch.stream()
                                    .map(this::toCustomer)
                                    .toList()
                    )
            );
}
~~~

buffer(100) gom tối đa 100 input trong một nhóm trước khi gọi saveAll. Điều này giúp kiểm soát lượng dữ liệu được đưa vào mỗi bước xử lý.

Lưu ý: saveAll không nhất thiết đồng nghĩa một câu SQL bulk insert duy nhất. Repository implementation và driver có thể thực hiện nhiều statement. Nếu cần tối ưu batch SQL thực sự, hãy kiểm tra SQL phát ra hoặc dùng API phù hợp với database.

### 10.1. Chọn batch size và concurrency riêng

Batch size quyết định số phần tử được gom vào một nhóm. Concurrency quyết định có bao nhiêu inner publisher/batch được xử lý đồng thời.

Nếu batch size là 100 và concurrency là 5, pipeline có thể giữ nhiều batch cùng lúc. Bộ nhớ và số thao tác database tiềm năng có thể tăng đáng kể.

Đừng tăng cả hai tham số mà không đo. Bắt đầu bằng batch vừa phải, concurrency thấp, sau đó tăng từng yếu tố và quan sát throughput, memory, pool wait và database latency.

### 10.2. Backpressure không tự thay thế giới hạn toàn hệ thống

Reactor hỗ trợ demand/backpressure để subscriber yêu cầu dữ liệu theo khả năng tiêu thụ. Tuy nhiên, backpressure không tự động tạo một giới hạn global cho mọi request trong ứng dụng.

Một Flux đầu vào có thể được điều tiết trong subscription của nó, nhưng nhiều subscription độc lập vẫn có thể cùng chạy. Cần thêm giới hạn admission hoặc bulkhead ở tầng ứng dụng khi workload có thể tăng vượt năng lực database.

## 11. Transaction làm thay đổi cách sử dụng connection

Với reactive transaction, Spring thường bind connection vào Reactor Context cho transaction hiện tại. Các thao tác R2DBC tham gia transaction đó dùng connection được quản lý cho transaction.

Điều này có hai hệ quả:

1. Một transaction thường giữ connection từ lúc bắt đầu đến khi hoàn tất commit/rollback.
2. Nhiều thao tác song song trong cùng transaction có thể cùng truy cập một connection.

Không phải mọi R2DBC driver/connection đều hỗ trợ nhiều statement đồng thời trên cùng một connection. Vì vậy, tránh mặc định rằng flatMap concurrency cao trong một transaction sẽ tạo nhiều connection riêng nhưng vẫn nằm trong cùng transaction.

Ví dụ chuỗi thao tác tuần tự trong một transaction:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(saved ->
                    orderLineRepository.saveAll(toLines(saved.id(), command))
                            .thenReturn(saved)
            )
            .flatMap(saved ->
                    inventoryRepository.reserve(command.items())
                            .thenReturn(saved)
            );
}
~~~

Các bước phụ thuộc nhau được nối tuần tự bằng flatMap/then. Chúng có thể tham gia cùng transaction và connection được bind.

### 11.1. Tránh gọi dịch vụ bên ngoài trong transaction dài

Không nên giữ transaction mở trong khi chờ HTTP, email hoặc người dùng phản hồi. Connection có thể bị giữ dù database không thực hiện query, làm pool nhanh cạn khi tải tăng.

Ví dụ không nên:

~~~java
@Transactional
public Mono<Order> placeOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentClient.authorize(order)
                            .thenReturn(order)
            )
            .flatMap(order ->
                    orderRepository.markPaid(order.id())
                            .thenReturn(order)
            );
}
~~~

Nếu paymentClient mất vài giây, transaction có thể giữ connection và lock trong toàn bộ thời gian chờ. Thiết kế phù hợp hơn có thể dùng state machine, saga hoặc outbox tùy yêu cầu nghiệp vụ, với các transaction database ngắn.

### 11.2. Không dùng concurrency để chạy nhiều query trên cùng transaction connection một cách tùy tiện

Nếu hai query phụ thuộc cùng transaction và driver không hỗ trợ concurrent statement trên connection, hãy nối tuần tự:

~~~java
return customerRepository.findById(customerId)
        .flatMap(customer ->
                addressRepository.findByCustomerId(customer.id())
                        .collectList()
                        .map(addresses ->
                                new CustomerProfile(customer, addresses)
                        )
        );
~~~

Chỉ chạy song song các query trong cùng transaction khi đã xác nhận driver, connection và Spring transaction integration hỗ trợ mô hình đó. Nếu các query cần connection độc lập, chúng không thể tự động trở thành một transaction atomic chỉ bằng cách chạy trong flatMap.

## 12. Streaming và thời gian giữ connection

Một Flux từ database có thể giữ connection trong lúc driver đọc result set và subscriber tiêu thụ dữ liệu. Nếu downstream xử lý chậm, connection có thể bị giữ lâu hơn dự kiến.

Ví dụ:

~~~java
return customerRepository.findAll()
        .map(this::toExportRow)
        .flatMap(exportService::writeRow, 4);
~~~

Nếu exportService ghi file hoặc gọi dịch vụ khác chậm, pipeline có thể kéo dài thời gian tiêu thụ Flux. Cần xem xét liệu connection có còn bị giữ trong toàn bộ quá trình xử lý hay không theo publisher và driver.

Một số cách giảm áp lực:

- Dùng pagination/keyset pagination cho dữ liệu lớn.
- Chia công việc đọc và xử lý theo batch.
- Tránh tạo một Flux rất dài cho export nếu cần giữ connection lâu.
- Giới hạn số export đang chạy đồng thời.
- Không gọi dịch vụ blocking trong map/flatMap.
- Đảm bảo subscriber có thể cancel khi không còn cần dữ liệu.
- Đo thời gian stream và thời gian giữ connection.

Không dùng collectList() cho tập dữ liệu không giới hạn chỉ để đóng connection sớm. collectList() giữ toàn bộ dữ liệu trong bộ nhớ và có thể tạo memory pressure. Hãy chọn pagination hoặc batch phù hợp với kích thước dữ liệu.

## 13. Cấu hình timeout cho pool và query

Các timeout ở những tầng khác nhau giải quyết các vấn đề khác nhau:

| Timeout | Giới hạn điều gì |
|---|---|
| Connection acquire timeout | Thời gian chờ lấy connection từ pool |
| Connection creation timeout | Thời gian tạo connection mới |
| Query/statement timeout | Thời gian thực thi câu SQL theo hỗ trợ của driver/database |
| Transaction timeout | Thời gian transaction theo transaction manager |
| HTTP/request deadline | Tổng thời gian request được phép xử lý |
| Retry backoff | Khoảng chờ trước khi thử lại |

Acquire timeout ngắn giúp phát hiện pool saturation sớm, nhưng nếu đặt quá ngắn có thể từ chối request trong burst ngắn dù database vẫn còn khả năng xử lý.

Acquire timeout quá dài làm request chờ lâu và giữ tài nguyên upstream. Hãy đặt nó nhỏ hơn hoặc phù hợp với request deadline và ngân sách latency của nghiệp vụ.

Không nhầm timeout lấy connection với timeout query. Một request có thể lấy connection nhanh nhưng query bị lock lâu. Ngược lại, query có thể nhanh nhưng request chờ pool quá lâu trước khi bắt đầu.

## 14. Đặt pool max-size quá thấp hoặc quá cao

### 14.1. Pool quá thấp

Dấu hiệu:

- Nhiều request chờ connection dù database còn tài nguyên.
- Pool pending acquire tăng.
- Acquire latency tăng.
- Acquire timeout xuất hiện.
- Database active session thấp so với năng lực có thể dùng.
- Throughput bị giới hạn bởi pool.

Cách xử lý:

- Kiểm tra thời gian giữ connection.
- Xác định có transaction dài hoặc stream dài không.
- Kiểm tra query đang chậm hay pool chỉ thiếu connection.
- Tăng max-size từng bước nếu database còn headroom.
- Điều chỉnh concurrency của workload để tránh queue quá lớn.

Không tăng pool nếu nguyên nhân thực sự là query chậm hoặc transaction giữ connection quá lâu.

### 14.2. Pool quá cao

Dấu hiệu:

- Database có quá nhiều session.
- CPU hoặc I/O database tăng mạnh khi concurrency tăng.
- p95/p99 latency xấu đi.
- Lock wait, deadlock hoặc context switching tăng.
- Throughput không tăng dù số connection tăng.
- Các service khác bị thiếu connection.

Cách xử lý:

- Giảm max-size hoặc concurrency workload.
- Tối ưu query và index.
- Giảm thời gian transaction.
- Tách batch lớn thành nhóm nhỏ.
- Điều tiết background job.
- Kiểm tra số replica và tổng connection toàn hệ thống.

Pool lớn không phải biện pháp chữa mọi vấn đề throughput. Đôi khi giảm concurrency giúp database hoàn thành mỗi query nhanh hơn và tổng throughput tăng.

## 15. Đo các chỉ số trước khi thay đổi

Để điều chỉnh có căn cứ, cần theo dõi cả ứng dụng và database.

### 15.1. Chỉ số phía connection pool

Tùy phiên bản pool và hệ thống metrics, cần quan sát:

- Số connection allocated/created.
- Số connection acquired/in-use.
- Số connection idle.
- Số yêu cầu đang pending acquire.
- Thời gian acquire trung bình và percentile.
- Số acquire timeout.
- Số connection bị dispose/evict.
- Thời gian tạo connection.

Nếu pool đã dùng gần max-size liên tục và pending acquire tăng, ứng dụng có thể đang bị giới hạn bởi pool. Nhưng nếu database cũng đã bão hòa, tăng pool chỉ làm tình hình xấu hơn.

### 15.2. Chỉ số phía database

Quan sát:

- Active sessions và số connection.
- Query latency p50/p95/p99.
- Throughput query/transaction.
- CPU và memory.
- Disk I/O và buffer/cache hit.
- Lock wait và deadlock.
- Slow query.
- Replication lag nếu có replica.
- Transaction duration và idle-in-transaction session.

Các chỉ số cần được đối chiếu theo cùng khoảng thời gian với metrics pool. Không kết luận chỉ từ một biểu đồ connection count.

### 15.3. Chỉ số phía ứng dụng

Theo dõi:

- Request concurrency và request rate.
- Số thao tác database trung bình mỗi request.
- Background job concurrency.
- Thời gian xử lý mỗi publisher.
- Tỷ lệ lỗi và timeout.
- Queue/backlog trong pipeline.
- Memory và GC.
- Số replica đang chạy và autoscaling event.

Một thay đổi max-size có thể ảnh hưởng khác nhau giữa một request có một SELECT và một request fan-out thành 20 query.

## 16. Quy trình tuning có kiểm soát

Một quy trình thực tế:

1. Đo baseline ở workload đại diện.
2. Ghi lại request rate, query throughput, connection usage và p95/p99 latency.
3. Xác định pool có đang là bottleneck hay database đã bão hòa.
4. Kiểm tra thời gian giữ connection, transaction và stream.
5. Chọn một giới hạn concurrency phù hợp cho workload.
6. Chọn max-size theo ngân sách connection toàn hệ thống.
7. Tăng hoặc giảm một tham số mỗi lần.
8. Chạy lại cùng workload và cùng dữ liệu.
9. So sánh throughput, latency, pending acquire, DB CPU và lock wait.
10. Kiểm tra khi số replica đạt mức tối đa và trong rolling deployment.
11. Chọn điểm cân bằng, không chỉ chọn throughput cao nhất trong một thời điểm.
12. Theo dõi sau deploy và có cách rollback cấu hình.

Không tuning bằng một test chạy vài request. Cần có tải đủ lâu để pool ổn định, database cập nhật statistics nếu cần và các pattern lock/cache xuất hiện.

## 17. Ví dụ đọc kết quả load test

Giả sử đo ba cấu hình trên cùng một database và workload:

| Pool max-size | Throughput | p95 latency | Pending acquire | DB CPU |
|---:|---:|---:|---:|---:|
| 10 | 700 ops/s | 180 ms | Cao | 45% |
| 20 | 1,050 ops/s | 150 ms | Thấp | 65% |
| 40 | 1,080 ops/s | 310 ms | Thấp | 95% |

Đây chỉ là số liệu giả định để minh họa cách đọc kết quả.

- Tăng từ 10 lên 20 giúp throughput tăng và pending acquire giảm.
- Tăng từ 20 lên 40 hầu như không tăng throughput.
- p95 latency và DB CPU tăng mạnh ở pool 40, cho thấy database có thể đã bão hòa.

Trong tình huống minh họa, pool 20 có vẻ cân bằng hơn pool 40. Nhưng cần kiểm tra workload, concurrency, số replica, các service khác và tail latency trước khi chọn cấu hình production.

Đừng chọn pool 40 chỉ vì nó cho phép nhiều connection hơn. Mục tiêu là throughput ổn định với latency và tài nguyên có thể chấp nhận.

## 18. Giới hạn global cho background worker

Một background worker có thể đọc hàng đợi công việc rồi ghi database. Nếu mỗi worker instance dùng flatMap concurrency 20 và deployment có 10 replica, số thao tác tiềm năng có thể lên đến 200.

Hãy tính concurrency trên toàn bộ worker fleet:

~~~text
Tổng concurrency tiềm năng
    = số worker instance
      × số subscription xử lý
      × concurrency mỗi subscription
~~~

Có thể điều chỉnh:

- Số worker replica.
- Số consumer/subscription trên mỗi instance.
- flatMap concurrency.
- Batch size.
- Tốc độ lấy message từ broker.
- Retry và backoff.
- Global rate limit hoặc partitioning.

Không chỉ giới hạn pool rồi để hàng đợi message tạo backlog vô hạn. Cần có chính sách backpressure/admission ở worker và quan sát lag.

Nếu message được xử lý lại sau timeout, hãy đảm bảo write idempotent. Tăng concurrency có thể làm duplicate hoặc conflict dễ xuất hiện hơn khi nhiều message cùng cập nhật một entity.

## 19. Retry có thể khuếch đại tải khi pool hoặc database đã quá tải

Khi acquire timeout hoặc query timeout xảy ra, retry tức thì có thể tạo thêm yêu cầu đúng lúc hệ thống đang bão hòa.

Ví dụ không nên retry liên tục không backoff:

~~~java
return repository.findById(id)
        .retry(5);
~~~

Một retry policy cần cân nhắc:

- Chỉ retry lỗi tạm thời và an toàn.
- Có giới hạn số lần.
- Có backoff và jitter.
- Có deadline tổng.
- Không retry lỗi validation hoặc constraint.
- Không retry write không idempotent nếu kết quả commit chưa rõ.
- Không để retry tạo tải vượt khả năng phục hồi của database.

Ví dụ:

~~~java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5);

return repository.findById(id)
        .retryWhen(retryPolicy);
~~~

Đây là ví dụ policy cho truy vấn có thể retry. Với thao tác ghi, phải đánh giá semantics lặp lại và idempotency trước khi áp dụng.

Khi database phục hồi, retry có backoff giúp tránh mọi client cùng thử lại ngay một lúc. Tuy nhiên, retry không thay thế circuit breaker, rate limit hoặc bulkhead khi cần kiểm soát tải.

## 20. Connection pool và nhiều loại workload

Nếu một ứng dụng có request tương tác và background batch, batch có thể chiếm toàn bộ connection khiến request quan trọng phải chờ.

Một số lựa chọn:

- Giới hạn concurrency batch thấp hơn.
- Chạy batch theo lịch hoặc queue có rate limit.
- Dành ngân sách connection hợp lý cho workload ưu tiên.
- Dùng pool riêng cho workload khác nhau nếu có lý do rõ và đã tính tổng connection.
- Đặt deadline cho request và job.
- Theo dõi pending acquire theo từng pool nếu có nhiều pool.

Không tạo nhiều pool chỉ để né queue mà chưa tính tổng số session. Hai pool max-size 20 và 20 vẫn có thể tạo 40 connection trên mỗi instance.

Nếu dùng pool riêng, cần quy định rõ transaction không tự chia sẻ giữa hai pool. Một transaction manager quản lý ConnectionFactory tương ứng; các thao tác qua pool khác không tự nằm trong cùng transaction atomic.

## 21. Tránh nhầm thread pool với connection pool

R2DBC là reactive database API. Connection pool và scheduler thread pool giải quyết hai loại tài nguyên khác nhau.

- Connection pool quản lý số connection database.
- Reactor scheduler quản lý nơi callback hoặc công việc được thực thi.
- flatMap concurrency giới hạn inner publisher của một pipeline.
- Database giới hạn khả năng xử lý truy vấn và session.

Không tăng số thread bằng Schedulers.parallel() để giải quyết pool cạn. Cũng không tăng pool để giải quyết CPU-heavy transformation.

Ví dụ CPU-heavy work có thể cần scheduler phù hợp:

~~~java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::calculateExpensiveScore);
~~~

Việc chuyển callback sang scheduler khác không tự làm query database nhanh hơn. Hãy tách rõ thời gian query, thời gian chờ connection và thời gian xử lý CPU.

Không chuyển R2DBC call sang boundedElastic chỉ vì quen với JDBC blocking. R2DBC driver đã cung cấp API non-blocking; dùng scheduler blocking một cách tùy tiện có thể làm mất lợi ích reactive và che giấu thiết kế pipeline chưa đúng.

## 22. Những anti-pattern khi tối ưu concurrency và pool

- **Đặt max-size thật lớn để hết acquire timeout:** có thể làm database bão hòa.
- **Tăng flatMap concurrency trên từng request mà không tính tổng request:** tạo tải lớn hơn dự kiến.
- **Cho mọi background worker chạy concurrency tối đa:** batch có thể chiếm hết pool.
- **Giữ transaction mở khi gọi HTTP hoặc xử lý lâu:** connection bị giữ không cần thiết.
- **Chạy nhiều statement song song trên cùng transaction connection:** driver có thể không hỗ trợ.
- **Dùng prefetch như thể đó là số connection:** hai tham số có ý nghĩa khác nhau.
- **Dùng collectList() cho dữ liệu không giới hạn:** tăng memory pressure.
- **Retry tức thì khi pool timeout:** khuếch đại tải.
- **Chỉ đo connection count:** không thấy latency, queue, lock và throughput.
- **Tính pool theo một replica:** bỏ qua autoscaling và rolling deployment.
- **Tạo nhiều pool mà không cộng tổng max-size:** vượt ngân sách database.
- **Tăng thread pool để sửa connection pool:** xử lý nhầm loại tài nguyên.
- **Dùng H2 hoặc mock để tuning pool production:** không phản ánh driver và engine thật.

## 23. Checklist trước khi thay đổi cấu hình

Trước khi tăng concurrency hoặc max-size, hãy xác định:

1. Query throughput thực tế và số query trung bình mỗi request là bao nhiêu?
2. Thời gian giữ connection trung bình và p95/p99 là bao nhiêu?
3. Pool có bao nhiêu connection acquired, idle và pending?
4. Acquire timeout xảy ra thường xuyên hay chỉ trong burst?
5. Database còn headroom CPU, memory, I/O và connection không?
6. Có lock wait, slow query hoặc transaction dài không?
7. Mỗi request có bao nhiêu inner publisher và concurrency?
8. Có bao nhiêu request/background subscription chạy cùng lúc?
9. Số replica tối đa và số pool trên mỗi replica là bao nhiêu?
10. Tổng max-size có nằm trong ngân sách database không?
11. Có transaction hoặc Flux stream giữ connection lâu không?
12. Có thao tác song song trên cùng transaction connection không?
13. Retry có backoff và write có idempotent không?
14. Load test đã dùng đúng database/driver và workload đại diện chưa?
15. p95/p99, throughput và DB resource có cải thiện sau thay đổi không?

## 24. Kết luận

Tối ưu mức đồng thời cùng kích thước pool là bài toán cân bằng giữa số thao tác reactive đang hoạt động, số connection ứng dụng được phép mượn và năng lực xử lý thực tế của database. flatMap concurrency là giới hạn theo từng subscription; khi có nhiều request và worker, tổng concurrency có thể lớn hơn nhiều so với tham số đặt trong một pipeline. Connection pool max-size là giới hạn connection theo pool của một instance, còn tổng connection toàn hệ thống phải tính theo mọi pool và mọi replica.

Hãy bắt đầu bằng ngân sách connection của database, đo thời gian giữ connection và throughput, dùng Little’s Law để ước lượng số thao tác trung bình đang hoạt động, rồi kiểm chứng bằng load test. Giới hạn concurrency theo workload, giữ transaction ngắn, tránh stream dài và batch không kiểm soát, đặt acquire/query/request timeout phù hợp và quan sát pool pending cùng database latency/CPU/lock. Tăng pool chỉ khi pool thực sự là nút thắt và database còn khả năng xử lý. Mục tiêu là throughput ổn định với tail latency và tài nguyên nằm trong giới hạn, không phải tạo nhiều connection hoặc publisher nhất có thể.

