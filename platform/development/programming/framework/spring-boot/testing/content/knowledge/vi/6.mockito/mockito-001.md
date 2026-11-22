# Mockito: Mock, stub, fake và spy trong thiết kế kiểm thử

## 1. Mục tiêu và vấn đề cần giải quyết

Khi kiểm thử một service Spring Boot, đối tượng được kiểm thử (system under test, **SUT**) thường phụ thuộc repository, HTTP client, cổng thanh toán, bộ gửi email hoặc một bean khác. Ta cần chọn thành phần nào chạy thật, thành phần nào được thay thế để test **nhanh, lặp lại được và phát hiện đúng lỗi cần tìm**.

Các tên **mock**, **stub**, **fake** và **spy** mô tả những vai trò khác nhau của *test double* (đối tượng thay thế trong test). Mockito cung cấp nhiều công cụ để tạo hoặc quan sát những vai trò này, nhưng **đối tượng tạo bằng `Mockito.mock()` không tự động mang ý nghĩa “mock” trong mọi bài test**: nếu chỉ dùng nó để trả dữ liệu được định trước, nó đang đóng vai trò *stub*. Ngược lại, khi dùng `verify(...)` để xác minh tương tác, nó đóng vai trò *mock* theo nghĩa kiểm thử hành vi.

Kết thúc bài học, bạn cần:

- Phân biệt test double với production implementation, hiểu dummy, stub, fake, mock và spy.
- Xác định lựa chọn theo câu hỏi “test đang kiểm **trạng thái/kết quả** hay **tương tác**?”.
- Biết dùng `mock`, `when(...).thenReturn(...)`, `thenThrow`, `verify`, `@Mock`, `spy`, `@Spy` và `doReturn(...).when(...)`.
- Viết được unit test Java 17+ với JUnit Jupiter và Mockito, trong đó SUT chạy thật.
- Hiểu giới hạn của fake, nguy cơ spy gọi code thật, strict stubbing, trường hợp cần integration test Spring Boot.
- Tránh bài test chỉ lặp lại cấu hình mock hoặc phụ thuộc quá chặt vào chi tiết triển khai.

## 2. Test double là gì? Phân biệt năm khái niệm

**Test double** là cách gọi chung cho thành phần thay một collaborator của SUT. Không phải mọi test double đều là một Mockito mock.

| Loại | Ý nghĩa chính | Bằng chứng test thường kiểm | Ví dụ |
| --- | --- | --- | --- |
| **Dummy** | Chỉ để truyền vào tham số bắt buộc; test không sử dụng hành vi của nó | Không có tương tác/giá trị cần quan tâm | Một đối tượng thông tin phụ không được đọc trong kịch bản |
| **Stub** | Trả về kết quả hoặc ném lỗi đã định trước | Kết quả SUT khi nhận đầu vào từ collaborator | `when(catalog.price("BOOK")).thenReturn(1500L)` |
| **Fake** | Implementation giản lược nhưng có hành vi và trạng thái thực sự | Trạng thái sau các thao tác | Repository dùng `Map` thay vì database |
| **Mock** | Đối tượng để xác minh lời gọi và tham số/số lần gọi | SUT có gửi đúng lệnh hay không | `verify(payment).charge("ORD-1", 3000L)` |
| **Spy** | Bọc một đối tượng thật, mặc định cho chạy method thật nhưng có thể quan sát hoặc stub chọn lọc | Vừa kiểm hành vi thật, vừa kiểm tương tác | `spy(new ArrayList<>())`; `verify(spyList).add("A")` |

**Thành phần thật** không phải test double: nó là implementation production hoặc implementation thực của đối tượng bạn muốn kiểm. Chẳng hạn, khi kiểm quy tắc checkout, phải tạo và chạy **`CheckoutService` thật**; mock chính service sẽ không chứng minh được logic checkout.

### Stub và mock phân biệt bằng điều test muốn khẳng định

Giả sử collaborator là `ExchangeRateProvider`:

~~~java
when(rateProvider.rate("USD", "VND")).thenReturn(25_000L);
~~~

Khi test gọi SUT và `assertEquals(...)` lên tổng tiền quy đổi, rate provider đang đóng vai trò **stub**: nó cung cấp đầu vào kiểm soát được. Nếu test thêm:

~~~java
verify(rateProvider).rate("USD", "VND");
~~~

thì bài test còn kiểm **tương tác** của SUT với provider. Cùng một đối tượng Mockito có thể vừa trả dữ liệu (stub) vừa được xác minh lời gọi (mock). Đoạn mã trên minh họa API; `rateProvider` và hợp đồng `rate(...)` do ứng dụng cung cấp.

Từ “mock” trong tài liệu/đời thường có thể được dùng rộng cho bất kỳ đối tượng `Mockito.mock()` nào; khi thiết kế test, hãy nói rõ **đang stub dữ liệu hay verify lời gọi** để tránh nhầm mục tiêu.

### Fake không chỉ là stub có nhiều dữ liệu

Stub thường trả kết quả được lập trình từ trước. Fake triển khai một quy tắc tối thiểu nhưng **có state**: ví dụ `save(order)` làm `findById(id)` đọc được order vừa lưu, hoặc `delete(id)` làm item biến mất.

Fake rất tiện để kiểm chuỗi thao tác nghiệp vụ, nhưng **không trở thành PostgreSQL** chỉ vì nó thực thi `OrderRepository` interface. Nó không mặc nhiên mô phỏng unique index, foreign key, SQL transaction, locking, rollback hoặc query dialect. Những đặc tính đó phải được kiểm với adapter/database thật khi cần.

## 3. Quyết định dựa trên hành vi và rủi ro

