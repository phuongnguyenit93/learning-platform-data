# Bộ dữ liệu có thể tái tạo và hạt giống ngẫu nhiên được ghi nhận

## 1. Vì sao dữ liệu test cần tái tạo được?

Một test đáng tin cậy phải có thể chạy lại với cùng điều kiện và cho cùng kết quả. Nếu mỗi lần chạy test tạo ra dữ liệu khác nhau mà không lưu lại cách tạo, một lỗi xuất hiện trên CI có thể rất khó tái hiện trên máy lập trình viên.

Ví dụ, test tính tổng đơn hàng tạo ngẫu nhiên 20 dòng hàng. Một lần chạy có thể sinh giá trị hợp lệ, nhưng lần khác tạo số lượng hoặc giá trị biên làm lộ lỗi. Nếu CI chỉ báo test thất bại mà không ghi lại dữ liệu đã sinh, người sửa lỗi phải đoán bộ dữ liệu nào đã gây lỗi.

Một bộ dữ liệu có thể tái tạo giúp:

- Chạy lại chính xác tình huống đã làm test thất bại.
- Phân biệt lỗi sản phẩm với lỗi do dữ liệu đầu vào không hợp lệ.
- Giảm phụ thuộc vào thứ tự chạy test và trạng thái môi trường.
- Chia sẻ cùng một tình huống giữa máy lập trình viên và CI.
- Chuyển một trường hợp lỗi ngẫu nhiên thành test hồi quy cố định.

Trong Spring Framework Testing, tính tái tạo áp dụng cho unit test, service test, repository test, MVC/WebFlux test và integration test. Dữ liệu test có thể đến từ builder, factory, file JSON/CSV, SQL fixture, database container hoặc bộ sinh dữ liệu ngẫu nhiên.

Nguyên tắc quan trọng: nếu test dùng dữ liệu ngẫu nhiên, phải ghi nhận đủ thông tin để tạo lại dữ liệu đó.

## 2. Bộ dữ liệu xác định và bộ dữ liệu ngẫu nhiên

Có hai cách tạo fixture thường gặp.

### Fixture xác định

Fixture xác định có giá trị được khai báo rõ:

~~~java
Order order = new Order(
        "ORD-1001",
        "CUST-42",
        List.of(
                new OrderLine("BOOK-1", 2, new BigDecimal("15.00")),
                new OrderLine("PEN-1", 3, new BigDecimal("2.50"))
        )
);
~~~

Ưu điểm là người đọc biết ngay dữ liệu nào đang được kiểm tra. Fixture xác định phù hợp với test nghiệp vụ, test validation, test mapping và các trường hợp biên cần nêu rõ.

### Fixture sinh ngẫu nhiên

Fixture ngẫu nhiên tạo nhiều giá trị khác nhau trong một miền đã định nghĩa:

~~~java
Random random = new Random(12345L);

int quantity = 1 + random.nextInt(5);
long cents = random.nextInt(100_000);
BigDecimal price = BigDecimal.valueOf(cents, 2);
~~~

Ngẫu nhiên hữu ích khi cần thử nhiều tổ hợp đầu vào, kiểm tra invariant hoặc tìm lỗi chỉ xuất hiện ở một số tổ hợp. Nhưng nếu không kiểm soát seed và cách sinh, dữ liệu thay đổi qua mỗi lần chạy và làm test khó tái hiện.

Không phải test nào cũng nên dùng random. Một test kiểm tra quy tắc giảm giá ở đúng mức 10% nên có ví dụ rõ ràng. Một test kiểm tra tính tổng không âm với hàng nghìn tổ hợp có thể phù hợp với dữ liệu sinh ngẫu nhiên.

Cách làm hiệu quả là dùng fixture xác định cho hợp đồng nghiệp vụ quan trọng, sau đó bổ sung test sinh dữ liệu để mở rộng phạm vi tổ hợp.

## 3. Seed là gì?

**Seed** (hạt giống) là giá trị khởi tạo cho một bộ sinh số giả ngẫu nhiên. Từ cùng seed, một bộ sinh xác định có thể tạo ra cùng một chuỗi số nếu thuật toán và thứ tự gọi các phương thức giống nhau.

Ví dụ:

~~~java
Random first = new Random(20261113L);
Random second = new Random(20261113L);

assertThat(first.nextInt()).isEqualTo(second.nextInt());
assertThat(first.nextInt()).isEqualTo(second.nextInt());
~~~

Hai đối tượng Random có cùng seed. Khi các lời gọi được thực hiện theo cùng thứ tự, chúng tạo ra cùng chuỗi kết quả.

Seed không phải là toàn bộ dữ liệu test. Nó chỉ tái tạo chuỗi số của generator. Để tạo lại fixture, cần giữ nguyên cả:

- Thuật toán/generator được sử dụng.
- Seed.
- Thứ tự và số lượng các lần gọi generator.
- Phiên bản thư viện sinh dữ liệu nếu thư viện có thuật toán riêng.
- Quy tắc chuyển số ngẫu nhiên thành dữ liệu domain.
- Các tham số đầu vào khác như số lượng bản ghi, locale và timezone.

