# Những lỗi có thể phát hiện và những bảo đảm không thể suy ra

## 1. Hiểu đúng phạm vi của kiểm thử hợp đồng

Trong một hệ thống gồm nhiều dịch vụ, **producer** (bên cung cấp) triển khai API hoặc phát thông điệp; **consumer** (bên sử dụng) gửi yêu cầu, nhận phản hồi hoặc tiêu thụ thông điệp đó. Hai phía thường được phát triển và phát hành độc lập. Một thay đổi tưởng như nhỏ ở producer, chẳng hạn đổi tên trường JSON, có thể làm consumer ngừng hoạt động dù các bài kiểm thử đơn vị của mỗi bên vẫn xanh.

**Spring Cloud Contract** giúp mô tả một số tương tác được hai phía kỳ vọng bằng hợp đồng (contract) viết với **Groovy DSL hoặc YAML DSL**. Từ hợp đồng, công cụ có thể sinh kiểm thử để chạy với producer và sinh **stub** mô phỏng phản hồi hoặc thông điệp cho consumer. **Stub Runner** giúp consumer dùng các stub đó trong kiểm thử tích hợp; CI có thể chặn thay đổi khi các kiểm thử tương ứng thất bại.

Giới hạn cần nhớ ngay từ đầu:

> **Một lần chạy contract test thành công chỉ chứng minh rằng triển khai được kiểm tra đáp ứng những tương tác và điều kiện đã được biểu diễn, thực thi và xác nhận trong bộ kiểm thử tại thời điểm chạy.** Nó không tự chứng minh toàn bộ API đúng, mọi consumer tương thích, hoặc bản đã triển khai ngoài môi trường chạy test hoạt động tốt.

Hợp đồng là một **tập các kỳ vọng có chủ đích**, không phải mô tả đầy đủ mọi trạng thái có thể xảy ra của hệ thống.

## 2. Ví dụ: một thay đổi mà contract test có thể bắt được

Giả sử dịch vụ đặt hàng cung cấp endpoint lấy thông tin đơn hàng. Consumer cần biết mã đơn, trạng thái và mã HTTP để hiển thị kết quả. Nhóm thống nhất một hợp đồng Spring Cloud Contract bằng YAML:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
request:
  method: GET
  url: /api/orders/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Hợp đồng trên mô tả **một tình huống cụ thể**: khi gửi `GET /api/orders/42`, producer cần trả HTTP 200, nội dung JSON và các giá trị đã nêu. Trong quá trình build, Spring Cloud Contract có thể sinh kiểm thử phía producer từ hợp đồng này. Khi kiểm thử thực sự khởi động thành phần ứng dụng cần thiết, gửi request và so khớp response, các thay đổi sau có thể làm bài kiểm thử thất bại:

- Endpoint đổi thành `/api/v2/orders/42` và đường dẫn cũ không còn trả kết quả mong đợi.
- Producer trả `404` hoặc `500` thay vì `200` trong tình huống đã định nghĩa.
- Producer đổi trường `status` thành `state`, bỏ trường `id`, hoặc trả giá trị `CANCELLED` thay cho `PAID`.
- Producer trả Content-Type khác giá trị đã ràng buộc trong hợp đồng.

Khả năng phát hiện phụ thuộc vào **các assertion được sinh ra, cấu hình kiểm thử và cách ứng dụng được dựng lên**. Nếu một trường, header hay trường hợp đầu vào không được đưa vào hợp đồng hoặc không được kiểm tra, không thể mặc định rằng sai lệch của nó sẽ bị phát hiện.

Chẳng hạn, hợp đồng ở trên **không** nói gì về `GET /api/orders/43`, tình huống thiếu token, hay đơn hàng chưa thanh toán. Việc endpoint 42 vượt qua bài kiểm thử không cho biết các trường hợp đó đúng hay sai.

## 3. Những nhóm lỗi có thể phát hiện

| Nhóm lỗi | Ví dụ | Điều kiện để phát hiện |
|---|---|---|
| Sai tuyến HTTP hoặc phương thức | Consumer dự kiến `GET /api/orders/42`, producer bỏ đường dẫn cũ | Hợp đồng khai báo đúng request; kiểm thử producer gửi request tương ứng |
| Sai mã trạng thái | Đáng lẽ `200` nhưng trả `404` | Hợp đồng nêu status mong đợi và test kiểm tra |
| Sai header hoặc kiểu nội dung | Thiếu `Content-Type: application/json` | Header nằm trong phần kỳ vọng được xác nhận |
| Sai cấu trúc hoặc dữ liệu phản hồi | Xóa `status`, đổi tên `id`, trả giá trị không phù hợp | Body và matcher đủ cụ thể để ràng buộc thuộc tính đó |
| Sai cách producer chấp nhận request | Đổi query parameter, header bắt buộc hoặc cấu trúc request body | Có hợp đồng cho đầu vào chịu tác động và test gọi được tình huống đó |
| Sai định dạng thông điệp | Đổi trường payload, header hay loại thông điệp mà consumer cần | Có messaging contract và kiểm thử producer/consumer được cấu hình, kích hoạt đúng |
| Consumer sử dụng sai giao diện đã thỏa thuận | Consumer không parse được payload stub, gọi sai phương thức hoặc path | Consumer chạy kiểm thử với đúng stub và có assertion cho hành vi cần bảo vệ |

