# Thiết kế entity bất biến, converter và phát hiện trạng thái mới

## 1. Mục tiêu bài thực hành

Một đối tượng miền bất biến không có setter để framework gán ID, version hoặc metadata sau khi lưu. Nếu ứng dụng đồng thời dùng value object và ID được cấp trước, cần thiết kế rõ ba việc:

1. Framework tạo lại đối tượng bằng constructor hoặc cơ chế nào?
2. Value object được chuyển thành biểu diễn lưu trữ và đọc lại ra sao?
3. Repository nhận diện đối tượng mới hay đã tồn tại từ thông tin nào?

Trong Spring Data Commons, các khái niệm mapping metadata, persistence constructor, converter, `Persistable` và entity information hỗ trợ tổ chức bài toán. Semantics cụ thể của `save`, version và dạng dữ liệu vẫn phụ thuộc Spring Data module.

Bài chọn **Spring Data MongoDB** cho đường triển khai chính. Model dùng Java record, mã khóa học dạng value object, ID chuỗi do ứng dụng cấp và version nullable do framework quản lý. Phần cuối phân tích lựa chọn `Persistable` khi cần chính sách trạng thái mới tường minh.

Các đoạn mã là mẫu thực hành cho bộ phiên bản có hỗ trợ record mapping và API tương ứng. Không dùng model record này như một entity JPA portable chỉ bằng cách thay annotation.

## 2. Chốt hợp đồng dữ liệu trước khi viết model

Hệ thống quản lý thẻ học tập với các yêu cầu:

| Thành phần | Quy tắc |
| --- | --- |
| ID | Ứng dụng cấp một UUID dạng chuỗi khi tạo thẻ |
| Version | Dùng `Long`, để null khi tạo mới và để MongoDB module quản lý khi lưu |
| Mã khóa học | Value object bất biến, chuẩn hóa chữ hoa theo quy tắc nghiệp vụ |
| Tiêu đề | Không rỗng; đổi tiêu đề tạo một đối tượng mới |
| Trạng thái | DRAFT hoặc ARCHIVED |
| Cập nhật cạnh tranh | Phát hiện bằng version trên đường ghi có hỗ trợ |
| Biểu diễn mã trong document | Chuỗi scalar, không phải object lồng chứa field `value` |

Mã khóa học khác ID của thẻ. Hai thẻ có thể tham chiếu cùng mã khóa học trong bài này; không đặt unique index cho field `code` chỉ vì nó có tên là mã. Nếu nghiệp vụ yêu cầu một khóa riêng duy nhất, cần xác định đúng phạm vi và tạo ràng buộc tương ứng tại store.

ID đã có giá trị không có nghĩa dữ liệu đã được lưu. Một đối tượng vừa được factory tạo có ID, nhưng chưa có version và chưa có document trong collection.

## 3. Tạo value object bất biến

```java
import java.util.Locale;
import java.util.regex.Pattern;

public record CourseCode(String value) {

    private static final Pattern FORMAT =
        Pattern.compile("[A-Z0-9][A-Z0-9-]{2,39}");

    public CourseCode {
        if (value == null) {
            throw new IllegalArgumentException("Thiếu mã khóa học");
        }

        value = value.strip().toUpperCase(Locale.ROOT);

        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException("Mã khóa học không hợp lệ");
        }
    }
}
```

Theo quy tắc của bài, đầu vào ` sdc-101 ` trở thành `SDC-101`. Việc dùng `Locale.ROOT` tránh để quy tắc chữ hoa phụ thuộc locale mặc định của máy chạy.

Đây là chính sách của mã khóa học, không phải công thức chuẩn hóa mọi chuỗi. Không áp tương tự cho tên người, nội dung tự do hoặc định danh có quy tắc khác.

Pattern được chuẩn bị một lần; mỗi lần kiểm tra dùng matcher riêng. Value object không giữ request, tenant hoặc trạng thái mutable dùng chung.

### Constructor cũng chạy khi đọc dữ liệu

Khi converter đọc chuỗi cũ để tạo `CourseCode`, validation và chuẩn hóa trên vẫn chạy. Nếu dữ liệu cũ không đáp ứng quy tắc mới, thao tác đọc có thể thất bại.

