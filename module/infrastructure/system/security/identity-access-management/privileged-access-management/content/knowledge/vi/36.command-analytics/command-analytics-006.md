# Heuristic analysis trong phân tích lệnh đặc quyền

## 1. Mục tiêu và phạm vi

Trong Privileged Access Management (PAM), một phiên đã xác thực hợp lệ vẫn có thể chứa hành vi ngoài mục đích được phê duyệt. Người quản trị có thể dùng nhầm tài khoản, thực hiện thao tác vượt phạm vi ticket hoặc chạy một công cụ hợp lệ theo cách gây rủi ro. Tài khoản bị chiếm dụng cũng có thể đi qua đúng cổng PAM và sử dụng những lệnh quen thuộc.

**Heuristic analysis** là cách đánh giá hành vi bằng các dấu hiệu và quy tắc suy luận thực dụng. Thay vì chỉ hỏi “lệnh này có nằm trong danh sách cấm không?”, hệ thống đặt thêm các câu hỏi: ai chạy lệnh, trên tài nguyên nào, vào thời điểm nào, với mục đích gì, sau những thao tác nào và có bằng chứng nào xác nhận tác động?

Bài học thuộc chương Command analytics, tập trung vào cách thiết kế heuristic cho hoạt động quản trị đặc quyền, tài khoản dịch vụ và hạ tầng nhạy cảm. Cách tiếp cận này hỗ trợ kiểm kê quyền, least privilege, JIT/JEA, giám sát phiên và lưu bằng chứng. Nó không thay thế các cơ chế kiểm soát quyền truy cập đó.

Sau bài học, người học có thể:

- Phân biệt heuristic với khớp từ khóa, chính sách cấp quyền và mô hình học máy.
- Chuyển dấu hiệu rời rạc thành quy tắc có điều kiện áp dụng, bằng chứng và giới hạn rõ ràng.
- Thiết kế cách tính điểm có thể giải thích, tránh cộng trùng và xử lý dữ liệu thiếu.
- Đọc một cảnh báo theo mức độ rủi ro, độ tin cậy và trạng thái thực thi.
- Hiệu chỉnh cảnh báo dựa trên phản hồi vận hành và giữ đủ dấu vết kiểm toán.

Các tên trường, mã quy tắc, trọng số và ngưỡng trong bài là mô hình minh họa. Chúng không phải cấu hình mặc định hay cam kết tính năng của một sản phẩm PAM cụ thể.

## 2. Heuristic trả lời câu hỏi gì?

### 2.1. Từ một chuỗi lệnh đến một giả thuyết có căn cứ

Giả sử một quản trị viên mở phiên JIT để kiểm tra tình trạng dịch vụ. Trong phiên, hệ thống thấy ba nhóm hoạt động:

1. Kiểm tra tiến trình và trạng thái dịch vụ.
2. Yêu cầu thay đổi một thiết lập giám sát không thuộc phạm vi ticket.
3. Xuất hiện kết nối từ máy đích đến một đích mạng chưa được ghi nhận trong hồ sơ công việc.

Một phép khớp từ khóa có thể bỏ qua nhóm thứ nhất hoặc cảnh báo quá rộng ở nhóm thứ hai. Heuristic kết hợp ngữ cảnh để hình thành giả thuyết: “phiên kiểm tra dịch vụ có dấu hiệu vượt mục đích và làm suy yếu giám sát, đồng thời có hoạt động mạng cần xác minh”.

Giả thuyết này chưa chứng minh có xâm nhập hoặc dữ liệu đã bị lấy đi. Nó giúp người trực vận hành ưu tiên điều tra và biết cần kiểm chứng bằng chứng nào tiếp theo.

### 2.2. Phân biệt các cơ chế liên quan

| Cơ chế | Câu hỏi chính | Kết quả thường gặp | Giới hạn cần nhớ |
|---|---|---|---|
| Chính sách truy cập | Chủ thể có được phép thực hiện thao tác không? | Cho phép, từ chối, yêu cầu phê duyệt | Có quyền không đồng nghĩa có mục đích hợp lệ |
| Khớp mẫu hoặc chữ ký | Chuỗi hay cấu trúc có khớp mẫu đã biết không? | Một mẫu trúng hoặc không trúng | Dễ mất ngữ cảnh nếu chỉ so khớp văn bản |
| Heuristic analysis | Tập dấu hiệu này có đáng ngờ trong hoàn cảnh hiện tại không? | Lý do cảnh báo, điểm ưu tiên, bằng chứng | Phụ thuộc giả định, dữ liệu và hiệu chỉnh |
| Phát hiện bất thường thống kê | Hành vi khác đường cơ sở đến mức nào? | Độ lệch hoặc mức bất thường | Khác thường có thể vẫn hợp lệ |
| Mô hình học máy | Mẫu đầu vào được mô hình đánh giá thế nào? | Nhãn, điểm hoặc xếp hạng | Cần quản trị dữ liệu và đánh giá riêng |

Các cơ chế có thể phối hợp. Một heuristic có thể dùng kết quả khớp cấu trúc lệnh hoặc tín hiệu bất thường làm đầu vào. Heuristic không bắt buộc phải sử dụng học máy.

Một quy tắc giới hạn quyền kiểu JEA cần thực thi theo chính sách được phê duyệt. Điểm heuristic thấp không tạo thêm quyền và không được làm mất hiệu lực của một quyết định từ chối truy cập.

## 3. Đơn vị phân tích và dữ liệu đầu vào

### 3.1. Chọn đơn vị trước khi viết quy tắc

Có ít nhất ba đơn vị phân tích:

- **Sự kiện:** một yêu cầu lệnh, một lần thực thi tiến trình hoặc một quyết định chính sách.
- **Cửa sổ hành vi:** các sự kiện liên quan trong một khoảng thời gian xác định.
- **Phiên hoặc tác vụ:** toàn bộ hoạt động gắn với phiên PAM, lượt cấp JIT hay một công việc tự động.

Quy tắc cho sự kiện không nên âm thầm trở thành quy tắc cho cả tài khoản. Một người có nhiều phiên đồng thời; một tài khoản dịch vụ cũng có thể phục vụ nhiều workload. Gộp mọi hoạt động theo tên tài khoản dễ tạo ra một chuỗi hành vi chưa từng xảy ra trong cùng tác vụ.

Khóa tương quan nên ưu tiên session ID, task ID, máy đích và định danh tiến trình nếu có. Khi phải dùng khóa suy luận, cảnh báo cần thể hiện mức không chắc chắn của việc nối sự kiện.

### 3.2. Mô hình sự kiện tối thiểu

Một sự kiện chuẩn hóa có thể được mô tả như sau:

```json
{
  "eventId": "evt-481",
  "eventTime": "2026-11-20T03:12:00Z",
  "ingestTime": "2026-11-20T03:12:02Z",
  "sessionId": "pam-session-042",
  "actorId": "user-ops-17",
  "privilegedAccountId": "svc-admin-09",
  "targetId": "production-node-07",
  "targetTier": "critical",
  "ticketId": "CHG-DEMO-42",
  "jitGrantId": "jit-grant-042",
  "observationStage": "execution_observed",
  "command": {
    "executable": "systemctl",
    "argumentsRedacted": ["status", "orders.service"],
    "parseQuality": "structured",
    "semanticAction": "service.status.read"
  },
  "execution": {
    "exitCode": 0,
    "outcome": "observed"
  },
  "telemetry": {
    "source": "endpoint-process",
    "coverage": "available"
  }
}
```

Đây chỉ là schema giảng dạy. Một nguồn PAM có thể không cung cấp đủ các trường trên. Thiếu trường không phải lý do tự suy ra giá trị từ tên tài khoản hay từ một chuỗi văn bản gần giống.

Cần phân biệt:

- Actor đăng nhập với tài khoản đặc quyền được sử dụng.
- Máy trung chuyển với máy thực sự thực thi lệnh.
- Lệnh được nhập với tiến trình được quan sát.
- Yêu cầu bị chính sách từ chối với thao tác đã chạy.
- Thoát tiến trình thành công với trạng thái nghiệp vụ đã thay đổi đúng dự kiến.

### 3.3. Nguồn bổ sung làm thay đổi cách hiểu

| Nguồn | Thông tin bổ sung | Điều không nên suy diễn |
|---|---|---|
| PAM session metadata | Chủ thể, máy đích, phê duyệt, phiên ghi hình | Phiên được phê duyệt không có nghĩa mọi lệnh đều đúng mục đích |
| Hệ thống ticket | Phạm vi, thời gian, tác vụ được chấp thuận | Ticket tồn tại không chứng minh nội dung phù hợp |
| JIT/JEA | Thời hạn cấp quyền, vai trò, tập thao tác cho phép | Có grant không chứng minh mọi thay đổi được duyệt |
| Endpoint audit | Tiến trình, cây tiến trình, một số trạng thái thực thi | Không có sự kiện có thể do thiếu telemetry |
| Audit dịch vụ hoặc ứng dụng | Thay đổi đối tượng, kết quả nghiệp vụ | Cần kiểm tra quan hệ với đúng phiên |
| Metadata mạng | Đích kết nối, thời điểm, lưu lượng | Kết nối không chứng minh nội dung dữ liệu đã bị lộ |
| Lịch vận hành | Cửa sổ bảo trì, batch job, vùng giờ | Ngoài giờ không tự động đồng nghĩa trái phép |

Chất lượng ngữ cảnh là một phần của kết quả phân tích. Cảnh báo thiếu ticket nên ghi “chưa đánh giá được phạm vi phê duyệt”, thay vì tự ghi “vượt phạm vi”.

## 4. Chuẩn hóa lệnh mà không làm mất ý nghĩa

### 4.1. Vì sao khớp văn bản đơn giản dễ sai?

Một tên công cụ có thể xuất hiện trong phần trợ giúp, trong một chuỗi được in ra hoặc trong đối số của lệnh tìm kiếm. Các lệnh cũng có thể được chạy qua shell, script, wrapper, alias hoặc công cụ điều phối. Cùng một chuỗi hiển thị trên terminal chưa chắc đại diện cho cùng hành động thực thi.

Ví dụ đọc trạng thái dịch vụ và thay đổi cấu hình dịch vụ có thể dùng cùng một executable. Nếu quy tắc chỉ nhìn tên executable, hệ thống sẽ đánh đồng tác vụ chẩn đoán với tác vụ thay đổi trạng thái.

Ngược lại, thao tác thay đổi quyền có thể được thực hiện thông qua nhiều công cụ. Chỉ tìm một tên lệnh cụ thể sẽ bỏ sót cùng một hành động dưới hình thức khác.

### 4.2. Ba lớp biểu diễn

Nên giữ quan hệ giữa ba lớp:

1. **Bằng chứng gốc:** bản ghi có nguồn gốc, thời gian và chính sách truy cập phù hợp.
2. **Biểu diễn cú pháp:** executable, đối số, toán tử shell, phạm vi đối tượng và chất lượng parse.
3. **Ý nghĩa đã suy luận:** đọc trạng thái, thay đổi quyền, quản lý tài khoản, thay đổi giám sát, truyền dữ liệu hoặc hành động chưa xác định.

