# Kiểm thử hợp đồng do bên sử dụng định hướng

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Chiến lược kiểm thử.  
> **Trọng tâm:** Consumer-Driven Contract Testing (CDC) giúp các dịch vụ phát triển, kiểm thử và triển khai tương đối độc lập bằng cách xác minh rằng phía cung cấp API vẫn đáp ứng những tương tác mà bên sử dụng thực sự cần.

## 1. Bài toán trong microservices

Giả sử hệ thống bán hàng có ba dịch vụ:

- **Order Service** nhận yêu cầu tạo đơn và cần kiểm tra tồn kho.
- **Inventory Service** cung cấp API kiểm tra sản phẩm và số lượng còn lại.
- **Notification Service** tiêu thụ sự kiện đơn hàng đã tạo để gửi thông báo.

Order gọi Inventory qua HTTP:

~~~http
GET /api/inventory/BOOK-101 HTTP/1.1
Accept: application/json
~~~

Order chỉ cần một phần nhỏ trong response của Inventory:

~~~json
{
  "sku": "BOOK-101",
  "available": 8,
  "warehouse": "HCM-01",
  "lastReconciledAt": "2026-11-12T02:00:00Z"
}
~~~

Trong code Order, hai trường **sku** và **available** là thiết yếu. Một ngày, nhóm Inventory đổi tên **available** thành **availableQuantity**. Các unit test của hai dịch vụ vẫn có thể xanh vì mỗi nhóm chỉ kiểm thử code của mình. Sau khi triển khai, Order không đọc được số lượng tồn kho và không tạo đơn được.

Nếu dựa chủ yếu vào end-to-end test trên toàn bộ hệ thống, đội phát triển phải khởi động nhiều service, database và môi trường tích hợp; test có thể chậm, không ổn định, tốn công thiết lập dữ liệu và chỉ phát hiện sự cố muộn.

**Consumer-Driven Contract Testing** cho phép Order mô tả chính xác yêu cầu mà nó dựa vào từ Inventory. Inventory chạy verification để chứng minh bản triển khai mới còn đáp ứng các yêu cầu đó trước khi phát hành.

**Ý tưởng chính:** Consumer phát biểu “Tôi gọi như thế này và cần provider trả như thế kia”; provider chứng minh “Tôi vẫn có khả năng đáp ứng tương tác đó”.

## 2. Định nghĩa: Consumer, Provider và Contract

Trong một tương tác giữa hai microservice:

- **Consumer:** ứng dụng sử dụng dữ liệu, API hoặc sự kiện từ dịch vụ khác. Ở ví dụ trên, Order là consumer của Inventory.
- **Provider:** dịch vụ cung cấp dữ liệu/API hoặc sinh ra message. Inventory là provider.
- **Contract:** tập hợp kỳ vọng có thể kiểm thử tại ranh giới giao tiếp giữa consumer và provider.
- **Consumer test:** kiểm tra code consumer hoạt động đúng khi nhận response/message thỏa contract, thường bằng mock server hoặc message fixture sinh từ contract.
- **Provider verification:** chạy tương tác contract với provider thật trong một môi trường test có kiểm soát, rồi xác nhận provider đáp ứng kỳ vọng.
- **Contract artifact:** bản biểu diễn có thể chia sẻ/version hóa các tương tác kỳ vọng, ví dụ file Pact.
- **Contract Broker/repository:** nơi các đội công bố contract, verification result và quan hệ giữa version, environment, deployment.

Các vai trò tương đối theo từng tương tác. Order là **consumer** khi gọi Inventory nhưng có thể là **provider** khi xuất API cho Web BFF hoặc phát sự kiện **OrderCreated** cho Notification.

Cùng một provider có thể phục vụ nhiều consumer. Mỗi consumer có thể cần các trường hoặc hành vi khác nhau. Vì vậy việc “provider test pass” chưa đủ nếu provider test không biết yêu cầu của những consumer đang chạy.

~~~mermaid
flowchart LR
    O[Order Service Consumer] -->|Tạo contract| P[Pact artifact]
    P -->|Công bố| B[Contract Broker]
    B -->|Hợp đồng cần xác minh| V[Provider verification]
    I[Inventory Service Provider] --> V
    V -->|Kết quả theo version| B
    B --> G{Compatible to deploy?}
    G -->|Yes| D[Deploy]
    G -->|No / Unknown| H[Giữ bản phát hành]
~~~

Các thành phần có thể được hiện thực khác nhau tùy công cụ; đây là mô hình khái niệm, không phải kiến trúc bắt buộc.

## 3. “Do bên sử dụng định hướng” nghĩa là gì?

**Consumer-driven** chỉ ra ai xác định kỳ vọng quan trọng của một interaction: **những ứng dụng thực tế đang dùng API**.

Thay vì provider tạo bộ kiểm tra khổng lồ cho mọi trường và yêu cầu tất cả client phải khớp toàn bộ response, consumer khai báo những gì mình dùng. Với Order, có thể là:

- Gửi **GET /api/inventory/{sku}**.
- Gửi hoặc nhận các header liên quan tới protocol đã thỏa thuận.
- Khi SKU tồn tại, nhận HTTP **200**.
- Trong body có **sku** là chuỗi và **available** là số nguyên.
- Khi SKU không tồn tại, nhận một contract lỗi được thống nhất, ví dụ HTTP **404** và error code rõ ràng.

Nếu provider thêm trường **warehouseZone** mà Order không dùng, contract của Order thường vẫn pass. Nếu provider bỏ **available**, verification thất bại vì thay đổi ảnh hưởng đến nhu cầu thật.

Điều đó tạo sự cân bằng:

1. **Consumer có tiếng nói** về các điều kiện nó thật sự dựa vào.
2. **Provider có tự do tiến hóa** những chi tiết không bị consumer sử dụng.
3. **Cả hai cùng thấy bằng chứng tương thích** theo version thay vì trao đổi bằng lời hoặc giả định.

Consumer không được viết contract tùy ý để ép provider triển khai một khả năng chưa được thống nhất. Contract vẫn là **thỏa thuận giữa các nhóm** về endpoint, trạng thái, trường dữ liệu và chính sách lỗi.

## 4. CDC khác gì với các loại kiểm thử khác?

| Loại kiểm thử | Câu hỏi chính | Đặc điểm | Giới hạn |
| --- | --- | --- | --- |
| **Unit test** | Hàm/lớp xử lý logic đúng không? | Nhanh, cô lập implementation | Không chứng minh API giữa hai service tương thích |
| **Component/service test** | Service có hoạt động với dependency giả lập và database test không? | Kiểm tra phạm vi rộng hơn unit | Stub có thể khác provider thực |
| **Consumer contract test** | Consumer có gửi request và xử lý response theo kỳ vọng không? | Ghi lại tương tác mà client code sử dụng | Một mình consumer test không xác minh provider thực |
| **Provider contract verification** | Provider có thỏa các tương tác đã công bố không? | Phát hiện thay đổi API làm gãy consumer | Không đo đầy đủ toàn bộ business flow |
| **Integration test** | Các thành phần thực kết nối và phối hợp được không? | Thử network, DB, security hoặc middleware thật | Chậm/phức tạp hơn test cô lập |
| **End-to-end test** | Luồng người dùng xuyên nhiều service có thành công không? | Kiểm tra hành vi tổng thể | Khó tìm nguyên nhân, tốn công chuẩn bị môi trường |
| **Performance/security test** | SLO, tải, phân quyền và bảo vệ có đúng không? | Đánh giá các thuộc tính phi chức năng | CDC không thay thế những kiểm tra này |

