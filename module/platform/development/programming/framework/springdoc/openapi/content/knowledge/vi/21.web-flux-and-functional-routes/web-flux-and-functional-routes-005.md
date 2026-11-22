# Giới hạn gọi thử và hiển thị luồng trên giao diện

Spring WebFlux hỗ trợ endpoint trả về Mono hoặc Flux, bao gồm các route được khai báo bằng RouterFunction. springdoc-openapi có thể mô tả những route này trong OpenAPI để Swagger UI hiển thị operation, media type, response và ví dụ. Tuy nhiên, việc mô tả một luồng dữ liệu không đồng nghĩa Swagger UI trở thành công cụ theo dõi từng event theo thời gian thực.

Khi thiết kế tài liệu cho WebFlux, cần tách ba việc: công bố đúng hợp đồng HTTP, quyết định operation nào được phép gọi thử từ Swagger UI và chọn công cụ phù hợp để kiểm tra dữ liệu streaming. Bài này tập trung vào try-it-out, functional routes và giới hạn hiển thị các luồng SSE/NDJSON.

## 1. Swagger UI làm gì khi gọi Try it out?

Swagger UI đọc OpenAPI document rồi tạo giao diện cho người dùng xem operation, nhập parameter, request body và nhấn Execute. Khi thực thi, giao diện gửi HTTP request từ trình duyệt tới server được mô tả trong tài liệu.

Try it out phù hợp để:

- Kiểm tra nhanh endpoint có response hữu hạn.
- Thử query parameter, path parameter, header và request body.
- Xem status code, response header và response body.
- Tạo request mẫu hoặc cURL command để tái hiện thao tác.
- Kiểm tra API trong môi trường phát triển hoặc kiểm thử có quyền truy cập phù hợp.

Try it out không phải công cụ chuyên dụng để đọc một kết nối streaming kéo dài. Với SSE hoặc NDJSON, response có thể tiếp tục mở và gửi nhiều phần dữ liệu. Giao diện có thể vẫn ở trạng thái đang chờ, hoặc chỉ hiển thị dữ liệu khi body kết thúc, tùy phiên bản Swagger UI, swagger-client và trình duyệt.

Vì vậy, hãy dùng Swagger UI để công bố hợp đồng và thử các request hữu hạn; dùng cURL với chế độ không buffer, WebClient, EventSource hoặc một HTTP client hỗ trợ stream để quan sát từng event.

## 2. Điều khiển Try it out bằng cấu hình Swagger UI

springdoc-openapi chuyển các thuộc tính cấu hình Swagger UI qua prefix springdoc.swagger-ui. Hai thuộc tính quan trọng là:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| try-it-out-enabled | Bật sẵn vùng Try it out khi mở operation |
| supported-submit-methods | Danh sách HTTP method được phép dùng Try it out |

Ví dụ chỉ cho phép gọi thử GET và POST:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
    supported-submit-methods:
      - get
      - post
~~~

try-it-out-enabled chỉ điều khiển trạng thái mặc định của giao diện. Người dùng vẫn có thể bấm Try it out trên operation nếu method đó nằm trong danh sách được hỗ trợ.

supported-submit-methods giới hạn method có nút Execute. Ví dụ, cấu hình chỉ có get sẽ không cho người dùng gọi thử PUT, PATCH hoặc DELETE từ giao diện. Danh sách rỗng sẽ tắt Try it out cho mọi operation:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

Việc giới hạn method không ẩn operation khỏi tài liệu. Endpoint vẫn xuất hiện trong Swagger UI và OpenAPI JSON; chỉ khả năng thực thi từ giao diện bị tắt.

## 3. Giới hạn Try it out không phải là bảo mật API

supported-submit-methods là cấu hình giao diện. Nó không thay đổi RouterFunction, không xóa HTTP mapping và không chặn request đến server.

Người dùng vẫn có thể gọi endpoint bằng cURL, Postman, WebClient hoặc một ứng dụng khác. Vì vậy:

- Dùng Spring Security hoặc gateway để xác thực và phân quyền.
- Dùng CORS để kiểm soát request cross-origin từ trình duyệt.
- Dùng CSRF protection phù hợp nếu API dùng cookie/session.
- Không xem việc ẩn nút Execute là biện pháp bảo vệ endpoint ghi dữ liệu.
- Không công bố server URL nội bộ hoặc token thật trong tài liệu.

Nếu API chỉ cho phép thử GET trong Swagger UI, cấu hình đó giúp giảm thao tác ghi nhầm từ giao diện. Quyền tạo, sửa hoặc xóa dữ liệu vẫn phải được server kiểm tra.

## 4. Chọn method phù hợp cho từng môi trường

Có thể dùng profile để điều chỉnh giao diện theo môi trường:

application-dev.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    try-it-out-enabled: true
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

application-prod.yml:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: false
    supported-submit-methods: []
~~~

Ví dụ này chỉ điều chỉnh giao diện. Nếu production không nên công bố Swagger UI hoặc OpenAPI endpoint, cần cấu hình riêng springdoc.swagger-ui.enabled và springdoc.api-docs.enabled, đồng thời bảo vệ các đường dẫn tài liệu bằng Spring Security hoặc gateway. Tắt giao diện không tự động tắt endpoint JSON/YAML.

Không bật toàn bộ method trên môi trường dùng chung nếu các operation có thể thay đổi dữ liệu thật. Nên dùng dữ liệu thử, tài khoản có quyền tối thiểu và môi trường được cô lập.

## 5. springdoc nhận diện functional routes như thế nào?

Với annotation-based controller, springdoc có thể đọc mapping từ @GetMapping, @PostMapping, @RequestMapping và các annotation liên quan. Functional endpoint được khai báo bằng RouterFunction và HandlerFunction, nên không có cùng tập annotation mapping trên method controller.

Để mô tả functional routes, springdoc hỗ trợ hai cách chính:

1. Dùng @RouterOperation cho một route hoặc @RouterOperations cho nhiều route trong một RouterFunction bean.
2. Dùng functional DSL của springdoc để gắn metadata OpenAPI trực tiếp vào quá trình xây dựng route.

Nếu một RouterFunction chứa nhiều route, @RouterOperations cần khai báo path cho từng @RouterOperation. Mỗi operation nên có operationId duy nhất. springdoc dùng path, HTTP method, produces và consumes để ghép mô tả với route thực tế; thông tin phải đủ cụ thể để xác định đúng một route.

## 6. Mô tả nhiều RouterFunction bằng @RouterOperations

Ví dụ một RouterFunction có endpoint stream sự kiện SSE và endpoint lấy một sự kiện dạng JSON:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
class EventRoutes {

    @Bean
    @RouterOperations({
        @RouterOperation(
            path = "/api/events/stream",
            method = RequestMethod.GET,
            produces = MediaType.TEXT_EVENT_STREAM_VALUE,
            beanClass = EventHandler.class,
            beanMethod = "stream",
            operation = @Operation(
                operationId = "streamEvents",
                summary = "Nhận sự kiện theo thời gian thực",
                responses = @ApiResponse(
                    responseCode = "200",
                    description = "Luồng Server-Sent Events",
                    content = @Content(
                        mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
                        schema = @Schema(
                            type = "string",
                            description = "Mỗi event có thể chứa id, event và data; các event được ngăn cách bằng dòng trống."
                        ),
                        examples = @ExampleObject(
                            name = "orderUpdated",
                            summary = "Một event cập nhật đơn hàng",
                            value = "id: evt-100\nevent: order-updated\ndata: {\"orderId\":\"O-100\",\"status\":\"SHIPPED\"}\n\n"
                        )
                    )
                )
            )
        ),
        @RouterOperation(
            path = "/api/events/{id}",
            method = RequestMethod.GET,
            produces = MediaType.APPLICATION_JSON_VALUE,
            beanClass = EventHandler.class,
            beanMethod = "findById",
            operation = @Operation(
                operationId = "findEventById",
                summary = "Lấy một sự kiện",
                responses = @ApiResponse(
                    responseCode = "200",
                    description = "Thông tin sự kiện",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = EventMessage.class)
                    )
                )
            )
        )
    })
    RouterFunction<ServerResponse> eventRoutes(EventHandler handler) {
        return route()
            .GET("/api/events/stream",
                accept(MediaType.TEXT_EVENT_STREAM),
                handler::stream)
            .GET("/api/events/{id}",
                accept(MediaType.APPLICATION_JSON),
                handler::findById)
            .build();
    }
}
~~~

