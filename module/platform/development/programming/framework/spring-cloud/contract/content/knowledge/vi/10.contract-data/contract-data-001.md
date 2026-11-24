# Thiết kế fixture đơn giản, ổn định và sát nhu cầu consumer

## Mục tiêu học tập

Trong **Spring Cloud Contract**, **producer** là dịch vụ cung cấp API hoặc phát thông điệp, còn **consumer** là bên sử dụng API hoặc nhận thông điệp đó. Hợp đồng được mô tả bằng **Groovy/YAML DSL** để sinh kiểm thử hành vi phía producer, đồng thời tạo stub cho consumer sử dụng qua **Stub Runner**.

Ở chương **Dữ liệu hợp đồng**, bài này tập trung vào một câu hỏi thực tế: **nên chọn dữ liệu mẫu (fixture) như thế nào để kiểm thử có ý nghĩa, dễ tái lập và không phụ thuộc vào những chi tiết ngẫu nhiên của môi trường?**

Sau bài học, bạn có thể:

- Phân biệt fixture, contract, dữ liệu test trong producer và response stub phía consumer.
- Chọn tập fixture **nhỏ nhưng đại diện** cho các quyết định thực tế của consumer.
- Tránh dữ liệu biến động do thời gian, UUID, thứ tự, nguồn dữ liệu bên ngoài hoặc trạng thái dùng chung.
- Biết khi nào dùng **giá trị cố định**, khi nào dùng **matcher** và cặp giá trị producer/consumer.
- Tổ chức fixture cho Groovy/YAML DSL, generated tests, Stub Runner và pipeline CI.
- Đánh giá một fixture có phản ánh đúng ngữ nghĩa API mà consumer phụ thuộc hay không.

## 1. Fixture là gì và nó đóng vai trò nào?

**Fixture** là dữ liệu mẫu có chủ đích được dùng để tạo ra hoặc kiểm chứng một tình huống kiểm thử. Trong contract testing, fixture có thể xuất hiện tại nhiều vị trí:

| Vị trí | Ví dụ | Chức năng |
|---|---|---|
| Request trong contract | `GET /api/inventory/SKU-101` | Xác định tương tác được kiểm chứng |
| Expected response trong contract | `{"sku":"SKU-101","available":true,"quantity":8}` | Cam kết hành vi producer cần đáp ứng |
| Dữ liệu nền của producer test | Bản ghi tồn kho `SKU-101` với số lượng `8` | Giúp producer thật trả kết quả theo hợp đồng |
| Stub được sinh từ contract | Response JSON ổn định cho request phù hợp | Giúp consumer kiểm tra logic gọi API và xử lý response |
| Dữ liệu assertion của consumer | “`available=true` thì cho phép tiếp tục đặt hàng” | Xác nhận consumer thực sự hiểu và sử dụng hợp đồng |

Các lớp dữ liệu này **liên quan nhưng không tự động giống nhau**. Ví dụ `SKU-101` trong contract sẽ không tự tạo hàng tồn kho trong database của producer. Nhóm producer phải thiết lập trạng thái test phù hợp; nếu không, generated test có thể trả `404` thay vì `200` dù DSL đúng.

Sơ đồ đơn giản:

~~~mermaid
flowchart TD
    C["Groovy/YAML contract<br/>request và expected response"] --> P["Generated producer test"]
    C --> S["Stub artifact"]
    D["Test data của producer<br/>SKU-101, quantity=8"] --> P
    P --> A["Producer implementation"]
    S --> R["Stub Runner"]
    R --> U["Consumer test<br/>client và logic thật"]
    A --> V{"Đáp ứng contract?"}
    U --> W{"Consumer xử lý đúng?"}
~~~

**Contract** nói hai bên đã cam kết hành vi gì; **fixture** cung cấp ví dụ cụ thể để kiểm chứng cam kết ấy; **stub** giả lập producer từ contract. Dù stub trả kết quả đúng, vẫn cần generated test với producer thật. Dù producer test xanh, consumer vẫn cần kiểm tra cách mình dùng stub.

## 2. “Đơn giản, ổn định, sát consumer” nghĩa là gì?

Một fixture hữu ích phải đạt ba tính chất cùng lúc.

### Đơn giản (minimal)

Chỉ đưa vào các trường và tình huống cần cho hành vi kiểm thử. Một JSON gồm 50 field giả có thể khiến reviewer khó thấy field nào thật sự quan trọng. Một fixture ngắn thường dễ bảo trì hơn nếu nó vẫn nêu đủ điều kiện nghiệp vụ.

Ví dụ Checkout chỉ cần:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Không nên tự thêm `warehouseManager`, `lastMaintenanceAt`, `supplierInternalCode` và nhiều field khác nếu chúng không phải là phần giao diện producer đã cam kết.

