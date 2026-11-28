# Application admin role

## 1. Application admin role là gì?

Application admin role là vai trò cho phép một chủ thể thực hiện các thao tác quản trị trong phạm vi một ứng dụng. Tùy thiết kế, vai trò có thể quản lý cấu hình, người dùng, tích hợp, dữ liệu vận hành, chính sách truy cập hoặc một tập tác vụ quản trị cụ thể.

Tên “admin” không mô tả đầy đủ mức đặc quyền. Một quản trị viên chỉ sửa mẫu thông báo khác đáng kể với người có thể tạo API key, thay cấu hình đăng nhập hoặc cấp quyền quản trị cho người khác.

Trong quản lý truy cập đặc quyền (PAM), cần nhìn vai trò quản trị ứng dụng như một tập năng lực có thể tác động đến:

- Tính bí mật của dữ liệu và credential.
- Tính toàn vẹn của cấu hình, dữ liệu và quy trình nghiệp vụ.
- Tính sẵn sàng của dịch vụ.
- Khả năng thay đổi ai được truy cập và truy cập bằng cách nào.
- Khả năng tạo ra quyền tồn tại lâu hơn phiên quản trị ban đầu.
- Khả năng ghi nhận và điều tra hành động quản trị.

Bài học dùng “application admin role” theo nghĩa tổng quát. Khi triển khai một sản phẩm cụ thể, phải đọc định nghĩa quyền thực tế của sản phẩm; không suy luận từ tên hiển thị của vai trò.

Sau bài này, bạn có thể thiết kế một vai trò quản trị ứng dụng có phạm vi rõ ràng, phân tách trách nhiệm, cấp quyền theo nhu cầu, kiểm soát truy cập tạm thời và thu bằng chứng về cả sử dụng lẫn thu hồi.

## 2. Quản trị ứng dụng khác quản trị hạ tầng như thế nào?

Một người không có quyền root trên máy chủ vẫn có thể làm thay đổi nghiêm trọng hệ thống bằng quyền quản trị ứng dụng. Ví dụ, họ có thể đổi nơi nhận dữ liệu xuất, tạo tích hợp có quyền rộng hoặc thay chính sách duyệt giao dịch.

Ngược lại, quản trị viên hạ tầng có thể có đường tác động vào ứng dụng qua triển khai mã, cấu hình hoặc credential, dù không được gán role trong giao diện ứng dụng. Hai nhóm quyền có điểm giao nhau nhưng không đồng nhất.

| Lớp quyền | Ví dụ năng lực | Câu hỏi kiểm soát |
|---|---|---|
| Hạ tầng | Quản trị máy, mạng, nền tảng chạy | Có thể điều khiển mã và dữ liệu nền của ứng dụng không? |
| Danh tính và SSO | Quản lý nhóm, mapping, phiên đăng nhập | Ai có thể khiến một chủ thể trở thành admin ứng dụng? |
| Quản trị ứng dụng | Sửa cấu hình, tích hợp, tài khoản | Những thao tác nào có thể đổi ranh giới truy cập? |
| Nghiệp vụ | Duyệt đơn, sửa hồ sơ, xuất báo cáo | Admin ứng dụng có mặc nhiên được thực hiện nghiệp vụ nhạy cảm không? |
| Dữ liệu | Đọc, sửa, xóa hoặc xuất dữ liệu | Quyền quản trị cấu hình có đường dẫn đến dữ liệu không? |

Thiết kế tốt cần làm rõ từng lớp. Không nên mặc định “quản trị ứng dụng” đồng nghĩa “được xem mọi dữ liệu nghiệp vụ”.

Một ví dụ hữu ích là hệ thống xử lý hồ sơ nhân sự. Người quản lý cấu hình giao diện có thể cần sửa mẫu trang, nhưng không cần đọc lương. Nếu ứng dụng chỉ cung cấp một role admin bao trùm cả hai, đó là một giới hạn phân quyền cần được đánh giá, không phải lý do coi mọi quyền trong role đều là nhu cầu thực tế.

## 3. Phân biệt vai trò, quyền, phép gán và phiên kích hoạt

Bốn khái niệm thường bị gộp làm một:

| Khái niệm | Nội dung | Ví dụ |
|---|---|---|
| Permission | Thao tác cụ thể trên loại tài nguyên | Sửa cấu hình tích hợp |
| Role definition | Tập quyền và điều kiện được đóng gói | Vai trò vận hành ứng dụng |
| Role assignment | Quan hệ chủ thể được giữ role trong phạm vi | An được giữ role vận hành ở tenant A |
| Activation | Một lần đưa quyền đủ điều kiện vào hiệu lực | An kích hoạt quyền production cho yêu cầu bảo trì |

Một ứng dụng đơn giản có thể chỉ hỗ trợ gán role thường trực. Muốn triển khai cơ chế kích hoạt tạm thời, có thể cần tích hợp thêm hệ thống PAM hoặc cơ chế điều phối. Không nên ghi đã có JIT chỉ vì biểu mẫu có trường thời gian.

