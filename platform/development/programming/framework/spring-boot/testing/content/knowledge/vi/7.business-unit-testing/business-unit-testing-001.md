# Kiểm thử service bằng constructor injection mà không khởi động Spring

Trong Spring Boot, một service thường chứa quy tắc nghiệp vụ và phối hợp với các thành phần như repository, HTTP client, clock hoặc message publisher. Để kiểm tra **logic của chính service**, chúng ta có thể dùng **JUnit Jupiter + Java thuần**, tạo service thật bằng constructor rồi cung cấp những phụ thuộc có thể điều khiển trong test. **Không cần khởi tạo Spring `ApplicationContext`** nếu hành vi cần xác minh không phụ thuộc vào framework.

Đây là kỹ thuật căn bản của nhóm **Unit test nghiệp vụ**: chạy nhanh, dễ xác định nguyên nhân khi thất bại, kiểm soát đầu vào và khuyến khích thiết kế ranh giới phụ thuộc rõ ràng. Mục tiêu là kiểm tra **mã nghiệp vụ thật** của service. Các dependency ở rìa được thay bằng mock, stub, fake hoặc đối tượng deterministic (như `Clock.fixed`), tùy câu hỏi cần chứng minh.

## 1. Xác định đối tượng và ranh giới của bài test

Giả sử hệ thống đặt hàng có sơ đồ:

```text
HTTP request
    |
    v
OrderController
    |
    v
OrderService  <--- SUT: xử lý quy tắc nghiệp vụ thật
    |-- StockGateway ----> REST API / hệ thống tồn kho
    |-- OrderStore ------> database
    \-- Clock -----------> đồng hồ hệ thống
```

**SUT (System Under Test)** là `OrderService`. Điều cần kiểm chứng không phải HTTP hay database, mà là quyết định của service: kiểm tra dữ liệu, hỏi trạng thái tồn kho, tạo đơn đúng thời điểm và chỉ yêu cầu lưu khi hợp lệ.

Ta có thể mô tả các yêu cầu:

| Tình huống | Given | When | Then |
| --- | --- | --- | --- |
| Hợp lệ, còn hàng | Kho trả `true` | `place("BOOK-7", 2)` | Trả về `Order` đúng dữ liệu và yêu cầu lưu đúng một lần |
| Hết hàng | Kho trả `false` | `place("BOOK-7", 2)` | Ném `OutOfStockException`, không lưu |
| SKU trống | `sku = " "` | `place(" ", 2)` | Ném lỗi dữ liệu, chưa gọi kho hoặc store |
| Số lượng không hợp lệ | `quantity = 0` | `place("BOOK-7", 0)` | Ném lỗi dữ liệu, không gọi phụ thuộc |
| Kho gặp lỗi | Kho ném exception | `place("BOOK-7", 2)` | Theo hợp đồng ví dụ, chuyển tiếp lỗi và không lưu |

Các ca này đều có thể chạy **service thật** với fake/mock ở hai cổng và một clock cố định. Unit test chứng minh service **yêu cầu** lưu khi thích hợp; nó không tự chứng minh SQL đã chạy, DB đã commit hay HTTP trả status nào.

**Ranh giới đúng phụ thuộc câu hỏi:** “Khi không đủ hàng thì service không lưu” là câu hỏi unit test. “`@Transactional` rollback khi repository ném exception” là câu hỏi integration test vì transaction do proxy/transaction manager của Spring thực hiện.

## 2. Constructor injection cho phép dựng service như Java thông thường

**Constructor injection** đưa các phụ thuộc bắt buộc qua constructor:

```java
public OrderService(
        StockGateway stock,
        OrderStore store,
        Clock clock) {
    this.stock = Objects.requireNonNull(stock, "stock");
    this.store = Objects.requireNonNull(store, "store");
    this.clock = Objects.requireNonNull(clock, "clock");
}
```

Đây là **đoạn nằm trong class `OrderService` đầy đủ ở mục 4**. Phương thức `Objects.requireNonNull` giúp thất bại sớm nếu test hay production quên truyền dependency. Các tham chiếu thường được giữ trong trường `private final`.

Trong ứng dụng Spring Boot thật, Spring có thể gọi constructor để tạo bean. Trong unit test, ta tự gọi:

```java
OrderService sut =
        new OrderService(stockDouble, storeDouble, fixedClock);
```

Không có sự khác biệt về cách Java chạy phương thức `place`. Thứ khác biệt là ai tạo các dependency: Spring ở runtime, còn test tự tạo những bản phù hợp.

