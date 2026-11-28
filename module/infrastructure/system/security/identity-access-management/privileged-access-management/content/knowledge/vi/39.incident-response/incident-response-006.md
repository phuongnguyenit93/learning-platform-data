# Chặn đường remote access

## 1. Mục tiêu của việc chặn truy cập từ xa

Khi tài khoản đặc quyền bị nghi chiếm quyền, một phiên quản trị bất thường xuất hiện hoặc bastion có dấu hiệu bị xâm nhập, mục tiêu trước mắt là ngăn đối tượng tiếp tục điều khiển hệ thống. Trong bối cảnh Privileged Access Management (PAM), việc này không chỉ là khóa một tài khoản hay tắt một đường VPN. Cần đồng thời kiểm soát người truy cập, quyền đang được cấp, phiên đang tồn tại và mọi đường mạng có thể tới tài nguyên nhạy cảm.

**Chặn đường remote access** là tập hợp hành động có phối hợp nhằm ngăn tạo mới, tái lập hoặc tiếp tục sử dụng những đường quản trị từ xa nằm trong phạm vi sự cố. Kết quả cần đạt là quyền điều khiển trái phép không còn hiệu lực, trong khi đội ứng cứu vẫn có một kênh quản trị được kiểm soát để điều tra và phục hồi.

Một tài khoản bị vô hiệu hóa nhưng còn phiên SSH đang mở có thể chưa bị cô lập. Một phiên RDP bị ngắt kết nối nhưng chưa đăng xuất có thể vẫn giữ trạng thái đăng nhập trên máy đích. Một VPN bị khóa nhưng máy chủ còn nhận kết nối trực tiếp từ mạng quản trị khác cũng chưa đạt mục tiêu. Vì vậy, tiêu chí thành công phải gắn với các đường truy cập và trạng thái thực tế, không chỉ với thông báo “thao tác thành công” của một công cụ.

Sau bài học, người học cần có khả năng:

- Xác định những đường truy cập từ xa liên quan đến một danh tính, thiết bị, phiên hoặc máy đích.
- Phân biệt khóa danh tính, thu hồi quyền, thu hồi bí mật, kết thúc phiên và chặn kết nối mạng.
- Chọn phạm vi cô lập phù hợp với mức độ nghiêm trọng và độ tin cậy của hạ tầng quản trị.
- Lập trình tự chặn có người chịu trách nhiệm, bằng chứng kiểm chứng và kênh ứng cứu còn hoạt động.
- Đặt điều kiện mở lại truy cập theo least privilege, JIT/JEA và khả năng quan sát.

## 2. Phạm vi: đường quản trị nào cần được xét đến?

Remote access trong PAM bao gồm mọi cơ chế cho phép một chủ thể điều khiển hoặc thay đổi tài nguyên từ một vị trí khác. Nó không giới hạn ở giao diện desktop từ xa.

| Nhóm đường truy cập | Ví dụ trong môi trường quản trị | Điểm cần kiểm tra khi có sự cố |
| --- | --- | --- |
| Kết nối vào mạng | VPN, cổng truy cập theo danh tính, mạng quản trị riêng | Phiên kết nối, thiết bị nguồn, tuyến mạng và quyền tới đích |
| Trung gian quản trị | Bastion, jump host, PAM proxy, session gateway | Phiên đang chuyển tiếp, quyền mở phiên mới, đường dự phòng |
| Giao thức trên máy đích | SSH, RDP, giao diện quản trị web, quản trị từ xa qua dịch vụ hệ điều hành | Listener, phiên đăng nhập, quyền cục bộ và cơ chế xác thực |
| Quản trị qua API | API hạ tầng, control plane cloud, công cụ điều phối | Token, role, phiên liên kết danh tính và tác vụ đã gửi |
| Truy cập do agent duy trì | Công cụ hỗ trợ từ xa, connector, agent quản lý | Kênh kết nối ra ngoài, danh tính agent, nơi phát lệnh |
| Kênh khẩn cấp hoặc hạ tầng | Console quản trị, kênh ngoài băng, tài khoản break-glass | Mức độ độc lập, người được sử dụng và nhật ký hoạt động |

Một đường tới đích có thể gồm nhiều thành phần:

```text
Thiết bị quản trị
    -> Cổng truy cập mạng
    -> Bastion hoặc PAM session gateway
    -> Dịch vụ quản trị trên máy đích
    -> Quyền thực thi lệnh hoặc thay đổi cấu hình
```

Tuy nhiên, hệ thống cũng có thể tồn tại đường khác như kết nối trực tiếp từ subnet nội bộ, gateway dự phòng, agent kết nối ra ngoài hoặc API control plane. Chặn được đường đi tiêu chuẩn chưa chứng minh rằng mọi đường trong phạm vi sự cố đã bị chặn.

Phạm vi bài học là **containment đối với truy cập đặc quyền từ xa**. Cô lập này không tự loại bỏ phần mềm độc hại, tác vụ đã lập lịch, thay đổi cấu hình hay dữ liệu đã bị lấy đi. Những vấn đề đó cần tiếp tục được điều tra và xử lý trong quy trình ứng phó sự cố.

## 3. Tách năm loại kiểm soát thường bị nhầm lẫn

### 3.1. Khóa danh tính

Khóa hoặc tạm vô hiệu hóa danh tính nhằm ngăn danh tính đó tiếp tục xác thực hoặc được cấp thêm quyền theo cơ chế đang áp dụng. Đây là một lớp kiểm soát cần thiết khi tài khoản đặc quyền bị nghi chiếm quyền.

Tác dụng đối với phiên cũ phụ thuộc hệ thống. Một máy đích có thể đã chấp nhận xác thực trước đó và không truy vấn lại trạng thái tài khoản trong suốt phiên. Token hoặc thông tin đăng nhập được lưu tạm cũng có thể có vòng đời riêng.