CDC được dùng **bổ trợ**, không xóa sạch integration hoặc end-to-end test. Một contract HTTP pass chỉ chứng minh giao thức tại boundary; nó không đảm bảo hệ thống giữ tồn kho nhất quán khi nhiều order cùng chạy, không đảm bảo p99 latency, không chứng minh dữ liệu customer không bị truy cập sai quyền.

Trong chiến lược kiểm thử microservices, có thể dùng nhiều unit/component/contract test chạy thường xuyên và một tập nhỏ end-to-end test cho luồng quan trọng, cùng các bài security, performance và resilience theo nhu cầu.

## 5. Contract chứa những gì?

Với HTTP API, một interaction contract thường có:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Provider state** | “SKU BOOK-101 tồn tại và còn 3 sản phẩm” | Điều kiện dữ liệu trước khi verify |
| **Request method** | GET | Consumer thực sự sử dụng phương thức nào |
| **Path/query** | /api/inventory/BOOK-101 | Địa chỉ và tham số được gửi |
| **Headers cần thiết** | Accept: application/json | Điều kiện protocol mà consumer phụ thuộc |
| **Request body** | JSON tạo reservation | Cấu trúc lệnh gửi sang provider |
| **Response status** | 200 hoặc 404 | Cách consumer phân nhánh thành công/thất bại |
| **Response headers** | Content-Type | Thông tin consumer cần để parse |
| **Response body matchers** | sku là string, available là integer | Shape và type thực sự sử dụng |
| **Interaction description** | “Read stock for existing SKU” | Mục đích dễ hiểu khi gặp lỗi |
| **Contract version** | Commit SHA/version của consumer | Contract thuộc bản consumer nào |

Với message/event contract, hình dạng có thể gồm **message body**, metadata, content type, schema version, key/headers và điều kiện sinh message. Cơ chế verify sẽ khác HTTP vì consumer không trực tiếp gọi endpoint đồng bộ.

### 5.1. Kỳ vọng nên đủ chặt và đủ linh hoạt

**Quá chặt:** yêu cầu response có đúng mọi trường của provider, timestamp cố định, thứ tự property JSON cố định hoặc request ID cố định. Như vậy thay đổi không ảnh hưởng consumer cũng làm test fail.

**Quá lỏng:** chỉ kiểm tra HTTP 200 hoặc JSON là object bất kỳ. Lúc đó provider có thể xóa trường quan trọng mà contract vẫn pass.

Ví dụ matcher hợp lý: **sku** là chuỗi theo định dạng SKU, **available** là số nguyên không âm, **status** thuộc tập giá trị mà consumer hiểu. Không nhất thiết assert **lastReconciledAt** nếu Order không dùng.

Tuy nhiên một số giá trị **phải match chính xác** vì quyết định hành vi, ví dụ status code 404, error code **SKU_NOT_FOUND**, media type hoặc enum nghiệp vụ. Sự linh hoạt không được làm mất ý nghĩa contract.

## 6. Quy trình CDC từ góc nhìn Consumer

Giả sử nhóm Order đang viết client gọi Inventory. Luồng phát triển:

1. Thiết kế interaction từ **nhu cầu của Order**, gồm case thành công, không tìm thấy SKU và lỗi cần xử lý.
2. Dùng công cụ hợp đồng như **Pact** định nghĩa request và response matcher.
3. Chạy **consumer test** với mock server sinh từ contract.
4. Kiểm tra client thật của Order parse và xử lý response đúng; không chỉ kiểm tra một hàm giả.
5. Sinh **Pact artifact**, gắn với version/build của Order.
6. Công bố artifact lên Broker hoặc kho được chọn.
7. CI của Inventory lấy contract phù hợp và chạy **provider verification**.
8. Kết quả verification được công bố cùng version provider.
9. Trước khi triển khai, kiểm tra version consumer/provider chuẩn bị chạy có tương thích với nhau không.

Một consumer có thể phát triển trước khi provider triển khai xong endpoint mới. Test sẽ chứng minh consumer hợp lý đối với contract đã định nghĩa, nhưng **chỉ khi provider verification thành công** mới có bằng chứng rằng provider có thể phục vụ interaction đó.

## 7. Ví dụ xuyên suốt: Order gọi Inventory

### 7.1. Hợp đồng API được hai nhóm thống nhất

Provider công khai endpoint:

~~~http
GET /api/inventory/BOOK-101 HTTP/1.1
Accept: application/json
~~~

Response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "BOOK-101",
  "available": 3
}
~~~

Khi SKU không tồn tại:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "SKU_NOT_FOUND",
  "message": "SKU does not exist"
}
~~~

Trong ứng dụng thật, trạng thái **không tìm thấy SKU** khác với **tồn kho bằng 0**. Nếu SKU có thật nhưng đã hết hàng, provider có thể trả 200 với available=0 theo contract đã thỏa thuận; không nên dùng 404 cho mọi trường hợp không có hàng.

Order cần xử lý cả nhánh **200** và **404**. Nếu chỉ định nghĩa contract thành công, provider có thể thay đổi response lỗi mà CI không phát hiện.

### 7.2. Client Java dùng RestClient

Ví dụ sử dụng Spring Boot 3.x / Spring Framework 6.1+:

~~~java
import org.springframework.web.client.RestClient;

public final class InventoryClient {
    private final RestClient http;

    public InventoryClient(String baseUrl) {
        this.http = RestClient.builder()
            .baseUrl(baseUrl)
            .build();
    }

    public InventoryView findStock(String sku) {
        return http.get()
            .uri("/api/inventory/{sku}", sku)
            .retrieve()
            .body(InventoryView.class);
    }

    public record InventoryView(String sku, int available) {}
}
~~~

Đây là ví dụ tối giản để tập trung vào contract. Trong production cần cấu hình **timeout, TLS, authentication, client error mapping, tracing và bulkhead/retry policy** theo thiết kế hệ thống. Không dùng lại đoạn client đơn giản này như một bộ HTTP client production hoàn chỉnh.

Với Spring RestClient, lỗi 4xx/5xx theo mặc định được xử lý qua cơ chế status handler/exception; để kiểm thử 404 như một nhánh nghiệp vụ, cần triển khai mapping cụ thể của ứng dụng trước khi viết consumer test tương ứng.

### 7.3. Tạo consumer test với Pact JVM

Một minh họa theo kiểu API của **Pact JVM JUnit 5**. Tên package, annotation và cấu hình build có thể khác theo phiên bản Pact đang được sử dụng; giữ đồng nhất dependency Pact plugin và Pact JVM trong dự án.

~~~java
import au.com.dius.pact.consumer.MockServer;
import au.com.dius.pact.consumer.dsl.PactDslWithProvider;
import au.com.dius.pact.consumer.junit5.PactConsumerTestExt;
import au.com.dius.pact.consumer.junit5.PactTestFor;
import au.com.dius.pact.core.model.RequestResponsePact;
import au.com.dius.pact.core.model.annotations.Pact;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(PactConsumerTestExt.class)
@PactTestFor(providerName = "inventory-service")
class InventoryClientContractTest {

