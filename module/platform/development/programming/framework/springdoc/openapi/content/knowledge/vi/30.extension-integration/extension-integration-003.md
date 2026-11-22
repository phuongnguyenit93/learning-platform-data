# Dùng chung đặc tả nhưng kiểm tra riêng khả năng hiển thị của từng giao diện

Một ứng dụng Spring Boot có thể tạo một OpenAPI document bằng springdoc-openapi rồi dùng document đó cho nhiều giao diện: Swagger UI, ReDoc, Scalar hoặc RapiDoc. Cách làm này giữ một hợp đồng API thống nhất trong khi mỗi giao diện có cách trình bày, điều hướng, hiển thị schema, xử lý xác thực và thao tác riêng.

Tuy nhiên, cùng đọc một file OpenAPI không có nghĩa các giao diện sẽ hiển thị giống nhau. Một renderer có thể trình bày tốt oneOf nhưng làm ví dụ khó tìm; một giao diện có nút gửi request trong khi giao diện khác chỉ đọc tài liệu; OAuth redirect có thể hoạt động trong Swagger UI nhưng sai đường dẫn khi đặt giao diện sau reverse proxy. Vì vậy cần kiểm tra document một lần ở cấp hợp đồng và kiểm tra riêng từng giao diện ở cấp hiển thị, tương tác và vận hành.

Bài này hướng dẫn tạo một nguồn OpenAPI dùng chung từ springdoc, gắn nhiều renderer vào nguồn đó, so sánh các khác biệt quan trọng và thiết kế bộ kiểm tra để bảo đảm mỗi giao diện hiển thị đúng những gì consumer cần.

## 1. Tách nguồn hợp đồng khỏi giao diện hiển thị

Trong kiến trúc này có ba phần:

1. **Ứng dụng Spring Boot** đăng ký controller, DTO, validation, security và các OpenAPI annotation.
2. **springdoc-openapi** đọc mapping và metadata của ứng dụng rồi cung cấp OpenAPI JSON/YAML.
3. **Renderer** tải OpenAPI document và trình bày nó thành trang tài liệu cho người dùng.

Luồng dữ liệu:

~~~mermaid
flowchart TD
    A[Spring Boot controllers, DTO, annotations] --> B[springdoc-openapi]
    B --> C[OpenAPI JSON/YAML]
    C --> D[Swagger UI]
    C --> E[ReDoc]
    C --> F[Scalar]
    C --> G[RapiDoc]
    D --> H[Developer / API consumer]
    E --> H
    F --> H
    G --> H
~~~

Renderer không phải nguồn hợp đồng thứ hai. Nó đọc document, diễn giải nội dung và tạo giao diện. Nếu mỗi giao diện được cấu hình bằng một bản OpenAPI riêng được sao chép thủ công, các bản đó có thể lệch nhau theo thời gian.

Giữ một nguồn có version rõ ràng giúp:

- Mọi giao diện hiển thị cùng operation, schema và security scheme.
- Thay renderer không cần sửa controller hoặc DTO.
- Có thể so sánh renderer mới với renderer cũ bằng cùng một document.
- CI có thể kiểm tra nội dung OpenAPI độc lập với kiểm tra giao diện.
- Các portal, tài liệu tĩnh và client generator dùng cùng hợp đồng đã phát hành.

## 2. springdoc tạo document dùng chung

Với Spring MVC, starter có Swagger UI thường là **springdoc-openapi-starter-webmvc-ui**. Nếu ứng dụng dùng WebFlux, chọn **springdoc-openapi-starter-webflux-ui**. Khi chỉ cần endpoint OpenAPI để giao cho renderer khác, dùng starter API tương ứng và không đóng gói Swagger UI.

Ví dụ cấu hình cơ bản:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

Các URL mặc định:

| Nội dung | URL |
| --- | --- |
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| Swagger UI | /swagger-ui.html |

Nếu chuyển sang ReDoc hoặc Scalar, vẫn giữ springdoc để tạo document. Có thể tắt Swagger UI hoặc thay starter -ui bằng starter -api, tùy giao diện nào được ứng dụng cung cấp.

Ví dụ chỉ bật API document:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Không tắt springdoc.api-docs.enabled khi renderer cần tải document từ ứng dụng. Tắt giao diện Swagger UI và tắt endpoint OpenAPI là hai việc khác nhau.

## 3. Một document có thể được đọc bởi nhiều renderer

