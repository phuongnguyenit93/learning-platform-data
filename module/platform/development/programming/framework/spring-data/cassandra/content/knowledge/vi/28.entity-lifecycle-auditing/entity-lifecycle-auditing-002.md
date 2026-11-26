# ApplicationEvent và EntityCallback trong vòng đời lưu trữ

> **Chương:** Vòng đời và auditing  
> **Module:** SPRING_DATA_CASSANDRA — truy cập Apache Cassandra qua Spring Data entity mapping, repository, CassandraTemplate và CQL theo khóa phân vùng.  
> **Mục tiêu:** phân biệt lifecycle `ApplicationEvent` với `EntityCallback`, chọn đúng thời điểm kiểm tra/biến đổi entity, triển khai auditing đúng thứ tự và hiểu những thao tác không đi qua vòng đời mapping của Spring Data Cassandra.

## 1. Tình huống: lưu thiết bị và tự động điền thông tin audit

Một ứng dụng IoT lưu thiết bị vào bảng Cassandra theo `device_id`. Khi tạo hoặc cập nhật thiết bị, hệ thống muốn:

- Chuẩn hóa tên hiển thị: bỏ khoảng trắng ở hai đầu.
- Ghi người tạo/người sửa và thời gian thay đổi.
- Ghi log để phục vụ chẩn đoán sau khi lưu thành công.
- Kiểm tra tính hợp lệ trước khi ghi.
- Hỗ trợ cả repository, `CassandraTemplate` và các câu CQL tùy chỉnh.

Developer có thể nghĩ đến `ApplicationListener<BeforeSaveEvent<DeviceState>>` hoặc một `@EventListener` để chỉnh tên trước khi ghi. Nhưng **BeforeSaveEvent xảy ra sau khi Spring Data đã tạo statement từ entity**, nên chỉnh Java object lúc đó chưa chắc sửa dữ liệu sẽ được persist.

Spring Data Cassandra có hai cơ chế liên quan nhưng khác mục đích:

1. **Lifecycle ApplicationEvents**: sự kiện theo vòng đời mapping được gửi qua hạ tầng sự kiện Spring, hữu ích cho quan sát hoặc tích hợp nhẹ.
2. **EntityCallbacks**: hook có thứ tự xác định tại các checkpoint lưu trữ, có thể trả về entity đã biến đổi để Spring Data dùng ở bước tiếp theo.

**Quy tắc chọn nhanh:** nếu muốn thay đổi **dữ liệu thật được ghi**, ưu tiên `BeforeConvertCallback`; nếu muốn quan sát việc save/load/delete, cân nhắc lifecycle event nhưng không xem nó là một nguồn sự kiện nghiệp vụ bền vững.

## 2. Kết quả học tập

Sau bài này, bạn có thể:

- Vẽ được đường đi từ `repository.save(entity)` qua callback, mapping, CQL statement, Cassandra và lifecycle event.
- Nêu đúng các hook của `AbstractCassandraEventListener`: `onBeforeSave`, `onAfterSave`, `onBeforeDelete`, `onAfterDelete`, `onAfterLoad` và `onAfterConvert`.
- Viết `BeforeConvertCallback<DeviceState>` với đúng chữ ký `onBeforeConvert(entity, CqlIdentifier tableName)`.
- Giải thích vì sao `BeforeSaveCallback` nhận một `Statement<?>` đã được tạo, và sửa entity tại thời điểm đó không tự sửa statement.
- Sử dụng `@EnableCassandraAuditing`, `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy`.
- Hiểu rủi ro `isNew` khi Cassandra entity có UUID được cấp sẵn, và lý do cân nhắc `@Version` hoặc `Persistable`.
- So sánh hành vi của API đồng bộ, reactive và truy vấn CQL đi trực tiếp qua `CqlSession`.
- Thiết kế integration test chứng minh dữ liệu được lưu thật, callback chỉ gọi một lần theo điểm móc mong đợi, và event không thay thế reliable event delivery.

## 3. Các khái niệm cần phân biệt

| Khái niệm | Thuộc lớp nào? | Trách nhiệm |
| --- | --- | --- |
| `ApplicationEvent` | Spring Framework | Thông báo một tình huống qua application event multicaster |
| `CassandraMappingEvent` | Spring Data Cassandra | Gốc cho những sự kiện vòng đời mapping |
| `AbstractCassandraEventListener<T>` | Spring Data Cassandra | Lớp cơ sở đăng ký xử lý các event theo entity type |
| `EntityCallback<T>` | Spring Data Commons/Cassandra | Hook gọi tại checkpoint xác định, có thể trả entity thay đổi |
| `BeforeConvertCallback<T>` | Cassandra EntityCallback | Biến đổi entity **trước khi** tạo CQL statement |
| `BeforeSaveCallback<T>` | Cassandra EntityCallback | Nhận entity và statement **sau khi** mapping sang statement |
| `AuditingEntityCallback` | Spring Data Cassandra | Điền trường auditing ở bước before-convert |
| `CassandraRepository` | Spring Data | API repository, thường đi qua cơ chế mapping/template |
| `CassandraTemplate` | Spring Data Cassandra | API mapping cho insert/update/select/delete |
| `CqlTemplate`/`CqlSession` | CQL/driver | Truy vấn CQL cấp thấp, không tự kích hoạt toàn bộ entity lifecycle |

Các từ **event** và **callback** không đồng nghĩa. Event thông báo để listener quan sát; callback trả về giá trị để pipeline tiếp tục với kết quả ấy. Đây là khác biệt căn bản trong việc bảo đảm sửa entity đúng thời điểm.

## 4. Chuẩn bị schema theo partition key

Ví dụ dùng một bảng nhỏ phục vụ đọc theo ID thiết bị:

~~~sql
-- Keyspace telemetry phải được tạo và replication phải được
-- cấu hình theo môi trường; không dùng RF=1 của lab cho production.
CREATE TABLE IF NOT EXISTS telemetry.device_state_by_id (
    device_id     uuid PRIMARY KEY,
    display_name  text,
    firmware      text,
    created_at    timestamp,
    updated_at    timestamp,
    created_by    text,
    updated_by    text,
    version       bigint
);
~~~

`device_id` là partition key. Mọi ví dụ truy vấn một thiết bị đều cung cấp giá trị này, nên Cassandra định tuyến trực tiếp được partition. Lifecycle events không thể thay thế thiết kế bảng theo truy vấn; nếu cần lọc theo `firmware` của tất cả thiết bị, cần một read model/index phù hợp, không thêm event listener để quét toàn bảng.

