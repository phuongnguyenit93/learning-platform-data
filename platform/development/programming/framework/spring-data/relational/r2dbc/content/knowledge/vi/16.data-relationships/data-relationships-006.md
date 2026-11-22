# Nhận diện và xử lý truy vấn N+1

Trong ứng dụng Spring Data Relational R2DBC, truy vấn N+1 xuất hiện khi ứng dụng lấy một tập bản ghi cha bằng một câu SQL, sau đó thực hiện thêm một câu SQL cho từng bản ghi cha để lấy dữ liệu liên quan. Nếu có N bản ghi cha, tổng số lần truy vấn thường là 1 + N.

Ví dụ, ứng dụng lấy danh sách 100 khách hàng rồi lần lượt truy vấn đơn hàng của từng khách hàng. Database nhận một câu SELECT khách hàng và thêm 100 câu SELECT đơn hàng. Dù các thao tác được viết bằng Mono hoặc Flux và không chặn thread theo mô hình R2DBC, số lượt trao đổi với database vẫn là 101.

**Reactive không tự loại bỏ N+1.** R2DBC giúp tổ chức I/O theo mô hình non-blocking, còn N+1 là vấn đề về số lượng truy vấn và round trip. Muốn xử lý, cần thay đổi cách lấy dữ liệu: JOIN và projection, batch query với IN, truy vấn tổng hợp, hoặc thiết kế read model phù hợp.

## 1. N+1 là gì?

N+1 là mẫu truy vấn gồm:

1. Một truy vấn lấy N bản ghi gốc, thường gọi là bản ghi cha.
2. Mỗi bản ghi cha kích hoạt một truy vấn bổ sung để lấy dữ liệu liên quan.

Ví dụ có bảng customer và purchase_order:

~~~sql
SELECT id, name
FROM customer
WHERE active = true;
~~~

Sau đó, với mỗi customer, ứng dụng chạy:

~~~sql
SELECT id, customer_id, total
FROM purchase_order
WHERE customer_id = :customerId;
~~~

Nếu kết quả truy vấn đầu có 100 khách hàng, câu SELECT thứ hai được chạy 100 lần.

| Thành phần | Số lần truy vấn |
|---|---:|
| Lấy danh sách customer | 1 |
| Lấy purchase_order cho từng customer | N |
| Tổng cộng | 1 + N |

Với N = 100, tổng số truy vấn là 101. Nếu N tăng lên 1.000, số truy vấn tăng lên 1.001 dù màn hình chỉ cần hiển thị một danh sách.

Tên gọi N+1 mô tả số truy vấn theo số bản ghi cha. Đây không phải lỗi cú pháp SQL hay lỗi riêng của R2DBC; nó là vấn đề thiết kế luồng truy cập dữ liệu.

## 2. N+1 phát sinh như thế nào trong R2DBC?

Trong Spring Data R2DBC, N+1 thường xuất hiện khi service gọi repository bên trong một reactive operator cho từng phần tử:

~~~java
public Flux<CustomerWithOrders> findCustomersWithOrders() {
    return customerRepository.findByActiveTrue()
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerWithOrders(customer, orders)
                )
        );
}
~~~

Luồng thực hiện:

1. findByActiveTrue() phát ra các customer.
2. Với mỗi customer, flatMap gọi findByCustomerId().
3. Mỗi lần gọi repository tạo một truy vấn lấy đơn hàng.
4. Kết quả đơn hàng được gom thành danh sách và gắn với customer.

Nếu truy vấn đầu trả N customer, phần truy vấn con được gọi N lần. Số truy vấn là 1 + N.

Thay flatMap bằng concatMap không giải quyết N+1:

~~~java
return customerRepository.findByActiveTrue()
    .concatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders ->
                new CustomerWithOrders(customer, orders)
            )
    );
~~~

concatMap làm các truy vấn con chạy tuần tự theo thứ tự phần tử. Nó có thể giảm mức độ đồng thời và giữ thứ tự, nhưng vẫn phát sinh một truy vấn cho mỗi customer. flatMap có thể chạy nhiều truy vấn con đồng thời, song số lượng truy vấn vẫn là N.

## 3. Vì sao N+1 gây vấn đề?

