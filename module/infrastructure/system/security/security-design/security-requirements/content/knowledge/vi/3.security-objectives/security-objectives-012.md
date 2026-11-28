# Secure by default

## 1. Trạng thái mặc định là một quyết định bảo mật

Một hệ thống có thể hỗ trợ xác thực, phân quyền, mã hóa và logging nhưng vẫn khởi động với xác thực tắt, tài khoản quản trị dùng mật khẩu chung hoặc kho dữ liệu được mở công khai. Người vận hành phải tự biết và tự bật từng biện pháp trước khi sử dụng.

Trong trường hợp đó, khả năng bảo vệ có tồn tại nhưng trạng thái ban đầu chưa bảo vệ người dùng theo mục tiêu đã đặt ra.

**Secure by default — an toàn theo mặc định** là nguyên tắc chọn trạng thái ban đầu và hành vi khi chưa có lựa chọn rõ ràng sao cho hệ thống duy trì mức bảo vệ phù hợp với bối cảnh, thay vì tự cấp quyền rộng hoặc làm lộ dữ liệu.

Một yêu cầu theo nguyên tắc này cần trả lời:

- Khi cài mới, hệ thống tự bật hoặc tự tắt điều gì?
- Khi tạo một tài khoản, tenant, tài nguyên hay giao diện mới, quyền và mức công khai ban đầu là gì?
- Khi thiếu cấu hình, gặp lỗi hoặc khôi phục trạng thái, hệ thống xử lý thế nào?
- Người vận hành có phải thực hiện một bước không được nhắc tới mới đạt mức bảo vệ cần thiết không?
- Ai có thể thay đổi mặc định và thay đổi đó được quản lý ra sao?

Mặc định an toàn phải được thiết kế cho chức năng thực tế. Một hệ thống từ chối mọi hành động có thể tránh một số truy cập sai quyền nhưng không đáp ứng nhu cầu sử dụng. Cần cung cấp đường sử dụng hợp lệ rõ ràng, thuận tiện và được bảo vệ.

Bài học thuộc chương **Mục tiêu bảo mật**, tập trung vào cách chuyển nguyên tắc này thành yêu cầu có thể triển khai và kiểm chứng. Các cấu hình, mã yêu cầu và tình huống dưới đây là ví dụ giả định.

## 2. Phân biệt các nguyên tắc liên quan

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Secure by design | Kiến trúc và quy trình có đưa bảo mật vào từ đầu không? | Quyền được thực thi ở máy chủ trước khi trả dữ liệu |
| Secure by default | Khi chưa tùy chỉnh, trạng thái sử dụng có được bảo vệ không? | Tài nguyên mới không tự công khai hoặc nhận quyền quá rộng |
| Least privilege | Chủ thể được cấp ít quyền đến mức cần thiết nào? | Tài khoản tác vụ chỉ đọc tập dữ liệu phục vụ tác vụ đó |
| Default deny | Khi không có quyết định cho phép hợp lệ, kết quả quyền là gì? | Giao diện không có chính sách cho phép không tự mở truy cập |
| Fail-safe defaults | Khi thiếu điều kiện hoặc lỗi, hệ thống có giữ trạng thái bảo vệ không? | Không xác định được quyền thì không thực hiện thao tác nhạy cảm |
| Hardening | Cần điều chỉnh gì để giảm bề mặt tấn công cho môi trường cụ thể? | Thu hẹp cổng, tính năng và quyền vận hành không cần thiết |

Các nguyên tắc hỗ trợ nhau nhưng không thay thế nhau.

Một kiến trúc có cơ chế phân quyền tốt vẫn có thể có mặc định xấu nếu mọi tài khoản mới đều được gán vai trò quản trị. Một bản hướng dẫn hardening không tự làm cài đặt ban đầu an toàn nếu người vận hành phải đọc tới cuối mới phát hiện cần tắt tài khoản dùng chung.

### 2.1. “Mặc định” có nhiều thời điểm

Không chỉ lúc chạy ứng dụng lần đầu. Cần xét:

1. Cài mới hoặc tạo môi trường.
2. Tạo tài khoản, tenant, khóa, tệp hoặc nhóm quyền.
3. Thêm endpoint, tác vụ hoặc tích hợp.
4. Thiếu, sai hoặc mâu thuẫn cấu hình.
5. Nâng cấp và di chuyển dữ liệu.
6. Khôi phục sau sự cố hoặc đặt lại cấu hình.
7. Hết hạn một ngoại lệ hoặc một quyền tạm thời.

Một trạng thái an toàn ở thời điểm cài mới có thể bị phá vỡ khi nâng cấp hoặc phục hồi. Phạm vi yêu cầu phải bao phủ các thời điểm có ảnh hưởng tới tài sản cần bảo vệ.

### 2.2. Không có một bộ giá trị phù hợp mọi sản phẩm

Một ứng dụng nội bộ, một dịch vụ công khai và một thư viện sẽ có các quyết định mặc định khác nhau.

Ví dụ, giao diện đăng nhập có thể cần công khai theo thiết kế, còn dữ liệu khách hàng phải có kiểm soát truy cập. Việc xác định rõ giao diện công khai là một quyết định có chủ đích; không nên mở toàn bộ API chỉ vì sản phẩm có một số chức năng công khai.

Các giá trị như thời hạn phiên, ngưỡng chống lạm dụng và thời gian lưu log phải xuất phát từ rủi ro, nghiệp vụ và nghĩa vụ áp dụng. Nguyên tắc không cung cấp một con số phổ quát để sao chép.

## 3. Bối cảnh xuyên suốt: dịch vụ hóa đơn nhiều tenant

Mỗi tenant là một tổ chức khách hàng có phạm vi dữ liệu và quyền riêng.

Ứng dụng cho phép:

