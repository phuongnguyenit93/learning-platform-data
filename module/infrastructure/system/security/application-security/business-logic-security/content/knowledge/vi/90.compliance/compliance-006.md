# Regional rule variation

## 1. Quy tắc nghiệp vụ thay đổi theo vùng như thế nào?

**Regional rule variation** là việc cùng một thao tác nghiệp vụ phải áp dụng tập điều kiện khác nhau tùy phạm vi thị trường, chủ thể kinh doanh, nơi cung cấp dịch vụ hoặc các yếu tố liên quan đã được xác định. Trong chương **Compliance**, vấn đề không chỉ là có nhiều bộ cấu hình, mà là chứng minh hệ thống chọn đúng bộ quy tắc và không cho người dùng tự chuyển sang bộ dễ hơn.

Ví dụ, một sản phẩm có thể đặt thời hạn hủy đơn và ngưỡng phê duyệt hoàn tiền khác nhau giữa các thị trường. Nếu máy chủ chọn quy tắc từ header `X-Region` do client gửi, người dùng có thể đổi header để xin hạn mức cao hơn, bỏ qua phê duyệt hoặc mở lại một thao tác đã hết thời hạn.

Trong bảo mật logic nghiệp vụ, cần bảo vệ đồng thời:

- **Tính đúng của phạm vi áp dụng:** quyết định dựa trên ngữ cảnh nghiệp vụ đáng tin cậy.
- **Tính đúng của quy tắc:** dùng phiên bản, mốc thời gian và cách kết hợp đã được xác nhận.
- **Tính nhất quán khi thực thi:** API, worker, công cụ quản trị và đường retry áp dụng cùng quyết định phù hợp.
- **Các invariant xuyên vùng:** phân quyền theo đối tượng, giới hạn tiền, chuyển trạng thái và chống lặp vẫn được giữ.

Bài học dùng hai thị trường giả định `MKT-A` và `MKT-B`. Các thời hạn, ngưỡng tiền và mã policy đều là **chính sách thương mại minh họa của một sản phẩm**, không mô tả luật của quốc gia nào. Khi triển khai yêu cầu bên ngoài, tổ chức cần xác nhận nguồn, phiên bản, phạm vi và cách diễn giải trước khi chuyển thành quy tắc kỹ thuật.

## 2. Phân biệt thị trường, thẩm quyền áp dụng và vùng hạ tầng

Một trường `region` duy nhất thường không đủ diễn tả ngữ cảnh cần thiết:

| Khái niệm | Vai trò | Điều không nên suy luận tự động |
| --- | --- | --- |
| Business market | Thị trường hoặc kênh bán mà giao dịch được thiết lập | Không nhất thiết trùng nơi người dùng đang truy cập |
| Merchant entity | Pháp nhân hoặc đơn vị bán hàng chịu trách nhiệm giao dịch | Không được đổi chỉ bằng lựa chọn ngôn ngữ |
| Customer jurisdiction context | Thông tin khách hàng có liên quan đến phạm vi quy tắc | Không được xác định chắc chắn chỉ từ IP |
| Delivery/service location | Nơi giao hàng hoặc cung cấp dịch vụ theo dữ liệu đã xác minh | Không phải lúc nào cũng quyết định mọi quy tắc của giao dịch |
| Deployment region | Vùng máy chủ, database hoặc worker đang chạy | Không tự quyết định quyền hủy đơn hay hạn mức hoàn tiền |
| Locale | Ngôn ngữ, định dạng ngày hoặc cách hiển thị số | Không phải căn cứ cấp thêm quyền nghiệp vụ |
| Currency | Đơn vị tiền tệ của giao dịch | Không đủ để xác định thị trường hoặc bộ yêu cầu áp dụng |

Một đơn có thể được bán bởi một merchant entity, giao tới nơi khác và được xử lý ở một cụm máy chủ thứ ba. Bộ phận nghiệp vụ có trách nhiệm xác định yếu tố nào quyết định từng nhóm quy tắc; kỹ thuật không nên tự đặt một thứ tự chung cho mọi tình huống.

### 2.1. Phân loại độ tin cậy của dữ liệu

Ngữ cảnh do máy chủ lưu khi tạo đơn, tài khoản merchant đã cấu hình và thông tin đã được kiểm chứng là nguồn khác với query parameter, cookie, locale hoặc địa chỉ do client vừa nhập. Dữ liệu client có thể là đầu vào cần xác minh, nhưng không tự trở thành kết luận về phạm vi áp dụng.

Ví dụ client gửi:

```http
POST /orders/O-731/refunds
X-Region: MKT-A
Accept-Language: vi-VN

{"amount": 1200000, "currency": "VND"}
```

Nếu đơn `O-731` có ngữ cảnh đã xác nhận thuộc `MKT-B`, header trên không được làm máy chủ đổi sang policy của `MKT-A`. Máy chủ vẫn phải xác thực actor, kiểm tra quyền trên đơn và sử dụng dữ liệu tiền của giao dịch đã lưu.

### 2.2. Ngữ cảnh phải có lịch sử thay đổi