**Lợi ích của constructor injection:**

- Phụ thuộc được liệt kê trong chữ ký constructor, không ẩn trong field được tự động inject.
- Không phải bật Spring để dựng object hoàn chỉnh; không dùng reflection để gán dependency.
- Không truyền `null` và chờ lỗi muộn trong phương thức nghiệp vụ.
- Dễ thay I/O bằng mock/fake và đồng hồ thật bằng clock cố định.
- Khi thêm dependency bắt buộc, các vị trí gọi constructor không còn khớp chữ ký và được compiler báo, giúp cập nhật test đúng lúc.

**So với field injection:** một trường `@Autowired private OrderStore store;` chỉ được Spring xử lý khi bean được quản lý. Nếu viết `new OrderService()` cho class phụ thuộc field injection, trường đó không được Spring gán; test có thể gặp `NullPointerException` hoặc phải dùng reflection. Constructor injection giải quyết vấn đề ngay từ thiết kế.

**Không cần tạo interface cho mọi class.** Một giá trị `record`, phép tính thuần hoặc policy deterministic nằm trong phạm vi cần kiểm chứng thường nên giữ thật. Interface/port đặc biệt có ích tại ranh giới DB, mạng, file, messaging hoặc nguồn dữ liệu có kết quả phải điều khiển được.

## 3. Tạo service thật, chỉ thay collaborator

Có bốn vai trò cần phân biệt:

- **SUT:** đối tượng service thật được gọi bằng `sut.place(...)`.
- **Stub:** collaborator trả dữ liệu đã sắp đặt, ví dụ `when(stock.available(...)).thenReturn(false)`.
- **Mock:** collaborator dùng để kiểm chứng tương tác như `verify(store).save(expected)` hay `verifyNoInteractions(store)`.
- **Fake:** implementation đơn giản thực thi được, ví dụ `OrderStore` lưu vào `ArrayList` thay vì database.

Mockito có thể thực hiện cả vai trò stub và mock. **`@Mock` của Mockito không yêu cầu Spring context.** `@ExtendWith(MockitoExtension.class)` là JUnit extension giúp tạo mock, không phải lệnh khởi động Spring Boot.

| Phần trong ví dụ | Dùng gì trong unit test? | Vì sao? |
| --- | --- | --- |
| `OrderService` | Object thật qua `new` | Chạy đúng nhánh nghiệp vụ |
| `StockGateway` | Stub/mock hoặc lambda fake | Ép câu trả lời đủ/hết hàng, lỗi kho |
| `OrderStore` | Mock hoặc fake in-memory | Kiểm chứng lệnh lưu hoặc không lưu |
| `Clock` | `Clock.fixed(...)` | Không phụ thuộc ngày chạy test |
| `Order` | Java record thật | Kiểm chứng giá trị dữ liệu |
| Spring container | Không dùng | Không có framework behavior nào cần chứng minh trong các case này |

**Lỗi quan trọng:** nếu mock chính `OrderService` rồi stub `place(...)` trả đơn mong đợi, bài test chỉ xác nhận thư viện Mockito trả dữ liệu đã dặn. Nó không kiểm tra validation, hết hàng hay lưu đơn của production code.

## 4. Ví dụ đầy đủ với Java 17+: OrderService

Ví dụ dưới đây thiết kế để có thể biên dịch bằng JDK 17+ và chạy trong project Spring Boot đã có JUnit Jupiter/Mockito. Business rule được đặt trong Java thuần, không cần annotation Spring để service hoạt động.

Tổ chức file:

```text
src/
├── main/java/example/testing/orders/
│   ├── OrderService.java
│   └── OrderServiceDemo.java
└── test/java/example/testing/orders/
    ├── OrderServiceTest.java
    └── OrderServiceFakeTest.java
```

### 4.1. File production: OrderService.java

Tạo `src/main/java/example/testing/orders/OrderService.java`:

```java
package example.testing.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public class OrderService {
    private final StockGateway stock;
    private final OrderStore store;
    private final Clock clock;

    public OrderService(
            StockGateway stock,
            OrderStore store,
            Clock clock) {
        this.stock = Objects.requireNonNull(stock, "stock");
        this.store = Objects.requireNonNull(store, "store");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Order place(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        if (!stock.available(sku, quantity)) {
            throw new OutOfStockException(sku);
        }

        Order order = new Order(
                sku, quantity, Instant.now(clock));
        store.save(order);
        return order;
    }
}

interface StockGateway {
    boolean available(String sku, int quantity);
}

interface OrderStore {
    void save(Order order);
}

record Order(String sku, int quantity, Instant createdAt) {}

class OutOfStockException extends RuntimeException {
    OutOfStockException(String sku) {
        super("Out of stock: " + sku);
    }
}
```

