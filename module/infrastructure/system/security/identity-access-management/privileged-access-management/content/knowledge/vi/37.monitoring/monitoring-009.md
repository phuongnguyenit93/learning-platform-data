# PAM service health

## 1. Sức khỏe dịch vụ PAM là gì?

Sức khỏe dịch vụ PAM là khả năng hệ thống quản lý truy cập đặc quyền thực hiện đúng các chức năng đã cam kết, trong điều kiện tải và sự cố cụ thể. Một dịch vụ PAM khỏe phải hỗ trợ người dùng hợp lệ nhận quyền đúng chính sách, sử dụng quyền trong phạm vi cho phép, hết quyền đúng lúc và để lại bằng chứng cần thiết.

Khái niệm này rộng hơn việc tiến trình còn chạy hay trang đăng nhập trả HTTP 200. Giao diện có thể hoạt động trong khi vault không cấp được credential; broker có thể mở phiên nhưng recorder không lưu được bản ghi; hệ thống có thể trả credential nhanh nhưng không thực thi được việc thu hồi quyền sau thời hạn JIT. Những trường hợp đó đều ảnh hưởng đến sức khỏe PAM.

Trong module kiểm soát tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm, theo dõi PAM service health nhằm bảo vệ đồng thời ba mục tiêu:

- **Khả dụng:** người dùng và workload hợp lệ tiếp cận được tài nguyên theo nhu cầu đã phê duyệt.
- **Tính đúng đắn của kiểm soát:** chính sách, thời hạn quyền, danh tính và cơ chế bảo vệ hoạt động đúng.
- **Khả năng chứng minh:** sự kiện kiểm toán, bản ghi phiên và kết quả thao tác được lưu, truy xuất và liên kết đủ để điều tra.

Không thể coi PAM khỏe chỉ vì một trong ba mục tiêu đạt yêu cầu. Mặt khác, mất một chức năng phụ trợ không nhất thiết đồng nghĩa phải ngắt toàn bộ phiên đang chạy. Cần xác định ảnh hưởng theo từng năng lực, tài nguyên và chính sách.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt process health, dependency health và end-to-end service health.
2. Xây dựng ma trận sức khỏe cho vault, broker, connector, recorder và các thành phần liên quan.
3. Chọn SLI, SLO, health probe và synthetic transaction phù hợp.
4. Phân loại tình trạng suy giảm và thiết kế cảnh báo có thể hành động.
5. Điều tra một sự cố sức khỏe PAM mà vẫn bảo toàn kiểm soát truy cập và bằng chứng.

## 2. Đánh giá sức khỏe theo luồng nghiệp vụ

Một lượt truy cập đặc quyền có thể đi qua chuỗi sau:

~~~text
Người dùng hoặc workload
        |
        v
Xác thực danh tính -> kiểm tra chính sách/phê duyệt
        |
        v
Cấp quyền JIT hoặc cấp credential từ vault
        |
        v
Broker/connector -> tài nguyên đích
        |
        +-> ghi nhận và lưu bằng chứng
        |
        v
Kết thúc phiên -> thu hồi quyền/credential theo chính sách
~~~

Đây là mô hình khái niệm. Một triển khai có thể không dùng broker, có thể cấp credential cho ứng dụng qua API, hoặc sử dụng chứng thư ngắn hạn thay cho mật khẩu. Phải lập bản đồ theo kiến trúc thực tế trước khi thiết kế giám sát.

Ví dụ, luồng quản trị máy chủ qua broker cần kiểm tra việc thiết lập phiên và ghi hình. Luồng cấp secret cho ứng dụng cần kiểm tra xác thực workload, chính sách đọc, độ trễ API và tính dùng được của secret. Một kết quả xanh của luồng thứ nhất không chứng minh luồng thứ hai khỏe.

### Bốn lớp kiểm tra bổ sung cho nhau

| Lớp kiểm tra | Câu hỏi trả lời | Ví dụ | Điều không chứng minh được |
|---|---|---|---|
| Tiến trình | Thành phần còn thực thi được không? | Tiến trình chạy, event loop phản hồi | Người dùng có truy cập được tài nguyên hay không |
| Phụ thuộc | Thành phần kết nối và dùng được dịch vụ nền không? | Truy vấn DB, đọc khóa mã hóa, ghi object thử | Toàn bộ luồng cấp quyền có đúng chính sách không |
| Chức năng | Một năng lực PAM có thực hiện được không? | Kiểm tra policy, cấp chứng thư thử | Các năng lực khác có hoạt động hay không |
| Đầu cuối | Luồng đại diện có hoàn tất và để lại bằng chứng không? | Phiên thử có kiểm soát, kết thúc, xác nhận audit | Mọi loại tài nguyên và mọi tình huống đều khỏe |

Không có một phép kiểm tra đơn lẻ thay thế được cả bốn lớp. Kết hợp phép kiểm tra bên trong thành phần với phép kiểm tra từ phía người sử dụng giúp phát hiện cả lỗi cục bộ và lỗi trên đường truyền dịch vụ.

## 3. Lập danh mục thành phần và phụ thuộc

Mỗi thành phần cần có chủ sở hữu vận hành, phạm vi phục vụ, tín hiệu giám sát, mức ảnh hưởng và hướng xử lý khi lỗi. Danh mục này phải phản ánh cả đường cấp quyền và đường thu hồi quyền.

