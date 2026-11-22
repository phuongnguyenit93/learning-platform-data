# Giới hạn của kiểm tra hợp đồng khi chưa có kiểm thử quy tắc nghiệp vụ

Kiểm thử hợp đồng giúp xác nhận hai thành phần giao tiếp đúng theo thỏa thuận: request có cấu trúc mà provider chấp nhận, response có status, header, media type và body mà consumer mong đợi. Với Spring Boot, springdoc-openapi giúp tạo hợp đồng OpenAPI từ controller, DTO và annotation; MockMvc hoặc WebTestClient giúp kiểm tra HTTP endpoint; Pact và Spring Cloud Contract giúp kiểm tra kỳ vọng giữa consumer và provider.

Tuy nhiên, một API có thể trả về đúng HTTP 201, đúng JSON schema và đúng tên field mà vẫn tính sai tiền, trừ tồn kho sai, cho phép chuyển trạng thái trái quy tắc hoặc xử lý trùng giao dịch. Những lỗi này nằm trong quy tắc nghiệp vụ. Nếu chỉ có kiểm thử hợp đồng, pipeline có thể xanh trong khi hệ thống vẫn đưa ra quyết định sai.

Bài này phân biệt phạm vi của contract test và business-rule test, chỉ ra những lỗ hổng thường gặp, rồi xây dựng bộ kiểm thử nhiều lớp để vừa giữ hợp đồng API ổn định vừa bảo vệ hành vi nghiệp vụ.

## 1. Hợp đồng API trả lời câu hỏi nào?

Hợp đồng mô tả cách một thành phần giao tiếp với thành phần khác. Với HTTP API, hợp đồng thường xác định:

- Path và HTTP method.
- Path parameter, query parameter, header và request body.
- Kiểu dữ liệu, format, required, nullable, range và pattern.
- Status code, response header, media type và response body.
- Cơ chế xác thực, scope và quyền truy cập được công bố.
- Các lỗi mà consumer cần hiểu để xử lý.

Ví dụ, hợp đồng của POST /api/orders có thể quy định:

| Thành phần | Hợp đồng |
| --- | --- |
| Method/path | POST /api/orders |
| Request | productId là string; quantity là integer lớn hơn 0 |
| Thành công | 201 Created và body OrderResponse |
| Thiếu dữ liệu hoặc sai kiểu | 400 Bad Request |
| Không đủ hàng | 409 Conflict |
| Media type | application/json |

springdoc-openapi có thể sinh mô tả này từ controller, DTO, validation annotation và OpenAPI annotation. Nó giúp tài liệu phản ánh mapping được khai báo trong ứng dụng, nhưng việc sinh ra một document hợp lệ không chứng minh implementation đã thực hiện đúng nghiệp vụ.

## 2. Ba loại kiểm tra thường bị gọi chung là contract test

Trong thực tế, cụm từ “kiểm thử hợp đồng” được dùng cho một số mục tiêu khác nhau. Cần phân biệt chúng để biết kết quả xanh có ý nghĩa gì.

| Loại kiểm tra | Điều được xác nhận | Điều chưa được chứng minh |
| --- | --- | --- |
| OpenAPI document validation | Tài liệu JSON/YAML hợp lệ theo phiên bản OpenAPI, có schema và operation có thể phân tích | Ứng dụng thật trả response đúng hoặc xử lý nghiệp vụ đúng |
| Provider contract test | Endpoint provider thực tế đáp ứng status, header và body theo hợp đồng đã công bố | Tất cả quy tắc nghiệp vụ, mọi trạng thái dữ liệu và mọi chuỗi thao tác đều đúng |
| Consumer-driven contract test | Provider đáp ứng những request cụ thể mà consumer đang phụ thuộc | Provider đã được kiểm tra toàn bộ hành vi nghiệp vụ hoặc mọi consumer khác |
| Business-rule test | Quy tắc quyết định và chuyển đổi dữ liệu của nghiệp vụ đúng với yêu cầu | Mọi thành phần HTTP, proxy và hệ thống ngoài đều tích hợp đúng |

Pact mô tả contract test ở cấp tích hợp là kiểm tra từng ứng dụng độc lập để bảo đảm message gửi/nhận phù hợp thỏa thuận giữa consumer và provider. Một Pact thường là tập các request/response cụ thể mà consumer cần. Spring Cloud Contract cũng tập trung vào hợp đồng giữa các ứng dụng và nêu rõ hợp đồng không nhằm mô phỏng toàn bộ hành vi nghiệp vụ.

