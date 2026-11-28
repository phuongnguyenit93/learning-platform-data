# Tenant offboarding

## 1. Tenant offboarding là gì?

**Tenant offboarding** là quy trình chấm dứt việc một tổ chức hoặc không gian khách hàng sử dụng hệ thống, đồng thời xử lý có kiểm soát các danh tính, quyền truy cập, credential, tích hợp và dữ liệu thuộc tenant đó.

Ví dụ, Công ty An ngừng sử dụng một nền tảng quản lý tài liệu. Hệ thống cần ngăn nhân viên và ứng dụng của Công ty An tiếp tục truy cập, xử lý những tác vụ đang chạy, bàn giao dữ liệu theo phương án đã thống nhất, rồi lưu giữ hoặc xóa dữ liệu theo chính sách áp dụng. Việc chỉ đổi tên tenant thành “đã đóng” không thực hiện được những công việc này.

Tenant offboarding khác với việc một người rời một tenant:

| Tình huống | Phạm vi thay đổi |
|---|---|
| Một nhân viên rời Công ty An | Thu hồi membership và quyền liên quan của nhân viên trong tenant An |
| Công ty An ngừng dùng nền tảng | Chấm dứt hoạt động của cả tenant An, gồm người dùng, workload, tích hợp và dữ liệu |
| Tài khoản cá nhân bị chiếm đoạt | Có thể cần khóa danh tính toàn cục, ảnh hưởng mọi tenant theo quyết định xử lý sự cố |

Một tài khoản có thể thuộc cả Công ty An và Công ty Bình. Đóng tenant An không mặc nhiên cho phép xóa tài khoản toàn cục hoặc thu hồi các quyền hợp lệ của người đó trong tenant Bình.

Mục tiêu của offboarding là tạo ra một trạng thái kết thúc có thể chứng minh: quyền đã bị chặn đúng phạm vi, dữ liệu đã được xử lý theo kế hoạch, các phần còn chờ được ghi nhận rõ và tenant không bị tái kích hoạt ngoài ý muốn.

## 2. Xác định ranh giới trước khi offboarding

Đối tượng cần đóng phải được xác định bằng tenant ID ổn định, không chỉ bằng tên hiển thị, tên miền email hoặc tên khách hàng trên một yêu cầu hỗ trợ.

Trước khi thực hiện, cần xác định:

- Ai có thẩm quyền yêu cầu chấm dứt tenant và ai phê duyệt các bước nhạy cảm.
- Thời điểm ngừng truy cập thông thường.
- Người hoặc quy trình được nhận dữ liệu bàn giao.
- Những loại dữ liệu cần xuất, giữ lại, xóa hoặc chuyển quyền sở hữu.
- Các credential, workload và tích hợp thuộc riêng tenant.
- Các tài nguyên dùng chung với tenant khác hoặc với nền tảng.
- Những điều kiện có thể cho phép hủy yêu cầu trước điểm không thể hoàn tác.

Một yêu cầu offboarding nên có mã riêng, ví dụ `offboarding_request_id`, gắn với tenant ID, phiên bản kế hoạch, người phê duyệt và các mốc thời gian. Mã này giúp theo dõi cùng một quy trình qua nhiều dịch vụ và nhiều lần retry.

Không lấy tenant ID trong biểu mẫu làm bằng chứng quyền thực hiện. Máy chủ phải xác thực actor, kiểm tra quyền yêu cầu hoặc phê duyệt offboarding đối với chính tenant đó và áp dụng quy tắc xác nhận bổ sung nếu thao tác có tác động lớn.

## 3. Dùng trạng thái có ý nghĩa thực thi

Offboarding thường kéo dài qua nhiều bước. Một cờ `deleted = true` không diễn tả đủ những gì đã làm và những gì còn tồn tại.

Một mô hình minh họa:

