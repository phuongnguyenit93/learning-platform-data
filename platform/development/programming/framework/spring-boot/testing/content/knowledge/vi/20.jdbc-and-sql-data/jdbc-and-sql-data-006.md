# Kiểm tra câu lệnh SQL, điều kiện lọc và số dòng bị tác động

Trong một ứng dụng **Spring Boot sử dụng JDBC**, câu SQL chạy không ném exception vẫn có thể **sai nghiệp vụ**: SELECT trả dữ liệu tenant khác, WHERE dùng AND/OR thiếu ngoặc, bản ghi archived bị lọt vào kết quả, UPDATE tác động quá nhiều dòng hoặc DELETE trả 0 nhưng API lại báo xóa thành công. Do đó, kiểm thử SQL cần xác minh **đúng tập bản ghi, đúng điều kiện lọc, đúng giá trị biên, số dòng bị tác động và trạng thái dữ liệu sau câu lệnh**.

Bài này tập trung **JdbcTemplate**, PreparedStatement parameter binding, **SELECT/UPDATE/DELETE**, affected-row counts **0, 1 hoặc N**, optimistic update theo version, JDBC batchUpdate, NULL, LIKE và phòng tránh SQL injection. Dự án mẫu chạy với **Java 17, Spring Boot 3.4.5, Spring JDBC, H2, JUnit Jupiter và @JdbcTest**. Các test thực sự gửi SQL tới embedded database; không mock JdbcTemplate. Kết quả được nêu là **dự kiến theo code**, không phải log Gradle đã được chạy trong quá trình biên soạn.

## 1. SQL đúng là gì? Đừng chỉ hỏi “có trả dữ liệu không?”

Giả sử hệ thống có bảng task_items và mỗi row thuộc một tenant. Yêu cầu: “Liệt kê BUG đang OPEN, priority tối thiểu 4, chưa archived của TENANT_A, xếp priority giảm dần rồi ID tăng dần.”

Một câu SQL sai có thể:

- Thiếu **tenant_key = ?** khiến lộ task của TENANT_B.
- Dùng **priority > ?** thay vì **>= ?**, loại bản ghi đúng ngưỡng.
- Bỏ **archived = FALSE**, đưa soft-deleted tasks vào kết quả.
- Sai ngoặc khi kết hợp **AND/OR**, làm một nhánh bỏ qua tenant.
- Không có thứ tự tổng thể **ORDER BY**, khiến test flaky khi DB đổi kế hoạch truy vấn.
- Nối user input trực tiếp vào SQL, có nguy cơ injection.
- Chỉ assert **size() == 2**; hai ID sai cũng có thể đạt size 2.

Fixture trong bài được thiết kế để mỗi lỗi trên có row đối chứng:

| ID | Tenant | Category | Status | Priority | Archived | Ý nghĩa |
| ---: | --- | --- | --- | ---: | --- | --- |
| 1 | TENANT_A | BUG | OPEN | 5 | false | Khớp |
| 2 | TENANT_A | FEATURE | OPEN | 2 | false | Category/priority khác |
| 3 | TENANT_A | BUG | DONE | 3 | false | Status khác |
| 4 | TENANT_B | BUG | OPEN | 5 | false | Tenant khác, nếu quên tenant filter sẽ lọt |
| 5 | TENANT_A | BUG | OPEN | 1 | true | Soft deleted |
| 6 | TENANT_A | BUG | OPEN | 5 | false | Khớp, trùng priority với ID 1 |
| 7 | TENANT_B | FEATURE | DONE | 4 | false | Bắt lỗi OR thiếu ngoặc |

Kết quả đúng cho truy vấn mục tiêu là **[1, 6]**. Test nên assert **exact ordered IDs** và thuộc tính từng row; thêm negative cases cho tenant B, archived và priority boundary.

## 2. SELECT bằng JdbcTemplate và điều kiện WHERE rõ ràng

~~~sql
SELECT id, tenant_key, category, status,
       priority, version, title, reviewer, archived
FROM task_items
WHERE tenant_key = ?
  AND category = ?
  AND status = 'OPEN'
  AND priority >= ?
  AND archived = FALSE
ORDER BY priority DESC, id ASC;
~~~

Dấu **?** là placeholder cho **PreparedStatement values**. Với JdbcTemplate, các giá trị phải được cung cấp đúng thứ tự:

~~~java
List<TaskRow> rows = jdbc.query(
        sql,
        rowMapper,
        "TENANT_A", "BUG", 4);
~~~

Đây là trích đoạn, không phải chương trình độc lập; phần 7 có class hoàn chỉnh. Binding giúp giá trị không thay đổi cấu trúc SQL, nhưng không tự bổ sung authorization condition. Bạn vẫn phải viết WHERE tenant_key rõ ràng.

**Các trường hợp nên assert:**

| Input | Expected IDs |
| --- | --- |
| TENANT_A / BUG / minPriority=4 | [1,6] |
| TENANT_A / BUG / minPriority=5 | [1,6] |
| TENANT_A / BUG / minPriority=6 | [] |
| TENANT_B / BUG / minPriority=4 | [4] |
| TENANT_A / FEATURE / minPriority=4 | [] |

Hai task có priority=5 giúp kiểm tra tie-breaker **id ASC**. Không được dựa vào thứ tự tự nhiên của INSERT hoặc primary-key scan: không có ORDER BY thì SQL không bảo đảm thứ tự kết quả.

### Không chỉ assert COUNT(*)

**COUNT(*)** dùng để đếm số dòng phù hợp một predicate. Nó **không thay thế** assertion danh sách ID hoặc giá trị thực. Truy vấn thiếu tenant filter có thể cho cùng số lượng trong một fixture khác nhưng sai tập dữ liệu. Nếu business yêu cầu đúng 2 rows **1 và 6**, test phải nói rõ hai IDs đó.

## 3. AND/OR: có ngoặc mới giữ đúng tenant filter

