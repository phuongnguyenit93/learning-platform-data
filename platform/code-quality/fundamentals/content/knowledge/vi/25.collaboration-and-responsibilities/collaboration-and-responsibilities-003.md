# Chuyển yêu cầu chất lượng thành thỏa thuận có thể thực hiện

Một yêu cầu sản phẩm ghi: “Trang thanh toán phải nhanh, an toàn, dễ bảo trì và hoạt động ổn định.” Cả nhóm đều đồng ý với câu này, nhưng mỗi người có thể hiểu khác nhau. Product nghĩ trang phải tải trong hai giây; người dùng hiểu thao tác thanh toán phải hoàn tất trong hai giây; nhóm backend nghĩ chỉ API cần phản hồi nhanh; vận hành lại quan tâm tỷ lệ lỗi và khả năng phục hồi. Khi có sự cố, mọi người có thể tranh luận rằng phần việc của mình đã hoàn thành vì chưa từng có một tiêu chí chung.

Trong chương **Cộng tác và trách nhiệm** của module **CODE_QUALITY_FUNDAMENTALS**, bài học này tập trung vào cách chuyển mong muốn về chất lượng thành **thỏa thuận có thể thực hiện, kiểm chứng và duy trì**. Một thỏa thuận tốt giúp người yêu cầu, người thiết kế, người phát triển, người kiểm thử và người vận hành cùng hiểu điều gì phải đúng, ai chịu trách nhiệm, bằng chứng nào được chấp nhận và cách xử lý khi có đánh đổi.

Mục tiêu là giúp mã nguồn và hệ thống **đáng tin cậy, dễ hiểu và dễ thay đổi**. Điều đó đòi hỏi sự phối hợp từ lúc làm rõ yêu cầu đến lúc triển khai và theo dõi, chứ không chỉ thêm một quality gate ở cuối quy trình.

## 1. Tại sao yêu cầu chất lượng cần trở thành thỏa thuận?

Các thuộc tính chất lượng thường được diễn đạt bằng những từ đúng nhưng quá rộng:

- Nhanh.
- An toàn.
- Ổn định.
- Dễ bảo trì.
- Dễ mở rộng.
- Có khả năng phục hồi.
- Dễ kiểm thử.
- Tương thích ngược.

Những từ này hữu ích để bắt đầu cuộc trao đổi, nhưng **chưa đủ để quyết định một thay đổi đã đạt hay chưa**.

| Cách diễn đạt ban đầu | Những cách hiểu khác nhau có thể xuất hiện | Điều cần thống nhất |
| --- | --- | --- |
| API phải nhanh | Thời gian trung bình, p95, p99 hay thời gian toàn hành trình? | Điểm đo, workload, percentile và ngưỡng |
| Dịch vụ phải ổn định | Không crash, ít lỗi, hay tự phục hồi sau dependency failure? | Loại lỗi, tỷ lệ thành công, thời gian phục hồi |
| Dữ liệu phải an toàn | Mã hóa, phân quyền, audit hay chống lộ qua log? | Tài sản, mối đe dọa, kiểm soát và bằng chứng |
| Mã phải dễ bảo trì | Ít dòng, ít cảnh báo hay dễ thay đổi quy tắc? | Khả năng thay đổi cụ thể và cách đánh giá |
| Hệ thống phải mở rộng | Thêm người dùng, dữ liệu, instance hay module? | Quy mô, tốc độ tăng và giới hạn tài nguyên |
| Có kiểm thử đầy đủ | Bao nhiêu coverage, ca biên hay các luồng tích hợp? | Rủi ro cần bảo vệ và bằng chứng phù hợp |

Nếu không làm rõ, nhóm có thể hoàn thành đúng phần việc cục bộ nhưng vẫn không đáp ứng mục tiêu tổng thể. Thỏa thuận chất lượng tạo ra **một cách hiểu chung có thể hành động**.

### 1.1. Thỏa thuận không chỉ là một con số

Một tiêu chí kiểu “p95 dưới 300 ms” vẫn có thể vô nghĩa nếu không biết:

- Đo từ client, gateway hay bên trong service?
- Tính thời gian queue hay chỉ thời gian xử lý?
- Dữ liệu có bao nhiêu bản ghi?
- Tải đồng thời và tỷ lệ cache hit là bao nhiêu?
- Đo trong môi trường nào?
- Tính cả timeout và lỗi hay chỉ các request thành công?
- Ai duy trì phép đo sau khi phát hành?

Một thỏa thuận có thể thực hiện cần tối thiểu **mục tiêu, ngữ cảnh, điều kiện đo, ngưỡng chấp nhận, bằng chứng, người chịu trách nhiệm và cách xử lý ngoại lệ**.

### 1.2. Phân biệt yêu cầu chức năng và yêu cầu chất lượng

| Loại yêu cầu | Mô tả | Ví dụ |
| --- | --- | --- |
| **Chức năng** | Hệ thống thực hiện hành động hoặc quy tắc nghiệp vụ nào | Thành viên đủ điều kiện được miễn phí vận chuyển |
| **Chất lượng** | Hành động đó cần được thực hiện với thuộc tính nào | API báo giá đạt p95 dưới 300 ms ở tải đã xác định |
| **Ràng buộc** | Giới hạn kỹ thuật, pháp lý hoặc tổ chức phải tuân theo | Dữ liệu thanh toán không được ghi vào log ứng dụng |
| **Tiêu chí chấp nhận** | Bằng chứng cụ thể để quyết định yêu cầu đã đạt | Test ở ngưỡng 500.000 VND xác nhận đúng chính sách |
| **Điều kiện vận hành** | Cách theo dõi và duy trì sau phát hành | Cảnh báo khi tỷ lệ lỗi vượt SLO trong cửa sổ quy định |

