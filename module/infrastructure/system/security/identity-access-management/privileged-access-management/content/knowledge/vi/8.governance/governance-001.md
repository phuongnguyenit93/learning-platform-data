# PAM policy

**PAM policy** là chính sách quản lý truy cập đặc quyền: tập quy tắc xác định ai hoặc workload nào được sử dụng quyền đặc biệt, để làm gì, trên tài nguyên nào, trong điều kiện nào và ai chịu trách nhiệm về quyết định đó.

Trong phạm vi Identity and Access Management, Privileged Access Management (PAM) bảo vệ tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Chính sách PAM nối các hoạt động kiểm kê quyền, least privilege, JIT/JEA, quản lý credential, giám sát phiên và lưu bằng chứng thành một cơ chế quản trị có thể thực thi và kiểm tra.

Một chính sách hữu ích phải giúp người vận hành đưa ra quyết định cụ thể. Câu “mọi truy cập quản trị phải an toàn” chưa đủ để biết có nên cho kỹ sư trực ca khởi động lại dịch vụ thanh toán, phải dùng danh tính nào, quyền hết hạn khi nào và xử lý ra sao nếu không thể thu hồi phiên.

## 1. Chính sách phải trả lời những câu hỏi nào

Với một hành động đặc quyền, cần trả lời tối thiểu:

- **Chủ thể:** người dùng, nhà thầu hoặc workload nào yêu cầu và sử dụng quyền.
- **Mục đích:** công việc, thay đổi hoặc sự cố nào cần quyền đó.
- **Khả năng:** hành động được phép và những hành động vượt phạm vi.
- **Tài nguyên:** hệ thống, môi trường, dữ liệu hoặc đối tượng cụ thể.
- **Điều kiện:** xác thực, phê duyệt, thiết bị, trạng thái rủi ro và đường truy cập được phép.
- **Thời gian:** khi nào được kích hoạt, được sử dụng bao lâu và cách kết thúc.
- **Trách nhiệm:** ai duyệt, vận hành, xác minh và chấp nhận ngoại lệ.
- **Bằng chứng:** dữ liệu nào chứng minh quyết định được áp dụng đúng ở đích.

Một quyết định có thể được diễn đạt theo mô hình:

```text
Cho phép chủ thể P thực hiện hành động A trên tài nguyên R
trong thời gian T, khi các điều kiện C được đáp ứng,
với danh tính thực thi E và bằng chứng B phải được tạo.
```

Không xem đăng nhập thành công là đủ để cho phép mọi hành động quản trị. Xác thực chứng minh danh tính theo cơ chế sử dụng; chính sách còn phải quyết định quyền, phạm vi và điều kiện thực thi.

## 2. Phân biệt chính sách với tiêu chuẩn và quy trình

Chính sách cần ổn định đủ để định hướng, nhưng không nên chứa toàn bộ hướng dẫn cấu hình của mọi nền tảng.

| Loại tài liệu hoặc thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Chính sách | Quy định điều bắt buộc, phạm vi, thẩm quyền và cách quản lý ngoại lệ | Quyền quản trị sản xuất phải có nhu cầu xác định, thời hạn và bằng chứng |
| Tiêu chuẩn kiểm soát | Cụ thể hóa yêu cầu theo loại tài nguyên hoặc mức rủi ro | Quy tắc xác thực, giới hạn phiên và điều kiện ghi nhận cho một nhóm hệ thống |
| Quy trình vận hành | Hướng dẫn người thực hiện theo từng tình huống | Cấp quyền trực ca, luân chuyển secret, thu hồi khi nghỉ việc |
| Cấu hình kỹ thuật | Cưỡng chế các điều kiện trên nền tảng | Role, endpoint JEA, vault policy, gateway và cơ chế hết hạn |
| Bằng chứng | Chứng minh điều gì đã xảy ra và kết quả | Phê duyệt, phiên bản policy, log phiên và xác minh thu hồi |

Ví dụ, chính sách yêu cầu credential của dịch vụ phải có chủ quản và vòng đời được kiểm soát. Tiêu chuẩn xác định phương thức phù hợp với từng backend; quy trình mô tả cập nhật các consumer; cấu hình thực hiện thao tác; bằng chứng xác nhận credential cũ không còn được chấp nhận theo yêu cầu.