Trước khi dùng Mockito, hãy viết một câu xác định **lỗi bạn muốn bài test phát hiện**:

- “Nếu tồn kho không đủ, hệ thống không được thu tiền” → service thật, fake tồn kho để dựng state, mock payment port để `verifyNoInteractions`.
- “Tổng tiền sau khuyến mãi phải là 3.000 cent” → công thức thật, stub bảng giá/discount làm dữ liệu cố định, assert giá trị trả về.
- “Khi thanh toán thành công, đơn hàng phải được lưu” → service thật, fake repository nhỏ để assert state. Nếu mục tiêu là kiểm SQL/schema, cần repository và DB thật.
- “Chỉ một email xác nhận được yêu cầu gửi” → mock mail port, `verify(..., times(1))` với recipient và nội dung quan trọng.
- “Một formatter thật phải được gọi, đồng thời giữ cách format gốc” → có thể dùng spy, nhưng ưu tiên assert output nếu không cần kiểm lời gọi.
- “`@Transactional` rollback và unique constraint thật hoạt động” → Spring-managed bean + database thật trong integration test; mock/fake không đủ.

Quy tắc chọn:

1. **Giữ implementation thật ở nơi chứa logic cần kiểm.** Đây là SUT.
2. Nếu chỉ cần một giá trị hoặc lỗi cố định từ collaborator, **stub**.
3. Nếu cần trạng thái qua nhiều thao tác nhưng không quan tâm đặc tính hệ thống ngoài, **fake**.
4. Nếu **lời gọi đi ra ngoài là một phần hợp đồng**, **mock** và verify các tương tác có ý nghĩa.
5. Nếu cần quan sát đối tượng thật mà không muốn thay toàn bộ implementation, có thể **spy**, nhưng kiểm rủi ro thực thi thật.
6. Nếu lỗi tiềm ẩn nằm ở SQL, migration, serialization, HTTP wire protocol, Redis TTL hay Kafka acknowledgement, **integration test với adapter/dịch vụ thật hoặc test server phù hợp**.

Nên ưu tiên assertion trên **đầu ra và trạng thái công khai**, bởi bài test kiểm quá nhiều lời gọi nội bộ sẽ bị vỡ khi code được refactor dù hành vi vẫn đúng. Verify là công cụ thiết yếu khi chính tương tác là yêu cầu nghiệp vụ.

## 4. Thiết kế seam: thay tại ranh giới, giữ phần quan trọng chạy thật

Giả sử một checkout service có bốn collaborator:

~~~text
                +-----------------------+
  checkout() -->| CheckoutService THẬT |
                +-----------------------+
                    |    |      |     |
                    v    v      v     v
                Catalog Payment Store  Audit
                 stub    mock   fake    spy
~~~

- `Catalog` trả giá được kiểm soát để test tập trung vào tính tổng.
- `PaymentGateway` phải được gọi đúng số tiền, đúng order ID nên test dùng mock.
- `OrderStore` dùng fake `Map` để quan sát đơn được lưu mà không phải khởi động database.
- `AuditTrail` dùng spy cho phần ghi log nội bộ thật và thêm khả năng verify trong một số kịch bản.

Trong production, bốn interface này có thể được cài bằng HTTP client, JDBC repository, logging service… Unit test **không cần biết** URL, pool, network hay bean wiring khi mục tiêu là nghiệp vụ của `CheckoutService`.

**Port/interface ở ranh giới có lợi nhưng không nên tạo interface cho mọi lớp.** Đối tượng giá trị, record, entity đơn giản và pure function thường nên chạy thật. Tạo một lớp mock cho `String`, DTO hoặc đối tượng chỉ giữ dữ liệu sẽ làm test phức tạp hơn mà ít giá trị.

Một collaborator có thể mang vai trò khác trong bài test khác: `OrderStore` là fake trong `CheckoutServiceTest`, nhưng chính adapter `JdbcOrderStore` phải chạy thật trong `JdbcOrderStoreIT` với PostgreSQL/Testcontainers. Không có mâu thuẫn: hai bài test chứng minh hai loại hành vi.

## 5. Các API Mockito cơ bản

### 5.1 Tạo đối tượng bằng mock() hoặc @Mock

Để tạo test double trực tiếp:

~~~java
Catalog catalog = Mockito.mock(Catalog.class);
~~~

Hoặc dùng JUnit Jupiter extension:

~~~java
@ExtendWith(MockitoExtension.class)
class PriceServiceTest {
    @Mock
    Catalog catalog;

    // ... các @Test method
}
~~~

Đây là **đoạn code minh họa trong dự án có interface `Catalog`**, không phải file test độc lập. `MockitoExtension` khởi tạo và quản lý annotation của Mockito trước khi test chạy, đồng thời giúp phát hiện stubbing không dùng đến theo cấu hình strictness tương ứng.

Các import thường dùng:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
~~~

Đừng nhầm `@Mock` (Mockito tạo mock trong unit test) với annotation thay bean của Spring test context. Một `@Mock` thông thường **không tự ghi đè bean trong ApplicationContext**.

### 5.2 Stub giá trị hoặc lỗi: when/thenReturn, thenThrow

~~~java
when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
when(catalog.unitPriceCents("UNKNOWN"))
        .thenThrow(new IllegalArgumentException("Unknown SKU"));
~~~

Stub chỉ nên mô tả đầu vào thực sự liên quan đến kịch bản. Nếu không stub, Mockito thường trả **default value** (như `0` cho số nguyên, `false` cho boolean, `null` cho nhiều kiểu tham chiếu; có ngoại lệ đối với một số kiểu đặc biệt). Không nên nhầm default value với hành vi production.

