# Escape regex qua các lớp DSL, JSON và Java

## Mục tiêu bài học

**Spring Cloud Contract** dùng hợp đồng **Groovy DSL** hoặc **YAML DSL** để mô tả hành vi HTTP hay thông điệp giữa **producer** và **consumer**. Từ hợp đồng, công cụ có thể sinh kiểm thử phía producer, đóng gói stub, để consumer dùng **Stub Runner** và tích hợp các kiểm tra vào CI nhằm phát hiện thay đổi API không tương thích.

Khi dữ liệu thay đổi nhưng phải tuân thủ một định dạng, ta thường dùng **regular expression (regex)** trong matcher. Một lỗi rất phổ biến là regex đúng về mặt ý tưởng nhưng bị **escape thiếu hoặc thừa** trong tệp Groovy, YAML, JSON hoặc Java được sinh ra. Kết quả có thể là lỗi phân tích cú pháp, kiểm thử thất bại hoặc nghiêm trọng hơn: stub/test match sai mà không ai nhận thấy.

Sau bài này, bạn sẽ:

- Phân biệt **ký tự mà regex engine phải nhận** với cách viết nó trong từng loại chuỗi nguồn.
- Chuyển cùng một pattern giữa Groovy DSL, YAML DSL, JSON string và Java string literal mà không nhân đôi hoặc đánh rơi dấu `\`.
- Viết matcher với JSONPath cho request và response và biết vai trò của chúng trong stub/producer test.
- Nhận diện các trường hợp dễ sai: `\d`, `\.`, `\\`, dấu `$`, GString, JSONPath và regex trong JSON lồng nhau.
- Xác minh kết quả bằng test dương/âm, kiểm tra generated test/stub và CI, không chỉ nhìn code source.

## 1. Quy tắc nền tảng: một regex có thể đi qua nhiều lớp biểu diễn

Giả sử mã đơn hàng cần có dạng **ORD-** theo sau là bốn chữ số, ví dụ `ORD-2048`. Regex mà **regex engine** cần nhận là:

~~~regex
^ORD-\d{4}$
~~~

Ý nghĩa các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `^` | Đầu chuỗi |
| `ORD-` | Các ký tự cố định |
| `\d` | Một chữ số theo quy tắc của regex engine |
| `{4}` | Lặp đúng bốn lần |
| `$` | Cuối chuỗi |

Trong mẫu này, dấu `\` là **một ký tự của regex**. Nhưng khi regex được viết bên trong **string literal**, chính ngôn ngữ chứa string có thể dùng dấu `\` để escape. Do đó, người viết cần phân biệt:

1. **Lớp regex**: regex engine phải nhận `^ORD-\d{4}$`.
2. **Lớp biểu diễn nguồn**: Groovy, YAML, JSON hoặc Java phải tạo ra đúng chuỗi đó.
3. **Lớp công cụ sinh mã**: Spring Cloud Contract chuyển hợp đồng thành generated tests/stubs, có thể phải escape chuỗi một lần nữa để tạo mã nguồn đích hợp lệ.
4. **Lớp thực thi**: test hoặc stub dùng giá trị cuối cùng để match input/output.

~~~mermaid
flowchart TD
    A["Regex có ý nghĩa nghiệp vụ"] --> B["Chuỗi trong Groovy DSL<br/>hoặc YAML DSL"]
    B --> C["Mô hình hợp đồng của Spring Cloud Contract"]
    C --> D["Generated Java test<br/>chuỗi nguồn Java"]
    C --> E["Stub mapping<br/>chuỗi trong JSON"]
    D --> F["Regex engine hoặc assertion của producer test"]
    E --> G["Matcher của stub / Stub Runner"]
~~~

**Một dấu gạch chéo ngược xuất hiện hai lần trong mã nguồn không nhất thiết là hai dấu trong regex cuối cùng.** Hãy hỏi: chuỗi đang nằm ở *lớp nào*?

## 2. Bảng chuyển đổi nhanh cho cùng một pattern

Cùng quy tắc `^ORD-\d{4}$` được biểu diễn khác nhau:

| Nơi viết | Biểu diễn | Vì sao |
| --- | --- | --- |
| Regex engine nhận | `^ORD-\d{4}$` | Cần một dấu `\` trước `d` |
| Groovy **single-quoted** string | `'^ORD-\\d{4}$'` | Groovy xử lý `\\` để tạo một `\` |
| Java string literal | `"^ORD-\\d{4}$"` | Java xử lý `\\` để tạo một `\` |
| YAML **single-quoted** scalar | `'^ORD-\d{4}$'` | YAML single quote không dùng dấu `\` để escape |
| YAML **double-quoted** scalar | `"^ORD-\\d{4}$"` | YAML double quote có quy tắc escape riêng |
| JSON string | `"^ORD-\\d{4}$"` | JSON cần `\\` để chứa một `\` |

**Cảnh báo:** bảng này mô tả **các chuỗi có cùng ý nghĩa sau khi parse**. Không có nghĩa Spring Cloud Contract sẽ đặt tất cả chúng vào cùng vị trí hoặc hỗ trợ mọi phương thức matcher ở mọi phiên bản. Phải kiểm tra đầu ra sinh thực tế.

### Đếm dấu `\` đúng cách

Ví dụ khi dùng `\d`:

~~~text
Regex mong muốn:           ^ORD-\d{4}$
Groovy single quote:      '^ORD-\\d{4}$'
YAML single quote:        '^ORD-\d{4}$'
YAML double quote:        "^ORD-\\d{4}$"
JSON string:              "^ORD-\\d{4}$"
Java string literal:      "^ORD-\\d{4}$"
~~~

Khi Java compiler đọc source `"^ORD-\\d{4}$"`, giá trị chuỗi runtime có **một dấu `\`**. Regex engine mới diễn giải `\d` là lớp ký tự chữ số.

Nếu Java source viết `"^ORD-\d{4}$"`, dấu `\d` không phải một escape hợp lệ của Java string, nên mã có thể không biên dịch. Với YAML double-quoted scalar, `"\d"` cũng không phải cách ghi đúng một dấu backslash cho regex.

## 3. Escape trong Groovy DSL: single quote, double quote và slashy string

Groovy hỗ trợ nhiều cách viết string. Trong hợp đồng, **single quote** thường giúp các regex dễ đọc hơn vì tránh việc vô tình dùng biến nội suy, nhưng dấu gạch chéo ngược vẫn cần được xử lý theo cách của Groovy.

### 3.1. Groovy single-quoted string

~~~groovy
// Giá trị string sau khi Groovy đánh giá là ^ORD-\d{4}$
def orderIdPattern = '^ORD-\\d{4}$'
~~~

Đoạn này có **hai dấu `\` trong source**, tương ứng **một dấu `\` trong string runtime**. Đó là điều regex engine cần.

Một ví dụ khác: dấu chấm thực trong mã phiên bản.

~~~groovy
// Muốn chấp nhận "v2.1", không chấp nhận "v2x1":
def versionPattern = '^v\\d+\\.\\d+$'
~~~

Trong regex cuối cùng, `\.` match **dấu chấm thật**; nếu chỉ dùng `.`, dấu chấm regex có thể match nhiều ký tự khác. Hai lớp escape ở đây khác nhau:

- `\\.` trong Groovy source tạo ra `\.` trong regex string.
- `\.` trong regex string yêu cầu regex engine match ký tự dấu chấm.

### 3.2. Groovy double-quoted string và GString

~~~groovy
// Không nội suy biến thì vẫn tạo string có một backslash:
def pattern = "^ORD-\\d{4}$"
~~~

Groovy double quote có thể hỗ trợ **nội suy** khi gặp biểu thức dùng dấu `$`. Trong regex, `$` lại là anchor cuối chuỗi. Vì thế cần đặc biệt cẩn thận khi viết các biểu thức phức tạp trong double-quoted string, nhất là khi có ký hiệu kết hợp với tên biến hoặc dấu ngoặc nhọn.

Để giảm nhầm lẫn, nên ưu tiên **single-quoted** cho các regex tĩnh trong Groovy contract; nếu có nội suy thật sự, bảo đảm nội suy đó có chủ đích và kết quả cuối là pattern mà consumer/producer đã thống nhất.

### 3.3. Slashy string không phải quy tắc chung cho mọi DSL

Groovy còn có cú pháp **slashy string**:

~~~groovy
def pattern = /^\d{4}$/
~~~

Trong dạng slashy string, dấu `\` trước `d` thường có thể viết gần với cú pháp regex hơn. Nhưng dấu `/` có thể cần escape vì là ký tự phân cách, và các quy tắc về nội suy cần được hiểu rõ.

Ngoài ra, các API của Spring Cloud Contract có thể mong đợi **chuỗi** hoặc **kiểu dữ liệu matcher** cụ thể. Không mặc định rằng một `Pattern` Groovy tạo bằng `~/.../` có thể thay trực tiếp một lời gọi `regex(...)` ở mọi vị trí. Với bài thực hành và CI, dùng cú pháp matcher đã được DSL hỗ trợ là cách an toàn hơn.

## 4. Escape trong YAML DSL: single quote khác double quote

YAML thường được chọn để đọc hợp đồng như dữ liệu khai báo. Tuy nhiên, kiểu dấu nháy ảnh hưởng trực tiếp đến backslash.

### 4.1. Single quote: phù hợp với regex tĩnh

~~~yaml
# Một backslash trong YAML source được giữ nguyên:
value: '^ORD-\d{4}$'
~~~

Trong YAML **single-quoted scalar**, backslash không phải ký tự escape. Chuỗi sau khi parse giữ **một dấu `\`** trước `d`. Nếu viết `'^ORD-\\d{4}$'` trong YAML single quote, giá trị sau parse lại có **hai dấu `\`** trước `d`. Regex có thể hiểu nó theo nghĩa khác, ví dụ match dấu backslash literal thay vì chữ số.

Để biểu diễn dấu nháy đơn thật trong YAML single quote, quy tắc escape riêng của YAML là **viết hai dấu nháy đơn**, không dùng backslash:

~~~yaml
example: 'It''s a test value'
~~~

### 4.2. Double quote: phải escape backslash

~~~yaml
# Hai backslash trong YAML source tạo một backslash trong chuỗi:
value: "^ORD-\\d{4}$"
~~~

YAML double quote cho phép các escape sequence như `\n` và `\t`. Vì vậy, khi muốn chuyển regex `\d` cho regex engine, phải viết `\\d`. Một chuỗi như `"\d"` có thể bị trình phân tích YAML báo lỗi escape không hợp lệ.

**Quy tắc nhớ nhanh:** regex tĩnh trong YAML single quote thường gần với biểu thức cần match hơn; YAML double quote lại gần với JSON/Java về số dấu `\`.

### 4.3. Không nên dùng scalar không quote tùy tiện

Một pattern ngắn đôi khi có thể viết dưới dạng YAML plain scalar, nhưng các ký tự như dấu `:`, `#`, dấu cách hoặc cấu trúc đặc biệt có thể khiến YAML hiểu theo vai trò cú pháp thay vì dữ liệu. Khi thiết kế hợp đồng có regex, nên chọn quy ước **trích dẫn nhất quán** để giảm lỗi khó phát hiện.