| Thành phần hoặc phụ thuộc | Dấu hiệu cần theo dõi | Ảnh hưởng điển hình khi lỗi |
|---|---|---|
| Cổng API/giao diện PAM | Tỷ lệ lỗi, độ trễ, TLS, số kết nối | Yêu cầu mới thất bại hoặc chậm |
| IdP, MFA và liên kết danh tính | Lỗi xác thực, timeout, metadata/chứng thư hết hạn | Người dùng mới không xác thực được |
| Policy engine và phê duyệt | Độ trễ quyết định, phiên bản policy, hàng đợi phê duyệt | Cấp quyền bị chặn hoặc quyết định sai lệch |
| Vault và dịch vụ khóa | Khả năng giải mã, trạng thái seal nếu có, quyền truy cập khóa | Không lấy hoặc cập nhật credential được |
| Cơ sở dữ liệu/metadata store | Độ trễ, replication lag, dung lượng, khả năng ghi | Mất đồng bộ trạng thái yêu cầu hoặc phiên |
| Broker/proxy phiên | Phiên mới, phiên đang chạy, ngắt kết nối, giới hạn tài nguyên | Không mở được phiên hoặc phiên bị gián đoạn |
| Connector tới tài nguyên | Kết nối mạng, xác thực, phiên bản tương thích, timeout | Lỗi tập trung ở một nhóm tài nguyên |
| Rotation engine | Job trễ, thất bại, tài khoản không đồng bộ | Credential cũ tồn tại hoặc ứng dụng mất truy cập |
| Recorder và kho bản ghi | Ghi thành công, backlog, dung lượng, khả năng đọc lại | Bằng chứng không đủ hoặc không truy xuất được |
| Audit pipeline/SIEM | Sự kiện gửi/nhận, hàng đợi, tuổi sự kiện cũ nhất | Phát hiện và điều tra bị chậm |
| Bộ lập lịch thu hồi JIT | Quyền quá hạn, job trễ, xác nhận thu hồi | Đặc quyền còn tồn tại sau thời gian cho phép |
| DNS, mạng, thời gian và PKI | Phân giải, mất gói, clock offset, hạn chứng thư | Lỗi liên thành phần hoặc sai xác thực |
| Dịch vụ backup/restore | Tuổi bản sao tốt cuối cùng, kết quả phục hồi thử | Khả năng khôi phục không đạt yêu cầu |

CPU, RAM và dung lượng là tín hiệu nguyên nhân hoặc nguy cơ. Chúng cần thiết nhưng không trực tiếp thay thế cho tỷ lệ cấp quyền thành công, độ trễ mở phiên hay số quyền quá hạn.

### Chú ý phạm vi ảnh hưởng

Cùng một lỗi connector nhưng kết quả có thể rất khác:

- Một connector dự phòng lỗi trong khi connector còn lại đủ năng lực: giảm khả năng chịu lỗi.
- Connector duy nhất của một vùng lỗi: vùng đó mất khả năng mở phiên mới.
- Connector phục vụ tài khoản phục hồi hạ tầng lỗi: ảnh hưởng đặc biệt nghiêm trọng dù số phiên ít.

Vì vậy, mỗi tín hiệu cần gắn với năng lực và vùng phục vụ. Tỷ lệ thành công gộp toàn hệ thống có thể che khuất một nhóm tài nguyên nhỏ nhưng quan trọng.

## 4. Mô hình trạng thái sức khỏe

Có thể sử dụng các trạng thái sau để truyền đạt tình hình vận hành:

| Trạng thái | Ý nghĩa | Cách diễn giải |
|---|---|---|
| Healthy | Các năng lực trong phạm vi đáp ứng tiêu chí đã định | Tiếp tục phục vụ và theo dõi |
| Degraded | Vẫn phục vụ được nhưng mất một phần năng lực, hiệu năng hoặc dự phòng | Hiển thị rõ năng lực và phạm vi suy giảm |
| Unavailable | Không thực hiện được năng lực yêu cầu | Chặn hoặc định tuyến yêu cầu theo chính sách |
| Unknown | Không có dữ liệu đủ mới hoặc phép đo không đáng tin cậy | Điều tra mất khả năng quan sát |
| Maintenance | Đang bảo trì có kế hoạch và có phạm vi được xác nhận | Đánh giá ảnh hưởng thực tế trong cửa sổ bảo trì |

Maintenance là bối cảnh vận hành, không phải bằng chứng dịch vụ khỏe. Trong cửa sổ bảo trì vẫn phải thấy những năng lực bị gián đoạn và các sai lệch ngoài dự kiến.

### Không lấy trung bình các trạng thái

Giả sử chín connector khỏe, một connector lỗi. Hiển thị “90% khỏe” không giúp người quản trị biết tài nguyên mình cần có truy cập được không. Tương tự, việc vault khỏe không bù được recorder mất khả năng lưu bằng chứng bắt buộc.

Nên tổng hợp theo quy tắc phụ thuộc:

~~~text
Năng lực mở phiên được ghi lại
    cần: xác thực + policy + vault phù hợp + broker
          + connector đích + recording path theo chính sách
~~~

Nếu thiếu một điều kiện bắt buộc, năng lực đó không đạt yêu cầu dù những thành phần khác vẫn xanh. Dashboard tổng quan nên cho phép đi từ trạng thái năng lực xuống thành phần gây ảnh hưởng.

### Dữ liệu cũ phải chuyển thành Unknown

Một exporter báo khỏe lúc 10:00 rồi ngừng gửi dữ liệu không thể tiếp tục được hiển thị xanh lúc 10:30. Mỗi kết quả cần có thời điểm quan sát và giới hạn độ mới. Giám sát cần phát hiện riêng tình trạng mất scrape, mất heartbeat và không chạy được synthetic check.

## 5. SLI và SLO cho PAM service health

**SLI** là phép đo thể hiện chất lượng dịch vụ. **SLO** là mục tiêu chất lượng đặt lên SLI trong một khoảng thời gian. Mục tiêu phải gắn với nhu cầu nghiệp vụ, chính sách an toàn và khả năng vận hành.

