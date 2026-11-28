# Chủ sở hữu và người quản lý asset

## 1. Vì sao một asset phải có người chịu trách nhiệm?

Một tài sản thông tin (asset) có thể là tập dữ liệu khách hàng, ứng dụng, máy chủ, tài khoản dịch vụ, khóa mã hóa hoặc bản sao lưu. Phân loại tài sản cho biết cần bảo vệ tài sản đến mức nào. Việc chỉ định chủ sở hữu và người quản lý giúp xác định ai được quyết định mức bảo vệ đó, ai triển khai và ai phải cung cấp bằng chứng rằng các biện pháp bảo vệ đang hoạt động.

Giả sử cơ sở dữ liệu khách hàng được gắn nhãn “Hạn chế”, nhưng không ai có thẩm quyền duyệt việc xuất dữ liệu. Nhãn phân loại chưa đủ để ngăn một nhân viên nhận toàn bộ dữ liệu khi họ chỉ cần xem một nhóm khách hàng. Ngược lại, một nhóm vận hành giỏi cũng khó cấu hình đúng quyền truy cập nếu chưa có quyết định nghiệp vụ về người nào được xem thông tin nào.

Trong thiết kế yêu cầu bảo mật, cần nối được chuỗi sau:

**Tài sản → tác động nếu bị xâm phạm → người có quyền quyết định → yêu cầu bảo vệ → người thực hiện → bằng chứng kiểm chứng.**

Bài học này giúp bạn:

- Phân biệt chủ sở hữu tài sản với người quản lý, vận hành tài sản.
- Xác định quyền quyết định và ranh giới trách nhiệm giữa các vai trò.
- Ghi nhận quyền sở hữu trong hồ sơ phân loại tài sản.
- Chuyển trách nhiệm thành yêu cầu về xác thực, phân quyền, dữ liệu, logging và phục hồi.
- Kiểm chứng rằng trách nhiệm vẫn được duy trì khi hệ thống hoặc nhân sự thay đổi.

Trong bài, “chủ sở hữu” là vai trò chịu trách nhiệm quản trị trong tổ chức. Khái niệm này không tự khẳng định quyền sở hữu pháp lý đối với dữ liệu, cũng không đồng nghĩa với chủ thể mà dữ liệu mô tả.

## 2. Chủ sở hữu tài sản và người quản lý tài sản

### 2.1. Chủ sở hữu tài sản: quyết định và chịu trách nhiệm về kết quả bảo vệ

Chủ sở hữu tài sản, thường gọi là **asset owner**, là vai trò được tổ chức giao thẩm quyền quyết định cách sử dụng và mức bảo vệ cần thiết cho một tài sản trong phạm vi xác định.

Chủ sở hữu cần hiểu giá trị nghiệp vụ, tác động khi tài sản bị lộ, bị sửa sai hoặc không thể sử dụng. Họ không nhất thiết tự vận hành hệ thống, nhưng phải bảo đảm các quyết định bảo vệ có người thực hiện, có nguồn lực và có cơ chế theo dõi.

Các trách nhiệm điển hình gồm:

- Xác nhận mục đích sử dụng, phạm vi và mức độ quan trọng của tài sản.
- Phê duyệt phân loại ban đầu và các thay đổi phân loại.
- Xác định nhóm người được sử dụng tài sản, mục đích sử dụng và giới hạn chia sẻ.
- Xác định nhu cầu bảo mật, tính toàn vẹn, tính sẵn sàng, thời gian lưu giữ và phục hồi.
- Phê duyệt yêu cầu cấp quyền hoặc quy tắc cấp quyền tự động trong phạm vi được ủy quyền.
- Xem xét kết quả rà soát quyền, kết quả kiểm thử và các sai lệch chưa được xử lý.
- Đưa quyết định có rủi ro vượt thẩm quyền lên người có thẩm quyền phê duyệt.
- Bảo đảm có người tiếp nhận trách nhiệm khi chuyển giao hoặc ngừng sử dụng tài sản.

Ví dụ, trưởng bộ phận vận hành khách hàng có thể là chủ sở hữu tập dữ liệu hồ sơ khách hàng. Người này xác nhận nhân viên hỗ trợ được xem trường nào và trường nào phải che, dù nhóm cơ sở dữ liệu mới là bên triển khai chính sách truy cập.

Không nên gán vai trò chủ sở hữu chỉ vì một người tạo tài nguyên trên cloud, đứng tên tài khoản thanh toán hoặc giữ quyền quản trị cao nhất. Các dấu hiệu kỹ thuật đó chưa chứng minh họ có thẩm quyền quyết định nghiệp vụ.

### 2.2. Người quản lý tài sản: triển khai và duy trì biện pháp bảo vệ

Người quản lý tài sản trong bài này tương ứng với **asset custodian**: vai trò giữ gìn, vận hành hoặc quản trị kỹ thuật tài sản theo yêu cầu đã được phê duyệt.

Tùy tổ chức, vai trò này có thể do nhóm vận hành nền tảng, quản trị cơ sở dữ liệu, nhóm ứng dụng, nhóm dữ liệu hoặc nhà cung cấp dịch vụ thực hiện. “Người” ở đây có thể là một nhóm, nhưng nhóm phải có đầu mối và cơ chế phân công rõ ràng.