- Khởi tạo tổ chức và người quản trị đầu tiên.
- Thêm thành viên.
- Đọc và phê duyệt hóa đơn.
- Xuất dữ liệu ra tệp.
- Gửi thông báo và ghi sự kiện kiểm toán.
- Sao lưu, nâng cấp và phục hồi.

Tài sản cần bảo vệ gồm dữ liệu hóa đơn, thông tin cá nhân, quyền phê duyệt, tệp xuất, bí mật tích hợp và dấu vết kiểm toán.

Các rủi ro liên quan trực tiếp tới mặc định:

| Mã | Tình huống | Hậu quả |
| --- | --- | --- |
| R-DEF-01 | Tài khoản mới tự có quyền quản trị hoặc phê duyệt | Người chưa được cấp quyền tạo tác động nhạy cảm |
| R-DEF-02 | Tenant hoặc tệp mới tự có quyền truy cập rộng | Rò rỉ dữ liệu giữa các khách hàng |
| R-DEF-03 | Thiếu cấu hình xác thực làm ứng dụng bỏ kiểm tra | Truy cập trái phép sau lỗi triển khai |
| R-DEF-04 | Môi trường thật chạy bằng cấu hình mẫu có bí mật chung | Chiếm tài khoản hoặc tài nguyên tích hợp |
| R-DEF-05 | Debug và dữ liệu lỗi chi tiết được bật sẵn | Lộ token, thông tin nội bộ hoặc dữ liệu khách hàng |
| R-DEF-06 | Nâng cấp hoặc phục hồi đưa quyền và cấu hình về trạng thái yếu | Mở lại truy cập đã bị thu hồi hoặc tính năng đã bị tắt |
| R-DEF-07 | Tích hợp mới tự chấp nhận nguồn hoặc quyền quá rộng | Dữ liệu bị gửi sai nơi hoặc thông điệp giả tạo tác động |

Những tình huống này giúp chuyển “an toàn theo mặc định” thành nghĩa vụ cụ thể. Chỉ ghi “mọi cấu hình phải secure” chưa đủ để thiết kế hoặc nghiệm thu.

## 4. Bắt đầu bằng trạng thái bảo vệ và bất biến

**Bất biến bảo mật** là điều kiện cần được giữ trong những trạng thái thuộc phạm vi. Ví dụ:

- Không trả dữ liệu hóa đơn khi chưa xác lập được quyền đọc phù hợp.
- Không để tài khoản mới tự có quyền phê duyệt nếu chưa có quyết định cấp quyền hợp lệ.
- Không gửi bí mật xác thực tới log.
- Không xác nhận phục hồi hoàn tất khi các điều kiện về dữ liệu và quyền chưa đạt.

Bất biến khác với một giá trị cấu hình. Một cờ bật xác thực có thể góp phần thực hiện bất biến, nhưng không chứng minh mọi đường đọc dữ liệu đều đi qua xác thực và phân quyền.

### 4.1. Chọn đường sử dụng hợp lệ được bảo vệ

Với tạo thành viên, có thể thiết kế:

```text
Tạo lời mời có phạm vi tenant
  -> người nhận hoàn tất điều kiện xác thực
  -> tài khoản được kích hoạt theo chính sách
  -> chỉ nhận vai trò cơ bản đã xác định
  -> quyền nhạy cảm được cấp qua thao tác có thẩm quyền
```

Không nên yêu cầu người vận hành nhớ hạ quyền cho từng tài khoản sau khi hệ thống đã tự cấp quyền quản trị.

Nếu sản phẩm cần cấp vai trò ban đầu để dùng được, phải định nghĩa chính xác tập quyền đó và kiểm chứng nó không bao gồm quyền ngoài mục đích.

### 4.2. Phân biệt mặc định và ràng buộc không được tùy ý hạ thấp

Có hai dạng quyết định:

- **Mặc định có thể điều chỉnh:** giá trị ban đầu có thể thay đổi trong phạm vi chính sách, chẳng hạn thời gian lưu một loại sự kiện.
- **Ràng buộc bắt buộc:** điều kiện phải được giữ trong môi trường hoặc chức năng đã xác định, chẳng hạn không bỏ kiểm tra quyền đối với dữ liệu khách hàng.

Nếu một ràng buộc bắt buộc có thể bị tắt bằng một giá trị môi trường không được kiểm tra, việc đặt mặc định đúng chưa đủ.

Thiết kế cần xác định ai được thay đổi, phạm vi thay đổi và cơ chế từ chối cấu hình không hợp lệ. Một ngoại lệ, nếu được phép, phải được quản lý riêng theo thẩm quyền.

## 5. Các mặc định cần đặc tả theo nhóm yêu cầu

### 5.1. Xác thực và khởi tạo quản trị

Cài mới không được để tồn tại một thông tin xác thực quản trị dùng chung, có thể dự đoán và còn sử dụng được trong môi trường cần bảo vệ.

Đường khởi tạo có thể sử dụng một cơ chế riêng biệt, có thời hạn và được bảo vệ. Cần đặc tả:

- Ai được bắt đầu hoặc hoàn tất khởi tạo?
- Kênh nào được dùng để chuyển thông tin khởi tạo?
- Làm sao ngăn một người không có quyền chiếm bước “người quản trị đầu tiên”?
- Cơ chế khởi tạo có bị vô hiệu hóa sau khi hoàn tất không?
- Có thể tái sử dụng hoặc khởi tạo lại ngoài quy trình không?
- Bí mật khởi tạo có bị đưa vào log hoặc tài liệu mẫu không?

Không nên xử lý bằng cách phát hành tài khoản mặc định rồi chỉ thêm một câu “hãy đổi mật khẩu”. Nếu quy trình cho phép một thông tin khởi tạo tạm thời, phải kiểm soát việc cấp, sử dụng, thời hạn và vô hiệu hóa của chính nó.