Ví dụ cho thấy hai phần cần đồng bộ:

- RouterFunction xác định route thực thi, method và predicate.
- @RouterOperations mô tả path, method, media type và OpenAPI operation tương ứng.

beanClass và beanMethod giúp springdoc tham chiếu handler method để đọc thêm metadata nếu cần. Nếu một bean chỉ chứa một route có thể dùng @RouterOperation riêng; khi có nhiều route, dùng @RouterOperations và khai báo path cho từng mục.

operationId nên duy nhất trong toàn bộ tài liệu OpenAPI. Không tái sử dụng cùng operationId cho route SSE và route JSON chỉ vì chúng cùng xử lý một loại sự kiện.

## 7. Functional DSL để gắn metadata cùng lúc xây dựng route

springdoc cũng cung cấp DSL thay thế annotation. Có thể gắn operationId, parameter và response vào builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Bean
RouterFunction<ServerResponse> eventRoutes(EventHandler handler) {
    return route()
        .GET("/api/events/sample", handler::stream, ops -> ops
            .operationId("sampleEvents")
            .tag("Events")
            .response(responseBuilder()
                .responseCode("200")
                .description("Một luồng sự kiện hữu hạn dùng để kiểm tra.")
            )
        )
        .build();
}
~~~

Đây là ví dụ rút gọn; cần import static helper responseBuilder của functional DSL theo đúng phiên bản springdoc đang dùng. DSL phù hợp khi muốn khai báo route và metadata gần nhau. Với response streaming cần mô tả rõ media type, ví dụ và cấu trúc event, annotation @RouterOperation có thể dễ đọc hơn; có thể dùng OpenApiCustomizer nếu cần kiểm soát OpenAPI model chi tiết.

Khi dùng DSL, import các builder helper của springdoc theo phiên bản dependency. Cú pháp và package helper có thể khác giữa major version; tham khảo đúng tài liệu v1 hoặc v2 của dự án.

## 8. Phân biệt Flux hữu hạn và giao thức streaming

Flux chỉ là Publisher phát ra nhiều phần tử. Nó không tự quyết định cách các phần tử được biểu diễn trên HTTP. Media type và codec quyết định định dạng body và cách ghi dữ liệu.

| Return type và media type | Cách biểu diễn thường dùng |
| --- | --- |
| Mono<T> với application/json | Một JSON object |
| Flux<T> với application/json | Một JSON array; WebFlux mặc định gom các giá trị thành collection để serialize |
| Flux<T> với application/x-ndjson | Mỗi phần tử là một JSON document trên một dòng |
| Flux<ServerSentEvent<T>> với text/event-stream | Các event SSE được ghi và flush riêng |
| Flux<T> với application/stream+json | Dòng JSON streaming theo codec hỗ trợ và phiên bản framework |

Đừng suy luận rằng một endpoint trả Flux<T> chắc chắn là streaming trên wire. Nếu muốn client nhận từng phần tử khi chúng được phát ra, hãy chọn media type streaming rõ ràng như application/x-ndjson hoặc text/event-stream và kiểm tra response thực tế.

Với application/json, Spring WebFlux mặc định thu thập các phần tử Flux thành collection rồi serialize. Đây là hợp đồng JSON array hữu hạn, phù hợp để Swagger UI hiển thị như một response JSON thông thường.

## 9. SSE là một giao thức event stream

