# Tính xác định của fixture và kiểm thử được sinh

## Mục tiêu học tập

Trong **Spring Cloud Contract**, producer và consumer cùng dựa vào **hợp đồng Groovy/YAML DSL** để thống nhất hành vi HTTP hoặc thông điệp. Từ hợp đồng, công cụ sinh **test phía producer**, tạo **stub** để consumer sử dụng bằng **Stub Runner**, rồi kết hợp với **CI** để phát hiện thay đổi API không tương thích.

Một bộ hợp đồng chỉ đáng tin nếu kết quả kiểm thử đủ **xác định** (*deterministic*): cùng phiên bản code, contract, fixture và điều kiện kiểm thử sẽ cho kết quả nhất quán. Nếu test đôi lúc xanh, đôi lúc đỏ vì đồng hồ, UUID, thứ tự phần tử, dữ liệu còn sót, broker hoặc cấu hình máy chạy, CI sẽ khó phân biệt **API thực sự thay đổi** với **nhiễu của môi trường**.

Bài thuộc chương **Chất lượng hợp đồng** và giúp bạn:

- Hiểu tính xác định ở **fixture**, **producer generated tests**, **stub mappings** và **consumer tests**.
- Thiết kế dữ liệu mẫu cố định, dễ đọc nhưng vẫn phản ánh những ràng buộc mà consumer cần.
- Dùng **giá trị cụ thể** ở nơi test producer phải gửi request, **matcher có chủ đích** ở nơi dữ liệu hợp lệ được phép thay đổi.
- Điều khiển đồng hồ, timezone, UUID, dữ liệu database, thứ tự phần tử, trạng thái stub và message delivery.
- Đọc generated test và mapping thực tế thay vì chỉ xem DSL nguồn.
- Phát hiện test xanh giả do matcher quá rộng, response mặc định 404 hoặc artifact stub sai phiên bản.
- Xây dựng quality gates CI, cách tái hiện flakiness và checklist review contract.

> **Nguyên tắc:** tính xác định không có nghĩa “mọi trường đều hardcode”. Nó có nghĩa **đầu vào, trạng thái và tiêu chí chấp nhận được kiểm soát**, còn các giá trị biến đổi hợp lệ được xác minh bằng matcher phù hợp.

## 1. Tính xác định là gì trong contract testing?

Xét một phép kiểm thử:

~~~text
Result = verify(
    producer_code,
    contract_DSL,
    fixture,
    runtime_configuration,
    dependency_versions,
    external_state
)
~~~

Một test đáng tin phải cho kết quả **tương đương về mặt hành vi** khi các thành phần trên không thay đổi. Điều đó **không đòi** cùng một byte log, thứ tự JSON object keys hay thời gian chạy giống nhau đến mili-giây.

Ví dụ:

- Producer trả một UUID mới mỗi lần là hành vi hợp lệ **nếu contract chỉ đòi UUID đúng định dạng**.
- Producer trả số lượng tồn kho khác nhau vì test khác vừa trừ tồn kho là **mất tính xác định** khi tình huống lẽ ra cần stock cố định.
- JSON object đổi thứ tự keys thường không làm thay đổi ý nghĩa JSON; một assertion so chuỗi byte có thể gây flakiness vô ích.
- JSON array đổi thứ tự phần tử **có thể là lỗi hợp đồng** nếu consumer dựa vào thứ tự; không được tự xóa kiểm tra thứ tự chỉ để test xanh.
- Một test message vượt timeout vì broker dùng chung hoặc consumer khác lấy mất event là dấu hiệu fixture/hạ tầng không được cô lập.

Có thể phân thành năm tầng:

| Tầng | Câu hỏi cần trả lời | Ví dụ cần kiểm soát |
|---|---|---|
| **Đầu vào** | Producer test gửi chính xác request nào? | Method, URL, body, headers, IDs |
| **Trạng thái** | Khi test chạy, producer có dữ liệu nền gì? | DB rows, mock returns, queue contents |
| **Thời gian và ngẫu nhiên** | Các nguồn giá trị biến thiên được xử lý thế nào? | `Clock`, UUID supplier, timezone |
| **Tiêu chí chấp nhận** | Test kiểm tra đúng bất biến giao diện nào? | Status, JSON type, regex, ordering |
| **Toolchain/artifact** | Test và stub được sinh từ phiên bản nào? | Plugin, JDK, contract commit, stub digest |

Tính xác định là **một tính chất của cả chuỗi**, không chỉ của một file fixture JSON.

## 2. Vì sao flakiness ở contract test đặc biệt nguy hiểm?

Trong Spring Cloud Contract có hai đầu kiểm chứng:

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Generated producer test"]
    A --> C["Generated stub mappings"]
    B --> D["Producer implementation"]
    D --> E{"Producer test PASS?"}
    E -->|Không| X["Không phát hành verified stub"]
    E -->|Có| F["Versioned :stubs artifact"]
    C --> F
    F --> G["Stub Runner"]
    G --> H["Consumer client/handler test"]
    H --> I{"Consumer PASS?"}
    I -->|Có| J["Compatibility evidence"]
    I -->|Không| K["Điều tra contract/client/mapping"]
~~~

Nếu producer test đỏ ngẫu nhiên, đội sẽ có xu hướng rerun đến khi xanh rồi bỏ qua báo cáo. Nếu consumer test xanh nhờ stub cũ hoặc matcher quá lỏng, CI có thể **không phát hiện breaking change**.

Một quality gate tốt phải phân biệt:

1. **Sai contract:** yêu cầu của consumer chưa được producer chấp nhận hoặc DSL mô tả sai.
2. **Sai implementation:** code producer không đáp ứng contract đã chốt.
3. **Sai fixture:** dữ liệu test không được chuẩn bị đúng hoặc không reset.
4. **Sai generated assertions:** DSL/matcher sinh ra điều kiện quá yếu hoặc quá chặt.
5. **Sai hạ tầng:** thời gian, broker, cổng, repository, concurrency, artifact version.

Không sửa bằng cách đơn giản đặt timeout rất lớn hoặc dùng `--rerun-tasks` đến khi có một lần PASS.

## 3. Tình huống xuyên suốt: Inventory phục vụ Checkout

Giả sử Inventory producer có endpoint:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Khi test bắt đầu với dữ liệu được chuẩn bị:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8,
  "checkedAt": "2026-01-15T10:00:00Z"
}
~~~

Checkout consumer sử dụng `sku`, `available`, `quantity` và hiển thị `checkedAt`.

Có ba loại kỳ vọng khác nhau:

- `sku` phải đúng **SKU-101** để biết response thuộc sản phẩm đã hỏi.
- `available` phải là **boolean** và `quantity` phải là **number**; giá trị `8` có thể cần cố định trong tình huống kiểm thử tồn kho cụ thể.
- `checkedAt` có thể là **thời điểm hiện tại hợp lệ** trong production; trong fixture, nên dùng thời điểm cố định hoặc matcher định dạng/thời gian phù hợp với trách nhiệm của API.

Nhóm không nên tạo fixture bằng cách lấy bất kỳ hàng nào trong database dev hoặc dùng `new Date()` ngay trong DSL.

### Một contract Groovy với fixture hoàn toàn cố định

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 co ton kho xac dinh'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8,
            checkedAt: '2026-01-15T10:00:00Z'
        )
    }
}
~~~

Đây là baseline dễ hiểu: generated test có thể kiểm tra phản hồi cố định, Stub Runner cung cấp body mẫu ổn định. Nhưng nó chỉ phù hợp nếu producer test setup **thực sự điều khiển được** `checkedAt` và stock. Nếu producer cố ý dùng clock hiện tại, yêu cầu equality với một instant cố định sẽ làm test fail ngoài ý muốn.

### YAML DSL tương đương

~~~yaml
description: 'SKU-101 co ton kho xac dinh'
request:
  method: GET
  url: /api/inventory/SKU-101
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    available: true
    quantity: 8
    checkedAt: '2026-01-15T10:00:00Z'
~~~

Chỉ chọn một trong hai tệp cho cùng tình huống thực tế nếu chúng có request matcher trùng nhau. **YAML nên quote timestamp** để không bị parser của môi trường khác tự chuyển kiểu dữ liệu.

## 4. Một fixture tốt cần đáp ứng những tiêu chí nào?

Fixture là dữ liệu đầu vào/trạng thái mẫu tạo điều kiện cho một tình huống test: stock snapshot, bản ghi database, JSON request, message payload, mock return hoặc file ngoài.

### Năm tiêu chí thiết kế

