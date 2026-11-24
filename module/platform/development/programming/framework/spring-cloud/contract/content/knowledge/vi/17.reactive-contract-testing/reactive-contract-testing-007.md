# Tránh block hoặc điều kiện đua trong phần chuẩn bị kiểm thử

## 1. Vấn đề: test reactive thất bại dù contract không thay đổi

Trong một ứng dụng **Spring WebFlux**, producer có thể nhận HTTP request, truy vấn cơ sở dữ liệu bằng Reactive Streams và trả `Mono<T>` hoặc `Flux<T>`. Consumer chỉ nhìn thấy HTTP status, headers và JSON body. **Spring Cloud Contract** cho phép mô tả những kỳ vọng đó bằng Groovy/YAML DSL, sinh test phía producer, phát hành stub để consumer chạy qua Stub Runner và tích hợp verification vào CI.

Khó khăn xuất hiện khi **chuẩn bị dữ liệu kiểm thử** theo cách bất đồng bộ nhưng **không đợi nó hoàn tất**.

Ví dụ một generated test sẽ gọi:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
Accept: application/json
~~~

và mong nhận:

~~~json
{
  "orderId": "ORD-123",
  "status": "CONFIRMED",
  "totalAmount": 120000
}
~~~

Trước khi test gửi request, base class cần tạo đơn hàng `ORD-123` trong một reactive repository. Nếu setup viết như sau:

~~~java
@BeforeEach
protected void setUp() {
    repository.save(new OrderEntity(
        "ORD-123", "CONFIRMED", 120000L
    )).subscribe();
}
~~~

thì lời gọi `subscribe()` **khởi động một subscription nhưng trả về ngay**; nó không đảm bảo lệnh lưu dữ liệu đã hoàn thành trước khi generated test gửi request. Một lần chạy có thể nhận `200`, lần khác lại `404`. Đây là **race condition trong test fixture**, không nhất thiết là producer phá vỡ API.

Nếu đổi thành một lệnh `Thread.sleep(1000)`, test vẫn có thể thất bại khi máy CI chậm, đồng thời làm bộ kiểm thử tốn thời gian. Nếu gọi `block()` trong một luồng xử lý reactive không cho phép blocking, producer hoặc test có thể báo lỗi hoặc gây nghẽn.

Bài học thuộc chương **Kiểm thử reactive** của module `SPRING_CLOUD_CONTRACT`, tập trung vào cách bảo đảm điều kiện ban đầu của generated contract tests **đã sẵn sàng** mà không chặn event loop hoặc dựa vào khoảng đợi tùy tiện.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích cold publisher, subscription, completion và nguyên nhân race trong setup.
2. Phân biệt việc **chờ hoàn tất có giới hạn ở test thread** với việc **blocking nguy hiểm trên event-loop thread**.
3. Sử dụng `StepVerifier` để chuẩn bị dữ liệu một cách có thể xác minh.
4. Chọn chiến lược fixture tốt hơn: mock trả `Mono.just(...)`, seed reactive repository có thứ tự hoặc chờ sự kiện xác định.
5. Cấu hình WebFlux contract tests dùng `WEBTESTCLIENT`/`RestAssuredWebTestClient` và base test phù hợp.
6. Tránh trạng thái dùng chung, đăng ký subscriber trễ và các timeout không có điểm dừng.
7. Chẩn đoán sai lệch fixture so với breaking change của API trước khi phát hành stub.

> **Nguyên tắc:** *Dữ liệu cần cho test phải có trạng thái sẵn sàng quan sát được trước lúc gửi request*. Không coi việc tạo `Mono`, gọi `subscribe()`, hoặc ngủ một khoảng thời gian là bằng chứng setup đã hoàn tất.

## 2. Nắm vững ba thời điểm của một Publisher

Trong Project Reactor, `Mono<T>` biểu diễn tối đa một giá trị hoặc tín hiệu hoàn tất/lỗi, còn `Flux<T>` biểu diễn từ 0 đến nhiều giá trị. Nhiều publisher là **cold**: thao tác I/O hoặc logic chỉ được kích hoạt khi có subscriber.

Xét:

~~~java
Mono<OrderEntity> saveOperation =
    repository.save(new OrderEntity("ORD-123", "CONFIRMED", 120000L));
~~~

Cần phân biệt:

| Thời điểm | Điều đã xảy ra | Điều **chưa** được bảo đảm |
| --- | --- | --- |
| Tạo `Mono` | Có mô tả công việc lưu dữ liệu | Chưa chắc I/O đã chạy |
| Subscribe | Publisher bắt đầu được tiêu thụ | Chưa chắc thao tác hoàn tất |
| Nhận `onNext` và/hoặc `onComplete` | Publisher báo tiến độ/thành công theo contract của nó | Chưa chắc những hệ thống ngoài publisher đã quan sát được nếu có cơ chế nhất quán eventual khác |
| Nhận `onError` | Thao tác báo thất bại | Không thể coi fixture đã sẵn sàng |

Với reactive repository thông thường, hoàn tất từ publisher lưu dữ liệu là mốc đồng bộ quan trọng để gửi HTTP request tiếp theo. Nếu hệ thống có hàng đợi, indexing bất đồng bộ, cache hoặc sự kiện phát ra sau khi lưu, cần **quan sát mốc sẵn sàng thực sự** của thành phần mà request sẽ đọc.

### 2.1. Sơ đồ race do subscribe tách rời

~~~mermaid
sequenceDiagram
    participant J as JUnit @BeforeEach
    participant DB as Reactive repository
    participant T as Generated contract test
    participant API as WebFlux controller
    J->>DB: save(order).subscribe()
    J-->>T: setup trả về ngay
    T->>API: GET /api/orders/ORD-123
    API->>DB: findById(ORD-123)
    DB-->>API: Chưa thấy order
    API-->>T: 404
    DB-->>J: save hoàn tất sau đó
~~~

Đây là tình huống lỗi **không ổn định theo lịch chạy**: kết quả phụ thuộc việc scheduler nào được thực thi trước, độ trễ database, CPU và tải CI.

### 2.2. “Không block” không có nghĩa “không bao giờ phải đợi”

Trong test, câu hỏi chính là **đợi ở luồng nào, có giới hạn không và đợi điều kiện gì**:

- **Sai:** Gọi `block()` hoặc `Thread.sleep` bên trong callback WebFlux đang chạy trên Reactor Netty event loop.
- **Rủi ro:** Dùng `subscribe()` trong `@BeforeEach` rồi để test chạy tiếp mà không có tín hiệu hoàn tất.
- **Chấp nhận được khi được kiểm soát:** Dùng `StepVerifier.verify(Duration)` trên **JUnit test thread** để đợi publisher setup hoàn tất với timeout hữu hạn.
- **Còn tốt hơn cho web-slice test:** Mock reactive dependency trả `Mono.just(...)` hoặc `Mono.empty()` để không cần seeding I/O bất đồng bộ.

Mục tiêu là tránh **blocking không kiểm soát** và tránh **điều kiện đua**, không phải ép mọi phương thức Java trong test trở thành reactive.

## 3. Các anti-pattern cần nhận ra ngay

### 3.1. Chỉ tạo Mono mà không subscribe

~~~java
@BeforeEach
protected void setUp() {
    repository.deleteAll()
        .then(repository.save(order));
}
~~~

Ở đây chỉ tạo ra một pipeline. Nếu không có subscription từ bên ngoài, thông thường **không có thao tác xóa/lưu nào được thực thi**.

### 3.2. Fire-and-forget trong setup

~~~java
@BeforeEach
protected void setUp() {
    repository.deleteAll().subscribe();
    repository.save(order).subscribe();
}
~~~

Hai subscription độc lập, vì vậy **không bảo đảm xóa xong rồi mới lưu**, cũng không bảo đảm lưu xong trước request. Đặc biệt nguy hiểm khi generated tests chạy song song: một test có thể xóa dữ liệu mà test khác vừa tạo.

### 3.3. Ngủ để “chờ dữ liệu ổn định”

~~~java
@BeforeEach
protected void setUp() throws InterruptedException {
    repository.save(order).subscribe();
    Thread.sleep(1000);
}
~~~

Đây là cách **phụ thuộc thời gian**. Chạy local thấy ổn không có nghĩa CI sẽ ổn. Tăng từ 1 giây lên 10 giây chỉ che rủi ro và làm suite chậm hơn.

### 3.4. `block()` trong pipeline phục vụ request

~~~java
@GetMapping("/api/orders/{id}")
Mono<OrderView> get(@PathVariable String id) {
    OrderEntity entity = repository.findById(id).block(); // Không nên
    return Mono.just(mapper.toView(entity));
}
~~~

WebFlux/Netty event loop cần duy trì tính không chặn. Gọi `block()` ở đây có thể gây lỗi `IllegalStateException` trên non-blocking thread hoặc tạo nút thắt hiệu năng. Code producer đúng hướng là **compose publisher**:

~~~java
@GetMapping("/api/orders/{id}")
Mono<OrderView> get(@PathVariable String id) {
    return repository.findById(id)
            .map(mapper::toView);
}
~~~

**Phạm vi khác nhau:** `block()` trên JUnit thread trong một đoạn setup có kiểm soát không giống `block()` bên trong pipeline WebFlux. Tuy nhiên `block()` không timeout vẫn có nguy cơ treo test, vì vậy ưu tiên `StepVerifier` có timeout và assertion về completion.

## 4. Cách chuẩn bị fixture bằng StepVerifier có giới hạn

Một cách đơn giản là **compose công việc xóa/lưu thành một pipeline**, rồi đợi tín hiệu hoàn tất trước khi JUnit bước sang generated test.

