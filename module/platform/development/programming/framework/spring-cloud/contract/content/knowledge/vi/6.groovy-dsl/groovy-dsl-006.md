# Hàm hỗ trợ và biểu thức trong Groovy DSL

## 1. Vai trò của hàm hỗ trợ trong Spring Cloud Contract

**Spring Cloud Contract** giúp producer và consumer kiểm tra sự tương thích bằng cách mô tả hành vi HTTP hoặc thông điệp trong hợp đồng. Khi dùng **Groovy DSL**, ta không chỉ ghi các giá trị cố định như `method 'GET'` hay `status 200` mà còn dùng **hàm hỗ trợ (helper)** và **biểu thức (expression)** để diễn tả quy tắc:

- Request nào từ consumer được coi là hợp lệ để **stub** trả kết quả?
- Producer thực sự phải trả chính xác giá trị nào, hay chỉ phải đáp ứng một định dạng?
- Khi JSON chứa UUID, timestamp hoặc giá trị sinh động, làm thế nào tránh test thất bại giả?
- Khi phản hồi phải lặp lại dữ liệu request, có thể diễn đạt quan hệ đó như thế nào?
- Khi matcher cơ bản chưa đủ, có thể gọi một hàm kiểm tra riêng từ test được sinh ra không?

Các quy tắc này được dùng theo hai hướng: **Spring Cloud Contract Verifier** sinh test kiểm chứng producer và sinh stub (thường là WireMock mapping cho HTTP); **Stub Runner** đưa stub vào kiểm thử của consumer. Biểu thức đặt sai phía có thể khiến stub từ chối request hợp lệ hoặc khiến generated test so sánh sai phản hồi của producer.

Bài học thuộc chương **Groovy DSL**, tập trung vào các helper thông dụng, cú pháp biểu thức, nguyên tắc chọn matcher và những tình huống dễ nhầm. YAML DSL vẫn là lựa chọn hợp lệ trong Spring Cloud Contract, nhưng các ví dụ về `value()`, `$()`, `execute()` và `fromRequest()` dưới đây dành cho Groovy DSL.

## 2. Khung Groovy DSL và các helper nền tảng

Một hợp đồng HTTP tối thiểu có thể viết như sau:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Trả thông tin đơn hàng đã thanh toán'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header 'Accept', 'application/json'
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            state: 'PAID',
            currency: 'VND'
        )
    }
}
```

`Contract.make { ... }` tạo mô tả một hợp đồng; `request`, `response` và `headers` là các khối cấu hình (Groovy *closure*). Những lời gọi như `method GET()`, `status OK()`, `contentType(applicationJson())` là các helper thuộc DSL, được xử lý khi hợp đồng được biên dịch để sinh test và stub.

| Nhóm | Lời gọi thường gặp | Ý nghĩa và lưu ý |
|---|---|---|
| HTTP method | `GET()`, `POST()`, `PUT()`, `DELETE()`, hoặc `method 'GET'` | Xác định phương thức HTTP; có thể dùng chuỗi trực tiếp |
| URL | `url '/api/orders/42'`, `urlPath('/api/orders') { ... }` | `urlPath` cho phép mô tả query parameter riêng, dễ review |
| Query | `queryParameters { parameter('page', 1) }` | Đặt trong closure URL/URL path khi contract dùng query |
| HTTP status | `OK()`, `NOT_FOUND()`, `status 201` | Helper trả mã trạng thái tương ứng; số trực tiếp cũng hợp lệ |
| Header | `header('X-Client', 'checkout')` | Khai báo header và giá trị cần kiểm tra/trả về |
| Content type | `contentType(applicationJson())` | Thuận tiện cho `Content-Type: application/json` |
| Body | `body(id: 42, state: 'PAID')` | Map Groovy mô tả JSON object |
| Metadata | `description '...'`, `name '...'`, `priority 1` | Diễn tả mục đích, định danh hoặc độ ưu tiên chọn stub khi cần |

Có thể viết các lời gọi Groovy với hoặc không có dấu ngoặc, ví dụ `method 'GET'` và `method('GET')`. Nên chọn một phong cách nhất quán trong repository. `description` là diễn giải cho người đọc, còn `name` có thể hỗ trợ định danh trường hợp test; tránh tên quá chung như `test1`.

### 2.1. Query parameter: ví dụ dễ đọc

```groovy
request {
    method GET()
    urlPath('/api/orders') {
        queryParameters {
            parameter('state', 'PAID')
            parameter('limit', 10)
        }
    }
}
```

Với cấu trúc này, việc sửa `limit` hoặc thêm tiêu chí lọc được review tại đúng nơi mô tả query. Chỉ dùng matcher linh hoạt khi nghiệp vụ cho phép nhiều giá trị; nếu consumer thực sự gửi `state=PAID` thì kiểm tra đúng giá trị đó thường dễ bảo trì hơn một regex quá rộng.

## 3. Biểu thức động: `value()` và `$()`

### 3.1. Hai phía của một giá trị

Đặc trưng quan trọng của Groovy DSL là **một trường có thể có cách mô tả khác nhau cho consumer và producer**:

```groovy
value(consumer(...), producer(...))
$(consumer(...), producer(...))