Giả sử ứng dụng phục vụ OpenAPI JSON tại /v3/api-docs. Các renderer có thể tham chiếu cùng URL:

~~~text
https://api.example.com/v3/api-docs
~~~

| Renderer | Cách nhận document phổ biến |
| --- | --- |
| Swagger UI | url hoặc urls trong Swagger UI config |
| ReDoc Community Edition | Thuộc tính spec-url trên phần tử redoc |
| Scalar | scalar.url hoặc danh sách scalar.sources |
| RapiDoc | Thuộc tính spec-url trên phần tử rapi-doc |

Nếu renderer được host ở domain khác với API, trình duyệt sẽ tải document qua cross-origin request. Khi có thể, hãy phục vụ giao diện và document dưới cùng origin hoặc cấu hình CORS chính xác cho nguồn tài liệu. Không mở CORS wildcard cho toàn bộ API chỉ để làm trang docs hoạt động.

## 4. Khác biệt giữa các giao diện

Các renderer có mục tiêu và bộ tính năng khác nhau. Bảng sau là điểm bắt đầu để chọn và kiểm thử, không phải cam kết mọi phiên bản đều giống nhau.

| Khả năng | Swagger UI | ReDoc Community Edition | Scalar | RapiDoc |
| --- | --- | --- | --- | --- |
| Cách trình bày | Operation theo tag, tương tác trực tiếp | Bố cục ba cột, điều hướng và schema | API reference tương tác, sidebar và API client | Web component có thể tùy biến layout |
| Tập trung chính | Khám phá endpoint và thử request | Đọc mô tả, schema và ví dụ | Đọc tài liệu và gửi request từ API client | Nhúng reference vào trang riêng |
| Gửi request từ UI | Có Try it out | Bản Community Edition không có Try-it console tích hợp | Có nút Test Request | Có thể bật chức năng thử request theo cấu hình |
| Xác thực | Hỗ trợ Authorize và cấu hình OAuth | Hiển thị security scheme; khả năng thử auth tùy bản/triển khai | API client có thể dùng security scheme của document | Có thành phần authorize theo cấu hình |
| Deep link | Hỗ trợ khi bật deepLinking | Điều hướng theo anchor/section | Có deep links tới operation và schema | Hỗ trợ link/anchor tùy phiên bản |
| Nhiều document | Hỗ trợ urls và top bar | Có thể tạo nhiều trang hoặc nhiều entry theo cách host | Có sources và document switcher | Có thể đổi spec-url hoặc cấu hình nhiều nguồn |
| Phạm vi schema | Phụ thuộc phiên bản Swagger UI | Hiển thị schema và composition | Hiển thị schema cùng ví dụ | Hiển thị schema theo OpenAPI feature được hỗ trợ |

Một số điểm cần nhớ:

- Swagger UI phù hợp khi người dùng cần khám phá operation và gọi thử endpoint ngay trong trang.
- ReDoc Community Edition phù hợp với tài liệu đọc, điều hướng và xem schema; tính năng Try-it của sản phẩm ReDocly hosted không đồng nghĩa có trong bản Community Edition.
- Scalar cung cấp API client tích hợp và cấu hình nhiều nguồn document; cần bảo đảm URL nguồn có thể được browser truy cập.
- RapiDoc là web component, hữu ích khi cần nhúng reference vào trang do nhóm tự thiết kế.

Không chọn renderer chỉ dựa vào ảnh chụp trang chủ. Hãy thử bằng document thật của ứng dụng, gồm security, schema composition, examples và nhiều group.

## 5. Kiểm tra cùng một document trên Swagger UI

Springdoc tích hợp Swagger UI thông qua starter springdoc-openapi-starter-webmvc-ui hoặc springdoc-openapi-starter-webflux-ui. Các thuộc tính giao diện dùng prefix springdoc.swagger-ui.

Ví dụ:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    deep-linking: true
    display-operation-id: true
    display-request-duration: true
    operations-sorter: alpha
    tags-sorter: alpha
    doc-expansion: none
~~~

Các thuộc tính trên ảnh hưởng cách Swagger UI trình bày:

- path: đường dẫn trang giao diện.
- deep-linking: cho phép tạo URL fragment trỏ tới tag hoặc operation.
- display-operation-id: hiển thị operationId để đối chiếu contract và client code.
- display-request-duration: hiển thị thời gian request khi dùng Try it out.
- operations-sorter và tags-sorter: sắp xếp operation/tag.
- doc-expansion: trạng thái mở rộng ban đầu của nhóm operation.

