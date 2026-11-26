# Đánh giá đường tắt giữa các tầng bằng số đo và ngoại lệ kiến trúc rõ ràng

Trong chương **Hiệu năng và triển khai**, bài học này hướng dẫn cách đánh giá một đường đi tắt giữa các tầng của ứng dụng bằng dữ liệu thực tế, sau đó quyết định có nên cho phép ngoại lệ kiến trúc hay không. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là tổ chức phần mềm theo kiến trúc phân tầng: tầng trình bày, ứng dụng, nghiệp vụ và truy cập dữ liệu có trách nhiệm riêng, đồng thời cần cân bằng khả năng thay đổi với hiệu năng khi hệ thống vận hành.

Khi một endpoint chậm, cách sửa có vẻ nhanh là bỏ qua một tầng: controller gọi thẳng repository, dịch vụ ứng dụng truy cập `JdbcTemplate`, hoặc một module đọc trực tiếp bảng của module khác. Đường đi ngắn hơn có thể giảm một số bước, nhưng cũng có thể bỏ qua kiểm tra quyền, quy tắc nghiệp vụ, transaction, audit, cache hoặc hợp đồng dữ liệu. Hơn nữa, lời gọi giữa các lớp trong cùng tiến trình thường rất nhỏ so với thời gian truy vấn database, gọi mạng, serialize hoặc chờ khóa. Vì vậy, không thể kết luận một tầng là nguyên nhân gây chậm chỉ bằng cách đếm số lớp.

Một quyết định tốt cần trả lời ba câu hỏi: **điều gì đang thực sự chậm, giải pháp nào cải thiện số đo, và ngoại lệ nào được phép tồn tại với giới hạn rõ ràng?** Ngoại lệ có thể hợp lý trong một số đường đọc chuyên biệt, nhưng phải có bằng chứng, phạm vi, chủ sở hữu, kiểm thử bảo vệ và thời điểm xem xét lại.

Sau bài học, bạn có thể:

- Phân biệt đường đi tắt thực sự với tối ưu hóa bên trong một tầng.
- Đo bottleneck bằng metric, trace, profiler và benchmark phù hợp.
- So sánh lợi ích hiệu năng với chi phí về nghiệp vụ, bảo mật, transaction và bảo trì.
- Ưu tiên tối ưu truy vấn, projection, batching hoặc cache trước khi bỏ qua một ranh giới.
- Xác định điều kiện cho phép ngoại lệ kiến trúc và ghi lại quyết định có thể kiểm tra.
- Dùng kiểm thử kiến trúc và số đo sau triển khai để ngăn ngoại lệ lan rộng.

## 1. Đường tắt giữa các tầng là gì?

Trong kiến trúc phân tầng, một đường đi thông thường có thể là:

~~~mermaid
flowchart TD
    C[Presentation: Controller] --> A[Application: Use case]
    A --> D[Domain: Quy tắc nghiệp vụ]
    A --> P[Data access port]
    P --> R[Persistence adapter]
    R --> DB[(Database)]
~~~

Một đường tắt xuất hiện khi thành phần gọi bỏ qua trách nhiệm hoặc hợp đồng của một tầng. Ví dụ, controller gọi trực tiếp JPA repository để đọc entity và tự quyết định cách cập nhật trạng thái đơn hàng. Hoặc dịch vụ ứng dụng tự mở JDBC connection để chạy một câu SQL mà không đi qua adapter dữ liệu được thiết kế.

Không phải mọi lời gọi trực tiếp đều là đường tắt xấu. Một service gọi repository là quan hệ bình thường trong nhiều kiến trúc phân tầng. Một query adapter dùng SQL projection thay vì ORM entity cũng có thể là tối ưu hóa hợp lệ bên trong tầng truy cập dữ liệu. Cần phân biệt:

- **Tối ưu bên trong ranh giới:** thay câu SQL, thêm chỉ mục, dùng projection, batching hoặc cache mà consumer vẫn dùng cùng hợp đồng.
- **Thay đổi hợp đồng hoặc luồng tầng:** bỏ qua một tầng, gọi trực tiếp thành phần thuộc tầng khác hoặc làm lộ kiểu dữ liệu nội bộ.
- **Ngoại lệ có chủ đích:** một luồng cụ thể được phép đi theo đường khác vì có bằng chứng và điều kiện bảo vệ rõ ràng.