Một snapshot hữu ích có thể gồm `merchant_entity_id`, `sales_market`, thông tin địa điểm cần thiết, loại sản phẩm, currency, mốc hợp đồng và tham chiếu bằng chứng xác minh. Lưu thêm `context_version` cùng nguồn của các thuộc tính quan trọng.

Không phải mọi thuộc tính đều bất biến vĩnh viễn. Khi cho phép đổi nơi giao hàng hoặc merchant entity, phải có quy trình xác thực, phân quyền, kiểm tra trạng thái và đánh giá lại quy tắc liên quan. Không âm thầm ghi đè ngữ cảnh khiến một đơn cũ được hưởng policy mới chỉ vì người dùng sửa hồ sơ hiện tại.

## 3. Tách invariant chung khỏi điều kiện theo thị trường

Giả sử sản phẩm cho phép hủy đơn đã thanh toán nhưng chưa giao, rồi hoàn tiền theo một ý định có định danh riêng. Chính sách minh họa là:

| Thuộc tính | `MKT-A` | `MKT-B` |
| --- | --- | --- |
| Thời lượng tiếp nhận yêu cầu hủy kể từ `paid_at` | 60 phút | 30 phút |
| Ngưỡng hoàn tiền cần quản lý độc lập duyệt | Trên 2.000.000 VND | Trên 1.000.000 VND |
| Đồng tiền hỗ trợ trong ví dụ | VND | VND |
| Trạng thái đơn cho phép hủy | Đã thanh toán, chưa giao, chưa hủy | Đã thanh toán, chưa giao, chưa hủy |

Hai thị trường cùng dùng VND có chủ đích: currency không phải khóa suy ra thị trường. Quy tắc thời gian ở đây dùng thời lượng thực, với điều kiện `request_received_at < paid_at + cancellation_duration`; request đúng thời điểm kết thúc đã nằm ngoài cửa sổ của chính sách minh họa này.

Với khoản hoàn 1.200.000 VND, `MKT-A` không yêu cầu quản lý duyệt theo ngưỡng trên, còn `MKT-B` có yêu cầu. Dù ở đâu, những invariant sau không được bỏ qua:

1. Actor có quyền trên đúng đơn, payment và tenant liên quan.
2. Số tiền lấy từ nguồn máy chủ, có currency hợp lệ và không vượt phần tiền có thể hoàn.
3. Trạng thái nghiệp vụ cho phép thao tác; không gọi thẳng bước cuối để bỏ qua điều kiện.
4. Phê duyệt bắt buộc, nếu có, đến từ người có quyền và gắn với đúng payload/version.
5. Cùng một ý định không tạo hai khoản hoàn khi retry, đổi tuyến hoặc chạy lại worker.
6. Kết quả chưa rõ sau timeout được đối soát, không bị coi là thất bại dứt khoát để mở khoản hoàn cạnh tranh.

“Không cần quản lý duyệt theo ngưỡng” không có nghĩa là không cần phân quyền hoặc không cần kiểm tra giới hạn tiền. Regional policy chỉ quyết định những điều kiện thuộc phạm vi của nó.

## 4. Xác định tập quy tắc áp dụng

### 4.1. Resolve từ ngữ cảnh nghiệp vụ, không từ tuyến mạng

Resolver nên nhận đối tượng đã được máy chủ xác định, loại thao tác và ngữ cảnh có phiên bản. Kết quả cần ghi rõ policy nào áp dụng, tại sao và còn thiếu dữ liệu gì.

```text
Đối tượng + loại thao tác + ngữ cảnh đã xác minh
  -> tiêu chí xác định phạm vi
  -> tập policy và phiên bản cần áp dụng
  -> quyết định cùng nghĩa vụ bổ sung
```

Một request được cân bằng tải sang cụm khác không nên tự đổi thị trường của đơn. Nếu có dịch vụ xác định policy dùng chung, cần bảo vệ cả API của dịch vụ đó và dữ liệu đầu vào; không cho downstream worker ghi đè kết luận bằng một header chưa kiểm chứng.

### 4.2. Không dùng quy tắc “luôn chọn chặt nhất” một cách máy móc

Một số điều kiện là giới hạn, một số là quyền của khách hàng, một số là nghĩa vụ phải thực hiện. Thời hạn ngắn hơn hoặc từ chối nhiều hơn không tự bảo đảm đáp ứng yêu cầu. Một policy có thể yêu cầu cung cấp một quyền lợi rộng hơn thay vì hạn chế thêm.

Khi có nhiều bộ quy tắc liên quan, cần một cách kết hợp đã được xác nhận: quy tắc nào áp dụng cho khía cạnh nào, có ưu tiên nào, trường hợp xung đột xử lý ra sao. Không dùng `min(window)` hoặc `max(approval_level)` làm lời giải mặc định cho mọi sự khác biệt.

