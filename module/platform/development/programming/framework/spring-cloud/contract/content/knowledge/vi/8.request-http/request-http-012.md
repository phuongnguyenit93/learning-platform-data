# Xác minh yêu cầu có xác thực bằng dữ liệu kiểm thử

Trong ứng dụng microservices, consumer thường phải gửi **thông tin xác thực** khi gọi API của producer. Ví dụ, dịch vụ **Billing** gọi `GET /api/accounts/42` để đọc tài khoản của khách hàng, kèm header `Authorization: Bearer ...`. Nếu producer đổi cơ chế xác thực, yêu cầu scope khác hoặc trả mã lỗi khác với cam kết, consumer có thể thất bại dù đường dẫn và cấu trúc JSON không thay đổi.

Với **Spring Cloud Contract**, nhóm có thể mô tả request có header xác thực trong **Groovy DSL hoặc YAML DSL**, sinh kiểm thử phía producer, tạo stub cho consumer kiểm thử bằng **Stub Runner**, rồi đưa các kiểm tra vào CI. Tuy nhiên, phải hiểu ranh giới: **contract test kiểm tra hành vi giao tiếp đã mô tả**, còn việc kiểm chứng chữ ký JWT, hết hạn token, phân quyền theo người dùng và cấu hình bảo mật thực sự cần được kiểm thử với **chuỗi bộ lọc bảo mật** hoặc các bài kiểm thử bảo mật phù hợp.

Bài này thuộc chương **Request HTTP**. Mục tiêu là chuẩn bị **dữ liệu kiểm thử xác thực có thể lặp lại**, viết hợp đồng cho các trường hợp `200`, `401` và `403`, bảo đảm producer thực thi đúng kỳ vọng, đồng thời tránh nhầm một stub trả đúng phản hồi với bằng chứng rằng API được bảo vệ an toàn.

## 1. “Xác minh yêu cầu có xác thực” nghĩa là gì?

Xét API dành cho người dùng đã đăng nhập:

```http
GET /api/accounts/42
Accept: application/json
Authorization: Bearer contract-reader-token
```

Producer cần xác định request thuộc người dùng nào, token có được chấp nhận không và người dùng có quyền xem tài khoản 42 không. Nếu tất cả điều kiện đều đạt, ví dụ kỳ vọng là:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "ownerId": "user-42",
  "currency": "VND",
  "balance": 850000
}
```

Từ phía consumer, một hợp đồng hữu ích mô tả **những gì có thể quan sát tại ranh giới HTTP**: method, URL, header bắt buộc, phản hồi thành công, mã lỗi và dữ liệu consumer dùng. Những chi tiết bên trong như loại bảng lưu user hay cách producer cache token không nhất thiết thuộc hợp đồng.

Cần phân biệt các lớp kiểm tra:

| Lớp | Câu hỏi | Công cụ/kỹ thuật thường dùng |
|---|---|---|
| **Request contract** | Consumer có gửi đúng header, endpoint và format mà producer yêu cầu không? | Spring Cloud Contract DSL và generated producer tests |
| **Behavior contract** | Với dữ liệu người dùng/quyền đã xác định, producer trả `200`, `401` hay `403` và body đúng cam kết không? | Generated producer tests cùng fixture xác thực và dữ liệu nghiệp vụ |
| **Security integration** | Filter chain, token decoder/introspector, quyền truy cập và trạng thái hết hạn có hoạt động không? | Spring Security integration tests, MockMvc hoặc môi trường test với cơ chế xác thực thật |
| **Consumer integration** | HTTP client của consumer có đính kèm token và xử lý response tương ứng không? | Stub Runner, HTTP client thực của consumer |
| **End-to-end** | Hệ thống có xác thực đúng với identity provider, gateway, TLS và tài nguyên thực không? | Integration/E2E tests trong môi trường phù hợp |

Không một hàng nào tự thay thế tất cả hàng còn lại. Ví dụ, nếu Stub Runner trả `200` khi thấy chuỗi `Bearer contract-reader-token`, điều đó **không chứng minh** token đã được kiểm tra chữ ký hoặc thuộc một tài khoản có thật.

## 2. Chuẩn bị dữ liệu kiểm thử trước khi viết contract

Hợp đồng xác thực chỉ có thể kiểm tra được nếu nhóm xác định rõ **danh tính, quyền, dữ liệu tài nguyên và phản hồi**. Tránh viết một hợp đồng `200` rồi để producer verification phụ thuộc vào user ngẫu nhiên trong database chung.

Giả sử producer là **Account Service**, consumer là **Billing**. Trong môi trường kiểm thử dành riêng cho contract, thống nhất bộ fixture:

| Fixture | Ý nghĩa | Kết quả mong đợi với `GET /api/accounts/42` |
|---|---|---|
| `contract-reader-token` | Token test hợp lệ của `user-42`, có quyền `accounts.read` | `200 OK`, trả dữ liệu tài khoản 42 |
| `contract-invalid-token` | Token test không hợp lệ | `401 Unauthorized` |
| `contract-no-scope-token` | Đã xác thực nhưng thiếu `accounts.read` | `403 Forbidden` |
| Không có `Authorization` | Chưa cung cấp thông tin xác thực | Thường là `401 Unauthorized` với API dùng Bearer |
| `contract-other-user-token` | Có quyền đọc loại tài nguyên nhưng không sở hữu tài khoản 42 | `403` hoặc `404` tùy chính sách che giấu tài nguyên |
| Tài khoản số `42` | Tồn tại, thuộc `user-42` | Dữ liệu cố định: `currency=VND`, `balance=850000` |

**Tên token ở bảng là chuỗi giả phục vụ ví dụ**, tuyệt đối không phải access token hợp lệ mặc định. Để producer nhận chúng, **test profile phải có bộ xác thực test** quy định rõ cách chuyển các chuỗi fixture thành danh tính và quyền. Nếu producer dùng JWT thật, một chuỗi như `contract-reader-token` sẽ bị JWT decoder từ chối; khi đó phải dùng JWT test được ký đúng khóa kiểm thử hoặc kỹ thuật cấp token động phù hợp với DSL/build.

Bộ fixture phải xác định được:

1. **User ID:** ai đang gọi, ví dụ `user-42`.
2. **Quyền/scope:** gọi endpoint nào, ví dụ `accounts.read`.
3. **Thuộc tính tài nguyên:** tài khoản 42 thuộc user nào, tenant nào, dữ liệu nào.
4. **Tình huống từ chối:** token thiếu/sai/hết hạn, đã đăng nhập nhưng không đủ quyền.
5. **Thời gian:** nếu kiểm tra `exp`/`nbf` của JWT thì dùng clock kiểm soát được hoặc tạo token tại lúc chạy, tránh fixture tự hết hạn sau vài tuần.
6. **Kết quả HTTP:** mã status, header như `WWW-Authenticate` và schema lỗi được công bố.

Ví dụ dữ liệu trong test profile, đây là **bảng ánh xạ minh họa**, không phải file cấu hình do Spring Cloud Contract tự nhận:

```yaml
testIdentities:
  contract-reader-token:
    subject: user-42
    scopes: [accounts.read]
    active: true
  contract-no-scope-token:
    subject: user-42
    scopes: [profile.read]
    active: true
  contract-invalid-token:
    active: false
