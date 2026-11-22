# Ma trận kiểm thử Spring Boot: trường hợp thành công, đầu vào sai, giá trị biên và phụ thuộc lỗi

## 1. Mục tiêu và cách đọc ma trận

Một ma trận trường hợp kiểm thử (test-case matrix) biến **quy tắc nghiệp vụ và hợp đồng API** thành các tình huống có thể thực thi, với kết quả mong đợi và bằng chứng kiểm tra cụ thể. Trong Spring Boot, bốn nhóm cần được tách rõ:

- **Thành công (happy path):** yêu cầu hợp lệ, nghiệp vụ thành công; xác minh kết quả trả về **và** tác dụng phụ đúng.
- **Đầu vào sai (invalid input):** thiếu trường, sai kiểu, sai định dạng hoặc vi phạm ràng buộc; yêu cầu phải bị từ chối trước khi gọi phụ thuộc hay ghi dữ liệu.
- **Giá trị biên (boundary):** kiểm tra ngay dưới, tại và ngay trên ngưỡng cho phép. Biên hợp lệ có thể nằm trong nhóm thành công; biên không hợp lệ nằm trong nhóm đầu vào sai.
- **Phụ thuộc lỗi (dependency failure):** dịch vụ, cơ sở dữ liệu hoặc hệ thống bên ngoài trả lỗi, hết thời gian chờ, mất kết nối hoặc trả kết quả nghiệp vụ không đáp ứng. Phải phân biệt **từ chối nghiệp vụ** với **lỗi kỹ thuật**.

Mỗi dòng phải trả lời được: điều kiện ban đầu là gì, thao tác nào được thực hiện, phản hồi nào đúng, các thành phần nào được/không được gọi và có tác dụng phụ nào cần xác nhận. Không xem một mã HTTP duy nhất là đủ để kết luận PASS.

## 2. Chốt hợp đồng mẫu trước khi lập ma trận

Xét API minh họa của một ứng dụng Spring Boot: `POST /api/orders`, tạo đơn cho một mã hàng. Đây là **hợp đồng ví dụ được quy định cho bài học**, không phải mặc định của mọi hệ thống.

Yêu cầu JSON:

```json
{
  "sku": "SKU-01",
  "quantity": 5
}
```

Quy tắc:

1. `sku` là chuỗi không `null`, không rỗng và không chỉ chứa khoảng trắng.
2. `quantity` phải có mặt, là số nguyên và nằm trong khoảng **1 đến 10**, kể cả hai đầu mút.
3. Khi dữ liệu hợp lệ, hệ thống gọi `InventoryPort.reserve(sku, quantity)` một lần để giữ hàng. Trả `true` nghĩa là có thể giữ hàng; `false` nghĩa là hết hàng.
4. Nếu giữ hàng thành công, trả `201 Created` và JSON có `orderId` khác rỗng. Ứng dụng thực tế có thể còn lưu đơn; lúc đó phải xác minh lưu đúng một lần.
5. Dữ liệu yêu cầu không hợp lệ → `400 Bad Request`, không gọi hệ thống kho. Hết hàng do nghiệp vụ → `409 Conflict`. Phụ thuộc kho không sẵn sàng, kết nối lỗi, timeout hoặc phản hồi kỹ thuật 5xx được adapter chuyển thành lỗi phụ thuộc → `503 Service Unavailable`.
6. Adapter và cơ chế xử lý ngoại lệ phải thực sự thực hiện các ánh xạ ở mục 5. Nếu sản phẩm dùng `422`, `502` hoặc `504`, thay kết quả mong đợi theo hợp đồng đã duyệt, không sửa test chỉ để khớp hành vi bất kỳ.

Ví dụ DTO của Spring Boot 3+ với Jakarta Bean Validation:

```java
package example;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
    @NotBlank String sku,
    @NotNull @Min(1) @Max(10) Integer quantity
) {}
```

Ở controller cần `@Valid @RequestBody CreateOrderRequest request` và dependency `spring-boot-starter-validation`. Dùng `Integer` để phân biệt trường bị thiếu/`null` với số `0`; nếu dùng primitive `int`, dữ liệu thiếu có thể thành `0` khiến ý nghĩa lỗi khó rõ ràng. Ràng buộc `@Min`/`@Max` kiểm tra cận theo giá trị, không tự kiểm tra parse JSON. JSON sai cú pháp hoặc `quantity: "abc"` thường bị tầng chuyển đổi JSON từ chối trước bước Bean Validation.

