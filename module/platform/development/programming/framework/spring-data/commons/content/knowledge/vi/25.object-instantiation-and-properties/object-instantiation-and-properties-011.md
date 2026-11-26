# Kiểm thử mô hình miền trước khi tối ưu cơ chế ánh xạ

## 1. Vì sao cần chứng minh tính đúng trước?

Cơ chế ánh xạ của Spring Data phải tạo object từ dữ liệu lưu trữ, chuyển đổi kiểu và cung cấp giá trị cho các thuộc tính. Hạ tầng có thể dùng constructor, factory, field accessor, setter hoặc cơ chế tạo accessor tối ưu tùy mô hình và module.

Một thay đổi nhằm giảm chi phí khởi tạo có thể vô tình:

- Bỏ qua validation vốn chạy trong constructor.
- Làm mất ID hoặc version khi tạo bản sao immutable.
- Thay đổi giá trị do getter, setter hoặc converter xử lý.
- Khiến dữ liệu lịch sử không còn nạp được.
- Làm framework nhận nhầm object đã tồn tại là object mới.
- Ghi đè dữ liệu chưa được nạp khi lưu một object không đầy đủ.

Vì vậy, câu hỏi đầu tiên không phải là “có dùng generated accessor không?”, mà là “mô hình được tạo, đọc, sửa và lưu có giữ đúng trạng thái và quy tắc nghiệp vụ không?”.

Trong Spring Data Commons, các abstraction như metadata entity, metadata thuộc tính và repository giúp diễn đạt mô hình chung. Nhưng cách converter, repository và store thực hiện một thao tác phải được kiểm chứng trên module thực tế.

## 2. Xác định hợp đồng cần giữ nguyên

Trước khi tối ưu, viết ra những hành vi quan sát được mà ứng dụng cần giữ.

| Nhóm hành vi | Ví dụ hợp đồng |
| --- | --- |
| Invariant nghiệp vụ | SKU không rỗng, số lượng lớn hơn 0, đơn giá không âm |
| Khởi tạo | Creator nhận đủ dữ liệu cần thiết và không âm thầm làm mất trạng thái |
| Bản sao immutable | Đổi số lượng giữ nguyên ID, SKU, đơn giá và version |
| Mapping | Tên thuộc tính, tên field lưu trữ và kiểu dữ liệu được xử lý đúng |
| Vòng đời persistence | Tạo mới, nhận ID, cập nhật và optimistic locking hoạt động đúng |
| Dữ liệu lịch sử | Bản ghi cũ được nạp hoặc từ chối theo chính sách đã định |
| Projection | Kiểu kết quả chỉ chứa dữ liệu được yêu cầu, không bị dùng như entity đầy đủ |
| Hiệu năng | Đạt mục tiêu đo lường mà không phá các hợp đồng trên |

Không cần một test cho mọi dòng code. Cần những test có khả năng phát hiện thay đổi sai về hành vi.

Ví dụ, test chỉ xác nhận một getter trả lại field vừa được gán ít giá trị hơn test chứng minh một method tạo bản sao không làm mất version dùng cho optimistic locking.

## 3. Mô hình mẫu: dòng mua hàng immutable

Ví dụ sử dụng số nguyên biểu diễn đơn giá theo đơn vị tiền nhỏ nhất để tập trung vào khởi tạo và mapping. Đây không phải mô hình tiền tệ đầy đủ cho mọi hệ thống.

Model sử dụng annotation của Spring Data Commons:

```java
package com.example.purchase;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.Version;

public final class PurchaseLine {

    @Id
    private final String id;

    private final String sku;
    private final int quantity;
    private final long unitPriceInCents;

    @Version
    private final Long version;

    @PersistenceCreator
    public PurchaseLine(
            String id,
            String sku,
            int quantity,
            long unitPriceInCents,
            Long version) {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        if (unitPriceInCents < 0) {
            throw new IllegalArgumentException(
                    "unitPriceInCents must not be negative");
        }

        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceInCents = unitPriceInCents;
        this.version = version;
    }

    public static PurchaseLine create(
            String sku,
            int quantity,
            long unitPriceInCents) {
        return new PurchaseLine(
                null,
                sku,
                quantity,
                unitPriceInCents,
                null);
    }

    public PurchaseLine withId(String newId) {
        return new PurchaseLine(
                newId,
                sku,
                quantity,
                unitPriceInCents,
                version);
    }

    public PurchaseLine withVersion(Long newVersion) {
        return new PurchaseLine(
                id,
                sku,
                quantity,
                unitPriceInCents,
                newVersion);
    }

    public PurchaseLine changeQuantity(int newQuantity) {
        return new PurchaseLine(
                id,
                sku,
                newQuantity,
                unitPriceInCents,
                version);
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public long getUnitPriceInCents() {
        return unitPriceInCents;
    }

    public Long getVersion() {
        return version;
    }

    @Transient
    public long getTotalInCents() {
        return Math.multiplyExact(
                (long) quantity,
                unitPriceInCents);
    }
}
```

