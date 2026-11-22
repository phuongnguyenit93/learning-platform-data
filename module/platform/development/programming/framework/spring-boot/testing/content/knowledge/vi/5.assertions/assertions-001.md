# Chọn kết quả quan sát được để xác nhận hành vi trong kiểm thử

## 1. Mục tiêu: assertion phải chứng minh điều người dùng hoặc hệ thống khác nhận được

Một test thường có ba phần: chuẩn bị (**Arrange**), thực hiện hành động (**Act**), xác minh kết quả (**Assert**). Phần khó nhất không phải viết `assertEquals` hay `assertThat`, mà là **chọn sự thật nào cần kiểm tra**.

Ví dụ khi khách hàng đặt giữ 3 sản phẩm từ kho còn 10, hợp đồng nghiệp vụ có thể yêu cầu:

1. Hệ thống thông báo giữ hàng thành công.
2. Số lượng tồn kho sau đó còn 7.
3. Không xuất hiện lần giữ hàng thứ hai ngoài yêu cầu.
4. Nếu số lượng yêu cầu lớn hơn tồn kho, hệ thống từ chối và **không làm thay đổi** tồn kho.

Chỉ kiểm tra “phương thức có trả một object không null” không chứng minh được những hành vi ấy. Kiểm tra “hàm nội bộ `calculateRemaining()` được gọi một lần” cũng không đủ: hàm có thể được gọi nhưng dữ liệu cuối cùng vẫn sai.

**Kết quả quan sát được** (*observable outcome*) là đầu ra hoặc thay đổi mà một bên có quyền sử dụng hợp đồng của hệ thống có thể nhận biết: giá trị trả về, ngoại lệ/nhóm lỗi, trạng thái tồn tại sau hành động, HTTP status/body/header, sự kiện phát ra, bản ghi được lưu, lệnh gửi tới cổng bên ngoài, v.v. Phạm vi quan sát phụ thuộc **ranh giới của test**; test unit nhìn thấy trạng thái của fake, còn integration test có thể nhìn thấy dữ liệu ở database thật.

Mục tiêu học tập:

- Biến yêu cầu nghiệp vụ thành một hoặc nhiều **mệnh đề có thể kiểm chứng**.
- Phân biệt assertion về **kết quả** với assertion về **chi tiết triển khai**.
- Chọn đúng đối tượng quan sát theo tầng: Java thuần, service, web, persistence, message, security.
- Thiết kế trường hợp thành công và thất bại, bao gồm **điều không được xảy ra**.
- Viết assertion đủ mạnh để bắt lỗi thực sự nhưng không ràng buộc những chi tiết ngoài hợp đồng.
- Nhận biết false positive, brittle test, test bất định và các bẫy state/transaction trong Spring Boot.

## 2. Từ yêu cầu thành hợp đồng quan sát

Trước khi viết assertion, hãy trả lời bốn câu hỏi:

1. **Kích thích:** hành động cụ thể nào được thực hiện, với dữ liệu nào?
2. **Kết quả bắt buộc:** điều gì phải đúng sau hành động?
3. **Điều bị cấm:** điều gì tuyệt đối không được xảy ra?
4. **Ranh giới quan sát:** test nhìn được kết quả ở đâu mà không phụ thuộc vào cách code bên trong được viết?

Một mẫu mô tả ngắn:

> Khi [điều kiện ban đầu], nếu [hành động], thì [kết quả quan sát được] và [bất biến vẫn đúng]; nếu không thể thực hiện thì [lỗi/cách từ chối] và [không phát sinh tác động ngoài ý muốn].

Ví dụ:

> Khi tồn kho `ITEM-7` bằng 10, gọi giữ 3 sản phẩm phải trả `RESERVED` và số lượng còn 7. Khi yêu cầu 11 sản phẩm, phải trả `INSUFFICIENT` và tồn kho vẫn là 10.

Có ba nhóm bằng chứng thường gặp:

| Nhóm | Câu hỏi test trả lời | Ví dụ |
| --- | --- | --- |
| **Output** | Người gọi nhận được gì? | `ReservationResult(status=RESERVED, remaining=7)`, HTTP 201, JSON có `id` |
| **State** | Trạng thái có thể đọc sau đó là gì? | Số dư, số hàng trong DB, trạng thái đơn hàng |
| **Effect / interaction tại ranh giới** | Hệ thống đã gây tác động gì ra ngoài? | Publish event, gọi payment gateway, gửi email, không gọi API khi dữ liệu sai |

Không phải hành vi nào cũng cần cả ba nhóm. Với hàm tính giá thuần, output là đủ. Với thao tác ghi dữ liệu, chỉ output có thể tạo **false positive** nếu code trả “thành công” nhưng bỏ quên việc lưu. Với command không có return value, state/effect mới là nơi chứa bằng chứng.

**Bất biến** là mệnh đề phải luôn đúng, ví dụ “tồn kho không âm”, “tổng tiền nợ và có của một bút toán cân bằng”, “mỗi khóa idempotency chỉ dẫn tới một giao dịch nghiệp vụ”. Bất biến thường đáng assertion hơn số lần chạy hàm riêng.

## 3. Ví dụ chạy được với Java 17 và JUnit Jupiter

Ví dụ sau không cần Spring context. Nó mô tả dịch vụ giữ hàng và một repository giả bằng bộ nhớ, để tập trung vào cách chọn assertion. Với dự án Spring Boot dùng `spring-boot-starter-test`, JUnit Jupiter thường đã có trên test classpath. Chạy bằng task `test` cấu hình JUnit Platform.

### 3.1. Mã nghiệp vụ: `src/main/java/example/StockService.java`