Server-Sent Events dùng media type text/event-stream. Mỗi event là một khối văn bản UTF-8; các field thường gặp:

| Field | Ý nghĩa |
| --- | --- |
| id | Định danh event, có thể dùng để tiếp tục sau khi kết nối lại |
| event | Tên loại event |
| data | Nội dung event; có thể là JSON string |
| retry | Khoảng thời gian gợi ý trước khi client thử kết nối lại |

Các dòng của một event được kết thúc bằng một dòng trống. Ví dụ:

~~~text
id: evt-100
event: order-updated
data: {"orderId":"O-100","status":"SHIPPED"}

id: evt-101
event: order-delayed
data: {"orderId":"O-101","reason":"WEATHER"}

~~~

Trong WebFlux, có thể trả về Flux<ServerSentEvent<EventMessage>>. Nếu chỉ cần gửi data, có thể dùng publisher các giá trị và khai báo produces là text/event-stream. ServerSentEvent giúp điều khiển id, event, retry và comment.

Ví dụ handler:

~~~java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record EventMessage(String id, String orderId, String status) {
}

@Component
class EventHandler {

    public Mono<ServerResponse> stream(ServerRequest request) {
        Flux<ServerSentEvent<EventMessage>> events =
            Flux.interval(Duration.ofSeconds(1))
                .take(5)
                .map(index -> ServerSentEvent.<EventMessage>builder()
                    .id("evt-" + index)
                    .event("order-progress")
                    .data(new EventMessage(
                        "evt-" + index,
                        "O-100",
                        "STEP-" + index
                    ))
                    .build());

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(events, ServerSentEvent.class);
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        String id = request.pathVariable("id");
        EventMessage event = new EventMessage(id, "O-100", "SHIPPED");

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(event);
    }
}
~~~

Luồng trên chỉ phát năm event rồi hoàn tất, nên thích hợp cho một lần thử có giới hạn. Endpoint production có thể không kết thúc cho đến khi client ngắt kết nối hoặc nguồn dữ liệu dừng.

## 10. NDJSON truyền từng JSON record theo dòng

NDJSON (newline-delimited JSON) dùng media type application/x-ndjson. Mỗi dòng là một JSON document độc lập:

~~~text
{"id":"evt-100","orderId":"O-100","status":"PACKING"}
{"id":"evt-101","orderId":"O-100","status":"SHIPPED"}
{"id":"evt-102","orderId":"O-101","status":"CREATED"}
~~~

Một handler WebFlux có thể trả Flux<EventMessage> với content type application/x-ndjson:

~~~java
Mono<ServerResponse> sample(ServerRequest request) {
    Flux<EventMessage> records =
        Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(index -> new EventMessage(
                "evt-" + index,
                "O-100",
                "STATUS-" + index
            ));

    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(records, EventMessage.class);
}
~~~

WebFlux có thể encode, ghi và flush từng phần tử với streaming media type NDJSON. Client đọc từng dòng, parse từng JSON object và xử lý ngay mà không cần đợi toàn bộ response kết thúc.

Khi mô tả NDJSON trong OpenAPI, cần nói rõ schema biểu diễn một record trong stream và body chứa nhiều record được phân cách bằng newline. Không mô tả body như một JSON array nếu server không gửi dấu ngoặc vuông và dấu phẩy của array.

## 11. Mô tả response streaming trong OpenAPI

OpenAPI mô tả response qua status code, media type, schema, description và example. Với SSE, schema có thể mô tả wire body là text/event-stream và description giải thích event framing. Với NDJSON, schema có thể chỉ rõ cấu trúc một record; description giải thích mỗi record nằm trên một dòng.

Ví dụ YAML cho SSE:

~~~yaml
responses:
  '200':
    description: Luồng sự kiện Server-Sent Events
    content:
      text/event-stream:
        schema:
          type: string
          description: Chuỗi SSE gồm các event được phân cách bằng dòng trống.
        example: |
          id: evt-100
          event: order-updated
          data: {"orderId":"O-100","status":"SHIPPED"}
