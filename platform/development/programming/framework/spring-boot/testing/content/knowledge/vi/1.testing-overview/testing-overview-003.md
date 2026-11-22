# Đơn vị được kiểm thử và các ranh giới phụ thuộc

Trong Spring Boot, muốn viết bài kiểm thử hữu ích trước hết phải trả lời hai câu hỏi: **hành vi nào thuộc trách nhiệm của đối tượng đang kiểm thử?** và **đến đâu thì việc thực thi được giao cho thành phần khác?** Câu trả lời xác định *System Under Test* (SUT, đối tượng/đơn vị được kiểm thử), ranh giới phụ thuộc, loại test thích hợp và những gì cần quan sát để kết luận đúng/sai.

## 1. Hiểu đúng “đơn vị” được kiểm thử

**Đơn vị được kiểm thử** là phần hành vi mà một bài test muốn chứng minh. Nó có thể là một hàm thuần, một lớp, một service hoặc một nhóm nhỏ đối tượng phối hợp để thực hiện cùng một trách nhiệm. “Unit” không mặc định đồng nghĩa với “một phương thức” hay “một bean”. Hãy chọn ranh giới sao cho hành vi cần chứng minh rõ ràng, các điều kiện đầu vào kiểm soát được và kết quả có thể kiểm chứng.

Ví dụ trong luồng đặt hàng:

1. `OrderController` nhận HTTP request và chuyển dữ liệu cho ứng dụng.
2. `OrderService` quyết định số lượng hợp lệ, kiểm tra tồn kho và yêu cầu lưu đơn.
3. `StockGateway` truy vấn nguồn thông tin tồn kho.
4. `OrderRepository` ghi đơn hàng xuống cơ sở dữ liệu.

Nếu mục tiêu là **“khi không đủ hàng, không lưu đơn”**, SUT phù hợp là `OrderService`. Kết quả quan sát gồm ngoại lệ/ngữ nghĩa trả về và việc *không gọi* lưu đơn. Database, HTTP server và hệ thống kho không cần chạy trong bài unit test này.

Nếu mục tiêu đổi thành **“HTTP trả 400 khi JSON thiếu trường bắt buộc”**, SUT đã dịch chuyển sang ranh giới Spring MVC, nơi `@RequestBody`, `@Valid`, exception handler và cấu hình web tham gia. Khi ấy gọi trực tiếp một phương thức controller chưa đủ; nên dùng kiểm thử web slice hoặc tích hợp.

Nếu mục tiêu là **“repository ánh xạ entity và truy vấn đúng dữ liệu”**, cần dùng JPA/JDBC thật với database thử nghiệm. Mock repository sẽ loại bỏ chính hành vi muốn kiểm tra.

Phân biệt ba khái niệm:

- **SUT:** thành phần/hành vi đang được kiểm chứng.
- **Collaborator (thành phần cộng tác):** thứ SUT gọi để hoàn thành công việc, như port lưu trữ, client HTTP, `Clock` hoặc bộ tính giá.
- **Boundary (ranh giới):** điểm mà bài test quyết định dùng thành phần thật, thay bằng test double, hoặc chuyển sang một cấp kiểm thử khác.

## 2. Vẽ ranh giới từ hành vi, không từ sơ đồ lớp

Với mỗi trường hợp, viết một câu theo mẫu: **“Khi [điều kiện], SUT phải [kết quả quan sát được], bất kể [chi tiết ngoài trách nhiệm]”.** Sau đó liệt kê mọi lời gọi đi ra ngoài SUT.

| Thành phần | Điều cần kiểm tra | Ranh giới hợp lý |
| --- | --- | --- |
| Hàm tính phí/định giá thuần | Kết quả cho đầu vào cụ thể | Dùng logic thật; không cần Spring context |
| Service xử lý nghiệp vụ | Nhánh quyết định, kết quả, tác động mong đợi lên port | Tạo service thật; thay I/O bên ngoài bằng stub/mock/fake |
| Controller và HTTP binding | Status, JSON, validation, route, exception mapping | `@WebMvcTest` + `MockMvc`, cấu hình đúng các bean cần thiết |
| Repository JPA | Query, mapping, constraint, transaction với persistence | `@DataJpaTest` và database kiểm thử phù hợp |
| Luồng qua nhiều bean, security filter, transaction hoặc messaging | Các thành phần tích hợp vận hành cùng nhau | `@SpringBootTest` hoặc test tích hợp có hạ tầng thực thích hợp |

Đây là lựa chọn **theo câu hỏi kiểm thử**, không phải xếp hạng test nào “tốt hơn”. Một service có thể cần cả unit test cho quy tắc nghiệp vụ và integration test cho transaction/SQL.