Mỗi truy vấn database thường có chi phí cố định ngoài thời gian thực thi SQL:

- Gửi request qua kết nối.
- Database phân tích và lập kế hoạch câu lệnh.
- Thực thi và đọc kết quả.
- Truyền dữ liệu về ứng dụng.
- Driver giải mã kết quả và phát các row vào reactive pipeline.

Khi số round trip tăng, chi phí cố định này lặp lại nhiều lần. Ngay cả khi từng câu SQL chạy nhanh, tổng thời gian vẫn có thể lớn.

Ví dụ minh họa:

| Số customer | Truy vấn cha | Truy vấn con | Tổng truy vấn |
|---:|---:|---:|---:|
| 10 | 1 | 10 | 11 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |
| 1.000 | 1 | 1.000 | 1.001 |

Các con số thời gian thực tế còn phụ thuộc connection pool, network latency, database load, index và kích thước kết quả. Tuy nhiên, số lượng truy vấn tăng tuyến tính theo số bản ghi cha là dấu hiệu cần kiểm tra.

### Reactive không làm biến mất chi phí round trip

R2DBC cho phép thread không phải đứng chờ I/O theo cách blocking của JDBC. Khi database đang xử lý, event loop có thể phục vụ công việc khác. Nhưng database vẫn phải nhận từng câu lệnh và gửi từng kết quả.

N+1 trong reactive pipeline có thể làm:

- Tăng tổng thời gian hoàn thành request.
- Tăng số lần acquire hoặc sử dụng connection.
- Tạo nhiều statement và nhiều tín hiệu reactive.
- Tăng tải xử lý trên database.
- Làm pool bận lâu hơn khi nhiều truy vấn cùng chạy.
- Tạo áp lực lớn khi số customer trong kết quả tăng.

Nếu flatMap chạy đồng thời nhiều truy vấn, tải đỉnh lên database có thể tăng mạnh. Nếu concatMap chạy tuần tự, thời gian hoàn thành có thể tăng do phải chờ từng truy vấn nối tiếp.

## 4. Phân biệt N+1 với một truy vấn có nhiều dòng

Không phải cứ có nhiều row hoặc nhiều câu SQL là N+1.

- Một câu JOIN trả 1.000 dòng vẫn chỉ là một truy vấn.
- Hai câu truy vấn cố định, một câu lấy customer và một câu batch lấy tất cả order, thường là hai truy vấn dù có hàng trăm customer.
- Một truy vấn cho mỗi customer là mẫu N+1.
- Nhiều truy vấn độc lập theo các bước nghiệp vụ khác nhau không nhất thiết là N+1.

Điểm cần xem là số lần thực thi truy vấn có tăng theo số phần tử của tập cha hay không.

## 5. N+1 trong R2DBC khác gì với lazy loading của ORM?

Trong JPA/Hibernate, N+1 thường được nhắc đến khi ứng dụng tải danh sách entity rồi truy cập một quan hệ lazy. ORM có thể phát thêm một câu SELECT cho từng entity khi quan hệ được truy cập.

Spring Data Relational và Spring Data R2DBC không cung cấp persistence context và cơ chế lazy-loading proxy như JPA/Hibernate. Vì vậy, N+1 thường rõ ràng hơn trong code ứng dụng:

- Service gọi repository con trong flatMap/concatMap.
- Mapper gọi repository để bổ sung thông tin cho từng DTO.
- Một vòng lặp thực hiện DatabaseClient query cho từng ID.
- Nhiều component được gọi theo từng phần tử và mỗi component truy cập database riêng.

Ví dụ một mapper có thể vô tình tạo N+1:

~~~java
return customerRepository.findAll()
    .flatMap(customer ->
        ownerRepository.findById(customer.getOwnerId())
            .map(owner ->
                new CustomerView(
                    customer.getId(),
                    customer.getName(),
                    owner.getDisplayName()
                )
            )
    );
~~~

Nếu có 200 customer và owner của mỗi customer được truy vấn riêng, ứng dụng có thể chạy 1 truy vấn customer cộng 200 truy vấn owner. Nếu nhiều customer dùng chung một owner, cách này còn có thể truy vấn lặp cùng một owner nhiều lần.

## 6. Cách nhận diện N+1

