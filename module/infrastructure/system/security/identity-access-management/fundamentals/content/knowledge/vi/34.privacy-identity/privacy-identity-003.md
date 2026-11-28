# Purpose limitation: giới hạn mục đích sử dụng dữ liệu danh tính

## 1. Dữ liệu dùng để xác thực không mặc nhiên được dùng cho mọi việc

Purpose limitation là nguyên tắc xác định rõ dữ liệu được xử lý để làm gì và giới hạn việc sử dụng dữ liệu theo những mục đích đã được xác lập, xem xét và cho phép.

Trong IAM, cùng một trường dữ liệu có thể phục vụ nhiều hoạt động rất khác nhau. Số điện thoại có thể dùng để khôi phục tài khoản, địa chỉ email để gửi thông báo bảo mật, membership để đánh giá quyền và lịch sử đăng nhập để điều tra sự cố.

Việc hệ thống đã có dữ liệu không có nghĩa mọi dịch vụ, nhân viên hoặc mô hình phân tích đều được sử dụng nó cho một mục tiêu mới.

Ví dụ, công ty An Bình thu thập số điện thoại để hỗ trợ khôi phục tài khoản. Nhóm tiếp thị muốn dùng danh sách này để gửi quảng cáo. Câu hỏi không chỉ là nhóm tiếp thị có quyền đọc bảng dữ liệu hay không, mà còn là dữ liệu có được phép sử dụng cho mục đích tiếp thị trong bối cảnh đó hay chưa.

Bài học tập trung vào cách chuyển giới hạn mục đích thành thiết kế và quy trình vận hành IAM: xác định mục đích cụ thể, gắn dữ liệu với luồng sử dụng, hạn chế bên nhận và kiểm soát việc tái sử dụng.

## 2. Phân biệt mục đích, thao tác và khả năng kỹ thuật

Ba câu hỏi cần được tách rõ:

| Câu hỏi | Ví dụ |
| --- | --- |
| Mục đích là gì? | Giúp chủ tài khoản khôi phục quyền truy cập |
| Thao tác cần thực hiện là gì? | Đọc thông tin liên hệ và gửi challenge khôi phục |
| Hệ thống có khả năng làm gì? | Truy vấn toàn bộ hồ sơ hoặc xuất danh sách người dùng |

Một quyền API như đọc hồ sơ mô tả khả năng thao tác, nhưng chưa giải thích vì sao thao tác đó được thực hiện. Ngược lại, một mục đích được phê duyệt cũng không có nghĩa người thực hiện được đọc mọi trường trong hồ sơ.

“Cải thiện dịch vụ”, “phục vụ kinh doanh” hoặc “bảo mật” có thể quá rộng để đưa ra quyết định cụ thể. Mục đích có ích cần giúp trả lời dữ liệu nào cần dùng, ai được dùng và hành động nào nằm ngoài phạm vi.

Ví dụ cụ thể hơn:

> Xác minh yêu cầu khôi phục tài khoản và gửi thông báo liên quan tới chính lượt khôi phục đó, bằng thông tin liên hệ đã được quản lý cho luồng này.

Mô tả trên giúp nhận ra rằng xuất toàn bộ danh bạ cho một chiến dịch không thuộc luồng khôi phục, dù cùng sử dụng trường số điện thoại.

Cũng cần tránh đồng nhất mục đích với tên ứng dụng. Một ứng dụng IAM có thể thực hiện xác thực, quản lý tài khoản, hỗ trợ người dùng và báo cáo vận hành. Các hoạt động đó không nhất thiết cần cùng dữ liệu hoặc cùng giới hạn sử dụng.

## 3. Quan hệ với các nguyên tắc và kiểm soát khác

Purpose limitation phối hợp với những kiểm soát khác, nhưng mỗi kiểm soát trả lời một câu hỏi riêng:

