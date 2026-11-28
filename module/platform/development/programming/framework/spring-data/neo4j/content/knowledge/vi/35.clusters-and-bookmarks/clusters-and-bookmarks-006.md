# Chia sẻ bookmark giữa yêu cầu hoặc phiên bản ứng dụng khi cần

Bookmark của Neo4j là token đại diện cho trạng thái đã commit của database. Khi transaction sau nhận bookmark từ transaction trước, Neo4j bảo đảm transaction sau chỉ chạy sau khi trạng thái được tham chiếu đã được áp dụng trên máy chủ phục vụ nó. Cơ chế này tạo causal consistency, thường dùng khi một luồng công việc ghi dữ liệu rồi một luồng khác đọc hoặc tiếp tục xử lý dữ liệu đó.

Spring Data Neo4j (SDN) đã tự quản lý bookmark cho các transaction do SDN quản lý. Trong một application context, các thao tác imperative hoặc reactive theo đúng transaction manager có thể tiếp tục đọc được thay đổi đã commit trước đó mà không cần tự truyền token qua từng lời gọi repository. Việc chia sẻ thủ công chỉ cần thiết khi causal chain đi qua ranh giới mà bookmark manager mặc định không chia sẻ được, chẳng hạn giữa nhiều JVM, nhiều service hoặc các phiên bản ứng dụng chạy song song.

## 1. Bookmark giải quyết vấn đề gì?

Trong cụm Neo4j, một lần ghi có thể được thực hiện trên primary rồi lan truyền tới các secondary/reader. Một transaction đọc bắt đầu ngay sau đó trên máy chủ khác cần biết trạng thái mà lần ghi trước đã tạo ra.

Ví dụ:

1. Service A tạo node Order và commit transaction.
2. Service B nhận thông báo có orderId vừa được tạo.
3. Service B đọc Order để tạo bước xử lý tiếp theo.
4. Nếu transaction đọc không mang quan hệ nhân quả với lần ghi trước, nó có thể đến một reader chưa áp dụng thay đổi đó.

Bookmark cho transaction đọc biết phải chờ trạng thái của transaction ghi được áp dụng trước khi thực thi query phụ thuộc.

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant P as Neo4j primary
    participant R as Neo4j reader
    participant B as Service B
    A->>P: CREATE Order
    P-->>A: Commit + bookmark
    A->>B: orderId + bookmark
    B->>R: Đọc Order kèm bookmark
    R->>R: Chờ trạng thái được áp dụng
    R-->>B: Trả Order đã commit
~~~

Bookmark không chứa dữ liệu của node hay relationship. Nó là tham chiếu tới trạng thái database đã commit, được driver và Neo4j sử dụng để điều phối thứ tự nhân quả.

## 2. Khi nào không cần tự chia sẻ bookmark?

Với SDN hiện đại, bookmark management được bật tự động. Trong phần lớn ứng dụng, không cần thêm annotation quản lý bookmark, không cần tự tạo BookmarkManager và không cần gắn token vào mọi request.

Các trường hợp thông thường:

- Nhiều repository method nằm trong cùng một Spring transaction: chúng dùng chung transaction.
- Nhiều transaction SDN nối tiếp nhau trong cùng luồng xử lý imperative hoặc reactive: SDN quản lý bookmark để transaction sau thấy thay đổi trước đó.
- Các query chạy trong cùng một Neo4j Driver session: driver tự duy trì causal chaining giữa các transaction trong session.
- Các request được xử lý bởi cùng application instance và cùng transaction manager SDN: bookmark manager của SDN tự quản lý trạng thái mà nó đã nhận.

Ví dụ một use case SDN thông thường:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ShipmentRepository shipments;

    public OrderService(
            OrderRepository orders,
            ShipmentRepository shipments) {
        this.orders = orders;
        this.shipments = shipments;
    }

    @Transactional
    public Shipment createOrderAndShipment(Order order) {
        Order savedOrder = orders.save(order);
        return shipments.save(new Shipment(savedOrder.getOrderId()));
    }
}
~~~