// Các alias tương đương:
$(c(...), p(...))
$(stub(...), test(...))
$(client(...), server(...))
```

Hai cú pháp `value(...)` và `$(...)` có cùng mục đích. `c` là alias của `consumer`; `p` là alias của `producer`. Tên `stub`/`test` gợi nhớ môi trường sử dụng, nhưng **ý nghĩa của giá trị phụ thuộc nó nằm trong `request` hay `response`**.

| Vị trí | Phía consumer / stub | Phía producer / test |
|---|---|---|
| **Request** | Điều kiện khớp request mà stub chấp nhận, ví dụ regex mã đơn hàng | Giá trị request cụ thể generated test sẽ gửi vào producer |
| **Response** | Giá trị response cụ thể mà stub trả cho consumer | Điều kiện/assertion generated test dùng để kiểm chứng response thực tế |

Tại sao phải tách hai phía? Giả sử consumer gửi một mã đơn hàng phù hợp mẫu `ORD-[0-9]+`. Stub nên chấp nhận nhiều mã thỏa mẫu đó, nhưng test producer vẫn cần **một giá trị mẫu xác định** để chuẩn bị fixture. Ngược lại, producer có thể tạo mã theo dõi ngẫu nhiên; test chỉ cần xác nhận mã đúng cấu trúc, trong khi stub vẫn phải gửi một giá trị mẫu cụ thể để consumer kiểm thử.

### 3.2. Request: consumer dùng regex, producer dùng giá trị mẫu

```groovy
request {
    method GET()
    url value(
        consumer(regex('/api/orders/[0-9]+')),
        producer('/api/orders/42')
    )
}
```

Từ đây có hai hành vi:

1. **Stub phía consumer** có thể nhận `GET /api/orders/42`, `GET /api/orders/71`, ... nếu URL khớp regex.
2. **Test phía producer** gửi `GET /api/orders/42` để có input cụ thể mà hệ thống test có thể dựng dữ liệu.

Không nên hiểu regex ở phía consumer là yêu cầu producer phải “tự sinh mọi URL”. Đây là quy tắc khớp request của stub. Producer test chỉ thực thi kịch bản cụ thể do DSL tạo ra; để kiểm thử thêm nghiệp vụ của các ID khác cần viết kịch bản khác.

**Chú ý tính nhất quán của stub:** nếu regex cho phép mọi ID nhưng response được viết cứng là đơn hàng `42`, stub có thể trả dữ liệu của đơn hàng `42` cho request `/api/orders/71`. Chỉ mở rộng matcher khi phản hồi mẫu vẫn phù hợp với các request được chấp nhận, hoặc sử dụng `fromRequest()`/nhiều kịch bản để giữ quan hệ đúng giữa ID request và dữ liệu response. Trong những bài test cần đúng đơn hàng, so khớp một ID cụ thể thường an toàn hơn.

### 3.3. Response: consumer nhận giá trị mẫu, producer được kiểm tra bằng regex

```groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        orderId: 42,
        state: 'PAID',
        trackingId: $(
            consumer('TRK-A1B2C3D4'),
            producer(regex('TRK-[A-Z0-9]{8}'))
        )
    )
}
```

Stub sẽ trả `trackingId: "TRK-A1B2C3D4"` để consumer có dữ liệu dự đoán được. Generated producer test sẽ chấp nhận các mã như `TRK-9A8B7C6D` nếu khớp định dạng đã cam kết. Trong khi đó `state: 'PAID'` là giá trị nghiệp vụ cần giữ chính xác, nên không cần nới lỏng thành `.*`.

**Bẫy phổ biến:** đảo hai phía thành `consumer(regex(...))` và `producer('TRK-A1B2C3D4')` trong *response*. Cách đó làm test producer đòi một mã cố định, còn stub lại phải tạo một ví dụ dựa vào regex. Hãy xem lại bảng request/response trước khi chọn phía.

## 4. Helper cho regex và kiểu dữ liệu

### 4.1. `regex(...)`, `~/.../` và nguyên tắc khớp toàn bộ

Groovy DSL có thể dùng:

```groovy
regex('[A-Z]{3}-[0-9]{4}')