Không dùng chính bộ phân tích để thực thi chuỗi lệnh. Không đưa chuỗi không tin cậy vào shell nhằm “giải mã” hay kiểm tra nó. Việc phân tích phải xử lý dữ liệu như dữ liệu, với giới hạn kích thước, độ sâu và thời gian.

Một bản ghi terminal có thể chỉ cho thấy lệnh gọi script, không cho biết từng lệnh bên trong script. Trong trường hợp đó, kết luận đúng là phạm vi quan sát có giới hạn; không gán ý nghĩa chi tiết chưa có bằng chứng.

### 4.3. Bảo vệ dữ liệu nhạy cảm

Đối số, đường dẫn và đầu ra lệnh có thể chứa credential hoặc dữ liệu cá nhân. Quy trình phân tích nên:

- Ưu tiên chỉ thu các trường cần thiết cho use case.
- Che hoặc loại bỏ secret trước khi đưa vào chỉ mục tìm kiếm phổ thông.
- Dùng tham chiếu tới bằng chứng được bảo vệ thay vì sao chép toàn bộ đầu ra vào cảnh báo.
- Kiểm soát quyền đọc, thời gian lưu và việc truy xuất bản ghi nhạy cảm.
- Giữ định danh tài nguyên cần thiết để điều tra nhưng không đính kèm nội dung secret.

Nếu chính sách yêu cầu giữ bằng chứng gốc, việc lưu đó cần kho riêng với kiểm soát chặt chẽ. Không nên mở rộng thu thập secret chỉ để tăng độ tiện lợi của heuristic.

## 5. Thiết kế một heuristic có thể vận hành

Một heuristic hữu ích không chỉ có điều kiện “nếu A thì cảnh báo B”. Nó cần một hợp đồng rõ ràng.

| Thành phần | Nội dung cần xác định |
|---|---|
| Mục tiêu | Hành vi hoặc rủi ro muốn phát hiện |
| Đơn vị | Sự kiện, cửa sổ hay phiên |
| Điều kiện áp dụng | Nhóm tài nguyên, loại tài khoản, giai đoạn thao tác |
| Dữ liệu bắt buộc | Trường và nguồn cần có để đưa ra kết luận |
| Điều kiện trúng | Biểu thức hoặc chuỗi sự kiện cụ thể |
| Ngoại lệ | Phạm vi, người phê duyệt và thời hạn |
| Bằng chứng | Event ID, nguồn, thời gian, tham chiếu liên quan |
| Trọng số và nhóm | Mức đóng góp vào điểm và cách tránh cộng trùng |
| Giới hạn | Những điều quy tắc chưa chứng minh được |
| Hành động | Tạo cảnh báo, bổ sung ngữ cảnh, điều tra hoặc phản ứng được duyệt |
| Quản trị | Chủ sở hữu, phiên bản, ngày rà soát và phương án hoàn tác |

### 5.1. Bốn trạng thái đánh giá

Mỗi quy tắc nên trả một trong bốn trạng thái:

- **HIT:** đủ dữ liệu và điều kiện trúng.
- **MISS:** đủ dữ liệu, quy tắc áp dụng nhưng không trúng.
- **UNKNOWN:** thiếu dữ liệu hoặc chất lượng phân tích không đủ.
- **NOT_APPLICABLE:** không thuộc phạm vi áp dụng của quy tắc.

Ví dụ quy tắc “thao tác ngoài cửa sổ được phê duyệt”:

- Có thời gian sự kiện, lịch được phê duyệt và phép đổi múi giờ hợp lệ: có thể HIT hoặc MISS.
- Không tải được lịch: UNKNOWN.
- Tác vụ không sử dụng cửa sổ kiểu này và có loại phê duyệt khác được định nghĩa: NOT_APPLICABLE.

UNKNOWN không nên bị ép thành MISS. Nếu toàn bộ quy tắc đều UNKNOWN, điểm bằng 0 vẫn không có nghĩa phiên an toàn.

### 5.2. Phân biệt dấu hiệu rủi ro với lỗi telemetry

Mất bản ghi PAM hoặc gián đoạn nguồn audit có thể là sự cố tích hợp. Nó cũng có thể xảy ra gần một hành vi làm suy yếu giám sát. Hai tình huống cần tuyến xử lý khác nhau.

Một quy tắc “quan sát thấy yêu cầu thay đổi audit” dựa vào sự kiện cụ thể. Một quy tắc “không nhận được telemetry trong thời gian kỳ vọng” dựa vào độ phủ và sức khỏe nguồn. Không dùng sự vắng mặt của log để tự kết luận ai đó đã tắt audit.

Có thể tạo cảnh báo sức khỏe giám sát riêng và liên kết nó với phiên liên quan. Chỉ tăng mức nghi ngờ hành vi khi có thêm dữ liệu hỗ trợ.

## 6. Danh mục dấu hiệu minh họa

Bảng dưới mô tả một bộ quy tắc giả định. Trọng số được dùng xuyên suốt ví dụ của bài để minh họa tính nhất quán, không phải các con số đã được hiệu chỉnh cho môi trường thực tế.

