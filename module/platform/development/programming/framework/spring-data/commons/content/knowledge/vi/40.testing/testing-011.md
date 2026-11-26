# Kiểm thử converter, callback, auditing và sự kiện

## 1. Xác định hành vi cần chứng minh

Trong chương **Kiểm thử** của **SPRING_DATA_COMMONS**, converter, callback, auditing và sự kiện đều có thể tham gia đường đi của dữ liệu qua repository. Tuy nhiên, chúng không phải một cơ chế duy nhất và không có cùng thời điểm thực thi.

Một test chỉ gọi repository mock không chứng minh những cơ chế này đã được kích hoạt. Cần xác định từng hợp đồng rồi kiểm tra ở đúng tầng:

| Cơ chế | Câu hỏi kiểm thử chính |
| --- | --- |
| Converter | Giá trị domain được đổi sang biểu diễn lưu trữ và đọc ngược đúng không? |
| Entity callback | Callback có được đăng ký, được gọi ở thao tác phù hợp và tạo ra kết quả mong muốn không? |
| Auditing | Người thao tác và thời điểm có được điền đúng trong lần tạo và cập nhật không? |
| Domain event | Sự kiện có được đăng ký và phát qua đường gọi repository được hỗ trợ không? |
| Transactional event listener | Listener có chạy ở đúng giai đoạn transaction và đúng điều kiện không? |

Abstraction chung của Commons giúp biểu đạt nhiều hợp đồng này, nhưng khả năng hỗ trợ và tích hợp cụ thể thuộc từng module. Không mang callback MongoDB áp dụng trực tiếp cho JPA, hoặc mặc định mọi store có transaction giống nhau.

## 2. Dùng cả kiểm thử đơn vị và kiểm thử tích hợp

Hai tầng test trả lời các câu hỏi khác nhau:

~~~text
Unit test:
Đầu vào → Hàm converter hoặc logic callback → Kết quả

Integration test:
Repository thật → Hạ tầng module → Callback/auditing/conversion
                → Store thật → Đọc lại dữ liệu và quan sát sự kiện
~~~

Unit test giúp kiểm tra thuật toán chuyển đổi và các nhánh đầu vào nhanh, rõ ràng. Integration test xác minh wiring, metadata, thứ tự có ý nghĩa và biểu diễn lưu trữ thực tế.

Ví dụ, converter chuyển CustomerCode thành String có thể vượt qua mọi unit test nhưng chưa được đăng ký vào mapping của store. Ngược lại, converter được đăng ký nhưng logic chuẩn hóa sai thì integration test cũng chưa chắc phát hiện nếu fixture chỉ có giá trị đã chuẩn.

Bộ test cần có cả dữ liệu phân biệt lỗi và đường thực thi thật.

## 3. Mô hình xuyên suốt

Giả sử ứng dụng quản lý hồ sơ khách hàng với các yêu cầu:

- CustomerCode được chuẩn hóa theo quy tắc nghiệp vụ.
- Biểu diễn lưu trữ của code là một chuỗi.
- searchName được tính từ displayName trước khi chuyển thành dữ liệu lưu.
- Thông tin tạo/cập nhật được điền bởi auditing.
- Khi đổi tên, aggregate đăng ký ProfileRenamed.

Các đoạn minh họa dùng Java 17. Phần tích hợp chọn **Spring Data MongoDB** để có một ngữ cảnh cụ thể cho conversion và entity callback. Đây là ví dụ của module store, không phải API lưu trữ phổ quát của Spring Data Commons.

Phần sự kiện dùng abstraction aggregate của Commons; phần transaction phải được cấu hình theo store riêng.

### Value object và sự kiện

~~~java
import java.util.Locale;
import java.util.Objects;

public record CustomerCode(String value) {

    public CustomerCode {
        Objects.requireNonNull(value, "value");
        value = value.strip().toUpperCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("CustomerCode không được rỗng");
        }
    }
}
~~~