| Khái niệm | Câu hỏi chính |
| --- | --- |
| Giới hạn mục đích | Vì sao dữ liệu được xử lý và được dùng vào việc nào? |
| Giảm thiểu dữ liệu | Với việc đó, thực sự cần những dữ liệu nào và độ chi tiết bao nhiêu? |
| Kiểm soát truy cập | Chủ thể nào được thực hiện thao tác nào trên dữ liệu? |
| Giới hạn lưu giữ | Dữ liệu còn cần được giữ tới thời điểm hoặc điều kiện nào? |
| Bảo vệ dữ liệu khi truyền và lưu | Dữ liệu được bảo vệ khỏi truy cập hoặc thay đổi trái phép ra sao? |
| Minh bạch và lựa chọn của người dùng | Người dùng hiểu và kiểm soát những hoạt động liên quan như thế nào? |
| Kiểm toán | Có thể đối chiếu ai đã xử lý dữ liệu trong luồng nào không? |

Một bảng được mã hóa vẫn có thể bị dùng sai mục đích bởi người có quyền giải mã. Một API yêu cầu đăng nhập vẫn có thể trả thừa dữ liệu. Một log được giữ trong thời gian ngắn vẫn có thể bị chuyển sang hoạt động không nằm trong phạm vi đã xác định.

Tương tự, một lần người dùng đồng ý với một hoạt động không phải giấy phép vô hạn cho mọi mục tiêu tương lai. Cần ghi nhận phạm vi và bối cảnh thực tế của lựa chọn đó, thay vì dùng một cờ chung cho tất cả hoạt động.

Mục tiêu của thiết kế là làm các kiểm soát bổ sung cho nhau. Chỉ gắn nhãn mục đích vào dữ liệu mà không thay đổi quyền truy cập hoặc luồng xử lý thì chưa đủ.

## 4. Mô tả mục đích đủ cụ thể để thực thi

Một mô tả mục đích nên làm rõ ít nhất những nội dung sau:

- Kết quả cần đạt cho người dùng hoặc hoạt động vận hành.
- Luồng xử lý và điều kiện bắt đầu luồng.
- Nhóm dữ liệu cần sử dụng.
- Chủ thể, dịch vụ hoặc bên nhận tham gia.
- Những thao tác được thực hiện.
- Điều kiện kết thúc nhu cầu sử dụng.
- Chủ sở hữu chịu trách nhiệm giải thích và duy trì phạm vi.

Ví dụ bảng mục đích của An Bình:

| Mục đích | Dữ liệu có thể cần | Giới hạn cần làm rõ |
| --- | --- | --- |
| Đăng nhập tài khoản | Định danh và bằng chứng xác thực theo cơ chế được chọn | Không xuất hồ sơ đầy đủ cho mọi client |
| Khôi phục tài khoản | Thông tin liên hệ và trạng thái của lượt khôi phục | Không dùng danh sách liên hệ để gửi nội dung không thuộc luồng |
| Đánh giá quyền truy cập | Thuộc tính, membership hoặc quyền cần cho quyết định | Chỉ chuyển những thuộc tính cần cho tài nguyên đang xét |
| Điều tra sự cố xác thực | Sự kiện, thời gian và tham chiếu phục vụ đối chiếu | Không ghi credential hoặc mở quyền xem log cho mọi nhóm |
| Quản lý vòng đời tài khoản | Trạng thái và thông tin ánh xạ với nguồn có thẩm quyền | Không sao chép toàn bộ dữ liệu nguồn chỉ vì connector đọc được |

Đây là bảng minh họa, không phải một danh sách quyền mặc định. Từng hệ thống cần xác định dữ liệu cần thiết theo cơ chế và phạm vi thực tế.

Một mục đích có thể được phiên bản hóa. Khi phạm vi thay đổi, phiên bản mới giúp phân biệt dữ liệu và hoạt động nào được đánh giá theo mô tả nào. Tuy nhiên, tăng số phiên bản không tự tạo ra quyền sử dụng mới; thay đổi vẫn cần được xem xét trước khi áp dụng.

