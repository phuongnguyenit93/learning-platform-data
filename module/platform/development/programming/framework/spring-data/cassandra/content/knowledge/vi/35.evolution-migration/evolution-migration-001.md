# Thêm, bỏ hoặc đổi ý nghĩa cột và tác động tới mã ánh xạ trong Spring Data Cassandra

Trong ứng dụng sử dụng **Spring Data Cassandra**, một cột trong Apache Cassandra đồng thời tồn tại ở nhiều nơi: định nghĩa bảng CQL, dữ liệu đã được ghi, câu truy vấn từ `CassandraRepository` hoặc `CassandraTemplate`, entity Java, API trả về và logic nghiệp vụ. Khi thêm, bỏ hoặc đổi ý nghĩa cột, sửa một chỗ rồi triển khai ngay có thể khiến các phiên bản ứng dụng không tương thích, đọc sai dữ liệu lịch sử hoặc vô tình ghi đè dữ liệu.

Bài thuộc chương **Tiến hóa và di trú** của module `SPRING_DATA_CASSANDRA`. Trọng tâm là tiến hóa schema có kiểm soát, xử lý dữ liệu cũ và giữ tính tương thích trong lúc triển khai. Cassandra là cơ sở dữ liệu phân tán được thiết kế theo **truy vấn và partition key**; vì vậy những thay đổi tưởng như chỉ liên quan một cột đôi khi phải đánh giá lại bảng, đường đọc/ghi, consistency level, chi phí backfill và hiệu năng trên toàn cluster.

## 1. Phân biệt ba loại thay đổi

| Loại thay đổi | Ví dụ | Vấn đề chính |
| --- | --- | --- |
| **Thêm cột** | Thêm `preferred_locale text` vào hồ sơ khách hàng | Row cũ không tự có giá trị; ứng dụng cũ và mới phải cùng tồn tại |
| **Bỏ cột** | Bỏ `legacy_note` đã ngừng sử dụng | Query hoặc mapping cũ có thể vẫn tham chiếu cột; dữ liệu bị loại khỏi schema |
| **Đổi ý nghĩa cột** | Tên `customer_tier` trước đây là nhóm marketing, nay muốn dùng làm hạng thanh toán | Cùng tên/kiểu dữ liệu nhưng ý nghĩa đã khác; dữ liệu cũ có thể bị diễn giải sai |

**Đổi ý nghĩa** thường nguy hiểm hơn đổi kiểu dữ liệu. Một cột `text` vẫn có thể chứa chuỗi hợp lệ nhưng mang ý nghĩa nghiệp vụ không còn đúng. Ví dụ giá trị `"gold"` theo chương trình marketing không thể tự suy ra là khách hàng đã mua gói thanh toán `"gold"`.

Cần tách bốn lớp hợp đồng:

1. **Hợp đồng lưu trữ:** tên bảng, tên cột, CQL type, partition/clustering key, TTL và các đặc điểm schema.
2. **Hợp đồng ứng dụng:** `@Table`, `@Column`, `@PrimaryKey`, constructor, converter, query và repository.
3. **Hợp đồng dữ liệu:** giá trị nào hợp lệ, `null` có nghĩa gì, nguồn dữ liệu nào có thẩm quyền.
4. **Hợp đồng triển khai:** trong thời gian rollout, phiên bản ứng dụng cũ và mới có thể đọc/ghi ra sao.

Không nên xem `ALTER TABLE` thành công là dấu hiệu migration đã hoàn tất; đó chỉ là một bước của quá trình.

## 2. Tình huống xuyên suốt: hồ sơ khách hàng

Giả sử hệ thống CRM đang lưu hồ sơ theo mã khách hàng trong keyspace `crm`:

~~~sql
CREATE TABLE crm.profiles_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    customer_tier text,
    legacy_note text
);
~~~

Giả sử bảng và keyspace đã được quản lý bằng migration trước đó. Ở ví dụ này:

- `customer_id` là partition key, giúp đọc một khách hàng theo ID.
- `display_name` là tên hiển thị.
- `customer_tier` là **nhóm marketing** như `bronze`, `silver`, `gold`.
- `legacy_note` là ghi chú được nhập từ một hệ thống cũ.

Yêu cầu mới gồm ba phần:

- Bổ sung `preferred_locale` để hiển thị nội dung theo ngôn ngữ ưa thích.
- Ngừng sử dụng `legacy_note` sau khi những màn hình và luồng xử lý liên quan đã chuyển đổi.
- Thêm khái niệm **gói thanh toán đang có hiệu lực**. Nó khác ý nghĩa của `customer_tier`, do đó không được gán lại tên cột cũ cho mục đích mới.

Thiết kế mong muốn là bổ sung hai cột:

~~~sql
ALTER TABLE crm.profiles_by_id
ADD preferred_locale text;

ALTER TABLE crm.profiles_by_id
ADD billing_plan_code text;
~~~

Sau quá trình chuyển đổi, hệ thống có thể loại `legacy_note` và cuối cùng cả `customer_tier` nếu không còn consumer nào sử dụng:

~~~sql
ALTER TABLE crm.profiles_by_id
DROP legacy_note;
~~~

**Không chạy lệnh DROP ngay sau khi ADD**. Các câu CQL trên là những thao tác minh họa; quyết định triển khai cần dựa trên dữ liệu thật, ứng dụng đang chạy và trạng thái schema agreement.

## 3. Thêm cột: schema thay đổi, dữ liệu lịch sử chưa đổi

`ALTER TABLE ... ADD` bổ sung định nghĩa cột cho bảng. Nó **không tự backfill** tất cả partition/row đã tồn tại và không tạo ra một giá trị business default cho lịch sử dữ liệu.

Giả sử sau khi thêm cột, row cũ là:

~~~text
customer_id        = 11111111-1111-1111-1111-111111111111
display_name       = "Lan"
customer_tier      = "gold"
legacy_note        = "Imported in 2024"
preferred_locale   = null (chưa từng ghi)
billing_plan_code  = null (chưa có nguồn dữ liệu xác nhận)
~~~