Các giá trị số trong bài là ví dụ để luyện thiết kế, không phải chuẩn chung cho mọi hệ thống PAM.

### 5.1. Tỷ lệ hoàn tất yêu cầu hợp lệ

Một SLI cấp credential có thể được định nghĩa:

~~~text
Tỷ lệ thành công =
  Số yêu cầu hợp lệ được xử lý đúng và hoàn tất trong ngưỡng thời gian
  ----------------------------------------------------------------
  Tổng số yêu cầu hợp lệ trong phạm vi đo
~~~

Cần định nghĩa “hợp lệ” và “xử lý đúng” trước khi đếm:

- Yêu cầu sai định dạng hoặc bị từ chối đúng policy không nên tự động được tính là sự cố khả dụng.
- IdP hoặc policy service timeout làm người dùng hợp lệ không tiếp tục được phải được phản ánh theo phạm vi SLO đã thống nhất.
- Credential được trả về nhưng không dùng được do trạng thái rotation không đồng bộ không phải kết quả thành công đầu cuối.
- Việc loại trừ yêu cầu phải có quy tắc minh bạch; không loại trừ lỗi chỉ để cải thiện chỉ số.

Theo dõi riêng tỷ lệ từ chối chính sách, lỗi xác thực, lỗi hạ tầng và lỗi đích. Sự tăng đột ngột của các lần từ chối cũng có thể chỉ ra cấu hình sai hoặc hành vi bất thường, dù không thuộc mẫu số của SLI khả dụng.

### 5.2. Độ trễ theo từng giai đoạn

Độ trễ toàn luồng giúp mô tả trải nghiệm; độ trễ từng chặng giúp tìm nguyên nhân:

~~~text
Thời gian hoàn tất yêu cầu =
  xác thực + chờ phê duyệt + quyết định policy
  + cấp quyền/credential + kết nối đích
~~~

Thời gian chờ người phê duyệt thường có đặc tính khác độ trễ xử lý máy. Nên tách chúng thành chỉ số riêng, đồng thời giữ một góc nhìn toàn luồng. Không báo API nhanh để bỏ qua việc yêu cầu bị kẹt trong hàng đợi phê duyệt.

Dùng phân vị như p95 hoặc p99 khi phù hợp, kèm số lượng mẫu. Trung bình thấp có thể che giấu một nhóm yêu cầu rất chậm. Phân vị từ lưu lượng cực thấp cũng có thể thiếu ổn định; synthetic check và số đếm lỗi giúp bổ sung bối cảnh.

### 5.3. Sức khỏe của kiểm soát và bằng chứng

Một bộ SLI cân bằng có thể gồm:

| Năng lực | SLI minh họa | Lưu ý |
|---|---|---|
| Mở phiên | Tỷ lệ phiên thử mở được trong ngưỡng | Phân tách theo giao thức và vùng |
| Cấp credential | Tỷ lệ yêu cầu hợp lệ hoàn tất | Không ghi giá trị secret vào telemetry |
| Thu hồi JIT | Tỷ lệ quyền được xác nhận thu hồi đúng hạn | Xác nhận tại đích khi kiến trúc cho phép |
| Rotation | Tỷ lệ job đến hạn hoàn tất và được kiểm tra | Theo dõi cả tuổi job quá hạn |
| Recording | Tỷ lệ phiên thuộc diện bắt buộc có bản ghi dùng được | “Upload thành công” chưa đủ chứng minh bản ghi đọc được |
| Audit | Tỷ lệ sự kiện tới đích trong ngưỡng | Kiểm tra cả mất sự kiện và độ trễ |
| Dự phòng | Số miền phục vụ còn đủ điều kiện | Thành công hiện tại không chứng minh còn khả năng failover |
| Quan sát | Tỷ lệ phép kiểm tra hoàn tất đúng lịch | Phân biệt lỗi dịch vụ với lỗi bộ kiểm tra |

Với các ràng buộc an toàn như cấp sai quyền, không nên coi error budget khả dụng là quyền cho phép vi phạm. Những vi phạm này cần tiêu chí kiểm soát và xử lý riêng.

### 5.4. Ví dụ cách đặt mục tiêu

Một đội có thể đặt mục tiêu thử nghiệm: trong 30 ngày, 99,9% yêu cầu cấp credential hợp lệ ở vùng sản xuất hoàn tất trong hai giây. Với SLO theo yêu cầu, error budget là 0,1% số yêu cầu thuộc phạm vi đo; không tự chuyển thành một số phút downtime cố định.

Đội cũng có thể đặt mục tiêu riêng: mọi quyền JIT hết hạn phải được phát hiện nếu chưa có xác nhận thu hồi sau khoảng trễ cho phép. Đây là mục tiêu kiểm soát trạng thái, không nên gộp vào SLO độ trễ API.

## 6. Thiết kế health endpoint và probe

Ba loại phép kiểm tra phổ biến có mục đích khác nhau.

| Probe | Mục đích | Nên kiểm tra | Tránh đưa vào |
|---|---|---|---|
| Liveness | Phát hiện tiến trình không còn tự phục hồi | Khả năng phản hồi nội bộ, deadlock hoặc tình trạng tương đương | Mọi phụ thuộc ngoài mạng |
| Readiness | Xác định instance có nhận được loại yêu cầu mới không | Các điều kiện bắt buộc để phục vụ đúng năng lực | Phép kiểm tra nặng hoặc gây thay đổi nghiệp vụ |
| Startup | Cho phép khởi động trong thời gian hợp lý | Hoàn tất nạp cấu hình, khởi tạo và kiểm tra ban đầu | Cơ chế che vô thời hạn lỗi khởi động |