## 5. Lập bản đồ dữ liệu theo đường đi thực tế

Dữ liệu danh tính hiếm khi chỉ nằm trong một bảng. Nó có thể đi qua directory, nhà cung cấp danh tính, ứng dụng, cache, log, hệ thống hỗ trợ và kho phân tích.

~~~mermaid
flowchart LR
    A[Nguồn danh tính] --> B[Nhà cung cấp danh tính]
    B --> C[Ứng dụng nhận thông tin cần thiết]
    B --> D[Luồng khôi phục tài khoản]
    B --> E[Sự kiện kiểm toán]
    C --> F[Cache và dữ liệu ứng dụng]
    E --> G[Điều tra được kiểm soát]
    E --> H[Đề xuất sử dụng mới cần xem xét]
~~~

Ở mỗi điểm chuyển, cần hỏi:

| Câu hỏi | Ví dụ vấn đề phát hiện được |
| --- | --- |
| Bên nhận cần dữ liệu để làm gì? | Client chỉ cần định danh nhưng nhận cả hồ sơ |
| Có thể trả ít dữ liệu hơn không? | Gửi trạng thái đủ điều kiện thay cho thuộc tính gốc |
| Có bản sao phát sinh không? | Token hoặc response được ghi nguyên vào log |
| Dữ liệu đi tiếp tới đâu? | Nhóm hỗ trợ xuất CSV rồi đưa sang kho phân tích |
| Ai kiểm soát quyền và lưu giữ tại đích? | Bên nhận giữ bản sao lâu hơn luồng gốc |
| Mục đích có bị thay đổi tại đích không? | Log bảo mật trở thành báo cáo theo dõi cá nhân |

Giới hạn mục đích cần đi theo các bản sao và dữ liệu dẫn xuất có liên quan. Nếu bản gốc được kiểm soát chặt nhưng bản xuất lại được dùng tự do, giới hạn ở nguồn không còn đủ hiệu quả.

Không chỉ xem hệ thống chính thức. File tạm, báo cáo gửi qua kênh hỗ trợ, dữ liệu thử nghiệm và bản sao trong công cụ chẩn đoán cũng có thể trở thành đường tái sử dụng.

## 6. Chuyển mục đích thành cấu hình và quyết định truy cập

Có thể duy trì một bản mô tả có cấu trúc để liên kết mục đích với các luồng được phép. Ví dụ:

~~~yaml
purposeId: IAM_ACCOUNT_RECOVERY_V1
owner: identity_operations
description: Xác minh và hoàn tất yêu cầu khôi phục tài khoản
allowedWorkflows:
  - verify_recovery_request
  - deliver_recovery_challenge
allowedDataCategories:
  - account_reference
  - recovery_contact
  - recovery_attempt_state
allowedServiceRoles:
  - recovery_orchestrator
retentionPolicyRef: recovery_data_lifecycle
~~~

Đây là tài liệu minh họa cho thiết kế, không phải cấu hình có thể tự động bảo đảm việc thực thi.

Khi chuyển thành policy, cần đối chiếu ít nhất người gọi, dịch vụ, hành động, dữ liệu, luồng nghiệp vụ và bối cảnh yêu cầu. RBAC có thể giới hạn nhóm vai trò; ABAC có thể bổ sung các điều kiện phù hợp. Chỉ có tên vai trò chưa thể hiện toàn bộ giới hạn mục đích.

Một quyết định minh họa:

~~~text
Chấp nhận thao tác khi:
    danh tính dịch vụ đã được xác minh
    VÀ dịch vụ được phép chạy luồng khôi phục
    VÀ có lượt khôi phục đang ở trạng thái phù hợp
    VÀ thao tác thuộc bước hiện tại của luồng
    VÀ dữ liệu được yêu cầu nằm trong tập cho phép
    VÀ các điều kiện phạm vi khác đều đạt
~~~

