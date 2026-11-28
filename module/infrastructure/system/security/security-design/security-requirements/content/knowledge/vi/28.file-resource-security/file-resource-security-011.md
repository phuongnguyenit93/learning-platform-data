# Download authorization — Đặc tả yêu cầu phân quyền tải xuống tài nguyên

## 1. Mục tiêu là kiểm soát ai được nhận nội dung nào

Download authorization là quyết định cho phép hoặc từ chối một chủ thể nhận nội dung tài nguyên trong một ngữ cảnh cụ thể. Quyết định đó có thể phụ thuộc vào danh tính, tenant, quyền với hồ sơ cha, phân loại dữ liệu, trạng thái tài liệu, phiên bản nội dung và hiệu lực của một quyền truy cập tạm thời.

Một endpoint yêu cầu đăng nhập chưa chứng minh đã phân quyền đúng. Một người đăng nhập hợp lệ vẫn có thể không được đọc hồ sơ của người khác. Tương tự, tệp được lưu ở nơi riêng tư vẫn có thể bị ứng dụng trả cho sai chủ thể.

Trong module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, mục tiêu là chuyển yêu cầu “chỉ người được phép mới tải tài liệu” thành những điều kiểm chứng được:

- Chủ thể nào được đọc tài nguyên, thông qua quan hệ quyền nào?
- Quyền được kiểm tra với phiên bản và trạng thái nào?
- Các đường GET, HEAD, tải từng phần, preview và export có cùng ranh giới không?
- Khi quyền thay đổi, sau bao lâu request mới phải bị chặn?
- URL tạm thời, cache và CDN có giữ đúng bảo đảm đó không?
- Audit nào chứng minh quyết định và nội dung thực tế đã được phân phối?

Bài học dùng ví dụ cổng hồ sơ nhiều tenant. Tài liệu là riêng tư, người dùng chỉ được tải khi còn quyền đọc hồ sơ và tài liệu đã được phép phát hành. Các ngưỡng trong bài là giả định thiết kế, không phải tiêu chuẩn áp dụng mặc định.

## 2. Phân biệt xác thực, phân quyền và khả năng truy cập

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Người gọi là ai? | Phiên đăng nhập thuộc user-37 |
| Authorization | Người đó có quyền thực hiện thao tác này trên tài nguyên này không? | User-37 được đọc tài liệu trong hồ sơ case-915 |
| Trạng thái phát hành | Tài nguyên có được cung cấp trong trạng thái hiện tại không? | Phiên bản 4 đã được phép tải, không còn trong vùng cách ly |
| Storage access | Thành phần kỹ thuật có đọc được nội dung không? | File service có quyền đọc object riêng |
| Delegated access | Có một khả năng truy cập được cấp với phạm vi nào? | Một URL tạm thời cho đúng object/version và thời hạn |
| Distribution control | Nội dung đi qua cache, CDN hoặc đường dẫn nào? | Cache không dùng response riêng tư của người này cho người khác |

Quyền đọc bucket của service account không có nghĩa mọi người dùng của ứng dụng được đọc mọi object. Đó là quyền kỹ thuật để phục vụ nghiệp vụ, còn ứng dụng vẫn phải quyết định ai được nhận nội dung.

Một URL khó đoán hoặc resource ID dài cũng không thay thế phân quyền. URL có thể bị chia sẻ, ghi log hoặc xuất hiện trong lịch sử trình duyệt.

## 3. Ví dụ xuyên suốt: tải tài liệu trong hồ sơ

Giả sử một tài liệu có metadata phía máy chủ:

```json
{
  "resource_id": "doc-482",
  "tenant_id": "tenant-07",
  "parent_record_id": "case-915",
  "content_version": "v4",
  "storage_reference": "private-object-86",
  "classification": "confidential",
  "release_state": "RELEASED",
  "policy_revision": 19
}
```

Ngữ cảnh người dùng có:

```json
{
  "principal_id": "user-37",
  "acting_service": "portal-api",
  "verified_tenant_id": "tenant-07",
  "session_id": "session-62",
  "authentication_context": "interactive-session"
}
```

Các dữ kiện trong ngữ cảnh phải đến từ xác thực và quan hệ tenant đã được kiểm chứng. Không dùng một header do client tùy ý khai báo để xác định họ thuộc tenant nào.

### 3.1. Chính sách minh họa

Một request tải được phép khi đồng thời thỏa mãn:

1. Chủ thể và phiên đáp ứng chính sách xác thực.
2. Tài nguyên thuộc tenant mà chủ thể đang được phép sử dụng.
3. Chủ thể có quyền đọc nội dung của hồ sơ cha.
4. Các điều kiện riêng của tài liệu và phân loại dữ liệu được đáp ứng.
5. Phiên bản được yêu cầu đang ở trạng thái RELEASED và chưa bị thu hồi.
6. Không có điều kiện từ chối có hiệu lực theo chính sách đã chọn.
7. Đường phân phối giữ được các ràng buộc của quyết định.

Quan hệ giữa quyền kế thừa, quyền riêng trên tài liệu và điều kiện từ chối phải được đặc tả. Không mặc định mọi mô hình đều có cùng quy tắc ưu tiên.

Trong ví dụ này, một quyền từ chối có hiệu lực ngăn tải ngay cả khi chủ thể có quyền đọc hồ sơ cha. Đây là lựa chọn chính sách của ví dụ, cần được triển khai nhất quán.

### 3.2. Người tạo tệp không mặc nhiên có quyền mãi mãi

Người từng upload hoặc tạo export có thể đã rời hồ sơ, đổi tenant, bị khóa hoặc bị thu hồi quyền. Quyền tạo tài nguyên trước đây không tự trở thành quyền tải vĩnh viễn.

Tương tự, người có vai trò quản trị một phần hệ thống không mặc nhiên có quyền đọc mọi nội dung. Quyền quản trị vận hành và quyền truy cập dữ liệu cần được xác định theo nhiệm vụ.

## 4. Mô hình đe dọa và yêu cầu tương ứng

