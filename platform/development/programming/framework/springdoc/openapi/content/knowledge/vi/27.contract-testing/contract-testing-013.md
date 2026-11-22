# Smoke test giao diện và thao tác gọi thử trên môi trường phù hợp

Smoke test cho Swagger UI kiểm tra nhanh rằng người dùng có thể mở trang tài liệu, tải đúng OpenAPI document, nhìn thấy các operation quan trọng và gửi được một request thử nghiệm đến API. Với springdoc-openapi, quy trình này cần kiểm tra cả giao diện, endpoint tài liệu và API runtime vì ba thành phần có thể hoạt động độc lập.

Một trang Swagger UI hiển thị được chưa chứng minh API gọi được. OpenAPI JSON tải thành công cũng chưa chứng minh security, CORS, server URL hoặc response runtime đúng. Vì vậy, hãy kiểm tra theo luồng từ trang tài liệu đến request thực tế, trên môi trường có dữ liệu và quyền truy cập phù hợp.

Môi trường phù hợp thường là local, integration hoặc staging có cấu hình gần production, tài khoản kiểm thử riêng và dữ liệu có thể tạo/xóa an toàn. Với production, chỉ chạy các phép kiểm tra đã được phê duyệt và có tính đọc an toàn; không dùng Try it out để tạo, cập nhật hoặc xóa dữ liệu thật tùy tiện.

## 1. Smoke test kiểm tra điều gì?

Smoke test là tập kiểm tra ngắn để phát hiện lỗi triển khai rõ ràng trước khi chạy kiểm thử sâu hơn. Với Swagger UI và springdoc-openapi, nên chia thành các lớp:

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Trang Swagger UI | Trang giao diện có mở được không? | /swagger-ui/index.html trả về trang và render UI |
| OpenAPI document | UI có tải được đặc tả đúng không? | /v3/api-docs trả JSON hợp lệ |
| Nội dung operation | Endpoint cần kiểm tra có được công bố không? | Có GET /api/orders/{id} |
| Security | Cơ chế đăng nhập/Authorize có hoạt động không? | Bearer token được gửi trong header |
| Try it out | Request có đến đúng API server và trả kết quả mong đợi không? | GET test order trả 200 |
| Hợp đồng | Response runtime có khớp schema và status được mô tả không? | JSON có field và kiểu dữ liệu đúng |

Smoke test không thay thế unit test, integration test, contract test hoặc kiểm thử hiệu năng. Nó chỉ giúp xác nhận đường đi cơ bản từ tài liệu đến một số API operation quan trọng đang hoạt động trong môi trường được chọn.

## 2. Chọn môi trường và dữ liệu kiểm thử

Trước khi mở Swagger UI, xác định rõ môi trường đang được kiểm tra:

- Base URL của Swagger UI.
- URL OpenAPI document hoặc document group.
- API server URL trong trường servers.
- Tài khoản hoặc token kiểm thử.
- Những operation được phép gọi.
- Dữ liệu test đã có sẵn hoặc quy tắc tạo và dọn dữ liệu.
- Các giới hạn về rate limit, email, thanh toán, message hoặc side effect.

Ví dụ một môi trường staging:

~~~text
Swagger UI: https://staging.example.com/swagger-ui/index.html
OpenAPI:    https://staging.example.com/v3/api-docs
API server: https://staging-api.example.com
~~~

Các địa chỉ trên chỉ là ví dụ. Dùng URL do nhóm vận hành hoặc pipeline cung cấp; không tự suy ra hostname production từ tên service.

Nên có bộ dữ liệu kiểm thử ổn định, chẳng hạn một order đã seed với mã smoke-order-001. Nếu cần thử thao tác ghi, dùng mã định danh riêng cho lần chạy và có bước cleanup. Tránh dùng tài khoản cá nhân hoặc dữ liệu khách hàng thật.

### 2.1. Chỉ kiểm tra read-only trên production

Trong production, có thể kiểm tra trang tài liệu và OpenAPI document nếu chính sách cho phép. Nếu cần gọi API, ưu tiên endpoint health hoặc operation đọc dữ liệu được thiết kế cho smoke test.