// Cú pháp Pattern của Groovy, ví dụ một đường dẫn:
~/\/api\/orders\/[0-9]+/
```

Regex có thể được đưa vào `consumer(...)`, `producer(...)` hoặc `byRegex(...)` tùy vị trí. Trình so khớp dùng quy tắc **khớp toàn bộ chuỗi** ở nhiều chỗ, nên regex `[0-9]{3}` không tương đương với “chuỗi chứa ba chữ số ở bất kỳ đâu”. Muốn khớp mọi chuỗi chứa một đoạn, phải mô tả toàn bộ cấu trúc dự kiến, nhưng không nên dùng `.*` thiếu kiểm soát.

Sự khác biệt giữa chuỗi Groovy cũng quan trọng:

- `'...'` là chuỗi thường, không nội suy biểu thức của Groovy; thích hợp với nhiều regex/JSONPath.
- `"..."` có thể tạo GString và nội suy khi chứa biến hoặc biểu thức; hữu ích khi thực sự cần tạo văn bản động, nhưng dễ gây lỗi với ký tự `$`.
- Với JSONPath như `'$.orderId'`, dùng dấu nháy đơn thường dễ tránh nội suy nhầm.
- Regex có dấu gạch chéo, dấu gạch ngược hoặc ký tự đặc biệt cần kiểm tra phép escape đúng với **Groovy** và với **regex**; đây là hai tầng biểu diễn khác nhau.

### 4.2. Các helper tạo pattern có sẵn

Spring Cloud Contract cung cấp nhiều hàm tạo regex thường dùng:

| Helper | Mục đích | Ví dụ vị trí sử dụng |
|---|---|---|
| `onlyAlphaUnicode()`, `alphaNumeric()` | Chuỗi ký tự chữ hoặc chữ-số | Mã hiển thị, mã tham chiếu |
| `number()`, `anInteger()`, `positiveInt()`, `aDouble()` | Kiểu số | Số lượng, ID số, tiền |
| `anyBoolean()` | Giá trị boolean | Cờ kết quả |
| `uuid()`, `uuid4()` | Định dạng UUID | Correlation ID |
| `email()`, `hostname()`, `ipAddress()` | Định dạng thường gặp | Email, host/IP của dữ liệu |
| `isoDate()`, `isoDateTime()`, `isoTime()`, `iso8601WithOffset()` | Ngày và thời gian | Trường thời điểm |
| `nonEmpty()`, `nonBlank()` | Chuỗi không rỗng hoặc không toàn khoảng trắng | Tên/ghi chú bắt buộc |

Ngoài những helper trả **pattern**, có các dạng tiện ích tạo **giá trị động** mang tiền tố `any...`, chẳng hạn `anyNumber()`, `anyInteger()`, `anyPositiveInt()`, `anyUuid()`, `anyDateTime()`, `anyNonBlankString()` và `anyOf('PAID', 'PENDING')`. Chúng hỗ trợ những trường hợp DSL cần tự sinh một ví dụ phù hợp matcher.

```groovy
response {
    status OK()
    body(
        correlationId: $(anyUuid()),
        count: $(anyPositiveInt())
    )
}
```

Ở ví dụ trên, hàm tiện ích làm giảm công viết regex thủ công. Tuy nhiên, **khả năng chấp nhận dữ liệu không đồng nghĩa với đúng nghiệp vụ**: nếu `state` chỉ được là `PAID` hoặc `PENDING`, không nên thay bằng một chuỗi không rỗng bất kỳ.

### 4.3. Kiểu khi dùng regex

Trong `bodyMatchers`, regex mô tả giá trị mong đợi và có thể kèm thông tin kiểu:

```groovy
bodyMatchers {
    jsonPath('$.count', byRegex(anInteger()).asInteger())
    jsonPath('$.totalAmount', byRegex(number()).asDouble())
    jsonPath('$.active', byRegex(anyBoolean()).asBooleanType())
}
```

Tránh dùng regex chỉ kiểm tra hình dạng chuỗi khi consumer phụ thuộc **kiểu JSON thật**. Một JSON number và một JSON string chứa chữ số có thể gây khác biệt lớn với client. Với số tiền, kiểu và giới hạn giá trị (không âm, độ chính xác, đơn vị) phải phù hợp cam kết nghiệp vụ.

### 4.4. Matcher quá rộng và matcher quá chặt

| Trường | Matcher dễ gây lỗi | Matcher thích hợp hơn |
|---|---|---|
| `orderId` dạng `ORD-42` | `.*` | `ORD-[0-9]+` |
| `state` chỉ có `PAID` tại tình huống cụ thể | Bất kỳ chuỗi | Giá trị cố định `PAID` |
| `totalAmount` phải là số nguyên dương | `[0-9]*` cho phép rỗng | `positiveInt()` hoặc giới hạn chặt theo nghiệp vụ |
| `trackingId` có 8 ký tự chữ hoa/số sau tiền tố | Giá trị ví dụ cố định cho producer test | `TRK-[A-Z0-9]{8}` |
| `createdAt` sinh tại runtime | So sánh timestamp cụ thể mọi lần | `byTimestamp()`/`isoDateTime()` đúng định dạng cam kết |

Nếu phụ thuộc vào khả năng tự **sinh chuỗi từ regex**, cần lưu ý các giới hạn của bộ sinh chuỗi; đặc biệt nên tránh đưa `^`/`$` vào pattern dùng để sinh giá trị tự động khi thư viện phiên bản đang dùng không xử lý ổn định. Cách chắc chắn cho kịch bản quan trọng là chỉ rõ một giá trị mẫu hợp lệ và dùng regex ở phía cần matcher.

## 5. `bodyMatchers` và các helper JSONPath

Đặt matcher bên trong `body` tiện cho trường hợp đơn giản; với nhiều thuộc tính cần quy tắc riêng, `bodyMatchers` làm mục tiêu so khớp rõ ràng hơn. Điểm quan trọng là cùng cú pháp `bodyMatchers` có vai trò khác nhau:

- Trong **`request`**, nó mô tả **stub matchers** để phân biệt request nào được consumer gửi tới stub.
- Trong **`response`**, nó mô tả **test matchers** để generated producer test xác minh phản hồi thực tế.

### 5.1. Ví dụ hoàn chỉnh dùng matcher hai phía

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tạo đơn hàng và trả mã tham chiếu có định dạng'

    request {
        method POST()
        url '/api/orders'
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: 'C-42',
            quantity: 2
        )
        bodyMatchers {
            // Stub chấp nhận nhiều customerId cùng định dạng.
            jsonPath('$.customerId', byRegex('C-[0-9]+').asString())
            jsonPath('$.quantity', byRegex(positiveInt()).asInteger())
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            state: 'CREATED',
            trackingId: 'TRK-A1B2C3D4',
            generatedAt: '2026-11-24T01:02:03'
        )
        bodyMatchers {
            jsonPath('$.state', byEquality())
            jsonPath('$.trackingId', byRegex('TRK-[A-Z0-9]{8}'))
            jsonPath('$.generatedAt', byTimestamp())
        }
    }
}
```

