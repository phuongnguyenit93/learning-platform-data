# Giữ test độc lập với thứ tự chạy và dịch vụ ngoài không liên quan

Một bài kiểm thử Spring Boot đáng tin cậy phải cho cùng kết quả khi được chạy **một mình**, chạy cùng cả bộ test, thay đổi thứ tự thực thi hoặc chạy lại trên máy CI sạch. Kết quả cũng không nên phụ thuộc vào việc một dịch vụ bên ngoài **không liên quan đến điều đang kiểm thử** đang hoạt động hay bị lỗi.

Đây là hai dạng độc lập liên quan chặt chẽ:

- **Độc lập với thứ tự chạy:** test A không cần test B thực thi trước để chuẩn bị trạng thái, và không làm trạng thái rò rỉ sang test C.
- **Độc lập với hạ tầng không thuộc phạm vi:** unit test logic tính giá không cần mạng, database thật, SMTP, hệ thống thanh toán hay một service khác khởi động chỉ để dựng được đối tượng cần kiểm thử.

Mục tiêu không phải loại bỏ hoàn toàn integration test. Mục tiêu là **chọn đúng ranh giới kiểm thử**, giữ mọi đầu vào và tác dụng phụ có thể kiểm soát, rồi chỉ sử dụng dịch vụ thật ở những bài test thực sự cần xác nhận sự tích hợp đó.

## 1. Thế nào là test độc lập?

Hãy tưởng tượng các lệnh sau:

~~~bash
./gradlew test --tests "*PricingServiceTest"
./gradlew test
~~~

Nếu một test thành công khi chạy cả bộ nhưng thất bại khi chạy riêng, có thể nó đang phụ thuộc vào trạng thái mà một test khác vô tình tạo ra. Nếu chạy riêng thành công nhưng đôi lúc thất bại khi chạy cả bộ, có thể các test đang chia sẻ database, cache, file tạm, static field hoặc những tài nguyên dùng chung.

Một test độc lập nên tự thiết lập **tiền điều kiện**, thực hiện **hành vi cần kiểm tra**, rồi xác nhận kết quả và **không để lại tác động không kiểm soát** cho test khác.

Có thể mô tả:

~~~text
Test A:
    Arrange A -> Act A -> Assert A -> Cleanup A

Test B:
    Arrange B -> Act B -> Assert B -> Cleanup B

Đổi thứ tự A và B không làm kết quả thay đổi.
~~~

Trái lại, một thiết kế phụ thuộc thứ tự:

~~~text
Test A: tạo user "alice" trong database chung
Test B: tìm user "alice" và cập nhật
Test C: xóa user "alice"
~~~

Nếu B chỉ chạy được sau A và C phải chạy sau B, đó là **một kịch bản nhiều bước bị tách thành ba test có phụ thuộc**, chứ không phải ba test độc lập.

Nếu muốn kiểm tra một luồng tạo → cập nhật → xóa, hãy thực hiện cả ba bước trong **một test có fixture của riêng nó**, hoặc viết integration test dạng workflow rõ ràng với dữ liệu và cleanup riêng.

## 2. Những nguồn gây test không ổn định

Một số nguyên nhân phổ biến:

| Nguồn phụ thuộc | Ví dụ | Hậu quả |
|---|---|---|
| Static/global state | Danh sách `static` dùng chung | Test sau đọc dữ liệu test trước |
| Database chung | Entity cố định cùng ID/email | Trùng khóa, test chạy khác thứ tự thì fail |
| Cache chung | Test A ghi cache, B mong cache rỗng | Assertion phụ thuộc thứ tự |
| Bean singleton mutable | Counter hoặc map được giữ trong Spring context | Trạng thái rò rỉ giữa test method |
| Filesystem | Cùng ghi `/tmp/report.csv` | Test đè file của nhau |
| Clock hệ thống | So sánh chính xác với `Instant.now()` | Test fail theo thời điểm hoặc timezone |
| Random/UUID | Dữ liệu kỳ vọng cố định nhưng đầu vào ngẫu nhiên | Kết quả khó lặp lại |
| Luồng bất đồng bộ | Dùng `Thread.sleep(...)` để đợi | Fail khi CI chậm |
| Dịch vụ mạng | API bên thứ ba, SMTP, Redis không thuộc mục tiêu test | Fail vì DNS, cổng, credential, downtime |
| Cấu hình môi trường | Phụ thuộc biến môi trường của một máy | Chạy máy khác có kết quả khác |

Một số loại dữ liệu được chia sẻ là bình thường, chẳng hạn constant bất biến. Vấn đề nằm ở **trạng thái có thể thay đổi và tiền điều kiện không được test sở hữu**.

Test độc lập không yêu cầu mọi test phải chạy song song được ngay. Nhưng khi test thực sự độc lập, việc thay đổi thứ tự hoặc mở rộng sang parallel execution sẽ an toàn hơn nhiều.

## 3. Thiết kế service với dependency rõ ràng

Để có thể unit test mà không chạy Spring context hoặc gọi dịch vụ ngoài, hãy biểu diễn collaborator dưới dạng dependency của constructor.