| Kịch bản | Rủi ro | Hướng yêu cầu |
| --- | --- | --- |
| Người dùng đổi resource ID trong URL | Đọc tài liệu của người hoặc tenant khác | Kiểm tra quyền trên đối tượng cụ thể, không chỉ trên endpoint |
| Client gửi tenant hoặc owner tùy ý | Bẻ ngữ cảnh quyết định | Tenant và chủ thể lấy từ nguồn có thẩm quyền |
| Tài liệu chưa phát hành vẫn có đường tải | Lộ dữ liệu chờ kiểm tra hoặc bị thu hồi | Kiểm tra trạng thái và phiên bản nội dung |
| URL được cấp trước lúc thu hồi quyền | Tiếp tục tải sau thời hạn thu hồi cho phép | Định nghĩa và kiểm thử độ trễ hiệu lực quyền |
| Cache trả nội dung theo URL chung | Người khác nhận response đã được cấp cho chủ thể trước | Chính sách cache tương thích với ngữ cảnh phân quyền |
| Origin hoặc static route còn công khai | Đi vòng API có kiểm tra quyền | Bảo vệ mọi đường phân phối, không chỉ route ứng dụng |
| HEAD hoặc Range không kiểm tra quyền | Lộ metadata hoặc một phần nội dung | Áp chính sách lên mọi biến thể tải |
| Worker dùng quyền kỹ thuật rộng | Export dữ liệu ngoài quyền người yêu cầu | Phân biệt danh tính service và quyền đại diện chủ thể |
| Một phần tử trong ZIP không thuộc quyền | Rò rỉ qua tải nhóm | Kiểm tra từng tài nguyên và quyền tải artifact tổng hợp |
| Chỉ kiểm tra tên hoặc ID trước khi object đổi | Phát nội dung khác nội dung đã được cho phép | Quyết định ràng buộc với phiên bản thực tế |
| Policy service lỗi, ứng dụng dùng cache quá cũ | Tiếp tục tải bằng quyền không còn được tin cậy | Quy định độ mới và hành vi khi không đủ bằng chứng |
| Log chứa URL mang quyền truy cập | Người đọc log có thể tải tài liệu | Không ghi bí mật truy cập hoặc URL còn quyền ngoài chính sách |

Bất biến chính có thể diễn đạt như sau:

> Nội dung được phân phối phải thuộc đúng tài nguyên và phiên bản mà một quyết định hợp lệ đã cho phép chủ thể hoặc khả năng truy cập được cấp nhận, theo bảo đảm về hiệu lực quyền của hệ thống.

Bất biến này phải bao phủ cả kênh ứng dụng và kênh được ủy quyền phân phối.

## 5. Điểm thực thi quyền và nguồn sự thật

### 5.1. Luồng tải qua ứng dụng

```text
Client yêu cầu resource ID
          |
          v
Xác thực và xác định tenant đáng tin
          |
          v
Đọc metadata, quyền và trạng thái đủ mới
          |
          v
Quyết định quyền cho resource + version + operation
          |
          v
Mở đúng nội dung ở storage riêng
          |
          v
Phân phối theo chính sách + ghi dấu vết
```

Máy chủ có thể dùng một thành phần quyết định chính sách riêng hoặc kiểm tra trong ứng dụng. Điều quan trọng là quyết định có dữ kiện đủ tin cậy và điểm thực thi không bị bỏ qua.

### 5.2. Mã giả

```text
download(resource_id, request_context):
    subject = authenticate(request_context)
    tenant = resolve_verified_tenant(subject, request_context)

    resource = load_resource_in_tenant(resource_id, tenant)
    decision = authorize(
        subject = subject,
        action = "download_content",
        resource = resource,
        policy = sufficiently_current_policy()
    )

    if not decision.allowed:
        return mapped_denial_without_sensitive_metadata()

    content = open_authorized_version(
        resource.storage_reference,
        resource.content_version,
        decision.content_binding
    )

    record_decision_and_start_of_transfer(decision, content)
    return approved_delivery(content, decision)
```

Đây là mã giả, không phải một API thư viện. Việc mở nội dung cần giữ ràng buộc với tài nguyên, phiên bản và điều kiện của quyết định. Không kiểm tra quyền với một object rồi đọc một object khác từ path do client chọn.

### 5.3. Quyền ở cấp đối tượng

Kiểm tra “có role nhân viên” hoặc “đã đăng nhập” thường chưa đủ. Cần quan hệ với hồ sơ, tài liệu, tenant và thao tác.

Nếu quyền xem metadata khác quyền tải nội dung, hai quyền cần được mô hình hóa rõ. Ví dụ, một người được biết có tài liệu trong hồ sơ nhưng chưa được nhận tệp gốc.

Không trả tên tệp, kích thước, phân loại hoặc thông tin storage trước khi đạt quyền cần thiết theo chính sách. Một response không có nội dung vẫn có thể tiết lộ dữ liệu nhạy cảm.

### 5.4. Nguồn dữ liệu đủ mới

Quyền và metadata có thể đến từ DB, dịch vụ chính sách hoặc cache. Yêu cầu phải nêu mức độ mới chấp nhận được, thay vì mặc định mọi dữ liệu đọc được đều có thẩm quyền cho quyết định hiện tại.

Một replica cập nhật trễ có thể vẫn cho thấy quyền đã bị thu hồi. Nếu kiến trúc cho phép độ trễ, phải định lượng và kiểm thử độ trễ đó; không hứa hiệu lực tức thời khi dùng dữ liệu cũ.

## 6. Thu hồi quyền và hiệu lực của quyết định

### 6.1. Định nghĩa thời hạn có thể đo

Giả sử yêu cầu minh họa là:

> Sau khi quyết định thu hồi được commit tại nguồn quyền có thẩm quyền, mọi quyết định cho request tải mới phải phản ánh việc thu hồi trong không quá 60 giây, trên toàn bộ các đường phân phối thuộc phạm vi.

Yêu cầu cần xác định:

- Sự kiện nào được coi là thu hồi đã commit.
- “Request mới” được xác định ở điểm tiếp nhận hoặc quyết định nào.
- Các lớp cache, gateway, origin và CDN nào thuộc phạm vi.
- Cách đo từ thời điểm thu hồi tới lần chấp nhận cuối không còn hợp lệ.
- Hành vi khi không đo được độ mới hoặc nguồn quyền không truy cập được.