    @Pact(consumer = "order-service")
    RequestResponsePact stockContract(PactDslWithProvider pact) {
        return pact
            .given("SKU BOOK-101 has 3 items available")
            .uponReceiving("stock lookup for BOOK-101")
                .path("/api/inventory/BOOK-101")
                .method("GET")
            .willRespondWith()
                .status(200)
                .headers(Map.of("Content-Type", "application/json"))
                .body("""
                    {
                      "sku": "BOOK-101",
                      "available": 3
                    }
                    """)
            .toPact();
    }

    @Test
    @PactTestFor(pactMethod = "stockContract")
    void parsesStockResponse(MockServer mockServer) {
        InventoryClient client =
            new InventoryClient(mockServer.getUrl());

        InventoryClient.InventoryView value =
            client.findStock("BOOK-101");

        assertEquals("BOOK-101", value.sku());
        assertEquals(3, value.available());
    }
}
~~~

Điều quan trọng trong test:

- **@Pact** định nghĩa interaction do Order mong đợi.
- **MockServer** nhận lời gọi thực từ InventoryClient và trả response của contract.
- Test gọi **code client thực** của Order; nếu client gửi sai method/path hoặc không parse được body, test thất bại.
- Provider state “SKU BOOK-101 has 3 items available” mô tả tiền điều kiện cho phía Inventory khi chạy provider verification; consumer mock server không yêu cầu database thật có dữ liệu này.
- Sau khi consumer test pass, Pact artifact phản ánh tương tác và matchers được khai báo.
- Trong ví dụ trên, body dùng giá trị cố định để dễ hiểu; contract thực nên khai báo **type matcher** cho dữ liệu thay đổi, nhưng vẫn giữ exact match cho các giá trị thực sự ràng buộc nghiệp vụ.
- Đây là **một interaction thành công**. Cần thêm interaction/test cho các nhánh lỗi mà consumer thật sử dụng.

Nếu test gọi trực tiếp MockServer bằng một HTTP request tự viết trong test nhưng **không đi qua InventoryClient production**, có nguy cơ contract test vẫn xanh trong khi code client thực gửi một request khác. Tốt nhất dùng đúng adapter outbound của application.

### 7.4. Khai báo matcher thay vì đóng đinh tất cả dữ liệu

Ví dụ một contract response có thể mang ý nghĩa:

~~~text
Response HTTP 200
Content-Type: application/json
Body:
  $.sku        -> string, ví dụ "BOOK-101"
  $.available  -> integer >= 0, ví dụ 3
Các trường response khác: không bị ràng buộc nếu consumer không dùng
~~~

Pact cho phép mô tả kiểu, regex hoặc generator theo phiên bản thư viện. Ví dụ dữ liệu trong body chỉ giúp hình dung và sinh mock response; **matcher** mới là quy tắc provider verification áp dụng. Không nên coi mọi giá trị ví dụ là bất biến.

Chọn matcher:

- Với **available**, integer type hoặc miền giá trị phù hợp contract.
- Với **sku**, định dạng SKU nếu ứng dụng thực sự dựa vào.
- Với **currency**, giá trị enum chính xác nếu client chỉ hỗ trợ một tập hữu hạn.
- Với **requestId** và timestamp do server tạo, thường không so sánh bằng một chuỗi cố định.
- Với **error code**, match chính xác khi code điều khiển nhánh xử lý.
- Với danh sách, chỉ ràng buộc shape, cardinality hoặc sort order khi consumer phụ thuộc.

## 8. Provider verification: xác minh bằng service thật

Provider verification khác với chạy một mock server phía consumer. Đây là lúc **Inventory Service thật** phải trả response khớp contract dưới dữ liệu đã chuẩn bị.

Các bước cơ bản:

1. CI của Inventory tải những contract từ consumer/version liên quan.
2. Khởi động Inventory Service ở chế độ test với dependency đã được kiểm soát.
3. Thiết lập **provider state** cho từng interaction, ví dụ tạo SKU BOOK-101 còn 3 item.
4. Công cụ contract gửi request trong contract đến provider thật.
5. So sánh response theo status, header và body matcher.
6. Lưu/report verification result với **provider version** và **consumer pact version**.

Ví dụ provider state:

~~~java
import au.com.dius.pact.provider.junitsupport.State;
import org.springframework.beans.factory.annotation.Autowired;

public class InventoryProviderStates {
    @Autowired
    private InventoryTestFixture testFixture;

    @State("SKU BOOK-101 has 3 items available")
    public void skuAvailable() {
        testFixture.setStock("BOOK-101", 3);
    }
}
~~~

**InventoryTestFixture** là fixture service giả định thuộc test source; ví dụ chưa bao gồm implementation. Trong hệ thống thật, provider-state callback cần được nối đúng vào lớp verification, transaction/data setup và cleanup. Chỉ báo state đã chuẩn bị khi database hoặc repository test thực sự đã ở trạng thái tương ứng.

Một cấu hình provider test JUnit 5 thường gồm ý tưởng:

~~~java
import au.com.dius.pact.provider.junit5.HttpTestTarget;
import au.com.dius.pact.provider.junit5.PactVerificationContext;
import au.com.dius.pact.provider.junit5.PactVerificationInvocationContextProvider;
import au.com.dius.pact.provider.junitsupport.Provider;
import au.com.dius.pact.provider.junitsupport.loader.PactFolder;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestTemplate;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@Provider("inventory-service")
@PactFolder("pacts")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryProviderContractTest {

    @LocalServerPort
    int port;

    @BeforeEach
    void beforeEach(PactVerificationContext context) {
        context.setTarget(new HttpTestTarget("localhost", port));
    }

    @TestTemplate
    @ExtendWith(PactVerificationInvocationContextProvider.class)
    void verify(PactVerificationContext context) {
        context.verifyInteraction();
    }
}
~~~

Đoạn provider test trên minh họa **cấu trúc chạy verification**, chưa có hook provider-state hoặc fixture cụ thể. Có thể dùng **@PactBroker** hay cách tải Pact phù hợp CI thay cho **@PactFolder**. Test phải gắn class/state callback để setup SKU và dọn dữ liệu trước hoặc sau interaction. Tên package/import thay đổi theo Pact JVM version cần được đối chiếu khi triển khai thực.

**Điểm cần nhớ:** Nếu provider verification chỉ dùng một mock InventoryService khác thay cho ứng dụng thật, ta lại có hai mock đồng ý với nhau nhưng không xác minh implementation provider.

## 9. Provider states và dữ liệu kiểm thử ổn định

**Provider state** mô tả điều kiện cần để một tương tác xảy ra. Ví dụ:

- “SKU BOOK-101 has 3 items available”.
- “SKU UNKNOWN-999 does not exist”.
- “Reservation R-501 is already completed”.
- “Authenticated tenant A owns order O-100”.

Chúng không phải công thức “chạy tất cả migration và toàn bộ database production”. Test setup nên:

- **Deterministic:** cùng state tạo ra cùng kết quả.
- **Isolated:** interaction này không phụ thuộc dữ liệu của interaction khác.
- **Fast:** dùng database test hoặc fixture tối thiểu khi phù hợp.
- **Idempotent:** chạy lại state không gây trùng hoặc hỏng dữ liệu.
- **Clean:** xóa/reset dữ liệu hoặc dùng transaction/container cách ly khi cần.
- **Safe:** không gọi payment hoặc email thật từ provider test.