### Các chủ đích trong thiết kế

- Constructor cho phép ID và version null vì object mới có thể chưa được persistence cấp metadata.
- Validation áp dụng cả khi ứng dụng tạo mới và khi mapper tái tạo dữ liệu.
- Factory `create` dành cho tạo mới, không được đánh dấu là persistence creator.
- Creator dùng để đọc nhận đủ cả ID và version.
- Các method thay đổi trạng thái trả instance mới.
- Tổng tiền là giá trị suy ra, không lưu thành một nguồn dữ liệu thứ hai.
- `Math.multiplyExact` làm lộ lỗi tràn số thay vì trả một kết quả sai trong im lặng.

Ví dụ dùng class thông thường, nên constructor mapping cần có thông tin tên tham số phù hợp. Giả định artifact được biên dịch với metadata tên tham số, chẳng hạn qua `-parameters`, hoặc cơ chế tương đương mà mapper hỗ trợ.

`@PersistenceCreator` chỉ định creator; nó không tự cung cấp tên cho mọi tham số bị thiếu metadata.

Các ví dụ kiểm thử bên dưới dùng JUnit Jupiter. Code được trình bày để đưa vào project kiểm thử của ứng dụng, không thay thế cấu hình dependency và môi trường store thực tế.

## 4. Lớp kiểm thử thứ nhất: nghiệp vụ thuần Java

Kiểm thử lớp này không cần application context hoặc database.

### 4.1. Từ chối trạng thái không hợp lệ

```java
package com.example.purchase;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class PurchaseLineInvariantTest {

    @Test
    void rejectsInvalidBusinessState() {
        assertThrows(
                IllegalArgumentException.class,
                () -> PurchaseLine.create(null, 1, 100));

        assertThrows(
                IllegalArgumentException.class,
                () -> PurchaseLine.create("  ", 1, 100));

        assertThrows(
                IllegalArgumentException.class,
                () -> PurchaseLine.create("BOOK-01", 0, 100));

        assertThrows(
                IllegalArgumentException.class,
                () -> PurchaseLine.create("BOOK-01", 1, -1));
    }
}
```

Những test này xác nhận chính sách của domain. Chúng chưa chứng minh Spring Data sử dụng đúng constructor khi đọc dữ liệu.

Nếu có yêu cầu cho phép số lượng 0 để biểu diễn một trạng thái riêng, phải đổi hợp đồng và test tương ứng. Không giữ validation chỉ vì nó có trong ví dụ.

### 4.2. Kiểm tra bản sao không làm mất metadata

```java
@Test
void quantityChangePreservesPersistentIdentity() {
    PurchaseLine original =
            new PurchaseLine(
                    "line-17",
                    "BOOK-01",
                    2,
                    125_000L,
                    3L);

    PurchaseLine changed = original.changeQuantity(5);

    assertAll(
            () -> assertNotSame(original, changed),
            () -> assertEquals(2, original.getQuantity()),
            () -> assertEquals(5, changed.getQuantity()),
            () -> assertEquals(
                    original.getId(),
                    changed.getId()),
            () -> assertEquals(
                    original.getSku(),
                    changed.getSku()),
            () -> assertEquals(
                    original.getUnitPriceInCents(),
                    changed.getUnitPriceInCents()),
            () -> assertEquals(
                    original.getVersion(),
                    changed.getVersion()),
            () -> assertEquals(
                    625_000L,
                    changed.getTotalInCents()));
}
```

Đoạn method dùng các static assertion tương ứng của JUnit Jupiter và được đặt trong test class.

Test này phát hiện một lỗi quan trọng: method tạo bản sao gọi nhầm factory `create`, khiến ID và version trở về null.

