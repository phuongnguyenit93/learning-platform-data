# Thiết lập fixture, xác thực và trạng thái ban đầu trong base test

Trong **Spring Cloud Contract**, một file hợp đồng mô tả điều mà **producer** phải đáp ứng khi **consumer** gửi request hoặc nhận thông điệp. **Contract Verifier** có thể sinh các bài kiểm thử từ hợp đồng Groovy/YAML DSL, nhưng những bài test ấy không tự biết phải chuẩn bị đơn hàng nào trong cơ sở dữ liệu, dùng token xác thực gì, hoặc đưa ứng dụng về trạng thái nào trước mỗi lần chạy. Đó là nhiệm vụ quan trọng của **base test**.

Bài thuộc chương **Base test** của mô-đun **SPRING_CLOUD_CONTRACT**. Chúng ta sẽ xây dựng một base test cho producer HTTP bằng Spring Boot, JUnit 5 và MockMvc: **tạo dữ liệu fixture xác định**, **thiết lập xác thực bằng Spring Security** và **đưa trạng thái ban đầu về đúng giả định của hợp đồng**. Sau đó, ta kết nối kết quả kiểm thử producer với stub phát hành cho consumer dùng bằng Stub Runner và với cổng kiểm tra trong CI.

Điểm cần nắm chắc: **fixture không phải là hợp đồng**. Hợp đồng quy định request/response quan sát được; fixture tạo điều kiện để producer thực sự có thể đáp ứng. Nếu fixture sai, test có thể thất bại do dữ liệu thiếu chứ không phải do API vi phạm; nếu fixture quá dễ dãi hoặc dùng mock sai chỗ, test có thể xanh trong khi producer thật không thực hiện đúng hành vi quan trọng.

## 1. Base test cung cấp những gì?

Trong một dự án đã cấu hình Spring Cloud Contract Verifier, các generated tests thường **kế thừa một lớp cơ sở** được chỉ định trong plugin. Lớp này chịu trách nhiệm tạo môi trường chung, không thay thế nội dung assertion của từng hợp đồng.

| Trách nhiệm | Ví dụ | Nếu thiếu hoặc sai |
| --- | --- | --- |
| **Test context** | Khởi động Spring Boot, controller, security filter và repository cần thiết. | Generated test không chạy được hoặc gọi nhầm đối tượng. |
| **HTTP test client** | Nối `RestAssuredMockMvc` với `MockMvc` trong chế độ `MOCKMVC`. | Request không tới controller cần kiểm. |
| **Fixture** | Đơn hàng ID `42` tồn tại, có `status=PAID`. | Test hợp đồng 200 nhận 404 do không có dữ liệu. |
| **Xác thực/ủy quyền** | Token test mang scope `orders.read`, hoặc thiết lập user bảo mật theo chính sách. | Test thành công nhận 401/403 hoặc test bảo mật bị vượt qua không chủ ý. |
| **Trạng thái ban đầu** | Xóa dữ liệu cũ, seed lại trước từng test; reset mock hoặc clock khi cần. | Test phụ thuộc thứ tự chạy, lúc pass lúc fail. |
| **Độ cô lập** | Mỗi test bắt đầu từ trạng thái có thể dự đoán, kể cả khi chạy lại riêng lẻ. | Một test sửa dữ liệu làm test kế tiếp bị ảnh hưởng. |

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML"] --> B["Contract Verifier sinh test"]
    B --> C["Generated test kế thừa base test"]
    C --> D["Base test: context, fixture, auth, state"]
    D --> E["Gọi producer qua MockMvc/HTTP"]
    E --> F{"Status, header, body khớp?"}
    F -->|Không| G["Build thất bại, điều tra nguồn sai lệch"]
    F -->|Có| H["Cho phép quy trình đóng gói/publish stub"]
    H --> I["Consumer kiểm thử bằng Stub Runner"]
~~~

Về nguyên tắc, **lớp cơ sở nên thiết lập dữ liệu và hạ tầng; contract nên chứa kỳ vọng giao tiếp**. Tránh viết hàng loạt assertion nghiệp vụ vào một base test dùng chung, vì test được sinh có thể cùng chạy lại logic không liên quan, khó tìm nguyên nhân thất bại.

## 2. Tình huống mẫu: đơn hàng tồn tại và quyền truy cập

Giả sử **Order Service** cung cấp endpoint:

~~~http
GET /api/orders/42
Authorization: Bearer contract-read-token
Accept: application/json
~~~

Phản hồi hợp lệ khi caller có quyền đọc:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

Ta muốn kiểm bốn tình huống tách biệt:

| Tình huống | Trạng thái dữ liệu | Xác thực/ủy quyền | Kỳ vọng |
| --- | --- | --- | --- |
| **Đọc đơn thành công** | Đơn `42` tồn tại, trạng thái `PAID`. | Token hợp lệ có scope `orders.read`. | `200` và JSON đúng. |
| **Thiếu xác thực** | Dữ liệu có thể vẫn tồn tại. | Không gửi header `Authorization`. | `401 Unauthorized`. |
| **Không đủ quyền** | Đơn `42` tồn tại. | Token được chấp nhận nhưng chỉ có scope `profile.read`. | `403 Forbidden`. |
| **Không tìm thấy đơn** | Không tồn tại đơn `99`. | Token có scope `orders.read`. | `404 Not Found`. |