Các trách nhiệm điển hình gồm:

- Áp dụng cấu hình xác thực, phân quyền, mã hóa và kết nối.
- Cấp, thay đổi và thu hồi quyền dựa trên quyết định hợp lệ.
- Thực hiện sao lưu, kiểm tra khả năng phục hồi và theo dõi lỗi.
- Thu thập, bảo vệ và cung cấp log phục vụ kiểm chứng.
- Cập nhật cấu hình, vá lỗi và xử lý sai lệch theo phạm vi phụ trách.
- Báo cho chủ sở hữu khi yêu cầu chưa thể thực hiện hoặc có rủi ro mới.
- Cung cấp bằng chứng cho các đợt rà soát, bàn giao và ngừng sử dụng.

Người quản lý không mặc nhiên được hạ mức phân loại, mở rộng phạm vi chia sẻ hoặc chấp nhận rủi ro tồn dư. Nếu được ủy quyền một phần quyền quyết định, phạm vi, điều kiện và thời hạn ủy quyền phải được ghi nhận.

Có thể ghi nhớ:

> Chủ sở hữu xác nhận tài sản cần được bảo vệ thế nào và ai được sử dụng; người quản lý triển khai, duy trì và chứng minh việc bảo vệ đó.

### 2.3. Khác biệt quan trọng trong thực tế

| Khía cạnh | Chủ sở hữu tài sản | Người quản lý tài sản |
|---|---|---|
| Góc nhìn chính | Giá trị, mục đích và tác động nghiệp vụ | Cách triển khai và trạng thái vận hành |
| Phân loại | Phê duyệt mức phân loại trong phạm vi được giao | Áp dụng nhãn, cấu hình và kiểm soát tương ứng |
| Quyền truy cập | Phê duyệt chính sách và nhu cầu sử dụng | Thực thi cấp, đổi, thu hồi quyền |
| Dữ liệu | Quyết định mục đích, phạm vi chia sẻ và quy tắc lưu giữ theo chính sách | Cấu hình lưu trữ, che dữ liệu, sao lưu và xóa theo quyết định |
| Phục hồi | Xác nhận mức gián đoạn và mất dữ liệu có thể chấp nhận | Thiết kế, vận hành, kiểm thử phương án phục hồi |
| Sai lệch | Quyết định xử lý hoặc trình cấp có thẩm quyền | Phát hiện, báo cáo, khắc phục và lưu bằng chứng |
| Bàn giao | Bảo đảm có người tiếp nhận trách nhiệm | Bàn giao hệ thống, quyền, cấu hình và quy trình |

Ranh giới này là một mô hình phân công. Tên chức danh có thể khác nhau, nhưng mỗi quyết định vẫn cần người có thẩm quyền và mỗi biện pháp vẫn cần người thực hiện.

## 3. Phân biệt các vai trò dễ bị nhầm

### 3.1. Chủ sở hữu dữ liệu và chủ sở hữu hệ thống

Một hệ thống có thể xử lý dữ liệu của nhiều đơn vị. Vì vậy, không nên giả định chủ sở hữu hệ thống đồng thời được quyết định mọi mục đích sử dụng dữ liệu trong hệ thống.

Ví dụ:

- **Chủ sở hữu dữ liệu khách hàng** quyết định ai được khai thác thông tin khách hàng và trường dữ liệu nào phải che.
- **Chủ sở hữu ứng dụng chăm sóc khách hàng** chịu trách nhiệm về mục tiêu vận hành của ứng dụng, ngân sách và lộ trình thay đổi.
- **Nhóm nền tảng** quản lý hạ tầng chạy ứng dụng.
- **Nhóm cơ sở dữ liệu** thực thi quyền, sao lưu và phục hồi dữ liệu theo phân công.

Khi nhiều chủ sở hữu dữ liệu cùng sử dụng một nền tảng, cần xác định phạm vi của từng người và người chịu trách nhiệm cho các quyết định chung. Một thay đổi làm lộ dữ liệu giữa hai đơn vị không thể chỉ được phê duyệt bởi bên phụ trách vận hành nền tảng.

### 3.2. Chủ sở hữu rủi ro

**Chủ sở hữu rủi ro (risk owner)** là vai trò chịu trách nhiệm xử lý một rủi ro cụ thể và có thẩm quyền quyết định hoặc trình phê duyệt cách xử lý rủi ro đó.

Chủ sở hữu tài sản và chủ sở hữu rủi ro có thể là cùng một người, nhưng không bắt buộc. Rủi ro ảnh hưởng nhiều hệ thống hoặc nhiều đơn vị có thể cần cấp có thẩm quyền rộng hơn.

Ví dụ, chủ sở hữu dữ liệu đề xuất tạm hoãn một biện pháp bảo vệ để bảo đảm tiến độ kinh doanh. Quyết định chấp nhận rủi ro phải do đúng cấp có thẩm quyền thực hiện, với phạm vi, thời hạn và điều kiện rõ ràng. Việc chấp nhận rủi ro nội bộ không tự làm mất hiệu lực của yêu cầu bắt buộc mà tổ chức phải tuân thủ.

### 3.3. Nhóm an toàn thông tin, người dùng và nhà cung cấp