MFA, khi bắt buộc với nhóm quản trị theo mô hình đã chọn, cần được áp dụng trong luồng khởi tạo và các đường truy cập quản trị liên quan. Không chỉ đặt một tùy chọn cho phép bật sau.

### 5.2. Phân quyền và cách ly tenant

Mặc định cần tránh cấp quyền ngoài mục đích.

| Đối tượng mới | Trạng thái cần xác định |
| --- | --- |
| Thành viên | Chỉ có tập quyền cơ bản được phê duyệt |
| Vai trò | Không ngầm nhận mọi quyền chưa liệt kê |
| Tenant | Không tự nhận quan hệ chia sẻ dữ liệu với tenant khác |
| Endpoint bảo vệ | Chỉ cho phép khi có chính sách phù hợp |
| Danh tính máy | Chỉ được cấp tài nguyên và thao tác cần thiết |
| Chức năng xuất dữ liệu | Không tự mở cho mọi vai trò nếu chưa có chính sách cấp quyền |

Một giao diện có thể được khai báo công khai nếu chức năng đòi hỏi. Danh sách và điều kiện công khai phải rõ ràng. Endpoint mới không nên tự kế thừa quyền công khai chỉ vì thiếu cấu hình.

Ẩn nút trên giao diện không thực hiện đầy đủ nghĩa vụ này. Máy chủ phải kiểm tra quyền trước khi trả dữ liệu hoặc tạo tác động.

### 5.3. Dữ liệu và tính công khai

Đối tượng chứa dữ liệu khách hàng không nên tự có quyền đọc công khai hoặc chia sẻ rộng.

Cần xét cả bản chính và các bản phát sinh:

- Tệp tải lên và tệp xuất.
- Bộ nhớ đệm và dữ liệu tạm.
- Bản sao lưu.
- Hàng đợi.
- Chỉ mục tìm kiếm.
- Dữ liệu lỗi và tracing.

Nếu sản phẩm có chức năng chia sẻ, hành động mở chia sẻ cần nêu rõ đối tượng, người nhận, phạm vi và thời hạn. Việc tạo tệp không nên âm thầm tương đương với công bố tệp.

Mã hóa là một phần của bảo vệ dữ liệu trong bối cảnh phù hợp. Nó không thay thế kiểm tra quyền đối với ứng dụng có thể giải mã.

### 5.4. Logging và dữ liệu lỗi

Mặc định nên có các sự kiện cần thiết cho vận hành và kiểm toán theo phạm vi, đồng thời không tự thu thập bí mật hoặc nội dung quá mức.

Cần quy định:

- Sự kiện nào được bật.
- Trường nào được phép và trường nào bị cấm.
- Mức chi tiết lỗi trả cho người dùng.
- Quyền truy xuất dữ liệu quan sát.
- Hành vi của thư viện tự thu thập request, header hoặc stack trace.
- Thời gian lưu theo loại dữ liệu và nguồn chính sách.

“Bật mọi log” không đồng nghĩa an toàn. “Tắt mọi log để khỏi lộ dữ liệu” cũng có thể làm mất nghĩa vụ truy vết. Cần chọn nội dung và quyền đúng mục đích.

### 5.5. Tích hợp và kết nối

Tích hợp mới không được tự mở rộng nguồn tin cậy hoặc quyền gọi.

Ví dụ:

- Nguồn phát hành danh tính được xác định bằng cấu hình tin cậy.
- Dữ liệu máy khách gửi không tự trở thành địa chỉ nguồn khóa hoặc đích gửi bí mật.
- Lỗi xác minh kết nối không làm hệ thống tự tắt kiểm tra chứng thư để thử lại.
- Danh tính gọi đối tác không tự nhận quyền trên mọi tài khoản hay mọi tenant.
- Webhook không được chấp nhận chỉ vì nội dung có trường “đã xác thực”.

Mức công khai của cổng và giao diện quản trị phải phù hợp môi trường triển khai. Không thể chỉ nhìn địa chỉ bind của tiến trình mà kết luận toàn bộ đường truy cập đã được bảo vệ; cần xét lớp định tuyến, proxy và chính sách mạng liên quan.

## 6. Cấu hình thiếu hoặc sai không được biến thành đường bỏ bảo vệ

Nhiều mặc định yếu không xuất phát từ một quyết định rõ ràng. Chúng xuất hiện do cách xử lý cấu hình:

- Không tìm thấy biến bật xác thực thì coi như tắt.
- Không tìm được khóa mã hóa thì lưu dữ liệu không mã hóa.
- Không gọi được dịch vụ quyền thì cho phép để tránh gián đoạn.
- Gặp lỗi kết nối thì bỏ xác minh danh tính đích.
- Một giá trị gõ sai bị bỏ qua rồi hệ thống chạy bằng chế độ mở.

Nếu trạng thái thiếu hoặc sai cấu hình có thể xảy ra, hành vi đó phải được đặc tả như một phần của yêu cầu.

### 6.1. Xác định quy tắc ưu tiên và kiểm tra

Khi có cấu hình từ tệp, biến môi trường, tham số chạy và hệ thống quản lý bí mật, cần biết nguồn nào có quyền ghi đè nguồn nào.

Một quy trình khởi động có thể gồm:

```text
Đọc các nguồn cấu hình được phép
  -> tổng hợp theo thứ tự ưu tiên đã công bố
  -> xác định hồ sơ triển khai
  -> kiểm tra kiểu, giá trị và quan hệ giữa các trường
  -> kiểm tra các ràng buộc bảo mật bắt buộc
  -> chỉ mở chức năng khi điều kiện tương ứng đã đạt
```

Không nên có một nguồn cấu hình ít được chú ý có thể vô hiệu hóa các ràng buộc bắt buộc mà không bị phát hiện.

Các lỗi cấu hình cần được thông báo đủ để xử lý nhưng không in giá trị bí mật. Có thể ghi tên trường hoặc mã lỗi thay vì chép toàn bộ cấu hình đã tổng hợp vào log.

