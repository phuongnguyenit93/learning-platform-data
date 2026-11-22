# Kiểm thử @Query, projection, scrolling và aggregation

Khi xây dựng API tìm kiếm đơn hàng bằng **Spring Data MongoDB**, việc gọi thành công `MongoRepository` hoặc `MongoTemplate` mới chứng minh code chạy được; chưa bảo đảm câu truy vấn lọc đúng tenant, projection trả đúng trường, scrolling không lặp/bỏ sót bản ghi, hay aggregation tính đúng kết quả. Những lỗi này thường chỉ xuất hiện khi có dữ liệu đủ đa dạng, nhiều bản ghi cùng giá trị sắp xếp, field tùy chọn bị thiếu hoặc pipeline có nhiều stage.

Bài học thuộc chương **Kiểm thử**, sử dụng một ví dụ xuyên suốt để kiểm thử bốn cơ chế: **`@Query`, projection, scrolling và aggregation**. Phạm vi của module `SPRING_DATA_MONGODB` gồm kết nối/ánh xạ document, thao tác MongoDB bằng template hoặc repository, truy vấn/index/transaction/reactive access và chẩn đoán hiệu năng; do đó bài nhấn mạnh **integration test trên MongoDB thực**, kiểm tra kết quả ánh xạ, khả năng quan sát command và các giả định về dữ liệu khi mở rộng.

## 1. Nên kiểm thử ở lớp nào?

| Cấp kiểm thử | Phạm vi kiểm tra | Phát hiện được | Giới hạn |
| --- | --- | --- | --- |
| Unit test với fake/mock repository | Quy tắc nghiệp vụ trong service | Cách xử lý kết quả rỗng, quyền truy cập, chuyển đổi DTO | Không chứng minh cú pháp JSON query hoặc pipeline MongoDB chạy đúng |
| **Repository integration test** | Repository/`MongoTemplate` + MongoDB thật | Binding `?0`, ánh xạ BSON, field projection, sort, scroll, aggregation | Chi phí chạy cao hơn unit test |
| API integration test | Security, controller, service, repository và MongoDB | Tenant isolation, response DTO, validation, phân trang ở ranh giới HTTP | Cần dựng thêm ứng dụng và auth test |
| Kiểm thử hiệu năng | Query, index, dữ liệu lớn, concurrency | Latency, `explain`, index scan, bộ nhớ khi scrolling/aggregation | Không thay thế assert tính đúng dữ liệu |

**Khuyến nghị:** dùng unit test để bảo vệ logic service; dùng `@DataMongoTest` và một MongoDB thử nghiệm thực để xác nhận hành vi của Spring Data MongoDB. Với Testcontainers, nên cố định phiên bản MongoDB và dependencies trong dự án. Các ví dụ dưới đây dùng Spring Boot 3.x, Spring Data MongoDB tương thích, JUnit 5, AssertJ và Testcontainers; tên package của Testcontainers có thể khác ở các major version, cần dùng đúng bộ dependency của dự án.

### Ma trận yêu cầu tối thiểu

| Cơ chế | Case đúng | Case biên hoặc lỗi thường gặp |
| --- | --- | --- |
| `@Query` | Trả đúng trạng thái và tenant | Tenant khác cùng mã đơn, kết quả rỗng, literal chứa ký tự đặc biệt |
| Projection | Chỉ trả các thuộc tính cần thiết; đúng tên BSON | Field thiếu, mapping `@Field`, `_id` bị ẩn/mặc định |
| Scrolling | Đi hết tập theo thứ tự ổn định, mỗi ID một lần | Nhiều document cùng sort key, thiếu tie-breaker, thay đổi dữ liệu giữa trang |
| Aggregation | `$match`/`$group`/`$project` trả đúng số lượng và tổng | Không có kết quả, kiểu số, sai tên field/stage, lọt dữ liệu tenant khác |

## 2. Thiết kế một bộ fixture để lộ lỗi