Vì vậy, thay constructor không chỉ ảnh hưởng API tạo mới. Cần có chính sách cho dữ liệu lịch sử: giữ khả năng đọc, chuyển đổi dữ liệu hoặc báo lỗi có thể chẩn đoán. Không âm thầm biến mọi mã sai thành một mã mặc định.

## 4. Model bất biến có ID và version

```java
public enum CardStatus {
    DRAFT,
    ARCHIVED
}
```

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

import java.util.Objects;
import java.util.UUID;

@Document("learning_cards")
public record LearningCard(
    @Id String id,
    @Version Long version,
    CourseCode code,
    String title,
    CardStatus status
) {

    public LearningCard {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Thiếu ID thẻ");
        }
        Objects.requireNonNull(code, "Thiếu mã khóa học");
        Objects.requireNonNull(status, "Thiếu trạng thái");

        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không được rỗng");
        }
        title = title.strip();
    }

    public static LearningCard draft(CourseCode code, String title) {
        return new LearningCard(
            UUID.randomUUID().toString(),
            null,
            code,
            title,
            CardStatus.DRAFT
        );
    }

    public LearningCard rename(String newTitle) {
        if (status == CardStatus.ARCHIVED) {
            throw new IllegalStateException("Thẻ đã được lưu trữ");
        }
        return new LearningCard(id, version, code, newTitle, status);
    }

    public LearningCard archive() {
        return new LearningCard(
            id, version, code, title, CardStatus.ARCHIVED
        );
    }
}
```

Record có các field final và tạo giá trị mới khi đổi trạng thái. Trong bộ mapping hỗ trợ record, canonical constructor là thông tin quan trọng để khởi tạo hoặc tạo lại đối tượng.

`rename()` và `archive()` giữ nguyên ID cùng version đã đọc. Chúng không tự tăng version; việc đó thuộc đường ghi của module.

Version nullable là có chủ đích. Không đặt `0L` cho mọi đối tượng mới chỉ vì muốn tránh null: trong cơ chế phát hiện dựa trên version không primitive, null và một số cụ thể mang ý nghĩa khác nhau.

Record chỉ bất biến nông. Nếu thêm collection hoặc object mutable, cần bảo vệ các thành phần đó bằng thiết kế phù hợp, chẳng hạn sao chép phòng vệ. Field final không làm mọi đối tượng được tham chiếu bên trong tự bất biến.

## 5. Converter hai chiều cho biểu diễn scalar

### 5.1. Đọc chuỗi thành value object

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class CourseCodeReadConverter
        implements Converter<String, CourseCode> {

    @Override
    public CourseCode convert(String source) {
        return new CourseCode(source);
    }
}
```

### 5.2. Ghi value object thành chuỗi

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class CourseCodeWriteConverter
        implements Converter<CourseCode, String> {

    @Override
    public String convert(CourseCode source) {
        return source.value();
    }
}
```

Đầu vào và đầu ra được xác định hẹp. Converter không gọi repository để tìm khóa học và không thay đổi ID/version của thẻ.

Nếu cần kiểm tra mã có tồn tại trong danh mục, nên điều phối truy vấn đó tại service hoặc một quy trình có ranh giới rõ. Đưa lookup vào converter có thể tạo truy vấn phụ cho từng field hoặc từng phần tử được mapping.

### 5.3. Đăng ký vào mapping của MongoDB

Một cấu hình minh họa dùng API `MongoCustomConversions.create`:

```java
@Configuration(proxyBeanMethods = false)
class CardConversionsConfiguration {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new CourseCodeReadConverter());
            adapter.registerConverter(new CourseCodeWriteConverter());
        });
    }
}
```

Ví dụ lược bỏ import cấu hình và dùng `MongoCustomConversions` của Spring Data MongoDB. Class cấu hình phải được nạp; mapping converter thực tế phải sử dụng bộ custom conversions này.

Nếu ứng dụng đã có cấu hình conversions hoặc tự tạo mapping converter, cần hợp nhất theo cơ chế đang dùng. Không thay toàn bộ cấu hình cũ bằng chỉ hai converter rồi bỏ mất các converter nghiệp vụ khác.

`@ReadingConverter` và `@WritingConverter` thể hiện chiều chuyển đổi. Chúng không tự đăng ký hai class vào mọi module Spring Data, cũng không áp dụng thay cho `AttributeConverter` của JPA.

## 6. Repository và vòng đời lưu đối tượng bất biến

```java
public interface LearningCardRepository
        extends MongoRepository<LearningCard, String> {

    List<LearningCard> findByCode(CourseCode code);

    Slice<LearningCard> findByStatus(
        CardStatus status,
        Pageable pageable
    );
}
```

Các import thông dụng được lược bỏ. Query theo `CourseCode` cần được kiểm chứng với mapping/conversions đang đăng ký; không chỉ kiểm tra converter bằng cách gọi trực tiếp.

Luồng sử dụng đúng luôn giữ kết quả trả về:

```java
LearningCard fresh = LearningCard.draft(
    new CourseCode(" sdc-101 "),
    "Abstraction repository"
);