1. **Có danh tính rõ:** `SKU-101`, `customer-test-001`, `order-001` thay vì “row đầu tiên trong DB”.
2. **Đủ cho use case:** có field và quan hệ nghiệp vụ cần thiết, không nhồi toàn bộ schema.
3. **Có kết quả được dự đoán:** cùng setup cho cùng status/body/side effect.
4. **Không phụ thuộc test khác:** test chạy riêng hoặc đảo thứ tự vẫn PASS.
5. **Không chứa secrets/dữ liệu thật:** dùng dữ liệu nhân tạo, có thể phát hành trong stub JAR.

Một ví dụ fixture nhỏ:

~~~json
{
  "sku": "SKU-101",
  "stockOnHand": 10,
  "reserved": 2,
  "availableToSell": 8
}
~~~

Từ đó có bất biến nghiệp vụ:

~~~text
availableToSell = stockOnHand - reserved = 10 - 2 = 8
~~~

Một producer test có thể chuẩn bị service trả `8` trực tiếp, nhưng nếu mục tiêu là kiểm tra phép tính trong domain service thì cần **đưa service thật vào test và seed dữ liệu 10/2**, không mock luôn kết quả muốn xác nhận.

### Bảng cân bằng

| Cách tạo fixture | Điểm mạnh | Nguy cơ |
|---|---|---|
| Literal JSON/POJO cố định | Đọc được, tái hiện dễ | Có thể quá chặt cho field động |
| Test data builder có tham số rõ | Tái sử dụng, tên field có ý nghĩa | Default ẩn hoặc auto-random gây khó hiểu |
| Factory dùng seed xác định | Kiểm soát ngẫu nhiên có chủ đích | Vẫn phụ thuộc thứ tự gọi khi chia sẻ RNG |
| SQL seed/transaction test | Kiểm tra persistence thật | Cleanup, sequence, parallel test cần quản lý |
| Live dev/staging database | Có vẻ sát thực tế | Không cô lập, không tái hiện, dữ liệu nhạy cảm |
| `now()`/`randomUUID()` tại mỗi lần setup | Trông thực tế | Dễ làm test fail vì expectation cố định |
| Stub server stateful | Hỗ trợ kịch bản nhiều bước | Có thể phụ thuộc thứ tự test/request |

**Cố định dữ liệu không có nghĩa phải bỏ mọi trường hợp biên.** Tạo các fixture khác nhau cho hết hàng, không tìm thấy SKU, số lượng bằng 0, quyền truy cập và lỗi tạm thời, với **mỗi case có đầu vào được kiểm soát**.

## 5. Những nguồn không xác định thường xuất hiện

| Nguồn | Dấu hiệu | Biện pháp chính |
|---|---|---|
| Đồng hồ hệ thống | Test PASS trước nửa đêm, FAIL sau nửa đêm | Inject `Clock` hoặc dùng matcher thời gian |
| Timezone/locale | Timestamp và number format khác giữa máy | UTC/locale cố định trong test, contract ghi format |
| UUID/ngẫu nhiên | ID khác mỗi lần | Inject generator hoặc matcher đúng kiểu/format |
| Database dùng chung | Stock bị test khác thay đổi | DB riêng, rollback/cleanup/seed có thứ tự |
| Auto-increment/sequence | ID 1 trên máy dev, ID 42 trên CI | Không assert ID sequence nếu không là contract |
| Thứ tự collection không được định nghĩa | Array đổi order sau query/hash iteration | Sắp xếp ở producer hoặc assert order-independent nếu API cho phép |
| Messaging bất đồng bộ | Thời điểm nhận thay đổi | Correlation ID, isolated queue, bounded await |
| Mạng ngoài | Timeout, dữ liệu upstream thay đổi | Mock boundary/test container hoặc network test riêng |
| Random port | Consumer gọi sai port | Lấy cổng Stub Runner runtime |
| Version artifact mutable | Consumer chạy stub cũ | Pin version/commit/digest |
| Test chạy song song | State bị cross-contamination | Namespaces, resource locks, isolation |
| File encoding/newlines | Text/binary body khác | UTF-8, explicit encoding và canonical fixture |

Bảng này là danh sách điểm cần điều tra, không phải lời khuyên “mock tất cả”. Cần chọn **ranh giới** phù hợp với điều mà contract test thực sự có trách nhiệm chứng minh.

## 6. Giá trị cụ thể và matcher: khác biệt hai phía

Spring Cloud Contract có tính năng **dynamic properties** để cùng một contract tạo được:

- **Request matcher phù hợp cho stub** mà consumer gọi.
- **Request cụ thể** để generated producer test có thể gửi.
- **Response cụ thể** mà stub trả cho consumer.
- **Response matcher** để generated producer test chấp nhận dữ liệu động hợp lệ từ producer.

Tài liệu chính thức giải thích sự bất đối xứng này trong phần [How to Provide Dynamic Values](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-provide-dynamic-values.html).

| Phần giao tiếp | Tại producer generated test | Tại consumer Stub Runner |
|---|---|---|
| **Request** | Cần một giá trị **cụ thể** để gửi vào producer thật | Có thể dùng **matcher** để chấp nhận nhiều request hợp lệ |
| **Response** | Có thể dùng **matcher** để kiểm tra producer thật trả giá trị hợp lệ | Thường trả **giá trị mẫu cụ thể** cho consumer test |
| **Mục tiêu** | Chứng minh implementation đáp ứng contract | Chứng minh consumer xử lý giao diện đã mô tả |
| **Rủi ro nếu thiết kế sai** | Test flaky hoặc assertion quá lỏng | Stub không match request thực hoặc trả fixture không có ý nghĩa |

Điểm dễ nhầm là tên `consumer(...)` và `producer(...)`. Trong Groovy DSL, `consumer`/`client`/`stub` liên quan phía stub/consumer; `producer`/`server`/`test` liên quan phía producer verification. **Ý nghĩa còn phụ thuộc giá trị nằm trong request hay response**, nên hãy kiểm tra generated artifacts chứ không chỉ đoán từ tên hàm.

## 7. Ví dụ đúng: request động, test producer vẫn tái hiện được

Checkout gửi yêu cầu đặt giữ chỗ:

~~~http
POST /api/inventory/reservations HTTP/1.1
Content-Type: application/json

{
  "sku": "SKU-101",
  "quantity": 2,
  "clientRequestId": "c6f90433-e8a0-496b-a1b8-d47ff73e6421"
}
~~~

Trong production, `clientRequestId` thay đổi theo mỗi request. Nếu stub chỉ match **một UUID cố định**, nhiều consumer test hợp lệ sẽ nhận WireMock unmatched response.

Với Groovy DSL, có thể cho request body chứa **ví dụ cụ thể** nhưng gắn matcher ở phía request:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Dat giu cho voi clientRequestId UUID'

    request {
        method 'POST'
        url '/api/inventory/reservations'
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            quantity: 2,
            clientRequestId: 'c6f90433-e8a0-496b-a1b8-d47ff73e6421'
        )
        bodyMatchers {
            jsonPath('$.clientRequestId',
                byRegex('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'))
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'RSV-1001',
            sku: 'SKU-101',
            reservedQuantity: 2,
            status: 'ACTIVE'
        )
    }
}
~~~

**Kỳ vọng về đầu ra generator:**

- Producer test gửi đúng literal `clientRequestId=c6f90433-...` và seed fixture cho request ấy.
- Stub mapping có matcher cho `$.clientRequestId`, để consumer có thể dùng UUID khác cùng định dạng.
- `sku` và `quantity` vẫn bị giới hạn theo ví dụ, không chấp nhận bất kỳ SKU/số lượng tùy ý nếu contract chưa định nghĩa điều đó.
- Stub trả response mẫu `RSV-1001`, giúp consumer có dữ liệu xác định để assert.

`bodyMatchers` và `jsonPath(..., byRegex(...))` là cú pháp được mô tả trong [Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html).

**Lưu ý:** đây là một contract request mẫu duy nhất. Nó chưa chứng minh idempotency, concurrency hoặc tồn kho được trừ chính xác sau reservation. Các bảo đảm đó đòi contract cases và/or integration tests riêng.

## 8. Response có ID động: chọn kiểm tra đúng bất biến

Giả sử producer tạo reservation ID mới mỗi lần:

~~~json
{
  "reservationId": "RSV-4821",
  "sku": "SKU-101",
  "reservedQuantity": 2,
  "status": "ACTIVE"
}
~~~

Nếu DSL response hardcode `RSV-1001` với equality, generated test có thể fail dù producer vẫn đáp ứng giao diện “ID bắt đầu bằng RSV- và bốn chữ số”.

Có thể giữ một **response mẫu cụ thể** cho stub, nhưng dùng **response matcher** ở producer test:

~~~groovy
response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        reservationId: 'RSV-1001',
        sku: 'SKU-101',
        reservedQuantity: 2,
        status: 'ACTIVE'
    )
    bodyMatchers {
        jsonPath('$.reservationId', byRegex('RSV-[0-9]{4}'))
    }
}
~~~