Ngưỡng 60 giây là lựa chọn của ví dụ. Dữ liệu nhạy cảm hơn có thể cần chính sách chặt hơn; dữ liệu khác có thể chấp nhận một bảo đảm khác sau đánh giá rủi ro.

### 6.2. Không nhầm thời hạn token với thời hạn thu hồi

Một token đăng nhập còn hiệu lực không có nghĩa quyền đọc mọi tài liệu vẫn còn. Một URL tải tạm thời còn dùng được cũng không mặc nhiên đáp ứng thu hồi quyền động.

Ví dụ, nếu khâu cấp URL có thể dùng quyền trễ tối đa 30 giây và URL còn hiệu lực thêm 5 phút mà nơi nhận không kiểm tra lại quyền, việc giảm TTL xuống 5 phút không đáp ứng bảo đảm thu hồi trong 60 giây.

Khi lập ngân sách, phải xét cả khoảng trễ lúc cấp và khoảng sử dụng còn lại của grant, cùng các lớp cache hoặc cơ chế phân phối có thể tiếp tục phục vụ. Không chỉ nhìn một con số TTL.

Nếu cần bảo đảm chặt, có thể phải kiểm tra quyền tại điểm sử dụng, có cơ chế thu hồi thực sự hoặc chọn một đường phân phối khác. Thiết kế phải theo khả năng nền tảng, không theo tên gọi của token.

### 6.3. Quyền đã cấp và luồng đang truyền

Một request đã được cho phép trước thu hồi có thể đang truyền một tệp lớn. Hệ thống phải chọn chính sách:

- Cho luồng đã được chấp nhận tiếp tục theo giới hạn phiên tải đã quy định.
- Hoặc kiểm tra/điều khiển luồng để ngắt theo điều kiện đã đặc tả.

Trong ví dụ, bảo đảm 60 giây áp dụng cho quyết định tải mới. Luồng đã được cho phép trước đó có thể tiếp tục theo thời hạn truyền đã được duyệt. Nếu sản phẩm cần ngắt cả luồng đang chạy, phải có yêu cầu và kiểm thử riêng.

Mỗi request Range mới là một lần yêu cầu mới theo chính sách của ví dụ; một quyết định trước đó không tạo quyền vô hạn tải thêm các đoạn sau.

Thu hồi quyền không xóa nội dung đã được người dùng tải về. Không công bố một bảo đảm vượt khỏi khả năng của cơ chế phân phối.

### 6.4. Hành vi khi thiếu bằng chứng

Nếu cache quyền quá tuổi cho phép hoặc không xác minh được trạng thái thu hồi, không được coi “không biết” là “còn quyền” cho tài liệu thuộc phạm vi cần bảo vệ.

Có thể từ chối tạm thời hoặc dùng một nguồn có thẩm quyền khác theo thiết kế. Không dựa vào role hoặc trạng thái client gửi để tiếp tục tải.

Nếu có ngoại lệ vận hành, cần phân loại tài nguyên, thời hạn, người phê duyệt và audit. Không dùng một fallback chung làm vô hiệu yêu cầu thu hồi.

## 7. URL có quyền truy cập và các hình thức ủy quyền

### 7.1. URL mang khả năng truy cập

Một URL tạm thời có thể cho phép người giữ nó tải nội dung trong những điều kiện đã cấp. Việc phát hành URL cần bắt đầu từ một quyết định quyền hợp lệ.

Các thuộc tính cần đặc tả có thể gồm:

- Đúng resource và phiên bản nội dung.
- Phương thức hoặc hành động được phép.
- Thời điểm bắt đầu, hết hạn và dung sai liên quan.
- Phạm vi đường phân phối hoặc dịch vụ nhận.
- Khả năng chia sẻ, thu hồi và sử dụng lại.
- Những dữ kiện được nơi thực thi kiểm tra thực sự.

Không nên nhúng principal ID vào token rồi kết luận chỉ principal đó dùng được. Nếu điểm nhận chỉ kiểm tra chữ ký và không xác thực người giữ, token vẫn có thể hoạt động như một khả năng truy cập cho bất kỳ ai sở hữu nó.

### 7.2. Phạm vi càng rộng, rủi ro càng lớn

Một grant cho một object/version khác với grant đọc mọi object theo prefix. Grant cho đọc nội dung không mặc nhiên được phép liệt kê, sửa hoặc xóa.

Cần tránh để client thay key, version, phương thức hoặc resource mà vẫn dùng được cùng grant. Cơ chế kiểm chứng phải ràng buộc những thuộc tính có ý nghĩa tại điểm sử dụng.

Grant khó đoán hoặc được ký không sửa được một policy cấp quyền quá rộng. Tính toàn vẹn của grant và tính đúng của quyết định cấp là hai điều cùng phải đạt.

### 7.3. URL có quyền không nên xuất hiện tùy ý

URL còn khả năng truy cập có thể bị lộ qua log, ảnh chụp màn hình, công cụ hỗ trợ, lịch sử hoặc thông tin điều hướng. Cần quản lý những nơi có thể lưu và chuyển tiếp nó.

Không ghi toàn bộ URL mang quyền vào audit chỉ để liên kết sự kiện. Có thể dùng grant ID hoặc định danh tham chiếu được thiết kế không tự cấp khả năng truy cập.

Nếu sản phẩm chủ động cho chia sẻ liên kết, cần một nghiệp vụ chia sẻ có phạm vi, quyền cấp, thời hạn và chính sách thu hồi riêng. Không coi việc copy URL là cơ chế chia sẻ ngầm không cần đặc tả.

### 7.4. Chuyển hướng và chuyển giao nội bộ

Nếu ứng dụng kiểm tra quyền rồi chuyển hướng tới origin, bước sau vẫn phải giữ ràng buộc đã quyết định. Không redirect tới một object công khai tồn tại lâu dài khi chính sách yêu cầu kiểm tra quyền động.

Nếu dùng cơ chế chuyển giao nội bộ cho web server truyền tệp, client không được gọi trực tiếp đường nội bộ hoặc tự tạo chỉ dẫn đọc tệp.