Vì vậy, không dùng sự kiện “account disabled” làm bằng chứng duy nhất cho việc mọi phiên đã mất hiệu lực.

### 3.2. Thu hồi quyền và chặn cấp mới

Nhóm này gồm hủy quyền JIT đang còn thời hạn, bỏ quyền vào nhóm quản trị tạm thời, đình chỉ yêu cầu chờ phê duyệt và ngăn cấp mới quyền truy cập tới tài nguyên bị ảnh hưởng.

Cần xét cả quy trình cấp quyền. Nếu chỉ xóa quyền hiện tại nhưng luồng phê duyệt hoặc automation vẫn tiếp tục cấp lại, đường truy cập có thể được mở lại ngay sau khi đội ứng cứu vừa chặn.

Đối với JEA, việc giới hạn tập lệnh được phép có thể giảm phạm vi tác động, nhưng không thay thế việc kết thúc một phiên đang bị đối tượng điều khiển.

### 3.3. Thu hồi hoặc thay thế thông tin xác thực

Thông tin xác thực có thể là mật khẩu, khóa SSH, certificate, token, secret dùng bởi agent hoặc credential do vault cấp. Biện pháp cần chọn theo loại credential và cách máy đích kiểm tra nó.

- Đổi mật khẩu làm mất tác dụng của mật khẩu cũ ở nơi đã cập nhật, nhưng không mặc nhiên kết thúc phiên đã xác thực.
- Gỡ khóa được tin cậy khỏi máy đích chỉ hữu ích ở những đích đã nhận thay đổi; cần kiểm kê đầy đủ nơi khóa có hiệu lực.
- Thu hồi certificate chỉ có tác dụng nếu bên xác thực thực sự thực thi cơ chế thu hồi tương ứng. Không giả định mọi đích đều kiểm tra cùng một nguồn thu hồi.
- Token đã phát hành có thể tiếp tục được chấp nhận cho tới khi hết hạn hoặc tới khi cơ chế thu hồi có hiệu lực tại điểm thực thi.
- Xoay secret của tài khoản dịch vụ cần phối hợp với các ứng dụng sử dụng nó để tránh gây thêm sự cố vận hành.

Một secret đã lộ phải được xử lý theo quy trình vòng đời credential, nhưng việc đó cần đi cùng containment đối với phiên và đường truy cập.

### 3.4. Kết thúc phiên đang tồn tại

Phiên có thể tồn tại ở cổng VPN, gateway PAM, bastion, máy đích hoặc API control plane. Một người dùng có thể đồng thời có nhiều phiên và nhiều token, kể cả trên các nút dự phòng khác nhau.

Phân biệt rõ:

- **Disconnect:** kết nối giao diện hoặc kênh truyền bị tách ra; trạng thái đăng nhập hay tác vụ trên đích có thể vẫn tồn tại.
- **Terminate hoặc logoff:** phiên được kết thúc theo cơ chế của hệ thống; vẫn phải kiểm tra tác vụ đã tách khỏi phiên.
- **Revoke session hoặc token:** trạng thái xác thực bị thu hồi theo cơ chế cụ thể; cần xác minh các bên thực thi đã nhận và áp dụng.

Không suy diễn rằng thao tác trên gateway chắc chắn đã xóa toàn bộ phiên, tiến trình hoặc quyền trên máy đích.

### 3.5. Chặn đường mạng

Chặn đường mạng ngăn luồng quản trị tiếp tục đi qua một điểm kiểm soát: firewall, phân đoạn mạng, chính sách truy cập cổng hoặc host firewall.

Đây là lớp kiểm soát hữu ích khi việc thu hồi danh tính có độ trễ hoặc khi chưa tin cậy hệ thống danh tính. Tuy nhiên, chính sách mạng mới có thể chỉ ảnh hưởng kết nối mới; cách xử lý kết nối đã thiết lập phụ thuộc thiết bị, trạng thái kết nối và cách áp dụng rule.

Cần kiểm chứng riêng kết nối mới và kết nối đang tồn tại. Khi phải xóa trạng thái kết nối, thực hiện có mục tiêu theo kế hoạch đã phê duyệt và đánh giá ảnh hưởng tới các luồng hợp lệ.

## 4. Xác định phạm vi cô lập từ bằng chứng

### 4.1. Đặt câu hỏi theo bốn đối tượng

Trước khi chọn biện pháp, xác định các đối tượng nghi bị ảnh hưởng:

1. **Danh tính:** tài khoản người quản trị, tài khoản dùng chung, service account, danh tính liên kết hoặc tài khoản khẩn cấp.
2. **Thiết bị nguồn:** máy trạm quản trị, máy VPN, máy automation hoặc thiết bị hỗ trợ từ xa.
3. **Điểm trung gian:** bastion, PAM proxy, gateway, connector hoặc hệ thống phát lệnh.
4. **Tài nguyên đích:** máy chủ, thiết bị mạng, kho secret, cơ sở dữ liệu hoặc control plane.

Cùng một sự kiện đăng nhập bất thường có thể dẫn đến phạm vi xử lý khác nhau. Nếu bằng chứng cho thấy credential bị lộ nhưng thiết bị quản trị vẫn đáng tin, containment có thể tập trung vào danh tính, phiên và các đích credential đó truy cập được. Nếu máy trạm quản trị bị xâm nhập, các tài khoản đã sử dụng trên máy đó cũng cần được đưa vào phạm vi điều tra. Nếu bastion bị kiểm soát, mọi phiên qua nó và các credential nó có thể tiếp cận đều cần được đánh giá.

### 4.2. Tạo bản đồ truy cập tối thiểu

Một bản đồ phục vụ containment cần đủ để trả lời “ai có thể tới đâu bằng đường nào”, không cần chờ hoàn thành toàn bộ sơ đồ hạ tầng.