| Mã | Dấu hiệu | Nhóm điểm | Trọng số | Bằng chứng quan trọng |
|---|---|---|---:|---|
| H1 | Actor truy cập máy đặc quyền chưa từng làm việc trong tập lịch sử đủ độ phủ | context | 10 | Actor, máy đích, lịch sử và phạm vi dữ liệu |
| H2 | Thao tác xảy ra ngoài cửa sổ được phê duyệt | context | 10 | Event time và cửa sổ phê duyệt có múi giờ |
| H3 | Hành động đã hiểu không nằm trong phạm vi công việc được duyệt | intent | 25 | Semantic action và phạm vi phê duyệt đã cấu trúc |
| H4 | Thao tác nhạy cảm trên đối tượng đặc biệt quan trọng | command | 20 | Loại thao tác, đối tượng và mức quan trọng |
| H5 | Quan sát thấy yêu cầu làm suy yếu kiểm soát giám sát hoặc bảo vệ | control | 30 | Sự kiện thao tác cùng trạng thái bị chặn hay đã thực thi |
| H6 | Chuỗi chuẩn bị, tập hợp dữ liệu và hoạt động truyền ra liên quan | sequence | 25 | Thứ tự, khóa tương quan và dữ liệu từ các nguồn liên quan |
| H7 | Kết nối tới đích chưa được phê duyệt cho tác vụ hiện tại | egress | 20 | Flow metadata, ánh xạ phiên và danh sách đích được phép |
| H8 | Tần suất thao tác thay đổi tăng mạnh so với tác vụ tương đương | volume | 10 | Cửa sổ đo và nhóm so sánh phù hợp |

### 6.1. Những điểm cần làm rõ cho từng dấu hiệu

**H1 không phải “lần đầu = xấu”.** Người mới nhận nhiệm vụ hoặc một máy vừa đưa vào vận hành đều có thể tạo dấu hiệu này. Nếu lịch sử chỉ còn một ngày do lỗi lưu trữ, không đủ cơ sở gọi máy đích là mới đối với actor.

**H3 cần hiểu nội dung phê duyệt.** Một ticket có mô tả tự do quá rộng có thể không đủ để tự động kết luận hành động ngoài phạm vi. Khi phạm vi chưa được chuẩn hóa hoặc có cách hiểu mâu thuẫn, quy tắc trả UNKNOWN và đưa việc xác minh vào bước điều tra.

**H4 cần ngữ nghĩa và đối tượng.** Đọc metadata thông thường khác với thay đổi quyền đối với tài khoản quản trị hoặc kho credential. Không lấy một từ xuất hiện trong đầu ra làm bằng chứng của thao tác thay đổi.

**H5 phải ghi rõ giai đoạn.** Một yêu cầu bị chính sách chặn vẫn có thể cần điều tra về ý định hoặc thao tác nhầm. Tuy nhiên, cảnh báo không được nói kiểm soát đã bị vô hiệu hóa nếu chỉ có bằng chứng yêu cầu bị từ chối.

**H6 không phải phép tìm ba từ khóa bất kỳ.** Các sự kiện phải liên quan về phiên hoặc tác vụ, tài nguyên và thời gian. Độ trễ log, hai phiên song song hoặc tiến trình nền có thể tạo chuỗi giả nếu nối sai.

**H7 không chứng minh lấy cắp dữ liệu.** Một đích mạng chưa được phê duyệt cần được kiểm tra; nó có thể là hệ thống sao lưu mới hoặc phụ thuộc chưa được cập nhật. Muốn kết luận truyền dữ liệu cần bằng chứng phù hợp về hoạt động thực tế.

**H8 phải so sánh đúng loại công việc.** Batch job luân chuyển credential có đặc điểm khác phiên hỗ trợ thủ công. Tần suất cao của một job hợp lệ không nên bị so với đường cơ sở của một người dùng tương tác.

## 7. Tính điểm mà vẫn giữ khả năng giải thích

### 7.1. Điểm ưu tiên không phải xác suất

Một phép cộng trọng số giúp xếp hàng xử lý. Nếu điểm là 85, không được diễn giải thành “85% khả năng bị xâm nhập” trừ khi có một quy trình hiệu chuẩn xác suất riêng chứng minh điều đó.

Trong mô hình minh họa:

```text
điểm_nhóm = min(trần_nhóm, tổng trọng số các HIT độc lập trong nhóm)
điểm_cửa_sổ = min(100, tổng điểm_nhóm)
```

Nhóm context có trần 15; các nhóm khác có trần bằng trọng số quy tắc tương ứng trong bảng. Vì vậy H1 và H2 cùng trúng chỉ đóng góp 15 thay vì 20.

Mỗi quy tắc chỉ đóng góp một lần trong một cửa sổ đánh giá. Nhiều sự kiện làm cùng quy tắc trúng phải được giữ làm bằng chứng, không tự nhân số điểm. Nếu tần suất là một dấu hiệu cần thiết, hãy đưa nó vào quy tắc volume được thiết kế riêng.

### 7.2. Tránh điểm bị thổi phồng

Có hai dạng trùng cần xử lý:

1. **Trùng sự kiện:** một hành động được nguồn gửi lại hoặc được nhiều collector sao chép.
2. **Trùng suy luận:** một hành động được nhiều quy tắc mô tả với tên khác nhau.

Event ID, source ID và khóa ổn định giúp xử lý dạng thứ nhất. Trần nhóm và nhóm loại trừ đóng góp giúp xử lý dạng thứ hai.

Ví dụ một yêu cầu thay đổi thiết lập giám sát có thể đồng thời thỏa H4 và H5. Nếu cả hai mô tả cùng một hành động, bộ quy tắc này chỉ giữ đóng góp mạnh hơn, tức H5. H4 vẫn có thể được ghi nhận là lý do bổ sung nhưng không cộng thêm 20 điểm cho cùng bằng chứng.

H6 cũng có thể dùng chính sự kiện mạng của H7. Nếu điểm của chuỗi đã bao hàm rủi ro egress, cần một quy ước chống cộng trùng cho phần bằng chứng đó. Không nên coi mọi quy tắc ở các nhóm khác nhau là độc lập một cách mặc định.