Không thử POST, PUT, PATCH hoặc DELETE lên dữ liệu thật chỉ để xác nhận nút Try it out hoạt động. Nếu tổ chức có quy trình production smoke test ghi dữ liệu, phải dùng tài nguyên kiểm thử được chỉ định, quyền hạn giới hạn, idempotency key và quy trình dọn dẹp đã được phê duyệt.

## 3. Xác nhận Swagger UI và OpenAPI document

Với cấu hình mặc định của springdoc, các URL thường gặp là:

| Thành phần | Endpoint mặc định |
|---|---|
| Trang vào Swagger UI | /swagger-ui.html |
| Swagger UI static entry | /swagger-ui/index.html |
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| OpenAPI document của group | /v3/api-docs/{group} |

Dự án có thể đổi các đường dẫn này bằng cấu hình springdoc hoặc reverse proxy. Hãy dùng URL thực tế của ứng dụng.

Mở Swagger UI trong browser và xác nhận:
1. Trang không trả 404, 5xx hoặc redirect loop.
2. Giao diện Swagger UI render hoàn chỉnh.
3. Không có lỗi JavaScript quan trọng trong Console.
4. Request tải OpenAPI document trả status thành công.
5. Danh sách tag và operation xuất hiện như dự kiến.
6. Không có URL nội bộ, localhost hoặc HTTP không phù hợp trong cấu hình API server.

Nếu UI hiển thị lỗi Failed to load API definition, kiểm tra request /v3/api-docs hoặc URL document group trong Network trước. Lỗi có thể do endpoint tài liệu bị chặn bởi security, sai path, response không phải JSON OpenAPI hoặc reverse proxy rewrite sai URL.

## 4. Kiểm tra OpenAPI document độc lập với giao diện

Swagger UI thường tải một tài liệu OpenAPI riêng. Gọi trực tiếp endpoint này giúp phân biệt lỗi giao diện với lỗi sinh đặc tả.

Ví dụ:

~~~bash
curl -i https://staging.example.com/v3/api-docs
~~~

Nếu endpoint yêu cầu xác thực, gửi credential kiểm thử theo cách được môi trường hỗ trợ. Không dán token thật vào tài liệu, terminal được chia sẻ hoặc log CI.

Có thể tải JSON vào file để kiểm tra:

~~~bash
curl -fsS \
  https://staging.example.com/v3/api-docs \
  -o openapi.json
~~~

Nếu có jq, kiểm tra nhanh cấu trúc cơ bản:

~~~bash
jq -e '.openapi and .info.title and .paths and (.paths | length > 0)' openapi.json
~~~

Kiểm tra thủ công hoặc tự động thêm:
- Trường openapi có phiên bản đúng với dự án.
- info.title và info.version có giá trị.
- Các path quan trọng có mặt.
- Operation dùng đúng HTTP method.
- servers trỏ đến API server của môi trường đang kiểm thử.
- Security scheme và security requirement có mặt ở operation cần bảo vệ.
- Request body, response và schema không bị thiếu.

Nếu dùng GroupedOpenApi, kiểm tra từng document group được công bố. Ví dụ /v3/api-docs/public và /v3/api-docs/internal có thể chứa các tập operation khác nhau; tải được document mặc định không chứng minh mọi group đều hoạt động.

## 5. Kiểm tra server URL trước khi nhấn Try it out

Swagger UI dùng URL trong servers kết hợp với path của operation để tạo request. Vì vậy, hãy xem trường này trước khi gửi request:

~~~yaml
servers:
  - url: https://staging-api.example.com
    description: Staging API
paths:
  /api/orders/{id}:
    get:
      responses:
        "200":
          description: Order found
~~~

Với cấu hình này, operation sẽ gọi:

~~~text
https://staging-api.example.com/api/orders/{id}
~~~

