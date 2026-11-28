# Kiểm thử hiệu lực kiểm soát đặc quyền (Control testing)

Một chính sách PAM yêu cầu quản trị viên chỉ được nâng quyền sau khi phê duyệt, quyền phải hết hạn sau 30 phút và mọi phiên phải có bằng chứng. Giao diện có đủ ba tùy chọn đó chưa chứng minh kiểm soát hoạt động. Phép kiểm thử cần chỉ ra yêu cầu chưa được duyệt bị chặn, quyền được thu hồi đúng hạn trên tài nguyên đích và bằng chứng của các phiên thuộc phạm vi có thể truy xuất.

**Control testing** là quá trình thu thập, đối chiếu và đánh giá bằng chứng để xác định một kiểm soát có được thiết kế phù hợp và có vận hành theo tiêu chí đã xác định hay không. Trong Privileged Access Management (PAM), phép thử phải đi xuyên qua danh tính, quyết định cấp quyền, thông tin xác thực, tài nguyên đích, phiên sử dụng và dấu vết kiểm toán. Một kết quả “success” của bộ điều phối không thay thế được bằng chứng ở điểm thực thi.

Bài này hướng dẫn kiểm thử kiểm soát đối với tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Nội dung tập trung vào cách biến yêu cầu thành phép thử có thể lặp lại, xác lập tổng thể và mẫu, đánh giá ngoại lệ, rồi báo cáo trong phạm vi bằng chứng thực sự hỗ trợ.

## 1. Phân biệt mục tiêu, kiểm soát và phép kiểm thử

Ba khái niệm này liên quan nhưng không đồng nhất:

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong PAM |
| --- | --- | --- |
| Mục tiêu kiểm soát | Rủi ro nào cần giảm? | Hạn chế việc duy trì quyền quản trị sau khi công việc kết thúc |
| Kiểm soát | Cơ chế nào giúp đạt mục tiêu? | JIT cấp quyền có thời hạn, kèm cơ chế thu hồi và phát hiện lỗi thu hồi |
| Phép kiểm thử | Bằng chứng nào cho thấy cơ chế đáp ứng tiêu chí? | Đối chiếu thời hạn được duyệt, thời điểm thu hồi và quyền thực tế trên máy đích |

Một kiểm soát không nhất thiết thuộc riêng sản phẩm PAM. Quy trình nghỉ việc có thể cần sự phối hợp của hệ thống nhân sự, IdP, kho mật khẩu, nền tảng PAM và quản trị tài nguyên. Nếu nhân sự đã bị khóa trên IdP nhưng phiên đặc quyền đang tồn tại vẫn sử dụng được, phép thử chỉ tại IdP sẽ bỏ sót một phần mục tiêu.

### 1.1. Ba góc đánh giá

**Thiết kế phù hợp — design effectiveness.** Kiểm soát, nếu được vận hành đúng, có khả năng xử lý rủi ro đã nêu hay không? Ví dụ, JIT thu hồi thành viên nhóm nhưng để lại một token có quyền rộng và thời hạn dài có thể chưa đáp ứng mục tiêu chấm dứt khả năng sử dụng đặc quyền.

**Được triển khai — implementation.** Thiết kế có thực sự được áp dụng cho tài nguyên, danh tính và đường truy cập thuộc phạm vi hay chưa? Một policy đúng nhưng chưa gán cho nhóm máy sản xuất không bảo vệ được nhóm máy đó.

**Vận hành có hiệu lực — operating effectiveness.** Trong khoảng thời gian kiểm tra, kiểm soát có hoạt động nhất quán theo thiết kế và tiêu chí không? Một lần trình diễn thành công tại cuối kỳ không chứng minh mọi lần thực thi trong cả kỳ.

Có thể phải ghi nhận nhiều kết luận cho cùng một kiểm soát. Chẳng hạn thiết kế hợp lý, triển khai đầy đủ, nhưng vận hành thất bại khi một tác vụ thu hồi bị lỗi và không được xử lý.

### 1.2. Kiểm thử khác với quan sát trạng thái

Giám sát phát hiện tình huống đang xảy ra, còn kiểm thử kiểm soát đánh giá một mục tiêu và tiêu chí cụ thể. Dữ liệu giám sát có thể là đầu vào cho kiểm thử, nhưng không tự tạo ra kết luận.

Ví dụ, biểu đồ cho thấy 99% tác vụ luân chuyển credential thành công. Trước khi sử dụng số liệu này, người kiểm thử cần biết:

- Mẫu số có bao gồm các tác vụ đáng lẽ phải chạy nhưng không được lên lịch không?
- “Thành công” biểu thị cập nhật trong vault hay cả cập nhật trên tài nguyên đích?
- Có tính thử lại nhiều lần thành nhiều lần thành công không?
- Credential cũ có còn được chấp nhận ở đường truy cập khác không?
- Các tài khoản được miễn trừ có nằm ngoài mẫu số một cách hợp lệ không?

Không có cảnh báo cũng chưa phải bằng chứng rằng không có sai lệch. Nguồn log có thể đã mất kết nối hoặc quy tắc cảnh báo chưa được bật.

## 2. Viết tiêu chí đủ cụ thể để kiểm thử

Một mô tả như “quản lý quyền quản trị an toàn” không đủ để xác định PASS hay FAIL. Tiêu chí nên nêu rõ đối tượng, điều kiện, hành vi mong đợi, thời hạn và bằng chứng.

Ví dụ, tổ chức đặt ra yêu cầu nội bộ:

> Đối với truy cập quản trị thông thường vào nhóm máy sản xuất P, người yêu cầu phải được người có thẩm quyền khác phê duyệt trước khi quyền có hiệu lực. Quyền được cấp tối đa 30 phút và khả năng sử dụng quyền phải chấm dứt trong vòng 60 giây sau hạn, theo cơ chế thu hồi đã được phê duyệt.

Các giá trị 30 phút và 60 giây trong ví dụ là giả định của tổ chức, không phải ngưỡng chung cho mọi hệ thống. Trước khi kiểm thử, cần thống nhất cách hiểu “khả năng sử dụng quyền”: chặn phiên mới, thu hồi quyền hiện hữu hay kết thúc cả phiên đang chạy. Đây là các hành vi khác nhau.

Một hồ sơ tiêu chí có thể viết như sau:

| Thuộc tính | Nội dung ví dụ |
| --- | --- |
| Control ID | PAM-JIT-01 |
| Tài nguyên | Nhóm máy sản xuất P theo danh sách đã chốt |
| Danh tính | Tài khoản quản trị con người có định danh cá nhân |
| Điều kiện | Truy cập thông thường; đường khẩn cấp được kiểm tra bằng tiêu chí riêng |
| Yêu cầu | Phê duyệt độc lập trước khi cấp quyền |
| Thời hạn | Thời lượng tối đa và độ trễ thu hồi theo chính sách nội bộ |
| Bằng chứng | Request, approval, grant, revoke, quyền tại đích và thử truy cập sau hạn |
| Khoảng thời gian | Mốc bắt đầu và kết thúc, kèm múi giờ |
| Ngoại lệ | Chỉ chấp nhận ngoại lệ được phê duyệt trước và còn hiệu lực |

Mọi thay đổi tiêu chí giữa kỳ cần được giữ lịch sử. Nếu chính sách đổi từ 60 phút thành 30 phút vào giữa tháng, đánh giá từng sự kiện theo phiên bản có hiệu lực tại thời điểm đó. Không dùng cấu hình hiện tại để diễn giải toàn bộ lịch sử.

## 3. Xây dựng ma trận kiểm thử PAM

Ma trận giúp liên kết rủi ro với cách kiểm thử và bằng chứng. Cột bằng chứng không nên chỉ liệt kê ảnh chụp màn hình; phải nêu nguồn có thể xác minh quyết định và trạng thái thực thi.

| Kiểm soát | Rủi ro chính | Phép thử trọng tâm | Bằng chứng cần đối chiếu |
| --- | --- | --- | --- |
| Kiểm kê tài khoản đặc quyền | Tài khoản không được quản lý tiếp tục tồn tại | So sánh nguồn tài sản, quyền tại đích và danh sách được onboard | Danh sách tài nguyên, principal, entitlement và tài khoản PAM |
| Least privilege/JEA | Tài khoản làm được nhiều hơn nhu cầu | Thử thao tác được phép và thao tác ngoài phạm vi | Policy, nhóm quyền, kết quả thực thi trên đích |
| Phê duyệt JIT | Quyền được cấp khi chưa có quyết định hợp lệ | Đối chiếu người duyệt, thời điểm duyệt, tài nguyên và thời hạn | Request, approval và grant cùng định danh |
| Thu hồi quyền | Quyền vẫn dùng được sau hạn | Quan sát quyền tại đích và thử lại khả năng sử dụng sau hạn | Revoke event, trạng thái nhóm/token và kết quả truy cập |
| Vault và luân chuyển credential | Credential cũ hoặc bản sao không được kiểm soát vẫn dùng được | Kiểm tra cập nhật ở vault, tại đích và ảnh hưởng tới bên sử dụng | Phiên bản credential, tác vụ rotation, xác nhận đích, trạng thái ứng dụng |
| Ghi nhận phiên | Không thể truy nguyên hoạt động quản trị | Đối chiếu tổng thể phiên với log/bản ghi và thử truy xuất | Session ledger, metadata bản ghi, kiểm tra quyền đọc bằng chứng |
| Break-glass | Đường khẩn cấp bị lạm dụng hoặc không dùng được khi cần | Kiểm tra điều kiện kích hoạt, thông báo, hậu kiểm và trả trạng thái an toàn | Nhật ký sử dụng, cảnh báo, quyết định hậu kiểm, rotation sau dùng |
| Offboarding | Người đã rời tổ chức còn truy cập hoặc giữ secret | Đối chiếu sự kiện nghỉ việc với quyền, phiên và credential liên quan | Thời điểm kết thúc, disable/revoke, phiên và xác nhận thay secret |

Ma trận là bản đồ công việc. Mỗi dòng vẫn cần thủ tục đủ chi tiết để người khác lặp lại phép thử và hiểu phạm vi của kết luận.

Không mặc định mọi kiểm soát đều cần chạy thao tác chủ động trên sản xuất. Có phép thử phù hợp với đối chiếu log toàn bộ kỳ, có phép thử cần tài khoản kiểm thử, và có phép thử phải được bố trí trong môi trường riêng.

## 4. Lập kế hoạch, phạm vi và điều kiện thực hiện

### 4.1. Chốt phạm vi trước khi lấy dữ liệu

Phạm vi nên xác định được bằng danh sách hoặc quy tắc truy vấn rõ ràng:

- Hệ thống, tenant, vùng mạng và môi trường.
- Tài nguyên đích và đường truy cập: qua broker, SSH trực tiếp, console cloud hoặc API.
- Loại danh tính: con người, dịch vụ, workload, nhà cung cấp.
- Loại credential: mật khẩu, SSH key, certificate, token hoặc cơ chế định danh không dùng secret dài hạn.
- Policy và phiên bản policy áp dụng.
- Kỳ kiểm tra, thời điểm chốt dữ liệu và các trường hợp giao nhau với ranh giới kỳ.

Nếu chỉ thử kết nối qua cổng PAM mà không xem xét đường SSH trực tiếp vẫn mở, kết luận chỉ hỗ trợ đường qua cổng. Muốn kết luận mọi truy cập quản trị đều chịu kiểm soát, phải kiểm tra khả năng đi vòng hoặc có bằng chứng độc lập rằng các đường khác bị hạn chế.

### 4.2. Phân công trách nhiệm

Control owner giải thích mục tiêu và cơ chế vận hành. Người kiểm thử lựa chọn thủ tục, thu thập và đánh giá bằng chứng theo vai trò được giao. Chủ hệ thống xác nhận tác động có thể xảy ra khi thực hiện phép thử.

Mức độ độc lập cần phù hợp với mục đích đánh giá. Người vận hành có thể tự kiểm tra thường xuyên, nhưng báo cáo phải thể hiện đây là tự kiểm tra. Một hoạt động đánh giá độc lập không nên chỉ dựa vào tuyên bố của chính người chịu trách nhiệm vận hành.

Định danh rõ ai được chạy thao tác, ai quan sát, ai bảo quản bằng chứng, ai phân loại phát hiện và ai chấp nhận rủi ro còn lại. Tránh để người sửa lỗi tự quyết định đóng phát hiện mà không có bước xác minh theo quy trình.

### 4.3. Thiết kế phép thử không gây gián đoạn ngoài dự kiến

Luân chuyển mật khẩu, thu hồi token và chấm dứt phiên có thể ảnh hưởng ứng dụng hoặc hoạt động quản trị. Kế hoạch cần nêu tài khoản kiểm thử, tài nguyên đích, cửa sổ thực hiện, điều kiện dừng và cách khôi phục.

