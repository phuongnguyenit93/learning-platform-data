# Kiểm tra nhu cầu consumer đã được phản ánh trong hợp đồng

## 1. Tại sao contract đúng cú pháp vẫn có thể thiếu nhu cầu consumer?

Trong một hệ thống microservices, **consumer** cần hành vi công khai từ **producer** để hoàn thành tác vụ của mình. Spring Cloud Contract hỗ trợ mô tả các tương tác HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh kiểm thử phía producer, tạo stub, dùng **Stub Runner** cho kiểm thử consumer và tích hợp CI nhằm phát hiện thay đổi API không tương thích.

Tuy nhiên, **một contract hợp lệ về cú pháp không có nghĩa nó bảo vệ đầy đủ điều consumer cần**.

Ví dụ Checkout Service (consumer) gọi Inventory Service (producer) để quyết định có cho khách đặt mua ba sản phẩm hay không:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Producer có thể định nghĩa contract chỉ kiểm tra:

~~~json
{
  "sku": "SKU-100"
}
~~~

Contract đó có thể được sinh thành test và chạy xanh. Nhưng Checkout thực tế cần biết:

- `available` có phải boolean để quyết định còn hàng không?
- `quantity` có phải number để so sánh với số lượng đặt không?
- Nếu mã SKU **không tồn tại**, producer trả status và error code nào?
- Nếu response là `404`, Checkout có hiển thị đúng thông báo hay có cố tạo đơn hàng?
- Trường `quantity` có bao giờ được trả `null` hoặc bị lược bỏ không?

Nếu những điều này chưa được phản ánh vào hợp đồng và kiểm thử, cả producer lẫn consumer có thể đều báo test xanh trong khi thay đổi dữ liệu vẫn làm ứng dụng hỏng.

**Mục tiêu của bài:** Xác minh rằng những nhu cầu thực sự của consumer đã được chuyển thành **những lời cam kết quan sát được**, được kiểm tra ở cả phía producer và consumer, không chỉ tồn tại dưới dạng mô tả trong tài liệu.

### Sau bài học, bạn có thể

1. Thu thập và phân loại nhu cầu consumer theo request, response, lỗi và thông điệp.
2. Lập bảng truy vết từ nhu cầu nghiệp vụ tới contract, assertion và consumer test.
3. Đọc Groovy/YAML DSL để phát hiện thiếu status, header, field, kiểu JSON hoặc nhánh lỗi.
4. Chọn matcher đủ linh hoạt cho dữ liệu động nhưng đủ chặt với các mã và field quan trọng.
5. Phân biệt generated producer verification với consumer tests sử dụng stub.
6. Xác minh consumer client gọi **đúng request** và xử lý **đúng response**.
7. Nhận diện những khoảng trống trong contract review, versioning và CI.
8. Thiết kế bài thực hành và checklist trước khi chấp nhận một hợp đồng.

> **Nguyên tắc:** Đừng bắt đầu bằng câu “Producer đang trả gì?”. Hãy bắt đầu bằng câu **“Consumer phải đưa ra quyết định gì, và cần quan sát những tín hiệu nào để quyết định đó đúng?”**

## 2. Ba lớp cần khớp: nhu cầu, hợp đồng và thực thi

Một nhu cầu consumer thường bắt đầu từ một use case. Ví dụ: Checkout Service chỉ cho phép đặt hàng nếu tồn kho ít nhất bằng số lượng khách muốn mua.

Từ use case này, ta cần ít nhất ba lớp:

| Lớp | Câu hỏi | Minh họa |
| --- | --- | --- |
| **Nhu cầu consumer** | Consumer cần dữ liệu/hành vi gì để ra quyết định? | `available` và `quantity`, cùng tình huống không tìm thấy SKU |
| **Contract** | Giao diện công khai đã cam kết điều gì? | `GET /api/inventory/{sku}`, HTTP `200`, boolean `available`, number `quantity`, lỗi `404` |
| **Kiểm thử thực thi** | Bên nào xác minh điều gì? | Producer generated tests kiểm tra API thật; consumer tests qua Stub Runner kiểm tra client và use case |

Luồng:

~~~mermaid
flowchart TD
    A["Use case consumer"] --> B["Nhu cầu có thể quan sát tại API"]
    B --> C["Groovy/YAML contract"]
    C --> D["Generated producer tests"]
    C --> E["Stub mappings"]
    D --> F["Producer verification đạt"]
    E --> G["Stub Runner khởi động stubs"]
    G --> H["Consumer code gửi request"]
    H --> I["Assertions về hành vi consumer"]
    F --> J["Phiên bản stub được duyệt cho CI"]
    I --> J
~~~

Đây là một **vòng xác minh hai phía**:

- Nếu producer đổi JSON number thành String trong một trường đã được contract ràng buộc, **producer test** nên phát hiện mismatch.
- Nếu consumer gửi sai path/header hoặc đọc sai JSON, **consumer test với stub** nên phát hiện.
- Nếu nhu cầu chưa được viết vào **contract hoặc consumer test**, không có cơ chế nào tự động bảo vệ nó.

### 2.1. Contract không có chức năng đoán nhu cầu

Spring Cloud Contract **không đọc code consumer để tự suy ra mọi business requirement**. Việc chọn status, field, matcher, request case và những lỗi cần bảo vệ vẫn là trách nhiệm phối hợp của người thiết kế API, producer và consumer.

Generated tests chỉ kiểm chứng những gì DSL biểu đạt theo cơ chế generation. Nếu DSL bỏ `quantity`, không thể mặc định generated test sẽ cảnh báo producer bỏ field đó.

## 3. Thu thập nhu cầu từ hành vi consumer, không chỉ từ endpoint

Giả sử một phương thức trong Checkout:

~~~java
public boolean canPlaceOrder(String sku, int requestedQuantity) {
    InventoryStock stock = inventoryClient.findStock(sku);

    return stock.available()
        && stock.quantity() >= requestedQuantity;
}
~~~

Ví dụ trên là code minh họa: một ứng dụng thật còn có luồng xử lý `404`, timeout, security và quyết định hiển thị thông báo.

Đọc từ **điều kiện ra quyết định** để ghi nhu cầu:

1. Consumer cần định danh đúng sản phẩm thông qua `sku`.
2. Consumer cần `available` là **boolean**, không phải chuỗi `"true"`.
3. Consumer cần `quantity` là **number**, không phải chuỗi `"8"`.
4. Với số lượng còn 0, consumer cần xử lý trường hợp hết hàng.
5. Với SKU không tồn tại, consumer cần phân biệt với lỗi hệ thống.
6. Consumer cần nội dung và media type có thể deserialize được, chẳng hạn `application/json`.

### 3.1. Tập hợp các nhóm nhu cầu