Ranh giới tốt có bốn đặc điểm:

- **Có thể điều khiển đầu vào:** ép được các nhánh hết hàng, lỗi mạng, timeout, dữ liệu không hợp lệ.
- **Quan sát được hành vi:** kiểm tra giá trị, ngoại lệ, trạng thái hay lệnh gửi đến port; không phụ thuộc biến cục bộ bên trong.
- **Độc lập với môi trường ngoài khi không cần thiết:** unit test không vô tình gọi mạng, DB, broker hoặc đồng hồ hệ thống thật.
- **Đủ thực để chứng minh yêu cầu:** không mock đi phần logic mà bài test định xác minh.

## 3. Phân loại phụ thuộc: giữ thật hay thay thế?

Không phải phụ thuộc nào cũng nên mock. Quyết định dựa vào **vai trò của nó trong hành vi cần kiểm tra**:

| Phụ thuộc | Cách xử lý trong unit test | Khi nào cần kiểm tra với bản thật? |
| --- | --- | --- |
| Value object, `record`, hàm thuần, bộ tính toán xác định | Giữ thật để kiểm tra cả logic và dữ liệu liên quan | Thường có thể kiểm tra độc lập |
| Repository/DAO gọi SQL hoặc JPA | Dùng interface port và mock/fake để SUT phản ứng với kết quả cụ thể | Test riêng query, mapping, constraint và transaction |
| HTTP client gọi dịch vụ ngoài | Stub kết quả thành công, lỗi nghiệp vụ, timeout qua port/client | Test HTTP serialization, authentication, retry và contract ở ranh giới HTTP |
| Đồng hồ, random, UUID | Tiêm `Clock`/nguồn sinh giá trị có thể điều khiển | Kiểm tra wiring/cấu hình thực khi cần |
| Queue, file, cache, email | Mock/fake tại cổng tác động bên ngoài | Test tích hợp khi cần chứng minh định dạng, delivery, TTL hoặc độ bền |
| Spring proxy, `@Transactional`, `@Cacheable`, method security | Unit test logic nội tại của method | Test có Spring context để xác minh interceptor/AOP thực sự chạy |

Ví dụ: với quy tắc “đơn hàng hợp lệ được lưu”, mock `OrderStore` giúp biết service *đã yêu cầu* lưu đúng dữ liệu. Nó **không chứng minh** database đã commit, unique constraint được thực thi hay bản ghi còn sau restart. Những khẳng định ấy cần integration test.

### Test double có những loại nào?

- **Stub:** trả dữ liệu/ngoại lệ đã sắp đặt để đưa SUT vào nhánh cần test, như tồn kho = `false`.
- **Fake:** một bản thay thế hoạt động đơn giản, ví dụ repository lưu trong `Map`; hữu ích khi nhiều thao tác cần trạng thái nhưng không xác minh chính xác hành vi DB thật.
- **Mock:** cộng tác viên cho phép kiểm tra lời gọi, tham số, số lần gọi hoặc việc không gọi.
- **Spy:** bọc một đối tượng thật và có thể thay một phần hành vi; dùng thận trọng vì side effect của phương thức thật vẫn có thể xảy ra.

Mockito hỗ trợ tạo mock và stubbing/verification; tên “mock” trong thư viện không làm mọi cách sử dụng đều là verification. Dùng `when(...).thenReturn(...)` chủ yếu để điều khiển dữ liệu đầu vào; dùng `verify(...)` khi lời gọi là một phần của yêu cầu. Tránh kiểm đếm mọi lời gọi nội bộ vì test sẽ vỡ khi refactor dù hành vi bên ngoài không đổi.

## 4. Thiết kế ranh giới rõ ràng trong Spring Boot

Constructor injection làm phụ thuộc hiển thị trực tiếp, dễ thay thế và tránh phải tạo Spring context cho unit test:

```text
JUnit/Mockito
    |
    v
OrderService (SUT thật)
    |-- StockGateway (mock: quyết định trả lời tồn kho)
    \-- OrderStore   (mock: quan sát lệnh lưu)
```

`StockGateway` và `OrderStore` là **outbound ports**: giao diện mô tả thứ service cần từ thế giới bên ngoài. Trong ứng dụng thật, adapter có thể kết nối đến REST API, Kafka, Redis hoặc Spring Data; trong unit test, ta cung cấp test double. Đây là kỹ thuật tạo ranh giới rõ ràng, không có nghĩa mọi lớp đều cần thêm interface.

