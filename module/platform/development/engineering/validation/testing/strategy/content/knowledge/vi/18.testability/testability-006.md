# Thiết kế healthcheck và điều kiện sẵn sàng của môi trường

Một hệ thống có thể đã khởi động tiến trình nhưng vẫn chưa đủ điều kiện để nhận yêu cầu hoặc chạy kiểm thử. Cơ sở dữ liệu có thể chưa hoàn tất khởi tạo, migration chưa chạy, hàng đợi chưa kết nối, dữ liệu kiểm thử chưa được tạo hoặc dịch vụ phụ thuộc chưa sẵn sàng. Nếu pipeline chỉ kiểm tra rằng một cổng mạng đã mở rồi bắt đầu chạy test, kết quả có thể thất bại ngẫu nhiên và khó phân biệt lỗi sản phẩm với lỗi môi trường.

Healthcheck và điều kiện sẵn sàng giúp xác định hệ thống đang ở trạng thái nào, có thể phục vụ loại công việc nào và cần chờ hoặc khắc phục điều gì trước khi tiếp tục. Healthcheck cung cấp tín hiệu sức khỏe của tiến trình hoặc dịch vụ. Điều kiện sẵn sàng của môi trường rộng hơn: chúng xác nhận các thành phần, cấu hình, dữ liệu, quyền truy cập và phụ thuộc cần thiết đã được chuẩn bị cho một mục tiêu cụ thể, chẳng hạn chạy bộ kiểm thử tích hợp hoặc E2E.

Trong chiến lược kiểm thử, thiết kế đúng các tín hiệu này giúp pipeline chờ theo điều kiện thực tế thay vì dựa vào thời gian ngủ cố định, ngăn test chạy trên môi trường chưa hoàn chỉnh, giảm flaky test và cung cấp bằng chứng rõ ràng khi môi trường không đáp ứng yêu cầu.

## 1. Phân biệt healthcheck, readiness và environment readiness

Các thuật ngữ này thường được dùng gần nhau nhưng trả lời những câu hỏi khác nhau.

- **Healthcheck:** phép kiểm tra cho biết tiến trình hoặc dịch vụ có đang hoạt động theo một tiêu chí sức khỏe đã định nghĩa hay không.
- **Liveness:** tín hiệu cho biết tiến trình còn sống và có khả năng tiếp tục hoạt động hay không. Nếu liveness thất bại liên tục, nền tảng điều phối có thể khởi động lại tiến trình.
- **Readiness:** tín hiệu cho biết dịch vụ đã sẵn sàng nhận lưu lượng hoặc thực hiện một loại công việc cụ thể hay chưa.
- **Startup check:** tín hiệu cho biết quá trình khởi động ban đầu đã hoàn tất hay chưa, hữu ích với dịch vụ cần thời gian khởi tạo dài.
- **Environment readiness:** trạng thái tổng hợp cho biết môi trường kiểm thử đã có đủ hạ tầng, dịch vụ, cấu hình, dữ liệu, quyền và phụ thuộc để thực hiện một nhóm kiểm thử cụ thể.

Một tiến trình có thể còn sống nhưng chưa sẵn sàng. Ví dụ, ứng dụng đã mở cổng HTTP nhưng vẫn đang nạp cấu hình và chạy migration. Khi đó liveness có thể đạt trong khi readiness chưa đạt. Tương tự, ứng dụng có thể sẵn sàng nhận yêu cầu đọc dữ liệu nhưng chưa sẵn sàng xử lý thanh toán vì kết nối đến cổng thanh toán chưa được thiết lập.

### Vì sao không nên dùng một tín hiệu duy nhất?

Nếu một endpoint health trả về thành công ngay khi tiến trình mở cổng, pipeline có thể hiểu nhầm rằng toàn bộ môi trường đã sẵn sàng. Nếu endpoint đó kiểm tra mọi dịch vụ phụ thuộc và được dùng làm liveness, một sự cố tạm thời ở database có thể khiến nền tảng khởi động lại hàng loạt ứng dụng dù tiến trình vẫn hoạt động bình thường.

Tách tín hiệu theo mục đích giúp hành động phù hợp:

| Tín hiệu | Câu hỏi | Hành động thường tương ứng |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất khởi tạo ban đầu chưa? | Chưa đạt thì tiếp tục chờ trong giới hạn khởi động |
| Liveness | Tiến trình còn phản hồi và có thể tiếp tục hoạt động không? | Thất bại liên tục có thể kích hoạt restart |
| Readiness | Dịch vụ có thể nhận loại yêu cầu này an toàn không? | Chưa đạt thì ngừng định tuyến lưu lượng hoặc công việc mới đến dịch vụ |
| Environment readiness | Môi trường có đủ điều kiện cho bộ kiểm thử được chọn không? | Chưa đạt thì chưa bắt đầu test; báo thành phần hoặc điều kiện còn thiếu |
| Smoke check | Một số hành vi thiết yếu có hoạt động qua đường đi thực tế không? | Đạt thì cho phép bước kiểm thử tiếp theo theo chính sách |

## 2. Thiết kế liveness, readiness và startup check

### Liveness: kiểm tra khả năng tiếp tục chạy

Liveness nên tập trung vào việc tiến trình có bị treo, deadlock hoặc rơi vào trạng thái không thể phục hồi bằng hoạt động bình thường hay không. Kiểm tra có thể xác nhận event loop hoặc thread xử lý chính còn phản hồi, tiến trình không bị kẹt và endpoint nội bộ vẫn phục vụ được.