Hai thao tác repository tham gia cùng transaction. Không cần lấy bookmark giữa hai lần gọi save.

Nếu hai transaction độc lập nhưng vẫn do cùng transaction manager SDN quản lý, hãy để SDN xử lý trước. Chỉ thêm cơ chế chia sẻ thủ công khi có một ranh giới thực sự giữa các process hoặc transaction manager độc lập.

## 3. Bookmark manager mặc định không tự chia sẻ giữa nhiều JVM

Mỗi application instance có Spring context và transaction manager riêng. Bookmark manager mặc định giữ trạng thái trong bộ nhớ của instance đó. Vì vậy:

- Instance A có thể biết bookmark của các transaction đã commit qua transaction manager A.
- Instance B có bookmark manager riêng và không tự biết bookmark mà A vừa nhận.
- Restart instance làm mất bookmark manager state trong bộ nhớ.
- Rolling deployment có thể chạy đồng thời phiên bản cũ và phiên bản mới, mỗi phiên bản có manager riêng.

Nếu một request ghi ở instance A rồi request phụ thuộc được xử lý ở instance B, cần truyền causal dependency qua một kênh chung. Kênh đó có thể là message nội bộ, shared store hoặc cơ chế điều phối workflow.

Không nên đồng nhất việc các instance kết nối cùng một Neo4j cluster với việc chúng tự chia sẻ bookmark. Driver có thể routing tới cùng cluster, nhưng bookmark manager trong bộ nhớ của từng process vẫn là các đối tượng độc lập.

## 4. Hai cách chuyển bookmark qua ranh giới ứng dụng

| Mô hình | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Truyền tường minh theo workflow | Producer gửi bookmark cùng message/command; consumer dùng bookmark cho transaction phụ thuộc | Một request hoặc event có quan hệ nhân quả cụ thể với một lần ghi |
| Shared bookmark store | Các instance ghi bookmark đã commit vào kho dùng chung; transaction manager của instance khác lấy bookmark để seed transaction | Nhiều phiên bản hoặc nhiều service cần dùng chung causal state |

Không phải mọi query đều cần bookmark. Chỉ chuyển bookmark cho thao tác thực sự phụ thuộc vào trạng thái do transaction trước tạo ra. Các query độc lập không cần chờ nhau.

## 5. Chuyển bookmark tường minh bằng Neo4j Java Driver

Khi dùng Java Driver trực tiếp, session có thể nhận một hoặc nhiều bookmark ban đầu qua SessionConfig.Builder.withBookmarks(...).

Ví dụ producer lấy bookmark sau khi ghi:

~~~java
import java.util.Set;

import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public Set<String> createOrderAndGetBookmarks(Driver driver) {
    try (var session = driver.session(
            SessionConfig.builder().withDatabase("neo4j").build())) {

        session.executeWrite(tx -> {
            tx.run("""
                    CREATE (:Order {orderId: $orderId})
                    """,
                    java.util.Map.of("orderId", "order-42"))
                .consume();
            return null;
        });

        return session.lastBookmarks().stream()
            .map(Bookmark::value)
            .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }
}
~~~

Producer có thể gắn tập giá trị bookmark vào một message nội bộ cùng với orderId. Consumer chuyển các chuỗi đó thành Bookmark và cấu hình session:

~~~java
import java.util.Set;
import java.util.stream.Collectors;

import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public void readOrderAfterWrite(
        Driver driver, String orderId, Set<String> bookmarkValues) {

    Set<Bookmark> bookmarks = bookmarkValues.stream()
        .map(Bookmark::from)
        .collect(Collectors.toUnmodifiableSet());

    try (var session = driver.session(
            SessionConfig.builder()
                .withDatabase("neo4j")
                .withBookmarks(bookmarks)
                .build())) {

        session.executeRead(tx -> tx.run("""
                MATCH (o:Order {orderId: $orderId})
                RETURN o
                """,
                java.util.Map.of("orderId", orderId))
            .single());
    }
}
~~~