| Trạng thái tenant | Ý nghĩa | Truy cập nghiệp vụ thông thường |
|---|---|---|
| ACTIVE | Tenant hoạt động bình thường | Được đánh giá theo membership và chính sách |
| OFFBOARDING | Đã khóa luồng hoạt động thông thường, đang xử lý bàn giao và thu hồi | Bị chặn |
| RETAINED | Dữ liệu cần giữ còn tồn tại trong phạm vi lưu giữ được phê duyệt | Bị chặn |
| PURGING | Đang xóa các bản dữ liệu thuộc phạm vi kế hoạch | Bị chặn |
| CLOSED | Các điều kiện kết thúc đã được xác nhận | Bị chặn |

Đây là mô hình thiết kế, không phải tập trạng thái bắt buộc cho mọi sản phẩm. Nếu cần giai đoạn chuẩn bị khi tenant vẫn hoạt động, có thể ghi yêu cầu ở trạng thái chờ phê duyệt trong hồ sơ quy trình, thay vì làm `OFFBOARDING` có hai ý nghĩa truy cập trái ngược nhau.

Sau thời điểm khóa, quyền xuất dữ liệu hoặc thực hiện cleanup phải đi qua một luồng quản trị chuyên biệt. Không cho phép mọi ADMIN tiếp tục dùng API thông thường bằng ngoại lệ “đang offboarding”.

Một điều kiện truy cập cần xét cả trạng thái tenant:

```text
allow_business_request =
    subject được xác thực và còn được phép hoạt động
    AND tenant.status == ACTIVE
    AND membership hoặc workload grant còn hiệu lực
    AND chính sách cho phép hành động
    AND tài nguyên thuộc đúng tenant
```

Như vậy, ngay cả khi một membership hoặc role chưa kịp được cập nhật trong tác vụ nền, trạng thái tenant vẫn là một lớp chặn chung. Lớp chặn này chỉ có tác dụng khi các đường truy cập liên quan thực sự kiểm tra trạng thái, với cơ chế xử lý cache và lỗi đã xác định.

## 4. Quy trình offboarding theo các mốc rõ ràng

Có thể tổ chức quy trình theo thứ tự sau:

```text
Xác minh yêu cầu và kế hoạch
        |
        v
Khóa truy cập thông thường, ngăn cấp quyền mới
        |
        v
Thu hồi phiên, credential và xử lý công việc đang chạy
        |
        v
Xuất dữ liệu bằng luồng được cấp quyền riêng
        |
        v
Lưu giữ có kiểm soát hoặc xóa theo kế hoạch
        |
        v
Đối soát kết quả và xác nhận trạng thái kết thúc
```

Nếu sản phẩm hỗ trợ khách hàng tự xuất dữ liệu trước khi ngừng hoạt động, bước xuất có thể diễn ra trước mốc khóa. Kế hoạch phải nói rõ thời điểm dữ liệu được chụp và liệu còn thay đổi dữ liệu sau lần xuất đó hay không. Không coi một bản xuất cũ là ảnh chụp cuối cùng nếu tenant vẫn tiếp tục ghi dữ liệu.

### 4.1. Chuẩn bị

Lập danh mục những tài nguyên và đường truy cập cần xử lý. Chọn người phụ trách từng nhóm và bằng chứng xác nhận hoàn tất. Xác định thời gian lưu giữ từ chính sách đã được tổ chức phê duyệt; không tự đặt một con số mặc định cho mọi khách hàng.

### 4.2. Khóa tại mốc T0

T0 là thời điểm máy chủ chuyển tenant sang trạng thái chặn hoạt động thông thường. Cùng với đó, hệ thống phải ngăn các luồng có thể tạo lại quyền, chẳng hạn:

- Chấp nhận lời mời đang chờ.
- Tạo membership mới hoặc khôi phục membership cũ.
- Cấp role, credential hoặc ủy quyền mới cho tenant.
- Tự cấp membership khi đăng nhập qua SSO.
- Đồng bộ provisioning làm tenant hoạt động trở lại.

Các thao tác này cần kiểm tra trạng thái ở phía máy chủ. Ẩn nút trên giao diện không ngăn được request API, đồng bộ nền hoặc retry đã được lên lịch.

### 4.3. Xử lý phần còn tồn tại

