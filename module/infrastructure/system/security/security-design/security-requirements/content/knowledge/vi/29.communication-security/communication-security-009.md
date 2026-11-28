# Webhook timestamp — Đặc tả yêu cầu thời gian để kiểm soát độ mới và replay

## 1. Timestamp có vai trò gì trong bảo mật webhook?

Webhook là một thông báo được hệ thống gửi tới endpoint của hệ thống khác, thường qua HTTP. Bên nhận cần xác minh nguồn, tính toàn vẹn nội dung, độ mới của lần gửi và quyền thực hiện thao tác nghiệp vụ tương ứng.

Timestamp có thể giúp giới hạn khoảng thời gian một thông điệp hợp lệ được chấp nhận. Nếu không có giới hạn phù hợp, một webhook bị ghi lại có thể được gửi lại sau rất lâu và vẫn vượt qua kiểm tra chữ ký.

Tuy nhiên, timestamp chỉ có giá trị bảo mật khi được ràng buộc với nội dung đã xác thực và được so sánh bằng nguồn thời gian đáng tin. Một header thời gian do người gửi tự khai báo mà không nằm trong phần được bảo vệ không chứng minh webhook còn mới.

Trong module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, bài học chuyển mục tiêu “không nhận webhook cũ hoặc phát lại trái phép” thành yêu cầu cụ thể:

- Timestamp nào được dùng để đánh giá độ mới?
- Timestamp đó có được chữ ký hoặc cơ chế xác thực bao phủ không?
- Chấp nhận trễ bao lâu và cho phép đi trước đồng hồ bên nhận bao nhiêu?
- Khi webhook được retry, timestamp được tạo lại hay giữ nguyên?
- Đánh giá độ mới tại cổng nhận hay tại worker xử lý sau?
- Làm thế nào để một webhook còn mới không gây tác dụng lặp?
- Đồng hồ lỗi, khóa đổi hoặc hệ thống phục hồi ảnh hưởng tới quyết định ra sao?

Các ngưỡng và tên header trong bài là hợp đồng minh họa. Khi tích hợp thực tế, phải dùng đúng giao thức và khả năng của bên gửi; không áp một định dạng ký chung cho mọi nhà cung cấp.

## 2. Phân biệt các loại thời gian

| Mốc | Ý nghĩa | Không nên tự suy ra |
| --- | --- | --- |
| event_occurred_at | Thời điểm sự kiện nghiệp vụ được ghi nhận ở nguồn | Đây luôn là thời điểm tạo chữ ký của mỗi lần giao |
| signed_at hoặc delivery timestamp | Mốc mà hợp đồng ký dùng cho lần gửi hoặc đối tượng được xác thực | Chắc chắn đúng với thời gian thực nếu chỉ có chữ ký |
| received_at | Thời điểm bên nhận ghi nhận request tại ranh giới đáng tin | Có thể lấy từ header tùy ý do client gửi |
| verified_at | Thời điểm hoàn tất xác minh | Đây là mốc duy nhất phù hợp cho mọi mô hình hàng đợi |
| processed_at | Thời điểm thực hiện nghiệp vụ | Message phải bị loại chỉ vì đợi lâu sau khi đã được nhận hợp lệ |
| expires_at nghiệp vụ | Thời hạn cho phép của một quyết định hoặc thao tác | Cùng ý nghĩa với cửa sổ chống replay ở cổng webhook |

Một sự kiện xảy ra từ một giờ trước vẫn có thể được giao lại hợp lệ bằng một lần gửi mới, nếu hợp đồng bên gửi cho phép và tạo lại chứng cứ thời gian phù hợp.

Ngược lại, một timestamp giao hàng mới không tự làm một thao tác nghiệp vụ đã hết hạn trở lại hợp lệ. Độ mới của kênh nhận và hiệu lực nghiệp vụ cần được kiểm tra riêng.

### 2.1. Chữ ký không chứng minh thời gian tuyệt đối

Chữ ký hợp lệ cho biết bên có quyền ký đã bảo vệ giá trị thời gian theo cơ chế được chọn. Nếu đồng hồ bên ký sai, timestamp vẫn có thể sai dù chữ ký đúng.

Do đó, yêu cầu cần cả ràng buộc mật mã, chất lượng đồng hồ và cửa sổ chấp nhận. Nếu khóa ký bị chiếm, kẻ có khóa có thể tạo timestamp mới; kiểm tra thời gian không thay thế quản lý khóa và thu hồi quyền nguồn gửi.

### 2.2. Không dùng thời gian sự kiện thay cho thời gian giao theo mặc định

Một field nghiệp vụ như thời điểm thanh toán không mặc nhiên là field được dùng để chống replay. Việc dùng nhầm có thể loại mọi retry của sự kiện cũ hoặc cho lệnh cũ đi qua bằng một field không được bảo vệ.

Phải xác định chính xác field/header, đơn vị, định dạng và ý nghĩa theo hợp đồng tích hợp.

## 3. Mô hình đe dọa và bất biến

| Kịch bản | Rủi ro | Hướng yêu cầu |
| --- | --- | --- |
| Gửi lại một webhook hợp lệ đã ghi được | Tạo tác dụng sau thời gian cho phép | Cửa sổ độ mới và chống lặp nghiệp vụ |
| Sửa timestamp thành thời điểm hiện tại | Làm mới thông điệp cũ | Timestamp phải nằm trong dữ liệu được xác thực |
| Timestamp đi quá xa vào tương lai | Kéo dài khả năng replay hoặc phá xử lý thời gian | Có giới hạn tương lai riêng |
| Nhầm giây với mili giây | Chấp nhận hoặc loại sai | Parse đúng đơn vị, không tự đoán/chuyển đổi |
| Hai timestamp cùng xuất hiện | Proxy và ứng dụng hiểu khác nhau | Quy tắc nguồn và số lượng timestamp rõ ràng |
| Bên nhận lệch giờ | Loại webhook hợp lệ hoặc nhận webhook quá cũ | Giám sát đồng hồ và hành vi khi thời gian không đủ tin cậy |
| Queue nội bộ chậm | Loại sự kiện đã được tiếp nhận hợp lệ | Tách kiểm tra tại ingress khỏi thời điểm xử lý nghiệp vụ |
| Retry giữ nguyên chữ ký cũ | Rơi ngoài cửa sổ dù là retry thật | Đánh giá tương thích với chính sách retry của bên gửi |
| Webhook mới nhưng được gửi nhiều lần | Tác dụng lặp trong cùng cửa sổ | Deduplication và idempotency độc lập với timestamp |
| Restore làm mất marker đã xử lý | Nhận lại sự kiện cũ như mới | Bảo toàn hoặc đối soát trạng thái chống lặp |
| Header thời gian nhận do client cung cấp | Bẻ mốc so sánh tại receiver | received_at phải do ranh giới tin cậy tạo |
| Request kéo dài để giữ mốc cũ | Mở rộng hiệu lực ngoài chủ đích | Giới hạn thời gian nhận và định nghĩa mốc nhận rõ ràng |

Một bất biến quan trọng:

> Không có webhook tạo tác dụng nghiệp vụ mới chỉ nhờ tự khai báo timestamp còn mới, vượt qua cửa sổ thời gian bằng field không được bảo vệ hoặc lợi dụng trạng thái chống lặp bị mất.

Webhook có chữ ký hợp lệ và còn trong cửa sổ cũng chưa mặc nhiên được phép thực hiện mọi tác vụ. Consumer vẫn cần kiểm tra nguồn, tenant, loại sự kiện và trạng thái nghiệp vụ.

### 3.1. Tài sản, tác nhân và ranh giới tin cậy

Tài sản cần bảo vệ là tính đúng đắn của trạng thái nghiệp vụ, quyền của nguồn gửi, bí mật khóa ký, bằng chứng tiếp nhận và trạng thái chống xử lý lặp. Với webhook thanh toán, thiệt hại cần ngăn là ghi có hoặc giao hàng nhiều lần, kể cả khi mọi bản gửi đều có chữ ký đúng.

Giả định kẻ tấn công có thể gọi endpoint công khai, lựa chọn body/header, gửi đồng thời nhiều bản, trì hoãn hoặc phát lại request từng bị lộ. Kẻ đó chưa có khóa ký của nguồn hợp lệ và chưa kiểm soát receiver. Nếu khóa hoặc receiver bị chiếm, timestamp không còn là biện pháp đủ để chứng minh nguồn hay thời điểm gửi; cần thu hồi, điều tra và phục hồi riêng.

```text
Nguồn gửi đã đăng ký
  [đồng hồ sender + quyền ký]
             |
             | HTTP qua TLS; request bên ngoài chưa đáng tin
             v
Ingress receiver
  [giới hạn nhận + mốc nhận + bằng chứng chất lượng đồng hồ]
             |
             v
Bộ xác minh
  [hợp đồng ký + khóa được phép + cửa sổ + phạm vi nguồn]
             |
             | chuyển qua ranh giới tiếp nhận nghiệp vụ khi đạt
             v
Inbox bền vững + outbox trong cùng giao dịch
             |
             | danh tính producer và quyền đọc/ghi queue được kiểm soát
             v
Worker + ràng buộc idempotency của thao tác nghiệp vụ
```

Mạng nội bộ và một queue riêng không tự tạo bằng chứng message đã được xác minh. Receiver phải kiểm soát ai được phát message, metadata nào do ingress tạo và metadata liên kết với body nào. TLS bảo vệ kết nối theo cấu hình triển khai; chữ ký bảo vệ phần thông điệp theo hợp đồng. Timestamp không mã hóa payload, không xác thực người nhận và không thay thế TLS.

### 3.2. Phân biệt độ mới, replay và tính duy nhất

- **Độ mới:** lần gửi nằm trong cửa sổ được phép so với mốc nhận đáng tin.
- **Replay:** đưa lại một thông điệp đã có nhằm tác động tới quyết định của receiver.
- **Deduplication:** nhận ra cùng một sự kiện/lần giao trong một phạm vi định danh.
- **Idempotency:** lặp cùng một ý định nghiệp vụ không tạo thêm tác dụng ngoài hợp đồng.

Timestamp làm hẹp thời gian replay có thể vượt kiểm tra độ mới, nhưng không ngăn replay ngay trong cửa sổ. Một nonce ngẫu nhiên cũng chỉ chống dùng lại khi receiver lưu và kiểm tra nó trong đúng phạm vi, với thao tác nguyên tử và retention đủ dài. Tính không đoán được của nonce không tự tạo tính duy nhất khi xử lý.