Các loại này có thể liên quan chặt chẽ. Ví dụ “không ghi dữ liệu thẻ vào log” vừa là yêu cầu bảo mật, vừa là tiêu chí chấp nhận cho thay đổi logging. Không cần ép mỗi câu vào đúng một nhãn; cần bảo đảm mọi bên hiểu và có thể xác minh.

## 2. Chuyển từ tính từ mơ hồ sang kịch bản chất lượng

Một cách hiệu quả để làm rõ yêu cầu là mô tả **kịch bản chất lượng** (*quality attribute scenario*). Thay vì viết “hệ thống phải nhanh”, hãy xác định ai tạo ra kích thích, trong hoàn cảnh nào, thành phần nào chịu tác động, phản hồi mong đợi là gì và đo bằng cách nào.

Một kịch bản có thể gồm sáu phần:

1. **Nguồn kích thích:** ai hoặc điều gì tạo ra sự kiện?
2. **Kích thích:** request, lỗi, tải tăng, thay đổi dữ liệu hoặc hành động nào xảy ra?
3. **Môi trường:** hệ thống đang ở điều kiện bình thường, tải cao, dependency lỗi hay đang triển khai?
4. **Thành phần chịu tác động:** API, module, database, worker hay toàn hệ thống?
5. **Phản hồi mong đợi:** hệ thống phải làm gì?
6. **Thước đo phản hồi:** số liệu nào chứng minh đã đáp ứng?

Ví dụ:

| Thành phần | Kịch bản chưa rõ | Kịch bản có thể kiểm chứng |
| --- | --- | --- |
| Nguồn | Người mua | Client đã xác thực |
| Kích thích | Mở trang thanh toán | Gửi yêu cầu tạo báo giá với giỏ hàng hợp lệ |
| Môi trường | Bình thường | Tải 200 request/giây, dữ liệu kiểm thử có 100.000 sản phẩm |
| Thành phần | Hệ thống | API báo giá và các dependency đồng bộ của nó |
| Phản hồi | Phải nhanh | Trả kết quả hoặc lỗi đã định nghĩa, không chờ vô hạn |
| Thước đo | Nhanh | p95 dưới 300 ms trong bài tải đã thống nhất, tỷ lệ timeout dưới ngưỡng đã đặt |

Các con số trong ví dụ là **giả định để minh họa**, không phải chuẩn chung. Nhóm cần chọn ngưỡng từ nhu cầu người dùng, dữ liệu nền, chi phí và năng lực vận hành.

### 2.1. Ví dụ kịch bản hiệu năng

```text
Thuộc tính: Hiệu năng
Nguồn: Client đã xác thực
Kích thích: Gửi request tạo báo giá
Môi trường: 200 request/giây, dữ liệu đại diện 100.000 sản phẩm
Thành phần: Quote API và dependency đồng bộ
Phản hồi: Trả báo giá hoặc lỗi đã định nghĩa
Thước đo:
  - p95 latency < 300 ms
  - tỷ lệ timeout < 0,1%
  - đo trên cửa sổ 15 phút ổn định
  - ghi nhận offered load và completed throughput
```

Kịch bản này có thể dẫn tới một bài load test, dashboard và SLO. Nó cũng tạo câu hỏi cho kiến trúc: cache, truy vấn, giới hạn kết nối và khả năng mở rộng cần được xem xét ở đâu?

### 2.2. Ví dụ kịch bản độ tin cậy

```text
Thuộc tính: Độ tin cậy
Nguồn: Database chính
Kích thích: Kết nối bị ngắt trong lúc ghi đơn
Môi trường: Request đang trong transaction
Thành phần: Order service và repository
Phản hồi:
  - Không trả thành công khi chưa xác nhận commit
  - Không để lại trạng thái đơn nửa vời
  - Có thể tra cứu kết quả nếu phản hồi bị mất sau commit
Thước đo:
  - Integration test xác minh rollback/commit
  - Retry cùng request ID không tạo đơn thứ hai
  - Số đơn ở trạng thái không hợp lệ bằng 0 trong kiểm tra đối soát
```

Kịch bản này liên kết chất lượng với bất biến dữ liệu, transaction và idempotency. Chỉ đo tỷ lệ uptime không đủ để xác nhận hành vi đúng khi commit hoặc phản hồi bị gián đoạn.

### 2.3. Ví dụ kịch bản khả năng bảo trì

“Dễ bảo trì” khó đo bằng một con số duy nhất. Có thể viết kịch bản gắn với **một loại thay đổi thường xảy ra**:

```text
Thuộc tính: Khả năng thay đổi
Nguồn: Nhóm sản phẩm
Kích thích: Thay ngưỡng miễn phí vận chuyển
Môi trường: Chính sách áp dụng cho một phiên bản thị trường
Thành phần: Shipping policy và các use case sử dụng policy
Phản hồi:
  - Quy tắc được cập nhật tại nơi sở hữu chính sách
  - Báo giá và chốt đơn tiếp tục dùng cùng hợp đồng
  - Không cần sửa các module không liên quan
Thước đo/bằng chứng:
  - Có một nguồn quyết định chính sách
  - Unit test biên và integration test các điểm gọi đạt
  - Diff không chứa bản sao điều kiện ở các use case
  - Review xác nhận trách nhiệm và chiều phụ thuộc rõ
```

Đây là cách đo **khả năng thực hiện một thay đổi cụ thể**, không phải tuyên bố mọi thay đổi trong tương lai đều dễ. Có thể theo dõi thêm lead time, số module phải sửa và tỷ lệ hồi quy, nhưng cần diễn giải cùng độ phức tạp của từng yêu cầu.

## 3. Chọn tiêu chí có thể đo mà không tạo mục tiêu sai

Một tiêu chí tốt cần đủ cụ thể để kiểm tra nhưng không khuyến khích nhóm tối ưu con số bằng cách làm giảm chất lượng thật.