LearningCard stored = repository.save(fresh);
LearningCard renamed = stored.rename("Repository và CRUD chọn lọc");
LearningCard updated = repository.save(renamed);
```

`fresh` là snapshot trước lưu. `stored` mang trạng thái framework trả sau lưu, gồm version được gán theo cơ chế của module. `updated` là snapshot cần dùng cho bước tiếp theo.

Không nên giả định framework có thể sửa metadata ngay trên record ban đầu. Hợp đồng `save` trả đối tượng cần được sử dụng, đặc biệt với model bất biến hoặc đường mapping trả một instance thay thế.

### Mẫu dễ gây lỗi

```java
LearningCard fresh = LearningCard.draft(code, title);
repository.save(fresh);
repository.save(fresh.rename("Tiêu đề khác"));
```

Lần gọi thứ hai vẫn dựa trên version null của snapshot mới ban đầu. Với đường repository MongoDB nhận diện nó là entity mới, thao tác có thể lại đi theo nhánh insert và gặp trùng ID đã tồn tại.

Đây không phải lý do để xóa version hoặc sinh ID khác mỗi lần cập nhật. Cách sửa là dùng snapshot trả về sau lưu, hoặc đọc bản hiện tại rồi thực hiện lệnh nghiệp vụ trên bản đó.

## 7. Phát hiện trạng thái mới không phải truy vấn tồn tại

### 7.1. Metadata là tín hiệu lựa chọn đường ghi

Với cơ chế mặc định dùng metadata của entity, Spring Data có thể xem xét version phù hợp trước ID. Chi tiết phải được xác nhận cho module và kiểu property.

Trong model MongoDB của bài, `Long version` cho phép biểu diễn trạng thái mới bằng null:

| Snapshot | ID | Version | Ý nghĩa theo thiết kế |
| --- | --- | --- | --- |
| Vừa gọi `draft()` | Đã có UUID | null | Được nhận diện là mới |
| Kết quả sau insert thành công | Giữ ID | Không null | Không còn là snapshot mới |
| Kết quả `stored.rename()` | Giữ ID | Giữ version đã đọc | Cập nhật có điều kiện theo version |
| Tự dựng lại với ID cũ nhưng version null | ID đã dùng | null | Bị mô tả như entity mới, dù document có thể đã tồn tại |

Giá trị version đầu tiên và cách tăng phụ thuộc module/kiểu property. Test nên kiểm tra những điều cần thiết như version được điền và tiến triển sau cập nhật, thay vì dùng một con số làm quy ước chung cho mọi store.

### 7.2. Có ID không chứng minh đã lưu

UUID được cấp trước giúp định danh ổn định cho một đối tượng chưa được ghi. Nó không thể tự trả lời document có tồn tại hay không.

Ngược lại, một version không null cũng chỉ là metadata mà snapshot đang mang, không phải một phép kiểm tra tồn tại tức thời. Document có thể đã bị xóa hoặc thay đổi bởi tiến trình khác.

Newness detection giúp chọn đường thao tác. Ràng buộc ID, điều kiện version và phản hồi từ store mới là những phần kiểm chứng tác dụng ghi thực tế.

### 7.3. `save` không có semantics đồng nhất cho mọi store

Không suy ra mọi module dùng ID có sẵn đều thực hiện cùng một loại upsert. Trong JPA có khái niệm persist/merge; trong JDBC và MongoDB có các đường ghi khác theo trạng thái cùng implementation tương ứng.

Cần tách quyết định “được coi là mới” khỏi kết luận “chắc chắn đã tạo mới thành công”. Lỗi trùng khóa, xung đột version hoặc lỗi transaction vẫn có thể xảy ra.

## 8. Bất biến và optimistic locking cần phối hợp

Bất biến bảo vệ snapshot Java khỏi việc bị sửa trực tiếp. Nó không ngăn hai tiến trình đọc cùng version rồi tạo hai bản cập nhật khác nhau.

```text
A đọc thẻ version V
B đọc thẻ version V
A tạo snapshot đổi tiêu đề và lưu -> version mới
B tạo snapshot từ V rồi lưu -> cần phát hiện xung đột
```

Trong MongoDB, phải dùng đường thao tác hỗ trợ version và mức write concern có xác nhận phù hợp để quan sát lỗi đáng tin cậy. Không mặc định bulk hoặc driver operation trực tiếp tự áp dụng cùng lifecycle/version như repository.

Sau xung đột, không tự tăng version trên snapshot B để ép ghi. Nếu nghiệp vụ cho phép retry, đọc lại trạng thái hiện tại và kiểm tra lại lệnh. Với chỉnh sửa từ biểu mẫu cũ, có thể cần thông báo xung đột cho người dùng thay vì âm thầm ghi đè.

Một snapshot có field audit hoặc version đã được tạo không tự chứng minh giao dịch ngoài đã commit. Với transaction, sử dụng kết quả theo ranh giới hoàn tất thích hợp và xử lý trường hợp rollback.

## 9. Khi nào cần `Persistable`?

Nếu cơ chế mặc định không biểu đạt được trạng thái mới, ứng dụng có thể triển khai `Persistable<ID>`. Khi module sử dụng cơ chế này, `isNew()` do đối tượng cung cấp có thể thay thế quyết định mặc định dựa trên ID/version.

Đây là một trách nhiệm bổ sung: ứng dụng phải quản lý trạng thái cho đối tượng vừa tạo, đối tượng đọc từ store và đối tượng trả về sau lưu.

Không nên thêm `Persistable` chỉ để bỏ qua một lỗi trùng khóa đang do tái dùng snapshot cũ. Với model chính của bài, version nullable đã cung cấp tín hiệu cần thiết.

### Minh họa riêng: cờ mới không được lưu

Ví dụ sau dùng collection riêng và chỉ minh họa quản lý newness tường minh; nó chưa có cơ chế version để bảo vệ cập nhật cạnh tranh:

```java
@Document("manual_state_cards")
public final class ManualStateCard implements Persistable<String> {