Ví dụ, ngưỡng duyệt nội bộ và điều kiện tiếp nhận hủy có thể là hai quyết định riêng. Quyền hủy được chấp nhận không tự bỏ yêu cầu kiểm soát việc thực hiện hoàn tiền; đồng thời quy trình duyệt nội bộ không nên làm mất dấu thời điểm khách hàng đã gửi yêu cầu hợp lệ.

### 4.3. Dữ liệu thiếu hoặc xung đột phải có trạng thái rõ ràng

| Tình huống | Hành vi thiết kế phù hợp |
| --- | --- |
| Có ngữ cảnh và policy hợp lệ, nhất quán | Đánh giá theo tập quy tắc đã xác định |
| Client tự khai thị trường khác với đơn | Không đổi phạm vi chỉ vì dữ liệu tự khai; ghi nhận sai lệch nếu cần |
| Thiếu thuộc tính bắt buộc để xác định policy | Chuyển trạng thái cần làm rõ, không dùng mặc định dễ hơn |
| Nhiều policy xung đột mà chưa có cách kết hợp | Chuyển rà soát có trách nhiệm, không chọn tùy thứ tự cấu hình |
| Policy service không khả dụng | Dùng snapshot/cache đã được cho phép theo thiết kế hoặc hoãn bước nhạy cảm; không tự nới điều kiện |

Khi cần hoãn, hãy lưu yêu cầu và thời điểm tiếp nhận đáng tin cậy, trả trạng thái dễ hiểu và có thời hạn xử lý nội bộ. Chặn side effect chưa đủ điều kiện không có nghĩa phải làm mất yêu cầu hoặc tự coi khách hàng chưa từng gửi yêu cầu. Nhánh rà soát phải có người chịu trách nhiệm và đường hoàn tất.

## 5. Phiên bản policy và mốc thời gian áp dụng

### 5.1. Phân biệt thời điểm chọn policy với thời điểm đánh giá điều kiện

Một quyết định thường có nhiều mốc:

- `contract_at`: thời điểm hình thành giao dịch theo định nghĩa của sản phẩm.
- `paid_at`: mốc thanh toán đáng tin cậy dùng cho cửa sổ hủy trong ví dụ.
- `request_received_at`: thời điểm máy chủ tiếp nhận yêu cầu hợp lệ.
- `decision_at`: thời điểm hệ thống đưa ra quyết định.
- `execution_at`: thời điểm worker thực hiện hoặc gửi lệnh ra ngoài.

Trong ví dụ, chính sách thương mại có thể được chọn theo mốc giao dịch của đơn, còn điều kiện còn hạn hủy được tính bằng `request_received_at` so với `paid_at`. Nếu queue chậm mười phút, dùng thời điểm worker chạy thay cho thời điểm tiếp nhận sẽ cho kết quả khác dù khách hàng đã gửi yêu cầu đúng hạn.

Không mặc định mọi quy tắc đều được đóng băng theo lúc tạo đơn. Cũng không mặc định mọi quy tắc đều dùng phiên bản mới nhất lúc worker chạy. Cần định nghĩa cơ sở thời gian cho từng nhóm yêu cầu, bao gồm quy tắc về các lệnh đang chờ khi có thay đổi cần áp dụng ngay.

Lưu version hoặc digest của policy thực sự đã được đánh giá, phiên bản ngữ cảnh, dữ liệu đầu vào cần thiết và lý do quyết định. Giữ khả năng tái hiện quyết định cũ bằng đúng phiên bản đó thay vì chỉ đọc cấu hình hiện tại.

### 5.2. Thay đổi policy cần có quy tắc chuyển tiếp

Giả sử ngưỡng duyệt `MKT-B` thay đổi trong khi có refund đã tạo nhưng chưa thực hiện. Thiết kế phải trả lời:

- Yêu cầu nào giữ quyết định cũ, yêu cầu nào phải đánh giá lại?
- Approval cũ còn hợp lệ với payload và phiên bản quyết định mới không?
- Outbox đã commit nhưng chưa gửi được xử lý thế nào?
- Refund đang `UNKNOWN` sau khi có thể đã gửi có được thay đổi không?

Nếu cần đánh giá lại, tạo dấu vết chuyển tiếp rõ ràng và giữ nguyên liên kết operation. Không biến việc cập nhật policy thành một lệnh hoàn tiền mới. Khi provider có thể đã thực hiện, ưu tiên xác minh kết quả; không gửi lệnh thay thế theo bộ quy tắc mới trong lúc kết quả cũ chưa rõ.

### 5.3. Thời lượng, ngày địa phương và tiền tệ

“Trong 24 giờ” và “đến cuối ngày làm việc tiếp theo” là hai quy tắc khác nhau. Quy tắc theo ngày địa phương cần múi giờ được cấu hình, lịch làm việc nếu có và cách xử lý thời điểm nhập nhằng. Đừng thay bằng một UTC offset cố định hoặc tự nhân số ngày với 24 giờ cho mọi trường hợp.

Với thời lượng của ví dụ, lưu timestamp chuẩn và dùng đồng hồ máy chủ được kiểm soát. Timestamp do client gửi không được tự thay thế thời điểm tiếp nhận. Nếu cho phép người dùng bổ sung bằng chứng thời gian, đó phải là quy trình xác minh riêng.