### 3.1. Chọn thước đo phù hợp với thuộc tính

| Thuộc tính | Thước đo/bằng chứng có thể dùng | Điều cần tránh |
| --- | --- | --- |
| Hiệu năng | p95/p99, throughput, timeout, CPU/RAM dưới workload xác định | Chỉ dùng thời gian trung bình |
| Độ tin cậy | Tỷ lệ request thành công, lỗi theo mức độ, MTTR, số lần vi phạm bất biến | Đếm lỗi tuyệt đối mà bỏ qua lượng sử dụng |
| Bảo mật | Test phân quyền âm, kết quả scan đã hoàn tất, thời gian xử lý finding | Coi scan sạch là chứng minh không có lỗ hổng |
| Khả năng bảo trì | Số nơi sở hữu cùng quy tắc, mức lan truyền thay đổi, testability, review evidence | Chỉ tối ưu số dòng hoặc complexity |
| Tính tương thích | Contract test, schema diff, kiểm tra client phiên bản cũ | Chỉ kiểm thử server mới |
| Khả năng phục hồi | Thời gian phục hồi, tỷ lệ retry thành công, trạng thái sau lỗi | Chỉ test đường thành công |
| Khả năng quan sát | Tỷ lệ request có trace/log liên kết, độ đầy đủ metric, thời gian phát hiện | Thu thập quá nhiều dữ liệu nhạy cảm |

### 3.2. Định nghĩa tử số, mẫu số và cửa sổ đo

Với một tỷ lệ, cần viết rõ:

```text
failureRate = failedRequests / eligibleRequests
```

Nhưng định nghĩa thực tế còn phải chốt:

- Một request retry ba lần tính là một request nghiệp vụ hay ba lần thử?
- Request bị client hủy có nằm trong mẫu số không?
- Lỗi do client gửi dữ liệu sai có tính vào lỗi dịch vụ không?
- Cửa sổ đo là 5 phút, 1 giờ hay 30 ngày?
- Dữ liệu thiếu hoặc telemetry mất thì báo 0 hay không có số liệu?

Tương tự, “thời gian phục hồi dưới 30 phút” cần xác định bắt đầu từ lúc sự cố xảy ra, lúc được phát hiện hay lúc có người tiếp nhận. Nếu không, hai nhóm có thể báo cùng một chỉ số nhưng đang đo hai việc khác nhau.

### 3.3. Dùng percentile đúng cách

Với hiệu năng, trung bình có thể che nhóm request chậm. p95 nghĩa là khoảng 95% quan sát nằm ở hoặc dưới giá trị phân vị thứ 95 theo cách tính đã chọn; nó không có nghĩa mọi request đều nhanh hơn p95.

Thỏa thuận cần nêu:

- Điểm bắt đầu/kết thúc đo.
- Loại request và phân nhóm quan trọng.
- Workload, kích thước dữ liệu, cache state và môi trường.
- Khoảng thời gian đủ dài và cách lấy mẫu.
- Cách xử lý lỗi, timeout và request bị hủy.
- Nguồn histogram hoặc dữ liệu thô dùng để tính percentile.

Không nên lấy trung bình p95 theo từng phút để gọi là p95 của cả giờ. Nếu cần phân vị gộp, phải tổng hợp phân bố/histogram tương thích hoặc dữ liệu mẫu phù hợp.

### 3.4. Đặt guardrail để tránh tối ưu một phía

Nếu chỉ yêu cầu p95 dưới 300 ms, nhóm có thể từ chối request chậm để làm đẹp số liệu. Vì vậy cần xem đồng thời:

- p95/p99 latency.
- Tỷ lệ lỗi và timeout.
- Offered load và completed throughput.
- Tài nguyên tiêu thụ.
- Tỷ lệ request bị từ chối.
- Mức độ chính xác của kết quả.

Một tiêu chí có thể đạt về tốc độ nhưng thất bại về tính đúng đắn. Guardrail giúp thỏa thuận phản ánh **kết quả người dùng nhận được**, không chỉ con số thuận tiện cho dashboard.

## 4. Một thỏa thuận chất lượng cần có những phần nào?

Có thể dùng mẫu sau cho một yêu cầu hoặc một thay đổi có rủi ro đáng kể.

| Phần | Nội dung cần ghi |
| --- | --- |
| **Mục tiêu** | Vấn đề người dùng hoặc rủi ro cần giải quyết |
| **Phạm vi** | Dịch vụ, module, API, loại người dùng và môi trường |
| **Kịch bản** | Nguồn, kích thích, môi trường, thành phần, phản hồi |
| **Tiêu chí chấp nhận** | Điều kiện cụ thể có thể kiểm tra |
| **Thước đo** | Đơn vị, tử số/mẫu số, percentile, cửa sổ, workload |
| **Bằng chứng** | Unit, integration, contract, load, security test, report hoặc quan sát |
| **Trách nhiệm** | Ai quyết định, ai triển khai, ai xác minh, ai vận hành |
| **Đánh đổi** | Chi phí, độ trễ, bảo mật, khả năng tương thích, giới hạn được chấp nhận |
| **Ngoại lệ** | Điều kiện miễn, người phê duyệt, phạm vi và thời hạn |
| **Vận hành** | Dashboard, cảnh báo, runbook và chủ sở hữu sau phát hành |
| **Thay đổi thỏa thuận** | Cách đề xuất, đánh giá và phê duyệt khi yêu cầu đổi |

Mẫu này không cần biến thành biểu mẫu dài cho mọi thay đổi. Với một refactor nhỏ trong hàm thuần, có thể chỉ cần ghi hợp đồng giữ nguyên và test tương ứng. Với thay đổi thanh toán, dữ liệu cá nhân hoặc giao dịch phân tán, cần làm rõ nhiều phần hơn.