### 6.2. Phân biệt giá trị mặc định với điều kiện bắt buộc

Ví dụ:

- Nếu thiếu mức chi tiết log không nhạy cảm, ứng dụng có thể chọn mức mặc định đã phê duyệt.
- Nếu thiếu thông tin cần để xác thực nguồn danh tính, ứng dụng không được tự chấp nhận mọi nguồn.
- Nếu thiếu quyền giải mã cần thiết, đường chức năng cần giải mã không được tự chuyển sang lưu hoặc trả dữ liệu không được bảo vệ.
- Nếu chưa có cấu hình chia sẻ tệp, tệp mới không được tự công khai.

Không phải mọi thiếu sót đều cần làm dừng toàn bộ tiến trình. Có thể không mở một chức năng phụ thuộc vào điều kiện đó, miễn các đường còn lại đáp ứng nghĩa vụ và trạng thái suy giảm được thể hiện đúng.

### 6.3. Mô tả chính sách bằng cấu trúc rõ ràng

Ví dụ dưới đây là **mô hình chính sách minh họa**, không phải cấu hình của một framework cụ thể:

```yaml
securityPolicy:
  protectedApi:
    authenticationRequired: true
    defaultAuthorizationDecision: DENY
    publicAccessRequiresExplicitDeclaration: true
  newDataObject:
    publicReadAllowed: false
    crossTenantAccessAllowed: false
  diagnostics:
    returnInternalDetailsToClient: false
    recordAuthenticationSecrets: false
  configuration:
    rejectUnknownSecurityOptions: true
    rejectInvalidProtectedProfile: true
```

Các tên trường chỉ giúp diễn đạt ý định. Hệ thống thật cần có cơ chế thực thi và kiểm thử tương ứng. Một tệp cấu hình đúng không chứng minh mã nguồn đã thực sự sử dụng từng trường.

Quyền truy cập giữa tenant, nếu là chức năng hợp lệ của sản phẩm, cần một chính sách cấp quyền rõ ràng thay vì sửa mặc định thành cho phép tất cả.

## 7. Chuyển nguyên tắc thành các yêu cầu có thể nghiệm thu

Mỗi yêu cầu nên có phạm vi, lý do từ rủi ro, chủ sở hữu, tiêu chí chấp nhận và bằng chứng. Các mã dưới đây chỉ là minh họa.

### 7.1. SR-DEF-AUTH-01 — Không có thông tin quản trị chung còn sử dụng được

Đối với cài đặt thuộc hồ sơ triển khai cần bảo vệ, hệ thống không được mở quyền quản trị bằng thông tin xác thực chung được đóng gói trong sản phẩm, cấu hình mẫu hoặc tài liệu.

Nếu chưa khởi tạo quản trị, hệ thống chỉ được cung cấp các hành vi khởi tạo đã được bảo vệ theo chính sách. Sau khi hoàn tất, thông tin hoặc quyền khởi tạo tạm thời phải không còn sử dụng được ngoài quy trình được phép.

**Tiêu chí chấp nhận:**

- Cài mới không cho đăng nhập quản trị bằng thông tin chung từ gói phân phối.
- Một chủ thể không có quyền khởi tạo không chiếm được vị trí quản trị đầu tiên.
- Sử dụng lại cơ chế khởi tạo sau khi hoàn tất không mở quyền ngoài chính sách.
- Bí mật khởi tạo không xuất hiện trong log hoặc phản hồi công khai.
- Người được phép vẫn có đường hoàn tất khởi tạo hợp lệ.

### 7.2. SR-DEF-AUTHZ-01 — Endpoint bảo vệ không tự mở khi thiếu chính sách

Với các API thuộc nhóm bảo vệ, máy chủ chỉ cho phép hành động khi có danh tính và quyết định quyền hợp lệ cho chủ thể, tenant, hành động và đối tượng tương ứng.

Nếu endpoint mới không có chính sách cho phép hoặc khai báo công khai hợp lệ, nó không được tự mở quyền truy cập.

**Tiêu chí chấp nhận:**

- Chủ thể đúng quyền sử dụng được chức năng.
- Chủ thể chưa xác thực hoặc sai quyền không nhận dữ liệu và không tạo tác động.
- Endpoint chưa có chính sách không kế thừa quyền công khai ngoài ý định.
- Sửa tenant hoặc đối tượng ở máy khách không làm mở rộng quyền.
- Việc thêm một vai trò mới không tự cấp mọi quyền chưa khai báo.

### 7.3. SR-DEF-DATA-01 — Tài nguyên mới có phạm vi truy cập hạn chế

Tệp xuất chứa dữ liệu hóa đơn phải được tạo trong phạm vi tenant và quyền đã xác định. Tạo tệp không tự cấp quyền đọc công khai hoặc quyền đọc cho tenant khác.

Chia sẻ ra ngoài phạm vi đó, nếu được hỗ trợ, phải là hành động được cấp quyền riêng với điều kiện rõ ràng.

**Tiêu chí chấp nhận:**

- Sau khi tạo, chủ thể được phép tải được tệp qua đường đã thiết kế.
- Truy cập ẩn danh hoặc từ tenant không được cấp quyền không lấy được nội dung.
- Không có đường tải trực tiếp bỏ qua nghĩa vụ mà thiết kế đã đặt ra.
- Thử lỗi khi cấp quyền hoặc lưu đối tượng không để lại tài nguyên công khai ngoài ý định.
- Tệp tạm và bản sao nằm trong phạm vi cũng đáp ứng chính sách liên quan.

### 7.4. SR-DEF-CONF-01 — Cấu hình không hợp lệ không làm yếu bảo vệ