testAccounts:
  - id: 42
    ownerId: user-42
    currency: VND
    balance: 850000
```

Ứng dụng thực tế phải **hiện thực cách tải fixture và kiểm tra token** trong test configuration; Spring Cloud Contract không tự đọc bảng `testIdentities` này. Có thể dùng một implementation kiểm thử của token introspector, bộ tạo JWT ký bằng khóa dành riêng cho test, hoặc một test identity provider. Không sử dụng credentials hay khóa riêng production.

## 3. Thiết kế ma trận kịch bản HTTP

Nên bắt đầu từ những đường đi ảnh hưởng trực tiếp đến consumer:

| Kịch bản | Authentication | Authorization | HTTP thường kỳ vọng | Consumer cần xử lý |
|---|---|---|---|---|
| Đọc tài khoản hợp lệ | Token hợp lệ | Đủ quyền, đúng chủ sở hữu | `200` | Parse và sử dụng JSON |
| Thiếu Bearer token | Chưa xác thực | Chưa xét | `401` | Đăng nhập lại, bổ sung credentials hoặc xử lý lỗi |
| Token không hợp lệ/hết hạn | Thất bại | Chưa xét | `401` | Làm mới token nếu chính sách cho phép; không retry vô hạn |
| Đã xác thực, thiếu scope | Thành công | Bị từ chối | `403` | Hiển thị thiếu quyền hoặc dừng thao tác |
| Có scope nhưng sai chủ sở hữu | Thành công | Bị từ chối | `403` hoặc `404` | Tuân theo chính sách API, không tự đoán quyền |
| Tài khoản không tồn tại | Thành công | Có thể đủ quyền loại tài nguyên | `404` | Xử lý tài nguyên không tồn tại |

**`401` và `403` không đồng nghĩa.** Với Bearer authentication, `401` thường dùng khi request chưa được xác thực hợp lệ; `403` thường dùng khi đã xác thực nhưng thiếu quyền. Tuy vậy, một API có thể cố ý trả `404` để không tiết lộ tài nguyên; hợp đồng phải theo **chính sách đã thống nhất**, không gán cứng một mã lỗi cho mọi hệ thống.

Với OAuth2 Bearer, nhiều API dùng header `WWW-Authenticate` cho trường hợp cần thử xác thực, theo cấu hình và chuẩn áp dụng. Chỉ khai báo giá trị header cụ thể nếu producer **thực sự cam kết** cấu trúc đó và consumer cần sử dụng.

## 4. Groovy DSL: xác minh request mang Bearer token hợp lệ

Ví dụ contract thành công cho Billing khi gọi Account Service. Giả sử test profile đã được cấu hình để chấp nhận `contract-reader-token` với danh tính `user-42` và scope `accounts.read`.

File minh họa: `src/test/resources/contracts/billing/get_account_authorized_200.groovy`.

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billing_get_account_authorized_200'
    description 'Billing đọc tài khoản bằng token có quyền accounts.read'

    request {
        method GET()
        url '/api/accounts/42'
        headers {
            header 'Accept', 'application/json'
            header 'Authorization', 'Bearer contract-reader-token'
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            ownerId: 'user-42',
            currency: 'VND',
            balance: 850000
        )
    }
}
```

### 4.1. Contract này kiểm tra được điều gì?