Không nên đưa mọi phụ thuộc bên ngoài vào liveness. Nếu database tạm thời mất kết nối, ứng dụng có thể vẫn còn sống và có thể tự kết nối lại. Nếu liveness thất bại chỉ vì database chậm, nền tảng có thể liên tục restart ứng dụng, làm tăng tải và khiến sự cố lan rộng.

Chỉ dùng liveness để phát hiện tình trạng mà restart thực sự có khả năng khắc phục. Với lỗi cấu hình không thể tự sửa hoặc database đang ngừng hoạt động, restart liên tục thường không giải quyết được nguyên nhân.

### Readiness: kiểm tra khả năng nhận công việc

Readiness trả lời liệu dịch vụ có thể nhận yêu cầu mới và xử lý chúng theo hợp đồng hay không. Một dịch vụ có thể chưa ready trong khi đang:

- Nạp cấu hình bắt buộc hoặc hoàn tất khởi tạo.
- Thiết lập connection pool đến database cần thiết.
- Xác nhận schema ở phiên bản tương thích.
- Khôi phục trạng thái hoặc nạp dữ liệu cần thiết.
- Kết nối đến broker hoặc đăng ký consumer.
- Nạp mô hình, cache hoặc tài nguyên bắt buộc.

Readiness cần gắn với vai trò của dịch vụ. Nếu một tính năng không cần dịch vụ phụ thuộc đang lỗi, có thể vẫn phục vụ các thao tác khác ở chế độ suy giảm. Nếu mọi chức năng đều cần database chính, database chưa sẵn sàng có thể làm readiness của dịch vụ chính thất bại.

### Startup check: bảo vệ quá trình khởi động dài

Một số dịch vụ cần thời gian để nạp dữ liệu, chạy warm-up hoặc thực hiện khởi tạo nặng. Startup check cho phép tiến trình có đủ thời gian hoàn tất khởi động trước khi liveness và readiness được đánh giá theo chu kỳ bình thường.

Không nên dùng startup check để che giấu việc khởi động bị treo vô thời hạn. Cần có thời hạn tối đa, log tiến trình và trạng thái lỗi rõ ràng khi quá trình khởi tạo không hoàn thành.

### Ví dụ với dịch vụ xử lý đơn hàng

Giả sử dịch vụ đơn hàng cần database để đọc/ghi đơn và broker để phát sự kiện. Một thiết kế có thể là:

- Liveness chỉ xác nhận tiến trình HTTP và worker chính còn phản hồi.
- Startup check chờ cấu hình, connection pool và quá trình khởi tạo schema hoàn tất.
- Readiness cho API ghi đơn xác nhận database chính có thể nhận giao dịch và schema tương thích.
- Readiness của worker xác nhận broker có thể nhận kết nối và consumer đã đăng ký.
- Nếu dịch vụ email không sẵn sàng, hệ thống vẫn có thể tạo đơn và lưu sự kiện gửi email vào outbox để xử lý sau, tùy thiết kế nghiệp vụ.

Ví dụ này cho thấy readiness có thể khác nhau theo loại công việc. Một endpoint tổng quát cần có định nghĩa rõ nó bảo đảm điều gì, tránh trả một trạng thái ready quá rộng so với khả năng thực tế.

## 3. Xác định điều kiện sẵn sàng của môi trường kiểm thử

Environment readiness không chỉ là trạng thái của một ứng dụng. Nó là tập hợp điều kiện cần có để một nhóm kiểm thử cụ thể tạo ra kết quả đáng tin cậy.

### Hạ tầng và tài nguyên

Kiểm tra các tài nguyên cần thiết đã được tạo và có thể truy cập:

- Máy ảo, container, cluster, namespace hoặc runner.
- Mạng, DNS, route, firewall, ingress và chứng thư.
- Database, cache, message broker, object storage và các dịch vụ phụ trợ.
- CPU, bộ nhớ, dung lượng đĩa, connection pool và giới hạn quota.
- Phiên bản runtime, image, trình duyệt và công cụ thực thi kiểm thử.

Không chỉ kiểm tra tài nguyên tồn tại. Một database pod có trạng thái running nhưng chưa chấp nhận kết nối hoặc chưa phục hồi dữ liệu vẫn chưa sẵn sàng cho integration test.

### Ứng dụng và phiên bản triển khai

Môi trường cần chạy đúng phiên bản ứng dụng, image và cấu hình mà pipeline định kiểm tra. Cần xác nhận:

- Các deployment cần thiết đã hoàn tất và không còn rollout dở dang.
- Phiên bản dịch vụ tương thích với nhau.
- Endpoint nội bộ và bên ngoài được định tuyến đúng.
- Migration đã hoàn tất và schema ở phiên bản dự kiến.
- Feature flag và cấu hình môi trường phản ánh đúng kịch bản test.
- Không có một lần triển khai khác đang thay đổi thành phần trong lúc test chạy.

Nếu chỉ kiểm tra endpoint trả HTTP 200 mà không xác nhận phiên bản, pipeline có thể chạy test trên image cũ hoặc một deployment chưa được cập nhật.

### Dữ liệu và trạng thái ban đầu

Một số test yêu cầu dữ liệu cụ thể: tài khoản có vai trò nhất định, sản phẩm còn tồn kho, đơn hàng ở trạng thái chờ thanh toán hoặc dữ liệu biên. Điều kiện sẵn sàng nên xác nhận dữ liệu đã được seed thành công và có thể truy vấn theo định danh của lần chạy.

Các kiểm tra cần xem xét:

- Seed hoặc fixture đã hoàn tất và có phiên bản phù hợp.
- Dữ liệu có đủ số lượng và quan hệ cần thiết.
- Tài khoản và vai trò có quyền đúng với test.
- Dữ liệu không bị lần chạy khác sửa hoặc xóa.
- Cleanup hoặc reset có thể thực hiện an toàn.
- Dữ liệu không chứa thông tin cá nhân hoặc bí mật production không được phép sử dụng.

Không nên chỉ kiểm tra rằng một bản ghi mẫu tồn tại nếu test cần cả một tập dữ liệu liên kết. Ví dụ, kiểm thử luồng giao hàng có thể cần đơn hàng, địa chỉ, kho, sản phẩm, tồn kho và phương thức vận chuyển tương thích.

### Quyền truy cập và bí mật

Runner phải có quyền cần thiết để gọi API, truy cập database hoặc đọc artifact. Secret cần tồn tại, đúng phạm vi và còn hiệu lực. Không nên kiểm tra bằng cách in token hoặc mật khẩu ra log.

Có thể xác nhận quyền bằng một thao tác tối thiểu, an toàn và có thể lặp lại, chẳng hạn gọi endpoint kiểm tra quyền hoặc truy vấn một tài nguyên thử nghiệm được giới hạn. Kiểm tra sẵn sàng không nên thực hiện hành động phá hủy hoặc tạo giao dịch thật ngoài ý muốn.

### Phụ thuộc bên ngoài và sandbox

Nếu test cần nhà cung cấp thanh toán, email, SMS, dịch vụ định danh hoặc API đối tác, cần xác định môi trường đó có khả dụng và cấu hình đúng không. Sandbox có thể có quota, dữ liệu giả lập, thời gian bảo trì hoặc giới hạn tính năng khác production.

Hãy xác định phụ thuộc nào bắt buộc cho từng nhóm test. Một bộ unit/API test có thể không cần sandbox thanh toán; một contract test có thể dùng stub; một nhóm integration test cần xác minh xác thực và callback thật có thể yêu cầu sandbox. Không để toàn bộ môi trường bị đánh dấu chưa ready chỉ vì một dịch vụ không liên quan đến nhóm test đang chuẩn bị chạy.

### Quan sát và thu thập bằng chứng

Trước khi test bắt đầu, cần có khả năng thu thập log, metric, trace và trạng thái dịch vụ đủ để điều tra. Nếu môi trường tạm thời sẽ bị hủy sau test, cần xác nhận cơ chế lưu artifact hoạt động.

Môi trường có thể phục vụ request nhưng không đủ điều kiện cho một đợt kiểm thử nếu log không có correlation ID, đồng hồ lệch quá mức hoặc không thể xác định phiên bản triển khai. Những điều kiện này nên được phản ánh trong tiêu chí readiness khi chúng ảnh hưởng trực tiếp đến khả năng chẩn đoán.

## 4. Xây dựng mô hình readiness theo mục tiêu kiểm thử

Không nên dùng một checklist giống nhau cho mọi loại test. Điều kiện cần thiết phụ thuộc vào mục tiêu kiểm chứng.

| Nhóm kiểm thử | Điều kiện sẵn sàng điển hình |
|---|---|
| Unit test | Runtime và dependency của test đã cài; dữ liệu đầu vào hoặc fixture cục bộ sẵn sàng |
| Component test | Thành phần được build đúng phiên bản; test double hoặc dịch vụ cục bộ hoạt động |
| API test | Dịch vụ đã deploy, endpoint truy cập được, schema/migration tương thích, credential hợp lệ và dữ liệu chuẩn bị xong |
| Contract test | Hợp đồng/schema đúng phiên bản, provider hoặc broker test có thể truy cập và consumer expectations đã được nạp |
| Integration test | Các dịch vụ, database, queue, cache và cấu hình giao tiếp bắt buộc đã sẵn sàng |
| System/E2E | Toàn bộ luồng cần thiết, tài khoản, dữ liệu, trình duyệt, sandbox và các dịch vụ liên quan đã sẵn sàng |
| Performance test | Môi trường có cấu hình và tài nguyên đại diện, dữ liệu đủ lớn, tải nền được kiểm soát và metric đang thu thập |
| Resilience test | Có khả năng mô phỏng lỗi an toàn, quan sát trạng thái và khôi phục môi trường sau thử nghiệm |

### Tạo readiness profile

Một readiness profile là danh sách điều kiện dành cho một nhóm kiểm thử. Ví dụ, profile E2E thanh toán có thể yêu cầu:

1. Ứng dụng web và dịch vụ đơn hàng ở đúng phiên bản.
2. Database đã migrate và có thể ghi/đọc.
3. Broker và worker đã sẵn sàng.
4. Sandbox thanh toán có thể xác thực và phản hồi một giao dịch kiểm tra an toàn.
5. Webhook endpoint có thể nhận callback và xác minh chữ ký.
6. Tài khoản test và dữ liệu giỏ hàng đã được tạo.
7. Runner có trình duyệt đúng phiên bản và quyền truy cập.
8. Log/trace có thể thu thập và môi trường có thể cleanup.

Profile API đọc dữ liệu có thể không cần broker hoặc sandbox thanh toán. Tách profile giúp tránh kiểm tra thừa và giảm thời gian chờ.

### Phân loại điều kiện bắt buộc và điều kiện suy giảm

Mỗi điều kiện nên được phân loại:

- **Bắt buộc (required):** thiếu điều kiện thì không thể chạy test hoặc kết quả không có giá trị.
- **Tùy chọn (optional):** thiếu điều kiện không ngăn test mục tiêu, nhưng có thể làm giảm phạm vi kiểm tra.
- **Suy giảm có kiểm soát (degraded):** hệ thống có thể hoạt động với chức năng hạn chế; chỉ một số test phù hợp được phép chạy.
- **Không áp dụng (not applicable):** thành phần không thuộc profile của lần chạy.

