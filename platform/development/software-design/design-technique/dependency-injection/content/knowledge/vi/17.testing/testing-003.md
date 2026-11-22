# Chọn phụ thuộc thật hoặc đối tượng thay thế theo phạm vi kiểm thử

## 1. Dependency Injection giúp lựa chọn dependency, nhưng không quyết định thay ta

Trong **Dependency Injection (DI)**, một lớp nhận các đối tượng cộng tác từ bên ngoài, thường qua constructor, thay vì tự `new` chúng hoặc tra cứu một container toàn cục. **Composition root** chịu trách nhiệm chọn implementation, tạo object graph và quản lý scope/vòng đời. Đây là một cách thực hiện **Inversion of Control (IoC)**.

Khi kiểm thử, ta cũng tạo một composition root nhỏ cho bài test. Nhưng việc có thể inject fake hoặc mock **không có nghĩa mọi dependency đều phải bị thay bằng đối tượng giả**. Câu hỏi quan trọng hơn là:

> Bài kiểm thử muốn kiểm chứng hành vi **bên trong ranh giới nào**, và thành phần nào cần được giữ thật để kết quả có giá trị?

Ví dụ một dịch vụ tạo báo cáo có thể phụ thuộc vào:

- `ReportFormatter`: xử lý chuỗi và quy tắc định dạng thuần Java, không I/O.
- `ReportStore`: ghi và đọc báo cáo từ file hoặc database.
- `ReportNotifier`: gửi thông báo qua email hoặc API bên ngoài.
- `Clock`: nguồn thời gian hiện tại.

Trong **unit test** của `ReportService`, ta thường dùng `ReportFormatter` thật vì logic nhỏ, nhanh, xác định; dùng store giả trong bộ nhớ và notifier ghi nhận lời gọi để tránh I/O; dùng `Clock.fixed(...)` để thời gian ổn định. Trong **integration test**, ta có thể thay store giả bằng adapter ghi file thật, nhưng tiếp tục thay notifier để không gửi thư ngoài ý muốn.

**Mục tiêu học tập:**

1. Chọn phụ thuộc thật hay test double dựa trên **mục đích và phạm vi** của từng bài test.
2. Phân biệt dummy, stub, fake, spy và mock theo vai trò, không gọi mọi thứ là “mock”.
3. Viết unit test và integration test bằng **Java thuần**, không cần DI container hoặc thư viện mock.
4. Hiểu khi nào cần contract test để tránh fake hoạt động khác implementation thật.
5. Kiểm soát lỗi, trạng thái, tài nguyên, tính xác định và độ tin cậy của các bài test.

## 2. Phạm vi kiểm thử quyết định ranh giới thay thế

Không có quy tắc cứng rằng unit test bắt buộc dùng 100% fake, hoặc integration test bắt buộc dùng 100% dependency thật. Hãy xác định **đối tượng đang được kiểm chứng** trước khi chọn cộng tác viên.

| Phạm vi | Điều muốn chứng minh | Dependency thường dùng thật | Dependency thường thay thế |
| --- | --- | --- | --- |
| **Unit test** | Quy tắc nghiệp vụ và cách điều phối của một đơn vị nhỏ. | Hàm thuần, value object, formatter/strategy đơn giản, collection Java. | Database, network, email, clock không ổn định, kết nối ngoài tốn phí. |
| **Component/service test** | Một nhóm service/adaptor trong cùng thành phần phối hợp đúng. | Nhiều lớp ứng dụng, mapper, validator và đôi khi store local. | Hệ thống ngoài ranh giới component, API bên thứ ba. |
| **Contract test** | Các implementation của một hợp đồng tuân theo cùng hành vi đã định nghĩa. | Implementation cần kiểm chứng, kể cả adapter thật. | Phần hạ tầng không thuộc contract; có thể dùng môi trường kiểm thử tương ứng. |
| **Integration test** | Việc ghép với adapter, file, database, HTTP client hoặc giao dịch thực sự hoạt động. | Adapter thật và hệ thống tích hợp đang kiểm tra. | Các hệ thống ngoài phạm vi test để cô lập lỗi và giảm tác động phụ. |
| **End-to-end (E2E)** | Luồng người dùng hoàn chỉnh chạy xuyên các thành phần đã triển khai. | Các thành phần chính của đường đi được kiểm chứng. | Chỉ những dịch vụ bên ngoài cần sandbox/simulator có kiểm soát, nếu chính sách kiểm thử cho phép. |

Ranh giới này là **lựa chọn có chủ đích**, không phải nhãn chỉ dựa trên số lượng lớp hoặc việc có dùng mocking framework. Một test gọi repository thật nhưng database giả chưa chắc kiểm tra được cú pháp SQL; một test dùng database thật nhưng mock mọi lớp nghiệp vụ cũng chưa chắc kiểm chứng được use case.