~~~

Ví dụ YAML cho NDJSON:

~~~yaml
responses:
  '200':
    description: Luồng JSON, mỗi dòng là một EventMessage
    content:
      application/x-ndjson:
        schema:
          $ref: '#/components/schemas/EventMessage'
        example: |
          {"id":"evt-100","orderId":"O-100","status":"PACKING"}
          {"id":"evt-101","orderId":"O-100","status":"SHIPPED"}
~~~

Trong ví dụ NDJSON, schema tham chiếu EventMessage để mô tả cấu trúc từng record theo quy ước tài liệu. Hãy giải thích rõ rằng HTTP body là chuỗi record theo dòng, không phải một JSON object duy nhất hay một JSON array.

Với SSE, schema type string mô tả framing văn bản của response. Nếu muốn mô tả payload JSON bên trong field data, tạo schema riêng cho payload và liên kết bằng description hoặc component; đừng nhầm toàn bộ frame SSE với JSON object.

## 12. Swagger UI không phải trình đọc SSE/NDJSON chuyên dụng

Try it out gửi request qua HTTP client của Swagger UI. Nó hiển thị response theo khả năng xử lý response body của phiên bản swagger-client đang dùng. Một request SSE không kết thúc có thể giữ nút Execute ở trạng thái chờ lâu; một NDJSON stream cũng có thể chỉ xuất hiện sau khi response hoàn tất.

Các giới hạn cần nhớ:

- UI không cung cấp danh sách event có số thứ tự và thời điểm đến như một stream inspector chuyên dụng.
- UI không đảm bảo cập nhật nội dung theo từng event.
- Với kết nối vô hạn, người dùng có thể không nhận được vùng response hoàn chỉnh.
- Dừng request hoặc đóng tab có thể là cách duy nhất để kết thúc thao tác đang chờ trong một số phiên bản.
- Browser, proxy và gateway có thể buffer dữ liệu dù server đã flush từng event.

Swagger UI vẫn hữu ích để xem endpoint, media type, mô tả và ví dụ. Hãy dùng công cụ stream-aware để kiểm tra thời điểm nhận, thứ tự, nội dung và việc ngắt kết nối.

## 13. Dùng cURL để quan sát từng phần dữ liệu

Với SSE, dùng cURL và tùy chọn -N để tắt buffering ở phía cURL:

~~~bash
curl -N \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/events/stream
~~~

Với NDJSON:

~~~bash
curl -N \
  -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/events/ndjson
~~~

Nếu endpoint yêu cầu bearer token trong môi trường test, dùng token test qua biến môi trường hoặc secret store của shell; không ghi token thật trực tiếp vào tài liệu, script được commit hoặc ảnh chụp terminal.

Quan sát header:

~~~bash
curl -iN \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/events/stream
~~~

Kiểm tra Content-Type trả về đúng media type. Nếu cURL chỉ hiển thị dữ liệu sau khi stream kết thúc, kiểm tra tùy chọn -N, proxy buffering, compression và cấu hình flush ở tầng server.

## 14. Kiểm thử stream bằng WebTestClient

WebTestClient có thể kiểm tra status, header và các phần tử được phát ra từ endpoint WebFlux. Với stream hữu hạn, có thể xác nhận số event và việc hoàn tất:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class EventStreamTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void emitsFiniteSseEvents() {
        var result = webTestClient.get()
            .uri("/api/events/stream")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(new ParameterizedTypeReference<
                ServerSentEvent<EventMessage>>() {});

        StepVerifier.create(result.getResponseBody())
            .expectNextCount(5)
            .verifyComplete();
    }
}
~~~

Ví dụ minh họa test stream hữu hạn. Trong project thực tế cần import ParameterizedTypeReference và cấu hình WebTestClient phù hợp với ứng dụng. Nếu endpoint không bao giờ kết thúc, dùng StepVerifier với thenCancel sau khi nhận số event mong muốn và verify cancellation.