Đoạn này là **phần response** của một `Contract.make` đầy đủ, không phải file DSL độc lập.

Khi sinh artifact:

- **Consumer stub response:** có thể cung cấp `RSV-1001`.
- **Producer generated test:** kiểm tra `reservationId` theo regex thay vì bắt đúng `RSV-1001`.
- Các field `sku`, `reservedQuantity` và `status` vẫn được so theo yêu cầu của DSL.
- Một producer trả `reservationId="oops"` sẽ không đạt matcher.
- Nếu ID thực tế phải là UUID thì phải dùng **UUID matcher/format** đã thống nhất, không lấy regex `RSV-...` làm luật chung.

**Đừng dùng `.*` cho mọi trường động.** Nó cho phép chuỗi rỗng và các giá trị sai format, tạo false positive. Chỉ nới chính xác trường có tính động và chỉ trong phạm vi hợp đồng cho phép.

## 9. YAML DSL: dynamic matcher không phải Groovy embedded

Trong YAML, phần khai báo `matchers` có thể mô tả các quy tắc tương đương mà không chèn lệnh Groovy vào body.

Ví dụ tương ứng với request ID động, response ID có quy tắc:

~~~yaml
description: 'Dat giu cho, ID duoc kiem tra theo dinh dang'
request:
  method: POST
  url: /api/inventory/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    quantity: 2
    clientRequestId: c6f90433-e8a0-496b-a1b8-d47ff73e6421
  matchers:
    body:
      - path: $.clientRequestId
        type: by_regex
        value: '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    sku: SKU-101
    reservedQuantity: 2
    status: ACTIVE
  matchers:
    body:
      - path: $.reservationId
        type: by_regex
        value: 'RSV-[0-9]{4}'
~~~

**Đây là một tệp thay thế Groovy, không dùng đồng thời với file Groovy có cùng request matcher.** Tên `by_regex` và cấu trúc `matchers.body` được mô tả trong [Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html) và [YAML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html).

Một số matcher/option thay đổi theo phiên bản Spring Cloud Contract. Kiểm tra schema tài liệu ứng với plugin version đã ghim và đọc các tests/mappings thực tế được sinh.

**Không nhầm YAML với JSON thuần:** các scalar như `true`, `8`, `null` và timestamp cần được khai báo/quote chính xác để parser giữ kiểu phù hợp.


## 10. Matcher: đủ linh hoạt nhưng không được “nuốt” lỗi

Tính xác định cần cả **độ ổn định** lẫn **khả năng phát hiện sai lệch**. Matcher quá chặt tạo test đỏ khi gặp dữ liệu biến động hợp lệ; matcher quá rộng tạo test xanh khi API đã sai.

| Dữ liệu | Matcher/kiểm tra nên cân nhắc | Cần tránh |
|---|---|---|
| HTTP status | Equality với `200`, `201`, `404`... theo case | “Bất kỳ status nào” |
| `sku` từ request | Equality với `SKU-101` | Regex `.*` nếu consumer cần đúng SKU |
| `quantity` | Giá trị cụ thể cho case hoặc number + bất biến | Chấp nhận cả string khi schema yêu cầu number |
| `reservationId` sinh mới | UUID/ID regex hoặc matcher theo type/format | So cứng một ID không kiểm soát được |
| `checkedAt` | ISO-8601 format + mốc/quan hệ thời gian nếu cần | So byte string tùy timezone |
| Danh sách có order theo API | Assert đúng order | Bỏ qua order dù là business requirement |
| Danh sách không có order guarantee | Assert tập phần tử và identity | Dựa vào thứ tự database trả ngẫu nhiên |
| Nullable field | Kiểm tra present/null theo contract | Cho phép missing và null nếu consumer phân biệt |
| Error body | Assert code + schema cụ thể | Chỉ assert 404 có thể là unmatched stub |
| Header bắt buộc | Assert tên/giá trị và semantics | Xóa header matcher để tránh failure |

### Khi nào dùng byType?

Ví dụ response `quantity` có thể biến đổi trong một nhóm test và consumer chỉ yêu cầu kiểu number:

~~~groovy
response {
    status 200
    body(
        sku: 'SKU-101',
        quantity: 8,
        available: true
    )
    bodyMatchers {
        jsonPath('$.quantity', byType())
        jsonPath('$.available', byType())
    }
}
~~~

`byType()` giúp tránh hardcode giá trị số/boolean nhưng **không chứng minh** quantity không âm, available phản ánh quantity hoặc rằng stock là `8` theo fixture. Nếu các ràng buộc ấy có ý nghĩa với consumer, cần matcher/command phù hợp hoặc integration tests bổ sung.

### Đọc matcher như một phát biểu về contract

- “`reservationId` có format `RSV-####`” là một ràng buộc giao diện có thể kiểm chứng.
- “`reservationId` là bất kỳ chuỗi nào, kể cả rỗng” có thể chưa đủ để consumer hủy reservation.
- “`quantity` có cùng kiểu number” không chứng minh số lượng còn hàng.
- “Tổng `availableToSell` bằng `stockOnHand - reserved`” là ràng buộc nghiệp vụ có thể cần kiểm thử tầng service/domain.

Không dùng matcher chỉ để làm test PASS; phải giải thích **consumer phụ thuộc vào điều gì và vì sao cho phép biến đổi**.

## 11. Đồng hồ: kiểm soát Instant thay vì đóng băng toàn JVM

Một nguyên nhân flaky phổ biến:

~~~java
Instant checkedAt = Instant.now();
~~~

Nếu response contract yêu cầu một timestamp cố định, producer test sẽ fail khi đồng hồ thật thay đổi. Cách tốt trong thiết kế Java là **inject `java.time.Clock`**.

### Code producer minh họa

~~~java
package com.example.inventory;

import java.time.Clock;
import java.time.Instant;

public class StockTimestampService {
    private final Clock clock;

    public StockTimestampService(Clock clock) {
        this.clock = clock;
    }

    public Instant currentCheckTime() {
        return Instant.now(clock);
    }
}
~~~

Ở production, cung cấp một bean `Clock.systemUTC()`:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ClockConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Trong test, cấp một `Clock.fixed`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Khi producer code dùng `Instant.now(fixedClock)`, output sẽ ổn định. Đối với Spring Boot integration test, có thể override bean `Clock` bằng `@TestConfiguration`/`@Primary` hoặc cơ chế test bean được phiên bản Spring Boot hỗ trợ.

**Ưu điểm:** không phải sửa clock toàn JVM, vốn dễ tác động tới test khác và đặc biệt nguy hiểm khi chạy song song.

### Khi nào không nên fake đồng hồ?

Nếu contract chỉ yêu cầu “trả thời điểm kiểm tra có định dạng hợp lệ”, có thể dùng matcher timestamp và kiểm tra invariants bằng test khác. Không bắt mọi API phản hồi một instant cố định trong production, vì điều đó sẽ làm contract thiếu thực tế.

**Quy tắc:** kiểm soát clock trong test khi mốc thời gian liên quan chính xác đến tình huống, hoặc dùng matcher có nghĩa khi thời gian tự nhiên biến động.

## 12. Timezone, locale và precision cũng là fixture

Các chuỗi sau có thể đại diện cùng một thời điểm:

~~~text
2026-01-15T10:00:00Z
2026-01-15T17:00:00+07:00
2026-01-15T10:00:00.000Z
~~~

Nếu hợp đồng yêu cầu **định dạng UTC cụ thể**, chúng không nhất thiết tương đương theo byte; nếu contract chỉ yêu cầu **cùng Instant**, nên so giá trị thời gian đã parse thay vì so chuỗi thô.

Một bảng kiểm tra:

| Thuộc tính | Cần quyết định |
|---|---|
| **Timezone** | UTC bắt buộc hay offset bất kỳ được phép? |
| **Định dạng** | ISO-8601 string hay epoch millis? |
| **Precision** | Giây, milliseconds, nanoseconds? |
| **Nullability** | Field bắt buộc, optional hay có thể null? |
| **Ý nghĩa** | Event time, processing time, reservation expiration? |
| **Tính đơn điệu** | `expiresAt > createdAt` có cần được kiểm tra không? |

**Không tự áp `TimeZone.setDefault(...)` cho toàn JVM** nếu có test song song và thư viện khác phụ thuộc timezone toàn cục. Ưu tiên inject clock, cấu hình object mapper và so sánh kiểu `Instant`/`OffsetDateTime` đúng contract.

### Ví dụ dễ gây lỗi do locale

Nếu service format quantity thành chuỗi:

~~~text
1,234  // một nghìn hai trăm ba theo một locale
1.234  // có thể cùng ý nghĩa ở locale khác
~~~

thì fixture/CI dùng locale khác có thể sinh output khác. Với API JSON, **ưu tiên number 1234** thay vì chuỗi số theo locale, trừ khi hợp đồng thực sự đòi chuỗi định dạng cho hiển thị.