Với method `void`, không thể viết `when(...).thenReturn(...)` như với giá trị trả về. Dùng `doThrow(...)`:

~~~java
doThrow(new IllegalStateException("Gateway offline"))
        .when(messageSender).send("hello");
~~~

Trong ví dụ này `messageSender` và method `send(String)` là những thành phần minh họa. Muốn **không làm gì** khi gọi void method, Mockito mock vốn đã mặc định không thực thi implementation thật; `doNothing()` chỉ nên dùng khi làm rõ kịch bản hoặc khi xử lý spy.

### 5.3 Verify tương tác có giá trị nghiệp vụ

~~~java
verify(paymentGateway).charge("ORD-1", 3_000L);
verify(paymentGateway, times(2)).charge("ORD-2", 1_500L);
verify(paymentGateway, never()).charge(anyString(), anyLong());
verifyNoInteractions(emailSender);
~~~

Các lời gọi trên minh họa API; giả định `paymentGateway.charge(String,long)` và `emailSender` được khai báo trong test. `verify(mock).method(...)` mặc định tương đương kiểm **một lần**. `never()` yêu cầu **không có lời gọi phù hợp**; `verifyNoInteractions(...)` kiểm mock hoàn toàn chưa được tương tác.

**Đừng verify mọi getter, setter và trình tự nội bộ.** Nếu kết quả cuối cùng đã thể hiện rõ hợp đồng, dùng `assertEquals`/`assertTrue` là đủ. Verify chỉ nên kiểm những tương tác có ý nghĩa: thu tiền một lần, không gửi email khi thất bại, phát đúng event, gọi API với đúng key.

### 5.4 Argument matchers và captor

Mockito có `anyString()`, `anyLong()`, `eq(value)` và nhiều matcher khác. Nếu một lời gọi dùng matcher cho **một tham số**, các tham số còn lại cũng phải dùng matcher phù hợp (ví dụ `eq("ORD-1")`, không trộn matcher với literal trần cùng lời gọi).

~~~java
verify(paymentGateway).charge(eq("ORD-1"), anyLong());
~~~

Khi đối số phức tạp cần kiểm từng field, dùng `ArgumentCaptor<T>` để thu được đối số đã gửi rồi assert. Với dữ liệu đơn giản như `3_000L`, verify bằng exact argument thường ngắn và rõ hơn.

## 6. Ví dụ Java 17+ tự chứa: stub + fake + mock + spy trong một bài test

Ví dụ này dùng một **`CheckoutService` thật** với các interface nhỏ. Test chỉ phụ thuộc JUnit Jupiter và Mockito, không cần chạy Spring ApplicationContext hay database. Dự án Spring Boot dùng `spring-boot-starter-test` thường đã cung cấp hai thư viện này và Mockito Jupiter extension.

Đặt file **`src/test/java/example/CheckoutServiceTest.java`** như sau:

~~~java
package example;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@DisplayName("CheckoutService: chọn test double theo trách nhiệm")
class CheckoutServiceTest {

    @Mock
    Catalog catalog;                   // Stub dữ liệu giá.

    @Mock
    PaymentGateway payment;            // Mock tương tác thanh toán.

    @Spy
    RecordingAudit audit = new RecordingAudit(); // Gọi logic audit thật.

    FakeOrderStore store;               // Fake lưu trữ bằng Map.
    CheckoutService service;            // SUT thật.

    @BeforeEach
    void setUp() {
        store = new FakeOrderStore();
        service = new CheckoutService(catalog, payment, store, audit);
    }

    @Test
    @DisplayName("Thanh toán đúng tiền và lưu đơn khi hợp lệ")
    void createsOrderWhenPaymentSucceeds() {
        // Arrange: stub đầu vào, stub response của gateway.
        when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
        when(payment.charge("ORD-1", 3_000L)).thenReturn("PAY-9");

        // Act: chạy SUT thật.
        Order result = service.checkout("ORD-1", "BOOK", 2);

        // Assert state/output: trạng thái fake được cập nhật.
        assertAll(
                () -> assertEquals("ORD-1", result.id()),
                () -> assertEquals(3_000L, result.totalCents()),
                () -> assertEquals("PAY-9", result.paymentId()),
                () -> assertEquals(result, store.find("ORD-1")),
                () -> assertEquals(1, store.size()));

        // Assert interaction: lệnh thu tiền phải được phát đúng.
        verify(payment).charge("ORD-1", 3_000L);

        // Spy vẫn chạy implementation thật và ghi được sự kiện.
        verify(audit).record("created:ORD-1");
        assertEquals(List.of("created:ORD-1"), audit.events());
    }

    @Test
    @DisplayName("Đơn trùng ID bị từ chối trước khi tra giá hoặc thu tiền")
    void rejectsDuplicateOrderWithoutCharging() {
        store.save(new Order("ORD-1", "BOOK", 1, 1_500L, "PAY-OLD"));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.checkout("ORD-1", "BOOK", 2));

