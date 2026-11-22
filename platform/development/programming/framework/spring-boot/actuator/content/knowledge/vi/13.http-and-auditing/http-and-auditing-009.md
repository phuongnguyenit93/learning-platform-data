# Tổ chức nơi lưu kiểm toán bền vững và phân biệt với bộ nhớ tạm

## 1. Bắt đầu từ câu hỏi: sau khi ứng dụng dừng, bằng chứng còn ở đâu?

Một sự kiện kiểm toán (audit event) mô tả một hành động cần truy vết: ai thực hiện, vào lúc nào, hành động gì, tác động đến đối tượng nào và kết quả ra sao. Ví dụ: tài khoản `alice` đã phê duyệt hóa đơn `invoice-42` thành công.

Nếu sự kiện chỉ nằm trong một danh sách Java, việc đọc lại ngay sau khi ghi có thể thành công. Nhưng khi JVM kết thúc, danh sách đó biến mất. Một giao diện quản trị vừa hiển thị được sự kiện chưa chứng minh hệ thống có lịch sử kiểm toán lâu dài.

Bài học này tập trung vào nơi lưu và đường đi của sự kiện trong Spring Boot Actuator: phân biệt kho trong bộ nhớ với kho bền vững, hiện thực `AuditEventRepository` bằng JDBC, kiểm chứng qua hai tiến trình Java và nhận diện những điều còn phải thiết kế khi vận hành thực tế.

**Mô hình cần nhớ:** nguồn phát tạo sự kiện; repository tiếp nhận và truy vấn; hệ thống lưu trữ quyết định độ bền; endpoint chỉ cung cấp đường đọc. Bốn vai trò này không thay thế cho nhau.

## 2. Bộ nhớ tạm, bộ đệm và kho bền vững khác nhau ở đâu?

| Tiêu chí | Kho trong bộ nhớ của JVM | Kho kiểm toán trên CSDL bền vững |
| --- | --- | --- |
| Nơi giữ bản ghi | Các đối tượng trong bộ nhớ tiến trình | Dữ liệu đã được CSDL xác nhận lưu theo cấu hình độ bền |
| Khi JVM khởi động lại | Tạo kho mới, mất dữ liệu cũ | Đọc lại được nếu vẫn dùng đúng CSDL và dữ liệu còn được giữ |
| Khi chạy nhiều bản sao ứng dụng | Mỗi bản sao có lịch sử riêng | Có thể dùng chung kho để tra cứu tập trung |
| Khi hết dung lượng | Kho có giới hạn có thể loại bản ghi cũ | Cần kế hoạch dung lượng, phân vùng và thời hạn lưu |
| Chi phí ghi | Thường thấp, không phải chờ I/O lưu trữ | Có I/O, thời gian chờ và khả năng lỗi kết nối |
| Mục đích điển hình | Học thử, quan sát sự kiện gần nhất | Lưu lịch sử phục vụ điều tra và đối soát theo yêu cầu hệ thống |

**Bền vững** nghĩa là dữ liệu được thiết kế để tồn tại qua những loại sự cố đã xác định. Không có nghĩa “không thể mất trong mọi tình huống”. Ví dụ, CSDL trên đĩa của máy ứng dụng có thể sống qua việc khởi động lại JVM nhưng vẫn mất nếu ổ đĩa hỏng và không có bản sao khôi phục.

