# Kiểm thử hợp đồng, dữ liệu biên, reactive và hiệu năng

## 1. Mục tiêu và phạm vi bài thực hành

Một repository trả về đúng một bản ghi trong tình huống đơn giản chưa đủ chứng minh ứng dụng truy cập dữ liệu đúng. Lỗi thường xuất hiện khi không có kết quả, nhiều bản ghi cùng khóa sắp xếp, dữ liệu nằm sát ranh giới trang, hai lần cập nhật dùng cùng version hoặc subscriber hủy một luồng reactive.

Bài thực hành của module **SPRING_DATA_COMMONS** kết hợp Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing thành một chiến lược kiểm thử. Kết quả cần đạt gồm ba nhóm bằng chứng:

- Hành vi truy cập dữ liệu đáp ứng hợp đồng đã công bố.
- Luồng reactive phát đúng giá trị, lỗi và tín hiệu kết thúc trong điều kiện subscription cụ thể.
- Chi phí thực thi được đo trên workload có ý nghĩa, với môi trường và giới hạn đo rõ ràng.

Spring Data Commons cung cấp abstraction dùng chung; mapping, câu truy vấn, driver, transaction và khả năng reactive do module store quyết định. Bài chọn **Spring Data MongoDB reactive** làm đường minh họa tích hợp, dùng Java record, JUnit Jupiter và `reactor-test`. Khi áp dụng cho JPA, JDBC hoặc R2DBC, giữ lại yêu cầu nghiệp vụ nhưng điều chỉnh model, fixture và kỳ vọng theo store. JPA repository thông thường không trở thành reactive chỉ vì được bọc trong `Mono`.

Các ví dụ là mã để người học tích hợp vào dự án có bộ dependency tương thích và MongoDB dành riêng cho test. Không mặc định mọi đoạn mã bên dưới tạo thành một ứng dụng có thể chạy độc lập.

## 2. Viết hợp đồng trước khi viết assertion

Giả sử ứng dụng quản lý thẻ học tập theo tenant. Mỗi thẻ có ID, tiêu đề, trạng thái và version. Người dùng được xem các thẻ đã xuất bản của tenant hiện tại, theo thứ tự tiêu đề rồi ID.

Một hợp đồng đủ cụ thể có thể được mô tả như sau:

| Thao tác | Điều kiện | Kết quả quan sát được |
| --- | --- | --- |
| Tạo thẻ | Model hợp lệ, version chưa được cấp | Lưu được dữ liệu và dùng snapshot trả về cho bước tiếp theo. |
| Đọc theo ID | Không có ID tương ứng | Publisher hoàn tất mà không phát entity. |
| Tìm thẻ đã xuất bản | Có dữ liệu nhiều tenant và nhiều trạng thái | Chỉ trả dữ liệu phù hợp cả tenant lẫn trạng thái. |
| Sắp xếp | Nhiều thẻ có cùng tiêu đề | Thứ tự được quyết định tiếp bằng ID. |
| Phân trang | Dataset ổn định, kích thước trang dương | Mỗi trang chứa đúng phần tử theo offset và sort. |
| Cập nhật | Snapshot có version cũ | Báo lỗi optimistic locking trên đường ghi có hỗ trợ. |
| Reactive | Subscriber yêu cầu hoặc hủy | Hành vi tín hiệu đáp ứng kịch bản đã kiểm thử. |
| Projection | Dùng một view đã khai báo | Các thuộc tính view có giá trị đúng và không trộn dữ liệu tenant. |
| Auditing | Có hoặc thiếu auditor theo chính sách | Metadata phản ánh đúng chính sách và thời điểm của thao tác. |

Đây là **hợp đồng của bài thực hành**, gồm cả quy tắc ứng dụng và kỳ vọng hạ tầng. Không phải mọi dòng đều là bảo đảm chung của mọi repository Spring Data. Ví dụ, có `tenantId` trong entity không tự khiến `findById(id)` lọc theo tenant. Luồng ứng dụng cần truy vấn có điều kiện tenant hoặc bước kiểm tra quyền phù hợp.

Hợp đồng CRUD reactive phân biệt tìm không thấy, entity có version và các thao tác xóa theo ID; hãy đối chiếu [ReactiveCrudRepository](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/reactive/ReactiveCrudRepository.html) trước khi gán cùng kỳ vọng cho mọi overload.

## 3. Phân chia trách nhiệm kiểm thử

Không một loại test nào cung cấp đủ bằng chứng cho tất cả yêu cầu.

| Lớp kiểm thử | Đối tượng thực | Điều có thể khẳng định |
| --- | --- | --- |
| Unit test miền | Constructor, value object, lệnh đổi trạng thái | Quy tắc dữ liệu và bất biến của model. |
| Unit test service | Service với repository được thay bằng test double | Nhánh xử lý thiếu dữ liệu, ánh xạ lỗi, phối hợp các thao tác. |
| Repository integration test | Repository proxy, mapping, converter, driver, store | Tên query, binding, materialization và semantics ghi thực tế. |
| Kiểm thử luồng ứng dụng | API hoặc use case cùng hạ tầng liên quan | Quyền truy cập, tenant, auditing và response theo hợp đồng. |
| Kiểm thử hiệu năng | Workload cùng môi trường được kiểm soát | Chi phí và khả năng đáp ứng của workload đó. |