Giả sử muốn lấy những task chưa archived của tenant A, có status OPEN **hoặc** DONE.

**Đúng:**

~~~sql
SELECT id
FROM task_items
WHERE tenant_key = ?
  AND archived = FALSE
  AND (status = 'OPEN' OR status = 'DONE')
ORDER BY id;
~~~

**Sai:**

~~~sql
SELECT id
FROM task_items
WHERE tenant_key = ?
  AND archived = FALSE
  AND status = 'OPEN'
  OR status = 'DONE'
ORDER BY id;
~~~

Do **AND có ưu tiên cao hơn OR**, câu sai tương đương:

~~~text
(tenant_key = ? AND archived = FALSE AND status = 'OPEN')
OR status = 'DONE'
~~~

Mọi row DONE của tenant khác có thể lọt. Fixture chứa **ID 7 / TENANT_B / DONE** cố ý để test bắt lỗi này. Kết quả đúng cho TENANT_A là **[1,2,3,6]**; nếu xuất hiện 7 tức là có rủi ro lộ dữ liệu.

Các query phức tạp dùng nhiều nhánh OR/IN nên có test cho từng nhánh và một row cố ý khớp nhánh sai. Khi build WHERE động, tránh nối user input vào SQL; dùng **NamedParameterJdbcTemplate** với named values hoặc JdbcTemplate positional binding và nhóm predicates rõ ràng.

## 4. SQL NULL, LIKE và ký tự đặc biệt

### 4.1. NULL phải dùng IS NULL

Để tìm task chưa có reviewer:

~~~sql
SELECT id FROM task_items
WHERE tenant_key = ?
  AND reviewer IS NULL
  AND archived = FALSE
ORDER BY id;
~~~

**reviewer = NULL** không cho kết quả TRUE trong SQL three-valued logic; so sánh với NULL thường cho UNKNOWN, rồi WHERE loại row. Reviewer rỗng **''** cũng không đồng nghĩa NULL trên mọi DB. Fixture có reviewer NULL/không NULL, nên test đúng phải trả **[1,3]** cho TENANT_A chưa archived.

### 4.2. PreparedStatement không tự escape wildcard LIKE

Trong **LIKE**, phần trăm **%** và gạch dưới **_** là ký tự đại diện. Dù bạn bind bằng PreparedStatement, một fragment người dùng nhập **%** vẫn bị hiểu là wildcard nếu không escape. Muốn tìm **dấu phần trăm thật** trong title, chọn escape character, ví dụ **!**:

~~~sql
SELECT id FROM task_items
WHERE tenant_key = ?
  AND archived = FALSE
  AND title LIKE ? ESCAPE '!'
ORDER BY id;
~~~

Java biến fragment thành literal pattern:

~~~java
String escaped = fragment
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
String pattern = "%" + escaped + "%";
~~~

Khi fragment bằng **%**, pattern là **%!%%**: bất kỳ prefix, dấu phần trăm thật, bất kỳ suffix. Fixture có title **Plan 100% complete** ở ID 2, nên expected IDs là **[2]**. Nếu bỏ escape, pattern có thể match gần như mọi title.

### 4.3. Giá trị đầu vào phải là data, không phải SQL code

**Không làm:**

~~~java
String unsafe = "UPDATE task_items SET title = '"
        + userTitle + "' WHERE id = " + id;
~~~

Đây là ví dụ **sai có chủ ý**. Dữ liệu chứa dấu nháy hoặc comment marker có thể thay đổi câu SQL. Hãy dùng:

~~~java
jdbc.update(
        "UPDATE task_items SET title=? WHERE id=? AND tenant_key=?",
        userTitle, id, tenant);
~~~

Khi muốn người dùng chọn tên cột ORDER BY, **identifier không được bind bằng ?**. Cần allowlist server-side, ví dụ chỉ chấp nhận priority hoặc id rồi map sang constant SQL. Đừng tin trực tiếp sortKey từ request.

## 5. JdbcTemplate.update: số dòng bị tác động có ý nghĩa gì?

JdbcTemplate.update(...) trả một **int update count** do JDBC driver báo. Đó là bằng chứng về số row mà statement tác động theo semantics của driver/DB. Các tình huống:

| Count | Hợp đồng thường gặp | Cần kiểm chứng tiếp |
| ---: | --- | --- |
| **0** | Không có row khớp hoặc không được driver tính như affected row | Không row sai bị sửa; xác định conflict/not-found/unauthorized nếu business cần |
| **1** | Một row được tác động | Có đúng ID/tenant, state và version mong muốn không? |
| **N > 1** | Bulk operation hoặc WHERE quá rộng | N có phải số mong đợi, rows ngoài phạm vi có nguyên vẹn không? |
| **Exception** | Constraint, syntax, connection, transaction error... | Đúng exception category, rollback và dữ liệu cuối |

**Không suy ra count=0 tức ID không tồn tại.** Lệnh có nhiều conditions: ID có thể tồn tại nhưng tenant sai, version cũ, status không hợp lệ hoặc archived=true. Tầng API không nên tiết lộ tài nguyên thuộc tenant khác chỉ vì caller thử một ID.

Ngoài ra, một số engine/driver phân biệt **rows matched** và **rows thực sự đổi dữ liệu** khi UPDATE đặt lại cùng giá trị. Không áp một kỳ vọng “UPDATE giống dữ liệu cũ luôn trả 0” cho mọi database. Trong ví dụ, câu UPDATE theo version **thực sự đổi status và tăng version**, làm phép kiểm count rõ ràng hơn.

## 6. UPDATE theo ID, tenant, version và status

~~~sql
UPDATE task_items
SET status = 'DONE',
    version = version + 1
WHERE id = ?
  AND tenant_key = ?
  AND version = ?
  AND status = 'OPEN'
  AND archived = FALSE;
~~~