Quy tắc viết hoa là quy tắc của mã khách hàng trong ví dụ. Không tự áp dụng nó cho mọi loại định danh hoặc dữ liệu chuỗi.

~~~java
public record ProfileRenamed(String profileId, String displayName) {
}
~~~

Sự kiện nên chứa dữ liệu cần thiết theo hợp đồng. Tránh để consumer buộc phải đọc một đối tượng mutable có thể tiếp tục thay đổi sau khi sự kiện được đăng ký.

## 4. Kiểm thử converter theo hai chiều

Converter ghi và đọc có vai trò khác nhau. Trong Spring Data, annotation về chiều conversion có thể giúp module phân biệt ý định khi đăng ký converter.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class CustomerCodeWriteConverter
        implements Converter<CustomerCode, String> {

    @Override
    public String convert(CustomerCode source) {
        return source.value();
    }
}
~~~

~~~java
@ReadingConverter
public class CustomerCodeReadConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        return new CustomerCode(source);
    }
}
~~~

Hai converter phải được đăng ký qua cơ chế custom conversions của module. Việc class có annotation không tự chứng minh mọi cấu hình ứng dụng đã thu thập và đăng ký nó.

### Unit test cho hợp đồng chuyển đổi

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class CustomerCodeConverterTest {

    private final CustomerCodeWriteConverter writer =
            new CustomerCodeWriteConverter();

    private final CustomerCodeReadConverter reader =
            new CustomerCodeReadConverter();

    @Test
    void writesCanonicalCode() {
        String stored = writer.convert(new CustomerCode("  c-001  "));

        assertThat(stored).isEqualTo("C-001");
    }

    @Test
    void readsAndNormalizesStoredCode() {
        CustomerCode code = reader.convert(" c-001 ");

        assertThat(code).isEqualTo(new CustomerCode("C-001"));
    }

    @Test
    void roundTripPreservesTheCanonicalValue() {
        CustomerCode original = new CustomerCode("c-001");

        CustomerCode restored =
                reader.convert(writer.convert(original));

        assertThat(restored).isEqualTo(original);
    }

    @Test
    void rejectsBlankCode() {
        assertThatThrownBy(() -> reader.convert("   "))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Round trip ở đây bảo toàn giá trị chuẩn hóa, không bảo toàn khoảng trắng hoặc chữ thường của đầu vào ban đầu.

Đối với null, cần kiểm tra hợp đồng của conversion service và mapping đang dùng. Unit test gọi trực tiếp convert(null) không nhất thiết mô phỏng đúng việc framework có gọi converter với null hay bỏ qua nó.

### Round trip chưa đủ để chứng minh định dạng lưu trữ

Nếu cả hai converter cùng dùng sai một định dạng nhưng vẫn đối xứng, test đọc-ghi có thể xanh. Vì vậy, ngoài round trip, cần có assertion độc lập về biểu diễn mong muốn, chẳng hạn chuỗi C-001.

Với thời gian, số thập phân hoặc dữ liệu nhị phân, hãy kiểm tra độ chính xác và các giá trị biên có ý nghĩa. Không chọn fixture vô tình tránh mọi trường hợp mất thông tin.

## 5. Chuẩn bị aggregate và callback của module

Một phần domain dùng cho ví dụ MongoDB:

~~~java
import java.time.Instant;
import java.util.Locale;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.domain.AbstractAggregateRoot;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customer_profile")
public class CustomerProfile
        extends AbstractAggregateRoot<CustomerProfile> {

    @Id
    private String id;

    @Field("customer_code")
    private CustomerCode code;

    private String displayName;

    @Field("search_name")
    private String searchName;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Version
    private Long version;

    public CustomerProfile() {
    }

    public CustomerProfile(
            String id,
            CustomerCode code,
            String displayName) {
        this.id = id;
        this.code = code;
        this.displayName = displayName.strip();
    }

    public void rename(String newName) {
        this.displayName = newName.strip();
        registerEvent(new ProfileRenamed(id, displayName));
    }

    public void refreshSearchName() {
        this.searchName = displayName.toLowerCase(Locale.ROOT);
    }

    public String getId() { return id; }
    public CustomerCode getCode() { return code; }
    public String getDisplayName() { return displayName; }
    public String getSearchName() { return searchName; }
    public String getCreatedBy() { return createdBy; }
    public Instant getCreatedAt() { return createdAt; }
    public String getLastModifiedBy() { return lastModifiedBy; }
    public Instant getLastModifiedAt() { return lastModifiedAt; }
}
~~~

Getter được dùng để viết assertion; entity cần đáp ứng quy tắc mapping của cấu hình thật. Version dạng Long còn tham gia cơ chế nhận diện đối tượng mới và optimistic locking của module.

Với ID được cấp trước, cần hiểu cách isNew được xác định. Không suy ra “ID khác null thì luôn là cập nhật” hoặc “save đầu tiên chắc chắn được coi là tạo mới” cho mọi mô hình.

Callback MongoDB:

~~~java
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;

public class SearchNameCallback
        implements BeforeConvertCallback<CustomerProfile> {

    @Override
    public CustomerProfile onBeforeConvert(
            CustomerProfile profile,
            String collection) {
        profile.refreshSearchName();
        return profile;
    }
}
~~~

Callback cần được đăng ký theo cơ chế của module, chẳng hạn là bean được cấu hình phù hợp. Việc new callback và gọi trực tiếp chỉ kiểm tra logic bên trong, không kiểm tra việc repository thực sự sử dụng callback.

Ví dụ chọn callback trả lại cùng đối tượng. Nếu callback tạo đối tượng mới, caller và test phải dùng kết quả lưu mà repository trả về, thay vì chỉ kiểm tra tham chiếu đầu vào.

## 6. Kiểm thử callback: logic, kích hoạt và dữ liệu được ghi

Nên phân biệt ba câu hỏi:

1. refreshSearchName có tính đúng không?
2. SearchNameCallback có được gọi trên đường lưu đang kiểm tra không?
3. Giá trị tính được có thực sự đi vào biểu diễn lưu trữ không?

Unit test có thể trả lời câu đầu và một phần câu thứ hai khi gọi callback trực tiếp. Câu hỏi về wiring và persistence cần integration test.

Giả sử repository thật là:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, String> {
}
~~~

Một phương thức test tích hợp có thể quan sát cả domain sau khi đọc lại và BSON:

~~~java
@Test
void savesConvertedCodeAndComputedSearchName() {
    CustomerProfile saved = repository.save(
            new CustomerProfile(
                    "profile-001",
                    new CustomerCode(" c-001 "),
                    "Nguyen An"));

    CustomerProfile reloaded = repository
            .findById(saved.getId())
            .orElseThrow();

    assertThat(reloaded.getCode())
            .isEqualTo(new CustomerCode("C-001"));
    assertThat(reloaded.getSearchName()).isEqualTo("nguyen an");

    org.bson.Document raw = mongoTemplate
            .getCollection("customer_profile")
            .find(com.mongodb.client.model.Filters.eq(
                    "_id", saved.getId()))
            .first();

    assertThat(raw).isNotNull();
    assertThat(raw.get("customer_code"))
            .isInstanceOf(String.class);
    assertThat(raw.getString("customer_code")).isEqualTo("C-001");
    assertThat(raw.getString("search_name")).isEqualTo("nguyen an");
}
~~~

Đoạn test giả định fixture được cô lập, custom conversions cùng callback đã được đăng ký, và repository/MongoTemplate cùng trỏ đến database thử nghiệm.

Đọc BSON trực tiếp giúp phát hiện tình huống mapping mặc định lưu CustomerCode thành document lồng thay vì chuỗi, dù đối tượng đọc lại có vẻ vẫn đúng.

Cần chọn ID và cách mapping phù hợp. ID profile-001 trong ví dụ không được dùng để suy ra quy tắc chuyển đổi mọi String ID sang kiểu lưu trữ của MongoDB.

### Thứ tự callback

Nếu hai callback phụ thuộc nhau, hãy xác định thứ tự bằng cơ chế ordering được module hỗ trợ rồi kiểm tra kết quả có thể quan sát.

Không dựa vào thứ tự khai báo bean hoặc tên class. Cũng không tự dựng một thứ tự chung như “mọi callback luôn chạy trước mọi event” cho tất cả store.

Có thể dùng một trace trong test để ghi lại các checkpoint cần kiểm tra. Chỉ assertion những quan hệ thứ tự thuộc hợp đồng, tránh khóa test vào toàn bộ chi tiết nội bộ không cần thiết.

Trong ví dụ, searchName không phụ thuộc thời điểm auditing chạy, nên không cần ép thứ tự giữa callback đó và auditing.

## 7. Auditing cần nguồn thời gian và người thao tác có thể điều khiển

Auditing thường điền các thuộc tính như CreatedBy, CreatedDate, LastModifiedBy và LastModifiedDate. Để test ổn định, không nên phụ thuộc trực tiếp vào thời gian thực hoặc danh tính ngẫu nhiên của môi trường chạy.

Dùng hai mốc cố định:

~~~text
T0 = 2030-01-01T08:00:00Z, actor = alice
T1 = 2030-01-01T09:00:00Z, actor = bob
~~~

Fixture hỗ trợ cấu hình nguồn thời gian và auditor:

~~~java
import java.time.Instant;

public class AuditScenario {

    private String actor = "alice";
    private Instant now = Instant.parse("2030-01-01T08:00:00Z");

    public String actor() {
        return actor;
    }

    public Instant now() {
        return now;
    }

    public void changeTo(String actor, Instant now) {
        this.actor = actor;
        this.now = now;
    }
}
~~~

Cấu hình minh họa dành cho test MongoDB imperative:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(
        auditorAwareRef = "testAuditor",
        dateTimeProviderRef = "testTime",
        modifyOnCreate = true)
public class AuditingTestConfiguration {

    @Bean
    AuditScenario auditScenario() {
        return new AuditScenario();
    }

    @Bean
    AuditorAware<String> testAuditor(AuditScenario scenario) {
        return () -> Optional.ofNullable(scenario.actor());
    }

    @Bean
    DateTimeProvider testTime(AuditScenario scenario) {
        return () -> Optional.of(scenario.now());
    }
}
~~~

Test cần nạp cấu hình này vào context đang dùng. Nếu test slice không tự quét mọi bean ứng dụng, phải import hoặc cấu hình tường minh.

AuditScenario là fixture mutable. Cần reset giữa các test và không để các test chạy song song cùng sửa một instance. Nếu suite cần chạy song song, dùng cơ chế cô lập phù hợp.

Mốc thời gian nên tương thích độ chính xác store hỗ trợ. Không assertion nanosecond nguyên vẹn nếu đường lưu thực tế chỉ giữ millisecond.

## 8. Kiểm thử auditing trên lần tạo và cập nhật

Với modifyOnCreate được đặt rõ là true, test mong đợi cả thông tin tạo và sửa được điền trong lần tạo.

~~~java
@Test
void keepsCreationMetadataAndChangesModificationMetadata() {
    Instant t0 = Instant.parse("2030-01-01T08:00:00Z");
    Instant t1 = Instant.parse("2030-01-01T09:00:00Z");

    auditScenario.changeTo("alice", t0);

    CustomerProfile created = repository.save(
            new CustomerProfile(
                    "profile-audit",
                    new CustomerCode("C-002"),
                    "Nguyen An"));

    assertThat(created.getCreatedBy()).isEqualTo("alice");
    assertThat(created.getCreatedAt()).isEqualTo(t0);
    assertThat(created.getLastModifiedBy()).isEqualTo("alice");
    assertThat(created.getLastModifiedAt()).isEqualTo(t0);

    auditScenario.changeTo("bob", t1);

    CustomerProfile current = repository
            .findById(created.getId())
            .orElseThrow();

    current.rename("Nguyen Binh");
    CustomerProfile updated = repository.save(current);

    CustomerProfile reloaded = repository
            .findById(updated.getId())
            .orElseThrow();

    assertThat(reloaded.getCreatedBy()).isEqualTo("alice");
    assertThat(reloaded.getCreatedAt()).isEqualTo(t0);
    assertThat(reloaded.getLastModifiedBy()).isEqualTo("bob");
    assertThat(reloaded.getLastModifiedAt()).isEqualTo(t1);
}
~~~

Test chứng minh chính sách của cấu hình này, không khẳng định mọi cấu hình auditing phải điền modified metadata ngay khi tạo.

Cần đọc và lưu đúng version hiện tại khi module dùng optimistic locking. Không tạo một đối tượng mới cùng ID nhưng bỏ version rồi coi đó là cách cập nhật tương đương.

### Các trường hợp auditing cần bổ sung

| Trường hợp | Hợp đồng cần xác định |
| --- | --- |
| Không có auditor hiện tại | Giữ trống, giữ giá trị cũ hay ứng dụng phải từ chối thao tác? |
| Đối tượng được nhận diện là mới | Created metadata có được điền theo chính sách? |
| Đối tượng được nhận diện là đã tồn tại | Created metadata có được giữ nguyên? |
| Dữ liệu cũ chưa có audit field | Chính sách bổ sung hoặc tương thích là gì? |
| Ghi bằng bulk/native update | Đường ghi đó có đi qua auditing không? |
| Reactive repository | Auditor và thời gian có được lấy trong ngữ cảnh reactive phù hợp không? |

AuditorAware trả Optional.empty không tự tương đương một lỗi xác thực. Nếu nghiệp vụ bắt buộc có danh tính, cần quy tắc riêng và test quy tắc đó.

## 9. Phân biệt domain event với lifecycle event và callback

Ba cơ chế có thể cùng xuất hiện nhưng không cùng ý nghĩa:

| Cơ chế | Nguồn gốc | Ví dụ |
| --- | --- | --- |
| Domain event | Aggregate đăng ký sự kiện nghiệp vụ | ProfileRenamed |
| Store lifecycle event | Hạ tầng module thông báo mốc xử lý dữ liệu | Sự kiện trước hoặc sau một thao tác mapping/lưu của module |
| Entity callback | Hạ tầng gọi extension point cho entity | BeforeConvertCallback của MongoDB |

Một store lifecycle event không tự là sự kiện nghiệp vụ. Một callback chạy trước ghi không chứng minh transaction đã commit. Domain event được phát cũng không tự chứng minh consumer đã nhận thông điệp bền vững ngoài tiến trình.

Không nên đặt tất cả side effect vào bất kỳ hook nào có tên “after” rồi giả định chúng đều chạy sau commit.

## 10. Kiểm thử domain event qua repository thật

AbstractAggregateRoot hỗ trợ đăng ký domain event. Hạ tầng repository có thể phát các sự kiện này qua những thao tác được hỗ trợ, thường gặp là save.

Điều cần kiểm tra là đường đi:

~~~text
Đổi trạng thái aggregate
  → registerEvent
    → Gọi repository được hỗ trợ
      → Phát sự kiện
        → Listener quan sát
~~~

Gọi rename không tự đồng nghĩa sự kiện đã được publish. Gọi native update cũng không tự tương đương lưu aggregate qua repository.

Một probe đồng bộ dành cho test:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.context.event.EventListener;

public class ProfileEventProbe {

    private final List<ProfileRenamed> events =
            new CopyOnWriteArrayList<>();

    @EventListener
    public void on(ProfileRenamed event) {
        events.add(event);
    }

    public List<ProfileRenamed> snapshot() {
        return List.copyOf(events);
    }

    public void clear() {
        events.clear();
    }
}
~~~

Probe cần là bean trong context thử nghiệm. Với cấu hình event đồng bộ đang được kiểm tra, có thể quan sát ngay sau lời gọi repository:

~~~java
@Test
void publishesRenameEventAndDoesNotRepublishClearedEvents() {
    CustomerProfile saved = repository.save(
            new CustomerProfile(
                    "profile-event",
                    new CustomerCode("C-003"),
                    "An"));

    eventProbe.clear();

    CustomerProfile current = repository
            .findById(saved.getId())
            .orElseThrow();

    current.rename("Binh");

    CustomerProfile renamed = repository.save(current);

    assertThat(eventProbe.snapshot()).containsExactly(
            new ProfileRenamed(saved.getId(), "Binh"));

    repository.save(renamed);

    assertThat(eventProbe.snapshot()).hasSize(1);
}
~~~

Test thứ hai trong chuỗi lưu kiểm tra việc không phát lại danh sách sự kiện đã được xử lý trong luồng được cấu hình. Nó không chứng minh hệ thống có bảo đảm exactly-once qua crash, retry hoặc nhiều tiến trình.

Cần giữ nguyên ngữ cảnh giả định: listener đồng bộ, không có thao tác khác tạo thêm sự kiện, và đối tượng trả về từ save được dùng cho lần lưu tiếp theo.

Nếu cần kiểm tra một thao tác delete, hãy xem module và repository interceptor có aggregate để lấy event hay không. Không coi deleteById tự động tải entity và phát domain event của entity đó.

## 11. Sự kiện được publish không đồng nghĩa transaction đã commit

Một listener thường và một transactional listener có hợp đồng khác nhau.

Với cấu hình đồng bộ, EventListener thường có thể chạy trong quá trình xử lý lời gọi, trước khi transaction ngoài commit. Nếu transaction sau đó rollback, listener có thể đã được gọi.

Listener theo transaction:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class CommittedProfileListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(ProfileRenamed event) {
        // Xử lý theo hợp đồng sau commit.
    }
}
~~~

Để test AFTER_COMMIT có ý nghĩa, phải có transaction thật và phải đi đến commit thật.

### Ma trận kiểm tra thời điểm

| Tình huống | EventListener đồng bộ | AFTER_COMMIT mặc định |
| --- | --- | --- |
| Sự kiện được publish trong transaction rồi commit | Có thể đã chạy trước commit | Chạy sau commit |
| Sự kiện được publish rồi transaction rollback | Có thể đã chạy trước rollback | Không chạy ở nhánh sau commit |
| Publish không có transaction phù hợp | Vẫn có thể nhận sự kiện | Mặc định không chạy khi không có transaction |
| Bật fallbackExecution | Không làm thay đổi bản chất listener thường | Có thêm hành vi ngoài transaction theo cấu hình |

Không bật fallbackExecution chỉ để làm test xanh nếu production cần đúng điều kiện sau commit. Nó thay đổi hợp đồng listener.

### Cấu hình transaction phụ thuộc store

Với ví dụ MongoDB, không mặc định standalone server và một annotation bất kỳ đã tạo được transaction nhiều thao tác. Cần cấu hình transaction manager, topology và tài nguyên hỗ trợ phù hợp.

Nếu test framework tự rollback sau mỗi test, listener AFTER_COMMIT có thể không chạy. Cần chủ động thiết kế test commit/rollback rồi quan sát ở đúng thời điểm, thay vì kết luận listener chưa được đăng ký.

Với listener bất đồng bộ, cần chờ điều kiện có thời hạn hoặc tín hiệu hoàn tất. Không dùng sleep cố định làm bằng chứng và không coi lời gọi repository trả về là consumer đã xử lý xong.

### Sau commit cũng không phải cơ chế giao thông điệp bền vững

Lỗi listener sau commit không làm transaction gốc tự rollback. Nếu listener ghi dữ liệu, cần ranh giới giao dịch và chính sách lỗi phù hợp.

Crash sau khi database commit nhưng trước khi gửi thông điệp có thể làm mất tác vụ gửi nếu chỉ dựa vào listener trong bộ nhớ. Khi yêu cầu có độ tin cậy cao hơn, cần cơ chế như outbox cùng retry và tính idempotent của consumer.

## 12. Kiểm thử đường ghi bỏ qua hạ tầng

Một hành vi đúng qua repository không chứng minh mọi đường ghi khác cũng chạy đủ callback, auditing và domain event.

Cần phân loại đường ghi mà ứng dụng thực sự sử dụng:

~~~text
Repository save
Store template API
Bulk update
Native query hoặc raw driver
Import dữ liệu
Tác vụ di chuyển dữ liệu
~~~

Một số API template có thể kích hoạt một phần lifecycle của module, nhưng không vì thế mà tự có domain-event interceptor của repository. Bulk hoặc raw operation cũng có thể bỏ qua bước mapping entity đang được test.

Với mỗi đường quan trọng, hãy hỏi:

1. Converter có tham gia cho giá trị đang ghi không?
2. Callback nào được gọi và nhận dạng dữ liệu gì?
3. Auditing có được áp dụng không?
4. Có aggregate để thu thập domain event không?
5. Transaction nào bao quanh thao tác và listener?

Không khẳng định một đường ghi chắc chắn bỏ qua hoặc chắc chắn kích hoạt mọi cơ chế chỉ dựa vào tên phương thức. Test bằng thao tác thực tế của module.

## 13. Cô lập test và quan sát đúng kết quả

Một integration test cho các cơ chế này nên có:

- Store và database/collection thử nghiệm được xác định rõ.
- Repository, mapping context và custom conversions thật.
- Callback cùng auditing configuration được nạp tường minh.
- Nguồn thời gian, auditor và event probe được điều khiển.
- Cách dọn dữ liệu và reset probe giữa các test.
- Ranh giới transaction phù hợp với điều cần chứng minh.

Không để test A đổi auditor sang bob rồi test B vô tình dùng lại bob. Không để event probe còn sự kiện của lần save fixture và quy chúng cho thao tác đang kiểm tra.

Nên kiểm tra ba mức quan sát khi cần:

~~~text
Kết quả trả về từ thao tác
Dữ liệu đọc lại qua repository
Biểu diễn lưu trữ hoặc side effect thực tế
~~~

Với JPA, persistence context có thể che việc đọc lại từ database; cần cách flush/clear phù hợp khi kiểm tra mapping. Với store khác, dùng cơ chế tương ứng, không sao chép EntityManager vào mọi test.

Nếu converter hoặc callback xử lý mã hóa, serialization hay thời gian, fixture phải chứa giá trị đủ để phát hiện sai biểu diễn. Chỉ kiểm tra đối tượng không null thường quá yếu.

## 14. Ma trận kiểm thử đề xuất

| Nhóm | Ca kiểm thử trọng tâm | Bằng chứng |
| --- | --- | --- |
| Converter unit | Chuẩn hóa, giá trị không hợp lệ, round trip | Logic chuyển đổi đúng |
| Converter integration | Đọc/ghi và kiểm tra raw representation | Đăng ký và mapping thật đúng |
| Callback unit | Hàm biến đổi entity | Kết quả thuật toán đúng |
| Callback integration | Lưu qua đường hỗ trợ rồi đọc lại | Callback thực sự tham gia persistence |
| Auditing tạo mới | Actor alice, thời gian T0 | Created và modified theo chính sách |
| Auditing cập nhật | Actor bob, thời gian T1 | Giữ created, đổi modified |
| Auditing thiếu actor | Không có auditor | Chính sách đã chọn được thể hiện rõ |
| Domain event | Đổi trạng thái rồi save | Đúng payload và số sự kiện trong luồng kiểm soát |
| Event clearing | Save lại khi không có sự kiện mới | Không phát lại event cũ trong hợp đồng được hỗ trợ |
| Transaction listener | Commit và rollback thật | Đúng giai đoạn và điều kiện thực thi |
| Đường ghi thay thế | Bulk/native/template đang dùng | Biết chính xác cơ chế nào được kích hoạt |

Không cần kiểm tra mọi chi tiết nội bộ bằng spy. Assertion vào kết quả lưu trữ, metadata và sự kiện có ý nghĩa thường bền hơn assertion vào số lần gọi một hàm nội bộ.

Chỉ assertion số lần gọi khi đó là một phần hợp đồng được kiểm soát. Retry, nhiều thao tác lưu hoặc cấu hình async có thể làm kỳ vọng “luôn đúng một lần” không còn hợp lệ.

## 15. Chẩn đoán test thất bại

| Biểu hiện | Điểm cần kiểm tra |
| --- | --- |
| Unit converter xanh nhưng raw field sai kiểu | Converter chưa được đăng ký hoặc không được chọn ở đường mapping đó |
| Callback gọi trực tiếp đúng nhưng dữ liệu lưu sai | Bean chưa được nạp, thao tác ghi khác đường kiểm tra hoặc mapping dùng giá trị khác |
| Created metadata đổi khi cập nhật | Nhận diện isNew sai, đối tượng mất version hoặc chính sách auditing khác kỳ vọng |
| Thời gian lệch nhỏ giữa các lần chạy | Dùng đồng hồ thực hoặc precision store không tương thích assertion |
| Auditor rỗng | Sai bean, thiếu ngữ cảnh danh tính hoặc fixture chưa được reset |
| Probe nhận sự kiện của fixture | Chưa reset probe trước thao tác cần đo |
| Event phát nhiều lần | Aggregate còn event, thao tác đăng ký lặp, retry hoặc nhiều đường publish |
| AFTER_COMMIT không chạy | Không có transaction, chỉ rollback hoặc listener/configuration chưa được nạp |
| Test xanh nhưng production mất thông điệp | Nhầm application event trong bộ nhớ với giao thông điệp bền vững |

Nên xác định lớp thất bại trước khi sửa test: logic thuần Java, wiring, mapping, lifecycle, transaction hay cơ chế giao sự kiện.

## 16. Bài tập áp dụng

1. Viết converter cho CustomerCode và kiểm tra cả biểu diễn lưu lẫn round trip.
2. Lưu CustomerProfile qua repository thật, đọc raw field để chứng minh code là chuỗi.
3. Kiểm tra searchName được cập nhật sau khi đổi displayName và lưu lại.
4. Dùng actor/thời gian cố định để kiểm tra lần tạo và lần cập nhật.
5. Mô phỏng thiếu auditor và diễn đạt chính sách nghiệp vụ rõ ràng.
6. Đăng ký ProfileRenamed, lưu aggregate rồi kiểm tra payload và việc không phát lại event cũ.
7. Nếu môi trường có transaction thật, kiểm tra listener AFTER_COMMIT ở cả commit và rollback.
8. Thực hiện một đường ghi thay thế đang dùng trong ứng dụng và xác định những hook nào thực sự chạy.

Mỗi test cần nêu rõ hành vi được chứng minh và đường thực thi đã sử dụng. Converter đúng logic, callback đã đăng ký, auditing điền đúng và sự kiện đến đúng giai đoạn là các hợp đồng liên quan nhưng cần bằng chứng riêng.