Tên và hành vi cụ thể tùy nền tảng triển khai. Không giả định sản phẩm PAM nào cũng cung cấp sẵn ba endpoint như nhau.

### 6.1. Tại sao liveness không nên phụ thuộc toàn bộ hạ tầng?

Nếu IdP gặp sự cố, mọi instance PAM cùng thất bại liveness rồi khởi động lại, sự cố IdP có thể kéo theo gián đoạn broker, mất cache và tăng tải đăng nhập. Việc restart cũng không sửa được IdP.

Hãy để cảnh báo phụ thuộc thể hiện lỗi IdP. Readiness đánh giá instance có phục vụ an toàn luồng yêu cầu liên quan không. Liveness chỉ kích hoạt restart khi có bằng chứng tiến trình đang hỏng theo cách restart có thể giải quyết.

### 6.2. Readiness cần phân biệt loại yêu cầu

Một instance có thể không nhận phiên mới nhưng vẫn phục vụ phiên hiện có. Đưa instance ra khỏi tập nhận yêu cầu mới không đồng nghĩa phải giết kết nối đang chạy.

Nếu hạ tầng chỉ hỗ trợ một readiness chung, cần hiểu rõ hệ quả của nó đối với từng cổng, loại traffic và kết nối dài. Cơ chế drain phải có giới hạn thời gian, theo dõi phiên còn lại và quy trình xử lý phiên không kết thúc.

### 6.3. Phản hồi sức khỏe minh họa

~~~json
{
  "status": "degraded",
  "observedAt": "2026-01-15T03:20:00Z",
  "capabilities": {
    "credentialIssue": "healthy",
    "newRecordedSession": "unavailable",
    "existingSessionForwarding": "healthy"
  },
  "checks": [
    {
      "name": "recording-storage",
      "status": "unavailable",
      "reasonCode": "WRITE_TIMEOUT"
    }
  ]
}
~~~

Đây là schema minh họa, không phải API của một sản phẩm cụ thể. Endpoint công khai hoặc do load balancer gọi nên trả thông tin tối thiểu. Chi tiết thành phần, topology, lỗi khóa hoặc định danh tài khoản chỉ nên có trên kênh vận hành được bảo vệ.

Health check không được trả credential, token, chuỗi kết nối có mật khẩu hay nội dung phiên. Đồng thời, không thể yêu cầu một endpoint liveness phải đi qua toàn bộ IdP đang được chính nó kiểm tra, vì điều đó tạo phụ thuộc vòng.

## 7. Synthetic transaction đầu cuối

Synthetic transaction là một luồng thử chủ động, có kiểm soát, đại diện cho hành vi sử dụng thật. Nó giúp phát hiện trường hợp mọi thành phần báo khỏe nhưng luồng thực tế không hoàn tất.

### 7.1. Một luồng thử có phạm vi rõ ràng

Ví dụ kiểm tra phiên quản trị thử nghiệm:

1. Dùng danh tính kiểm thử riêng, được quản lý và giới hạn quyền.
2. Yêu cầu truy cập đúng một tài nguyên canary.
3. Đi qua policy và cơ chế phê duyệt được thiết kế cho luồng canary.
4. Mở phiên qua cùng đường dịch vụ cần kiểm tra.
5. Thực hiện thao tác không phá hủy, chẳng hạn đọc thời gian hoặc một marker vô hại.
6. Kết thúc phiên.
7. Kiểm tra có sự kiện audit, bản ghi theo chính sách và xác nhận đóng phiên.
8. Xác nhận quyền tạm đã được thu hồi nếu bài thử có cấp quyền JIT.

Luồng kiểm thử tự động không mặc nhiên chứng minh MFA tương tác hay quy trình phê duyệt của con người khỏe. Nếu canary dùng policy hoặc xác thực khác, phải ghi rõ phần nào được bao phủ và phần nào chưa được kiểm tra.

### 7.2. Yêu cầu đối với tài nguyên canary

Tài nguyên canary cần nằm trên đường dịch vụ đại diện nhưng có phạm vi ảnh hưởng thấp. Tài khoản thử không được có quyền quản trị toàn miền chỉ để thuận tiện. Credential của tài khoản thử vẫn phải chịu cơ chế bảo vệ phù hợp và không xuất hiện trong log của bộ kiểm tra.

Thiết kế phép thử cần có:

- Timeout tổng và timeout từng chặng.
- Mã tương quan để nối kết yêu cầu, phiên, audit và bản ghi.
- Hạn mức tần suất để không chiếm session slot hoặc gây lockout.
- Cleanup idempotent và phát hiện tài nguyên/quyền còn sót.
- Kênh theo dõi chính bộ kiểm tra.
- Phân tách traffic thử với traffic thật trong phân tích, nhưng không dùng nhãn synthetic làm lý do loại bỏ kết quả bất lợi.

Không thử rotation trên tài khoản dịch vụ sản xuất tùy tiện. Nếu cần kiểm tra rotation đầu cuối, dùng tài khoản canary chuyên dụng và cơ chế kiểm tra trước/sau được thiết kế riêng.

### 7.3. Tránh một canary tạo cảm giác bao phủ toàn bộ

Một canary ở cùng subnet với broker không phát hiện được mọi lỗi từ văn phòng từ xa. Một canary Linux không chứng minh connector tới database hoạt động.

Chọn tập kiểm thử theo các đường dịch vụ quan trọng: vùng mạng, giao thức, nhóm broker, loại tài nguyên và cách xác thực. Không cần nhân mọi tổ hợp một cách vô hạn; ưu tiên những khác biệt tạo ra miền lỗi thực sự.

## 8. Metrics, log và trace

Ba loại telemetry hỗ trợ nhau:

- **Metrics:** phát hiện xu hướng và vượt ngưỡng với chi phí truy vấn thấp.
- **Log:** mô tả sự kiện và nguyên nhân cụ thể.
- **Trace hoặc correlation ID:** nối các chặng của một yêu cầu qua nhiều dịch vụ.

Mỗi bản ghi sức khỏe nên có thời gian, thành phần, kết quả, mã lỗi có cấu trúc và định danh tương quan phù hợp. Cần đồng bộ thời gian vì clock lệch làm sai phép đo tuổi sự kiện, hết hạn quyền và thứ tự điều tra.

### 8.1. Kiểm soát cardinality và dữ liệu nhạy cảm

Không dùng giá trị credential, token, command đầy đủ hay session ID làm nhãn metrics. Không gắn mọi tên tài khoản, hostname và request ID vào chuỗi thời gian vì vừa tăng số lượng series vừa có thể lộ thông tin.

Các chiều thường hữu ích là region, component, capability, protocol và nhóm lỗi có tập giá trị giới hạn. Chi tiết từng tài khoản hoặc phiên nên nằm trong hệ thống sự kiện được phân quyền phù hợp, với chính sách lưu giữ rõ ràng.

### 8.2. Ví dụ chỉ số và truy vấn

Các tên metrics dưới đây hoàn toàn minh họa. Cần ánh xạ lại với exporter và ngữ nghĩa thực tế trước khi áp dụng:

~~~text
pam_requests_total{capability, result, region}
pam_request_duration_seconds_bucket{capability, region, le}
pam_rotation_overdue_accounts{region}
pam_jit_overdue_grants{region}
pam_audit_oldest_pending_age_seconds{region}
pam_recording_storage_free_bytes{region}
pam_synthetic_last_success_timestamp_seconds{check, region}
~~~

Với quy ước bộ đếm request chỉ gồm yêu cầu thuộc SLI và result là success hoặc error, tỷ lệ lỗi có thể được biểu diễn:

~~~promql
sum by (region) (
  rate(pam_requests_total{
    capability="credential_issue",
    result="error"
  }[5m])
)
/
sum by (region) (
  rate(pam_requests_total{
    capability="credential_issue"
  }[5m])
)
~~~

Không có request không đồng nghĩa tỷ lệ lỗi bằng không. Khi mẫu số bằng không hoặc series biến mất, truy vấn có thể không cho kết quả hữu ích. Cần kiểm tra lưu lượng tối thiểu, exporter còn được thu thập và kết quả synthetic riêng; không tự biến dữ liệu thiếu thành trạng thái khỏe.

Ví dụ phát hiện canary đã quá lâu chưa thành công:

~~~promql
time() - pam_synthetic_last_success_timestamp_seconds > 300
~~~

Truy vấn này chỉ hữu ích khi series vẫn tồn tại và timestamp có ngữ nghĩa đúng. Phải có cảnh báo riêng cho trường hợp metric biến mất, bộ kiểm tra dừng, hoặc exporter không được thu thập. Ngưỡng 300 giây chỉ minh họa.

Nếu sử dụng histogram để tính p95, phải giữ nhãn bucket cần thiết và chỉ gộp các phân phối tương thích. Không lấy trung bình các p95 của từng instance rồi gọi đó là p95 toàn dịch vụ.

## 9. Cảnh báo có thể hành động

Một cảnh báo tốt cần trả lời: năng lực nào bị ảnh hưởng, phạm vi ở đâu, bằng chứng gì, ai xử lý và bước đầu tiên là gì.

### 9.1. Phân tầng theo ảnh hưởng

| Mức tình huống | Ví dụ | Hành động phù hợp |
|---|---|---|
| Mất năng lực quan trọng | Mọi yêu cầu mở phiên ở vùng trọng yếu thất bại | Gọi trực vận hành, mở incident |
| Suy giảm dự phòng | Một broker lỗi nhưng hệ thống còn đủ tải | Xử lý theo mức rủi ro và thời gian chịu lỗi |
| Nguy cơ tích lũy | Dung lượng recording tăng, dự báo chạm ngưỡng | Lập hành động trước khi hết chỗ |
| Vi phạm kiểm soát | Quyền JIT quá hạn chưa thu hồi | Chuyển đúng đầu mối an ninh/vận hành |
| Mất khả năng quan sát | Canary và exporter đều không có dữ liệu mới | Điều tra đường giám sát, không kết luận PAM khỏe |

Mức độ nghiêm trọng phụ thuộc tài nguyên và chính sách. Một quyền đặc biệt quá hạn có thể cần xử lý gấp dù chỉ ảnh hưởng một tài khoản.

### 9.2. Tách symptom và cause

Cảnh báo symptom mô tả điều người dùng hoặc kiểm soát đang chịu: không mở được phiên, không có bằng chứng, thu hồi trễ. Cảnh báo cause gợi ý nguyên nhân: DB latency tăng, DNS lỗi, storage chậm.

Dùng grouping và inhibition phù hợp để tránh hàng trăm thông báo khi một phụ thuộc chung lỗi. Tuy nhiên, phải giữ được các tín hiệu khác bản chất, chẳng hạn mất khả dụng và quyền không thu hồi. Không tắt mọi cảnh báo con nếu điều đó che mất rủi ro kiểm soát.

### 9.3. Tránh ngưỡng gây dao động

Có thể yêu cầu lỗi liên tiếp hoặc duy trì trong một khoảng thời gian trước khi gửi cảnh báo; đồng thời dùng điều kiện hồi phục ổn định. Với lỗi nghiêm trọng như cấp sai quyền, không nên dùng khoảng chờ dài chỉ để giảm nhiễu.

