# Producer, consumer và ranh giới giao tiếp giữa hai bên

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **producer** (bên cung cấp giao diện) và **consumer** (bên sử dụng giao diện) trong một hệ thống nhiều dịch vụ.
- Xác định **ranh giới hợp đồng**: hành vi nào cần thống nhất và kiểm thử, chi tiết nào thuộc nội bộ từng dịch vụ.
- Đọc một hợp đồng HTTP viết bằng **Spring Cloud Contract Groovy DSL** và giải thích cách nó tạo test phía producer, tạo stub cho consumer.
- Nhận diện thay đổi tương thích và thay đổi có nguy cơ làm hỏng consumer; biết cách phối hợp nhóm và đặt kiểm tra hợp đồng vào CI.

## 1. Producer và consumer là ai?

Trong kiến trúc dịch vụ, hai bên trao đổi với nhau qua một giao diện được công bố, chẳng hạn API HTTP hoặc một thông điệp gửi qua broker.

- **Producer (provider)** là bên **cung cấp** giao diện và hiện thực hành vi phía sau giao diện đó. Với HTTP, producer nhận request và trả response; với messaging, producer có thể là dịch vụ phát thông điệp.
- **Consumer** là bên **phụ thuộc vào** giao diện ấy để hoàn thành công việc. Với HTTP, consumer gửi request và xử lý response; với messaging, consumer có thể là dịch vụ đăng ký nhận thông điệp.
- **Contract (hợp đồng)** là mô tả có thể kiểm chứng về cách hai bên tương tác: đầu vào hợp lệ, đầu ra được mong đợi và các quy tắc mà consumer có thể dựa vào.

Ví dụ, hệ thống thương mại điện tử có:

| Thành phần | Vai trò trong tương tác | Trách nhiệm |
|---|---|---|
| `Checkout Service` | Consumer | Hỏi số lượng hàng còn để hiển thị trước khi người mua xác nhận đơn |
| `Inventory Service` | Producer | Công bố endpoint kiểm tra tồn kho và trả dữ liệu đúng hợp đồng |
| Hợp đồng tồn kho | Thỏa thuận tại ranh giới | Quy định đường dẫn, phương thức, kiểu dữ liệu và phản hồi cho các trường hợp đã thống nhất |

Vai trò **phụ thuộc vào từng tương tác**, không cố định cho cả ứng dụng. `Inventory Service` có thể là producer khi trả lời `Checkout Service`, nhưng lại là consumer khi gọi dịch vụ kho vận. Trong một hệ thống dùng sự kiện, cùng một dịch vụ cũng có thể vừa nhận vừa phát các loại thông điệp khác nhau.

Spring Cloud Contract giúp biến thỏa thuận này thành **đặc tả thực thi được**: từ một hợp đồng, công cụ có thể sinh kiểm thử cho producer và sinh stub để consumer thử tích hợp mà không phải khởi chạy producer thật.

## 2. Ranh giới giao tiếp nằm ở đâu?

Hãy tưởng tượng hai nhóm phát triển độc lập. Nhóm Checkout không cần biết Inventory lưu dữ liệu bằng PostgreSQL, Redis hay gọi thêm dịch vụ khác. Nhóm Checkout chỉ cần biết: *nếu gửi yêu cầu hợp lệ theo giao diện đã công bố, nó nhận được điều gì và phải xử lý thế nào?*

Đó chính là ranh giới giao tiếp. Hợp đồng mô tả **hành vi quan sát được từ bên ngoài**, không mô tả cách producer tạo ra hành vi ấy.