Nếu servers trỏ đến http://localhost:8080, hostname container hoặc production trong khi UI đang mở ở staging, Try it out có thể gửi request nhầm môi trường. Không gửi request cho đến khi xác nhận server URL và path kết hợp thành địa chỉ mong muốn.

Nếu tài liệu có nhiều server, chọn đúng server trong dropdown của Swagger UI. Ghi lại server đã chọn trong kết quả smoke test để tránh nhầm giữa local, staging và production.

## 6. Kiểm tra operation trước khi gọi thử

Mở operation cần kiểm tra và rà lại các thông tin hiển thị:

- HTTP method và path.
- Summary, description và tag.
- Path parameter, query parameter và header.
- Request body và media type.
- Response status code.
- Response content type và schema.
- Security requirement.
- Example request/response nếu có.

Ví dụ operation đọc đơn hàng:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderResponse"
        "404":
          description: Order not found
~~~

Nếu id được đánh dấu required nhưng UI không hiển thị input, hoặc request body không có schema, cần xem lại tài liệu OpenAPI trước khi kiểm tra runtime. Smoke test cũng nên xác nhận operation quan trọng không biến mất sau khi đổi profile, group hoặc cấu hình springdoc.

## 7. Authorize bằng credential kiểm thử

Nếu operation yêu cầu xác thực, dùng nút Authorize của Swagger UI.

Với Bearer authentication, nhập access token kiểm thử theo hướng dẫn giao diện. Swagger UI sẽ thêm header Authorization theo security scheme được khai báo, thường có dạng:

~~~http
Authorization: Bearer <test-access-token>
~~~

Với OAuth2 Authorization Code, hoàn thành đăng nhập bằng tài khoản test và kiểm tra token được cấp đúng scope. Nếu ứng dụng dùng public browser client, cấu hình OAuth2 phải phù hợp với browser flow; không đưa client secret production vào Swagger UI.

Sau khi Authorize:
1. Xác nhận giao diện báo trạng thái đã được authorize.
2. Chọn một operation có security requirement.
3. Nhấn Try it out và Execute.
4. Trong Network hoặc request details, xác nhận request gửi header/credential mong muốn.
5. Kiểm tra response thực tế và log phía server nếu có lỗi.

Nếu không có token, có thể chạy negative smoke test có kiểm soát:
- Endpoint bảo vệ trả 401 khi thiếu hoặc token không hợp lệ.
- Endpoint trả 403 khi token hợp lệ nhưng thiếu quyền.
- Endpoint public vẫn truy cập được nếu hợp đồng quy định public.

Không dùng token có quyền cao hơn cần thiết. Không chia sẻ token trong ảnh chụp màn hình hoặc báo cáo.

## 8. Thực hiện Try it out theo trình tự an toàn

Nên bắt đầu bằng operation GET có dữ liệu kiểm thử đã biết. Ví dụ:

1. Mở GET /api/orders/{id}.
2. Chọn Try it out.
3. Nhập smoke-order-001 vào path parameter.
4. Kiểm tra server dropdown đang là staging.
5. Nhấn Execute.
6. Xem Request URL, curl command, response code, response headers và response body.
7. Đối chiếu dữ liệu trả về với test fixture và schema OpenAPI.

Kết quả kỳ vọng có thể là:
- HTTP 200.
- Content-Type: application/json.
- Body có id, status và các field được mô tả trong OrderResponse.
- Giá trị id khớp với order test.

Nếu endpoint trả 404, kiểm tra test fixture, tenant hoặc quyền truy cập trước khi kết luận tài liệu sai. Nếu trả 401/403, kiểm tra token và scope. Nếu browser báo CORS, xem preflight và actual request trong Network; request có thể đã đến server nhưng browser không cho JavaScript đọc response.

### 8.1. Kiểm tra operation ghi với dữ liệu tạm

Chỉ làm bước này trên local, integration hoặc staging được phép ghi dữ liệu.

Ví dụ POST tạo order:

~~~json
{
  "customerReference": "swagger-smoke-2026-001",
  "items": [
    {
      "sku": "TEST-SKU-001",
      "quantity": 1
    }
  ]
}
~~~