### 7.3. Ngưỡng minh họa

| Điểm | Mức ưu tiên minh họa | Hướng xử lý ban đầu |
|---:|---|---|
| 0–19 | Thấp | Giữ kết quả đánh giá; xem riêng tình trạng thiếu dữ liệu |
| 20–39 | Trung bình | Bổ sung ngữ cảnh hoặc rà soát theo hàng đợi |
| 40–69 | Cao | Tạo cảnh báo cần điều tra sớm |
| 70–100 | Rất cao | Chuyển tới người trực, kiểm tra bằng chứng và chọn phản ứng phù hợp |

Ngưỡng không phải quyết định tự động chấm dứt phiên. Một quy tắc chính sách bắt buộc có thể chặn thao tác ngay cả khi điểm rất thấp. Ngược lại, cảnh báo điểm cao với dữ liệu không chắc chắn có thể cần xác minh trước khi can thiệp.

### 7.4. Độ tin cậy là trục riêng

Điểm rủi ro và độ tin cậy cần được trình bày riêng:

- **Độ phủ dữ liệu:** có đủ nguồn và khoảng thời gian cần cho các quy tắc được sử dụng không?
- **Chất lượng parse:** biết thao tác thật hay chỉ có chuỗi terminal chưa phân tích chắc chắn?
- **Chất lượng tương quan:** có khóa nối trực tiếp hay chỉ suy luận theo thời điểm?
- **Mức xác nhận:** hành động được yêu cầu, được thực thi hay đã có xác nhận thay đổi trạng thái?

Không nhất thiết phải ép độ tin cậy thành một số. Một nhãn kèm lý do như “trung bình: ánh xạ kết nối đến phiên dựa trên thời gian và máy đích” thường dễ sử dụng hơn con số không được giải thích.

## 8. Chuỗi thời gian và cửa sổ phân tích

Heuristic chuỗi cần định nghĩa cả quan hệ lẫn thời gian.

Ví dụ giả định:

```text
A: có thao tác chuẩn bị liên quan tới một tập dữ liệu nhạy cảm
B: có hoạt động tập hợp tập dữ liệu đó
C: có hoạt động truyền ra được liên kết với cùng tác vụ

Điều kiện:
- A xảy ra trước B, B xảy ra trước C theo event time.
- Toàn chuỗi nằm trong cửa sổ 15 phút của ví dụ.
- Cùng tác vụ hoặc có quan hệ tiến trình được xác minh.
- Phạm vi dữ liệu và máy đích tương thích.
- Không thuộc workflow đã được phê duyệt tương ứng.
```

Mốc 15 phút là lựa chọn minh họa, không phải chuẩn chung. Một tác vụ sao lưu có thể kéo dài hơn; một sự cố tương tác có thể diễn ra nhanh hơn.

### 8.1. Event time khác ingest time

Nếu sự kiện B đến hệ thống thu thập trước A do độ trễ mạng, thứ tự ingest không phản ánh thứ tự thực tế. Cần:

- Dùng event time với thông tin chất lượng đồng bộ đồng hồ.
- Cho phép khoảng đệm nhận sự kiện trễ phù hợp với nguồn.
- Đánh dấu kết quả tạm thời nếu cửa sổ chưa ổn định.
- Cập nhật phiên bản cảnh báo khi sự kiện trễ làm thay đổi kết luận.
- Giữ dấu vết của lần đánh giá trước để người xử lý hiểu vì sao điểm thay đổi.

Nếu đồng hồ không đủ tin cậy để xác nhận A trước B, không nên khẳng định chuỗi đầy đủ. Có thể tạo giả thuyết yếu hơn và ghi rõ giới hạn.

### 8.2. Hành vi vượt ranh giới cửa sổ

Cửa sổ cố định dễ bỏ qua chuỗi nằm ở hai phía của một mốc thời gian. Cửa sổ trượt hoặc trạng thái theo phiên có thể giảm vấn đề này, nhưng cần giới hạn bộ nhớ, thời gian giữ trạng thái và cách xử lý phiên rất dài.

Đóng cửa sổ cũng không có nghĩa xóa bằng chứng. Dữ liệu đánh giá và dữ liệu lưu phục vụ kiểm toán có vòng đời khác nhau, cần được quản lý riêng.

## 9. Luồng đánh giá và giả mã

Một luồng vận hành có thể gồm:

```text
Thu nhận sự kiện
  -> kiểm tra nguồn và loại bỏ bản gửi trùng
  -> chuẩn hóa, che dữ liệu nhạy cảm, ghi chất lượng parse
  -> gắn ngữ cảnh quyền, ticket, tài nguyên và tác vụ
  -> đánh giá HIT / MISS / UNKNOWN / NOT_APPLICABLE
  -> chống cộng trùng, tính điểm và độ tin cậy
  -> tạo hoặc cập nhật cảnh báo có bằng chứng
  -> người xử lý hoặc playbook được duyệt tiếp nhận
  -> phản hồi phục vụ hiệu chỉnh và kiểm toán
```

Giả mã sau mô tả cách tổ chức kết quả; không phải một bộ máy phân tích lệnh hoàn chỉnh.