```java
package example;

import java.util.Objects;

public final class StockService {
    public interface StockRepository {
        int quantityOf(String sku);
        void setQuantity(String sku, int quantity);
    }

    public enum Status {
        RESERVED,
        INSUFFICIENT
    }

    public record Result(Status status, int remaining) {}

    private final StockRepository repository;

    public StockService(StockRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public Result reserve(String sku, int amount) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int available = repository.quantityOf(sku);
        if (available < amount) {
            return new Result(Status.INSUFFICIENT, available);
        }

        int remaining = available - amount;
        repository.setQuantity(sku, remaining);
        return new Result(Status.RESERVED, remaining);
    }
}
```

Đây là thuật toán đơn giản phục vụ kiểm thử. Trong ứng dụng thật, thao tác “đọc số lượng rồi ghi số lượng mới” cần xử lý cạnh tranh đồng thời bằng transaction, optimistic/pessimistic locking hoặc câu lệnh cập nhật có điều kiện. Unit test bên dưới **không chứng minh an toàn đồng thời**.

### 3.2. Test với repository fake: `src/test/java/example/StockServiceTest.java`

```java
package example;

import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StockServiceTest {
    private static final String SKU = "ITEM-7";

    static final class InMemoryStock
            implements StockService.StockRepository {
        private final Map<String, Integer> quantities = new HashMap<>();

        InMemoryStock(int initialQuantity) {
            quantities.put(SKU, initialQuantity);
        }

        @Override
        public int quantityOf(String sku) {
            return quantities.getOrDefault(sku, 0);
        }

        @Override
        public void setQuantity(String sku, int quantity) {
            quantities.put(sku, quantity);
        }
    }

    @Test
    void reservationReportsSuccessAndChangesStock() {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        StockService.Result result = service.reserve(SKU, 3);

        assertAll(
                () -> assertEquals(StockService.Status.RESERVED,
                        result.status()),
                () -> assertEquals(7, result.remaining()),
                () -> assertEquals(7, stock.quantityOf(SKU))
        );
    }

    @Test
    void insufficientStockIsRejectedWithoutMutation() {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        StockService.Result result = service.reserve(SKU, 11);

        assertAll(
                () -> assertEquals(StockService.Status.INSUFFICIENT,
                        result.status()),
                () -> assertEquals(10, result.remaining()),
                () -> assertEquals(10, stock.quantityOf(SKU))
        );
    }

    @Test
    void invalidAmountThrowsAndDoesNotChangeStock() {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.reserve(SKU, 0)
        );

        assertAll(
                () -> assertEquals("amount must be positive",
                        error.getMessage()),
                () -> assertEquals(10, stock.quantityOf(SKU))
        );
    }

    @ParameterizedTest
    @CsvSource({
        "1, 9",
        "9, 1",
        "10, 0"
    })
    void reservationSupportsBoundaries(int amount, int expectedRemaining) {
        var stock = new InMemoryStock(10);
        var service = new StockService(stock);

        StockService.Result result = service.reserve(SKU, amount);

        assertAll(
                () -> assertEquals(StockService.Status.RESERVED,
                        result.status()),
                () -> assertEquals(expectedRemaining,
                        result.remaining()),
                () -> assertEquals(expectedRemaining,
                        stock.quantityOf(SKU))
        );
    }
}
```

Cần môi trường có JUnit Jupiter API, `junit-jupiter-params` và Jupiter engine. Với Spring Boot 3.x / Java 17, cấu hình Gradle Groovy DSL thường là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là đoạn thêm vào **build đã có cấu hình Spring Boot BOM/repositories**, không phải một tệp `build.gradle` độc lập. Dùng wrapper của dự án:

```bash
./gradlew test --tests example.StockServiceTest
```

Với Windows: `.\gradlew.bat test --tests example.StockServiceTest`. Test không in stdout nghiệp vụ; nếu các assertion đúng, runner đánh dấu bốn phương thức test là thành công, trong đó phương thức parameterized thực thi ba lần. Tên phương thức và số lượng lần chạy hiện ra tùy báo cáo build/IDE.

**Vì sao ba assertion trong test thành công có giá trị khác nhau?**

- `result.status() == RESERVED`: service trả trạng thái đúng.
- `result.remaining() == 7`: service báo lượng còn lại đúng.
- `stock.quantityOf(SKU) == 7`: repository thực sự nhận trạng thái mới.

Nếu lập trình viên vô tình xóa `repository.setQuantity(sku, remaining)`, hai assertion đầu có thể vẫn xanh, assertion cuối đỏ. Điều này cho thấy **kết quả trả về và trạng thái đã lưu không phải cùng một bằng chứng**.

Nếu đổi điều kiện từ `available < amount` thành `available <= amount`, trường hợp đặt đúng 10 sản phẩm sẽ thất bại; đây là lý do chọn giá trị biên. Nếu trong nhánh thiếu hàng code vô tình trừ kho, test từ chối vẫn bắt được thay đổi không hợp lệ.

### 3.3. Assertion nào là quá yếu?

```java
// Không chứng minh trạng thái và dữ liệu cuối cùng:
assertNotNull(result);

// Quá rộng nếu hợp đồng yêu cầu chính xác RESERVED:
assertTrue(result.status() != null);

// Đây có thể là tự lặp lại công thức đang lỗi:
assertEquals(10 - amount, result.remaining());

// Tách expected từ ví dụ nghiệp vụ để phát hiện tính sai:
assertEquals(7, result.remaining());
```

Đoạn trên chỉ minh họa các cách chọn assertion, không phải phần bổ sung nguyên xi vào tệp test. `10 - amount` đôi khi vẫn phù hợp nếu đó là **oracle độc lập, đáng tin**; rủi ro xuất hiện khi expected được tính bằng cùng thuật toán/cùng helper đang được kiểm thử, khiến bug xuất hiện ở cả hai vế.

### 3.4. Assertion nào quá chặt?