Ngưỡng tiền phải chỉ rõ currency và đơn vị. Không so sánh số minor unit của VND với số của một đồng tiền khác. Nếu sản phẩm dùng chuyển đổi tiền tệ để xét ngưỡng, phải định nghĩa nguồn tỷ giá, mốc chốt, cách làm tròn và phiên bản dữ liệu; nếu chưa đủ thông tin thì không tự coi hai số là tương đương.

## 6. Kiến trúc thực thi nhất quán

### 6.1. Tách quyết định policy khỏi quyền thực hiện

Một policy engine có thể trả về:

| Kết quả | Ý nghĩa trong thiết kế minh họa |
| --- | --- |
| `ALLOW` | Điều kiện vùng đã thỏa mãn trong phạm vi đánh giá |
| `NEEDS_APPROVAL` | Cần phê duyệt phù hợp trước khi chấp nhận lệnh thực hiện |
| `DENY` | Điều kiện đã xác định không cho phép thao tác này |
| `REVIEW` | Thiếu dữ liệu, policy xung đột hoặc chưa đủ căn cứ tự quyết định |

`ALLOW` của bộ quy tắc vùng không cấp quyền truy cập đối tượng. Chỉ thực hiện nghiệp vụ sau khi quyền, trạng thái, ngân sách, approval và các điều kiện chung đều thỏa mãn. Trạng thái xử lý của workflow cũng cần tách khỏi kết quả policy: yêu cầu đang chờ duyệt chưa phải refund đã thực hiện.

### 6.2. Kiểm soát ranh giới transaction

Một luồng thực thi có thể tổ chức như sau:

1. Xác thực actor và giới hạn truy cập theo tenant; resolve đối tượng rồi kiểm tra quyền theo đối tượng.
2. Xác định ngữ cảnh nghiệp vụ có phiên bản và tập policy có thể áp dụng. Có thể chuẩn bị snapshot policy trước transaction để tránh gọi mạng trong lúc giữ khóa.
3. Trong transaction ngắn, khóa hoặc kiểm soát phiên bản đơn/payment. Nếu dữ liệu đã đổi so với snapshot dùng để resolve, dừng quyết định cũ và đánh giá lại.
4. Tính số tiền phía máy chủ, kiểm tra trạng thái, đánh giá policy, kiểm tra approval cần thiết và xử lý request key.
5. Ghi quyết định cùng phiên bản và thời điểm tiếp nhận. Nếu chưa đủ điều kiện, tạo trạng thái chờ phù hợp. Khi chấp nhận lệnh thực hiện refund, giữ chỗ tiền nguyên tử và ghi outbox cùng transaction.
6. Worker thực hiện lệnh đã lưu, gọi provider ngoài transaction cơ sở dữ liệu và áp dụng kết quả với cơ chế chống lặp.

Chính sách kích hoạt phiên bản mới phải phối hợp với cơ sở thời gian đã định nghĩa. Nếu có một thay đổi bắt buộc ảnh hưởng các quyết định mới, cần cơ chế kiểm tra phiên bản hoặc mốc kích hoạt đủ mạnh trước khi commit. Không chỉ dựa vào giả định mọi cache ở mọi instance đã cập nhật đồng thời.

Không giữ transaction cơ sở dữ liệu trong suốt lần gọi provider rồi cho rằng rollback sẽ hủy khoản hoàn ở bên ngoài. Sau lỗi mạng hoặc tiến trình chết, phục hồi bằng operation đã lưu, định danh provider và đối soát.

### 6.3. Quyết định có thể chuyển tuyến, ý định nghiệp vụ phải ổn định

Khóa idempotency ở API cần scope rõ ràng, chẳng hạn tenant, principal, loại thao tác và request key. Fingerprint phải gắn với đối tượng cùng dữ liệu có ý nghĩa. Nếu client giữ key nhưng đổi payload, hệ thống phát hiện xung đột thay vì sửa operation cũ.

Không dùng vùng do client chọn để chia namespace chống lặp theo cách cho phép cùng ý định tạo lại ở vùng khác. Đổi `X-Region`, locale hoặc điểm truy cập không được trở thành cách tạo refund độc lập thứ hai.

Khi gọi provider, lưu cả khóa ổn định, account, môi trường và định danh giao dịch cần thiết. Nếu khóa chỉ được provider bảo vệ trong một account, chuyển sang account hoặc provider khác sau timeout có thể tạo khoản hoàn mới. Chuyển tuyến hạ tầng không tự mở rộng phạm vi bảo vệ của khóa.

Giới hạn tiền cũng phải có nguồn quyết định nhất quán theo payment. Nếu hai vùng mỗi nơi tự giữ một bộ đếm riêng cho cùng khoản thu, cả hai có thể cùng thấy đủ số dư và hoàn vượt ngân sách. Cần authority hoặc cơ chế đồng bộ bảo vệ invariant đã được thiết kế rõ ràng; một bản sao dữ liệu trễ không đủ để cấp ngân sách độc lập.