Cách chọn hữu ích là đi từ câu hỏi: *“Nếu thành phần này hỏng ở production, bài test này có được kỳ vọng phát hiện không?”* Nếu có, ít nhất một bài test cần cho phép thành phần đó chạy thật.

## 3. Khi nào giữ thật, khi nào thay thế?

### 3.1. Ưu tiên dependency thật khi nó đơn giản và xác định

Một formatter thuần Java, phép tính tiền, rule bất biến hoặc parser có thể chạy nhanh và không cần kết nối ngoài. Thay nó bằng mock có thể làm test yếu đi:

```java
// Mock formatter để luôn trả về "expected" có thể che lỗi format.
when(formatter.format(...)).thenReturn("expected");
```

Đây là *pseudocode* của API mocking; không phải mã Java thuần chạy độc lập. Nếu `ReportService` cần kiểm tra nội dung báo cáo được tạo đúng, việc mock formatter sẽ bỏ qua chính hành vi quan trọng đó.

Dùng implementation thật khi nó:

- Chạy nhanh, ít tài nguyên và không gây side effect ngoài ranh giới bài test.
- Có kết quả ổn định với input được kiểm soát.
- Dễ thiết lập trạng thái đầu vào và kiểm tra trạng thái đầu ra.
- Không khiến bài test phụ thuộc không cần thiết vào hạ tầng hoặc cấu hình vận hành.

### 3.2. Thay thế ở ranh giới chậm, biến động hoặc nguy hiểm

Database production, SMTP thật, payment gateway, HTTP API bên ngoài, queue chia sẻ hoặc đồng hồ hệ thống thường làm unit test không xác định và khó cô lập lỗi. Test double giúp kiểm tra **điều mà service quyết định gửi sang ranh giới đó**.

Ví dụ:

- Fake `ReportStore` ghi vào `Map` để xác nhận nội dung cần lưu.
- Spy `ReportNotifier` ghi nhận số lần và ID thông báo.
- `Clock.fixed(...)` cung cấp thời gian xác định mà không phải thay đổi đồng hồ hệ thống.
- Stub trả về một kết quả hoặc ném một lỗi định trước để đi qua nhánh xử lý lỗi.

Điều này không phủ nhận nhu cầu test thật cho các adapter. Nó chỉ nói **unit test không phải nơi xác minh kết nối và giao thức của mọi hệ thống bên ngoài**.

### 3.3. Giữ thật những phần rủi ro nằm trong phạm vi

Nếu mục tiêu là kiểm tra `FileReportStore` viết UTF-8 và đọc lại đúng, đừng inject `InMemoryReportStore` rồi gọi đó là integration test của file store. Cần sử dụng **file adapter thật** và filesystem trong thư mục tạm.

Nếu mục tiêu là kiểm tra SQL query, migration hoặc transaction, một fake dùng `HashMap` không đủ. Cần chạy adapter SQL với database kiểm thử tương thích, dữ liệu cô lập và teardown rõ ràng. Nếu mục tiêu là kiểm tra HTTP mapping, phải có bài test đi qua serializer, router/client và response mapping thực sự.

## 4. Test double gồm những loại nào?

**Test double** là tên chung cho đối tượng thay thế một cộng tác viên trong kiểm thử. Tên gọi có tính thực hành; một đối tượng cụ thể có thể đảm nhận hơn một vai trò.

| Loại | Cách hoạt động | Mục đích |
| --- | --- | --- |
| **Dummy** | Được truyền để thỏa chữ ký nhưng không được sử dụng trong đường test. | Cung cấp một tham số không liên quan; nên tránh nếu dependency thật sự bắt buộc và có thể bị gọi. |
| **Stub** | Trả dữ liệu định sẵn hoặc ném lỗi định sẵn. | Điều khiển nhánh xử lý, ví dụ “kho dữ liệu trả rỗng”. |
| **Fake** | Triển khai đơn giản nhưng có hành vi làm việc được, ví dụ repository trong bộ nhớ. | Chạy luồng nghiệp vụ không cần hạ tầng thật. |
| **Spy** | Ghi nhận lời gọi, tham số hoặc thứ tự tương tác để test kiểm tra. | Xác minh thông báo chỉ gửi một lần hoặc không gửi khi lưu thất bại. |
| **Mock** | Đối tượng được cấu hình kỳ vọng tương tác, thường có framework hỗ trợ. | Kiểm tra giao thức tương tác khi điều đó chính là hành vi cần chứng minh. |