Một phép thử “credential cũ không còn dùng được” có thể gây khóa tài khoản nếu thử sai nhiều lần. Chỉ chạy số lần cần thiết bằng tài khoản và phương thức đã được cho phép; không đưa secret thật vào dòng lệnh, tệp bằng chứng hoặc lịch sử terminal.

Ưu tiên chứng minh cơ chế ở môi trường kiểm thử tương đương rồi kiểm tra cấu hình và bằng chứng vận hành trên sản xuất. Nếu môi trường khác biệt, ghi rõ phần nào chưa được chứng minh. Không dùng thành công trong lab để tự kết luận hiệu lực vận hành của sản xuất.

## 5. Xác lập tổng thể kiểm tra và độ đầy đủ dữ liệu

**Tổng thể — population** là tập các đối tượng hoặc lần thực thi mà kết luận hướng tới. Đơn vị tổng thể có thể là một tài khoản, một quyền được cấp, một yêu cầu truy cập, một phiên hoặc một lần rotation đến hạn.

Chọn sai đơn vị có thể làm sai kết quả dù lấy mẫu đúng kỹ thuật. Muốn kiểm tra mỗi lần cấp quyền có phê duyệt, đơn vị phù hợp là lần cấp quyền. Chọn một danh sách người dùng sẽ bỏ sót việc cùng một người được cấp quyền nhiều lần theo các điều kiện khác nhau.

### 5.1. Không lấy tổng thể chỉ từ nơi báo thành công

Nếu lấy tổng thể rotation từ danh sách tác vụ đã chạy, những tác vụ đáng lẽ phải được tạo nhưng chưa từng tồn tại sẽ biến mất khỏi phép thử.

Một cách đối chiếu hợp lý:

1. Xác định tài khoản thuộc diện phải rotation và lịch có hiệu lực.
2. Suy ra những lần đến hạn trong kỳ theo lịch đó.
3. Đối chiếu với các tác vụ thực tế, kể cả lỗi, hủy và chưa chạy.
4. Kiểm tra các lần đổi lịch, miễn trừ hoặc ngừng sử dụng được phê duyệt.
5. Ghi nhận trường hợp đến hạn nhưng không có lần thực thi tương ứng.

Tương tự, danh sách phiên trong kho ghi hình không phải tổng thể độc lập để kiểm tra “mọi phiên đều được ghi”. Nên lấy tổng thể phiên từ nguồn giao dịch hoặc nguồn đích, rồi đối chiếu với kho bằng chứng.

### 5.2. Kiểm tra kỹ thuật trích xuất

Lưu tiêu chí truy vấn, bộ lọc, phạm vi thời gian, múi giờ và thời điểm xuất. Kiểm tra phân trang, giới hạn số bản ghi, tài khoản có quyền đọc nguồn nào và nguồn nào đang lỗi kết nối.

Với tập dữ liệu lớn, cần xác minh:

- Trang cuối thực sự đã được lấy và không có cảnh báo cắt bớt.
- Số bản ghi trước và sau chuẩn hóa có giải thích được.
- Khóa định danh đủ phân biệt một lần thực thi với lần thử lại.
- Các trường quan trọng không bị null hoặc bị mất khi export.
- Dữ liệu đã quá thời hạn lưu giữ có làm kỳ kiểm tra bị thiếu không.
- Thời điểm ghi log và thời điểm sự kiện có khác nhau do hàng đợi hay không.

Một mã băm chứng minh tệp không đổi kể từ khi tính băm; nó không chứng minh truy vấn ban đầu lấy đủ dữ liệu hoặc nguồn log phản ánh đúng thực tế.

### 5.3. Chuẩn hóa thời gian và ranh giới kỳ

Chọn quy ước rõ ràng, chẳng hạn khoảng nửa mở `[start, end)`, và chuyển các mốc về cùng chuẩn thời gian để so sánh. Vẫn giữ giá trị gốc, múi giờ và nguồn chuyển đổi trong bằng chứng.

Một quyền được cấp trước đầu kỳ nhưng hết hạn trong kỳ vẫn có thể thuộc tổng thể kiểm tra thu hồi. Một quyền được cấp gần cuối kỳ và hết hạn sau cuối kỳ cần bằng chứng bổ sung nếu muốn kiểm tra đủ vòng đời. Không đánh dấu PASS chỉ vì chưa đến thời điểm phải thu hồi khi chốt báo cáo.

Độ trễ log và sai lệch đồng hồ phải được đánh giá. Nếu bằng chứng không đủ độ chính xác để phân biệt thu hồi trước hay sau ngưỡng 60 giây, kết quả chưa đủ cơ sở kết luận theo ngưỡng đó.

## 6. Chọn mẫu theo rủi ro và ghi rõ giới hạn

Không có một cỡ mẫu cố định phù hợp cho mọi kiểm soát PAM. Cách chọn phụ thuộc vào tần suất thực thi, quy mô tổng thể, mức độ tự động, mức tin cậy mong muốn, lịch sử sai lệch và mục đích đánh giá.

### 6.1. Ba cách tiếp cận

**Kiểm tra toàn bộ bằng phân tích dữ liệu.** Phù hợp với các điều kiện có thể xác định từ dữ liệu đáng tin cậy, như mọi grant đều có approval trước đó. Vẫn cần kiểm tra chất lượng dữ liệu và logic nối. Dữ liệu không chứa quyền thực tế tại đích thì phân tích toàn bộ log cũng không chứng minh được trạng thái tại đích.

**Chọn mẫu xác suất.** Mỗi phần tử có xác suất được chọn theo thiết kế đã xác định. Việc suy rộng cần phương pháp thống kê, giả định và cách xử lý sai lệch phù hợp. Không gọi một mẫu là ngẫu nhiên chỉ vì người kiểm thử chọn các dòng rải rác.

**Chọn mẫu có chủ đích theo rủi ro.** Ưu tiên tài nguyên quan trọng, quyền cao, truy cập ngoài giờ, thay đổi policy, lần thu hồi lỗi và đường khẩn cấp. Cách này hữu ích để tìm vấn đề nhưng thường không hỗ trợ suy rộng tỷ lệ sai lệch của toàn bộ tổng thể.

Có thể kết hợp các cách trên. Ví dụ kiểm tra toàn bộ mối liên hệ grant–approval bằng dữ liệu, rồi chọn mẫu có chủ đích để thử quyền thực tế và khả năng truy xuất bản ghi.

### 6.2. Phân tầng để tránh mẫu chỉ phản ánh đường thuận lợi

Các tầng đáng xem xét gồm:

| Chiều phân tầng | Ví dụ |
| --- | --- |
| Mức nhạy cảm | Hệ thống danh tính, vault, cơ sở dữ liệu sản xuất |
| Loại principal | Quản trị viên, service account, workload, vendor |
| Cơ chế quyền | JIT, quyền thường trực có ngoại lệ, break-glass |
| Công nghệ đích | Máy chủ, thiết bị mạng, cloud, cơ sở dữ liệu |
| Thời điểm | Trước/sau đổi policy, ngoài giờ, giai đoạn failover |
| Kết quả vận hành | Thành công, lỗi, thử lại, hủy, timeout |

Ghi tổng số phần tử từng tầng, cách chọn, lý do chọn và phần bị loại. Một mẫu chỉ gồm các tác vụ thành công vào giờ hành chính sẽ không phản ánh tốt hành vi khi connector lỗi hoặc khi hệ thống chuyển vùng.

Nếu chọn ngẫu nhiên, lưu quy tắc và seed khi phù hợp để tái lập. Nếu chọn theo rủi ro, lưu tiêu chí xếp ưu tiên. Không thay âm thầm một mẫu thất bại bằng mẫu khác dễ kiểm tra hơn.

### 6.3. Xử lý sai lệch trong mẫu

Một sai lệch cần được phân tích về bản chất, ảnh hưởng và khả năng lan rộng. Có thể mở rộng kiểm tra cho cùng connector, cùng phiên bản policy hoặc cùng khung thời gian để xác định phạm vi ảnh hưởng.

Tỷ lệ “1 lỗi trên 24 mẫu” chỉ mô tả tập mẫu đã kiểm tra. Với mẫu có chủ đích, không được tự chuyển thành khẳng định “4,17% mọi lần cấp quyền đều lỗi”.

Kết quả không thu thập được bằng chứng không mặc nhiên là thành công. Cần ghi thiếu bằng chứng, xác minh nguyên nhân và đánh giá liệu bản thân việc thiếu bằng chứng có vi phạm tiêu chí kiểm soát hay không.

## 7. Thực hiện phép thử: từ policy đến hành vi trên đích

Một thủ tục kiểm thử hữu ích thường có: điều kiện đầu vào, các bước, bằng chứng kỳ vọng, tiêu chí đánh giá và điều kiện dừng. Kết hợp nhiều phương thức giúp giảm phụ thuộc vào một nguồn.

| Phương thức | Giá trị | Giới hạn |
| --- | --- | --- |
| Phỏng vấn | Hiểu thiết kế, trách nhiệm và đường ngoại lệ | Lời giải thích không tự chứng minh vận hành |
| Kiểm tra tài liệu/cấu hình | Xác định policy và cấu hình có hiệu lực | Cấu hình có thể chưa được áp dụng tại đích |
| Quan sát | Thấy quy trình diễn ra trực tiếp | Chỉ phản ánh thời điểm quan sát |
| Tái thực hiện có kiểm soát | Kiểm chứng hành vi bằng một kịch bản xác định | Cần quyền thực hiện và quản lý tác động |
| Phân tích dữ liệu | Bao phủ nhiều giao dịch trong kỳ | Phụ thuộc độ đầy đủ, độ tin cậy của dữ liệu và logic |

### 7.1. JIT: phê duyệt và thu hồi

**Mục tiêu:** chỉ cấp quyền đúng phạm vi sau phê duyệt và kết thúc khả năng sử dụng đúng thời hạn.

Một kịch bản kiểm thử:

1. Tạo yêu cầu bằng tài khoản kiểm thử không có quyền quản trị nền.
2. Trước phê duyệt, thử một hành động quản trị vô hại đã được cho phép trong kế hoạch.
3. Xác nhận hành động bị từ chối vì chưa có quyền.
4. Duyệt bằng danh tính có thẩm quyền, khác người yêu cầu theo tiêu chí.
5. Đối chiếu tài nguyên, phạm vi quyền và thời lượng được duyệt với grant.
6. Trong thời hạn, xác nhận hành động được phép; hành động ngoài phạm vi vẫn bị chặn.
7. Sau hạn và cửa sổ thu hồi được phép, kiểm tra quyền tại đích và thử lại.
8. Kiểm tra phiên đã tồn tại theo đúng yêu cầu của chính sách.
9. Đối chiếu event thu hồi, lỗi nếu có, cảnh báo và xử lý tiếp theo.

Nếu thao tác sau hạn bị từ chối vì máy đích mất mạng, kết quả chưa chứng minh quyền đã được thu hồi. Cần phân biệt nguyên nhân từ chối bằng bằng chứng thích hợp.

Nếu tài khoản có thêm quyền từ nhóm khác, một lần revoke thành công trong PAM có thể không kết thúc đặc quyền thực tế. Phép thử phải xem quyền hiệu lực tổng hợp, gồm nhóm lồng nhau, role khác hoặc credential thay thế.

### 7.2. JEA/least privilege: thử cả hành động được phép và bị cấm

Chỉ kiểm tra một lệnh được phép chạy thành công là chưa đủ. Với một vai trò vận hành giới hạn, chọn ít nhất các nhóm hành vi cần chứng minh theo phạm vi:

- Hành động nghiệp vụ được cho phép.
- Hành động quản trị nằm ngoài vai trò.
- Tài nguyên ngoài tập được cấp quyền.
- Thay đổi phương thức gọi mà có thể vượt giới hạn của cùng hành động.

Không biến phép thử thành khai thác tùy ý. Các hành động âm tính phải nằm trong kế hoạch được cho phép và có tác động đã biết. Chỉ cần chứng minh đường kiểm soát có chặn hay không, không cần thực hiện phá hủy để chứng minh quyền quá rộng.

Lưu policy phiên bản tương ứng và phản hồi từ điểm thực thi. Ảnh giao diện role “read-only” không thay thế được xác nhận hành vi.

### 7.3. Vault và rotation: kiểm tra cả hai phía

**Mục tiêu:** credential được quản lý, thay đúng kỳ hoặc đúng sự kiện, và trạng thái giữa vault, tài nguyên đích cùng bên sử dụng nhất quán.

Các bước cần điều chỉnh theo loại credential:

1. Xác định tài khoản phải rotation, lịch đến hạn và ngoại lệ có hiệu lực.
2. Đối chiếu lần rotation với tài khoản, tài nguyên và phiên bản credential.
3. Kiểm tra bằng chứng cập nhật tại đích, không chỉ trạng thái tác vụ trên vault.
4. Khi được phép, xác nhận credential mới sử dụng được bằng thao tác xác thực tối thiểu.
5. Xác nhận credential cũ bị từ chối sau thời gian chuyển tiếp đã được phê duyệt.
6. Kiểm tra bên sử dụng đã nhận credential mới mà không tiếp tục phụ thuộc bản cũ.
7. Xác minh xử lý lỗi, thử lại, cảnh báo và trường hợp cập nhật một phía thành công.
8. Không đưa giá trị credential vào báo cáo hoặc log kiểm thử.

Một số cơ chế có giai đoạn chồng lấn hai credential để tránh gián đoạn. Phải đánh giá theo thiết kế được phê duyệt, gồm thời điểm hết chồng lấn; không coi việc credential cũ còn dùng được trong mọi trường hợp là cùng một loại lỗi.

Đổi mật khẩu không tự hủy mọi phiên, token hoặc vé đã phát hành trước đó. Nếu mục tiêu gồm chấm dứt quyền sau nghi ngờ lộ credential, cần phép thử riêng cho các dạng trạng thái xác thực còn tồn tại.

Với service account, xem cả phụ thuộc ứng dụng và danh sách bên sử dụng. Tài khoản đã rotation nhưng ứng dụng dùng một tài khoản phụ nằm ngoài vault có thể khiến số liệu thành công che giấu một đường truy cập chưa được quản lý.

### 7.4. Giám sát và bằng chứng phiên

**Mục tiêu:** hoạt động thuộc phạm vi có thể gắn với danh tính, được ghi nhận theo chính sách và chỉ người được phép mới truy cập được bằng chứng.

Thủ tục nên kiểm tra:

- Từ tổng thể phiên độc lập, tìm bản ghi/log tương ứng bằng session ID và định danh khác.
- Phân biệt phiên kết nối thất bại, phiên bị hủy và phiên có hoạt động thực tế.
- Kiểm tra metadata, thời gian, tài nguyên đích, danh tính và khả năng truy xuất.
- Kiểm tra bản ghi không rỗng, không hỏng và bao phủ phần hoạt động cần thiết.
- Kiểm tra thời hạn lưu, quyền đọc/xóa và dấu vết truy cập bằng chứng theo tiêu chí.
- Xác minh cảnh báo và cách xử lý khi bộ phận ghi nhận bị lỗi.

Có tệp ghi hình chưa chứng minh mọi lệnh đều được bao phủ; có log lệnh chưa chứng minh có đầy đủ dữ liệu màn hình. Chọn dạng bằng chứng theo yêu cầu thực tế, không gán khả năng cho một công nghệ ghi nhận mà chưa xác nhận.

Cũng cần kiểm tra việc che thông tin nhạy cảm theo thiết kế. Bằng chứng kiểm thử không nên tạo thêm bản sao secret hoặc dữ liệu sản xuất ngoài quy trình bảo vệ đã định.

### 7.5. Đường khẩn cấp và offboarding

Break-glass cần được đánh giá cả khả năng sử dụng khi phụ thuộc thông thường gặp sự cố và khả năng kiểm soát sau sử dụng. Tùy thiết kế, các tiêu chí có thể gồm điều kiện kích hoạt, người được giữ quyền, thông báo, giải trình, hậu kiểm và rotation credential sau dùng.

Không áp tiêu chí phê duyệt truy cập thông thường lên đường khẩn cấp nếu thiết kế đã phê duyệt cho phép trình tự khác. Thay vào đó, kiểm thử đúng các điều kiện và kiểm soát bù của đường khẩn cấp.

Với offboarding, lấy thời điểm kết thúc quan hệ làm đầu vào và kiểm tra những điểm vẫn có thể giữ quyền: tài khoản cá nhân, nhóm quản trị, SSH key, token, phiên đang mở, credential dùng chung người đó từng biết và quyền vendor liên quan. Chỉ khóa tài khoản PAM chưa đủ nếu người đó vẫn có tài khoản cục bộ tại đích.

## 8. Giữ bằng chứng đủ để tái lập và xem xét

Một bằng chứng tốt phải trả lời được ai, làm gì, trên tài nguyên nào, vào lúc nào, theo tiêu chí nào và từ nguồn nào. Một chuỗi bằng chứng cho JIT thường liên kết được:

```text
request_id
  -> approval_id + approver + thời điểm
  -> grant_id + principal + resource + phạm vi + hạn
  -> session_id hoặc hành vi thực thi tại đích
  -> revoke_id + thời điểm + trạng thái quyền thực tế
  -> test_id + kết quả + tham chiếu bằng chứng
```

Nếu một request có nhiều grant hoặc nhiều phiên, giữ quan hệ một-nhiều. Nối chỉ theo tên người dùng và phút gần nhất có thể ghép nhầm một lần duyệt cho nhiều lần cấp quyền.

### 8.1. Bộ hồ sơ tối thiểu của một phép thử

| Nhóm | Trường cần giữ |
| --- | --- |
| Định danh | Test ID, Control ID, người thực hiện, người xem xét |
| Phạm vi | Kỳ kiểm tra, môi trường, tài nguyên, principal, policy version |
| Tổng thể và mẫu | Nguồn, truy vấn, số lượng, cách chọn, danh sách phần tử mẫu |
| Thực thi | Điều kiện đầu vào, bước thực hiện, thời điểm, kết quả mong đợi |
| Kết quả | Quan sát thực tế, PASS/FAIL/chưa đủ bằng chứng, lý do |
| Bằng chứng | Nguồn, mã tham chiếu, thời điểm xuất, mã băm khi áp dụng |
| Xử lý | Phát hiện, owner, kế hoạch, ngày dự kiến và điều kiện kiểm thử lại |

Dùng mã tham chiếu thay vì chép toàn bộ log nhạy cảm vào báo cáo. Kho bằng chứng cần quyền truy cập phù hợp và chính sách lưu giữ đã được xác định.

### 8.2. Ảnh chụp và export bổ trợ cho nhau

Ảnh chụp thuận tiện để trình bày một trạng thái nhưng thường thiếu dữ liệu nền, bộ lọc và khả năng kiểm tra hàng loạt. Export có thể đối chiếu được nhưng vẫn cần nguồn, điều kiện truy vấn và kiểm tra tính toàn vẹn.

Không dùng thời điểm tạo tệp ảnh làm bằng chứng duy nhất cho thời điểm sự kiện. Khi dữ liệu đã được che hoặc chuẩn hóa, lưu cách biến đổi và liên kết tới bản gốc được bảo vệ để người có quyền có thể đối chiếu.