Có hai câu hỏi khác nhau:

- **Giá trị mặc định khi hiển thị:** nếu `preferred_locale` chưa có, UI tạm hiển thị tiếng Việt (`vi-VN`).
- **Giá trị thực sự được lưu:** chỉ ghi `preferred_locale = 'vi-VN'` sau khi có quy tắc migration/business rõ ràng.

Nếu ứng dụng tự áp dụng fallback `"vi-VN"` trong Java, điều đó **không có nghĩa** Cassandra đã lưu `"vi-VN"`. Chọn default trong code thuận tiện để giữ tương thích, nhưng không thay thế bước backfill khi reporting, indexing hoặc nghiệp vụ sau này yêu cầu giá trị thực tồn tại.

### Quy tắc an toàn khi thêm cột

1. Áp dụng DDL **trước** khi phiên bản ứng dụng mới phát ra CQL tham chiếu cột mới.
2. Kiểm tra schema agreement và xác nhận cột có mặt ở schema cluster theo quy trình triển khai.
3. Cho phép application logic xử lý row cũ thiếu dữ liệu, bao gồm `null`.
4. Xác định có cần backfill hay chỉ cần giá trị cho những bản ghi được tạo mới.
5. Đặt giới hạn phạm vi đọc/ghi cho quá trình backfill để không gây áp lực bất thường lên cluster.

Không nên dựa vào một lần chạy `SELECT *` thành công trên một node để kết luận tất cả node và mọi phiên bản ứng dụng đều đã sẵn sàng.

## 4. Tác động trực tiếp đến entity mapping

Spring Data Cassandra dùng annotation và converter để ánh xạ giữa CQL column và thuộc tính Java. Nếu tên hoặc kiểu cột không khớp, lỗi có thể xuất hiện khi đọc, ghi hoặc chuyển đổi object.

Ví dụ entity **giai đoạn chuyển tiếp**:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("profiles_by_id")
public class CustomerProfile {

    @PrimaryKey("customer_id")
    private UUID customerId;

    @Column("display_name")
    private String displayName;

    // Dữ liệu cũ vẫn được đọc trong giai đoạn migration.
    @Column("customer_tier")
    private String customerTier;

    @Column("legacy_note")
    private String legacyNote;

    // Hai cột mới có thể chưa tồn tại trên các row lịch sử.
    @Column("preferred_locale")
    private String preferredLocale;

    @Column("billing_plan_code")
    private String billingPlanCode;

    public CustomerProfile() {
    }

    public UUID getCustomerId() {
        return customerId;
    }