Nếu thêm một lần gọi nextInt() ở đầu hàm tạo fixture, mọi giá trị được sinh sau đó có thể thay đổi dù seed không đổi. Vì vậy, thay đổi thuật toán tạo dữ liệu cũng có thể làm một seed cũ tạo ra fixture khác.

## 4. Dùng java.util.Random với seed cố định

java.util.Random là lựa chọn đơn giản khi cần tạo chuỗi số giả ngẫu nhiên có thể tái tạo.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
}

final class OrderLineFactory {

    static List<OrderLine> create(long seed, int count) {
        Random random = new Random(seed);
        List<OrderLine> lines = new ArrayList<>();

        for (int index = 0; index < count; index++) {
            int quantity = 1 + random.nextInt(5);
            long cents = random.nextInt(100_000);
            BigDecimal price = BigDecimal.valueOf(cents, 2);

            lines.add(new OrderLine(
                    "SKU-" + index,
                    quantity,
                    price
            ));
        }

        return List.copyOf(lines);
    }
}
~~~

Mỗi lần gọi OrderLineFactory.create(20261113L, 10) sẽ tạo cùng danh sách theo cùng implementation và cùng thứ tự gọi generator. SKU được tạo từ chỉ số để không phụ thuộc thêm một lần random và không bị trùng trong fixture đó.

Một test có thể xác nhận invariant:

~~~java
@Test
void generatedOrderLinesHaveValidValues() {
    List<OrderLine> lines =
            OrderLineFactory.create(20261113L, 50);

    assertThat(lines).hasSize(50);
    assertThat(lines).allSatisfy(line -> {
        assertThat(line.quantity()).isBetween(1, 5);
        assertThat(line.unitPrice()).isGreaterThanOrEqualTo(BigDecimal.ZERO);
        assertThat(line.sku()).isNotBlank();
    });
}
~~~

Không nên tạo một Random static dùng chung cho toàn bộ test suite. Khi nhiều test dùng chung một generator, kết quả phụ thuộc test nào gọi trước và bao nhiêu lần. Hãy tạo generator riêng cho từng test hoặc từng fixture factory.

### Cùng seed nhưng khác thứ tự gọi

Đoạn code sau không tạo cùng dữ liệu vì thứ tự gọi khác nhau:

~~~java
Random random = new Random(seed);

int quantity = random.nextInt(5);
int cents = random.nextInt(100_000);
~~~

~~~java
Random random = new Random(seed);

int cents = random.nextInt(100_000);
int quantity = random.nextInt(5);
~~~

Cả hai dùng cùng seed nhưng gán các số được sinh vào field khác nhau. Khi thay đổi code tạo fixture, cần coi đó là thay đổi có thể ảnh hưởng khả năng replay.

## 5. Đóng gói seed trong TestDataFactory

Không nên lặp lại logic khởi tạo generator trong từng test. Có thể tạo một factory nhận seed rõ ràng:

~~~java
public final class TestDataFactory {

    private final Random random;

    public TestDataFactory(long seed) {
        this.random = new Random(seed);
    }

    public Customer customer(int index) {
        return new Customer(
                "customer-" + index,
                "user" + index + "@example.test",
                18 + random.nextInt(63)
        );
    }

    public List<Customer> customers(int count) {
        return IntStream.range(0, count)
                .mapToObj(this::customer)
                .toList();
    }
}
~~~

Test sử dụng factory:

~~~java
@Test
void shouldHandleManyCustomers() {
    long seed = 20261113L;
    TestDataFactory data = new TestDataFactory(seed);

    List<Customer> customers = data.customers(100);

    assertThat(customers).hasSize(100);
    assertThat(customers).allSatisfy(customer ->
            assertThat(customer.age()).isBetween(18, 80)
    );
}
~~~

Factory giữ generator riêng, do đó test không phụ thuộc generator của test khác. Truyền seed qua constructor cũng giúp đọc được nguồn dữ liệu ngay tại nơi khởi tạo fixture.

Một factory có thể tạo nhiều loại dữ liệu liên quan, nhưng cần giữ thứ tự gọi rõ ràng. Nếu một test tạo customer, order và payment từ cùng một generator, thay đổi cách tạo customer có thể làm dữ liệu order/payment đổi theo. Với fixture lớn, có thể dùng seed riêng cho từng nhóm dữ liệu để giảm phạm vi ảnh hưởng.

## 6. Ghi nhận seed khi test chạy

Một test ngẫu nhiên cần báo seed trong kết quả chạy, đặc biệt khi test thất bại trên CI. Đừng chỉ để seed trong source code hoặc trong log debug không được lưu.

JUnit Jupiter cung cấp TestReporter để ghi thông tin vào test report:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestReporter;

@Test
void generatedDataShouldPreserveOrderInvariants(TestReporter reporter) {
    long seed = 20261113L;
    reporter.publishEntry("random-seed", Long.toString(seed));

    TestDataFactory data = new TestDataFactory(seed);
    List<Customer> customers = data.customers(100);

    assertThat(customers).allSatisfy(customer ->
            assertThat(customer.age()).isBetween(18, 80)
    );
}
~~~

Có thể ghi thêm thông tin giúp replay:

~~~java
reporter.publishEntry("generator", "java.util.Random");
reporter.publishEntry("fixture-version", "customer-factory-v2");
reporter.publishEntry("record-count", "100");
reporter.publishEntry("random-seed", Long.toString(seed));
~~~

