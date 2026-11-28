# Storage ngoài web root — Đặc tả yêu cầu lưu trữ tệp ngoài vùng phục vụ công khai

## 1. Mục tiêu bảo mật của việc lưu ngoài web root

Web root là vùng nội dung được web server hoặc một thành phần phục vụ static ánh xạ ra HTTP. Nếu một tệp nằm trong vùng đó, hệ thống có thể trả nội dung tệp mà không đi qua luồng kiểm tra quyền của ứng dụng.

Lưu tệp ngoài web root giúp tách hai việc: nơi ứng dụng giữ dữ liệu và nơi máy chủ web được phép phục vụ nội dung trực tiếp. Đây là ranh giới quan trọng đối với tài liệu khách hàng, tệp đính kèm hồ sơ, bản xuất báo cáo, bản sao lưu và các tệp do người dùng tải lên.

Trong module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, yêu cầu cần chuyển từ câu “đặt upload ở thư mục riêng” thành những điều có thể kiểm chứng:

- Thành phần nào có thể ánh xạ đường dẫn lưu trữ thành URL?
- Tệp nào được phép phục vụ công khai, tệp nào phải qua phân quyền?
- Tệp tạm, bản preview và bản xuất có được giữ cùng mức bảo vệ không?
- Ai có quyền đọc, ghi hoặc thay đổi ánh xạ phục vụ tệp?
- API tải xuống xác định đúng tenant và tài nguyên bằng cách nào?
- Nếu cấu hình web server, CDN hoặc object storage thay đổi, điều gì chứng minh ranh giới vẫn còn hiệu lực?

Bài học dùng ví dụ cổng quản lý hồ sơ nhiều tenant. Tài liệu trong hồ sơ là riêng tư, chỉ người đang có quyền với hồ sơ mới được tải. Các con số xuất hiện trong ví dụ là giả định thiết kế, không phải ngưỡng bắt buộc cho mọi hệ thống.

## 2. Web root là một ánh xạ phục vụ, không chỉ là tên thư mục

Một cấu trúc có thể được thiết kế như sau:

```text
/srv/portal/public/
    app.css
    app.js
    logo.png

/srv/portal-private/
    objects/
    quarantine/
    temporary-exports/
```

Trong ví dụ:

- `/srv/portal/public/` được ánh xạ để phục vụ tài nguyên static công khai.
- `/srv/portal-private/` là vùng dữ liệu riêng, không có ánh xạ static cho client.
- Ứng dụng hoặc dịch vụ truy cập tệp sử dụng quyền riêng để đọc nội dung cần thiết.
- Client dùng resource ID để yêu cầu tài nguyên, không gửi đường dẫn lưu trữ làm căn cứ đọc tệp.

Trên Windows có thể biểu diễn cùng ý tưởng bằng các đường dẫn như `D:/apps/portal/wwwroot` và `D:/data/portal-private`. Tên ổ đĩa hoặc thư mục không tạo ra bảo đảm bảo mật; bảo đảm đến từ cấu hình phục vụ, quyền truy cập và luồng xử lý thực tế.

### 2.1. Alias có thể mở lại vùng riêng tư

Một thư mục nằm ngoài document root vẫn có thể bị public nếu có alias, route static, volume mount, reverse proxy hoặc thành phần khác ánh xạ nó ra HTTP.

Ví dụ logic:

```text
Document root: /srv/portal/public

Ánh xạ bổ sung:
    /files/* → /srv/portal-private/objects/*
```

Trong trường hợp này, vị trí filesystem nằm ngoài document root nhưng nội dung vẫn có đường phục vụ trực tiếp. Yêu cầu chỉ kiểm tra vị trí thư mục sẽ bỏ sót đường truy cập đó.

Phải kiểm kê toàn bộ ánh xạ có thể dẫn tới dữ liệu: web server chính, static middleware của ứng dụng, container phụ, cổng quản trị, CDN, origin và các môi trường triển khai liên quan.

### 2.2. Web root khác project root

Thư mục chứa mã nguồn, thư mục làm việc của tiến trình và document root có thể khác nhau. Một tệp nằm ngoài project vẫn có thể bị một server khác phục vụ; một tệp trong project có thể không được ánh xạ ra ngoài.

Vì vậy, đặc tả nên mô tả ranh giới phục vụ và quyền, thay vì dựa vào tên `uploads`, `private` hoặc vị trí tương đối với mã nguồn.

### 2.3. Object storage không có cùng khái niệm thư mục vật lý

Trong object storage, prefix như `private/` thường chỉ là một phần định danh object. Tên prefix không tự tạo quyền riêng tư.

Cần xác định bucket/container, policy, danh tính dịch vụ, endpoint, cơ chế public access và cấu hình CDN/origin. Mục tiêu tương đương là object riêng tư không có đường đọc công khai ngoài cơ chế truy cập được phê duyệt.

## 3. Vì sao đây là yêu cầu về business logic security?

Cổng hồ sơ có thể kiểm tra quyền đúng trong API `GET /documents/{id}`, nhưng nếu cùng tệp còn truy cập được qua `/uploads/filename.pdf`, người dùng có thể đi vòng qua quyết định nghiệp vụ.

Rủi ro không chỉ là đoán tên tệp. URL có thể bị lộ qua lịch sử trình duyệt, log, tin nhắn, metadata hoặc một tài khoản từng có quyền. Tên khó đoán giảm khả năng khám phá ngẫu nhiên nhưng không thay thế phân quyền.

Ngoài rò rỉ dữ liệu, lưu nội dung người dùng trong vùng có khả năng thực thi hoặc render còn có thể tạo rủi ro chạy nội dung không được tin cậy. Ví dụ, tệp được xử lý như script hoặc template có thể đi vào một luồng nguy hiểm tùy cấu hình nền tảng.

Đặt ngoài web root giảm đường truy cập trực tiếp, nhưng ứng dụng vẫn phải kiểm soát cách đọc, xử lý và trả tệp. Nếu ứng dụng tự nạp tệp tải lên như mã hoặc template, vị trí ngoài web root không tự ngăn hành vi đó.