Nếu có nhiều GroupedOpenApi, có thể cấu hình danh sách URL:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
~~~

Chỉ thêm danh sách này khi cần kiểm soát rõ các document mà người dùng được chọn. Nếu cấu hình group tự động của springdoc đã đáp ứng nhu cầu, không cần khai báo lại các URL.

Kiểm tra trên Swagger UI:

1. Trang docs tải được cấu hình và OpenAPI document.
2. Tag và operation có thứ tự dễ tìm.
3. OperationId không bị trống nếu nhóm yêu cầu hiển thị.
4. Request body, parameter và response example hiển thị đúng.
5. Authorize nhận đúng scheme.
6. Try it out gửi request tới server đúng.
7. Deep link vẫn mở đúng operation sau khi reload hoặc chia sẻ URL.

## 6. Kiểm tra cùng một document trên ReDoc

ReDoc Community Edition có thể được nhúng bằng HTML element và URL của OpenAPI document:

~~~html
<!doctype html>
<html lang="vi">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Order API</title>
  </head>
  <body>
    <redoc spec-url="/v3/api-docs"></redoc>
    <script type="module" src="/assets/redoc.standalone.js"></script>
  </body>
</html>
~~~

Ví dụ dùng asset đã được đóng gói tại /assets/redoc.standalone.js. Hãy cài một phiên bản ReDoc cụ thể, copy bundle vào thư mục static của ứng dụng hoặc host asset cùng domain; nếu dùng CDN, pin phiên bản thay vì dùng URL trôi nổi. Kiểm tra Content Security Policy, cache và khả năng tải asset từ browser của người dùng.

ReDoc Community Edition trình bày document theo bố cục ba cột: điều hướng, nội dung và vùng schema/example. Khi kiểm tra:

- Mô tả operation dài có đọc được và giữ heading/list không.
- Schema lồng nhau có điều hướng được không.
- oneOf, anyOf, allOf và discriminator có giúp người đọc hiểu các biến thể không.
- Example request/response có được hiển thị cạnh schema đúng không.
- Tag, operation và model có thể tìm thấy bằng search không.
- Nội dung dài có hoạt động trên màn hình hẹp không.

Không kỳ vọng nút Try it out giống Swagger UI trong ReDoc Community Edition. Nếu yêu cầu nghiệp vụ là gửi request từ tài liệu, chọn một renderer có API client tích hợp hoặc dùng phiên bản sản phẩm có tính năng tương ứng.

Có thể tạo trang HTML tĩnh từ OpenAPI file bằng Redocly CLI:

~~~bash
npx @redocly/cli build-docs openapi.yaml
~~~

Lệnh tạo trang tài liệu tĩnh để host trên web server hoặc artifact storage. Khi document có $ref tới file ngoài, hãy bundle các file liên quan trước khi phân phối một file độc lập.

## 7. Kiểm tra cùng một document trên Scalar

Scalar có tích hợp Spring Boot riêng. Với Spring MVC, có thể dùng scalar-webmvc; với WebFlux, dùng scalar-webflux. springdoc vẫn là thành phần sinh OpenAPI document.

Ví dụ cấu hình:

~~~yaml
scalar:
  enabled: true
  url: /v3/api-docs
  path: /scalar
  page-title: Spring Shop API Reference
~~~

Khi ứng dụng chạy, giao diện Scalar thường được phục vụ tại /scalar. Hãy kiểm tra tài liệu tích hợp theo đúng phiên bản Scalar và Spring Boot đang dùng; phiên bản Java integration có thể thay đổi module, property và yêu cầu runtime. Tài liệu Scalar Java integration hiện mô tả hỗ trợ Spring Boot 3.x, vì vậy không mặc định rằng một bản starter đang dùng được với Spring Boot 4.x nếu chưa xác minh compatibility matrix của release đó.

Nếu có nhiều group, khai báo nguồn riêng:

~~~yaml
scalar:
  enabled: true
  sources:
    - url: /v3/api-docs/public
      title: Public API
      slug: public
      is-default: true
    - url: /v3/api-docs/admin
      title: Admin API
      slug: admin
~~~

Scalar có thể hiển thị API client và nút Test Request cho operation. Kiểm tra:

- Nguồn document có tải được từ browser không.
- Document switcher chọn đúng group mặc định.
- Server được chọn đúng, đặc biệt khi app chạy sau gateway.
- Request body và parameter được nạp vào API client đúng.
- Bearer/API key/OAuth scheme được nhận diện.
- Token không bị nhúng sẵn vào HTML hoặc JavaScript public.
- Response thử nghiệm hiển thị status, header và body.

Không đặt token, client secret hoặc mật khẩu trong property được gửi tới browser. Những giá trị đó có thể bị người dùng xem qua DevTools, source map hoặc network request. Nếu muốn bảo vệ trang Scalar, dùng Spring Security để kiểm soát route giao diện và endpoint tài liệu.

## 8. RapiDoc như một web component khác

RapiDoc có thể được nhúng trong trang HTML bằng phần tử rapi-doc:

~~~html
<rapi-doc
  spec-url="/v3/api-docs"
  render-style="read"
  show-header="true">
</rapi-doc>
<script type="module" src="/assets/rapidoc-min.js"></script>
~~~

Đoạn trên minh họa cách truyền document vào web component. Hãy kiểm tra tên thuộc tính và giá trị được hỗ trợ theo phiên bản RapiDoc được pin trong dự án. Không dùng URL CDN không pin phiên bản trong production nếu cần tái lập giao diện.

RapiDoc hỗ trợ các phiên bản OpenAPI khác nhau theo release. Khi dùng OpenAPI 3.1 hoặc các thành phần mới như webhooks, kiểm tra compatibility matrix của chính phiên bản RapiDoc đang đóng gói.

## 9. Một OpenAPI contract cần chứa đủ thông tin để renderer trình bày

Renderer không thể hiển thị thông tin chưa được mô tả trong document. Ví dụ, nếu controller chỉ khai báo response DTO mà không mô tả response code, example hoặc security, giao diện sẽ không tự biết ý nghĩa nghiệp vụ còn thiếu.

Ví dụ OpenAPI rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Payment API
  version: 1.0.0
paths:
  /payments:
    post:
      operationId: createPayment
      tags:
        - Payments
      summary: Tạo thanh toán
      description: |
        Tạo một yêu cầu thanh toán cho đơn hàng.

        Chỉ gửi một lần với cùng idempotency key.
      security:
        - bearerAuth: []
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
          example: pay-req-10001
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PaymentRequest'
            examples:
              card:
                summary: Thanh toán bằng thẻ
                value:
                  orderId: ORD-10001
                  method: card
                  cardToken: tok_example
      responses:
        '201':
          description: Đã tạo yêu cầu thanh toán
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PaymentResponse'
              example:
                paymentId: PAY-10001
                status: PENDING
        '409':
          description: Idempotency key đã được dùng với payload khác
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    PaymentRequest:
      oneOf:
        - $ref: '#/components/schemas/CardPaymentRequest'
        - $ref: '#/components/schemas/BankPaymentRequest'
      discriminator:
        propertyName: method
        mapping:
          card: '#/components/schemas/CardPaymentRequest'
          bank: '#/components/schemas/BankPaymentRequest'
    CardPaymentRequest:
      type: object
      required: [orderId, method, cardToken]
      properties:
        orderId:
          type: string
        method:
          type: string
          enum: [card]
        cardToken:
          type: string
    BankPaymentRequest:
      type: object
      required: [orderId, method, bankCode]
      properties:
        orderId:
          type: string
        method:
          type: string
          enum: [bank]
        bankCode:
          type: string
    PaymentResponse:
      type: object
      required: [paymentId, status]
      properties:
        paymentId:
          type: string
        status:
          type: string
          enum: [PENDING, PAID, FAILED]
~~~

Đây là ví dụ contract minh họa, không phải controller hoàn chỉnh. Trong ứng dụng, springdoc có thể tạo phần lớn document từ @Operation, @Parameter, @RequestBody, @ApiResponse, @Schema và DTO; các ví dụ hoặc discriminator phức tạp có thể cần annotation hoặc customizer.

Khi thử cùng document trên nhiều giao diện, so sánh các điểm:

- operationId có hiển thị và deep link được không.
- Markdown trong description có giữ đoạn, danh sách và code không.
- Header Idempotency-Key có được trình bày là required không.
- Hai nhánh oneOf có được phân biệt bằng discriminator không.
- Example của request có thể xem và copy được không.
- Security scheme có hiển thị đúng là HTTP bearer không.
- Response 201 và 409 có thể được tìm thấy riêng không.