### 3.1. Định nghĩa role thay đổi sẽ ảnh hưởng ai?

Nếu thêm quyền tạo API key vào một role đang gán cho 100 người, phạm vi đặc quyền của 100 người có thể thay đổi mà không có phép gán mới nào.

Vì vậy, cần quản lý hai loại thay đổi riêng:

1. Thay đổi ai được giữ role.
2. Thay đổi role cho phép làm gì.

Cả hai đều cần chủ sở hữu, lý do, đánh giá tác động và bằng chứng phù hợp. Chỉ giám sát sự kiện “thêm người vào nhóm admin” có thể bỏ sót việc âm thầm làm role mạnh hơn.

### 3.2. Role chỉ là một phần của quyết định truy cập

Một quyết định quản trị nên xét ít nhất:

~~~text
Chủ thể nào?
+ Thao tác gì?
+ Tài nguyên nào?
+ Thuộc ứng dụng, môi trường và tenant nào?
+ Quyền có đang hiệu lực không?
+ Điều kiện bảo vệ nào phải được đáp ứng?
-> Cho phép hoặc từ chối
~~~

Ví dụ, “An là admin” chưa đủ để quyết định An có thể đổi cấu hình production của tenant B. An có thể chỉ là admin staging của tenant A.

## 4. Thiết kế phạm vi trước khi thiết kế tên role

Một phép gán quản trị cần trả lời rõ năm câu hỏi:

1. Ứng dụng nào?
2. Môi trường nào?
3. Tenant, tổ chức, dự án hoặc không gian nào?
4. Tập tài nguyên nào?
5. Tập thao tác nào?

Nếu thiếu một chiều quan trọng, vai trò có thể rộng hơn nhu cầu.

### Ví dụ về phạm vi

| Phép gán | Đánh giá |
|---|---|
| “Admin CRM” | Chưa rõ môi trường, tenant và thao tác |
| “Admin CRM staging” | Đã giới hạn môi trường, chưa rõ phạm vi chức năng |
| “Vận hành tích hợp CRM production của tenant A” | Rõ hơn, cần liệt kê quyền và giới hạn |
| “Sửa endpoint tích hợp đã được duyệt của tenant A trong cửa sổ bảo trì” | Gắn với tác vụ cụ thể, vẫn cần cơ chế thực thi |

Quyền ở tenant A không được trở thành quyền tenant B chỉ vì người dùng thay tham số trong yêu cầu. OWASP khuyến nghị xác lập ngữ cảnh tenant từ danh tính và quan hệ đã được phía máy chủ xác minh; mã tenant do client gửi không tự chứng minh quyền. [OWASP: Multi-Tenant Security](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html).

Từ nguyên tắc này, thiết kế minh họa trong bài coi lựa chọn tenant là một đầu vào phải kiểm tra. Nếu có đường quản trị xuyên tenant, đường đó cần được thiết kế và cấp quyền riêng, thay vì được mở ngầm cho mọi application admin.

### Danh tính con người và danh tính tự động

Người quản trị và pipeline tự động không nên dùng chung một tài khoản chỉ để dễ gán role. Chúng có cách xác thực, vòng đời, nguồn bằng chứng và nhu cầu quyền khác nhau.

Một job tự động sửa cấu hình theo lịch có thể cần một danh tính workload với quyền tác vụ hẹp. Việc gán role admin tương tác toàn phần cho job nên được xem là một lựa chọn phải giải thích, không phải cấu hình mặc định.

## 5. Phân rã role admin thành các năng lực có thể quản trị

Thay vì bắt đầu bằng một role “super admin”, hãy lập danh mục thao tác rồi nhóm theo mục đích.

Ví dụ hệ thống quản lý hồ sơ có các nhóm vai trò sau. Đây là thiết kế minh họa, không phải các role chuẩn của một nhà cung cấp:

| Vai trò | Được làm | Không được mặc định làm |
|---|---|---|
| Vận hành ứng dụng | Theo dõi trạng thái, thực hiện tác vụ vận hành đã định nghĩa | Cấp role admin, đọc mọi hồ sơ nghiệp vụ |
| Quản lý người dùng thường | Mời, khóa và quản lý role nghiệp vụ được duyệt | Quản lý tài khoản admin hoặc sửa chính sách phân quyền |
| Quản lý tích hợp | Quản lý tập kết nối và cấu hình được duyệt | Tự cấp scope mới hoặc tạo credential vượt phạm vi |
| Quản trị chính sách bảo mật | Quản lý chính sách xác thực và truy cập theo quy trình | Tự phê duyệt mọi thay đổi của chính mình |
| Người rà soát | Đọc cấu hình quyền và bằng chứng cần thiết | Sửa role hoặc xóa log |
| Hỗ trợ có giám sát | Thực hiện chức năng hỗ trợ giới hạn, có mã yêu cầu | Giả danh người dùng không giới hạn |

Không phải tổ chức nào cũng cần đúng sáu role này. Mục tiêu là phân biệt những năng lực có rủi ro và nhu cầu khác nhau.

