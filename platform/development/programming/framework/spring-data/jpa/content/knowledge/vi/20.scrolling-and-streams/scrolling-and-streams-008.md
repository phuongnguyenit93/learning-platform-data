# Đóng Stream, fetch size và thời gian giữ kết nối trong Spring Data JPA

Spring Data JPA có thể trả kết quả truy vấn dưới dạng Java `Stream<T>` để xử lý một tập dữ liệu lớn theo từng phần tử. Cách này hữu ích cho export, đối soát và xử lý dữ liệu hàng loạt, nhưng cần quản lý đúng ba tài nguyên liên quan: Java Stream, JDBC ResultSet/Statement và transaction/persistence context.

Có ba quy tắc quan trọng:

1. **Luôn đóng Stream**, kể cả khi dừng sớm hoặc xử lý phát sinh exception.
2. **Tiêu thụ Stream trong transaction còn mở** vì ResultSet và Statement thường gắn với transaction và connection.
3. **Cấu hình fetch size chưa đủ để bảo đảm streaming**. JPA provider và JDBC driver phải hỗ trợ cơ chế lấy dữ liệu theo lô; cần kiểm thử trên database thực tế.

Một Stream bị bỏ quên có thể giữ connection trong pool. Một Stream được đóng đúng nhưng driver vẫn buffer toàn bộ ResultSet thì vẫn có thể tốn nhiều heap. Fetch size, transaction boundary và thời gian xử lý mỗi hàng phải được thiết kế cùng nhau.

## 1. Stream query trong Spring Data JPA hoạt động qua những lớp nào?

Khi gọi repository method trả về `Stream<T>`, có nhiều lớp tham gia:

- **Java Stream:** cung cấp các thao tác như `filter`, `map`, `forEach`, `findFirst` và `count`.
- **Spring Data JPA:** tạo query và trả về Stream từ JPA provider.
- **JPA provider:** thường là Hibernate, quản lý EntityManager, persistence context và cách đọc kết quả.
- **JDBC driver:** quản lý Statement, ResultSet, fetch size và giao tiếp với database.
- **Database:** thực thi query; tùy driver và cấu hình, dữ liệu có thể được đọc qua cursor hoặc được gửi về client theo cách khác.

Vì vậy, `Stream<T>` là giao diện tiêu thụ kết quả trong Java. Nó không tự bảo đảm database gửi từng hàng một, cũng không tự bảo đảm bộ nhớ luôn ổn định.

### 1.1. Stream khác List ở điểm nào?

| Đặc điểm | `List<T>` | `Stream<T>` |
|---|---|---|
| Cách sử dụng | Nhận collection đã materialize | Tiêu thụ kết quả qua pipeline |
| Vòng đời tài nguyên | Thường kết thúc sau khi query tạo kết quả | Có thể giữ ResultSet/Statement/connection trong lúc đọc |
| Đóng tài nguyên | Không cần đóng List | Phải đóng Stream khi nó gắn với tài nguyên |
| Lấy dữ liệu theo lô | Thường phụ thuộc cách provider materialize collection | Có thể dùng cursor/fetch size nếu provider và driver hỗ trợ |
| Bộ nhớ | Có thể tăng theo toàn bộ số hàng | Có thể giảm, nhưng không được bảo đảm chỉ nhờ kiểu Stream |
| Dùng nhiều lần | Có thể duyệt lại collection | Stream chỉ tiêu thụ một lần |

Một Stream có thể được tiêu thụ bằng terminal operation như `forEach`, `count` hoặc `findFirst`. Sau khi terminal operation chạy, không thể dùng lại Stream đó. Nếu Stream sở hữu tài nguyên ngoài bộ nhớ, hãy đóng nó bằng try-with-resources.

### 1.2. Stream query không phải reactive stream

`java.util.stream.Stream` là API xử lý tuần tự hoặc song song trên JVM. Nó không cung cấp backpressure hoặc mô hình I/O non-blocking như Reactor `Flux`.

Spring Data JPA vẫn dùng JDBC và thường chiếm một connection trong lúc đọc. Không nên chọn `Stream<T>` với kỳ vọng nó biến JPA thành reactive database access.

## 2. Khai báo repository method trả về Stream

Ví dụ dưới đây đọc các đơn hàng từ một thời điểm, sắp xếp theo ID và trả về DTO để export.

### 2.1. DTO chỉ chứa dữ liệu cần dùng