Một response chứa chỉ dẫn chuyển giao chưa chứng minh an toàn. Phải kiểm tra điểm đích và cấu hình có thực sự ngăn việc đi vòng hay không.

## 8. Cache, CDN và origin

### 8.1. Cache dùng chung có thể phá ranh giới chủ thể

Giả sử user A có quyền tải `/documents/doc-482/content`. Nếu một cache lưu response theo URL rồi trả cho user B mà không xét ràng buộc cần thiết, phân quyền ở origin không còn bảo vệ request của B.

Cần xác định nội dung nào được cache, ở lớp nào và theo điều kiện nào. “Có header Vary” hoặc “cache theo token” không tự chứng minh đáp ứng thu hồi quyền; còn phải kiểm tra cấu hình hiệu lực và vòng đời dữ liệu cache.

Không tạo cache key chứa thông tin nhạy cảm tùy ý hoặc có cardinality không kiểm soát. Với tài liệu không cần cache, có thể chọn chính sách không lưu tại các lớp liên quan và kiểm thử hành vi thực tế.

### 8.2. Phải bảo vệ cả đường origin trực tiếp

CDN có xác thực không giúp ngăn rò rỉ nếu origin vẫn cho GET công khai theo object key. Ngược lại, origin riêng cũng không ngăn CDN phát rộng cho mọi chủ thể.

Danh mục điểm thực thi phải bao gồm endpoint ứng dụng, static route, CDN, origin và các endpoint lưu trữ có liên quan. Mỗi đường hoặc phải bị chặn, hoặc thực thi đúng một cơ chế truy cập đã được phê duyệt.

### 8.3. Cache và phiên bản nội dung

Một resource ID có thể trỏ sang phiên bản mới. Quyết định quyền và cache phải xác định rõ nội dung nào được phép phát.

Không kiểm tra quyền với metadata v4 rồi trả bản v5 do object bị thay hoặc cache không phân biệt phiên bản. Tương tự, một phiên bản đã bị thu hồi không được tiếp tục được phát chỉ vì bản cache còn tồn tại ngoài ngân sách chính sách.

Sửa header hoặc rule cache không tự xóa mọi bản lưu trước đó. Thay đổi cần có cách xử lý các bản đã lưu và kiểm tra sau triển khai.

## 9. Bao phủ mọi đường nhận nội dung

### 9.1. GET, HEAD, Range và kiểm tra điều kiện

HEAD có thể tiết lộ kích thước, loại nội dung hoặc thời điểm thay đổi. Range có thể trả một phần dữ liệu thực. Một request điều kiện có thể xác nhận sự tồn tại hoặc phiên bản tài nguyên.

Các đường này phải có quyết định quyền phù hợp trước khi trả nội dung hoặc metadata thuộc phạm vi bảo vệ. Không chỉ đặt guard trên GET tải toàn bộ.

HTTP status hoặc response không có body chưa đủ để kết luận không có rò rỉ. Phải đối chiếu những thông tin chính sách cho phép chủ thể nhận.

### 9.2. Preview và bản dẫn xuất

Ảnh thumbnail, kết quả OCR, bản chuyển đổi và bản xem trước có thể chứa dữ liệu nhạy cảm của bản gốc.

Cần xác định quyền riêng hoặc kế thừa phù hợp. Nếu người dùng chỉ được xem một bản đã che dữ liệu, không được cho cùng quyền đó tải bản gốc.

Metadata phải liên kết rõ loại nội dung và phiên bản được cấp. Một endpoint trả preview không được cho client thay tham số để mở object gốc mà không đánh giá lại quyền.

### 9.3. Tải nhóm và ZIP

Với một ZIP gồm nhiều tài liệu, quyền không thể được suy ra chỉ từ việc người dùng tạo job. Phải kiểm tra tập tài nguyên và kết quả tổng hợp.

Trong ví dụ, chính sách là từ chối việc tạo hoặc phát ZIP nếu một thành phần không còn đủ điều kiện theo điểm kiểm tra đã quy định. Nếu sản phẩm chọn bỏ qua phần tử không được phép, phải có hợp đồng rõ và không làm lộ metadata ngoài quyền.

Artifact ZIP cũng là tài nguyên riêng tư. Cần ghi nhận tập thành phần, phiên bản, phân loại và quan hệ quyền. Không biến nó thành tệp public chỉ vì đã kiểm tra từng thành phần lúc bắt đầu.

Nếu quyền đổi trong lúc tạo ZIP, phải có bước kiểm tra theo chính sách trước phát hành/tải. Một job kéo dài không được giữ quyền cũ vô hạn mà không có quyết định thiết kế tương ứng.

### 9.4. Export bất đồng bộ và dịch vụ đại diện

Worker thường có quyền kỹ thuật rộng để đọc storage. Quyền đó không tự cho phép worker tạo export mọi dữ liệu theo yêu cầu client.

Cần lưu chủ thể yêu cầu, phạm vi được duyệt và ngữ cảnh đại diện. Worker phải kiểm tra những quyền và guard cần thiết tại thời điểm thực thi, còn lần tải artifact phải tuân theo chính sách hiện hành tại điểm phân phối.

Lệnh trong hàng đợi không mặc nhiên giữ quyền mãi mãi. Service account có thể xác thực lệnh được giao, nhưng vẫn cần kiểm soát người mà nó đại diện và tài nguyên được phép xử lý.

### 9.5. Danh tính dịch vụ và danh tính người dùng

Một service có thể gọi API thay người dùng hoặc làm tác vụ hệ thống độc lập. Hai trường hợp cần quyền và audit khác nhau.

Không chấp nhận một header như “on behalf of user” chỉ vì request đến từ mạng nội bộ. Quan hệ đại diện phải được xác minh bằng cơ chế được duyệt, giới hạn đối tượng và hành động.

Nếu tác vụ hệ thống được phép không phụ thuộc quyền người dùng, đó phải là quyền hệ thống được đặc tả, không phải fallback vô tình khi mất ngữ cảnh người dùng.

## 10. Hợp đồng lỗi, tài nguyên và audit

### 10.1. Lỗi không làm lộ metadata ngoài quyền