## 7. Ví dụ cấu hình và quản trị policy

YAML sau chỉ minh họa cấu trúc của bộ quy tắc thương mại giả định. Nó không phải metadata của bài học hoặc mô tả yêu cầu pháp lý thực tế.

```yaml
policy_id: cancellation-refund-demo
version: demo-v3
policy_kind: COMMERCIAL_DEMO
selection_basis: order_contract_time
unknown_context_action: REVIEW
markets:
  MKT-A:
    currency: VND
    cancellation:
      duration_seconds: 3600
      evaluation_time: server_request_received_at
      end_boundary: EXCLUSIVE
    refund:
      independent_approval_if_amount_greater_than_minor: 2000000
  MKT-B:
    currency: VND
    cancellation:
      duration_seconds: 1800
      evaluation_time: server_request_received_at
      end_boundary: EXCLUSIVE
    refund:
      independent_approval_if_amount_greater_than_minor: 1000000
```

Bộ cấu hình này chỉ chứa điều kiện theo thị trường. Phân quyền, state machine, ngân sách và chống lặp vẫn thuộc kiểm soát chung. Không suy ra rằng một thuộc tính vắng mặt trong YAML có nghĩa kiểm soát tương ứng đã bị tắt.

Policy cần được quản trị như một thay đổi có thể tác động đến tiền và quyền người dùng:

- Kiểm tra schema, kiểu dữ liệu, thị trường được hỗ trợ, giá trị âm, currency và các thuộc tính bắt buộc.
- Phát hiện khoảng hiệu lực chồng lấn, thiếu phiên bản hoặc trường hợp không có quy tắc phù hợp.
- Rà soát nghiệp vụ và kỹ thuật theo trách nhiệm; ghi người đề xuất, người phê duyệt và lý do thay đổi.
- Liên kết yêu cầu nguồn, phạm vi và bộ test liên quan; giữ lịch sử phiên bản đã phát hành.
- Kiểm soát quyền sửa, kích hoạt và rollback; theo dõi digest policy trên các instance.

Chữ ký hoặc hash của gói policy giúp xác minh tính toàn vẹn theo cơ chế đã thiết kế, nhưng không chứng minh nội dung chính sách đã được diễn giải đúng. Một cấu hình sai được ký hợp lệ vẫn có thể gây lỗi nghiệp vụ.

## 8. Mã giả đánh giá một phần điều kiện vùng

Đoạn Java sau chỉ minh họa hàm đánh giá cửa sổ hủy và ngưỡng duyệt của ví dụ. Ngữ cảnh, amount và timestamp được máy chủ chuẩn bị từ dữ liệu đáng tin cậy. Các lớp và hàm là mã giả, không phải triển khai đầy đủ.

```java
RegionalDecision evaluateRegionalConditions(
        PolicySnapshot policy,
        VerifiedOrderContext context,
        Money serverRefundAmount,
        Instant serverReceivedAt) {

    if (!context.isComplete() || !policy.matches(context)) {
        return RegionalDecision.review("CONTEXT_UNRESOLVED");
    }

    MarketRule rule = policy.ruleFor(context.salesMarket());
    if (rule == null || !rule.currency().equals(serverRefundAmount.currency())) {
        return RegionalDecision.review("RULE_OR_CURRENCY_UNSUPPORTED");
    }

    if (context.paidAt() == null || serverReceivedAt.isBefore(context.paidAt())) {
        return RegionalDecision.review("TIME_EVIDENCE_INCONSISTENT");
    }

    Instant deadline = context.paidAt().plus(rule.cancellationDuration());
    if (!serverReceivedAt.isBefore(deadline)) {
        return RegionalDecision.deny("CANCELLATION_WINDOW_CLOSED");
    }

    if (serverRefundAmount.minorUnits() > rule.approvalThresholdMinor()) {
        return RegionalDecision.needsIndependentApproval(policy.version());
    }

    return RegionalDecision.allow(policy.version());
}
```

Đường gọi hàm vẫn phải kiểm tra amount dương, ngân sách hoàn, quyền trên đối tượng, trạng thái đơn và sự hợp lệ của approval. Khi kết quả là `NEEDS_APPROVAL`, việc người dùng truyền thêm `approved=true` không đáp ứng nghĩa vụ; phải xác minh bản ghi phê duyệt do máy chủ quản lý, người duyệt và payload/version liên quan.

Hàm được dùng cho một chính sách minh họa có cửa sổ hủy đơn giản. Sản phẩm có ngoại lệ hoặc tập quy tắc phức tạp cần resolver và mô hình quyết định tương ứng, không được coi nhánh `DENY` ở đây là lời giải chung cho mọi yêu cầu hủy.

## 9. Các đường lách quy tắc thường gặp

### 9.1. Chọn vùng bằng thuộc tính hiển thị

Nếu backend dùng locale, domain giao diện hoặc cookie để chọn ngưỡng duyệt, actor có thể chuyển giao diện rồi gửi lại request. Kiểm soát đúng là resolve policy từ đối tượng nghiệp vụ và dữ liệu đã xác nhận; thuộc tính hiển thị chỉ phục vụ trải nghiệm theo phạm vi được cho phép.

