# Mô tả hành vi quan sát được thay vì chi tiết triển khai

## Mục tiêu bài học

Trong kiểm thử hợp đồng giữa **producer** (dịch vụ cung cấp API hoặc phát thông điệp) và **consumer** (dịch vụ hoặc ứng dụng sử dụng API/thông điệp), một hợp đồng tốt phải trả lời được câu hỏi:

> Khi consumer gửi một yêu cầu hoặc nhận một thông điệp hợp lệ, consumer có thể quan sát và dựa vào những hành vi nào của producer?

Hợp đồng không cần mô tả producer dùng lớp Java nào, lưu dữ liệu trong bảng nào hay gọi bao nhiêu phương thức nội bộ. Với **Spring Cloud Contract**, các hành vi quan sát được được mô tả bằng **Groovy DSL** hoặc **YAML DSL**. Từ đó, công cụ có thể sinh kiểm thử xác minh phía producer và tạo stub để consumer kiểm thử tích hợp trước khi hai hệ thống chạy cùng nhau.

Sau bài này, bạn có thể:

- Phân biệt cam kết công khai với quyết định triển khai nội bộ.
- Chọn đúng đầu vào, đầu ra và trường hợp lỗi để đưa vào hợp đồng HTTP hoặc thông điệp.
- Viết hợp đồng minh họa bằng Groovy/YAML DSL mà không gắn chặt với cấu trúc mã nguồn producer.
- Nhận biết thay đổi tương thích và thay đổi có nguy cơ phá vỡ consumer.
- Hiểu cách test được sinh, stub, Stub Runner và CI cùng kiểm tra các cam kết đó.

## 1. Hợp đồng là ranh giới mà consumer thực sự nhìn thấy

Hãy hình dung producer như một **hộp đen**. Consumer chỉ biết cách gửi yêu cầu, nhận phản hồi hoặc xử lý thông điệp công khai. Producer có thể đổi thuật toán, cơ sở dữ liệu, framework hoặc cấu trúc package mà consumer không cần sửa theo, miễn các cam kết ở ranh giới tích hợp vẫn được giữ.

Với một API HTTP, hành vi quan sát được thường gồm:

| Thành phần | Câu hỏi của consumer | Ví dụ cam kết |
| --- | --- | --- |
| Yêu cầu | Gọi endpoint bằng cách nào? | GET /api/orders/ORD-1001 |
| Đầu vào | Tham số, header, body nào có ý nghĩa? | Mã đơn hàng trên URL; Accept: application/json |
| Phản hồi thành công | Khi hợp lệ, nhận trạng thái và dữ liệu nào? | HTTP 200; JSON chứa id và status |
| Phản hồi lỗi | Nếu dữ liệu không tồn tại hoặc đầu vào sai thì sao? | HTTP 404 cùng mã lỗi ORDER_NOT_FOUND |
| Quy tắc dữ liệu | Consumer có thể dựa vào kiểu hoặc tập giá trị nào? | status là chuỗi; PAID thể hiện đơn đã thanh toán |
| Tác động công khai | Sau một thao tác, kết quả nào có thể quan sát? | Tạo đơn hàng thành công trả mã đơn dùng được ở lần truy vấn tiếp theo |

Với hợp đồng thông điệp, ranh giới quan sát được là **sự kiện được phát/nhận**, loại thông điệp, trường dữ liệu, header hoặc metadata cần thiết và cách consumer diễn giải chúng. Tên hàng đợi hoặc topic chỉ là một phần hợp đồng nếu đó thực sự là giao diện tích hợp mà consumer được cam kết sử dụng.

Ngược lại, các chi tiết sau thường **không thuộc hợp đồng**:

- Lớp OrderController gọi OrderService hay một facade.
- Dữ liệu được đọc từ PostgreSQL, Redis hay một dịch vụ khác.
- Producer dùng JPA, JDBC, WebFlux hoặc thay đổi kiến trúc module.
- Số lượng truy vấn SQL, tên cột, tên bảng và thứ tự gọi hàm.
- Thời gian xử lý chính xác hoặc tên máy chủ nội bộ, trừ khi có cam kết bên ngoài rõ ràng liên quan đến chúng.

Điều quan trọng là **phân loại theo cam kết**, không theo cách triển khai. Ví dụ, cơ chế cache thường là nội bộ; nhưng header HTTP Cache-Control do producer công khai lại có thể là hành vi cần kiểm tra. Tương tự, mã lỗi là phần giao diện nếu consumer dùng nó để quyết định bước tiếp theo; stack trace của Java thì không nên được đưa vào hợp đồng.