Trước khi Execute, kiểm tra:
- Server đang chọn là môi trường test.
- Payload dùng fixture và SKU dành cho test.
- Operation không kích hoạt thanh toán, gửi hàng hoặc thông báo ra bên ngoài.
- Có cách tìm và xóa dữ liệu vừa tạo.
- Có idempotency key nếu API hỗ trợ và test có thể chạy lặp.

Sau khi Execute, xác nhận status theo hợp đồng, chẳng hạn 201 Created, response body hợp lệ và Location nếu API công bố header đó. Dùng GET để xác nhận tài nguyên vừa tạo, sau đó cleanup theo quy trình của môi trường.

Không giả định nút Try it out chỉ mô phỏng request. Khi nhấn Execute, Swagger UI gửi HTTP request thật đến server được chọn.

## 9. Kiểm tra response và đối chiếu hợp đồng

Swagger UI hiển thị response nhưng không nên được xem là một JSON Schema validator đầy đủ cho mọi response. Người kiểm thử cần đối chiếu response thực tế với OpenAPI document hoặc dùng công cụ contract validation riêng.

Các điểm kiểm tra cơ bản:

| Thành phần | Điều cần xác nhận |
|---|---|
| HTTP status | Khớp response code được công bố |
| Content-Type | Khớp media type của response |
| Body shape | Object/array và cấu trúc lồng nhau đúng |
| Property | Tên field và kiểu dữ liệu đúng schema |
| Required | Field bắt buộc có mặt |
| Nullable | Giá trị null phù hợp schema |
| Enum/constraint | Giá trị nằm trong tập/ràng buộc đã mô tả |
| Header | Location, correlation ID hoặc header công bố có mặt |
| Error response | Status và error schema đúng với tình huống lỗi |

Ví dụ response kỳ vọng:

~~~json
{
  "id": "smoke-order-001",
  "status": "CONFIRMED",
  "itemCount": 1
}
~~~

Nếu OpenAPI mô tả itemCount là integer nhưng runtime trả chuỗi "1", giao diện vẫn có thể hiển thị JSON bình thường. Đây là sai lệch hợp đồng cần được ghi nhận và xử lý.

## 10. Kiểm tra lỗi có chủ đích

Một smoke test hữu ích nên có ít nhất một số trường hợp lỗi an toàn, không chỉ happy path.

| Trường hợp | Kết quả mong đợi |
|---|---|
| GET với ID tồn tại | 200 và response schema đúng |
| GET với ID không tồn tại | 404 theo hợp đồng |
| Gọi endpoint bảo vệ không có token | 401 |
| Token thiếu scope | 403 |
| Gửi payload thiếu field bắt buộc | 400 hoặc 422 theo thiết kế API |
| Gửi enum không hợp lệ | Lỗi validation theo hợp đồng |
| Gửi Content-Type không hỗ trợ | 415 nếu API công bố hành vi này |

Chỉ thực hiện negative test trên dữ liệu và môi trường được kiểm soát. Không cố tình gửi payload gây tải lớn, file quá lớn hoặc chuỗi tấn công vào hệ thống thật khi chưa có kế hoạch kiểm thử bảo mật riêng.

Không ép mọi API phải dùng cùng một status code. Hãy đối chiếu với hợp đồng thực tế của service, ví dụ ứng dụng có thể quy ước 400 hoặc 422 cho validation error.

## 11. Kiểm tra CORS và request từ browser

Swagger UI chạy trong browser nên chịu Same-Origin Policy và CORS. Nếu UI và API khác origin, browser cần nhận CORS header phù hợp.

Trong tab Network:
1. Tìm request OPTIONS nếu browser gửi preflight.
2. Kiểm tra Access-Control-Allow-Origin.
3. Kiểm tra Access-Control-Allow-Methods.
4. Kiểm tra Access-Control-Allow-Headers, đặc biệt khi request dùng Authorization hoặc Content-Type.
5. Kiểm tra response của actual request cũng có CORS header phù hợp.
6. Nếu dùng cookie credentials, xác nhận origin cụ thể và Access-Control-Allow-Credentials đúng chính sách.