Nếu test dựa vào một database staging dùng chung rồi chờ SKU BOOK-101 “có sẵn”, test có thể fail ngẫu nhiên khi dữ liệu thay đổi; đó là vấn đề fixture chứ không chắc là contract break.

### 9.1. State có tham số

Một contract có thể dùng state có tham số như **sku=BOOK-101** và **quantity=3**, nếu công cụ hỗ trợ. Đối với provider thật, callback phải validate tham số và tạo dữ liệu. Tránh xây một bộ fake phức tạp khiến test state không phản ánh các tiền điều kiện mà code provider thực cần.

### 9.2. Authentication trong provider test

Nếu endpoint yêu cầu xác thực, provider verification vẫn cần kiểm tra **cấu trúc request liên quan đến auth** và chạy với identity test có quyền phù hợp.

Một số bộ test có thể thay thế token bằng giá trị sinh trong test để không ghi secret thật vào Pact artifact. Điều đó không chứng minh toàn bộ authn/authz, nhưng phải bảo đảm provider verification chạy qua tuyến xử lý đúng khi contract yêu cầu. Bổ sung security test riêng cho token invalid, cross-tenant, BOLA và forbidden access.

## 10. Ví dụ thay đổi tương thích và không tương thích

Giả sử Order đang dùng response:

~~~json
{
  "sku": "BOOK-101",
  "available": 3
}
~~~

Các thay đổi có mức ảnh hưởng khác nhau:

| Thay đổi tại Inventory | Tương thích với Order hiện tại? | Lý do |
| --- | --- | --- |
| Thêm **warehouse** vào response | Thường có | Nếu Order bỏ qua unknown fields |
| Thêm một endpoint mới | Có | Endpoint cũ không đổi |
| Đổi **available** thành **quantity** | Không | Order cần tên trường cũ |
| Đổi **available** từ integer sang string | Không | Client có thể không parse đúng |
| Trả **204** thay vì **200** khi tồn kho 0 | Có thể không | Contract cũ trông đợi 200 và body |
| Bắt buộc thêm request header trước đây không yêu cầu | Không đối với consumer cũ nếu nó không gửi header | Provider từ chối request hợp lệ trước đây |
| Bắt buộc request mới có tham số **region** | Có thể không | Client cũ không gửi |
| Thêm enum value **BACKORDERED** | Tùy client | Switch exhaustive có thể lỗi |
| Đổi ý nghĩa **available** từ số lượng có thể bán thành số lượng vật lý | Nguy hiểm dù shape không đổi | Đây là **semantic breaking change** |
| Thay thuật toán bên trong nhưng giữ contract | Có thể | Cần thêm kiểm thử nghiệp vụ để chứng minh hành vi đúng |

**Không có quy tắc “thêm trường luôn an toàn” cho mọi consumer.** Client deserializer có thể từ chối unknown field; contract matching hoặc schema policy có thể strict. Phải xét behavior của consumer thực.

**CDC kiểm tra contract được mã hóa**. Nếu contract chỉ nói “available là integer” mà không ghi nghĩa “số lượng có thể hứa cho đơn mới”, provider có thể đổi semantics mà test vẫn xanh. Do đó cần mô tả và kiểm thử bất biến nghiệp vụ.

## 11. Request và response phải được xét theo hai hướng

Khả năng tương thích không chỉ là response:

- **Consumer gửi request mới:** provider hiện tại có chấp nhận method, path, query, body, header không?
- **Provider trả response mới:** consumer đang chạy có parse và xử lý được không?
- **Provider yêu cầu input chặt hơn:** các consumer cũ có tiếp tục gọi được không?
- **Consumer đòi output mới:** provider đang chạy có cung cấp field/trạng thái đó không?

Ví dụ Order v2 bắt đầu gửi **warehouseId** trong request; Inventory v1 có thể bỏ qua field tùy chọn đó. Nhưng nếu Order v2 bắt đầu **phụ thuộc** vào response **reservedUntil**, Inventory v1 chưa cung cấp; không thể triển khai Order v2 khi Inventory vẫn là v1 nếu không có fallback tương thích.

Do đó **“provider mới tương thích consumer cũ”** và **“consumer mới tương thích provider đang chạy”** là hai câu hỏi khác nhau. CI/CD phải xét cả hai hướng theo version thực sự ở từng environment.

## 12. Consumer-driven contract khi có nhiều consumer

Inventory phục vụ:

- **Order:** dùng sku và available.
- **Catalog:** dùng sku, displayName và status.
- **Warehouse Dashboard:** dùng sku, warehouse breakdown và lastReconciledAt.

Nếu chỉ kiểm tra contract của Order, Inventory có thể gỡ **lastReconciledAt** mà không ảnh hưởng Order nhưng làm hỏng Dashboard. Vì thế provider phải verify **tập hợp contract của các consumer liên quan**, không chỉ một nhóm hoặc contract mới nhất.

Một provider không nên kết luận “tất cả consumer đều an toàn” nếu chưa biết:

- Những consumer/version nào đang chạy ở production?
- Có app mobile lâu không cập nhật hoặc đối tác bên ngoài không tham gia Broker không?
- Branch nào đang chuẩn bị deploy?
- Contract từ consumer nào đã được xác minh với provider version dự kiến?
- Có endpoint public cho bên thứ ba mà Pact không bao phủ không?

CDC hoạt động hiệu quả nhất khi **consumer có thể công bố yêu cầu**, provider có thể verify, và hệ thống release biết version nào đang ở đâu.

## 13. Pact Broker và ma trận tương thích phiên bản

Một **Pact Broker** (hoặc giải pháp tương đương) giúp lưu:

- Contract do **Order version O1/O2** sinh ra.
- Kết quả Inventory **I1/I2** verify từng contract.
- Branch, tag hoặc deployment/release metadata.
- Những version đang chạy ở staging/production.
- Quyết định khả năng triển khai dựa trên bằng chứng đã có.

Ví dụ ma trận:

| | Inventory I1 | Inventory I2 |
| --- | --- | --- |
| **Order O1** | PASS | PASS |
| **Order O2** | FAIL | PASS |

Trong ví dụ, **Order O2** bắt đầu cần field mới chỉ có ở Inventory I2.

- Nếu production có Inventory I1, không triển khai Order O2 một cách an toàn dựa trên contract này.
- Inventory I2 có thể được triển khai trước nếu nó còn thỏa Order O1.
- Khi Inventory I2 đã chạy, có thể triển khai Order O2 nếu các contract liên quan đã được verify.
- Không thể kết luận tương thích nếu ô kết quả là **UNKNOWN**. Chưa có kết quả không đồng nghĩa PASS.

~~~mermaid
sequenceDiagram
    participant O as Order CI
    participant B as Pact Broker
    participant I as Inventory CI
    participant D as Deployment Gate
    O->>O: Chạy consumer tests
    O->>B: Publish Order pact/version
    I->>B: Fetch relevant pacts
    I->>I: Start provider + setup states
    I->>B: Publish verification results
    D->>B: Can version pair deploy?
    B-->>D: Yes / No / Unknown
    D->>D: Apply release policy
~~~

**Không chỉ hỏi “những bản mới nhất có tương thích không?”**. Một production environment có thể chứa consumer cũ, worker chưa nâng cấp hoặc nhiều version đồng thời. Quyết định deploy cần phản ánh **version thực tế đang được sử dụng và sắp triển khai**.

### 13.1. Can-I-Deploy

