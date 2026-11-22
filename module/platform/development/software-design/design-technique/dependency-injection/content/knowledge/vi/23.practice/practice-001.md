# Chuyển một dịch vụ tự tạo repository sang constructor injection

Trong nhiều ứng dụng Java, một service được viết rất nhanh bằng cách **tự tạo repository** bên trong constructor hoặc field:

~~~java
final class CustomerRegistrationService {
    private final InMemoryCustomerRepository repository =
            new InMemoryCustomerRepository();

    // register(...) dùng repository ở trên.
}
~~~

Cách này có vẻ thuận tiện: người gọi chỉ cần `new CustomerRegistrationService()`. Tuy nhiên, service đang đồng thời quyết định **cách tạo hạ tầng lưu trữ** và **cách thực hiện nghiệp vụ đăng ký khách hàng**. Khi đổi sang JDBC, thêm cấu hình kết nối hoặc viết unit test không đụng đến database, ta sẽ phải can thiệp vào chính service.

Bài **thực hành** này hướng dẫn một cuộc refactor nhỏ nhưng đầy đủ trong module **DEPENDENCY_INJECTION**: từ class tự tạo repository sang class **nhận repository qua constructor**, được lắp ghép tại **composition root**. Đây là cách áp dụng **Dependency Injection (DI)** và **Inversion of Control (IoC)** bằng **Java thuần**, trước khi cân nhắc DI container.

Điểm cần giữ nguyên trong suốt quá trình là **hành vi nghiệp vụ**: tên và email được chuẩn hóa, khách hàng mới được lưu, email trùng bị từ chối. Phần thay đổi phải là **hướng phụ thuộc và nơi tạo đối tượng**, không phải quy tắc đăng ký.

## 1. Mục tiêu, điều kiện thực hành và tiêu chí hoàn thành

**Yêu cầu môi trường:** Java 17 trở lên, một terminal có thể chạy `javac` và `java`, không cần Maven, Gradle, Spring hay database.

Hoàn thành bài khi bạn có thể chứng minh:

1. `CustomerRegistrationService` **không gọi `new InMemoryCustomerRepository()`** và không tra cứu repository từ một registry toàn cục.
2. Constructor của service yêu cầu `CustomerRepository` và từ chối `null`.
3. `CustomerRepository` mô tả **hành vi cần dùng**, không phải chi tiết lưu trữ cụ thể.
4. `main` hoặc bootstrap **tạo một repository** rồi truyền đúng instance đó vào service.
5. Có thể thay repository bằng **fake** để kiểm tra chuẩn hóa dữ liệu, thứ tự thực thi và lỗi mà không khởi động hạ tầng.
6. Hai service được truyền **cùng repository instance** có thể chia sẻ dữ liệu lưu trong repository ấy; hai repository riêng thì không tự chia sẻ dữ liệu.
7. Người sở hữu các tài nguyên lưu trữ thật có chính sách **scope và lifecycle** rõ ràng.

**Phạm vi:** Bài dùng repository trong bộ nhớ để nhìn thấy object graph. Không thiết lập database thật, không viết DI container nhỏ, không làm vòng Content QA/refactor chuyên môn của các bài khác.

### Các tệp thực hành

Ta dùng ba tệp độc lập để bạn dễ đối chiếu:

| Tệp | Vai trò | Cách chạy |
| --- | --- | --- |
| `Before.java` | Phiên bản service tự tạo repository | `javac Before.java` rồi `java Before` |
| `After.java` | Phiên bản đã áp dụng constructor injection | `javac After.java` rồi `java After` |
| `AfterTest.java` | Unit test với fake và smoke test lắp ghép | `javac After.java AfterTest.java` rồi `java AfterTest` |

Các kiểu domain trong hai phiên bản được đặt dưới dạng **kiểu lồng nhau** của `Before` và `After` để bạn có thể lưu cả ba tệp trong **cùng một thư mục** mà không bị trùng tên class. Trong dự án thật, hãy tách chúng thành file/package theo trách nhiệm phù hợp.

## 2. Tình huống nghiệp vụ cần bảo toàn

Hệ thống nhận tên và email để đăng ký khách hàng:

~~~text
Đầu vào:
  name  = "  Mai  "
  email = "  MAI@EXAMPLE.TEST  "

Đầu ra khi đăng ký thành công:
  Customer(name = "Mai", email = "mai@example.test")

Khi đăng ký lại cùng email đã chuẩn hóa:
  Từ chối với DuplicateCustomerException
~~~

Để tập trung vào DI, ta sử dụng ba quy tắc đơn giản:

- Tên không được `null` hoặc chỉ gồm khoảng trắng; khi lưu phải `trim()`.
- Email không được `null` hoặc trống; khi lưu phải `trim()` và chuyển thành chữ thường theo `Locale.ROOT`; ví dụ chỉ kiểm tra tối thiểu có ký tự `@`, **không** thay thế bộ kiểm tra email production.
- Repository không thêm khách hàng thứ hai có cùng **email đã chuẩn hóa**; thao tác thêm trả về `false` nếu email đã tồn tại.