### 3.1. Ba mục tiêu riêng cần phối hợp

| Mục tiêu | Câu hỏi cần trả lời |
| --- | --- |
| Giới hạn khả năng được phục vụ | Có đường static hoặc public nào tới dữ liệu riêng không? |
| Kiểm soát truy cập nghiệp vụ | Chủ thể hiện tại có quyền đọc tài nguyên cụ thể không? |
| An toàn khi xử lý và phân phối nội dung | Tệp có bị thực thi, render hoặc sử dụng ngoài chính sách không? |

Một giải pháp đạt mục tiêu đầu tiên vẫn cần chứng minh hai mục tiêu còn lại theo phạm vi hệ thống.

## 4. Mô hình đe dọa và tài sản cần bảo vệ

| Kịch bản | Hậu quả | Hướng yêu cầu |
| --- | --- | --- |
| Tệp riêng tư nằm trong vùng static | Bỏ qua phân quyền ứng dụng | Vùng riêng không có ánh xạ phục vụ công khai |
| Alias hoặc static middleware trỏ vào vùng riêng | Public lại dữ liệu dù đã chuyển thư mục | Kiểm kê và kiểm thử mọi đường ánh xạ |
| Client gửi đường dẫn thay cho resource ID | Đọc tài nguyên ngoài phạm vi | Máy chủ tự ánh xạ ID tới storage reference được kiểm soát |
| Người dùng đổi resource ID của tenant khác | Truy cập tài liệu ngoài quyền | Phân quyền tài nguyên và tenant trước khi trả metadata/nội dung |
| Tệp tạm được tạo trong thư mục public | Rò rỉ trong một khoảng ngắn | Mọi giai đoạn lưu giữ đều thuộc vùng được bảo vệ |
| Thumbnail, preview hoặc export lưu ở nơi public | Lộ bản dẫn xuất của dữ liệu nhạy cảm | Dẫn xuất giữ phân loại và chính sách truy cập phù hợp |
| Bucket hoặc origin công khai | API riêng tư bị đi vòng qua endpoint khác | Kiểm soát policy và truy cập origin |
| Symlink hoặc thay đổi đường dẫn lúc đọc | Vượt ranh giới vùng lưu trữ | Giải quyết tài nguyên bằng cơ chế chống thoát vùng và race phù hợp |
| CDN giữ nội dung sau khi quyền đổi | Phân phối dữ liệu theo trạng thái cũ | Chính sách cache tương thích với yêu cầu thu hồi quyền |
| Tệp tải lên bị dùng như mã/template | Tác động tới máy chủ hoặc người dùng | Không coi dữ liệu upload là mã; tách luồng xử lý/hiển thị |
| Log hoặc thông báo lỗi chứa URL có quyền | Lộ khả năng truy cập hoặc cấu trúc lưu trữ | Giới hạn dữ liệu ghi log, che thông tin nhạy cảm |
| Vùng lưu riêng tăng không giới hạn | Cạn đĩa, ảnh hưởng dịch vụ | Quota, giới hạn tệp, cleanup và giám sát dung lượng |

Các tài sản bao gồm nội dung gốc, bản dẫn xuất, metadata nhạy cảm, quyền truy cập và khả năng kiểm soát đường phân phối. Không chỉ kiểm tra tệp gốc mà bỏ qua bản preview hoặc tệp đã được sao chép sang môi trường khác.

## 5. Kiến trúc truy cập qua kiểm soát quyền

Với tài liệu riêng tư, một kiến trúc logic có thể như sau:

```text
Client
   |
   | GET /documents/{resource_id}/content
   v
Điểm truy cập ứng dụng
   |
   +--> Xác thực chủ thể
   +--> Xác định tenant từ ngữ cảnh đáng tin
   +--> Đọc metadata và chính sách hiện hành
   +--> Kiểm tra quyền với hồ sơ/tài liệu cụ thể
   +--> Kiểm tra trạng thái tài liệu được phép phát hành
   |
   v
Dịch vụ truy cập storage
   |
   | storage reference do máy chủ quản lý
   v
Vùng lưu riêng, không có đường static công khai
   |
   v
Phản hồi nội dung theo chính sách phân phối và audit
```

### 5.1. Metadata tách khỏi tên tệp người dùng

Một bản ghi tài nguyên có thể gồm:

```json
{
  "resource_id": "doc-482",
  "tenant_id": "tenant-07",
  "parent_record_id": "case-915",
  "storage_reference": "object-ref-a83",
  "storage_version": "version-4",
  "original_filename": "ho-so.pdf",
  "classification": "private",
  "release_state": "APPROVED_FOR_DOWNLOAD",
  "content_type": "application/pdf",
  "size_bytes": 248120
}
```

Đây là minh họa metadata phía máy chủ. Không bắt buộc trả `storage_reference` cho client. Tên gốc phục vụ hiển thị, không nên được dùng trực tiếp làm đường dẫn có quyền đọc.

Resource ID khó đoán cũng không thay thế kiểm tra quyền. Quan hệ tenant, hồ sơ cha, trạng thái và chính sách phải được kiểm tra từ nguồn có thẩm quyền.

### 5.2. Không cho client chọn vị trí đọc

Một API nhận `path=/some/location` hoặc object key tùy ý có thể biến ứng dụng thành bộ đọc tệp ngoài ý định. Thiết kế ưu tiên nhận định danh nghiệp vụ, sau đó máy chủ ánh xạ sang tài nguyên được quản lý.

Nếu một chức năng thực sự cần đầu vào có cấu trúc đường dẫn, yêu cầu phải định nghĩa miền giá trị, ranh giới và cơ chế giải quyết an toàn. Không mặc định việc URL decode hoặc nối thư mục đã xử lý hết vấn đề.

### 5.3. Mã giả cho đường tải xuống

