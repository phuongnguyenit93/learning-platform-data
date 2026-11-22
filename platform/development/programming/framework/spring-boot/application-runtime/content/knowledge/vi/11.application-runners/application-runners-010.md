# Thiết kế Runner khởi tạo dữ liệu hoặc làm nóng cache có thể chạy lại an toàn trong Spring Boot

## 1. Bài toán: startup không phải công việc chỉ xảy ra một lần

Ứng dụng Spring Boot thường thực hiện một số việc sau khi tạo ApplicationContext nhưng trước khi được coi là đã khởi động xong:

- **Seed dữ liệu nền:** tạo một tài khoản hệ thống, trạng thái mặc định, danh mục mã chuẩn hoặc cấu hình cần thiết nếu chúng chưa tồn tại.
- **Warm up cache:** đọc các bản ghi thường dùng từ nguồn dữ liệu gốc để giảm độ trễ ở những request đầu tiên.
- **Kiểm tra điều kiện bắt buộc:** xác nhận dữ liệu/cấu hình tối thiểu đã sẵn sàng trước khi phục vụ.
- **Chuẩn bị cấu trúc tra cứu:** xây dựng một immutable snapshot, index trong bộ nhớ hoặc bảng ánh xạ được tạo từ dữ liệu hiện hành.

Trong Spring Boot, **ApplicationRunner** và **CommandLineRunner** là các hook phù hợp cho loại công việc sau khi context refresh thành công. Nhưng môi trường production không bảo đảm mỗi ứng dụng, mỗi pod hoặc mỗi job sẽ chỉ khởi động đúng một lần:

- Pod có thể bị restart bởi deployment, autoscaling hoặc lỗi runtime.
- Một instance có thể chết giữa lúc seed; hệ thống orchestration sẽ chạy lại.
- Nhiều replica có thể cùng khởi động và tranh nhau tạo một bản ghi mặc định.
- Người vận hành có thể redeploy cùng một version.
- Test có thể tạo context nhiều lần.
- Một runner có thể được gọi lại thủ công trong bài kiểm thử hoặc một quy trình recovery có kiểm soát.

Vì vậy mục tiêu không phải **"chỉ chạy duy nhất một lần"**, mà là **"chạy bao nhiêu lần cần thiết cũng không làm hỏng trạng thái đúng"**. Tính chất này gọi là **idempotency**.

### Định nghĩa thực tế

Với thao tác khởi tạo F trên trạng thái S, tính idempotent thường được hình dung bằng:

~~~text
F(F(S)) = F(S)
~~~

Nghĩa là chạy thêm lần nữa không làm thay đổi kết quả mong muốn. Trong hệ thống thật, cần định nghĩa "không thay đổi" theo dữ liệu và side effect nào:

- Với seed: không sinh thêm bản ghi trùng; không ghi đè giá trị mà quản trị viên đã sửa.
- Với warm-up: cache cuối cùng chứa một bản tra cứu hợp lệ từ nguồn hiện hành, không cộng dồn/chồng lấn các bản snapshot lỗi.
- Với thao tác ngoài hệ thống: không gửi lại email, không trừ tiền, không tạo tài nguyên bên ngoài lặp lại nếu hệ thống đã hoàn tất thao tác trước đó.

**Idempotent không tự đồng nghĩa "exactly once".** Một bước có thể chạy nhiều lần; thiết kế tốt làm các lần chạy lại tạo cùng trạng thái mong muốn hoặc được hệ thống phát hiện là đã xử lý.

## 2. Runner nằm ở đâu trong lifecycle Spring Boot?

Trong luồng khởi động thành công mặc định:

~~~text
SpringApplication.run(args)
          |
          v
Chuẩn bị Environment và tạo ApplicationContext
          |
          v
Nạp BeanDefinition, refresh Context
          |
          +--> Khởi tạo singleton non-lazy
          +--> @PostConstruct / BeanPostProcessor
          +--> ContextRefreshedEvent
          |
          v
ApplicationStartedEvent
          |
          v
ApplicationRunner / CommandLineRunner
          |
          +--> seed dữ liệu bắt buộc nếu thiếu
          +--> đọc dữ liệu nguồn
          +--> xây snapshot cache
          +--> xác nhận kết quả và trả về
          |
          v
ApplicationReadyEvent
          |
          v
ReadinessState.ACCEPTING_TRAFFIC
          |
          v
SpringApplication.run trả về
~~~

**ApplicationRunner** có phương thức **run(ApplicationArguments args)**; **CommandLineRunner** có **run(String... args)**. Cả hai được Spring Boot phát hiện dưới dạng bean và thực thi **sau khi ApplicationContext đã refresh**, **trước ApplicationReadyEvent**. Chúng phù hợp cho công việc startup sử dụng các Spring beans đã được tạo như **JdbcTemplate**, repository, transaction service hoặc cache manager.

### Điều mà Runner bảo đảm — và không bảo đảm

| Điều kiện | Ý nghĩa |
| --- | --- |
| Runner bắt đầu | Context đã refresh thành công |
| Runner hoàn thành bình thường | Công việc **đồng bộ** bên trong phương thức run đã trả về |
| Tất cả Runner hoàn thành | Spring Boot có thể tiếp tục phát ApplicationReadyEvent |
| Runner ném exception không được xử lý | Boot coi startup thất bại, không phát ApplicationReadyEvent bình thường |
| Runner chỉ submit một Future rồi trả về | **Không bảo đảm** tác vụ nền đã xong khi ứng dụng ready |
| Web server đã bind port | Không bảo đảm client truy cập trực tiếp sẽ đợi runner hoàn tất |
| ApplicationReadyEvent đã phát | Không bảo đảm các dependency ngoài sẽ khỏe mãi sau này |