Cột `version` được dùng trong ví dụ auditing có optimistic locking của Spring Data. Nó vừa hỗ trợ cơ chế phân biệt entity mới/cũ, vừa mang chi phí và semantics update riêng; nếu ứng dụng không cần optimistic locking, có thể xem phương án `Persistable` và new-state tracking đã kiểm thử.

**Lưu ý:** ví dụ DDL không tự tạo từ Java class. Tạo bảng bằng migration trước khi khởi chạy, và xác nhận kiểu `UUID`/`Instant`/`Long` tương thích Cassandra.

## 5. Entity Java: mapping và auditing metadata

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_state_by_id")
public class DeviceState {

    @PrimaryKey("device_id")
    private UUID deviceId;

    @Column("display_name")
    private String displayName;

    @Column("firmware")
    private String firmware;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("updated_at")
    private Instant updatedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("updated_by")
    private String updatedBy;

    @Version
    private Long version;

    public DeviceState() { }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    public String getFirmware() { return firmware; }
    public void setFirmware(String value) { firmware = value; }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { createdAt = value; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }

    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String value) { createdBy = value; }

    public String getUpdatedBy() { return updatedBy; }
    public void setUpdatedBy(String value) { updatedBy = value; }

    public Long getVersion() { return version; }
    public void setVersion(Long value) { version = value; }
}
~~~

Trong ứng dụng Cassandra, khóa UUID thường được tạo **trước** khi lưu. Không nên dùng `null` ID rồi hy vọng Cassandra tự phát sinh UUID. Nếu không có chiến lược phát hiện entity mới đáng tin cậy, auditing có thể coi đối tượng đã mang ID là đối tượng hiện hữu, làm sai `createdAt` và `createdBy`.

`@Version Long` là một lựa chọn giúp `isNew` dựa trên version null khi mới tạo, đồng thời bật optimistic locking. Phải kiểm tra câu CQL/LWT và chi phí của optimistic locking trong cluster thật, không thêm annotation chỉ để sửa test audit mà chưa đánh giá hiệu năng.

## 6. Dòng thời gian vòng đời lưu đối tượng

Một lần `repository.save(entity)` thông thường đi qua mapping pipeline tương ứng với `CassandraTemplate`. Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A["Repository / CassandraTemplate lưu entity"] --> B["BeforeConvertCallback + auditing"]
    B --> C["Map entity thành INSERT/UPDATE Statement"]
    C --> D["BeforeSaveEvent và BeforeSaveCallback"]
    D --> E["Thực thi statement trên Cassandra"]
    E --> F["AfterSaveEvent / xử lý hậu lưu"]
    F --> G["Trả kết quả về caller"]
~~~

Các sự kiện/callback có thể có điểm phát riêng và thứ tự chính xác phụ thuộc API/phiên bản. Trong Spring Data Cassandra, tài liệu nêu lifecycle events được publish **trước** entity callbacks tương ứng; vì vậy cần nắm rõ một `BeforeSaveEvent` xảy ra **sau khi đã tạo statement**, không phải “trước khi mapping”.

Giữ riêng hai khái niệm:

- **Before convert:** entity còn có thể được sửa để thay đổi giá trị đi vào statement.
- **Before save:** statement đã hình thành; thay entity đơn thuần không làm mapping lại statement một cách tự động.

Đây là nguyên tắc quan trọng nhất khi thiết kế normalization, validation và auditing.

## 7. ApplicationEvents của Spring Data Cassandra

Một `AbstractCassandraEventListener<DeviceState>` có thể override các hook:

| Hook | Điểm xuất hiện | Ví dụ sử dụng |
| --- | --- | --- |
| `onBeforeSave` | Trước insert/update thực sự, **sau khi tạo statement** | Log/kiểm tra thông tin statement hoặc metric |
| `onAfterSave` | Sau khi template hoàn thành bước lưu | Quan sát kết quả/ghi metric nhẹ |
| `onBeforeDelete` | Trước lệnh delete qua template | Ghi thông tin audit thao tác có chủ đích |
| `onAfterDelete` | Sau bước delete qua template | Metric xóa, không coi là transaction hook |
| `onAfterLoad` | Sau khi lấy row từ Cassandra, trước chuyển thành POJO | Quan sát lượng dữ liệu đọc |
| `onAfterConvert` | Sau khi chuyển row thành đối tượng Java | Kiểm tra trạng thái entity được map |

Lifecycle mapping events chủ yếu dành cho **root-level types**; không mặc định phát event độc lập cho mọi nested object/UDT nằm trong aggregate root. Tần suất event còn có thể rất cao khi đọc nhiều row, gây overhead nếu listener làm việc nặng.

**Đừng giả định mọi hàm `CassandraTemplate` đều phát đủ event như save entity.** Những đường cập nhật bằng CQL trực tiếp, `Query + Update`, custom statement và template overload có thể có điểm móc khác nhau. Phải kiểm thử chính đường API mà ứng dụng sử dụng.

## 8. Viết listener quan sát ApplicationEvent

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.cassandra.core.mapping.event.AbstractCassandraEventListener;
import org.springframework.data.cassandra.core.mapping.event.AfterSaveEvent;
import org.springframework.data.cassandra.core.mapping.event.BeforeSaveEvent;
import org.springframework.stereotype.Component;

@Component
public class DeviceStateEventListener
        extends AbstractCassandraEventListener<DeviceState> {

    private static final Logger log =
        LoggerFactory.getLogger(DeviceStateEventListener.class);

    @Override
    public void onBeforeSave(BeforeSaveEvent<DeviceState> event) {
        DeviceState source = event.getSource();
        log.debug("About to save device {}, version={}",
            source.getDeviceId(), source.getVersion());
    }

    @Override
    public void onAfterSave(AfterSaveEvent<DeviceState> event) {
        DeviceState source = event.getSource();
        log.debug("Save completed for device {}",
            source.getDeviceId());
    }
}
~~~

Listener này chỉ quan sát. Hãy tránh log `payload` nhạy cảm, token hoặc toàn bộ dữ liệu người dùng. Các hook chỉ cần làm việc nhẹ và không block thread quá lâu.

**Không dùng `onAfterSave` để khẳng định Cassandra đã đồng bộ mọi replica hoặc một transaction nhiều bảng đã commit.** Cassandra write consistency chỉ xác nhận theo CL, có thể còn replica chưa hội tụ. Sự kiện Spring là tín hiệu của **pipeline client-side**, không phải bản ghi event log bền vững ở cluster.

## 9. Vì sao sửa entity trong BeforeSaveEvent dễ sai?

Giả sử code làm thế này:

~~~java
@Override
public void onBeforeSave(BeforeSaveEvent<DeviceState> event) {
    DeviceState state = event.getSource();
    state.setDisplayName(state.getDisplayName().trim());
}
~~~

