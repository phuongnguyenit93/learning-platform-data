# Deprecation và tiêu chí kết thúc hỗ trợ hợp đồng cũ

Trong kiến trúc microservices, một producer có thể muốn đổi API để giảm nợ kỹ thuật, sửa thiết kế dữ liệu hoặc phát hành phiên bản mới. Nhưng **producer ngừng cung cấp hành vi cũ không đồng nghĩa mọi consumer đã sẵn sàng**. Nếu Billing Service vẫn đọc trường `totalMinor` còn Order Service chỉ trả `amount.minor`, một bản triển khai producer có thể làm consumer hỏng dù producer v2 hoạt động hoàn hảo.

**Deprecation** giúp thông báo rằng hợp đồng cũ **không còn được khuyến nghị cho tích hợp mới** nhưng thường vẫn được phục vụ trong giai đoạn chuyển đổi. **Kết thúc hỗ trợ (end of support/end of life)** là quyết định vận hành có điều kiện: khi nào producer được phép thôi bảo đảm hành vi cũ, xóa mã cũ hoặc ngừng phát hành tài nguyên hỗ trợ? Câu trả lời phải dựa vào **chính sách đã công bố, bằng chứng consumer đã di chuyển, kiểm thử tương thích và khả năng rollback**, chứ không chỉ dựa vào cảm giác “đã quá hạn”.

Bài thuộc chương **Phiên bản và tương thích** của mô-đun **SPRING_CLOUD_CONTRACT**. Spring Cloud Contract cho phép định nghĩa hợp đồng HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh **producer verification tests**, phát hành **stub**, dùng **Stub Runner** trong consumer test và tích hợp CI nhằm phát hiện thay đổi API không tương thích. Trọng tâm bài này là cách quản trị **vòng đời hợp đồng cũ** trong chính quy trình đó.

## 1. Phân biệt bốn trạng thái của một hợp đồng

| Trạng thái | Producer còn phục vụ không? | Consumer nên làm gì? | Kiểm thử cần giữ |
| --- | --- | --- | --- |
| **Active** | Có, theo SLA/hợp đồng hiện hành. | Được dùng cho tích hợp mới. | Producer contract tests và consumer tests. |
| **Deprecated** | **Có**, trừ khi tài liệu tuyên bố khác; mức hỗ trợ phải công khai. | Không tạo tích hợp mới, bắt đầu di chuyển. | **Tiếp tục kiểm hợp đồng cũ** trong suốt thời gian còn cam kết. |
| **Sunset scheduled** | Có cho tới mốc đã công bố, nếu không thay đổi theo chính sách. | Hoàn thành migration, xác nhận môi trường triển khai. | Kiểm cả cũ và mới; theo dõi consumer còn sử dụng. |
| **Retired / unsupported** | Không còn cam kết phục vụ hợp đồng cũ. | Không còn phụ thuộc vào phiên bản đó. | Có thể bỏ test hỗ trợ cũ sau khi các điều kiện EOL được phê duyệt; giữ bằng chứng lịch sử. |

**Deprecated không phải là “đã bị xóa”.** Khi producer vẫn tuyên bố hỗ trợ v1, một PR làm v1 trả sai schema là **vi phạm hợp đồng** dù v2 đã xuất hiện. Ngược lại, “retired” không nhất thiết nghĩa là xóa mọi tài liệu hoặc JAR stub cũ khỏi repository: cần chính sách lưu trữ và khả năng tái lập sự cố lịch sử.

Các thuật ngữ thường gặp:

- **Deprecation announcement:** thông báo từ ngày nào phiên bản cũ không nên được sử dụng cho phát triển mới.
- **Migration window:** khoảng thời gian consumer được hỗ trợ để chuyển sang phiên bản mới.
- **Sunset date:** mốc dự kiến dịch vụ cũ thôi được cung cấp; có thể được dời theo chính sách/điều kiện.
- **End of support:** hết cam kết sửa lỗi, tương thích hoặc vận hành cho hợp đồng cũ theo chính sách.
- **Removal / retirement:** loại bỏ endpoint, message publisher, route hoặc khả năng giải mã liên quan sau khi hoàn tất thủ tục EOL.
- **Rollback window:** thời gian giữ khả năng phục hồi hợp đồng cũ nếu rollout retirement gặp sự cố.

Không phải tổ chức nào cũng định nghĩa các trạng thái giống nhau. **Tài liệu API/ADR của nhóm phải giải thích rõ** rằng một bản “deprecated” còn nhận security fixes, bug fixes và SLA như thế nào, và lúc nào hành vi cũ thực sự dừng.

## 2. Phiên bản API khác phiên bản artifact `stubs`

Một lỗi tư duy rất phổ biến: cho rằng JAR `order-service:2.0.0:stubs` chỉ chứa API v2, còn JAR `order-service:1.0.0:stubs` bảo đảm producer 2.0 vẫn phục vụ API v1. Hai loại version **khác ý nghĩa**.

| Loại version | Ví dụ | Câu hỏi nó trả lời |
| --- | --- | --- |
| **API contract version** | `/api/v1/orders/{id}`, `/api/v2/orders/{id}` | Consumer đang dùng giao tiếp/semantics nào? |
| **Producer artifact version** | `com.acme:order-service:2.0.0` | Bản build/release nào của Order Service được triển khai? |
| **Stub artifact version** | `com.acme:order-service:2.0.0:stubs` | Bộ mappings/contracts nào được phát hành cùng bản producer tương ứng? |
| **Consumer application version** | `billing-service:3.4.0` | Bản Billing nào đang chạy và nó đã migrate chưa? |
| **Message schema version** | `eventType=OrderCreated`, `schemaVersion=2` | Payload/headers message phải được giải mã theo schema nào? |

Producer release `2.0.0` **có thể vẫn hỗ trợ cả API v1 và API v2**. Nếu vậy, **stub artifact của release 2.0.0 cần biểu đạt những hợp đồng vẫn được producer cam kết phục vụ**, bao gồm legacy v1 ở mức phù hợp. Việc giữ lại `1.0.0-stubs.jar` trong Maven repository chỉ giúp kiểm/truy nguyên bản producer cũ; **nó không kiểm được implementation của producer 2.0.0** nếu v1 đã vô tình hỏng.

**Quy tắc:** version của artifact là **dấu vết build**; trạng thái active/deprecated/retired là **chính sách hỗ trợ giao tiếp**. Hai trục này có liên quan nhưng không hoán đổi cho nhau.

## 3. Ví dụ xuyên suốt: Order Service v1 và v2

Giả sử **Billing Service** đọc thông tin thanh toán đơn hàng từ **Order Service**.

**Hợp đồng HTTP v1 đang dùng:**

~~~http
GET /api/v1/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID","totalMinor":125000}
~~~

**Hợp đồng HTTP v2 muốn chuyển tới:**

~~~http
GET /api/v2/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "ORD-42",
  "state": "PAID",
  "amount": {
    "minor": 125000,
    "currency": "VND"
  }
}
~~~

Trong v2, nhà thiết kế quyết định:

- `id` dạng số được thay bằng `orderId` dạng chuỗi có ý nghĩa nghiệp vụ.
- `status` đổi tên thành `state`.
- `totalMinor` chuyển thành object `amount` có tiền tệ.
- Đường dẫn có version rõ ràng: `/api/v1/` và `/api/v2/`.

