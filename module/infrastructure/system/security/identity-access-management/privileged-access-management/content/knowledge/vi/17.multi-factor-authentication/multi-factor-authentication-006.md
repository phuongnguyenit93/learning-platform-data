# Reauthentication theo rủi ro trong PAM

## Mục tiêu bài học

Một quản trị viên đã đăng nhập bằng MFA không có nghĩa mọi thao tác đặc quyền của họ trong nhiều giờ sau đều có cùng mức độ tin cậy. Thiết bị có thể thay đổi trạng thái, phiên có thể bị chiếm dụng, hoặc công việc chuyển từ đọc thông tin sang tiết lộ credential quản trị sản xuất.

**Reauthentication theo rủi ro** là việc yêu cầu bằng chứng xác thực mới khi độ tin cậy hiện tại không còn đáp ứng yêu cầu của một phiên hoặc hành động. Trong Privileged Access Management (PAM), cơ chế này giúp kiểm soát thời điểm kích hoạt quyền JIT, truy cập vault, mở phiên quản trị và thực hiện thao tác nhạy cảm.

Sau bài học, bạn có thể:

- Phân biệt xác thực lại, tăng cường xác thực, làm mới token và cấp quyền.
- Chọn tín hiệu rủi ro và điểm thực thi phù hợp với hành động đặc quyền.
- Thiết kế yêu cầu về độ mới và mức bảo đảm của bằng chứng xác thực.
- Ràng buộc kết quả xác thực lại với đúng người, phiên, tài sản và thao tác.
- Xử lý rủi ro thay đổi, lỗi tích hợp, phiên đang hoạt động và thu hồi quyền.
- Kiểm chứng cơ chế và lưu bằng chứng mà không thu thập bí mật xác thực.

Các thời hạn, tên trường dữ liệu và chính sách trong bài là minh họa. Chúng không phải giá trị mặc định của một sản phẩm hay yêu cầu áp dụng chung cho mọi tổ chức.

## 1. Vì sao MFA ở đầu phiên chưa đủ?

Giả sử quản trị viên đăng nhập vào cổng PAM lúc 08:00 bằng MFA, đọc báo cáo trong hai giờ, rồi lúc 10:00 yêu cầu hiển thị mật khẩu tài khoản quản trị cơ sở dữ liệu sản xuất.

Giữa hai thời điểm, có thể xảy ra:

- Người dùng rời máy nhưng phiên vẫn mở.
- Trình duyệt hoặc thiết bị bị điều khiển trái phép.
- Token hoặc cookie phiên bị đánh cắp.
- Thiết bị mất điều kiện bảo mật.
- Người dùng chuyển sang một hành động có tác động lớn hơn nhiều.
- Quyền, phê duyệt hoặc trạng thái danh tính đã thay đổi.

Một phiên hợp lệ lúc 08:00 là bằng chứng về trạng thái khi đó, không phải lời bảo đảm không giới hạn cho mọi hành động về sau.

Tuy nhiên, yêu cầu MFA lặp lại cho mọi lần bấm cũng không tạo ra kiểm soát tốt. Nó có thể gây gián đoạn, làm người dùng quen chấp thuận thông báo và vẫn không giải quyết được thiết bị đã bị xâm nhập.

Mục tiêu là đưa ra quyết định phù hợp tại điểm sử dụng quyền: tiếp tục với bằng chứng hiện có, yêu cầu xác thực mới, yêu cầu phương thức mạnh hơn, hoặc chặn và xử lý sự cố.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi được giải quyết |
|---|---|
| Xác thực ban đầu | Ai đang tạo phiên đăng nhập? |
| Reauthentication: xác thực lại | Có bằng chứng mới đủ tin cậy rằng người đó đang tiếp tục yêu cầu thao tác không? |
| Step-up authentication: tăng cường xác thực | Bằng chứng có đáp ứng mức bảo đảm cao hơn mà hành động yêu cầu không? |
| Làm mới token hoặc kéo dài phiên | Hệ thống có thể tiếp tục biểu diễn phiên theo cơ chế vòng đời đã thiết kế không? |
| Authorization: quyết định cấp phép | Người này có được thực hiện hành động đó trên tài sản này, lúc này không? |
| Phê duyệt công việc | Nhu cầu và phạm vi có được người có thẩm quyền chấp thuận không? |

Xác thực lại có thể dùng cùng phương thức nhưng tạo bằng chứng mới. Tăng cường xác thực có thể yêu cầu phương thức đáp ứng mức bảo đảm cao hơn. Hai việc có thể diễn ra cùng lúc, nhưng không đồng nghĩa.

Làm mới token không nhất thiết tạo một lần xác thực tương tác mới. Một token mới được phát hành từ phiên SSO cũ có thể vẫn dựa trên lần xác thực ban đầu cách đó nhiều giờ.