## 10. Kiểm tra oneOf, anyOf, allOf và discriminator

Schema composition là nơi các renderer dễ tạo cảm nhận khác nhau nhất:

- oneOf: dữ liệu phải khớp chính xác một schema trong danh sách.
- anyOf: dữ liệu có thể khớp một hoặc nhiều schema.
- allOf: dữ liệu kết hợp các schema thành phần.
- discriminator: chỉ ra field giúp chọn schema cụ thể trong các biến thể.

Không chỉ kiểm tra renderer có hiện tên các schema. Hãy kiểm tra người đọc có hiểu:

1. Các biến thể khác nhau ở field nào.
2. Field discriminator có giá trị nào.
3. Field nào bắt buộc ở mỗi biến thể.
4. Example tương ứng với schema nào.
5. $ref có mở được schema đích không.

Nếu một giao diện chỉ hiển thị danh sách schema mà không làm rõ discriminator mapping, hãy thêm description và example có chủ đích. Không làm thay đổi contract thành một schema đơn giản hơn chỉ để vừa mắt một renderer nếu điều đó làm mất ý nghĩa dữ liệu.

## 11. Kiểm tra example và mô tả

OpenAPI cho phép đặt example ở nhiều cấp: schema, parameter, media type hoặc request/response content. Các renderer có thể ưu tiên và trình bày các cấp đó khác nhau.

Nên có:

- Example hợp lệ cho request phổ biến.
- Example cho từng nhánh oneOf hoặc polymorphic type.
- Example response thành công.
- Example response lỗi có body nếu API trả error schema.
- Description giải thích đơn vị, timezone, định dạng và điều kiện nghiệp vụ.
- Example dùng dữ liệu tổng hợp, không dùng token, email, số thẻ hoặc dữ liệu khách hàng thật.

Nếu Swagger UI hiện example khác ReDoc, kiểm tra vị trí example/examples trong document trước khi chỉnh UI. Renderer không thể thống nhất một example nếu contract có nhiều ví dụ và mỗi giao diện chọn cách trình bày khác nhau.

## 12. Kiểm tra security và OAuth riêng cho từng giao diện

OpenAPI mô tả security scheme và operation requirement. Renderer đọc thông tin đó để hiển thị cách xác thực, nhưng renderer không thay thế Spring Security hoặc authorization server.

Các scheme phổ biến:

| Scheme | Thông tin trong OpenAPI |
| --- | --- |
| Bearer JWT | type: http, scheme: bearer, bearerFormat: JWT |
| API key | type: apiKey, name, in: header/query/cookie |
| Basic | type: http, scheme: basic |
| OAuth2 | type: oauth2, các flow và scope |
| OpenID Connect | type: openIdConnect, discovery URL |

Kiểm tra trên từng UI:

- Scheme được nhận diện đúng loại.
- Scope và OAuth flow hiển thị đúng.
- Authorization URL, token URL và redirect URI dùng đúng public host.
- Bearer token chỉ được lưu trong browser session theo hành vi của renderer.
- Nút Authorize không làm người dùng nghĩ rằng tài liệu đã bảo vệ API.
- Endpoint thử nghiệm vẫn được server xác thực và phân quyền như request bình thường.

Không thêm security requirement toàn cục nếu có endpoint public. Một renderer có thể hiển thị nút Authorize nổi bật, nhưng điều đó không có nghĩa mọi operation đều yêu cầu token.

Không nhúng client secret vào JavaScript hoặc cấu hình công khai. Với OAuth Authorization Code, dùng PKCE khi client là public browser app và cấu hình redirect URI chính xác ở authorization server.

## 13. Kiểm tra server URL và reverse proxy

Nút Try it out hoặc Test Request gửi request tới URL trong servers. Nếu springdoc suy ra host nội bộ từ request phía sau proxy, một số renderer có thể gọi sai địa chỉ.

Ví dụ document có:

~~~yaml
servers:
  - url: https://api.example.com
    description: Public API
~~~

Kiểm tra:

- Server URL có phải public base URL không.
- Context path có bị thêm hai lần không.
- HTTP/HTTPS có đúng theo môi trường không.
- Port nội bộ có vô tình xuất hiện trong document không.
- Proxy có truyền forwarded headers đúng không.
- Browser có thể truy cập host đó từ mạng người dùng không.