Sau T0, tiến hành thu hồi, bàn giao và lưu giữ/xóa theo các bước có thể kiểm chứng. Có thể thực hiện song song những phần độc lập, nhưng các điều kiện phụ thuộc vẫn phải được giữ: ví dụ, không xóa nguồn dữ liệu cần bàn giao trước khi bản xuất đã được xác nhận đủ theo kế hoạch.

### 4.4. Đối soát

Thu thập kết quả từ từng nhóm tài nguyên. Bước gửi yêu cầu xóa thành công không đồng nghĩa với dữ liệu đã biến mất ở mọi nơi. Chỉ kết thúc khi đáp ứng các điều kiện đã định nghĩa, đồng thời mô tả rõ ngoại lệ hoặc phần dữ liệu còn được giữ.

## 5. Thu hồi quyền của người dùng và workload

### 5.1. Membership, role và phiên người dùng

Các membership của tenant cần bị vô hiệu hóa theo mô hình đã chọn. Role assignment, quyền ủy quyền và lời mời chờ cũng phải được xử lý để không còn đường cấp lại quyền.

Phiên chung của người dùng có thể phục vụ nhiều tenant. Hệ thống cần thu hồi quyền sử dụng tenant đang đóng mà vẫn bảo toàn các quan hệ ngoài phạm vi. Nếu phải khóa tài khoản toàn cục do một nguyên nhân khác, đó là một quyết định riêng cần được ghi nhận.

Access token có thể còn hợp lệ về mặt chữ ký sau T0. Vì vậy, chỉ vô hiệu hóa refresh token chưa đủ để ngăn token hiện có gọi API. Có thể cần kết hợp:

- Kiểm tra tenant còn ACTIVE ở điểm ra quyết định.
- Đối chiếu phiên bản quyền hoặc cơ chế thu hồi.
- Vô hiệu hóa cache có liên quan.
- Giới hạn thời gian hiệu lực của thông tin quyền được lưu cục bộ.

Thiết kế cần định nghĩa độ trễ thu hồi chấp nhận được. Nếu một API chỉ xác minh chữ ký của token cũ và bỏ qua trạng thái hiện tại, tenant vẫn có thể được truy cập cho tới khi token hết hạn.

### 5.2. Workload và credential

Danh tính workload không nhất thiết đi theo membership của người đã tạo nó. Cần kiểm kê riêng:

| Thành phần | Việc cần xem xét |
|---|---|
| Service account thuộc tenant | Vô hiệu hóa grant, role và credential |
| API key của tenant | Thu hồi tại nơi kiểm tra key và làm mất hiệu lực cache |
| Refresh token hoặc OAuth grant cho tích hợp | Thu hồi theo cơ chế của hệ thống phát hành |
| Credential gọi nhà cung cấp bên ngoài | Thu hồi hoặc xoay theo phạm vi sở hữu |
| Tài khoản nền tảng dùng chung | Gỡ khả năng thao tác với tenant đích; bảo toàn tenant khác |
| Ủy quyền tạm thời cho hỗ trợ | Hết hiệu lực khi đóng tenant hoặc khi kết thúc nhiệm vụ đã phê duyệt |

Không xóa một client, key ký token hoặc kết nối danh tính dùng chung chỉ vì một tenant ngừng hoạt động. Với một thành phần dùng chung, cần thu hồi mapping hoặc quyền của tenant đích. Nếu không thể tách quyền theo tenant, phải đánh giá và thiết kế phương án thay thế có kiểm soát trước khi thực hiện thao tác ảnh hưởng nhiều tenant.

## 6. Xử lý SSO, provisioning và các tích hợp

Một kết nối SSO đang tồn tại có thể tiếp tục xác thực người dùng ở nhà cung cấp danh tính. Điều cần bảo đảm là kết quả đăng nhập đó không tạo ra quyền sử dụng tenant đã đóng.

Cần phân biệt:

- Xác thực ở nhà cung cấp danh tính bên ngoài.
- Liên kết kết quả xác thực với subject nội bộ.
- Cấp membership hoặc role trong tenant.
- Cho phép truy cập dữ liệu tenant.

