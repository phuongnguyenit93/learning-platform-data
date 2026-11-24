# Đọc test và mapping được sinh để phát hiện nhầm hai phía

## Mục tiêu học tập

Trong chương **Giá trị hai phía** của **Spring Cloud Contract**, một hợp đồng Groovy/YAML mô tả tương tác giữa **producer** (dịch vụ cung cấp API hoặc phát thông điệp) và **consumer** (dịch vụ sử dụng API hoặc nhận thông điệp). Spring Cloud Contract dựa trên DSL để **sinh kiểm thử phía producer** và **sinh stub** cho consumer kiểm thử bằng **Stub Runner**.

Điểm dễ nhầm nhất xuất hiện khi hợp đồng chứa **giá trị động**: cùng một trường có thể cần **giá trị cụ thể** ở một phía nhưng cần **quy tắc khớp** ở phía còn lại. Muốn biết DSL đã được hiểu đúng hay chưa, hãy xem **generated test** và **stub mapping** thực tế sau khi build.

Sau bài học, bạn có thể:

- Giải thích chính xác vai trò của `consumer(...)` và `producer(...)` trong **request** và **response** của Groovy DSL.
- Dự đoán producer test sẽ **gửi giá trị nào**, **assert điều gì**, và stub sẽ **match request thế nào**, **trả response gì**.
- Tìm tệp generated test, WireMock mapping và artifact stub sau khi chạy Spring Cloud Contract với Maven hoặc Gradle.
- So sánh DSL nguồn với hai đầu ra để phát hiện đổi chỗ hai phía, regex quá rộng, fixture sai kiểu hoặc stub không đúng phiên bản.
- Áp dụng tư duy tương đương cho **YAML DSL**, rồi đưa kiểm tra vào quy trình CI nhằm phát hiện thay đổi API không tương thích.

## 1. Vì sao một hợp đồng có hai cách nhìn?

Giả sử **Checkout Service** là consumer gửi request tạo đơn giữ hàng tới **Reservation Service** là producer:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "requestId": "REQ-1001",
  "sku": "SKU-101",
  "quantity": 1
}
~~~

Producer trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "reservationId": "RSV-98241",
  "accepted": true
}
~~~

Hai trường `requestId` và `reservationId` có thể thay đổi giữa các lần tương tác. Consumer cần được phép gửi **requestId hợp lệ khác nhau**; producer test lại cần **một request cụ thể** để thực sự gọi ứng dụng. Ngược lại, producer được phép sinh nhiều `reservationId` hợp lệ; consumer test cần **một response cụ thể, ổn định** từ stub để kiểm tra logic.

Spring Cloud Contract giải quyết sự khác biệt này bằng các giá trị **hai phía**. Trong **Groovy DSL**, cặp:

~~~groovy
$(consumer(...), producer(...))
~~~

diễn tả cùng một trường theo góc nhìn của hai bên. Tên hàm thể hiện **vai trò trong hợp đồng**, nhưng **đầu ra sử dụng chúng khác nhau tùy trường nằm ở request hay response**.

### Bảng quy tắc quan trọng nhất

| Nơi khai báo | Giá trị `consumer(...)` dùng để làm gì? | Giá trị `producer(...)` dùng để làm gì? |
|---|---|---|
| **Request** | Quy tắc/giá trị **stub dùng để nhận request từ consumer** | Giá trị cụ thể mà **generated producer test gửi** tới producer |
| **Response** | Giá trị cụ thể mà **stub trả cho consumer** | Quy tắc/giá trị **generated producer test dùng để assert response thật** |

Hãy đọc bảng theo **hành động cụ thể** thay vì học thuộc máy móc “consumer là client, producer là server”. Đặc biệt, `consumer(...)` xuất hiện trong **response** thì vẫn điều khiển *response của stub*, dù response trong giao tiếp thực là do producer gửi đi.