Không tin một trường purpose do client tự khai mà không kiểm tra. Nếu client tùy ý gửi purpose = account_recovery rồi nhận danh bạ, nhãn đó chỉ là lời khẳng định của bên gọi.

Bối cảnh mục đích nên được suy ra hoặc xác nhận từ luồng phía server đã được kiểm soát: endpoint phù hợp, vai trò dịch vụ, trạng thái giao dịch và dữ liệu liên quan. Thay đổi một header không được mở rộng quyền.

Ngay cả khi yêu cầu hợp lệ, API vẫn nên giới hạn kết quả. Ví dụ, một màn hình hỗ trợ có thể chỉ cần thông tin liên hệ đã che một phần, còn dịch vụ gửi challenge thực hiện gửi trực tiếp mà không trả toàn bộ giá trị cho người vận hành.

## 7. Giới hạn thuộc tính trong SSO, token và API

SSO làm giảm số lần đăng nhập, nhưng cũng có thể trở thành điểm phát tán dữ liệu nếu mọi ứng dụng đều nhận cùng một hồ sơ lớn.

Với mỗi client và API, cần xác định thông tin nào thực sự cần cho mục đích của nó. Ứng dụng chỉ cần nhận diện tài khoản không nhất thiết cần ngày sinh, số điện thoại, toàn bộ nhóm nội bộ hoặc hồ sơ nhân sự.

Những lựa chọn thiết kế cần xem xét gồm:

- Trả danh sách thuộc tính được chọn rõ thay vì tự động tuần tự hóa toàn bộ đối tượng người dùng.
- Giới hạn claim và bên nhận theo luồng sử dụng.
- Tách dữ liệu phục vụ hiển thị khỏi dữ liệu cần cho quyết định quyền.
- Tránh đưa thuộc tính nhạy cảm vào token nếu bên nhận không cần.
- Kiểm soát việc ghi token, response và claim vào log hoặc công cụ chẩn đoán.

Token được ký không mặc nhiên che giấu nội dung với những bên có thể đọc token. Chữ ký và việc hạn chế tiết lộ dữ liệu phục vụ các mục tiêu khác nhau.

Một OAuth scope có thể mô tả khả năng gọi API, nhưng tên scope không tự chứng minh mọi lần sử dụng dữ liệu đều đúng mục đích. Cần tiếp tục kiểm soát ở API, nơi dữ liệu được xử lý và khi dữ liệu được chuyển tiếp.

Định danh riêng theo từng bối cảnh hoặc từng bên nhận có thể giảm một số khả năng liên kết chéo so với dùng cùng một mã ở mọi nơi. Tuy nhiên, dữ liệu bổ sung, bảng ánh xạ hoặc các dấu hiệu khác vẫn có thể liên kết được cá nhân. Không coi việc đổi định danh là bảo đảm ẩn danh.

## 8. Log bảo mật không phải nguồn dữ liệu sử dụng không giới hạn

Audit log cần hỗ trợ điều tra và trách nhiệm giải trình. Những mục tiêu đó không yêu cầu ghi tất cả thông tin có sẵn trong một request.

Một sự kiện đăng nhập thường có thể ghi loại sự kiện, thời điểm, kết quả và tham chiếu thích hợp mà không ghi mật khẩu, mã MFA, token hoặc toàn bộ hồ sơ.

Việc đã thu thập log để điều tra sự cố không tự cho phép chuyển log sang mọi báo cáo về con người. Ví dụ, dùng thời điểm đăng nhập để xếp hạng hiệu suất hoặc suy luận giờ làm là một hoạt động khác cần được xem xét theo phạm vi riêng.

Ngay cả trong an ninh, từ “security” cũng cần được cụ thể hóa. Điều tra một sự cố đã xác định, phát hiện thử đăng nhập bất thường và xây dựng một bộ dữ liệu cho mô hình mới có thể khác nhau về dữ liệu, bên nhận, thời gian và mức liên kết.

Có thể tổ chức truy cập log theo các mức:

| Nhu cầu | Hướng giới hạn |
| --- | --- |
| Theo dõi tình trạng hệ thống | Metrics tổng hợp, không cần danh tính trực tiếp |
| Tìm một luồng lỗi | Tham chiếu giao dịch với trường chẩn đoán được chọn |
| Điều tra sự kiện liên quan tài khoản | Truy cập chi tiết theo vai trò và vụ việc |
| Xuất dữ liệu cho hoạt động khác | Xem xét riêng mục đích, phạm vi và bên nhận |

Việc giảm định danh trực tiếp có ích nhưng không làm mọi log trở thành vô danh. Một chuỗi sự kiện, mã tài khoản hoặc tổ hợp thời gian và ngữ cảnh vẫn có thể gắn với một người.

Quyền đọc log và quyền liên kết tham chiếu với danh tính thật có thể được tách khi phù hợp. Các thao tác tra cứu chi tiết hoặc xuất dữ liệu cũng cần có bằng chứng kiểm toán tương ứng.

## 9. Kiểm soát một đề xuất sử dụng dữ liệu cho mục đích mới

Mục đích có thể thay đổi theo sản phẩm và nhu cầu vận hành. Vấn đề không phải cấm mọi thay đổi, mà là không tự động tái sử dụng chỉ vì dữ liệu đã tồn tại.

Ví dụ, nhóm phân tích muốn dùng lịch sử khôi phục tài khoản để huấn luyện một mô hình dự đoán hành vi. Trước khi chuyển dữ liệu, cần làm rõ:

1. Mô hình giải quyết vấn đề cụ thể nào và có cần dữ liệu danh tính không.
2. Hoạt động mới khác gì so với mục đích thu thập ban đầu.
3. Người dùng và các bên liên quan được mô tả bối cảnh sử dụng như thế nào.
4. Dữ liệu, độ chi tiết và khả năng liên kết nào thực sự cần.
5. Bên nào nhận dữ liệu và còn chuyển tiếp cho ai.
6. Rủi ro mới đối với người có dữ liệu và đối với hệ thống.
7. Quyết định cho phép, điều kiện áp dụng và trách nhiệm thuộc về ai.
8. Những thay đổi cần có ở luồng, quyền, lưu giữ và thông tin cung cấp cho người dùng.

Kết quả có thể là không dùng tập dữ liệu đó, dùng dữ liệu tổng hợp phù hợp hơn, tạo dữ liệu tổng hợp nhân tạo, giảm phạm vi hoặc triển khai một hoạt động mới với các điều kiện đã được xác lập.

Không bắt đầu bằng cách sao chép dữ liệu sang hệ thống mới rồi mới đánh giá. Một bản sao đã được phân phối sẽ khó thu hồi và khó xác định mọi lần sử dụng.

Cũng không coi đổi tên cột, băm email hoặc gắn một nhãn mới là đủ để giải quyết câu hỏi mục đích. Băm một giá trị dễ đoán có thể vẫn cho phép đối chiếu; nếu bảng ánh xạ còn tồn tại, khả năng liên kết vẫn cần được kiểm soát.

## 10. Vòng đời dữ liệu phải phù hợp với mục đích

Khi mục đích đã hoàn tất hoặc không còn được thực hiện, cần xem xét dữ liệu nào còn cần giữ và dữ liệu nào phải kết thúc sử dụng theo thiết kế đã xác định.

Vòng đời có thể khác giữa các loại dữ liệu:

| Loại dữ liệu | Câu hỏi khi kết thúc luồng |
| --- | --- |
| Challenge khôi phục | Khi nào hết hiệu lực và không còn được chấp nhận? |
| Trạng thái tạm của giao dịch | Khi nào được dọn sau hoàn tất hoặc hết hạn? |
| Thông tin liên hệ cho khôi phục | Có còn được dùng cho tài khoản và mục đích tương ứng không? |
| Sự kiện kiểm toán cần thiết | Giữ phần nào để đối chiếu và theo lịch nào? |
| Bản sao phân tích hoặc file xuất | Ai chịu trách nhiệm kết thúc lưu giữ và sử dụng? |
| Cache và backup | Dữ liệu đi vào và ra khỏi vòng đời như thế nào? |