Trong YAML, đặt timestamp string trong dấu quote để tránh kiểu tự động thay đổi bởi parser:

~~~yaml
checkedAt: '2026-01-15T10:00:00Z'
~~~

## 13. UUID, ID tự tăng và giá trị ngẫu nhiên

Các ID có hai vai trò khác nhau:

1. **ID là input có thể kiểm soát**: producer generated test cần gửi một literal cụ thể.
2. **ID là output được producer sinh**: response matcher cần xác nhận tính hợp lệ mà không cứng hóa một giá trị không có bảo đảm.

### Anti-pattern: tạo UUID ngay lúc DSL được load

~~~groovy
// Không nên dùng làm dữ liệu hợp đồng tái lập.
def generatedId = java.util.UUID.randomUUID().toString()
~~~

Nếu dòng tương tự được dùng để tạo request/body khi generator đọc DSL, hai lần generate có thể cho nội dung khác nhau. Điều này làm debug và so sánh artifacts khó hơn, còn tăng nguy cơ coupling giữa generated test và mapping.

**Cách tốt:** giữ request exemplar cố định trong DSL và dùng matcher ở phía request khi consumer hợp lệ được phép gửi UUID khác.

### Khi logic producer tự tạo ID

Có thể inject một generator interface vào service và cấp bản test cố định:

~~~java
import java.util.UUID;
import java.util.function.Supplier;

Supplier<UUID> fixedIds = () ->
    UUID.fromString("c6f90433-e8a0-496b-a1b8-d47ff73e6421");
~~~

Ở production dùng một supplier tạo UUID mới. Ở producer contract test dùng fixture/generator ổn định khi ID cụ thể là một phần cần xác minh; hoặc để generator thật hoạt động và dùng **response matcher UUID** nếu không có yêu cầu về một ID nhất định.

### Auto-increment từ database

Không nên assert `id=1` chỉ vì database mới khởi tạo thường bắt đầu từ 1. Chạy test khác, migration, sequence cache hoặc retry có thể làm ID thay đổi.

Nếu consumer chỉ cần ID hợp lệ và ổn định trong một luồng nghiệp vụ, assert **format, presence, không rỗng và quan hệ giữa các response**. Nếu ID cụ thể là một phần contract test, phải bảo đảm fixture/sequence thật sự kiểm soát được nó.

## 14. Dựng base test cho producer có fixture tái hiện được

Trong `MockMvc` mode, Spring Cloud Contract generated tests thường kế thừa một base class được cấu hình bằng `baseClassForTests` hoặc `baseClassMappings`.

Ví dụ producer giả định có các class ứng dụng `InventoryController`, `InventoryService` và `StockResponse` với constructor/method tương ứng.

~~~java
package com.example.inventory.contracts;

import com.example.inventory.InventoryController;
import com.example.inventory.InventoryService;
import com.example.inventory.StockResponse;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public abstract class InventoryContractBase {

    @BeforeEach
    protected void prepareFixture() {
        InventoryService service = mock(InventoryService.class);

        when(service.findBySku("SKU-101"))
            .thenReturn(
                new StockResponse(
                    "SKU-101",
                    true,
                    8,
                    "2026-01-15T10:00:00Z"
                )
            );

        RestAssuredMockMvc.standaloneSetup(
            new InventoryController(service)
        );
    }
}
~~~

### Đoạn code chứng minh được gì?

- Generated producer test có thể gọi **InventoryController thật**.
- Service dependency được mock để trả đúng fixture theo SKU.
- Cùng request nhận cùng body, không phụ thuộc database dev.
- JUnit 5 `@BeforeEach` dựng fixture mỗi test.
- Không có `Instant.now()` hoặc `randomUUID()` trong test setup.

**Đoạn này là skeleton**: các class `InventoryController`, `InventoryService` và `StockResponse` cần do dự án định nghĩa; constructor phải tương thích. Nếu REST controller dùng bean validation, security, global exception handlers hoặc serialization đặc biệt, `standaloneSetup` có thể chưa kiểm chứng toàn bộ web stack.

### Cảnh báo false positive do mock quá sâu

Nếu logic tính tồn kho nằm trong `InventoryService`, mock thẳng `service.findBySku` trả `8` không kiểm chứng công thức tồn kho thực. Cần phân biệt:

- **HTTP contract test:** xác nhận controller, status, JSON schema/field theo fixture và routing.
- **Service/domain test:** xác nhận công thức stock, reservation semantics, concurrency.
- **Full integration test:** xác nhận database, security, serialization và hành vi chạy qua HTTP thực.

**Test xác định nhưng kiểm chứng sai ranh giới vẫn là test kém chất lượng.**

## 15. Database fixture: seed, reset và isolation

Nếu producer contract test chạy với Spring Boot application context và database thật (có thể là Testcontainers), dữ liệu nền phải được kiểm soát.

### Nguyên tắc seed

Ví dụ bảng test:

~~~text
inventory_items
+---------+----------+----------+
| sku     | on_hand  | reserved |
+---------+----------+----------+
| SKU-101 |       10 |        2 |
| SKU-404 |   absent |   absent |
+---------+----------+----------+
~~~

Với `GET /api/inventory/SKU-101`, producer phải trả availableToSell `8`. Với `SKU-404`, cần hợp đồng riêng cho `404` và error code nghiệp vụ.

Các bước setup tốt:

1. Tạo schema từ migration chính thức hoặc test-specific schema có cùng cấu trúc.
2. Seed **đúng rows tối thiểu** cho tình huống.
3. Xóa/reset dữ liệu trạng thái trong phạm vi test **trước** khi chạy.
4. Tránh hardcode sequence ID nếu không thuộc contract.
5. Cô lập database/schema hoặc namespace của suite chạy song song.
6. Không dùng database dev/staging có dữ liệu thay đổi hoặc dữ liệu thật.

### Vì sao `@Transactional` chưa chắc đủ?

Với test gọi controller trong cùng transaction qua MockMvc, rollback có thể giúp cô lập một số thay đổi. Nhưng với `RANDOM_PORT`/HTTP test, request được xử lý trong transaction của server thread khác; transaction của test method **không tự rollback toàn bộ commit của server**.

Khi dùng HTTP thật, cần thiết kế cleanup/fixture ở đúng database/test environment: transaction management rõ ràng, truncate/reset giữa case hoặc container database riêng.

**Không bao giờ áp dụng cleanup phá dữ liệu cho môi trường production/staging dùng chung.**

### Khi test song song

Nếu hai tests cùng cập nhật `SKU-101`, có thể xuất hiện:

~~~text
Test A expects quantity 8
Test B reserves 3 units
Test A receives quantity 5
~~~

Đó là lỗi **test isolation**, không chứng minh Inventory API broken. Có thể:

- Dùng SKU riêng cho từng test.
- Dùng database/container riêng cho mỗi test suite.
- Reset transaction/state theo quy trình test.
- Tắt parallelism cho nhóm không thể cô lập, hoặc dùng resource lock.

Không làm cho contract “ổn định” bằng cách đổi matcher `quantity` thành bất kỳ number nào khi business case cần chính xác `8`.

## 16. Kiểm tra generated producer test, không chỉ nhìn DSL

Một sai lầm thường gặp là đọc contract nguồn rồi tự suy rằng generator đang kiểm tra tất cả điều mong muốn.

Bạn cần inspect **generated test Java**, report và số test thực thi.

### Checklist khi mở generated test

1. Nó được sinh từ đúng contract file/version chưa?
2. Có kế thừa đúng `InventoryContractBase` không?
3. Request method, path, headers, body được gửi **cụ thể** như mong đợi không?
4. Mã HTTP status được assert không?
5. JSON body field có bị chuyển type hoặc mất matcher không?
6. `reservationId` được assert bằng regex hay equality như đã thiết kế?
7. `quantity` được assert là number hay lỏng đến mức chấp nhận string?
8. Test có chạy qua controller/HTTP handler thật của producer không?
9. Test được thực thi bao nhiêu lần, có bị skip/filter không?
10. Có dữ liệu phụ thuộc đồng hồ, DB, random hoặc test khác không?

Vị trí generated source khác nhau theo Maven/Gradle/plugin version; các ví dụ thường gặp:

~~~text
Maven:
  target/generated-test-sources/contracts/...

Gradle:
  build/generated-test-sources/contractTest/...
~~~

Các đường dẫn trên là convention thường gặp, **không phải đường dẫn bảo đảm cho mọi phiên bản**. Hãy xem plugin configuration và build logs.

### Không sửa generated test trực tiếp

Nếu test được sinh có assertion sai, hãy sửa **DSL/matcher hoặc test base class**, rồi sinh lại. Sửa generated Java trong `target`/`build` sẽ bị mất ở lần chạy tiếp theo và che vấn đề nguồn.