Một fake repository có thể đồng thời ghi số lần gọi và trở thành spy. Một spy có thể được viết bằng Java thuần; không bắt buộc dùng Mockito hay container. Ngược lại, **mock không mặc nhiên tốt hơn fake**: nếu mọi test khóa chặt số lời gọi của các phương thức nội bộ, refactor không đổi hành vi cũng có thể khiến test vỡ.

Nên ưu tiên kiểm chứng **kết quả quan sát được**: dữ liệu được lưu, báo cáo được sinh, lỗi được trả đúng, side effect dự kiến xảy ra hay không. Chỉ xác minh tương tác cụ thể khi tương tác đó là phần quan trọng của contract, chẳng hạn “không gửi thông báo khi lưu thất bại”.

## 5. Object graph ví dụ: chọn dependency khác nhau cho từng test

Ta có một dịch vụ tạo báo cáo:

```text
                     ReportService
                     /    |     \
                    v     v      v
             Formatter  Store  Notifier
                |         |       |
                +----- Clock -----+   (Clock được inject riêng vào service)

Unit test:
  Formatter THẬT + Store FAKE + Notifier SPY + Clock.fixed

File integration test:
  Formatter THẬT + FileReportStore THẬT + Notifier SPY + Clock.fixed

Composition root của chương trình demo:
  Formatter THẬT + FileReportStore THẬT + ConsoleNotifier + Clock.fixed
```

`ReportService` không biết implementation được dùng là fake hay thật. Nó nhận cùng những hợp đồng qua constructor; **mỗi bài test tự lắp object graph phù hợp**.

Quy tắc nghiệp vụ minh họa: `generate(id, body)` kiểm tra ID, tạo nội dung bằng formatter và ngày được cấp từ clock, **lưu trước**, sau đó mới gửi thông báo. Nếu lưu ném exception, thông báo không được gửi.

### 5.1. Mã ứng dụng chạy được bằng Java thuần

Lưu toàn bộ đoạn sau vào `ReportExample.java` (JDK 11 trở lên):

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Objects;

interface ReportFormatter {
    String format(String reportId, String body, LocalDate day);
}

final class PlainTextReportFormatter implements ReportFormatter {
    @Override
    public String format(String reportId, String body, LocalDate day) {
        return "Report: " + reportId
                + "\nDate: " + day
                + "\n" + body + "\n";
    }
}

interface ReportStore {
    void save(String reportId, String content) throws IOException;

    String load(String reportId) throws IOException;
}

interface ReportNotifier {
    void reportSaved(String reportId);
}

// Tách quy tắc ID thành một hàm thuần; không cần inject mọi hàm.
final class ReportIds {
    static void requireValid(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_REPORT_ID");
        }
    }
}

final class ReportService {
    private final ReportFormatter formatter;
    private final ReportStore store;
    private final ReportNotifier notifier;
    private final Clock clock;

    ReportService(ReportFormatter formatter, ReportStore store,
                  ReportNotifier notifier, Clock clock) {
        this.formatter = Objects.requireNonNull(formatter, "formatter");
        this.store = Objects.requireNonNull(store, "store");
        this.notifier = Objects.requireNonNull(notifier, "notifier");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    String generate(String id, String body) throws IOException {
        ReportIds.requireValid(id);
        Objects.requireNonNull(body, "body");

        String content = formatter.format(
                id, body, LocalDate.now(clock));

        // Nếu store thất bại, chưa được gọi notifier.
        store.save(id, content);
        notifier.reportSaved(id);
        return content;
    }
}

// Adapter thật: tương tác filesystem, không chỉ ghi vào Map.
final class FileReportStore implements ReportStore {
    private final Path directory;

    FileReportStore(Path directory) {
        this.directory = Objects.requireNonNull(directory, "directory");
        if (!Files.isDirectory(directory)) {
            throw new IllegalArgumentException(
                    "REPORT_DIRECTORY_NOT_FOUND");
        }
    }

    @Override
    public void save(String id, String content) throws IOException {
        ReportIds.requireValid(id); // Phòng vệ nếu adapter được gọi trực tiếp.
        Objects.requireNonNull(content, "content");
        Files.writeString(
                directory.resolve(id + ".txt"),
                content,
                StandardCharsets.UTF_8);
    }

    @Override
    public String load(String id) throws IOException {
        ReportIds.requireValid(id);
        return Files.readString(
                directory.resolve(id + ".txt"),
                StandardCharsets.UTF_8);
    }
}

final class ConsoleReportNotifier implements ReportNotifier {
    @Override
    public void reportSaved(String id) {
        System.out.println("Saved report: " + id);
    }
}

public class ReportExample {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("di-report-example-");