Nếu bằng chứng biến mất vì retention ngắn hơn kỳ kiểm tra, ghi nhận giới hạn và đánh giá yêu cầu lưu giữ. Không dựng lại log rồi trình bày như bằng chứng gốc.

## 9. Phân loại kết quả, ngoại lệ và phát hiện

Định nghĩa trạng thái trước khi thực hiện để tránh thay đổi cách chấm theo kết quả:

| Trạng thái | Khi sử dụng |
| --- | --- |
| PASS | Có đủ bằng chứng phù hợp cho thấy phần tử hoặc phép thử đáp ứng tiêu chí |
| FAIL | Có bằng chứng cho thấy một hoặc nhiều tiêu chí không được đáp ứng |
| INCONCLUSIVE | Chưa đủ bằng chứng tin cậy để quyết định |
| NOT_APPLICABLE | Có lý do phạm vi hợp lệ cho thấy tiêu chí không áp dụng |
| NOT_TESTED | Phép thử dự kiến chưa được thực hiện |

Các trạng thái này thuộc hồ sơ kiểm thử của bài học. Chúng không phải các giá trị thay thế cho field trạng thái tạo Knowledge trong YAML.

Một phép thử có thể có nhiều bước và một bước FAIL đã đủ làm thất bại tiêu chí liên quan. Không lấy trung bình các bước để biến một khả năng truy cập trái phép thành kết quả đạt.

### 9.1. Phân biệt miễn trừ và sai lệch

**Miễn trừ được phê duyệt** là quyết định phạm vi/rủi ro có trước, xác định rõ đối tượng, lý do, chủ sở hữu, thời hạn và kiểm soát bù. Người kiểm thử xác minh quyết định còn hiệu lực và kiểm soát bù thực sự hoạt động.

**Sai lệch kiểm soát** là điều kiện quan sát không đáp ứng tiêu chí đang áp dụng. Phê duyệt hồi tố sau khi phát hiện có thể là một quyết định xử lý rủi ro, nhưng không làm biến mất việc kiểm soát đã không vận hành đúng trong kỳ.

**Giới hạn bằng chứng** là tình huống chưa thể xác định kiểm soát có vận hành hay không. Nếu chính sách yêu cầu phải có log mà log thiếu, đồng thời có thể tồn tại một phát hiện riêng về lưu giữ bằng chứng.

### 9.2. Đánh giá mức độ dựa trên tác động

Xem xét mức đặc quyền, tài nguyên, thời gian phơi nhiễm, khả năng khai thác, số đối tượng ảnh hưởng, đường đi vòng và khả năng phát hiện. Một sai lệch duy nhất tại tài khoản quản trị hệ thống danh tính có thể nghiêm trọng hơn nhiều sai lệch về nhãn hiển thị.

Phân biệt lỗi thiết kế, cấu hình, tích hợp, vận hành thủ công và chất lượng bằng chứng. Ví dụ “revoke event được ghi nhưng nhóm tại đích không đổi” cần xác định connector, retry và kiểm tra xác nhận tại đích, thay vì chỉ yêu cầu người vận hành bấm thu hồi thêm một lần.

### 9.3. Báo cáo đúng tầng kết luận

Kết quả PASS của một mẫu không đồng nghĩa kiểm soát toàn kỳ có hiệu lực. Kết luận cấp kiểm soát phải tổng hợp thiết kế, triển khai, vận hành, độ đầy đủ bằng chứng và giới hạn phương pháp.

Kết luận cấp module PAM lại rộng hơn một kiểm soát. Việc kiểm thử JIT thành công không chứng minh kiểm kê tài khoản đầy đủ, credential được rotation hay bằng chứng phiên được bảo vệ.

## 10. Ví dụ xuyên suốt: kiểm thử PAM trong một kỳ

Giả sử nhóm đánh giá kiểm tra nhóm máy sản xuất P trong một tháng, theo chính sách nội bộ đã chốt. Các số liệu dưới đây chỉ minh họa cách lập luận.

### 10.1. Tổng thể đã đối chiếu

- Có 240 yêu cầu truy cập: 210 được cấp và 30 bị từ chối.
- Trong 210 lần cấp, có 200 lần thông thường và 10 lần break-glass.
- Trong tình huống minh họa này, mỗi lần cấp tạo đúng một phiên, nên có 210 phiên.
- Có 64 lần rotation đến hạn theo lịch áp dụng trong kỳ.

Nhóm đối chiếu danh sách yêu cầu với grant ledger, danh sách phiên với nguồn đích và lịch rotation với inventory tài khoản. Những con số bằng nhau ở đây không được mặc định cho hệ thống khác; một lần cấp thực tế có thể mở nhiều phiên hoặc không mở phiên nào.

### 10.2. Thiết kế phép thử

| Test ID | Phạm vi | Phương pháp | Kết quả minh họa |
| --- | --- | --- | --- |
| T-01 | 200 grant thông thường | Đối chiếu approval hợp lệ trước grant trên toàn bộ tổng thể | Không thấy sai lệch theo các trường đã kiểm tra |
| T-02 | 24 grant thông thường được chọn theo rủi ro | Kiểm tra hết hạn và khả năng sử dụng tại đích | 1 trường hợp vẫn dùng được sau cửa sổ thu hồi |
| T-03 | 10 lần break-glass | Kiểm tra toàn bộ theo tiêu chí khẩn cấp riêng | 1 lần thiếu hậu kiểm trong thời hạn nội bộ |
| T-04 | 210 phiên | Đối chiếu với kho bằng chứng và kiểm tra truy xuất theo thủ tục | 1 bản ghi ban đầu chưa có, cần xác minh thời điểm hoàn tất |
| T-05 | 6 trong 64 lần rotation, chọn theo rủi ro | Đối chiếu vault, đích và thử xác thực được cho phép | 1 trường hợp vault báo thành công nhưng đích chưa đồng bộ |

T-01 không có sai lệch chỉ hỗ trợ tiêu chí phê duyệt trong dữ liệu đã kiểm tra. T-02 cho thấy một điểm thất bại khác, nên không thể dùng T-01 để tuyên bố kiểm soát JIT tổng thể đạt.

### 10.3. Điều tra trước khi kết luận

Với T-02, nhóm thấy tác vụ revoke lỗi trên một connector. Quyền vẫn có hiệu lực ở đích và cảnh báo không được xử lý trong thời gian yêu cầu. Đây là bằng chứng sai lệch vận hành; tiếp tục xác định các grant cùng connector và giai đoạn ảnh hưởng.