Nhóm an toàn thông tin hỗ trợ phân tích đe dọa, xây dựng tiêu chí bảo vệ và kiểm chứng. Việc tham vấn nhóm này không thay thế trách nhiệm của chủ sở hữu tài sản.

Người dùng có nghĩa vụ sử dụng tài sản đúng mục đích và báo cáo vấn đề. Họ không trở thành chủ sở hữu chỉ vì được cấp quyền truy cập.

Nhà cung cấp có thể thực hiện một phần trách nhiệm quản lý kỹ thuật. Tổ chức sử dụng dịch vụ vẫn cần chủ sở hữu nội bộ để xác nhận mục đích sử dụng, yêu cầu bảo vệ, trách nhiệm hợp đồng và bằng chứng cần nhận từ nhà cung cấp.

## 4. Xác định asset và phạm vi trách nhiệm trước khi gán người

Một tên quá rộng như “dữ liệu công ty” không đủ để giao trách nhiệm. Một danh sách quá chi tiết đến từng tệp tạm thời cũng khó duy trì. Phạm vi nên đủ rõ để ra quyết định và kiểm chứng.

Có thể bắt đầu bằng các câu hỏi:

1. Tài sản là dữ liệu, ứng dụng, hạ tầng, danh tính hay vật liệu bí mật?
2. Tài sản phục vụ quy trình nghiệp vụ nào?
3. Tài sản tồn tại ở những môi trường và bản sao nào?
4. Ai bị ảnh hưởng nếu tài sản bị lộ, bị sửa sai hoặc ngừng hoạt động?
5. Ai có thẩm quyền quyết định mục đích sử dụng?
6. Nhóm nào có khả năng thực thi và cung cấp bằng chứng bảo vệ?
7. Các tài sản phụ thuộc có cần chủ sở hữu và phạm vi quản lý riêng không?

Ví dụ, tập dữ liệu khách hàng có thể bao gồm cơ sở dữ liệu chính, bản sao đọc, tệp xuất phục vụ nghiệp vụ và bản sao lưu. Một khóa mã hóa dùng cho tập dữ liệu đó có thể được đăng ký thành tài sản riêng vì có cơ chế quản lý, vòng đời và phạm vi truy cập khác.

Không bắt buộc mọi bản sao phải có một chủ sở hữu khác nhau. Điều bắt buộc là biết bản sao thuộc phạm vi ai quản lý và kiểm soát nào áp dụng. Việc sao chép dữ liệu không tự làm giảm mức nhạy cảm; thay đổi mức phân loại cần đánh giá dữ liệu thực tế và quyết định hợp lệ.

### 4.1. Hồ sơ trách nhiệm tối thiểu

| Trường | Ý nghĩa |
|---|---|
| Mã và tên tài sản | Định danh ổn định để nối với yêu cầu, cấu hình và bằng chứng |
| Loại và phạm vi | Bao gồm gì, loại trừ gì, môi trường và các bản sao liên quan |
| Mục đích sử dụng | Căn cứ để đánh giá quyền truy cập và chia sẻ |
| Phân loại và tác động | Mức phân loại, lý do, tác động về bí mật, toàn vẹn, sẵn sàng |
| Chủ sở hữu | Vai trò có thẩm quyền và người đang đảm nhiệm vai trò đó |
| Người thay thế | Người hoặc cơ chế tiếp nhận khi chủ sở hữu vắng mặt |
| Người quản lý | Nhóm vận hành, đầu mối và phạm vi kỹ thuật |
| Quyền quyết định | Ai duyệt truy cập, phân loại, chia sẻ, ngoại lệ và ngừng sử dụng |
| Yêu cầu và phụ thuộc | Liên kết yêu cầu bảo mật, hệ thống liên quan và nhà cung cấp |
| Cơ chế rà soát | Chu kỳ, sự kiện kích hoạt và ngày rà soát gần nhất |
| Nơi lưu bằng chứng | Liên kết đến quyết định, báo cáo và kết quả kiểm thử được bảo vệ |

Nên lưu cả vai trò ổn định lẫn người đang đảm nhiệm. Chỉ ghi tên cá nhân dễ tạo khoảng trống khi người đó nghỉ việc. Chỉ ghi tên phòng ban lại không đủ rõ người có quyền phê duyệt.

Hồ sơ tài sản cũng cần kiểm soát truy cập: vị trí hệ thống, danh sách tài khoản quản trị hoặc chi tiết phục hồi có thể là thông tin nhạy cảm. Không đưa mật khẩu, khóa bí mật hoặc mã khôi phục trực tiếp vào hồ sơ này.

### 4.2. Ví dụ hồ sơ cho một tập dữ liệu

Ví dụ dưới đây là tình huống giả định trong một doanh nghiệp cung cấp dịch vụ trực tuyến. Các nhãn và thời hạn sử dụng trong bài là lựa chọn để minh họa đặc tả yêu cầu, cần được tổ chức đánh giá trước khi áp dụng thực tế.

