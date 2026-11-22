# Giữ kết quả độc lập với thứ tự và mức song song

Một bộ kiểm thử CI đáng tin cậy phải cho cùng kết luận khi các test được chạy theo thứ tự khác nhau hoặc được thực thi đồng thời trong giới hạn tài nguyên đã cấu hình. Nếu một test chỉ đạt khi chạy sau test khác, hoặc thất bại khi hai test chạy cùng lúc, kết quả build đang phụ thuộc vào trạng thái ẩn của môi trường.

Hai yêu cầu này có liên quan nhưng khác nhau:

- **Độc lập với thứ tự:** kết quả của một test không phụ thuộc vào việc test nào đã chạy trước nó. Test phải tự chuẩn bị dữ liệu và không để lại trạng thái làm thay đổi test sau.
- **An toàn khi chạy song song:** nhiều test có thể chạy đồng thời mà không tranh chấp tài nguyên dùng chung, ghi đè dữ liệu hoặc làm sai kết quả của nhau.

Một test suite có thể độc lập về thứ tự nhưng vẫn không an toàn khi chạy song song. Ví dụ, mỗi test tự tạo dữ liệu riêng nhưng tất cả đều ghi vào cùng một file. Ngược lại, một suite có thể chạy song song mà không có race condition trong một lần chạy, nhưng vẫn phụ thuộc thứ tự vì test A tạo dữ liệu mà test B cần. Cần kiểm tra cả hai thuộc tính.

Trong CI/CD, vấn đề này ảnh hưởng trực tiếp tới chất lượng cổng kiểm thử. Một lần chạy xanh không đủ nếu kết quả thay đổi theo thứ tự, số worker, thời điểm hoặc tải của runner. Mục tiêu là thiết kế test có đầu vào rõ ràng, trạng thái riêng, đồng bộ đúng cách và bằng chứng đủ để tái hiện lỗi.

## 1. Vì sao thứ tự và mức song song có thể làm test thất bại?

Ở máy phát triển, test thường được chạy ít lần, theo thứ tự quen thuộc và trên một môi trường ít tải. CI có thể chạy nhiều class hoặc method cùng lúc, chia test thành nhiều process, chạy trên runner khác nhau hoặc lặp lại với thứ tự ngẫu nhiên. Những khác biệt này làm lộ ra phụ thuộc mà cách chạy tuần tự trước đó chưa phát hiện.

Các nguồn gây phụ thuộc phổ biến:

| Nguồn trạng thái | Ví dụ lỗi | Hướng kiểm soát |
|---|---|---|
| Biến static hoặc singleton | Test trước sửa static field; test sau nhận giá trị còn sót | Tránh mutable global state, khởi tạo riêng hoặc khôi phục trạng thái |
| System properties, locale, timezone | Một test đổi `Locale.setDefault`, test khác định dạng số theo locale mới | Không đổi global setting hoặc dùng resource lock chung |
| File và thư mục cố định | Nhiều test cùng ghi `target/test-output.json` | Dùng thư mục tạm riêng cho từng test |
| Database dùng chung | Test xóa bảng hoặc đọc bản ghi do test khác tạo | Dữ liệu riêng, schema/tenant riêng hoặc transaction có ranh giới rõ |
| Port cố định | Hai server test cùng bind port 8080 | Bind port 0 và lấy port được hệ điều hành cấp |
| Clock và dữ liệu thời gian | Test chạy qua ranh giới ngày hoặc timezone khác nhau | Tiêm `Clock`, dùng thời điểm cố định |
| Random và UUID | Test thất bại không tái hiện được vì dữ liệu khác mỗi lần | Seed có thể ghi lại, log seed và tách random generator |
| Cache hoặc thư mục dùng chung | Một test làm nóng cache, test khác dựa vào nội dung cũ | Cache riêng hoặc reset theo test |
| Message broker và queue | Test đọc nhầm message của test khác | Topic, queue hoặc correlation ID riêng |
| Async task và thread | Test kết thúc trước khi callback hoàn tất | Dùng latch/future và chờ có timeout |
| Dữ liệu thứ tự không xác định | Test giả định query luôn trả về một thứ tự | Dùng `ORDER BY` khi thứ tự là yêu cầu |

