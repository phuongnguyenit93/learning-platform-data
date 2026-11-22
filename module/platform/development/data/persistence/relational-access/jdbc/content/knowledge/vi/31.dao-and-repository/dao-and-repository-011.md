# Thiết kế bộ kiểm thử hợp đồng cho các triển khai truy cập dữ liệu

Khi ứng dụng Java sử dụng **DAO (Data Access Object)** hoặc **Repository**, tầng nghiệp vụ nên làm việc với **hợp đồng truy cập dữ liệu**, không cần biết dữ liệu được lưu bằng `JDBC`, một adapter khác hay một fake trong bộ nhớ. Nhưng việc hai lớp cùng triển khai một interface Java **không bảo đảm chúng hành xử giống nhau**: một triển khai có thể trả `null` thay vì `Optional.empty()`, quên lọc theo chủ sở hữu, thay đổi thứ tự kết quả hoặc xử lý bản ghi trùng khóa khác với triển khai còn lại.

**Bộ kiểm thử hợp đồng** (*contract test suite*) định nghĩa **những hành vi phải đúng với mọi implementation** rồi chạy cùng các test đó trên từng implementation. Với JDBC, bộ test này thường chạy trên cơ sở dữ liệu thật để kiểm chứng `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, ràng buộc SQL và cách ánh xạ bản ghi; với triển khai in-memory, nó xác nhận fake không ngầm cung cấp ngữ nghĩa khác biệt khiến unit test nghiệp vụ có kết quả sai.

Bài học thuộc chương **DAO và Repository** của module **JDBC**, tập trung vào thiết kế giao diện, kiểm thử CRUD, dữ liệu thiếu, tính nhất quán, phạm vi truy cập, giao dịch và các ranh giới thực thi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **contract test**, **unit test**, **integration test** và **test bằng mock**.
2. Chuyển mô tả nghiệp vụ thành các quy tắc quan sát được của một `Repository`.
3. Tạo một **abstract JUnit 5 test class** và cơ chế fixture để chạy lại trên các implementation.
4. Viết các test chung cho tạo, đọc, sửa, xóa, tìm kiếm, phân trang và trường hợp không tồn tại.
5. Kiểm tra tách dữ liệu theo `ownerId`/tenant, validation và xử lý lỗi giống nhau giữa các adapter.
6. Thử cả `JdbcNoteRepository` và `InMemoryNoteRepository` bằng cùng bộ test.
7. Thiết kế test database độc lập, setup/teardown không che mất commit thật.
8. Biết hợp đồng giao dịch nào thuộc repository, hợp đồng nào thuộc tầng service/Unit of Work.
9. Nhận diện hạn chế của fake: không tự mô phỏng khóa, isolation, constraint và transaction thật.
10. Đưa bộ contract test vào CI để phát hiện sai khác khi đổi SQL, driver, DBMS hoặc cách lưu dữ liệu.

## 2. Contract test kiểm tra điều gì?

Giả sử interface:

~~~java
public interface NoteRepository {
    void create(Note note);
    Optional<Note> findById(long ownerId, long id);
    boolean rename(long ownerId, long id, String newTitle);
    boolean delete(long ownerId, long id);
    List<Note> listByOwner(long ownerId, int limit);
}
~~~

Có ít nhất hai implementation:

~~~text
                  NoteRepository
                  /            \
                 /              \
     JdbcNoteRepository     InMemoryNoteRepository
          |                         |
       DataSource                Map<Long, Note>
          |
     PreparedStatement
          |
        Database
~~~

Cùng có các method không có nghĩa hai implementation tự động tương đương. Contract test phải mô tả hành vi theo góc nhìn của **người gọi**:

| Lời gọi | Hợp đồng quan sát được |
| --- | --- |
| `create(note)` | Note mới được lưu và đọc lại đúng trường; note có ID trùng bị từ chối |
| `findById(owner, id)` | Trả `Optional.of(note)` khi thấy đúng owner; trả `Optional.empty()` khi thiếu |
| `rename(owner, id, title)` | Trả `true` nếu bản ghi thuộc owner tồn tại và được cập nhật; `false` nếu không |
| `delete(owner, id)` | Lần xóa bản ghi đang tồn tại trả `true`; xóa lại trả `false` |
| `listByOwner(owner, limit)` | Chỉ chứa dữ liệu thuộc owner, sắp xếp theo ID tăng và có tối đa `limit` dòng |
| Input không hợp lệ | Báo `IllegalArgumentException` (hoặc `NullPointerException` với object null theo contract) |
| Lỗi truy cập dữ liệu | Báo exception ở tầng repository, không trá hình thành “không tìm thấy” |
| Các thao tác thành công liên tiếp | Thao tác được quan sát trong các lời gọi tiếp theo theo mô hình nhất quán đã công bố |

**Contract test không cần biết SQL được xây như thế nào**, không xác nhận `prepareStatement` được gọi mấy lần, và không buộc implementation dùng cùng schema hoặc cùng collection. Nó bảo vệ **ngữ nghĩa công khai**.

### Sự khác nhau giữa các cấp kiểm thử

| Loại test | Chủ yếu kiểm tra | Ví dụ |
| --- | --- | --- |
| Unit test có mock | Logic của một service, tương tác được kỳ vọng | Service gọi repository khi điều kiện hợp lệ |
| Contract test chung | Mọi implementation cùng tuân thủ quy tắc API | `delete` lần hai phải trả `false` |
| JDBC integration test | Mapping JDBC, schema/constraint/SQL thật | `create` rồi `findById` trên database test |
| Transaction integration test | Commit/rollback, isolation và lỗi SQL thật | Hai thao tác phải rollback cùng nhau |
| Performance/chaos test | Bộ nhớ, latency, pool, mạng, tải đồng thời | Đọc nhiều dòng, DB mất kết nối |

Một **contract test có thể đồng thời là integration test** khi được chạy trên JDBC thật. Hai khái niệm này mô tả hai trục khác nhau: *ta kiểm tra hành vi nào* và *ta chạy test ở mức tích hợp nào*.

## 3. Viết hợp đồng trước khi viết test

Một hợp đồng tốt phải đủ cụ thể để khi test thất bại, ta biết đó là lỗi implementation hay thiếu quy định nghiệp vụ.

Ở ví dụ này, ta quyết định:

- ID của note là **duy nhất toàn hệ thống**, là số nguyên dương.
- `ownerId` là số nguyên dương, do tầng đã xác thực/ủy quyền xác định.
- `title` không được `null`, không được toàn khoảng trắng và dài tối đa **100 ký tự Java**.
- `findById` trả `Optional.empty()` nếu thiếu hoặc thuộc owner khác; không bao giờ trả `null`.
- `create` không được ghi đè note có ID đã tồn tại; nó phải ném `RepositoryFailure`.
- `rename` và `delete` phải kiểm tra cả `ownerId` và ID; chỉ sửa/xóa nếu có quyền sở hữu theo phạm vi được truyền.
- `rename` giữ nguyên ID và owner.
- `delete` trả `true` khi thực sự xóa một dòng; `false` khi không tìm thấy.
- `listByOwner` trả tối đa `limit` dòng, `limit` thuộc khoảng **1..100**, thứ tự ID tăng.
- Kết quả trả về là dữ liệu **bất biến ở phía người gọi**: sửa đối tượng Java sau khi đọc không được âm thầm sửa trạng thái lưu trữ.
- Các thao tác đơn lẻ trong ví dụ là **tự hoàn tất**: caller không phải giữ connection hay gọi `commit()` sau từng thao tác.
- Contract chưa tuyên bố tính nguyên tử cho **nhiều lời gọi repository ghép lại**; nếu nghiệp vụ cần, phải có Unit of Work/transaction boundary riêng.

Nếu thay đổi các quy tắc trên (ví dụ muốn upsert hoặc list theo ngày tạo), hãy sửa contract và các test có chủ đích, thay vì sửa riêng một implementation để làm test xanh.

### Hợp đồng là cam kết, không phải chi tiết cài đặt

Tránh các assertion như:

~~~java
verify(preparedStatement).setString(3, "Tiêu đề");
verify(connection).close();
~~~

Đây có thể là **unit test của adapter JDBC**, nhưng không phải hợp đồng chung cho `InMemoryNoteRepository`. Contract nên hỏi:

~~~java
repository.create(new Note(101L, 7L, "Tiêu đề"));

Note actual = repository.findById(7L, 101L).get();
assertEquals("Tiêu đề", actual.title());
~~~

Câu hỏi đúng là “dữ liệu quan sát được có phù hợp không?”, không phải “implementation dùng một phương thức nội bộ cụ thể chưa?”.

## 4. Mô hình dữ liệu và interface dùng chung

Các khối mã tiếp theo trình bày theo từng lớp; khi đưa vào dự án Java, hãy đặt mỗi `public class`/`public interface` vào file Java tương ứng. Mã minh họa sử dụng **Java 8+**; test sử dụng **JUnit Jupiter (JUnit 5)**.

### 4.1. Đối tượng `Note` bất biến

~~~java
public final class Note {
    private final long id;
    private final long ownerId;
    private final String title;

    public Note(long id, long ownerId, String title) {
        this.id = requirePositive(id, "id");
        this.ownerId = requirePositive(ownerId, "ownerId");
        this.title = requireTitle(title);
    }

    public long id() {
        return id;
    }

    public long ownerId() {
        return ownerId;
    }

    public String title() {
        return title;
    }

    public static long requirePositive(long value, String field) {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    field + " phải là số dương");
        }
        return value;
    }

    public static int requireLimit(int value) {
        if (value < 1 || value > 100) {
            throw new IllegalArgumentException(
                    "limit phải trong khoảng 1..100");
        }
        return value;
    }

    public static String requireTitle(String value) {
        if (value == null
                || value.trim().isEmpty()
                || value.length() > 100) {
            throw new IllegalArgumentException(
                    "title không hợp lệ");
        }
        return value;
    }
}
~~~

`Note` không có setter. Sau khi đọc note, caller không thể thay đổi thuộc tính bên trong object này để sửa dữ liệu lưu trữ ngoài ý muốn. `String` cũng là immutable. Quy tắc độ dài 100 trong ví dụ được tính bằng `String.length()` (UTF-16 code units); giới hạn kích thước thực của một cột `VARCHAR(100)` có thể khác tùy DBMS và cách xử lý Unicode. Nếu nghiệp vụ cần 100 *code point* thay vì 100 UTF-16 code units, phải định nghĩa và test riêng.

### 4.2. Exception của tầng truy cập dữ liệu

~~~java
public final class RepositoryFailure extends RuntimeException {
    public RepositoryFailure(String message) {
        super(message);
    }

    public RepositoryFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Trong ví dụ, `RepositoryFailure` dùng cho lỗi lưu trữ như trùng khóa hoặc `SQLException`. Nó **khác** với `IllegalArgumentException` do input không đạt contract. Một hệ thống production có thể phân loại sâu hơn thành `DuplicateKey`, `ConcurrencyConflict`, `Unavailable`… nhưng không nên áp dụng mapping SQLState/vendor code chung mà chưa kiểm chứng.

### 4.3. Giao diện Repository

~~~java
import java.util.List;
import java.util.Optional;

public interface NoteRepository {
    void create(Note note);

    Optional<Note> findById(long ownerId, long id);

    boolean rename(long ownerId, long id, String newTitle);

    boolean delete(long ownerId, long id);

    List<Note> listByOwner(long ownerId, int limit);
}
~~~

**Quan trọng:** Mỗi method nhận đúng các đối số cần thiết. Không nhận tùy ý tên bảng, tên cột hoặc SQL fragment từ caller. Trong ứng dụng đa tenant, `ownerId` phải được lấy từ ngữ cảnh xác thực được kiểm tra ở service; chỉ bind giá trị an toàn bằng `PreparedStatement` chưa đồng nghĩa người dùng được phép chọn owner tùy ý.

## 5. Bộ contract test trừu tượng với JUnit 5

Ý tưởng là viết test **một lần** và dùng nó cho mọi implementation. Mỗi test có fixture **mới** để không phụ thuộc thứ tự và không chia sẻ dữ liệu.

### 5.1. Fixture nắm quyền sở hữu tài nguyên

~~~java
public interface NoteFixture extends AutoCloseable {
    NoteRepository repository();

    @Override
    void close() throws Exception;
}
~~~

Fixture có trách nhiệm:

- Cấp một repository trỏ đến **vùng dữ liệu riêng của test**.
- Bảo đảm vùng dữ liệu bắt đầu sạch, hoặc dùng ID/schema được phân vùng độc lập.
- Đóng pool/database test hay dọn fixture sau test.
- Không nuốt lỗi cleanup.
- Không tạo transaction test bao quanh các method nhằm che việc JDBC chưa commit.

Với in-memory, fixture chỉ tạo một `Map` mới. Với JDBC, fixture phải dùng một schema/database test riêng hoặc ID/namespace riêng; tuyệt đối không `DELETE FROM`/`TRUNCATE` bừa bãi trên một database dùng chung.

### 5.2. Abstract contract suite

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public abstract class NoteRepositoryContractTest {
    private NoteFixture fixture;
    protected NoteRepository repository;

    protected abstract NoteFixture newFixture() throws Exception;

    @BeforeEach
    void setup() throws Exception {
        fixture = newFixture();
        repository = fixture.repository();
    }

    @AfterEach
    void teardown() throws Exception {
        if (fixture != null) {
            fixture.close();
        }
    }

    @Test
    void createAndReadRoundTripPreservesData() {
        Note note = new Note(101L, 7L, "Ghi chú tiếng Việt");

        repository.create(note);

        Optional<Note> loaded =
                repository.findById(7L, 101L);

        assertTrue(loaded.isPresent());
        assertEquals(101L, loaded.get().id());
        assertEquals(7L, loaded.get().ownerId());
        assertEquals("Ghi chú tiếng Việt",
                loaded.get().title());
    }

    @Test
    void missingIdReturnsEmptyNotNull() {
        Optional<Note> missing =
                repository.findById(7L, 9999L);

        assertNotNull(missing);
        assertFalse(missing.isPresent());
    }

    @Test
    void createRejectsDuplicateAndDoesNotOverwrite() {
        repository.create(new Note(201L, 7L, "Bản gốc"));

        assertThrows(RepositoryFailure.class,
                () -> repository.create(
                        new Note(201L, 7L, "Bản thay thế")));

        assertEquals("Bản gốc",
                repository.findById(7L, 201L)
                          .get().title());
    }

    @Test
    void renameReturnsTrueAndChangesOnlyTitle() {
        repository.create(new Note(301L, 7L, "Trước"));

        assertTrue(repository.rename(7L, 301L, "Sau"));

        Note loaded = repository.findById(7L, 301L).get();

        assertEquals(301L, loaded.id());
        assertEquals(7L, loaded.ownerId());
        assertEquals("Sau", loaded.title());
    }

    @Test
    void renameAndDeleteMissingRowsReturnFalse() {
        assertFalse(repository.rename(7L, 444L, "Không có"));
        assertFalse(repository.delete(7L, 444L));
    }

    @Test
    void deleteRemovesRowAndSecondDeleteIsFalse() {
        repository.create(new Note(501L, 7L, "Sẽ xóa"));

        assertTrue(repository.delete(7L, 501L));
        assertFalse(repository.findById(7L, 501L).isPresent());
        assertFalse(repository.delete(7L, 501L));
    }

    @Test
    void ownerScopeIsEnforcedForAllOperations() {
        repository.create(new Note(601L, 7L, "Của owner A"));

        assertFalse(repository.findById(8L, 601L).isPresent());
        assertFalse(repository.rename(8L, 601L, "Cố sửa"));
        assertFalse(repository.delete(8L, 601L));
        assertTrue(repository.listByOwner(8L, 100).isEmpty());

        assertEquals("Của owner A",
                repository.findById(7L, 601L)
                          .get().title());
    }

    @Test
    void listIsOwnerScopedOrderedAndLimited() {
        repository.create(new Note(30L, 7L, "Ba mươi"));
        repository.create(new Note(10L, 7L, "Mười"));
        repository.create(new Note(20L, 7L, "Hai mươi"));
        repository.create(new Note(15L, 8L, "Owner khác"));

        List<Note> page = repository.listByOwner(7L, 2);

        assertEquals(2, page.size());
        assertEquals(10L, page.get(0).id());
        assertEquals(20L, page.get(1).id());
        assertEquals(7L, page.get(0).ownerId());
        assertEquals(7L, page.get(1).ownerId());
    }

    @Test
    void invalidInputIsRejectedConsistently() {
        assertThrows(IllegalArgumentException.class,
                () -> new Note(0L, 7L, "Sai ID"));
        assertThrows(IllegalArgumentException.class,
                () -> new Note(1L, -1L, "Sai owner"));
        assertThrows(IllegalArgumentException.class,
                () -> new Note(1L, 7L, null));
        assertThrows(IllegalArgumentException.class,
                () -> new Note(1L, 7L, "   "));

        assertThrows(IllegalArgumentException.class,
                () -> repository.findById(0L, 1L));
        assertThrows(IllegalArgumentException.class,
                () -> repository.rename(7L, 1L, null));
        assertThrows(IllegalArgumentException.class,
                () -> repository.listByOwner(7L, 0));
        assertThrows(IllegalArgumentException.class,
                () -> repository.listByOwner(7L, 101));
    }
}
~~~

Các method test chỉ gọi **API công khai** của repository. Không một test nào biết repository dùng SQL hay `Map`.

### Giải thích những điểm ít dễ thấy

- **Thiếu bản ghi trả `Optional.empty()`**, không trả `null`, không ném SQL exception cho kết quả “không thấy”.
- **Duplicate key:** test vừa assert loại exception vừa đọc lại bản gốc, bảo vệ nguyên tắc “không ghi đè”.
- **Phạm vi owner:** test dùng cùng ID nhưng sai owner để xác nhận cả `findById`, `rename`, `delete` và `listByOwner` không lộ hoặc sửa dữ liệu ngoài phạm vi.
- **Thứ tự:** note được insert theo `30, 10, 20`, nhưng list phải trả `10, 20`. Một in-memory `HashMap` không được giả vờ có thứ tự; implementation phải tự sort.
- **Giới hạn:** `limit=2` phải trả tối đa hai bản ghi, không được lấy tất cả rồi cho caller tưởng là một trang.
- **Input sai:** quy tắc validation phải **giống nhau** kể cả khi DBMS vốn chấp nhận một chuỗi trắng hoặc một cột nullable.
- **Mỗi test có fixture riêng:** test commit hoặc delete của một ca không được làm hỏng test kế tiếp.

Lưu ý: JUnit 5 mặc định chạy các method `@Test` được kế thừa từ lớp cha, nếu không bị override/ẩn theo quy tắc JUnit. Do đó các lớp con chỉ cần cung cấp `newFixture()`, không copy-paste toàn bộ test.

## 6. Triển khai thứ nhất: Repository trong bộ nhớ

In-memory adapter phù hợp cho unit test nhanh của service. Nhưng nó phải tôn trọng hợp đồng, không được tạo ra một “fake quá dễ dãi”.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public final class InMemoryNoteRepository
        implements NoteRepository {

    private final Map<Long, Note> byId = new HashMap<>();

    @Override
    public synchronized void create(Note note) {
        if (note == null) {
            throw new NullPointerException("note");
        }
        if (byId.containsKey(note.id())) {
            throw new RepositoryFailure("Note ID đã tồn tại");
        }
        byId.put(note.id(), note);
    }

    @Override
    public synchronized Optional<Note> findById(
            long ownerId, long id) {

        Note.requirePositive(ownerId, "ownerId");
        Note.requirePositive(id, "id");

        Note note = byId.get(id);
        if (note == null || note.ownerId() != ownerId) {
            return Optional.empty();
        }
        return Optional.of(note);
    }

    @Override
    public synchronized boolean rename(
            long ownerId, long id, String newTitle) {

        Note.requirePositive(ownerId, "ownerId");
        Note.requirePositive(id, "id");
        Note.requireTitle(newTitle);

        Note existing = byId.get(id);
        if (existing == null || existing.ownerId() != ownerId) {
            return false;
        }

        byId.put(id, new Note(id, ownerId, newTitle));
        return true;
    }

    @Override
    public synchronized boolean delete(
            long ownerId, long id) {

        Note.requirePositive(ownerId, "ownerId");
        Note.requirePositive(id, "id");

        Note existing = byId.get(id);
        if (existing == null || existing.ownerId() != ownerId) {
            return false;
        }
        byId.remove(id);
        return true;
    }

    @Override
    public synchronized List<Note> listByOwner(
            long ownerId, int limit) {

        Note.requirePositive(ownerId, "ownerId");
        Note.requireLimit(limit);

        return byId.values().stream()
                .filter(note -> note.ownerId() == ownerId)
                .sorted(Comparator.comparingLong(Note::id))
                .limit(limit)
                .collect(Collectors.toList());
    }
}
~~~

Đặc điểm:

- `byId` được tạo mới cho mỗi fixture nên không chia sẻ dữ liệu giữa test.
- ID bị trùng được từ chối, không `put` đè bản cũ.
- Tất cả thao tác đọc/ghi kiểm tra owner; riêng `create` nhận owner từ `Note` đã validate.
- `rename` tạo **đối tượng Note mới** để giữ tính bất biến.
- `listByOwner` luôn sort ID tăng trước khi limit, không phụ thuộc thứ tự duyệt `HashMap`.
- `synchronized` giúp một số thao tác trên map diễn ra tuần tự, nhưng **không khiến fake có isolation/locking giống một DBMS**.

### Lớp chạy contract test trên in-memory

~~~java
public final class InMemoryNoteRepositoryContractTest
        extends NoteRepositoryContractTest {

    @Override
    protected NoteFixture newFixture() {
        NoteRepository repository = new InMemoryNoteRepository();

        return new NoteFixture() {
            @Override
            public NoteRepository repository() {
                return repository;
            }

            @Override
            public void close() {
                // Mỗi test sở hữu một Map riêng, không cần cleanup DB.
            }
        };
    }
}
~~~

Chạy JUnit sẽ sử dụng lại toàn bộ test ở `NoteRepositoryContractTest`. Nếu in-memory fake sai thứ tự hoặc không kiểm tra owner, **chính test chung** phát hiện sai khác, không cần tạo một bộ assertion riêng.

## 7. Triển khai thứ hai: Repository dùng JDBC thật

Để chạy cùng contract test với JDBC, cần một implementation dùng `DataSource` và SQL thực. Ví dụ bảng:

~~~sql
CREATE TABLE repository_note (
    note_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    title VARCHAR(100) NOT NULL
);
~~~

Có thể tạo thêm index hỗ trợ `listByOwner`:

~~~sql
CREATE INDEX idx_repository_note_owner_id
    ON repository_note (owner_id, note_id);
~~~

DDL được thực hiện qua migration/test setup **trước test**, không thực hiện tùy tiện trong mỗi method repository. Các câu SQL dưới đây chỉ dùng kiểu và cú pháp phổ biến, còn cách tạo schema/index và ràng buộc độ dài Unicode cần kiểm thử trên DBMS thực tế.

### 7.1. JDBC adapter đầy đủ

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class JdbcNoteRepository
        implements NoteRepository {

    private final DataSource dataSource;

    public JdbcNoteRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    private static RepositoryFailure failure(
            String operation, SQLException cause) {
        // Không đưa dữ liệu tham số hoặc message driver
        // trực tiếp ra API công khai.
        return new RepositoryFailure(
                "Không thể thực hiện " + operation, cause);
    }

    private static void requireAutoCommit(Connection c)
            throws SQLException {
        // Contract ví dụ: mỗi lời gọi là một thao tác DB
        // độc lập, được commit ở cấp statement.
        if (!c.getAutoCommit()) {
            throw new RepositoryFailure(
                    "DataSource phải cung cấp autoCommit=true");
        }
    }

    @Override
    public void create(Note note) {
        Objects.requireNonNull(note, "note");

        String sql = "INSERT INTO repository_note "
                   + "(note_id, owner_id, title) VALUES (?, ?, ?)";

        try (Connection c = dataSource.getConnection()) {
            requireAutoCommit(c);

            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setLong(1, note.id());
                ps.setLong(2, note.ownerId());
                ps.setString(3, note.title());

                if (ps.executeUpdate() != 1) {
                    throw new RepositoryFailure(
                            "INSERT không tác động đúng một dòng");
                }
            }
        } catch (SQLException ex) {
            throw failure("create", ex);
        }
    }

    @Override
    public Optional<Note> findById(long ownerId, long id) {
        Note.requirePositive(ownerId, "ownerId");
        Note.requirePositive(id, "id");

        String sql = "SELECT note_id, owner_id, title "
                   + "FROM repository_note "
                   + "WHERE owner_id = ? AND note_id = ?";

        try (Connection c = dataSource.getConnection()) {
            requireAutoCommit(c);

            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setLong(1, ownerId);
                ps.setLong(2, id);

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        return Optional.empty();
                    }
                    return Optional.of(mapRow(rs));
                }
            }
        } catch (SQLException ex) {
            throw failure("findById", ex);
        }
    }

    @Override
    public boolean rename(long ownerId, long id, String newTitle) {
        Note.requirePositive(ownerId, "ownerId");
        Note.requirePositive(id, "id");
        Note.requireTitle(newTitle);

        String sql = "UPDATE repository_note SET title = ? "
                   + "WHERE owner_id = ? AND note_id = ?";

        try (Connection c = dataSource.getConnection()) {
            requireAutoCommit(c);

            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setString(1, newTitle);
                ps.setLong(2, ownerId);
                ps.setLong(3, id);
                return ps.executeUpdate() == 1;
            }
        } catch (SQLException ex) {
            throw failure("rename", ex);
        }
    }

    @Override
    public boolean delete(long ownerId, long id) {
        Note.requirePositive(ownerId, "ownerId");
        Note.requirePositive(id, "id");

        String sql = "DELETE FROM repository_note "
                   + "WHERE owner_id = ? AND note_id = ?";

        try (Connection c = dataSource.getConnection()) {
            requireAutoCommit(c);

            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setLong(1, ownerId);
                ps.setLong(2, id);
                return ps.executeUpdate() == 1;
            }
        } catch (SQLException ex) {
            throw failure("delete", ex);
        }
    }

    @Override
    public List<Note> listByOwner(long ownerId, int limit) {
        Note.requirePositive(ownerId, "ownerId");
        Note.requireLimit(limit);

        String sql = "SELECT note_id, owner_id, title "
                   + "FROM repository_note WHERE owner_id = ? "
                   + "ORDER BY note_id ASC";

        try (Connection c = dataSource.getConnection()) {
            requireAutoCommit(c);

            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setLong(1, ownerId);

                // Giới hạn số dòng trả về theo JDBC.
                // Driver có thể không tối ưu ở phía server.
                ps.setMaxRows(limit);

                List<Note> result = new ArrayList<>(limit);

                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        result.add(mapRow(rs));
                    }
                }
                return result;
            }
        } catch (SQLException ex) {
            throw failure("listByOwner", ex);
        }
    }

    private static Note mapRow(ResultSet rs)
            throws SQLException {
        long id = rs.getLong("note_id");
        if (rs.wasNull()) {
            throw new SQLException("note_id là NULL");
        }

        long ownerId = rs.getLong("owner_id");
        if (rs.wasNull()) {
            throw new SQLException("owner_id là NULL");
        }

        String title = rs.getString("title");
        if (title == null) {
            throw new SQLException("title là NULL");
        }

        return new Note(id, ownerId, title);
    }
}
~~~

Ở đây:

- **Các giá trị** đều được bind qua `?`, không ghép ID/title vào SQL.
- `WHERE owner_id = ? AND note_id = ?` bảo vệ phạm vi theo owner ở ngay câu SQL, không chỉ lọc sau khi đọc.
- `getLong` đi kèm `wasNull()` để không nhầm SQL `NULL` với số 0.
- `getBigDecimal`, batching hay cursor không cần cho ví dụ vì domain đơn giản; những quy tắc mapping phức tạp cần test riêng theo schema.
- `try-with-resources` đóng connection/statement/result set khi lỗi, kể cả exception từ mapper.
- `ps.setMaxRows(limit)` giới hạn số dòng JDBC trả về. **Nó không bảo đảm DBMS chỉ duyệt tối đa `limit` dòng ở server**. Với truy vấn lớn, nên thay bằng `LIMIT ?`/`FETCH FIRST` theo dialect đã kiểm thử và index phù hợp.
- Adapter này sử dụng **một statement tự commit cho mỗi lời gọi**. Nó đòi hỏi `DataSource` cung cấp `autoCommit=true`; thay vì âm thầm chuyển từ `false` sang `true` khi có transaction đang mở, nó báo lỗi cấu hình.
- `RepositoryFailure` bọc `SQLException` để caller không phụ thuộc trực tiếp vào vendor exception. Hệ thống lớn có thể phân loại lỗi (duplicate key, timeout, deadlock) rõ hơn qua adapter theo driver/SQLState.

### Về lỗi duplicate key

Trong schema này, `note_id` là primary key. `create` lần hai trên cùng ID phải thất bại và không ghi đè bản gốc. JDBC adapter bọc lỗi constraint vào `RepositoryFailure`; fake ném chính kiểu exception này.

**Không đồng nhất mọi SQLState bắt đầu bằng `23` với lỗi duplicate key** khi thiết kế exception riêng. SQLState class 23 là *integrity constraint violation* và có thể bao gồm nhiều loại ràng buộc. Nếu contract muốn `DuplicateNoteException` riêng, cần mapper chính xác theo DBMS/driver và test thêm nguyên nhân.

### Cẩn thận với update count

Ví dụ `rename` trả `ps.executeUpdate() == 1`. Hợp đồng giả định cập nhật một dòng tồn tại được tính là một dòng bị ảnh hưởng, kể cả khi title mới bằng title cũ. Một số DBMS/driver có cấu hình phân biệt **matched rows** và **changed rows**. Nếu ứng dụng hỗ trợ những môi trường đó, phải kiểm thử trường hợp đổi sang **cùng giá trị** và xác định rõ semantics: “có bản ghi” hay “giá trị thực sự thay đổi”. Có thể phải đổi cách xác nhận hoặc thiết kế API khác, không dùng update count một cách vô điều kiện.

## 8. Chạy lại bộ contract test trên JDBC

Lớp con không cần tự viết lại các assertion. Nó chỉ cung cấp một fixture dùng database thật.

~~~java
import javax.sql.DataSource;

public final class JdbcNoteRepositoryContractTest
        extends NoteRepositoryContractTest {

    @Override
    protected NoteFixture newFixture() throws Exception {
        // HẠ TẦNG DỰ ÁN PHẢI CUNG CẤP:
        // Tạo database/schema test riêng, apply migration
        // tạo repository_note, trả về DataSource autoCommit=true.
        TestDatabaseContext database =
                TestDatabase.createIsolatedNoteDatabase();

        NoteRepository jdbc =
                new JdbcNoteRepository(database.dataSource());

        return new NoteFixture() {
            @Override
            public NoteRepository repository() {
                return jdbc;
            }

            @Override
            public void close() throws Exception {
                database.close();
            }
        };
    }
}
~~~

`TestDatabase` và `TestDatabaseContext` là **test harness do dự án triển khai**, không thuộc JDBC/JUnit. Có thể dùng Testcontainers, schema riêng, database tạm hoặc môi trường CI dành cho test. Chúng phải:

1. Tạo nguồn dữ liệu **độc lập** cho mỗi test (hoặc phân vùng ID/tenant không đụng nhau).
2. Áp dụng migration tạo bảng và index **trước khi chạy contract test**.
3. Cấu hình `DataSource` cung cấp connection với `autoCommit=true` cho adapter trên.
4. Không dùng `@Transactional` bao toàn bộ test rồi rollback ở cuối, nếu mục tiêu là quan sát commit của từng method.
5. Đóng pool/session và dọn namespace khi `close()` được gọi, không ảnh hưởng database khác.
6. Báo lỗi setup/cleanup ra test runner thay vì bỏ qua.

**Lớp test ở trên là ví dụ tích hợp cần nối với hạ tầng database thật.** Không thể chạy chỉ với JDK vì `DataSource` là interface và JDK không cung cấp một DBMS mặc định. Bộ in-memory có thể chạy ngay khi đã cấu hình JUnit; bộ JDBC cần driver, schema và test database.

### Vì sao fixture phải thật sự cô lập?

Nếu hai test dùng `note_id=101` trên cùng bảng, test thứ hai có thể thất bại vì bản ghi từ test trước còn tồn tại, dù repository không sai. Nếu test dọn bằng `DELETE FROM repository_note` trên database dùng chung, nó có thể xóa dữ liệu của một test khác đang chạy.

Một số chiến lược:

| Chiến lược | Ưu điểm | Điều kiện/rủi ro |
| --- | --- | --- |
| DB/container mới cho mỗi test class | Mạnh về cô lập, dễ reset | Chi phí khởi động cao hơn |
| Schema riêng cho mỗi test | Cô lập rõ, nhanh hơn tùy DBMS | Cần hỗ trợ schema và migration |
| Tenant/ID namespace riêng | Tận dụng DB chung | Không được cleanup toàn bảng; cần khóa/ID thật sự không trùng |
| Transaction của test tự rollback | Cleanup nhanh | Có thể **che commit thật** và tạo dương tính giả |
| Test tuần tự cùng schema + cleanup | Thiết lập đơn giản | Chậm, dễ nhiễm bẩn dữ liệu nếu cleanup lỗi |

Đối với bài này, chọn **database/schema độc lập** làm tiền đề dễ hiểu nhất. Sau đó mới tối ưu tốc độ suite nếu số lượng test lớn.

## 9. Các thuộc tính hợp đồng dễ bị bỏ sót

### 9.1. Không tìm thấy khác với lỗi truy cập

`findById` trả `Optional.empty()` khi một note không tồn tại hoặc thuộc owner khác. Nếu DBMS mất kết nối, hết connection hoặc SQL sai, phải báo lỗi lưu trữ như `RepositoryFailure`. **Không** bắt mọi `SQLException` rồi trả empty:

~~~java
try {
    // Query JDBC...
} catch (SQLException failure) {
    return Optional.empty(); // Sai hợp đồng.
}
~~~

Điều này khiến service hiểu lỗi hệ thống là “không có dữ liệu”, che sự cố và tạo quyết định nghiệp vụ sai.

### 9.2. Phạm vi owner là một phần của contract, nhưng chưa phải authorization

Test `ownerScopeIsEnforcedForAllOperations` kiểm tra dữ liệu owner khác không được trả ra hay sửa/xóa khi truyền sai owner. Tuy nhiên caller vẫn có thể truyền **ownerId tùy ý**. Service phải lấy scope từ identity đã xác thực và kiểm tra quyền trước khi gọi repository.

Một test tầng service bổ sung nên chứng minh API **không cho client giả mạo ownerId**. Contract test repository không thể tự thay thế authorization test của endpoint.

### 9.3. Thứ tự và phân trang

Nếu contract nói danh sách trả thứ tự ID tăng, mọi implementation phải đưa ra kết quả xác định. Test cố ý tạo note theo thứ tự ngược để không phụ thuộc vào thứ tự insert.

Với trang lớn hoặc sử dụng `OFFSET`, cần thêm contract cho offset, thứ tự tie-breaker và giới hạn kết quả. `listByOwner(owner, limit)` ở đây chỉ trả **N bản ghi đầu**, không phải API phân trang đầy đủ. Không gọi nó là hỗ trợ “đọc hết hàng triệu dòng” khi chưa có cursor/checkpoint.

### 9.4. Null, Unicode và giới hạn độ dài

Một DBMS có thể coi chuỗi rỗng, chuỗi toàn khoảng trắng hoặc Unicode khác với fake. Nếu contract yêu cầu từ chối input toàn khoảng trắng, cả hai adapter phải thực hiện validation trước SQL.

Test nên thêm trường hợp:

~~~java
@Test
void unicodeAndQuotedTextRoundTrip() {
    String title = "Đơn hàng 'Ưu tiên' – Hà Nội";

    repository.create(new Note(701L, 7L, title));

    assertEquals(title,
            repository.findById(7L, 701L).get().title());
}
~~~

Đây là test **dữ liệu được bind và trả đúng**, không cần truyền payload phá hoại để thử SQL injection. Với Unicode nâng cao (emoji, ký tự tổ hợp), contract phải quyết định giới hạn “100 ký tự” theo code units, code points hay byte, rồi test đúng quy tắc đó.

### 9.5. Đối tượng trả về không được là tham chiếu trạng thái có thể sửa

`Note` bất biến nên fake có thể trả thẳng reference mà không sợ caller sửa trường. Nếu domain dùng DTO mutable hoặc trả một `List` nội bộ có thể chỉnh sửa, contract cần thêm test phòng ngừa:

- Sửa đối tượng đã đọc không được tự ghi DB nếu chưa gọi update.
- Sửa `List` trả về không làm thay đổi dữ liệu lưu trữ hoặc phá cấu trúc cache.
- Đọc lại phải phản ánh repository state, không phải cùng một object mutable đã bị sửa ở bên ngoài.

Trong hệ thống có ORM và persistence context, một object “đang được quản lý” có thể tự phát sinh update khi flush; lúc đó hợp đồng phải khác, không được áp dụng máy móc giả định của một repository JDBC trả DTO bất biến.

## 10. Giao dịch nhiều bước: một hợp đồng khác cần kiểm thử riêng

Bộ `NoteRepository` ví dụ có **các method độc lập**, mỗi method tự mượn connection và hoàn tất một câu SQL. Vì vậy:

~~~java
repository.create(noteA);
repository.create(noteB);
~~~

**không bảo đảm hai lệnh tạo này nằm trong cùng transaction.** Nếu lần thứ hai thất bại, lần thứ nhất có thể đã commit. Đây không phải lỗi của contract đã định nghĩa; đó là **một yêu cầu nghiệp vụ mới**.

Nếu muốn tạo hai note nguyên tử, hãy thiết kế API Unit of Work hoặc service transaction rõ:

~~~java
public interface NoteUnitOfWork {
    void createBoth(Note first, Note second);
}
~~~

Hợp đồng cho `createBoth`:

- Khi cả hai hợp lệ, **cả hai** xuất hiện sau khi method trả thành công.
- Khi thao tác thứ hai thất bại, **không có note nào** được commit.
- Không được trả thành công nếu chỉ một bản ghi được lưu.
- Nếu commit thất bại vì mất kết nối, cần chính sách **outcome bất định**, không retry mù.
- Hai thao tác JDBC phải dùng **cùng `Connection`**, với `autoCommit=false`, `commit()` một lần hoặc `rollback()` khi lỗi; một số DAO con nhận connection do service sở hữu.

Bộ test riêng có thể dùng:

~~~java
@Test
void failedSecondInsertRollsBackFirst() {
    // Tạo sẵn note ID 902 trong fixture đã commit.
    repository.create(new Note(902L, 7L, "Đã tồn tại"));

    Note first = new Note(901L, 7L, "Mới A");
    Note duplicate = new Note(902L, 7L, "Mới B");

    assertThrows(RepositoryFailure.class,
            () -> unitOfWork.createBoth(first, duplicate));

    // Quan sát SAU khi method kết thúc transaction.
    assertFalse(repository.findById(7L, 901L).isPresent());
    assertEquals("Đã tồn tại",
            repository.findById(7L, 902L).get().title());
}
~~~

`unitOfWork` là một implementation/service **khác** với `NoteRepository` đã minh họa. Đoạn test này chỉ chạy khi test fixture cung cấp `NoteUnitOfWork` được triển khai thật; nó không được đưa vào suite cơ bản nếu repository không hứa hỗ trợ transaction nhiều bước.

### Savepoint trong hợp đồng transaction

Nếu nghiệp vụ có bước bắt buộc A và bước tùy chọn B, có thể quy định:

~~~text
BEGIN
  A: cập nhật bắt buộc
  SAVEPOINT optional
  B: thêm thông tin phụ
  Nếu B lỗi và lỗi cho phép phục hồi: ROLLBACK TO SAVEPOINT
COMMIT A
~~~

Contract test cần xác nhận: A được commit, B không; còn nếu transaction ngoài rollback, **cả A lẫn B đều không được commit**. `Savepoint` không phải transaction độc lập. Trên PostgreSQL, MySQL InnoDB, SQL Server hay Oracle, việc phục hồi sau SQL error phụ thuộc loại lỗi và DBMS; test phải chạy với database mục tiêu.

### Không dùng mock để chứng minh transaction thật

~~~java
verify(connection).commit();
verify(connection).rollback();
~~~

Các assertion này hữu ích để kiểm tra điều phối API ở unit test, nhưng phải thêm **integration test** sử dụng transaction thật và **connection quan sát độc lập** để xác nhận kết quả lưu trữ.

## 11. Fake, cache và eventual consistency

Không phải mọi triển khai truy cập dữ liệu đều có cùng mức nhất quán mặc định. Ví dụ:

- **In-memory fake** thường thấy dữ liệu ngay sau khi gọi `create`.
- **JDBC một statement auto-commit** thường cho lời gọi sau thấy dữ liệu đã commit, với điều kiện không có replica/cache gây trễ.
- **Cached repository** có thể giữ dữ liệu cũ nếu không invalidation đúng.
- **Read replica** có thể có độ trễ và không đảm bảo *read-after-write* lập tức.
- **Eventually consistent store** có thể cần thời gian lan truyền.

Nếu contract nói “đọc ngay sau tạo phải thấy note”, thì một adapter đọc từ replica trễ có thể **không phù hợp contract hiện tại**. Có hai lựa chọn đúng:

1. Thay thiết kế adapter để bảo đảm read-your-writes theo hợp đồng.
2. Định nghĩa một contract **khác** với consistency model rõ ràng và test bất đồng bộ có timeout/quy tắc chấp nhận.

Không nên làm các test cơ bản ngẫu nhiên `Thread.sleep(1000)` rồi gọi đó là hợp đồng. Nếu nghiệp vụ chấp nhận eventual consistency, hãy định nghĩa thời hạn/điều kiện quan sát và dùng cơ chế polling có giới hạn rõ ràng.

### Test cache không phải chỉ test repository nguồn

Một caching decorator có thể vượt qua test `findById` ban đầu nhưng vẫn sai khi update/delete:

~~~text
create(note)
findById(...)     -> cache note
rename(...)       -> database đã đổi
findById(...)     -> cache vẫn trả title cũ  (FAIL)
~~~

Bộ contract test chung bắt được sai khác nếu test assert đọc lại **sau mutation**. Với cache nhiều instance hoặc TTL, cần thêm test riêng theo chính sách invalidation và consistency đã công bố.

## 12. Không để test framework che mất commit

Một lỗi phổ biến là bọc toàn bộ JUnit test trong transaction do framework tạo, rồi rollback tự động sau test:

~~~java
// Minh họa nguy cơ trong framework có @Transactional:
@Transactional
@Test
void createWorks() {
    service.create(...);
    assertTrue(repository.findById(...).isPresent());
}
~~~

Nếu service tham gia transaction của test, kết quả `findById` có thể chỉ là *read-your-writes* của dữ liệu **chưa commit**. Test pass nhưng không chứng minh production đã commit. Đối với contract ở bài này:

- JDBC method hoạt động theo hợp đồng tự hoàn tất; observer ở lời gọi sau phải nhìn thấy dữ liệu đã lưu.
- Fixture test DB được setup và cleanup độc lập, không phụ thuộc vào một transaction ẩn bao toàn bộ test.
- Nếu có transaction service phức tạp, phải kiểm thử riêng với đúng transaction manager và propagation thực.
- Không thay `rollback()` tường minh bằng `Connection.close()` rồi giả định mọi driver/pool đều rollback giống nhau.

Trường hợp cần test một service trên Spring, hãy xác định rõ **transaction boundary**, có thể dùng một test **không chạy bên trong transaction mặc định** để xác minh trạng thái đã commit qua connection khác.

## 13. Kiểm thử SQL và dữ liệu thực mà fake khó mô phỏng

Bộ contract chung nên được bổ sung **các test đặc thù JDBC** khi có rủi ro implementation riêng:

| Rủi ro | Test JDBC riêng |
| --- | --- |
| Constraint PK/unique | Trùng `note_id` thật sự bị DBMS từ chối |
| Column NOT NULL | Không có dữ liệu null ngoài hợp đồng |
| Độ dài cột và Unicode | Test độ dài 100, 101; emoji hoặc dấu kết hợp nếu yêu cầu |
| SQLState/vendor error | Mapper chuyển lỗi đúng loại; không làm lộ giá trị nhạy cảm |
| Connection pool | Không rò connection khi mapper/SQL ném lỗi |
| Transaction nhiều bước | Commit/rollback bằng một connection, observer mới |
| Isolation/locking | Test hai connection, thời gian chờ và outcome cụ thể |
| Timeout/cancel | Resource cleanup khi `SQLException`/network timeout |
| Ordering/pagination | `ORDER BY` ổn định và index phù hợp |
| Batching | Xử lý số dòng cập nhật, rollback khi một batch lỗi |
| NULL và kiểu dữ liệu | `wasNull()`, `BigDecimal`, ngày giờ/UTC theo schema |
| Dữ liệu lớn | Tránh nạp toàn bộ `ResultSet` thành `List` không giới hạn |

Những test này **không nên ép fake phải giả lập toàn bộ engine SQL**. Fake chỉ cần giữ contract hành vi chung; các đặc tính driver, transaction và hiệu năng phải được xác minh ở mức tích hợp với database.

## 14. Test matrix và quản lý vòng đời fixture

### Ma trận đề xuất

| Hành vi | In-memory | JDBC | Cache/adapter khác |
| --- | --- | --- | --- |
| Create → find round-trip | Bắt buộc | Bắt buộc | Bắt buộc theo consistency contract |
| Missing → Optional.empty | Bắt buộc | Bắt buộc | Bắt buộc |
| Duplicate không ghi đè | Bắt buộc | Bắt buộc | Bắt buộc |
| Rename/delete đúng owner | Bắt buộc | Bắt buộc | Bắt buộc |
| Sort, limit và dữ liệu owner khác | Bắt buộc | Bắt buộc | Bắt buộc |
| Input validation | Bắt buộc | Bắt buộc | Bắt buộc |
| SQL constraints thực | Không áp dụng | Bắt buộc | Theo backend |
| Rollback/savepoint | Không áp dụng nếu contract không hứa | Test riêng | Theo transaction semantics |
| Connection leak/timeout | Không áp dụng | Test riêng | Theo hạ tầng |
| Eventual consistency | Không áp dụng nếu synchronous | Nếu dùng replica thì test riêng | Theo hợp đồng |

### Quy tắc fixture trong CI

- **Không dùng production DB.** Chọn database test được cấp quyền rõ ràng.
- **Tạo schema qua migration** và kiểm tra cấu hình driver thật.
- **Không dùng cùng ID/schema cho các test chạy song song**, trừ khi có cơ chế cô lập khác.
- **Đóng tài nguyên** qua `try-with-resources` và `NoteFixture.close()`.
- **Cleanup không được xóa dữ liệu ngoài phạm vi**, chẳng hạn `TRUNCATE` toàn bộ bảng được các worker khác dùng.
- **Không phụ thuộc thứ tự test**; mỗi `@Test` chạy được riêng lẻ.
- **Không làm test “xanh” bằng cách bắt exception rồi bỏ qua**.
- **Bảo vệ lỗi gốc**: nếu cleanup thất bại sau assertion failure, ghi nhận cả hai, có thể gắn cleanup exception dưới dạng suppressed trong fixture manager.
- **Gắn version DBMS/driver vào kết quả CI** để biết test failure do thay đổi hạ tầng hay do code.
- **Test đúng ranh giới nghiệp vụ**: hợp đồng quan sát từ API, không copy-paste assertion SQL riêng cho từng implementation.

Với test DB dùng chung, các thao tác setup/teardown phải có transaction rõ và sử dụng ID/schema do test sở hữu. Với container riêng, đóng container/pool sau khi tất cả connection đã được trả về.

## 15. Những sai lầm thiết kế thường gặp

| Sai lầm | Hệ quả | Sửa thế nào |
| --- | --- | --- |
| Chỉ mock `Repository` ở service test | Không phát hiện fake và JDBC khác nhau | Chạy contract suite trên từng implementation |
| Test riêng hoàn toàn cho mỗi adapter | Các assertion trôi lệch khi yêu cầu thay đổi | Tái sử dụng abstract JUnit contract |
| Chỉ kiểm tra method trả về, không đọc lại | Bỏ sót lỗi commit hoặc SQL `WHERE` sai | Kiểm tra trạng thái quan sát được |
| Trả `null` khi không tìm thấy ở một adapter | Service có thể bị `NullPointerException` | Contract `Optional.empty()` thống nhất |
| Fake dùng `Map.put` ghi đè ID trùng | Unit test cho phép hành vi DB không cho phép | Duplicate phải bị từ chối và giữ bản cũ |
| Fake trả theo thứ tự `HashMap` | Thứ tự không ổn định, test flaky | Sort theo contract trước khi limit |
| JDBC query không lọc owner | Có thể lộ/sửa dữ liệu tenant khác | `WHERE owner_id = ?` ở mọi thao tác |
| Bắt mọi `SQLException` rồi trả empty | Che lỗi hệ thống thành “not found” | Phân biệt lỗi dữ liệu thiếu và lỗi DB |
| `@Transactional` bao test commit | Đọc dữ liệu chưa commit vẫn thấy, dương tính giả | Test commit ngoài transaction test |
| JDBC method mở connection riêng nhưng service giả định cùng transaction | Dễ partial commit | Thiết kế Unit of Work riêng |
| Dùng H2 pass rồi kết luận production tương đương | Khác biệt dialect/constraint/locking | Chạy integration trên DBMS đích |
| Fixture cleanup toàn bảng dùng chung | Phá dữ liệu test khác | Namespace/schema riêng và cleanup đúng phạm vi |
| Caching adapter không invalidation | Đọc ra dữ liệu cũ sau rename/delete | Áp cùng contract + test cache riêng |
| Contract kiểm tra `PreparedStatement` cụ thể | Không thể chạy trên in-memory | Chỉ kiểm tra hành vi công khai |

## 16. Bài tập thực hành

### Bài 1 — Nhận diện contract hay implementation detail

Cho các assertion:

~~~text
A. create(note) rồi findById trả title đúng.
B. PreparedStatement.setLong(1, 7) được gọi một lần.
C. delete lần hai trả false.
D. getConnection() được gọi đúng hai lần.
E. listByOwner trả ID tăng dần.
~~~

**Hỏi:** Assertion nào thuộc contract chung?

**Gợi ý:** A, C, E. B và D phụ thuộc cách implementation tổ chức JDBC, không áp dụng cho fake hoặc adapter khác.

### Bài 2 — Fake vi phạm hợp đồng

~~~java
void create(Note note) {
    byId.put(note.id(), note);
}
~~~

**Hỏi:** Vấn đề là gì? Contract test nào phát hiện?

**Gợi ý:** `Map.put` ghi đè dữ liệu khi trùng ID. Test duplicate cần assert exception và đọc lại bản gốc để xác nhận không bị thay thế.

### Bài 3 — Lỗ hổng phân quyền

JDBC adapter:

~~~sql
SELECT note_id, owner_id, title
FROM repository_note
WHERE note_id = ?;
~~~

**Hỏi:** Vì sao câu SQL này có thể vi phạm contract?

**Gợi ý:** Thiếu điều kiện `owner_id = ?`. Người dùng của owner khác có thể đọc ID nếu biết khóa note; contract test phải dùng cùng ID với owner không được phép và mong `Optional.empty()`.

### Bài 4 — Thứ tự và giới hạn

Fake dùng `HashMap.values()` rồi lấy hai phần tử đầu. JDBC có `ORDER BY note_id ASC`. Test tạo ID 30, 10, 20 theo thứ tự bất kỳ.

**Hỏi:** Lợi ích của việc test cả thứ tự lẫn limit là gì?

**Gợi ý:** Có thể cùng số dòng nhưng khác nội dung trang. Contract phải xác định ID 10, 20 trước khi cắt giới hạn 2.

### Bài 5 — Transaction bị hiểu nhầm

Service gọi hai lần `repository.create(...)`, trong khi mỗi method tự mở connection và auto-commit. Lần thứ hai gặp duplicate key.

**Hỏi:** Có thể mong lần thứ nhất tự rollback không? Phải đổi hợp đồng ra sao?

**Gợi ý:** Không. Cần Unit of Work/service transaction cho cả hai thao tác, dùng cùng connection hoặc transaction manager, và test rollback qua connection khác.

### Bài 6 — Lỗi bị che thành dữ liệu thiếu

JDBC adapter bắt mọi `SQLException` rồi trả `Optional.empty()`.

**Hỏi:** Vì sao nguy hiểm? Contract nên quy định gì?

**Gợi ý:** Mất DB bị hiểu là bản ghi không tồn tại. Contract cần phân biệt thiếu bản ghi với lỗi hạ tầng, chẳng hạn ném `RepositoryFailure` khi SQL thất bại.

### Bài 7 — Khi nào fake không còn đủ?

Một service bị deadlock, cần retry transaction trên SQLState phù hợp và không tạo dữ liệu trùng.

**Hỏi:** Chỉ chạy contract suite trên `InMemoryNoteRepository` có đủ không?

**Gợi ý:** Không. Cần integration/fault-injection test trên DBMS/driver thật vì fake không mô phỏng transaction isolation, locks, deadlock hoặc commit không chắc chắn.

### Bài 8 — Thiết kế CI có hai worker

Hai test JDBC dùng chung bảng `repository_note`, cùng tạo ID 101, rồi mỗi test cleanup bằng `DELETE FROM repository_note`.

**Hỏi:** Chuyện gì có thể xảy ra và bạn chọn cách cô lập nào?

**Gợi ý:** Unique conflict, đọc nhầm hoặc xóa dữ liệu của test khác. Dùng schema/database riêng cho từng test, hoặc namespace ID/tenant riêng với cleanup đúng phạm vi.

---

## 17. Checklist trước khi áp dụng contract suite

- [ ] Có **hợp đồng hành vi viết rõ**: found/missing, duplicate, update/delete, ordering, limit, null và lỗi.
- [ ] Contract test chỉ gọi API công khai của repository, không phụ thuộc `PreparedStatement` cụ thể.
- [ ] Mỗi implementation chạy **cùng** abstract suite, không copy test rồi chỉnh assertion tùy adapter.
- [ ] Mỗi test có fixture tách biệt và cleanup đúng phạm vi.
- [ ] JDBC suite chạy trên DBMS/driver mục tiêu, có migration và `DataSource` cấu hình đúng.
- [ ] Dữ liệu tạo bởi một lời gọi đã hoàn tất được quan sát từ lời gọi/connection sau theo consistency contract.
- [ ] Có test cho dữ liệu owner/tenant khác, không chỉ các trường hợp đúng owner.
- [ ] Duplicate ID không ghi đè; lỗi truy cập không biến thành `Optional.empty()`.
- [ ] Sort được định nghĩa và limit có giới hạn, kể cả khi backend dùng `Map`.
- [ ] Input validation nhất quán trên các implementation; độ dài Unicode được quy định rõ.
- [ ] Các transaction nhiều bước có **contract riêng**, không suy ra từ các method auto-commit đơn lẻ.
- [ ] Không dùng `@Transactional` bao test làm che kết quả commit cần kiểm chứng.
- [ ] Có integration test bổ sung cho constraint, rollback/savepoint, lock, timeout và resource cleanup.
- [ ] Không log dữ liệu nhạy cảm hoặc chi tiết lỗi driver ra kênh công khai.
- [ ] Bộ test chạy riêng lẻ, song song và trong CI mà không tác động dữ liệu ngoài phạm vi.

**Kết luận:** Thiết kế bộ kiểm thử hợp đồng cho **DAO và Repository** là xác định **ngữ nghĩa mà caller có thể quan sát**, rồi chạy lại **một bộ JUnit test chung** trên mọi triển khai, từ in-memory đến JDBC thật. Nhờ vậy, các khác biệt về thiếu dữ liệu, duplicate, thứ tự, owner, giới hạn và cách xử lý lỗi được phát hiện sớm. Đồng thời phải giữ ranh giới rõ: contract test chung không thay thế integration test cho **transaction, SQL constraint, isolation, connection và driver**. Khi kết hợp hai lớp kiểm thử với fixture cô lập và assertion trên trạng thái đã commit, tầng truy cập dữ liệu sẽ đáng tin cậy hơn và dễ thay đổi implementation mà không phá vỡ tầng nghiệp vụ.