```text
download(resource_id, request_context):
    identity = authenticate(request_context)
    tenant = verified_tenant(identity, request_context)

    metadata = load_resource_in_tenant(resource_id, tenant)
    authorize_read(identity, metadata, current_policy)
    require_downloadable_state(metadata)

    handle = private_storage.open_managed_reference(
        metadata.storage_reference,
        metadata.storage_version
    )

    record_access_decision_without_secrets(identity, metadata)
    return stream_with_approved_headers(handle, metadata)
```

Mã giả không thay thế thiết kế triển khai. `Open_managed_reference` phải chỉ mở tài nguyên hợp lệ của backend, bảo vệ ranh giới lưu trữ và phiên bản. Không được triển khai nó bằng cách tin một đường dẫn do client đưa qua.

Trạng thái phát hành phải gắn với đúng nội dung hoặc phiên bản đã được kiểm tra. Nếu object có thể bị ghi đè sau khi được phê duyệt, việc chỉ kiểm tra một cờ trên resource không bảo đảm nội dung đang phục vụ vẫn là nội dung được phép.

## 6. Bảo vệ ranh giới lưu trữ trên filesystem

### 6.1. Quyền tối thiểu theo vai trò

Nếu kiến trúc có tiến trình phục vụ static tách khỏi ứng dụng, có thể giới hạn tiến trình static chỉ đọc vùng public, còn ứng dụng hoặc file service đọc vùng riêng theo nhu cầu.

Một ma trận quyền minh họa:

| Chủ thể | Vùng public | Vùng riêng | Quyền thay ánh xạ |
| --- | --- | --- | --- |
| Tiến trình static riêng | Đọc nội dung được phát hành | Không đọc nếu kiến trúc không cần | Không |
| Ứng dụng/file service | Theo nhu cầu triển khai | Chỉ thao tác cần thiết | Không tự sửa cấu hình web server |
| Worker xử lý tệp | Không ghi nội dung người dùng vào vùng public | Đọc/ghi vùng được phân công | Không |
| Pipeline triển khai được kiểm soát | Cập nhật tài nguyên ứng dụng theo quy trình | Không mặc nhiên đọc tài liệu khách hàng | Thay theo quyền và review cấu hình |
| Quản trị được ủy quyền | Theo nhiệm vụ | Theo nhiệm vụ, có audit | Theo quy trình được phê duyệt |

Ma trận phải phản ánh triển khai thật. Nếu static server và ứng dụng chạy chung tiến trình hoặc danh tính, không thể tuyên bố đã phân tách quyền hệ điều hành như hai chủ thể độc lập. Khi đó cần mô tả giới hạn của ranh giới và các lớp bảo vệ còn lại.

### 6.2. Không cho nội dung người dùng trở thành mã triển khai

Đường ghi upload không được ghi đè tài nguyên ứng dụng, cấu hình phục vụ hoặc mã thực thi. Vùng public và artifact triển khai nên được bảo vệ khỏi quyền ghi không cần thiết của luồng xử lý tệp.

Không dùng thư mục upload làm nguồn nạp script, template hoặc cấu hình động. Một cấu hình không cho thực thi trực tiếp từ một mount không tự ngăn interpreter đọc nội dung rồi xử lý như mã.

Đặc tả cần tập trung vào kết quả: dữ liệu người dùng không được trở thành mã hoặc cấu hình có quyền của ứng dụng qua các đường đã được kiểm kê.

### 6.3. Ranh giới đường dẫn và symlink

Nếu backend sử dụng filesystem path, cần kiểm soát những cách có thể dẫn ra ngoài vùng được phép:

- Thành phần đường dẫn đi lên thư mục cha.
- Đường dẫn tuyệt đối hoặc dạng có ý nghĩa đặc biệt trên nền tảng.
- Khác biệt giải mã, dấu phân cách hoặc chuẩn hóa.
- Symlink, liên kết hoặc mount ngoài dự kiến.
- Thay đổi tệp hoặc đường dẫn giữa kiểm tra và mở.

Kiểm tra chuỗi bắt đầu bằng một prefix không đủ để chứng minh tài nguyên thực tế thuộc vùng cho phép. Việc canonicalize rồi mở sau đó cũng có thể gặp race nếu một chủ thể khác được thay đổi đường dẫn trung gian.

Cần chọn cơ chế mở tài nguyên và quản lý quyền phù hợp với nền tảng, đồng thời kiểm thử trên hệ điều hành triển khai. Có thể giảm rủi ro bằng cách không cho chủ thể không tin cậy tạo cấu trúc đường dẫn hoặc liên kết trong vùng được ứng dụng sử dụng.

Bài học này đặc tả yêu cầu về ranh giới; không áp một hàm xử lý đường dẫn duy nhất cho mọi nền tảng.

### 6.4. Định danh và phiên bản nội dung

Ứng dụng nên quản lý định danh lưu trữ riêng với tên do người dùng cung cấp. Khi cần bảo đảm nội dung sau kiểm tra không bị thay, phải ràng buộc trạng thái phát hành với phiên bản, nội dung bất biến hoặc cơ chế tương đương.

Không đánh dấu resource là được tải rồi cho phép một đường upload khác thay object phía dưới mà không đánh giá lại. Storage ngoài web root không tự giải quyết khoảng trống này.

## 7. Bao phủ toàn bộ vòng đời của tệp

### 7.1. Tệp tạm cũng có dữ liệu thật

Một luồng upload có thể đi qua:

```text
Nhận dữ liệu
    → vùng tạm có bảo vệ
    → vùng chờ xử lý/kiểm tra
    → vùng lưu riêng được quản lý
    → phát hành qua cơ chế kiểm soát quyền
    → hết hạn/xóa theo chính sách
```

Không được tạo tệp trong thư mục public rồi di chuyển ra ngoài sau. Khoảng thời gian ngắn vẫn là cửa sổ truy cập, nhất là khi tên hoặc URL đã biết.

Cần xác định cả vùng tạm của thư viện, framework, worker và hệ điều hành theo cấu hình triển khai. Việc ứng dụng tự chọn thư mục đích an toàn chưa chứng minh mọi giai đoạn trước đó cũng ở ngoài vùng phục vụ.