Trong Java, file này hợp lệ vì chỉ có một kiểu top-level `public` là `OrderService` và tên file trùng tên kiểu đó. Những interface, record và exception còn lại là **package-private**. Vì các test cùng package `example.testing.orders` nên truy cập được chúng. Dự án lớn có thể tách mỗi kiểu thành file riêng và điều chỉnh visibility khi adapter nằm ở package khác.

**Luồng thực thi:**

1. Constructor từ chối ba dependency null.
2. `place` kiểm tra SKU và quantity trước khi làm việc với dependency ngoài.
3. `StockGateway.available(sku, quantity)` quyết định còn hàng.
4. Hết hàng: ném `OutOfStockException`; không gọi store.
5. Còn hàng: tạo record `Order` với `Instant.now(clock)`, gọi `store.save(order)` rồi trả về record.

Trong ví dụ, nếu `stock.available` hoặc `store.save` ném exception, service **không bắt, không retry**; lỗi đi lên caller. Đây là hành vi hiện tại của code ví dụ, không phải quy tắc chung cho mọi hệ thống. Nếu yêu cầu nghiệp vụ cần retry/idempotency/compensation thì phải thiết kế và kiểm thử riêng.

### 4.2. Bộ test JUnit Jupiter với Mockito

Tạo `src/test/java/example/testing/orders/OrderServiceTest.java`:

```java
package example.testing.orders;

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
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-01-15T08:00:00Z");

    @Mock
    StockGateway stock;

    @Mock
    OrderStore store;

    private OrderService sut;

    @BeforeEach
    void setUp() {
        Clock fixedClock = Clock.fixed(NOW, ZoneOffset.UTC);
        sut = new OrderService(stock, store, fixedClock);
    }

    @Test
    void inStock_returnsAndSavesOrder() {
        when(stock.available("BOOK-7", 2)).thenReturn(true);

        Order actual = sut.place("BOOK-7", 2);

        Order expected = new Order("BOOK-7", 2, NOW);
        assertEquals(expected, actual);
        verify(store).save(expected);
    }

    @Test
    void outOfStock_throwsAndDoesNotSave() {
        when(stock.available("BOOK-7", 2)).thenReturn(false);

        OutOfStockException error = assertThrows(
                OutOfStockException.class,
                () -> sut.place("BOOK-7", 2));

        assertEquals("Out of stock: BOOK-7",
                error.getMessage());
        verifyNoInteractions(store);
    }

    @Test
    void blankSku_isRejectedBeforeDependencies() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> sut.place(" ", 2));

        assertEquals("sku must not be blank",
                error.getMessage());
        verifyNoInteractions(stock, store);
    }

    @Test
    void nonPositiveQuantity_isRejectedBeforeDependencies() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> sut.place("BOOK-7", 0));

        assertEquals("quantity must be positive",
                error.getMessage());
        verifyNoInteractions(stock, store);
    }

    @Test
    void inventoryFailure_isPropagatedWithoutSaving() {
        when(stock.available("BOOK-7", 2))
                .thenThrow(new IllegalStateException(
                        "inventory unavailable"));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> sut.place("BOOK-7", 2));

        assertEquals("inventory unavailable",
                error.getMessage());
        verifyNoInteractions(store);
    }
}
```