Từ yêu cầu đó, ta có hai trách nhiệm khác nhau:

| Trách nhiệm | Thuộc về ai? |
| --- | --- |
| Chuẩn hóa tên/email, quyết định lỗi nghiệp vụ khi trùng | `CustomerRegistrationService` |
| Cung cấp thao tác lưu khách hàng và phát hiện khóa đã tồn tại | `CustomerRepository` / adapter lưu trữ |
| Chọn repository nào, tạo instance và truyền vào service | Composition root (`main`) |
| Tạo, đóng connection/pool/session khi dùng hạ tầng thật | Bên sở hữu tài nguyên ở ranh giới ứng dụng hoặc unit of work |

Tách được ba phần đầu là mục tiêu chính của bài. Phần lifecycle sẽ được dùng để kiểm tra xem thiết kế còn phù hợp khi ứng dụng lớn hơn hay không.

## 3. Bước 0 — quan sát phiên bản đang ghép chặt

Lưu đoạn sau vào `Before.java`. Đây là **chương trình độc lập**, có thể biên dịch bằng Java 17.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public class Before {
    record Customer(String name, String email) {}

    static final class InMemoryCustomerRepository {
        private final Map<String, Customer> byEmail =
                new ConcurrentHashMap<>();

        boolean insertIfAbsent(Customer customer) {
            Objects.requireNonNull(customer, "customer");
            return byEmail.putIfAbsent(
                    customer.email(), customer) == null;
        }
    }

    static final class CustomerRegistrationService {
        // Vấn đề: service tự quyết định và tạo adapter cụ thể.
        private final InMemoryCustomerRepository repository =
                new InMemoryCustomerRepository();

        Customer register(String name, String email) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Invalid name");
            }
            if (email == null || email.isBlank()) {
                throw new IllegalArgumentException("Invalid email");
            }

            String normalizedName = name.trim();
            String normalizedEmail =
                    email.trim().toLowerCase(Locale.ROOT);

            if (!normalizedEmail.contains("@")) {
                throw new IllegalArgumentException("Invalid email");
            }

            Customer customer =
                    new Customer(normalizedName, normalizedEmail);

            if (!repository.insertIfAbsent(customer)) {
                throw new IllegalStateException(
                        "Duplicate customer: " + normalizedEmail);
            }

            return customer;
        }
    }

    public static void main(String[] args) {
        CustomerRegistrationService first =
                new CustomerRegistrationService();
        CustomerRegistrationService second =
                new CustomerRegistrationService();

        // Hai service tự tạo hai kho khác nhau.
        System.out.println(
                "First: " + first.register(
                        "  Mai  ", " MAI@EXAMPLE.TEST ").email());

        System.out.println(
                "Second: " + second.register(
                        "Mai", "mai@example.test").email());
    }
}
~~~

Chạy:

~~~bash
javac Before.java
java Before
~~~

Kết quả dự kiến:

~~~text
First: mai@example.test
Second: mai@example.test
~~~

### Phân tích kết quả và giới hạn của cách viết cũ

Mỗi service có `new InMemoryCustomerRepository()` tại field initializer, nên `first` và `second` đang lưu vào **hai map khác nhau**. Vì vậy cả hai đều đăng ký được cùng email. Đây **không tự động là bug** nếu hai service thật sự cần hai kho độc lập, nhưng là một **quyết định scope đã bị ẩn** trong service.

Vấn đề lớn hơn xuất hiện khi muốn:

- **Dùng chung repository:** không có tham số nào ở `new CustomerRegistrationService()` để cấp một instance đã tồn tại.
- **Đổi adapter:** phải sửa class nghiệp vụ để thay `InMemoryCustomerRepository` bằng adapter JDBC/HTTP.
- **Test lỗi từ repository:** rất khó cấp một fake cho phép kiểm tra trường hợp repository trả `false` hoặc ném exception.
- **Quản lý tài nguyên:** nếu repository tự tạo connection, service trở thành nơi ngầm sở hữu tài nguyên; ai đóng và đóng lúc nào không được thể hiện ở composition root.
- **Đọc object graph:** nhìn `main` không biết service đang tạo một kho dữ liệu mới.

Mã trên vẫn có thể **biên dịch và chạy**, nhưng lớp nghiệp vụ đang làm việc **lắp ghép hạ tầng** thay cho ranh giới ứng dụng.

~~~mermaid
flowchart LR
    Main["main"] -->|"new"| Service["CustomerRegistrationService"]
    Service -->|"tự new"| Repo["InMemoryCustomerRepository"]
    Repo --> Map["ConcurrentHashMap"]
~~~

**Mục tiêu refactor:** thay cạnh `Service --new--> Repository cụ thể` bằng cạnh `Service --cần--> CustomerRepository`. Composition root chịu trách nhiệm tạo implementation và đưa nó vào constructor.