### 7.2. Bản dẫn xuất phải giữ chính sách

Thumbnail, preview, kết quả OCR, bản nén và export có thể tiết lộ toàn bộ hoặc một phần dữ liệu gốc.

Một yêu cầu hợp lý là mỗi bản dẫn xuất được liên kết với tài nguyên và chính sách phù hợp, không tự hạ xuống public chỉ vì là ảnh nhỏ hoặc tệp trung gian.

Nếu có chức năng chủ động công khai tài liệu, cần một quyết định phát hành riêng, đúng quyền và phiên bản. Không dùng việc tạo preview như một bước công khai ngầm.

### 7.3. Cleanup và dung lượng

Vùng riêng vẫn có thể làm đầy đĩa hoặc storage. Cần giới hạn kích thước, số lượng, tổng dung lượng, tuổi tệp tạm và công việc xử lý theo phạm vi đã chọn.

Cleanup chỉ được xóa tài nguyên do hệ thống quản lý và theo chính sách. Không dùng đường dẫn do client gửi để xác định tập xóa.

Nếu storage dùng chung giữa nhiều tenant hoặc nhiều resource, phải kiểm tra tham chiếu và quyền trước khi xóa. Một bản nội dung được dùng chung nội bộ không làm quyền đọc hoặc quyền xóa của các resource trở thành giống nhau.

### 7.4. Backup, di chuyển và restore

Bản sao lưu, dữ liệu di chuyển và kết quả restore cũng phải không bị đưa vào một vùng có ánh xạ public ngoài chính sách.

Sau restore, cần kiểm tra policy, mapping, metadata quyền và phiên bản trước khi mở tải xuống. Một bucket được tạo lại với cấu hình mặc định khác có thể làm mất ranh giới dù nội dung phục hồi đúng.

Xóa tài liệu khỏi nguồn không tự xóa bản sao, cache hoặc tệp đã được người dùng tải về. Yêu cầu retention và xử lý dữ liệu phải phân biệt các phạm vi này.

## 8. Đường phân phối nội dung có kiểm soát

### 8.1. Ứng dụng stream tệp

Ứng dụng có thể kiểm tra quyền rồi đọc và stream tệp. Cần giới hạn tài nguyên như số download đồng thời, thời lượng, băng thông hoặc kích thước theo rủi ro.

Không đọc mọi tệp lớn vào bộ nhớ chỉ để tránh phục vụ static. Cách phân phối phải đáp ứng cả bảo mật và tính sẵn sàng.

Yêu cầu quan trọng là quyền đọc đã được đánh giá cho tài nguyên và phiên bản thực tế được trả, không phải chỉ có một endpoint đăng nhập ở phía trước.

### 8.2. Chuyển giao nội bộ sau phân quyền

Một số kiến trúc cho phép ứng dụng phê duyệt rồi giao việc truyền tệp cho web server bằng một cơ chế nội bộ.

Cơ chế đó cần bảo đảm:

- Client không thể gọi trực tiếp đường nội bộ để bỏ qua ứng dụng.
- Chỉ thành phần được tin cậy tạo chỉ dẫn chuyển giao.
- Client không tự chọn đường đích, header hoặc storage reference có quyền.
- Resource được chuyển giao khớp tài nguyên đã kiểm tra.
- Cấu hình không biến vùng nội bộ thành alias public.

Không thể kết luận an toàn chỉ vì API chính trả một header. Phải kiểm thử đường truy cập bên ngoài và quyền điều khiển chỉ dẫn đó.

### 8.3. URL có quyền truy cập tạm thời

Một URL được cấp quyền tạm thời có thể được dùng trong kiến trúc đã phê duyệt. Nó thường mang khả năng truy cập cho người giữ URL trong phạm vi điều kiện được cấp.

Cần đặc tả đối tượng, phiên bản, phương thức, thời hạn, khả năng chia sẻ, khả năng thu hồi và nơi có thể ghi lại URL. TTL ngắn giảm cửa sổ sử dụng nhưng không bảo đảm thu hồi tức thời.

Ví dụ, nếu yêu cầu là mọi request mới sau khi quyền bị thu hồi phải bị từ chối ngay theo điểm quyết định, một URL còn dùng được 5 phút mà không kiểm tra lại quyền có thể không đáp ứng yêu cầu đó.

Trong ví dụ cổng hồ sơ của bài, đường mặc định là tải qua kiểm tra quyền. Nếu bổ sung URL tạm thời, cần một quyết định kiến trúc và tiêu chí nghiệm thu riêng, không coi đó là chi tiết triển khai không ảnh hưởng bảo mật.

### 8.4. HEAD, Range và đường preview

Kiểm tra quyền phải bao phủ các phương thức và biến thể có thể trả nội dung hoặc metadata nhạy cảm, gồm HEAD, tải từng phần, preview và các bản chuyển đổi.

Không chỉ bảo vệ GET đầy đủ trong khi một đường khác trả kích thước, nội dung một phần hoặc bản preview cho người không có quyền.

Tương tự, một phản hồi xác nhận cache hoặc metadata không nên tiết lộ sự tồn tại của tài nguyên ngoài chính sách lỗi đã chọn.

## 9. Header, hiển thị và cache

### 9.1. Kiểm soát cách trả nội dung

Đối với tệp tải xuống, máy chủ cần chọn content type và cách phân phối theo chính sách. Tên do người dùng đặt không phải nguồn đáng tin để tạo header thô.