Khi contract do consumer đóng góp hoặc được hai bên thỏa thuận, các thay đổi đã liệt kê có thể được phát hiện **trước khi triển khai**, nếu kiểm thử được gắn vào pipeline và lỗi làm build thất bại. Đây là lợi ích cốt lõi: rút ngắn vòng phản hồi khi interface thay đổi.

Tuy nhiên, kết quả cụ thể không phải lúc nào cũng là “một thay đổi sẽ bị chặn”. Ví dụ, bổ sung trường JSON tùy chọn có thể tương thích với client bỏ qua trường lạ, nhưng lại gây lỗi ở consumer dùng bộ giải mã nghiêm ngặt. Phải nhìn vào kỳ vọng của client và kiểm thử thực tế; không thể suy ra tính tương thích chỉ từ việc thêm hay bớt một trường.

## 4. Hai phía kiểm thử chứng minh hai điều khác nhau

~~~mermaid
flowchart TB
    C["Contract được thống nhất"] --> P["Sinh test phía producer"]
    C --> S["Sinh stub"]
    P --> PT["Chạy test với producer"]
    S --> SR["Stub Runner"]
    SR --> CT["Chạy test với consumer"]
    PT --> PC["Bắt sai lệch giữa producer và contract"]
    CT --> CC["Bắt lỗi consumer khi dùng giao diện được mô phỏng"]
~~~

**Kiểm thử phía producer** kiểm tra một triển khai cụ thể có đáp ứng yêu cầu được khai báo hay không. Nếu producer đổi response trái hợp đồng và bài test liên quan được chạy, test có thể báo lỗi. Bài test chỉ bảo vệ những mẫu request, matcher và tình huống mà nó thực sự bao phủ.

**Kiểm thử phía consumer với Stub Runner** chạy consumer đối diện một dịch vụ giả lập được sinh từ contract. Cách này hữu ích để kiểm tra logic gọi API, xử lý status và giải mã dữ liệu mà không cần dựng producer thật. Nhưng **stub là hành vi mô phỏng từ bản hợp đồng**, không phải ảnh chụp tự động của producer đang chạy. Consumer chạy xanh với stub không đủ để kết luận rằng producer hiện tại hoặc phiên bản đang phục vụ production trả đúng như stub.

Ví dụ, producer vô tình đổi `status` thành `state`. Consumer có thể **vẫn chạy xanh** khi dùng stub cũ chứa `status`. Bài test producer có hợp đồng liên quan sẽ giúp phát hiện sai lệch, nhưng chỉ nếu được chạy thành công trên đúng mã nguồn producer và lỗi không bị bỏ qua. Hai nhánh kiểm thử bổ sung cho nhau, không thay thế lẫn nhau.

Với **message contract**, nguyên tắc cũng tương tự: test có thể kiểm tra payload, header và điều kiện phát hoặc nhận thông điệp đã mô tả. Điều đó chưa bảo đảm toàn bộ đường truyền qua broker, cấu hình topic/queue, quyền truy cập, thứ tự giao hàng hoặc cơ chế retry trong môi trường thật, trừ khi các yếu tố ấy cũng được kiểm thử riêng.

## 5. Những bảo đảm không thể tự suy ra