Chính sách có thể chọn phản hồi giống nhau cho “không tồn tại” và “không được phép” nhằm giảm tiết lộ. Cần áp dụng nhất quán trên các đường thuộc phạm vi, gồm metadata và đường tải gián tiếp.

Không bắt buộc mọi hệ thống phải dùng cùng một mã HTTP. Điều cần chứng minh là chủ thể không nhận thông tin vượt quyền và không có nội dung được gửi trước khi từ chối.

Thông báo lỗi không nên chứa storage path, bucket key nhạy cảm, URL có quyền hoặc chi tiết policy nội bộ không cần thiết. Phía audit có thể giữ lý do phân loại với kiểm soát truy cập phù hợp.

### 10.2. Phân quyền không thay thế giới hạn tài nguyên

Một người có quyền vẫn có thể tạo quá nhiều download hoặc Range request. Cần ngân sách phù hợp cho số phiên, băng thông, thời gian truyền và dung lượng export.

Giới hạn phải có đơn vị và phạm vi: mỗi principal, tenant, instance hay toàn cụm. Không công bố giới hạn toàn cụm khi thực tế chỉ có bộ đếm cục bộ.

Khi quá tải, từ chối có kiểm soát và giữ nguyên kiểm tra quyền. Không chuyển sang một đường public “để giảm tải” nếu chưa có cơ chế truy cập phù hợp.

### 10.3. Audit phân biệt quyết định và truyền dữ liệu

Các mốc cần phân biệt có thể gồm:

- Request được tiếp nhận.
- Quyết định cho phép hoặc từ chối được tạo.
- Grant được cấp hoặc nội dung bắt đầu được gửi.
- Kết thúc truyền, client hủy hoặc lỗi I/O.
- Số byte do điểm phân phối quan sát, nếu cần cho mục tiêu kiểm chứng.

Một audit “allowed” không chứng minh toàn bộ tệp đã được tải. Một lỗi ở cuối luồng cũng không chứng minh không byte nào đã rời máy chủ.

Dữ liệu audit nên liên kết principal, actor/service, tenant, resource, version, action, kết quả, nguồn/phiên bản policy khi áp dụng và correlation ID. Không ghi token hay URL mang quyền vào log thông thường.

### 10.4. Khi audit bắt buộc không còn hoạt động

Với tài liệu có yêu cầu audit bền vững trước phát hành, phải đặc tả điều kiện tiếp tục, lưu đệm hoặc từ chối khi đường audit lỗi.

Không để một logger gọi không chờ được coi là đã đáp ứng yêu cầu bền vững. Ngược lại, không cần áp chính sách chặn mọi tải cho mọi phân loại nếu yêu cầu nghiệp vụ không chọn cách đó.

Quyết định phải gắn với phân loại, rủi ro và bằng chứng nghiệm thu.

## 11. Bộ yêu cầu bảo mật minh họa

Các yêu cầu sau áp dụng cho tài liệu confidential của cổng hồ sơ. Trong ví dụ, đường mặc định kiểm tra quyền khi tải; nếu chọn cơ chế cấp quyền tạm thời, nó phải giữ được bảo đảm đã công bố hoặc có phạm vi chính sách khác được phê duyệt.

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| DLA-01 | Phải có danh mục mọi đường phân phối nội dung/metadata và ma trận chủ thể–hành động–tài nguyên–điều kiện; mỗi đường có điểm thực thi quyền được xác định. | Chủ dịch vụ/bảo mật | Đối chiếu API, static route, storage, CDN, preview và export; không có đường ngoài danh mục. |
| DLA-02 | Quyết định tải phải dựa trên danh tính, tenant, quyền với tài nguyên/hồ sơ và điều kiện phân loại từ nguồn có thẩm quyền; client không được tự đặt ngữ cảnh quyền. | Ứng dụng | Đổi ID, tenant, owner hoặc role trong request không vượt quyền; người hợp lệ tải đúng tài nguyên. |
| DLA-03 | Chỉ nội dung và phiên bản có trạng thái cho phép mới được phân phối; quyết định phải ràng buộc với phiên bản thực tế được mở. | Ứng dụng/storage | Thay object/version sau kiểm tra, thu hồi tài liệu hoặc chuyển trạng thái không làm trả nội dung trái quyết định. |
| DLA-04 | Trong ví dụ, mọi đường thuộc phạm vi phải phản ánh thu hồi trong không quá 60 giây đối với quyết định tải mới, tính từ commit tại nguồn quyền; chính sách luồng đang chạy được đặc tả riêng. | Bảo mật/nền tảng | Timeline thu hồi và request liên tục qua từng đường; đo lần chấp nhận cuối không còn hợp lệ, không chỉ kiểm tra một node. |
| DLA-05 | Nếu không xác minh được quyền hoặc độ mới trong giới hạn đã phê duyệt, tài liệu thuộc phạm vi không được tải dựa vào payload hoặc dữ liệu quá cũ. | Ứng dụng/bảo mật | Ngắt nguồn policy, làm cache quá tuổi, cung cấp dữ kiện client có vẻ hợp lệ; không tạo đường cho phép mù. |
| DLA-06 | GET, HEAD, Range, request điều kiện, preview và bản dẫn xuất phải có kiểm soát quyền phù hợp trước khi trả thông tin thuộc phạm vi bảo vệ. | Chủ API | Ma trận kiểm thử từng phương thức/biến thể với chủ thể được phép và không được phép. |
| DLA-07 | Grant tạm thời phải có resource/version/action/thời hạn và ngữ nghĩa người giữ rõ ràng; khâu cấp và sử dụng không được vượt bảo đảm thu hồi của phân loại. | Bảo mật/tích hợp | Sửa thuộc tính, hết hạn, chuyển người giữ và thu hồi; hành vi khớp mô hình bearer hoặc ràng buộc danh tính thực sự. |
| DLA-08 | Nội dung không được truy cập qua origin, static route hoặc endpoint storage ngoài cơ chế được phê duyệt; có quyền kỹ thuật của service không tạo quyền công khai. | Nền tảng | Dùng fixture và key đã biết qua mọi endpoint; không nhận nội dung khi thiếu quyền hoặc grant hợp lệ theo chính sách. |
| DLA-09 | Cache/CDN phải giữ phân tách cần thiết, phiên bản và hiệu lực quyền; thay cấu hình phải xử lý các bản cache cũ theo chính sách. | Nền tảng | Tải dưới nhiều principal, đổi quyền, đổi phiên bản và truy cập qua cache lẫn origin; không dùng nội dung cũ trái bảo đảm. |
| DLA-10 | Tải nhóm/export phải kiểm tra từng thành phần và quyền phát artifact; trong ví dụ, một thành phần không đủ điều kiện khiến tạo/phát nhóm bị từ chối theo điểm kiểm tra đã định. | Ứng dụng/nghiệp vụ | Trộn tài liệu của nhiều tenant, đổi quyền khi job chạy và tải artifact cũ; không lộ phần tử ngoài quyền. |
| DLA-11 | Dịch vụ đại diện phải chứng minh được ngữ cảnh ủy quyền và phạm vi; worker không được dùng quyền storage rộng để mở rộng quyền người yêu cầu. | Bảo mật/ứng dụng | Giả ngữ cảnh đại diện, mất chủ thể hoặc thay lệnh trong queue không làm export/tải dữ liệu ngoài phạm vi. |
| DLA-12 | Audit phải liên kết quyết định với resource/version, chủ thể, tenant và kết quả phân phối; không ghi token/URL có quyền ngoài chính sách, không coi allowed là bằng chứng hoàn tất truyền. | Vận hành/ứng dụng | Đối chiếu quyết định, log truyền và lỗi/hủy; kiểm tra bí mật không xuất hiện ở nơi không được phép. |
| DLA-13 | Lỗi và giới hạn tài nguyên phải giữ ranh giới quyền; metadata, path và chi tiết nhạy cảm không bị lộ, quá tải không chuyển sang đường public. | Chủ API/vận hành | Test lỗi backend, request không quyền và tải vượt ngân sách được quy định; phản hồi vẫn theo chính sách. |
| DLA-14 | Thay policy, cơ chế cấp grant, cache, backend hoặc restore phải kiểm tra lại ma trận quyền và bảo đảm thu hồi trước khi mở sử dụng. | Chủ dịch vụ | Bằng chứng kiểm thử sau thay đổi, gồm quyền cũ, grant cũ, artifact và các đường origin/CDN. |