## 4. Bước 1 — trích xuất hợp đồng repository đủ hẹp

Ở phiên bản sau, ta định nghĩa một interface:

~~~java
interface CustomerRepository {
    /**
     * Thêm khách hàng nếu email chưa tồn tại.
     *
     * @return true nếu đã thêm; false nếu email bị trùng.
     */
    boolean insertIfAbsent(Customer customer);
}
~~~

**Ý nghĩa contract:**

1. Caller truyền vào một `Customer` hợp lệ; email đã được chuẩn hóa theo quy tắc của ứng dụng.
2. Kết quả `true` nghĩa là adapter chấp nhận thêm khách hàng mới.
3. Kết quả `false` nghĩa là không thêm vì email đã tồn tại.
4. Ngoại lệ của hạ tầng (nếu có) **không** bị đổi thành `false`, vì `false` đã có ý nghĩa nghiệp vụ riêng.
5. Nếu hệ thống có nhiều request đồng thời, adapter production cần bảo đảm tính duy nhất phù hợp với phạm vi lưu trữ; ví dụ database có thể dùng **unique constraint** và cơ chế xử lý xung đột.

Interface trên là **port do use case cần**, không chứa `Map`, SQL, connection string hoặc cách lấy bean từ container.

### Vì sao không inject `Map<String, Customer>` thẳng vào service?

~~~java
// Kém rõ ràng: nghiệp vụ bị ghép với lựa chọn cấu trúc lưu trữ.
CustomerRegistrationService(Map<String, Customer> customers) { ... }
~~~

Một `Map` không diễn đạt đầy đủ contract “thêm nếu email chưa tồn tại”, không cho biết bảo đảm lỗi/transaction và gây khó khăn khi đổi sang database. Interface `CustomerRepository` cho phép adapter triển khai chính sách lưu trữ trong phạm vi hợp đồng nghiệp vụ.

Cũng không cần tạo các phương thức `findAll()`, `deleteAll()` hay `openTransaction()` chỉ vì chúng “thường có trong repository”. **Chỉ khai báo khả năng service hiện cần**, sau đó mở rộng khi có use case thật sự.

## 5. Bước 2 — chuyển repository vào constructor

Sự thay đổi quyết định là **không tạo repository bên trong service**.

~~~diff
 final class CustomerRegistrationService {
-    private final InMemoryCustomerRepository repository =
-            new InMemoryCustomerRepository();
+    private final CustomerRepository repository;
+
+    CustomerRegistrationService(CustomerRepository repository) {
+        this.repository =
+                Objects.requireNonNull(repository, "repository");
+    }
 }
~~~

Lợi ích trực tiếp:

- Service phụ thuộc **interface** thay vì class lưu trữ cụ thể.
- Constructor buộc caller lựa chọn repository trước khi tạo service.
- `Objects.requireNonNull` làm lỗi thiếu dependency xuất hiện ngay tại ranh giới khởi tạo.
- Field `final` giúp service giữ tham chiếu dependency đã được cấp, không bị thay sau đó.
- Không cần setter hoặc lookup động chỉ để hoàn thiện đối tượng.

**Đây là constructor injection bằng Java thuần.** Nó không đòi `@Autowired`, DI container, reflection hay thư viện test đặc biệt.

### DI khác Dependency Inversion Principle (DIP) ở đâu?

- **DI** là thao tác truyền một đối tượng repository từ bên ngoài vào service.
- **DIP** là quyết định cho service nghiệp vụ phụ thuộc vào **abstraction `CustomerRepository`**, trong khi adapter chi tiết triển khai abstraction đó.
- **IoC** là việc chuyển quyền lựa chọn/tạo/lắp ghép dependency ra khỏi service.
- **Composition root** là nơi thể hiện những quyết định đó trong mã chạy thật.

Có thể làm DI mà vẫn inject một class cụ thể. Nhưng kết hợp constructor injection với một port có ý nghĩa thường giúp thay adapter và kiểm thử rõ ràng hơn.

## 6. Bước 3 — chuyển việc tạo adapter sang composition root

Mã khởi động phải quyết định **instance nào được cấp**:

~~~java
InMemoryCustomerRepository repository =
        new InMemoryCustomerRepository();

CustomerRegistrationService service =
        new CustomerRegistrationService(repository);
~~~

Nếu hai service cùng tham gia một ứng dụng và cần nhìn thấy cùng dữ liệu, composition root có thể truyền **cùng một instance**:

~~~java
InMemoryCustomerRepository repository =
        new InMemoryCustomerRepository();

CustomerRegistrationService first =
        new CustomerRegistrationService(repository);

CustomerRegistrationService second =
        new CustomerRegistrationService(repository);
~~~

Trước refactor, mỗi service tự tạo kho riêng. Sau refactor, composition root có thể **chủ động chọn dùng chung hoặc cấp riêng**. Bản thân DI **không buộc mọi dependency là singleton**: phạm vi là quyết định của ứng dụng, không phải đặc tính của constructor.

