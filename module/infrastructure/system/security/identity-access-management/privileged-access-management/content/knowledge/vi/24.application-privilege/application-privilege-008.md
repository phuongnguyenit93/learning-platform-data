# Configuration write permission

Quyền sửa cấu hình có thể mang sức mạnh tương đương quyền quản trị dù người được cấp không được đăng nhập vào máy chủ hay đọc trực tiếp secret. Một thay đổi ở cấu hình có thể khiến ứng dụng chạy dưới danh tính khác, tải mã từ nguồn mới, gửi dữ liệu sang đích khác, bỏ qua kiểm tra truy cập hoặc ngừng xuất log.

Trong chương Application privilege của Privileged Access Management (PAM), **configuration write permission** là quyền tạo, thay đổi, xóa hoặc kích hoạt cấu hình chi phối hành vi của ứng dụng. Cần quản lý quyền này theo tác động thực tế của cấu hình, thay vì coi mọi thao tác sửa một tệp hoặc cập nhật một bản ghi là công việc vận hành thông thường.

Bài học tập trung vào cách kiểm kê, giới hạn, cấp tạm thời, giám sát và thu hồi quyền sửa cấu hình. Các tên ứng dụng, đường dẫn, API và policy trong ví dụ đều là minh họa; chúng không phải cú pháp cấu hình dùng trực tiếp cho một sản phẩm PAM cụ thể.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện cấu hình có khả năng tạo đặc quyền trực tiếp hoặc gián tiếp.
- Phân biệt quyền soạn thay đổi, phê duyệt, áp dụng và quản trị cơ chế kiểm soát.
- Giới hạn quyền theo trường dữ liệu, tài nguyên, môi trường, tenant và thời gian.
- Thiết kế luồng thay đổi có kiểm tra phiên bản, phê duyệt đúng nội dung và bằng chứng.
- Xác định các đường ghi thay thế có thể vượt qua cơ chế kiểm soát chính.
- Xây dựng kịch bản kiểm thử, thu hồi quyền, khôi phục cấu hình và xử lý sự cố.

## 2. Vì sao sửa cấu hình là một hành động đặc quyền?

### 2.1. Cấu hình quyết định ứng dụng làm gì và làm với quyền của ai

Một ứng dụng thường nhận cấu hình từ nhiều nơi:

- Tệp trên máy chủ hoặc volume.
- Biến môi trường do hệ thống triển khai cung cấp.
- Cơ sở dữ liệu hoặc dịch vụ cấu hình tập trung.
- API quản trị, giao diện vận hành hoặc công cụ dòng lệnh.
- Repository và pipeline triển khai.
- Metadata của workload hoặc tài nguyên hạ tầng.
- Feature flag và cơ chế cấu hình động.
- Tham chiếu tới secret trong vault.

Một người không có quyền gọi API quản trị trực tiếp vẫn có thể gây tác động quản trị nếu được sửa cấu hình của ứng dụng có quyền gọi API đó.

Ví dụ, một dịch vụ xuất báo cáo được phép đọc dữ liệu khách hàng. Nếu người vận hành đổi được địa chỉ nhận báo cáo sang một máy chủ do họ kiểm soát, quyền sửa cấu hình đã tạo ra đường lấy dữ liệu. Không cần có quyền đọc cơ sở dữ liệu trực tiếp.

~~~text
Quyền sửa cấu hình
        |
        +--> đổi đích dữ liệu --> dữ liệu đi ra ngoài ranh giới cho phép
        |
        +--> đổi danh tính runtime --> dùng quyền của principal mạnh hơn
        |
        +--> đổi plugin hoặc lệnh --> thực thi mã trong ứng dụng
        |
        +--> tắt kiểm tra truy cập --> mở đường cho thao tác trái phép
        |
        +--> đổi audit --> giảm khả năng phát hiện và đối soát
~~~

Không phải mọi quyền sửa cấu hình đều có mức rủi ro giống nhau. Tuy nhiên, phải chứng minh ranh giới đó bằng hành vi ứng dụng và cơ chế thực thi, không chỉ bằng tên role.

### 2.2. Tác động còn phụ thuộc vào nơi cấu hình được tiêu thụ

Cùng một trường tên là endpoint có thể mang ý nghĩa rất khác:

- Địa chỉ một dịch vụ công khai để lấy nội dung không nhạy cảm.
- Đích nhận bản sao lưu production.
- Địa chỉ hệ thống xác thực mà ứng dụng tin cậy.
- Địa chỉ truy xuất plugin hoặc gói thực thi.

Phân loại phải xét dữ liệu đi qua, danh tính sử dụng kết nối, khả năng thực thi mã và ảnh hưởng tới cơ chế bảo mật.

Một giá trị cấu hình trông như chuỗi thông thường cũng có thể được ứng dụng diễn giải thành lệnh, biểu thức hoặc đường dẫn tải mã. Khi đó, giới hạn “chỉ sửa một trường” chưa đủ để giảm quyền nếu trường ấy điều khiển toàn bộ hành vi quan trọng.

### 2.3. Quyền xóa và quyền khôi phục cũng cần được xét

Xóa cấu hình có thể khiến ứng dụng:

- Dùng giá trị mặc định có quyền rộng hơn.
- Mất kết nối tới vault hoặc audit.
- Chạy ở chế độ phục hồi ít kiểm soát hơn.
- Ngừng hoạt động hoặc mất dữ liệu.

Khôi phục một phiên bản cũ cũng là thay đổi. Bản cũ có thể chứa endpoint không còn tin cậy, tham chiếu secret đã bị thu hồi hoặc cơ chế xác thực đã bị loại bỏ. Không nên mặc định mọi rollback đều an toàn.