| Nhóm | Ví dụ câu hỏi cần hỏi consumer |
| --- | --- |
| **Request target** | HTTP method, path, path variable, query parameter nào? |
| **Request headers** | `Accept`, `Content-Type`, xác thực, tenant hoặc correlation ID nào là một phần giao diện? |
| **Request body** | Field bắt buộc, kiểu, nullability, list/map và validation ra sao? |
| **Success status** | `200`, `201`, `204` hay một status khác? |
| **Success body** | Consumer đọc field nào, kiểu gì, có thể vắng mặt không? |
| **Error status/body** | Khi not-found, invalid request hoặc conflict, client phải phân nhánh theo status/code nào? |
| **Động và tĩnh** | ID/timestamp có biến đổi? Mã trạng thái nào phải cố định? |
| **Version** | Consumer đang chạy với API/stub version nào? |
| **Messaging** | Topic/destination, event type, header, payload và schema version nào? |
| **Phi chức năng** | Timeout, retry, authentication, order/delivery semantics cần test riêng ở tầng nào? |

**Không phải mọi nhu cầu đều phải nhồi vào một contract.** Một HTTP contract nên tập trung vào **hành vi giao tiếp quan sát được**; thuật toán, hiệu năng hay cơ chế phân tán thường cần unit/integration/performance/security tests riêng.

### 3.2. Chọn phạm vi theo use case

Consumer có thể cần bốn kết quả:

- Tồn kho đủ: cho phép đặt hàng.
- Tồn kho không đủ: từ chối đặt hàng.
- SKU không tồn tại: hiển thị thông báo không tìm thấy.
- API không khả dụng: chuyển sang trạng thái lỗi tạm thời hoặc retry có kiểm soát.

Trong đó, ba tình huống đầu có thể cần **những phản hồi cụ thể** được công bố bởi producer. Tình huống không khả dụng có thể cần test resilience độc lập với stub response đã cam kết.

## 4. Lập bảng truy vết nhu cầu → contract → kiểm thử

Trước khi viết DSL, tạo một bảng có **ID nhu cầu** và tiêu chí chấp nhận đo được.

| ID | Nhu cầu consumer | Biểu hiện trong contract | Producer test | Consumer test |
| --- | --- | --- | --- | --- |
| C-01 | Gọi tồn kho theo SKU | `GET /api/inventory/SKU-100` | Gửi đúng GET/path | Client gọi đúng endpoint |
| C-02 | Nhận JSON khi có SKU | Status `200`, `Content-Type: application/json` | Assert status/media type | Deserialize thành DTO |
| C-03 | Biết còn hàng | `available: true` (boolean) | Assert field/kiểu | Quyết định checkout dựa trên boolean |
| C-04 | Biết số lượng tồn | `quantity: 8` (number) | Assert field/kiểu | So sánh với số lượng yêu cầu |
| C-05 | Biết trường hợp hết hàng | Response `quantity: 0`, `available: false` | Generated test cho case này | Không cho đặt hàng |
| C-06 | Phân biệt SKU không tồn tại | `404` + `code: INVENTORY_NOT_FOUND` | Assert status, code | Hiển thị/tuyên bố not-found |
| C-07 | Tránh nhận nhầm lỗi không khớp stub | Mapping cho C-06 có body riêng | Đúng response của producer | Assert code, không chỉ status |
| C-08 | Phân biệt dữ liệu sai | `400` + `code: INVALID_SKU` nếu API công bố | Test input invalid | Client hiển thị lỗi nhập liệu |

Bảng là **công cụ review**, không bắt buộc phải có trong runtime. Giá trị của nó nằm ở việc cho phép trả lời câu hỏi:

> Nếu một người thay đổi `quantity` từ JSON number thành String, **test nào phải thất bại?**

Nếu không thể chỉ ra một assertion hoặc kịch bản cụ thể, nhu cầu có thể chưa được bảo vệ đầy đủ.

### 4.1. Định nghĩa “đã phản ánh” như thế nào?

Một nhu cầu được coi là **được bảo vệ bằng contract** khi:

1. Nó được viết thành điều kiện quan sát được: request, status, header, field, kiểu, mã lỗi hoặc message.
2. Có contract đúng nguồn, đúng version, chứa điều kiện đó.
3. Generated producer test được sinh và **thực thi**, có assertion tương ứng.
4. Consumer test dùng stub đúng version, gọi **code consumer thật** và kiểm tra quyết định/hành vi.
5. CI có bước phát hiện khi contract bị xóa, test bị skip hoặc stub lấy nhầm version.

Nếu mới chỉ có contract DSL mà chưa chạy generated producer tests, ghi trạng thái **“đã mô tả, chưa xác minh producer”** thay vì “đã bảo đảm tương thích”.

## 5. Xây contract HTTP thành công dựa trên nhu cầu

Ta bắt đầu từ C-01 đến C-04. Tệp nguồn minh họa:

~~~text
src/test/resources/contracts/inventory/get_inventory_available.groovy
~~~

Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_available')
    description('Checkout đọc SKU còn hàng để quyết định đặt mua')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')

        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()

        headers {
            contentType(applicationJson())
        }

        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

Ý nghĩa:

- `method GET()`: Consumer dùng GET; nếu client gửi POST thì stub mapping có thể không khớp.
- `urlPath('/api/inventory/SKU-100')`: Một request cụ thể được kiểm chứng ở producer.
- `Accept: application/json`: Consumer công bố định dạng muốn nhận.
- `status OK()`: Producer phải trả `200` trong case này.
- `Content-Type`: Consumer deserialize JSON theo media type đã thỏa thuận.
- `available: true`: Boolean JSON, không phải String.
- `quantity: 8`: Number JSON, không phải String.

### 5.1. Vì sao cần chọn đúng kiểu JSON?

Hai response nhìn qua có vẻ giống nhau:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

~~~json
{
  "sku": "SKU-100",
  "available": "true",
  "quantity": "8"
}
~~~

Nhưng response thứ hai đổi kiểu String, có thể khiến consumer deserialization thất bại hoặc xử lý khác mong đợi. **Type là một phần của giao diện dữ liệu** nếu consumer deserialize theo DTO có trường boolean/int.

Khi review generated producer test, hãy kiểm tra matcher và assertions thực sự ràng buộc kiểu mong muốn. Không chỉ nhìn response sample rồi mặc định mọi field đều được test theo đúng cách consumer cần.

### 5.2. Không cố định field không cần thiết

Nếu response còn có `debugInfo`, `internalNodeId` hoặc `generatedAt` nhưng consumer không dùng, không nên mặc định ràng buộc cứng toàn bộ dữ liệu vì thấy chúng trong một JSON mẫu.

Chọn **hợp đồng đủ chặt** cho hành vi mà consumer sử dụng, **đủ linh hoạt** với metadata không cần thiết. Nếu client có strict JSON deserialization hoặc kiểm tra field lạ, việc thêm field mới cũng có thể là vấn đề; cần ghi rõ parser behavior thực tế trong đánh giá tương thích.