**Điểm quan trọng:** class test chỉ dùng JUnit và Mockito, **không** gắn `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, `@Autowired` hay `@MockBean`. `MockitoExtension` quản lý `@Mock` qua JUnit lifecycle; `@BeforeEach` chạy sau khi Mockito đã thiết lập các mock cần thiết.

Từng test thực sự kiểm tra gì?

- **`inStock_returnsAndSavesOrder`:** stub cổng tồn kho trả `true`, service tạo record với đúng SKU, số lượng và thời điểm từ fixed clock. `verify(store).save(expected)` mặc định xác minh một lời gọi khớp.
- **`outOfStock_throwsAndDoesNotSave`:** ném đúng exception và store không hề bị gọi. Đây là một thuộc tính nghiệp vụ quan trọng: thất bại không được sinh lệnh lưu.
- **`blankSku_isRejectedBeforeDependencies`:** đầu vào sai bị từ chối trước khi truy cập kho hay store. Nó bắt được lỗi code gọi I/O rồi mới validate.
- **`nonPositiveQuantity_isRejectedBeforeDependencies`:** số lượng 0 bị từ chối tại boundary.
- **`inventoryFailure_isPropagatedWithoutSaving`:** khi cổng kho gặp lỗi, service không tạo lệnh lưu; test còn xác nhận hành vi chuyển tiếp exception của code hiện tại.

**Vì sao clock phải cố định?** Nếu service gọi `Instant.now()` không có `Clock` được inject, thời gian trong expected có thể chênh vài mili giây so với actual hoặc phụ thuộc thời điểm CI chạy. Dùng `Clock.fixed(...)` giúp `createdAt` luôn bằng đúng `NOW` và khiến assertion có tính quyết định.

**Vì sao dùng record?** `Order` là `record` nên Java sinh `equals` theo các thành phần `sku`, `quantity` và `createdAt`. `assertEquals(expected, actual)` bảo vệ cả ba. Với entity/DTO không có value equality, nên assert trực tiếp các trường liên quan thay vì giả định mọi object có `equals` phù hợp.

### 4.3. Unit test với fake: không cần Mockito

Nếu chỉ muốn quan sát dữ liệu được gửi tới store, có thể dùng fake đơn giản. Tạo `src/test/java/example/testing/orders/OrderServiceFakeTest.java`:

```java
package example.testing.orders;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderServiceFakeTest {

    @Test
    void savesOneOrderToAnInMemoryStore() {
        Instant fixedNow =
                Instant.parse("2026-01-15T08:00:00Z");
        Clock fixedClock =
                Clock.fixed(fixedNow, ZoneOffset.UTC);

        List<Order> saved = new ArrayList<>();

        StockGateway stock = (sku, quantity) -> true;
        OrderStore store = order -> {
            saved.add(order);
        };

        OrderService sut =
                new OrderService(stock, store, fixedClock);

        Order actual = sut.place("BOOK-7", 2);
        Order expected =
                new Order("BOOK-7", 2, fixedNow);

        assertEquals(expected, actual);
        assertEquals(List.of(expected), saved);
    }
}
```

`StockGateway` và `OrderStore` ở ví dụ đều là functional interfaces, nên lambda triển khai hợp lệ. `List<Order>` chỉ tồn tại trong phạm vi test, không phải repository thật. Nó giúp kiểm tra service tạo và gửi đúng dữ liệu mà không phải `verify(...)` từng tương tác.

**Lựa chọn giữa mock và fake:** với hành vi “không gửi lệnh thanh toán khi thiếu tiền”, mock và `verifyNoInteractions` rất rõ. Với chuỗi thao tác đơn giản lên một tập dữ liệu, fake in-memory và assertion trên state có thể dễ đọc hơn. Không bắt buộc duy trì cả hai bộ test cho cùng một happy path trong production; đây là hai kỹ thuật thay thế được minh họa riêng.

### 4.4. Cấu hình chạy test bằng Gradle

Trong dự án Spring Boot đã thiết lập Gradle plugin và dependency management, phần cấu hình liên quan ở `build.gradle` (Groovy DSL) có thể là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn bổ sung** vào project đã có plugin/phiên bản thích hợp, không phải toàn bộ file build độc lập. Với cấu hình Spring Boot thông dụng, starter test cung cấp JUnit Jupiter và Mockito; `MockitoExtension` cần `mockito-junit-jupiter` trên test classpath. Nếu project tự quản lý test dependencies, bảo đảm các artifact/phiên bản này tương thích.

Chạy từ project có Gradle wrapper:

```bash
./gradlew test --tests example.testing.orders.OrderServiceTest
./gradlew test --tests example.testing.orders.OrderServiceFakeTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.orders.OrderServiceTest"
.\gradlew.bat test --tests "example.testing.orders.OrderServiceFakeTest"
```

**Kỳ vọng:** năm test Mockito và một test fake đều pass khi các file và dependency được tạo đúng. Thông báo của Gradle/JUnit phụ thuộc test runner và logging, vì vậy không có một chuỗi stdout cố định. Test report có thể hiển thị số case và kết quả. Với build nhiều subproject, chọn đúng test task/subproject chứa source.

### 4.5. Chạy production code bằng javac/java độc lập

Để thấy rõ logic không cần Spring hay Mockito, tạo `src/main/java/example/testing/orders/OrderServiceDemo.java`:

```java
package example.testing.orders;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public class OrderServiceDemo {
    public static void main(String[] args) {
        List<Order> saved = new ArrayList<>();

        StockGateway stock = (sku, quantity) ->
                quantity <= 5;
        OrderStore store = order -> {
            saved.add(order);
        };
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-15T08:00:00Z"),
                ZoneOffset.UTC);

        OrderService service =
                new OrderService(stock, store, fixedClock);
        Order order = service.place("BOOK-7", 2);

        System.out.println(order.sku());
        System.out.println(order.quantity());
        System.out.println(order.createdAt());
        System.out.println(saved.size());
    }
}
```

Từ thư mục gốc project, dùng JDK 17+:

```bash
javac -d out src/main/java/example/testing/orders/OrderService.java src/main/java/example/testing/orders/OrderServiceDemo.java
java -cp out example.testing.orders.OrderServiceDemo
```

Stdout chính xác:

```text
BOOK-7
2
2026-01-15T08:00:00Z
1
```

Lệnh trên chạy một chương trình `main` minh họa với fake in-memory; **không phải phép chạy JUnit**. Các nhánh exception và kiểm chứng tương tác cần được chạy trong test runner như mục 4.4.

## 5. Ai khởi tạo object trong unit test?

Luồng thực tế của `OrderServiceTest`:

```text
JUnit Jupiter
    |
    +-- MockitoExtension tạo @Mock StockGateway và OrderStore
    |
    +-- @BeforeEach:
    |     fixedClock = Clock.fixed(...)
    |     sut = new OrderService(stock, store, fixedClock)
    |
    +-- @Test:
    |     khi cần thì when(stock.available(...)).thenReturn(...)
    |     gọi sut.place(...) trên service THẬT
    |     assertEquals / assertThrows / verify(...)
    |
    \-- JUnit ghi kết quả từng ca