~~~mermaid
flowchart LR
    Root["main / composition root"] -->|"new"| Adapter["InMemoryCustomerRepository"]
    Root -->|"new service(repository)"| One["RegistrationService A"]
    Root -->|"new service(repository)"| Two["RegistrationService B"]
    One --> Port["CustomerRepository"]
    Two --> Port
    Adapter -.->|"implements"| Port
~~~

### Một bẫy hay gặp: vẫn tạo mới trong service khi thiếu tham số

Không nên giữ đường tắt:

~~~java
CustomerRegistrationService(CustomerRepository repository) {
    this.repository = repository != null
            ? repository
            : new InMemoryCustomerRepository();
}
~~~

Cách này khiến `null` trở thành tín hiệu “dùng repository mặc định” mà không được thể hiện ở composition root; lỗi quên wiring bị che. Nếu ứng dụng có nhu cầu mặc định thật sự, **composition root** có thể chọn default adapter rồi truyền vào constructor.

## 7. Bước 4 — phiên bản hoàn chỉnh sau refactor

Lưu đoạn sau vào `After.java`. Có thể đặt nó cùng thư mục với `Before.java` vì các kiểu được lồng trong hai class khác nhau.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public class After {
    // Dữ liệu nghiệp vụ bất biến.
    public record Customer(String name, String email) {
        public Customer {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Invalid name");
            }
            if (email == null || email.isBlank()) {
                throw new IllegalArgumentException("Invalid email");
            }
        }
    }

    // Port do nghiệp vụ yêu cầu, không rò chi tiết hạ tầng.
    @FunctionalInterface
    public interface CustomerRepository {
        boolean insertIfAbsent(Customer customer);
    }

    // Adapter thay thế được, chỉ biết cách lưu trong RAM.
    public static final class InMemoryCustomerRepository
            implements CustomerRepository {
        private final Map<String, Customer> byEmail =
                new ConcurrentHashMap<>();

        @Override
        public boolean insertIfAbsent(Customer customer) {
            Objects.requireNonNull(customer, "customer");
            return byEmail.putIfAbsent(
                    customer.email(), customer) == null;
        }

        public int count() {
            return byEmail.size();
        }
    }

    public static final class DuplicateCustomerException
            extends RuntimeException {
        public DuplicateCustomerException(String email) {
            super("Duplicate customer: " + email);
        }
    }

    // Service không còn biết implementation repository.
    public static final class CustomerRegistrationService {
        private final CustomerRepository repository;

        public CustomerRegistrationService(CustomerRepository repository) {
            this.repository =
                    Objects.requireNonNull(repository, "repository");
        }

        public Customer register(String name, String email) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Invalid name");
            }
            if (email == null || email.isBlank()) {
                throw new IllegalArgumentException("Invalid email");
            }

            String normalizedName = name.trim();
            String normalizedEmail =
                    email.trim().toLowerCase(Locale.ROOT);

            if (!normalizedEmail.contains("@")) {
                throw new IllegalArgumentException("Invalid email");
            }

            Customer customer =
                    new Customer(normalizedName, normalizedEmail);

            if (!repository.insertIfAbsent(customer)) {
                throw new DuplicateCustomerException(normalizedEmail);
            }

            return customer;
        }
    }

    // Composition root: toàn bộ quyết định wiring nằm ở đây.
    public static void main(String[] args) {
        InMemoryCustomerRepository repository =
                new InMemoryCustomerRepository();

        CustomerRegistrationService first =
                new CustomerRegistrationService(repository);
        CustomerRegistrationService second =
                new CustomerRegistrationService(repository);

        Customer saved =
                first.register("  Mai  ", " MAI@EXAMPLE.TEST ");
        System.out.println("Saved: " + saved.email());

        try {
            second.register("Mai", "mai@example.test");
        } catch (DuplicateCustomerException expected) {
            System.out.println("Duplicate detected");
        }

        System.out.println("Repository size: " + repository.count());
    }
}
~~~

Chạy:

~~~bash
javac After.java
java After
~~~

Kết quả dự kiến:

~~~text
Saved: mai@example.test
Duplicate detected
Repository size: 1
~~~

### Phân tích vì sao output khác phiên bản `Before`

`Before` tạo hai repository riêng bên trong hai service, nên mỗi kho đều có thể thêm cùng một email. `After` tạo **một repository** tại composition root rồi inject cùng tham chiếu vào hai service. Việc đăng ký lần thứ hai đi qua **cùng map** và bị từ chối vì khóa đã tồn tại.

Điều đáng học không phải “constructor injection làm dữ liệu tự động dùng chung”, mà là: **constructor injection cho phép người lắp ghép lựa chọn và nhìn thấy quyết định dùng chung**. Nếu `main` chủ động tạo hai `InMemoryCustomerRepository` khác nhau, hai service vẫn sẽ có dữ liệu độc lập.

### Đối chiếu trước/sau