Mock trả `Flux.just(...)` rất hữu ích khi kiểm tra service. Nó không chứng minh derived query được parse đúng, index tồn tại hay converter được đăng ký. Tương tự, test dùng store thật nhưng chỉ gọi `count()` không chứng minh đường đọc entity, projection hay auditing hoạt động.

Có thể tổ chức một lớp hợp đồng dùng chung rồi chạy qua adapter của từng store. Chỉ tái sử dụng các kỳ vọng thật sự chung. Những hành vi về collation, null, enum, transaction hoặc version cần các test bổ sung theo store.

## 4. Model và repository minh họa

### 4.1. Model nhỏ nhưng có đủ ranh giới

Các kiểu Java trong bài nằm trong package được ứng dụng scan; mỗi kiểu public tương ứng với một tệp Java khi người học triển khai.

```java
public enum CardState {
    DRAFT,
    PUBLISHED
}
```

```java
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("capstone_cards")
public record Card(
        @Id String id,
        String tenantId,
        String title,
        CardState state,
        @Version Long version) {

    public Card {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Thiếu ID");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Thiếu tenant");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Thiếu tiêu đề");
        }
        Objects.requireNonNull(state, "Thiếu trạng thái");
        title = title.strip();
    }

    public Card rename(String newTitle) {
        return new Card(id, tenantId, newTitle, state, version);
    }
}
```

ID do fixture hoặc ứng dụng cung cấp. Version dùng `Long` nullable và để `null` khi tạo mới. Với đường mapping MongoDB được chọn, version hỗ trợ phân biệt entity mới và xử lý optimistic locking. Không tự gán version mới trong `rename`.

Tiêu đề được loại khoảng trắng ở hai đầu theo chính sách riêng của model. Constructor không tự bảo đảm độ dài tối đa, chuẩn hóa Unicode hoặc tính duy nhất. Nếu nghiệp vụ cần các yêu cầu đó, phải thêm quy tắc rồi thêm test tương ứng.