Xác thực lại thành công cũng không mở rộng quyền. Một quản trị viên chứng minh được danh tính vẫn phải đáp ứng least privilege, phê duyệt, cửa sổ JIT và những điều kiện truy cập khác.

### Ví dụ ngắn

- Người dùng vừa xác thực mạnh nhưng yêu cầu một tài sản không được duyệt: **từ chối quyền**, không chỉ hỏi MFA thêm lần nữa.
- Người dùng có quyền hợp lệ nhưng bằng chứng xác thực quá cũ cho checkout bí mật: **yêu cầu xác thực lại**, rồi kiểm tra quyền một lần nữa trước khi tiết lộ.
- Thiết bị có tín hiệu xâm nhập rõ ràng: **chặn hoặc cô lập theo chính sách**, không coi một lần MFA thành công là cách xóa tín hiệu đó.

## 3. Mô hình tin cậy: người, phiên, thiết bị và hành động

Quyết định không nên chỉ dựa vào việc tài khoản đã bật MFA. Cần kết hợp các chiều liên quan:

| Chiều | Câu hỏi cần đánh giá |
|---|---|
| Người dùng | Danh tính còn hoạt động, phương thức xác thực và tình trạng tài khoản có phù hợp không? |
| Bằng chứng xác thực | Phương thức nào đã được xác minh và lần xác thực thực sự xảy ra khi nào? |
| Phiên | Phiên hiện tại có bị thu hồi, đổi chủ thể hoặc xuất hiện dấu hiệu bị chiếm dụng không? |
| Thiết bị | Thiết bị có đáp ứng điều kiện quản trị, kiểm soát và sức khỏe bảo mật không? |
| Ngữ cảnh | Nguồn kết nối, thay đổi môi trường và hành vi có cần đánh giá thêm không? |
| Hành động | Người dùng sắp làm gì, trên tài sản nào và tác động có thể lớn đến đâu? |
| Quyền và phê duyệt | Grant, ticket, tài sản và cửa sổ sử dụng còn hợp lệ không? |

Không phải triển khai nào cũng có đủ mọi tín hiệu. Chính sách phải nêu rõ tín hiệu nào bắt buộc, tín hiệu nào hỗ trợ và cách xử lý khi không có dữ liệu.

### 3.1. Những tín hiệu thường dùng

Có thể xem xét:

- Khoảng thời gian từ lần xác thực đáp ứng yêu cầu gần nhất.
- Thay đổi thiết bị, trình duyệt hoặc trạng thái quản lý thiết bị.
- Tín hiệu phát hiện sự cố tài khoản, phiên hoặc endpoint.
- Thay đổi nguồn mạng hoặc vị trí ước lượng.
- Truy cập loại tài sản nhạy cảm hơn thông thường.
- Chuyển từ sử dụng phiên qua proxy sang nhận trực tiếp credential.
- Thay đổi quyền, phê duyệt hoặc trạng thái danh tính.
- Mẫu thử xác thực thất bại hoặc yêu cầu xác thực bất thường.

Địa chỉ IP và vị trí không đủ để khẳng định danh tính. NAT, VPN, nhà mạng di động hoặc proxy doanh nghiệp có thể làm nhiều người dùng chung địa chỉ hoặc làm vị trí thay đổi.

Tín hiệu thiết bị cũng cần có nguồn và độ mới. Một bản ghi “đạt yêu cầu” từ lâu không thể thay thế trạng thái hiện tại nếu chính sách yêu cầu đánh giá mới.

### 3.2. Mức độ nhạy cảm của hành động

Trong PAM, các hành động có thể cần yêu cầu khác nhau:

| Hành động minh họa | Điểm cần cân nhắc |
|---|---|
| Xem danh mục tài sản được phép | Độ nhạy của thông tin hiển thị và điều kiện phiên |
| Mở phiên đọc log được phê duyệt | Độ mới xác thực, tài sản và vai trò hạn chế |
| Kích hoạt quyền quản trị sản xuất | Mức bảo đảm, JIT, phê duyệt và thiết bị |
| Hiển thị hoặc xuất credential | Khả năng bí mật bị sao chép và sử dụng ngoài phiên |
| Thay đổi chính sách PAM hoặc danh tính người phê duyệt | Tác động đến chính cơ chế kiểm soát |
| Thực hiện thao tác phá hủy hoặc thay đổi diện rộng | Giới hạn quyền, phê duyệt và kiểm soát thao tác riêng |

Mức rủi ro không chỉ do tên hành động. Đọc log có thể tiết lộ dữ liệu nhạy cảm; một vai trò mang tên “support” có thể có quyền rộng. Cần hiểu ánh xạ quyền và dữ liệu thực tế.

## 4. Thiết kế chính sách: tiếp tục, xác thực lại, tăng cường hay chặn

Một mô hình quyết định tham khảo:

```text
Yêu cầu hành động đặc quyền
           |
           v
Kiểm tra danh tính, quyền, phê duyệt và điều kiện bắt buộc
           |
           +--> Không hợp lệ / điều kiện cấm --> Từ chối và xử lý phù hợp
           |
           v
Đánh giá rủi ro và bằng chứng xác thực
           |
           +--> Đủ độ mới và mức bảo đảm --> Cho phép phạm vi đã kiểm tra
           |
           +--> Thiếu độ mới --> Xác thực lại
           |
           +--> Thiếu mức bảo đảm --> Tăng cường bằng phương thức phù hợp
           |
           +--> Không thể đạt điều kiện --> Từ chối / đường xử lý được thiết kế
```

Sau xác thực lại hoặc tăng cường, cần kiểm tra lại các điều kiện có thể đã thay đổi trước khi thực thi hành động.

### 4.1. Không để điểm số xóa điều kiện cấm

Có thể dùng mô hình rủi ro hoặc tập quy tắc để hỗ trợ quyết định. Tuy nhiên, điều kiện cấm như tài khoản bị khóa, grant hết hạn hoặc thiết bị được xác định bị xâm nhập không nên được “trung hòa” bởi các tín hiệu thuận lợi khác.

Nếu dùng điểm số, cần biết nguồn tín hiệu, cách cập nhật và giới hạn của mô hình. Không cần hiển thị một con số có vẻ chính xác nếu tổ chức không giải thích được nó dẫn đến hành động nào.

### 4.2. Ví dụ chính sách mô tả

```yaml
action_policy:
  action: reveal_production_credential
  prerequisites:
    active_identity: true
    valid_approval: true
    active_jit_grant: true
    managed_device_required: true
    confirmed_compromise: deny
  authentication:
    required_assurance: phishing_resistant_mfa
    maximum_authentication_age_seconds: 120
  result_scope:
    bind_to_subject: true
    bind_to_session: true
    bind_to_credential_reference: true
    bind_to_action: true
    single_use: true
  final_check:
    revalidate_authorization: true
    revalidate_risk_conditions: true
```

Đây là mô tả ý định chính sách, không phải schema có thể nạp vào một sản phẩm. Ngưỡng 120 giây là giả định của ví dụ, không phải một chuẩn áp dụng chung.

Nếu không có phương thức hoặc đường thực thi đáp ứng chính sách, cần xử lý rõ rằng hành động chưa thể được phép. Không tự hạ mức yêu cầu xuống một phương thức khác chỉ vì tích hợp chưa hỗ trợ.

## 5. Độ mới xác thực và mức bảo đảm

### 5.1. Đo tuổi của lần xác thực thực sự

Tuổi xác thực có thể được mô tả như sau:

```text
authentication_age =
    thời điểm quyết định tại máy chủ
    - thời điểm xác thực đáng tin cậy đáp ứng phương thức yêu cầu
```

Thời điểm phát hành access token, thời điểm làm mới cookie hoặc thời điểm người dùng tải lại trang không tự là thời điểm xác thực mới.

Trong tích hợp với IdP, PAM cần một hợp đồng rõ ràng về ý nghĩa của bằng chứng: chủ thể nào đã xác thực, khi nào, bằng phương thức nào và kết quả dành cho bên nhận nào. PAM phải kiểm tra bằng chứng từ nguồn tin cậy thay vì nhận một giá trị do trình duyệt tự gửi.

Nếu IdP trả về phiên SSO cũ mà không có bằng chứng đủ mới, yêu cầu xác thực lại chưa được đáp ứng, dù người dùng đã quay về giao diện PAM thành công.

### 5.2. Mức bảo đảm phải phù hợp với phương thức

Không nên chỉ kiểm tra một nhãn “MFA đã bật”. Cần biết lần xác thực liên quan đã dùng phương thức được chấp nhận hay chưa.

Phương thức chống phishing có thể giảm nguy cơ bằng chứng xác thực bị sử dụng tại một dịch vụ giả mạo. Tuy nhiên:

- Không phải mọi hình thức MFA đều có cùng khả năng chống phishing.
- Một phương thức mạnh không làm thiết bị đang bị điều khiển trở nên an toàn.
- Bằng chứng xác thực cho dịch vụ không mặc nhiên là sự chấp thuận cho một thao tác nghiệp vụ cụ thể.
- Khả năng ràng buộc người dùng, thiết bị và phiên phụ thuộc phương thức cùng cách tích hợp.

Các biện pháp như xác nhận số trong thông báo có thể giảm một số lỗi chấp thuận, nhưng không nên được tự động xem là tương đương mọi phương thức chống phishing.

Tổ chức cần ánh xạ các phương thức được IdP xác minh sang yêu cầu của chính sách PAM. Không suy ra mức bảo đảm từ tên hiển thị tùy ý hoặc cờ do ứng dụng khách cung cấp.

