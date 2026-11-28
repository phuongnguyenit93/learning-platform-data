# Kiểm thử HTTP bằng MockMvc hoặc WebTestClient theo web stack

Service broker giao tiếp với platform qua HTTP theo contract của Open Service Broker API (OSB API). Một method Java chạy đúng chưa đủ để chứng minh broker tích hợp được với Cloud Foundry hoặc Kubernetes adapter: endpoint phải đúng path, query parameter phải được đọc đúng, header phiên bản phải được xử lý, JSON request/response phải serialize chính xác, status code phải tuân thủ contract và security filter phải bảo vệ request. Vì vậy, cần kiểm thử ở ranh giới HTTP bằng công cụ phù hợp với web stack của ứng dụng.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, hai công cụ thường dùng là **MockMvc** cho ứng dụng Spring MVC/Servlet và **WebTestClient** cho ứng dụng Spring WebFlux/reactive. Cả hai cho phép gửi HTTP request và kiểm tra response mà không cần phụ thuộc vào một platform Cloud Foundry thật. Chọn đúng công cụ giúp test đi qua đúng loại dispatcher, filter chain, controller và exception handling mà broker đang chạy trong production.

## 1. Vì sao cần kiểm thử ở tầng HTTP?

Service broker triển khai các endpoint theo OSB API. Platform gửi request đến broker qua HTTP, vì thế nhiều lỗi chỉ xuất hiện khi request đi qua web layer:

- Mapping sai /v2/service_instances/{instance_id} hoặc /service_bindings/{binding_id}.
- Đọc nhầm service_id, plan_id hoặc accepts_incomplete trong query string.
- Không nhận hoặc xử lý sai X-Broker-API-Version.
- Deserialize sai context, parameters hoặc bind_resource.
- Serialize sai tên field JSON như dashboard_url, operation hoặc credentials.
- Trả HTTP status không đúng cho provision, bind, unbind hoặc deprovision.
- Exception nghiệp vụ bị biến thành HTTP 500 thay vì lỗi OSB phù hợp.
- Security filter chặn request hợp lệ hoặc cho request chưa xác thực đi qua.
- Reactive pipeline chưa được subscribe hoặc lỗi bị mất khi trả response.

Unit test cho domain service vẫn cần thiết, nhưng không chứng minh controller và HTTP contract hoạt động chính xác. HTTP test xác nhận cách platform thực sự nhìn thấy broker.

## 2. Chọn MockMvc hay WebTestClient?

Hãy chọn công cụ theo web stack đang được ứng dụng sử dụng.

| Tiêu chí | MockMvc | WebTestClient |
|---|---|---|
| Web stack chính | Spring MVC, Servlet | Spring WebFlux, reactive |
| Cách xử lý request | Mock Servlet API, chạy qua Spring MVC DispatcherServlet | Reactive HTTP client; có thể bind vào WebFlux application hoặc server thật |
| Kiểu assertion | MockHttpServletResponse, status, header, jsonPath | ExchangeResult, status, header, body |
| Kiểm thử reactive pipeline | Không phải lựa chọn tự nhiên | Phù hợp với Mono/Flux và WebFlux |
| Kiểm thử endpoint không cần server thật | Có | Có thể bind trực tiếp vào application context |
| Kiểm thử qua HTTP server thật | Không phải mục tiêu chính | Có thể dùng RANDOM_PORT |
| Stack servlet | Phù hợp | Có thể dùng adapter MockMvcWebTestClient nếu cần API client thống nhất |
| Stack reactive | Không dùng làm test chính cho WebFlux | Lựa chọn tự nhiên |

### Dùng MockMvc khi nào?

Dùng MockMvc nếu broker chạy trên Spring MVC, có DispatcherServlet và controller được xử lý theo Servlet stack. MockMvc gửi request qua Spring MVC infrastructure trong môi trường test, nhưng không mở cổng TCP thật.

MockMvc phù hợp để kiểm tra URL mapping, query parameter, header, content type, JSON serialization/deserialization, filter chain, exception handler, HTTP status và response body.

### Dùng WebTestClient khi nào?

Dùng WebTestClient nếu broker chạy trên Spring WebFlux. Client này hỗ trợ reactive request/response và có thể bind vào controller, application context hoặc một server đang chạy.

WebTestClient phù hợp khi cần kiểm tra controller trả Mono hoặc Flux, reactive security filter chain, reactive error handling, reactive body serialization và request đi qua ứng dụng WebFlux đầy đủ hoặc HTTP server thật.