Với T-03, đường khẩn cấp được sử dụng hợp lệ, nhưng hậu kiểm quá hạn. Không mô tả thành “truy cập chưa được phê duyệt” nếu chính sách khẩn cấp cho phép truy cập trước và hậu kiểm sau. Phát hiện phải bám đúng tiêu chí đã vi phạm.

Với T-04, bản ghi đang hoàn tất sau khi phiên vừa đóng. Nhóm chờ đến hết độ trễ cho phép theo thiết kế, trích xuất lại và kiểm tra truy xuất. Nếu bản ghi xuất hiện đầy đủ trong thời hạn thì không coi độ trễ ban đầu là sai lệch. Vẫn giữ bằng chứng và cách giải quyết khác biệt giữa hai lần lấy dữ liệu.

Với T-05, phải xác định credential nào có hiệu lực thực tế, ứng dụng nào bị ảnh hưởng và cửa sổ chồng lấn có được phép hay không. Không chạy lại rotation rồi xóa dấu vết lần thất bại để thay bằng kết quả thành công mới.

### 10.4. Cách viết kết luận có giới hạn

Một kết luận phù hợp có thể là:

> Trong phạm vi máy sản xuất P và kỳ đã xác định, đối chiếu 200 lần cấp quyền thông thường không phát hiện thiếu phê duyệt theo các trường dữ liệu được kiểm tra. Kiểm tra thu hồi trên 24 mẫu có chủ đích phát hiện một trường hợp quyền vẫn sử dụng được sau cửa sổ cho phép. Kết quả này chứng minh có sai lệch ở phần tử đã kiểm tra, chưa phải ước lượng tỷ lệ sai lệch của toàn bộ tổng thể. Phạm vi ảnh hưởng của connector đang được mở rộng kiểm tra.

Sau đó trình bày riêng phát hiện break-glass và rotation, cùng ảnh hưởng, owner và bước xử lý. Không gộp mọi quan sát thành một tỷ lệ “compliance” duy nhất làm che khuất rủi ro.

## 11. Mẫu hồ sơ một phép thử

Mẫu YAML dưới đây là nội dung minh họa cho hồ sơ kiểm thử, không phải chỉ thị tạo thêm file hoặc thay schema metadata bài học:

```yaml
test:
  id: PAM-TEST-JIT-EXPIRY-01
  controlId: PAM-JIT-01
  objective: Quyền không còn sử dụng được sau hạn theo chính sách nội bộ
  criteriaVersion: policy-revision-7
  period:
    start: "2026-10-01T00:00:00+07:00"
    endExclusive: "2026-11-01T00:00:00+07:00"
  scope:
    environment: production
    resourceSet: prod-group-p
    accessPath: managed-administration
    principalType: human-admin
  population:
    unit: grant
    count: 200
    extractionRef: E-POP-01
    completenessCheckRef: E-REC-01
  selection:
    method: risk-based-nonstatistical
    sampleCount: 24
    criteria:
      - critical-resource
      - connector-change-window
      - out-of-hours
  execution:
    procedureRef: PROC-JIT-EXPIRY-03
    targetConfirmationRequired: true
    expected: Quyền hết hiệu lực trong cửa sổ thu hồi được phê duyệt
  result:
    status: FAIL
    tested: 24
    passed: 23
    failed: 1
    inconclusive: 0
    evidenceRefs:
      - E-GRANT-024
      - E-TARGET-024
      - E-REVOKE-024
    findingRef: F-PAM-007
    limitation: Không suy rộng tỷ lệ từ mẫu có chủ đích
```

Không đặt secret, credential cũ/mới hoặc token trong hồ sơ. Nếu cần xác định một phiên bản credential, dùng mã phiên bản hoặc tham chiếu không tiết lộ giá trị.

Một phát hiện tương ứng cần nêu ít nhất:

- **Tiêu chí:** quyền không còn dùng được sau cửa sổ thu hồi đã phê duyệt.
- **Điều kiện thực tế:** quyền tại tài nguyên đích vẫn hoạt động sau thời điểm đó.
- **Bằng chứng:** định danh grant, mốc thời gian, trạng thái đích, kết quả thao tác kiểm thử và log connector.
- **Nguyên nhân:** phần đã xác minh và phần còn điều tra, không gán suy đoán thành kết luận.
- **Ảnh hưởng:** tài nguyên/quyền liên quan, thời gian phơi nhiễm và phạm vi chưa xác định.
- **Hành động:** xử lý tức thời, khắc phục nguyên nhân, mở rộng kiểm tra và kiểm thử lại.
- **Trách nhiệm:** owner, người xem xét, hạn xử lý và thẩm quyền chấp nhận rủi ro.

## 12. Khắc phục và kiểm thử lại

Khắc phục tức thời có thể là thu hồi quyền còn treo hoặc cô lập một đường truy cập theo quy trình ứng phó. Khắc phục nguyên nhân có thể là sửa connector, thêm xác nhận trạng thái tại đích, điều chỉnh retry hoặc cải thiện cảnh báo.

Hai loại hành động cần được theo dõi riêng. Việc một quản trị viên tự thu hồi quyền sau phát hiện giải quyết phần tử hiện tại nhưng chưa chứng minh cơ chế tự động đã được sửa.

Một kế hoạch kiểm thử lại nên bao gồm:

1. Xác nhận thay đổi đã được triển khai đúng môi trường và phiên bản.
2. Tái thực hiện kịch bản từng thất bại với điều kiện tương đương.
3. Kiểm tra các điều kiện biên liên quan, như timeout hoặc mất kết nối trong lúc thu hồi.
4. Kiểm tra cảnh báo và xử lý khi đường chính thất bại.
5. Thu thập bằng chứng vận hành bổ sung nếu kết luận yêu cầu tính ổn định trong một khoảng thời gian.
6. Đánh giá phần tồn tại từ trước thay đổi, không chỉ các giao dịch mới.
7. Ghi người xác minh và quyết định đóng, chấp nhận rủi ro hoặc tiếp tục theo dõi.

Không sửa kết quả FAIL lịch sử thành PASS. Giữ kết quả ban đầu, trạng thái khắc phục và kết quả kiểm thử lại như các mốc riêng. Điều này cho phép người xem hiểu thời gian kiểm soát chưa có hiệu lực và thời điểm đã được xác nhận khôi phục.

Nếu thay đổi thiết kế khiến tiêu chí cũ không còn phù hợp, phải có quyết định thay đổi và tiêu chí mới rõ ràng. Đó không phải lý do để xóa sai lệch xảy ra trước khi thay đổi có hiệu lực.