Khi tích hợp Spring Cloud Contract với producer test đúng cách, bài kiểm thử sinh ra sẽ gửi một request có `Authorization` và so sánh response với kỳ vọng trong DSL. Nếu producer:

- không nhận header hoặc không chấp nhận token test, test có thể trả `401`;
- nhận token nhưng không cho phép `accounts.read`, test có thể trả `403`;
- trả `200` nhưng body thiếu `currency` hoặc đổi `balance` thành chuỗi, test có thể thất bại nếu điều kiện kiểm tra tương ứng được tạo đúng;
- trả `200` và các trường phù hợp, test vượt qua kịch bản đã mô tả.

**Điều kiện quyết định:** generated test phải thật sự chạy qua security configuration mà hệ thống muốn kiểm tra. Nếu test base dùng controller độc lập và bỏ qua Spring Security filters, test xanh **không chứng minh** header `Authorization` đã được xác minh.

Ngoài ra, vì contract đang dùng giá trị cố định `contract-reader-token`, producer test phải **có dữ liệu và cơ chế nhận token này**. Không thay một token thật bằng chuỗi giả rồi mong toàn bộ kiểm thử bảo mật vẫn chạy đúng.

### 4.2. Khi nào dùng matcher cho header Authorization?

Trong ứng dụng thực, access token thường thay đổi theo thời điểm, môi trường hoặc người dùng. Một contract khóa chặt toàn bộ chuỗi JWT có thể làm kiểm thử giòn. Có thể cần **request matcher** để mô tả quy tắc định dạng Bearer, hoặc cơ chế tạo giá trị từ test setup.

Tuy nhiên, phải phân biệt:

- **Matcher định dạng** như `Bearer <token>` chỉ chứng minh header có dạng hợp lệ theo mẫu, **không chứng minh token xác thực thành công**.
- **Giá trị cụ thể để producer test sử dụng** vẫn phải được môi trường producer chấp nhận.
- **Stub mapping** có thể khớp một mẫu header rộng; nếu mẫu quá rộng, stub trả `200` cho token mà producer thật sẽ từ chối.
- **Kiểm tra bảo mật** cần validate chữ ký/expiry/issuer/audience/scope với cơ chế thật hoặc test double có phạm vi được định nghĩa rõ.

Do cú pháp matcher và cách phân biệt phía consumer/producer của DSL thay đổi theo phiên bản, hãy sử dụng API matcher trong **tài liệu Spring Cloud Contract đã ghim cho dự án**. Tránh chép một regex “nhận mọi token” mà không hiểu generated producer request và WireMock mapping được tạo ra thế nào.

## 5. YAML DSL: cùng hành vi được diễn đạt theo cấu trúc

Nếu nhóm ưu tiên YAML cho tài liệu hợp đồng dễ review, có thể định nghĩa tương đương như sau:

File minh họa: `src/test/resources/contracts/billing/get_account_authorized_200.yml`.

```yaml
name: billing_get_account_authorized_200
description: Billing đọc tài khoản bằng token có quyền accounts.read
request:
  method: GET
  url: /api/accounts/42
  headers:
    Accept: application/json
    Authorization: Bearer contract-reader-token
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    ownerId: user-42
    currency: VND
    balance: 850000
```

Đoạn YAML này diễn tả **cùng kịch bản** với Groovy ở mục 4. Trong một repository đang sinh test/stub, **chỉ chọn một bản làm nguồn chính** cho request đó, trừ khi cố ý cần nhiều hợp đồng có điều kiện khớp khác nhau. Giữ cả hai có thể tạo generated tests trùng hoặc hai mappings cùng nhận một request.

Với body JSON, chú ý `42` và `850000` là số trong YAML, còn `user-42` và `VND` là chuỗi. Việc đổi kiểu có thể ảnh hưởng consumer ngay cả khi response vẫn là JSON hợp lệ.

### 5.1. Các header khác có thể liên quan đến auth

Ngoài `Authorization`, tùy API còn có:

| Header/thuộc tính | Trường hợp sử dụng | Lưu ý trong contract |
|---|---|---|
| `Cookie` | Session-based authentication | Không viết session ID thật; chuẩn bị session fixture phù hợp |
| `X-API-Key` | Xác thực bằng API key | Chỉ dùng khóa test giả/lấy từ test environment |
| `X-Tenant-Id` | Định tuyến tenant theo hợp đồng API | Header này **không tự chứng minh quyền**; producer phải so sánh với token/identity |
| `X-Correlation-Id` | Truy vết request | Không phải cơ chế xác thực |
| `X-CSRF-TOKEN` hoặc biến thể của dự án | Bảo vệ thao tác thay đổi trạng thái trong session app | Kiểm tra nếu ứng dụng thực yêu cầu; không mặc định mọi Bearer API phải gửi CSRF token |
| `Accept` và `Content-Type` | Thỏa thuận định dạng JSON | Không thay thế auth nhưng có thể là một phần matcher/response |

Hợp đồng cần phản ánh **giao diện thật của producer**, không thêm header chỉ để khiến stub nhận đúng tình huống kiểm thử.

## 6. Hợp đồng cho token không hợp lệ: `401 Unauthorized`

Đối với consumer, `401` quan trọng vì có thể dẫn tới đăng nhập lại hoặc luồng làm mới token. Một kịch bản với **token sai được chỉ định rõ** cũng giúp stub phân biệt được mapping với request dùng token hợp lệ.