Code nhìn có vẻ hợp lý vì tên hook có chữ “BeforeSave”. Nhưng Spring Data Cassandra đã chuyển entity thành statement **trước khi** sự kiện này được phát. Việc sửa `state` lúc này có thể chỉ sửa Java object mà **không sửa giá trị đã bind trong CQL**.

Vì vậy có thể xảy ra:

~~~text
Dữ liệu input:     "  Kho A  "
Statement đã tạo: "  Kho A  "
Listener đổi Java object thành: "Kho A"
Dữ liệu persist:  "  Kho A  "   (vẫn còn khoảng trắng)
~~~

Đây là lỗi rất khó phát hiện khi test chỉ xem object sau `save` mà không đọc lại row từ Cassandra.

Nếu muốn chuẩn hóa giá trị **trước mapping**, dùng `BeforeConvertCallback`. Nếu cần kiểm tra statement CQL cụ thể, `BeforeSaveCallback` có thể được dùng để **inspect**, nhưng cần hiểu nó không tự remap entity.

## 10. EntityCallback: hook đồng bộ có thứ tự

`EntityCallback` cho phép code trả về entity được sửa hoặc object mới tại các checkpoint. Spring Data gọi callback theo thứ tự xác định trong pipeline đồng bộ; reactive path có interface tương ứng.

Với Cassandra, các callback được tài liệu chính thức liệt kê bao gồm:

| Callback | Chữ ký cơ bản | Ý nghĩa |
| --- | --- | --- |
| `BeforeConvertCallback<T>` | `T onBeforeConvert(T entity, CqlIdentifier tableName)` | Sửa entity **trước** khi thành statement |
| `BeforeSaveCallback<T>` | `T onBeforeSave(T entity, CqlIdentifier tableName, Statement<?> statement)` | Nhận entity và statement đã sinh; sửa entity không tự sửa statement |
| `AuditingEntityCallback` | `Object onBeforeConvert(Object entity, CqlIdentifier tableName)` | Điền created/modified metadata |
| `ReactiveBeforeConvertCallback<T>` | Trả `Publisher<T>`/`Mono<T>` theo API reactive | Hook trên reactive execution chain |
| `ReactiveBeforeSaveCallback<T>` | Trả reactive publisher theo API reactive | Hook trước khi thực thi statement trong luồng reactive |

Không suy từ tên interface của module khác rằng Cassandra chắc chắn có `AfterSaveCallback` hay `AfterConvertCallback` với cùng semantics. Tài liệu Cassandra nên là nguồn xác nhận cụ thể.

**Khác với event publishing** vốn phụ thuộc `ApplicationEventMulticaster`, entity callbacks được thiết kế để gọi theo thứ tự và sử dụng entity mà callback trả về, phù hợp hơn cho việc biến đổi dữ liệu.

## 11. BeforeConvertCallback dùng để chuẩn hóa dữ liệu

Ví dụ normalize tên và validate độ dài trước khi Spring Data tạo statement:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import org.springframework.core.annotation.Order;
import org.springframework.data.cassandra.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(50)
public class NormalizeDeviceName
        implements BeforeConvertCallback<DeviceState> {

    @Override
    public DeviceState onBeforeConvert(
            DeviceState entity, CqlIdentifier tableName) {

        if (entity.getDeviceId() == null) {
            throw new IllegalArgumentException(
                "deviceId là bắt buộc");
        }

        String raw = entity.getDisplayName();
        if (raw != null) {
            String normalized = raw.strip();
            if (normalized.length() > 120) {
                throw new IllegalArgumentException(
                    "displayName quá dài");
            }
            entity.setDisplayName(normalized);
        }

        return entity;
    }
}
~~~

Ở đây:

1. Hook chạy **trước khi entity được chuyển thành CQL statement**.
2. `entity.setDisplayName(normalized)` có thể ảnh hưởng giá trị Spring Data ghi.
3. `return entity` là một phần của hợp đồng callback.
4. `@Order(50)` chọn chạy trước auditing callback có order `100` trong tài liệu Cassandra hiện hành; xem lại version thực tế nếu phụ thuộc chặt vào thứ tự.
5. Cần áp dụng validation cho cả đường CQL trực tiếp nếu hệ thống có DAO dùng `CqlSession` và không qua entity mapping.

Với entity immutable, thay vì mutate, callback có thể trả về **bản sao** có field đã chuẩn hóa, nếu mapping của dự án hỗ trợ kiểu đó. Không giả định mọi setter trên record/immutable object tồn tại.

## 12. BeforeSaveCallback: statement đã được tạo

Chữ ký chính xác của Cassandra callback:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.cql.Statement;
import org.springframework.data.cassandra.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class DeviceStatementInspector
        implements BeforeSaveCallback<DeviceState> {

    @Override
    public DeviceState onBeforeSave(
            DeviceState entity,
            CqlIdentifier tableName,
            Statement<?> statement) {

        if (statement == null) {
            throw new IllegalStateException("Statement missing");
        }

        // Chỉ kiểm tra; không giả định sửa entity ở đây
        // sẽ cập nhật lại các giá trị đã map trong statement.
        return entity;
    }
}
~~~

`Statement<?>` là câu lệnh đã được tạo từ entity. Nếu callback thay `entity.setDisplayName(...)` lúc này, statement **không tự được tái tạo**.

Có thể dùng hook này để kiểm tra đặc tính câu lệnh hoặc phát metric, nhưng tránh:

- Phụ thuộc vào `statement.toString()` như một representation CQL đầy đủ có bind values chính xác.
- Đọc/log những giá trị nhạy cảm.
- Thực hiện truy vấn phụ liên tục, gây thêm network I/O cho mọi lần ghi.
- Tự sửa statement theo cách không được API contract hỗ trợ.
- Tạo side effect không idempotent khi caller retry.

Muốn đảm bảo normalization được ghi, dùng `BeforeConvertCallback` hoặc một service validation trước `save`, rồi đọc lại dữ liệu để chứng minh.

## 13. So sánh event listener và entity callback

| Tiêu chí | ApplicationEvent | EntityCallback |
| --- | --- | --- |
| Kiểu API | Spring application event/listener | Interface callback gắn với entity type |
| Mục đích mạnh nhất | Quan sát, logging, tích hợp nhẹ | Sửa/validate entity tại điểm móc |
| Thứ tự | Phụ thuộc multicaster và cấu hình listener | Có thứ tự trong pipeline, hỗ trợ `@Order`/`Ordered` |
| Bất đồng bộ | Có thể async nếu multicaster dùng executor | Hợp đồng sync/reactive tách riêng, chạy trong processing chain |
| Trả entity đã sửa | Không phải hợp đồng chính của event | Có; caller sử dụng giá trị callback trả |
| Trước mapping | Không dùng `BeforeSaveEvent` để bảo đảm | Dùng `BeforeConvertCallback` |
| Sau mapping | `BeforeSaveEvent`, `AfterSaveEvent` | `BeforeSaveCallback` nhận statement |
| Phát trên low-level CQL? | Không mặc định | Không mặc định |
| Thích hợp làm event log bền vững? | **Không** | **Không** |