Ví dụ, email sandbox có thể là optional cho test tạo đơn nhưng required cho test xác nhận email. Database chính là required cho cả hai nếu cả hai cần đọc/ghi đơn hàng.

## 5. Thiết kế endpoint và hợp đồng healthcheck

Health endpoint cần có ngữ nghĩa ổn định, phản hồi nhanh và không tạo tác dụng phụ. Cấu trúc phản hồi nên giúp máy đọc được trạng thái và con người hiểu thành phần nào chưa đạt.

### Ví dụ phản hồi tổng quát

~~~json
{
  "status": "NOT_READY",
  "service": "order-service",
  "version": "2026.11.16-rc3",
  "checks": {
    "database": {
      "status": "UP",
      "required": true
    },
    "messageBroker": {
      "status": "DOWN",
      "required": true
    },
    "emailProvider": {
      "status": "DEGRADED",
      "required": false
    }
  },
  "checkedAt": "2026-11-16T07:30:00Z"
}
~~~

Đây là ví dụ minh họa. Trong môi trường công khai, không nên tiết lộ hostname nội bộ, chuỗi kết nối, tên database nhạy cảm, stack trace hoặc thông tin bí mật. Có thể cung cấp chi tiết đầy đủ hơn cho hệ thống giám sát nội bộ với quyền truy cập phù hợp.

### Thiết kế mã trạng thái nhất quán

Nên định nghĩa rõ các trạng thái như:

- **UP:** kiểm tra thành công và thành phần có thể đáp ứng mục tiêu.
- **DOWN:** thành phần không hoạt động hoặc không thể đáp ứng điều kiện bắt buộc.
- **DEGRADED:** vẫn hoạt động nhưng thiếu một năng lực không bắt buộc hoặc có giới hạn.
- **UNKNOWN:** chưa có đủ dữ liệu để kết luận.
- **NOT_READY:** dịch vụ hoặc môi trường chưa đủ điều kiện cho mục tiêu được hỏi.

Không nên dùng một mã trạng thái HTTP cho mọi trường hợp mà không định nghĩa ý nghĩa. Ví dụ, endpoint liveness thường trả thành công nếu tiến trình còn sống; endpoint readiness có thể trả trạng thái không sẵn sàng khi thiếu phụ thuộc bắt buộc. Hợp đồng cần nêu rõ consumer nào sử dụng endpoint và hành động nào sẽ được kích hoạt.

### Tách endpoint theo mục đích

Một thiết kế có thể cung cấp các endpoint riêng:

- **/health/live:** kiểm tra tiến trình còn sống.
- **/health/startup:** kiểm tra quá trình khởi tạo đã hoàn tất.
- **/health/ready:** kiểm tra dịch vụ có thể nhận lưu lượng.
- **/test-support/readiness:** endpoint nội bộ dành cho pipeline, trả các điều kiện môi trường theo readiness profile.

Tên endpoint chỉ là ví dụ; tổ chức có thể dùng quy ước khác. Điều quan trọng là không để pipeline suy diễn readiness môi trường từ endpoint liveness của một dịch vụ đơn lẻ.

### Thiết kế phép kiểm tra nhẹ và an toàn

Healthcheck nên:

- Có thời gian thực thi ngắn và giới hạn timeout rõ.
- Không tạo giao dịch nghiệp vụ hoặc dữ liệu không cần thiết.
- Không chạy migration hoặc tác vụ khởi tạo nặng trong mỗi lần probe.
- Dùng truy vấn hoặc thao tác tối thiểu để xác nhận kết nối cần thiết.
- Có giới hạn tần suất để tránh tạo tải đáng kể.
- Không trả dữ liệu nhạy cảm ra ngoài.
- Ghi nhận lỗi đủ để vận hành điều tra mà không làm lộ bí mật.

Nếu cần xác nhận database có thể ghi, hãy cân nhắc một phép kiểm tra an toàn như transaction trên bảng kiểm tra riêng rồi rollback, hoặc một kiểm tra khác được thiết kế để không tạo tác dụng phụ. Không nên chèn/xóa bản ghi nghiệp vụ thật trong mỗi lần health probe.

## 6. Xác định ngưỡng, timeout và chống dao động trạng thái

Một probe có thể thất bại thoáng qua do mạng hoặc tải. Nếu hệ thống đổi trạng thái ngay sau một lần thất bại, traffic có thể bị rút khỏi dịch vụ liên tục; nếu chờ quá lâu, test có thể bắt đầu trên môi trường không còn sẵn sàng.

### Timeout và chu kỳ kiểm tra

Mỗi check cần có:

- **Timeout:** thời gian tối đa cho một lần kiểm tra.
- **Interval:** khoảng cách giữa các lần kiểm tra.
- **Failure threshold:** số lần thất bại liên tiếp trước khi đánh dấu không đạt.
- **Success threshold:** số lần thành công liên tiếp trước khi chuyển lại trạng thái đạt, nếu cần.
- **Overall deadline:** thời hạn tối đa mà pipeline hoặc bộ điều phối chờ trạng thái mong muốn.

Các giá trị cần dựa trên thời gian phản hồi thực tế, mức biến động và hậu quả của việc đánh dấu sai. Timeout quá ngắn gây false negative; timeout quá dài làm chậm phát hiện sự cố. Deadline của pipeline cần hữu hạn để tránh chờ vô hạn.