Các tầng là ranh giới logic; chúng có thể chạy trong cùng tiến trình. Không nên giả định rằng mỗi lần gọi qua một tầng đều tạo thêm một network hop. Tách tầng thành package, module hay tiến trình là các quyết định khác nhau và cần đo chi phí đúng theo cách triển khai thực tế.

## 2. Vì sao không nên tối ưu bằng cảm giác?

Giả sử endpoint `GET /orders/{id}` có độ trễ p95 là 900 ms. Nhóm phát triển nhận thấy request đi qua controller, service, mapper, repository và adapter, rồi đề xuất bỏ service để controller gọi repository trực tiếp. Nhưng 900 ms có thể chủ yếu đến từ:

- Một truy vấn ORM tải nhiều quan hệ lazy và gây N+1 query.
- Database phải quét toàn bảng vì thiếu chỉ mục phù hợp.
- Endpoint gọi một dịch vụ bên ngoài tuần tự.
- Response chứa quá nhiều dữ liệu hoặc serialize một graph entity lớn.
- Pool connection cạn, thread phải chờ hoặc có transaction giữ khóa lâu.
- Một cache miss xảy ra thường xuyên hoặc cache key không phù hợp.

Nếu thời gian thực thi method service chỉ chiếm 0,2 ms, bỏ nó không thể giải quyết phần lớn độ trễ. Nếu service đang thực hiện kiểm tra quyền hoặc áp dụng transaction, bỏ nó còn có thể tạo lỗi chức năng và bảo mật.

Đếm số dòng code, số package hoặc số lần gọi method không thay thế được phép đo. Hãy đo theo luồng người dùng thực tế, xác định phần thời gian tiêu tốn và tìm nguyên nhân có thể kiểm chứng.

## 3. Thiết lập baseline trước khi thay đổi

Baseline là số đo đại diện cho hành vi hiện tại, được thu thập trước khi tối ưu. Cần xác định rõ:

1. **Kịch bản:** endpoint hoặc ca sử dụng nào, với dữ liệu và thao tác nào?
2. **Tải:** bao nhiêu request đồng thời, tốc độ đến, kích thước dữ liệu và tỷ lệ đọc/ghi?
3. **Môi trường:** phiên bản ứng dụng, cấu hình JVM, database, network, cache và phần cứng nào?
4. **Chỉ số:** độ trễ, throughput, tỷ lệ lỗi, CPU, bộ nhớ, GC, connection pool, số query và thời gian database.
5. **Phân vị:** p50, p95, p99 và giá trị tối đa khi phù hợp; không chỉ nhìn trung bình.

Ví dụ bảng baseline:

| Chỉ số | Trước tối ưu | Mục tiêu minh họa |
|---|---:|---:|
| Throughput | 120 request/giây | Ít nhất 150 request/giây |
| Latency p50 | 110 ms | Không tăng đáng kể |
| Latency p95 | 900 ms | Dưới 400 ms |
| Latency p99 | 1.800 ms | Dưới 800 ms |
| Tỷ lệ lỗi | 0,3% | Không tăng |
| Số query trung bình/request | 38 | Dưới 5 với kịch bản này |

Các số liệu trên chỉ là ví dụ để minh họa cách đặt mục tiêu. Mục tiêu thật phải dựa trên SLO, trải nghiệm người dùng và tải của hệ thống. Không nên chọn mục tiêu chỉ để làm cho một thay đổi trông có vẻ thành công.

### Đo phân vị thay vì chỉ đo trung bình

Trung bình có thể che khuất một nhóm request rất chậm. Nếu phần lớn request mất 100 ms nhưng một phần nhỏ mất 2 giây, p50 có thể vẫn tốt trong khi p99 làm trải nghiệm không ổn định. Với endpoint quan trọng, hãy theo dõi p95/p99 theo route hoặc loại ca sử dụng và quan sát theo thời gian.

Khi so sánh trước và sau, dùng cùng cách tạo tải, cùng phân phối dữ liệu và môi trường tương đương. Ghi lại cả tỷ lệ lỗi và tài nguyên tiêu thụ; một giải pháp làm p95 tốt hơn nhưng tăng CPU gấp đôi hoặc gây lỗi dưới tải cao chưa chắc là tối ưu.

## 4. Dùng trace và profiler để tìm đúng bottleneck

### Distributed tracing và span theo tầng