Đóng tenant không mặc nhiên đồng nghĩa xóa người dùng tại nhà cung cấp danh tính của khách hàng. Hệ thống chỉ thực hiện thao tác bên ngoài khi có thẩm quyền và phạm vi được xác định.

Với provisioning, cần ngăn đồng bộ định kỳ hoặc request đến muộn tạo lại membership. Bản ghi trạng thái tenant đã đóng phải được kiểm tra ngay cả khi nguồn gửi dữ liệu vẫn đang hoạt động.

Các webhook và kết nối đồng bộ dữ liệu cũng cần được xử lý. Dừng phát sự kiện mới không tự hủy những sự kiện đã nằm trong hàng đợi retry. Khi xử lý lại, worker cần nhận biết trạng thái tenant và bỏ hoặc xử lý chúng theo chính sách offboarding, thay vì tiếp tục gửi dữ liệu ra ngoài.

Nếu credential tích hợp cũng được dùng để xuất dữ liệu cuối kỳ, phải xác định thời điểm thu hồi tương ứng. Có thể thay bằng một credential chuyên biệt, ít quyền và có thời hạn cho quy trình bàn giao; không giữ vô thời hạn credential nghiệp vụ cũ để “phòng khi cần”.

## 7. Công việc đang chạy và đường truy cập ít thấy

Offboarding phải bao phủ cả hoạt động không xuất phát từ request HTTP mới.

### 7.1. Tác vụ nền và hàng đợi

Một job đã được tạo khi tenant ACTIVE có thể chỉ bắt đầu chạy sau T0. Tenant ID trong payload không phải quyền thực thi bền vững. Worker cần xác minh tenant và quyền tương ứng trước khi thực hiện tác động.

Với job đang chạy, cần có chính sách rõ:

- Dừng hoặc hủy ở điểm an toàn.
- Cho phép hoàn tất một phần được xác định nếu không tạo quyền truy cập trái phép.
- Ghi lại kết quả và xử lý phần việc chưa hoàn tất.
- Ngăn retry làm hoạt động trở lại sau khi đã bị hủy.

Không phải mọi job liên quan tenant đều bị chặn giống nhau. Job nghiệp vụ thông thường cần dừng, còn job offboarding vẫn phải có khả năng thu hồi hoặc xóa. Danh tính cleanup cần có quyền riêng, gắn với tenant và request offboarding, thay vì một cờ bỏ qua kiểm tra tenant cho mọi worker.

### 7.2. Kết nối dài và quyền truy cập gián tiếp

WebSocket, stream tải dữ liệu và kết nối dài đã được thiết lập có thể tiếp tục tồn tại sau T0. Hệ thống cần có cơ chế đóng kết nối hoặc kiểm tra lại quyền ở các điểm phù hợp.

Các bản dữ liệu ở cache, chỉ mục tìm kiếm, kho phân tích và tệp đã xuất cần nằm trong danh mục xử lý. Xóa hàng trong cơ sở dữ liệu chính không tự xóa bản sao ở các thành phần này.

Một liên kết tải trực tiếp đã phát hành có thể còn dùng được tới hạn hết hiệu lực, tùy cơ chế lưu trữ. Thu hồi API key không tự bảo đảm liên kết đó ngừng hoạt động. Nếu cần chặn ngay, kiến trúc phải có cơ chế có thể thực thi yêu cầu này, chẳng hạn kiểm tra quyền qua cổng tải xuống hoặc cơ chế thu hồi được nơi lưu trữ hỗ trợ.

## 8. Xuất và bàn giao dữ liệu

Bản xuất cần được tạo từ đúng tenant, đúng phạm vi dữ liệu và đúng mốc thời gian đã thống nhất.

Những điểm cần xác định gồm:

- Loại dữ liệu được bàn giao và cấu trúc đầu ra.
- Những dữ liệu có thể thuộc bên khác hoặc ngoài phạm vi được nhận.
- Người được nhận, cách xác minh và quyền tải.
- Kênh lưu trữ, mã hóa và thời hạn truy cập bản xuất.
- Thời điểm bản xuất bị xóa và bằng chứng kết quả.