### 4.2. Repository có phạm vi truy vấn rõ

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CardRepository extends ReactiveCrudRepository<Card, String> {

    Flux<Card> findByTenantIdAndState(
            String tenantId, CardState state, Pageable pageable);

    Mono<Void> deleteByTenantId(String tenantId);
}
```

Repository sử dụng `Pageable` để chuyển offset, giới hạn và sort xuống query. Kết quả là `Flux<Card>`, không có metadata tổng số trang. Spring Data MongoDB reactive không hỗ trợ trả `Mono<Page<...>>` như một cách lấy `Page` tự động; xem [MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html).

Không dùng `collectList()` rồi mới `subList(...)` để giả lập việc store đã phân trang. Test như vậy có thể kiểm tra đúng danh sách đầu ra nhưng che việc toàn bộ dataset đã được tải về ứng dụng.

## 5. Fixture và lớp hợp đồng tích hợp

### 5.1. Cô lập dữ liệu theo từng test

Mỗi test có hai tenant riêng. Tenant thứ hai cung cấp dữ liệu gây nhiễu để phát hiện query quên điều kiện tenant. Fixture dùng ID có tiền tố riêng, tránh phụ thuộc ID ngẫu nhiên khi so sánh thứ tự.

Test cần database dành riêng cho kiểm thử, dependency MongoDB reactive, JUnit Jupiter, `reactor-test` và một application context tạo được repository. Khi dùng container, chờ store sẵn sàng trước khi chạy và bảo đảm cấu hình kết nối trỏ đúng instance test.

Không dựa vào giả định `@Transactional` sẽ tự rollback mọi reactive test. Transaction manager, Reactor Context, điểm subscribe và deployment store phải phù hợp. Với ví dụ này, dữ liệu được dọn theo tenant sau test, không gọi xóa toàn collection dùng chung.

### 5.2. Lớp hợp đồng cơ sở

Lớp dưới chứa các kiểm tra trực tiếp trên repository thật. Không có mock trong lớp này.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

abstract class ReactiveCardRepositoryContract {

    protected static final Duration VERIFY_LIMIT = Duration.ofSeconds(10);
    protected static final Sort ORDER =
            Sort.by("title").ascending().and(Sort.by("id").ascending());

    protected String tenant;
    protected String otherTenant;

    protected abstract CardRepository repository();

    @BeforeEach
    void allocateFixtureScope() {
        tenant = "contract-" + UUID.randomUUID();
        otherTenant = "other-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanFixtureScope() {
        Mono<Void> cleanup = Flux.just(tenant, otherTenant)
                .concatMap(value -> repository().deleteByTenantId(value))
                .then();

        StepVerifier.create(cleanup)
                .expectComplete()
                .verify(VERIFY_LIMIT);
    }

    protected String id(String suffix) {
        return tenant + "-" + suffix;
    }

    protected Card card(String suffix, String title, CardState state) {
        return new Card(id(suffix), tenant, title, state, null);
    }

    protected Mono<Void> seed(Card... cards) {
        return Flux.fromArray(cards)
                .concatMap(value -> repository().save(value))
                .then();
    }

    @Test
    void saveAndReadPreserveTheSavedSnapshot() {
        Card original = card("01", "  Java  ", CardState.PUBLISHED);

        var scenario = repository().save(original)
                .flatMap(saved -> repository().findById(saved.id())
                        .map(loaded -> Tuples.of(saved, loaded)));

        StepVerifier.create(scenario)
                .assertNext(pair -> {
                    Card saved = pair.getT1();
                    Card loaded = pair.getT2();
                    assertEquals(original.id(), saved.id());
                    assertNotNull(saved.version());
                    assertEquals(saved, loaded);
                    assertEquals("Java", loaded.title());
                })
                .expectComplete()
                .verify(VERIFY_LIMIT);
    }

    @Test
    void missingIdCompletesWithoutAnEntity() {
        StepVerifier.create(repository().findById(id("missing")))
                .expectComplete()
                .verify(VERIFY_LIMIT);
    }

    @Test
    void filterTenantStateAndPageWithAStableOrder() {
        Card outsider = new Card(
                otherTenant + "-01", otherTenant,
                "Java", CardState.PUBLISHED, null);

        var firstPage = PageRequest.of(0, 2, ORDER);
        var secondPage = PageRequest.of(1, 2, ORDER);

        Flux<String> scenario = seed(
                card("02", "Java", CardState.PUBLISHED),
                card("03", "Spring", CardState.PUBLISHED),
                card("01", "Java", CardState.PUBLISHED),
                card("04", "Abc", CardState.DRAFT),
                outsider)
                .thenMany(repository().findByTenantIdAndState(
                        tenant, CardState.PUBLISHED, firstPage))
                .concatWith(repository().findByTenantIdAndState(
                        tenant, CardState.PUBLISHED, secondPage))
                .map(Card::id);

        StepVerifier.create(scenario)
                .expectNext(id("01"), id("02"), id("03"))
                .expectComplete()
                .verify(VERIFY_LIMIT);
    }

    @Test
    void staleVersionFailsAndKeepsTheWinningUpdate() {
        var scenario = repository()
                .save(card("01", "V1", CardState.PUBLISHED))
                .flatMap(saved -> {
                    Card winner = saved.rename("V2");
                    Card stale = saved.rename("V3");
                    return repository().save(winner)
                            .then(repository().save(stale));
                });

        StepVerifier.create(scenario)
                .expectError(OptimisticLockingFailureException.class)
                .verify(VERIFY_LIMIT);

        StepVerifier.create(repository().findById(id("01")))
                .assertNext(current -> assertEquals("V2", current.title()))
                .expectComplete()
                .verify(VERIFY_LIMIT);
    }
}
```