Đối với NDJSON, có thể đọc response body theo EventMessage hoặc String tùy cách codec được cấu hình. Hãy kiểm tra cả Content-Type và từng record, không chỉ xác nhận status 200.

## 15. Kiểm tra route được sinh vào OpenAPI

Sau khi thêm @RouterOperations, lấy tài liệu:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
~~~

Kiểm tra path:

~~~json
{
  "paths": {
    "/api/events/stream": {
      "get": {
        "operationId": "streamEvents",
        "responses": {
          "200": {
            "content": {
              "text/event-stream": {}
            }
          }
        }
      }
    }
  }
}
~~~

Checklist:

1. Tất cả route cần công bố có xuất hiện trong paths không?
2. HTTP method có khớp RouterFunction không?
3. operationId có duy nhất không?
4. produces và response content type có khớp media type runtime không?
5. SSE có được mô tả là text/event-stream không?
6. NDJSON có được mô tả là application/x-ndjson không?
7. Schema và example có giải thích cấu trúc từng event/record không?
8. Có path bị ghép nhầm khi nhiều route dùng chung handler không?
9. Có response status và lỗi phù hợp cho route không?

Nếu route không xuất hiện, kiểm tra @RouterOperation(s) có đặt trên đúng RouterFunction bean, path/method/produces có khớp route và operationId đã khai báo chưa. Nếu một annotation có thể khớp nhiều route, bổ sung điều kiện method, produces hoặc consumes để nhận diện duy nhất.

## 16. Phân biệt lỗi tài liệu với lỗi streaming runtime

Một operation hiển thị đúng trong Swagger UI nhưng stream không hoạt động có thể do tầng HTTP/runtime:

| Hiện tượng | Khả năng cần kiểm tra |
| --- | --- |
| Không thấy event nào | Accept header, Content-Type, handler, nguồn Flux hoặc lỗi trước khi commit response |
| Event chỉ xuất hiện khi stream kết thúc | Buffering ở proxy, gateway, compression hoặc client |
| Swagger UI chờ mãi | Stream vô hạn và UI đang đợi response body hoàn tất |
| cURL hiển thị tất cả cùng lúc | Thiếu -N hoặc một tầng trung gian đang buffer |
| Client nhận JSON array thay vì từng dòng | Server dùng application/json thay vì media type streaming |
| Kết nối tự đóng | Timeout, idle timeout, lỗi nguồn, client cancel hoặc proxy |
| Client không nhận event sau khi reconnect | Thiếu id/Last-Event-ID hoặc logic resume |
| OpenAPI không có route | Thiếu @RouterOperation(s), path không khớp hoặc operationId thiếu |

Không chỉnh schema để chữa lỗi proxy buffering. Không chỉnh timeout của server chỉ để Swagger UI hoàn tất một stream vốn được thiết kế mở lâu dài.

## 17. Timeout, heartbeat và hủy kết nối

Một stream lâu dài cần xử lý việc client ngắt kết nối và hạ tầng đóng kết nối idle:

- Dùng heartbeat định kỳ nếu giao thức và nghiệp vụ cho phép.
- Với SSE, có thể gửi comment event hoặc event heartbeat để giữ kết nối và phát hiện client đã rời đi.
- Theo dõi cancellation của subscription để dừng công việc upstream khi client hủy.
- Cấu hình timeout ở server, gateway và load balancer nhất quán với thời lượng stream dự kiến.
- Không giữ kết nối vô hạn nếu nghiệp vụ chỉ cần một tập dữ liệu hữu hạn.
- Với SSE có resume, phát event id ổn định và xử lý Last-Event-ID.

Nếu stream chỉ phục vụ xem trước hoặc kiểm thử thủ công, tạo endpoint mẫu có giới hạn số event và tự hoàn tất. Endpoint production có thể tiếp tục chạy lâu dài theo thiết kế.

## 18. Giới hạn browser và CORS