| Thuộc tính | Giá trị minh họa |
|---|---|
| Mã tài sản | ASSET-CUST-001 |
| Tên | Tập dữ liệu hồ sơ khách hàng |
| Phạm vi | Dữ liệu sản xuất, bản sao đọc, tệp xuất được phê duyệt và bản sao lưu |
| Loại trừ | Dữ liệu thử nghiệm tổng hợp không tạo từ hồ sơ khách hàng thật |
| Mục đích | Cung cấp dịch vụ và hỗ trợ khách hàng theo nghiệp vụ đã duyệt |
| Phân loại | Hạn chế, vì chứa thông tin liên hệ và lịch sử tương tác |
| Chủ sở hữu | Trưởng bộ phận vận hành khách hàng; hồ sơ nhân sự xác định người đương nhiệm |
| Người thay thế | Phó bộ phận được chỉ định trong cơ chế ủy quyền |
| Người quản lý | Nhóm nền tảng dữ liệu; có đầu mối trực vận hành |
| Phụ thuộc | Dịch vụ định danh, ứng dụng hỗ trợ, kho log, dịch vụ quản lý khóa, kho sao lưu |
| Rà soát | Theo quý và khi thay đổi mục đích, tích hợp, phân loại hoặc người chịu trách nhiệm |

“Hạn chế” ở đây không tự suy ra cấu hình kỹ thuật cụ thể. Cần tiếp tục chuyển mức phân loại và tác động thành yêu cầu có thể kiểm chứng.

## 5. Dùng RACI để làm rõ ai quyết định và ai thực hiện

RACI là một cách biểu diễn trách nhiệm:

- **R — Responsible:** người thực hiện công việc.
- **A — Accountable:** người chịu trách nhiệm cuối cùng đối với quyết định hoặc kết quả trong phạm vi hàng đó.
- **C — Consulted:** người cần được tham vấn.
- **I — Informed:** người cần được thông báo.

Một hàng nên mô tả một quyết định hoặc đầu ra đủ hẹp, với một vai trò A rõ ràng. Một vai trò có thể đồng thời là R và A nếu được tổ chức giao như vậy.

Ví dụ cho ASSET-CUST-001:

| Hoạt động hoặc quyết định | Chủ sở hữu tài sản | Người quản lý | Nhóm an toàn thông tin | Chủ sở hữu rủi ro |
|---|---|---|---|---|
| Phê duyệt phân loại và mục đích sử dụng | A/R | C | C | I |
| Phê duyệt chính sách truy cập thông thường | A/R | C | C | I |
| Thực thi thay đổi quyền đã được duyệt | A | R | C | I |
| Cấu hình và theo dõi sao lưu theo yêu cầu | A | R | C | I |
| Xác nhận kết quả phục hồi đáp ứng nhu cầu nghiệp vụ | A | R | C | I |
| Phê duyệt chấp nhận rủi ro tồn dư trong thẩm quyền | R | C | C | A |
| Phê duyệt ngừng sử dụng tập dữ liệu | A/R | C | C | I |

Bảng trên chỉ phân công trách nhiệm. Nó chưa quy định bằng chứng phê duyệt, thời gian xử lý, hệ thống thực thi hay điều kiện kiểm thử. Những phần đó phải có trong đặc tả yêu cầu.

Nếu cùng một người đảm nhiệm cả chủ sở hữu và người quản lý, cần nhận diện xung đột ở các thao tác nhạy cảm. Ví dụ, người vận hành không nên tự duyệt yêu cầu mở rộng quyền quản trị cho chính mình. Tổ chức có thể yêu cầu cấp quản lý khác phê duyệt, ghi nhận đầy đủ thao tác và rà soát độc lập trong thời hạn xác định.

## 6. Từ trách nhiệm đến yêu cầu bảo mật có thể kiểm chứng

Câu “chủ sở hữu chịu trách nhiệm bảo mật dữ liệu” quá rộng để kiểm thử. Một yêu cầu hữu ích phải chỉ ra hành vi quan sát được và bằng chứng đủ để kết luận đạt hoặc không đạt.

Có thể dùng khuôn sau:

> Đối với [tài sản/phạm vi], khi [điều kiện hoặc sự kiện], [hệ thống hoặc vai trò] phải [hành vi bắt buộc] trong [giới hạn định lượng nếu cần]. [Vai trò phê duyệt] xác nhận quyết định. Bằng chứng gồm [đầu ra]. Kiểm chứng bằng [phương pháp và tiêu chí đạt].

Nên phân biệt ba lớp:

- **Yêu cầu quản trị:** hồ sơ tài sản phải có chủ sở hữu hợp lệ.
- **Yêu cầu hệ thống:** dịch vụ cấp quyền phải kiểm tra phê duyệt trước khi áp dụng.
- **Yêu cầu vận hành:** nhóm phụ trách phải xử lý tín hiệu thu hồi quyền trong thời hạn đã định.

Một kiểm thử API có thể xác minh điều kiện cấp quyền, nhưng không tự chứng minh người phê duyệt có thẩm quyền nghiệp vụ. Cần kết hợp kiểm tra cấu hình, hồ sơ quyết định và thử nghiệm hành vi thực tế.

### 6.1. Các yêu cầu minh họa

Các yêu cầu dưới đây tiếp tục dùng ASSET-CUST-001. Các mốc 4 giờ, 24 giờ, 15 phút, 8 giờ và chu kỳ theo quý là mục tiêu giả định của tình huống, không phải giá trị mặc định cho mọi tài sản.