| Thuộc ranh giới có thể đưa vào hợp đồng | Thuộc triển khai nội bộ, không nên ràng buộc |
|---|---|
| HTTP method, path, query parameter cần thiết | Tên lớp controller/service, cấu trúc package |
| Header liên quan đến giao tiếp, định dạng nội dung, xác thực theo thỏa thuận | Hàm nội bộ gọi theo thứ tự nào |
| Mã trạng thái HTTP và cấu trúc JSON/XML phản hồi | Bảng cơ sở dữ liệu, tên cột, thuật toán truy vấn |
| Trường bắt buộc, kiểu dữ liệu, giá trị hoặc quy tắc khớp | Framework hay thư viện nội bộ của producer |
| Trường hợp thành công, lỗi có ý nghĩa với consumer | Chi tiết log, cache và cách triển khai retry nội bộ |
| Với messaging: đích gửi, metadata/header, cấu trúc payload của sự kiện | Cách producer lưu sự kiện trong outbox |

Một hợp đồng tốt cần **đủ cụ thể** để phát hiện thay đổi phá vỡ tích hợp, nhưng không trói producer vào những chi tiết consumer không cần. Chẳng hạn, Checkout có thể cần `available` là kiểu boolean, còn `quantity` là số nguyên không âm; không nên bắt toàn bộ các giá trị động luôn bằng đúng dữ liệu ví dụ trong môi trường thật. Groovy/YAML DSL của Spring Cloud Contract hỗ trợ các bộ so khớp (matcher) để diễn đạt những quy tắc linh hoạt hơn so với khớp nguyên văn.

> **Phân biệt hợp đồng và mọi cam kết vận hành:** contract test kiểm chứng các ví dụ hành vi đã định nghĩa. Nó không tự chứng minh hệ thống đạt mọi yêu cầu về tải, độ trễ, bảo mật, khả năng phục hồi hoặc mọi trường hợp nghiệp vụ. Những khía cạnh đó cần các phép kiểm tra và giám sát bổ sung.

## 3. Ví dụ: Checkout gọi API tồn kho

Giả sử producer công bố API:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Host: inventory.example.internal
Accept: application/json
~~~

Với sản phẩm tồn tại, producer trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 12
}
~~~

Trong ví dụ, consumer dựa vào các quy tắc sau:

1. Gọi `GET /api/inventory/{sku}` để lấy thông tin tồn kho cho mã hàng.
2. Nếu nhận `200 OK`, đọc `sku` (chuỗi), `available` (boolean) và `quantity` (số).
3. Nếu mã hàng không tồn tại, cần có một trường hợp lỗi được hai bên thống nhất riêng, chẳng hạn `404 Not Found` kèm mã lỗi máy có thể xử lý.
4. Không suy diễn rằng phản hồi `available: true` là thao tác giữ hàng. Số lượng có thể thay đổi sau lần kiểm tra; việc đặt giữ hàng cần nghiệp vụ hoặc endpoint khác.

Điểm thứ tư rất quan trọng: **hợp đồng dữ liệu** và **ngữ nghĩa nghiệp vụ** phải cùng nhất quán. Nếu producer chỉ cam kết trả về ảnh chụp tồn kho tại thời điểm truy vấn, consumer không thể coi đó là lời hứa sẽ có hàng khi tạo đơn.

### Một hợp đồng bằng Groovy DSL