Giả sử `repository` là ReactiveCrudRepository và `order` là entity mẫu:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@BeforeEach
protected void seedOrder() {
    OrderEntity order =
        new OrderEntity("ORD-123", "CONFIRMED", 120000L);

    Mono<Void> arrange = repository.deleteAll()
        .then(repository.save(order))
        .then();

    StepVerifier.create(arrange)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

Giải thích từng bước:

1. `repository.deleteAll()` tạo publisher xóa dữ liệu.
2. `then(repository.save(order))` chạy lưu **sau khi xóa hoàn tất thành công**, không chạy song song với xóa.
3. `then()` chuyển kết quả thành `Mono<Void>` chỉ quan tâm tín hiệu hoàn tất/lỗi.
4. `StepVerifier.create(arrange)` tạo một verifier có subscription khi gọi `verify(...)`.
5. `expectComplete()` yêu cầu publisher kết thúc thành công, không phải chỉ có subscription.
6. `verify(Duration.ofSeconds(5))` đợi **tối đa** 5 giây trên test thread, thất bại nếu timeout hoặc sai kỳ vọng.

Đây là cách **chờ có giới hạn** trên luồng kiểm thử, không phải chặn Reactor event loop trong endpoint. Giá trị 5 giây chỉ là ví dụ; hãy chọn timeout phù hợp độ trễ thực tế của test database và CI, tránh kéo dài vô hạn.

### 4.1. Assertion thêm để xác minh fixture thực sự đã lưu

Nếu muốn kiểm chứng dữ liệu có thể được đọc:

~~~java
StepVerifier.create(repository.findById("ORD-123"))
    .assertNext(saved -> {
        assertThat(saved.getStatus()).isEqualTo("CONFIRMED");
        assertThat(saved.getTotalAmount()).isEqualTo(120000L);
    })
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Điều này giúp phân biệt “save publisher báo hoàn tất” với “read path chưa nhìn thấy dữ liệu” trong trường hợp cần thiết. Nếu thao tác đọc phụ thuộc một search index hoặc cache được cập nhật eventual, hãy chờ đúng cơ chế sẵn sàng đó bằng điều kiện xác định, không đọc lặp vô hạn.

### 4.2. Đừng quên timeout của StepVerifier

Các lệnh rút gọn như `verifyComplete()` tiện dụng, nhưng mặc định **có thể không có timeout** nếu dự án không đặt `StepVerifier.setDefaultTimeout(...)`. Trong một pipeline lỗi không phát `onComplete`, test có thể chờ vô hạn.

Với setup bắt buộc phải hoàn tất trước request, nên thể hiện mốc kết thúc và timeout:

~~~java
StepVerifier.create(repository.save(order))
    .expectNextMatches(saved -> "ORD-123".equals(saved.getId()))
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Đừng đặt timeout quá ngắn khiến CI thường xuyên lỗi giả; cũng đừng dùng timeout dài hàng phút như cách thay thế cho sửa race hoặc lỗi kết nối database.

## 5. Khi nào không cần kết nối database: reactive mock ổn định

Đối với HTTP contract test ở **web slice**, mục tiêu thường là kiểm tra method/path, status, JSON serialization và mapping của controller, không phải toàn bộ storage layer. Khi đó, **mock một dependency trả publisher có kết quả xác định** là cách đơn giản nhất để tránh race trong fixture.

Giả sử có interface:

~~~java
public interface OrderQuery {
    Mono<OrderView> findById(String orderId);
}
~~~

DTO:

~~~java
public record OrderView(
    String orderId,
    String status,
    long totalAmount
) {}
~~~

Controller reactive:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderQuery orderQuery;

    public OrderController(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @GetMapping("/{orderId}")
    public Mono<OrderView> getById(@PathVariable String orderId) {
        return orderQuery.findById(orderId);
    }
}
~~~

Trong base class, mock trả publisher **đã được định nghĩa sẵn**:

~~~java
@MockitoBean
OrderQuery orderQuery;

@BeforeEach
protected void setUp() {
    given(orderQuery.findById("ORD-123"))
        .willReturn(Mono.just(
            new OrderView("ORD-123", "CONFIRMED", 120000L)
        ));
}
~~~

`Mono.just(...)` phát giá trị khi được subscribe, không đòi truy cập database hay gửi một write bất đồng bộ trước đó. Vì thế web-slice contract test tập trung vào **request/response behavior** với fixture ổn định.

Nếu cần kiểm tra nhánh “không tồn tại”, có thể chuẩn bị:

~~~java
given(orderQuery.findById("ORD-404"))
    .willReturn(Mono.empty());
~~~

Lưu ý `Mono.empty()` chỉ cho biết dependency không có dữ liệu. **Status và error body cuối cùng** phụ thuộc việc controller dùng `switchIfEmpty(...)`, mapping lỗi hoặc exception handler nào. Không mặc định `Mono.empty()` tự tạo response `404` có JSON error envelope mong muốn.

### 5.1. Giới hạn của mock

Mock làm test ổn định hơn nhưng **không chứng minh reactive repository thực sự hoạt động** hay hệ thống xử lý transaction, race ghi/đọc đúng. Hãy kết hợp:

- Contract test ở web slice để bảo vệ HTTP API.
- Repository integration test để kiểm tra lưu/đọc reactive.
- Service/domain tests để xác minh nghiệp vụ.
- End-to-end test khi consumer phụ thuộc vào độ trễ eventual của hệ thống khác.

## 6. Viết HTTP contract và chọn WEBTESTCLIENT thay vì MOCKMVC

Ví dụ contract `src/test/resources/contracts/orders/get_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 120000
        )
    }
}
~~~

DSL mô tả **hành vi HTTP**, không mô tả test sẽ dùng MockMvc hay WebTestClient. Với producer sử dụng Spring WebFlux, Spring Cloud Contract hỗ trợ test mode **`WEBTESTCLIENT`** và mã generated có thể dùng **RestAssuredWebTestClient**. Điều này được mô tả trong tài liệu chính thức Spring Cloud Contract.

Cấu hình Maven minh họa:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <testMode>WEBTESTCLIENT</testMode>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
            com.example.orders.contract.ContractVerifierBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

Cấu hình Gradle minh họa:

~~~groovy
contracts {
    testMode = 'WEBTESTCLIENT'
}
~~~

Cấu hình cụ thể phải tương thích với phiên bản plugin, cách khai báo base class và JUnit của dự án. Đừng dán placeholder `REPLACE_WITH_COMPATIBLE_VERSION` vào dự án thật rồi mong Maven tự resolve.

### 6.1. Các test mode không đồng nghĩa nhau

| Test mode | Đặc điểm chính | Khi nào cân nhắc |
| --- | --- | --- |
| `WEBTESTCLIENT` | Sinh test cho WebTestClient/RestAssuredWebTestClient, không bắt buộc mở server socket | WebFlux controller/HTTP boundary |
| `EXPLICIT` | Dùng HTTP client kiểm tra server chạy thực (theo cấu hình plugin) | Muốn kiểm tra mạng và các lớp runtime rộng hơn |
| `MOCKMVC` | Spring MVC test stack | Producer dùng Spring MVC, không phải lựa chọn mặc định cho WebFlux thuần |

Nếu chọn `EXPLICIT` nhưng không khởi động server/cấu hình port đúng, có thể gặp `Connection refused`. Nếu chọn `MOCKMVC` cho WebFlux thuần, test có thể không phù hợp cơ chế routing của producer. Đừng chỉnh test mode chỉ để che lỗi fixture.

## 7. Base class cho reactive HTTP contract test

Có hai chiến lược chính: **web slice với WebTestClient thực của Spring** hoặc **standalone controller setup** cho RestAssuredWebTestClient.

### 7.1. Web-slice base class với @WebFluxTest

Ví dụ Spring Boot hỗ trợ `@WebFluxTest` và Spring Framework có `@MockitoBean`:

~~~java
package com.example.orders.contract;

import com.example.orders.api.OrderController;
import com.example.orders.api.OrderView;
import com.example.orders.api.OrderQuery;
import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import io.restassured.module.webtestclient.RestAssuredWebTestClientClient;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;

@WebFluxTest(OrderController.class)
public abstract class ContractVerifierBase {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrderQuery orderQuery;

    @BeforeEach
    protected void setUp() {
        given(orderQuery.findById("ORD-123"))
            .willReturn(Mono.just(
                new OrderView("ORD-123", "CONFIRMED", 120000L)
            ));

        RestAssuredWebTestClient.useClient(
            RestAssuredWebTestClientClient.builder()
                .webTestClient(webTestClient)
                .build()
        );
    }

    @AfterEach
    protected void tearDown() {
        RestAssuredWebTestClient.resetClient();
    }
}
~~~

Cách `useClient(...)`/`resetClient()` ở trên dựa vào **API REST Assured Spring WebTestClient hiện đại** hỗ trợ binding client theo thread, thuận lợi khi nhiều test dùng cấu hình riêng. **Kiểm tra phiên bản REST Assured được Spring Cloud Contract quản lý trong dự án**: nếu chưa có các API này, dùng cơ chế setup tương thích mà phiên bản đó cung cấp, chẳng hạn `standaloneSetup(...)` hoặc cách cấu hình WebTestClient được tài liệu version tương ứng chỉ dẫn. Không chọn một API mới mà bỏ qua điều kiện tương thích.

Những điểm quan trọng:

1. `@WebFluxTest(OrderController.class)` kiểm tra ranh giới WebFlux; nhiều service bean sẽ không được nạp và cần mock/import phù hợp.
2. `@MockitoBean` tạo dependency giả có phương thức trả `Mono.just(...)`, không có write/subscribe bất đồng bộ.
3. `@BeforeEach` chuẩn bị fixture **trước** generated test.
4. `RestAssuredWebTestClient.useClient(...)` kết nối cách gửi request của generated test với `WebTestClient` đã được Spring cung cấp.
5. `@AfterEach` gỡ thread-local client binding để hạn chế rò rỉ cấu hình giữa test.
6. Base class `public abstract` có thể được generated test kế thừa theo cấu hình `baseClassForTests`.

**Ghi chú JUnit:** JUnit 5 dùng `@BeforeEach`, `@AfterEach`; tài liệu cũ có thể dùng JUnit 4 `@Before`. Đừng sao chép annotation từ ví dụ khác hệ JUnit mà không điều chỉnh.

### 7.2. Standalone setup phù hợp khi test controller cô lập

REST Assured và Spring Cloud Contract cũng hỗ trợ dạng cấu hình đơn giản:

~~~java
import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;

public abstract class ContractVerifierBase {

    private final OrderQuery orderQuery = mock(OrderQuery.class);

    @BeforeEach
    protected void setUp() {
        given(orderQuery.findById("ORD-123"))
            .willReturn(Mono.just(
                new OrderView("ORD-123", "CONFIRMED", 120000L)
            ));

        RestAssuredWebTestClient.standaloneSetup(
            new OrderController(orderQuery)
        );
    }
}
~~~

Đây là đoạn **minh họa cần đầy đủ import/package của dự án**. Standalone setup thường nhanh và không cần Spring application context đầy đủ, nhưng có thể không tái hiện security filter, controller advice, codec và các custom web configurations như production. Nếu contract ràng buộc chúng, nên dùng cấu hình context phù hợp.

**Lưu ý chạy song song:** Static global setup như `standaloneSetup(...)` có thể ảnh hưởng test khác nếu suite song song và có cấu hình khác nhau. Khi có nhiều base class hoặc parallel execution, nên sử dụng per-thread client binding nếu version hỗ trợ, tách context hoặc giới hạn song song có chủ đích.

## 8. Kết nối seed reactive repository với base test

Khi muốn dùng **database thật dành cho integration test**, không nên mock repository rồi kết luận cả tuyến web → persistence đã được kiểm tra. Tuy nhiên, phải seeding theo một chuỗi thao tác đã hoàn tất.

Ví dụ khung base class:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
public abstract class ReactiveContractBase {

    @Autowired
    ReactiveOrderRepository repository;

    @Autowired
    WebTestClient webTestClient;

    @BeforeEach
    protected void prepareFixture() {
        Mono<Void> arrange = repository.deleteAll()
            .then(repository.save(
                new OrderEntity("ORD-123", "CONFIRMED", 120000L)
            ))
            .then();

        StepVerifier.create(arrange)
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        // Chọn cách cấu hình RestAssuredWebTestClient phù hợp phiên bản
        // rồi mới cho generated test gửi HTTP request.
    }
}
~~~

Snippet này chỉ mô tả phần chuẩn bị; các import, loại entity/repository, cấu hình database và kết nối REST Assured cần được hoàn thiện theo dự án. **Không copy song song cả mock `OrderQuery` và reactive repository seed** nếu controller vẫn dùng mock: khi đó việc seed database sẽ không ảnh hưởng response HTTP, tạo cảm giác đã kiểm tra persistence trong khi chưa làm vậy.

### 8.1. Tại sao không đặt deleteAll và save trong hai @BeforeEach khác nhau?

Nếu hai phương thức setup không có quan hệ phụ thuộc rõ ràng, thứ tự thực thi có thể khác kỳ vọng, đặc biệt khi có kế thừa hoặc callback từ nhiều extension. Một pipeline:

~~~java
repository.deleteAll()
    .then(repository.save(order))
    .then()
~~~

bảo đảm **xóa rồi mới lưu trong một subscription**, thay vì phụ thuộc vào thứ tự callback hoặc scheduler.

Nếu có nhiều loại entity phụ thuộc nhau, compose thứ tự rõ:

~~~java
Mono<Void> seed = customerRepository.save(customer)
    .then(orderRepository.save(order))
    .then();
~~~

Ở ví dụ này, order được lưu sau khi customer save hoàn tất. Nếu schema có foreign key, event handler hoặc dữ liệu phụ thuộc, **thứ tự setup phải phản ánh đúng ràng buộc đó**.

### 8.2. Tránh xóa toàn bộ database dùng chung

`deleteAll()` chỉ hợp lý khi môi trường test **cô lập và do test sở hữu**. Nếu nhiều tests hoặc workers dùng chung database, việc xóa toàn bộ sẽ tạo race lớn hơn.

Ưu tiên:

- Database/container riêng cho test suite hoặc namespace/schema riêng.
- Dữ liệu có ID duy nhất theo test case.
- Cleanup chỉ những bản ghi do test tạo.
- Transaction/cleanup strategy được xác minh với reactive driver.
- Không chạy song song các test mutate cùng aggregate, trừ khi có cơ chế cách ly chắc chắn.

Không mặc định `@Transactional` trên một JUnit method tự động rollback **mọi** công việc reactive bất đồng bộ; reactive transactions gắn với Reactor Context và subscription, nên cần hiểu ranh giới transaction thực tế của ứng dụng.

## 9. Bẫy tương tranh khi generated tests chạy song song

JUnit 5 có thể chạy test song song theo cấu hình dự án. Ngay cả khi mỗi test có `@BeforeEach` riêng, dữ liệu dùng chung vẫn có thể va chạm.

Ví dụ hai contract:

- Test A cần `ORD-123` ở trạng thái `CONFIRMED`.
- Test B cần `ORD-123` ở trạng thái `CANCELLED`.

Nếu cả hai cùng cập nhật một bảng chung, kết quả phụ thuộc test nào seed trước. Một generated test có thể đọc dữ liệu do test kia vừa ghi.

### 9.1. Các nguyên nhân race thường gặp

| Nguồn chia sẻ | Ví dụ | Cách giảm rủi ro |
| --- | --- | --- |
| Cùng database | Hai test cùng cập nhật ID `ORD-123` | ID riêng hoặc database/schema cô lập |
| Cùng mock singleton | Test A thay stubbing của test B | Mock theo context và lifecycle phù hợp |
| Static client config | Test A đổi `RestAssuredWebTestClient` setup toàn cục | Client binding theo test/thread hoặc giới hạn parallel |
| Shared Reactor sink | Một test subscribe trước, test khác emit | Sink/bus riêng cho từng kịch bản |
| Shared Kafka topic | Message của test khác bị consumer test đọc | Correlation key, test topic/consumer group riêng |
| Đồng hồ hệ thống | Response có `createdAt` biến đổi | Clock cố định hoặc matcher định dạng |
| Cache toàn cục | Cache cũ ảnh hưởng kết quả đọc | Cô lập/xóa cache có kiểm soát |
| UUID ngẫu nhiên | Fixture/stub không nhất quán | Giá trị mẫu ổn định hoặc matcher |

### 9.2. Chiến lược chọn theo chi phí

1. Với web contract test cần kiểm tra controller JSON: **mock reactive service**.
2. Với repository integration test: database/schema riêng hoặc dữ liệu định danh độc lập.
3. Với message integration test: correlation ID và điểm chờ completion rõ ràng.
4. Nếu chưa cô lập được resource: tạm giới hạn parallel execution **chỉ nhóm test liên quan**, không vô hiệu hóa song song toàn bộ dự án như giải pháp dài hạn.

Không nên sửa contract thành regex quá rộng để test xanh khi lỗi thực sự do dữ liệu giữa các tests bị ghi đè.

## 10. Sự kiện bất đồng bộ: subscriber phải sẵn sàng trước trigger

Reactive HTTP request có thể kích hoạt một side effect, ví dụ gửi sự kiện `OrderConfirmed`. Nếu test gọi endpoint rồi **mới bắt đầu subscribe** vào một hot publisher, sự kiện có thể đã phát trước khi subscriber sẵn sàng.

### Anti-pattern

~~~java
webTestClient.post()
    .uri("/api/orders/ORD-123/confirm")
    .exchange()
    .expectStatus().isAccepted();

// Nếu publisher là hot và không replay, sự kiện có thể đã đi qua.
StepVerifier.create(orderEvents.take(1))
    .expectNextMatches(e -> "ORD-123".equals(e.orderId()))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Nếu `orderEvents` là hot Flux không replay lịch sử, consumer test đăng ký sau hành động có thể **mất sự kiện**. Test khi đó fail không ổn định hoặc luôn timeout tùy scheduling.

### Cách sắp xếp tốt hơn

Khi có một publisher sự kiện đã được chuẩn bị đúng, StepVerifier có thể subscribe **trước** khi trigger:

~~~java
Flux<OrderEvent> eventsForOrder = orderEvents
    .filter(e -> "ORD-123".equals(e.orderId()))
    .take(1);

StepVerifier.create(eventsForOrder)
    .then(() ->
        webTestClient.post()
            .uri("/api/orders/ORD-123/confirm")
            .exchange()
            .expectStatus().isAccepted()
    )
    .expectNextMatches(e -> "CONFIRMED".equals(e.status()))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Ở đây verifier kích hoạt subscription trước khi thực hiện hành động trong `then(...)`, và timeout có giới hạn. Trong trường hợp message pipeline dùng broker thật, cần bảo đảm subscription thực sự đã được hệ thống đăng ký và có cơ chế correlation phù hợp; chỉ thấy một subscription ở client test chưa chứng minh broker consumer đã sẵn sàng.

### 10.1. Không dùng Thread.sleep để đợi message

~~~java
sendMessage();
Thread.sleep(2000);
assertThat(receivedMessages).hasSize(1);
~~~

Cách này có thể fail khi CI chậm hoặc pass sai khi nhận message của test khác. Ưu tiên chờ **tín hiệu/điều kiện cụ thể** với timeout, correlation ID và assertion trực tiếp trên payload.

### 10.2. Contract test messaging và sự kiện không đồng nghĩa nhau

Một HTTP contract có response `202 Accepted` **không tự chứng minh** message đã được phát, broker giao hàng thành công hoặc consumer xử lý xong. Nếu producer còn có hợp đồng messaging, cần kiểm chứng riêng message destination, headers và body; trường hợp cần bảo đảm side effect phải có integration test đúng tầng.

## 11. Bounded waits: đợi điều kiện, không đợi thời lượng đoán mò

Khi setup phụ thuộc hệ thống eventual consistency (ví dụ ghi database xong mới có dữ liệu trong search index), điểm hoàn tất của publisher `save(...)` có thể chưa đủ để query qua index trả kết quả.

Một chiến lược tốt phải xác định:

1. **Điều kiện sẵn sàng:** Chẳng hạn query trả record có trạng thái `CONFIRMED`.
2. **Thời hạn tối đa:** Ví dụ 5–10 giây, điều chỉnh theo môi trường test.
3. **Khoảng thăm dò hợp lý:** Không spin loop liên tục gây tải.
4. **Cách báo lỗi:** In điều kiện nào chưa đạt khi timeout.
5. **Dữ liệu riêng của test:** Không nhầm kết quả với record test khác.

Ví dụ với publisher có thể poll trạng thái một cách reactive:

~~~java
Mono<OrderView> waitUntilVisible = Mono.defer(
        () -> searchClient.findById("ORD-123")
    )
    .filter(order -> "CONFIRMED".equals(order.status()))
    .repeatWhenEmpty(repeat ->
        repeat.delayElements(Duration.ofMillis(100))
    )
    .timeout(Duration.ofSeconds(5));

StepVerifier.create(waitUntilVisible)
    .expectNextMatches(order -> "ORD-123".equals(order.orderId()))
    .expectComplete()
    .verify(Duration.ofSeconds(6));
~~~

Đây là **mẫu minh họa**: cần kiểm tra API `repeatWhenEmpty` của phiên bản Reactor đang dùng và cách `searchClient` báo lỗi hoặc trả empty. Ở đây `timeout(...)` ngăn đợi vô hạn; `Mono.defer(...)` làm mỗi lần thử tạo truy vấn mới.

**Không nên dùng polling nếu resource có thể phát tín hiệu completion trực tiếp.** Khi có sự kiện xác nhận “index đã cập nhật”, chờ tín hiệu đó sẽ rõ nghĩa và ít tải hơn.

## 12. Kiểm thử time-based logic với virtual time

Một bài test khác có thể phụ thuộc operator `delayElement`, `timeout` hoặc `retryWhen`. Đợi thời gian thật trong mọi test làm suite chậm và không ổn định.

Project Reactor hỗ trợ `StepVerifier.withVirtualTime(...)` cho các publisher sử dụng scheduler tương thích. Ví dụ:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofMinutes(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(5))
    .expectNext(0L)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

`Mono.delay(Duration.ofMinutes(5))` được tạo **bên trong supplier** để virtual scheduler được kích hoạt trước khi publisher được xây dựng. Test có thể kiểm chứng hành vi 5 phút ảo mà không phải ngủ 5 phút thực.

### 12.1. Giới hạn của virtual time

- Không tự làm database, Kafka, Redis, HTTP server hoặc external system chạy theo đồng hồ ảo.
- Không có tác dụng với source dùng scheduler riêng hoặc clock hệ thống không nằm dưới scheduler của Reactor.
- Nếu test dùng virtual time trong môi trường song song, cần biết nó có thể thay đổi scheduler factory dùng chung; cô lập bài test hoặc áp dụng best practices của Reactor.
- Nếu publisher được tạo **trước** khi bật virtual time, một số timer có thể không chịu tác động như mong muốn.
- Vẫn cần timeout khi `verify(...)` để tránh test treo.

Virtual time phù hợp **unit test operator/time logic**. Khi contract test phải xác minh phản hồi HTTP thật, thường tốt hơn là cố định clock hoặc mock logic delay có chủ đích, chứ không đưa time manipulation vào toàn bộ web context.

## 13. Tài nguyên chặn bắt buộc: phải cô lập khỏi event loop

Một ứng dụng có thể cần gọi thư viện blocking cũ như JDBC hoặc file I/O truyền thống. Trong reactive code, cách tiếp cận thường được dùng là chuyển tác vụ blocking sang scheduler phù hợp, chẳng hạn `Schedulers.boundedElastic()`:

~~~java
Mono<LegacyResult> result = Mono
    .fromCallable(() -> legacyClient.load("ORD-123"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Ý nghĩa:

- `fromCallable(...)` trì hoãn việc gọi thư viện blocking cho tới lúc subscribe.
- `subscribeOn(boundedElastic())` định vị thao tác blocking lên một nhóm thread thích hợp hơn event loop.
- Điều này giúp tránh chặn event loop, nhưng **không biến thư viện blocking thành non-blocking** và không xóa nguy cơ timeout/connection exhaustion.

Với fixture test, ưu tiên client/database reactive hoặc mock. Nếu một bước setup bắt buộc dùng blocking API, chạy nó ở test setup thread ngoài event loop với timeout/cleanup rõ ràng. Không rải `boundedElastic()` vô tội vạ lên mọi publisher: điều đó làm mất sự đơn giản và có thể che các lỗi thiết kế của producer.

### 13.1. Nhận diện blocking ngoài ý muốn

Các dấu hiệu cần chú ý:

- `IllegalStateException: block()/blockFirst()/blockLast() are blocking ...`.
- Request timeout khi có nhiều lời gọi đồng thời dù logic đơn giản.
- CPU hoặc event loop không xử lý được task khác khi có tác vụ I/O lâu.
- Test chỉ fail khi chạy toàn suite, không fail khi chạy từng contract.
- Một method controller gọi `Future.get()`, `Thread.sleep(...)` hoặc synchronous database API.

Có thể bổ sung BlockHound trong test thích hợp để phát hiện blocking call trên non-blocking thread, nhưng cần cấu hình và tương thích thư viện đúng; không coi nó là điều kiện bắt buộc để viết hợp đồng.

## 14. Đọc generated contract test để khoanh vùng lỗi reactive

Contract verifier sinh request và assertions từ DSL. Khi test fail, cần phân biệt **lỗi hành vi HTTP thực sự** với **race trong chuẩn bị dữ liệu**.

Ví dụ lỗi:

~~~text
Contract: get_confirmed_order
Expected status: 200
Actual status: 404
~~~

Điều tra theo thứ tự:

1. Generated test đã gọi đúng `GET /api/orders/ORD-123` chưa?
2. Test mode có phù hợp `WEBTESTCLIENT` và base class được kế thừa đúng không?
3. `@BeforeEach` có thực thi không?
4. Fixture dùng reactive repository có **được subscribe và hoàn tất** trước request không?
5. Test có đang chia sẻ ID/database với test khác không?
6. Controller/serializer có thay đổi khiến producer thật không còn đáp ứng contract không?

Nếu chạy test riêng lẻ pass nhưng chạy song song fail, nghi ngờ **shared state hoặc sequencing**. Nếu fail ổn định sau khi producer đổi path/field/status, xem xét **breaking change**.

### 14.1. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `404` không ổn định | Seed với `subscribe()` rồi request chạy trước | Chờ seed completion hoặc mock `Mono.just(...)` |
| Test fail khi chạy song song | Dùng chung ID, cache, sink, DB, client tĩnh | Cô lập fixture và cấu hình client |
| `IllegalStateException` về blocking | Gọi `block()` trên event-loop thread | Compose publisher hoặc chuyển blocking work ra đúng scheduler |
| Test treo | Publisher không hoàn tất hoặc verifier không timeout | Thêm timeout, kiểm tra lifecycle và error |
| `onError` trong setup bị bỏ qua | `subscribe()` không có error handler/không kiểm chứng | Dùng `StepVerifier` và assertion cho lỗi |
| Fixture không xuất hiện | Chỉ tạo Mono, không subscribe | Thực thi và xác minh pipeline |
| Fixture bị xóa | `deleteAll()` và `save()` subscribe độc lập | Compose bằng `then(...)` |
| `Connection refused` | Dùng explicit mode nhưng server chưa chạy | Cấu hình server/port hoặc mode phù hợp |
| Context load fail | `@WebFluxTest` thiếu mock/import, sai dependency | Kiểm tra bean graph và annotation |
| Response body sai kiểu | JSON serializer/DTO khác contract | Sửa producer/schema theo cam kết |
| HTTP `200` nhưng thiếu message | HTTP contract không kiểm chứng side effect | Bổ sung messaging/integration test |
| Có stub nhưng consumer test sai | Stub version/matcher không đúng | Kiểm tra Stub Runner và request runtime |
| Build xanh với 0 tests | Plugin hoặc runner bỏ qua generated tests | Kiểm tra source path và test execution count |

### 14.2. Cách báo cáo một race condition hữu ích

Thay vì ghi “CI flaky”, ghi đủ:

- Contract/source test nào fail và tỷ lệ tái hiện.
- Request/response thực tế, status, body.
- Setup thực hiện publisher nào, ở thời điểm nào và đợi completion bằng cách gì.
- Có chạy parallel hay dùng chung database/topic/client không.
- Timeline các log `seed started → seed completed → request sent`.
- Cách sửa sequencing và kết quả chạy lặp lại sau sửa.

Nhờ đó nhóm phân biệt được **lỗi hạ tầng test** với **thay đổi API gây hỏng consumer**.

## 15. Kiểm thử phản hồi HTTP chậm và timeout của client

Với WebTestClient, timeout kiểm tra response có thể phát sinh từ:

- Producer không phát `onNext` hoặc `onComplete`.
- Tác vụ blocking làm nghẽn event loop.
- Fixture chưa sẵn sàng, làm request chờ phụ thuộc.
- Kết nối tới downstream timeout.
- Test client đặt `responseTimeout` quá ngắn.

Một WebTestClient trực tiếp có thể được cấu hình response timeout trong test:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrderController(orderQuery))
    .configureClient()
    .responseTimeout(Duration.ofSeconds(5))
    .build();
~~~

Cấu hình này chỉ là **timeout của test client**, không sửa logic producer. Nếu service có hợp đồng latency/SLA, nó cần test hiệu năng và điều kiện môi trường thực tế riêng; không đánh đồng một HTTP contract test đơn lẻ với performance test.

## 16. Producer verification, stub và CI: ba loại đồng bộ khác nhau

~~~mermaid
flowchart LR
    C["Groovy/YAML contract"] --> G["Sinh generated producer tests"]
    G --> S["Base setup: fixture sẵn sàng"]
    S --> H["WebTestClient gọi WebFlux producer"]
    H --> A{"Assertions khớp?"}
    A -- "Không" --> F["Chặn build"]
    A -- "Có" --> P["Producer verification đạt"]
    C --> M["Sinh stub mappings"]
    P --> R["Phát hành stub có version"]
    M --> R
    R --> U["Consumer test qua Stub Runner"]
~~~

Cần phân biệt:

1. **Đồng bộ fixture phía producer:** Đảm bảo dữ liệu/mock/bus sẵn sàng trước request.
2. **Đồng bộ HTTP response:** Generated test đợi phản hồi và assertions theo test mode; không nên tự chèn `Thread.sleep`.
3. **Đồng bộ consumer/stub:** Consumer gửi request đến stub và kiểm tra response; việc producer dùng reactive hay MVC bên trong không làm stub tự nhiên có race giống database fixture producer.

**Stub không thực thi reactive repository của producer.** Vì vậy consumer test với Stub Runner có thể xanh dù producer verification fail do fixture race hoặc producer đổi API. Hai loại kiểm thử bổ sung nhau; cần vận hành pipeline phát hành chỉ sau khi producer tests đạt.

### 16.1. Lệnh CI minh họa

Với Maven dự án đã cấu hình Spring Cloud Contract plugin:

~~~bash
./mvnw -B clean verify
~~~

Với Gradle dự án đã cấu hình plugin và test tasks:

~~~bash
./gradlew clean build
~~~

Không mặc định `BUILD SUCCESS` là đủ. CI cần xác minh:

- Contract Groovy/YAML được phát hiện đúng.
- Generated producer tests được sinh, biên dịch và **thực thi**.
- Test mode `WEBTESTCLIENT` và base class đúng stack WebFlux.
- Fixture setup hoàn tất hoặc mock publisher ổn định trước request.
- Timeout hữu hạn và isolation rõ ràng.
- Lỗi `404` do race không bị che bằng cách nới contract.
- Stub artifact được phát hành theo đúng version producer đã xác minh.
- Consumer CI dùng Stub Runner chạy các kịch bản consumer cần.

## 17. Bài thực hành: sửa flaky test cho Inventory Service

Giả sử `Inventory Service` dùng Spring WebFlux + R2DBC. Consumer gọi:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Phản hồi kỳ vọng:

~~~json
{
  "sku": "SKU-100",
  "quantity": 8,
  "available": true
}
~~~

### 17.1. Contract Groovy

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('inventory_get_available')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            quantity: 8,
            available: true
        )
    }
}
~~~

### 17.2. Bài A — Phát hiện race trong base class

Đoạn setup sai:

~~~java
@BeforeEach
protected void setUp() {
    inventoryRepository.deleteAll().subscribe();
    inventoryRepository.save(
        new InventoryEntity("SKU-100", 8, true)
    ).subscribe();
}
~~~

Hãy chỉ ra ba vấn đề:

1. Hai subscriptions độc lập không bảo đảm `deleteAll` xong trước `save`.
2. JUnit không đợi cả hai publisher hoàn tất trước generated request.
3. Các test chạy song song có thể xóa dữ liệu của nhau.

### 17.3. Bài B — Sửa bằng pipeline có completion

Gợi ý:

~~~java
@BeforeEach
protected void setUp() {
    Mono<Void> arrange = inventoryRepository.deleteAll()
        .then(inventoryRepository.save(
            new InventoryEntity("SKU-100", 8, true)
        ))
        .then();

    StepVerifier.create(arrange)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

Sau khi bảo đảm môi trường test **có database cô lập**, thêm một test kiểm tra record có thể đọc lại. Nếu database dùng chung, đổi chiến lược từ `deleteAll` sang ID test riêng/cleanup chọn lọc.

### 17.4. Bài C — Thay bằng mock cho web slice

Nếu mục tiêu chỉ là kiểm tra HTTP mapping, JSON và status, tạo `@WebFluxTest(InventoryController.class)`, mock `InventoryQuery` và trả:

~~~java
given(inventoryQuery.findBySku("SKU-100"))
    .willReturn(Mono.just(
        new InventoryView("SKU-100", 8, true)
    ));
~~~

So sánh:

| Chiến lược | Lợi ích | Điều không kiểm chứng |
| --- | --- | --- |
| Reactive repository thật, seed có completion | Kiểm tra đường đọc/ghi dữ liệu thực hơn | Không tự bao phủ mọi downstream/broker |
| Mock `Mono.just(...)` trong web slice | Nhanh, deterministic, ít race | Không kiểm tra persistence thật |

### 17.5. Bài D — Kiểm tra tác động chạy song song

Tạo hai test với **hai SKU riêng**, hoặc dùng database/test schema riêng. Chạy lặp một nhóm test và kiểm tra:

- Không có `404` xuất hiện ngẫu nhiên.
- Không còn phụ thuộc `Thread.sleep`.
- Khi cố tình bỏ `subscribe`/`StepVerifier`, test không còn được coi là đã setup đúng.
- Khi đổi field `quantity` từ number thành String, generated contract test có thể phát hiện mismatch nếu assertions bảo vệ đúng kiểu.
- Nếu producer thay path `/api/inventory/SKU-100` thành `/api/stock/SKU-100` và bỏ path cũ, contract test phải phát hiện breaking change thật.

### 17.6. Bài E — Thực hành với thời gian ảo

Viết unit test cho operator giả định đợi 30 giây trước khi phát trạng thái `READY`, dùng `StepVerifier.withVirtualTime(...)` thay cho `Thread.sleep(30000)`. Giải thích vì sao publisher phải được xây dựng trong supplier và vì sao virtual time không thể thay thế database fixture seeding.

### 17.7. Câu hỏi tự đánh giá

1. Vì sao `repository.save(entity)` chưa chắc đã thực thi?
2. Vì sao `subscribe()` trong `@BeforeEach` có thể gây race?
3. `StepVerifier.verify(Duration)` có “block” không? Nó được phép chạy ở luồng nào?
4. Vì sao gọi `block()` trong controller WebFlux nguy hiểm?
5. Khi nào `Mono.just(...)` là chiến lược fixture tốt hơn reactive database thật?
6. Test HTTP `202 Accepted` có chứng minh message đã phát không?
7. Vì sao `deleteAll()` nguy hiểm khi tests chia sẻ database?
8. Khi parallel tests dùng RestAssuredWebTestClient, nên tránh dạng cấu hình nào?
9. Làm sao phân biệt `404` do fixture chưa sẵn sàng với `404` do producer bỏ endpoint?
10. Vì sao consumer test với Stub Runner không thay thế producer verification?

**Gợi ý:** Reactor publisher thường lazy; subscribe riêng không bảo đảm hoàn tất; `StepVerifier.verify(...)` chờ có timeout trên test thread; event loop cần non-blocking; mock tốt cho web-slice; message cần test riêng; isolation giải quyết race; xem generated request, setup và response trước khi kết luận breaking change.

## 18. Checklist trước khi kết luận reactive contract test ổn định

- [ ] DSL mô tả đúng HTTP method, path, headers và response mà consumer sử dụng.
- [ ] Producer dùng test mode hỗ trợ WebFlux, ví dụ `WEBTESTCLIENT`, với base class tương ứng.
- [ ] Không có `block()` hoặc `Thread.sleep` bên trong pipeline phục vụ request trên event loop.
- [ ] Không dùng `subscribe()` fire-and-forget trong `@BeforeEach` để seed dữ liệu cần cho request.
- [ ] Pipeline chuẩn bị fixture có thứ tự và được xác minh hoàn tất.
- [ ] Các điểm chờ có timeout hữu hạn; không dùng polling hoặc sleep vô hạn.
- [ ] Mock reactive dependencies trả publisher ổn định khi test chỉ cần web slice.
- [ ] Reactive database/test resources được cô lập, không `deleteAll` trên dữ liệu dùng chung.
- [ ] Các test song song không sửa cùng ID, mock, sink, cache hoặc static client config.
- [ ] Subscriber quan sát hot publisher sẵn sàng trước khi trigger side effect.
- [ ] Có correlation ID khi đọc message/event từ tài nguyên chung.
- [ ] Virtual time chỉ dùng đúng phạm vi operator/scheduler hỗ trợ.
- [ ] Generated tests được thực thi; tránh build xanh với 0 tests.
- [ ] Lỗi setup được phân biệt với response mismatch/breaking change thật.
- [ ] Chỉ phát hành stub sau khi producer verification đạt và consumer vẫn chạy Stub Runner đúng version.
- [ ] Những đặc tính broker delivery, idempotency, latency và security có test bổ sung ở tầng phù hợp.

## 19. Tài liệu tham khảo

- [Spring Cloud Contract — WebFlux with WebTestClient](https://docs.spring.io/spring-cloud-contract/reference/project-features-flows/feature-webflux.html): cấu hình `testMode=WEBTESTCLIENT` và base class cho WebFlux.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử WebFlux qua controller/application context hoặc server thật.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, giới hạn thời gian chờ, virtual time và kiểm chứng tín hiệu.
- [REST Assured — Spring WebTestClient](https://rest-assured.io/docs/spring/web-test-client/): setup `RestAssuredWebTestClient` và quản lý client khi chạy song song.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): khai báo method, path và response body.
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): plugin producer verification, stubs và vòng đời build.

**Ghi nhớ:** Trong kiểm thử reactive, **bắt đầu công việc không đồng nghĩa công việc đã hoàn tất**. `subscribe()` tách rời trong phần chuẩn bị tạo race; `Thread.sleep` chỉ đoán thời điểm; `block()` trên event loop có thể làm ứng dụng lỗi. Hãy **compose publisher đúng thứ tự**, đợi tín hiệu hoàn tất có giới hạn **trên test thread** khi cần, cô lập dữ liệu chạy song song hoặc mock dependency bằng `Mono.just(...)` cho web slice. Sau đó mới để generated producer test gửi request và kiểm chứng HTTP contract trước khi phát hành stub cho consumer.