Không chỉ assert số lượng mới. Nếu metadata bị mất, phép tính nghiệp vụ vẫn có thể đúng nhưng lần lưu tiếp theo lại sai vòng đời.

### 4.3. Kiểm tra đường cập nhật metadata

Các method `withId` và `withVersion` có thể được hạ tầng immutable mapping sử dụng khi module hỗ trợ cơ chế đó.

Cần kiểm tra chúng:

- Chỉ thay giá trị được yêu cầu.
- Giữ nguyên tất cả trạng thái còn lại.
- Không sửa instance ban đầu.
- Không vô tình chuẩn hóa lại dữ liệu theo một chính sách khác.

Không viết test giả định mọi store đều tự động nhận diện và sử dụng các method này. Việc hạ tầng có thực sự dùng được chúng thuộc lớp kiểm thử mapping và integration.

### 4.4. Kiểm tra giới hạn số học

```java
@Test
void totalFailsExplicitlyOnOverflow() {
    PurchaseLine line =
            PurchaseLine.create(
                    "BULK-01",
                    2,
                    Long.MAX_VALUE);

    assertThrows(
            ArithmeticException.class,
            line::getTotalInCents);
}
```

Nếu domain yêu cầu từ chối tràn số ngay từ lúc tạo object, hãy đưa kiểm tra vào creator và đổi test để phản ánh chính sách đó.

Điểm cần chốt trước tối ưu là lỗi số học được phát hiện ở đâu, không phải chọn cách nhanh hơn rồi để hành vi thay đổi ngẫu nhiên.

## 5. Lớp kiểm thử thứ hai: converter và metadata thực tế

Một object tạo được bằng `new` chưa chắc được mapper tái tạo đúng. Kiểm thử converter giúp phát hiện lỗi creator, tên thuộc tính, kiểu dữ liệu và thuộc tính không persistent.

Phần sau minh họa Spring Data MongoDB. Không dùng `MappingMongoConverter` để suy ra hành vi của JDBC hoặc JPA.

### 5.1. Fixture converter tối thiểu

```java
package com.example.purchase;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;
import org.springframework.data.mongodb.core.convert.NoOpDbRefResolver;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class PurchaseLineMongoMappingTest {

    private MappingMongoConverter converter;

    @BeforeEach
    void setUp() throws Exception {
        MongoMappingContext context = new MongoMappingContext();
        context.setInitialEntitySet(Set.of(PurchaseLine.class));
        context.afterPropertiesSet();

        converter = new MappingMongoConverter(
                NoOpDbRefResolver.INSTANCE,
                context);
        converter.afterPropertiesSet();
    }

    @Test
    void readsRawDocumentThroughPersistentCreator() {
        Document source = new Document("_id", "line-17")
                .append("sku", "BOOK-01")
                .append("quantity", 2)
                .append("unitPriceInCents", 125_000L)
                .append("version", 3L);

        PurchaseLine restored =
                converter.read(PurchaseLine.class, source);

        assertAll(
                () -> assertEquals(
                        "line-17",
                        restored.getId()),
                () -> assertEquals(
                        "BOOK-01",
                        restored.getSku()),
                () -> assertEquals(
                        2,
                        restored.getQuantity()),
                () -> assertEquals(
                        125_000L,
                        restored.getUnitPriceInCents()),
                () -> assertEquals(
                        Long.valueOf(3L),
                        restored.getVersion()),
                () -> assertEquals(
                        250_000L,
                        restored.getTotalInCents()));
    }

    @Test
    void writesOnlyExpectedPersistentState() {
        PurchaseLine line =
                new PurchaseLine(
                        "line-17",
                        "BOOK-01",
                        2,
                        125_000L,
                        3L);

        Document target = new Document();
        converter.write(line, target);

        assertAll(
                () -> assertEquals(
                        "line-17",
                        target.get("_id")),
                () -> assertEquals(
                        "BOOK-01",
                        target.get("sku")),
                () -> assertEquals(
                        2,
                        ((Number) target.get("quantity")).intValue()),
                () -> assertEquals(
                        125_000L,
                        ((Number) target.get("unitPriceInCents"))
                                .longValue()),
                () -> assertEquals(
                        3L,
                        ((Number) target.get("version")).longValue()),
                () -> assertFalse(
                        target.containsKey("totalInCents")));
    }
}
```

Fixture này không cần kết nối MongoDB và không dành để kiểm tra DBRef. `NoOpDbRefResolver` phù hợp vì model ví dụ không có DBRef.