Swagger UI chạy trong trình duyệt. Nếu trang Swagger UI và API khác origin, request có thể cần CORS. Việc Try it out bị trình duyệt chặn không nhất thiết là lỗi OpenAPI.

Với SSE:

- Native EventSource chủ yếu dùng GET và không cho đặt tùy ý Authorization header.
- Nếu API dùng bearer token trong header, có thể dùng fetch streaming hoặc client SSE hỗ trợ header.
- Cookie có thể được gửi theo chính sách same-site/credentials và CORS phù hợp.
- Không đưa token nhạy cảm vào query string chỉ để tương thích EventSource vì URL có thể xuất hiện trong log và history.

Với NDJSON, có thể dùng fetch và đọc response.body bằng stream reader. Hãy bảo đảm CORS cho phép method/header cần thiết và expose response header mà client cần đọc.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Functional route không xuất hiện trong Swagger UI | Chưa khai báo @RouterOperation hoặc @RouterOperations | Thêm annotation cho route và operationId |
| Nhiều route chỉ sinh một operation | Dùng @RouterOperation đơn cho RouterFunction nhiều route | Dùng @RouterOperations, khai báo path từng route |
| Route ghép nhầm metadata | Path/method/produces không xác định duy nhất route | Bổ sung các điều kiện nhận diện route |
| Flux không stream từng phần | Dùng application/json hoặc media type không streaming | Chọn NDJSON hoặc SSE và kiểm tra codec |
| Try it out cứ chờ | Endpoint là stream dài hạn | Dùng cURL -N hoặc client hỗ trợ stream |
| Stream chỉ hiện sau khi kết thúc | UI/client hoặc proxy buffer response | Kiểm tra bằng client stream-aware và kiểm tra proxy |
| Tắt Try it out nhưng operation vẫn thấy | supported-submit-methods chỉ tắt thao tác Execute | Đây là hành vi dự kiến; dùng security để bảo vệ endpoint |
| Endpoint vẫn gọi được bằng cURL | Cấu hình Swagger UI không chặn server | Bảo vệ route bằng Spring Security/gateway |
| Response schema mô tả nhầm array | Dùng schema collection cho NDJSON body | Mô tả từng record và quy tắc phân cách dòng |
| SSE event thiếu thông tin resume | Không phát id hoặc không xử lý Last-Event-ID | Thiết kế event id và chính sách resume |

## 20. Quy trình thiết kế tài liệu và gọi thử WebFlux

1. Xác định route là response hữu hạn, SSE hay NDJSON.
2. Chọn media type phù hợp với wire format thực tế.
3. Khai báo RouterFunction và handler đúng method, path, produces.
4. Dùng @RouterOperation hoặc @RouterOperations để mô tả route; đặt operationId duy nhất.
5. Mô tả response content, schema và example theo định dạng trên wire.
6. Dùng try-it-out-enabled và supported-submit-methods để kiểm soát giao diện gọi thử.
7. Giữ bảo mật endpoint ở Spring Security/gateway; không dựa vào giới hạn UI.
8. Dùng Swagger UI cho request hữu hạn và xem hợp đồng.
9. Dùng cURL -N, WebTestClient hoặc client stream-aware để kiểm tra từng event.
10. Kiểm tra timeout, heartbeat, cancellation, CORS và buffering qua proxy.

Khi tách rõ hợp đồng OpenAPI, quyền gọi thử và giao thức streaming, người tích hợp có thể hiểu đúng endpoint WebFlux và chọn công cụ phù hợp. Swagger UI giúp khám phá và thử API; việc xác minh dữ liệu đến theo từng event cần một client có khả năng đọc stream.

## Tài liệu tham khảo

- [springdoc-openapi v2 – WebFlux/WebMvc.fn Functional Endpoints](https://springdoc.org/v2/features.html)
- [Swagger UI – Configuration: tryItOutEnabled và supportedSubmitMethods](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework – WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework – Reactive Core, Jackson JSON và Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [MDN – Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [Swagger UI – SSE support discussion](https://github.com/swagger-api/swagger-ui/issues/4761)