Nếu test dùng thư viện Faker hoặc property-based testing framework, ghi tên generator/framework và phiên bản liên quan. Với dữ liệu phức tạp, lưu cả test method, tên fixture factory và tham số tạo dữ liệu.

Nên ghi seed trước khi thực hiện phần test có thể thất bại. Nếu chỉ log sau assertion cuối cùng, lỗi có thể xảy ra trước khi seed được ghi nhận.

### Seed mặc định và seed từ cấu hình

Có thể dùng một seed mặc định ổn định, đồng thời cho phép CI hoặc lập trình viên truyền seed khác qua system property:

~~~java
final class TestSeeds {

    private static final long DEFAULT_SEED = 20261113L;

    static long current() {
        String configured = System.getProperty("test.seed");
        return configured == null
                ? DEFAULT_SEED
                : Long.parseLong(configured);
    }

    private TestSeeds() {
    }
}
~~~

Test lấy seed từ cấu hình:

~~~java
@Test
void shouldProcessGeneratedOrders(TestReporter reporter) {
    long seed = TestSeeds.current();
    reporter.publishEntry("random-seed", Long.toString(seed));

    List<OrderLine> lines =
            OrderLineFactory.create(seed, 100);

    assertThat(lines).hasSize(100);
}
~~~

Seed mặc định giúp chạy local ổn định. Khi cần thử một bộ dữ liệu khác, truyền seed mới mà không sửa source code.

## 7. Truyền seed vào test process trên CI

Nếu dùng Gradle, cần bảo đảm system property từ Gradle process được chuyển tới test worker:

~~~groovy
tasks.test {
    systemProperty(
        "test.seed",
        System.getProperty("test.seed", "20261113")
    )
}
~~~

Sau đó có thể chạy một test cụ thể với seed đã ghi nhận:

~~~bash
./gradlew test --tests "com.example.OrderServiceTest" -Dtest.seed=847291
~~~

Lệnh trên chỉ có tác dụng nếu test.seed đã được chuyển tới test worker như cấu hình Gradle ở trên. Nếu dự án có nhiều test task, hãy truyền property cho task tương ứng.

Với Maven Surefire, có thể cấu hình systemPropertyVariables để chuyển property vào JVM test. Chạy lại bằng property tương ứng, ví dụ:

~~~bash
mvn -Dtest.seed=847291 -Dtest=OrderServiceTest test
~~~

Cần kiểm tra cấu hình plugin của dự án để chắc chắn property có mặt trong JVM chạy test. Việc truyền -D cho Maven/Gradle không tự động bảo đảm mọi test worker nhận được property nếu build chưa cấu hình chuyển tiếp.

## 8. Tạo seed riêng cho từng test và tránh phụ thuộc thứ tự

Một lỗi phổ biến là dùng một generator static:

~~~java
static final Random RANDOM = new Random(12345L);
~~~

Mỗi test tiêu thụ một số lượng random khác nhau. Nếu thứ tự test thay đổi, dữ liệu của test phía sau cũng thay đổi. Chạy song song còn có thể làm thứ tự gọi generator không xác định.

Thay vào đó, tạo generator riêng cho từng test:

~~~java
@Test
void shouldCalculateOneOrder() {
    Random random = new Random(1001L);
    // Tạo fixture cho riêng test này.
}

@Test
void shouldCalculateAnotherOrder() {
    Random random = new Random(1002L);
    // Tạo fixture độc lập.
}
~~~

Nếu muốn dùng một seed gốc cho cả suite, có thể tạo seed con ổn định theo tên test hoặc truyền seed riêng cho từng test case. Khi tạo seed con, hãy dùng phép biến đổi xác định và ghi lại seed cuối cùng được dùng để sinh dữ liệu.

Không nên dùng String.hashCode() như một định danh duy nhất nếu tên test có thể trùng hash. Hash chỉ nên là một thành phần trong quy tắc tạo seed; khi cần chắc chắn, lưu seed cụ thể cho từng test case.

### SplittableRandom và generator độc lập

SplittableRandom hỗ trợ tạo các generator con bằng split(), phù hợp khi cần chia luồng sinh dữ liệu thành các nhánh độc lập:

~~~java
SplittableRandom root = new SplittableRandom(20261113L);

SplittableRandom customerRandom = root.split();
SplittableRandom orderRandom = root.split();
~~~

Mỗi generator con có thể được giao cho một nhóm fixture riêng. Cách này giảm việc một nhóm dữ liệu tiêu thụ random làm thay đổi nhóm khác. Để replay chính xác, giữ nguyên cách và thứ tự tạo generator con.

SplittableRandom không thread-safe. Không chia sẻ cùng instance giữa nhiều thread. Hãy tạo hoặc split generator riêng cho từng tác vụ.

## 9. Các generator Java và khi nào dùng

