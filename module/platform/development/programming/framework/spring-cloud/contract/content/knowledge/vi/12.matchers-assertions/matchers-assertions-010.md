# Phân biệt thứ tự phần tử có ý nghĩa và không có ý nghĩa

Trong **Spring Cloud Contract**, khi hợp đồng mô tả một danh sách JSON, chúng ta cần quyết định **thứ tự phần tử có thuộc hành vi mà producer cam kết với consumer hay không**. Một API trả về các bước giao hàng theo trình tự thời gian khác với một API trả về tập hợp vai trò của người dùng. Nếu dùng cùng kiểu assertion cho cả hai, kiểm thử có thể quá chặt, khiến build thất bại dù hành vi vẫn đúng; hoặc quá lỏng, bỏ sót một thay đổi làm consumer xử lý sai.

Bài thuộc chương **Matcher và assertion** của mô-đun **SPRING_CLOUD_CONTRACT**. Spring Cloud Contract cho phép định nghĩa HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh test xác minh phía producer, tạo artifact stub và dùng **Stub Runner** để consumer kiểm thử mã gọi của mình. Trọng tâm ở đây là xác định **thứ tự nào là một phần hợp đồng**, lựa chọn matcher/assertion phù hợp, và kiểm tra rằng **generated producer test** lẫn **stub** không áp đặt hoặc bỏ qua thứ tự trái với thỏa thuận.

## 1. JSON có thứ tự ở đâu?

Cần tách hai cấu trúc JSON:

- **Object** là tập hợp các cặp tên và giá trị. Thứ tự các **khóa** không mang ý nghĩa ngữ nghĩa theo mô hình dữ liệu JSON.
- **Array** là một dãy có thứ tự. Phần tử ở vị trí 0, 1, 2 có thể được xử lý theo vị trí. Tuy nhiên, **API có thể quy định thứ tự này quan trọng hoặc không quan trọng với nghiệp vụ**.

Ví dụ hai object sau chứa cùng các trường và giá trị:

~~~json
{"id":42,"status":"PAID"}
~~~

~~~json
{"status":"PAID","id":42}
~~~

Một consumer đọc JSON object theo tên trường không nên bị ảnh hưởng bởi thứ tự biểu diễn các khóa. Hợp đồng thường cần so sánh **tên trường, kiểu và giá trị**, thay vì so nguyên văn chuỗi JSON byte-for-byte.

Với array, hai cấu trúc:

~~~json
["READER","EDITOR"]
~~~

~~~json
["EDITOR","READER"]
~~~

là hai **dãy khác nhau về vị trí phần tử**. Chúng có thể biểu diễn **cùng một tập vai trò**, nếu API cam kết rằng thứ tự không quan trọng. Nhưng nếu đây là danh sách các bước thực hiện, việc đổi vị trí có thể làm sai ý nghĩa. Vì vậy, câu hỏi cần hỏi trước khi chọn matcher là: **consumer dựa vào vị trí của phần tử hay chỉ dựa vào việc phần tử có tồn tại?**

## 2. Quyết định thứ tự từ nhu cầu nghiệp vụ

| Dữ liệu trả về | Thứ tự có ý nghĩa? | Quy tắc assertion nên dùng |
| --- | --- | --- |
| Các bước xử lý: `CREATED → PICKED → SHIPPED` | **Có**: biểu diễn trình tự công việc. | So thứ tự từng phần tử hoặc quan hệ trước/sau. |
| Kết quả tìm kiếm `sort=price,asc` | **Có**: consumer kỳ vọng kết quả được sắp theo giá. | Kiểm thứ tự giá; với giá bằng nhau, xác định thêm tie-breaker nếu cần tính ổn định. |
| Top 3 sản phẩm theo xếp hạng | **Có**: vị trí quyết định thứ hạng. | Kiểm phần tử tại từng vị trí hoặc thứ tự `rank`. |
| Tập vai trò `READER`, `EDITOR` của người dùng | **Không**, nếu API chỉ công bố các vai trò đang có. | Kiểm đủ phần tử, không phụ thuộc hoán vị; quyết định cả quy tắc trùng lặp. |
| Tập thẻ (tags) của bài viết | **Thường không**, nếu API mô tả như tập giá trị. | Kiểm nội dung không phân biệt thứ tự và không có trùng lặp nếu được cam kết. |
| Danh sách item trong giỏ hàng | **Tùy hợp đồng**: có thể là tập item theo SKU hoặc dãy người dùng đã sắp xếp. | Chọn so tập hợp hoặc so thứ tự theo nghiệp vụ thực. |
| Các sự kiện nhận từ message broker | **Phụ thuộc bảo đảm thứ tự của hệ thống và cách phân vùng**. | Chỉ khẳng định trình tự khi producer/broker thực sự có cam kết liên quan. |