Không nên chỉ suy đoán từ code. Hãy quan sát số câu SQL thực sự được thực thi trong một request hoặc một use case.

### 6.1. Bật log truy vấn trong môi trường phát triển

Có thể cấu hình logging cho các package Spring Data R2DBC, Spring R2DBC và driver theo phiên bản đang dùng. Mục tiêu là quan sát:

- Câu SELECT cha.
- Câu SELECT con lặp lại.
- Giá trị bind thay đổi theo từng customer ID.
- Số lần câu SQL tương tự được thực thi.
- Khoảng thời gian giữa các lần thực thi.

Log giúp nhìn thấy mẫu lặp, nhưng không nên bật log SQL chứa dữ liệu nhạy cảm ở production nếu chưa có chính sách che hoặc loại bỏ tham số.

### 6.2. Tìm mẫu câu lệnh lặp

Một dấu hiệu thường gặp:

~~~text
SELECT id, name FROM customer WHERE active = ?
SELECT id, customer_id, total FROM purchase_order WHERE customer_id = ?
SELECT id, customer_id, total FROM purchase_order WHERE customer_id = ?
SELECT id, customer_id, total FROM purchase_order WHERE customer_id = ?
...
~~~

Nếu cùng một cấu trúc SQL được gọi nhiều lần và chỉ khác customer_id, cần kiểm tra xem nó có nằm trong một vòng lặp hoặc reactive operator theo từng customer hay không.

### 6.3. Đếm query trên mỗi request

Có thể theo dõi:

- Tổng số câu SQL được thực thi trong một request.
- Số lần thực thi theo fingerprint của câu SQL.
- Số lần acquire connection.
- Thời gian truy vấn trung bình và p95/p99.
- Số dòng được trả về.
- Số request có query count tăng theo kích thước trang.

Nếu trang 20 customer chạy khoảng 21 truy vấn, còn trang 100 customer chạy khoảng 101 truy vấn, đó là bằng chứng mạnh của mẫu N+1.

### 6.4. Distributed tracing và database monitoring

Tracing giúp nhìn thấy nhiều span database bên trong một request. Nếu một request HTTP có một chuỗi dài các span SQL giống nhau, mỗi span xử lý một ID, cần xem xét N+1.

Database monitoring có thể nhóm câu lệnh theo query fingerprint, cho biết một loại SQL được thực thi bao nhiêu lần và chiếm bao nhiêu thời gian. Kết hợp thông tin này với trace ứng dụng giúp tìm được call site tạo truy vấn.

### 6.5. Kiểm thử số lượng truy vấn

Một integration test có thể tạo một tập customer và order đã biết, thực thi use case rồi đo số truy vấn. Với giải pháp batch, số query nên giữ gần như cố định theo số batch, thay vì tăng một lần cho mỗi customer.

Có thể dùng một R2DBC proxy hoặc ConnectionFactory wrapper trong kiểm thử để đếm statement execution. Cần đo các truy vấn phát sinh trong chính use case, loại trừ setup schema và dữ liệu test.

Không nên kiểm tra quá cứng một con số nếu framework có thể thực hiện thêm truy vấn metadata hoặc statement khác theo phiên bản. Hãy đặt ngưỡng phản ánh mục tiêu kiến trúc, ví dụ số query không tăng tuyến tính theo số customer.

## 7. Cách xử lý thứ nhất: JOIN và projection

Nếu màn hình cần customer cùng thông tin order, có thể lấy chúng bằng một câu JOIN:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       o.id AS order_id,
       o.total AS order_total
FROM customer c
LEFT JOIN purchase_order o
       ON o.customer_id = c.id
WHERE c.active = true
ORDER BY c.id, o.id;
~~~

Thay vì một truy vấn cha và N truy vấn con, database thực hiện một truy vấn có JOIN.

Ánh xạ kết quả phẳng:

~~~java
public record CustomerOrderRow(
    Long customerId,
    String customerName,
    Long orderId,
    BigDecimal orderTotal
) {
}
~~~

~~~java
Flux<CustomerOrderRow> rows =
    databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderRow(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_id", Long.class),
            row.get("order_total", BigDecimal.class)
        ))
        .all();
~~~