```

Trong luồng này **không có** bước Spring quét component, tạo bean, áp dụng auto-configuration, đọc datasource, mở web server hay tạo transaction proxy.

Ba tầng công cụ thường bị nhầm:

- **JUnit Jupiter:** chạy test, lifecycle `@BeforeEach`, `@Test` và assertion.
- **Mockito:** tạo mock và cung cấp API `when(...)/verify(...)`; `MockitoExtension` tích hợp Mockito với JUnit.
- **Spring Test/Boot:** chỉ tham gia khi test thực sự tạo Spring context hoặc sử dụng cấu hình/test infrastructure thích hợp. Sự tồn tại của dependency `spring-boot-starter-test` trên test classpath **không tự tạo ApplicationContext**.

Trong test Mockito, có thể thay `@Mock` bằng cách tạo trực tiếp:

```java
StockGateway stock = Mockito.mock(StockGateway.class);
OrderStore store = Mockito.mock(OrderStore.class);

OrderService sut = new OrderService(
        stock,
        store,
        Clock.fixed(
                Instant.parse("2026-01-15T08:00:00Z"),
                ZoneOffset.UTC));
```

Đây là **đoạn nằm trong một method test**, cần import `org.mockito.Mockito` và các kiểu thời gian. Cách này tạo mock bằng Java method call; không cần `MockitoExtension` chỉ để khởi tạo chúng. Với nhiều test, extension và `@BeforeEach` thường giúp code gọn, nhưng không phải điều kiện để unit test không Spring hoạt động.

### Có nên dùng @InjectMocks?

`@InjectMocks` là cơ chế thử inject mock vào một đối tượng qua constructor/setter/field của **Mockito**, không khởi động Spring. Nó có thể tiện, nhưng với mục tiêu rèn luyện constructor injection, viết rõ:

```java
sut = new OrderService(stock, store, fixedClock);
```

sẽ dễ review hơn. Nếu constructor thêm một dependency mới, compiler chỉ ra các chỗ khởi tạo cần cập nhật. Injection tự động có thể khiến test ít bộc lộ yêu cầu constructor và cần thận trọng với dependency không được cung cấp. Không dùng `@InjectMocks` như lý do tránh thiết kế dependency rõ ràng.

## 6. Thiết kế test có giá trị: output, exception, tương tác

Một unit test service tốt nên kiểm tra **hành vi quan sát được**, không chỉ xem method chạy xong mà không lỗi.

**Đầu ra:** đơn hàng trả về đúng dữ liệu; `assertEquals(new Order("BOOK-7", 2, NOW), actual)` bảo vệ các thuộc tính của record. Với đối tượng mutable/entity, kiểm tra những trường thuộc hợp đồng thay vì dựa vào object identity ngẫu nhiên.

**Ngoại lệ:** `assertThrows(OutOfStockException.class, ...)` xác nhận nhánh lỗi, `assertEquals(...)` với message chỉ nên dùng khi thông điệp là hợp đồng có ý nghĩa. `assertThrows` chấp nhận subtype; nếu yêu cầu đúng class exception, JUnit Jupiter còn có `assertThrowsExactly(...)`.

**Side effect:** `verify(store).save(expected)` chứng minh service gửi đúng lệnh lưu một lần. `verifyNoInteractions(store)` chứng minh không có bất kỳ lời gọi nào tới collaborator trong nhánh lỗi. Với collaborator có nhiều method, kiểm tra `never().save(...)` có phạm vi hẹp hơn “không có bất cứ tương tác nào”; chọn theo hợp đồng thực.

**Thứ tự:** không khóa cứng từng helper phải gọi trước/sau trừ khi thứ tự là yêu cầu nghiệp vụ. Với ví dụ này, “validate trước khi gọi kho” là có ý nghĩa vì input sai không được chạm I/O. Đặt assert `verifyNoInteractions(stock, store)` giúp bảo vệ thứ tự đó.

**Kết quả lỗi dependency:** khi kho throw, test `inventoryFailure_isPropagatedWithoutSaving` chứng minh store không được gọi. Nếu yêu cầu retry 3 lần hoặc map lỗi khác, cần bổ sung case đặc thù và thiết kế cụ thể, không suy diễn từ test hiện tại.

**Tính quyết định:** đồng hồ/UUID/random/network cần kiểm soát nếu ảnh hưởng kết quả. Inject `Clock` như ví dụ; nguồn ID có thể tiêm `Supplier<UUID>` hoặc interface sinh ID nếu cần; tránh chuyển mọi hằng số đơn giản thành interface.

### Chọn fixture và stubbing hợp lý

Trong `@BeforeEach`, chỉ dựng SUT và những dependency **được dùng chung**. Không nên tạo mọi `when(...)` trong setup nếu nhiều test không sử dụng. Mockito có thể báo **unnecessary stubbing** ở chế độ strict và việc stub toàn cục che điều kiện Given thật của từng test.

Thay vào đó:

```java
@Test
void outOfStock_throwsAndDoesNotSave() {
    when(stock.available("BOOK-7", 2)).thenReturn(false);
    // Gọi SUT và assert đúng hành vi ...
}
```

Đoạn này minh họa vị trí stubbing trong test; test hoàn chỉnh ở mục 4.2 có đủ assertion. Đặt stub sát case giúp thay đổi logic không vô tình làm test pass nhờ cấu hình quá rộng. Dùng matchers như `anyString()` khi thật sự không quan tâm giá trị, còn với SKU/số lượng mang ý nghĩa nghiệp vụ nên dùng đối số cụ thể.

## 7. Những hành vi chỉ Spring hoặc hạ tầng thật mới chứng minh được

Một object tạo qua `new` **không tự đi qua Spring AOP proxy**. Unit test service có thể xanh trong khi cấu hình runtime gặp lỗi về transaction, bean wiring, security hoặc repository. Các loại test bổ sung nên tương ứng đúng với lời khẳng định:

| Điều cần chứng minh | Test constructor thuần có làm được? | Nơi cần kiểm tra |
| --- | --- | --- |
| Quy tắc validate, còn/hết hàng, kết quả trả về | Có | JUnit/Mockito/fake |
| Không gửi lệnh lưu khi dữ liệu sai | Có, tại service boundary | JUnit + verify/fake |
| DB thật đã ghi, SQL và constraint đúng | Không | Repository/DB integration test |
| `@Transactional` commit/rollback | Không | Context với transaction manager và DB thích hợp |
| `@Cacheable` tạo cache hit/miss | Không | Test có caching proxy/config thực |
| Method security `@PreAuthorize` | Không | Test Spring Security phù hợp |
| `@Value`, `@ConfigurationProperties` và bean wiring | Không | Context/configuration test |
| HTTP binding, JSON, validation và status | Không | `@WebMvcTest`/`MockMvc` hoặc integration test |
| HTTP client serialization, retry, timeout thực | Không | Client adapter/contract test |
| Luồng nhiều thành phần hoạt động cùng nhau | Không | `@SpringBootTest`/integration test phù hợp |

**Ví dụ với `@Transactional`:** nếu annotate method của service rồi gọi object bằng `new`, transaction interceptor không chạy, nên test không chứng minh rollback. Trong Spring runtime, proxy-based transaction còn phụ thuộc lời gọi đi **qua proxy**; self-invocation qua `this.method()` thường không đi qua interceptor. Nếu dùng class/method final và proxy dựa trên subclass, còn phải kiểm tra giới hạn proxy cụ thể. Vì vậy test nghiệp vụ không thể thay thế test giao dịch.

**Ví dụ HTTP:** gọi `service.place(...)` không chứng minh `POST /orders` trả 201/400/409 hay Spring chuyển JSON đầu vào thành DTO đúng. Nếu đó là hợp đồng cần bảo vệ, dùng MVC slice hoặc integration test có request qua infrastructure thật.

**Ví dụ database:** `verify(store).save(order)` chỉ chứng minh lệnh được phát ra qua port. Fake in-memory không kiểm tra unique index, transaction isolation, migration, locking hoặc query. Nếu quy trình đặt hàng đòi nhất quán tồn kho dưới concurrency, cần thiết kế/test phối hợp hạ tầng thích hợp.

Một tính năng có thể có **nhiều lớp bằng chứng**: unit test dày cho logic nghiệp vụ; adapter/repository test cho I/O; một số integration tests cho wiring/transaction/HTTP quan trọng. Chi phí và rủi ro quyết định số lượng, không có tỷ lệ bắt buộc.

## 8. Dùng constructor injection trong production Spring Boot

Service Java thuần có thể được Spring quản lý mà không sửa logic. Một cách đăng ký là `@Configuration` với `@Bean`:

```java
@Configuration
class OrderConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderService orderService(
            StockGateway stock,
            OrderStore store,
            Clock clock) {
        return new OrderService(stock, store, clock);
    }
}
```

Đây là **đoạn minh họa trong project Spring**, cần imports `org.springframework.context.annotation.Configuration`, `Bean` và `java.time.Clock`; cần adapter thật được đăng ký cho hai port, và package/config được Spring scan hoặc import phù hợp. Nó **không phải một file Java độc lập** để biên dịch bằng JDK thuần. Với interface package-private như ví dụ, config phải cùng package hoặc các interface được chuyển sang API có mức truy cập phù hợp.

Cách khác là gắn `@Service` lên `OrderService` và cung cấp đúng một constructor phù hợp để Spring tự inject dependency. Không khai báo hai bean service cùng mục đích nếu không có chủ đích. Nếu thêm annotation AOP như `@Transactional`, cần kiểm tra proxy/runtime bằng integration test, không suy diễn từ constructor-based unit test.

Trong unit test, dù production chọn `@Bean` hay `@Service`, dòng thiết lập vẫn:

```java
OrderService sut =
        new OrderService(stockDouble, storeDouble, fixedClock);