Nếu ứng dụng có custom conversions, naming strategy, type mapper hoặc cấu hình mapping khác, fixture tối thiểu không thay thế converter đã cấu hình trong ứng dụng. Cần bổ sung kiểm thử sử dụng cấu hình đó.

### 5.2. Vì sao chuẩn bị raw document độc lập?

Chỉ kiểm tra:

```text
object → converter.write → converter.read → object
```

có thể bỏ sót lỗi mà cả chiều ghi và chiều đọc cùng mắc theo một quy ước sai.

Ví dụ, ứng dụng cần field `unit_price`, nhưng converter ghi và đọc cùng tên `unitPrice`. Round-trip tự tạo vẫn có thể pass trong khi dữ liệu thật không tương thích.

Vì vậy nên có cả:

- Fixture raw được thiết kế theo schema hoặc dữ liệu thực tế.
- Kiểm tra chiều đọc độc lập.
- Kiểm tra chiều ghi độc lập.
- Một số round-trip đại diện.

Không cần sao chép nguyên document nội bộ rồi assert tuyệt đối mọi key như `_class` nếu ứng dụng không coi chi tiết đó là hợp đồng. Tập trung vào trạng thái persistent và quy tắc ứng dụng phụ thuộc.

### 5.3. Kiểm tra dữ liệu không hợp lệ khi nạp

Tạo raw document có `quantity = 0`, rồi đọc bằng converter.

Kỳ vọng nghiệp vụ là dữ liệu bị từ chối vì constructor không chấp nhận số lượng đó. Lỗi có thể được bọc trong exception khởi tạo hoặc conversion.

Khi kiểm tra lỗi:

- Xác nhận nguyên nhân liên quan invariant mong đợi.
- Phân biệt với lỗi không tìm thấy creator hoặc lỗi kiểu dữ liệu.
- Tránh buộc test phụ thuộc toàn bộ chuỗi thông báo nội bộ.
- Không bắt mọi exception rồi coi đó là PASS.

Ví dụ, một lỗi thiếu dependency cũng làm test thất bại, nhưng không chứng minh validation của constructor đã được thực thi.

## 6. Ma trận dữ liệu cần thử trước khi thay đổi cơ chế khởi tạo

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Đầy đủ field, đúng kiểu | Giá trị được gán đúng và giữ metadata |
| Thiếu field tùy chọn | Default hoặc null đúng chính sách |
| Thiếu field bắt buộc | Lỗi hoặc migration đúng kế hoạch |
| Giá trị null | Không bị đánh đồng với 0 hoặc chuỗi rỗng |
| Numeric khác kiểu biểu diễn | Conversion đúng hoặc từ chối rõ ràng |
| Tên field khác tên Java | Metadata đổi tên được áp dụng |
| Thuộc tính kế thừa hoặc bị shadow | Đúng thuộc tính tham gia mapping |
| Field hoặc getter tính toán | Không bị lưu nhầm nếu phải transient |
| Creator có validation | Validation vẫn chạy khi nạp |
| Object immutable có ID/version | Bản sao giữ đủ trạng thái persistence |
| Dữ liệu được projection một phần | Không bị coi là entity đầy đủ để ghi lại |

Không cần triển khai mọi trường hợp nếu domain không có đặc điểm tương ứng. Chọn dữ liệu có khả năng làm thay đổi quyết định thiết kế.

### Dữ liệu lịch sử là một đầu vào riêng

Một constructor mới cấm null có thể đúng với dữ liệu được tạo từ hôm nay nhưng phá khả năng đọc dữ liệu đã lưu nhiều năm trước.

Trước khi siết invariant hoặc đổi primitive sang wrapper, cần xác định:

1. Dữ liệu cũ có trạng thái nào?
2. Domain có chấp nhận chúng không?
3. Có cần migration không?
4. Giá trị mặc định có làm mất ý nghĩa “chưa biết” không?
5. Có thể triển khai nhiều phiên bản ứng dụng cùng lúc không?

Không xử lý dữ liệu lịch sử bằng cách âm thầm đổi constructor thành “luôn chấp nhận mọi thứ” chỉ để benchmark chạy được.

## 7. Lớp kiểm thử thứ ba: thao tác với store thật

Converter test không chứng minh database cấp ID, kiểm tra version hoặc thực thi câu lệnh như mong đợi.

