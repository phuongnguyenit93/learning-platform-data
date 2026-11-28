# Bookmark và vai trò của Neo4jBookmarkManager

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích bookmark biểu diễn trạng thái nào của Neo4j và vì sao nó hỗ trợ causal consistency.
- Phân biệt bookmark với transaction, session, lock và dữ liệu nghiệp vụ.
- Mô tả cách Neo4j Java Driver quản lý bookmark trong một session và giữa nhiều session.
- Hiểu vì sao Spring Data Neo4j (SDN) thường tự quản lý bookmark mà không cần cấu hình riêng.
- Sử dụng Neo4jBookmarkManager để tạo, nhận bookmark khởi tạo và vô hiệu hóa bookmark management khi có lý do phù hợp.
- Capture bookmark sau commit và seed bookmark khi ứng dụng khởi động hoặc chuyển tiếp công việc.
- Áp dụng bookmark cho ứng dụng imperative và reactive.
- Nhận biết chi phí, giới hạn và lỗi cấu hình thường gặp.

## 1. Bookmark giải quyết vấn đề gì?

Neo4j có thể chạy dưới dạng một instance đơn hoặc một cluster. Trong cluster, transaction ghi được thực hiện trên primary và thay đổi sau đó được truyền tới các thành viên khác. Một truy vấn đọc được định tuyến đến một thành viên chưa nhận thay đổi mới nhất có thể nhìn thấy trạng thái cũ nếu truy vấn đó không mang thông tin phụ thuộc vào lần ghi trước.

Bookmark là một token đại diện cho một trạng thái đã commit của database. Khi transaction tiếp theo sử dụng bookmark đó, Neo4j bảo đảm truy vấn chỉ chạy sau khi trạng thái được bookmark đại diện đã được áp dụng ở nơi thực thi truy vấn.

Ví dụ:

1. Service A tạo một Order và transaction commit.
2. Neo4j trả bookmark cho trạng thái sau commit.
3. Service B nhận yêu cầu đọc Order vừa tạo.
4. Service B mở session với bookmark từ bước 2.
5. Neo4j chờ cho thành viên xử lý truy vấn đạt ít nhất trạng thái đó rồi mới thực thi truy vấn đọc.

Nhờ vậy, Service B có thể đọc được thay đổi vừa commit mà không phải dựa vào việc truy vấn tình cờ được định tuyến đến đúng máy chủ đã thực hiện ghi.

### Luồng nhân quả

~~~mermaid
sequenceDiagram
    participant A as Transaction ghi
    participant P as Neo4j primary
    participant BM as Bookmark manager
    participant R as Transaction đọc
    participant F as Neo4j member đọc

    A->>P: Ghi Order
    P-->>A: Commit thành công
    P-->>BM: Bookmark mới
    BM->>BM: Lưu trạng thái causal mới
    R->>BM: Lấy bookmark đã biết
    BM-->>R: Bookmark
    R->>F: Mở transaction với bookmark
    F->>F: Chờ áp dụng trạng thái cần thiết
    F-->>R: Kết quả đọc nhất quán
~~~

Bookmark thường quan trọng khi các transaction độc lập cần quan sát thay đổi của nhau. Trong cùng một session, driver đã tự nối các transaction theo quan hệ nhân quả.

## 2. Bookmark không phải là gì?

Bookmark dễ bị hiểu nhầm thành một số thứ khác:

| Khái niệm | Vai trò | Khác với bookmark ở điểm nào? |
|---|---|---|
| Transaction | Nhóm thao tác commit hoặc rollback cùng nhau | Bookmark chỉ được tạo sau commit để mô tả trạng thái đã commit |
| Session | Ngữ cảnh thực thi query và transaction | Session quản lý bookmark nội bộ giữa các transaction của nó |
| Lock | Bảo vệ dữ liệu khi có truy cập đồng thời | Bookmark không khóa node, relationship hay property |
| Version | Phát hiện cập nhật cạnh tranh trên một entity | Bookmark không phát hiện lost update |
| Timestamp | Thời điểm xảy ra sự kiện | Bookmark là token opaque, không phải đồng hồ hoặc thứ tự thời gian nghiệp vụ |
| Snapshot | Một ảnh chụp dữ liệu tại một thời điểm | Bookmark không đóng băng database thành snapshot để đọc lâu dài |