Với ngưỡng ví dụ, nếu timestamp đang đi trước receiver 30 giây, lần ký đó có thể còn đạt độ mới trong 330 giây tiếp theo theo đồng hồ receiver ổn định: từ delta = -30 đến delta = 300. Vì vậy, W_past = 300 không có nghĩa mọi thông điệp chỉ có thể được dùng lại trong tối đa 300 giây kể từ lần nhận đầu. Bất biến chống tác dụng lặp phải được thiết kế độc lập.

## 4. Hợp đồng timestamp và chữ ký

### 4.1. Hợp đồng minh họa

Giả sử một endpoint đăng ký với một nguồn gửi đã biết sử dụng:

```http
X-Example-Webhook-Time: 1800000000
X-Example-Webhook-Key-Id: key-02
X-Example-Webhook-Signature: <signature-by-contract>
```

Trong ví dụ:

- Timestamp là số nguyên thập phân biểu diễn giây từ mốc thời gian được hợp đồng quy định.
- Mỗi request có một giá trị timestamp theo grammar đã công bố.
- Key ID chỉ chọn trong tập khóa được phép của nguồn và endpoint đã đăng ký.
- Chữ ký bao phủ timestamp và đúng phần nội dung ứng dụng được quy định.
- Quy tắc ký, mã hóa và kiểm chứng được lấy từ hợp đồng, không do receiver tự thay.

Nếu một giao thức dùng mili giây, định dạng văn bản hoặc nhiều chữ ký khi rotation, phải đặc tả đúng các quy tắc đó. Yêu cầu một timestamp không có nghĩa mọi giao thức chỉ được có một chữ ký.

### 4.2. Dữ liệu được ký phải ràng buộc đúng ý nghĩa

Một mô hình khái niệm:

```text
signed_input = ContractEncode(
    delivery_timestamp,
    endpoint_or_audience_binding_if_required,
    delivery_identity_if_part_of_contract,
    exact_application_body_bytes
)

signature_valid = VerifyUsingApprovedProtocol(
    allowed_key,
    signed_input,
    received_signature
)
```

Đây là mô hình trách nhiệm, không phải đề xuất một thuật toán hoặc định dạng ký mới. Đầu vào cần được mã hóa không nhập nhằng theo giao thức, và receiver phải sử dụng cơ chế kiểm chứng được phê duyệt.

Nếu timestamp không nằm trong phần được xác thực, kẻ gửi lại có thể thay nó thành “bây giờ” mà không sửa nội dung cũ. Chỉ kiểm tra chữ ký của body rồi kiểm tra một header thời gian độc lập sẽ không đạt mục tiêu này.

### 4.3. Giữ đúng bytes cần kiểm chứng

Một JSON được parse rồi serialize lại có thể thay đổi thứ tự field, khoảng trắng hoặc cách biểu diễn số. Chữ ký tính trên bytes của hợp đồng có thể không còn khớp dù ý nghĩa JSON có vẻ giống nhau.

Cần xác định raw body ở đúng lớp ứng dụng theo giao thức ký. Đây không nhất thiết là toàn bộ bytes của gói HTTP trên mạng. Proxy, content encoding và middleware có thể thay đổi nội dung trước khi ứng dụng kiểm chứng.

Phải kiểm thử với cấu hình triển khai thật và các biến thể hợp lệ. Không tự chuẩn hóa body hoặc timestamp khác hợp đồng để “sửa” lỗi chữ ký.

### 4.4. Parse thời gian nghiêm ngặt

Đặc tả cần nêu:

- Tên và nguồn giá trị được sử dụng.
- Grammar, đơn vị, miền giá trị và quy tắc làm tròn.
- Cách xử lý giá trị thiếu, trùng hoặc xung đột.
- Giới hạn độ dài và chống tràn số.
- Trường hợp được phép có nhiều giá trị/chữ ký theo giao thức.
- Hành vi với giá trị không hợp lệ.

Không tự đoán một số dài là mili giây rồi chia cho 1.000 nếu hợp đồng yêu cầu giây. Không dùng số dấu phẩy động khi cần biểu diễn chính xác một miền số nguyên.

HTTP header có thể được xử lý khác nhau qua các lớp trung gian. Test phải bao phủ cách triển khai thực sự gộp, từ chối hoặc chuyển tiếp giá trị trùng, thay vì chỉ thử một request chuẩn.

## 5. Đặc tả cửa sổ chấp nhận

### 5.1. Dùng hai giới hạn có ý nghĩa riêng

Ký hiệu:

```text
t_signed   = timestamp đã được chữ ký xác thực
t_received = mốc nhận do receiver tạo tại ranh giới đáng tin
W_past     = độ trễ quá khứ tối đa được phép
W_future   = mức đi trước đồng hồ receiver tối đa được phép

delta = t_received - t_signed

Hợp lệ về độ mới khi:
    -W_future ≤ delta ≤ W_past
```

Trong ví dụ:

```text
W_past   = 300 giây
W_future = 30 giây
```

Giới hạn quá khứ xử lý độ trễ giao và rủi ro replay. Giới hạn tương lai xử lý chênh lệch đồng hồ và việc kéo dài hiệu lực bằng thời gian quá xa.

Không dùng mặc định `abs(delta) ≤ 300` nếu chính sách chỉ cho phép đi trước 30 giây. Cách kiểm tra đối xứng đó sẽ mở rộng dung sai tương lai ngoài thiết kế.

### 5.2. Ví dụ ranh giới

Giả sử mốc nhận tổng hợp trong bài thử là `1800000000` giây, và chữ ký, nguồn cùng các điều kiện khác đều hợp lệ:

| t_signed | delta | Kết quả kiểm tra độ mới |
| --- | --- | --- |
| 1800000000 | 0 giây | Đạt |
| 1799999700 | 300 giây | Đạt tại biên quá khứ |
| 1799999699 | 301 giây | Không đạt: quá cũ |
| 1800000030 | -30 giây | Đạt tại biên tương lai |
| 1800000031 | -31 giây | Không đạt: quá xa tương lai |

Các mốc trên là dữ liệu tổng hợp để kiểm tra phép tính, không gắn với ngày diễn tập thực tế.

Bảng dùng giá trị nguyên giây. Nếu receiver đo độ phân giải cao hơn, hợp đồng phải nêu cách quy đổi và kiểm tra ranh giới. Không để giao diện làm tròn che việc giá trị thực đã vượt giới hạn.

### 5.3. Chọn ngưỡng từ ngân sách và rủi ro

Cửa sổ cần dựa trên độ trễ giao có thể chấp nhận, sai lệch đồng hồ hai phía, thời gian nhận request, hành vi retry và mức rủi ro replay.

Nếu mỗi bên có biên sai lệch so với tham chiếu là 2 giây, chênh lệch giữa hai đồng hồ có thể tới 4 giây. Không dùng biên một máy như biên chênh lệch của cả cặp.

Quan hệ khái niệm:

```text
delta_quan_sát
    = tuổi_giao_theo_thời_gian_thực
      + sai_lệch_receiver
      - sai_lệch_sender
```

Ngưỡng 300/30 giây trong ví dụ là quyết định chính sách cần được chứng minh phù hợp. Nó không tự suy ra từ một giá trị NTP hoặc từ timeout HTTP.

Tăng cửa sổ có thể giảm loại nhầm nhưng cũng tăng khoảng có thể dùng lại thông điệp hợp lệ. Khi cần chịu gián đoạn dài, nên xem xét chính sách giao lại và kênh đối soát phù hợp, thay vì mở cửa sổ vô hạn.

### 5.4. Ví dụ lập ngân sách và tính chính xác ở biên

Giả sử hợp đồng nội bộ đặt mục tiêu tuổi lần giao khi nhận đủ body không quá 240 giây, biên sai lệch mỗi phía là 2 giây và dự phòng vận hành là 56 giây. Tổng ngân sách quá khứ là 240 + 2 + 2 + 56 = 300 giây. Đây là cách giải thích một lựa chọn minh họa; phải đo độ trễ thực tế và đánh giá phần ngoài mục tiêu trước khi áp dụng.

Với cùng giả định, mức chênh lệch đồng hồ thuần túy tối đa là 4 giây. Nếu vẫn chọn W_future = 30 giây, phần 26 giây còn lại là dung sai chính sách cần có lý do, không phải sai lệch đã được chứng minh của đồng hồ. Không cộng thêm một khoản clock skew lần nữa trong code khi ngân sách đã bao gồm nó.

Khi timestamp ký có đơn vị giây nhưng receiver có phần lẻ, ví dụ này so sánh thời gian chính xác, không cắt phần lẻ trước khi kiểm tra:

```text
t_signed = 1799999700 giây
received_at = 1800000000.000000000 → delta = 300 giây: đạt biên
received_at = 1800000000.000000001 → delta > 300 giây: quá cũ

t_signed = 1800000030 giây
received_at = 1800000000.000000000 → delta = -30 giây: đạt biên
received_at = 1799999999.999999999 → delta < -30 giây: quá xa tương lai
```

Một giao thức có thể quy định quy đổi khác, nhưng sender, receiver và bộ test phải dùng cùng quy tắc đã công bố. Không đổi đơn vị bằng cách đoán số chữ số, không dùng kiểu 32 bit cho timestamp và không lấy trị tuyệt đối của một phép trừ có nguy cơ tràn.

## 6. Xác định mốc nhận tại ranh giới đáng tin

### 6.1. Không lấy received_at từ bên gửi

Nếu client tự cung cấp thời gian “bên nhận đã nhận”, họ có thể bẻ phép so sánh. Mốc nhận phải do thành phần đáng tin của receiver tạo.

Trong ví dụ, `t_received` được ghi khi request body cần kiểm chứng đã được nhận đầy đủ tại ingress. Request có giới hạn kích thước và thời gian nhận theo hợp đồng.

Cách chọn này tránh việc ghi mốc từ byte đầu rồi cho phép client kéo dài truyền body quá lâu để giữ một timestamp còn mới. Nếu kiến trúc chọn mốc khác, phải chứng minh nó không mở thêm cửa sổ ngoài chủ đích.

Header thời gian do một proxy đáng tin tạo chỉ được dùng khi có ranh giới xác thực và cơ chế ngăn client tự chèn/ghi đè. Không mặc định mọi header mang tên “received” đều đáng tin.

### 6.2. Mốc nhận khác thời điểm chạy worker

Một kiến trúc có thể:

```text
Nhận đầy đủ request
    → ghi t_received đáng tin
    → xác minh chữ ký và cửa sổ
    → ghi nhận bền vững cùng trạng thái chống lặp
    → trả ACK tiếp nhận
    → worker xử lý sau
```

Nếu worker bắt đầu sau 20 phút, không nhất thiết áp lại cửa sổ 300 giây với đồng hồ hiện tại để loại một message đã được tiếp nhận hợp lệ. Cần sử dụng bằng chứng tiếp nhận theo hợp đồng nội bộ.

Bằng chứng đó phải được bảo vệ: đúng nguồn, endpoint, bytes hoặc định danh nội dung, timestamp đã xác minh, mốc nhận và kết quả kiểm tra. Worker không được tin một field `verified=true` do bên ngoài tự gửi vào queue.

Worker vẫn phải kiểm tra hiệu lực nghiệp vụ tại thời điểm chính sách yêu cầu. Một yêu cầu đã được tiếp nhận không có nghĩa thao tác vẫn được phép mãi mãi.

### 6.3. Kiểm tra tại lớp nào phải được nêu rõ

Nếu webhook chỉ được xác minh ở worker sau một queue chưa đáng tin, phải tính cả độ trễ và bảo vệ của queue trong thiết kế. Không công bố ngưỡng nhận 5 phút nhưng thực tế chờ vài giờ mới xác minh mà không có cơ chế tương ứng.

Một phản hồi tiếp nhận thành công phải gắn với điều kiện bền vững đã chọn. Không ACK rồi mới đặt công việc vào bộ nhớ dễ mất nếu hợp đồng yêu cầu không làm mất sự kiện.

## 7. Chất lượng đồng hồ và xử lý suy giảm

### 7.1. Đồng hồ receiver là một phụ thuộc bảo mật

Sai lệch của receiver có thể làm webhook cũ trông còn mới hoặc làm webhook hợp lệ bị loại hàng loạt. Cần quan sát offset, độ không chắc chắn và độ mới của bằng chứng đồng bộ theo thiết kế.

Ví dụ, dự án có thể chọn điều kiện khỏe là biên sai lệch receiver không quá 2 giây và mẫu đo không cũ quá 60 giây. Các giá trị này phải khả thi và phù hợp với cửa sổ được phê duyệt.

Một tiến trình đồng bộ đang chạy chưa chứng minh giờ đúng. UTC cũng chỉ là cách biểu diễn, không phải bằng chứng đồng hồ chính xác.

### 7.2. Không tự nới cửa sổ khi đồng hồ lỗi

Nếu sức khỏe thời gian không đủ tin cậy, cần chính sách rõ:

- Từ chối tạm thời và để bên gửi retry theo hợp đồng.
- Hoặc ghi nhận vào một vùng chờ an toàn, chưa cho tạo tác dụng nghiệp vụ, rồi xác minh theo quy trình được phê duyệt.
- Dùng kênh đối soát được xác thực nếu không thể giao lại trong giới hạn bình thường.

Không thay `t_signed` bằng “bây giờ”, bỏ kiểm tra chữ ký hoặc tự tăng W_past/W_future để làm hết lỗi.

Quy trình ngoại lệ cần phạm vi, người phê duyệt, thời hạn và audit. Không biến một sự cố đồng hồ thành đường chấp nhận webhook cũ vô thời hạn.

### 7.3. Giờ lịch và thời lượng

So sánh timestamp liên hệ thống cần nguồn thời gian lịch theo hợp đồng. Đo thời lượng nhận body, timeout hoặc retry nội bộ cần nguồn phù hợp của nền tảng, thường là đồng hồ đơn điệu khi có bảo đảm tương ứng.

Không dùng một giá trị đơn điệu trên máy này để so trực tiếp với timestamp lịch của bên gửi. Khi kiểm thử chỉnh giờ tiến/lùi, cần đánh giá cả quyết định độ mới lẫn timeout của request.

### 7.4. Lưu bằng chứng thời gian tại lúc nhận và giới hạn vùng chờ

Sức khỏe đồng hồ phải gắn với thời điểm tạo received_at. Một đồng hồ đã khỏe trở lại tại verified_at không chứng minh đồng hồ đúng khi request đến. Ingress cần chụp cả mốc nhận và bằng chứng chất lượng tương ứng, chẳng hạn tuổi mẫu đo cùng biên sai lệch mà nền tảng bảo đảm. Dùng đồng hồ đơn điệu phù hợp để đo tuổi mẫu giúp tránh việc chỉnh giờ lịch làm mẫu cũ trông mới.

Nếu thiếu bằng chứng đáng tin tại lúc nhận, không được giữ timestamp cũ rồi sau sự cố gắn nhãn “đã xác minh độ mới tại ingress”. Vùng chờ chỉ chứa dữ liệu chưa đủ điều kiện xử lý. Khi phục hồi, có thể xác minh lại bằng thời gian hiện tại đủ tin cậy nếu thông điệp vẫn trong cửa sổ; nếu đã quá cũ, phải yêu cầu lần giao mới hợp lệ hoặc đi qua kênh đối soát được xác thực và quy trình ngoại lệ. Không suy ngược received_at từ thời gian do bên gửi tự khai.

Ví dụ vùng chờ có giới hạn tổng dung lượng, số message theo nguồn và thời gian lưu tối đa 1 giờ, được mã hóa và phân quyền theo mức nhạy cảm dữ liệu. Hết thời hạn thì xóa/đối soát theo chính sách; thời gian lưu 1 giờ không mở cửa sổ độ mới thành 1 giờ. Không trả ACK mang nghĩa đã tiếp nhận nghiệp vụ nếu chỉ lưu vào vùng chờ, trừ khi hợp đồng định nghĩa rõ trạng thái riêng và trách nhiệm giao lại.

## 8. Retry, replay và chống tác dụng lặp

### 8.1. Retry hợp lệ phụ thuộc hợp đồng bên gửi

Có hai mô hình thường cần phân biệt:

| Mô hình | Ý nghĩa thiết kế |
| --- | --- |
| Mỗi lần giao có timestamp/chứng cứ thời gian mới | Sự kiện cũ có thể được giao lại bằng lần gửi mới, nhưng vẫn cần chống tác dụng lặp |
| Giữ nguyên timestamp/chữ ký của thông điệp ban đầu | Retry sau cửa sổ ngắn có thể không còn vượt kiểm tra độ mới |

Không thể tự sửa header thành thời điểm mới ở receiver để tương thích. Nếu không có quyền ký, việc đó phá ràng buộc xác thực; nếu bỏ kiểm tra để cho qua thì phá yêu cầu bảo mật.

Trước khi chốt cửa sổ, phải xác minh hành vi retry thực tế. Khi không tương thích, cần đổi hợp đồng, chọn phương án đã được bên gửi hỗ trợ hoặc dùng kênh tra cứu/đối soát được xác thực.

### 8.2. Thời gian không thay thế idempotency

Trong 300 giây, một webhook hợp lệ có thể được gửi lại nhiều lần. Cả hai bản đồng thời đều có thể vượt kiểm tra chữ ký và timestamp.

Cần một danh tính sự kiện/lệnh và cơ chế quyết định xử lý nguyên tử. Scope có thể gồm nguồn đã xác thực, endpoint hoặc tenant theo hợp đồng và event/business operation ID.

Không dùng event ID đơn lẻ trên toàn bộ hệ thống nếu các nguồn có thể trùng namespace. Không tin tenant trong payload để cho phép chiếm marker của tenant khác.

### 8.3. Marker và tiếp nhận bền vững

Nếu đánh dấu đã xử lý trước khi lưu công việc cần thiết, crash có thể làm mất sự kiện. Nếu tạo tác dụng rồi mới ghi marker ở bước tách rời, crash có thể gây lặp.

Cần ranh giới nhất quán cho trạng thái tiếp nhận, ý định xử lý và kết quả theo mô hình đã chọn. Với tác dụng bên ngoài, vẫn cần định danh ổn định và đối soát; một timestamp còn mới không bảo đảm thực hiện đúng một lần.

### 8.4. ACK cho duplicate và webhook ngoài cửa sổ

Một duplicate còn hợp lệ về nguồn và thời gian có thể nhận ACK theo hợp đồng, không tạo tác dụng mới. Phải kiểm tra quyền và nội dung liên kết trước khi trả kết quả chứa thông tin nhạy cảm.

Trong ví dụ mặc định, webhook ngoài cửa sổ không được tạo tiếp nhận nghiệp vụ mới. Nó bị xử lý theo hợp đồng lỗi hoặc quy trình đối soát, không tự chấp nhận vì field event ID giống một giá trị đã biết.

Nếu tích hợp cần ACK một delivery cũ đã được tiếp nhận hợp lệ trước đó, phải đặc tả riêng cách xác thực, đối chiếu nguồn/nội dung và ngăn làm sống lại tác dụng. Không tạo shortcut “event ID đã thấy thì bỏ qua mọi kiểm tra”.

### 8.5. Retention, nhiều replica và trùng ID khác nội dung

Marker phải được chia sẻ hoặc được phối hợp nhất quán giữa mọi replica có thể nhận cùng sự kiện. Cache cục bộ trên từng instance không ngăn hai instance cùng nhận lần đầu. Việc claim nên dựa vào một ràng buộc duy nhất có hiệu lực trong phạm vi xử lý, không phải chuỗi “đọc chưa thấy → ghi” không được bảo vệ.

Cần phân biệt hai thời hạn:

1. Marker của **một lần giao** phục vụ chống phát lại bản giao đó. Nếu muốn chặn toàn bộ các bản còn có thể đạt độ mới, thời hạn phải bao phủ phần cửa sổ còn lại, dung sai tương lai và giả định đồng hồ tương ứng.
2. Bất biến của **một thao tác nghiệp vụ** phải tồn tại theo thời hạn mà thao tác có thể được gửi lại, ký lại, phục hồi hoặc đối soát. Nó thường dài hơn cửa sổ timestamp và có thể được giữ bằng khóa duy nhất trong sổ nghiệp vụ.

Ví dụ nguồn retry trong 24 giờ và quy trình vận hành còn cho gửi bù trong 7 ngày: giữ marker 5 phút là không đủ. Có thể chọn inbox 8 ngày theo ngân sách được duyệt, trong khi ràng buộc “một giao dịch thanh toán chỉ được ghi có một lần” vẫn được duy trì trong sổ nghiệp vụ suốt vòng đời cần thiết. Retention inbox không tự thay thế thời hạn lưu dữ liệu và bảo vệ dữ liệu cá nhân.