Giả sử ứng dụng lưu đơn hàng của nhiều tenant trong collection `test_orders`. Các field cần thử bao gồm `tenantId`, `status`, `amountCents` và `createdAt`. Sử dụng **số tiền đơn vị cent kiểu `long`** nhằm tránh nhiễu từ làm tròn số thực trong ví dụ; nếu dùng `Decimal128` hoặc `BigDecimal` thì cần thêm test chuyển đổi và độ chính xác riêng.

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("test_orders")
public record OrderDocument(
        @Id String id,
        String tenantId,
        String externalRef,
        String status,
        long amountCents,
        Instant createdAt,
        String internalNote
) {}
```

Tạo dữ liệu có **hai tenant** và năm document cho tenant `alpha`. Tenant `beta` cố tình có `externalRef` giống `alpha` để dễ phát hiện lỗi quên lọc tenant.

| `_id` | Tenant | Mã ngoài | Trạng thái | Số cent | Thời điểm |
| --- | --- | --- | --- | ---: | --- |
| `a-1` | alpha | INV-1 | PAID | 1.200 | 2026-01-01T00:00:01Z |
| `a-2` | alpha | INV-2 | NEW | 900 | 2026-01-01T00:00:02Z |
| `a-3` | alpha | INV-3 | PAID | 800 | 2026-01-01T00:00:03Z |
| `a-4` | alpha | INV-4 | PAID | 500 | 2026-01-01T00:00:04Z |
| `a-5` | alpha | INV-5 | NEW | 700 | 2026-01-01T00:00:05Z |
| `b-1` | beta | INV-1 | PAID | 9.900 | 2026-01-01T00:00:01Z |

Từ fixture này có thể tính bằng tay:

- `@Query` lọc `tenantId = alpha`, `status = PAID` phải trả đúng **3** ID `a-1`, `a-3`, `a-4`.
- Projection theo tenant `alpha` phải có **5** kết quả, chỉ lộ những thuộc tính DTO được phép đọc.
- Scrolling theo `createdAt ASC, _id ASC` với page size 2 phải lần lượt thấy **2 + 2 + 1** document.
- Aggregation trạng thái `PAID` của `alpha` phải có **3 đơn hàng, tổng 2.500 cent**; dữ liệu `beta` không được cộng vào.

Fixture có giá trị hơn khi cố tình chứa dữ liệu trùng tên/mã, trường tùy chọn null hoặc missing, nhiều record cùng timestamp và dữ liệu của tenant khác. Dữ liệu không nên chỉ có một tenant và một trạng thái vì sai query cũng có thể trả kết quả “đúng” tình cờ.

## 3. Khai báo các phương thức repository cần kiểm thử

### 3.1. `@Query` lọc tenant và trạng thái

`@Query` trong Spring Data MongoDB cho phép khai báo biểu thức JSON-like, hỗ trợ binding tham số theo vị trí `?0`, `?1` và các cách binding tương ứng. Ví dụ:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    List<OrderDocument> findByTenantAndStatus(
            String tenantId, String status);
}
```

Tham số được **binder** của Spring Data xử lý: không tự ghép chuỗi JSON từ input của client. Điều kiện tenant phải được lấy từ danh tính đã xác thực và được phép sử dụng; việc test repository chỉ chứng minh **câu query có chứa điều kiện tenant**, chưa thay thế kiểm thử authorization ở API/service.

### 3.2. Projection cho màn hình danh sách

Projection cần được kiểm thử ở **hai mức**: đối tượng trả về có đúng các getter cần thiết, và câu query gửi tới MongoDB có yêu cầu các field phù hợp nếu mục tiêu là giảm payload.

```java
public interface OrderCard {
    String getExternalRef();
    String getStatus();
}
```

Thêm vào `OrderRepository`:

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    fields = "{ '_id': 1, 'externalRef': 1, 'status': 1 }"
)
List<OrderCard> findCards(String tenantId);
```

`OrderCard` là **interface-based projection**. Tên getter phải khớp property mapping hoặc conversion. Việc trả kiểu chỉ có hai getter không tự chứng minh server trả ít field: ở đây phần `fields` định nghĩa projection trong MongoDB query. Nếu chỉ cần một DTO API, vẫn nên cắt field nội bộ ở service và không coi projection là cơ chế phân quyền độc lập.

Với field ánh xạ khác tên Java, ví dụ:

```java
@Document("test_orders")
public record MappedOrder(
        @Id String id,
        @Field("external_ref") String externalRef
) {}
```

Schema BSON thực tế chứa `external_ref`, trong khi code Java dùng `externalRef`; Spring Data mapping thường dịch property path qua metadata khi xây truy vấn/template. Hãy kiểm thử query thực tế và lệnh gửi tới server, nhất là khi dùng custom aggregation/raw BSON, field aliases hoặc converters. Trong ví dụ chính, tên Java và BSON giống nhau để phép test tập trung vào semantics của `@Query`.

### 3.3. Scrolling theo thứ tự ổn định

Spring Data Commons cung cấp kiểu `Window<T>` và `ScrollPosition`. Với repository được hỗ trợ scrolling, khai báo derived query có giới hạn số phần tử một cửa sổ:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

// Thêm trong OrderRepository:
Window<OrderDocument>
findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
        String tenantId, ScrollPosition position);
```

Ở đây sort gồm `createdAt ASC` và `id ASC` để xử lý trường hợp nhiều document cùng timestamp. `id` là tie-breaker duy nhất; trong MongoDB nó tương ứng với `_id` thông qua mapping. **Keyset scrolling** yêu cầu các trường sort cần thiết không null và có sẵn trong kết quả projection. Khi dùng projection cho `Window<T>`, phải giữ cả sort keys và ID; thiếu chúng có thể làm việc tính cursor thất bại.