Nếu dùng cùng document ở staging và production, cân nhắc tạo server list phù hợp hoặc publish document riêng theo môi trường. Đừng để một document production trỏ vào hostname staging.

## 14. CORS và quyền truy cập document

Nếu trang docs và OpenAPI endpoint khác origin, browser phải được phép đọc response của endpoint tài liệu. CORS chỉ cho phép browser đọc response; nó không xác thực người dùng và cũng không bảo vệ nội dung OpenAPI khỏi người có quyền truy cập.

Kiểm tra:

- GET /v3/api-docs hoặc URL group trả 200 từ origin của renderer.
- Preflight được xử lý nếu request có header cần thiết.
- Security filter không trả trang login HTML thay cho JSON.
- CORS chỉ cho phép origin docs được tin cậy.
- $ref ngoài cũng được phép tải hoặc đã được bundle.
- CSP cho phép script/style/connect source mà renderer cần.

Nếu API contract chứa endpoint nội bộ hoặc thông tin nhạy cảm, kiểm soát quyền truy cập ở server và ở nơi host tài liệu. Tắt Swagger UI không tự động tắt OpenAPI JSON endpoint.

## 15. Giữ cùng một phiên bản contract cho mọi giao diện

Trong môi trường phát triển, renderer có thể đọc trực tiếp /v3/api-docs. Trong môi trường phát hành, nên cân nhắc lưu OpenAPI document như artifact có version:

~~~text
artifacts/
  openapi/
    1.4.0/
      openapi.json
      openapi.yaml
~~~

Quy trình:

1. Build ứng dụng và sinh OpenAPI document.
2. Kiểm tra document hợp lệ.
3. Lưu artifact gắn với version hoặc commit.
4. Publish artifact vào nơi được phép truy cập.
5. Cấu hình từng renderer trỏ vào cùng artifact.
6. Khi release mới, cập nhật mọi renderer cùng một lần.

Không để Swagger UI đọc document từ commit mới trong khi ReDoc vẫn đọc file cũ trên CDN. Nếu có cache, dùng versioned URL hoặc ETag/cache policy phù hợp để phát hiện document stale.

## 16. Kiểm tra renderer không làm sai ý nghĩa OpenAPI

Một giao diện có thể bỏ qua hoặc trình bày khác một số thành phần:

| Thành phần OpenAPI | Điều cần quan sát |
| --- | --- |
| operationId | Có được hiển thị, dùng làm deep link hoặc code sample không |
| deprecated | Có dấu hiệu cảnh báo operation đã deprecated không |
| tags | Có nhóm đúng và giữ thứ tự mong muốn không |
| externalDocs | Link có xuất hiện và mở đúng đích không |
| callbacks | Có hiển thị callback contract nếu renderer hỗ trợ không |
| webhooks | Có hiển thị đúng cấu trúc webhook không |
| links | Có thể xem quan hệ giữa response và operation tiếp theo không |
| x-* extensions | Extension quan trọng có được renderer hỗ trợ không |
| multipart/form-data | Field file và field thường có dễ hiểu không |
| Binary response | Media type và nội dung tải về có được mô tả đúng không |
| readOnly/writeOnly | Phân biệt request và response field có rõ không |

Không giả định mọi renderer hỗ trợ mọi phần của OpenAPI như nhau. Ghi lại các tính năng contract mà ứng dụng thực sự dùng, sau đó đối chiếu release note hoặc feature matrix của renderer đã pin.

## 17. Kiểm tra giao diện trên desktop, tablet và mobile

Một document có thể đúng nhưng giao diện vẫn khó sử dụng:

- Tên schema dài làm tràn sidebar.
- Bảng parameter quá rộng trên mobile.
- Code block không cuộn ngang được.
- Mô tả nhiều cấp heading làm điều hướng rối.
- Model expansion mở quá nhiều nội dung.
- Nút Authorize hoặc Try it out bị che trên màn hình nhỏ.
- Contrast của tag, badge hoặc trạng thái deprecated không đủ.

Kiểm tra ít nhất ba kích thước viewport: desktop, tablet và mobile. Dùng bàn phím để đi qua navigation, operation, parameter và nút tương tác. Kiểm tra focus state, heading hierarchy và tên accessible của control.

## 18. Thiết kế bộ kiểm tra theo hai lớp