Nếu cùng event ID xuất hiện với nội dung khác, không mặc nhiên coi đó là duplicate vô hại. Phải xác minh nguồn, đối chiếu phiên bản và dữ liệu nghiệp vụ theo hợp đồng, rồi từ chối xung đột hoặc áp dụng quy tắc cập nhật đã đặc tả. Hash bytes có thể phục vụ phát hiện khác biệt, nhưng hai lần serialize JSON cùng ý nghĩa có thể có hash khác; không dùng sự khác biệt bytes để tự suy ra một giao dịch mới được phép thực hiện.

## 9. Luồng xác minh và thứ tự quyết định

Một luồng khái niệm:

```text
handle_webhook(request):
    enforce_request_size_and_receive_deadline(request)
    raw_body = receive_exact_body_by_contract(request)
    receipt = capture_receipt_time_and_clock_health_at_body_completion()
    received_at = receipt.received_at

    endpoint = resolve_registered_endpoint_context(request)
    timestamp = parse_timestamp_strictly_by_contract(request)
    key = resolve_allowed_key(endpoint, request.key_id)

    verify_signature_by_contract(
        key,
        timestamp,
        raw_body,
        request.signature
    )

    require_receiver_time_health_at_receipt(receipt.time_health)
    require(-W_future <= received_at - timestamp <= W_past)

    event = parse_and_validate_authenticated_event(raw_body)
    validate_source_scope_tenant_and_event_policy(endpoint, event)

    outcome = atomically_record_or_find_existing_operation(
        verified_event = event,
        verified_timestamp = timestamp,
        trusted_received_at = received_at,
        receipt_time_health = receipt.time_health,
        content_binding = authenticated_content_reference
    )

    return documented_ack_or_error(outcome)
```

Đây là mã giả, không phải hướng dẫn gọi một SDK cụ thể. Các phép tính phải tránh tràn số và các giá trị ngoài miền.

Luồng có thể kiểm tra sơ bộ rẻ để giảm tải trước khi xác minh mật mã, nhưng không được coi dữ kiện chưa xác thực là bằng chứng một nguồn hợp lệ đang gửi webhook cũ. Audit và metric phải phân biệt request chưa xác thực với sự kiện đã xác thực nhưng ngoài cửa sổ.

Không xử lý tác dụng nghiệp vụ trước khi chữ ký, độ mới và các điều kiện bắt buộc đạt. Việc parse để biết kiểu không cho phép gọi dịch vụ hoặc cập nhật trạng thái theo payload chưa được tin.

### 9.1. Adapter HTTP, trạng thái xử lý và phản hồi

Adapter đứng trước bộ xác minh phải thu được đúng một timestamp và một chữ ký của hợp đồng ví dụ; header trùng, kể cả hai giá trị giống nhau, đều bị từ chối. Nếu proxy đã gộp giá trị bằng dấu phẩy, giá trị đó không được bộ parse ví dụ chấp nhận. Cần thử qua đúng proxy và web framework để bảo đảm duplicate không bị lặng lẽ chọn giá trị đầu/cuối.

Endpoint xác định nguồn, môi trường, audience mong đợi và danh mục Key ID từ cấu hình receiver. Key ID nhận từ request chỉ là gợi ý tra cứu có giới hạn trong danh mục đó, chưa chứng minh nguồn. Không cho client chọn thuật toán, đổi audience mong đợi hoặc tải khóa từ một URL tùy ý. Với MAC dùng khóa bí mật chung, mọi bên giữ khóa đều có khả năng tạo MAC; không coi MAC là bằng chứng chống chối bỏ giữa các bên cùng giữ khóa.

Các trạng thái cần được phân biệt: `REJECTED`, `UNVERIFIED_HOLD`, `ACCEPTED_PENDING` và `PROCESSED`. Chỉ `ACCEPTED_PENDING` đã có tiếp nhận bền vững mới được đi vào hàng xử lý nghiệp vụ bình thường. Một kết quả `FRESH` trong hàm kiểm tra chưa phải là `ACCEPTED_PENDING`.

| Kết quả | Phản hồi minh họa | Tác dụng/ghi nhận được phép |
| --- | --- | --- |
| Header/body sai cấu trúc, vượt giới hạn | 400 hoặc 413 theo loại lỗi | Không thêm công việc nghiệp vụ; audit lỗi với dữ liệu giới hạn |
| Nguồn/khóa không được phép, chữ ký sai | 401 với thông báo bên ngoài chung | Không xử lý; không tiết lộ khóa nào tồn tại hoặc nội dung bí mật |
| Chữ ký đúng nhưng quá cũ/quá xa tương lai | 400 theo hợp đồng ví dụ | Không tạo tiếp nhận mới; yêu cầu giao lại/đối soát đúng hợp đồng |
| Không đủ tin cậy về đồng hồ hoặc bộ kiểm chứng lỗi nội bộ | 503 | Không tạo tác dụng; retry theo ngân sách và hợp đồng nguồn gửi |
| Lưu inbox/outbox thất bại hoặc trạng thái commit chưa rõ | 503 hoặc kết thúc kết nối theo tình huống | Không tuyên bố đã tiếp nhận; lần retry phải đối chiếu trạng thái bền vững |
| Xác minh đạt, inbox/outbox đã commit | 202 | Tiếp nhận bền vững, worker xử lý sau |
| Duplicate hợp lệ, cùng ý định đã được tiếp nhận | 200 hoặc 204 | Không thêm tác dụng/lệnh nghiệp vụ tương ứng |
| Cùng danh tính nhưng nội dung xung đột với hợp đồng bất biến | 409 theo hợp đồng ví dụ | Không âm thầm ghi đè hoặc tạo tác dụng mới; lưu bằng chứng xung đột |

Đây là lựa chọn cho ví dụ, không phải bảng mã bắt buộc cho mọi nhà cung cấp. Trước khi chốt, phải xác nhận nguồn có retry với mã nào, giới hạn retry ra sao và bên nào chịu trách nhiệm đối soát. Không phân loại lỗi hạ tầng tạm thời thành thành công chỉ để ngừng retry.

### 9.2. Một hợp đồng ký hoàn chỉnh cho tích hợp nội bộ minh họa

Để biến signed input khái niệm thành ví dụ triển khai, giả sử hai dịch vụ nội bộ cùng thống nhất profile sau. Không dùng profile này thay cho giao thức ký của một nhà cung cấp đã có hợp đồng riêng.

| Thành phần | Quy tắc của profile ví dụ |
| --- | --- |
| Phiên bản và thuật toán | `v1`, HMAC-SHA-256 cố định; request không được chọn thuật toán |
| Timestamp | Giá trị ASCII khớp `[1-9][0-9]{0,9}`, Unix time theo giây; không dấu, không phần lẻ, không zero đầu, không khoảng trắng bên trong giá trị ứng dụng |
| Header | Đúng một `X-Example-Webhook-Time`, một `X-Example-Webhook-Key-Id` và một `X-Example-Webhook-Signature` |
| Audience | Chuỗi receiver cấu hình, ví dụ `payment-events/prod`; khớp `[a-z0-9/_-]{1,80}` |
| Key ID | Khớp `[A-Za-z0-9_-]{1,64}`; được tra trong tập khóa còn được phép của nguồn/endpoint/môi trường |
| Body | Đúng bytes UTF-8 ứng dụng được giao; profile không dùng content encoding biến đổi body; tối đa 1 MiB, nhận đầy đủ trong 10 giây |
| Signed input | ASCII của `v1`, timestamp nguyên dạng, audience và Key ID, mỗi phần kết thúc bằng LF; nối với toàn bộ bytes body |
| Chữ ký trên HTTP | Hex chữ thường, đúng 64 ký tự; so sánh MAC bằng hàm thư viện phù hợp thay cho so sánh chuỗi thông thường |
| Đồng hồ và cửa sổ | Mốc nhận đầy đủ body cùng bằng chứng sức khỏe tại lúc nhận; -30 <= delta <= 300 giây, bao gồm hai biên, không cắt phần lẻ receiver |
| Retry | Mỗi lần giao mới được ký lại với timestamp hiện hành của sender; event ID và ý định nghiệp vụ giữ ổn định |

Các field trước body bị giới hạn grammar nên không chứa LF; body là phần cuối, không cần parse để xác định ranh giới các field đứng trước. Sender và receiver phải dùng LF đúng một byte `0A`, không dùng quy tắc xuống dòng mặc định của hệ điều hành. Quy tắc loại bỏ HTTP optional whitespace ở lớp HTTP phải nhất quán qua các hop; ứng dụng không được tùy ý trim/chuyển dạng timestamp trước khi kiểm chứng.

Body được ký không được parse/serialize lại. Audience và Key ID cũng nằm trong MAC: một request ký cho `payment-events/staging` không trở thành request hợp lệ ở `payment-events/prod` bằng cách đổi endpoint. Dù vậy, vẫn phải tách khóa và quyền giữa các môi trường; không dựa riêng vào chuỗi audience.

### 9.3. Ví dụ Java kiểm chứng MAC và độ mới