```text
evaluate(window, ruleSetVersion, contextSnapshot):
    events = deduplicate(window.events)
    facts = normalizeWithoutExecution(events)
    results = []

    for rule in loadRules(ruleSetVersion):
        if not rule.applies(facts, contextSnapshot):
            results.add(rule.result(NOT_APPLICABLE))
            continue

        if not rule.hasRequiredInputs(facts, contextSnapshot):
            results.add(rule.result(UNKNOWN, reason = "missing inputs"))
            continue

        result = rule.evaluate(facts, contextSnapshot)
        results.add(result)  // gồm trạng thái, evidence IDs và giới hạn

    hits = uniqueRuleHits(results)
    contributions = resolveOverlappingEvidence(hits)
    groupScores = sumWithGroupCaps(contributions)
    score = min(100, sum(groupScores))
    confidence = describeConfidence(facts, results, contextSnapshot)

    return assessment(
        score = score,
        confidence = confidence,
        reasons = results,
        telemetryGaps = collectUnknownReasons(results),
        evidenceRefs = collectEvidenceReferences(results),
        ruleSetVersion = ruleSetVersion,
        contextVersion = contextSnapshot.version
    )
```

Các yêu cầu quan trọng khi triển khai:

- Cùng tập dữ liệu, phiên bản quy tắc và snapshot ngữ cảnh cần cho kết quả tái lập.
- Việc gửi lại cùng sự kiện không được tạo thêm điểm hoặc cảnh báo mới ngoài ý muốn.
- Giới hạn kích thước đầu vào, độ sâu phân tích và trạng thái theo phiên.
- Một nguồn bị lỗi cần tạo chỉ báo chất lượng, không âm thầm chuyển mọi quy tắc thành MISS.
- Ghi rõ quy tắc đã chạy và quy tắc không thể chạy.
- Tách kết quả phân tích khỏi hành động phản ứng để quản trị quyền can thiệp độc lập.

## 10. Ví dụ tính điểm và diễn giải cảnh báo

### 10.1. Bối cảnh

Một phiên JIT trên máy production được phê duyệt để kiểm tra trạng thái dịch vụ. Cửa sổ được phê duyệt đã kết thúc, nhưng phiên vẫn còn hoạt động do một sai lệch giữa cơ chế cấp quyền và cơ chế kết thúc phiên.

Hệ thống quan sát:

- Thời gian thao tác nằm ngoài cửa sổ: H2 trúng, 10 điểm.
- Yêu cầu thay đổi giám sát không thuộc tập hành động được phê duyệt: H3 trúng, 25 điểm.
- Endpoint ghi nhận yêu cầu thay đổi kiểm soát giám sát: H5 trúng, 30 điểm.
- Flow metadata được nối chắc chắn tới tác vụ cho thấy kết nối tới đích chưa được phê duyệt: H7 trúng, 20 điểm.
- Chưa có bằng chứng về chuỗi tập hợp dữ liệu đầy đủ: H6 không được cộng điểm.

Giả sử các bằng chứng đủ để đánh giá các quy tắc trên và H3 có phạm vi phê duyệt rõ ràng, tổng điểm là:

```text
context: H2 = 10
intent:  H3 = 25
control: H5 = 30
egress:  H7 = 20

Tổng = 85/100
```

Nếu H4 cũng trúng vì cùng yêu cầu thay đổi giám sát, nó bị loại khỏi phần đóng góp do trùng hành động với H5. Điểm vẫn là 85.

H6 có thể là UNKNOWN nếu thiếu telemetry cần thiết để đánh giá chuỗi. Nếu đã có đủ dữ liệu và không có chuỗi tương ứng, H6 là MISS. Việc không cộng điểm không tự cho biết hai trạng thái này.

### 10.2. Kết luận nào được phép đưa ra?

Cảnh báo có thể viết:

> Phiên có điểm ưu tiên 85 theo bộ quy tắc minh họa. Các dấu hiệu gồm thao tác ngoài cửa sổ, yêu cầu ngoài phạm vi công việc, yêu cầu tác động tới giám sát và kết nối tới đích chưa được phê duyệt. Cần xác minh trạng thái giám sát thực tế và mục đích kết nối.

Không nên viết:

> Kẻ tấn công đã tắt giám sát và lấy cắp dữ liệu.

Câu thứ hai vượt quá bằng chứng. Quan sát yêu cầu chưa chứng minh thay đổi thành công; một kết nối chưa chứng minh nội dung đã truyền.

### 10.3. Nếu thiếu dữ liệu thì sao?

Nếu ticket không truy xuất được, H3 chuyển thành UNKNOWN. Nếu không nối chắc chắn flow tới tác vụ, H7 cũng chưa đủ điều kiện HIT. Điểm có thể còn 40 từ H2 và H5, nhưng kết quả phải kèm các khoảng trống dữ liệu.

Không tự giảm ưu tiên xử lý chỉ vì điểm giảm do mất telemetry. Có thể vẫn cần điều tra khẩn dựa trên H5, mức quan trọng của tài nguyên và sự cố giám sát. Đây là quyết định vận hành có giải thích, không phải sửa số điểm để che đi dữ liệu thiếu.

## 11. Từ cảnh báo đến phản ứng PAM

Heuristic có giá trị khi hỗ trợ một quyết định rõ ràng.

### 11.1. Nội dung một cảnh báo hữu ích

Một cảnh báo nên chứa:

- Actor, tài khoản đặc quyền, phiên hoặc tác vụ và máy đích.
- Điểm, mức ưu tiên và lý do độ tin cậy.
- Quy tắc trúng, trạng thái thực thi và các quy tắc UNKNOWN có liên quan.
- Ticket, grant JIT, cửa sổ phê duyệt và phiên bản ngữ cảnh.
- Timeline ngắn với tham chiếu bằng chứng.
- Giới hạn kết luận và bước cần xác minh tiếp.
- Phiên bản bộ quy tắc, thời điểm đánh giá và người hoặc hệ thống tiếp nhận.

Một hash của bằng chứng có thể hỗ trợ kiểm tra tính toàn vẹn, nhưng tự nó không chứng minh dữ liệu thu ban đầu đầy đủ hoặc đúng nguồn. Cần cả quản trị truy cập, nguồn gốc bản ghi, đồng bộ thời gian và lịch sử xử lý.