Với **ID 1, TENANT_A, expectedVersion=0**, lần đầu trả **1** và thay OPEN -> DONE, version 0 -> 1. Lần thứ hai vẫn expectedVersion=0 sẽ trả **0**, vì version/status đã khác. Với **ID 6** đang version 2 nhưng truyền expectedVersion=1, trả **0**. Với ID 4 thuộc tenant B nhưng truyền TENANT_A, cũng trả **0**.

Đây là kiểu **compare-and-set** ở database: điều kiện version được kiểm tra trong chính statement, không phải SELECT rồi kiểm tra ở Java trước khi UPDATE. Nó giảm rủi ro **lost update** khi có concurrent requests. Tuy nhiên nó không thay toàn bộ business conflict handling hoặc transaction policy.

**0 rows không chỉ có một nguyên nhân**: thiếu ID, sai tenant, stale version, status DONE hay archived. Nếu cần báo domain error khác nhau, service phải thiết kế tra cứu bổ sung có kiểm tra quyền và tránh lộ sự tồn tại của ID của tenant khác.

### Bulk update cố ý ảnh hưởng N rows

~~~sql
UPDATE task_items
SET archived = TRUE, version = version + 1
WHERE tenant_key = ?
  AND status = 'DONE'
  AND archived = FALSE;
~~~

Trong fixture, TENANT_A có đúng **một DONE chưa archived** (ID 3). Lệnh archive trả **1**, lần chạy lại trả **0**. ID 7 là DONE của TENANT_B nên phải vẫn archived=false. Nếu quên tenant predicate, count và state tests sẽ fail.

### DELETE phải kiểm tra cả những row sống sót

~~~sql
DELETE FROM task_items
WHERE tenant_key = ?
  AND archived = TRUE;
~~~

Với TENANT_A, câu SQL xóa ID 5, trả **1**; chạy lại trả **0**. Tổng số rows tenant A từ **5 xuống 4**, nhưng quan trọng hơn là **ID 4 của tenant B và các tasks chưa archived của A còn nguyên**. Test DELETE chỉ assert count=1 không đủ: một câu DELETE sai cũng có thể xóa đúng một row nhưng là **row khác**.

## 7. Dự án runnable: Spring Boot 3.4.5, Spring JDBC và H2

Dự án dùng một repository SQL thủ công, record Java cho một row và @JdbcTest thực thi SQL trên embedded H2. Các lệnh kiểm thử không phụ thuộc web server hoặc DB ngoài.

**Cấu trúc:**

~~~text
settings.gradle
build.gradle
src/main/java/com/example/sqlqa/SqlQaApplication.java
src/main/java/com/example/sqlqa/TaskRow.java
src/main/java/com/example/sqlqa/TaskItemJdbcRepository.java
src/test/resources/application.properties
src/test/resources/schema.sql
src/test/resources/data.sql
src/test/java/com/example/sqlqa/TaskItemJdbcRepositoryTest.java
~~~

### 7.1. Gradle và cấu hình test

**settings.gradle**

~~~groovy
rootProject.name = 'spring-jdbc-sql-qa'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/test/resources/application.properties**

~~~properties
spring.datasource.generate-unique-name=true
spring.sql.init.mode=always
~~~

**spring-boot-starter-jdbc** cấu hình DataSource và JdbcTemplate. **spring-boot-starter-test** cung cấp JUnit Jupiter và Spring TestContext. Embedded H2 chạy trong test classpath. **@JdbcTest** mặc định rollback mỗi test method; datasource là database nhúng và repository @Component thông thường không tự được scan. Phần test dùng **@Import** để thêm một repository thật.

**schema.sql** và **data.sql** nằm trong src/test/resources, được SQL initialization nạp lúc test ApplicationContext khởi tạo. Trong một dự án đã có Flyway/Liquibase/production schema, cần chọn một chiến lược migrations/fixtures riêng để tránh chạy script tạo bảng trùng.

### 7.2. Schema với tenant và soft-delete

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE task_items (
    id BIGINT PRIMARY KEY,
    tenant_key VARCHAR(40) NOT NULL,
    category VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    priority INTEGER NOT NULL,
    version INTEGER NOT NULL,
    title VARCHAR(120) NOT NULL,
    reviewer VARCHAR(60),
    archived BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_task_tenant_status
    ON task_items (tenant_key, status, archived, priority);
~~~

ID fixtures được cấp tường minh nên tests không lệ thuộc auto-increment sequence. **reviewer nullable** để test IS NULL. **archived** là soft-delete flag. **version** là cột integer phục vụ optimistic update bằng SQL, không phải JPA @Version (dự án không dùng JPA).

### 7.3. Fixture có cả rows nên và không nên match

**src/test/resources/data.sql**

~~~sql
INSERT INTO task_items
 (id, tenant_key, category, status, priority,
  version, title, reviewer, archived)
VALUES
 (1, 'TENANT_A', 'BUG', 'OPEN', 5,
  0, 'Bug A-1', NULL, FALSE),
 (2, 'TENANT_A', 'FEATURE', 'OPEN', 2,
  0, 'Plan 100% complete', 'Mai', FALSE),
 (3, 'TENANT_A', 'BUG', 'DONE', 3,
  1, 'Bug A-done', NULL, FALSE),
 (4, 'TENANT_B', 'BUG', 'OPEN', 5,
  0, 'Bug B-1', NULL, FALSE),
 (5, 'TENANT_A', 'BUG', 'OPEN', 1,
  0, 'Already archived', NULL, TRUE),
 (6, 'TENANT_A', 'BUG', 'OPEN', 5,
  2, 'Bug A-2', 'An', FALSE),
 (7, 'TENANT_B', 'FEATURE', 'DONE', 4,
  0, 'Other tenant done', 'Bao', FALSE);
~~~

Không nên tối giản fixture còn một row; khi đó SQL thiếu tenant/status/archived vẫn có thể xanh. Có **ID 7 DONE của tenant khác** giúp phát hiện OR grouping, **ID 5 archived** giúp phát hiện soft-delete filter, **ID 1 và 6 đồng priority** giúp kiểm tra tie-breaker, **ID 2 có %** giúp test LIKE escape.

### 7.4. Application và kiểu dữ liệu trả về

**src/main/java/com/example/sqlqa/SqlQaApplication.java**

~~~java
package com.example.sqlqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SqlQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(SqlQaApplication.class, args);
    }
}
~~~