Ví dụ dùng các API chuẩn của JDK 17. Hàm nhận raw body, Key ID đã tra được trong cấu hình receiver và khóa được phép tương ứng. `Receipt` phải do ingress tin cậy tạo cùng bằng chứng sức khỏe tại lúc nhận; không dựng record này từ header/payload do client khai báo.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Objects;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class WebhookTimestampExample {
    public enum Decision {
        MALFORMED, BAD_SIGNATURE, CLOCK_UNTRUSTED,
        TOO_OLD, TOO_FAR_IN_FUTURE, FRESH
    }

    public record Receipt(Instant receivedAt, boolean clockTrustedAtReceipt) {
        public Receipt {
            Objects.requireNonNull(receivedAt);
        }
    }

    private static final Duration MAX_AGE = Duration.ofSeconds(300);
    private static final Duration MAX_FUTURE = Duration.ofSeconds(30);
    private static final int MAX_BODY_BYTES = 1024 * 1024;

    public static Decision verify(
            String timestampValue, String signatureHex, byte[] rawBody,
            String expectedAudience, String allowedKeyId, SecretKey allowedKey,
            Receipt receipt) throws GeneralSecurityException {
        Objects.requireNonNull(receipt);
        Objects.requireNonNull(allowedKey);
        if (expectedAudience == null
                || !expectedAudience.matches("[a-z0-9/_-]{1,80}")
                || allowedKeyId == null
                || !allowedKeyId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid receiver configuration");
        }
        if (timestampValue == null
                || !timestampValue.matches("[1-9][0-9]{0,9}")
                || signatureHex == null
                || !signatureHex.matches("[0-9a-f]{64}")
                || rawBody == null || rawBody.length > MAX_BODY_BYTES) {
            return Decision.MALFORMED;
        }

        byte[] supplied = HexFormat.of().parseHex(signatureHex);
        byte[] expected = authenticate(
                allowedKey, timestampValue, expectedAudience, allowedKeyId, rawBody);
        if (!MessageDigest.isEqual(expected, supplied)) {
            return Decision.BAD_SIGNATURE;
        }
        if (!receipt.clockTrustedAtReceipt()) {
            return Decision.CLOCK_UNTRUSTED;
        }

        // Grammar bounds the number to 1..9_999_999_999 seconds.
        Instant signedAt = Instant.ofEpochSecond(Long.parseLong(timestampValue));
        Duration delta = Duration.between(signedAt, receipt.receivedAt());
        if (delta.compareTo(MAX_AGE) > 0) {
            return Decision.TOO_OLD;
        }
        if (delta.compareTo(MAX_FUTURE.negated()) < 0) {
            return Decision.TOO_FAR_IN_FUTURE;
        }
        return Decision.FRESH;
    }

    private static byte[] authenticate(
            SecretKey key, String timestamp, String audience, String keyId,
            byte[] body) throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        String prefix = "v1\n" + timestamp + "\n" + audience + "\n" + keyId + "\n";
        mac.update(prefix.getBytes(StandardCharsets.US_ASCII));
        return mac.doFinal(body);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        // Ephemeral test key; never a production credential.
        KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
        generator.init(256);
        SecretKey key = generator.generateKey();
        String audience = "payment-events/prod";
        String keyId = "test-key-02";
        String timestamp = "1799999700";
        byte[] body = "{\"event_id\":\"evt-demo-1\"}"
                .getBytes(StandardCharsets.UTF_8);
        String signature = HexFormat.of().formatHex(
                authenticate(key, timestamp, audience, keyId, body));
        Instant received = Instant.ofEpochSecond(1800000000L);

        expect(Decision.FRESH, verify(timestamp, signature, body, audience,
                keyId, key, new Receipt(received, true)));
        expect(Decision.TOO_OLD, verify(timestamp, signature, body, audience,
                keyId, key, new Receipt(received.plusNanos(1), true)));
        expect(Decision.BAD_SIGNATURE, verify("1800000000", signature, body,
                audience, keyId, key, new Receipt(received, true)));
        expect(Decision.CLOCK_UNTRUSTED, verify(timestamp, signature, body,
                audience, keyId, key, new Receipt(received, false)));
        expect(Decision.MALFORMED, verify("1800000000000", signature, body,
                audience, keyId, key, new Receipt(received, true)));
        String futureTimestamp = "1800000030";
        String futureSignature = HexFormat.of().formatHex(
                authenticate(key, futureTimestamp, audience, keyId, body));
        expect(Decision.FRESH, verify(futureTimestamp, futureSignature, body,
                audience, keyId, key, new Receipt(received, true)));
        expect(Decision.TOO_FAR_IN_FUTURE, verify(futureTimestamp,
                futureSignature, body, audience, keyId, key,
                new Receipt(received.minusNanos(1), true)));
        byte[] changedBody = "{\"event_id\":\"evt-demo-2\"}"
                .getBytes(StandardCharsets.UTF_8);
        expect(Decision.BAD_SIGNATURE, verify(timestamp, signature, changedBody,
                audience, keyId, key, new Receipt(received, true)));
        expect(Decision.BAD_SIGNATURE, verify(timestamp, signature, body,
                "payment-events/staging", keyId, key, new Receipt(received, true)));
        System.out.println("Nine timestamp verifier examples passed");
    }

    private static void expect(Decision wanted, Decision actual) {
        if (wanted != actual) {
            throw new IllegalStateException("Expected " + wanted + ", got " + actual);
        }
    }
}
```

`Duration` giữ phần lẻ của `receivedAt`, nên 300 giây cộng 1 nanosecond không bị cắt thành 300 giây. Grammar giới hạn giá trị trước `Long.parseLong`; không thử parse một chuỗi vô hạn rồi mới kiểm tra lỗi tràn. Chữ ký đúng phải được xác nhận trước khi ghi kết luận “nguồn đã xác thực gửi timestamp quá cũ”. Lỗi của thư viện mật mã hoặc cấu hình khóa phải đi vào luồng lỗi hạ tầng, không được catch rồi trả `FRESH`.

Hàm này chỉ minh họa lớp xác minh, chưa thực hiện adapter HTTP, thu body có deadline, đánh giá nguồn thời gian, phân quyền nghiệp vụ, inbox/outbox hay idempotency. Phải hoàn thành các lớp đó trước khi biến `FRESH` thành tiếp nhận nghiệp vụ. Phần `main` tạo fixture tổng hợp và kiểm tra chín trường hợp; kết quả chạy mẫu không thay thế kiểm thử qua proxy, nhiều replica và DB thật.

### 9.4. Ví dụ xuyên suốt: webhook thanh toán và retry

Giả sử endpoint `payment-events/prod` nhận sự kiện `evt-demo-1` cho thao tác `credit/pay-demo-1`. `event_occurred_at = 1799990000`, timestamp lần gửi `1799999990` và mốc nhận đáng tin `1800000000`; delta = 10 giây. Sự kiện nghiệp vụ đã cũ hơn nhiều nhưng lần giao vẫn đạt độ mới. Receiver còn phải kiểm tra thanh toán có thật, nguồn/tenant được phép và trạng thái thanh toán cho phép ghi có.

Receiver ghi inbox với phạm vi `(authenticated_source, registered_endpoint, authorized_tenant, event_id)` và liên kết tới thao tác nghiệp vụ ổn định. Khi chưa có bản ghi, nó tạo inbox cùng ý định outbox trong một giao dịch; chỉ sau commit mới trả 202. Khi đã có bản ghi, nó đối chiếu nội dung/phiên bản theo hợp đồng rồi trả ACK duplicate mà không tạo lại ý định tương ứng. Với hai request cạnh tranh, ràng buộc duy nhất của DB quyết định ai tạo bản ghi đầu tiên.

| Lượt | Dữ kiện | Quyết định và bằng chứng cần thấy |
| --- | --- | --- |
| A | Nhận lần đầu ở 1800000000, signed_at = 1799999990 | Delta 10; sau khi mọi guard đạt, một inbox và một ý định outbox được commit |
| B | Phát lại nguyên bản ở 1800000030 | Delta 40 vẫn đạt độ mới; duplicate không thêm ý định hay khoản ghi có |
| C | Phát lại nguyên bản ở 1800000330 | Delta 340; từ chối tiếp nhận mới theo chính sách ngoài cửa sổ, dù đã biết event ID |
| D | Sender ký lại cùng sự kiện với signed_at = 1800000360, receiver nhận ở 1800000363 | Delta 3; xác thực/độ mới đạt nhưng guard theo event/operation vẫn chặn tác dụng lặp |
| E | Kẻ phát lại tự đổi timestamp thành 1800000360, giữ chữ ký của A | MAC sai; không coi đây là một lần giao hợp lệ mới |
| F | Worker của A bắt đầu ở 1800001200 | Dùng bằng chứng tiếp nhận hợp lệ ở A; kiểm tra trạng thái nghiệp vụ hiện hành, không loại chỉ vì queue chờ 20 phút |

Worker dùng khóa nghiệp vụ ổn định cho `credit/pay-demo-1`. Nếu ghi có trong cùng DB, ràng buộc duy nhất và cập nhật trạng thái phải nằm trong giao dịch phù hợp. Nếu gọi hệ thống bên ngoài, cần idempotency mà phía đích hỗ trợ và đối soát khi kết quả chưa rõ; việc commit inbox/outbox không tự bảo đảm tác dụng bên ngoài diễn ra đúng một lần.

Crash sau commit nhưng trước ACK khiến sender retry; retry phải tìm thấy bản tiếp nhận đã lưu. Crash trước commit không được để lại ACK đã tiếp nhận. Crash sau khi tác dụng ngoài đã xảy ra nhưng trước khi lưu kết quả phải đi qua tra cứu/đối soát hoặc retry với cùng khóa idempotency, không tạo một operation ID mới.

## 10. Logging, cảnh báo, khóa và phục hồi

### 10.1. Dữ liệu cần quan sát

Có thể ghi hoặc tổng hợp:

- Nguồn/endpoint đã đăng ký và kết quả xác thực.
- Key ID không phải bí mật, nếu phù hợp chính sách.
- Timestamp nhận được, mốc nhận đáng tin và delta theo phạm vi được phép.
- Lý do từ chối: sai cấu trúc, sai chữ ký, quá cũ, quá xa tương lai hoặc thời gian receiver không đáng tin.
- Event/operation reference, duplicate và kết quả tiếp nhận.
- Sức khỏe đồng hồ, độ trễ ingress và queue nội bộ.

Không ghi secret ký, chữ ký có thể tái sử dụng kèm đầy đủ payload, hoặc body nhạy cảm vào log thông thường. Metric cần giới hạn cardinality; không dùng mọi event ID làm một nhãn riêng.

### 10.2. Phân biệt nguồn lỗi

Tăng đột biến webhook quá cũ có thể do sự cố mạng, retry không tương thích, đồng hồ sender sai hoặc replay. Không kết luận tất cả đều là tấn công.

Timestamp tương lai có thể do sender đi trước, receiver đi sau hoặc request bị giả. Cần đối chiếu xác thực, sức khỏe thời gian và cấu hình.

Cảnh báo phải có ngưỡng, thời hạn và người xử lý. Không tự sửa cửa sổ để giảm số lỗi mà không đánh giá lại rủi ro.

### 10.3. Rotation và thu hồi khóa

Một timestamp trong cửa sổ không làm khóa hết hiệu lực trở lại hợp lệ. Receiver chỉ được dùng tập khóa và điều kiện chấp nhận theo chính sách tích hợp.

Nếu có nhiều chữ ký trong giai đoạn rotation, phải hỗ trợ đúng số lượng và cách chọn được quy định, đồng thời giới hạn công việc kiểm chứng. Không tải khóa từ đường dẫn hoặc URL tùy ý do Key ID chỉ định.

Quy tắc với sự kiện lưu lâu và khóa cũ phải được nêu rõ. Không dùng thời gian do bên gửi tự khai báo làm bằng chứng duy nhất rằng thông điệp đã được ký trước lúc khóa bị thu hồi.

### 10.4. Restore và marker chống lặp

Sau restore, đồng hồ, cấu hình cửa sổ, tập khóa, trạng thái endpoint và marker phải được kiểm tra trước khi mở tiếp nhận hoặc chạy lại queue.

Không chỉ dựa vào cửa sổ 300 giây để ngăn mọi tác dụng lặp: một sự kiện cũ có thể được bên gửi ký lại với timestamp mới. Bất biến nghiệp vụ và trạng thái đã xử lý vẫn phải được bảo toàn hoặc đối soát.

## 11. Bộ yêu cầu bảo mật minh họa

Các yêu cầu sau áp dụng cho một endpoint nhận sự kiện nhỏ theo hợp đồng đã mô tả. Giá trị 300 giây quá khứ, 30 giây tương lai, ngân sách đồng hồ và giới hạn request phải được phê duyệt trước khi dùng trong hệ thống thực.

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| WHT-01 | Hợp đồng phải chỉ rõ field/header thời gian, ý nghĩa, đơn vị, grammar, cơ chế ký, hành vi retry và phạm vi endpoint/nguồn gửi. | Tích hợp/chủ dịch vụ | Tài liệu tích hợp và mẫu request được kiểm chứng; không suy metadata từ một field có tên gần giống. |
| WHT-02 | Timestamp dùng cho độ mới phải nằm trong dữ liệu được xác thực cùng nội dung theo đúng giao thức; sửa thời gian hoặc body không được giữ kết quả xác minh hợp lệ. | Bảo mật/ứng dụng | Thay timestamp, body và ngữ cảnh ràng buộc theo hợp đồng; chữ ký không còn được chấp nhận. |
| WHT-03 | Parse phải đúng đơn vị, miền và quy tắc trùng; đầu vào sai định dạng/tràn số hoặc timestamp xung đột không được tự sửa thành hợp lệ. | Chủ API | Test giây/mili giây, số quá dài, giá trị thiếu/trùng và xử lý qua proxy/middleware. |
| WHT-04 | Trong ví dụ, chỉ đạt kiểm tra độ mới khi -30 ≤ received_at - signed_at ≤ 300 giây; quy tắc biên và làm tròn phải nhất quán. | Ứng dụng/bảo mật | Test bằng, ngay trong và ngay ngoài cả hai biên; chữ ký sai vẫn bị chặn dù thời gian trong cửa sổ. |
| WHT-05 | received_at phải do ranh giới tin cậy tạo khi nhận đủ body; request của endpoint ví dụ tối đa 1 MiB và thời gian nhận tối đa 10 giây tại cổng đã chỉ định. | Nền tảng/chủ API | Client không ghi đè mốc; request vượt ngân sách bị xử lý đúng, không giữ hiệu lực bằng truyền kéo dài. |
| WHT-06 | Receiver phải đánh giá sức khỏe thời gian; trong ví dụ, biên sai lệch không quá 2 giây và mẫu không cũ quá 60 giây. Thiếu tin cậy không được tự nới cửa sổ hoặc bỏ kiểm tra. | Nền tảng/bảo mật | Tiêm lệch giờ, mất mẫu và chỉnh giờ; chuyển sang hành vi suy giảm được duyệt, không tạo tác dụng mù. |
| WHT-07 | Cửa sổ phải tương thích với retry thực tế; receiver không thay timestamp hoặc xác thực lại một lần gửi bằng cách tự làm mới thông điệp bên ngoài. | Tích hợp | Retry ký mới và retry giữ nguyên chữ ký được phân biệt; trường hợp ngoài cửa sổ đi đúng luồng lỗi/đối soát. |
| WHT-08 | Nếu xác minh tại ingress rồi xử lý sau, bằng chứng tiếp nhận và nội dung liên kết phải bền vững, được bảo vệ; queue không cho bên ngoài tự khai đã xác minh. | Ứng dụng/nền tảng | Trì hoãn worker, sửa metadata nội bộ và thử message giả; không tin verified flag tự khai hoặc loại nhầm chỉ vì chờ queue. |
| WHT-09 | Webhook còn mới nhưng lặp phải tuân thủ idempotency và ràng buộc nghiệp vụ; claim/marker/ý định xử lý phải có tính nhất quán phù hợp. | Ứng dụng/dữ liệu | Gửi đồng thời, đổi delivery ID cho cùng operation và crash tại điểm ghi; không mất việc hoặc tạo tác dụng bị cấm. |
| WHT-10 | Tập khóa, Key ID, rotation và thu hồi phải được kiểm soát; timestamp hợp lệ không làm khóa không còn được phép trở lại hợp lệ. | Bảo mật/tích hợp | Test khóa sai phạm vi, khóa cũ, nhiều chữ ký đúng hợp đồng và Key ID ngoài danh mục. |
| WHT-11 | Không có tiếp nhận nghiệp vụ mới hoặc tác dụng nhạy cảm trước khi nguồn, chữ ký, độ mới và guard bắt buộc đạt; ACK phản ánh đúng mức tiếp nhận bền vững. | Chủ dịch vụ | Test từng bước không đạt; đối chiếu DB, queue, phản hồi và tác dụng thực tế, không chỉ mã HTTP. |
| WHT-12 | Audit/metric phải phân biệt lỗi cấu trúc, xác thực, quá cũ, tương lai và đồng hồ receiver; không ghi secret hoặc dữ liệu có thể tái sử dụng ngoài chính sách. | Vận hành/bảo mật | Log/trace đủ liên kết và không lộ dữ liệu; request chưa xác thực không bị ghi như nguồn hợp lệ đã được chứng minh. |
| WHT-13 | Phải có ngưỡng, thời hạn cảnh báo và chủ xử lý cho lỗi đồng hồ, độ mới bất thường, backlog và mất khả năng quan sát; quá tải không làm giảm kiểm tra. | Vận hành/nền tảng | Tiêm lỗi và tải vượt ngân sách; cảnh báo đúng hạn, request không đi vào fallback thiếu bảo vệ. |
| WHT-14 | Thay cửa sổ, định dạng ký, middleware, khóa, retry hoặc restore phải kiểm tra lại hợp đồng, đồng hồ, endpoint và trạng thái chống lặp trước mở xử lý. | Chủ dịch vụ | Bằng chứng regression và đối soát sau thay đổi; không replay mù hoặc mở lại nguồn/khóa đã thu hồi. |

Các yêu cầu bổ sung dưới đây làm rõ ranh giới triển khai và phục hồi; chúng được truy vết tới kiểm thử mở rộng ở mục 12.4.

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| WHT-15 | Request phải gắn với đúng nguồn/endpoint/môi trường và tenant được phép. Theo profile 9.2, audience cùng Key ID phải nằm trong MAC, audience mong đợi lấy từ cấu hình receiver. | Tích hợp/bảo mật | Chuyển request hợp lệ sang endpoint/môi trường khác, đổi audience hoặc Key ID; không tạo tiếp nhận trái phạm vi dù thời gian còn mới. |
| WHT-16 | Marker phải có phạm vi và claim nhất quán giữa các replica; tài liệu phải nêu thời hạn chống lặp delivery và thời hạn bất biến nghiệp vụ. Cùng ID khác nội dung phải có quyết định xung đột rõ ràng. | Ứng dụng/dữ liệu | 100 request đồng thời qua ít nhất hai replica chỉ tạo một tiếp nhận cho cùng event; xóa cache cục bộ không phá ràng buộc; fixture ký mới sau TTL không lặp nghiệp vụ. |
| WHT-17 | Bằng chứng sức khỏe thời gian phải áp dụng tại lúc tạo received_at, được lưu liên kết với nội dung và không lấy từ request. Đồng hồ khỏe sau sự cố không tự hợp thức hóa mốc nhận chưa được tin. | Nền tảng/ứng dụng | Giả header thời gian/sức khỏe, thay bằng chứng hoặc cho đồng hồ phục hồi trước khi worker chạy; không tạo kết luận tiếp nhận hợp lệ giả. |
| WHT-18 | Nếu có vùng chờ chưa xác minh: ví dụ tối đa 1 GiB và 10.000 message cho một tích hợp, thời gian chờ tối đa 1 giờ. Hết giờ không còn được đưa sang nghiệp vụ; giải phóng dữ liệu hết hạn trong 60 giây, theo chính sách lưu bằng chứng. Không tự nới cửa sổ hoặc đổi timestamp để thoát vùng chờ. | Nền tảng/vận hành | Cả giới hạn dung lượng/số lượng/thời gian có hiệu lực; request vượt quota đi đúng luồng quá tải; dữ liệu hết hạn không chạy và được xử lý đúng thời hạn. |

Với WHT-13, một cấu hình minh họa là đánh giá sức khỏe thời gian mỗi 30 giây và gửi cảnh báo trong 2 phút từ lúc phát hiện điều kiện không đạt. Điều này không cho phép tiếp tục tạo tác dụng trong 2 phút khi quyết định đã thiếu bằng chứng tin cậy.

Cảnh báo và chặn tại điểm thực thi là hai yêu cầu khác nhau. Có cảnh báo đúng không biến một webhook bị chấp nhận ngoài chính sách thành đạt.

### 11.1. Mẫu đặc tả chi tiết cho cửa sổ thời gian

```text
ID: WHT-04
Mục tiêu: giới hạn chấp nhận lại một lần gửi đã được xác thực
Rủi ro: R-WEBHOOK-02 — thông điệp cũ hoặc quá xa tương lai được dùng lại
Phạm vi: endpoint nhận sự kiện đã đăng ký, theo hợp đồng timestamp giây
Nguồn signed_at: timestamp nằm trong phần được chữ ký bảo vệ
Nguồn received_at: receiver ghi khi nhận đủ body tại ingress đáng tin
Điều kiện:
  - Chữ ký và nguồn đạt
  - Đồng hồ receiver đủ tin cậy
  - -30 <= received_at - signed_at <= 300 giây
  - Parse và phép tính không tràn, làm tròn theo quy tắc đã định