Không đưa cả hai công cụ vào mọi test chỉ vì dự án có dependency của cả hai. Xác định stack production và dùng test client tương ứng làm lựa chọn mặc định.

## 3. Chuẩn bị test dependencies

Một dự án Spring Boot thường dùng spring-boot-starter-test để có JUnit Jupiter, Spring Test, AssertJ và Mockito.

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chọn starter tương ứng với web stack của ứng dụng. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Hoặc dùng WebFlux thay cho starter-web. -->
    <!--
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    -->

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là dependency minh họa. Dự án cũng cần starter hoặc module Spring Cloud Open Service Broker tương ứng với phiên bản đang sử dụng. Không thêm đồng thời spring-boot-starter-web và spring-boot-starter-webflux nếu không có chủ đích rõ ràng, vì Spring Boot có thể chọn web application type theo classpath và tạo ra cấu hình khác với production.

Nếu dùng WebFlux, WebTestClient được cung cấp qua Spring Test và có thể được auto-configure bởi Spring Boot. Nếu dùng MVC, MockMvc cũng được tích hợp qua Spring Test. spring-security-test bổ sung helper để mô phỏng authentication trong test.

## 4. Xác định test scope: slice hay full application

Có hai mức kiểm thử thường gặp:

| Kiểu test | Annotation/cách tạo | Thành phần được kiểm tra |
|---|---|---|
| Web slice | @WebMvcTest hoặc @WebFluxTest | Controller, converter, filter/configuration được import vào slice |
| Full application context | @SpringBootTest kết hợp MockMvc/WebTestClient | Cấu hình ứng dụng, broker auto-configuration, controller, service bean và security |
| Standalone controller | MockMvcBuilders.standaloneSetup(...) | Controller và các thành phần được gắn thủ công |
| Random port | @SpringBootTest(webEnvironment = RANDOM_PORT) | HTTP server thực và toàn bộ request pipeline |

### Web slice

Dùng slice test để kiểm tra một nhóm endpoint nhanh. Tuy nhiên, OSB controller có thể được tạo bởi auto-configuration của Spring Cloud Open Service Broker. Một slice test có thể không tự nạp đầy đủ broker configuration. Khi đó, cần import đúng cấu hình hoặc chuyển sang full application context.

### Full application context

Với broker cần xác minh cả OSB auto-configuration, service implementation, security và serialization, @SpringBootTest thường phù hợp hơn. Có thể thay backend adapter bằng mock hoặc fake để test không tạo tài nguyên cloud thật.

### Standalone MockMvc

MockMvcBuilders.standaloneSetup hữu ích cho controller MVC tự viết. Nếu test endpoint OSB do framework tự cấu hình, standalone setup có thể bỏ qua controller, converter hoặc exception handler thực tế. Chỉ dùng khi mục tiêu test giới hạn rõ ràng.

## 5. Những thành phần HTTP cần xác minh trong OSB API

Một HTTP test tốt nên kiểm tra cả request lẫn response.

| Thành phần | Ví dụ | Điều cần xác minh |
|---|---|---|
| Method | GET, PUT, PATCH, DELETE | Đúng method theo endpoint |
| Path | /v2/catalog | Đúng route |
| Path variable | instance_id, binding_id | Được map đúng |
| Query parameter | service_id, plan_id | Được truyền đúng vào request model |
| Async parameter | accepts_incomplete=true | Chỉ chấp nhận async khi platform cho phép |
| Version header | X-Broker-API-Version | Phiên bản được hỗ trợ |
| Authentication | Basic/Bearer/mTLS tùy cấu hình | Filter xác thực đúng |
| Content-Type | application/json | Body được deserialize đúng |
| Accept | application/json | Response phù hợp |
| Status | 200, 201, 202, 400, 401, 403, 404, 409, 422... | Khớp contract và exception mapping |
| JSON body | dashboard_url, operation, credentials | Tên field và giá trị chính xác |

Các status trong bảng là những mã thường gặp trong HTTP/OSB workflow; từng trường hợp phải tuân theo OSB API version và mapping mà broker triển khai. Không viết test chỉ kiểm tra status 200 cho mọi request.

## 6. Những endpoint nên có HTTP test

Tùy capability của broker, các endpoint quan trọng gồm:

| Endpoint | Method | Mục tiêu kiểm thử |
|---|---|---|
| /v2/catalog | GET | Catalog, service, plan và bindable |
| /v2/service_instances/{instance_id} | PUT | Provision |
| /v2/service_instances/{instance_id} | PATCH | Update nếu broker hỗ trợ |
| /v2/service_instances/{instance_id} | DELETE | Deprovision |
| /v2/service_instances/{instance_id}/last_operation | GET | Poll operation |
| /v2/service_instances/{instance_id}/service_bindings/{binding_id} | PUT | Bind |
| /v2/service_instances/{instance_id}/service_bindings/{binding_id} | DELETE | Unbind |
| /v2/service_instances/{instance_id}/service_bindings/{binding_id} | GET | Retrieve binding nếu broker công bố hỗ trợ |

Không nhất thiết broker phải hỗ trợ mọi endpoint tùy chọn. Test phải phản ánh capability thực tế đã công bố trong catalog và cấu hình broker.

## 7. Dùng MockMvc kiểm tra catalog

Ví dụ full application test cho broker MVC:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BrokerCatalogMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldReturnCatalog() throws Exception {
        mockMvc.perform(get("/v2/catalog")
                .header("X-Broker-API-Version", "2.17")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.services").isArray())
            .andExpect(jsonPath("$.services[0].id")
                .value("svc-postgresql"))
            .andExpect(jsonPath("$.services[0].plans[0].id")
                .value("plan-standard"));
    }
}
~~~

Ví dụ giả định broker công bố route /v2/catalog và catalog có service/plan tương ứng. Thay ID bằng dữ liệu fixture của dự án.

Catalog test nên xác minh service ID và tên ổn định; plan thuộc đúng service; bindable đúng với khả năng binding; dashboard client hoặc schema extension chỉ xuất hiện khi được cấu hình; không lộ secret cấu hình nội bộ ngoài các field contract cần công bố; catalog response có content type và JSON structure hợp lệ.

Nếu catalog phụ thuộc profile hoặc platform registration, hãy thiết lập fixture rõ ràng để test không phụ thuộc thứ tự dữ liệu trong database.

## 8. Dùng MockMvc kiểm tra provision đồng bộ

OSB provision thường được gửi bằng PUT với instance ID trong path, service ID và plan ID trong query string.

Ví dụ:

~~~http
PUT /v2/service_instances/orders-db-001?service_id=svc-postgresql&plan_id=plan-standard
X-Broker-API-Version: 2.17
Content-Type: application/json
Accept: application/json

{
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "database_name": "orders"
  }
}
~~~

MockMvc test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BrokerProvisionMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldProvisionSynchronously() throws Exception {
        String requestBody = """
            {
              "context": {
                "platform": "cloudfoundry",
                "organization_guid": "org-123",
                "space_guid": "space-456"
              },
              "parameters": {
                "database_name": "orders"
              }
            }
            """;

        mockMvc.perform(put("/v2/service_instances/{id}",
                    "orders-db-001")
                .queryParam("service_id", "svc-postgresql")
                .queryParam("plan_id", "plan-standard")
                .header("X-Broker-API-Version", "2.17")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(requestBody))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
    }
}
~~~

Test này xác minh route, query, header, JSON deserialization và status. Nên bổ sung assertion cho response body nếu broker trả dashboard_url, metadata hoặc field khác. Đồng thời xác minh domain service nhận đúng instance ID, service ID, plan ID và parameters.

Nếu broker yêu cầu authentication, test phải gửi credential phù hợp hoặc dùng helper của Spring Security. Không bỏ security filter chỉ để test provision dễ chạy; cần có test riêng chứng minh request thiếu credential bị từ chối.

## 9. Dùng WebTestClient kiểm tra catalog và provision

Với WebFlux, WebTestClient có API fluent:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BrokerProvisionWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void shouldProvisionSynchronously() {
        String requestBody = """
            {
              "context": {
                "platform": "cloudfoundry",
                "organization_guid": "org-123",
                "space_guid": "space-456"
              },
              "parameters": {
                "database_name": "orders"
              }
            }
            """;

        webTestClient.put()
            .uri(uriBuilder -> uriBuilder
                .path("/v2/service_instances/{id}")
                .queryParam("service_id", "svc-postgresql")
                .queryParam("plan_id", "plan-standard")
                .build("orders-db-001"))
            .header("X-Broker-API-Version", "2.17")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(requestBody)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON);
    }
}
~~~

RANDOM_PORT khởi động HTTP server thật trên cổng ngẫu nhiên. Cách này kiểm tra nhiều thành phần runtime hơn so với bind trực tiếp vào application context, nhưng tốn thời gian hơn.