## 2. Thiết kế từ nhu cầu của consumer

Giả sử một ứng dụng bán hàng cần hiển thị trạng thái thanh toán của đơn hàng. Producer cung cấp API đơn hàng. Consumer chỉ cần biết mã đơn có tồn tại hay không và trạng thái hiện tại để quyết định hiển thị nút hoặc thông báo phù hợp.

Luồng tích hợp có thể mô tả như sau:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant P as Producer: Order API
    C->>P: GET /api/orders/ORD-1001
    alt Đơn hàng tồn tại
        P-->>C: 200 {"id":"ORD-1001","status":"PAID"}
        Note over C: Hiển thị "Đã thanh toán"
    else Không tìm thấy đơn
        P-->>C: 404 {"code":"ORDER_NOT_FOUND"}
        Note over C: Hiển thị thông báo phù hợp
    end
~~~

Để thiết kế hợp đồng, hãy trả lời lần lượt:

1. **Ai là consumer và họ cần quyết định điều gì?** Ứng dụng bán hàng phải biết trạng thái đơn hàng.
2. **Tín hiệu đầu vào nào có ý nghĩa?** Phương thức GET và mã đơn trên đường dẫn.
3. **Tín hiệu đầu ra tối thiểu nào đủ dùng?** HTTP status, id, status và mã lỗi khi không tìm thấy.
4. **Quy tắc nào cần được giữ ổn định?** Kiểu dữ liệu, ý nghĩa của PAID, HTTP 200/404 và cấu trúc lỗi.
5. **Điều gì có thể thay đổi mà không ảnh hưởng consumer?** Tên class, schema cơ sở dữ liệu, cache, thuật toán lấy trạng thái.

Tư duy này giúp tránh hai cực đoan: hợp đồng **quá mơ hồ** (chỉ kiểm tra HTTP 200 nên dữ liệu sai vẫn qua) và hợp đồng **quá chi tiết** (buộc producer giữ nguyên các trường hoặc thông tin mà consumer không sử dụng).

## 3. Đặc tả một hành vi HTTP bằng YAML DSL

Một hợp đồng cho trường hợp lấy đơn hàng đã thanh toán có thể viết như sau:

~~~yaml
description: "Trả về trạng thái của đơn hàng đã tồn tại"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Ví dụ này mô tả **một trường hợp có thể kiểm chứng**:

- Với GET và đường dẫn đã định, producer phải chấp nhận yêu cầu có header Accept tương ứng.
- Producer phải trả về HTTP 200 và một JSON có các giá trị như đã khai báo.
- Consumer có thể dựa vào trường id và status; không cần biết dữ liệu được nạp từ đâu.

Trong ví dụ, mã ORD-1001 và trạng thái PAID là **dữ liệu mẫu xác định**. Khi chạy test sinh bởi Spring Cloud Contract, producer phải được chuẩn bị trạng thái dữ liệu phù hợp với mẫu này (chẳng hạn bằng fixture trong test). Đây không phải chỉ dẫn phải tạo một bản ghi thật trong cơ sở dữ liệu production.

Nếu consumer chỉ cần **định dạng** của một mã sinh động hoặc mốc thời gian, không nên khóa cứng một giá trị ngẫu nhiên trong hợp đồng. Spring Cloud Contract hỗ trợ các matcher/biểu thức và giá trị khác nhau giữa phía consumer và producer; lựa chọn phù hợp tùy phiên bản DSL và quy tắc muốn cam kết. Chỉ kiểm tra đúng phần bất biến, chẳng hạn trường là chuỗi, có định dạng hợp lệ hoặc thuộc tập giá trị đã công bố.

### Cùng hành vi bằng Groovy DSL

Trong dự án dùng Groovy DSL, có thể biểu diễn trường hợp tương đương:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description("Trả về trạng thái của đơn hàng đã tồn tại")

    request {
        method GET()
        url "/api/orders/ORD-1001"
        headers {
            header("Accept", "application/json")
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID"
        )
    }
}
~~~

Hai cách biểu diễn có cùng mục tiêu: đặc tả **yêu cầu có thể gửi** và **phản hồi công khai có thể kiểm chứng**. Chọn DSL theo chuẩn dự án và tính năng cần dùng; không cần dùng cả hai cho cùng một kịch bản.