Không đạt:
  - Không tạo tiếp nhận nghiệp vụ mới theo luồng bình thường
  - Phản hồi/đối soát theo hợp đồng tích hợp
  - Ghi lý do phân loại mà không lộ dữ liệu nhạy cảm
Chủ sở hữu: đội ứng dụng, phối hợp đội bảo mật và tích hợp
Kiểm thử: T-WHT-01, T-WHT-02, T-WHT-03, T-WHT-06
Bằng chứng: fixture ký, mốc nhận, delta, quyết định và tác dụng
```

Mẫu này chỉ đặc tả độ mới của lần gửi. Nguồn được phép thực hiện sự kiện nào và thao tác có còn hợp lệ về nghiệp vụ vẫn là yêu cầu bổ sung.

## 12. Ma trận kiểm thử nghiệm thu

Sử dụng môi trường kiểm soát, khóa thử và payload tổng hợp. Bộ kiểm thử cần kiểm soát được timestamp ký, đồng hồ receiver và điểm nhận, đồng thời ghi bằng chứng tác dụng thực tế.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-WHT-01 | Ký một request hợp lệ rồi sửa timestamp, body hoặc field thuộc ràng buộc của giao thức. | Không chấp nhận kết quả xác minh cũ; không xử lý theo nội dung đã bị thay. | WHT-01, 02 |
| T-WHT-02 | Với chữ ký hợp lệ và received_at cố định, thử delta 299, 300 và 301 giây. | Đạt ở 299/300, không đạt ở 301 theo hợp đồng ví dụ; làm tròn không làm sai biên. | WHT-04 |
| T-WHT-03 | Thử delta -29, -30 và -31 giây, thêm delta 0 nhưng chữ ký sai. | Đạt độ mới ở -29/-30; -31 bị chặn; chữ ký sai không được cho qua dù delta 0. | WHT-02, 04 |
| T-WHT-04 | Thiếu timestamp, timestamp trùng/xung đột, nhầm mili giây, số quá dài, giá trị ngoài grammar và biến thể proxy. | Từ chối hoặc xử lý đúng giao thức; không tự đoán/chuyển đơn vị hoặc nhận giá trị khác nhau giữa các lớp. | WHT-03 |
| T-WHT-05 | Body có cùng ý nghĩa JSON nhưng bytes khác, middleware đổi encoding/nội dung và các biến thể hợp lệ của giao thức. | Kiểm chứng trên đúng bytes/định dạng hợp đồng; không serialize lại để vô tình chấp nhận sai hoặc loại không đúng. | WHT-01, 02, 14 |
| T-WHT-06 | Receiver lệch tiến/lùi, biên không chắc chắn vượt mức, mẫu đồng bộ quá tuổi hoặc mất. | Không tiếp tục quyết định bằng thời gian không đủ tin cậy; không tự mở rộng W_past/W_future. | WHT-04, 06 |
| T-WHT-07 | Giả received_at trong header, kéo dài nhận body và gửi payload vượt 1 MiB theo fixture. | Không ghi đè mốc đáng tin; giới hạn nhận có hiệu lực, không giữ webhook còn mới bằng truyền kéo dài. | WHT-05 |
| T-WHT-08 | Retry một sự kiện cũ bằng timestamp/chữ ký mới hợp lệ; ở lượt khác giữ nguyên lần ký đã ngoài cửa sổ. | Phân biệt thời gian sự kiện và lần gửi; lần mới còn phải qua idempotency/guard, lần cũ không tự được làm mới. | WHT-07, 09 |
| T-WHT-09 | Tiếp nhận hợp lệ rồi trì hoãn worker 20 phút; thử đưa message có verified flag giả vào queue. | Bằng chứng ingress hợp lệ được dùng đúng; message tự khai không được tin; hiệu lực nghiệp vụ vẫn kiểm tra riêng. | WHT-08, 11 |
| T-WHT-10 | Gửi cùng webhook còn mới đồng thời, delivery ID khác cho cùng operation và event ID trùng giữa nguồn khác. | Scope và claim nguyên tử đúng; không tạo tác dụng lặp hoặc chiếm marker của nguồn/tenant khác. | WHT-09 |
| T-WHT-11 | Crash trước/sau ghi marker, ý định queue, ACK và commit theo từng lượt. | Không ACK quá mức bền vững; không mất việc hoặc tạo tác dụng lặp do trạng thái một phần. | WHT-08, 09, 11 |
| T-WHT-12 | Rotation khóa, khóa sai nguồn/endpoint, khóa đã thu hồi và nhiều chữ ký theo hợp đồng. | Chỉ dùng tập khóa/điều kiện được phép; timestamp còn mới không cứu khóa trái policy. | WHT-10 |
| T-WHT-13 | Tăng lỗi quá cũ/tương lai, ngắt quan sát thời gian và tạo tải request không hợp lệ. | Phân loại đúng, cảnh báo đúng hạn, không lộ bí mật hoặc bỏ kiểm tra để giảm tải. | WHT-12, 13 |
| T-WHT-14 | Restore cấu hình, khóa, marker và queue; gửi lại sự kiện đã xử lý với một lần ký mới hợp lệ. | Không phụ thuộc riêng vào cửa sổ để chống lặp; đối soát giữ đúng kết quả và nguồn/khóa hiện hành. | WHT-09, 14 |

### 12.1. Kiểm thử retry cần đúng hành vi tích hợp

Không giả lập bên gửi luôn ký mới nếu thực tế họ giữ chữ ký cũ. Cũng không ép mọi retry của bên ký mới dùng timestamp sự kiện ban đầu.

Bài nghiệm thu phải ghi rõ giả định về lịch retry, điều gì được ký lại và điều gì giữ nguyên. Nếu chưa có thông tin đủ, chưa thể kết luận cửa sổ đáp ứng mọi delivery hợp lệ.

### 12.2. Đối chiếu cả quyết định và tác dụng

HTTP 2xx có thể chỉ nghĩa đã tiếp nhận, còn 4xx/5xx không tự chứng minh chưa có thay đổi nếu hệ thống đã xử lý trước khi trả lỗi.

Cần kiểm tra DB, queue, marker, audit và tác dụng ngoài theo phạm vi. Một webhook bị ghi là “stale” nhưng vẫn được đưa vào hàng xử lý nghiệp vụ là vi phạm, dù response lỗi đúng.

### 12.3. Bằng chứng cần lưu

Báo cáo nên gồm phiên bản ứng dụng, hợp đồng ký, cấu hình cửa sổ, middleware, nguồn thời gian, fixture, timestamp, mốc nhận, delta và kết quả thực tế.

Khóa thử và thông điệp thử phải được quản lý để không trở thành credential production. Không đưa secret hoặc payload thật vào báo cáo chỉ để chứng minh phép tính.

### 12.4. Kiểm thử mở rộng cho profile và trạng thái tiếp nhận

| Test ID | Fixture/điều kiện | Tiêu chí đạt và truy vết |
| --- | --- | --- |
| T-WHT-15 | Ký đúng; kiểm tra delta tại 300 giây, 300 giây + 1 ns, -30 giây và -30 giây - 1 ns. | Chỉ hai giá trị đúng biên đạt; không cắt phần lẻ receiver hoặc dùng sai bất đẳng thức. WHT-03, 04. |
| T-WHT-16 | Giữ body/time/signature, đổi audience mong đợi sang staging; ở lượt khác chuyển sang nguồn/endpoint không được cấp cùng khóa hoặc sửa Key ID. | Không tiếp nhận trái phạm vi; MAC không xác minh ở audience khác theo profile, Key ID không mở tra cứu ngoài danh mục. WHT-02, 10, 15. |
| T-WHT-17 | Gửi 100 bản hợp lệ cùng event qua ít nhất hai replica; sau đó restart một replica và gửi lại trong cửa sổ. | Một inbox/ý định nghiệp vụ tương ứng được tạo; duplicate không tạo thêm tác dụng. Chứng minh bằng DB và hệ thống đích, không chỉ đếm HTTP 2xx. WHT-09, 11, 16. |
| T-WHT-18 | Cùng ID với dữ liệu nghiệp vụ khác và MAC mới hợp lệ; lượt khác dùng delivery/event mới nhưng cùng operation đã hoàn tất. | Xung đột được phân loại theo hợp đồng, không âm thầm ghi đè; cùng operation không tạo thêm tác dụng bị cấm. WHT-09, 16. |
| T-WHT-19 | Tạo request khi bằng chứng đồng hồ receiver không đạt; đồng hồ phục hồi trước lúc xử lý. Thử thay metadata received_at hoặc clock health trong message. | Không gắn nhãn đã xác minh tại ingress cho lần nhận thiếu tin cậy; metadata giả bị chặn; chỉ đi tiếp bằng xác minh/đối soát được phép. WHT-06, 08, 17. |
| T-WHT-20 | Thử timestamp có zero đầu, dấu +, khoảng trắng ứng dụng, dấu thập phân, ký tự Unicode nhìn giống chữ số, 13 chữ số mili giây; thử dùng CRLF thay LF trong signed input. | Profile từ chối grammar không hợp lệ; thay bytes trong signed input không giữ MAC hợp lệ; không sửa đầu vào để cho qua. WHT-01, 02, 03. |
| T-WHT-21 | Nạp vùng chờ đến từng quota; thử đọc message sau 1 giờ và quan sát dọn dẹp trong 60 giây tiếp theo. | Không có đường chạy nghiệp vụ của message hết hạn, không vượt quota đã chọn, dọn dữ liệu đúng hạn; lưu bằng chứng theo chính sách không làm sống lại quyền xử lý. WHT-13, 18. |
| T-WHT-22 | Fixture có MAC/thời gian đúng nhưng tenant không được nguồn/endpoint cho phép; lượt khác làm kho inbox hoặc thư viện mật mã lỗi. | Không xử lý nghiệp vụ của tenant sai; lỗi phụ thuộc không biến thành `FRESH`/ACK tiếp nhận thành công; audit phân loại đúng. WHT-10, 11, 12, 15. |

Kiểm thử T-WHT-16 cần tách các biến thể. Dùng đúng khóa thử nhưng đổi audience kiểm tra ràng buộc mật mã; dùng khóa/Key ID không thuộc phạm vi kiểm tra quyền tra cứu. Một lỗi bị chặn ở lớp đầu chưa chứng minh mọi lớp còn lại đều hoạt động đúng.

### 12.5. Acceptance criteria theo Given–When–Then

**AC-01 — Biên quá khứ và không có tác dụng sớm.** Given một endpoint đã đăng ký, khóa thử được phép, body hợp lệ và MAC đúng cho signed_at = 1799999700; đồng hồ receiver khỏe tại received_at = 1800000000. When receiver nhận và xác minh. Then độ mới đạt đúng biên; chỉ sau khi guard nghiệp vụ đạt và inbox/outbox commit mới trả 202. Trước worker, fixture có một inbox, một ý định outbox và chưa ghi có. Nếu chỉ đổi received_at thành 1800000000 cộng 1 ns, Then từ chối vì quá cũ, không tạo inbox/outbox nghiệp vụ mới.

**AC-02 — Biên tương lai.** Given MAC đúng cho signed_at = 1800000030. When receiver có mốc nhận 1800000000 với bằng chứng đồng hồ đạt. Then độ mới đạt. When mốc nhận là 1799999999.999999999 trong fixture độc lập. Then từ chối vì quá xa tương lai; không làm tròn thành giá trị đạt.

**AC-03 — Sửa thời gian và replay nhanh.** Given bản gửi A ở ví dụ 9.4. When sửa timestamp nhưng giữ MAC. Then từ chối xác thực và không tạo tác dụng. When phát lại nguyên bản khi delta vẫn trong cửa sổ. Then độ mới có thể đạt nhưng cơ chế chống lặp chỉ cho một ý định nghiệp vụ; worker và đích nhận phải chứng minh kết quả theo khóa operation, không theo số lần giao.

**AC-04 — Queue chậm và nghiệp vụ hết hạn.** Given đã có tiếp nhận bền vững cùng bằng chứng ingress đúng ở A. When worker chạy muộn 20 phút. Then không loại chỉ vì tuổi tính lại vượt 300 giây. Nếu thao tác đã hết hiệu lực theo chính sách nghiệp vụ, Then không thực hiện tác dụng đó; ghi kết quả nghiệp vụ riêng với lỗi xác thực/độ mới của lần giao.

**AC-05 — Lỗi đồng hồ và phục hồi.** Given mẫu đồng bộ quá tuổi hoặc biên sai lệch không đạt tại lúc nhận. When request có MAC đúng và timestamp có vẻ gần. Then không tiếp nhận nghiệp vụ bình thường. Nếu dùng vùng chờ, trạng thái vẫn chưa xác minh và có quota/expiry. When thời gian đã khỏe nhưng bản giao không còn đạt cửa sổ. Then không đổi timestamp, không tăng cửa sổ và không coi bản cũ đã được nhận hợp lệ; yêu cầu giao mới hoặc đối soát theo quyền được duyệt.

**AC-06 — Crash, retry ký mới và bất biến nghiệp vụ.** Given một ý định thanh toán đã được tiếp nhận hoặc đã ghi có. When crash được tiêm trước/sau commit, trước ACK hoặc sau tác dụng ngoài, rồi nguồn gửi retry có MAC/timestamp mới. Then không mất ý định đã ACK và không phát sinh khoản ghi có thứ hai bị cấm. Với kết quả tác dụng ngoài chưa rõ, phải có bản ghi cần đối soát hoặc tra cứu theo khóa idempotency, không báo thành công chỉ dựa vào timestamp.

Mỗi AC cần fixture có phiên bản, trạng thái DB trước/sau, phản hồi, reason code, mốc nhận và bằng chứng kết quả đích. Chỉ kết luận đạt khi cả quyết định lẫn tác dụng thỏa yêu cầu; một log “đã chặn replay” không đủ. Các giá trị ngưỡng, quota và lịch retry trong bài là giả định nghiệm thu minh họa, phải được chủ dịch vụ phê duyệt cho tích hợp cụ thể.

## 13. Truy vết qua vòng đời phát triển

Chuỗi truy vết tối thiểu:

```text
Mục tiêu chống chấp nhận lại ngoài điều kiện cho phép
    → Kịch bản sửa timestamp, replay, lệch giờ hoặc retry không tương thích
    → Yêu cầu WHT-xx
    → Hợp đồng ký, nguồn thời gian và ranh giới ingress
    → Test T-WHT-xx
    → Metric, audit, đối soát và quy trình phục hồi
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Không làm mới webhook bằng sửa thời gian | Timestamp không nằm trong chữ ký | WHT-02 | Ràng buộc đúng signed input; T-WHT-01 |
| Chặn quá cũ và tương lai quá mức | Cửa sổ đối xứng hoặc sai đơn vị | WHT-03, 04 | Grammar và hai giới hạn; T-WHT-02, 03, 04 |
| Không tin đồng hồ lỗi | Receiver lệch hoặc mất bằng chứng | WHT-06 | Sức khỏe thời gian và suy giảm; T-WHT-06 |
| Retry đúng nhưng không tạo tác dụng lặp | Cùng sự kiện có lần ký mới | WHT-07, 09 | Hợp đồng delivery và idempotency; T-WHT-08, 10 |
| Không loại nhầm vì queue nội bộ | Worker xác minh lại bằng mốc sai | WHT-08 | Bằng chứng ingress được bảo vệ; T-WHT-09 |
| Không lặp sau phục hồi | Marker bị mất nhưng bên gửi ký lại | WHT-14 | Restore/đối soát trạng thái; T-WHT-14 |