### 5.1. Tách quản lý người dùng thường khỏi quản lý quản trị viên

Người hỗ trợ khóa tài khoản nhân viên chưa chắc cần quyền đặt lại phương thức xác thực của quản trị viên.

Nếu một role có thể chiếm quyền điều khiển tài khoản mạnh hơn thông qua reset credential hoặc thay yếu tố xác thực, role đó có đường nâng quyền đáng kể dù không có permission “grant admin”.

Khi thiết kế, hỏi:

- Có được thao tác với mọi tài khoản hay chỉ tài khoản thường?
- Có được thay địa chỉ phục hồi hoặc phương thức xác thực không?
- Có thể chuyển quyền sở hữu đối tượng quan trọng không?
- Có thể gán một nhóm mà nhóm đó đã có đặc quyền không?
- Có thể tạo tài khoản mới và cấp cho nó một role mạnh không?

Các câu trả lời cần được thực thi tại hệ thống, không chỉ ghi trong hướng dẫn.

### 5.2. Tách quản lý role khỏi phê duyệt quyền

Có ít nhất ba hoạt động khác nhau:

1. Định nghĩa permission trong role.
2. Gán role cho một chủ thể.
3. Phê duyệt nhu cầu nhận role.

Một người có thể tham gia nhiều hoạt động trong tổ chức nhỏ, nhưng xung đột phải được nhận diện. Với thay đổi nhạy cảm, cần một điểm kiểm tra độc lập phù hợp.

Không nên để một người tự tạo role mạnh, tự gán role và tự xác nhận rằng thay đổi đó đã được rà soát.

## 6. Những năng lực quản trị có thể tạo quyền gián tiếp

Đánh giá role cần đi xa hơn danh sách nút bấm trên giao diện.

| Năng lực | Đường tác động có thể phát sinh | Câu hỏi cần kiểm tra |
|---|---|---|
| Thay cấu hình SSO | Thay đổi cách nhận diện và mapping người dùng | Có thể làm một chủ thể trở thành admin không? |
| Tạo API key hoặc client credential | Tạo một đường truy cập mới | Credential có phạm vi và thời hạn nào? |
| Cài plugin hoặc mã tùy biến | Đưa mã vào ngữ cảnh ứng dụng | Mã chạy dưới danh tính có quyền gì? |
| Sửa webhook hoặc nơi xuất dữ liệu | Thay đổi nơi dữ liệu được gửi | Có thể gửi dữ liệu nhạy cảm ra ngoài không? |
| Đổi chủ sở hữu đối tượng | Chuyển năng lực quản lý hoặc truy cập | Người nhận có nhận thêm quyền ngầm không? |
| Sửa chính sách lưu giữ hoặc audit | Giảm khả năng phát hiện và điều tra | Có thể xóa hoặc làm thiếu bằng chứng không? |
| Khôi phục bản sao | Đưa cấu hình và dữ liệu cũ trở lại | Có khôi phục cả quyền đã thu hồi không? |
| Điều khiển tác vụ nền | Làm ứng dụng thực hiện hành động thay người dùng | Danh tính thực thi có quyền rộng hơn người yêu cầu không? |

Không phải mọi sản phẩm cho phép mọi đường tác động trong bảng. Bảng là công cụ đặt câu hỏi để kiểm chứng capability thực tế.

### Ví dụ: role cấu hình không có quyền đọc dữ liệu

Giả sử một role không có quyền “xem hồ sơ”, nhưng có quyền cấu hình tác vụ xuất toàn bộ hồ sơ sang một đích tùy chọn.

Nếu tác vụ xuất thực sự thực hiện được, role vẫn có một đường tác động đến tính bí mật của dữ liệu. Phân tích chỉ dựa vào permission “read record” sẽ bỏ sót đường này.

Có thể cần giới hạn tập đích, loại dữ liệu được xuất, người phê duyệt hoặc tách thao tác tạo và kích hoạt cấu hình. Biện pháp phải phù hợp khả năng sản phẩm và nhu cầu nghiệp vụ.

## 7. Least privilege và phân tách trách nhiệm

Một yêu cầu quản trị tốt bắt đầu bằng tác vụ cụ thể:

> Cần cập nhật địa chỉ của một tích hợp đã được chủ dịch vụ phê duyệt, tại production của tenant A, trong cửa sổ bảo trì.

Yêu cầu yếu hơn là:

> Cần admin vì đang phụ trách hệ thống.

Từ tác vụ, xác định permission tối thiểu, tài nguyên, khoảng thời gian và điều kiện kiểm tra.

### 7.1. Ma trận thao tác minh họa