### Chống flapping

Flapping là tình trạng trạng thái liên tục chuyển giữa UP và DOWN trong thời gian ngắn. Có thể giảm hiện tượng này bằng cách yêu cầu nhiều lần thất bại hoặc thành công liên tiếp, dùng cửa sổ quan sát, giới hạn tần suất và phân biệt lỗi tạm thời với lỗi kéo dài.

Không nên làm trơn tín hiệu quá mức đến mức che giấu sự cố thật. Ngưỡng cần phù hợp với mục tiêu: readiness cho traffic có thể phản ứng nhanh hơn một báo cáo sức khỏe tổng hợp dùng cho dashboard.

### Deadline theo giai đoạn

Không nên dùng một timeout khổng lồ cho toàn bộ quá trình. Hãy đặt thời hạn riêng cho:

1. Provisioning hạ tầng.
2. Deployment và startup.
3. Migration và seed dữ liệu.
4. Readiness của dịch vụ phụ thuộc.
5. Smoke test.
6. Thu thập bằng chứng và bắt đầu test suite.

Khi một giai đoạn hết hạn, báo tên điều kiện chưa đạt, thời gian đã chờ và trạng thái quan sát được. Điều này giúp phân biệt provisioning chậm với database chưa sẵn sàng hoặc seed dữ liệu bị lỗi.

## 7. Điều phối readiness trong CI/CD

Pipeline nên coi readiness là một cổng có thể kiểm chứng trước khi chạy test. Trình tự cần rõ ràng và có timeout, log cùng khả năng cleanup.

### Trình tự chuẩn bị môi trường

1. Cấp phát runner và môi trường.
2. Deploy các dịch vụ và cấu hình đúng phiên bản.
3. Chờ startup check của từng dịch vụ.
4. Chờ readiness của các phụ thuộc bắt buộc.
5. Chạy migration và seed dữ liệu theo phiên bản.
6. Kiểm tra quyền, secret, endpoint và kết nối mạng.
7. Chạy smoke test để xác nhận một số hành vi thiết yếu.
8. Đánh dấu environment profile sẵn sàng và bắt đầu bộ test.
9. Thu thập kết quả, log và trace; sau đó cleanup theo chính sách.

Không nên dùng một lệnh sleep cố định rồi giả định môi trường đã sẵn sàng. Thời gian khởi tạo thay đổi theo tải, cache, kích thước dữ liệu và trạng thái dịch vụ. Pipeline nên polling một điều kiện có ý nghĩa cho đến khi đạt hoặc hết deadline.

### Ví dụ polling readiness

~~~text
deadline = current_time + 180 seconds
repeat:
  response = request readiness endpoint with a short timeout
  if response is valid and required checks are READY:
    continue to smoke tests
  if current_time >= deadline:
    fail with the list of unmet checks
  wait for a short interval
~~~

Đây là thuật toán minh họa. Trong triển khai thực tế nên phân tích JSON bằng công cụ phù hợp, xử lý HTTP status riêng và che thông tin nhạy cảm trong output. Nếu endpoint trả danh sách check, pipeline nên hiển thị các điều kiện bắt buộc chưa đạt.

### Readiness gate theo profile

Một pipeline có thể yêu cầu profile khác nhau. Ví dụ profile E2E thanh toán gồm các check bắt buộc:

- webApplication
- orderService
- database
- messageBroker
- paymentSandbox
- webhookReceiver
- testData
- browserRunner
- observability

Profile này chỉ là ví dụ. Danh sách thực tế cần khớp với kiến trúc và test suite. Một test chỉ kiểm tra API đọc đơn hàng không nên bị chặn bởi payment sandbox nếu nó không phụ thuộc vào thanh toán.

### Phân biệt readiness gate và smoke test

Readiness gate kiểm tra điều kiện tiên quyết: dịch vụ có sẵn, phiên bản đúng, kết nối và dữ liệu cần thiết tồn tại. Smoke test kiểm tra một số hành vi tối thiểu qua đường đi thực tế: ví dụ đăng nhập bằng tài khoản thử nghiệm, đọc một tài nguyên hoặc tạo rồi hủy một đối tượng thử nghiệm an toàn.

Hai bước bổ sung cho nhau. Một endpoint có thể báo ready nhưng ứng dụng vẫn lỗi khi thực hiện request nghiệp vụ; smoke test có thể phát hiện sai cấu hình routing hoặc lỗi xử lý cơ bản. Ngược lại, smoke test không nên thay thế toàn bộ readiness check vì nó có thể không chỉ rõ thành phần nào chưa được chuẩn bị.

## 8. Thiết kế readiness trong môi trường container và Kubernetes

Trong môi trường điều phối container, các probe thường được cấu hình để nền tảng quyết định khi nào khởi động lại container hoặc đưa nó vào/ra khỏi tập endpoint nhận traffic. Ý nghĩa của từng probe cần được giữ đúng.

### Startup probe

Startup probe cho ứng dụng có thời gian khởi động dài. Trong khi startup probe chưa đạt, liveness và readiness chưa được thực hiện theo chu kỳ thông thường. Khi startup thành công, các probe còn lại bắt đầu hoạt động.

### Liveness probe

Liveness xác định container có cần được khởi động lại hay không. Nếu probe thất bại đủ số lần theo cấu hình, nền tảng có thể restart container. Chỉ nên dùng cho tình trạng tiến trình không thể tự phục hồi.

### Readiness probe

Readiness xác định pod có nên nhận traffic từ service hay không. Pod chưa ready vẫn có thể tiếp tục chạy để hoàn tất khởi tạo hoặc chờ phụ thuộc. Khi readiness đạt, pod có thể được đưa trở lại endpoint phục vụ.