Ví dụ Groovy:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billing_get_account_invalid_token_401'
    description 'Billing nhận 401 khi Bearer token không hợp lệ'

    request {
        method GET()
        url '/api/accounts/42'
        headers {
            header 'Authorization', 'Bearer contract-invalid-token'
        }
    }

    response {
        status 401
        headers {
            header 'WWW-Authenticate', 'Bearer'
        }
    }
}
```

**Điều kiện thực thi:** security config của producer trong test environment phải từ chối `contract-invalid-token`, và nếu hợp đồng yêu cầu `WWW-Authenticate: Bearer` thì producer thật phải trả header ấy. Không tự thêm body lỗi hay thông điệp `error_description` nếu API không công bố chúng.

### 6.1. Thiếu token có khác token sai không?

Hai tình huống thường cùng trả `401` nhưng **request khác nhau**:

```http
GET /api/accounts/42
Accept: application/json
```

và:

```http
GET /api/accounts/42
Authorization: Bearer contract-invalid-token
```

Với producer tests, có thể viết hợp đồng riêng cho trường hợp thiếu header và kiểm tra status. Nhưng khi **đóng gói HTTP stub**, một mapping chỉ quy định `GET /api/accounts/42` mà **không ràng buộc việc vắng mặt của Authorization** có thể cũng khớp request mang token hợp lệ. Nếu hai mappings trả `200`/`401` khác nhau, stub server có thể chọn mapping không như người kiểm thử mong đợi.

Do đó:

1. Kiểm tra mapping thực tế mà plugin sinh từ contract.
2. Khi cần kịch bản “không có header”, định nghĩa điều kiện **header vắng mặt** bằng matcher được phiên bản DSL/WireMock hỗ trợ hoặc kiểm thử trường hợp này bằng lớp bảo mật thực trong producer.
3. Không phụ thuộc ngầm vào thứ tự nạp file hay độ ưu tiên mapping.
4. Chạy consumer test với **cả request có và không có token**, bảo đảm stub không vô tình trả `401` cho request hợp lệ.

Với Bearer flow, nên có **security integration test trực tiếp** cho tình huống thiếu token ngay cả khi cũng có contract `401`.

## 7. Đã xác thực nhưng thiếu quyền: `403 Forbidden`

Một request có token được chấp nhận vẫn có thể không đủ quyền truy cập. Ví dụ, user có scope `profile.read` nhưng API yêu cầu `accounts.read`.

YAML DSL cho tình huống này:

```yaml
name: billing_get_account_insufficient_scope_403
description: Token đã xác thực nhưng không có quyền đọc tài khoản
request:
  method: GET
  url: /api/accounts/42
  headers:
    Authorization: Bearer contract-no-scope-token
response:
  status: 403
```

Producer test profile phải ánh xạ `contract-no-scope-token` thành một danh tính **đã xác thực** nhưng không có scope cần thiết. Nếu token này bị coi là sai hoàn toàn, producer sẽ trả `401` và test thất bại. Đó là dấu hiệu fixture đang mô phỏng sai kịch bản, không phải lý do để đổi `403` thành `401` một cách tùy tiện.

**Lưu ý về phân quyền theo tài nguyên:** một người dùng có scope `accounts.read` chưa chắc được đọc **mọi** tài khoản. Ví dụ, `contract-other-user-token` có thể bị từ chối khi xem tài khoản 42 dù có scope tổng quát. Để bảo vệ ranh giới sở hữu, cần thêm kịch bản kiểm tra `ownerId` hoặc `tenantId` với dữ liệu kiểm thử tương ứng.

### 7.1. Đừng biến contract testing thành kiểm thử toàn bộ chính sách bảo mật

Có thể mô tả các trường hợp lỗi mà consumer cần xử lý, nhưng các tổ hợp chi tiết như JWT hết hạn đúng một mili giây, `nbf`, issuer sai, audience sai, khóa ký bị thu hồi, mTLS, nhiều vai trò lồng nhau thường phù hợp với **security integration tests chuyên biệt**.

Ví dụ ma trận bảo mật mở rộng:

| Trường hợp | Lớp kiểm thử nên chịu trách nhiệm chính |
|---|---|
| Không gửi `Authorization` → `401` | Contract nếu consumer phụ thuộc; security integration cũng nên có |
| Token test sai → `401` | Contract và security integration |
| Token hợp lệ thiếu scope → `403` | Contract và security integration |
| JWT sai chữ ký/issuer/audience → từ chối | Security integration với decoder/introspector thật |
| Token hết hạn → từ chối | Security integration với clock kiểm soát được |
| Phân quyền theo `ownerId`/tenant | Security/integration với fixture dữ liệu |
| Body thành công phải có `id`, `currency`, `balance` | Contract giữa producer và consumer |

Việc phân chia này giữ contract rõ ràng nhưng vẫn kiểm tra được các yếu tố an ninh cần thiết.

## 8. Cấu hình producer test để không vô tình bỏ qua xác thực

Spring Cloud Contract sinh kiểm thử từ DSL, nhưng bài test chỉ đáng tin cậy nếu **test base** nạp đúng ứng dụng và **đi qua Spring Security filter chain**. Dự án có thể dùng MockMvc, RestAssured hoặc môi trường web khác, tùy phiên bản và cấu hình plugin.

Với producer Spring MVC dùng MockMvc, một hướng cấu hình thường gặp là:

```java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
public abstract class ContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