## 6. Trường hợp tồn kho không đủ cần có fixture riêng

C-05 không được chứng minh chỉ bằng case trả `available: true`. Nếu Checkout cần từ chối đặt hàng khi số lượng không đủ, nên có một tương tác khác hoặc một test consumer khác dựa trên response đã được hợp đồng công bố.

Ví dụ:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_out_of_stock')

    request {
        method GET()
        urlPath('/api/inventory/SKU-EMPTY')

        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-EMPTY',
            available: false,
            quantity: 0
        )
    }
}
~~~

Phân biệt:

- **Contract producer** ở đây xác minh một SKU tồn tại nhưng hết hàng được biểu diễn bằng `200` với `available: false`, `quantity: 0`.
- **Consumer test** cần kiểm tra Checkout **không cho đặt hàng** khi nhận response đó.

Không cần viết hàng trăm hợp đồng chỉ để thử mọi số lượng. Nếu contract đã bảo vệ kiểu và shape, logic so sánh `requestedQuantity` với `quantity` có thể được kiểm tra bằng **unit tests của Checkout** với nhiều giá trị `0`, `1`, `8`, `9`. Contract test chọn các kịch bản đại diện mà consumer phụ thuộc.

### 6.1. Bảng phân phối trách nhiệm hợp lý

| Câu hỏi | Contract test | Unit/domain test |
| --- | --- | --- |
| Producer có field `quantity` kiểu number không? | Có, nếu được DSL/matcher bảo vệ | Không phải mục tiêu chính |
| Producer trả `available: false` cho fixture hết hàng không? | Có | Không bắt buộc |
| Checkout từ chối khi yêu cầu 9 nhưng tồn 8 không? | Có thể test end-to-end với stub | Nên có unit test cho quy tắc biên |
| Tồn kho thực được cập nhật chính xác khi nhiều đơn đồng thời không? | Không tự đủ | Cần transaction/concurrency/integration tests |

## 7. Nhánh lỗi là nhu cầu consumer, không phải phần phụ

Giả sử consumer phân biệt **không tồn tại** với **hết hàng**:

- SKU tồn tại, số lượng 0 → `200` cùng `available: false`.
- SKU không tồn tại → `404` cùng `code: INVENTORY_NOT_FOUND`.

Nếu hai tình huống đều biến thành `404`, Checkout có thể hiển thị sai hoặc xử lý không đúng.

Groovy DSL cho nhánh not-found:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_not_found')

    request {
        method GET()
        urlPath('/api/inventory/SKU-404')

        headers {
            accept(applicationJson())
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVENTORY_NOT_FOUND',
            message: 'SKU not found'
        )
    }
}
~~~

Consumer nên test cả:

1. HTTP `404` và code `INVENTORY_NOT_FOUND` được phân nhánh thành lỗi “không có SKU”.
2. Checkout không coi kết quả này là tồn kho bằng 0 để thử đặt hàng.
3. Một unmatched WireMock `404` (do sai path, header hoặc port) **không bị nhầm** với lỗi nghiệp vụ có body đã cam kết.

### 7.1. Response sai request khác response lỗi nghiệp vụ

Một lỗi quan trọng khi dùng Stub Runner: nếu client gọi `/api/inventories/SKU-404` (sai path), WireMock có thể trả `404` vì **không có mapping nào khớp**.

Trong khi đó, hợp đồng not-found mong đợi:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "INVENTORY_NOT_FOUND",
  "message": "SKU not found"
}
~~~

Chỉ assert status `404` có thể làm consumer test **xanh sai**. Hãy kiểm tra đúng error code/body hoặc hành vi consumer chỉ xảy ra khi nhận lỗi nghiệp vụ.

### 7.2. Request không hợp lệ cần contract khi consumer dùng nhánh đó

Nếu client có thể gửi mã SKU rỗng hoặc ký tự không hợp lệ và API đã công bố `400` + `INVALID_SKU`, định nghĩa thêm case:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_invalid_sku')

    request {
        method GET()
        urlPath('/api/inventory/INVALID-SKU!')
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVALID_SKU'
        )
    }
}
~~~

Ví dụ chỉ hợp lệ nếu producer **thực sự coi `INVALID-SKU!` là mã không hợp lệ theo quy tắc public API** và trả response đã cam kết; một route có chứa ký tự đặc biệt cũng có thể bị filter/router xử lý khác. Khi thực hành, dùng một mã lỗi thử nghiệm và route đúng với chính sách validation của dự án. Không tự ép mọi API dùng `400` hay đúng tên field `code`; đó là quy ước được producer/consumer cùng chọn.

## 8. Biểu diễn nhu cầu thành công trong YAML DSL

Cùng contract `get_inventory_available` bằng YAML:

~~~yaml
name: get_inventory_available
description: Checkout đọc SKU còn hàng để quyết định đặt mua
request:
  method: GET
  urlPath: /api/inventory/SKU-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-100
    available: true
    quantity: 8
~~~

Cùng contract not-found:

~~~yaml
name: get_inventory_not_found
request:
  method: GET
  urlPath: /api/inventory/SKU-404
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: INVENTORY_NOT_FOUND
    message: SKU not found
~~~

**Chọn một định dạng nguồn phù hợp với dự án**, không kích hoạt cả Groovy và YAML định nghĩa trùng tương tác chỉ vì muốn có hai bản ví dụ. Trong bài học, hai cách được trình bày để người đọc hiểu cú pháp.

### 8.1. Các lỗi khi chuyển từ Groovy sang YAML

- `available: true` phải là YAML boolean, không phải `available: "true"`.
- `quantity: 8` phải là number, không phải `"8"` nếu API cam kết Number.
- Với chuỗi rỗng, nên viết `""` rõ ràng để không bị hiểu nhầm thành null.
- JSON array được viết bằng YAML sequence (`-`), không bằng map.
- Các chuỗi như `"00123"` cần đặt dấu nháy nếu consumer mong String có số 0 đầu.
- Nếu JSON field có dấu chấm hoặc ký tự đặc biệt, dùng cú pháp YAML và JSONPath tương ứng.

Việc tạo producer tests từ YAML không loại bỏ nhu cầu review **semantics**: cú pháp đúng nhưng chọn matcher quá rộng hoặc bỏ status vẫn tạo khoảng trống.

## 9. Dữ liệu động: ràng buộc cái cần ổn định, nới cái cần biến đổi

Một API tạo reservation có thể trả ID mới và timestamp thay đổi ở mỗi request:

~~~json
{
  "reservationId": "RES-123",
  "status": "CONFIRMED",
  "createdAt": "2026-11-24T03:00:00Z"
}
~~~

Consumer cần:

- `reservationId` có định dạng hợp lệ để gọi API tiếp theo.
- `status` phải là `CONFIRMED` để chuyển sang bước tiếp.
- `createdAt` parse được thành timestamp, nhưng không phụ thuộc một thời điểm cố định.

Có thể dùng response matchers:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_reservation')

    request {
        method POST()
        urlPath('/api/reservations')
        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }
        body(
            sku: 'SKU-100',
            quantity: 1
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'RES-123',
            status: 'CONFIRMED',
            createdAt: '2026-11-24T03:00:00Z'
        )
        bodyMatchers {
            jsonPath('$.reservationId', byRegex('RES-[0-9]+'))
            jsonPath('$.createdAt', byTimestamp())
        }
    }
}
~~~

**Điểm chính:** `status` là literal được giữ chặt; `reservationId` và `createdAt` là dữ liệu có thể biến đổi nên dùng matcher theo nhu cầu.

### 9.1. Khi matcher quá rộng sẽ che breaking change

Nếu hợp đồng chỉ kiểm tra `quantity` bằng `byType()`, một producer trả 999 dù kho thật chỉ có 8 vẫn có thể đạt vì nó vẫn là Number. Type matcher bảo vệ **kiểu**, không bảo vệ **giá trị nghiệp vụ**.

Khi consumer cần một giá trị có tính quyết định (ví dụ `status: CONFIRMED` hay `code: INVENTORY_NOT_FOUND`), so khớp chính xác hoặc dùng matcher hẹp có chủ đích. Không chuyển mọi field thành `byRegex('.*')` chỉ để build xanh.

### 9.2. Consumer-side và producer-side values

Spring Cloud Contract có cơ chế hai phía cho giá trị động, ví dụ ở **request**:

~~~groovy
request {
    method POST()
    urlPath('/api/echo')
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: $(consumer(regex('CUS-[0-9]+')),
                      producer('CUS-7'))
    )
}
~~~

Ở request, generated **producer test** thường gửi giá trị cụ thể `CUS-7`, còn **stub** có thể chấp nhận một số mã phù hợp regex. Đừng nhầm matcher rộng cho stub với việc producer được test trên mọi mã khách hàng.

Ở response, cách chọn mẫu dành cho consumer và matcher phía producer cũng cần được hiểu đúng theo DSL. Khi review, luôn mở generated producer assertions và stub mapping thực tế để xác nhận hai phía nhận đúng điều mà consumer cần.

## 10. Nhu cầu consumer chỉ thực sự được bảo vệ khi test cả hai phía

Một workflow chuẩn:

~~~mermaid
flowchart TD
    N["Nhu cầu consumer được ghi rõ"] --> DSL["Contract Groovy/YAML"]
    DSL --> PT["Generated producer tests"]
    DSL --> STUB["Stub JAR / mappings"]
    PT --> P{"Producer đáp ứng?"}
    P -- "Không" --> FIX["Sửa producer hoặc thương lượng contract"]
    P -- "Có" --> R["Phát hành stub đã xác minh"]
    STUB --> R
    R --> SR["Consumer chạy Stub Runner"]
    SR --> CT["Consumer client và use case test"]
    CT --> Q{"Consumer xử lý đúng?"}
    Q -- "Không" --> CF["Sửa consumer hoặc rà soát contract"]
    Q -- "Có" --> PASS["Nhu cầu đã có bằng chứng hai phía"]
~~~

**Generated producer test** kiểm tra việc producer thực sự trả đúng response như contract trong môi trường test. **Consumer test** kiểm tra consumer gửi request đúng và xử lý response của stub đúng.

Điều mà một phía không chứng minh:

| Test nào xanh? | Đã chứng minh | Chưa chứng minh |
| --- | --- | --- |
| Chỉ producer generated tests | Producer đáp ứng những interactions được sinh và chạy | Consumer có đang gọi đúng endpoint và xử lý response đúng không? |
| Chỉ consumer stub tests | Consumer xử lý đúng các stub fixtures đã chạy | Producer code thật có còn đáp ứng contract không? |
| Cả hai đều xanh nhưng thiếu case 404 | Những case đã được mô tả đạt | Nhu cầu not-found chưa chắc được bảo vệ |
| Cả hai xanh nhưng dùng stub version cũ | Tương thích với phiên bản đã thử | Không chứng minh tương thích với producer mới |
| Cả hai xanh và matrix đầy đủ | Có bằng chứng tốt cho các yêu cầu giao tiếp trong phạm vi | Không chứng minh mọi tình huống concurrency/security/latency |

### 10.1. Tại sao contract review phải đi cùng code consumer?

Một producer có thể đề xuất schema rất hợp lý nhưng consumer thực tế đang phụ thuộc vào:

~~~text
response.data.inventory.available
~~~

trong khi contract mới chỉ mô tả:

~~~text
response.available
~~~

Cả hai đều là JSON hợp lệ, nhưng chúng khác nhau về cấu trúc. Đánh giá đúng phải so sánh **DTO/client parser/use case consumer** với **schema mà contract mô tả**, không chỉ so sánh contract với một API sample do producer đưa ra.


## 11. Viết consumer test: gọi client thật qua Stub Runner

Giả sử Inventory Service đã đóng gói stub JAR từ contract và producer verification đã đạt. Checkout Service dùng HTTP client để lấy thông tin tồn kho.

Một client minh họa bằng Spring `RestClient`:

~~~java
public record InventoryStock(
    String sku,
    boolean available,
    int quantity
) {}

public final class InventoryClient {
    private final RestClient client;

    public InventoryClient(String baseUrl) {
        this.client = RestClient.create(baseUrl);
    }

    public InventoryStock findStock(String sku) {
        return client.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(InventoryStock.class);
    }
}
~~~

Lớp này minh họa Java record và `RestClient` (Spring Framework 6.1+); khi sử dụng thực tế cần package/import tương ứng và có thể thay bằng WebClient, OpenFeign hoặc adapter client đang được Checkout sử dụng.

Use case consumer:

~~~java
public final class CheckoutService {
    private final InventoryClient inventoryClient;

    public CheckoutService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public boolean canPlaceOrder(String sku, int requestedQuantity) {
        InventoryStock stock = inventoryClient.findStock(sku);
        return stock.available()
            && stock.quantity() >= requestedQuantity;
    }
}
~~~

Test chạy cùng Stub Runner, lấy cổng WireMock từ `@StubRunnerPort`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutConsumerContractTest {

    @StubRunnerPort("com.example:inventory-producer")
    int inventoryStubPort;

    @Test
    void shouldAllowOrderWhenInventoryIsAvailable() {
        InventoryClient client =
            new InventoryClient("http://localhost:" + inventoryStubPort);
        CheckoutService checkout = new CheckoutService(client);

        boolean allowed = checkout.canPlaceOrder("SKU-100", 3);

        assertThat(allowed).isTrue();
    }

    @Test
    void shouldRejectOrderWhenOutOfStock() {
        InventoryClient client =
            new InventoryClient("http://localhost:" + inventoryStubPort);
        CheckoutService checkout = new CheckoutService(client);

        boolean allowed = checkout.canPlaceOrder("SKU-EMPTY", 1);

        assertThat(allowed).isFalse();
    }
}
~~~