Một adapter trong ứng dụng Spring Boot có thể cung cấp repository cho lớp hợp đồng:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MongoCardRepositoryTest extends ReactiveCardRepositoryContract {

    @Autowired
    CardRepository cardRepository;

    @Override
    protected CardRepository repository() {
        return cardRepository;
    }
}
```

Adapter giả định dự án đã có cấu hình ứng dụng, repository scanning và kết nối store test. Có thể thay full application context bằng data test slice phù hợp phiên bản để giảm chi phí khởi động, miễn slice vẫn có mapping, converter và auditing mà hợp đồng cần kiểm tra.

### 5.3. Điều các test đã chứng minh

Test round trip so sánh snapshot trả về sau lưu với snapshot đọc lại. Nó không dựa vào đồng nhất tham chiếu hoặc số version ban đầu cụ thể. Test query chèn dữ liệu cố ý lệch thứ tự, có tiêu đề trùng và có dữ liệu ngoài phạm vi; assertion không thể vô tình vượt qua chỉ vì insertion order thuận lợi.

Test version tạo hai bản cập nhật từ cùng snapshot rồi ghi tuần tự. Nó tái hiện stale update một cách xác định, không cần hai thread chạy đua ngẫu nhiên. Với MongoDB, khả năng phát hiện lỗi này cần mức xác nhận ghi phù hợp; xem phần optimistic locking trong [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html).

Bộ test trên mới kiểm tra hai trang trên một dataset nhỏ. Nó chưa chứng minh mọi kích thước trang, mọi dữ liệu biên hoặc hành vi khi dataset thay đổi giữa hai query.

## 6. Thiết kế dữ liệu biên có hệ thống

### 6.1. Biên phân trang

Với kích thước trang `k`, hãy kiểm tra các tổng số phần tử khớp query sau:

| Số phần tử | Điều cần kiểm chứng |
| --- | --- |
| `0` | Trang đầu không có phần tử và publisher hoàn tất. |
| `1` | Chỉ một phần tử, không bị nhân đôi bởi mapping hoặc phép ghép. |
| `k - 1` | Trang đầu thiếu một phần tử so với giới hạn. |
| `k` | Trang đầu đầy, trang kế tiếp rỗng. |
| `k + 1` | Trang kế tiếp có đúng một phần tử. |
| `2k` | Hai trang đầy, trang thứ ba rỗng. |

Có thể dùng parameterized test với một `k` nhỏ, chẳng hạn `3`, để fixture dễ đọc. Tạo danh sách ID kỳ vọng độc lập từ dữ liệu đầu vào, rồi so sánh từng trang bằng lát cắt của danh sách đó. Không dùng chính kết quả query đang kiểm thử để xây dựng expected result.

Kiểm tra cả số phần tử từng trang và thứ tự toàn bộ phần tử. Chỉ ghép các trang rồi kiểm tra tổng số có thể bỏ sót tình huống trang đầu trả quá nhiều, trang sau trả quá ít. Để bắt lỗi offset, cần biết chính xác ID nào thuộc từng trang.

Sort theo `title` rồi `id` giúp thứ tự xác định trên dataset cố định. Nó không tạo snapshot nhất quán giữa hai query nếu có insert hoặc delete đồng thời. Nếu API hứa không bỏ sót dữ liệu khi người khác ghi xen kẽ, phải chọn semantics phù hợp, chẳng hạn cơ chế cursor/snapshot được store hỗ trợ, rồi kiểm thử riêng lời hứa đó.

### 6.2. Biên đầu vào và model

| Nhóm dữ liệu | Trường hợp cần chọn | Nơi khẳng định kết quả |
| --- | --- | --- |
| Chuỗi bắt buộc | `null`, rỗng, toàn khoảng trắng | Unit test constructor hoặc validation ở biên API. |
| Độ dài | Ngắn nhất, giới hạn tối đa, vượt giới hạn | Quy tắc nghiệp vụ và kiểu lưu trữ nếu có giới hạn. |
| Unicode | Tiếng Việt có dấu, emoji, biểu diễn Unicode khác nhau | Chính sách chuẩn hóa, sort và collation đã chọn. |
| Ký tự đặc biệt | Dấu nháy, `%`, `_`, ký tự regex | Ý nghĩa query cụ thể, không áp cùng quy tắc cho mọi store. |
| Enum | Mọi giá trị hợp lệ, giá trị lịch sử không còn hợp lệ | Converter và mapping trên dữ liệu thực. |
| Giá trị tùy chọn | Thiếu field, `null`, giá trị mặc định | Hợp đồng model và chính sách đọc dữ liệu cũ. |
| Tập tham số | Tập rỗng, phần tử trùng, tập lớn | Semantics của query và giới hạn thực tế của driver/store. |
| ID | Không tồn tại, khác tenant, định dạng sai | Phân biệt lỗi validation, không tìm thấy và không có quyền. |

Nếu giới hạn tiêu đề tính bằng ký tự người dùng nhìn thấy, `String.length()` chưa chắc là phép đo đúng vì đó là số đơn vị UTF-16. Test phải phản ánh cách nghiệp vụ định nghĩa độ dài. Tương tự, không khẳng định sort chữ có dấu theo thứ tự tiếng Việt nếu chưa cấu hình và kiểm tra collation.

Không đưa `null` vào mọi API như một cách biểu diễn “không giới hạn”. Các abstraction có giá trị thể hiện ý nghĩa đó như `Pageable.unpaged()` và `Sort.unsorted()`. Cách dùng tham số đặc biệt được mô tả trong [Defining Query Methods](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-methods-details.html).

### 6.3. Không gộp mọi lỗi vào một kỳ vọng

Phân biệt các trường hợp sau:

- Constructor từ chối dữ liệu ngay khi tạo object.
- Repository từ chối đối số không hợp lệ khi phương thức được gọi.
- Publisher phát lỗi sau khi subscribe.
- Store từ chối ghi vì ràng buộc hoặc version.

Không mặc định mọi lỗi reactive đều phải xuất hiện qua `onError`; một lời gọi Java với đối số sai có thể bị từ chối ngay trước khi trả publisher. Nếu service chủ động công bố hợp đồng lỗi qua publisher, có thể dùng `Mono.defer(...)` để đưa phần tạo dữ liệu và thực thi vào thời điểm subscription, rồi kiểm thử đúng ranh giới đó.

## 7. Projection, converter và auditing trong cùng bộ hợp đồng

### 7.1. Kiểm thử view và chi phí tải dữ liệu riêng

Có thể thêm closed projection:

```java
public interface CardSummary {
    String getId();
    String getTitle();
}
```

Và thêm vào `CardRepository` một query method trả view:

```java
Flux<CardSummary> findSummaryByTenantIdAndState(
        String tenantId, CardState state, Pageable pageable);