Do đó, trước khi đọc kết quả CI, hãy hỏi chính xác test đang kiểm tra lớp nào.

## 3. Một ví dụ: response đúng nhưng tổng tiền sai

Giả sử API nhận:

~~~json
{
  "productId": "SKU-100",
  "quantity": 2,
  "couponCode": "SAVE10"
}
~~~

Hợp đồng quy định response:

~~~json
{
  "orderId": "ORD-10482",
  "status": "CONFIRMED",
  "total": 180.00,
  "currency": "VND"
}
~~~

MockMvc test chỉ kiểm tra:

- Request được nhận với JSON hợp lệ.
- Server trả 201 Created.
- Body có orderId, status, total và currency.
- total là number, currency là string.

Nếu implementation tính tổng tiền thành 200.00 thay vì 180.00, test vẫn có thể xanh nếu chỉ kiểm tra kiểu dữ liệu và sự tồn tại của field. JSON hoàn toàn phù hợp schema nhưng kết quả kinh doanh sai.

Các ví dụ tương tự:

| Hành vi sai | Vì sao contract test cơ bản có thể vẫn xanh? |
| --- | --- |
| Áp dụng coupon 10% thành 0% | Response vẫn có total kiểu number |
| Trừ tồn kho hai lần | Response vẫn là 201 và đúng schema |
| Cho phép hủy đơn đã giao | Status và body vẫn đúng cấu trúc |
| Tính phí vận chuyển theo sai khu vực | shippingFee vẫn là decimal hợp lệ |
| Chấp nhận cùng idempotency key nhưng tạo hai đơn | Cả hai response đều có thể đúng schema |
| Cấp quyền đọc đơn của tenant khác | Response có cấu trúc hợp lệ nhưng lộ dữ liệu |
| Ghi trạng thái PAID trước khi thanh toán thành công | Response có thể đúng shape trong khi dữ liệu lưu sai |

Schema mô tả kiểu và ràng buộc cấu trúc. Nó không tự thể hiện mọi công thức, điều kiện thời gian, quyền sở hữu dữ liệu hay thứ tự giao dịch.

## 4. springdoc và OpenAPI kiểm tra được gì?

Với springdoc-openapi, có thể kiểm tra các điểm sau:

1. Controller và functional route mong đợi có được đưa vào OpenAPI document không.
2. HTTP method, path, operationId và tag có đúng không.
3. Request/response schema có đúng kiểu, field, format và required không.
4. Response status và media type có được mô tả đầy đủ không.
5. Security scheme và scope có xuất hiện trong operation cần bảo vệ không.
6. Example có khớp schema và không chứa dữ liệu thật không.
7. OpenAPI document có hợp lệ theo phiên bản được cấu hình không.

Có thể kiểm tra tài liệu được sinh ở /v3/api-docs hoặc YAML endpoint, sau đó lưu artifact và so sánh contract diff trong CI.

Ví dụ kiểm tra tài liệu qua MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesCreateOrderOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/orders'].post").exists());
    }
}
~~~

Test này xác nhận endpoint tài liệu hoạt động và operation mong đợi xuất hiện. Nó chưa xác nhận request tạo đơn thật trả response đúng schema; cần HTTP contract test riêng cho operation đó. Cũng cần lưu ý test chỉ kiểm tra một path/method sẽ không phát hiện các operation khác bị thiếu.

## 5. Kiểm tra HTTP contract bằng MockMvc

MockMvc phù hợp với Spring MVC khi muốn kiểm tra request/response tại tầng web mà không cần mở cổng HTTP thật. Spring Boot hỗ trợ WebMvcTest để kiểm tra riêng web layer hoặc SpringBootTest kết hợp AutoConfigureMockMvc để tải ứng dụng rộng hơn.

Ví dụ controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = orderService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

Ví dụ request DTO:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String productId,
    @Min(1) @Max(100) int quantity,
    String couponCode
) {
}
~~~