Một dấu hiệu quan trọng là test thất bại khi chạy riêng thì đạt, nhưng khi chạy toàn bộ suite lại thất bại. Điều đó thường chỉ ra trạng thái bị rò rỉ hoặc tranh chấp tài nguyên, dù nguyên nhân chính xác vẫn cần được xác minh bằng log và cách tái hiện.

## 2. Phân biệt tính độc lập về thứ tự và an toàn song song

Hãy xem hai test minh họa:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CounterTest {
    private static int counter = 0;

    @Test
    void startsAtZero() {
        assertEquals(0, counter);
    }

    @Test
    void incrementsCounter() {
        counter++;
        assertEquals(1, counter);
    }
}
```

Test `startsAtZero` chỉ đạt nếu chưa có test nào thay đổi `counter`. Khi thứ tự thay đổi, kết quả có thể đổi. Nếu hai method chạy đồng thời, cả hai còn có thể đọc/ghi biến trong thời điểm không dự đoán được. Đây vừa là phụ thuộc thứ tự, vừa là race condition.

Một ví dụ khác: mỗi test tạo bản ghi riêng trong database, nhưng cả hai cùng chạy câu lệnh `TRUNCATE orders` trong `@BeforeEach`. Dữ liệu của test này có thể bị xóa khi test kia bắt đầu. Mỗi test tưởng rằng mình tự chuẩn bị trạng thái, nhưng thao tác reset lại tác động lên tài nguyên dùng chung.

Nên thiết kế để mỗi test có vòng đời riêng:

1. Tạo dữ liệu và tài nguyên chỉ test đó sở hữu.
2. Thực hiện hành động cần kiểm tra.
3. Xác minh kết quả bằng dữ liệu do test đó tạo.
4. Dọn đúng tài nguyên của test đó, không xóa dữ liệu của test khác.

Nếu một tài nguyên thực sự phải dùng chung, cần khai báo rõ cách đồng bộ và bảo đảm mọi test truy cập tài nguyên đó tuân theo cùng một quy tắc.

## 3. Viết test độc lập với trạng thái toàn cục

### Tránh mutable static state

Không dùng biến static có thể thay đổi để lưu dữ liệu kiểm thử giữa các test. Thay vào đó, tạo đối tượng mới trong từng test hoặc dùng factory tạo fixture riêng.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class CartTest {
    @Test
    void addsItemToEmptyCart() {
        var cart = new Cart();

        cart.add(new Item("book", 1));

        assertEquals(1, cart.items().size());
    }

    @Test
    void newCartStartsEmpty() {
        var cart = new Cart();

        assertTrue(cart.items().isEmpty());
    }
}
```

Mỗi test tạo `Cart` mới, nên test thêm item không làm thay đổi trạng thái của test khác. Với cache hoặc registry singleton trong production, nên cung cấp cách reset có kiểm soát hoặc thay dependency bằng implementation riêng trong test.

### Hiểu đúng vòng đời test của JUnit Jupiter

Mặc định, JUnit Jupiter tạo một test instance mới cho mỗi method (`PER_METHOD`). Điều này giúp các field instance không bị chia sẻ giữa các method. Tuy nhiên, nó không cô lập static field, singleton, system property, file, database hoặc service bên ngoài.

Khi dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, nhiều method có thể dùng chung một instance. Nếu bật chạy song song, mutable field trong instance đó có thể bị truy cập đồng thời. Chỉ dùng `PER_CLASS` khi trạng thái instance là bất biến hoặc đã có cơ chế đồng bộ phù hợp.

Không nên dựa vào `@BeforeAll` để tạo một bộ dữ liệu chung rồi để mọi test tự sửa. Nếu test cần dữ liệu nền, hãy coi dữ liệu đó là chỉ đọc hoặc tạo bản sao riêng cho từng test.