Trong môi trường Kubernetes, nên dùng **readiness probe** đúng nghĩa để quản lý nhận traffic. Mở cổng TCP không phải bằng chứng dữ liệu/caches bắt buộc đã sẵn sàng.

## 3. Chia việc thành hai nhóm với hợp đồng rõ ràng

### 3.1. Seed dữ liệu nền: bảo vệ nguồn dữ liệu gốc

Một lần seed an toàn cần trả lời:

1. **Điều kiện có tồn tại:** bản ghi được nhận diện bằng mã ổn định nào (natural key/unique key)?
2. **Bất biến dữ liệu:** có được ghi đè bản ghi đã được sửa không?
3. **Tính nguyên tử:** việc kiểm tra và ghi dữ liệu có an toàn khi nhiều instance cùng chạy không?
4. **Giao dịch:** nếu seed nhiều bảng liên quan, trạng thái nửa chừng có chấp nhận được không?
5. **Khả năng chạy lại:** sau crash giữa các bước, lần chạy sau có tiếp tục hoàn tất mà không sinh dữ liệu trùng không?
6. **Versioning:** seed dữ liệu mới theo phiên bản, có cần migration thay vì thao tác khởi động lặp lại không?

Ví dụ: một danh mục có mã **DEFAULT**. Mục tiêu an toàn là **"nếu chưa có DEFAULT thì tạo; nếu đã có thì giữ nguyên"**. Nếu người vận hành đổi tên hiển thị của DEFAULT, lần restart không được tự động đưa về tên cũ trừ khi đó là quy tắc nghiệp vụ được nêu rõ.

### 3.2. Warm-up cache: xây một trạng thái dẫn xuất có thể thay thế

Cache thường là **derived data**, không phải source of truth. Warm-up đúng nghĩa là:

1. Đọc từ nguồn chính đã nhất quán và đủ tin cậy.
2. Xây một snapshot mới **ngoài vùng dữ liệu đang được client đọc**.
3. Kiểm tra các điều kiện hợp lệ: dữ liệu có đủ không, kích thước có phù hợp, key có unique/nonnull không.
4. **Publish/thay thế nguyên tử** snapshot mới hoặc cập nhật cache bằng chiến lược có kiểm soát.
5. Nếu rebuild lỗi, **không công bố snapshot nửa chừng**; quyết định giữ snapshot cũ, trả lỗi startup hoặc đánh dấu readiness theo mức độ bắt buộc.

Với cache local, snapshot có thể bị mất mỗi lần restart; điều này bình thường. Tính idempotency ở đây không yêu cầu bộ nhớ sống qua restart, mà yêu cầu **sau mỗi lần warm-up thành công, cache phản ánh dữ liệu đúng**.

## 4. Các anti-pattern cần tránh

| Cách làm dễ mắc | Vì sao không an toàn | Cách tốt hơn |
| --- | --- | --- |
| Mỗi startup gọi INSERT vô điều kiện | Tạo duplicate hoặc lỗi unique constraint | Dùng business key unique, insert-if-absent/DB upsert phù hợp |
| SELECT kiểm tra chưa có, rồi INSERT | Hai replica có thể cùng thấy chưa có | Để database bảo vệ bằng unique key và xử lý conflict |
| "Seed" bằng UPDATE toàn bộ giá trị mỗi lần | Ghi đè thay đổi hợp lệ của người vận hành | Định nghĩa rõ dữ liệu bất biến hay default-only |
| Bỏ qua mọi DataAccessException | Che lỗi mất kết nối, schema sai, permission | Chỉ xử lý lỗi trùng key dự kiến; lỗi khác phải được báo |
| Mỗi lần warm-up chỉ append vào list/map | Cache có thể tích lũy entries cũ hoặc dữ liệu sai | Xây snapshot mới rồi thay thế có kiểm soát |
| Cache.clear() rồi put dần trước readers | Readers nhìn thấy cache trống hoặc nửa chừng | Atomic swap hoặc cơ chế refresh cache hỗ trợ consistency |
| Dùng @PostConstruct để gọi DB dài | Context còn trong quá trình khởi tạo bean; khó kiểm soát readiness | Dùng runner/service sau refresh khi phù hợp |
| Runner submit async task rồi return | Boot có thể phát ready trước khi cache xong | Await bounded task hoặc quản lý readiness riêng |
| Dựa vào JVM synchronized để chống seed trùng | Khóa chỉ tác dụng trong một instance | Unique constraint/transaction hoặc distributed coordination |
| Mong "execute once" qua in-memory boolean | Restart hoặc replica khác không biết trạng thái | Durable marker/version/unique key ở nguồn tin cậy |

## 5. Thiết kế seed idempotent ở tầng database

### 5.1. Đặt unique constraint thật sự

Giả sử bảng danh mục:

~~~sql
CREATE TABLE catalog (
    code VARCHAR(40) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
~~~

**code** là khóa nghiệp vụ ổn định. Database có thể bảo đảm rằng ngay cả khi **hai replica** cùng muốn tạo **code=DEFAULT**, chỉ một bản ghi có thể tồn tại.

### 5.2. Tránh check-then-insert race

Đoạn logic sau **không đủ an toàn** khi chạy song song:

~~~java
if (!repository.existsById("DEFAULT")) {
    repository.save(new CatalogItem("DEFAULT", "Mặc định"));
}
~~~

Đây là **mảnh minh họa** của JPA, không phải code chạy độc lập. Hai tiến trình A và B có thể cùng nhận **exists=false**, rồi cùng INSERT. Nếu có primary key, một tiến trình sẽ nhận lỗi constraint; nếu không có constraint, dữ liệu sẽ bị nhân đôi.

Cách an toàn hơn là **đưa bất biến vào database**:

- PostgreSQL: **INSERT ... ON CONFLICT (code) DO NOTHING** cho default-only seed.
- Một số database có **MERGE** hoặc cú pháp insert-if-absent khác; phải kiểm tra transaction/isolation và semantics của từng hệ quản trị.
- Nếu không có thao tác no-op-on-conflict thống nhất, có thể thử **INSERT** rồi chỉ xử lý **DuplicateKeyException** đúng constraint được mong đợi.
- Với seed gồm nhiều bảng, cần xác định transaction boundary và thứ tự ràng buộc.

**Tránh vô thức dùng ON CONFLICT DO UPDATE** nếu yêu cầu là chỉ tạo mặc định một lần: UPDATE có thể ghi đè giá trị do người dùng thay đổi. Quy tắc kinh doanh phải quyết định liệu seed là **immutable reference data**, **default-only**, hay **versioned correction**.

### 5.3. Chỉ bỏ qua lỗi đã được chấp nhận

~~~java
try {
    jdbcTemplate.update(
            "INSERT INTO catalog(code, display_name) VALUES (?, ?)",
            "DEFAULT", "Mặc định");
} catch (DuplicateKeyException alreadyExists) {
    // Một bản ghi cùng code đã tồn tại: không ghi đè.
}
~~~

Đoạn trên là **mảnh code minh họa** cần import JdbcTemplate/DuplicateKeyException và bảng có unique key. Với dữ liệu không hợp lệ, mất kết nối, schema thiếu hoặc permission sai, chương trình **không nên** bắt **Exception** rồi lặng lẽ tiếp tục. Khi seed là điều kiện bắt buộc, các lỗi thực tế đó phải làm startup thất bại và được ghi log phù hợp.

Tuy nhiên, ngay cả với DuplicateKeyException, hãy bảo đảm constraint bị vi phạm thật sự là key mà logic đang cho phép tồn tại. Nếu bảng có nhiều unique constraints và thao tác INSERT có thể vi phạm constraint khác, nên dùng SQL xử lý conflict **đích danh khóa nghiệp vụ** hoặc phân loại lỗi chính xác hơn.

## 6. Ví dụ hoàn chỉnh Java 17+: seed danh mục và warm-up cache có thể chạy lại

Ví dụ sử dụng **Spring Boot 3.5.x**, Java 17+, Maven, **Spring JDBC** và **H2 dạng file**. Lý do dùng H2 file là dữ liệu **tồn tại qua nhiều lần khởi động ứng dụng**; nếu chỉ dùng H2 in-memory, database mới được tạo mỗi lần process chạy nên không kiểm chứng được tình huống restart giữ dữ liệu.

Chương trình sẽ:

1. Tạo bảng bằng script SQL có thể chạy lại ở H2.
2. Trong **ApplicationRunner**, thử tạo bản ghi danh mục DEFAULT bằng INSERT.
3. Nếu DEFAULT đã tồn tại, giữ nguyên giá trị.
4. Đọc toàn bộ bảng thành một map tạm.
5. Thay thế cache local bằng **immutable snapshot** qua một phép gán tham chiếu **volatile**.
6. **Gọi cùng logic hai lượt** trong một lần chạy và in số bản ghi/cache.
7. Khi chạy lại chương trình với cùng file H2, không tạo thêm bản ghi trùng.

### 6.1. Tạo dự án Maven

Dùng **Spring Initializr**, chọn **Java 17+**, **Spring Boot 3.5.x**, group **com.example**, artifact **repeatable-startup**, package **com.example.demo**. Chọn:

- **JDBC API / Spring JDBC** (tương ứng Spring Boot Starter JDBC).
- **H2 Database**.

Trong POM do Initializr tạo, các dependencies cốt lõi tương đương:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đây **chỉ là phần dependencies**, không phải một file pom.xml độc lập. Hãy để parent/BOM của Spring Boot quản lý phiên bản tương thích. Không cần Spring Web, vì bài tập sử dụng **non-web application**.

Cấu trúc file:

~~~text
repeatable-startup/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── src/main/
    ├── java/com/example/demo/RepeatableStartupApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 6.2. Cấu hình datasource và SQL init

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=repeatable-startup
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:file:./repeatable-seed-db;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

- **jdbc:h2:file:./repeatable-seed-db** tạo/lưu database H2 trên filesystem tương ứng working directory; các file database vẫn tồn tại khi process kết thúc bình thường.
- **DB_CLOSE_ON_EXIT=FALSE** để H2 không dựa vào JVM shutdown hook riêng cho đóng database; pool datasource do Spring quản lý vẫn cần đóng bình thường.
- **spring.sql.init.mode=always** yêu cầu Boot chạy SQL initialization scripts ngay cả với datasource file-based, thay vì chỉ dựa trên phát hiện embedded database.
- **spring.main.web-application-type=none** giúp project chạy runner rồi kết thúc, không cần HTTP server.

Trong dự án thật, không lưu password production trong source code. H2 ở đây chỉ là môi trường học; production thường dùng PostgreSQL/MySQL và migration tool phù hợp.

File **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS catalog (
    code VARCHAR(40) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
~~~

**CREATE TABLE IF NOT EXISTS** là cú pháp H2 được dùng trong ví dụ, không phải lời hứa rằng cùng script có thể chạy trên mọi database. Khi ứng dụng khởi động lần thứ hai, script này không tạo lại hay xóa dữ liệu đã có.

Lưu ý không bỏ **DROP TABLE** hoặc **TRUNCATE** vào startup schema nếu mục đích là giữ seed qua restart.

### 6.3. Chương trình Java đầy đủ

Tạo file **src/main/java/com/example/demo/RepeatableStartupApplication.java**:

~~~java
package com.example.demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RepeatableStartupApplication {

    public static void main(String[] args) {
        SpringApplication.run(RepeatableStartupApplication.class, args);
    }

    @Bean
    LookupCache lookupCache() {
        return new LookupCache();
    }

    @Bean
    ApplicationRunner seedAndWarmUp(
            JdbcTemplate jdbcTemplate,
            LookupCache cache) {

        return args -> {
            // Hai lượt trong cùng một startup để kiểm chứng chạy lại.
            for (int pass = 1; pass <= 2; pass++) {
                ensureDefaultRow(jdbcTemplate);
                warmUpCache(jdbcTemplate, cache);

                Long rows = jdbcTemplate.queryForObject(
                        "SELECT COUNT(*) FROM catalog", Long.class);

                System.out.println("pass=" + pass
                        + ", rows=" + rows
                        + ", cache=" + cache.size()
                        + ", default="
                        + cache.find("DEFAULT").orElse("MISSING"));
            }
        };
    }

    private static void ensureDefaultRow(JdbcTemplate jdbcTemplate) {
        try {
            jdbcTemplate.update(
                    "INSERT INTO catalog(code, display_name) "
                            + "VALUES (?, ?)",
                    "DEFAULT", "Mặc định");
        } catch (DuplicateKeyException alreadyExists) {
            // PRIMARY KEY code đã tồn tại; giữ nguyên bản ghi.
        }
    }

    private static void warmUpCache(
            JdbcTemplate jdbcTemplate, LookupCache cache) {

        Map<String, String> next = new HashMap<>();

        jdbcTemplate.query(
                "SELECT code, display_name FROM catalog",
                rs -> {
                    next.put(
                            rs.getString("code"),
                            rs.getString("display_name"));
                });

        // Chỉ công bố bản snapshot sau khi đọc xong thành công.
        cache.replace(next);
    }

    static final class LookupCache {
        private volatile Map<String, String> snapshot = Map.of();

        void replace(Map<String, String> data) {
            snapshot = Map.copyOf(data);
        }

        int size() {
            return snapshot.size();
        }

        Optional<String> find(String code) {
            return Optional.ofNullable(snapshot.get(code));
        }
    }
}
~~~

**Đây là file Java hoàn chỉnh**, không phải pseudocode, khi nằm trong project có dependencies như trên. Maven sẽ cung cấp Spring JDBC/H2 trên classpath; không thể chỉ chạy **javac RepeatableStartupApplication.java** mà không truyền các thư viện Spring.

### 6.4. Giải thích các cơ chế then chốt

**ApplicationRunner** do Spring Boot gọi sau refresh. **JdbcTemplate** và **LookupCache** đã là các bean có thể inject vào runner.

**ensureDefaultRow(...)** thử INSERT theo khóa chính DEFAULT:

- Nếu chưa có, thêm một bản ghi.
- Nếu đã có, H2 trả lỗi trùng khóa; Spring JDBC dịch thành **DuplicateKeyException**. Chương trình coi riêng trường hợp này là "đã seed".
- Mọi lỗi truy cập dữ liệu khác không được bắt ở đây; chúng làm runner fail và tránh phát ready bình thường.
- Không sử dụng UPDATE nên không ghi đè display_name mà người dùng đã sửa.

**warmUpCache(...)** tạo **Map next** mới thay vì sửa map mà người đọc đang sử dụng. Khi JDBC query thành công hoàn toàn, **cache.replace(next)** gọi **Map.copyOf** rồi gán tham chiếu volatile. Mỗi reader sẽ thấy **snapshot cũ hoặc snapshot mới hoàn chỉnh**, không thấy map bị clear rồi nạp dở.

**volatile** cung cấp tính nhìn thấy của tham chiếu snapshot giữa các threads. Nó không làm thao tác **đọc dữ liệu từ DB + publish cache** trở thành transaction xuyên hai hệ thống; nếu DB thay đổi sau query, cache vẫn có thể nhanh chóng trở nên cũ. Để cập nhật theo thời gian thực, cần thêm TTL, invalidation hoặc refresh strategy.

Vì ví dụ chỉ có một runner làm cả hai bước theo thứ tự, **seed phải thành công rồi mới warm-up**. Không phụ thuộc vào thứ tự tự nhiên của hai runner riêng biệt.

### 6.5. Chạy và kiểm tra lần đầu

Tại thư mục gốc dự án:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt:
# .\mvnw.cmd spring-boot:run
~~~

Nếu database mới và không có cấu hình khác thay đổi, hai dòng do chương trình chủ động in:

~~~text
pass=1, rows=1, cache=1, default=Mặc định
pass=2, rows=1, cache=1, default=Mặc định
~~~

Đây là các dòng từ runner, **không phải toàn bộ stdout** (Maven/Spring Boot có log khác). Hai lượt gọi liên tiếp không thêm bản ghi thứ hai.

### 6.6. Chạy lại sau khi restart

Dừng process nếu đang chạy, rồi chạy lại đúng lệnh từ **cùng working directory**. H2 vẫn giữ file database. **CREATE TABLE IF NOT EXISTS** không xóa bảng, còn INSERT trùng key được xử lý.

Với database vẫn chỉ có bản ghi DEFAULT như lần trước, kết quả runner tiếp tục là:

~~~text
pass=1, rows=1, cache=1, default=Mặc định
pass=2, rows=1, cache=1, default=Mặc định
~~~

Đây là thử nghiệm **chạy lại cùng startup logic**, không phải mô phỏng trạng thái "mỗi lần là database rỗng". Nếu đã thêm các dòng dữ liệu khác hoặc sửa tên DEFAULT, số lượng và tên trong output sẽ phản ánh dữ liệu hiện tại — đó là hành vi đúng, không phải lỗi.

### 6.7. Chứng minh seed không ghi đè chỉnh sửa hiện có

Dùng một H2 SQL client hoặc H2 Console kết nối tới database file khi ứng dụng đã đóng, đổi display_name của DEFAULT thành **"Tên do quản trị viên sửa"**, rồi chạy lại. Runner vẫn gọi INSERT, nhưng vì khóa đã có nên không overwrite. Cache sẽ được nạp từ bảng và lấy tên mới.

Ngược lại, nếu seed sử dụng **MERGE** theo cách mặc định là "matched thì UPDATE", tên này có thể bị ghi đè về **"Mặc định"** khi restart. Đây là ví dụ tại sao phải làm rõ seed là **default-only** hay **synchronization/update**.

### 6.8. Giới hạn của ví dụ

- H2 file được dùng để học và chạy trên một máy. **Không dùng chung file H2 như một database nhiều pod**.
- **schema.sql** phù hợp cho demo; production thường dùng migration có version và quy trình release kiểm soát.
- Bảng chỉ có một primary key và một kiểu INSERT dự kiến nên catch DuplicateKeyException là có chủ đích. Nếu schema phức tạp hơn, phải kiểm tra đúng conflict được cho phép.
- Cache là **per-process local snapshot**, không đồng bộ tự động giữa các replicas. Nếu cần cache phân tán, phải bổ sung giao thức invalidation/versioning.
- Runner chạy hai vòng để kiểm chứng idempotency. Production thường chỉ cần thực hiện một lần tại mỗi startup; có thể chạy lại theo quy trình retry có kiểm soát.

## 7. Khi seed gồm nhiều bảng: giao dịch và điểm khôi phục

Giả sử seed cần tạo **role** và **role_permission**. Nếu INSERT role thành công rồi lỗi trước khi INSERT permission, lần chạy sau phải biết còn thiếu gì. Các lựa chọn:

- **Transaction cho một đơn vị nghiệp vụ:** dùng **TransactionTemplate** hoặc phương thức service **@Transactional** qua proxy Spring để mọi thay đổi liên quan commit cùng nhau.
- **Mỗi bước idempotent riêng:** role được insert-if-absent, permission association có unique key ghép (role_id, permission_code), chạy lại tiếp tục bù phần thiếu.
- **Version marker bền vững:** ghi marker version **sau khi** toàn bộ bước cần thiết thành công; không đánh dấu hoàn tất trước khi dữ liệu thật đã commit.
- **Migration tool:** với schema/reference data gắn chặt version release, xem xét Flyway/Liquibase thay vì đặt mọi biến đổi vào runner.

Ví dụ cấu trúc ranh giới transaction (mảnh code minh họa, không phải file độc lập):

~~~java
transactionTemplate.executeWithoutResult(status -> {
    ensureRoleExists();
    ensureRolePermissionExists();
    markSeedVersionComplete();
});
~~~

Các hàm **ensure...** phải được implement bằng thao tác idempotent và các unique constraints phù hợp; transactionTemplate cần được cấu hình từ PlatformTransactionManager đúng datasource.

**Quan trọng:** đặt **@Transactional** trực tiếp trên method khởi tạo hoặc gọi một method **@Transactional** qua **this.someMethod()** có thể không qua Spring AOP proxy; không mặc định nó tạo transaction. Tách logic vào một service Spring được inject và gọi qua proxy, hoặc dùng **TransactionTemplate** khi cần ranh giới rõ.

Nếu job có side effect ngoài DB (message, API, email) thì một transaction database đơn lẻ **không bảo đảm atomicity** cho cả bên ngoài. Cân nhắc outbox, idempotency keys, durable job state và retry policy.

## 8. Nhiều replica đồng thời: idempotency khác với mutual exclusion

Giả sử hai pod A và B cùng startup và cùng gọi seed:

~~~text
Pod A: INSERT DEFAULT ----+
                          +----> DB với PRIMARY KEY(code)
Pod B: INSERT DEFAULT ----+
                                  |
                         Một lần INSERT thành công
                         Lần còn lại gặp duplicate key
                                  |
                         Cả hai tiếp tục đọc DEFAULT
                                  |
                         Mỗi pod warm-up cache riêng
~~~

**Unique constraint ở DB** xử lý bất biến **"một bản ghi cho một code"**. Nó mạnh hơn synchronized, AtomicBoolean hoặc lock trong một JVM vì tất cả các pod phải đi qua cùng nguồn dữ liệu.

Không phải mọi bài toán đều có thể giải bằng unique key. Khi cần một tác vụ gây side effect tốn kém thực sự chỉ được một worker thực thi tại một thời điểm, có thể cần:

- Durable job record với unique job key + status.
- Transactional claim (SELECT FOR UPDATE hoặc cơ chế claim phù hợp hệ DB).
- Distributed lock/lease, cùng **fencing token** nếu tài nguyên bên ngoài cần chống stale owner.
- Idempotency key được phía API đích hỗ trợ.
- Retry + recovery sau crash/timeout.

**Khóa phân tán không thay thế idempotency.** Lease có thể hết hạn khi worker cũ còn đang chạy; crash có thể xảy ra ngay sau side effect nhưng trước khi lưu trạng thái. Thiết kế an toàn cần cân nhắc cả claim, side effect và cơ chế khôi phục.

Với một cache local per replica, việc nhiều pod cùng đọc DB và nạp cache thường chấp nhận được, miễn DB chịu tải. Nếu số lượng pod lớn hoặc warm-up đọc rất nhiều bản ghi, nên thêm giới hạn tốc độ, batch/pagination, shared cache hoặc chiến lược startup staggered để tránh **thundering herd**.

## 9. Warm-up cache an toàn khi chạy lại và khi lỗi

### 9.1. Snapshot nguyên tử

Một cách triển khai sai:

~~~java
cache.clear();
for (Entry entry : repository.findAll()) {
    cache.put(entry.code(), entry.value());
}
~~~

Đây là **pseudocode minh họa**, không phải class runnable. Nếu query/loop lỗi ở giữa, cache chỉ có một phần. Trong khi loop chạy, các readers có thể gặp cache thiếu dữ liệu.

Cách cải thiện:

~~~java
Map<String, String> next = loadAndValidateAllEntries();
cacheReference.set(Map.copyOf(next));
~~~

Mảnh code trên giả định đã có **loadAndValidateAllEntries()** và **AtomicReference<Map<String,String>> cacheReference**. Tư tưởng cốt lõi: **build → validate → publish**.

Có thể dùng **AtomicReference** hoặc field **volatile** để publish cả map không thay đổi. Với dữ liệu lớn, phải cân nhắc thêm RAM gấp đôi tạm thời (old snapshot + new snapshot), thời gian build và sự khác biệt revision/epoch của dữ liệu.

### 9.2. Cache miss vẫn phải có chiến lược

Warm-up không bảo đảm cache sẽ chứa mọi key về sau. Khi có cache miss:

- Query lại database hoặc nguồn chính (cache-aside).
- Dùng TTL và invalidation phù hợp.
- Giới hạn số request đồng thời cùng tái tải một key (single-flight nếu cần).
- Nếu key bắt buộc cho hệ thống hoạt động, đánh dấu readiness hoặc trả lỗi rõ ràng thay vì lặng lẽ dùng giá trị sai.

**Không dùng cache làm nguồn sự thật** trong tình huống dữ liệu thường xuyên thay đổi mà không có cơ chế consistency.

### 9.3. Warm-up "required" khác "best effort"

| Chính sách | Khi warm-up thất bại | Hậu quả |
| --- | --- | --- |
| **Bắt buộc trước ready** | Runner ném exception hoặc ngăn readiness, theo thiết kế | Instance không nhận traffic khi thiếu điều kiện bắt buộc |
| **Best effort** | Ghi log/metric, tiếp tục startup; dùng cache miss fallback | Startup nhanh hơn nhưng request đầu có thể chậm |
| **Asynchronous warm-up** | Runner tạo tác vụ nền rồi return | **Không bảo đảm** tác vụ hoàn tất trước ApplicationReadyEvent |
| **Partial warm-up** | Chỉ nạp hot keys, key còn lại load-on-demand | Cần dự trù miss và cold-start latency |

Nếu runner async là yêu cầu thật, dùng **Future/CompletableFuture** với deadline, error handling và cơ chế readiness. Đừng cho rằng Boot tự đợi task con sau khi runner trả về.

Một failure policy hợp lý cho required data: nếu seed sai schema/mất kết nối -> **fail fast**, không công bố readiness. Còn cache chỉ để tối ưu tốc độ -> **best effort** có thể chấp nhận nếu luôn có đường đọc dữ liệu gốc.

## 10. Thứ tự giữa nhiều Runner

Spring Boot cho phép nhiều **ApplicationRunner** và **CommandLineRunner** trong cùng application. Khi cần sắp xếp, dùng **@Order** hoặc **Ordered** trên các runner beans.

Ví dụ ý tưởng:

~~~java
@Bean
@Order(10)
ApplicationRunner seedRunner() {
    return args -> seedDefaults();
}

@Bean
@Order(20)
ApplicationRunner warmupRunner() {
    return args -> rebuildCache();
}
~~~

Đây là **mảnh cấu hình minh họa**, cần implement **seedDefaults()**, **rebuildCache()** và import **Bean**, **Order**, **ApplicationRunner**. Phương thức trên không phải file Java độc lập.

Dùng order chỉ khi **các giai đoạn thực sự có dependency**. Nếu warm-up bắt buộc phải chạy sau seed, có thể đơn giản hơn khi dùng **một runner điều phối** như ví dụ runnable tại mục 6, tránh phụ thuộc ngầm vào thứ tự các runner do nhiều module đóng góp.

**@Order không tạo transaction, không tạo distributed lock và không đồng bộ giữa các pods.** Nó chỉ ảnh hưởng thứ tự thực thi các runner trong một SpringApplication startup.

Không viết logic phụ thuộc thứ tự của hai runner có cùng order nếu framework không bảo đảm thứ tự ổn định giữa chúng.

## 11. Phân biệt seed, migration và runtime repair

| Nhu cầu | Công cụ/hook thường phù hợp | Lưu ý |
| --- | --- | --- |
| Tạo vài default records nếu thiếu | Runner + DB unique key/insert-if-absent | Chạy lại không ghi đè data hợp lệ |
| Tiến hóa schema theo version | Flyway/Liquibase migrations | Versioned, quản lý thứ tự và checksum |
| Cập nhật reference data bất biến theo release | Migration/versioned script | Không thay vô tình user customizations |
| Rebuild cache local lúc startup | ApplicationRunner hoặc cache service startup hook | Build/swap snapshot, failure policy |
| Dữ liệu thay đổi liên tục | Cache-aside, TTL, invalidation, CDC/event | Startup warm-up một lần không đủ |
| Repair dữ liệu production có rủi ro | Job quản trị riêng, có audit và dry run | Không tự chạy phá dữ liệu ở mọi replica startup |
| Background scheduled synchronization | Scheduler/worker có idempotency | Bảo vệ concurrency, retry, observability |

**Seed qua Runner không thay thế database migrations.** Runner chạy sau khi Boot đã refresh context; một datasource được ORM hoặc các bean khác sử dụng có thể đòi schema hợp lệ **trước đó**. Với schema có version, migration nên chạy trước những thành phần phụ thuộc schema.

Khi một bản ghi thực sự phải thay đổi theo version, không nên "thêm seed mỗi lần" theo cách mơ hồ. Hãy định nghĩa điều kiện version, transaction, audit trail và khả năng rollback trước.

## 12. Kiểm thử để chứng minh "chạy lại an toàn"

Không chỉ chạy happy path một lần. Một bộ kiểm thử thực tế nên có các tình huống:

| Test | Dữ liệu ban đầu | Thao tác | Kỳ vọng |
| --- | --- | --- | --- |
| Fresh start | Bảng rỗng | Chạy seed rồi warm-up | Tạo đúng DEFAULT, cache có giá trị |
| Repeat in process | Đã có DEFAULT | Chạy lại cùng logic | Không tăng số bản ghi, cache đúng |
| Restart | File DB giữ nguyên | Tắt/mở process | Không tạo thêm DEFAULT |
| Manual edit preservation | DEFAULT có display_name tùy chỉnh | Chạy lại | Tên mới được giữ và đưa vào cache |
| Concurrent startup | Hai tiến trình seed cùng key | Chạy song song | Tối đa một DEFAULT, không mất dữ liệu |
| DB unavailable | Không kết nối DB | Chạy required seed | Startup fail rõ ràng, không che lỗi |
| Failed cache read | Query lỗi giữa lúc xây snapshot | Warm-up lại | Không publish snapshot chưa hoàn tất |
| Cache staleness | DB đổi sau warm-up | Đọc key | Miss/TTL/invalidation xử lý đúng chiến lược |
| Additional records | Bảng có thêm mã khác | Chạy warm-up | Cache chứa các mã hợp lệ, không xóa DB |
| Crash mid-seed | Dữ liệu mới ghi một phần | Restart và chạy lại | Transaction rollback hoặc bước thiếu được bù idempotent |

### Assertion cho bài demo

Với database sạch, sau hai lượt trong runner:

~~~text
COUNT(catalog) = 1
cache.size()   = 1
cache.DEFAULT  = "Mặc định"
~~~

Sau restart với cùng DB, những điều kiện đó vẫn đúng. Nếu đổi display_name trong DB, kiểm tra cache lấy **giá trị từ DB**, không lấy default hardcode.

Khi viết integration tests thực sự cho Spring Boot 3.5, có thể dùng **@SpringBootTest**, **JdbcTemplate** và một database test phù hợp. Nếu cần mô phỏng restart thật, đừng dùng duy nhất H2 in-memory tái tạo mới mỗi test rồi tuyên bố đã kiểm chứng tính bền vững qua process; hãy dùng file/temporary database phù hợp hoặc database integration test container.

## 13. Logging, đo lường và xử lý failure

Một runner production nên ghi được các thông tin giúp quan sát nhưng không rò rỉ dữ liệu nhạy cảm:

- Tên tác vụ và version logic seed.
- Số bản ghi đã được **tạo mới**, **đã tồn tại** và **thất bại**.
- Thời gian seed, thời gian warm-up và kích thước snapshot.
- Trạng thái DB/cache dependency với metric thích hợp.
- Mốc bắt đầu/hoàn thành và failure reason đủ để truy vết.
- Key/tenant được xử lý nếu phù hợp chính sách bảo mật và cardinality của metrics.

Không log token, mật khẩu, dữ liệu cá nhân hoặc hàng nghìn key vào stdout chỉ để kiểm tra warm-up.

### Retry có kiểm soát

Nếu DB tạm thời không sẵn sàng:

1. Chỉ retry loại lỗi có thể phục hồi (transient).
2. Dùng giới hạn số lần, deadline, exponential backoff và jitter khi nhiều replicas cùng retry.
3. Khi hết retry, chọn **fail startup** hoặc **degraded readiness** theo yêu cầu nghiệp vụ.
4. Luôn làm thao tác idempotent để lần retry không làm hỏng dữ liệu đã ghi.
5. Không retry vô hạn bên trong runner khiến startup treo mà không có tín hiệu.

Lỗi vi phạm schema hoặc cấu hình là lỗi **không nên** retry mù quáng. Một lỗi DuplicateKeyException cho đúng key đã tồn tại là trường hợp bình thường trong seed-if-absent, nhưng không vì thế được bỏ qua mọi lỗi database khác.

## 14. Các câu hỏi tự kiểm tra

**Câu 1.** Vì sao một Runner "chỉ chạy lúc startup" vẫn phải idempotent?

**Câu 2.** Hai replica cùng kiểm tra **existsById=false** rồi insert. Vì sao chỉ dùng kiểm tra ở tầng Java là không đủ?

**Câu 3.** Một DEFAULT row được quản trị viên đổi tên. Sau restart, seed should leave it unchanged hay update về mặc định? Điều này phụ thuộc quy tắc nào?

**Câu 4.** Vì sao thao tác **cache.clear()** rồi nạp dần nguy hiểm khi có readers đồng thời? Snapshot qua volatile/AtomicReference cải thiện gì?

**Câu 5.** Một runner submit CompletableFuture rồi return ngay. Có thể kết luận warm-up hoàn tất trước ApplicationReadyEvent không?

**Câu 6.** @Order trên hai runner có thay thế unique constraint hoặc distributed lock không?

**Câu 7.** Khi nào cần migration tool thay vì đặt mọi SQL vào runner?

**Câu 8.** Nếu cache là tối ưu hiệu năng và DB vẫn phục vụ trực tiếp được, warm-up lỗi có nhất thiết phải fail startup không?

**Đáp án gợi ý:**

1. Vì restart, redeploy, retries và nhiều replicas khiến thao tác lặp lại.
2. Hai tiến trình cùng đọc trạng thái cũ; cần unique constraint/atomic database operation để ngăn duplicate.
3. Với seed mặc định-if-absent, phải giữ nguyên; với dữ liệu bất biến/versioned correction, phải có hợp đồng update rõ ràng.
4. Readers thấy cache rỗng/nửa chừng; immutable snapshot được công bố nguyên tử sau khi tải xong.
5. Không; Spring Boot chỉ chờ phương thức runner hoàn thành, không chờ task async tự phát.
6. Không, @Order chỉ là thứ tự trong một application instance.
7. Khi schema/reference data cần versioning, audit, migration có thứ tự và rollback/repair rõ ràng.
8. Không nhất thiết; có thể best effort và dùng đường fallback, tùy SLO/readiness policy.

## 15. Checklist thiết kế trước khi triển khai

- [ ] Đã định nghĩa rõ điều kiện thành công của seed/warm-up và điều gì xảy ra nếu gọi lại?
- [ ] Có unique/business key ở **database**, không chỉ check ở Java?
- [ ] Dữ liệu người vận hành chỉnh sửa có được bảo toàn đúng hợp đồng?
- [ ] Transaction boundary có đủ để tránh dữ liệu nửa chừng?
- [ ] Nếu có nhiều replicas, chiến lược race/conflict rõ ràng?
- [ ] Không bắt và bỏ qua tất cả exception?
- [ ] Cache được **build/validate/publish** thay vì clear-and-refill nguy hiểm?
- [ ] Có cache miss strategy, TTL hoặc invalidation khi nguồn thay đổi?
- [ ] Warm-up bắt buộc hay best effort đã được quyết định?
- [ ] Runner đồng bộ thực sự đợi các bước bắt buộc trước khi trả về?
- [ ] Readiness và liveness được dùng đúng vai trò?
- [ ] Có retry limit, timeout, logging, metrics và test restart/concurrency?
- [ ] Schema/version migrations được tách khỏi startup seed nếu cần?

## 16. Tóm tắt

**ApplicationRunner/CommandLineRunner là nơi phù hợp để thực hiện công việc sau refresh và trước ApplicationReadyEvent. Nhưng chạy tại startup không có nghĩa chỉ chạy một lần.** Thiết kế cần cho phép restart, retry và nhiều instance cùng hoạt động mà vẫn duy trì trạng thái đúng.

Hai nguyên tắc thực hành chính:

1. **Seed idempotent:** dùng business key ổn định + constraint ở nguồn dữ liệu, insert-if-absent và transaction phù hợp; không ghi đè thay đổi hợp lệ chỉ vì ứng dụng restart.
2. **Warm-up idempotent:** đọc từ source of truth, xây snapshot mới hoàn chỉnh, chỉ publish sau khi tải/kiểm tra thành công; quyết định rõ phải chặn readiness hay có thể best effort.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — SpringApplication, ApplicationRunner/CommandLineRunner và application events: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Database Initialization: https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html
- Spring Boot 3.5 — Application Availability và probes: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability
- Spring Framework — JDBC, JdbcTemplate và exception translation: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html

Ví dụ runnable dùng **Spring Boot 3.5.x, Spring Framework 6.x, Java 17+ và H2**. Với dự án sử dụng phiên bản hoặc cơ sở dữ liệu khác, hãy kiểm tra JavaDoc và SQL dialect tương ứng trước khi triển khai nguyên mẫu lên production.