### Test report cũng là một fixture chất lượng

Một CI job có `BUILD SUCCESS` nhưng chạy `0 generated producer tests` không phải một bằng chứng tốt. Cần kiểm tra **test count, skipped tests, failed tests** và artifact có đúng revision.

## 17. Kiểm tra stub mapping và response fixture đã sinh

Ở phía consumer, Stub Runner chạy stub artifact chứa WireMock HTTP mappings hoặc message definitions. **Mapping là kết quả chuyển DSL**, không phải bản sao chắc chắn 1:1 của file nguồn.

Những điều cần kiểm tra:

- Request matcher là method/URL/header/body nào?
- Các dynamic fields có được chuyển thành regex/bodyPatterns như dự định không?
- Có mapping nào trùng request và trả response khác không?
- Default 404 của WireMock có đang bị nhầm với một contract 404 nghiệp vụ không?
- Response body là JSON object đúng kiểu hay chuỗi JSON bị escape?
- Có file `__files` được tham chiếu bởi `bodyFileName` không?
- Stub JAR có classifier/version đúng không?
- Fixture dùng trong stub có còn ổn định sau hai lần generate không?

### Minh họa mapping, không phải output nguyên văn bắt buộc

Một WireMock mapping đơn giản có thể trông như:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": {
        "contains": "application/json"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-101",
      "available": true,
      "quantity": 8,
      "checkedAt": "2026-01-15T10:00:00Z"
    }
  }
}
~~~

Đây là **mapping tự viết minh họa tương đương hành vi**, không khẳng định plugin sinh ra chính xác format/ordering đó. Kiểm tra artifact thực để biết WireMock matcher/response mà Stub Runner sẽ sử dụng.

### Phân biệt 404 do matcher không khớp và 404 nghiệp vụ

Nếu consumer gửi:

~~~http
GET /api/inventory/SKU-102
~~~

nhưng chỉ có mapping cho `SKU-101`, WireMock có thể trả mặc định `404`. Điều đó **không chứng minh** producer đã triển khai hợp đồng lỗi `SKU_NOT_FOUND`.

Một contract 404 có ý nghĩa nên có error body cụ thể, ví dụ:

~~~json
{
  "code": "SKU_NOT_FOUND",
  "message": "Product does not exist"
}
~~~

Consumer test cần assert `code` và request match, không chỉ status. Nếu không, một URL typo cũng có thể làm test “pass”.


## 18. Messaging fixture: payload đúng vẫn có thể test flaky

Với Spring Cloud Contract **message contracts**, producer có thể phát thông điệp qua Kafka, RabbitMQ hoặc một messaging abstraction được cấu hình. Generated tests cần kích hoạt producer publisher, quan sát message và assert destination, headers, payload.

Một Groovy DSL minh họa:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('publishStockChanged()')
    }

    outputMessage {
        sentTo('inventory-events')
        headers {
            messagingContentType(applicationJson())
        }
        body(
            eventType: 'StockChanged',
            eventId: 'evt-stock-101',
            sku: 'SKU-101',
            quantity: 8,
            occurredAt: '2026-01-15T10:00:00Z'
        )
    }
}
~~~

Giả định base class producer cung cấp method `publishStockChanged()` và môi trường messaging test phù hợp. Đây là contract minh họa một sự kiện có payload cố định. Nếu producer thực sinh `eventId`/`occurredAt`, dùng dependency inject hoặc matcher có nghĩa thay vì bắt code thật luôn phát `evt-stock-101` ở runtime.

### Tại sao test message dễ không xác định?

| Nguồn biến động | Biểu hiện | Cách khắc phục |
|---|---|---|
| Queue/topic còn message cũ | Test nhận nhầm event trước đó | Isolated destination/consumer group, drain/reset có kiểm soát |
| Nhiều test dùng chung consumer group | Event bị test khác nhận mất | Namespace và nhóm nhận riêng |
| Event đến bất đồng bộ | Test assert trước khi listener xử lý | Await có timeout hữu hạn |
| Không gắn correlation ID | Test match nhầm event của request khác | Correlate bằng `eventId`/`sku` hoặc business key |
| Producer publish không đồng bộ sau commit | Test chạy trước commit | Đồng bộ điều kiện readiness và transactional semantics |
| Offset/ack thay đổi | Test chạy qua một lần, fail lần khác | Seed/reset offsets, broker/test binder rõ ràng |
| Clock/UUID trong event | Payload khác giữa runs | Inject fixed clock/ID generator hoặc matcher |
| Schema serialization khác | JSON fields/headers thay đổi | Kiểm tra converter, Content-Type và contract |

### Một assertion bất đồng bộ có deadline

Nếu consumer nhận event rồi cập nhật một projection, không được assert projection ngay trong cùng tick nếu handler bất đồng bộ. Với Awaitility trong test (giả định dependency đã thêm):

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

await()
    .atMost(10, SECONDS)
    .untilAsserted(() -> {
        var projection = projectionRepository.findBySku("SKU-101");
        org.assertj.core.api.Assertions.assertThat(projection.quantity())
            .isEqualTo(8);
    });
~~~

Đoạn này chỉ là **minh họa assertion**; trước nó phải khởi động đúng consumer, trigger/publish message, chuẩn bị projection repository và cô lập dữ liệu. Timeout `10s` là một lựa chọn ví dụ, cần chọn theo SLO của môi trường test.

**Không dùng `Thread.sleep(10000)` làm điều kiện sẵn sàng.** Sleep cố định vừa làm chậm test vừa không bảo đảm message đã xử lý.

### StubTrigger không phải producer verification

Khi consumer dùng Stub Runner `StubTrigger` để phát event theo label, consumer test đang kiểm tra **handler của consumer với message mô phỏng**. Producer contract test vẫn cần kiểm chứng publisher thực phát message đúng. Một bên PASS không thay thế bên kia.

## 19. Test order và trạng thái được chia sẻ

Một test có thể ổn định khi chạy riêng nhưng fail khi chạy cả suite:

~~~text
Test A: GET stock SKU-101 -> expects quantity 8
Test B: POST reservation SKU-101 quantity 3
Test A after B: GET stock -> actual quantity 5
~~~

Nếu test A và B cùng dùng database, queue hoặc WireMock scenario state mà không reset, test suite đã có **phụ thuộc thứ tự**.

### Ba chiến lược cô lập

**Chiến lược 1 — Test-specific identity.** Cho mỗi test một SKU/order ID khác nhau (được cấp rõ ràng, có thể định danh theo test case). Thích hợp cho song song, nhưng cần giới hạn/cleanup dữ liệu.

**Chiến lược 2 — Test-specific environment.** Mỗi suite có database schema/container, broker namespace hoặc Stub Runner instance riêng. Cách này cô lập tốt hơn nhưng tốn tài nguyên.

**Chiến lược 3 — Reset state có kiểm soát.** Trước mỗi test dọn và seed dữ liệu/mapping/offset về baseline, nếu công nghệ test hỗ trợ. Phải tránh reset làm ảnh hưởng test khác đang chạy.

Không “giải quyết” test-order bug bằng cách cho mọi matcher chấp nhận nhiều quantity khác nhau. Nếu contract yêu cầu chính xác `8` cho fixture A, cần giữ kiểm tra ấy.

### Đảo thứ tự để phát hiện coupling

Có thể chạy cùng một suite:

- Chạy test riêng từng case.
- Chạy cả suite với thứ tự khác.
- Chạy một lần tuần tự và một lần song song (nếu policy cho phép).
- Lặp lại nhiều lần ở môi trường sạch.
- Ghi seed/test IDs khi một lần fail để tái hiện.

Tính xác định **không** đòi mỗi test chạy sau một test khác để “làm nóng” cache hoặc tạo dữ liệu. Nếu có dependency nghiệp vụ nhiều bước, hãy biến chúng thành **một scenario rõ ràng** thay vì hai test độc lập phụ thuộc vào thứ tự.

## 20. Stateful stub scenarios và reset WireMock

WireMock hỗ trợ các kịch bản stateful. Ví dụ consumer muốn gọi reservation lần đầu nhận `201`, lần sau nhận `409` hoặc kiểm tra một retry sequence.

Khi dùng stateful mapping:

1. Khai báo **trạng thái ban đầu** và transitions rõ.
2. Đặt các bước thuộc **cùng một scenario test**, không phân tán qua các tests không có thứ tự.
3. Reset scenario state trước mỗi lần chạy scenario.
4. Không cho hai suites thao tác chung một WireMock server stateful nếu không có isolation.
5. Kiểm tra matched request journal để biết request nào chuyển state.
6. Phân biệt retry logic thật và response giả lập cố tình thay đổi theo số lần gọi.