Đối với error budget, cảnh báo burn rate nhiều cửa sổ giúp nhận biết cả sự cố nhanh và suy giảm kéo dài. Phải chọn cửa sổ và ngưỡng từ SLO cụ thể, không sao chép một công thức chung mà bỏ qua lưu lượng và hậu quả.

### 9.4. Nội dung một cảnh báo minh họa

~~~yaml
alert: PAMRecordedSessionUnavailable
scope:
  region: dc-a
  capability: new_recorded_session
evidence:
  synthetic_failures: 3
  failure_stage: recording_finalize
impact: "Chưa xác nhận được khả năng hoàn tất phiên có bản ghi tại dc-a"
owner: pam-oncall
first_action: "Kiểm tra recorder, hàng đợi và recording storage theo runbook"
~~~

Đây là nội dung mô tả cảnh báo, không phải cấu hình trực tiếp cho một hệ thống giám sát cụ thể. Không nhúng secret hoặc URL quản trị chứa token vào thông báo.

## 10. HA, capacity và trạng thái suy giảm

High availability chỉ có ý nghĩa khi hệ thống còn phục vụ đúng chức năng sau sự cố. Hai instance cùng chạy nhưng dùng chung một phụ thuộc đơn lẻ chưa tạo ra khả năng chịu lỗi toàn luồng.

### 10.1. Theo dõi dự phòng thực tế

Cần biết instance nào đủ điều kiện nhận traffic, instance nào đang drain và phần năng lực còn lại sau khi mất một miền lỗi. Theo dõi thêm:

- Số phiên hiện có và tốc độ tăng phiên mới.
- Giới hạn kết nối, hàng đợi và thread/worker pool.
- Dung lượng, độ trễ và tốc độ ghi bản ghi phiên.
- Replication lag và tính mới của trạng thái policy/credential.
- Khả năng tiếp cận dịch vụ khóa và lưu trữ từ từng miền.
- Trạng thái quorum hoặc cơ chế bầu chọn nếu sản phẩm sử dụng.
- Headroom để phục vụ tải khi mất một node hoặc một vùng.

Cách tính quorum, failover và điều kiện phục vụ phụ thuộc sản phẩm. Không áp dụng quy tắc chung như “luôn chỉ cần hai node” cho mọi kiến trúc.

### 10.2. Không tự động hóa failover một cách mù quáng

Khi mạng phân vùng, việc hai nơi cùng nhận ghi có thể gây xung đột trạng thái credential hoặc quyền. Failover cần cơ chế xác định chủ thể được quyền phục vụ, kiểm soát writer và fencing theo kiến trúc được hỗ trợ.

Giám sát phải cho thấy vai trò, điều kiện nhận traffic và tính nhất quán cần thiết. Thấy node còn sống chưa đủ để kết luận node được phép phục vụ.

### 10.3. Khi hệ thống suy giảm

Trước mỗi tình huống, cần quy định năng lực nào tiếp tục, năng lực nào chặn và điều kiện phục hồi. Ví dụ:

| Sự cố | Cách ứng xử cần xác định trước |
|---|---|
| Không truy cập được IdP | Hành vi với đăng nhập mới, phiên hiện có và cơ chế phục hồi đã duyệt |
| Recording storage lỗi | Quy tắc cho phiên bắt buộc ghi lại; khả năng đệm cục bộ và giới hạn đệm |
| Rotation lỗi | Khoanh vùng tài khoản, xác định credential đang có hiệu lực, bảo vệ ứng dụng |
| Audit sink lỗi | Chính sách buffer, cảnh báo tuổi backlog, điều kiện giới hạn yêu cầu mới |
| Policy không tải được | Có cho dùng bản đã xác minh còn hiệu lực không; hết hiệu lực thì xử lý ra sao |

Không tự biến sự cố PAM thành lý do bỏ MFA, kéo dài quyền JIT vô hạn hoặc cấp mật khẩu quản trị dùng chung. Break-glass, nếu cần, phải theo cơ chế đã phê duyệt, có xác thực, phạm vi và bằng chứng riêng.

## 11. Runbook điều tra sự cố sức khỏe

Một runbook hiệu quả cần đủ ngắn để dùng khi có áp lực nhưng đủ cụ thể để tránh thao tác theo cảm tính.

### Bước 1: Xác nhận ảnh hưởng và độ mới dữ liệu

Kiểm tra thời điểm lỗi đầu tiên, luồng bị ảnh hưởng, vùng tài nguyên và số người dùng/workload liên quan. Xác nhận exporter và canary còn chạy. Không kết luận dịch vụ đã phục hồi chỉ vì đồ thị ngừng nhận dữ liệu.

### Bước 2: Tách lỗi theo chặng

Dùng correlation ID hoặc mẫu sự kiện để xác định lỗi ở xác thực, policy, cấp credential, broker, connector, tài nguyên đích hay bằng chứng. Phân biệt lỗi chung với lỗi chỉ trên một loại đích.

Không yêu cầu người dùng gửi mật khẩu hoặc token để tái hiện. Thu thập mã lỗi, thời gian, mã yêu cầu và thông tin đã khử nhạy cảm.

### Bước 3: Kiểm tra thay đổi gần thời điểm sự cố

Đối chiếu triển khai mới, thay chứng thư, chỉnh firewall/DNS, cập nhật policy, rotation tài khoản phụ thuộc và thay đổi lưu trữ. Mối tương quan thời gian là đầu mối điều tra, chưa phải bằng chứng nguyên nhân.

### Bước 4: Khoanh vùng và giảm ảnh hưởng

Thực hiện theo runbook: drain instance hỏng, chuyển traffic sang miền đủ điều kiện, tạm dừng một loại job lỗi hoặc giới hạn yêu cầu mới nếu chính sách yêu cầu. Mọi thao tác phải có người chịu trách nhiệm và dấu vết thực hiện.