Thay nhà cung cấp webhook, format chữ ký, proxy, cách đọc body, cửa sổ, hệ thống đồng bộ giờ hoặc retention marker đều có thể thay đổi bảo đảm.

Ngoại lệ phải có nguồn/endpoint, phạm vi dữ liệu, thời hạn, rủi ro còn lại, biện pháp bù và người phê duyệt. Không bỏ kiểm tra độ mới của mọi nguồn để xử lý một tích hợp có retry khác biệt.

## 14. Những lỗi đặc tả thường gặp

| Cách viết hoặc triển khai | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Có timestamp là chống replay.” | Giá trị có thể không được xác thực | Ràng buộc timestamp với nội dung và nguồn |
| “Body ký đúng nên header time đáng tin.” | Header có thể nằm ngoài chữ ký | Kiểm tra đúng phạm vi giao thức |
| “Dùng thời điểm sự kiện cho mọi delivery.” | Retry thật có thể giao sự kiện rất cũ | Phân biệt thời gian nghiệp vụ và lần gửi |
| “Cho lệch tuyệt đối 5 phút.” | Có thể mở dung sai tương lai ngoài ý định | Đặc tả W_past và W_future riêng |
| “Số dài thì chắc là mili giây.” | Tự đoán đơn vị gây nhập nhằng | Parse đúng hợp đồng, từ chối sai định dạng |
| “Bên nhận dùng UTC nên giờ đúng.” | UTC không chứng minh đồng hồ chính xác | Quan sát offset, độ không chắc chắn và độ mới |
| “Queue chậm thì tăng cửa sổ vô hạn.” | Mở rộng khả năng replay | Xác minh ở ranh giới phù hợp và bảo vệ bằng chứng |
| “Còn trong cửa sổ thì xử lý mọi lần.” | Replay nhanh vẫn vượt kiểm tra thời gian | Idempotency và guard nghiệp vụ |
| “Event ID đã thấy thì bỏ qua chữ ký.” | Field tự khai có thể làm sai quyết định hoặc lộ thông tin | Xác thực và đối chiếu theo hợp đồng duplicate |
| “Đồng hồ lỗi thì thay timestamp bằng bây giờ.” | Phá ý nghĩa độ mới và nguồn | Hành vi suy giảm/đối soát được phê duyệt |
| “Khóa cũ ký với thời gian cũ thì luôn hợp lệ.” | Timestamp tự khai không chứng minh thời điểm ký thật | Chính sách khóa và bằng chứng thời gian phù hợp |
| “Cửa sổ ngắn nên restore không cần marker.” | Nguồn có thể ký lại sự kiện cũ bằng thời gian mới | Giữ hoặc đối soát bất biến chống lặp |