### 9.2. Sửa hồ sơ để đổi quy tắc cho giao dịch cũ

Người dùng đổi địa chỉ tài khoản ngay trước khi hoàn tiền. Nếu hệ thống đọc địa chỉ hiện tại mà bỏ snapshot của đơn, giao dịch có thể bị áp dụng policy khác. Cần phân biệt dữ liệu liên hệ hiện tại với ngữ cảnh có hiệu lực của giao dịch và đánh giá mọi thay đổi ngữ cảnh qua quy trình phù hợp.

### 9.3. Gọi đường có policy cũ hoặc bị bỏ qua

API chính có thể áp dụng policy mới nhưng endpoint cũ, script hỗ trợ hoặc worker đối soát vẫn dùng hằng số cũ. Kẻ tấn công hoặc người vận hành thiếu thông tin có thể đi qua đường này. Rà soát mọi nơi tạo cùng hiệu ứng và bảo đảm chúng có quyết định hợp lệ, đúng phiên bản, đúng phạm vi trách nhiệm.

Việc dùng chung thư viện không đủ nếu một đường truyền `skipRegionalChecks=true` hoặc tự gán thị trường mặc định. Các ngoại lệ cần được định nghĩa, phân quyền và kiểm chứng riêng.

### 9.4. Chuyển vùng để làm mất dấu chống lặp

Một operation đã gửi tại cụm A bị timeout, sau đó request được gửi sang cụm B. Nếu B không tìm thấy operation vì dữ liệu phân mảnh theo vùng truy cập, nó có thể tạo refund mới. Cần ánh xạ request về authority của đối tượng hoặc cơ chế nhất quán phù hợp; không coi “không thấy trong bản sao cục bộ” là bằng chứng operation chưa tồn tại.

Không chuyển provider/account để thử lại khoản tiền chưa rõ kết quả chỉ vì nhà cung cấp ở vùng khác đang khả dụng. Trước hết phải giải quyết trạng thái của ý định đã gửi.

### 9.5. Dùng policy để bỏ qua kiểm soát chung

Một implementation có thể viết `if (region == MKT_A) allowRefund()` rồi bỏ toàn bộ state guard, quyền và giới hạn tiền. Nhánh vùng phải trả về điều kiện hoặc nghĩa vụ trong phạm vi của nó; command handler cuối cùng vẫn duy trì các invariant chung.

Tương tự, phê duyệt theo vùng không cho phép người duyệt thao tác tenant khác, cũng không hợp thức hóa khoản hoàn vượt phần tiền còn lại. Mỗi điều kiện có mục đích riêng và phải được kiểm tra ở đúng điểm thực thi.

## 10. Kiểm thử ranh giới, lạm dụng và thay đổi cấu hình

### 10.1. Ma trận kiểm thử tối thiểu

| Nhóm kiểm thử | Tình huống | Điều cần chứng minh |
| --- | --- | --- |
| Chống giả mạo vùng | Đơn thuộc `MKT-B`, client gửi header/locale của `MKT-A` | Policy vẫn resolve từ ngữ cảnh đơn; khoản 1.200.000 VND vẫn cần duyệt |
| Phân quyền theo đối tượng | Actor biết order ID của tenant khác | Không được đổi ngữ cảnh, tạo refund hoặc đọc dữ liệu ngoài quyền |
| Biên thời gian | Gửi ngay trước, đúng và ngay sau deadline | Kết quả đúng quy ước biên đã công bố; dùng timestamp tiếp nhận đáng tin cậy |
| Queue chậm | Nhận request còn hạn, worker chạy sau deadline | Không tự đổi mốc đánh giá thành thời điểm worker chạy; các điều kiện trạng thái khác vẫn được kiểm tra |
| Biên số tiền | Amount đúng ngưỡng và lớn hơn ngưỡng một minor unit | Điều kiện `>` được áp dụng đúng; không sai do kiểu số hoặc làm tròn |
| Currency khác | Đơn hoặc refund dùng currency không được cấu hình | Không so sánh mù với threshold VND; chuyển kết quả theo thiết kế đã xác định |
| Thiếu ngữ cảnh | Không đủ dữ liệu hoặc policy không xác định | Không dùng mặc định dễ hơn; yêu cầu được giữ để làm rõ |
| Thay đổi hồ sơ | Đổi địa chỉ tài khoản rồi yêu cầu refund đơn cũ | Không âm thầm thay policy của đơn bằng hồ sơ hiện tại |
| Đua thay đổi ngữ cảnh | Context version đổi giữa resolve và commit | Quyết định dựa trên snapshot cũ không được commit như còn hợp lệ |
| Thay policy | Một yêu cầu đang chờ duyệt qua mốc kích hoạt mới | Áp dụng đúng quy tắc chuyển tiếp, giữ lịch sử và kiểm tra approval liên quan |
| Retry qua cụm khác | Gửi lại cùng operation sau timeout và chuyển tuyến | Không tạo refund độc lập thứ hai; khoản chưa rõ vẫn được đối soát |
| Đường quản trị và batch | Thực hiện cùng nghiệp vụ qua công cụ khác API chính | Cùng invariant được bảo vệ; ngoại lệ có phạm vi và quyền rõ ràng |
| Sự kiện trùng/sai thứ tự | Provider gửi kết quả lặp hoặc pending đến muộn | Không ghi sổ hai lần hoặc mở lại operation đã hoàn tất |
| Policy service lỗi | Mất kết nối hoặc cache không đủ phiên bản | Hành vi dự phòng đúng thiết kế; không tự nới điều kiện và không làm mất yêu cầu |