## 3. Ma trận trường hợp kiểm thử mẫu

Các mã M01–M19 là định danh ổn định để gắn với yêu cầu, test tự động và kết quả chạy. Cột “Kho” mô tả stub/mock phản hồi từ phụ thuộc; “không gọi” là một **assertion bắt buộc** cho đầu vào sai.

| ID | Nhóm | Dữ liệu hoặc tình huống | Kho | Kết quả mong đợi và bằng chứng |
| --- | --- | --- | --- | --- |
| M01 | Thành công thông thường | `sku=SKU-01`, `quantity=5` | `true` | `201`; `orderId` khác rỗng; gọi `reserve("SKU-01",5)` đúng một lần |
| M02 | Biên dưới hợp lệ | `quantity=1` | `true` | `201`; gọi kho đúng giá trị `1` |
| M03 | Biên trên hợp lệ | `quantity=10` | `true` | `201`; gọi kho đúng giá trị `10` |
| M04 | Đầu vào sai | Thiếu trường `sku` | Không gọi | `400`; không gọi kho/không tạo đơn |
| M05 | Đầu vào sai | `sku="   "` | Không gọi | `400`; xác minh `@NotBlank` loại chuỗi toàn khoảng trắng |
| M06 | Đầu vào sai | Thiếu trường `quantity` | Không gọi | `400`; không gọi kho |
| M07 | Đầu vào sai | `quantity=null` | Không gọi | `400`; không gọi kho |
| M08 | Ngay dưới biên dưới | `quantity=0` | Không gọi | `400`; không gọi kho |
| M09 | Giá trị âm | `quantity=-1` | Không gọi | `400`; không gọi kho |
| M10 | Ngay trên biên trên | `quantity=11` | Không gọi | `400`; không gọi kho |
| M11 | Xa ngoài biên | `quantity=2147483647` | Không gọi | `400`; không gọi kho; không xảy ra tràn số trong xử lý |
| M12 | Sai kiểu | `quantity="abc"` | Không gọi | `400` do không chuyển đổi được sang số nguyên; không gọi kho |
| M13 | JSON hỏng | JSON thiếu dấu ngoặc đóng | Không gọi | `400`; không gọi kho; lỗi được trả an toàn |
| M14 | Từ chối nghiệp vụ | Yêu cầu hợp lệ `quantity=5` | `false` | `409`; không tạo đơn; không đổi thành `503` |
| M15 | Phụ thuộc timeout | Yêu cầu hợp lệ | Timeout được adapter quy đổi thành ngoại lệ phụ thuộc | `503` theo hợp đồng mẫu; không công bố stack trace |
| M16 | Phụ thuộc mất kết nối | Yêu cầu hợp lệ | Connection refused / network error | `503`; không báo thành công giả |
| M17 | Phụ thuộc trả 5xx | Yêu cầu hợp lệ | HTTP `500`/`503` từ kho | `503` sau ánh xạ của adapter; giữ nguyên quy tắc không tạo đơn |
| M18 | Phụ thuộc phản hồi bất thường | Yêu cầu hợp lệ | Payload không đúng schema, adapter coi là không khả dụng | `503` nếu đó là chính sách adapter; phải có test adapter xác nhận cách phân loại |
| M19 | Thứ tự ưu tiên lỗi | `quantity=0` **và** kho đang hỏng | Không được gọi | `400`; không xảy ra truy cập kho; tránh lỗi `503` che lỗi đầu vào |

**Bộ tứ biên trọng tâm** cho miền số nguyên `[1,10]` là `0, 1, 10, 11`: hai điểm hợp lệ và hai điểm không hợp lệ. `-1` và số nguyên rất lớn là trường hợp bổ sung theo rủi ro. Nếu thay hợp đồng (chẳng hạn tăng tối đa lên 100), phải sửa ranh giới và dữ liệu test đồng thời.

M18 chỉ được chốt thành test với `503` khi adapter định nghĩa phản hồi hỏng là “phụ thuộc không khả dụng”; hệ thống khác có thể dùng `502 Bad Gateway`. Không suy đoán từ một lỗi mà tầng HTTP tình cờ trả về.