Vì JOIN một-nhiều tạo một dòng cho mỗi order, thông tin customer bị lặp trên nhiều dòng. Ứng dụng có thể nhóm các dòng theo customer ID để tạo response lồng nhau.

~~~java
Mono<List<CustomerWithOrders>> result =
    rows.collectList()
        .map(this::groupCustomerOrderRows);
~~~

Phương thức groupCustomerOrderRows sẽ gom tất cả row có cùng customerId, tạo một customer và danh sách order tương ứng.

### Ưu điểm của JOIN

- Giảm số round trip tới database.
- Cho phép database tối ưu JOIN và filter.
- Có thể chọn chính xác các cột cần thiết.
- Thuận tiện cho projection, báo cáo và read model.

### Những điểm cần chú ý

- Một customer có nhiều order sẽ xuất hiện nhiều lần trong kết quả phẳng.
- Nhiều quan hệ one-to-many JOIN cùng lúc có thể tạo tích Descartes hoặc làm số dòng tăng rất lớn.
- Cần xử lý các cột null do LEFT JOIN khi customer không có order.
- Nếu gom toàn bộ bằng collectList(), bộ nhớ tăng theo kích thước kết quả.
- Phân trang trên kết quả JOIN một-nhiều có thể phân trang theo row thay vì theo customer.

JOIN phù hợp khi dữ liệu cần lấy có quan hệ rõ và kích thước kết quả có thể kiểm soát. Không nên JOIN mọi bảng chỉ để giảm số lượng SQL nếu kết quả phình to quá mức.

## 8. Cách xử lý thứ hai: batch query bằng IN

Nếu muốn giữ hai loại dữ liệu riêng và tránh kết quả JOIN lặp nhiều dòng cha, có thể:

1. Truy vấn danh sách customer.
2. Thu thập ID của các customer.
3. Truy vấn tất cả order thuộc các ID đó bằng một câu IN.
4. Nhóm order theo customer ID.
5. Ghép danh sách order vào từng customer.

Ví dụ repository:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Flux<PurchaseOrder> findByCustomerIdIn(
        Collection<Long> customerIds
    );
}
~~~

Service:

~~~java
public Flux<CustomerWithOrders> findCustomersWithOrders() {
    return customerRepository.findByActiveTrue()
        .collectList()
        .flatMapMany(customers -> {
            if (customers.isEmpty()) {
                return Flux.empty();
            }

            List<Long> customerIds = customers.stream()
                .map(Customer::getId)
                .toList();

            return orderRepository.findByCustomerIdIn(customerIds)
                .collectMultimap(PurchaseOrder::getCustomerId)
                .flatMapMany(ordersByCustomer ->
                    Flux.fromIterable(customers)
                        .map(customer -> {
                            Collection<PurchaseOrder> orders =
                                ordersByCustomer.getOrDefault(
                                    customer.getId(),
                                    List.of()
                                );

                            return new CustomerWithOrders(
                                customer,
                                List.copyOf(orders)
                            );
                        })
                );
        });
}
~~~

Với N customer trong một batch, cách này thường cần:

- Một query lấy customer.
- Một query lấy tất cả order của các customer đó.

Tổng cộng khoảng hai query thay vì 1 + N.

### Vì sao phải kiểm tra danh sách rỗng?

Nếu không có customer, không cần gọi truy vấn order. Một số database không chấp nhận cú pháp IN với danh sách rỗng; hành vi expansion cũng phụ thuộc API và phiên bản framework. Trả Flux.empty() giúp tránh phát sinh câu query vô ích.

### Giới hạn kích thước batch

Một danh sách IN quá lớn có thể vượt giới hạn bind parameter hoặc tạo SQL lớn. Khi có nhiều customer, chia ID thành từng batch có kích thước hợp lý:

~~~text
Customer IDs: 1 ... 2.500
       |
       +-- Batch 1: 1 ... 500
       +-- Batch 2: 501 ... 1.000
       +-- Batch 3: 1.001 ... 1.500
       +-- Batch 4: 1.501 ... 2.000
       +-- Batch 5: 2.001 ... 2.500
~~~

Mỗi batch chạy một truy vấn lấy orders. Số truy vấn khi đó tăng theo số batch, không phải theo số customer.