Nếu không cần TCP server, có thể cấu hình WebTestClient bind vào application context hoặc controller theo hướng dẫn Spring Test. Dù dùng cách nào, giữ nguyên WebFlux stack để test reactive handler đúng với production.

## 10. Kiểm tra query parameters và headers

Lỗi mapping query parameter thường khó phát hiện nếu chỉ kiểm tra response status. Hãy xác minh service nhận đúng giá trị từ URL.

Ví dụ dùng Mockito:

~~~java
verify(serviceInstanceService).createServiceInstance(
    argThat(request ->
        request.getServiceInstanceId().equals("orders-db-001")
        && request.getServiceDefinitionId().equals("svc-postgresql")
        && request.getPlanId().equals("plan-standard")
    )
);
~~~

Đây là ví dụ minh họa; kiểu request và getter phụ thuộc phiên bản Spring Cloud Open Service Broker. Nếu service method trả reactive publisher, test phải chờ HTTP exchange hoàn tất trước khi verify.

Kiểm tra version header:

- Header hiện diện và version được hỗ trợ: request được xử lý.
- Header version thấp hơn hoặc cao hơn mức broker hỗ trợ: phản hồi theo policy/version negotiation của broker.
- Header thiếu: xác minh hành vi mặc định theo contract và framework version.
- Header malformed: request bị từ chối với response có thể chẩn đoán.

Không giả định mọi broker hỗ trợ cùng một dải version. Test nên dùng phiên bản mà ứng dụng đã cấu hình.

## 11. Kiểm tra bind và credentials response

Bind request sử dụng instance ID và binding ID:

~~~http
PUT /v2/service_instances/orders-db-001/service_bindings/orders-api-binding?service_id=svc-postgresql&plan_id=plan-standard
X-Broker-API-Version: 2.17
Content-Type: application/json

{
  "context": {
    "platform": "cloudfoundry"
  },
  "bind_resource": {
    "app_guid": "app-orders-api"
  },
  "parameters": {
    "access_mode": "read_write"
  }
}
~~~

MockMvc test có thể xác minh response credentials:

~~~java
mockMvc.perform(put(
        "/v2/service_instances/{instanceId}/service_bindings/{bindingId}",
        "orders-db-001",
        "orders-api-binding")
        .queryParam("service_id", "svc-postgresql")
        .queryParam("plan_id", "plan-standard")
        .header("X-Broker-API-Version", "2.17")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestBody))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.credentials.hostname")
        .value("postgres.example.internal"))
    .andExpect(jsonPath("$.credentials.username")
        .value("orders_api"));
~~~

Không ghi password thật ra console hoặc test report. Nếu cần xác minh password, dùng giá trị giả trong test fixture và chỉ assertion trong bộ nhớ. Test phải xác nhận binding response không trả credential của consumer khác.

Nếu service có bindable=false, test bind phải xác minh broker từ chối request và backend adapter không được gọi. Nếu binding ID đã tồn tại với parameters khác, kiểm tra conflict theo contract.

## 12. Kiểm tra deprovision và unbind

Deprovision đồng bộ thường trả HTTP 200 sau khi broker hoàn tất thao tác. Unbind cũng có response thành công theo OSB API contract. Test cần xác minh đúng resource ID và query parameter được chuyển tới service layer.

Ví dụ MockMvc:

~~~java
mockMvc.perform(delete("/v2/service_instances/{id}", "orders-db-001")
        .queryParam("service_id", "svc-postgresql")
        .queryParam("plan_id", "plan-standard")
        .header("X-Broker-API-Version", "2.17"))
    .andExpect(status().isOk());
~~~

Ví dụ unbind:

~~~java
mockMvc.perform(delete(
        "/v2/service_instances/{instanceId}/service_bindings/{bindingId}",
        "orders-db-001",
        "orders-api-binding")
        .queryParam("service_id", "svc-postgresql")
        .queryParam("plan_id", "plan-standard")
        .header("X-Broker-API-Version", "2.17"))
    .andExpect(status().isOk());
~~~

Ngoài status, verify deprovision chỉ gọi backend cho instance đã resolve đúng platform/tenant; unbind chỉ revoke credential của binding được chỉ định; request lặp không xóa nhầm tài nguyên khác; service/plan ID không khớp được xử lý theo policy; backend adapter không bị gọi khi ownership validation thất bại.

Đừng để test chỉ assert HTTP 200 mà không xác minh side effect quan trọng.

## 13. Kiểm tra asynchronous operation

