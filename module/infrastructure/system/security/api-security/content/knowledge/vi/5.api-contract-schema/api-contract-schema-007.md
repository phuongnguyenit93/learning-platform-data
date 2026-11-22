# Contract test giữa producer và consumer

Trong một hệ thống có nhiều service, producer (dịch vụ cung cấp API) và consumer (dịch vụ hoặc ứng dụng gọi API) thường được phát triển, kiểm thử và triển khai ở các thời điểm khác nhau. Producer có thể thay đổi endpoint hoặc schema mà không biết consumer đang phụ thuộc vào trường dữ liệu nào; consumer cũng có thể giả định sai về status code, header hoặc yêu cầu xác thực. Một thay đổi tưởng như nhỏ vì thế có thể làm hỏng tích hợp hoặc tạo ra lỗ hổng bảo mật.

**Contract test** kiểm tra các cam kết ở ranh giới giao tiếp giữa hai phía. Bài kiểm thử xác nhận request mà consumer gửi phù hợp với hợp đồng và response mà producer trả về đáp ứng những điều consumer cần. Trong API Security, hợp đồng còn cần thể hiện yêu cầu xác thực, quyền cần có, hành vi khi bị từ chối, giới hạn dữ liệu đầu vào và những trường được phép xuất hiện trong response.

Contract test giúp phát hiện sớm sự không tương thích, nhưng không chứng minh toàn bộ logic phân quyền hoặc an toàn của hệ thống. Các kiểm tra quyền trên từng đối tượng, trạng thái nghiệp vụ, chống SSRF và giới hạn tài nguyên vẫn cần những bài kiểm thử chuyên biệt.

## 1. Producer, consumer và API contract

Producer là thành phần sở hữu và triển khai API. Consumer là thành phần sử dụng API đó. Một producer có thể phục vụ nhiều consumer, và một consumer có thể gọi nhiều producer.

API contract mô tả cách hai phía giao tiếp mà không phụ thuộc vào cấu trúc nội bộ của từng ứng dụng. Một hợp đồng HTTP thường bao gồm:

| Thành phần | Nội dung cần xác định |
| --- | --- |
| Endpoint | Path, HTTP method, query parameter, path parameter và content type. |
| Request | Header, cấu trúc body, trường bắt buộc, kiểu dữ liệu, giới hạn độ dài và miền giá trị. |
| Response | Status code, header, schema, nullability và ý nghĩa của từng trường. |
| Security | Cơ chế xác thực, scope hoặc quyền cần có, hành vi với credential thiếu/sai và trường hợp không đủ quyền. |
| Error | Cấu trúc lỗi, mã lỗi ổn định và status code cho từng tình huống. |
| Operational behavior | Timeout, pagination, rate limit, retry, idempotency và header liên quan như `Retry-After`. |

Contract cần mô tả hành vi quan sát được từ bên ngoài. Nó không nên buộc consumer biết tên bảng database, class nội bộ, cách producer triển khai authorization hay topology của service.

### 1.1. Contract test khác gì các loại kiểm thử khác?

| Loại kiểm thử | Câu hỏi chính | Phạm vi |
| --- | --- | --- |
| Unit test | Một hàm hoặc thành phần có xử lý đúng logic riêng không? | Một đơn vị code, thường cô lập dependency. |
| Integration test | Các thành phần có phối hợp đúng khi kết nối thật không? | Nhiều thành phần, có thể gồm database, broker hoặc HTTP server. |
| Contract test | Request và response giữa hai phía có tuân theo cam kết đã thống nhất không? | Ranh giới giao tiếp producer-consumer. |
| End-to-end test | Luồng nghiệp vụ hoàn chỉnh có hoạt động trong môi trường gần thực tế không? | Nhiều service và hạ tầng cùng tham gia. |

Contract test thường nhanh và tập trung hơn end-to-end test. Nó có thể chạy mà không cần dựng toàn bộ hệ thống, nhưng vẫn cần producer verification để xác nhận provider thật sự đáp ứng hợp đồng.