Không xóa hàng đợi audit/recording để làm dashboard hết đỏ. Không chạy rotation hàng loạt khi chưa xác định tình trạng credential tại vault và tài nguyên đích.

### Bước 5: Xác nhận phục hồi đầu cuối

Sau khi sửa nguyên nhân, thực hiện synthetic transaction đại diện. Kiểm tra cả việc mở và kết thúc phiên, lưu bằng chứng, xử lý backlog và thu hồi quyền. Một endpoint trở lại HTTP 200 mới chỉ chứng minh một phần.

### Bước 6: Theo dõi hậu quả còn lại

Hệ thống có thể phục vụ lại trong khi audit backlog vẫn tăng hoặc credential một số tài khoản chưa đồng bộ. Theo dõi cho tới khi các hậu quả này được xử lý hoặc được bàn giao với chủ sở hữu, thời hạn và mức rủi ro rõ ràng.

## 12. Tình huống thực hành: dashboard xanh nhưng không có bản ghi dùng được

Một tổ chức có hai broker và một recorder dùng chung object storage. Sau thay đổi chính sách truy cập storage, người dùng vẫn mở được phiên nhưng bản ghi không hoàn tất.

Quan sát ban đầu:

~~~text
API success rate:                 99,98%
Broker process liveness:          PASS
New session establishment:       PASS
Recording finalize errors:       tăng
Oldest pending recording age:    tăng từ 20 giây lên 8 phút
Synthetic recorded session:      FAIL tại bước xác nhận bản ghi
~~~

### 12.1. Vì sao trạng thái xanh ban đầu sai?

Dashboard chỉ dựa vào khả năng mở phiên và tiến trình broker. Nó chưa mô hình hóa năng lực “phiên có bằng chứng dùng được”. Recorder có thể ghi tạm nhưng không có quyền hoàn tất object; việc mở phiên thành công không phát hiện lỗi này.

### 12.2. Cách điều tra

1. Xác nhận synthetic check còn hoạt động và lỗi tập trung ở recording.
2. Kiểm tra lỗi storage đã khử nhạy cảm cùng thời điểm thay đổi policy.
3. Xác định bản ghi đang ở đâu, còn bao nhiêu dung lượng buffer và có nguy cơ mất dữ liệu không.
4. Áp dụng quy tắc nhận phiên mới theo yêu cầu recording của từng nhóm tài nguyên.
5. Khôi phục quyền storage đúng phạm vi thay vì cấp quyền toàn bộ kho.
6. Xác nhận một phiên canary có bản ghi mở được, thời lượng hợp lý và sự kiện liên kết đầy đủ.
7. Theo dõi backlog, kiểm tra những phiên bị ảnh hưởng và lưu bằng chứng xử lý.

Nếu storage được khôi phục nhưng một số bản ghi đã mất, trạng thái phục vụ hiện tại có thể đã tốt lên nhưng incident chưa thể coi là không có hậu quả. Cần ghi nhận khoảng trống bằng chứng và chuyển xử lý theo quy trình tương ứng.

### 12.3. Cải thiện thiết kế giám sát

Bổ sung health theo năng lực, synthetic check có xác nhận bản ghi, cảnh báo tuổi backlog và theo dõi dung lượng đệm. Dashboard cần thể hiện rõ phạm vi phiên bắt buộc recording và mức ảnh hưởng khi recorder suy giảm.

## 13. Kiểm tra sức khỏe định kỳ ngoài giám sát liên tục

Không phải mọi năng lực đều phù hợp với kiểm tra mỗi phút. Một chương trình sức khỏe PAM nên có các lớp theo nhịp độ khác nhau:

| Nhịp kiểm tra | Nội dung đại diện | Kết quả cần lưu |
|---|---|---|
| Liên tục | Request, lỗi, tài nguyên, heartbeat, backlog | Chuỗi thời gian và cảnh báo |
| Theo lịch ngắn | Canary cấp quyền, mở phiên, thu hồi | Kết quả từng chặng và độ bao phủ |
| Sau thay đổi | Policy, connector, TLS, storage, deployment | Bằng chứng kiểm tra trên phạm vi thay đổi |
| Định kỳ phục hồi | Failover và restore có kiểm soát | Thời gian phục hồi, dữ liệu phục hồi và sai lệch |
| Rà soát vận hành | SLO, cảnh báo nhiễu, điểm mù, công suất | Hành động cải tiến có chủ sở hữu |

Backup job báo thành công không chứng minh restore được vault và metadata. Phục hồi thử cần kiểm tra cả dữ liệu, khả năng sử dụng khóa, các phụ thuộc và tính dùng được của hệ thống theo kế hoạch đã phê duyệt.

Thử failover cần có phạm vi và tiêu chí dừng rõ ràng. Không thực hiện thử nghiệm gây gián đoạn trên hệ thống sản xuất chỉ vì bài giám sát yêu cầu “kiểm tra HA”.

## 14. Dashboard vận hành tối thiểu

Một dashboard hữu ích nên cho phép trả lời các câu hỏi sau mà không phải ghép thủ công nhiều màn hình:

1. Năng lực nào đang Healthy, Degraded, Unavailable hoặc Unknown?
2. Người dùng và workload ở vùng nào bị ảnh hưởng?
3. Mở phiên, cấp credential, rotation và thu hồi JIT có đáp ứng mục tiêu không?
4. Audit và recording có đầy đủ, đủ mới và truy xuất được không?
5. Hệ thống còn bao nhiêu dự phòng và công suất?
6. Phụ thuộc nào đang lỗi và có thay đổi nào liên quan?
7. Dữ liệu vừa hiển thị được quan sát lúc nào?