Với integration test, cần một môi trường store dành cho kiểm thử và cấu hình giống đường ứng dụng sử dụng ở các điểm quan trọng: converter, callback, write concern, transaction hoặc naming strategy.

### 7.1. Kiểm tra vòng đời của object immutable

Đoạn method sau được đặt trong integration test đã cung cấp field `MongoTemplate template` kết nối tới MongoDB kiểm thử:

```java
@Test
void savesAndReloadsImmutableLine() {
    String collection =
            "purchase_line_test_"
                    + java.util.UUID.randomUUID()
                            .toString()
                            .replace("-", "");

    try {
        PurchaseLine draft =
                PurchaseLine.create(
                        "BOOK-01",
                        2,
                        125_000L);

        PurchaseLine saved =
                template.save(draft, collection);

        assertAll(
                () -> assertNull(draft.getId()),
                () -> assertNull(draft.getVersion()),
                () -> assertNotNull(saved.getId()),
                () -> assertNotNull(saved.getVersion()));

        PurchaseLine loaded =
                template.findById(
                        saved.getId(),
                        PurchaseLine.class,
                        collection);

        assertNotNull(loaded);
        assertAll(
                () -> assertEquals(
                        saved.getId(),
                        loaded.getId()),
                () -> assertEquals(
                        saved.getVersion(),
                        loaded.getVersion()),
                () -> assertEquals(
                        2,
                        loaded.getQuantity()),
                () -> assertEquals(
                        250_000L,
                        loaded.getTotalInCents()));
    } finally {
        template.dropCollection(collection);
    }
}
```

Model không cần `@Document` trong ví dụ vì collection được truyền tường minh. Nếu dùng repository, phải cấu hình domain type, collection và package scanning theo module.

Test cố ý:

- Giữ kết quả `save`.
- Không kỳ vọng instance immutable ban đầu bị gán ID tại chỗ.
- Không đóng đinh version ban đầu vào một con số khi mục tiêu chỉ là có metadata hợp lệ.
- Đọc lại dữ liệu authoritative từ store.

Giả định cấu hình MongoDB hỗ trợ ID `String` sinh tự động và các annotation của model theo phiên bản sử dụng. Nếu ứng dụng có chính sách ID riêng, fixture và kỳ vọng phải theo chính sách đó.

### 7.2. Kiểm tra optimistic locking bằng hai bản đọc

Kịch bản có ý nghĩa hơn việc chỉ xác nhận field version tồn tại:

1. Lưu một dòng mua hàng.
2. Đọc nó thành hai instance độc lập A và B.
3. A thay đổi số lượng rồi được lưu thành công.
4. B vẫn giữ version cũ.
5. Lưu thay đổi của B và xác nhận lỗi optimistic locking theo module.

Với đường MongoDB hỗ trợ versioning, test có thể kỳ vọng `OptimisticLockingFailureException` khi lưu instance cũ, trong cấu hình ghi có xác nhận phù hợp.

Kịch bản phát hiện lỗi method tạo bản sao không giữ version hoặc cấu hình ghi không thực hiện kiểm tra mong muốn.

Nếu đổi sang custom update, bulk operation hoặc native client, phải kiểm tra lại. Những đường đó không tự được coi là tương đương với repository/template save có quản lý version.

### 7.3. Kiểm tra nhận diện object mới

ID và version có thể tham gia quyết định object mới hay đã tồn tại.

Đặc biệt, với chiến lược dựa trên version dạng nullable, một bản sao làm mất version có thể bị xem là mới dù vẫn có ID, tùy hạ tầng và cấu hình.

Cần có test:

- Tạo mới chỉ tạo bản ghi theo dự kiến.
- Cập nhật không biến thành một thao tác tạo mới ngoài ý muốn.
- Method domain không làm mất metadata.
- Đối tượng triển khai `Persistable`, nếu có, trả trạng thái `isNew` đúng vòng đời.

Không sửa chiến lược `isNew` để che lỗi mất metadata trong method tạo bản sao.

## 8. Projection và dữ liệu chỉ được nạp một phần

Một tối ưu thường gặp là chỉ lấy những field cần thiết. Đây là tối ưu query và dữ liệu truyền, khác với tối ưu creator.

Ví dụ DTO:

```java
public record PurchaseLineSummary(
        String sku,
        int quantity) {
}
```

Khi module hỗ trợ DTO projection, canonical constructor có thể dùng để dựng kết quả này.

