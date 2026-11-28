# Vendor access review

## 1. Rà soát quyền truy cập nhà cung cấp nhằm trả lời điều gì?

Nhà cung cấp thường cần truy cập đặc quyền để bảo trì hệ thống, khắc phục sự cố hoặc hỗ trợ một sản phẩm. Một lần phê duyệt hợp lệ ở thời điểm cấp quyền không có nghĩa là quyền đó tiếp tục cần thiết nhiều tháng sau. Kỹ sư có thể đã chuyển nhóm, hợp đồng đã hết hạn, hệ thống đã đổi chủ hoặc phương thức hỗ trợ từ xa đã thay đổi.

**Vendor access review** là hoạt động kiểm tra có bằng chứng để xác định quyền truy cập hiện tại của từng người hoặc danh tính máy thuộc nhà cung cấp còn phù hợp hay không. Kết quả phải dẫn tới một quyết định cụ thể và được thực thi: giữ quyền có thời hạn, thu hẹp quyền, tạm đình chỉ, thu hồi hoặc chuyển sang xử lý sự cố.

Trong PAM, đối tượng được rà soát không chỉ là tài khoản đăng nhập. Phạm vi còn bao gồm entitlement trên vault, khả năng lấy credential, chính sách JIT/JEA, tài khoản đích, đường đi qua jump host, phiên đang mở, SSH key, token và các cơ chế truy cập trực tiếp có thể vượt qua PAM.

Một đợt review tốt phải trả lời được các câu hỏi sau:

- Ai đang có khả năng truy cập, và người đó thuộc tổ chức nào?
- Ai trong nội bộ chịu trách nhiệm về nhu cầu và phạm vi truy cập?
- Quyền được phép theo hồ sơ có khớp với quyền hiệu lực trên hệ thống không?
- Quyền đã được sử dụng cho công việc nào, trong thời gian nào?
- Có quyền dư thừa, credential tồn lưu hoặc phiên chưa kết thúc không?
- Quyết định sau review đã có hiệu lực trên các điểm thực thi hay mới tồn tại trong ticket?

**Không có bằng chứng sử dụng** và **không còn nhu cầu sử dụng** là hai kết luận khác nhau. Một quyền chưa được dùng có thể là quyền dự phòng hợp lệ. Ngược lại, một quyền được dùng thường xuyên vẫn có thể quá rộng hoặc không được phê duyệt.

## 2. Phân biệt review với các hoạt động liên quan

| Hoạt động | Câu hỏi chính | Đầu ra cần có |
|---|---|---|
| Phê duyệt truy cập | Công việc dự kiến có được phép thực hiện không? | Phạm vi, thời hạn, người phê duyệt |
| Cấp quyền | Cấu hình nào cho phép thực hiện công việc? | Entitlement và điều kiện kỹ thuật |
| Giám sát phiên | Hoạt động đang diễn ra có phù hợp không? | Sự kiện, cảnh báo, can thiệp khi cần |
| Vendor access review | Quyền hiện hữu còn cần thiết và đúng phạm vi không? | Quyết định cùng bằng chứng thực thi |
| Offboarding | Làm thế nào chấm dứt mọi khả năng truy cập? | Thu hồi đã được xác minh |
| Điều tra sự cố | Điều gì đã xảy ra và ảnh hưởng đến đâu? | Bằng chứng, phạm vi ảnh hưởng, biện pháp ứng phó |

Review có thể phát hiện dấu hiệu sự cố, nhưng không thay thế quy trình ứng phó sự cố. Nếu thấy truy cập trái phép, credential bị lộ hoặc hoạt động đáng ngờ đang diễn ra, cần kích hoạt xử lý theo mức độ rủi ro; không chờ đến ngày đóng đợt review định kỳ.

Review cũng không chỉ là việc chủ hệ thống bấm “Approve” cho một danh sách tài khoản. Nếu danh sách thiếu tài khoản đích hoặc không thể hiện quyền kế thừa, thao tác xác nhận chỉ chứng minh rằng người review đã xem một tập dữ liệu chưa đầy đủ.

## 3. Xác định đúng đơn vị rà soát

### 3.1. Không chỉ review tên nhà cung cấp

Một nhà cung cấp có thể có nhiều hợp đồng, nhiều nhóm hỗ trợ và nhiều kỹ sư. Một kỹ sư có thể truy cập nhiều môi trường với các vai trò khác nhau. Nếu chỉ ghi “Nhà cung cấp A — giữ quyền”, rất khó biết quyết định đó áp dụng cho ai và cho quyền nào.

Đơn vị quyết định nên đủ chi tiết để truy vết:

> Nhà cung cấp → danh tính cụ thể → đường truy cập → entitlement → tài nguyên hoặc nhóm tài nguyên có cùng điều kiện kiểm soát.

Ví dụ:

~~~text
Nhà cung cấp: Atlas Support
Danh tính: atlas.nguyen-an
Nhà tài trợ nội bộ: owner-erp
Đường truy cập: IdP → PAM gateway → jump host → máy chủ ERP
Entitlement: erp-prod-diagnostics
Tài nguyên: erp-app-01, erp-app-02
Khả năng được cấp: xem trạng thái dịch vụ và đọc log đã giới hạn
Điều kiện: MFA, ticket được duyệt, JIT 60 phút, ghi phiên
Ngày hết hạn eligibility: 2026-12-15
~~~

Đây là dữ liệu minh họa. Tên chính sách và thời hạn phải được điều chỉnh theo hệ thống và nhu cầu thực tế.