Session.lastBookmarks() trả về tập bookmark của session. Dùng Bookmark.value() để lưu hoặc truyền token dưới dạng chuỗi và Bookmark.from(value) để tái tạo bookmark ở consumer. Ví dụ trên minh họa session imperative của Driver; nếu toàn bộ thao tác đang dùng SDN repository, không cần mở thêm session Driver độc lập chỉ để chuyển bookmark.

## 6. Bắt sự kiện bookmark do SDN phát ra

SDN cung cấp Neo4jBookmarksUpdatedEvent. Event này được phát sau khi transaction manager đã commit transaction vật lý thành công và nhận được bookmark mới từ cluster. Ứng dụng có thể lắng nghe event để chuyển bookmark vào shared store hoặc hệ thống message.

~~~java
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarksUpdatedEvent;

@Component
public class BookmarkCapture
        implements ApplicationListener<Neo4jBookmarksUpdatedEvent> {

    private final SharedBookmarkStore bookmarkStore;

    public BookmarkCapture(SharedBookmarkStore bookmarkStore) {
        this.bookmarkStore = bookmarkStore;
    }

    @Override
    public void onApplicationEvent(Neo4jBookmarksUpdatedEvent event) {
        Set<String> values = event.getBookmarks().stream()
            .map(bookmark -> bookmark.value())
            .collect(Collectors.toUnmodifiableSet());

        if (!values.isEmpty()) {
            bookmarkStore.merge("neo4j", values);
        }
    }
}
~~~

SharedBookmarkStore là abstraction do ứng dụng định nghĩa, có thể được triển khai bằng Redis, database dùng chung hoặc một dịch vụ lưu trạng thái. Ví dụ hợp đồng:

~~~java
import java.util.Set;

public interface SharedBookmarkStore {

    Set<String> load(String databaseKey);

    void merge(String databaseKey, Set<String> bookmarkValues);
}
~~~

Phương thức merge cần có thao tác cập nhật nguyên tử để nhiều instance có thể ghi bookmark đồng thời mà không ghi đè mất dữ liệu của nhau. Không dùng một biến static hoặc collection trong bộ nhớ của JVM nếu mục tiêu là chia sẻ giữa các process.

Event chỉ được phát sau commit thành công. Vì vậy, nếu listener lưu bookmark vào hệ thống ngoài bị lỗi, transaction Neo4j đã commit vẫn không thể rollback trở lại. Trong production, cần xác định cách retry hoặc chuyển tiếp sự kiện đáng tin cậy và theo dõi lỗi đồng bộ bookmark.

## 7. Seed bookmark vào transaction manager của SDN

Để instance mới hoặc instance khác dùng bookmark đã lưu, tạo Neo4jBookmarkManager với một Supplier<Set<Bookmark>>. Supplier cung cấp bookmark ban đầu cho transaction manager. Sau đó truyền manager này vào Neo4jTransactionManager.

Ví dụ cho ứng dụng imperative:

~~~java
import java.util.Set;
import java.util.function.Supplier;
import java.util.stream.Collectors;

import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarkManager;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class BookmarkSeedingConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(
            Driver driver,
            DatabaseSelectionProvider databaseSelectionProvider,
            SharedBookmarkStore bookmarkStore) {

        Supplier<Set<Bookmark>> bookmarkSupplier = () ->
            bookmarkStore.load("neo4j").stream()
                .map(Bookmark::from)
                .collect(Collectors.toUnmodifiableSet());

        Neo4jBookmarkManager bookmarkManager =
            Neo4jBookmarkManager.create(bookmarkSupplier);

        return new Neo4jTransactionManager(
            driver, databaseSelectionProvider, bookmarkManager);
    }
}
~~~

Đây là cấu hình tùy chỉnh thay cho transaction manager imperative mặc định. Nếu Spring Boot đã tự cấu hình transaction manager, chỉ thêm cấu hình này khi thực sự cần seeding; không đăng ký hai bean cùng vai trò rồi để ứng dụng chọn ngẫu nhiên.

Với ứng dụng reactive, dùng reactive transaction manager và factory tương ứng:

~~~java
import java.util.Set;
import java.util.function.Supplier;
import java.util.stream.Collectors;

import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.Neo4jBookmarkManager;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
public class ReactiveBookmarkSeedingConfiguration {

    @Bean
    ReactiveTransactionManager reactiveTransactionManager(
            Driver driver,
            ReactiveDatabaseSelectionProvider databaseSelectionProvider,
            SharedBookmarkStore bookmarkStore) {

        Supplier<Set<Bookmark>> bookmarkSupplier = () ->
            bookmarkStore.load("neo4j").stream()
                .map(Bookmark::from)
                .collect(Collectors.toUnmodifiableSet());

        Neo4jBookmarkManager bookmarkManager =
            Neo4jBookmarkManager.createReactive(bookmarkSupplier);

        return new ReactiveNeo4jTransactionManager(
            driver, databaseSelectionProvider, bookmarkManager);
    }
}
~~~

Hai ví dụ là hai lựa chọn cấu hình cho hai kiểu ứng dụng. Không khai báo cả hai transaction manager nếu ứng dụng chỉ dùng một persistence model. Nếu ứng dụng có nhiều database, hãy tạo khóa riêng cho từng database selection và không trộn bookmark giữa các database.

Supplier là API đồng bộ và cần trả về nhanh, an toàn khi nhiều thread gọi. Nếu shared store là dịch vụ từ xa có độ trễ, nên nạp dữ liệu vào cache thread-safe trước khi transaction manager yêu cầu và cập nhật cache một cách nguyên tử. Không thực hiện một lời gọi mạng chậm trong supplier khi transaction đang bắt đầu.

## 8. Lưu trữ và hợp nhất bookmark đúng cách

Bookmark là token opaque. Ứng dụng không nên giải mã, so sánh chuỗi, sắp xếp theo thứ tự từ điển hoặc tự suy luận bookmark nào mới hơn. Driver và Neo4j hiểu ngữ nghĩa của các token và có thể nhận một tập bookmark.

Khi thiết kế shared store:

- Dùng khóa có phạm vi rõ ràng, tối thiểu theo cluster/environment và database.
- Lưu toàn bộ bookmark cần cho causal dependency, không chọn token bằng cách so sánh chuỗi.
- Dùng thao tác merge/atomic update khi nhiều instance có thể commit cùng lúc.
- Loại trùng theo giá trị token.
- Có chính sách dọn dẹp dựa trên vòng đời consumer và causal dependency; không xóa bookmark chỉ vì token có vẻ cũ.
- Không trộn bookmark từ database khác hoặc môi trường khác.

Nếu shared store chỉ giữ một giá trị duy nhất theo kiểu last-write-wins, hai transaction độc lập từ hai instance có thể cập nhật đồng thời và ghi đè mất causal dependency của nhau. Cần chọn cấu trúc lưu trữ và cơ chế đồng bộ phù hợp với số lượng producer, consumer và workflow đang chạy.

## 9. Chia sẻ bookmark giữa các phiên bản ứng dụng khi rolling deployment

Giả sử phiên bản V1 và V2 chạy song song trong lúc triển khai:

1. V1 ghi dữ liệu và commit.
2. V2 nhận message cần đọc dữ liệu do V1 tạo.
3. Bookmark manager mặc định của V2 không tự biết token đang nằm trong bộ nhớ V1.
4. Nếu V1 đã publish bookmark vào shared store, V2 có thể seed transaction manager từ store đó.
5. Transaction đọc của V2 chờ trạng thái cần thiết được áp dụng trước khi query.

Để luồng này hoạt động, mọi phiên bản có thể tạo dữ liệu phụ thuộc cần được cấu hình capture bookmark trước khi dựa vào consumer dùng shared bookmark. Nếu một phiên bản cũ không phát bookmark, shared store không thể tự suy ra transaction mà phiên bản đó đã commit.

Một rollout an toàn có thể làm theo thứ tự:

- Triển khai cơ chế capture/publish bookmark lên các producer trước.
- Xác nhận các instance đang chạy đều cập nhật shared store sau commit.
- Khởi động phiên bản mới với transaction manager được seed từ shared store.
- Chuyển dần traffic và message consumer sang phiên bản mới.
- Chỉ bỏ cơ chế chia sẻ khi không còn workflow phụ thuộc giữa các process hoặc phiên bản.

Không nên giả định rằng việc hai phiên bản cùng kết nối một Neo4j cluster đã đủ để bảo đảm chúng nhìn thấy cùng bookmark state.

## 10. Bookmark không thay thế transaction hoặc concurrency control

Bookmark chỉ bảo đảm thứ tự nhân quả giữa các trạng thái đã commit. Nó không:

- Tạo transaction phân tán giữa nhiều service.
- Khóa node hoặc relationship để ngăn hai request cập nhật đồng thời.
- Giải quyết optimistic locking conflict.
- Bảo đảm mọi query độc lập chạy tuần tự.
- Thay thế unique constraint hoặc validation nghiệp vụ.
- Tự retry một workflow đã thất bại.

Nếu hai transaction cùng cập nhật một entity, hãy dùng @Version, constraint và chính sách xử lý conflict phù hợp. Bookmark chỉ giúp transaction phụ thuộc đợi một trạng thái trước đó được áp dụng.

## 11. Chi phí hiệu năng và phạm vi áp dụng

Khi transaction sử dụng bookmark, Neo4j có thể phải chờ một trạng thái đã commit được lan truyền trước khi query bắt đầu. Vì vậy, chia sẻ bookmark quá rộng có thể tăng latency:

- Các request không liên quan bị buộc chờ cùng một causal chain.
- Nhiều bookmark độc lập có thể làm transaction sau phải đợi nhiều trạng thái.
- Shared store thêm một bước đọc/ghi và một điểm có thể lỗi.
- Đồng bộ bookmark giữa các instance có thể tạo thêm tải cho hệ thống.

Hãy ưu tiên gom các thao tác phụ thuộc vào cùng transaction hoặc cùng Driver session. Chỉ dùng bookmark qua ranh giới process khi nghiệp vụ cần read-after-write hoặc causal dependency giữa các instance. Query độc lập không cần chờ bookmark của một workflow khác.

## 12. Kiểm thử causal consistency qua bookmark

Một integration test có thể mô phỏng producer và consumer dùng hai session riêng:

1. Mở session A và tạo một node.
2. Commit transaction rồi lấy sessionA.lastBookmarks().
3. Đóng session A.
4. Mở session B với SessionConfig.withBookmarks(...).
5. Đọc node vừa tạo trong session B.
6. Xác nhận dữ liệu được đọc thành công.

Với SDN, nên bổ sung kiểm thử:

- Một transaction ghi hoàn tất rồi transaction tiếp theo trên cùng application context đọc được dữ liệu.
- Neo4jBookmarksUpdatedEvent được phát sau commit và mang bookmark.
- Bookmark được lưu vào shared store theo đúng database key.
- Một application context mới được seed từ store và có thể đọc dữ liệu phụ thuộc.
- Nhiều producer cập nhật store đồng thời không làm mất bookmark.
- Khi shared store không khả dụng, ứng dụng báo lỗi hoặc fallback theo chính sách đã định nghĩa.
- Bookmark của database A không bị truyền sang database B.

