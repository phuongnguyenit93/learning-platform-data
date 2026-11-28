# Kiểm thử rollback, auditing, callback và xung đột đồng thời

Bài học này thuộc chương **Kiểm thử** của module **SPRING_DATA_NEO4J**. Một ứng dụng Spring Data Neo4j không chỉ cần kiểm tra repository có lưu và đọc đúng node hay không. Những lỗi khó phát hiện thường xuất hiện ở ranh giới transaction, khi dữ liệu phải rollback sau exception, auditing cần ghi đúng thời điểm, callback biến đổi entity trước hoặc sau khi ánh xạ, và nhiều request cùng cập nhật một node hoặc relationship.

Một bộ kiểm thử tốt cần xác minh cả kết quả cuối trong graph lẫn cách Spring Data Neo4j phối hợp với transaction manager và Neo4j Java Driver. Các tình huống cần kiểm tra gồm:

- Một nghiệp vụ gồm nhiều thao tác ghi phải rollback toàn bộ khi có lỗi.
- Trường tạo/cập nhật và auditor phải được điền đúng.
- Callback phải chạy đúng thời điểm và thay đổi đúng object được persistence.
- Hai thao tác dùng cùng phiên bản entity không được âm thầm ghi đè thay đổi của nhau.
- Các thao tác Cypher nguyên tử, lock contention và deadlock phải có hành vi có thể dự đoán.

## 1. Chọn loại kiểm thử phù hợp

Có thể chia kiểm thử thành ba lớp:

| Loại kiểm thử | Phạm vi | Công cụ phù hợp |
|---|---|---|
| Unit test | Quy tắc domain, hàm chuyển đổi thuần, xử lý dữ liệu không truy cập database | JUnit, Mockito hoặc AssertJ |
| Integration test | Repository, mapping, auditing, callback, Cypher và transaction thực tế | Spring Boot **@DataNeo4jTest** cùng Neo4j Testcontainers hoặc Neo4j Test Harness |
| Concurrency/integration stress test | Xung đột phiên bản, lock contention, deadlock, retry và tải đồng thời | Neo4j thật hoặc Testcontainers, nhiều thread/session/transaction độc lập |

Không nên giả lập repository khi mục tiêu là kiểm tra rollback, auditing hoặc optimistic locking. Những hành vi này phụ thuộc vào transaction manager, mapping context và phản hồi thực tế từ Neo4j.

## 2. Dùng @DataNeo4jTest cho integration test

Spring Boot cung cấp **@DataNeo4jTest** trong spring-boot-starter-test. Test slice này cấu hình các thành phần cần cho kiểm thử SDN:

- Driver và hạ tầng kết nối theo cấu hình test.
- Neo4jClient và Neo4jTemplate.
- Transaction manager imperative hoặc reactive tương ứng.
- Các repository Neo4j và entity được phát hiện.
- Spring TestContext cho JUnit Jupiter.

**@DataNeo4jTest** không tự khởi chạy một database. Test cần kết nối tới Neo4j Testcontainers, Neo4j Test Harness hoặc một database test được cấu hình riêng. Test Harness chạy cùng JVM và có thể nhanh, nhưng hiệu năng/thời gian không nhất thiết giống môi trường production.

Ví dụ dùng Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@DataNeo4jTest
class Neo4jSliceTest {

    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5");

    @DynamicPropertySource
    static void neo4jProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password", neo4j::getAdminPassword);
    }

    @Autowired
    Neo4jClient neo4jClient;

    @Test
    void shouldConnectToNeo4j() {
        var result = neo4jClient.query("RETURN 1 AS value")
            .fetchAs(Long.class)
            .mappedBy((typeSystem, record) -> record.get("value").asLong())
            .one();

        assertThat(result).contains(1L);
    }
}
~~~

Chọn image Neo4j tương thích với phiên bản Java Driver, Spring Boot và SDN mà ứng dụng đang dùng. Không dùng database production cho test rollback hoặc concurrency vì test có thể tạo, sửa và xóa dữ liệu thật.

**@DataNeo4jTest** là test slice nên không tự quét mọi service component trong ứng dụng. Khi cần kiểm tra service transaction, import service vào test context bằng **@Import(ServiceClass.class)** hoặc dùng **@SpringBootTest** nếu cần toàn bộ application context.

## 3. Transaction mặc định của @DataNeo4jTest

**@DataNeo4jTest** thêm một transaction imperative ngầm cho mỗi test method. Theo mặc định, transaction này rollback sau khi test kết thúc. Điều đó giúp dữ liệu tạo trong một test không tồn tại trong test tiếp theo.

Ví dụ:

~~~java
@DataNeo4jTest
class NoteRepositoryTest {

    @Autowired
    NoteRepository noteRepository;

    @Test
    void shouldPersistNoteInsideTestTransaction() {
        noteRepository.save(new Note("note-1", "Graph basics"));

        assertThat(noteRepository.findById("note-1")).isPresent();
    }
}
~~~

Sau khi test kết thúc, Spring TestContext rollback transaction của test. Tuy nhiên, cần hiểu đúng giới hạn:

- Các repository call trong test thường tham gia transaction test đang mở.
- Nếu service có propagation REQUIRED, service có thể tham gia transaction test đó thay vì mở một transaction độc lập.
- Việc test tự kết thúc bằng rollback không chứng minh một service transaction đã rollback đúng tại thời điểm exception.
- Transaction test mặc định là imperative. Nó không tự kiểm tra reactive transaction.