## 2. Hai hướng xây dựng contract

### 2.1. Contract do producer công bố

Producer định nghĩa API contract bằng một đặc tả như OpenAPI hoặc JSON Schema. Consumer sinh client, kiểm tra schema hoặc viết test dựa trên đặc tả được công bố. Producer kiểm tra implementation của mình có phù hợp với đặc tả hay không.

Cách tiếp cận này phù hợp khi producer là chủ sở hữu chính thức của API, có nhiều consumer hoặc cần công bố API cho đối tác. Đặc tả OpenAPI có thể mô tả path, method, schema, response và security scheme; các công cụ kiểm tra schema có thể phát hiện request hoặc response không đúng cấu trúc.

### 2.2. Consumer-driven contract (CDC)

Với consumer-driven contract, mỗi consumer mô tả những tương tác mà nó thực sự sử dụng. Công cụ như Pact ghi lại kỳ vọng request/response trong consumer test. Producer sau đó chạy provider verification để xác nhận phiên bản hiện tại đáp ứng các kỳ vọng đó.

CDC hữu ích khi producer phục vụ nhiều consumer có nhu cầu khác nhau. Hợp đồng tập trung vào phần giao tiếp consumer đang phụ thuộc, tránh bắt producer phải cam kết mọi chi tiết triển khai. Đổi lại, cần quản lý nhiều hợp đồng và bảo đảm tất cả consumer quan trọng đều được đại diện.

Hai cách tiếp cận có thể được kết hợp: OpenAPI là đặc tả công khai của API; CDC kiểm tra các tương tác cụ thể giữa những consumer đã biết và producer. Không nên coi một bản OpenAPI hợp lệ là bằng chứng rằng mọi consumer đang dùng API đúng cách.

## 3. Mô tả security trong API contract

Trong module API Security, contract phải thể hiện rõ các cam kết có thể quan sát được về bảo mật. Tối thiểu cần làm rõ:

- Endpoint yêu cầu loại credential nào và credential được gửi qua đâu.
- Quyền hoặc scope nào cần thiết cho thao tác.
- Request thiếu credential hoặc credential không hợp lệ được xử lý như thế nào.
- Người đã xác thực nhưng thiếu quyền nhận được phản hồi nào.
- Quy tắc che giấu tài nguyên có thể khiến producer trả `404` thay vì `403` trong trường hợp nào.
- Những trường nào được nhận, trường nào bị từ chối hoặc bỏ qua, và những trường nào được phép xuất hiện trong response.
- Lỗi validation, payload quá lớn, rate limit và lỗi nghiệp vụ có schema ổn định ra sao.

Một số status code thường gặp:

| Status | Ý nghĩa trong contract | Điều consumer cần xử lý |
| --- | --- | --- |
| `200` / `204` | Thao tác thành công, có hoặc không có response body | Đọc response theo schema hoặc xử lý phản hồi rỗng. |
| `400` / `422` | Request sai cấu trúc hoặc không thỏa điều kiện validation/nghiệp vụ theo quy ước API | Hiển thị lỗi đầu vào có kiểm soát; không retry vô ích. |
| `401` | Thiếu hoặc không chấp nhận credential | Yêu cầu xác thực lại hoặc xử lý credential hết hạn. |
| `403` | Đã xác thực nhưng không được phép thực hiện hành động | Không lặp lại request với cùng quyền. |
| `404` | Không tìm thấy tài nguyên hoặc producer chủ động che giấu sự tồn tại của tài nguyên | Xử lý như tài nguyên không khả dụng theo chính sách API. |
| `413` | Request body vượt giới hạn | Giảm kích thước payload hoặc từ chối thao tác. |
| `429` | Vượt rate limit hoặc quota | Tôn trọng `Retry-After` nếu producer cung cấp. |