### Hợp đồng cho đường đi lỗi

Chỉ mô tả trường hợp thành công là chưa đủ nếu consumer cần phân biệt lỗi với kết quả trống. Một hợp đồng khác cho mã đơn không tồn tại:

~~~yaml
description: "Trả về lỗi khi không tìm thấy đơn hàng"
name: get_unknown_order
request:
  method: GET
  url: /api/orders/ORD-9999
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
~~~

Mã lỗi có cấu trúc giúp consumer xử lý ổn định hơn là phụ thuộc vào toàn bộ câu thông báo có thể được dịch hoặc biên tập lại. Nếu thông báo hiển thị **cũng** là một phần cam kết công khai thì mới cần đặc tả thêm.

Đối với API ghi dữ liệu, có thể cần hợp đồng cho đầu vào không hợp lệ (400), thiếu quyền (401/403) hoặc xung đột trạng thái (409) **khi các nhánh đó thực sự nằm trong hành vi mà consumer sử dụng**. Không nhất thiết liệt kê mọi lỗi giả định: mỗi hợp đồng nên phục vụ một tình huống tích hợp cụ thể.

## 4. Đừng biến hợp đồng thành kiểm thử cấu trúc mã nguồn

Giả sử producer ban đầu xử lý yêu cầu bằng OrderController, OrderService và OrderRepository. Nếu kiểm thử hợp đồng phụ thuộc vào số lần gọi repository, một lần thay đổi sang cache hoặc API khác sẽ làm test gãy dù consumer vẫn nhận đúng dữ liệu.

Ví dụ kiểm thử quá gắn với triển khai:

~~~java
// Đây là kiểm thử tương tác nội bộ, KHÔNG phải hợp đồng API.
verify(orderRepository, times(1)).findById("ORD-1001");
verify(orderMapper).toResponse(any());
~~~

Kiểm thử tương tác như trên có thể hữu ích trong một **unit test** cụ thể. Nhưng đối với ranh giới producer–consumer, điều cần đảm bảo là:

~~~text
Yêu cầu:  GET /api/orders/ORD-1001
Phản hồi: HTTP 200
          Content-Type: application/json
          {"id":"ORD-1001","status":"PAID"}
~~~

Sự khác biệt thực tế:

| Khi producer thay đổi... | Hợp đồng hành vi có cần đổi không? | Vì sao |
| --- | --- | --- |
| Chuyển từ SQL sang một nguồn dữ liệu khác | Không, nếu phản hồi công khai giữ nguyên | Consumer không truy cập cách lưu trữ |
| Tách một service thành nhiều lớp | Không | Call graph là chi tiết nội bộ |
| Đổi tên trường JSON status thành state | Có nguy cơ phá vỡ consumer | Consumer đọc tên trường công khai |
| Đổi phản hồi không tìm thấy từ 404 sang 200 với body rỗng | Có nguy cơ phá vỡ consumer | Consumer có thể điều khiển luồng theo status |
| Thêm trường JSON không bắt buộc | Thường có thể tương thích, cần xác minh | Phụ thuộc cách consumer parse dữ liệu và cam kết schema |
| Thay tập giá trị status, ví dụ bỏ PAID | Có nguy cơ phá vỡ consumer | Ý nghĩa nghiệp vụ của dữ liệu đã thay đổi |

Một quy tắc thực hành: **nếu thay đổi chỉ nằm bên trong producer và consumer không thể phân biệt bằng giao diện đã công bố, đừng viết hợp đồng buộc thay đổi đó phải lộ ra**.

## 5. Mức độ chính xác của hợp đồng: đủ chặt, đủ linh hoạt

Không phải mọi giá trị trong phản hồi đều cần khớp từng ký tự. Ngược lại, những gì consumer dựa vào phải được mô tả đủ chính xác.

### Nên ràng buộc rõ

- Phương thức, đường dẫn và các tham số bắt buộc của endpoint.
- HTTP status mà consumer dùng để phân nhánh.
- Tên trường JSON, kiểu dữ liệu và ý nghĩa nghiệp vụ cần thiết.
- Các giá trị thuộc miền nghiệp vụ quan trọng (ví dụ PAID, CANCELLED).
- Header như Content-Type, Location hoặc header điều phối phiên bản **nếu consumer phụ thuộc**.
- Định dạng số tiền, mã định danh, thời gian hoặc mã lỗi khi định dạng đó là giao diện công khai.