Những yêu cầu có nhiều điều kiện có thể được tách thành các mục nhỏ hơn trong đặc tả dự án để giao chủ sở hữu và nghiệm thu riêng. Điều quan trọng là giữ liên kết giữa mục tiêu, rủi ro, thiết kế và bằng chứng.

### 11.1. Mẫu đặc tả chi tiết cho thu hồi quyền

```text
ID: DLA-04
Mục tiêu: ngăn request tải mới tiếp tục dùng quyền đã bị thu hồi quá hạn
Rủi ro: R-DOWNLOAD-04 — quyền cũ tồn tại ở cache hoặc grant phân phối
Phạm vi:
  - Tài liệu confidential và bản dẫn xuất trong danh mục
  - API, gateway, CDN/origin và cơ chế grant được phê duyệt
Bắt đầu tính:
  - Thời điểm thu hồi commit tại nguồn quyền có thẩm quyền
Điều kiện đạt:
  - Không có quyết định tải mới dựa vào quyền đã thu hồi sau 60 giây
  - Thiếu bằng chứng đủ mới không được xem là còn quyền
  - Thời hạn bao phủ cả trễ cấp grant và khả năng dùng grant còn lại
Luồng đã bắt đầu:
  - Theo chính sách riêng của ví dụ, có thể tiếp tục trong giới hạn đã duyệt
  - Request Range mới vẫn phải kiểm tra lại theo hợp đồng
Chủ sở hữu: đội bảo mật và nền tảng; chủ dịch vụ chịu trách nhiệm nghiệm thu
Kiểm thử: T-DLA-04, T-DLA-05, T-DLA-07
Bằng chứng: timeline, phiên bản policy, điểm vào và kết quả request
```

Một grant chỉ có TTL nhưng không có cách thu hồi có thể không đạt yêu cầu này. Khi đó cần đổi thiết kế hoặc phạm vi bảo đảm được phê duyệt; không sửa định nghĩa đo để tạo kết quả đạt.

## 12. Ma trận kiểm thử nghiệm thu