Giải thích từng điểm:

1. Producer test vẫn gửi request mẫu có `customerId = C-42` và `quantity = 2`. Fixture producer phải đáp ứng dữ liệu này.
2. Stub có thể khớp các `customerId` theo `C-[0-9]+` và số lượng hợp lệ theo matcher thay vì chỉ đúng một chuỗi JSON.
3. `state` được kiểm tra bằng `byEquality()` vì `CREATED` là kết quả nghiệp vụ cụ thể của kịch bản.
4. `trackingId` được xác minh bằng regex và `generatedAt` được xác minh bằng helper timestamp; vì vậy producer có thể sinh giá trị khác mỗi lần chạy.
5. Stub trả những giá trị body mẫu đã ghi để consumer có thể kiểm thử một cách có thể lặp lại.

### 5.2. Bảng các loại matcher thường gặp

| Matcher | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `byEquality()` | Bằng giá trị đã mô tả trong body | Trạng thái nghiệp vụ, hằng số |
| `byRegex('...')` | Khớp biểu thức chính quy | ID, mã tham chiếu, cấu trúc chuỗi |
| `byDate()` | Khớp định dạng ngày ISO mà verifier hỗ trợ | `yyyy-MM-dd` |
| `byTime()` | Khớp định dạng thời gian | Thời điểm trong ngày |
| `byTimestamp()` | Khớp timestamp theo định dạng được hỗ trợ | Dữ liệu tạo thời điểm |
| `byType()` | Kiểm tra kiểu của trường so với giá trị mẫu | Số, chuỗi, danh sách/đối tượng |
| `byType { minOccurrence(...); maxOccurrence(...) }` | Ràng buộc số phần tử theo ngữ cảnh collection | Danh sách kết quả |
| `byNull()` | Trường có giá trị null | Khi API cam kết JSON null |
| `byCommand('method($it)')` | Gọi helper kiểm tra tùy chỉnh trong generated test | Điều kiện nghiệp vụ khó viết bằng regex |