**Đây là thay đổi phá tương thích nếu áp lên response v1**, vì client cũ có thể không parse được. Nhưng thêm **endpoint v2 độc lập**, đồng thời giữ **v1 với semantics cũ**, là một chiến lược migration an toàn hơn.

### 3.1. Không có một cách versioning bắt buộc

Ví dụ dùng **URL path versioning** để dễ nhìn. Trong hệ thống khác, phiên bản có thể nằm trong media type, header, GraphQL schema hoặc một quy ước explicit khác. Điều quan trọng là consumer **xác định được giao tiếp nào đang dùng**, producer có thể phục vụ đồng thời khi cần, và bộ test bảo vệ đúng biến thể.

**Không tự giả định** đổi patch/minor của thư viện Java là cùng một thay đổi với version API. API có thể bị breaking change ngay trong một artifact có tên “minor” nếu quy trình quản trị yếu; ngược lại một major release ứng dụng có thể vẫn phục vụ hợp đồng cũ.

## 4. Chiến lược expand → migrate → contract

Thay đổi theo ba giai đoạn thường giúp giảm rủi ro:

~~~mermaid
flowchart TD
    A["Expand: thêm API v2, giữ v1 hoạt động"] --> B["Verify v1 + v2 trên producer hiện tại"]
    B --> C["Publish stub cùng release: mappings v1 + v2"]
    C --> D["Migrate: consumer triển khai client v2"]
    D --> E["Thu thập bằng chứng usage và xác nhận chủ sở hữu"]
    E --> F{"Điều kiện EOL v1 đạt?"}
    F -->|Chưa| G["Tiếp tục phục vụ v1, điều tra blocker"]
    G --> E
    F -->|Đạt| H["Contract: retirement qua rollout có kiểm soát"]
    H --> I["Theo dõi lỗi và sẵn sàng rollback"]
~~~

**Expand:** producer bổ sung giao diện mới **mà không phá giao diện cũ**. Hai hợp đồng v1/v2 cùng tồn tại và được kiểm trong release đang chạy.

**Migrate:** consumer cập nhật HTTP client, DTO, validation, error handling, feature flags và quy trình release. Producer theo dõi usage để tìm consumer chưa di chuyển.

**Contract:** chỉ sau khi qua **cổng EOL** đã thống nhất, producer mới bỏ endpoint/behavior cũ. Contract test cũ chỉ được bỏ khỏi build sau khi có quyết định ngừng hỗ trợ, không phải khi developer vừa viết xong endpoint v2.

Mô hình này không buộc mọi dự án phải duy trì **hai backend logic riêng**. Producer có thể dùng cùng application service ở bên trong và hai lớp mapping response v1/v2 để tránh lặp nghiệp vụ, miễn **mỗi giao tiếp được kiểm độc lập**.

## 5. Groovy DSL: giữ hợp đồng v1 trong release đã có v2

Trong repository producer đang hỗ trợ cả hai API, có thể đặt:

~~~text
src/test/resources/contracts/
└── orders/
    ├── get_paid_order_v1.groovy
    └── get_paid_order_v2.groovy
~~~

**Hợp đồng v1 vẫn phải hoạt động:**

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldKeepLegacyOrderV1'
    description 'API v1 vẫn trả schema đã cam kết trong giai đoạn deprecation'

    request {
        method 'GET'
        url '/api/v1/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            totalMinor: 125000
        )
    }
}
~~~

**Hợp đồng v2 được bổ sung:**

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnOrderV2'
    description 'API v2 trả orderId, state và amount có currency'

    request {
        method 'GET'
        url '/api/v2/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-42',
            state: 'PAID',
            amount: [
                minor: 125000,
                currency: 'VND'
            ]
        )
    }
}
~~~

Hai contract tạo **hai nhóm verification độc lập**. Một PR làm thay v1 response thành format v2 tại `/api/v1/orders/42` phải khiến **generated producer test v1 FAIL**. Đó là ý nghĩa thực tế của việc **đặt legacy contract ở lại build**.

**Không chuyển nội dung file `get_paid_order_v1.groovy` thành v2 mà vẫn giữ tên v1**. Nếu muốn chuyển, tạo v2 riêng, xác định consumer nào dùng v1 rồi chờ qua giai đoạn deprecation. Cũng không được xóa v1 khỏi đường quét của plugin khi producer vẫn cam kết phục vụ v1.

### 5.1. Hợp đồng cũ có thể cần nhiều hơn happy path

Producer cần giữ cả **các tình huống đã cam kết**, không chỉ một response 200 mẫu. Ví dụ:

| Trường hợp | Contract v1 nên còn kiểm? | Vì sao |
| --- | --- | --- |
| Order tồn tại, status PAID | **Có** | Happy path mà consumer dùng. |
| Order không tồn tại, trả 404 theo error schema cũ | **Có nếu đã cam kết** | Client cũ có thể parse error code/body. |
| Query/header bắt buộc | **Có nếu là phần hợp đồng** | Việc siết yêu cầu ngầm có thể phá client cũ. |
| Không có quyền, trả 401/403 | **Có nếu là hành vi được hỗ trợ** | Migration không được làm hỏng auth v1. |
| Pagination/sort/filter | **Có nếu v1 có quy ước** | Thay order hoặc mặc định sort có thể là breaking change. |
| Runtime throughput/SLA | Kiểm riêng theo chính sách | Contract status/body không thay thế performance tests. |

**Một generated test v1 pass không tự chứng minh mọi consumer v1 đều hoạt động.** Cần bộ hợp đồng bao phủ những hành vi quan trọng và xác nhận từ consumer tests đang được hỗ trợ.

## 6. YAML DSL: ví dụ tương đương, không nạp trùng

Nhóm chọn YAML có thể viết v1:

~~~yaml
description: API v1 còn được phục vụ trong migration window
request:
  method: GET
  url: /api/v1/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
    totalMinor: 125000
~~~

V2 ở một tệp riêng:

~~~yaml
description: API v2 với schema amount mới
request:
  method: GET
  url: /api/v2/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-42
    state: PAID
    amount:
      minor: 125000
      currency: VND
~~~

Đây là **hai hợp đồng khác nhau**, không phải hai cách viết trùng cùng endpoint. Tuy nhiên, nếu bạn cũng giữ hai file Groovy tương đương cho cùng v1/v2 trong đường dẫn được plugin nạp, có thể tạo test/mappings trùng. **Chọn một DSL làm nguồn có hiệu lực cho từng trường hợp**, giữ mapping version rõ ràng và kiểm generated tests.

## 7. Producer implementation: phục vụ song song mà không nhầm schema

Ví dụ controller Spring MVC tối giản:

~~~java
package com.acme.orders;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class OrderController {

    @GetMapping(
        value = "/v1/orders/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderV1 getOrderV1(@PathVariable long id) {
        if (id != 42L) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.NOT_FOUND);
        }
        return new OrderV1(42L, "PAID", 125000L);
    }

    @GetMapping(
        value = "/v2/orders/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderV2 getOrderV2(@PathVariable long id) {
        if (id != 42L) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.NOT_FOUND);
        }
        return new OrderV2(
            "ORD-42", "PAID", new Amount(125000L, "VND"));
    }

    public record OrderV1(long id, String status, long totalMinor) {}
    public record Amount(long minor, String currency) {}
    public record OrderV2(String orderId, String state, Amount amount) {}
}
~~~