Không nhất thiết tạo một phiếu riêng cho từng máy nếu nhiều máy có cùng chủ sở hữu, cùng vai trò và cùng điều kiện kiểm soát. Tuy nhiên, quyết định nhóm phải cho biết rõ danh sách thành viên ở thời điểm review; không dùng một tên nhóm mơ hồ để bao phủ các tài nguyên mới xuất hiện sau đó.

### 3.2. Phân biệt eligibility và quyền đang hoạt động

Trong mô hình JIT, người dùng có thể chưa có quyền quản trị hiện tại nhưng vẫn có eligibility để xin kích hoạt quyền. Vì vậy, “không có grant đang mở” chưa đủ để kết luận không có khả năng truy cập đặc quyền.

Cần review riêng:

- **Eligibility:** ai có thể yêu cầu hoặc tự kích hoạt loại quyền nào.
- **Activation:** quyền nào đã được kích hoạt, theo phê duyệt nào, đến bao giờ.
- **Credential access:** ai có thể xem, checkout hoặc nhận credential.
- **Session:** phiên nào đang hoạt động và quyền thực tế trong phiên đó.
- **Residual access:** credential, key, token hoặc tài khoản đích còn dùng được ngoài luồng dự kiến.

Một kỹ sư hết hợp đồng có thể không có phiên mở nhưng vẫn còn eligibility. Một kỹ sư bị xóa khỏi nhóm PAM có thể vẫn giữ SSH key trên máy đích. Hai trường hợp đều cần hành động, nhưng điểm thực thi khác nhau.

### 3.3. Phân biệt danh tính người và danh tính máy

Tài khoản dịch vụ do nhà cung cấp vận hành không nên được gộp vào phiếu xác nhận của một kỹ sư. Danh tính máy cần chủ sở hữu nội bộ, mục đích tích hợp, phạm vi API hoặc hệ thống đích, nơi lưu secret và quy trình luân chuyển riêng.

Khi kỹ sư rời dự án, có thể phải thu hồi quyền của người đó trên vault và luân chuyển secret mà họ từng có khả năng biết. Không được mặc định xóa ngay tài khoản dịch vụ đang phục vụ một tích hợp sản xuất mà chưa xác định tác động và phương án thay thế.

## 4. Vai trò và trách nhiệm

Review cần có người chịu trách nhiệm về nhu cầu nghiệp vụ và người chịu trách nhiệm về việc thay đổi kỹ thuật. Nếu cả hai vai trò đều bị gán chung cho “đội PAM”, hệ thống có thể được cấu hình đúng nhưng vẫn giữ quyền không còn cần thiết.

| Vai trò | Trách nhiệm chính |
|---|---|
| Nhà tài trợ nội bộ | Xác nhận nhà cung cấp và từng người còn được giao công việc |
| Chủ hệ thống hoặc chủ dữ liệu | Xác nhận tài nguyên, thao tác và mức quyền cần thiết |
| Đội IAM/PAM | Cung cấp inventory, thực thi thay đổi và lưu bằng chứng kỹ thuật |
| Đội vận hành đích | Xác minh quyền trên hệ điều hành, cơ sở dữ liệu hoặc thiết bị |
| Đội an ninh/SOC | Đối chiếu cảnh báo và chuyển dấu hiệu bất thường sang xử lý phù hợp |
| Đầu mối nhà cung cấp | Xác nhận danh sách nhân sự, vai trò và thay đổi bên ngoài |
| Người điều phối review | Theo dõi thời hạn, tồn đọng, ngoại lệ và điều kiện đóng |

Nhà cung cấp có thể xác nhận kỹ sư nào còn thuộc nhóm hỗ trợ, nhưng quyết định cho phép truy cập tài sản của doanh nghiệp cần người có thẩm quyền phía doanh nghiệp. Việc nhà cung cấp tự xác nhận không thay thế phê duyệt của chủ hệ thống.

Với quyền có ảnh hưởng lớn, nên tách người đề nghị, người quyết định và người thực thi khi khả thi. Nếu tổ chức nhỏ không thể tách hoàn toàn, cần ghi rõ giới hạn đó và có một bước kiểm tra độc lập tương xứng.

## 5. Khi nào cần review?

### 5.1. Review định kỳ theo rủi ro

Tần suất nên phản ánh độ nhạy cảm của tài nguyên, mức quyền, khả năng lấy credential, phạm vi mạng và chất lượng giám sát. Quyền quản trị môi trường sản xuất cần được xem xét chặt hơn quyền đọc thông tin hỗ trợ trong môi trường thử nghiệm.

Có thể xây dựng các nhóm rủi ro để tổ chức lịch review, nhưng không nên xem một chu kỳ minh họa như yêu cầu áp dụng cho mọi hệ thống. Điều quan trọng là mỗi nhóm có người sở hữu, lịch được phê duyệt và cách xử lý khi quá hạn.

JIT giúp giảm thời gian tồn tại của quyền đang hoạt động; nó không loại bỏ nhu cầu review eligibility, chính sách phê duyệt và danh sách tài nguyên được phép.

### 5.2. Review theo sự kiện

Không chờ chu kỳ định kỳ khi xảy ra các thay đổi có ảnh hưởng trực tiếp:

- Kết thúc, gia hạn hoặc thay đổi phạm vi hợp đồng.
- Thay người hỗ trợ, chuyển nhóm hoặc sử dụng nhà thầu phụ.
- Hoàn tất dự án, chuyển giao vận hành hoặc ngừng một dịch vụ.
- Thay đổi chủ hệ thống, mức nhạy cảm dữ liệu hoặc kiến trúc truy cập.
- Phát hiện tài khoản dùng chung, MFA không còn phù hợp hoặc đường truy cập trực tiếp.
- Có cảnh báo đăng nhập, hành vi phiên hoặc checkout credential bất thường.
- Không liên lạc được với nhà tài trợ nội bộ hoặc không xác nhận được người dùng.

Sự kiện nhân sự phải tác động tới đúng danh tính và các quyền liên quan, không chỉ cập nhật tên đầu mối trong hồ sơ hợp đồng.

### 5.3. Khi người review không phản hồi

“Không phản hồi” là trạng thái chưa giải quyết, không phải một sự đồng ý ngầm. Quy trình cần có nhắc việc, chuyển cấp và thời hạn xử lý.

Có thể áp dụng tạm đình chỉ hoặc để quyền tự hết hạn khi chưa được tái xác nhận, tùy chính sách và khả năng duy trì dịch vụ. Với một tích hợp quan trọng, cần điều phối biện pháp thay thế để tránh làm gián đoạn ngoài dự kiến. Mọi trường hợp tiếp tục duy trì quyền phải có người chấp nhận rủi ro, lý do, kiểm soát bù và ngày hết hạn rõ ràng.

## 6. Chuẩn bị dữ liệu và bằng chứng

### 6.1. Inventory phải bao phủ toàn bộ đường truy cập

Nguồn PAM thể hiện entitlement trong PAM, nhưng không tự chứng minh tất cả quyền ngoài PAM đã được thu hồi. Một đợt review cần đối chiếu các nguồn phù hợp với kiến trúc đang dùng.

| Nguồn | Thông tin cần lấy | Điểm cần thận trọng |
|---|---|---|
| Hồ sơ hợp đồng và công việc | Thời hạn, phạm vi, đầu mối, nhà tài trợ | Hợp đồng còn hiệu lực không đồng nghĩa mọi người còn cần quyền |
| IdP/directory | Danh tính, nhóm, trạng thái, phương thức xác thực | Có thể còn token hoặc phiên cũ sau khi thay đổi nhóm |
| PAM | Eligibility, grant, chính sách, checkout, phiên | Có thể không thấy đường truy cập trực tiếp |
| Vault | Quyền trên secret, lịch sử truy xuất, phiên bản secret | Không đưa giá trị secret vào hồ sơ review |
| Hệ thống đích | Local account, role, nhóm, key, quyền kế thừa | Quyền hiệu lực có thể rộng hơn tên role |
| VPN/gateway/firewall | Đường kết nối và phạm vi mạng | Chặn mạng không thu hồi credential đã bị lấy |
| Ticket và nhật ký thay đổi | Mục đích, người duyệt, thời điểm | Ticket tồn tại chưa chứng minh hành vi nằm trong phạm vi |
| Nhật ký an ninh và phiên | Đăng nhập, hành động, cảnh báo, kết thúc phiên | Thiếu log không đồng nghĩa không có hoạt động |

Các nguồn cần được liên kết bằng định danh ổn định nếu có. Chỉ nối dữ liệu bằng tên hiển thị hoặc địa chỉ email có thể gây nhầm khi đổi tên, tái sử dụng email hoặc có nhiều tài khoản tương tự.

### 6.2. Ghi rõ thời điểm và mức đầy đủ

Mỗi gói dữ liệu cần có thời điểm chụp, khoảng thời gian của log, môi trường và nguồn xuất. Ví dụ, inventory entitlement lúc 09:00 và danh sách phiên lúc 15:00 không phải một ảnh chụp đồng thời.

Trong quá trình review, quyền có thể tiếp tục thay đổi. Vì vậy cần:

1. Ghi lại phiên bản hoặc thời điểm snapshot.
2. Ghi nhận các thay đổi phát sinh sau snapshot.
3. Đối chiếu lại quyền và phiên trước khi đóng.
4. Chuyển quyền mới phát sinh vào review bổ sung nếu chúng nằm ngoài quyết định đã có.

Nếu một connector lỗi, một máy chủ chưa được quét hoặc log bị thiếu, cần ghi rõ phần thiếu. Không đánh dấu “không phát hiện quyền dư” như thể toàn bộ phạm vi đã được kiểm tra.

### 6.3. Thu thập bằng chứng vừa đủ

Hồ sơ review nên tham chiếu tới bản ghi được kiểm soát truy cập, thay vì sao chép toàn bộ log và bản ghi phiên vào email. Nội dung phiên có thể chứa dữ liệu nhạy cảm hoặc thông tin của khách hàng.

Chỉ đưa vào hồ sơ những trường cần để ra quyết định: định danh, tài nguyên, quyền, thời gian, ticket, kết quả và tham chiếu bằng chứng. Không lưu mật khẩu, private key hoặc token thô. Việc lưu giữ, truy cập và xóa bằng chứng phải theo chính sách của tổ chức và yêu cầu áp dụng cho môi trường đó.

## 7. Nội dung cần xem xét trong từng quyền

### 7.1. Tính hợp lệ của người và nhu cầu

Trước hết phải xác nhận người đó còn thuộc phạm vi hỗ trợ được phép. Đối chiếu danh sách phía nhà cung cấp với danh tính trong directory và người bảo trợ nội bộ.

Các câu hỏi hữu ích:

- Người này đang thực hiện công việc nào?
- Có cần truy cập trong giai đoạn sắp tới không?
- Công việc cần quyền thường trực hay chỉ một lần?
- Người thay thế đã được cấp quyền nhưng người cũ chưa bị thu hồi chưa?
- Có tài khoản dùng chung khiến không xác định được cá nhân thực hiện không?

Nếu không xác định được chủ sở hữu hoặc mục đích, quyền không đủ cơ sở để tái xác nhận. Cần chuyển xử lý và áp dụng quyết định theo mức rủi ro.

### 7.2. Phạm vi tài nguyên và thao tác

Review quyền hiệu lực, không chỉ tên entitlement. Một vai trò “Support” có thể kế thừa quyền quản trị qua nhóm khác. Một nhóm tài nguyên có thể đã được mở rộng từ hai máy thử nghiệm sang toàn bộ cụm sản xuất.

Cần đối chiếu:

- Môi trường sản xuất, thử nghiệm và phát triển.
- Máy chủ, cơ sở dữ liệu, tenant, namespace hoặc thiết bị cụ thể.
- Quyền đọc, thay đổi cấu hình, khởi động lại, xuất dữ liệu hoặc quản trị danh tính.
- Quyền gián tiếp như sửa nhóm, sửa chính sách PAM hoặc thay đổi secret.
- Quyền kế thừa, nhóm lồng nhau và các tài khoản đặc quyền thay thế.
- Khả năng truyền tệp, chuyển tiếp kết nối hoặc mở một đường truy cập mới.

Với JEA hoặc cơ chế giới hạn lệnh, cần xem chính sách thực tế có giới hạn đúng tác vụ không. Việc chỉ cho phép một công cụ mạnh vẫn có thể tạo ra nhiều khả năng ngoài dự kiến tùy cách cấu hình công cụ đó.

### 7.3. Điều kiện truy cập

Quyền có phạm vi tài nguyên đúng nhưng điều kiện kích hoạt yếu vẫn có thể không phù hợp. Review cần kiểm tra MFA, thiết bị, nguồn kết nối, giờ truy cập, phê duyệt, thời lượng, ghi phiên và cơ chế can thiệp theo chính sách.

Không phải mọi điều kiện đều thích hợp cho mọi kiểu truy cập. Danh tính máy không thể áp dụng tương tác MFA như người dùng; cần cơ chế xác thực workload, secret ngắn hạn hoặc kiểm soát tương ứng.

Các ngoại lệ như truy cập trực tiếp hoặc checkout mật khẩu cần có lý do riêng và ngày hết hạn. Không giữ ngoại lệ vô thời hạn chỉ vì nó từng được cho phép trong một sự cố.

### 7.4. Sử dụng thực tế và hành vi

Đối chiếu các lần truy cập với ticket, khung giờ và tài nguyên được duyệt. “Đã đăng nhập thành công” chỉ chứng minh một sự kiện xác thực; chưa cho biết công việc có hợp lệ.

Một số dấu hiệu cần làm rõ:

- Truy cập vào tài nguyên không xuất hiện trong yêu cầu.
- Dùng tài khoản chung hoặc tài khoản của người đã rời dự án.
- Checkout secret nhưng không có phiên hoặc công việc tương ứng.
- Phiên kéo dài qua thời hạn được cấp.
- Truy cập ngoài lịch hỗ trợ mà không có yêu cầu phù hợp.
- Tạo tài khoản, key hoặc token mới không nằm trong thay đổi đã phê duyệt.
- Truy cập xuất hiện trên hệ thống đích nhưng không có dấu vết tại PAM.

Một dấu hiệu không tự động chứng minh có hành vi xấu. Nó tạo ra một câu hỏi phải được giải thích bằng bằng chứng; nếu có khả năng đe dọa đang diễn ra, chuyển sang quy trình ứng phó tương ứng.

### 7.5. Credential và truy cập tồn lưu

Nếu nhà cung cấp từng được xem mật khẩu hoặc lấy private key, việc xóa entitlement không làm mất bản sao họ có thể đã giữ. Khi cần chấm dứt khả năng truy cập, có thể phải luân chuyển credential, loại key khỏi nơi tin cậy, thu hồi token và kiểm tra các đường truy cập liên quan.

Thay đổi một secret trên vault nhưng chưa đồng bộ với hệ thống đích chưa chứng minh credential cũ vô hiệu. Ngược lại, đổi mật khẩu ở đích mà không cập nhật ứng dụng tiêu thụ có thể gây lỗi dịch vụ. Thao tác cần có xác minh cả phía xác thực và phía sử dụng hợp lệ.

## 8. Quy trình review từ đầu đến cuối

~~~mermaid
flowchart TD
    A[Chốt phạm vi và người chịu trách nhiệm] --> B[Thu inventory và bằng chứng]
    B --> C[Đối chiếu nhu cầu với quyền hiệu lực]
    C --> D{Dữ liệu đủ để quyết định?}
    D -- Chưa --> E[Bổ sung hoặc chuyển cấp theo rủi ro]
    E --> C
    D -- Đủ --> F[Quyết định từng quyền]
    F --> G[Thực thi thay đổi tại các điểm kiểm soát]
    G --> H[Kiểm tra quyền, credential và phiên]
    H --> I{Đã đạt kết quả yêu cầu?}
    I -- Chưa --> G
    I -- Rồi --> J[Đóng review và lên lịch tiếp theo]
~~~

### Bước 1: Chốt phạm vi