### 5.3. Xác thực gần đây không có hiệu lực toàn cục

Người dùng vừa xác thực để mở phiên đọc log không nhất thiết đã đáp ứng chính sách tiết lộ mật khẩu quản trị hoặc thay đổi cấu hình vault.

Có thể tái sử dụng bằng chứng xác thực trong một phạm vi và khoảng thời gian đã định nghĩa để tránh gián đoạn không cần thiết. Quyết định cho phép hành động vẫn phải được đánh giá riêng.

Không lưu một cờ chung `mfa_ok=true` vô thời hạn rồi áp dụng cho tất cả tài sản, phiên và hành động.

## 6. Ràng buộc xác thực lại với đúng hành động

Nếu xác thực lại tách rời thao tác đang chờ, có thể xảy ra tình huống người dùng xác thực cho một hành động nhưng hệ thống thực hiện hành động khác.

Một luồng tham khảo:

1. Người dùng yêu cầu một hành động cụ thể.
2. Máy chủ đánh giá quyền và rủi ro, xác định cần xác thực lại.
3. Máy chủ tạo ngữ cảnh chờ có thời hạn với người dùng, phiên, tài sản và hành động.
4. Người dùng được chuyển đến cơ chế xác thực đáng tin cậy.
5. Máy chủ kiểm tra kết quả xác thực và liên kết về đúng ngữ cảnh chờ.
6. Máy chủ đánh giá lại quyền, phê duyệt và rủi ro hiện hành.
7. Chỉ thực thi hành động đã ràng buộc, trong phạm vi và thời hạn cho phép.
8. Ghi nhận kết quả, tiêu thụ quyền sử dụng một lần nếu chính sách yêu cầu.

Ngữ cảnh chờ nên được quản lý phía máy chủ hoặc bảo vệ bằng cơ chế tương đương. Không tin cậy tài sản, vai trò hoặc hành động chỉ vì chúng nằm trong tham số trả về từ trình duyệt.

### 6.1. Những ràng buộc cần có

| Ràng buộc | Mục đích |
|---|---|
| Đúng chủ thể | Kết quả của người A không dùng cho người B |
| Đúng phiên | Giảm việc chuyển kết quả sang một phiên khác không được phép |
| Đúng tài sản và hành động | Không dùng xác thực đọc log để tiết lộ một bí mật khác |
| Đúng phạm vi và phiên bản yêu cầu | Không áp dụng cho nội dung đã bị sửa |
| Thời hạn ngắn theo chính sách | Hạn chế sử dụng một kết quả cũ |
| Mã tương quan hoặc thử thách duy nhất | Gắn phản hồi về lần yêu cầu đang chờ |
| Chống sử dụng lại khi cần | Không thực hiện lại một hành động dùng một lần |
| Đúng bên phát hành và bên nhận | Không chấp nhận bằng chứng dành cho một dịch vụ khác |

Các ràng buộc trên cần được thực thi theo giao thức và thư viện phù hợp của hệ thống. Không tự thiết kế thuật toán mật mã chỉ để hiện thực một luồng xác thực lại.

Nếu cần sự chấp thuận có nội dung giao dịch, phải có thiết kế hiển thị và ràng buộc nội dung tương ứng. Một lần chạm vào thiết bị xác thực không tự chứng minh người dùng đã nhìn thấy và đồng ý với toàn bộ lệnh quản trị phía sau.

### 6.2. Kiểm tra cuối trước khi thực thi

Trong lúc người dùng xác thực, ticket có thể bị hủy, grant hết hạn hoặc thiết bị xuất hiện cảnh báo. Vì vậy kết quả xác thực thành công chỉ là một đầu vào của quyết định cuối.

Ví dụ:

```text
Kết quả xác thực hợp lệ?
  -> Ngữ cảnh chờ đúng người, phiên và hành động?
  -> Kết quả còn mới và đạt mức bảo đảm?
  -> Yêu cầu, grant, phê duyệt và điều kiện thiết bị còn hợp lệ?
  -> Không có điều kiện cấm mới?
  -> Thực thi đúng hành động và ghi kết quả.
```

Nếu điều kiện đã thay đổi, từ chối hoặc yêu cầu lại theo chính sách. Không “hoàn tất cho người dùng” bằng cách bỏ qua kiểm tra cuối vì họ vừa trải qua một bước MFA.

### 6.3. Hành động bất đồng bộ và lỗi từng phần

Một tác vụ cấp quyền có thể được đưa vào hàng đợi sau xác thực lại nhưng chỉ chạy vài phút sau. Tác vụ cần kiểm tra các điều kiện còn hiệu lực khi thực sự cấp quyền.

Không để hàng đợi trở thành cách kéo dài vô hạn một kết quả xác thực ngắn hạn. Nếu cần cho phép một tác vụ cụ thể chạy sau, phạm vi và thời hạn thực thi phải được xác định rõ.