Các giả định bắt buộc cho ví dụ:

- Producer đã tạo mappings cho `SKU-100` và `SKU-EMPTY`.
- Stub artifact `com.example:inventory-producer:1.2.3:stubs` đã được cài trong Maven local repository; nếu không, đổi mode/nguồn stub cho phù hợp.
- Checkout test có dependencies Spring Boot Test, Spring Cloud Contract Stub Runner và HTTP client/Jackson tương thích.
- Một dự án thực tế cần chạy trên Spring configuration/JUnit version phù hợp.
- Nếu ứng dụng Checkout dùng dependency injection, nên test **CheckoutService thật với InventoryClient thật** đã được nối với stub URL, thay vì tạo một phiên bản logic giả chỉ để test.

### 11.1. Vì sao một stub smoke test chưa đủ?

Một test như sau:

~~~java
String response = RestClient
    .create("http://localhost:" + inventoryStubPort)
    .get()
    .uri("/api/inventory/SKU-100")
    .retrieve()
    .body(String.class);

assertThat(response).contains("SKU-100");
~~~

chỉ chứng minh **WireMock trả được dữ liệu mẫu**. Nó chưa chứng minh:

- InventoryClient của Checkout gửi đúng method/URL/headers.
- Checkout parse `available` và `quantity` đúng kiểu.
- Checkout không nhận đơn khi `quantity` không đủ.
- Checkout phân biệt not-found và lỗi hệ thống.

**Consumer test đúng mục đích phải chạy qua code consumer** và assert hành vi mà use case cần.

### 11.2. Đừng hard-code port khi không cần

Trong ví dụ, `ids` không pin port, Stub Runner chọn port theo cấu hình. `@StubRunnerPort` lấy port tương ứng với producer. Điều này giảm xung đột khi nhiều bộ test chạy song song.

Nếu có nhiều stub services, phải lấy đúng port cho Inventory, Pricing, Payment... Không được trỏ tất cả clients vào một WireMock server chỉ vì chỉ nhìn thấy một giá trị `localhost`.

## 12. Kiểm thử nhánh lỗi bằng consumer behavior

Với contract `get_inventory_not_found`, khi client gọi `SKU-404`, WireMock trả `404` cùng JSON `INVENTORY_NOT_FOUND`.

Nếu dùng `RestClient.retrieve()` với thiết lập mặc định, response `4xx` thường gây exception kiểu HTTP client error. Consumer phải có logic xử lý được **error status và error body**, hoặc một adapter khác trả về kết quả có phân loại.

Pseudocode cho yêu cầu nghiệp vụ:

~~~java
// PSEUDOCODE: API riêng của Checkout, không phải hàm có sẵn
CheckoutResult result = checkout.tryPlaceOrder("SKU-404", 1);

assertThat(result.reason()).isEqualTo("SKU_NOT_FOUND");
assertThat(result.isAccepted()).isFalse();
~~~

Cần thêm test:

- `SKU-EMPTY`: request đúng, response `200`; Checkout từ chối vì hết hàng.
- `SKU-404`: response `404` với `code: INVENTORY_NOT_FOUND`; Checkout hiển thị không tìm thấy.
- Client gửi path sai: unmatched WireMock stub; test phải fail thay vì nhầm là một phản hồi not-found hợp lệ.
- `400` khi input sai, nếu đó là nhánh lỗi mà consumer thực sự nhận và cần xử lý.
- Downstream `5xx`/timeout khi hệ thống có chính sách retry/circuit breaker; phần resilience cần kiểm thử thêm bằng công cụ/phương pháp phù hợp.

### 12.1. Error code có thể quan trọng hơn message

Ví dụ response:

~~~json
{
  "code": "INVENTORY_NOT_FOUND",
  "message": "SKU not found"
}
~~~

Nếu Checkout dùng `code` để quyết định logic, mã `INVENTORY_NOT_FOUND` cần ổn định và được contract bảo vệ. `message` có thể đổi do bản địa hóa; nên xác định consumer phụ thuộc wording hay chỉ yêu cầu field là String, rồi chọn mức ràng buộc phù hợp.

**Không sử dụng String message để phân nhánh nghiệp vụ** nếu API đã cung cấp một mã lỗi máy đọc được ổn định. Trường hợp consumer thật đang phân nhánh dựa trên message cần được ghi nhận như một rủi ro tương thích và lên kế hoạch thay đổi, không giả vờ rằng nó không tồn tại.

## 13. HTTP không chỉ có response body: request cũng phải phản ánh nhu cầu

Consumer có thể cần truyền thông tin về warehouse, tenant hoặc channel. Nếu contract chỉ mô tả response nhưng bỏ qua request thực tế, stub có thể chấp nhận quá rộng và client sai vẫn được coi là hợp lệ.

Ví dụ một API khác nhận header `X-Channel`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_for_checkout')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')

        headers {
            accept(applicationJson())
            header('X-Channel', 'checkout')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

Nếu `X-Channel` là một phần giao diện public ảnh hưởng dữ liệu hoặc quyền truy cập, nên được contract ràng buộc. Nếu đó chỉ là header quan sát nội bộ và consumer không phụ thuộc, cần cân nhắc có đưa vào contract hay không.

### 13.1. Query parameter, path và request body

Checklist khi so contract với client:

| Thông tin | Contract và consumer cần nhất quán |
| --- | --- |
| HTTP method | `GET` khác `POST` |
| Path | `/api/inventory/SKU-100` khác `/api/inventories/SKU-100` |
| Query | `warehouse=HCM` khác `warehouse=HN` nếu kết quả phụ thuộc kho |
| Headers | `Accept`, `Content-Type`, auth/tenant/channel khi được API công bố |
| JSON body | Tên field, kiểu, null, list và nested object |
| Encoding | URL encoding của ký tự đặc biệt trong path/query |
| Status | `200`, `201`, `204`, `400`, `404` và ý nghĩa tương ứng |

Đối với route động `/api/inventory/{sku}`, một contract dùng literal `SKU-100` kiểm tra **một đại diện cụ thể**. Nếu consumer phải gọi nhiều SKU, có thể chọn request matcher phù hợp và thêm fixture theo các phân vùng dữ liệu có ý nghĩa; không nên coi một literal là bằng chứng mọi URL hợp lệ đều được producer xử lý đúng.

### 13.2. Contract quá rộng có thể làm test client sai vẫn xanh

Ví dụ mapping WireMock khớp mọi path bắt đầu bằng `/api/`, không yêu cầu method hoặc body cụ thể. Consumer có thể gửi sai `/api/inventory/item/SKU-100` và vẫn nhận `200`.

Do đó request matching phải đủ chặt cho **request shape mà consumer được phép phát đi**. Nhưng cũng không nên bắt buộc header động không cần thiết như correlation ID phải bằng một giá trị cố định; dùng matcher theo pattern/kiểu nếu nó thực sự là một phần contract.

## 14. Messaging consumer: kiểm tra event consumer thực sự sử dụng

Với messaging, consumer có thể cần biết sự kiện thanh toán được xác nhận để mở khóa một đơn hàng.

Ví dụ message contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('payment_authorized_event')
    label 'paymentAuthorized'

    input {
        triggeredBy('publishAuthorizedPayment()')
    }

    outputMessage {
        sentTo('payments.authorized')
        headers {
            header('eventType', 'PaymentAuthorized')
        }
        body(
            eventId: 'evt-100',
            paymentId: 'PAY-100',
            orderId: 'ORD-123',
            amount: 120000
        )
    }
}
~~~