**Tình huống:** Khi số lượng hợp lệ và còn hàng, service tạo đơn và yêu cầu lưu. Khi hết hàng, service báo lỗi và tuyệt đối không lưu. Khi số lượng không hợp lệ, service từ chối ngay, chưa gọi bất kỳ cổng phụ thuộc nào.

Tạo tệp `src/main/java/demo/order/OrderService.java` (Java 17 trở lên):

```java
package demo.order;

import java.util.Objects;

public class OrderService {
    private final StockGateway stock;
    private final OrderStore orders;

    public OrderService(StockGateway stock, OrderStore orders) {
        this.stock = Objects.requireNonNull(stock);
        this.orders = Objects.requireNonNull(orders);
    }

    public Order place(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (!stock.isAvailable(sku, quantity)) {
            throw new OutOfStockException(sku);
        }

        Order order = new Order(sku, quantity);
        orders.save(order);
        return order;
    }
}

interface StockGateway {
    boolean isAvailable(String sku, int quantity);
}

interface OrderStore {
    void save(Order order);
}

record Order(String sku, int quantity) {}

class OutOfStockException extends RuntimeException {
    OutOfStockException(String sku) {
        super("Out of stock: " + sku);
    }
}
```

Các interface và `record` ở cùng tệp có phạm vi package để ví dụ gọn và Java vẫn biên dịch hợp lệ. Khi xây dựng module lớn, có thể tách chúng thành tệp/package phù hợp. Đoạn code là **logic nghiệp vụ độc lập với Spring annotations**; dự án Spring Boot có thể khai báo `OrderService` thành bean qua `@Service` hoặc `@Bean` trong cấu hình thực. Unit test dưới đây tạo instance bằng constructor.

Tạo tệp `src/test/java/demo/order/OrderServiceTest.java`:

```java
package demo.order;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {
    @Mock StockGateway stock;
    @Mock OrderStore orders;

    private OrderService sut;

    @BeforeEach
    void setUp() {
        sut = new OrderService(stock, orders);
    }

    @Test
    void conHang_taoVaYeuCauLuuDungDon() {
        when(stock.isAvailable("BOOK-1", 2)).thenReturn(true);

        Order actual = sut.place("BOOK-1", 2);

        assertEquals(new Order("BOOK-1", 2), actual);
        ArgumentCaptor<Order> saved = ArgumentCaptor.forClass(Order.class);
        verify(orders).save(saved.capture());
        assertEquals(actual, saved.getValue());
    }

    @Test
    void hetHang_baoLoiVaKhongLuu() {
        when(stock.isAvailable("BOOK-1", 2)).thenReturn(false);

        OutOfStockException error = assertThrows(
                OutOfStockException.class,
                () -> sut.place("BOOK-1", 2));

        assertEquals("Out of stock: BOOK-1", error.getMessage());
        verifyNoInteractions(orders);
    }

    @Test
    void soLuongKhongHopLe_khongChamPhuThuoc() {
        assertThrows(IllegalArgumentException.class,
                () -> sut.place("BOOK-1", 0));

        verifyNoInteractions(stock, orders);
    }
}
```

Trong một project Gradle Spring Boot đã cấu hình quản lý phiên bản dependencies, các test này dùng JUnit Jupiter và Mockito từ `spring-boot-starter-test`. Nếu chưa có dependency/cấu hình chạy JUnit Platform, phần cần thiết trong `build.gradle` (Groovy DSL) có dạng:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy từ thư mục project Gradle phù hợp:

```bash
./gradlew test --tests demo.order.OrderServiceTest
```

Trên Windows có thể dùng `.\gradlew.bat test --tests demo.order.OrderServiceTest`. Nếu test task thuộc một subproject, chọn đúng task/subproject khi chạy. **Kỳ vọng:** cả ba test pass nếu project có cấu hình build và dependencies tương ứng; không có stdout cố định vì JUnit/Gradle hiển thị kết quả theo cấu hình chạy.

Ý nghĩa từng test:

1. **Còn hàng:** stub phản hồi từ hệ thống kho, sau đó kiểm tra đơn trả về và *lệnh lưu* mang đúng dữ liệu. `ArgumentCaptor` quan sát outbound command, không xác minh database thật.
2. **Hết hàng:** quan sát ngoại lệ và đảm bảo không chạm repository, nhờ vậy lỗi kho không tạo đơn sai.
3. **Đầu vào sai:** xác nhận thứ tự kiểm tra: service từ chối trước khi hỏi kho hoặc lưu trữ.

Không có `@SpringBootTest`, `@Autowired`, server, datasource hay kết nối mạng trong những test này. Đó là dụng ý của ranh giới unit test. Khi đổi implementation của `StockGateway` từ REST sang gRPC, ba test vẫn phản ánh cùng hợp đồng nghiệp vụ.