## 13. Những lỗi khiến kết quả kiểm thử không đáng tin

| Lỗi thường gặp | Vì sao kết luận yếu | Cách xử lý |
| --- | --- | --- |
| Chỉ chụp cấu hình PAM | Không chứng minh triển khai hoặc vận hành tại đích | Kết hợp cấu hình, giao dịch trong kỳ và xác nhận ở đích |
| Chỉ chọn tác vụ thành công | Loại mất chính các tình huống rủi ro | Xây tổng thể từ nghĩa vụ phải thực hiện, giữ lỗi và trường hợp chưa chạy |
| Lấy mẫu từ bản ghi phiên để kiểm tra đủ bản ghi | Tập bị thiếu không bao giờ xuất hiện trong mẫu | Dùng nguồn phiên độc lập để đối chiếu |
| Dùng cùng username để nối mọi sự kiện | Có thể ghép nhầm lần duyệt, grant và phiên | Ưu tiên ID và kiểm tra quan hệ một-nhiều |
| Chỉ thử trong thời hạn quyền | Không chứng minh thu hồi | Kiểm tra sau hạn, tại đích và với phiên đang tồn tại khi cần |
| Coi API trả success là kết quả cuối | Bộ điều phối có thể chưa thực thi xong hoặc đích lỗi | Xác nhận trạng thái thực tế và độ trễ hợp lệ |
| Gộp thiếu log vào PASS | Không có bằng chứng cho tiêu chí | Ghi INCONCLUSIVE hoặc phát hiện thiếu bằng chứng theo yêu cầu |
| Loại mọi tài khoản có nhãn exception | Nhãn không chứng minh miễn trừ hợp lệ | Kiểm tra phê duyệt, phạm vi, thời hạn và kiểm soát bù |
| Thay mẫu lỗi bằng mẫu khác | Che giấu sai lệch và làm sai phương pháp chọn | Giữ phần tử lỗi và giải thích mọi thay đổi mẫu |
| Suy rộng từ mẫu có chủ đích | Mẫu không được thiết kế để ước lượng toàn bộ | Giới hạn kết luận và dùng phương pháp phù hợp nếu cần suy rộng |
| Chạy lại rồi chỉ giữ kết quả đẹp | Xóa dấu vết thất bại và thời gian phơi nhiễm | Giữ lịch sử, phân biệt lần đầu và lần kiểm thử lại |

## 14. Bài thực hành

### Bài 1: Chuyển chính sách thành thủ tục

Cho yêu cầu nội bộ: “Mọi quyền quản trị thông thường trên nhóm máy Q phải có phê duyệt độc lập và tự hết hạn”.

Hãy xác định đơn vị tổng thể, người duyệt hợp lệ, thời hạn, điểm thực thi, đường có thể đi vòng và cách kiểm tra phiên đang mở. Viết các bước kiểm thử cả trường hợp được phép lẫn bị từ chối. Nêu phần còn thiếu trong yêu cầu trước khi có thể đặt tiêu chí PASS/FAIL.

**Gợi ý tự đối chiếu:** nếu chưa biết “hết hạn” có áp dụng cho phiên đã mở hay chỉ cho phiên mới, không thể kết luận đúng theo cùng một tiêu chí.

### Bài 2: Phát hiện tổng thể bị thiếu

Vault báo 500 lần rotation thành công và 3 lần thất bại. Inventory cùng lịch có hiệu lực cho thấy có 520 lần đến hạn. Có 7 lần được miễn trừ hợp lệ trước kỳ và không thuộc nghĩa vụ phải chạy trong kỳ.

Hãy tính số lần cần có bằng chứng thực thi, xác định phần chưa được giải thích và đề xuất nguồn để đối chiếu. Không giả định các lần còn lại đều thất bại hoặc đều được hoãn hợp lệ.

**Hướng xử lý:** nếu các con số cùng đơn vị và không có lần thử lại bị đếm trùng, nghĩa vụ còn 513 lần, đã có 503 kết quả thực thi và còn 10 lần cần làm rõ. Trước khi kết luận, vẫn phải kiểm tra các giả định về đơn vị, lịch, retry và phạm vi miễn trừ.

### Bài 3: Đánh giá bằng chứng chưa đủ

Một mẫu JIT có revoke event đúng hạn. Khi người kiểm thử thử lại, kết nối bị timeout vì đường mạng tới đích lỗi.

Hãy chọn kết quả phù hợp cho tiêu chí “quyền không còn dùng được ở đích”, giải thích bằng chứng thiếu và nêu cách hoàn tất phép thử.

**Hướng xử lý:** revoke event hỗ trợ việc bộ điều phối đã phát lệnh, còn timeout không chứng minh quyền đã mất. Cần xác nhận trạng thái quyền tại đích hoặc thử lại khi đường kết nối hợp lệ, theo thủ tục và thời điểm được phép.

### Bài 4: Viết phát hiện và điều kiện đóng

Trong 15 mẫu được chọn theo rủi ro, một tài khoản dịch vụ vẫn xác thực được bằng credential cũ sau thời gian chuyển tiếp cho phép.

Viết phát hiện gồm tiêu chí, điều kiện, bằng chứng, ảnh hưởng và giới hạn. Đề xuất xử lý tức thời cùng điều kiện kiểm thử lại. Không ước lượng tỷ lệ lỗi toàn bộ tài khoản dịch vụ từ 15 mẫu này.

## 15. Các điểm cần ghi nhớ

Control testing có giá trị khi nối được rủi ro, tiêu chí, tổng thể, phép thử và bằng chứng. Với PAM, đường nối này phải tới tài nguyên đích và khả năng sử dụng đặc quyền thực tế.

Một kế hoạch tốt kiểm tra cả hành động hợp lệ và hành động phải bị chặn, cả vận hành thông thường lẫn lỗi và đường khẩn cấp. Một bộ bằng chứng tốt giải thích được độ đầy đủ dữ liệu, cách chọn mẫu, thời gian và quan hệ giữa request, approval, grant, session và revoke.

Kết luận phải tương xứng với phạm vi đã kiểm tra. Giữ rõ ranh giới giữa thiết kế, triển khai, vận hành; giữa sai lệch, miễn trừ và thiếu bằng chứng; giữa khắc phục tức thời và kiểm thử lại nguyên nhân. Nhờ đó, kết quả kiểm thử hỗ trợ cải thiện kiểm soát đặc quyền và cung cấp bằng chứng có thể xem xét trong hoạt động kiểm toán.