**Minimal không có nghĩa là lược bỏ field bắt buộc.** Nếu hợp đồng API yêu cầu `currency` để hiểu `price`, hãy giữ cả hai; bỏ `currency` chỉ vì fixture ngắn hơn sẽ làm mất ngữ nghĩa.

### Ổn định (deterministic)

Khi chạy cùng revision contract và cùng cấu hình test, dữ liệu phải dẫn đến **kết quả dự đoán được**, không phụ thuộc múi giờ, ngày chạy, random, dữ liệu của đồng nghiệp hoặc dịch vụ mạng.

| Dữ liệu dễ gây bất ổn | Cách chọn ổn định hơn |
|---|---|
| `LocalDateTime.now()` | Mốc thời gian test cố định hoặc matcher cho định dạng |
| UUID mới ở mỗi lần chạy | ID mẫu cố định ở stub và matcher ở producer nếu ID thật biến động |
| Chọn `findFirst()` trên tập không có thứ tự | Ấn định quy tắc sort nếu consumer dựa vào thứ tự |
| Database dùng chung giữa các test | Seed dữ liệu riêng, làm sạch và cô lập trạng thái |
| API bên ngoài đang hoạt động | Fake/mock ở ranh giới phụ thuộc hoặc môi trường test kiểm soát được |
| Tỷ giá/giá sản phẩm lấy trực tiếp từ live API | Giá trị trong dataset kiểm thử đã cố định, có quy tắc cập nhật |

Tính ổn định **không đòi producer thật phải luôn trả cùng một UUID/timestamp trong production**. Hợp đồng có thể dùng một giá trị đại diện phía stub để consumer kiểm thử dễ dàng, đồng thời dùng matcher ở phía producer để chấp nhận giá trị hợp lệ có thể thay đổi.

### Sát nhu cầu consumer (consumer-relevant)

Mỗi fixture nên gắn với **một nhánh quyết định** của consumer:

- `available=true`, `quantity > 0` → có thể cho người dùng tiếp tục.
- `available=false`, `quantity=0` → hiển thị thông báo hết hàng.
- Sản phẩm không tồn tại → xử lý `404` và mã lỗi `SKU_NOT_FOUND`.
- Request sai định dạng → xử lý `400` với mã lỗi validation.

Nếu hai fixture chỉ khác mã sản phẩm, nhưng consumer xử lý y hệt và không có khác biệt nghiệp vụ, thường không cần giữ cả hai.

## 3. Ví dụ xuyên suốt: Checkout và Inventory

**Inventory Service** là producer của endpoint:

~~~http
GET /api/inventory/{sku}
Accept: application/json
~~~

**Checkout Service** là consumer. Nhóm Checkout đưa ra các câu hỏi cần kiểm chứng:

1. Nếu hàng còn, có thể tiếp tục bước xác nhận đơn không?
2. Nếu số lượng bằng 0, có hiển thị trạng thái hết hàng thay vì báo lỗi mạng không?
3. Nếu mã SKU không tồn tại, có phân biệt được `404` với danh sách trống không?
4. Nếu SKU sai định dạng, có nhận ra lỗi đầu vào `400` không?

Ta đề xuất **ma trận fixture nhỏ**:

| Mã tình huống | Request | HTTP status | Response chủ chốt | Nhánh consumer |
|---|---|---|---|---|
| `stock-available` | `GET /api/inventory/SKU-101` | `200` | `available: true`, `quantity: 8` | Cho phép tiếp tục |
| `stock-empty` | `GET /api/inventory/SKU-EMPTY` | `200` | `available: false`, `quantity: 0` | Báo hết hàng |
| `sku-not-found` | `GET /api/inventory/SKU-404` | `404` | `code: SKU_NOT_FOUND` | Xử lý không tìm thấy |
| `invalid-sku` | `GET /api/inventory/INVALID!` | `400` | `code: INVALID_SKU` | Xử lý mã nhập không hợp lệ |

Mã SKU, số lượng và quy tắc validation ở trên là **quy ước minh họa** của hai nhóm. Các quy tắc đó phải được thống nhất trước; Spring Cloud Contract không tự quyết định sản phẩm nào “còn hàng”.

### Fixture cho “còn hàng”

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Ta chọn `8` để minh họa số lượng dương. Nếu consumer chỉ cần boolean `available` và không phụ thuộc số lượng cụ thể, không nên viết logic test “phải đúng 8” ở mọi chỗ. Ngược lại, nếu Checkout phải kiểm tra không cho mua quá `quantity`, consumer test cần dùng chính số `8` để thử giới hạn, chẳng hạn đặt `9` món phải bị chặn ở tầng ứng dụng.

### Fixture cho “hết hàng”

~~~json
{
  "sku": "SKU-EMPTY",
  "available": false,
  "quantity": 0
}
~~~

**Không** dùng một fixture mâu thuẫn như `available: true` nhưng `quantity: 0` nếu API định nghĩa `available` dựa vào số lượng > 0. Những fixture thiếu nhất quán khiến test thông qua hoặc thất bại theo hành vi sai.