## 5. Ranh giới của test nằm ở đâu trong Spring Boot?

### 5.1. Controller: gọi method trực tiếp chưa đủ để test HTTP

Gọi `new OrderController(service).create(dto)` chỉ kiểm tra Java method. Cách đó không kích hoạt đầy đủ việc parse JSON, chọn route, binding, `@Valid`, mapping ngoại lệ hoặc filter chain của Spring MVC. Với yêu cầu HTTP, chọn `@WebMvcTest(YourController.class)` cùng `MockMvc` và khai báo/mock những cộng tác viên cần cho context. Test gửi request qua MVC infrastructure rồi assert status, response body, header và validation thực tế. Cấu hình security/filter cần được đưa vào phạm vi theo mục tiêu kiểm thử.

### 5.2. Service: method thật khác với proxy Spring thật

Một unit test khởi tạo service bằng `new` có thể kiểm chứng tốt điều kiện nghiệp vụ, nhưng **không chạy interceptor Spring**. Ví dụ gọi method gắn `@Transactional` trực tiếp không chứng minh commit/rollback, propagation hoặc transaction boundary; `@Cacheable` không chứng minh caching; kiểm tra method security cũng cần cơ chế bảo mật thực. Hãy bổ sung test có Spring context và các adapter thực khi tính năng framework là điều cần chứng minh.

### 5.3. Repository: mock không chứng minh SQL/JPA

Mock `JpaRepository` phù hợp để ép service nhận `Optional.empty()` hoặc một entity xác định. Nó không chạy generated query, entity mapping, lazy loading, constraint hay migration. Dùng `@DataJpaTest` cho persistence slice. Nếu query phụ thuộc tính năng PostgreSQL/MySQL, một in-memory database khác dialect chưa phải bằng chứng đáng tin; hãy dùng đúng loại database thử nghiệm (ví dụ qua Testcontainers khi phù hợp).

### 5.4. Giao tiếp ra ngoài: tách quyết định khỏi giao thức

Unit test của service nên giả lập kết quả ở port “gọi thanh toán thành công / thất bại”. Riêng HTTP client adapter cần test request URL, method, header, payload, status/error mapping với mock server hoặc môi trường tích hợp. Với messaging, kiểm tra ở service rằng event đúng được yêu cầu publish; dùng test tích hợp để chứng minh serialization, broker delivery, retry hoặc consumer behavior.

## 6. Chọn ranh giới qua bảng tình huống

| Câu hỏi cần chứng minh | SUT và test nên chọn | Điều *chưa* được chứng minh |
| --- | --- | --- |
| Giỏ hàng trống thì không tạo đơn | Service thật + mock store | Transaction/DB schema |
| Giảm giá theo điều kiện hội viên | Bộ tính giá thật + dữ liệu thử | HTTP/API wiring |
| `POST /orders` thiếu field trả HTTP 400 | Spring MVC slice + request thật qua `MockMvc` | DB commit |
| `@Transactional` rollback khi lỗi sau insert | Spring context + database test | Hành vi dịch vụ từ xa nếu đã fake |
| JPA query tìm đúng đơn theo trạng thái | Repository slice + DB test | Toàn bộ HTTP/security pipeline |
| Timeout của payment client được map đúng | Client adapter + simulated HTTP timeout | Service bên ngoài thật hoạt động |
| Role không đủ quyền bị chặn trước nghiệp vụ | Security/MVC integration test | Hệ thống identity provider thật nếu đã stub |

**Nguyên tắc kiểm chứng:** hãy đặt assertion ngay tại ranh giới đang kiểm tra. Đừng lấy việc `verify(repository).save(...)` làm bằng chứng “đã lưu DB”, và đừng lấy việc gọi controller method trực tiếp làm bằng chứng “endpoint trả HTTP 201”.

## 7. Thiết kế test dễ bảo trì

Một bài test đủ sắc nét thường có ba pha:

1. **Given:** dựng SUT thật và chuẩn bị input; chỉ stub những phản hồi cần thiết cho tình huống.
2. **When:** gọi một hành vi công khai ở ranh giới cần kiểm tra.
3. **Then:** assert giá trị/trạng thái hoặc ngoại lệ; `verify` các tương tác có ý nghĩa nghiệp vụ (ví dụ không được gửi lệnh thu tiền hai lần).

Chọn dữ liệu có ý nghĩa: số lượng `0` để test validation, tồn kho `false` để test hết hàng, lỗi timeout riêng với lỗi nghiệp vụ. Mỗi ca cần diễn tả rõ điều kiện, không chỉ đổi tên test.

