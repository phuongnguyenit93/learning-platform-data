# Retire requirement — Cho yêu cầu bảo mật ngừng hiệu lực có kiểm soát

## 1. Retire requirement là gì?

Trong vòng đời yêu cầu, **retire requirement** là quyết định cho một yêu cầu ngừng là nghĩa vụ hiện hành trong **phạm vi và thời điểm đã xác định**, sau khi lý do áp dụng của nó không còn hoặc trách nhiệm bảo vệ đã được chuyển sang các yêu cầu khác có hiệu lực.

Một yêu cầu đã retire vẫn cần có bản ghi lịch sử phù hợp: nội dung từng áp dụng, nguồn gốc, phiên bản, phạm vi, lý do thay đổi, người quyết định và bằng chứng hỗ trợ. Thời hạn lưu bản ghi phụ thuộc chính sách và nghĩa vụ áp dụng; không mặc định phải giữ mọi hiện vật vô thời hạn.

Ví dụ, ứng dụng từng tự cung cấp chức năng đặt lại mật khẩu. Sau khi chuyển hoàn toàn sang nhà cung cấp danh tính — IdP — ứng dụng có thể cho yêu cầu riêng về token đặt lại mật khẩu cục bộ ngừng hiệu lực. Nhưng cần chứng minh luồng cũ đã được loại bỏ khỏi phạm vi vận hành và các nghĩa vụ xác thực liên quan đã được phân bổ đúng.

Ẩn nút “quên mật khẩu” chưa đủ. API cũ, tác vụ gửi email, tài khoản khẩn cấp hoặc phiên bản còn được hỗ trợ có thể vẫn làm yêu cầu đó tiếp tục cần thiết.

Trong module thiết kế yêu cầu bảo mật, retire là một thay đổi có thể tác động đến rủi ro, kiến trúc, xác thực, phân quyền, dữ liệu, logging và phục hồi. Quyết định cần được đánh giá theo cùng mục tiêu bảo vệ đã làm phát sinh yêu cầu.