Nếu mục tiêu là kiểm soát dữ liệu persist, callback là lựa chọn rõ ràng hơn. Nếu chỉ cần telemetry/logging, event listener có thể phù hợp, với giới hạn về chi phí và thứ tự.

## 14. Ordering của callbacks và auditing

Theo tài liệu Spring Data Cassandra hiện hành:

- `AuditingEntityCallback` thực hiện `BeforeConvertCallback` ở **order 100**.
- `BeforeConvertCallback` và `BeforeSaveCallback` thông thường có mặc định `Ordered.LOWEST_PRECEDENCE` nếu không khai báo order khác.
- Có thể dùng `@Order` hoặc implement `Ordered` để điều khiển thứ tự.
- Event mapping tương ứng được publish trước EntityCallback theo tài liệu, nhưng không nên dựa vào thứ tự của listener asynchronous để biến đổi state.

Ví dụ:

~~~text
@Order(50) NormalizeDeviceName
    ↓
order 100 AuditingEntityCallback
    ↓
các BeforeConvertCallback khác (nếu có, theo thứ tự)
    ↓
Map entity -> Statement
    ↓
BeforeSaveEvent / BeforeSaveCallback
    ↓
Thực thi CQL
~~~

Lựa chọn order 50 có lý do: auditing thấy entity đã được chuẩn hóa trước khi ghi metadata.

**Không đồng nghĩa mọi callback chạy đúng một lần trong mọi tình huống.** Một request HTTP có thể retry `save`; ORM layer hoặc reactive subscription có thể thực thi thêm lượt; caller cũng có thể save nhiều lần. Chọn logic callback idempotent và không phụ thuộc “chỉ gọi đúng một lần trên toàn hệ thống”.

## 15. Bật Cassandra auditing

Spring Data Cassandra hỗ trợ annotation-based auditing:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.EnableCassandraAuditing;
import org.springframework.data.domain.AuditorAware;

@Configuration
@EnableCassandraAuditing(auditorAwareRef = "auditorProvider")
public class CassandraAuditConfiguration {

    @Bean
    public AuditorAware<String> auditorProvider() {
        // Giá trị demo để thấy trường created_by/updated_by.
        // Production phải dùng danh tính từ auth context được xác thực.
        return () -> java.util.Optional.of("system-demo");
    }
}
~~~

Khi entity có `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy`, auditing infrastructure có thể điền metadata tại **before-convert**, miễn phát hiện entity mới/cũ đúng.

`@EnableCassandraAuditing` còn có các tùy chọn như `setDates`, `modifyOnCreate`, `dateTimeProviderRef`. Vì `modifyOnCreate` thường mặc định là true, một entity mới có thể được điền cả created và lastModified fields ngay khi tạo. Nếu sản phẩm muốn trường updatedAt chỉ có khi sửa lần hai, cần chọn policy tương ứng và test.

Không để `createdBy` và `updatedBy` phụ thuộc vào tên người dùng do HTTP client tự khai nếu đã có authentication; nên lấy chủ thể từ hệ thống bảo mật hoặc service identity đáng tin.

## 16. AuditorAware lấy đúng người thao tác

Trong Spring Security ứng dụng servlet, provider có thể đọc principal đã xác thực:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null ||
                !authentication.isAuthenticated()) {
            return Optional.empty();
        }

        String principalName = authentication.getName();
        return Optional.ofNullable(principalName);
    }
}
~~~

Đây chỉ là ví dụ: một token anonymous vẫn có thể được Spring Security đánh dấu authenticated trong một số cấu hình. Ứng dụng thật cần loại trừ anonymous principal và định nghĩa behavior cho system/batch jobs.

Nếu dùng **reactive Spring WebFlux**, không dùng `ThreadLocal` SecurityContextHolder như một giải pháp mặc định để lấy principal qua nhiều threads. Cần `ReactiveAuditorAware` và Reactor context/security integration tương ứng.

Đừng ném toàn bộ access token, email cá nhân không cần thiết hoặc PII vào cột `created_by`. Có thể dùng stable actor ID/service account ID, phù hợp retention và chính sách dữ liệu.

## 17. Cassandra không tự sinh ID và ảnh hưởng đến auditing isNew

Với Cassandra, ứng dụng thường tạo UUID trước khi insert:

~~~java
DeviceState state = new DeviceState();
state.setDeviceId(java.util.UUID.randomUUID());
state.setDisplayName("Kho A");

repository.save(state);
~~~

Nếu **không** có `@Version` hoặc chiến lược `Persistable.isNew()` đáng tin, Spring Data Commons mặc định có thể dùng ID để quyết định newness. Vì ID đã khác null, đối tượng có thể bị coi là **không mới**, làm `@CreatedDate`/`@CreatedBy` không hoạt động đúng như mong đợi.

Có hai hướng:

1. **Optimistic locking bằng `@Version`:** version null báo entity mới; version được quản lý khi save, đồng thời có kiểm tra cập nhật cạnh tranh.
2. **`Persistable<UUID>`:** cung cấp `isNew()` được duy trì chính xác qua lifecycle; các field trạng thái tạm phải đánh dấu `@Transient`.

Không nên tạo `isNew() { return true; }` vĩnh viễn: mọi lần save sau có thể bị coi là tạo mới, phá audited timestamps. Nếu entity được đọc từ Cassandra rồi save lại, cần đảm bảo trạng thái isNew đã được cập nhật đúng.

Với `@Version`, việc triển khai optimistic locking thường gắn với LWT/conditional write, có overhead so với upsert thông thường. Kiểm tra thông số theo version Spring Data Cassandra và SLO ghi thiết bị trước khi chọn.

## 18. Auditing không phải lịch sử bất biến của mọi thao tác

`created_at`/`updated_at` và `created_by`/`updated_by` là **metadata hiện trạng** của entity. Chúng không tự lưu một bản ghi vĩnh viễn cho từng mutation.

Ví dụ:

~~~text
10:00 tạo thiết bị:
  created_by = alice
  updated_by = alice

10:05 bob đổi firmware:
  created_by = alice
  updated_by = bob

10:15 carol đổi displayName:
  created_by = alice
  updated_by = carol
~~~