Một phản hồi minh họa cho tệp tải về có thể gồm:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="document.pdf"
Cache-Control: private, no-store
```

Đây là ví dụ cho một trường hợp tải riêng tư, không phải cấu hình duy nhất cho mọi loại tài liệu. Tên tệp thực tế phải được mã hóa và xử lý bằng cơ chế phù hợp của nền tảng, tránh ký tự điều khiển hoặc cấu trúc làm thay đổi header.

Yêu cầu tải dạng attachment giúp kiểm soát trải nghiệm và giảm một số rủi ro hiển thị ngoài ý định, nhưng không thay thế phân quyền hoặc thiết kế cô lập nội dung chủ động.

Nếu cho preview trong trình duyệt, cần đánh giá riêng loại nội dung, origin, cookie, khả năng chạy nội dung và quyền truy cập. Không tự bật inline cho mọi upload dựa vào phần mở rộng.

### 9.2. Cache có thể đi vòng kiểm tra quyền

Nếu một cache dùng chung lưu response theo URL mà bỏ qua ngữ cảnh phân quyền, người dùng khác có thể nhận dữ liệu mà origin không được gọi lại.

Cần chỉ rõ:

- Nội dung riêng tư có được cache ở các lớp nào.
- Cache key và phạm vi chia sẻ có phù hợp với quyền không.
- Khi quyền đổi hoặc tài liệu bị thu hồi, cơ chế ngừng phân phối hoạt động thế nào.
- Bản đã cache trước khi đổi policy được xử lý ra sao.
- Download qua origin và qua CDN có cùng mức bảo vệ không.

Thêm một header hôm nay không tự xóa các bản đã được cache trước đó. Việc sửa cấu hình cần bao gồm kiểm tra và xử lý nội dung còn tồn tại theo cơ chế nền tảng.

### 9.3. Phạm vi của thu hồi quyền

Một chính sách có thể yêu cầu mỗi request tải mới đều kiểm tra quyền hiện hành. Cần nói rõ với luồng tải đã được chấp nhận trước lúc thu hồi: tiếp tục hay ngắt theo khả năng và rủi ro.

Không hứa rằng thu hồi quyền sẽ xóa dữ liệu đã tải về thiết bị người dùng. Điều đó nằm ngoài bảo đảm của việc lưu ngoài web root.

## 10. Object storage, CDN và origin

### 10.1. Không dựa vào tên private

Đối với object storage, phải kiểm tra quyền hiệu lực của bucket/container và object, không chỉ tên prefix.

Các đường cần xét gồm endpoint đọc object, endpoint phục vụ website nếu có, CDN, origin trực tiếp, URL tạm thời và công cụ chia sẻ. Chặn liệt kê object không tự chặn đọc khi biết đúng key.

Ứng dụng cần dùng danh tính có quyền tối thiểu. Quyền upload không mặc nhiên cần quyền sửa policy hoặc làm object công khai; quyền đọc phục vụ một chức năng cũng không mặc nhiên cần đọc mọi bucket.

### 10.2. CDN phải có cơ chế truy cập origin phù hợp

Một CDN được bảo vệ không giải quyết rò rỉ nếu client vẫn đọc được object gốc trực tiếp. Ngược lại, một origin riêng vẫn có thể bị public qua rule phân phối CDN quá rộng.

Kiến trúc phải bảo vệ cả hai hướng: ai được lấy dữ liệu từ origin và ai được nhận nội dung từ lớp phân phối. Các ràng buộc phải phù hợp với cơ chế của nền tảng được chọn.

### 10.3. Cấu hình là một phần của ranh giới bảo mật

Cần quản lý thay đổi alias, static route, bucket policy, quyền danh tính và CDN rule. Một thay đổi thuận tiện cho debug có thể tạo đường public mới.

Có thể kiểm tra tự động cấu hình đã biết và chạy phép thử truy cập từ bên ngoài. Phân tích cấu hình và kiểm thử hành vi bổ sung cho nhau; chỉ một trong hai có thể bỏ sót triển khai khác với dự kiến.

Không dùng đường kiểm tra đặc quyền nội bộ để kết luận rằng client công khai đã bị chặn. Các nhóm quyền và đường mạng phải đúng với mô hình đe dọa.

## 11. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây áp dụng cho tài liệu riêng tư của cổng hồ sơ. Yêu cầu filesystem hoặc object storage được áp dụng theo backend thực tế; không mặc định một kiến trúc phải dùng cả hai.

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| OWR-01 | Phải có danh mục vùng public, vùng riêng và mọi ánh xạ HTTP/CDN/origin có thể phục vụ chúng; tài liệu riêng không được nằm trong vùng được phục vụ static ngoài chính sách. | Nền tảng/chủ dịch vụ | Đối chiếu cấu hình hiệu lực, mount và route; có phép thử từ các điểm vào thực tế. |
| OWR-02 | Tệp riêng tư phải được lưu ngoài web root và không có alias, static route hoặc đường public tương đương tới vùng đó. | Nền tảng | Dùng fixture riêng tư có nội dung nhận diện; truy cập trực tiếp qua từng đường đã kiểm kê không trả nội dung ngoài cơ chế được duyệt. |
| OWR-03 | Mọi giai đoạn tạm, chờ kiểm tra, bản dẫn xuất và export phải giữ cùng mức bảo vệ phù hợp phân loại; không tạo bản public tạm rồi di chuyển sau. | Ứng dụng/worker | Quan sát vị trí và quyền trong suốt luồng, gồm lỗi và hủy; preview/export không có đường rò rỉ riêng. |
| OWR-04 | API nhận resource ID và tự ánh xạ tới storage reference; client không được tự chọn vị trí đọc hoặc trường hệ thống quyết định nơi lưu. | Ứng dụng | Sửa path, key, storage reference và tên gốc không cho đọc/ghi tài nguyên ngoài phạm vi. |
| OWR-05 | Mỗi request tải mới phải xác thực và phân quyền với đúng tenant, tài nguyên, hồ sơ cha và trạng thái hiện hành tại điểm quyết định đã đặc tả. | Bảo mật/ứng dụng | Chủ thể được phép tải đúng nội dung; người ngoài tenant, người bị thu hồi và tài nguyên chưa phát hành bị chặn theo chính sách. |
| OWR-06 | Phiên bản nội dung được phát phải khớp phiên bản được phép; thay nội dung không được giữ nguyên hiệu lực phát hành ngoài quy trình. | Ứng dụng/storage | Đổi object hoặc phiên bản sau kiểm tra không làm nội dung mới tự được tải; kiểm tra race khi ánh xạ và mở. |
| OWR-07 | Quyền filesystem hoặc policy storage phải theo vai trò tối thiểu; luồng upload không được sửa mã, cấu hình phục vụ hoặc làm tài nguyên riêng thành public. | Nền tảng/bảo mật | Thử quyền bằng từng danh tính thật; thay mapping/policy phải qua quyền và dấu vết được kiểm soát. |
| OWR-08 | Cơ chế mở tài nguyên phải bảo vệ ranh giới backend trước đường dẫn thoát vùng, liên kết và thay đổi cạnh tranh theo nền tảng áp dụng. | Ứng dụng/nền tảng | Test đường dẫn đặc biệt, liên kết ngoài vùng và thay đổi trung gian; không đọc được dữ liệu ngoài tập được quản lý. |
| OWR-09 | HEAD, Range, preview, tải dẫn xuất và chuyển giao nội bộ phải giữ kiểm soát tương đương đường tải chính; client không tự kích hoạt đường nội bộ. | Ứng dụng/nền tảng | Test từng biến thể và thử gọi trực tiếp đường nội bộ; không trả nội dung hoặc metadata trái chính sách. |
| OWR-10 | Phân phối và cache phải tương thích với phân loại và yêu cầu thu hồi; tên tệp không được tạo header thô, thông báo lỗi không lộ vị trí nhạy cảm. | Chủ API/nền tảng | Kiểm tra header, nội dung, cache chia sẻ, quyền bị đổi và phản hồi lỗi; không lộ dữ liệu cho chủ thể khác. |
| OWR-11 | Với object storage/CDN, object gốc và đường phân phối phải có policy được duyệt; chặn listing không được coi là đủ nếu GET theo key còn công khai. | Nền tảng | Test endpoint object, website, CDN và origin theo kiến trúc; danh tính không có quyền không lấy được fixture. |
| OWR-12 | Phải truy vết quyết định truy cập và thay đổi ranh giới phục vụ; log không được chứa credential hoặc URL có quyền truy cập ngoài chính sách. | Vận hành/bảo mật | Audit liên kết actor, tenant, resource, kết quả và thay đổi cấu hình; kiểm tra log không chứa bí mật truy cập. |
| OWR-13 | Vùng tạm và vùng riêng phải có quota, tuổi lưu, cleanup và cảnh báo dung lượng theo ngân sách được phê duyệt. | Chủ dịch vụ/vận hành | Tải thử tới ngưỡng; hệ thống từ chối hoặc giảm tải đúng, cleanup không xóa tài nguyên ngoài phạm vi. |
| OWR-14 | Thay cấu hình phục vụ, migrate storage hoặc restore phải kiểm tra lại khả năng truy cập public, quyền và trạng thái phát hành trước khi mở dịch vụ. | Chủ dịch vụ | Có bằng chứng kiểm tra sau thay đổi; fixture không trở thành public do policy/mapping mặc định mới. |

OWR-02 cần được đọc cùng OWR-05: không có đường static public không đồng nghĩa endpoint ứng dụng đã kiểm tra quyền đúng. Cả ranh giới phân phối và quyết định quyền đều phải đạt.

Nếu hệ thống chủ động dùng URL tạm thời hoặc phát hành tài liệu công khai, cần phân loại và chính sách riêng. Không đánh dấu mọi đường trực tiếp là lỗi khi đó là cơ chế được phê duyệt, nhưng phải chứng minh phạm vi, thời hạn và quyền cấp khả năng truy cập đó.

### 11.1. Mẫu đặc tả chi tiết

```text
ID: OWR-02
Mục tiêu: không bỏ qua phân quyền bằng URL static hoặc origin public
Rủi ro: R-FILE-02 — tài liệu riêng được phục vụ ngoài đường kiểm soát
Phạm vi:
  - Nội dung gốc, tệp tạm, preview và export thuộc phân loại private
  - Các điểm vào HTTP, static middleware, proxy, CDN/origin đã kiểm kê