Trong hệ sinh thái Pact Broker, lệnh **can-i-deploy** kiểm tra ma trận phiên bản và kết quả verification tương ứng. Cú pháp minh họa:

~~~bash
pact-broker can-i-deploy \
  --pacticipant order-service \
  --version "$GIT_SHA" \
  --to-environment production
~~~

Lệnh trên giả định CI đã cấu hình đúng kết nối Broker, token, version, environment và thông tin deployment. Cần xác minh cú pháp chính xác theo Pact CLI đang sử dụng. Việc truyền một version chưa publish, thiếu provider verification hoặc metadata production có thể trả kết quả chưa thể xác nhận.

Không hardcode token Broker trong source hoặc log. Dùng secret/credential mechanism của CI.

### 13.2. Ghi lại deployment

Sau khi triển khai thành công một version, pipeline cần ghi nhận version đó đang ở environment nào để các lần **can-i-deploy** tiếp theo so sánh đúng. Nếu bỏ bước này, Broker có thể dựa trên metadata cũ và đưa ra quyết định không phản ánh trạng thái hiện tại.

Việc record deployment phải xảy ra **sau khi** deployment thật đã hoàn tất theo tiêu chí của pipeline, không ghi nhận sớm như một “ý định triển khai”.

## 14. Tích hợp vào CI/CD cho hai đội

### 14.1. Consumer pipeline — Order Service

Một chuỗi hợp lý:

1. Build và chạy unit tests của Order.
2. Chạy Pact consumer tests đối với outbound InventoryClient.
3. Sinh Pact artifact có version xác định (thường gắn với commit SHA).
4. Publish contract đến Broker.
5. Chạy các component/security tests liên quan.
6. Trước deployment, kiểm tra **can-i-deploy** với provider versions đang chạy ở target environment.
7. Chỉ triển khai nếu policy cho phép và những kiểm tra còn lại pass.

### 14.2. Provider pipeline — Inventory Service

Một chuỗi hợp lý:

1. Build Inventory và chạy unit/component tests.
2. Tải các Pact có liên quan từ Broker theo branch/version/environment policy.
3. Khởi động service thật ở môi trường test; chuẩn bị provider states.
4. Verify mọi interaction từ các consumer được chọn.
5. Publish verification results cho **Inventory version**.
6. Kiểm tra khả năng triển khai Inventory version mới so với consumer đang dùng ở production.
7. Triển khai, ghi lại version/environment khi thành công.

Cần chú ý **xung đột thời gian**: consumer có thể publish Pact khi provider chưa có code đáp ứng. Đây là tín hiệu hữu ích để phối hợp thay đổi, không nhất thiết là lỗi yêu cầu revert consumer ngay lập tức. Pipeline nên hiểu khác biệt giữa **contract trên nhánh feature** và **contract của consumer production**, tránh chặn mọi phát triển chỉ vì một feature chưa được provider hỗ trợ.

### 14.3. Ví dụ pipeline khái niệm

~~~yaml
# Pseudocode workflow để diễn giải thứ tự, không phải GitHub Actions hoàn chỉnh.
consumer_pipeline:
  - build_and_unit_test
  - run_pact_consumer_tests
  - publish_pact_with_consumer_version
  - run_can_i_deploy_for_target_environment
  - deploy_when_all_required_gates_pass
  - record_successful_deployment

provider_pipeline:
  - build_and_unit_test
  - fetch_relevant_consumer_pacts
  - setup_provider_states_and_verify
  - publish_verification_results_with_provider_version
  - run_can_i_deploy_for_target_environment
  - deploy_when_all_required_gates_pass
  - record_successful_deployment
~~~

Công cụ như **Pact Broker webhooks**, CI triggers và **pending/WIP pacts** có thể hỗ trợ flow phát triển bất đồng bộ giữa các nhóm. Cấu hình thế nào để một Pact mới trên nhánh chưa phát hành không chặn mọi build phải dựa vào release policy; **pending** không có nghĩa một interaction đã an toàn cho production.

## 15. Tránh phụ thuộc vào thứ tự triển khai

Một lợi ích quan trọng của CDC là phát hiện yêu cầu phối hợp **trước khi hai service triển khai không đồng bộ**.

Ví dụ thay đổi field:

**Trạng thái ban đầu:**

~~~json
{
  "sku": "BOOK-101",
  "available": 3
}
~~~

**Mục tiêu cuối cùng:**

~~~json
{
  "sku": "BOOK-101",
  "availableQuantity": 3
}
~~~

Đổi thẳng field sẽ phá Order cũ. Một lộ trình **expand–migrate–contract**:

1. **Expand provider:** Inventory trả cả **available** và **availableQuantity**. Provider vẫn pass contract của Order cũ.
2. **Migrate consumer:** Order phát hành version mới đọc **availableQuantity**, kiểm tra can-i-deploy với provider đã hỗ trợ.
3. **Observe:** xác nhận mọi consumer cần thiết đã chuyển sang field mới; lưu ý service ít sử dụng hoặc client ngoài Broker.
4. **Contract phase:** gỡ field **available** khi không còn consumer phụ thuộc; chạy lại provider verification và kiểm tra deployment.

~~~mermaid
flowchart TD
    A[Inventory I1: available] --> B[Inventory I2: available + availableQuantity]
    B --> C[Order O2: reads availableQuantity]
    C --> D{All relevant consumers migrated?}
    D -->|No| B
    D -->|Yes| E[Inventory I3: remove available]
~~~

Điều kiện “mọi consumer đã chuyển” cần bằng chứng từ Broker, telemetry, inventory client và thời hạn hỗ trợ của những client không trực tiếp tham gia CDC.

CDC giúp chỉ ra **tương thích giao thức** của lộ trình; nó không thay thế database migration, data backfill, idempotency hay nghiệp vụ.

## 16. CDC cho REST, gRPC và GraphQL

### 16.1. REST/HTTP

Contract thường mô tả request method, path/query/header/body, response status/header/body. Pact hỗ trợ tương tác HTTP theo cơ chế đã minh họa. Cần đặc biệt chú ý:

- **Error responses:** 400/401/403/404/409/429/503 nếu consumer dựa vào.
- **Pagination/cursor:** shape và semantics tiếp trang.
- **Content-Type và encoding:** media type, charset khi có liên quan.
- **Optional vs required:** null/missing/default.
- **Enum và số:** thay đổi kiểu hoặc miền giá trị.
- **Không đóng đinh dynamic fields:** timestamp, correlation ID hoặc server-generated UUID.

### 16.2. gRPC/Protobuf

Với gRPC, API contract còn gắn với file **.proto**, service/method, message field number/type và trạng thái gRPC. Một schema compatibility check có thể phát hiện nhiều kiểu break ngay khi CI chạy, chẳng hạn tái sử dụng field number sai hoặc đổi kiểu không tương thích.

Tuy nhiên schema compatible không đảm bảo consumer xử lý đúng semantics, timeout, retries hoặc business errors. Có thể bổ sung contract/behavior verification theo công cụ phù hợp.

Lưu ý: thay đổi tên field trong Protobuf có thể có mức ảnh hưởng khác thay đổi field number/wire type; phải hiểu wire compatibility và cách code generation của client hoạt động.

### 16.3. GraphQL

Trong GraphQL, consumer thường chọn field cần dùng trong query. Kiểm thử có thể tập trung vào **query/operation mà consumer thực gửi**, validation schema và behavior của resolver. Xóa field đang được query sẽ phá consumer; thêm field mới thường không phá operation cũ.