Sau lần cuối, bảng chính chỉ phản ánh metadata gần nhất. Nếu luật nghiệp vụ cần biết **ai sửa gì, trước/sau ra sao, tại thời điểm nào**, cần thiết kế bảng audit history/event log riêng cùng policy lưu trữ, idempotency và quyền truy cập.

Cassandra có TTL, tombstone, replication và consistency. `updated_at` là thời điểm nghiệp vụ trong một cột; nó không nhất thiết bằng **writetime** của cell Cassandra hoặc thời điểm mọi replica hội tụ.

**Không coi auditing annotation là cơ chế compliance audit log không thể sửa/xóa.** Cần lưu trữ bền vững, retention, chống chỉnh sửa, reconciliation và quy trình phục hồi riêng nếu có yêu cầu kiểm toán.

## 19. ApplicationEvent bất đồng bộ: rủi ro ordering và mutation

Spring dùng `ApplicationEventMulticaster` để phát event. Nếu cấu hình multicaster với một `TaskExecutor` bất đồng bộ hoặc listener có cơ chế chạy async, event handler có thể chạy trên thread khác và ở thời điểm khó dự đoán so với pipeline persistence.

Ví dụ nguy hiểm:

~~~text
Thread A:
  map DeviceState -> Statement
  publish BeforeSaveEvent
  execute CQL

Thread B:
  BeforeSaveEvent listener
  mutate state.displayName
~~~

Không có bảo đảm thread B hoàn thành việc mutate **trước** khi thread A thực thi statement. Ngay cả với listener đồng bộ, lúc BeforeSaveEvent được gọi statement đã được sinh ra.

Hệ quả:

- Đừng dùng `ApplicationEvent` bất đồng bộ để validate dữ liệu bắt buộc trước save.
- Đừng dùng listener để phát sinh UUID/key hoặc auditing timestamp mà statement cần chứa.
- Đừng dựa vào event ordering giữa nhiều listeners để thi hành business invariant.
- Đừng xuất bản side effect không idempotent mà không xét retry/timeout.

Dùng `BeforeConvertCallback` cho mutation cần đồng bộ với statement. Dùng event listeners cho quan sát, nhất là metric/log nhẹ; nếu cần workflow bất đồng bộ có độ tin cậy cao, dùng message log/outbox kiến trúc phù hợp.

## 20. Reactive EntityCallback và Reactive Cassandra

Spring Data Cassandra phân biệt callback **synchronous** và **reactive**. Khi API lưu trữ là reactive, callback sync không tự động được dùng trong mọi trường hợp; cần các interface reactive như `ReactiveBeforeConvertCallback<T>`.

Ví dụ ý tưởng:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import org.springframework.data.cassandra.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveDeviceNormalizer
        implements ReactiveBeforeConvertCallback<DeviceState> {

    @Override
    public Mono<DeviceState> onBeforeConvert(
            DeviceState entity, CqlIdentifier tableName) {

        if (entity.getDisplayName() != null) {
            entity.setDisplayName(entity.getDisplayName().strip());
        }

        return Mono.just(entity);
    }
}
~~~

Callback reactive được thực thi trong lifecycle của publisher, thường **khi có subscription**. Nếu một `Mono` bị subscribe nhiều lần, pipeline có thể chạy nhiều lần và callback có thể được gọi lại.

Không block một reactive callback để gọi HTTP/CQL đồng bộ vì có thể làm nghẽn event-loop. Nếu thực sự cần tương tác bất đồng bộ, giữ thao tác trong reactive chain, có timeout, error handling và context propagation rõ ràng.

Với reactive auditing, sử dụng `ReactiveAuditingEntityCallback` và `ReactiveAuditorAware` phù hợp, không copy nguyên provider ThreadLocal của servlet.

## 21. CqlSession và raw CQL bỏ qua entity lifecycle mapping

Spring Data lifecycle callbacks áp dụng khi hoạt động đi qua **mapping/template pipeline** tương ứng. Nếu code gọi driver trực tiếp:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

public final class RawDeviceWriter {
    private final CqlSession session;

    public RawDeviceWriter(CqlSession session) {
        this.session = session;
    }

    public void updateFirmware(java.util.UUID id, String firmware) {
        var ps = session.prepare(
            "UPDATE telemetry.device_state_by_id "
          + "SET firmware = ? WHERE device_id = ?");
        session.execute(ps.bind(firmware, id));
    }
}
~~~

Driver chỉ nhận CQL/bind values; nó không biến `RawDeviceWriter` thành một Spring Data entity save. Do đó:

- `NormalizeDeviceName` không tự chạy.
- Auditing callback không tự điền `updated_at` và `updated_by`.
- `AfterSaveEvent<DeviceState>` không tự được phát chỉ vì CQL ghi một row tương ứng.
- Logic validation phải được thực thi ở service/DAO hoặc trong một shared domain component.
- Cần tự kiểm soát consistency, timeout, retry, TTL và idempotency theo contract.

**Cẩn thận về query shape:** ví dụ CQL trên bảng demo có partition key `device_id` nên hợp lệ; nếu bảng dùng composite key phải bind đủ các thành phần cần thiết, không dùng `ALLOW FILTERING` để “sửa” mutation thiếu khóa.

## 22. Query + Update không nhất thiết tương đương save(entity)

Khi dùng `CassandraTemplate`, có nhiều đường cập nhật:

~~~java
template.insert(deviceState);
template.update(deviceState);

template.update(query, update, DeviceState.class);
~~~

Các đường có thể đi qua những nhánh xử lý khác nhau. `update(query, update, ...)` có thể thao tác trực tiếp vào các cột được chỉ định mà **không có một entity domain đầy đủ** để truyền qua các callback giống `save(entity)`.

Vì vậy không nên khẳng định:

~~~text
"Mọi update Cassandra đều tự gọi BeforeConvertCallback,
nên audit update_at luôn được điền."
~~~

Thay vào đó:

- Xác định API thực tế mà từng service dùng.
- Viết integration test cho chính API đó, kiểm tra trường được lưu.
- Với partial update, chỉ rõ mutation `updated_at`/`updated_by` có chủ đích nếu callback không tham gia.
- Không gọi `repository.save(entity)` chỉ để “kích hoạt audit” khi API PATCH phải giữ nguyên các cột không được gửi. Full-entity save có thể có semantics null/tombstone khác.

Event/callback là **hợp đồng của một đường API cụ thể**, không phải trigger database cho mọi CQL mutation.

## 23. Vòng đời read: AfterLoadEvent và AfterConvertEvent

Khi đọc entity qua các phương thức mapping của `CassandraTemplate`:

~~~text
SELECT từ Cassandra
  ↓
Row trả về
  ↓
AfterLoadEvent
  ↓
Mapping row -> DeviceState
  ↓