Điều kiện:
  - Nằm ngoài vùng phục vụ public ở backend tương ứng
  - Không có mapping khác mở lại cùng dữ liệu
  - Không có public object policy ngoài cơ chế được phê duyệt
Nghiệm thu:
  - Dùng fixture tồn tại, có marker nội dung và metadata đã biết
  - Thử anonymous, người có phiên nhưng không có quyền và tenant khác
  - Kiểm tra cả URL dự kiến lẫn các đường ánh xạ hiệu lực
  - Không trả nội dung/metadata nhạy cảm ngoài chính sách
Chủ sở hữu: đội nền tảng, phối hợp đội ứng dụng và bảo mật
Kiểm thử: T-OWR-01, T-OWR-02, T-OWR-08
Bằng chứng: cấu hình hiệu lực, kết quả HTTP và đối chiếu fixture
```

Đặc tả dự án phải thay tên vai trò chung bằng đầu mối cụ thể, và có danh sách điểm vào đủ để kiểm tra. Câu “mọi URL đều an toàn” không thể được nghiệm thu nếu chưa biết những đường phục vụ nào tồn tại.

## 12. Ma trận kiểm thử nghiệm thu

Thử trong môi trường kiểm soát với tệp tổng hợp, không dùng tài liệu thật chỉ để chứng minh public access. Fixture cần đủ rõ để phân biệt nội dung tệp với trang đăng nhập, trang lỗi hoặc trang ứng dụng mặc định.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-OWR-01 | Tạo fixture riêng tư và thử đọc trực tiếp theo các mapping static/web root đã kiểm kê. | Không nhận nội dung fixture ngoài đường được phê duyệt, dù biết đúng tên hoặc vị trí suy đoán. | OWR-01, 02 |
| T-OWR-02 | Kiểm tra cấu hình có alias/static middleware/mount trỏ vào vùng riêng; ở bài thử có kiểm soát, tạo một mapping sai để xác minh cơ chế phát hiện. | Cấu hình và phép thử hành vi phát hiện đường public; không chỉ dựa vào vị trí thư mục. | OWR-01, 02, 14 |
| T-OWR-03 | Tải qua API bằng người được phép, anonymous, tenant khác, người không có quyền và người vừa bị thu hồi quyền. | Chỉ chủ thể đúng quyền theo điểm quyết định nhận nội dung; chính sách lỗi không lộ tài nguyên ngoài phạm vi. | OWR-04, 05 |
| T-OWR-04 | Sửa resource ID, path, object key, tên tệp, storage reference và các thành phần đường dẫn theo nền tảng. | Không chọn được tệp ngoài metadata được phép; không đọc/ghi vượt ranh giới. | OWR-04, 08 |
| T-OWR-05 | Tạo liên kết hoặc thay đổi đường dẫn trung gian trong điều kiện race mà mô hình quyền cho phép thử. | Cơ chế mở tài nguyên không thoát vùng hoặc trả sai tài nguyên; quyền không cho phép tạo liên kết trái chính sách. | OWR-06, 07, 08 |
| T-OWR-06 | Theo dõi upload đang chạy, thất bại, bị hủy; tạo preview và export. | Tất cả bản tạm/dẫn xuất giữ bảo vệ; không có cửa sổ xuất hiện trong vùng public. | OWR-03, 13 |
| T-OWR-07 | Đổi nội dung/object version sau khi được phép phát hành rồi yêu cầu tải. | Không trả nội dung mới bằng quyết định cũ trái chính sách; phiên bản thực tế khớp kiểm tra. | OWR-05, 06 |
| T-OWR-08 | Với object storage/CDN, thử GET theo key đã biết, listing, origin trực tiếp, endpoint website và đường CDN. | Không có đường public ngoài chính sách; deny listing không che việc GET còn mở. | OWR-02, 11 |
| T-OWR-09 | Thử HEAD, tải từng phần, preview, tài liệu dẫn xuất và gọi trực tiếp đường chuyển giao nội bộ. | Mọi biến thể đều giữ kiểm soát; client không tự chọn được đích nội bộ. | OWR-09 |
| T-OWR-10 | Tải khi có quyền, đổi quyền rồi thử request mới từ chủ cũ và người khác; kiểm tra qua cache/CDN. | Hành vi theo yêu cầu thu hồi và cache đã công bố; không dùng response của người này cho người khác. | OWR-05, 10 |
| T-OWR-11 | Dùng tên tệp chứa ký tự cần xử lý; gây lỗi backend; kiểm tra audit và log. | Header được tạo an toàn; không lộ path/credential/URL có quyền ngoài chính sách; audit đủ đối chiếu. | OWR-10, 12 |
| T-OWR-12 | Đưa lưu trữ hoặc vùng tạm tới quota, chạy cleanup và thử nhiều tenant. | Không cạn tài nguyên ngoài ngân sách; cleanup chỉ tác động tài nguyên đúng phạm vi và chính sách. | OWR-13 |
| T-OWR-13 | Restore hoặc migrate sang môi trường có cấu hình phục vụ khác, rồi chạy kiểm tra trước mở lưu lượng. | Mapping/policy/quyền được xác minh; dữ liệu riêng không vô tình trở thành public. | OWR-14 |

Nếu dùng URL có quyền tạm thời, bổ sung test hết hạn, sai resource/version, chia sẻ ngoài phạm vi dự kiến và thu hồi theo đúng bảo đảm được công bố. Không suy luận kết quả của luồng API proxy sẽ áp dụng cho luồng URL đó.

### 12.1. Bằng chứng nào là chưa đủ?

- Thư mục gốc trả 403 trong khi tệp cụ thể vẫn tải được.
- Một URL trả 404 nhưng một alias hoặc origin khác trả nội dung.
- Không có directory listing nhưng GET theo key vẫn công khai.
- Người không đăng nhập bị chặn trong API nhưng đường static vẫn mở.
- Filename khó đoán nhưng URL đã lộ vẫn dùng được.
- Tệp gốc riêng tư nhưng preview hoặc bản export được cache công khai.
- Cấu hình nguồn đúng nhưng cấu hình đang chạy khác với dự kiến.

Cần đối chiếu nội dung, metadata và đường phục vụ thực tế. HTTP 200 có thể chỉ là trang ứng dụng mặc định; HTTP 403/404 ở một đường cũng không chứng minh các đường còn lại đã bị chặn.

### 12.2. Ghi lại phạm vi kiểm thử

Báo cáo nên gồm phiên bản ứng dụng, cấu hình hiệu lực, danh sách route/origin, backend, danh tính thử, fixture, request, phản hồi và đối chiếu nội dung.

Không cần đưa tài liệu thật, credential hoặc URL còn quyền vào báo cáo. Sử dụng dữ liệu tổng hợp và che thông tin truy cập có thể tái sử dụng.

## 13. Truy vết trong vòng đời phát triển

Chuỗi truy vết tối thiểu:

```text
Mục tiêu bảo mật dữ liệu
    → Đường truy cập có thể bỏ qua kiểm soát
    → Yêu cầu OWR-xx
    → Vùng lưu, mapping, quyền và cơ chế tải
    → Test T-OWR-xx
    → Audit, kiểm tra thay đổi và phục hồi
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Không lộ tài liệu qua static | Tệp private có mapping public | OWR-01, 02 | Vùng riêng và danh mục mapping; T-OWR-01, 02 |
| Giữ ranh giới tenant | Đổi ID hoặc storage reference | OWR-04, 05 | Metadata có thẩm quyền và phân quyền tài nguyên; T-OWR-03, 04 |
| Không lộ qua bản trung gian | Tệp tạm/preview/export public | OWR-03 | Vòng đời tệp có bảo vệ; T-OWR-06 |
| Phát đúng nội dung đã được phép | Object bị thay sau kiểm tra | OWR-06 | Ràng buộc phiên bản; T-OWR-07 |
| Không đi vòng qua CDN/origin | Lớp phân phối đúng nhưng origin công khai | OWR-10, 11 | Policy origin và cache; T-OWR-08, 10 |
| Không mất ranh giới sau thay đổi | Mapping hoặc policy mới khác mặc định | OWR-14 | Kiểm tra sau deploy/migrate/restore; T-OWR-13 |