### Nên tránh ràng buộc tùy tiện

- Thứ tự các thuộc tính trong JSON object, khi thứ tự không có ý nghĩa.
- Timestamp, UUID hoặc giá trị random cụ thể nếu consumer chỉ cần định dạng.
- Thời lượng phản hồi từng mili giây trong hợp đồng chức năng; cam kết hiệu năng có phương pháp kiểm tra riêng.
- Các header do proxy hoặc môi trường triển khai tự thêm và consumer không sử dụng.
- Trường debug, stack trace, tên node, đường dẫn file hoặc dữ liệu nội bộ.
- Nội dung toàn bộ object chỉ vì producer đang trả về object đó, dù consumer dùng rất ít trường.

**Ví dụ với số tiền:** nếu consumer tính toán hoặc hiển thị tổng tiền, cần quyết định rõ số tiền được biểu diễn bằng số nguyên đơn vị nhỏ nhất, số thập phân hay chuỗi, và mã tiền tệ nằm ở đâu. Đừng thay đổi kiểu từ số sang chuỗi chỉ vì producer đổi thư viện biểu diễn tiền. Đó là quyết định giao diện, có khả năng ảnh hưởng consumer.

**Ví dụ với timestamp:** nếu hệ thống yêu cầu định dạng ISO-8601 có múi giờ, nên kiểm tra định dạng và ý nghĩa thời gian thay vì buộc mọi lần chạy trả về cùng một thời điểm. Cần tránh tạo test không ổn định do đồng hồ hệ thống.

Hợp đồng không phải là bản sao nguyên vẹn của mọi phản hồi từng xuất hiện trong môi trường thật. Nó là tập những **ví dụ và quy tắc có chủ đích** mà hai bên đồng ý duy trì.

## 6. Hành vi quan sát được của thông điệp bất đồng bộ

Spring Cloud Contract còn hỗ trợ mô tả hợp đồng cho các tương tác theo thông điệp, ngoài HTTP. Với một sự kiện cho biết đơn hàng đã được thanh toán, consumer thường quan tâm tới loại sự kiện và payload:

~~~json
{
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-24T04:00:00Z"
}
~~~

Đây là **mẫu payload minh họa**, không phải bản thân một file hợp đồng YAML/Groovy. Trong hợp đồng thông điệp thực tế, cần mô tả đầu vào kích hoạt hoặc đầu ra của producer, điểm gửi/nhận nếu đó là giao diện công khai, và các matcher tương ứng.

Hãy xác định consumer thực sự phụ thuộc vào:

| Cần cam kết | Không nên khóa chặt khi không được công bố |
| --- | --- |
| Loại sự kiện ORDER_PAID | Tên lớp Java tạo sự kiện |
| Trường orderId là mã đơn có định dạng hợp lệ | ID bản ghi nội bộ dùng trong database |
| Ý nghĩa và định dạng occurredAt | Thời điểm cố định trong ví dụ |
| Header định tuyến hoặc phiên bản khi consumer sử dụng | Cấu hình thread pool hoặc cách serialize nội bộ |
| Thứ tự, khả năng gửi trùng hoặc bảo đảm giao hàng **nếu đã thỏa thuận** | Chiến lược retry nội bộ không lộ ra giao diện |

Đặc biệt, đừng ngầm coi mọi hệ thống thông điệp đều bảo đảm đúng một lần giao hàng hoặc giữ nguyên thứ tự toàn cục. Nếu consumer dựa vào các tính chất này, phải có thỏa thuận giao tiếp và kiểm thử thích hợp ở cấp hệ thống; một payload mẫu không thể chứng minh tất cả các đặc tính vận hành đó.

## 7. Hợp đồng hành vi đi vào kiểm thử và CI như thế nào?

Spring Cloud Contract làm cho đặc tả hành vi trở thành tài sản có thể thực thi.

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Sinh test phía producer"]
    B --> D["Sinh mapping/stub"]
    C --> E["Build và kiểm thử producer trong CI"]
    D --> E
    E -->|"Test đạt"| F["Đóng gói, phát hành stub"]
    F --> G["Consumer dùng Stub Runner"]
    G --> H["Kiểm thử tích hợp consumer"]
~~~

**Phía producer:** Verifier sinh kiểm thử theo các request và response trong hợp đồng. Test gọi vào ứng dụng hoặc thiết lập test phù hợp, nên môi trường test phải chuẩn bị dữ liệu như ORD-1001 và ORD-9999. Nếu producer đổi từ 404 sang 200 cho trường hợp không tìm thấy đơn, kiểm thử sinh từ hợp đồng tương ứng có thể thất bại ngay trong CI của producer.