AfterConvertEvent
  ↓
Trả DeviceState cho caller
~~~

`AfterLoadEvent` xảy ra khi row đã được lấy về nhưng chưa chuyển thành entity. `AfterConvertEvent` xảy ra sau mapping, phù hợp nếu listener cần quan sát đối tượng Java đã hình thành.

Nếu một trang có 10.000 row, event/listener có thể được kích hoạt theo từng row. Logging toàn bộ đối tượng hoặc gọi service bên ngoài ở mỗi `onAfterConvert` rất dễ tạo N+1 I/O và tăng p99.

Không sửa persisted state chỉ để tạo computed field trong read event rồi mong Cassandra tự lưu. Nếu cần một field hiển thị tính toán, có thể làm trong DTO mapping/service hoặc projection phù hợp.

## 24. Vòng đời delete: BeforeDeleteEvent và AfterDeleteEvent

Cassandra delete được thực hiện bằng tombstone, không phải xóa vật lý ngay. Với template delete entity:

~~~text
CassandraTemplate.delete(...)
    ↓
BeforeDeleteEvent
    ↓
Thực thi DELETE CQL
    ↓
AfterDeleteEvent
~~~

Sự kiện sau xóa không có nghĩa tombstone đã được compact/purge hoặc đã đồng bộ tới mọi replica. Nó chỉ phản ánh mốc xử lý của API/statement theo consistency level.

Nếu business phải giữ audit event khi xóa, một `AfterDeleteEvent` listener ghi vào hệ thống khác **không tạo transaction nguyên tử** với CQL DELETE. Nếu Cassandra xóa thành công nhưng listener lỗi hoặc tiến trình bị kill, có thể thiếu audit record. Nếu listener ghi trước mà DELETE thất bại, có thể có audit record “đã xóa” không đúng.

Giải pháp phải cân nhắc event log bền vững, quy trình command/audit outbox theo kiến trúc được hỗ trợ và reconciliation, thay vì phụ thuộc vào một listener trong memory.

## 25. Không nhầm ApplicationEvent với domain event đáng tin cậy

Lifecycle `ApplicationEvent` là thông báo nội bộ quá trình mapping, không tự được gửi sang Kafka, RabbitMQ hoặc lưu bền vững khi process crash.

Ví dụ nguy hiểm:

~~~java
@Override
public void onAfterSave(AfterSaveEvent<DeviceState> event) {
    externalGateway.sendDeviceUpdated(event.getSource());
}
~~~

Nếu `externalGateway` chậm, thất bại hoặc gửi thành công rồi client timeout và retry, hành vi có thể khác mong muốn:

- Người dùng thấy lưu thành công nhưng message chưa đến nơi.
- Message có thể bị gửi hai lần.
- Phía downstream có thể xử lý lặp nếu không có idempotency key.
- Side effect trong listener có thể làm tăng latency/error rate của API.
- Spring Event không cung cấp replay sau khi service restart.

Với dữ liệu quan trọng, một phương án là ghi **domain event vào nguồn durable** và có projector/consumer idempotent. Cassandra không cung cấp transaction ACID xuyên Kafka và nhiều Cassandra partitions; phải thiết kế retry, dedup, reconciliation và cách xử lý partial failures.

## 26. Idempotency của callback và event listener

Một callback normalize bằng `strip()` là ví dụ operation idempotent:

~~~text
"  Kho A  " -> "Kho A"
"Kho A"     -> "Kho A"
~~~

Nếu callback được gọi lặp lại, kết quả vẫn không đổi. Ngược lại, những hành động sau có thể không idempotent:

- Tăng một counter mỗi lần `BeforeConvertCallback` chạy.
- Tạo UUID event mới cho mỗi lần save/retry.
- Gửi email/thông báo từ `onAfterSave` không có dedup.
- Ghi một record audit history không có event ID ổn định.
- Đặt timestamp ngẫu nhiên ở mỗi lần callback khiến retry thay đổi thứ tự mutation.

Cassandra có write timestamp và cơ chế giải quyết xung đột giữa replicas. Khi retry một CQL mutation, client timeout không đồng nghĩa write trước đó chưa thành công. Vì thế side effect lifecycle phải có **idempotency policy**, không chỉ đặt trong tên hook “after”.

## 27. Testing: kiểm tra dữ liệu lưu, không chỉ object Java

Để kiểm tra `BeforeConvertCallback` thật sự chuẩn hóa tên, cần ghi rồi đọc lại từ Cassandra.

Giả sử repository:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceStateRepository
        extends CassandraRepository<DeviceState, UUID> {
}
~~~

Mẫu test tích hợp (schema và Cassandra test đã được chuẩn bị):

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DeviceStateLifecycleIT {

    @Autowired
    DeviceStateRepository repository;

    @Test
    void beforeConvertNormalizationIsPersisted() {
        DeviceState state = new DeviceState();
        UUID id = UUID.randomUUID();
        state.setDeviceId(id);
        state.setDisplayName("  Kho A  ");

        repository.save(state);

        DeviceState loaded =
            repository.findById(id).orElseThrow();

        assertThat(loaded.getDisplayName()).isEqualTo("Kho A");
    }
}
~~~

Nên dùng Testcontainers hoặc cluster integration test riêng, với schema/migration giống production. Đừng dùng một mock `CassandraRepository` để kết luận callback thực sự được Spring Data gọi.

**Lưu ý:** vì entity ví dụ có `@Version`, test cần hạ tầng/phiên bản Cassandra hỗ trợ optimistic locking và bảng có cột `version` tương ứng. Nếu dự án không dùng version, thay bằng chiến lược new-state tracking có kiểm chứng.

## 28. Testing: vì sao BeforeSave không đủ để mutate statement?

Một test quan trọng gồm hai callback:

1. `BeforeConvertCallback` thay `displayName` bằng giá trị chuẩn hóa.
2. `BeforeSaveCallback` cố thay `displayName` sang chuỗi khác **sau** khi statement đã tạo.

Ví dụ logic:

~~~text
Input:            "  Kho A  "
BeforeConvert:    "Kho A"
Statement:        display_name="Kho A"
BeforeSave:       entity.displayName="Kho B"

Đọc trực tiếp Cassandra:
  display_name = "Kho A" (nếu callback chỉ sửa object)
~~~

Test này minh họa vì sao API trả một Java object có trường `Kho B` không chứng minh persistence đã chứa `Kho B`. Assertion đúng là **đọc lại row từ database** hoặc kiểm tra câu CQL/bind values theo cơ chế an toàn của driver.

Không nên cố tình đưa callback sai vào hệ thống production để kiểm thử; thực hiện trong test fixture riêng và tháo nó khỏi context sau test.

