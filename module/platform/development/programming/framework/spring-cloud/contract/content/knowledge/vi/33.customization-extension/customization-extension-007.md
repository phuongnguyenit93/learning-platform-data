# Tùy biến WireMock mà vẫn giữ dấu vết nguồn hợp đồng

## 1. Vấn đề: stub linh hoạt hơn nhưng mất mối liên hệ với contract

**Spring Cloud Contract (SCC)** giúp các nhóm producer và consumer thỏa thuận hành vi HTTP hoặc thông điệp thông qua **Groovy/YAML DSL**. Từ contract, Contract Verifier sinh test để kiểm chứng **implementation producer thật**; công cụ cũng có thể sinh **WireMock stubs**, đóng gói thành artifact để consumer dùng **Stub Runner** trong CI. Luồng này phát hiện những thay đổi API không tương thích trước khi phát hành.

WireMock có nhiều khả năng hơn một response JSON tĩnh: response templating, custom response transformer, request matching mở rộng, ưu tiên mapping, scenario state, latency và network faults. Những tùy biến đó hữu ích khi consumer cần thử dữ liệu động hoặc trường hợp lỗi. Nhưng nếu sửa stub trực tiếp mà không liên kết lại với nguồn hợp đồng, ta có thể tạo ra tình huống:

- Contract từ Inventory Service cam kết `GET /api/inventory/SKU-123` trả `available:true`.
- Generated producer tests xác nhận controller/service trả đúng body.
- Một nhóm sửa WireMock mapping thủ công để trả `available:false` hoặc đổi field thành `inStock`.
- Checkout Service thử với stub đã sửa, test xanh theo một giao diện **khác với contract được producer kiểm chứng**.
- Pipeline kết luận “đã xác nhận tương thích” nhưng không chỉ ra được response thực sự đến từ revision nào.

Nguy cơ còn lớn hơn khi một extension global thay đổi status, body hoặc headers của **mọi** mapping, khi một catch-all stub ghi đè mapping sinh từ contract, hoặc khi Stub Runner vẫn đang dùng artifact cũ.

**Đích đến của bài:** tùy biến WireMock để tăng năng lực thử nghiệm **mà không phá chuỗi truy vết**:

~~~text
Contract source + producer commit
    → generated producer tests
    → generated WireMock mappings
    → versioned, reviewed customization
    → stubs artifact có nguồn gốc rõ
    → Stub Runner đúng candidate
    → consumer client/handler thật
    → test report và compatibility decision
~~~

Đây là bài thuộc chương **Tùy biến và mở rộng**, tập trung đúng chủ đề **“Tùy biến WireMock mà vẫn giữ dấu vết nguồn hợp đồng”**.

### Sau bài học, bạn có thể

1. Phân biệt **contract source**, **generated mapping**, **custom mapping**, **WireMock extension** và **stub artifact**.
2. Nêu rõ tùy biến nào là **hành vi API đã cam kết**, tùy biến nào chỉ dành cho **test harness/resilience test**.
3. Dùng request matching, mapping priority, response templating, metadata và scenarios mà không che các ràng buộc quan trọng của contract.
4. Tổ chức customizations trong source control, không chỉnh trực tiếp output sinh trong `target`/`build`.
5. Ghi nguồn gốc của stubs artifact theo contract revision, producer commit, extension version và checksum.
6. Phân biệt WireMock server tự quản lý với WireMock do **Stub Runner** tạo; tránh cấu hình sai instance.
7. Tạo test đối chứng chứng minh custom mapping không biến request sai thành response đúng.
8. Đưa generation, verification, packaging, provenance và consumer compatibility vào CI có thể tái lập.

## 2. Năm loại đối tượng: không nên gọi tất cả là “stub”

| Đối tượng | Nguồn | Vai trò | Nguy cơ nếu nhầm |
|---|---|---|---|
| **Contract DSL** | `src/test/resources/contracts` hoặc contract repository đã thống nhất | Khai báo giao tiếp producer–consumer | Sửa mapping mà không sửa contract |
| **Generated producer test** | SCC Contract Verifier | Kiểm tra implementation producer đáp ứng DSL | Test bị skip/fake producer nhưng vẫn báo xanh |
| **Generated WireMock mapping** | SCC stub generator | Cho consumer một mô hình HTTP theo DSL | Chỉnh thủ công rồi mất khả năng tái sinh |
| **Custom WireMock config/extension** | Code và cấu hình test harness do nhóm sở hữu | Templating, matcher, state, fault, header phụ trợ... | Thay đổi semantics nhưng không được review như API change |
| **Stubs artifact + Stub Runner** | JAR được đóng gói/publish và nạp vào WireMock runtime | Phân phối và phục vụ mappings cho consumer | Chạy nhầm build, version hoặc mapping |

**Contract là nguồn thỏa thuận**, generated output là sản phẩm của một phiên bản generator, còn customization là **một input có chủ đích** của quá trình tạo/chạy stub. Mỗi phần phải có vị trí, quyền sở hữu và bằng chứng riêng.

Không nên dùng từ “contract passed” để mô tả một WireMock server do consumer tự viết mapping. Test như vậy có thể tốt cho thiết kế giao diện, nhưng **chưa chứng minh producer thật đáp ứng hợp đồng**.

## 3. Ba phạm vi tùy biến cần tách thành chính sách

| Nhóm tùy biến | Ví dụ | Có phải thay đổi contract công khai? | Cách kiểm chứng |
|---|---|---|---|
| **Hành vi thuộc hợp đồng** | Status, JSON schema, error code, required header, request matching | **Có**, nếu behavior thay đổi | Sửa/được review trong Groovy/YAML DSL; generated producer + consumer tests |
| **Kỹ thuật mô phỏng không đổi semantics** | Echo correlation ID, response templating đúng format, dữ liệu động nhưng trong miền được phép | **Có thể không**, nhưng vẫn cần kiểm | Assert contract invariants và kiểm mapping output với expected behavior |
| **Test harness / resilience** | 2 giây delay, connection reset, injected 503, scenario state giả lập | Thường **không phải** API producer cam kết | Đánh dấu test-only, chạy trong suite riêng, không thay thế baseline contract stub |

Ví dụ, việc client kiểm tra retry khi WireMock giả lập connection reset hữu ích, nhưng **không thể suy ra producer có cam kết sẽ reset connection**. Một fault injection test không được biến thành artifact “hợp đồng đã được producer verified”.

Quy tắc thiết kế: **nếu tùy biến làm thay đổi request nào được chấp nhận hoặc response nào consumer nhìn thấy theo giao diện công khai, hãy coi đó là thay đổi cần được review như một contract change**.

## 4. Kiến trúc bảo toàn provenance

~~~mermaid
flowchart TD
    A["Commit producer P và contract revision C"] --> B["SCC Contract Verifier"]
    B --> D["Generated producer tests"]
    B --> M["Generated WireMock mappings"]
    D --> G{"Executed tests > 0, tất cả đạt?"}
    G -- "Không" --> X["BLOCK"]
    G -- "Có" --> H["Build candidate"]
    M --> H
    E["Reviewed WireMock customizations revision W"] --> H
    H --> I["Stubs JAR candidate, digest và manifest"]
    I --> J["Maven-compatible repository"]
    J --> K["Stub Runner resolve exact candidate"]
    K --> L["WireMock nạp mappings + extensions"]
    L --> N["Consumer HTTP client thật"]
    N --> O{"Compatibility tests đạt?"}
    O -- "Không" --> X
    O -- "Có" --> Q["Release policy + audit record"]
~~~

Tại mỗi bước cần trả lời câu hỏi:

- **P:** code producer commit nào đã được kiểm thử?
- **C:** contract DSL revision/hash nào là nguồn?
- **W:** customization source và binary version nào đã được dùng?
- **I:** JAR candidate thực tế có nội dung nào, digest gì?
- **K–L:** Stub Runner đã resolve artifact nào và WireMock đã load những gì?
- **N–O:** consumer version nào dùng client thật, có assertion gì?

Chỉ có tên artifact `1.4.0-SNAPSHOT` không đủ xác định I; một SNAPSHOT mutable có thể trỏ nhiều builds khác nhau.

