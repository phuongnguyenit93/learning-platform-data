# Unit test cho service được thiết kế bằng constructor injection

Trong Spring Boot, service thường phụ thuộc vào repository, client HTTP, bộ mã hóa, đồng hồ hệ thống hoặc một service khác. **Constructor injection** làm các phụ thuộc đó xuất hiện tường minh trong constructor, nhờ đó một service có thể được tạo trực tiếp trong unit test mà **không cần khởi động Spring ApplicationContext**.

Đây là lợi ích quan trọng: unit test kiểm tra logic của một đơn vị code trong điều kiện có thể kiểm soát, trong khi Spring chỉ cần tham gia khi mục tiêu kiểm thử là cơ chế wiring, transaction, persistence, HTTP hoặc sự tích hợp giữa nhiều thành phần.

Bài học minh họa cách thiết kế service có thể kiểm thử, sử dụng JUnit Jupiter và Mockito, kiểm tra kết quả cùng tương tác với dependency, điều khiển thời gian và phân biệt phạm vi unit test với integration test.

## 1. Unit test cho service kiểm tra điều gì?

Giả sử nghiệp vụ yêu cầu đăng ký người dùng:

1. Email và mật khẩu không được bỏ trống.
2. Email được chuẩn hóa trước khi tra cứu.
3. Email đã tồn tại thì từ chối đăng ký.
4. Mật khẩu phải được chuyển thành hash trước khi lưu.
5. Thời điểm đăng ký được ghi nhận.
6. Repository lưu dữ liệu và trả về kết quả.

Một unit test nên tập trung vào những quyết định do service chịu trách nhiệm. Nó không nhất thiết phải mở kết nối database thật, khởi động HTTP server hoặc chạy toàn bộ auto-configuration của Spring Boot.

Ví dụ, với một dependency `UserRepository`, test có thể giả lập câu trả lời “email chưa tồn tại” hoặc “email đã tồn tại” để kiểm tra cả hai nhánh xử lý.

| Thành phần | Trong unit test của service | Mục tiêu |
|---|---|---|
| Service đang kiểm thử | **Đối tượng thật** được tạo bằng constructor | Kiểm tra logic thật |
| Repository | Mock hoặc fake | Kiểm soát kết quả truy vấn/lưu |
| PasswordHasher | Mock hoặc fake | Kiểm tra service có dùng hash |
| Clock | Đồng hồ cố định thật | Kiểm tra thời gian ổn định |
| ApplicationContext | Không cần | Giữ test gọn và nhanh |
| Database, HTTP server | Không cần | Tránh phụ thuộc hạ tầng bên ngoài |

Tên thường dùng cho đối tượng được kiểm thử là **SUT** (*System Under Test*). Trong bài này, SUT là `RegistrationService`.

## 2. Vì sao constructor injection giúp unit test đơn giản?

Xét một service dùng field injection:

~~~java
@Service
public class LegacyRegistrationService {

    @Autowired
    private UserRepository repository;

    @Autowired
    private PasswordHasher hasher;

    // Business logic ...
}
~~~

Các dependency được gán sau khi Spring tạo bean. Nếu test tự gọi `new LegacyRegistrationService()` thì các field đó chưa được Spring inject và thường có giá trị `null`.

Để test, lập trình viên phải dựng ApplicationContext, dùng reflection để gán field hoặc dựa vào công cụ inject mock. Những cách này có thể hoạt động, nhưng khiến các điều kiện tạo service khó nhìn thấy hơn.

Với constructor injection:

~~~java
@Service
public class RegistrationService {

    private final UserRepository repository;
    private final PasswordHasher hasher;

    public RegistrationService(
            UserRepository repository,
            PasswordHasher hasher) {
        this.repository = repository;
        this.hasher = hasher;
    }
}
~~~

Test có thể tạo service trực tiếp:

~~~java
UserRepository repository = mock(UserRepository.class);
PasswordHasher hasher = mock(PasswordHasher.class);

RegistrationService service =
        new RegistrationService(repository, hasher);
~~~

Các dependency của service hiện ra trong constructor và có thể được thay bằng test doubles. Một dependency mới được thêm vào constructor sẽ làm nơi tạo service phải cập nhật, giúp nhận ra thay đổi thiết kế thay vì âm thầm để dependency chưa được cấu hình.

Constructor injection còn cho phép dùng field `final`, giảm khả năng thay dependency bất ngờ sau khi object đã được tạo.

### Có cần @Autowired trên constructor không?

Với một Spring bean có **duy nhất một constructor**, Spring có thể sử dụng constructor đó để inject dependency mà không cần `@Autowired`. Vì vậy, một service thông thường có thể dùng constructor injection thuần Java:

~~~java
@Service
public class BillingService {

    private final PaymentGateway gateway;