Đặc tính này phụ thuộc cả vào thời điểm commit, cơ chế ghi của CSDL, bộ nhớ đệm của hệ điều hành và thiết bị lưu trữ. Chỉ gọi một API ghi thành công chưa đủ để suy ra khả năng chịu mất điện của cả hệ thống. Xem [PostgreSQL: Reliability](https://www.postgresql.org/docs/current/wal-reliability.html).

Cần phân biệt thêm:

- **Bộ đệm (buffer):** giữ sự kiện chờ chuyển đi. Hàng đợi trong RAM giúp tách tốc độ xử lý nhưng mất theo tiến trình.
- **Bộ nhớ đệm (cache):** giữ bản sao để đọc nhanh; dữ liệu gốc phải có nơi tồn tại độc lập. Nếu sự kiện chỉ có trong cache thì cache đang gánh vai trò kho duy nhất.
- **Hàng đợi bền vững:** có thể giữ sự kiện chờ ghi vào kho đích nếu đã cấu hình lưu trữ, xác nhận nhận tin và thời hạn giữ phù hợp. Không được suy ra điều này chỉ từ việc hệ thống có một message broker.
- **Kho kiểm toán:** nơi chịu trách nhiệm giữ lịch sử theo thời hạn đã xác định, cung cấp truy vấn và hỗ trợ khôi phục.

Một hệ thống có thể dùng cả bốn thành phần. Phải chỉ rõ bản ghi đang ở đâu và thành phần nào đã xác nhận giữ nó tại từng thời điểm.

## 3. Vai trò của các API trong Spring Boot Actuator

### 3.1. Hợp đồng của AuditEventRepository

Trong Spring Boot 3.3.x, repository có hai thao tác chính:

```java
void add(AuditEvent event);

List<AuditEvent> find(String principal, Instant after, String type);
```

Đây là trích lược chữ ký API, không phải một tệp Java độc lập.

`add` tiếp nhận một sự kiện. `find` tìm theo người thực hiện (`principal`), thời điểm (`after`) và loại sự kiện (`type`). Với từng tham số tìm kiếm, `null` nghĩa là không hạn chế theo tiêu chí đó; `after` có nghĩa là sự kiện xảy ra **sau** mốc truyền vào. Khi hiện thực bằng SQL, điều kiện tương ứng là `occurred_at > :after`.

Giao diện này không quy định backend phải là RAM, JDBC hay một hệ thống lưu trữ khác; cũng không cung cấp giao thức phân trang hoặc mã sự kiện ổn định để tự động chống ghi trùng. Xem [Javadoc AuditEventRepository 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html).

### 3.2. InMemoryAuditEventRepository có ích nhưng có giới hạn

`InMemoryAuditEventRepository` giữ dữ liệu trong tiến trình và giới hạn số sự kiện được giữ. Tăng dung lượng chỉ kéo dài cửa sổ quan sát, không làm dữ liệu sống qua việc khởi động lại JVM.

Spring cung cấp cách hiện thực này để thuận tiện khi phát triển và khuyến nghị xây dựng repository thay thế cho môi trường vận hành. Việc thêm Actuator không đồng nghĩa đã có kho kiểm toán bền vững. Xem [Spring Boot 3.3: Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

### 3.3. Không đồng nhất kiểm toán với lịch sử HTTP hoặc Spring Data auditing

Một HTTP exchange mô tả lần trao đổi yêu cầu/phản hồi, chẳng hạn đường dẫn và mã trạng thái. Một sự kiện kiểm toán mô tả hành động có ý nghĩa cần truy vết. Một yêu cầu HTTP có thể tạo nhiều sự kiện, không tạo sự kiện nào, hoặc thất bại trước khi nghiệp vụ bắt đầu.

`HttpExchangeRepository` và `AuditEventRepository` là hai hợp đồng riêng. Thay repository kiểm toán không tự làm lịch sử HTTP trở nên bền vững. Spring cũng khuyến nghị giới hạn `InMemoryHttpExchangeRepository` ở môi trường phát triển; xem [Recording HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

Các trường như “người sửa cuối cùng” hoặc “thời điểm sửa cuối cùng” trên một thực thể cũng không tự tạo lịch sử mọi hành động. Nếu liên tục ghi đè một hàng hóa đơn, trạng thái cuối cùng không trả lời được đầy đủ ai đã thử làm gì trước đó.

## 4. Tổ chức đường ghi và xác định thời điểm dữ liệu được giữ

Một đường ghi đồng bộ đơn giản có thể được tổ chức như sau:

```text
Hành động cần kiểm toán
    -> tạo dữ liệu sự kiện đã chọn lọc
    -> AuditEventRepository.add(...)
    -> INSERT vào CSDL
    -> commit thành công
    -> tiếp tục theo chính sách của ứng dụng

Đường đọc:
Người có quyền tra cứu
    -> endpoint hoặc dịch vụ truy vấn
    -> AuditEventRepository.find(...)
    -> CSDL
```

Sơ đồ thể hiện ý tưởng thiết kế, không khẳng định mọi lời gọi `add` luôn tự commit. Nếu lời gọi tham gia giao dịch đang mở, câu `INSERT` có thể thành công rồi bị rollback cùng giao dịch đó.

Với đường ghi bất đồng bộ, cần đánh dấu các trạng thái:

```text
Được tạo -> nằm trong RAM -> được hệ thống trung gian giữ bền vững
         -> được kho kiểm toán đích commit
```

Hai trạng thái đầu chưa chứng minh sự kiện đã được lưu bền vững. Khi tiến trình chết sau lúc đưa vào hàng đợi RAM nhưng trước khi ghi CSDL, sự kiện có thể mất. Khi kho đích đã commit nhưng bên gửi chưa nhận xác nhận, thử gửi lại có thể tạo bản ghi trùng.

Nếu thay đổi nghiệp vụ và sự kiện kiểm toán bắt buộc phải đi cùng nhau, một lựa chọn là ghi cả hai trong cùng giao dịch CSDL. Nếu phải chuyển tiếp sang hệ thống khác, có thể dùng **transactional outbox**: ghi trạng thái nghiệp vụ và bản ghi chờ chuyển trong cùng giao dịch, sau đó tiến trình chuyển tiếp đọc và gửi lại khi cần. Bên nhận vẫn cần xử lý việc nhận trùng bằng mã sự kiện ổn định.

Đối với lần đăng nhập bị từ chối hoặc hành động thất bại, yêu cầu có thể là giữ sự kiện dù giao dịch nghiệp vụ rollback. Khi đó phải thiết kế ranh giới giao dịch riêng phù hợp. Không áp dụng máy móc cùng một ranh giới cho mọi loại sự kiện.

Đây là các lựa chọn kiến trúc, không phải bảo đảm tự có của `AuditApplicationEvent` hoặc của tên gọi “audit repository”.

## 5. Thiết kế bản ghi và tổ chức kho

Một cấu trúc ban đầu thường cần các thông tin sau:

| Thông tin | Vai trò |
| --- | --- |
| `event_id` | Nhận diện sự kiện; nếu cần gửi lại thì mã phải ổn định qua các lần thử |
| `occurred_at` | Thời điểm hành động xảy ra |
| `recorded_at` | Thời điểm kho nhận/lưu, hữu ích khi sự kiện đến muộn |
| `principal_name` | Danh tính người hoặc dịch vụ thực hiện, lấy từ ngữ cảnh đáng tin cậy |
| `event_type` | Tên loại sự kiện ổn định, chẳng hạn `INVOICE_APPROVED` |
| `target_id`, `outcome` | Đối tượng bị tác động và kết quả của hành động |
| `correlation_id` | Liên kết với yêu cầu hoặc luồng xử lý để điều tra |
| `schema_version` | Giải thích đúng cấu trúc dữ liệu khi định dạng thay đổi |

Đây là gợi ý mô hình nghiệp vụ; `AuditEvent` của Actuator chỉ có timestamp, principal, type và bản đồ dữ liệu bổ sung. Những trường còn lại cần được quy ước trong dữ liệu hoặc bổ sung ở lớp lưu trữ.

Các quyết định quan trọng:

1. **Thời gian:** biểu diễn thời điểm bằng `Instant`; thống nhất cách lưu UTC và độ chính xác khi chuyển sang SQL. Không dùng giờ địa phương thiếu múi giờ cho việc đối chiếu giữa máy chủ. Đồng hồ nhiều máy vẫn có thể lệch, nên timestamp không tự xác lập thứ tự nhân quả tuyệt đối.
2. **Chỉ mục:** xuất phát từ truy vấn thật. Tra cứu theo người thực hiện và thời gian có thể cần chỉ mục kết hợp; truy vấn theo loại sự kiện hoặc tenant có thể cần chỉ mục khác. Không đánh chỉ mục mọi trường JSON theo thói quen.
3. **Nhiều tenant:** ràng buộc tenant ở tầng truy vấn và phân quyền. `principal` là điều kiện lọc, không phải cơ chế bảo vệ dữ liệu giữa tenant.
4. **Thời hạn lưu:** đặt chính sách theo loại sự kiện và mục đích sử dụng; không mặc định lưu mọi dữ liệu mãi mãi. Lưu trữ dài hạn, xóa theo chính sách và sao lưu là ba việc khác nhau.
5. **Khôi phục:** thử phục hồi bản sao lưu và kiểm tra lại số lượng, thời gian, quyền đọc. Có tệp sao lưu nhưng chưa thử phục hồi thì chưa biết khả năng khôi phục thực tế.
6. **Phân quyền:** tách quyền ghi, tra cứu, quản lý lược đồ và xóa dữ liệu. Ứng dụng ghi sự kiện thường không cần quyền sửa/xóa mọi bản ghi cũ.
7. **Dữ liệu nhạy cảm:** chỉ giữ dữ liệu cần thiết. Không lưu mật khẩu, token, cookie phiên hoặc toàn bộ yêu cầu theo mặc định. Danh tính và địa chỉ liên hệ cũng có thể cần hạn chế truy cập.

**Lưu bền vững và chống sửa đổi là hai thuộc tính khác nhau.** Một hàng CSDL có thể sống qua việc khởi động lại nhưng vẫn bị tài khoản có quyền `UPDATE` thay đổi. Nếu cần phát hiện sửa đổi, phải có thiết kế bổ sung: giới hạn quyền, lưu chỉ bổ sung, dấu vết quản trị độc lập, chữ ký hoặc cơ chế lưu trữ phù hợp với yêu cầu. Một giá trị hash đặt cạnh dữ liệu không đủ nếu cùng một người có thể sửa cả hai.

## 6. Thực hành: hai tiến trình Java, cùng một kho trên tệp

Ví dụ sau chạy độc lập trong một thư mục học thử, dùng Java 17+ và Maven 3.6.3+. Có thể dùng JDK 21. Phiên bản thư viện được cố định theo nhánh Spring Boot 3.3.x của bài; đây không phải đề xuất chọn phiên bản mới cho một hệ thống sản xuất.

Chương trình dùng API kiểm toán thật của Actuator nhưng không khởi động máy chủ HTTP. Mục tiêu là cô lập phép thử lưu trữ: tiến trình thứ nhất ghi, tiến trình thứ hai chỉ đọc. Không cần tạo endpoint nghiệp vụ giả để chứng minh độ bền.

### 6.1. Cấu trúc và phụ thuộc

Tạo thư mục mới `audit-store-lab` với cấu trúc:

```text
audit-store-lab/
├── pom.xml
└── src/main/java/demo/
    ├── JdbcAuditEventRepository.java
    └── AuditStoreDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>audit-store-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
</project>
```

Parent quản lý phiên bản phụ thuộc. `spring-boot-actuator` cung cấp `AuditEvent` và các repository; `spring-jdbc` cung cấp công cụ JDBC; Jackson chuyển dữ liệu đã chọn lọc thành JSON; H2 là driver CSDL.

### 6.2. Hiện thực repository JDBC

Tệp `src/main/java/demo/JdbcAuditEventRepository.java`:

```java
package demo;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public final class JdbcAuditEventRepository implements AuditEventRepository {
    private static final Set<String> ALLOWED_KEYS = Set.of(
            "action", "targetId", "outcome", "correlationId");

    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper json;

    public JdbcAuditEventRepository(
            NamedParameterJdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Override
    public void add(AuditEvent event) {
        Map<String, Object> safeData = new LinkedHashMap<>();
        event.getData().forEach((key, value) -> {
            if (ALLOWED_KEYS.contains(key) && value instanceof String text) {
                if (text.length() > 256) {
                    throw new IllegalArgumentException("Audit field too long: " + key);
                }
                safeData.put(key, text);
            }
        });

        var parameters = new MapSqlParameterSource()
                .addValue("id", UUID.randomUUID().toString())
                .addValue("at", utc(event.getTimestamp()))
                .addValue("principal", event.getPrincipal())
                .addValue("type", event.getType())
                .addValue("data", encode(safeData));

        jdbc.update("""
                INSERT INTO audit_event
                    (event_id, occurred_at, principal_name, event_type, data_json)
                VALUES (:id, :at, :principal, :type, :data)
                """, parameters);
    }

    @Override
    public List<AuditEvent> find(String principal, Instant after, String type) {
        StringBuilder sql = new StringBuilder("""
                SELECT occurred_at, principal_name, event_type, data_json
                FROM audit_event WHERE 1 = 1
                """);
        var parameters = new MapSqlParameterSource();

        if (principal != null) {
            sql.append(" AND principal_name = :principal");
            parameters.addValue("principal", principal);
        }
        if (after != null) {
            sql.append(" AND occurred_at > :after");
            parameters.addValue("after", utc(after));
        }
        if (type != null) {
            sql.append(" AND event_type = :type");
            parameters.addValue("type", type);
        }
        sql.append(" ORDER BY occurred_at, event_id");

        return jdbc.query(sql.toString(), parameters, (rs, rowNumber) ->
                new AuditEvent(
                        rs.getObject("occurred_at", OffsetDateTime.class).toInstant(),
                        rs.getString("principal_name"),
                        rs.getString("event_type"),
                        decode(rs.getString("data_json"))));
    }

    private static OffsetDateTime utc(Instant instant) {
        return OffsetDateTime.ofInstant(instant, ZoneOffset.UTC);
    }

    private String encode(Map<String, Object> data) {
        try {
            return json.writeValueAsString(data);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot encode audit data", ex);
        }
    }

    private Map<String, Object> decode(String text) {
        try {
            return json.readValue(text, new TypeReference<Map<String, Object>>() {});
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot decode stored audit data", ex);
        }
    }
}
```

Những điểm cần đọc kỹ:

- Câu SQL dùng tham số đặt tên cho dữ liệu từ bên ngoài. Phần nối chuỗi chỉ thêm những mệnh đề cố định, không ghép trực tiếp giá trị `principal` hoặc `type` vào SQL.
- Ba bộ lọc độc lập và có thể cùng được bỏ qua bằng `null`. `after` dùng dấu `>`, không phải `>=`.
- Thời gian được ghi bằng `OffsetDateTime` ở UTC và đọc lại thành `Instant`.
- `data` được giới hạn bằng danh sách khóa cho phép và chỉ nhận giá trị chuỗi. Dữ liệu phức tạp tùy ý trong sự kiện bảo mật không được tự động tuần tự hóa thành toàn bộ đồ thị đối tượng.
- Ví dụ từ chối chuỗi được phép dài hơn 256 ký tự. Đây là quy tắc của bài thực hành, không phải giới hạn chung của `AuditEvent`.
- Lỗi mã hóa, lỗi SQL và lỗi đọc JSON được đưa ra ngoài. Không bắt mọi lỗi rồi giả vờ ghi thành công hoặc trả danh sách rỗng.
- `ORDER BY occurred_at, event_id` tạo thứ tự truy vấn xác định cho các bản ghi đã có; UUID ngẫu nhiên không đại diện cho thứ tự hành động thực tế.

Repository này sinh UUID mới mỗi lần `add`. Điều đó đủ cho phép thử từng lần ghi nhưng **chưa chống ghi trùng khi thử lại**. Không được gọi nó là giải pháp “exactly once”. Hệ thống cần thử gửi lại phải nhận diện cùng một sự kiện bằng mã ổn định được tạo trước lần gửi đầu tiên.

Danh sách khóa cho phép cũng chưa bảo đảm nội dung của các giá trị luôn an toàn: một `correlationId` hoặc `targetId` vẫn có thể chứa dữ liệu không nên lưu nếu nguồn phát dùng sai quy ước. Cần kiểm soát cả nơi tạo sự kiện và quyền tra cứu kho.

### 6.3. Chương trình ghi và đọc

Tệp `src/main/java/demo/AuditStoreDemo.java`:

```java
package demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;

public class AuditStoreDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1
                || (!args[0].equals("write") && !args[0].equals("read"))) {
            throw new IllegalArgumentException("Use write or read");
        }

        Files.createDirectories(Path.of("data"));
        var source = new DriverManagerDataSource(
                "jdbc:h2:file:./data/audit;WRITE_DELAY=0", "sa", "");
        var jdbc = new NamedParameterJdbcTemplate(source);

        jdbc.getJdbcTemplate().execute("""
                CREATE TABLE IF NOT EXISTS audit_event (
                    event_id VARCHAR(36) PRIMARY KEY,
                    occurred_at TIMESTAMP(9) WITH TIME ZONE NOT NULL,
                    principal_name VARCHAR(200) NOT NULL,
                    event_type VARCHAR(100) NOT NULL,
                    data_json CLOB NOT NULL
                )
                """);
        jdbc.getJdbcTemplate().execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_principal_time
                ON audit_event (principal_name, occurred_at, event_id)
                """);

        var durable = new JdbcAuditEventRepository(jdbc, new ObjectMapper());
        var memory = new InMemoryAuditEventRepository(2);
        Instant at = Instant.parse("2026-01-01T00:00:00Z");

        if (args[0].equals("write")) {
            var event = new AuditEvent(at, "alice", "INVOICE_APPROVED", Map.of(
                    "action", "approve",
                    "targetId", "invoice-42",
                    "outcome", "success",
                    "correlationId", "request-7",
                    "password", "DO_NOT_STORE"));
            memory.add(event);
            durable.add(event);
        }

        var events = durable.find("alice", null, "INVOICE_APPROVED");
        System.out.println("mode=" + args[0]);
        System.out.println("memory.count=" + memory.find(null, null, null).size());
        System.out.println("durable.count=" + events.size());
        System.out.println("durable.afterExact="
                + durable.find("alice", at, "INVOICE_APPROVED").size());
        System.out.println("durable.afterBefore="
                + durable.find("alice", at.minusSeconds(1), "INVOICE_APPROVED").size());
        System.out.println("durable.wrongPrincipal="
                + durable.find("bob", null, null).size());
        System.out.println("durable.passwordStored="
                + events.stream().anyMatch(e -> e.getData().containsKey("password")));
        if (!events.isEmpty()) {
            System.out.println("durable.target=" + events.get(0).getData().get("targetId"));
        }
    }
}
```

URL `jdbc:h2:file:./data/audit` tạo kho trên tệp trong thư mục làm việc. Không dùng `jdbc:h2:mem:...` cho phép thử sống qua hai JVM. Chỉ đặt `DB_CLOSE_DELAY=-1` cho CSDL trong bộ nhớ cũng không làm nó sống qua việc kết thúc JVM.

`WRITE_DELAY=0` yêu cầu H2 không trì hoãn ghi theo khoảng thời gian cấu hình; phép thử dưới đây vẫn chỉ chứng minh việc mở lại sau khi tiến trình kết thúc bình thường. Không suy rộng kết quả thành chứng nhận chống mất điện hay hỏng ổ đĩa. Xem [H2: chế độ kết nối và CSDL trong bộ nhớ](https://h2database.com/html/features.html).

Bảng dùng `TIMESTAMP(9) WITH TIME ZONE` cho H2. Khi chuyển sang backend khác, cần điều chỉnh DDL, kiểu JSON và độ chính xác thời gian theo backend đó; không sao chép nguyên DDL rồi mặc định mọi CSDL hỗ trợ giống nhau.

`DriverManagerDataSource` mở kết nối trực tiếp để bài thử dễ theo dõi. Trong ứng dụng thực tế, dùng `DataSource` được quản lý với pool kết nối và cấu hình phù hợp. Việc khởi tạo bảng trong `main` chỉ phục vụ phòng thực hành; lược đồ vận hành nên được quản lý bằng migration có phiên bản.

### 6.4. Biên dịch và chạy hai JVM

Đứng tại thư mục `audit-store-lab`. Lần đầu Maven cần mạng để lấy phụ thuộc. Dùng thư mục thực hành mới, chưa có `data/audit.mv.db`, để các số đếm dưới đây khớp chính xác.

Trên PowerShell:

```powershell
mvn -q package dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cp = "target/classes;" + (Get-Content -LiteralPath classpath.txt -Raw).Trim()
java -cp $cp demo.AuditStoreDemo write
java -cp $cp demo.AuditStoreDemo read
```

Trên Linux/macOS, sau cùng lệnh Maven:

```bash
cp="target/classes:$(cat classpath.txt)"
java -cp "$cp" demo.AuditStoreDemo write
java -cp "$cp" demo.AuditStoreDemo read
```

Maven thực hiện biên dịch; mỗi lệnh `java` phía trên tạo một tiến trình mới. Không mở hai tiến trình cùng lúc trên cùng tệp H2 embedded của bài.

Stdout của lần `write` đầu tiên:

```text
mode=write
memory.count=1
durable.count=1
durable.afterExact=0
durable.afterBefore=1
durable.wrongPrincipal=0
durable.passwordStored=false
durable.target=invoice-42
```

Stdout của lần `read` ngay sau đó:

```text
mode=read
memory.count=0
durable.count=1
durable.afterExact=0
durable.afterBefore=1
durable.wrongPrincipal=0
durable.passwordStored=false
durable.target=invoice-42
```

Giải thích từng bằng chứng:

1. `memory.count` giảm từ 1 xuống 0 vì JVM thứ hai tạo một repository RAM mới.
2. `durable.count` vẫn là 1 vì JVM thứ hai mở lại cùng kho trên tệp; nhánh `read` không thêm sự kiện.
3. Mốc `after` bằng chính timestamp của sự kiện cho kết quả 0. Mốc trước đó một giây cho kết quả 1, xác nhận ý nghĩa “sau”.
4. Lọc `bob` trả 0 vì bản ghi thuộc `alice`.
5. Khóa `password` được đưa vào sự kiện bằng một giá trị giả để minh họa, nhưng không được ghi vào kho JDBC do không thuộc danh sách cho phép.
6. `targetId` được phép vẫn được đọc lại, cho thấy dữ liệu bổ sung không bị bỏ hết.

Nếu chạy `write` thêm một lần, số bản ghi JDBC sẽ tăng: ví dụ chưa có cơ chế chống trùng. Nếu chạy `read` từ thư mục làm việc khác, đường dẫn tương đối có thể trỏ tới một CSDL khác. Hai hiện tượng đó phải được giải thích trước khi kết luận có lỗi lưu trữ.

Không xóa tệp dữ liệu trong phép thử đọc lại. Để lặp từ trạng thái rỗng mà không ảnh hưởng dữ liệu cũ, tạo một thư mục thực hành mới.

## 7. Đưa repository vào ứng dụng Spring Boot

Đoạn dưới là **mã tích hợp**, không phải chương trình chạy riêng. Giả sử ứng dụng Spring Boot đã có Actuator, JDBC, Jackson, driver CSDL, `DataSource` và lược đồ được migration tạo sẵn. Đặt lớp cấu hình trong vùng package được quét và tái sử dụng lớp repository ở phần thực hành.

```java
package demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class AuditStorageConfiguration {
    @Bean
    AuditEventRepository auditEventRepository(
            NamedParameterJdbcTemplate jdbc, ObjectMapper objectMapper) {
        return new JdbcAuditEventRepository(jdbc, objectMapper);
    }
}
```

Ứng dụng cần cấu hình rõ backend theo môi trường. Không đăng ký đồng thời repository RAM và repository JDBC rồi để việc chọn bean phụ thuộc tình cờ vào cách tiêm phụ thuộc.

Nguồn phát có thể ghi trực tiếp qua `AuditEventRepository` hoặc phát `AuditApplicationEvent` để hạ tầng audit của Boot tiếp nhận khi được cấu hình phù hợp. Chọn một đường ghi cho cùng một sự kiện; làm cả hai có thể ghi hai lần. Cơ chế application event trong tiến trình tự nó không phải hàng đợi bền vững. Hai cách tích hợp được mô tả trong [Spring Boot: Custom Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html#actuator.auditing.custom).

Cung cấp bean repository và mở quyền đọc qua HTTP là hai quyết định riêng. Trong ứng dụng có web, có thể chọn expose `auditevents` nếu người vận hành thực sự cần, nhưng phải cấu hình xác thực, phân quyền và giới hạn truy cập. Không expose công khai lịch sử kiểm toán chỉ vì đã chuyển dữ liệu sang CSDL.

Endpoint `auditevents` tra cứu dựa trên repository; việc đọc được endpoint không chứng minh dữ liệu tồn tại lâu dài. Bản thân endpoint cũng không thay thế giao diện tìm kiếm lịch sử quy mô lớn có phân trang và chính sách quyền riêng. Xem [Actuator Web API: Audit Events](https://docs.spring.io/spring-boot/api/rest/actuator/auditevents.html).

## 8. Những phần phải bổ sung trước khi vận hành

### 8.1. Xác định hành vi khi ghi thất bại

Không có một lựa chọn phù hợp với mọi sự kiện:

| Lựa chọn | Lợi ích | Đánh đổi cần giải quyết |
| --- | --- | --- |
| Chờ ghi đồng bộ trước khi tiếp tục | Có thể biết lỗi ghi ngay tại luồng xử lý | Tăng độ trễ, phụ thuộc tình trạng kho |
| Ghi trạng thái và audit/outbox cùng giao dịch | Giữ quan hệ nhất quán trong một CSDL | Phải xác định rõ sự kiện thành công/thất bại và ranh giới rollback |
| Gửi qua hệ thống trung gian bền vững | Tách tốc độ tiếp nhận với tốc độ ghi kho đích | Cần xác nhận lưu, giới hạn tồn đọng, thử lại và chống trùng |
| Cho phép tiếp tục dù audit lỗi | Tránh dừng một số hoạt động được phép | Phải chấp nhận khoảng trống dữ liệu và làm nó quan sát được |

Chính sách phải gắn với mức độ quan trọng của hành động. Khi yêu cầu là “không được thực hiện nếu chưa giữ được bằng chứng”, không thể chỉ log lỗi rồi vẫn trả thành công. Nếu chấp nhận tiếp tục, cần ghi rõ phạm vi mất dữ liệu có thể xảy ra.

Khi mất kết nối ngay sau commit, phía gọi có thể không biết đã ghi hay chưa. Thử lại phải dùng cùng mã sự kiện và ràng buộc chống trùng; không sinh mã mới cho mỗi lần gửi.

### 8.2. Giới hạn đọc và dung lượng

`find` trong ví dụ trả toàn bộ bản ghi khớp điều kiện, phù hợp tập dữ liệu nhỏ của phòng thực hành. Không dùng nguyên cách này để mở lịch sử nhiều năm ra một request.

Trong hệ thống lớn, thiết kế dịch vụ truy vấn riêng có khoảng thời gian, kích thước trang và con trỏ ổn định, thường dựa trên cặp thời gian/mã sự kiện. Không âm thầm thêm `LIMIT 100` vào repository rồi khiến người đọc hiểu nhầm rằng đã nhận đầy đủ lịch sử.

Lập kế hoạch tốc độ phát sinh, kích thước sự kiện, chỉ mục, thời hạn lưu, phân vùng và lưu trữ dài hạn. Quy trình xóa theo chính sách cần quyền riêng và dấu vết quản trị phù hợp.

### 8.3. Quan sát chính đường ghi audit

Cần quan sát ít nhất lỗi ghi, thời gian ghi, số lần thử lại, số sự kiện tồn đọng và tuổi sự kiện chưa được chuyển. Nếu có đường loại bỏ sự kiện, số lượng bị loại phải nhìn thấy được; không âm thầm mất dữ liệu khi hàng đợi đầy.

Không dùng từng `event_id` hoặc từng tên người dùng làm nhãn metric có số giá trị tăng không giới hạn. Metric cho biết sức khỏe đường ghi, còn chi tiết của sự kiện nằm trong kho được phân quyền.

Kiểm tra việc nhiều bản sao ứng dụng cùng ghi và đọc một kho, khôi phục từ sao lưu, thay đổi lược đồ JSON và đồng bộ thời gian. “Đã chuyển từ List sang SQL” mới giải quyết một phần bài toán.

## 9. Kiểm chứng theo tình huống, không chỉ nhìn thấy một bản ghi

| Tình huống | Điều cần quan sát |
| --- | --- |
| Ghi rồi đọc trong cùng JVM | Kiểm tra luồng cơ bản, chưa chứng minh khả năng sống qua khởi động lại |
| Ghi, kết thúc JVM, mở JVM mới chỉ đọc | Dữ liệu kho bền vững còn; kho RAM mới trống |
| Vượt dung lượng kho RAM | Các bản ghi cũ có thể bị loại; không được hiểu là lịch sử đầy đủ |
| Tra cứu với `after` đúng timestamp | Sự kiện cùng mốc không được trả về |
| Bỏ từng bộ lọc bằng `null` | Chỉ bỏ điều kiện tương ứng, không vô tình bỏ các điều kiện khác |
| Kho đích không truy cập được | Quan sát đúng chính sách chặn/tiếp tục/thử lại, không báo thành công giả |
| Gửi lại cùng một sự kiện | Với thiết kế chống trùng hoàn chỉnh, không tạo thêm bản ghi nghiệp vụ trùng |
| Dữ liệu chứa trường nhạy cảm | Chỉ thông tin đã được chính sách cho phép xuất hiện trong kho |
| Hai bản sao ứng dụng | Người có quyền có thể tra cứu lịch sử tập trung theo thiết kế |
| Phục hồi sang kho mới | Dữ liệu và quyền đọc phục hồi đúng phạm vi đã công bố |

Phép thử hai JVM ở trên đã minh họa việc mở lại bình thường, bộ lọc thời gian/người thực hiện và chọn lọc dữ liệu. Các tình huống mất điện, nghẽn tải, nhiều nút và phục hồi cần phép thử vận hành riêng; không được xem là đã đạt chỉ từ stdout của bài.

## 10. Lỗi thường gặp và bài tự kiểm tra

Các lỗi dễ mắc:

- Dùng repository trong bộ nhớ cho lịch sử cần lưu lâu, rồi tăng capacity khi phát hiện thiếu sự kiện.
- Chuyển sang SQL nhưng đặt dữ liệu trong ổ tạm của container; thay container làm mất kho.
- Chỉ giữ bản sao trên máy ứng dụng mà không có chính sách sao lưu/khôi phục.
- Nuốt lỗi ghi hoặc trả danh sách rỗng khi CSDL lỗi, khiến “không đọc được” bị hiểu thành “không có sự kiện”.
- Gắn `@Async` rồi kết luận sự kiện đã được lưu bền vững.
- Coi mã HTTP `200` là bằng chứng nghiệp vụ đã thành công, hoặc đồng nhất toàn bộ HTTP exchanges với kiểm toán.
- Nhận `principal` từ một trường yêu cầu do người dùng tự gửi rồi xem đó là danh tính đã xác thực.
- Ghi toàn bộ `event.getData()` mà chưa quyết định những trường nào được phép.
- Ghi audit trong giao dịch sẽ rollback nhưng lại kỳ vọng giữ được dấu vết thất bại.
- Coi kho SQL là tự động chống sửa đổi hoặc coi endpoint Actuator là công cụ tìm kiếm lịch sử hoàn chỉnh.

**Bài tập 1:** Trong ứng dụng ba bản sao, mỗi bản sao dùng `InMemoryAuditEventRepository`. Vì sao truy vấn qua bộ cân bằng tải có lúc thấy sự kiện, có lúc không?

**Gợi ý đáp án:** mỗi JVM giữ một kho riêng. Yêu cầu ghi và yêu cầu đọc có thể tới các bản sao khác nhau. Cần kho chung hoặc kiến trúc thu thập tập trung phù hợp; chỉ cố định phiên truy cập không giải quyết việc mất dữ liệu khi bản sao dừng.

**Bài tập 2:** Trong phòng thực hành, chạy `write` hai lần rồi chạy `read`. Hãy dự đoán số đếm và giải thích.

**Gợi ý đáp án:** nếu bắt đầu từ kho rỗng, JDBC có 2 bản ghi vì mỗi lần `add` sinh UUID mới; lần `read` có `memory.count=0`. `durable.afterBefore` bằng 2, `durable.afterExact` vẫn bằng 0. Dữ liệu sống qua JVM không đồng nghĩa chống ghi trùng.

**Bài tập 3:** Một ứng dụng trả thành công ngay sau khi đưa sự kiện vào `BlockingQueue` trong RAM. Tiến trình bị dừng trước lúc luồng ghi lấy sự kiện ra. Có thể khẳng định lịch sử đầy đủ không?

**Gợi ý đáp án:** không. Sự kiện chưa tới điểm được lưu bền vững. Cần đổi đường xác nhận, dùng nơi trung gian bền vững hoặc chấp nhận và công bố rõ khoảng trống theo chính sách.

Sau bài này, tiêu chí đánh giá một kho kiểm toán không phải “endpoint có trả JSON”, mà là xác định được dữ liệu được giữ ở đâu, khi nào được xác nhận, sống qua những loại sự cố nào, ai có thể đọc/sửa và bằng chứng kiểm thử nào hỗ trợ các kết luận đó.