## 4. Biến ma trận thành các phép kiểm tra

Một test có chất lượng cần **đầu vào (arrange)**, **hành động (act)** và **điều kiện PASS (assert)**. Ngoài mã trạng thái, cần kiểm tra các yếu tố sau:

| Phân loại | Assert ở biên HTTP | Assert tại service/adapter | Tác dụng phụ |
| --- | --- | --- | --- |
| Thành công | `201`, nội dung và cấu trúc `orderId` | Gọi kho đúng `sku`, `quantity`, số lần gọi | Nếu có repository, lưu đúng một đơn; không lưu hai lần |
| Đầu vào sai | `400` và hợp đồng lỗi phù hợp | Không gọi service hoặc kho trước khi validation xong | Không lưu, không gửi sự kiện, không giữ hàng |
| Biên | `1` và `10` được chấp nhận; `0` và `11` bị từ chối | Giá trị biên truyền nguyên vẹn xuống service | Không làm tròn, ép kiểu hoặc đổi cận ngầm |
| Hết hàng | `409` và thông tin lỗi nghiệp vụ an toàn | `reserve` trả `false` | Không tạo đơn |
| Phụ thuộc kỹ thuật lỗi | `503` theo hợp đồng, không lộ chi tiết nội bộ | Adapter phân loại timeout, kết nối, upstream 5xx chính xác | Không ghi trạng thái “thành công”; kiểm tra tính nhất quán và retry |

Không chỉ kiểm tra `verify(inventory).reserve(...)`: với đường lỗi đầu vào, `verifyNoInteractions(inventory)` hoặc `verifyNoInteractions(orderService)` tại đúng tầng mới chứng minh yêu cầu không đi sâu vào hệ thống. Nếu có nhiều thành phần, kiểm tra cả repository, event publisher và các side effect quan trọng.

Khi phản hồi lỗi có body chuẩn như Problem Details (`application/problem+json`), assert các trường đã công bố (`status`, `type`, `title` hoặc `detail` theo contract); không cố định nội dung thông báo nội bộ, stack trace hay timestamp không ổn định.

## 5. Ví dụ JUnit Jupiter + Mockito chạy được cho service

Ví dụ sau là **một tệp test Java 17 độc lập về mặt mã nguồn**, đặt tại `src/test/java/example/OrderServiceTest.java` trong dự án có JUnit Jupiter và Mockito (thường được đưa vào bởi `spring-boot-starter-test`). Các lớp lồng nhau là fixture tối giản để minh họa M01–M03, M14–M16; ở dự án thật, thay chúng bằng `OrderService` và `InventoryPort` của ứng dụng.

```java
package example;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderServiceTest {
    interface InventoryPort {
        boolean reserve(String sku, int quantity);
    }

    static class OutOfStockException extends RuntimeException {}
    static class DependencyUnavailableException extends RuntimeException {}

    static class OrderService {
        private final InventoryPort inventory;

        OrderService(InventoryPort inventory) {
            this.inventory = inventory;
        }

        String create(String sku, int quantity) {
            if (!inventory.reserve(sku, quantity)) {
                throw new OutOfStockException();
            }
            return UUID.randomUUID().toString();
        }
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 5, 10})
    void validQuantityReservesExactlyOnce(int quantity) {
        InventoryPort inventory = mock(InventoryPort.class);
        when(inventory.reserve("SKU-01", quantity)).thenReturn(true);

        String orderId = new OrderService(inventory)
                .create("SKU-01", quantity);

        assertNotNull(orderId);
        assertFalse(orderId.isBlank());
        verify(inventory).reserve("SKU-01", quantity);
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void noStockProducesBusinessFailure() {
        InventoryPort inventory = mock(InventoryPort.class);
        when(inventory.reserve("SKU-01", 5)).thenReturn(false);

        OrderService service = new OrderService(inventory);

        assertThrows(OutOfStockException.class,
                () -> service.create("SKU-01", 5));
        verify(inventory).reserve("SKU-01", 5);
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void unavailableInventoryDoesNotBecomeSuccess() {
        InventoryPort inventory = mock(InventoryPort.class);
        when(inventory.reserve("SKU-01", 5))
                .thenThrow(new DependencyUnavailableException());

        OrderService service = new OrderService(inventory);

        assertThrows(DependencyUnavailableException.class,
                () -> service.create("SKU-01", 5));
        verify(inventory).reserve("SKU-01", 5);
        verifyNoMoreInteractions(inventory);
    }
}
```