Khi thêm preview, thay nơi lưu tệp tạm, bật CDN, đổi framework phục vụ static hoặc thêm volume mount, cần đánh giá lại phạm vi.

Quyền thay cấu hình cũng là một phần của thiết kế. Nếu mọi worker có thể sửa policy hoặc ghi tệp vào web root, ranh giới khó duy trì lâu dài dù cấu hình ban đầu đúng.

Ngoại lệ phải có phân loại dữ liệu, phạm vi, thời hạn, rủi ro còn lại, biện pháp bù và người phê duyệt. Một đường debug không được mặc nhiên bỏ qua chính sách tài liệu riêng tư.

## 14. Những lỗi đặc tả thường gặp

| Cách viết hoặc triển khai | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Đổi tên uploads thành private.” | Tên không thay mapping hoặc policy | Kiểm tra vùng phục vụ và quyền hiệu lực |
| “Nằm ngoài document root là an toàn.” | Alias hoặc server khác có thể mở lại | Kiểm kê mọi điểm vào và test nội dung thực tế |
| “Tên ngẫu nhiên nên không ai tải được.” | URL có thể bị lộ hoặc chia sẻ | Phân quyền hoặc khả năng truy cập được cấp có điều kiện |
| “API có đăng nhập là đủ.” | Đường static/origin có thể bỏ qua API | Bảo vệ cả đường gián tiếp và trực tiếp |
| “Không listing là private.” | Biết key vẫn có thể GET | Kiểm tra quyền đọc object cụ thể |
| “Move ra ngoài sau khi upload xong.” | Có cửa sổ tồn tại trong vùng public | Chọn vùng tạm được bảo vệ từ đầu |
| “Preview ít dữ liệu nên public được.” | Có thể lộ nội dung hoặc metadata nhạy cảm | Giữ phân loại và quyền phù hợp với tài nguyên gốc |
| “Chỉ GET cần phân quyền.” | HEAD, Range hoặc biến thể khác vẫn có thể lộ | Áp kiểm soát trên mọi đường phân phối |
| “Thêm no-store là xóa mọi cache.” | Bản cũ có thể còn tồn tại | Có kế hoạch cache và xử lý thay đổi rõ ràng |
| “Mount không execute là đủ.” | Ứng dụng vẫn có thể đọc rồi diễn giải như mã | Không đưa nội dung người dùng vào luồng thực thi |
| “Ứng dụng tự gửi path, vậy là đáng tin.” | Path có thể bắt nguồn từ client hoặc metadata bị sửa | Storage reference do máy chủ quản lý và quyền ghi được kiểm soát |
| “Restore dữ liệu xong là mở dịch vụ.” | Policy hoặc mapping mới có thể khác | Kiểm tra lại ranh giới và quyền trước mở lưu lượng |