**src/main/java/com/example/sqlqa/TaskRow.java**

~~~java
package com.example.sqlqa;

public record TaskRow(
        long id,
        String tenantKey,
        String category,
        String status,
        int priority,
        int version,
        String title,
        String reviewer,
        boolean archived) {
}
~~~

Java record giúp test truy cập các trường bằng id(), tenantKey(), status()... Đây **không phải JPA entity**, không có dirty checking; mọi phép cập nhật đều bằng JdbcTemplate.update.

### 7.5. JDBC repository thực thi câu SQL

**src/main/java/com/example/sqlqa/TaskItemJdbcRepository.java**

~~~java
package com.example.sqlqa;

import java.util.Arrays;
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class TaskItemJdbcRepository {
    private final JdbcTemplate jdbc;

    private static final String COLUMNS = """
            SELECT id, tenant_key, category, status,
                   priority, version, title, reviewer, archived
            FROM task_items
            """;

    private static final RowMapper<TaskRow> MAPPER =
            (rs, number) -> new TaskRow(
                    rs.getLong("id"),
                    rs.getString("tenant_key"),
                    rs.getString("category"),
                    rs.getString("status"),
                    rs.getInt("priority"),
                    rs.getInt("version"),
                    rs.getString("title"),
                    rs.getString("reviewer"),
                    rs.getBoolean("archived"));

    public TaskItemJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<TaskRow> findOpenCritical(
            String tenant, String category, int minimum) {
        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND category = ?
                  AND status = 'OPEN'
                  AND priority >= ?
                  AND archived = FALSE
                ORDER BY priority DESC, id ASC
                """, MAPPER, tenant, category, minimum);
    }

    public List<TaskRow> findActiveOpenOrDone(String tenant) {
        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND archived = FALSE
                  AND (status = 'OPEN' OR status = 'DONE')
                ORDER BY id
                """, MAPPER, tenant);
    }

    public List<TaskRow> findUnassigned(String tenant) {
        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND reviewer IS NULL
                  AND archived = FALSE
                ORDER BY id
                """, MAPPER, tenant);
    }

    public List<TaskRow> searchLiteralTitle(
            String tenant, String fragment) {
        String escaped = fragment.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
        String pattern = "%" + escaped + "%";

        return jdbc.query(COLUMNS + """
                WHERE tenant_key = ?
                  AND archived = FALSE
                  AND title LIKE ? ESCAPE '!'
                ORDER BY id
                """, MAPPER, tenant, pattern);
    }

    public Optional<TaskRow> findForTenant(
            long id, String tenant) {
        List<TaskRow> rows = jdbc.query(COLUMNS + """
                WHERE id = ? AND tenant_key = ?
                """, MAPPER, id, tenant);
        return rows.stream().findFirst();
    }

    public int closeOpenWithVersion(
            long id, String tenant, int expectedVersion) {
        return jdbc.update("""
                UPDATE task_items
                SET status = 'DONE', version = version + 1
                WHERE id = ?
                  AND tenant_key = ?
                  AND version = ?
                  AND status = 'OPEN'
                  AND archived = FALSE
                """, id, tenant, expectedVersion);
    }

    public int changeTitle(
            long id, String tenant, String title) {
        return jdbc.update("""
                UPDATE task_items
                SET title = ?
                WHERE id = ?
                  AND tenant_key = ?
                  AND archived = FALSE
                """, title, id, tenant);
    }

    public int archiveDone(String tenant) {
        return jdbc.update("""
                UPDATE task_items
                SET archived = TRUE, version = version + 1
                WHERE tenant_key = ?
                  AND status = 'DONE'
                  AND archived = FALSE
                """, tenant);
    }

    public int deleteArchived(String tenant) {
        return jdbc.update("""
                DELETE FROM task_items
                WHERE tenant_key = ?
                  AND archived = TRUE
                """, tenant);
    }

    public int[] raisePriorities(String tenant, long... ids) {
        List<Object[]> args = Arrays.stream(ids)
                .mapToObj(id -> new Object[]{tenant, id})
                .toList();

        return jdbc.batchUpdate("""
                UPDATE task_items
                SET priority = priority + 1
                WHERE tenant_key = ?
                  AND id = ?
                  AND archived = FALSE
                """, args);
    }
}
~~~

Repository này có các điểm cần bảo vệ:

- Mọi truy vấn nghiệp vụ **nhận tenant qua bind parameter**; SELECT/UPDATE/DELETE đều có predicate rõ ràng.
- **COLUMNS** là SELECT field list dùng chung; RowMapper chuyển ResultSet thành TaskRow theo tên column.
- **findOpenCritical** kiểm tra >=, archived và ORDER BY tie-breaker.
- **findActiveOpenOrDone** nhóm OR bằng ngoặc.
- **findUnassigned** dùng IS NULL.
- **searchLiteralTitle** escape wildcard và dùng LIKE ESCAPE '!'.
- **findForTenant** dùng Optional cho trường hợp không có row; queryForObject trên 0 row sẽ ném EmptyResultDataAccessException.
- **closeOpenWithVersion** là atomic SQL predicate cho optimistic update.
- **changeTitle** bind input hoàn toàn thành data, kể cả dấu nháy.
- **archiveDone** có thể ảnh hưởng nhiều rows nhưng luôn giới hạn bởi tenant/status.
- **deleteArchived** phải xóa đúng những rows đã archive.
- **raisePriorities** là JDBC batch update nhiều bộ arguments; mảng count cần diễn giải theo JDBC driver.

Không có mock repository/JdbcTemplate trong bộ test: mục tiêu của bài là chứng minh **SQL thực sự chạy**.

## 8. Test JUnit 5 với @JdbcTest và @Import

**src/test/java/com/example/sqlqa/TaskItemJdbcRepositoryTest.java**

~~~java
package com.example.sqlqa;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest
@Import(TaskItemJdbcRepository.class)
class TaskItemJdbcRepositoryTest {
    @Autowired
    private TaskItemJdbcRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void selectChecksEveryPredicateAndStableOrder() {
        List<TaskRow> rows = repository.findOpenCritical(
                "TENANT_A", "BUG", 4);

        assertEquals(List.of(1L, 6L),
                rows.stream().map(TaskRow::id).toList());
        assertTrue(rows.stream().allMatch(row ->
                row.tenantKey().equals("TENANT_A")
                && row.category().equals("BUG")
                && row.status().equals("OPEN")
                && row.priority() >= 4
                && !row.archived()));
    }

    @Test
    void boundaryAndWrongTenantAreExcluded() {
        assertEquals(List.of(1L, 6L),
                repository.findOpenCritical("TENANT_A", "BUG", 5)
                        .stream().map(TaskRow::id).toList());

        assertTrue(repository.findOpenCritical(
                "TENANT_A", "BUG", 6).isEmpty());

        assertEquals(List.of(4L),
                repository.findOpenCritical("TENANT_B", "BUG", 4)
                        .stream().map(TaskRow::id).toList());

        assertTrue(repository.findOpenCritical(
                "TENANT_A", "FEATURE", 4).isEmpty());
    }

    @Test
    void orGroupDoesNotLeakOtherTenants() {
        List<Long> ids = repository.findActiveOpenOrDone("TENANT_A")
                .stream().map(TaskRow::id).toList();

        assertEquals(List.of(1L, 2L, 3L, 6L), ids);
        assertFalse(ids.contains(7L));
        assertFalse(ids.contains(5L));
    }

    @Test
    void nullAndLikeHavePreciseSemantics() {
        assertEquals(List.of(1L, 3L),
                repository.findUnassigned("TENANT_A")
                        .stream().map(TaskRow::id).toList());

        List<TaskRow> matches =
                repository.searchLiteralTitle("TENANT_A", "%");
        assertEquals(List.of(2L),
                matches.stream().map(TaskRow::id).toList());
        assertEquals("Plan 100% complete", matches.get(0).title());
    }

    @Test
    void findByIdCannotIgnoreTenant() {
        assertTrue(repository.findForTenant(
                4L, "TENANT_A").isEmpty());
        assertEquals("TENANT_B",
                repository.findForTenant(4L, "TENANT_B")
                        .orElseThrow().tenantKey());
    }

    @Test
    void exactOneThenZeroOnOptimisticUpdate() {
        int first = repository.closeOpenWithVersion(
                1L, "TENANT_A", 0);
        assertEquals(1, first);

        TaskRow changed = repository.findForTenant(
                1L, "TENANT_A").orElseThrow();
        assertEquals("DONE", changed.status());
        assertEquals(1, changed.version());

        assertEquals(0, repository.closeOpenWithVersion(
                1L, "TENANT_A", 0));
        assertEquals(0, repository.closeOpenWithVersion(
                6L, "TENANT_A", 1));
        assertEquals(0, repository.closeOpenWithVersion(
                4L, "TENANT_A", 0));

        assertEquals("OPEN",
                repository.findForTenant(4L, "TENANT_B")
                        .orElseThrow().status());
        assertEquals("OPEN",
                repository.findForTenant(6L, "TENANT_A")
                        .orElseThrow().status());
    }

    @Test
    void preparedParametersPreventTitleSqlInjection() {
        String suspicious = "x', status='DONE' --";
        assertEquals(1, repository.changeTitle(
                1L, "TENANT_A", suspicious));

        TaskRow row = repository.findForTenant(
                1L, "TENANT_A").orElseThrow();
        assertEquals(suspicious, row.title());
        assertEquals("OPEN", row.status());

        assertEquals(0, repository.changeTitle(
                4L, "TENANT_A", "wrong tenant"));
        assertEquals("Bug B-1",
                repository.findForTenant(4L, "TENANT_B")
                        .orElseThrow().title());
    }

    @Test
    void bulkArchiveChecksCountAndUntouchedTenant() {
        assertEquals(1, repository.archiveDone("TENANT_A"));
        assertEquals(0, repository.archiveDone("TENANT_A"));

        TaskRow archived = repository.findForTenant(
                3L, "TENANT_A").orElseThrow();
        assertTrue(archived.archived());
        assertEquals(2, archived.version());

        TaskRow other = repository.findForTenant(
                7L, "TENANT_B").orElseThrow();
        assertFalse(other.archived());
        assertEquals(0, other.version());
    }

    @Test
    void deletionAffectsOnlyArchivedRows() {
        long before = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items "
                        + "WHERE tenant_key = 'TENANT_A'",
                Long.class);
        assertEquals(5L, before);

        assertEquals(1, repository.deleteArchived("TENANT_A"));
        assertEquals(0, repository.deleteArchived("TENANT_A"));

        long after = jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items "
                        + "WHERE tenant_key = 'TENANT_A'",
                Long.class);
        assertEquals(4L, after);
        assertEquals(0, jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items WHERE id=5",
                Integer.class).intValue());
        assertEquals(1, jdbc.queryForObject(
                "SELECT COUNT(*) FROM task_items WHERE id=4",
                Integer.class).intValue());
    }

    @Test
    void batchReturnsPerStatementCounts() {
        int[] affected = repository.raisePriorities(
                "TENANT_A", 1L, 2L, 4L);
        assertArrayEquals(new int[]{1, 1, 0}, affected);

        assertEquals(6, repository.findForTenant(
                1L, "TENANT_A").orElseThrow().priority());
        assertEquals(3, repository.findForTenant(
                2L, "TENANT_A").orElseThrow().priority());
        assertEquals(5, repository.findForTenant(
                4L, "TENANT_B").orElseThrow().priority());
    }
}
~~~

**Vì sao @Import?** @JdbcTest chỉ tập trung JDBC infrastructure và database, không tự quét business @Repository thông thường. **@Import(TaskItemJdbcRepository.class)** đăng ký đúng repository implementation thật để test chạy SQL thay vì một mock.

**Vì sao các test độc lập?** @JdbcTest mặc định chạy mỗi test method trong một transaction rồi **rollback**. Vì vậy update/delete ở test trước không khiến test sau mất fixture. Dữ liệu schema/data được nạp khi test context khởi tạo. Nếu thay bằng @SpringBootTest real HTTP, @Transactional ở JUnit test method không tự rollback server request thread; cần cleanup riêng.

### 8.1. Bằng chứng từ SELECT và filters

- **selectChecksEveryPredicateAndStableOrder** xác nhận [1,6] và tất cả điều kiện row.
- **boundaryAndWrongTenantAreExcluded** bắt lỗi > thay vì >=, bỏ tenant filter hoặc sai category.
- **orGroupDoesNotLeakOtherTenants** bắt thiếu ngoặc AND/OR bằng ID7 tenant B DONE.
- **nullAndLikeHavePreciseSemantics** bắt reviewer = NULL và LIKE không escape %, qua expected IDs [1,3] / [2].
- **findByIdCannotIgnoreTenant** chứng minh ID4 có tồn tại nhưng không được đọc dưới TENANT_A.

### 8.2. Bằng chứng từ UPDATE/DELETE

- **exactOneThenZeroOnOptimisticUpdate**: lần đầu sửa đúng ID1 (count=1), version tăng; stale ID1, stale ID6 và sai tenant ID4 đều trả 0; rows bị loại giữ nguyên.
- **preparedParametersPreventTitleSqlInjection**: input chứa dấu nháy và comment marker được lưu đúng nguyên văn, không thay SQL structure/status.
- **bulkArchiveChecksCountAndUntouchedTenant**: chỉ ID3 DONE tenant A được archived; count 1 rồi 0; ID7 DONE tenant B còn nguyên.
- **deletionAffectsOnlyArchivedRows**: chỉ ID5 archived A bị xóa, A count 5→4, ID4 tenant B còn.
- **batchReturnsPerStatementCounts**: H2 trả [1,1,0] cho update ID1 A, ID2 A và ID4 B khi gọi dưới tenant A; verify cả priority sau update.

**Không chỉ assert count trả về.** Một UPDATE sai WHERE có thể ảnh hưởng 1 row nhưng không phải row mục tiêu. Do đó các test đọc lại dữ liệu sau thao tác.

## 9. Chạy test và kết quả dự kiến

Tạo Gradle Wrapper tương thích JDK 17 và Spring Boot 3.4.x. Trong thư mục dự án chạy:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.sqlqa.TaskItemJdbcRepositoryTest
~~~

Windows dùng **gradlew.bat** với cùng args. Các test được **thiết kế để PASS** nếu files/dependencies/cấu hình đúng như bài; đây là **kỳ vọng từ code**, không phải stdout Gradle đã được quan sát.

Bảng kết quả mong đợi:

| Test | Giá trị quan trọng |
| --- | --- |
| selectChecksEveryPredicateAndStableOrder | ID [1,6] |
| boundaryAndWrongTenantAreExcluded | [1,6], [], [4], [] |
| orGroupDoesNotLeakOtherTenants | [1,2,3,6], không có ID7 |
| nullAndLikeHavePreciseSemantics | Reviewer NULL [1,3], literal % [2] |
| exactOneThenZeroOnOptimisticUpdate | Counts 1,0,0,0; ID1 DONE/version1 |
| preparedParametersPreventTitleSqlInjection | Count1, status giữ OPEN |
| bulkArchiveChecksCountAndUntouchedTenant | Counts 1 rồi 0, ID7 không đổi |
| deletionAffectsOnlyArchivedRows | DELETE 1 rồi 0, A total 5→4 |
| batchReturnsPerStatementCounts | Batch [1,1,0], B unaffected |

Không cố định một câu SQL stdout hoặc execution-plan giống nhau trên mọi database: driver, query optimizer và dialect khác nhau. Contract chủ yếu ở **kết quả và trạng thái**, không ở whitespace SQL log.

## 10. Affected rows: những nhầm lẫn quan trọng

### 10.1. 0 rows không tiết lộ lý do

Với UPDATE có nhiều predicates, **0** có thể nghĩa ID không tồn tại, tenant không được phép, expectedVersion cũ, status đã DONE hoặc archived=true. Một API multi-tenant không nên phản hồi một cách khiến client suy ra ID của tenant khác tồn tại. Chọn response 404/409/403 theo policy có kiểm soát, không từ count duy nhất mà tự suy đoán nguyên nhân.

### 10.2. Đếm trước UPDATE không bảo đảm count khi UPDATE

Nếu SELECT COUNT(*) trước cho biết 1 matching row, transaction khác có thể thay đổi state trước UPDATE. **COUNT trước UPDATE không làm update atomic**. Với optimistic concurrency, đưa version vào **chính WHERE của UPDATE**, sau đó dùng update count làm tín hiệu compare-and-set.

### 10.3. Matched-vs-changed rows là driver-specific

SQL UPDATE đặt một value bằng chính value hiện tại có thể được driver báo số dòng khớp hoặc số dòng thực sự đổi, phụ thuộc DB/config. Đừng viết test portable yêu cầu count luôn 0 trong trường hợp no-op. Ví dụ sử dụng **version = version + 1**, nên mỗi update thành công có thay đổi thật.

### 10.4. Batch counts có mã trạng thái đặc biệt

JDBC batchUpdate có thể trả **Statement.SUCCESS_NO_INFO = -2** (thành công nhưng không có count cụ thể) hoặc **Statement.EXECUTE_FAILED = -3** tùy error handling/driver. Mảng **[1,-2,0]** không được cộng lại thành -1 để suy ra tổng affected rows. Khi thao tác batch có failure, kiểm tra DataAccessException/BatchUpdateException được translate, transaction rollback, trạng thái từng row và tính atomicity cần thiết.

Test H2 trong bài **dự kiến [1,1,0]**, nhưng driver production có thể báo differently; cần test trên engine/driver thật khi exact counts là business contract.

### 10.5. Một bulk statement khác JDBC batch

**UPDATE ... WHERE tenant_key=?** có thể sửa N rows trong **một SQL statement** và JdbcTemplate.update trả một count. **JdbcTemplate.batchUpdate** chạy một PreparedStatement với N sets tham số, trả **mảng count**. Hai phương án khác về transaction, error handling và performance. Đừng dùng một assert chung cho cả hai loại.

## 11. Ghi log SQL, đo query và tránh test “mock xanh”

Bạn có thể bật log để chẩn đoán:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
~~~

Logging này chỉ nên dùng trong test/development khi cần; thông tin tham số có thể chứa dữ liệu nhạy cảm. Log cho biết SQL/bind values, nhưng **không tự chứng minh WHERE đúng**. Cần fixture có rows đối chứng và behavior assertions.

Một test Mockito kiểu **verify(jdbcTemplate).update(sql, params)** có thể giúp unit test builder tạo đúng argument list, nhưng không phát hiện SQL syntax lỗi, cột sai hoặc constraint violation. Với mục tiêu trong bài, **@JdbcTest với database thật** là bằng chứng quan trọng hơn.

Có thể dùng DataSource proxy/spy để assert SQL structure trong những hệ thống yêu cầu hint, query routing hoặc số SQL statements. Đừng buộc một unit test vào exact SQL whitespace/alias khi điều cần bảo vệ là business row set. Với performance, dùng query plan/EXPLAIN trên database thực và dữ liệu đủ đại diện.

## 12. H2 khác database production ở đâu?

H2 phù hợp để test JDBC wiring, cú pháp SQL cơ bản, parameter binding, WHERE logic và kết quả row updates. Nhưng có những khác biệt cần lưu ý:

- Dialect và syntax của PostgreSQL/MySQL/Oracle (UPSERT, RETURNING, functions, JSON types).
- Collation, case sensitivity, Unicode và LIKE matching.
- JDBC update-count semantics cho matched/changed rows.
- Isolation, locking, deadlock, optimistic/pessimistic conflicts.
- Constraint timing, foreign keys, unique indexes và transaction behavior.
- Query plan/index usage và hiệu năng dữ liệu lớn.
- Schema migrations bằng Flyway/Liquibase trong production.

Nếu một tính năng phụ thuộc vendor behavior, bổ sung **Testcontainers** với database engine/version gần deployment. Một H2 test xanh không tự chứng minh tất cả SQL dialect, transaction isolation hoặc query plan production đúng.

## 13. @Sql, TestContext transactions và rollback

Spring TestContext cho phép seed scripts bằng **@Sql** trước/sau test method. Cần biết **@SqlConfig(transactionMode=ISOLATED)** có thể chạy script trong transaction riêng và commit, khiến rollback của test method không dọn dữ liệu ấy. Đừng trộn seed script được commit với assumption “mọi dữ liệu đều rollback”.

Trong dự án trên, SQL initializer nạp schema/data khi test context khởi tạo, còn DML trong test method được @JdbcTest rollback. Nếu thực sự muốn chứng minh commit visibility, hãy viết test transaction lifecycle riêng, không gắn mặc định rollback rồi suy ra client khác đã thấy row.

**@JdbcTest không phải @SpringBootTest**: slice không tự tải mọi @Service, MVC controller hoặc security filters. Nó đủ để chứng minh SQL repository với DataSource/H2 và transaction test. Khi cần kiểm tra controller → service → SQL, thêm integration test full context, hiểu rằng server HTTP thread khác transaction của JUnit test method.

**Cảnh báo JUnit preemptive timeout:** Spring transaction thường gắn thread. Nếu assertTimeoutPreemptively hoặc một framework chạy thân test trên thread khác, DML có thể chạy ngoài test-managed transaction và không được rollback như kỳ vọng. Dùng timeout không tạo thread khác hoặc quản lý transaction đúng.

## 14. Truy vấn động và NamedParameterJdbcTemplate

Khi category/status filters là danh sách, **NamedParameterJdbcTemplate** giúp bind collection cho điều kiện IN:

~~~java
String sql = """
    SELECT id FROM task_items
    WHERE tenant_key = :tenant
      AND category IN (:categories)
      AND archived = FALSE
    ORDER BY id
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("tenant", "TENANT_A")
        .addValue("categories", List.of("BUG", "FEATURE"));

List<Long> ids = namedJdbc.queryForList(
        sql, params, Long.class);
~~~

Đây là **trích đoạn**, không thuộc source runnable; cần các imports, biến **NamedParameterJdbcTemplate namedJdbc**, và xử lý danh sách categories rỗng có chủ đích. Một số DB không chấp nhận **IN ()**, nên hãy định nghĩa empty list có nghĩa “no match” hay “no filter” trước khi tạo SQL. Không nối thẳng user input vào IN string.

Sort column/direction cũng cần allowlist:

~~~java
String column = switch (sortKey) {
    case "priority" -> "priority";
    case "id" -> "id";
    default -> throw new IllegalArgumentException("invalid sort");
};
~~~

Trích đoạn này nằm trong một method có biến sortKey. Sau đó chỉ thêm ASC/DESC từ enum hoặc allowlist. PreparedStatement bảo vệ **values**, không bind tên cột/tên bảng thành identifiers.

## 15. Bảng lỗi thường gặp và cách bắt

| Lỗi SQL | Dấu hiệu | Assertion cần có |
| --- | --- | --- |
| Thiếu tenant filter | Lọt ID tenant B | Exact ordered IDs, assert không có ID4/7 |
| OR không có ngoặc | DONE tenant B lọt tenant A | Fixture ID7, expected [1,2,3,6] |
| > thay vì >= | Mất ID đúng priority threshold | Priority=5, min=5 trả [1,6] |
| Bỏ archived=false | ID5 xuất hiện | Expected list không có ID5 |
| ORDER BY thiếu tie-breaker | Kết quả không ổn định | ID1,ID6 cùng priority, id ASC |
| reviewer = NULL | Thiếu reviewer NULL | IS NULL test expected [1,3] |
| LIKE không escape % | Trả quá nhiều rows | Literal % chỉ match ID2 |
| Nối SQL input trực tiếp | Injection/syntax error | Suspicious title lưu nguyên văn |
| UPDATE thiếu expectedVersion | Stale request overwrite row | Version sai trả count0 |
| UPDATE thiếu tenant | Sửa ID4 của tenant B | Tenant A update ID4 trả 0, B unchanged |
| Bulk UPDATE thiếu status | Archive OPEN rows | ID3 đổi, ID1/2/6 còn active |
| DELETE thiếu archived | Xóa active tasks | Chỉ ID5 biến mất |
| Chỉ assert affected count | Xóa sai row cũng có thể count1 | Readback IDs và untouched rows |
| Batch count sum sai | Có -2/-3 | Kiểm tra mã JDBC và dữ liệu cuối |
| Mock JDBC thay DB | Không bắt syntax/schema | @JdbcTest + H2 |
| Test xanh riêng, fail cả suite | Fixture/transaction/context rò state | Rollback, SQL init, @Sql policy rõ |
| H2 xanh, prod sai | Dialect/driver/isolation khác | Testcontainers DB engine thật |

## 16. Bài tập tự kiểm tra

**A.** SELECT trả đúng hai rows, nhưng một row TENANT_B. Test chỉ assert size==2 đủ không? **Không.** Assert exact IDs/tenant, không chỉ số lượng.

**B.** WHERE tenant=? AND status='OPEN' OR status='DONE' có rủi ro gì? **OR thiếu ngoặc** có thể bỏ qua tenant cho nhánh DONE.

**C.** SELECT COUNT(*) trước UPDATE bằng 1, UPDATE sau chắc chắn count1 không? **Không.** Data/transaction có thể đổi; dùng count từ UPDATE thật.

**D.** UPDATE trả 0 thì ID chắc chắn không tồn tại không? **Không.** Sai tenant, stale version, status và archived đều có thể gây 0.

**E.** PreparedStatement có tự escape % trong LIKE không? **Không.** Phải escape pattern wildcard khi cần tìm ký tự thật.

**F.** UPDATE cùng giá trị cũ phải trả 0 trên mọi DB không? **Không.** Matched/changed row count phụ thuộc driver.

**G.** @JdbcTest sửa row rồi test sau vẫn thấy fixture cũ. Vì sao? Test DML được rollback sau từng method.

**H.** DELETE count1 có chứng minh đúng ID được xóa chưa? **Chưa.** Phải kiểm tra row identity và những rows còn nguyên.

**I.** Batch result [1,-2,0] cộng lại được -1 affected rows không? **Không.** -2 là SUCCESS_NO_INFO, không phải số row âm.

**J.** H2 PASS có chứng minh PostgreSQL dùng cùng query plan/locking không? **Không.** Cần test engine thật.

**K.** Một test chỉ verify Mockito JdbcTemplate.update invocation có chứng minh SQL hợp lệ không? **Không**; câu SQL chưa hề chạy trên DB.

**L.** Vì sao câu UPDATE theo version mạnh hơn SELECT-check-UPDATE? Vì **WHERE version và SET version+1** là một compare-and-set SQL statement, giảm race giữa hai thao tác riêng.

### Checklist QA

- Có đủ test rows khớp và rows **không được phép khớp**?
- SELECT đã assert exact IDs, ordering, tenant/category/status/priority/archived?
- AND/OR đã được nhóm bằng ngoặc, NULL dùng IS NULL?
- LIKE có escape %/_ khi tìm literal?
- User values được bind bằng ? hoặc named parameters, identifiers/sort được allowlist?
- UPDATE/DELETE assert **0/1/N theo contract** và **state sau thao tác**?
- Có assert rows **ngoài WHERE** không thay đổi?
- Optimistic update dùng version predicate, không chỉ check ở Java?
- BatchUpdate counts có xử lý driver-specific -2/-3?
- @JdbcTest có repository thật thông qua @Import và H2 fixtures tin cậy?
- Rollback vs commit và HTTP server thread đã được phân biệt?
- Có test trên production DB engine cho SQL dialect, collation và isolation nếu cần?

**Kết luận:** SQL test đáng tin không chỉ kiểm tra rằng câu lệnh chạy thành công. Với **SELECT**, phải bảo vệ đúng tập ID, tenant, predicates và ORDER BY. Với **UPDATE/DELETE**, cần kiểm tra số dòng affected và đọc lại **đúng rows đã đổi**, đồng thời những rows ngoài WHERE vẫn nguyên vẹn. **@JdbcTest + H2** giúp bắt lỗi sớm và nhanh; khi behavior phụ thuộc driver/production database, bổ sung integration tests trên engine thật.

## Tài liệu chính thức

- Spring Framework — JDBC Core và JdbcTemplate query/update: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Boot 3.4 — @JdbcTest Javadoc, embedded DB và rollback: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/JdbcTest.html
- Spring Boot 3.4 — Slice Auto-configuration: https://docs.spring.io/spring-boot/3.4/appendix/test-auto-configuration/slices.html
- Spring Framework — TestContext @Sql: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html
- Spring Framework — Test-managed Transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