~~~mermaid
flowchart TB
    D["Contract DSL<br/>consumer(...) / producer(...)"] --> T["Generated producer test"]
    D --> M["WireMock stub mapping"]
    T --> TR["Request từ phía producer(...)"]
    T --> TA["Assert response theo producer(...)"]
    M --> MR["Match request theo consumer(...)"]
    M --> MS["Trả response theo consumer(...)"]
~~~

**Quy tắc dễ nhớ:** generated test cần một request để *gửi* và một kỳ vọng để *kiểm tra*; stub cần một điều kiện để *nhận request* và một response để *trả*. Hai công cụ có những nhiệm vụ khác nhau nên sử dụng giá trị khác nhau của cùng một contract.

## 2. Ví dụ Groovy DSL hoàn chỉnh

Trong producer có cấu hình Spring Cloud Contract, tạo một file như `src/test/resources/contracts/reservations/createReservation.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tao reservation voi requestId hop le'

    request {
        method 'POST'
        url '/api/reservations'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
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
        status 201

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

Hai cặp giá trị động cần đọc theo vị trí:

**Trong request:**

~~~groovy
requestId: $(
    consumer(regex('REQ-[0-9]{4}')),
    producer('REQ-1001')
)
~~~

- Stub sẽ nhận một request có `requestId` phù hợp với mẫu `REQ-` và bốn chữ số, ví dụ `REQ-4321`.
- Generated test sẽ thực sự gửi `"requestId":"REQ-1001"` tới producer.
- Nếu chỉ nhìn thấy regex trong file DSL và tin rằng generated test gửi **chuỗi regex** là đã nhầm phía.

**Trong response:**

~~~groovy
reservationId: $(
    consumer('RSV-1001'),
    producer(regex('RSV-[0-9]+'))
)
~~~

- Stub trả `"reservationId":"RSV-1001"` để consumer có phản hồi ổn định.
- Generated test kiểm tra response thật có `reservationId` khớp mẫu `RSV-[0-9]+`, ví dụ `RSV-98241`.
- Nếu cho rằng producer thật phải luôn trả đúng `RSV-1001` chỉ vì đó là giá trị ở `consumer(...)`, ta đã nhầm nghĩa DSL.

`sku` và `quantity` không có cặp giá trị động nên có thể giữ làm ví dụ cố định trong cả hai đầu ra. `accepted` là boolean; không nên biến thành string `"true"` nếu consumer đang dựa vào kiểu boolean.

**Lưu ý:** ví dụ trên cố tình chỉ kiểm tra một tình huống hợp lệ. Với request sai định dạng, số lượng bằng 0 hoặc SKU không tồn tại, cần các hợp đồng/tình huống kiểm thử khác nếu consumer phụ thuộc những nhánh ấy.

## 3. Nhìn vào generated producer test: request thực và assertion thực

Sau khi cấu hình plugin và chạy bước sinh test, Spring Cloud Contract tạo mã kiểm thử dựa trên DSL. Đường dẫn phụ thuộc build, plugin và cấu hình, nhưng thường gặp:

~~~text
# Maven (cấu hình thường gặp)
target/generated-test-sources/contracts/

# Gradle (cấu hình thường gặp)
build/generated-test-sources/contracts/
~~~

Tên class, framework kiểm thử (RestAssured, MockMvc, WebTestClient và các biến thể), cách import, matcher và vị trí output có thể khác theo phiên bản Spring Cloud Contract. Vì vậy, **hãy mở chính file Java/Groovy test được sinh trong dự án** thay vì giả định output luôn giống hệt ví dụ trong tài liệu.

### Hình dạng generated test cần nhận ra

Một test minh họa ở mức hành vi có thể được đọc như sau (**mã giả mô tả các bước, không phải bản chép nguyên văn từ một phiên bản generator cụ thể**):

~~~text
TEST "createReservation":
  GIVEN
    POST /api/reservations
    Content-Type: application/json
    Accept: application/json
    request body:
      requestId = "REQ-1001"
      sku       = "SKU-101"
      quantity  = 1

  WHEN
    send request to real producer test environment

  THEN
    HTTP status = 201
    Content-Type = application/json
    response.accepted = true
    response.reservationId MATCHES "RSV-[0-9]+"
~~~

Hãy tìm chính xác hai ý:

1. **Request được tạo có giá trị mẫu `REQ-1001`** từ phía `producer(...)` của DSL, không phải regex của phía `consumer(...)`.
2. **Assertion của response kiểm tra regex `RSV-[0-9]+`** từ phía `producer(...)`, không bắt buộc producer luôn trả `RSV-1001`.

Ví dụ một đoạn Java biểu đạt **ý tưởng assertion**, không phải code được cam kết generator sẽ sinh đúng từng dòng:

~~~java
// Minh họa điều cần thấy khi đọc generated test:
String sentRequestId = "REQ-1001";
int expectedStatus = 201;

assertThat(actualStatus).isEqualTo(expectedStatus);
assertThat(actualBody.get("accepted")).isEqualTo(true);
assertThat((String) actualBody.get("reservationId"))
        .matches("RSV-[0-9]+");
~~~

Test producer cần một **base test class/cấu hình test** và dữ liệu nền phù hợp để gọi vào implementation thật. Nếu môi trường test tự sinh ID khác nhau mỗi lần nhưng vẫn khớp regex, contract test vẫn có thể hợp lệ. Nếu regex quá lỏng (chẳng hạn `.*`), test có thể không phát hiện ID vô nghĩa; đó là vấn đề chất lượng hợp đồng, không phải lỗi generator.

### Những dấu hiệu nhầm phía ngay trong generated test

| Quan sát khi đọc test | Cách diễn giải | Hành động |
|---|---|---|
| Test gửi `REQ-1001` | Đúng ví dụ đang thiết kế | Kiểm tra tiếp phần response assertion |
| Test cố gửi chuỗi `REQ-[0-9]{4}` như dữ liệu thông thường | Có thể đã đảo giá trị hoặc đặt matcher sai | So lại `request.body.requestId` và cách generator chuyển giá trị |
| Test assert response ID **bằng đúng `RSV-1001`** | Hợp đồng đang khóa một giá trị cố định | Nếu ID là động, xem lại `response` và matcher phía producer |
| Test chỉ assert ID tồn tại hoặc luôn match mọi chuỗi | Quy tắc quá lỏng | Viết matcher mô tả định dạng/ngữ nghĩa consumer cần |
| Test bỏ qua field `accepted` mà consumer phụ thuộc | Contract hoặc bước kiểm tra chưa đủ | Rà soát DSL, cấu hình và test sinh ra |
| Test báo lỗi dù response hợp lệ khác fixture | Có thể ràng buộc quá cứng | Tách ví dụ stub khỏi quy tắc producer bằng giá trị hai phía |

**Đừng sửa trực tiếp generated test để “chữa lỗi”.** Nếu test được sinh lại ở build sau, thay đổi đó sẽ mất. Hãy sửa DSL nguồn, dữ liệu fixture hoặc cấu hình sinh test rồi tạo lại và đọc output mới.

## 4. Nhìn vào stub mapping: request matcher và response trả về

Ở phía consumer, Spring Cloud Contract thường sinh **WireMock mapping** làm một phần của stub artifact. Khi **Stub Runner** tải và chạy artifact, mapping mô tả request nào được nhận và response nào được trả.

Các vị trí output thường cần tìm:

~~~text
# Maven, một layout thường gặp:
target/stubs/META-INF/<groupId>/<artifactId>/<version>/mappings/
target/<artifactId>-<version>-stubs.jar

# Gradle, một layout có thể gặp:
build/stubs/META-INF/<groupId>/<artifactId>/<version>/mappings/
~~~

Không cần đoán tên file JSON cụ thể. Hãy kiểm tra output của plugin, hoặc mở nội dung `*-stubs.jar` và thư mục `mappings` trong đó. Nếu dự án cấu hình đường dẫn custom hoặc phiên bản plugin khác, lấy vị trí **từ build thật**.

### WireMock mapping nhìn như thế nào?

Sau đây là **một mapping rút gọn để minh họa ngữ nghĩa**, không phải khẳng định generator luôn xuất JSON đúng từng key, cách sắp xếp hoặc biểu thức:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
      }
    },
    "bodyPatterns": [
      {
        "matchesJsonPath": "$[?(@.requestId =~ /REQ-[0-9]{4}/)]"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "RSV-1001",
      "accepted": true
    }
  }
}
~~~

Trong mapping thực, generator có thể dùng cách biểu diễn `matchesJsonPath`, `equalToJson`, body string, `jsonBody` hoặc các matcher WireMock khác; đồng thời có thể bổ sung điều kiện cho `sku` và `quantity`. **Điều cần xác minh là hành vi**, không phải một dạng JSON duy nhất:

- **Request matcher:** có chấp nhận `requestId` phù hợp `REQ-[0-9]{4}` không? Có kiểm tra đúng method, URL, header và các field quan trọng không?
- **Response:** có trả `201`, `reservationId: "RSV-1001"` và `accepted: true` không?
- **Kiểu dữ liệu:** `accepted` có thật sự là boolean trong JSON, hay vô tình bị serialize thành string?
- **Độ đặc hiệu:** mapping có match nhầm các request của hợp đồng khác không?

Trong ví dụ này, consumer test có thể gửi `REQ-4321`. Nếu stub đúng, response vẫn có thể mang `RSV-1001`. Điều đó **không phải lỗi của producer**: stub trả fixture có chủ đích để consumer kiểm tra nhánh xử lý, còn generated producer test mới kiểm tra implementation thực.

### Một bảng đối chiếu nhanh

| Câu hỏi | Đọc generated test | Đọc stub mapping |
|---|---|---|
| Request `requestId` phải như thế nào? | Gửi `REQ-1001` | Match `REQ-[0-9]{4}` |
| Response `reservationId` phải như thế nào? | Assert regex `RSV-[0-9]+` | Trả mẫu `RSV-1001` |
| `accepted` phải là kiểu gì? | Assert boolean `true` | Trả boolean `true` |
| Endpoint nào được gọi? | Gọi `POST /api/reservations` | Match `POST /api/reservations` |
| Test có đang gọi ứng dụng thật? | Có, nếu môi trường producer test được cấu hình đúng | Không; stub mô phỏng response |

Đây là lý do cần **đọc cả hai đầu ra**: một test producer chạy xanh không đủ để khẳng định consumer có thể gọi stub như mong muốn, còn stub mapping hợp lệ không chứng minh producer thật tuân thủ hợp đồng.

## 5. Bốn vị trí dễ đảo giá trị và triệu chứng

Hãy dùng bảng này khi review pull request có `consumer(...)` / `producer(...)`:

| Vị trí trong DSL | Đúng: consumer side | Đúng: producer side | Dấu hiệu khi đảo hoặc dùng nhầm |
|---|---|---|---|
| Request path / query | Pattern mà stub nhận | Path / query cụ thể generated test gửi | Stub chỉ match một path cứng hoặc test gửi một regex như path |
| Request header | Pattern/giá trị stub kiểm tra | Header cụ thể test gửi | Header động không match stub hoặc test gửi giá trị không hợp lệ |
| Request JSON/body | Pattern/giá trị stub nhận | Body cụ thể test gửi | Stub từ chối request hợp lệ; test producer không tạo được dữ liệu mẫu đúng |
| Response body / header | Giá trị cụ thể stub trả | Matcher/giá trị test assert | Stub trả chuỗi regex thay cho ID; test assert sai một ID cố định |

Một số phiên bản DSL/generator có kiểm tra để từ chối các tổ hợp không sinh được stub/test hoặc có thể tự tạo giá trị mẫu với ràng buộc nhất định. Vì vậy **không nên dự đoán một cách máy móc** rằng mọi lỗi đảo hai phía đều dẫn đến một kiểu output. Cách xác nhận chắc chắn nhất là **sinh lại test và mapping rồi xem thực tế**.

### Trường hợp A: request đặt regex ở phía producer

~~~groovy
// Không phù hợp với mục tiêu "test gửi một requestId cụ thể".
requestId: $(
    consumer('REQ-1001'),
    producer(regex('REQ-[0-9]{4}'))
)
~~~

Điều này có thể khiến stub chỉ chấp nhận một ID cố định thay vì nhận mọi ID đúng định dạng; generated test lại không có một giá trị request cụ thể như dự kiến hoặc phải dựa vào cách generator xử lý regex. Nếu consumer cần gửi nhiều requestId, hãy dùng:

~~~groovy
requestId: $(
    consumer(regex('REQ-[0-9]{4}')),
    producer('REQ-1001')
)
~~~

### Trường hợp B: response đặt regex ở phía consumer

~~~groovy
// Không phù hợp với mục tiêu "stub trả một ID mẫu ổn định".
reservationId: $(
    consumer(regex('RSV-[0-9]+')),
    producer('RSV-1001')
)
~~~

Phía stub cần có **dữ liệu response cụ thể** để trả, còn producer test cần kiểm tra định dạng ID động. Hợp đồng thích hợp hơn:

~~~groovy
reservationId: $(
    consumer('RSV-1001'),
    producer(regex('RSV-[0-9]+'))
)
~~~

### Trường hợp C: nhầm kiểu dữ liệu sau khi đổi DSL

~~~yaml
# Nếu accepted là boolean theo hợp đồng:
body:
  reservationId: 'RSV-1001'
  accepted: true
~~~

Khác với:

~~~yaml
# accepted giờ là chuỗi "true" trong YAML:
body:
  reservationId: 'RSV-1001'
  accepted: 'true'
~~~

Ngay cả khi test và stub đều được sinh thành công, thay đổi kiểu `boolean -> string` có thể làm consumer deserialize sai. Khi đọc mapping, hãy xem response JSON chứa `true` hay `"true"`. Khi đọc generated test, hãy xem assertion kiểm tra kiểu nào.

### Trường hợp D: request matcher quá rộng, mapping đè nhau

Giả sử có hai contract cùng match `POST /api/reservations` và chỉ khác response `accepted=true` so với `accepted=false`, nhưng request matcher của cả hai đều chấp nhận mọi body. Stub Runner/WireMock không thể biết tình huống nào người viết mong muốn chỉ từ request đó. Một mapping có thể “ăn” request của tình huống còn lại.

Cách sửa là cho request của từng tình huống có **điều kiện phân biệt có nghĩa** (mã SKU, trường trạng thái, header hoặc body hợp lệ theo giao diện). Đừng dùng thứ tự load mapping như một cách vô tình lựa chọn response.

## 6. YAML DSL: đọc `matchers` thay cho cặp giá trị Groovy

Trong **YAML DSL**, cùng ý tưởng hai phía thường được diễn đạt bằng **giá trị mẫu trong `body`** và **matcher trong `request.matchers` / `response.matchers`**.

Ví dụ YAML tương đương về mục đích với trường hợp tạo reservation:

~~~yaml
description: 'Tao reservation voi requestId hop le'
request:
  method: POST
  url: '/api/reservations'
  headers:
    Content-Type: 'application/json'
    Accept: 'application/json'
  body:
    requestId: 'REQ-1001'
    sku: 'SKU-101'
    quantity: 1
  matchers:
    body:
      - path: '$.requestId'
        type: by_regex
        value: 'REQ-[0-9]{4}'
response:
  status: 201
  headers:
    Content-Type: 'application/json'
  body:
    reservationId: 'RSV-1001'
    accepted: true
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

**Đừng hiểu sai rằng matcher nào cũng chạy ở cả hai phía:**

- `request.body.requestId: 'REQ-1001'` là **giá trị mẫu cụ thể** để generated producer test gửi.
- `request.matchers.body` là **quy tắc stub dùng để match request consumer gửi**.
- `response.body.reservationId: 'RSV-1001'` là **giá trị cụ thể stub trả**.
- `response.matchers.body` là **quy tắc generated producer test dùng để kiểm tra response producer thật**.

So sánh:

| YAML DSL | Mục đích tương ứng ở Groovy DSL |
|---|---|
| `request.body.requestId` | Giá trị `producer('REQ-1001')` trong request |
| `request.matchers.body` | Quy tắc `consumer(regex(...))` trong request |
| `response.body.reservationId` | Giá trị `consumer('RSV-1001')` trong response |
| `response.matchers.body` | Quy tắc `producer(regex(...))` trong response |

Đường dẫn JSONPath `$.requestId` và `$.reservationId` phải trỏ đúng trường trong JSON. Chỉ cần viết sai path, có thể khiến matcher không kiểm tra điều người viết tưởng đang được bảo vệ. YAML hợp lệ chưa đủ; cần generator chấp nhận **schema DSL của phiên bản Spring Cloud Contract đang dùng**.

## 7. Đọc output từng bước: một quy trình kiểm tra có thể lặp lại

Khi nhận một PR thay đổi giá trị động, hãy làm theo thứ tự sau.

### Bước 1: Chọn một hợp đồng và ghi kỳ vọng trước khi build

Với `createReservation.groovy`, ghi lại:

~~~text
KỲ VỌNG PHÍA GENERATED PRODUCER TEST
- Gửi POST /api/reservations.
- Gửi requestId = REQ-1001.
- Expect HTTP 201.
- Assert reservationId khớp RSV-[0-9]+.
- Assert accepted = true (boolean).

KỲ VỌNG PHÍA STUB MAPPING
- Match POST /api/reservations.
- Match requestId theo REQ-[0-9]{4}.
- Trả HTTP 201.
- Trả reservationId = RSV-1001.
- Trả accepted = true (boolean).
~~~

Việc ghi trước kỳ vọng giúp tránh một sai lầm tâm lý phổ biến: thấy output của generator rồi tự mặc định đó là điều mình định nghĩa.

### Bước 2: Sinh output bằng build của producer

Các lệnh tham khảo khi module producer đã cấu hình plugin phù hợp:

~~~bash
# Maven: sinh test theo cấu hình plugin; mục tiêu thực tế phụ thuộc version.
./mvnw generate-test-sources

# Maven: build/kiểm thử đầy đủ theo lifecycle đã cấu hình.
./mvnw verify

# Gradle: xem tên task do plugin cung cấp.
./gradlew tasks --all
~~~

Tên goal/task cụ thể, việc sinh stub trước hay sau bước test, và vị trí đầu ra phụ thuộc plugin. Hãy dùng **log build của module producer** làm nguồn xác nhận. Không tự kết luận thành công chỉ vì process trả exit code 0 khi plugin chưa được cấu hình để đọc hợp đồng.

### Bước 3: Đọc generated test

Tìm file tương ứng với tên contract. Xác nhận method, URL, request header/body, status và assertion response. Nếu test gửi một chuỗi trông như regex thay vì ví dụ hợp lệ, cần quay lại DSL và phân biệt `consumer(...)` / `producer(...)`.

Đặc biệt kiểm tra assertion:

- Kiểu JSON: string, number, boolean.
- Regex có bảo vệ đúng định dạng không?
- Có kiểm tra field bắt buộc mà consumer cần không?
- Với status lỗi, có assert đúng status/mã lỗi không?
- Với dữ liệu động, có vô tình khóa một ID hoặc timestamp cố định không?

### Bước 4: Đọc stub mapping

Tìm JSON mapping của contract (thường nằm trong thư mục `mappings` bên trong stub artifact). Xác nhận:

- `request.method`, path/path pattern, header.
- Quy tắc body/query phù hợp với hành vi mà consumer cần gửi.
- `response.status`, header và body mẫu cụ thể.
- Các contract khác có mapping trùng hoặc chồng lấn điều kiện không?

Một mapping có thể đúng về cú pháp nhưng **không match request thật của consumer** vì path, header, regex hoặc body type khác nhau. Đó là nguyên nhân phổ biến của phản hồi WireMock “no matching stub mapping”.

### Bước 5: Chạy test consumer với đúng artifact

Consumer dùng Stub Runner để tải/chạy stub đã tạo, rồi gọi bằng **HTTP client thật của ứng dụng**. Ví dụ test cần xác nhận khi nhận `RSV-1001`, Checkout có thể đọc `reservationId` và lưu/hiển thị kết quả mà không dựa vào một giá trị được hardcode trong ứng dụng.

Nếu consumer test gọi nhầm producer thật hoặc dùng stub của phiên bản cũ, việc test xanh **không chứng minh contract trong PR tương thích**.

### Bước 6: Ghi kết luận trong PR

Nên ghi:

- Commit/revision của DSL.
- Generated test nào đã được đọc và kết quả producer test.
- Mapping nào trong artifact stub, tọa độ/version và các điều kiện match đáng chú ý.
- Test consumer nào chạy với chính artifact đó.
- Các thay đổi tương thích hoặc chưa tương thích được phát hiện.

Báo cáo này giúp người review kết luận dựa trên bằng chứng thực tế thay vì chỉ đánh giá file Groovy/YAML bằng mắt.

## 8. Khi “test xanh” nhưng hợp đồng vẫn sai

Cần phân biệt những cấp độ kiểm chứng:

| Bằng chứng | Điều nó chứng minh được | Điều chưa chắc chứng minh |
|---|---|---|
| DSL parse thành công | File được công cụ đọc và hiểu ở mức cú pháp/schema | Phân vai hai phía đã đúng mục đích |
| Generated test được sinh | Plugin đã tạo ra mã test | Assertion đủ chặt hoặc test đã thực sự chạy |
| Producer generated test xanh | Producer đáp ứng những trường hợp contract mới mô tả | Consumer cũ còn tương thích |
| Mapping WireMock tồn tại | Stub đã có cấu hình mô phỏng | Request thực của consumer sẽ match |
| Consumer test với stub xanh | Consumer hiểu và xử lý đúng response của **stub được dùng** | Producer thật đáp ứng hợp đồng hoặc stub đang là bản mới |
| Hai phía xanh với cùng revision | Có bằng chứng cho hành vi đã được bao phủ | Mọi yêu cầu nghiệp vụ, lỗi biên và môi trường production đều đúng |

**Một lỗi đặc biệt nguy hiểm:** người viết sửa cả contract và implementation producer, producer test xanh, nhưng contract mới đã đổi `reservationId` từ string sang number. Consumer cũ deserialize theo string có thể lỗi. Cần kiểm tra tương thích và chạy consumer test với **candidate stub**, chứ không chỉ đọc kết quả producer test.

## 9. Bài thực hành: phát hiện đảo hai phía trong PR

Một PR cho endpoint `POST /api/reservations` chứa đoạn Groovy sau:

~~~groovy
request {
    method 'POST'
    url '/api/reservations'
    headers {
        contentType(applicationJson())
    }
    body(
        requestId: $(
            consumer('REQ-1001'),
            producer(regex('REQ-[0-9]{4}'))
        )
    )
}

response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        reservationId: $(
            consumer(regex('RSV-[0-9]+')),
            producer('RSV-1001')
        )
    )
}
~~~

Yêu cầu nghiệp vụ thực tế:

- Consumer có thể gửi bất kỳ `requestId` dạng `REQ-` và đúng bốn chữ số.
- Producer test cần gửi một `requestId` cụ thể như `REQ-1001`.
- Producer thật được phép tạo nhiều `reservationId` theo mẫu `RSV-[0-9]+`.
- Stub cần trả `RSV-1001` ổn định cho consumer test.

**Câu hỏi:**

1. Có bao nhiêu nơi đang đặt nhầm phía?
2. Generated producer test và stub mapping có thể xuất hiện những dấu hiệu gì?
3. Sửa DSL thế nào để hai đầu ra đáp ứng yêu cầu?

### Đáp án và lý do

**Có hai nơi đặt ngược**: `request.requestId` và `response.reservationId`.

Phiên bản sửa:

~~~groovy
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
        )
    )
}

response {
    status 201
    headers {
        contentType(applicationJson())
    }
    body(
        reservationId: $(
            consumer('RSV-1001'),
            producer(regex('RSV-[0-9]+'))
        )
    )
}
~~~

**Đọc đầu ra kỳ vọng sau sửa:**

| Kiểm tra | Kết quả đúng |
|---|---|
| Generated test gửi request | `requestId = REQ-1001` |
| Generated test kiểm tra response | `reservationId` phù hợp `RSV-[0-9]+` |
| Stub request matcher | Chấp nhận `REQ-1001`, `REQ-4321` và các giá trị hợp lệ cùng dạng |
| Stub response | Trả `reservationId = RSV-1001` |

Nếu test đã sinh không giống bảng, cần kiểm tra file DSL thực sự được plugin đọc, version, matcher và các cấu hình override trước khi kết luận generator có lỗi.

### Thử thêm một tình huống YAML

~~~yaml
request:
  method: POST
  url: '/api/reservations'
  body:
    requestId: 'REQ-1001'
  matchers:
    body:
      - path: '$.requestId'
        type: by_regex
        value: 'REQ-[0-9]{4}'
response:
  status: 201
  body:
    reservationId: 'RSV-1001'
  matchers:
    body:
      - path: '$.reservationId'
        type: by_regex
        value: 'RSV-[0-9]+'
~~~

Tự trả lời: `request.matchers` đi vào **generated test** hay **stub mapping**? `response.matchers` dùng để kiểm tra giá trị ở phía nào?

**Đáp án:** `request.matchers` quy định matching phía **stub**; `response.matchers` quy định assertion của **generated producer test**. Request và response body giữ các ví dụ cụ thể cho phía còn lại.

## 10. Checklist review khi đọc test và mapping sinh ra

- [ ] Đã xác nhận đúng file DSL, revision và phiên bản Spring Cloud Contract mà build sử dụng.
- [ ] Với **request**, generated test gửi **giá trị producer cụ thể**; stub match theo **giá trị/quy tắc consumer**.
- [ ] Với **response**, generated test assert theo **giá trị/quy tắc producer**; stub trả **giá trị consumer cụ thể**.
- [ ] Các regex kiểm soát đúng định dạng, không vô tình mở rộng thành `.*`.
- [ ] JSON type của field quan trọng được giữ đúng (string, number, boolean, null, array/object).
- [ ] Header, URL, query và body matcher không bị bỏ sót hoặc chồng lấn giữa nhiều contract.
- [ ] Generated test thực sự chạy với producer test environment có trạng thái được kiểm soát.
- [ ] Stub artifact chứa mapping vừa kiểm tra và được xuất bản với version có thể truy vết.
- [ ] Consumer test gọi đúng cổng Stub Runner và chạy client thật với **cùng candidate stub**.
- [ ] Thay đổi có nguy cơ phá vỡ consumer cũ đã được đánh giá và có kế hoạch chuyển đổi.
- [ ] CI lưu bằng chứng producer test, artifact stub và consumer test theo cùng revision.

## 11. Ghi nhớ

Khi dùng giá trị hai phía trong **Spring Cloud Contract**, đừng đoán hành vi bằng tên `consumer(...)` / `producer(...)` một cách tách rời. **Trong request:** stub dùng phía consumer để match, còn generated producer test gửi phía producer. **Trong response:** stub trả phía consumer, còn generated test kiểm tra phía producer. Với **YAML DSL**, giá trị mẫu trong `body` đi cùng `request.matchers` / `response.matchers` theo quy tắc tương ứng.

Cách phát hiện nhầm chắc chắn nhất là **đọc cả generated test và WireMock stub mapping được sinh từ cùng revision**, rồi chạy test producer và consumer với đúng phiên bản stub. Khi đưa việc đối chiếu này vào review/CI, nhóm có thể bắt được lỗi đảo giá trị, matcher sai, body sai kiểu hoặc thay đổi API không tương thích trước khi phát hành.