### 11.2. Chọn phản ứng theo tác động

Các phản ứng có thể gồm yêu cầu xác nhận mục đích, chuyển giám sát trực tiếp, yêu cầu phê duyệt bổ sung, tạm dừng một thao tác hoặc kết thúc phiên theo playbook được duyệt.

Trước khi ngắt phiên, cần xét tác động vận hành: đây là người dùng tương tác hay tài khoản dịch vụ; tác vụ có đang giữ giao dịch hoặc thực hiện khôi phục không; có đường truy cập dự phòng được kiểm soát không?

Đối với tài khoản dịch vụ, thu hồi quyền hoặc xoay credential lập tức có thể ảnh hưởng nhiều workload. Quyết định cần gắn với phạm vi phụ thuộc, phương án duy trì dịch vụ và mức khẩn cấp thực tế.

Nếu có căn cứ credential bị lộ, vault và quy trình luân chuyển credential là phần của ứng phó. Heuristic đơn lẻ không tự chứng minh credential đã bị lộ.

### 11.3. Liên kết với least privilege và JIT/JEA

Phản hồi từ phân tích có thể chỉ ra rằng:

- Một vai trò cấp quá nhiều quyền so với công việc thường làm.
- Grant JIT kéo dài hơn cửa sổ công việc.
- Một tập lệnh hoặc endpoint JEA cần được thu hẹp.
- Tài khoản dùng chung khiến việc quy trách nhiệm không đủ rõ.
- Ticket thiếu cấu trúc nên khó đánh giá phạm vi.

Những phát hiện này hỗ trợ cải thiện thiết kế quyền. Không nên tự động cắt quyền chỉ vì người dùng ít sử dụng trong một khoảng quan sát ngắn; cần xem nhiệm vụ, chu kỳ vận hành và các tình huống dự phòng.

## 12. Hiệu chỉnh để giảm nhiễu mà không tạo điểm mù

### 12.1. Những nguồn cảnh báo giả thường gặp

| Tình huống hợp lệ | Vì sao dễ trúng heuristic | Cách cải thiện |
|---|---|---|
| Đợt triển khai trên nhiều máy mới | H1 và H8 tăng | Bổ sung phạm vi rollout, loại tài khoản và task ID |
| Sao lưu tới hạ tầng mới | H6 hoặc H7 trúng | Phê duyệt đích, lịch và luồng tác vụ cụ thể |
| Xử lý sự cố ngoài giờ | H2 và H3 có thể trúng | Ghi nhận cơ chế phê duyệt khẩn có thời hạn |
| Bảo trì hệ thống giám sát | H5 trúng | Đối chiếu phạm vi thay đổi và xác nhận khôi phục |
| Luân chuyển credential hàng loạt | H8 tăng mạnh | So sánh với job cùng loại thay vì phiên thủ công |

Không giải quyết nhiễu bằng cách miễn toàn bộ tài khoản quản trị hoặc bỏ qua toàn bộ phiên có ticket. Những ngoại lệ rộng như vậy làm mất khả năng phát hiện chính nhóm hành vi cần giám sát.

Một ngoại lệ nên có actor hoặc workload, tập tài nguyên, loại hành động, cửa sổ thời gian, tham chiếu phê duyệt, chủ sở hữu và ngày hết hạn. Khi hết hạn, hệ thống quay lại đánh giá bình thường.

### 12.2. Quy trình đưa quy tắc vào hoạt động

Một trình tự phù hợp:

1. Viết giả thuyết và định nghĩa dữ liệu cần có.
2. Chạy trên dữ liệu lịch sử được phép sử dụng.
3. Kiểm tra cả tình huống hợp lệ, tình huống đáng ngờ và tình huống thiếu dữ liệu.
4. Chạy chế độ chỉ quan sát để đo khối lượng cảnh báo.
5. Hiệu chỉnh điều kiện và ngoại lệ có thời hạn.
6. Đưa vào hàng đợi xử lý với playbook rõ ràng.
7. Chỉ bổ sung phản ứng tự động khi bằng chứng, tác động và quyền phê duyệt phù hợp.
8. Theo dõi sau thay đổi và có phương án quay lại phiên bản trước.

Không chỉ tăng ngưỡng để đạt số lượng cảnh báo mong muốn. Cách làm đó có thể làm giảm độ nhạy ở những hành vi hiếm nhưng nghiêm trọng. Nên sửa nguyên nhân nhiễu, cách nhóm sự kiện và chất lượng ngữ cảnh trước.

### 12.3. Đo hiệu quả đúng cách

Có thể theo dõi:

- Số cảnh báo trên mỗi nghìn phiên hoặc tác vụ, tách theo nhóm công việc.
- Tỷ lệ cảnh báo đã điều tra có kết quả hữu ích, cùng định nghĩa nhãn rõ ràng.
- Thời gian từ sự kiện đến cảnh báo và từ cảnh báo đến người tiếp nhận.
- Tỷ lệ UNKNOWN và độ phủ dữ liệu theo nguồn.
- Tỷ lệ cảnh báo trùng, ngoại lệ còn hiệu lực và ngoại lệ quá hạn.
- Khả năng phát hiện các kịch bản đã kiểm thử trong phạm vi quan sát.
- Tác động của phản ứng tới hoạt động hợp lệ.

Nếu trong 100 cảnh báo đã điều tra có 30 cảnh báo được xác nhận là hành vi cần xử lý, precision theo định nghĩa nhãn đó là 30%. Các cảnh báo chưa được điều tra không tự động được coi là false positive.