**Phía consumer:** stub phát hành từ hợp đồng cho phép consumer kiểm thử cách gọi HTTP và xử lý phản hồi mà không cần chạy một producer thật ở cùng môi trường. **Stub Runner** hỗ trợ tìm và chạy các stub đã phát hành để tích hợp vào test của consumer. Consumer có thể kiểm tra luồng hiển thị, xử lý lỗi hoặc gọi các API tiếp theo dựa trên phản hồi mẫu.

**Trong CI:** một chu trình điển hình gồm kiểm tra các hợp đồng ở phía producer, chạy test sinh ra, đóng gói/phát hành artifact stub sau khi kiểm thử đạt, rồi dùng artifact tương ứng trong kiểm thử consumer. Việc artifact được xuất bản vào kho nào, phiên bản được chọn ra sao và thời điểm chạy test phụ thuộc pipeline của dự án.

Điểm cần nhớ: **stub chỉ cho biết consumer hành xử ra sao với phản hồi đã đặc tả; test phía producer mới kiểm chứng việc producer thực sự đáp ứng đặc tả đó**. Hai phía bổ trợ nhau. Chỉ chạy consumer với stub mà không kiểm tra producer có thể tạo ra cảm giác tương thích sai nếu stub đã cũ hoặc không phản ánh hành vi thực tế.

## 8. Nhận diện thay đổi API không tương thích

Giả sử consumer đã dùng hợp đồng nhận trạng thái thanh toán:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Những thay đổi sau cần được đánh giá trước khi phát hành:

| Thay đổi từ producer | Tác động có thể có | Hành động nên làm |
| --- | --- | --- |
| Đổi status thành paymentState | Consumer đọc status bị lỗi | Giữ trường cũ một thời gian, hoặc thống nhất nâng phiên bản hợp đồng và chuyển consumer |
| Chuyển status từ chuỗi sang số | Parser/logic nghiệp vụ có thể sai | Tránh đổi kiểu tại giao diện hiện có |
| Đổi 404 thành 204 | Logic phân nhánh lỗi có thể đổi | Thảo luận với consumer, cập nhật contract và test hai phía |
| Thêm trường description tùy chọn | Thường không ảnh hưởng consumer chấp nhận trường lạ | Xác minh cơ chế deserialize; ghi rõ trường tùy chọn |
| Bổ sung giá trị trạng thái REFUNDED | Consumer dùng enum đóng có thể không xử lý | Kiểm tra khả năng xử lý giá trị mới và cam kết về tập giá trị |
| Đổi chiến lược lưu trữ nhưng giữ nguyên HTTP response | Consumer không bị ảnh hưởng | Không cần sửa hợp đồng chỉ vì refactor nội bộ |

Không có quy tắc tuyệt đối rằng mọi trường bổ sung đều luôn tương thích: một consumer cấu hình parser nghiêm ngặt vẫn có thể từ chối trường không biết. Ngược lại, hai hệ thống có thể chủ động thiết kế quy tắc cho phép mở rộng. Vì vậy, hãy đánh giá dựa trên **hành vi consumer đang phụ thuộc và thỏa thuận tương thích**, không chỉ dựa trên việc JSON có còn hợp lệ hay không.

Khi cần thay đổi lớn, cân nhắc duy trì hành vi cũ trong giai đoạn chuyển tiếp, xuất bản hợp đồng và stub tương ứng cho từng phiên bản, chạy test consumer với phiên bản phù hợp, sau đó loại bỏ hành vi cũ theo kế hoạch đã thống nhất.

## 9. Những lỗi thiết kế thường gặp

### Lỗi 1: Chỉ kiểm tra status 200

Một contract chỉ cam kết status 200 vẫn có thể qua test dù producer trả body trống hoặc thiếu trường status mà consumer đang cần. Hãy khai báo **tối thiểu các trường và ý nghĩa cần thiết**.

### Lỗi 2: Chép toàn bộ entity nội bộ vào hợp đồng

Nếu body chứa mọi trường của OrderEntity, thay đổi schema hoặc thêm cột có thể kéo theo hợp đồng mới không cần thiết. Hãy thiết kế DTO công khai theo nhu cầu của consumer và chỉ cam kết các trường có ý nghĩa bên ngoài.