Consumer thực sự cần:

- Destination/event type đúng để listener nhận được.
- `orderId` liên kết được với đơn hàng.
- `amount` là number nếu consumer tính toán hoặc so sánh.
- `eventId` có danh tính ổn định để hỗ trợ idempotency, nếu cần.
- Schema version hoặc những trường mới được xử lý theo chiến lược tương thích đã thống nhất.

Với tích hợp Stub Runner messaging phù hợp, consumer test có thể kích hoạt message stub rồi kiểm tra listener deserialize và xử lý event.

**Giới hạn quan trọng:** Một message contract kiểm chứng destination, headers, body; nó **không tự chứng minh** thứ tự toàn broker, redelivery/ack và exactly-once business effects. Các nhu cầu này phải được ghi sang **broker integration**, idempotency hoặc failure-injection tests. Không ghi “đã được contract bảo vệ” khi chỉ có field `eventId` trong JSON.

## 15. Review hợp đồng bằng câu hỏi thay đổi ngược (mutation thinking)

Một cách hiệu quả để phát hiện thiếu coverage là đặt câu hỏi:

> “Nếu producer thay đổi X, bài test nào phải đỏ?”

Ma trận thử nghiệm:

| Thay đổi giả định của producer | Tác động có thể có tới consumer | Bằng chứng test cần có |
| --- | --- | --- |
| Xóa field `quantity` | Checkout không so sánh được tồn kho | Generated test thất bại do thiếu field |
| Đổi `quantity` từ number sang String | Deserialize hoặc so sánh sai | Generated assertion kiểm tra type |
| Đổi `available` thành `inStock` | Client không đọc được tên cũ | Contract bảo vệ tên field |
| Đổi `200` thành `204` | Không còn body để consumer đọc | Status và response body assertions |
| Đổi `404` thành `200` với error JSON | Client có thể coi lỗi là thành công | Contract not-found kiểm tra status |
| Đổi `INVENTORY_NOT_FOUND` thành `SKU_MISSING` | Consumer phân nhánh bằng code cũ hỏng | Equality trên error code |
| Đổi request path nhưng không giữ route cũ | Client gọi endpoint cũ thất bại | Producer/generated test gửi path cũ |
| Thêm header bắt buộc mà consumer chưa gửi | WireMock/client hoặc producer trả lỗi | Contract/request matching và consumer test |
| Đổi message destination | Listener có thể không nhận event | Message contract kiểm tra `sentTo` |
| Giao message hai lần | Consumer có thể xử lý lặp nghiệp vụ | Idempotency/integration tests, **không chỉ** contract |
| Tăng latency ngoài SLA | Client timeout | Performance/resilience tests riêng |

Đây là một bài kiểm tra **tư duy bao phủ**. Không cần sửa code producer thật cho mọi dòng trong review. Với những thay đổi có tác động cao, có thể thực hiện mutation experiment trong môi trường kiểm thử có kiểm soát để xác nhận assertions thực sự bắt lỗi.

### 15.1. Khi test không đỏ như kỳ vọng

Có thể do:

1. Nhu cầu chưa được thể hiện trong DSL.
2. Matcher quá rộng và chấp nhận giá trị sai.
3. Generated producer tests không được sinh hoặc bị skip.
4. Consumer test chỉ ping stub, không kiểm tra code consumer.
5. Stub đang dùng version cũ.
6. Một nhánh lỗi hoặc dữ liệu biên chưa có fixture.
7. Dữ liệu bị mock ở tầng bỏ qua hành vi cần kiểm tra.

Cách sửa là quay lại **nhu cầu consumer và ranh giới thực thi**, không vội thêm hàng loạt matcher không rõ mục đích.

## 16. Quy trình review giữa producer và consumer

Một hợp đồng tốt thường được duyệt qua các bước sau:

### Bước 1 — Consumer nêu use case và quyết định cần đưa ra

Ví dụ: “Checkout cần `available` và `quantity` để quyết định có nhận đơn; nếu không có SKU cần hiển thị thông báo không tìm thấy”.

Đừng bắt đầu từ class DTO nội bộ của producer.

### Bước 2 — Chuyển thành các acceptance criteria đo được

Ví dụ:

- Khi `GET /api/inventory/SKU-100`, nhận `200`, JSON có `sku`, `available` boolean và `quantity` number.
- Khi `GET /api/inventory/SKU-EMPTY`, nhận `200`, `available: false` và `quantity: 0`.
- Khi `GET /api/inventory/SKU-404`, nhận `404` và `code: INVENTORY_NOT_FOUND`.

### Bước 3 — So DSL với acceptance criteria

Xem Groovy/YAML contract đã có đủ request, response, status, headers, error code, shape và matcher chưa.

### Bước 4 — Producer chạy generated verification

Đảm bảo producer thực sự tạo đúng response trong test context; khi thay code producer, test phải phát hiện vi phạm thỏa thuận.

### Bước 5 — Consumer kiểm thử qua Stub Runner

Khởi động stub đúng version, nối vào client thật, assert use case cùng các nhánh lỗi.

### Bước 6 — Ghi rõ những nhu cầu ngoài phạm vi contract

Concurrency, transaction, security policies, retry hoặc delivery semantics cần các tests khác. Liên kết kết quả với yêu cầu ban đầu thay vì xóa yêu cầu khỏi checklist.

### Bước 7 — Chấp nhận hoặc thương lượng thay đổi

Khi producer muốn đổi schema, đánh giá consumer hiện tại bị ảnh hưởng, migration plan, thời gian deprecation, version và quy trình phát hành artifact tương ứng.

### 16.1. Vai trò của từng bên