Phân biệt các lớp giúp tránh hai vấn đề: một văn bản quá chung không thể áp dụng, hoặc một chính sách chứa quá nhiều chi tiết công cụ rồi nhanh chóng không còn khớp triển khai.

## 3. Xác định phạm vi bao phủ

### 3.1. Chủ thể và loại đặc quyền

Phạm vi không nên chỉ gồm tài khoản có tên `admin`. Cần bao phủ:

- Tài khoản quản trị của con người, kể cả tài khoản cục bộ và tài khoản khẩn cấp.
- Tài khoản dịch vụ, danh tính workload, service principal và danh tính triển khai.
- Nhóm, role hoặc quan hệ có thể cấp, chuyển giao hay kích hoạt đặc quyền.
- Credential có thể cho phép truy cập mạnh: mật khẩu, khóa, chứng thư, API key và token theo cơ chế áp dụng.
- Bên thứ ba và nhà cung cấp có đường truy cập tới tài nguyên của tổ chức.

Đặc quyền bao gồm quản lý hệ thống, sửa quyền truy cập, lấy bí mật, giải mã dữ liệu, triển khai mã bằng danh tính mạnh hoặc can thiệp cơ chế giám sát. Quyền chỉ đọc vẫn có thể nhạy cảm nếu làm lộ bí mật hoặc dữ liệu quan trọng.

### 3.2. Tài nguyên và đường truy cập

Cần xác định môi trường, hệ thống và đường truy cập nằm trong chính sách: directory, máy chủ, cơ sở dữ liệu, cloud, nền tảng container, thiết bị hạ tầng, vault và ứng dụng quản trị tương ứng.

Chính sách phải xét cả đường đi qua PAM và đường trực tiếp có cùng khả năng tác động. Việc đưa một tài khoản vào vault chưa chứng minh mọi lần sử dụng tài khoản đều bị kiểm soát.

Hệ thống cũ chưa tích hợp được không nên biến mất khỏi phạm vi. Cần có chủ quản, mức bao phủ hiện tại, biện pháp bù đắp, ngoại lệ có hạn và kế hoạch xử lý phù hợp.

### 3.3. Quyền của chính hệ thống PAM

Quyền sửa policy, quản lý vault, xuất dữ liệu, thay kết nối đích hoặc xóa bằng chứng của PAM cũng là đặc quyền. Cần kiểm kê và bảo vệ các quyền này thay vì chỉ kiểm soát tài khoản mà PAM quản lý.

Một người vừa có thể tự cấp quyền, sửa đường truy cập và xóa log liên quan tạo ra rủi ro tập trung. Chính sách phải xác định cách phân tách, giám sát và quản lý ngoại lệ cho các trường hợp không thể tách hoàn toàn.

## 4. Nguyên tắc nền tảng

### 4.1. Có danh tính và trách nhiệm rõ ràng

Mỗi tài khoản đặc quyền phải có mục đích và chủ quản. Tài khoản của con người cần liên kết được với người chịu trách nhiệm; tài khoản dịch vụ cần liên kết với workload và đơn vị vận hành.

Nếu nhiều người sử dụng cùng một tài khoản đích qua PAM, phải truy vết được người dùng thực tế đứng sau từng phiên hoặc hành động. Chỉ ghi tên tài khoản dùng chung không đáp ứng mục tiêu quy trách nhiệm.

### 4.2. Quyền tối thiểu và mặc định từ chối

Quyền chỉ được cấp trong phạm vi cần thiết cho nhiệm vụ. Khi chưa có căn cứ cho phép hoặc thiếu điều kiện bắt buộc, luồng thông thường không tự mở quyền.

Không dùng khả năng công cụ cho phép làm căn cứ cho nhu cầu nghiệp vụ. Một role tổng quát dễ cấu hình chưa chắc phù hợp với công việc chỉ cần thao tác một dịch vụ.

### 4.3. Thời gian và khả năng thực thi cùng được giới hạn

JIT thu hẹp khoảng thời gian có quyền. JEA thu hẹp thao tác, tham số và đối tượng được quản trị. Hai cơ chế bổ sung cho nhau và vẫn cần quyền tối thiểu ở hệ thống đích.

Một shell quản trị đầy đủ trong năm phút vẫn có thể tạo thay đổi tồn tại lâu dài. Ngược lại, một chức năng hẹp được cấp thường trực vẫn cần đánh giá nhu cầu, scope và rủi ro theo thời gian.