Dùng môi trường kiểm soát với tài liệu tổng hợp có marker nội dung và metadata đã biết. Cần có nhiều principal/tenant, các trạng thái tài liệu và các đường phân phối thực tế.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-DLA-01 | Người có quyền tải qua đường chính; sau đó anonymous, người cùng tenant không có quyền và tenant khác thử cùng resource ID, không có grant riêng hợp lệ. | Chỉ chủ thể đúng chính sách nhận nội dung; không suy ra quyền chỉ từ phiên đăng nhập hoặc ID khó đoán. | DLA-01, 02 |
| T-DLA-02 | Sửa tenant, owner, role, resource ID hoặc storage reference trong request. | Ngữ cảnh đáng tin và ánh xạ máy chủ được giữ; không đọc tài nguyên ngoài phạm vi. | DLA-02, 08 |
| T-DLA-03 | Tài liệu ở trạng thái chờ kiểm tra/bị thu hồi; đổi object/version sau quyết định đọc. | Không trả nội dung chưa được phép hoặc phiên bản khác; trạng thái và phiên bản thực tế khớp quyết định. | DLA-03 |
| T-DLA-04 | Cấp quyền, tạo cache/grant theo thiết kế, rồi commit thu hồi; gửi request mới qua mọi đường với nguồn đo nhất quán. | Sau tối đa 60 giây trong ví dụ không còn quyết định mới dựa vào quyền cũ; có timeline từng lớp và lần chấp nhận cuối. | DLA-04, 09 |
| T-DLA-05 | Ngắt policy service, làm cache quá tuổi hoặc chặn cập nhật thu hồi; đồng thời client gửi role/quyền cũ. | Không dùng dữ kiện thiếu tin cậy để tiếp tục; trạng thái lỗi và cảnh báo theo thiết kế. | DLA-04, 05 |
| T-DLA-06 | Thử GET, HEAD, Range, request điều kiện, preview và bản đã che dữ liệu/bản gốc dưới các quyền khác nhau. | Mỗi biến thể chỉ trả nội dung/metadata thuộc quyền; quyền xem bản che không tự mở bản gốc. | DLA-06 |
| T-DLA-07 | Nếu có grant, sửa resource/version/action, dùng trước/sau hạn, chia sẻ và kiểm tra thu hồi. | Điểm nhận thực thi đúng thuộc tính và mô hình người giữ; không hứa ràng buộc principal khi thực tế chỉ là bearer grant. | DLA-04, 07 |
| T-DLA-08 | Truy cập static route, origin, CDN và endpoint object theo key đã biết, thiếu quyền/grant phù hợp. | Không đi vòng được kiểm soát; deny listing hoặc bảo vệ một URL không được tính là đủ. | DLA-01, 08 |
| T-DLA-09 | Tạo cache bằng principal A, sau đó principal B dùng cùng URL; đổi quyền và phiên bản rồi thử lại. | Cache không phát dữ liệu ngoài quyền, sai phiên bản hoặc quá ngân sách thu hồi. | DLA-09 |
| T-DLA-10 | Tạo ZIP/export chứa một tài liệu không thuộc quyền; ở lượt khác thu hồi quyền khi job đang chạy hoặc trước tải artifact. | Chính sách từng thành phần và artifact được giữ; worker không cho phép vượt quyền nhờ quyền kỹ thuật rộng. | DLA-10, 11 |
| T-DLA-11 | Giả header đại diện, đổi actor trong lệnh queue hoặc gọi bằng service account ngoài phạm vi được giao. | Không chấp nhận ngữ cảnh đại diện không được xác minh; audit phân biệt service và chủ thể nghiệp vụ. | DLA-11, 12 |
| T-DLA-12 | Cho phép tải rồi client hủy, lỗi I/O giữa chừng, lỗi audit theo chính sách và request không quyền. | Audit không nhầm allowed với hoàn tất; phản hồi và dữ liệu không lộ bí mật, path hoặc metadata trái quyền. | DLA-12, 13 |
| T-DLA-13 | Tải vượt số phiên/băng thông theo ngân sách; tạo nhiều Range request và lỗi backend. | Từ chối/giảm tải có kiểm soát; không chuyển sang đường public hoặc bỏ phân quyền. | DLA-13 |
| T-DLA-14 | Restore hoặc migrate quyền, metadata, CDN/storage; thử lại quyền đã thu hồi, grant/artifact cũ và đường origin. | Không làm sống lại truy cập trái chính sách; bằng chứng kiểm tra trước mở lưu lượng đầy đủ. | DLA-14 |

Nếu một thiết kế không dùng grant tạm thời, test grant không được đánh dấu đạt theo suy đoán; ghi rõ không áp dụng và bằng chứng cơ chế không tồn tại trong phạm vi.

Nếu có nhiều loại chia sẻ, phải tách test theo loại. Một người không đăng nhập nhưng giữ một grant bearer hợp lệ có thể được phép theo chính sách chia sẻ đã duyệt; không được nhầm điều đó với việc object công khai không cần bất kỳ quyền nào.

### 12.1. Cách đo thu hồi

Một phép đo đủ ý nghĩa cần:

1. Ghi nhận mốc commit thu hồi tại nguồn có thẩm quyền.
2. Duy trì request mới qua từng điểm vào trong phạm vi.
3. Phân biệt quyết định mới với luồng tải đã được cho phép trước đó.
4. Kiểm tra quyền, grant và cache có thể tiếp tục cho nội dung bằng cách nào.
5. Xác định lần chấp nhận cuối dựa vào quyền đã thu hồi.
6. Báo độ không chắc chắn của thời gian và mọi điểm chưa quan sát được.

Không tính mốc bắt đầu từ lúc cache cuối cùng đã cập nhật. Làm vậy sẽ bỏ qua chính độ trễ cần kiểm chứng.

### 12.2. Bằng chứng phải gắn với nội dung thực tế

Một response 200 có thể chỉ là trang đăng nhập hoặc trang ứng dụng mặc định. Một response 403/404 ở một đường không chứng minh origin khác đã bị chặn.

Cần so marker, metadata và tài nguyên/phiên bản nhận được. Không dùng tài liệu thật để kiểm tra rò rỉ trong khi fixture tổng hợp có thể chứng minh cùng điều kiện.

Báo cáo nên có cấu hình hiệu lực, phiên bản policy, danh tính thử, resource/version, điểm vào, request, kết quả và dấu vết tương ứng. Không đưa token hoặc URL còn quyền vào báo cáo không được bảo vệ.

## 13. Truy vết từ rủi ro đến vận hành

Chuỗi truy vết tối thiểu:

```text
Mục tiêu bảo vệ tài liệu
    → Kịch bản truy cập ngoài quyền hoặc dùng quyền cũ
    → Yêu cầu DLA-xx
    → Nguồn quyền, điểm quyết định và đường phân phối
    → Test T-DLA-xx
    → Audit, metric, cảnh báo và kiểm tra thay đổi
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Giữ ranh giới tenant và hồ sơ | Đổi resource ID hoặc ngữ cảnh client | DLA-02 | Quan hệ quyền và tenant có thẩm quyền; T-DLA-01, 02 |
| Phát đúng nội dung được phép | Object đổi sau kiểm tra | DLA-03 | Ràng buộc version; T-DLA-03 |
| Thu hồi quyền trong giới hạn | Cache hoặc grant tiếp tục hoạt động | DLA-04, 07, 09 | Ngân sách hiệu lực đầu cuối; T-DLA-04, 07, 09 |
| Không lộ qua đường phụ | HEAD, Range, preview hoặc origin bỏ guard | DLA-01, 06, 08 | Danh mục và điểm thực thi; T-DLA-06, 08 |
| Không mở rộng quyền qua worker | Export dùng quyền service quá rộng | DLA-10, 11 | Ngữ cảnh đại diện và kiểm tra artifact; T-DLA-10, 11 |
| Chứng minh quyết định và phân phối | Audit chỉ ghi allowed | DLA-12 | Tách quyết định, bắt đầu, hoàn tất và lỗi; T-DLA-12 |

Thay đổi quyền kế thừa, phân loại, TTL, cơ chế cache, endpoint storage hoặc định dạng export đều có thể thay đổi bảo đảm. Cần đánh giá lại ma trận và test liên quan.

Ngoại lệ cần có phạm vi tài liệu, đường phân phối, bảo đảm khác biệt, thời hạn, biện pháp bù và người phê duyệt. Không giảm độ bảo vệ của mọi tài liệu vì một loại nội dung cần chia sẻ thuận tiện hơn.

## 14. Những lỗi đặc tả thường gặp

| Cách viết hoặc triển khai | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Đăng nhập mới được tải.” | Người đã đăng nhập vẫn có thể ngoài quyền tài nguyên | Kiểm tra đối tượng, tenant, hồ sơ và điều kiện nội dung |
| “Resource ID ngẫu nhiên nên an toàn.” | ID có thể bị lộ hoặc chia sẻ | Giữ kiểm tra quyền trên mọi request thuộc phạm vi |
| “Người upload luôn là owner nên được tải.” | Quyền có thể bị thu hồi hoặc thay đổi | Đánh giá quyền hiện hành theo chính sách |
| “Service đọc được bucket nên cho trả luôn.” | Quyền kỹ thuật không bằng quyền người dùng | Phân biệt service và chủ thể được đại diện |
| “URL hết hạn sau 5 phút nên thu hồi được trong 1 phút.” | TTL và độ trễ cấp có thể vượt ngân sách thu hồi | Tính bảo đảm đầu cuối hoặc đổi cơ chế |
| “Token ghi user ID nên không chia sẻ được.” | Điểm nhận có thể không xác thực người giữ | Kiểm tra ràng buộc thực sự hoặc công bố mô hình bearer |
| “Chỉ GET cần guard.” | HEAD, Range và preview vẫn có thể lộ | Kiểm tra mọi biến thể nhận nội dung/metadata |
| “CDN có bảo vệ là đủ.” | Origin có thể vẫn công khai | Kiểm tra cả origin và đường phân phối |
| “Job đã nhận thì không cần kiểm tra lại quyền.” | Lệnh có thể chờ tới khi quyền đã đổi | Đặc tả kiểm tra lúc thực thi và lúc phát artifact |
| “Allowed nghĩa là đã tải xong.” | Client có thể hủy hoặc truyền lỗi | Audit phân biệt quyết định và diễn biến truyền |
| “403 ở URL chính chứng minh không rò rỉ.” | URL khác, cache hoặc metadata có thể vẫn mở | Ma trận đường truy cập và đối chiếu fixture |
| “Restore đúng tệp là xong.” | Quyền, grant hoặc cache cũ có thể sống lại | Kiểm tra ranh giới và hiệu lực quyền sau phục hồi |

## 15. Bài tập áp dụng

Một nền tảng nhân sự có tài liệu hợp đồng, ảnh đại diện và hồ sơ ứng tuyển. API tải yêu cầu đăng nhập nhưng dùng role chung. Preview đi qua CDN, export chạy bằng service account, và URL tải hợp đồng có thời hạn 10 phút. Khi nhân viên rời bộ phận, quyền đọc hồ sơ phải bị thu hồi trong 60 giây.

Hãy thực hiện:

1. Phân loại tài nguyên và xác định quyền đọc metadata, preview, bản gốc và export.
2. Lập danh mục điểm vào, nguồn quyền và điểm thực thi.
3. Giải thích vì sao role chung và URL 10 phút có thể không đáp ứng yêu cầu của hợp đồng.
4. Viết sáu yêu cầu có ID, phạm vi, điều kiện đạt, chủ sở hữu và bằng chứng.
5. Thiết kế kiểm thử tenant khác, quyền bị thu hồi, Range, cache và origin.
6. Đề xuất ngữ cảnh đại diện cho worker export và điều kiện phát artifact.
7. Phân biệt grant bearer với grant thực sự ràng buộc danh tính tại điểm nhận.
8. Thiết kế audit cho từ chối, cho phép, bắt đầu truyền, hủy và hoàn tất.
9. Nêu những gì cần kiểm tra sau migrate hoặc restore trước khi mở tải xuống.

Đáp án tốt phải giải thích được ai nhận nội dung nào, bằng quyết định nào, trong thời hạn hiệu lực nào và qua những đường có thể kiểm chứng.

## 16. Checklist chấp nhận yêu cầu

- Có ma trận chủ thể–hành động–tài nguyên–điều kiện rõ ràng chưa?
- Danh tính, tenant và quyền có đến từ nguồn có thẩm quyền không?
- Có kiểm tra quyền đối tượng thay vì chỉ role hoặc phiên đăng nhập không?
- Trạng thái và phiên bản được trả có khớp quyết định không?
- Thời hạn thu hồi có mốc bắt đầu, phạm vi và cách đo đầu cuối không?
- Luồng đang chạy và request Range mới có chính sách rõ không?
- Cache quyền quá cũ hoặc nguồn policy lỗi có hành vi được phê duyệt không?
- Grant có phạm vi, thời hạn, ngữ nghĩa người giữ và khả năng thu hồi thực tế không?
- HEAD, Range, preview, bản dẫn xuất và ZIP có cùng mức bảo vệ phù hợp không?
- Worker có ngữ cảnh đại diện được xác minh và không mở rộng quyền người yêu cầu không?
- Origin, static route và storage có tránh đường đi vòng không?
- Cache/CDN có giữ quyền, phiên bản và hiệu lực thu hồi không?
- Lỗi có tránh lộ metadata, path và khả năng truy cập không?
- Audit có phân biệt quyết định với dữ liệu thực sự đã được phân phối không?
- Test có bao phủ quyền cũ, grant cũ, artifact và đường truy cập sau restore không?

Phân quyền tải xuống đáp ứng mục tiêu bảo mật khi từng nội dung được gắn với một quyết định hợp lệ, mọi đường phân phối giữ đúng điều kiện của quyết định đó, và việc thay đổi quyền được thực thi trong giới hạn đã công bố.