    public void setCustomerId(UUID customerId) {
        this.customerId = customerId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getCustomerTier() {
        return customerTier;
    }

    public void setCustomerTier(String customerTier) {
        this.customerTier = customerTier;
    }

    public String getLegacyNote() {
        return legacyNote;
    }

    public void setLegacyNote(String legacyNote) {
        this.legacyNote = legacyNote;
    }

    public String getPreferredLocale() {
        return preferredLocale;
    }

    public void setPreferredLocale(String preferredLocale) {
        this.preferredLocale = preferredLocale;
    }

    public String getBillingPlanCode() {
        return billingPlanCode;
    }

    public void setBillingPlanCode(String billingPlanCode) {
        this.billingPlanCode = billingPlanCode;
    }
}
~~~

Repository:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerProfileRepository
        extends CassandraRepository<CustomerProfile, UUID> {
}
~~~

Cấu hình keyspace (Spring Boot 3.x) cần trỏ về `crm`:

~~~yaml
spring:
  cassandra:
    keyspace-name: crm
    schema-action: NONE
~~~

`schema-action: NONE` giúp ví dụ làm rõ rằng việc thay đổi schema do **migration bên ngoài ứng dụng** quản lý. Tên property và hành vi auto-configuration phải được đối chiếu với Spring Boot đang dùng. Không để nhiều application instance tự phát hành DDL không được điều phối khi khởi động.

### Lưu ý mapping và kiểu Java

- Ưu tiên `String`, `Boolean`, `Integer` hoặc kiểu wrapper có thể biểu diễn giá trị chưa có; primitive như `boolean` dễ làm `null` lịch sử biến thành `false` mà nghiệp vụ không phân biệt được.
- Với immutable entity, record hoặc constructor binding, cập nhật constructor, tên tham số, mapping annotation và các converter. Thêm thuộc tính mới có thể khiến constructor hiện tại không phù hợp dữ liệu cũ.
- Nếu dùng enum cho `billing_plan_code`, đừng giả định mọi chuỗi lịch sử đều là enum hợp lệ; xử lý mã chưa nhận diện theo chính sách nghiệp vụ.
- `@Transient` có thể đánh dấu thuộc tính Java không lưu vào Cassandra, nhưng nó **không** đổi schema hoặc xóa cột phía server.
- Cột mới có thể mang `null` ở row cũ; phương thức đọc cần xét cả giá trị chưa có, được xóa và hết TTL nếu bảng dùng TTL.

Quan trọng hơn, trong các phiên bản Spring Data Cassandra, cách tạo câu CQL khi `save(entity)` hoặc `CassandraTemplate.insert/update(...)` gặp thuộc tính `null` có thể phụ thuộc mapping, write options và cách gửi giá trị `null`/`UNSET`. Với Cassandra, ghi **explicit null** có thể tạo tombstone, khác với **UNSET** (không ghi cột đó). Vì vậy cần kiểm tra CQL hoặc driver behavior thực tế; đừng giả định “entity có null thì luôn giữ nguyên dữ liệu cũ”.

## 5. Nguy cơ khi dùng entity đọc thiếu rồi lưu lại

Một vấn đề phổ biến là query chọn ít cột để tối ưu API:

~~~sql
SELECT customer_id, display_name, preferred_locale
FROM crm.profiles_by_id
WHERE customer_id = ?;
~~~

Nếu ánh xạ kết quả này vào **entity đầy đủ** `CustomerProfile`, các trường chưa tải như `customer_tier`, `legacy_note` và `billing_plan_code` có thể là `null` trong object Java.

Một luồng dễ gây sai:

~~~java
// Minh họa nguy cơ, không phải mã nên triển khai.
CustomerProfile partial = readOnlySomeColumns(customerId);
partial.setDisplayName("Tên mới");
repository.save(partial);
~~~

Tùy write semantics, lưu lại entity thiếu trường có thể phát ra CQL xử lý các cột chưa tải, dẫn đến xóa/ghi đè dữ liệu hoặc ít nhất khiến ý định cập nhật không rõ ràng.

Cách an toàn hơn:

- Dùng **read DTO/projection riêng** cho màn hình chỉ đọc.
- Khi sửa một cột, phát **UPDATE rõ cột cần thay đổi** thay vì lưu object thiếu thông tin.
- Giữ quyền ghi tập trung vào service nắm đủ ý nghĩa dữ liệu và trạng thái migration.

Ví dụ CQL cập nhật một cột theo partition key:

~~~sql
UPDATE crm.profiles_by_id
SET display_name = ?
WHERE customer_id = ?;
~~~

Câu CQL trên chỉ yêu cầu cập nhật `display_name`. Khi dùng `CassandraTemplate` hoặc Java Driver, có thể xây dựng equivalent bằng query/update API phù hợp; cần xác minh CQL sinh ra không chứa cột ngoài ý định.

## 6. Đổi ý nghĩa cột: thêm tên mới thay vì tái diễn giải dữ liệu cũ

Giả sử `customer_tier = 'gold'` từng có nghĩa “nhóm khách hàng dành cho chiến dịch khuyến mại”. Bộ phận billing nay có `billing_plan_code = 'gold'` là “gói dịch vụ trả phí”. Dù hai giá trị giống chữ, chúng có thể hoàn toàn khác nhau:

| Trường | Nguồn dữ liệu | Ý nghĩa | Chủ sở hữu |
| --- | --- | --- | --- |
| `customer_tier` | CRM/marketing | Phân nhóm ưu đãi và chăm sóc | Marketing |
| `billing_plan_code` | Hệ thống đăng ký/thu phí | Gói thanh toán đang có hiệu lực | Billing |

Nếu chỉ sửa code để đổi getter `getCustomerTier()` thành `getBillingPlanCode()` nhưng vẫn map vào cột `customer_tier`, dữ liệu sẽ **có vẻ hợp lệ về kiểu** nhưng có thể đưa ra quyết định billing sai. Đây là lỗi hợp đồng nghiệp vụ mà test mapping đơn giản chưa chắc phát hiện.

Giải pháp:

1. Thêm cột **tên đúng ý nghĩa**: `billing_plan_code`.
2. Xác định **nguồn dữ liệu authoritative** cho billing.
3. Chỉ backfill `billing_plan_code` từ nguồn đó, hoặc từ quy tắc chuyển đổi đã được chủ nghiệp vụ xác nhận.
4. Cho phép hai cột cùng tồn tại trong một thời gian, ghi/đọc theo trách nhiệm riêng.
5. Cập nhật API, DTO, event contract, báo cáo và job dùng `customer_tier` để không âm thầm suy ra gói billing.
6. Sau khi tất cả consumers chuyển đổi, mới cân nhắc bỏ cột marketing nếu nó thực sự hết nhu cầu.

**Không backfill bằng câu như** `UPDATE ... SET billing_plan_code = customer_tier`. CQL Cassandra không có cùng mô hình `UPDATE` biểu thức đọc một cột rồi gán trực tiếp sang cột khác như một số hệ SQL quan hệ, và quan trọng hơn, về nghiệp vụ phép chuyển này chưa chắc đúng. Phải có logic chuyển đổi rõ và phương án chạy migration phù hợp.

### Khi nào được dùng fallback từ cột cũ?

Chỉ khi hai cột có **cùng ngữ nghĩa** hoặc có phép ánh xạ một-một đã kiểm chứng. Ví dụ đổi tên hiển thị của mã ngôn ngữ từ `language_code` sang `preferred_locale` với cùng tập giá trị, khi đã đánh giá đầy đủ dữ liệu lịch sử thì có thể cân nhắc đọc cột mới, nếu null thì đọc cột cũ trong giai đoạn chuyển tiếp.

Với trường hợp **marketing tier → billing plan**, fallback này không hợp lệ vì tương quan dữ liệu không phải xác nhận quyền sử dụng gói trả phí. Nên trả trạng thái “chưa xác định”, gọi nguồn dữ liệu billing hoặc áp dụng chính sách nghiệp vụ đã được phê duyệt.

## 7. Expand → migrate → contract: lộ trình triển khai tương thích

Schema evolution nên diễn ra theo các giai đoạn rõ ràng để nhiều phiên bản ứng dụng cùng hoạt động trong khi rolling deployment.

~~~mermaid
flowchart TD
    A["0. Kiểm kê schema, writer, reader và dữ liệu"] --> B["1. EXPAND: ADD cột mới"]
    B --> C["2. Triển khai code tương thích + đo lường"]
    C --> D["3. MIGRATE: backfill / điều chỉnh writes"]
    D --> E{"Đã xác minh độ phủ và tính đúng?"}
    E -->|Chưa| D
    E -->|Rồi| F["4. Chuyển read path sang cột mới"]
    F --> G["5. Ngừng mọi writer/reader cột cũ"]
    G --> H["6. CONTRACT: DROP khi đủ điều kiện"]
~~~

Một lộ trình cho ví dụ:

| Giai đoạn | CQL/schema | Ứng dụng | Điểm kiểm soát |
| --- | --- | --- | --- |
| 0. Baseline | Bảng cũ | Chỉ đọc/ghi trường cũ | Thống kê row lịch sử, phụ thuộc, API, job |
| 1. Expand | `ADD preferred_locale`; `ADD billing_plan_code` | Code cũ vẫn chạy | Schema agreement, quyền CQL |
| 2. App tương thích | Giữ cả cột cũ và mới | Đọc null an toàn; bắt đầu ghi cột mới ở đúng nguồn | Error rate, write semantics |
| 3. Migrate | Schema giữ nguyên | Backfill có kiểm soát, kiểm chứng dữ liệu | Độ phủ, sai lệch, retry/backoff |
| 4. Cutover | Schema giữ nguyên | Consumer mới dùng cột mới; old consumer dần rút | Không còn lệ thuộc cột cũ |
| 5. Contract | `DROP legacy_note` và cột không còn cần | Bỏ mapping, query, job của cột cũ | Không còn query/statement cũ, rollback plan |

Không nhất thiết mọi thay đổi ADD đều phải qua backfill. Với cột tùy chọn chỉ áp dụng cho dữ liệu mới, có thể chấp nhận row cũ không có giá trị. Nhưng **quyết định bỏ qua backfill phải được ghi rõ**, tránh ứng dụng sau này xem `null` như dữ liệu bị lỗi.

### Khi nào dual write?

Dual write phù hợp nếu cần giữ hai cách biểu diễn **tương đương về ý nghĩa** để hỗ trợ cả consumer cũ và mới. Trong giai đoạn này, tránh tình trạng:

- Writer cũ ghi `old_column` nhưng không ghi `new_column`.
- Writer mới cập nhật `new_column` nhưng một consumer vẫn đọc `old_column`.
- Backfill chạy sau lại đè lên một giá trị mới hơn.
- Hai đường ghi dùng TTL hoặc write timestamp khác nhau.

Nếu hai cột có ý nghĩa khác nhau như `customer_tier` và `billing_plan_code`, không nên “dual write cùng một giá trị” chỉ để thuận tiện chuyển đổi. Mỗi cột phải được ghi từ nguồn dữ liệu đúng.

## 8. Backfill Cassandra: cập nhật theo partition key, giới hạn tải

Backfill là bước bổ sung dữ liệu cột mới cho các row đã tồn tại. Trong Cassandra, không nên mặc định một migration SQL duy nhất có thể quét toàn bộ bảng và cập nhật mọi row với chi phí thấp.

Hướng thực hiện thường đáng tin cậy hơn:

1. Xác định nguồn **danh sách khóa** từ nghiệp vụ, sự kiện, export có kiểm soát hoặc công cụ bulk/Spark/DSBulk phù hợp với cluster.
2. Xử lý theo batch nhỏ và **partition key đầy đủ**.
3. Dùng prepared statements, không ghép chuỗi CQL từ dữ liệu.
4. Áp dụng rate limit/concurrency cap theo tốc độ cluster chịu được.
5. Lưu tiến độ ở hệ thống job; cho phép resume sau lỗi và chạy lại an toàn.
6. So sánh dữ liệu đã migrate với nguồn authoritative bằng phép kiểm tra có thể lặp lại.
7. Theo dõi latency, timeout, dropped messages, compaction, tombstone và ảnh hưởng lên request production.

Ví dụ CQL cập nhật locale của một hồ sơ:

~~~sql
UPDATE crm.profiles_by_id
SET preferred_locale = ?
WHERE customer_id = ?;
~~~

Ví dụ logic backfill minh họa với Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

public final class LocaleBackfillWriter {
    private final CqlSession session;
    private final PreparedStatement updateLocale;