Không đưa password hash, secret hệ thống, token tích hợp hoặc credential nền tảng vào bản xuất chỉ vì chúng nằm gần dữ liệu tenant. Phạm vi bàn giao phải phân biệt dữ liệu khách hàng với vật liệu xác thực và dữ liệu vận hành không được phép tiết lộ.

Một quy trình bàn giao có thể ghi manifest gồm danh sách tệp, số lượng bản ghi hoặc kích thước và giá trị băm. Giá trị băm giúp kiểm tra tính toàn vẹn khi tải, nhưng không tự chứng minh bản xuất đủ về nghiệp vụ; cần đối chiếu với phạm vi đã thống nhất.

Quyền tải bản xuất là một quyền còn tồn tại trong giai đoạn offboarding. Nó cần được cấp riêng, có giới hạn và được thu hồi sau khi hết mục đích. Không công khai một bucket hoặc gửi URL không có thời hạn để đơn giản hóa bàn giao.

Nếu dữ liệu còn thay đổi trong quá trình xuất, cần chọn cơ chế nhất quán phù hợp, ví dụ chụp ảnh dữ liệu hoặc đặt mốc cắt ghi. Nếu không, các tệp có thể phản ánh những thời điểm khác nhau và thiếu quan hệ giữa các bản ghi.

## 9. Lưu giữ và xóa dữ liệu

### 9.1. Phân loại kết quả theo từng nơi lưu

Không phải mọi loại dữ liệu đều có cùng thời điểm xử lý.

| Nhóm dữ liệu | Hướng xử lý minh họa |
|---|---|
| Dữ liệu nghiệp vụ đang phục vụ ứng dụng | Ngừng phục vụ, sau đó lưu giữ hoặc xóa theo kế hoạch |
| Bản xuất bàn giao | Hạn chế người nhận, hết hạn và xóa sau thời gian đã quy định |
| Credential | Thu hồi và loại bỏ vật liệu bí mật khi không còn cần thiết |
| Audit | Giữ các trường cần thiết theo chính sách, hạn chế truy cập |
| Cache và chỉ mục tìm kiếm | Vô hiệu hóa, xóa hoặc xây dựng lại để không phục vụ dữ liệu tenant |
| Backup và snapshot | Theo lịch lưu giữ hoặc cơ chế xóa đã được thiết kế |
| Dữ liệu tại nhà cung cấp tích hợp | Gửi yêu cầu và đối soát kết quả trong phạm vi có quyền xử lý |

Chính sách lưu giữ có thể có ngoại lệ đã được phê duyệt, chẳng hạn dữ liệu thuộc một yêu cầu giữ lại đang có hiệu lực. Hệ thống cần ghi nhận phạm vi và người có thẩm quyền xử lý ngoại lệ; không tự đưa ra kết luận pháp lý từ trạng thái offboarding.

### 9.2. Cách ly dữ liệu được giữ lại

Giữ dữ liệu không có nghĩa tiếp tục cho tenant sử dụng dữ liệu. Dữ liệu ở trạng thái RETAINED cần được tách khỏi luồng ứng dụng thông thường, có nhóm truy cập được phê duyệt và có thời điểm hoặc điều kiện đánh giá lại.

Trạng thái tenant cần tiếp tục chặn truy cập ngay cả khi dữ liệu vẫn còn vật lý trong bảng dùng chung. Một bộ lọc chỉ dùng ở giao diện hoặc một convention đặt tên thư mục không tạo ra cách ly truy cập đáng tin cậy.

### 9.3. Bảo toàn ranh giới tenant khi xóa

Một tác vụ xóa phải nhận đúng tenant ID từ hồ sơ đã xác minh. Trong cơ sở dữ liệu hoặc object storage dùng chung, điều kiện xóa phải phản ánh ranh giới tenant và quan hệ sở hữu thực tế.

Không xóa dữ liệu theo email của nhân viên, tên tổ chức hoặc đường dẫn do người gọi tự ghép. Một subject có thể được tenant khác tham chiếu; một đối tượng dùng chung có thể không thuộc riêng tenant đang đóng.