Controller trên chỉ minh họa **hai dạng biểu diễn HTTP của cùng đơn hàng**. Implementation thực nên sử dụng một service/domain model chung rồi map sang hai DTO, thay vì nhân đôi logic. Dữ liệu ID 42 là fixture, không phải cách viết controller production.

Nếu một ngày developer đổi `getOrderV1` thành trả `OrderV2` vì muốn “xóa code thừa”, **v1 contract test phải thất bại**. Không được xóa test v1 để làm build xanh khi vẫn còn consumer phụ thuộc. Phải chuyển consumer và hoàn tất EOL trước.

### 7.1. Không dùng deprecation annotation làm bằng chứng đã di chuyển

Các annotation như `@Deprecated` trên Java method chỉ cảnh báo **người biên dịch/gọi mã Java**; chúng **không tự thông báo** cho consumer HTTP viết bằng ngôn ngữ khác, không tạo version API và không buộc consumer migrate.

Đánh dấu deprecated ở code là hữu ích cho đội producer, nhưng phải đi kèm **thông báo công khai cho đối tượng tiêu thụ, changelog, tài liệu và bằng chứng usage**.

## 8. Thông báo deprecation: rõ ai, cái gì và khi nào

Thông báo chất lượng tối thiểu nên trả lời:

1. **Hợp đồng nào** bị deprecate: method/path/header/media type/message destination/schema version cụ thể.
2. **Từ ngày nào** trạng thái deprecated có hiệu lực.
3. **Phiên bản thay thế** và sự khác biệt quan trọng về field, error schema, auth, semantics.
4. **Ngày sunset dự kiến** hoặc điều kiện để xác định ngày, có timezone rõ ràng.
5. **Đội nào chịu trách nhiệm**, kênh hỗ trợ và cách consumer báo blocker.
6. **Tài liệu migration** có code examples, contract/stub tương ứng, tests và hướng rollback.
7. **Phạm vi cam kết v1 trong migration window**: lỗi bảo mật, lỗi nghiêm trọng, bug fixes, SLA.
8. **Cách xác nhận consumer đã di chuyển**, kể cả các job chạy ít thường xuyên.

Ví dụ một lịch **giả định để học**, không phải thông báo của một dịch vụ đang tồn tại:

| Mốc | Ngày ví dụ | Diễn giải |
| --- | --- | --- |
| Publish v2 + giữ v1 | 2027-01-15 | Producer có hai contracts, consumer có thể chuyển thử. |
| Announce v1 deprecated | 2027-02-01 | Không nhận tích hợp v1 mới; công bố kế hoạch migration. |
| Review tiến độ từng consumer | 2027-04-01 | Đối chiếu deployment và thực tế request, xử lý blocker. |
| Sunset dự kiến | 2027-06-30 | **Chỉ áp dụng nếu EOL gates đã đạt và được duyệt**. |
| Theo dõi sau retirement | Sau khi đóng v1 | Giữ monitoring/rollback trong thời hạn theo quy định. |

**Ngày sunset là một cam kết truyền thông, không phải điều kiện kỹ thuật đủ để xóa code.** Nếu còn consumer quan trọng chưa migrate hoặc có sự cố chưa giải quyết, phải quản lý ngoại lệ/điều chỉnh kế hoạch rõ ràng, không xóa API chỉ vì lịch đã đến.

## 9. Tín hiệu HTTP và tài liệu API

Ngoài email/changelog/portal/ADR, producer có thể công bố **thời điểm sunset** bằng HTTP response header chuẩn nếu chính sách API áp dụng.

Ví dụ phản hồi v1 trong giai đoạn đã có lịch sunset:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Sunset: Wed, 30 Jun 2027 23:59:59 GMT

{"id":42,"status":"PAID","totalMinor":125000}
~~~

Header `Sunset` thể hiện **thời điểm dự kiến tài nguyên ngừng có sẵn** theo cách công bố của API; nó **không tự động tắt endpoint** và không thay thế tài liệu migration. Khi dùng thêm metadata deprecation/links, phải theo đúng cú pháp và chuẩn mà client/tooling đang hỗ trợ, không tự bịa header rồi kỳ vọng mọi consumer hiểu.

Nếu producer cam kết **header Sunset** như một phần của giao tiếp, có thể thêm assertion vào Groovy contract:

~~~groovy
response {
    status 200
    headers {
        contentType(applicationJson())
        header('Sunset', 'Wed, 30 Jun 2027 23:59:59 GMT')
    }
    body(id: 42, status: 'PAID', totalMinor: 125000)
}
~~~

**Lưu ý:** chỉ thêm vào contract **khi producer thực tế phát header đó** và giá trị dự kiến đã được policy phê duyệt. Header deprecation/sunset thường mang thông tin chính sách; nếu ngày thay đổi, cần cập nhật thông báo và contract một cách có kiểm soát, tránh test thất bại vì một giá trị đã lỗi thời.

Để consumer thực sự biết, hãy kết hợp tài liệu API (chẳng hạn OpenAPI description hoặc changelog), thông báo trực tiếp tới owners và monitoring deprecation headers. Không giả định mọi HTTP client tự đọc hay hiển thị header này cho người vận hành.

## 10. Tiêu chí EOL phải đo được, không chỉ “đã quá 90 ngày”

Một quyết định kết thúc hỗ trợ nên có **những điều kiện bắt buộc (gates) với bằng chứng**. Dưới đây là bộ tiêu chí thực dụng, cần được điều chỉnh theo hợp đồng dịch vụ và mức rủi ro của tổ chức:

| Gate | Câu hỏi kiểm | Bằng chứng phù hợp | Owner |
| --- | --- | --- | --- |
| **G1. Đã công bố chính sách** | Consumer được báo thời hạn và cách migrate chưa? | Changelog/announcement/ADR và xác nhận đã gửi. | API owner. |
| **G2. Có thay thế hoạt động** | V2 có feature parity cho use cases cần thiết chưa? | Producer verification + functional/security tests. | Producer team. |
| **G3. Danh sách consumer đầy đủ** | Biết ai dùng v1, ai sở hữu, phiên bản nào đang chạy? | Service catalog, access logs, tracing, registry, xác nhận owners. | Platform + consumers. |
| **G4. Migration đã triển khai** | Consumer quan trọng thực tế chạy v2 ở mọi môi trường được hỗ trợ? | Deployment evidence, release records, consumer stub tests. | Consumer owners. |
| **G5. Không còn traffic v1 ngoài ngoại lệ** | Có usage thực hay batch/offline jobs bị bỏ sót? | Metrics/logs theo khoảng quan sát phù hợp, đối chiếu job lịch định kỳ. | SRE/Platform. |
| **G6. Đã kiểm lỗi và tính tương thích** | V2 error handling, auth, timeout, business semantics đúng? | Contract tests, integration tests và migration validation. | Producer + consumers. |
| **G7. Có kế hoạch rollback** | Xóa/disable v1 gây lỗi thì phục hồi thế nào? | Playbook, feature flag/gateway route, canary, diễn tập. | Release/SRE. |
| **G8. Đã phê duyệt retirement** | Risk owner và bên liên quan đồng ý, không còn blocker? | Biên bản phê duyệt/EOL decision, lịch deploy, thông báo cuối. | API owner/change authority. |