Kiểm tra schema không bảo đảm tất cả field vẫn có ý nghĩa nghiệp vụ hoặc quyền dữ liệu đúng. Cần đo và quản lý consumer operation/contract đang dùng.

## 17. Consumer-driven contract với message/event

Trong event-driven architecture, consumer và provider không gặp nhau qua một request HTTP trực tiếp. Ví dụ:

- **Order Service** phát **OrderCreated**.
- **Notification Service** nhận event và cần **orderId**, **customerId**, **occurredAt**.
- **Analytics Service** cũng nhận event và cần thêm **items** và **totalAmount**.

Ở đây **Notification là message consumer**, còn **Order là message provider/producer**. Notification tạo kỳ vọng về message mà nó có thể xử lý. Provider verification yêu cầu Order sinh một message thỏa kỳ vọng đó.

Contract ví dụ:

~~~json
{
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "eventId": "ab20cf25-5324-44f9-98c1-b5318478a101",
  "orderId": "ORD-101",
  "customerId": "CUS-54",
  "occurredAt": "2026-11-12T02:00:00Z"
}
~~~

Message contract có thể bao gồm:

- Key hoặc event type.
- Content type và schema version.
- Metadata/header cần cho routing.
- Body fields và matchers.
- Điều kiện provider state để tạo event.
- Quy tắc nullable/optional/enum và backward compatibility.

### 17.1. Khác biệt quan trọng giữa HTTP và event

Provider verification cho message thường gọi một **message generator** của Order để lấy payload và xác minh matcher, thay vì thực hiện một GET/POST trực tiếp.

Nếu chỉ dựng JSON cứng trong test mà không dùng serializer/event-producing code thật, provider contract có thể pass trong khi event thực được publish khác schema.

Nhưng ngay cả khi message contract pass, các điều kiện sau vẫn cần **integration/resilience test riêng**:

- Topic/exchange/queue có được tạo đúng?
- Consumer group/subscription có quyền và nhận message không?
- Message có bị gửi trùng, mất, đảo thứ tự hoặc đến muộn không?
- Retry, dead-letter queue và poison message xử lý thế nào?
- Kafka key/partition và ordering có phù hợp?
- Outbox/inbox, idempotency và transaction boundary có đảm bảo nghiệp vụ?

Schema Registry, Avro/Protobuf schema compatibility và CDC có thể bổ sung cho nhau. Chúng không hoàn toàn tương đương: schema kiểm tra cấu trúc tổng quát, CDC phản ánh interaction/field mà consumer cụ thể phụ thuộc.

## 18. CDC cho lỗi và trường hợp biên

Nhiều sự cố production xảy ra ở **error path**, không phải response 200. Consumer nên tạo contract cho các case nó thực sự xử lý, ví dụ:

| Interaction | Consumer cần | Provider cần chứng minh |
| --- | --- | --- |
| SKU tồn tại, còn hàng | 200 và available >= 1 | Trả shape đúng trong state có hàng |
| SKU tồn tại, hết hàng | 200 và available=0 | Không nhầm sang 404 nếu contract là 200 |
| SKU không tồn tại | 404 với code SKU_NOT_FOUND | Lỗi có cấu trúc ổn định |
| Reservation xung đột | 409 với code rõ | Consumer có thể báo không còn hàng |
| Request sai | 400 với cấu trúc lỗi | Không đổi contract lỗi âm thầm |
| Auth thiếu/sai | 401/403 theo API policy | Auth behavior phù hợp contract/security tests |

Không nhất thiết biến tất cả lỗi hạ tầng thành Pact interaction: timeout mạng, DNS fail, TLS error hoặc connection reset thường được kiểm thử bằng fault injection, client resilience và integration test. Pact HTTP contract phù hợp hơn với **response có ý nghĩa được provider trả về**.

### 18.1. Negative-path consumer test

Nếu Order xử lý **404** thành lỗi domain **UnknownSkuException**, consumer test phải assert mapping đó. Chỉ khai báo Pact 404 mà không chạy client error mapping chưa chứng minh Order có thể xử lý response đúng.

### 18.2. Kiểu lỗi cố định

Nếu Order phân nhánh theo **code=SKU_NOT_FOUND**, trường **code** cần được ghi rõ trong contract. **message** thường dùng để hiển thị/ghi log và có thể cần độ linh hoạt hơn, trừ khi consumer có dependency đặc biệt vào chuỗi đó.

## 19. Kiểm thử hợp đồng và API specification

**OpenAPI** mô tả giao diện REST rộng hơn một tập Pact interactions. OpenAPI có thể định nghĩa:

- Endpoint, parameters và request/response schema.
- Authentication scheme.
- Status codes.
- Constraints, examples, descriptions.
- API versioning và quy ước chung.

CDC/Pact mô tả **những tương tác cụ thể mà consumer đã mã hóa vào test**, thường sát với code gọi thật. Hai cách bổ trợ:

- **OpenAPI diff/schema check** phát hiện những thay đổi bề mặt API có thể không tương thích.
- **Consumer contract tests** cho biết những consumer nào thực sự phụ thuộc một interaction.
- **Provider verification** chứng minh provider implementation đáp ứng expectation.
- **Integration/E2E** kiểm tra deployment wiring và luồng nghiệp vụ thật.

Một provider có thể **đúng OpenAPI** nhưng consumer vẫn lỗi nếu consumer dựa trên giả định không được mô tả. Ngược lại, Pact pass nhưng API có thể không tuân thủ các phần spec ngoài phạm vi interaction.

Không dùng CDC để làm tài liệu API đầy đủ cho bên ngoài; các đối tác không tham gia contract workflow vẫn cần OpenAPI, versioning, changelog và chính sách deprecation.

## 20. Versioning và backward/forward compatibility

### 20.1. Consumer version

Pact artifact cần gắn với **version của consumer**. Khi hai commit tạo hai kỳ vọng khác nhau, Broker phải phân biệt chính xác. Có thể dùng Git SHA hoặc version theo release policy.

### 20.2. Provider version

Verification result phải gắn với **version provider đã chạy test**. Một kết quả PASS ở Inventory I1 không tự động chứng minh Inventory I2 tương thích. Nếu I2 đổi endpoint, phải verify lại.

### 20.3. Version của contract

Ngoài version ứng dụng, schema/interaction có thể có version theo giao thức (ví dụ event.schemaVersion=2). Không đánh đồng **Pacticipant version** với **schemaVersion** của event.

### 20.4. Backward compatibility

Provider mới còn đáp ứng consumer cũ. Ví dụ Inventory I2 vẫn trả field **available** cho Order O1.

### 20.5. Forward compatibility

Consumer mới có thể hoạt động với provider hiện tại, hoặc consumer được viết để chấp nhận field bổ sung/chưa biết mà không lỗi. Điều này phụ thuộc contract từng API và cách parser hoạt động; không thể suy luận từ Semantic Versioning chung.

### 20.6. Mixed-version rollout

Trong rolling deployment, nhiều phiên bản có thể chạy đồng thời. Nên kiểm tra ma trận:

- Consumer đang chạy ↔ provider mới.
- Consumer mới ↔ provider đang chạy.
- Consumer mới ↔ provider mới sau rollout.
- Consumer cũ còn ngoài Broker ↔ provider mới nếu phải hỗ trợ.