Trong dự án producer có tích hợp Spring Cloud Contract, có thể lưu một file hợp đồng, chẳng hạn `src/test/resources/contracts/inventory/shouldReturnAvailableStock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Tra ve ton kho cho ma hang da biet'

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
            quantity: 12
        )
    }
}
~~~

Đọc hợp đồng từ trên xuống:

- `request` quy định producer phải nhận một request `GET` theo URL và header đã nêu.
- `response` quy định phản hồi mong đợi: status `200`, content type JSON và các trường trong body.
- `description` giúp nhóm hiểu mục đích của ví dụ; nó không thay thế các quy tắc trong `request` và `response`.

Đây là **một trường hợp hợp đồng cụ thể**, không phải tài liệu mô tả tất cả mã sản phẩm. Với URL hoặc giá trị động, có thể áp dụng matcher của Spring Cloud Contract để xác định loại giá trị và quy tắc khớp thích hợp. Trường hợp mã hàng không tồn tại phải có hợp đồng khác nếu consumer cần dựa vào phản hồi lỗi đó.

Spring Cloud Contract còn hỗ trợ YAML DSL để diễn tả các tình huống tương đương. Hai định dạng là **cách viết đặc tả**, không thay đổi vai trò producer/consumer hay nguyên tắc ranh giới.

## 4. Ai kiểm chứng điều gì?

<details>
<summary>Luồng kiểm chứng hợp đồng cho HTTP</summary>

~~~mermaid
flowchart LR
    A["Contract Groovy/YAML<br/>được hai bên thống nhất"] --> B["Sinh test phía producer"]
    A --> C["Sinh stub HTTP"]
    B --> D["Chạy với ứng dụng producer thật"]
    C --> E["Consumer chạy test với Stub Runner"]
    D --> F{"Producer đáp ứng?"}
    E --> G{"Consumer hiểu đúng?"}
    F -->|Có| H["Build producer có thể phát hành stub"]
    F -->|Không| I["Sửa producer hoặc thương lượng thay đổi"]
    G -->|Không| J["Sửa consumer hoặc làm rõ hợp đồng"]
~~~

</details>

**Phía producer:** công cụ sinh kiểm thử từ DSL. Khi được cấu hình đúng, các test gọi vào ứng dụng thực (hoặc tầng HTTP được dựng cho kiểm thử) và xác nhận đầu ra của producer có phù hợp với ví dụ trong hợp đồng hay không. Producer cần cấu hình môi trường test, lớp cơ sở cho test được sinh và dữ liệu kiểm thử cần thiết; chỉ đặt file Groovy vào dự án chưa đủ để tự bảo đảm mọi test chạy được.

**Phía consumer:** stub được sinh từ hợp đồng đóng vai trò một producer giả lập tại ranh giới HTTP. Consumer gửi request tới stub qua **Spring Cloud Contract Stub Runner** (hoặc WireMock được cấu hình tương ứng), rồi kiểm tra logic gọi API, giải mã response và xử lý kết quả của chính consumer.

| Câu hỏi kiểm chứng | Producer contract test | Consumer test dùng stub |
|---|---|---|
| Ứng dụng producer thật có trả đúng hành vi đã cam kết? | **Có**, trong các trường hợp hợp đồng bao phủ | Không, vì đang gọi producer giả |
| Consumer có gửi đúng request và đọc đúng response theo hợp đồng? | Không kiểm tra đầy đủ mã consumer | **Có**, nếu test consumer được viết cho các luồng ấy |
| Hệ thống chạy đầu-cuối, kết nối mạng và hạ tầng thật có hoạt động? | Chưa đủ | Chưa đủ |

Ví dụ, việc consumer chạy thành công với stub **không chứng minh** producer đã triển khai đúng. Hai kết quả cần đi cùng nhau: producer phải vượt qua các test được sinh, consumer phải kiểm tra logic tích hợp với stub tương ứng.

### Chu trình phối hợp thường gặp

1. **Thống nhất nhu cầu:** consumer đề xuất hành vi cụ thể mà ứng dụng của mình phụ thuộc, ví dụ trường `available` và ý nghĩa của nó.
2. **Định nghĩa hợp đồng:** producer và consumer xem xét các trường hợp HTTP/thông điệp cần hỗ trợ, rồi lưu hợp đồng ở nơi có quản lý phiên bản (thường là repository của producer hoặc repository hợp đồng chung).
3. **Kiểm chứng producer:** pipeline tạo và chạy contract test với code producer. Nếu test lỗi, thay đổi chưa phù hợp với hợp đồng hiện tại.
4. **Phát hành stub:** khi kiểm tra thành công, build có thể đóng gói artifact stub (với Maven thường dùng classifier `stubs`) và đưa vào kho artifact.
5. **Kiểm chứng consumer:** consumer lấy **đúng phiên bản stub** và dùng Stub Runner chạy các test tương tác của mình.
6. **Tích hợp CI:** các pipeline tự động phản hồi sớm khi một bên thay đổi interface, trước lúc phát hành hoặc tích hợp lên môi trường chung.

Tên plugin, vị trí file contract, cách tạo base test, repository artifact và cơ chế chọn phiên bản stub phụ thuộc cấu hình Spring Cloud Contract trong dự án. Đừng mặc định rằng hai pipeline đang sử dụng cùng một bản hợp đồng chỉ vì chúng đều báo xanh: **phiên bản hợp đồng/stub là một phần của việc điều phối**.

## 5. Khi nào thay đổi có thể làm hỏng consumer?

Tương thích cần được xét **từ những gì consumer thực sự phụ thuộc**. Ví dụ:

| Thay đổi phía producer | Nguy cơ | Lý do |
|---|---|---|
| Đổi `quantity` từ số sang chuỗi | Cao | Consumer giải mã sang số có thể lỗi |
| Đổi `GET /api/inventory/{sku}` thành path khác mà không duy trì path cũ | Cao | Request cũ không còn được hỗ trợ |
| Đổi phản hồi thành công từ `200` sang `204` và bỏ body | Cao | Consumer đang chờ body để xử lý |
| Đổi nghĩa `available` nhưng giữ nguyên tên, kiểu dữ liệu | Cao, khó phát hiện nếu hợp đồng thiếu quy tắc nghiệp vụ | JSON vẫn hợp lệ nhưng quyết định đặt hàng có thể sai |
| Thêm một trường tùy chọn vào JSON response | Thường ít rủi ro **nếu** consumer bỏ qua trường lạ | Consumer dùng bộ giải mã nghiêm ngặt vẫn có thể bị ảnh hưởng |
| Thay PostgreSQL bằng một cơ sở dữ liệu khác, giữ nguyên hành vi ngoài | Thường không ảnh hưởng hợp đồng | Chi tiết lưu trữ nằm ngoài ranh giới |

Không có quy tắc chung rằng "thêm field luôn tương thích". Khả năng tương thích còn phụ thuộc cách consumer parse dữ liệu, trường có bắt buộc không, hợp đồng công bố gì và hai bên quản lý phiên bản ra sao.

Khi cần thay đổi lớn, có thể duy trì giao diện cũ trong một giai đoạn, giới thiệu phiên bản mới, cho consumer chuyển dần, rồi loại bỏ giao diện cũ theo lịch đã thống nhất. Contract test và stub test giúp phát hiện sớm một số thay đổi phá vỡ kỳ vọng, nhưng quyết định tiến hóa API vẫn cần phối hợp giữa các nhóm.

## 6. Với messaging, ai là producer và consumer?

Với một sự kiện `StockChanged`:

- `Inventory Service` là **message producer** vì phát sự kiện.
- `Checkout Service` (nếu đăng ký nhận) là **message consumer** vì xử lý sự kiện.
- Ranh giới có thể bao gồm **đích gửi**, **header**, **payload**, loại sự kiện, định danh và các trường cần thiết để xử lý.

Ví dụ về payload mong đợi:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 8
}
~~~

Một thay đổi như đổi `quantity` từ number thành string vẫn có thể làm consumer hỏng, dù không có HTTP request/response. Spring Cloud Contract hỗ trợ mô tả các tương tác thông điệp trong DSL, sinh kiểm thử cho hành vi phát/nhận phù hợp với cấu hình messaging của dự án.

Riêng các bảo đảm về **thứ tự sự kiện, giao ít nhất một lần, trùng lặp, thời điểm phát lại** phụ thuộc hệ thống broker và thiết kế nghiệp vụ. Nếu consumer cần chúng, cần quy định và kiểm thử bổ sung. Một ví dụ payload đơn lẻ không chứng minh được toàn bộ các bảo đảm đó.

## 7. Những nhầm lẫn thường gặp

**Nhầm 1: Consumer phải chờ producer chạy thật mới kiểm thử được.** Stub từ Spring Cloud Contract cho phép consumer thử logic gọi API độc lập với môi trường producer. Tuy vậy, vẫn cần producer contract test và một mức kiểm thử tích hợp phù hợp.

**Nhầm 2: Contract test là kiểm thử toàn bộ nghiệp vụ.** Hợp đồng chỉ kiểm chứng những tình huống đã mô tả. Nếu chỉ có trường hợp thành công, các tình huống 400, 401, 404, timeout hoặc phản hồi lỗi khác mà consumer dựa vào sẽ chưa được bảo vệ bằng hợp đồng.

**Nhầm 3: Càng khóa chặt mọi giá trị JSON càng tốt.** Dữ liệu thay đổi như ID, timestamp, số lượng hàng cần matcher phù hợp khi không có yêu cầu phải cố định nguyên văn. Kiểm tra quá cứng có thể gây lỗi giả; kiểm tra quá lỏng có thể bỏ lọt thay đổi phá vỡ interface.

**Nhầm 4: Consumer dùng field nào cũng mặc nhiên thành hợp đồng.** Consumer không nên đọc các trường thử nghiệm hoặc dựa vào thứ tự key trong JSON nếu producer chưa cam kết. Hai nhóm cần ghi rõ các phụ thuộc có ý nghĩa trước khi xem chúng là nghĩa vụ của producer.

**Nhầm 5: Test xanh có nghĩa bản stub đang dùng đúng với bản sẽ phát hành.** Nếu consumer sử dụng stub cũ, kiểm thử vẫn có thể xanh trong khi producer đang chuẩn bị thay đổi mới. CI cần chính sách chọn, cập nhật và xác minh phiên bản stub.

## 8. Bài tập tư duy

Bạn đang xây `Checkout Service` sử dụng `Inventory Service`. Nhóm producer đề xuất trả về:

~~~json
{
  "sku": "SKU-101",
  "available": "yes",
  "quantity": 12,
  "warehouse": "WH-01"
}
~~~

Trong hợp đồng trước đây, `available` là boolean và không có `warehouse`.

1. **Thay đổi nào cần cảnh báo trước?** Giá trị `available` chuyển thành chuỗi: consumer đang xử lý boolean có thể hỏng. Việc thêm `warehouse` còn tùy vào chính sách parse trường lạ.
2. **Kiểm thử nào phát hiện lỗi?** Producer contract test cho trường `available` kiểu boolean sẽ không khớp với response mới. Consumer test với stub mới giúp nhận ra logic consumer không giải mã hoặc xử lý được giá trị dạng chuỗi.
3. **Cần trao đổi gì giữa hai nhóm?** Producer có bắt buộc đổi kiểu không? Có thể giữ boolean và thêm field riêng để biểu diễn trạng thái chi tiết không? Nếu buộc phải đổi, cách chuyển phiên bản và thời điểm dừng hỗ trợ cũ là gì?

### Tự kiểm tra

- Bạn có thể giải thích vì sao một dịch vụ có thể đồng thời là producer và consumer không?
- Bạn có phân biệt được hành vi có thể quan sát qua API với chi tiết nội bộ của producer không?
- Bạn có thể nêu lý do cần **cả** producer contract test **và** consumer test với stub không?
- Bạn có chỉ ra được ít nhất một trường hợp lỗi cần bổ sung ngoài phản hồi thành công không?

## Ghi nhớ

**Producer cam kết hành vi tại giao diện, consumer dựa vào hành vi ấy.** Spring Cloud Contract ghi lại cam kết bằng Groovy hoặc YAML DSL, rồi hỗ trợ kiểm chứng theo hai phía: sinh test đối với triển khai producer và sinh stub để consumer thử tích hợp. Giá trị của hợp đồng nằm ở việc làm rõ **ranh giới phụ thuộc** và phát hiện sớm khi hai phía không còn hiểu giống nhau về giao diện.