        try {
            // Composition root: chọn implementation và lắp ghép.
            ReportFormatter formatter = new PlainTextReportFormatter();
            ReportStore store = new FileReportStore(directory);
            ReportNotifier notifier = new ConsoleReportNotifier();
            Clock clock = Clock.fixed(
                    Instant.parse("2026-01-02T00:00:00Z"),
                    ZoneOffset.UTC);

            ReportService service =
                    new ReportService(formatter, store, notifier, clock);

            service.generate("DEMO", "Hello DI");
            System.out.print(store.load("DEMO"));
        } finally {
            // main sở hữu thư mục tạm, chịu trách nhiệm dọn.
            Files.deleteIfExists(directory.resolve("DEMO.txt"));
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy:

```bash
javac ReportExample.java
java ReportExample
```

Đầu ra dự kiến:

```text
Saved report: DEMO
Report: DEMO
Date: 2026-01-02
Hello DI
```

Các quyết định quan trọng:

- `PlainTextReportFormatter` là **implementation thật**, thuần Java, dùng được trong unit test.
- `FileReportStore` làm I/O thật; một integration test cho nó cần file thật.
- `ConsoleReportNotifier` chỉ in console cho demo, **không thay cho kiểm thử kết nối email/HTTP thật**.
- `Clock.fixed` là một đối tượng `Clock` thật của JDK nhưng cho thời gian **cố định**, giúp test không phụ thuộc vào ngày hiện tại.
- `ReportService` dùng constructor injection và không có câu lệnh chọn adapter theo môi trường.

Chú ý: `FileReportStore` viết file bằng cách ghi đè nội dung cùng ID. Ví dụ không cung cấp transaction hay atomic write; không nên suy rằng nó đã xử lý crash, race condition, quyền file hoặc an toàn cho nhiều process truy cập đồng thời.

## 6. Unit test: thật ở phần tính toán, fake ở ranh giới I/O

Một unit test của `ReportService` cần chứng minh: định dạng nội dung đúng; store được gọi với dữ liệu đúng; notifier chỉ được gọi **sau khi lưu thành công**; dữ liệu không hợp lệ bị từ chối trước khi có side effect.

Ta dùng `InMemoryReportStore` làm fake, `RecordingNotifier` làm spy, giữ `PlainTextReportFormatter` thật và `Clock.fixed`.

Đặt mã sau vào `ReportTests.java` cùng thư mục với `ReportExample.java`:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;

final class InMemoryReportStore implements ReportStore {
    private final Map<String, String> data = new HashMap<>();
    int saveCount;

    @Override
    public void save(String id, String content) {
        ReportIds.requireValid(id);
        data.put(id, content);
        saveCount++;
    }

    @Override
    public String load(String id) throws IOException {
        ReportIds.requireValid(id);
        if (!data.containsKey(id)) {
            throw new FileNotFoundException(id);
        }
        return data.get(id);
    }
}

final class RecordingNotifier implements ReportNotifier {
    int calls;
    String lastReportId;

    @Override
    public void reportSaved(String reportId) {
        calls++;
        lastReportId = reportId;
    }
}

public class ReportTests {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-02T00:00:00Z"),
                ZoneOffset.UTC);
    }

    static void unitTest() throws IOException {
        InMemoryReportStore fakeStore = new InMemoryReportStore();
        RecordingNotifier spyNotifier = new RecordingNotifier();

        // Giữ formatter thật và clock xác định; thay hai ranh giới I/O.
        ReportService service = new ReportService(
                new PlainTextReportFormatter(),
                fakeStore,
                spyNotifier,
                fixedClock());

        String expected = "Report: U1\nDate: 2026-01-02\nhello\n";
        String actual = service.generate("U1", "hello");

        check(expected.equals(actual), "Sai nội dung trả về");
        check(expected.equals(fakeStore.load("U1")),
                "Sai dữ liệu gửi tới store");
        check(fakeStore.saveCount == 1, "Phải lưu đúng một lần");
        check(spyNotifier.calls == 1
                        && "U1".equals(spyNotifier.lastReportId),
                "Phải thông báo một lần cho đúng báo cáo");

        // ID không hợp lệ bị từ chối trước khi có side effect.
        boolean invalidRejected = false;
        try {
            service.generate("../escape", "bad");
        } catch (IllegalArgumentException expectedFailure) {
            invalidRejected = true;
        }
        check(invalidRejected, "Không từ chối ID không hợp lệ");
        check(fakeStore.saveCount == 1 && spyNotifier.calls == 1,
                "Có side effect sau validation failure");

        // Điều khiển lỗi I/O: notifier không được gọi nếu save thất bại.
        ReportStore failingStore = new ReportStore() {
            @Override
            public void save(String id, String content)
                    throws IOException {
                throw new IOException("Simulated store failure");
            }

            @Override
            public String load(String id) throws IOException {
                throw new FileNotFoundException(id);
            }
        };

        RecordingNotifier notifierAfterFailure = new RecordingNotifier();
        ReportService failingService = new ReportService(
                new PlainTextReportFormatter(),
                failingStore,
                notifierAfterFailure,
                fixedClock());

        boolean saveFailureObserved = false;
        try {
            failingService.generate("FAIL", "body");
        } catch (IOException expectedFailure) {
            saveFailureObserved = true;
        }
        check(saveFailureObserved, "Không truyền lỗi lưu trữ");
        check(notifierAfterFailure.calls == 0,
                "Không được gửi thông báo nếu lưu thất bại");

        System.out.println("UNIT PASS");
    }