Khi cần kiểm tra ranh giới transaction thật của service, hãy tắt transaction do test quản lý bằng **@Transactional(propagation = Propagation.NOT_SUPPORTED)**. Khi đó, method service được Spring proxy sẽ mở và hoàn tất transaction riêng.

## 4. Kiểm thử rollback của một nghiệp vụ nhiều thao tác

Giả sử một nghiệp vụ tạo node Note, sau đó ghi thêm node AuditMarker bằng Cypher. Nếu thao tác thứ hai hoặc logic nghiệp vụ ném exception, cả hai thay đổi phải rollback khi chúng nằm trong cùng Neo4j transaction.

Entity và repository:

~~~java
package com.example.graph.domain;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.annotation.Version;

@Node("Note")
public class Note {

    @Id
    private String id;

    private String title;

    @Version
    private Long version;

    public Note() {
    }

    public Note(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

~~~java
package com.example.graph.repository;

import com.example.graph.domain.Note;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface NoteRepository extends Neo4jRepository<Note, String> {
}
~~~

Service mở transaction:

~~~java
package com.example.graph.service;

import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteCommandService {

    private final NoteRepository noteRepository;
    private final Neo4jClient neo4jClient;

    public NoteCommandService(
            NoteRepository noteRepository,
            Neo4jClient neo4jClient) {
        this.noteRepository = noteRepository;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void createThenFail(String id) {
        noteRepository.save(new Note(id, "Draft"));

        neo4jClient.query("""
                CREATE (:AuditMarker {id: $id, action: 'NOTE_CREATED'})
                """)
            .bind(id).to("id")
            .run();

        throw new IllegalStateException("Simulated failure");
    }
}
~~~

Repository và Neo4jClient cần dùng cùng hạ tầng Driver/transaction manager để câu Cypher tùy biến tham gia transaction đang mở. Không tự mở một session/transaction độc lập bằng Driver nếu mong đợi thao tác đó rollback cùng repository.

Test phải không nằm trong transaction test-managed:

~~~java
import com.example.graph.repository.NoteRepository;
import com.example.graph.service.NoteCommandService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataNeo4jTest
@Import(NoteCommandService.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class TransactionRollbackTest {

    @Autowired
    NoteCommandService noteCommandService;

    @Autowired
    NoteRepository noteRepository;

    @Autowired
    Neo4jClient neo4jClient;

    @Test
    void shouldRollbackAllWritesWhenServiceFails() {
        assertThatThrownBy(() -> noteCommandService.createThenFail("note-rollback"))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Simulated failure");

        assertThat(noteRepository.findById("note-rollback")).isEmpty();

        var markerCount = neo4jClient.query("""
                MATCH (m:AuditMarker {id: $id})
                RETURN count(m) AS total
                """)
            .bind("note-rollback").to("id")
            .fetchAs(Long.class)
            .mappedBy((typeSystem, record) -> record.get("total").asLong())
            .one();

        assertThat(markerCount).contains(0L);
    }
}
~~~

Test này xác nhận cả node được lưu bằng repository lẫn node được tạo bằng Neo4jClient đều biến mất sau rollback. Nếu chỉ kiểm tra repository, một transaction độc lập vô tình được mở bởi custom Driver code có thể vẫn commit mà test không phát hiện.

## 5. Quy tắc rollback với checked và unchecked exception

Theo mặc định của Spring @Transactional, transaction rollback khi method ném RuntimeException hoặc Error. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định.

Nếu nghiệp vụ dùng checked exception để báo lỗi cần rollback, khai báo rõ:

~~~java
public class ImportFailedException extends Exception {

    public ImportFailedException(String message) {
        super(message);
    }
}
~~~

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional(rollbackFor = ImportFailedException.class)
public void importGraph() throws ImportFailedException {
    // ghi nhiều node và relationship
    throw new ImportFailedException("Invalid graph data");
}
~~~

Không bắt exception rồi bỏ qua nếu muốn transaction rollback. Nếu bắt exception để bổ sung log hoặc chuyển đổi kiểu lỗi, hãy ném lại exception phù hợp hoặc đánh dấu transaction rollback-only khi thật sự cần.

Một lỗi thường gặp trong test là bắt exception bên trong method @Transactional rồi tiếp tục trả về bình thường. Khi đó, Spring có thể không nhận được tín hiệu lỗi để rollback theo quy tắc mong đợi. Hãy để exception đi qua transaction interceptor hoặc đánh dấu rollback-only một cách tường minh.

## 6. Phân biệt rollback của database và trạng thái object trong bộ nhớ

Rollback khôi phục graph trong database về trạng thái trước transaction. Nó không tự khôi phục object Java mà ứng dụng đang giữ.

Ví dụ, sau repository.save(note), object note có thể đã được cập nhật ID, version, @CreatedDate hoặc @LastModifiedDate. Nếu transaction sau đó rollback, các giá trị trong object vẫn có thể còn nguyên dù node không tồn tại trong Neo4j.

Vì vậy:

- Sau rollback, không dùng lại object đã thay đổi như thể nó phản ánh trạng thái database.
- Nếu cần tiếp tục nghiệp vụ, hãy tải lại entity trong transaction mới.
- Trong test, xác minh trạng thái bằng repository hoặc query mới sau khi transaction kết thúc.
- Không dùng giá trị trong object tại thời điểm exception làm bằng chứng rằng dữ liệu đã commit.

## 7. Kiểm thử auditing với DateTimeProvider xác định

Auditing của Spring Data Neo4j hỗ trợ @CreatedDate và @LastModifiedDate. Hãy bật @EnableNeo4jAuditing và cung cấp DateTimeProvider có thời gian xác định trong test.

Thêm trường audit vào entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;

public Instant getCreatedAt() {
    return createdAt;
}

public Instant getLastModifiedAt() {
    return lastModifiedAt;
}
~~~

Provider có thể dùng AtomicReference<Instant> để test chủ động thay đổi thời gian:

~~~java
import java.time.Instant;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.data.auditing.DateTimeProvider;

public class MutableDateTimeProvider implements DateTimeProvider {

    private final AtomicReference<Instant> current =
        new AtomicReference<>();

    public void setNow(Instant instant) {
        current.set(instant);
    }

    @Override
    public Optional<TemporalAccessor> getNow() {
        return Optional.<TemporalAccessor>of(current.get());
    }
}
~~~

Cấu hình test:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@TestConfiguration(proxyBeanMethods = false)
@EnableNeo4jAuditing(
    dateTimeProviderRef = "testDateTimeProvider",
    modifyOnCreate = true
)
public class AuditingTestConfiguration {

    @Bean
    MutableDateTimeProvider testDateTimeProvider() {
        return new MutableDateTimeProvider();
    }
}
~~~

Test tạo rồi cập nhật cùng một entity:

~~~java
import java.time.Instant;

import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@DataNeo4jTest
@Import(AuditingTestConfiguration.class)
class NoteAuditingTest {

    @Autowired
    NoteRepository noteRepository;

    @Autowired
    MutableDateTimeProvider testDateTimeProvider;

    @Test
    void shouldKeepCreationTimeAndAdvanceModificationTime() {
        Instant createdAt = Instant.parse("2026-05-10T03:00:00Z");
        Instant modifiedAt = Instant.parse("2026-05-10T03:05:00Z");

        testDateTimeProvider.setNow(createdAt);
        Note saved = noteRepository.save(new Note("note-audit", "Draft"));

        assertThat(saved.getCreatedAt()).isEqualTo(createdAt);
        assertThat(saved.getLastModifiedAt()).isEqualTo(createdAt);

        testDateTimeProvider.setNow(modifiedAt);
        Note loaded = noteRepository.findById("note-audit").orElseThrow();
        loaded.setTitle("Published");
        Note updated = noteRepository.save(loaded);

        assertThat(updated.getCreatedAt()).isEqualTo(createdAt);
        assertThat(updated.getLastModifiedAt()).isEqualTo(modifiedAt);
    }
}
~~~

Test trên dùng modifyOnCreate = true, nên @LastModifiedDate được điền ngay lần lưu đầu. Nếu cấu hình modifyOnCreate = false, hãy điều chỉnh expectation cho lần tạo. Không dùng Thread.sleep() để đợi thời gian thay đổi; provider xác định làm test nhanh và lặp lại ổn định.

Nếu entity có @CreatedBy hoặc @LastModifiedBy, cần cấu hình AuditorAware<T> để cung cấp principal. Chỉ theo dõi ngày tạo/cập nhật thì không cần auditor provider.

## 8. Kiểm thử auditing khi transaction rollback

Auditing callback chạy trước khi entity được bind và ghi xuống graph. Nếu transaction rollback, các property audit đã được ghi trong transaction cũng rollback cùng node.

Một test có thể:

1. Đặt DateTimeProvider ở thời điểm cố định.
2. Gọi service @Transactional để lưu entity có @CreatedDate.
3. Cố ý ném unchecked exception sau khi lưu.
4. Xác nhận repository không tìm thấy entity sau rollback.
5. Không dùng object Java đã lưu làm bằng chứng entity còn tồn tại.

Lưu ý: nếu callback ghi log hoặc gọi một hệ thống ngoài, hành động bên ngoài đó không tự rollback cùng Neo4j. Callback nên tập trung vào việc chuẩn bị entity. Với side effect chỉ được thực hiện sau khi commit, dùng event được xử lý ở pha AFTER_COMMIT hoặc transactional outbox.

## 9. Kiểm thử BeforeBindCallback

BeforeBindCallback<T> được gọi trước khi SDN chuyển entity thành record để ghi vào Neo4j. Callback có thể trả về chính entity đã sửa hoặc một instance mới.

Ví dụ chuẩn hóa tiêu đề trước khi lưu:

~~~java
import com.example.graph.domain.Note;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.data.neo4j.core.mapping.callback.BeforeBindCallback;

@TestConfiguration(proxyBeanMethods = false)
public class NoteCallbackConfiguration {

    @Bean
    BeforeBindCallback<Note> normalizeNoteTitle() {
        return note -> {
            note.setTitle(note.getTitle().trim());
            return note;
        };
    }
}
~~~

Kiểm thử callback qua repository:

~~~java
import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@DataNeo4jTest
@Import(NoteCallbackConfiguration.class)
class NoteCallbackTest {

    @Autowired
    NoteRepository noteRepository;

    @Test
    void shouldNormalizeTitleBeforeBinding() {
        noteRepository.save(new Note("note-callback", "  Graph model  "));

        Note loaded = noteRepository.findById("note-callback").orElseThrow();

        assertThat(loaded.getTitle()).isEqualTo("Graph model");
    }
}
~~~

Test đọc lại entity từ database để xác nhận giá trị đã được ghi, thay vì chỉ kiểm tra object đầu vào đã bị callback sửa trong bộ nhớ.

Nhiều BeforeBindCallback có thể cùng tồn tại. Nếu thứ tự có ý nghĩa, triển khai Ordered hoặc dùng @Order để xác định trình tự. Không dựa vào thứ tự khởi tạo bean ngẫu nhiên.

## 10. Kiểm thử AfterConvertCallback

AfterConvertCallback<T> chạy sau khi SDN đã đọc record và hydrate entity cùng các association. Callback có thể điều chỉnh instance được trả về cho phần còn lại của quá trình đọc.

Ví dụ thêm nhãn hiển thị chỉ dùng trong ứng dụng:

~~~java
import com.example.graph.domain.Note;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.data.neo4j.core.mapping.callback.AfterConvertCallback;

@TestConfiguration(proxyBeanMethods = false)
public class NoteReadCallbackConfiguration {

    @Bean
    AfterConvertCallback<Note> addDisplayTitle() {
        return (note, entity, source) -> {
            note.setDisplayTitle("[loaded] " + note.getTitle());
            return note;
        };
    }
}
~~~

SDN không có ReactiveAfterConvertCallback riêng; AfterConvertCallback có thể được dùng cho cả luồng imperative và reactive.

Trường displayTitle nên được đánh dấu @Transient nếu không muốn lưu thành property Neo4j:

~~~java
import org.springframework.data.annotation.Transient;

@Transient
private String displayTitle;

public String getDisplayTitle() {
    return displayTitle;
}

public void setDisplayTitle(String displayTitle) {
    this.displayTitle = displayTitle;
}
~~~

Kiểm thử cần phân biệt hai trạng thái:

- Object sau khi đọc có thể chứa displayTitle do callback tạo ra.
- Graph vẫn không có property displayTitle nếu trường được đánh dấu transient.

AfterConvertCallback không phải nơi để ghi ngược thay đổi vào database. Nếu callback thay đổi một field persistent trên object được đọc rồi ứng dụng lưu lại object đó, thay đổi có thể được ghi trong lần save sau; đó là một thao tác persistence riêng.

Có thể xác minh callback khi đọc và xác minh property transient không được lưu:

~~~java
import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.neo4j.core.Neo4jClient;

import static org.assertj.core.api.Assertions.assertThat;

@DataNeo4jTest
@Import(NoteReadCallbackConfiguration.class)
class NoteReadCallbackTest {

    @Autowired
    NoteRepository noteRepository;

    @Autowired
    Neo4jClient neo4jClient;

    @Test
    void shouldEnrichLoadedObjectWithoutPersistingTransientField() {
        noteRepository.save(new Note("note-read-callback", "Graph"));

        Note loaded = noteRepository.findById("note-read-callback").orElseThrow();
        assertThat(loaded.getDisplayTitle()).isEqualTo("[loaded] Graph");

        var displayTitleIsNull = neo4jClient.query("""
                MATCH (n:Note {id: $id})
                RETURN n.displayTitle IS NULL AS isNull
                """)
            .bind("note-read-callback").to("id")
            .fetchAs(Boolean.class)
            .mappedBy((typeSystem, record) -> record.get("isNull").asBoolean())
            .one();

        assertThat(displayTitleIsNull).contains(true);
    }
}
~~~

## 11. Callback và auditing có chạy với mọi câu Cypher không?

Không. Callback của SDN gắn với quá trình mapping entity.

| Đường truy cập | BeforeBindCallback | Auditing entity | AfterConvertCallback |
|---|---|---|---|
| repository.save(entity) | Có | Có, nếu bật auditing | Có thể chạy khi hydrate kết quả |
| Neo4jTemplate.save(entity) | Có | Có, nếu bật auditing | Có thể chạy khi hydrate kết quả |
| Neo4jClient.query(...).run() ghi Cypher thô | Không | Không tự chạy | Không có entity để hydrate |
| Driver Session.run(...) trực tiếp | Không | Không tự chạy | Không có entity để hydrate |
| Query trả entity qua cơ chế mapping SDN | Không có bước bind entity để ghi | Không tự điền audit lúc query đọc | Có thể chạy sau khi hydrate entity |

Nếu custom Cypher trực tiếp tạo hoặc cập nhật node, hãy tự đặt các property audit trong câu lệnh hoặc gọi một đường ghi entity có auditing. Không giả định annotation trên entity tự động tác động tới mọi lệnh Cypher.

## 12. Optimistic locking với @Version

Spring Data Neo4j hỗ trợ optimistic locking bằng @Version trên field kiểu Long. SDN tự quản lý version:

- Entity mới nhận giá trị version ban đầu do SDN quản lý.
- Mỗi lần cập nhật thành công, version được tăng tự động.
- Khi lưu một entity mang version cũ, SDN phát hiện version trong database đã thay đổi và ném OptimisticLockingFailureException.
- Ứng dụng cần tải phiên bản mới nhất, hợp nhất ý định nghiệp vụ rồi mới thử lưu lại.

Không tự tăng hoặc gán version bằng code nghiệp vụ.
Với entity dùng business ID do ứng dụng cấp, @Version cũng là metadata quan trọng để SDN phân biệt trạng thái mới và đã tồn tại; version mới thường bắt đầu từ 0.

Ví dụ entity dùng business ID:

~~~java
@Node("Note")
public class Note {

    @Id
    private String id;

    private String title;

    @Version
    private Long version;

    // constructors, getters and setters
}
~~~

Với business ID do ứng dụng cấp, @Version cũng giúp SDN phân biệt entity mới với entity đã tồn tại. Không bỏ version field khỏi entity chỉ vì ID đã là duy nhất.

## 13. Kiểm thử stale update một cách xác định

Không nhất thiết phải tạo một cuộc đua thread khó tái hiện để kiểm tra optimistic locking. Có thể tải cùng entity hai lần, giữ hai snapshot cùng version, lưu snapshot thứ nhất rồi thử lưu snapshot thứ hai.

Service phải được gọi qua Spring proxy để mỗi method có transaction riêng:

~~~java
import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteEditService {

    private final NoteRepository noteRepository;

    public NoteEditService(NoteRepository noteRepository) {
        this.noteRepository = noteRepository;
    }

    @Transactional(readOnly = true)
    public Note loadForEdit(String id) {
        return noteRepository.findById(id).orElseThrow();
    }

    @Transactional
    public Note saveEdit(Note note) {
        return noteRepository.save(note);
    }
}
~~~

Test không mở transaction bao ngoài:

~~~java
import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import com.example.graph.service.NoteEditService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataNeo4jTest
@Import(NoteEditService.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class OptimisticLockingTest {

    @Autowired
    NoteRepository noteRepository;

    @Autowired
    NoteEditService noteEditService;

    @Test
    void shouldRejectAnUpdateBasedOnAnOldVersion() {
        noteRepository.save(new Note("note-version", "Original"));

        Note firstSnapshot = noteEditService.loadForEdit("note-version");
        Note secondSnapshot = noteEditService.loadForEdit("note-version");
        Long initialVersion = firstSnapshot.getVersion();

        assertThat(firstSnapshot.getVersion())
            .isEqualTo(secondSnapshot.getVersion());

        firstSnapshot.setTitle("Updated by first editor");
        Note firstUpdated = noteEditService.saveEdit(firstSnapshot);

        secondSnapshot.setTitle("Updated by second editor");

        assertThatThrownBy(() -> noteEditService.saveEdit(secondSnapshot))
            .isInstanceOf(OptimisticLockingFailureException.class);

        Note latest = noteEditService.loadForEdit("note-version");
        assertThat(latest.getTitle()).isEqualTo("Updated by first editor");
        assertThat(firstUpdated.getVersion()).isGreaterThan(initialVersion);
        assertThat(latest.getVersion()).isEqualTo(firstUpdated.getVersion());
    }
}
~~~

Test này mô phỏng hai editor đọc cùng một phiên bản. Sau khi editor thứ nhất commit, editor thứ hai không được phép ghi snapshot cũ và âm thầm ghi đè dữ liệu. Kiểm tra entity cuối cùng để xác nhận giá trị của lần cập nhật hợp lệ vẫn được giữ.

## 14. Kiểm thử hai transaction đồng thời bằng barrier

Để kiểm tra tương tác giữa các transaction thực sự chạy trên hai thread, có thể dùng CountDownLatch trong test-only service. Mỗi invocation mở transaction riêng, đọc cùng version, chờ cả hai thread đã đọc xong rồi mới ghi.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConcurrentNoteService {

    private final NoteRepository noteRepository;

    public ConcurrentNoteService(NoteRepository noteRepository) {
        this.noteRepository = noteRepository;
    }

    @Transactional
    public void updateAfterBothReadersArrive(
            String id,
            String title,
            CountDownLatch readersReady,
            CountDownLatch allowWrites) {

        Note note = noteRepository.findById(id).orElseThrow();
        readersReady.countDown();

        try {
            if (!allowWrites.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for test barrier");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }

        note.setTitle(title);
        noteRepository.save(note);
    }
}
~~~

Test chạy hai invocation qua cùng Spring bean proxy:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.example.graph.domain.Note;
import com.example.graph.repository.NoteRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@DataNeo4jTest
@Import(ConcurrentNoteService.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ConcurrentNoteUpdateTest {

    @Autowired
    NoteRepository noteRepository;

    @Autowired
    ConcurrentNoteService concurrentNoteService;

    @Test
    void onlyOneWriterCanCommitFromTheSameVersion() throws Exception {
        noteRepository.save(new Note("note-race", "Original"));

        CountDownLatch readersReady = new CountDownLatch(2);
        CountDownLatch allowWrites = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> first = executor.submit(() ->
                concurrentNoteService.updateAfterBothReadersArrive(
                    "note-race", "Writer A", readersReady, allowWrites));

            Future<?> second = executor.submit(() ->
                concurrentNoteService.updateAfterBothReadersArrive(
                    "note-race", "Writer B", readersReady, allowWrites));

            assertThat(readersReady.await(5, TimeUnit.SECONDS)).isTrue();
            allowWrites.countDown();

            int successCount = 0;
            int conflictCount = 0;

            for (Future<?> future : new Future<?>[] {first, second}) {
                try {
                    future.get(10, TimeUnit.SECONDS);
                    successCount++;
                } catch (ExecutionException ex) {
                    Throwable cause = ex.getCause();
                    while (cause != null
                            && !(cause instanceof OptimisticLockingFailureException)) {
                        cause = cause.getCause();
                    }
                    if (cause instanceof OptimisticLockingFailureException) {
                        conflictCount++;
                    } else {
                        throw ex;
                    }
                }
            }

            assertThat(successCount).isEqualTo(1);
            assertThat(conflictCount).isEqualTo(1);

            Note finalNote = noteRepository.findById("note-race").orElseThrow();
            assertThat(finalNote.getTitle()).isIn("Writer A", "Writer B");
        } finally {
            allowWrites.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Barrier buộc cả hai transaction đọc trước khi được phép ghi. Vì vậy, hai transaction bắt đầu với cùng version và một transaction phải thất bại sau khi transaction còn lại commit. Test cần có timeout để không treo CI nếu một thread không đến được barrier.

Đây là integration test có điều phối nên nên chạy trên Neo4j test instance thật hoặc Testcontainers. Không dùng chung transaction test-managed giữa các thread; mỗi service invocation cần đi qua proxy và có transaction riêng.
Việc chờ barrier bên trong transaction chỉ phục vụ kiểm thử để giữ hai transaction cùng đọc một version; không đưa thao tác chờ hoặc I/O ngoài database vào transaction nghiệp vụ production.

## 15. Cách xử lý OptimisticLockingFailureException

Không retry bằng cách lưu lại chính object stale. Cách đúng là tải lại version hiện tại và hợp nhất ý định nghiệp vụ:

~~~java
import com.example.graph.domain.Note;
import org.springframework.stereotype.Service;
import org.springframework.dao.OptimisticLockingFailureException;

@Service
public class NoteRetryCoordinator {

    private final NoteEditService noteEditService;

    public NoteRetryCoordinator(NoteEditService noteEditService) {
        this.noteEditService = noteEditService;
    }

    public Note renameWithRetry(String id, String requestedTitle) {
        try {
            Note latest = noteEditService.loadForEdit(id);
            latest.setTitle(requestedTitle);
            return noteEditService.saveEdit(latest);
        } catch (OptimisticLockingFailureException conflict) {
            Note latest = noteEditService.loadForEdit(id);
            latest.setTitle(requestedTitle);
            return noteEditService.saveEdit(latest);
        }
    }
}
~~~

Coordinator là một Spring bean riêng và không mở transaction bao ngoài. Các lời gọi qua NoteEditService đi qua proxy để mỗi lần tải/lưu có transaction boundary riêng. Đây chỉ là minh họa cho một lần tải lại; trong production, retry nên có giới hạn, backoff và chính sách merge theo nghiệp vụ. Không phải mọi xung đột đều có thể giải quyết bằng cách ghi đè field của người khác. Nếu hai người cùng thay đổi một tập dữ liệu không thể merge, hãy trả conflict cho client để người dùng quyết định.

Đặt retry ở service boundary phù hợp và bảo đảm mỗi lần thử bắt đầu trong transaction mới. Không bắt exception rồi tiếp tục dùng transaction đã bị đánh dấu rollback-only.

## 16. Read-committed, write lock và lost update trong Neo4j

Neo4j mặc định dùng isolation level read committed. Một transaction đọc node hoặc relationship không khóa dữ liệu đó để ngăn transaction khác cập nhật trước khi transaction đọc kết thúc. Neo4j tự lấy write lock khi thực hiện nhiều loại thao tác ghi, nhưng điều đó không có nghĩa mọi chuỗi đọc-sửa-ghi ở tầng ứng dụng đều tránh được lost update.

Ví dụ một câu Cypher tăng counter có phụ thuộc trực tiếp vào property đang cập nhật:

~~~cypher
MATCH (c:Counter {id: $id})
SET c.value = c.value + $delta
RETURN c.value AS value
~~~

Cypher tự lấy write lock trước khi đọc property trong biểu thức cập nhật. Điều này bảo vệ phép tăng nguyên tử khỏi một số trường hợp lost update.

Ngược lại, nếu ứng dụng đọc giá trị trong một câu lệnh trước, tính toán ở Java, rồi gửi giá trị tuyệt đối trong câu lệnh sau, hai transaction có thể cùng tính từ một giá trị cũ và ghi đè nhau:

~~~java
long current = counterRepository.findValue(id);
long next = current + delta;
counterRepository.setValue(id, next);
~~~

Nếu use case chỉ là tăng/giảm một giá trị, ưu tiên thực hiện phép toán ngay trong một câu Cypher có phụ thuộc trực tiếp vào property. Nếu cần bảo vệ một aggregate entity được đọc rồi chỉnh sửa trong Java, dùng @Version để phát hiện stale update.

## 17. Kiểm thử custom Cypher với version compare-and-set

Một câu Cypher tùy biến không tự đi qua quy trình repository.save(entity) và không nên được giả định là tự áp dụng @Version hoặc entity callbacks. Nếu custom query phải cập nhật entity có version, hãy đưa điều kiện version vào query:

~~~cypher
MATCH (n:Note {id: $id})
WHERE n.version = $expectedVersion
SET n.title = $title,
    n.version = n.version + 1
RETURN n
~~~

Nếu không có record trả về, version không còn khớp hoặc entity không tồn tại. Ứng dụng cần phân biệt hai trường hợp nếu hợp đồng API yêu cầu, ví dụ kiểm tra tồn tại bằng một truy vấn riêng hoặc trả conflict chung cho stale write.

Test custom query nên xác minh:

- Version cũ cho phép cập nhật đúng một lần.
- Cùng version cũ được dùng lần thứ hai không cập nhật tiếp.
- Version mới có thể cập nhật thành công.
- Các callback/auditing không tự chạy cho query ghi thô; query phải tự xử lý property cần thiết.

## 18. Deadlock và thứ tự ghi

Deadlock xảy ra khi hai transaction giữ lock mà transaction kia cần. Ví dụ:

- Transaction A cập nhật node A, sau đó chờ node B.
- Transaction B cập nhật node B, sau đó chờ node A.

Neo4j phát hiện deadlock và kết thúc một transaction với mã lỗi transient như Neo.TransientError.Transaction.DeadlockDetected. Các lock của transaction bị kết thúc được giải phóng khi transaction rollback.

Để giảm deadlock:

- Luôn cập nhật nhiều node/relationship theo cùng một thứ tự ổn định, chẳng hạn sắp xếp ID tăng dần.
- Tránh transaction mở lâu và tránh chờ dịch vụ bên ngoài trong lúc đang giữ lock.
- Giảm số entity dùng chung bị nhiều request cập nhật cùng lúc.
- Chia batch lớn thành các transaction nhỏ.
- Chỉ retry lỗi transient khi toàn bộ thao tác có thể chạy lại an toàn.

Không nên viết test unit dựa vào một lịch thread cụ thể để bắt buộc deadlock xảy ra. Deadlock phụ thuộc timing, lock order và query plan; hãy dùng stress/integration test có kiểm soát và quan sát mã lỗi, thay vì giả định một interleaving luôn xảy ra.

## 19. Retry transaction và tính idempotent

Neo4j Java Driver managed transaction function có thể tự chạy lại callback khi gặp lỗi transient. Do callback có thể được thực thi nhiều lần, logic bên trong phải idempotent:

- Không gửi email hoặc gọi payment API trực tiếp trong transaction callback.
- Không tăng biến static hoặc sửa global state như một side effect của mỗi lần thử.
- Dùng khóa nghiệp vụ và MERGE có định danh ổn định cho thao tác tạo dữ liệu có thể retry.
- Chỉ commit side effect ngoài database sau khi transaction đã commit hoặc dùng transactional outbox.

Đừng mặc định một method Spring @Transactional sẽ tự động được gọi lại khi có deadlock hoặc optimistic locking failure. Nếu cần retry ở tầng Spring, thiết kế retry boundary rõ ràng để mỗi lần thử có transaction mới và bắt đầu từ dữ liệu mới nhất.

## 20. Kiểm thử reactive rollback

@DataNeo4jTest có thể cấu hình cả imperative và reactive infrastructure, nhưng transaction ngầm của test slice là imperative. Để kiểm tra reactive transaction, dùng ReactiveTransactionManager và TransactionalOperator.

Ví dụ:

~~~java
import com.example.graph.domain.Note;
import com.example.graph.repository.ReactiveNoteRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataNeo4jTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ReactiveRollbackTest {

    @Autowired
    ReactiveNoteRepository noteRepository;

    @Autowired
    ReactiveTransactionManager transactionManager;

    @Test
    void shouldRollbackReactiveWriteWhenPublisherFails() {
        TransactionalOperator operator =
            TransactionalOperator.create(transactionManager);

        Mono<Void> work = noteRepository.save(
                new Note("reactive-rollback", "Temporary"))
            .then(Mono.<Void>error(new IllegalStateException("stop")));

        StepVerifier.create(operator.transactional(work))
            .expectError(IllegalStateException.class)
            .verify();

        StepVerifier.create(noteRepository.findById("reactive-rollback"))
            .verifyComplete();
    }
}
~~~

Trong reactive test, không dùng block() hoặc tự subscribe() để kiểm tra transaction. Hãy nối các thao tác vào cùng publisher và dùng StepVerifier để tạo subscription. Nếu test slice đang mở imperative test transaction, hãy vô hiệu hóa transaction test-managed cho test reactive và để TransactionalOperator điều khiển transaction cần xác minh.

Repository reactive dùng trong ví dụ:

~~~java
import com.example.graph.domain.Note;
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface ReactiveNoteRepository
        extends ReactiveNeo4jRepository<Note, String> {
}
~~~

## 21. Kiểm thử relationship entity và auditing

Nếu relationship có property riêng như role, joinedAt hoặc weight, hãy kiểm tra entity @RelationshipProperties và target node cùng transaction. Nếu relationship entity có @Version, kiểm tra stale update của relationship bằng hai snapshot tương tự node entity.

Ví dụ các trường cần xác minh:

- Relationship được tạo với đúng type và direction.
- Property của relationship được ghi cùng với relationship.
- @CreatedDate/@LastModifiedDate trên relationship entity được điền nếu auditing được bật và mapping hỗ trợ.
- Rollback xóa hoặc khôi phục cả relationship và property liên quan.
- Xung đột version trên relationship không làm ghi đè dữ liệu mới.

Khi test relationship, kiểm tra graph bằng query Cypher sau khi lưu. Chỉ kiểm tra collection trong object Java có thể bỏ sót sai direction, sai relationship type hoặc property chưa được ghi.

## 22. Những lỗi thường gặp trong test

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test pass nhưng service rollback sai | Test-managed transaction che khuất ranh giới transaction của service | Dùng Propagation.NOT_SUPPORTED cho test và gọi service qua proxy |
| Node vẫn còn sau rollback | Một thao tác ghi dùng transaction độc lập hoặc transaction manager khác | Dùng chung SDN infrastructure và xác minh mọi write cùng transaction |
| @CreatedDate luôn null | Chưa bật auditing hoặc test không dùng cấu hình auditing | Import cấu hình @EnableNeo4jAuditing và provider |
| Timestamp test chập chờn | Dùng đồng hồ thật hoặc Thread.sleep() | Inject DateTimeProvider cố định/điều khiển được |
| Callback không chạy | Ghi bằng Driver/Cypher thô thay vì entity persistence | Test qua repository hoặc template |
| Callback sửa object nhưng graph không đổi | Chỉ kiểm tra object trong bộ nhớ hoặc callback chạy ở pha đọc | Reload entity và xác minh property trong graph |
| Hai writer ghi đè nhau | Entity không có @Version hoặc query custom bỏ qua version | Dùng optimistic locking hoặc compare-and-set trong Cypher |
| Retry làm tạo dữ liệu trùng | Transaction callback có side effect không idempotent | Dùng khóa ổn định, MERGE, outbox và retry có giới hạn |
| Test concurrency bị treo | Barrier/latch không có timeout hoặc thread không được giải phóng | Đặt timeout và luôn mở latch trong finally |
| Test reactive không rollback | Đang dựa vào transaction imperative ngầm của @DataNeo4jTest | Dùng TransactionalOperator và reactive transaction manager |

## 23. Ma trận kiểm thử nên có

| Nhóm | Kịch bản | Kết quả cần xác minh |
|---|---|---|
| Rollback | Lưu node rồi ném unchecked exception | Node không tồn tại sau khi transaction kết thúc |
| Rollback nhiều abstraction | Repository và Neo4jClient ghi trong cùng transaction | Cả hai thay đổi rollback |
| Rollback checked exception | Checked exception với rollbackFor | Toàn bộ thay đổi rollback theo cấu hình |
| Auditing | Tạo entity với thời gian cố định | Created/modified date đúng |
| Auditing | Cập nhật entity với thời gian mới | Created date giữ nguyên, modified date thay đổi |
| Callback | BeforeBind chuẩn hóa field | Graph lưu giá trị đã chuẩn hóa |
| Callback | AfterConvert tạo field transient | Object đọc có field dẫn xuất, graph không có property đó |
| Optimistic locking | Hai snapshot cùng version | Chỉ lần ghi đầu commit, lần ghi stale bị từ chối |
| Atomic Cypher | Nhiều request tăng counter bằng một câu lệnh | Giá trị cuối bằng tổng delta |
| Deadlock | Stress test với thứ tự lock khác nhau | Có thể quan sát transient deadlock và retry an toàn |
| Reactive rollback | Publisher phát lỗi trong transaction | Không còn dữ liệu sau rollback |

## 24. Nguyên tắc cần nhớ

- Dùng @DataNeo4jTest cho repository/mapping integration test; nó không tự khởi chạy database.
- @DataNeo4jTest mặc định mở imperative test transaction và rollback sau mỗi test.
- Dùng Propagation.NOT_SUPPORTED khi cần xác minh transaction riêng của service.
- Repository và Neo4jClient chỉ rollback cùng nhau khi tham gia cùng transaction manager/Driver.
- Mặc định Spring rollback với unchecked exception và Error; khai báo rollbackFor cho checked exception cần rollback.
- Kiểm tra trạng thái graph sau khi transaction kết thúc, không chỉ trạng thái object trong bộ nhớ.
- Dùng DateTimeProvider cố định để test auditing; không dùng thời gian thực hoặc sleep.
- BeforeBindCallback chạy trước khi entity được bind; AfterConvertCallback chạy sau khi hydrate.
- Callback entity không tự chạy cho câu Cypher ghi thô qua Driver hoặc client.
- Dùng @Version Long để phát hiện stale update và không sửa version thủ công.
- Khi gặp optimistic conflict, tải entity mới và hợp nhất ý định nghiệp vụ; không retry object stale.
- Neo4j mặc định dùng read committed; dùng phép cập nhật Cypher nguyên tử hoặc optimistic locking khi phù hợp.
- Giữ thứ tự cập nhật node/relationship ổn định để giảm deadlock.
- Retry transaction phải có giới hạn và logic idempotent.
- Reactive rollback cần ReactiveTransactionManager/TransactionalOperator, không dựa vào imperative test transaction.

Khi kiểm thử Spring Data Neo4j, hãy tạo các integration test phản ánh đúng transaction boundary của ứng dụng. Xác minh dữ liệu sau rollback, kiểm soát thời gian auditing, kiểm tra callback qua đúng persistence path và mô phỏng stale writer bằng version. Những test này giúp phát hiện sớm lỗi chỉ xuất hiện khi nhiều thao tác hoặc nhiều request cùng tác động lên một graph.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 – Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Data Neo4j 8.1 – Metadata-based Mapping and @Version](https://docs.spring.io/spring-data/neo4j/reference/8.1/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j 8.2 – FAQ: Auditing and entity callbacks](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – BeforeBindCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/BeforeBindCallback.html)
- [Spring Data Neo4j – AfterConvertCallback API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/mapping/callback/AfterConvertCallback.html)
- [Spring Data Commons – Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Neo4j Operations Manual – Concurrent data access, isolation and locks](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Java Driver Manual – Transactions and rollback](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Reactive API](https://neo4j.com/docs/java-manual/current/reactive/)