Cần xử lý phản hồi trùng, mất kết nối và thử lại sao cho không tạo thêm grant hoặc tiết lộ lại bí mật ngoài ý định. Việc tiêu thụ kết quả dùng một lần và thao tác tại hệ thống khác có thể không nằm trong một giao dịch nguyên tử; cần cơ chế trạng thái và đối soát phù hợp.

## 7. Điểm thực thi trong kiến trúc PAM

Xác thực lại cần được kiểm tra tại nơi có thể kiểm soát hành động thực tế, không chỉ nơi hiển thị thông báo.

| Điểm thực thi | Ví dụ kiểm soát |
|---|---|
| API hoặc dịch vụ vault | Kiểm tra trước khi hiển thị hoặc cấp credential |
| Cơ chế cấp quyền JIT | Kiểm tra trước khi tạo grant hoặc thêm vai trò tạm |
| Session broker/gateway | Kiểm tra trước khi mở hoặc nâng mức phiên |
| Cổng quản trị PAM | Kiểm tra trước thay đổi cấu hình, vai trò hoặc chính sách |
| Endpoint quản trị hạn chế | Kiểm tra trước những hành động đặc biệt nếu kiến trúc hỗ trợ |

Nếu giao diện hỏi MFA nhưng API có thể được gọi trực tiếp mà không kiểm tra tương đương, kiểm soát có thể bị bỏ qua.

Một hệ thống đích không tích hợp không tự hiểu rằng phiên PAM cần xác thực lại. Cần cầu nối thực thi như gateway, agent, cơ chế grant hoặc chính sách tại đích.

### 7.1. Phiên đang mở và rủi ro thay đổi

Có thể đánh giá lại theo sự kiện hoặc tại các điểm kiểm soát, thay vì chỉ theo lịch cố định. Tuy nhiên, “theo dõi liên tục” không có nghĩa mọi giao thức đều hỗ trợ tạm dừng từng lệnh để hỏi MFA.

Với phiên hiện hữu, chính sách cần nêu rõ:

- Có chặn hành động nhạy cảm tiếp theo được không?
- Có thể tạm khóa hoặc ngắt phiên qua broker không?
- Những tiến trình hoặc kết nối trên máy đích có tiếp tục sau khi ngắt không?
- Grant, token hoặc credential nào cần thu hồi thêm?
- Ai xử lý nếu thao tác đang chạy có thể ảnh hưởng dịch vụ?

Ngắt kết nối không tự hoàn tác thay đổi hoặc dừng mọi tác vụ nền. Cần có cách kiểm tra và xử lý tác động tại đích.

### 7.2. Tài khoản dịch vụ và công việc không có người tương tác

Không gắn một luồng MFA tương tác của người quản trị vào mọi tác vụ máy để rồi phải chia sẻ OTP hoặc giữ phiên người dùng sống vô hạn.

Danh tính workload cần cơ chế xác thực, cấp quyền, credential và vòng đời phù hợp riêng. Khi một người yêu cầu hoặc thay đổi một tác vụ đặc quyền, có thể kiểm tra xác thực lại đối với hành động của người đó; quyền của tác vụ vẫn phải được giới hạn và kiểm soát riêng.

## 8. Gián đoạn, phục hồi và đường khẩn cấp

### 8.1. IdP hoặc dịch vụ rủi ro không sẵn sàng

Cần thiết kế hành vi theo từng loại hành động. Với một hành động bắt buộc có bằng chứng xác thực mới, không thể coi việc dịch vụ xác thực lỗi là lý do tự động cho phép.

Nếu thiếu tín hiệu rủi ro bắt buộc, hệ thống cần phản ánh trạng thái chưa đủ điều kiện hoặc áp dụng đường xử lý đã được phê duyệt. Tín hiệu hỗ trợ bị chậm có thể được xử lý khác, nhưng phải có quy tắc về độ mới và giới hạn.

Không nên mặc định rằng khi một dịch vụ hỗ trợ mất kết nối thì toàn bộ hoạt động quản trị luôn phải dừng hoặc luôn được tiếp tục. Cần quyết định trước theo loại quyền, mức rủi ro và khả năng vận hành an toàn.

Với phiên đang hoạt động, hành vi khi mất thành phần phụ thuộc cũng cần được xác định và thử nghiệm: chặn nâng quyền, hạn chế hành động, thông báo người vận hành hoặc kết thúc theo điều kiện đã thiết kế.

### 8.2. Mất yếu tố xác thực

Quy trình phục hồi phải xác minh người dùng bằng phương thức phù hợp và có người chịu trách nhiệm. Nếu chỉ một cuộc gọi helpdesk có thể vô hiệu hóa MFA mà không đủ kiểm soát, người tấn công sẽ nhắm vào đường đó.