| Thao tác | Vận hành | Quản lý người dùng thường | Quản trị bảo mật | Rà soát |
|---|---|---|---|---|
| Xem trạng thái dịch vụ | Cho phép | Theo nhu cầu | Theo nhu cầu | Đọc nếu cần |
| Sửa cấu hình vận hành trong phạm vi | Cho phép có điều kiện | Từ chối | Không mặc định | Từ chối |
| Khóa tài khoản thường | Không mặc định | Cho phép trong phạm vi | Theo quy trình | Từ chối |
| Cấp role quản trị | Từ chối | Từ chối | Theo phê duyệt độc lập | Từ chối |
| Đổi chính sách đăng nhập | Từ chối | Từ chối | Cho phép có kiểm soát | Từ chối |
| Đọc bằng chứng quyền | Theo nhu cầu | Theo nhu cầu | Theo nhu cầu | Cho phép trong phạm vi |
| Xóa bằng chứng audit | Từ chối | Từ chối | Không mặc định | Từ chối |

Bảng này thể hiện ý định thiết kế. Khi triển khai, mỗi ô “theo nhu cầu” phải được chuyển thành quyết định cụ thể, không để thành một vùng mơ hồ trong cấu hình.

### 7.2. Kiểm soát các tổ hợp quyền

Hai role riêng lẻ có thể tạo thành một tổ hợp rủi ro:

~~~text
Role A: tạo tích hợp
Role B: phê duyệt tích hợp
A + B: có thể tự tạo và tự phê duyệt đường truy cập mới
~~~

Nếu chỉ kiểm tra từng role độc lập, tổ chức có thể không thấy xung đột. Cần đánh giá quyền hiệu lực của chủ thể, bao gồm gán trực tiếp, nhóm, role kế thừa và quyền khác liên quan.

Với chức năng nhạy cảm, kiểm soát nên ràng buộc vào người thực hiện thực tế. Hai tài khoản do cùng một người kiểm soát không tạo ra sự độc lập chỉ vì có hai tên đăng nhập.

## 8. Cấp quyền tạm thời và giới hạn thao tác

### 8.1. Điều kiện được kích hoạt khác quyền đang hoạt động

Một người có thể đủ điều kiện xin role quản trị nhưng chưa được dùng role đó cho đến khi có yêu cầu hợp lệ.

Luồng minh họa:

~~~mermaid
flowchart LR
    A[Yêu cầu gắn với tác vụ] --> B[Kiểm tra phạm vi và xung đột]
    B --> C[Phê duyệt phù hợp]
    C --> D[Kích hoạt quyền giới hạn]
    D --> E[Thực hiện và ghi bằng chứng]
    E --> F[Hết hạn hoặc thu hồi]
    F --> G[Kiểm chứng quyền đã kết thúc]
~~~

Thông tin cấp quyền cần có người sử dụng, role, scope, lý do, mã yêu cầu, người phê duyệt, thời điểm bắt đầu và thời điểm kết thúc.

Mục tiêu JIT là giảm khoảng thời gian quyền mạnh có hiệu lực. Mục tiêu JEA là giảm tập thao tác có thể thực hiện. Chỉ làm một trong hai vẫn có thể để lại rủi ro từ phần còn lại.

### 8.2. Thời hạn token không phải thời hạn quyền

Một phiên quản trị có thể chứa token còn hiệu lực sau khi phép gán role bị gỡ, tùy kiến trúc kiểm tra quyền và cache.

Ngược lại, token ngắn hạn không giúp giảm quyền thường trực nếu người dùng có thể lấy token mới với cùng role bất kỳ lúc nào.

Khi thiết kế, tách:

- Thời gian phép gán hoặc kích hoạt quyền tồn tại.
- Thời gian token có hiệu lực.
- Thời gian phiên ứng dụng còn dùng được.
- Thời điểm backend nhận biết thay đổi quyền.
- Thời gian một tác vụ nền được phép tiếp tục.

Các giá trị này cần có cơ chế và bằng chứng tương ứng.

### 8.3. Chú ý hiện vật được tạo trong cửa sổ JIT

Nếu admin tạm thời có thể tạo API key không hết hạn, kết thúc role không tự kết thúc đường truy cập đã tạo.

Tương tự, tác vụ xuất dữ liệu, tài khoản mới, integration credential hoặc phiên giả danh có thể có vòng đời riêng.

Với những hiện vật đó, cần một trong các cách thiết kế phù hợp:

- Không cho role tạm tạo hiện vật ngoài nhu cầu.
- Giới hạn phạm vi và thời hạn của hiện vật.
- Yêu cầu phê duyệt riêng.
- Liên kết hiện vật với mã tác vụ và đưa vào bước đối soát cuối.
- Có cơ chế thu hồi và kiểm chứng khi tác vụ kết thúc.

## 9. Thực thi quyền tại ứng dụng

Ẩn menu admin giúp trải nghiệm rõ ràng nhưng chưa phải ranh giới bảo mật. Quyết định cho phép phải được thực thi ở nơi xử lý thao tác.