**Không gate nào nên được đánh dấu PASS bằng giả định không có bằng chứng.** Một tập metric trong 24 giờ không chứng minh cron hàng tháng đã migrate. Một Stub Runner test xanh không chứng minh consumer v2 đã được deploy ở production. Một email thông báo không chứng minh client nhận được và có đủ thời gian sửa.

### 10.1. Tùy mức rủi ro, có thể cần thêm gate

- **Tuân thủ pháp lý hoặc hợp đồng khách hàng:** yêu cầu thời hạn thông báo tối thiểu, phương án gia hạn hoặc phê duyệt đối tác.
- **Phần mềm on-prem/offline:** khách hàng có thể không online để được đo traffic; cần chứng nhận phiên bản hỗ trợ và chính sách release.
- **Dữ liệu sự kiện giữ lâu:** cần đảm bảo mọi dữ liệu v1 còn lưu vẫn có thể được đọc/replay.
- **Ứng dụng mobile/embedded:** rollout lâu, tỷ lệ cập nhật thấp, không thể buộc mọi thiết bị update ngay.
- **Hệ thống đa vùng:** quan sát và deploy phải bao phủ các region/tenant, không chỉ khu vực nhận traffic nhiều nhất.

Những gate này giúp EOL là **quyết định kiểm soát rủi ro** chứ không đơn thuần là dọn code.

## 11. Làm thế nào biết consumer nào còn dùng v1?

Không có một tín hiệu duy nhất đủ trong mọi hệ thống. Kết hợp **khai báo phụ thuộc** và **quan sát thực tế**:

~~~mermaid
flowchart TD
    A["Inventory consumer + owner"] --> D["Bảng trạng thái migration"]
    B["Gateway/access logs theo version/path"] --> D
    C["Tracing, analytics, scheduled jobs, offline users"] --> D
    D --> E["Phỏng vấn/xác nhận owner và release evidence"]
    E --> F{"Còn consumer đang phụ thuộc v1?"}
    F -->|Có hoặc chưa biết| G["Giữ v1, mở blocker/ngoại lệ"]
    F -->|Không + đủ bằng chứng| H["Review EOL gates"]
~~~

Các nguồn thường hữu ích:

| Nguồn | Đo được điều gì | Giới hạn |
| --- | --- | --- |
| API gateway logs / route metrics | Request theo path/header/API version, tần suất và lỗi. | Có thể không gắn với owner, retention ngắn, traffic nội bộ bypass gateway. |
| Distributed tracing | Consumer service và tuyến gọi downstream. | Sampling có thể bỏ qua tác vụ hiếm. |
| Service catalog/ownership | Ai đăng ký phụ thuộc, môi trường và contact. | Có thể thiếu/không cập nhật nếu onboarding không đầy đủ. |
| Consumer CI contract tests | Bản code consumer có thể sử dụng contract v2. | **Không chứng minh code đã deploy**. |
| Deployment/release records | Phiên bản consumer nào chạy ở môi trường cụ thể. | Không tự chứng minh không còn binary cũ ngoài hệ thống. |
| Batch/scheduled jobs | Job chạy hằng tuần/tháng/quý còn dùng v1. | Giai đoạn quan sát phải đủ dài để bắt job hiếm. |
| External partner confirmations | Kênh tích hợp ngoài tổ chức đã chuyển chưa. | Có thể dựa vào self-report; cần điều khoản/cửa sổ hợp lý. |

**“Không thấy request v1” khác “không có consumer v1”.** Có thể client đã cài đặt nhưng chỉ chạy khi sự kiện hiếm xảy ra, hoặc lỗi mạng khiến không gọi được trong thời gian quan sát. Trước EOL phải biết **khoảng quan sát phù hợp với tần suất nghiệp vụ** và xử lý consumer không nhận diện được.

### 11.1. Ví dụ bảng theo dõi owner

| Consumer | Owner | Giao tiếp đang chạy | Test v2 | Deploy v2 | Usage v1 gần đây | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| Billing Service | Billing team | v2 ở staging, v1 ở production | PASS | Chưa | Có | **BLOCKER** |
| Analytics batch | Data team | v1 | Chưa có | Chưa | Không thấy trong 7 ngày | **BLOCKER**: batch chạy mỗi tháng. |
| Checkout Service | Checkout team | v2 | PASS | Có | Không | Có thể đạt sau đủ thời gian quan sát. |
| External partner X | Partner engineering | Chưa rõ | Không có thông tin | Chưa xác nhận | Lác đác | **BLOCKER**: cần xác nhận quyền/phiên bản. |

Đây là **dữ liệu minh họa**, không phải trạng thái của dịch vụ thật. Một bản ghi “Unknown” không nên tự chuyển thành “Done” chỉ vì không xuất hiện trong truy vấn log.

## 12. Consumer migration cần kiểm nhiều hơn DTO mới

Khi Billing chuyển sang `/api/v2/orders/{id}`, công việc thường bao gồm:

1. **URL/header/media type**: gửi request tới giao diện v2 đúng cách.
2. **DTO/schema**: đọc `orderId`, `state`, `amount.minor`, `amount.currency`.
3. **Business meaning**: tiền theo đơn vị nào, trạng thái có ý nghĩa như v1 không?
4. **Error responses**: xử lý 400/401/403/404/409/5xx theo quy ước v2.
5. **Auth/permissions**: token audience/scope và policy có thay đổi không?
6. **Timeout/retry/rate limits**: SLA, idempotency, error retry có khác không?
7. **Telemetry**: ghi rõ consumer đang gọi v1 hay v2 mà không log secrets/PII.
8. **Deployment**: rollout tới production, region, tenant, batch/worker liên quan.
9. **Fallback**: khi v2 chưa ổn, có thể revert có kiểm soát mà không làm dữ liệu sai?

Consumer chỉ đổi URL mà vẫn dùng DTO v1 có thể nhận response v2 **200 OK** nhưng không đọc được field, hoặc nhận giá trị mặc định như `null`/`0` khiến lỗi âm thầm. **Contract tests phải khẳng định cả nội dung và semantics quan trọng**, không chỉ status 200.

### 12.1. Consumer test với Stub Runner v2

Một ví dụ JUnit 5 minh họa:

~~~java
import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:2.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingUsesOrderV2Test {
    @Autowired
    private StubFinder stubFinder;

    @Test
    void readsNewOrderSchema() {
        URL baseUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderV2Client client = new OrderV2Client(
            baseUrl.toExternalForm()
        );
        OrderV2Client.OrderDto order = client.getOrder(42L);

        assertThat(order.orderId()).isEqualTo("ORD-42");
        assertThat(order.state()).isEqualTo("PAID");
        assertThat(order.amount().minor()).isEqualTo(125000L);
        assertThat(order.amount().currency()).isEqualTo("VND");
    }
}
~~~