Provision, update, deprovision hoặc binding có thể xử lý bất đồng bộ nếu platform gửi accepts_incomplete=true và broker hỗ trợ async theo OSB API version.

Request ví dụ:

~~~http
PUT /v2/service_instances/orders-db-async?service_id=svc-postgresql&plan_id=plan-production&accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json

{
  "parameters": {
    "database_name": "orders"
  }
}
~~~

Khi broker chấp nhận thao tác bất đồng bộ, response thường là HTTP 202 và chứa operation token nếu broker dùng token đó để truy vấn tiến độ.

MockMvc assertion:

~~~java
mockMvc.perform(put("/v2/service_instances/{id}", "orders-db-async")
        .queryParam("service_id", "svc-postgresql")
        .queryParam("plan_id", "plan-production")
        .queryParam("accepts_incomplete", "true")
        .header("X-Broker-API-Version", "2.17")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestBody))
    .andExpect(status().isAccepted())
    .andExpect(jsonPath("$.operation").isNotEmpty());
~~~

Cần kiểm tra các trường hợp:

| Request | Hành vi mong đợi |
|---|---|
| Async được hỗ trợ và platform chấp nhận | Trả 202 cùng operation reference khi cần |
| Broker cần async nhưng accepts_incomplete không được gửi | Từ chối theo OSB contract |
| Operation đã tồn tại do retry | Trả kết quả/operation nhất quán |
| Request parameters không hợp lệ | Trả lỗi validation, không enqueue job |
| Worker hoàn tất | Last operation trả succeeded |
| Worker thất bại | Last operation trả failed và mô tả an toàn |
| Operation không thuộc instance/platform | Không tiết lộ trạng thái của resource khác |

Last operation endpoint:

~~~http
GET /v2/service_instances/orders-db-async/last_operation?service_id=svc-postgresql&plan_id=plan-production&operation=op-123
X-Broker-API-Version: 2.17
~~~

Test response state và description:

~~~java
webTestClient.get()
    .uri(uriBuilder -> uriBuilder
        .path("/v2/service_instances/{id}/last_operation")
        .queryParam("service_id", "svc-postgresql")
        .queryParam("plan_id", "plan-production")
        .queryParam("operation", "op-123")
        .build("orders-db-async"))
    .header("X-Broker-API-Version", "2.17")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.state").isEqualTo("succeeded");
~~~

HTTP completion của request ban đầu chỉ xác nhận broker đã trả response accepted. Test worker và operation store riêng để xác minh backend thực sự hoàn tất; không suy ra worker thành công chỉ từ status 202.

## 14. Kiểm tra lỗi và exception mapping

Service broker cần ánh xạ exception nghiệp vụ thành HTTP status và OSB error response phù hợp. Các trường hợp quan trọng:

| Tình huống | Điều cần xác minh |
|---|---|
| JSON malformed | HTTP 400 hoặc lỗi request theo mapping |
| Thiếu service ID/plan ID | Request bị từ chối rõ ràng |
| Service/plan không tồn tại | Error status theo OSB contract |
| Parameters không hợp lệ | Validation error, không gọi backend |
| Instance không tồn tại trong scope | Response không tiết lộ dữ liệu tenant khác |
| Binding ID conflict | Conflict theo contract |
| Service không bindable | Request bind bị từ chối |
| Authentication thiếu/sai | HTTP 401 |
| Caller không có quyền | HTTP 403 hoặc response không tiết lộ resource theo policy |
| Backend timeout | Lỗi/operation state được phân loại; không tạo tài nguyên trùng |
| Lỗi không dự kiến | HTTP 500 với mô tả an toàn |

Ví dụ test malformed body:

~~~java
mockMvc.perform(put("/v2/service_instances/{id}", "orders-db-001")
        .queryParam("service_id", "svc-postgresql")
        .queryParam("plan_id", "plan-standard")
        .header("X-Broker-API-Version", "2.17")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{invalid-json"))
    .andExpect(status().isBadRequest());
~~~

Không hard-code mọi exception thành 400. Cần xác minh exception handler của Spring Cloud Open Service Broker và mapping mà broker đã cấu hình. Với lỗi provider, response không được chứa stack trace, credential, account ID hoặc endpoint nội bộ.

## 15. Kiểm tra security filter chain

HTTP test nên chứng minh endpoint OSB được bảo vệ theo authentication scheme mà broker cấu hình.

Ví dụ với MockMvc và Spring Security Test:

~~~java
mockMvc.perform(get("/v2/catalog"))
    .andExpect(status().isUnauthorized());
~~~

Nếu broker dùng HTTP Basic:

~~~java
mockMvc.perform(get("/v2/catalog")
        .with(httpBasic("broker-client", "test-secret")))
    .andExpect(status().isOk());
~~~

Nếu dùng JWT resource server, có thể dùng helper jwt() trong spring-security-test khi test filter chain:

~~~java
mockMvc.perform(get("/v2/catalog")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("BROKER_CATALOG_READ"))))
    .andExpect(status().isOk());