```

Test chức năng cần gọi các accessor và kiểm tra ID, tiêu đề, thứ tự, tenant cùng trường hợp không có dữ liệu. Chỉ kiểm tra object khác `null` chưa đủ để phát hiện property name sai hoặc mapping view sai.

Closed projection cho phép hạ tầng biết các thuộc tính cần dùng, nhưng mức tối ưu còn phụ thuộc store và query. Vì vậy, kết quả view đúng chưa chứng minh chỉ các field đó được tải từ database. Muốn khẳng định giảm dữ liệu truyền, phải quan sát query và response ở tầng store. Đối chiếu [Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html) khi chọn dạng projection.

### 7.2. Converter cần test trực tiếp và test qua mapping

Nếu mở rộng `title` hoặc một field khác thành value object, hãy kiểm tra converter trực tiếp cho dữ liệu hợp lệ, dữ liệu biên và dữ liệu cũ. Sau đó lưu–đọc qua repository thật và kiểm tra biểu diễn raw document trong fixture test.

Hai loại test tìm những lỗi khác nhau: converter chạy đúng khi gọi trực tiếp nhưng chưa được đăng ký vẫn làm integration sai; repository đọc được một object không chứng minh dạng lưu trữ đúng hợp đồng nếu mapping mặc định đã vô tình tạo document lồng thay cho chuỗi scalar.

Cần kiểm tra cả tham số query sử dụng value object khi query đó thuộc phạm vi ứng dụng. Đường chuyển đổi lúc ghi field và lúc bind query có thể bộc lộ các cấu hình thiếu khác nhau.

### 7.3. Auditing cần thời gian và danh tính xác định

Model `Card` tối giản chưa chứa field audit. Khi mở rộng model và bật auditing theo module, thêm các kịch bản:

| Kịch bản | Điều kiểm tra |
| --- | --- |
| Tạo entity | Created metadata được điền theo cấu hình. |
| Cập nhật entity | Created metadata được giữ; modified metadata phản ánh lần cập nhật. |
| Lưu thất bại | Không nhận nhầm metadata trong object thành bằng chứng ghi đã commit. |
| Thiếu auditor | Áp dụng đúng chính sách: cho phép trống, tài khoản hệ thống hoặc lỗi. |
| Hai yêu cầu có auditor khác nhau | Không lẫn danh tính giữa các subscription. |
| Khác múi giờ hoặc độ chính xác lưu trữ | So sánh theo kiểu và độ chính xác được thống nhất. |

Dùng nguồn thời gian điều khiển được, chẳng hạn `DateTimeProvider` phù hợp cấu hình, thay vì ngủ một khoảng rồi hy vọng timestamp thay đổi. Hành vi modified metadata ngay trong lần tạo mới cũng cần theo cấu hình được chọn. Auditing phải được bật qua hạ tầng của store; chỉ thêm annotation vào entity chưa hoàn tất cấu hình. Xem [Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html).

## 8. Kiểm thử reactive bằng tín hiệu

### 8.1. Subscription là một phần của kịch bản

Việc tạo publisher chưa phải bằng chứng thao tác đã hoàn tất. `StepVerifier` cho phép khai báo giá trị và terminal signal, rồi bắt đầu xác minh khi gọi `verify(...)`.

Trong test tích hợp, nên có giới hạn chờ để lỗi kết nối hoặc luồng không kết thúc không làm suite treo vô hạn. `VERIFY_LIMIT` trong ví dụ là giới hạn kỹ thuật của test; nó không phải yêu cầu độ trễ của sản phẩm. Cách dựng kịch bản và timeout được mô tả tại [StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html).

Không gọi `subscribe()` thủ công rồi kiểm tra ngay một biến được callback thay đổi. Test có thể kết thúc trước callback hoặc bỏ mất lỗi. Cũng không gọi `block()` bên trong chuỗi repository reactive để làm thứ tự có vẻ dễ đọc hơn; hãy ghép các bước bằng operator và xác minh publisher cuối.

### 8.2. Demand và cancellation

Phương thức dưới có thể bổ sung vào lớp hợp đồng cơ sở. Setup được chờ hoàn tất trước khi bắt đầu kiểm tra demand của query.

```java
@Test
void querySupportsIncrementalDemandAndCancellation() {
    StepVerifier.create(seed(
                    card("01", "Java", CardState.PUBLISHED),
                    card("02", "Java", CardState.PUBLISHED),
                    card("03", "Spring", CardState.PUBLISHED)))
            .expectComplete()
            .verify(VERIFY_LIMIT);

    Flux<String> result = repository().findByTenantIdAndState(
                    tenant, CardState.PUBLISHED, PageRequest.of(0, 10, ORDER))
            .map(Card::id);

    StepVerifier.create(result, 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(id("01"))
            .thenRequest(1)
            .expectNext(id("02"))
            .thenCancel()
            .verify(VERIFY_LIMIT);
}
```

Test này xác minh một kịch bản demand tăng dần rồi hủy ở biên publisher được quan sát. Nó không chứng minh database chỉ đọc đúng hai document, không có prefetch hoặc cursor đã đóng tức thì. Driver có batch và buffering riêng; cần quan sát thêm tài nguyên, command hoặc kết nối để kết luận về hạ tầng bên dưới.

Nếu service dùng `flatMap`, không mặc định thứ tự đầu ra còn giống đầu vào. Chỉ dùng assertion thứ tự khi hợp đồng bảo đảm thứ tự. Với tập kết quả không có sort, so sánh theo tập hoặc multiset phù hợp, đồng thời vẫn kiểm tra số lượng để không che bản ghi trùng.

### 8.3. Empty, error và fallback

Tại lớp service, thêm test cho các nhánh độc lập:

- Query không có entity và service chuyển sang kết quả “không tìm thấy”.
- Query phát lỗi store và service giữ hoặc ánh xạ lỗi theo hợp đồng.
- Fallback chỉ được subscribe khi nhánh chính rỗng.
- Subscriber hủy trước khi nhánh tiếp theo hoàn tất.

`PublisherProbe` có thể giúp xác minh một publisher thay thế có được subscribe hay không; `TestPublisher` giúp điều khiển tín hiệu của nguồn giả. Đây là công cụ cho logic phối hợp publisher, không phải sự thay thế cho integration với store. Các công cụ được giới thiệu trong [Reactor Testing](https://projectreactor.io/docs/core/release/reference/testing.html).

Đừng dùng `onErrorResume(error -> Mono.empty())` chỉ để test xanh. Nó có thể biến sự cố store thành kết quả “không tồn tại” và làm sai hợp đồng nghiệp vụ.

## 9. Reactor Context và auditor

Context gắn với subscriber và được đọc theo vị trí operator trong chuỗi. Nó phù hợp để truyền dữ liệu ngữ cảnh qua reactive pipeline; một field singleton chứa “người dùng hiện tại” không cung cấp sự cô lập đó. Cơ chế `contextWrite` và `deferContextual` được giải thích trong [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).

Ví dụ sau kiểm tra riêng adapter đọc auditor. Nó chưa kiểm chứng callback auditing của MongoDB:

```java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.data.domain.ReactiveAuditorAware;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.function.Tuples;

class AuditorContextTest {

    @Test
    void eachSubscriptionReadsItsOwnAuditor() {
        ReactiveAuditorAware<String> aware = () -> Mono.deferContextual(
                context -> Mono.justOrEmpty(
                        context.<String>getOrEmpty("test.auditor")));

        Mono<String> first = aware.getCurrentAuditor()
                .contextWrite(context -> context.put("test.auditor", "an"));
        Mono<String> second = aware.getCurrentAuditor()
                .contextWrite(context -> context.put("test.auditor", "binh"));

        StepVerifier.create(Mono.zip(first, second))
                .expectNext(Tuples.of("an", "binh"))
                .expectComplete()
                .verify(Duration.ofSeconds(2));

        StepVerifier.create(aware.getCurrentAuditor())
                .expectComplete()
                .verify(Duration.ofSeconds(2));
    }
}
```

Trong integration mở rộng, đăng ký auditor provider vào cấu hình auditing thực tế, lưu entity dưới các context khác nhau rồi đọc lại metadata. Nếu luồng ứng dụng đổi scheduler hoặc có nhiều yêu cầu đồng thời, kiểm thử cả các đường đó. Test adapter ở trên cho thấy cách đọc context và chính sách empty của adapter, chưa tự chứng minh toàn bộ ứng dụng không rò rỉ context.

## 10. Thời gian ảo dành cho operator thời gian

Với logic retry, timeout hoặc delay ở lớp phối hợp, thời gian ảo giúp kiểm thử mà không chờ đủ thời gian thực. Publisher và operator thời gian cần được tạo bên trong supplier của `withVirtualTime` để dùng scheduler ảo phù hợp.

Ví dụ này mô phỏng một thao tác đọc thất bại tạm thời hai lần rồi thành công. Nó không thực hiện I/O database:

```java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class ReadRetryTest {

    @Test
    void retryTransientReadFailureWithControlledTime() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() -> Mono.defer(() -> {
                    int attempt = attempts.incrementAndGet();
                    return attempt < 3
                            ? Mono.<String>error(new IOException("temporary"))
                            : Mono.just("ok");
                })
                .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                        .jitter(0)
                        .filter(IOException.class::isInstance)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("ok")
                .expectComplete()
                .verify(Duration.ofSeconds(2));
    }
}
```

Hai lần retry cộng với lần gọi đầu tạo tối đa ba attempt. Trong ứng dụng, còn cần test lỗi không được retry, hết số lần retry và việc cancel làm dừng kịch bản. Không áp retry ghi một cách máy móc: sau lỗi mạng, kết quả ghi trước đó có thể chưa rõ; cần thiết kế idempotency và phân loại lỗi tương ứng.

Thời gian ảo không tăng tốc MongoDB, mạng hoặc driver chạy theo tài nguyên ngoài scheduler được thay thế. Cách dùng supplier và các giới hạn của virtual time nằm trong [Reactor Testing: Manipulating Time](https://projectreactor.io/docs/core/release/reference/testing.html#_manipulating_time).

## 11. Đo hiệu năng với workload cụ thể

### 11.1. Đặt câu hỏi đo

Không dùng một test tích hợp mất 300 ms để kết luận repository “nhanh” hay “chậm”. Cần biết khoảng đo chứa khởi động context, mở kết nối, tạo index, query, mapping hay toàn bộ response.

Một kế hoạch đo cho danh sách thẻ có thể gồm:

| Chiều workload | Giá trị cần mô tả |
| --- | --- |
| Quy mô | Số tenant, số thẻ mỗi tenant và phân bố tenant lớn/nhỏ. |
| Độ chọn lọc | Tỷ lệ thẻ PUBLISHED và tỷ lệ query không có kết quả. |
| Dạng dữ liệu | Độ dài tiêu đề, field lớn và quan hệ/value object nếu có. |
| Đường đọc | Entity đầy đủ, projection, trang đầu và trang sâu. |
| Tải đồng thời | Số yêu cầu đang xử lý, tốc độ phát yêu cầu và pool kết nối. |
| Môi trường | Phiên bản ứng dụng, driver, store, index, CPU, RAM và vị trí mạng. |
| Khoảng đo | Từ subscription đến tín hiệu kết thúc hoặc từ yêu cầu API đến response đầy đủ. |

Các giá trị trên là đầu vào của thí nghiệm, không phải số đo đã có. Chọn workload gần nhu cầu vận hành rồi giữ nó ổn định khi so sánh thay đổi.

### 11.2. Chờ thực thi xong trước khi ghi nhận thời gian

Đối với luồng reactive, đo thời gian tạo `Flux` thường chỉ đo assembly. Muốn đo đường query, phải subscribe và quan sát đủ số phần tử cùng terminal signal theo kịch bản.

Nếu chỉ quan sát phần tử đầu tiên, hãy gọi metric đó là thời gian đến phần tử đầu tiên. Nếu hủy sau hai phần tử, kết quả không phải thời gian đọc xong toàn bộ tập dữ liệu. Ghi riêng số lần thành công, lỗi, timeout và cancel; bỏ các lỗi khỏi thống kê độ trễ sẽ làm bức tranh quá lạc quan.

Không thu tất cả dữ liệu vào một danh sách chỉ để đo nếu use case thực tế là streaming. Việc đó đổi áp lực bộ nhớ và hành vi backpressure của workload.

### 11.3. Bộ chỉ số nên đọc cùng nhau

- Độ trễ trung vị và các phân vị như p95, p99, kèm số mẫu và thời gian chạy.
- Throughput thành công trong điều kiện tải đã mô tả.
- Tỷ lệ lỗi, timeout và request bị hủy.
- Thời gian chờ pool, số kết nối, bộ nhớ, CPU và tài nguyên store.
- Số query/command, dữ liệu truyền và chi phí mapping khi cần giải thích nút thắt.

Một vài lần chạy không cho ước lượng p99 ổn định. Tách warm-up khỏi khoảng đo, chạy đủ mẫu và lặp thí nghiệm trong điều kiện tương đương. Nếu dùng tải đóng với số request đồng thời cố định, báo rõ mô hình đó; khi hệ thống chậm, nguồn phát tải cũng có thể tự chậm theo.

Ngưỡng `verify(Duration...)` dùng để chặn test treo không thay cho SLO của sản phẩm. Performance regression cần ngưỡng có căn cứ từ baseline, mức nhiễu môi trường và mục tiêu vận hành.

## 12. Quan sát query plan và index

Với truy vấn tenant + state rồi sort theo title + ID, một index ứng viên trong ví dụ MongoDB là:

```javascript
// Chỉ áp dụng trong môi trường thực hành do người học chuẩn bị.
db.capstone_cards.createIndex({
    tenantId: 1,
    state: 1,
    title: 1,
    _id: 1
});
```

Trong raw document MongoDB, property ID được ánh xạ thành `_id`; do đó query raw và index dùng tên lưu trữ. Index trên là ứng viên để thử nghiệm, không phải kết luận tối ưu cho mọi collation, phân bố dữ liệu hoặc dạng query.

Có thể xem kế hoạch cho một query tương ứng:

```javascript
db.capstone_cards
    .find({ tenantId: "tenant-benchmark", state: "PUBLISHED" })
    .sort({ title: 1, _id: 1 })
    .skip(10000)
    .limit(20)
    .explain("executionStats");