    @Id
    private final String id;

    private final String title;

    @Transient
    private final boolean newEntity;

    @PersistenceCreator
    public ManualStateCard(String id, String title) {
        this(id, title, false);
    }

    private ManualStateCard(String id, String title, boolean newEntity) {
        if (id == null || id.isBlank()
                || title == null || title.isBlank()) {
            throw new IllegalArgumentException("ID hoặc tiêu đề sai");
        }
        this.id = id;
        this.title = title;
        this.newEntity = newEntity;
    }

    public static ManualStateCard fresh(String id, String title) {
        return new ManualStateCard(id, title, true);
    }

    public ManualStateCard asExisting() {
        return new ManualStateCard(id, title, false);
    }

    @Override
    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    @Override
    @Transient
    public boolean isNew() {
        return newEntity;
    }
}
```

Ví dụ dùng `Persistable` từ `org.springframework.data.domain` cùng `Id`, `Transient`, `PersistenceCreator` từ `org.springframework.data.annotation`. Cần giữ thông tin tên tham số constructor theo yêu cầu mapping của bộ công cụ đang dùng.

Constructor được chọn để đọc chỉ nhận dữ liệu đã lưu và đặt cờ mới bằng false. Factory `fresh()` tạo trạng thái mới bằng true. Cờ nội bộ không trở thành dữ liệu nghiệp vụ trong document.

Không đưa một cờ transient bắt buộc vào persistence constructor rồi giả định store sẽ cấp giá trị cho nó. Đặc biệt với record, mọi component thuộc canonical constructor; thêm một component transient có thể đòi hỏi thiết kế lại đường khởi tạo, không chỉ thêm annotation.

### Trạng thái sau lưu phải có chính sách rõ

Với đối tượng bất biến dùng cờ tường minh, lưu xong không mặc nhiên làm cờ trên instance ban đầu đổi thành false. Nếu đường lưu không trả một snapshot đã chuyển trạng thái, ứng dụng cần một bước như `asExisting()` sau khi thành công theo ranh giới được chọn, hoặc cơ chế lifecycle phù hợp được kiểm chứng.

Không đánh dấu “đã tồn tại” trước thao tác ghi rồi dùng nó tiếp nếu ghi thất bại. Cũng không coi `isNew() == false` là kiểm tra tồn tại hoặc là cơ chế optimistic locking.

Nếu nhận DTO từ client, không tin một cờ `newEntity` do client gửi để chọn tùy ý đường insert/update. Quyết định đó phải thuộc quy trình nghiệp vụ và trạng thái mà ứng dụng quản lý.

## 10. Constructor, callback và auditing trên đối tượng bất biến

### 10.1. Constructor phải phục vụ cả dữ liệu mới và dữ liệu đọc lại

Canonical/persistence constructor cần nhận đủ thông tin để khôi phục snapshot hợp lệ. Một factory chỉ dành cho tạo mới có thể sinh ID/version mặc định khác với dữ liệu lưu, nên không nên bị chọn nhầm làm đường đọc.

Nếu class có nhiều constructor hoặc factory phù hợp, cần dùng cơ chế chỉ định persistence creator mà module hỗ trợ. Không thêm nhiều annotation chọn constructor rồi dựa vào thứ tự framework thử.

### 10.2. Callback trả instance mới phải được sử dụng

Trong module hỗ trợ entity callback, một callback có thể trả đối tượng đã biến đổi. Với model bất biến, trả một bản sao có ý nghĩa hơn việc tìm setter không tồn tại.

Cần kiểm tra rằng đường ghi sử dụng đúng instance mới và vẫn giữ ID/version cùng các field không được thay đổi. Một callback chuẩn hóa tiêu đề nhưng vô tình gọi lại factory `draft()` sẽ tạo ID mới và version null, làm biến đổi ý nghĩa thao tác.

### 10.3. Auditing cũng tạo yêu cầu mapping metadata

Nếu thêm field tạo/sửa hoặc actor vào model bất biến, framework cần có đường gán metadata được module hỗ trợ, chẳng hạn khởi tạo lại qua constructor/property accessor tương ứng.

Ứng dụng vẫn phải dùng đối tượng trả về sau lưu. Không kiểm tra metadata trên snapshot cũ rồi kết luận auditing không chạy. Đồng thời, auditing phải được bật và có nguồn actor/time phù hợp; bất biến không tự cấu hình những phần đó.

## 11. Kiểm thử theo từng lớp

### 11.1. Unit test value object và hành vi bất biến

```java
@Test
void normalizesCourseCode() {
    assertThat(new CourseCode(" sdc-101 ").value())
        .isEqualTo("SDC-101");
}
```

```java
@Test
void renameCreatesSnapshotAndPreservesIdentityMetadata() {
    LearningCard original = new LearningCard(
        "card-a", 5L, new CourseCode("SDC-101"),
        "Tiêu đề cũ", CardStatus.DRAFT
    );

    LearningCard renamed = original.rename("Tiêu đề mới");

    assertThat(original.title()).isEqualTo("Tiêu đề cũ");
    assertThat(renamed.title()).isEqualTo("Tiêu đề mới");
    assertThat(renamed.id()).isEqualTo(original.id());
    assertThat(renamed.version()).isEqualTo(original.version());
}
```

Ví dụ dùng JUnit Jupiter và AssertJ, lược bỏ import. Giá trị 5L chỉ là fixture cho snapshot đã có version, không phải quy định version khởi đầu.

Thêm trường hợp mã không hợp lệ, tiêu đề rỗng và đổi tên thẻ ARCHIVED. Test cần chứng minh quy tắc nghiệp vụ cùng việc giữ snapshot cũ, không chỉ chứng minh record có accessor.

### 11.2. Unit test converter hai chiều

```java
@Test
void convertsCodeToAndFromScalarValue() {
    var writer = new CourseCodeWriteConverter();
    var reader = new CourseCodeReadConverter();
    CourseCode code = new CourseCode("SDC-101");

    String storedValue = writer.convert(code);
    CourseCode restored = reader.convert(storedValue);

    assertThat(storedValue).isEqualTo("SDC-101");
    assertThat(restored).isEqualTo(code);
}
```

Test này chưa chứng minh mapping converter đã đăng ký hai converter. Nó chỉ kiểm tra logic chuyển đổi trực tiếp.

Nếu biểu diễn cũ khác với chuỗi scalar, cần test migration/đọc tương thích riêng. Không kỳ vọng converter `String -> CourseCode` tự hiểu một document lồng có cấu trúc khác.

## 12. Integration test mapping và newness trên MongoDB

Test cần repository thật, cấu hình conversions đã nạp và MongoDB test phù hợp. Khi dùng test slice như `@DataMongoTest`, cần import cấu hình converter nếu nó chưa nằm trong phạm vi test.

### 12.1. Lưu mới rồi cập nhật bằng snapshot trả về

```java
@Test
void savesImmutableCardAndUsesReturnedVersion() {
    LearningCard fresh = LearningCard.draft(
        new CourseCode("sdc-101"), "Bản nháp"
    );

    LearningCard stored = cards.save(fresh);

    assertThat(fresh.version()).isNull();
    assertThat(stored.id()).isEqualTo(fresh.id());
    assertThat(stored.version()).isNotNull();

    LearningCard updated = cards.save(stored.rename("Đã đổi tên"));

    assertThat(updated.id()).isEqualTo(stored.id());
    assertThat(updated.version()).isGreaterThan(stored.version());
    assertThat(cards.findById(updated.id()))
        .contains(updated);
}
```

Test thể hiện kỳ vọng của model bất biến và đường repository được chọn. Không hard-code giá trị version đầu tiên.

### 12.2. Quan sát biểu diễn được ghi thật

Có thể đọc document bằng driver để xác nhận field `code` là chuỗi:

```java
Document raw = mongoTemplate.getCollection("learning_cards")
    .find(Filters.eq("_id", stored.id()))
    .first();