Điều phân biệt lỗi rất quan trọng: **401** thường nói request chưa được xác thực phù hợp; **403** nói danh tính đã được nhận nhưng không đủ quyền; **404** trong ví dụ là do **thiếu tài nguyên**, không phải do thiếu stub mapping. Việc hợp đồng kiểm đủ các nhánh giúp producer không vô tình chuyển một lỗi xác thực thành lỗi nghiệp vụ.

**Phạm vi minh họa:** ví dụ dùng **Spring Security OAuth2 Resource Server (JWT)**, Spring MVC, Spring Data JPA và H2 trong test. Token và dữ liệu đều là **fixture giả**, không dùng để đăng nhập hệ thống thật. Cách cấu hình sẽ khác nếu dự án sử dụng session/cookie, API key, mTLS hoặc phương thức xác thực khác.

## 3. Định nghĩa hợp đồng trước khi chuẩn bị fixture

Ta đặt các hợp đồng tại `src/test/resources/contracts/orders/get_order.groovy` của producer. Với Groovy DSL, một file có thể trả về danh sách nhiều `Contract.make { ... }` độc lập:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldReadPaidOrder'
        request {
            method 'GET'
            url '/api/orders/42'
            headers {
                header('Authorization', 'Bearer contract-read-token')
            }
        }
        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body(id: 42, status: 'PAID')
        }
    },
    Contract.make {
        name 'shouldRejectAnonymousRequest'
        request {
            method 'GET'
            url '/api/orders/42'
        }
        response {
            status 401
        }
    },
    Contract.make {
        name 'shouldRejectCallerWithoutReadScope'
        request {
            method 'GET'
            url '/api/orders/42'
            headers {
                header('Authorization', 'Bearer contract-no-scope-token')
            }
        }
        response {
            status 403
        }
    },
    Contract.make {
        name 'shouldReportMissingOrder'
        request {
            method 'GET'
            url '/api/orders/99'
            headers {
                header('Authorization', 'Bearer contract-read-token')
            }
        }
        response {
            status 404
        }
    }
]
~~~

Mỗi hợp đồng quy định **một request và một response mong đợi**. Hợp đồng không biết `42` có trong database hay JWT decoder hiểu hai token test ra sao; phần đó phải được **base test và ứng dụng** cung cấp. Các request được phân biệt bằng đường dẫn hoặc header `Authorization`, tránh stub mapping chồng lấn.

**Lưu ý:** ta chỉ kiểm mã trạng thái cho ba nhánh lỗi vì ví dụ chưa quy định schema lỗi. Nếu consumer phụ thuộc vào `code` hoặc `message`, hãy bổ sung chúng vào hợp đồng và kiểm chúng trong producer/consumer tests; đừng mặc nhiên xem mọi response cùng status là tương đương.

Nếu nhóm chọn **YAML DSL**, mỗi tình huống có thể đặt trong file riêng. Ví dụ hợp đồng thành công:

~~~yaml
description: Đọc đơn hàng đã thanh toán với quyền orders.read
request:
  method: GET
  url: /api/orders/42
  headers:
    Authorization: Bearer contract-read-token
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Chỉ cần chọn **một định dạng hợp đồng có hiệu lực** cho cùng tình huống trong build; không đồng thời nạp cả YAML và Groovy tương đương rồi vô tình tạo hai bộ test/stub trùng nhau.

## 4. Producer tối thiểu: controller, repository và bảo mật thật

Để fixture được kiểm thử trên một tầng dữ liệu thực, ví dụ sử dụng Spring Data JPA. Mã dưới đây là các **mảnh ghép minh họa** trong package `com.acme.orders`; ứng dụng cần có class `@SpringBootApplication` và cấu hình datasource tương ứng.

Entity đơn giản:

~~~java
package com.acme.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {}

    public OrderEntity(Long id, String status) {
        this.id = id;
        this.status = status;
    }

    public Long getId() { return id; }
    public String getStatus() { return status; }
}
~~~

Repository:

~~~java
package com.acme.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {}
~~~

Controller gọi **repository thật**:

~~~java
package com.acme.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderRepository orders;

    public OrderController(OrderRepository orders) {
        this.orders = orders;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderView getOrder(@PathVariable long id) {
        OrderEntity entity = orders.findById(id)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
        return new OrderView(entity.getId(), entity.getStatus());
    }

    public record OrderView(long id, String status) {}
}
~~~

Security configuration ví dụ:

~~~java
package com.acme.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrderSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Phần bảo mật này yêu cầu request `GET /api/orders/**` có **authority `SCOPE_orders.read`**. Cơ chế Resource Server thực hiện bước đọc bearer token, gọi `JwtDecoder` để xác thực token và chuyển claim `scope` thành authority; ví dụ sau sẽ **mock riêng decoder** trong test, nhưng vẫn chạy **security filter chain và cơ chế kiểm quyền**.