## 5. Ví dụ xuyên suốt: Inventory và Checkout

Checkout Service cần:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
X-Correlation-Id: req-1001
~~~

Inventory Service cam kết cho fixture `SKU-123` số lượng 12:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-Id: req-1001

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Giả sử correlation ID được phản hồi từ request và các SKU khác được phép có giá trị khác nhau. Ta có hai mục tiêu:

1. **Giữ invariants của contract:** method/path/status, kiểu/semantics của `sku`, `available`, `quantity` và header quan trọng.
2. **Tăng tính linh hoạt của stub:** cho phép nhiều correlation IDs hoặc phản hồi các tình huống lỗi do consumer test kích hoạt.

Không được “giải quyết” mục tiêu 2 bằng cách xóa mọi request matcher hoặc cho response body trả một mẫu không liên quan producer behavior.

## 6. Contract Groovy là nguồn hành vi công khai

Ví dụ tệp `src/test/resources/contracts/inventory/get-stock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout tra tồn kho SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

Một dạng YAML tương đương có thể là:

~~~yaml
description: Checkout tra tồn kho SKU-123
name: get_stock_sku123

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

Hai ví dụ là **lựa chọn thay thế** cho cùng scenario, không nhất thiết commit cả hai rồi sinh trùng mappings.

**Lưu ý quan trọng:** correlation header trong ví dụ HTTP đầu phần 5 chưa nằm trong contract ở phần này. Nếu consumer thật sự phụ thuộc **producer echo chính xác `X-Correlation-Id`**, đó là một **behavior công khai phải bổ sung vào contract/review và producer verification**, không chỉ thêm một response transformer ở stub.

## 7. Generated mapping: kiểm output nhưng không sửa làm nguồn

Từ contract, SCC có thể tạo WireMock mapping tương tự:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

**Đây là cấu trúc minh họa**. Mapping thực có thể dùng `body` thay vì `jsonBody`, thêm request headers/regex/JSONPath/metadata hoặc được đặt trong cấu trúc thư mục khác tùy SCC/WireMock version. Phải **mở file generated thực tế** để xác nhận.

Một mapping như trên là đầu ra của generation. Nếu tự sửa nó trong `target`/`build`:

- Lần `clean` tiếp theo có thể làm mất sửa đổi.
- Producer tests vẫn dùng contract cũ, trong khi consumer stub mới trả behavior khác.
- Không thể tái tạo JAR từ source code/version đã commit.
- Reviewer không thấy phần delta thật nếu output không nằm trong Git.
- Build cache có thể khôi phục một bản mapping không đúng revision.

**Nguyên tắc:** generated mappings là **derived artifacts**, không phải nguồn chỉnh sửa thủ công. Nếu một behavior thuộc hợp đồng thì sửa DSL; nếu là test harness, commit customization ở vị trí riêng, có ownership và test riêng.

## 8. Dấu vết nguồn tối thiểu cho một mapping

Với mỗi stub quan trọng, cần truy ra:

| Thông tin | Ví dụ | Thu từ đâu? |
|---|---|---|
| Producer service | `inventory-service` | Artifact identity / CI |
| Contract source path | `contracts/inventory/get-stock.groovy` | Contract repository |
| Contract revision | Commit/hash `a1b2c3d4` | Git/contract artifact |
| Generated mapping identifier | `get-stock-sku123` hoặc file path | SCC generation |
| Generator/plugin version | SCC build plugin version | Build metadata |
| Customization version | `wiremock-fixtures@c2d3e4` | Git module/build |
| Stub coordinates | `com.example:inventory-service:1.4.0-rc.pr173:stubs` | Repository |
| Stub digest | SHA-256 của JAR sau đóng gói | Producer CI |
| Consumer resolution | Exact version/digest được Stub Runner tải | Consumer CI |
| Consumer test | Checkout build/commit, scenario report | Test runner |

Không nên chỉ ghi một comment `generated by SCC` bên trong mapping: comment có thể không đầy đủ, mapping có thể bị ghi đè, và không biết JAR nào đã chạy.

Tùy khả năng của registry/pipeline, provenance có thể được lưu **bên trong artifact, ở metadata mapping hoặc trong một sidecar attestation/report**. Quan trọng là có thể đối chiếu **digest và revision** sau khi packaging.

## 9. Quy tắc source ownership cho customization

Một cấu trúc *đề xuất* trong producer repository:

~~~text
inventory-service/
├── pom.xml  (hoặc build.gradle)
├── src/test/resources/contracts/inventory/
│   ├── get-stock.groovy
│   └── sku-not-found.yml
├── src/test/java/com/example/inventory/
│   └── ContractTestBase.java
├── src/test/java/com/example/inventory/wiremock/
│   └── InventoryWireMockCustomizerTest.java
└── src/test/resources/wiremock-custom/
    ├── README-as-policy-example.txt
    ├── resilience/
    │   └── connection-reset.json
    └── scenarios/
        └── reservation-state.json
~~~

Cấu trúc này chỉ minh họa **phân loại source**; không phải các thư mục mà SCC mặc nhiên tự đóng gói. Nếu muốn package các mapping tùy biến vào stubs JAR, cần cấu hình **copy/merge resources có chủ đích** theo plugin/build thực tế và kiểm tra artifact cuối. Đừng tạo một thư mục tùy biến rồi giả định Stub Runner sẽ tự nhìn thấy nó.

Có thể đặt customization trong một test-support module/repository riêng, nhưng phải chốt version cùng producer candidate và nêu rõ phần nào chỉ là resilience test.

## 10. Lựa chọn 1: biểu diễn được bằng contract DSL thì ưu tiên DSL

Nếu requirement là producer trả 404 khi SKU không tồn tại, hãy mô tả trong contract, ví dụ:

~~~yaml
description: SKU không tồn tại

request:
  method: GET
  url: /api/inventory/SKU-404

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
~~~

**Không cần tự viết WireMock mapping thay thế** chỉ để mô tả 404 này. Đưa behavior vào DSL mang lại hai bằng chứng từ cùng nguồn:

- Generated producer test kiểm tra **Inventory implementation** trả 404 và error body.
- Generated stub thể hiện behavior ấy cho Checkout consumer test.

Nếu sửa riêng mapping thành `ITEM_NOT_FOUND`, producer test không còn kiểm điều consumer nhìn thấy. Đây là một trong những cách dễ tạo “hai sự thật” nhất.

Ưu tiên DSL cho method, URL, query/header/body matchers, status, headers, expected body, enum/error codes và các behavior HTTP/message mà SCC version hỗ trợ.

## 11. Lựa chọn 2: response templating khi dữ liệu thực sự động

WireMock hỗ trợ **response templating** (thường dựa trên Handlebars) để phản hồi theo dữ liệu request. Ví dụ một test harness cho phép echo correlation header:

~~~json
{
  "name": "inventory-correlation-example",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123",
    "headers": {
      "X-Correlation-Id": {
        "matches": "req-[0-9]{4,}"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json",
      "X-Correlation-Id": "{{request.headers.X-Correlation-Id}}"
    },
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    },
    "transformers": ["response-template"]
  }
}
~~~

**Đây là ví dụ WireMock mapping để minh họa nguyên lý**, không phải mapping mặc định của SCC. Cú pháp template expression, header lookup, tính năng transformer và việc templating cho từng thuộc tính phải được kiểm tra theo WireMock version đã chọn. Có thể dùng `body` dạng template nếu `jsonBody` không được xử lý như kỳ vọng trong phiên bản/harness.

Dùng response templating hợp lý khi:

- Echo một correlation ID được contract cam kết;
- Tạo response dynamic phù hợp format/semantics được phép;
- Giảm trùng lặp mapping mà không nới request matcher;
- Tạo fixture test data có quy tắc rõ ràng.

**Không dùng templating để “bịa” một business response chưa được producer verification chấp thuận.**

## 12. Escaping, injection và tính xác định của template

Tái sử dụng dữ liệu request trong response rất tiện, nhưng có rủi ro:

- Một giá trị chứa dấu ngoặc kép có thể phá JSON nếu chèn thẳng vào `body` mà không escape.
- Template helper không đúng ngữ cảnh có thể sinh HTML/JSON không hợp lệ.
- In nguyên authorization token, password hoặc PII từ request vào response/log có thể làm lộ dữ liệu.
- Random/time helper tạo output không xác định, khiến test flaky khi fixture cần giá trị chính xác.
- Một helper tự xây có thể truy cập nguồn dữ liệu không được phép trong môi trường test.

Khi sử dụng:

1. Ràng buộc request input bằng matcher/validation đúng contract.
2. Escape/serialize dữ liệu theo **ngữ cảnh JSON**, không nối chuỗi bừa bãi.
3. Chỉ echo field được contract cho phép; không echo secrets.
4. Dùng deterministic seed/clock khi cần tái lập.
5. Viết negative test với quote, newline, Unicode, chuỗi dài và ký tự đặc biệt.
6. Ghi rõ template engine/extension version trong build metadata.

Một template echo `X-Correlation-Id` mới chỉ mô phỏng behavior; nếu đó là nghĩa vụ công khai, phải chứng minh **producer thật** cũng echo đúng qua generated test/integration assertion.

## 13. Mapping priority: custom fallback không được nuốt contract mapping

WireMock có cơ chế **ưu tiên mappings**; thông thường **số priority nhỏ hơn có độ ưu tiên cao hơn**. Ví dụ mapping cụ thể:

~~~json
{
  "name": "inventory-contract-specific",
  "priority": 1,
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

Một fallback riêng cho test harness:

~~~json
{
  "name": "inventory-unmatched-fallback",
  "priority": 10,
  "request": {
    "method": "ANY",
    "urlPathPattern": "/api/inventory/.*"
  },
  "response": {
    "status": 501,
    "jsonBody": {
      "code": "STUB_NOT_CONFIGURED"
    }
  }
}
~~~

**Cảnh báo:** mapping `method: "ANY"` hoặc regex ở fallback cần đối chiếu cú pháp/khả năng WireMock version. Khi không chắc, dùng các method explicit hoặc kiểm mapping load thành công.

Mục tiêu của fallback:

- Thể hiện rõ “request không thuộc contract” khi test gọi nhầm;
- Không tạo business success 200 giả;
- Có priority thấp hơn mapping chuyên biệt;
- Không thay business 404/validation 422 đã được contract cam kết;
- Được dùng như **diagnostic fixture**, không mặc định là behavior producer.

Nếu fallback trả `200 {"available":true}` cho mọi đường dẫn, consumer test có thể xanh dù client gửi URL sai. Đó là anti-pattern cần loại bỏ.

## 14. Test fallback bằng request sai để bắt “xanh giả”

Để kiểm soát fallback và mapping priority, không chỉ gửi request hợp lệ. Hãy cố tình gửi:

~~~text
GET /api/inventory/SKU-123      -> 200 + body contract
GET /api/inventory/NOT-A-SKU     -> không được nhận nhầm success SKU-123
POST /api/inventory/SKU-123     -> không được nhận nhầm GET mapping
GET /api/inventory/SKU-123?x=1  -> xét policy query params
GET /wrong/inventory/SKU-123    -> không được nhận 200 inventory
~~~

Nếu một fallback được dùng trong môi trường test, nên bảo đảm **lỗi không match** được báo rõ (có thể là status chẩn đoán khác với business response) và consumer test không nhầm với `SKU_NOT_FOUND` hợp lệ từ producer.

**Không dùng một HTTP status duy nhất làm tiêu chí:** WireMock unmatched 404 có thể không phải business 404. Test lỗi nghiệp vụ cần assert cả **mã lỗi/body** và khi cần xem request journal.

Một test đối chứng mạnh còn kiểm tra mapping được match bằng **ID/name/metadata** hoặc từ request journal, tùy API của WireMock version. Bằng cách đó, không chỉ thấy 200 mà còn biết **mapping nào** đã phục vụ request.

## 15. Mapping metadata: gắn nhãn provenance nhưng đừng coi nhãn là chứng cứ duy nhất

WireMock cho phép lưu **metadata** ở mapping, hữu ích để mô tả nguồn:

~~~json
{
  "name": "inventory-stock-sku123",
  "metadata": {
    "purpose": "contract-generated-or-reviewed",
    "contractSource": "contracts/inventory/get-stock.groovy",
    "producerService": "inventory-service",
    "scenarioId": "INV-STOCK-001",
    "owner": "inventory-api-team"
  },
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

Metadata là **mô tả**, không tự chứng minh rằng source file thực đã sinh mapping. Một người có thể copy sai tên `contractSource` sang file khác. Vì vậy:

- Dùng metadata để **liên kết/tra cứu** mappings.
- Ghi **contract revision/hash** và candidate artifact provenance ở mức CI.
- So sự hiện diện của mapping trong JAR với danh sách contracts kỳ vọng.
- Tạo metadata trong bước build có kiểm soát, không tin một nhãn tự ghi.
- Xác minh digest của artifact **sau** khi đóng gói mọi metadata/customization.

Nếu generator không thêm metadata vào mappings mặc định, có thể duy trì **manifest bên ngoài mappings**: map `mapping file → contract source → customization source`. Cách này không yêu cầu sửa generated files bằng tay.

## 16. Không nên dùng metadata làm đường vòng sửa contract

Ví dụ mapping:

~~~json
{
  "metadata": {
    "contractSource": "contracts/inventory/get-stock.groovy"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "available": false
    }
  }
}
~~~

trong khi contract nguồn cam kết `available=true`.

Có `contractSource` **không làm response tự trở nên hợp lệ**. Muốn chấp nhận behavior mới:

1. Sửa contract DSL tương ứng.
2. Để producer/consumer owners review breaking/change semantics.
3. Chạy generated producer tests trên implementation thật.
4. Sinh lại stub từ cùng revision.
5. Chạy consumer compatibility tests với candidate mới.

Nếu response `available=false` chỉ dùng để thử Checkout handling khi hết hàng, hãy tạo **một scenario contract có producer state phù hợp** hoặc **một test-only fault/fixture riêng** có nhãn rõ, không trình bày nó là response hợp lệ của scenario SKU-123 còn 12 đơn vị.

## 17. Custom response transformer: khi templating chưa đủ

Một extension có thể sửa response trước khi WireMock phục vụ, ví dụ thêm một **header chẩn đoán chỉ dùng cho test harness** hoặc biến đổi format dữ liệu trong giới hạn đã công bố.

WireMock có API mở rộng cho response transformers; phiên bản **WireMock 2** và **WireMock 3** có khác biệt về interface, package, lifecycle và cách đăng ký. Mẫu dưới đây là **minh họa ý tưởng** theo kiểu API WireMock 3 của `ResponseDefinitionTransformerV2`; cần điều chỉnh và biên dịch với đúng dependency đã chọn:

~~~java
import com.github.tomakehurst.wiremock.extension.ResponseDefinitionTransformerV2;
import com.github.tomakehurst.wiremock.http.ResponseDefinition;
import com.github.tomakehurst.wiremock.http.ResponseDefinitionBuilder;
import com.github.tomakehurst.wiremock.stubbing.ServeEvent;

public final class DiagnosticTraceTransformer
        extends ResponseDefinitionTransformerV2 {

    @Override
    public String getName() {
        return "diagnostic-trace";
    }

    @Override
    public ResponseDefinition transform(ServeEvent event) {
        ResponseDefinition original = event.getResponseDefinition();

        return ResponseDefinitionBuilder.like(original)
            .withHeader("X-Test-Harness", "inventory-stub")
            .build();
    }
}
~~~

Một mapping có thể yêu cầu transformer theo tên:

~~~json
{
  "name": "inventory-with-diagnostic-header",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    },
    "transformers": ["diagnostic-trace"]
  }
}
~~~

Những điều cần lưu ý:

- Extension class phải có trên **classpath của WireMock instance thực sự chạy**.
- Extension phải được **đăng ký trong server configuration** theo WireMock version; tên trong JSON tự nó không cài JAR.
- Header `X-Test-Harness` là **chỉ dấu nội bộ cho test**, không phải header producer cam kết. Không viết consumer contract assertions dựa vào header này trừ khi mục tiêu là kiểm test harness.
- Một transformer **global** có thể sửa mọi mapping, kể cả business error responses. Ưu tiên **per-stub opt-in** khi không muốn ảnh hưởng toàn suite.
- `like(original)` nhằm giữ response definition hiện có, nhưng phải kiểm code và behavior của phiên bản được dùng, nhất là khi response có body file, delays hoặc headers.
- Khi nâng WireMock major version, kiểm API extension và generated mappings trước khi cho phép reuse binary.

Nếu một transformer **đổi `status`, `available`, `quantity` hoặc error code**, đó có thể là thay đổi semantics; nó phải được review/kiểm chứng giống như sửa contract.

## 18. Standalone WireMockServer không phải Stub Runner server

Để hiểu cách đăng ký extension ở một WireMock server **do test tự tạo**, ví dụ conceptual:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;

WireMockServer server = new WireMockServer(
    WireMockConfiguration.wireMockConfig()
        .dynamicPort()
        .extensions(new DiagnosticTraceTransformer())
);

server.start();

try {
    // Nạp mappings và thực thi test với server này.
    // Trong dự án thật, cần chọn đúng artifact nguồn mapping.
} finally {
    server.stop();
}
~~~

Đoạn này minh họa quản lý server độc lập. Nếu consumer test dùng `@AutoConfigureStubRunner`, **Stub Runner có thể khởi tạo WireMockServer khác**. Đăng ký extension vào `server` trên **không mặc nhiên đăng ký** nó vào server do Stub Runner quản lý.

Vì vậy cần kiểm tra:

- WireMock nào thực sự phục vụ URL mà HTTP client của consumer đang gọi?
- Server ấy có extension binary/classpath và registration config chưa?
- Stub Runner version có hỗ trợ cách tùy biến WireMock instance nào?
- Nếu framework expose customization hook, hook được gọi **trước khi mappings được nạp** hay không?
- Có nhiều stubs JAR/server trong cùng test không, và extension áp dụng cho server nào?

Không nên sao chép một `WireMockServer` startup độc lập vào test dùng Stub Runner rồi tưởng đã tùy biến Stub Runner. Có thể vô tình tạo **hai server** và client trỏ vào server sai.

## 19. Phân biệt custom code của test harness với binary được consumer chạy

Một extension cần nhiều hơn file Java source:

~~~text
customization source revision W
    ↓ compile/package
extension binary E + dependency versions
    ↓ wiremock runtime classpath
WireMock instance + registered extension
    ↓
effective mapping behavior
~~~

Do đó khi ghi provenance, cần biết ít nhất:

- Source revision của custom transformer/matcher;
- Dependency WireMock version tương thích với binary;
- Hash/version của extension JAR hoặc test-support module;
- Config đăng ký extension vào Stub Runner/WireMock;
- Mapping nào đang bật transformer ấy;
- Test report chứng minh behavior khi extension được bật/tắt.

Một stubs JAR chứa **JSON mapping có `"transformers":["diagnostic-trace"]`** không đủ nếu runtime thiếu extension. Consumer CI phải báo lỗi rõ, không tự bỏ qua transformer rồi trả response mặc định hoặc fallback mà vẫn xem suite là pass.

## 20. Custom request matcher: mở rộng nhưng đừng biến mọi request thành hợp lệ

WireMock có các kiểu request matcher mở rộng khi method/path/header/JSONPath mặc định chưa đủ, chẳng hạn xác nhận chữ ký request theo quy tắc thử nghiệm hoặc đối chiếu một trường với nhiều phần khác.

Một matcher đúng có nhiệm vụ trả **match/no-match** theo quy tắc contract. Nhưng custom matcher cũng có thể quá rộng:

~~~text
Sai:
  isMatch(request) = true

Đúng theo intent:
  isMatch(request) =
    method = POST
    AND path = /api/reservations
    AND Content-Type là application/json
    AND sku theo format đã cam kết
    AND quantity là số nguyên trong miền hợp lệ
~~~

Nếu dùng custom matcher cho chữ ký HMAC:

- Test secret phải được quản lý an toàn, không hardcode production credentials.
- Phải định nghĩa canonicalization body/header chuẩn; đừng đơn giản so chuỗi body nếu JSON cho phép thay thứ tự keys.
- Viết negative tests cho chữ ký sai, thiếu timestamp, body đã đổi, replay ngoài cửa sổ hợp lệ.
- Đảm bảo matching không quá đắt hoặc có side effect.
- Ghi extension version/owner và trường hợp nào được dùng.

Các API `RequestMatcherExtension`/`MatchResult` có thể thay đổi giữa WireMock versions; bài này trình bày **contract của extension ở mức chức năng** để không đưa một code signature không đúng vào dự án chưa xác định version.

Đừng dùng custom matcher để **bỏ qua** những ràng buộc mà DSL gốc có thể thể hiện rõ và kiểm chứng được.

## 21. Stateful scenarios: mô phỏng quá trình nhưng phải reset

WireMock hỗ trợ **scenario states** để phản hồi theo chuỗi tương tác. Ví dụ một hành trình test:

~~~text
Started
  GET /api/inventory/SKU-123 -> 200 available=true
  -> chuyển sang Depleted

Depleted
  GET /api/inventory/SKU-123 -> 200 available=false
~~~

Một mapping minh họa cho lần đầu:

~~~json
{
  "name": "inventory-started",
  "scenarioName": "inventory-depletes",
  "requiredScenarioState": "Started",
  "newScenarioState": "Depleted",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 1
    }
  }
}
~~~

Mapping cho trạng thái tiếp theo:

~~~json
{
  "name": "inventory-depleted",
  "scenarioName": "inventory-depletes",
  "requiredScenarioState": "Depleted",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "jsonBody": {
      "sku": "SKU-123",
      "available": false,
      "quantity": 0
    }
  }
}
~~~

Đây là **WireMock test scenario**, không tự chứng minh Inventory thực sự giảm quantity sau GET. Nếu contract nghiệp vụ nói GET là read-only, mô phỏng việc GET làm cạn kho là **không phản ánh producer semantics** và chỉ nên dùng khi test một tình huống client resilience được gắn nhãn rõ.

Để tránh false failures/false PASS:

- Reset scenario state giữa các bài test;
- Không để test A vô tình để lại `Depleted` cho test B;
- Không chạy parallel tests trên cùng stateful WireMock instance nếu chưa cô lập;
- Không dùng scenario state để mô phỏng producer business behavior mà producer chưa được verification.

**Stateful stub kiểm tra consumer behavior**, còn producer state transition phải được kiểm chứng trong producer tests/integration tests riêng.

## 22. Latency, fault injection và HTTP 503: phân biệt testing với contract

WireMock có thể trả response chậm hoặc mô phỏng network fault:

~~~json
{
  "name": "inventory-delayed-test-only",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "status": 200,
    "fixedDelayMilliseconds": 1500,
    "jsonBody": {
      "sku": "SKU-123",
      "available": true,
      "quantity": 12
    }
  }
}
~~~

Một dạng fault injection minh họa:

~~~json
{
  "name": "inventory-reset-test-only",
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-123"
  },
  "response": {
    "fault": "CONNECTION_RESET_BY_PEER"
  }
}
~~~

Các cấu hình trên cần được kiểm tra với WireMock version chạy thật. Đặc biệt, **connection reset không phải HTTP response status 503**: client thường nhận transport exception, còn 503 là một response HTTP được server trả.

Mục tiêu và kết luận phải đúng:

| Fixture | Test điều gì? | Không chứng minh |
|---|---|---|
| Delay 1.500 ms | Consumer timeout/latency handling | Producer thực có latency 1.500 ms |
| Connection reset | Retry/circuit breaker khi kết nối hỏng | Producer cam kết tự reset connection |
| Contract 503 + `INVENTORY_UNAVAILABLE` | Consumer xử lý business/service error đã cam kết | Mọi sự cố mạng đều trả 503 |
| 200 với body đúng contract | Happy path compatibility | Timeout/broker/database production |

Nếu dùng fault/resilience mappings cùng baseline mappings, **phải cô lập theo test suite, scenario, port hoặc header chỉ dành cho test**. Đừng để một global priority cao “bắt cóc” baseline contract stub.

## 23. Mapping collision: khi hai stub cùng match một request

Khi merge generated mapping và custom mapping, rất dễ có hai entries cùng match:

~~~text
Generated:
  GET /api/inventory/SKU-123 -> 200 available=true

Custom:
  GET /api/inventory/SKU-123 -> 200 available=false
~~~

Nếu priority và điều kiện match không đủ phân biệt, **thứ tự phục vụ có thể khó dự đoán**. Một custom mapping vô tình có ưu tiên cao hơn có thể che generated mapping. Consumer test nhìn thấy response khác nhưng report vẫn gắn với “stub artifact đúng version”.

Để kiểm soát collisions:

1. Liệt kê generated và custom mapping IDs/names, method/path/headers/body predicates.
2. Kiểm những cặp mapping có **tập requests chồng lấn**.
3. Đặt priority có chủ đích; nhớ số nhỏ thường ưu tiên cao.
4. Chỉ dùng custom behavior khi có discriminator rõ (test-only header, riêng port, scenario state hoặc test suite riêng).
5. Tránh catch-all success 200, đặc biệt với fallback.
6. Viết test gọi request **có thể match cả hai** để xác minh mapping được chọn đúng.
7. Chạy negative tests với request thiếu header/sai path.
8. Kiểm request journal và mapping thực tế đã phục vụ response.

Với cùng một business behavior thuộc contract, **không nên có hai nguồn mapping đối lập**. Hãy đưa behavior được chấp nhận vào contract DSL rồi regenerate.

## 24. Dynamic mappings qua Admin API: tiện nhưng khó tái lập

WireMock có API quản lý mappings trong runtime, cho phép test thêm hoặc đổi stub khi server đã chạy. Điều này có ích cho setup đặc thù, nhưng nếu dùng tùy tiện:

- Test A thêm mapping, test B tình cờ dùng lại;
- CI chỉ lưu JAR nhưng không lưu mapping được tạo bằng code;
- Không có cách tái lập chính xác response từng request;
- Runtime admin state thay đổi mà artifact digest vẫn giống hệt;
- Test có thể pass local nhưng fail khi chạy song song.

Cách sử dụng an toàn:

- Quản lý dynamic mapping definitions dưới version control.
- Test setup **nạp deterministic fixtures** từ source/manifest.
- Reset mappings/scenarios đúng lifecycle trước và sau test.
- Log các mapping IDs/versions đã thêm bằng code.
- Không chấp nhận mapping runtime tự phát **làm nguồn contract chính thức**.
- Khi cần kiểm chứng compatibility, kiểm effective mappings sau khi setup, không chỉ stubs JAR tĩnh.

Nếu một response được nạp qua Admin API thay vì đến từ candidate artifact, phải nói rõ trong report đó là **custom test fixture**, không tự gán nó là SCC-generated mapping.

## 25. Customization nên nằm trong build graph có thể tái tạo

Một nguyên tắc tốt:

~~~text
StubsCandidate =
    Generate(ContractSources@C, SCCPlugin@V)
    + ReviewedOverrides@W
    + StaticFixtures@F
    + BuildConfiguration@B
~~~

Đây là **mô hình phụ thuộc**, không phải cú pháp build plugin có sẵn. Từng input cần được định danh để tái tạo artifact khi cần.

Một bản ghi build có thể giữ:

~~~yaml
producer:
  service: inventory-service
  commit: a1b2c3d4
contract:
  revision: a1b2c3d4
  root: src/test/resources/contracts
toolchain:
  springCloudContractPlugin: VERSION_FROM_BUILD
  wireMockRuntime: VERSION_FROM_BUILD
customization:
  revision: c2d3e4f5
  manifest: wiremock-custom-manifest
artifact:
  groupId: com.example
  artifactId: inventory-service
  version: 1.4.0-rc.pr173.a1b2c3d4
  classifier: stubs
  sha256: SHA256_FROM_PACKAGED_ARTIFACT
~~~

Đây là **manifest minh họa do CI quản lý**, không phải schema SCC bắt buộc. Dữ liệu `VERSION_FROM_BUILD` phải lấy từ effective dependency/build configuration thật.

**Quan trọng về checksum:** digest của JAR chỉ được tính **sau khi tất cả customizations/metadata bên trong JAR đã được đóng gói**. Nếu thêm provenance JSON vào JAR **sau** khi tính digest, giá trị đã ghi không còn đúng.

## 26. Provenance ở đâu: mapping metadata, manifest trong JAR hay sidecar?

Ba phương án có ưu/nhược điểm khác nhau:

| Phương án | Ưu điểm | Giới hạn |
|---|---|---|
| `metadata` trong từng mapping | Dễ gắn nhãn source/scenario/owner | Có thể bị copy sai; generated mapping không mặc định có |
| `META-INF/contract-provenance.json` trong stubs JAR | Artifact tự mang thông tin source/toolchain | Phải cấu hình packaging, không được tự giả định SCC tạo |
| Sidecar provenance/attestation gắn digest artifact | Có thể ký, audit và không sửa JAR khi đã đóng | Registry/CI cần quản lý liên kết không nhập nhằng |

Một phương án thực dụng là dùng **mapping names/metadata cho truy vết từng scenario** và **sidecar/provenance record ở cấp artifact** cho commit, dependency versions, digest và build run.

Nếu dùng manifest **bên trong** JAR, cần tạo/đóng gói trước khi tính checksum. Đừng tự nhét `artifactSha256` của chính JAR vào nội dung JAR theo cách tạo bài toán vòng lặp digest; nên lưu **digest ở sidecar sau packaging**.

Mọi thông tin provenance cần được tạo từ **build inputs đáng tin**, không chỉ từ chuỗi người dùng nhập vào manifest.

## 27. Sản phẩm khi publish: JAR đầy đủ, không phải mapping rời

Một stubs artifact ví dụ:

~~~text
groupId:    com.example
artifactId: inventory-service
version:    1.4.0-rc.pr173.a1b2c3d4
classifier: stubs
type:       jar
~~~

Tên file logic:

~~~text
inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Tùy SCC/plugin version, mappings/contracts/resources có thể được lưu dưới một cấu trúc gần như:

~~~text
META-INF/com.example/inventory-service/1.4.0-rc.pr173.a1b2c3d4/
  contracts/
    inventory/get-stock.groovy
  mappings/
    inventory-get-stock.json
  __files/
    inventory-response.json
~~~

**Cấu trúc chỉ là minh họa.** Phải kiểm JAR thật vì layout/path của SCC, body files và các resource paths có thể khác.

Khi đóng gói customizations:

- Không để file response body được mapping tham chiếu nhưng bị thiếu trong JAR.
- Không dùng path tuyệt đối phụ thuộc máy developer.
- Không làm mất original generated mappings.
- Không tạo mappings trùng mà không có chủ ý về priority.
- Không đặt secrets/PII của production trong fixtures.
- Extension binary (nếu cần ở runtime) phải sẵn sàng theo cơ chế cung cấp của test runner; **JSON trong JAR không tự mang theo toàn bộ dependency classpath**.

## 28. Kiểm stubs JAR trước khi publish

Trước khi consumer chạy Stub Runner, cần kiểm **chính artifact sẽ được publish**, không chỉ source trong producer:

~~~bash
# Đổi tên theo output JAR thật.
jar tf target/inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Xác minh có đủ contract sources, generated mappings, các `__files` mà `bodyFileName` tham chiếu, đúng classifier `stubs`, không có fixture resilience lọt vào baseline, không có mapping collision và không thiếu extension binary/registration cần thiết.

Số mapping phải được đối chiếu với **danh sách scenario kỳ vọng**. Chỉ đếm file JSON không đủ: một mapping bị thiếu và một mapping thừa vẫn có thể cho cùng tổng số. Khi plugin hỗ trợ sinh contract naming/path khác nhau, dùng **manifest map file → contract source** để so.

Không nên suy diễn rằng SCC tự đóng gói mọi thư mục `wiremock-custom` đã tạo; mở JAR cuối để kiểm **đường dẫn thực mà Stub Runner đọc**.

## 29. Digest và candidate version là bằng chứng về đúng bytes

Để so bản producer publish với bản consumer tải:

~~~bash
sha256sum target/inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Trên Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 -Path .\target\inventory-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Một báo cáo nên có:

~~~yaml
producerCommit: a1b2c3d4
contractRevision: a1b2c3d4
customizationRevision: c2d3e4f5
sccPluginVersion: FROM_BUILD
wireMockVersion: FROM_RUNTIME
stubArtifact: com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs
producerSha256: FROM_PACKAGED_JAR
consumerResolvedSha256: FROM_DOWNLOADED_JAR
generatedMappingCount: FROM_BUILD
loadedMappingCount: FROM_STUB_RUNTIME
~~~

Dữ liệu `FROM_*` chỉ là placeholder, không phải kết quả đã đo. **Điều kiện:** digest ở consumer phải khớp digest producer CI phát hành cho **đúng candidate**.

Nếu thêm một manifest vào JAR sau khi tính SHA-256, phải tính lại. Tránh lưu chính digest của JAR **bên trong JAR** theo cách tạo vòng lặp; đặt digest ở sidecar attestation sau packaging.

## 30. Consumer test phải chạy client thật với Stub Runner

Ví dụ ở Checkout Service:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/candidates"
)
class InventoryConsumerCompatibilityTest {

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void checkoutCanReadInventoryCandidate() {
        StockResponse stock =
            inventoryClient.getStock("SKU-123");

        assertThat(stock.sku()).isEqualTo("SKU-123");
        assertThat(stock.available()).isTrue();
        assertThat(stock.quantity()).isEqualTo(12);
    }
}
~~~

`InventoryClient` và `StockResponse` là class ví dụ của Checkout, không phải SCC API. `example.invalid` là URL giả; cấu hình repository/credential/port cần thay theo dự án. `REMOTE` resolve artifact từ repository phù hợp; `LOCAL` yêu cầu artifact đã được install vào nguồn local runner hỗ trợ, **không mặc định dùng cùng local cache producer**.

Nếu test dùng `when(inventoryClient.getStock(...)).thenReturn(...)`, nó **không gọi WireMock**; mọi custom matcher/transformer trong JAR đều có thể bị bỏ qua. Với compatibility suite, phải gọi **HTTP client production thật**.

## 31. Kiểm đúng WireMock instance, không nhầm server

Một suite có thể tồn tại nhiều server:

~~~text
Checkout InventoryClient -> Stub Runner Inventory:18081
Checkout PricingClient   -> Stub Runner Pricing:18082
Test custom setup        -> Standalone WireMockServer:dynamicPort
~~~

Extension chỉ có tác dụng ở server **đã đăng ký nó**. Để xác minh, log:

1. Base URL của consumer client thật;
2. Artifact/version/digest mà Stub Runner resolve;
3. Port thực và mapping count của WireMock;
4. Extension name/version đã được server đăng ký;
5. Mapping name/ID thực sự match request qua journal;
6. Test context lifecycle, scenario state và thời điểm startup.

Một method `.extensions(new MyTransformer())` trong một standalone server ở port khác **không tùy biến Stub Runner instance**. Nếu SCC version có customization hook, kiểm API/chữ ký của đúng version và bảo đảm hook được áp dụng cho **managed instance**.

## 32. Tách baseline compatibility và resilience tests

| Suite | Response source | Kết luận hợp lệ |
|---|---|---|
| Producer Contract Verifier | Implementation producer thật | Producer đáp ứng contract scenarios |
| Consumer baseline | Stubs artifact candidate có provenance, mapping không đổi semantics | Consumer hiểu behavior contract đã được producer-verified |
| Consumer resilience | Custom delay/reset/overload fixtures | Client xử lý sự cố giả lập đúng |
| Design preview | Mapping consumer tự tạo | Client xử lý một API giả định trong phát triển |
| End-to-end | Producer/broker/network thật | Tích hợp theo phạm vi môi trường |

**Resilience test PASS không thay thế baseline compatibility PASS.** Nếu faults chia sẻ artifact hoặc server baseline, cần có header/port/scenario suite isolation để fault không vô tình đè generated contract mapping.

Một report tốt phải nêu rõ mapping nào do contract sinh, mapping nào được thêm chỉ để thử fault, và consumer đã chạy với instance/version nào.

## 33. Negative tests cho request matcher và priority

Một ma trận bắt lỗi:

| Request | Kỳ vọng | Nếu trả nhầm success |
|---|---|---|
| `GET /api/inventory/SKU-123` | Match baseline 200 | — |
| `GET /api/inventory/WRONG` khi không có contract | Không match baseline SKU-123 | URL matcher quá rộng |
| `POST /api/inventory/SKU-123` | Không match GET baseline | Method matcher lỏng |
| `GET /api/inventory/SKU-123` thiếu header required | Theo contract phải bị từ chối/match scenario phù hợp | Header matcher lỏng |
| Request không có test-only discriminator | Không match fault mapping | Fault mapping bị bật global |
| Request match cả generated và custom | Test biết mapping nào thắng | Collision/priority không kiểm soát |
| Client gọi port của Pricing | Test fail rõ | Sai base URL hoặc service routing |

Không phải mọi request không hợp lệ đều phải trả 404: có thể có **business validation 400/422 đã được contract hóa**. Điều quan trọng là **không nhận nhầm happy-path 200/201**.

Xem WireMock request journal/near misses khi cần để biết mapping **thực sự phục vụ** request; chỉ thấy HTTP status không đủ chứng minh đã match mapping mong muốn.

## 34. Mutation tests: tùy biến không được che lỗi producer

Trong một nhánh thử, sửa code Inventory:

~~~java
// Code đúng cho fixture quantity=12:
return new StockResponse("SKU-123", true, 12);
~~~

thành:

~~~java
// Mutation cố ý sai:
return new StockResponse("SKU-123", false, 12);
~~~

Generated producer test phải **FAIL** khi contract yêu cầu `available:true`. Nếu base test dùng fake controller luôn trả `true`, kết quả xanh giả. Nếu custom transformer sửa `false` thành `true` trong producer test path, nó có thể che sai behavior.

Thử thêm các mutation phía consumer/stub:

- Đổi URL request thành `/api/stock/SKU-123`; baseline matcher phải không trả success.
- Đổi header required; stub không được trả nhầm mapping khác.
- Tăng priority fault mapping ở baseline; negative test phải phát hiện.
- Tắt extension đang required; test phải báo ERROR/FAIL.
- Thay response body file bằng file không tồn tại; artifact check phải chặn.
- Dùng JAR candidate cũ; digest/provenance gate phải chặn.

Khôi phục mọi mutation trước khi merge. Lưu **test chuyển đỏ rồi xanh trở lại** như bằng chứng suite có khả năng phát hiện regression.

## 35. CI pipeline nối code, contract, customization và consumer

~~~mermaid
flowchart TD
    A["Producer code + contract revision"] --> B["SCC generate tests + mappings"]
    B --> C{"Producer tests executed > 0 và PASS?"}
    C -- "Không" --> X["BLOCK"]
    C -- "Có" --> D["Merge reviewed customizations"]
    E["Customization revision + extension binary"] --> D
    D --> F["Validate mappings, collisions, __files, test cases"]
    F --> G{"Không có override trái phép?"}
    G -- "Không" --> X
    G -- "Có" --> H["Package stubs JAR candidate"]
    H --> I["Compute digest + provenance attestation"]
    I --> J["Publish immutable candidate artifact"]
    J --> K["Stub Runner resolve đúng artifact"]
    K --> L["Consumer client thật + negative tests"]
    L --> M{"Compatible?"}
    M -- "Không" --> X
    M -- "Có" --> N["Release quality gates"]
~~~

Một gate tối thiểu cần bảo đảm contract discovery và executed producer tests **lớn hơn 0**, customizations được review, JAR đủ resources, artifact digest khớp khi consumer tải, extension nạp đúng runtime và test dùng HTTP client thật.

`BUILD SUCCESSFUL` chỉ có ý nghĩa với các checks **thực sự chạy**; không coi generated test bằng 0 hoặc consumer mock test là bằng chứng đã kiểm chứng contract.

## 36. Maven và Gradle: merge customization là một bước build có kiểm soát

Trong producer Maven, có thể hình dung:

~~~text
Groovy/YAML contracts
 -> spring-cloud-contract-maven-plugin
 -> generated producer tests + WireMock mappings
 -> test runner kiểm code producer thật
 -> merge reviewed custom resources
 -> package stubs JAR classifier
 -> install/deploy candidate
~~~

Với Gradle:

~~~text
contracts source
 -> Spring Cloud Contract Gradle plugin
 -> generated tests/mappings
 -> test task/producer verification
 -> merge custom resources trước stubs Jar task
 -> publish candidate artifact
~~~

**Đây là lifecycle khái niệm**, không phải bảo đảm mọi SCC version tự chạy cùng thứ tự/phase. Khi áp dụng, kiểm reference của đúng plugin version và test output thực tế.

Một bước merge có kiểm soát cần:

1. Chạy **sau generation, trước packaging**.
2. Đọc source files đã commit, không đọc ngẫu nhiên từ workspace tạm.
3. Không ghi đè mapping generated trừ khi có quyết định công khai và được kiểm chứng.
4. Validate JSON schema, body file paths, mapping collision và priority.
5. Pin extension binary/dependency version trong classpath.
6. Tạo manifest truy nguồn contract–mapping–customization.
7. Gắn artifact candidate với producer commit và customization revision.
8. Chỉ tính digest **sau khi đóng gói đầy đủ**.
9. Chỉ publish nếu executed producer contract tests > 0 và tất cả đạt.
10. Không cho một rerun tự tải `latest` hoặc một dependency mutable khác lần đầu.

Không nên dùng generated output trong `target`/`build` làm nơi lưu thay đổi thủ công, vì clean/regenerate/build cache có thể xóa hoặc ghi đè nó.

## 37. SNAPSHOT, cache và runtime chưa cập nhật

Một timeline thường gặp:

~~~text
T1: Stub Runner nạp JAR A + extension A
T2: Developer sửa mapping và extension thành B
T3: Producer publish lại 1.4.0-SNAPSHOT
T4: Consumer test gọi WireMock server được start từ T1
T5: Response vẫn của A, test có thể PASS giả
~~~

Cần phân biệt:

- **Resolver đã tải được JAR mới, extension binary mới chưa?**
- **WireMock instance đang chạy đã load nội dung mới chưa?**

Maven `-U` và Gradle `--refresh-dependencies` có thể ảnh hưởng dependency resolution, nhưng **không mặc nhiên hot reload WireMock process**.

Khuyến nghị release gate dùng **unique candidate version** gắn producer commit và repository policy chặn overwrite. Nếu bắt buộc dùng SNAPSHOT, ghi resolved timestamped build, digest và startup time. Nếu runtime extension là dependency riêng, cũng ghi/pin **version và digest của extension**, vì JAR stub đúng mà extension khác vẫn có thể đổi behavior.

## 38. Bảo mật của WireMock customization

Một response template, request matcher hay extension có thể đọc request data và runtime config, nên cần:

- Không echo/log `Authorization`, session cookies, password, tokens hoặc PII.
- Dùng dữ liệu giả/ẩn danh trong `contracts`, mappings và `__files`.
- Giới hạn WireMock Admin API trong test network; không expose ra public không cần thiết.
- Cấm extension thực hiện file/network access không kiểm soát.
- Pin dependency versions và review extension source.
- Kiểm JSON escaping, Unicode, quote, newline, long strings.
- Tránh regex có nguy cơ tiêu thụ CPU quá mức.
- Không để global transformers/priority vượt quá phạm vi test.
- Reset scenario state giữa tests và cô lập parallel test runs.
- Sanitize request journals trước khi lưu vào CI.
- Giới hạn quyền publish stubs artifact theo owner/registry policy.

**Provenance giúp cả security lẫn debugging**: biết binary nào đã nạp, source revision nào cung cấp nó và ai phê duyệt behavior.

## 39. Case study: transformer khiến Checkout test xanh giả

### Tình huống

Inventory contract v1 trả:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Producer v2 đổi thành:

~~~json
{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

Nhóm consumer thêm transformer WireMock:

~~~text
Nếu response có inStock:
    thêm available = inStock
    bỏ inStock
~~~

Checkout v3 vẫn đọc `available` và test PASS với WireMock tùy biến. Nhưng khi deploy, **producer thật không có transformer này** và chỉ trả `inStock`, khiến Checkout v3 lỗi.

### Nguyên nhân

Consumer đang test **API mô phỏng đã được sửa body**, không phải behavior được producer verification bảo đảm. Pipeline vẫn ghi nhận “dùng đúng stubs version”, nhưng **runtime customization khác với producer code**.

### Cách khắc phục

1. Đánh giá Checkout v3 có còn thuộc danh sách được hỗ trợ không.
2. Nếu cần tương thích, producer thật nên dùng **dual-field response** trong giai đoạn chuyển đổi.
3. Sửa Groovy/YAML contract thể hiện cả `available` và `inStock`; hai nhóm review.
4. Chạy generated producer tests trên implementation thật.
5. Sinh JAR mới, **không dùng semantic rewrite** trong baseline compatibility.
6. Cho Checkout v3 chạy client thật với candidate stub mới.
7. Di chuyển consumer mới sang `inStock` rồi mới deprecate field cũ theo chính sách.
8. Nếu giữ transformer cho design/resilience test, gắn nhãn **test-only** và không dùng để tuyên bố production compatibility.

**Kết luận:** tùy biến WireMock không được dùng để che sự khác biệt giữa contract mà producer đã xác nhận và API mà consumer thật sẽ nhận.

## 40. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Contract đúng nhưng Stub Runner trả khác | Custom mapping override, JAR cũ | Resolved digest, priority, journal |
| Body có nguyên `{{...}}` | Response templating chưa bật | Mapping transformers, WireMock version |
| Transformer không chạy | Chưa đăng ký đúng instance | Classpath, startup logs |
| Local compile, CI lỗi | WireMock major version/dependency khác | Runtime version và extension API |
| JSON template bị lỗi | Input chưa escape | Negative request inputs, JSON parser |
| Request sai URL vẫn nhận 200 | Catch-all mapping | Matchers và fallback priority |
| Test đôi lúc FAIL | Stateful scenario không reset | Scenario states, parallelism |
| Producer tests PASS dù code sai | Fake controller hoặc không chạy tests | Base test, executed count, mutation |
| Missing body file | `bodyFileName`/`__files` bị đóng gói sai | `jar tf` và mapping resource |
| JAR mới nhưng response cũ | Server start trước publish | Restart và kiểm effective mappings |
| JAR đúng, behavior khác | Extension runtime khác | Extension binary/version |
| Consumer test không phát HTTP | Client bị mock hoặc port sai | Client URL và request journal |
| WireMock 404 bị nhầm business 404 | Assertion chỉ status | Error code/body và near misses |
| CI đôi lúc pass với SNAPSHOT | Cache/race publish | Exact candidate version/digest |

Thứ tự điều tra:

~~~text
Contract source/commit
 -> Generated producer tests/report
 -> Generated + custom mapping sources
 -> Extension version/registration
 -> Packaged JAR + body files
 -> Repository/consumer resolved digest
 -> Stub Runner effective mappings/scenario state
 -> Consumer real request/client URL
 -> Business assertions và CI decision
~~~

Đừng sửa contract để “cho khớp” một request client sai hay xóa cache khi nguyên nhân thật là extension không được đăng ký.

## 41. Bài thực hành A — Thêm provenance không đổi semantics

**Mục tiêu:** gắn dấu vết nguồn cho mapping.

1. Tạo producer Inventory và Groovy contract GET SKU-123 trả 200, `available:true`, `quantity:12`.
2. Sinh generated tests và WireMock mappings bằng SCC.
3. Đọc mapping thực; tạo manifest source-controlled chứa contract path, mapping name, commit và customization revision.
4. Nếu dùng metadata trong mapping, bổ sung bằng **bước build deterministic**, không sửa tay output tạm.
5. Package JAR; mở JAR kiểm mappings, metadata/manifest, body files.
6. Tính SHA-256 sau packaging; lưu sidecar digest.
7. So contract response trước/sau: không được thay status, headers và business fields.
8. Mutation producer `available:false` phải làm generated test FAIL.
9. Khôi phục code rồi chạy test lại.
10. Ghi rõ metadata là **nhãn tra cứu**, không phải bằng chứng duy nhất.

**Bằng chứng nộp:** contract, mapping/manifest, JAR listing, digest và producer test/mutation report.

## 42. Bài thực hành B — Templating/extension có giới hạn

**Mục tiêu:** thêm khả năng động mà không sửa behavior công khai ngoài contract.

1. Thảo luận xem echo `X-Correlation-Id` có phải producer public contract không.
2. Nếu có, sửa producer/DSL để verification bảo vệ behavior đó.
3. Tạo template hoặc transformer test-only chỉ thêm header chẩn đoán.
4. Pin WireMock version, compile extension và đăng ký đúng instance.
5. Thử request ID hợp lệ, thiếu header, quote/newline/Unicode, chuỗi dài.
6. Kiểm JSON escaping và không echo secrets.
7. So `sku`, `available`, `quantity` trước/sau transformer.
8. Chạy negative request tests: path sai, header sai, unexpected body.
9. Nếu consumer dùng Stub Runner, xác minh candidate JAR **và extension version** đang chạy.
10. Báo cáo riêng baseline compatibility và test harness diagnostic.

**Bằng chứng nộp:** source extension/template, runtime log, matcher test matrix, provenance và giải thích giới hạn test.

## 43. Bài thực hành C — Cô lập fault injection và priority

**Mục tiêu:** resilience mappings không che baseline mappings.

1. Sinh baseline mapping GET SKU-123 → 200.
2. Tạo test-only connection-reset/delay mappings.
3. Kích hoạt chúng bằng port/header/scenario riêng, không dùng global catch-all.
4. Đảm bảo baseline request vẫn nhận 200 từ mapping contract.
5. Gửi request bật fault; kiểm consumer retry/timeout/circuit-breaker.
6. Cố ý đặt priority fault cao để đè baseline; negative test phải báo lỗi.
7. Khôi phục priority và chạy lại cả hai suites.
8. Reset scenario states; chạy thử song song để tìm shared-state flakiness.
9. Package candidate và kiểm không có custom mapping ngoài scope.
10. Ghi riêng **baseline compatibility result** và **resilience test result**.

**Bằng chứng nộp:** mapping priority table, request journal, report và chính sách cô lập suites.

## 44. Checklist review customization trước khi merge

- [ ] Groovy/YAML contract là **nguồn chính** của hành vi HTTP/message producer cam kết.
- [ ] Mọi thay đổi semantics được review qua contract/producer implementation, không sửa riêng stub.
- [ ] Generated producer tests chạy trên code thật, count > 0 và đạt.
- [ ] Generated mappings trong `target`/`build` không bị sửa tay làm source.
- [ ] Custom mapping/transformer/matcher được commit, có owner và review.
- [ ] Extension binary/WireMock runtime versions đã pin và test compatibility.
- [ ] Mapping priority/overlap/catch-all được kiểm, không che baseline.
- [ ] Không trả success cho request không đúng contract.
- [ ] Response template dùng escaping, không echo PII/token.
- [ ] Test-only fault/scenario không bị nhầm là public producer behavior.
- [ ] Stateful WireMock scenarios được reset và cô lập.
- [ ] Transformer global chỉ bật khi chủ đích; ưu tiên per-stub opt-in.
- [ ] Extension đăng ký trên **đúng instance** mà consumer client gọi.
- [ ] Stubs JAR có mappings, `__files` và classifier đúng.
- [ ] Provenance map contract path/revision, producer commit, customization revision.
- [ ] Digest JAR tính **sau packaging**, consumer CI đối chiếu digest thật.
- [ ] Candidate version bất biến; SNAPSHOT có timestamp/checksum nếu bắt buộc.
- [ ] Consumer test dùng real client/handler, không mock giao tiếp.
- [ ] Negative/mutation tests khiến request/behavior sai làm test đỏ.
- [ ] Không nhầm unmatched 404 với contract business 404.
- [ ] Baseline và resilience suites có kết quả/ownership riêng.
- [ ] CI không đánh dấu PASS khi thiếu executed tests hoặc thiếu artifact provenance.
- [ ] Không có secret, token hay production PII trong JAR/log/test fixtures.

## 45. Câu hỏi tự kiểm tra

**1. Vì sao không sửa generated mapping trực tiếp?**

Vì nó bị regeneration ghi đè và mất liên kết với DSL/producer tests. Hãy sửa DSL hoặc dùng customization được version-control và review.

**2. Metadata `contractSource` có tự chứng minh mapping được sinh từ contract đó không?**

Không. Cần đối chiếu source revision, build inputs, JAR digest và test reports.

**3. Khi nào response templating phải được phản ánh trong contract?**

Khi behavior động (ví dụ echo correlation ID) là **cam kết công khai của producer**. Stub-only template không chứng minh producer thật có behavior đó.

**4. Vì sao transformer có thể gây xác nhận tương thích giả?**

Nó sửa stub response theo cách producer runtime không có, khiến consumer test một giao diện mô phỏng khác production.

**5. Extension đăng ký vào standalone WireMockServer có tự áp dụng cho Stub Runner không?**

Không. Hai server có thể khác instance; cần cấu hình đúng Stub Runner-managed runtime.

**6. Mapping priority số nhỏ nghĩa là gì?**

WireMock thường ưu tiên **số priority nhỏ**. Phải xác nhận mapping được chọn và không có overlap ngoài ý muốn.

**7. Connection reset có phải HTTP status 503 không?**

Không. Reset là transport fault; HTTP 503 là response có status và thường có body/headers riêng.

**8. Vì sao resilience PASS không thay baseline compatibility PASS?**

Resilience dùng fault/delay fixtures để test client failure handling, không chứng minh producer behavior đã được contract-verified.

**9. Tại sao JAR đúng version chưa chắc response đúng?**

SNAPSHOT có thể mutable, server đã load JAR cũ hoặc extension version/runtime khác. Phải kiểm digest, mapping và extension.

**10. Bằng chứng tối thiểu của một customization an toàn là gì?**

Reviewed source revision, producer generated test PASS, mapping/extension version/collision checks, JAR digest, Stub Runner nạp đúng candidate, real consumer client và negative tests.

## 46. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): producer verification, Groovy/YAML DSL và stub artifacts.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): behavior HTTP/message và matchers.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): artifact resolution và consumer compatibility.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generated tests và stubs packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle integration và publishing.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mappings, priority và response definitions.
- [WireMock — Response Templating](https://wiremock.org/docs/response-templating/): Handlebars helpers và transformer config.
- [WireMock — Extending WireMock](https://wiremock.org/docs/extending-wiremock/): extension interfaces và registration.
- [WireMock — Stateful Behaviour](https://wiremock.org/docs/stateful-behaviour/): scenario state lifecycle.
- [WireMock — Simulating Faults](https://wiremock.org/docs/simulating-faults/): delays và transport errors.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): matcher predicates, request journal, near misses.
- [Apache Maven — Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote artifact resolution.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): changing/dynamic dependencies.

**Lưu ý phiên bản:** WireMock 2/3 khác nhau về extension API, templating, helper/registration và lifecycle. SCC Stub Runner cũng có hooks/tùy biến khác nhau giữa Spring Boot–Cloud Contract versions. Code snippets là **ví dụ kỹ thuật cần đối chiếu dependency thực**, không phải lời khẳng định mọi snippet chạy nguyên văn. Paths, URLs `example.invalid`, commits và SHA trong bài chỉ minh họa. Bước biên soạn không chạy Maven/Gradle hay Content QA chuyên môn.

---

**Điểm cần nhớ:** Tùy biến WireMock hữu ích cho response động, matcher nâng cao, fault injection và scenario state, nhưng **contract DSL vẫn là nguồn của hành vi producer cam kết**. Custom mappings/extensions phải là **inputs có version và review**, không thay response công khai ở phía stub mà producer không thực thi. Dấu vết nguồn phải đi được từ **contract revision → generated mapping → customization revision → stubs JAR/digest → Stub Runner runtime → consumer client thật → test report**. Chỉ vậy khả năng mở rộng mới không làm mất giá trị kiểm thử tương thích.