Kiểm thử cần chứng minh:

- DTO nhận đúng các field được chọn.
- Constructor phù hợp tên, alias và kiểu dữ liệu của query.
- Null từ kết quả hợp lệ được xử lý theo chính sách.
- Projection không bị đưa vào đường lưu entity đầy đủ.

Không nạp một phần dữ liệu vào `PurchaseLine`, điền phần còn lại bằng default rồi gọi `save` như thể đã có toàn bộ trạng thái. Tùy store và thao tác replacement/update, điều đó có thể ghi đè dữ liệu chưa được đọc.

### Phân trang và sắp xếp

Nếu thêm `Pageable` hoặc `Sort`, kiểm thử kết quả phải đi qua store hỗ trợ đường truy vấn đó.

Constructor mapping chỉ dựng từng phần tử. Nó không tự bảo đảm thứ tự ổn định, tổng số bản ghi đúng hoặc không có truy vấn bổ sung.

Muốn tối ưu độ trễ của một màn hình danh sách, cần tách rõ:

- Chi phí query và index.
- Chi phí count.
- Lượng dữ liệu trả về.
- Chi phí conversion và khởi tạo object.

Không gán toàn bộ độ trễ cho reflection chỉ vì model có nhiều thuộc tính.

## 9. Không đồng nhất khả năng giữa các store

| Module hoặc đường đọc–ghi | Cách kiểm chứng phù hợp |
| --- | --- |
| MongoDB mapping | Raw document, converter và thao tác MongoDB thực tế |
| JDBC/R2DBC mapping | Giá trị cột, constructor binding, SQL được sinh và vòng đời generated value |
| JPA | Mapping của provider, persistence context, lifecycle và SQL thực thi |
| Custom repository fragment | Cả logic fragment và việc ghép fragment vào proxy repository |
| Custom converter | Chuyển đổi riêng và việc converter được đăng ký trong đường ứng dụng |
| Native client hoặc câu lệnh thủ công | Contract riêng của đường thao tác đó |

Spring Data JPA không thể được đánh giá chỉ bằng một test `MappingMongoConverter`. Entity JPA còn phải tuân theo cơ chế của provider; một mô hình final immutable phù hợp với mapper khác không tự trở thành entity JPA hợp lệ.

Tương tự, test blocking không chứng minh đường R2DBC hoặc repository reactive không chặn luồng.

Giới hạn kết luận theo chính đường đã kiểm tra giúp tránh biến một PASS cục bộ thành một khẳng định cho mọi store.

## 10. Sau khi các hợp đồng PASS, mới đặt giả thuyết tối ưu

Một giả thuyết có thể kiểm tra được:

> Trong workload đọc nhiều object nhỏ, phần khởi tạo và population đang chiếm tỷ lệ đáng kể; thay đổi đường khởi tạo có thể giảm allocation hoặc CPU.

Một giả thuyết chưa đủ rõ:

> Reflection chậm nên cần bỏ setter.

Muốn đánh giá giả thuyết, cần biết:

- Đường nào đang tiêu tốn thời gian.
- Tần suất tạo object.
- Số thuộc tính và kiểu dữ liệu.
- Conversion có phức tạp không.
- Chi phí mạng hoặc database có lấn át mapping không.
- Tối ưu có làm thay đổi model hoặc API không.

### Không đánh đổi contract mà không nhận diện

Một số thay đổi có thể trông giống tối ưu nhưng thực chất đổi hành vi:

| Thay đổi | Rủi ro cần test lại |
| --- | --- |
| Chuyển property access sang field access | Bỏ qua setter normalization hoặc validation |
| Thêm constructor không tham số | Creator được chọn hoặc đường population thay đổi |
| Thay constructor nhận đủ tham số bằng factory thiếu metadata | Mất ID, version hoặc giá trị từ store |
| Chuyển class sang record | Accessor, equality, nullability và cách cập nhật immutable thay đổi |
| Đổi visibility để phù hợp accessor tối ưu | Phạm vi API và khả năng truy cập thay đổi |
| Bỏ custom converter | Kiểu lưu trữ hoặc dữ liệu lịch sử không còn tương thích |
| Chỉ nạp một phần field | Object kết quả không còn an toàn để lưu như entity đầy đủ |

Không đổi tất cả cùng lúc. Chọn một thay đổi, chạy lại các contract liên quan rồi mới so sánh số đo.