**Thứ tự trên dây truyền không đồng nghĩa với cam kết thứ tự.** JSON array luôn có vị trí phần tử, nhưng một endpoint công bố tập các vai trò có thể trả các hoán vị khác nhau theo thứ tự truy vấn cơ sở dữ liệu, cấu trúc `Set` hoặc cách serialize. Ngược lại, nếu API công bố kết quả được sắp xếp, consumer có quyền phụ thuộc vào thứ tự đó.

Khi thứ tự **có** ý nghĩa, hãy ghi cụ thể quy tắc: theo `createdAt` tăng dần, theo `rank` giảm dần, hay đúng thứ tự xử lý. Khi thứ tự **không** có ý nghĩa, hãy ghi rõ tính chất tập hợp: có cho phép trùng lặp không, có yêu cầu đủ mọi phần tử không, có cho phép phần tử bổ sung không.

## 3. Hai tình huống xuyên suốt

Giả sử **Shipping Service** là producer, còn **Order Portal** là consumer.

### 3.1. Danh sách bước vận chuyển: thứ tự bắt buộc

~~~http
GET /api/shipments/42/steps
~~~

~~~json
{
  "shipmentId": 42,
  "steps": [
    {"code":"CREATED","sequence":1},
    {"code":"PICKED","sequence":2},
    {"code":"SHIPPED","sequence":3}
  ]
}
~~~

Portal trình bày một timeline. Nếu `SHIPPED` xuất hiện trước `CREATED`, timeline sai. Vì thế, hợp đồng cần bảo vệ **thứ tự các bước**; chỉ kiểm đủ ba mã trạng thái là chưa đủ.

### 3.2. Danh sách quyền: thứ tự không quan trọng

~~~http
GET /api/users/42/roles
~~~

~~~json
{"roles":["READER","EDITOR"]}
~~~

Nếu nghiệp vụ quy định tập quyền hiện tại là `{READER, EDITOR}`, response sau cũng đúng:

~~~json
{"roles":["EDITOR","READER"]}
~~~

Consumer chỉ cần biết có đúng hai quyền này. Nếu test yêu cầu `READER` luôn đứng trước `EDITOR`, test đang áp đặt một **điều kiện không nằm trong hợp đồng nghiệp vụ**.

## 4. Bốn mức độ assertion dễ nhầm

Các bộ thư viện kiểm thử như **AssertJ**, **Hamcrest** hay công cụ kiểm JSON có nhiều kiểu assertion, không có kiểu nào phù hợp cho tất cả API.

| Ý định | Ví dụ AssertJ trên `List<String> actual` | Kết quả có ý nghĩa |
| --- | --- | --- |
| Bằng dãy **đúng thứ tự và đúng số phần tử** | `assertThat(actual).containsExactly("CREATED", "PICKED", "SHIPPED");` | Đổi chỗ, thiếu hoặc thêm phần tử đều thất bại. |
| Bằng **cùng các phần tử và số lần xuất hiện**, bỏ qua thứ tự | `assertThat(actual).containsExactlyInAnyOrder("READER", "EDITOR");` | Đổi chỗ được chấp nhận; thiếu, thừa hoặc trùng sai số lần sẽ thất bại. |
| Có chứa các phần tử yêu cầu nhưng **có thể có thêm** | `assertThat(actual).contains("READER", "EDITOR");` | Hữu ích khi hợp đồng chỉ đòi có các giá trị; **không chứng minh danh sách chỉ gồm những giá trị ấy**. |
| Chỉ gồm những giá trị thuộc tập cho phép, **có thể bỏ qua trùng lặp** | `assertThat(actual).containsOnly("READER", "EDITOR");` | Không phù hợp khi số lần xuất hiện là một phần của hợp đồng. |

Ví dụ Java:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

List<String> orderedSteps = List.of("CREATED", "PICKED", "SHIPPED");
assertThat(orderedSteps)
    .containsExactly("CREATED", "PICKED", "SHIPPED");

List<String> unorderedRoles = List.of("EDITOR", "READER");
assertThat(unorderedRoles)
    .containsExactlyInAnyOrder("READER", "EDITOR");
~~~

Nếu response có `["READER","READER","EDITOR"]`, phép kiểm `containsExactlyInAnyOrder("READER", "EDITOR")` **phải thất bại** vì số phần tử và số lần xuất hiện không đúng. Với API coi vai trò như **set**, đây thường là điều mong muốn. Nếu API cho phép trùng lặp và chỉ quan tâm các loại quyền xuất hiện, hãy tuyên bố quy tắc khác rõ ràng.