Trong hồ sơ triển khai cần bảo vệ, thiếu hoặc sai các cấu hình bắt buộc cho xác thực, phân quyền và bảo vệ dữ liệu không được dẫn tới bỏ kiểm tra hoặc mở truy cập rộng.

Hệ thống phải từ chối khởi động phần chức năng liên quan hoặc duy trì trạng thái hạn chế đã đặc tả, đồng thời cung cấp chẩn đoán không chứa bí mật.

**Tiêu chí chấp nhận:**

- Bỏ từng cấu hình bắt buộc không tạo đường bỏ bảo vệ.
- Giá trị sai kiểu, không nhận diện hoặc mâu thuẫn được xử lý theo hợp đồng.
- Không có nguồn ghi đè nào được phép âm thầm vô hiệu hóa ràng buộc bắt buộc.
- Lỗi không làm ghi bí mật vào log.
- Chức năng không phụ thuộc vẫn hoạt động nếu thiết kế cho phép và không làm sai nghĩa vụ.

### 7.5. SR-DEF-LOG-01 — Quan sát an toàn ngay từ cấu hình ban đầu

Cài đặt ban đầu phải ghi các sự kiện bắt buộc theo phạm vi, dùng tập trường được phép và không ghi mật khẩu, token truy cập hoặc bí mật tích hợp.

Phản hồi lỗi cho máy khách không được chứa thông tin nội bộ bị cấm theo chính sách. Chi tiết phục vụ xử lý phải được chuyển tới kênh có quyền phù hợp.

**Tiêu chí chấp nhận:**

- Các sự kiện đã liệt kê xuất hiện khi thực hiện hành vi tương ứng.
- Dữ liệu thử chứa bí mật không bị lộ qua log, tracing, báo lỗi và phản hồi thuộc phạm vi.
- Thư viện tích hợp không tự thu thập trường bị cấm ở cấu hình ban đầu.
- Chủ thể không có quyền không truy xuất được dữ liệu quan sát nhạy cảm.

### 7.6. SR-DEF-LIFE-01 — Nâng cấp và phục hồi không tự hạ mức bảo vệ

Nâng cấp, di chuyển dữ liệu, đặt lại hoặc phục hồi phải giữ các ràng buộc bảo mật áp dụng. Không tự mở lại tài khoản, quyền chia sẻ hoặc đường truy cập đã bị vô hiệu hóa ngoài chính sách.

Cấu hình cũ không tương thích cần được xử lý rõ, không tự chuyển thành một chế độ dễ dãi.

**Tiêu chí chấp nhận:**

- Thiết lập hạn chế hợp lệ được bảo toàn hoặc chuyển đổi theo chính sách đã mô tả.
- Trường cấu hình mới có mặc định phù hợp thay vì tự mở tính năng.
- Khôi phục dữ liệu cũ có bước xác minh quyền và trạng thái nhạy cảm trước khi mở lại.
- Có thể phát hiện cấu hình không tương thích hoặc điều kiện phục hồi chưa đạt.
- Không báo hoàn tất nếu nghĩa vụ bắt buộc vẫn bị vi phạm.

## 8. Mặc định an toàn trong nâng cấp, phục hồi và thay đổi

### 8.1. Không ghi đè lựa chọn bảo vệ mạnh hơn

Giả sử cấu hình mới có giá trị mặc định hạn chế hơn cấu hình cũ. Khi nâng cấp, phải có quy tắc chuyển đổi và thông tin tác động phù hợp.

Cũng có trường hợp người vận hành đã đặt thiết lập mạnh hơn mặc định. Nâng cấp không nên tự đưa thiết lập đó về một giá trị yếu hơn chỉ vì viết lại tệp cấu hình từ mẫu.

Cần phân biệt:

- Áp dụng mặc định cho trường chưa tồn tại.
- Chuyển đổi trường cũ theo ngữ nghĩa tương đương.
- Giữ lựa chọn hợp lệ đang có.
- Từ chối hoặc yêu cầu xử lý cấu hình không còn đáp ứng ràng buộc.

Không thể giải quyết mọi trường hợp bằng quy tắc “luôn giữ nguyên” hoặc “luôn dùng mẫu mới”.

### 8.2. Phục hồi có thể làm sống lại trạng thái không còn hợp lệ

Một bản sao lưu cũ có thể chứa:

- Tài khoản chưa bị khóa tại thời điểm sao lưu.
- Quyền phê duyệt đã bị thu hồi sau đó.
- Tệp hoặc liên kết chia sẻ đã bị xóa.
- Bí mật hoặc cấu hình nguồn tin cậy đã thay đổi.

Khôi phục xong dữ liệu không tự đồng nghĩa trạng thái bảo vệ đã đúng.

Quy trình cần xác định nguồn cập nhật, bước đối soát và điều kiện mở lại chức năng. Nếu chưa xác minh được quyền, không nên tự sử dụng quyền cũ cho thao tác nhạy cảm.

### 8.3. Đặt lại cấu hình phải có phạm vi rõ

“Reset về mặc định” có thể tác động tới cả chức năng và bảo mật. Cần nêu:

- Reset phần nào?
- Có xóa hoặc thay đổi bí mật không?
- Tài khoản và quyền nào được giữ?
- Tính công khai của dữ liệu có thay đổi không?
- Có cần quay lại quy trình khởi tạo không?
- Trạng thái reset có thể được truy cập từ xa trước khi hoàn tất bảo vệ không?

Nếu mặc định ban đầu an toàn nhưng chức năng reset lại tạo một tài khoản chung, toàn bộ vòng đời chưa đáp ứng nguyên tắc.

## 9. Môi trường phát triển và ngoại lệ

### 9.1. Đường phát triển thuận tiện cần ranh giới rõ

Một sản phẩm có thể cung cấp chế độ phát triển cục bộ với dữ liệu giả và cách khởi tạo đơn giản. Chế độ đó cần được nhận diện rõ, không sử dụng dữ liệu thật và không vô tình trở thành cấu hình triển khai được bảo vệ.