Có thể chuẩn bị phương thức dự phòng được đăng ký và quản trị phù hợp. Khi mất hoặc nghi ngờ lộ yếu tố xác thực, cần xử lý credential, phiên hoặc thiết bị liên quan theo chính sách.

Không gửi OTP, mã khôi phục hoặc khóa riêng vào ticket. Không chia sẻ yếu tố của một quản trị viên khác để hoàn tất công việc.

### 8.3. Truy cập khẩn cấp

Đường khẩn cấp cần được thiết kế và kiểm thử trước, với điều kiện kích hoạt, người chịu trách nhiệm, phạm vi, thời hạn và cách bảo vệ bằng chứng.

Một đường khẩn cấp có thể áp dụng điều kiện khác khi hạ tầng xác thực gặp sự cố, nhưng phải ghi nhận đúng rằng nó được dùng. Không đánh dấu như một lần xác thực theo chính sách chuẩn nếu bằng chứng tương ứng không tồn tại.

Sau sử dụng, cần rà soát, thu hồi quyền tạm, xử lý credential cần thiết và kiểm tra phiên hoặc dấu vết truy cập còn tồn tại.

### 8.4. Hạn chế thông báo và chống chấp thuận theo thói quen

Số lần yêu cầu xác thực cần có giới hạn và giải thích phù hợp. Người dùng nên thấy hành động nào đang cần xác thực, tài sản liên quan và cách xử lý nếu không phải mình yêu cầu.

Các yêu cầu lặp không mong đợi có thể là tín hiệu cần điều tra. Không tiếp tục gửi thông báo vô hạn cho đến khi người dùng chấp thuận.

Có thể giảm gián đoạn bằng cách tái sử dụng bằng chứng còn đủ mới trong phạm vi được phép, gộp những bước hợp lý và tránh tạo thử thách trùng. Cách này phải giữ được ràng buộc hành động và điều kiện chính sách, không biến thành một lần xác thực cho mọi quyền.

## 9. Tình huống thực hành: từ đọc log đến checkout credential

### 9.1. Bối cảnh

Hà đăng nhập vào PAM từ máy trạm quản trị được quản lý. Chính sách minh họa quy định:

- Mở phiên đọc log cần bằng chứng xác thực phù hợp không quá 15 phút.
- Hiển thị credential quản trị sản xuất cần phương thức MFA được chấp nhận là chống phishing và lần xác thực đáp ứng yêu cầu không quá hai phút.
- Checkout vẫn cần phê duyệt và grant JIT còn hiệu lực.
- Tín hiệu thiết bị bị xâm nhập sẽ chặn hành động đặc quyền theo chính sách.
- Mọi kết quả xác thực cho hành động một lần phải gắn đúng ngữ cảnh.

Các ngưỡng này chỉ phục vụ tình huống, không phải khuyến nghị chung.

### 9.2. Diễn biến

| Thời điểm | Sự kiện | Quyết định phù hợp |
|---|---|---|
| 09:00 | Hà xác thực bằng phương thức đáp ứng chính sách | Tạo phiên và lưu bằng chứng xác thực đáng tin cậy |
| 09:04 | Mở phiên đọc log đã được duyệt | Bằng chứng còn mới; kiểm tra quyền và các điều kiện còn lại |
| 09:25 | Yêu cầu hiển thị một credential sản xuất | Yêu cầu xác thực lại vì chưa đáp ứng độ mới của hành động |
| 09:26 | Xác thực lại thành công | Chưa tiết lộ ngay; kiểm tra ngữ cảnh và điều kiện hiện hành |
| 09:26 | Phát hiện phê duyệt vừa bị hủy | Từ chối checkout dù xác thực vừa thành công |
| 09:35 | Có yêu cầu mới được xử lý hợp lệ | Đánh giá lại theo trạng thái và thời hạn mới |
| 09:36 | Nhận tín hiệu thiết bị bị xâm nhập đã được xác nhận | Chặn hành động; xử lý phiên và grant theo quy trình sự cố |

Ở mốc 09:26, Hà đã chứng minh được danh tính bằng một bằng chứng mới nhưng không còn được phép thực hiện checkout. Xác thực và cấp phép trả lời hai câu hỏi khác nhau.

### 9.3. Biến thể: đổi credential sau khi thử thách được tạo

Hà khởi tạo xác thực lại cho credential A nhưng trước khi trả kết quả, trình duyệt gửi một yêu cầu thay đối tượng sang credential B.

Máy chủ phải đối chiếu ngữ cảnh đã ràng buộc. Kết quả cho A không được mở checkout B nếu chưa được đánh giá và xử lý phù hợp.

Cần dùng mã tham chiếu bí mật hoặc tài sản, không đưa giá trị credential thực vào tham số, thông báo hoặc log.

### 9.4. Biến thể: tab thứ hai và kết quả trùng