    // Một tập hành vi chung cho mọi implementation ReportStore.
    static void storeContract(ReportStore store) throws IOException {
        store.save("CONTRACT", "first");
        check("first".equals(store.load("CONTRACT")),
                "Store không đọc lại đúng nội dung đã lưu");

        store.save("CONTRACT", "second");
        check("second".equals(store.load("CONTRACT")),
                "Store không ghi đè theo hợp đồng của ví dụ");

        boolean missingReported = false;
        try {
            store.load("MISSING");
        } catch (IOException expected) {
            missingReported = true;
        }
        check(missingReported,
                "Store phải báo lỗi khi chưa có báo cáo");
    }

    static void contractAndFileIntegrationTest() throws IOException {
        // Contract test chạy trên fake.
        storeContract(new InMemoryReportStore());
        System.out.println("FAKE CONTRACT PASS");

        // Một integration test nhỏ dùng FILE STORE THẬT.
        Path directory = Files.createTempDirectory("di-report-test-");
        try {
            FileReportStore actualStore = new FileReportStore(directory);
            storeContract(actualStore); // Cùng contract trên implementation thật.

            RecordingNotifier spyNotifier = new RecordingNotifier();
            ReportService service = new ReportService(
                    new PlainTextReportFormatter(),
                    actualStore,
                    spyNotifier,
                    fixedClock());

            String expected = "Report: INT1\nDate: 2026-01-02\nbody\n";
            service.generate("INT1", "body");

            // Đọc trực tiếp từ filesystem, không chỉ qua fake.
            String persisted = Files.readString(
                    directory.resolve("INT1.txt"),
                    StandardCharsets.UTF_8);
            check(expected.equals(persisted),
                    "Adapter không ghi đúng file UTF-8");
            check(spyNotifier.calls == 1,
                    "Service không thông báo sau khi ghi file");

            System.out.println("FILE INTEGRATION PASS");
        } finally {
            Files.deleteIfExists(directory.resolve("CONTRACT.txt"));
            Files.deleteIfExists(directory.resolve("INT1.txt"));
            Files.deleteIfExists(directory);
        }
    }