**Phạm vi hỗ trợ khác nhau:** `byEquality`, `byRegex`, `byDate`, `byTime` và `byTimestamp` dùng được trong các matcher request/response theo khả năng của verifier. Các matcher như `byCommand` và `byNull` được sử dụng cho xác minh **phía producer response**, không tùy tiện đặt ở request và mong Stub Runner chạy code Java từ base test.

### 5.3. Kiểm tra kiểu và độ dài danh sách

```groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(
        items: [
            [id: 42, state: 'PAID']
        ]
    )
    bodyMatchers {
        jsonPath('$.items', byType {
            minOccurrence(1)
            maxOccurrence(20)
        })
    }
}
```

`byType` sử dụng kiểu từ dữ liệu mẫu ở `body`; đối với collection, matcher có thể có `minOccurrence`, `maxOccurrence`. Khi dùng JSONPath dẫn tới cấu trúc lồng nhau, cần hiểu cách các phần tử được làm phẳng trong cơ chế matcher để không kiểm tra nhầm kích thước. Nếu yêu cầu đếm phần tử đặc biệt phức tạp, có thể dùng `byCommand` và một phương thức kiểm tra riêng.

**Phân biệt null và thiếu trường:** `byNull()` diễn tả giá trị `null`, không nhất thiết đồng nghĩa rằng thuộc tính hoàn toàn vắng mặt. Hãy xác định hành vi consumer thật sự dựa vào trước khi viết matcher.

## 6. `optional()` và các giá trị tùy chọn

Đôi khi giao diện cho phép một trường xuất hiện hoặc không. Groovy DSL có helper `optional(...)`:

```groovy
request {
    method POST()
    url '/api/customers'
    headers {
        contentType(applicationJson())
    }
    body(
        email: $(
            consumer(optional(regex(email()))),
            producer('demo@example.test')
        )
    )
}
```

`optional()` có phạm vi sử dụng đặc biệt: **phía stub của request** và **phía test của response**. Nó biểu diễn phần có thể tùy chọn trong cơ chế so khớp; không nên hiểu rằng chỉ cần bọc `optional` là mọi tình huống “vắng cả property JSON” đều tự được xác minh theo ý định nghiệp vụ. Nếu “có field” và “không có field” dẫn tới hai hành vi khác nhau, cân nhắc tách thành các hợp đồng riêng để test rõ ràng.

Ở ví dụ, producer test vẫn dùng email mẫu `demo@example.test`. Test producer **không tự thử cả hai nhánh** email có/không có; muốn bảo vệ cả hai hành vi phải có test/kịch bản tương ứng.

## 7. Tham chiếu request khi tạo response bằng `fromRequest()`