Không dùng một screenshot làm bằng chứng duy nhất. Chia test thành hai lớp:

**Lớp A — contract/document**

- OpenAPI JSON/YAML parse được.
- Version OpenAPI đúng.
- Path và HTTP method bắt buộc tồn tại.
- Schema, $ref, examples và security requirement có đủ.
- Không có endpoint nội bộ ngoài ý muốn.
- Contract diff không có breaking change chưa được chấp nhận.

**Lớp B — renderer/UI**

- Trang renderer tải thành công.
- Browser tải đúng document version.
- Không có lỗi JavaScript hoặc network quan trọng.
- Tag, operation, model và examples có thể tìm thấy.
- Auth và server selector hoạt động.
- Deep link mở đúng operation.
- Layout, accessibility và responsive behavior đạt yêu cầu.

Contract test xanh không chứng minh renderer hiển thị đúng. Renderer mở được trang cũng không chứng minh contract hợp lệ hoặc request thật thành công.

## 19. Smoke test endpoint document

Kiểm tra document từ ứng dụng:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi.json

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output openapi.yaml
~~~

Kiểm tra JSON có version và paths:

~~~bash
jq -e '.openapi and (.paths | length > 0)' openapi.json
~~~

Nếu dùng nhiều group:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs/public \
  --output openapi-public.json
~~~

Kiểm tra từng URL mà renderer dùng, không chỉ URL document mặc định. Nếu UI tải được trang nhưng document trả 401, 403, 404 hoặc HTML login, phần hiển thị có thể trống hoặc báo lỗi parse.

## 20. Smoke test trên browser

Với mỗi renderer, kiểm tra một tập operation đại diện:

1. Operation có path parameter và query parameter.
2. Operation có request body và nhiều content type.
3. Operation có response thành công và response lỗi.
4. Operation có schema composition như oneOf.
5. Operation có security requirement.
6. Operation có example dài hoặc description nhiều đoạn.
7. Operation thuộc một group riêng.

Có thể dùng Playwright hoặc công cụ browser automation của dự án để:

- Mở trang UI.
- Chờ document tải xong.
- Xác nhận tên API hoặc operation quan trọng xuất hiện.
- Mở deep link.
- Kiểm tra không có request document thất bại.
- Chụp screenshot tại viewport cố định để so sánh khi nâng renderer.

Không nên khóa test vào class CSS nội bộ dễ đổi của renderer. Ưu tiên text, accessible role/name, URL, response network và các hành vi người dùng thực sự cần.

## 21. Ma trận test cho nhiều giao diện

Ví dụ ma trận kiểm tra release:

| Hạng mục | Swagger UI | ReDoc | Scalar | RapiDoc |
| --- | --- | --- | --- | --- |
| Tải đúng OpenAPI artifact | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Hiển thị operation quan trọng | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Schema composition | Bắt buộc nếu contract có dùng | Bắt buộc nếu contract có dùng | Bắt buộc nếu contract có dùng | Bắt buộc nếu contract có dùng |
| Request/response examples | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Authorize/OAuth | Test theo nhu cầu | Kiểm tra hiển thị và tính năng bản dùng | Test API client nếu dùng | Test nếu bật tương tác |
| Gửi request | Test Try it out | Không áp dụng cho bản Community Edition | Test Test Request | Test nếu bật |
| Deep link | Test khi bật | Test anchor/navigation | Test operation/schema link | Test link theo version |
| Responsive/accessibility | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Security/CORS | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |

Không đánh dấu “không áp dụng” cho một tính năng rồi bỏ qua yêu cầu sản phẩm. Nếu người dùng bắt buộc phải thử request từ tài liệu, chọn renderer hỗ trợ yêu cầu đó hoặc bổ sung một API client riêng.