Trace giúp nhìn thấy thời gian của một request qua các thành phần. Với ứng dụng có instrumentation phù hợp, có thể quan sát span cho controller, use case, repository, truy vấn SQL và lời gọi dịch vụ ngoài.

~~~mermaid
flowchart LR
    A[Controller và mapping<br/>8 ms] --> B[Application use case<br/>18 ms]
    B --> C[Database query<br/>620 ms]
    C --> D[External service<br/>180 ms]
    D --> E[Serialization và response<br/>24 ms]
~~~

Trong ví dụ, phần lớn thời gian nằm ở database và dịch vụ ngoài. Tối ưu vài lời gọi method giữa controller và service không có khả năng tạo khác biệt lớn. Có thể cần kiểm tra kế hoạch thực thi SQL, index, connection pool hoặc cách gọi dịch vụ ngoài.

Khi trace qua nhiều tiến trình, cần correlation/trace context để nối span. Với tác vụ bất đồng bộ, message hoặc scheduler, phải truyền context qua metadata hoặc cơ chế instrumentation phù hợp; không giả định thread-local của request sẽ tự đi theo sang worker.

### Profiling JVM

Profiler giúp tìm nơi CPU, bộ nhớ hoặc thời gian chờ được tiêu thụ. Với Java, Java Flight Recorder (JFR) và Java Mission Control có thể giúp quan sát:

- Hot method và mức sử dụng CPU.
- Allocation rate, object sống lâu và áp lực garbage collection.
- Thread contention, monitor lock và thời gian chờ.
- Socket, file I/O và sự kiện liên quan đến runtime.

Nếu CPU cao, tìm hot method hoặc thuật toán tốn kém. Nếu CPU thấp nhưng latency cao, kiểm tra I/O, connection pool, khóa và dịch vụ phụ thuộc. Nếu GC thường xuyên, xem allocation, object graph và kích thước heap trước khi đổi cấu trúc tầng.

Profiler có overhead và cách thu thập khác nhau. Nên chọn cấu hình phù hợp, đo trên môi trường gần production và so sánh với baseline. Không suy luận từ một ảnh chụp profiler ngắn hoặc một lần chạy không đại diện.

### Đo database riêng

Kiểm tra số câu SQL, thời gian từng truy vấn, số hàng đọc/ghi, kế hoạch thực thi và mức chờ khóa. Công cụ `EXPLAIN` hoặc `EXPLAIN ANALYZE` tùy database có thể cho biết truy vấn đang dùng index hay quét bảng. Cần thận trọng với lệnh phân tích có thực thi truy vấn thật hoặc tạo tải đáng kể trên production.

Một truy vấn chậm có thể được cải thiện bằng index, thay join, projection, pagination hoặc giảm số lần gọi. Trước khi bỏ tầng ứng dụng, hãy xác minh rằng bottleneck thực sự nằm ở đường gọi tầng đó.

## 5. So sánh các phương án tối ưu theo chi phí và rủi ro

Khi đã biết bottleneck, hãy so sánh các phương án từ ít xâm lấn đến nhiều xâm lấn:

| Phương án | Ví dụ | Ảnh hưởng ranh giới | Rủi ro cần kiểm tra |
|---|---|---|---|
| Tối ưu truy vấn trong adapter | Thêm index, sửa join, tránh N+1 | Giữ nguyên hợp đồng tầng | Index tăng chi phí ghi; query plan khác theo dữ liệu. |
| Projection/read model | Chỉ lấy cột cần cho màn hình | Giữ port đọc, giảm tải ORM | Phải đồng bộ mapping và quyền truy cập dữ liệu. |
| Batching | Gom nhiều lần ghi hoặc đọc thành chunk | Giữ ca sử dụng nhưng thay cách thực hiện | Transaction lớn, lỗi một phần, bộ nhớ và retry. |
| Cache | Cache kết quả đọc theo key | Có thể giữ nguyên API | Stale data, invalidation, quyền truy cập và stampede. |
| Xử lý bất đồng bộ | Đưa công việc dài vào queue | Thay đổi hợp đồng thời gian phản hồi | Eventual consistency, retry và idempotency. |
| Thay đổi luồng tầng | Bỏ qua use case hoặc gọi trực tiếp adapter | Tác động kiến trúc rõ rệt | Bỏ sót kiểm tra, transaction, audit, cache hoặc validation. |