Cần tránh:

- Cấu hình mẫu chứa bí mật dùng được ở nhiều môi trường.
- Chế độ phát triển tự được chọn khi thiếu cấu hình môi trường.
- Một cờ tiện lợi tắt đồng thời xác thực, phân quyền và kiểm tra kết nối mà không bị nhận diện.
- Artifact hoặc mẫu triển khai mang cấu hình phát triển sang môi trường thật.
- Dùng cùng thông tin xác thực có quyền cao cho phát triển và vận hành.

Không nên chỉ dựa vào tên tệp hoặc lời nhắc trong tài liệu. Quy trình triển khai và kiểm tra cấu hình cần thực thi ràng buộc tương ứng.

### 9.2. Thay đổi mặc định phải là hành động có chủ đích

Với thay đổi được chính sách cho phép, cần có:

- Chủ thể có quyền thực hiện.
- Phạm vi chức năng, dữ liệu và môi trường.
- Lý do và đánh giá tác động.
- Dấu vết thay đổi.
- Thời hạn hoặc điều kiện kết thúc nếu là tạm thời.
- Cách phát hiện cấu hình lệch khỏi đường bảo vệ đã chọn.

Nếu một yêu cầu bắt buộc không cho phép tắt phân quyền trong môi trường đó, một tùy chọn cấu hình không được tự biến thành quyền miễn nghĩa vụ.

Một ngoại lệ cần quyết định đúng thẩm quyền. Trạng thái kỹ thuật chưa đáp ứng vẫn phải được ghi đúng, không đổi thành đạt chỉ vì có người đồng ý tiếp tục.

## 10. Hành vi khi lỗi: giữ nghĩa vụ, giới hạn phạm vi suy giảm

Secure by default liên quan tới trạng thái ban đầu và lựa chọn ngầm định. Để bảo vệ được trong vận hành, cần kết hợp với hành vi an toàn khi điều kiện thay đổi.

| Tình huống lỗi | Hành vi cần tránh | Hướng đặc tả |
| --- | --- | --- |
| Không xác lập được quyền | Cho phép để giữ tốc độ phản hồi | Từ chối thao tác cần quyền; mô tả đường còn có thể phục vụ hợp lệ |
| Không có khóa cần thiết | Ghi dữ liệu nhạy cảm không mã hóa | Không thực hiện đường cần bảo vệ đó nếu chưa có cách hợp lệ |
| Không xác minh được kết nối | Tự tắt kiểm tra danh tính đích | Giữ yêu cầu xác minh, xử lý lỗi theo phạm vi |
| Kho nhận log gián đoạn | Âm thầm bỏ sự kiện bắt buộc | Dùng cơ chế lưu/đệm đáp ứng nghĩa vụ hoặc hạn chế thao tác liên quan |
| Nhà cung cấp thanh toán timeout | Coi là chưa xử lý rồi tạo giao dịch mới | Giữ kết quả chưa xác định và đối soát theo thiết kế |
| Cấu hình nâng cấp không hợp lệ | Chạy với chế độ mở để tương thích | Từ chối hoặc hạn chế phần chưa đáp ứng ràng buộc |

Mỗi hàng cần được đặc tả cho hệ thống thật. Không phải mọi lỗi đều cần dừng mọi chức năng. Cũng không thể dùng nhu cầu sẵn sàng để tự bỏ nghĩa vụ bảo mật.

### Logging cần một quyết định cụ thể

Nếu một thay đổi quyền bắt buộc có dấu vết lưu bền vững, “kho log hỏng thì bỏ log” không đáp ứng yêu cầu.

Có thể thiết kế lưu sự kiện cùng thay đổi hoặc một cơ chế khác có khả năng đối soát phù hợp. Nếu dùng bộ đệm, cần giới hạn, bảo vệ dữ liệu và hành vi khi đầy. “Có buffer” chưa đủ nếu mất tiến trình sẽ mất toàn bộ dấu vết bắt buộc.

### Phụ thuộc có thể thay đổi mức phục vụ nhưng không đổi chính sách ngầm

Ví dụ, khi dịch vụ danh tính gián đoạn, một hệ thống có thể vẫn xác minh được phiên bằng dữ liệu đã lưu hợp lệ; hệ thống khác cần kiểm tra trực tuyến.

Cần đặc tả độ cũ được phép, điều kiện thu hồi và giới hạn chức năng. Không có quy tắc chung rằng mọi phiên đều phải được chấp nhận hoặc mọi chức năng đều phải dừng.

## 11. Kiểm chứng mặc định an toàn

### 11.1. Dùng cài đặt sạch và đường sử dụng được công bố

Nếu chỉ kiểm tra một môi trường đã được chuyên gia hardening thủ công, chưa biết sản phẩm có an toàn theo mặc định hay không.

Phép kiểm chứng cần bắt đầu từ gói, mẫu triển khai và quy trình được cung cấp cho người sử dụng. Cung cấp đầu vào bắt buộc qua đường đã thiết kế, chẳng hạn bí mật triển khai, nhưng không tự thêm các bước bảo vệ không được công bố rồi coi chúng là mặc định.

Cần ghi lại:

- Phiên bản sản phẩm và mẫu triển khai.
- Hồ sơ môi trường.
- Đầu vào được cung cấp.
- Cấu hình hiệu lực, với giá trị bí mật được bảo vệ.
- Trạng thái dữ liệu và quyền ban đầu.
- Các thao tác để hoàn tất khởi tạo.
- Kết quả quan sát và giới hạn phép thử.

### 11.2. Ma trận kiểm chứng minh họa

