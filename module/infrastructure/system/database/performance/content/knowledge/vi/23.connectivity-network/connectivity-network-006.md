# Độ trễ mạng, số lượt trao đổi và khoảng cách giữa ứng dụng với cơ sở dữ liệu

Một truy vấn có thể có execution time rất thấp trong cơ sở dữ liệu nhưng API vẫn phản hồi chậm. Nguyên nhân thường nằm ở đường đi giữa ứng dụng và DBMS: mỗi lần gửi lệnh phải đi qua mạng, thiết lập kết nối có chi phí, kết quả có thể phải truyền thành nhiều gói, hoặc ứng dụng thực hiện quá nhiều lượt hỏi đáp tuần tự. Khi ứng dụng và cơ sở dữ liệu nằm ở hai vùng địa lý xa nhau, độ trễ của từng lượt trao đổi có thể trở thành phần lớn thời gian phản hồi.

Trong chương **Kết nối và mạng**, bài học này phân tích độ trễ mạng, số lượt trao đổi và khoảng cách giữa ứng dụng với cơ sở dữ liệu. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta sẽ tách thời gian thực thi SQL khỏi thời gian kết nối và truyền dữ liệu, nhận diện round trips dư thừa, giảm mẫu truy vấn chatty, tổ chức connection pool và batch hợp lý, rồi benchmark trên topology gần production.

Tối ưu kết nối không chỉ là tăng băng thông. Với nhiều API OLTP, một truy vấn trả về vài dòng có thể bị chi phối bởi latency của từng lượt trao đổi. Giảm số lần ứng dụng phải chờ DBMS thường đem lại lợi ích rõ hơn việc truyền nhanh hơn một lượng dữ liệu nhỏ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích latency, round-trip time (RTT), throughput và bandwidth trong đường truyền ứng dụng-cơ sở dữ liệu.
- Phân biệt thời gian thiết lập kết nối, thời gian chờ DBMS, thời gian truyền kết quả và thời gian xử lý ở ứng dụng.
- Ước lượng tác động của nhiều lượt trao đổi tuần tự đến latency tổng thể.
- Nhận diện truy vấn chatty, N+1 queries và các transaction có nhiều lượt gửi nhận.
- Giảm round trips bằng JOIN, truy vấn set-based, batch, fetch size và connection reuse khi phù hợp.
- Đánh giá chi phí của TLS handshake, DNS, TCP setup, connection pooling và proxy.
- Hiểu tác động của khoảng cách địa lý, cross-zone/cross-region và network path.
- Đo bytes, packets, RTT, retransmission, connection wait và DB execution time.
- Thiết kế timeout, retry và idempotency để xử lý lỗi mạng mà không tạo tải lặp.
- Benchmark với cùng topology, concurrency, payload và cache state để xác nhận cải thiện.

## 1. Các khái niệm mạng cần phân biệt

### 1.1. Latency và round-trip time

Latency là thời gian trễ khi dữ liệu đi qua một thành phần hoặc đường truyền. Trong giao tiếp request-response, round-trip time (RTT) là thời gian để một tín hiệu đi từ bên gửi tới bên nhận và phản hồi quay lại bên gửi.

Với ứng dụng gửi SQL tới DBMS, một lượt trao đổi có thể bao gồm:
1. Ứng dụng gửi request qua socket.
2. Hệ điều hành và mạng chuyển dữ liệu đến máy chủ DBMS.
3. DBMS nhận và xử lý request.
4. DBMS gửi phản hồi.
5. Ứng dụng nhận và giải mã phản hồi.

RTT đo thời gian khứ hồi mạng theo một phép đo cụ thể; thời gian hoàn tất một SQL request còn bao gồm xử lý ở DBMS và driver. Vì vậy không nên đồng nhất query latency với network RTT.

### 1.2. Bandwidth và throughput

Bandwidth là năng lực truyền tối đa của một đường truyền trong điều kiện nhất định. Throughput là lượng dữ liệu thực tế được truyền trong một đơn vị thời gian.

Một đường truyền có bandwidth cao vẫn có thể có latency lớn. Ví dụ kết nối liên vùng có thể truyền hàng gigabyte mỗi giây sau khi pipeline ổn định, nhưng mỗi request nhỏ vẫn phải chờ một khoảng RTT đáng kể.

Điều này tạo ra hai kiểu nút thắt:
- **Latency-bound:** thời gian bị chi phối bởi số lượt trao đổi và thời gian chờ mỗi lượt.
- **Bandwidth-bound:** thời gian bị chi phối bởi lượng dữ liệu phải truyền so với thông lượng đường truyền.

API OLTP thường nhạy với latency-bound vì mỗi truy vấn trả về ít dữ liệu. Báo cáo trả hàng triệu dòng có thể nhạy với bandwidth-bound.

### 1.3. Packet, frame và payload

Ứng dụng gửi dữ liệu theo giao thức DBMS qua TCP/IP. Dữ liệu được chia thành các segment/packet và frame theo từng tầng mạng. Một câu SQL nhỏ không nhất thiết tương ứng với một packet; driver, TLS, TCP segmentation, buffering và network stack có thể gộp hoặc chia dữ liệu.

Payload là phần dữ liệu hữu ích của ứng dụng. Trên đường truyền còn có header của TCP/IP, TLS record, Ethernet hoặc tunnel. Vì vậy bytes trên wire có thể lớn hơn payload SQL/result.

Khi đo network, cần phân biệt:
- Số bytes ứng dụng gửi/nhận.
- Số bytes trên interface.
- Số packet/segment.
- Số lần request-response ở protocol.
- Số lần round trip thực sự phải chờ tuần tự.