Đây là **ví dụ test base**, không phải cấu hình hoàn chỉnh để bật Spring Cloud Contract trong mọi dự án. Cần:

- Cấu hình plugin sinh test sử dụng lớp `ContractTestBase` và **test mode tương ứng với MockMvc**.
- Khai báo dependency thích hợp theo phiên bản Spring Boot, Spring Cloud Contract và RestAssured MockMvc.
- Cấp dữ liệu tài khoản số 42 và authentication fixture cho test context.
- Bảo đảm Spring Security filter chain được nạp và áp dụng; `addFilters = true` cho phép filter tham gia vào `MockMvc`, nhưng bản thân nó không tạo bean security.
- Nếu ứng dụng dùng Spring WebFlux hoặc test mode khác, dùng base/test setup tương ứng thay vì sao chép nguyên ví dụ MVC.

Điều cần quan sát sau khi chạy là test `200` **chỉ đạt với token hợp lệ**. Nếu bỏ token mà controller vẫn trả `200`, rất có thể security filter bị bypass, test profile cấp quyền quá rộng hoặc endpoint không được bảo vệ như dự kiến.

### 8.1. Tránh cấu hình làm mất giá trị kiểm thử xác thực

Các lỗi thường gặp:

- Dùng `MockMvcBuilders.standaloneSetup(controller)` rồi tưởng đã kích hoạt security filter chain. Khi dùng standalone setup, filter phải được tích hợp chủ động; nếu không, endpoint có thể trả `200` dù không có token.
- Dùng `@WithMockUser` hoặc mock `SecurityContext` trong **mọi** generated contract test. Điều này có thể khiến kịch bản “token invalid” chạy với danh tính mock hợp lệ và không còn kiểm tra request header thực tế.
- Tắt toàn bộ security cho test profile bằng một rule `permitAll()`. Bài test `200` sẽ dễ xanh nhưng không còn xác minh header xác thực.
- Dùng token test đã hết hạn hoặc fixture tài khoản thay đổi theo môi trường dùng chung. Khi đó test đỏ không phản ánh thay đổi API mà chỉ phản ánh dữ liệu không ổn định.

Mock identity hoặc test token decoder **có thể hữu ích**, nhưng phải đặt ranh giới rõ: nó giúp mô phỏng danh tính/scope trong contract test, còn các bài test bảo mật riêng vẫn cần kiểm chứng thực tế signature/expiry/authority mapping.

### 8.2. Kiểm tra bổ sung để xác nhận filters đang hoạt động

Một bài security integration test trực tiếp qua `MockMvc`, độc lập với DSL, có thể như sau:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class AccountSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void requiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
            .andExpect(status().isUnauthorized());
    }
}
```

Test này có ý nghĩa khi endpoint thực sự dùng chính sách trả `401` cho request thiếu credentials. Nó kiểm tra cơ chế bảo vệ trong app context; **không thay thế producer contract tests** kiểm tra response đã cam kết với consumer.

## 9. Chuẩn bị token test sao cho tái lập được

Không nên đưa một JWT sản xuất hay token lấy thủ công từ người dùng vào file `.groovy`, `.yml`, log CI hoặc artifact stub. Token loại này có thể hết hạn, bị thu hồi hoặc lộ thông tin nhạy cảm.

Hai hướng thiết kế phổ biến:

### 9.1. Hướng A — test-specific token verifier/introspector

Trong test profile:

- Nhận `contract-reader-token` → danh tính `user-42`, scope `accounts.read`.
- Nhận `contract-no-scope-token` → danh tính `user-42`, scope `profile.read`.
- Nhận `contract-invalid-token` → báo không hợp lệ.
- Không có Bearer token → tiếp tục luồng `401` thực tế của security filter.
- Dữ liệu account 42 được tạo mới hoặc reset trước mỗi lần chạy.

Ưu điểm là **fixture ổn định, contract dễ đọc và test chạy nhanh**. Giới hạn là verifier/introspector lúc này thuộc **test double**; nó không chứng minh producer tương tác đúng với identity provider thật hoặc giải mã JWT đúng. Phải có security integration test khác.

Quan trọng: chỉ kích hoạt test verifier trong profile kiểm thử; không để ứng dụng production chấp nhận chuỗi `contract-reader-token`.

### 9.2. Hướng B — JWT thử nghiệm có chữ ký và thời gian kiểm soát được

Nếu muốn đi qua JWT decoder thật:

1. Tạo cặp khóa hoặc secret **chỉ dành cho test**; không dùng production key.
2. Tạo token chứa `sub=user-42`, issuer, audience và scope/roles đúng mà producer yêu cầu.
3. Dùng clock kiểm soát được, hoặc phát hành token mới khi bắt đầu mỗi test để tránh tự hết hạn.
4. Tạo token thiếu scope, sai chữ ký, sai issuer hoặc hết hạn cho các security test riêng.
5. Khi contract DSL cần header giá trị cố định, thiết kế cơ chế cấp token/matcher hỗ trợ **giá trị động cho phía producer** phù hợp với phiên bản Spring Cloud Contract; không ép một JWT sẽ hết hạn vào file trong nhiều năm.

Hướng B xác thực sâu hơn nhưng cần cấu hình tinh tế hơn cho generated tests. Với người mới học, có thể bắt đầu từ hướng A để hiểu producer–consumer contract, sau đó bổ sung security integration test với decoder thật.

### 9.3. Dữ liệu nghiệp vụ cũng phải ổn định

Ngay cả token hợp lệ vẫn có thể nhận `404` nếu tài khoản 42 chưa được tạo, hoặc `403` nếu owner của tài khoản không khớp `user-42`. Hãy seed dữ liệu test **trước khi generated test chạy** và dọn dẹp sau test, hoặc dùng transaction/test container/fixture isolation theo khả năng của dự án.

Tránh phụ thuộc vào:

- User thực trong production hoặc staging dùng chung.
- Token mà một developer copy từ trình duyệt.
- Account ID ngẫu nhiên không được kiểm soát.
- Đồng hồ máy CI không đồng bộ trong test hết hạn.
- Quyền người dùng đã được thay đổi bởi bài test khác.

## 10. Consumer dùng Stub Runner để kiểm tra cách gửi Authorization

Khi producer contract test đã chứng minh implementation đáp ứng hợp đồng, build có thể đóng gói các mappings thành **stub artifact**. Consumer tải stub bằng Stub Runner, trỏ HTTP client đến server giả lập và gọi API.

Ví dụ cấu hình Stub Runner trong một bài Spring Boot test của Billing:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:account-service:1.0.0-SNAPSHOT:stubs:8085",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class AccountClientContractIntegrationTest {
    // Cấu hình client của Billing gọi http://localhost:8085.
    // Viết @Test để kiểm tra client gắn Authorization và xử lý 200/401/403.
}
```