Bookmark cũng không thay thế transaction. Nếu cần tạo Order và trừ Stock như một đơn vị nguyên tử, hãy đặt chúng trong cùng transaction. Nếu cần ngăn hai người cùng cập nhật một entity, hãy dùng optimistic locking hoặc cơ chế concurrency phù hợp.

## 3. Causal consistency trong một session

Neo4j Java Driver tự quản lý bookmark giữa các transaction trong cùng một session. Sau khi transaction thứ nhất commit, các transaction tiếp theo trong session có thể đọc kết quả của nó.

Ví dụ:

~~~java
try (var session = driver.session()) {

    session.executeWrite(tx -> {
        tx.run("""
            CREATE (:Person {id: $id, name: $name})
            """,
            Map.of("id", "p-101", "name", "An")
        ).consume();

        return null;
    });

    // Transaction thứ hai trong cùng session có thể đọc thay đổi vừa ghi.
    String name = session.executeRead(tx ->
        tx.run("""
            MATCH (p:Person {id: $id})
            RETURN p.name AS name
            """,
            Map.of("id", "p-101")
        ).single().get("name").asString()
    );
}
~~~

Không cần tự lấy bookmark rồi truyền lại giữa các transaction trong cùng session. Driver thực hiện việc này.

Nếu các thao tác thuộc cùng một đơn vị nghiệp vụ và có thể dùng chung transaction, hãy ưu tiên một transaction. Nếu chúng cần transaction riêng nhưng vẫn cùng session, driver đã hỗ trợ causal chaining.

## 4. Khi nào cần truyền bookmark giữa các session?

Mỗi session độc lập có thể không biết transaction đã commit trong một session khác. Nếu session B phải nhìn thấy kết quả vừa được session A tạo, hãy chuyển bookmark từ A sang B.

Ví dụ với Java Driver:

~~~java
import java.util.Map;
import java.util.Set;

import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

Set<Bookmark> bookmarks;

try (Session writer = driver.session(
        SessionConfig.builder()
            .withDatabase("neo4j")
            .build()
)) {
    writer.executeWrite(tx -> {
        tx.run("""
            CREATE (:Invoice {id: $id, amount: $amount})
            """,
            Map.of("id", "inv-501", "amount", 250)
        ).consume();

        return null;
    });

    bookmarks = writer.lastBookmarks();
}

try (Session reader = driver.session(
        SessionConfig.builder()
            .withDatabase("neo4j")
            .withBookmarks(bookmarks)
            .build()
)) {
    Integer amount = reader.executeRead(tx ->
        tx.run("""
            MATCH (i:Invoice {id: $id})
            RETURN i.amount AS amount
            """,
            Map.of("id", "inv-501")
        ).single().get("amount").asInt()
    );
}
~~~

Điểm chính:

- Session ghi lấy bookmark sau khi transaction commit.
- Session đọc nhận bookmark qua `SessionConfig.Builder.withBookmarks(...)`.
- Transaction đầu tiên của session đọc sẽ chờ trạng thái cần thiết được áp dụng.
- Chỉ dùng bookmark của database tương ứng với công việc cần đọc.
- Có thể kết hợp nhiều bookmark từ các session độc lập thành một tập hợp.

Nếu không có bookmark, session đọc vẫn chạy bình thường, nhưng trong cluster nó có thể không có bảo đảm đọc thấy ngay thay đổi của transaction ở session khác.

## 5. Bookmark trong Spring Data Neo4j

SDN tích hợp bookmark management với transaction infrastructure. Với cấu hình thông thường, bạn không cần tự tạo bookmark, đọc bookmark hay truyền bookmark giữa các lời gọi repository.