OWASP khuyến nghị từ chối theo mặc định và kiểm tra quyền trên mọi yêu cầu, kể cả yêu cầu không đi qua giao diện thông thường. [OWASP: Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Từ nguyên tắc đó, một thiết kế minh họa có thể dùng mô hình:

~~~text
quản_trị_cấu_hình(yêu_cầu):
    chủ_thể = xác_minh_danh_tính_và_phiên(yêu_cầu)
    nếu không có chủ_thể:
        từ_chối()

    ngữ_cảnh = xác_lập_phạm_vi_đã_kiểm_chứng(chủ_thể, yêu_cầu)
    tài_nguyên = tìm_tài_nguyên_trong_phạm_vi(ngữ_cảnh, yêu_cầu.id)

    quyết_định = đánh_giá_chính_sách(
        chủ_thể,
        thao_tác = "integration.configuration.update",
        tài_nguyên,
        ngữ_cảnh,
        quyền_đang_hiệu_lực
    )

    nếu quyết_định không cho phép:
        ghi_sự_kiện_từ_chối_an_toàn()
        từ_chối()

    kiểm_tra_nội_dung_thay_đổi(yêu_cầu)
    kiểm_tra_phê_duyệt_gắn_với_thay_đổi_nếu_bắt_buộc()
    thực_hiện_thay_đổi_có_kiểm_soát()
    ghi_bằng_chứng_thành_công_hoặc_lỗi()
~~~

Đây là giả mã mô tả điểm kiểm soát, không phải một triển khai hoàn chỉnh.

### 9.1. Không tin role do client tự khai

Các trường như `isAdmin`, tên role trong form hoặc tenant trong header có thể là dữ liệu yêu cầu. Chúng không được trở thành bằng chứng quyền nếu chưa được xác minh qua nguồn tin cậy.

Ngay cả claim có chữ ký cũng cần được kiểm tra đúng nguồn phát hành, đối tượng sử dụng, thời hạn và cách ánh xạ vào quyền của ứng dụng. Một nhóm tên “admin” trong hệ thống khác không tự mang cùng ý nghĩa trong mọi ứng dụng.

### 9.2. Phê duyệt phải gắn với đúng thay đổi

Nếu yêu cầu được duyệt để đổi endpoint A thành B nhưng thao tác thực thi lại đổi sang C, phê duyệt không còn chứng minh người có thẩm quyền đã chấp thuận kết quả đó.

OWASP yêu cầu kiểm soát phê duyệt giao dịch được thực thi phía máy chủ và bảo vệ dữ liệu quan trọng của giao dịch khỏi bị thay đổi trong quá trình phê duyệt. [OWASP: Transaction Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

Áp dụng vào tác vụ quản trị, hồ sơ duyệt nên liên kết các trường nhạy cảm như đích, loại quyền, scope và thời hạn. Nếu chúng đổi, hệ thống cần đánh giá lại theo chính sách thay vì tái dùng một dấu “đã duyệt” chung.

### 9.3. Quyền thay đổi trong lúc tác vụ đang chạy

Với tác vụ dài hoặc xử lý bất đồng bộ, cần xác định thời điểm kiểm tra quyền: khi nhận yêu cầu, khi bắt đầu thực thi, trước thao tác nhạy cảm hoặc theo các điểm kiểm soát được thiết kế.

Không có một quy tắc “hủy mọi tác vụ ngay” phù hợp mọi nghiệp vụ. Tuy nhiên, hành vi khi quyền bị thu hồi phải rõ ràng, có thể kiểm thử và không phụ thuộc một giả định ngầm trong giao diện.

## 10. Bảo vệ tài khoản và phiên quản trị

### Tài khoản có thể quy trách nhiệm

Mỗi người quản trị nên dùng danh tính cá nhân hoặc cơ chế cho phép liên kết chắc chắn hành động với cá nhân. Tài khoản dùng chung làm khó xác định ai đã thực hiện thay đổi.

Nếu buộc phải dùng tài khoản chia sẻ của sản phẩm cũ, cần đánh giá các kiểm soát bù như cấp credential qua PAM, giới hạn người nhận, liên kết mã yêu cầu, kiểm soát phiên và đối soát. Các biện pháp bù không tự biến tài khoản chia sẻ thành tương đương danh tính cá nhân.

### Xác thực và xác thực lại

Tài khoản quản trị cần phương thức xác thực phù hợp rủi ro. Với thao tác nhạy cảm, có thể yêu cầu xác thực lại hoặc bước xác minh bổ sung theo chính sách.

Việc đã đăng nhập từ đầu ngày không phải căn cứ đủ cho mọi thay đổi quan trọng. Đồng thời, bước xác thực bổ sung không thay cho kiểm tra quyền: một người xác thực rất mạnh vẫn có thể không được phép cấp role admin.

### Phiên hỗ trợ hoặc giả danh người dùng

Nếu ứng dụng có chức năng hỗ trợ dưới ngữ cảnh người dùng khác, cần thể hiện cả người quản trị thật và người dùng được hỗ trợ trong bằng chứng.

Phải xác định rõ thao tác nào được phép, dữ liệu nào được xem, có cần sự chấp thuận nào và khi nào phiên hỗ trợ kết thúc. Không để log chỉ ghi tên người dùng bị giả danh vì như vậy dễ quy trách nhiệm sai.

## 11. Kiểm kê, cấp quyền và thay đổi vai trò

### 11.1. Hồ sơ một phép gán quản trị

Mẫu sau là dữ liệu kiểm kê minh họa, không phải cấu hình để nhập trực tiếp vào sản phẩm:

~~~yaml
admin_assignment:
  record_id: APP-ADM-EX-014
  application: case-management
  environment: production
  principal_reference: "<định danh người quản trị>"
  role_reference: "<định danh role thực tế>"
  role_definition_revision: "example-revision-3"
  scope:
    tenant_reference: "<tenant được phép>"
    resource_set_reference: "<tập cấu hình được quản lý>"
  purpose: update-approved-integration
  assignment_mode: temporary-activation
  request_reference: CHANGE-EX-014
  approver_reference: "<người có thẩm quyền>"
  activation_start: "<thời điểm có múi giờ>"
  activation_end: "<thời điểm có múi giờ>"
  evidence_reference: EVID-EX-014
  accountable_owner: team-application
~~~

Giá trị thời gian phải được xác định theo tác vụ và chính sách. Không dùng một khoảng mặc định dài chỉ vì người dùng có thể cần lại quyền trong tương lai.

### 11.2. Khi người dùng đổi vị trí công việc

Quyền cũ không tự mất đi chỉ vì người dùng đã nhận một chức danh mới. Cần đối soát:

- Role trực tiếp trong ứng dụng.
- Nhóm định danh được ánh xạ thành role.
- Quyền sở hữu đối tượng.
- Quyền ủy quyền hoặc role lồng nhau.
- Credential và tài khoản tích hợp do người đó tạo hoặc kiểm soát.
- Phiên và cơ chế hỗ trợ đang còn hiệu lực.

Nếu quy trình provisioning chỉ thêm quyền mới mà không xử lý quyền cũ, đặc quyền có thể tăng dần theo thời gian.

### 11.3. Khi role được mở rộng

Đổi role definition có thể ảnh hưởng toàn bộ người đang giữ role. Trước khi mở rộng, xác định tập chủ thể bị ảnh hưởng và xem nhu cầu mới có thực sự áp dụng cho họ không.

Một quyền mới chỉ dành cho hai người có thể nên được đưa vào role riêng, thay vì thêm vào role đang gán cho cả đội.

## 12. Thu hồi phải bao phủ quyền hiệu lực

Bỏ người dùng khỏi một nhóm là một thao tác quản trị, chưa tự chứng minh ứng dụng đã từ chối truy cập.

Quy trình thu hồi cần đối soát:

1. Gán role trực tiếp và gián tiếp.
2. Kích hoạt tạm thời còn hoạt động.
3. Phiên ứng dụng và token liên quan.
4. Quyền được cache hoặc lưu trong nhiều replica.
5. API key, delegation hoặc tài khoản đã được tạo.
6. Tác vụ nền và phiên hỗ trợ.
7. Các đối tượng mà người dùng còn giữ quyền sở hữu.

Tùy kiến trúc, có thể cần cập nhật trạng thái quyền, làm mới hoặc vô hiệu hóa cache, kết thúc phiên hoặc áp dụng biện pháp khác. Chọn cơ chế theo sản phẩm và kiểm chứng kết quả thực tế.

### Kiểm thử sau thu hồi

| Kiểm tra | Bằng chứng mong muốn |
|---|---|
| Gọi thao tác quản trị bằng phiên cũ | Bị từ chối khi chính sách yêu cầu quyền đã hết |
| Đăng nhập mới | Không còn nhận role đã thu hồi |
| Truy cập qua API hoặc đường thay thế | Cùng chịu giới hạn quyền |
| Thực hiện trên replica khác | Không còn quyền chỉ vì cache chưa đồng bộ ngoài giới hạn chấp nhận |
| Sử dụng hiện vật tạo trong phiên admin | Hiệu lực được xử lý đúng theo thiết kế riêng |
| Tiếp tục chức năng không đặc quyền | Hoạt động nếu người dùng vẫn còn quyền nghiệp vụ hợp lệ |

Không cần khóa toàn bộ tài khoản nếu chỉ phải thu hồi một role và ứng dụng hỗ trợ phân tách phù hợp. Nhưng cũng không nên kết luận thu hồi xong chỉ vì nút admin đã biến mất.

## 13. Nhật ký và bằng chứng quản trị

Bằng chứng cần giúp trả lời: ai đã làm gì, trên phạm vi nào, bằng quyền nào, vì lý do gì, vào lúc nào và kết quả ra sao.

Một sự kiện quản trị nên có các trường phù hợp:

| Nhóm | Thông tin gợi ý |
|---|---|
| Chủ thể | Định danh người thật, danh tính thực thi, cơ chế hỗ trợ nếu có |
| Phạm vi | Ứng dụng, môi trường, tenant, tài nguyên |
| Quyền | Role, phiên kích hoạt hoặc quyết định quyền có liên quan |
| Hành động | Thao tác, thay đổi trước/sau đã rút gọn an toàn |
| Liên kết | Mã yêu cầu, mã phê duyệt, mã tương quan |
| Thời gian | Dấu thời gian có thể đối soát |
| Kết quả | Thành công, thất bại, từ chối và mã nguyên nhân phù hợp |

Không ghi mật khẩu, token, khóa riêng, toàn bộ dữ liệu cá nhân hoặc cấu hình bí mật chỉ để làm bằng chứng “đầy đủ”.

Nếu role quản trị ứng dụng có thể sửa hoặc xóa log, cần một đường thu thập và bảo vệ bằng chứng phù hợp ngoài khả năng tùy ý chỉnh sửa của role đó.

### Các thay đổi đáng giám sát

- Thêm người vào role mạnh hoặc mở rộng role definition.
- Thay mapping nhóm thành role.
- Thay chính sách SSO hoặc phương thức phục hồi tài khoản admin.
- Tạo API key hoặc tích hợp có scope lớn.
- Thay nơi nhận dữ liệu xuất.
- Sử dụng quyền ngoài phạm vi tác vụ đã duyệt.
- Thay đổi hoặc vô hiệu hóa audit.
- Nhiều lần bị từ chối truy cập ngoài tenant hoặc ngoài môi trường.

Cảnh báo cần được đối chiếu yêu cầu thay đổi và ngữ cảnh. Một thay đổi có thể hợp lệ; mục tiêu là có đủ dữ liệu để phân biệt và phản hồi.

## 14. Tình huống thực tế: đội hỗ trợ cần xử lý lỗi tích hợp

### Bối cảnh

Một hệ thống quản lý hồ sơ có hai tenant thử nghiệm A và B. Nhân viên hỗ trợ cần sửa một endpoint tích hợp của tenant A trong production. Người đó hiện chỉ có quyền đọc trạng thái.

Một giải pháp vội có thể là cấp role admin toàn cục và nhắc người dùng chỉ sửa tenant A. Cách đó không biến lời nhắc thành giới hạn kỹ thuật.

### Thiết kế phù hợp hơn

1. Xác định permission cần thiết để sửa đúng tích hợp.
2. Giới hạn scope tenant A và tập đối tượng liên quan.
3. Dùng mã thay đổi đã được chủ dịch vụ phê duyệt.
4. Kích hoạt quyền trong khoảng thời gian phù hợp tác vụ.
5. Kiểm tra lại thông tin nhạy cảm của thay đổi trước khi thực thi.
6. Ghi người thực hiện, đối tượng và kết quả.
7. Thu hồi quyền, kiểm tra phiên cũ và đối soát hiện vật phát sinh.

Nếu sản phẩm chỉ có role admin toàn cục, cần ghi nhận giới hạn, cân nhắc đường thực hiện khác hoặc ngoại lệ có thẩm quyền với kiểm soát bù. Không mô tả quyền toàn cục là quyền tenant A nếu hệ thống không thực thi được giới hạn đó.

### Kiểm thử của tình huống

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Đọc trạng thái tenant A trước kích hoạt | Thành công với quyền đọc hiện có |
| Sửa tích hợp tenant A trước kích hoạt | Bị từ chối |
| Sửa tích hợp đã duyệt sau kích hoạt | Thành công |
| Sửa tài nguyên tương tự ở tenant B | Bị từ chối |
| Cấp role admin cho tài khoản khác | Bị từ chối |
| Tạo credential ngoài nhu cầu sửa tích hợp | Bị từ chối |
| Sửa tiếp sau khi quyền bị thu hồi | Bị từ chối theo yêu cầu đã thiết kế |
| Đọc trạng thái sau thu hồi | Vẫn thành công nếu quyền đọc còn hợp lệ |

Bảng kiểm thử chứng minh cả điều được phép và giới hạn của quyền. Chỉ chạy ca thành công chưa đủ để đánh giá một role quản trị.

## 15. Những lỗi thiết kế thường gặp

### Dùng một cờ admin toàn cục

Một trường `isAdmin=true` có thể đơn giản lúc đầu nhưng khó biểu đạt môi trường, tenant, loại tài nguyên và điều kiện sử dụng.

Không phải ứng dụng nào cũng cần hệ thống chính sách phức tạp. Tuy nhiên, mô hình phải biểu đạt được các giới hạn thực tế mà tổ chức cam kết.

### Nhầm quản lý tài khoản với quản lý đặc quyền

Role hỗ trợ người dùng có thể vô tình nhận cả khả năng reset quản trị viên, thay nhóm mạnh hoặc chuyển quyền sở hữu. Cần phân tích từng thao tác và đối tượng được thao tác.

### Chỉ bảo vệ giao diện

Một menu đã ẩn nhưng API vẫn chấp nhận yêu cầu quản trị là kiểm soát không đầy đủ. Cần kiểm tra các đường thực thi thực tế, gồm bulk API, chức năng nhập dữ liệu và tác vụ nền nếu có.

### Phê duyệt chung chung

Một mã yêu cầu không gắn với đối tượng, quyền hoặc thay đổi cụ thể có thể bị tái sử dụng ngoài ý định ban đầu. Phê duyệt phải có dữ liệu đủ để đối chiếu kết quả.

### JIT tạo ra credential dài hạn

Kết thúc role nhưng giữ API key mạnh là một đường tồn dư. Phải quản lý vòng đời của các hiện vật do admin tạo.

### Không quản lý role definition

Chỉ rà soát người giữ role mà bỏ qua nội dung role sẽ không phát hiện việc role đã được mở rộng.

### Dựa vào hướng dẫn thay cho ranh giới

“Không được dùng cho tenant khác” là quy định hành vi. Nếu hệ thống vẫn cho phép, cần ghi nhận khoảng trống kiểm soát và quyết định xử lý phù hợp.

### Đánh đồng read-only với vô hại

Role đọc cấu hình có thể nhìn thấy secret hoặc dữ liệu nhạy cảm nếu sản phẩm không che phù hợp. Đánh giá theo nội dung có thể truy cập, không chỉ theo tên read-only.

## 16. Bài thực hành

### Đề bài

Thiết kế role quản trị cho ứng dụng thử nghiệm có ba nhu cầu:

- Đội vận hành sửa cấu hình dịch vụ.
- Đội hỗ trợ quản lý tài khoản người dùng thường.
- Đội bảo mật quản lý chính sách truy cập.

Ứng dụng có hai tenant và hai môi trường. Một số thao tác cần được phê duyệt trước khi thực hiện.

### Sản phẩm cần có

1. Danh mục permission mô tả thao tác và đối tượng.
2. Ma trận role với các ô cho phép, từ chối và điều kiện cụ thể.
3. Mô hình scope theo ứng dụng, môi trường và tenant.
4. Một yêu cầu cấp quyền tạm thời có chủ sở hữu và thời hạn.
5. Phân tích ít nhất hai tổ hợp quyền có thể tạo nâng quyền gián tiếp.
6. Kế hoạch thu hồi bao gồm phiên cũ và hiện vật phát sinh.
7. Bảng kiểm thử có ca thành công, từ chối, vượt tenant và sau thu hồi.
8. Mẫu sự kiện audit không chứa credential.

### Gợi ý đánh giá

Phương án đạt cần giải thích vì sao mỗi quyền tồn tại và ai chịu trách nhiệm. Vai trò hỗ trợ không được âm thầm quản lý tài khoản admin. Vai trò vận hành không tự có quyền cấp role bảo mật. Kiểm thử phải dùng danh tính có quyền đúng như thiết kế, không dùng một tài khoản quản trị mạnh hơn để thay thế.

Nếu môi trường thử nghiệm không hỗ trợ một giới hạn, ghi rõ đó là điểm chưa thực thi được. Một sơ đồ đẹp không thay cho bằng chứng backend đã chặn thao tác ngoài phạm vi.

## 17. Câu hỏi tự kiểm tra

**Application admin có mặc nhiên được đọc mọi dữ liệu nghiệp vụ không?**

Không nên mặc định như vậy trong thiết kế. Cần xác định quyền thực tế và những đường truy cập gián tiếp mà role có thể tạo.

**Tại sao thay role definition là một thay đổi đặc quyền?**

Vì quyền của toàn bộ chủ thể đang giữ role có thể thay đổi mà không phát sinh phép gán mới.

**Xác thực đa yếu tố có thay cho kiểm tra scope không?**

Không. Xác thực giúp xác định chủ thể; quyền và phạm vi vẫn phải được kiểm tra riêng.

**Khi nào một role hỗ trợ có thể trở thành đường nâng quyền?**

Khi nó cho phép điều khiển tài khoản mạnh hơn, đổi nhóm đặc quyền, chuyển ownership hoặc tạo credential có quyền vượt nhu cầu hỗ trợ.

**Vì sao role tạm thời vẫn có thể tạo truy cập dài hạn?**

Vì admin có thể tạo các hiện vật như API key, integration credential hoặc phép ủy quyền có vòng đời độc lập nếu thiết kế không giới hạn.

**Làm sao chứng minh đã thu hồi role?**

Đối soát các đường gán, phiên, token, cache và hiện vật liên quan; sau đó kiểm tra thao tác đặc quyền bị từ chối trong phạm vi và điều kiện đã đặt ra.

**Nếu sản phẩm chỉ có role admin toàn cục thì làm thế nào?**

Ghi rõ giới hạn, đánh giá phương án thực hiện khác và dùng quy trình ngoại lệ có thẩm quyền khi cần. Các kiểm soát bù phải có bằng chứng và không được mô tả như giới hạn kỹ thuật mà sản phẩm chưa có.

Một application admin role có thể quản trị được khi tổ chức biết chính xác tập năng lực của nó, phạm vi tác động, người có thể sử dụng và cách chứng minh quyền đã kết thúc sau công việc.