Đây là phần **khai báo môi trường test**, chưa phải một test JUnit hoàn chỉnh. Điều kiện để chạy: dependency Stub Runner tương thích, artifact stub đã được cài ở Maven local repository và cổng 8085 khả dụng. Với kiểm thử song song, có thể dùng cổng động và lấy cổng từ Stub Runner. Pipeline dùng repository từ xa cần cấu hình `stubsMode` và kho artifact tương ứng.

Bài test consumer phải **đi qua HTTP client thật của Billing**, ví dụ một adapter thiết lập `Authorization: Bearer contract-reader-token` rồi parse `currency`/`balance`. Nếu test chỉ gọi stub server trực tiếp bằng một client khác, nó có thể bỏ sót lỗi code gắn header của Billing.

### 10.1. Stub Runner không thay thế bộ xác thực producer

Một stub HTTP thường dựa trên **WireMock request matching**. Nó có thể trả `200` vì request chứa đúng chuỗi `Authorization` được ghi trong mapping, nhưng:

- không kiểm tra chữ ký JWT thật;
- không tự xác minh token có hết hạn;
- không biết trạng thái tài khoản thật hay chính sách owner;
- có thể trả `404` của **stub server** khi request không khớp mapping, điều này **khác** với `404` nghiệp vụ của API.

Ví dụ consumer quên gửi `Authorization`: nếu chỉ có mapping `200` yêu cầu header, WireMock có thể không tìm thấy mapping và trả response mặc định của stub server. Không được tự hiểu rằng producer thật sẽ trả cùng status/body như vậy. Muốn kiểm tra lỗi `401`/`403` ở consumer, cần những mappings được thiết kế rõ ràng hoặc dùng test mô phỏng lỗi độc lập; đồng thời producer phải có kiểm thử bảo mật tương ứng.

### 10.2. Cách kiểm tra client có thực sự gửi token

Trong consumer test:

1. Cấu hình endpoint của Account Service trỏ đến Stub Runner.
2. Dùng một **test credentials provider** cấp `contract-reader-token`.
3. Gọi method thật như `accountClient.getAccount(42)`.
4. Xác minh body `200` được map vào model của Billing đúng.
5. Cấp token invalid/no scope trong những kịch bản có mappings tương ứng và kiểm tra cách Billing xử lý `401`/`403`.
6. Chạy thêm tình huống không gắn header nếu consumer phải chủ động xử lý thiếu credentials; kiểm tra chính xác response/mapping, không suy luận từ unmatched stub request.

Test này giúp phát hiện thay đổi ở phía consumer, chẳng hạn code đánh mất tiền tố `Bearer `, đổi tên header hoặc dùng một token không đúng môi trường.

## 11. Tránh làm rò rỉ dữ liệu xác thực trong hợp đồng và báo cáo CI

Contract DSL, artifact stub, generated tests và log CI thường được nhiều người hoặc hệ thống đọc. Vì vậy dữ liệu xác thực dùng trong ví dụ cần **không phải bí mật thật**.

| Nên làm | Tránh |
|---|---|
| Dùng token placeholder hoặc token chỉ hợp lệ trong môi trường test | Commit access token thật hoặc refresh token cá nhân |
| Dùng test signing key riêng, phạm vi cô lập | Tái sử dụng khóa ký production |
| Ghim version stub và kiểm soát repository truy cập | Publish artifact chứa credentials lên kho công khai |
| Mask header `Authorization` trong log/request dump | In nguyên token trong CI logs, stack trace hoặc báo cáo HTTP |
| Cấp quyền tối thiểu cho identity fixture | Cho mọi token test quyền admin để tất cả test xanh |
| Dọn dữ liệu có thể nhận diện cá nhân khỏi fixture | Dùng email/số tài khoản của khách hàng thật |