Một kịch bản trạng thái là hợp lệ nếu **cùng trình tự request có cùng chuỗi response**. Nó không xác định nếu kết quả phụ thuộc số request từ một test hoàn toàn khác.

### Phân biệt “stub fixture” với hệ thống state thật

Nếu producer thực có transaction, race condition và reservation expiration, WireMock stateful scenario chỉ mô phỏng một số quan sát. Nó **không chứng minh** database producer có transaction correctness. Cần producer/integration tests riêng cho bảo đảm ấy.

## 21. JSON object, array và bản chất thứ tự

JSON object không có ngữ nghĩa thứ tự key theo hợp đồng, trong khi JSON array thường có thứ tự được consumer quan sát. Đây là khác biệt quan trọng khi kiểm tra determinism.

### JSON object: không nên so chuỗi thô

Hai object dưới đây tương đương về key/value:

~~~json
{"sku":"SKU-101","quantity":8,"available":true}
~~~

~~~json
{"available":true,"quantity":8,"sku":"SKU-101"}
~~~

Nếu test so chuỗi JSON byte-for-byte, nó có thể fail khi serializer đổi thứ tự key. Hãy ưu tiên JSONPath/matcher kiểm tra **key, type và value**. Nếu thứ tự key là yêu cầu đặc thù của một giao thức ký chữ ký số, phải có canonicalization được thiết kế riêng, không dựa vào hành vi ngẫu nhiên của Map.

### JSON array: phải quyết định có contract order không

Ví dụ API danh sách kho:

~~~json
[
  {"warehouse":"HN","quantity":5},
  {"warehouse":"HCM","quantity":3}
]
~~~

Nếu hợp đồng nói “sắp xếp theo warehouse ID”, producer phải có `ORDER BY`/sorting rõ ràng. Nếu API nói “không bảo đảm thứ tự”, consumer nên assert theo **tập identity/value**, không dựa vào việc bản ghi HN luôn đứng trước HCM.

**Không tự bỏ kiểm tra thứ tự khi UI/consumer thực sự cần ưu tiên kho gần nhất.** Khi thứ tự là contract, phải kiểm tra đúng thuật toán hoặc giá trị sort được hứa.

### Collection size cũng có nghĩa

Đối với một API trả về danh sách, `byType()` không nhất thiết bảo vệ kích thước tập hợp. Nếu consumer yêu cầu “exactly two options”, cần assert length/occurrence rõ, không chỉ kiểm tra mỗi phần tử có đúng schema.

## 22. Nội dung text, XML, binary và file fixture ngoài

Không phải mọi contract đều là JSON. Với XML, multipart hoặc file binary, tính xác định còn phụ thuộc encoding và đường dẫn fixture.

### Text/XML

- Chọn encoding rõ ràng (thường UTF-8).
- Tránh CRLF/LF không được chuẩn hóa làm thay đổi signature/hash.
- Dùng XPath/XML matcher khi thứ tự attribute không mang nghĩa.
- Kiểm tra XML namespace và sự tồn tại của element quan trọng.
- Không xóa phần kiểm tra header `Content-Type` nếu consumer dựa vào loại nội dung.

### File fixture

Cấu trúc stub HTTP có thể chứa:

~~~text
mappings/
  stock-found.json
__files/
  stock-found-body.json
  sample-invoice.pdf
~~~

Trong Spring Cloud Contract stub JAR, đường dẫn thực có thể nằm dưới `META-INF/...`. Khi build/giải nén sang WireMock filesystem, giữ đúng relative path cho `bodyFileName`.

Kiểm tra:

1. File có được đóng gói vào artifact không?
2. Path và case-sensitivity đúng trên Linux CI không?
3. Encoding và newline có được kiểm soát không?
4. Không đọc file từ home directory cá nhân của developer.
5. File binary có checksum phù hợp không?
6. Stub mapping có tham chiếu path thực sự tồn tại không?

**Không sử dụng fixture chứa dữ liệu cá nhân thật hoặc secret** để đổi lấy “tính sát thực tế”. Dữ liệu tổng hợp có giá trị như nhau cho contract test nếu giữ đúng schema và ràng buộc cần thiết.

## 23. Header và network behavior có thể tạo flakiness

Một số header không nên hardcode vô lý:

| Header | Có cần assert cụ thể? | Cách tiếp cận |
|---|---|---|
| `Content-Type` | Thường **có** | Kiểm tra media type + charset khi contract yêu cầu |
| `Location` cho `201` | Tùy API, nhiều khi **có** | Kiểm tra path/ID quan trọng, không cứng hóa host random |
| `Date` | Phụ thuộc consumer | Matcher date hoặc kiểm soát clock |
| `X-Request-ID` | Có thể động | Regex UUID/nonblank và correlation |
| `Authorization` request | Thường yêu cầu scheme/permission | Test token fixture, không dùng secret thật |
| `Retry-After` | Có ý nghĩa với retry logic | Kiểm tra định dạng/giá trị đã thống nhất |
| `Transfer-Encoding` | Thường do HTTP stack xử lý | Không assert nếu không thuộc contract |
| `Server` | Phụ thuộc proxy/runtime | Thường không đưa vào contract |

Nếu test mode là MockMvc, một số đặc tính HTTP proxy/server thật không được mô phỏng. Nếu cần kiểm tra status, routing và JSON qua nhiều filter/security, cân nhắc WebApplicationContext hoặc HTTP server test. Đừng biến điều kiện mạng của production thành fixture bắt buộc nếu contract không yêu cầu.

### Cổng ngẫu nhiên của Stub Runner

Với `@AutoConfigureStubRunner(ids="...:stubs:0")`, `0` yêu cầu cổng động; không có nghĩa consumer gọi `http://localhost:0`.

Trong test Spring:

~~~java
@StubRunnerPort("inventory-producer")
int inventoryPort;
~~~

Consumer phải dùng port được inject hoặc `StubFinder` để tạo URL, tránh hardcode một port có thể bị process khác sử dụng.

## 24. Ổn định test không có nghĩa bỏ qua concurrency

Một phương pháp nhanh để giảm flakiness là vô hiệu hóa mọi test song song. Điều đó có thể giúp cô lập nguyên nhân, nhưng không chứng minh hệ thống xử lý concurrency đúng.

Cần phân biệt:

- **Contract fixture deterministic:** một request/response đại diện được kiểm tra có thể tái hiện.
- **Concurrency behavior:** hai request đồng thời có bảo đảm transaction/idempotency mà hệ thống hứa hay không.
- **Test infrastructure isolation:** tests chạy song song không chia sẻ state trái phép.

Nếu producer có hai đơn hàng tranh mua một SKU, một contract HTTP đơn lẻ không bảo đảm không oversell. Hãy bổ sung concurrency/integration tests, nhưng thiết kế chúng sao cho có **điểm bắt đầu đồng bộ**, dữ liệu test riêng và assertions cuối cùng không phụ thuộc race bất định.

**Không mock mất concurrency ở contract base class rồi ghi rằng transaction behavior đã được xác nhận.**

## 25. Toolchain và artifact cũng phải tái lập được

Fixture ổn định chưa đủ nếu CI dùng generator/compiler khác nhau giữa các lần chạy.

Các thành phần nên được ghim:

- JDK version/distribution, ít nhất ở mức major tương thích.
- Spring Boot, Spring Cloud Contract plugin, verifier và Stub Runner versions.
- Maven Wrapper/Gradle Wrapper version.
- Dependency BOM và artifact repositories.
- Contract DSL source revision.
- Stub artifact version/classifier/digest.
- Locale, timezone, encoding của runner nếu chúng ảnh hưởng serialization.
- Test database/broker image version và fixture state.
- Gradle/Maven caches được quản lý theo input version.

### Hai lần generate khác nhau

Không phải mọi byte của generated Java/WireMock mapping phải **giống tuyệt đối** giữa hai plugin versions: generator có thể đổi whitespace, import order hoặc mapping serialization mà không đổi semantics.

Cách đánh giá đúng:

1. Với **cùng toolchain/version**, kết quả generate không nên phụ thuộc thời gian/random/environment bất ngờ.
2. Với **toolchain version đổi**, review generated assertions và mappings theo semantics, không chỉ diff số dòng.
3. Với **contract revision đổi**, xác minh đó là thay đổi có chủ đích, đặc biệt ở matcher.
4. Với **artifact publish**, giữ version/digest bất biến và đọc chính candidate được test.

Nếu artifact output khác do timestamp trong JAR metadata, điều này liên quan reproducible builds; vẫn cần phân biệt **khác bytes vì metadata** với **khác hành vi stub**. Khi tổ chức cần bảo đảm provenance byte-for-byte, cấu hình build reproducibility tương ứng và kiểm tra checksum.

## 26. Quality gate CI cho fixture và test được sinh

Một pipeline hợp lý:

~~~mermaid
flowchart TD
    A["Contract source được review"] --> B["Resolve pinned toolchain/fixture"]
    B --> C["Generate producer tests"]
    C --> D{"Đủ contract/tests?"}
    D -->|Không| X["Fail closed"]
    D -->|Có| E["Run producer tests"]
    E --> F{"PASS?"}
    F -->|Không| X
    F -->|Có| G["Inspect/package stub artifact"]
    G --> H["Stub Runner + real consumer tests"]
    H --> I{"Consumer PASS?"}
    I -->|Không| X
    I -->|Có| J["Record version/digest/test report"]
    J --> K["Release policy gate"]
~~~

### Tầng 1 — Contract discovery

- Các file Groovy/YAML expected có được phát hiện?
- `contractsPath`/`contractsDslDir` có đúng?
- Có DSL duplicated/trùng request mappings?
- Fixture files có được tham chiếu bằng path hợp lệ?
- Source revision/version có đúng với PR được review?

### Tầng 2 — Generated producer tests

- Đã sinh test Java và **thực sự chạy**?
- Số tests executed có khác 0 khi module cần contract?
- Không có test bị skip/ignored ngoài chính sách?
- Base class gọi producer code thật?
- Assertions cho static/dynamic values đúng như contract?

### Tầng 3 — Stub artifact

- Đúng `group:artifact:version:stubs`?
- Mappings/fixtures được đóng gói đầy đủ?
- Matcher không bị nới quá mức?
- Artifact đến từ cùng source/contract revision producer đã verify?
- Checksums/provenance có được ghi lại?

### Tầng 4 — Consumer test

- Stub Runner tải đúng candidate artifact?
- Consumer client gọi đúng port/URL runtime?
- Test check cả success, lỗi và JSON types liên quan?
- Không dùng unmatched WireMock 404 như một business 404 giả?
- Messaging handlers được kiểm tra với correlation/await hợp lý?

### Tầng 5 — Flake monitoring

Ngoài gate chính, có thể chạy **test stability suite định kỳ** trên runner sạch, lặp lại một số generated producer tests và consumer tests để nhận diện flakiness.

Ví dụ command tham khảo:

~~~bash
# Gradle plugin hiện đại, gọi trong đúng multi-project build:
./gradlew :inventory-producer:contractTest --rerun-tasks --no-build-cache

# Maven producer đã cấu hình verifier plugin:
./mvnw -B -ntp clean verify
~~~

Đây là các ví dụ để chạy trong dự án thật, **không phải lệnh đã thực thi trong bài học này**. `--rerun-tasks` giúp loại giả thuyết task bị UP-TO-DATE, nhưng không giải quyết nguyên nhân fixture state/time/random bị nhiễu.

### Đừng dùng retry để giấu lỗi

Chạy một test năm lần và chấp nhận “có một lần PASS” không tạo bằng chứng tương thích. Nếu policy cho phép automatic retry vì hạ tầng, phải:

1. Ghi nhận lần fail đầu tiên.
2. Phân loại flaky/infrastructure issue.
3. Có giới hạn retry rõ ràng.
4. Không làm mất log và artifact từ lần fail.
5. Có owner và mục tiêu loại bỏ flakiness.
6. Không phát hành API breaking chỉ nhờ test ngẫu nhiên xanh.


## 27. Chẩn đoán flaky test bằng bằng chứng

Khi generated test lúc PASS, lúc FAIL, hãy lưu đủ dữ liệu tái hiện:

~~~text
Contract:
  file: inventory/stockAvailable.groovy
  revision: <contract-sha>

Producer:
  source revision: <producer-sha>
  test: InventoryContractTest.shouldReturnStock
  expected status: 200
  actual status: 200
  expected quantity: 8
  actual quantity: 5

Environment:
  JDK: <version>
  SCC plugin: <version>
  timezone: <zone>
  database: <isolated-db-id>
  parallel tests: <on/off>
  fixture revision: <fixture-sha>

Stub:
  artifact: <group:artifact:version:stubs>
  digest: <sha256>
~~~

Các giá trị trong dấu `<...>` là placeholder phải lấy từ CI, không phải metadata Spring Cloud Contract tự tạo.

### Trình tự điều tra

1. **Tái hiện test đơn lẻ** với cùng source/contract revision.
2. **Đối chiếu fixture** trước và sau test, đặc biệt dữ liệu bị thay đổi.
3. **Chạy lại cùng test** trong môi trường mới được tạo sạch.
4. **Đổi thứ tự suite** hoặc tạm tắt parallelism để phát hiện shared state.
5. **Kiểm soát clock/timezone/locale** để xem test có phụ thuộc thời gian không.
6. **Đọc generated Java test** để xác nhận equality/matcher được sinh.
7. **Đọc generated WireMock mapping** để xác nhận stub request/response.
8. **Kiểm tra artifact version/digest**; có thể lỗi đến từ stub cũ chứ không phải flakiness.
9. **Sửa fixture/DSL/base test** ở nguồn, không sửa generated code.
10. **Thêm regression test** và giám sát sau khi sửa.

### Một lỗi trông ngẫu nhiên có thể là lỗi thật

Nếu hai request đồng thời tạo reservation cho cùng SKU và kết quả thay đổi, đó có thể là **lỗi concurrency của producer** thực sự. Đừng gắn nhãn “flaky infrastructure” khi chưa kiểm tra bất biến nghiệp vụ.

Một báo cáo hữu ích chỉ rõ producer nhận request gì, fixture ban đầu ra sao, test nào thay đổi state và bên nào có trách nhiệm xác minh.

## 28. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Fail khi timezone CI khác | `checkedAt` so chuỗi không chuẩn | Inject UTC clock/kiểm tra time semantics |
| Fail gần nửa đêm | `LocalDate.now()` phụ thuộc ngày | Dùng `Clock` và `ZoneId` |
| Fail do UUID khác | Response equality với ID động | Matcher format hoặc injected ID generator |
| Chỉ PASS khi test khác chạy trước | Fixture phụ thuộc state từ test khác | Setup/seed độc lập mỗi test |
| Chỉ fail khi parallel | Dùng chung DB row/queue/stub state | Isolation, namespace, resource lock |
| Fail do JSON key order | So chuỗi JSON nguyên văn | JSONPath/structural matcher |
| Array đổi thứ tự | Query thiếu sort hoặc contract không định nghĩa order | Chốt thứ tự và assert đúng semantics |
| Consumer nhận WireMock 404 | Request không match mapping | Kiểm tra method/path/header/body |
| Business 404 test xanh vì typo | Chỉ assert status | Assert error code/body |
| Stub trả dữ liệu cũ | Artifact/version stale | Ghim coordinate, kiểm tra digest |
| Producer test xanh dù đổi DSL | 0 tests hoặc test skip | Xem report, source set và plugin |
| Producer đỏ nhưng consumer xanh | Producer không đáp ứng DSL | Chặn publish verified stub |
| Message timeout | Broker/listener chưa ready, sai destination | Correlation, isolated group, bounded wait |
| Message test nhận event cũ | Queue/consumer group dùng chung | Reset/cô lập destination |
| Fixture không load trên Linux | Sai case path hoặc encoding | Kiểm tra path, UTF-8, entries trong JAR |
| Fail chỉ trên CI mới | JDK/plugin/dependency khác | Ghim wrapper/BOM/environment |
| Stateful stub fail sau test khác | WireMock state chưa reset | Reset scenario/instance riêng |
| Test xanh dù field sai | Regex `.*` hoặc `byType()` quá rộng | Thắt matcher theo invariant |
| Pass khi rerun nhiều lần | Shared state/race/time | Điều tra nguyên nhân, không pass-by-retry |

Các lỗi làm CI **không phát hiện breaking change** (matcher quá rộng, test skip, artifact cũ, unmatched 404) cần được ưu tiên xử lý ngang hoặc cao hơn các lỗi flaky làm suite đỏ.

## 29. Bài thực hành 1: timestamp biến đổi

Producer thực trả:

~~~json
{
  "sku": "SKU-101",
  "quantity": 8,
  "checkedAt": "2026-01-15T10:01:02Z"
}
~~~

DSL hiện đòi:

~~~json
{
  "sku": "SKU-101",
  "quantity": 8,
  "checkedAt": "2026-01-15T10:00:00Z"
}
~~~

Generated producer test fail mặc dù `checkedAt` được thiết kế là thời điểm đọc tồn kho và có thể thay đổi.

**Câu 1. Có nên xóa `checkedAt` khỏi contract không?**

Không tự động. Nếu consumer cần field đó, phải giữ và kiểm tra yêu cầu tương ứng. Xóa field chỉ hợp lý sau khi hai bên thống nhất nó không thuộc giao diện.

**Câu 2. Có những cách nào làm test xác định?**