## 5. JSON string luôn có lớp escape của JSON

Nếu regex được lưu vào JSON dưới dạng trường string, ví dụ một file stub mapping hoặc dữ liệu mô tả matcher, nó phải tuân thủ escape của JSON.

~~~json
{
  "pattern": "^ORD-\\d{4}$"
}
~~~

Khi JSON parser đọc nội dung trên, giá trị trường **pattern** thành `^ORD-\d{4}$`. Việc file JSON hiển thị hai dấu backslash là **đúng**; chưa thể kết luận regex đang bị double escaping.

JSON phân biệt:

~~~json
{
  "regexWithDigit": "^ORD-\\d{4}$",
  "regexWithLiteralDot": "^v\\d+\\.\\d+$"
}
~~~

Trong đó:

- `\\d` ở **JSON source** trở thành `\d` trong chuỗi được regex engine nhận.
- `\\.` ở JSON source trở thành `\.`; regex engine hiểu đây là dấu chấm literal.

**Không ghi JSON string như sau:**

~~~text
{"pattern":"^ORD-\d{4}$"}
~~~

Vì JSON chỉ cho phép những escape sequence nhất định; `\d` không phải JSON escape hợp lệ. Một JSON parser tuân thủ chuẩn sẽ từ chối.

### 5.1. Khi regex nằm trong JSON do Java hoặc Groovy tạo ra