### 4.4. Kiểm tra kết quả ở điểm thực thi

Phê duyệt, cấu hình PAM và trạng thái tài nguyên phải được đối chiếu. Không xem một bản ghi “đã thu hồi” là bằng chứng đủ nếu token, phiên hoặc quyền trực tiếp ở đích vẫn còn khả năng sử dụng.

Chính sách phải nêu mức bằng chứng cần thiết và cách xử lý khi chưa xác minh được, thay vì mặc định mọi API thành công đều đồng nghĩa toàn bộ quyền đã thay đổi.

## 5. Phân công thẩm quyền và trách nhiệm

| Vai trò | Trách nhiệm trong chính sách |
| --- | --- |
| Chủ chính sách | Duy trì mục tiêu, yêu cầu, thẩm quyền và chu kỳ rà soát |
| Chủ tài sản hoặc dịch vụ | Xác nhận nhu cầu, tác động, scope và phụ thuộc vận hành |
| Người duyệt hoặc cơ chế duyệt được ủy quyền | Quyết định yêu cầu theo đúng thẩm quyền và điều kiện |
| Đội vận hành PAM | Triển khai, vận hành, xử lý lỗi và lưu bằng chứng |
| Người dùng hoặc chủ workload | Sử dụng đúng mục đích, bảo vệ phương tiện truy cập và báo vấn đề |
| Đội giám sát, ứng phó | Theo dõi bất thường, điều tra và phối hợp thu hồi |
| Bên đánh giá độc lập phù hợp | Kiểm tra thiết kế, hiệu lực và việc xử lý sai lệch |
| Người chấp nhận ngoại lệ | Chấp thuận rủi ro trong phạm vi thẩm quyền với thời hạn rõ ràng |

Cần xác định người thay thế khi đầu mối vắng mặt và quy tắc ủy quyền. Tránh để việc thiếu người duyệt dẫn tới tự động cấp quyền hoặc dùng một tài khoản quản trị chung ngoài kiểm soát.

Người vận hành PAM không mặc nhiên được tự duyệt nhu cầu sử dụng đặc quyền của mình. Nếu tổ chức có hạn chế nhân sự, biện pháp bù đắp và cơ chế rà soát độc lập phải được quy định rõ.

## 6. Khung điều khoản cốt lõi

Bảng dưới đây là khung minh họa để xây dựng chính sách. Tổ chức cần xác định phạm vi, mức rủi ro và cơ chế áp dụng cụ thể trước khi ban hành.

| Điều khoản mẫu | Yêu cầu | Bằng chứng chính |
| --- | --- | --- |
| Kiểm kê và ownership | Đối tượng đặc quyền trong phạm vi phải được nhận diện, có mục đích và chủ quản | Inventory, nguồn discovery, xác nhận ownership và phần chưa bao phủ |
| Xác thực | Truy cập phải dùng mức bảo đảm phù hợp; con người và workload có cơ chế kiểm chứng tương ứng | Cấu hình, sự kiện xác thực và danh tính nguồn |
| Cấp quyền | Quyền phải có nhu cầu, scope và thẩm quyền phê duyệt hoặc quy tắc tự động được chấp thuận | Yêu cầu, quyết định và phiên bản chính sách |
| Least privilege | Quyền và giao diện quản trị phải phù hợp nhiệm vụ, xét cả đường gián tiếp | Role, policy, tham số được phép và đánh giá quyền hiệu lực |
| Thời hạn | Quyền tạm thời phải có mốc hết hạn, giới hạn gia hạn và cơ chế cưỡng chế | Lịch hiệu lực, sự kiện áp dụng, xác minh hết hạn |
| Credential | Bí mật phải được bảo vệ, giới hạn truy xuất và quản lý vòng đời | Tham chiếu nơi quản lý, log sử dụng và trạng thái luân chuyển/thu hồi |
| Phiên và hành động | Hoạt động đặc quyền phải có bằng chứng phù hợp với giao thức và rủi ro | Log phiên, sự kiện API, hành động ở đích và liên kết danh tính |
| Vòng đời danh tính | Thay đổi công việc, kết thúc hợp đồng hoặc ngừng dịch vụ phải kích hoạt rà soát, thu hồi phù hợp | Sự kiện vòng đời, quyết định và kết quả tại đích |
| Ngoại lệ và khẩn cấp | Sai khác được chấp thuận phải có thẩm quyền, scope, biện pháp bù đắp và hạn | Hồ sơ ngoại lệ, log sử dụng và rà soát sau sự kiện |
| Rà soát và thay đổi | Policy và triển khai phải được rà soát, quản lý phiên bản và xử lý sai lệch | Lịch sử thay đổi, kiểm chứng, kết quả đối soát và quyết định xử lý |