## 3. Kiểm kê quyền theo chuỗi thay đổi thực tế

### 3.1. Tách quyền soạn, duyệt, áp dụng và sử dụng

Một thay đổi thường đi qua nhiều trạng thái:

~~~text
Đề xuất -> Kiểm tra -> Phê duyệt -> Áp dụng -> Kích hoạt -> Xác minh
~~~

Các quyền tương ứng không nhất thiết thuộc cùng một principal.

| Năng lực | Ý nghĩa | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Đọc cấu hình | Xem giá trị hoặc metadata | Có thể lộ secret hoặc thông tin nhạy cảm |
| Tạo bản đề xuất | Soạn cấu hình dự kiến | Có thể chèn thay đổi khó nhận biết |
| Phê duyệt | Cho phép một bản thay đổi cụ thể | Có thể hợp thức hóa thay đổi ngoài phạm vi |
| Áp dụng | Ghi vào nguồn cấu hình có hiệu lực | Có thể sửa production trực tiếp |
| Kích hoạt | Reload, restart hoặc chuyển phiên bản | Có thể đưa bản đã lưu vào hoạt động |
| Khôi phục | Chọn và áp dụng một bản trước | Có thể đưa rủi ro cũ trở lại |
| Quản trị policy | Đổi ai được sửa và quy trình kiểm tra | Có thể tự mở rộng quyền hoặc vô hiệu hóa kiểm soát |

Nếu hệ thống lưu cấu hình và tự kích hoạt ngay sau khi ghi, quyền ghi cũng bao gồm quyền kích hoạt. Nếu hai bước tách biệt, vẫn phải xét quyền chuyển con trỏ phiên bản hoặc yêu cầu reload.

### 3.2. Inventory phải bao gồm cả người và máy

Không chỉ lập danh sách quản trị viên. Cần kiểm kê:

- Tài khoản người dùng và tài khoản quản trị riêng.
- Service account của pipeline.
- Agent trên máy chủ.
- Dịch vụ đồng bộ cấu hình.
- Tài khoản hỗ trợ từ nhà cung cấp.
- Principal dùng trong phục hồi và break-glass.
- Danh tính runtime có khả năng tự ghi cấu hình.

Một bản ghi tối thiểu nên trả lời được:

| Thuộc tính | Ví dụ |
| --- | --- |
| Ứng dụng và tài nguyên | Billing API, bộ cấu hình runtime |
| Môi trường và tenant | Production, tenant nội bộ đã xác định |
| Principal được cấp | Pipeline config-publisher-prod |
| Owner | Nhóm vận hành Billing |
| Đường ghi | API cấu hình và repository triển khai |
| Trường hoặc thao tác được phép | Điều chỉnh concurrency trong khoảng đã duyệt |
| Tác động đặc quyền | Thay đổi tải và tính sẵn sàng |
| Cơ chế xác thực | Danh tính workload, không dùng tài khoản cá nhân |
| Điều kiện | Bản thay đổi đã duyệt, cửa sổ hợp lệ |
| Thời hạn | Grant tạm thời hoặc quyền nền có rà soát |
| Bằng chứng | Change ID, quyết định policy, phiên bản và kết quả |

Owner của ứng dụng không tự động là owner của mọi quyền. Với cấu hình xác thực, audit hoặc trust, có thể cần owner kiểm soát bảo mật tham gia.

### 3.3. Lập bản đồ mọi đường ghi

Một giao diện quản trị được bảo vệ tốt vẫn không đủ nếu cùng cấu hình có thể được sửa qua đường khác:

- Kết nối trực tiếp cơ sở dữ liệu.
- Shell trên máy chủ.
- Tệp gắn từ volume dùng chung.
- API cũ hoặc endpoint batch.
- Pipeline khác dùng cùng credential.
- Công cụ quản trị của nền tảng.
- Quyền sửa template sinh cấu hình.
- Quyền thay thứ tự ưu tiên giữa các nguồn cấu hình.

Cần xác định nguồn nào là nguồn chuẩn và nguồn nào được ưu tiên lúc chạy. Tệp trong repository đã đúng nhưng bị biến môi trường ghi đè thì quyền kiểm soát thực tế nằm ở nơi đặt biến môi trường đó.

## 4. Phân loại cấu hình theo khả năng gây tác động

Bảng dưới đây là khung phân tích, không phải phân loại cố định cho mọi hệ thống.

| Nhóm cấu hình | Ví dụ | Hệ quả có thể xảy ra |
| --- | --- | --- |
| Danh tính và ủy quyền | Runtime identity, role mapping, trust issuer | Leo thang quyền hoặc chấp nhận danh tính không phù hợp |
| Secret và credential | Secret reference, đường dẫn vault | Dùng sai secret hoặc chuyển sang nguồn do bên khác kiểm soát |
| Thực thi mã | Plugin, startup command, script hook | Chạy mã với quyền của ứng dụng |
| Đích dữ liệu | Webhook, backup target, export destination | Chuyển dữ liệu tới đích ngoài phạm vi |
| Kết nối mạng | Proxy, callback, upstream endpoint | Truy cập dịch vụ ngoài dự kiến hoặc làm lộ thông tin kết nối |
| Kiểm soát bảo mật | Access check, TLS validation, admin feature | Suy yếu xác thực, phân quyền hoặc bảo vệ truyền tải |
| Audit và giám sát | Log sink, event filter, sampling | Mất sự kiện hoặc làm gián đoạn phát hiện |
| Tính sẵn sàng | Pool size, concurrency, timeout | Quá tải, cạn tài nguyên hoặc ngừng dịch vụ |
| Vòng đời dữ liệu | Retention, purge, archive | Xóa sớm, giữ dữ liệu sai chính sách hoặc mất khả năng khôi phục |