CORS không thay authentication hoặc authorization. curl và Postman không thực thi CORS như browser, vì vậy một request thành công từ terminal không chứng minh Try it out sẽ hoạt động. Ngược lại, browser có thể chặn JavaScript đọc response dù server đã nhận request.

Nếu UI và API cùng origin, thường không cần CORS cho luồng đó. Đừng mở wildcard origin chỉ để làm smoke test pass.

## 12. Tự động hóa smoke test trang Swagger UI bằng Playwright

Có thể tự động kiểm tra trang UI render và OpenAPI document được tải bằng Playwright. Ví dụ dưới đây giả định ứng dụng dùng endpoint mặc định /v3/api-docs:

~~~typescript
import { test, expect } from "@playwright/test";

test("Swagger UI loads the expected OpenAPI document", async ({ page }) => {
  const docsResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());

    return (
      url.pathname.endsWith("/v3/api-docs") &&
      response.request().method() === "GET"
    );
  });

  await page.goto(process.env.SWAGGER_UI_URL!);

  await expect(page.locator(".swagger-ui")).toBeVisible();

  const docsResponse = await docsResponsePromise;
  expect(docsResponse.ok()).toBeTruthy();

  const spec = await docsResponse.json();

  expect(spec.openapi).toMatch(/^3\./);
  expect(spec.info.title).toBeTruthy();
  expect(Object.keys(spec.paths ?? {}).length).toBeGreaterThan(0);
  expect(spec.paths).toHaveProperty("/api/health");
});
~~~

Thiết lập biến môi trường SWAGGER_UI_URL trong job CI bằng URL của môi trường test. Thay /api/health bằng path thật mà nhóm muốn kiểm tra.

Nếu dùng context path, URL document group hoặc springdoc.swagger-ui.url trỏ đến một file khác, điều chỉnh điều kiện nhận diện response cho đúng. Selector .swagger-ui là selector giao diện của Swagger UI; nếu nâng version hoặc tùy biến UI, có thể cần cập nhật selector.

Đoạn test này kiểm tra trang và document được tải, không tự nhấn Execute trên operation. Nên giữ phần kiểm tra Try it out thành bước thủ công có kiểm soát hoặc viết API integration/contract test riêng. Tự động click vào các nút giao diện có thể phụ thuộc DOM và dễ hỏng khi nâng version Swagger UI.

## 13. Kiểm tra endpoint bằng HTTP trong CI

Ngoài browser smoke test, CI có thể kiểm tra nhanh status của trang UI và OpenAPI document:

~~~bash
curl -fsS -L \
  https://staging.example.com/swagger-ui.html \
  -o swagger-ui.html

curl -fsS \
  https://staging.example.com/v3/api-docs \
  -o openapi.json

jq -e '.openapi and .info.title and (.paths | length > 0)' openapi.json
~~~

Nếu endpoint được bảo vệ, cung cấp credential test thông qua secret store của CI và dùng cách xác thực phù hợp. Không ghi access token ra log.

Các bước kiểm tra có thể mở rộng:
- Kiểm tra path quan trọng bằng jq.
- Kiểm tra server URL không trỏ về production hoặc localhost.
- Validate OpenAPI document bằng validator tương thích với phiên bản đặc tả.
- So sánh với baseline để phát hiện breaking changes.
- Upload JSON/YAML như build artifact để reviewer xem lại.

HTTP check không xác nhận JavaScript UI render đúng. Vì vậy, nếu giao diện là một phần quan trọng của sản phẩm, giữ ít nhất một browser smoke test.

## 14. Ghi nhận kết quả smoke test

Một báo cáo ngắn nên có đủ thông tin để tái hiện:

| Trường | Ví dụ |
|---|---|
| Môi trường | staging |
| Thời điểm/build | build number hoặc commit |
| Swagger UI URL | URL giao diện đã kiểm tra |
| OpenAPI version | 3.1.0 |
| Document group | public |
| Operation | GET /api/orders/{id} |
| Server được chọn | staging API |
| Authentication | test user, scope orders:read |
| Request fixture | smoke-order-001 |
| Kết quả | 200, JSON hợp lệ |
| Cleanup | Không tạo dữ liệu / đã xóa fixture |
| Lỗi phát hiện | Không có hoặc mô tả ngắn |

Không đưa token, cookie, mật khẩu hoặc dữ liệu cá nhân vào báo cáo. Nếu đính kèm ảnh chụp Swagger UI, che thông tin xác thực và dữ liệu nhạy cảm.

## 15. Lỗi thường gặp và cách xử lý

**Swagger UI mở được nhưng không tải được API definition.** Kiểm tra URL document trong Network, status HTTP, response content type, security và path sau reverse proxy.

**UI tải tài liệu nhưng không có operation.** Kiểm tra đúng document group, path filter, package scan và cấu hình springdoc.

**Try it out gọi nhầm môi trường.** Xem dropdown server và trường servers trong OpenAPI trước khi Execute.

**Request bị 401.** Kiểm tra token hết hạn, scheme Bearer, header Authorization và authentication filter.

**Request bị 403.** Token có thể hợp lệ nhưng thiếu role/scope hoặc bị policy từ chối.

**Browser báo CORS nhưng curl thành công.** Kiểm tra preflight và response CORS của actual request. curl không mô phỏng browser CORS.

**Response hiển thị nhưng sai schema.** Swagger UI không thay thế validator response. Dùng contract test để xác nhận kiểu, required, enum và constraint.

**POST tạo dữ liệu trùng khi chạy lại.** Dùng fixture riêng, idempotency key nếu có và cleanup sau test.

**Swagger UI không có nút Try it out hoặc method bị vô hiệu hóa.** Kiểm tra cấu hình springdoc.swagger-ui.supportedSubmitMethods, cấu hình UI tùy chỉnh và method có được khai báo trong operation hay không.

**Tài liệu được tải từ group khác với dự kiến.** Kiểm tra springdoc.swagger-ui.url, springdoc.swagger-ui.urls và endpoint /v3/api-docs/{group}.

**Test production gây side effect.** Chuyển thao tác ghi sang staging hoặc sandbox, chỉ giữ các kiểm tra production read-only đã được phê duyệt.

## 16. Checklist hoàn tất

- [ ] Môi trường và base URL đã được xác nhận.
- [ ] Có tài khoản và dữ liệu kiểm thử riêng.
- [ ] Swagger UI mở được và render đầy đủ.
- [ ] OpenAPI document tải thành công.
- [ ] Phiên bản OpenAPI, title và version đúng.
- [ ] Document group chứa các operation cần kiểm tra.
- [ ] servers trỏ đến đúng môi trường.
- [ ] Parameter, request body, response và security metadata hiển thị đúng.
- [ ] Authorize bằng credential kiểm thử thành công.
- [ ] Một operation GET với fixture trả kết quả mong đợi.
- [ ] Nếu thử ghi, dữ liệu chỉ nằm trong môi trường test và đã cleanup.
- [ ] Status, Content-Type, response body và header khớp hợp đồng.
- [ ] CORS được kiểm tra trên browser khi UI/API khác origin.
- [ ] Không có token hoặc dữ liệu nhạy cảm trong báo cáo.
- [ ] Có HTTP/browser smoke test phù hợp trong CI.
- [ ] Đã ghi nhận môi trường, build và operation được kiểm tra.

## Tài liệu tham khảo

- [springdoc-openapi – Getting Started](https://springdoc.org/): endpoint OpenAPI, Swagger UI và cấu hình tích hợp Spring Boot.
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): cấu hình URL tài liệu, server, authorize và Try it out.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): mô tả server, operation, parameter, request body, response và security.
- [Playwright – Writing Tests](https://playwright.dev/docs/writing-tests): tự động hóa kiểm tra giao diện browser.
- [MDN – Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): hành vi CORS và preflight trong browser.