SDN sử dụng bookmark nội bộ để hỗ trợ causal consistency. Các transaction theo sau nhau trong cùng thread hoặc cùng reactive stream có thể đọc những thay đổi đã được transaction trước commit.

Ví dụ:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository invoices;
    private final InvoiceSummaryRepository summaries;

    public InvoiceService(
            InvoiceRepository invoices,
            InvoiceSummaryRepository summaries
    ) {
        this.invoices = invoices;
        this.summaries = summaries;
    }

    @Transactional
    public InvoiceSummary createAndReadSummary(Invoice invoice) {
        invoices.save(invoice);

        // Cùng transaction có thể đọc dữ liệu vừa ghi.
        return summaries.findSummaryByInvoiceId(invoice.getId())
            .orElseThrow();
    }
}
~~~

Trong ví dụ trên, hai repository tham gia cùng transaction Spring. Không cần bookmark riêng giữa chúng.

Nếu hai service method chạy ở hai transaction độc lập hoặc hai session độc lập, hãy xác định xem chúng có cần quan hệ nhân quả hay không. Nếu có, bookmark manager là cơ chế để SDN và driver phối hợp trạng thái đó.

### Neo4jBookmarkManager làm gì?

Interface nằm trong package:

~~~java
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarkManager;
~~~

Neo4jBookmarkManager chịu trách nhiệm lưu, cập nhật và cung cấp bookmark cho transaction của Neo4j. Các factory method chính:

| Factory method | Mục đích |
|---|---|
| create() | Tạo bookmark manager imperative mặc định |
| create(Supplier<Set<Bookmark>>) | Tạo manager với bookmark khởi tạo do supplier cung cấp |
| createReactive() | Tạo bookmark manager cho cấu hình reactive |
| createReactive(Supplier<Set<Bookmark>>) | Tạo reactive manager có bookmark khởi tạo |
| noop() | Tạo manager bỏ qua toàn bộ bookmark |

Manager nhận bookmark mới sau commit và dùng bookmark đã biết cho transaction tiếp theo. Thông thường, transaction manager thực hiện việc cập nhật này; không cần tự gọi updateBookmarks trong code nghiệp vụ.

Hãy phân biệt ba kiểu API:

| API | Vai trò |
|---|---|
| `org.neo4j.driver.Bookmark` | Token opaque đại diện cho trạng thái đã commit |
| `org.neo4j.driver.BookmarkManager` | Hợp đồng bookmark manager của Java Driver, có thể gắn vào `SessionConfig` hoặc `QueryConfig` |
| `org.springframework.data.neo4j.core.transaction.Neo4jBookmarkManager` | Hợp đồng manager của SDN, được `Neo4jTransactionManager` và `ReactiveNeo4jTransactionManager` sử dụng |

Các kiểu này thuộc hai lớp tích hợp khác nhau. Khi dùng repository hoặc template của SDN, hãy cấu hình `Neo4jBookmarkManager`. Khi dùng Java Driver session trực tiếp, bạn có thể truyền bookmark qua `SessionConfig.Builder.withBookmarks(...)` hoặc cấu hình driver `BookmarkManager` cho session. Không truyền nhầm manager của SDN vào API chỉ nhận manager của driver.

## 6. Dùng bookmark manager mặc định

Nếu ứng dụng không cần nhận bookmark từ hệ thống ngoài hoặc lưu bookmark để dùng sau khi restart, hãy để SDN dùng cấu hình mặc định.

Không cần tạo bean Neo4jBookmarkManager chỉ để bật bookmark. Đây là lựa chọn phù hợp cho hầu hết ứng dụng dùng repository, Neo4jTemplate hoặc Neo4jClient với transaction manager do SDN/Spring Boot cấu hình.

Một số tình huống cần cấu hình tùy chỉnh:

- Ứng dụng nhận bookmark từ một tiến trình hoặc service khác.
- Ứng dụng cần lưu bookmark sau commit để chuyển sang một instance khác.
- Một quy trình cần bắt đầu từ trạng thái database đã được một công việc trước đó xác nhận.
- Ứng dụng muốn chủ động capture bookmark để phục vụ một luồng phối hợp đặc biệt.

## 7. Seed bookmark khi khởi tạo transaction manager

Một số hệ thống lưu bookmark sau commit vào kho bền vững. Khi ứng dụng khởi động hoặc khi một workflow mới bắt đầu, bookmark đã lưu có thể được nạp vào manager để transaction mới bắt đầu từ trạng thái causal phù hợp.

Giả sử ứng dụng có abstraction:

~~~java
import java.util.Set;

public interface BookmarkStore {

    Set<String> load();

    void save(Set<String> bookmarks);
}
~~~

Cấu hình manager với supplier:

~~~java
import java.util.Set;
import java.util.stream.Collectors;

import org.neo4j.driver.Bookmark;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarkManager;

@Configuration
public class BookmarkConfiguration {

    @Bean
    Neo4jBookmarkManager neo4jBookmarkManager(BookmarkStore store) {
        return Neo4jBookmarkManager.create(() ->
            store.load().stream()
                .map(Bookmark::from)
                .collect(Collectors.toSet())
        );
    }
}
~~~

Supplier trả về tập bookmark khởi tạo. Nếu chưa có bookmark, trả về tập rỗng. Neo4jBookmarkManager bảo đảm cách gọi supplier được quản lý an toàn trong nội bộ manager; tuy nhiên, implementation của BookmarkStore vẫn phải an toàn khi có nhiều luồng truy cập.

Nếu tự cấu hình transaction manager, hãy truyền cùng instance Neo4jBookmarkManager vào transaction manager:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarkManager;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class Neo4jTransactionConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(
            Driver driver,
            DatabaseSelectionProvider databaseSelectionProvider,
            Neo4jBookmarkManager bookmarkManager
    ) {
        return new Neo4jTransactionManager(
            driver,
            databaseSelectionProvider,
            bookmarkManager
        );
    }
}
~~~

Nếu tự tạo Neo4jClient bằng builder, hãy cấu hình cùng instance manager qua withNeo4jBookmarkManager(...). Transaction manager và client phải chia sẻ cùng manager để trạng thái bookmark được phối hợp nhất quán.

Nếu ứng dụng dùng Spring Boot auto-configuration, hãy kiểm tra cấu hình hiện có trước khi tự khai báo transaction manager. Không cần thay thế cấu hình mặc định chỉ để sử dụng bookmark thông thường.

## 8. Capture bookmark sau khi transaction commit

SDN phát sự kiện Neo4jBookmarksUpdatedEvent sau khi transaction manager commit vật lý thành công và nhận bookmark mới từ cluster. `event.getBookmarks()` trả về tập bookmark mới gắn với event, không phải một danh sách có thứ tự thời gian để ứng dụng tự so sánh token.

Ứng dụng có thể lắng nghe event để lưu bookmark vào kho riêng:

~~~java
import java.util.Set;
import java.util.stream.Collectors;

import org.neo4j.driver.Bookmark;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarksUpdatedEvent;

@Component
public class BookmarkCapture
        implements ApplicationListener<Neo4jBookmarksUpdatedEvent> {

    private final BookmarkStore bookmarkStore;

    public BookmarkCapture(BookmarkStore bookmarkStore) {
        this.bookmarkStore = bookmarkStore;
    }

    @Override
    public void onApplicationEvent(Neo4jBookmarksUpdatedEvent event) {
        Set<String> values = event.getBookmarks().stream()
            .map(Bookmark::value)
            .collect(Collectors.toSet());

        bookmarkStore.save(values);
    }
}
~~~