- Inject `Clock.fixed` trong producer test để response khớp thời điểm mẫu.
- Dùng matcher timestamp nếu contract chỉ đòi định dạng hợp lệ; bổ sung test khác cho quan hệ thời gian khi cần.

**Câu 3. Nếu consumer hiển thị giờ theo timezone người dùng?**

API nên trả một định dạng không mơ hồ, ví dụ ISO-8601 với `Z`/offset. Consumer tự chuyển sang timezone hiển thị; không hardcode locale text của CI.

**Câu 4. Chỉ dùng `byType()` có đủ không?**

Không luôn đủ: string type không bảo đảm parse được timestamp. Cần matcher timestamp hoặc parse/so sánh thời gian trong test phù hợp.

## 30. Bài thực hành 2: matcher quá lỏng

Checkout yêu cầu:

~~~json
{"reservationId":"RSV-1001","status":"ACTIVE"}
~~~

Producer lỗi trả:

~~~json
{"reservationId":"","status":"FAILED"}
~~~

Generated test chỉ dùng:

~~~groovy
bodyMatchers {
    jsonPath('$.reservationId', byType())
    jsonPath('$.status', byType())
}
~~~

**Câu 1. Vì sao test có thể vẫn PASS?**

Vì cả chuỗi rỗng lẫn `FAILED` đều là string. Matcher kiểu không kiểm tra business constraints: **ID hợp lệ** và **status ACTIVE**.

**Câu 2. Cách sửa hợp lý?**

- `reservationId`: regex/format hoặc nonblank matcher đúng specification.
- `status`: equality `ACTIVE` ở happy-path fixture.
- Assert HTTP `201`, Content-Type và các field liên quan.

Phần response minh họa:

~~~groovy
response {
    status 201
    body(
        reservationId: 'RSV-1001',
        status: 'ACTIVE'
    )
    bodyMatchers {
        jsonPath('$.reservationId', byRegex('RSV-[0-9]{4}'))
    }
}
~~~

Đoạn này cần đặt trong một `Contract.make` đầy đủ.

**Câu 3. `.*` có tốt hơn `byType()` không?**

Không. Regex quá rộng có thể chấp nhận chuỗi rỗng. Chỉ nới nơi contract cho phép biến động.

## 31. Bài thực hành 3: HTTP và messaging chạy song song

### Tình huống

- Test A seed `SKU-101 quantity=8` rồi gọi GET.
- Test B tạo reservation làm giảm quantity.
- Test C nhận `StockChanged` từ broker topic dùng chung.
- Khi song song, A đôi lúc nhận `5` và C nhận event từ lần chạy trước.

### Kế hoạch khắc phục mẫu

1. Dùng **SKU/namespace riêng** cho từng suite hoặc test khi có thể.
2. Seed DB có cleanup/transaction rõ; không để test A bị test B sửa cùng row.
3. Tách consumer group/topic test hoặc reset offsets có kiểm soát.
4. Correlate message theo event ID/transaction ID, không match bất kỳ event nào.
5. Dùng Awaitility/condition-based wait với timeout hữu hạn thay `sleep`.
6. Không assert thứ tự event giữa Kafka partitions nếu giao thức không bảo đảm.
7. Giữ integration test cho concurrency thật, **không** xóa assertion vì parallel fail.
8. Dùng DB/broker/container test cô lập ở CI khi chạy nhiều suite.

### Câu hỏi tự kiểm tra

- Nếu A chỉ PASS khi B chưa chạy, đó là lỗi implementation hay fixture isolation?
- Nếu API cam kết quantity giảm sau reservation, cần test nào chứng minh?
- Nếu event ID là UUID động, producer test nên dùng equality hay matcher?
- Làm sao phân biệt business 404 với unmatched WireMock 404?
- Stub Runner tải bản cũ thì consumer PASS có chứng minh candidate mới tương thích không?

## 32. Checklist review fixture và generated tests

### Dữ liệu và trạng thái

- [ ] Mỗi contract có tên và tình huống nghiệp vụ rõ.
- [ ] Request mẫu có field/type/value cụ thể để producer test gửi được.
- [ ] Test identities không dựa vào row ngẫu nhiên trong database.
- [ ] Fixture không chứa secret hoặc dữ liệu người dùng thật.
- [ ] Không tạo `now()`/`UUID.randomUUID()` khi DSL được load nếu không cần.
- [ ] Nếu dùng random seed, seed được ghi và RNG không chia sẻ sai giữa các test.
- [ ] Database/queue được seed/reset theo ranh giới xác định.
- [ ] Tests có thể chạy riêng, đảo thứ tự và chạy nhiều lần.
- [ ] Parallel tests có namespace/lock/isolation phù hợp.

### Matcher và assertion

- [ ] Stub request matcher chấp nhận đúng request hợp lệ, không quá rộng.
- [ ] Producer generated test gửi request cụ thể.
- [ ] Stub response có fixture cụ thể, dễ dùng cho consumer.
- [ ] Producer response matcher chỉ nới những trường động hợp lệ.
- [ ] Status, headers, JSON types và giá trị nghiệp vụ được assert.
- [ ] ID/timestamp kiểm tra đúng format/invariant hoặc do injected dependency kiểm soát.
- [ ] Array ordering/length được kiểm tra theo contract.
- [ ] Không dùng `.*`/`byType()` để bỏ business constraints.
- [ ] Business 404 có error body/code khác unmatched stub response.
- [ ] Null, missing và empty values được phân biệt nếu consumer phụ thuộc.

### Generated artifacts và runtime

- [ ] Producer base class dựng đúng implementation trong phạm vi kiểm chứng.
- [ ] `Clock`/timezone/locale/encoding được kiểm soát khi ảnh hưởng output.
- [ ] Generated Java tests đã được đọc để kiểm tra request/assertions.
- [ ] Generated tests **thực sự chạy và PASS**, có test count hợp lệ.
- [ ] Stub mapping có method/path/body matchers đúng.
- [ ] Fixture `__files` được đóng gói đầy đủ.
- [ ] Stub Runner tải đúng version/classifier/digest, không lấy cache cũ.
- [ ] Random port được tra ở runtime, không hardcode `localhost:0`.
- [ ] Messaging tests có correlation, isolated group và bounded wait.
- [ ] Stateful WireMock scenarios được reset hoặc chạy trong instance riêng.

### CI và quy trình nhóm

- [ ] JDK/Gradle/Maven/Spring Cloud Contract versions đã ghim.
- [ ] Contract revision và stub artifact digest được ghi.
- [ ] Không publish verified stub khi producer tests fail/skip/0.
- [ ] Consumer tests dùng candidate stub cùng producer revision đã verify.
- [ ] Nhánh lỗi và boundary cases có fixture riêng.
- [ ] Test retry không xóa/che lần failure đầu tiên.
- [ ] Có người phụ trách điều tra flakiness.
- [ ] Mỗi thay đổi matcher được review tác động consumer.
- [ ] Có integration tests bảo vệ invariants ngoài phạm vi contract test.
- [ ] Không coi “test luôn xanh” là bằng chứng nó phát hiện được lỗi.

## 33. Ghi nhớ và tài liệu tham khảo

Một bộ Spring Cloud Contract tốt phải **vừa tái hiện được vừa đủ nghiêm ngặt**. Fixture cố định giúp producer generated test có input và state xác định. Matcher cho phép timestamp, UUID và các giá trị do producer tạo ra biến đổi hợp lệ. Nhưng chỉ dùng matcher tại nơi consumer cho phép: **không nới những quy tắc nghiệp vụ cần kiểm chứng**.

Đọc cả hai đầu: **generated producer tests** phải gửi request cụ thể và assert đúng hành vi; **stub mappings** phải match đúng request và trả response fixture phù hợp. CI xanh chỉ đáng tin nếu test thực sự chạy, artifact đúng version và test state được cô lập.

### Tài liệu chính thức

- [Spring Cloud Contract — Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): `consumer`/`producer` và dynamic values.
- [Spring Cloud Contract — How to Provide Dynamic Values](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-provide-dynamic-values.html): request matcher ở stub và concrete input ở producer test.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL và `bodyMatchers`.
- [Spring Cloud Contract — YAML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): matcher syntax của YAML.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractTest`, generated tests và `verifierStubsJar`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): producer verification và packaging stubs.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer sử dụng stubs.
- [Java — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): `Clock.fixed` và testable time.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mappings, request matcher và stateful scenarios.
- [Testcontainers — Documentation](https://java.testcontainers.org/): cô lập database, broker và test dependencies.

**Kết luận thực hành:** thay vì hỏi “fixture có giống production không?”, hãy hỏi **“cùng một tình huống, test có luôn kiểm tra đúng hành vi, bắt được lỗi và tạo stub mà consumer dùng đúng ý nghĩa không?”** Kiểm soát input, state, matcher, version và CI mới khiến kết quả contract testing thực sự đáng tin.