### Fixture cho lỗi

~~~json
{
  "code": "SKU_NOT_FOUND",
  "message": "SKU does not exist"
}
~~~

Consumer nên phân nhánh bằng **status** và **mã lỗi ổn định** (`SKU_NOT_FOUND`), không dựa vào toàn bộ câu `message`. Nếu message có thể dịch ngôn ngữ hoặc thay đổi, dùng matcher/kiểm tra riêng cho cấu trúc phù hợp; đừng biến câu chữ thành cam kết nếu không cần.

## 4. Viết fixture thành một contract Groovy đơn giản

Giả sử producer đã tích hợp Spring Cloud Contract Verifier. Ta viết một file đại diện cho trường hợp `stock-available` tại `src/test/resources/contracts/inventory/stockAvailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Con hang cho SKU-101'

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
            quantity: 8
        )
    }
}
~~~

Những điểm cần chú ý:

- `method`, `url` và `Accept` là các điều kiện consumer gửi.
- `status`, `Content-Type` và ba trường body là hành vi producer cam kết.
- `quantity: 8` là **số**, `available: true` là **boolean**, `sku` là **string**.
- Đây là **một tình huống cụ thể**, chưa bao phủ tất cả SKU hoặc mọi số lượng.

Spring Cloud Contract sinh **producer contract test** từ DSL và tạo **stub** phù hợp. Để generated test chạy, producer cần xây dựng môi trường test có dữ liệu `SKU-101`. Chỉ thêm file Groovy không tự seed database.

### Khi giữ giá trị cố định là hợp lý

Giữ giá trị phản hồi cố định là lựa chọn tốt khi:

- Fixture dùng riêng cho một tình huống đã định danh, ví dụ `SKU-101`.
- Producer test **kiểm soát được trạng thái** và phải chứng minh hành vi trả đúng số lượng `8`.
- Consumer cần một response đại diện dễ đoán để test luồng của chính mình.

Nếu quantity thực tế được tính từ nguồn không kiểm soát và không thể tái lập, hãy ưu tiên cô lập phụ thuộc hoặc dùng matcher phù hợp cho phần có thể thay đổi. Đừng chỉ thay `8` bằng `.*` vì làm vậy có thể mất kiểm tra kiểu dữ liệu và quy tắc nghiệp vụ.

## 5. YAML DSL: cùng fixture, không cần nhân đôi hợp đồng

Spring Cloud Contract cũng hỗ trợ **YAML DSL**. Đây là cách viết thay thế cho cùng tình huống, ví dụ `stockAvailable.yml`:

~~~yaml
description: 'Con hang cho SKU-101'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 8
~~~

YAML này tương đương về ý định với Groovy DSL phía trên. **Trong một build thực tế, chọn một trong hai định dạng cho tình huống đó**; không đặt cả `stockAvailable.groovy` lẫn `stockAvailable.yml` như hai contract độc lập cho cùng request chỉ để thử cú pháp, vì có thể tạo các stub mapping trùng và tăng chi phí bảo trì.

### Lưu ý các kiểu YAML dễ gây sai fixture

~~~yaml
# Đúng khi quantity là number và available là boolean.
body:
  sku: '00123'
  quantity: 8
  available: true
~~~

~~~yaml
# Sai kiểu nếu hợp đồng yêu cầu number và boolean.
body:
  sku: '00123'
  quantity: '8'
  available: 'true'
~~~

Các giá trị trong đoạn thứ hai **đều là string**. Một test chỉ so sánh văn bản hiển thị dễ bỏ sót khác biệt; contract phải bảo vệ kiểu dữ liệu mà consumer giải mã. Với mã SKU có số 0 đầu, luôn quote nếu cần giữ giá trị là string nguyên vẹn.

### Dữ liệu rỗng không đồng nghĩa với dữ liệu lỗi

Một API trả **danh sách** có thể công bố `200 OK` và JSON array rỗng khi không có kết quả. Khi đó:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body: []
~~~

`body: []` biểu diễn mảng rỗng. Nó khác `body: {}` (object rỗng), `body: null`, chuỗi `'[]'` và response `204 No Content`. Fixture cần đúng **shape** mà consumer thực sự parse; thay thế một kiểu bằng kiểu khác chỉ vì “đều rỗng” có thể làm consumer hỏng.

## 6. Fixture không chỉ là response: chuẩn bị trạng thái producer test

Một nguồn lỗi phổ biến: contract quy định `SKU-101` trả `200` nhưng khi generated test chạy, database trống nên producer thật trả `404`.

Cần thiết kế cả **dữ liệu nền** và **điều kiện test**:

| Contract | Trạng thái producer phải có trước test | Kết quả cần kiểm chứng |
|---|---|---|
| `stock-available` | SKU-101 tồn kho 8, có thể bán | `200`, `available=true`, `quantity=8` |
| `stock-empty` | SKU-EMPTY tồn kho 0 | `200`, `available=false`, `quantity=0` |
| `sku-not-found` | SKU-404 **không** tồn tại | `404`, `code=SKU_NOT_FOUND` |
| `invalid-sku` | Validation từ chối ký tự `!` | `400`, `code=INVALID_SKU` |

Tùy kiến trúc dự án, có thể seed vào database test, dùng repository giả hoặc mock tầng phụ thuộc. Spring Cloud Contract sinh test giao diện, **không tự tạo toàn bộ trạng thái ứng dụng**.

### Minh họa chuẩn bị trạng thái

Ví dụ giả mã Java, **không phải lớp cơ sở hoàn chỉnh có thể chạy ngay**:

~~~java
// Minh họa ý tưởng trong phần setup của producer test.
@BeforeEach
void setUp() {
    inventoryRepository.clearTestData();
    inventoryRepository.save(
        new StockItem("SKU-101", true, 8)
    );
    inventoryRepository.save(
        new StockItem("SKU-EMPTY", false, 0)
    );
    // Chủ ý không tạo SKU-404.
}
~~~

Trong ứng dụng thật, `clearTestData()` và `StockItem` phụ thuộc thiết kế repository/domain. Đoạn giả mã nhằm mô tả **thứ tự chuẩn bị dữ liệu**, không yêu cầu tạo các API đó. Dùng database hoặc fake chuyên dụng cho test; không thực hiện xóa dữ liệu trên database đang phục vụ người dùng.

Các nguyên tắc khi setup fixture:

1. **Cô lập:** test không phụ thuộc thứ tự chạy hay dữ liệu do test khác để lại.
2. **Tái lập:** mỗi lần test nhận cùng dữ liệu đầu vào và trạng thái mong đợi.
3. **Có chủ đích:** test `404` phải chắc chắn SKU tương ứng không tồn tại.
4. **Tường minh:** nếu test dựa vào inventory mock, cần ghi rõ mock trả gì.
5. **Dọn dẹp:** transaction rollback, reset fake, khởi tạo lại dataset hoặc cơ chế phù hợp để tránh ô nhiễm giữa test.

Nếu test chạy song song, dùng cùng một database hay fake mutable có thể tạo race condition. Hãy thiết kế cơ chế isolation phù hợp; chỉ chạy tuần tự là biện pháp tạm thời khi chưa sửa được nguồn chia sẻ trạng thái.

## 7. Dữ liệu động: phân biệt ví dụ cụ thể và quy tắc cần kiểm chứng

Không phải field nào cũng nên cố định trong producer test. Ví dụ response khi tạo đơn đặt trước:

~~~json
{
  "reservationId": "RSV-1001",
  "accepted": true
}
~~~

`reservationId` thường do hệ thống sinh. Producer có thể tạo `RSV-1002` ở lần khác nhưng vẫn đúng giao diện, trong khi consumer cần một giá trị **cụ thể** để thử lưu/hiển thị ID.

Spring Cloud Contract hỗ trợ **giá trị khác nhau giữa phía consumer và producer** trong Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tao yeu cau dat truoc hop le'

    request {
        method 'POST'
        url '/api/reservations'
        headers {
            contentType(applicationJson())
        }
        body(
            requestId: $(
                consumer(regex('REQ-[0-9]{4}')),
                producer('REQ-1001')
            ),
            sku: 'SKU-101',
            quantity: 1
        )
    }

    response {
        status 202
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: $(
                consumer('RSV-1001'),
                producer(regex('RSV-[0-9]+'))
            ),
            accepted: true
        )
    }
}
~~~

**Cách hiểu đúng theo từng phía:**

| Vị trí | Phía consumer/stub | Phía producer/generated test |
|---|---|---|
| `request.requestId` | Stub chấp nhận ID khớp `REQ-[0-9]{4}` | Generated test gửi request có `REQ-1001` thật |
| `response.reservationId` | Stub trả **giá trị cụ thể** `RSV-1001` để consumer test sử dụng | Generated test chấp nhận ID khớp `RSV-[0-9]+` |
| `response.accepted` | Stub trả boolean `true` | Producer phải trả boolean `true` |

Tên `consumer(...)` và `producer(...)` ở đây chỉ **hai góc nhìn về giá trị kiểm thử**. Với request, consumer cần quy tắc để stub nhận những ID hợp lệ; producer cần một giá trị mẫu để generated test thực sự gửi đi. Với response, producer cần quy tắc xác nhận ID động; consumer cần kết quả cụ thể để test.

**Chú ý:** cặp giá trị `$(consumer(...), producer(...))` và regex như trên là cú pháp của **Groovy DSL**. Trong **YAML DSL**, các giá trị động được cấu hình ở phần `matchers` theo schema YAML, không copy nguyên cú pháp Groovy vào YAML.

### Matcher riêng cho YAML

Nếu producer trả một field động nhưng cần đảm bảo định dạng, có thể dùng `response.matchers.body`:

~~~yaml
description: 'Kiem tra reservationId co dinh dang hop le'
request:
  method: GET
  url: '/api/reservations/RSV-1001'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    reservationId: 'RSV-1001'
    status: 'ACCEPTED'
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

Body cung cấp **một giá trị mẫu hợp lệ** để stub có thể trả cho consumer. Matcher bảo vệ quy tắc ở generated producer test. Đừng đặt một matcher `.*` cho mọi field: làm vậy có thể bỏ lọt response không đúng kiểu hoặc dữ liệu không có giá trị.

### Matcher không thay thế mọi ràng buộc nghiệp vụ

Giả sử producer trả:

~~~json
{
  "available": true,
  "quantity": 0
}
~~~

Matcher `quantity` là số nguyên vẫn có thể chấp nhận `0`, nhưng nếu nghiệp vụ quy định `available=true` chỉ khi `quantity > 0`, dữ liệu này vẫn **mâu thuẫn về ngữ nghĩa**. Cần contract hoặc kiểm thử nghiệp vụ bổ sung chứng minh mối quan hệ đó.

## 8. Chọn mức độ cố định của fixture theo nhu cầu

Một nguyên tắc hữu ích là: **cố định dữ liệu quan trọng với quyết định của consumer; dùng matcher cho phần biến động nhưng vẫn có quy tắc rõ ràng**.

| Field | Ví dụ fixture | Đề xuất | Vì sao |
|---|---|---|---|
| `sku` trong tình huống có hàng | `SKU-101` | Cố định | Tình huống cần định danh rõ ràng |
| `available` | `true` | Cố định hoặc kiểm tra boolean kèm ngữ nghĩa | Consumer phân nhánh theo giá trị |
| `quantity` | `8` | Cố định khi kiểm soát dữ liệu test; bổ sung test điều kiện nếu cần | Dễ thử ranh giới số lượng |
| `reservationId` sinh tự động | `RSV-1001` trên stub | Producer dùng matcher định dạng | Tránh test lỗi vì ID thay đổi hợp lệ |
| `timestamp` | `2026-01-15T08:00:00Z` | Cố định ở stub; matcher/clock test ở producer | Tránh phụ thuộc thời điểm chạy |
| `message` của lỗi | `SKU does not exist` | Chỉ cố định khi API cam kết chính xác câu chữ | Consumer nên xử lý `code` |
| `correlationId` | `corr-1001` | Matcher định dạng hoặc kiểm tra tồn tại/kiểu | Giá trị được sinh mỗi request |
| `tags` là array | `["featured"]` | Chọn đúng cấu trúc; chỉ kiểm tra thứ tự nếu có cam kết | Không ràng buộc thứ tự ngoài ý muốn |

Nếu người viết không biết consumer có phụ thuộc vào `quantity` hay không, nên hỏi rõ **consumer dùng nó để làm gì** trước khi quyết định fixture và matcher. Tránh tự coi mọi trường là dữ liệu “không quan trọng”.

### Thời gian, UUID và số ngẫu nhiên

Không nên đặt trực tiếp `new Date()`, `UUID.randomUUID()` hoặc `System.currentTimeMillis()` vào file hợp đồng với mục đích có kết quả khác nhau mỗi lần. Điều đó làm snapshot, test và stub khó tái lập.

Các phương án thực tế:

- **Đóng băng clock** ở producer test nếu thời gian là một phần của hành vi cần chứng minh.
- **Dùng regex/matcher** cho ID/timestamp do producer sinh, trong khi stub trả một giá trị mẫu cụ thể.
- **Đặt rõ múi giờ và định dạng** (`ISO-8601`, offset, độ chính xác) nếu consumer phụ thuộc chúng.
- **Dùng một seed cố định** cho random nếu thật sự cần dữ liệu giả có tính đa dạng mà vẫn tái lập được.
- **Tránh suy thời gian từ môi trường CI** trong expected body.

Regex kiểm tra định dạng có thể vẫn chưa đủ để chứng minh thời gian hợp lệ theo lịch thực tế hoặc quan hệ thứ tự `createdAt <= expiresAt`. Nếu consumer cần ngữ nghĩa đó, phải có kiểm thử bổ sung.

## 9. Quản lý fixture trong file ngoài khi hợp lý

Khi JSON/XML body dài hoặc được dùng bởi nhiều công cụ, có thể tách nội dung ra file fixture. Spring Cloud Contract có cơ chế đọc body từ file:

| Dữ liệu | Groovy DSL | YAML DSL |
|---|---|---|
| File văn bản/JSON/XML | `body(file('stock-response.json'))` | `bodyFromFile: 'stock-response.json'` |
| File nhị phân cần bảo toàn byte | `body(fileAsBytes('sample.pdf'))` | `bodyFromFileAsBytes: 'sample.pdf'` |

Ví dụ cách tổ chức ở producer:

~~~text
src/test/resources/contracts/inventory/
├── stockAvailable.groovy
├── stockEmpty.groovy
├── stockNotFound.yml
└── fixtures/
    ├── stock-available.json
    └── stock-empty.json
~~~

Nếu một contract Groovy tại thư mục `inventory` tham chiếu file `fixtures/stock-available.json`, ví dụ:

~~~groovy
response {
    status 200
    headers {
        contentType(applicationJson())
    }
    body(file('fixtures/stock-available.json'))
}
~~~

Ví dụ YAML **thay thế** cho cùng cách tham chiếu (không cần tạo hai contract trùng):

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  bodyFromFile: 'fixtures/stock-available.json'
~~~

Các đường dẫn trên là ví dụ **để người học tự bố trí tệp**, không phải tệp được sinh tự động. Cần bảo đảm fixture file thật sự tồn tại trong nguồn của build, đường dẫn tương đối được giải quyết đúng theo plugin và file được commit cùng contract.

### Khi nào nên đặt inline, khi nào nên tách file?

- **Inline** khi response ngắn, 2–5 field và ý nghĩa có thể đọc ngay trong DSL.
- **Tách file** khi có XML/JSON dài, nội dung văn bản lớn hoặc file binary.
- **Không tách file chỉ vì mọi contract đều phải có folder fixtures**; quá nhiều file nhỏ làm reviewer khó đối chiếu request và expected response.
- Nếu nhiều contract dùng chung một file, thay đổi file dùng chung có thể ảnh hưởng **nhiều hành vi**. Kiểm tra tất cả nơi tham chiếu trước khi sửa.
- Với binary fixture, dùng `fileAsBytes` / `bodyFromFileAsBytes` để bảo toàn byte, không chuyển dữ liệu nhị phân thành String.

Tách fixture ra file không thay thế việc định nghĩa status, header, matcher và ý nghĩa nghiệp vụ trong contract.

## 10. Nguyên tắc đặt tên và tổ chức tình huống

Tên fixture nên biểu thị **hành vi**, không chỉ là một số thứ tự:

~~~text
Nên dùng:
  stockAvailable.groovy
  stockEmpty.groovy
  stockNotFound.yml
  invalidSku.yml

Khó hiểu:
  test1.groovy
  contract2.yml
  data-final-new.json
~~~

Một cấu trúc thư mục tốt giúp tìm theo loại API hoặc hành vi, nhưng phải giữ đúng **layout mà Spring Cloud Contract plugin được cấu hình để đọc**. Không nên tự suy rằng mọi folder tùy ý đều được plugin phát hiện.

Đối với mỗi tình huống, hãy ghi ngắn gọn:

- Consumer nào và luồng nghiệp vụ nào sử dụng?
- Request cụ thể và điều kiện match stub là gì?
- Producer cần setup trạng thái nào?
- Response nào là phần **cam kết**, field nào chỉ là dữ liệu minh họa?
- Nếu có thay đổi, cần thông báo nhóm nào và chạy consumer test nào?

Những thông tin này có thể đặt ở `description`, mô tả PR hoặc tài liệu nhóm tùy quy mô, không cần nhân bản thông tin ở nhiều nơi.

### Đảm bảo các stub mapping không mơ hồ

Hai contract với **cùng method, path, header và điều kiện request** nhưng trả response khác nhau sẽ tạo ra tình huống stub khó dự đoán nếu chúng cùng khớp một request.

Ví dụ nếu cả `stockAvailable.groovy` và `stockEmpty.groovy` đều mô tả `GET /api/inventory/SKU-101` mà không có điều kiện phân biệt trạng thái, stub **không thể tự biết** nên trả `available=true` hay `false`.

Để tránh chồng lấn:

1. Tách request bằng ID/parameter/header có ý nghĩa nghiệp vụ hoặc điều kiện match phù hợp.
2. Nếu cùng một request có kết quả phụ thuộc trạng thái, cần thiết kế trạng thái stub có chủ đích hoặc dùng tình huống khác cho từng nhánh; không mặc định stub “nhớ” thay đổi tồn kho.
3. Rà soát độ ưu tiên mapping chỉ khi quy tắc DSL/Stub Runner hỗ trợ và nhóm đã thống nhất.
4. Kiểm tra consumer test có gọi đúng tình huống, không vô tình match stub khác.

## 11. Fixture cho messaging có gì khác?

Với sự kiện `StockChanged`, producer có thể phát payload:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 0
}
~~~

Consumer đăng ký nhận sự kiện này có thể cập nhật giao diện “hết hàng”. Fixture message cần mô tả:

| Khía cạnh | Ví dụ | Vì sao cần |
|---|---|---|
| Loại sự kiện | `StockChanged` | Consumer chọn đúng handler |
| Khóa định danh | `SKU-101` | Xác định đối tượng bị thay đổi |
| Giá trị mới | `quantity: 0` | Kiểm tra nhánh hết hàng |
| Header/metadata quan trọng | Event type, content type, phiên bản schema nếu API cam kết | Kiểm tra việc định tuyến/giải mã |
| Event ID/timestamp | Mẫu cố định hoặc matcher | Cho phép dữ liệu động nhưng giữ tính kiểm chứng |

Không cần sinh hàng chục sự kiện ngẫu nhiên để chứng minh một handler đã xử lý trường `quantity=0`. Nhưng nếu consumer cần **idempotency**, xử lý **trùng sự kiện**, **sai thứ tự** hoặc **sự kiện được phát lại**, phải có test riêng cho hành vi đó.

Một hợp đồng message đơn lẻ không tự chứng minh broker cung cấp bảo đảm về thứ tự, retry hoặc giao ít nhất một lần. Điều này thuộc cấu hình broker và thiết kế ứng dụng, cần kiểm tra độc lập khi nghiệp vụ phụ thuộc.

## 12. Những lỗi thiết kế fixture thường gặp

| Lỗi | Dấu hiệu | Cách sửa |
|---|---|---|
| Chọn bản ghi ngẫu nhiên từ database | Lúc test xanh, lúc `404` | Seed SKU cố định hoặc fake/repository test |
| Dùng thời gian thật trong expected response | Test lỗi theo giờ, múi giờ, ngày | Clock cố định hoặc matcher định dạng |
| Fixture quá lớn | Reviewer không biết trường nào quan trọng | Giữ dữ liệu vừa đủ cho nhánh consumer |
| Fixture quá nghèo | Chỉ có `status: 200` dù consumer cần `available` | Mô tả field/kiểu/ngữ nghĩa mà consumer phụ thuộc |
| Fixture mâu thuẫn nghiệp vụ | `available=true` nhưng `quantity=0` | Định nghĩa bất biến và tạo bộ giá trị nhất quán |
| Trộn lỗi với dữ liệu rỗng | `404` cho truy vấn danh sách hợp lệ khi đã cam kết `200 []` | Tách nhánh không có kết quả với lỗi tài nguyên |
| Quote sai kiểu YAML | `quantity: '8'` thành string | Giữ đúng kiểu number/boolean/string |
| Regex quá rộng | `.*` cho ID, trạng thái, giá trị | Matcher phản ánh đúng quy tắc hợp đồng |
| Mock producer nhưng không chứng minh hành vi HTTP | Test chỉ xác nhận stub đúng với chính nó | Chạy generated test trên tầng producer được cấu hình phù hợp |
| Consumer test dùng stub cũ | Test xanh, API mới vẫn phá vỡ | Ghim và đồng bộ phiên bản candidate stub |
| Chia sẻ fixture mutable giữa test | Test lỗi phụ thuộc thứ tự hoặc chạy song song | Reset/rollback/cô lập trạng thái |
| Sử dụng dữ liệu khách hàng thật | Có nguy cơ lộ thông tin, khó tái lập | Dữ liệu tổng hợp, không chứa bí mật hoặc thông tin cá nhân |

Một fixture ít trường hơn nhưng đúng với **quyết định của consumer** thường tốt hơn một snapshot lớn sao chép ngẫu nhiên từ database production.

## 13. Đưa kiểm chứng fixture vào CI

Lý tưởng nhất, mỗi thay đổi contract đều có đường truy vết từ dữ liệu mẫu đến test hai phía:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / CI
    participant K as Contract + fixture
    participant P as Producer tests
    participant A as Stub artifact
    participant U as Consumer tests
    Dev->>K: Thay đổi Groovy/YAML và dữ liệu mẫu
    K->>P: Sinh generated tests
    P->>P: Seed trạng thái và gọi producer
    alt Producer test đạt
        P-->>A: Đóng gói stub cùng revision
        A-->>U: Stub Runner tải đúng phiên bản
        U->>U: Test hành vi consumer với response mẫu
    else Producer test lỗi
        P-->>Dev: Kiểm tra fixture, contract hoặc implementation
    end
~~~

Các cổng kiểm tra nên có:

1. **Kiểm tra DSL:** hợp đồng Groovy/YAML parse được, matcher tham chiếu đến field hợp lệ, file fixture tồn tại và được đưa vào build.
2. **Generated producer tests:** ứng dụng producer được dựng với trạng thái test xác định; các test phải kiểm tra status, header, body theo hợp đồng.
3. **Candidate stub:** stub được tạo từ **cùng revision** contract đã được producer kiểm chứng; artifact gắn version có thể truy vết.
4. **Consumer tests với Stub Runner:** consumer gọi stub qua HTTP client thực của mình và kiểm tra quyết định khi còn hàng, hết hàng, không tìm thấy hoặc request lỗi.
5. **Compatibility review:** nếu thay đổi kiểu hoặc ngữ nghĩa dữ liệu, cần đánh giá consumer cũ đang sử dụng stub/contract nào.

**Cảnh báo:** producer tests có thể xanh nếu cả contract lẫn implementation cùng thay đổi theo hướng phá vỡ consumer cũ. CI cần kết hợp test consumer, danh bạ phụ thuộc và quản lý phiên bản stub; một mình việc sinh test thành công chưa đủ để chứng minh tương thích.

Một báo cáo build hữu ích nên ghi rõ:

- Revision/commit của contract và fixture.
- Commit của producer và kết quả generated tests.
- Tọa độ/version artifact stub.
- Commit consumer và test đã chạy với version stub đó.
- Các trường hợp chưa được bao phủ hoặc cần migration.

## 14. Bài thực hành: rút gọn một fixture rối

Đề bài: Checkout chỉ cần biết SKU nào còn hàng, số lượng tối đa có thể đặt và cách xử lý khi sản phẩm không tồn tại. Một nhóm đề xuất fixture sau:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8,
  "lastUpdated": "NOW",
  "requestId": "random-each-run",
  "warehouseManager": "Example Person",
  "supplierPhone": "000-000-0000",
  "internalCacheKey": "stock-live-101",
  "supplierCategory": "X",
  "debugFlag": "internal"
}
~~~

**Câu hỏi 1:** Field nào có thể loại bỏ khỏi contract nếu không thuộc API đã công bố và consumer không cần?  
**Gợi ý:** `warehouseManager`, `supplierPhone`, `internalCacheKey`, `supplierCategory`, `debugFlag` là ứng viên rõ ràng; không quyết định xóa khỏi API chỉ bằng việc sửa fixture mà chưa thống nhất với chủ sở hữu giao diện.

**Câu hỏi 2:** `lastUpdated` và `requestId` nên xử lý thế nào?  
**Gợi ý:** Nếu consumer cần các field này, dùng giá trị mẫu cụ thể ở stub và matcher/clock kiểm soát ở producer; nếu hoàn toàn không thuộc hợp đồng công bố, không thêm chỉ để fixture “trông giống production”.

**Câu hỏi 3:** Cần thêm fixture nào?  
**Gợi ý:** Tối thiểu `SKU-EMPTY` với `available=false`, `quantity=0` và `SKU-404` trả `404` với mã lỗi `SKU_NOT_FOUND`. Nếu quy tắc cho phép đặt số lượng lớn hơn tồn kho, thêm kiểm thử consumer dùng quantity dương để thử trường hợp vượt giới hạn.

**Câu hỏi 4:** Làm sao biết thay đổi không phá vỡ consumer?  
**Gợi ý:** Chạy generated producer tests và consumer test với **candidate stub** cùng revision, đồng thời rà soát những consumer khác và phiên bản đang triển khai.

### Tự kiểm tra

- Fixture, contract và stub khác nhau ở đâu?
- Vì sao test producer cần trạng thái dữ liệu nền riêng dù đã có JSON mẫu trong DSL?
- Khi nào nên cố định `quantity=8`, khi nào nên dùng matcher?
- Tại sao một fixture `available=true`, `quantity=0` có thể tạo cảm giác “test xanh” nhưng sai nghiệp vụ?
- Vì sao matcher trong request và response có vai trò khác nhau giữa consumer và producer?
- Khi nào tách `bodyFromFile` sẽ tốt hơn body inline?
- Tại sao hai stub mapping giống điều kiện request nhưng khác response có thể gây lỗi khó dự đoán?
- Những dữ kiện nào cần gắn vào CI để truy vết artifact stub?

## 15. Tham khảo và ghi nhớ

Tài liệu chính thức Spring Cloud Contract:

- [How Can I Provide Dynamic Values to a Contract?](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-provide-dynamic-values.html): giải thích vì sao request/response cần giá trị mẫu và matcher theo từng phía.
- [Dynamic properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): cặp `consumer/producer` trong Groovy DSL và phần `matchers` cho YAML.
- [YML Schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html): cấu trúc các trường hợp đồng YAML được công cụ hỗ trợ.

**Fixture tốt là một ví dụ có chủ đích về hành vi mà consumer phụ thuộc.** Dữ liệu cần đủ nhỏ để hiểu, đủ ổn định để test tái lập và đủ thực tế để kiểm tra các nhánh quan trọng. Khi giá trị do producer sinh có thể biến động, Spring Cloud Contract cho phép kết hợp **ví dụ cố định phía stub** với **matcher phía generated test**. Producer cần setup trạng thái tương ứng; consumer cần test logic với đúng artifact stub; CI phải gắn hai kết quả vào cùng phiên bản hợp đồng để phát hiện sớm thay đổi API hoặc thông điệp không tương thích.