| Mã | Đặc tả yêu cầu | Trách nhiệm và bằng chứng | Cách kiểm chứng |
|---|---|---|---|
| SR-OWN-01 | Trước khi đưa vào sản xuất, ASSET-CUST-001 phải có hồ sơ xác định chủ sở hữu đang đảm nhiệm, người thay thế, nhóm quản lý và phạm vi tài sản. Quy trình phát hành phải kiểm tra hồ sơ này. | Chủ sở hữu xác nhận phạm vi; người quản lý cung cấp liên kết hệ thống; lưu bản phê duyệt và kết quả kiểm tra phát hành. | Thử phát hành với hồ sơ thiếu từng trường bắt buộc; quy trình phải từ chối. Kiểm tra trường chủ sở hữu trỏ đến người đương nhiệm có thẩm quyền. |
| SR-AUTH-01 | Mọi truy cập tương tác bằng quyền quản trị tới tài sản phải dùng danh tính cá nhân qua cơ chế xác thực đa yếu tố được tổ chức phê duyệt; đường truy cập khẩn cấp phải tuân theo SR-EXC-01. | Người quản lý cấu hình đường truy cập; chủ sở hữu xác nhận phạm vi người được quản trị; lưu cấu hình và log xác thực. | Thử trên mọi đường quản trị đã kiểm kê, gồm công cụ cơ sở dữ liệu và bảng điều khiển; truy cập thiếu yếu tố bắt buộc phải bị từ chối. |
| SR-ACC-01 | Chỉ cấp quyền khi yêu cầu có tài sản, người nhận, tập quyền, mục đích, thời hạn và phê duyệt hợp lệ của chủ sở hữu hoặc người được ủy quyền. Người yêu cầu không được tự duyệt yêu cầu của mình. | Chủ sở hữu phê duyệt chính sách; người quản lý thực thi; lưu yêu cầu, danh tính người duyệt và kết quả cấp quyền. | Thử yêu cầu thiếu, hết hạn, tự duyệt hoặc có người duyệt ngoài phạm vi ủy quyền; tất cả phải bị từ chối. Yêu cầu hợp lệ chỉ được cấp đúng tập quyền đã duyệt. |
| SR-ACC-02 | Trong tối đa 4 giờ từ lúc hệ thống quản lý truy cập tiếp nhận thông báo thu hồi hợp lệ, quyền tương ứng phải bị vô hiệu hóa trên các đường truy cập thuộc phạm vi, kể cả phiên và token còn hiệu lực. | Người quản lý xử lý và ghi mốc thời gian; chủ sở hữu xác nhận phạm vi quyền cần thu hồi. | Dùng tài khoản thử đã có phiên trước khi thu hồi; sau hạn xử lý phải không truy cập được qua ứng dụng, API và đường trực tiếp đã đăng ký. |
| SR-DATA-01 | Vai trò hỗ trợ thông thường chỉ được đọc tập trường đã duyệt và không được xuất hàng loạt. Xuất hàng loạt phải có phê duyệt riêng xác định trường dữ liệu, người nhận, mục đích và hạn sử dụng. | Chủ sở hữu duyệt ma trận quyền; người quản lý áp dụng trên ứng dụng, API và cơ sở dữ liệu; lưu cấu hình và phê duyệt xuất. | Thử đọc trường ngoài quyền, sửa yêu cầu API để lấy thêm trường và truy vấn qua đường trực tiếp bằng cùng phạm vi quyền; các thao tác vượt quyền phải bị chặn. |
| SR-LOG-01 | Mọi sự kiện cấp, đổi, thu hồi quyền, đổi phân loại và xuất dữ liệu phải tạo bản ghi có mã tài sản, danh tính tác động, thời điểm, hành động, đối tượng, kết quả và mã yêu cầu/phê duyệt nếu có. Log không chứa mật khẩu, token hoặc toàn bộ hồ sơ khách hàng. | Người quản lý thu thập và hạn chế quyền sửa/xóa log; nhóm an toàn thông tin hỗ trợ kiểm chứng; lưu mẫu sự kiện và cấu hình bảo vệ. | Sinh từng loại sự kiện, đối chiếu đủ trường; thử sửa log bằng tài khoản vận hành tài sản không có quyền quản trị kho log và xác nhận bị từ chối. |
| SR-REC-01 | Phương án phục hồi phải đạt RPO không quá 15 phút và RTO không quá 4 giờ trong kịch bản kiểm thử đã được chủ sở hữu phê duyệt; thực hiện kiểm thử theo quý và sau thay đổi lớn ảnh hưởng phục hồi. | Người quản lý thực hiện; chủ sở hữu xác nhận tiêu chí nghiệp vụ; lưu thời điểm, dữ liệu kiểm tra, cấu hình và biên bản kết quả. | Thực hiện phục hồi trong môi trường cô lập, đo độ lùi dữ liệu và thời gian khôi phục, kiểm tra tính toàn vẹn cùng khả năng thực hiện nghiệp vụ đã xác định. |
| SR-HAND-01 | Thay đổi người đảm nhiệm vai trò chủ sở hữu phải có người tiếp nhận hoặc người thay thế được chỉ định trước thời điểm bàn giao có hiệu lực; hồ sơ và quyền phê duyệt phải được cập nhật tại thời điểm đó. | Chủ sở hữu hoặc cấp quản lý có thẩm quyền xác nhận; người quản lý cập nhật luồng phê duyệt; lưu biên bản và lịch sử thay đổi. | Mô phỏng chuyển vai trò; sau thời điểm hiệu lực, người cũ không còn duyệt được, người mới duyệt đúng phạm vi và các yêu cầu đang chờ được chuyển tiếp có dấu vết. |