### Khôi phục system property và global setting

Một test có thể cần thay system property hoặc locale để kiểm tra hành vi. Nếu phải thay global state, hãy lưu giá trị cũ và khôi phục trong `finally`:

```java
String previous = System.getProperty("app.mode");
try {
    System.setProperty("app.mode", "test");
    // Thực hiện kiểm tra phụ thuộc app.mode.
} finally {
    if (previous == null) {
        System.clearProperty("app.mode");
    } else {
        System.setProperty("app.mode", previous);
    }
}
```

Việc khôi phục giúp test sau không nhận trạng thái đã đổi. Nhưng nếu test khác đang đọc property trong lúc nó bị thay, kết quả vẫn có thể sai. Với tài nguyên toàn cục, cần thêm khóa đồng bộ hoặc thiết kế lại để không phải thay global state.

## 4. Tiêm Clock và kiểm soát dữ liệu ngẫu nhiên

Thời gian và random là hai nguồn đầu vào dễ khiến test lúc đạt lúc thất bại.

### Dùng `Clock` thay cho thời gian hệ thống

Không gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()` ở sâu trong logic nghiệp vụ nếu kết quả cần được kiểm thử chính xác. Tiêm `Clock` để test có thể chọn một thời điểm cố định.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

final class ExpirationPolicy {
    private final Clock clock;

    ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
```

Test:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

@Test
void expiresAtConfiguredInstant() {
    var now = Instant.parse("2026-11-18T10:00:00Z");
    var clock = Clock.fixed(now, ZoneOffset.UTC);
    var policy = new ExpirationPolicy(clock);

    assertTrue(policy.isExpired(now));
}
```

Test không còn phụ thuộc thời điểm thật mà runner thực thi. Các trường hợp trước hạn, đúng hạn và sau hạn có thể được kiểm tra bằng những `Clock` cố định khác nhau.

### Dùng seed có thể tái hiện cho random

Nếu thuật toán cần random, hãy tiêm nguồn random thay vì tạo `new Random()` rải rác trong logic. Trong test, dùng seed cố định để cùng một test nhận cùng chuỗi giá trị.

```java
import java.util.Random;

final class SampleSelector {
    private final Random random;

    SampleSelector(Random random) {
        this.random = random;
    }

    int chooseIndex(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }
        return random.nextInt(size);
    }
}
```

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

@Test
void selectsWithinRangeWithKnownSeed() {
    var selector = new SampleSelector(new Random(12345L));

    int index = selector.chooseIndex(5);

    assertTrue(index >= 0 && index < 5);
}
```

Seed cố định giúp tái hiện đầu vào random. Nếu mục tiêu là kiểm tra nhiều chuỗi random, hãy chạy nhiều seed có ghi nhận, thay vì để test tự lấy seed không thể truy vết. Với chức năng bảo mật, không dùng `java.util.Random` làm nguồn ngẫu nhiên production; ví dụ này chỉ minh họa khả năng kiểm soát dữ liệu test.

## 5. Cô lập filesystem, port và dịch vụ bên ngoài

### Dùng thư mục tạm riêng