Chạy trong dự án Maven có đủ thư viện test: `mvn test -Dtest=OrderServiceTest` (nếu dự án có Maven Wrapper, có thể dùng `./mvnw test -Dtest=OrderServiceTest`, hoặc `mvnw.cmd` trên Windows). Test không in stdout theo thiết kế; kết quả PASS/FAIL được Maven/JUnit báo trong kết quả test. Không assert chính xác UUID sinh ngẫu nhiên: ở ví dụ này chỉ cần xác nhận ID được tạo khi giữ hàng thành công.

**Giới hạn có chủ đích:** lớp `OrderService` của fixture không chứa HTTP, Bean Validation hoặc repository, nên các test này **không chứng minh** `400`/`409`/`503`, không kiểm tra transaction và không xác minh lưu dữ liệu. Đó là nhiệm vụ của test controller, adapter và integration ở các tầng tương ứng.

## 6. Kiểm tra HTTP và Bean Validation với MockMvc

Trong ứng dụng thật, dùng `@WebMvcTest` và `MockMvc` để kiểm tra input bị chặn trước khi gọi service. Đối với Spring Framework 6.2+ / Spring Boot 3.4+, có thể dùng `@MockitoBean` để thay dependency của controller bằng mock; ở phiên bản cũ hơn, xác định annotation mocking tương ứng mà dự án đang hỗ trợ.

Ví dụ **trích đoạn bên trong một test method đã cấu hình `MockMvc mockMvc` và mock `orderService`**; đây không phải chương trình Java chạy độc lập:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\"SKU-01\",\"quantity\":0}"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(orderService);
```

Ở đây giả định controller có `@Valid` và DTO ở mục 2, nên `quantity=0` bị từ chối trước khi controller gọi service. Cần có static imports cho `post`, `status`, `verifyNoInteractions` và các imports cho `MediaType`. Khi kiểm tra `quantity=11`, JSON thiếu trường, `null`, `sku` chỉ có khoảng trắng hoặc JSON sai cú pháp, thay dữ liệu đầu vào và xác nhận trạng thái/tác dụng phụ tương ứng.

Trường hợp thành công cũng cần HTTP test minh họa, với service stub trả ID cố định để assert ổn định:

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\"SKU-01\",\"quantity\":5}"))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.orderId").isNotEmpty());
```

Đoạn trên giả định controller trả body có thuộc tính JSON `orderId`. Trước khi chạy, cấu hình mock service để trả kết quả thành công; nếu không, mock có thể trả `null` hoặc khiến test bị sai nguyên nhân. Với M14–M18, stub service/adapter ném **ngoại lệ đã được mapping** và kiểm tra `409` hoặc `503` ở biên HTTP. Để test xác minh lỗi thực của dependency HTTP, sử dụng HTTP stub server có thể trả `500`, đóng kết nối hoặc gây timeout; chỉ mock service không chứng minh cấu hình timeout/HTTP client hoạt động đúng.

Ví dụ handler cần có theo hợp đồng mẫu:

- `OutOfStockException` → `409 Conflict`.
- `DependencyUnavailableException` (được adapter phát ra khi timeout, mất kết nối, upstream 5xx hoặc phản hồi lỗi định dạng theo chính sách) → `503 Service Unavailable`.
- Lỗi không xác định → phản hồi server error an toàn theo chính sách chung; không bắt mọi `RuntimeException` rồi biến thành `201` hoặc `400`.

## 7. Cách tạo dữ liệu test để không bỏ sót trường hợp

Bắt đầu từ từng trường trong hợp đồng, liệt kê lớp tương đương và điểm biên. Ví dụ:

| Trường/điều kiện | Lớp hợp lệ | Lớp không hợp lệ | Điểm cần thử |
| --- | --- | --- | --- |
| `sku` | Chuỗi có ít nhất một ký tự không phải khoảng trắng | Thiếu, `null`, rỗng, toàn khoảng trắng | `"SKU-01"`, `""`, `"   "` |
| `quantity` | Số nguyên trong `[1,10]` | Thiếu, `null`, ngoài khoảng, không parse được | `0, 1, 5, 10, 11`, `"abc"` |
| `reserve` | `true` | `false` nghiệp vụ; exception kỹ thuật | success, out-of-stock, timeout, connection error, upstream 5xx |
| Cơ chế lỗi | Phản hồi theo hợp đồng | Ánh xạ sai hoặc lộ lỗi nội bộ | `400`, `409`, `503` và kiểm tra body |

Cách làm:

1. **Trích quy tắc đo được:** trường bắt buộc, kiểu, miền giá trị, response, tương tác phụ thuộc, side effect, chính sách retry và timeout.
2. **Chọn representative của mỗi lớp:** giá trị bình thường, hai biên hợp lệ và hai biên sai; tối thiểu một trường hợp cho mỗi loại lỗi phụ thuộc thực sự khác cách xử lý.
3. **Gắn một oracle rõ ràng:** status, JSON, exception, lời gọi mock, dữ liệu lưu, sự kiện phát, trạng thái transaction.
4. **Gắn tầng test:** controller để kiểm tra parse/validation và contract HTTP; service để kiểm tra nhánh nghiệp vụ; adapter để kiểm tra HTTP client và mapping; integration để kiểm tra database/transaction/serialization/bean wiring.
5. **Chạy rồi đối chiếu ma trận:** giữ ID ổn định, ghi test name, mức ưu tiên, kết quả và lỗi thực tế. Khi yêu cầu đổi, xem lại các dòng chịu ảnh hưởng và expected outcome.

Không cần nhân toàn bộ tổ hợp (mọi `sku` × mọi `quantity` × mọi lỗi kho); điều đó tạo nhiều test trùng mà không tăng đáng kể khả năng bắt lỗi. Dùng một case nền hợp lệ (M01), thay **một yếu tố tại một thời điểm**, sau đó thêm vài tổ hợp có rủi ro cao như M19 để kiểm tra thứ tự validation và gọi phụ thuộc. Với nhiều trường tương tác mạnh, có thể dùng pairwise testing, nhưng những quy tắc nghiệp vụ quan trọng vẫn cần test tường minh.

## 8. Ưu tiên và tổ chức bộ test trong Spring Boot

Có thể đánh mức ưu tiên như sau (điều chỉnh theo rủi ro hệ thống):

- **P0 – chạy mỗi pull request:** M01, M02, M03, M04, M06, M08, M10, M14, M15, M19. Đây là luồng cơ bản, biên chính, thứ tự validation và nhánh lỗi phụ thuộc trọng yếu.
- **P1 – chạy trong CI thường xuyên:** M05, M07, M09, M11, M12, M13, M16, M17, M18 và các trường hợp thay đổi theo contract.
- **Bổ sung khi có yêu cầu:** duplicate requests, idempotency key, retry/backoff, circuit breaker, concurrency, race condition, sự cố database sau khi reserve hàng, rollback/compensation. Chỉ khẳng định expected behavior sau khi chốt quy tắc cho những tính năng này.

Gợi ý phân lớp:

| Tầng | Công cụ phù hợp | Mục đích |
| --- | --- | --- |
| Unit service | JUnit Jupiter + Mockito | Nhánh thành công/hết hàng, số lần gọi và đối số |
| MVC slice | `@WebMvcTest` + `MockMvc` | Status HTTP, JSON, validation, handler |
| Adapter / HTTP client | MockWebServer hoặc WireMock | Upstream 5xx, timeout, lỗi kết nối, parse response |
| Integration | `@SpringBootTest`; Testcontainers nếu cần DB thật | Wiring, giao dịch, ghi dữ liệu, điều kiện rollback |
| Smoke / end-to-end | Ứng dụng chạy trong môi trường kiểm soát | Hợp đồng xuyên tầng và cấu hình thật quan trọng |

Mock hoặc fake nên đủ chặt để test báo lỗi khi gọi sai đối số; tránh để mock mặc định trả `false`/`null` vô tình che một nhánh. Với timeout, dùng stub và timeout client được cấu hình ngắn, có giới hạn; tránh `Thread.sleep` dài khiến test chậm, chập chờn. Dữ liệu chung phải độc lập giữa các test để thứ tự chạy không ảnh hưởng kết quả.