| Generator | Có thể replay bằng seed? | Lưu ý |
|---|---|---|
| java.util.Random | Có | Cùng seed và cùng chuỗi lời gọi tạo cùng chuỗi số |
| SplittableRandom | Có khi giữ nguyên cách split và thứ tự dùng | Hữu ích để chia luồng dữ liệu; không thread-safe |
| RandomGenerator | Tùy implementation được chọn | Ghi cả tên thuật toán/generator cùng seed |
| ThreadLocalRandom | Không hỗ trợ đặt seed theo cách thông thường | Không phù hợp cho fixture cần replay |
| SecureRandom | Không nên dùng để tạo fixture có tính tái tạo | Dành cho nhu cầu mật mã; tính ngẫu nhiên không phải mục tiêu replay |
| Math.random() | Không có API truyền seed trực tiếp | Tránh dùng trong test cần tái tạo |

Với Java 17 trở lên, API RandomGenerator cho phép làm việc với nhiều thuật toán:

~~~java
RandomGenerator generator =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(20261113L);
~~~

Khi dùng generator theo tên, ghi cả tên thuật toán và seed. Đừng chỉ ghi seed rồi sau này đổi implementation mà vẫn kỳ vọng nhận được cùng dữ liệu.

Không dùng SecureRandom hoặc ThreadLocalRandom cho dữ liệu test cần tái tạo. Nếu một test đang kiểm tra chức năng mật mã, hãy tách test tính đúng của thuật toán khỏi test tạo fixture ngẫu nhiên; dùng test vector cố định cho các kết quả mật mã cần xác nhận.

## 10. Dùng Faker hoặc thư viện sinh dữ liệu

Thư viện như Java Faker/DataFaker có thể tạo tên, địa chỉ, số điện thoại và dữ liệu có vẻ thực tế. Đây là cách hữu ích khi cần khối lượng fixture lớn, nhưng cần khởi tạo thư viện với random source có seed.

Ví dụ với Java Faker:

~~~java
long seed = 20261113L;
Faker faker = new Faker(new Random(seed));

String name = faker.name().fullName();
String city = faker.address().city();
~~~

Nếu dùng một Faker instance riêng cho mỗi test, seed được kiểm soát và các lời gọi theo cùng thứ tự có thể tái tạo dữ liệu theo phiên bản thư viện đang dùng.

Khi nâng cấp Faker/DataFaker, thuật toán hoặc danh sách dữ liệu nội bộ có thể thay đổi. Vì vậy, seed cũ chưa chắc tạo ra đúng chuỗi văn bản cũ trên phiên bản thư viện mới. Ghi phiên bản dependency trong build report và cố định version qua dependency management.

Không nên dùng Faker để sinh mọi dữ liệu. Với field có quy tắc nghiệp vụ, hãy tạo dữ liệu theo domain constraint. Ví dụ, một email hợp lệ chưa chắc là email đã được đăng ký trong hệ thống; một địa chỉ ngẫu nhiên chưa chắc thuộc vùng giao hàng. Faker tạo dữ liệu hình thức, không tự bảo đảm tính hợp lệ của domain.


## 11. Dữ liệu xác định trong Spring integration test

Khi test dùng Spring ApplicationContext, nên tạo fixture ở một nơi dễ kiểm soát như test data builder, repository fixture factory hoặc SQL script.

Ví dụ một repository test có thể chuẩn bị dữ liệu cố định:

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldFindCustomerByEmail() {
        Customer customer = new Customer(
                "C-1001",
                "linh@example.test",
                "Linh"
        );
        repository.save(customer);

        assertThat(repository.findByEmail("linh@example.test"))
                .contains(customer);
    }
}
~~~

Với test repository chạy trong transaction do Spring Test quản lý, dữ liệu có thể được rollback sau method nếu transaction manager và cách truy cập dữ liệu nằm trong cùng transaction.

Một lựa chọn khác là SQL fixture:

~~~java
@Test
@Sql("/sql/customer-fixture.sql")
void shouldReturnTheSeededCustomer() {
    assertThat(repository.findByEmail("linh@example.test"))
            .isPresent();
}
~~~

File SQL có thể tạo cùng dữ liệu ở mọi lần chạy, giúp việc tái tạo đơn giản. Nếu nhiều test dùng chung database hoặc chạy song song, hãy dùng khóa riêng theo test hoặc dọn đúng fixture. Không dùng một script cleanup xóa toàn bộ bảng trong khi test khác có thể đang sử dụng database.

### Transaction test không bao bọc request HTTP thật

Nếu test gửi request tới server bằng RANDOM_PORT, request được xử lý trong luồng server và transaction riêng. Transaction của test method không tự truyền qua ranh giới HTTP.

Vì vậy, dữ liệu do endpoint tạo có thể vẫn còn sau khi test method rollback transaction của chính nó. Với HTTP integration test, hãy:

- Tạo fixture riêng trước request hoặc qua endpoint.
- Ghi lại id/namespace của fixture.
- Gửi request qua HTTP.
- Cleanup đúng dữ liệu sau test.
- Dùng database/schema riêng khi test chạy song song hoặc cần isolation mạnh.

Không dựa vào @Transactional trên test để tự động rollback dữ liệu được ghi bởi request tới server thật.

## 12. Dùng namespace và ID xác định cho fixture

Dữ liệu test cần vừa tái tạo được vừa không va chạm với test khác. Một cách là tạo namespace dựa trên tên test và seed, sau đó thêm chỉ số tăng dần:

~~~java
final class FixtureIds {

    private final String namespace;
    private int sequence;