Ví dụ giả định `OrderV2Client` là lớp thật của Billing, với `OrderDto` và `Amount` record phù hợp; source class và dependencies được consumer cung cấp. Với `LOCAL`, artifact `2.0.0:stubs` phải có trong Maven local. Trong CI khác máy, dùng `REMOTE` và repository/credentials tương ứng.

**Test này chứng minh:** Billing code có thể gọi và giải mã **mẫu HTTP v2 trong artifact**. **Test này chưa chứng minh:** Billing đã deploy phiên bản đó ở production hay producer release 2.0.0 còn phục vụ v1 đúng khi v1 vẫn được cam kết. Cần các bằng chứng riêng.

## 13. Kiểm cả legacy và new contract trong cùng producer release

Một trường hợp quan trọng: Order Service release `2.0.0` còn hỗ trợ **cả v1 và v2**. Sau producer verification, artifact:

~~~text
com.acme:order-service:2.0.0:stubs
~~~

nên có **mappings/contracts phù hợp cho cả hai giao tiếp còn được hỗ trợ**, nếu plugin được cấu hình quét cả hai. Consumer cũ có thể chạy test v1 với **stub artifact của producer release mới**, trong khi consumer mới chạy test v2 với cùng release.

Mục tiêu ma trận:

| Producer release | V1 contract | V2 contract | Vì sao |
| --- | --- | --- | --- |
| `order-service 1.0.0` | PASS | Chưa có | Đường cơ sở lịch sử. |
| `order-service 2.0.0` trong migration | **PASS** | **PASS** | Giữ consumer cũ và mở khả năng cho consumer mới. |
| `order-service 2.1.0` còn cam kết v1 | **PASS** | **PASS** | Nâng cấp producer không được phá legacy. |
| Release retirement đã được phê duyệt | Không còn cam kết v1 | PASS | Chỉ sau khi EOL gates đạt và thông báo có hiệu lực. |

**Đừng chỉ chạy consumer v1 với `1.0.0-stubs.jar`** khi producer production đã lên `2.1.0`: điều đó chỉ kiểm hợp đồng **quá khứ**, không bảo đảm release hiện tại vẫn tạo response v1 đúng. Lựa chọn kiểm là **stub của release producer thực tế**, hoặc tốt hơn là **generated producer tests trong chính release đó**.

## 14. Deprecation không đồng nghĩa “producer sửa response cũ cho đẹp”

Những thay đổi dễ bị đánh giá sai:

| Thay đổi ở v1 | Có thể phá consumer cũ không? | Hướng đúng |
| --- | --- | --- |
| Đổi `totalMinor` thành `amountMinor` ở response v1 | **Có** | Giữ field cũ hoặc thêm v2 riêng. |
| Đổi số `125000` thành chuỗi `"125000"` | **Có** | Bảo vệ kiểu JSON number và hợp đồng. |
| Bỏ trường `status` vì DTO mới dùng `state` | **Có** | Không xóa field v1 trong support window. |
| Đổi 404 error body/code | **Có** | Giữ quy tắc lỗi cũ hoặc version hóa. |
| Thêm trường optional nhưng consumer strict parser | **Có thể** | Kiểm consumer cũ và policy unknown fields. |
| Tối ưu repository/service mà HTTP không đổi | Thường **không** | Contract tests vẫn phải PASS. |
| Đổi thứ tự khóa JSON object | Thường **không**, nếu không có canonical requirement | Dùng JSON assertions theo semantics, không ép thứ tự khóa. |
| Đổi thứ tự phần tử JSON array đã cam kết sort | **Có** | Giữ ordering hoặc version semantics. |
| Đổi auth policy làm token cũ không được chấp nhận | **Có thể** | Thỏa thuận security transition, kiểm 401/403. |
| Thay 404 nghiệp vụ bằng no-match 404 WireMock | Test có thể **đạt giả** | Contract lỗi có error body và assert request mapping. |

**Tương thích không chỉ là schema parse được.** Nếu v1 vẫn trả `totalMinor=125000` nhưng đổi ý nghĩa từ minor units thành major units, JSON vẫn hợp lệ nhưng Billing có thể tính sai tiền. Hợp đồng và test phải bảo vệ những **ý nghĩa nghiệp vụ thiết yếu**.

## 15. Messaging deprecation phức tạp hơn HTTP

Với event-driven architecture, Order Service có thể phát `OrderCreated` theo schema v1 và v2. Có hai khái niệm cần phân biệt:

- **Ngừng phát event v1:** producer thôi xuất bản message mới theo schema v1.
- **Ngừng hỗ trợ đọc event v1:** consumer/deserializer không còn đọc được **message v1 đã lưu hoặc có thể được replay**.

Hai thời điểm này **có thể khác nhau rất xa** vì Kafka retention, queue backlog, dead-letter queue, outbox, audit log hoặc lưu trữ sự kiện lâu dài.

Ví dụ message v1:

~~~json
{
  "eventId": "evt-001",
  "orderId": "ORD-42",
  "amountMinor": 125000
}
~~~

V2:

~~~json
{
  "eventId": "evt-001",
  "orderId": "ORD-42",
  "amount": {
    "minor": 125000,
    "currency": "VND"
  }
}
~~~

Có thể dùng `schemaVersion`, event type mới, topic mới hoặc schema registry tùy giao thức đã thống nhất. **Không có một cơ chế versioning messaging duy nhất bắt buộc**; quan trọng là consumer biết cách phân biệt payload và có chiến lược tương thích/di chuyển.

### 15.1. Hợp đồng Groovy output message cho v1

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    description 'Sự kiện v1 còn được phát trong giai đoạn migration'

    input {
        triggeredBy('publishOrderCreatedV1()')
    }

    outputMessage {
        sentTo('orders.created.v1')
        headers {
            header('contentType', 'application/json')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amountMinor: 125000
        )
    }
}
~~~

### 15.2. Hợp đồng Groovy output message cho v2

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV2'
    description 'Sự kiện v2 với amount có currency'

    input {
        triggeredBy('publishOrderCreatedV2()')
    }

    outputMessage {
        sentTo('orders.created.v2')
        headers {
            header('contentType', 'application/json')
            header('schemaVersion', 2)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amount: [
                minor: 125000,
                currency: 'VND'
            ]
        )
    }
}
~~~

Hai contract minh họa **hai destination riêng** để dễ học. Trong thực tế, phiên bản có thể được phân biệt trên **cùng topic** bằng header/schema registry; khi đó cần đổi `sentTo`/headers và logic consumer tương ứng. `triggeredBy` là phương thức kích hoạt producer verification; để generated tests chạy, base test và messaging adapter phải được cấu hình theo phiên bản plugin.

**Stub Runner có thể dùng label để phát message mẫu**, nhưng nó không tự chứng minh transaction outbox, broker ordering, redelivery, retention hay khả năng replay. Để quyết định EOL sự kiện v1, phải kiểm cả **producer publishing**, **consumer decoding** và **dữ liệu tồn kho trên broker/storage**.

## 16. Tiêu chí EOL riêng cho message schema cũ

Ngoài G1–G8 ở mục 10, hợp đồng messaging thường cần:

| Gate messaging | Câu hỏi bắt buộc |
| --- | --- |
| **Publisher readiness** | Producer đã dừng phát v1 có kiểm soát, v2 đã được xác minh và consumer chấp nhận? |
| **Dual publish policy** | Nếu một giai đoạn gửi cả v1/v2, consumer có nguy cơ xử lý trùng nghiệp vụ không? Đã dùng event ID/idempotency phù hợp chưa? |
| **Consumer subscription** | Mọi consumer cần thiết đã chuyển topic/destination hoặc giải mã schema mới? |
| **Message backlog** | Queue/partition còn messages v1 chưa tiêu thụ không? |
| **DLQ / retry** | Dead-letter và retry topics còn message v1 có thể được phát lại không? |
| **Replay / audit** | Có yêu cầu khôi phục lịch sử v1 từ event store/archive lâu dài không? |
| **Schema registry** | Policy compatibility, schema ID/defaults/field presence có cho phép consumer mới đọc dữ liệu cũ? |
| **Observability** | Có metric phân theo schemaVersion/eventType và owner, không chỉ số message hiện tại? |

Một chiến lược có thể là **ngừng phát v1** nhưng giữ **consumer reader cho v1** trong thời gian dài để hỗ trợ replay. **Không xóa schema/decoder cũ** ngay khi producer chỉ phát v2, nếu dữ liệu cũ vẫn có thể được xử lý hợp lệ theo yêu cầu sản phẩm.

**Lưu ý backward/forward compatibility của schema** (đặc biệt Avro/Protobuf) phải được kiểm theo định nghĩa cụ thể của registry/serializer và chiều đọc dữ liệu. Một schema mới “hợp lệ” không tự bảo đảm mọi consumer cũ đọc được, và một consumer mới “đọc được v2” không tự bảo đảm nó có thể replay v1.

## 17. Quyết định 404, 410 hay route disabled sau retirement

Khi EOL v1 đã được phê duyệt, producer có thể:

- **Gỡ route** `/api/v1/orders/{id}` khiến request không tìm thấy (thường 404 trong cấu hình routing cụ thể).
- **Trả 410 Gone** theo thiết kế nếu muốn thông báo tài nguyên không còn và hạ tầng hỗ trợ quy ước đó.
- **Giữ gateway compatibility adapter** hoặc redirect có kiểm soát nếu hợp đồng/consumer cho phép.
- **Giữ v1 trong read-only mode** trong một giai đoạn ngoại lệ nếu chính sách có.

**Không có quy tắc rằng deprecation luôn phải trả 410.** Trong thời gian còn hỗ trợ, v1 vẫn phải đáp ứng hợp đồng cũ; nếu tự đổi từ 200 sang 410 trong migration window, đó là **breaking change** với consumer đang được cam kết hỗ trợ.

Sau retirement, nếu định nghĩa response 410 riêng, hãy có **test cho hành vi retirement được thiết kế**, tránh để 404 WireMock **do không khớp mapping** bị hiểu lầm là một contract 404/410 chính thức.

### 17.1. Rollout có kiểm soát hơn xóa code ngay

Một quá trình retirement an toàn thường tách:

1. Thông báo final cutoff và xác nhận cổng EOL.
2. Giới hạn hoặc vô hiệu v1 ở một nhóm nhỏ/đường route được kiểm soát khi hạ tầng cho phép.
3. Giám sát 4xx/5xx, customer incidents và traffic không nhận diện.
4. Có **rollback route/feature flag** hoặc kế hoạch khôi phục theo SLA.
5. Sau khi ổn định, mới dọn implementation/contract active và điều chỉnh tài liệu.
6. Lưu bằng chứng thay đổi, quyết định phê duyệt và artifact lịch sử.

Không biến một ngày sunset giả định thành một lệnh xóa code tự động nếu thiếu kiểm soát phát hành và bằng chứng migration.

## 18. Quy trình CI bảo vệ v1 trong thời gian deprecation

Trong thời gian hỗ trợ đồng thời, pipeline producer cần kiểm **cả v1 và v2**:

~~~mermaid
flowchart TD
    A["PR producer sửa Order API"] --> B["Contract Verifier sinh tests từ v1 + v2"]
    B --> C["Chạy generated producer tests"]
    C --> D{"Cả hợp đồng còn hỗ trợ đều PASS?"}
    D -->|Không| E["Chặn publish/deploy; điều tra regression"]
    D -->|Có| F["Đóng gói stub release hiện tại gồm v1 + v2"]
    F --> G["Publish artifact theo version"]
    G --> H["Consumer CI: legacy client + new client"]
    H --> I["Xác minh deployment + usage + migration gates"]
    I --> J{"EOL v1 đã được phê duyệt?"}
    J -->|Chưa| K["Tiếp tục bảo vệ v1 trên producer"]
    J -->|Có| L["Rollout retirement và giám sát/rollback"]
~~~

Gợi ý kiểm soát cụ thể:

1. **Contract Verifier** nạp các file v1/v2, sinh và chạy tests trên **producer implementation hiện tại**.
2. **Báo cáo test** chỉ rõ ít nhất các trường hợp quan trọng của **cả hai version** đã thực thi, không chỉ tổng số test > 0.
3. **Consumer Stub Runner tests** chạy cho các phiên bản consumer được hỗ trợ, ghim artifact version tương ứng.
4. **Compatibility checks** không chỉ dựa vào một happy path; bao gồm error schemas, auth, pagination và business semantics đã cam kết.
5. **EOL inventory** là dữ liệu riêng ngoài test: owners, deployments, usage, exceptions và phê duyệt.
6. **Pull request xóa v1** phải có tham chiếu đến quyết định EOL đã duyệt, không chỉ ghi “deprecated”.
7. **Release pipeline** ngăn publish nếu producer tests fail, nếu artifact stub không đúng hoặc retirement chưa được phê duyệt.
8. **Monitoring sau deploy** theo version và lỗi, có điều kiện rollback rõ.

Một thay đổi làm `/api/v1/orders/42` trả body v2 trong giai đoạn migration phải **FAIL producer verification**. Một thay đổi làm v2 lỗi nhưng v1 còn đúng cũng phải **FAIL** nếu v2 đã là hợp đồng được hỗ trợ.

## 19. Bảng quyết định ngừng hỗ trợ: ví dụ thực dụng

Giả sử hội đồng thay đổi xem xét dừng `GET /api/v1/orders/{id}`:

| Gate | Bằng chứng cần có | Ví dụ kết quả | Quyết định |
| --- | --- | --- | --- |
| Đã thông báo | Changelog + danh sách owner nhận thông báo | PASS | Có thể tiếp tục đánh giá. |
| V2 đáp ứng use cases | Test producer/consumer + auth/error reviews | PASS | Có thể tiếp tục đánh giá. |
| Billing đã deploy v2 | Release ghi nhận ở production | PASS | Có thể tiếp tục đánh giá. |
| Analytics batch đã migrate | CI pass nhưng batch tháng chưa triển khai | **FAIL** | **Không EOL v1**. |
| External clients | Một đối tác chưa phản hồi | **UNKNOWN** | **Không EOL**, cần xác minh/ngoại lệ. |
| Traffic v1 | Không thấy 7 ngày nhưng có job hàng tháng | **INSUFFICIENT** | Kéo dài quan sát. |
| Rollback | Đã có route toggle nhưng chưa diễn tập | **PENDING** | Hoàn thiện trước cutoff. |
| Quyết định cuối | Chưa đủ chứng cứ | **NOT APPROVED** | Giữ contract v1 và test v1. |