Các trường tối thiểu gồm:

- Danh tính và nhóm quyền liên quan.
- Thiết bị hoặc vùng mạng nguồn.
- Cổng truy cập, bastion, proxy hoặc connector trung gian.
- Máy đích và dịch vụ quản trị có thể truy cập.
- Loại credential, nơi cấp, nơi chấp nhận và thời hạn hiệu lực.
- Phiên đang hoạt động, định danh phiên và thời điểm quan sát.
- Cơ chế dự phòng và các đường có thể bỏ qua PAM.
- Chủ sở hữu kiểm soát, hành động dự kiến và nguồn log dùng để xác minh.

Địa chỉ IP đơn lẻ hiếm khi đủ để định danh một chủ thể. NAT, máy dùng chung, proxy và địa chỉ thay đổi có thể làm nhiều hoạt động trùng địa chỉ nguồn. Cần kết hợp IP với danh tính, device ID, session ID và thời gian.

### 4.3. Không chờ dữ liệu hoàn hảo khi thiệt hại đang tiếp diễn

Nếu đối tượng đang thực hiện thay đổi nguy hiểm hoặc có dấu hiệu lấy dữ liệu, đội ứng cứu có thể cần cô lập ngay một vùng đã xác định trong phạm vi thẩm quyền. Ghi rõ lý do, giả định và ảnh hưởng dự kiến, rồi mở rộng bản đồ từ bằng chứng thu được.

Ngược lại, khi mức độ nghi ngờ còn thấp và hệ thống có yêu cầu sẵn sàng cao, có thể áp dụng kiểm soát hẹp hơn trong khi xác minh thêm. Quyết định dựa trên nguy cơ đang tiếp diễn, độ tin cậy bằng chứng và hậu quả vận hành; không đặt một thời gian chờ cố định cho mọi sự cố.

## 5. Chọn mức cô lập

| Tình huống quan sát | Phạm vi containment ban đầu có thể phù hợp | Điều kiện cần kiểm chứng |
| --- | --- | --- |
| Một tài khoản quản trị bị nghi chiếm quyền | Ngừng cấp quyền cho danh tính, kết thúc phiên liên quan, chặn credential bị lộ | Không còn phiên hoặc đường thay thế của cùng danh tính trong phạm vi |
| Một thiết bị quản trị bị xâm nhập | Chặn thiết bị tại cổng vào và phân đoạn liên quan, rà soát danh tính đã dùng trên thiết bị | Đường truy cập từ thiết bị không còn hoạt động; đội ứng cứu dùng thiết bị sạch |
| Một bastion hoặc gateway bị xâm nhập | Cô lập thành phần đó bằng điểm kiểm soát còn tin cậy, chuyển kênh ứng cứu | Không thể tới đích qua thành phần bị nghi; có khả năng quản trị độc lập |
| Một máy đích bị đối tượng điều khiển | Giới hạn các đường quản trị tới đích và đường đích có thể dùng để lan truyền | Truy cập trái phép bị chặn; kênh điều tra được giới hạn rõ |
| Chưa xác định danh tính nhưng có hoạt động gây hại đang diễn ra | Cô lập vùng hoặc tập đích theo bằng chứng và thẩm quyền khẩn cấp | Phạm vi đủ ngăn tác động, ảnh hưởng nghiệp vụ được theo dõi |

Bảng trên mô tả cách suy nghĩ, không phải bộ luật tự động. Việc mở rộng hoặc thu hẹp phạm vi phải do người chỉ huy sự cố phối hợp với chủ hệ thống quyết định theo quyền hạn đã chuẩn bị trước.

Một nguyên tắc hữu ích là chọn **phạm vi nhỏ nhất đủ ngăn nguy cơ đã quan sát**, đồng thời có điều kiện mở rộng rõ ràng nếu xuất hiện bằng chứng về đường truy cập khác. Phạm vi nhỏ nhưng bỏ sót đường vào không đáp ứng containment; phạm vi quá rộng có thể khiến đội ứng cứu mất quyền điều khiển và làm gián đoạn hệ thống không liên quan.

## 6. Chuẩn bị kênh ứng cứu trước khi tự khóa mình

### 6.1. Kênh ứng cứu phải có mức độc lập phù hợp

Trước khi chặn thành phần mà đội ứng cứu đang sử dụng, cần kiểm tra một kênh quản trị thay thế đủ tin cậy. Ví dụ là console do đội hạ tầng kiểm soát hoặc một kênh ngoài băng đã được chuẩn bị.

“Tồn tại tài khoản break-glass” chưa đủ. Cần xác minh:

- Credential khẩn cấp còn sử dụng được và được lấy qua quy trình kiểm soát.
- Thiết bị dùng để truy cập không thuộc phạm vi bị nghi xâm nhập.
- Đường mạng tới console không đi qua chính gateway sắp bị cô lập.
- Cơ chế xác thực không phụ thuộc hoàn toàn vào dịch vụ đang mất tin cậy.
- Người được chỉ định có thể thực sự tới đúng đích.
- Hoạt động khẩn cấp vẫn được ghi nhận hoặc có phương án ghi nhận thay thế được phê duyệt.

Một kênh ngoài băng về mặt mạng có thể vẫn dùng chung danh tính hoặc nền tảng quản trị với hệ thống bị sự cố. Do đó, phải xem tính độc lập theo cả mạng, danh tính và control plane.

### 6.2. Kiểm soát ngoại lệ khẩn cấp

Kênh ứng cứu không nên trở thành đường vòng không thời hạn. Mỗi ngoại lệ cần có người chịu trách nhiệm, nguồn truy cập, tập đích, quyền được phép, thời hạn và điều kiện đóng.