## 15. Bài tập áp dụng

Một cổng nhận webhook thanh toán kiểm tra chữ ký body nhưng không ký timestamp header. Ứng dụng dùng `abs(now - timestamp) <= 600`. Webhook được đưa vào queue trước khi xác minh, worker có thể chờ 30 phút. Khi timeout, bên gửi có thể retry trong 24 giờ, nhưng đội phát triển chưa xác định họ có ký timestamp mới hay không.

Hãy thực hiện:

1. Nêu ít nhất sáu kịch bản rủi ro về timestamp, chữ ký, replay và queue.
2. Xác định các mốc sự kiện, lần ký, nhận request và xử lý nghiệp vụ.
3. Đề xuất hợp đồng W_past/W_future có giải thích ngân sách và rủi ro.
4. Nêu thông tin cần xác minh về retry trước khi chốt cửa sổ.
5. Viết sáu yêu cầu có ID, phạm vi, điều kiện đạt, chủ sở hữu và bằng chứng.
6. Thiết kế test biên quá khứ/tương lai, sai đơn vị, body bị đổi và đồng hồ receiver lỗi.
7. Đề xuất ranh giới tiếp nhận bền vững và bằng chứng nội bộ để worker không tin verified flag giả.
8. Giải thích vì sao timestamp hợp lệ không thay thế chống lặp khi cùng sự kiện được ký mới.
9. Nêu cách xử lý và đối soát sau restore marker hoặc khi không thể giao lại trong cửa sổ bình thường.

Đáp án tốt phải gắn từng phép so sánh với đúng mốc và nguồn tin, đồng thời chứng minh không có tác dụng mới chỉ do webhook tự khai còn mới.

## 16. Checklist chấp nhận yêu cầu

- Hợp đồng đã phân biệt thời gian sự kiện và thời gian lần gửi chưa?
- Timestamp dùng cho độ mới có nằm trong phần được xác thực không?
- Body và các trường ký có được giữ đúng biểu diễn của giao thức không?
- Đơn vị, grammar, giá trị trùng, làm tròn và tràn số có được đặc tả không?
- W_past và W_future có riêng, có biên và lý do lựa chọn không?
- received_at có do ranh giới tin cậy tạo ở mốc rõ ràng không?
- Request size và thời gian nhận có ngăn kéo dài cửa sổ ngoài ý định không?
- Đồng hồ receiver có tiêu chí sức khỏe và hành vi khi không đủ tin cậy không?
- Retry thực tế có tương thích với cửa sổ và cách ký lại không?
- Bằng chứng ingress có được bảo vệ khi chuyển sang queue/worker không?
- Idempotency có ngăn tác dụng lặp trong cùng cửa sổ và sau lần ký mới không?
- Khóa, rotation và thu hồi có được kiểm tra độc lập với độ mới không?
- ACK có phản ánh đúng mức tiếp nhận bền vững không?
- Audit/cảnh báo có phân biệt lỗi và tránh lộ dữ liệu tái sử dụng không?
- Restore có giữ hoặc đối soát marker, endpoint, khóa và cấu hình thời gian không?

Timestamp webhook có giá trị bảo mật khi nó được xác thực cùng thông điệp, được so sánh tại ranh giới đáng tin bằng cửa sổ có ý nghĩa, và phối hợp với chống lặp cùng kiểm tra nghiệp vụ trong toàn bộ vòng đời tiếp nhận.