Trong bảng giả định này, **không được xóa v1** dù đã có ngày dự kiến. Một tiêu chí **FAIL** hoặc **UNKNOWN** quan trọng phải dẫn đến kéo dài hỗ trợ, kế hoạch khắc phục hoặc **ngoại lệ được phê duyệt rõ** chứ không bị tự động bỏ qua.

### 19.1. Checklist có thể gắn vào một PR retirement

~~~text
[ ] Contract v1, phạm vi endpoint/event và owners được ghi rõ
[ ] Deprecation announcement và migration guide đã phát hành
[ ] V2 producer verification và consumer tests đã đạt
[ ] Danh sách tất cả consumer và đối tác đã được kiểm tra
[ ] Các consumer critical đã deploy bản không dùng v1
[ ] Usage v1 được theo dõi đủ chu kỳ nghiệp vụ/retention
[ ] Batch/offline/replay/DLQ đã được đánh giá nếu có
[ ] Các ngoại lệ và quyền gia hạn đã được giải quyết
[ ] Đã chuẩn bị, diễn tập rollback/fallback khi phù hợp
[ ] SRE, API owner và change authority đã phê duyệt
[ ] Có kế hoạch cập nhật docs, SDKs, stubs và monitoring
[ ] Có bằng chứng/kết quả hậu triển khai để xác nhận EOL
~~~

Checklist là **công cụ ra quyết định**, không phải một bộ test tự động. Các ô chỉ được đánh dấu khi có **nguồn bằng chứng và người chịu trách nhiệm** tương ứng.

## 20. Quản lý artifact lịch sử và dữ liệu sau EOL

Một hiểu lầm khác: khi xóa v1 endpoint, phải xóa ngay mọi JAR stub cũ. Điều đó có thể gây khó khăn khi:

- Cần tái lập sự cố của một bản Billing cũ.
- Cần audit vì sao một consumer đã hoạt động trước migration.
- Một nhánh bảo trì được phép dùng một version cũ trong thời gian xác định.
- Cần xác định mapping/contract đã được publish ở một thời điểm lịch sử.

**Artifact retention policy** khác **API support policy**:

| Đối tượng | Sau EOL cần làm gì? |
| --- | --- |
| Mã route/handler v1 trên producer mới | Có thể xóa sau khi được phê duyệt, rollout và ổn định. |
| Generated producer test v1 trên nhánh phát triển mới | Chỉ bỏ khi release mới **không còn cam kết v1** và đã qua EOL. |
| Stub artifact phiên bản cũ | Có thể **giữ read-only** theo chính sách retention/audit. |
| Docs migration và changelog | Nên giữ mốc lịch sử, ghi rõ v1 đã retired. |
| SDK/client cũ | Đánh dấu unsupported, thông báo rõ lộ trình dừng cập nhật. |
| Metrics/alerts riêng cho v1 | Giữ đủ thời gian hậu rollout rồi dọn theo kế hoạch. |
| Message v1 còn được lưu | Tiếp tục hỗ trợ giải mã/replay nếu yêu cầu retention/audit còn hiệu lực. |

**Đừng dùng “artifact vẫn tải được” làm dấu hiệu API v1 đang được hỗ trợ**. Một JAR stub lịch sử có thể tồn tại để debug dù producer production không còn phục vụ endpoint đó. Ngược lại, producer còn route v1 không đủ để nói v1 được hỗ trợ nếu SLA/security policy đã chấm dứt; tài liệu phải nhất quán.

## 21. Các sai lầm thường gặp và cách khắc phục

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| “Đã deprecated nên xóa contract test v1.” | Producer v1 âm thầm hỏng trước EOL. | Giữ generated tests v1 tới khi hết hỗ trợ được phê duyệt. |
| “Đã có v2 nên mọi consumer chuyển rồi.” | Billing/partner/batch còn gọi v1. | Lập consumer inventory và xác nhận deployment/usage. |
| “Không có traffic v1 trong 24 giờ là đủ.” | Bỏ sót batch định kỳ, offline clients. | Quan sát đủ chu kỳ và xác nhận owner. |
| Chỉ chạy v1 consumer test với stub 1.0.0 cũ. | Không kiểm được producer release mới còn v1 đúng. | Giữ v1 trong generated tests của producer hiện tại và stub release hiện tại. |
| Chỉ kiểm status 200 của v2. | DTO/error/semantic sai vẫn lọt. | Assert schema, kiểu dữ liệu, lỗi và ý nghĩa nghiệp vụ. |
| Đổi header/path cũ và gọi là “refactor”. | Request của consumer cũ không còn match. | Giữ giao diện cũ; thêm v2 riêng cho thay đổi phá tương thích. |
| Coi HTTP `Sunset` tự tắt API. | Không có rollout/rollback, consumer không được cập nhật. | Coi nó là tín hiệu chính sách; EOL cần cổng riêng. |
| Đổi response v1 sang 410 ngay lúc announce. | Consumer cũ ngừng hoạt động lập tức. | Duy trì v1 trong migration window đã cam kết. |
| Xóa event v1 decoder ngay khi producer dừng publish. | Replay/queue/DLQ chứa v1 không thể xử lý. | Tính cả retention và dữ liệu lịch sử. |
| Dual publish v1/v2 không có idempotency. | Consumer nhận hai sự kiện cùng nghiệp vụ, xử lý trùng. | Quy ước event identity, dedup và migration tests. |
| Coi release artifact version là API version. | Stub 2.0 chỉ kiểm v2, không bảo vệ v1 còn hỗ trợ. | Quản lý hai trục version riêng. |
| Đổi error response nhưng test vẫn xanh. | Contract thiếu negative cases hoặc matcher quá rộng. | Bổ sung error contracts và consumer handling tests. |
| Xóa route v1 trong PR không có link quyết định EOL. | Không rõ ai chịu trách nhiệm và bằng chứng nào. | Yêu cầu phê duyệt, checklist và kế hoạch rollback. |
| Xóa tất cả stubs cũ ngay khi EOL. | Không tái lập được sự cố lịch sử. | Giữ artifacts theo retention policy, tách khỏi cam kết hỗ trợ. |
| Stub Runner test v2 xanh nghĩa là đã deploy v2. | Source code pass nhưng production còn binary cũ. | Kiểm deployment records, runtime telemetry và owner sign-off. |

**Khi gặp lỗi migration, lần theo chuỗi:** contract v1/v2 → generated producer tests → release artifacts → consumer Stub Runner tests → deployment/runtime usage → quyết định EOL. Chọn đúng tầng để khắc phục; không sửa hợp đồng để che lỗi triển khai.

## 22. Thực hành: deprecate v1 mà không phá Billing

Thực hiện trên Order Service (producer) và Billing Service (consumer) với hai API `/api/v1/orders/42` và `/api/v2/orders/42`.