Không thể suy ra round trips chỉ từ packet count.

### 1.4. Latency cộng dồn qua nhiều lượt tuần tự

Giả sử một request API cần 40 truy vấn DB độc lập, mỗi truy vấn mất khoảng 2 ms để đi-về và xử lý rất ít ở DBMS. Nếu các truy vấn được thực hiện tuần tự, phần chi phí lặp có thể gần 40 × 2 ms = 80 ms, chưa kể thời gian thực thi SQL, serialization và application logic.

Nếu cùng công việc được biểu diễn bằng một truy vấn set-based hoặc một batch phù hợp, số lượt trao đổi có thể giảm đáng kể. Đây là lý do số round trips thường quan trọng hơn việc rút ngắn vài microsecond trong một operator SQL.

Phép nhân trên chỉ là mô hình ước lượng. Trong thực tế có thể có pipelining, parallel requests, connection scheduling, protocol buffering và DB processing khác nhau. Hãy đo thời gian thực tế thay vì dùng RTT làm thời gian truy vấn chính xác.

## 2. Những thành phần tạo độ trễ ứng dụng-cơ sở dữ liệu

Thời gian một request DB từ góc nhìn ứng dụng có thể gồm:

~~~text
API request
   |
   +--> lấy connection từ pool
   |
   +--> DNS / TCP / TLS setup (nếu tạo kết nối mới)
   |
   +--> gửi SQL và tham số
   |
   +--> network transit + DB queueing
   |
   +--> DB execution / lock wait / I/O wait
   |
   +--> truyền result set qua mạng
   |
   +--> driver decode / mapping
   |
   +--> application processing
   |
   +--> trả connection về pool
~~~

Không phải mọi request đều phải thực hiện DNS/TCP/TLS setup. Với connection pool, kết nối thường đã được thiết lập và tái sử dụng. Sơ đồ giúp phân loại các thành phần cần đo.

### 2.1. Connection acquisition

Ứng dụng có thể phải chờ lấy connection từ pool nếu tất cả connection đang được sử dụng. Đây là thời gian chờ ở application/pool, không phải DB execution time.

Nếu pool quá nhỏ, request xếp hàng dù DBMS còn capacity. Nếu pool quá lớn, nhiều session có thể gây memory, worker, lock và I/O contention ở DBMS. Cần đo pool wait, active/idle connections, timeout và DB session count.

### 2.2. DNS lookup

Khi tạo kết nối mới, client có thể cần phân giải hostname thành địa chỉ IP. DNS cache thường giảm chi phí ở các lần tiếp theo, nhưng DNS timeout, resolver chậm hoặc cấu hình search domain có thể tạo tail latency.

Không nên thực hiện DNS lookup cho mỗi SQL statement. Dùng hostname ổn định, connection pooling và cơ chế DNS phù hợp với môi trường. Nếu DB endpoint thay đổi IP, pool và driver cần xử lý refresh/reconnect theo chính sách an toàn.

### 2.3. TCP handshake

Một kết nối TCP mới cần thiết lập trạng thái kết nối thông qua handshake. Việc này tiêu tốn ít nhất một lượt trao đổi mạng và có thể chịu ảnh hưởng lớn khi client và DBMS ở xa nhau.

Tái sử dụng kết nối giúp tránh lặp TCP handshake cho từng truy vấn. Tuy nhiên, kết nối lâu sống cần có kiểm tra health, xử lý idle timeout, failover và giới hạn tuổi kết nối theo môi trường.

### 2.4. TLS handshake

Nếu kết nối dùng TLS, thiết lập session có thêm chi phí handshake và trao đổi chứng chỉ/khóa. TLS session resumption có thể giảm chi phí ở các lần kết nối sau nếu client, server và driver hỗ trợ.

Không nên tắt TLS để giảm latency nếu kết nối đi qua mạng không tin cậy hoặc chính sách bảo mật yêu cầu mã hóa. Hãy tối ưu connection reuse, TLS configuration và topology trong phạm vi bảo đảm an toàn.

### 2.5. DB queueing và execution

Sau khi request tới DBMS, nó có thể chờ scheduler, lock, worker, memory hoặc I/O trước khi thực thi. Query execution time và wait time cần được tách theo khả năng quan sát của DBMS.

Nếu ứng dụng đo 100 ms nhưng DBMS ghi nhận query execution 5 ms, phần chênh lệch có thể nằm ở pool wait, network, driver, queueing hoặc thời gian fetch kết quả. Không nên lập tức thay index khi chưa phân loại thời gian.

### 2.6. Result transfer và driver decoding

DBMS có thể thực thi nhanh nhưng trả về nhiều dòng hoặc nhiều cột. Dữ liệu phải được serialize, truyền qua mạng, giải mã và ánh xạ thành object ở ứng dụng.

Một truy vấn SELECT * trên hàng trăm nghìn dòng có thể bị chi phối bởi bytes truyền và allocation/GC ở client. Projection chỉ lấy cột cần dùng, phân trang và streaming/fetch phù hợp có thể giảm chi phí.

## 3. Khoảng cách địa lý và topology

### 3.1. Cùng host, cùng zone, khác region

Độ trễ phụ thuộc vị trí của client, DBMS và đường mạng:

| Topology | Đặc điểm thường gặp | Rủi ro hiệu năng |
|---|---|---|
| Ứng dụng và DB cùng host | Network path ngắn, có thể dùng loopback hoặc socket | Cạnh tranh CPU/RAM và tài nguyên máy |
| Cùng data center/zone | RTT thường thấp và ổn định hơn | Network virtualization, congestion hoặc giới hạn bandwidth |
| Khác availability zone | Có thêm network hop và chi phí liên vùng | RTT và phí truyền dữ liệu có thể tăng |
| Khác region/quốc gia | Khoảng cách vật lý và nhiều hop hơn | Mỗi round trip có thể đắt; tail latency cao hơn |
| Ứng dụng qua VPN/proxy/service mesh | Có thêm tunnel, proxy hoặc TLS termination | Thêm hop, queue và xử lý mã hóa |

Đây là xu hướng, không phải cam kết về số ms. Hãy đo từ đúng subnet, zone, region, container hoặc VM mà ứng dụng production sử dụng.

### 3.2. Khoảng cách ảnh hưởng mạnh đến truy vấn chatty

Nếu mỗi truy vấn nhỏ cần một lượt request-response, khoảng cách địa lý được nhân lên theo số lượt tuần tự. Một ứng dụng ở xa DB có thể chịu latency cao ngay cả khi DBMS CPU gần như rảnh.

Ví dụ giả định RTT mạng là 8 ms:
- 1 round trip tuần tự có chi phí mạng cỡ 8 ms.
- 10 lượt tuần tự có thể cộng dồn khoảng 80 ms.
- 50 lượt tuần tự có thể cộng dồn khoảng 400 ms.

Đây là phép tính minh họa khi mỗi lượt phụ thuộc phản hồi trước. Thời gian DB execution, TCP behavior và protocol có thể làm số thực tế khác đi. Nếu các lệnh có thể batch hoặc pipeline, tổng thời gian có thể giảm.

### 3.3. Đặt application gần database

Với workload có nhiều SQL request nhỏ, triển khai application service trong cùng region hoặc gần DB endpoint thường giảm RTT. Tuy nhiên, cần xem toàn bộ kiến trúc: người dùng có thể ở vùng khác, service-to-service call có thể tăng, và replication/failover có thể thay đổi vị trí DB.

Không nên chuyển DB hoặc ứng dụng chỉ dựa trên ping. Hãy đo end-to-end latency, query mix, data transfer cost, availability, failover path và yêu cầu residency của dữ liệu.

### 3.4. Read replica và khoảng cách

Read replica ở gần người dùng có thể giảm latency đọc, nhưng có thể bị replication lag. Nếu API cần đọc dữ liệu vừa commit trên primary, đọc replica gần client có thể trả dữ liệu cũ.

Cần xác định consistency requirement:
- Đọc chấp nhận eventual consistency.
- Đọc cần read-your-writes.
- Đọc phải từ primary.
- Có thể định tuyến một số query sang replica sau khi xác nhận replication position.

Tối ưu khoảng cách không được làm sai semantics nghiệp vụ.

## 4. Round trips và truy vấn chatty

### 4.1. Một round trip có thể đắt hơn phần xử lý SQL

Một câu SELECT theo primary key có thể hoàn tất rất nhanh trong DBMS. Nhưng ứng dụng phải gửi request, chờ phản hồi, nhận result và giải mã. Nếu API cần hàng chục truy vấn nhỏ tuần tự, latency mạng lặp lại có thể chiếm phần lớn thời gian.

Mẫu chatty thường xuất hiện khi:
- Mỗi object được tải bằng một truy vấn riêng.
- ORM lazy loading phát sinh N+1 queries.
- Ứng dụng kiểm tra tồn tại rồi mới truy vấn chi tiết trong một lượt khác.
- Một transaction gửi nhiều statement độc lập mà có thể batch.
- Ứng dụng đọc từng dòng bằng query riêng thay vì fetch result set.
- API gọi stored procedure hoặc service theo từng thuộc tính.

### 4.2. N+1 query

Ví dụ ứng dụng tải 100 đơn hàng, sau đó truy vấn khách hàng riêng cho từng đơn:

~~~java
List<Order> orders = orderRepository.findRecentOrders();

for (Order order : orders) {
    Customer customer =
        customerRepository.findById(order.getCustomerId());
    order.setCustomer(customer);
}
~~~

Nếu không có cache hoặc batch fetching, ứng dụng có thể thực hiện 1 truy vấn lấy orders và 100 truy vấn lấy customers. Đây là N+1 pattern.

Có thể lấy dữ liệu bằng JOIN:

~~~sql
SELECT o.order_id,
       o.created_at,
       c.customer_id,
       c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= :from_time
ORDER BY o.created_at DESC;
~~~

Một truy vấn có thể giảm round trips, nhưng JOIN có thể nhân bản dòng nếu quan hệ một-nhiều. Hãy chọn projection và join cardinality phù hợp, kiểm tra actual plan và tránh kéo về cột không cần thiết.

Nếu JOIN quá lớn hoặc làm dữ liệu lặp nhiều, batch load theo tập customer_id có thể là phương án cân bằng. Mục tiêu là giảm lượt trao đổi mà không tạo result set phình to.

### 4.3. Lazy loading và ORM

Lazy loading trì hoãn truy vấn quan hệ đến khi thuộc tính được truy cập. Điều này tiện trong code nhưng có thể phát sinh truy vấn ẩn trong vòng lặp, serialization hoặc template rendering.

Cách kiểm soát:
- Bật SQL logging/trace trong môi trường phù hợp để thấy số query.
- Dùng fetch join/entity graph cho quan hệ thực sự cần.
- Dùng batch fetching nếu ORM hỗ trợ.
- Dùng DTO projection thay vì tải toàn bộ object graph.
- Kiểm tra pagination để tránh fetch join collection gây duplicate hoặc sai phân trang.
- Đặt giới hạn cho lazy loading ngoài transaction nếu framework cho phép.