Trước khi xóa dữ liệu dùng chung, cần có quy tắc sở hữu và tham chiếu rõ ràng. Thao tác xóa tenant An không được làm hỏng tài khoản, tài liệu hoặc tích hợp hợp lệ của tenant Bình.

### 9.4. Backup và khôi phục

Xóa khỏi dữ liệu đang phục vụ chưa đồng nghĩa xóa khỏi backup. Nếu backup chỉ hết hạn theo vòng đời, báo cáo cần nêu rõ khoảng tồn tại còn lại và giới hạn truy cập, thay vì tuyên bố đã xóa toàn bộ.

Việc hủy khóa mã hóa chỉ có thể dùng như một phần phương án xóa khi có khả năng chứng minh khóa đó được tách đúng phạm vi, các bản sao khóa được quản lý và dữ liệu không còn được giải mã bằng đường khác. Không hủy khóa dùng chung với tenant còn hoạt động.

Cần ngăn việc khôi phục backup cũ làm tenant sống lại. Một cách là duy trì bản ghi tối thiểu về tenant đã đóng ở nguồn kiểm soát phù hợp, rồi áp dụng lại trạng thái chặn và các quyết định xử lý trước khi hệ thống khôi phục được mở cho truy cập. Bản ghi này thường được gọi là tombstone; nó phục vụ điều phối vòng đời, không phải bản sao đầy đủ dữ liệu khách hàng.

## 10. Điều phối offboarding trong hệ thống phân tán

Một giao dịch cơ sở dữ liệu đơn lẻ thường không thể đồng thời thu hồi token, xóa object storage, dừng hàng đợi và cập nhật mọi hệ thống bên ngoài. Vì vậy, quy trình cần lưu tiến độ bền vững và xử lý được từng bước thất bại.

Mỗi bước có thể lưu:

```text
offboarding_request_id
tenant_id
step_name
state: PENDING | RUNNING | SUCCEEDED | FAILED | WAITING
attempt
started_at
finished_at
result_reference
failure_reason
```

Các thuộc tính quan trọng:

**Idempotency.** Chạy lại bước thu hồi cùng một key hoặc xóa cùng một đối tượng không được tạo quyền mới, xóa lan sang phạm vi khác hay làm sai kết quả đã xác nhận.

**Retry có giới hạn và phân loại lỗi.** Lỗi tạm thời có thể thử lại. Lỗi sai tenant, thiếu thẩm quyền hoặc chưa đủ điều kiện lưu giữ cần được xử lý theo nguyên nhân, không retry mù.

**Ràng buộc cạnh tranh.** Một lần cập nhật quyền đang diễn ra đồng thời với offboarding không được làm tenant có quyền mới sau T0. Cần kiểm tra trạng thái trong giao dịch hoặc cơ chế nhất quán tương đương. Chỉ kiểm tra ACTIVE trước khi bắt đầu một chuỗi thao tác dài là chưa đủ.

**Bằng chứng hoàn thành.** Sự kiện gửi đi hoặc HTTP thành công có thể mới chỉ là xác nhận nhận yêu cầu. Bước phải được ghi thành công theo hợp đồng của thành phần đích và có readback hoặc bằng chứng kết quả phù hợp.

**Khả năng tiếp tục sau restart.** Worker hoặc dịch vụ điều phối khởi động lại phải đọc hồ sơ hiện tại để tiếp tục. Không tự tạo một kế hoạch mới hoặc mở tenant lại vì bộ nhớ tiến độ đã mất.

Khi một bước xóa dữ liệu đã thành công, “rollback” không nhất thiết có nghĩa khôi phục được dữ liệu. Hủy offboarding trước mốc phá hủy và phục hồi sau khi đã xóa là hai quy trình khác nhau. Quyền truy cập không được tự động khôi phục chỉ vì một bước cleanup tiếp theo bị lỗi.

## 11. Ví dụ: đóng tenant An, giữ tenant Bình hoạt động

Giả sử Lan có một tài khoản chung:

```text
Lan -> tenant-an   : ADMIN
Lan -> tenant-binh : VIEWER

report-bot-an -> tenant-an : quyền đọc báo cáo
shared-worker -> nhiều tenant : thực thi job theo tenant scope
```

Sau khi phê duyệt đóng tenant An:

1. Hệ thống chuyển tenant An sang OFFBOARDING tại T0.
2. Mọi request nghiệp vụ vào tenant An bị chặn, kể cả request mang access token còn hạn của Lan.
3. Membership và grant của tenant An được vô hiệu hóa; API key của report-bot-an bị thu hồi.
4. JIT và provisioning không được tạo lại quyền trong tenant An.
5. Job báo cáo đang chờ của tenant An bị hủy theo chính sách; shared-worker vẫn phục vụ tenant Bình.
6. Một danh tính phục vụ bàn giao, có phạm vi riêng và thời hạn, xuất dữ liệu đã được phê duyệt.
7. Dữ liệu được giữ hoặc xóa theo từng nhóm; bản xuất và backup được theo dõi riêng.
8. Hồ sơ chỉ chuyển sang CLOSED khi các điều kiện kết thúc áp dụng đã đạt.

Lan vẫn được đánh giá quyền VIEWER trong tenant Bình. Không xóa subject toàn cục của Lan, không thu hồi credential dùng chung của nền tảng và không ngừng toàn bộ shared-worker.

Nếu yêu cầu xóa dữ liệu đang phục vụ đã hoàn tất nhưng một nhóm backup còn chờ hết hạn, hệ thống phải biểu diễn phần chờ đó. Nếu điều kiện kết thúc yêu cầu không còn nhóm dữ liệu này, quy trình chưa được xác nhận CLOSED. Không dùng nhãn “hoàn tất” để che một nghĩa vụ vẫn đang mở.

## 12. Bằng chứng để xác nhận offboarding

Các tình huống sau giúp kiểm chứng thiết kế và kết quả của một lần offboarding:

| Tình huống | Kết quả cần quan sát |
|---|---|
| Người dùng dùng token cũ gọi API tenant đã khóa | Request bị từ chối theo cơ chế thu hồi và giới hạn độ trễ đã xác định |
| Người dùng đổi sang tenant khác còn hợp lệ | Được đánh giá bằng quyền của tenant đó |
| Chấp nhận invitation cũ sau T0 | Không tạo membership có hiệu lực |
| Đăng nhập SSO vào tenant đã đóng | Không tái cấp quyền truy cập tenant |
| Provisioning gửi dữ liệu cập nhật đến muộn | Không hồi sinh tenant hoặc membership |
| Job đã xếp hàng trước T0 chạy sau T0 | Bị chặn hoặc xử lý theo chính sách công việc đang tồn tại |
| Webhook đã được lên lịch retry | Không tiếp tục gửi dữ liệu ngoài kế hoạch |
| Gọi lại một bước cleanup đã thành công | Kết quả ổn định, không mở rộng phạm vi |
| Một dịch vụ đích lỗi trong lúc cleanup | Hồ sơ giữ trạng thái chưa xong, tenant vẫn bị khóa |
| Khôi phục backup có tenant đã offboard | Trạng thái chặn được áp dụng trước khi mở quyền truy cập |
| Truy cập bản xuất sau khi hết hạn | Không được tải qua cơ chế đã thiết kế |
| Đối soát danh mục dữ liệu | Phân biệt được dữ liệu đã xóa, đang chờ và được giữ có phê duyệt |

Audit của quy trình nên lưu actor, tenant ID, mã yêu cầu, mốc khóa, thay đổi trạng thái, kết quả từng bước và ngoại lệ. Không lưu secret hoặc token vào log để chứng minh đã thu hồi chúng; định danh credential và kết quả xử lý là dữ liệu phù hợp hơn.

Tenant offboarding hoàn chỉnh kết nối vòng đời tổ chức với vòng đời quyền và dữ liệu. Việc khóa tenant phải có hiệu lực thực thi; việc thu hồi phải bao phủ người dùng lẫn workload; việc kết thúc phải dựa trên bằng chứng xử lý của các thành phần trong phạm vi.