## 11. Đo hiệu năng mà không biến unit test thành benchmark

Không dùng một assertion kiểu:

```java
// Không dùng làm tiêu chí unit test ổn định.
// assertTrue(elapsedNanos < 1_000_000);
```

Thời gian có thể dao động vì JIT, class loading, GC, tải máy và môi trường CI.

### 11.1. Tách hai phép đo

| Phép đo | Bao gồm | Câu hỏi trả lời |
| --- | --- | --- |
| Benchmark mapping riêng | Dữ liệu raw có sẵn, conversion, khởi tạo và population | Đường mapping nào tốn CPU hoặc allocation? |
| Đo workload ứng dụng | Query, mạng, mapping, callback và xử lý nghiệp vụ liên quan | Thay đổi có cải thiện trải nghiệm hoặc throughput thực tế không? |

Nếu dùng công cụ microbenchmark như JMH, cần thiết kế warmup, measurement và cách tiêu thụ kết quả phù hợp. Không để JVM loại bỏ toàn bộ công việc vì kết quả không được dùng.

### 11.2. Giữ điều kiện so sánh tương đương

Hai phương án cần dùng:

- Cùng dữ liệu đầu vào và phân bố kích thước.
- Cùng conversion và quy tắc nghiệp vụ.
- Cùng cấu hình JVM, dependency và phần cứng đo.
- Cùng ranh giới đo.
- Đủ lần chạy để quan sát biến động.

Không so sánh `new PurchaseLine(...)` thuần Java với một bên gồm query mạng rồi kết luận sự khác biệt là chi phí mapper.

Nếu benchmark chỉ dùng dữ liệu hợp lệ nhưng production có nhánh xử lý dữ liệu thiếu hoặc converter đặc thù, cần ghi rõ giới hạn kết luận.

### 11.3. Số đo cần quan tâm

Tùy mục tiêu, có thể theo dõi:

- Throughput.
- Thời gian mỗi operation.
- Allocation mỗi operation.
- Áp lực GC.
- Độ trễ của request hoặc batch thực tế.
- Tỷ lệ thời gian mapping trong tổng workload.

Không đưa một tỷ lệ tăng tốc cố định thành lời hứa cho mọi model. Đặc điểm class, classloader, module system, JDK và phiên bản Spring Data có thể ảnh hưởng đường tối ưu được sử dụng.

## 12. Không buộc test nghiệp vụ phụ thuộc implementation nội bộ

Một contract test tốt xác nhận dữ liệu và hành vi.

Không nên làm test nghiệp vụ thất bại chỉ vì tên class accessor nội bộ thay đổi từ một implementation sang implementation khác, nếu dữ liệu và hành vi vẫn đúng.

Cũng không assert “reflection tuyệt đối không được dùng” trong toàn ứng dụng nếu yêu cầu thực tế chỉ là đạt độ trễ hoặc throughput cụ thể.

Khi cần xác định framework có dùng đường sinh mã tối ưu hay fallback:

- Dùng công cụ quan sát, profiling hoặc chẩn đoán phù hợp.
- Kiểm tra điều kiện hỗ trợ của phiên bản.
- Tách quan sát đó khỏi contract nghiệp vụ.
- Đánh giá tác động bằng số đo.

Một fallback đúng có thể đủ nhanh cho workload. Một generated accessor không khắc phục được query thiếu index hoặc payload quá lớn.

## 13. Bộ kiểm tra hồi quy tối thiểu sau một thay đổi mapping

Không cần chạy mọi kiểm thử của mọi module cho một thay đổi cục bộ, nhưng phải giữ những lớp liên quan.

Ví dụ thay `PurchaseLine` bằng một mô hình constructor khác:

1. Chạy test invariant và method tạo bản sao.
2. Chạy fixture raw chiều đọc.
3. Chạy test chiều ghi và thuộc tính transient.
4. Chạy test save–reload với store.
5. Chạy optimistic locking nếu metadata hoặc creator bị ảnh hưởng.
6. Chạy projection nếu tên hoặc kiểu thuộc tính thay đổi.
7. Đo lại cùng benchmark sau khi các contract đã PASS.

Nếu thay đổi chỉ là query projection, test tương ứng phải kiểm tra nội dung query, dữ liệu thiếu và khả năng sử dụng kết quả. Không kéo theo việc sửa creator toàn domain khi chưa có bằng chứng cần thiết.