Không thể suy ra recall của toàn bộ hành vi xấu chỉ từ số cảnh báo hiện có. Muốn ước lượng cần tập tình huống có nhãn hoặc phương pháp đánh giá đủ căn cứ; sự cố chưa được phát hiện vốn không xuất hiện trong hàng đợi.

## 13. Bài thực hành bằng dữ liệu giả lập

Bài thực hành này chỉ cần dữ liệu mô tả. Không cần chạy lệnh thay đổi hệ thống thật.

### 13.1. Chuẩn bị ba phiên

**Phiên A — kiểm tra hợp lệ**

- Actor được cấp JIT trong đúng cửa sổ.
- Chạy thao tác đọc trạng thái dịch vụ trong phạm vi ticket.
- Không có thay đổi nhạy cảm hoặc hoạt động mạng bất thường theo các nguồn quan sát đầy đủ.

Kỳ vọng: các quy tắc áp dụng có đủ dữ liệu trả MISS; những quy tắc ngoài phạm vi trả NOT_APPLICABLE. Điểm 0 không thay thế kiểm tra sức khỏe telemetry.

**Phiên B — nhiều tín hiệu kết hợp**

- Dùng bối cảnh và bằng chứng của ví dụ 85 điểm.
- Có yêu cầu thay đổi giám sát và kết nối chưa được phê duyệt.
- Giữ rõ trạng thái yêu cầu, thực thi và xác nhận tác động.

Kỳ vọng: H2, H3, H5 và H7 trúng; điểm 85. Nếu H4 dùng cùng hành động với H5, H4 không cộng thêm. Cảnh báo không kết luận truyền dữ liệu khi chưa có bằng chứng.

**Phiên C — thiếu ngữ cảnh**

- Có sự kiện yêu cầu thay đổi giám sát.
- Không truy xuất được ticket.
- Không có dữ liệu mạng đủ để nối hoạt động với phiên.

Kỳ vọng: H5 có thể HIT nếu bằng chứng đáp ứng điều kiện; H3 và H7 là UNKNOWN. Kết quả phải ghi khoảng trống dữ liệu, không mô tả phiên là an toàn.

### 13.2. Thử tính bền vững của phép đánh giá

Lần lượt thay đổi dữ liệu:

1. Gửi lại cùng event ID ba lần: điểm và số cảnh báo không được tăng do bản gửi trùng.
2. Gửi sự kiện theo thứ tự ingest đảo ngược: chuỗi được đánh giá bằng event time và giới hạn độ trễ đã chọn.
3. Thêm một phiên song song của cùng actor: không được ghép nhầm thành một chuỗi hành vi.
4. Cho H1 và H2 cùng trúng: nhóm context đóng góp tối đa 15.
5. Đặt ngoại lệ hẹp cho đúng tác vụ bảo trì, sau đó cho hết hạn: kiểm tra cả thời gian hiệu lực và bước quay lại đánh giá.
6. Chuyển một yêu cầu thành policy_denied: cảnh báo phải thể hiện thao tác đã bị chặn, không gán tác động thực tế.
7. Làm mất nguồn audit: hiển thị sự cố độ phủ, không suy ra đã có hành vi vô hiệu hóa giám sát.

Sản phẩm thực hành nên gồm bảng kết quả quy tắc, điểm đóng góp, lý do UNKNOWN, timeline và bản mô tả cảnh báo. Mục tiêu là khiến người khác tái hiện được kết luận từ cùng dữ liệu.

## 14. Các lỗi thiết kế cần tránh

- **Dùng tên lệnh làm kết luận cuối:** bỏ qua đối số, mục tiêu và trạng thái thực thi.
- **Dùng tài khoản làm khóa tương quan duy nhất:** ghép hoạt động của nhiều người hoặc workload.
- **Cộng điểm theo số bản ghi:** làm nguồn gửi trùng và thao tác lặp tăng rủi ro giả.
- **Coi dữ liệu thiếu là không có hành vi:** biến mất telemetry thành kết quả “sạch”.
- **Tạo ngoại lệ không hết hạn:** giữ điểm mù lâu hơn nhu cầu vận hành.
- **Đánh đồng cảnh báo với bằng chứng xâm nhập:** làm playbook phản ứng quá mức.
- **Lưu mọi đầu ra để tiện điều tra:** tăng nguy cơ lộ secret và dữ liệu nhạy cảm.
- **Tự động can thiệp chỉ dựa vào điểm:** bỏ qua độ tin cậy, chính sách và tác động dịch vụ.
- **Không lưu phiên bản quy tắc:** không giải thích được vì sao cùng phiên từng có điểm khác nhau.
- **Chỉ đo số cảnh báo:** không biết hệ thống đang hữu ích hơn hay chỉ im lặng hơn.

## 15. Nguyên tắc vận dụng

Heuristic analysis trong PAM biến sự kiện lệnh thành một đánh giá có ngữ cảnh, có thể giải thích và có giới hạn rõ ràng. Chất lượng không nằm ở việc tạo thật nhiều quy tắc, mà ở cách xác định hành động, nối đúng tác vụ, quản lý dữ liệu thiếu và lưu bằng chứng cho từng kết luận.

Một kết quả có thể sử dụng cần trả lời được: điều gì đã được quan sát, vì sao nó đáng chú ý trong phạm vi công việc này, mức chắc chắn đến đâu, điều gì còn chưa biết và ai có quyền quyết định bước tiếp theo. Khi duy trì được các câu trả lời đó, heuristic hỗ trợ cả phát hiện sớm lẫn cải thiện least privilege, JIT/JEA và khả năng kiểm toán của hệ thống PAM.