Việc ẩn token trong log **không đồng nghĩa** có thể bỏ header xác thực khỏi contract. Contract vẫn có thể mô tả `Authorization` và matcher thích hợp, còn test setup cung cấp giá trị an toàn.

Với OAuth2/OIDC, không nên mô phỏng một flow hoàn chỉnh bằng một chuỗi Bearer cố định rồi tuyên bố đã xác minh đăng nhập. Bước lấy token, refresh token, cookie/session, gateway và identity provider cần các bài tích hợp riêng nếu hệ thống phụ thuộc vào chúng.

## 12. Tích hợp kiểm thử xác thực vào CI

Một pipeline có thể tổ chức thành các bước:

```mermaid
flowchart TD
    A[Review contract HTTP có auth] --> B[Chuẩn bị test identities và dữ liệu tài nguyên]
    B --> C[Sinh producer contract tests]
    C --> D[Chạy producer tests qua security filter chain]
    D --> E{200/401/403 đúng hợp đồng?}
    E -- Không --> F[Sửa implementation, fixture hoặc hợp đồng đã thương lượng]
    F --> C
    E -- Có --> G[Chạy security integration tests]
    G --> H{Security tests đạt?}
    H -- Không --> F
    H -- Có --> I[Đóng gói và publish stub có phiên bản]
    I --> J[Consumer chạy test HTTP client qua Stub Runner]
    J --> K{Consumer xử lý đúng?}
    K -- Không --> L[Sửa client hoặc cập nhật hợp đồng qua review]
    L --> A
    K -- Có --> M[Cho phép tích hợp và phát hành]
```

Trong CI cần xác minh:

- **Build dùng phiên bản tương thích** của Spring Boot, Spring Cloud Contract, JDK và Maven/Gradle Wrapper.
- **Fixture được khởi tạo trước test** và có cùng ý nghĩa trên laptop/CI.
- **Generated producer tests được chạy thật**, không bị bỏ qua bằng `skipTests` hoặc rule exclude.
- **Security filters thực sự được bật** cho kịch bản xác thực.
- **Các security integration tests chuyên biệt** kiểm tra phần ngoài khả năng mô phỏng của contract.
- **Artifact stub gắn với build producer đã kiểm chứng**; consumer dùng đúng version.
- **Secrets và token thật không xuất hiện trong artifact hoặc log**.

Một bản stub `preview` được tạo khi producer chưa hoàn thành có thể giúp consumer phát triển sớm. Nhưng nó chưa có bằng chứng producer tuân thủ hợp đồng cho đến khi producer contract tests đạt; không sử dụng trạng thái preview như cổng phát hành chính thức.

## 13. Các lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Contract `200` trả `401` | Test token không được decoder/introspector nhận, chưa cài fixture, sai issuer/audience | Xem test auth configuration và request header thực |
| Contract `200` trả `403` | Thiếu scope/role, sai owner/tenant | Kiểm tra user fixture và resource fixture |
| Contract `200` vẫn đạt khi bỏ token | Security filter bị bypass hoặc test profile `permitAll` | Chạy test thiếu token, kiểm tra MockMvc setup và filter chain |
| `401` đáng lẽ là `403` | Fixture “thiếu quyền” thực tế là token invalid | Phân biệt bước authentication với authorization |
| Producer trả `200` nhưng body không khớp | Fixture tài khoản khác hoặc producer thay schema | So sánh JSON và dữ liệu seed với contract |
| Stub trả `404` khi consumer thiếu Authorization | Không có mapping khớp request; đây có thể là WireMock `404` | Kiểm tra mapping và request log trước khi kết luận API trả lỗi nghiệp vụ |
| Stub trả `200` cho token lạ | Matcher `Authorization` quá rộng | Xem mapping generated, thu hẹp matcher và kiểm tra auth thật ở producer |
| Consumer gửi token nhưng không đúng header | Client interceptor, credentials provider hoặc header bị ghi đè | Gọi qua client thật và kiểm tra header gửi ra |
| JWT fixture chạy được hôm qua, hôm nay bị `401` | Token hết hạn, clock lệch hoặc test key đổi | Dùng clock/test token issuance tái lập |
| CI thất bại còn local thành công | Thiếu test secret/issuer config, khác JDK/dependency, DB fixture khác | Đối chiếu config môi trường và log đã mask |
| Kiểm tra thành công nhưng token production bị lộ | Test sử dụng secret thật hoặc log HTTP đầy đủ | Thu hồi/đổi secret theo quy trình và sửa cách tạo fixture/logging |

Khi có lỗi, xem trước **request thực tế và context kiểm thử**, rồi mới sửa DSL. Nếu hợp đồng chính xác mà test đỏ vì producer chưa có quyền `accounts.read`, có thể producer đang vi phạm cam kết. Nếu test đỏ vì seed account 42 bị thiếu, cần sửa fixture. Hai trường hợp dẫn đến những hành động rất khác nhau.

## 14. Bài thực hành: Account Service và Billing

Bài tập có thể thực hiện trong hai ứng dụng Spring Boot hoặc một producer cùng một consumer test project. Cần Spring Cloud Contract plugin và Stub Runner phù hợp với phiên bản dự án, kèm Spring Security và môi trường test.