Contract nên quy định hành vi nhất quán, nhưng không cần tiết lộ cho consumer lý do nội bộ nhạy cảm như user ID nào sở hữu tài nguyên hoặc policy engine nào đã từ chối. Một error response có thể cung cấp mã lỗi ổn định và thông điệp an toàn, trong khi chi tiết điều tra được giữ trong log phía server.

## 4. Ví dụ OpenAPI cho endpoint có yêu cầu bảo mật

Giả sử `orders-service` cung cấp endpoint cho phép thay đổi địa chỉ giao hàng. Consumer cần biết token phải được gửi qua Bearer Authentication, body chỉ có trường `address`, và response không tiết lộ toàn bộ entity đơn hàng.

Đoạn OpenAPI 3.1 dưới đây là ví dụ rút gọn:

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders/{orderId}/shipping-address:
    patch:
      operationId: changeShippingAddress
      summary: Change an order shipping address
      description: Requires an access token with the orders:write permission.
      security:
        - BearerAuth: []
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [address]
              properties:
                address:
                  type: string
                  minLength: 1
                  maxLength: 200
      responses:
        '200':
          description: Address changed
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderAddressView'
        '401':
          description: Missing or invalid access token
        '403':
          description: Authenticated caller lacks the required permission
        '404':
          description: Order not found or not visible to the caller
        '422':
          description: Address does not satisfy business validation
        '429':
          description: Request quota exceeded
          headers:
            Retry-After:
              schema:
                type: string
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token must carry the orders:write permission.
  schemas:
    OrderAddressView:
      type: object
      additionalProperties: false
      required: [id, status, shippingAddress]
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
        shippingAddress:
          type: string