Khi API echo một phần yêu cầu hoặc đưa correlation ID từ request sang response, nếu gắn cứng giá trị ở cả hai nơi, hợp đồng dễ vỡ khi sửa dữ liệu. `fromRequest()` cho phép thể hiện **mối quan hệ giữa request và response**:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        url '/api/echo'
        headers {
            contentType(applicationJson())
            header('X-Request-Id', 'req-123')
        }
        body(
            orderId: 42,
            action: 'CONFIRM'
        )
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: fromRequest().body('$.orderId'),
            requestId: fromRequest().header('X-Request-Id'),
            path: fromRequest().path()
        )
    }
}
```

Trong kịch bản này, response phải phản ánh `orderId`, `X-Request-Id` và đường dẫn thực tế của request. Cách viết đó có giá trị khi muốn ngăn producer trả sai dữ liệu tham chiếu mà không ràng buộc response vào một literal độc lập.

| Hàm | Ý nghĩa |
|---|---|
| `fromRequest().url()` | URL request gồm query parameters |
| `fromRequest().path()` | Đường dẫn không gồm query string |
| `fromRequest().path(index)` | Một thành phần đường dẫn theo chỉ số |
| `fromRequest().query('key')` | Giá trị query đầu tiên của key |
| `fromRequest().query('key', index)` | Giá trị query theo chỉ số khi có nhiều giá trị cùng tên |
| `fromRequest().header('Header-Name')` | Giá trị header đầu tiên của tên tương ứng |
| `fromRequest().body()` | Toàn bộ body request |
| `fromRequest().body('$.field')` | Giá trị được chọn trong JSON body bằng JSONPath |

Ở phía stub HTTP, cơ chế này có thể được chuyển thành **WireMock response templating**. Khi thiết lập repository và Stub Runner, cần bảo đảm phiên bản/cấu hình WireMock tương thích với kiểu template được sinh. Trong YAML DSL, cơ chế tương tự thường dùng Handlebars và các helper tương ứng thay cho gọi trực tiếp `fromRequest()`.

## 8. `execute()` và `byCommand()`: gọi hàm trong base test

Regex không phù hợp với mọi ràng buộc. Chẳng hạn doanh nghiệp có quy tắc phức tạp cho giá tiền, mã quyền truy cập hoặc chữ ký dữ liệu. Khi đó có thể đặt logic kiểm tra trong **base class của generated test** và tham chiếu bằng DSL.

### 8.1. `byCommand()`: kiểm tra giá trị nhận từ producer

Trong Groovy contract:

```groovy
response {
    status OK()
    body(
        totalAmount: 120000
    )
    bodyMatchers {
        jsonPath('$.totalAmount', byCommand('assertPositiveAmount($it)'))
    }
}
```

Trong base test Java mà generated tests kế thừa:

```java
public abstract class ContractVerifierBase {

    protected void assertPositiveAmount(Number value) {
        if (value == null || value.doubleValue() <= 0) {
            throw new AssertionError("totalAmount must be positive");
        }
    }
}
```

`$it` là placeholder chỉ giá trị lấy được qua JSONPath trong code test được sinh ra; nó **không phải biến Groovy phải tự khai báo trong file contract**. Nên kiểm tra kiểu giá trị đầu vào của helper, vì JSONPath có thể đưa vào `String`, `Number`, `Map` hoặc `List` tùy expression. Phương thức trong base test phải được generated test truy cập được; ví dụ trên là mã minh họa cho phần validation, cần kết hợp với setup HTTP/Spring phù hợp.

Chỉ dùng `byCommand` nếu việc kiểm tra thực sự cần custom logic. Với điều kiện “là số dương”, matcher kiểu/regex hoặc assertion đơn giản thường dễ đọc hơn; ví dụ ở đây chủ yếu minh họa cách gọi hàm. Không dùng custom method để che giấu một hợp đồng quá phức tạp.

### 8.2. `execute()`: lấy dữ liệu test từ phương thức tùy chỉnh

Đối với **request body** phía producer test, có thể cần lấy payload đã chuẩn bị từ base class:

```groovy
request {
    method POST()
    url '/api/orders'
    headers {
        contentType(applicationJson())
    }
    body(
        $(consumer('{"customerId":"C-42"}'),
          producer(execute('contractRequestBody()')))
    )
}
```

`contractRequestBody()` là phương thức được định nghĩa trong base test, trả về một payload thích hợp cho HTTP request. Giá trị `consumer(...)` cung cấp dữ liệu mẫu cho stub, còn `producer(execute(...))` yêu cầu generated test gọi hàm tương ứng. Đối với request body theo dạng này, `execute` áp dụng **cho cả body**, không phải một phần của body.

Không nối chuỗi với lời gọi `execute` kiểu `'Bearer ' + execute('token()')` rồi kỳ vọng DSL ghép giá trị chính xác. Nếu cần header Authorization động, để phương thức trả nguyên giá trị header và dùng `header('Authorization', execute('authorizationHeader()'))` ở vị trí được DSL hỗ trợ.

Sử dụng custom helper ở mức vừa đủ: contract nên cho người review thấy dữ liệu có ý nghĩa, còn base test chỉ chứa công việc thiết lập hoặc điều kiện kiểm chứng khó mô tả bằng DSL.

## 9. Hợp đồng thông điệp cũng sử dụng helper và biểu thức

Spring Cloud Contract không chỉ kiểm tra HTTP; hệ thống dùng message broker có thể mô tả **input** và **outputMessage**. Ví dụ minh họa một thông điệp phát ra khi đơn hàng được thanh toán:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldPublishOrderPaid'
    label 'order_paid'

    input {
        triggeredBy('publishOrderPaid()')
    }

    outputMessage {
        sentTo('orders.paid')
        headers {
            header('eventType', 'OrderPaid')
        }
        body(
            orderId: 42,
            state: 'PAID',
            eventId: $(consumer('f26d1437-54a3-4f5b-9f81-2a7107c05441'),
                       producer(regex(uuid())))
        )
    }
}
```