Ưu tiên kiểm tra kết quả và giao kèo với collaborator, không kiểm tra chi tiết cách code chia thành các helper method. `verifyNoMoreInteractions(...)` chỉ nên dùng khi **không phát sinh thêm hành động** là yêu cầu thật; áp dụng cứng nhắc sẽ làm test dễ vỡ khi triển khai thêm logging/metrics.

Với thời gian, thay `Instant.now()` bằng `Clock` được inject và `Clock.fixed(...)` trong test để kiểm tra các mốc sát ngày hết hạn. Với UUID/random, inject nguồn tạo giá trị hoặc cố định đầu vào. Với xử lý bất đồng bộ, cần đồng bộ bằng kết quả/event có thể quan sát thay vì dùng `Thread.sleep(...)` tùy tiện.

Khi cần nhiều phụ thuộc để tạo SUT, đó có thể là tín hiệu service gánh quá nhiều trách nhiệm. Tuy nhiên, **không tách lớp chỉ để làm đẹp test**; đánh giá lại ranh giới nghiệp vụ và vai trò từng collaborator trước khi refactor.

## 8. Những lỗi dễ mắc và cách sửa

**Lỗi 1 — Mock cả đối tượng đang kiểm thử.** Nếu `sut` là mock, `when(sut.someMethod()).thenReturn(...)` chỉ xác nhận Mockito hoạt động, không chạy logic cần test. Hãy tạo SUT thật; chỉ thay cộng tác viên ở ngoài ranh giới.

**Lỗi 2 — Mock mọi thứ, kể cả value object và logic thuần.** Điều này che mất lỗi thực và tăng số setup. Hãy giữ thật những thành phần nhanh, xác định và là một phần hành vi cần kiểm tra.

**Lỗi 3 — Khởi động `@SpringBootTest` cho từng phép tính đơn giản.** Context chậm hơn, mang nhiều cấu hình và khó định vị nguyên nhân lỗi. Dùng JUnit thuần khi hành vi không cần Spring; vẫn dùng context khi chính wiring/proxy/transaction là mục tiêu.

**Lỗi 4 — Test trả xanh nhưng phần cần kiểm tra đã bị mock.** Ví dụ mock repository rồi khẳng định JPA query đúng, hoặc mock HTTP client rồi khẳng định JSON serialization đúng. Dời SUT sang adapter/repository thực và chọn cấp test tương ứng.

**Lỗi 5 — Ranh giới bị thủng do side effect ẩn.** Trong unit test service vẫn gọi `System.currentTimeMillis()`, HTTP singleton, static utility truy cập DB hoặc repository thật. Tách side effect vào dependency rõ ràng; kiểm tra test không cần credential, mạng, broker hay trạng thái môi trường.

**Lỗi 6 — Kiểm tra quá nhiều tương tác nội bộ.** Test đòi gọi helper A rồi B, đúng thứ tự dù không nằm trong hợp đồng; refactor hợp lệ làm test đỏ. Đổi assertion sang output và side effect có ý nghĩa, chỉ kiểm tra thứ tự khi thứ tự là quy tắc nghiệp vụ.

**Lỗi 7 — Đồng nhất fake và production.** Fake in-memory có thể bỏ qua unique index, transaction isolation, network failure hoặc eventual consistency. Dùng fake để test quyết định của SUT; thêm integration/contract test cho khác biệt có rủi ro.

## 9. Checklist trước khi hoàn tất một bài kiểm thử

- Tôi diễn đạt được **một hành vi cụ thể** mà test cần chứng minh chưa?
- SUT đang là thành phần thật, với input được điều khiển và output/side effect quan sát được chưa?
- Mỗi dependency được giữ thật hay thay thế có lý do theo ranh giới đã chọn chưa?
- Nếu test chỉ có mock, tôi có vô tình kết luận về DB, HTTP, Spring proxy hoặc security mà nó chưa kiểm chứng không?
- Các ca thành công, thất bại, input biên và việc **không thực hiện side effect** quan trọng đã được xét chưa?
- Test có phụ thuộc thời gian, mạng, thứ tự chạy, dữ liệu dùng chung hoặc chi tiết nội bộ không cần thiết không?
- Có bài slice/integration test bổ sung cho những hợp đồng framework và adapter mà unit test không bao phủ không?

**Ghi nhớ:** một unit test đáng tin đặt **logic thật cần chứng minh** ở giữa, **dependency controllable** ở rìa và **assertion đúng tại ranh giới hành vi**. Trong Spring Boot, chọn dùng hoặc không dùng application context là hệ quả của điều cần chứng minh, không phải định nghĩa của SUT.