Không ghi file test vào một đường dẫn cố định dùng chung. JUnit hỗ trợ `@TempDir` để tạo thư mục tạm cho test và dọn sau khi test kết thúc.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ReportWriterTest {
    @Test
    void writesReportIntoTemporaryDirectory(@TempDir Path tempDir) throws Exception {
        Path report = tempDir.resolve("report.txt");

        Files.writeString(report, "build passed");

        assertEquals("build passed", Files.readString(report));
    }
}
```

Mỗi test nhận thư mục riêng nên không ghi đè file của test khác. Nếu test tạo nhiều file con, hãy tiếp tục đặt chúng dưới thư mục tạm này.

### Không chiếm port cố định

Hai test khởi động server cùng port có thể tranh chấp. Hãy yêu cầu hệ điều hành cấp port bằng cách bind port `0`, sau đó đọc port thực tế từ socket hoặc server đã khởi động.

```java
try (var serverSocket = new java.net.ServerSocket(0)) {
    int assignedPort = serverSocket.getLocalPort();
    assertTrue(assignedPort > 0);
}
```

Đoạn code minh họa cách lấy port khả dụng trong thời gian socket còn mở. Với HTTP server test, hãy cấu hình server bind port 0 và lấy port từ server đang chạy. Tránh quy trình tìm một port trống, đóng socket rồi mới khởi động server trên port đó; một process khác có thể chiếm port trong khoảng thời gian giữa hai thao tác.

### Database và message broker

Khi nhiều test dùng cùng database, mỗi test nên có dữ liệu riêng. Một số lựa chọn:

- Tạo schema hoặc database riêng theo test class, test worker hoặc test run.
- Tạo tenant hoặc namespace riêng cho mỗi test.
- Dùng khóa chính và correlation ID duy nhất để truy vấn đúng dữ liệu của test.
- Dọn đúng các bản ghi do test tạo, không truncate bảng dùng chung.
- Dùng transaction rollback khi mọi thao tác của test thực sự chạy trong cùng transaction.

Transaction rollback không tự cô lập được mọi trường hợp. Nếu ứng dụng mở connection khác, chạy async, gọi service ngoài process hoặc phát message đã commit, transaction của test có thể không hoàn tác những tác động đó. Khi đó cần namespace riêng, cleanup rõ ràng hoặc môi trường disposable.

Với message broker, dùng queue/topic riêng hoặc message key có correlation ID. Test chỉ đọc message thuộc yêu cầu của chính nó và dọn subscription sau khi kết thúc.

## 6. Đồng bộ đúng cách với test bất đồng bộ

Không dùng `Thread.sleep()` để đoán rằng một tác vụ bất đồng bộ đã hoàn tất. Thời gian xử lý phụ thuộc tải CPU, network và runner; sleep ngắn có thể làm test thất bại ngẫu nhiên, còn sleep dài làm suite chậm.

Hãy chờ một tín hiệu hoàn tất có timeout, chẳng hạn `CompletableFuture`, `CountDownLatch` hoặc một cơ chế await có điều kiện.

Ví dụ dùng `CountDownLatch`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

@Test
void waitsForBackgroundWork() throws Exception {
    var completed = new java.util.concurrent.CountDownLatch(1);
    var result = new java.util.concurrent.atomic.AtomicReference<String>();

    var executor = java.util.concurrent.Executors.newSingleThreadExecutor();
    try {
        executor.submit(() -> {
            result.set("done");
            completed.countDown();
        });

        assertTrue(completed.await(2, java.util.concurrent.TimeUnit.SECONDS));
        assertEquals("done", result.get());
    } finally {
        executor.shutdownNow();
    }
}
```

Timeout giúp test dừng với lỗi rõ ràng nếu tác vụ không hoàn tất. `finally` đóng executor ngay cả khi assertion thất bại. Với code production, nên ưu tiên quản lý vòng đời executor qua dependency hoặc lifecycle của ứng dụng thay vì tạo thread pool toàn cục không được dọn.

Đồng bộ phải dựa trên điều kiện cần xác minh, không phải một khoảng chờ tùy ý. Nếu cần chờ một trạng thái trong hệ thống bên ngoài, dùng polling có khoảng thời gian và timeout giới hạn, đồng thời ghi lại trạng thái cuối cùng khi hết hạn.

## 7. Không dựa vào thứ tự ngầm của dữ liệu

Database không bảo đảm thứ tự bản ghi nếu câu SQL không có `ORDER BY`. Collection không có thứ tự hoặc map không được quy định thứ tự cũng không nên được kiểm tra như một danh sách có thứ tự.

Ví dụ, nếu API cần trả đơn hàng mới nhất trước, hãy thể hiện điều đó trong truy vấn:

```sql
SELECT id, created_at, total
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, id DESC;
```