Nếu cơ chế ghi phiên thông thường không còn đáng tin, đội ứng cứu phải ghi lại hạn chế đó và dùng nguồn bằng chứng khác theo quy trình của tổ chức. Không coi việc thiếu recording là lý do mặc định để bỏ qua kiểm soát người sử dụng và nội dung thay đổi.

Các thao tác thử kênh ứng cứu nên là thao tác vô hại, đủ xác nhận khả năng truy cập và quyền cần thiết. Không tạo thay đổi phá hủy chỉ để chứng minh rằng quyền đặc quyền đang hoạt động.

## 7. Quy trình chặn có phối hợp

### Bước 1 — Ghi nhận sự cố và xác lập người quyết định

Mở hồ sơ sự cố với mã định danh duy nhất. Ghi thời gian theo một chuẩn thống nhất, nguồn cảnh báo, đối tượng bị nghi, tài nguyên quan trọng và hoạt động đang tiếp diễn.

Chỉ định người chỉ huy sự cố, người vận hành PAM, người quản trị danh tính, người kiểm soát mạng và chủ hệ thống đích. Một người có thể kiêm nhiều vai trò trong tổ chức nhỏ, nhưng trách nhiệm cho từng hành động vẫn phải rõ.

Hành động khẩn cấp cần tuân theo thẩm quyền đã được quy định. Ghi lại ai quyết định, căn cứ nào và phạm vi nào được cho phép, kể cả khi quy trình cho phép thực hiện trước rồi hoàn thiện hồ sơ sau.

### Bước 2 — Chụp trạng thái quan trọng nếu điều kiện cho phép

Thu thập trạng thái phiên tại PAM, gateway, bastion và các đích liên quan; ghi định danh phiên, tài khoản, nguồn, đích, thời điểm bắt đầu và thời điểm quan sát. Lưu những log và recording sẵn có bằng cơ chế được phê duyệt.

Đối với thay đổi kiểm soát, ghi lại cấu hình hiện tại đủ phục vụ so sánh và khôi phục có mục tiêu. Tránh xuất secret hoặc dữ liệu nhạy cảm không cần thiết vào hồ sơ sự cố.

Không kéo dài việc chụp trạng thái nếu điều đó để hoạt động gây hại tiếp tục. Khi phải chặn trước, ghi rõ dữ liệu nào chưa kịp thu thập và lý do.

### Bước 3 — Xác minh kênh quản trị sạch và phương án phục hồi

Đội ứng cứu xác nhận có thể sử dụng kênh độc lập đã chọn. Kiểm tra rằng thao tác chặn dự kiến không đồng thời xóa tuyến, danh tính hoặc chính sách đang bảo vệ kênh này.

Phương án khôi phục phải chỉ ra thay đổi nào có thể đảo lại, ai được phép thực hiện và bằng chứng nào cho thấy có thể làm an toàn. Khôi phục kết nối không đồng nghĩa khôi phục credential đã bị lộ hoặc tái kích hoạt một thành phần chưa đáng tin.

### Bước 4 — Ngăn tái cấp và tái kết nối

Đình chỉ cấp mới quyền đặc quyền trong phạm vi sự cố, hủy hoặc giữ lại các yêu cầu chờ phê duyệt và ngăn automation cấp lại quyền vừa bị thu hồi.

Tùy mức độ rủi ro, đồng thời áp dụng chặn tại điểm vào còn đáng tin để đối tượng không tiếp tục tạo phiên trong lúc đội ứng cứu đang kết thúc phiên cũ. Nếu các đội thực hiện song song, cần một thời điểm hiệu lực được phối hợp và một người tổng hợp kết quả.

Không đợi hoàn tất toàn bộ công việc credential mới bắt đầu chặn đường mạng khi hoạt động gây hại vẫn tiếp diễn.

### Bước 5 — Kết thúc phiên và thu hồi hiệu lực xác thực

Dùng định danh phiên và tài khoản đã đối chiếu để thực hiện kết thúc phiên tại các lớp cần thiết. Kiểm tra những phiên trên gateway dự phòng, phiên trực tiếp vào máy đích và phiên API không hiện trong giao diện PAM.

Thu hồi quyền JIT, token hoặc thông tin xác thực theo khả năng của từng nền tảng. Với credential có thể đã lộ, đưa vào kế hoạch thay thế và kiểm tra các nơi sử dụng.

Đối với session recording, bảo đảm dữ liệu ghi trước thời điểm kết thúc được lưu giữ nếu cơ chế hỗ trợ. Không xóa phiên hoặc log chỉ nhằm làm giao diện hiển thị “không còn hoạt động”.

### Bước 6 — Chặn các đường còn lại tới tài nguyên

Áp dụng kiểm soát mạng và kiểm soát trên đích để loại bỏ những đường còn mở trong phạm vi. Xét cả truy cập trực tiếp, đường từ mạng nội bộ, kênh agent và các mặt phẳng quản trị khác.

Với bastion bị nghi xâm nhập, không dựa duy nhất vào thao tác do chính bastion xác nhận. Dùng điểm kiểm soát còn tin cậy nằm bên ngoài phạm vi bị nghi, chẳng hạn cơ chế phân đoạn mạng hoặc quản trị hạ tầng độc lập phù hợp với kiến trúc.

Các thay đổi phải gắn với mã sự cố và định danh rule hoặc cấu hình. Tránh ghi đè toàn bộ bộ chính sách chỉ để chặn một luồng nếu không cần thiết.

### Bước 7 — Kiểm chứng từ nhiều điểm quan sát

Kiểm tra không thể mở phiên mới bằng đường bị chặn, các phiên cũ đã kết thúc theo mục tiêu và hệ thống đích không còn chấp nhận hoạt động qua đường đó.

Đối chiếu kết quả giữa PAM, cổng mạng và máy đích. Một thành phần bị nghi xâm nhập không được xem là nguồn duy nhất xác nhận thành công.