~~~

Đây là ví dụ cấu hình test; authority và principal phải khớp converter của ứng dụng. Nếu security của broker dùng custom filter hoặc mTLS, cần test đúng cơ chế đó thay vì chỉ mock một authority tùy ý.

Với WebTestClient, có thể dùng mutateWith(mockJwt()) khi ứng dụng dùng reactive JWT resource server. Với HTTP Basic có thể gửi headers(headers -> headers.setBasicAuth(...)).

Nên có test cho request thiếu credential; credential sai hoặc hết hạn; platform registration bị suspend; principal hợp lệ nhưng tenant/resource ngoài scope; request có quyền đọc nhưng không có quyền mutation; security filter không vô tình chặn endpoint OSB hợp lệ.

Nếu broker dùng CSRF protection, cấu hình cho machine-to-machine OSB endpoint cần được thiết kế có chủ đích. Không tắt CSRF toàn ứng dụng chỉ để một test PUT chạy qua; có thể phân biệt broker API và dashboard/browser endpoints.

## 16. Kiểm tra JSON contract

Không chỉ assert status. Hãy xác minh tên field và cấu trúc JSON đúng contract.

Ví dụ response provision:

~~~json
{
  "dashboard_url": "https://dashboard.example.test/instances/ref-123",
  "operation": "op-123"
}
~~~

Ví dụ response binding:

~~~json
{
  "credentials": {
    "hostname": "postgres.example.test",
    "port": 5432,
    "username": "orders_api",
    "password": "test-only-secret"
  }
}
~~~

Các assertion nên kiểm tra JSON property dùng đúng snake_case theo OSB API; field optional chỉ xuất hiện khi có giá trị hoặc theo serializer policy; không trả field nội bộ như tenant secret, provider account credential hoặc stack trace; credentials là object và có key mà client cần; operation có giá trị khi thao tác async cần token; dashboard_url ổn định và không chứa secret; error response không làm lộ dữ liệu nhạy cảm.

Có thể dùng jsonPath, JSONAssert hoặc deserialize response thành model rồi assert. Khi kiểm tra toàn bộ JSON, cẩn thận với field optional và thứ tự property; JSON object không yêu cầu thứ tự key cố định.

## 17. Mock backend adapter, không mock HTTP contract

Một HTTP test không nên gọi cloud provider thật hoặc tạo database production. Thay backend adapter bằng mock/fake để kiểm soát kết quả và kiểm tra lời gọi.

Ví dụ:

~~~java
@MockitoBean
DatabaseProviderAdapter providerAdapter;
~~~

Trong test, cấu hình adapter trả kết quả giả:

~~~java
when(providerAdapter.provision(any(), any()))
    .thenReturn(new ProviderProvisionResult(
        "provider-resource-test",
        null,
        ProviderStatus.READY
    ));
~~~

Tên annotation và kiểu trả về cần khớp phiên bản Spring Boot/ứng dụng. Các phiên bản cũ thường dùng @MockBean; các phiên bản mới hơn có thể dùng @MockitoBean.

Điểm cần giữ:

- Mock provider adapter hoặc repository bên dưới application service.
- Không mock chính controller/OSB endpoint đang muốn kiểm thử.
- Không mock MockMvc hoặc WebTestClient.
- Xác minh adapter không được gọi khi validation/authentication thất bại.
- Dùng fake state store nếu cần kiểm tra lifecycle nhiều bước.
- Dùng provider sandbox/contract test riêng cho adapter khi cần kiểm chứng API bên ngoài.

Mục tiêu là kiểm tra HTTP boundary và orchestration của broker, đồng thời giữ external side effect có thể kiểm soát.

## 18. Test data và tính độc lập giữa các test

HTTP test cần dữ liệu có thể dự đoán. Có thể dùng fixture:

~~~java
static final String SERVICE_ID = "svc-postgresql";
static final String PLAN_ID = "plan-standard";
static final String INSTANCE_ID = "orders-db-test";
static final String BINDING_ID = "orders-api-binding-test";
~~~