Nếu dùng DatabaseClient và tự tạo mệnh đề IN, hãy tạo placeholder riêng cho từng ID và bind giá trị. Không nối ID người dùng vào chuỗi SQL. Cần kiểm tra khả năng collection expansion của abstraction và driver cụ thể thay vì giả định mọi R2DBC driver đều nhận một collection trong một bind marker.

## 9. Batch theo từng trang dữ liệu

Không nên luôn collect toàn bộ customer vào bộ nhớ. Với tập dữ liệu lớn, hãy phân trang danh sách cha rồi batch query các bản ghi con theo ID của trang hiện tại.

Ví dụ quy trình:

~~~text
Đọc trang customer (ví dụ 100 bản ghi)
              |
              v
Lấy 100 customer ID
              |
              v
Một query lấy orders cho 100 ID
              |
              v
Nhóm orders theo customer ID
              |
              v
Tạo response cho trang hiện tại
              |
              v
Đọc trang customer tiếp theo
~~~

Nếu có P trang, mỗi trang cần một truy vấn cha và một truy vấn con batch, tổng số truy vấn xấp xỉ 2P. Đây vẫn là số lượng hữu hạn theo trang thay vì một query cho từng customer.

Khi phân trang, nên:

- Dùng thứ tự ổn định, ví dụ created_at kết hợp ID làm tie-breaker.
- Chỉ lấy ID và các cột cần thiết cho bước batch.
- Giới hạn số phần tử mỗi trang để kiểm soát kích thước IN.
- Xử lý trường hợp trang rỗng.
- Không phân trang trực tiếp trên kết quả JOIN một-nhiều nếu mục tiêu là phân trang theo customer.

## 10. Cách xử lý thứ ba: dùng SQL aggregate khi chỉ cần số liệu

Đôi khi ứng dụng chỉ cần số đơn hàng của mỗi customer, không cần toàn bộ order. Khi đó, không cần tải danh sách order rồi đếm trong Java.

Có thể dùng GROUP BY:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o
       ON o.customer_id = c.id
WHERE c.active = true
GROUP BY c.id, c.name
ORDER BY c.id;
~~~

DTO:

~~~java
public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
~~~

Mapping:

~~~java
Flux<CustomerOrderCount> counts =
    databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderCount(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_count", Long.class)
        ))
        .all();
~~~

Database tính COUNT và chỉ trả về số liệu cần thiết. Đây thường là lựa chọn hiệu quả cho dashboard hoặc danh sách có số lượng liên quan.

Lưu ý dùng COUNT(o.id) thay vì COUNT(*) trong truy vấn LEFT JOIN. Khi customer không có order, LEFT JOIN vẫn tạo một dòng với các cột order là NULL; COUNT(*) có thể đếm dòng đó thành 1, trong khi COUNT(o.id) trả về 0.

## 11. Cách xử lý thứ tư: dùng read model hoặc cache có kiểm soát

Nếu một màn hình thường xuyên cần dữ liệu ghép từ nhiều bảng, có thể xây dựng read model phù hợp với nhu cầu hiển thị:

- View trong database.
- Bảng tổng hợp được cập nhật theo quy trình nghiệp vụ.
- Read model riêng cho truy vấn dashboard.
- Cache các dữ liệu tham chiếu dùng chung và ít thay đổi.

Những cách này có thể giảm việc lặp lại JOIN hoặc batch query, nhưng làm tăng yêu cầu về đồng bộ và nhất quán dữ liệu.

Cache chỉ giúp khi các truy vấn lặp lại cùng một key và dữ liệu có chính sách invalidation rõ ràng. Cache từng order theo customer không phải giải pháp tổng quát cho N+1 nếu mỗi request vẫn phải kiểm tra hoặc tải hàng trăm key chưa có trong cache.

Không nên tạo bảng denormalized hoặc cache chỉ để chữa một truy vấn chưa được đo lường. Trước hết, xác định use case và query pattern thực tế.

## 12. Giới hạn concurrency không phải là loại bỏ N+1

Nếu chưa thể thay đổi ngay cách truy vấn, có thể giới hạn số truy vấn con chạy đồng thời:

~~~java
return customerRepository.findByActiveTrue()
    .flatMap(
        customer -> orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders ->
                new CustomerWithOrders(customer, orders)
            ),
        8
    );