Các yêu cầu xác thực dành cho người quản trị không tự áp dụng nguyên dạng cho tài khoản dịch vụ. Danh tính máy cần đặc tả riêng về cách cấp thông tin xác thực, phạm vi quyền, thời hạn, xoay vòng và thu hồi. Chủ sở hữu phải xác nhận dịch vụ được phép làm gì; người quản lý phải triển khai cơ chế tương ứng.

### 6.2. Làm rõ mốc đo và phạm vi kiểm thử

“Thu hồi trong 4 giờ” chỉ có ý nghĩa khi xác định được lúc bắt đầu đo, lúc kết thúc và đường truy cập phải kiểm tra. SR-ACC-02 chọn mốc bắt đầu là khi hệ thống quản lý truy cập tiếp nhận thông báo hợp lệ. Quy trình phát hiện và gửi thông báo cũng cần mục tiêu riêng nếu muốn kiểm soát toàn bộ thời gian từ lúc một người nghỉ việc đến lúc họ mất quyền.

Tương tự, cần thống nhất cách đo phục hồi:

- **RPO — Recovery Point Objective:** mức mất dữ liệu tối đa được chấp nhận, biểu diễn bằng khoảng thời gian lùi dữ liệu.
- **RTO — Recovery Time Objective:** thời gian mục tiêu để khôi phục khả năng cung cấp dịch vụ trong phạm vi đã xác định.

Trong kịch bản minh họa, mốc bắt đầu đo RTO là lúc sự cố giả lập làm dịch vụ không đáp ứng; mốc kết thúc là lúc các thao tác nghiệp vụ được chọn hoạt động trở lại và qua kiểm tra toàn vẹn. RPO được đối chiếu giữa thời điểm giao dịch gần nhất trước sự cố và thời điểm giao dịch liên tục gần nhất có thể khôi phục. Cần kiểm tra cả khoảng trống giao dịch, không chỉ nhìn một bản ghi có thời gian mới nhất.

Khôi phục thành công một bản sao lưu chưa đủ để kết luận đạt yêu cầu phục hồi dịch vụ. Dịch vụ còn có thể thiếu khóa giải mã, cấu hình, danh tính máy, kết nối hoặc khả năng truy cập các phụ thuộc.

### 6.3. Trường hợp khẩn cấp và ngoại lệ

Quyền truy cập khẩn cấp cần một quy trình đã được phê duyệt trước. Nếu đợi chủ sở hữu trực tiếp xác nhận mọi thao tác trong một sự cố nghiêm trọng, việc phục hồi có thể bị trì hoãn. Nếu chỉ ghi “khẩn cấp thì bỏ qua”, lại tạo một đường vượt kiểm soát không có giới hạn.

Ví dụ đặc tả cho SR-EXC-01:

> Cơ chế khẩn cấp chỉ được kích hoạt bởi vai trò trực sự cố đã chỉ định, theo quy trình được chủ sở hữu và cấp có thẩm quyền phê duyệt trước. Mỗi lần kích hoạt phải có mã sự cố, danh tính người dùng, lý do, phạm vi quyền và thời điểm hết hạn; quyền có thời hạn tối đa 8 giờ và phải tự hết hiệu lực. Hệ thống phải ghi log và phát thông báo ngay khi kích hoạt. Một người có thẩm quyền độc lập với người sử dụng quyền phải hoàn tất rà soát trong 24 giờ kể từ lúc kích hoạt.

Kiểm thử cần xác nhận cả việc cấp quyền có giới hạn, tự hết hạn, lưu dấu vết, phát thông báo và khả năng truy cập bằng phiên cũ sau khi quyền hết hiệu lực. Nếu quy trình rà soát quá hạn, phải phát sinh đầu việc xử lý có người chịu trách nhiệm.

Ngoại lệ tạm thời đối với một yêu cầu khác cũng cần lưu tài sản bị ảnh hưởng, lý do, rủi ro, biện pháp bù đắp, người phê duyệt, hạn hết hiệu lực và kế hoạch xử lý. Hết hạn không được tự động hiểu là gia hạn.

## 7. Liên kết chủ sở hữu với mô hình đe dọa và kiến trúc

Phân công trách nhiệm nên xuất hiện khi phân tích luồng dữ liệu và ranh giới tin cậy, không chỉ nằm trong một bảng kiểm kê tách rời.

Xét luồng đơn giản:

**Nhân viên hỗ trợ → dịch vụ định danh → ứng dụng hỗ trợ → API hồ sơ → cơ sở dữ liệu khách hàng.**

Ngoài luồng đó còn có đường quản trị, tác vụ sao lưu và tệp xuất dữ liệu. Mỗi đường có thể sử dụng danh tính và cơ chế phân quyền khác nhau.