assertThat(raw).isNotNull();
assertThat(raw.get("code")).isEqualTo("SDC-101");
```

Ví dụ dùng `org.bson.Document` và `com.mongodb.client.model.Filters`, giả định `stored` là kết quả lưu từ fixture tương ứng. Đồng thời, đọc lại bằng repository phải khôi phục đúng `CourseCode`.

Test query `findByCode(new CourseCode("sdc-101"))` giúp xác nhận giá trị tham số cũng được ánh xạ phù hợp, thay vì chỉ kiểm tra chiều ghi document.

### 12.3. Xung đột giữa hai snapshot cũ

```java
LearningCard left = cards.findById(id).orElseThrow();
LearningCard right = cards.findById(id).orElseThrow();

cards.save(left.rename("Tên từ A"));

assertThrows(
    OptimisticLockingFailureException.class,
    () -> cards.save(right.rename("Tên từ B"))
);
```

Ví dụ giả định `id` đã được seed, đường ghi có hỗ trợ version và write concern có xác nhận phù hợp. Đây là kiểm tra stale snapshot; không cần thêm thread ngẫu nhiên chỉ để chứng minh điều kiện version.

Đối với cờ `Persistable`, bổ sung test đối tượng mới, đối tượng đọc lại, sau lưu và khi lưu thất bại. Kiểm tra raw document không có cờ nội bộ. Những trạng thái đó không được suy ra chỉ từ test của model versioned chính.

Test MongoDB không tự có rollback giống mọi test JPA. Cần cách ly database/collection hoặc dọn đúng dữ liệu thuộc test theo cấu hình thực tế.

## 13. Các lỗi thiết kế dễ gặp

| Lỗi | Hệ quả hoặc cách nhận biết |
| --- | --- |
| Bỏ kết quả `save()` | Tiếp tục dùng ID/version/audit metadata cũ |
| Tạo bản cập nhật bằng factory tạo mới | ID hoặc trạng thái new bị đặt lại |
| Gán `0L` cho version của mọi bản mới | Có thể làm entity không còn được nhận diện là mới theo chiến lược nullable version |
| Converter ghi cả root document và bỏ version | Làm sai mapping hoặc cơ chế cạnh tranh mà thiết kế dựa vào |
| Thêm cờ `Persistable` nhưng không đổi trạng thái sau lưu | Những lần lưu tiếp theo có thể vẫn bị coi là tạo mới |
| Dùng constructor đọc tự sinh ID mới | Snapshot khôi phục không còn giữ định danh lưu trữ |
| Record chứa collection mutable chưa được bảo vệ | Bất biến chỉ còn ở tham chiếu ngoài |
| Đọc lỗi dữ liệu cũ rồi trả object mặc định | Che dữ liệu không tương thích và có thể gây ghi sai về store |
| Chỉ test converter trực tiếp | Bỏ sót đăng ký custom conversions và mapping/query thật |

Không dùng một boolean “đã lưu” làm bằng chứng commit hay khả năng tồn tại hiện tại. Nó là thông tin mô hình ứng dụng phải quản lý cùng kết quả của store.

## 14. Service điều phối nên giữ hợp đồng snapshot rõ ràng

Một lệnh đổi tiêu đề có thể đi theo các bước:

```text
Nhận ID và nội dung đã được kiểm tra quyền
    -> đọc snapshot hiện tại
    -> kiểm tra trạng thái nghiệp vụ
    -> tạo snapshot đổi tiêu đề, giữ ID/version
    -> lưu bằng repository
    -> dùng snapshot trả về để tạo response