`id` là tiêu chí phụ giúp thứ tự ổn định khi hai bản ghi có cùng `created_at`. Nếu thứ tự không phải yêu cầu nghiệp vụ, test nên so sánh tập phần tử hoặc kiểm tra membership thay vì phụ thuộc thứ tự trả về.

Tương tự, không nên dựa vào thứ tự khởi tạo file, thứ tự duyệt thư mục hoặc thứ tự event từ nhiều thread nếu hợp đồng của hệ thống không bảo đảm điều đó. Nếu thứ tự có ý nghĩa, hãy sắp xếp hoặc đồng bộ tại đúng lớp chịu trách nhiệm.

## 8. Phát hiện test phụ thuộc thứ tự bằng randomization

Chạy test theo thứ tự cố định quen thuộc có thể che giấu phụ thuộc. Một cách phát hiện là thay đổi thứ tự class và method qua các lần chạy.

JUnit Jupiter cho phép chọn orderer ngẫu nhiên. Có thể đặt trong `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.execution.order.random.seed=20261118
```

Với seed cố định, thứ tự ngẫu nhiên được tái hiện giữa các lần chạy tương ứng. Khi phát hiện lỗi, lưu seed cùng class và method thất bại để có thể chạy lại cùng thứ tự.

Một seed cố định không khám phá được mọi thứ tự có thể. Có thể dùng seed ổn định trong pipeline pull request để kết quả dễ so sánh, rồi thêm một job định kỳ chạy nhiều seed khác nhau để tìm phụ thuộc hiếm gặp. Khi thay seed, ghi lại giá trị đó trong log hoặc test report.

Không dùng `@TestMethodOrder` để sắp xếp test theo thứ tự cần thiết chỉ nhằm làm suite xanh. Nếu hai test cần cùng một kịch bản, hãy biến chúng thành một test scenario có bước rõ ràng hoặc tạo fixture riêng cho mỗi test. Thứ tự tường minh chỉ phù hợp khi thứ tự là một phần của hành vi cần kiểm thử, không phải để bù cho trạng thái rò rỉ.

## 9. Bật chạy song song có kiểm soát với JUnit 5

JUnit Jupiter mặc định không bật parallel execution. Có thể bật bằng file `junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

Ở cấu hình này, JUnit dùng chiến lược fixed với parallelism bằng 2 và cho phép method/class chạy đồng thời theo mode đã khai báo. Con số 2 chỉ là ví dụ; hãy điều chỉnh theo CPU, bộ nhớ và sức chịu tải của dịch vụ kiểm thử.

Không nên bật parallel execution cho toàn bộ suite trước khi test có isolation tốt. Có thể bắt đầu với nhóm test độc lập, quan sát lỗi và mức tiêu thụ tài nguyên, sau đó mở rộng dần.

### Khóa tài nguyên dùng chung bằng `@ResourceLock`

Nếu một số test bắt buộc truy cập tài nguyên toàn cục, JUnit cung cấp `@ResourceLock` để tuần tự hóa những test khai báo cùng khóa.

```java
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(value = "default-locale", mode = ResourceAccessMode.READ_WRITE)
class LocaleSensitiveTest {
    @Test
    void formatsUsingConfiguredLocale() {
        Locale previous = Locale.getDefault();
        try {
            Locale.setDefault(Locale.US);
            // Thực hiện assertion phụ thuộc locale.
        } finally {
            Locale.setDefault(previous);
        }
    }
}
```

Mọi test khác đọc hoặc thay đổi default locale trong cùng test plan cũng phải khai báo cùng khóa nếu cần phối hợp. Một test không khai báo khóa vẫn có thể chạy đồng thời và đọc trạng thái đang bị thay đổi. `@ResourceLock` điều phối test trong phạm vi JUnit engine; nó không khóa process Gradle khác, job CI khác hoặc ứng dụng bên ngoài.

### Dùng `@Isolated` khi cả class cần chạy riêng

`@Isolated` đánh dấu một test class không được chạy đồng thời với các test khác trong cùng kế hoạch thực thi. Đây là lựa chọn cho test legacy cần thay đổi nhiều trạng thái toàn cục khó khóa riêng lẻ.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Isolated;

@Isolated
class LegacyGlobalConfigurationTest {
    @Test
    void verifiesLegacyConfiguration() {
        // Test cần độc quyền truy cập trạng thái toàn cục.
    }
}
```