```

Khi triển khai thực hành, xác nhận raw field và biểu diễn enum đúng với mapping thực tế. Đối chiếu số kết quả trả về, số document/key được xem xét, cách dùng index và sort. Cấu trúc explain có thể thay đổi giữa các phiên bản; ý nghĩa quan sát cơ bản được trình bày tại [MongoDB: Interpret Explain Plan Results](https://www.mongodb.com/docs/manual/tutorial/analyze-query-plan/).

Không đặt assertion mọi query phải có đúng một tên stage ở một vị trí JSON cố định nếu mục tiêu thực sự là kiểm soát chi phí. Planner và cấu trúc kế hoạch có thể thay đổi dù hành vi vẫn đúng. Thay vào đó, giữ workload, đọc kế hoạch và dùng chỉ số có quan hệ rõ với yêu cầu hiệu năng.

Trang offset sâu có thể đòi hỏi nhiều công việc hơn trang đầu; có index không loại bỏ mọi chi phí offset. Nếu use case thường duyệt rất sâu, cân nhắc query theo khóa/cursor được store hỗ trợ và kiểm tra các trường sort, giá trị trùng cùng hành vi khi dữ liệu thay đổi.

Nếu API tự ghép `content` từ một query và `total` từ query đếm khác, đo cả hai. Hai query riêng không tự tạo snapshot nhất quán khi có ghi xen kẽ. Khi không cần tổng số, một hợp đồng chỉ cung cấp nội dung và thông tin còn trang sau có thể phù hợp hơn, nhưng phải được thiết kế và kiểm thử riêng.

## 13. Giữ bộ test đáng tin cậy

Các dấu hiệu sau thường làm suite xanh nhưng bằng chứng yếu:

| Cách kiểm tra | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| Chỉ `expectNextCount(3)` | Không biết đó là ba ID nào | Kiểm tra nội dung và phạm vi dữ liệu. |
| Expected lấy từ query đang test | Lỗi bị lặp lại ở cả actual và expected | Xây expected độc lập từ fixture. |
| Dataset chỉ có một tenant | Query bỏ điều kiện tenant vẫn qua | Thêm dữ liệu đối chứng khác tenant. |
| Tên tiêu đề đều khác nhau | Không phát hiện sort thiếu khóa phụ | Thêm tiêu đề trùng, chèn lệch thứ tự. |
| Ngủ để chờ callback | Phụ thuộc tốc độ máy và lịch chạy | Dùng tín hiệu hoàn tất hoặc thời gian ảo phù hợp. |
| `subscribe()` không chờ | Assertion chạy trước I/O và mất lỗi | Xác minh publisher cuối với giới hạn chờ. |
| Dọn dữ liệu chưa subscribe | Fixture cũ vẫn còn trong store | Chờ cleanup hoàn tất như một publisher. |
| Rollback được giả định | Transaction không bao phủ subscription | Xác nhận scope thực tế hoặc cô lập fixture. |
| Chỉ đo assembly publisher | Không đo query thực thi | Đo đường subscription theo terminal signal. |
| Chỉ dùng mock repository | Bỏ qua parser, converter và store | Bổ sung integration cho các hợp đồng cần store. |

Nếu bật chạy song song, không chia sẻ các field fixture mutable giữa nhiều test method bằng một test instance dùng chung mà chưa có biện pháp cô lập. Prefix ngẫu nhiên giúp tách dữ liệu, nhưng không sửa được race do chính test ghi đè `tenant` của nhau.

Khi test thất bại, phân loại theo giai đoạn: tạo context, seed dữ liệu, subscribe, query, mapping, assertion hay cleanup. Lưu thông tin fixture và lỗi đủ để tái hiện, tránh chỉ tăng timeout cho đến khi test qua.

## 14. Tiêu chí hoàn thành bài thực hành

Bài thực hành hoàn thành khi có thể đưa ra bằng chứng cho các yêu cầu sau:

1. Model và biên API có test cho dữ liệu hợp lệ, thiếu, rỗng và những giới hạn nghiệp vụ đã công bố.
2. Repository integration kiểm tra lưu–đọc, không tìm thấy, lọc đúng phạm vi và các cập nhật cần version.
3. Phân trang được thử ở nhiều ranh giới kích thước; thứ tự có khóa phụ và expected result độc lập.
4. Projection và converter được kiểm tra qua mapping thật nếu ứng dụng sử dụng chúng.
5. Auditing có nguồn thời gian/danh tính kiểm soát được và có test chính sách thiếu context.
6. Reactive test kiểm tra giá trị, terminal signal, lỗi, demand và cancellation theo đường gọi liên quan.
7. Fixture được cô lập và cleanup được chờ hoàn tất; kết quả không phụ thuộc thứ tự chạy test.
8. Báo cáo hiệu năng nêu workload, môi trường, cách đo, lỗi và giới hạn kết luận; query plan được dùng khi cần giải thích chi phí.

Một bộ kiểm thử tốt làm rõ lời hứa nào đã được kiểm chứng và lời hứa nào còn cần bằng chứng ở tầng khác. Trong Spring Data Commons, cùng một abstraction có thể được nhiều store hiện thực; vì vậy hợp đồng nghiệp vụ, semantics của module và dữ liệu đo thực tế cần được đối chiếu cùng nhau.