Có thể có thêm một lớp:

~~~text
Giá trị regex mong muốn:       ^ORD-\d{4}$
Chuỗi Java source:            "^ORD-\\d{4}$"
JSON được serializer ghi:     {"pattern":"^ORD-\\d{4}$"}
Giá trị JSON sau parse:       ^ORD-\d{4}$
~~~

Không nên tự **nhân đôi backslash một lần nữa** trước khi đưa chuỗi vào một JSON serializer chuẩn: serializer đã có trách nhiệm escape cho JSON. Việc escape thủ công trước đó có thể dẫn tới **double escaping**.

Trong Spring Cloud Contract, generated stub mapping thường có định dạng JSON. Khi kiểm tra mapping được sinh, hãy phân biệt **chuỗi hiển thị trong file** và **giá trị parser chuyển cho matcher**.

## 6. Java source sinh ra: nhìn hai dấu `\` chưa phải là lỗi

Generated producer tests có thể dùng Java. Ví dụ một test Java có thể kiểm tra định dạng ID bằng regex như sau:

~~~java
import java.util.regex.Pattern;

class OrderIdFormatExample {
    static boolean validOrderId(String value) {
        return value != null
                && Pattern.matches("^ORD-\\d{4}$", value);
    }
}
~~~

Trong mã nguồn Java, `"^ORD-\\d{4}$"` là cách viết đúng để tạo pattern có **một dấu `\`** trước `d`. Không sửa generated source thành `"^ORD-\d{4}$"`: Java không chấp nhận cách escape đó.

Nếu mã test do Spring Cloud Contract sinh ra hiển thị nhiều dấu backslash hơn bạn dự đoán, hãy xác minh:

1. Đó là **Java source**, **JSON text** hay **runtime string**?
2. Chuỗi thực được đưa tới matcher là gì?
3. Generated test có đang test đúng ví dụ dương và âm không?

Đừng sửa generated test bằng tay để “sửa escape”. Những tệp đó thường được tái sinh; nguồn cần sửa là **DSL**, cấu hình hoặc cách mô tả matcher.

## 7. So sánh ba mẫu regex dễ nhầm

### 7.1. Chữ số `\d`

Mục tiêu: `ORD-0001` hợp lệ, `ORD-ABCD` không hợp lệ.

~~~text
Regex engine:    ^ORD-\d{4}$
Groovy source:   '^ORD-\\d{4}$'
YAML single:     '^ORD-\d{4}$'
YAML double:     "^ORD-\\d{4}$"
JSON string:     "^ORD-\\d{4}$"
Java source:     "^ORD-\\d{4}$"
~~~

### 7.2. Dấu chấm literal `\.`

Mục tiêu: `v2.1` hợp lệ, `v2x1` không hợp lệ.

~~~text
Regex engine:    ^v\d+\.\d+$
Groovy source:   '^v\\d+\\.\\d+$'
YAML single:     '^v\d+\.\d+$'
YAML double:     "^v\\d+\\.\\d+$"
JSON string:     "^v\\d+\\.\\d+$"
Java source:     "^v\\d+\\.\\d+$"
~~~

Sai lầm rất phổ biến: bỏ `\` trước dấu chấm và dùng `^v\d+.\d+$`. Khi đó dấu chấm là **ký tự bất kỳ** theo quy tắc regex, nên một giá trị không mong muốn vẫn có thể match.

### 7.3. Dấu backslash literal trong dữ liệu

Mục tiêu: kiểm tra chuỗi dữ liệu có **một dấu `\`** giữa `A` và `B`, ví dụ một mã kỹ thuật `A\B`.

Để regex engine match **backslash literal**, bản thân regex cần hai backslash:

~~~text
Giá trị dữ liệu:        A\B
Regex engine:          ^A\\B$
Groovy source:         '^A\\\\B$'
YAML single:           '^A\\B$'
YAML double:           "^A\\\\B$"
JSON string:           "^A\\\\B$"
Java source:           "^A\\\\B$"
~~~

Lý do: **lớp regex** dùng `\\` để yêu cầu match một dấu backslash. Sau đó Java/Groovy string literal hoặc JSON/YAML double quote lại cần escape **từng dấu backslash** của regex.

Nếu chính **dữ liệu JSON** muốn chứa chuỗi `A\B` (không phải một regex), JSON body phải ghi:

~~~json
{"code": "A\\B"}
~~~

Đừng nhầm **escape dữ liệu JSON** với **escape pattern dùng để match dữ liệu JSON**; chúng là hai bước giải thích khác nhau.

## 8. JSONPath và regex là hai ngôn ngữ khác nhau

Trong Spring Cloud Contract, một matcher thường có **JSONPath để chọn trường** và **regex để kiểm tra giá trị của trường**.

Ví dụ JSON response:

~~~json
{
  "order": {
    "id": "ORD-2048",
    "version": "v2.1"
  }
}
~~~

Khi đó:

- JSONPath `$.order.id` chọn đúng trường **id**.
- Regex `^ORD-\d{4}$` kiểm tra **giá trị của id**.
- JSONPath `$.order.version` chọn trường **version**.
- Regex `^v\d+\.\d+$` kiểm tra **giá trị version**.

JSONPath bắt đầu bằng `$` nhưng dấu `$` ở **regex cuối chuỗi** lại có nghĩa khác. Không dùng cùng một quy tắc escape cho cả hai:

| Ký hiệu | Trong JSONPath | Trong regex |
| --- | --- | --- |
| `$` | Gốc của tài liệu JSON | Anchor cuối chuỗi (nếu ở vị trí thích hợp) |
| `.` | Ngăn các cấp property, ví dụ `$.order.id` | Match một ký tự bất kỳ |
| `[0]` | Chọn phần tử mảng thứ nhất | Một nhóm ký tự trong dấu ngoặc vuông có nghĩa khác |
| `\` | Có thể liên quan tới escape trong tên property tùy cú pháp JSONPath | Escape của regex |

Ví dụ:

~~~groovy
bodyMatchers {
    jsonPath('$.order.id', byRegex('^ORD-\\d{4}$'))
}
~~~

Hàm `jsonPath` nhận **hai chuỗi có vai trò khác nhau**: chuỗi chọn vị trí dữ liệu và chuỗi diễn đạt điều kiện match. Chỉ regex `'^ORD-\\d{4}$'` cần `\\d` vì đây là Groovy source.

## 9. Viết request matcher trong Groovy DSL

Giả sử consumer gọi POST /api/orders với mã khách hàng có ba chữ số và trường orderCode có dạng ORD-0001. Ta muốn producer test gửi request mẫu ổn định, nhưng stub có thể nhận nhiều mã hợp lệ.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Tạo đơn với mã định danh theo regex"

    request {
        method POST()
        url "/api/orders"
        headers {
            contentType(applicationJson())
        }
        body(
            customerId: "CUS-101",
            orderCode: "ORD-2048",
            quantity: 2
        )
        bodyMatchers {
            jsonPath('$.customerId', byRegex('^CUS-\\d{3}$'))
            jsonPath('$.orderCode', byRegex('^ORD-\\d{4}$'))
        }
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(orderId: "ORD-2048", status: "CREATED")
    }
}
~~~

**Điều cần kiểm tra:**

1. Cặp dấu `\\` trong Groovy source phải đi tới matcher thành `\d`.
2. Producer test gửi request mẫu như **CUS-101**, **ORD-2048**.
3. Stub sử dụng matcher của request để nhận diện lời gọi từ consumer.
4. Regex cho mã khách hàng không kiểm tra khách hàng có tồn tại; `quantity: 2` không kiểm tra mọi số lượng hợp lệ.

Nếu matcher quá rộng, stub có thể trả success cho request mà producer thật từ chối. Nếu regex sai escape, stub có thể không nhận request hoàn toàn hợp lệ. Cần chạy test với cả giá trị **được chấp nhận** và **phải bị từ chối**.

## 10. Response matcher trong Groovy DSL

Với response, consumer stub cần giá trị mẫu để consumer xử lý, còn producer test cần kiểm tra dữ liệu thực tế.

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method GET()
        url "/api/orders/ORD-2048"
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: "ORD-2048",
            status: "PAID"
        )
        bodyMatchers {
            jsonPath('$.orderId', byRegex('^ORD-\\d{4}$'))
        }
    }
}
~~~

Trong phạm vi matcher của response, generated producer test có thể xác minh **orderId** trả về tuân thủ quy tắc; stub vẫn có thể trả một giá trị mẫu như **ORD-2048**. Cách generator kết hợp giá trị body cố định, matcher và các cấu trúc giá trị hai phía còn tùy phiên bản, vì vậy cần kiểm tra generated test và stub mapping thực tế.

Nếu producer có mã đơn hàng dài động theo UUID, nên dùng matcher tương ứng **định dạng công khai** hoặc fixture kiểm soát ID, không khóa vào một bản ghi production. Regex cũng không chứng minh mã vừa tạo tồn tại trong database hoặc có thể truy vấn lại: đó là hành vi cần thêm bài test.

## 11. YAML DSL matcher: chú ý cách quote khi chuyển từ Groovy

Cùng quy tắc về customerId có thể viết trong YAML DSL như sau:

~~~yaml
description: "Tạo đơn với mã khách hàng đúng định dạng"
name: create_order_customer_pattern
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-101"
    quantity: 2
  matchers:
    body:
      - path: $.customerId
        type: by_regex
        value: '^CUS-\d{3}$'
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    orderId: "ORD-2048"
    status: CREATED
~~~

Ở đây `value: '^CUS-\d{3}$'` là YAML **single-quoted**, nên giữ nguyên một dấu backslash. Nếu chuyển sang YAML double quote, phải ghi:

~~~yaml
value: "^CUS-\\d{3}$"
~~~

Trong các phiên bản/cấu hình Spring Cloud Contract khác nhau, khả năng matcher và cách sinh stub/test cần được xác minh theo DSL thực tế; đừng chỉ sửa số dấu `\` trong source mà không quan sát đầu ra.

**Lưu ý:** YAML matcher dạng `by_regex` là một cấu trúc khai báo, không phải một đoạn Java string literal. Copy nguyên `'\\d'` từ Groovy single-quoted sang YAML single-quoted sẽ làm thay đổi nội dung chuỗi.

## 12. Lỗi escape không chỉ ở dấu backslash

### 12.1. Nhầm giữa dấu chấm JSONPath và dấu chấm regex

~~~text
JSONPath: $.customer.email
Regex:    ^[^@]+@example\.test$
~~~

Trong JSONPath, dấu chấm phân tách cấp object. Trong regex, muốn match dấu chấm thật của domain `example.test` thì dùng `\.`. Trong Groovy string, phải ghi `\\.`; trong YAML single quote, ghi `\.`.

### 12.2. Nhầm dấu `$` với GString interpolation

Regex `^ORD-\d{4}$` kết thúc bằng dấu `$`. Trong Groovy double-quoted string, `$` cũng liên quan tới cú pháp nội suy khi theo sau là biểu thức phù hợp. Nên chọn **single quote** cho regex cố định để tránh tạo GString ngoài ý muốn.

Nếu thật sự cần ghép phần động vào regex, hãy giới hạn rõ phần đầu vào, escape các ký tự regex đặc biệt của dữ liệu ghép vào và kiểm tra kết quả. Không đưa trực tiếp dữ liệu người dùng hay biến môi trường vào regex mà chưa xử lý, vì nội dung đó có thể làm thay đổi ý nghĩa pattern.

### 12.3. Nhầm newline thật với regex `\n`

Khi muốn match **ký tự xuống dòng**, phải phân biệt:

- Một ký tự newline thật trong dữ liệu.
- Chuỗi chứa hai ký tự `\` và `n`.
- Cách biểu diễn `\n` trong regex hoặc trong string literal.

Ví dụ với JSON:

~~~json
{"message":"First line\nSecond line"}
~~~

Trong file JSON, chuỗi `\n` biểu diễn **một ký tự xuống dòng sau khi parse**, không phải hai ký tự literal trong dữ liệu runtime. Nếu bạn cần một backslash literal đứng trước chữ `n`, JSON phải chứa `\\n`. Việc này khác với JSON string lưu **regex pattern** kiểm tra một newline.

### 12.4. Sử dụng regex quá mạnh cho dữ liệu có cấu trúc

JSONPath có thể chọn đúng field, do đó không cần dùng một regex khổng lồ để match toàn bộ JSON đã serialize. Regex toàn bộ body dễ phụ thuộc thứ tự key, khoảng trắng và cách serialize. Hãy mô tả JSON bằng map/object và đặt matcher tại các trường cần linh hoạt.

## 13. Bảng lỗi thường gặp khi chuyển giữa DSL và Java/JSON

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| Java generated test không biên dịch | Một escape không hợp lệ lọt vào Java string literal | Kiểm tra DSL source và Java source sinh ra; không sửa generated file bằng tay |
| YAML parser báo unknown escape | Dùng `"\d"` trong YAML double quote | Dùng `"\\d"` hoặc `'\d'` |
| Stub không match `ORD-1234` | Regex đã được escape thừa và có thể đang match dấu backslash literal | Kiểm tra mapping JSON và test request dương/âm |
| Stub nhận `v2x1` thay vì chỉ `v2.1` | Thiếu `\` trước dấu chấm regex | Dùng `\.` ở regex engine; escape tương ứng theo ngôn ngữ nguồn |
| JSON mapping không parse được | JSON chứa escape không hợp lệ như `\d` | Ghi `\\d` trong JSON source |
| Hợp đồng Groovy sinh kết quả khác giữa CI | Nội suy hoặc phụ thuộc môi trường tạo pattern động | Dùng hằng/matcher ổn định và review chuỗi cuối cùng |
| JSONPath không tìm thấy trường | Đường dẫn chọn sai cấp hoặc bị nhầm với regex | Kiểm tra JSONPath và body mẫu riêng |
| Test vẫn PASS với dữ liệu không hợp lệ | Matcher quá rộng hoặc thiếu assertion phủ định | Bổ sung ví dụ không được match |
| Consumer test PASS nhưng producer thay đổi API | Consumer vẫn dùng stub artifact cũ | Chốt phiên bản/revision và kiểm thử lại với stub mới |

**Chỉ nhìn số dấu `\` trong file stub không đủ để kết luận lỗi.** Cần biết file đó là JSON source, một Java source, Groovy string hay một giá trị đã parse.

## 14. Kiểm tra regex bằng ví dụ dương và âm

Một pattern tốt cần phân biệt rõ đầu vào được chấp nhận và không được chấp nhận. Đối với `^ORD-\d{4}$`:

| Giá trị | Kỳ vọng | Vì sao |
| --- | --- | --- |
| `ORD-2048` | Match | Đúng tiền tố và bốn chữ số |
| `ORD-0001` | Match | Có thể bắt đầu bằng số 0 nếu định dạng cho phép |
| `ORD-123` | Không match | Thiếu một chữ số |
| `ORD-12345` | Không match | Dư một chữ số |
| `ORD-ABCD` | Không match | Chữ cái thay vì chữ số |
| `XORD-2048` | Không match | Ký tự thừa phía trước |
| `ORD-2048X` | Không match | Ký tự thừa phía sau |
| `ORD-\d{4}` | Không match | Đây là ký tự literal, không phải mã đơn hợp lệ |

Đoạn Java sau minh họa **kiểm tra bản thân regex** trước khi đưa vào hợp đồng:

~~~java
import java.util.regex.Pattern;

public class OrderIdRegexExample {
    public static void main(String[] args) {
        Pattern pattern = Pattern.compile("^ORD-\\d{4}$");
        String[] valid = {"ORD-2048", "ORD-0001"};
        String[] invalid = {
            "ORD-123", "ORD-12345", "ORD-ABCD",
            "XORD-2048", "ORD-2048X", "ORD-\\d{4}"
        };

        for (String value : valid) {
            if (!pattern.matcher(value).matches()) {
                throw new AssertionError("Must match: " + value);
            }
        }
        for (String value : invalid) {
            if (pattern.matcher(value).matches()) {
                throw new AssertionError("Must not match: " + value);
            }
        }
    }
}
~~~

Đây là ví dụ Java độc lập để làm rõ cách Java string truyền pattern cho regex engine. Trong một dự án thực, có thể đưa các kiểm tra này vào unit test cho matcher tùy chỉnh hoặc kiểm thử contract/stub ở phạm vi phù hợp.

**Lưu ý:** phép kiểm tra regex dương/âm **không thay thế** việc chạy Spring Cloud Contract Verifier; nó chỉ chứng minh chính pattern đã viết match những chuỗi được chọn. Việc sinh test/stub có thể giới thiệu một lớp escape khác, và nghiệp vụ có thể có ràng buộc ngoài định dạng.

## 15. Xác minh ở cả producer test và Stub Runner

Đối với Spring Cloud Contract, hãy kiểm chứng xuyên suốt vòng đời:

1. **Hợp đồng được phát hiện:** Groovy/YAML hợp lệ và nằm đúng nguồn được plugin quét.
2. **Mã được sinh:** generated producer test có chuỗi Java hợp lệ, matcher được đưa vào đúng chỗ.
3. **Producer test thực thi:** ứng dụng producer trả phản hồi phù hợp; test thật sự chạy, không bị skip.
4. **Stub mapping đúng:** nếu mapping là JSON, chuỗi có thể hiển thị nhiều dấu backslash hơn regex engine nhận. Phải kiểm tra hành vi match thực tế.
5. **Consumer test với Stub Runner:** các request hợp lệ match được, request sai định dạng bị từ chối theo kịch bản/hành vi stub, consumer xử lý response đúng.
6. **Version và provenance:** stub consumer test dùng phải gắn với đúng contract revision và producer build đã xác minh; không dùng bản cũ không kiểm soát.

~~~mermaid
flowchart TD
    A["Regex trong Groovy/YAML"] --> B["Sinh test/stub"]
    B --> C{"Generated test biên dịch?"}
    C -->|Không| X["BLOCK: kiểm tra escape"]
    C -->|Có| D["Chạy producer test"]
    D --> E{"PASS và đủ test?"}
    E -->|Không| X
    E -->|Có| F["Xem stub mapping"]
    F --> G["Kiểm tra request dương/âm với stub"]
    G --> H{"Matcher đúng?"}
    H -->|Không| X
    H -->|Có| I["Consumer test qua Stub Runner"]
    I --> J["Ghi bằng chứng tương thích có phạm vi"]
~~~

**Không kết luận “regex đúng” chỉ vì build xanh**: có thể contract không được phát hiện, test bị skip, stub cũ vẫn đang được dùng, hoặc không có trường hợp âm để phát hiện pattern quá rộng.

Với regex phức tạp, hãy lưu vài ví dụ input mong đợi và không mong đợi ngay cạnh bài test; tập trung vào **ý nghĩa giao diện** thay vì các chi tiết trong code producer.

## 16. Bài tập thực hành

### Bài tập A — Chuyển đổi biểu diễn

Regex engine cần pattern `^CUS-\d{3}$`. Hãy viết cùng pattern cho:

1. Groovy single-quoted string.
2. YAML single-quoted scalar.
3. YAML double-quoted scalar.
4. JSON string.
5. Java string literal.

**Đáp án gợi ý:**

~~~text
Groovy:      '^CUS-\\d{3}$'
YAML single: '^CUS-\d{3}$'
YAML double: "^CUS-\\d{3}$"
JSON:        "^CUS-\\d{3}$"
Java:        "^CUS-\\d{3}$"
~~~

### Bài tập B — Tìm lỗi escape

Một tệp YAML chứa:

~~~yaml
value: '^ORD-\\d{4}$'
~~~

Tác giả muốn chấp nhận `ORD-2048` nhưng stub không match. Hãy chỉ ra vì sao nội dung YAML **single quote** trên không đưa đến regex mong muốn.

**Gợi ý:** backslash trong YAML single quote không bị unescape; cặp `\\` được giữ thành hai ký tự và regex engine có thể hiểu chúng là escape cho một backslash literal. Sửa thành `'^ORD-\d{4}$'`, sau đó kiểm tra stub được sinh và chạy ví dụ dương/âm.

### Bài tập C — Dấu chấm trong mã phiên bản

Consumer gửi giá trị `v3.12`. Hãy viết regex chỉ chấp nhận `v`, một hoặc nhiều chữ số, dấu chấm literal, một hoặc nhiều chữ số. Đưa ra ít nhất ba chuỗi không được match.

**Gợi ý:** regex engine `^v\d+\.\d+$`. Các chuỗi `v3x12`, `v3`, `v3.12x` phải bị từ chối. Khi viết trong Groovy, thêm escape theo quy tắc Groovy string.

### Bài tập D — JSONPath hay regex?

Body:

~~~json
{
  "customer": {"id": "CUS-101"},
  "items": [{"sku": "BOOK-001", "quantity": 2}]
}
~~~

Hãy chọn JSONPath đến customer ID và SKU đầu tiên; chỉ đặt regex cho định dạng mã, không dùng regex để match cả JSON body đã serialize.

**Gợi ý:** `$.customer.id` và `$.items[0].sku` là các đường dẫn JSONPath. Định dạng của chúng không phải một regex; regex áp dụng cho **giá trị** mà đường dẫn chọn.

### Bài tập E — Test dương và âm trong CI

Đội thay matcher của mã đơn từ `^ORD-\d{4}$` thành một biểu thức rộng hơn và CI vẫn xanh. Đề xuất tập input dương/âm và các bước xác minh trên generated test, stub mapping và consumer Stub Runner test.

**Gợi ý:** dùng các mã hợp lệ/không hợp lệ ở mục 14, xác nhận test được sinh và chạy, khóa stub artifact mới, kiểm tra stub không trả phản hồi thành công cho request sai định dạng. Sau đó đánh giá thay đổi có mở rộng giao diện ngoài dự kiến hay không.

## 17. Checklist khi đưa regex vào hợp đồng

- [ ] Viết rõ **regex engine phải nhận chuỗi gì** trước khi chọn cú pháp biểu diễn.
- [ ] Phân biệt Groovy single/double quote, YAML single/double quote, JSON string và Java string literal.
- [ ] Với `\d`, `\.` và `\\`, đã đếm đúng các lớp escape.
- [ ] Regex tĩnh trong Groovy tránh GString interpolation không cần thiết.
- [ ] JSONPath dùng để **chọn field**, regex dùng để **kiểm tra giá trị field**.
- [ ] Không dùng regex quá rộng hoặc match cả JSON đã serialize khi có thể match object theo cấu trúc.
- [ ] Có ví dụ dương và âm thể hiện đúng ranh giới được phép.
- [ ] Generated producer test biên dịch, chạy và xác minh được kịch bản mong muốn.
- [ ] Stub mapping được kiểm tra theo **giá trị sau parse** và bằng request thực, không chỉ đếm dấu `\`.
- [ ] Consumer test qua Stub Runner với stub version và contract revision đã xác định.
- [ ] Không bỏ qua test sai matcher để làm CI xanh; sửa đúng DSL hoặc cấu hình nguồn.
- [ ] Chỉ tuyên bố tương thích với những consumer, phiên bản và hành vi thật sự được kiểm chứng.

**Ghi nhớ:** Regex không tự “thêm lớp escape” một cách bí ẩn; **mỗi ngôn ngữ chứa regex có quy tắc string riêng**. Muốn Spring Cloud Contract sinh test và stub chính xác, trước tiên xác định pattern mà regex engine cần nhận, viết lại theo đúng lớp Groovy/YAML/JSON/Java, rồi kiểm chứng bằng test dương/âm ở cả producer và consumer. Đó là cách tránh lỗi matcher và assertion làm CI bỏ sót thay đổi API không tương thích.