```

OpenAPI mô tả Bearer Authentication và các phản hồi dự kiến. Vì `BearerAuth` là HTTP bearer scheme nên danh sách scope không được biểu diễn theo cú pháp OAuth2 scope của OpenAPI; mô tả quyền `orders:write` được ghi trong operation và security scheme. Nếu API sử dụng OAuth2 flow, có thể khai báo `type: oauth2` và scopes để công cụ hiểu scope trực tiếp.

`additionalProperties: false` làm rõ rằng request/response không chấp nhận hoặc công bố trường ngoài schema. Khi áp dụng vào API thực tế, cần xác định producer sẽ từ chối hay bỏ qua trường lạ và bảo đảm implementation cùng contract thống nhất. OpenAPI là đặc tả; bản thân nó không tự thực thi authorization hay lọc dữ liệu.

## 5. Consumer-driven contract với Pact

Pact là một công cụ phổ biến để triển khai consumer-driven contract testing. Consumer viết test với mock provider. Test mô tả request và response mà consumer cần; Pact tạo contract để provider xác minh sau đó.

Một interaction thường có các thành phần:

1. **Provider state:** trạng thái dữ liệu được chuẩn bị ở provider, ví dụ đơn hàng tồn tại trong tenant của người gọi và người gọi có quyền thay đổi địa chỉ.
2. **Request:** method, path, query, header và body consumer gửi.
3. **Expected response:** status code, header và body mà consumer cần xử lý.
4. **Matching rule:** quy tắc so khớp linh hoạt cho giá trị biến đổi như UUID, timestamp hoặc chuỗi có định dạng.

Ví dụ dưới đây minh họa nội dung của một interaction, không phải file Pact hoàn chỉnh được tạo bởi framework:

```json
{
  "description": "consumer changes an order shipping address",
  "providerStates": [
    {
      "name": "order belongs to tenant-a and caller has orders:write"
    }
  ],
  "request": {
    "method": "PATCH",
    "path": "/api/orders/7b6d8f6e-ff2b-4c13-8b8c-61c8f3f1d001/shipping-address",
    "headers": {
      "Content-Type": ["application/json"],
      "Authorization": ["Bearer test-token"]
    },
    "body": {
      "address": "12 Nguyen Hue, District 1"
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "body": {
      "id": "7b6d8f6e-ff2b-4c13-8b8c-61c8f3f1d001",
      "status": "PROCESSING",
      "shippingAddress": "12 Nguyen Hue, District 1"
    }
  }
}
```

Trong consumer test, token nên là credential giả dành riêng cho test hoặc được cấp bởi test identity provider. Không lưu access token thật, API key thật hay dữ liệu cá nhân thật vào Pact file. Nếu contract cần kiểm tra header `Authorization`, có thể dùng matcher để xác nhận dạng Bearer token mà không ràng buộc vào giá trị bí mật cụ thể.

### 5.1. Provider verification

Sau khi consumer test tạo contract, provider chạy verification để kiểm tra implementation thực tế. Provider state handler chuẩn bị dữ liệu và quyền phù hợp cho từng interaction. Provider verification gửi request theo contract đến provider đang chạy trong môi trường test rồi so sánh response nhận được với kỳ vọng.

Với ví dụ trên, provider state có thể tạo đơn hàng thuộc `tenant-a`, gán chủ sở hữu cho test user và cấp quyền `orders:write`. Provider cần xác minh request thành công trả đúng schema. Một interaction khác có thể thiết lập state người gọi thiếu quyền và kỳ vọng `403`, hoặc tài nguyên thuộc tenant khác và kỳ vọng `404` theo chính sách che giấu của API.

Provider verification cần chạy trên phiên bản provider ứng với code sắp triển khai. Chỉ xác minh một mock hoặc một bản build cũ không chứng minh phiên bản production sẽ đáp ứng contract.

## 6. Kiểm thử contract cho các cam kết bảo mật

Contract test nên bao phủ cả luồng thành công và những phản hồi bảo mật mà consumer phải xử lý. Có thể chia thành các nhóm sau:

| Nhóm | Tình huống trong contract test | Điều cần xác minh |
| --- | --- | --- |
| Authentication | Không gửi token, token hết hạn hoặc token sai audience | Producer trả `401` theo error contract và không thực hiện side effect. |
| Function authorization | Token hợp lệ nhưng thiếu `orders:write` | Producer trả `403` hoặc hành vi đã công bố; không thay đổi đơn hàng. |
| Object authorization | Người dùng ở tenant khác truy cập `orderId` | Producer trả `404` hoặc `403` theo chính sách nhất quán; không trả dữ liệu của tenant khác. |
| Request schema | Thiếu `address`, sai kiểu, chuỗi quá dài hoặc gửi thêm `ownerId` | Producer thực thi đúng quy tắc schema và không cho mass assignment. |
| Business validation | Đơn hàng ở trạng thái không cho phép đổi địa chỉ | Trả mã lỗi nghiệp vụ đã công bố và giữ nguyên trạng thái dữ liệu. |
| Response schema | Producer thêm trường nội bộ như `paymentToken` hoặc `ownerId` | Contract hoặc kiểm thử bảo mật phát hiện trường không được phép xuất hiện. |
| Resource limit | Payload quá lớn hoặc quota bị vượt | Producer trả `413`/`429` và header retry theo contract. |

Một số trường hợp cần được kiểm tra ở nhiều tầng. Ví dụ, contract test có thể xác nhận consumer nhận `403` khi thiếu scope, nhưng bài kiểm thử authorization chuyên sâu vẫn phải chứng minh service không thể đọc object của tenant khác, kể cả khi gọi trực tiếp backend hoặc đi qua đường mạng nội bộ.

### 6.1. Provider state phải phản ánh đúng ranh giới tin cậy

Provider state là dữ liệu chuẩn bị cho test, không phải cơ chế bảo mật production. State handler có thể tạo user, token giả, role, tenant và bản ghi cần thiết. Khi test quyền đối tượng, cần chuẩn bị ít nhất hai tenant hoặc hai chủ sở hữu để xác nhận việc cô lập dữ liệu.

Không để consumer quyết định provider state bằng cách gửi `X-User-Id` hoặc `X-Tenant-Id` tùy ý. Trong môi trường verification, test harness cần thiết lập identity theo con đường đáng tin cậy của hệ thống, chẳng hạn test issuer, fixture được xác minh hoặc cơ chế test authentication được giới hạn trong profile test.

Nếu provider state chỉ tạo dữ liệu mà không thiết lập identity/quyền, test có thể vô tình xác nhận một endpoint luôn cho phép truy cập. Nếu state cấp quyền quá rộng, test cũng có thể bỏ sót lỗi thiếu kiểm tra object hoặc tenant.

## 7. Tương thích ngược và quản lý thay đổi schema

Contract test đặc biệt hữu ích khi producer thay đổi API. Một thay đổi tương thích với consumer này có thể phá consumer khác, vì mỗi consumer chỉ dùng một phần contract.

| Thay đổi | Rủi ro tương thích |
| --- | --- |
| Thêm response field tùy chọn | Thường tương thích nếu consumer bỏ qua trường không biết; có thể phá consumer parse strict hoặc schema cấm trường lạ. |
| Thêm request field bắt buộc | Thường phá consumer cũ vì request cũ không gửi trường mới. |
| Xóa hoặc đổi tên field | Phá consumer đang đọc field đó. |
| Đổi kiểu dữ liệu hoặc thay đổi nullability | Có thể làm consumer parse lỗi hoặc xử lý sai. |
| Thu hẹp giới hạn độ dài/miền giá trị | Có thể từ chối request trước đây hợp lệ. |
| Thay đổi enum | Thêm giá trị mới có thể phá consumer giả định enum đóng; xóa giá trị luôn có nguy cơ phá tích hợp. |
| Đổi status code hoặc error schema | Có thể khiến consumer retry sai hoặc bỏ qua lỗi bảo mật. |
| Tăng scope bắt buộc hoặc thay đổi security scheme | Có thể khiến consumer hiện tại không còn quyền gọi API. |
| Thay đổi response để lộ thêm trường nhạy cảm | Là rủi ro bảo mật dù schema vẫn hợp lệ về mặt kỹ thuật. |

Không thể kết luận một thay đổi là an toàn chỉ vì JSON Schema vẫn hợp lệ. Cần xét cách consumer thực sự parse và sử dụng dữ liệu, cũng như quyền và dữ liệu mà API công bố. Với thay đổi breaking, nên có phiên bản API mới hoặc giai đoạn chuyển tiếp có thời hạn, đồng thời theo dõi consumer đang sử dụng phiên bản cũ.

### 7.1. Tránh contract quá chặt

Contract nên kiểm tra điều consumer phụ thuộc, không khóa những chi tiết không ổn định. Ví dụ:

- Dùng matcher cho UUID, timestamp và giá trị sinh động thay vì cố định một giá trị production.
- Chỉ yêu cầu các response field consumer thật sự sử dụng, trừ khi chính sách dữ liệu yêu cầu danh sách field chính xác.
- Không khẳng định thứ tự JSON object nếu định dạng không quy định thứ tự.
- Không đưa database ID nội bộ, stack trace hoặc thông tin triển khai vào contract công khai.
- Với response có dữ liệu nhạy cảm, có thể kiểm tra schema allowlist hoặc kiểm tra không xuất hiện các trường cấm thay vì chỉ kiểm tra sự tồn tại của trường mong đợi.

Contract quá chặt làm producer khó thay đổi hợp lệ; contract quá lỏng khiến thay đổi nguy hiểm lọt qua. Mức kiểm tra phải dựa trên cam kết thực sự giữa hai phía và mức độ nhạy cảm của dữ liệu.

## 8. Đưa contract test vào CI/CD

Một quy trình thường dùng với CDC có thể gồm:

1. Consumer thay đổi code và chạy consumer contract test cùng unit test.
2. Contract được tạo và publish lên Pact Broker hoặc kho quản lý hợp đồng tương đương, gắn với phiên bản consumer và commit.
3. Producer chạy provider verification với các contract đang được consumer sử dụng.
4. Kết quả verification được publish, gắn với phiên bản provider và môi trường.
5. Pipeline kiểm tra tương thích giữa phiên bản consumer/provider dự kiến triển khai và các phiên bản đang chạy.
6. Chỉ triển khai khi các hợp đồng bắt buộc đã được xác minh; theo dõi kết quả sau triển khai và giữ khả năng rollback.

Với contract dựa trên OpenAPI, pipeline có thể lint đặc tả, kiểm tra breaking change so với phiên bản trước, sinh client/server stub, chạy schema validation trên request/response mẫu và chạy provider integration test. Có thể kết hợp hai hướng để kiểm tra cả đặc tả công bố và nhu cầu thực tế của consumer.

Các kết quả nên được gắn với commit hoặc artifact version. Nếu chỉ lưu một trạng thái “contract pass” không gắn phiên bản, pipeline có thể dùng nhầm kết quả của một build cũ để cho phép deploy build mới.

## 9. Lỗi thường gặp khi triển khai contract testing

- **Chỉ kiểm tra consumer với mock:** mock phản hồi đúng theo kỳ vọng của consumer nhưng không chứng minh producer thật sự trả như vậy. Cần provider verification.
- **Không có provider state rõ ràng:** test phụ thuộc dữ liệu tồn tại ngẫu nhiên, khó tái lập và có thể không kiểm tra đúng quyền.
- **Chỉ test status `200`:** bỏ sót `401`, `403`, `404`, lỗi validation và rate limit mà consumer cần xử lý.
- **Dùng token hoặc dữ liệu thật trong contract:** làm rò rỉ bí mật vào repository, broker hoặc log pipeline.
- **Xem schema là toàn bộ bảo mật:** schema không chứng minh object authorization, tenant isolation, chống SSRF hoặc giới hạn tài nguyên được thực thi.
- **Bỏ qua consumer cũ:** producer verification chỉ chạy với consumer mới nhất có thể phá ứng dụng vẫn đang chạy phiên bản cũ.
- **Đóng chặt enum và response field không cần thiết:** làm thay đổi mở rộng thông thường trở thành breaking change.
- **Không kiểm tra side effect:** response trả lỗi nhưng database đã bị thay đổi trước khi authorization hoàn tất.
- **Không quản lý phiên bản contract:** kết quả test cũ có thể được dùng nhầm cho artifact mới.

## 10. Checklist cho producer và consumer

**Consumer** cần xác nhận:

- [ ] Chỉ phụ thuộc vào endpoint, method, header và field được công bố.
- [ ] Gửi đúng credential và xử lý `401`, `403`, `404` theo contract.
- [ ] Xử lý lỗi validation, quota và retry theo status/header đã cam kết.
- [ ] Contract test dùng token giả và dữ liệu test; không chứa secret thật.
- [ ] Consumer test phản ánh các tương tác mà ứng dụng thực sự sử dụng.

**Producer** cần xác nhận:

- [ ] OpenAPI/JSON Schema phản ánh đúng request, response và security requirement.
- [ ] Provider verification chạy với mọi contract consumer cần hỗ trợ.
- [ ] Provider state thiết lập identity, role, tenant và dữ liệu theo kịch bản kiểm thử.
- [ ] Không thực hiện side effect khi authentication, authorization hoặc validation thất bại.
- [ ] Response chỉ chứa field được phép và error response không làm lộ chi tiết nội bộ.
- [ ] Thay đổi schema, status code và quyền bắt buộc được đánh giá tương thích trước khi deploy.
- [ ] Kết quả verification được gắn với đúng phiên bản consumer, provider và môi trường.

Contract test tạo một thỏa thuận có thể kiểm chứng giữa producer và consumer. Khi hợp đồng mô tả cả schema, hành vi lỗi và yêu cầu bảo mật, hai phía có thể thay đổi độc lập với ít rủi ro hơn. Tuy nhiên, hợp đồng chỉ xác nhận hành vi tại ranh giới giao tiếp; producer vẫn phải kiểm tra quyền trên từng đối tượng, bảo vệ dữ liệu và thực thi các giới hạn an toàn trong runtime.