## 9. Các sai lầm thường gặp và cách phát hiện

**Chỉ có happy path:** test `quantity=5` thành công nhưng lỗi so sánh `>=` và `>` ở cận không bị bắt. Khắc phục bằng bộ `0,1,10,11`.

**Nhập sai mà vẫn gọi dependency:** controller thiếu `@Valid` hoặc để service gọi kho trước khi validate. Test `400` kèm `verifyNoInteractions` sẽ bắt được hành vi này.

**Gộp hết lỗi thành 500:** hết hàng (`false`) là từ chối nghiệp vụ, trong khi timeout là lỗi kỹ thuật. Kiểm tra M14 cạnh M15 để bảo đảm `409` và `503` không bị trộn.

**Mock ở tầng quá cao:** stub `OrderService` rồi thấy `503` không chứng minh client có timeout hoặc adapter chuyển đổi upstream 5xx đúng. Cần test riêng adapter với server giả lập và một test tích hợp wiring nếu quan trọng.

**Assert quá yếu hoặc quá cứng:** chỉ assert `201` mà không kiểm tra body, số lần gọi, lưu dữ liệu; hoặc lại assert UUID/timestamp sinh ngẫu nhiên và thông báo lỗi framework biến động. Assert đúng phần của hợp đồng.

**Retry không an toàn:** lời gọi giữ hàng có tác dụng phụ. Nếu timeout xảy ra sau khi kho đã xử lý, retry có thể giữ hàng hai lần. Chỉ kỳ vọng retry khi có idempotency key, chính sách retry và đảm bảo nhất quán được đặc tả và test riêng; không mặc định “timeout thì gọi lại”.

**Lẫn lộn tầng chịu trách nhiệm:** Bean Validation không thay kiểm tra nghiệp vụ như còn hàng hay quyền sở hữu tài nguyên; ngược lại unit service không thể một mình chứng minh status HTTP. Ma trận nên ghi rõ tầng nào chịu trách nhiệm cho từng assertion.

## 10. Mẫu tối thiểu để áp dụng vào endpoint khác

Sao chép cấu trúc hàng sau, rồi điền bằng **hợp đồng thật** của endpoint:

| Test ID | Quy tắc / rủi ro | Given: dữ liệu + trạng thái phụ thuộc | When | Then: phản hồi + trạng thái hệ thống | Tầng | Ưu tiên |
| --- | --- | --- | --- | --- | --- | --- |
| TC-001 | Giá trị hợp lệ thông thường | Input hợp lệ; dependency thành công | Gọi API | Status/body đúng; side effect đúng một lần | MVC + service | P0 |
| TC-002 | Dưới / tại / trên biên | `min-1`, `min`, `max`, `max+1` | Gọi API | Ranh giới được chấp nhận/từ chối chính xác | MVC | P0 |
| TC-003 | Thiếu/sai trường | Field không hợp lệ | Gọi API | Lỗi validation; dependency không được gọi | MVC | P0 |
| TC-004 | Từ chối nghiệp vụ | Dependency trả kết quả nghiệp vụ âm | Gọi API | Lỗi nghiệp vụ; không tạo kết quả thành công | Service + MVC | P0 |
| TC-005 | Lỗi kỹ thuật | Timeout / kết nối / 5xx | Gọi API | Lỗi kỹ thuật theo contract; state nhất quán | Adapter + integration | P0/P1 |

Checklist nghiệm thu ma trận: **(1)** mỗi yêu cầu quan trọng có ít nhất một case; **(2)** điểm `min-1, min, max, max+1` đúng; **(3)** lỗi input chặn side effect; **(4)** thất bại nghiệp vụ khác thất bại kỹ thuật; **(5)** timeout/5xx được kiểm tra ở đúng tầng; **(6)** status, body, lời gọi và trạng thái sau xử lý đều được assert; **(7)** test độc lập, xác định và có thể lặp lại. Khi cả bảy điều kiện đạt, ma trận vừa làm tài liệu thiết kế test, vừa là bản đồ để duy trì regression suite khi API thay đổi.