Giả sử ứng dụng có service đặt chỗ. Trách nhiệm của service:

1. Kiểm tra mã khách hàng và mã phòng.
2. Hỏi một cổng kiểm tra phòng còn trống.
3. Tạo thông tin đặt chỗ với thời gian hiện tại.
4. Lưu qua repository.
5. Trả về kết quả.

Một số bước có thể đi tới database hoặc remote service trong production, nhưng unit test chỉ cần **giả lập kết quả của các cổng đó**.

~~~java
package com.example.booking;

public interface RoomAvailabilityPort {
    boolean isAvailable(String roomCode);
}
~~~

~~~java
package com.example.booking;

public interface BookingRepository {
    Booking save(Booking booking);
}
~~~

~~~java
package com.example.booking;

import java.time.Instant;

public record Booking(
        String customerId,
        String roomCode,
        Instant createdAt
) {
}
~~~

Service dùng constructor injection:

~~~java
package com.example.booking;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class BookingService {

    private final RoomAvailabilityPort availability;
    private final BookingRepository repository;
    private final Clock clock;

    public BookingService(
            RoomAvailabilityPort availability,
            BookingRepository repository,
            Clock clock) {
        this.availability = Objects.requireNonNull(availability);
        this.repository = Objects.requireNonNull(repository);
        this.clock = Objects.requireNonNull(clock);
    }

    public Booking book(String customerId, String roomCode) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        if (roomCode == null || roomCode.isBlank()) {
            throw new IllegalArgumentException("roomCode is required");
        }

        if (!availability.isAvailable(roomCode)) {
            throw new IllegalStateException("room is unavailable");
        }

        Booking booking = new Booking(
                customerId,
                roomCode,
                Instant.now(clock)
        );

        return repository.save(booking);
    }
}
~~~

Service không biết `RoomAvailabilityPort` dùng HTTP hay database. Đây là một **ranh giới kiểm thử**: logic quyết định đặt chỗ được kiểm tra riêng, còn adapter gọi remote API được kiểm thử bằng bài integration/contract test khác.

## 4. Unit test thuần với JUnit Jupiter và Mockito

Với Spring Boot, bộ test phổ biến sử dụng `spring-boot-starter-test`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Một lớp unit test có thể dùng Mockito Extension mà không cần `@SpringBootTest`:

~~~java
package com.example.booking;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class BookingServiceTest {

    @Mock
    RoomAvailabilityPort availability;

    @Mock
    BookingRepository repository;

    BookingService service;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        service = new BookingService(
                availability,
                repository,
                clock
        );
    }

    @Test
    void booksAvailableRoom() {
        when(availability.isAvailable("A101")).thenReturn(true);
        when(repository.save(any(Booking.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        Booking result = service.book("customer-1", "A101");

        assertEquals("customer-1", result.customerId());
        assertEquals("A101", result.roomCode());
        assertEquals(
                Instant.parse("2026-01-01T00:00:00Z"),
                result.createdAt()
        );

        verify(availability).isAvailable("A101");
        verify(repository).save(result);
    }

    @Test
    void rejectsUnavailableRoomWithoutSaving() {
        when(availability.isAvailable("A101")).thenReturn(false);

        assertThrows(
                IllegalStateException.class,
                () -> service.book("customer-1", "A101")
        );

        verify(availability).isAvailable("A101");
        verify(repository, never()).save(any(Booking.class));
    }

    @Test
    void rejectsBlankCustomerBeforeCallingDependencies() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.book("  ", "A101")
        );

        verifyNoInteractions(availability, repository);
    }
}
~~~

Đặc điểm của bộ test trên:

- `BookingService` là object thật tạo bằng `new`.
- Collaborator là Mockito mock riêng cho từng test.
- `Clock.fixed(...)` thay thế giờ hệ thống.
- Không khởi động ApplicationContext.
- Không có kết nối HTTP hoặc database.
- Mỗi test tự khai báo stubbing cần thiết cho nhánh của nó.

Test `rejectsUnavailableRoomWithoutSaving` không yêu cầu `booksAvailableRoom` chạy trước; cả hai tự tạo dữ liệu đầu vào và hành vi dependency.

### Không mock chính đối tượng đang kiểm thử

Nếu dùng:

~~~java
BookingService service = mock(BookingService.class);
when(service.book("customer-1", "A101"))
        .thenReturn(expectedBooking);
~~~

thì test chỉ kiểm tra kết quả đã định nghĩa trong Mockito, không kiểm tra logic của `BookingService`. Hãy mock collaborator, không mock SUT trong unit test của chính SUT đó.

## 5. Fixture phải do từng test sở hữu

JUnit Jupiter có `@BeforeEach` và `@BeforeAll` nhưng hai annotation có mục đích khác nhau.

| Cơ chế | Khi nào chạy | Dữ liệu nên chuẩn bị |
|---|---|---|
| `@BeforeEach` | Trước từng test method | Object mutable, fixture cụ thể, mock, trạng thái dùng cho một test |
| `@AfterEach` | Sau từng test method | Cleanup tài nguyên riêng của test |
| `@BeforeAll` | Một lần trước các test trong lớp | Cấu hình bất biến hoặc hạ tầng dùng chung được quản lý rõ |
| `@AfterAll` | Một lần sau các test trong lớp | Giải phóng hạ tầng dùng chung do lớp tạo |