| Kết luận dễ nhầm | Vì sao contract test chưa đủ? | Cách kiểm chứng bổ sung |
|---|---|---|
| “Mọi endpoint đều tương thích” | Chỉ các request và tình huống có contract/test mới được kiểm tra | Kiểm kê API, lập ma trận contract theo consumer và ca sử dụng |
| “Mọi input và nhánh lỗi đều đúng” | Một hợp đồng cho đơn hàng hợp lệ không bao phủ input sai, null, phân trang hay giới hạn | Unit test, integration test và contract cho các tình huống lỗi quan trọng |
| “Logic nghiệp vụ đúng” | Response có đúng định dạng vẫn có thể tính sai thuế, tiền, quyền lợi hoặc quy tắc trạng thái | Kiểm thử nghiệp vụ và quy tắc miền |
| “Dữ liệu đã lưu đúng” | Response phù hợp có thể được trả trước khi transaction thất bại | Integration test với cơ sở dữ liệu, xác nhận side effect và transaction |
| “Hệ thống đủ nhanh và ổn định” | Hợp đồng không đo tải, độ trễ, tranh chấp tài nguyên, retry hay timeout ở quy mô thực | Performance, load và resilience test |
| “API an toàn” | Có JSON đúng không chứng minh xác thực, phân quyền, chống rò rỉ dữ liệu và bảo vệ bí mật | Security test, authorization test và rà soát cấu hình |
| “Hệ thống chạy tốt sau deploy” | Môi trường test có thể khác DNS, network, gateway, broker, secret và cấu hình production | Smoke test, end-to-end test và giám sát sau phát hành |
| “Tất cả consumer đang dùng đều được bảo vệ” | Có thể tồn tại client ngoài danh sách, phiên bản cũ hoặc client chưa có contract | Quản lý danh mục consumer, version và chính sách ngừng hỗ trợ |
| “Phiên bản đã deploy khớp bản đã test” | CI có thể kiểm tra commit A trong khi môi trường chạy artifact B hoặc stub phiên bản cũ | Gắn phiên bản hợp đồng/stub với build, kiểm tra provenance và release |
| “Thay đổi có cùng kiểu dữ liệu thì tương thích” | `amount: 100` có thể đổi nghĩa từ đơn vị đồng sang xu; hình dạng JSON vẫn giống nhau | Thỏa thuận ngữ nghĩa, kiểm thử nghiệp vụ và rà soát thay đổi |

Điểm mấu chốt là **tương thích cấu trúc không đồng nghĩa tương thích ngữ nghĩa**. Ví dụ, contract chỉ ràng buộc `total` là số; producer trả giá trị bằng đơn vị khác nhưng vẫn là số hợp lệ. Test có thể không biết ý nghĩa bị thay đổi. Các quy tắc về đơn vị, múi giờ, thứ tự, cách xử lý null, tính duy nhất, giới hạn giá trị và ý nghĩa từng enum cần được ghi rõ, rồi kiểm thử ở lớp phù hợp.

**Bảo đảm về phiên bản cũng có hướng**: client cũ gọi producer mới là một câu hỏi khác với client mới gọi producer cũ. Một cặp producer/consumer chạy xanh chỉ đại diện cho phiên bản và tình huống đã được thử. Khi nhiều phiên bản cùng tồn tại, cần kiểm tra các tổ hợp thực tế được hỗ trợ.

## 6. Bốn tình huống để phân biệt tín hiệu thật và cảm giác an toàn

### Tình huống A — Producer bỏ trường mà consumer dùng

Consumer đọc `response.status` để hiển thị tình trạng đơn. Contract có trường `status`; producer đổi nó thành `state`.

- **Producer contract test:** có thể báo lỗi vì response khác hợp đồng.
- **Consumer test với stub cũ:** có thể vẫn xanh vì stub vẫn trả `status`.
- **Kết luận:** cần chạy và bắt buộc pass test producer ở commit phát hành; chỉ dựa vào test consumer là chưa đủ.

### Tình huống B — Producer thêm trường tùy chọn

Producer thêm `promotionCode` vào JSON response nhưng giữ nguyên những trường cũ.

- **Producer contract test:** thường không cần thất bại nếu hợp đồng và matcher cho phép trường bổ sung.
- **Consumer test:** client đọc linh hoạt có thể hoạt động bình thường; client cấm trường lạ có thể lỗi.
- **Kết luận:** phải kiểm tra cách consumer xử lý dữ liệu mở rộng. “Có thêm trường” không tự động đồng nghĩa an toàn hay phá vỡ tương thích.

### Tình huống C — API đúng định dạng nhưng sai ý nghĩa

Producer vẫn trả `{ "id": 42, "status": "PAID" }` dù giao dịch thực tế chưa được thanh toán.

- **Contract test:** có thể xanh vì output đúng với tình huống fixture được dựng hoặc vì hợp đồng không chứng minh trạng thái cơ sở dữ liệu.
- **Kiểm thử cần thêm:** kiểm tra quy trình thanh toán, chuyển trạng thái, transaction và đối soát với dữ liệu thực tế.
- **Kết luận:** contract là bằng chứng về giao tiếp, không tự chứng minh tính đúng đắn nghiệp vụ.

### Tình huống D — Stub và artifact không cùng phiên bản

Consumer kiểm thử bằng stub `1.4.0`; producer triển khai bản `1.5.0` có thay đổi ngoài kỳ vọng.

- **Consumer test:** vẫn có thể xanh với stub `1.4.0`.
- **Rủi ro:** kết quả test không phản ánh bản producer đang chạy.
- **Kết luận:** cần quản lý phiên bản stub/contract, chạy producer verification cho artifact dự định phát hành và kiểm tra các phiên bản consumer cần hỗ trợ.

## 7. Làm cho contract test trở thành một cổng kiểm soát hữu ích trong CI