## 5. Ví dụ xuyên suốt: thỏa thuận chất lượng cho checkout

Giả sử nhóm xây dựng chức năng checkout cho một nền tảng bán hàng. Các bên liên quan đã thống nhất những giả định sau để làm ví dụ:

- API tạo đơn chỉ chấp nhận yêu cầu hợp lệ từ người dùng đã xác thực.
- Giá sản phẩm và ưu đãi được xác minh ở server.
- Một request nghiệp vụ có mã idempotency ổn định.
- Không tạo hai đơn cho cùng một request logic.
- Đơn chỉ ở trạng thái PAID khi có xác nhận thanh toán phù hợp từ cổng thanh toán.
- Dữ liệu thanh toán nhạy cảm không được ghi vào log.
- API báo giá có mục tiêu hiệu năng riêng ở tải đã định nghĩa.

### 5.1. Viết các tiêu chí chấp nhận

| ID | Tiêu chí | Bằng chứng | Người xác nhận chính |
| --- | --- | --- | --- |
| AC-01 | Giá và ưu đãi được tính từ dữ liệu server đã xác minh | Unit test policy và integration test nguồn giá | Product + Engineering |
| AC-02 | Request không hợp lệ không tạo đơn hoặc phát sự kiện thành công | API test và kiểm tra trạng thái DB/outbox | QA + Engineering |
| AC-03 | Retry cùng idempotency key không tạo đơn/thanh toán trùng | Integration test với DB và payment adapter test | Engineering |
| AC-04 | Timeout sau khi gửi lệnh thanh toán được biểu diễn là kết quả chưa rõ khi chưa đối soát | Failure injection và contract test trạng thái | Product + Engineering + Operations |
| AC-05 | Không ghi dữ liệu thẻ hoặc secret vào log | Test logging, review cấu hình và scan phù hợp | Security + Engineering |
| AC-06 | API báo giá đạt p95 dưới 300 ms ở 200 request/giây với workload đại diện | Load test có report và môi trường được ghi | Performance/Operations |
| AC-07 | Dashboard hiển thị lỗi thanh toán, timeout và trạng thái đối soát | Kiểm tra metric/trace và runbook | Operations |

Các tiêu chí này có thể được tách thành ticket hoặc test. Điều quan trọng là mỗi tiêu chí có **một nguồn kỳ vọng và một loại bằng chứng**.

### 5.2. Chuyển một tiêu chí thành kịch bản Given/When/Then

Ví dụ AC-03:

```text
Given:
  Một request tạo đơn hợp lệ với idempotency key K
  đã được xử lý và có orderId O.

When:
  Client gửi lại cùng request nghiệp vụ với key K.

Then:
  Hệ thống trả lại kết quả gắn với O theo hợp đồng.
  Không tạo order mới.
  Không gửi lệnh charge thứ hai.
  Không phát thêm sự kiện nghiệp vụ trùng trái hợp đồng.
```

Kịch bản này cụ thể hơn câu “hỗ trợ idempotency”. Nó cũng gợi ra câu hỏi cần chốt: cùng key nhưng payload khác thì sao? Key có phạm vi theo user, endpoint hay tenant? Thời gian lưu key là bao lâu? Kết quả cũ có được trả lại sau khi chính sách thay đổi không?

### 5.3. Xác định phần chưa thể kết luận bằng một test

Một unit test mock payment gateway có thể xác nhận application service gửi cùng idempotency key. Nó không chứng minh payment provider thực sự xử lý key đúng, DB có ràng buộc duy nhất hoặc hai request đồng thời không tạo hai bản ghi.

Do đó có thể cần:

- Unit test cho policy và trạng thái.
- Integration test với database thật hoặc môi trường tương thích.
- Contract test với payment adapter/provider sandbox.
- Test đồng thời và retry.
- Failure injection cho timeout sau khi gửi lệnh.
- Monitoring sau phát hành.

Thỏa thuận nên nói rõ **bằng chứng nào là bắt buộc trước merge** và **bằng chứng nào được thu thập trong môi trường staging/production**.

## 6. Phân định trách nhiệm: ai quyết định, ai thực hiện, ai xác minh?

Một yêu cầu chất lượng thường liên quan nhiều vai trò. Nếu không phân định trách nhiệm, mọi người có thể nghĩ người khác đang chốt ngưỡng hoặc chịu trách nhiệm vận hành.

### 6.1. Các vai trò thường gặp

| Vai trò | Trách nhiệm chính trong thỏa thuận chất lượng |
| --- | --- |
| **Product owner / người sở hữu nghiệp vụ** | Xác nhận nhu cầu, ưu tiên, hành vi mong đợi và đánh đổi chấp nhận được |
| **Architecture / technical lead** | Đề xuất giải pháp, ranh giới, rủi ro kỹ thuật và tiêu chí kiến trúc |
| **Developer** | Làm rõ tính khả thi, triển khai, viết test và cung cấp bằng chứng |
| **QA / test engineer** | Chuyển tiêu chí thành kịch bản, kiểm tra oracle và phạm vi kiểm thử |
| **Security** | Đánh giá mối đe dọa, kiểm soát và bằng chứng bảo mật |
| **Operations / SRE** | Xác nhận khả năng vận hành, metric, alert, SLO và runbook |
| **Data owner / DBA** | Xác nhận quyền sở hữu dữ liệu, schema, migration, retention và tính nhất quán |
| **Support / customer-facing team** | Phản ánh tác động người dùng và quy trình xử lý khi có sự cố |

Một người có thể đảm nhận nhiều vai trò trong nhóm nhỏ. Điều cần tránh là **không có ai chịu trách nhiệm cuối cùng cho quyết định**.

### 6.2. Dùng RACI để làm rõ trách nhiệm