Event được phát sau khi transaction đã commit. Bookmark trong event có thể được dùng để seed transaction manager hoặc truyền cho một thành phần khác cần tiếp tục công việc theo trạng thái vừa commit. Ví dụ trên giả định các lần cập nhật của cùng workflow được tuần tự hóa. Nếu nhiều transaction của cùng workflow có thể commit đồng thời, hãy tuần tự hóa việc ghi bookmark hoặc lưu kèm sequence/version của workflow; không sắp xếp bookmark bằng cách so sánh chuỗi token vì bookmark là opaque.

Hãy lưu bookmark theo cách thread-safe. Nếu bookmark cần tồn tại qua lần restart hoặc chuyển giữa nhiều instance ứng dụng, kho lưu trữ phải bền vững và có quy tắc cập nhật nguyên tử phù hợp.

Không nên ghi đè bookmark mới bằng một event cũ đến trễ. Nếu nhiều transaction hoàn tất đồng thời, bookmark store phải xử lý cập nhật theo thứ tự của workflow hoặc quản lý phiên bản cập nhật phù hợp; không tự giả định event luôn đến theo thứ tự nghiệp vụ.

## 9. Bookmark manager và ứng dụng nhiều instance

Một Neo4jBookmarkManager trong bộ nhớ chỉ quản lý trạng thái mà instance ứng dụng đó biết. Nếu ứng dụng có nhiều pod hoặc nhiều tiến trình độc lập, manager trong pod A không tự chia sẻ trạng thái với manager trong pod B.

Nếu một workflow ghi ở pod A rồi đọc ở pod B, có thể dùng một trong các cách:

- Truyền bookmark cùng metadata workflow sang pod B.
- Lưu bookmark trong kho dùng chung và seed manager hoặc session tiếp theo.
- Để một thành phần điều phối workflow giữ bookmark và chuyển nó cho bước đọc.

Ví dụ luồng:

~~~text
Pod A
  |
  | ghi dữ liệu và commit
  v
Neo4j trả bookmark
  |
  | lưu bookmark cùng workflow ID
  v
Shared bookmark store
  |
  | bước tiếp theo lấy bookmark
  v
Pod B
  |
  | mở transaction với bookmark đã seed
  v
Đọc trạng thái sau lần ghi của Pod A
~~~

Không cần chia sẻ bookmark cho mọi request. Chỉ chuyển bookmark khi bước tiếp theo thực sự phụ thuộc vào kết quả commit trước đó.

Khi lưu bookmark bền vững, hãy gắn nó với database và workflow phù hợp. Không dùng một bookmark như token chung cho mọi tenant, mọi database hoặc mọi luồng nghiệp vụ mà không xác định phạm vi.

## 10. Reactive bookmark management

SDN cung cấp bookmark manager cho reactive transaction:

~~~java
@Bean
Neo4jBookmarkManager reactiveBookmarkManager() {
    return Neo4jBookmarkManager.createReactive();
}
~~~

Reactive transaction manager nhận cùng manager:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarkManager;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Bean
ReactiveTransactionManager reactiveTransactionManager(
        Driver driver,
        ReactiveDatabaseSelectionProvider databaseSelectionProvider,
        Neo4jBookmarkManager reactiveBookmarkManager
) {
    return new ReactiveNeo4jTransactionManager(
        driver,
        databaseSelectionProvider,
        reactiveBookmarkManager
    );
}
~~~

Nếu tự cấu hình ReactiveNeo4jClient, hãy truyền cùng instance manager qua withNeo4jBookmarkManager(...).

Trong reactive flow, bookmark management phối hợp với transaction context của publisher. Hãy giữ các thao tác phụ thuộc trong cùng pipeline khi có thể:

~~~java
return reactiveInvoices.save(invoice)
    .then(reactiveSummaries.findSummaryByInvoiceId(invoice.getId()))
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Invoice summary not found")
    ));
~~~

Không gọi block() để lấy bookmark hoặc chờ transaction trong reactive pipeline. Để SDN và reactive transaction manager quản lý lifecycle của transaction.

## 11. Khi nào nên tắt bookmark management?

SDN cung cấp:

~~~java
@Bean
Neo4jBookmarkManager neo4jBookmarkManager() {
    return Neo4jBookmarkManager.noop();
}
~~~