    FixtureIds(String testName, long seed) {
        this.namespace = testName + "-" + seed;
    }

    String next(String prefix) {
        return namespace + "-" + prefix + "-" + sequence++;
    }
}
~~~

Ví dụ, test có thể tạo các ID như:

~~~text
OrderServiceTest-847291-customer-0
OrderServiceTest-847291-order-1
OrderServiceTest-847291-payment-2
~~~

Namespace xác định giúp tạo lại cùng ID khi replay cùng test và seed. Nếu nhiều worker chạy cùng một test/seed trên cùng database, cần thêm namespace cho worker hoặc tách database/schema theo worker. Thông tin worker cũng phải được ghi lại để có thể dựng lại cùng fixture.

Không dùng ID ngẫu nhiên không có seed như UUID.randomUUID() nếu mục tiêu là tạo lại chính xác toàn bộ fixture. Nếu cần UUID, có thể dùng UUID cố định trong test, hoặc sinh UUID từ một nguồn deterministic đã được quản lý rõ.

## 13. Cố định thời gian, locale và timezone

Seed chỉ kiểm soát generator. Nó không làm test ổn định nếu kết quả còn phụ thuộc đồng hồ hệ thống, timezone hoặc locale của máy chạy CI.

### Dùng Clock thay cho thời gian hệ thống

Nếu service gọi LocalDate.now() hoặc Instant.now() trực tiếp, kết quả có thể thay đổi theo ngày chạy test. Hãy inject Clock:

~~~java
@Configuration
class TimeConfig {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Trong test, thay Clock bằng thời điểm cố định:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
~~~

Có thể dùng @TestBean hoặc @MockitoBean để cung cấp clock test nếu ứng dụng đã inject Clock qua constructor. Khi đó, test không phụ thuộc ngày thực tế hoặc thời điểm chạy trên CI.

### Cố định timezone và locale

Khi test format ngày, số hoặc tiền tệ, hãy chỉ định rõ locale và zone:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.UK);

String value = formatter
        .withZone(ZoneId.of("UTC"))
        .format(Instant.parse("2026-01-15T10:00:00Z"));
~~~

Không dựa vào Locale.getDefault() hoặc ZoneId.systemDefault() trong assertion nếu API yêu cầu một định dạng cố định. Cùng một Instant có thể hiển thị thành ngày khác khi timezone khác; dấu thập phân và cách nhóm số cũng có thể khác theo locale.

## 14. Kiểm tra dữ liệu ngẫu nhiên bằng invariant

Khi dữ liệu được sinh ngẫu nhiên, thường không nên hard-code toàn bộ kết quả mong đợi nếu mục tiêu là kiểm tra một quy tắc tổng quát. Hãy xác định invariant phải luôn đúng.

Ví dụ, với mỗi dòng đơn hàng:

- Số lượng phải lớn hơn 0.
- Đơn giá không âm.
- Tổng dòng bằng đơn giá nhân số lượng.
- Tổng đơn hàng bằng tổng các dòng.
- Tổng tiền không vượt giới hạn domain đã định nghĩa.