RACI thường được hiểu là:

- **R — Responsible:** trực tiếp thực hiện công việc.
- **A — Accountable:** chịu trách nhiệm cuối cùng và đưa ra quyết định.
- **C — Consulted:** được tham vấn hai chiều.
- **I — Informed:** được thông báo.

Ví dụ cho checkout:

| Công việc | Product | Tech lead | Developer | QA | Security | Operations |
| --- | --- | --- | --- | --- | --- | --- |
| Chốt hành vi nghiệp vụ và ưu tiên | A | C | C | C | I | I |
| Chọn ranh giới và giải pháp kỹ thuật | C | A | R | C | C | C |
| Triển khai và unit test | I | A | R | C | C | I |
| Xây acceptance/integration tests | C | C | R | A | C | I |
| Chốt tiêu chí bảo mật | C | C | R | C | A | C |
| Chốt dashboard, alert, runbook | I | C | R | C | C | A |
| Quyết định chấp nhận rủi ro còn lại | A hoặc người được ủy quyền theo policy | C | I | C | C | C |

Bảng chỉ là **ví dụ phân công**. Trong thực tế, mỗi đầu việc nên có một người hoặc vai trò **A** rõ ràng; không để mọi bên cùng nghĩ bên kia sẽ quyết định. Quyền phê duyệt rủi ro bảo mật hoặc pháp lý có thể thuộc vai trò chuyên trách theo chính sách tổ chức, không nhất thiết là Product.

### 6.3. Trách nhiệm không đồng nghĩa đẩy lỗi

Khi một tiêu chí không đạt, câu hỏi hữu ích là:

- Tiêu chí đã được thống nhất chưa?
- Ai sở hữu việc xác nhận kỳ vọng?
- Ai sở hữu triển khai?
- Bằng chứng nào đã được cung cấp?
- Ranh giới nào chưa có kiểm thử?
- Cần thay đổi mã, đặc tả, công cụ hay quy trình?

Không nên dùng RACI để tìm người bị quy trách nhiệm cá nhân. Mục tiêu là làm rõ **quyết định và công việc có chủ sở hữu**, để vấn đề được giải quyết.

## 7. Thương lượng đánh đổi một cách minh bạch

Các thuộc tính chất lượng có thể xung đột:

- Cache giúp giảm độ trễ nhưng có thể làm dữ liệu cũ.
- Mã hóa và kiểm tra quyền tăng bảo vệ nhưng có thể tăng chi phí xử lý.
- Tính nhất quán mạnh có thể làm tăng độ trễ hoặc giảm khả năng phục vụ khi dependency lỗi.
- Nhiều bước xác minh tăng độ tin cậy nhưng kéo dài thời gian phản hồi.
- Trừu tượng hóa hỗ trợ thay đổi nhưng tăng độ gián tiếp và chi phí hiểu mã.
- Chạy mọi test trong mỗi PR tăng bằng chứng nhưng có thể làm vòng phản hồi quá chậm.

Không thể giải quyết bằng câu “chất lượng luôn phải cao nhất”. Cần **nêu rõ lựa chọn, rủi ro và giới hạn**.

### 7.1. Ví dụ bảng đánh đổi

| Lựa chọn | Lợi ích | Chi phí/rủi ro | Điều kiện chấp nhận |
| --- | --- | --- | --- |
| Cache báo giá 30 giây | Giảm tải và latency | Giá/ưu đãi có thể thay đổi trong cửa sổ cache | Có quy tắc hết hạn và xác nhận lại khi chốt |
| Gọi payment đồng bộ | Luồng đơn giản khi thành công nhanh | Timeout làm kết quả chưa rõ | Có idempotency và đối soát |
| Chạy integration suite đầy đủ mỗi PR | Phản hồi sớm lỗi ranh giới | CI chậm và tốn tài nguyên | Chia suite, chạy song song và giữ test ổn định |
| Chấp nhận API version cũ thêm 6 tháng | Hỗ trợ client đang dùng | Duy trì hai hợp đồng | Có ngày kết thúc và kế hoạch migration |
| Dùng một policy chung | Giảm sai khác giữa các use case | Có thể gom nhầm hai chính sách khác nghĩa | Cùng owner, ngữ nghĩa và vòng đời thay đổi |

### 7.2. Ghi nhận quyết định thay vì chỉ ghi kết quả

Một quyết định kỹ thuật có thể ghi:

```text
Quyết định: Cache báo giá tối đa 30 giây.

Lý do:
  Giảm tải truy vấn giá trong giờ cao điểm.

Đánh đổi:
  Giá hiển thị có thể cũ trong tối đa 30 giây.

Bảo vệ:
  Khi chốt đơn, server xác minh lại giá và voucher.
  Nếu giá thay đổi, trả trạng thái yêu cầu xác nhận lại.

Chủ sở hữu:
  Tech lead của checkout.

Xem xét lại:
  Khi thay đổi chính sách giá hoặc khi metric stale-price vượt ngưỡng.
```

Đây là mẫu nội dung cho một decision record. Nếu quyết định ảnh hưởng hợp đồng công khai hoặc dữ liệu người dùng, cần có người sở hữu nghiệp vụ và vai trò liên quan tham gia phê duyệt.

## 8. Đưa thỏa thuận vào quy trình phát triển

Một thỏa thuận chỉ hữu ích khi xuất hiện ở những nơi nhóm làm việc.

### 8.1. Trước khi bắt đầu: Definition of Ready

Một thay đổi có thể sẵn sàng triển khai khi:

- Mục tiêu và người dùng bị ảnh hưởng đã rõ.
- Các thuật ngữ nghiệp vụ, đơn vị và trường hợp biên đã được xác nhận.
- Thuộc tính chất lượng liên quan đã được nêu.
- Tiêu chí chấp nhận có thể kiểm tra hoặc có kế hoạch tạo bằng chứng.
- Phạm vi và dependency được biết ở mức đủ để ước lượng.
- Người quyết định khi có xung đột hoặc ngoại lệ đã được xác định.

Không phải mọi ticket cần tài liệu dài. Với thay đổi nhỏ, Definition of Ready có thể chỉ là vài câu rõ ràng. Nhưng nếu một yêu cầu chứa “nhanh, an toàn, ổn định” mà không ai giải thích được, nhóm chưa có đủ cơ sở để cam kết.

### 8.2. Trong khi triển khai: Definition of Done

Một thay đổi có thể được coi là hoàn thành khi các điều kiện phù hợp đã đạt:

- Hành vi chức năng đáp ứng acceptance criteria.
- Test ở các lớp cần thiết đã chạy và có report.
- Các quality gate bắt buộc đạt hoặc waiver hợp lệ.
- Hợp đồng API/schema và tài liệu liên quan được cập nhật.
- Log, metric, trace và alert cần thiết đã được xem xét.
- Rủi ro và giới hạn chưa xử lý được ghi rõ.
- Có chủ sở hữu vận hành và cách rollback/khôi phục khi cần.

**Definition of Done không nên là danh sách bất biến cho mọi thay đổi.** Một chỉnh sửa tài liệu không cần load test; thay đổi transaction thanh toán có thể cần integration, concurrency và failure test.

### 8.3. Đưa tiêu chí vào công cụ

| Nơi lưu | Nội dung phù hợp |
| --- | --- |
| Ticket/issue | Mục tiêu, phạm vi, acceptance criteria, người quyết định |
| API specification | Schema, mã lỗi, tương thích và ý nghĩa field |
| Test suite | Các kịch bản có thể chạy lặp lại |
| CI quality gate | Điều kiện tự động chặn hoặc cảnh báo |
| ADR/decision record | Đánh đổi và lý do chọn phương án |
| Runbook | Cách vận hành, đối soát và phục hồi |
| Dashboard/SLO | Đo lường kết quả sau phát hành |
| PR description | Thay đổi, bằng chứng, giới hạn và liên kết tới quyết định |

Không nên sao chép một tiêu chí thành nhiều bản tài liệu độc lập rồi để chúng lệch nhau. Chọn **nguồn chuẩn** cho mỗi loại thông tin và liên kết tới nó.

## 9. Khi yêu cầu chưa thể đo ngay

Có những yêu cầu ban đầu chưa có baseline hoặc chưa rõ khả năng kỹ thuật. Không nên bịa một ngưỡng chỉ để ticket trông có vẻ cụ thể.

Một cách làm có trách nhiệm:

1. Ghi điều đã biết và phần chưa biết.
2. Xác định quyết định nào bị chặn bởi thiếu thông tin.
3. Tạo spike hoặc thử nghiệm đo lường có phạm vi và thời hạn.
4. Thu baseline trong môi trường đại diện.
5. Đề xuất ngưỡng cùng chi phí và đánh đổi.
6. Để người có thẩm quyền chấp thuận tiêu chí.
7. Chuyển kết quả thành test, gate hoặc SLO nếu phù hợp.

Ví dụ: chưa biết p95 hiện tại của API báo giá. Thay vì cam kết 100 ms tùy ý, nhóm có thể đo baseline theo workload thực, phân tích dependency và đưa ra mục tiêu theo nhu cầu người dùng.

### 9.1. Phân biệt mục tiêu, SLI và SLO

- **SLI (Service Level Indicator):** phép đo cụ thể, ví dụ tỷ lệ request hợp lệ hoàn tất thành công.
- **SLO (Service Level Objective):** mục tiêu cho SLI trong một cửa sổ, ví dụ tỷ lệ thành công ít nhất 99,9% trong 30 ngày.
- **SLA (Service Level Agreement):** cam kết dịch vụ có thể có hệ quả hợp đồng hoặc bồi hoàn; không nên gọi mọi SLO nội bộ là SLA.

Ví dụ:

```text
SLI:
  Successful eligible quote requests / all eligible quote requests

SLO:
  At least 99.9% over a rolling 30-day window

Measurement:
  Exclude only explicitly defined client-invalid requests.
  Include server errors and timeouts.
  Publish missing-telemetry rate separately.
```

Đây là ví dụ định nghĩa, không phải mục tiêu phù hợp cho mọi sản phẩm. Cần xác định request đủ điều kiện, mẫu số, loại lỗi và cách xử lý telemetry thiếu. Một SLO không có định nghĩa SLI rõ sẽ khó đánh giá công bằng.

## 10. Khi các bên không đồng ý

Tranh luận về chất lượng thường xuất hiện khi lợi ích và chi phí khác nhau. Ví dụ Product muốn phát hành nhanh, Security muốn thêm bước xác minh, Operations không muốn nhận một dịch vụ chưa có cảnh báo và rollback.

Một quy trình trao đổi hữu ích:

### Bước 1 — Quay lại kết quả người dùng và rủi ro

Hỏi vấn đề nào xảy ra nếu không đạt tiêu chí? Ai chịu tác động và hậu quả nghiêm trọng tới đâu?

### Bước 2 — Tách điều bắt buộc khỏi điều mong muốn

Phân loại yêu cầu pháp lý/bảo mật, hợp đồng đã cam kết, mục tiêu trải nghiệm và cải thiện nội bộ. Không gộp tất cả thành một mức ưu tiên.

### Bước 3 — Đưa ra lựa chọn và đánh đổi

Ví dụ phát hành theo nhóm người dùng, giới hạn tải ban đầu, giữ API cũ, hoặc hoãn một tính năng để hoàn thiện quan sát.

### Bước 4 — Chỉ định người có quyền quyết định