| Vai trò | Cần xác nhận |
| --- | --- |
| Consumer developer | Contract bảo vệ những field/nhánh mà client thực sự dùng |
| Producer developer | Có thể triển khai behavior và generated tests phản ánh cam kết |
| API/platform owner | Naming, media type, error schema, versioning nhất quán |
| QA/test engineer | Có case biên, phủ lỗi, giả định setup và bằng chứng test |
| CI/release owner | Stub được lấy đúng version, không skip tests, release gates rõ |

Không cần một quy trình họp nặng nề cho từng field; có thể dùng pull request template và bảng truy vết ngắn. Nhưng **review chỉ từ phía producer** dễ bỏ sót nhu cầu mà client đang dựa vào.

## 17. Các tình huống tương thích và thay đổi API

### 17.1. Thêm field mới có luôn tương thích?

Không thể trả lời tuyệt đối. Nếu consumer dùng JSON parser bỏ qua unknown fields, thêm field có thể tương thích. Nếu client dùng strict schema validation hoặc decoder không cho phép field lạ, nó có thể thất bại.

Vì vậy review nên kiểm tra cách deserialize thực tế, không chỉ áp dụng câu “thêm field là backward compatible” trong mọi trường hợp.

### 17.2. Xóa hoặc đổi tên field mà consumer đang dùng

Thường là breaking change. Ví dụ đổi `quantity` thành `remainingQuantity` khiến client cũ không parse được, trừ khi producer duy trì cả hai field trong giai đoạn chuyển tiếp.

### 17.3. Nới matcher không thay thế migration

Nếu producer muốn đổi `status: CONFIRMED` sang `ACCEPTED`, chuyển contract matcher thành một String bất kỳ để test xanh có thể che việc consumer phân nhánh sai. Cần:

1. Biết consumer nào dùng `CONFIRMED`.
2. Thống nhất version/migration.
3. Giữ hành vi cũ hoặc hỗ trợ song song trong thời gian chuyển đổi.
4. Tạo contract/tests cho behavior mới và cũ nếu cùng tồn tại.
5. Chỉ loại bỏ contract cũ khi không còn consumer cần nó.

### 17.4. Cập nhật stub version có kiểm soát

Producer có thể phát hành artifact `com.example:inventory-producer:1.2.4:stubs` sau khi verification. Consumer đang dùng `1.2.3` cần có kế hoạch nâng stub version để thử tương thích với bản mới.

Tránh dùng `+` hoặc latest một cách vô thức trong CI cần tái lập. Một test xanh với stub cũ **không chứng minh tương thích với release mới**.

## 18. CI: đo bằng nhu cầu được bao phủ, không chỉ số lượng test

Ví dụ pipeline producer Maven đã cấu hình Spring Cloud Contract Verifier:

~~~bash
./mvnw -B clean verify
~~~

Hoặc với Gradle đã cấu hình plugin/tasks:

~~~bash
./gradlew clean build
~~~

Các lệnh là ví dụ. CI phải xác minh **generated tests được sinh, biên dịch và thực thi**, không chỉ build thành công khi 0 tests.

### 18.1. Các cổng chất lượng đề xuất

| Gate | Câu hỏi |
| --- | --- |
| Contract review | Một thay đổi có ảnh hưởng consumer nào và nhu cầu nào? |
| Producer verification | Contract tests của các kịch bản quan trọng đã chạy và đạt chưa? |
| Stub packaging | Artifact chứa mappings đúng, đúng coordinates/classifier/version chưa? |
| Consumer verification | Client/logic consumer đã được chạy với stub phù hợp chưa? |
| Negative-path coverage | 404/400/409 và dữ liệu biên mà consumer dùng đã được thử chưa? |
| Version discipline | Consumer CI đang dùng bản stub nào? Có cập nhật khi producer thay đổi không? |
| Separate reliability tests | Những nhu cầu ngoài contract được kiểm tra bằng loại test nào? |

### 18.2. Một báo cáo coverage có ích

Thay vì chỉ ghi “15 hợp đồng, 35 tests”, nên ghi:

~~~text
C-01 GET path/header:          COVERED (producer + consumer)
C-02 HTTP 200 JSON:            COVERED (producer + consumer)
C-03 available boolean:        COVERED (producer + consumer)
C-04 quantity number:          COVERED (producer + consumer)
C-05 out-of-stock branch:      COVERED (producer + consumer)
C-06 not-found 404 + code:     MISSING consumer behavior test
C-07 avoid unmatched stub 404: MISSING assertion
C-08 invalid SKU 400:          NOT REQUIRED for current use case
~~~

Các nhãn `COVERED`, `MISSING` và `NOT REQUIRED` nên có bằng chứng link tới contract/test/build result trong workflow nội bộ nếu có.

**Đừng biến coverage thành việc đếm field đơn thuần.** Đếm 100 JSON fields nhưng không bảo vệ nhánh 404 mà Checkout cần vẫn là một hợp đồng thiếu.

## 19. Bài thực hành: đánh giá hợp đồng của Shipping Service

Giả sử Checkout Service cần hiển thị phí vận chuyển dự kiến. Shipping Service (producer) cung cấp:

~~~http
POST /api/shipping/quotes HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "destinationZone": "HCM",
  "weightGrams": 800
}
~~~

Response dự kiến:

~~~json
{
  "quoteId": "Q-123",
  "fee": 30000,
  "currency": "VND",
  "service": "STANDARD"
}
~~~

Consumer yêu cầu:

1. `fee` phải là Number để tính tổng thanh toán.
2. `currency` phải là `VND` nếu báo giá sử dụng đồng Việt Nam trong kịch bản này.
3. `service` phải cho biết loại dịch vụ.
4. `quoteId` phải có định dạng có thể lưu và dùng khi xác nhận giao hàng.
5. Nếu `weightGrams` không hợp lệ, producer phải trả một lỗi cụ thể được API công bố.
6. Khi không có dịch vụ ở zone đã chọn, phải có một nhánh phản hồi để Checkout hiển thị phù hợp.

### 19.1. Nhiệm vụ A — Phát hiện thiếu sót

Contract ban đầu:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        urlPath('/api/shipping/quotes')
        body(
            destinationZone: 'HCM',
            weightGrams: 800
        )
    }

    response {
        status OK()
        body(
            quoteId: 'Q-123'
        )
    }
}
~~~

Hãy chỉ ra các thiếu sót:

- Chưa khai báo media type request/response trong khi consumer cần JSON.
- Chưa bảo vệ `fee`, `currency` và `service`.
- Chưa phân biệt trường ID động với field nghiệp vụ cố định.
- Chưa có nhánh input invalid hoặc không có dịch vụ.
- Chưa có consumer test xác minh tính tổng phí và hiển thị lỗi.

### 19.2. Nhiệm vụ B — Viết contract sửa lại