Khi viết điều khoản, nên dùng ngôn ngữ rõ ràng. “Phải” là yêu cầu bắt buộc trong phạm vi áp dụng; “nên” là khuyến nghị có lý do; ngoại lệ chỉ có hiệu lực khi đáp ứng quy trình tương ứng. Tránh dùng “thường xuyên”, “đủ mạnh” hoặc “kịp thời” mà không có tiêu chí cụ thể ở chính sách hoặc tiêu chuẩn được tham chiếu.

## 7. Quyết định theo rủi ro

### 7.1. Phân loại hành động và bối cảnh

Mức kiểm soát nên dựa trên tác động nếu quyền bị sử dụng sai, phạm vi tài sản, độ nhạy dữ liệu, danh tính đích và khả năng đảo ngược thay đổi.

Một hành động đọc trạng thái không chứa dữ liệu nhạy cảm có thể cần kiểm soát khác hành động sửa IAM hoặc lấy khóa. Tuy nhiên, “chỉ đọc” không mặc nhiên là rủi ro thấp nếu đầu ra chứa bí mật.

Có thể xác định các tầng kiểm soát như sau:

| Tình huống | Cách thiết kế kiểm soát cần xem xét |
| --- | --- |
| Quan sát một dịch vụ, đầu ra đã giới hạn | Vai trò hẹp, xác thực phù hợp, log truy cập; tự động duyệt nếu có chính sách cho phép |
| Thay đổi vận hành trên production | Nhiệm vụ rõ, scope cụ thể, JIT, phê duyệt theo thẩm quyền và giám sát |
| Sửa cấp quyền, credential hoặc cơ chế bảo vệ | Phân tách nhiệm vụ, kiểm tra tác động và bằng chứng chi tiết hơn |
| Khôi phục khẩn cấp khi đường thông thường không hoạt động | Cơ chế break-glass đã thiết kế, scope và thời hạn riêng, cảnh báo và rà soát sau sử dụng |

Không cần bắt buộc con người duyệt mọi yêu cầu nếu chính sách cho phép tự động hóa trong phạm vi đã đánh giá. Nhưng quyết định tự động phải dựa trên điều kiện rõ, có phiên bản và lưu được lý do cho phép hoặc từ chối.

### 7.2. Không áp dụng cùng một cơ chế xác thực cho mọi chủ thể

Với con người, chính sách có thể yêu cầu MFA và các điều kiện thiết bị hoặc phiên phù hợp với mức rủi ro. Khi cần xác thực tăng cường, phải xác định thao tác nào kích hoạt yêu cầu và bằng chứng được chấp nhận.

Với workload, cần dùng danh tính và phương thức xác thực được hỗ trợ: ví dụ quan hệ tin cậy, chứng thư hoặc credential ngắn hạn được ràng buộc với môi trường chạy. Không áp dụng MFA tương tác như một yêu cầu hình thức cho tác vụ máy chạy không có người tham gia.

Tài khoản dịch vụ không nên trở thành đường đăng nhập quản trị tùy ý của con người. Nếu có nhu cầu vận hành đặc biệt, cần quy định đường sử dụng, thẩm quyền và khả năng truy vết.

### 7.3. Nêu rõ cách xử lý khi thiếu điều kiện

Nếu không xác minh được điều kiện bắt buộc như phê duyệt, hiệu lực danh tính hoặc scope, luồng thông thường không tự cho phép. Chính sách phải định nghĩa phản ứng với lỗi phụ thuộc, thiếu log hoặc hệ thống PAM không sẵn sàng.

Khả năng tiếp tục một phiên đã được cấp cần được thiết kế riêng: kiểm tra nào ở lúc tạo phiên, kiểm tra nào lặp lại, thời hạn nào được cưỡng chế tại đích. Không mặc định sự cố hệ thống điều khiển làm mọi quyền được gia hạn.