| Đe dọa hoặc sai lệch | Quyết định thuộc chủ sở hữu | Việc người quản lý cần thực hiện | Yêu cầu liên quan |
|---|---|---|---|
| Nhân viên xem dữ liệu vượt nhu cầu công việc | Xác định tập trường, tập khách hàng và mục đích được phép | Thực thi chính sách ở các điểm truy cập và kiểm tra trường hợp từ chối | SR-ACC-01, SR-DATA-01 |
| Tài khoản đã nghỉ việc vẫn giữ phiên truy cập | Xác nhận sự kiện thu hồi và phạm vi ảnh hưởng | Vô hiệu hóa quyền, phiên và token trong phạm vi | SR-ACC-02 |
| Người vận hành tự mở rộng quyền | Yêu cầu phê duyệt độc lập và quy định khẩn cấp | Chặn tự duyệt, giới hạn quyền và ghi log | SR-AUTH-01, SR-ACC-01, SR-EXC-01 |
| Dữ liệu bị xuất ra ngoài luồng ứng dụng | Xác định ai được xuất, người nhận và mục đích hợp lệ | Chặn xuất hàng loạt trái quyền, bảo vệ các đường trực tiếp | SR-DATA-01, SR-LOG-01 |
| Phục hồi không đạt nhu cầu nghiệp vụ | Xác định ưu tiên, RPO, RTO và tiêu chí chấp nhận | Thiết kế, kiểm thử dữ liệu, khóa, cấu hình và phụ thuộc | SR-REC-01 |

Bảng liên kết giúp phát hiện khoảng trống. Chẳng hạn, nếu kiểm soát che dữ liệu chỉ đặt ở giao diện trong khi tài khoản hỗ trợ có quyền đọc trực tiếp cơ sở dữ liệu, yêu cầu chưa được thực thi trên toàn bộ phạm vi.

Khi đổi kiến trúc, cần xem lại cả trách nhiệm. Thêm kho phân tích, tích hợp đối tác hoặc công cụ hỗ trợ mới có thể tạo thêm bản sao, thêm người quản lý và thêm quyết định chia sẻ cần chủ sở hữu phê duyệt.

## 8. Duy trì trách nhiệm trong vòng đời tài sản

### 8.1. Khi tạo mới hoặc tiếp nhận

Trước khi sử dụng tài sản, cần có định danh, phạm vi, chủ sở hữu, người quản lý và phân loại ban đầu. Nếu chưa biết ai có thẩm quyền quyết định, phải giao đầu mối tạm thời theo cơ chế của tổ chức và hạn chế việc sử dụng đến khi hoàn tất phân công.

Quy trình tiếp nhận nên yêu cầu bằng chứng về:

- Quyết định sử dụng và mục đích đã phê duyệt.
- Các phụ thuộc và đường truy cập chính.
- Yêu cầu bảo vệ, người triển khai và cách kiểm chứng.
- Điều kiện cho phép đưa vào môi trường sản xuất.

### 8.2. Khi vận hành

Chủ sở hữu cần nhận được thông tin đủ để quyết định, như danh sách quyền đang có, sai lệch chưa xử lý, kết quả phục hồi và các ngoại lệ sắp hết hạn. Một báo cáo chỉ ghi “đã cấu hình bảo mật” không cho biết yêu cầu nào đạt và yêu cầu nào chưa đạt.

Người quản lý cần thông báo các thay đổi có thể ảnh hưởng đến phân loại hoặc yêu cầu: dữ liệu mới được thu thập, lượng người dùng tăng, vùng triển khai mới, đường truy cập mới hoặc nhà cung cấp mới.

Đối với ví dụ trong bài, rà soát theo quý cần có:

1. Xác nhận chủ sở hữu và người quản lý vẫn đúng.
2. Đối chiếu danh sách quyền với nhu cầu hiện tại.
3. Kiểm tra bản sao, tệp xuất và phụ thuộc mới.
4. Xem kết quả phục hồi cùng các sai lệch.
5. Ghi quyết định, người xử lý và hạn hoàn thành cho từng vấn đề.

Chu kỳ rà soát phải được chọn theo rủi ro. Ngoài chu kỳ, thay đổi quan trọng phải kích hoạt rà soát riêng, không chờ kỳ tiếp theo.

### 8.3. Khi chuyển giao

Chuyển giao trách nhiệm cần bao gồm hồ sơ và quyền quyết định, không chỉ đổi tên trên danh sách tài sản.

Hồ sơ bàn giao nên thể hiện:

- Người giao, người nhận và thời điểm có hiệu lực.
- Phạm vi tài sản, mức phân loại và các yêu cầu đang áp dụng.
- Ngoại lệ, rủi ro và đầu việc còn mở.
- Vị trí bằng chứng, kết quả kiểm thử và quy trình xử lý sự cố.
- Các luồng phê duyệt và quyền cần cập nhật hoặc thu hồi.

Nếu chủ sở hữu rời tổ chức đột ngột, cơ chế người thay thế hoặc cấp quản lý có thẩm quyền phải được kích hoạt để tránh tài sản không có người quyết định. Người quản lý kỹ thuật không tự trở thành chủ sở hữu chỉ vì họ vẫn đang duy trì hệ thống.

### 8.4. Khi ngừng sử dụng