    public BillingService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Unit test tạo `BillingService` bằng `new`. Khi chạy ứng dụng thật, Spring tạo bean và cung cấp `PaymentGateway`.

Hai đường tạo object khác nhau, nhưng **logic nghiệp vụ dùng cùng một class**.

## 3. Ví dụ xuyên suốt: service đăng ký người dùng

Ta sử dụng cấu trúc minh họa:

~~~text
src/
├── main/java/com/example/registration/
│   ├── RegistrationService.java
│   ├── RegisterUserCommand.java
│   ├── RegisteredUser.java
│   ├── UserRepository.java
│   ├── PasswordHasher.java
│   └── DuplicateEmailException.java
└── test/java/com/example/registration/
    └── RegistrationServiceTest.java
~~~

Các class cùng thuộc package `com.example.registration`. Thiết kế này tách phần **ra quyết định nghiệp vụ** khỏi các cơ chế lưu trữ và mã hóa cụ thể.

### Command và model

~~~java
package com.example.registration;

public record RegisterUserCommand(
        String email,
        String password
) {
}
~~~

~~~java
package com.example.registration;

import java.time.Instant;

public record RegisteredUser(
        String email,
        String passwordHash,
        Instant createdAt
) {
}
~~~

`RegisterUserCommand` mô tả đầu vào, còn `RegisteredUser` chứa dữ liệu đã xử lý trước khi lưu. `record` giúp tạo các value object bất biến, có `equals()` và các accessor rõ ràng.

### Các interface phụ thuộc

~~~java
package com.example.registration;

public interface UserRepository {

    boolean existsByEmail(String email);

    RegisteredUser save(RegisteredUser user);
}
~~~

~~~java
package com.example.registration;

public interface PasswordHasher {

    String hash(String rawPassword);
}
~~~

`UserRepository` mô tả **khả năng truy cập dữ liệu mà service cần**, không buộc unit test phải sử dụng một database thật. `PasswordHasher` mô tả khả năng chuyển mật khẩu sang hash, không buộc test phải chạy một thuật toán hash cụ thể.

Một ứng dụng thực tế có thể có adapter JPA cho repository và adapter cho mật mã hóa; các implementation đó sẽ được kiểm thử riêng theo đúng phạm vi của chúng.

### Exception nghiệp vụ

~~~java
package com.example.registration;

public class DuplicateEmailException extends RuntimeException {

    public DuplicateEmailException(String email) {
        super("Email already registered: " + email);
    }
}
~~~

Exception giúp caller phân biệt nhánh từ chối đăng ký vì trùng email với lỗi lưu dữ liệu hoặc lỗi đầu vào.

Trong ứng dụng thật, không nên đưa thông tin nhạy cảm vào log/exception một cách không kiểm soát; ví dụ sử dụng địa chỉ `example.test` để minh họa.

## 4. Code của service được thiết kế để kiểm thử

~~~java
package com.example.registration;

import java.time.Clock;
import java.time.Instant;
import java.util.Locale;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final UserRepository repository;
    private final PasswordHasher hasher;
    private final Clock clock;

    public RegistrationService(
            UserRepository repository,
            PasswordHasher hasher,
            Clock clock) {

        this.repository = Objects.requireNonNull(
                repository, "repository"
        );
        this.hasher = Objects.requireNonNull(
                hasher, "hasher"
        );
        this.clock = Objects.requireNonNull(
                clock, "clock"
        );
    }

    public RegisteredUser register(RegisterUserCommand command) {
        Objects.requireNonNull(command, "command");

        if (command.email() == null || command.email().isBlank()) {
            throw new IllegalArgumentException("email is required");
        }

        if (command.password() == null
                || command.password().isBlank()) {
            throw new IllegalArgumentException("password is required");
        }

        String email = command.email()
                .trim()
                .toLowerCase(Locale.ROOT);

        if (repository.existsByEmail(email)) {
            throw new DuplicateEmailException(email);
        }

        String passwordHash = hasher.hash(command.password());

        RegisteredUser candidate = new RegisteredUser(
                email,
                passwordHash,
                Instant.now(clock)
        );

        return repository.save(candidate);
    }
}
~~~

Service chỉ biết các hợp đồng nó cần:

- `UserRepository` để kiểm tra trùng lặp và lưu.
- `PasswordHasher` để biến mật khẩu thô thành hash.
- `Clock` để biết thời gian hiện tại.

Không có lệnh `new JdbcTemplate(...)`, `DriverManager.getConnection(...)` hay lời gọi HTTP trực tiếp trong service. Không có việc tự tìm dependency từ `ApplicationContext`.

`Clock` là một dependency đặc biệt hữu ích. Nếu service gọi thẳng `Instant.now()`, test sẽ phải so sánh thời gian với độ sai lệch hoặc phụ thuộc thời điểm chạy. Khi inject `Clock`, unit test dùng một mốc thời gian cố định và có thể assert chính xác.

### Cấu hình Clock trong ứng dụng thật

Unit test có thể truyền `Clock.fixed(...)` trực tiếp. Để Spring tạo được bean `RegistrationService` trong ứng dụng, cần có bean `Clock` tương ứng:

~~~java
package com.example.registration;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Trong production, Spring inject `Clock.systemUTC()`. Trong unit test, ta cung cấp một đồng hồ cố định. Đây là một ví dụ về **cùng service, khác implementation của dependency theo môi trường kiểm thử**.