### Giai đoạn 1 — thiết kế và viết hợp đồng

1. Xác định API `GET /api/accounts/42`, các trường JSON mà Billing sử dụng và ba kịch bản `200`, `401`, `403`.
2. Chọn **Groovy hoặc YAML DSL** cho mỗi kịch bản. Đặt tên file/`name` khác nhau để truy vết.
3. Dùng `contract-reader-token` cho `200`, `contract-invalid-token` cho `401`, `contract-no-scope-token` cho `403`.
4. Tạo tài khoản 42 thuộc `user-42` với `currency=VND` và `balance=850000` trong test fixture.
5. Quy định rõ nghĩa của mỗi token qua test profile, hoặc tạo JWT test có thể xác minh bằng cơ chế thật.

### Giai đoạn 2 — xác minh producer

1. Cấu hình plugin sinh test từ contract, trỏ tới test base nạp Spring Security filters.
2. Cố ý cho endpoint trả `200` mà không kiểm tra token; chạy test thiếu token và quan sát vấn đề (nếu chưa có test thiếu token, bổ sung security integration test).
3. Bật luồng authentication/authorization theo chính sách, chạy lại các kịch bản `200`, `401`, `403`.
4. Cố ý bỏ scope `accounts.read` khỏi fixture reader; quan sát `200` contract test chuyển sang `403`, rồi khôi phục fixture.
5. Xác minh generated tests, response và stub mappings đều tương ứng với DSL.

### Giai đoạn 3 — xác minh consumer và CI

1. Đóng gói stub artifact từ bản producer đã đạt test.
2. Cho Stub Runner khởi chạy stub và cấu hình Billing HTTP client trỏ tới stub.
3. Kiểm tra Billing thực sự gắn `Authorization` khi gọi `getAccount(42)`; xác minh xử lý JSON `200`.
4. Thử token không hợp lệ và thiếu scope; xác minh Billing xử lý `401`/`403` theo hợp đồng mà không retry liên tục.
5. Kiểm tra riêng trường hợp thiếu header trên producer security tests.
6. Ghim phiên bản stub và bổ sung các bước producer contract tests, security tests, consumer tests vào CI.

**Tiêu chí hoàn thành:** producer test thật sự đi qua security filter chain; `200` chỉ đạt với fixture xác thực và quyền phù hợp; `401`/`403` được phân biệt rõ; consumer gửi đúng Bearer header và xử lý response qua Stub Runner; không có token hoặc khóa production trong mã nguồn.

## 15. Câu hỏi tự kiểm tra

1. **Contract có header `Authorization` đã chứng minh producer kiểm tra chữ ký JWT chưa?** Chưa. Phải bảo đảm generated test đi qua bộ xác thực thích hợp và có security integration tests cho chữ ký/expiry.
2. **Vì sao `contract-reader-token` có thể bị producer trả `401`?** Vì đây chỉ là chuỗi fixture; môi trường test phải chủ động chấp nhận nó hoặc dùng token được ký/kiểm tra đúng cơ chế.
3. **`401` và `403` khác nhau thế nào?** `401` thường chỉ request chưa xác thực hợp lệ; `403` thường là đã xác thực nhưng thiếu quyền.
4. **Nếu MockMvc test dùng `standaloneSetup` mà không có security filters, test `200` có bảo đảm auth hoạt động không?** Không.
5. **Vì sao Stub Runner có thể trả `404` khi consumer quên gắn Authorization?** Vì request không khớp mapping đã sinh; response đó có thể là mặc định của stub server, không phải `404` nghiệp vụ của producer.
6. **Có thể commit một Bearer token lấy từ production để test cho tiện không?** Không. Dùng dữ liệu kiểm thử an toàn, riêng biệt và có thể tái lập.
7. **Đã có scope `accounts.read` thì có chắc được đọc mọi account không?** Không. Cần kiểm tra owner/tenant hay chính sách phân quyền theo tài nguyên.
8. **Producer contract test xanh với test token verifier đã đủ kiểm tra identity provider thật chưa?** Chưa. Cần security integration/E2E tests cho những tích hợp đó.
9. **Vì sao cần ghim stub artifact version trong CI của consumer?** Để biết consumer kiểm thử với bộ hợp đồng nào và tránh khác biệt do tự chọn bản stub mới.
10. **Khi producer trả `401` thay vì `200`, nên sửa hợp đồng ngay không?** Không. Trước tiên kiểm tra header gửi thực tế, fixture, auth filter, decoder và cam kết đã được hai nhóm thống nhất.

## Kết luận

Để **xác minh yêu cầu HTTP có xác thực** bằng Spring Cloud Contract, nhóm cần biến kỳ vọng giữa producer và consumer thành **kịch bản có request, token fixture, quyền và dữ liệu nghiệp vụ xác định**. Groovy/YAML DSL có thể bảo vệ cách gửi `Authorization` và cách xử lý `200`, `401`, `403`; producer tests phải chạy qua security filters và Stub Runner giúp consumer kiểm thử độc lập. Kết hợp **fixture tái lập**, **security integration tests**, **stub version có thể truy vết** và **CI bắt buộc** sẽ giúp phát hiện sớm thay đổi API không tương thích mà vẫn giữ đúng giới hạn của kiểm thử hợp đồng.