Nếu cần duy trì khả năng khôi phục dịch vụ khi PAM gặp sự cố, cơ chế khẩn cấp phải được chuẩn bị và kiểm chứng trước. Không để đường dự phòng trở thành một tài khoản quản trị thường trực thiếu giám sát.

## 8. Chính sách cho vòng đời cấp quyền

### 8.1. Yêu cầu và phê duyệt

Một yêu cầu cần xác định chủ thể hưởng quyền, nhiệm vụ, hành động hoặc role, tài nguyên, thời gian, điều kiện và mức rủi ro. Người duyệt phải có đủ thông tin để đánh giá phần quyền được xin.

Quyết định phải gắn với nội dung cụ thể và phiên bản tương ứng. Thay đổi role, scope hoặc thời gian sau phê duyệt cần được xử lý theo quy tắc đánh giá lại; không mặc định phê duyệt cũ bao phủ nội dung mới.

Mã phiếu được nhập vào một ô không tự chứng minh phê duyệt hợp lệ. Cần đối chiếu với nguồn có thẩm quyền, trạng thái nhiệm vụ, người được giao và thời hạn tương ứng.

### 8.2. Kích hoạt và sử dụng

Trước khi áp dụng, hệ thống cần kiểm tra điều kiện còn đạt và yêu cầu chưa hết hiệu lực hoặc bị thu hồi. Chỉ báo quyền đã hoạt động khi có kết quả phù hợp từ thành phần cưỡng chế.

Ví dụ, thời hạn hiển thị trong PAM, thành viên nhóm tạm thời và khả năng sử dụng endpoint có thể là ba trạng thái khác nhau. Chính sách cần xác định trạng thái nào là căn cứ cho phép tiếp tục công việc và trạng thái nào cần đối soát.

Hoạt động phải tuân theo phạm vi được cấp. Người dùng không tự chuyển từ tác vụ khởi động lại dịch vụ sang sửa cấu hình bảo mật vì đang có một phiên quản trị.

### 8.3. Gia hạn

Gia hạn là quyết định tiếp tục cấp quyền. Cần tái đánh giá nhu cầu, danh tính, trạng thái rủi ro, scope và giới hạn thời gian tích lũy. Chính sách phải có giới hạn mỗi lần, tổng thời lượng hoặc điều kiện khác phù hợp để tránh duy trì quyền vô hạn.

Một yêu cầu gửi trước hạn nhưng được duyệt sau khi quyền đã hết không tự tạo hiệu lực hồi tố. Nếu phạm vi thay đổi hoặc quyền không còn hoạt động, phải dùng luồng đánh giá phù hợp thay vì chỉ sửa mốc hết hạn.

### 8.4. Thu hồi và kết thúc

Cần quy định các tác nhân thu hồi: hết hạn, nhiệm vụ kết thúc, thay đổi vai trò công việc, hợp đồng kết thúc, workload ngừng dùng, vi phạm điều kiện hoặc nghi bị chiếm quyền.

Thu hồi phải xét assignment, đường truy cập, phiên, token và credential theo cơ chế áp dụng. Gỡ thành viên nhóm không bảo đảm mọi phiên đã mở mất quyền ngay; đổi mật khẩu cũng không mặc nhiên đóng mọi kết nối đã xác thực.

Khi chưa xác minh được kết quả, trạng thái phải thể hiện còn việc cần xử lý. Chính sách cần xác định người chịu trách nhiệm, thời hạn xử lý và cơ chế nâng cấp sự cố theo tác động.

## 9. Credential, workload và bằng chứng sử dụng

### 9.1. Quản lý credential theo cơ chế thực tế

Credential dài hạn còn cần dùng phải được bảo vệ trong cơ chế quản lý phù hợp, với quyền truy xuất và mục đích rõ ràng. Không lưu mật khẩu hoặc private key trong inventory, phiếu yêu cầu hay log phiên.

Không phải mọi role cloud đều có mật khẩu để đưa vào vault. Với danh tính liên kết, khóa không xuất được hoặc credential ngắn hạn, chính sách cần quản lý nguồn cấp, quan hệ tin cậy và quyền sử dụng tương ứng.