### 4.1. Phân tích cả tổ hợp trường

Một trường đơn lẻ có thể an toàn nhưng tổ hợp thay đổi tạo ra đường tác động mới.

Ví dụ:

- Trường destination chỉ cho phép một nhóm miền nội bộ.
- Trường proxy cho phép chuyển mọi kết nối qua một máy trung gian.
- Trường TLS verification cho phép tắt kiểm tra chứng thư.

Nếu cùng principal sửa được cả ba, kiểm soát destination có thể không còn bảo đảm ý nghĩa dự kiến. Cần kiểm tra cấu hình hiệu lực sau khi hợp nhất mọi trường và nguồn.

### 4.2. Feature flag có thể mang quyền quản trị

Một flag tên là enableDiagnostics có thể mở chức năng đọc bộ nhớ, xuất cấu hình hoặc chạy lệnh chẩn đoán. Không nên cấp quyền sửa mọi flag chỉ vì hệ thống gọi chúng là tính năng sản phẩm.

Phân loại theo hành vi khi bật hoặc tắt, ai truy cập được chức năng sau thay đổi và chức năng ấy dùng danh tính nào.

### 4.3. Giá trị không chứa secret vẫn có thể rất nhạy cảm

Tham chiếu tới secret không nhất thiết chứa giá trị bí mật. Nhưng nếu principal được tự chọn bất kỳ tham chiếu nào và runtime có quyền đọc rộng, ứng dụng có thể truy cập secret ngoài nhu cầu.

Do đó, cần giới hạn cả:

- Những secret mà runtime được phép đọc.
- Những secret reference mà người sửa cấu hình được phép chọn.
- Chức năng dùng secret và đích gửi kết quả.

Chỉ thay credential hoặc chuyển giá trị sang vault không tự thu hẹp quyền sửa cấu hình.

## 5. Thiết kế least privilege cho quyền sửa cấu hình

### 5.1. Giới hạn trên nhiều chiều

Một grant nên được mô tả theo:

~~~text
Principal
  + hành động
  + ứng dụng / tài nguyên
  + trường hoặc nhóm cấu hình
  + môi trường / tenant
  + miền giá trị hợp lệ
  + điều kiện phê duyệt
  + thời gian hiệu lực
~~~

Ví dụ: một kỹ sư trực ca được đề xuất tăng workerConcurrency của Billing API production từ 8 lên 12, trong khoảng cho phép từ 4 tới 16, với thời hạn thay đổi và người phê duyệt đã xác định. Grant đó không bao gồm quyền đổi secret reference, audit sink hoặc danh tính runtime.

### 5.2. Tách quyền cấu hình thông thường và cấu hình bảo mật

Một cách phân chia có thể là:

- Nhóm vận hành điều chỉnh các tham số hiệu năng đã định nghĩa.
- Nhóm bảo mật phê duyệt thay đổi trust hoặc kiểm soát xác thực.
- Pipeline áp dụng bản đã duyệt bằng danh tính riêng.
- Principal quản trị policy được quản lý theo quy trình riêng.

Không cần tạo một role cho từng trường nếu điều đó làm hệ thống không thể vận hành. Có thể nhóm các trường có cùng owner, tác động và điều kiện. Tuy nhiên, nhóm phải có ý nghĩa rõ ràng; role “config-admin” chứa mọi khả năng thường làm mất ranh giới cần bảo vệ.

### 5.3. Kiểm tra giá trị và quan hệ, không chỉ tên trường

Quyền cập nhật timeout cần kiểm tra kiểu và khoảng giá trị. Quyền cập nhật endpoint còn cần kiểm tra đích được phép và cách ứng dụng sử dụng đích đó.

Các kiểm tra thường cần:

- Tên trường thuộc danh sách cho phép.
- Không có trường lạ hoặc trường ẩn có thể thay đổi hành vi.
- Kiểu, kích thước và miền giá trị phù hợp.
- Quan hệ giữa các trường vẫn hợp lệ.
- Đối tượng tham chiếu thuộc đúng môi trường và tenant.
- Đích mạng, plugin và nguồn trust phù hợp với chính sách.
- Cấu hình hợp nhất cuối cùng thỏa các điều kiện bảo mật.

Nếu API nhận thao tác xóa, thay toàn bộ document, import hoặc patch, phải đánh giá riêng từng dạng. Kiểm tra một số trường trong request không đủ nếu thao tác thay document có thể xóa những trường bắt buộc.

### 5.4. Quyền runtime nên hẹp hơn quyền phát hành

Ứng dụng thường chỉ cần đọc cấu hình. Không nên cho runtime quyền ghi lại nguồn cấu hình chuẩn chỉ vì nó cần cập nhật trạng thái hoạt động.

Nếu ứng dụng phải lưu trạng thái động, nên tách vùng dữ liệu đó khỏi cấu hình quản trị. Quyền ghi trạng thái công việc không nên cho phép thay policy hoặc đường dẫn secret.

Quyền phát hành cũng cần bị giới hạn. Một pipeline có thể ghi tất cả ứng dụng production sẽ tạo phạm vi ảnh hưởng rộng dù từng người dùng chỉ được gửi thay đổi nhỏ.

## 6. Luồng thay đổi có phê duyệt và cấp quyền có hạn

### 6.1. Phê duyệt phải gắn với đúng nội dung

Một yêu cầu “cho phép sửa cấu hình Billing hôm nay” quá rộng để chứng minh người phê duyệt đã chấp thuận thay đổi thực tế.

Bản phê duyệt nên gắn với:

- Ứng dụng, môi trường và tài nguyên cụ thể.
- Phiên bản cấu hình nguồn.
- Bản thay đổi hoặc nội dung đích đã chuẩn hóa.
- Người đề xuất và principal sẽ áp dụng.
- Điều kiện áp dụng và thời hạn.
- Mục đích, đánh giá tác động và phương án khôi phục.

Có thể dùng digest của bản thay đổi để ràng buộc nội dung. Tuy nhiên, digest chỉ hỗ trợ đối chiếu: hệ thống vẫn phải bảo vệ bản ghi phê duyệt và thực thi kiểm tra. Một hash do chính client tự gửi không chứng minh đã được phê duyệt.

Nếu nội dung thay đổi sau phê duyệt, phải áp dụng lại quy tắc đánh giá đã định. Không được dùng phê duyệt cho bản A để phát hành bản B.

### 6.2. JIT không chỉ là đặt thời hạn token

Quyền Just-in-Time cần quy định rõ:

1. Điều kiện được cấp grant.
2. Grant cho phép thao tác nào và trên đối tượng nào.
3. Thời điểm bắt đầu và kết thúc.
4. Cách ngăn thao tác mới sau khi hết hạn hoặc bị thu hồi.
5. Cách xử lý yêu cầu đã nhận hoặc job đang chờ.

Token ngắn hạn không bảo đảm request đang chạy hay job đã xếp hàng tự dừng. Hệ thống cần có hợp đồng rõ cho các trường hợp đó và kiểm tra tại điểm có tác động phù hợp.

Một đường thay đổi tương tác có thể dùng phiên qua proxy PAM với thao tác giới hạn. Một pipeline thường phù hợp hơn với danh tính workload và grant ràng buộc vào bản phát hành. Không cần ép mọi thao tác API vào một phiên terminal.

### 6.3. Tách người đề xuất và người duyệt theo mức tác động

Với cấu hình quan trọng, một người không nên vừa đề xuất vừa tự phê duyệt bằng role khác mà họ cũng kiểm soát. Phải kiểm tra quan hệ danh tính thực, không chỉ hai tên tài khoản.

Không phải mọi thay đổi cần cùng số người duyệt. Có thể phân tầng theo rủi ro:

- Tham số vận hành trong khoảng an toàn: tự động kiểm tra và áp dụng theo policy.
- Thay đổi production có tác động đáng kể: phê duyệt bởi owner phù hợp.
- Thay đổi trust, đặc quyền hoặc audit: kiểm soát độc lập chặt hơn.
- Break-glass: luồng khẩn cấp có thời hạn và hậu kiểm theo quy định.

Dù được tự động phê duyệt, hệ thống vẫn cần lưu điều kiện policy nào cho phép thay đổi.

## 7. Thực thi tại dịch vụ cấu hình

### 7.1. Luồng kiểm tra tham khảo

~~~text
Người hoặc pipeline
        |
        v
Xác thực principal
        |
        v
Kiểm tra quyền trên ứng dụng, môi trường, tenant và trường
        |
        v
Kiểm tra phiên bản nguồn và nội dung thay đổi
        |
        v
Kiểm tra schema, quan hệ và policy bảo mật
        |
        v
Đối chiếu phê duyệt, grant và thời hạn
        |
        v
Ghi phiên bản mới với kiểm soát đồng thời
        |
        v
Kích hoạt theo policy
        |
        v
Đọc lại trạng thái hiệu lực, giám sát và lưu bằng chứng
~~~

Gateway có thể xác thực và kiểm tra quyền tổng quát, nhưng dịch vụ biết cấu hình vẫn phải kiểm tra đối tượng và nội dung. Một token có scope config.write không tự cho phép sửa mọi trường của mọi ứng dụng.

### 7.2. Ví dụ yêu cầu cập nhật

~~~http
PATCH /v1/apps/billing/configuration
Authorization: Bearer <access-token>
If-Match: "config-v41"
Content-Type: application/json

{
  "environment": "production",
  "changeId": "CHG-2841",
  "changes": {
    "workerConcurrency": 12
  }
}
~~~

Trong ví dụ này, API có thể dùng If-Match để yêu cầu phiên bản hiện tại vẫn là config-v41. Tên header và mã phiên bản minh họa cơ chế kiểm soát đồng thời; triển khai phải định nghĩa rõ hợp đồng cụ thể.

Các giá trị environment và changeId do client gửi chỉ là thông tin yêu cầu. Server phải đối chiếu chúng với danh tính, tài nguyên thật và bản ghi được tin cậy.

### 7.3. Policy minh họa

~~~yaml
policyName: billing-production-tuning
subject:
  principal: config-publisher-prod
resource:
  application: billing
  environment: production
actions:
  - configuration.update
allowedFields:
  workerConcurrency:
    type: integer
    minimum: 4
    maximum: 16
requirements:
  approvedChange: true
  approvedPayloadMatch: true
  currentVersionMatch: true
  activeGrantAtCommit: true
~~~

Đây là cách mô tả ý định, không phải policy được bảo đảm chạy trên một engine cụ thể. Nó cũng không cho phép thay các trường ngoài allowedFields.

Nếu tài nguyên có tenant, policy phải bổ sung ranh giới tenant. Nếu một trường đổi được đích mạng hoặc tham chiếu quyền, cần kiểm tra sâu hơn khoảng giá trị số.

### 7.4. Mã giả cho điểm cập nhật