Ở ví dụ này, `triggeredBy('publishOrderPaid()')` liên kết kịch bản với phương thức kích hoạt phía test; `sentTo('orders.paid')` xác định kênh/đích gửi được mô tả trong hợp đồng. Helper tạo UUID cho phép producer sinh ID hợp lệ mà không buộc cố định một ID. Cấu hình base test và framework nhắn tin quyết định cách test thực sự kích hoạt, thu thập và xác minh message.

Tên kênh `orders.paid` và phương thức `publishOrderPaid()` chỉ là giả định. Không suy ra độ bảo đảm “đúng một lần”, tính thứ tự hoặc transaction delivery chỉ từ việc contract mô tả một message. Những tính chất đó cần được thiết kế và kiểm thử theo đặc thù hệ thống.

## 10. Những lỗi thường gặp khi viết Groovy DSL

| Biểu hiện | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Stub chỉ nhận đúng một ID dù API cho phép nhiều ID | Đặt literal ở request consumer, hoặc thiếu regex | Dùng `consumer(regex(...))` ở request; giữ giá trị producer test cụ thể |
| Producer test thất bại do timestamp/UUID khác mỗi lần | Đặt literal phía producer response | Dùng `producer(regex(...))` hay response `bodyMatchers` với định dạng phù hợp |
| Consumer nhận giá trị khác kỳ vọng trong stub | Đặt matcher thay cho sample phía consumer response | Cung cấp ví dụ cụ thể `consumer('...')` |
| JSONPath không tìm thấy trường | Sai path, sai cấp lồng nhau hoặc field không xuất hiện | Kiểm tra cấu trúc JSON body và path `'$.field'` |
| Regex match một chuỗi nhưng không match chuỗi dài hơn | Thư viện có thể match toàn chuỗi | Mô tả pattern phù hợp toàn bộ định dạng đầu vào |
| Test generated không gọi được custom method | Sai `baseClassForTests`, tên method hoặc kiểu tham số | Đảm bảo phương thức được khai báo và truy cập được từ class test sinh |
| `byNull()` không thể hiện ý định “không có property” | Đang nhầm JSON null với field vắng mặt | Chọn assertion/kịch bản diễn đạt đúng hành vi consumer |
| `optional()` không kiểm tra đủ hai nhánh | Nhầm optional matcher với hai test thực thi | Thêm hợp đồng cho trường hợp vắng mặt nếu nghiệp vụ quan trọng |
| DSL chạy nhưng test thiếu ý nghĩa | Regex `.*`, `byType()` cho mọi giá trị | Khớp chặt những giá trị quyết định hành vi của consumer |
| Mã Groovy lỗi cú pháp | Nhầm `$` trong GString, dấu nháy, escape regex | Tách regex thành literal rõ ràng, thử sinh/compile contract trong build |