Nếu dùng database test:

- Dùng database riêng cho test hoặc Testcontainers.
- Khởi tạo service/plan fixture rõ ràng.
- Xóa hoặc rollback dữ liệu sau mỗi test theo chiến lược phù hợp.
- Không phụ thuộc test chạy theo thứ tự.
- Không dùng ID giống nhau nếu test chạy song song và chia sẻ state.
- Tạo tenant/platform fixture tường minh.
- Đảm bảo operation state được reset giữa các test.

Với async workflow, không dựa vào Thread.sleep() để chờ worker. Dùng fake worker, controllable publisher, test scheduler hoặc polling có timeout. Test cần kết thúc ổn định và không để tác vụ nền rò sang test khác.

## 19. Kiểm tra headers, content negotiation và version negotiation

Một broker có thể nhận request từ platform dùng các version OSB API khác nhau. Test nên xác minh header X-Broker-API-Version được xử lý đúng.

Ví dụ MockMvc:

~~~java
mockMvc.perform(get("/v2/catalog")
        .header("X-Broker-API-Version", "2.17")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string(
        HttpHeaders.CONTENT_TYPE,
        containsString(MediaType.APPLICATION_JSON_VALUE)));
~~~

Tùy serializer và server, Content-Type có thể bao gồm charset; dùng matcher tương thích thay vì so sánh chuỗi cứng nếu không cần thiết.

Nên kiểm tra Content-Type: application/json khi gửi body; Accept: application/json khi đọc response; version header nằm trong dải broker hỗ trợ; header thiếu hoặc malformed theo policy; không chấp nhận content type không hỗ trợ; response không lộ header nội bộ hoặc credential; CORS chỉ cấu hình nếu dashboard/browser cần. OSB server-to-server request không nên dựa vào CORS để bảo vệ API.

## 20. Kiểm tra WebFlux reactive behavior

Với WebFlux, test cần xác minh publisher được subscribe đúng và lỗi được truyền đến HTTP response. WebTestClient tự thực hiện exchange và chờ response, nên phù hợp với Mono/Flux.

Một ví dụ kiểm tra lỗi reactive:

~~~java
webTestClient.put()
    .uri(uriBuilder -> uriBuilder
        .path("/v2/service_instances/{id}")
        .queryParam("service_id", "svc-postgresql")
        .queryParam("plan_id", "plan-standard")
        .build("invalid-instance"))
    .header("X-Broker-API-Version", "2.17")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("""
        {
          "parameters": {
            "storage_gb": -10
          }
        }
        """)
    .exchange()
    .expectStatus().isBadRequest();
~~~

Cần tránh gọi block() trong controller chỉ để test dễ hơn; dùng subscribe() bên trong service method khiến HTTP response kết thúc trước side effect; chạy blocking provider SDK trên event loop; dùng Thread.sleep() để đợi reactive operation; bỏ qua cancellation/timeout behavior nếu request có thể bị client ngắt.

Nếu provider client blocking, có thể chạy trên scheduler phù hợp và kiểm tra timeout/cancellation ở lớp adapter. HTTP test nên xác minh lỗi được ánh xạ ổn định, còn test scheduler/worker kiểm tra chi tiết concurrency.

## 21. Khi nào cần HTTP server thật?

MockMvc và WebTestClient bind vào application context thường đủ để test controller và filter. Dùng RANDOM_PORT khi cần xác minh các yếu tố phụ thuộc server/runtime:

- Embedded server và port binding.
- Network-level timeout hoặc connection behavior.
- Reverse proxy/header forwarding trong môi trường tích hợp.
- Serialization qua HTTP server thật.
- Security filter chain đầy đủ.
- Client gọi từ process khác hoặc container khác.