~~~text
function updateConfiguration(request, authenticatedPrincipal):
    target = resolveApplicationAndEnvironment(request)

    requireAuthorizedAction(
        authenticatedPrincipal,
        "configuration.update",
        target
    )

    current = readCurrentConfiguration(target)
    proposed = applySupportedPatch(current, request.changes)

    requireAllowedFields(authenticatedPrincipal, target, request.changes)
    validateSchema(proposed)
    validateSecurityConstraints(target, proposed)
    validateReferencedResources(authenticatedPrincipal, target, proposed)

    approval = loadTrustedApproval(request.changeId)
    requireApprovalMatches(
        approval,
        target,
        current.version,
        canonicalChange(current, proposed)
    )

    requireActiveGrant(authenticatedPrincipal, target, approval)

    committed = conditionalCommit(
        target,
        expectedVersion = current.version,
        newConfiguration = proposed,
        authorizationContext = approval
    )

    recordDecisionAndResult(committed)
    return committed.version
~~~

Mã giả chỉ mô tả trách nhiệm. Trong triển khai thật, phải kiểm soát khoảng thời gian giữa kiểm tra và ghi. Nếu quyền hoặc phê duyệt có thể bị thu hồi trong khoảng đó, cần cơ chế thực thi phù hợp với hợp đồng thu hồi tại thời điểm commit.

Không thể coi hai bước “kiểm tra một lần” và “ghi sau đó” là nguyên tử chỉ vì chúng nằm cạnh nhau trong mã nguồn.

### 7.5. Job bất đồng bộ phải mang ngữ cảnh đã được bảo vệ

Nếu request chỉ tạo job, worker áp dụng cấu hình cần biết:

- Đúng tài nguyên và phiên bản nguồn.
- Nội dung được phép áp dụng.
- Phê duyệt và principal chịu trách nhiệm.
- Thời hạn và điều kiện cần kiểm tra lại.
- Chính sách khi quyền bị thu hồi trước lúc chạy.

Không được biến một request được giới hạn thành job chạy với quyền quản trị chung rồi tin mọi trường trong payload. Credential rộng của worker không phải căn cứ cho phép người gọi thực hiện mọi thay đổi.

Định nghĩa rõ quyền nào phải còn hiệu lực khi job chạy và trường hợp nào được phép hoàn tất sau khi phiên người đề xuất kết thúc. Khi không còn đáp ứng điều kiện bắt buộc, job phải dừng hoặc chuyển sang trạng thái cần đánh giá theo hợp đồng đã công bố.

## 8. Bảo vệ các đường ghi thay thế

### 8.1. Cấu hình trong repository

Quyền sửa repository có thể trở thành quyền sửa production nếu pipeline tự phát hành thay đổi. Kiểm soát phải bao gồm:

- Nhánh và đường dẫn được bảo vệ.
- Người có quyền bỏ qua kiểm tra.
- Cách xác định bản commit đã được duyệt.
- Quyền sửa workflow, template và script tạo cấu hình.
- Danh tính và quyền của pipeline.
- Khả năng sửa artifact sau khi đã duyệt.

Chỉ áp dụng phê duyệt cho tệp cấu hình nhưng cho cùng principal sửa script kiểm tra có thể làm mất giá trị của quy trình.

### 8.2. Cấu hình trên máy chủ

Quyền ghi tệp phải xét cả quyền trên thư mục cha và cơ chế thay thế tệp. Có thể tồn tại đường thay một tệp thông qua đổi tên, thay liên kết hoặc ghi từ một mount khác dù quyền trực tiếp trên tệp có vẻ bị hạn chế.

Cần xem xét tài khoản dịch vụ, quyền sở hữu, filesystem, công cụ triển khai và môi trường thực tế. Không nên dựa vào một thiết lập quyền đơn lẻ mà bỏ qua khả năng sửa thư mục hoặc công cụ đang dùng quyền cao hơn.

Nếu dùng công cụ đặc quyền để sửa cấu hình, giới hạn cả thao tác và giá trị đầu vào. Một wrapper cho phép nhập đường dẫn tùy ý hoặc chạy lệnh phụ có thể trở thành quyền thực thi rộng.

### 8.3. Cấu hình trong cơ sở dữ liệu

Tài khoản ứng dụng chỉ cần đọc cấu hình không nên có quyền cập nhật bảng cấu hình quản trị. Nếu có công cụ hỗ trợ truy cập trực tiếp, phải quản lý riêng và đối soát với luồng chuẩn.

Trigger hoặc kiểm tra tại giao diện không tự bảo vệ mọi đường ghi. Cần biết chính sách nào được thực thi trong cơ sở dữ liệu, chính sách nào nằm ở dịch vụ và đường truy cập nào có thể bỏ qua chúng.

### 8.4. Cấu hình trên nền tảng triển khai

Quyền sửa định nghĩa workload, biến môi trường hoặc volume có thể ghi đè cấu hình từ repository. Quyền thay danh tính workload, image hoặc startup command còn có thể vượt xa quyền sửa một tham số.

Kiểm kê cả quyền cập nhật tài nguyên, quyền gắn identity và quyền quản trị admission hoặc policy tương ứng. Giới hạn giao diện cấu hình ứng dụng không đủ nếu principal vẫn quản trị toàn bộ nền tảng chạy ứng dụng đó.

## 9. Secret, vault và danh tính phát hành

### 9.1. Tránh đưa secret vào diff và log

Cấu hình nên dùng tham chiếu secret khi phù hợp. Tuy nhiên, bản diff, lỗi kiểm tra và sự kiện audit vẫn có thể làm lộ giá trị nhạy cảm nếu hệ thống ghi toàn bộ document.

Cần thiết kế:

- Phân loại trường nhạy cảm.
- Che hoặc loại giá trị bí mật khỏi log và phản hồi.
- Quyền đọc các phiên bản cấu hình.
- Nơi lưu bản cũ và bản phục hồi.
- Cách hạn chế plaintext trong bộ nhớ, tệp tạm và artifact.