Ví dụ sai:

~~~java
static final List<String> processed = new ArrayList<>();

@Test
void testA() {
    processed.add("A");
    assertEquals(1, processed.size());
}

@Test
void testB() {
    processed.add("B");
    assertEquals(1, processed.size());
}
~~~

Lớp này không cô lập trạng thái: `processed` là danh sách dùng chung. Nếu chạy A rồi B, B có thể thấy hai phần tử. Nếu đổi thứ tự, A có thể thất bại.

Một cách đúng là tạo danh sách riêng cho từng test:

~~~java
private List<String> processed;

@BeforeEach
void setUp() {
    processed = new ArrayList<>();
}
~~~

Có thể tốt hơn nữa là tạo danh sách trực tiếp trong từng test nếu không cần dùng chung fixture.

### @TestInstance(PER_CLASS) có làm test độc lập hơn?

Không. JUnit Jupiter mặc định thường tạo một instance test class mới cho mỗi test method. Khi chọn `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, nhiều method có thể chia sẻ instance field của cùng đối tượng test.

Chế độ PER_CLASS có các use case riêng, nhưng cũng làm việc rò rỉ state giữa test method dễ xảy ra hơn. Nếu sử dụng, cần chủ động tránh các mutable field chia sẻ hoặc thiết lập lại chúng trước từng test.

## 6. Không dùng test order để che giấu state leak

JUnit có thể sắp xếp thứ tự test bằng `@TestMethodOrder` và `@Order`:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class OrderedWorkflowTest {

    @Test
    @Order(1)
    void create() {
        // ...
    }

    @Test
    @Order(2)
    void update() {
        // ...
    }
}
~~~

Nhưng **khả năng điều khiển thứ tự không phải giải pháp mặc định** cho các test vốn nên độc lập. Nếu `update()` chỉ thành công sau `create()`, việc thêm `@Order` làm dependency trở nên ẩn trong một bộ test tưởng như gồm hai trường hợp riêng.

Cách tổ chức tốt hơn cho một workflow:

~~~java
@Test
void createsThenUpdatesBooking() {
    // Arrange: tạo dữ liệu riêng cho test

    // Act: tạo booking, rồi cập nhật booking

    // Assert: kiểm tra trạng thái cuối

    // Cleanup: được quản lý trong phạm vi test
}
~~~

Khi cần nhiều bước như một scenario thực sự, một test có trình tự nội bộ rõ ràng là hợp lý. Còn mỗi `@Test` dùng để kiểm tra một quy tắc độc lập thì không nên cần `@Order`.

Cũng đừng giả định JUnit sẽ luôn dùng thứ tự xuất hiện trong source code. Chạy theo tên phương thức, IDE, Gradle, Maven, parallel execution hoặc cấu hình test engine có thể thay đổi thứ tự thực tế.

## 7. Test không được phụ thuộc một dịch vụ ngoài không liên quan

Giả sử một service tính phí giao hàng, nhưng `@SpringBootTest` của nó khởi động toàn bộ ứng dụng. Trong ApplicationContext còn có:

- Email adapter kết nối SMTP khi tạo bean.
- Payment client kiểm tra token khi startup.
- Message broker consumer cần Kafka.
- Redis client hoặc analytics scheduler.
- External configuration client gọi API nội bộ.

Nếu email server tạm ngừng, test tính phí có thể thất bại **trước khi test chạy đến phương thức tính phí**, dù logic cần kiểm tra không dùng email.

Đây là lỗi **phạm vi context quá rộng**. Tại sao một test tính phí phải phụ thuộc vào SMTP?

Cách xử lý theo mức ưu tiên:

1. Với unit test logic thuần, **không khởi động Spring**; tạo SUT bằng constructor.
2. Với test chỉ cần một phần web/data, sử dụng **test slice** phù hợp.
3. Nếu cần Spring context nhưng không cần external adapter, dùng **fake/mock hoặc cấu hình loại bỏ integration không liên quan**.
4. Chỉ dùng dịch vụ thật trong test có mục tiêu kiểm chứng integration đó.

Không nên xử lý bằng cách tăng timeout, retry vô hạn hoặc để CI “đợi dịch vụ ổn định” nếu dịch vụ đó không liên quan đến hành vi đang kiểm tra.

## 8. @SpringBootTest khác unit test như thế nào?

`@SpringBootTest` tạo Spring ApplicationContext với cấu hình ứng dụng tương đối đầy đủ. Đây là công cụ mạnh để kiểm tra bean wiring, AOP, cấu hình và sự tích hợp.

Ví dụ:

~~~java
@SpringBootTest
class ApplicationWiringTest {

    @Autowired
    BookingService service;

    @Test
    void contextProvidesBookingService() {
        assertNotNull(service);
    }
}
~~~

Test này kiểm tra Spring có thể tạo và inject `BookingService`. Đó là mục tiêu khác với unit test kiểm tra các nhánh `book(...)`.

Nếu ứng dụng có hàng chục integration được auto-configure, khởi động context rộng có thể kích hoạt nhiều dependency ngoài phạm vi. Cần phân biệt:

- **Unit test:** test logic của `BookingService` bằng mock/fake.
- **Context test:** kiểm tra bean được tạo và wired đúng.
- **Integration test:** kiểm tra adapter kết nối tới database, HTTP service hoặc broker.
- **End-to-end test:** kiểm tra luồng đi qua nhiều thành phần thật.

Không phải mọi test có file Java trong project Spring Boot đều cần `@SpringBootTest`.

## 9. Dùng test slice thay vì load toàn bộ ứng dụng

Spring Boot có các test slice để khởi tạo một phần hạ tầng có liên quan.

Ví dụ thường gặp:

| Mục tiêu | Công cụ | Những thứ thường không cần |
|---|---|---|
| Controller HTTP mapping, serialization, validation | `@WebMvcTest` | Toàn bộ repository/database |
| JPA entity và repository | `@DataJpaTest` | Web server, mail sender |
| JSON serialization | `@JsonTest` | Business integrations |
| JDBC repository | `@JdbcTest` | Controller, remote APIs |
| Unit logic service | JUnit + Mockito | Toàn bộ Spring context |

Với `@WebMvcTest`, các collaborator của controller thường được thay bằng mock để tập trung vào mapping, request/response và logic web. Các rule Spring Security hoặc filter có thể vẫn tham gia tùy cấu hình test slice, nên không nên nghĩ slice luôn bỏ qua mọi hạ tầng ngoài web.

Ví dụ minh họa với Spring Framework 6.2+ có `@MockitoBean`:

~~~java
@WebMvcTest(BookingController.class)
class BookingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    BookingService bookingService;

    @Test
    void returnsBookingResponse() throws Exception {
        // Stub service, gọi request qua MockMvc, assert response.
    }
}
~~~

Các import tiêu biểu:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
~~~

Trong các dự án Spring Boot cũ hơn, có thể gặp `@MockBean` của Spring Boot test. Khi dùng ví dụ này cần chọn annotation phù hợp **với phiên bản Spring Framework/Spring Boot của dự án**, không trộn tùy tiện hai cơ chế.

Một test slice chỉ có ý nghĩa nếu mục tiêu là cơ chế của slice. Nếu chỉ gọi `BookingService.book(...)` rồi assert kết quả, unit test trực tiếp sẽ đơn giản hơn.

## 10. Test context caching: nhanh hơn nhưng dễ che state rò rỉ

Spring Test Framework thường **cache ApplicationContext** để nhiều test có cùng cấu hình được dùng lại context, giúp tránh khởi động lại Spring liên tục.

Đây là tối ưu tốt, nhưng nó có hậu quả:

- Bean singleton mutable có thể giữ trạng thái nếu test chỉnh sửa trực tiếp.
- Cache ứng dụng có thể còn entry từ test trước.
- Các scheduler/background worker vẫn đang chạy nếu được bật.
- Một mock trong context cần được reset đúng lifecycle.
- Dữ liệu ngoài context như database/file vẫn tồn tại dù context bị tạo lại.

Ví dụ một bean lưu counter trong field:

~~~java
@Component
public class RequestCounter {

    private int value;

    public void increment() {
        value++;
    }

    public int value() {
        return value;
    }
}
~~~

Nếu test A increment và test B mong giá trị ban đầu bằng 0 trên cùng singleton, thứ tự chạy sẽ ảnh hưởng kết quả.

Giải pháp hợp lý tùy mục tiêu:

- Nếu test chỉ kiểm tra logic counter, tạo object thật riêng từng test, không cần Spring.
- Nếu phải dùng Spring context, chủ động reset fixture khi test sở hữu state đó.
- Nếu bean có state ứng dụng thật, cân nhắc đưa state vào repository/cache có lifecycle rõ ràng thay vì một singleton mutable tùy tiện.
- Nếu mỗi test thật sự cần context hoàn toàn mới, cân nhắc `@DirtiesContext` nhưng hiểu chi phí.

### @DirtiesContext: công cụ cuối, không phải mặc định

~~~java
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class SpecialContextMutationTest {
    // Test thay đổi cấu hình hoặc bean state ở mức context.
}
~~~

`@DirtiesContext` đánh dấu context không còn phù hợp để tái sử dụng. Spring sẽ bỏ context đó khỏi cache và tạo lại khi test khác cần.

Điều này có thể cần thiết nếu test cố ý thay đổi environment hoặc cấu trúc context. Tuy nhiên, dùng `@DirtiesContext` tràn lan khiến test suite khởi động lại Spring nhiều lần và thường **che giấu nguyên nhân state leak**. Nó cũng không tự xóa database hay file nằm bên ngoài ApplicationContext.

## 11. Cách ly dữ liệu database giữa các test

Khi mục tiêu thực sự là kiểm thử persistence, cần database hoặc một giải pháp phù hợp. Test vẫn phải tự tạo dữ liệu riêng.

Ví dụ không tốt:

~~~java
@Test
void findsAccount() {
    Account account = repository.findByEmail("admin@example.test")
            .orElseThrow();

    assertEquals("ADMIN", account.role());
}
~~~

Test này giả định database đã có user `admin@example.test`, có thể là dữ liệu do migration, môi trường hay một test khác tạo ra. Nếu tiền điều kiện không phải dữ liệu fixture do chính test quản lý, kết quả khó dự đoán.

Tốt hơn:

~~~java
@Test
void findsAccount() {
    Account saved = repository.save(
            new Account("test-user-42@example.test", "ADMIN")
    );

    Account found = repository.findById(saved.getId())
            .orElseThrow();

    assertEquals("ADMIN", found.getRole());
}
~~~

Đây chỉ là cấu trúc minh họa; constructor/entity mapping phụ thuộc model dự án. Khi nhiều test chạy trên cùng database, nên dùng dữ liệu hoặc ID riêng, transaction rollback phù hợp hoặc database/schema được cô lập.

### @Transactional test rollback có giới hạn

Trong các integration test dùng Spring TestContext, một test method đánh dấu `@Transactional` thường được chạy trong **test-managed transaction** và được rollback mặc định sau test:

~~~java
@DataJpaTest
class AccountRepositoryTest {

    @Autowired
    AccountRepository repository;

    @Test
    void savesAndLoadsAccount() {
        // Data test được quản lý trong transaction test.
    }
}
~~~

`@DataJpaTest` thường cấu hình transaction cho persistence test theo môi trường phù hợp. Tuy nhiên:

- Dữ liệu ghi ở transaction khác có thể không bị rollback theo transaction của test.
- Side effect bên ngoài database như file, message hoặc email không bị rollback.
- Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, request HTTP có thể được xử lý ở một thread/transaction khác với thread test.
- Nếu code cố ý commit trong transaction độc lập, test rollback không nhất thiết hoàn nguyên tác động đó.

Vì vậy, không nên mặc định rằng chỉ thêm `@Transactional` là mọi loại integration test đều sạch dữ liệu.

### Tránh xung đột khi chạy song song

Không dùng chung một email cố định như `test@example.test` cho nhiều test đồng thời nếu DB có unique constraint. Có thể sinh ID riêng cho từng case và dọn dẹp dữ liệu có chủ đích.

Nhưng không nên dùng ngẫu nhiên để che lỗi rồi không lưu lại thông tin tái hiện. Khi phát sinh dữ liệu động, nên ghi nhận ID trong failure report hoặc sử dụng một generator có thể lặp lại bằng seed.

## 12. Dùng Testcontainers khi integration cần hạ tầng thật

Nếu mục tiêu là kiểm tra repository với chính hệ quản trị database mà production sử dụng, một database tạm thời trong container có thể phù hợp hơn một database shared cố định.

Testcontainers giúp test sở hữu lifecycle của dependency kiểm thử, ví dụ PostgreSQL container. Sơ đồ:

~~~text
Integration test
       |
       +--> PostgreSQL container dành cho test
       |
       +--> Spring application/repository
       |
       v
   Assertion
       |
       v
   Cleanup theo lifecycle
~~~

Ưu điểm:

- Giảm phụ thuộc vào database cài sẵn trên máy lập trình.
- Có thể chạy cùng phiên bản dịch vụ cố định trong CI.
- Giảm rủi ro tác động vào dữ liệu thật.
- Cấu hình môi trường có thể lặp lại.

Nhưng Testcontainers không làm test trở thành unit test. Nó vẫn là integration test, cần runtime container, thời gian startup và chiến lược quản lý dữ liệu.

Nếu một test chỉ kiểm tra logic tính toán và không thực sự cần SQL, **đừng khởi động PostgreSQL container** cho test đó. Hạ tầng càng ít, phạm vi lỗi càng rõ.

## 13. Dịch vụ HTTP: mock/fake cho unit test, mock server cho adapter test

Trong unit test của `BookingService`, `RoomAvailabilityPort` là mock. Không có request HTTP thật.

Nhưng khi viết adapter thật:

~~~java
@Component
public class HttpRoomAvailabilityAdapter
        implements RoomAvailabilityPort {

    // Dùng RestClient/WebClient được cấu hình.
    // Chuyển kết quả HTTP thành boolean.
}
~~~

ta có mục tiêu kiểm thử mới: URL, HTTP method, JSON mapping, status code, timeout và xử lý lỗi.

Khi đó có thể dùng:

- Mock HTTP server chạy cục bộ trên port động.
- `MockRestServiceServer` với những client Spring hỗ trợ.
- WireMock hoặc MockWebServer trong một integration test được cấu hình phù hợp.
- Contract test xác minh request/response của adapter.

Nguyên tắc là adapter test **chủ động tạo mô phỏng của dịch vụ mà nó cần**, không gọi API production hoặc một staging endpoint có trạng thái thay đổi.

Ví dụ một unit test service không nên yêu cầu:

~~~yaml
room:
  service:
    url: https://real-availability.example.test
~~~

Nếu service gọi endpoint thật, test có thể thất bại vì DNS, chứng chỉ TLS, rate limit hoặc maintenance mà không có lỗi nghiệp vụ nào trong service.

### Mock endpoint không có nghĩa hợp đồng HTTP đã được xác nhận

Một mock của `RoomAvailabilityPort` chỉ kiểm tra logic điều phối. Nó không chứng minh adapter có gửi đúng header, parse JSON đúng hay thực sự tương thích với remote API.

Hãy dành test riêng cho adapter/contract; không ép mọi unit test phải gọi dịch vụ ngoài để “thực tế hơn”.

## 14. Tránh để hạ tầng không liên quan kết nối lúc startup

Ngay cả trong integration test, việc Spring khởi động một bean không cần thiết có thể làm test phụ thuộc dịch vụ bên ngoài.

Ví dụ một component có code:

~~~java
@PostConstruct
public void initialize() {
    remoteClient.connect();
}
~~~

Nếu bean được tạo trong `@SpringBootTest`, test có thể thất bại tại startup dù không gọi chức năng của component đó.

Có vài hướng thiết kế tốt hơn:

1. **Giảm phạm vi context:** nếu test không cần bean đó, dùng test slice hoặc cấu hình context tập trung.
2. **Tách adapter khỏi business service:** inject interface, thay adapter bằng fake/mock khi integration không thuộc phạm vi.
3. **Dời kết nối sang lúc sử dụng thực sự:** tránh những network call không cần thiết trong constructor hoặc `@PostConstruct`.
4. **Cấu hình có điều kiện:** khi nghiệp vụ cho phép, đăng ký integration bean bằng property/profile và tắt nó rõ ràng trong test.
5. **Cấu hình test dependency:** nếu test cần context và cần bean đó nhưng không cần network, cung cấp implementation test có hành vi xác định.

Ví dụ adapter có thể đăng ký có điều kiện:

~~~java
@Configuration(proxyBeanMethods = false)
public class ExternalClientConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "external.notifications",
            name = "enabled",
            havingValue = "true"
    )
    NotificationClient notificationClient() {
        return new NotificationClient();
    }
}
~~~

Đây là mẫu ý tưởng: nếu thật sự tắt bean, các component phụ thuộc cũng phải được cấu hình để không yêu cầu bean bị tắt. Không nên chỉ thêm một flag rồi tạo tình trạng thiếu dependency khi context khởi động.

Cũng cần nhớ một test có thể không dùng integration X về nghiệp vụ nhưng các điều kiện auto-configuration của ứng dụng vẫn cố khởi tạo X. Hãy xác định đúng bean hoặc auto-configuration tạo kết nối, thay vì “mở” hàng loạt tài nguyên ngoài để mọi test khởi động được.

## 15. Dùng profile và property riêng cho test một cách rõ ràng

Với test cần Spring context, có thể khai báo:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ApplicationIntegrationTest {
    // ...
}
~~~

Và đặt `src/test/resources/application-test.yml`:

~~~yaml
external:
  notifications:
    enabled: false
  analytics:
    enabled: false

spring:
  task:
    scheduling:
      enabled: false
~~~

Các property ở ví dụ chỉ có tác dụng khi application hoặc auto-configuration cụ thể **thực sự hỗ trợ chúng**. Không nên giả định mọi scheduler của ứng dụng sẽ tắt chỉ vì đặt một key tùy ý; kiểm tra logic cấu hình của chính component.

Có thể override property cho test:

~~~java
@SpringBootTest(properties = {
        "external.notifications.enabled=false",
        "external.analytics.enabled=false"
})
class ShippingApplicationTest {
}
~~~

Một lựa chọn khác là `@TestPropertySource` khi cần nguồn property dành riêng cho test.

**Không dùng profile test như một công tắc tổng vô điều kiện.** Nếu production không thể khởi động vì bean wiring sai, một test profile tắt quá nhiều thành phần có thể che mất vấn đề. Hãy dùng profile/properties để kiểm soát những integration nằm ngoài mục tiêu; có test wiring/integration riêng xác nhận những integration quan trọng hoạt động.

## 16. Làm cho thời gian, timezone và random có thể kiểm soát

Những test dùng giờ hệ thống thường không ổn định ở mốc giao ngày, timezone khác nhau hoặc máy CI có tốc độ khác nhau.

Ví dụ dễ lỗi:

~~~java
LocalDate today = LocalDate.now();
assertEquals(today, service.expiryDate());
~~~

Giữa hai lần gọi có thể qua nửa đêm; service còn có thể dùng timezone khác.

Nên inject `Clock`:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-03-01T12:00:00Z"),
        ZoneOffset.UTC
);
~~~

Service dùng:

~~~java
Instant createdAt = Instant.now(clock);
~~~

Test assert chính xác trên `createdAt` mà không phụ thuộc thời điểm chạy.

Tương tự với random ID:

~~~java
public interface BookingIdGenerator {
    String nextId();
}
~~~

Trong test, generator có thể trả `"booking-123"`. Trong production, implementation có thể dùng UUID.

Không phải mọi phép tính đều cần abstract interface. Chỉ nên tạo seam khi nguồn dữ liệu có tính bất định hoặc phụ thuộc hạ tầng có thể làm test không lặp lại được.

## 17. Tài nguyên file phải có phạm vi riêng

Nếu hai test cùng dùng tên file:

~~~text
/tmp/booking-report.csv
~~~

thì test này có thể ghi đè hoặc xóa dữ liệu của test kia. Khi chạy song song, tình huống còn khó kiểm soát hơn.

JUnit Jupiter cung cấp `@TempDir` để tạo thư mục tạm riêng cho test:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReportWriterTest {

    @TempDir
    Path tempDir;

    @Test
    void writesReport() throws Exception {
        Path output = tempDir.resolve("report.txt");

        Files.writeString(output, "completed");

        assertEquals("completed", Files.readString(output));
    }
}
~~~

Mỗi test sở hữu đường dẫn của mình. JUnit quản lý việc dọn dẹp theo lifecycle thích hợp, giảm nguy cơ dữ liệu test trước tác động tới test sau.

Nếu code production cố định đường dẫn trong implementation, khó thay đường dẫn khi test; đây là dấu hiệu nên truyền đường dẫn hoặc một storage abstraction vào constructor thay vì hard-code.

## 18. Test bất đồng bộ: chờ điều kiện, không đoán thời gian

Một anti-pattern:

~~~java
service.startAsyncWork();
Thread.sleep(500);
assertEquals("DONE", repository.getStatus());
~~~

`Thread.sleep(500)` không chứng minh công việc đã hoàn tất: CI chậm có thể cần hơn 500 ms; máy nhanh khiến test phải đợi không cần thiết. Nó cũng che exception xảy ra trong luồng nền.

Tốt hơn là làm cho tác vụ quan sát được:

- Trả về `CompletableFuture` và đợi với timeout phù hợp.
- Inject executor có thể kiểm soát trong unit test.
- Dùng một điều kiện có thể poll hoặc cơ chế đồng bộ tường minh trong integration test.
- Thu thập exception từ future thay vì dựa vào log.

Ví dụ với một future:

~~~java
CompletableFuture<String> future = service.processAsync();

String result = future.get(2, TimeUnit.SECONDS);

assertEquals("DONE", result);
~~~

Thời hạn chờ ở đây là **giới hạn để test không treo vô hạn**, không phải một giả định rằng task luôn hoàn tất sau đúng hai giây.

Nếu code dùng `@Async` và cần kiểm tra proxy hoặc executor thực, đây là integration test của Spring async infrastructure; unit test logic bên trong có thể thực thi đồng bộ qua dependency/executor được kiểm soát.

## 19. Parallel test cần cách ly tài nguyên rõ ràng

Khi bật JUnit parallel execution hoặc Gradle thực thi nhiều test worker, các test vốn chỉ “may mắn” pass tuần tự có thể lộ race condition.

Các rủi ro thường gặp:

- Cùng cập nhật static field.
- Cùng dùng database/schema và key cố định.
- Cùng mở một TCP port cố định.
- Cùng ghi file chung.
- Cùng chỉnh global system property.
- Test A restart/stop service mà test B đang dùng.
- Cùng thao tác cache hoặc message queue không có namespace riêng.

Không nên giải quyết mọi vấn đề bằng cách tắt parallel execution vĩnh viễn. Trước hết hãy tìm trạng thái dùng chung không cần thiết và cô lập nó.

Khi có một tài nguyên **thực sự không thể chia sẻ đồng thời**, có thể dùng cơ chế đồng bộ test như `@ResourceLock` của JUnit Jupiter. Nhưng lock không giải quyết trường hợp test B cần dữ liệu do A tạo từ trước; nó chỉ điều phối truy cập cùng lúc.

Nếu cần khóa để nhiều test can thiệp một global state duy nhất, có thể đó là dấu hiệu cần refactor test fixture hoặc thiết kế lại dependency.

## 20. Tránh thao tác system properties và môi trường toàn cục không kiểm soát

Một test có thể dùng:

~~~java
System.setProperty("app.mode", "test");
~~~

`System.setProperty` thay đổi trạng thái toàn JVM. Nếu không hoàn nguyên, test khác có thể đọc giá trị `app.mode=test` bất kể nó tự cấu hình gì.

Nếu bắt buộc sửa system property, cần giữ giá trị cũ và phục hồi cẩn thận trong `finally` hoặc extension hỗ trợ cleanup. Nhưng trong Spring Boot, thường dễ kiểm soát hơn khi truyền property thông qua test context:

~~~java
@SpringBootTest(properties = "app.mode=test")
class ModeIntegrationTest {
}
~~~

Với unit test, nên inject một object cấu hình hoặc tham số constructor thay vì phụ thuộc global system property.

Các biến môi trường của tiến trình cũng không phải tài nguyên dễ thay đổi cục bộ cho từng test trong cùng JVM. Đừng thiết kế unit test đòi phải mutate môi trường OS trong lúc test chạy.

## 21. CI và việc tái hiện lỗi thứ tự chạy

Một bộ test độc lập tốt có thể chạy từ IDE, Gradle/Maven và CI mà không cần “chạy test khởi tạo” trước.

Các dấu hiệu cần chú ý khi lỗi xảy ra:

- **Chạy riêng fail, chạy cả bộ pass:** có thể thiếu fixture và dựa vào test khác chuẩn bị dữ liệu.
- **Chạy riêng pass, chạy cả bộ fail:** có thể rò rỉ mutable state hoặc trùng tài nguyên.
- **Máy developer pass, CI fail:** có thể dựa vào dịch vụ/local config đã cài sẵn, timezone, đường dẫn hoặc timing.
- **Chỉ fail khi parallel:** có thể race condition, cổng cố định, database key chung hoặc test cùng sửa global state.
- **Fail khi dịch vụ A ngừng, dù test B không kiểm tra A:** có thể context quá rộng hoặc kết nối eager không liên quan.

Khi chẩn đoán, nên thu thập tên test, input, exception, nguồn property và trạng thái phụ thuộc để tìm nguyên nhân; không tự chấp nhận việc “rerun đến khi xanh” là giải pháp lâu dài.

Các lệnh Gradle/Maven dùng để chạy một phần test có thể hữu ích trong quá trình phát triển bộ kiểm thử, ví dụ:

~~~bash
./gradlew test --tests "*BookingServiceTest"
mvn -Dtest=BookingServiceTest test
~~~

Các lệnh này chỉ là ví dụ học tập, không làm thay đổi nguyên tắc thiết kế test. Một test độc lập không được cần “chạy toàn bộ suite trước” để hoạt động.

## 22. Phân định rõ ba loại phụ thuộc

Khi thiết kế một bài test, hãy phân biệt:

| Loại | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Phụ thuộc nghiệp vụ trực tiếp | Service cần biết phòng có trống | Mock/fake port ở unit test; integration test riêng cho adapter |
| Hạ tầng đúng mục tiêu test | Repository test cần PostgreSQL | Cung cấp DB kiểm thử cô lập, có lifecycle và dữ liệu riêng |
| Dịch vụ ngoài không liên quan | Unit test tính tiền lại gọi SMTP | Không khởi động/không gọi SMTP; thu hẹp context hoặc thay bean |

Mục tiêu của unit test không phải giả vờ rằng external service không tồn tại trong hệ thống. Mục tiêu là kiểm tra **hợp đồng của một đơn vị code** mà không kéo vào những yếu tố không thuộc hợp đồng cần kiểm chứng.

Khi một service phụ thuộc mạnh vào nhiều hệ thống, constructor injection và các interface port giúp test quyết định rõ dependency nào được mô phỏng. Với integration test, phạm vi cần thiết có thể lớn hơn, nhưng mọi hạ tầng được sử dụng phải thuộc mục tiêu kiểm thử và có trạng thái quản lý được.

## 23. Quy trình thiết kế một test độc lập

Có thể áp dụng cách suy nghĩ sau khi thêm một test Spring Boot:

1. **Xác định đơn vị cần kiểm chứng.** Đây là logic service, HTTP controller, JPA repository hay luồng end-to-end?
2. **Chọn phạm vi nhỏ nhất đủ kiểm tra mục tiêu.** Unit test thì không cần Spring context; test controller/repository có thể dùng slice.
3. **Liệt kê toàn bộ đầu vào.** Bao gồm dữ liệu, clock, random, configuration và kết quả collaborator.
4. **Tạo fixture riêng.** Không dựa vào object, dữ liệu hoặc side effect do test khác chuẩn bị.
5. **Thay dependency ngoài phạm vi bằng mock/fake.** Không bắt unit test gọi API, SMTP, broker hoặc database thật.
6. **Sở hữu tài nguyên cần dùng.** Nếu integration test cần database/container/file, đảm bảo lifecycle và dữ liệu độc lập.
7. **Kiểm tra kết quả quan sát được.** Assert output, exception và side effect có ý nghĩa; không khóa test vào chi tiết implementation không cần thiết.
8. **Dọn dẹp hoặc tránh tạo state toàn cục.** Chú ý transaction riêng, cache, static state, temporary files và luồng nền.
9. **Không dùng thứ tự test làm tiền điều kiện.** Một workflow nhiều bước nên được mô tả trong cùng một scenario, không chia thành các test phụ thuộc.
10. **Kiểm soát hạ tầng lúc context khởi tạo.** Nếu một adapter không liên quan vẫn cố gọi mạng, thu hẹp context, thay adapter hoặc sửa điểm kết nối eager.

Điểm cốt lõi là **mỗi test chịu trách nhiệm cho tiền điều kiện và tài nguyên của chính nó**. Constructor injection giúp thay collaborator bằng mock/fake; fixture độc lập loại bỏ phụ thuộc thứ tự; test slices và cấu hình context thu hẹp giúp ngăn dịch vụ ngoài không liên quan tác động vào kết quả. Những integration test cần hạ tầng thật vẫn có chỗ đứng, nhưng được tách riêng theo mục đích và phải quản lý dữ liệu/lifecycle rõ ràng.

Khi đạt được các nguyên tắc đó, bộ kiểm thử Spring Boot sẽ dễ đọc, chạy lặp lại được và giúp lỗi phản ánh đúng hành vi cần kiểm chứng, thay vì phản ánh trạng thái ngẫu nhiên của những test hoặc dịch vụ khác.