### Lỗi 3: Dùng dữ liệu ngẫu nhiên nhưng kiểm tra chính xác

Khóa cứng timestamp hoặc UUID được sinh mới sau mỗi lần chạy khiến test thất bại không ổn định. Dùng fixture cố định khi đó là kịch bản xác định; dùng matcher thích hợp khi yêu cầu là định dạng hoặc quan hệ giữa dữ liệu.

### Lỗi 4: Dùng stub để thay thế toàn bộ kiểm thử

Stub giúp kiểm thử sự tích hợp của consumer với một mô phỏng có kiểm soát. Nó không thay thế kiểm thử logic nội bộ, quyền truy cập, độ tin cậy mạng, hiệu năng hoặc kiểm thử hệ thống đầu cuối. Producer vẫn phải chạy test xác minh hợp đồng.

### Lỗi 5: Không thống nhất ý nghĩa nghiệp vụ

Hai phía có thể cùng dùng trường status là chuỗi mà vẫn hiểu khác nhau về PAID hoặc CANCELLED. Hợp đồng cần kèm mô tả ý nghĩa hoặc quy tắc nghiệp vụ khi kiểu dữ liệu không đủ diễn đạt cam kết.

## 10. Bài tập thực hành

**Bài tập A — Chọn ranh giới hợp đồng.** Một producer trả đơn hàng bằng API GET. Bạn được đề xuất thêm các trường sau vào JSON: id, status, databaseShard, cacheHit, totalAmount, currency. Consumer chỉ cần hiển thị trạng thái và tổng tiền theo đơn vị tiền tệ. Hãy chọn trường nào cần cam kết, nêu lý do loại bỏ những trường còn lại và xem xét có cần trường id hay không.

**Bài tập B — Thêm trường hợp lỗi.** Viết một hợp đồng YAML riêng cho GET /api/orders/ORD-9999 với HTTP 404 và body chứa code: ORDER_NOT_FOUND. Giải thích vì sao chỉ thay body của hợp đồng thành công là chưa đủ nếu không đổi trạng thái HTTP và dữ liệu đầu vào.

**Bài tập C — Đánh giá thay đổi.** Producer đổi cách lưu từ SQL sang Redis, đổi tên JSON status thành state và bổ sung header X-Request-Id. Hãy chỉ ra thay đổi nào cần thương lượng với consumer. Sau đó mô tả test producer và test consumer với Stub Runner sẽ phát hiện sai khác ra sao.

**Gợi ý tự kiểm tra:** Với bài A, status, totalAmount và currency phục vụ nhu cầu công khai; id cần được cam kết nếu consumer dùng nó để liên kết đúng đơn hàng. databaseShard và cacheHit là chi tiết nội bộ trong bối cảnh này. Với bài C, đổi tên status có nguy cơ phá vỡ hợp đồng; đổi kho lưu trữ thường không. Header mới chỉ trở thành phần cam kết nếu consumer được yêu cầu sử dụng hoặc nó ảnh hưởng tương thích.

## Checklist trước khi chốt một hợp đồng

- [ ] Nêu rõ consumer và tình huống sử dụng cụ thể.
- [ ] Chỉ cam kết request, response, sự kiện và tác động có thể quan sát từ giao diện tích hợp.
- [ ] Kiểm tra đủ status, kiểu dữ liệu, tên trường và mã lỗi mà consumer cần.
- [ ] Tránh ràng buộc class, repository, database, cache và thông tin debug nội bộ.
- [ ] Phân biệt dữ liệu fixture cố định với trường cần matcher/định dạng.
- [ ] Có trường hợp lỗi quan trọng thay vì chỉ kiểm tra đường đi thành công.
- [ ] Chuẩn bị fixture để test được sinh phía producer chạy ổn định.
- [ ] Phát hành stub từ hợp đồng đã được producer xác minh và chạy kiểm thử consumer bằng Stub Runner.
- [ ] Đánh giá khả năng tương thích trước khi thay đổi giao diện công khai.

**Ghi nhớ:** Spring Cloud Contract phát huy tác dụng khi hợp đồng mô tả **điều consumer có quyền kỳ vọng**, đủ cụ thể để kiểm thử tự động phát hiện sai khác nhưng đủ độc lập để producer cải tiến triển khai bên trong. Đây là nền tảng cho kiểm thử hợp đồng producer–consumer có ý nghĩa và quy trình CI phát hiện thay đổi API không tương thích.