Hà mở hai tab cùng yêu cầu checkout. Nếu chính sách dùng một lần, mỗi hành động phải có trạng thái xác định; phản hồi lặp hoặc việc tải lại trang không được gây tiết lộ thêm ngoài ý định.

Nếu chính sách cho phép một lần xác thực đáp ứng nhiều hành động trong một khoảng ngắn, mỗi hành động vẫn phải qua kiểm tra quyền, đối tượng và rủi ro. Việc tái sử dụng bằng chứng phải là một quy tắc có giới hạn, không phải hệ quả vô tình của cache.

### 9.5. Biến thể: thiết bị không còn đạt điều kiện

Sau lần MFA thành công, máy trạm mất trạng thái đáp ứng chính sách. Hỏi MFA thêm không làm máy trở lại đạt điều kiện.

Cần yêu cầu sử dụng đường hoặc thiết bị được phép, hoặc áp dụng đường khẩn cấp nếu đủ điều kiện. Nếu có dấu hiệu sự cố, cần xử lý theo mức độ thay vì chỉ hướng dẫn người dùng đăng nhập lại nhiều lần.

## 10. Bằng chứng cần lưu

Một hồ sơ quyết định nên liên kết được:

```text
Yêu cầu hành động
  -> Trạng thái quyền, phê duyệt và tín hiệu rủi ro
  -> Chính sách và lý do cần xác thực lại
  -> Ngữ cảnh thử thách
  -> Kết quả xác thực từ nguồn tin cậy
  -> Kiểm tra cuối
  -> Cho phép hoặc từ chối
  -> Grant/phiên/thao tác và kết quả thu hồi khi có
```

Những trường thông tin hữu ích gồm:

- Định danh người dùng, phiên, yêu cầu, tài sản và hành động.
- Thời điểm quyết định, chính sách và lý do áp dụng.
- Thời điểm xác thực thực sự, nhóm phương thức đã được xác minh và nguồn bằng chứng.
- Tín hiệu rủi ro cần thiết cùng thời điểm hoặc độ mới.
- Mã tương quan ngữ cảnh và kết quả, thời hạn, trạng thái tiêu thụ.
- Kết quả kiểm tra quyền cuối cùng và lý do từ chối nếu có.
- Mã grant, phiên PAM hoặc thao tác thực tế để đối chiếu.

Không ghi OTP, cookie phiên, access token, mã khôi phục hoặc nội dung bí mật vào log. Nếu cần lưu tham chiếu đến một bằng chứng nhạy cảm, phải bảo vệ và giới hạn truy cập phù hợp.

Tín hiệu vị trí, thiết bị và hành vi có thể liên quan đến thông tin cá nhân. Chỉ thu thập dữ liệu cần thiết, có mục đích và vòng đời lưu rõ ràng.

Bằng chứng “xác thực lại thành công” chưa chứng minh một lệnh đã chạy. Cần log ở điểm thực thi để biết hành động có được cho phép và thực sự thực hiện hay không.

### Chỉ số vận hành

Có thể theo dõi tỷ lệ hành động nhạy cảm được kiểm tra, số lần yêu cầu xác thực theo loại hành động, lỗi tích hợp, độ trễ tín hiệu, tỷ lệ hủy, phản hồi trùng và trường hợp chặn sau xác thực thành công.

Đánh giá cả gián đoạn người dùng và khả năng chặn đúng. Không giảm số thử thách bằng cách mở rộng thời hạn hoặc hạ mức bảo đảm mà không xem xét tác động.

## 11. Kiểm chứng cơ chế trước khi vận hành

Thử nghiệm trên môi trường, tài khoản và tài sản được phép.

| Phép thử | Kết quả mong đợi |
|---|---|
| Token mới được phát hành từ phiên xác thực cũ | Không bị coi là xác thực mới nếu chưa có bằng chứng đáp ứng |
| Trình duyệt gửi thời gian hoặc cờ MFA tự khai | Không được dùng làm căn cứ tin cậy |
| Người dùng có quyền nhưng bằng chứng quá cũ | Yêu cầu xác thực lại đúng chính sách |
| Bằng chứng mới nhưng phương thức chưa đạt | Không cho phép chỉ dựa vào độ mới |
| Có xác thực mạnh nhưng thiếu phê duyệt | Từ chối hành động |
| Grant hết hạn trong lúc xác thực | Kiểm tra cuối chặn thao tác |
| Tài sản hoặc hành động thay đổi sau khi tạo ngữ cảnh | Không dùng kết quả cũ cho phạm vi mới |
| Kết quả dành cho người, phiên hoặc bên nhận khác | Không được chấp nhận |
| Kết quả dùng một lần được gửi lại | Không tạo thêm tác động ngoài chính sách |
| API được gọi trực tiếp bỏ giao diện | Vẫn thực thi kiểm tra tương đương |
| Tín hiệu xâm nhập đến sau MFA nhưng trước thao tác | Điều kiện cấm được áp dụng tại kiểm tra cuối |
| Dịch vụ xác thực hoặc tín hiệu bắt buộc lỗi | Không âm thầm bỏ qua yêu cầu |
| Hủy thử thách hoặc để quá hạn | Hành động vẫn chưa được cho phép |
| Phiên bị ngắt do rủi ro | Kiểm tra thêm grant, token và trạng thái đích liên quan |
| Một phiên giao thức cũ không hỗ trợ chặn từng hành động | Áp dụng đường kiểm soát khả thi đã thiết kế, không giả định khả năng không có |