Một nguyên tắc hữu ích khi review là hỏi: **“Từ hợp đồng này, điều gì khiến stub nhận hoặc từ chối request; điều gì khiến test producer pass hoặc fail?”** Nếu không thể trả lời bằng một ví dụ cụ thể, cần viết lại expression cho rõ hơn.

## 11. Thực hành tổng hợp: xử lý tình huống đổi API

**Yêu cầu:** `checkout-service` gọi `GET /api/orders/{id}`. Producer trả `state` (bắt buộc là `PAID` trong kịch bản này) và `receiptId` sinh động với định dạng `RCT-` theo sau là tám chữ số.

**Hợp đồng đề xuất:**

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Consumer lấy biên lai cho đơn hàng đã thanh toán'

    request {
        method GET()
        url '/api/orders/42'
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            state: 'PAID',
            receiptId: $(
                consumer('RCT-00001234'),
                producer(regex('RCT-[0-9]{8}'))
            )
        )
    }
}
```

**Cách kiểm tra kết quả:**

1. Chạy producer contract test đã sinh. Producer phải trả `200`, `id=42`, `state=PAID` và một `receiptId` đúng mẫu.
2. Tạo/phát hành stub artifact của phiên bản producer. Stub Runner chạy stub cho consumer và trả sample `RCT-00001234` khi request khớp.
3. Consumer test dùng client HTTP của ứng dụng, kiểm tra logic hiển thị biên lai khi `state=PAID` và sử dụng `receiptId`.
4. Thử thay producer trả `receiptId: "invoice-123"`: generated producer test phải thất bại vì vi phạm định dạng.
5. Thử đổi `state` thành `COMPLETED` mà consumer vẫn dựa vào `PAID`: generated producer test cũng phải thất bại, dù status HTTP vẫn là `200`.

**Câu hỏi tự kiểm tra:**

- Nếu đổi request thành `$(consumer(regex('/api/orders/[0-9]+')), producer('/api/orders/42'))`, điều gì cần lưu ý? — Stub có thể nhận `/api/orders/71` nhưng vẫn trả body cố định `id: 42`; cần thu hẹp matcher hoặc tạo phản hồi gắn đúng với ID request.
- Nếu đổi phía response thành `producer('RCT-00001234')`, rủi ro là gì? — Producer test bị khóa vào mã cố định, dù hệ thống thực có thể tạo mã khác nhưng vẫn hợp lệ.
- Có nên đổi `state` thành `producer(regex('.*'))`? — **Không**; khi đó test không còn phát hiện thay đổi giá trị nghiệp vụ quan trọng.

## 12. Checklist khi review hàm hỗ trợ và expression

- [ ] Tách rõ input cho stub và input của producer test trong `request`.
- [ ] Tách rõ sample stub và assertion kiểm tra producer trong `response`.
- [ ] Giá trị nghiệp vụ cố định dùng equality; dữ liệu động dùng matcher có giới hạn.
- [ ] Regex khớp cả giá trị như dự kiến; không bỏ qua kiểu JSON và định dạng cần cam kết.
- [ ] `bodyMatchers` ở đúng phía; `byCommand` chỉ dùng nơi có generated producer test phù hợp.
- [ ] Dữ liệu fixture của producer tương ứng literal trong request.
- [ ] `fromRequest()` chỉ dùng khi response thật sự phụ thuộc dữ liệu request.
- [ ] `execute()` có method trong base test và không được nối chuỗi sai cách.
- [ ] Các giá trị tùy chọn có kịch bản kiểm thử rõ ràng, tránh chỉ dựa vào `optional()`.
- [ ] Build sinh test phía producer, đóng gói stub và kiểm thử với Stub Runner trong CI để phát hiện API không tương thích.

Các helper của Groovy DSL chỉ hữu ích khi chúng **diễn tả đúng cam kết với consumer**. Viết hợp đồng bằng `value()`, `$()`, regex và JSONPath một cách có chủ đích sẽ giúp kiểm thử bền vững khi producer thay đổi dữ liệu động, nhưng vẫn cảnh báo ngay khi thay đổi các hành vi quan trọng như tên trường, mã lỗi, kiểu dữ liệu hoặc trạng thái nghiệp vụ.

### Tài liệu đối chiếu

- Spring Cloud Contract Reference, *Contract DSL*: https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html
- Spring Cloud Contract Reference, *Dynamic properties*: https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html