Không chỉ kiểm tra rằng query cuối trả về dữ liệu trong một test single-instance. Hãy tạo hai session hoặc hai application context độc lập để mô phỏng đúng ranh giới cần chia sẻ.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tự truyền bookmark giữa mọi repository method | Tăng độ phức tạp dù SDN đã quản lý tự động | Dùng transaction manager mặc định cho luồng trong cùng application context |
| Nghĩ bookmark manager mặc định chia sẻ giữa nhiều JVM | Instance mới có thể không biết trạng thái commit của instance khác | Dùng event capture và shared store khi cần causal handoff |
| Lưu một bookmark duy nhất bằng last-write-wins | Có thể mất dependency từ transaction đồng thời khác | Merge atomically và giữ tập bookmark cần thiết |
| So sánh bookmark bằng chuỗi để chọn token mới nhất | Hiểu sai token opaque | Chuyển cả tập bookmark cho driver/SDN |
| Trộn bookmark giữa các database | Transaction chờ sai trạng thái hoặc lỗi | Scope theo cluster, environment và database |
| Dùng bookmark để ngăn hai writer cập nhật cùng node | Vẫn có race condition hoặc optimistic locking conflict | Dùng @Version, constraint và transaction phù hợp |
| Lưu bookmark trước khi transaction commit | Consumer có thể chờ trạng thái chưa commit hoặc không tồn tại | Capture từ Neo4jBookmarksUpdatedEvent sau commit |
| Giả định listener lưu shared store có thể rollback cùng Neo4j | Neo4j đã commit nhưng shared store có thể lỗi | Có retry, durable handoff và giám sát |
| Dùng bookmark cho query không phụ thuộc nhau | Tăng latency và giảm khả năng song song | Chỉ truyền causal dependency khi nghiệp vụ yêu cầu |
| Supplier đọc remote store chậm khi transaction bắt đầu | Tăng thời gian mở transaction và chặn luồng gọi | Dùng cache thread-safe, cập nhật có kiểm soát |

## 14. Quy trình triển khai chia sẻ bookmark

1. Xác định workflow có thực sự đi qua nhiều JVM hoặc application version hay không.
2. Nếu chỉ dùng một application context SDN, giữ bookmark management mặc định.
3. Nếu cần chia sẻ, chọn cách truyền token theo workflow hoặc shared bookmark store.
4. Capture bookmark sau commit qua Neo4jBookmarksUpdatedEvent.
5. Lưu token bằng Bookmark.value() và tái tạo bằng Bookmark.from(...).
6. Seed transaction manager imperative bằng Neo4jBookmarkManager.create(supplier) hoặc reactive bằng createReactive(supplier).
7. Bảo đảm supplier thread-safe, nhanh và chỉ trả bookmark đúng database.
8. Thiết kế shared store có atomic merge và cơ chế xử lý lỗi sau commit.
9. Cấu hình tất cả producer đang hoạt động để publish bookmark trước khi bật consumer phụ thuộc.
10. Kiểm thử hai session hoặc hai application instance, sau đó đo latency để xác nhận chỉ các workflow cần thiết mới bị ràng buộc nhân quả.

## 15. Tự kiểm tra

1. Bookmark đại diện cho điều gì trong Neo4j?
2. Vì sao SDN thông thường không yêu cầu cấu hình bookmark thủ công?
3. Vì sao bookmark manager mặc định của một JVM không tự chia sẻ với instance khác?
4. Neo4jBookmarksUpdatedEvent được phát ở thời điểm nào?
5. Bookmark.value() và Bookmark.from(...) dùng để làm gì?
6. Khác biệt giữa Neo4jBookmarkManager.create(...) và createReactive(...) là gì?
7. Vì sao shared bookmark store cần atomic merge khi có nhiều producer?
8. Vì sao không được so sánh token bookmark như một chuỗi version thông thường?
9. Bookmark có giải quyết optimistic locking hoặc transaction phân tán không?
10. Khi nào nên tránh chia sẻ bookmark vì chi phí latency?

SDN đã tự quản lý bookmark cho phần lớn transaction trong cùng application context. Khi causal dependency phải vượt qua ranh giới JVM hoặc phiên bản ứng dụng, hãy capture bookmark sau commit, chuyển token qua message hoặc shared store và seed transaction manager của consumer. Giữ token opaque, scope theo database, xử lý cập nhật đồng thời và chỉ áp dụng cho workflow thực sự cần read-after-write.

Tài liệu tham khảo:

- [Spring Data Neo4j FAQ – bookmark management and seeding](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – Neo4jBookmarkManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jBookmarkManager.html)
- [Spring Data Neo4j – Neo4jBookmarksUpdatedEvent API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jBookmarksUpdatedEvent.html)
- [Neo4j Java Driver Manual – Coordinate parallel transactions](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Java Driver API – Bookmark](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Bookmark.html)