~~~

Tham số concurrency giới hạn số inner publisher được xử lý đồng thời tại một thời điểm. Nó giúp tránh tạo quá nhiều truy vấn đồng thời và giảm áp lực lên connection pool.

Tuy nhiên, nếu có 100 customer thì vẫn có thể có 100 truy vấn con. Tổng số truy vấn vẫn là 101. Đây là biện pháp kiểm soát tải tạm thời, không phải cách loại bỏ N+1.

Tương tự:

- concatMap chạy tuần tự nhưng vẫn có N truy vấn.
- flatMap với concurrency giới hạn vẫn có N truy vấn.
- zip hoặc merge nhiều publisher không tự động gộp SQL.
- Bọc các truy vấn trong một transaction không làm chúng trở thành một truy vấn.

Muốn giảm query count, phải thay đổi cách lấy dữ liệu hoặc gom các ID vào một truy vấn batch.

## 13. Index có giải quyết N+1 không?

Index trên purchase_order.customer_id có thể làm từng truy vấn con nhanh hơn:

~~~sql
CREATE INDEX idx_purchase_order_customer_id
ON purchase_order(customer_id);
~~~

Nhưng index không làm số truy vấn giảm từ 1 + N xuống 2. Nó chỉ giúp database tìm order nhanh hơn cho mỗi lần truy vấn.

Index là tối ưu bổ sung hữu ích sau khi đã chọn chiến lược truy vấn phù hợp. Cần kiểm tra execution plan và workload để quyết định index, không tạo index chỉ dựa trên tên cột.

## 14. Những lỗi cần tránh khi xử lý N+1

### 14.1. Dùng flatMap và nghĩ rằng đã batch

~~~java
customers.flatMap(customer ->
    orderRepository.findByCustomerId(customer.getId())
);
~~~

flatMap chỉ kết hợp các publisher. Nó không tự gộp nhiều repository call thành một SQL IN.

### 14.2. Dùng concatMap rồi nghĩ query count đã giảm

concatMap chỉ tuần tự hóa các truy vấn con. Nó có thể làm request chậm hơn nếu phải đợi từng query nối tiếp.

### 14.3. Dùng cache mà không có invalidation

Cache dữ liệu quan hệ mà không xác định thời gian sống hoặc quy tắc invalidation có thể trả dữ liệu cũ. Cache cũng không giúp với các key mới chưa được tải.

### 14.4. JOIN quá nhiều quan hệ một-nhiều

Nếu customer có nhiều order và mỗi order có nhiều line, JOIN cả hai quan hệ có thể tạo số dòng bằng tích số lượng phần tử. Kết quả có thể lớn hơn nhiều so với dữ liệu nghiệp vụ thực sự.

Trong trường hợp đó, hai query batch riêng có thể hiệu quả và dễ nhóm dữ liệu hơn một JOIN lớn.

### 14.5. Phân trang sau JOIN một-nhiều

LIMIT/OFFSET trên kết quả JOIN có thể cắt giữa các order của một customer hoặc làm một customer xuất hiện ở nhiều trang. Nếu yêu cầu là phân trang customer, hãy phân trang bảng customer trước rồi mới lấy dữ liệu con cho trang đó.

### 14.6. Dùng collectList() không giới hạn

collectList() thuận tiện để nhóm dữ liệu, nhưng có thể giữ toàn bộ kết quả trong bộ nhớ. Với dữ liệu lớn, hãy phân trang hoặc xử lý theo batch có kích thước giới hạn.

## 15. Kiểm thử để tránh N+1 quay trở lại

Sau khi tối ưu, nên có integration test kiểm tra số query hoặc xu hướng query count.

Ví dụ bộ dữ liệu:

- 5 customer.
- Mỗi customer có 3 order.
- Use case trả customer cùng danh sách order.

So sánh:

| Cách triển khai | Số query dự kiến |
|---|---:|
| Lấy customer rồi query order từng người | 1 + 5 = 6 |
| JOIN customer và order | 1 |
| Lấy customer rồi batch order bằng IN | 2 |
| Batch theo từng trang, một trang chứa 5 customer | 2 |

Con số thực tế có thể cộng thêm query setup, transaction hoặc thao tác phụ của framework. Test nên đo riêng phần truy cập dữ liệu của use case.