Tạo `OrderExportRow.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderExportRow(
        Long id,
        Instant createdAt,
        BigDecimal total) {
}
~~~

Dùng DTO giúp tránh giữ các entity managed và quan hệ lazy không cần thiết trong persistence context. Với export, thường chỉ cần ID, thời điểm tạo và tổng tiền; không cần tải toàn bộ entity graph.

### 2.2. Repository stream query

Tạo phương thức trong `OrderRepository.java`:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.stream.Stream;
import jakarta.persistence.QueryHint;
import org.hibernate.jpa.HibernateHints;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
           select new com.example.orders.OrderExportRow(
               o.id,
               o.createdAt,
               o.total
           )
           from PurchaseOrder o
           where o.createdAt >= :from
           order by o.id
           """)
    @QueryHints(
        value = @QueryHint(
            name = HibernateHints.HINT_FETCH_SIZE,
            value = "200"
        )
    )
    Stream<OrderExportRow> streamForExport(
            @Param("from") Instant from);
}
~~~

Đây là ví dụ dùng Hibernate. `HibernateHints.HINT_FETCH_SIZE` là hint riêng của Hibernate, không phải fetch-size hint portable của Jakarta Persistence. Giá trị `200` chỉ là điểm bắt đầu để benchmark, không phải con số tối ưu cho mọi query hoặc driver.

Query dùng constructor expression để chỉ lấy các trường cần export. `order by o.id` tạo thứ tự ổn định; nó cũng hữu ích nếu sau này chuyển sang keyset batching.

Nếu không dùng Hibernate, cần xem tài liệu provider tương ứng để cấu hình JDBC fetch size. Không giả định provider khác sẽ hiểu hint `org.hibernate.fetchSize`.

### 2.3. Cấu hình fetch size toàn cục của Hibernate

Có thể đặt fetch size mặc định:

~~~properties
spring.jpa.properties.hibernate.jdbc.fetch_size=200
~~~

Cấu hình này áp dụng ở cấp Hibernate/JDBC cho các statement phù hợp. Nếu chỉ một truy vấn cần streaming, query hint riêng giúp giới hạn phạm vi ảnh hưởng.

Không nên cấu hình đồng thời nhiều giá trị khác nhau rồi đoán giá trị nào thắng. Hãy chọn một cách cấu hình, kiểm tra Statement thực tế và xác nhận driver có dùng nó.

## 3. Luôn đóng Stream bằng try-with-resources

`Stream` triển khai `AutoCloseable` thông qua `BaseStream`. Dùng try-with-resources để bảo đảm `close()` được gọi khi:

- Đã đọc hết kết quả.
- Dừng sớm bằng `findFirst`, `limit` hoặc điều kiện nghiệp vụ.
- Có exception trong lúc xử lý.
- Caller rời khỏi block do return.

Ví dụ:

~~~java
try (Stream<OrderExportRow> rows =
             orderRepository.streamForExport(from)) {
    rows.forEach(this::writeRow);
}
~~~

Đây là mẫu đúng về vòng đời tài nguyên. Không nên chỉ gọi `rows.count()` hoặc `rows.forEach(...)` rồi bỏ Stream mà không đóng.

### 3.1. Không đóng Stream có thể giữ tài nguyên

Nếu Stream đang gắn với JDBC ResultSet và Statement, không đóng nó có thể giữ:

- ResultSet đang mở.
- Statement đang thực thi hoặc còn giữ kết quả.
- Connection được mượn từ connection pool.
- Transaction và persistence context bao quanh truy vấn.

Khi nhiều request cùng để Stream mở, connection pool có thể hết connection dù database chưa quá tải. Những request khác phải chờ connection hoặc timeout.

### 3.2. Dừng sớm vẫn phải đóng

Ví dụ chỉ cần hàng đầu tiên:

~~~java
try (Stream<OrderExportRow> rows =
             orderRepository.streamForExport(from)) {
    return rows.findFirst();
}
~~~

`findFirst()` là terminal operation có thể dừng trước khi đọc hết ResultSet. Try-with-resources vẫn đóng Stream và giải phóng tài nguyên.

Không giả định các thao tác như `limit(100)` tự đóng Stream. Chúng chỉ giới hạn phần tử pipeline phát ra; trách nhiệm đóng tài nguyên vẫn thuộc caller.

### 3.3. Không trả Stream ra khỏi service transaction

Mẫu nguy hiểm:

~~~java
@Transactional(readOnly = true)
public Stream<OrderExportRow> openExport(Instant from) {
    return repository.streamForExport(from);
}
~~~

Khi method trả về, transaction do Spring quản lý có thể kết thúc. Caller bên ngoài mới bắt đầu tiêu thụ Stream, trong khi ResultSet cần transaction/connection đã không còn hợp lệ.

Hãy tiêu thụ và đóng Stream ngay trong method service có transaction. Không trả Stream từ service sang controller hoặc một thread khác để xử lý sau.

## 4. Transaction phải bao trọn thời gian tiêu thụ Stream

Spring Data JPA lưu ý rằng Stream query gắn với tài nguyên như JDBC ResultSet hoặc Statement và thường phụ thuộc transaction xung quanh. Vì thế, transaction cần còn mở trong toàn bộ thời gian đọc Stream.

Ví dụ service:

~~~java
package com.example.orders;

import java.io.BufferedWriter;
import java.io.IOException;
import java.time.Instant;
import java.util.stream.Stream;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderExportService {

    private final OrderRepository orders;

    public OrderExportService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public void exportSince(
            Instant from,
            BufferedWriter writer) throws IOException {

        try (Stream<OrderExportRow> rows =
                     orders.streamForExport(from)) {

            var iterator = rows.iterator();

            while (iterator.hasNext()) {
                OrderExportRow row = iterator.next();

                writer.write(row.id() + ","
                        + row.createdAt() + ","
                        + row.total());
                writer.newLine();
            }
        }
    }
}
~~~

Method service mở transaction trước khi gọi repository, tiêu thụ Stream trong transaction đó và đóng Stream trước khi method kết thúc. Khi method trả về, Spring hoàn tất transaction.

Ví dụ giả định caller đã tạo `BufferedWriter` và chịu trách nhiệm đóng writer. Trong ứng dụng thật, nên ghi file tạm, hoàn tất export thành công rồi mới đổi tên file để tránh công bố file dở dang nếu query hoặc ghi file lỗi.

### 4.1. readOnly không có nghĩa là connection được trả sớm

`@Transactional(readOnly = true)` có thể giúp transaction manager/provider tối ưu đường đọc. Nó không rút ngắn vòng đời transaction và không tự đóng ResultSet khi Stream còn mở.

Connection vẫn cần được giữ trong thời gian query còn tiêu thụ kết quả. Một export kéo dài 20 phút có thể giữ connection trong khoảng thời gian tương tự, dù transaction là read-only.

### 4.2. Lưu ý về Spring proxy

`@Transactional` thường được áp dụng qua Spring AOP proxy. Nếu một method trong cùng class gọi trực tiếp method khác có `@Transactional`, lời gọi nội bộ (self-invocation) thường không đi qua proxy ở chế độ proxy mặc định.

Đặt transaction boundary ở public service method được gọi từ bean khác hoặc tách phần đọc Stream sang một service riêng. Đừng giả định annotation tự mở transaction cho mọi lời gọi nội bộ.

## 5. Fetch size là gì?

Fetch size là gợi ý cho JDBC driver về số hàng nên lấy từ database trong một lượt giao tiếp khi cần đọc thêm kết quả.

Ví dụ:

~~~java
query.setHint(HibernateHints.HINT_FETCH_SIZE, 200);
~~~

Hoặc dùng cấu hình Hibernate:

~~~properties
spring.jpa.properties.hibernate.jdbc.fetch_size=200
~~~

Nếu driver hỗ trợ cursor fetching, fetch size 200 có thể khiến driver lấy khoảng 200 hàng mỗi lượt thay vì buffer toàn bộ kết quả ngay từ đầu.

Fetch size là **JDBC hint**. Theo hợp đồng JDBC, driver có thể bỏ qua hint hoặc xử lý khác tùy database, driver, kiểu ResultSet và cấu hình connection. Cần kiểm tra hành vi thật thay vì chỉ nhìn annotation.

### 5.1. Fetch size không phải page size

| Khái niệm | Ý nghĩa |
|---|---|
| Fetch size | Số hàng driver được gợi ý lấy mỗi lượt từ database |
| Page size | Số hàng ứng dụng yêu cầu trong một trang query |
| SQL LIMIT/FETCH FIRST | Giới hạn số hàng mà query trả về |
| JDBC batch size | Số lệnh ghi được gom trong một batch |
| Hibernate batch fetch size | Số association/proxy có thể được tải theo lô |

Fetch size không giới hạn tổng số hàng query trả về. Nếu query có 2 triệu hàng và fetch size 200, ứng dụng vẫn có thể đọc đủ 2 triệu hàng qua nhiều lượt.

Fetch size cũng không đồng nghĩa với `hibernate.jdbc.batch_size`, vốn liên quan đến batching câu lệnh ghi.

### 5.2. Chọn fetch size như thế nào?

Fetch size nhỏ:

- Buffer phía client nhỏ hơn.
- Có thể cần nhiều lượt giao tiếp hơn.
- Thích hợp khi mỗi hàng lớn hoặc memory budget thấp.

Fetch size lớn:

- Có thể giảm số lượt round trip.
- Buffer mỗi lượt lớn hơn.
- Có thể tăng heap hoặc memory phía driver.

Không có giá trị tối ưu chung. Hãy thử một số mức như 50, 100, 200, 500 hoặc 1000 với kích thước hàng và mạng gần production. Đo thời gian đến hàng đầu tiên, tổng thời gian, heap, số lượt fetch và thời gian giữ connection.

## 6. Fetch size phụ thuộc JDBC driver

Một query hint có thể được chuyển thành `Statement.setFetchSize()`, nhưng driver quyết định có dùng cursor/buffering ra sao.

### 6.1. PostgreSQL JDBC (pgJDBC)

Theo pgJDBC, mặc định driver thu thập toàn bộ kết quả query cùng lúc. Cursor-based fetching có các điều kiện quan trọng:

- Connection không ở chế độ auto-commit.
- ResultSet là `TYPE_FORWARD_ONLY`.
- Query là một statement đơn.
- Fetch size lớn hơn 0.

Nếu không thỏa điều kiện, driver có thể âm thầm quay lại lấy toàn bộ ResultSet. Spring transaction thường tắt auto-commit trong transaction đang hoạt động, nhưng vẫn cần kiểm tra cấu hình connection và statement thực tế.

Ví dụ cấu hình fetch size theo Hibernate:

~~~properties
spring.jpa.properties.hibernate.jdbc.fetch_size=200
~~~

Với PostgreSQL, đừng chỉ kiểm tra rằng Stream có thể duyệt hết kết quả. Hãy kiểm tra rằng cursor mode thực sự được kích hoạt trên driver/version đang dùng.

### 6.2. MySQL Connector/J

MySQL Connector/J mặc định có thể lấy toàn bộ ResultSet về bộ nhớ client. Với cursor-based fetching, driver hỗ trợ:

- `useCursorFetch=true`.
- `defaultFetchSize` lớn hơn 0 hoặc Statement được gọi `setFetchSize()` với giá trị lớn hơn 0.
- Driver tự bật server-side prepared statements khi cursor fetching được dùng vì cơ chế cursor phụ thuộc prepared statement phía server.

Ví dụ JDBC URL:

~~~properties
spring.datasource.url=jdbc:mysql://localhost:3306/shop?useCursorFetch=true&defaultFetchSize=200
~~~

Có một cơ chế streaming row-by-row cũ dùng fetch size đặc biệt `Integer.MIN_VALUE` cùng ResultSet forward-only/read-only. Cơ chế này có các giới hạn riêng, ví dụ phải đọc hết hoặc đóng ResultSet trước khi dùng connection cho truy vấn khác. Trong ứng dụng JPA, ưu tiên cấu hình cursor fetch được driver hỗ trợ và kiểm thử với phiên bản Connector/J thực tế.

### 6.3. Không áp dụng cấu hình của một driver cho mọi database

PostgreSQL, MySQL, MariaDB, Oracle và SQL Server có cách xử lý ResultSet và fetch size khác nhau. Không có một JDBC URL hoặc giá trị hint bảo đảm streaming giống nhau trên tất cả database.

Khi đổi driver hoặc nâng cấp database, hãy chạy lại integration test với lượng dữ liệu lớn và kiểm tra heap/connection metrics.

## 7. Stream entity có thể vẫn tăng bộ nhớ

Một hiểu nhầm phổ biến là Stream luôn có memory usage thấp. Với JPA, entity được tiêu thụ từ Stream vẫn có thể được gắn vào persistence context (first-level cache), giống như entity lấy từ collection query.

Nếu xử lý hàng trăm nghìn entity, persistence context có thể lớn dần dù driver chỉ fetch 200 hàng mỗi lượt.

### 7.1. Ưu tiên DTO projection khi chỉ đọc

Ví dụ query DTO ở phần trước:

~~~java
select new com.example.orders.OrderExportRow(
    o.id,
    o.createdAt,
    o.total
)
from PurchaseOrder o
where o.createdAt >= :from
order by o.id
~~~

DTO không phải entity managed và không cần theo dõi dirty checking. Điều này thường phù hợp cho export, báo cáo và xử lý chỉ đọc.

### 7.2. Nếu phải stream entity

Nếu nghiệp vụ thật sự cần entity:

- Dùng transaction read-only khi phù hợp.
- Không tải quan hệ không cần thiết.
- Tránh sửa entity trong một job chỉ đọc.
- Có thể detach entity sau khi xử lý nếu không còn cần lazy association.
- Nếu dùng `EntityManager.clear()` theo từng nhóm, hãy hiểu nó detach tất cả entity đang managed trong persistence context; không gọi khi còn cần các entity đó hoặc quan hệ lazy của chúng.
- Kiểm thử cách provider xử lý cursor khi persistence context được clear/detach.

Đừng gọi `clear()` theo cảm tính. DTO projection thường dễ dự đoán hơn cho các luồng đọc lớn.

### 7.3. Tránh terminal operation materialize toàn bộ kết quả

Các cách sau có thể đưa toàn bộ kết quả vào bộ nhớ:

~~~java
List<OrderExportRow> all = rows.toList();
~~~

~~~java
Object[] array = rows.toArray();
~~~

Nếu mục tiêu là xử lý tăng dần, hãy ghi/biến đổi từng hàng rồi bỏ tham chiếu sau khi hoàn tất. Những thao tác như `sorted()` có thể cần buffer toàn bộ dữ liệu trước khi phát phần tử đầu tiên; không dùng chúng trên Stream lớn nếu chưa đánh giá chi phí.

### 7.4. Không dùng parallel stream trên JPA cursor

Không gọi `parallel()` cho Stream gắn với persistence context/JDBC cursor. EntityManager và Hibernate Session không được thiết kế để nhiều thread đồng thời thao tác cùng một context. JDBC ResultSet cũng thường là luồng đọc tuần tự.

Nếu cần xử lý song song, hãy đọc từng batch DTO trong transaction ngắn, đóng transaction/connection, rồi gửi batch đã tách khỏi persistence context cho worker xử lý song song.

## 8. Thời gian giữ connection và ảnh hưởng đến connection pool

Một Stream query thường giữ connection trong lúc ResultSet còn mở và transaction chưa kết thúc. Thời gian này gồm:

- Thời gian database thực thi query.
- Thời gian driver lấy các batch tiếp theo.
- Thời gian Java xử lý từng hàng.
- Thời gian ghi file, gửi dữ liệu hoặc chờ hệ thống khác.
- Thời gian transaction hoàn tất và connection được trả về pool.

Ví dụ: query đọc 500.000 hàng chỉ mất 20 giây để database chuẩn bị kết quả, nhưng ứng dụng ghi file chậm trong 15 phút. Connection có thể bị giữ trong gần 15 phút, dù phần lớn thời gian không phải database đang tính toán.

### 8.1. Connection pool có thể cạn dù database còn khỏe

Giả sử pool có 20 connection và 20 export job đều giữ Stream mở. Các request web cần query khác sẽ phải chờ connection. Hệ quả có thể là:

- Connection acquisition timeout.
- Request latency tăng.
- HikariCP báo pending threads.
- Một tác vụ export làm giảm khả năng phục vụ request tương tác.

Tăng pool size không phải cách chữa mặc định. Nếu mỗi export giữ connection quá lâu, pool lớn hơn có thể làm database phải phục vụ quá nhiều truy vấn đồng thời.

### 8.2. Tránh việc chậm không liên quan nằm trong transaction

Không nên gọi API HTTP, gửi email, chờ message broker hoặc thực hiện thao tác người dùng trong lúc đang duyệt Stream. Những thao tác này kéo dài transaction và thời gian mượn connection.

Nếu cần gửi dữ liệu ra hệ thống khác, hãy cân nhắc đọc theo batch DTO, đóng transaction sau mỗi batch rồi xử lý batch bên ngoài. Nếu phải bảo đảm snapshot nhất quán, xác định rõ isolation/snapshot strategy trước khi chia transaction.

### 8.3. Transaction dài có thể giữ snapshot và tài nguyên database

Transaction đọc kéo dài có thể giữ snapshot lâu hơn dự kiến. Tác động cụ thể phụ thuộc database và isolation level; trên một số hệ quản trị, snapshot cũ có thể làm chậm việc dọn phiên bản hàng cũ hoặc tăng áp lực lưu trữ.

Transaction ghi dài còn có thể giữ lock lâu hơn. Vì vậy, không nên để một job đọc/ghi hàng triệu bản ghi chạy trong transaction duy nhất nếu có thể xử lý theo nhóm với semantics phù hợp.

## 9. Khi nào nên dùng Stream, khi nào nên dùng keyset batch?

Stream phù hợp khi:

- Cần duyệt một query lớn theo thứ tự.
- Provider và driver thực sự hỗ trợ incremental/cursor fetching.
- Có thể giữ transaction/connection trong khoảng thời gian chấp nhận được.
- Công việc mỗi hàng nhẹ và không cần truy vấn khác trên cùng connection.
- Có thể bảo đảm Stream luôn được đóng.

Keyset batch thường phù hợp hơn khi:

- Export kéo dài hoặc mỗi hàng cần xử lý chậm.
- Cần trả connection về pool giữa các nhóm.
- Muốn retry theo batch.
- Muốn giới hạn bộ nhớ ở mức rõ ràng.
- Không cần một transaction/snapshot duy nhất cho toàn bộ job, hoặc đã thiết kế cách bảo đảm nhất quán.

### 9.1. Ví dụ keyset pagination theo ID

Repository:

~~~java
@Query("""
       select new com.example.orders.OrderExportRow(
           o.id,
           o.createdAt,
           o.total
       )
       from PurchaseOrder o
       where o.id > :afterId
       order by o.id
       """)
List<OrderExportRow> readNextBatch(
        @Param("afterId") Long afterId,
        Pageable pageable);
~~~

Một reader service tải một batch trong transaction ngắn:

~~~java
@Service
public class OrderBatchReader {

    private static final int BATCH_SIZE = 500;

    private final OrderRepository orders;

    public OrderBatchReader(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public List<OrderExportRow> loadAfter(Long lastId) {
        return orders.readNextBatch(
                lastId,
                PageRequest.of(0, BATCH_SIZE)
        );
    }
}
~~~

Orchestrator không giữ transaction trong toàn bộ vòng lặp:

~~~java
public void exportAll(OrderBatchReader reader) {
    long lastId = 0L; // Ví dụ giả định ID sinh ra luôn dương.

    while (true) {
        List<OrderExportRow> batch = reader.loadAfter(lastId);

        if (batch.isEmpty()) {
            break;
        }

        for (OrderExportRow row : batch) {
            writeRow(row);
            lastId = row.id();
        }
    }
}
~~~

Mỗi lần gọi `loadAfter` đi qua Spring proxy, mở transaction đọc, tải tối đa 500 DTO rồi kết thúc transaction. Orchestrator xử lý batch sau khi reader đã trả về, do đó connection của batch trước được giải phóng trước khi ghi hoặc gọi dịch vụ ngoài.

Đây là ví dụ minh họa. Trong dự án thật, cần dùng ID khởi đầu phù hợp với schema, xử lý lỗi/retry, lưu checkpoint và bảo đảm reader được gọi qua bean proxy. Nếu cần transaction cho từng batch, không đặt một `@Transactional` bao trọn orchestrator.

### 9.2. Keyset tránh chi phí OFFSET tăng dần

Với offset pagination, trang sau có thể yêu cầu database bỏ qua ngày càng nhiều hàng. Keyset dùng điều kiện `id > lastId` kết hợp `ORDER BY id`, thường phù hợp hơn cho việc quét tuần tự tập dữ liệu lớn khi có index trên ID.

Nếu thứ tự dùng nhiều cột, predicate keyset phải so sánh đầy đủ khóa sắp xếp, ví dụ `(createdAt, id)`, và thứ tự phải xác định duy nhất.

### 9.3. Keyset không tự tạo snapshot cố định

Trong lúc job chạy, dữ liệu có thể được thêm hoặc cập nhật. Keyset giảm vấn đề dịch chuyển offset nhưng không tự bảo đảm export phản ánh đúng một thời điểm duy nhất.

Nếu cần tập dữ liệu cố định:

- Ghi nhận high-water mark, ví dụ ID lớn nhất tại lúc bắt đầu, rồi chỉ đọc đến mốc đó.
- Xác định chính sách với hàng bị cập nhật trong lúc job chạy.
- Nếu cần snapshot nhất quán tuyệt đối, chọn transaction/isolation hoặc snapshot mechanism phù hợp database và cân nhắc chi phí giữ snapshot dài.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Connection pool không trả connection | Stream không được đóng | Dùng try-with-resources |
| Stream lỗi sau khi service trả về | Transaction đã kết thúc trước khi caller tiêu thụ | Tiêu thụ Stream bên trong service transaction |
| Heap vẫn tăng dù dùng Stream | Driver buffer toàn bộ hoặc entity tích lũy trong persistence context | Kiểm tra cursor fetch, dùng DTO và đo heap |
| Fetch size không có tác dụng | Driver bỏ qua hint hoặc thiếu điều kiện cursor | Kiểm tra tài liệu driver, autocommit và ResultSet mode |
| PostgreSQL vẫn tải toàn bộ | Autocommit đang bật, fetch size bằng 0 hoặc điều kiện cursor không thỏa | Dùng transaction và fetch size dương; xác minh pgJDBC |
| MySQL vẫn buffer ResultSet | Cursor fetch chưa bật hoặc fetch size không dương | Kiểm tra `useCursorFetch` và `defaultFetchSize`/query hint |
| Request khác chờ connection | Stream xử lý quá lâu và giữ connection | Giảm thời gian xử lý trong transaction hoặc dùng keyset batch |
| Lỗi khi query khác trong lúc đang stream | Driver có thể không cho chạy statement khác trên connection đang có active result | Không query lồng trong vòng lặp; lấy đủ dữ liệu bằng projection/batch |
| LazyInitializationException | Entity/association được truy cập sau khi context đóng hoặc đã detach | Tải trường cần thiết trong query/transaction |
| Dữ liệu trùng hoặc thiếu khi phân trang | Thứ tự không duy nhất hoặc dùng offset trên tập dữ liệu thay đổi | Dùng order duy nhất và keyset phù hợp |
| Export dở dang sau exception | File đích được ghi trực tiếp trước khi job hoàn tất | Ghi file tạm rồi publish/rename sau khi thành công |

## 11. Kiểm thử và quan sát trong môi trường thực tế

Một unit test nhỏ xác nhận repository trả đúng hàng không chứng minh driver đang streaming. Cần integration test với database và JDBC driver thực tế.

### 11.1. Kiểm thử đóng Stream

Ví dụ kiểm tra nội dung query và bảo đảm caller sử dụng try-with-resources:

~~~java
@DataJpaTest
class OrderStreamRepositoryTest {

    @Autowired
    private OrderRepository orders;

    @Test
    void streamReturnsExpectedRows() {
        try (Stream<OrderExportRow> rows =
                     orders.streamForExport(Instant.parse("2026-01-01T00:00:00Z"))) {

            assertThat(rows.map(OrderExportRow::id).toList())
                    .containsExactly(1L, 2L, 3L);
        }
    }
}
~~~

Test giả định dữ liệu fixture có đúng ba đơn hàng với ID và ngày phù hợp. Test này xác nhận nội dung và sử dụng đúng cách đóng Stream; nó chưa chứng minh cursor fetching hoặc memory usage.

### 11.2. Kiểm thử cursor/fetch size

Với integration test trên database thật:

1. Tạo tập dữ liệu lớn hơn nhiều lần fetch size.
2. Dùng transaction read-only bao trọn thời gian tiêu thụ.
3. Xác minh JDBC Statement nhận fetch size mong muốn bằng datasource/driver instrumentation hoặc JDBC proxy.
4. Kiểm tra cấu hình cursor của driver, ví dụ autocommit và ResultSet type với PostgreSQL.
5. Quan sát thời gian đến hàng đầu tiên và các lượt fetch tiếp theo.
6. Đo heap khi số hàng tăng từ vài nghìn lên hàng trăm nghìn.
7. Đo thời gian connection ở trạng thái active và xác nhận connection được trả sau khi Stream đóng/transaction kết thúc.
8. Thử exception và short-circuit để bảo đảm tài nguyên được giải phóng.

Không chỉ dựa vào SQL log. SQL log có thể cho biết câu query đã chạy, nhưng không nhất thiết cho biết driver buffer toàn bộ hay lấy qua cursor.

### 11.3. Theo dõi connection pool

Với HikariCP, quan sát các chỉ số:

- Active connections.
- Idle connections.
- Pending threads đang chờ connection.
- Connection acquisition time.
- Connection usage/hold time.
- Transaction duration.

Có thể bật leak detection threshold trong môi trường phát triển/kiểm thử để phát hiện connection được giữ quá lâu. Đây là công cụ chẩn đoán; nó không thay thế việc đóng Stream và không nên đặt ngưỡng quá thấp trong production vì có thể tạo log cảnh báo nhiễu.

### 11.4. Benchmark nhiều mức fetch size

Chạy cùng một query và cùng dữ liệu với các giá trị fetch size khác nhau, chẳng hạn 50, 100, 200, 500 và 1000. Giữ nguyên các yếu tố khác để so sánh:

- Tổng thời gian đọc.
- Thời gian đến hàng đầu tiên.
- Heap peak và garbage collection.
- Số lượt fetch/round trip nếu driver cung cấp metric.
- Thời gian connection bị giữ.
- Tác động lên request khác khi pool có tải đồng thời.

Chọn giá trị theo workload và driver thực tế. Không tối ưu chỉ dựa trên một lần chạy hoặc dataset quá nhỏ.

## 12. Checklist triển khai

- [ ] Repository method trả `Stream<T>` chỉ dùng cho use case cần đọc tập lớn.
- [ ] Stream được tiêu thụ bên trong service transaction.
- [ ] Stream luôn nằm trong try-with-resources.
- [ ] Không trả Stream qua ranh giới transaction, controller hoặc thread khác.
- [ ] Dùng DTO/projection nếu chỉ cần đọc một số trường.
- [ ] Đã kiểm tra persistence context không tích lũy quá nhiều entity.
- [ ] Fetch size được cấu hình theo provider/driver và đã đo.
- [ ] Đã xác minh driver thực sự dùng cursor/incremental fetching.
- [ ] Với PostgreSQL, đã kiểm tra autocommit, forward-only ResultSet và fetch size dương.
- [ ] Với MySQL Connector/J, đã kiểm tra `useCursorFetch` và fetch size dương.
- [ ] Không gọi API từ xa hoặc chờ tác vụ chậm trong lúc giữ Stream mở.
- [ ] Không chạy parallel stream trên cùng persistence context/cursor.
- [ ] Có phương án keyset batch khi cần giảm thời gian giữ connection.
- [ ] Đã xác định yêu cầu snapshot nhất quán khi dữ liệu thay đổi trong lúc export.
- [ ] Integration test dùng đúng database và JDBC driver production.
- [ ] Đã theo dõi active/idle/pending connections và thời gian giữ connection.

## 13. Tài liệu tham khảo

- [Spring Data JPA — Repository Query Return Types](https://docs.spring.io/spring-data/jpa/reference/repositories/query-return-types-reference.html) — Stream là tài nguyên có thể gắn với ResultSet/Statement; cần transaction bao quanh và phải đóng sau khi dùng.
- [Spring Data Commons — Streaming Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html) — ví dụ Stream query, try-with-resources và lưu ý về việc không bảo đảm incremental fetching.
- [Hibernate JDBC Settings](https://docs.hibernate.org/stable/core/javadocs/org/hibernate/cfg/JdbcSettings.html) — `hibernate.jdbc.fetch_size` và ý nghĩa JDBC fetch-size hint.
- [pgJDBC — Getting Results Based on a Cursor](https://jdbc.postgresql.org/documentation/query/) — điều kiện cursor-based ResultSet và fetch size.
- [MySQL Connector/J — Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html) — `useCursorFetch`, `defaultFetchSize` và server-side prepared statements.
- [MySQL Connector/J — JDBC API Implementation Notes](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-implementation-notes.html) — streaming ResultSet, cursor fetch và giới hạn khi connection còn active result.

`Stream<T>` giúp tổ chức việc đọc tuần tự, nhưng hiệu quả bộ nhớ và vòng đời connection phụ thuộc provider, driver và transaction. Đóng Stream đúng cách, cấu hình fetch size có kiểm chứng và giữ phần xử lý trong transaction ngắn nhất có thể sẽ giúp export ổn định hơn. Với công việc kéo dài hoặc cần gọi dịch vụ ngoài, keyset batch thường cho phép kiểm soát bộ nhớ, retry và thời gian giữ connection rõ ràng hơn.