## 15. Bài tập áp dụng

Một nền tảng nhận tài liệu ứng tuyển. Tệp gốc nằm trong thư mục upload của ứng dụng, preview được tạo vào thư mục static, và export được đặt trong bucket có thể đọc bằng URL. API hồ sơ có kiểm tra quyền nhưng các URL tệp được gửi thẳng cho trình duyệt.

Hãy thực hiện:

1. Liệt kê các đường có thể đọc nội dung mà không qua quyết định quyền của hồ sơ.
2. Xác định vùng public, vùng riêng, vùng tạm và các bản dẫn xuất.
3. Đề xuất kiến trúc resource ID → metadata → phân quyền → storage reference → phân phối.
4. Viết sáu yêu cầu có ID, phạm vi, điều kiện đạt, chủ sở hữu và bằng chứng nghiệm thu.
5. Thiết kế test cho alias public, tenant khác, preview, cache, origin và restore.
6. Giải thích khác biệt giữa tên object khó đoán và cơ chế truy cập được phân quyền.
7. Nếu dùng URL tạm thời, nêu phạm vi, thời hạn, khả năng chia sẻ và giới hạn thu hồi.
8. Chỉ ra các kiểm soát bổ sung cần để tệp người dùng không trở thành mã hoặc nội dung được xử lý trái chính sách.

Đáp án tốt phải chứng minh tài liệu không có đường phục vụ ngoài chính sách trong suốt vòng đời, đồng thời giữ quyền tài nguyên và cách phân phối phù hợp.

## 16. Checklist chấp nhận yêu cầu

- Đã phân biệt web root, project root và các mapping khác chưa?
- Có danh mục đầy đủ static route, alias, CDN và origin không?
- Dữ liệu riêng có nằm ngoài mọi vùng phục vụ public ngoài chính sách không?
- Tệp tạm, quarantine, preview và export có cùng mức bảo vệ phù hợp không?
- Client có bị ngăn chọn path hoặc storage reference có quyền không?
- Mỗi request mới có kiểm tra tenant, tài nguyên, trạng thái và quyền hiện hành không?
- Nội dung thực tế có khớp phiên bản đã được phép không?
- Quyền ghi có ngăn upload sửa mã, cấu hình hoặc policy phục vụ không?
- Cơ chế mở tệp có bảo vệ ranh giới và race theo nền tảng không?
- HEAD, Range, preview và chuyển giao nội bộ có được kiểm soát không?
- Cache và URL tạm thời có tương thích với bảo đảm thu hồi được công bố không?
- Object storage có được kiểm tra GET theo key, không chỉ listing không?
- Audit, quota, cleanup và retention có được đặc tả không?
- Sau migrate hoặc restore có kiểm tra lại ranh giới trước khi mở dịch vụ không?
- Test có đối chiếu nội dung fixture thực tế qua mọi đường đã kiểm kê không?

Lưu ngoài web root có giá trị bảo mật khi vị trí dữ liệu, ánh xạ phục vụ và quyền truy cập cùng tạo thành một ranh giới có thể kiểm chứng, được giữ nhất quán từ lúc tạo tệp đến khi phân phối và kết thúc vòng đời.