Một luồng làm việc thực tế với Spring Cloud Contract có thể gồm các bước:

1. **Thống nhất kỳ vọng có ý nghĩa với consumer.** Mô tả request, response hoặc message cho các luồng quan trọng; chọn giá trị cố định và matcher phù hợp. Với trường tùy biến như ID, thời gian, mã giao dịch, đặt ràng buộc đủ mạnh để bảo vệ client nhưng tránh gắn chặt vào dữ liệu ngẫu nhiên.
2. **Sinh và chạy kiểm thử phía producer.** Cấu hình build để kiểm thử được tạo từ Groovy/YAML DSL thực sự chạy trên triển khai producer. Lỗi của bài kiểm thử phải làm job CI thất bại. Khi thay đổi contract có chủ đích, cập nhật contract và mã triển khai trong cùng quy trình review.
3. **Sinh và phát hành stub có phiên bản.** Xuất bản artifact stub từ bộ contract đã xác nhận. Lưu dấu vết phiên bản để consumer biết nó đang kiểm thử với giao diện nào.
4. **Chạy kiểm thử consumer bằng Stub Runner.** Consumer gọi stub trong các tình huống sử dụng thực; assertion cần xác nhận cách client xử lý dữ liệu, status, lỗi và các trường quan trọng. Kiểm tra đúng phiên bản stub tương ứng với chính sách hỗ trợ.
5. **Chặn phát hành khi không tương thích đã được kiểm chứng.** Kết hợp kết quả kiểm thử producer, consumer cần thiết và bước đối chiếu artifact. Với hệ thống có nhiều phiên bản, xác định rõ ma trận tương thích được bảo vệ.
6. **Giữ các lớp kiểm thử khác.** Bổ sung unit test cho nghiệp vụ, integration test cho database/broker, end-to-end test cho chuỗi dịch vụ, cùng kiểm thử bảo mật, tải và quan sát vận hành.

**Ví dụ về cổng CI:** một pull request đổi tên `status` thành `state`. Nếu contract vẫn yêu cầu `status`, producer test thất bại và CI chặn merge hoặc release. Nếu đây là thay đổi có chủ ý, nhóm cần thống nhất chiến lược chuyển đổi: duy trì trường cũ trong giai đoạn tương thích, bổ sung trường mới, cập nhật các consumer liên quan, rồi chỉ loại bỏ trường cũ sau khi đã kiểm chứng không còn client cần dùng.

Một pipeline chỉ **sinh** test hoặc artifact stub nhưng không **chạy** kiểm thử, không bắt trạng thái lỗi hoặc không ràng buộc release với build đã xác minh sẽ tạo cảm giác được bảo vệ mà chưa có bằng chứng tương ứng.

## 8. Checklist diễn giải một kết quả “PASS”

Trước khi tuyên bố một thay đổi API an toàn, hãy trả lời các câu hỏi sau:

- Hợp đồng này bảo vệ **consumer nào, tương tác nào và phiên bản nào**?
- Các request, response, thông điệp, header, trường dữ liệu, giá trị và matcher quan trọng đã được mô tả chưa?
- Bộ test sinh từ contract đã được **chạy trên đúng producer/artifact** chuẩn bị phát hành chưa? Kết quả có thực sự làm CI thất bại khi sai lệch không?
- Consumer đã kiểm thử cách gọi API và giải mã dữ liệu bằng **stub đúng phiên bản** chưa?
- Có tình huống âm (4xx/5xx), dữ liệu thiếu, dữ liệu biên, timeout hoặc tương tác bất đồng bộ nào còn chưa được kiểm tra không?
- Những rủi ro ngoài hình dạng giao diện — nghiệp vụ, dữ liệu, bảo mật, tải, broker, network, triển khai — được kiểm chứng ở đâu?

Khi các câu hỏi chưa có bằng chứng, nên báo cáo chính xác **phần đã được kiểm tra** thay vì nói chung rằng “API tương thích 100%”.

## 9. Ghi nhớ

Spring Cloud Contract có giá trị nhất khi hợp đồng thể hiện đúng điều các consumer cần, kiểm thử producer được thực thi trong CI, và consumer kiểm thử hành vi thực tế với stub có phiên bản. Cơ chế này có thể phát hiện sớm nhiều lỗi về **giao diện HTTP và thông điệp**, nhất là những thay đổi làm producer lệch khỏi hợp đồng đã thống nhất.

Kết quả xanh là **bằng chứng hữu hạn** cho các tương tác đã được xác nhận. Nó không tự mở rộng thành bảo đảm về toàn bộ hành vi nghiệp vụ, hiệu năng, an ninh, môi trường triển khai, mọi client hay mọi phiên bản đang hoạt động. Xác định rõ ranh giới ấy giúp nhóm dùng contract test đúng vai trò trong chiến lược kiểm thử nhiều lớp.