Hai chế độ khác nhau:

- **Offset**: `ScrollPosition.offset()`; tiếp tục từ vị trí offset. Dễ hiểu nhưng độ trễ có thể tăng khi bỏ qua nhiều document và vị trí bị xê dịch nếu dữ liệu thay đổi.
- **Keyset**: `ScrollPosition.keyset()`; vị trí tiếp tục được xác định từ các khóa sort của phần tử cuối. Tốt cho nhiều trường hợp duyệt sâu, nhưng cần sort ổn định, chỉ mục phù hợp và khóa không null.

### 3.4. Aggregation trực tiếp trong repository

`@Aggregation` cho phép mô tả pipeline với các stage MongoDB. Kết quả dùng projection/DTO tương ứng với field pipeline trả về.

```java
import org.springframework.data.mongodb.repository.Aggregation;

public record PaidTotals(
        String tenantId,
        long orders,
        long cents
) {}

// Thêm trong OrderRepository:
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
    "{ '$group': { '_id': '$tenantId', "
        + "'orders': { '$sum': 1 }, "
        + "'cents': { '$sum': '$amountCents' } } }",
    "{ '$project': { '_id': 0, 'tenantId': '$_id', "
        + "'orders': 1, 'cents': 1 } }"
})
List<PaidTotals> summarizePaid(String tenantId);
```

Phương thức được thêm vào `OrderRepository`; record `PaidTotals` đặt ở file riêng hoặc kiểu phù hợp trong dự án. Đây là **aggregation pipeline** trên collection của `OrderDocument`. `$match` đứng trước `$group` nhằm lọc tenant và trạng thái trước khi cộng. Trong bài toán nhiều tenant, thiếu `tenantId` ở `$match` là lỗi nghiêm trọng dù tổng tiền cuối cùng có vẻ hợp lý.

Một nhóm không có document match sẽ cho **danh sách rỗng**, không tự tạo ra bản ghi với `orders = 0` và `cents = 0`. Nếu API yêu cầu trả zero, service cần xử lý trường hợp rỗng rõ ràng.

## 4. Tạo integration test với @DataMongoTest và Testcontainers

`@DataMongoTest` khởi tạo slice liên quan tới MongoDB repository, `MongoTemplate` và mapping. Với Testcontainers, test chạy trên một MongoDB server thật, giúp bắt lỗi `@Query`, cursor, BSON conversion và pipeline mà mock repository không thể phát hiện.

Ví dụ dưới dùng API `MongoDBContainer` thuộc Testcontainers 1.x. Với Testcontainers 2.x, cần chỉnh import/dependency theo phiên bản mà ứng dụng chọn. Cần Docker hoặc container runtime hỗ trợ Testcontainers để chạy. Cố định image MongoDB tương thích với ứng dụng; `mongo:7.0` trong ví dụ chỉ là phiên bản tham khảo cho môi trường thử nghiệm.

```java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Testcontainers
class OrderRepositoryIT {

    @Container
    static final MongoDBContainer MONGO =
            new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
        registry.add("spring.data.mongodb.database",
                () -> "testing011");
    }

    @Autowired OrderRepository repository;
    @Autowired MongoTemplate mongoTemplate;

    private static Instant second(int second) {
        return Instant.parse(
                String.format("2026-01-01T00:00:%02dZ", second));
    }

    @BeforeEach
    void seedData() {
        repository.deleteAll();
        repository.saveAll(List.of(
            new OrderDocument("a-1", "alpha", "INV-1",
                    "PAID", 1200L, second(1), "note-a1"),
            new OrderDocument("a-2", "alpha", "INV-2",
                    "NEW", 900L, second(2), "note-a2"),
            new OrderDocument("a-3", "alpha", "INV-3",
                    "PAID", 800L, second(3), "note-a3"),
            new OrderDocument("a-4", "alpha", "INV-4",
                    "PAID", 500L, second(4), "note-a4"),
            new OrderDocument("a-5", "alpha", "INV-5",
                    "NEW", 700L, second(5), "note-a5"),
            new OrderDocument("b-1", "beta", "INV-1",
                    "PAID", 9900L, second(1), "note-b1")
        ));
    }

    // Các phương thức @Test của những phần tiếp theo đặt ở đây.
}
```

**Giải thích fixture:** mọi test chạy sau `@BeforeEach` với dữ liệu cố định. `repository.deleteAll()` phù hợp với **database test cách ly**, không dùng đoạn dọn dữ liệu như vậy trên production. Nếu nhiều test class chia sẻ collection/database và chạy song song, việc xóa ở `@BeforeEach` có thể gây race; khi đó dùng collection/database riêng cho từng suite, tắt parallelism hoặc xây chiến lược fixture có cách ly.