Để dựng ví dụ, project producer cần các dependency tương ứng: `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-oauth2-resource-server`; ở test có `spring-boot-starter-test`, `spring-cloud-starter-contract-verifier` và `com.h2database:h2` (scope `test`). Thư viện/version Spring Cloud Contract phải tương thích với Spring Boot/Spring Cloud đang dùng.

## 5. Cô lập cơ sở dữ liệu và profile của contract tests

Không nên chạy generated producer tests trên **database phát triển dùng chung** hay database production. Đặt file cấu hình dành riêng cho test ở `src/test/resources/application-contract.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:contractdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Profile `contract` sẽ được kích hoạt bởi base test. Cấu hình này minh họa **H2 in-memory** và cho Hibernate tạo schema riêng cho bài thực hành. Trong dự án thật, nếu producer dùng SQL/tính năng database không tương thích H2, nên dùng **Testcontainers với cùng loại database production**, kết hợp migration thật, thay vì ép mọi test chạy H2 rồi bỏ sót sai biệt.

**Không đưa `ddl-auto: create-drop` vào profile production.** Cấu hình để xóa/tạo bảng chỉ phù hợp môi trường test cô lập. Mục đích là có dữ liệu xác định, không phá dữ liệu của ứng dụng thật.

## 6. Base test hoàn chỉnh: fixture + JWT mock + MockMvc

Tạo `src/test/java/com/acme/orders/ContractTestBase.java`. Đây là lớp mà **generated producer tests sẽ kế thừa**:

~~~java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMockMvc
@ActiveProfiles("contract")
public abstract class ContractTestBase {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderRepository orders;

    @MockBean
    private JwtDecoder jwtDecoder;

    @BeforeEach
    void prepareContracts() {
        // 1. Mọi hợp đồng bắt đầu ở trạng thái biết trước.
        orders.deleteAll();
        orders.save(new OrderEntity(42L, "PAID"));

        // 2. Giả lập kết quả xác thực token, giữ filter/authorization thật.
        Jwt withPermission = Jwt.withTokenValue("contract-read-token")
            .header("alg", "RS256")
            .claim("sub", "billing-service")
            .claim("scope", "orders.read")
            .build();

        Jwt withoutPermission = Jwt.withTokenValue("contract-no-scope-token")
            .header("alg", "RS256")
            .claim("sub", "billing-service")
            .claim("scope", "profile.read")
            .build();

        when(jwtDecoder.decode("contract-read-token"))
            .thenReturn(withPermission);
        when(jwtDecoder.decode("contract-no-scope-token"))
            .thenReturn(withoutPermission);

        // 3. Generated tests dùng RestAssuredMockMvc đến Spring MVC thật.
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Ví dụ dùng API `@MockBean` phù hợp với **Spring Boot 3.3.x**. Từ các phiên bản Spring Boot/Spring Framework mới hơn, API này bị deprecate theo hướng dùng `@MockitoBean` của Spring Test; khi áp dụng vào dự án hiện tại, chọn annotation tương thích và điều chỉnh import. Không nên sao chép các phiên bản annotation trộn lẫn mà không kiểm classpath.

### 6.1. Mỗi phần trong base test bảo vệ điều gì?

| Thành phần | Ý nghĩa |
| --- | --- |
| `@SpringBootTest(classes = OrderApplication.class)` | Khởi động ứng dụng producer trong test context. |
| `@AutoConfigureMockMvc` | Tạo `MockMvc` có thể đi qua Spring MVC và các filter được tích hợp. |
| `@ActiveProfiles("contract")` | Dùng datasource/config riêng cho contract test. |
| `orders.deleteAll()` | Loại dữ liệu còn lại từ test trước, trước khi seed. |
| `orders.save(new OrderEntity(42L, "PAID"))` | Bảo đảm request hợp lệ tới đơn 42 nhận được đúng dữ liệu. |
| `@MockBean JwtDecoder` | Thay nguồn xác thực JWT bên ngoài bằng decoder có phản hồi xác định. |
| `when(jwtDecoder.decode(...))` | Quy định token test nào mang scope phù hợp hoặc không phù hợp. |
| `RestAssuredMockMvc.mockMvc(mockMvc)` | Nối Rest Assured MockMvc với ứng dụng được Spring test khởi tạo. |

Thứ tự setup có ý nghĩa: **dữ liệu và xác thực phải sẵn sàng trước khi generated test gửi request**. `@BeforeEach` trong lớp cơ sở được JUnit Jupiter thực thi cho các test kế thừa, nên mỗi tình huống bắt đầu từ một bản dữ liệu giống nhau; một test trước đó không được giả định đã chuẩn bị đơn cho test kế tiếp.

**Giới hạn của việc mock decoder:** ví dụ kiểm được yêu cầu có bearer token, cách Spring Security chuyển scope thành authority và điều kiện 401/403 của endpoint. Nó **không kiểm chữ ký, hạn sử dụng, issuer, audience hay việc tải JWKS thực**. Các điều kiện đó cần được xác minh bằng integration/security tests riêng với decoder/configuration thích hợp. Một chuỗi như `contract-read-token` không phải JWT thật; nó chỉ hoạt động vì `JwtDecoder` đã được thay bằng mock **trong profile test**.

### 6.2. Vì sao không gắn `@WithMockUser` lên mọi generated test?

`@WithMockUser` hữu ích khi chỉ muốn kiểm logic được bảo vệ **dưới một danh tính đã xác thực**. Tuy nhiên, nếu đặt nó trên base class cho **tất cả** generated tests, request **không gửi token** vẫn có thể được xử lý trong security context đã có user giả, làm tình huống `401` không còn kiểm đúng đường đi xác thực.

Với hợp đồng có cả `200`, `401` và `403` như ví dụ, tốt hơn là để **request header** quyết định trường hợp nào được xác thực; mock decoder chỉ thay cơ chế xác thực JWT bên ngoài. Không tắt filter bằng `@AutoConfigureMockMvc(addFilters = false)` khi mục tiêu là kiểm các yêu cầu authorization.

## 7. Khai báo plugin để generated tests kế thừa đúng lớp

Ví dụ phần cấu hình Maven trong `pom.xml` của producer:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>4.1.5</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

Phiên bản `4.1.5` là **ví dụ cho hệ Spring Cloud Contract 4.1.x**, không phải chỉ dẫn dùng phiên bản mới nhất; hãy dùng bộ Spring Boot, Spring Cloud BOM và Spring Cloud Contract plugin **tương thích** với dự án. Đây là **đoạn plugin**, không phải POM hoàn chỉnh: cần khai báo các dependencies test phù hợp và bảo đảm Maven/Gradle thực thi generated tests.

Ba dòng quan trọng:

- `testFramework=JUNIT5`: generated tests dùng JUnit Jupiter và kế thừa setup `@BeforeEach` phù hợp.
- `testMode=MOCKMVC`: test gọi Spring MVC trong test context; không phải khởi động HTTP socket riêng.
- `baseClassForTests`: tên package/class phải khớp **chính xác** với base test vừa tạo.

Nếu một dự án có nhiều nhóm hợp đồng cần fixture khác nhau, có thể cấu hình base class theo quy ước/đường dẫn hợp đồng mà phiên bản plugin hỗ trợ, hoặc tổ chức hierarchy/helper rõ ràng. Không đặt **mọi dữ liệu của mọi API** vào một base test khổng lồ: thời gian setup tăng và các bài kiểm thử không còn độc lập theo nghiệp vụ.

## 8. Kiểm tra bốn nhánh: 200, 401, 403 và 404

Khi chạy generated producer tests với fixture trên, kỳ vọng:

| Hợp đồng | Trước khi gửi request | Cách producer xử lý | Expected |
| --- | --- | --- | --- |
| `shouldReadPaidOrder` | Đơn 42 đã seed; decoder trả JWT scope `orders.read`. | Security cho qua, controller lấy đơn 42. | `200` + `PAID`. |
| `shouldRejectAnonymousRequest` | Đơn 42 vẫn có; request không có bearer token. | Security yêu cầu xác thực trước khi tới controller. | `401`. |
| `shouldRejectCallerWithoutReadScope` | Decoder trả JWT scope `profile.read`. | Caller được xác thực nhưng không có authority `SCOPE_orders.read`. | `403`. |
| `shouldReportMissingOrder` | Chỉ seed đơn 42; không có đơn 99; scope đọc hợp lệ. | Security cho qua, repository không tìm thấy ID 99. | `404`. |

**Không dùng `404` của stub để kết luận controller đã trả lỗi tài nguyên không tồn tại.** Generated producer tests ở bảng này gọi **producer thật qua MockMvc**, nên 404 từ controller có ý nghĩa. Còn trên HTTP stub, 404 cũng có thể đến từ **request không khớp mapping WireMock**. Nếu consumer cần xử lý lỗi tài nguyên, nên có body/header lỗi nghiệp vụ để kiểm được mapping cụ thể.

### 8.1. Tự kiểm khả năng bắt lỗi

Sau khi test chạy xanh, thực hiện riêng từng thay đổi và khôi phục trước khi thử tiếp:

1. Xóa lệnh seed đơn 42 → test `200` phải thất bại, vì fixture không còn dữ liệu.
2. Đổi trạng thái seed từ `PAID` sang `PENDING` nhưng giữ hợp đồng → generated test `200` phải thất bại vì JSON lệch.
3. Cho authority rule yêu cầu `SCOPE_orders.write` thay vì `SCOPE_orders.read` → test `200` có thể thành `403`, chỉ ra hợp đồng xác thực bị phá.
4. Vô hiệu hóa security filters trong MockMvc → các test `401`/`403` không còn được bảo vệ đáng tin cậy, có thể nhận kết quả khác mong đợi.
5. Seed thêm đơn 99 → test `404` phải thất bại vì tài nguyên không còn thiếu.

Khi một tình huống thất bại, hãy xác định **fixture không đáp ứng tiền điều kiện** hay **implementation vi phạm hợp đồng**. Không đổi hợp đồng sang một kết quả sai chỉ để build xanh.

## 9. Trạng thái ban đầu và tính độc lập giữa các bài test

`@BeforeEach` làm lại dữ liệu trước từng method giúp ví dụ dễ hiểu. Nhưng dự án thật có nhiều trạng thái ngoài database: cache, event đã phát, bộ đếm sequence, clock, thông điệp trong queue, file tạm và mock của hệ thống ngoài.

Một checklist isolation:

- **Database:** seed tối thiểu, xóa đúng dữ liệu của test; nếu dùng database chung cho nhiều test, tránh `deleteAll()` trên bảng có dữ liệu của bài test khác.
- **Transaction:** xác định phần nào cần commit để code ứng dụng đọc được; đừng mặc nhiên tin rollback của test luôn dọn được mọi thay đổi.
- **Cache:** xóa hoặc dùng key riêng cho mỗi tình huống; không để response lấy từ cache của test trước.
- **Clock/timezone:** cố định thời gian bằng `Clock` hoặc provider injectable nếu hợp đồng kiểm thời gian; tránh so `Instant.now()` theo thời gian thực.
- **Message/outbox:** xóa dữ liệu sự kiện hoặc dùng transaction/test fixture tách biệt; tránh assertion đọc message còn lại từ test trước.
- **Mock external dependencies:** reset và stub lại cho mỗi tình huống khi cần; không dựa vào số lần gọi của test khác.
- **ID tự sinh:** chỉ assert ID cố định nếu fixture thực sự bảo đảm nó; nếu producer tạo ID động, dùng matcher phù hợp trong hợp đồng.
- **Chạy song song:** test dùng cùng database/cache hoặc thay đổi cấu hình static của Rest Assured có thể va chạm; cần cô lập dữ liệu hoặc cấu hình parallel có kiểm soát.

**Bài học về thứ tự chạy:** generated producer tests có thể được tạo/đặt tên khác nhau khi thêm hợp đồng hoặc nâng plugin; không được dựa vào “test tạo trước, test xóa sau”. Mỗi tình huống phải có tiền điều kiện độc lập để có thể chạy riêng lẻ, chạy lại sau lỗi và chạy trong CI.

## 10. Khi nào nên dùng `@Sql`, factory fixture hoặc Testcontainers?

Không có một cách seed dữ liệu tối ưu cho mọi hệ thống:

| Cách thiết lập | Phù hợp khi | Rủi ro/cân nhắc |
| --- | --- | --- |
| `@BeforeEach` + repository | Fixture nhỏ, cần tạo object qua domain/repository. | Nếu nhiều test dùng chung database, dọn dữ liệu quá rộng có thể gây xung đột. |
| `@Sql` trước test | Muốn trạng thái SQL rõ ràng, có dữ liệu quan hệ phức tạp. | Script phụ thuộc schema và transaction; phải đồng bộ với migration. |
| Fixture builder/factory | Dữ liệu có nhiều trường nhưng chỉ vài trường cần thay đổi theo tình huống. | Factory ẩn quá nhiều mặc định khiến reviewer không nhìn thấy tiền điều kiện. |
| Testcontainers | Cần kiểm hành vi của PostgreSQL/MySQL/broker gần hệ thật. | Khởi động chậm hơn; CI cần runtime cho container và tài nguyên phù hợp. |
| Mock service/repository | Mục tiêu chỉ là kiểm mapping/controller/serialization ở mức slice. | Không kiểm được truy vấn, constraint hoặc lỗi integration bị mock bỏ qua. |

Ví dụ **thay cho** `orders.deleteAll()/save(...)`, có thể seed bằng SQL trước từng test:

~~~java
import org.springframework.test.context.jdbc.Sql;

@Sql(
    scripts = "/sql/order-contract-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
public abstract class ContractTestBase {
    // Giữ phần Spring context, MockMvc và auth setup phù hợp.
}
~~~

Script ví dụ tại `src/test/resources/sql/order-contract-fixture.sql`:

~~~sql
DELETE FROM orders;
INSERT INTO orders (id, status) VALUES (42, 'PAID');
~~~

**Chọn một cách seed chủ đạo** cho cùng fixture để tránh xóa/ghi hai lần không cần thiết. `@Sql` có thể tham gia transaction và context lifecycle theo cấu hình Spring Test; nếu test khởi động HTTP server thật, dữ liệu chưa commit trong transaction của test có thể **không nhìn thấy từ request ở thread khác**. Khi đó phải chủ động quản lý transaction/commit phù hợp.

Với Testcontainers, ngoài container database, vẫn cần **cơ chế reset dữ liệu** giữa các hợp đồng. Dùng database gần production giúp phát hiện khác biệt SQL nhưng không tự giải quyết test phụ thuộc trạng thái.

## 11. `MOCKMVC` khác `EXPLICIT` về fixture và xác thực

Base test ở mục 6 phục vụ chế độ `MOCKMVC`. Nếu chọn `EXPLICIT`, generated test gửi HTTP đến một server thực trong test. Ví dụ Spring Boot `@SpringBootTest(webEnvironment = RANDOM_PORT)` có thể khởi động ứng dụng, rồi test lấy `@LocalServerPort` để cấu hình HTTP client.

Những điểm cần điều chỉnh:

1. **HTTP client:** `RestAssuredMockMvc.mockMvc(mockMvc)` không còn là cách gửi request qua socket; base test phải cấu hình Rest Assured HTTP client cho đúng base URI/port hoặc client mà plugin sinh ra sử dụng.
2. **Fixture visibility:** request qua server thường chạy trong thread riêng, có transaction riêng. Dữ liệu seed cần được **commit/hiển thị** trước khi gửi HTTP.
3. **Security:** bearer token vẫn đi qua filter thật. Mock `JwtDecoder` có thể đủ để test phân quyền, nhưng không kiểm chữ ký/JWKS; nếu cần kiểm decoder thật, dùng cấu hình token/test keys phù hợp.
4. **Reset:** khi nhiều generated tests chia sẻ một server/database, phải quản lý cô lập dữ liệu và concurrency, đặc biệt khi test chạy song song.

Đối với **Spring WebFlux**, có thể dùng `WEBTESTCLIENT` nếu phiên bản plugin hỗ trợ; base test cần cung cấp WebTestClient hoặc binding tương ứng. Không sao chép nguyên thiết lập RestAssuredMockMvc vào một WebFlux base test rồi mong generated tests tự sử dụng nó.

Với **messaging contracts**, base test cần cơ chế kích hoạt gửi thông điệp, thiết lập broker/adapter giả hoặc thật và các assertion message, không thể thay thế bằng fixture MockMvc HTTP. Tuy vậy, nguyên tắc dữ liệu ban đầu, auth/authorization nếu có và reset trạng thái vẫn giống nhau.

## 12. Fixture đúng nhưng test vẫn xanh sai: những bẫy quan trọng

**Bẫy A — mock luôn phần đang cần xác minh.** Nếu mục tiêu là xác minh controller, request mapping và JSON serialization, mock service bên dưới có thể chấp nhận được. Nhưng nếu mục tiêu là chứng minh producer thực truy vấn đúng đơn hàng 42, mock toàn bộ repository/service sẽ che giấu lỗi database. Hãy xác định **ranh giới kiểm thử** rồi chọn fixture thật ở phần quan trọng.

**Bẫy B — bypass security làm 401/403 vô nghĩa.** Gắn `@WithMockUser` toàn cục, bật `addFilters=false` hoặc giả lập trực tiếp controller không qua security filter có thể làm kiểm thử “được xác thực” nhưng không còn kiểm đúng việc request cần bearer token. Nếu contract bao gồm authentication, hãy gửi header thật trong request và dùng một cơ chế xác thực thử nghiệm có kiểm soát.

**Bẫy C — dùng token test như token production.** Mock `JwtDecoder` chỉ phù hợp để kiểm nhánh filter/authorization. Muốn khẳng định xác minh chữ ký, issuer, audience, expiry, key rotation hoặc lỗi JWKS, phải chạy các security integration tests có decoder thật và dữ liệu chữ ký hợp lệ.

**Bẫy D — fixture chia sẻ giữa các test.** Một method đổi `PAID` thành `CANCELLED` có thể làm method khác fail tùy thứ tự chạy. Seed lại hoặc cô lập mỗi tình huống; đừng cố định thứ tự test để che lỗi.

**Bẫy E — test dùng `@Transactional` là đủ trong mọi chế độ.** Rollback có thể thuận tiện khi request chạy trong cùng test transaction, nhưng với HTTP server thật ở thread khác hoặc message consumer bất đồng bộ, dữ liệu/transaction nhìn thấy và tác dụng rollback khác nhau. Cần kiểm thực tế điều kiện transaction của từng test mode.

**Bẫy F — generated tests bị skip.** Base test biên dịch thành công không có nghĩa hợp đồng đã được kiểm. Cần nhìn thấy generated test classes/methods và báo cáo test có số lượng thực thi đúng, không chỉ dòng `BUILD SUCCESS`.

## 13. Stub Runner không mang theo fixture producer

Khi producer tests đạt, build có thể đóng gói stub theo classifier `stubs`, ví dụ:

~~~text
com.acme:order-service:1.0.0:stubs
order-service-1.0.0-stubs.jar
~~~

**Stub không phải một bản sao ứng dụng producer** và không chạy `ContractTestBase`, H2 hay `JwtDecoder` mock ở trên. Stub Runner dùng **mapping được sinh từ hợp đồng** để trả response đã mô tả cho các request phù hợp. Vì vậy:

- Consumer gửi `Authorization: Bearer contract-read-token` có thể nhận response `200` theo stub mapping, nhưng stub **không xác thực chữ ký JWT thật**.
- Consumer không gửi header có thể nhận `401` **nếu** có mapping hợp đồng cho tình huống đó; nếu request không match mapping nào, WireMock cũng có thể trả `404` do no-match.
- Việc thử `403` trên stub giúp consumer kiểm cách xử lý response lỗi, **không chứng minh** luật phân quyền của Spring Security đang hoạt động ở producer; điều đó thuộc generated producer test với security filter được thiết lập đúng.
- Các trạng thái 200/401/403/404 được stub mô phỏng độc lập; stub không tự truy vấn đơn 42 trong H2 hay đọc dữ liệu phát sinh từ test khác.

Một consumer test minh họa (cần có `OrderClient`, imports và test dependencies của consumer):

~~~java
@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientStubTest {

    @Autowired OrderClient orderClient;

    @Test
    void readsOrderWithAuthorizationHeader() {
        OrderDto dto = orderClient.getOrder(42L, "contract-read-token");
        assertThat(dto.status()).isEqualTo("PAID");
    }
}
~~~

Với `LOCAL`, artifact phải được producer cài vào Maven local trước đó. Với CI đa máy, producer cần publish stub lên Maven repository và consumer dùng `REMOTE`, `repositoryRoot` cùng credentials phù hợp. **Không cần khởi động producer thật để chạy consumer test với HTTP stub.**

## 14. Đưa fixture, auth và trạng thái ban đầu vào CI

Pipeline nên bảo đảm **test chạy trong môi trường cô lập** và **stub chỉ được phát hành sau khi producer đúng hợp đồng**:

~~~mermaid
flowchart TD
    A["Checkout mã producer + contracts"] --> B["Tạo database/test services cô lập"]
    B --> C["Verifier sinh generated tests"]
    C --> D["Base test seed fixture + mock auth phù hợp"]
    D --> E["Producer tests kiểm 200/401/403/404"]
    E --> F{"Tất cả test đạt?"}
    F -->|Không| G["Chặn publish; tìm lỗi fixture/auth/implementation"]
    F -->|Có| H["Đóng gói và publish artifact stubs"]
    H --> I["Consumer CI tải stub bằng Stub Runner"]
    I --> J["Chạy consumer contract tests với mã client thật"]
~~~

Các nguyên tắc cần thực hiện:

1. **Không dùng tài nguyên production** cho fixture. Secrets thật và token thật không thuộc source test hoặc hợp đồng.
2. **Không dựa vào thứ tự test.** Mỗi test cần khởi đầu xác định, có thể chạy một mình hoặc trong bộ test đầy đủ.
3. **Xác minh auth filter thật sự bật** nếu hợp đồng có 401/403. Test không được ngầm bypass security bằng annotation global.
4. **Quan sát số test được sinh và thực thi**, không coi build xanh với 0 generated tests là bằng chứng.
5. **Chặn publish stub khi producer verification thất bại**. Bản stub chưa được producer xác minh không nên xem là hợp đồng đáng tin.
6. **Ghim version stub cho consumer CI**, giữ lại những hợp đồng còn hiệu lực để phát hiện thay đổi API không tương thích với consumer cũ.
7. **Phân biệt test auth tầng controller và integration bảo mật thật**: nếu dự án cần bảo đảm JWT signature, issuer, audience và mTLS, phải có test khác bổ sung.

## 15. Bảng chẩn đoán lỗi trong base test

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra hoặc sửa |
| --- | --- | --- |
| `200` lại thành `404` trong producer test. | Thiếu fixture hoặc seed nhầm ID, profile dùng database khác. | Kiểm `@ActiveProfiles`, repository, bản ghi 42 ngay trước request. |
| `200` lại thành `401`. | Thiếu header, mock decoder chưa stub hoặc token không khớp. | So `Authorization` trong contract và `jwtDecoder.decode(...)`. |
| `200` lại thành `403`. | JWT thiếu scope hoặc security rule đòi authority khác. | Kiểm claim `scope` và `SCOPE_orders.read`. |
| Test `401` lại trả `200`. | `@WithMockUser` áp dụng mọi test, security filter bị tắt. | Gỡ mock user toàn cục, bật filter và kiểm request không có token. |
| Test `403` lại trả `401`. | Token “thiếu quyền” không được decoder chấp nhận. | Mock decoder trả JWT xác thực được nhưng có scope khác. |
| Test `404` lại trả `200`. | Dữ liệu 99 còn từ test trước hoặc fixture seed quá rộng. | Reset trạng thái cho từng method và chỉ seed 42. |
| Test pass riêng lẻ nhưng fail khi chạy cả bộ. | State/cache/mock/clock bị chia sẻ, chạy song song. | Cô lập test resources, reset fixture, kiểm parallel settings. |
| MockMvc test không đi qua authentication. | `addFilters=false` hoặc test gọi controller trực tiếp. | Dùng `@AutoConfigureMockMvc` tích hợp filters thích hợp. |
| Test `EXPLICIT` không thấy dữ liệu vừa seed. | Transaction chưa commit và HTTP request chạy thread khác. | Điều chỉnh transaction/seed hoặc dùng setup ngoài transaction test. |
| Generated tests không thấy `@BeforeEach`. | Sai tên base class, test framework khác JUnit 5. | Kiểm plugin `baseClassForTests` và mã generated test. |
| Consumer stub chạy xanh dù producer security hỏng. | Stub không chạy filter hay database producer. | Bắt buộc producer verification và bổ sung security integration tests. |

## 16. Bài thực hành và checklist hoàn thành

Hãy thử trên một ứng dụng Spring Boot dùng Spring Cloud Contract Verifier:

1. **Tạo bốn hợp đồng** HTTP như mục 3, tương ứng `200`/`401`/`403`/`404`.
2. **Thiết lập fixture riêng**: H2 test database chứa đơn 42 `PAID`, không có đơn 99; kiểm profile chỉ dùng cho test.
3. **Tạo base class JUnit 5 + MockMvc**: dùng `@BeforeEach` seed dữ liệu, mock `JwtDecoder` cho token hợp lệ và thiếu quyền, nối `RestAssuredMockMvc`.
4. **Chạy generated producer tests** bằng Maven hoặc Gradle phù hợp; xác nhận cả bốn tình huống được sinh và thực thi, không chỉ nhìn build status.
5. **Phá fixture có chủ đích**: đổi seed trạng thái thành `PENDING`, chạy lại và quan sát test `200` thất bại. Hoàn nguyên.
6. **Phá auth có chủ đích**: đổi scope của token hợp lệ sang `profile.read`; test `200` phải thất bại với 403. Hoàn nguyên.
7. **Tắt filters để kiểm độ nhạy** trong một lần chạy thử, quan sát test 401/403 có còn bảo vệ hành vi không; khôi phục.
8. **Thử chạy lại và chạy song song** trong điều kiện dự án cho phép, bảo đảm không có state leak giữa các generated tests.
9. **Đóng gói/cài hoặc publish stub sau khi producer test đạt**; dùng Stub Runner chạy consumer test đọc đơn và xử lý lỗi theo mapping đã định nghĩa.
10. **Ghi lại giới hạn**: base test đã bảo vệ controller/repository/security filter gì, và những điều nào vẫn cần kiểm JWT thật, database production hoặc message broker.

Checklist hoàn thành:

- [ ] Hợp đồng mô tả rõ request và kỳ vọng 200/401/403/404.
- [ ] Base test được generated test kế thừa, setup chạy trước từng method.
- [ ] Fixture có đơn 42 `PAID` và không có đơn 99, sử dụng datasource test cô lập.
- [ ] Mock JWT decoder không vô tình tắt security filter hoặc bypass 401/403.
- [ ] Đảo dữ liệu/trạng thái/quyền có chủ đích khiến đúng test thất bại.
- [ ] Producer test được thực thi và pass trước khi publish artifact `stubs`.
- [ ] Consumer dùng Stub Runner để kiểm mã client thật, không nhầm stub với producer.

## 17. Câu hỏi tự kiểm tra

1. Vì sao chỉ tạo hợp đồng `GET /api/orders/42` chưa đủ để generated producer test chạy thành công?
2. Vì sao `@BeforeEach` nên seed dữ liệu có thể dự đoán trước từng test thay vì phụ thuộc test khác tạo đơn trước?
3. Với Resource Server, mock `JwtDecoder` khác gì việc tắt Spring Security filters?
4. Nếu đặt `@WithMockUser` trên base class của mọi generated tests, điều gì có thể xảy ra với hợp đồng 401?
5. Vì sao token có scope `profile.read` nên dẫn đến 403 chứ không phải 401 trong ví dụ?
6. Khi chuyển từ `MOCKMVC` sang `EXPLICIT`, vì sao dữ liệu seed trong một transaction chưa commit có thể không thấy ở HTTP server?
7. Nếu Stub Runner trả 200 cho request có token test, điều đó có chứng minh chữ ký JWT của producer được xác minh đúng không?
8. Vì sao build xanh với 0 generated tests không chứng minh hợp đồng đã được kiểm?
9. Khi nào nên dùng Testcontainers thay H2, và vì sao Testcontainers vẫn không tự giải quyết vấn đề state leak?

**Ghi nhớ:** **Base test là nơi biến tiền điều kiện của hợp đồng thành một môi trường kiểm thử tái lập**. Trong Spring Cloud Contract, hãy cấu hình fixture, xác thực và trạng thái ban đầu đúng với từng tình huống; chỉ mock những phần nằm ngoài phạm vi cần xác minh; bảo đảm generated producer tests thật sự chạy với bảo mật và implementation phù hợp. Sau khi producer verification đạt, mới phát hành stub để consumer sử dụng qua Stub Runner. Một hệ thống contract testing đáng tin cần **đúng dữ liệu, đúng quyền, đúng trạng thái và đúng phạm vi kiểm thử** — không chỉ cần một build hiển thị màu xanh.