Nếu chưa thể kiểm tra một đường, ghi là chưa xác minh và giao người xử lý. Không đổi trạng thái đó thành “đã chặn” chỉ vì chưa thấy hoạt động mới.

### Bước 8 — Theo dõi tái kết nối và bàn giao điều tra

Giám sát những nỗ lực mở lại phiên, cấp lại quyền, sửa policy hoặc sử dụng danh tính liên quan từ nguồn khác. Nếu xuất hiện đường mới, cập nhật bản đồ và mở rộng containment trong thẩm quyền.

Bàn giao cho đội điều tra cả những trạng thái còn tồn tại trên đích. Các tiến trình đã chạy, tác vụ đã gửi hoặc thay đổi đã lưu có thể tiếp tục gây hại dù không còn đường remote access.

Trình tự trên có quan hệ phụ thuộc, nhưng không bắt buộc mọi việc phải thực hiện hoàn toàn nối tiếp. Khi tác động đang diễn ra, có thể phối hợp các lớp chặn song song sau khi đã xác định thẩm quyền, kênh ứng cứu và cách kiểm chứng.

## 8. Những đường dễ bị bỏ sót

### 8.1. Truy cập trực tiếp bỏ qua PAM

Máy đích có thể cho phép quản trị từ cả PAM proxy và một subnet quản trị khác. Nếu chỉ dừng phiên trên PAM, đường trực tiếp vẫn tồn tại.

Trong containment, đối chiếu chính sách mà máy đích và mạng thực sự thực thi. Mục tiêu dài hạn thường là đưa truy cập đặc quyền qua các đường được quản lý, nhưng trong sự cố trước mắt cần chặn ngay đường trái phép đã xác định thay vì đợi một dự án tái kiến trúc.

### 8.2. Kết nối ra ngoài do agent duy trì

Một công cụ hỗ trợ từ xa có thể duy trì kênh từ máy đích ra dịch vụ trung gian. Chặn inbound tới SSH hoặc RDP không nhất thiết ngắt kênh này.

Cần xác định nền tảng phát lệnh, danh tính agent, quyền truy cập và chính sách kết nối liên quan. Nếu phải vô hiệu hóa agent hoặc chặn đích kết nối của nó, đánh giá cả ảnh hưởng tới quan sát và quản lý hệ thống.

### 8.3. Giao thức, địa chỉ và đường dự phòng

Không giả định một rule cho một cổng và một họ địa chỉ đã bao phủ mọi đường. Máy đích có thể có nhiều interface, dịch vụ ở cổng khác hoặc được truy cập qua đường IPv4 và IPv6 khác nhau.

Gateway dự phòng hoặc chính sách được nhân bản không đầy đủ có thể tiếp tục nhận phiên. Bằng chứng áp dụng phải thể hiện phạm vi nút đã nhận thay đổi, không chỉ trạng thái của nút mà người vận hành đang mở.

### 8.4. Token và API thay cho phiên tương tác

Đối tượng có thể tiếp tục gửi thao tác quản trị qua API dù phiên desktop đã đóng. Danh tính API, token và quyền role cần được đưa vào cùng phạm vi containment nếu có liên quan.

Thu hồi quyền mới không tự thu hồi mọi tác vụ đã được hệ thống chấp nhận. Đội ứng cứu phải kiểm tra tác vụ đang chạy và thay đổi đã được lên lịch theo khả năng của nền tảng.

### 8.5. Tài khoản cục bộ và tài khoản dùng chung

Khóa danh tính tập trung không chắc đã tác động tới tài khoản cục bộ trên máy đích. Tài khoản dùng chung còn làm khó việc quy trách nhiệm và xác định phiên nào là hợp lệ.

Khi cần chặn một tài khoản dùng chung, phối hợp chủ dịch vụ để xác định tác động. Nếu không thể tách riêng người sử dụng ngay, có thể cần chặn toàn bộ đường của tài khoản đó trong phạm vi sự cố và cung cấp kênh thay thế được kiểm soát cho người hợp lệ.

## 9. Kiểm chứng containment bằng tiêu chí quan sát được

### 9.1. Ma trận kiểm chứng

| Mục tiêu | Cách kiểm chứng có kiểm soát | Bằng chứng nên lưu | Điều chưa thể kết luận từ riêng phép kiểm tra |
| --- | --- | --- | --- |
| Không mở được phiên mới | Thử từ nguồn kiểm thử được phép, tới đúng tập đích và qua đường bị chặn | Thời gian, nguồn, đích, kết quả từ điểm thực thi | Các đường chưa nằm trong phép thử cũng bị chặn |
| Phiên cũ đã kết thúc | Đối chiếu định danh phiên tại trung gian và đích | Sự kiện kết thúc, trạng thái phiên, thời điểm | Mọi tiến trình do phiên từng tạo đều đã dừng |
| Quyền không tự được cấp lại | Kiểm tra yêu cầu chờ, policy và automation liên quan | Quyết định đình chỉ, sự kiện cấp hoặc từ chối quyền | Không còn credential khác ngoài tập đã rà soát |
| Chặn mạng có hiệu lực | Quan sát quyết định tại đúng điểm kiểm soát và luồng được phép kiểm thử | Rule ID, bản cấu hình, log hoặc telemetry phù hợp | Không có API hoặc agent dùng một đường khác |
| Kênh ứng cứu còn dùng được | Thử thao tác vô hại từ thiết bị sạch qua kênh đã phê duyệt | Người thử, đường đi, đích và kết quả | Toàn bộ hạ tầng quản trị đã sạch |

Một phép thử timeout không tự chứng minh firewall đã chặn đúng. Timeout cũng có thể do lỗi định tuyến hoặc đích không hoạt động. Khi có thể, cần đối chiếu với quyết định tại điểm thực thi và tình trạng của tài nguyên đích.