    public static void main(String[] args) throws IOException {
        unitTest();
        contractAndFileIntegrationTest();
        System.out.println("ALL PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac ReportExample.java ReportTests.java
java ReportTests
```

Đầu ra dự kiến:

```text
UNIT PASS
FAKE CONTRACT PASS
FILE INTEGRATION PASS
ALL PASS
```

### 6.1. Vì sao cách chọn dependency có ý nghĩa?

**Trong `unitTest()`:**

- Formatter thật được chạy, nên test phát hiện được lỗi định dạng.
- Clock cố định loại bỏ phụ thuộc vào ngày chạy test.
- Fake store ghi nhận nội dung để test kiểm tra **dữ liệu được yêu cầu lưu**, không chạm filesystem.
- Spy notifier kiểm tra side effect có chủ ý.
- Store ném lỗi được tạo để kiểm tra **nhánh thất bại**; notifier được kỳ vọng không chạy.

**Trong `contractAndFileIntegrationTest()`:**

- Một bộ kiểm tra `storeContract` được chạy trên **fake** và **file adapter thật**.
- Khi kiểm tra file adapter, test dùng `Files.readString` để đọc **file thật trên filesystem**. Đây là ranh giới tích hợp mà unit test đã cố tình không chạm vào.
- Notifier vẫn là spy vì gửi thông báo thật **không thuộc mục tiêu** của integration test file.
- Thư mục tạm được tạo riêng và dọn trong `finally`, tránh phụ thuộc dữ liệu có sẵn hoặc để lại file dùng chung.

**Điều chưa được chứng minh:** test không kiểm tra email/HTTP thật, database SQL, transaction, quyền file trên mọi hệ điều hành, thông báo khi notifier thất bại hay concurrency khi nhiều request cùng ghi một report ID. Cần những bài kiểm thử riêng nếu đó là rủi ro của sản phẩm.

## 7. Contract test: fake có hành vi gần với implementation thật đến đâu?

Một fake trong bộ nhớ thường khác database hoặc filesystem thật ở những điểm quan trọng:

- **Lưu bền vững:** `Map` mất dữ liệu khi process kết thúc; database/file có thể tồn tại sau khi khởi động lại.
- **Transaction:** fake có thể ghi ngay trong khi database dùng commit/rollback.
- **Ràng buộc duy nhất:** database có unique key, foreign key và isolation; fake có thể không mô phỏng.
- **Thứ tự và nhất quán:** một truy vấn SQL không có `ORDER BY` không có thứ tự mặc định; collection Java có thể duyệt khác.
- **Cạnh tranh đồng thời:** fake `HashMap` không thread-safe và không mô phỏng locking/transaction.
- **Ngữ nghĩa lỗi:** file có thể ném `NoSuchFileException`, database có thể ném exception khác, còn fake có thể chỉ trả `null`.

Vì vậy, **contract test** xác nhận một tập hành vi mà mọi implementation phải đáp ứng. Trong ví dụ, ba điều được kiểm tra là **lưu rồi đọc lại**, **ghi đè cùng ID** và **báo lỗi khi đọc ID chưa tồn tại**.

Nhưng contract test trong ví dụ **không chứng minh** mọi đặc tính quan trọng của một repository production. Một contract đầy đủ hơn có thể phải quy định atomicity, lỗi trùng khóa, transaction, thứ tự đọc, xử lý giá trị `null`, đồng thời và dữ liệu lớn. Khi yêu cầu tăng, nên bổ sung kiểm thử chạy trên **adapter thật với hạ tầng thực tế của môi trường test**, không cố tái tạo mọi đặc tính của database trong fake.

Một nguyên tắc tốt: **fake càng đơn giản càng dễ hiểu, nhưng mọi giả định từ fake ảnh hưởng tới logic nghiệp vụ cần được kiểm chứng lại ở ranh giới thật**.

## 8. Chọn test double để kiểm thử lỗi và nhánh hiếm gặp

Những lỗi như timeout, database từ chối kết nối, gửi email thất bại hoặc dữ liệu không tồn tại khó tạo lặp lại một cách an toàn trên hệ thống thật. Stub và fake có thể mô phỏng để kiểm tra **cách service phản ứng**:

```java
// Một stub cố ý ném lỗi để kiểm tra logic của service.
ReportStore failingStore = new ReportStore() {
    public void save(String id, String data) throws IOException {
        throw new IOException("simulated failure");
    }

    public String load(String id) throws IOException {
        throw new FileNotFoundException(id);
    }
};
```

Đây là mẫu đã xuất hiện trong test phía trên. Lỗi do stub tạo ra **không chứng minh** adapter thật sẽ ném cùng exception, cùng mã trạng thái, hay cùng thời điểm. Nó chỉ cho phép ta kiểm tra hành vi khi nhận **một loại lỗi được mô tả trong contract**.

Các trường hợp thường đáng bổ sung:

1. **Lưu thất bại:** không gửi thông báo, lỗi được trả hoặc chuyển thành lỗi nghiệp vụ phù hợp.
2. **Thông báo thất bại sau khi lưu:** dữ liệu đã được lưu nhưng gửi thông báo thất bại; cần chính sách xử lý nhất quán.
3. **Định dạng thất bại:** không ghi dữ liệu chưa hợp lệ, không gửi thông báo.
4. **Trùng ID:** xác định ghi đè hay từ chối; fake và adapter thật phải tuân thủ quyết định giống nhau.
5. **Hủy request hoặc task:** tài nguyên phải được đóng trong scope dù lệnh xử lý thất bại.

**Lưu ý:** trong ví dụ, việc lưu và thông báo là hai side effect độc lập, không có transaction phân tán. Test `notifier.calls == 0` khi lưu thất bại là hợp lệ với thứ tự hiện tại, nhưng **không giải quyết** trường hợp lưu thành công rồi gửi thất bại. Ứng dụng thật có thể cần outbox, retry, idempotency hoặc mô hình trạng thái nghiệp vụ phù hợp.

## 9. Những lỗi thường gặp khi chọn thật hay giả

### 9.1. Mock mọi thứ

Nếu mock cả formatter, rule nghiệp vụ và value object đơn giản, bài test thường chỉ chứng minh lớp gọi đúng những method đã được lập trình sẵn, không chứng minh kết quả thật. Hãy giữ implementation thật ở những nơi **nhanh, xác định, không I/O** mà hành vi cần kiểm tra.

### 9.2. Dùng fake database rồi coi là đã kiểm tra SQL

`InMemoryReportStore` không thực thi migration, SQL query, transaction hoặc constraint của database thật. Hãy có integration test dùng đúng loại database kiểm thử cần thiết khi các đặc tính đó quan trọng.

### 9.3. Dùng dịch vụ production trong test

Unit và integration test thông thường không nên gửi tiền thật, email tới khách hàng thật hoặc ghi vào database production. Nếu cần xác minh hệ thống bên ngoài, sử dụng sandbox, tenant/test account riêng, dữ liệu thử và quyền hạn tối thiểu, với cleanup và giới hạn tác động rõ ràng.

### 9.4. Dùng `Thread.sleep` hoặc thời gian thực cho mọi test

Thời gian hệ thống, scheduler và network làm test dễ chập chờn. Inject `Clock`, scheduler/fake executor hoặc một abstraction phù hợp để điều khiển thời gian; dành test tích hợp thật cho hành vi timeouts, scheduling và concurrency ở cấp hệ thống.

### 9.5. Chia sẻ state fake giữa các test

Nếu fake repository là singleton dùng chung cho cả suite, test sau có thể phụ thuộc dữ liệu từ test trước. Mỗi bài test nên tạo object graph riêng hoặc reset state theo quy tắc rõ. **Độc lập và có thể chạy lại** là yêu cầu quan trọng hơn việc giảm vài lời gọi `new`.

### 9.6. Kiểm tra chi tiết implementation thay vì hành vi

Một test buộc `formatter.format` được gọi đúng một lần có thể thất bại sau một refactor tối ưu hóa, dù nội dung báo cáo không đổi. Chỉ assert số lần gọi khi đó là **yêu cầu nghiệp vụ hoặc hiệu năng**. Với formatter thuần, assert chuỗi kết quả thường bền vững hơn.

### 9.7. Dùng một fake quá thông minh

Fake cố mô phỏng mọi ràng buộc, retry, locking và protocol có thể thành một implementation thứ hai khó bảo trì. Nếu fake quá phức tạp, hãy giảm phần logic giả; bổ sung contract test và integration test thực thay vì tạo một database giả hoàn chỉnh.

## 10. Scope, ownership và tài nguyên trong kiểm thử DI

Chọn thật hay giả còn là quyết định về **vòng đời đối tượng**.

| Dependency | Unit test | Integration test | Điều phải dọn |
| --- | --- | --- | --- |
| Formatter thuần Java | Instance thật mới theo test hoặc dùng chung nếu bất biến. | Instance thật. | Thường không có tài nguyên ngoài. |
| Fake repository trong bộ nhớ | Tạo riêng mỗi test để tránh rò state. | Chỉ dùng nếu repository không nằm trong mục tiêu integration. | Bỏ tham chiếu hoặc reset state. |
| File/database adapter | Thường thay bằng fake. | Tạo adapter thật trong môi trường tạm/cô lập. | File, transaction, connection, container hoặc dữ liệu thử. |
| HTTP/email adapter | Spy/stub/fake. | Thật với sandbox hoặc test server nếu đường tích hợp nằm trong phạm vi. | Client, socket, request in-flight, dữ liệu thử. |
| Clock và scheduler | `Clock.fixed`, virtual clock/scheduler phù hợp. | Thật hoặc được điều khiển theo mục tiêu test. | Executor/thread nếu có. |

Một test fixture có thể là **composition root riêng**: nó tạo dependency thật hoặc giả, lắp service và chịu trách nhiệm giải phóng. Không nên để một service nghiệp vụ tự đóng client dùng chung chỉ vì test tạo client đó.

Với resource `AutoCloseable`, dùng `try-with-resources` khi sở hữu rõ. Với dữ liệu test trên filesystem, dùng thư mục tạm riêng, tên file hợp lệ và cleanup trong `finally`. Với database, dùng transaction rollback hoặc schema/instance cô lập theo contract của hệ thống, không giả định mọi DDL hoặc thao tác ngoài database đều rollback được.

**Scope của ứng dụng thật vẫn phải được test:** nếu một singleton giữ state request hoặc một fake không thread-safe bị dùng đồng thời, test tuần tự với fake có thể bỏ sót lỗi. Viết kiểm thử đồng thời và tích hợp khi use case thực có nhiều request/job chung dependency.

## 11. Thiết kế bộ kiểm thử cân bằng

Một chiến lược thực tế là tạo nhiều bài test ở những ranh giới khác nhau thay vì bắt một bài test chứng minh tất cả:

```text
Nhiều unit test
   - nhanh, xác định
   - giữ rule/formatter thật, fake I/O
             |
             v
Contract + component tests
   - xác minh các implementation cùng giữ hợp đồng
   - xác minh phối hợp trong một component
             |
             v
Integration tests chọn lọc
   - file/database/HTTP/queue thật trong môi trường kiểm thử
   - kiểm tra wiring, serialization, transaction, lifecycle
             |
             v
Một số E2E flows quan trọng
   - xác nhận đường đi hoàn chỉnh và cấu hình triển khai
   - chạy trong môi trường an toàn, cô lập
```

Đây là hướng phân bổ nỗ lực, **không phải công thức số lượng test cố định**. Những thay đổi rủi ro cao ở adapter hạ tầng có thể cần nhiều integration test hơn. Những quy tắc tính toán thuần túy thường được bao phủ tốt bằng unit test nhanh và đầy đủ các biên.

Trước khi thêm một mock hay dùng adapter thật, hãy trả lời:

- **Đối tượng đang được kiểm chứng là gì?** Service, adapter, contract hay cả luồng?
- **Hành vi nào phải chạy thật để bài test có giá trị?** Tính toán, mapping, SQL, HTTP, persistence hay cấu hình?
- **Tác dụng phụ nào phải tránh?** Dữ liệu production, tiền, email, hạ tầng dùng chung.
- **Các giá trị bất định đã được kiểm soát chưa?** Thời gian, random, scheduler, network và thứ tự duyệt.
- **Ai sở hữu dữ liệu và tài nguyên test?** Chúng có được cô lập/dọn ngay cả khi test thất bại không?
- **Nếu fake khác implementation thật thì test nào phát hiện?** Có contract/integration test cho những giả định quan trọng không?

## 12. Bài tập thực hành

**Bối cảnh:** `CheckoutService` có bốn dependency: `TaxCalculator` tính thuế thuần Java, `OrderRepository` lưu đơn vào database, `PaymentGateway` gọi hệ thống thanh toán và `Clock` cung cấp thời gian. Yêu cầu là không thu tiền thật trong các bài test thông thường.

1. **Lập bảng lựa chọn:** với unit test, component test, integration test và E2E, dependency nào nên dùng thật hoặc double? Giải thích bằng ranh giới cần kiểm chứng, không chỉ bằng tên loại test.
2. **Viết unit test:** dùng `TaxCalculator` thật, fake `OrderRepository`, spy `PaymentGateway` và clock cố định; kiểm tra kết quả tính tiền và lời gọi cần thiết.
3. **Giả lập thất bại:** khiến repository ném exception. Nêu thứ tự các side effect cần kiểm tra và sự khác biệt giữa “đã test nhánh lỗi” với “đã bảo đảm transaction thật”.
4. **Thiết kế contract test:** định nghĩa các bất biến `OrderRepository` mà fake và SQL adapter phải cùng thỏa, như lưu/đọc, ID trùng, lỗi không tìm thấy; bổ sung integration test với database thật để kiểm tra transaction/concurrency.
5. **Lập integration test cho payment adapter:** dùng sandbox/test server có kiểm soát, không gọi production; kiểm tra request mapping, authentication, timeout và phản hồi lỗi mà không để secret lọt vào log.
6. **Quản lý lifecycle:** chỉ rõ ai tạo/đóng database connection pool, client và transaction, và cách test cô lập nhiều trường hợp.
7. **Phân tích test yếu:** một unit test mock cả `TaxCalculator` rồi assert `CheckoutService` gọi `calculateTax` đúng một lần đã bỏ sót những lỗi nào?
8. **Phân tích test lỗi giả:** nếu fake repository cho phép hai đơn cùng ID nhưng database production có unique constraint, hệ thống có thể sai ở đâu? Hãy đề xuất bài test phát hiện sự khác biệt.

**Gợi ý đối chiếu:** `TaxCalculator` thuần túy thường nên dùng thật trong unit test; `Clock.fixed` giữ thời gian xác định. Repository và gateway thường được thay bằng fake/stub/spy ở unit test, nhưng SQL và giao thức thanh toán phải có integration test riêng nếu là rủi ro cần kiểm soát. E2E quan trọng nên đi qua cấu hình gần thực tế trong môi trường thử an toàn. Contract test giúp phát hiện fake sai ngữ nghĩa nhưng không thay thế các phép kiểm tra giao dịch và đồng thời thật.

**Điểm cần nhớ:** DI cho phép cùng một lớp nghiệp vụ nhận **dependency thật hoặc test double** theo composition root của từng bài test. Hãy chọn theo **phạm vi và hành vi muốn chứng minh**, không theo thói quen “mock hết” hoặc “dùng thật hết”. Unit test tập trung vào logic nhanh và xác định; contract test bảo vệ ngữ nghĩa của abstraction; integration/E2E xác minh những ranh giới thật cần thiết. Luôn quản lý scope, vòng đời và dữ liệu thử rõ ràng trước khi chuyển từ Java thuần sang DI container.