1. **Tạo contract v1** bằng Groovy/YAML DSL trả `id`, `status`, `totalMinor`. Tạo controller v1 và generated producer tests.
2. **Chạy producer verification v1**, xác nhận test thật sự được sinh và thực thi. Cố tình đổi `totalMinor` sang `amountMinor` để chứng minh test FAIL, rồi hoàn nguyên.
3. **Bổ sung API và contract v2** trả `orderId`, `state` và `amount.{minor,currency}`. Giữ nguyên v1 ở release mới.
4. **Chạy Contract Verifier trên producer hỗ trợ cả v1/v2**, kiểm cả hai bộ test PASS, không chỉ kiểm số test tổng.
5. **Đóng gói và phát hành `stubs` của release mới** chứa các hợp đồng còn được hỗ trợ; kiểm nội dung JAR thực tế.
6. **Viết BillingV1Client** và BillingV2Client (hoặc adapter tách version), chạy mỗi client qua Stub Runner dùng artifact đã chọn. Kiểm path, JSON schema và error handling.
7. **Lập bảng consumer inventory** giả định gồm Billing, Analytics batch, Checkout và external partner; đánh dấu owner, production deployment, lần cuối thấy v1 và mức độ rủi ro.
8. **Viết một thông báo deprecation mẫu** ghi ngày, API cũ, thay thế, migration guide, hỗ trợ trong window và ngày sunset **giả định** có điều kiện.
9. **Mô phỏng Analytics chưa migrate:** dù v2 tests PASS, đánh dấu gate G4/G5 FAIL, kết luận **không được xóa v1**.
10. **Mô phỏng đủ bằng chứng:** tất cả owners xác nhận, deployment v2 hoàn tất, quan sát đủ chu kỳ job, rollback đã diễn tập và EOL approval có hiệu lực.
11. **Thực hiện retirement trong nhánh thử nghiệm** bằng route toggle/removal có kiểm soát; kiểm behavior retirement được thiết kế (404/410 nếu đó là policy), theo dõi hậu triển khai và rollback nếu cần.
12. **Bổ sung trường hợp messaging**: phát `OrderCreated` schema v1/v2; giả lập DLQ/replay còn dữ liệu v1 để giải thích vì sao decoder cũ có thể phải ở lại lâu hơn publisher v1.
13. **Kết nối CI:** trong migration window, mọi PR producer phải PASS v1/v2 tests; sau EOL đã phê duyệt mới bỏ v1 tests ở release tương lai, vẫn giữ artifact lịch sử theo retention.

**Tiêu chí đạt:** người học biết **vì sao deprecation không đồng nghĩa retirement**, viết được contract v1/v2 chạy song song, chứng minh producer không phá v1 trước EOL, phân biệt API version với artifact version, lập **tiêu chí EOL có bằng chứng** và giải thích được điều kiện rollback/retention sau khi đóng hợp đồng cũ.

## 23. Câu hỏi tự kiểm tra

1. Khác biệt giữa active, deprecated, sunset scheduled và retired là gì?
2. Tại sao không thể bỏ generated producer test v1 ngay khi công bố v2?
3. Tại sao `order-service:2.0.0:stubs` có thể cần chứa cả mappings v1 và v2?
4. Vì sao JAR stub 1.0.0 còn trong Maven repository không chứng minh producer 2.0.0 phục vụ v1 đúng?
5. Thay đổi `totalMinor` → `amount.minor` tại cùng endpoint v1 có thể phá consumer ra sao?
6. `@Deprecated` trên Java method có tự thông báo deprecation tới consumer HTTP không?
7. Header `Sunset` có tự vô hiệu hóa endpoint sau ngày công bố không?
8. Vì sao một mốc 90 ngày hoặc 7 ngày không thấy traffic chưa đủ để quyết định EOL?
9. Bạn cần những nguồn dữ liệu nào để lập inventory consumer và xác định ai chưa migrate?
10. Consumer test với Stub Runner pass nhưng production vẫn chạy client v1: EOL đã đủ điều kiện chưa?
11. Đâu là tám gate cơ bản trước khi kết thúc hỗ trợ hợp đồng cũ?
12. Nếu một consumer không xác định được owner hoặc một đối tác chưa xác nhận, nên ghi trạng thái gì và quyết định thế nào?
13. Sau EOL, producer có bắt buộc trả 410 Gone không?
14. Vì sao phải giữ rollback plan khi đã có đủ báo cáo migration?
15. Với messaging, tại sao có thể ngừng phát event v1 nhưng vẫn phải giữ decoder v1?
16. Dual publishing v1/v2 có thể gây lỗi duplicate processing như thế nào?
17. Backward/forward compatibility của serializer có thay thế kiểm ý nghĩa nghiệp vụ không?
18. Nên giữ hay xóa các stub artifacts lịch sử sau EOL, và vì sao?
19. Nếu v2 contract test pass nhưng v1 contract test fail trong migration window, pipeline producer nên làm gì?
20. Bằng chứng nào chứng minh consumer v2 đã **được deploy**, chứ không chỉ build/test thành công?

## 24. Mẫu quyết định EOL cho nhóm phát triển

Có thể dùng khung ngắn dưới đây khi tạo ticket/ADR ngừng hỗ trợ một hợp đồng:

| Trường | Nội dung cần điền |
| --- | --- |
| **Tên hợp đồng** | Method/path/API version hoặc event type/schema version/destination. |
| **Producer và owner** | Tên dịch vụ, nhóm chịu trách nhiệm, người phê duyệt. |
| **Phiên bản thay thế** | Đường dẫn/schema mới, link contract và migration guide. |
| **Ngày announce** | Ngày cụ thể, timezone và kênh thông báo. |
| **Sunset dự kiến** | Mốc thời gian theo chính sách, có điều kiện có thể lùi. |
| **Danh sách consumers** | Owners, deployments, criticality, trạng thái migration, ngoại lệ. |
| **Bằng chứng migration** | Consumer tests, release/deployment records, metrics, batch/offline confirmations. |
| **Bằng chứng compatibility** | Producer contract tests v1/v2 và CI reports. |
| **Rủi ro messaging** | Retention, replay, DLQ, schema registry, nếu áp dụng. |
| **Rollback và monitoring** | Toggle/route/rollback procedure, owner on-call, success/failure signals. |
| **Quyết định cuối** | GO/NO-GO, người duyệt, ngày phê duyệt, link bằng chứng. |
| **Retirement hậu kỳ** | Ngày dọn code/docs/SDK/metrics; chính sách giữ artifact lịch sử. |

**Kết luận:** **Một hợp đồng deprecated vẫn phải được kiểm và phục vụ đúng chừng nào producer còn cam kết hỗ trợ nó**. Spring Cloud Contract giúp bảo vệ hành vi v1 và v2 thông qua Groovy/YAML DSL, generated producer tests và Stub Runner consumer tests; nhưng **quyết định EOL cần thêm bằng chứng vận hành**, bao gồm owner của consumer, bản triển khai thực tế, mức sử dụng theo chu kỳ nghiệp vụ, dữ liệu messaging còn lưu, chính sách và khả năng rollback. Chỉ khi cổng EOL được thông qua mới nên ngừng cam kết và loại bỏ giao tiếp cũ trong release mới; các artifact lịch sử được xử lý theo chính sách lưu trữ riêng. Nhờ vậy, phiên bản mới có thể phát triển mà không vô tình phá vỡ những consumer vẫn đang được hỗ trợ.