Tương tự, không có log truy cập mới chỉ là một tín hiệu. Nếu pipeline log bị trễ hoặc điểm thu thập không bao phủ đường đó, sự im lặng không đủ xác nhận containment.

### 9.2. Phạm vi và thời điểm của kết luận

Kết luận tốt cần nêu được đối tượng, đường đi, thời gian và giới hạn kiểm tra. Ví dụ:

> Tại thời điểm xác minh, các phiên đã liệt kê của tài khoản quản trị bị ảnh hưởng đã kết thúc trên gateway và hai máy đích. Các phép thử được phê duyệt từ vùng nguồn liên quan không mở được phiên mới qua gateway và đường trực tiếp đã xác định. Kênh console ứng cứu vẫn hoạt động. Đường qua connector dự phòng đang chờ kiểm tra nên chưa được xác nhận.

Kết luận này hữu ích hơn câu “đã khóa tài khoản, sự cố đã được xử lý”, vì nó không trộn lẫn containment với loại bỏ nguyên nhân và phục hồi hoàn toàn.

### 9.3. Khoảng quan sát sau khi chặn

Chọn khoảng quan sát theo rủi ro, thời gian đồng bộ policy, vòng đời token, chu kỳ automation và khả năng thu thập log của hệ thống. Không có một số phút áp dụng đúng cho mọi môi trường.

Nếu chính sách đã áp dụng ở một số nút nhưng còn nút chưa xác nhận, trạng thái vẫn là chặn chưa đầy đủ đối với phạm vi đó. Đội ứng cứu cần xử lý điểm chưa có hiệu lực hoặc áp dụng lớp chặn khác đủ tin cậy.

## 10. Bằng chứng và nhật ký thay đổi

Hồ sơ containment cần giúp người khác tái dựng được điều gì đã xảy ra, vì sao có quyết định đó và hệ thống đã thay đổi như thế nào.

Mỗi hành động quan trọng nên ghi:

- Mã sự cố, người phê duyệt và người thực hiện.
- Thời điểm yêu cầu, thời điểm thực thi và thời điểm kiểm chứng, kèm múi giờ hoặc chuẩn thời gian.
- Danh tính, thiết bị, đích, session ID hoặc rule ID liên quan.
- Trạng thái trước và sau, kết quả công cụ và bằng chứng độc lập nếu có.
- Ảnh hưởng nghiệp vụ, ngoại lệ được giữ lại và thời hạn của ngoại lệ.
- Đường dẫn tới log, recording hoặc bản cấu hình được bảo quản.
- Việc còn tồn đọng, chủ sở hữu và điều kiện mở lại.

Không ghi mật khẩu, private key hoặc bearer token vào ticket. Nếu cần liên kết tới một credential, dùng định danh đối tượng trong vault hoặc tham chiếu đã được kiểm soát.

Log gốc nên được bảo quản với quyền truy cập phù hợp. Hash có thể hỗ trợ kiểm tra dữ liệu có thay đổi sau một thời điểm thu nhận, nhưng không tự chứng minh rằng dữ liệu thu nhận đã đầy đủ hoặc chính xác. Cần ghi nguồn, phương thức thu thập và chuỗi bàn giao bằng chứng theo quy trình của tổ chức.

Nếu các nguồn có lệch đồng hồ, giữ lại timestamp gốc và ghi cách hiệu chỉnh khi xây dựng timeline. Không sửa bản gốc chỉ để mọi thời điểm trông khớp nhau.

## 11. Ví dụ: tài khoản quản trị có phiên ngoài kế hoạch

### 11.1. Bối cảnh

Một hệ thống có hai máy chủ ứng dụng được quản trị qua PAM gateway. Quản trị viên dùng VPN từ máy trạm chuyên dụng. Ngoài đường chuẩn, một vùng mạng quản trị cũ vẫn có thể truy cập trực tiếp tới dịch vụ quản trị của hai máy chủ.

Đội giám sát phát hiện tài khoản quản trị đang mở phiên tới cả hai máy chủ ngoài lịch bảo trì. Chủ tài khoản xác nhận không thực hiện hoạt động đó. Có thêm bằng chứng cho thấy phiên đang thay đổi cấu hình nhạy cảm.

Người chỉ huy sự cố cho phép containment đối với tài khoản, các phiên liên quan và đường quản trị tới hai máy chủ. Một kênh console được chuẩn bị cho đội ứng cứu từ thiết bị sạch.

### 11.2. Những việc cần phối hợp

Đội PAM ngừng cấp quyền mới cho danh tính bị ảnh hưởng, đình chỉ yêu cầu chờ và ghi lại định danh các phiên. Đội danh tính khóa tài khoản theo quy trình. Đội mạng áp dụng chính sách chặn phù hợp để ngăn tái kết nối từ nguồn và qua các đường đã xác định, bao gồm đường trực tiếp từ vùng quản trị cũ.

Đội vận hành kết thúc phiên trên gateway và xác minh trạng thái đăng nhập tại hai máy đích. Những credential có thể bị lộ được đưa vào kế hoạch thay thế. Nếu một credential cũng phục vụ tác vụ tự động, chủ dịch vụ phải phối hợp thay thế và kiểm tra tác vụ đó.

Các hành động được phối hợp theo cùng hồ sơ sự cố. Khi cần thực hiện song song để ngăn tác động tiếp diễn, từng đội báo thời điểm áp dụng và kết quả cho người tổng hợp.

### 11.3. Kết quả xác minh giả định

- Hai phiên được quan sát ban đầu đã có sự kiện kết thúc trên gateway và không còn ở trạng thái đăng nhập tương ứng trên đích.
- Phép thử được phép qua đường chuẩn và đường trực tiếp đều không tạo được phiên mới trong phạm vi đã chặn.
- Kênh console ứng cứu hoạt động từ thiết bị sạch và được giới hạn cho người được chỉ định.
- Các yêu cầu cấp quyền liên quan không được tự động phê duyệt hoặc tái tạo.
- Một tác vụ đã được tạo trên máy đích trước thời điểm chặn vẫn tồn tại và được chuyển sang điều tra.