| Tình huống | Điều cần quan sát |
| --- | --- |
| Cài mới chưa hoàn tất khởi tạo | Không có quyền quản trị công khai hoặc thông tin chung dùng được |
| Hoàn tất khởi tạo hợp lệ | Người có quyền sử dụng được; đường khởi tạo tạm thời bị giới hạn đúng |
| Tạo thành viên | Chỉ nhận tập quyền mặc định đã phê duyệt |
| Tạo tenant mới | Không đọc được dữ liệu tenant khác |
| Tạo tệp xuất | Không có quyền đọc công khai ngoài chính sách |
| Thêm endpoint chưa có chính sách | Không tự mở dữ liệu hoặc tác động |
| Bỏ một cấu hình bắt buộc | Không rơi vào chế độ bỏ kiểm tra |
| Đặt cấu hình mâu thuẫn từ nhiều nguồn | Áp dụng quy tắc ưu tiên và ràng buộc đã mô tả |
| Kích hoạt lỗi với dữ liệu chứa token thử | Không lộ token qua các đầu ra thuộc phạm vi |
| Nâng cấp từ cấu hình cũ | Không làm mất thiết lập bảo vệ hợp lệ hoặc mở tính năng ngoài ý định |
| Phục hồi bản sao lưu cũ | Có bước xác minh quyền và trạng thái trước khi mở lại |
| Đặt lại cấu hình | Không tạo lại tài khoản chung hoặc quyền công khai |
| Hết hạn quyền hoặc ngoại lệ tạm thời | Không tiếp tục duy trì ngoài điều kiện đã quyết định |

Các trường hợp trên là hướng xây dựng phép thử, không phải kết quả đã được thực hiện cho một hệ thống cụ thể.

### 11.3. Kiểm tra cả chức năng hợp lệ

Một hệ thống từ chối mọi yêu cầu có thể vượt qua các phép thử chỉ kiểm tra “không được truy cập”.

Cần có bằng chứng rằng:

- Người được phép có thể khởi tạo và sử dụng sản phẩm.
- Thành viên cơ bản làm được nghiệp vụ được cấp.
- Người có quyền phê duyệt thực hiện được đúng hành động.
- Tệp được tải qua đường hợp lệ.
- Chức năng công khai được chủ đích thiết kế vẫn hoạt động mà không làm lộ phần bảo vệ.

Mục tiêu là thực thi đúng chính sách. Khả dụng và bảo vệ cần được thiết kế cùng nhau.

### 11.4. Đánh giá từ hành vi, không chỉ từ cờ cấu hình

Tệp cấu hình có `authenticationRequired: true` chưa đủ nếu một đường xuất dữ liệu bỏ qua bộ lọc xác thực.

Cần kết hợp rà soát điểm thực thi với kiểm thử tích hợp và quan sát kết quả. Với quyền, kiểm tra tác động dữ liệu; với logging, kiểm tra dữ liệu thực sự được ghi; với phục hồi, kiểm tra điều kiện mở lại.

Các kiểm tra tĩnh có thể phát hiện một phần sai cấu hình, nhưng không thay thế mọi bằng chứng hành vi.

## 12. Liên kết với kiến trúc và vòng đời phát triển

| Giai đoạn | Quyết định cần thực hiện | Bằng chứng cần chuẩn bị |
| --- | --- | --- |
| Phân tích | Tài sản nào cần được bảo vệ trong trạng thái ban đầu và khi thay đổi? | Mô hình đe dọa, danh sách trạng thái và giả định |
| Thiết kế | Điểm nào thực thi mặc định, điểm nào kiểm tra ràng buộc? | Chính sách quyền, sơ đồ khởi tạo, quy tắc cấu hình |
| Triển khai | Endpoint, vai trò, dữ liệu mới nhận trạng thái nào? | Cơ chế dùng chung và phép thử cho đường mới |
| Đóng gói | Mẫu cấu hình, tài liệu và artifact có cùng ý định không? | Kiểm chứng gói phân phối và cài đặt sạch |
| Phát hành | Các hồ sơ môi trường đáp ứng điều kiện nào? | Kết quả kiểm chứng và phần chưa đạt |
| Vận hành | Cấu hình có bị lệch, quyền có tự mở rộng không? | Theo dõi thay đổi, đối soát và đầu mối xử lý |
| Nâng cấp/phục hồi | Trạng thái cũ được chuyển đổi ra sao? | Kiểm thử chuyển đổi và diễn tập phục hồi |

Cơ chế dùng chung giúp giảm việc mỗi nhóm phải nhớ tự thêm bảo vệ. Ví dụ, một lớp thực thi chính sách có thể từ chối endpoint bảo vệ chưa có khai báo. Nhưng vẫn phải kiểm tra các đường không đi qua cơ chế đó như tác vụ nền, tệp xuất hoặc giao diện quản trị.

Một thay đổi nhỏ cũng có thể làm đổi mặc định: thêm vai trò, thêm trường cấu hình hoặc đổi thứ tự ưu tiên nguồn cấu hình. Việc rà soát cần theo tác động tới nghĩa vụ, không chỉ theo số dòng mã.

### Chỉ số theo dõi cần phản ánh đúng điều được đo

“Số endpoint đã khai báo chính sách” giúp quản lý độ bao phủ, nhưng không chứng minh chính sách đúng.

“Không có vi phạm quan sát được” không chứng minh không có đường bỏ qua nếu hệ thống không quan sát đường đó.

Nên liên kết chỉ số với yêu cầu cụ thể và giữ các trạng thái: đã đặc tả, đã triển khai, đã kiểm chứng, chưa đủ bằng chứng hoặc có ngoại lệ. Không dùng một tỷ lệ tổng hợp để che một đường truy cập sai quyền.

## 13. Những nhầm lẫn thường gặp