Không phụ thuộc vào thứ tự chạy của các test. Những ID `a-1` đến `b-1` là chuỗi không giống ObjectId, giúp assert rõ ràng mà không cần driver tự sinh ID.

## 5. Kiểm thử @Query: đúng filter, đúng dữ liệu tenant

Đặt hai test sau vào `OrderRepositoryIT` ở trên:

```java
@Test
void query_onlyReturnsPaidOrdersOfRequestedTenant() {
    List<OrderDocument> found =
            repository.findByTenantAndStatus("alpha", "PAID");

    assertThat(found).extracting(OrderDocument::id)
            .containsExactlyInAnyOrder("a-1", "a-3", "a-4");

    assertThat(found).allSatisfy(order -> {
        assertThat(order.tenantId()).isEqualTo("alpha");
        assertThat(order.status()).isEqualTo("PAID");
    });
}

@Test
void query_returnsEmptyInsteadOfLeakingOtherTenant() {
    assertThat(repository.findByTenantAndStatus(
            "alpha", "CANCELLED")).isEmpty();

    List<OrderDocument> beta =
            repository.findByTenantAndStatus("beta", "PAID");

    assertThat(beta).extracting(OrderDocument::id)
            .containsExactly("b-1");
}
```

Các assert này kiểm tra **nội dung và tập ID**, thay vì chỉ kiểm tra `size() == 3`. Nếu lập trình viên vô tình bỏ `tenantId` khỏi `@Query`, test sẽ phát hiện vì document `b-1` cũng có trạng thái `PAID`.

Cần bổ sung test về binding nếu input có ký tự đặc biệt:

```java
@Test
void query_bindsParameterAsValueRatherThanJsonFragment() {
    List<OrderDocument> found = repository.findByTenantAndStatus(
            "alpha", "PAID' }, { 'status': 'NEW");

    assertThat(found).isEmpty();
}
```

Test này kiểm tra cách sử dụng API binding an toàn trong đường truy cập đang thử. Vẫn cần validation/authorization ở tầng API và không cấp quyền tenant dựa riêng vào tham số client gửi.

### Truy vấn không có thứ tự sẽ không được assert theo thứ tự

`@Query` ở đây chỉ có `$match`, không có `sort`; MongoDB **không cam kết thứ tự trả về**. Vì vậy test dùng `containsExactlyInAnyOrder(...)`. Muốn assert thứ tự, phải thêm `Sort`, `Pageable` với sort hoặc cấu hình sort tường minh và bảo đảm tie-breaker khi cần.

## 6. Kiểm thử projection: trường trả về và payload

Đặt test tiếp theo trong `OrderRepositoryIT`:

```java
@Test
void projection_returnsCardFieldsForTenant() {
    List<OrderCard> cards = repository.findCards("alpha");

    assertThat(cards).hasSize(5);
    assertThat(cards).extracting(OrderCard::getExternalRef)
            .containsExactlyInAnyOrder(
                    "INV-1", "INV-2", "INV-3", "INV-4", "INV-5");

    assertThat(cards).allSatisfy(card -> {
        assertThat(card.getExternalRef()).isNotBlank();
        assertThat(card.getStatus()).isIn("NEW", "PAID");
    });
}
```

Test trên bảo vệ **contract của projection interface** và tenant filter. Nhưng nó **chưa chứng minh chắc chắn** mọi trường nhạy cảm bị loại khỏi command hay khỏi HTTP JSON, vì kết quả phụ thuộc cơ chế mapping/projection và lớp serialization. Nếu mục tiêu là giảm payload hoặc tránh đưa field nội bộ qua mạng, cần kiểm tra thêm **lệnh `find` thực sự gửi tới MongoDB** (qua `CommandListener`, profiler hoặc quan sát query) và API response.

Với `@Query(fields = "{ '_id': 1, 'externalRef': 1, 'status': 1 }")`, command cần có tài liệu projection tương ứng. Khi field `internalNote` bị loại theo projection, không nên mong projection interface cho phép truy cập hoặc tái tạo trường đó. Nếu muốn kiểm tra field bị thiếu bằng một entity đầy đủ, phải nhớ **partial entity** có thể mang `null` hoặc giá trị mặc định cho field bị loại; không save ngược partial entity vì có nguy cơ ghi đè mất dữ liệu.

### Kiểm thử mapping và field BSON khác tên

Giả sử đổi property `externalRef` trong entity sang `@Field("external_ref")`, phải kiểm chứng dữ liệu lưu thực tế dùng `external_ref`, query và projection vẫn trả về đúng getter Java. Các cách kiểm tra:

1. Tạo document bằng repository có mapping mới.
2. Dùng raw `MongoTemplate.getCollection(...)` đọc document và xác minh tên field BSON thật.
3. Gọi lại projection repository; assert giá trị tương ứng.
4. Nếu dùng `@Query(fields = ...)` hoặc raw aggregation, kiểm tra command/stage đã được mapping đúng tên field; mọi tên BSON được hard-code phải đồng bộ với schema.

Không nên đổi entity fixture giữa chừng mà không cập nhật pipeline và kỳ vọng của các test khác. Bài này cố định field name để các ví dụ tập trung vào mục tiêu chính.

## 7. Kiểm thử scrolling: thứ tự, cursor và tập kết quả

Scrolling dùng để duyệt từng **cửa sổ** dữ liệu; nó khác việc tải cả danh sách bằng `findAll()`, và khác việc cam kết một snapshot bất biến giữa các request. Hai lỗi thường gặp là **trùng/bỏ sót phần tử** và **cursor không thể tính tiếp** do thiếu khóa sort.

### 7.1. Keyset scrolling với dữ liệu ổn định

Các test sau tiếp tục đặt trong lớp `OrderRepositoryIT` đã tạo. Với năm đơn hàng của `alpha`, kích thước cửa sổ là hai nên phải có ba cửa sổ: `[a-1, a-2]`, `[a-3, a-4]`, `[a-5]`.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