Giả sử hợp đồng chỉ cần trả trạng thái `RESERVED` và remaining 7, còn service được phép dùng repository batch update hoặc SQL atomic update. Test xác minh “hàm `setQuantity` được gọi **đúng một lần**” có thể vỡ khi đổi hiện thực, dù hành vi cuối vẫn đúng.

Hãy chỉ kiểm tra số lần gọi khi **số lần đó thuộc hợp đồng**: ví dụ thanh toán chỉ được thu tiền một lần, không phát duplicate event, hoặc không retry request ngoài chính sách. Còn số lần gọi private helper/cache lookup thường là chi tiết triển khai không cần cố định.

## 4. Tiêu chuẩn chọn assertion tốt

Một assertion tốt thường thỏa sáu tiêu chuẩn:

1. **Có nguồn từ yêu cầu:** người đọc có thể nối assertion với một quy tắc/hợp đồng cụ thể.
2. **Phân biệt đúng và sai:** nếu sản phẩm vi phạm quy tắc, test thực sự đỏ.
3. **Quan sát ở ranh giới thích hợp:** test service quan sát return/state/outbound port; test web quan sát HTTP; test persistence quan sát DB.
4. **Ít phụ thuộc implementation:** refactor hợp lệ, đổi helper, chia method hoặc tối ưu cấu trúc không làm test đỏ vô cớ.
5. **Xác định được nguyên nhân:** message/test name/fixture cho biết trường hợp nào hỏng.
6. **Ổn định khi chạy lại:** không phụ thuộc thứ tự chạy, đồng hồ máy, dữ liệu chung hoặc độ trễ không kiểm soát.

Các ví dụ:

| Yêu cầu | Assertion phù hợp | Assertion chưa đủ hoặc dễ giòn |
| --- | --- | --- |
| Phí ship miễn khi tổng ≥ 500.000 | `assertEquals(0, fee(500000))` | `fee >= 0` |
| Giữ hàng cập nhật tồn kho | Status thành công **và** truy vấn tồn kho còn 7 | Chỉ `result != null` |
| Đầu vào sai phải bị từ chối | Loại lỗi/HTTP status đúng **và** state không đổi | Chỉ kiểm tra có log ERROR |
| Tạo resource thành công | HTTP 201, `Location` hợp lệ, GET theo URL tìm được resource | Chỉ 2xx, hoặc chỉ gọi `repository.save` |
| Không thu tiền hai lần | Số transaction/charge thực hoặc outbound port ≤ 1 theo hợp đồng | Đếm số lần gọi helper nội bộ |
| Event mang dữ liệu đúng | Event type, key, payload nghiệp vụ, correlation id | Bất kỳ message nào xuất hiện |
| Không lộ thông tin người khác | 403/404 theo chính sách, response không chứa dữ liệu, DB không bị đổi | Chỉ kiểm tra controller method trả non-null |

Đối với một đối tượng phức tạp, hãy assert **những trường thuộc hợp đồng**. So sánh toàn bộ object có thể hữu ích nếu tất cả trường đều có ý nghĩa; nhưng snapshot quá rộng sẽ vỡ khi metadata không quan trọng thay đổi. Ngược lại, cố tình bỏ các trường trọng yếu như `currency` hoặc `ownerId` khiến test yếu.

## 5. Kết quả quan sát theo từng tầng của Spring Boot

Một hành vi có thể được quan sát từ nhiều tầng. Chọn điểm quan sát thấp nhất nhưng đủ chứng minh rủi ro đang xét.

| Loại test | Hành động | Điểm quan sát có giá trị |
| --- | --- | --- |
| Java unit test | Gọi hàm/constructor | Return value, exception, object state |
| Service unit test | Gọi use case với fake/mock | Kết quả nghiệp vụ, state fake, outbound command quan trọng |
| MVC slice `@WebMvcTest` | Gửi request qua `MockMvc` | HTTP status, header, JSON, validation/error mapping |
| JPA slice `@DataJpaTest` | Ghi/đọc entity/repository | Dữ liệu query, relationship, constraint, persistence behavior |
| `@SpringBootTest` + `MockMvc` | Request đi qua nhiều bean thật | HTTP response + dữ liệu DB hoặc effect liên quan |
| `RANDOM_PORT` | Gửi HTTP tới server đang mở cổng | Status, content type/body, header, cookie, contract mạng |
| Kafka/queue/integration | Gửi command hoặc thay đổi đầu vào | Event được broker/consumer nhận, payload, trạng thái cuối |
| Security test | Truy cập với principal/role cụ thể | Response cho phép/từ chối, dữ liệu không rò, không tác động cấm |

**Quan sát ở ranh giới nhỏ trước, mở rộng khi thiếu bằng chứng.** Một `@WebMvcTest` với service mock có thể chứng minh controller mapping và JSON contract nhưng không chứng minh JPA đã lưu đúng. Một repository unit test fake không chứng minh câu SQL thật. Full integration test có thể chứng minh cả luồng, đổi lại chậm và khó cô lập hơn.

### 5.1. Web: assert hợp đồng HTTP thay vì chi tiết controller

Giả sử endpoint `POST /api/reservations` nhận:

```json
{"sku":"ITEM-7","amount":3}
```

và, với số lượng đủ, trả HTTP 200:

```json
{"status":"RESERVED","remaining":7}
```

Dưới đây là controller minh họa tương thích Spring MVC 6 / Boot 3.x, dùng `StockService` ở mục 3. Tệp `src/main/java/example/StockController.java`:

```java
package example;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reservations")
public class StockController {
    private final StockService service;

    public StockController(StockService service) {
        this.service = service;
    }

    public record ReserveRequest(String sku, int amount) {}

    @PostMapping
    public StockService.Result reserve(@RequestBody ReserveRequest request) {
        return service.reserve(request.sku(), request.amount());
    }
}
```