Chu kỳ và điều kiện luân chuyển phải phù hợp loại credential, backend, mức rủi ro và nhu cầu vận hành. Không áp một con số ngày chung cho mọi bí mật mà không xét khả năng cập nhật consumer hoặc cơ chế thu hồi.

Luân chuyển phải bao gồm xác minh đích, nơi quản lý và các consumer liên quan. Nếu nghi bị lộ, cần quy trình xử lý sự cố phù hợp; không chờ tới lịch luân chuyển định kỳ chỉ vì lịch chưa đến.

### 9.2. Ghi nhận theo loại hoạt động

Phiên tương tác có thể có bản ghi phiên hoặc transcript; tác vụ tự động có thể cần sự kiện API, danh tính workload, mã triển khai và kết quả tại đích. Chính sách cần xác định bằng chứng đáp ứng mục tiêu thay vì yêu cầu cùng một hình thức cho mọi giao thức.

Nên liên kết người yêu cầu, danh tính thực thi, tài nguyên, tác vụ, thời gian, quyết định và phiên bản chính sách. Bằng chứng phê duyệt không thay thế bằng chứng thực thi; bản ghi phiên cũng không thay thế mọi log trên tài nguyên.

Phải kiểm soát dữ liệu nhạy cảm trong nội dung ghi nhận, quyền xem, quyền xuất và quyền xóa. Thời gian lưu, mục đích sử dụng và phạm vi thu thập cần được xác định theo yêu cầu áp dụng của tổ chức và loại dữ liệu, rồi thể hiện trong tiêu chuẩn vận hành.

## 10. Ví dụ chính sách cho thao tác dịch vụ production

Giả sử đội trực ca cần kiểm tra và khởi động lại `ContosoBillingAgent` trên `APP-PAY-02`. Một bộ quy tắc minh họa có thể gồm:

| Thuộc tính | Quy tắc trong ví dụ |
| --- | --- |
| Chủ thể | Thành viên nhóm trực ca đã được xác nhận và được phân công nhiệm vụ |
| Hành động | Xem trạng thái và khởi động lại đúng dịch vụ đã giao |
| Phạm vi | Chỉ `APP-PAY-02` trong môi trường production |
| Xác thực | Người dùng đáp ứng yêu cầu MFA và điều kiện phiên của nhóm tài sản này |
| Phê duyệt | Chủ dịch vụ hoặc người được ủy quyền phù hợp, độc lập với người yêu cầu |
| Giao diện | Endpoint JEA hoặc chức năng tương đương chỉ cung cấp các thao tác cần thiết |
| Credential | Do thành phần được phép sử dụng; người trực ca không mặc nhiên được xem bí mật |
| Thời gian | Ba mươi phút ban đầu; tổng thời lượng không quá sáu mươi phút nếu gia hạn hợp lệ |
| Ghi nhận | Yêu cầu, quyết định, người dùng, danh tính thực thi, hành động và kết quả tại đích |
| Kết thúc | Ngăn sử dụng tiếp theo thời hạn, xử lý phiên liên quan và xác minh theo cơ chế endpoint |

Các giá trị thời lượng chỉ phục vụ ví dụ; không phải mức chuẩn áp dụng cho mọi tác vụ PAM.

Một yêu cầu hợp lệ được kích hoạt lúc 09:00 có mốc hết hạn ban đầu 09:30. Nếu cần thêm thời gian, người dùng phải dùng quy trình gia hạn, không tự giữ quyền bằng cách mở thêm phiên hoặc xin liên tiếp các yêu cầu để bỏ qua giới hạn tổng.

Nếu kỹ sư cần sửa cấu hình hoặc chuyển sang máy chủ khác, yêu cầu đó vượt scope của quy tắc này và cần đánh giá phù hợp. Việc đang xử lý cùng một sự cố không tự mở rộng quyền.

Triển khai phải bảo đảm không có đường quản trị trực tiếp tương đương làm vô hiệu hóa giới hạn của endpoint, hoặc đường đó phải được quản lý rõ như một phạm vi hay ngoại lệ riêng. Quyền của danh tính thực thi ở đích cũng cần được giới hạn theo nhiệm vụ.

Trong kiểm toán, một bộ bằng chứng cần nối được yêu cầu với phiên bản quy tắc, kết quả áp dụng tại endpoint, hành động đã thực hiện và trạng thái kết thúc. Chỉ có ảnh chụp biểu mẫu phê duyệt không đủ trả lời toàn bộ chuỗi này.