Không dùng cùng một thời hạn cho mọi thứ chỉ để đơn giản cấu hình. Dữ liệu giao dịch ngắn hạn, hồ sơ tài khoản đang hoạt động và sự kiện phục vụ điều tra có nhu cầu khác nhau.

Nếu một tập dữ liệu cần tiếp tục được giữ cho một hoạt động đã được xác lập khác, phải mô tả phạm vi còn giữ, giới hạn truy cập và điều kiện kết thúc. Không dùng lý do “có thể cần sau này” để mở việc lưu giữ vô hạn.

Xóa bản ghi ở hệ thống chính chưa chứng minh mọi bản sao đã kết thúc vòng đời. Cần tính tới queue, cache, file xuất, công cụ hỗ trợ, môi trường thử nghiệm và backup.

Với backup, thiết kế cần hiểu thời gian bản sao còn tồn tại và cách xử lý dữ liệu cũ khi phục hồi. Việc phục hồi không nên âm thầm tái kích hoạt các luồng sử dụng dữ liệu đã được kết thúc.

## 11. Bên nhận và các dịch vụ liên quan cũng phải có giới hạn

Một dịch vụ được phép nhận dữ liệu cho một luồng không mặc nhiên được chuyển dữ liệu cho mọi dịch vụ khác.

Ví dụ, dịch vụ gửi challenge khôi phục có thể cần địa chỉ đích và nội dung gửi. Điều đó không có nghĩa nó cần membership nội bộ, toàn bộ lịch sử đăng nhập hoặc quyền xuất danh sách tài khoản.

Ở ranh giới dịch vụ hoặc bên nhận, cần xác định:

- Dữ liệu nào được truyền.
- Luồng và mục đích cụ thể của việc truyền.
- Quyền truy cập, lưu giữ và xóa tại bên nhận.
- Khả năng chuyển tiếp hoặc tạo bản sao.
- Bằng chứng cần có để đối chiếu việc thực hiện.
- Cách xử lý khi luồng hoặc quan hệ tích hợp kết thúc.

Danh tính workload không nằm ngoài vấn đề này. Một pipeline triển khai hoặc dịch vụ tự động có thể đọc dữ liệu về con người, hoặc log hành động gắn với người khởi tạo. Vì vậy, quyền của workload cũng cần được giới hạn theo luồng xử lý dữ liệu.

Tài khoản dịch vụ có quyền rộng chỉ vì “dùng nội bộ” làm tăng khả năng dữ liệu bị sử dụng ngoài mục đích. Nên cấp quyền vừa đủ và tránh dùng chung một credential cho những hoạt động có phạm vi khác nhau.

## 12. Áp dụng tại An Bình

An Bình có ba nhu cầu: khôi phục tài khoản, phát hiện sự kiện xác thực bất thường và báo cáo tình trạng dịch vụ.

Thiết kế ban đầu đưa số điện thoại, email và lịch sử đăng nhập vào một kho chung. Nhân viên hỗ trợ và nhóm phân tích đều có thể xuất toàn bộ bảng.

Nhóm IAM chuyển sang thiết kế theo luồng:

| Luồng | Dữ liệu được cung cấp | Giới hạn sử dụng |
| --- | --- | --- |
| Khôi phục tài khoản | Tham chiếu tài khoản, liên hệ cần cho challenge và trạng thái lượt khôi phục | Chỉ cho giao dịch khôi phục tương ứng |
| Hỗ trợ người dùng | Thông tin đã che một phần và trạng thái cần giải thích | Không xuất danh bạ từ màn hình hỗ trợ |
| Điều tra xác thực | Sự kiện và tham chiếu cần cho vụ việc | Truy cập chi tiết theo quyền và phạm vi điều tra |
| Dashboard vận hành | Số lượt, nhóm kết quả và latency tổng hợp | Không cần liệt kê danh tính từng người |
| Đề xuất phân tích mới | Chưa tự động nhận bản sao | Xem xét mục đích và thiết kế dữ liệu trước khi truyền |