Test MVC slice cho Spring Boot 3.3.x: `src/test/java/example/StockControllerWebTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StockController.class)
class StockControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    StockService service;

    @Test
    void exposesStatusAndRemainingStockInJson() throws Exception {
        when(service.reserve("ITEM-7", 3))
                .thenReturn(new StockService.Result(
                        StockService.Status.RESERVED, 7));

        mvc.perform(post("/api/reservations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"sku":"ITEM-7","amount":3}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("RESERVED"))
                .andExpect(jsonPath("$.remaining").value(7));
    }
}
```

Đoạn này yêu cầu dependency Spring MVC runtime và Spring Boot starter test phù hợp, một cấu hình `@SpringBootApplication` tìm được từ test package, và phiên bản Boot 3.3.x. Trong Boot 3.4+ với Spring Framework 6.2+, `@MockitoBean` của Spring Framework là hướng thay thế `@MockBean`; ở Boot 4.x, package/module test MVC cũng thay đổi. Khi dự án có Spring Security filter, cần authentication/CSRF thích hợp; HTTP 401/403 ngoài mong đợi có thể là vấn đề cấu hình security test. Không bê nguyên annotation/import Boot 3.3 sang mọi Boot 4.x.

**Điều được chứng minh:** route, JSON input, MVC dispatch, output serialization/status theo giả định service trả đúng dữ liệu. **Điều chưa được chứng minh:** service trừ kho đúng và repository lưu thật, vì service bị mock. Đó là lý do test unit ở mục 3 vẫn cần thiết.

Nếu API contract còn quy định `Content-Type: application/json`, header version, `Location`, mã lỗi 400/409 hoặc định dạng error body, thêm assertion tương ứng. Không bắt response body khớp nguyên chuỗi JSON chỉ vì thứ tự key hoặc khoảng trắng khác nếu hợp đồng không quy định.

### 5.2. Persistence: assert trạng thái truy vấn được

Với repository JPA, hành vi lưu dữ liệu nên được xác nhận qua một **truy vấn có ý nghĩa**:

```java
// Đoạn minh họa bên trong một @DataJpaTest có entity/repository tương ứng:
repository.saveAndFlush(new StockEntity("ITEM-7", 7));
entityManager.clear();

StockEntity reloaded = repository.findById("ITEM-7")
        .orElseThrow();

assertEquals(7, reloaded.getQuantity());
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập: cần `StockEntity`, `StockJpaRepository`, `EntityManager` và imports phù hợp. `saveAndFlush` yêu cầu repository hỗ trợ phương thức đó, thường từ `JpaRepository`.

Vì JPA có **first-level persistence context cache**, lấy lại cùng đối tượng đang managed đôi khi chỉ chứng minh state trong bộ nhớ, chưa đủ để xác minh vòng ghi/đọc database theo mục đích test. `flush` đẩy thay đổi pending xuống database trong transaction và `clear` bỏ entity đang managed để truy vấn lại; việc test dùng transaction và rollback là một vấn đề khác cần kiểm tra. Nếu mục tiêu là chứng minh dữ liệu đã **commit** và nhìn thấy từ request/transaction khác, hãy kiểm tra với ranh giới transaction thực và không mặc nhiên tin rollback test.

Khi cần kiểm tra schema constraint, unique key, optimistic locking, isolation hay dialect SQL, dùng database đủ giống production (thường qua Testcontainers). Một fake hoặc H2 không thể chứng minh mọi hành vi PostgreSQL/MySQL.

### 5.3. Service tích hợp nhiều lớp: assert ở hai đầu

Với một use case lưu dữ liệu, test `@SpringBootTest` + `@AutoConfigureMockMvc` có thể kiểm tra đồng thời:

```text
POST /api/reservations
      |
      v
HTTP status/body đúng          ← assertion 1
      |
Controller → Service
      |
Repository → Database
      |
đọc lại dữ liệu persisted       ← assertion 2
```

Hai đầu cho biết hệ thống vừa trả hợp đồng HTTP đúng vừa thực hiện hiệu ứng thật. Nếu chỉ verify `repository.save(...)`, test chưa chứng minh transaction commit/constraint hoặc dữ liệu có thể đọc lại. Nếu chỉ assert status 200, implementation có thể trả thành công dù không ghi gì.

`@SpringBootTest` mặc định không mở cổng HTTP thật; với `@AutoConfigureMockMvc`, request đi qua mock servlet environment. `@SpringBootTest(webEnvironment = RANDOM_PORT)` mở HTTP server thật; transaction ở thread test và thread server có thể khác, nên `@Transactional` trên test không tự bảo đảm rollback dữ liệu server đã commit.

### 5.4. Event và outbound API: interaction đôi khi **là** kết quả

Khi application được yêu cầu “gửi lệnh thu tiền đúng một lần”, lời gọi ra `PaymentGateway` là effect quan sát được ở **ranh giới ngoài**. Nếu test không thể kết nối hệ thống thanh toán thật, mock hoặc fake cổng là công cụ hợp lý.

```java
// Minh họa bên trong một unit test đã khai báo PaymentGateway và CheckoutService:
var gateway = mock(PaymentGateway.class);
var service = new CheckoutService(gateway);

service.checkout("order-42", 120_000L);