Điểm cuối cho thấy chặn remote access đã giới hạn khả năng điều khiển tiếp theo, nhưng không tự giải quyết mọi dấu vết hoặc tác động đã phát sinh trên máy đích.

## 12. Mô hình hóa hành động để tránh thao tác mù

Một kế hoạch containment nên có điều kiện trước, hành động, phép kiểm chứng và điều kiện kết thúc. Ví dụ sau chỉ minh họa cách ghi kế hoạch, không phải cấu hình của một sản phẩm PAM cụ thể và không phải lệnh triển khai:

```yaml
incident: IR-DEMO-001
objective: ngăn truy cập quản trị trái phép tới tập đích đã xác định
scope:
  identity: privileged-user-demo
  targets:
    - application-node-a
    - application-node-b
actions:
  - name: suspend-new-access
    owner: pam-operator
    verify: không còn yêu cầu hoặc policy cấp lại quyền trong phạm vi
  - name: terminate-observed-sessions
    owner: system-operator
    verify: đối chiếu định danh phiên ở trung gian và máy đích
  - name: block-remaining-paths
    owner: network-operator
    verify: kiểm tra đường chuẩn và đường trực tiếp đã kiểm kê
emergency_access:
  owner: incident-commander
  path: approved-console
  source: verified-clean-admin-device
  expiry: explicit-time-approved-in-incident-record
reopen_gate:
  - nguyên nhân liên quan đã được xử lý hoặc rủi ro còn lại được phê duyệt
  - credential bị lộ đã được thay thế theo phạm vi xác minh
  - đường truy cập được giới hạn và có khả năng giám sát
```

Khi tự động hóa một phần quy trình, cần giữ lại khả năng dừng và yêu cầu người có thẩm quyền xử lý khi kết quả không rõ. Không chuyển thẳng sang trạng thái hoàn thành chỉ vì API trả về đã nhận yêu cầu.

```text
Nếu phạm vi hoặc thẩm quyền không hợp lệ:
    dừng và chuyển người có trách nhiệm

Xác nhận kênh ứng cứu phù hợp với hành động sắp thực hiện
Ghi trạng thái quan trọng nếu điều kiện cho phép
Ngăn cấp mới hoặc tái tạo quyền trong phạm vi
Phối hợp chặn đường truy cập và kết thúc phiên
Kiểm chứng kết quả tại các điểm thực thi liên quan

Nếu có đường chưa kiểm chứng hoặc hành động thất bại:
    giữ trạng thái containment chưa đầy đủ
    giao chủ sở hữu xử lý và xem xét lớp chặn thay thế
Ngược lại:
    ghi nhận containment theo đúng phạm vi đã xác minh
    tiếp tục quan sát và bàn giao điều tra
```

Automation nên xử lý được việc chạy lại an toàn: nhận biết rule đã có, phiên đã kết thúc hoặc quyền đã bị thu hồi. Đồng thời phải tránh đảo ngược thay đổi hợp lệ của đội khác hoặc tự mở lại đường truy cập khi một bước sau thất bại.

## 13. Mở lại truy cập sau containment

### 13.1. Đặt gate mở lại theo rủi ro

Không mở lại chỉ vì người dùng báo không thể làm việc hoặc vì một khoảng thời gian cố định đã trôi qua. Cần có bằng chứng đáp ứng điều kiện khôi phục đã được đặt ra.

Các điều kiện thường cần đánh giá gồm:

- Thiết bị nguồn được xác nhận đủ tin cậy hoặc đã được thay thế bằng thiết bị sạch.
- Danh tính và các phương thức xác thực liên quan đã được xử lý theo kết quả điều tra.
- Credential bị lộ đã được thay thế tại những nơi xác minh có sử dụng.
- Bastion, gateway hoặc connector bị ảnh hưởng đã được phục hồi theo quy trình phù hợp.
- Đường trực tiếp và ngoại lệ mạng đã được xem xét, không vô tình mở lại đường vòng.
- Logging, recording, cảnh báo và khả năng kết thúc phiên đã hoạt động.
- Chủ hệ thống và người chỉ huy sự cố chấp nhận rủi ro còn lại trong phạm vi thẩm quyền.

Nếu một thành phần chưa đủ tin cậy, có thể tiếp tục dùng kênh thay thế được kiểm soát thay vì khôi phục toàn bộ mô hình cũ.

### 13.2. Mở theo từng phạm vi nhỏ

Bắt đầu bằng một danh tính đã xử lý, một thiết bị sạch, tập đích giới hạn và quyền tối thiểu. Áp dụng JIT cho thời gian thực sự cần, JEA cho tập thao tác phù hợp và theo dõi phiên đầu tiên sau khi mở lại.

Một lần mở thử thành công không tự cho phép khôi phục mọi danh tính và mọi đích. Mỗi lần mở rộng cần có căn cứ và khả năng giám sát tương ứng.

Nếu phát hiện dấu hiệu tái xâm nhập, dùng kế hoạch containment còn sẵn để chặn lại phạm vi liên quan. Phương án phục hồi nên đưa hệ thống về trạng thái an toàn đã xác định, không phục hồi mật khẩu hoặc khóa đã biết bị lộ.

### 13.3. Đóng ngoại lệ và thu hồi quyền khẩn cấp

Khi truy cập thông thường đã được khôi phục an toàn, kết thúc phiên break-glass, thu hồi quyền tạm, xử lý credential khẩn cấp theo chính sách vòng đời và đóng các rule tạm không còn cần thiết.

Đối chiếu từng ngoại lệ với người sở hữu và hồ sơ thay đổi. Không xóa toàn bộ rule có vẻ “tạm thời” nếu chưa xác định được chúng thuộc sự cố nào và còn cần thiết hay không.