`@Isolated` có thể làm giảm mức song song và kéo dài thời gian suite. Hãy dùng như biện pháp giới hạn cho test khó cô lập, đồng thời tạo công việc refactor để loại bỏ trạng thái toàn cục về lâu dài.

## 10. Cấu hình song song ở Gradle

JUnit điều khiển mức song song bên trong test engine. Gradle còn có thể chạy nhiều test worker process. Hai lớp này độc lập và có thể nhân mức đồng thời lên.

Trong `build.gradle.kts`:

```kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    // Tối đa hai JVM test worker cho mỗi Test task.
    maxParallelForks = 2

    // Giữ worker sống trong suốt task; không fork lại sau mỗi test.
    forkEvery = 0
}
```

Nếu mỗi worker JVM lại cho JUnit chạy song song 2 test, một `Test` task có thể có khoảng 4 test đang chạy cùng lúc. Nếu Gradle chạy nhiều `Test` task song song hoặc CI chia suite thành nhiều job, tổng số test đồng thời còn cao hơn.

Phân biệt các cơ chế:

| Cơ chế | Phạm vi | Tác động |
|---|---|---|
| JUnit parallel execution | Method/class trong một test JVM | Nhiều test cùng chạy trong một process |
| Gradle `maxParallelForks` | Nhiều JVM test worker của một `Test` task | Cách ly static state giữa các worker process, nhưng vẫn có thể tranh chấp DB/file/port bên ngoài |
| Gradle `org.gradle.parallel` | Các project/task đủ điều kiện trong build | Không đồng nghĩa với JUnit method parallelism |
| CI matrix hoặc test sharding | Nhiều job/runner | Tăng mức đồng thời trên nhiều máy, cần namespace tài nguyên riêng |

`maxParallelForks` mặc định là 1. Tăng số worker có thể giảm thời gian test nhưng tăng bộ nhớ và kết nối dịch vụ. Không đặt số worker chỉ dựa trên số CPU; database, container, file descriptor và giới hạn API cũng cần được tính đến.

## 11. Xác định mức song song phù hợp

Mức song song tối ưu là mức giúp rút ngắn thời gian phản hồi mà không làm tăng đáng kể test flaky hoặc làm quá tải dịch vụ dùng chung.

Khi điều chỉnh, xem xét:

- Số lõi CPU và bộ nhớ khả dụng trên runner.
- Mức sử dụng database connection pool, message broker và container.
- Số lượng test khởi chạy server hoặc process con.
- Thời gian chờ I/O so với thời gian xử lý CPU.
- Số Gradle worker và số JUnit thread trong mỗi worker.
- Số CI job hoặc shard chạy đồng thời trên cùng môi trường kiểm thử.

Có thể bắt đầu với một cấu hình tuần tự làm baseline, sau đó tăng dần JUnit parallelism hoặc Gradle forks và đo thời gian p50/p95, tỷ lệ thất bại, memory peak và tải dịch vụ. Nếu thời gian không giảm nhưng lỗi tăng, mức song song đang vượt quá khả năng của test hoặc hạ tầng.

Một số test tích hợp có thể cần chạy tuần tự vì dùng một môi trường dùng chung không hỗ trợ namespace riêng. Hãy giới hạn tuần tự đúng nhóm tài nguyên đó; không nên vô hiệu hóa song song cho toàn bộ suite chỉ vì một vài test legacy.

## 12. Chẩn đoán test thất bại theo thứ tự hoặc song song

Khi test flaky xuất hiện, cần giữ đủ dữ liệu để tái hiện. Không chỉ ghi “test đôi khi fail”. Hãy thu thập:

- Tên class và method thất bại, test engine và phiên bản JUnit.
- Commit SHA, phiên bản JDK/Gradle và cấu hình CI.
- Thứ tự test hoặc random seed.
- Số JUnit thread và số Gradle worker.
- Test chạy riêng có đạt không; chạy cả suite có thất bại không?
- Test chạy tuần tự có đạt nhưng chạy song song có thất bại không?
- ID worker, schema/database/tenant, port hoặc thư mục tạm liên quan.
- Log của test thất bại đầu tiên và các test chạy đồng thời với nó.

### Ma trận tái hiện

| Lần chạy | Thứ tự | Mức song song | Mục đích |
|---|---|---|---|
| A | Thứ tự mặc định | 1 | Tạo baseline tuần tự |
| B | Ngẫu nhiên, seed cố định | 1 | Tìm phụ thuộc thứ tự |
| C | Thứ tự mặc định | 2 hoặc hơn | Tìm race condition |
| D | Ngẫu nhiên, seed cố định | 2 hoặc hơn | Kết hợp hai loại phụ thuộc |
| E | Test thất bại chạy riêng | 1 | Phân biệt lỗi logic với lỗi tương tác |

Nếu chỉ B thất bại, ưu tiên tìm trạng thái rò rỉ giữa test. Nếu chỉ C hoặc D thất bại, tìm tranh chấp tài nguyên và race condition. Nếu E cũng thất bại, có thể là lỗi logic độc lập với thứ tự. Đây là hướng khoanh vùng, không phải kết luận tự động.

### Chạy lại một test cụ thể

Gradle cho phép lọc test theo class hoặc method:

```bash
./gradlew test --tests "com.example.OrderServiceTest.createsOrder" --info
```

Chạy cả suite với một seed cụ thể bằng cách truyền seed qua Gradle property. Ví dụ, trong `build.gradle.kts`:

```kotlin
val testOrderSeed = providers.gradleProperty("testOrderSeed").orElse("20261118")

tasks.withType<Test>().configureEach {
    systemProperty("junit.jupiter.execution.order.random.seed", testOrderSeed.get())
}
```

Sau đó chạy:

```bash
./gradlew test -PtestOrderSeed=987654321 --info
```

Ghi lại seed cùng log khi test thất bại. Seed cần được giữ nguyên khi tái hiện, sau đó có thể thử các seed khác để tìm thêm phụ thuộc.

### Đọc log theo test worker

Khi Gradle chạy nhiều worker, log có thể xen kẽ. Bật log đủ chi tiết hoặc xuất report theo test để xác định worker và thời điểm. Tránh log dữ liệu nhạy cảm. Nếu test dùng schema hoặc namespace riêng, đưa mã nhận diện không nhạy cảm vào log để liên hệ test với tài nguyên nó tạo.

## 13. Ví dụ workflow CI chạy test với cấu hình có kiểm soát

Workflow GitHub Actions dưới đây minh họa một job chạy test trên JDK cố định và giữ log/report khi thất bại:

```yaml
name: Java tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 25
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run tests
        run: ./gradlew --no-daemon test --info

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports-${{ github.sha }}
          path: build/reports/tests/test/
          if-no-files-found: ignore
          retention-days: 7
```

Workflow này không tự bật JUnit parallel execution; cấu hình đó nằm trong `junit-platform.properties`. Cách tách cấu hình giúp repository quyết định rõ mức song song và có thể thay đổi theo nhóm test. `if: always()` chỉ dùng để lưu báo cáo sau khi test kết thúc, không làm cho job test được coi là đạt nếu lệnh test thất bại.

Nếu CI dùng matrix hoặc chia test thành shard, mỗi job cần namespace riêng cho database, queue, bucket và các tài nguyên bên ngoài. Đặt `run ID + shard ID` vào tên schema hoặc namespace để tránh hai job cùng ghi một tập dữ liệu.

## 14. Những cách làm dễ che giấu lỗi