        assertEquals("duplicate order", error.getMessage());
        assertEquals(1, store.size());
        verifyNoInteractions(catalog, payment);
        verify(audit, never()).record(anyString());
    }

    @Test
    @DisplayName("Số lượng bằng 0 không làm phát sinh I/O")
    void rejectsNonPositiveQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.checkout("ORD-2", "BOOK", 0));

        assertEquals(0, store.size());
        verifyNoInteractions(catalog, payment);
        verify(audit, never()).record(anyString());
    }

    @Test
    @DisplayName("Thanh toán lỗi thì không lưu đơn và không ghi audit")
    void doesNotSaveWhenPaymentFails() {
        when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
        when(payment.charge("ORD-2", 1_500L))
                .thenThrow(new IllegalStateException("declined"));

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.checkout("ORD-2", "BOOK", 1));

        assertEquals("declined", error.getMessage());
        assertFalse(store.exists("ORD-2"));
        assertEquals(0, store.size());
        verify(payment).charge("ORD-2", 1_500L);
        verify(audit, never()).record(anyString());
    }

    @Test
    @DisplayName("doReturn cho spy tránh gọi method thật lúc stub")
    void stubsSpyWithoutExecutingRealMethodDuringSetup() {
        List<String> listSpy = spy(new ArrayList<>(List.of("first")));

        // Nếu dùng when(listSpy.get(9)), get(9) thật sẽ ném lỗi
        // ngay lúc cấu hình stub; doReturn không gọi get(9).
        doReturn("stubbed").when(listSpy).get(9);

        assertEquals("stubbed", listSpy.get(9));
        assertEquals(1, listSpy.size()); // Method size() chạy thật.
        verify(listSpy).get(9);
    }

    interface Catalog {
        long unitPriceCents(String sku);
    }

    interface PaymentGateway {
        String charge(String orderId, long amountCents);
    }

    interface OrderStore {
        boolean exists(String orderId);
        void save(Order order);
        Order find(String orderId);
        int size();
    }

    interface AuditTrail {
        void record(String event);
    }

    record Order(
            String id,
            String sku,
            int quantity,
            long totalCents,
            String paymentId) {
    }

    static final class CheckoutService {
        private final Catalog catalog;
        private final PaymentGateway payment;
        private final OrderStore store;
        private final AuditTrail audit;

        CheckoutService(Catalog catalog, PaymentGateway payment,
                        OrderStore store, AuditTrail audit) {
            this.catalog = catalog;
            this.payment = payment;
            this.store = store;
            this.audit = audit;
        }

        Order checkout(String orderId, String sku, int quantity) {
            if (orderId == null || orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid order");
            }
            if (store.exists(orderId)) {
                throw new IllegalStateException("duplicate order");
            }

            long unitPrice = catalog.unitPriceCents(sku);
            if (unitPrice <= 0) {
                throw new IllegalArgumentException("invalid price");
            }

            long amount = Math.multiplyExact(unitPrice, quantity);
            String paymentId = payment.charge(orderId, amount);

            Order order = new Order(
                    orderId, sku, quantity, amount, paymentId);
            store.save(order);
            audit.record("created:" + orderId);

            return order;
        }
    }

    static final class FakeOrderStore implements OrderStore {
        private final Map<String, Order> orders = new HashMap<>();

        @Override
        public boolean exists(String orderId) {
            return orders.containsKey(orderId);
        }

        @Override
        public void save(Order order) {
            if (orders.putIfAbsent(order.id(), order) != null) {
                throw new IllegalStateException("duplicate order");
            }
        }

        @Override
        public Order find(String orderId) {
            return orders.get(orderId);
        }

        @Override
        public int size() {
            return orders.size();
        }
    }

    static class RecordingAudit implements AuditTrail {
        private final List<String> events = new ArrayList<>();

        @Override
        public void record(String event) {
            events.add(event);
        }

        List<String> events() {
            return List.copyOf(events);
        }
    }
}
~~~

### Phân tích vai trò và bằng chứng của từng test

| Phần | Vai trò | Vì sao chọn | Assertion có ý nghĩa |
| --- | --- | --- | --- |
| `CheckoutService` | **Real component** | Logic checkout là nội dung đang kiểm | Đơn được trả về, giá, trạng thái |
| `catalog` | **Stub** trên Mockito `@Mock` | Test cần đơn giá ổn định, không kiểm catalog | Tổng tiền = số lượng × đơn giá |
| `payment` | **Mock** trên Mockito `@Mock` | Phải biết lệnh thu tiền được/không được gửi | `verify(payment).charge(...)` và `verifyNoInteractions(...)` |
| `store` | **Fake** viết tay | Cần lưu và tìm đơn mà không dùng database | `store.find(...)`, `store.size()` |
| `audit` | **Spy** của implementation thật | Muốn giữ việc lưu sự kiện và quan sát lời gọi | `audit.events()` và `verify(audit).record(...)` |

**Kịch bản thành công:** stub `catalog` trả 1.500 cent, lệnh tính `2 × 1.500 = 3.000 cent` chạy qua service thật; `payment` được stub trả mã `PAY-9` và được verify đúng lời gọi. Fake store giữ bản ghi; spy audit thực sự thêm sự kiện vào list.

**Đơn trùng:** fake đã có `ORD-1` nên service từ chối trước khi hỏi giá/thu tiền. Không tạo stub thừa trong setup; test kiểm cụ thể cả trạng thái và không có các lệnh I/O giả lập.

**Số lượng bằng 0:** validation chạy trước mọi collaborator; test không cần stub nào. Điều này tránh `UnnecessaryStubbingException` khi dùng MockitoExtension với strict stubbing.

**Thanh toán lỗi:** Mockito trả exception theo kịch bản; service không lưu đơn và không ghi audit. Assertion phản ánh hành vi hiện tại của ví dụ, **không khẳng định giao dịch thanh toán bên ngoài đã rollback**.

**Spy trên list:** việc dùng `doReturn("stubbed").when(listSpy).get(9)` không gọi `ArrayList.get(9)` lúc khai báo stub. Nếu dùng `when(listSpy.get(9)).thenReturn("stubbed")`, lời gọi `get(9)` thật xảy ra ngay tại bước stubbing và có thể ném `IndexOutOfBoundsException`.

### Chạy bằng Gradle