    public LocaleBackfillWriter(CqlSession session) {
        this.session = session;
        this.updateLocale = session.prepare("""
            UPDATE crm.profiles_by_id
            SET preferred_locale = ?
            WHERE customer_id = ?
            """);
    }

    public void update(UUID customerId, String locale) {
        // Caller chịu trách nhiệm xác minh nguồn locale và rate limit.
        session.execute(updateLocale.bind(locale, customerId));
    }
}
~~~

Đoạn mã chỉ minh họa phần ghi cho **một khóa**. Job thực tế cần kiểm soát retry, trạng thái tiến độ, lỗi từng bản ghi và điều kiện tránh ghi đè giá trị mới. Không tạo một `CqlSession` mới cho từng row.

### Tránh đọc toàn bộ bảng theo kiểu OLTP

Một câu `SELECT * FROM crm.profiles_by_id LIMIT 100000` không phải chiến lược backfill hoàn chỉnh: `LIMIT` không bảo đảm đi hết tất cả token range, không tạo checkpoint bền vững và có thể gây tải lớn.

Để xử lý toàn bộ dữ liệu, dùng luồng quét phân tán có kiểm soát, chia token range hoặc công cụ bulk phù hợp. Nếu có nguồn khóa nghiệp vụ đầy đủ, đọc/ghi theo các partition key có thể dễ kiểm soát hơn. Việc có dùng token range scan hay export cần dựa vào kích thước bảng và công cụ vận hành thực tế.

### Tính idempotent và tranh chấp với writer đang chạy

Cassandra dùng write timestamp để quyết định giá trị hiển thị cho các cell xung đột. Một backfill đến muộn có thể **ghi đè dữ liệu mới hơn**, tùy timestamp gắn với write; chỉ gọi cùng câu `UPDATE` nhiều lần không chứng minh migration đúng dưới concurrent writes.

Ví dụ rủi ro:

~~~text
09:00  Job đọc locale cũ.
09:01  User đổi locale từ vi-VN sang en-US trên ứng dụng mới.
09:02  Job ghi lại vi-VN theo snapshot cũ.
Kết quả: dữ liệu có nguy cơ quay về vi-VN nếu write của job thắng theo timestamp.
~~~

Giảm nguy cơ bằng cách thiết kế thứ tự rollout, nguồn sự thật, checkpoints và chính sách đối chiếu. Có thể cân nhắc conditional update/LWT trong những trường hợp cụ thể khi cần compare-and-set, nhưng phải đánh giá hiệu năng, consistency và điều kiện hỗ trợ CQL; không bật LWT cho mọi row một cách mặc định.

## 9. Bỏ cột: mã cũ phải ngừng dùng trước khi DROP

Lệnh:

~~~sql
ALTER TABLE crm.profiles_by_id
DROP legacy_note;
~~~

thay đổi schema, khiến tên cột không còn hợp lệ cho các câu CQL mới dựa vào cột đó. Tuy nhiên, nhiều nơi có thể vẫn tham chiếu:

- Field `@Column("legacy_note")` trong entity.
- Query viết tay qua `@Query` hoặc `CassandraTemplate`, hoặc CQL phát từ repository.
- Prepared statement tạo trước khi schema thay đổi.
- Job import/export, ETL, dashboard, báo cáo, consumer của event.
- Bản ứng dụng cũ vẫn chạy trong rolling deployment.

Vì vậy cần làm hai việc **trước** khi DROP:

1. **Dừng cả đường đọc lẫn đường ghi cột cũ** trên mọi phiên bản đang chạy.
2. **Xác minh bằng quan sát thực tế** rằng không còn query/statement hoặc job cần cột đó, thay vì chỉ xóa field từ một class Java.

Sau đó mới phát hành migration `DROP` với kế hoạch khôi phục. Nếu một ứng dụng cũ ghi câu CQL có tên cột đã bị xóa, truy vấn có thể trả lỗi; không thể sửa bằng cách refresh schema đơn thuần.

### DROP không đồng nghĩa dữ liệu vật lý biến mất ngay

Cassandra lưu dữ liệu dưới dạng cấu trúc phân tán (memtable/SSTable) và xử lý xóa thông qua cơ chế tombstone, schema metadata và compaction. Một cột bị DROP có thể còn dữ liệu vật lý trong SSTable cho đến khi vòng đời lưu trữ/compaction xử lý. **Không xem ALTER TABLE DROP là thao tác xóa dữ liệu nhạy cảm tức thời hoặc bảo đảm xóa khỏi backup.** Nếu yêu cầu là tiêu hủy dữ liệu theo chính sách bảo mật, phải có quy trình xóa/retention/backup riêng.

Việc **thêm lại một cột cùng tên** sau khi DROP có các ràng buộc và rủi ro liên quan dữ liệu lịch sử, type và schema version. Không dùng “DROP rồi ADD lại cùng tên” như cách thông thường để đổi ý nghĩa hoặc đổi kiểu cột; chọn tên cột mới và migration rõ ràng.

## 10. Đổi tên hoặc kiểu cột khác gì đổi ý nghĩa?

Với nhiều hệ SQL quan hệ, người học quen với việc `ALTER COLUMN ... TYPE` hoặc `RENAME COLUMN` bất kỳ. Cassandra có các hạn chế theo **phiên bản** và **loại cột**, nên không thể áp dụng máy móc cùng một cách.

| Mong muốn | Hướng xử lý an toàn thường dùng | Lý do |
| --- | --- | --- |
| Đổi tên một cột dữ liệu thông thường | Thêm cột tên mới, chuyển code và dữ liệu, cuối cùng bỏ cột cũ | Khả năng rename trực tiếp bị giới hạn tùy loại cột/phiên bản |
| Đổi `text` sang `int` hoặc type không tương thích | Thêm cột mới có type đúng; chuyển đổi và kiểm tra dữ liệu | Không nên giả định sửa type tại chỗ được hỗ trợ/an toàn |
| Đổi ý nghĩa business của một cột | Thêm cột mang tên/định nghĩa mới và dùng nguồn dữ liệu đúng | Chuỗi cũ có thể hợp lệ về CQL type nhưng sai nghĩa |
| Thay partition key | Tạo **bảng mới** thiết kế theo truy vấn và chuyển đường đọc/ghi | Partition key quyết định phân phối dữ liệu, không thể sửa như một thuộc tính thông thường |
| Thay clustering key/order | Thiết kế bảng mới nếu mô hình query thay đổi | Clustering thuộc primary key và trật tự lưu trữ trong partition |

Một số phiên bản Cassandra cho phép rename trong những tình huống có giới hạn, đặc biệt liên quan các thành phần primary key, nhưng còn ràng buộc về schema và truy vấn. Không dùng các cú pháp rename như công thức chung mà chưa xác nhận phiên bản cluster và sự tương thích của ứng dụng.

### Khi partition key cần đổi

Giả sử yêu cầu mới là đọc nhiều hồ sơ theo `region` trong khi bảng `profiles_by_id` phân vùng theo `customer_id`. Thêm cột `region` không tự làm truy vấn `WHERE region = ?` trở nên hiệu quả. Cần thiết kế một bảng phục vụ access pattern mới (ví dụ `profiles_by_region` với cơ chế bucket hợp lý), cân nhắc cập nhật đồng bộ, backfill và xử lý consistency giữa các read models.

Spring Data Cassandra hỗ trợ ánh xạ nhiều bảng theo nhu cầu đọc, nhưng không tự thay đổi cơ chế phân vùng của Cassandra. Đánh giá partition size, hot partitions, paging, fan-out và chi phí ghi khi tiến hóa mô hình.

## 11. Repository, CassandraTemplate và CQL viết tay bị ảnh hưởng thế nào?

Một migration có thể làm một số đường đọc/ghi hỏng dù các đường khác vẫn chạy. Khi thêm/bỏ cột, kiểm tra đồng thời:

| Thành phần | Điểm cần rà soát | Hệ quả nếu bỏ sót |
| --- | --- | --- |
| Entity `@Table`/`@Column` | Tên và type cột; nullability; converter; constructor | Conversion exception, null không mong muốn, CQL sai cột |
| `@PrimaryKey` và `@PrimaryKeyClass` | Partition/clustering key vẫn tương thích | Không đọc đúng partition, write/update sai khóa |
| `CassandraRepository` | Query method, `@Query`, custom repository | Câu CQL dùng cột đã drop; projection chưa đổi |
| `CassandraTemplate` | Query/update criteria, entity class, select columns | Chọn/ghi cột không còn tồn tại hoặc đọc entity thiếu dữ liệu |
| Java Driver / `CqlSession` | Prepared CQL, bind type, row mapper | Query hoặc mapper dùng vị trí/tên cột cũ |
| DTO và API | Field mới, fallback, enum, backward compatibility | Khách hàng API hiểu sai ý nghĩa hoặc thiếu trường |
| Event/ETL/analytics | Schema của message, export và báo cáo | Pipeline ngoài service vẫn cần dữ liệu cũ |

Ví dụ nếu entity đã đổi sang:

~~~java
@Column("billing_plan_code")
private String billingPlanCode;
~~~

nhưng một query viết tay vẫn là:

~~~sql
SELECT customer_id, customer_tier
FROM crm.profiles_by_id
WHERE customer_id = ?;
~~~

thì giá trị `billingPlanCode` **không xuất hiện** chỉ vì getter đổi tên. CQL phải đọc `billing_plan_code`, mapper phải lấy đúng cột, và business logic phải hiểu chính xác ngữ nghĩa mới.

### Kiểm chứng ánh xạ bằng dữ liệu thật

Unit test mock repository có thể xác nhận service gọi `save()` nhưng không chứng minh schema CQL phù hợp. Integration test với Cassandra thật nên:

1. Tạo schema **trước migration** và ghi mẫu dữ liệu cũ.
2. Chạy `ALTER TABLE ... ADD` vào schema thử nghiệm.
3. Khởi động phiên bản code mới và kiểm chứng đọc row thiếu cột mới không lỗi.
4. Ghi giá trị mới bằng repository/template, đọc lại bằng CQL độc lập.
5. Kiểm chứng migration của dữ liệu cũ và các trường hợp không ánh xạ được.
6. Xác minh không còn query tới cột bị drop trước khi test `DROP`.

`CassandraContainer` với Testcontainers phù hợp cho integration test schema/mapping ở **một node**, nhưng không mô phỏng đầy đủ schema agreement, replication, network partition hoặc rolling deployment nhiều node. Các khía cạnh này cần môi trường cluster phù hợp.

## 12. Mẫu truy cập tương thích trong giai đoạn chuyển tiếp

Xét trường hợp cột mới `preferred_locale` chưa được backfill hết. Đường **đọc** có thể dùng fallback hiển thị:

~~~java
public final class LocaleResolver {