| Cách làm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chạy test theo thứ tự cố định để test sau nhận dữ liệu test trước | Suite phụ thuộc thứ tự và khó chạy riêng | Mỗi test tự tạo fixture và dữ liệu riêng |
| Dùng static mutable field để chia sẻ fixture | Trạng thái rò rỉ hoặc race condition | Tạo fixture riêng, dùng object bất biến |
| Dùng port hoặc file path cố định | Nhiều test/worker ghi đè hoặc bind trùng | Port động và `@TempDir` |
| Truncate database dùng chung trong `@BeforeEach` | Test này xóa dữ liệu test khác | Schema/tenant riêng hoặc cleanup theo owner |
| Dùng `Thread.sleep()` để chờ async | Flaky theo tải runner và làm chậm suite | Chờ condition/future/latch với timeout |
| Bật song song tối đa ngay lập tức | Hạ tầng quá tải, nhiều lỗi khó chẩn đoán | Tăng dần và đo theo từng lớp |
| Tăng retry để làm xanh pipeline | Che giấu race condition và test không ổn định | Giữ lần fail, tái hiện và sửa nguyên nhân |
| Dùng `@Isolated` cho mọi test | Mất lợi ích song song | Khóa đúng tài nguyên hoặc cô lập fixture |
| Chỉ chạy test thất bại riêng rồi kết luận đã sửa | Bỏ qua tương tác với test khác | Chạy lại suite theo seed và mức song song gây lỗi |
| Dùng một seed random duy nhất mãi mãi | Không khám phá các thứ tự khác | Seed ổn định cho PR, nhiều seed trong job định kỳ |

## 15. Checklist giữ kết quả độc lập

Trước khi bật hoặc tăng mức song song trong CI, hãy kiểm tra:

- [ ] Mỗi test có thể chạy riêng và không cần test khác chuẩn bị dữ liệu.
- [ ] Test tự tạo fixture và chỉ xác minh dữ liệu do nó sở hữu.
- [ ] Không có mutable static state hoặc singleton dùng chung ngoài ý muốn.
- [ ] System properties, locale, timezone và global setting được tránh hoặc khôi phục an toàn.
- [ ] Test dùng `Clock` hoặc đầu vào thời gian cố định khi cần kết quả xác định.
- [ ] Random seed có thể ghi nhận và tái hiện; dữ liệu random không làm thay đổi kết quả mong đợi ngoài kiểm soát.
- [ ] File dùng thư mục tạm riêng; port được cấp động.
- [ ] Database, queue, bucket và service có namespace riêng hoặc cơ chế đồng bộ rõ.
- [ ] Async test chờ tín hiệu hoàn tất với timeout, không dựa vào sleep tùy ý.
- [ ] Truy vấn và collection chỉ phụ thuộc thứ tự khi thứ tự đã được quy định rõ.
- [ ] Suite được chạy thử với thứ tự ngẫu nhiên và seed có thể tái hiện.
- [ ] JUnit parallelism và Gradle `maxParallelForks` được cấu hình có chủ đích.
- [ ] Tổng mức đồng thời giữa JUnit, Gradle và CI matrix nằm trong khả năng runner/dịch vụ.
- [ ] Tài nguyên dùng chung có `@ResourceLock`, `@Isolated` hoặc cơ chế isolation tương đương khi cần.
- [ ] CI lưu test report, seed, worker và thông tin cần thiết để điều tra.
- [ ] Test flaky được sửa ở nguyên nhân gốc; retry không được dùng để che giấu lỗi.

Một test suite tốt không cần được chạy theo một trình tự bí mật để đạt. Mỗi test phải tự quản lý trạng thái của mình, còn những tài nguyên thực sự dùng chung phải có quy tắc đồng bộ và giới hạn rõ. Khi thứ tự được thay đổi và mức song song được tăng dần mà kết quả vẫn ổn định, nhóm có thể tin cậy hơn vào cổng kiểm thử và rút ngắn thời gian phản hồi của CI.