Không phải phương án ít xâm lấn luôn tốt hơn; có trường hợp cần thay đổi lớn. Nhưng hãy chọn giải pháp có lợi ích đo được và tổng chi phí phù hợp, bao gồm chi phí vận hành và bảo trì trong tương lai.

## 6. Ví dụ: tối ưu truy vấn mà vẫn giữ hợp đồng tầng

Giả sử màn hình danh sách đơn hàng chỉ cần mã đơn, thời gian tạo và tổng tiền. Repository hiện tại tải toàn bộ entity cùng các quan hệ không cần thiết, gây nhiều query và serialize graph lớn.

Thay vì để controller truy cập thẳng `JpaRepository`, có thể giữ use case đọc và tối ưu adapter bằng projection:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record OrderSummary(
        UUID id,
        Instant createdAt,
        BigDecimal total
) {}

public interface OrderSummaryReader {
    List<OrderSummary> findRecent(int limit);
}

public interface FindRecentOrders {
    List<OrderSummary> execute(int limit);
}
~~~

Use case điều phối có thể kiểm tra giới hạn và gọi port đọc:

~~~java
import org.springframework.stereotype.Service;

@Service
class FindRecentOrdersService implements FindRecentOrders {
    private final OrderSummaryReader reader;

    FindRecentOrdersService(OrderSummaryReader reader) {
        this.reader = reader;
    }

    @Override
    public List<OrderSummary> execute(int limit) {
        if (limit < 1 || limit > 200) {
            throw new IllegalArgumentException("Limit không hợp lệ");
        }
        return reader.findRecent(limit);
    }
}
~~~

Adapter JDBC chỉ truy vấn những cột cần thiết:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
class JdbcOrderSummaryReader implements OrderSummaryReader {
    private final JdbcTemplate jdbc;

    JdbcOrderSummaryReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<OrderSummary> findRecent(int limit) {
        return jdbc.query("""
                select id, created_at, total
                from orders
                order by created_at desc
                limit ?
                """, (rs, rowNum) -> new OrderSummary(
                rs.getObject("id", java.util.UUID.class),
                rs.getTimestamp("created_at").toInstant(),
                rs.getBigDecimal("total")), limit);
    }
}
~~~

Controller tiếp tục gọi hợp đồng use case:

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderQueryController {
    private final FindRecentOrders findRecentOrders;

    OrderQueryController(FindRecentOrders findRecentOrders) {
        this.findRecentOrders = findRecentOrders;
    }

    @GetMapping
    List<OrderSummary> recent(
            @RequestParam(defaultValue = "50") int limit) {
        return findRecentOrders.execute(limit);
    }
}
~~~

Ví dụ giả định database hỗ trợ cú pháp `LIMIT ?`; cú pháp phân trang và cách ánh xạ UUID/timestamp cần điều chỉnh theo hệ quản trị. Các import, kiểu dữ liệu và API có thể cần bổ sung theo phiên bản Java/Spring của dự án. Điều quan trọng là consumer vẫn gọi hợp đồng ứng dụng, adapter tối ưu câu truy vấn và không trả JPA entity ra tầng trình bày.

Sau khi triển khai, đo lại số query, thời gian SQL, p95/p99, allocation và tải database. Nếu projection làm số query giảm từ 38 xuống 2 và p95 giảm rõ rệt mà không đổi hợp đồng, không cần tạo ngoại lệ bỏ qua tầng.

## 7. Khi nào có thể chấp nhận một đường tắt?

Một ngoại lệ có thể được cân nhắc khi đồng thời đáp ứng các điều kiện:

1. Có số đo lặp lại cho thấy đường đi hiện tại gây chi phí đáng kể đối với một SLO hoặc yêu cầu hiệu năng cụ thể.
2. Đã xem xét giải pháp giữ nguyên ranh giới như tối ưu SQL, projection, batching, cache hoặc giảm dữ liệu trả về; nếu không chọn, phải giải thích lý do.
3. Đường tắt có phạm vi nhỏ, một mục đích rõ và không tạo ra phụ thuộc ngầm cho các luồng khác.
4. Các quy tắc nghiệp vụ, quyền truy cập, tenant isolation, audit và tính nhất quán vẫn được bảo đảm ở nơi có trách nhiệm.
5. Có người sở hữu, kiểm thử bảo vệ và điều kiện xem xét lại khi hệ thống hoặc tải thay đổi.