verify(gateway, times(1)).charge("order-42", 120_000L);
```

Đoạn này cố ý **không độc lập** vì phụ thuộc hợp đồng `PaymentGateway` và `CheckoutService` của ứng dụng. `verify(..., times(1))` có ý nghĩa khi hợp đồng cấm thu hai lần. Với các tương tác nội bộ không thuộc hợp đồng, số lần gọi chính xác có thể khiến test giòn khi refactor.

Nếu mục tiêu là xác minh HTTP request gửi đi, test với mock HTTP server (WireMock hoặc giải pháp tương đương) sẽ cho bằng chứng mạnh hơn về method, URL, header, body và cách xử lý lỗi. Với message broker, chỉ verify lời gọi `publisher.send` chưa chứng minh broker đã nhận hoặc consumer đã xử lý; hãy dùng integration test ở ranh giới broker khi đó là rủi ro cần kiểm tra.

## 6. Chọn cả kết quả được phép và tác động **không được xảy ra**

Nhiều lỗi nghiêm trọng nằm ở **đường thất bại**. Test “thất bại đúng” gồm hai vế:

- **Từ chối đúng:** exception/error code/HTTP status/message thuộc hợp đồng.
- **Không có tác động cấm:** không trừ tiền, không giảm kho, không ghi đơn, không phát event thành công.

Ví dụ yêu cầu giữ 11 sản phẩm khi kho chỉ còn 10:

```java
var stock = new InMemoryStock(10);
var service = new StockService(stock);

var result = service.reserve("ITEM-7", 11);

assertEquals(StockService.Status.INSUFFICIENT, result.status());
assertEquals(10, stock.quantityOf("ITEM-7"));
```

Đây là đoạn trích dựa trên `InMemoryStock` của mục 3. Nếu bỏ assertion thứ hai, test có thể xanh trong khi hệ thống vừa từ chối vừa âm thầm trừ kho.

Với API, những tình huống nên xem xét:

| Tình huống | Kết quả trả về | Tác động không được có |
| --- | --- | --- |
| Input sai | 400 với mã lỗi theo hợp đồng | Không ghi dữ liệu |
| Không xác thực | 401 | Không thực hiện nghiệp vụ được bảo vệ |
| Không đủ quyền | 403 hoặc 404 theo chính sách | Không lộ resource/không sửa dữ liệu |
| Conflict hoặc hết hàng | 409 hoặc mã nghiệp vụ tương ứng | Không tạo reservation thành công |
| Tài nguyên không tồn tại | 404 | Không sửa tài nguyên khác |
| Thanh toán lặp request | Theo hợp đồng idempotency | Không thu tiền lần hai |
| Phụ thuộc ngoài timeout | Lỗi/đường retry đã quy định | Không tạo kết quả giả thành công |

Đây là **các hợp đồng minh họa**, không mặc định Spring Boot tự sinh các HTTP status trên. Ứng dụng cần validation, exception mapping, security và transaction behavior đúng để thỏa chúng.

## 7. Chọn assertion theo mức độ chính xác của hợp đồng

### 7.1. Chính xác tuyệt đối khi hợp đồng chính xác

Các kết quả tiền tệ nguyên, trạng thái enum, mã lỗi hay số lượng kho thường cần giá trị **chính xác**:

```java
assertEquals(7, remaining);
assertEquals("INSUFFICIENT_STOCK", errorCode);
```

Đừng đổi thành `assertTrue(remaining >= 0)` nếu mục tiêu là kiểm tra đã trừ đúng 3 sản phẩm.

Với decimal, tiền và số thực:

- Dùng `BigDecimal` cho nhiều phép tính tiền và xác định scale/rounding theo nghiệp vụ.
- Với số thực khoa học, dùng tolerance phù hợp đặc tả, ví dụ `assertEquals(expected, actual, 1e-9)` nếu độ chính xác cho phép.
- Đừng tự thêm tolerance quá rộng làm lỗi tính toán lọt qua.
- Với `BigDecimal`, `equals` phân biệt scale (`1.0` khác `1.00`); nếu hợp đồng xem chúng cùng giá trị số học, cân nhắc `compareTo` hoặc AssertJ `isEqualByComparingTo`.

### 7.2. Khoảng, tập hợp, thứ tự và tính duy nhất

Nếu hợp đồng chỉ yêu cầu “ít nhất một kết quả” hoặc “mọi kết quả có trạng thái active”, hãy kiểm tra đúng thuộc tính đó. Không bắt thứ tự list nếu API không đảm bảo sort.

Ví dụ với AssertJ:

```java
// Có thứ tự được hợp đồng quy định:
assertThat(ids).containsExactly("A", "B", "C");

// Không quy định thứ tự nhưng phải cùng các giá trị:
assertThat(ids).containsExactlyInAnyOrder("A", "B", "C");

// Chỉ quy định không có trùng:
assertThat(ids).doesNotHaveDuplicates();
```

Ba dòng là các lựa chọn cho **ba hợp đồng khác nhau**, không nhất thiết cùng xuất hiện trong một test. `ids` là danh sách được chuẩn bị tại test thực tế.

### 7.3. Thời gian, ID ngẫu nhiên, metadata

Không hard-code timestamp/UUID được tạo ngẫu nhiên nếu hợp đồng không hứa giá trị cố định. Thay vào đó:

- Inject `Clock.fixed(...)` vào service nếu cần xác minh **thời điểm chính xác** một cách lặp lại.
- Với generated ID, kiểm tra định dạng, không rỗng, duy nhất hoặc GET lại resource bằng ID đó nếu đó là hợp đồng.
- Với timestamp do server sinh, kiểm tra mối quan hệ `createdAt <= updatedAt` và ranh giới thời gian có ý nghĩa; đừng assert một giờ thực tế dễ trôi vì CI.
- Không cố định các header như `Date`, `Server` hoặc thứ tự JSON fields trừ khi contract yêu cầu.

### 7.4. Thông báo lỗi

Thông điệp lỗi là một kết quả quan sát được **nếu API/hợp đồng yêu cầu ổn định**. Với lỗi Java nội bộ, thường chỉ cần class exception và state được bảo toàn; assert chính xác từng dấu chấm trong message có thể quá chặt nếu message chỉ phục vụ developer.

```java
assertThrows(IllegalArgumentException.class,
        () -> service.reserve("ITEM-7", 0));