Một giá trị đã che trong giao diện không có nghĩa API, log hay bản lưu cũ cũng đã che.

### 9.2. Tách credential của pipeline và của runtime

Pipeline dùng credential để phát hành; runtime dùng credential để hoạt động. Hai mục đích này thường cần quyền khác nhau.

Ưu tiên danh tính workload và credential có hạn khi hạ tầng hỗ trợ. Nếu phải dùng credential lưu trong vault, cần giới hạn người hoặc máy lấy được, thời hạn sử dụng, cơ chế luân chuyển và thu hồi.

Luân chuyển credential không tự xóa grant hoặc role đã cấp cho principal. Khi thu hồi quyền sửa cấu hình, phải xử lý cả quyền hiệu lực và đường xác thực liên quan.

### 9.3. Không lưu toàn bộ quyền trong một credential dùng chung

Một tài khoản dùng chung cho mọi pipeline làm giảm khả năng truy vết và tăng phạm vi ảnh hưởng. Nếu không thể tách ngay, cần ghi rõ ngoại lệ, owner, phạm vi, thời hạn xử lý và biện pháp giới hạn.

Bằng chứng “tài khoản deploy đã sửa” chưa đủ để xác định thay đổi đến từ pipeline, phiên bản và yêu cầu nào.

## 10. Bằng chứng, phát hiện drift và xác minh hiệu lực

### 10.1. Ghi nhận quyết định và kết quả

Một sự kiện audit nên cho phép nối:

- Principal xác thực và người đề xuất nếu có.
- Principal áp dụng và đường gọi.
- Tài nguyên, môi trường và tenant.
- Phiên bản trước và sau.
- Trường thay đổi hoặc bản diff đã xử lý dữ liệu nhạy cảm.
- Change ID, phê duyệt và grant liên quan.
- Quyết định policy và lý do từ chối hoặc cho phép.
- Kết quả ghi, kích hoạt và xác minh.
- Thời điểm và mã tương quan.

Ví dụ minh họa:

~~~json
{
  "event": "configuration.applied",
  "actor": "config-publisher-prod",
  "requestedBy": "operator-017",
  "application": "billing",
  "environment": "production",
  "changeId": "CHG-2841",
  "fromVersion": "config-v41",
  "toVersion": "config-v42",
  "changedFields": ["workerConcurrency"],
  "grantId": "grant-184",
  "decision": "allow",
  "activationState": "verified",
  "correlationId": "cfg-operation-019"
}
~~~

Không đưa access token, giá trị secret hoặc nội dung nhạy cảm nguyên vẹn vào sự kiện. Bản ghi phê duyệt và bằng chứng phải được bảo vệ khỏi principal đang sửa cấu hình ở mức phù hợp.

### 10.2. Ghi thành công khác với có hiệu lực

Có thể xảy ra:

- API đã lưu bản mới nhưng ứng dụng chưa reload.
- Một số instance đã nhận cấu hình, số khác chưa.
- Biến môi trường ghi đè giá trị mới.
- Cache còn dùng bản cũ.
- Ứng dụng từ chối cấu hình và quay về bản trước.
- Một tác vụ đồng bộ ghi lại giá trị khác.

Vì vậy, readback cần xác nhận cả bản lưu và phiên bản hiệu lực khi cơ chế hệ thống cho phép. Với nhiều instance, cần định nghĩa ngưỡng hoàn thành và cách xử lý tình trạng chỉ áp dụng một phần.

Không cần xuất mọi giá trị nhạy cảm để chứng minh readback; có thể kiểm tra phiên bản, digest phù hợp, metadata và hành vi đã thiết kế.

### 10.3. Phát hiện drift

Drift là khác biệt giữa cấu hình được kỳ vọng và cấu hình thực tế. Nguồn phát hiện có thể là:

- So sánh nguồn chuẩn với bản đang lưu.
- So sánh phiên bản được phát hành với phiên bản instance đang dùng.
- Theo dõi sự kiện thay đổi ngoài pipeline.
- Phát hiện principal ghi không nằm trong luồng cho phép.
- Cảnh báo khi thay đổi cấu hình bảo mật hoặc audit.

Không phải mọi drift đều độc hại. Có thể là thay đổi khẩn cấp, lỗi đồng bộ hoặc khác biệt tạm thời. Quy trình xử lý phải xác định owner, mức tác động, cách xác minh và quyết định giữ hay khôi phục.

Tự động ghi đè mọi drift có thể xóa một thay đổi phục hồi cần thiết. Chỉ tự động khắc phục trong các trường hợp đã được định nghĩa và kiểm thử.

## 11. Thu hồi quyền, rollback và ứng phó sự cố

### 11.1. Thu hồi quyền sửa không hoàn tác thay đổi đã thực hiện

Nếu một principal đã đổi đích xuất dữ liệu, thu hồi grant chỉ ngăn thao tác tương lai theo cơ chế thực thi. Cấu hình độc hại có thể vẫn hoạt động.

Khi xử lý sự cố, cần xem xét riêng:

1. Chặn cấp quyền hoặc phát hành credential mới.
2. Ngăn thay đổi mới qua mọi đường ghi liên quan.
3. Xử lý phiên, token và job đang tồn tại theo khả năng hệ thống.
4. Xác định thay đổi đã được áp dụng.
5. Khôi phục cấu hình và xác minh trạng thái hiệu lực.
6. Đánh giá secret, dữ liệu hoặc quyền khác đã bị ảnh hưởng.
7. Lưu bằng chứng phục vụ điều tra.