Ghi rõ nhà cung cấp, hợp đồng hoặc dịch vụ liên quan, môi trường, danh tính, tài nguyên và khoảng thời gian cần xem xét. Xác định người quyết định và thời hạn hoàn thành.

Nếu đang review một sự kiện cụ thể như thay kỹ sư, vẫn cần xem các quyền gián tiếp và credential liên quan tới người đó, không chỉ tài khoản có cùng tên.

### Bước 2: Chuẩn hóa danh sách quyền

Tạo danh sách có thể đối chiếu giữa người, nhóm, entitlement và hệ thống đích. Tách trạng thái của danh tính, quyền, phiên và credential.

Một dòng dữ liệu nên cho biết quyền được cấp trực tiếp hay kế thừa. Với quyền kế thừa, lưu chuỗi nhóm hoặc chính sách dẫn tới quyền để có thể thu hồi đúng chỗ.

### Bước 3: Đối chiếu nhu cầu và bằng chứng

Chủ hệ thống xác nhận tác vụ cần thiết; nhà tài trợ xác nhận người thực hiện; đội kỹ thuật xác nhận khả năng truy cập thực tế. Xem sử dụng gần đây như một nguồn hỗ trợ quyết định, không biến nó thành tiêu chí duy nhất.

Nếu ticket ghi “chẩn đoán” nhưng entitlement cho phép sửa toàn bộ cơ sở dữ liệu, review phải giải quyết chênh lệch đó ngay cả khi chưa thấy hành vi sửa dữ liệu.

### Bước 4: Quyết định từng quyền

Các lựa chọn nên có nghĩa rõ ràng:

| Quyết định | Khi áp dụng | Thông tin bắt buộc |
|---|---|---|
| Giữ có thời hạn | Nhu cầu và kiểm soát vẫn phù hợp | Lý do, phạm vi, người chịu trách nhiệm, hạn tiếp theo |
| Thu hẹp | Còn nhu cầu nhưng quyền quá rộng | Quyền đích, quyền cần bỏ, ngày thực hiện |
| Tạm đình chỉ | Chưa xác minh được hoặc cần ngăn truy cập trong khi xử lý | Điều kiện mở lại, thời hạn và người quyết định |
| Thu hồi | Hết nhu cầu hoặc không còn đủ điều kiện | Danh tính, entitlement, credential và phiên liên quan |
| Ngoại lệ có thời hạn | Chưa thể đạt kiểm soát mục tiêu ngay | Rủi ro, kiểm soát bù, người chấp nhận, ngày hết hạn |
| Chuyển xử lý sự cố | Có dấu hiệu cần điều tra hoặc can thiệp khẩn | Tham chiếu sự cố và biện pháp kiểm soát ban đầu |

Không gộp “đã quyết định thu hồi” vào “đã thu hồi”. Quyết định và kết quả thực thi cần hai trường trạng thái riêng.

### Bước 5: Thực thi

Thực hiện thay đổi ở những nơi thực sự tạo khả năng truy cập. Tùy kiến trúc, cần xử lý directory, PAM, vault, tài khoản đích, key, token, rule kết nối và phiên.

Khi phải thu hẹp một quyền đang phục vụ công việc hợp lệ, phối hợp với chủ hệ thống để cấu hình quyền thay thế và kiểm tra tác vụ được phép. Với tình huống cần ngăn truy cập khẩn, ưu tiên biện pháp cô lập phù hợp và ghi rõ tác động dự kiến.

### Bước 6: Xác minh sau thay đổi

Đọc lại cấu hình từ điểm thực thi. Kiểm tra nhóm, eligibility, grant và trạng thái phiên sau thời gian truyền thay đổi đã được xác định.

Có thể dùng kiểm tra truy cập được kiểm soát để xác nhận thao tác bị thu hồi đã bị chặn và tác vụ còn hợp lệ vẫn hoạt động. Chỉ thực hiện trong phạm vi được cho phép; không lấy tài khoản thật của nhà cung cấp để thử đăng nhập ngoài quy trình.

### Bước 7: Đóng hoặc giữ mở

Chỉ đóng khi các quyết định cần thực thi đã có bằng chứng phù hợp. Trường hợp chưa hoàn thành phải có người xử lý, hạn và trạng thái tồn đọng; ngoại lệ cần ngày hết hiệu lực.

Ghi lại thời điểm kết thúc và thay đổi cuối cùng đã được đối chiếu. Review đợt trước không tự bao phủ quyền cấp thêm vào ngày hôm sau.

## 9. Hồ sơ review mẫu

Mẫu dưới đây minh họa cấu trúc thông tin, không phải cấu hình của một sản phẩm PAM cụ thể.

~~~yaml
reviewId: VAR-2026-042
scope:
  vendorId: atlas-support
  service: erp-support
  environment: production
  snapshotAt: "2026-11-20T09:00:00+07:00"
  activityWindow:
    from: "2026-10-01T00:00:00+07:00"
    to: "2026-11-20T09:00:00+07:00"

subject:
  identityId: ext-1842
  identityType: human
  internalSponsor: owner-erp
  entitlementId: erp-prod-admin
  targetSet:
    - erp-app-01
    - erp-app-02
  accessMode: pam-jit

assessment:
  businessNeed: "Tiếp tục hỗ trợ chẩn đoán ERP"
  finding: "Quyền quản trị rộng hơn tác vụ chẩn đoán"
  evidenceRefs:
    - "inventory-export-20261120"
    - "ticket-CHG-1842"
    - "session-metadata-erp-1842"