```

Nếu API cung cấp `errorCode` ổn định và `message` được localize, ưu tiên assert `errorCode` chính xác và schema/message tối thiểu cần thiết; không cố định câu tiếng Anh nếu nó có thể thay đổi theo locale.

## 8. Nhiều assertion trong một test: bao nhiêu là đủ?

Quy tắc hữu ích là **một kịch bản hành vi**, không phải “chỉ một câu lệnh assert”. Một kết quả nghiệp vụ có thể cần nhiều assertion bổ sung cho nhau, ví dụ:

```java
assertAll(
        () -> assertEquals(StockService.Status.RESERVED,
                result.status()),
        () -> assertEquals(7, result.remaining()),
        () -> assertEquals(7, stock.quantityOf("ITEM-7"))
);
```

`assertAll` của JUnit Jupiter thu thập các thất bại từ những assertion có thể thực hiện độc lập, giúp báo cáo nhiều điểm sai trong cùng một kịch bản. **Không** dùng nó để ghép một chuỗi dài hành động phụ thuộc nhau hoặc trộn nhiều use case khác nhau vào cùng một test.

Tách thành test khác khi:

- Điều kiện ban đầu khác đáng kể (đủ hàng vs hết hàng).
- Phải reset state riêng.
- Lỗi sẽ có nguyên nhân khác hoặc hợp đồng khác.
- Kịch bản trở nên khó đọc vì nhiều nhánh.

Có thể đặt helper cho Arrange và assertion có nghĩa nghiệp vụ, nhưng tránh che dấu toàn bộ expected logic trong helper phức tạp. Một tên như `assertOrderPersistedWithTotal(...)` có thể hữu ích khi nhiều test cần cùng hợp đồng, miễn helper thật sự kiểm tra các trường trọng yếu.

## 9. Test oracle: expected đến từ đâu?

**Test oracle** là cơ sở độc lập để biết kết quả đúng. Oracle có thể là đặc tả, bảng quy tắc nghiệp vụ, ví dụ đã được duyệt, phép toán/bất biến độc lập hoặc một hệ thống tham chiếu đáng tin.

Các nguồn oracle tốt:

1. **Đặc tả rõ ràng:** “ngưỡng 500.000 miễn phí ship”.
2. **Bảng dữ liệu đầu vào/đầu ra được duyệt:** giá trị biên, trường hợp lỗi, chính sách quyền.
3. **Bất biến toán học/nghiệp vụ:** sau chuyển tiền giữa hai tài khoản, tổng số dư không đổi nếu không có phí.
4. **Quan hệ biến hình (*metamorphic relation*):** tăng số lượng giữ hàng hợp lệ thêm một đơn vị thì lượng tồn còn lại giảm thêm một, với cùng tồn kho ban đầu.
5. **Hệ thống tham chiếu:** chỉ khi có hiểu biết rõ về độ tin cậy và phạm vi so sánh.

Những cách dễ tạo false positive:

- Tính `expected` bằng chính phương thức đang được test.
- Gọi cùng một hàm helper sản xuất trong cả Act và expected, rồi kết luận thuật toán đã đúng.
- Assert dữ liệu sau Act từ object đã được thay đổi **cùng nguồn**, thay vì quan sát qua cổng lưu trữ phù hợp.
- Chép snapshot response được tạo bởi code hiện tại rồi luôn chấp nhận nó mà không đối chiếu hợp đồng.
- Assert `true` chỉ vì build không ném exception.

**Ví dụ oracle độc lập:** với kho đầu 10 và giữ 3, expected = 7 lấy từ quy tắc đã biết; không cần gọi lại một phương thức `calculateRemaining` trong production để tính expected.

## 10. Độ mạnh của assertion và kiểm thử lỗi cố ý

Một phương pháp tự đánh giá rất hiệu quả là hỏi:

> Nếu tôi cố tình đưa một lỗi nhỏ, quan trọng vào code, assertion này có đỏ không?

Với `StockService` ở mục 3, hãy hình dung các mutation sau:

| Mutation cố ý | Assertion phải bắt được |
| --- | --- |
| Đổi `available < amount` thành `available <= amount` | Trường hợp giữ đúng 10/10 |
| Xóa `repository.setQuantity(...)` | Assertion đọc lại số lượng từ fake |
| Đổi trạng thái thành `RESERVED` dù thiếu hàng | Assertion status nhánh thiếu |
| Vẫn giảm kho khi từ chối | Assertion kho không đổi |
| Trả `remaining = available` dù đã trừ kho | Assertion trên result.remaining |
| Bỏ kiểm tra `amount <= 0` | Assertion về exception và state |

Có thể thực hiện thử nghiệm có kiểm soát trên branch/sandbox rồi hoàn nguyên; công cụ mutation testing có thể tự tạo mutation tương tự. Không cần ép mỗi assertion bắt mọi mutation; điều quan trọng là **tập test của một hợp đồng** phải bắt được những sai lệch có ý nghĩa đối với hợp đồng đó.

**Line coverage 100% không đồng nghĩa assertion tốt.** Test có thể chạy mọi dòng nhưng chỉ gọi phương thức rồi `assertNotNull`. Mutation testing cho cái nhìn bổ sung về khả năng phát hiện lỗi, nhưng mutation score cũng không thay thế review hợp đồng và test integration ở những ranh giới quan trọng.

## 11. Khi có nhiều người dùng hoặc chạy bất đồng bộ

### 11.1. Concurrency và transaction

Một unit test chạy tuần tự chỉ chứng minh kết quả trong điều kiện tuần tự. Với tồn kho còn 1 và hai request cùng giữ 1 sản phẩm, bất biến cần là **không thể có hai reservation thành công nếu cả hai cùng tiêu thụ một đơn vị**.

Muốn xác nhận bất biến này phải có test với các transaction/request thật, cơ chế đồng bộ rõ, và quan sát dữ liệu cuối cùng cùng kết quả của cả hai tác vụ. Unit test dùng `HashMap` ở mục 3 không chứng minh tính nguyên tử hoặc chống race condition; triển khai production cần optimistic/pessimistic locking hoặc update có điều kiện phù hợp.

Khi test DB:

- Kiểm tra transaction nào đã commit/rollback và thread nào sở hữu transaction.
- Nếu kết quả cần tồn tại sau commit, đọc từ một transaction/connection thích hợp thay vì chỉ nhìn entity đang managed.
- Cô lập test data; không để thứ tự chạy hoặc dữ liệu của test khác quyết định kết quả.

### 11.2. Eventual consistency và message queue

Với consumer xử lý sự kiện bất đồng bộ, yêu cầu thường là “cuối cùng xuất hiện kết quả trong vòng giới hạn” chứ không phải “ngay trong một mili giây”.

Đừng dùng:

```java
// Mong manh: tốc độ CI không được cam kết.
Thread.sleep(1000);
assertEquals("PAID", readOrderStatus());
```

Thay bằng chờ **điều kiện** với timeout có giới hạn (ví dụ Awaitility nếu đã khai báo dependency kiểm thử thích hợp):

```java
// Đoạn minh họa, cần Awaitility trên test classpath:
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
            assertEquals("PAID", readOrderStatus()));