Khi nhóm tiếp thị xin danh sách số điện thoại từ luồng khôi phục, hệ thống không coi quyền đọc kho chung là đủ. Đề xuất được xử lý như một yêu cầu sử dụng dữ liệu khác, có chủ sở hữu và quyết định riêng trước khi có thay đổi kỹ thuật.

Khi một nhóm muốn dùng log đăng nhập để đánh giá giờ làm, nhóm IAM cũng không suy diễn rằng log bảo mật có sẵn thì hoạt động đó đã nằm trong phạm vi. Họ xác định rõ đây là một thay đổi mục đích cần xem xét.

Kết quả thiết kế không chỉ là một tài liệu chính sách. API được giới hạn trường, vai trò hỗ trợ mất quyền xuất hàng loạt, dashboard dùng dữ liệu tổng hợp và luồng xuất dữ liệu có điểm kiểm soát.

## 13. Quan sát và kiểm tra việc thực thi

Có thể theo dõi một số tín hiệu kỹ thuật để phát hiện phạm vi sử dụng bị mở rộng:

| Tín hiệu | Câu hỏi điều tra |
| --- | --- |
| API trả thêm trường sau triển khai | Có thay đổi mục đích hay chỉ vô tình trả thừa? |
| Một vai trò bắt đầu xuất dữ liệu hàng loạt | Hoạt động có thuộc luồng được phép không? |
| Xuất hiện bên nhận mới | Đã xác định dữ liệu và mục đích của bên nhận chưa? |
| Dữ liệu quá hạn vẫn được truy vấn | Cơ chế vòng đời có được thực thi không? |
| Client tự đặt purpose tùy ý | Quyết định phía server có đang tin dữ liệu không đáng tin không? |
| Log chứa profile hoặc token nguyên vẹn | Có bản sao ngoài dự kiến không? |
| Dữ liệu thử nghiệm chứa hồ sơ thật | Luồng sao chép có vượt mục đích đã xác định không? |

Những tín hiệu này giúp phát hiện vấn đề, không tự chứng minh toàn bộ hệ thống đáp ứng giới hạn mục đích. Phần việc của con người và việc sử dụng sau khi xuất dữ liệu cũng cần được quản lý.

Một số tình huống kiểm tra thiết kế:

- Dịch vụ khôi phục chỉ đọc được những dữ liệu cần cho lượt khôi phục hợp lệ.
- Client thay nhãn purpose nhưng không có luồng tương ứng thì không nhận thêm quyền.
- API không trả một trường mới chỉ vì đối tượng dữ liệu nguồn vừa được bổ sung trường đó.
- Người hỗ trợ có thể hoàn thành công việc mà không cần xuất toàn bộ danh bạ.
- Dashboard tổng hợp không yêu cầu người xem có quyền tra danh tính chi tiết.
- Luồng điều tra có thể đối chiếu sự kiện cần thiết mà không ghi credential.
- Khi thêm bên nhận, cấu hình mặc định không tự chia sẻ mọi thuộc tính.
- Dữ liệu tạm và các bản sao đi theo vòng đời đã được xác định.
- Sau phục hồi, những giới hạn đã áp dụng không bị bỏ qua bởi dữ liệu hoặc cấu hình cũ.

Purpose limitation có hiệu quả khi một mục đích cụ thể dẫn tới những giới hạn cụ thể: dữ liệu được chọn, luồng được xác nhận, quyền vừa đủ, bên nhận rõ ràng và vòng đời có điểm kết thúc. Trong IAM, cách thiết kế đó giúp bảo vệ dữ liệu danh tính ngay cả khi người gọi đã đăng nhập và hệ thống có khả năng kỹ thuật để đọc nhiều hơn.