### Ví dụ cấu hình rút gọn

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-service
spec:
  containers:
    - name: app
      image: example/order-service:1.4.0
      ports:
        - containerPort: 8080
      startupProbe:
        httpGet:
          path: /health/startup
          port: 8080
        periodSeconds: 5
        failureThreshold: 30
      livenessProbe:
        httpGet:
          path: /health/live
          port: 8080
        periodSeconds: 10
        failureThreshold: 3
      readinessProbe:
        httpGet:
          path: /health/ready
          port: 8080
        periodSeconds: 5
        failureThreshold: 2
~~~

Các con số chỉ minh họa, không phải giá trị mặc định phù hợp cho mọi dịch vụ. Cần chọn period, timeout và threshold dựa trên thời gian khởi động, độ trễ thực tế và hành vi phục hồi. Không nên cấu hình liveness phụ thuộc trực tiếp vào mọi dịch vụ bên ngoài nếu restart không giúp khôi phục.

## 9. Kiểm thử chính healthcheck và readiness logic

Healthcheck cũng là mã sản phẩm và có thể chứa lỗi. Một endpoint luôn trả UP sẽ khiến hệ thống không phát hiện được sự cố; một endpoint luôn trả DOWN có thể loại dịch vụ khỏi traffic. Vì vậy, cần kiểm thử cả logic đánh giá lẫn cách nền tảng hoặc pipeline phản ứng với kết quả.

### Kiểm thử trạng thái bình thường

- Tiến trình khởi động và startup check chuyển sang đạt.
- Liveness trả trạng thái đúng khi tiến trình phản hồi.
- Readiness đạt khi mọi phụ thuộc bắt buộc sẵn sàng.
- Environment readiness đạt khi tất cả điều kiện trong profile đã được xác nhận.
- Trường version, timestamp và danh sách check phản ánh đúng môi trường đang chạy.

### Kiểm thử trạng thái không sẵn sàng

- Database chưa chấp nhận kết nối.
- Schema không tương thích hoặc migration chưa hoàn tất.
- Broker không kết nối được hoặc consumer chưa đăng ký.
- Secret thiếu hoặc hết hạn.
- Seed dữ liệu thất bại hoặc dữ liệu không đủ.
- Runner không truy cập được endpoint do DNS, route hoặc chứng thư.
- Sandbox bên ngoài không sẵn sàng trong profile có yêu cầu nó.

Xác nhận đúng check bị đánh dấu không đạt, pipeline không bắt đầu test phụ thuộc và thông báo chỉ ra nguyên nhân có thể hành động.

### Kiểm thử phục hồi và chuyển trạng thái

Mô phỏng phụ thuộc tạm thời mất kết nối rồi phục hồi. Xác nhận readiness chuyển từ NOT_READY sang READY theo ngưỡng, không flapping quá mức và không cần restart nếu tiến trình vẫn khỏe. Với liveness, mô phỏng trạng thái treo có kiểm soát để xác nhận cơ chế restart hoạt động khi phù hợp.

### Kiểm thử lỗi và ranh giới

- Endpoint health bị timeout hoặc trả payload sai schema.
- Phản hồi có trạng thái UNKNOWN hoặc dữ liệu thiếu.
- Một phụ thuộc optional bị lỗi trong khi chức năng chính vẫn hoạt động.
- Một lần probe bị gọi đồng thời hoặc thường xuyên.
- Endpoint bị gọi từ mạng hoặc danh tính không được phép.
- Môi trường đang rollout và có nhiều phiên bản cùng tồn tại.

### Kiểm thử không tạo tác dụng phụ

Gọi healthcheck nhiều lần không được tạo đơn hàng, gửi email, tăng số lượt sử dụng mã giảm giá hoặc ghi dữ liệu nghiệp vụ không cần thiết. Nếu cần kiểm tra write path, dùng tài nguyên riêng có thể dọn dẹp an toàn và giới hạn tần suất.

## 10. Bảo mật và quyền truy cập đối với health endpoint

Health endpoint có thể tiết lộ phiên bản, trạng thái phụ thuộc, tên thành phần và cấu trúc nội bộ. Những thông tin này hữu ích cho vận hành nhưng cũng có thể giúp người ngoài hiểu kiến trúc hoặc tìm điểm yếu.

Nên phân loại endpoint:

- **Public hoặc external health:** chỉ trả thông tin tối thiểu cần cho bộ cân bằng tải hoặc người dùng, không nêu chi tiết nội bộ.
- **Internal health:** dành cho hệ thống giám sát và vận hành có xác thực, có thể trả chi tiết check cần thiết.
- **Test readiness endpoint:** chỉ dành cho runner hoặc pipeline được cấp quyền, trả điều kiện của profile kiểm thử.

Các nguyên tắc quan trọng:

- Không trả secret, token, connection string, stack trace hoặc dữ liệu khách hàng.
- Hạn chế truy cập theo mạng và danh tính dịch vụ.
- Không cho endpoint readiness thực hiện hành động quản trị hoặc thay đổi cấu hình.
- Giới hạn tần suất và bảo vệ khỏi request quá lớn.
- Ghi log truy cập theo chính sách nhưng không lưu thông tin nhạy cảm.
- Xác minh rằng môi trường production không vô tình mở endpoint chỉ dành cho kiểm thử.

## 11. Quan sát và chẩn đoán readiness

Một tín hiệu readiness chỉ hữu ích khi nhóm biết nó thất bại vì điều gì. Phản hồi chung chung “environment not ready” không đủ để điều tra.