Đối với event, cần thêm producer mới ↔ consumer cũ, producer cũ ↔ consumer mới do message tồn đọng và consumer lag.

## 21. Consumer test không được biến thành implementation test

Hợp đồng là **ranh giới công khai**, không phải cách provider lưu dữ liệu hoặc tổ chức code. Tránh yêu cầu:

- Tên bảng SQL, tên repository class hay private method.
- Internal exception message mà caller không nhận.
- Các header/timestamp kỹ thuật không được consumer sử dụng.
- Toàn bộ response field chỉ vì hiện tại provider đang trả.
- Thứ tự property của JSON object không có ý nghĩa giao thức.
- Một test data ID cố định nếu contract không dựa vào giá trị đó.

Nếu provider đổi từ JPA sang MongoDB hoặc tách microservice nội bộ, contract nên giữ nguyên miễn API vẫn tương thích.

**CDC tốt tạo tự do đổi implementation bên trong provider mà không phá consumer.**

## 22. Contract cũng không được quá yếu

Một số anti-pattern ngược lại:

- Kiểm tra response có status 200 nhưng không assert body mà code consumer cần.
- Khai báo mọi field đều optional dù client truy cập bắt buộc.
- Dùng matcher “any string” cho status enum mà client chỉ biết ACTIVE/INACTIVE.
- Bỏ qua error response vì test happy path đã pass.
- Test chỉ mock adapter giả, không gọi code HTTP client thật.
- Cho phép provider verification trả PASS khi không thực sự chạy interaction.
- Không công bố kết quả theo version; team nhìn thấy test pass cũ và nghĩ build mới an toàn.

Cần để contract phản ánh **dependency thực tế**, nhưng tránh phình thành full provider snapshot.

## 23. Provider state không nên làm giả kết quả API

Ví dụ không đáng tin:

- Một test handler trong Inventory trả JSON cố định khi đang chạy verification.
- Provider verification được cấu hình chỉ test mock endpoint.
- State callback đánh dấu “success” nhưng không thực sự tạo dữ liệu.
- Stub có thể trả 200 trong khi controller thật đang trả 404.
- Hệ thống test thay route thật bằng route giản lược không có serialization/policy tương ứng.

Mục tiêu provider verification là chứng minh **implementation public boundary** có thể tạo response khớp contract. Có thể mock dependency ngoài phạm vi Inventory (ví dụ payment third party), nhưng phải kiểm tra controller, serialization và logic route thật mà consumer đang phụ thuộc.

Điều gì phải thật và điều gì được thay bằng test double là quyết định kiến trúc: ưu tiên giữ lớp ứng dụng cung cấp contract ở dạng thật, rồi cô lập những dependency khó kiểm soát bên dưới.

## 24. Tính ổn định của test và chi phí vận hành

Một bộ CDC có thể thất bại bởi thiết kế test kém dù hai service tương thích. Những nguồn flaky phổ biến:

| Nguyên nhân | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Dùng database staging chung | State bị đổi giữa hai test | Fixture cô lập hoặc DB container test |
| Request/response chứa timestamp cố định | Test fail không liên quan contract | Dùng matcher phù hợp |
| Cố định UUID do server sinh | Mỗi lần chạy khác nhau | Match format/type, không exact |
| Không reset state | Test order-dependent | Setup/cleanup per interaction |
| Gọi external provider thật trong unit test | Network/secret làm build fail | Mock outbound dependency theo boundary |
| Pact và code client không cùng version | Artifact stale | Sinh Pact từ consumer test trong cùng build |
| Publish kết quả sai commit SHA | Broker kết luận nhầm | Gắn version từ nguồn CI đáng tin |
| Chọn sai branch/version từ Broker | Thiếu interaction đang hoạt động | Dùng selector policy rõ ràng |
| Thay môi trường target tùy tiện | Canary khác production | Gắn deployment metadata chính xác |

Contract tests nên có tốc độ và tính ổn định đủ tốt để chạy mỗi pull request/commit liên quan. Test mất nhiều phút vì bootstrap một cluster đầy đủ có thể đã trượt sang integration/E2E; cần xem lại boundary.

## 25. Security trong CDC

CDC có thể kiểm tra các tương tác bảo mật ở mức protocol nhưng **không thay thế security testing**.

Có thể contract hóa:

- Request cần **Authorization** hoặc một loại token/identity test.
- Error schema/status cho 401/403 khi contract yêu cầu.
- API dùng đúng media type và header cần thiết.
- Consumer nhận được lỗi có thể xử lý khi token thiếu quyền.

Nhưng cần security test riêng cho:

- Chữ ký JWT, issuer, audience, expiry, token replay.
- Phân quyền mức đối tượng/tenant (**BOLA**).
- Injection, SSRF, XSS, mass assignment.
- TLS/mTLS và cấu hình certificate/hostname.
- Lộ dữ liệu nhạy cảm qua logs/response.
- Rate limit, abuse và resource exhaustion.

**Không publish token thật, user password, thông tin thẻ hoặc PII production** trong Pact artifact. Pact thường được chia sẻ giữa nhóm hoặc đưa lên Broker. Dùng dữ liệu synthetic và provider state an toàn.

Nếu endpoint chỉ hoạt động với user đã xác thực, test có thể dùng identity fixture và token test; endpoint vẫn phải được bảo vệ trong cấu hình production.

## 26. Những ranh giới CDC không bao phủ

Để dùng đúng kỳ vọng, cần biết CDC **không tự bảo đảm**:

1. **Performance:** provider có thể trả đúng shape nhưng mất 10 giây.
2. **Availability:** contract pass nhưng production đang mất mạng hoặc database.
3. **Distributed transactions:** không chứng minh thanh toán, tồn kho và order cùng nhất quán.
4. **Business semantics đầy đủ:** matcher kiểu dữ liệu không biết số lượng tồn kho có chính xác không.
5. **Authorization/tenant isolation:** phải kiểm thử policy độc lập.
6. **Observability:** Pact pass không đảm bảo trace, log hoặc dashboard đủ tốt.
7. **Message delivery semantics:** shape đúng không chứng minh at-least-once, ordering hoặc idempotency.
8. **Unknown consumers:** không bảo vệ đối tác/client không công bố contract.
9. **Infrastructure routing:** DNS, gateway, service discovery, TLS deployment vẫn cần integration/smoke test.
10. **Data migration compatibility:** schema contract pass không chứng minh dữ liệu cũ đọc được.
11. **Rollback toàn hệ thống:** rollback app có thể không tương thích state đã ghi.
12. **Một môi trường production sạch:** môi trường thực có traffic, volume và dữ liệu phức tạp hơn test.

CDC là bằng chứng về **tương thích tại boundary đã được mô tả**, không phải “chứng nhận hệ thống không lỗi”.

## 27. Phối hợp giữa các đội khi thay API

Một quy trình cộng tác giảm xung đột:

1. Consumer đề xuất interaction mới, mô tả business requirement và failure handling.
2. Provider xác nhận endpoint, schema, ngữ nghĩa và thời gian hỗ trợ.
3. Consumer commit contract test cùng client code và publish Pact của branch feature.
4. Provider thực hiện code hỗ trợ và provider verification trong branch tương ứng.
5. Các nhóm dùng Broker để quan sát trạng thái tương thích, không kết luận chỉ từ merge status.
6. Triển khai phần hỗ trợ backward compatible của provider trước nếu consumer mới cần tính năng chưa có.
7. Consumer triển khai sau khi provider phù hợp đã chạy, hoặc có cơ chế rollout đồng bộ rõ.
8. Sau deprecation window, gỡ trường/call path cũ khi mọi consumer thực tế đã chuyển.
9. Ghi changelog và cập nhật OpenAPI/schema nếu có thay đổi contract công khai.