```

Sự độc lập này là điều ta mong muốn: **business logic có thể chạy và được kiểm chứng bằng Java thông thường**; Spring chịu trách nhiệm tạo và kết nối các thành phần production.

## 9. Ranh giới test có thể gồm hơn một class

“Unit” không bắt buộc là **một method** hay **một bean**. Nếu service gọi một `PriceCalculator` là class thuần, nhanh, không có I/O và kết quả deterministic, có thể giữ calculator thật để kiểm tra hành vi đặt hàng cùng tính giá. Ngược lại, khi service gọi SQL hoặc API từ xa, thường nên tách ranh giới đó bằng port và mock/fake, vì test phải chủ động ép lỗi và chạy ổn định.

Khi constructor có quá nhiều dependency, đó có thể là tín hiệu class đang gánh quá nhiều trách nhiệm. Hãy kiểm tra lại nghiệp vụ và hướng phụ thuộc, không tự tạo hàng chục interface chỉ để số lượng mock ít đi. Nguyên tắc vẫn là: **logic cần chứng minh phải chạy thật; môi trường ngoài chỉ thay khi việc thay thế giúp điều khiển đúng điều kiện test**.

Trong mã legacy dùng static singleton, gọi HTTP ẩn trong method hoặc đọc `System.currentTimeMillis()`, có thể cần refactor để tách side effect thành dependency rõ. Làm điều đó cùng test bảo vệ hành vi hiện tại và test cho yêu cầu mới; tránh thay đổi cả rule, transaction và I/O cùng lúc khi chưa có bằng chứng hồi quy.

## 10. Lỗi thường gặp

**1. Mock chính service.** Stub `when(sut.place(...)).thenReturn(...)` không chạy code nghiệp vụ. Tạo service thật, mock những collaborator ngoài ranh giới.

**2. Bật `@SpringBootTest` cho mọi phép kiểm tra nhỏ.** ApplicationContext tạo chi phí và nguyên nhân lỗi không liên quan. Dùng JUnit thuần khi không cần tính năng Spring; bổ sung context test cho những gì thực sự cần nó.

**3. Có `@Mock` nhưng quên MockitoExtension hoặc khởi tạo thủ công.** Field mock không được tạo đúng sẽ làm constructor nhận null. Dùng `@ExtendWith(MockitoExtension.class)` hoặc `Mockito.mock(...)`.

**4. Dùng `@InjectMocks` để che constructor.** Tự gọi constructor giúp nhìn rõ đủ/mất dependency, dễ sửa khi chữ ký thay đổi.

**5. Field injection làm test cần reflection.** Nếu không có Spring context, `@Autowired` field không tự được gán. Constructor injection đơn giản hóa cả runtime thiết kế lẫn unit test.

**6. Mock cả value object và policy thuần.** Khi mock phần cần chứng minh, test trở thành bài kiểm tra stub; giữ thật logic deterministic trong ranh giới phù hợp.

**7. Stub mọi collaborator trong `@BeforeEach`.** Các stub không dùng có thể làm test khó hiểu hoặc báo strict stubbing. Chỉ khai báo Given cần thiết cho từng case.

**8. Khóa test vào mọi lời gọi nội bộ.** Assertion về lệnh lưu/không lưu hữu ích; assertion về private helper hoặc thứ tự không thuộc nghiệp vụ dễ vỡ khi refactor.

**9. Dùng mock repository rồi khẳng định DB đã commit.** Đây là vượt quá chứng cứ unit test. Dùng repository/transaction integration test khi điều cần bảo vệ nằm ở SQL/DB.

**10. Không kiểm soát thời gian, random hoặc state chung.** Inject `Clock`, nguồn ID hoặc fake cô lập; test phải lặp lại ổn định bất kể thời điểm chạy.

**11. Chỉ viết happy path.** Nếu input sai nhưng service vẫn gọi DB trước khi throw, test chỉ có thành công sẽ bỏ sót bug. Thêm case dữ liệu biên và không có side effect.

**12. Fake không giống DB thật.** In-memory fake có thể bỏ qua transaction, constraint và concurrency. Dùng fake để xác minh quyết định service; dùng hạ tầng thật để chứng minh đặc tính adapter.

## 11. Checklist thực hành

Trước khi tạo test:

- Xác định hành vi service cần chứng minh, đầu vào và kết quả quan sát được chưa?
- Service có constructor liệt kê đầy đủ dependency bắt buộc không?
- Phần nào nên chạy thật, phần nào cần stub/mock/fake để điều khiển dữ liệu và side effect?
- Đã kiểm soát clock, ID, random hoặc I/O ngoài ranh giới khi cần chưa?

Trong test:

- **Given:** tạo SUT thật bằng `new` và chuẩn bị chính xác điều kiện collaborator của case.
- **When:** gọi một hành vi public, không dùng reflection để gọi private method.
- **Then:** assert output/exception và tương tác có ý nghĩa nghiệp vụ.
- Có case thành công, thất bại, input biên và không thực hiện side effect khi lỗi?
- Test chạy bằng JUnit và không vô tình đòi Spring context/DB/network?

Sau khi test xanh:

- Khi refactor, những assertion còn bảo vệ hành vi thay vì chi tiết implementation không?
- Lời khẳng định “service yêu cầu lưu” đã được phân biệt với “DB thực sự lưu” chưa?
- Có behavior phụ thuộc proxy/transaction/security/HTTP/DB cần integration test riêng không?

**Ghi nhớ:** constructor injection giúp service Java được dựng **đầy đủ và rõ ràng** ngoài Spring. Khi kiểm thử nghiệp vụ, tạo **service thật**, truyền collaborator có thể kiểm soát, xác nhận output/exception/side effect tại đúng ranh giới. Spring context chỉ cần thiết khi chính **hành vi của Spring hoặc hạ tầng kết nối** là điều cần chứng minh.