Người chịu trách nhiệm nghiệp vụ quyết định đánh đổi sản phẩm; vai trò bảo mật/pháp lý quyết định những kiểm soát thuộc phạm vi chuyên môn theo chính sách; người phụ trách vận hành xác nhận khả năng tiếp nhận và khôi phục.

### Bước 5 — Ghi quyết định và điều kiện xem xét lại

Nêu lựa chọn, lý do, rủi ro chấp nhận, người phê duyệt, thời hạn và tín hiệu khiến nhóm phải đánh giá lại.

### 10.1. Khi nào không nên thương lượng?

Một số ràng buộc có thể là **điều kiện bắt buộc**, ví dụ không để lộ credential hoặc không ghi dữ liệu thanh toán nhạy cảm vào log theo chính sách áp dụng. Khi đó nhóm cần tìm phương án đáp ứng ràng buộc, không đơn giản đổi ngưỡng để hợp thức hóa việc vi phạm.

Nếu có ngoại lệ được phép, cần theo quy trình quản trị rủi ro chính thức, phạm vi rõ và phê duyệt đúng thẩm quyền.

## 11. Quản lý thay đổi thỏa thuận theo thời gian

Yêu cầu chất lượng có thể đổi khi:

- Số người dùng hoặc quy mô dữ liệu tăng.
- Thêm thị trường, thiết bị hoặc client mới.
- Thay database, cloud provider hoặc dịch vụ ngoài.
- Phát hiện threat mới.
- SLO hoặc chi phí vận hành thay đổi.
- Hợp đồng API cần nâng phiên bản.
- Một giả định thiết kế ban đầu không còn đúng.

Khi thay đổi, cần ghi:

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Điều gì thay đổi so với thỏa thuận cũ? | Xác định phạm vi hành vi/chất lượng mới |
| Vì sao cần đổi? | Liên kết với nhu cầu hoặc rủi ro |
| Ai phê duyệt? | Bảo đảm đúng quyền quyết định |
| Có client hoặc dữ liệu cũ bị ảnh hưởng? | Tránh phá hợp đồng đã tồn tại |
| Test/gate/SLO nào cần cập nhật? | Giữ bằng chứng nhất quán |
| Mốc hiệu lực là khi nào? | Phân biệt đối tượng cũ và mới |
| Khi nào đánh giá lại? | Tránh mục tiêu tạm thời thành quy tắc vĩnh viễn |

Một thỏa thuận chất lượng cần **được quản lý như một hợp đồng sống**, nhưng không được sửa âm thầm để làm cho kết quả đo hiện tại trông đạt.

## 12. Đánh giá thỏa thuận có thực sự hữu ích không?

Có thể đánh giá qua các tín hiệu:

| Tín hiệu | Câu hỏi đánh giá | Giới hạn |
| --- | --- | --- |
| Tỷ lệ acceptance criteria được kiểm chứng | Nhóm có bằng chứng cho điều đã cam kết không? | Tiêu chí có thể thiếu hoặc sai |
| Số lần tranh luận do hiểu khác yêu cầu | Thỏa thuận có giảm mơ hồ không? | Cần phân biệt tranh luận có ích với xung đột không cần thiết |
| Số rủi ro phát hiện trước phát hành | Review/test có phát hiện sớm không? | Nhiều phát hiện có thể do thay đổi lớn hơn |
| Thời gian xử lý ngoại lệ | Quy trình quyết định có rõ không? | Nhanh không đồng nghĩa quyết định tốt |
| SLO và incident trend | Kết quả vận hành có tiến bộ không? | Cần kiểm soát tải, phạm vi và thay đổi cách đo |
| Thời gian từ yêu cầu đến kiểm thử | Nhóm có chuyển yêu cầu thành bằng chứng sớm không? | Không nên tối ưu bằng cách bỏ làm rõ |
| Tỷ lệ tiêu chí không có owner | Có yêu cầu nào không ai chịu trách nhiệm không? | Cần xem chất lượng phân công, không chỉ số lượng |

Không nên đánh giá cộng tác bằng số cuộc họp, số trang tài liệu hay số ô checklist đã đánh dấu. Thước đo có ý nghĩa hơn là **những người liên quan có cùng hiểu hợp đồng và có thể cung cấp bằng chứng khi cần hay không**.

## 13. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao chưa đủ | Cách làm phù hợp |
| --- | --- | --- |
| “Nhanh và an toàn là tiêu chí rõ rồi.” | Chưa có điểm đo, workload, threat hoặc ngưỡng | Viết kịch bản và thước đo cụ thể |
| “Developer tự quyết mọi tiêu chí chất lượng.” | Có tiêu chí thuộc quyền Product, Security, Operations hoặc pháp lý | Xác định người sở hữu quyết định |
| “Product chỉ cần nêu yêu cầu, kỹ thuật tự lo phần còn lại.” | Kỹ thuật không thể tự đoán đánh đổi nghiệp vụ | Cùng làm rõ ngưỡng và hậu quả |
| “Có test là đã có thỏa thuận.” | Test có thể mã hóa giả định chưa được phê duyệt | Xác nhận test oracle và tiêu chí |
| “Coverage cao là dễ bảo trì.” | Coverage không đo trách nhiệm hay khả năng thay đổi | Dùng kịch bản thay đổi và review dependency |
| “SLO nội bộ chính là SLA.” | SLA có thể có nghĩa vụ hợp đồng khác | Dùng đúng thuật ngữ và thẩm quyền |
| “Cứ đặt ngưỡng thật cao để đảm bảo chất lượng.” | Có thể không khả thi và tạo động cơ lách số liệu | Dùng baseline, nhu cầu và guardrail |
| “Ngoại lệ là thất bại của quy trình.” | Một số đánh đổi có thể được chấp nhận có chủ đích | Ghi waiver, người duyệt và hạn hiệu lực |
| “Đã chốt một lần thì không cần xem lại.” | Quy mô, threat và môi trường thay đổi | Quản lý phiên bản và thời điểm hiệu lực |
| “Nhiều tài liệu đồng nghĩa cộng tác tốt.” | Bản sao dễ lệch và không ai sở hữu | Chọn nguồn chuẩn và liên kết |
| “Mọi yêu cầu đều phải có con số.” | Một số thuộc tính cần bằng chứng định tính có cấu trúc | Dùng kịch bản, review và tiêu chí rõ |
| “Gate xanh nghĩa là thỏa thuận đã đạt toàn diện.” | Gate chỉ kiểm tra phạm vi đã cấu hình | Nêu giới hạn và bằng chứng còn thiếu |