@Test
void keysetScroll_returnsAllRowsExactlyOnce() {
    Window<OrderDocument> first =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", ScrollPosition.keyset());

    assertThat(first.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-1", "a-2");
    assertThat(first.hasNext()).isTrue();

    Window<OrderDocument> second =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", first.positionAt(first.size() - 1));

    assertThat(second.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-3", "a-4");
    assertThat(second.hasNext()).isTrue();

    Window<OrderDocument> third =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", second.positionAt(second.size() - 1));

    assertThat(third.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-5");
    assertThat(third.hasNext()).isFalse();
}
```

Test này chứng minh: query lọc đúng `tenantId` trong mỗi cửa sổ, sort đúng như khai báo và cursor dẫn sang phần tiếp theo khi dữ liệu **không thay đổi**.

### 7.2. Đặt nhiều document có cùng createdAt để thử tie-breaker

Nếu chỉ sort theo `createdAt`, hai document có timestamp giống nhau có thể đổi vị trí hoặc tạo biên cửa sổ khó xác định. Hãy bổ sung document mới cùng timestamp với `a-3`, rồi duyệt toàn bộ:

```java
import java.util.ArrayList;
import java.util.List;

@Test
void keysetScroll_handlesEqualTimestampsWithIdTieBreaker() {
    repository.save(new OrderDocument(
            "a-6", "alpha", "INV-6",
            "PAID", 100L, second(3), "note-a6"));

    List<String> ids = new ArrayList<>();
    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<OrderDocument> window =
                repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                        "alpha", position);

        ids.addAll(window.getContent().stream()
                .map(OrderDocument::id).toList());

        if (!window.hasNext()) {
            break;
        }
        position = window.positionAt(window.size() - 1);
    }

    assertThat(ids).containsExactly(
            "a-1", "a-2", "a-3", "a-6", "a-4", "a-5");
    assertThat(ids).doesNotHaveDuplicates();
}
```

Trong trường hợp này `a-3` và `a-6` cùng `createdAt`, nhưng `id` giúp phân định thứ tự. Nếu quên tie-breaker hoặc projection thiếu `createdAt`/`id`, trường hợp biên có thể bị lỗi mà fixture chỉ có timestamp duy nhất không phát hiện được.

### 7.3. So sánh offset và keyset dưới thay đổi dữ liệu

Giả sử client đọc cửa sổ đầu chứa `a-1, a-2`. Trước khi đọc cửa sổ hai, một request khác chèn `a-0` với `createdAt` sớm hơn `a-1`.

- **Offset scrolling:** nếu lấy offset dựa trên số phần tử đã đọc, dữ liệu mới làm dịch vị trí; cửa sổ tiếp theo có thể chứa lại `a-2` hoặc bỏ sót phần tử tùy thao tác concurrent.
- **Keyset scrolling:** cửa sổ tiếp theo dựa vào khóa sort sau `a-2`; việc chèn một document **đứng trước cursor** không làm khóa tiếp tục bị lùi. Tuy nhiên dữ liệu mới đứng trước cursor cũng không được đưa vào các cửa sổ phía sau.
- **Cả hai đều không phải snapshot giao dịch xuyên nhiều request.** Nếu một document cập nhật `createdAt` hoặc bị xóa trong lúc cuộn, kết quả có thể khác so với thời điểm bắt đầu.

Một test minh họa sự khác biệt có thể tạo `a-0` ngay sau cửa sổ đầu và assert cửa sổ tiếp theo của keyset vẫn bắt đầu từ `a-3`:

```java
@Test
void keysetScroll_continuesAfterCursorWhenEarlierRowInserted() {
    Window<OrderDocument> first =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", ScrollPosition.keyset());

    repository.save(new OrderDocument(
            "a-0", "alpha", "INV-0",
            "NEW", 100L, second(0), "inserted-later"));

    Window<OrderDocument> second =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", first.positionAt(first.size() - 1));

    assertThat(second.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-3", "a-4");
}
```

Với offset, có thể dùng `ScrollPosition.offset()` làm điểm xuất phát và `window.positionAt(window.size()-1)` để lấy vị trí kế tiếp; test tương đương nên đưa vào suite nếu API đang dùng offset scrolling. Trên dữ liệu lớn, đo thêm `explain`/thời gian vì offset sâu thường phải bỏ qua nhiều bản ghi.

### 7.4. Quy tắc cho scrolling an toàn

| Điều kiện | Vì sao phải kiểm thử? |
| --- | --- |
| Sort xác định và có khóa duy nhất ở cuối | Tránh trùng/lệch trang khi nhiều record có cùng timestamp |
| Trường sort của keyset khác null và có trong projection | Cursor cần các giá trị khóa để tiếp tục |
| Tenant và bộ lọc giữ nguyên giữa các window | Không vô tình trộn dữ liệu hoặc đổi kết quả khi tiếp tục |
| Cursor do server/ứng dụng tạo và xác minh | Không tin cursor client tự sửa; kiểm tra tenant, filter và sort của cursor |
| Có dữ liệu mới/xóa/sửa trong khi cuộn | Xác định contract: duyệt gần thời gian thực hay cần snapshot nhất quán |
| Hết dữ liệu | `hasNext()` phải false, không tạo loop vô hạn hoặc query lặp |

Nếu API công khai trả cursor dưới dạng chuỗi, cần định nghĩa rõ cách serialize, validate và bảo vệ cursor (ví dụ ký giá trị chứa tenant, sort và filter) ở tầng ứng dụng. `ScrollPosition` là cơ chế tiếp tục truy vấn, **không phải bằng chứng về quyền truy cập**.

## 8. Kiểm thử aggregation: đúng nhóm, đúng tổng, đúng phạm vi

Aggregation thường gây lỗi khó phát hiện hơn query thông thường vì nhiều stage kết hợp: `$match` → `$group` → `$project` → `$sort`. Khi test, **tự tính kỳ vọng từ fixture**, không tạo expected bằng chính pipeline cần kiểm thử.

### 8.1. Kiểm tra @Aggregation trong repository

`OrderRepository.summarizePaid("alpha")` phải cộng `1200 + 800 + 500 = 2500` cent và đếm `3` đơn hàng:

```java
@Test
void aggregation_countsAndSumsOnlyPaidOrdersOfOneTenant() {
    List<PaidTotals> totals = repository.summarizePaid("alpha");

    assertThat(totals).singleElement().satisfies(row -> {
        assertThat(row.tenantId()).isEqualTo("alpha");
        assertThat(row.orders()).isEqualTo(3L);
        assertThat(row.cents()).isEqualTo(2500L);
    });
}

@Test
void aggregation_returnsEmptyWhenNoGroupMatches() {
    assertThat(repository.summarizePaid("missing-tenant")).isEmpty();
}
```

Việc chứa một đơn `beta` trạng thái `PAID` với 9.900 cent giúp test bắt lỗi thiếu tenant ở `$match`. Nếu kết quả của `alpha` là 12.400 cent thì có thể pipeline đã trộn dữ liệu tenant khác. Nếu tổng đúng nhưng số lượng sai, cần xem filter trạng thái và pipeline group.

### 8.2. Kiểm thử pipeline tương đương qua MongoTemplate

Khi aggregation được xây dựng động, nên có test trực tiếp trên `MongoTemplate.aggregate(...)`. Ví dụ pipeline tương ứng:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Test
void mongoTemplateAggregation_matchesKnownFixture() {
    Aggregation pipeline = newAggregation(
            match(Criteria.where("tenantId").is("alpha")
                    .and("status").is("PAID")),
            group("tenantId")
                    .count().as("orders")
                    .sum("amountCents").as("cents"),
            project("orders", "cents")
                    .and("_id").as("tenantId")
                    .andExclude("_id")
    );

    AggregationResults<PaidTotals> result =
            mongoTemplate.aggregate(
                    pipeline, OrderDocument.class, PaidTotals.class);

    assertThat(result.getMappedResults())
            .singleElement()
            .satisfies(row -> {
                assertThat(row.tenantId()).isEqualTo("alpha");
                assertThat(row.orders()).isEqualTo(3L);
                assertThat(row.cents()).isEqualTo(2500L);
            });
}
```

Khi group theo `tenantId`, MongoDB tạo key nhóm ở `_id`. Stage `project` phía sau đổi `_id` thành `tenantId` để ánh xạ kết quả về DTO. Nếu đổi tên field trong document bằng `@Field`, phải kiểm tra việc mapping field path sang BSON trong pipeline DSL và trong `@Aggregation`. Đặc biệt với stage JSON viết tay, không nên giả định mọi đường field đều được chuyển đổi y hệt lệnh query derived.

### 8.3. Các biến thể cần có trong bộ kiểm thử

| Trường hợp | Kỳ vọng |
| --- | --- |
| Tenant có 3 đơn PAID và 2 đơn NEW | Tổng/số lượng chỉ tính 3 đơn PAID |
| Tenant khác có mã ngoài giống nhau | Không làm thay đổi kết quả tenant được hỏi |
| Không có document match | Danh sách kết quả rỗng; service có thể đổi thành tổng bằng 0 theo contract |
| `amountCents` bằng 0 hoặc số âm (refund) | Tổng đúng quy tắc nghiệp vụ, không giả định mọi khoản đều dương |
| Field tổng bị null/missing | Hiểu hành vi `$sum` của MongoDB và quy ước nghiệp vụ cần áp dụng |
| Group theo nhiều trường | `_id` dạng object; DTO/project phải khớp |
| Dùng `$unwind` trên array có null/empty | Xác minh số hàng trước/sau unwind và `preserveNullAndEmptyArrays` nếu cần |
| Truy vấn trả nhiều nhóm | Sort tường minh trước khi assert thứ tự |
| Giá trị tiền lớn hoặc thập phân | Kiểm tra type BSON, chuyển đổi `Decimal128`/`BigDecimal` và overflow |

Lưu ý: `$sum` của MongoDB có quy tắc riêng với giá trị không phải số và kiểu dữ liệu; không dùng `null`/missing như dữ liệu kiểm thử duy nhất. Nếu tiền tệ yêu cầu decimal exact, dùng `Decimal128` hoặc biểu diễn số nguyên với scale thống nhất rồi test chuyển đổi phù hợp.

## 9. Index, explain và giới hạn của kiểm thử tích hợp

Các test vừa viết tập trung **tính đúng đắn**. Kết quả test PASS trên sáu document không có nghĩa query chạy nhanh trên sáu triệu document. Khi chuyển sang kiểm thử hiệu năng, cần chuẩn bị index phù hợp với filter/sort.

Ví dụ có thể tạo compound index phục vụ truy vấn theo tenant và scrolling:

```java
import org.springframework.data.domain.Sort.Direction;
import org.springframework.data.mongodb.core.index.Index;

// Chỉ chạy trong setup hoặc migration dành cho môi trường test phù hợp.
mongoTemplate.indexOps(OrderDocument.class)
        .ensureIndex(new Index()
                .on("tenantId", Direction.ASC)
                .on("createdAt", Direction.ASC)
                .on("_id", Direction.ASC));
```

Đối với `findByTenantAndStatus` có thể cần index `{ tenantId: 1, status: 1 }` hoặc một compound index bao gồm các sort field tùy workload. Index cho scrolling và aggregation có thể khác nhau; không nên chọn một index chỉ vì mọi test logic đều PASS.

Kiểm tra `explain` trên một truy vấn gần với query thực:

```java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

Document explain = mongoTemplate.getCollection("test_orders")
        .find(Filters.eq("tenantId", "alpha"))
        .sort(Sorts.ascending("createdAt", "_id"))
        .explain();

// Xem queryPlanner / winningPlan / executionStats tùy verb.
```

Đọc `explain` để biết kế hoạch và index được chọn, số document/key được xét khi có execution stats, các stage có sort hoặc scan lớn. **Không hard-code kỳ vọng đúng một plan duy nhất** cho mọi phiên bản/tập dữ liệu: optimizer có thể chọn phương án khác nhau. Test hiệu năng cần chạy với kích thước dataset đủ đại diện và nên có ngưỡng thực tế riêng cho môi trường CI/performance.

## 10. Những bẫy kiểm thử thường làm test PASS giả

### Mock repository hoặc MongoTemplate

`when(repository.findByTenantAndStatus(...)).thenReturn(...)` chỉ xác nhận service đã dùng mock như được cấu hình; test này **không chạy JSON trong `@Query`**. Mock tốt cho unit test service, còn repository integration test phải đi qua MongoDB thật.

### Fixture một tenant hoặc một trạng thái

Nếu tất cả document đều của `alpha`, quên filter `tenantId` vẫn có thể cho kết quả đúng. Nếu mọi document đều `PAID`, quên `status` cũng dễ qua test. Fixture phải cố tình phân biệt các điều kiện.

### Assert theo thứ tự khi không có sort

MongoDB không đảm bảo thứ tự natural order cố định. Nếu `@Query` không có sort, dùng `containsExactlyInAnyOrder` hoặc so tập ID. Với scrolling, sort phải được định nghĩa cụ thể và có tie-breaker.

### Phép kiểm tra expected dựa trên cùng logic sai

Nếu test tính expected aggregate bằng một aggregation thứ hai xây từ cùng helper, cả hai có thể sai giống nhau. Nên tính tay từ fixture hoặc dùng thuật toán đối chiếu độc lập bằng Java trên một tập dữ liệu test nhỏ.

### Quên kiểm tra tên field và kiểu BSON

`@Field("external_ref")`, `@Id`, `Instant`, `Decimal128`, custom converters và projected DTO ảnh hưởng mapping. Khi thất bại chỉ trong production, hãy dùng raw BSON trong integration test để kiểm tra field thực tế. Với `Instant`, chú ý độ chính xác lưu trữ/rounding theo kiểu BSON timestamp/date và nhất quán timezone.

### Giả định scrolling là snapshot

Keyset giúp tiếp tục ổn định dựa trên sort keys, nhưng **không tự làm dữ liệu bất biến**. Với API đòi xuất toàn bộ dữ liệu nhất quán, cần thiết kế snapshot hoặc cơ chế checkpoint phù hợp, hoặc chấp nhận semantics duyệt gần thời gian thực rồi test theo contract đó.

### Bỏ qua lỗi runtime

Test chỉ assert không exception chưa đủ: khi dùng reactive API, cần subscribe/await publisher; khi dùng transaction, kiểm tra commit/rollback; với aggregation hoặc bulk, kiểm tra kết quả thực sự lưu và trả về. Nếu sử dụng `ReactiveMongoTemplate`, test có thể dùng Reactor Test `StepVerifier` để chờ terminal signal trước khi assert dữ liệu.

```java
// reactiveRepository: ReactiveMongoRepository với cùng domain.
// Ví dụ kiểm tra kết quả, không dừng ở việc tạo Flux.
StepVerifier.create(
        reactiveRepository.findByTenantIdAndStatus(
                "alpha", "PAID").collectList())
        .assertNext(found ->
                assertThat(found).hasSize(3))
        .verifyComplete();
```

## 11. Bộ tiêu chí hoàn thành cho @Query, projection, scrolling, aggregation

| Thành phần | Cần chứng minh qua test |
| --- | --- |
| `@Query` | Binding đúng, filter đầy đủ, không trộn tenant, case rỗng và input đặc biệt |
| Projection | Getter/DTO đúng, query projection đúng field, không trả field nội bộ ra API, mapping BSON phù hợp |
| Scrolling | Thứ tự xác định, cursor đúng, đúng tập ID qua nhiều window, tie-breaker, khi dữ liệu thay đổi có semantics rõ |
| Aggregation | Stage/filter đúng, count/sum/tên field/kiểu dữ liệu chính xác, case không có group, kết quả không trộn tenant |
| Hạ tầng test | MongoDB thật, fixture cách ly, cùng phiên bản server/driver đã chọn, test có thể chạy lặp |
| Hiệu năng | Index và `explain` được kiểm tra trên workload đại diện; không dùng kết quả của fixture nhỏ để kết luận production |

### Bài thực hành

1. Thêm `@Query` tìm đơn theo `tenantId`, `status` và ngưỡng `amountCents`; viết test cho ba điều kiện và một tenant khác có dữ liệu trùng.
2. Tạo một projection chỉ gồm `externalRef` và `status`; kiểm tra API response, raw BSON field mapping và command projection.
3. Thêm hai record cùng `createdAt`; duyệt hết bằng keyset với cửa sổ hai phần tử, assert tập ID không trùng/bỏ sót. Thử chèn một record trước cursor giữa hai lần lấy window và mô tả khác biệt với offset.
4. Mở rộng aggregation nhóm theo `status`, tính count và sum cho mỗi nhóm; tính expected trực tiếp từ fixture, kiểm tra nhóm rỗng và field số.
5. Tăng số document để dùng `explain`, quan sát index và đo thời gian; tách kết luận hiệu năng khỏi các assertion về tính đúng đắn.

**Điểm cần nhớ:** Kiểm thử Spring Data MongoDB hiệu quả phải dùng dữ liệu cố tình gây phân biệt để xác minh **`@Query` lọc đúng, projection trả đúng, scrolling duyệt đúng và aggregation tính đúng**. `@DataMongoTest` với MongoDB thực cho phép kiểm chứng cả BSON mapping và query engine; unit test/service test bổ sung việc phân quyền và contract API, còn kiểm thử `explain`/hiệu năng kiểm tra hành vi khi dữ liệu tăng.