[NASA — Requirements Management](https://www.nasa.gov/reference/6-2-requirements-management/) nhấn mạnh quản lý thay đổi baseline, duy trì truy vết và đánh giá tác động của thay đổi. Trong bài này, retire được xử lý như một dạng thay đổi yêu cầu cần có cơ sở và quyết định rõ ràng.

Sau bài học, người học cần có thể:

- Phân biệt ngừng hiệu lực với hoàn thành, miễn trừ và thay đổi giải pháp.
- Xác định phạm vi thật sự không còn cần một yêu cầu.
- Phân tích tác động đến yêu cầu khác, kiểm soát, dữ liệu và bằng chứng.
- Viết điều kiện để việc ngừng hiệu lực có thể kiểm chứng.
- Cập nhật baseline hiện hành mà vẫn giữ lịch sử và trách nhiệm bảo vệ.

## 2. Phân biệt các quyết định dễ nhầm

Các nhãn dưới đây là cách diễn đạt phục vụ bài học. Tổ chức có thể dùng tên khác, miễn định nghĩa và hiệu lực được thống nhất.

| Tình huống | Ý nghĩa | Điều cần giữ rõ |
| --- | --- | --- |
| Yêu cầu đã được đáp ứng | Hệ thống có bằng chứng phù hợp với yêu cầu | Yêu cầu thường vẫn có hiệu lực trong vận hành |
| Yêu cầu đang được sửa đổi | Nội dung hoặc tham số thay đổi | Có phiên bản và phân tích tác động |
| Yêu cầu được thay thế — superseded | Một hoặc nhiều yêu cầu mới tiếp nhận nghĩa vụ liên quan | Có ánh xạ phạm vi và thời điểm chuyển giao |
| Đang chuẩn bị ngừng hiệu lực — deprecated/transitioning | Đã có kế hoạch chuyển đổi, còn điều kiện chưa hoàn tất | Yêu cầu cũ vẫn áp dụng trong phần phạm vi còn hoạt động |
| Có ngoại lệ hoặc miễn trừ | Một phần không đáp ứng được xử lý theo cơ chế được phép | Nghĩa vụ gốc và rủi ro chưa tự biến mất |
| Không áp dụng cho một phạm vi | Điều kiện áp dụng không tồn tại ở phạm vi cụ thể | Không suy rộng sang mọi hệ thống hoặc phiên bản |
| Yêu cầu đã retire | Ngừng hiệu lực theo phạm vi, thời điểm và quyết định đã ghi | Có lịch sử, lý do, bằng chứng và nghĩa vụ còn tồn tại |
| Xóa bản ghi | Loại bỏ nội dung khỏi nơi lưu | Có thể làm mất khả năng giải thích baseline trước đây |

### 2.1. “Đã triển khai xong” không có nghĩa là retire

Yêu cầu cách ly tenant đã vượt qua kiểm thử vẫn cần được duy trì khi có API mới, thay đổi dữ liệu hoặc thay cơ chế quyền. Nếu retire chỉ vì công việc triển khai đã đóng, nhóm có thể ngừng kiểm tra đúng lúc hệ thống tiếp tục thay đổi.

Trạng thái công việc, trạng thái đáp ứng và trạng thái hiệu lực nên được phân biệt. Một ticket hoàn thành không tự thay đổi hiệu lực của yêu cầu.

### 2.2. Đổi công nghệ chưa chắc làm yêu cầu hết cần thiết

Chuyển từ cơ sở dữ liệu tự quản lý sang dịch vụ cloud không tự làm yêu cầu bảo vệ dữ liệu lưu trữ ngừng áp dụng. Có thể thay cách phân bổ trách nhiệm hoặc bằng chứng đánh giá, trong khi mục tiêu và nghĩa vụ vẫn giữ nguyên.

Tương tự, dùng IdP không thay thế toàn bộ yêu cầu phân quyền tài nguyên của ứng dụng. Xác thực danh tính và quyết định người đó được đọc dữ liệu nào là hai trách nhiệm khác nhau.

### 2.3. Không thực hiện được không phải lý do đủ để retire

Một yêu cầu tốn kém hoặc đang làm kiểm thử thất bại có thể cần thay đổi thiết kế, thu hẹp phạm vi, sửa yêu cầu chưa hợp lý hoặc xử lý ngoại lệ. Phải đánh giá nội dung thực tế; không đổi nhãn sang retired chỉ để loại phát hiện khỏi báo cáo.

## 3. Khi nào có thể đề xuất retire?

### 3.1. Những lý do có thể hợp lệ

| Lý do đề xuất | Ví dụ | Bằng chứng cần tìm |
| --- | --- | --- |
| Chức năng không còn trong phạm vi | Ngừng đặt lại mật khẩu cục bộ | API, tài khoản, tác vụ và cấu hình cũ không còn phục vụ luồng đó |
| Dữ liệu hoặc tài sản không còn tồn tại trong phạm vi | Không còn xử lý một loại tệp riêng | Kiểm kê và xác minh các bản sao, cache, bản xuất, backup có liên quan |
| Yêu cầu khác thay thế đầy đủ | Hai yêu cầu trùng được hợp nhất | Ánh xạ các điều kiện và thuộc tính được bảo vệ |
| Nguồn ràng buộc đã thay đổi | Điều khoản hợp đồng được thay thế theo thỏa thuận | Nguồn mới, phạm vi áp dụng và người xác nhận |
| Thành phần hoặc phiên bản đã kết thúc vận hành | Một dịch vụ cũ đã ngừng phục vụ | Hồ sơ chuyển đổi, loại bỏ truy cập và quản lý dữ liệu còn lại |
| Yêu cầu ban đầu có lỗi hoặc không có căn cứ | Quy tắc được suy từ giả định đã được bác bỏ | Phân tích nguồn, rủi ro và quyết định thay đổi có thẩm quyền |

Lý do hợp lệ để **đề xuất** chưa phải bằng chứng đủ để **hoàn tất**. Kế hoạch ngừng tính năng không chứng minh tính năng đã ngừng ở mọi nơi cần thiết.

### 3.2. Những lý do cần chất vấn

Các câu sau chưa đủ để cho yêu cầu ngừng hiệu lực:

- “Không có ai gọi API trong tuần vừa rồi.”
- “Đã ẩn chức năng trên giao diện.”
- “Khách hàng chủ yếu đã chuyển sang phiên bản mới.”
- “Nhà cung cấp nói rằng dịch vụ của họ an toàn.”
- “Yêu cầu không còn trong checklist phiên bản mới.”
- “Không đủ thời gian sửa trước ngày phát hành.”
- “Mã nguồn đã xóa ở nhánh chính.”
- “Kiểm thử này lâu nay đều đạt.”

Không có lưu lượng quan sát được không chứng minh không có khả năng truy cập. Nhánh chính cũng không phản ánh mọi bản đang vận hành, nhánh bảo trì hoặc gói có thể được phục hồi.

## 4. Xác định phạm vi ngừng hiệu lực

Một quyết định cần trả lời được **ở đâu, cho ai, từ khi nào và với điều kiện gì**.

| Chiều phạm vi | Ví dụ thông tin cần ghi |
| --- | --- |
| Sản phẩm hoặc dịch vụ | Ứng dụng nào sở hữu yêu cầu |
| Môi trường | Vận hành chính thức, thử nghiệm, phục hồi thảm họa |
| Phiên bản | Những bản phát hành nào được thay đổi baseline |
| Tenant hoặc nhóm khách hàng | Nhóm nào đã chuyển đổi, nhóm nào còn dùng luồng cũ |
| Giao diện | Web, API, mobile, tác vụ nền, tích hợp bên ngoài |
| Dữ liệu | Bản chính, bản sao, tệp tạm, log và backup |
| Cấu hình | Feature flag, realm danh tính, cấu hình dự phòng |
| Thời gian | Thời điểm dự kiến, thời điểm thực tế, điều kiện có hiệu lực |
| Trạng thái hỗ trợ | Bản được hỗ trợ, bản đang chuyển đổi và bản đã ngừng vận hành |

### Ví dụ retire theo phạm vi

Có thể ghi:

> Từ baseline B-2027-03, yêu cầu SR-LOCAL-RESET-01 ngừng hiệu lực đối với các môi trường và phiên bản đã được xác nhận chỉ dùng IdP, không còn cung cấp luồng đặt lại mật khẩu cục bộ.

Nếu một nhóm khách hàng còn chạy bản hỗ trợ đăng nhập cục bộ, yêu cầu vẫn hiện hành trong phạm vi đó. Không đổi một trạng thái toàn cục khiến người đọc hiểu mọi khách hàng đều đã chuyển đổi.

Một nhóm có thể tách thành các bản ghi áp dụng theo phạm vi, hoặc giữ bảng hiệu lực riêng. Cách tổ chức dữ liệu nào cũng phải tránh làm mất mối liên hệ với mã và phiên bản yêu cầu gốc.

### Phê duyệt kế hoạch khác thời điểm có hiệu lực

Người có thẩm quyền có thể phê duyệt kế hoạch trước khi thực hiện. Việc retire chỉ có hiệu lực sau khi các điều kiện tiên quyết được đáp ứng và được xác nhận theo quyết định.

Một ngày dự kiến không thay thế bằng chứng hoàn thành. Nếu điều kiện không đạt, yêu cầu tiếp tục áp dụng ở phần phạm vi liên quan.

## 5. Phân tích tác động trước khi quyết định

### 5.1. Đi từ nguồn đến các đối tượng phụ thuộc

Một chuỗi truy vết hữu ích là:

**Nguồn hoặc mục tiêu → rủi ro → yêu cầu → thiết kế/kiểm soát → thành phần triển khai → đánh giá → vận hành và bằng chứng.**

Khi đề xuất retire, đi theo cả hai hướng:

- Về phía nguồn: mục tiêu, nghĩa vụ hoặc rủi ro nào từng làm yêu cầu cần thiết?
- Về phía phụ thuộc: tài liệu, kiểm soát, dữ liệu, kiểm thử và quy trình nào đang dựa vào yêu cầu?

Nếu yêu cầu cũ được thay thế, phải kiểm tra các phần nghĩa vụ đã được chuyển sang đâu. Nếu không có yêu cầu kế nhiệm, cần giải thích vì sao không còn điều kiện áp dụng.

### 5.2. Những nhóm tác động cần xem xét

| Nhóm | Điều có thể bị ảnh hưởng |
| --- | --- |
| Xác thực | Luồng cũ, tài khoản khẩn cấp, reset, đăng nhập dự phòng, phiên đang tồn tại |
| Phân quyền | Tài nguyên còn được truy cập qua API hoặc tích hợp khác |
| Dữ liệu | Dữ liệu còn tồn, bản sao, kho lưu trữ và quyền quản trị |
| Logging | Sự kiện thay đổi sau chuyển đổi, liên kết danh tính và yêu cầu lưu bằng chứng |
| Phục hồi | Backup cũ có thể khôi phục lại chức năng hoặc cấu hình đã ngừng |
| Kiểm soát dùng chung | Hệ thống khác có thể đang kế thừa kiểm soát bị loại bỏ |
| Đánh giá | Tiêu chí hiện hành, kiểm thử cần thay, phát hiện chưa được giải quyết |
| Tuân thủ và hợp đồng | Nghĩa vụ còn áp dụng dù thành phần hoặc giải pháp đổi |
| Vận hành | Runbook, trực sự cố, cấu hình cảnh báo và người chịu trách nhiệm |
| Khách hàng và nhà cung cấp | Tích hợp chưa chuyển đổi, thời hạn hỗ trợ và cam kết dịch vụ |

Bảng là gợi ý phân tích theo rủi ro, không buộc mọi thay đổi phải có cùng mức tài liệu. Việc retire một yêu cầu trùng nội dung có thể đơn giản hơn việc loại bỏ cơ chế xác thực trên nhiều phiên bản.

### 5.3. Xem xét lại mô hình đe dọa

Chuyển đổi có thể loại bỏ một đường tấn công nhưng tạo đường mới. Khi chuyển sang IdP:

- Ứng dụng không còn phát hành token reset cục bộ.
- Cấu hình quan hệ tin cậy với IdP trở thành điểm quan trọng.
- Việc ánh xạ danh tính và tenant vẫn phải đúng.
- Thu hồi phiên ứng dụng có thể cần cơ chế phối hợp mới.
- Mất IdP làm thay đổi hành vi dự phòng và phục hồi.

Vì vậy, không suy từ “thành phần cũ đã biến mất” sang “mọi rủi ro danh tính đã được giải quyết”.

## 6. Chuyển giao nghĩa vụ khi có yêu cầu kế nhiệm

### 6.1. Ánh xạ theo ý nghĩa thay vì chỉ đổi mã

Một yêu cầu có thể bị tách, hợp nhất hoặc chuyển cấp. Quan hệ thay thế không nhất thiết là một-một.

Ví dụ, yêu cầu cũ về đặt lại mật khẩu cục bộ có thể liên quan đến:

- Yêu cầu mới về khôi phục danh tính tại IdP.
- Yêu cầu của ứng dụng về xử lý trạng thái tài khoản và thu hồi phiên.
- Yêu cầu ngăn ứng dụng tiếp tục cung cấp luồng cục bộ.
- Yêu cầu bảo vệ dữ liệu xác thực cũ còn được giữ lại.

Mục tiêu cha “ngăn người không được phép chiếm tài khoản” vẫn cần được bảo vệ. Không retire mục tiêu đó chỉ vì một luồng triển khai đã được thay.

| Nội dung cần bảo vệ | Trước chuyển đổi | Sau chuyển đổi cần làm rõ |
| --- | --- | --- |
| Ai được phép khôi phục danh tính | Luồng reset của ứng dụng | Chính sách và quy trình tại IdP |
| Hiệu lực của bằng chứng khôi phục | Token do ứng dụng phát hành | Thuộc tính của cơ chế khôi phục mới đã được đánh giá |
| Phiên ứng dụng sau sự kiện bảo mật | Ứng dụng tự xử lý | Phối hợp giữa IdP và ứng dụng |
| Truy vết sự kiện khôi phục | Log ứng dụng | Log IdP và thông tin liên kết cần thiết |
| Không mở lại đường cũ | Giới hạn trong luồng đang hoạt động | Cấu hình, triển khai và phục hồi phải giữ đường cũ không hoạt động |
| Dữ liệu xác thực cũ | Kho hoạt động và backup | Bảo vệ, giữ lại hoặc xử lý theo chính sách áp dụng |

Nếu cơ chế mới có tham số khác, như thời hạn hoặc điều kiện khôi phục, cần xem xét đó là thay đổi yêu cầu. Không gắn nhãn “tương đương” khi chưa đánh giá thuộc tính bảo vệ thực tế.

### 6.2. Có yêu cầu kế nhiệm chưa đủ

Trước khi chuyển hiệu lực cần xác nhận:

1. Yêu cầu kế nhiệm đã rõ phạm vi và được chấp thuận theo quy trình.
2. Thành phần thực hiện đã được triển khai ở phạm vi cần thiết.
3. Có bằng chứng đánh giá phù hợp với thuộc tính bảo vệ.
4. Trách nhiệm của ứng dụng và nhà cung cấp không bị bỏ trống.
5. Các khoảng thời gian giao nhau hoặc chuyển tiếp được quản lý.
6. Người vận hành biết kiểm soát nào còn phải duy trì.

Không để yêu cầu cũ hết hiệu lực trước khi cơ chế mới đủ điều kiện, trừ khi phạm vi tạo rủi ro đã thực sự dừng và có quyết định phù hợp.

### 6.3. Quyền quyết định không chuyển theo vị trí dữ liệu

Nhà cung cấp có thể vận hành một kiểm soát nhưng không tự có thẩm quyền xóa nghĩa vụ của bên sử dụng. Hệ thống khách hàng vẫn cần kiểm tra điều kiện sử dụng, cấu hình tích hợp, bằng chứng và phần trách nhiệm của mình.

Tương tự, chuyển dữ liệu vào archive không tự giải phóng yêu cầu bảo mật dữ liệu đó.

## 7. Điều kiện hoàn tất phải kiểm chứng được

Retire cũng cần tiêu chí quan sát được. Câu “đã chuyển xong” không cho biết những gì đã được xác minh.

Ví dụ với luồng reset cục bộ:

| Điều kiện | Bằng chứng phù hợp |
| --- | --- |
| Không còn người dùng thuộc phạm vi dựa vào reset cục bộ | Kiểm kê tài khoản, nhóm khách hàng và cấu hình xác thực |
| Các điểm vào cũ không thực hiện chức năng | Kiểm thử trực tiếp API và đường truy cập trên các môi trường thuộc phạm vi |
| Không còn phát hành token mới | Cấu hình, phân tích thành phần phát hành và kiểm tra tác vụ liên quan |
| Token cũ không còn dùng được | Kiểm tra token đã phát hành trước chuyển đổi và trạng thái xác thực liên quan |
| Không còn tác vụ cũ có thể khôi phục luồng | Kiểm kê hàng đợi, lịch chạy, worker và mẫu email có liên quan |
| Cơ chế kế nhiệm hoạt động đúng | Bằng chứng khôi phục danh tính và kiểm thử tích hợp với ứng dụng |
| Dữ liệu còn lại có người chịu trách nhiệm | Danh mục dữ liệu, quyền truy cập và lịch giữ lại/xử lý |
| Phục hồi không mở lại cơ chế cũ | Diễn tập hoặc đánh giá quy trình phục hồi và cấu hình đích |
| Hồ sơ đã được cập nhật | Baseline, truy vết, danh mục kiểm soát và quyết định hiệu lực |

Kiểm tra trực tiếp điểm vào giúp phát hiện trường hợp giao diện đã ẩn nhưng API vẫn nhận yêu cầu. Kiểm kê triển khai giúp phát hiện bản cũ còn hoạt động ở môi trường khác.

### Điều kiện không đạt

Cần ghi rõ khi nào chưa được retire, chẳng hạn:

- Còn tenant đang dùng đăng nhập hoặc reset cục bộ.
- Còn tài khoản hỗ trợ khẩn cấp phụ thuộc cơ chế đó.
- Không xác định được ai quản lý dữ liệu xác thực trong backup.
- Chưa chứng minh việc phục hồi không bật lại đường cũ.
- Có yêu cầu kế nhiệm trên tài liệu nhưng chưa có bằng chứng triển khai.
- Một hệ thống khác vẫn phụ thuộc kiểm soát đang chuẩn bị loại bỏ.

Việc chưa đủ bằng chứng phải được ghi nhận đúng nghĩa. Không thay bằng kết luận “không áp dụng” để hoàn tất kế hoạch.

### Vai trò của quan sát sau chuyển đổi

Theo dõi lưu lượng, lỗi và hành vi người dùng giúp phát hiện phụ thuộc còn sót. Khoảng quan sát cần dựa trên chu kỳ nghiệp vụ và rủi ro, không mặc định một số ngày chung cho mọi hệ thống.

Quan sát không thay thế kiểm tra khả năng truy cập và cấu hình. Một API không có lượt gọi vẫn có thể đang mở.

## 8. Quy trình xử lý một đề xuất retire

Quy trình sau là mô hình thực hành của bài học, không phải tập trạng thái bắt buộc do NIST hoặc OWASP quy định.

~~~mermaid
flowchart TD
    A[Yêu cầu đang có hiệu lực] --> B[Đề xuất retire và nêu phạm vi]
    B --> C[Phân tích nguồn, rủi ro và phụ thuộc]
    C --> D{Cơ sở thay đổi có phù hợp?}
    D -->|Chưa phù hợp| A
    D -->|Phù hợp| E[Quyết định kế hoạch và điều kiện chuyển tiếp]
    E --> F[Triển khai thay đổi, giữ nghĩa vụ còn áp dụng]
    F --> G[Đánh giá điều kiện hoàn tất]
    G --> H{Đủ bằng chứng và điều kiện?}
    H -->|Chưa| F
    H -->|Đủ| I[Xác nhận thời điểm retire theo phạm vi]
    I --> J[Cập nhật baseline, lịch sử và vận hành]
    J --> K[Theo dõi điều kiện có thể làm phạm vi áp dụng trở lại]
~~~

### Bước 1 — Lập đề xuất có nguồn

Ghi mã và phiên bản yêu cầu, phát biểu hiện hành, nguồn, lý do, phạm vi đề nghị và thời điểm dự kiến. Liên kết với thay đổi chức năng, kiến trúc hoặc nguồn ràng buộc làm phát sinh đề xuất.

Không sửa lịch sử để tạo cảm giác yêu cầu chưa từng tồn tại.

### Bước 2 — Phân tích tác động và khoảng trống

Xác định các nghĩa vụ còn lại, yêu cầu kế nhiệm, dữ liệu tồn, phụ thuộc, phiên bản đang dùng và cách khôi phục. Đánh giá rủi ro nếu retire và nếu giữ yêu cầu hiện hành.

Nếu yêu cầu trùng, đối chiếu cả điều kiện, ngoại lệ, ngưỡng và phạm vi; cùng tên không có nghĩa cùng nội dung.

### Bước 3 — Xác định người quyết định và điều kiện

Tổ chức cần có người đủ thẩm quyền quyết định thay đổi trong phạm vi liên quan. Có thể cần chủ yêu cầu, chủ hệ thống, chủ dữ liệu hoặc người quản lý nguồn ràng buộc.

Không phải mọi thay đổi đều cần một hội đồng riêng. Mức xem xét phụ thuộc tác động và quy trình hiện hành, nhưng phải xác định được trách nhiệm.

### Bước 4 — Thực hiện chuyển tiếp

Triển khai yêu cầu mới hoặc ngừng phạm vi cũ, kiểm soát tài khoản và tích hợp còn tồn, cập nhật cấu hình và thông báo cần thiết.

Trong chuyển tiếp, giữ yêu cầu cũ ở phạm vi nó vẫn bảo vệ. Nếu có ngoại lệ, ghi riêng cùng thời hạn và người quyết định; không đánh đồng với việc ngừng hiệu lực.

### Bước 5 — Đánh giá và xác nhận hiệu lực

Đối chiếu kết quả với tiêu chí hoàn tất, ghi bằng chứng và giới hạn. Khi điều kiện đã đáp ứng, xác nhận thời điểm có hiệu lực theo cơ chế đã quyết định.

Nếu kết quả khác kế hoạch, cập nhật đề xuất hoặc tiếp tục chuyển tiếp. Không tự lùi ngày hiệu lực để hợp thức hóa khoảng trống đã xảy ra.

### Bước 6 — Cập nhật các sản phẩm liên quan

Cập nhật baseline, ma trận truy vết, danh mục kiểm soát, tài liệu thiết kế, đánh giá, hướng dẫn vận hành và thông tin hỗ trợ khách hàng có liên quan.

Những yêu cầu mới như “không cho phép bật lại cơ chế cũ ngoài quy trình” vẫn có thể cần giám sát trong vận hành.

## 9. Phân công trách nhiệm

| Vai trò | Phần trách nhiệm cần làm rõ |
| --- | --- |
| Chủ yêu cầu hoặc chủ nghiệp vụ | Xác nhận mục tiêu, quy tắc và lý do thay đổi |
| Chủ hệ thống | Xác định phạm vi triển khai và tổ chức thực hiện |
| Nhóm bảo mật | Phân tích rủi ro, phụ thuộc và khoảng trống bảo vệ |
| Chủ dữ liệu | Xác nhận dữ liệu còn tồn và yêu cầu xử lý |
| Người phụ trách nghĩa vụ áp dụng | Xác nhận nguồn hợp đồng, chính sách hoặc nghĩa vụ có thực sự thay đổi |
| Đội phát triển và kiến trúc | Xác định thành phần, mã và cấu hình bị ảnh hưởng |
| QA hoặc người đánh giá | Thu thập bằng chứng theo tiêu chí hoàn tất |
| Vận hành và phục hồi | Loại bỏ phụ thuộc cũ, điều chỉnh runbook, kiểm tra khôi phục |
| Chủ kiểm soát dùng chung hoặc nhà cung cấp | Xác nhận phạm vi kế thừa và trách nhiệm được chuyển giao |
| Người có thẩm quyền quyết định | Chấp thuận thay đổi và điều kiện theo phạm vi thẩm quyền |

Một người có thể giữ nhiều vai trò. Điều cần tránh là không có ai nhận trách nhiệm cho dữ liệu, cấu hình hoặc bằng chứng sau khi nhóm dự án kết thúc.

Đối với nghĩa vụ bên ngoài, cần kiểm tra cơ chế thay đổi hoặc miễn trừ thực sự được phép. Việc sửa backlog nội bộ không tự thay đổi hợp đồng hay nghĩa vụ áp dụng.

## 10. Dữ liệu, logging và phục hồi sau khi retire

### 10.1. Dữ liệu cũ có thể tiếp tục tạo nghĩa vụ bảo vệ

Một luồng đã ngừng vẫn có thể để lại:

- Dữ liệu xác thực hoặc thông tin khôi phục.
- Tệp tạm, bản xuất, cache và chỉ mục tìm kiếm.
- Log, báo cáo sự cố và bằng chứng đánh giá.
- Backup, snapshot hoặc dữ liệu do nhà cung cấp giữ.
- Bản sao ở môi trường hỗ trợ hoặc phục hồi.

Với từng loại, cần ghi người quản lý, quyền truy cập, thời hạn giữ lại, cách xử lý khi hết hạn và điều kiện phục hồi. Không retire yêu cầu bảo vệ dữ liệu chỉ vì chức năng tạo dữ liệu đã dừng.

Ngược lại, không giữ mọi bản sao vô thời hạn chỉ để có thể giải thích lịch sử. Bản ghi yêu cầu và bằng chứng nên được lưu theo chính sách phù hợp, giảm thông tin nhạy cảm khi có thể.

### 10.2. Điều chỉnh logging theo hành vi mới

Sau khi chuyển sang IdP, ứng dụng có thể không còn phát sinh sự kiện “local_password_reset_completed”. Cần:

- Giữ khả năng đọc và giải thích log lịch sử trong thời hạn lưu.
- Xác định sự kiện nào từ IdP thay thế cho mục đích điều tra.
- Làm rõ quan hệ danh tính, tenant, thời gian và mã tương quan giữa các nguồn.
- Bỏ hoặc sửa cảnh báo chỉ đúng với kiến trúc cũ.
- Duy trì cảnh báo về việc đường cũ bất ngờ hoạt động trở lại nếu rủi ro yêu cầu.

Không xóa mọi kiểm tra logging cùng với yêu cầu cũ. Mục tiêu phát hiện và truy vết có thể vẫn hiện hành nhưng cần bằng chứng từ nguồn khác.

### 10.3. Backup và rollback không được làm sống lại phạm vi cũ ngoài kiểm soát

Một bản backup có thể chứa cấu hình bật luồng cũ; một gói triển khai cũ có thể vẫn có API reset. Kế hoạch phục hồi cần xác định baseline đích, bước chuyển đổi cấu hình và kiểm tra trước khi mở dịch vụ.

Nếu rollback thực sự cần đưa cơ chế cũ trở lại hoạt động:

1. Xem xét lại phạm vi và rủi ro.
2. Khôi phục hoặc sửa các yêu cầu cần thiết trong baseline có kiểm soát.
3. Đánh giá trạng thái bảo vệ của phiên bản quay lui.
4. Có quyết định phù hợp trước khi mở phạm vi theo quy trình đã xác định.

Quyền rollback kỹ thuật không tự thay thế quyết định về hiệu lực yêu cầu.

[NIST SP 800-37 Rev. 2, nhiệm vụ M-7](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf) đề cập chiến lược xử lý khi hệ thống hoặc thành phần rời vận hành, cùng việc cập nhật kiểm kê và kế hoạch bảo vệ. Đây là tham chiếu cho phần tác động vận hành; ngừng một yêu cầu không đồng nghĩa đã hoàn tất xử lý toàn hệ thống.

[OWASP SAMM — System Decommissioning / Legacy Management](https://owaspsamm.org/model/operations/operational-management/stream-b/) cũng nhấn mạnh quản lý chuyển đổi khách hàng, phiên bản cũ và các tài nguyên liên quan khi ngừng dịch vụ. Áp dụng vào retire requirement, nhóm phải kiểm tra môi trường thực tế thay vì chỉ sửa tài liệu yêu cầu.

## 11. Ví dụ: ngừng yêu cầu về reset mật khẩu cục bộ

### 11.1. Bối cảnh

Một cổng đối tác từng quản lý tài khoản và reset mật khẩu trong ứng dụng. Yêu cầu hiện hành:

**SR-LOCAL-RESET-01:** Token reset mật khẩu cục bộ chỉ được sử dụng thành công một lần và phải hết hiệu lực sau tối đa 15 phút kể từ khi phát hành.

Giới hạn 15 phút là giả định của ví dụ. Mục tiêu cha **GOAL-ID-01** là ngăn người không được phép chiếm quyền điều khiển tài khoản.

Tổ chức quyết định chuyển sang IdP. Trong kiến trúc đích, ứng dụng không còn tạo hoặc xác minh mật khẩu cục bộ; việc khôi phục danh tính được xử lý tại IdP theo các yêu cầu đã được đánh giá.

### 11.2. Đề xuất đầu tiên chưa đủ điều kiện

Nhóm đề xuất retire SR-LOCAL-RESET-01 vì màn hình đăng nhập mới đã được phát hành.

Phân tích cho thấy:

- Một số tenant vẫn dùng cấu hình đăng nhập cục bộ.
- Nhánh bảo trì của phiên bản cũ vẫn được hỗ trợ.
- API reset vẫn gọi trực tiếp được dù nút trên giao diện đã ẩn.
- Một worker vẫn có thể gửi email từ yêu cầu cũ trong hàng đợi.
- Bản phục hồi tiêu chuẩn chưa áp dụng cấu hình IdP mới.

Kết luận phù hợp là tiếp tục giữ yêu cầu trong phần phạm vi còn áp dụng và hoàn thiện chuyển đổi. Chưa có cơ sở retire toàn cục.

### 11.3. Các nghĩa vụ sau khi chuyển đổi

Nhóm xác định các yêu cầu sau. Đây là cấu trúc minh họa, chưa thay thế đặc tả chi tiết của một hệ thống thực.

| Mã | Nghĩa vụ | Trạng thái sau chuyển đổi |
| --- | --- | --- |
| GOAL-ID-01 | Bảo vệ tài khoản khỏi bị chiếm quyền trái phép | Tiếp tục hiện hành |
| SR-LOCAL-RESET-01 | Giới hạn hiệu lực và sử dụng token reset cục bộ | Được đề xuất retire khi không còn luồng áp dụng |
| SR-IDP-RECOVERY-01 | Cơ chế khôi phục tại IdP đáp ứng các thuộc tính bảo vệ và tham số được chấp thuận | Hiện hành trong kiến trúc đích |
| SR-APP-SESSION-01 | Ứng dụng xử lý trạng thái tài khoản và thu hồi phiên theo chính sách đã xác định | Tiếp tục hiện hành, cập nhật phần tích hợp |
| SR-NO-LOCAL-01 | Ứng dụng thuộc baseline đích không được cung cấp reset mật khẩu cục bộ | Hiện hành, dùng để phát hiện việc mở lại luồng cũ |
| SR-CRED-DATA-01 | Bảo vệ dữ liệu xác thực cũ còn được giữ lại | Hiện hành trong thời gian dữ liệu còn thuộc phạm vi |
| SR-AUDIT-ID-01 | Có bằng chứng điều tra các sự kiện danh tính quan trọng | Hiện hành, điều chỉnh nguồn sự kiện |
| SR-RESTORE-ID-01 | Phục hồi đúng baseline danh tính đã được chấp thuận | Hiện hành trong quy trình phục hồi |

Yêu cầu tại IdP phải được đặc tả và xác minh về nội dung thực tế. Nếu không còn dùng token giống cơ chế cũ, phải chứng minh cơ chế mới bảo vệ mục tiêu bằng các thuộc tính phù hợp; không yêu cầu hai giải pháp có cùng cấu trúc nội bộ chỉ vì chúng thay thế nhau.

### 11.4. Điều kiện để xác nhận retire trong phạm vi đích

Nhóm thống nhất rằng chỉ xác nhận SR-LOCAL-RESET-01 ngừng hiệu lực khi:

1. Danh sách tenant và bản đang được hỗ trợ trong phạm vi đều đã chuyển đổi.
2. Không còn tài khoản cục bộ đang hoạt động dựa vào luồng reset này.
3. Các API phát hành và tiêu thụ token cũ không còn thực hiện chức năng reset.
4. Token đã phát hành được vô hiệu hóa hoặc được xác minh không còn khả năng sử dụng.
5. Worker, hàng đợi và lịch chạy cũ đã được xử lý.
6. Các yêu cầu kế nhiệm có bằng chứng phù hợp.
7. Dữ liệu còn tồn có kế hoạch bảo vệ và xử lý riêng.
8. Quy trình phục hồi duy trì kiến trúc danh tính đích.
9. Hồ sơ thay đổi được người có thẩm quyền xác nhận theo phạm vi.

Một khoảng theo dõi sau chuyển đổi hỗ trợ phát hiện tích hợp còn sót. Nó không thay cho các điều kiện kỹ thuật đã liệt kê.

### 11.5. Diễn biến theo baseline

| Baseline | Hiện trạng | Hiệu lực của SR-LOCAL-RESET-01 |
| --- | --- | --- |
| B1 | Reset cục bộ hoạt động | Hiện hành trong phạm vi cũ |
| B2 | Chuyển một phần tenant sang IdP | Vẫn hiện hành cho tenant và phiên bản còn dùng luồng cũ |
| B3 | Đã triển khai kiến trúc đích, đang xác minh điều kiện hoàn tất | Chưa xác nhận retire chỉ vì triển khai đã xong |
| B4 | Điều kiện hoàn tất đã được xác nhận, quyết định có hiệu lực | Retired trong phạm vi B4; lịch sử B1–B3 được giữ nguyên |

Nếu vẫn còn một phiên bản cũ được phép phục vụ reset cục bộ, bảng phải thể hiện phạm vi đó còn hiện hành. Không ghi retired cho toàn sản phẩm chỉ vì baseline mới đã đáp ứng điều kiện.

## 12. Bản ghi quyết định và cập nhật truy vết

### 12.1. Thông tin nên có trong quyết định

| Trường | Ý nghĩa |
| --- | --- |
| Mã quyết định | Liên kết các hoạt động và bằng chứng của thay đổi |
| Mã, phiên bản yêu cầu | Nhận diện chính xác nội dung ngừng hiệu lực |
| Phát biểu hoặc tham chiếu lịch sử | Hiểu yêu cầu từng bảo vệ điều gì |
| Lý do | Nguồn thay đổi, chức năng dừng hoặc nghĩa vụ được thay thế |
| Phạm vi | Hệ thống, môi trường, tenant, phiên bản và dữ liệu |
| Yêu cầu kế nhiệm | Quan hệ thay thế và các nghĩa vụ vẫn hiện hành |
| Phân tích tác động | Rủi ro, phụ thuộc, dữ liệu còn lại và điều kiện phục hồi |
| Điều kiện hoàn tất | Những điều phải được kiểm chứng trước khi có hiệu lực |
| Bằng chứng | Kết quả gắn với đúng phiên bản và cấu hình |
| Người quyết định | Vai trò, thẩm quyền và tham chiếu xác nhận |
| Thời điểm hiệu lực | Thời gian thực tế theo điều kiện được chấp thuận |
| Nghĩa vụ sau retire | Bảo vệ dữ liệu, bằng chứng, giám sát hoặc hỗ trợ còn lại |
| Điều kiện xem xét lại | Những thay đổi làm căn cứ retire không còn đúng |

### 12.2. Bản ghi minh họa

~~~text
Quyết định: RETIRE-LOCAL-RESET-01
Yêu cầu: SR-LOCAL-RESET-01, phiên bản 1.2

Lý do:
Ứng dụng trong phạm vi đích không còn cung cấp reset mật khẩu cục bộ.
Khôi phục danh tính được chuyển sang IdP theo các yêu cầu đã chấp thuận.

Phạm vi:
Baseline B4 của cổng đối tác và các triển khai có trong danh mục
chuyển đổi đã được xác nhận.
Không suy rộng sang một bản hoặc môi trường chưa được kiểm kê.

Điều kiện hiệu lực:
- Các điểm vào reset cục bộ không thực hiện chức năng.
- Không còn tài khoản hoạt động phụ thuộc cơ chế đó.
- Token và tác vụ tồn đã được xử lý.
- Bằng chứng của cơ chế kế nhiệm đã được chấp nhận.
- Phục hồi không tự bật lại luồng cũ.

Nghĩa vụ tiếp tục:
GOAL-ID-01, SR-IDP-RECOVERY-01, SR-APP-SESSION-01,
SR-NO-LOCAL-01, SR-CRED-DATA-01, SR-AUDIT-ID-01,
SR-RESTORE-ID-01.

Bằng chứng:
Manifest kết quả chuyển đổi, kiểm thử và phục hồi của baseline B4.

Xác nhận:
Tham chiếu bản ghi quyết định của người có thẩm quyền.

Thời điểm hiệu lực:
Ghi thời điểm thực tế sau khi điều kiện được xác nhận.

Xem xét lại khi:
Đề nghị khôi phục đăng nhập cục bộ, bổ sung luồng dự phòng,
hoặc phát hiện triển khai còn cung cấp reset cục bộ.
~~~

Mẫu là tài liệu minh họa, không tự tạo một phê duyệt thực. Trong hồ sơ được sử dụng, thời điểm, phạm vi và tham chiếu bằng chứng phải được điền cụ thể; không đánh dấu hoàn tất khi còn thiếu thông tin trọng yếu.

### 12.3. Giữ truy vết và ý nghĩa lịch sử

Sau khi retire:

- Giữ mã cũ để các báo cáo và kết quả đánh giá trước đây vẫn giải thích được.
- Không tái sử dụng mã đó cho một yêu cầu khác không liên quan.
- Ghi quan hệ thay thế và phần mục tiêu còn hiện hành.
- Tách ngày quyết định, ngày có hiệu lực và baseline chịu tác động.
- Đánh dấu rõ tài liệu hiện hành và bản lịch sử.
- Quản lý quyền truy cập và thời hạn lưu hiện vật phù hợp.

Nếu nội dung được xem xét trở lại, có thể tạo phiên bản mới hoặc yêu cầu mới theo quy tắc quản lý của tổ chức. Phải có dấu vết về khoảng thời gian và phạm vi thay đổi, thay vì âm thầm đổi bản retired thành active rồi xóa lịch sử.

## 13. Xử lý kiểm thử, phát hiện và số liệu

### 13.1. Không xóa tất cả kiểm thử gắn với yêu cầu cũ

Các kiểm thử có thể được xử lý khác nhau:

| Loại kiểm thử | Cách xử lý có thể phù hợp |
| --- | --- |
| Kiểm tra hành vi token reset cục bộ trên bản không còn luồng đó | Ngừng chạy trong suite hiện hành của phạm vi đích; giữ tham chiếu lịch sử theo chính sách |
| Kiểm tra bản cũ vẫn được hỗ trợ | Tiếp tục chạy theo baseline và phạm vi còn áp dụng |
| Kiểm tra API cũ không còn thực hiện reset | Chuyển thành bằng chứng hoặc kiểm tra hồi quy cho SR-NO-LOCAL-01 |
| Kiểm tra khôi phục tài khoản qua IdP | Liên kết với yêu cầu kế nhiệm |
| Kiểm tra thu hồi phiên ứng dụng | Tiếp tục theo yêu cầu hiện hành |
| Kiểm tra dữ liệu cũ trong backup | Tiếp tục nếu dữ liệu và nghĩa vụ bảo vệ còn tồn tại |

Tách việc lưu bằng chứng lịch sử khỏi việc chạy tự động hằng ngày. Không nhất thiết duy trì hạ tầng không an toàn chỉ để chạy lại mọi kiểm thử của một bản đã ngừng; cần quản lý hiện vật theo chính sách và nhu cầu đánh giá thực tế.

### 13.2. Phát hiện cũ cần kết luận riêng

Nếu một phát hiện liên quan luồng đã ngừng, có thể đánh giá rằng nó không còn áp dụng cho phạm vi đích. Kết luận phải dẫn đến bằng chứng loại bỏ khả năng gây hại tương ứng.

Không ghi “đã sửa” khi thực tế là chức năng đã được loại khỏi phạm vi. Nếu dữ liệu từng bị lộ hoặc sự cố đã xảy ra, việc retire không tự đóng trách nhiệm điều tra, xử lý hậu quả hoặc các nghĩa vụ liên quan.

Một phát hiện có nhiều nguyên nhân cũng có thể tiếp tục tồn tại ở luồng mới. Ví dụ lỗi ánh xạ tenant không được giải quyết chỉ bằng việc chuyển xác thực sang IdP.

### 13.3. Báo cáo thay đổi baseline thay vì làm đẹp tỷ lệ đạt

Giả sử baseline cũ có 50 yêu cầu: 45 đạt và 5 chưa đạt. Nếu chỉ loại 5 yêu cầu chưa đạt rồi báo 45/45 đạt, con số không cho biết rủi ro đã thay đổi như thế nào.

Báo cáo cần thể hiện:

- Những yêu cầu nào đã ngừng hiệu lực và vì sao.
- Phạm vi và thời điểm có hiệu lực.
- Yêu cầu mới hoặc nghĩa vụ được chuyển giao.
- Kết quả đánh giá trước và sau theo đúng baseline.
- Rủi ro hoặc phát hiện nào còn mở.

Một yêu cầu retire đúng căn cứ có thể làm baseline gọn hơn. Nhưng giảm số dòng không phải phép đo trực tiếp mức giảm rủi ro.

## 14. Sai sót thường gặp và cách xử lý

| Sai sót | Rủi ro tạo ra | Cách xử lý |
| --- | --- | --- |
| Retire vì ticket triển khai đã hoàn thành | Ngừng duy trì bảo vệ vẫn cần thiết | Tách trạng thái công việc, đáp ứng và hiệu lực |
| Xóa yêu cầu khỏi tài liệu hiện hành lẫn lịch sử | Mất khả năng giải thích quyết định cũ | Giữ bản ghi và quan hệ phiên bản theo chính sách |
| Chỉ dựa vào không có lưu lượng | Điểm vào vẫn có thể bị gọi | Đối chiếu kiểm kê, cấu hình và kiểm tra trực tiếp |
| Chỉ xét nhánh chính | Bản cũ hoặc môi trường khác vẫn hoạt động | Quản lý phạm vi theo triển khai và trạng thái hỗ trợ |
| Cho yêu cầu cũ hết hiệu lực trước khi yêu cầu mới sẵn sàng | Có khoảng trống bảo vệ | Xác định điều kiện chuyển giao và thứ tự thực hiện |
| Coi IdP thay mọi yêu cầu phân quyền | Quyền tài nguyên ứng dụng bị bỏ sót | Giữ ranh giới trách nhiệm và đánh giá tích hợp |
| Quên dữ liệu trong backup và log | Dữ liệu không còn người bảo vệ | Giữ các yêu cầu dữ liệu và người chịu trách nhiệm |
| Tắt mọi cảnh báo liên quan cơ chế cũ | Không phát hiện cơ chế bị bật lại | Giữ tín hiệu cần thiết theo yêu cầu mới |
| Rollback làm luồng cũ hoạt động lại | Baseline thực tế không khớp quyết định | Kiểm soát khôi phục, cấu hình và thay đổi phạm vi |
| Gọi ngoại lệ là retire | Che khuất nghĩa vụ và rủi ro còn tồn | Ghi riêng quyết định ngoại lệ và giới hạn |
| Tự suy rằng nghĩa vụ ngoài tổ chức đã hết | Loại bỏ yêu cầu vẫn áp dụng | Xác minh nguồn và thẩm quyền thay đổi |
| Xóa phát hiện để tỷ lệ đạt tăng | Báo cáo không phản ánh trạng thái rủi ro | Giữ lịch sử và nêu rõ lý do kết luận theo phạm vi |

## 15. Tiêu chí hoàn tất một quyết định retire

Đây là kiểm tra mức đầy đủ của hồ sơ và việc chuyển đổi. Mức bằng chứng phải phù hợp với tác động của thay đổi.

- [ ] Xác định đúng mã, phiên bản, nội dung và nguồn của yêu cầu.
- [ ] Có lý do giải thích vì sao yêu cầu không còn áp dụng hoặc được thay thế.
- [ ] Phạm vi gồm các môi trường, phiên bản và nhóm sử dụng liên quan.
- [ ] Đã kiểm tra mục tiêu, nghĩa vụ và rủi ro cha.
- [ ] Các yêu cầu kế nhiệm hoặc nghĩa vụ tiếp tục được chỉ rõ.
- [ ] Có bằng chứng cơ chế mới đáp ứng phần bảo vệ được chuyển giao.
- [ ] Đã kiểm tra các điểm vào, tài khoản, tác vụ và tích hợp còn sót.
- [ ] Dữ liệu, log, backup và hiện vật còn lại có người quản lý.
- [ ] Kế hoạch phục hồi hoặc rollback không tự tạo lại phạm vi ngoài kiểm soát.
- [ ] Điều kiện hoàn tất và thời điểm hiệu lực được xác nhận.
- [ ] Người có thẩm quyền đã quyết định theo đúng phạm vi.
- [ ] Baseline, truy vết, kiểm thử, tài liệu vận hành và báo cáo được cập nhật.
- [ ] Lịch sử đáp ứng và phát hiện trước đây không bị viết lại.
- [ ] Có điều kiện xem xét lại khi căn cứ retire thay đổi.

## 16. Tài liệu tham khảo

- [NASA — Requirements Management](https://www.nasa.gov/reference/6-2-requirements-management/): quản lý thay đổi baseline, truy vết và phân tích tác động.
- [OWASP SAMM — System Decommissioning / Legacy Management](https://owaspsamm.org/model/operations/operational-management/stream-b/): chuyển đổi phiên bản cũ và xử lý tài nguyên liên quan khi ngừng vận hành.
- [NIST SP 800-37 Rev. 2](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-37r2.pdf): nhiệm vụ M-7 về system disposal và các cập nhật quản lý rủi ro liên quan.