## 22. Lỗi thường gặp khi dùng nhiều renderer

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Một UI thiếu operation | UI đọc nhầm group hoặc document cũ | Kiểm tra URL, artifact version và cache |
| Swagger UI hiển thị nhưng ReDoc không có Try it | ReDoc Community Edition không có Try-it console tích hợp | Chọn renderer có API client hoặc sản phẩm có tính năng phù hợp |
| Schema oneOf khó hiểu | Thiếu discriminator, description hoặc example | Bổ sung contract metadata và kiểm tra từng renderer |
| OAuth hoạt động ở UI này nhưng không ở UI khác | Redirect URL, PKCE hoặc OAuth config khác nhau | Kiểm tra redirect allowlist và config riêng renderer |
| Nút gửi request gọi sai host | servers hoặc forwarded headers sai | Sửa public server URL và proxy configuration |
| UI trống dù trang trả 200 | Document bị chặn, sai content type hoặc response là HTML login | Kiểm tra network response của browser |
| Group không xuất hiện trong top bar | UI chưa được cấu hình danh sách URL/source | Cấu hình group URL cho renderer |
| Example khác nhau giữa các UI | Renderer chọn cấp example/examples khác nhau | Chuẩn hóa vị trí và nội dung examples |
| Một số schema không render | Renderer version chưa hỗ trợ feature hoặc $ref không resolve | Pin/nâng renderer, bundle refs và kiểm tra support matrix |
| Trang hoạt động local nhưng lỗi production | CORS, CSP, context path, proxy hoặc CDN cache | Kiểm tra network/security policy trên domain thật |
| UI lộ thông tin API nội bộ | Document công bố quá rộng hoặc route docs không được bảo vệ | Giới hạn package/path và bảo vệ endpoint tài liệu |

## 23. Quy trình release khi có nhiều giao diện

1. Sinh OpenAPI document từ đúng source code và profile được phát hành.
2. Validate document và chạy contract diff.
3. Kiểm tra paths, schemas, security và examples bắt buộc.
4. Lưu artifact với version hoặc commit rõ ràng.
5. Cấu hình Swagger UI, ReDoc, Scalar hoặc RapiDoc dùng cùng artifact.
6. Chạy smoke test riêng cho từng renderer được hỗ trợ.
7. Kiểm tra OAuth, server URL, CORS và quyền truy cập trên staging.
8. Kiểm tra desktop/mobile và accessibility.
9. Publish document và giao diện theo cùng release.
10. Ghi nhận renderer version, artifact version và kết quả kiểm thử để lần nâng cấp sau có thể so sánh.

Khi nâng renderer, giữ nguyên OpenAPI artifact trong lần thử đầu. Khi nâng contract, giữ renderer version cố định trong lần thử đầu. Tách hai thay đổi giúp xác định lỗi đến từ document hay từ giao diện.

## 24. Checklist review

- [ ] springdoc là nguồn tạo OpenAPI document duy nhất.
- [ ] Mỗi renderer trỏ tới đúng JSON/YAML URL hoặc artifact version.
- [ ] Document mặc định và mọi group đều được kiểm tra.
- [ ] Swagger UI, ReDoc, Scalar hoặc RapiDoc được pin version.
- [ ] operationId, tags và deep links có ý nghĩa và ổn định.
- [ ] Schema composition, discriminator và $ref được render đúng.
- [ ] Request/response examples dễ tìm và không chứa dữ liệu thật.
- [ ] Security scheme và OAuth flow hiển thị đúng.
- [ ] Server URL và proxy prefix trỏ tới public endpoint.
- [ ] CORS, CSP và Spring Security cho phép đúng luồng tải document.
- [ ] API client/Try it out chỉ được kiểm tra ở renderer có hỗ trợ.
- [ ] Responsive layout, keyboard navigation và contrast được kiểm tra.
- [ ] CI có contract validation và browser smoke test riêng.
- [ ] Các giao diện cùng dùng một contract version khi phát hành.

Một OpenAPI document dùng chung giúp các nhóm không phải duy trì nhiều bản hợp đồng. Nhưng chất lượng trải nghiệm phụ thuộc renderer cụ thể và cách nó xử lý từng phần của document. Hãy kiểm tra contract một lần ở cấp dữ liệu, rồi kiểm tra riêng từng giao diện ở cấp hiển thị, tương tác, bảo mật và responsive behavior.

## Tài liệu tham khảo

- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – Deep Linking](https://swagger.io/docs/open-source-tools/swagger-ui/usage/deep-linking/)
- [ReDoc – OpenAPI-generated API Reference](https://github.com/Redocly/redoc)
- [Redocly CLI – build-docs](https://redocly.com/docs/cli/commands/build-docs)
- [Scalar – Spring Boot Integration](https://scalar.com/docs-for/spring-boot)
- [Scalar – Java Integration](https://scalar.com/products/api-references/integrations/java)
- [RapiDoc – OpenAPI Support](https://rapidocui.com/docs/get-started/openapi-support/)