decision:
  action: reduce
  approvedBy: erp-system-owner
  approvedAt: "2026-11-21T10:00:00+07:00"
  targetEntitlement: erp-prod-diagnostics
  eligibilityExpiresAt: "2026-12-15T18:00:00+07:00"

implementation:
  state: verified
  changeRef: "CHG-1901"
  removedEntitlements:
    - erp-prod-admin
  grantedEntitlements:
    - erp-prod-diagnostics
  activeSessionsHandled: true
  credentialExposureAssessment: "Không phát hiện luồng xem secret trong phạm vi log đã có"
  verifiedAt: "2026-11-22T15:00:00+07:00"
  verifiedBy: pam-operator-02
  evidenceRefs:
    - "effective-access-readback-1901"
    - "controlled-access-check-1901"

followUp:
  nextReviewDue: "2026-12-10"
  unresolvedItems: []
~~~

Trường đánh giá credential trong ví dụ có giới hạn rõ ràng: nó chỉ nói về các nguồn log đã có. Không nên thay câu này bằng “credential chắc chắn chưa từng bị sao chép” khi cơ chế thu thập không đủ để chứng minh.

Hồ sơ thực tế cũng cần bảo vệ khỏi chỉnh sửa không được kiểm soát. Nếu quyết định hoặc bằng chứng thay đổi, phải giữ được lịch sử để biết ai thay đổi điều gì, vào thời điểm nào.

## 10. Tình huống thực tế: thu hẹp quyền hỗ trợ ERP

### Bối cảnh

Atlas Support có ba kỹ sư được hỗ trợ ERP. Ban đầu cả ba được cấp eligibility quản trị toàn bộ máy chủ ERP để phục vụ giai đoạn triển khai. Sau khi vận hành ổn định, công việc thường gặp chỉ còn xem trạng thái dịch vụ và đọc log.

Review phát hiện:

- Một kỹ sư đã chuyển sang dự án khác.
- Hai kỹ sư còn lại vẫn cần hỗ trợ nhưng entitlement bao phủ cả máy chủ cơ sở dữ liệu.
- Có một phiên quản trị đang mở từ trước khi bắt đầu đợt review.
- Một tài khoản đích vẫn nằm trong nhóm quản trị cục bộ dù nhóm PAM tương ứng đã được chỉnh sửa.
- Hồ sơ hỗ trợ có một ngoại lệ xem mật khẩu được cấp trong giai đoạn triển khai.

### Phân tích và quyết định

Với kỹ sư đã rời dự án, xác nhận danh tính và nhu cầu với nhà tài trợ rồi quyết định thu hồi. Phạm vi thu hồi gồm eligibility, grant đang có và mọi phương thức truy cập gắn với người đó.

Với hai kỹ sư còn lại, chuyển sang entitlement chẩn đoán trên hai máy chủ ứng dụng. Không giữ quyền quản trị cơ sở dữ liệu chỉ để thuận tiện cho những công việc có thể phát sinh sau này; công việc vượt phạm vi sẽ cần yêu cầu riêng.

Phiên đang mở cần được xem xét và kết thúc hoặc tái thiết lập theo quyền mới, tùy khả năng của hệ thống. Không giả định thay đổi eligibility lập tức làm biến mất quyền bên trong một phiên đã được tạo.

Tài khoản trong nhóm quản trị cục bộ cần được xử lý tại hệ thống đích. Đây là minh chứng cho việc chỉ review cấu hình PAM sẽ bỏ sót quyền tồn lưu.

Ngoại lệ xem mật khẩu cần được kiểm tra riêng. Nếu người đã rời dự án từng có khả năng biết một credential còn hiệu lực, phải đánh giá việc luân chuyển, ảnh hưởng tới các bên tiêu thụ và cách xác minh credential cũ không còn dùng được.

### Điều kiện đóng

Đợt review được đóng khi:

1. Danh tính đã rời dự án không còn đường truy cập trong phạm vi kiểm tra.
2. Hai kỹ sư còn lại chỉ có quyền chẩn đoán đúng tài nguyên.
3. Phiên cũ đã được xử lý và có bằng chứng.
4. Quyền quản trị cục bộ dư thừa đã được loại bỏ.
5. Credential liên quan đã được xử lý theo quyết định có ghi nhận.
6. Các thao tác hỗ trợ hợp lệ vẫn thực hiện được qua luồng mới.

Một ticket ghi “đã xóa khỏi nhóm PAM” chưa đáp ứng toàn bộ các điều kiện này.

## 11. Kiểm tra thu hồi: cần nhìn qua nhiều lớp

| Lớp | Cần xác minh | Kết luận không nên suy diễn |
|---|---|---|
| Danh tính | Tài khoản bị vô hiệu hoặc không còn đủ điều kiện | Vô hiệu tài khoản luôn hủy ngay mọi token |
| Eligibility | Không còn khả năng xin/kích hoạt quyền đã thu hồi | Không có grant đang mở nghĩa là không còn eligibility |
| Grant | Quyền tạm thời đã hết hoặc bị thu hồi | Grant hết hạn luôn kết thúc mọi tiến trình |
| Phiên | Phiên liên quan đã kết thúc hoặc bị kiểm soát đúng quyết định | Xóa nhóm tự động đóng mọi phiên |
| Vault/secret | Không còn quyền lấy secret; secret bị lộ được xử lý | Xóa quyền vault làm mất bản sao secret |
| Hệ thống đích | Role, nhóm, key, token và tài khoản đã đúng trạng thái | Cấu hình PAM phản ánh đầy đủ quyền cục bộ |
| Đường mạng | Đường không được phép đã bị chặn | Chặn VPN đủ để vô hiệu mọi credential |