Khi kiểm thử thời gian, dùng đồng hồ điều khiển được. Khi kiểm thử cạnh tranh, dùng barrier hoặc cơ chế đồng bộ rõ ràng. Các kiểm tra transaction, giữ chỗ và ràng buộc dữ liệu cần bằng chứng với cơ sở dữ liệu phù hợp; kiểm tra refund trùng cần quan sát cả sổ provider/fake provider và dữ liệu nội bộ.

Không chỉ kiểm tra mã HTTP. Với request bị chặn, xác nhận không có refund hoặc outbox ngoài điều kiện cho phép. Với request đang rà soát, xác nhận ý định và thời điểm tiếp nhận đã được lưu nhưng side effect chưa đủ điều kiện chưa được thực hiện.

### 10.2. Các thuộc tính cần giữ trên nhiều bộ dữ liệu

Ngoài test từng ví dụ, có thể kiểm tra các thuộc tính:

- Với cùng ngữ cảnh chuẩn và cùng phiên bản policy, đổi locale hoặc tuyến hạ tầng không đổi quyết định nghiệp vụ.
- Mọi thị trường đều giữ quyền theo đối tượng, giới hạn tiền và chống lặp.
- Cùng một operation được giao lại nhiều lần vẫn chỉ có hiệu ứng được phép một lần.
- Thiếu dữ liệu bắt buộc không tự tạo một quyết định `ALLOW` không có căn cứ.
- Một quyết định đã lưu có thể tái hiện từ policy, context và input snapshot tương ứng.

Không dùng thuộc tính “policy mới luôn nghiêm hơn policy cũ” làm quy tắc chung. Chính sách hợp lệ có thể mở rộng quyền lợi hoặc thay cách đánh giá; cần kiểm tra chênh lệch theo mục tiêu và nguồn thay đổi cụ thể.

### 10.3. Đánh giá thay đổi mà không tạo side effect kép

Trước khi kích hoạt, có thể chạy bộ dữ liệu đại diện qua policy cũ và mới để xem quyết định nào thay đổi. Nếu dùng shadow evaluation, nhánh shadow chỉ tính quyết định, không phát lệnh refund, giao hàng hoặc gửi thông báo nghiệp vụ như luồng chính.

Phân tích chênh lệch theo thị trường, loại thao tác, currency, thời điểm và lý do. Mỗi chênh lệch phải có giải thích mong đợi hoặc được xử lý như một vấn đề cần xem xét. Tỷ lệ quyết định giống nhau cao không tự chứng minh đúng nếu phần khác biệt rơi vào nhóm rủi ro quan trọng.

## 11. Bằng chứng cho compliance và khả năng giải thích quyết định

Một bản ghi quyết định nên liên kết được ít nhất:

| Nhóm thông tin | Nội dung cần lưu hoặc tham chiếu |
| --- | --- |
| Đối tượng và danh tính | Operation, order/payment, actor, tenant; không dùng ID do client khai báo mà chưa resolve |
| Ngữ cảnh áp dụng | Market, merchant entity, thuộc tính cần thiết, context version và nguồn xác minh |
| Policy | Policy ID/version/digest, cơ sở chọn phiên bản và các rule liên quan |
| Thời gian | Mốc giao dịch, thanh toán, tiếp nhận, quyết định và thực hiện theo nhu cầu tái hiện |
| Điều kiện | Amount/currency từ máy chủ, trạng thái, approval hoặc nghĩa vụ chưa hoàn tất |
| Kết quả | `ALLOW`, `DENY`, `NEEDS_APPROVAL` hoặc `REVIEW`, cùng reason code và giới hạn |
| Hiệu ứng | Outbox, provider reference, trạng thái tiền tệ, lịch sử đối soát và khôi phục |

Ví dụ có thể giải thích: “Operation R-92 thuộc đơn có context version 4 của `MKT-B`; policy `demo-v3` yêu cầu quản lý duyệt vì số tiền 1.200.000 VND vượt 1.000.000 VND; yêu cầu được nhận trong cửa sổ hủy; chưa có approval phù hợp nên chưa gửi lệnh refund.” Kết luận đó cụ thể hơn một dòng log `region=B, rejected` và phân biệt rõ điều kiện thời gian với nghĩa vụ duyệt còn thiếu.