## 5. Thiết lập JUnit Jupiter và Mockito

Spring Boot dự án thường dùng starter test:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Starter test cung cấp các công cụ phổ biến trong hệ sinh thái kiểm thử Spring Boot, bao gồm JUnit Jupiter, Mockito và thư viện assertion phù hợp theo phiên bản dependency được quản lý.

Nếu dự án không dùng Spring Boot starter test, có thể khai báo JUnit Jupiter, Mockito Core và `mockito-junit-jupiter` riêng, với các phiên bản tương thích. Trong bài này, giả định dự án đã có JUnit Jupiter và Mockito Extension.

Các annotation quan trọng:

| Annotation / API | Chức năng |
|---|---|
| `@Test` | Đánh dấu phương thức test |
| `@BeforeEach` | Chuẩn bị fixture trước từng test |
| `@ExtendWith(MockitoExtension.class)` | Kết nối Mockito với lifecycle JUnit Jupiter |
| `@Mock` | Tạo test double bằng Mockito |
| `when(...).thenReturn(...)` | Cấu hình kết quả của mock |
| `verify(...)` | Kiểm tra một tương tác đã xảy ra |
| `assertEquals(...)`, `assertThrows(...)` | Kiểm tra kết quả và exception |
| `ArgumentCaptor` | Thu thập argument đã truyền cho mock |

Không cần đặt `@SpringBootTest` trên lớp unit test này. `MockitoExtension` không khởi động Spring; nó chỉ hỗ trợ tạo và quản lý mock của Mockito trong test.

## 6. Tạo fixture test bằng constructor

Một fixture cơ bản:

~~~java
package com.example.registration;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RegistrationServiceTest {

    @Mock
    UserRepository repository;

    @Mock
    PasswordHasher hasher;

    private RegistrationService service;

    @BeforeEach
    void setUp() {
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        service = new RegistrationService(
                repository,
                hasher,
                fixedClock
        );
    }
}
~~~

Mỗi test nhận một bộ mock theo lifecycle của Mockito Extension và tạo lại SUT trong `@BeforeEach`. Các test không chia sẻ trạng thái mutable của service giữa nhiều trường hợp.

Việc tạo SUT bằng constructor được viết rõ ràng để minh họa nguyên tắc:

~~~text
JUnit / Mockito
       |
       +--> mock UserRepository
       +--> mock PasswordHasher
       +--> fixed Clock
                 |
                 v
new RegistrationService(...)
                 |
                 v
       Thực thi method thật
                 |
                 v
      Assertion và verify
~~~

`Clock` không cần mock. Một object thật có hành vi xác định được như `Clock.fixed` thường dễ hiểu và ổn định hơn mock một API thuần Java chỉ để trả về thời gian.

## 7. Unit test cho nhánh đăng ký thành công

Phương thức đăng ký thành công cần chứng minh rằng service:

1. Chuẩn hóa email.
2. Kiểm tra trùng email với repository.
3. Gọi hasher bằng mật khẩu gốc.
4. Lưu object chứa hash và thời gian cố định.
5. Trả về kết quả do repository cung cấp.

Ví dụ:

~~~java
@Test
void registersUserWhenEmailIsAvailable() {
    // Arrange
    when(repository.existsByEmail("linh@example.test"))
            .thenReturn(false);

    when(hasher.hash("valid-password"))
            .thenReturn("hash-123");

    when(repository.save(any(RegisteredUser.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

    // Act
    RegisteredUser result = service.register(
            new RegisterUserCommand(
                    "  LINH@Example.Test ",
                    "valid-password"
            )
    );

    // Assert: trạng thái trả về
    assertEquals("linh@example.test", result.email());
    assertEquals("hash-123", result.passwordHash());
    assertEquals(
            Instant.parse("2026-01-01T00:00:00Z"),
            result.createdAt()
    );

    // Assert: tương tác với dependency
    verify(repository).existsByEmail("linh@example.test");
    verify(hasher).hash("valid-password");

    ArgumentCaptor<RegisteredUser> captor =
            ArgumentCaptor.forClass(RegisteredUser.class);

    verify(repository).save(captor.capture());

    RegisteredUser saved = captor.getValue();
    assertEquals("linh@example.test", saved.email());
    assertEquals("hash-123", saved.passwordHash());
    assertEquals(
            Instant.parse("2026-01-01T00:00:00Z"),
            saved.createdAt()
    );

    verifyNoMoreInteractions(repository, hasher);
}
~~~

Ví dụ sử dụng các static import trong lớp test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import org.mockito.ArgumentCaptor;
import org.junit.jupiter.api.Test;
~~~

### Vì sao dùng thenAnswer cho save?

`UserRepository.save(...)` có hợp đồng trả về `RegisteredUser`. Trong ví dụ này, mock được cấu hình trả về chính object mà service truyền vào:

~~~java
when(repository.save(any(RegisteredUser.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));
~~~

Nhờ vậy, service không phải biết Mockito; nó chỉ làm việc với interface repository. Đây là một cách giả lập đơn giản, không chứng minh persistence thực tế hoạt động.

Trong một test khác, có thể muốn giả lập repository trả object đã được database gán ID. Khi đó, hãy khai báo object kết quả cụ thể thay vì mặc định mọi `save` đều trả nguyên argument.

### Khi nào cần ArgumentCaptor?

`ArgumentCaptor` hữu ích khi cần kiểm tra **dữ liệu service gửi cho collaborator**. Ở ví dụ này, ta muốn chắc rằng mật khẩu thô không được đưa vào repository và thời điểm đăng ký đúng.

Nếu chỉ cần xác nhận một lời gọi đơn giản, có thể dùng:

~~~java
verify(repository).existsByEmail("linh@example.test");
~~~

Không cần captor cho mọi tham số; hãy dùng công cụ ít phức tạp nhất đủ chứng minh hành vi quan trọng.

## 8. Unit test cho email bị trùng

Khi repository báo email đã tồn tại, service phải ném exception và không gọi hasher hay save:

~~~java
@Test
void rejectsDuplicateEmailWithoutHashingOrSaving() {
    // Arrange
    when(repository.existsByEmail("linh@example.test"))
            .thenReturn(true);

    // Act
    DuplicateEmailException error = assertThrows(
            DuplicateEmailException.class,
            () -> service.register(
                    new RegisterUserCommand(
                            "LINH@example.test",
                            "valid-password"
                    )
            )
    );

    // Assert
    assertTrue(error.getMessage().contains("linh@example.test"));

    verify(repository).existsByEmail("linh@example.test");
    verify(repository, never()).save(any(RegisteredUser.class));
    verifyNoInteractions(hasher);
}
~~~

Các static import bổ sung:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verifyNoInteractions;
~~~

Test này kiểm tra cả **kết quả** lẫn **tác dụng phụ không được phép xảy ra**. Nếu chỉ assert exception, service có thể vô tình hash hoặc lưu dữ liệu trước khi phát hiện trùng email mà test không nhận biết.

Đối với nghiệp vụ có yêu cầu không được phát sinh side effect trong nhánh thất bại, việc verify tương tác âm tính là một phần có ý nghĩa của hợp đồng service.

## 9. Unit test cho input không hợp lệ

Các kiểm tra input cần xảy ra trước khi gọi repository hay hasher. Có thể dùng parameterized test để tránh lặp lại nhiều trường hợp gần giống nhau.

~~~java
@ParameterizedTest
@NullSource
@ValueSource(strings = {"", "   "})
void rejectsMissingOrBlankEmail(String email) {
    IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.register(
                    new RegisterUserCommand(email, "valid-password")
            )
    );

    assertEquals("email is required", error.getMessage());
    verifyNoInteractions(repository, hasher);
}
~~~

Các import tương ứng:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;
~~~

Nếu mật khẩu không hợp lệ:

~~~java
@Test
void rejectsBlankPasswordBeforeAccessingDependencies() {
    IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.register(
                    new RegisterUserCommand(
                            "linh@example.test",
                            " "
                    )
            )
    );

    assertEquals("password is required", error.getMessage());
    verifyNoInteractions(repository, hasher);
}
~~~

Với command hoàn toàn `null`:

~~~java
@Test
void rejectsNullCommand() {
    assertThrows(
            NullPointerException.class,
            () -> service.register(null)
    );

    verifyNoInteractions(repository, hasher);
}
~~~

Ở ví dụ này, `Objects.requireNonNull(command, "command")` tạo `NullPointerException` có chủ đích. Một dự án có thể chọn exception khác hoặc xác thực bằng Jakarta Validation ở tầng API; unit test nên phản ánh hợp đồng đã thống nhất của service.

### Không kiểm thử nhiều hành vi không liên quan trong một test

Một test nên có lý do thất bại dễ hiểu. Đừng kiểm tra nhánh email trùng, password rỗng và repository lỗi trong cùng một phương thức có hàng chục lần gọi.

Đặt tên như `rejectsDuplicateEmailWithoutHashingOrSaving` giúp mô tả cả tình huống và kết quả mong đợi.

## 10. Khi dependency phát sinh exception

Service có thể không bắt exception từ repository. Khi đó, lỗi được truyền lên caller theo đúng thiết kế. Một unit test có thể mô tả hành vi này:

~~~java
@Test
void propagatesRepositoryFailure() {
    when(repository.existsByEmail("linh@example.test"))
            .thenReturn(false);

    when(hasher.hash("valid-password"))
            .thenReturn("hash-123");

    when(repository.save(any(RegisteredUser.class)))
            .thenThrow(new IllegalStateException("storage unavailable"));

    IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.register(
                    new RegisterUserCommand(
                            "linh@example.test",
                            "valid-password"
                    )
            )
    );

    assertEquals("storage unavailable", error.getMessage());

    verify(repository).existsByEmail("linh@example.test");
    verify(hasher).hash("valid-password");
    verify(repository).save(any(RegisteredUser.class));
}
~~~

Đây không phải test kết nối database. Nó chỉ kiểm tra service ứng xử thế nào khi collaborator báo lỗi.

Nếu business yêu cầu chuyển exception hạ tầng thành exception domain, test nên assert loại exception sau khi được chuyển. Không nên tự thêm hành vi catch/retry chỉ để test có nhiều nhánh hơn.

## 11. Arrange – Act – Assert giúp test dễ đọc

Mỗi unit test có thể được chia thành ba phần:

**Arrange:** chuẩn bị input, test doubles, giá trị trả về và thời gian cố định.

**Act:** gọi đúng một hành vi chính của SUT.

**Assert:** kiểm tra kết quả hoặc exception; khi cần, kiểm tra tương tác với dependency.

Ví dụ thu gọn:

~~~java
@Test
void rejectsDuplicateEmail() {
    // Arrange
    when(repository.existsByEmail("taken@example.test"))
            .thenReturn(true);

    // Act
    Executable action = () -> service.register(
            new RegisterUserCommand(
                    "taken@example.test",
                    "valid-password"
            )
    );

    // Assert
    assertThrows(DuplicateEmailException.class, action);
    verifyNoInteractions(hasher);
}
~~~

`Executable` trong ví dụ là `org.junit.jupiter.api.function.Executable`.

Test nên độc lập với thứ tự chạy: không dùng một test để tạo trạng thái cho test tiếp theo. Mockito Extension và fixture tạo mới trong `@BeforeEach` giúp giới hạn sự chia sẻ trạng thái.

## 12. @Mock, @InjectMocks và việc tạo SUT thủ công

Mockito cung cấp `@InjectMocks` để cố gắng đưa các mock vào đối tượng cần kiểm thử:

~~~java
@ExtendWith(MockitoExtension.class)
class ExampleTest {

    @Mock
    UserRepository repository;

    @Mock
    PasswordHasher hasher;

    @InjectMocks
    SomeService service;
}
~~~

Cách này có thể tiện khi constructor đơn giản. Tuy nhiên, nó **không thay thế Spring dependency injection** và không bảo đảm tạo được mọi collaborator cần thiết.

Trong service có thêm `Clock` không được mock, việc dùng `@InjectMocks` có thể khiến test khó nhận ra dependency nào còn thiếu hoặc được gán `null`. Vì vậy, với bài học này, cách viết:

~~~java
service = new RegistrationService(
        repository,
        hasher,
        Clock.fixed(fixedInstant, ZoneOffset.UTC)
);
~~~

rõ ràng hơn:

- Người đọc thấy toàn bộ dependencies.
- Test tự quyết định implementation của mỗi dependency.
- Không phụ thuộc vào cơ chế suy luận injection của Mockito.
- Khi constructor thay đổi, compiler thường chỉ ra vị trí test cần cập nhật.

Đây là một trong những điểm mạnh của constructor injection: **không cần container và cũng không cần magic injection trong test**.

## 13. Mock và fake: chọn test double phù hợp

Không phải dependency nào cũng nên được mock.

| Test double | Ý tưởng | Phù hợp khi |
|---|---|---|
| Mock | Cấu hình kết quả và xác minh tương tác | Kiểm tra gọi repository, gateway, notifier |
| Stub | Trả dữ liệu cố định cho lời gọi | Chỉ cần kiểm soát đầu ra phụ thuộc |
| Fake | Implementation đơn giản nhưng có hoạt động thật | Cần mô phỏng kho lưu in-memory hoặc thuật toán đơn giản |
| Spy | Bọc object thật và có thể quan sát/ghi đè một số lời gọi | Có nhu cầu đặc thù, cần cẩn thận side effect |

Ví dụ fake repository giữ người dùng trong memory:

~~~java
import java.util.HashMap;
import java.util.Map;

final class InMemoryUserRepository implements UserRepository {

    private final Map<String, RegisteredUser> users =
            new HashMap<>();

    @Override
    public boolean existsByEmail(String email) {
        return users.containsKey(email);
    }

    @Override
    public RegisteredUser save(RegisteredUser user) {
        users.put(user.email(), user);
        return user;
    }

    RegisteredUser get(String email) {
        return users.get(email);
    }
}
~~~

Có thể truyền fake này cùng một fake hasher đơn giản vào service và kiểm tra trạng thái sau khi gọi. Cách này thích hợp nếu hành vi lưu/đọc của fake nhỏ và dễ hiểu.

Nhưng cần nhớ fake là code bổ sung phải được bảo trì. Nếu fake tự viết có hành vi khác repository thật, test vẫn có thể xanh dù integration với database lỗi. Fake không thay thế kiểm thử adapter persistence.

### Vì sao không nên mock mọi value object?

`RegisterUserCommand`, `RegisteredUser`, `Instant` và `Clock.fixed(...)` đều dễ tạo thật. Mock chúng sẽ làm test phụ thuộc vào lời gọi accessor hoặc stubbing không cần thiết.

Một quy tắc thực dụng: **mock collaborator ở ranh giới hệ thống; dùng object thật cho dữ liệu và phép tính thuần**.

## 14. Kiểm tra trạng thái hay kiểm tra tương tác?

Có hai kiểu assertion phổ biến.

**State-based testing** quan sát kết quả:

~~~java
assertEquals("linh@example.test", result.email());
assertEquals("hash-123", result.passwordHash());
~~~

**Interaction-based testing** kiểm tra lời gọi tới collaborator:

~~~java
verify(repository).existsByEmail("linh@example.test");
verify(hasher).hash("valid-password");
verify(repository).save(any(RegisteredUser.class));
~~~

Cả hai đều hữu ích, nhưng không nên verify mọi lời gọi nội bộ không thuộc hợp đồng nghiệp vụ. Test càng ràng buộc chặt vào chi tiết implementation, càng dễ vỡ khi refactor mà hành vi người dùng không thay đổi.

Ví dụ, nếu service được refactor từ `String.trim().toLowerCase(...)` sang một helper chuyên dụng nhưng kết quả email chuẩn hóa không đổi, unit test không nên phải thay đổi chỉ vì tên helper.

Ngược lại, kiểm tra service **không lưu người dùng khi email trùng** là tương tác có ý nghĩa, vì nó thể hiện một quy tắc nghiệp vụ và side effect quan trọng.

### Tránh verifyNoMoreInteractions thiếu chủ đích

`verifyNoMoreInteractions(...)` giúp phát hiện lời gọi ngoài dự kiến nhưng cũng có thể làm test quá gắn với implementation.

Nên dùng khi yêu cầu thật sự là “không phát sinh bất kỳ tương tác nào khác” hoặc khi muốn kiểm soát side effect nghiêm ngặt. Đừng dùng đại trà trong mọi test chỉ để tăng số lượng assertion.

## 15. Mockito stubbing: khi nào cần và khi nào không?

Với Mockito, một mock thường trả giá trị mặc định nếu chưa được stub:

- `boolean` thường là `false`.
- Kiểu tham chiếu thường là `null` hoặc giá trị rỗng thích hợp theo API.
- Các collection/optional có thể có default riêng tùy kiểu và phiên bản.

Không nên dựa quá nhiều vào default nếu giá trị đó là một tiền đề nghiệp vụ. Ví dụ, trong test thành công, nên chủ động viết:

~~~java
when(repository.existsByEmail("linh@example.test"))
        .thenReturn(false);
~~~

Điều này làm rõ điều kiện email chưa tồn tại.

Với kiểm tra validation không chạm dependency, không cần stub repository hay hasher. Mockito Extension thường hỗ trợ phát hiện stubbing không cần thiết; cố stub mọi phương thức trong `@BeforeEach` có thể tạo những stubbing dư thừa cho các test đi qua nhánh khác.

### Không trộn matcher và giá trị literal tùy tiện

Khi một phương thức mock có nhiều tham số, nếu dùng matcher cho một tham số thì nên dùng matcher cho các tham số còn lại trong cùng lời gọi stubbing/verify theo quy tắc Mockito.

Ví dụ:

~~~java
verify(gateway).send(
        eq("welcome"),
        any(String.class)
);
~~~

Đừng trộn `eq(...)` hoặc `any(...)` với một argument literal không được bọc matcher trong cùng lời gọi tương ứng.

### Stubbing không chứng minh side effect thật

Câu lệnh:

~~~java
when(repository.save(any(RegisteredUser.class)))
        .thenReturn(savedUser);
~~~

không ghi dữ liệu vào database. Nó chỉ khiến mock trả về `savedUser`. Unit test nên kiểm tra việc service **ra quyết định gọi save đúng**, không tuyên bố đã kiểm chứng transaction hoặc persistence.

## 16. Thời gian, ngẫu nhiên và dữ liệu bên ngoài: thêm seam có chủ đích

Một unit test đáng tin cậy cần đầu vào xác định được. Các nguồn không ổn định thường gặp:

- Thời gian hệ thống: `Instant.now()`, `LocalDate.now()`.
- Sinh ID hoặc token ngẫu nhiên: `UUID.randomUUID()`.
- Biến môi trường, cấu hình global hoặc system properties.
- HTTP, database, filesystem.
- Thread hoặc executor thực thi bất đồng bộ.

Constructor injection cho phép thay những nguồn này bằng interface hoặc đối tượng cụ thể có thể kiểm soát.

Ví dụ với thời gian:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
~~~

Nếu nghiệp vụ sinh mã đăng ký, có thể inject một `IdGenerator`:

~~~java
public interface IdGenerator {
    String nextId();
}
~~~

Sau đó test cho generator trả một ID cố định. Không cần sửa hành vi `UUID.randomUUID()` bằng các công cụ can thiệp static call khi đã có thể thể hiện nguồn ID thành dependency của service.

Điều này không có nghĩa mọi phép toán thuần đều phải trừu tượng hóa thành interface. Mục tiêu là tạo seam ở những nơi logic phụ thuộc vào **thế giới bên ngoài hoặc nguồn không xác định**, không phải tăng số class vô ích.

## 17. Một unit test không xác thực toàn bộ Spring Boot runtime

Trong bài này, test gọi:

~~~java
RegistrationService service =
        new RegistrationService(repository, hasher, fixedClock);
~~~

Đó là **unit test thuần**. Annotation `@Service` trên lớp không tham gia vào việc tạo SUT. Vì không có ApplicationContext, các cơ chế sau **không được kiểm thử**:

- Component scanning và bean registration.
- Autowiring nhiều implementation.
- `@Transactional` proxy và commit/rollback thực tế.
- `@Async` và executor advice.
- `@Cacheable` và cache interceptor.
- JPA mapping, query, database constraints.
- HTTP mapping, serialization, authentication và authorization.
- Binding `@ConfigurationProperties` hoặc profile activation.

Ví dụ, nếu phương thức được gắn `@Transactional`, unit test tạo service bằng `new` **không chứng minh** transaction interceptor sẽ chạy khi ứng dụng thực tế gọi qua Spring proxy.

Muốn kiểm tra những cơ chế đó, cần loại test khác.

| Mục tiêu | Loại test thường phù hợp |
|---|---|
| Nhánh nghiệp vụ trong service | Unit test với JUnit + Mockito/fake |
| JPA mapping và truy vấn repository | Persistence integration/slice test, ví dụ `@DataJpaTest` |
| MVC routing, request validation, JSON và controller advice | Web slice test, ví dụ `@WebMvcTest` |
| Bean wiring, AOP, transaction hoặc luồng thực tế giữa thành phần | Spring context/integration test |
| Hợp đồng với database hoặc hệ thống ngoài | Integration/contract test với hạ tầng phù hợp |

Spring Boot có annotation `@SpringBootTest` cho integration test cần context rộng, nhưng không nên dùng nó chỉ vì lớp được kiểm thử có `@Service`. Nếu chỉ kiểm tra logic thuần, thời gian startup và dependency môi trường thường không mang lại giá trị tương xứng.

## 18. Khi nào cần một integration test bổ sung?

Unit test có thể chứng minh `RegistrationService` gọi `repository.save(...)` đúng một lần với dữ liệu mong đợi. Nhưng nó không chứng minh:

- Database có unique constraint cho email.
- Transaction rollback khi repository phát sinh lỗi.
- Email được lưu đúng kiểu và encoding trong database.
- Implementation `PasswordHasher` trong production thực sự tạo hash an toàn.
- Spring có thể inject đủ `UserRepository`, `PasswordHasher` và `Clock`.

Các vấn đề này nên được kiểm tra tại tầng tương ứng.

Ví dụ về nguy cơ race condition: hai request đồng thời đều có thể nhận `existsByEmail(...) == false` trước khi cùng gọi `save(...)`. Unit test của service mô tả quy tắc dự định, nhưng **không thay thế unique constraint trong database** và cơ chế xử lý lỗi vi phạm constraint.

Tương tự, unit test dùng mock hasher không đánh giá sức mạnh thuật toán mật mã. Hãy kiểm thử adapter mã hóa riêng và sử dụng implementation đã được lựa chọn theo tiêu chuẩn bảo mật của hệ thống.

Thiết kế test theo nhiều tầng giúp nhận biết lỗi ở đúng nơi thay vì bắt một unit test giả lập cả database, HTTP, transaction và thread scheduling.

## 19. Lỗi thiết kế test thường gặp

### Dùng @SpringBootTest cho mọi service test

Điều này làm test chậm hơn, tăng phụ thuộc cấu hình và có thể tạo lỗi vì bean không liên quan. Nếu service có constructor rõ ràng, chỉ cần khởi tạo trực tiếp SUT và thay collaborator bằng mock/fake.

### Chỉ kiểm tra verify mà không assert kết quả

Kiểm tra `verify(repository).save(...)` có thể chưa đủ. Nếu phương thức phải trả về object đã lưu, hãy assert kết quả trả về và các quy tắc dữ liệu quan trọng.

### Chỉ kiểm tra kết quả mà quên side effect cần tránh

Trong nhánh email trùng, service không được hash/lưu dữ liệu. Nếu side effect là một phần nghiệp vụ, hãy kiểm tra tương tác không mong muốn không xảy ra.

### Mock chính service đang muốn kiểm thử

Không nên viết:

~~~java
RegistrationService service = mock(RegistrationService.class);
when(service.register(any())).thenReturn(expected);
~~~

rồi kết luận logic của `RegistrationService` đã được kiểm tra. Lúc này test chỉ xác nhận hành vi do chính Mockito định nghĩa.

**SUT phải là object thật**, còn dependency của nó mới là đối tượng được thay bằng test double khi cần.

### Dùng dữ liệu thời gian thực

Ví dụ:

~~~java
assertEquals(Instant.now(), result.createdAt());
~~~

gần như chắc chắn không ổn định vì hai lời gọi xảy ra ở thời điểm khác nhau. Inject `Clock` và dùng `Clock.fixed(...)` sẽ rõ ràng hơn.

### Để mock bị dùng lại giữa các test

Khi state hoặc stubbing của mock vô tình bị chia sẻ, test có thể phụ thuộc vào thứ tự chạy. Dùng fixture độc lập theo từng test và không giữ mutable global state không cần thiết.

### Stub tất cả trong @BeforeEach

Một test đầu vào sai không gọi repository, nên stubbing repository ở fixture chung vừa gây nhiễu vừa có thể bị Mockito phát hiện là không sử dụng. Hãy stub gần từng tình huống cần kiểm tra.

### Dùng exception từ một lớp phụ thuộc cụ thể trong mọi test

Nếu service chỉ quan tâm tới một hợp đồng repository, đừng làm mọi unit test phụ thuộc vào exception/implementation của một JDBC driver cụ thể. Các tình huống liên quan đến SQL hoặc mapping nên có test adapter persistence riêng.

### Dựa vào @InjectMocks để che constructor phức tạp

Nếu một service có quá nhiều dependency, khó setup test và khó hiểu trách nhiệm, đó có thể là dấu hiệu service đang làm quá nhiều việc. Thay vì tăng mức tự động inject, hãy xem lại ranh giới trách nhiệm.

## 20. Kiểm thử sau khi refactor service

Một thiết kế tốt cho unit test thường bền vững khi refactor những chi tiết implementation không ảnh hưởng hợp đồng.

Giả sử trước đây service gọi `repository.existsByEmail` rồi `repository.save`. Sau này nghiệp vụ chuyển sang một method repository chuyên biệt để xử lý atomic insert. Nếu hành vi nghiệp vụ vẫn là “email trùng thì từ chối, email hợp lệ thì lưu”, các assertion về kết quả vẫn nên có giá trị.

Các test verify tương tác có thể cần thay đổi do hợp đồng với repository thay đổi. Điều đó bình thường nếu repository interface thật sự đã thay đổi.

Ngược lại, thay tên biến local, tách private helper hoặc thay vòng lặp bằng Stream không nên buộc test thay đổi nếu đầu ra và side effect quan trọng giữ nguyên.

Các tiêu chí hữu ích khi thiết kế unit test service:

- Mỗi test diễn đạt một quy tắc nghiệp vụ dễ hiểu.
- SUT được tạo bằng constructor với dependency tường minh.
- Test không phụ thuộc ApplicationContext nếu không cần kiểm tra Spring.
- Dữ liệu thời gian/ngẫu nhiên/hạ tầng được kiểm soát.
- Assertion ưu tiên hành vi có thể quan sát, không bám vào private implementation.
- Những tương tác có ý nghĩa như “không lưu khi input sai” được xác minh.
- Mỗi test có thể chạy độc lập trên máy lập trình và CI.

## 21. Bài tập mở rộng

Có thể áp dụng cùng mô hình constructor injection để nâng chất lượng kiểm thử.

**Bài tập 1 — Kiểm tra mật khẩu quá ngắn.** Bổ sung quy tắc độ dài mật khẩu tối thiểu ở service và viết parameterized test cho chuỗi ngắn. Xác nhận không có lời gọi repository/hasher khi validation thất bại.

**Bài tập 2 — Đăng ký lúc thời gian cố định khác.** Truyền một `Clock.fixed(...)` với thời điểm khác và assert `createdAt` chính xác. Bài tập củng cố việc không phụ thuộc giờ hệ thống.

**Bài tập 3 — Có repository trả object khác.** Thay vì để `save(...)` trả argument, cấu hình mock trả một `RegisteredUser` được biểu diễn khác theo hợp đồng repository và xác nhận service trả đúng giá trị từ repository.

**Bài tập 4 — Thêm thông báo chào mừng.** Inject `WelcomeNotifier` qua constructor, rồi viết test xác nhận nhánh thành công mới gửi thông báo. Cân nhắc thực tế rằng thông báo không nên gửi trước khi transaction database commit; phần phối hợp commit cần integration test hoặc một thiết kế outbox/event phù hợp.

**Bài tập 5 — Thử fake repository.** Viết `InMemoryUserRepository` để kiểm tra lưu và đọc trong unit test, sau đó bổ sung integration test riêng cho repository JPA thật.

## 22. Kết luận

Một service dễ unit test không nhất thiết phải viết code riêng cho môi trường test. Điều quan trọng là thiết kế dependency rõ ràng:

~~~text
Spring Boot production:
ApplicationContext
     |
     +--> UserRepository thật
     +--> PasswordHasher thật
     +--> Clock.systemUTC()
              |
              v
      RegistrationService


JUnit unit test:
Mockito mocks + Clock.fixed()
              |
              v
new RegistrationService(...)
              |
              v
   Assert kết quả và side effect
~~~

Constructor injection cho phép **dùng cùng logic service trong cả hai môi trường** mà không cần tự gọi Spring container trong unit test. JUnit mô tả hành vi mong đợi; Mockito kiểm soát những collaborator ở ranh giới; object thật như `Clock.fixed` giúp test có kết quả xác định được.

Giữ unit test tập trung vào logic service, rồi dùng integration test cho wiring, AOP, database, HTTP và các phụ thuộc hệ thống thật. Sự phân tách này tạo ra bộ kiểm thử nhanh, rõ ràng và có khả năng phát hiện lỗi ở đúng tầng của ứng dụng Spring Boot.