noop() bỏ qua bookmark: manager không cung cấp bookmark cũ và loại bỏ bookmark mới.

Trong cluster, việc tắt bookmark có thể khiến ứng dụng đọc dữ liệu cũ sau một transaction ghi ở session khác. Điều này có thể gây ra quyết định nghiệp vụ dựa trên dữ liệu chưa được cập nhật, hoặc ghi đè trạng thái mới hơn.

Chỉ cân nhắc noop() khi:

- Ứng dụng chấp nhận eventual consistency và stale read.
- Các luồng không cần đọc ngay dữ liệu vừa được ghi ở transaction khác.
- Ứng dụng đã có cơ chế đồng bộ hoặc retry phù hợp với nghiệp vụ.
- Việc giảm chi phí chờ causal consistency có lợi ích đo được.

Trong một instance Neo4j đơn, bookmark có thể không tạo khác biệt đáng kể. Tuy nhiên, không nên tắt bookmark chỉ vì muốn tối ưu trước khi đo hiệu năng và xác định yêu cầu nhất quán.

## 12. Chi phí và giới hạn của bookmark

Bookmark có thể khiến transaction phải chờ thành viên cluster áp dụng trạng thái cần thiết. Điều này hỗ trợ causal consistency nhưng cũng có thể làm tăng độ trễ.

| Tình huống | Cách tiếp cận |
|---|---|
| Nhiều thao tác thuộc cùng đơn vị nghiệp vụ | Gom trong một transaction |
| Nhiều transaction liên tiếp trong cùng session | Để driver tự quản lý bookmark |
| Transaction độc lập cần đọc kết quả của nhau | Truyền bookmark giữa session hoặc dùng manager chung |
| Hai transaction không phụ thuộc nhau | Không cần ép causal chain |
| Nhiều pod cần tiếp tục cùng workflow | Capture và lưu bookmark để chuyển tiếp |
| Hệ thống chấp nhận stale read | Có thể cân nhắc noop sau khi đánh giá rủi ro |

Bookmark không giải quyết mọi vấn đề đồng thời. Nó không:

- Khóa dữ liệu.
- Ngăn hai transaction cùng sửa một node.
- Thay thế @Version.
- Bảo đảm transaction phân tán qua nhiều database là nguyên tử.
- Thay thế retry, idempotency hoặc xử lý conflict.
- Giữ dữ liệu bất biến như một snapshot lịch sử.

Nếu cần phát hiện hai người cùng sửa một Document, hãy dùng optimistic locking. Nếu cần nhiều bước ghi cùng thành công hoặc thất bại, hãy dùng transaction. Bookmark chỉ điều phối trạng thái nhân quả giữa các transaction.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Session đọc không thấy dữ liệu vừa ghi ở session khác | Không truyền bookmark hoặc manager không chia sẻ trạng thái | Truyền bookmark từ session ghi sang session đọc |
| Nghĩ rằng bookmark là timestamp | Xem token như thời gian | Xem bookmark là token opaque, không phân tích giá trị |
| Tự quản lý bookmark trong cùng session | Không biết driver đã tự causal-chain | Để driver quản lý transaction trong cùng session |
| Manager không nhận bookmark mới | Client và transaction manager dùng hai instance khác nhau | Dùng cùng Neo4jBookmarkManager instance |
| Đọc cũ giữa nhiều pod | Bookmark manager chỉ tồn tại trong bộ nhớ từng pod | Capture và seed bookmark qua kho dùng chung |
| Bookmark cũ ghi đè bookmark mới | Store cập nhật theo thứ tự event đến | Hợp nhất tập bookmark hoặc kiểm soát phiên bản |
| Tắt bookmark rồi gặp stale read | Dùng noop trong cluster có yêu cầu causal consistency | Bật lại bookmark hoặc thay đổi yêu cầu nhất quán |
| Truyền bookmark sai database | Không quản lý phạm vi bookmark | Gắn bookmark với database/workflow phù hợp |
| Tăng latency sau khi bật bookmark | Transaction phải chờ trạng thái được replicate | Gom transaction và chỉ chain các thao tác phụ thuộc |
| Dùng bookmark để chống lost update | Nhầm causal consistency với optimistic locking | Dùng @Version hoặc cơ chế concurrency riêng |