Test contract ở tầng HTTP:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderControllerContractTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void createsOrderUsingExpectedHttpContract() throws Exception {
        given(orderService.create(any()))
            .willReturn(new OrderResponse(
                "ORD-10482",
                "CONFIRMED",
                new BigDecimal("180.00"),
                "VND"
            ));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "productId": "SKU-100",
                      "quantity": 2,
                      "couponCode": "SAVE10"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.orderId").value("ORD-10482"))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$.total").value(180.00))
            .andExpect(jsonPath("$.currency").value("VND"));
    }
}
~~~

Test này xác nhận controller gọi service và ánh xạ response đúng giao kèo HTTP. Vì OrderService đã được mock, test không chứng minh service tính đúng coupon, giá hoặc tồn kho. Đây là giới hạn có chủ đích của test ở tầng web.

Các assertion jsonPath ở đây là kiểm tra thủ công những field đã chọn; chúng chưa phải bộ kiểm tra đầy đủ đối chiếu toàn bộ response với OpenAPI schema. Nếu cần kiểm tra response theo document, tích hợp một OpenAPI response validator vào test client và xác nhận validator dùng đúng phiên bản document của ứng dụng. Dù dùng validator nào, việc response khớp schema vẫn không chứng minh công thức giá hoặc workflow đúng.

Nếu dùng Spring Boot phiên bản mới đã chuyển sang MockitoBean, có thể thay MockBean bằng annotation đó. Chọn annotation theo phiên bản Spring Boot của dự án.

## 6. Kiểm tra request validation cũng chưa phải kiểm tra toàn bộ nghiệp vụ

Bean Validation có thể kiểm tra các ràng buộc đơn giản như:

- Field bắt buộc không được trống.
- Số lượng nằm trong khoảng.
- Email đúng định dạng.
- Chuỗi không vượt quá độ dài.
- Ngày có định dạng hợp lệ.

Ví dụ:

~~~java
@Test
void rejectsQuantityOutsideDeclaredRange() throws Exception {
    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "productId": "SKU-100",
                  "quantity": 0
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Test này xác nhận ràng buộc quantity >= 1 được thực thi ở biên HTTP. Nhưng nó không kiểm tra các quy tắc phụ thuộc trạng thái hoặc nhiều field:

- Sản phẩm có được bán tại thời điểm đặt hàng không?
- Khách hàng có đủ hạn mức mua chịu không?
- Coupon còn hiệu lực và có áp dụng cho sản phẩm này không?
- Tổng tiền có vượt giới hạn giao dịch không?
- Số lượng có vượt tồn kho khả dụng sau khi giữ hàng cho đơn khác không?

Các quy tắc này cần test service/domain hoặc integration test với trạng thái dữ liệu phù hợp.

## 7. Viết business-rule test cho service/domain

Quy tắc nghiệp vụ nên được kiểm tra tại nơi quyết định được thực hiện. Với logic thuần như tính giá, có thể dùng unit test nhanh, không cần Spring context.

Ví dụ service tính tổng tiền:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

class OrderPricing {

    BigDecimal calculate(
            BigDecimal unitPrice,
            int quantity,
            BigDecimal discountPercent) {

        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid unit price");
        }
        if (discountPercent.signum() < 0
                || discountPercent.compareTo(new BigDecimal("100")) > 0) {
            throw new IllegalArgumentException("Invalid discount");
        }

        BigDecimal subtotal = unitPrice.multiply(
            BigDecimal.valueOf(quantity));
        BigDecimal discount = subtotal
            .multiply(discountPercent)
            .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);

        return subtotal.subtract(discount)
            .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Test quy tắc:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderPricingTest {

    private final OrderPricing pricing = new OrderPricing();

    @Test
    void appliesTenPercentDiscountToSubtotal() {
        BigDecimal total = pricing.calculate(
            new BigDecimal("100.00"),
            2,
            new BigDecimal("10")
        );

        assertThat(total).isEqualByComparingTo("180.00");
    }

    @Test
    void rejectsQuantityAboveBusinessLimit() {
        assertThatThrownBy(() -> pricing.calculate(
            new BigDecimal("100.00"),
            101,
            new BigDecimal("0")
        )).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Unit test này kiểm tra công thức và giới hạn nghiệp vụ. Nó bổ sung cho MockMvc test: một test xác nhận response HTTP, test còn lại xác nhận quyết định tính tiền.

Không nên chỉ kiểm tra một ví dụ đẹp. Hãy thêm các điểm biên: số lượng tối thiểu/tối đa, discount 0%/100%, số tiền có phần lẻ, rounding, giá âm, currency không hỗ trợ và coupon hết hạn.

## 8. Kiểm tra quy tắc chuyển trạng thái

Một schema có thể khai báo status là enum PENDING, CONFIRMED, SHIPPED, CANCELLED. Schema này không thể hiện đầy đủ trạng thái nào được phép chuyển sang trạng thái nào.

Ví dụ quy tắc:

| Trạng thái hiện tại | Lệnh | Trạng thái mới | Kết quả |
| --- | --- | --- | --- |
| PENDING | confirm | CONFIRMED | Cho phép |
| CONFIRMED | ship | SHIPPED | Cho phép khi đã giữ hàng |
| PENDING | cancel | CANCELLED | Cho phép |
| SHIPPED | cancel | CANCELLED | Từ chối |
| CANCELLED | confirm | CONFIRMED | Từ chối |

Test domain nên kiểm tra cả chuyển hợp lệ và không hợp lệ:

~~~java
@Test
void cannotCancelShippedOrder() {
    Order order = Order.shipped("ORD-10482");

    assertThatThrownBy(order::cancel)
        .isInstanceOf(InvalidOrderTransitionException.class);

    assertThat(order.getStatus()).isEqualTo(OrderStatus.SHIPPED);
}
~~~

Contract test có thể xác nhận trường hợp từ chối trả 409 Conflict với error schema ổn định. Business-rule test xác nhận lệnh cancel không thay đổi trạng thái và không hoàn tồn kho sai.

## 9. Quy tắc phụ thuộc database cần integration test

Không phải quy tắc nào cũng có thể kiểm tra bằng unit test thuần. Một số quyết định phụ thuộc vào transaction, constraint, lock hoặc trạng thái đồng thời trong database.

Ví dụ giữ hàng:

1. Tồn kho hiện tại là 5.
2. Hai request đồng thời mỗi request đặt 4 sản phẩm.
3. Chỉ một request được giữ hàng thành công.
4. Tồn kho còn lại không âm.
5. Request còn lại nhận lỗi nghiệp vụ được ánh xạ thành response đã công bố.

Unit test với repository mock có thể xác nhận service gọi reserve(4), nhưng không chứng minh SQL update nguyên tử hoặc transaction isolation hoạt động đúng. Cần integration test với database tương ứng, thường chạy bằng Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class InventoryReservationIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // Khởi tạo ứng dụng với datasource trỏ vào container,
    // seed tồn kho = 5, sau đó gửi hai lệnh reserve(4)
    // đồng thời và xác nhận chỉ một lệnh thành công.
}
~~~

Đoạn trên phác họa cấu trúc test; cấu hình datasource và đồng bộ thread cần được bổ sung theo ứng dụng. Điều quan trọng là test phải dùng database thật của loại đang triển khai để xác minh constraint, lock và transaction.

## 10. Kiểm tra idempotency và side effect

Một API có thể công bố header Idempotency-Key trong OpenAPI. Schema và response không tự bảo đảm server thực thi tính idempotent.

Business/integration tests nên kiểm tra:

- Cùng key và cùng payload không tạo thêm đơn hàng hoặc thanh toán.
- Cùng key nhưng payload khác được từ chối theo chính sách.
- Retry sau timeout trả lại kết quả đã lưu thay vì lặp side effect.
- Outbox/event chỉ được ghi một lần theo transaction.
- Nếu downstream trả lỗi, trạng thái và khả năng retry đúng với chính sách.

Contract test có thể kiểm tra header được chấp nhận và response duplicate có status/body đã thỏa thuận. Integration test mới xác nhận số bản ghi, số lần gọi payment gateway hoặc event được phát.

## 11. Consumer-driven contract test kiểm tra kỳ vọng của consumer

Pact và Spring Cloud Contract hữu ích khi nhiều service do các nhóm khác nhau phát triển. Consumer viết các tương tác mà nó thực sự sử dụng; provider chạy verification để xác nhận response đáp ứng những tương tác đó.

Ví dụ consumer shipping-service chỉ cần:

~~~http
GET /api/orders/ORD-10482
Accept: application/json
~~~

Và kỳ vọng tối thiểu:

~~~json
{
  "orderId": "ORD-10482",
  "status": "CONFIRMED"
}
~~~

Pact provider verification phát lại request và kiểm tra response phù hợp contract. Điều này giúp phát hiện provider đổi tên field hoặc thay đổi status mà consumer đang dùng.

Nhưng consumer không yêu cầu kiểm tra công thức giá, vì nó không dùng total. Provider có thể tính sai giá mà Pact vẫn xanh. Đây không phải lỗi của Pact; đó là phạm vi mà contract đã chọn.

Provider state giúp chuẩn bị điều kiện trước mỗi interaction, ví dụ một đơn hàng ORD-10482 đang tồn tại và ở trạng thái CONFIRMED. Provider state không phải bộ kiểm thử toàn bộ quy tắc chuyển trạng thái.

## 12. Spring Cloud Contract cũng không thay thế business tests

Spring Cloud Contract hỗ trợ producer-driven và consumer-driven contracts, sinh stub và test provider. Có thể dùng nó để xác nhận:

- Request phù hợp contract.
- Response có status/header/body theo thỏa thuận.
- Consumer stub phản ánh đúng response provider.
- Thay đổi provider không phá vỡ các consumer đã công bố contract.

Tài liệu Spring Cloud Contract nói rõ contract test không nhằm viết toàn bộ hành vi nghiệp vụ vào contract. Ví dụ một use case fraud có thể có nhiều lý do; contract có thể chỉ xác nhận một trường hợp chấp nhận và một trường hợp từ chối. Các quy tắc fraud chi tiết thuộc bộ test nghiệp vụ.

Không nên biến contract thành hàng trăm kịch bản nghiệp vụ nếu mục tiêu là xác nhận giao tiếp giữa service. Hãy giữ contract tập trung vào các tương tác thực sự được tích hợp.

## 13. Dùng WebTestClient cho Spring WebFlux

Với WebFlux, WebTestClient kiểm tra endpoint reactive. Nó có thể chạy trong mock web environment hoặc kết nối tới server thật.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OrderWebFluxContractTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void returnsOrderUsingJsonContract() {
        webTestClient.get()
            .uri("/api/orders/ORD-10482")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.orderId").isEqualTo("ORD-10482")
            .jsonPath("$.status").isEqualTo("CONFIRMED");
    }
}
~~~

Test này kiểm tra response HTTP của WebFlux. Nó vẫn cần business tests riêng để kiểm tra vì sao đơn hàng được xác nhận, liệu tồn kho đã giữ thành công hay điều kiện thanh toán đã thỏa mãn.

Import AutoConfigureWebTestClient trong ví dụ dùng package của Spring Boot 3.x. Với Spring Boot 4.x, annotation được chuyển sang package org.springframework.boot.webtestclient.autoconfigure; hãy dùng package theo phiên bản Boot trong dự án.

Spring Boot phân biệt mock web environment với RANDOM_PORT chạy embedded server thật. MockMvc/WebTestClient mock-based nhanh hơn nhưng không bao phủ mọi hành vi ở tầng server/container hoặc proxy. Khi cần xác minh TLS, compression, servlet container, network timeout hoặc reverse proxy, hãy bổ sung test với server và hạ tầng phù hợp.

## 14. Những quy tắc mà schema khó thể hiện đầy đủ

OpenAPI có thể mô tả nhiều constraint như minimum, maximum, pattern, enum, required, format và composition. Tuy vậy, một số quy tắc cần dữ liệu hoặc lịch sử để đánh giá:

| Quy tắc | Vì sao cần test nghiệp vụ |
| --- | --- |
| Coupon chỉ dùng một lần cho mỗi khách hàng | Phụ thuộc lịch sử sử dụng và transaction |
| Người mua chỉ hủy đơn trong 15 phút | Phụ thuộc thời gian và trạng thái hiện tại |
| Tổng tiền phải bằng giá từng dòng cộng thuế và phí | Phụ thuộc công thức và rounding |
| Người dùng chỉ xem dữ liệu tenant của mình | Phụ thuộc identity và ownership |
| Chỉ một request đồng thời giữ được số lượng cuối | Phụ thuộc concurrency và database |
| Hoàn tiền không vượt số tiền đã thu | Phụ thuộc trạng thái thanh toán tích lũy |
| Chuyển trạng thái phải theo workflow | Phụ thuộc trạng thái trước và sự kiện |
| Phí giao hàng thay đổi theo vùng và khối lượng | Phụ thuộc bảng giá và dữ liệu đầu vào |

Có thể mô tả một phần điều kiện bằng schema hoặc description, nhưng mô tả không thực thi quy tắc. Phải có test gọi logic hoặc endpoint với trạng thái dữ liệu thích hợp.

## 15. Ma trận test cho API tạo đơn hàng

Một bộ test cân bằng có thể được tổ chức như sau:

| Tình huống | OpenAPI/contract | Business unit test | Integration test |
| --- | --- | --- | --- |
| Request thiếu productId | Xác nhận 400 và error schema | Không cần nếu chỉ là validation framework | Chỉ khi error handler cần DB |
| quantity nhỏ hơn 1 | Xác nhận 400 | Kiểm tra giới hạn nếu domain cũng bảo vệ | Không bắt buộc |
| Coupon hợp lệ 10% | Xác nhận request/response shape | Kiểm tra công thức discount | Có thể kiểm tra giá lấy từ DB |
| Coupon hết hạn | Xác nhận 422/409 và error body | Kiểm tra thời gian hiệu lực | Kiểm tra dữ liệu coupon và clock |
| Tồn kho không đủ | Xác nhận 409 và error body | Kiểm tra nhánh từ chối | Kiểm tra update/lock DB |
| Chuyển trạng thái sai | Xác nhận response lỗi | Kiểm tra state machine | Kiểm tra trạng thái lưu không đổi |
| Gửi lại idempotency key | Xác nhận status/body retry | Kiểm tra logic key | Xác nhận không tạo duplicate record/event |
| User tenant A đọc đơn tenant B | Xác nhận 403/404 theo chính sách | Kiểm tra authorization rule | Kiểm tra query có tenant filter |
| Hai request giữ hàng đồng thời | Xác nhận một success, một conflict | Test logic cạnh tranh ở mức phù hợp | Kiểm tra transaction/constraint thật |

Ma trận này giúp phát hiện khoảng trống. Không cần lặp lại mọi scenario ở mọi lớp; mỗi test nên đặt ở lớp có thể xác minh nguyên nhân và kết quả một cách đáng tin cậy.

## 16. Các dấu hiệu cho thấy test suite chỉ kiểm tra hình thức

Hãy xem lại bộ test nếu có những dấu hiệu sau:

- Tất cả controller test đều mock toàn bộ service và chỉ kiểm tra status().isOk().
- Không có test cho giá trị biên hoặc nhánh từ chối.
- Không có test xác nhận trạng thái dữ liệu sau một thao tác.
- Test chỉ kiểm tra JSON có field mà không kiểm tra giá trị có ý nghĩa.
- Mọi test database đều dùng repository mock, kể cả logic phụ thuộc transaction.
- Không có kiểm tra authorization theo chủ sở hữu hoặc tenant.
- Không có test retry, idempotency hoặc request đồng thời cho API tài chính/đặt hàng.
- Contract được sinh từ controller nhưng chưa có test đối chiếu response runtime.
- Consumer contract chỉ bao phủ một consumer nhưng pipeline coi đó là bằng chứng cho tất cả consumer.

Test xanh chỉ có giá trị trong phạm vi assertion đã viết. Không nên suy rộng kết quả của một lớp test sang lớp khác.

## 17. Dùng mutation testing để tìm assertion yếu

Mutation testing cố tình thay đổi một phần implementation, ví dụ:

- Bỏ phép trừ discount.
- Đổi > thành >= ở điều kiện giới hạn.
- Bỏ kiểm tra quyền sở hữu.
- Luôn trả CONFIRMED bất kể trạng thái thanh toán.
- Bỏ kiểm tra idempotency key.

Nếu test suite vẫn xanh sau mutation, có thể test chưa quan sát quy tắc quan trọng hoặc chưa tạo được trạng thái cần thiết.

Mutation testing không thay thế phân tích yêu cầu. Nó giúp kiểm tra xem test hiện tại có đủ nhạy với các lỗi mà nhóm quan tâm hay không. Chọn mutation ở những quyết định nghiệp vụ có rủi ro cao thay vì chạy mọi mutation trên toàn codebase ngay từ đầu.

## 18. Quy trình CI nên kiểm tra nhiều lớp

Một pipeline cho API Spring Boot có thể chạy theo thứ tự:

1. Biên dịch và unit tests cho domain/service rules.
2. Test validation và controller mapping bằng MockMvc hoặc WebTestClient.
3. Sinh OpenAPI bằng springdoc và xác nhận document hợp lệ.
4. Kiểm tra operation, schema, security và response metadata quan trọng.
5. Chạy provider contract tests hoặc consumer-driven verification.
6. Chạy integration tests với database/message broker thật hoặc Testcontainers cho quy tắc phụ thuộc hạ tầng.
7. Chạy test authorization, idempotency và concurrency theo rủi ro.
8. So sánh OpenAPI contract với bản phát hành trước và review breaking changes.
9. Chỉ sau khi các lớp kiểm tra phù hợp đều đạt mới đóng gói artifact.

Không phải mọi dự án cần Pact, Spring Cloud Contract, Testcontainers và mutation testing cùng lúc. Chọn công cụ theo kiến trúc và rủi ro. Một service nội bộ đơn giản có thể chỉ cần OpenAPI validation, MockMvc và domain tests; hệ thống nhiều consumer hoặc có giao dịch tài chính cần thêm provider/consumer verification và integration tests.

## 19. Chẩn đoán khi contract test xanh nhưng người dùng vẫn gặp lỗi

| Hiện tượng | Điều cần kiểm tra tiếp |
| --- | --- |
| Client parse JSON thành công nhưng hiển thị sai tiền | Công thức giá, thuế, discount, rounding |
| API trả 201 nhưng đơn không thể giao | Workflow, tồn kho, trạng thái thanh toán |
| Consumer contract pass nhưng tích hợp production lỗi | Provider state, version contract, auth, network và downstream |
| Schema đúng nhưng field luôn rỗng | Mapping DTO, query, serialization và business state |
| User nhận dữ liệu của tenant khác | Authorization, repository query và isolation |
| Retry tạo giao dịch trùng | Idempotency storage, transaction và race condition |
| Test mock pass nhưng production DB lỗi | Constraint, transaction isolation, locking và migration |
| Test MockMvc pass nhưng proxy lỗi | Embedded server, forwarded headers, TLS, CORS và timeout |

Hãy truy ngược theo lớp: request có vào đúng handler không, validation có chạy không, service đưa ra quyết định gì, repository ghi gì và response mapper chuyển kết quả ra sao. Log và trace nên dùng correlation ID; không ghi token hoặc dữ liệu cá nhân nhạy cảm chỉ để debug.

## 20. Checklist review test suite

- [ ] OpenAPI document parse được và có đủ operation mong đợi.
- [ ] Request/response status, media type, header và schema được kiểm tra.
- [ ] Có test request sai cấu trúc và validation failure.
- [ ] Controller test không bị hiểu nhầm là business test khi service đã mock.
- [ ] Mỗi quy tắc nghiệp vụ quan trọng có test đúng tại domain/service.
- [ ] Có kiểm tra giá trị biên, nhánh từ chối và state transition.
- [ ] Quy tắc phụ thuộc database được kiểm tra bằng integration test phù hợp.
- [ ] Quyền truy cập và tenant isolation có test âm tính.
- [ ] Retry/idempotency/concurrency được kiểm tra khi nghiệp vụ cần.
- [ ] Consumer contract được xác minh ở provider.
- [ ] Contract test không bị dùng thay cho toàn bộ business behavior.
- [ ] CI phân biệt rõ lỗi document, lỗi HTTP contract và lỗi nghiệp vụ.

Một hợp đồng API tốt giúp các service giao tiếp ổn định. Một bộ kiểm thử tốt còn phải chứng minh service đưa ra quyết định đúng với dữ liệu và trạng thái thực tế. Hãy giữ contract test tập trung vào giao tiếp, đồng thời bảo vệ các quy tắc quan trọng bằng unit, integration và scenario tests.

## Tài liệu tham khảo

- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Cloud Contract – Introducing Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/getting-started/introducing-spring-cloud-contract.html)
- [Spring Cloud Contract – Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/index.html)
- [Pact – Introduction to Contract Testing](https://docs.pact.io/)
- [Pact – How Pact Works and Provider States](https://docs.pact.io/getting_started/how_pact_works)
- [Pact – Verifying Pacts](https://docs.pact.io/getting_started/verifying_pacts)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)