```

Hai đoạn này minh họa chiến lược chờ, không phải chương trình chạy độc lập: `readOrderStatus()` cần được hiện thực; `await()` từ Awaitility và `Duration` từ Java. Chọn timeout dựa trên SLA/test environment, không tùy tiện phóng to thời gian để che race condition.

Hãy assert thêm các invariant nếu nghiệp vụ cần: event chỉ được xử lý một lần về mặt hiệu ứng, correlation ID đúng, message lỗi chuyển DLQ, không tạo bản ghi trùng khi retry. Chỉ đếm message trên một topic không đủ chứng minh consumer đã áp dụng đúng.

## 12. Phân biệt assertion của test với logic chuẩn bị test

Test ổn định cần phân biệt ba loại mã:

- **Fixture/Arrange:** tạo người dùng, tồn kho ban đầu, dữ liệu database, stub response.
- **Act:** gọi một hành động duy nhất cần kiểm tra.
- **Assert:** đọc kết quả độc lập và so với hợp đồng.

Ví dụ nên tránh:

```java
var result = service.reserve("ITEM-7", 3);
// Không tốt: chuẩn bị thêm trạng thái sau Act rồi mới assert.
stock.setQuantity("ITEM-7", 7);
assertEquals(7, stock.quantityOf("ITEM-7"));
```

Ở đây test tự sửa state sau hành động, nên có thể xanh dù service không làm gì. Tương tự, test data builder có side effect lưu DB hoặc tự publish event có thể che lỗi của hệ thống.

Một test đáng tin phải **tự tạo state ban đầu**, chỉ tác động qua hành vi đang kiểm thử ở bước Act, rồi quan sát kết quả. Nếu buộc phải dọn dữ liệu sau test, cleanup không được tham gia “làm đúng” kết quả trước assertion.

Với API HTTP/JSON, assertion nên đọc **response thật của request vừa gửi**; với DB, ưu tiên query theo business key/ID để xác minh dữ liệu xuất hiện đúng. Với fake, hãy giữ fake đơn giản và dễ kiểm chứng để không biến fake thành một hệ thống phức tạp thứ hai.

## 13. Các lỗi assertion phổ biến trong thực tế

| Dấu hiệu | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| `assertTrue(true)` hoặc test không có assert | Không có bằng chứng hành vi | Thêm kết quả cụ thể cần chứng minh |
| `assertNotNull(response)` cho mọi endpoint | Test yếu, sai status/body vẫn xanh | Assert status, trường JSON và effect liên quan |
| `verify(privateHelper, times(1))` | Phụ thuộc cấu trúc triển khai | Assert output/state; chỉ verify outbound contract |
| So sánh nguyên JSON string | Dễ vỡ vì whitespace/thứ tự key | JSONPath/object field/schema theo hợp đồng |
| Assert full DTO gồm timestamp/UUID random | Giòn theo dữ liệu không ổn định | Cố định `Clock` hoặc assert thuộc tính cần thiết |
| Assert status 200 cho lệnh tạo resource | Có thể quá yếu nếu contract là 201/Location | Chọn HTTP contract chính xác |
| Chỉ assert response success khi ghi DB | Không thấy lỗi “trả success nhưng không lưu” | Thêm đọc lại persisted state ở integration test |
| Chỉ assert exception, không assert state | Có thể đã trừ tiền/kho rồi mới ném lỗi | Assert không phát sinh effect cấm |
| Dùng dữ liệu từ test khác | Phụ thuộc thứ tự, dễ flake | Tạo fixture và cleanup độc lập |
| Ngủ cố định rồi assert async | Flaky trên CI chậm | Chờ theo điều kiện và timeout |
| Assert số lượng record toàn DB chung | Dữ liệu song song ảnh hưởng | Cô lập DB/schema hoặc lọc business ID |
| Assert từ entity JPA đang managed | Có thể chỉ quan sát bộ nhớ cấp 1 | Flush/clear, query lại và kiểm tra transaction |
| Chỉ dùng fake để kết luận SQL thực | Fake không thực thi constraint/query dialect | Thêm `@DataJpaTest`/integration với DB phù hợp |

Phân tích test đỏ cũng cần đúng phạm vi: lỗi JSON/body thuộc hợp đồng web; lỗi container không chạy là vấn đề môi trường, không nên đổi expected nghiệp vụ để làm xanh; lỗi timeouts cần điều tra độ trễ/race thay vì tăng thời gian vô hạn.

## 14. Bộ câu hỏi chọn assertion trước khi code

Dùng bảng quyết định đơn giản:

```text
Cần xác minh hành vi gì?
    |
    +-- Hàm tính toán thuần?
    |      -> assert giá trị/exception và giá trị biên.
    |
    +-- Command làm thay đổi state?
    |      -> assert phản hồi + đọc lại state + bất biến.
    |
    +-- Gọi cổng hệ thống ngoài?
    |      -> assert command/payload/idempotency;
    |         mock port ở unit, giao thức thật ở integration nếu cần.
    |
    +-- HTTP API?
    |      -> assert status + header/body/schema theo contract;
    |         thêm DB/effect nếu phải chứng minh toàn luồng.
    |
    +-- Xử lý async?
    |      -> assert kết quả cuối bằng chờ điều kiện có timeout;
    |         kiểm tra không duplicate hoặc hiệu ứng cấm.
    |
    +-- Từ chối/ngoại lệ?
           -> assert lỗi đúng + state/effect không đổi.