Gợi ý:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_shipping_quote')

    request {
        method POST()
        urlPath('/api/shipping/quotes')
        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }
        body(
            destinationZone: 'HCM',
            weightGrams: 800
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            quoteId: 'Q-123',
            fee: 30000,
            currency: 'VND',
            service: 'STANDARD'
        )
        bodyMatchers {
            jsonPath('$.quoteId', byRegex('Q-[0-9]+'))
        }
    }
}
~~~

Lưu ý: Status `200` trong ví dụ là chính sách đã giả định của Shipping Service, không phải giá trị bắt buộc cho mọi API tạo báo giá. Nếu API thật cam kết `201` thì phải dùng `201` và kiểm tra theo đó.

### 19.3. Nhiệm vụ C — Lập ma trận traceability

Tạo ít nhất sáu hàng:

| Nhu cầu | Contract case | Assertion producer | Assertion consumer |
| --- | --- | --- | --- |
| Phí là số | `create_shipping_quote` | `$.fee` là number | Tính đúng tổng phí |
| Tiền tệ VND | `create_shipping_quote` | `currency == VND` | Hiển thị đúng đơn vị |
| ID hợp lệ | `create_shipping_quote` | Regex `Q-[0-9]+` | Client lưu ID, có thể dùng |
| Input sai | Contract 400 riêng | Status/error code | Không gửi đơn tiếp |
| Không có dịch vụ | Contract lỗi riêng | Status/body theo API | Hiển thị trạng thái phù hợp |
| Truyền đúng body | `create_shipping_quote` | Request method/body | Client phát request đúng |

### 19.4. Nhiệm vụ D — Consumer test qua Stub Runner

- Khởi động stub Shipping Service đúng version.
- Trỏ ShippingClient thật của Checkout đến stub.
- Gửi `destinationZone: HCM`, `weightGrams: 800`.
- Kiểm tra Checkout hiển thị hoặc tính toán với `fee: 30000`, `currency: VND`.
- Thử input invalid và no-service với các stub mappings đã được contract công bố.
- Kiểm tra unmatched stub request không bị nhận nhầm như một lỗi nghiệp vụ hợp lệ.

### 19.5. Nhiệm vụ E — Mutation review

Giả sử producer lần lượt:

1. Đổi `fee` từ 30000 thành String `"30000"`.
2. Bỏ `service`.
3. Đổi `currency` thành `USD`.
4. Đổi `quoteId` từ `Q-123` thành `INVALID`.
5. Trả `200` cho input invalid mà trước đây trả `400`.
6. Giữ response đúng nhưng đổi path thành `/api/shipping/prices` và xóa route cũ.

Với mỗi thay đổi, ghi **contract assertion nào dự kiến thất bại**, **consumer behavior nào bị ảnh hưởng** và **cần sửa producer hay thỏa thuận API mới**.

### 19.6. Câu hỏi tự đánh giá

1. Vì sao generated producer test xanh vẫn chưa chứng minh consumer đã gửi đúng HTTP request?
2. `fee` dùng `byType()` có kiểm tra đúng giá 30000 không?
3. Tại sao một response `404` không có error code có thể là unmatched stub thay vì lỗi nghiệp vụ?
4. Khi nào việc thêm field mới là tương thích? Khi nào có thể phá strict parser?
5. Vì sao không nên lấy version stub `+` trong CI cần tái lập?
6. Có phải mọi lỗi timeout và concurrency đều phải được mô tả bằng Spring Cloud Contract không?
7. Một bảng traceability thiếu consumer test nhưng có DSL và producer test nên được đánh dấu thế nào?
8. Vì sao cần người viết consumer xác nhận contract trước khi chấp nhận thay đổi breaking?

**Định hướng:** Contract mô tả, producer verification chứng minh producer, Stub Runner test chứng minh consumer. Matcher chọn theo mức độ bất biến thực tế; những đặc tính ngoài giao diện cần kiểm thử riêng.

## 20. Checklist: nhu cầu consumer đã thật sự được phản ánh chưa?

- [ ] Xác định use case và quyết định nghiệp vụ mà consumer phải đưa ra.
- [ ] Liệt kê method, path, query, headers và body mà client thực sự gửi.
- [ ] Chỉ rõ success status và media type.
- [ ] Có đầy đủ các field/kiểu JSON mà consumer đọc.
- [ ] Nullability, optional, list/map và nested structure được quyết định có chủ đích.
- [ ] Các nhánh success, out-of-stock, not-found, validation/error quan trọng được bao phủ.
- [ ] Error code được ràng buộc nếu consumer dùng nó để phân nhánh.
- [ ] Matcher không quá rộng làm lọt sai lệch về kiểu hoặc mã nghiệp vụ.
- [ ] Dữ liệu động có matcher phù hợp, không cố định ID/timestamp ngẫu nhiên.
- [ ] Contract có tên và vị trí để truy vết về requirement.
- [ ] Producer generated tests được sinh, chạy, không bị skip.
- [ ] Producer fixture thực sự dựng đúng các tình huống đã contract.
- [ ] Stub artifact có đúng version, classifier và mappings.
- [ ] Consumer tests dùng Stub Runner và gọi **code consumer thật**.
- [ ] Consumer assertions kiểm tra hành vi, không chỉ ping WireMock.
- [ ] Test lỗi 404 xác minh body/code, tránh unmatched stub pass giả.
- [ ] Khi producer thay field/path/status, có thể chỉ ra test nào phải thất bại.
- [ ] Có kế hoạch migration/version nếu API thay đổi không tương thích.
- [ ] Những nhu cầu concurrency/security/retry/latency được gán cho test khác phù hợp.
- [ ] CI và review thể hiện rõ yêu cầu nào COVERED, MISSING hoặc NOT REQUIRED.

## 21. Tài liệu tham khảo

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): kiến trúc producer/consumer contract testing, stub và build integration.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): method, URL, headers, request và response DSL.
- [Spring Cloud Contract — Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): producer/consumer values, response matchers và JSONPath.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): cách tìm/chạy stubs cho consumer.
- [Spring Cloud Contract — Developing Your First Application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): generated producer verification và consumer use of stubs.
- [Spring Cloud Contract — Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): các hợp đồng message theo destination, headers và payload.

**Ghi nhớ:** Kiểm tra nhu cầu consumer đã phản ánh trong hợp đồng nghĩa là **đi từ use case đến tiêu chí có thể kiểm chứng**, không chỉ xem Groovy/YAML đúng cú pháp. Một yêu cầu quan trọng phải truy được tới contract, generated producer assertions, stub đúng version và consumer behavior test. Khi cả hai phía và CI kiểm tra đúng những tín hiệu consumer phụ thuộc, nhóm mới có bằng chứng thực chất rằng API hoặc message contract đang bảo vệ sự tương thích cần thiết.