### Hồ sơ kết quả có thể review

Lưu thông tin đủ để người khác hiểu quyết định:

```text
Thay đổi: mô tả một thay đổi cụ thể về creator/accessor.
Contract: những hành vi được xác nhận và phạm vi store.
Dữ liệu: fixture đại diện và dữ liệu lịch sử liên quan.
Môi trường: JDK, Spring Data, converter và store.
Số đo: workload, ranh giới đo, kết quả và độ dao động.
Quyết định: giữ hoặc bỏ thay đổi cùng lý do.
```

Nếu không có cải thiện đáng kể trong workload mục tiêu, không cần giữ một model khó hiểu hơn chỉ vì benchmark riêng lẻ có chênh lệch nhỏ.

## 14. Lỗi tư duy thường gặp

| Nhận định | Vấn đề | Cách sửa |
| --- | --- | --- |
| Unit test dùng `new` PASS nên mapping chắc chắn đúng | Chưa kiểm tra creator và converter | Thêm fixture raw và test mapping |
| Round-trip PASS nên schema đúng | Hai chiều có thể cùng sai quy ước | Kiểm tra raw fixture độc lập |
| Có field version nên optimistic locking đúng | Chưa có xung đột thực tế | Thử hai instance cùng version |
| `save` đã chạy nên object cũ có metadata mới | Immutable model có thể nhận bản sao | Dùng instance trả về |
| Thêm no-arg constructor luôn giúp persistence | Có thể đổi đường tạo object | Kiểm tra creator và invariant |
| Generated accessor luôn tạo khác biệt lớn | Chi phí mapping có thể nhỏ trong workload | Profile rồi đo đúng ranh giới |
| Bỏ validation sẽ nhanh hơn nên là tối ưu hợp lệ | Đã đổi hợp đồng domain | Tách quyết định nghiệp vụ khỏi tối ưu kỹ thuật |
| Test MongoDB PASS nên JPA cũng đúng | Khác mapping và lifecycle | Kiểm tra module/provider tương ứng |
| Query thiếu field rồi lưu lại vẫn an toàn | Có thể mất dữ liệu | Dùng DTO hoặc thiết kế update có chọn lọc |
| Assert thời gian trong JUnit chứng minh hiệu năng | Dễ nhiễu và thiếu kiểm soát | Dùng phép đo chuyên biệt, giữ unit test xác định |

## 15. Bài thực hành

Dùng một model immutable có ID, version và ít nhất một invariant.

### Phần A: tạo baseline đúng

1. Viết test cho trạng thái hợp lệ và không hợp lệ.
2. Kiểm tra method tạo bản sao giữ nguyên metadata.
3. Chuẩn bị raw fixture đầy đủ và một fixture lịch sử thiếu dữ liệu.
4. Kiểm tra chiều đọc và chiều ghi riêng.
5. Kiểm tra save–reload trên store của ứng dụng.
6. Kiểm tra xung đột version nếu module và model sử dụng optimistic locking.

### Phần B: đề xuất đúng một thay đổi

Chọn một thay đổi về creator hoặc cách truy cập thuộc tính mà phiên bản đang dùng hỗ trợ.

Trước khi sửa, ghi rõ:

- Hành vi nào phải giữ nguyên.
- Chi phí nào dự kiến giảm.
- Test nào có thể phát hiện hồi quy.
- Phép đo nào xác nhận giả thuyết.

Sau khi sửa, chạy lại các contract liên quan rồi mới đo hiệu năng. Nếu hành vi thay đổi, phải xem đó là thay đổi thiết kế cần được đánh giá, không gọi đơn thuần là tối ưu.

### Tiêu chí hoàn thành

- Domain invariant được kiểm tra độc lập với framework.
- Converter đọc được dữ liệu theo schema thực.
- Bản sao immutable không làm mất ID hoặc version.
- Store xử lý vòng đời và xung đột như ứng dụng yêu cầu.
- Kết quả đo có ranh giới và môi trường rõ ràng.
- Quyết định tối ưu dựa trên lợi ích quan sát được và vẫn giữ hợp đồng.

Một mô hình miền phù hợp với Spring Data trước hết phải tái tạo đúng trạng thái và bảo vệ đúng quy tắc. Tối ưu creator hoặc accessor chỉ có ý nghĩa khi những hành vi đó đã được kiểm chứng và chi phí mapping thực sự là vấn đề cần giải quyết.