Không nên chỉ dùng một ô xanh/đỏ toàn cục. Tổ chức màn hình theo năng lực, sau đó tới vùng và thành phần. Trên cùng màn hình cần thấy thời điểm cập nhật, cửa sổ đo, số lượng mẫu và liên kết runbook.

Dashboard cho vận hành PAM có thể chứa thông tin hạ tầng nhạy cảm. Phân quyền xem và che dữ liệu cần đi cùng thiết kế telemetry; không xuất topology hoặc danh sách tài khoản đặc quyền ra màn hình công khai.

## 15. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ theo dõi CPU/RAM | Bỏ sót lỗi policy và luồng nghiệp vụ | Thêm SLI theo năng lực và canary |
| HTTP 200 là điều kiện khỏe duy nhất | Trang đăng nhập xanh nhưng không dùng được PAM | Xác minh chức năng và kết quả đầu cuối |
| Liveness gọi mọi phụ thuộc | Restart dây chuyền khi phụ thuộc lỗi | Tách liveness, readiness và dependency check |
| Dữ liệu mất được chuyển thành số 0 | Mất quan sát bị hiểu là hết lỗi | Hiển thị Unknown và cảnh báo thiếu dữ liệu |
| Gộp mọi vùng vào một tỷ lệ | Che khuất miền lỗi nhỏ nhưng quan trọng | Phân tách theo miền phục vụ |
| Canary có quyền quá rộng | Biến công cụ giám sát thành tài khoản đặc quyền nguy hiểm | Dùng quyền tối thiểu và tài nguyên thử riêng |
| Chỉ xác nhận gửi audit | Không phát hiện mất dữ liệu sau khâu gửi | Theo dõi tiếp nhận, độ trễ và đối soát phù hợp |
| Bỏ qua thu hồi JIT | Đặc quyền tồn tại quá hạn dù cấp quyền vẫn nhanh | Đo và xác nhận vòng đời quyền |
| Cảnh báo không có chủ sở hữu | Phát hiện nhưng không có người xử lý | Gắn owner, mức ảnh hưởng và runbook |
| Tự mở quyền khi PAM lỗi | Tạo đường truy cập không kiểm soát | Dùng cơ chế phục hồi được phê duyệt |

Một điểm quan trọng là phân biệt “phát hiện hoạt động bất thường của người dùng” với “phát hiện PAM không thực thi được kiểm soát”. Hai loại giám sát có thể dùng chung dữ liệu, nhưng mục đích và cách phản ứng khác nhau.

## 16. Bài tập tự kiểm tra

### Bài tập 1: Xây dựng ma trận sức khỏe

Một hệ thống dùng IdP bên ngoài, vault, hai broker, ba connector và kho recording. Hãy lập ma trận cho ba năng lực: cấp credential qua API, mở phiên có ghi lại và thu hồi JIT.

Với mỗi năng lực, ghi:

- Phụ thuộc bắt buộc.
- Tín hiệu kiểm tra bên trong.
- Phép kiểm tra đầu cuối.
- Ngưỡng dữ liệu cũ chuyển thành Unknown.
- Hành vi khi phụ thuộc lỗi.
- Chủ sở hữu xử lý.

Đáp án hợp lý phải phân biệt luồng cấp credential với luồng broker và phải có tín hiệu xác nhận kết thúc vòng đời quyền. Không nên kết luận mọi năng lực có cùng một tập phụ thuộc.

### Bài tập 2: Đánh giá cảnh báo thiếu dữ liệu

Một canary không gửi kết quả trong mười phút. Dashboard vẫn hiển thị lần thành công cuối cùng màu xanh. Hãy mô tả sai sót và đề xuất sửa.

Hướng xử lý: tách kết quả lần kiểm tra gần nhất khỏi tuổi của kết quả, thêm trạng thái Unknown khi quá hạn, giám sát lịch chạy và đường gửi telemetry. Không thể chỉ tăng timeout của PAM để giải quyết lỗi này.

### Bài tập 3: Chọn cách xử lý khi vault khỏe nhưng thu hồi JIT lỗi

API cấp quyền đạt SLO, nhưng có năm quyền quá hạn chưa được xác nhận thu hồi. Có nên báo dịch vụ hoàn toàn khỏe không?

Không. Năng lực cấp quyền có thể khỏe trong khi kiểm soát thu hồi đang suy giảm. Cần xác định quyền nào còn hiệu lực tại đích, mức độ nhạy cảm của chúng và cơ chế xử lý đã duyệt. Không tiếp tục gia hạn quyền một cách mặc định để làm chỉ số quá hạn biến mất.

### Bài tập 4: Thiết kế điều kiện phục hồi

Sau khi sửa storage, endpoint recorder báo khỏe. Hãy nêu bằng chứng cần có trước khi đóng sự cố recording.

Một phương án đầy đủ gồm phép ghi và đọc lại đại diện, bản ghi canary truy xuất được, liên kết audit đúng, backlog được kiểm soát, phạm vi bản ghi thiếu đã xác định và không còn tác động chưa được giao xử lý.

## 17. Ghi nhớ

Sức khỏe PAM phải được đo bằng khả năng thực hiện trọn vòng đời truy cập đặc quyền: xác thực, quyết định policy, cấp quyền, sử dụng, lưu bằng chứng và thu hồi. Tiến trình còn chạy chỉ là một tín hiệu nền.

Kết hợp health probe nhẹ, telemetry theo năng lực, synthetic transaction có giới hạn và kiểm tra phục hồi định kỳ. Luôn thể hiện phạm vi ảnh hưởng và độ mới dữ liệu. Khi PAM suy giảm, hành động vận hành phải bảo toàn kiểm soát và bằng chứng theo chính sách đã xác định.