## 14. Bài tập vận dụng: thống nhất yêu cầu chất lượng cho API đăng ký khóa học

Một nhóm xây dựng API `POST /enrollments` cho nền tảng học trực tuyến. Yêu cầu ban đầu từ Product:

> “Đăng ký phải nhanh, không được mất chỗ, dữ liệu học viên phải an toàn và nhóm phải dễ bổ sung quy tắc ưu tiên.”

Bối cảnh giả định:

- Một lớp có tối đa 30 chỗ.
- Có nhiều application instance dùng chung database.
- Người học có thể nhấn đăng ký nhiều lần do mạng chậm.
- Hệ thống gửi sự kiện để tạo email xác nhận.
- Operations cần vận hành dịch vụ cả ngoài giờ làm việc.
- Nhóm hiện chưa có baseline hiệu năng.

Hãy thực hiện:

1. **Làm rõ từ mơ hồ:** nêu câu hỏi để xác định “nhanh”, “không mất chỗ”, “an toàn” và “dễ bổ sung quy tắc”.
2. **Viết bốn quality scenarios:** một về hiệu năng, một về cạnh tranh giữ chỗ, một về bảo vệ dữ liệu và một về khả năng thay đổi chính sách.
3. **Viết ít nhất sáu acceptance criteria:** có điều kiện, kết quả và bằng chứng cụ thể; phân biệt unit, integration, contract và load test.
4. **Chốt mẫu số và điều kiện đo:** với hiệu năng, xác định workload, p95, timeout, cửa sổ đo và cách xử lý request lỗi.
5. **Lập bảng trách nhiệm RACI:** Product, Tech lead, Developer, QA, Security và Operations; bảo đảm mỗi quyết định có người A rõ.
6. **Nêu ba đánh đổi:** ví dụ cache, idempotency, outbox, consistency hoặc thời gian CI; ghi lợi ích, rủi ro và điều kiện chấp nhận.
7. **Định nghĩa Definition of Ready và Done:** điều kiện nào cần có trước khi bắt đầu, bằng chứng nào phải có trước khi phát hành?
8. **Xử lý bất đồng:** Product muốn phát hành sớm nhưng integration test concurrency chưa chạy được; ai quyết định, cần bằng chứng nào và khi nào có thể chấp nhận ngoại lệ?
9. **Lập kế hoạch theo dõi:** metric, alert, runbook và người sở hữu sau khi phát hành.

**Hướng tự đối chiếu:** “nhanh” chưa có nghĩa nếu thiếu workload và điểm đo; “không mất chỗ” cần bất biến và kiểm thử tại database dùng chung, không chỉ khóa trong một JVM; “an toàn” cần xác định tài sản và mối đe dọa; “dễ bổ sung quy tắc” cần chỉ ra một loại thay đổi cụ thể và ranh giới sở hữu policy. Product xác nhận hành vi và ưu tiên; Security xác nhận kiểm soát thuộc phạm vi bảo mật; Operations xác nhận khả năng vận hành; kỹ thuật đề xuất giải pháp và bằng chứng. Ngoại lệ cho integration test phải có phạm vi, người duyệt, hạn và biện pháp thay thế, không được tự coi bước chưa chạy là đạt.

## 15. Ghi nhớ

- **Yêu cầu chất lượng cần được diễn đạt thành kịch bản và tiêu chí có thể xác minh**, không dừng ở tính từ như nhanh, an toàn hoặc dễ bảo trì.
- **Thỏa thuận cần có ngữ cảnh, điểm đo, workload, ngưỡng, bằng chứng và giới hạn diễn giải**.
- **Mỗi quyết định cần có người sở hữu**; Product, kỹ thuật, QA, Security và Operations cùng đóng góp theo trách nhiệm.
- **Thương lượng phải làm rõ đánh đổi**, rủi ro được chấp nhận và điều kiện xem xét lại.
- **Đưa thỏa thuận vào ticket, test, API contract, quality gate, ADR và runbook**, đồng thời duy trì một nguồn chuẩn cho từng loại thông tin.
- **Không bịa ngưỡng khi chưa có baseline**; tạo hoạt động đo có thời hạn rồi chốt mục tiêu dựa trên bằng chứng.
- **Quản lý thay đổi thỏa thuận theo phiên bản và thời điểm hiệu lực**, bảo vệ client và dữ liệu đã tồn tại.
- **Đánh giá cộng tác bằng sự thống nhất và bằng chứng**, không bằng số cuộc họp hay số trang tài liệu.

Một thỏa thuận chất lượng tốt biến câu “chúng ta muốn hệ thống tốt” thành **điều gì phải đúng, trong điều kiện nào, ai chịu trách nhiệm và bằng chứng nào xác nhận**. Khi những điều đó được thống nhất từ sớm và được duy trì qua phát triển, kiểm thử và vận hành, nhóm có thể đưa ra quyết định rõ ràng hơn, xử lý đánh đổi minh bạch hơn và cải thiện mã nguồn một cách bền vững.