Không giả định vô hiệu hóa tài khoản sẽ ngay lập tức hủy mọi access token hoặc job đã được cấp. Cần kiểm tra hành vi thực tế của cơ chế xác thực, cache quyền và dịch vụ thực thi.

### 11.2. Rollback cần một bản phục hồi còn phù hợp

Trước khi rollback, kiểm tra:

- Bản cũ có tương thích với phiên bản ứng dụng hiện tại không.
- Secret reference còn hợp lệ không.
- Endpoint và trust còn được cho phép không.
- Có làm mất một bản vá bảo mật không.
- Có thay đổi dữ liệu hoặc trạng thái bên ngoài mà cấu hình không đảo ngược được không.
- Có cần thứ tự phối hợp giữa các dịch vụ không.

Rollback cấu hình không khôi phục dữ liệu đã xuất ra ngoài hoặc hoàn tác mọi tác động của một thay đổi. Đối với tác động không thể đảo ngược, cần biện pháp ứng phó tương ứng.

### 11.3. Break-glass phải được giới hạn và hậu kiểm

Trong sự cố, có thể cần sửa cấu hình khi pipeline chuẩn không hoạt động. Luồng break-glass cần có:

- Danh tính riêng và owner rõ ràng.
- Phạm vi tối thiểu theo khả năng nền tảng.
- Điều kiện kích hoạt và thời hạn.
- Giám sát thao tác và bằng chứng.
- Cách đóng quyền sau sử dụng.
- Đối soát cấu hình về nguồn chuẩn.
- Hậu kiểm lý do, tác động và các thay đổi đi kèm.

Tránh để một lần sửa khẩn cấp tạo ra đường ghi thường trực không có giám sát.

## 12. Những thiết kế thường thất bại

| Thiết kế | Vì sao không đạt mục tiêu | Hướng xử lý |
| --- | --- | --- |
| Mọi kỹ sư có role sửa mọi cấu hình | Phạm vi rộng hơn nhu cầu công việc | Giới hạn theo ứng dụng, môi trường và nhóm trường |
| Chỉ bảo vệ giao diện quản trị | API, database hoặc shell vẫn có thể ghi | Kiểm kê và kiểm soát mọi đường ghi |
| Phê duyệt theo ticket chung | Nội dung áp dụng có thể khác nội dung được xem | Ràng buộc phê duyệt vào tài nguyên, phiên bản và bản thay đổi |
| Có JIT nên không kiểm tra job nền | Job có thể chạy sau khi điều kiện hết hiệu lực | Quy định và thực thi điều kiện tại thời điểm phù hợp |
| Giấu nút sửa trường nhạy cảm | Client có thể tự gửi request | Thực thi kiểm tra tại server |
| Runtime được sửa cấu hình của chính nó | Lỗi ứng dụng có thể thành sửa policy hoặc đặc quyền | Tách quyền đọc cấu hình và ghi trạng thái |
| Chỉ lưu log request thành công | Không biết bản nào thực sự hoạt động | Theo dõi ghi, kích hoạt và readback |
| Rollback luôn được miễn kiểm tra | Bản cũ có thể không còn an toàn | Kiểm tra chính sách và tương thích hiện tại |
| Đổi credential sau sự cố là đủ | Cấu hình và grant cũ có thể vẫn tồn tại | Thu hồi quyền và xử lý trạng thái đã thay đổi |

## 13. Bài thực hành: giới hạn quyền sửa Billing API

### 13.1. Bối cảnh

Billing API production có các trường:

~~~yaml
workerConcurrency: 8
requestTimeoutSeconds: 30
exportDestination: https://reports.example.internal
runtimeIdentity: billing-runtime-prod
auditEnabled: true
secretReference: vault://billing/prod/database
~~~

Đây là cấu hình giả định để phân tích, không phải một tệp triển khai hoàn chỉnh.

Hiện tại nhóm trực ca có thể sửa toàn bộ document qua giao diện. Pipeline cũng có quyền ghi toàn bộ cấu hình. Ngoài ra, tài khoản hỗ trợ có quyền cập nhật trực tiếp bảng cấu hình.

Nhu cầu thực tế của ca trực là tăng workerConcurrency khi xử lý tồn đọng và điều chỉnh requestTimeoutSeconds trong một khoảng đã định. Nhóm này không cần đổi runtime identity, secret reference, audit hoặc đích xuất dữ liệu.

### 13.2. Thiết kế cần tạo

Đề xuất một phương án thỏa các yêu cầu:

1. Kỹ sư trực ca chỉ được đề xuất hai tham số vận hành đã nêu.
2. Giá trị phải nằm trong miền được owner ứng dụng xác nhận.
3. Quyền production không dùng cho staging và ngược lại.
4. Pipeline chỉ áp dụng bản đã duyệt cho đúng ứng dụng.
5. Người đề xuất không tự phê duyệt thay đổi thuộc diện cần phê duyệt độc lập.
6. Thay đổi phải kiểm tra phiên bản nguồn để tránh ghi đè thay đổi khác.
7. Đường ghi trực tiếp trong cơ sở dữ liệu được xử lý bằng policy rõ ràng.
8. Có readback phiên bản đang hoạt động và bằng chứng đối soát.
9. Có cách thu hồi và xử lý job đang chờ.