| Thành phần | Trước refactor | Sau refactor |
| --- | --- | --- |
| Constructor service | Không yêu cầu repository | Yêu cầu `CustomerRepository` |
| Lớp mà service biết | `InMemoryCustomerRepository` cụ thể | Interface `CustomerRepository` |
| Nơi gọi `new Repository` | Bên trong service | `main` / composition root |
| Kiểm thử không cần lưu trữ thật | Khó thay thế repository | Truyền fake bằng lambda |
| Phạm vi của repository | Mỗi instance service có một kho | Do composition root lựa chọn |
| Xử lý thiếu dependency | Không lộ ở điểm tạo service | Constructor từ chối `null` |
| Đổi từ RAM sang DB | Phải sửa hoặc mở rộng service | Thay adapter/binding, giữ contract |
| Quản lý đóng tài nguyên | Dễ bị giấu trong service | Có thể tập trung tại owner |

**Lưu ý về ngoại lệ:** Phiên bản `Before` ném `IllegalStateException` khi trùng, còn `After` minh họa bằng `DuplicateCustomerException` chuyên biệt (một subclass của `RuntimeException`). Nếu yêu cầu là **bảo toàn tuyệt đối kiểu ngoại lệ quan sát được**, hãy giữ `IllegalStateException` trong bước refactor DI, rồi thay đổi taxonomy lỗi trong một PR riêng. Trong bài thực hành này, cả hai đều diễn đạt từ chối trùng; điểm thay đổi liên quan DI được tách ra để quan sát.

## 8. Bước 5 — unit test với fake repository

Kiểm thử đúng mục tiêu là **không tạo repository hạ tầng** để kiểm tra logic `CustomerRegistrationService`. Ta cấp một fake `CustomerRepository` có thể ghi lại lời gọi và chủ động trả `true` hoặc `false`.

Lưu đoạn sau vào `AfterTest.java`:

~~~java
public class AfterTest {
    static final class FakeCustomerRepository
            implements After.CustomerRepository {
        int calls;
        After.Customer lastSaved;
        boolean acceptInsert = true;

        @Override
        public boolean insertIfAbsent(After.Customer customer) {
            calls++;
            lastSaved = customer;
            return acceptInsert;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectInvalid(Runnable operation, String scenario) {
        boolean rejected = false;
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "Expected invalid input: " + scenario);
    }

    static void testNormalizeAndSave() {
        FakeCustomerRepository fake = new FakeCustomerRepository();
        After.CustomerRegistrationService service =
                new After.CustomerRegistrationService(fake);

        After.Customer actual =
                service.register("  Mai  ", " MAI@EXAMPLE.TEST ");

        check(actual.equals(new After.Customer(
                "Mai", "mai@example.test")),
                "Must normalize name and email");
        check(fake.calls == 1,
                "Repository must be called exactly once");
        check(fake.lastSaved == actual,
                "Repository must receive the returned customer");

        // Input lỗi phải bị từ chối trước khi gọi repository.
        expectInvalid(
                () -> service.register("  ", "mai@example.test"),
                "Blank name");
        expectInvalid(
                () -> service.register("Mai", "invalid-email"),
                "Invalid email format");
        expectInvalid(
                () -> service.register("Mai", null),
                "Missing email");

        check(fake.calls == 1,
                "Invalid input must not reach repository");
    }

    static void testDuplicate() {
        FakeCustomerRepository fake = new FakeCustomerRepository();
        fake.acceptInsert = false;

        After.CustomerRegistrationService service =
                new After.CustomerRegistrationService(fake);

        boolean duplicateRejected = false;
        try {
            service.register("Mai", "mai@example.test");
        } catch (After.DuplicateCustomerException expected) {
            duplicateRejected = true;
        }

        check(duplicateRejected,
                "Duplicate customer must be rejected");
        check(fake.calls == 1,
                "Duplicate path must call repository exactly once");
    }

    static void testDependencyAndFailure() {
        boolean missingRejected = false;
        try {
            new After.CustomerRegistrationService(null);
        } catch (NullPointerException expected) {
            missingRejected = true;
        }
        check(missingRejected,
                "Null repository must fail at construction");

        // Adapter lỗi là lỗi hạ tầng, không phải email trùng.
        After.CustomerRepository failing = customer -> {
            throw new IllegalStateException("Storage unavailable");
        };

        After.CustomerRegistrationService service =
                new After.CustomerRegistrationService(failing);

        boolean failureObserved = false;
        try {
            service.register("Mai", "mai@example.test");
        } catch (IllegalStateException expected) {
            failureObserved = true;
        }
        check(failureObserved,
                "Storage failure must not be swallowed");
    }

    static void testSharedWiring() {
        After.InMemoryCustomerRepository shared =
                new After.InMemoryCustomerRepository();

        After.CustomerRegistrationService first =
                new After.CustomerRegistrationService(shared);
        After.CustomerRegistrationService second =
                new After.CustomerRegistrationService(shared);

        first.register("Mai", "mai@example.test");

        boolean duplicateRejected = false;
        try {
            second.register("Another", "MAI@EXAMPLE.TEST");
        } catch (After.DuplicateCustomerException expected) {
            duplicateRejected = true;
        }

        check(duplicateRejected,
                "Two services must observe one shared repository");
        check(shared.count() == 1,
                "Shared repository must hold exactly one customer");

        // Graph khác với repository khác vẫn độc lập có chủ đích.
        After.InMemoryCustomerRepository independent =
                new After.InMemoryCustomerRepository();
        After.CustomerRegistrationService other =
                new After.CustomerRegistrationService(independent);

        other.register("Mai", "mai@example.test");
        check(independent.count() == 1,
                "Independent graph must have its own data");
    }

    public static void main(String[] args) {
        testNormalizeAndSave();
        testDuplicate();
        testDependencyAndFailure();
        testSharedWiring();
        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac After.java AfterTest.java
java AfterTest
~~~

Kết quả dự kiến:

~~~text
PASS
~~~

### Các phép kiểm tra xác minh điều gì?

- **`testNormalizeAndSave`:** service áp dụng quy tắc xử lý dữ liệu và gọi repository đúng một lần.
- **`testDuplicate`:** khi port báo trùng, service diễn giải thành lỗi nghiệp vụ.
- **`testDependencyAndFailure`:** repository bắt buộc được kiểm tra ở constructor; lỗi lưu trữ được chuyển lên caller, không bị ngụy trang thành trùng email.
- **`testSharedWiring`:** hai service được inject cùng một repository có thể chia sẻ dữ liệu; graph có repository riêng vẫn độc lập.

Phân biệt **unit test** và **wiring smoke test**: các test dùng `FakeCustomerRepository` kiểm tra service cô lập với hạ tầng; `testSharedWiring` dùng adapter trong RAM để kiểm tra một lựa chọn lắp ghép cụ thể. Test này không chứng minh database thật hoạt động hoặc các instance trong những tiến trình khác nhau chia sẻ dữ liệu.

## 9. Bước 6 — xác định scope và lifecycle sau refactor

Đưa repository ra khỏi service khiến câu hỏi về vòng đời trở nên **rõ và có thể quyết định**. Không có quy tắc “cứ repository là singleton”.

| Nhu cầu | Ví dụ lựa chọn | Điều cần kiểm tra |
| --- | --- | --- |
| Adapter stateless, thread-safe | Một instance dùng chung | Client/adapter có thực sự an toàn đa luồng? |
| Kho dữ liệu RAM trong một ứng dụng demo | Một instance giữ map dùng chung | Map có scope và nhu cầu lưu đúng không? |
| Unit of work giữ entity mutable | Context riêng cho mỗi công việc | Các bước trong cùng unit nhận đúng context |
| Transaction/session ngắn hạn | Tạo theo request/job/transaction | Không giữ session đã đóng trong singleton |
| Connection pool | Thường do application runtime sở hữu | Consumer không tự đóng pool sau mỗi lời gọi |
| Repository dùng JDBC | Adapter có thể dùng pool và mở connection theo thao tác | Giao dịch, isolation và ownership được thiết kế riêng |

Nếu sau này thay adapter thành JDBC, mô hình tổng thể có thể là:

~~~mermaid
flowchart LR
    Root["Composition root"] -->|"tạo/giữ"| Pool["DataSource / pool"]
    Pool --> Adapter["JdbcCustomerRepository"]
    Root -->|"truyền"| Service["CustomerRegistrationService"]
    Service --> Port["CustomerRepository"]
    Adapter -.->|"implements"| Port
    Adapter --> Pool
~~~

`CustomerRegistrationService` không cần biết cách cấu hình JDBC, URL database, connection pool hoặc lúc đóng pool. Nó vẫn gọi `insertIfAbsent(customer)` thông qua interface.

**Ownership:** nếu pool được tạo tại composition root, runtime hoặc container nên là bên quản lý shutdown. Service chỉ **sử dụng** repository được cấp, không tự gọi `close()` trên tài nguyên dùng chung sau mỗi lần đăng ký.

**Tính đồng thời:** `ConcurrentHashMap.putIfAbsent` trong ví dụ bảo đảm thao tác thêm theo khóa trong phạm vi **một map của một JVM**. Nó **không bảo đảm** tính duy nhất toàn hệ thống nếu bạn triển khai nhiều process/instance. Với database thật, hãy dùng ràng buộc duy nhất của database và xử lý xung đột đúng contract. Đừng thay `insertIfAbsent` bằng hai lệnh “kiểm tra tồn tại” rồi “lưu” riêng rẽ và mặc định chúng nguyên tử khi nhiều request chạy đồng thời.

**Dữ liệu trong RAM không bền vững:** restart ứng dụng khiến map bị mất. DI giúp thay adapter lưu trữ, nhưng không tự cung cấp persistence, transaction hoặc migration schema.

## 10. Sai lầm thường gặp trong bài thực hành

| Lối làm | Vì sao chưa đạt mục tiêu? | Sửa thế nào? |
| --- | --- | --- |
| Giữ `new InMemoryCustomerRepository()` trong constructor service | Service vẫn chọn và tạo hạ tầng | Chuyển `new` ra composition root |
| Thêm setter `setRepository(...)` nhưng để service có thể chạy trước khi được gán | Đối tượng có trạng thái chưa hoàn chỉnh | Dùng constructor cho dependency bắt buộc |
| Inject `GlobalContainer` rồi gọi `get(CustomerRepository.class)` | Phụ thuộc thật bị ẩn phía sau locator | Inject `CustomerRepository` trực tiếp |
| Constructor nhận concrete `InMemoryCustomerRepository` | Có DI nhưng vẫn ghép với implementation | Dùng port `CustomerRepository` nếu cần thay adapter |
| Tạo repository mới **mỗi lần `register()`** | Mất state trong RAM, sai scope, tốn tài nguyên | Chọn scope ở bootstrap hoặc một factory có lý do rõ |
| Cho service tự đóng repository/client được inject | Consumer giành quyền sở hữu tài nguyên | Để owner ở application runtime/container đóng |
| Test dùng DB thật chỉ để kiểm tra trim/lowercase | Chậm, khó cô lập và khó tái hiện lỗi | Fake repository và kiểm tra dữ liệu truyền vào |
| Fake luôn trả `true` rồi chỉ test đường thành công | Bỏ sót nhánh duplicate và lỗi hạ tầng | Kiểm tra cả `false`, exception và input không hợp lệ |
| Thay đổi luôn logic nghiệp vụ khi refactor DI | Khó xác định regression thuộc wiring hay behavior | Giữ hành vi cũ, thay đổi nhỏ theo bước |
| Coi `@Autowired` hoặc `@Inject` là bắt buộc | Đánh đồng DI với framework | Constructor injection bằng `new Service(repository)` là DI hợp lệ |

### Interface không phải điều kiện duy nhất của DI

Có thể viết:

~~~java
CustomerRegistrationService(InMemoryCustomerRepository repository) {
    this.repository = repository;
}
~~~

Đây **vẫn là DI** vì dependency được truyền từ ngoài. Nhưng service còn biết implementation cụ thể, nên khó thay bằng adapter khác không kế thừa kiểu ấy. Trong bài, ta chọn interface để đồng thời thực hành **Dependency Inversion Principle (DIP)** và khả năng thay fake/adapter.

### Một service có nên biết `DataSource`?

Nếu service nghiệp vụ chỉ cần “thêm khách hàng nếu email chưa tồn tại”, truyền `DataSource` sẽ đưa chi tiết hạ tầng vào API nghiệp vụ. Nên truyền `CustomerRepository`. Đối với một adapter lưu trữ, ngược lại, nhận `DataSource` qua constructor **có thể hoàn toàn hợp lý**, vì adapter là nơi thao tác với hạ tầng.

## 11. Checklist code review cho cuộc refactor

Trước khi đánh dấu hoàn thành, hãy đọc lại code và xác nhận:

- [ ] Class nghiệp vụ có một constructor yêu cầu `CustomerRepository`.
- [ ] Không có `new InMemoryCustomerRepository()` hoặc `GlobalServices.get(...)` trong service.
- [ ] Mọi nhánh của `register()` dùng field `repository` đã được inject.
- [ ] Validation và chuẩn hóa dữ liệu vẫn hoạt động như trước.
- [ ] Repository contract chỉ chứa khả năng use case cần.
- [ ] Composition root quyết định tạo một instance dùng chung hay nhiều instance độc lập.
- [ ] Unit test có thể chạy chỉ bằng fake, không cần container hoặc DB.
- [ ] Test bao gồm thành công, duplicate, input không hợp lệ và lỗi hạ tầng.
- [ ] Adapter thực không bị consumer đóng khi còn dùng chung.
- [ ] Các giả định concurrency/persistence được nêu rõ; không suy từ DI sang transaction.

**Tiêu chí đánh giá thiết kế:** Nếu ngày mai thay `InMemoryCustomerRepository` bằng `JdbcCustomerRepository` tuân theo cùng contract, file chứa `CustomerRegistrationService` **không phải sửa**. Chỉ adapter mới và phần wiring/configuration cần thay đổi.

## 12. Bài tập tự mở rộng

### Bài tập A — viết adapter ghi nhận thao tác

Tạo `RecordingCustomerRepository` triển khai `After.CustomerRepository` và lưu danh sách những email đã được gọi lưu. Cấp nó cho `CustomerRegistrationService`.

**Yêu cầu:** đăng ký thành công phải gọi `insertIfAbsent` đúng một lần với email đã chuyển thành chữ thường; dữ liệu đầu vào sai không được gọi repository.

*Gợi ý:* có thể dùng `List<String>` trong fake; không cần dựng database.

### Bài tập B — kiểm tra lựa chọn dùng chung

Tại `main`, thử tạo hai repository khác nhau, truyền lần lượt cho hai service và đăng ký cùng email. Sau đó thay bằng **một repository** truyền cho cả hai.

**Câu hỏi:** khác biệt về kết quả do constructor injection hay do **quyết định object graph của composition root**?

*Đáp án định hướng:* constructor injection cho phép lựa chọn rõ; kết quả cụ thể phụ thuộc instance nào đã được truyền.

### Bài tập C — đổi sang adapter giả lập lỗi

Tạo một implementation `CustomerRepository` luôn ném `IllegalStateException("Storage unavailable")`. Test xem service có vô tình chuyển lỗi hạ tầng thành `DuplicateCustomerException` không.

**Yêu cầu:** lỗi hạ tầng phải còn nhận diện được; `false` mới là kết quả trùng email theo contract.

### Bài tập D — thêm clock mà không tạo trong service

Giả sử đăng ký cần gắn thời điểm tạo. Định nghĩa `Customer` có thêm `Instant createdAt` và cho service nhận `Clock` qua constructor.

**Yêu cầu:** production composition root truyền `Clock.systemUTC()`; unit test dùng `Clock.fixed(...)` để không phụ thuộc thời gian chạy. Không gọi `Instant.now()` rải rác trong nghiệp vụ.

### Bài tập E — chuẩn bị cho lưu trữ thật

Phác thảo `JdbcCustomerRepository` triển khai `CustomerRepository`. Chỉ mô tả:

1. Nó nhận dependency hạ tầng gì qua constructor?
2. Unique email được bảo đảm ở đâu?
3. Ai sở hữu và đóng connection pool?
4. Lỗi khóa trùng được ánh xạ thành `false` như thế nào?
5. Lỗi DB không liên quan trùng khóa được báo ra sao?

Không cần viết SQL chạy thật. Mục đích là thấy **service không thay đổi** khi thay công nghệ lưu trữ.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao `private final Repository repo = new RepositoryImpl()` chưa phải constructor injection?**

Vì lớp tự tạo collaborator, không nhận nó từ bên ngoài. `final` chỉ cố định tham chiếu sau khi gán; nó không chuyển quyền lắp ghép cho composition root.

**2. Dùng constructor nhận `CustomerRepository` có bắt buộc phải dùng Spring không?**

Không. Lời gọi `new CustomerRegistrationService(repository)` là constructor injection đầy đủ bằng Java thuần. DI container chỉ giúp tự động hóa các bước registration và resolution khi đồ thị lớn hơn.

**3. Nếu hai service nhận hai fake repository khác nhau, có được kết luận DI hỏng vì state không chia sẻ không?**

Không. DI không hứa mọi dependency dùng chung. Scope/identity do composition root quyết định; hai đồ thị độc lập có thể là điều mong muốn.

**4. Tại sao fake repository cần mô tả kết quả `false` và cả đường ném exception?**

Vì `false` biểu thị **email trùng**, trong khi exception có thể biểu thị **lỗi hạ tầng**. Service phải xử lý hai trường hợp theo hợp đồng khác nhau.

**5. Nếu repository được inject là mutable và có nhiều thread dùng chung, constructor injection có làm nó an toàn luồng không?**

Không. Thread safety phụ thuộc implementation và cách sử dụng; DI chỉ cung cấp dependency. Với ví dụ RAM, `ConcurrentHashMap` hỗ trợ thao tác `putIfAbsent`, nhưng các bất biến nhiều bước hoặc persistence phân tán vẫn cần cơ chế khác.

**6. Vì sao không truyền một `ServiceLocator` hoặc toàn bộ DI container để service tự tìm repository?**

Vì dependency thật sẽ bị ẩn; service phụ thuộc vào cơ chế tra cứu và có thể lỗi muộn khi lookup. Truyền `CustomerRepository` trực tiếp làm yêu cầu của service tường minh.

**7. Khi nào nên truyền factory thay cho repository instance?**

Khi một thao tác thật sự cần **tạo repository/context mới theo mỗi unit of work** hoặc cần tham số runtime để tạo. Khi đó phải mô tả rõ hợp đồng tạo mới, scope và quyền sở hữu. Không nên dùng factory chỉ để tránh khai báo dependency bắt buộc.

## Ghi nhớ

**Refactor sang constructor injection không phải chỉ thêm một tham số.** Ta đang chuyển quyền **chọn và tạo repository** ra khỏi service, khai báo một **hợp đồng lưu trữ đủ hẹp**, rồi cho **composition root** quyết định adapter và phạm vi dùng chung. Nhờ đó logic nghiệp vụ có thể được kiểm thử bằng fake, đồ thị phụ thuộc trở nên tường minh và việc thay công nghệ lưu trữ ít ảnh hưởng đến service. **IoC và DIP** hỗ trợ phân chia trách nhiệm; DI container là bước tự động hóa tùy nhu cầu, không phải điều kiện để thực hành DI đúng.