Với thay đổi nhỏ tương thích hoàn toàn, có thể thực hiện nhanh hơn; nhưng vẫn cần verification và deployment evidence cho những service quan trọng.

## 28. Mẫu quyết định triển khai thực tế

Tình huống: Inventory I2 thay đổi cách đặt tên field. Có hai consumer:

- Order O1 đang chạy production, đọc **available**.
- Catalog C1 đang chạy production, chỉ đọc **sku** và **status**.

Nhóm Inventory muốn xóa **available** ngay.

**Bằng chứng cần xem:**

| Consumer | Trường phụ thuộc | I2 xóa available | Đánh giá |
| --- | --- | --- | --- |
| Order O1 | sku, available | Order không parse được | **Breaking** |
| Catalog C1 | sku, status | Không bị ảnh hưởng trực tiếp | Có thể compatible |
| Consumer chưa ghi danh | Chưa biết | Chưa biết | Không được mặc định safe |

**Phương án triển khai:** giữ **available**, thêm field mới và verify cả Order/Catalog. Sau khi Order O2 chuyển sang field mới và production không còn consumer cần **available**, mới gỡ trong một release sau.

Nếu contract test của Catalog pass nhưng Order fail, không thể tuyên bố Inventory I2 sẵn sàng để triển khai production chung. Quyết định còn phụ thuộc version đang chạy và rollout topology.

## 29. Kịch bản CDC với event OrderCreated

Notification yêu cầu event:

~~~json
{
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-101",
  "customerId": "CUS-54"
}
~~~

Đội Order muốn tách **customerId** thành **buyerId** và **recipientId**.

Một lộ trình an toàn:

1. Notification công bố consumer message contract vẫn cần **customerId**.
2. Order v2 phát thêm **buyerId** và **recipientId** nhưng tiếp tục phát **customerId**.
3. Provider message verification kiểm tra Order v2 tạo event hợp lệ với contract Notification v1.
4. Notification v2 nhận field mới và publish contract mới.
5. Khi mọi event còn tồn trong broker và mọi consumer liên quan đã hỗ trợ, Order mới bỏ field legacy theo policy.
6. Consumer vẫn cần xử lý duplicate delivery/retry và idempotency độc lập với message contract.

Nếu schema có quy tắc tương thích tự động, chúng bổ sung cho Pact nhưng không luôn xác minh **đường code producer thực**. Message contract test nên chạy trên serializer/event generator production khi có thể.

## 30. Câu hỏi tự kiểm tra

**1. Nếu consumer test pass với Pact mock server, provider đã chắc chắn tương thích chưa?**  
Chưa. Consumer test chỉ chứng minh code consumer hoạt động với giả định đã ghi. Phải chạy **provider verification** trên implementation provider thật.

**2. Tại sao provider không nên yêu cầu Pact assert mọi field response?**  
Vì các consumer không nhất thiết dùng tất cả. Test quá chặt làm thay đổi không ảnh hưởng consumer trở thành breaking, tăng coupling giữa hai team.

**3. Một contract chỉ assert status 200 có đủ không?**  
Thường không. Nếu consumer cần **available** là số nguyên, contract phải thể hiện yêu cầu đó, nếu không provider có thể bỏ field mà vẫn pass.

**4. Thêm field response mới có luôn backward compatible không?**  
Không tuyệt đối; cần xem consumer có chấp nhận unknown fields và contract có strict matching không. Nhưng với consumer tolerant, thêm field không sử dụng thường tương thích.

**5. Khi nào provider được xóa field cũ?**  
Khi có bằng chứng mọi consumer/version cần hỗ trợ không còn dùng field đó, các client bên ngoài đã qua deprecation window, và provider verification/deployment policy cho phép.

**6. Vì sao cần provider state?**  
Để provider thật có dữ liệu/trạng thái phù hợp với interaction, ví dụ SKU tồn tại. Nếu state phụ thuộc dữ liệu staging ngẫu nhiên, verification không đáng tin.

**7. CDC có bắt được lỗi sai tính tổng tiền nhưng response vẫn đúng schema không?**  
Chỉ nếu contract có kỳ vọng giá trị/semantics đủ cụ thể. Thông thường cần domain/component/integration test cho logic tính tiền.

**8. CDC áp dụng cho message/event thế nào?**  
Message consumer định nghĩa payload cần nhận; producer/provider được verify có thể sinh message thỏa matcher. Queue routing, ordering và delivery semantics cần kiểm thử riêng.

**9. Tại sao can-i-deploy phải dựa vào version đang chạy thay vì “latest”?**  
Vì production có thể chạy consumer/provider cũ hoặc nhiều version đồng thời; ma trận tương thích phải phản ánh thực tế deployment.

**10. Unknown trong ma trận Broker nghĩa là gì?**  
Chưa có đủ bằng chứng verification cho cặp version. Không thể coi unknown như pass; release gate cần xử lý theo policy xác định.

## 31. Checklist áp dụng cho một cặp microservice

Trước khi áp dụng CDC:

- Xác định **consumer/provider** theo từng interaction.
- Kiểm kê endpoint/message và các field mà consumer thật dùng.
- Chọn contract framework thích hợp cho HTTP, gRPC, GraphQL hoặc message.
- Viết consumer test **qua client adapter thật**, gồm happy/error paths quan trọng.
- Dùng matchers phản ánh dependency, không đóng đinh dữ liệu động.
- Tạo provider states deterministic và cô lập side effect.
- Verify trên implementation provider thật; kiểm soát auth/fixture.
- Gắn artifact và kết quả verification với version/commit đáng tin.
- Công bố kết quả và mô hình hóa production/staging deployment trong Broker.
- Đặt release gate dựa trên version compatibility theo cả hai hướng.
- Duy trì compatibility policy/deprecation cho consumer không có trong Broker.
- Kết hợp với unit, integration, E2E, security, performance và resilience tests.
- Dọn contract không còn được sử dụng sau khi xác minh không còn client cần hỗ trợ.

## 32. Tài liệu tham khảo

- Pact — Consumer Driven Contract Testing: https://docs.pact.io/
- Pact — What is a Pact? https://docs.pact.io/getting_started/how_pact_works
- Pact — Provider Verification: https://docs.pact.io/provider
- Pact — Pact Broker and deployment compatibility: https://docs.pact.io/pact_broker
- Pact JVM: https://docs.pact.io/implementation_guides/jvm
- Spring Cloud Contract: https://spring.io/projects/spring-cloud-contract
- Martin Fowler — Consumer-Driven Contracts: https://martinfowler.com/articles/consumerDrivenContracts.html
- Martin Fowler — Contract Test: https://martinfowler.com/bliki/ContractTest.html
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html

**Ghi nhớ:** Consumer-Driven Contract Testing xây dựng bằng chứng rằng **những interaction mà consumer đang cần** vẫn được provider hỗ trợ. Consumer test, provider verification và release gating theo version tạo thành một chu trình; thiếu bất kỳ bước nào, một bộ mock test xanh vẫn có thể che giấu thay đổi API làm hỏng microservice khác.