| Cách nghĩ | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Có tính năng bảo mật là mặc định an toàn” | Tính năng có thể đang tắt hoặc không áp dụng cho mọi đường cần bảo vệ | Kiểm chứng trạng thái ban đầu và phạm vi thực thi |
| “Người dùng sẽ đọc hướng dẫn rồi tự bật” | Bảo vệ phụ thuộc vào bước thủ công dễ bỏ sót | Chọn mặc định phù hợp và hướng dẫn phần tùy chỉnh thực sự cần thiết |
| “Default deny nghĩa là đóng hết mọi API” | Không phân biệt chức năng công khai có chủ đích và chức năng bảo vệ | Khai báo chính sách cho từng nhóm giao diện |
| “Tài khoản mới nên là admin để dễ dùng” | Tự cấp quyền vượt mục đích | Cấp tập quyền cơ bản và có đường cấp quyền nhạy cảm riêng |
| “Thiếu secret thì dùng một giá trị mẫu” | Có thể tạo bí mật chung hoặc dự đoán được | Không mở chức năng cần bí mật khi chưa có đầu vào hợp lệ |
| “Bật tất cả log là an toàn” | Có thể lộ dữ liệu và bí mật | Chọn sự kiện, trường và quyền theo mục đích |
| “Khôi phục được dữ liệu là có thể mở dịch vụ” | Quyền, bí mật và chia sẻ có thể đã cũ | Kiểm tra điều kiện bảo vệ trước khi mở lại |
| “Cờ cấu hình đúng nên không cần thử hành vi” | Mã có thể bỏ qua hoặc diễn giải khác | Kiểm tra điểm thực thi và kết quả thực tế |
| “Chế độ phát triển không liên quan sản xuất” | Mẫu hoặc artifact có thể được đưa sang môi trường khác | Nhận diện hồ sơ, kiểm tra triển khai và tránh bí mật chung |
| “Mặc định đúng rồi nên cho phép tắt mọi ràng buộc” | Cấu hình lại dễ làm mất nghĩa vụ bắt buộc | Phân biệt tùy chọn với điều kiện không được hạ thấp |

## 14. Bài tập vận dụng

### Bài 1: Phân biệt khả năng và mặc định

Sản phẩm hỗ trợ phân quyền theo vai trò, nhưng mọi thành viên mới đều được gán vai trò quản trị.

Sản phẩm đã an toàn theo mặc định về quyền chưa?

**Gợi ý:** chưa. Có cơ chế phân quyền không đủ khi trạng thái ban đầu cấp quyền quá rộng. Cần xác định tập quyền cơ bản và đường cấp quyền quản trị có thẩm quyền.

### Bài 2: Thiếu cấu hình

Khi không có địa chỉ nguồn khóa xác minh, ứng dụng đọc địa chỉ đó từ thông tin do máy khách gửi rồi chấp nhận khóa tương ứng.

Vấn đề nằm ở đâu?

**Gợi ý:** dữ liệu không tin cậy đang tự quyết định nguồn tin cậy. Cần nguồn cấu hình đã được chấp thuận và hành vi hạn chế khi thiếu điều kiện xác minh, không tự mở rộng nguồn.

### Bài 3: Tệp mới và tính công khai

Chức năng xuất tạo tệp trong một nơi lưu có quyền đọc công khai. Giao diện ứng dụng chỉ hiển thị liên kết cho người có quyền.

Ẩn liên kết có đủ bảo vệ tệp không?

**Gợi ý:** không. Cần kiểm soát đường tải và quyền thực tế của đối tượng. Tạo tệp không được tự công khai ngoài chính sách chỉ vì giao diện đã hạn chế hiển thị.

### Bài 4: Nâng cấp và cấu hình mạnh hơn

Một tổ chức đã tắt chia sẻ ra ngoài. Bản nâng cấp viết lại cấu hình mẫu và bật chia sẻ.

Có thể nói cài mới vẫn an toàn nên không có vấn đề về mặc định không?

**Gợi ý:** không. Vòng đời còn gồm nâng cấp. Cần quy tắc bảo toàn hoặc chuyển đổi thiết lập và không hạ mức bảo vệ hợp lệ ngoài chính sách.

### Bài 5: Phục hồi quyền cũ

Bản sao lưu chứa quyền phê duyệt của U, nhưng quyền đã bị thu hồi sau thời điểm sao lưu. Sau phục hồi, U lại phê duyệt được.

**Gợi ý:** quy trình đang dùng trạng thái quyền cũ ngoài điều kiện đã đặt ra. Cần đối soát hoặc cập nhật quyền trước khi mở lại thao tác nhạy cảm, cùng tiêu chí phục hồi cụ thể.

## 15. Các câu hỏi trước khi chốt mục tiêu

- Trạng thái ban đầu của tài khoản, tenant, endpoint và dữ liệu mới đã rõ chưa?
- Các quyền nhạy cảm có cần hành động cấp quyền có chủ đích không?
- Cài đặt và khởi tạo có tránh thông tin xác thực chung không?
- Thiếu hoặc sai cấu hình có giữ nghĩa vụ bảo vệ không?
- Có tách tùy chọn điều chỉnh được khỏi ràng buộc bắt buộc không?
- Logging mặc định có đủ sự kiện cần thiết và loại bỏ bí mật không?
- Mẫu cấu hình, tài liệu và gói triển khai có nhất quán với yêu cầu không?
- Nâng cấp, reset và phục hồi có thể làm yếu quyền hoặc tính công khai không?
- Người được phép có đường sử dụng hợp lệ mà không phải tự tháo bỏ bảo vệ không?
- Bằng chứng đã kiểm tra hành vi thực tế trong đúng hồ sơ môi trường chưa?

Secure by default có giá trị khi đường sử dụng bình thường đã đưa hệ thống vào trạng thái được bảo vệ, các lựa chọn chưa được khai báo không tự mở quyền và những thay đổi trong vòng đời không âm thầm làm mất nghĩa vụ. Yêu cầu cụ thể cùng phép kiểm chứng giúp nguyên tắc này trở thành thuộc tính vận hành của sản phẩm.