### 13.3. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Đổi concurrency trong khoảng hợp lệ với đầy đủ điều kiện | Cho phép, ghi nhận phiên bản và xác minh hiệu lực |
| Đổi concurrency vượt khoảng | Từ chối do kiểm tra giá trị |
| Gửi thêm runtimeIdentity trong cùng request | Từ chối phần thay đổi ngoài quyền theo hợp đồng API |
| Xóa auditEnabled qua thao tác patch hoặc thay document | Không được tạo cấu hình thiếu kiểm soát bắt buộc |
| Dùng grant staging để sửa production | Từ chối theo ranh giới môi trường |
| Đổi ứng dụng trong URL nhưng giữ changeId cũ | Từ chối vì phê duyệt không khớp tài nguyên |
| Sửa payload sau khi được duyệt | Từ chối vì nội dung không khớp |
| Gửi bản thay đổi dựa trên phiên bản cũ | Không ghi đè âm thầm; trả kết quả xung đột theo hợp đồng |
| Job được nhận trước khi grant bị thu hồi | Xử lý theo policy job đã định và lưu lý do |
| Gọi API trực tiếp thay cho giao diện | Vẫn chịu cùng kiểm tra server |
| Thay cấu hình qua đường database không được phép | Bị chặn; nếu tồn tại ngoại lệ thì được giám sát và đối soát |
| Một instance chưa nhận phiên bản mới | Không báo toàn bộ triển khai đã xác minh |
| Rollback về bản có secret reference không còn hợp lệ | Không bỏ qua kiểm tra chỉ vì là rollback |

Kiểm thử phải chứng minh lý do bị từ chối. Một request thất bại do lỗi kết nối hoặc dữ liệu sai định dạng không chứng minh cơ chế phân quyền trên trường hoạt động.

### 13.4. Đầu ra cần nộp

- Inventory principal, đường ghi và owner.
- Ma trận quyền theo ứng dụng, môi trường và nhóm trường.
- Luồng đề xuất, phê duyệt, áp dụng và kích hoạt.
- Policy về JIT, thu hồi và job đang chờ.
- Kế hoạch xử lý đường ghi database.
- Mẫu bằng chứng không chứa secret.
- Kết quả kiểm thử cho cả đường được phép và đường bị cấm.
- Phương án rollback và đối soát cấu hình hiệu lực.

Bài thực hành đạt khi người rà soát có thể giải thích rõ ai được thay đổi giá trị nào, vì sao được phép và bằng chứng nào xác nhận thay đổi đã hoạt động đúng phạm vi.

## 14. Chỉ số để duy trì kiểm soát

Không nên chỉ đếm số role hoặc số phiên PAM. Các chỉ số hữu ích hơn gồm:

- Tỷ lệ nguồn cấu hình và đường ghi đã có owner.
- Số principal còn quyền sửa cấu hình rộng.
- Số ngoại lệ quyền production quá hạn.
- Tỷ lệ thay đổi có thể nối từ phê duyệt tới phiên bản hiệu lực.
- Thời gian từ quyết định thu hồi tới khi thao tác mới bị từ chối.
- Thời gian phát hiện và xử lý drift ngoài luồng chuẩn.
- Số thay đổi cấu hình bảo mật không đi qua điều kiện bắt buộc.
- Tỷ lệ trường đặc quyền có kiểm thử từ chối và kiểm tra đường ghi thay thế.

Phải nêu rõ mẫu số. “Mọi thay đổi đều được audit” chỉ có ý nghĩa khi bao gồm cả API, pipeline, công cụ quản trị và các ngoại lệ đã được đưa vào phạm vi kiểm soát.

## 15. Câu hỏi tự kiểm tra

**Vì sao quyền sửa một endpoint có thể là đặc quyền?**

Endpoint có thể quyết định nơi gửi dữ liệu, nguồn tin cậy hoặc nơi tải mã. Tác động phụ thuộc vào cách ứng dụng sử dụng giá trị và danh tính runtime.

**Đã đưa secret vào vault thì quyền sửa cấu hình có còn rủi ro không?**

Có. Người sửa có thể đổi secret reference hoặc thay đường sử dụng secret. Vault cần đi cùng quyền runtime hẹp và kiểm tra tham chiếu được phép.

**Phê duyệt một ticket có đủ để cho phép mọi cập nhật trong ticket đó không?**

Không nên mặc định như vậy. Phê duyệt cần gắn với nội dung, tài nguyên, phiên bản và điều kiện cụ thể theo policy.

**Token đã hết hạn thì job có tự dừng không?**

Không có bảo đảm chung. Hệ thống phải định nghĩa điều kiện áp dụng cho job và thực thi chúng ở điểm phù hợp.

**Thu hồi quyền sửa có tự trả cấu hình về trạng thái cũ không?**

Không. Quyền tương lai và cấu hình đã thay đổi là hai trạng thái khác nhau, cần xử lý riêng.

**Vì sao quyền sửa workflow phải được xét cùng quyền sửa cấu hình?**

Workflow có thể quyết định cách kiểm tra, phê duyệt và phát hành cấu hình. Người kiểm soát workflow có thể tác động tới toàn bộ chuỗi thực thi nếu không có ranh giới độc lập phù hợp.

**Readback chỉ đọc lại document đã lưu có đủ không?**

Chưa chắc. Cần biết ứng dụng đang dùng phiên bản nào, có nguồn khác ghi đè hay có instance chưa nhận cấu hình không.

**Rollback có phải luôn được phép với người có quyền sửa thông thường không?**

Không. Nó cần được đánh giá theo quyền và tác động thực tế; một bản cũ có thể khôi phục cấu hình không còn phù hợp.

Quyền sửa cấu hình cần được quản lý như một khả năng tác động lên hành vi, dữ liệu và đặc quyền của ứng dụng. Khi inventory bao phủ mọi đường ghi, quyền được giới hạn theo nội dung và tài nguyên, phê duyệt gắn với đúng phiên bản, còn bằng chứng nối tới trạng thái hiệu lực, PAM mới kiểm soát được quyền này trong suốt vòng đời vận hành.