Ví dụ có thể cân nhắc là endpoint đọc danh sách thẻ sản phẩm công khai với lưu lượng rất lớn. Endpoint chỉ đọc một projection, không thực hiện chuyển trạng thái, không cần điều phối nhiều nguồn và đã có cơ chế xác thực/ủy quyền phù hợp ở ranh giới. Một adapter truy vấn chuyên biệt có thể được phép phục vụ trực tiếp controller thông qua một hợp đồng read-only được công bố. Ngoại lệ này phải được giới hạn cho endpoint và kiểu dữ liệu cụ thể; không mở quyền cho controller truy cập mọi repository hoặc entity.

Không nên chấp nhận đường tắt nếu nó bỏ qua kiểm tra quyền hoặc quy tắc miền quan trọng, tạo khả năng ghi dữ liệu không nhất quán, lộ entity nội bộ, phá transaction, làm mất audit hoặc khiến nhiều module phụ thuộc vào schema riêng của nhau. Hiệu năng tốt hơn không bù được dữ liệu sai hoặc lỗ hổng bảo mật.

## 8. Ví dụ ngoại lệ đọc có kiểm soát

Giả sử một endpoint catalog công khai chỉ cần danh sách thẻ hiển thị. Một query port chuyên biệt có thể trả projection bất biến:

~~~java
import java.util.List;
import java.util.UUID;

public record CatalogCard(UUID id, String title, String thumbnailUrl) {}

public interface FeaturedCatalogReader {
    List<CatalogCard> findVisibleCards(int limit);
}
~~~

Controller sử dụng trực tiếp query port theo ngoại lệ đã được phê duyệt:

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
class FeaturedCatalogController {
    private final FeaturedCatalogReader reader;

    FeaturedCatalogController(FeaturedCatalogReader reader) {
        this.reader = reader;
    }

    @GetMapping("/featured")
    List<CatalogCard> featured(
            @RequestParam(defaultValue = "20") int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Limit không hợp lệ");
        }
        return reader.findVisibleCards(limit);
    }
}
~~~

Đây là đường ngắn từ presentation tới read-only query port, bỏ qua một lớp điều phối ứng dụng tổng quát. Adapter vẫn nằm sau một hợp đồng nhỏ, chỉ trả projection, chỉ đọc và không công bố entity hoặc `JdbcTemplate`. Trước khi dùng mẫu này, nhóm cần xác định rõ ai kiểm tra quyền, quy tắc hiển thị, lọc tenant và giới hạn dữ liệu. Nếu các điều kiện đó có logic ứng dụng đáng kể, nên đặt lại một query use case để điều phối chúng.

Ngoại lệ này không cho phép dùng cùng đường gọi để cập nhật catalog, thay đổi giá hoặc thực hiện nghiệp vụ. Các thao tác ghi tiếp tục đi qua ca sử dụng có trách nhiệm kiểm tra quyền và invariant. Nếu sau này endpoint cần phối hợp nhiều nguồn, kiểm tra chính sách phức tạp hoặc áp dụng cache theo actor, ngoại lệ cần được xem xét lại.

## 9. Ghi lại ngoại lệ kiến trúc

Một ngoại lệ không nên chỉ tồn tại trong lời nói hoặc comment rời rạc. Hãy ghi lại bằng một Architecture Decision Record (ADR) hoặc hồ sơ quyết định tương đương. Nội dung tối thiểu:

| Trường | Nội dung cần ghi |
|---|---|
| Bối cảnh | Luồng nào chậm, ai bị ảnh hưởng và SLO nào chưa đạt? |
| Bằng chứng | Baseline, trace, profiler, query plan, tải thử và thời điểm đo. |
| Phương án đã xét | Các tối ưu giữ nguyên ranh giới và lý do chọn/bỏ. |
| Quyết định | Đường tắt cụ thể, module/lớp được phép gọi và hợp đồng được dùng. |
| Bảo vệ | Quyền, validation, transaction, audit, tenant, giới hạn dữ liệu và kiểm thử. |
| Chủ sở hữu | Nhóm hoặc người chịu trách nhiệm duy trì ngoại lệ. |
| Điều kiện kết thúc | Chỉ số hoặc thay đổi nào khiến ngoại lệ phải được gỡ bỏ hay thiết kế lại? |
| Ngày xem xét | Mốc đánh giá lại hoặc sự kiện kích hoạt việc xem xét. |

Ví dụ nội dung quyết định:

~~~text
ADR: Cho phép FeaturedCatalogController gọi FeaturedCatalogReader trực tiếp

Bối cảnh:
- Endpoint /catalog/featured có p95 420 ms ở tải mục tiêu.
- Trace cho thấy 70% thời gian nằm trong bước điều phối query không cần thiết.
- Endpoint chỉ đọc một projection công khai.

Quyết định:
- Cho phép controller này gọi FeaturedCatalogReader.
- Chỉ trả CatalogCard; không expose entity hoặc repository tổng quát.
- Giới hạn limit tối đa 100; giữ lọc trạng thái hiển thị và tenant theo chính sách.

Bảo vệ:
- Kiểm thử quyền và lọc dữ liệu.
- Architecture test chỉ allowlist dependency này.
- Theo dõi p95, tỷ lệ lỗi và query time sau triển khai.

Xem xét lại:
- Đánh giá sau 90 ngày hoặc khi endpoint thêm nghiệp vụ/nguồn dữ liệu mới.
~~~

Các số liệu và thời hạn trên chỉ là ví dụ. ADR cần trỏ tới dữ liệu đo thực tế và người chịu trách nhiệm cụ thể. Không ghi thông tin nhạy cảm, secret hoặc dữ liệu khách hàng vào tài liệu quyết định.

## 10. Dùng kiểm thử kiến trúc để giữ ngoại lệ trong giới hạn

Kiểm thử kiến trúc giúp phát hiện phụ thuộc không được phép khi code thay đổi. Ví dụ, quy tắc mặc định có thể cấm controller phụ thuộc package persistence, sau đó chỉ cho phép một dependency đã được ghi nhận:

~~~java
// Pseudocode minh họa quy tắc; tên package và API phụ thuộc dự án.
noClasses()
    .that().resideInAPackage("..presentation..")
    .should().dependOnClassesThat()
    .resideInAPackage("..persistence..")
    .allowDependency(
        "..presentation.catalog.FeaturedCatalogController",
        "..persistence.catalog.FeaturedCatalogReader");
~~~

Đoạn trên là pseudocode, không phải cú pháp ArchUnit có thể chạy nguyên trạng. Trong dự án Java, có thể dùng ArchUnit hoặc công cụ tương đương để mô tả quy tắc và allowlist cụ thể. Hãy giới hạn ngoại lệ theo lớp và interface cần thiết, tránh whitelist cả package `presentation` hoặc `persistence` vì như vậy ngoại lệ dễ lan rộng.

Ngoài kiểm thử dependency, cần có kiểm thử hành vi để bảo đảm đường tắt không bỏ sót:

- Quyền truy cập và tenant isolation.
- Điều kiện lọc dữ liệu được phép hiển thị.
- Giới hạn phân trang và kích thước kết quả.
- Cách xử lý lỗi, timeout và database không sẵn sàng.
- Tính nhất quán khi dữ liệu thay đổi trong lúc đọc.

Một kiểm thử kiến trúc chỉ xác nhận đường phụ thuộc được cho phép; nó không chứng minh endpoint đúng nghiệp vụ hoặc an toàn. Cần kết hợp unit test, integration test và kiểm tra hiệu năng.

## 11. Đo lại sau tối ưu và theo dõi khi triển khai

Sau khi thay đổi, chạy lại đúng kịch bản baseline và so sánh cùng nhóm chỉ số. Không chỉ kiểm tra một request đơn lẻ. Cần có:

- Tải ổn định và tải đỉnh gần với thực tế.
- Độ trễ p50/p95/p99, throughput và tỷ lệ lỗi.
- CPU, memory, allocation/GC, thread và connection pool.
- Số query, query time, cache hit rate và tài nguyên database.
- Hành vi khi dependency chậm hoặc mất kết nối.

Nếu p95 giảm nhưng p99 tăng mạnh, hãy tìm nguyên nhân ở request hiếm hoặc tranh chấp tài nguyên. Nếu throughput tăng nhưng lỗi tăng, thay đổi chưa đáp ứng mục tiêu. Nếu latency giảm nhờ cache nhưng dữ liệu cũ hoặc sai quyền, đó không phải thành công.

Triển khai có thể dùng canary hoặc rollout từng phần để quan sát hành vi trước khi mở rộng. Đặt ngưỡng rollback hoặc dừng rollout dựa trên SLO và error budget. Nếu ngoại lệ tạo ra lợi ích nhỏ hơn dự kiến hoặc gây chi phí bảo trì lớn, hãy quay lại thiết kế có ranh giới rõ hơn.