Nếu policy bắt nguồn từ yêu cầu bên ngoài, hồ sơ ánh xạ cần nối nguồn đã xác nhận tới mục tiêu, rule kỹ thuật, test và bằng chứng hoạt động. Một reason code hoặc cấu hình tồn tại chưa tự chứng minh sản phẩm đáp ứng toàn bộ yêu cầu đó.

Giới hạn dữ liệu trong log theo nhu cầu giải thích. Có thể lưu reference tới ngữ cảnh được bảo vệ thay vì sao chép địa chỉ, giấy tờ hoặc thông tin thanh toán vào mọi sự kiện. Phân quyền truy cập, bảo vệ lịch sử và áp dụng thời hạn lưu phù hợp với chính sách dữ liệu đã xác nhận; không tự coi một thời hạn chung là đúng cho mọi thị trường.

Khi đánh giá theo kỳ, ghi phạm vi triển khai, phiên bản dịch vụ, policy digest và thời gian có dữ liệu. Kết quả test ở một cụm chưa chứng minh cụm khác chạy cùng policy; ảnh chụp cấu hình cuối kỳ chưa mô tả được mọi phiên bản từng hoạt động trong kỳ.

## 12. Vận hành, xử lý sai lệch và bài thực hành

### 12.1. Vận hành policy như một phần của hệ thống nghiệp vụ

Theo dõi số quyết định theo market và reason code, tỷ lệ `REVIEW`, độ trễ giải quyết yêu cầu, instance dùng sai digest, operation chưa rõ kết quả và chênh lệch đối soát. Thay đổi đột ngột có thể là lỗi cấu hình, nguồn dữ liệu hỏng hoặc hành vi lạm dụng; cần phân tích bằng chứng thay vì kết luận chỉ từ một chỉ số.

Nếu phát hiện policy sai, quy trình xử lý cần xác định:

1. Phiên bản, khoảng thời gian, market và entry point bị ảnh hưởng.
2. Các operation đã được chấp nhận, bị từ chối, chờ duyệt hoặc chờ làm rõ theo phiên bản đó.
3. Hiệu ứng thực tế đã xảy ra ở database và hệ thống bên ngoài.
4. Yêu cầu nào cần đánh giá lại hoặc khắc phục, với operation ID được giữ ổn định.
5. Bằng chứng và người chịu trách nhiệm cho quyết định chuyển tiếp.

Rollback policy không tự hoàn tác refund đã thực hiện, không khôi phục một quyền lợi đã bị từ chối sai và không chứng minh các operation đang bay đã dừng. Khắc phục phải theo trạng thái thực tế, có kiểm soát lặp và có đường đối soát.

Phân công rõ người chịu trách nhiệm xác nhận nội dung policy, người triển khai enforcement và người vận hành nhánh ngoại lệ. Quyền sửa policy, quyền duyệt refund và quyền thực hiện nghiệp vụ là các quyền cần được quản lý theo phạm vi, không gộp mặc nhiên thành một vai trò toàn năng.

### 12.2. Bài thực hành tự chứa

Giả sử một đơn thuộc `MKT-B` được thanh toán lúc 10:00 UTC. Máy chủ nhận yêu cầu hủy và hoàn 1.200.000 VND lúc 10:25 UTC; worker chỉ xử lý lúc 10:35 UTC. Client gửi header `X-Region: MKT-A`. Đơn chưa giao, actor có quyền, tiền còn đủ để hoàn và chưa có approval quản lý.

Theo chính sách minh họa của bài:

- Dùng ngữ cảnh `MKT-B` của đơn, giữ phiên bản policy phù hợp; header không đổi phạm vi.
- Đánh giá cửa sổ bằng mốc tiếp nhận 10:25, nên điều kiện 30 phút vẫn thỏa mãn.
- Khoản 1.200.000 VND vượt ngưỡng `MKT-B`, nên yêu cầu cần approval độc lập trước bước thực hiện.
- Chưa gửi refund khi nghĩa vụ duyệt chưa hoàn tất; giữ yêu cầu và các mốc thời gian đã lưu.
- Nếu client gửi lại cùng ý định lúc 10:45, trả tiến trình của operation cũ theo hợp đồng idempotency; không tự tạo ý định mới hoặc thay mốc tiếp nhận gốc.

Hãy bổ sung các biến thể: request đầu tiên đến đúng 10:30; amount đúng 1.000.000 VND; thiếu context version; đơn đã giao trước bước chấp nhận thực hiện; policy đổi trong khi chờ duyệt; provider hoàn tiền rồi timeout và request được chuyển sang cụm khác. Với mỗi trường hợp, chỉ rõ kết quả policy, trạng thái workflow và side effect được phép.

Bài thực hành hoàn tất khi có thể chứng minh nguồn xác định vùng, phiên bản và mốc thời gian áp dụng, các invariant chung, đường xử lý dữ liệu thiếu, chống lặp xuyên tuyến và bằng chứng giải thích quyết định. Mọi ngoại lệ hoặc khoảng chưa biết phải hiện rõ trong kết quả thay vì được che bằng một cấu hình mặc định.