Cần kiểm tra cả luồng hợp lệ để tránh làm quy trình không thể sử dụng. Khi một kiểm soát chưa được giao thức hoặc sản phẩm hỗ trợ, phải ghi rõ giới hạn và xử lý kiến trúc phù hợp trước khi coi mục tiêu đã đạt.

## 12. Sai lầm thường gặp

**Chỉ kiểm tra tài khoản đã bật MFA.** Trạng thái đăng ký phương thức không chứng minh lần yêu cầu hiện tại có bằng chứng đủ mới và đủ mạnh.

**Lấy tuổi token làm tuổi xác thực.** Token có thể được làm mới từ một phiên cũ. Cần thời điểm xác thực có ý nghĩa được nguồn tin cậy xác nhận.

**Hỏi MFA cho mọi tín hiệu bất thường.** Tín hiệu mạnh về xâm nhập hoặc điều kiện cấm cần hành động chặn và xử lý phù hợp.

**Chỉ kiểm soát trên giao diện.** Hành động thực tế qua API hoặc kênh quản trị khác phải chịu điều kiện tương đương.

**Dùng xác thực lại để thay phê duyệt hoặc JIT.** Người dùng xác thực thành công vẫn cần đúng quyền, đúng tài sản và đúng cửa sổ công việc.

**Giữ kết quả xác thực chung cho mọi hành động.** Cần phạm vi và thời hạn, cùng kiểm tra cấp phép cho từng thao tác.

**Cho rằng ngắt phiên là thu hồi hoàn tất.** Token, grant hoặc tác vụ tại máy đích có thể cần xử lý riêng.

**Vô hiệu hóa MFA khi helpdesk gặp khó khăn.** Phục hồi và khẩn cấp cần là các đường được thiết kế với trách nhiệm và bằng chứng rõ ràng.

## 13. Tự kiểm tra

1. Xác thực lại khác làm mới access token như thế nào?
2. Bằng chứng vừa có nhưng phương thức yếu hơn yêu cầu thì có được checkout credential không?
3. Vì sao xác thực lại thành công không thay thế phê duyệt quyền?
4. Cần ràng buộc những gì để kết quả cho tài sản A không bị dùng cho tài sản B?
5. Một thiết bị bị xác nhận xâm nhập có thể trở lại đáng tin chỉ bằng MFA không?
6. Vì sao cần kiểm tra lại quyền sau khi người dùng hoàn tất thử thách?
7. Ngắt một phiên PAM có bảo đảm dừng mọi tác vụ trên máy đích không?
8. Những dữ liệu xác thực nào không nên ghi vào log?

### Gợi ý trả lời

1. Xác thực lại tạo bằng chứng mới đáp ứng yêu cầu; token mới có thể chỉ là kết quả kéo dài một phiên cũ.
2. Không. Cần cả độ mới và mức bảo đảm phù hợp.
3. Xác thực chứng minh danh tính; phê duyệt và cấp phép quyết định phạm vi công việc được làm.
4. Chủ thể, phiên, tài sản, hành động, phạm vi, thời hạn và trạng thái sử dụng của ngữ cảnh.
5. Không. Cần xử lý điều kiện thiết bị và sự cố theo chính sách.
6. Grant, ticket, danh tính hoặc rủi ro có thể đã thay đổi trong lúc xác thực.
7. Không. Cần xem kết nối, tiến trình, token và quyền còn tồn tại tại đích.
8. OTP, token, cookie, mật khẩu, khóa riêng, mã khôi phục và các bí mật tương tự.

## Kết luận

Reauthentication theo rủi ro giúp PAM yêu cầu bằng chứng xác thực phù hợp tại thời điểm sử dụng quyền đặc biệt. Giá trị của cơ chế nằm ở khả năng đánh giá đúng hành động, hiểu độ mới và mức bảo đảm, ràng buộc kết quả với ngữ cảnh, rồi kiểm tra lại trước khi thực thi.

Khi kết hợp với least privilege, JIT/JEA, vault, kiểm soát phiên và thu hồi có bằng chứng, xác thực lại trở thành một phần của vòng đời quyền có thể kiểm chứng. Nó hỗ trợ quyết định tin cậy tại thời điểm cần thiết và vẫn giữ các điều kiện về quyền, phê duyệt và trạng thái hệ thống trong hiệu lực.