## 29. Testing: auditing created/modified và isNew

Ma trận kiểm thử:

| Kịch bản | Kỳ vọng cần kiểm chứng |
| --- | --- |
| Create với UUID cấp trước và version null | `createdAt`/`createdBy` được điền; version được quản lý |
| Save lại entity đã có version | `createdAt` giữ nguyên, `updatedAt`/`updatedBy` theo actor mới |
| Save với version cũ do concurrent update | Optimistic locking xử lý đúng, không âm thầm ghi đè |
| Đọc entity rồi save tiếp | Newness không bị nhận nhầm là create |
| Thiếu authentication | Actor dùng system identity theo policy hoặc auditing field absent, không giả mạo |
| Async/reactive save | Có provider/callback tương ứng, actor context không bị mất |
| Raw CqlSession UPDATE | Không giả định auditing callback tự chạy |
| Partial Query+Update | Kiểm tra thực tế field auditing có được ghi hay không |
| Retry cùng mutation | Không sinh audit event trùng ngoài ý muốn |
| Delete bằng raw CQL | Không kỳ vọng Spring mapping event được phát |

Nếu production dùng nhiều đường ghi, cần kiểm thử **từng đường** thay vì một happy-path `repository.save`. Test nên xác nhận dữ liệu ở Cassandra, không chỉ kiểm tra callback được mock gọi.

## 30. Testing: ghi nhận event lifecycle và thứ tự

Có thể dùng một test-only listener lưu event markers trong một collection in-memory **cô lập theo test**, rồi assert những giai đoạn quan sát được:

~~~text
BeforeConvertCallback
BeforeSaveEvent
BeforeSaveCallback
AfterSaveEvent

Read:
AfterLoadEvent
AfterConvertEvent
~~~

Các event/callback không nhất thiết bao phủ mọi overload/API và thứ tự chi tiết cần xác minh theo phiên bản Spring Data Cassandra. Không viết test dựa vào thứ tự hoàn tất của **asynchronous event listeners**, vì executor có thể xáo trộn thực thi.

Để test thứ tự một cách đáng tin cậy:

- Chỉ dùng synchronous event multicaster trong test kiểm chứng ordering.
- Ghi dấu bằng một queue/thread-safe test probe.
- Tạo một entity có ID duy nhất và lọc markers theo ID đó.
- Tránh listener thực hiện side effects ngoài database test.
- Assert rằng `BeforeConvertCallback` sửa giá trị trước khi CQL statement được sinh.
- Đọc database để chứng minh thay đổi được persist.
- Xác minh không nhận event với raw `CqlSession` khi đường đó không qua mapping.
- Không khẳng định callback được gọi **đúng một lần toàn đời request** khi có retries.

## 31. Hiệu năng: vòng đời có thể nhân chi phí theo số row

Một API đọc 2.000 thiết bị có thể khiến `AfterLoadEvent` và `AfterConvertEvent` xử lý nhiều lần. Nếu mỗi event listener thực hiện một query phụ, độ trễ có thể tăng rất mạnh.

Ví dụ:

~~~text
SELECT 2.000 DeviceState rows
    ↓
AfterLoadEvent × 2.000
AfterConvertEvent × 2.000
    ↓
Nếu mỗi listener gọi thêm một query:
Có thể thêm ~4.000 requests
~~~

Đây là một dạng **N+1** do lifecycle hook. Giữ event listeners đơn giản, không truy cập mạng hoặc ghi log toàn row. Với logic enrich dữ liệu cho UI, cân nhắc projection read model, batch lookup có giới hạn hoặc DTO mapping phù hợp.

Theo dõi:

- p95/p99 latency của `save`/`find`.
- Số callback/event được gọi mỗi request và thời gian chạy.
- CPU, GC, heap allocation khi đọc tập row lớn.
- Số câu CQL/round trips phát sinh từ listener.
- Timeout/retry khi callback làm tăng thời gian xử lý.
- Audit metadata missing rate và lỗi mapping.
- Side effect failures, duplicate messages và reconciliation drift.

Tài liệu Spring Data cho phép tắt lifecycle event publication ở một số Template API; nếu cân nhắc tối ưu, phải kiểm tra phiên bản/cấu hình và hiểu rằng **tắt events không nên vô tình tắt auditing callbacks** mà nghiệp vụ đang cần.

## 32. Những sai lầm phổ biến

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Listener trim tên nhưng DB vẫn có khoảng trắng | `BeforeSaveEvent` sau statement mapping | Dùng `BeforeConvertCallback` |
| Auditing created fields không được điền | Entity UUID cấp trước bị coi là existing | Dùng `@Version` hoặc `Persistable` đúng cách |
| Callback thay entity nhưng statement không đổi | Dùng `BeforeSaveCallback` cho mutation quá muộn | Di chuyển mutation sang before-convert |
| Listener async chạy muộn, không ổn định | Dựa vào `ApplicationEventMulticaster` async | Dùng EntityCallback cho mutation |
| Raw CQL không điền updatedAt | Không đi qua mapping callbacks | Update audit fields tường minh hoặc shared service |
| Event afterSave gửi message trùng | Retry/timeout, thiếu idempotency key | Durable event log, dedup và reconciliation |
| Event không xuất hiện khi query trực tiếp | Driver không phát Spring Data lifecycle events | Đừng coi event là database trigger |
| Audit timestamp thay đổi lạ sau save | isNew/modifyOnCreate/DateTimeProvider config | Chốt auditing policy, test create/update |
| Reactivity mất actor | Dùng ThreadLocal trong reactive chain | `ReactiveAuditorAware` và reactive context |
| Đọc 10k row rất chậm | Listener làm I/O cho mỗi row | Bỏ N+1 và đo callback overhead |
| AfterDelete được gọi nhưng dữ liệu còn trên replica | Tombstone/consistency/compaction | Hiểu Cassandra delete semantics |
| Version conflict xảy ra khi save | Optimistic locking đúng chức năng | Xử lý concurrent edit theo contract |

## 33. Quy trình chọn hook cho một yêu cầu nghiệp vụ

Khi có yêu cầu mới, hỏi lần lượt:

1. **Có cần thay giá trị CQL thực sự được ghi không?** Nếu có, dùng service validation hoặc `BeforeConvertCallback`.
2. **Có cần created/modified metadata không?** Bật auditing, thiết kế isNew và actor provider rõ ràng.
3. **Có cần quan sát save/load/delete không?** Sử dụng listener nhẹ, hiểu thời điểm hook.
4. **Có cần ghi audit history/durable domain event không?** Thiết kế event log/outbox/reconciliation riêng, không xem Spring event là commit log.
5. **Đường ghi có đi qua Spring Data entity mapping không?** Kiểm tra repository/template/raw CQL từng đường.
6. **Ứng dụng sync hay reactive?** Chọn callback và auditor provider phù hợp.
7. **Có concurrency/retry/TTL/tombstone không?** Bảo đảm idempotency và consistency policy.
8. **Có kiểm thử tích hợp đọc lại row không?** Không chỉ assert Java object/listener đã chạy.
9. **Chi phí ra sao?** Đo callback/event overhead ở throughput và dataset lớn.
10. **Ai chịu trách nhiệm?** Ghi policy lifecycle và audit theo từng model/endpoint.

Một lifecycle hook tốt phải giữ **một trách nhiệm nhỏ, xác định và có thể kiểm thử**, không trở thành “nơi mọi service tự móc vào lưu trữ”.

## 34. Bài tập thực hành

### Bài A — Chọn đúng hook

Một API lưu `display_name="  Kho A  "` và yêu cầu DB chỉ chứa `"Kho A"`. Bạn chọn `onBeforeSave(BeforeSaveEvent)` hay `BeforeConvertCallback`? Giải thích thời điểm CQL statement được tạo.

**Gợi ý:** before-convert để mutation đi vào statement; before-save event diễn ra sau mapping.

### Bài B — Auditing cho UUID cấp trước

Một entity có `@PrimaryKey UUID` được tạo sẵn ID trước khi save và dùng `@CreatedDate`. Vì sao Spring Data có thể coi entity là đã tồn tại? Đề xuất dùng `@Version` hoặc `Persistable.isNew` và nêu rủi ro của từng phương án.

### Bài C — Đổi actor theo request

Cấu hình `AuditorAware<String>` lấy actor ID từ Spring Security. Bạn cần kiểm tra gì khi chạy job nền không có user authentication? Khi chuyển sang WebFlux, vì sao provider đồng bộ dựa ThreadLocal có thể sai?

### Bài D — Callback ordering

Có normalize callback `@Order(50)`, auditing callback order 100 và callback khác không khai báo order. Hãy nêu thứ tự mong đợi và lý do cần test khi phụ thuộc vào thứ tự.

### Bài E — Đọc nhiều row

Một query trả 5.000 row, mỗi `onAfterConvert` lại gọi API metadata để enrich entity. Tính số request bổ sung và đề xuất cách chuyển logic khỏi listener.

### Bài F — CqlSession bypass

Một service dùng `repository.save`, service khác dùng `session.execute(UPDATE ...)`. Vì sao audit fields cập nhật khác nhau? Thiết kế service contract để cả hai đường lưu có validation/audit nhất quán.

### Bài G — BeforeSaveCallback

Viết `BeforeSaveCallback<DeviceState>` chỉ inspect `Statement<?>`, rồi mô tả một test chứng minh đổi `displayName` trong callback này không tự cập nhật statement đã sinh.

### Bài H — Durable event delivery

Một listener `onAfterSave` gửi thông báo thiết bị đổi firmware. Phân tích ít nhất ba kịch bản làm thiếu/trùng thông báo và đề xuất durable log, idempotency key, retry/reconciliation.

### Bài I — Optimistic locking

Có hai người sửa cùng một entity chứa `@Version`. Mô tả kỳ vọng của optimistic locking và vì sao tạo version chỉ để auditing có thể làm write latency tăng trên Cassandra.

### Bài J — Kiểm thử tổng hợp

Lập ma trận gồm repository insert/update, template partial update, raw CQL, reactive save, delete và read-many. Chỉ ra callback/event nào dự kiến được kích hoạt và cách đo thực tế trên cluster test.

**Tiêu chí đạt:** người học phân biệt Event với Callback, chọn đúng before-convert cho mutation, hiểu statement đã có ở before-save, cấu hình auditing/isNew, không nhầm Spring event với durable transaction event, và kiểm thử cả đường ghi thấp-level lẫn repository.

## 35. Checklist trước khi đưa lifecycle hook lên production

- [ ] Hook được chọn có đúng nhiệm vụ: mutate, audit hay observe?
- [ ] Nếu mutate dữ liệu, thực hiện trước khi statement được tạo?
- [ ] `BeforeSaveEvent`/`BeforeSaveCallback` không bị dùng để sửa field theo kiểu sẽ tự persist?
- [ ] Callback trả về entity hợp lệ và không tự tạo side effects không idempotent?
- [ ] `@Order`/`Ordered` cùng auditing callback order đã được ghi nhận và test?
- [ ] Entity ID/version/isNew đủ chính xác cho created/modified auditing?
- [ ] `AuditorAware` lấy actor đáng tin; reactive dùng ReactiveAuditorAware?
- [ ] Repository, CassandraTemplate và raw CQL có policy audit nhất quán?
- [ ] Không coi `AfterSaveEvent` là message bền vững hoặc đồng nghĩa mọi replica đã commit?
- [ ] Hệ thống có retry/duplicate handling cho mọi side effect?
- [ ] Có integration test đọc lại database sau save?
- [ ] Callback/event không gây N+1 I/O cho read-many hoặc save-many?
- [ ] Có phân biệt dữ liệu rỗng, timeout, optimistic-lock conflict và schema error?
- [ ] Có metrics latency và lỗi của chính các hook?
- [ ] Migration CQL, keyspace, partition key, consistency và TTL khớp nghiệp vụ?

## Tài liệu tham khảo

- [Spring Data Cassandra — Lifecycle Events và Entity Callbacks](https://docs.spring.io/spring-data/cassandra/reference/cassandra/events.html): lifecycle events, ordering và các Cassandra callbacks được hỗ trợ.
- [Spring Data Cassandra — BeforeConvertCallback Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/mapping/event/BeforeConvertCallback.html): mutation trước khi tạo statement.
- [Spring Data Cassandra — BeforeSaveCallback Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/mapping/event/BeforeSaveCallback.html): statement đã sinh và ý nghĩa callback.
- [Spring Data Cassandra — AbstractCassandraEventListener Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/mapping/event/AbstractCassandraEventListener.html): phương thức nhận events.
- [Spring Data Cassandra — Auditing Configuration](https://docs.spring.io/spring-data/cassandra/reference/cassandra/auditing.html): `@EnableCassandraAuditing` và auditor provider.
- [Spring Data Cassandra — Core Concepts / Is-New Detection](https://docs.spring.io/spring-data/cassandra/reference/repositories/core-concepts.html): `@Version`, `Persistable` và đặc thù Cassandra ID.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/cassandra/reference/data-commons/3.5/auditing.html): `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`.
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): ánh xạ entity, `@Table`, `@PrimaryKey`, `@Column` và `@Version`.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/): partition key, mutation, consistency và TTL.