## 11. Ngoại lệ, break-glass và bên thứ ba

### 11.1. Ngoại lệ có thời hạn

Ngoại lệ là quyết định cho phép sai khác một hoặc nhiều yêu cầu trong phạm vi xác định. Hồ sơ cần nêu điều khoản liên quan, lý do, tài sản, principal, tác động, người chịu trách nhiệm, người chấp thuận, biện pháp bù đắp và mốc kết thúc hoặc rà soát.

Không dùng ngoại lệ chung kiểu “ứng dụng cũ” để miễn mọi kiểm soát. Có thể chưa hỗ trợ ghi hình phiên nhưng vẫn phải xác định hình thức log thay thế, giới hạn người dùng và phương án giảm rủi ro phù hợp.

Khi hết hạn, ngoại lệ cần được đóng, đánh giá lại hoặc chuyển sang quyết định mới theo thẩm quyền. Gia hạn ngoại lệ tự động không có đánh giá có thể tạo ra quyền thường trực ngoài chính sách.

### 11.2. Break-glass

Break-glass là đường truy cập khẩn cấp được chuẩn bị để xử lý tình huống đáp ứng điều kiện đã quy định, ví dụ cần khôi phục khi đường truy cập thông thường không dùng được. Nó không phải cách bỏ qua quy trình vì người duyệt đang bận.

Chính sách cần xác định:

- Ai đủ điều kiện sử dụng, tiêu chí kích hoạt và scope tối đa.
- Cách xác thực và bảo vệ phương tiện khôi phục khi một số thành phần không sẵn sàng.
- Thời hạn, cảnh báo và loại bằng chứng vẫn phải thu thập.
- Cách kết thúc quyền, xử lý credential và các phiên sau sử dụng.
- Người rà soát, dữ liệu phải cung cấp và cách xử lý dấu hiệu lạm dụng.

Nếu cơ chế ghi nhận chính không hoạt động, phải có cách xử lý được định nghĩa trước cho tình huống đó. Không ngầm bỏ hết bằng chứng; cũng không thiết kế đường khôi phục phụ thuộc duy nhất vào chính thành phần đang cần được khôi phục.

### 11.3. Truy cập của bên thứ ba

Quyền của nhà thầu hoặc nhà cung cấp cần gắn với danh tính, đơn vị bảo trợ, nhiệm vụ và thời hạn hợp đồng hoặc phiên công việc. Quyền từ xa thường trực chỉ vì thuận tiện hỗ trợ phải được đánh giá như một quyết định rủi ro.

Quy trình cần xử lý thay đổi nhân sự bên cung cấp, chấm dứt hợp đồng, sự cố của bên liên quan và xác minh thu hồi ở hệ thống đích. Tài khoản dùng chung của cả nhà cung cấp không tự tạo khả năng truy trách nhiệm từng người.

## 12. Quản lý phiên bản và đưa chính sách vào thực thi

### 12.1. Quản trị văn bản

Một policy cần có định danh, phiên bản, chủ quản, người hoặc cơ chế phê chuẩn, phạm vi, ngày hiệu lực, lịch sử thay đổi và điều kiện rà soát. Tài liệu liên quan phải có cách tham chiếu đủ rõ để biết yêu cầu nào áp dụng tại một thời điểm.

Khi thay đổi chính sách, cần đánh giá ảnh hưởng tới người dùng, workload, đường khôi phục và phiên đang tồn tại. Có thể cần chuyển đổi theo giai đoạn hoặc ngoại lệ chuyển tiếp có hạn, thay vì để văn bản và cấu hình không khớp mà không có trách nhiệm xử lý.

### 12.2. Nối điều khoản với cấu hình

Mỗi yêu cầu quan trọng nên có liên kết tới thành phần thực hiện và bằng chứng kiểm tra. Ví dụ, giới hạn thời gian cần được nối tới cơ chế cấp quyền, gateway hoặc endpoint, chứ không chỉ tới một nhãn trên giao diện.

Policy-as-code có thể giúp quản lý phiên bản, kiểm tra và triển khai quy tắc, nhưng mã cấu hình không tự thay thế thẩm quyền, mục tiêu quản trị và quy trình ngoại lệ. Cũng phải kiểm soát ai được sửa mã, phê duyệt và triển khai thay đổi có ảnh hưởng đặc quyền.