Ví dụ WebTestClient với server thật:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class BrokerHttpServerTest {

    @Autowired
    WebTestClient client;

    @Test
    void shouldExposeCatalogOverHttp() {
        client.get()
            .uri("/v2/catalog")
            .header("X-Broker-API-Version", "2.17")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Không cần dùng RANDOM_PORT cho mọi test vì khởi động server làm suite chậm hơn. Giữ phần lớn HTTP contract test ở mock environment và thêm một số integration test server thật cho các ranh giới quan trọng.

## 22. Ma trận test tối thiểu cho service broker

Một bộ test HTTP thực tế có thể được tổ chức như sau:

| Nhóm | Test case chính |
|---|---|
| Catalog | Catalog trả đúng service, plan, bindable và extension |
| Provision | Sync 201, async 202, query/body/header mapping |
| Update | Parameters update, plan transition và status/error |
| Bind | Credentials response, bindable, ownership và duplicate ID |
| Unbind | Thu hồi đúng binding, retry và response |
| Deprovision | Xóa đúng instance, async operation và idempotency |
| Last operation | IN_PROGRESS, SUCCEEDED, FAILED, operation không tồn tại |
| Validation | JSON malformed, field thiếu, parameters sai schema |
| Authentication | Thiếu token, token sai, principal hợp lệ |
| Authorization | Sai tenant, sai platform, quyền read-only |
| Serialization | snake_case, optional field, error body |
| Version/header | Supported/unsupported OSB API version |
| Security | Không lộ secret, CSRF boundary và scope |
| Reactive | Mono error, timeout, cancellation và backpressure ở endpoint phù hợp |

Không cần viết hàng chục test chỉ lặp lại một assertion. Chọn test đại diện cho từng nhánh contract, cộng test cho các lỗi có hậu quả cao như cross-tenant access, credential leakage và retry tạo tài nguyên trùng.

## 23. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng MockMvc cho ứng dụng WebFlux như test chính | Không kiểm tra đúng reactive stack | Dùng WebTestClient |
| Dùng WebTestClient nhưng không nạp broker auto-configuration | Endpoint OSB thực tế không được test | Dùng full context hoặc import cấu hình cần thiết |
| Chỉ test service method | Bỏ sót route, header, JSON và status | Thêm HTTP contract tests |
| Chỉ assert HTTP 200 | Không phát hiện sai response body | Assert status, headers và JSON fields |
| Không gửi X-Broker-API-Version | Test khác request platform thật | Gửi version header phù hợp |
| Không kiểm tra accepts_incomplete | Async contract có thể sai | Test cả async allowed và not allowed |
| Mock controller thay vì backend | Test không đi qua endpoint thật | Mock provider adapter/service dependency thấp hơn |
| Dùng cloud provider thật trong test HTTP | Chậm, tốn chi phí và khó lặp lại | Fake/mock adapter; contract test riêng |
| Bỏ qua Spring Security filter | Có thể bỏ sót lỗ hổng authentication | Giữ filter chain và test credential |
| Chỉ kiểm tra UI/response, không verify side effect | Backend có thể bị gọi sai hoặc không được gọi | Verify adapter/repository interactions |
| Dùng Thread.sleep() cho async | Test chập chờn và chậm | Poll có timeout hoặc controllable worker |
| Log response credentials trong test | Secret có thể lọt vào CI log | Dùng test secret và redaction |
| Chia sẻ database fixture giữa test | Kết quả phụ thuộc thứ tự | Fixture cô lập và cleanup rõ ràng |

## 24. Nguyên tắc cần ghi nhớ

MockMvc và WebTestClient đều kiểm thử HTTP contract của service broker, nhưng cần chọn theo web stack. MockMvc là lựa chọn tự nhiên cho Spring MVC/Servlet; WebTestClient phù hợp với Spring WebFlux/reactive và cũng có thể kiểm tra server thật khi cần.

Khi triển khai **SPRING_CLOUD_SERVICE_BROKER**, hãy áp dụng các nguyên tắc:

- Xác định MVC hay WebFlux theo production configuration trước khi chọn test client.
- Dùng @SpringBootTest khi cần xác minh OSB auto-configuration và filter chain đầy đủ; dùng slice test cho mục tiêu hẹp.
- Kiểm tra path, method, query, headers, Content-Type, JSON và status code.
- Gửi X-Broker-API-Version và các query parameter OSB như accepts_incomplete trong test.
- Kiểm tra cả provision/bind đồng bộ và async, bao gồm last operation.
- Test exception mapping và security filter chain.
- Mock provider adapter thay vì gọi cloud resource thật trong HTTP test.
- Verify side effect và không gọi backend khi request bị từ chối.
- Không log credentials hoặc token.
- Dùng server thật ở một số integration test khi cần xác minh network/runtime boundary.
- Giữ test độc lập, deterministic và không dùng sleep để chờ worker.

Một bộ HTTP test đúng web stack giúp phát hiện sớm lỗi tích hợp giữa Spring, Spring Cloud Open Service Broker và platform. Nó chứng minh platform nhìn thấy đúng contract, broker bảo vệ đúng endpoint và các thao tác vòng đời được chuyển đến domain/provider layer với dữ liệu chính xác.