Trong module Spring Boot đã có Gradle plugin và dependency management, `build.gradle` thường chứa đoạn cấu hình sau (đây **không phải file build độc lập**):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` của các phiên bản Spring Boot 3.x phù hợp cung cấp JUnit Jupiter và Mockito, bao gồm `mockito-junit-jupiter` để dùng `MockitoExtension`. Với dự án Java thuần không dùng Spring Boot, cần tự khai báo JUnit Jupiter engine và `org.mockito:mockito-junit-jupiter` theo BOM/phiên bản tương thích.

Chạy từ root Gradle chứa module test:

~~~bash
./gradlew test --tests example.CheckoutServiceTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.CheckoutServiceTest
~~~

**Kết quả mong đợi:** JUnit Platform nhận diện **5 phương thức `@Test`** và cả 5 PASS khi project đã cấu hình đúng. Không có stdout do các test tự in; Gradle thông thường kết thúc tác vụ thành công bằng `BUILD SUCCESSFUL`, còn mức chi tiết console phụ thuộc Gradle/IDE. Test này không cần Docker, PostgreSQL hay Spring ApplicationContext.

**Giới hạn mô hình:** mọi class nghiệp vụ được đặt trong file test để ví dụ tự chứa và biên dịch được. Trong dự án thực tế, `CheckoutService`, `Order` và các port phải được **import từ `src/main/java`**; không viết bản sao logic production trong test rồi xem đó là bằng chứng kiểm thử production.

## 7. Spy: vừa thực thi code thật vừa quan sát, nhưng phải thận trọng

Spy thường dùng một đối tượng đã có implementation thật:

~~~java
List<String> spyList = spy(new ArrayList<>());
spyList.add("A");

verify(spyList).add("A");
assertEquals(List.of("A"), spyList);
~~~

Đây là **đoạn minh họa trong lớp test**; `spy`, `verify`, `assertEquals` cần các static import phù hợp và `List`/`ArrayList` cần import `java.util`.

Khác với mock thuần, **spy gọi method thật theo mặc định**. Điều đó hữu ích khi cần giữ hành vi gốc, nhưng có hai rủi ro:

1. **Stubbing với `when(spy.method())` có thể thực thi method thật ngay tại lúc tạo stub.** Nếu method kết nối DB, đọc file hoặc ném lỗi vì tham số chưa hợp lệ, hậu quả xảy ra trước cả lúc SUT được gọi. Khi stub spy, thường chọn cú pháp `doReturn(...).when(spy).method(...)` hoặc `doThrow(...).when(spy).method(...)`.
2. **Spy không phải lúc nào là proxy chuyển tiếp đến instance ban đầu.** Mockito có thể tạo một **bản sao trạng thái** khi spy được tạo; thay đổi vào object gốc sau đó không nhất thiết xuất hiện trong spy và ngược lại. Hãy tương tác với spy trong test; không dựa vào việc hai tham chiếu cùng chia sẻ state.

Nếu mục đích là kiểm đúng output mà không cần quan sát lời gọi, **dùng real object không spy** thường đơn giản hơn. Không spy một service chỉ để verify những private/internal methods; thiết kế test nên dựa vào hợp đồng công khai.

**Spy trên Spring bean** khác spy một POJO: Spring bean có thể có proxy cho transaction, cache, security hoặc các advice khác. Mockito spy một đối tượng bên ngoài Spring không tự kiểm rằng các advice đó hoạt động. Khi cần spy một bean trong Spring test context, dùng cơ chế override/spy bean phù hợp với phiên bản Spring Boot/Framework và hiểu interaction với AOP proxy; đối với test `@Transactional` quan trọng, ưu tiên assertions trên transaction và dữ liệu thực.

## 8. @Mock, @Spy, @InjectMocks và việc quản lý vòng đời test

Mockito có thể cấp các thành phần qua annotation khi có `MockitoExtension`:

- `@Mock`: tạo mock cho interface/class.
- `@Spy`: bọc một implementation thật để giữ phần lớn hành vi và ghi nhận tương tác.
- `@Captor`: tạo `ArgumentCaptor<T>` để bắt và kiểm đối số phức tạp.
- `@InjectMocks`: cố gắng tạo SUT (nếu cần) và inject những mock/spy hiện có qua constructor, setter hoặc field theo khả năng; nó **không khởi động Spring** và không thay thế cơ chế dependency injection thực sự của Spring Boot.

Ví dụ ý tưởng:

~~~java
@ExtendWith(MockitoExtension.class)
class PriceServiceTest {
    @Mock
    PriceProvider provider;

    @InjectMocks
    PriceService service;

    // @Test dùng service thật, provider được thay bằng mock.
}
~~~

Đoạn trên **chỉ minh họa cách khai báo annotation**, chưa đủ để biên dịch một mình vì `PriceProvider`/`PriceService` là class của ứng dụng. Với constructor rõ ràng, việc tạo SUT **thủ công** như trong `CheckoutServiceTest` thường dễ đọc hơn và giúp nhận ra thiếu dependency ngay lập tức.

Đừng lạm dụng `@InjectMocks` cho graph lớn và suy diễn rằng “vì test pass nên Spring sẽ inject bean giống vậy”. Integration test Spring Boot mới kiểm được configuration, bean selection, qualifier, profile và AOP thật.

Trong JUnit Jupiter, `@ExtendWith(MockitoExtension.class)` thường là cách chuẩn để dùng Mockito annotations trong unit test. Nếu không dùng extension, bạn có thể gọi `mock(...)`/`spy(...)` trực tiếp; khi muốn khởi tạo `@Mock` thủ công, phải quản lý lifecycle qua `MockitoAnnotations.openMocks(...)` và đóng tài nguyên khi phù hợp. Tránh trộn nhiều cơ chế lifecycle mà không có lý do.

## 9. Cách viết assertion về trạng thái và tương tác

### Khi nào dùng verify?

Ví dụ yêu cầu “hệ thống phải gửi đúng một yêu cầu thanh toán”:

~~~java
verify(payment).charge("ORD-1", 3_000L);
~~~

Nếu chỉ assert đơn đã được lưu vào fake, bài test **có thể bỏ sót** một triển khai gọi gateway hai lần. Vì charge là side effect ngoài hệ thống, verify một lần là tín hiệu quan trọng.

Ví dụ yêu cầu “đơn phải được lưu đúng tổng tiền”:

~~~java
assertEquals(3_000L, store.find("ORD-1").totalCents());
~~~

Trong trường hợp này, `verify(store).save(...)` không cần thiết nếu fake đã cho phép quan sát dữ liệu cuối. Dùng cả hai bừa bãi sẽ khiến test phụ thuộc chi tiết quá trình lưu.

### ArgumentCaptor khi payload phức tạp

Giả sử method nhận một `PaymentRequest` gồm nhiều field, bạn có thể bắt đối số:

~~~java
ArgumentCaptor<PaymentRequest> captor =
        ArgumentCaptor.forClass(PaymentRequest.class);

verify(paymentPort).charge(captor.capture());

assertEquals("ORD-1", captor.getValue().orderId());
assertEquals(3_000L, captor.getValue().amountCents());
~~~

Đoạn này **minh họa** API khi port có chữ ký `charge(PaymentRequest)`, **khác** port `charge(String,long)` trong ví dụ đầy đủ. Trong Java thật phải dùng đúng chữ ký của interface. Nếu đối số là record có `equals` đúng, verify trực tiếp bằng record có thể rõ ràng hơn captor.

### Kiểm thứ tự bằng InOrder khi hợp đồng thật sự yêu cầu

Ví dụ nghiệp vụ yêu cầu không ghi audit trước khi thanh toán thành công, bạn có thể dùng `InOrder` để kiểm tương tác giữa hai mock/spy. Nhưng thứ tự giữa các getter, mapper hoặc helper nội bộ **không nên là hợp đồng test**. Khi đổi thứ tự thao tác mà kết quả và invariant vẫn giữ nguyên, test nên tiếp tục PASS.

`verifyNoMoreInteractions(...)` có thể làm test quá giòn: một log vô hại hoặc một lời gọi thêm có thể khiến test fail. Chỉ dùng khi hợp đồng thực sự cấm mọi tương tác bổ sung, chẳng hạn phải bảo đảm không có lệnh I/O thứ hai.

## 10. Strict stubbing, default answers và chất lượng test

Với Mockito JUnit Jupiter extension, strict stubbing giúp phát hiện kịch bản thiết lập stub nhưng **không dùng** hoặc dùng tham số không khớp, ví dụ:

~~~java
when(catalog.unitPriceCents("BOOK")).thenReturn(1_500L);
// Test chỉ kiểm quantity = 0 và kết thúc trước khi hỏi catalog.
~~~

Nếu test không bao giờ gọi `catalog.unitPriceCents("BOOK")`, Mockito có thể báo `UnnecessaryStubbingException` lúc kết thúc. Đây thường là dấu hiệu **Arrange thừa**: một bài test đang chuẩn bị dữ liệu cho đường đi không xảy ra.

Cách sửa tốt:

- Đặt stubbing **ngay trong từng test** cần nó, như ví dụ ở mục 6.
- Nếu nhiều test thật sự dùng cùng stub, có thể gom vào setup, nhưng tránh setup toàn bộ “happy path” cho cả bài test lỗi.
- Chỉ dùng `lenient()` hoặc nới strictness khi có lý do rõ, không để che mọi unused stub.
- Không gọi `reset(mock)` liên tục giữa các bước chỉ để dùng lại một mock chung; thông thường tạo fixture mới cho mỗi test dễ quản lý hơn.

### Default answers không đại diện cho production

Một Mockito mock không được stub vẫn có thể “đáp” giá trị mặc định. Nếu `payment.charge(...)` trả `null`, không có nghĩa gateway thật sẽ trả null. Test nên rõ ràng về trường hợp nào được phép trả null, trường hợp nào cần stub response, exception hay network failure.

Mục đích của Mockito là **kiểm soát sự phụ thuộc ở một ranh giới đã chọn**, không phải mô phỏng đầy đủ service thật.

## 11. Mockito trong Spring Boot: unit test khác Spring context test

### Unit test: @Mock cùng constructor, không cần ApplicationContext

Với business service thuần Java, dùng `MockitoExtension` và tạo SUT bằng constructor. Đây thường là cách nhanh và rõ nhất để kiểm nhánh nghiệp vụ.

### Spring slice/integration test: thay bean trong ApplicationContext

Khi test controller bằng `@WebMvcTest` hoặc khởi động context bằng `@SpringBootTest`, một field `@Mock` thông thường không tự ghi đè bean đang được Spring inject. Cần dùng API override của Spring test phù hợp phiên bản:

- **Spring Boot 3.3 trở về trước**: thường dùng `org.springframework.boot.test.mock.mockito.MockBean` hoặc `SpyBean`.
- **Spring Boot 3.4 / Spring Framework 6.2 trở lên**: có `org.springframework.test.context.bean.override.mockito.MockitoBean` và `MockitoSpyBean`; các annotation cũ của Spring Boot được đánh dấu deprecated trong 3.4. Kiểm phiên bản dependency/import thực tế trước khi thay đổi.
- Với dự án nâng version, không sao chép annotation của release khác mà chưa đối chiếu API và hành vi bean override.

Ví dụ cú pháp trong Spring Framework hỗ trợ `@MockitoBean` (không phải file độc lập, vì cần controller/service thực tế):

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @MockitoBean
    OrderService orderService;

    // @Test với MockMvc để kiểm status, JSON và MVC mapping.
}
~~~

Spring test này kiểm web slice và wiring trong context, không chỉ unit logic của `OrderService`. Không thay `OrderController` bằng mock rồi kết luận HTTP mapping hoạt động: phải giữ phần MVC cần kiểm thật.

Tương tự, khi kiểm `@Transactional`, JPA mapping hoặc Spring Security method advice, hãy giữ thành phần framework/bean liên quan chạy thật; tránh mock làm mất cơ chế đang cần chứng minh. Test dùng repository mock không thể xác nhận SQL hay transaction rollback.

## 12. Fake phải được kiểm soát như một contract giản lược

Một fake repository bằng `Map` thường dễ viết, nhưng cần nêu rõ **những hành vi nó bảo đảm**:

- `save` rồi `find` trả dữ liệu theo ID.
- Kiểm tra điều kiện duplicate ID nếu unit test cần quy tắc đó.
- Trạng thái là độc lập giữa các test, khởi tạo mới ở `@BeforeEach`.
- Không bảo đảm locking, concurrent update, transaction rollback hay SQL constraint.

Nếu fake có hành vi sai so với adapter thật, unit test sẽ đưa ra bằng chứng sai. Khi cần, viết **cùng một tập contract test** chạy với fake và adapter thật để đảm bảo phần hợp đồng chung; với tính năng database đặc thù, bổ sung integration test riêng.

**Không mở rộng fake thành một DB tự chế.** Khi fake bắt đầu mô phỏng query optimizer, race condition, transaction isolation, pagination phức tạp…, dùng database thật trong Testcontainers sẽ phù hợp và ít rủi ro hơn.

Ví dụ lựa chọn theo loại lỗi:

| Lỗi muốn phát hiện | Lựa chọn phù hợp |
| --- | --- |
| Sai phép tính hoặc thiếu validation trong service | Service thật + stub/fake/mock tại biên |
| Không gửi email khi yêu cầu thất bại | Mock email port, `verifyNoInteractions` |
| Đơn đã được ghi vào repository port với dữ liệu đúng | Fake store + assert state |
| JPQL/native SQL sai, entity mapping thiếu cột | Repository thật + DB container |
| HTTP client tạo sai header/JSON | HTTP stub server/contract test qua transport thật |
| Redis TTL, Kafka ack/offset | Adapter thật + Redis/Kafka thích hợp |
| Transaction Spring không rollback | Spring context và DB thật, assert trạng thái sau transaction |

Fake và mock giúp cô lập **logic**; chúng không thay thế toàn bộ bằng chứng từ **protocol và hạ tầng thật**.

## 13. Những lỗi phổ biến khi dùng Mockito

### 13.1 Mock chính SUT

Sai mục tiêu: `CheckoutService service = mock(CheckoutService.class)` rồi stub `checkout(...)` trả một `Order` và assert kết quả đó. Test chỉ chứng minh Mockito trả đúng giá trị ta đã khai báo, **không kiểm logic checkout**.

Giải pháp: tạo `CheckoutService` thật, chỉ thay các collaborator tại ranh giới cần thiết.

### 13.2 Over-mocking mọi lớp

Mock controller, service, mapper, entity, record, repository khiến bài test mô phỏng chính nội bộ implementation và khó refactor. Ưu tiên dữ liệu thật cho value objects và pure functions; mock I/O hoặc side effect quan trọng.

### 13.3 Stubbing thừa hoặc quá rộng

`when(provider.anything()).thenReturn(...)` với `any()` quá rộng có thể che việc SUT truyền sai SKU/key. Stub đúng đầu vào cần thiết và để strict stubbing phát hiện lệch đối số. Nếu response có ý nghĩa với nhiều input, thể hiện hợp đồng đó rõ ràng.

### 13.4 Lạm dụng verifyNoMoreInteractions và InOrder

Những assertion này ràng buộc test với mọi bước nội bộ, khiến refactor hợp lệ phá test. Chỉ dùng khi **không có lời gọi dư** hoặc **thứ tự** thực sự là yêu cầu nghiệp vụ.

### 13.5 Spy thực thi I/O thật ngoài ý muốn

`when(spyClient.fetch()).thenReturn(data)` có thể gọi HTTP thật ngay lúc thiết lập. Dùng `doReturn(...)` cho spy và suy nghĩ lại xem spy có thật sự cần thiết hay chỉ mock interface I/O.

### 13.6 Spy object gốc rồi tiếp tục mutate object gốc

Đối tượng spy không nên được giả định đồng bộ mọi thay đổi với object đầu vào vì Mockito có thể sao chép state khi tạo. Tương tác qua tham chiếu spy, tự quản lý các tài nguyên được chia sẻ nếu có.

### 13.7 Dùng Mockito như framework giả lập database

Mockito không tái hiện transaction, constraint, SQL hoặc query planner. Unit test service với mock repository có thể rất tốt, nhưng repository riêng vẫn cần kiểm thực nếu rủi ro nằm ở persistence.

### 13.8 Trộn @Mock với Spring bean override

Một field `@Mock` trong `@SpringBootTest` không tự động đổi bean mà controller/service lấy từ ApplicationContext. Chọn đúng `@MockBean`/`@MockitoBean` theo phiên bản khi thật sự cần Spring test.

### 13.9 Dựa vào chi tiết nội bộ thay vì kết quả

Verify private-like helper, mọi mapping method hoặc số lần gọi getter làm test kém bền vững. Test nên đọc được như một hợp đồng: “không thu tiền khi hết hàng”, “lưu đúng đơn khi thành công”.

### 13.10 Bỏ qua checked exception và kiểu trả về

Không thể `thenReturn(...)` một giá trị khác kiểu khai báo của method. Mockito cũng có quy tắc với checked exception: không thể tùy ý stub một checked exception mà method không khai báo phù hợp. Hãy mô hình hợp đồng port rõ ràng để test phản ánh những trạng thái lỗi production có thể xảy ra.

### 13.11 Dùng chung mock giữa các test

Mock lưu lịch sử tương tác; dùng static singleton mock hoặc `reset` liên tục dễ tạo test phụ thuộc thứ tự. JUnit Jupiter + MockitoExtension tạo mock cho lifecycle từng test là lựa chọn mặc định tốt.

### 13.12 Quên kiểm việc hủy hoặc hoàn tác side effect

`verify(payment).charge(...)` chỉ chứng minh đã gửi lệnh tới port; nó không chứng minh cổng thanh toán bên ngoài thành công, idempotent hay rollback. Khi nghiệp vụ quan trọng, bổ sung integration/contract test và thiết kế transaction/compensation tương ứng.

## 14. Cách xây một test có giá trị với Mockito

Một quy trình dễ áp dụng:

1. **Đặt tên hành vi:** ví dụ “Không gửi lệnh thu tiền khi số lượng không hợp lệ”.
2. **Chọn SUT chạy thật:** `CheckoutService`.
3. **Phân loại collaborator:** dữ liệu → stub; state → fake; external command → mock; real behavior cần quan sát → spy nếu cần.
4. **Arrange tối thiểu:** chỉ stub dữ liệu test thực sự dùng; tạo state fake bằng các phương thức của hợp đồng.
5. **Act một lần:** gọi public API của SUT; đừng gọi private/internal helpers.
6. **Assert kết quả:** trả về, state, exception; bổ sung `verify` cho các tương tác quan trọng.
7. **Xem xét rủi ro chưa được kiểm:** query thật, transaction, serialization, HTTP status, broker… để đặt integration test ở lớp phù hợp.
8. **Kiểm tính lặp lại:** mỗi test có fixture độc lập, tránh giờ thật/ngẫu nhiên/network không kiểm soát, không lệ thuộc thứ tự.

Ví dụ đặc biệt quan trọng: khi ghi event là tác dụng chính của một use case, **mock publisher** và `verify(publish(event))` là cần thiết. Nhưng khi service trả về kết quả đã quan sát được, thường chỉ cần **assert output**. Test tốt lựa chọn tương tác **có chủ đích**, không verify mặc định mọi dependency.

## 15. Checklist trước khi chốt bài kiểm thử

- [ ] SUT là implementation thật đang cần kiểm, không bị mock.
- [ ] Stub trả đầu vào/lỗi cố định có lý do; không giả định default response của mock giống production.
- [ ] Fake có state và hợp đồng nhỏ, được khởi tạo độc lập theo test.
- [ ] Mock verify chỉ các tương tác có ý nghĩa nghiệp vụ, nhất là side effect đi ra ngoài.
- [ ] Spy được dùng có chủ đích; hiểu method thật chạy mặc định và cân nhắc `doReturn`/`doThrow` khi stub.
- [ ] `@Mock`/`@Spy` có `MockitoExtension` hoặc cơ chế khởi tạo/đóng phù hợp.
- [ ] Không trộn annotation Mockito unit test với Spring bean override theo cách khiến SUT chạy ở context khác dự kiến.
- [ ] Đối với dữ liệu công khai, ưu tiên `assertEquals`/assertion state trước khi thêm các verify nội bộ.
- [ ] Không lạm dụng `lenient`, `reset`, `verifyNoMoreInteractions` hoặc `InOrder`.
- [ ] Test kiểm nhiều trường hợp: thành công, input không hợp lệ, collaborator lỗi và **không phát side effect** khi bị từ chối.
- [ ] SQL/schema/transaction/HTTP wire protocol cần integration/contract test tương ứng; fake/mock không tự chứng minh chúng.
- [ ] Test Java 17+ chạy qua JUnit Platform, không yêu cầu network/DB khi chỉ kiểm unit logic.

**Tóm tắt khái niệm:** *stub* cho dữ liệu đã lập trình; *fake* cho hành vi/trạng thái giản lược; *mock* để kiểm tương tác; *spy* để quan sát object thật (và có thể stub chọn lọc). Mockito có thể hiện thực nhiều vai trò khác nhau, còn mục tiêu và assertions mới quyết định lựa chọn test double. Luôn giữ logic cần kiểm chạy thật và bổ sung integration test ở nơi hành vi thực tế của hạ tầng quyết định tính đúng.

### Tài liệu tham khảo

- Martin Fowler, [Test Double](https://martinfowler.com/bliki/TestDouble.html): thuật ngữ dummy, stub, fake, mock, spy và phân biệt state/behavior verification.
- [Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): `mock`, `spy`, stubbing, verification và lưu ý thực thi method thật trên spy.
- [Mockito JUnit Jupiter extension](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org.mockito.junit.jupiter/org/mockito/junit/jupiter/MockitoExtension.html): quản lý `@Mock`/strict stubbing trong JUnit 5.
- [Spring Framework Testing – Bean Override with Mockito](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): `@MockitoBean`, `@MockitoSpyBean` và Spring test context.
- [Spring Boot Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): các kiểu unit/slice/integration test và Spring Boot starter test.