```

Không cần đọc rồi ghi qua nhiều converter thủ công nếu mapping đã đăng ký đúng. Cũng không nhận một entity đầy đủ từ client rồi tin rằng version/newness do client gửi đã phản ánh trạng thái store.

Nếu API cho phép client cung cấp version để phát hiện chỉnh sửa từ màn hình cũ, phải có hợp đồng đối chiếu rõ. Việc service đọc bản mới rồi bỏ qua version mà client nhìn thấy có thể làm mất ý nghĩa kiểm tra xung đột ở biên API.

Với nhiều thao tác cần transaction, phải dùng manager và deployment MongoDB có khả năng đáp ứng phạm vi đó. Model bất biến và một lời gọi `save()` không tự tạo transaction xuyên nhiều document hay nhiều datastore.

## 15. Điều kiện hoàn thành bài thực hành

Bài thực hành đạt mục tiêu khi có thể chứng minh:

1. Model chính bất biến và các lệnh thay đổi tạo snapshot mới.
2. ID ổn định qua đổi tiêu đề/lưu trữ; version do module quản lý.
3. Converter ghi `CourseCode` thành chuỗi và đọc lại đúng quy tắc.
4. Mapping thực sự dùng converter, gồm cả query parameter cần thiết.
5. Đối tượng có ID cấp trước vẫn được nhận diện mới nhờ chính sách đã chọn.
6. Consumer dùng kết quả trả về sau lưu, không tái dùng snapshot mới ban đầu để cập nhật.
7. Xung đột version được phát hiện trên store với mức xác nhận phù hợp.
8. Nếu chọn `Persistable`, cờ nội bộ không được lưu và trạng thái sau đọc/lưu/lỗi có quy tắc rõ.
9. Constructor và converter có chính sách cho dữ liệu cũ hoặc không hợp lệ.

Các điều kiện là tiêu chí triển khai cho người thực hành. Chúng không thể được thay bằng việc chỉ thấy code compile hoặc chỉ kiểm tra record không có setter.

## 16. Bài tập mở rộng

Hãy thêm auditing và một phần mô tả đa ngôn ngữ vào thẻ học tập, vẫn giữ model bất biến.

Cần làm rõ:

- Collection mô tả được bảo vệ khỏi sửa ngoài ý muốn ra sao.
- Metadata audit được tạo lại trong snapshot bằng đường mapping/callback nào.
- Có cần converter cho từng giá trị hay cho cả cấu trúc không.
- Dữ liệu đã lưu trước khi có field mới sẽ được đọc như thế nào.
- Version và trạng thái mới có bị đặt lại khi tạo bản sao không.

Sau đó so sánh nếu chuyển aggregate sang Spring Data JDBC hoặc một model JPA phù hợp. Giữ lại các yêu cầu nghiệp vụ, nhưng đánh giá lại constructor, annotation, chuyển đổi và semantics lưu theo module. Không coi bộ annotation của ví dụ MongoDB là hợp đồng portable cho mọi kho.

## 17. Điểm cần nhớ

Thiết kế bất biến cần nối constructor, converter và metadata trạng thái thành một hợp đồng thống nhất. ID có sẵn chưa chứng minh đã lưu; version nullable hoặc `Persistable` phải được chọn có chủ đích và kiểm chứng theo store.

Luôn giữ snapshot trả về sau ghi, bảo toàn ID/version khi thực hiện lệnh nghiệp vụ và kiểm tra biểu diễn lưu trữ thật. Các abstraction Commons giúp tổ chức thiết kế, còn tính đúng của mapping, newness, optimistic locking và auditing phải được xác nhận trên đường truy cập của module cụ thể.