Trước khi áp dụng thay đổi, cần có phương án khôi phục phù hợp. Quay lại một phiên bản cấu hình cũ không được vô tình phục hồi quyền đã bị thu hồi vì sự cố hoặc tiếp tục chấp nhận một credential bị lộ.

### 12.3. Kiểm chứng thiết kế và hiệu lực

Các tình huống dưới đây gợi ý cách kiểm chứng trong môi trường triển khai; chúng không phải kết quả kiểm thử của một hệ thống cụ thể.

| Tình huống | Kết quả cần kiểm tra |
| --- | --- |
| Yêu cầu đúng người, tác vụ và thời gian | Chỉ cấp đúng khả năng được phép |
| Đổi scope sau phê duyệt | Phát hiện nội dung thay đổi, không dùng lại phê duyệt sai phạm vi |
| Người dùng tự duyệt khi không có thẩm quyền | Bị từ chối |
| Workload hợp lệ cần credential ngắn hạn | Được xử lý theo chính sách danh tính máy, không ép MFA tương tác |
| Quyền hết hạn nhưng phiên còn mở | Hành vi phù hợp với quy tắc kết thúc và cơ chế cưỡng chế |
| Hệ thống phê duyệt hoặc PAM lỗi | Không ngầm mở rộng quyền; đường khẩn cấp tuân theo điều kiện riêng |
| Credential cũ bị thu hồi trong lúc thay đổi cấu hình | Cấu hình mới không làm credential đó hoạt động trở lại |
| Một đường truy cập trực tiếp bỏ qua PAM | Được phát hiện và xử lý theo scope hoặc ngoại lệ |
| Log chứa dữ liệu nhạy cảm hoặc thiếu sự kiện | Phát hiện và xử lý theo yêu cầu ghi nhận, bảo vệ dữ liệu |

Không chỉ kiểm tra trường hợp được phép. Các trường hợp bị từ chối, dữ liệu thiếu, xung đột trạng thái và lỗi tích hợp mới cho thấy ranh giới chính sách có được giữ khi hệ thống gặp vấn đề hay không.

## 13. Đo hiệu lực và rà soát chính sách

Chính sách cần được đánh giá bằng cả độ bao phủ và kết quả vận hành. Các chỉ số có thể gồm:

- Tỷ lệ đối tượng đặc quyền đã biết có chủ quản và mục đích được xác nhận.
- Tỷ lệ tài sản nằm trong phạm vi đã được discovery và đối soát thành công.
- Quyền mạnh thường trực, quyền không sử dụng và quyền vượt phạm vi phê duyệt đã xác minh.
- Độ trễ từ quyết định thu hồi tới xác minh tại đích, gồm những trường hợp còn phiên hoặc token.
- Ngoại lệ quá hạn, break-glass chưa được rà soát và sai lệch lặp lại.
- Tỷ lệ bằng chứng không đầy đủ hoặc không nối được người yêu cầu với hành động.

Phải nói rõ mẫu số và phạm vi quan sát. Tỷ lệ một trăm phần trăm tài khoản đã có trong PAM không chứng minh toàn bộ tổ chức được bao phủ nếu discovery còn thiếu hệ thống hoặc đường truy cập.

Không dùng số lượng phê duyệt hoặc tỷ lệ chấp thuận như thước đo duy nhất. Quy trình có thể tạo nhiều phiếu nhưng vẫn cấp quyền quá rộng, hoặc gây chậm trễ khiến người dùng tìm đường ngoài kiểm soát.

Rà soát cần được thực hiện theo chu kỳ tổ chức quy định và khi có thay đổi quan trọng: sự cố, hệ thống mới, mô hình danh tính mới, thay đổi chủ sở hữu, phát hiện đường truy cập ngoài dự kiến hoặc bằng chứng kiểm soát không còn hiệu quả.

Kết quả rà soát phải dẫn tới quyết định có chủ quản: điều chỉnh scope, thu hẹp role, cải thiện quy trình, sửa cơ chế cưỡng chế hoặc xử lý ngoại lệ. Một chính sách được quản lý tốt nối được yêu cầu quản trị với hành vi tại tài nguyên và bằng chứng về toàn bộ vòng đời đặc quyền.