    public String resolveForDisplay(CustomerProfile profile) {
        String stored = profile.getPreferredLocale();
        if (stored == null || stored.isBlank()) {
            return "vi-VN";  // Default UI, chưa phải dữ liệu đã lưu.
        }
        return stored;
    }
}
~~~

Giải pháp này phù hợp nếu quy tắc UI thật sự chấp nhận mặc định `vi-VN`. Không tự sử dụng fallback này trong báo cáo “khách hàng đã chọn ngôn ngữ nào” vì nó sẽ biến giá trị **chưa xác định** thành **đã lựa chọn**.

Với `billing_plan_code`, không dùng giá trị `customer_tier` làm fallback nếu chưa có chứng cứ tương đương. Đường đọc nên tìm nguồn billing có thẩm quyền hoặc biểu diễn trạng thái chưa xác định.

Nếu một endpoint chỉ cần thông tin tóm tắt, có thể dùng câu CQL projection:

~~~sql
SELECT customer_id, display_name, preferred_locale
FROM crm.profiles_by_id
WHERE customer_id = ?;
~~~

Nhớ phân biệt projection/read DTO và entity ghi đầy đủ. Đọc một phần entity rồi gọi `save()` mà không kiểm soát các trường chưa tải là lỗi dễ xuất hiện trong migration.

## 13. Schema agreement, driver metadata và prepared statements

Một lệnh DDL đã trả thành công trên một node không có nghĩa mọi node và mọi client đã lập tức có góc nhìn schema giống nhau.

Trong Cassandra:

- Schema changes cần lan truyền/hội tụ giữa các node; quy trình triển khai cần kiểm tra schema agreement theo công cụ/driver phù hợp.
- Java Driver giữ metadata về keyspace/bảng/cột và có cơ chế cập nhật khi cluster phát sự kiện schema; sự kiện hoặc refresh có thể bị trễ khi mạng lỗi.
- Prepared statement có metadata về tham số/result và được chuẩn bị trên server. Sau thay đổi schema hoặc restart node, có thể xảy ra lỗi prepare/reprepare hoặc query không còn hợp lệ.
- Làm mới schema metadata của client **không tự tạo cột**, **không đổi type** và **không biến CQL cũ thành tương thích**.

Một checklist lúc phát hành DDL:

~~~text
1. Kiểm tra cluster khỏe và quyền quản trị DDL hợp lệ.
2. Chạy migration qua một luồng có kiểm soát.
3. Chờ/xác minh schema agreement và schema thực tế.
4. Deploy/enable đường đọc-ghi dùng cột mới.
5. Theo dõi lỗi CQL và mapping trên từng phiên bản app.
6. Chỉ contract (DROP) khi mọi consumer cũ đã ngừng.
~~~

Không chạy DDL từ mọi pod Spring Boot mỗi lần startup để “đảm bảo bảng đúng”. Điều này có thể tạo tranh chấp, làm mất khả năng kiểm soát phiên bản và che lỗi migration.

## 14. TTL, tombstone và tính nhất quán khi backfill

Các thay đổi cột không tách rời cơ chế lưu trữ Cassandra:

**TTL:** Một cột được ghi với TTL có thể hết hạn trước các cột khác cùng row. Khi backfill hoặc dual write, cần làm rõ giá trị mới có kế thừa TTL hay là dữ liệu tồn tại lâu dài. Việc tự ghi giá trị mới không kèm TTL vào một cột trước đây được quản lý vòng đời có thể làm thay đổi retention.

**Tombstone:** Xóa cột hoặc ghi explicit `null` có thể tạo tombstone. Một migration ồ ạt liên tục tạo xóa có thể tăng tombstone/read amplification. Tránh “xóa sạch rồi ghi lại” trên toàn bảng nếu không cần thiết.

**Write timestamp:** Cassandra sử dụng timestamp trong giải quyết xung đột ghi. Backfill sử dụng thời điểm/timestamp không phù hợp có thể lấn át giá trị được cập nhật mới hơn. Cần xác định chiến lược giữ giá trị mới với concurrent writes, không chỉ tin rằng job có thể chạy lại nhiều lần là an toàn.

**Consistency level:** Chọn consistency phù hợp cho cả đường ứng dụng và backfill, dựa trên replication factor và khả năng replica. Consistency level mạnh hơn không tự ngăn những xung đột do cả hai writer ghi cùng cell với timestamp khác nhau.

**Partition access:** Dù migration chỉ thêm một cột, job quét tất cả partition có thể ảnh hưởng latency của workload production. Tối ưu batching, paging và rate limit, theo dõi hot partitions và compaction.

Để chẩn đoán giá trị hiện có, CQL cho phép dùng các hàm như `WRITETIME(column)` hoặc `TTL(column)` với những loại cột/kiểu truy vấn được hỗ trợ:

~~~sql
SELECT preferred_locale,
       WRITETIME(preferred_locale),
       TTL(preferred_locale)
FROM crm.profiles_by_id
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
~~~

Kết quả phải được diễn giải theo ngữ nghĩa giá trị và loại cột; không suy ra từ `WRITETIME` rằng nguồn dữ liệu business đã đúng. Đây là phép chẩn đoán một partition, không phải cơ chế quét/kiểm định toàn bảng.

## 15. Kiểm thử những gì trước và sau rollout?

Nên kiểm thử cả **logic mapping** lẫn **giao thức chuyển đổi dữ liệu**. Một ma trận mẫu:

| Phiên bản ứng dụng | Phiên bản schema | Kỳ vọng |
| --- | --- | --- |
| Cũ | Cũ | Hành vi hiện tại vẫn đúng (baseline) |
| Cũ | Đã ADD cột mới | Code cũ vẫn đọc/ghi được các cột quen thuộc |
| Mới tương thích | Đã ADD cột mới | Đọc row lịch sử có `null` đúng; ghi cột mới thành công |
| Mới sau cutover | Đã backfill | Tất cả đường đọc chủ chốt dùng dữ liệu đúng ngữ nghĩa |
| Cũ | Đã DROP cột cũ | **Không triển khai tổ hợp này** nếu code còn dùng cột bị xóa |
| Mới sau contract | Đã DROP cột cũ | Không còn entity/query/job tham chiếu cột cũ |

Các ca kiểm thử quan trọng:

- **Row cũ thiếu cột mới:** `preferred_locale` là `null`, fallback hiển thị hoạt động theo chính sách.
- **Giá trị lạ:** `billing_plan_code` chứa một mã không nhận diện; hệ thống xử lý được và log đủ an toàn.
- **Write đồng thời:** backfill và người dùng cùng cập nhật, dữ liệu mới không bị phục hồi thành giá trị cũ.
- **Mixed-version deployment:** app cũ và app mới cùng chạy trên schema đã mở rộng.
- **Projection:** query trả read DTO không vô tình ghi đè các cột chưa tải.
- **Migration gián đoạn:** job chạy lại từ checkpoint không tạo sai dữ liệu.
- **TTL:** dữ liệu được chuyển đổi vẫn có retention đúng.
- **Drop:** quét cấu hình, source query, scheduled job và dashboard để tìm consumer còn dùng cột cũ.

Nếu code mới bắt buộc phụ thuộc cột mới, integration test phải tạo schema từ đúng migration chain. Một test tự tạo bảng phiên bản cuối cùng bằng `CREATE TABLE` có thể bỏ sót lỗi thứ tự DDL hoặc tình huống bảng lịch sử chứa row thiếu dữ liệu.

## 16. Quan sát và rollback khi thay schema

Theo dõi các tín hiệu sau trong suốt rollout:

| Tín hiệu | Vì sao hữu ích |
| --- | --- |
| Tỷ lệ `InvalidQueryException`, lỗi unknown column/type mismatch | Phát hiện application/schema không tương thích |
| Lỗi conversion/mapping trong Spring Data | Phát hiện enum, converter, constructor hoặc null handling sai |
| Tỷ lệ row chưa có cột mới | Theo dõi độ phủ migration; cần đo theo phương pháp sampling/job kiểm định rõ ràng |
| Sai lệch giữa nguồn authoritative và cột mới | Phát hiện backfill sai ngữ nghĩa |
| Thời gian p95/p99 của request Cassandra | Phát hiện tác động tải backfill hoặc cột lớn |
| Write/read timeout, retry, compaction, tombstones | Phát hiện nguy cơ vận hành cluster |
| Phiên bản ứng dụng và migration đang hoạt động | Xác định liệu còn consumer cũ trước contract hay không |

**Rollback cần theo từng giai đoạn.** Khi chỉ mới ADD cột, có thể tắt feature flag hoặc rollback code mới mà vẫn giữ cột mới vô hại trong schema. Sau khi backfill và nhiều writer đã đổi, rollback có thể yêu cầu đồng bộ lại dữ liệu/đọc từ nguồn cũ; cần có kế hoạch trước. Sau khi DROP cột, không thể giả định chạy `ADD` cùng tên sẽ khôi phục giá trị cũ. Backup và log sự kiện chỉ hữu ích nếu có quy trình phục hồi đã được kiểm chứng.

Đặt “điểm dừng” cho mỗi giai đoạn: nếu lỗi mapping tăng, backfill sai tỉ lệ cho phép hoặc p99 tăng vượt mục tiêu, dừng rollout và điều tra. Không chuyển sang DROP chỉ vì migration job báo đã xử lý đủ số record.

## 17. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Thêm cột và nghĩ mọi row có default | Dữ liệu lịch sử trả `null` | Fallback có ý nghĩa hoặc backfill có kiểm soát |
| Dùng primitive Java cho cột tùy chọn | Không phân biệt “chưa có” với giá trị mặc định | Dùng wrapper, xử lý null rõ ràng |
| Đổi ý nghĩa nhưng giữ tên cột | Hợp lệ về kiểu nhưng sai nghiệp vụ | Thêm tên cột mới theo domain |
| DROP khi còn phiên bản cũ | Query/statement cũ lỗi runtime | Loại mọi consumer trước khi DROP |
| Đọc projection rồi `save()` entity | Có thể ghi/xóa trường chưa tải | DTO chỉ đọc, UPDATE đúng cột |
| Đổi type cột trực tiếp theo thói quen RDBMS | CQL không hỗ trợ hoặc dữ liệu không tương thích | Cột/bảng mới và migration |
| Backfill toàn bảng không kiểm soát tải | Timeout, tác động p99, disk/compaction | Batch, paging, throttle, checkpoint |
| Backfill từ snapshot cũ không xử lý concurrent writes | Đè lên giá trị mới | Xác định source of truth và chiến lược ghi |
| Cho rằng metadata refresh sửa được query cũ | Lỗi không biến mất | Sửa CQL/entity và schema thực tế |
| Coi DROP là xóa dữ liệu vật lý ngay | Không đáp ứng yêu cầu bảo mật/retention | Quy trình dữ liệu và backup riêng |

## 18. Bài tập vận dụng

**Bài 1 — Thêm cột nhưng row cũ thiếu giá trị.** Bảng `profiles_by_id` vừa thêm `preferred_locale`. API muốn hiển thị tiếng Việt nếu chưa có lựa chọn, trong khi báo cáo cần phân biệt “chưa từng chọn” với “đã chọn tiếng Việt”. Thiết kế thế nào?

**Gợi ý:** Ở UI, có thể fallback `vi-VN`; báo cáo giữ trạng thái chưa biết của giá trị gốc. Chỉ backfill nếu nghiệp vụ xác nhận được giá trị thực. Không tự ghi fallback vào mọi row chỉ vì hiển thị.

**Bài 2 — Đổi ý nghĩa.** Cột `customer_tier` lưu `gold` cho marketing, nhóm sản phẩm muốn dùng nó để quyết định quyền mở tính năng trả phí. Có thể đổi tên getter rồi sử dụng ngay không?

**Gợi ý:** Không. Tạo `billing_plan_code` theo nguồn billing, thêm quy tắc xác nhận và backfill từ nguồn có thẩm quyền. Dùng giá trị marketing làm billing plan có nguy cơ cấp quyền sai.

**Bài 3 — Lỗi sau DROP.** Tất cả pod mới đã triển khai nhưng một scheduled export job cũ vẫn chạy câu `SELECT legacy_note FROM ...`. Sau khi DROP, job thất bại. Thiếu bước nào?

**Gợi ý:** Kiểm kê toàn bộ consumer ngoài ứng dụng HTTP: job, report, ETL, query viết tay, prepared statements. DROP chỉ an toàn sau khi chúng đều ngừng dùng cột.

**Bài 4 — Backfill ghi đè.** Migration đọc `preferred_locale` lúc 10:00, khách hàng sửa lúc 10:01, migration ghi kết quả cũ lúc 10:02. Làm sao ngăn dữ liệu bị quay về giá trị cũ?

**Gợi ý:** Đánh giá write timestamp, nguồn authoritative, thứ tự rollout và cơ chế cập nhật có điều kiện khi cần. Backfill phải có chiến lược tránh ghi đè dữ liệu mới, không chỉ retry idempotent trên cùng snapshot cũ.

**Bài 5 — Đổi partition key.** Hệ thống bổ sung nhu cầu đọc hồ sơ theo vùng, trong khi primary key hiện tại chỉ là `customer_id`. Có thể thêm cột `region` rồi gọi repository query theo `region` để đảm bảo hiệu năng không?

**Gợi ý:** Không tự động. Cần thiết kế bảng/read model theo access pattern mới hoặc lựa chọn index có đánh giá phù hợp. Partition key của bảng hiện tại không thay đổi bởi việc thêm cột.

## 19. Checklist trước khi kết thúc migration

- [ ] Đã xác định chính xác **ý nghĩa nghiệp vụ** của cột cũ/mới và nguồn dữ liệu có thẩm quyền.
- [ ] Biết mọi reader/writer: entity, repository, template, CQL viết tay, scheduled job, ETL, API, event và report.
- [ ] DDL ADD được thực hiện trước khi code mới phụ thuộc vào cột mới; đã kiểm tra schema agreement.
- [ ] Entity mapping, constructor/converter, wrapper null, enum, projection và query được cập nhật phù hợp.
- [ ] Đã phân biệt default hiển thị với giá trị thực được lưu.
- [ ] Đã kiểm chứng write semantics của `null` so với `UNSET`, tránh ghi đè các cột chưa tải.
- [ ] Backfill có key scope, throughput limit, checkpoint, retry/backoff và cơ chế tránh stale writes.
- [ ] Có kiểm tra ngữ nghĩa giá trị, TTL, consistency, tombstone và tác động tới hiệu năng cluster.
- [ ] Mixed-version rollout được kiểm thử với dữ liệu lịch sử, không chỉ schema mới hoàn toàn.
- [ ] Đã đo độ phủ migration và sai lệch với nguồn authoritative.
- [ ] Mọi consumer cột cũ đã được loại trước khi `DROP`; có kế hoạch rollback phù hợp.
- [ ] Nếu thay đổi partition key hoặc mẫu truy vấn, đã đánh giá bảng mới và cách chuyển dữ liệu.
- [ ] Không xem thao tác DROP là biện pháp xóa vật lý tức thời hoặc phục hồi được bằng ADD.
- [ ] Đã quan sát query errors, mapping errors, latency, timeout và metadata/schema trong rollout.

**Ghi nhớ:** Tiến hóa cột trong Spring Data Cassandra là tiến hóa **hợp đồng dữ liệu** trên một hệ thống phân tán. Hãy mở rộng schema trước, giữ ứng dụng tương thích, di trú dữ liệu theo partition key và nguồn có thẩm quyền, chuyển đường đọc/ghi, rồi mới bỏ cột cũ. Với thay đổi ý nghĩa nghiệp vụ hoặc partition key, hãy ưu tiên mô hình cột/bảng mới có tên và access pattern rõ ràng thay vì sửa tên getter hoặc tái diễn giải dữ liệu cũ.