~~~java
@Test
void generatedOrderTotalMustEqualSumOfLines() {
    long seed = 847291L;
    List<OrderLine> lines = OrderLineFactory.create(seed, 100);

    BigDecimal expected = lines.stream()
            .map(line -> line.unitPrice()
                    .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

    BigDecimal actual = orderCalculator.total(lines);

    assertThat(actual).isEqualByComparingTo(expected);
}
~~~

Ở đây, dữ liệu được sinh theo seed nhưng expected được tính bằng một phép tổng độc lập từ các dòng đầu vào. Tránh gọi cùng một method production để tạo cả actual và expected; nếu hai phía dùng chung logic sai, test có thể vẫn pass.

Đối với thuật toán có kết quả chuẩn đã biết, vẫn nên giữ test ví dụ cố định. Random test bổ sung phạm vi đầu vào; nó không thay thế các ví dụ minh họa quy tắc nghiệp vụ.

## 15. Property-based testing và seed được ghi nhận

Property-based testing sinh nhiều đầu vào để kiểm tra một thuộc tính tổng quát thay vì chỉ chạy một vài ví dụ do người viết test chọn.

Ví dụ, một thuộc tính có thể là: với mọi giá trị tiền không âm trong miền hỗ trợ, áp dụng giảm giá 0% phải giữ nguyên giá gốc.

Với jqwik:

~~~java
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.LongRange;

class DiscountProperties {

    @Property(tries = 200)
    void zeroDiscountKeepsTheOriginalPrice(
            @ForAll @LongRange(min = 0, max = 1_000_000_00L) long cents
    ) {
        BigDecimal price = BigDecimal.valueOf(cents, 2);

        assertThat(discountService.apply(price, 0))
                .isEqualByComparingTo(price);
    }
}
~~~

Property-based framework có thể tạo nhiều giá trị và thường có cơ chế shrinking: khi tìm thấy đầu vào gây lỗi, framework cố rút gọn nó thành trường hợp nhỏ hơn, dễ hiểu hơn.

Với test ngẫu nhiên kiểu này, seed có vai trò quan trọng. Framework như jqwik báo seed trong kết quả để người phát triển có thể chạy lại cùng một lần sinh. Khi lưu lỗi CI, hãy giữ:

- Tên property/test method.
- Seed mà framework báo.
- Số lần thử và cấu hình generator.
- Phiên bản jqwik và JDK.
- Giá trị cụ thể đã làm property thất bại nếu report cung cấp.

Có thể ghim seed vào cấu hình property khi cần replay một lỗi. Cú pháp replay cụ thể phụ thuộc phiên bản jqwik; hãy dùng seed mà report cung cấp và API/configuration của version đang dùng.

### Khi nào dùng property-based testing?

Phù hợp khi:

- Có invariant tổng quát áp dụng cho nhiều đầu vào.
- Không gian tổ hợp lớn và khó liệt kê thủ công.
- Cần tìm lỗi ở biên hoặc kết hợp nhiều field.
- Muốn framework thu nhỏ đầu vào thất bại thành ví dụ dễ chẩn đoán.

Không nên dùng property test để thay mọi test nghiệp vụ. Các kịch bản như đơn hàng bị từ chối vì thiếu tồn kho, người dùng không có quyền hoặc thanh toán đã hoàn tất vẫn cần ví dụ cố định diễn đạt rõ kỳ vọng.

## 16. Dữ liệu ngẫu nhiên hợp lệ phải tuân thủ domain constraint

Sinh số trong một khoảng không tự động tạo ra dữ liệu hợp lệ. Ví dụ:

- Tuổi trong khoảng 18–80 có thể hợp lệ, nhưng ngày sinh phải tương ứng với tuổi đó.
- Số lượng dương vẫn có thể vượt giới hạn tồn kho.
- Email đúng định dạng có thể trùng với một tài khoản đã tồn tại.
- Ngày kết thúc phải sau ngày bắt đầu.
- Tổng tiền cần tuân thủ quy tắc scale và rounding của tiền tệ.

Nên đặt quy tắc domain ngay trong fixture factory:

~~~java
static Subscription subscription(Random random) {
    LocalDate start = LocalDate.of(2026, 1, 1)
            .plusDays(random.nextInt(365));
    LocalDate end = start.plusDays(1 + random.nextInt(30));

    return new Subscription(start, end);
}
~~~

Generator nên tạo dữ liệu hợp lệ theo mặc định. Các test negative case có thể tạo dữ liệu sai có chủ đích để kiểm tra validation. Không nên để phần lớn test random thất bại vì generator vô tình tạo dữ liệu không hợp lệ ngoài mục tiêu đang kiểm tra.


## 17. Chiến lược seed cho local, pull request và nightly CI

Một quy trình CI tốt cần cân bằng giữa khả năng tái tạo và khả năng khám phá nhiều dữ liệu.

Có thể dùng ba chế độ:

| Chế độ | Seed | Mục tiêu |
|---|---|---|
| Local mặc định | Seed ổn định trong cấu hình | Mọi người chạy lại cùng bộ dữ liệu khi chưa chỉ định seed |
| Pull request | Seed ổn định hoặc seed theo build đã ghi nhận | Kết quả review có thể tái tạo |
| Nightly/stress | Seed thay đổi theo lần chạy và luôn được lưu | Mở rộng phạm vi tổ hợp đầu vào để tìm lỗi hiếm |

Nếu nightly CI dùng seed thay đổi, hãy ghi seed vào test report và log tổng hợp của build. Khi một test thất bại, tạo một lần chạy replay dùng đúng seed thay vì tiếp tục chạy với seed mới.

Một cách tạo seed theo build là dùng build number hoặc một giá trị do CI cấp. Tuy nhiên, không được chỉ dựa vào build number nếu không ghi lại giá trị thực tế đã truyền tới test worker. Report nên cho biết seed cuối cùng mà generator đã nhận.

Không nên thay seed ở mọi lần chạy mà không lưu lại. Khi đó test có thể phát hiện lỗi nhưng không cung cấp đủ dữ liệu để sửa lỗi.

## 18. Ghi lại seed và thông tin fixture trong CI

Ngoài JUnit TestReporter, có thể ghi seed bằng logger để thông tin xuất hiện trong log của CI:

~~~java
long seed = TestSeeds.current();

logger.info(
        "Running randomized order test with seed={}, fixtureVersion={}",
        seed,
        "order-lines-v3"
);
~~~

Một record replay hữu ích nên gồm:

| Trường | Ví dụ | Lý do |
|---|---|---|
| Test class/method | OrderCalculatorTest.generatedOrderTotal | Xác định test cần chạy lại |
| Seed | 847291 | Tạo lại chuỗi số |
| Generator | java.util.Random | Xác định thuật toán |
| Fixture version | order-lines-v3 | Xác định quy tắc chuyển số thành domain data |
| Record count | 100 | Xác định kích thước dữ liệu |
| JDK | 21.x | Ghi nhận môi trường chạy |
| Dependency version | DataFaker 2.x | Cần thiết nếu dùng thư viện sinh dữ liệu |
| CI build/run ID | pipeline-1842 | Tìm log và artifact gốc |

Nếu test thất bại vì một record cụ thể, nên ghi cả giá trị đã sinh hoặc lưu fixture vào artifact của build. Seed có thể không đủ nếu generator phụ thuộc thư viện ngoài, dữ liệu locale hoặc thuật toán thay đổi theo version.

Không ghi thông tin nhạy cảm thật vào test report. Dữ liệu test nên dùng địa chỉ và định danh giả lập như example.test, không lấy thông tin cá nhân hoặc dữ liệu production.

## 19. Quy trình tái hiện lỗi random từ CI

Khi CI báo một test random thất bại, hãy làm theo quy trình có thể lặp lại:

1. Mở report và tìm tên test, seed, generator và fixture version.
2. Xác định đúng JDK và dependency version của build thất bại.
3. Chạy riêng test đó với seed đã ghi nhận.
4. Xác nhận test tái hiện cùng lỗi.
5. Ghi lại đầu vào nhỏ nhất có thể nếu property-based framework đã shrink dữ liệu.
6. Sửa lỗi và thêm test hồi quy cho trường hợp cụ thể.
7. Giữ test random để tiếp tục khám phá các tổ hợp khác nếu nó mang lại giá trị.

Ví dụ chạy lại với Gradle:

~~~bash
./gradlew test --tests "com.example.OrderCalculatorTest" -Dtest.seed=847291
~~~

Nếu test dùng seed riêng được framework quản lý, truyền seed theo cơ chế của framework đó thay vì chỉ truyền system property chung. Một seed của jqwik không nhất thiết giống seed của factory dùng java.util.Random.

### Khi không thể tái hiện

Nếu cùng seed nhưng không tái hiện được, hãy kiểm tra các yếu tố khác ngoài seed:

- Test có dùng generator static hoặc chia sẻ giữa các test không?
- Thứ tự chạy hoặc số lần gọi random có khác không?
- Có test khác ghi vào cùng database/cache/queue không?
- Có thời gian hệ thống, timezone hoặc locale ảnh hưởng kết quả không?
- Có tác vụ bất đồng bộ chưa hoàn tất khi test kết thúc không?
- Có phiên bản JDK hoặc thư viện sinh dữ liệu khác không?
- Có dữ liệu ngoài test hoặc service bên ngoài thay đổi không?

Seed chỉ tái tạo phần ngẫu nhiên mà nó kiểm soát. Nó không tự làm môi trường chạy trở nên xác định.

## 20. Cô lập dữ liệu khi chạy song song

CI thường chạy test class hoặc test method song song để giảm thời gian. Nếu các test ghi vào cùng database, file, queue hoặc mock state, dữ liệu có thể va chạm dù mỗi test có seed cố định.

Một số cách cô lập:

- Tạo ID riêng theo test class, test method, seed và worker.
- Dùng database/schema/container riêng cho từng test suite hoặc worker.
- Dọn đúng bản ghi do test tạo thay vì xóa toàn bộ bảng.
- Dùng thư mục tạm riêng cho từng test.
- Dùng topic/queue có namespace riêng.
- Không chia sẻ mutable Random hoặc SplittableRandom giữa các thread.
- Không dùng chung một fixture factory có state giữa các test chạy đồng thời.

Nếu hai worker chạy cùng test với cùng seed, chúng có thể tạo cùng ID. Vì vậy, seed không phải định danh duy nhất cho resource bên ngoài. Thêm worker namespace hoặc tách database là cần thiết khi các lần chạy đồng thời chia sẻ một resource.

### Tránh test phụ thuộc thứ tự

Một test không nên cần test khác chạy trước để tạo fixture hoặc reset state. Hãy để mỗi test tự tạo dữ liệu cần thiết và cleanup theo phạm vi của mình.

Context caching của Spring giúp tiết kiệm thời gian nạp ApplicationContext, nhưng không tự làm sạch database, Redis, file hoặc message broker. Các tài nguyên bên ngoài context vẫn cần được quản lý độc lập.

## 21. Các nguồn nondeterminism khác ngoài random

Một seed được ghi nhận vẫn chưa đủ nếu test phụ thuộc vào yếu tố môi trường không cố định.

| Nguồn thay đổi | Ví dụ | Cách kiểm soát |
|---|---|---|
| Đồng hồ hệ thống | Đơn hàng hết hạn theo ngày hiện tại | Inject Clock và dùng Clock.fixed |
| Timezone | Ngày hiển thị khác giữa máy local và CI | Dùng ZoneId cụ thể |
| Locale | Dấu thập phân hoặc tên tháng khác nhau | Chỉ định Locale rõ ràng |
| Thứ tự collection | Duyệt HashMap và giả định thứ tự | Sort theo key trước khi assert |
| Database state | Bản ghi cũ còn sót lại | Fixture riêng, transaction phù hợp và cleanup |
| Sequence/identity | ID tăng khác nhau giữa lần chạy | Không assert ID tự sinh cố định nếu không phải contract |
| Concurrency | Race condition thay đổi thứ tự event | Dùng latch/barrier và assertion theo contract |
| Port mạng | Server chọn port khác | Lấy port được inject hoặc URL từ server fixture |
| External service | Response thay đổi theo thời gian | Stub bằng server local hoặc fixture xác định |
| File system | Đường dẫn hoặc nội dung file cũ | Dùng temporary directory và dọn sau test |

Khi test kiểm tra thứ tự xử lý bất đồng bộ, không nên dùng Thread.sleep() để hy vọng các tác vụ hoàn tất đúng lúc. Dùng latch, barrier, publisher có điều khiển hoặc Awaitility với deadline rõ ràng.

## 22. Chuyển một lỗi random thành test hồi quy

Khi random test tìm được lỗi, hãy giữ lại một ví dụ cố định để lỗi đó không biến mất khi seed hoặc generator thay đổi.

Ví dụ, random test tìm ra trường hợp tổng tiền bị sai khi số lượng rất lớn. Sau khi xác định input cụ thể, thêm test rõ ràng:

~~~java
@Test
void shouldCalculateTotalForLargeQuantities() {
    List<OrderLine> lines = List.of(
            new OrderLine(
                    "SKU-LARGE",
                    100_000,
                    new BigDecimal("999.99")
            )
    );

    assertThat(orderCalculator.total(lines))
            .isEqualByComparingTo("99999000.00");
}
~~~

Sau đó vẫn có thể giữ random/property test để tìm thêm tổ hợp. Test hồi quy cố định bảo vệ trường hợp đã biết và làm rõ quy tắc; test random tiếp tục khám phá miền đầu vào rộng hơn.

Nếu lỗi chỉ tái hiện với một chuỗi nhiều thao tác, lưu seed cùng test method và fixture version. Nếu chuỗi đó phụ thuộc trạng thái ngoài, hãy lưu thêm dữ liệu đầu vào hoặc event sequence để tái tạo đầy đủ.

## 23. Checklist sử dụng dữ liệu random có thể tái tạo

Trước khi đưa một random test vào CI, hãy xác định:

- Generator nào được dùng và có hỗ trợ seed hay không.
- Seed lấy từ đâu: hằng số, system property hay CI build.
- Seed được ghi ở đâu trong report/log.
- Factory có state riêng cho từng test hay không.
- Các giá trị sinh ra có tuân thủ domain constraint không.
- Fixture có ID/namespace tránh va chạm khi chạy song song không.
- Có thể chạy riêng test thất bại với seed đã ghi nhận không.
- Có lưu generator version và fixture version nếu cần không.
- Các nguồn khác như clock, locale, timezone và database state đã được kiểm soát chưa.
- Trường hợp lỗi đã biết có test hồi quy xác định chưa.

Không cần sinh hàng triệu bản ghi cho mọi test. Hãy chọn kích thước dữ liệu phù hợp với invariant cần xác nhận và dùng stress/load test riêng khi cần kiểm tra giới hạn hiệu năng.

## 24. Một mẫu test hoàn chỉnh có thể replay

Ví dụ sau kết hợp seed từ system property, TestReporter và fixture factory:

~~~java
@SpringBootTest
class OrderCalculatorRandomizedTest {

    private static final long DEFAULT_SEED = 20261113L;

    @Autowired
    private OrderCalculator orderCalculator;

    @Test
    void totalMustMatchTheSumOfGeneratedLines(TestReporter reporter) {
        long seed = Long.parseLong(
                System.getProperty(
                        "test.seed",
                        Long.toString(DEFAULT_SEED)
                )
        );

        reporter.publishEntry("random-seed", Long.toString(seed));
        reporter.publishEntry("generator", "java.util.Random");
        reporter.publishEntry("fixture-version", "order-lines-v1");

        List<OrderLine> lines = OrderLineFactory.create(seed, 100);

        BigDecimal expected = lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal actual = orderCalculator.total(lines);

        assertThat(actual).isEqualByComparingTo(expected);
    }
}
~~~

Khi test thất bại trên CI, lấy giá trị random-seed từ report và chạy lại đúng test với system property tương ứng. Cần bảo đảm Gradle/Maven đã chuyển property vào test process.

Ví dụ này kiểm tra tổng của dữ liệu được sinh. Trong dự án thực tế, có thể bổ sung các assertion cho giới hạn domain, rounding, số lượng, trạng thái đơn hàng và cách xử lý dữ liệu rỗng. Hãy giữ expected calculation độc lập với implementation được kiểm tra.

## 25. Nguyên tắc duy trì bộ dữ liệu tái tạo được

- Ưu tiên fixture cố định cho các kịch bản nghiệp vụ cụ thể.
- Dùng random cho việc khám phá nhiều tổ hợp và kiểm tra invariant.
- Tạo generator riêng cho mỗi test hoặc mỗi nhánh fixture.
- Ghi seed trước khi assertion có thể thất bại.
- Ghi tên thuật toán, fixture version và thư viện sinh dữ liệu khi cần.
- Truyền seed từ CI vào test worker một cách rõ ràng.
- Cô lập database, queue, file và ID khi chạy song song.
- Cố định Clock, timezone, locale và thứ tự dữ liệu khi chúng ảnh hưởng kết quả.
- Replay lỗi CI bằng seed đã ghi nhận, sau đó thêm test hồi quy xác định.
- Giữ dữ liệu test giả lập và không dùng dữ liệu production nhạy cảm.

Một bộ dữ liệu test tốt vừa giúp test khám phá nhiều tình huống, vừa cho phép tái tạo chính xác trường hợp đã thất bại. Seed được ghi nhận là điểm bắt đầu; generator, quy tắc tạo fixture và môi trường chạy cũng cần được kiểm soát để CI có thể cung cấp một lỗi có thể điều tra và sửa chữa.