Mức kiểm tra cần tương xứng với quyết định và kiến trúc. Không cần giả định sản phẩm nào cũng có mọi lớp trên; cần xác định những lớp thật sự có trong đường truy cập của mình.

Thu hồi có thể lan truyền không đồng thời giữa các hệ thống. Hồ sơ cần phân biệt thời điểm gửi yêu cầu, thời điểm điểm thực thi xác nhận và thời điểm kiểm tra kết quả. Nếu một thay đổi còn đang đồng bộ, trạng thái phải phản ánh điều đó.

## 12. Xử lý dữ liệu thiếu và ngoại lệ

### 12.1. Có nhu cầu nhưng thiếu log

Không thể kết luận hoạt động trước đây phù hợp nếu không có dữ liệu để xem. Có thể đánh giá nhu cầu hiện tại, nhưng phải ghi riêng phần không thể xác minh về sử dụng.

Biện pháp tiếp theo có thể là bổ sung thu thập log, giới hạn thời lượng và phạm vi, yêu cầu phê duyệt từng lần hoặc tăng giám sát trong thời gian khắc phục. Quyền tiếp tục tồn tại cần một quyết định có trách nhiệm; không tự động chuyển thành “review đạt”.

### 12.2. Không sử dụng nhưng là quyền dự phòng

Kiểm tra kịch bản dự phòng, người chịu trách nhiệm, khả năng kích hoạt và cách thử nghiệm có kiểm soát. Có thể giữ eligibility giới hạn nếu nhu cầu được xác nhận, thay vì duy trì quyền quản trị thường trực.

Nếu quyền được giữ chỉ vì “có thể cần”, không có kịch bản hoặc chủ sở hữu, lý do đó chưa đủ để tái xác nhận.

### 12.3. Nhà cung cấp dùng tài khoản chung

Một tài khoản chung khiến khó quy trách nhiệm và thu hồi theo cá nhân. Cần xác định khả năng chuyển sang danh tính cá nhân qua PAM và cách gắn người thực hiện với phiên trên tài khoản đích.

Trong giai đoạn chuyển đổi, ít nhất phải biết ai được phép sử dụng, ai đã dùng, thời gian nào, credential được kiểm soát ra sao và khi một người rời nhóm thì xử lý thế nào. Bản ghi phiên không tự khắc phục mọi hạn chế của tài khoản chung.

### 12.4. Nhà thầu phụ chưa có trong hồ sơ

Xác minh xem phạm vi hợp đồng và chính sách truy cập có cho phép nhóm đó hay không. Yêu cầu định danh cá nhân, nhà tài trợ và phê duyệt tương ứng trước khi duy trì quyền.

Không coi người dùng là hợp lệ chỉ vì họ có email cùng miền với nhà cung cấp hoặc được một kỹ sư khác giới thiệu.

### 12.5. Không thể thu hồi ngay vì ảnh hưởng dịch vụ

Ghi rõ phụ thuộc, tác động dự kiến, thời gian chuyển đổi và kiểm soát bù. Ví dụ, tạm giới hạn tài nguyên và thời gian truy cập, yêu cầu giám sát trực tiếp hoặc thay thế credential theo kế hoạch có kiểm tra.

Ngoại lệ cần ngày hết hạn và người chịu trách nhiệm. Khi hết hạn mà chưa khắc phục, phải được xử lý theo quy trình tiếp theo, không âm thầm kéo dài.

## 13. Chỉ số theo dõi hiệu quả

Chỉ số nên đo cả việc ra quyết định và việc thực thi. Một đợt review hoàn thành nhanh nhưng không thu hồi quyền dư không tạo ra kết quả mong muốn.

| Chỉ số | Cách hiểu | Lưu ý |
|---|---|---|
| Tỷ lệ bao phủ inventory | Quyền có trong đợt review so với phạm vi đã xác định | Mẫu số phải bao gồm các nguồn ngoài PAM nếu có |
| Tỷ lệ quyết định đúng hạn | Các quyền được quyết định trước hạn | Chưa thể hiện thay đổi đã có hiệu lực |
| Tỷ lệ thực thi đã xác minh | Quyết định cần thay đổi có bằng chứng hoàn thành | Không tính chỉ dựa trên ticket đã đóng |
| Số quyền không có nhà tài trợ | Quyền thiếu người chịu trách nhiệm nội bộ | Cần theo dõi tuổi tồn đọng và mức rủi ro |
| Thời gian thu hồi | Từ quyết định hoặc sự kiện chuẩn tới hiệu lực được xác minh | Phải định nghĩa mốc bắt đầu nhất quán |
| Số ngoại lệ quá hạn | Ngoại lệ hết hạn nhưng chưa xử lý | Phân biệt ngoại lệ mới với ngoại lệ kéo dài |
| Số quyền tồn lưu tại đích | Quyền ngoài ý định được phát hiện khi đối chiếu | Có thể cho thấy inventory hoặc luồng thu hồi chưa đầy đủ |
| Tỷ lệ thiếu bằng chứng | Quyền không đủ log hoặc metadata để đánh giá | Không diễn giải là số hoạt động trái phép |