### Thông tin nên ghi nhận

- Mã lần chạy, môi trường, readiness profile và commit.
- Thành phần hoặc check chưa đạt.
- Trạng thái quan sát được và trạng thái mong đợi.
- Thời điểm bắt đầu, thời điểm kiểm tra gần nhất và thời gian chờ.
- Mã lỗi đã chuẩn hóa và correlation ID nếu có.
- Phiên bản dịch vụ, image và schema liên quan.
- Số lần probe, timeout và chuyển trạng thái.
- Người hoặc pipeline sở hữu môi trường.

Không ghi toàn bộ response có thể chứa thông tin nội bộ vào log công khai. Nên có một thông báo tóm tắt cho pipeline và chi tiết đầy đủ trong hệ thống quan sát có kiểm soát quyền.

### Chỉ số vận hành

| Chỉ số | Ý nghĩa |
|---|---|
| Time to ready | Thời gian từ khi yêu cầu môi trường đến khi profile đạt |
| Readiness failure rate | Tỷ lệ lần chuẩn bị môi trường không đạt trong deadline |
| Dependency availability | Mức sẵn sàng của từng phụ thuộc bắt buộc |
| Probe timeout rate | Tỷ lệ healthcheck hết thời gian |
| Flapping count | Số lần trạng thái chuyển qua lại trong một cửa sổ |
| Environment setup failure | Tỷ lệ provisioning, deployment, migration hoặc seed thất bại |
| Test blocked by environment | Số lần test không thể bắt đầu do môi trường |
| Recovery time | Thời gian từ khi check thất bại đến khi readiness được khôi phục |

Phân tích theo profile, môi trường, dịch vụ và thời gian giúp tìm nút thắt. Nếu time to ready tăng, cần biết do provisioning, migration, seed hay một phụ thuộc bên ngoài; chỉ xem thời gian tổng không đủ để chọn hành động.

## 12. Quản lý readiness cho môi trường tạm thời

Môi trường tạm thời (ephemeral environment) thường được tạo theo pull request hoặc test run. Nó cần một vòng đời có thể quan sát: requested, provisioning, deploying, initializing, seeding, checking, ready, testing, collecting artifacts và cleanup.

### Vòng đời môi trường

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> Provisioning
    Provisioning --> Deploying
    Deploying --> Initializing
    Initializing --> Seeding
    Seeding --> Checking
    Checking --> Ready
    Checking --> Failed
    Ready --> Testing
    Testing --> CollectingArtifacts
    CollectingArtifacts --> Cleanup
    Failed --> CollectingArtifacts
    Cleanup --> [*]
~~~

Mỗi trạng thái nên có timestamp và timeout. Nếu môi trường thất bại trước khi ready, pipeline cần lưu log provisioning và check lỗi trước cleanup. Nếu test hoàn tất, cần thu thập artifact rồi mới hủy tài nguyên.

### Tránh dùng nhầm môi trường

Gắn môi trường với mã lần chạy hoặc pull request, đồng thời kiểm tra metadata trước khi test. Không nên để hai pipeline ghi vào cùng một namespace hoặc database nếu test có thể thay đổi dữ liệu. Nếu có tài nguyên dùng chung, cần khóa hoặc phân vùng rõ ràng.

### Dọn dẹp tài nguyên bị bỏ quên

Môi trường có thể bị bỏ lại khi pipeline bị hủy hoặc runner mất kết nối. Dùng TTL, owner label và tác vụ cleanup có kiểm soát để thu hồi tài nguyên hết hạn. Không xóa môi trường còn đang được điều tra hoặc đang được người dùng giữ theo quy trình được phê duyệt.

## 13. Ví dụ thực hành: chuẩn bị môi trường cho E2E thanh toán

Giả sử pipeline cần chạy E2E từ lúc khách hàng tạo đơn đến khi đơn được đánh dấu đã thanh toán. Môi trường gồm web app, order service, payment adapter, database, message broker, webhook receiver và sandbox của nhà cung cấp.

### Xác định readiness profile

Các điều kiện bắt buộc:

1. Web app, order service và payment adapter đã deploy đúng commit.
2. Database chấp nhận đọc/ghi và schema ở phiên bản tương thích.
3. Broker hoạt động, topic hoặc queue đã tồn tại và worker đang nhận sự kiện.
4. Payment sandbox xác thực được bằng credential test.
5. Webhook receiver truy cập được từ sandbox và có thể xác minh chữ ký.
6. Tài khoản test, sản phẩm và giỏ hàng đã được seed.
7. Runner truy cập được web app và có trình duyệt đúng phiên bản.
8. Log và trace được bật, có correlation ID và có thể lưu artifact.

### Thực hiện các bước kiểm tra

- Startup check xác nhận từng dịch vụ đã hoàn tất khởi tạo.
- Readiness của order service xác nhận database và broker bắt buộc sẵn sàng.
- Check của payment adapter xác nhận cấu hình sandbox và credential hợp lệ bằng thao tác không tạo giao dịch thật ngoài ý muốn.
- Check webhook xác nhận endpoint có thể truy cập và cấu hình chữ ký đã nạp.
- Data readiness xác nhận sản phẩm, tài khoản và giỏ hàng của test run tồn tại.
- Smoke test đăng nhập và đọc giỏ hàng, sau đó mới bắt đầu E2E thanh toán.

### Xử lý một tình huống chưa sẵn sàng