Không nên eager load mọi quan hệ. Điều đó có thể tạo JOIN rất rộng, tải nhiều dữ liệu không cần thiết và tăng memory.

### 4.4. Nhiều statement trong một transaction

Một transaction có thể gồm nhiều câu SQL tuần tự:

~~~text
BEGIN
SELECT account
UPDATE account
INSERT audit row
UPDATE order
COMMIT
~~~

Nếu mỗi statement phải chờ một round trip, latency mạng có thể cộng dồn. Một stored procedure hoặc batch có thể giảm số lượt client-server, nhưng chuyển logic vào DBMS có trade-off về khả năng bảo trì, versioning và resource usage.

Hãy cân nhắc:
- Có thể gộp thao tác thành một statement set-based không?
- Có thể dùng RETURNING/OUTPUT để lấy kết quả ngay trong cùng statement không?
- Có thể batch nhiều INSERT/UPDATE không?
- Có thể dùng stored procedure nếu logic dữ liệu phù hợp không?
- Có cần từng kết quả trung gian ở ứng dụng hay không?

Không gộp các thao tác nếu làm thay đổi thứ tự, atomicity hoặc xử lý lỗi của nghiệp vụ.

## 5. Giảm round trips bằng SQL set-based

### 5.1. Thay vòng lặp truy vấn bằng một truy vấn tập hợp

Ví dụ kiểm tra trạng thái của nhiều đơn hàng. Cách chatty là gọi SELECT riêng cho từng order_id. Cách set-based có thể dùng IN, array parameter, table-valued parameter hoặc temporary table tùy DBMS.

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id IN (:id1, :id2, :id3, :id4);
~~~

Với tập ID lớn, không nên tạo một SQL string khổng lồ hoặc vượt giới hạn parameter. Hãy dùng cơ chế truyền danh sách phù hợp của DBMS/driver, temporary table hoặc bulk input.

### 5.2. Dùng EXISTS thay vì hai lượt kiểm tra

Nếu ứng dụng thực hiện:
1. SELECT COUNT(*) để xem có dòng không.
2. SELECT chi tiết nếu count lớn hơn 0.

Có thể truy vấn chi tiết trực tiếp hoặc dùng EXISTS trong cùng SQL logic. Tránh một lượt trao đổi chỉ để xác định điều mà câu truy vấn tiếp theo đã làm rõ.

Ví dụ:

~~~sql
SELECT order_id, status, total
FROM orders
WHERE order_id = :order_id;
~~~

Ứng dụng kiểm tra có result hay không. Nếu cần cờ tồn tại cùng dữ liệu, không cần một COUNT riêng.

### 5.3. Dùng RETURNING/OUTPUT khi phù hợp

Một INSERT có thể trả khóa và dữ liệu vừa tạo trong cùng lượt:

~~~sql
INSERT INTO orders (customer_id, status, total)
VALUES (:customer_id, 'PENDING', :total)
RETURNING order_id, created_at;
~~~

PostgreSQL hỗ trợ RETURNING. SQL Server có OUTPUT; cú pháp và khả năng của MySQL phụ thuộc phiên bản, và thường cần cách lấy generated key riêng. Không giả định cú pháp này dùng chung mọi DBMS.

Lấy kết quả ngay trong statement có thể tránh một SELECT round trip sau INSERT. Hãy kiểm tra driver và transaction semantics.

### 5.4. Batch DML

Batch giúp gửi nhiều thao tác cùng loại trong một lần giao tiếp logic hoặc ít lượt hơn, tùy driver và protocol. Ví dụ JDBC:

~~~java
String sql = """
    INSERT INTO order_items
        (order_id, product_id, quantity, unit_price)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderItem item : items) {
        ps.setLong(1, item.orderId());
        ps.setLong(2, item.productId());
        ps.setInt(3, item.quantity());
        ps.setBigDecimal(4, item.unitPrice());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

Driver có thể gửi batch theo cách khác nhau; không phải mọi driver đều biến batch thành một packet hoặc một statement duy nhất. Một số driver cần cấu hình để rewrite batch thành multi-row insert. Hãy kiểm tra tài liệu driver, số round trips và SQL thực tế trên server.

Batch size quá lớn có thể tạo statement dài, packet lớn, log burst, lock duration dài và rollback cost cao. Benchmark nhiều kích thước batch thay vì chọn số lớn nhất.

## 6. Connection pooling và tái sử dụng kết nối

### 6.1. Vì sao không mở connection cho từng truy vấn?

Tạo connection mới có thể bao gồm DNS, TCP handshake, TLS handshake, authentication, session initialization và cấp phát tài nguyên phía DBMS. Nếu mỗi API request mở rồi đóng connection, chi phí này lặp lại liên tục.

Connection pool giữ sẵn một số kết nối để ứng dụng mượn và trả lại. Việc tái sử dụng giúp giảm setup latency và số lần authentication, đồng thời giới hạn số session DBMS.

### 6.2. Pool quá nhỏ và quá lớn

Pool quá nhỏ:
- Request chờ connection dù DBMS còn khả năng xử lý.
- Pool wait tăng.
- Thread ứng dụng có thể bị giữ lâu.
- Throughput bị giới hạn bởi số connection.

Pool quá lớn:
- DBMS phải quản lý nhiều session.
- Nhiều truy vấn đồng thời tranh chấp CPU, memory, locks và I/O.
- Context switching và queueing tăng.
- Một số workload có thể làm cache và worker pressure tăng.

Số connection tối ưu phụ thuộc DBMS, query duration, transaction mix, CPU, memory và mức concurrency. Không đặt pool size bằng số thread ứng dụng hoặc số CPU một cách máy móc.

### 6.3. Pool sizing theo thời gian giữ connection

Một cách tiếp cận là đo:
- Request rate.
- Thời gian trung bình giữ connection.
- p95/p99 pool acquisition wait.
- Số connection active/idle.
- DB session count và CPU/IO utilization.

Little's Law có thể giúp ước lượng số connection đang bận trung bình bằng throughput nhân thời gian giữ connection. Đây là điểm xuất phát, không phải công thức capacity cuối cùng. Pool cần đủ cho tải đỉnh nhưng không được vượt capacity DBMS.

### 6.4. Connection lifecycle

Pool cần xử lý:
- Idle timeout của firewall/load balancer.
- Server restart và failover.
- Connection bị hỏng hoặc network reset.
- Max lifetime để tránh kết nối quá lâu trong một số môi trường.
- Validation hoặc keepalive phù hợp.
- Leak detection khi code quên trả connection.
- Transaction/session state còn sót lại.

Không chạy SELECT 1 trước mọi truy vấn nếu pool/driver đã có cơ chế health check phù hợp; validation quá thường xuyên cũng tạo round trips. Chọn cách kiểm tra theo hạ tầng và yêu cầu phát hiện connection hỏng.

### 6.5. Proxy và connection multiplexing

Database proxy có thể quản lý connection, pooling, failover hoặc định tuyến. Một số proxy hỗ trợ multiplexing, nhưng transaction đang mở, session variables, temporary tables, prepared statements hoặc advisory locks có thể yêu cầu connection affinity.

Kiểm tra giới hạn và semantics của proxy. Multiplexing giúp giảm số connection backend nhưng có thể làm session behavior phức tạp hơn. Đo latency thêm hop và queue của proxy.

## 7. Fetch size, streaming và kích thước kết quả

### 7.1. Result set lớn cần nhiều lượt truyền

Một SELECT trả về 100.000 dòng có thể không được truyền trong một response duy nhất. DBMS và driver thường chia dữ liệu thành các gói hoặc fetch batches. Nếu fetch size nhỏ, ứng dụng có thể phải thực hiện nhiều lượt lấy dữ liệu hơn.

Ví dụ JDBC có thể cấu hình fetch size:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            processRow(rs);
        }
    }
}
~~~

Ý nghĩa và hiệu quả của setFetchSize phụ thuộc JDBC driver và DBMS. Một số driver mặc định buffer toàn bộ result; một số cần cursor/server-side fetch và transaction phù hợp. Kiểm tra tài liệu driver và memory behavior.

### 7.2. Fetch size quá nhỏ hoặc quá lớn

Fetch size quá nhỏ:
- Nhiều lần fetch.
- Nhiều lượt trao đổi.
- Tăng latency tổng với RTT cao.

Fetch size quá lớn:
- Tăng memory phía client.
- Có thể tạo burst network lớn.
- Tăng thời gian decode và garbage collection.
- Giữ nhiều dữ liệu không cần thiết.

Chọn fetch size theo row width, số dòng, memory budget, driver behavior và network latency. Đo cả thời gian tới dòng đầu tiên (time to first row) và thời gian đọc hết result set.

### 7.3. Streaming và backpressure

Streaming cho phép xử lý từng phần dữ liệu thay vì tải toàn bộ vào RAM. Nhưng nếu consumer xử lý chậm, DBMS connection có thể bị giữ mở lâu, transaction/snapshot có thể kéo dài và server-side cursor có thể giữ tài nguyên.

Cần kiểm soát:
- Tốc độ consumer.
- Thời gian giữ connection.
- Transaction lifetime.
- Cancellation khi client ngừng đọc.
- Backpressure và buffer giới hạn.
- Tác động tới vacuum/version cleanup tùy DBMS.

Không dùng streaming một cách máy móc cho mọi endpoint. Nếu chỉ cần 20 dòng đầu, dùng LIMIT/keyset pagination thường tốt hơn tải toàn bộ.

### 7.4. Giảm payload trước khi tối ưu băng thông

Các cách thường hiệu quả:
- Chọn đúng cột thay vì SELECT *.
- Lọc tại DBMS thay vì tải về rồi lọc ở ứng dụng.
- Dùng pagination hoặc cursor có kiểm soát.
- Tránh lặp dữ liệu lớn do JOIN fan-out.
- Trả projection/DTO phù hợp API.
- Dùng kiểu dữ liệu và định dạng gọn khi có thể.

Nén có thể giảm bytes nhưng tiêu tốn CPU và có overhead. Chỉ bật hoặc điều chỉnh compression sau khi đo bandwidth, CPU và latency. Với payload nhỏ, nén có thể làm chậm hơn.

## 8. Protocol, pipelining và prepared statements

### 8.1. Protocol request-response

Giao thức client-server của DBMS quy định cách gửi query, parameter, result, error và transaction state. Một số thao tác phải chờ phản hồi trước khi gửi bước tiếp theo; một số driver/protocol hỗ trợ pipelining hoặc multiplexing ở mức nhất định.

Hãy phân biệt số SQL statement với số round trips thực tế. Một batch gồm nhiều statement có thể vẫn được gửi trong một lần hoặc nhiều lần tùy driver. Một truy vấn trả nhiều result set có thể cần nhiều message để truyền hết.

### 8.2. Prepared statement

Prepared statement tách cấu trúc SQL khỏi giá trị parameter:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, status FROM orders WHERE customer_id = ?")) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // map row
        }
    }
}
~~~

Lợi ích thường gồm giảm việc tạo SQL string lặp, hỗ trợ bind parameter, bảo vệ khỏi SQL injection khi dùng đúng cách và có thể tái sử dụng plan/statement tùy driver/DBMS.

Prepared statement không nhất thiết giảm một round trip cho mỗi execute. Việc prepare có thể là thao tác riêng hoặc được driver mô phỏng; statement caching và server-side prepare phụ thuộc cấu hình. Hãy đo behavior thực tế.

### 8.3. Pipelining

Pipelining cho phép gửi nhiều lệnh mà không chờ phản hồi của từng lệnh trước, nếu protocol và driver hỗ trợ. Điều này có thể giảm chi phí latency tuần tự. Nhưng:
- Kết quả và lỗi cần được ghép đúng với từng lệnh.
- Transaction order vẫn phải bảo toàn.
- Một lỗi có thể ảnh hưởng các lệnh tiếp theo trong pipeline.
- Không phải driver/DBMS nào cũng hỗ trợ.
- Pipeline không giảm tổng lượng công việc ở DBMS.

Chỉ dùng pipelining khi thư viện hỗ trợ rõ semantics và có benchmark chứng minh lợi ích.

## 9. Transaction design và số lượt trao đổi

### 9.1. Tránh mở transaction rồi chờ bên ngoài

Transaction dài làm connection bị giữ, lock có thể tồn tại lâu và các phiên bản dữ liệu có thể phải được giữ lại. Nếu ứng dụng mở transaction rồi gọi HTTP service, chờ người dùng hoặc xử lý CPU lâu, connection và transaction bị chiếm trong thời gian không cần thiết.

Thực hiện công việc ngoài DB trước khi mở transaction nếu semantics cho phép. Trong transaction, chỉ giữ các thao tác cần tính nguyên tử.

### 9.2. Giảm chatty transaction

Một transaction có 20 statement tuần tự qua mạng xa có thể tích lũy nhiều RTT. Có thể giảm bằng:
- Một statement set-based.
- Batch DML.
- Stored procedure cho logic dữ liệu phù hợp.
- RETURNING/OUTPUT.
- Tái sử dụng kết quả đã đọc trong transaction.
- Loại bỏ SELECT kiểm tra trùng lặp nếu constraint có thể bảo vệ.

Không chuyển tất cả logic vào stored procedure chỉ để giảm round trips. Cần xem khả năng bảo trì, transaction semantics, CPU DBMS và mức độ dùng chung logic.

### 9.3. Batch transaction và kích thước lô

Batch transaction giảm commit count và network exchanges nhưng tăng lượng công việc trong một transaction. Batch quá lớn có thể:
- Giữ lock lâu.
- Tăng log volume và rollback cost.
- Tạo transaction log pressure.
- Tăng memory và result buffering.
- Làm retry tốn kém.
- Gây ảnh hưởng các transaction khác.

Chọn batch size theo độ trễ, throughput, lock duration, log generation và khả năng retry. Với import lớn, có thể chia thành các chunk có checkpoint nghiệp vụ và idempotency key.

### 9.4. Idempotency khi retry

Mạng có thể đứt sau khi DBMS đã commit nhưng trước khi ứng dụng nhận được phản hồi. Ứng dụng không biết chắc transaction đã commit hay chưa. Nếu retry mù quáng, có thể tạo đơn hàng hoặc thanh toán trùng.

Dùng idempotency key, unique constraint, transaction record hoặc cơ chế deduplication phù hợp. Retry phải được thiết kế theo semantics của thao tác, không chỉ dựa vào mã lỗi socket.

## 10. Timeout, retry và network failure

### 10.1. Các loại timeout khác nhau

Cần phân biệt:
- Connection timeout: thời gian tối đa để tạo kết nối.
- Pool acquisition timeout: thời gian tối đa chờ connection từ pool.
- Socket/read timeout: thời gian chờ dữ liệu từ server.
- Query/statement timeout: giới hạn thời gian DBMS thực thi hoặc driver chờ kết quả.
- Transaction timeout: giới hạn thời gian transaction tồn tại nếu framework/DBMS hỗ trợ.
- Idle timeout: đóng kết nối không hoạt động.

Đặt timeout quá ngắn có thể hủy truy vấn hợp lệ trong giờ cao điểm. Timeout quá dài giữ connection và thread quá lâu khi có sự cố. Cần dựa trên SLA và phân phối latency thực tế.

### 10.2. Retry có thể khuếch đại sự cố

Khi DBMS hoặc mạng đang quá tải, nhiều client cùng timeout rồi retry ngay có thể tạo retry storm. Tải tăng khiến latency tiếp tục tăng và nhiều request lại retry.

Dùng:
- Exponential backoff.
- Jitter để tránh retry đồng bộ.
- Giới hạn số lần retry.
- Circuit breaker hoặc admission control phù hợp.
- Retry chỉ với lỗi được xác định là tạm thời.
- Idempotency cho thao tác có side effect.

Không retry lỗi SQL logic, constraint violation hoặc query đã bị hủy vì điều kiện nghiệp vụ không hợp lệ.

### 10.3. Phân biệt lỗi trước và sau commit

Nếu connection mất trước khi DBMS nhận COMMIT, transaction có thể rollback khi session kết thúc. Nếu mất sau khi DBMS commit nhưng trước khi client nhận response, kết quả có thể không xác định từ phía client.

Đối với thao tác quan trọng, cần có cách tra cứu trạng thái bằng transaction/business identifier hoặc idempotency key. Không suy luận rằng client nhận timeout đồng nghĩa transaction chắc chắn thất bại.

### 10.4. TCP retransmission và packet loss

Packet loss gây retransmission và có thể làm latency tăng đáng kể, đặc biệt với request nhỏ cần phản hồi nhanh. Network congestion, MTU mismatch, firewall, NAT hoặc đường truyền không ổn định có thể là nguyên nhân.

Theo dõi retransmission, packet loss, TCP reset, connection reset và latency theo từng hop. Ping thành công không chứng minh đường TCP của DB protocol ổn định hoặc không bị mất gói.

## 11. Đo lường độ trễ end-to-end

### 11.1. Instrumentation ở ứng dụng

Ghi các mốc thời gian:
- Bắt đầu request API.
- Bắt đầu chờ connection pool.
- Nhận connection.
- Gửi statement.
- Nhận metadata/result đầu tiên.
- Đọc xong result set.
- Trả connection về pool.
- Kết thúc API response.

Từ đó có thể tách:
- Pool wait.
- Connection setup nếu có.
- Time to first row.
- Result fetch duration.
- Application mapping/processing.
- Tổng request latency.

Không ghi SQL parameter nhạy cảm hoặc dữ liệu cá nhân vào log chỉ để đo thời gian. Dùng query fingerprint, trace ID và metric tổng hợp phù hợp.

### 11.2. So sánh với số liệu DBMS

DBMS có thể cung cấp query duration, execution plan, wait events, rows read, rows returned, logical reads và I/O time. So sánh thời gian ứng dụng với thời gian DBMS:

- App time cao, DB time thấp: xem pool wait, network, driver, result transfer và client processing.
- App time và DB time đều cao: xem plan, locks, CPU, I/O hoặc memory.
- Time to first row thấp nhưng fetch complete cao: xem result size, fetch size, bandwidth và client decode.
- Latency tăng theo vùng địa lý nhưng DB execution ổn định: xem RTT và network path.

Các metric không phải lúc nào cũng dùng cùng điểm bắt đầu/kết thúc. Cần hiểu cách driver và DBMS định nghĩa duration trước khi trừ hai con số.

### 11.3. Đo RTT từ đúng vị trí

Đo từ cùng host, container, subnet hoặc zone với ứng dụng production. Có thể dùng công cụ network phù hợp để kiểm tra RTT, route, packet loss và TCP connection setup. Tuy nhiên, ping/ICMP có thể bị chặn hoặc ưu tiên khác TCP; nó chỉ là chỉ dấu, không thay thế đo trên kết nối DB thực.

Đo latency đến DB endpoint qua đúng proxy, TLS, firewall và load balancer. Đường đi qua một endpoint test khác có thể không đại diện production.

### 11.4. Distributed tracing

Trace giúp gắn thời gian của API, service call, pool acquisition và DB span vào cùng trace ID. Một trace có thể cho thấy request chờ 70 ms ở pool, 8 ms DB execution và 25 ms đọc result.

Cần kiểm soát sampling và cardinality. Không đưa customer ID, SQL literals hoặc dữ liệu nhạy cảm vào span attributes nếu không có chính sách phù hợp.

### 11.5. Metrics mạng cần theo dõi

Tùy môi trường, có thể theo dõi:
- RTT và latency theo percentile.
- Packet loss và TCP retransmissions.
- TCP resets và connection errors.
- Connection establishment time.
- Bytes sent/received.
- Throughput và bandwidth utilization.
- Interface drops/errors.
- Queueing ở proxy/load balancer.
- TLS handshake duration.
- DNS resolution time.

Metric mạng cần được ghép với pool metrics và DBMS metrics. Một con số RTT trung bình không giải thích toàn bộ tail latency.

## 12. Benchmark round trips và khoảng cách

### 12.1. Benchmark cùng một SQL ở nhiều vị trí

Chạy cùng query, cùng tham số và cùng dữ liệu từ:
- Host gần DB.
- Application subnet.
- Một zone khác.
- Một region khác nếu kiến trúc thực tế có thể như vậy.

Đo pool acquisition, time to first row, fetch complete và API latency. Giữ cùng phiên bản driver, TLS và connection pool nếu muốn so sánh topology.

### 12.2. So sánh chatty và set-based

Tạo hai phiên bản:
- N truy vấn tuần tự cho N entity.
- Một JOIN hoặc batch query lấy cùng dữ liệu.

Đảm bảo hai phiên bản trả cùng kết quả và cùng semantics. Đo số statement, số protocol exchanges nếu quan sát được, bytes truyền, DB CPU, rows read và p95 latency.

Một truy vấn lớn có thể giảm round trips nhưng tăng CPU, result size hoặc lock duration. Phải so sánh toàn bộ chi phí.

### 12.3. Kiểm tra concurrency

Một connection pool có thể hoạt động tốt ở 5 request đồng thời nhưng quá tải ở 100 request. Tăng tải theo bước và quan sát pool wait, DB sessions, CPU, I/O, queue và p95/p99.

Không dùng chỉ một virtual user. Workload phải phản ánh transaction mix và tỷ lệ đọc/ghi thực tế.

### 12.4. Warm-up và cache

Giữ cùng cache state hoặc chạy đủ vòng warm-up trước khi đo. Không so sánh một lần chạy có connection/TLS mới với lần chạy dùng connection pool đã ấm mà không ghi rõ. Đo riêng cold connection setup và steady-state query nếu cả hai đều quan trọng.

### 12.5. Kết quả cần báo cáo

Một benchmark hữu ích nên ghi:
- Topology và vị trí client/DB.
- RTT distribution và network path.
- Driver, protocol, TLS và pool settings.
- Query count và round trips/request.
- Bytes sent/received và rows fetched.
- Pool wait, DB execution và fetch time.
- p50/p95/p99 API latency.
- Throughput và concurrency.
- CPU, memory, I/O và DB waits.
- Kết quả tính đúng đắn trước/sau.

## 13. Ví dụ: API tìm kiếm có latency cao dù SQL nhanh

Giả sử API hiển thị danh sách 30 đơn hàng cùng tên khách hàng và số dòng chi tiết. Trace cho thấy:
- Query lấy danh sách orders: 4 ms DB time.
- Mỗi order truy vấn customer riêng: 30 query × khoảng 3 ms thời gian đi-về.
- Mỗi order lại truy vấn count order_items riêng: thêm 30 query.
- Tổng API latency khoảng 220 ms, trong khi từng query rất nhanh.

Đây là N+1 và chatty access. Có thể cải thiện bằng:
1. JOIN orders với customers để lấy tên khách hàng trong cùng query.
2. GROUP BY order_items theo order_id cho tập 30 đơn hoặc dùng một truy vấn tổng hợp.
3. Dùng DTO projection chỉ lấy cột cần.
4. Giữ pagination ở phía orders trước khi JOIN collection lớn.
5. Kiểm tra plan và index trên customer_id, order_id.
6. Đo lại số statement, rows read, bytes và p95 API latency.

Không nên JOIN trực tiếp order_items rồi phân trang nếu một đơn có nhiều item, vì fan-out có thể làm pagination trên order bị sai hoặc trả ít hơn 30 đơn duy nhất. Có thể dùng CTE/subquery lấy page order trước, rồi join/aggregate phần liên quan.

## 14. Các biện pháp tối ưu theo nguyên nhân

| Dấu hiệu | Hướng xử lý cần đánh giá |
|---|---|
| Pool acquisition wait cao | Điều chỉnh pool theo capacity, rút ngắn thời gian giữ connection, tìm connection leak |
| Nhiều query nhỏ tuần tự | Set-based SQL, JOIN phù hợp, batch, loại bỏ N+1 |
| RTT cao do khác region | Đưa application gần DB, giảm round trips, xem read replica với consistency phù hợp |
| TLS/TCP setup lặp lại | Connection pooling, reuse, session resumption |
| Result fetch chiếm nhiều thời gian | Projection, pagination, fetch size, streaming và giảm payload |
| Bytes lớn, bandwidth bão hòa | Giảm cột/dòng, tránh fan-out, compression sau khi đo CPU |
| Packet loss/retransmission | Điều tra network path, congestion, MTU, firewall và hạ tầng |
| DB time cao | Phân tích execution plan, index, lock, CPU, I/O và memory |
| Retry storm | Backoff, jitter, retry budget, circuit breaker và idempotency |
| Proxy queue cao | Đo thêm hop, backend pool, multiplexing và giới hạn proxy |

Một dấu hiệu có thể có nhiều nguyên nhân. Chỉ áp dụng biện pháp sau khi đã đối chiếu trace, network metrics và DBMS metrics.

## 15. Checklist điều tra và tối ưu kết nối

- [ ] Đã tách pool wait, connection setup, DB execution, result fetch và application processing chưa?
- [ ] Đã đo RTT từ đúng vị trí ứng dụng production chưa?
- [ ] Đã xác định số statement và số round trips cho một API request chưa?
- [ ] Đã tìm N+1 queries, lazy loading hoặc vòng lặp truy vấn chưa?
- [ ] Đã cân nhắc JOIN/set-based SQL/batch để giảm lượt trao đổi chưa?
- [ ] Đã kiểm tra query result size, số cột và bytes truyền chưa?
- [ ] Đã kiểm tra fetch size, streaming và client memory chưa?
- [ ] Đã tái sử dụng connection bằng pool chưa?
- [ ] Pool size có phù hợp với DB capacity và thời gian giữ connection không?
- [ ] Đã đo DNS, TCP/TLS setup khi tạo connection mới chưa?
- [ ] Đã xem proxy, service mesh, VPN và network hop chưa?
- [ ] Đã phân biệt local commit với read replica lag và consistency requirement chưa?
- [ ] Timeout có phù hợp SLA và từng giai đoạn kết nối không?
- [ ] Retry có backoff, jitter, giới hạn và idempotency không?
- [ ] Đã theo dõi packet loss, retransmission, reset và queueing chưa?
- [ ] Đã benchmark cùng topology, driver, TLS, payload và concurrency chưa?
- [ ] Đã xác nhận kết quả SQL và semantics không thay đổi chưa?

## Kết luận

Độ trễ giữa ứng dụng và cơ sở dữ liệu phụ thuộc RTT, khoảng cách địa lý, số lượt trao đổi tuần tự, connection setup, payload, driver, proxy và thời gian chờ ở từng tầng. Với truy vấn nhỏ, round trips có thể chi phối latency; với result set lớn, bandwidth, fetch size và client processing có thể quan trọng hơn.

Hãy đo end-to-end bằng trace, tách pool wait, network, DB execution và result fetch; kiểm tra số query trên mỗi request và loại bỏ N+1/chatty patterns bằng SQL set-based hoặc batch phù hợp. Tái sử dụng connection, đặt pool theo capacity, đưa application gần DB khi hợp lý và thiết kế timeout/retry có idempotency. Mọi thay đổi cần benchmark trên cùng topology và workload, đồng thời xác nhận tính đúng đắn, consistency và p95/p99 của toàn hệ thống.