**Cẩn thận với phép kiểm quá yếu:** dùng `hasItem("READER")` hoặc `contains("READER")` để kiểm tập quyền không chứng minh `EDITOR` tồn tại hay không có quyền thừa như `ADMIN`. Chỉ bỏ qua **thứ tự** không có nghĩa được phép bỏ qua **số phần tử, giá trị hoặc tính duy nhất**.

## 5. Groovy DSL khi thứ tự bắt buộc

Với Shipping Service, có thể đặt hợp đồng tại `src/test/resources/contracts/shipping/get_steps.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnOrderedShipmentSteps'
    description 'Các bước vận chuyển theo đúng thứ tự xử lý'

    request {
        method 'GET'
        url '/api/shipments/42/steps'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            shipmentId: 42,
            steps: [
                [code: 'CREATED', sequence: 1],
                [code: 'PICKED',  sequence: 2],
                [code: 'SHIPPED', sequence: 3]
            ]
        )
    }
}
~~~

Trong hợp đồng này, danh sách mẫu thể hiện một **dãy có thứ tự**. Khi producer thực thi, generated producer test cần kiểm hành vi tương ứng với hợp đồng, trong đó có thứ tự nếu nó là một phần yêu cầu. Với các cấu hình sinh test có so sánh JSON array, việc đảo `PICKED` và `SHIPPED` thường sẽ làm phép so sánh dãy thất bại.

**Không suy đoán chỉ từ Groovy source:** hãy mở generated test để xem các assertion đang được tạo ra cho `$.steps`. Tùy phiên bản plugin, test mode và body matcher, mã được sinh có thể so cả cấu trúc JSON, từng JSONPath hoặc một matcher khác. Nếu việc giữ thứ tự là yêu cầu bắt buộc, cần **thấy một assertion thực sự kiểm thứ tự** và cố tình đảo hai phần tử để xác nhận producer test thất bại.

Ví dụ với MockMvc và Hamcrest, một assertion kiểm đúng thứ tự mã bước:

~~~java
import static org.hamcrest.Matchers.contains;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/shipments/42/steps"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.steps[*].code",
            contains("CREATED", "PICKED", "SHIPPED")));
~~~

Đây là **đoạn trong một test Java** với `mockMvc` đã cấu hình; nó minh họa điều cần được kiểm. Nếu chỉ so `sequence` tăng dần mà không kiểm các mã trạng thái, producer vẫn có thể trả đúng thứ tự số nhưng sai nội dung. Với giao diện timeline, thông thường cần **cả thứ tự lẫn dữ liệu của từng bước**.

## 6. Groovy DSL khi thứ tự không có ý nghĩa

Một contract mô tả tập quyền có thể bắt đầu với body mẫu:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnUserRoles'
    description 'Trả đúng các quyền, không cam kết thứ tự'

    request {
        method 'GET'
        url '/api/users/42/roles'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            roles: ['READER', 'EDITOR']
        )
    }
}
~~~

**Đây mới là hợp đồng có một body mẫu.** Chỉ viết trong `description` rằng “không cam kết thứ tự” **không bảo đảm generated producer test bỏ qua thứ tự**. Nếu công cụ sinh assertion so toàn bộ array với thứ tự cố định, build có thể báo lỗi khi producer trả `["EDITOR","READER"]` dù hai bên thống nhất rằng nó tương đương.

Để biểu diễn đúng quy tắc, cần **chọn matcher của Spring Cloud Contract phù hợp với công cụ/phiên bản dự án** hoặc dùng cơ chế custom assertion được hỗ trợ, và **đối chiếu generated test**. Một hướng mở rộng của Groovy DSL là khai báo custom matcher cho đường dẫn JSON:

~~~groovy
// Minh họa phần bổ sung bên trong response, cần triển khai helper
// trong base test và xác minh cách plugin sinh assertion.
bodyMatchers {
    jsonPath('$.roles', by_command('assertRolesIgnoringOrder($it)'))
}
~~~

`by_command` cho phép ủy quyền xác minh sang hàm kiểm thử do dự án cung cấp. Phần `assertRolesIgnoringOrder` phải được triển khai tại lớp/cấu hình base test có thể truy cập từ generated test; kiểu tham số cụ thể và cách truyền `$it` cần được đối chiếu với mã test được sinh trong phiên bản Spring Cloud Contract đang sử dụng. **Không nên chỉ sao chép đoạn này rồi coi việc bỏ qua thứ tự đã được bảo đảm.**

Ví dụ logic mà custom assertion cần thực hiện:

~~~java
// Minh họa ý định kiểm thử sau khi đã lấy được List<String> roles.
// Mã nhận giá trị từ generated test cần phù hợp kiểu tham số thực tế.
void assertRolesIgnoringOrder(List<String> roles) {
    assertThat(roles)
        .containsExactlyInAnyOrder("READER", "EDITOR");
}
~~~

Khi tùy biến matcher, cần xem lại **toàn bộ generated assertions** để chắc chắn không còn một phép so sánh thứ tự ở nơi khác làm hợp đồng bị chặt hơn dự kiến. Nếu phiên bản plugin chưa hỗ trợ biểu đạt chính xác ràng buộc mong muốn trong DSL, có thể giữ đặc tả cơ bản và bổ sung **producer integration test rõ ràng**, đồng thời ghi nhận giới hạn của generated test trước khi công bố rằng giao diện đã được bảo vệ đầy đủ.

## 7. So sánh trong producer test: exact order và any order

Với Spring MVC, `MockMvc` kết hợp `jsonPath` và Hamcrest giúp biểu diễn ý định một cách trực tiếp:

~~~java
import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Timeline: thứ tự đúng là một phần của hợp đồng.
mockMvc.perform(get("/api/shipments/42/steps"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.steps[*].code",
        contains("CREATED", "PICKED", "SHIPPED")));

// Vai trò: đúng giá trị và số phần tử, không xét thứ tự.
mockMvc.perform(get("/api/users/42/roles"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.roles",
        containsInAnyOrder("READER", "EDITOR")));
~~~

Đây là đoạn test minh họa; giả định `mockMvc` có sẵn, dữ liệu fixture đã chuẩn bị và các endpoint tồn tại. Hamcrest `contains` kiểm từng phần tử theo thứ tự, còn `containsInAnyOrder` kiểm tập phần tử kỳ vọng theo dạng **không quan tâm hoán vị nhưng có xét số lượng/lần xuất hiện**.

**Một test viết tay không tự xóa assertion do Spring Cloud Contract sinh.** Nếu generated test áp đặt thứ tự cố định cho `$.roles`, dù test MockMvc riêng đã dùng `containsInAnyOrder`, pipeline producer vẫn có thể thất bại. Nhóm cần thống nhất matcher trong hợp đồng và xác minh điều kiện thực sự đang được generated test kiểm.

### 7.1. Thử cố tình hoán đổi để kiểm độ nhạy

Hãy làm hai thử nghiệm độc lập:

1. Đổi thứ tự `PICKED` và `SHIPPED` của endpoint timeline. **Producer test phải thất bại** nếu kiểm thử hợp đồng đã bảo vệ thứ tự.
2. Đổi thứ tự `READER` và `EDITOR` của endpoint roles. **Producer test phải tiếp tục đạt** nếu hợp đồng không cam kết thứ tự và matcher đã được cấu hình đúng.

Nếu kết quả ngược lại, đó là dấu hiệu **assertion đang kiểm sai điều kiện so với nghiệp vụ**. Cần kiểm contract, generated test và matcher thực tế, rồi sửa ở nguồn đặc tả/test setup phù hợp.

## 8. Request JSON array: Stub Runner và WireMock có khớp đúng thứ tự không?

Không chỉ response, **request body** cũng có thể chứa array. Ví dụ consumer gửi danh sách quyền để cập nhật:

~~~http
PUT /api/users/42/roles
Content-Type: application/json

{"roles":["READER","EDITOR"]}
~~~

Nếu API quy định đây là **tập các quyền**, request:

~~~json
{"roles":["EDITOR","READER"]}
~~~

phải được xử lý tương đương. Nhưng nếu stub mapping chỉ khớp JSON với thứ tự cố định, consumer test có thể nhận **404 không khớp mapping** khi đổi hoán vị. Khi đó lỗi nằm ở độ chặt của **stub request matcher**, chưa chắc consumer đã gọi sai API.

Với HTTP, Spring Cloud Contract thường tạo mapping để WireMock mô phỏng producer. Một ví dụ **thuần WireMock** diễn đạt ý tưởng khớp JSON array không phụ thuộc thứ tự:

~~~json
{
  "request": {
    "method": "PUT",
    "url": "/api/users/42/roles",
    "bodyPatterns": [
      {
        "equalToJson": "{\"roles\":[\"READER\",\"EDITOR\"]}",
        "ignoreArrayOrder": true,
        "ignoreExtraElements": false
      }
    ]
  },
  "response": {
    "status": 204
  }
}
~~~

`ignoreArrayOrder: true` chỉ định **bỏ qua thứ tự phần tử trong phép so khớp JSON array** của mapping này. `ignoreExtraElements: false` cho biết không chủ ý bỏ qua phần tử/thuộc tính ngoài mong đợi trong kiểu so khớp đó. Đây là **minh họa cú pháp một WireMock mapping**, **không cam kết** plugin Spring Cloud Contract sinh ra chính xác JSON trên từ bất kỳ Groovy/YAML contract nào.

Để dùng trong dự án thật, hãy kiểm tài liệu và khả năng **request matcher của DSL tại phiên bản đang dùng**, chạy build rồi mở mapping được đóng gói trong artifact `stubs`. Không sửa tay file mapping **đã sinh** rồi tiếp tục publish như thể nó vẫn xuất phát đầy đủ từ hợp đồng: lần build tiếp theo có thể ghi đè sửa đổi, làm producer test và stub lệch nguồn đặc tả.

## 9. Thứ tự và so sánh trong YAML DSL

Nếu nhóm chọn YAML, có thể mô tả danh sách bước theo thứ tự trong `response.body`:

~~~yaml
description: Trả về các bước giao hàng theo trình tự nghiệp vụ
request:
  method: GET
  url: /api/shipments/42/steps
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    shipmentId: 42
    steps:
      - code: CREATED
        sequence: 1
      - code: PICKED
        sequence: 2
      - code: SHIPPED
        sequence: 3
~~~

Các dấu `-` trong YAML biểu diễn một **sequence có thứ tự**. Tuy nhiên, YAML là ngôn ngữ biểu diễn dữ liệu; việc generated producer test so array chính xác theo thứ tự hay dùng matcher khác phụ thuộc **cách Spring Cloud Contract phân tích hợp đồng và cấu hình matchers**.

Đối với một **tập quyền** không quan tâm thứ tự, YAML có thể biểu diễn **body mẫu**:

~~~yaml
description: Trả các quyền hiện có
request:
  method: GET
  url: /api/users/42/roles
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    roles:
      - READER
      - EDITOR
~~~

Tuy nhiên **không nên suy** rằng chỉ việc có sequence trong YAML nghĩa là plugin tự kiểm theo tập hợp. Nếu muốn bỏ qua thứ tự, cần thiết lập matcher/assertion phù hợp trong phiên bản đang dùng và xác nhận phép kiểm thực tế. Tên, cấu trúc và khả năng của custom body matcher trong YAML/Groovy không nhất thiết tương đương từng chữ; tránh tự viết một khóa `ignoreOrder: true` vào YAML DSL khi chưa xác nhận công cụ hỗ trợ.

## 10. Kiểm consumer: đừng để test chặt hơn hoặc lỏng hơn hợp đồng

Giả sử **Order Portal** có hai HTTP client:

- `ShippingClient.getSteps(42)` trả `List<ShipmentStep>` theo thứ tự bước vận chuyển.
- `UserClient.getRoles(42)` trả `List<String>` các quyền người dùng, trong đó thứ tự không mang ý nghĩa.

Trong test dùng **Spring Cloud Contract Stub Runner**, consumer có thể cấu hình stub cho hai producer tương ứng. Đoạn sau minh họa cách **assert**, còn cơ chế load hai artifact và base URL phải được cấu hình đúng trong dự án:

~~~java
@Test
void shouldKeepTimelineOrder() {
    List<String> steps = shippingClient.getSteps(42L).stream()
        .map(ShipmentStep::code)
        .toList();

    assertThat(steps)
        .containsExactly("CREATED", "PICKED", "SHIPPED");
}

@Test
void shouldAcceptEitherRoleOrder() {
    List<String> roles = userClient.getRoles(42L);

    assertThat(roles)
        .containsExactlyInAnyOrder("READER", "EDITOR");
}
~~~

Hai test tiêu thụ **mã HTTP client thật**, nên kiểm được việc tạo request, deserialize JSON và xử lý danh sách. Nếu consumer chuyển dữ liệu vào `HashSet` trước khi kiểm timeline, thông tin thứ tự đã mất; test có thể không phát hiện producer trả sai thứ tự. Ngược lại, nếu consumer dùng `List.equals` để so roles, có thể báo lỗi giả khi producer đổi thứ tự.

**Giới hạn của consumer test trên stub:** stub thường trả một **response mẫu cố định**, nên test với Stub Runner chỉ thấy hoán vị có trong mapping. Một test roles với `containsExactlyInAnyOrder` phù hợp về ý định nhưng **chưa chứng minh** client xử lý chính xác mọi hoán vị nếu stub luôn trả `["READER","EDITOR"]`. Khi cần bảo vệ việc consumer **không phụ thuộc thứ tự**, hãy thêm một test với hoán vị khác bằng fixture/stub có chủ đích hoặc một phép kiểm độc lập; giữ nguồn contract và các biến thể kiểm thử nhất quán.

## 11. Danh sách object: so theo khóa nghiệp vụ khi thứ tự không quan trọng

So một array các object bằng thứ tự ngẫu nhiên thường gây test không ổn định. Xét response:

~~~json
{
  "items": [
    {"sku":"SKU-A","quantity":1},
    {"sku":"SKU-B","quantity":2}
  ]
}
~~~

Nếu API xác định `items` là một tập các dòng hàng, hãy kiểm **cả cặp SKU và quantity** trong mỗi phần tử:

~~~java
record LineItem(String sku, int quantity) {}

List<LineItem> actual = List.of(
    new LineItem("SKU-B", 2),
    new LineItem("SKU-A", 1)
);

assertThat(actual).containsExactlyInAnyOrder(
    new LineItem("SKU-A", 1),
    new LineItem("SKU-B", 2)
);
~~~

Chỉ lấy riêng các SKU rồi kiểm `containsInAnyOrder("SKU-A","SKU-B")` **không phát hiện** producer tráo số lượng giữa hai SKU. Với dữ liệu lồng nhau, dùng matcher giữ được **quan hệ giữa các trường trong cùng object**.

Nếu số lần xuất hiện của mỗi SKU cần đúng bằng một, đừng vô tình chuyển toàn bộ danh sách thành `Set` trước khi so; phép chuyển đó có thể loại các phần tử trùng mà API không cho phép. Nếu API cho phép cùng SKU xuất hiện nhiều lần với ý nghĩa độc lập, yêu cầu kiểm tra lại khác với một tập SKU duy nhất.

## 12. Phân trang, xếp hạng và thứ tự không ổn định

Một danh sách có thứ tự nhưng **không xác định đầy đủ cách phá hòa** cũng tạo test thất thường. Ví dụ API:

~~~http
GET /api/products?sort=price,asc&page=0&size=3
~~~

Nếu hai sản phẩm cùng giá, thứ tự giữa chúng có thể thay đổi giữa các lần query. Có hai lựa chọn thiết kế hợp lệ:

1. **Cam kết thứ tự ổn định:** thêm khóa phụ như `id` tăng dần khi `price` bằng nhau. Khi đó hợp đồng có thể so thứ tự chính xác, và phân trang ổn định hơn.
2. **Chỉ cam kết thứ tự theo giá:** test cần kiểm giá không giảm, đồng thời tránh áp đặt vị trí cố định cho hai sản phẩm cùng giá. Nếu consumer cần thứ tự xác định qua nhiều trang, hợp đồng nên được làm rõ thêm.

Khi phân trang, **thứ tự có thể ảnh hưởng trực tiếp việc bỏ sót/lặp phần tử qua các trang**. Không bỏ qua thứ tự chỉ để giảm test đỏ nếu API có cam kết `sort` hoặc `rank`. Ngược lại, đừng ghi một danh sách cố định vào contract rồi ngầm yêu cầu mọi lần gọi cùng dữ liệu phải có thứ tự giống nhau khi API không hứa điều đó.

## 13. Hợp đồng thông điệp cũng cần phân biệt thứ tự

Spring Cloud Contract có thể mô tả **messaging** bên cạnh HTTP. Một event có array `items` vẫn có câu hỏi giống JSON response: các item là trình tự hay một tập hợp? Ngoài ra, **thứ tự giữa các thông điệp** là một khía cạnh khác:

- Trong **một payload**, thứ tự array có thể được consumer sử dụng như trình tự xử lý.
- Giữa **nhiều message**, bảo đảm thứ tự phụ thuộc broker, partition/key, concurrency, retry và cách triển khai. Không nên suy từ hai hợp đồng event riêng rằng mọi consumer luôn nhận đúng thứ tự thời gian.
- Các test contract xác minh cấu trúc/thông điệp được phát trong những tình huống được mô tả; việc kiểm **thứ tự end-to-end của nhiều event** thường cần thêm integration test trên broker và cấu hình thực.

Nếu thứ tự event mang ý nghĩa, cần xác định chính xác **phạm vi bảo đảm** (ví dụ trong cùng một key/partition) và test điều kiện đó. Một matcher array không thay thế kiểm chứng trật tự giao nhận thông điệp ở hạ tầng thật.

## 14. Quy trình xác minh trong CI

Luồng kiểm thử đầy đủ nên đối chiếu **quy tắc thứ tự trong contract**, **assertion ở producer** và **cách consumer sử dụng stub**:

~~~mermaid
flowchart TD
    A["Xác định ngữ nghĩa thứ tự của API"] --> B["Viết contract và matcher phù hợp"]
    B --> C["Sinh và xem producer test"]
    C --> D["Đảo thứ tự dữ liệu có kiểm soát"]
    D --> E{"Kết quả đúng ý định?"}
    E -->|Không| F["Điều chỉnh matcher/assertion, chạy lại"]
    F --> C
    E -->|Có| G["Producer verification đạt"]
    G --> H["Đóng gói và phát hành stubs theo version"]
    H --> I["Stub Runner chạy consumer tests"]
    I --> J["Kiểm thứ tự, giá trị và số phần tử theo hợp đồng"]
~~~

Checklist của pipeline:

1. **Review contract:** ghi rõ danh sách có cam kết thứ tự hay không; loại assertion có kiểm đủ phần tử, số lần xuất hiện và các trường quan trọng không.
2. **Generated producer test:** xác nhận plugin thực sự sinh và chạy assertion có ngữ nghĩa phù hợp. Đừng chỉ dựa vào `BUILD SUCCESS`.
3. **Kiểm thử gây sai lệch:** đảo phần tử trong endpoint ordered thì test phải **FAIL**; đảo phần tử trong endpoint unordered thì test phải **PASS** nếu nội dung không đổi.
4. **Stub mapping:** kiểm request matcher của các array trong HTTP request, đặc biệt khi thứ tự không mang ý nghĩa; chạy cả hai hoán vị và các trường hợp thêm, thiếu, trùng phần tử.
5. **Consumer test:** dùng mã client thật, chọn `containsExactly` hay `containsExactlyInAnyOrder` theo ngữ nghĩa đã thỏa thuận. Với dữ liệu lồng nhau, kiểm đúng quan hệ field.
6. **Publish/version:** chỉ phát hành stub sau khi producer verification đạt, dùng artifact version rõ ràng và kiểm consumer còn được hỗ trợ khi thay đổi cam kết thứ tự.

Việc chuyển API từ “danh sách có thứ tự xác định” sang “có thể trả bất kỳ thứ tự nào” có thể là **breaking change** nếu consumer dựa vào vị trí. Ngược lại, bổ sung thứ tự ổn định cho API vốn coi là tập hợp có thể tương thích về dữ liệu nhưng vẫn nên review chi phí và hành vi mới. Nếu producer sửa contract để bỏ assertion thứ tự, test mới xanh **không chứng minh** consumer cũ còn tương thích.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách phát hiện và sửa |
| --- | --- | --- |
| So nguyên văn chuỗi JSON khi kiểm object. | Thay thứ tự khóa cũng làm test đỏ dù dữ liệu giống nhau. | Parse JSON rồi so trường, kiểu và giá trị. |
| Dùng exact order cho tập quyền. | Producer đổi hoán vị hợp lệ làm build thất bại giả. | Thỏa thuận ngữ nghĩa tập hợp, dùng matcher không phụ thuộc thứ tự và xác minh generated test. |
| Dùng unordered assertion cho timeline. | Đảo `PICKED` và `SHIPPED` không bị phát hiện. | Kiểm thứ tự bằng `containsExactly` hoặc quan hệ vị trí. |
| Chỉ dùng `contains` khi phải kiểm đủ danh sách. | Phần tử thừa hoặc thiếu có thể bị bỏ sót. | Dùng phép kiểm đúng số lượng và nội dung. |
| Chuyển sang `Set` trước khi kiểm list. | Mất thứ tự và/hoặc số lần xuất hiện. | Giữ list gốc; chọn equality theo hợp đồng. |
| Chỉ đọc `description` của contract. | Generated test vẫn có thể áp đặt thứ tự từ body array mẫu. | Kiểm test được sinh và chạy hoán vị ngược. |
| Chỉnh trực tiếp stub mapping đã sinh. | Test/stub lệch nguồn hợp đồng, lần build sau ghi đè thay đổi. | Sửa tại nguồn DSL/cấu hình sinh stub được hỗ trợ và kiểm lại artifact. |
| Coi mọi WireMock 404 là lỗi nghiệp vụ. | Request không khớp array matcher cũng trả 404, test lỗi có thể đạt giả. | Phân biệt no-match và response lỗi có body/code hợp đồng. |
| Chỉ kiểm SKU mà bỏ quantity ở từng item. | Tráo dữ liệu giữa các item nhưng test vẫn đạt. | So object hoàn chỉnh hoặc theo khóa nghiệp vụ. |
| Ghim thứ tự cho dữ liệu phân trang thiếu tie-breaker. | Test ngẫu nhiên đỏ theo thứ tự query. | Xác định sort/tie-breaker hoặc kiểm đúng mức cam kết. |

## 16. Bài thực hành: kiểm hai API theo hai loại thứ tự

Trên dự án Spring Boot đã cấu hình Spring Cloud Contract Verifier và một consumer có Stub Runner:

1. **Viết hợp đồng ordered** cho `GET /api/shipments/42/steps` gồm `CREATED`, `PICKED`, `SHIPPED` theo thứ tự. Sinh producer test và kiểm generated assertion có bảo vệ thứ tự.
2. **Gây lỗi có chủ đích:** cho producer trả `SHIPPED` trước `PICKED`; chạy test và xác nhận **FAIL**. Sửa lại để **PASS**.
3. **Viết hợp đồng unordered** cho `GET /api/users/42/roles` với hai quyền `READER` và `EDITOR`, tuyên bố rõ không cam kết thứ tự và không chấp nhận quyền thừa.
4. **Điều chỉnh matcher/assertion** theo khả năng DSL của phiên bản đang dùng; chạy hai hoán vị và yêu cầu **đều PASS** khi nội dung giống nhau. Nếu generated test vẫn kiểm thứ tự, chưa coi phần này đạt.
5. **Thêm phần tử trùng** `READER` hoặc quyền thừa `ADMIN` vào response roles; assertion phù hợp phải **FAIL** nếu API chỉ cho đúng hai quyền và không cho trùng lặp.
6. **Kiểm request array** của endpoint cập nhật quyền; tạo artifact stub và dùng Stub Runner gọi cả `["READER","EDITOR"]` lẫn `["EDITOR","READER"]`. Nếu API không cam kết thứ tự nhưng stub chỉ match một hoán vị, kiểm mapping và sửa cách biểu đạt matcher.
7. **Chạy consumer tests**: timeline dùng `containsExactly`, roles dùng `containsExactlyInAnyOrder`; thêm một tình huống lồng nhau để kiểm đầy đủ cả `sku` lẫn `quantity`.
8. **Đưa vào CI** với bước producer verification trước publish, artifact `stubs` theo version và consumer tests kiểm đúng ngữ nghĩa thứ tự. Ghi rõ những tình huống deliberately FAIL/PASS khi hoán đổi.

Kết quả cần đạt không chỉ là một build xanh. Bạn phải **giải thích vì sao đổi thứ tự làm test timeline thất bại nhưng không làm test roles thất bại**, chỉ ra assertion tương ứng trong generated test hoặc test bổ sung, và chứng minh stub request matcher không tự áp đặt thứ tự mà API đã tuyên bố không có ý nghĩa.

## 17. Câu hỏi tự kiểm tra

1. Thứ tự khóa trong JSON object và thứ tự phần tử trong JSON array khác nhau thế nào?
2. Khi API trả tập vai trò của người dùng, vì sao `containsExactlyInAnyOrder` thường phù hợp hơn `containsExactly`?
3. Nếu danh sách có phần tử trùng lặp, tại sao không nên tự chuyển sang `Set` rồi so?
4. Chỉ thêm `description 'không quan tâm thứ tự'` trong Groovy contract có đủ để generated test bỏ qua thứ tự không?
5. Với timeline, kiểm đủ ba mã trạng thái nhưng không kiểm vị trí có thể bỏ sót lỗi nào?
6. Vì sao request `{"roles":["EDITOR","READER"]}` có thể bị WireMock trả 404 dù hai giá trị đều đúng?
7. Khi API cam kết sắp theo giá nhưng hai giá bằng nhau, cần làm gì để tránh kiểm thử thứ tự thiếu ổn định?
8. Nếu generated producer test và consumer test đều xanh sau khi bỏ ràng buộc thứ tự cũ, điều gì cần kiểm trước khi khẳng định không có breaking change?

**Ghi nhớ:** JSON array có thứ tự ở mức biểu diễn, nhưng **thứ tự chỉ là một phần của hợp đồng khi producer và consumer cam kết nó có ý nghĩa**. Dùng assertion **đúng thứ tự** cho timeline, xếp hạng và kết quả có sort; dùng assertion **không phụ thuộc thứ tự nhưng vẫn kiểm đủ nội dung và số lần xuất hiện** cho tập hợp. Với Spring Cloud Contract, luôn đối chiếu **DSL → generated producer tests → stub mappings → consumer tests qua Stub Runner** để điều kiện kiểm thử phản ánh đúng hành vi API và có thể phát hiện thay đổi không tương thích.