Ngoài query count, cần kiểm tra:

- Kết quả có đủ customer không?
- Customer không có order có được giữ lại không?
- Mỗi order có gắn đúng customer không?
- Có bị trùng order do JOIN không?
- Phân trang có đúng theo entity cha không?
- Dữ liệu có được lọc theo tenant và quyền truy cập không?
- Thứ tự kết quả có ổn định không?

Một tối ưu chỉ giảm query count nhưng làm sai kết quả không phải là tối ưu hợp lệ.

## 16. Chọn chiến lược theo use case

| Nhu cầu | Chiến lược phù hợp |
|---|---|
| Danh sách cha kèm một số trường con | JOIN và DTO/projection |
| Cần danh sách object cha và collection con | Batch query bằng IN rồi group theo parent ID |
| Chỉ cần số lượng hoặc tổng tiền liên quan | GROUP BY và hàm aggregate |
| Dữ liệu lớn cần phân trang | Phân trang cha trước, batch con theo từng trang |
| Truy vấn lặp cùng dữ liệu tham chiếu ít thay đổi | Cache có chính sách invalidation |
| Chưa thể sửa ngay N+1 | Giới hạn concurrency để giảm áp lực tạm thời |
| Nhiều màn hình dùng cùng một read shape | Xem xét read model hoặc database view |

Không có một cách duy nhất phù hợp với mọi quan hệ. JOIN thường tốt cho một truy vấn đọc có kích thước kiểm soát; batch IN phù hợp khi muốn giữ các collection riêng; aggregate query phù hợp khi chỉ cần số liệu.

## 17. Quy trình tìm và xử lý N+1

Có thể áp dụng trình tự sau:

1. Chọn một request hoặc use case có dấu hiệu chậm.
2. Đếm tổng số SQL statement trong request.
3. Nhóm statement theo query fingerprint và xem câu nào lặp lại.
4. Đối chiếu tham số để tìm mẫu một query cha cộng một query con cho mỗi ID.
5. Tìm call site trong reactive chain, mapper hoặc vòng lặp repository.
6. Xác định dữ liệu thực sự cần: full object graph, một projection hay chỉ số liệu.
7. Chọn JOIN, batch IN, aggregate query hoặc read model.
8. Nếu cần, phân trang cha và chia batch để giới hạn bộ nhớ cùng số bind parameter.
9. Kiểm thử cả kết quả lẫn query count với số lượng parent khác nhau.
10. Theo dõi lại latency, query count, pool usage và tải database sau thay đổi.

Khi tăng số parent từ 10 lên 100, số query của giải pháp tốt không nên tăng thêm 90 chỉ vì mỗi parent lại gọi một repository method riêng. Nếu dùng batch theo trang, query count nên tăng theo số trang hoặc số batch.

## 18. Ghi nhớ

- N+1 là một truy vấn lấy N bản ghi cha cộng thêm N truy vấn con, thường tổng cộng 1 + N.
- Trong R2DBC, N+1 thường đến từ việc gọi repository hoặc DatabaseClient bên trong flatMap, concatMap hoặc vòng lặp theo từng entity.
- Reactive không loại bỏ round trip tới database; flatMap chỉ điều khiển cách kết hợp và mức độ đồng thời.
- Nhận diện bằng SQL log, query fingerprint, tracing, metrics và integration test đếm statement.
- JOIN và projection có thể lấy dữ liệu liên quan trong một truy vấn, nhưng cần xử lý row lặp và pagination.
- Batch IN thường giảm 1 + N query thành một query cha và một query con cho mỗi batch.
- Nếu chỉ cần số liệu, dùng COUNT/GROUP BY thay vì tải toàn bộ collection về ứng dụng.
- Phân trang cha trước rồi batch dữ liệu con theo từng trang khi tập dữ liệu lớn.
- Giới hạn concurrency chỉ giảm số truy vấn chạy cùng lúc, không giảm tổng số truy vấn.
- Index làm từng truy vấn nhanh hơn nhưng không tự loại bỏ N+1.
- Chọn chiến lược theo hình dạng dữ liệu cần trả về và kiểm thử cả tính đúng đắn lẫn số query.