## 12. Microbenchmark và benchmark hệ thống

JMH hữu ích khi cần đo một đoạn code Java nhỏ, ví dụ so sánh hai cách chuyển đổi object hoặc hai thuật toán trong bộ nhớ. Nó cần warmup, nhiều lần đo, fork phù hợp và tránh dead-code elimination. Một microbenchmark không thể đại diện cho latency end-to-end có database, network, thread pool và tải đồng thời.

Với endpoint hoặc ca sử dụng, hãy dùng load test và quan sát trên môi trường gần production. Benchmark phải có dữ liệu đủ đại diện, cache state rõ ràng, JVM warmup và cách tạo tải không làm client generator trở thành bottleneck. Ghi lại phiên bản code, cấu hình, dataset và công cụ để có thể lặp lại.

Không dùng một lần chạy local làm bằng chứng duy nhất để bỏ qua một tầng. Nếu kết quả biến động lớn, hãy tìm hiểu nguyên nhân biến động trước khi đưa ra quyết định kiến trúc.

## 13. Khi nào cần gỡ bỏ ngoại lệ?

Ngoại lệ cần được xem xét lại khi:

- SLO đã đạt sau khi tối ưu ở tầng khác hoặc tải hệ thống thay đổi.
- Endpoint phát sinh thêm quy tắc nghiệp vụ, quyền hoặc tác dụng phụ.
- Nhiều consumer khác bắt đầu dùng đường tắt và tạo phụ thuộc mới.
- Hợp đồng read-only không còn đủ, phải trả entity hoặc truy cập thêm dữ liệu nội bộ.
- Chi phí bảo trì, kiểm thử hoặc xử lý sự cố lớn hơn lợi ích hiệu năng.
- Công nghệ lưu trữ hoặc kiến trúc triển khai thay đổi khiến lý do ban đầu không còn đúng.

Gỡ ngoại lệ cũng là một công việc kỹ thuật: chuyển consumer về hợp đồng chuẩn, xóa allowlist, cập nhật ADR và đo lại để xác nhận hiệu năng vẫn đáp ứng mục tiêu. Không để một ngoại lệ được coi là vĩnh viễn chỉ vì nó từng giúp giải quyết một bottleneck.

## 14. Tự rà soát trước khi cho phép đường tắt

1. Có số đo nào chứng minh tầng hoặc lời gọi đang bị bỏ qua là nguyên nhân đáng kể không?
2. Đã kiểm tra trace, profiler, query plan và các phụ thuộc bên ngoài chưa?
3. Có thể đạt mục tiêu bằng cách tối ưu bên trong tầng, projection, batching hoặc cache không?
4. Đường tắt bỏ qua trách nhiệm nào: quyền, validation, transaction, audit, cache hay invariant?
5. Ai sở hữu hợp đồng và adapter mới? Phạm vi consumer được phép dùng là gì?
6. Có ADR ghi bằng chứng, quyết định, bảo vệ và điều kiện xem xét lại không?
7. Kiểm thử kiến trúc có allowlist hẹp và kiểm thử hành vi có bảo vệ quy tắc không?
8. Đã đo lại p95/p99, throughput, lỗi và tài nguyên sau thay đổi chưa?
9. Có điều kiện rollback hoặc gỡ ngoại lệ nếu lợi ích không đạt kỳ vọng không?

## Kết luận

Đường tắt giữa các tầng chỉ nên được cân nhắc sau khi số đo cho thấy một bottleneck thực sự và các tối ưu giữ nguyên hợp đồng không đủ đáp ứng mục tiêu. Hãy dùng trace, profiler, benchmark và tải đại diện để tìm nguyên nhân, rồi chọn giải pháp có lợi ích rõ với rủi ro chấp nhận được. Nếu cần ngoại lệ, giới hạn nó vào một luồng cụ thể, giữ các bảo đảm về nghiệp vụ và bảo mật, ghi quyết định cùng chủ sở hữu và điều kiện xem xét lại, đồng thời bảo vệ bằng kiểm thử kiến trúc và đo lường sau triển khai. Nhờ vậy, hiệu năng được cải thiện mà cấu trúc phân tầng vẫn có thể được hiểu, kiểm tra và duy trì.