Giả sử tất cả dịch vụ đều ready nhưng broker chưa có worker đăng ký. Nếu profile chỉ kiểm tra broker TCP port, nó có thể báo đạt dù sự kiện thanh toán không được xử lý. Cần bổ sung check xác nhận consumer group hoặc worker readiness, hoặc chạy một smoke check an toàn để xác nhận đường đi sự kiện.

Nếu sandbox thanh toán không sẵn sàng, pipeline có thể đánh dấu profile E2E thanh toán là NOT_READY và dừng trước khi test. Các test API không phụ thuộc sandbox vẫn có thể chạy theo profile riêng. Cách phân tách này giữ thông tin chính xác về phạm vi chưa có bằng chứng.

### Bằng chứng sau khi chạy

Kết quả nên ghi nhận readiness profile, phiên bản dịch vụ, thời gian đạt ready, các check đã chạy, smoke test, commit, test run ID và trạng thái cleanup. Khi E2E thất bại, nhóm có thể xác định môi trường đã sẵn sàng trước lúc chạy hay readiness đã thay đổi giữa chừng.

## 14. Những sai lầm thường gặp

- **Dùng một endpoint health cho mọi mục đích:** liveness, readiness và environment readiness có hành động và phạm vi khác nhau.
- **Kiểm tra chỉ cổng mạng:** cổng mở không chứng minh ứng dụng đã khởi tạo, schema tương thích hoặc dữ liệu sẵn sàng.
- **Đưa mọi phụ thuộc vào liveness:** sự cố phụ thuộc có thể gây restart dây chuyền.
- **Dùng readiness quá rộng:** một dịch vụ optional không nên chặn các test không phụ thuộc vào nó.
- **Chờ bằng sleep cố định:** môi trường có thể khởi động nhanh hoặc chậm hơn dự kiến; cần polling có deadline.
- **Không xác nhận phiên bản:** test có thể chạy trên image hoặc schema cũ.
- **Chỉ kiểm tra dữ liệu tồn tại:** dữ liệu có thể sai trạng thái, thiếu quan hệ hoặc bị test khác thay đổi.
- **Healthcheck tạo tác dụng phụ:** probe có thể tạo giao dịch hoặc làm tăng tải không cần thiết.
- **Không giới hạn timeout và tần suất:** probe chậm hoặc quá dày có thể tự tạo áp lực cho dịch vụ.
- **Không lưu bằng chứng trước cleanup:** mất log và trạng thái khiến điều tra khó khăn.
- **Tiết lộ thông tin nội bộ:** endpoint công khai có thể làm lộ cấu trúc hoặc chi tiết nhạy cảm.
- **Không kiểm thử chính healthcheck:** một endpoint luôn trả UP có thể khiến lỗi thật bị bỏ qua.
- **Không quản lý TTL cho môi trường tạm thời:** tài nguyên bỏ quên làm tăng chi phí và gây xung đột.

## 15. Danh sách kiểm tra thiết kế healthcheck và readiness

**Ngữ nghĩa healthcheck**

- Liveness, readiness và startup có mục đích riêng và được định nghĩa rõ chưa?
- Liveness chỉ kiểm tra tình trạng mà restart có thể khắc phục chưa?
- Readiness có phản ánh khả năng nhận đúng loại công việc không?
- Startup có deadline và tín hiệu lỗi khi khởi tạo không hoàn tất không?

**Điều kiện môi trường**

- Hạ tầng, deployment, phiên bản và schema đã đúng chưa?
- Các dịch vụ bắt buộc và phụ thuộc của profile đã sẵn sàng chưa?
- Credential, quyền, network và DNS đã được xác minh an toàn chưa?
- Dữ liệu test, fixture và trạng thái ban đầu đã đầy đủ, cô lập chưa?
- Log, metric, trace và lưu artifact có hoạt động không?

**Thiết kế và vận hành**

- Probe có nhanh, an toàn, không tạo tác dụng phụ và có giới hạn tần suất không?
- Timeout, interval, threshold và overall deadline có phù hợp không?
- Trạng thái DOWN, DEGRADED, UNKNOWN và NOT_READY có ngữ nghĩa rõ không?
- Endpoint nội bộ và test readiness có được bảo vệ quyền truy cập không?
- Pipeline polling theo điều kiện thay vì sleep cố định không?
- Mỗi readiness profile có chủ sở hữu và phạm vi phụ thuộc rõ không?
- Môi trường tạm thời có quy trình cleanup và TTL không?

**Kiểm thử và bằng chứng**

- Đã kiểm thử trường hợp sẵn sàng, không sẵn sàng và phục hồi chưa?
- Đã mô phỏng phụ thuộc lỗi, timeout và trạng thái dao động chưa?
- Test có bị chặn khi môi trường thiếu điều kiện bắt buộc không?
- Báo cáo có chỉ ra check nào thất bại và vì sao không?
- Có ghi nhận thời gian đạt ready, failure rate và test bị block do môi trường không?

## Kết luận

Healthcheck xác định sức khỏe của tiến trình hoặc dịch vụ; liveness, startup và readiness phục vụ những quyết định khác nhau; environment readiness xác nhận môi trường đã đủ điều kiện cho một nhóm kiểm thử cụ thể. Thiết kế tốt cần gắn tín hiệu với mục đích, xác định rõ phụ thuộc bắt buộc, phiên bản, dữ liệu, quyền và khả năng quan sát, đồng thời dùng timeout cùng deadline hữu hạn. Khi pipeline chờ theo điều kiện thực tế, chạy smoke test phù hợp và lưu bằng chứng trước cleanup, nhóm giảm được test thất bại do môi trường, phân loại sự cố chính xác hơn và tạo ra kết quả kiểm thử đáng tin cậy.