## 14. Sai lầm thường gặp

**Chỉ đổi mật khẩu rồi kết luận đã cô lập.** Credential mới không tự kết thúc mọi phiên cũ. Cần kiểm tra cả phiên, token và đường mạng.

**Ngắt giao diện RDP nhưng không kiểm tra trạng thái trên đích.** Disconnect có thể để lại phiên đăng nhập. Cần phân biệt với logoff và tiếp tục kiểm tra tác vụ liên quan.

**Chỉ chặn IP nguồn trong log.** Địa chỉ đó có thể là NAT hoặc proxy, còn đối tượng có thể dùng nguồn khác. Cần kết hợp danh tính, thiết bị, phiên và phạm vi truy cập.

**Tin toàn bộ báo cáo từ bastion bị nghi xâm nhập.** Thành phần đó có thể không còn là nguồn đáng tin duy nhất. Phải kiểm chứng qua lớp kiểm soát hoặc nguồn quan sát độc lập phù hợp.

**Tắt một gateway nhưng bỏ qua nút dự phòng và đường trực tiếp.** Kiểm kê đường truy cập phải bao gồm các đường vẫn được máy đích chấp nhận.

**Chặn toàn bộ mạng quản trị trước khi kiểm tra console ứng cứu.** Đội xử lý có thể tự mất khả năng kiểm soát. Cần xác minh đường ứng cứu phù hợp với phạm vi chặn, trừ tình huống phải hành động tức thời theo thẩm quyền khẩn cấp.

**Xoay credential dùng chung mà không xác định phụ thuộc.** Dịch vụ hợp lệ có thể ngừng hoạt động trong khi phiên trái phép chưa bị kết thúc. Cần phối hợp xử lý credential và containment.

**Coi không có log mới là bằng chứng tuyệt đối.** Cần kiểm tra độ trễ, độ bao phủ và sức khỏe của pipeline log.

**Mở lại toàn bộ cấu hình cũ sau khi cảnh báo im lặng.** Điều đó có thể tái tạo chính đường bị khai thác. Mở lại phải có gate và theo phạm vi kiểm soát.

## 15. Thực hành trên mô hình lab

Xây dựng một bài tập tabletop hoặc môi trường lab cô lập với một thiết bị quản trị, một gateway, hai máy đích giả lập và một đường quản trị trực tiếp ngoài gateway. Chỉ sử dụng danh tính và credential dành riêng cho lab.

Giao tình huống: một danh tính có phiên đặc quyền không được chủ tài khoản thừa nhận, đang truy cập một trong hai máy đích. Đội thực hành phải lập kế hoạch chặn mà vẫn giữ được một kênh ứng cứu đã xác định.

Sản phẩm cần có:

1. Bản đồ đường truy cập, bao gồm đường ngoài gateway.
2. Phạm vi cô lập và lý do chọn phạm vi đó.
3. Thứ tự hoặc cách phối hợp các hành động về quyền, phiên, credential và mạng.
4. Ma trận kiểm chứng cho phiên cũ, phiên mới, đường trực tiếp và kênh ứng cứu.
5. Hồ sơ bằng chứng đã loại bỏ secret và dữ liệu nhạy cảm.
6. Điều kiện mở lại theo JIT/JEA và cách đóng quyền khẩn cấp.

Thêm một tình huống gây khó: quyền đã bị thu hồi nhưng vẫn còn phiên hoạt động; hoặc gateway báo kết thúc phiên trong khi máy đích còn tác vụ đã được tạo. Người học cần giải thích vì sao hai trạng thái này không mâu thuẫn và việc tiếp theo thuộc containment hay điều tra trên máy đích.

Không cần thực hiện hành vi xâm nhập thật để kiểm tra mục tiêu học tập. Trọng tâm là chứng minh các kiểm soát được phối hợp và kết luận dựa trên bằng chứng đúng phạm vi.

## 16. Tự kiểm tra

**Tại sao khóa tài khoản chưa đủ để chặn remote access?** Vì phiên đã xác thực, token còn hiệu lực, tài khoản cục bộ hoặc đường khác có thể tiếp tục hoạt động. Phải xác minh từng lớp liên quan.

**Khi nào cần chặn ngoài hệ thống PAM?** Khi có đường bỏ qua PAM, khi thu hồi quyền có độ trễ hoặc khi chính thành phần PAM bị nghi mất tin cậy. Điểm chặn phải nằm ở lớp còn đủ tin cậy để thực thi.

**Làm sao biết một thao tác kết thúc phiên thực sự có hiệu lực?** Đối chiếu định danh và trạng thái tại trung gian với máy đích, kiểm tra hoạt động qua đường đó và phân biệt phiên kết thúc với tiến trình đã tách khỏi phiên.

**Có nên luôn thu thập đủ bằng chứng trước khi chặn?** Không. Thu thập khi điều kiện cho phép, nhưng không kéo dài việc đó để hoạt động gây hại tiếp diễn. Ghi rõ dữ liệu chưa thu được và lý do hành động khẩn cấp.

**Bằng chứng nào cần có trước khi mở lại?** Bằng chứng xử lý các yếu tố liên quan theo phạm vi điều tra, credential phù hợp, đường truy cập được giới hạn, khả năng quan sát hoạt động và quyết định chấp nhận rủi ro còn lại.

Chặn remote access hiệu quả là kiểm soát đồng thời khả năng được cấp quyền, khả năng dùng credential, phiên đang tồn tại và đường tới tài nguyên. Mọi kết luận phải nói rõ đã chặn đối tượng nào, trên đường nào, vào thời điểm nào và còn giới hạn gì. Đó là cơ sở để đội ứng cứu tiếp tục điều tra và khôi phục truy cập đặc quyền một cách có kiểm soát.