Không nên lấy “số quyền bị thu hồi” làm thước đo duy nhất cho chất lượng review. Một phạm vi được quản lý tốt có thể không cần thu hồi nhiều. Ngược lại, review không phát hiện gì trong khi dữ liệu không đầy đủ không phải bằng chứng của kiểm soát tốt.

## 14. Lỗi thường gặp và cách cải thiện

**Xác nhận theo tên nhà cung cấp.** Cách này bỏ qua khác biệt giữa từng người và từng môi trường. Cần quyết định ở mức danh tính và entitlement có phạm vi xác định.

**Chỉ xem trạng thái tài khoản.** Tài khoản còn hoạt động chưa cho biết quyền đặc quyền thực tế; tài khoản bị khóa cũng chưa chứng minh mọi phiên và credential đều vô hiệu. Cần đối chiếu các lớp tạo khả năng truy cập.

**Dùng đăng nhập gần nhất để quyết định tất cả.** Một hoạt động gần đây có thể không hợp lệ, còn một quyền dự phòng có thể chưa được dùng. Cần kết hợp nhu cầu, quyền và bằng chứng.

**Chấp thuận hàng loạt mà không có lý do.** Người review khó chịu trách nhiệm nếu không thấy tài nguyên, quyền và thay đổi từ kỳ trước. Nên trình bày dữ liệu đủ để họ ra quyết định cụ thể.

**Thu hồi trong PAM nhưng bỏ quên đích.** Cần kiểm tra local role, nhóm, key, token và các đường truy cập liên quan.

**Đóng ticket khi lệnh thay đổi được gửi thành công.** Cần đọc lại trạng thái và kiểm tra kết quả tại điểm thực thi; yêu cầu gửi thành công không đồng nghĩa đã có hiệu lực.

**Giữ ngoại lệ không có hạn.** Cần thời hạn, người chấp nhận rủi ro, biện pháp bù và lịch khắc phục.

**Đính kèm secret hoặc quá nhiều dữ liệu phiên.** Dùng tham chiếu bằng chứng có kiểm soát truy cập và giữ dữ liệu cần thiết cho quyết định.

## 15. Bài tập áp dụng

### Tình huống

Một nhà cung cấp có bốn kỹ sư hỗ trợ hệ thống thanh toán. Kết quả kiểm kê ban đầu cho thấy:

- Kỹ sư A vẫn thuộc hợp đồng nhưng chỉ cần đọc log.
- Kỹ sư B đã rời nhóm hỗ trợ tuần trước.
- Kỹ sư C có eligibility JIT quản trị và không có grant đang hoạt động.
- Kỹ sư D có ticket sự cố hợp lệ nhưng phiên đã vượt khung thời gian được duyệt.
- Một SSH key dùng chung vẫn được tin cậy trên hai máy đích.
- Log PAM đầy đủ nhưng chưa thu được trạng thái tài khoản cục bộ trên một máy.

Hãy lập quyết định cho từng trường hợp và nêu bằng chứng cần có trước khi đóng.

### Hướng phân tích

Với A, đối chiếu tác vụ đọc log với quyền hiệu lực. Nếu đang có quyền quản trị rộng, đề xuất thu hẹp và kiểm tra tác vụ được phép sau thay đổi.

Với B, xác minh sự kiện rời nhóm và thu hồi các đường truy cập liên quan. Đánh giá credential mà B từng có khả năng biết, gồm SSH key dùng chung nếu phù hợp với phạm vi của B.

Với C, review eligibility ngay cả khi không có grant. Xác nhận nhu cầu, phạm vi đích, điều kiện phê duyệt và ngày hết hạn. Không đánh dấu “không có quyền” chỉ dựa trên danh sách grant hiện tại.

Với D, làm rõ công việc có còn tiếp diễn và có phê duyệt gia hạn hợp lệ không. Xử lý phiên theo quyết định và mức rủi ro; ticket ban đầu không tự gia hạn mọi điều kiện.

Với SSH key dùng chung, xác định người có khả năng nắm private key, nơi key được tin cậy và phụ thuộc vận hành. Lập kế hoạch thay thế hoặc thu hồi, rồi kiểm tra trạng thái ở cả hai máy.

Với máy chưa có dữ liệu cục bộ, giữ rõ phần chưa xác minh. Không đóng toàn bộ phạm vi như thể inventory đã đầy đủ. Có thể hoàn tất các mục độc lập đã đủ bằng chứng và tiếp tục theo dõi mục còn thiếu.

### Câu hỏi tự kiểm tra

1. Vì sao “không có phiên đang mở” chưa chứng minh nhà cung cấp không còn quyền?
2. Khi nào xóa entitlement cần đi kèm luân chuyển credential?
3. Người quyết định giữ quyền cần thấy những dữ liệu nào?
4. Làm thế nào phân biệt quyết định thu hồi với thu hồi đã có hiệu lực?
5. Nếu dữ liệu snapshot đã cũ, cần làm gì trước khi đóng review?
6. Vì sao tài khoản dịch vụ cần một đơn vị review riêng?
7. Một ngoại lệ có thời hạn cần những thành phần nào?
8. Những bằng chứng nào giúp chứng minh quyền trên hệ thống đích đã phù hợp?

Vendor access review hoàn thành khi từng quyền trong phạm vi đã có quyết định có trách nhiệm, thay đổi cần thiết đã được thực thi và kết quả được xác minh. Giá trị của hoạt động này nằm ở việc duy trì khả năng truy cập đúng người, đúng việc, đúng phạm vi và đúng thời hạn trong suốt vòng đời hợp tác với nhà cung cấp.