```

Checklist viết test:

- [ ] Tôi có thể phát biểu hành vi cần chứng minh bằng một câu nghiệp vụ rõ ràng.
- [ ] Test cho biết điều kiện ban đầu và hành động duy nhất cần quan sát.
- [ ] Expected được lấy từ hợp đồng/oracle độc lập, không sao chép thuật toán production.
- [ ] Assertion đủ cụ thể để nhận ra một lỗi thực tế mà người dùng quan tâm.
- [ ] Nếu hành vi thay đổi state, tôi đã kiểm tra state sau hành động khi cần.
- [ ] Nếu hành vi thất bại, tôi đã xác minh những tác động bị cấm không xảy ra.
- [ ] Nếu kiểm tra mock interaction, tôi xác nhận đó là **ranh giới hợp đồng**, không phải chi tiết nội bộ.
- [ ] Test không phụ thuộc timestamp ngẫu nhiên, thứ tự dữ liệu không cam kết, DB chung hoặc sleep cố định.
- [ ] Tôi biết test **không thể chứng minh** điều gì (SQL thật, transaction, HTTP thật, concurrency...).
- [ ] Khi cố ý tạo lỗi ở logic quan trọng, ít nhất một assertion liên quan trở thành đỏ.

## 15. Bài thực hành có đáp án định hướng

**Bài 1 — Bắt lỗi giả thành công.** Trong `StockService.reserve`, tạm xóa lệnh `repository.setQuantity(sku, remaining)` ở nhánh đủ hàng. Chạy `reservationReportsSuccessAndChangesStock`. Hai assertion output có thể pass nhưng state assertion phải fail. Khôi phục mã ngay sau thử nghiệm. Kết luận: khi hành vi yêu cầu ghi state, test nên đọc lại state.

**Bài 2 — Bắt lỗi ranh giới.** Đổi `available < amount` thành `available <= amount`. Chạy trường hợp parameterized đặt 10/10. Expected `RESERVED` và remaining 0 phải làm test fail. Khôi phục. Kết luận: chọn dữ liệu biên có ý nghĩa hơn chỉ thử mức trung bình.

**Bài 3 — Viết đường từ chối.** Với stock = 10 và amount = 11, viết test chỉ assert `INSUFFICIENT`. Sau đó cố ý thêm mutation giảm stock trước khi trả lỗi: test còn xanh hay không? Thêm `assertEquals(10, stock.quantityOf(SKU))` để bắt tác động cấm.

**Bài 4 — Từ unit tới HTTP.** Dùng controller ở mục 5, mô tả chính xác endpoint contract: success 200 và JSON `status=RESERVED, remaining=7`. Với `@WebMvcTest`, khẳng định cả status lẫn hai field; giải thích vì sao test này không chứng minh database đã thay đổi. Nếu muốn chứng minh điều đó, thiết kế integration test có repository thật và đọc lại state.

**Bài 5 — Review assertion.** Phân loại các assertion sau theo “mạnh đúng hợp đồng”, “quá yếu” hoặc “quá chặt”:

| Assertion ứng viên | Khi nào hợp lý? |
| --- | --- |
| `assertNotNull(receipt)` | Chỉ khi hợp đồng duy nhất thực sự là non-null; đa số bài toán thanh toán chưa đủ |
| `assertEquals("PAID", receipt.status())` | Khi trạng thái phải chính xác |
| `verify(gateway, times(1)).charge(...)` | Khi charge đúng một lần là effect quan trọng |
| `verify(repository, times(2)).findById(...)` | Thường quá chặt nếu cache/refactor được phép |
| `assertEquals(7, queryStock("ITEM-7"))` | Khi hành vi bắt buộc tồn kho mới bằng 7 |
| `assertEquals(expectedRawJsonString, responseBody)` | Chỉ nếu từng byte/ký tự là contract, thường không phải API JSON thông thường |

**Tiêu chí hoàn thành bài:** học viên không chỉ viết được assertion đúng cú pháp mà còn giải thích được (a) **hợp đồng** đằng sau assertion, (b) **mutation** nào nó bắt được và (c) **khoảng trống bằng chứng** của cấp test đã chọn.

## Tài liệu tham khảo chính thức

- JUnit User Guide — assertions, grouped assertions, exception testing, parameterized tests: https://docs.junit.org/current/user-guide/
- AssertJ — object, collection, exception and field assertions: https://assertj.github.io/doc/
- Mockito — mocking, stubbing, verification: https://site.mockito.org/
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Framework — Testing Transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