Chủ sở hữu xác nhận tài sản không còn cần cho mục đích đang được phê duyệt, đồng thời kiểm tra các yêu cầu lưu giữ hoặc tạm giữ đang có hiệu lực. Người quản lý thực hiện thu hồi quyền, dừng luồng tích hợp, xử lý dữ liệu và ghi bằng chứng theo quyết định đó.

Phạm vi xử lý phải xét cả bản sao lưu, tệp xuất, bộ nhớ đệm và dữ liệu tại nhà cung cấp. Nếu một bản sao lưu phải được giữ đến hết thời hạn đã duyệt, cần ghi rõ nơi lưu, giới hạn truy cập, ngày hết hạn và cách xử lý khi phục hồi lại dữ liệu đã được yêu cầu xóa.

Việc đánh dấu “đã ngừng sử dụng” trong danh mục chưa chứng minh dữ liệu đã được xử lý đúng. Cần bằng chứng tương ứng với phương thức đã chọn, chẳng hạn kết quả thu hồi quyền, danh sách tài nguyên đã dừng và xác nhận xử lý bản sao từ bên cung cấp dịch vụ.

## 9. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Ghi chủ sở hữu là “IT” | Không rõ ai được quyết định mục đích hoặc chấp thuận chia sẻ | Chỉ định vai trò có thẩm quyền, người đương nhiệm và người thay thế |
| Gán chủ sở hữu cho người tạo tài nguyên | Quyền kỹ thuật bị nhầm với quyền quyết định nghiệp vụ | Xác nhận quyền sở hữu từ quy trình sử dụng và thẩm quyền được giao |
| Mọi bộ phận cùng là chủ sở hữu của cùng một quyết định | Dễ bỏ sót hoặc trì hoãn phê duyệt | Tách phạm vi, xác định một đầu mối chịu trách nhiệm cho từng quyết định |
| Người quản lý được tự giảm phân loại để dễ vận hành | Biện pháp bảo vệ bị hạ mà không xét tác động | Bắt buộc quyết định phân loại có phê duyệt và lịch sử thay đổi |
| Chỉ kiểm kê dữ liệu chính | Bản sao và tệp xuất có thể không được quản lý | Mở rộng phạm vi sang các bản sao và luồng phân phối |
| Chỉ lưu tên cá nhân | Người nghỉ việc khiến tài sản mất đầu mối | Lưu cả vai trò, người đương nhiệm và cơ chế thay thế |
| Giao toàn bộ trách nhiệm cho nhà cung cấp | Không có người nội bộ quyết định và xác nhận đáp ứng | Chỉ định chủ sở hữu nội bộ, quy định trách nhiệm và bằng chứng từ nhà cung cấp |
| Dùng câu “phải an toàn” làm yêu cầu | Không có điều kiện đạt hoặc không đạt | Chỉ rõ hành vi, phạm vi, mốc đo và cách kiểm chứng |
| Có RACI nhưng hệ thống cho phép tự duyệt | Trách nhiệm trên giấy không được thực thi | Liên kết RACI với danh tính, luồng phê duyệt và kiểm thử từ chối |
| Rà soát xong nhưng không xử lý sai lệch | Vấn đề lặp lại và không có hạn khắc phục | Mỗi sai lệch phải có người xử lý, hạn hoàn thành và quyết định rủi ro phù hợp |

## 10. Bài tập tự thực hành

Chọn một tài sản quen thuộc, ví dụ kho mã nguồn, dữ liệu đơn hàng hoặc khóa ký phát hành ứng dụng. Thực hiện các bước sau:

1. Viết phạm vi tài sản và ít nhất hai phụ thuộc hoặc bản sao liên quan.
2. Mô tả tác động khi tài sản bị lộ, bị sửa sai và không thể sử dụng.
3. Chỉ định chủ sở hữu, người thay thế, người quản lý và người có thẩm quyền xử lý rủi ro.
4. Liệt kê ai quyết định phân loại, cấp quyền, chia sẻ, phục hồi và ngừng sử dụng.
5. Viết ba yêu cầu có thể kiểm chứng: một yêu cầu truy cập, một yêu cầu logging và một yêu cầu phục hồi hoặc thu hồi quyền.
6. Với mỗi yêu cầu, ghi người phê duyệt, người thực hiện, bằng chứng và tiêu chí đạt.
7. Mô phỏng tình huống chủ sở hữu nghỉ việc hoặc người quản lý cần quyền khẩn cấp; kiểm tra xem có khoảng trống trách nhiệm không.

Tự kiểm tra kết quả:

- Người được gọi là chủ sở hữu có thẩm quyền thực tế hay chỉ đang giữ quyền quản trị?
- Có quyết định nào chưa biết ai phê duyệt không?
- Có đường truy cập hoặc bản sao nào ngoài phạm vi quản lý không?
- Có thể chứng minh một yêu cầu đã đạt bằng hành vi và hồ sơ cụ thể không?
- Khi đổi nhân sự, quyền phê duyệt có được chuyển giao và quyền cũ có bị thu hồi không?

Chỉ định đúng vai trò là điểm bắt đầu. Giá trị của việc phân công xuất hiện khi quyết định nghiệp vụ được chuyển thành yêu cầu cụ thể, được thực thi tại đúng vị trí trong kiến trúc và có bằng chứng để kiểm chứng xuyên suốt vòng đời tài sản.