## 14. Bài tập thực hành

Giả sử một ứng dụng có hai service:

- InvoiceWriter tạo Invoice trong một transaction.
- InvoiceReader đọc Invoice trong một session khác ngay sau khi writer hoàn tất.

Thực hiện:

1. Viết query tạo Invoice bằng Java Driver.
2. Sau commit, lấy bookmark từ session ghi.
3. Mở session đọc với withBookmarks(...).
4. Đọc Invoice và xác nhận dữ liệu vừa tạo xuất hiện.
5. Bỏ withBookmarks(...) để quan sát hành vi trên cluster.
6. Chạy hai transaction độc lập không phụ thuộc nhau và xác định khi nào không cần bookmark.
7. Cấu hình Neo4jBookmarkManager mặc định trong SDN.
8. Viết một ApplicationListener nhận Neo4jBookmarksUpdatedEvent.
9. Lưu bookmark vào BookmarkStore và seed manager bằng supplier.
10. Nếu dùng reactive repository, cấu hình createReactive() và kiểm tra các thao tác trong cùng reactive stream.

Câu hỏi tự kiểm tra:

- Bookmark đại diện cho điều gì sau khi transaction commit?
- Vì sao transaction trong cùng session có thể đọc thay đổi trước đó mà không cần truyền bookmark thủ công?
- Khi nào cần dùng withBookmarks(...)?
- Neo4jBookmarkManager khác Bookmark của Neo4j Java Driver như thế nào?
- Vì sao SDN thường không cần cấu hình bookmark riêng cho cluster?
- Neo4jBookmarksUpdatedEvent được phát ở thời điểm nào?
- Supplier truyền vào Neo4jBookmarkManager.create(...) có trách nhiệm gì?
- Vì sao noop() có thể gây stale read trong cluster?
- Bookmark có ngăn lost update hoặc khóa node không?
- Cần làm gì để một workflow chạy ở pod khác vẫn đọc được thay đổi đã commit?

## Kết luận

Bookmark là token đại diện cho trạng thái đã commit của Neo4j. Nó giúp transaction tiếp theo chờ cho trạng thái cần thiết được áp dụng trước khi đọc, nhờ đó hỗ trợ causal consistency giữa các session hoặc transaction độc lập.

Spring Data Neo4j tự quản lý bookmark trong cấu hình thông thường. Neo4jBookmarkManager cung cấp các factory method để dùng manager mặc định, seed bookmark ban đầu, tạo biến thể reactive hoặc tắt quản lý bookmark. Khi cần phối hợp công việc giữa nhiều instance, ứng dụng có thể capture Neo4jBookmarksUpdatedEvent, lưu bookmark và seed lại manager cho bước tiếp theo.

Chỉ dùng bookmark cho các thao tác thực sự phụ thuộc vào trạng thái đã commit trước đó. Bookmark không thay thế transaction, optimistic locking hay cơ chế xử lý conflict; việc chain không cần thiết có thể làm tăng độ trễ của cluster.

## Tài liệu tham khảo

- [Spring Data Neo4j FAQ: Using a Neo4j cluster instance and bookmark management](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j API: Neo4jBookmarkManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jBookmarkManager.html)
- [Spring Data Neo4j API: Neo4jTransactionManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Spring Data Neo4j API: ReactiveNeo4jTransactionManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/ReactiveNeo4jTransactionManager.html)
- [Neo4j Java Driver Manual: Coordinate parallel transactions with bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Java Driver API: Bookmark](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Bookmark.html)
- [Neo4j Java Driver API: SessionConfig.Builder.withBookmarks](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/SessionConfig.Builder.html)
