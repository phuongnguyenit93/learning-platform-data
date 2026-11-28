# Privileged Access Workstation — Máy trạm dành cho truy cập đặc quyền

## 1. PAW là gì?

**Privileged Access Workstation (PAW)** là máy trạm được xây dựng, quản lý và sử dụng theo một mức bảo vệ phù hợp để thực hiện công việc quản trị đặc quyền.

PAW bảo vệ điểm khởi đầu của thao tác quản trị: nơi người vận hành đăng nhập, sử dụng yếu tố xác thực, mở portal PAM, chạy công cụ quản trị và tương tác với hệ thống đích.

Một PAW không chỉ là laptop có thêm tài khoản administrator. Giá trị của nó đến từ việc giảm hoạt động không cần thiết, bảo vệ danh tính và phiên quản trị, kiểm soát phần mềm, quản lý trạng thái thiết bị và giới hạn đường truy cập.

Trong quản lý truy cập đặc quyền (PAM), câu hỏi thường được đặt ra là:

> Ai được quyền quản trị hệ thống nào, bằng cách nào và trong bao lâu?

PAW bổ sung một câu hỏi quan trọng:

> Người đó đang thao tác từ một môi trường có đủ mức tin cậy hay không?

Ví dụ, một kỹ sư có thể xác thực MFA thành công và được duyệt quyền restart dịch vụ. Nhưng nếu máy đang dùng đã bị kiểm soát, mã độc có thể tìm cách lấy token, đọc nội dung phiên hoặc thực hiện hành động qua phiên của kỹ sư.

PAW giúp giảm rủi ro đó. Nó vẫn cần kết hợp với least privilege, JIT, JEA, vault, kiểm soát phiên và giám sát hệ thống đích.

Bài học này tập trung vào mục đích, ranh giới tin cậy, kiến trúc, vòng đời và cách kiểm chứng một PAW trong luồng PAM.

## 2. PAW bảo vệ những tài sản nào?

### 2.1. Không chỉ mật khẩu

Một máy quản trị có thể tiếp xúc với nhiều tài sản nhạy cảm:

| Tài sản | Rủi ro khi bị lộ hoặc lạm dụng |
|---|---|
| Mật khẩu hoặc credential đã checkout | Có thể bị sử dụng ngoài phiên được kiểm soát |
| Private key và quyền sử dụng khóa | Có thể được dùng để giả mạo danh tính hoặc mở kết nối |
| Cookie và token | Có thể cho phép tiếp tục phiên mà không lặp lại toàn bộ MFA |
| Phiên quản trị đang mở | Người khác có thể thao tác với quyền hiện tại |
| Nội dung terminal hoặc giao diện quản trị | Có thể chứa cấu hình, thông tin hệ thống hoặc dữ liệu nhạy cảm |
| File cấu hình công cụ và context CLI | Có thể chỉ tới môi trường quan trọng hoặc chứa thông tin xác thực |
| Script, module và công cụ | Có thể trở thành phương tiện chạy mã với quyền cao |
| Log, bản xuất dữ liệu và file tạm | Có thể giữ bí mật sau khi công việc kết thúc |

Một thiết kế không cho hiển thị mật khẩu vẫn cần bảo vệ endpoint. Người kiểm soát máy trạm có thể không cần biết mật khẩu nếu họ dùng được phiên đang hoạt động.

### 2.2. MFA không làm endpoint sạch

MFA giúp chứng minh danh tính theo cơ chế được lựa chọn. Nó không tự phát hiện mọi mã độc trên máy.

Một cơ chế chống phishing có thể ngăn dùng kết quả xác thực cho một dịch vụ giả, nhưng không bảo đảm rằng mọi hành động sau đăng nhập trên endpoint bị kiểm soát đều là ý muốn của người dùng.

Tương tự, khóa được bảo vệ bằng phần cứng có thể khó bị trích xuất hơn. Tuy vậy, nếu môi trường điều khiển bị ảnh hưởng, kẻ tấn công có thể tìm cách yêu cầu sử dụng khóa hoặc điều khiển phiên trong phạm vi được phép.

Vì thế, cần bảo vệ cả yếu tố xác thực lẫn môi trường sử dụng yếu tố đó.

### 2.3. Quyền quản trị hệ thống khác quyền quản trị máy trạm

Người vận hành cần quản trị production không có nghĩa họ phải có quyền quản trị cục bộ thường trực trên PAW.

Nếu người dùng có thể tùy ý tắt bảo vệ, cài phần mềm hoặc sửa chính sách máy trạm, nhiều kiểm soát của PAW sẽ mất hiệu lực.

Công cụ cần quyền cục bộ cao nên được triển khai qua cơ chế quản lý hoặc nâng quyền có giới hạn. Phải phân biệt rõ:

- Danh tính dùng hằng ngày.
- Danh tính quản trị hệ thống đích.
- Danh tính quản lý chính PAW.
- Tài khoản hoặc dịch vụ vận hành nền tảng quản lý thiết bị.

## 3. PAW, bastion và PAM giữ vai trò khác nhau

| Thành phần | Vai trò chính | Điều không tự bảo đảm |
|---|---|---|
| PAW | Bảo vệ môi trường đầu cuối của người quản trị | Không tự cấp đúng quyền hoặc thu hồi mọi phiên đích |
| Bastion hoặc jump host | Tạo điểm trung gian cho đường quản trị | Không tự làm máy khách đầu vào trở nên đáng tin cậy |
| PAM portal và control plane | Điều phối yêu cầu, phê duyệt, cấp quyền và vòng đời | Không tự loại bỏ mã độc trên máy người dùng |
| Vault | Quản lý credential theo chính sách | Không tự ngăn mọi hành động qua một phiên đã bị chiếm |
| Gateway hoặc session proxy | Kiểm soát đường kết nối và khả năng quan sát được hỗ trợ | Không nhất thiết hiểu hoặc giới hạn được mọi thao tác của giao thức |
| Hệ thống đích | Thực thi quyền và hành động cuối cùng | Không tự biết đầy đủ bối cảnh người vận hành nếu chỉ thấy tài khoản kỹ thuật |

Một luồng tham chiếu:

~~~mermaid
flowchart LR
    A[Người quản trị và MFA] --> B[PAW được quản lý]
    B --> C[PAM: kiểm tra thiết bị, yêu cầu và phê duyệt]
    C --> D[Gateway hoặc tác vụ quản trị có giới hạn]
    D --> E[Hệ thống đích]
    F[Quản lý thiết bị, cập nhật và giám sát] --> B
    B --> G[Bằng chứng thiết bị và hoạt động]
    C --> G
    D --> G
    E --> G
~~~

Các lớp hỗ trợ nhau. Nếu người dùng có thể truy cập trực tiếp hệ thống đích từ một laptop thông thường bằng credential dài hạn, chỉ bổ sung PAW vào đường portal chưa giải quyết được đường truy cập đó.

Phải xác định và kiểm soát các đường thực sự dẫn tới quyền quản trị.

## 4. Nguyên tắc tin cậy của môi trường quản trị

### 4.1. Không dùng môi trường dễ bị ảnh hưởng để điều khiển môi trường quan trọng hơn

Một máy dùng để đọc email, mở tài liệu từ nhiều nguồn, truy cập web tùy ý và cài công cụ cá nhân có nhiều bề mặt tiếp xúc.

Nếu cùng môi trường đó giữ phiên quản trị nhạy cảm, một sự cố từ công việc thông thường có thể tác động đến quyền cao hơn.

PAW hướng tới giảm sự pha trộn này. Các hoạt động được phép nên phục vụ trực tiếp công việc quản trị và khả năng vận hành máy trạm.

Điều đó không có nghĩa cấm mọi kết nối mạng. PAW vẫn cần cập nhật, xác thực, phân giải tên, kiểm tra chứng thư, quản lý thiết bị và chuyển log qua những đường đã được kiểm soát.

### 4.2. Phân vùng theo mức tác động

Không phải mọi loại quản trị có cùng hậu quả khi bị chiếm.

Ví dụ, tài khoản có thể thay đổi IdP, CA, PAM hoặc nền tảng quản lý thiết bị có thể ảnh hưởng nhiều danh tính và hệ thống khác. Công việc hỗ trợ một ứng dụng giới hạn có phạm vi khác.

Tổ chức có thể phân vùng quản trị theo mức tác động và ranh giới tin cậy:

- Hệ thống danh tính và các thành phần quyết định tin cậy.
- Hạ tầng hoặc nền tảng.
- Ứng dụng, dịch vụ và dữ liệu thuộc phạm vi cụ thể.

Đây là cách phân loại minh họa, không phải sơ đồ bắt buộc cho mọi tổ chức.

Cần quyết định nhóm công việc nào có thể dùng chung một PAW, nhóm nào cần cách ly mạnh hơn. Không để credential của vùng nhạy cảm xuất hiện trên một môi trường được quản lý bởi vùng có mức bảo vệ thấp hơn.

### 4.3. Hệ thống quản lý PAW cũng là một tài sản đặc quyền

Nền tảng có thể đẩy phần mềm hoặc cấu hình xuống PAW có khả năng tác động tới người quản trị.

Vì vậy cần quản lý:

- Ai có thể thay baseline hoặc cài agent.
- Ai có thể điều khiển từ xa.
- Ai có thể thay trust store hoặc chính sách xác thực.
- Ai đọc được dữ liệu chẩn đoán.
- Cơ chế phê duyệt, ghi nhận và thu hồi các quyền đó.

Không bảo vệ chặt tài khoản production rồi để một tài khoản hỗ trợ thông thường điều khiển tùy ý mọi PAW.

## 5. Các mô hình triển khai và giới hạn của chúng

### 5.1. Thiết bị vật lý chuyên dụng

Một máy vật lý dành cho quản trị giúp tách công việc này khỏi môi trường hằng ngày.

Ưu điểm là ranh giới sử dụng dễ hiểu và có thể giảm phần mềm, dữ liệu không liên quan. Đổi lại, tổ chức phải quản lý thiết bị, cập nhật, dự phòng và trải nghiệm làm việc phù hợp.

“Chuyên dụng” không tự có nghĩa an toàn. Máy vẫn cần baseline, quản lý danh tính, hạn chế phần mềm và giám sát.

### 5.2. Máy quản trị từ xa hoặc VDI

Một môi trường quản trị từ xa có thể tập trung công cụ và giảm dữ liệu nằm trên client. Tuy nhiên, client vẫn có thể nhìn màn hình, nhận bàn phím và tương tác với phiên.

Nếu client bị kiểm soát, có thể có rủi ro lấy nội dung, điều khiển phiên hoặc thay đổi thao tác. Không nên mặc định truy cập VDI từ mọi máy cá nhân đều đạt mức bảo đảm của một PAW được quản lý.

Cần đánh giá cả:

- Môi trường quản trị từ xa.
- Endpoint đầu vào.
- Giao thức và cấu hình phiên.
- Clipboard, truyền file và chuyển hướng thiết bị.
- Danh tính, token và khả năng thu hồi.

### 5.3. Máy ảo quản trị trên laptop thông thường

Nếu host bị kiểm soát, nó có thể tác động đến máy ảo thông qua màn hình, đầu vào, bộ nhớ, lưu trữ hoặc thành phần ảo hóa tùy kiến trúc.

Vì vậy, đặt một VM quản trị trên host không được bảo vệ tương xứng không tự tạo ra môi trường quản trị đáng tin cậy.

Máy ảo có thể hữu ích, nhưng phải xem ai quản lý host và ranh giới cách ly thực tế.

### 5.4. Host được bảo vệ mạnh và môi trường công việc thông thường được cách ly

Một thiết kế khác đặt môi trường quản trị trên host được quản lý chặt, còn công việc ít tin cậy hơn nằm trong môi trường cách ly.

Cách này vẫn cần kiểm soát hypervisor, clipboard, ổ đĩa chia sẻ, thiết bị và việc chuyển dữ liệu. Không có mô hình ảo hóa nào tự loại bỏ mọi rủi ro chỉ bằng một tùy chọn cấu hình.

| Mô hình | Điểm cần kiểm chứng |
|---|---|
| PAW vật lý | Baseline, phần mềm, danh tính, quản lý và dự phòng |
| PAW từ xa | Mức tin cậy của cả client và môi trường từ xa |
| VM quản trị trên host thường | Khả năng host tác động tới môi trường quản trị |
| Host quản trị với vùng công việc cách ly | Ranh giới cách ly và luồng dữ liệu giữa các vùng |

Lựa chọn phải dựa trên mô hình đe dọa và yêu cầu vận hành, không chỉ chi phí thiết bị hoặc sự tiện dụng.

## 6. Baseline của một PAW

### 6.1. Nguồn triển khai và trạng thái nền

PAW cần được triển khai từ nguồn được quản trị, có cấu hình và lịch sử thay đổi kiểm soát được.

Các cơ chế như bảo vệ quá trình khởi động, mã hóa lưu trữ và kiểm tra tính toàn vẹn có thể hỗ trợ. Tuy nhiên, chúng có mục đích khác nhau:

- Bảo vệ khởi động hỗ trợ kiểm soát chuỗi khởi động theo khả năng triển khai.
- Mã hóa lưu trữ bảo vệ dữ liệu khi thiết bị hoặc ổ đĩa bị lấy trong những điều kiện tương ứng.
- Quản lý cấu hình giúp giữ baseline.
- Giám sát endpoint hỗ trợ phát hiện và phản ứng.

Mã hóa ổ đĩa không ngăn mã độc đọc dữ liệu qua một phiên đang mở. Một chỉ số “compliant” cũng không chứng minh tuyệt đối rằng máy không bị ảnh hưởng.

### 6.2. Các nhóm kiểm soát

| Nhóm | Mục tiêu thiết kế |
|---|---|
| Hệ điều hành và firmware | Duy trì phiên bản, cấu hình và cập nhật được quản lý |
| Quyền cục bộ | Hạn chế quản trị thường trực của người vận hành |
| Ứng dụng | Chỉ triển khai công cụ cần thiết và kiểm soát nguồn |
| Trình duyệt | Giới hạn extension, đồng bộ và các chức năng không phù hợp |
| Danh tính | Tách tài khoản quản trị với tài khoản công việc thường |
| Credential | Bảo vệ khóa và hạn chế bí mật tồn tại lâu trên máy |
| Mạng | Giới hạn đường quản trị và kết nối cần thiết |
| Giám sát | Quan sát trạng thái, thay đổi và tín hiệu bất thường |
| Dữ liệu | Quản lý file tạm, bản xuất, clipboard và lưu trữ |
| Phục hồi | Có thể xây dựng lại từ nguồn được tin cậy và quản lý phương tiện dự phòng |

Danh sách cụ thể phụ thuộc hệ điều hành, công cụ và môi trường. Cần ánh xạ mục tiêu sang khả năng thực thi, thay vì chỉ đặt tên các kiểm soát trong tài liệu.

### 6.3. Cập nhật và công cụ quản trị

PAW cần bản vá và công cụ tương thích. Trì hoãn cập nhật vô hạn để “giữ ổn định” có thể làm tăng rủi ro; cập nhật không kiểm thử cũng có thể làm mất đường quản trị.

Cần có vòng thử nghiệm, triển khai, theo dõi và khôi phục phù hợp. Các công cụ mới nên qua nguồn phân phối được quản trị.

Chữ ký phần mềm giúp xác minh nguồn và tính toàn vẹn theo cơ chế sử dụng, không tự chứng minh phần mềm phù hợp hoặc không có hành vi nguy hiểm. Cần quản lý cả nguồn, phiên bản, quyền và mục đích sử dụng.

## 7. Danh tính, credential và phiên trên PAW

### 7.1. Tách danh tính theo mục đích

Danh tính quản trị nên được sử dụng cho công việc đặc quyền đã xác định. Không dùng để đọc email thông thường, đăng ký dịch vụ bên ngoài hoặc đồng bộ hồ sơ cá nhân.

Việc chỉ tạo hai tài khoản trên cùng một môi trường không tự tạo ra ranh giới cách ly mạnh. Cần xem credential, phiên, quyền cục bộ và phần mềm có thể tác động lẫn nhau như thế nào.

### 7.2. Hạn chế credential lưu lâu dài

Ưu tiên đường truy cập không yêu cầu người dùng giữ bí mật dài hạn khi kiến trúc cho phép, chẳng hạn phiên qua PAM hoặc credential ngắn hạn.

Cần quản lý các vị trí dễ giữ lại bí mật:

- Lịch sử terminal.
- File cấu hình và biến môi trường.
- Script.
- Bộ nhớ công cụ hoặc agent.
- Cache của CLI.
- Trình duyệt và extension.
- Snapshot, bản sao lưu và file chẩn đoán.

Không chỉ kiểm tra có file password.txt hay không. Token và context đăng nhập cũng có thể tạo quyền truy cập.

### 7.3. MFA và khóa được bảo vệ

MFA phù hợp với rủi ro giúp bảo vệ đăng nhập và hành động nhạy cảm. Có thể sử dụng phương thức chống phishing và bảo vệ khóa bằng phần cứng theo chính sách.

Cần phân biệt:

- Thiết bị đã được đăng ký.
- Người dùng đã xác thực.
- Người dùng đã xác thực đủ mới cho hành động.
- Tài khoản có entitlement hợp lệ.
- Yêu cầu đã được phê duyệt.

Không dùng chứng thư thiết bị như bằng chứng duy nhất rằng một cá nhân cụ thể được phép quản trị.

### 7.4. Phiên có vòng đời riêng

PAW cần tự khóa khi không sử dụng và quản lý phiên đăng nhập. Nhưng khóa màn hình không tự kết thúc phiên PAM hoặc quyền trên đích.

Tương tự, đăng xuất portal không nhất thiết thu hồi mọi token hoặc phiên quản trị. Cần có quy trình kết thúc phù hợp với từng công cụ và điểm thực thi.

Không xóa dữ liệu tùy tiện để “dọn máy” nếu việc đó làm mất bằng chứng cần giữ. Việc dọn cache và dữ liệu phải theo quy trình, phạm vi và khả năng của công cụ.

## 8. Mạng, trình duyệt và chuyển dữ liệu

### 8.1. Giới hạn kết nối theo mục đích

PAW thường cần tới các dịch vụ như:

- IdP hoặc bộ xác thực.
- PAM portal, vault và gateway.
- Hệ thống quản lý thiết bị.
- Nguồn cập nhật và kho công cụ.
- DNS, thời gian và dịch vụ kiểm tra chứng thư theo kiến trúc.
- Nơi thu thập log.
- Các endpoint quản trị được phép.

Không nên coi vị trí trong mạng nội bộ là bằng chứng đủ để tin cậy. Kết nối vẫn cần xác thực và cấp quyền tương ứng.

Nếu truy cập từ xa, phải có đường mạng được bảo vệ theo chính sách. VPN có thể cung cấp một lớp kết nối nhưng không tự chứng minh endpoint khỏe hoặc người dùng đủ quyền.

### 8.2. Giảm hoạt động web không liên quan

Trình duyệt trên PAW có thể cần để dùng portal quản trị. Điều đó không có nghĩa nên dùng cùng môi trường cho email, mạng xã hội hoặc mở liên kết tùy ý.

Một profile trình duyệt riêng giúp tổ chức công việc nhưng không tự tạo ra ranh giới an toàn tương đương một môi trường cách ly.

Cần quản lý extension, đồng bộ, lưu mật khẩu, download và quyền của website theo nhu cầu. Các giao diện quản trị cũng có thể hiển thị nội dung không đáng tin cậy, nên vẫn cần bảo vệ trình duyệt và ứng dụng.

### 8.3. Đưa script và công cụ vào vùng quản trị

Sao chép một đoạn lệnh từ ticket hoặc tài liệu không được kiểm tra có thể đưa hành vi không mong muốn vào phiên đặc quyền.

Nên có đường đưa công cụ và nội dung vào PAW:

1. Xác định nguồn và mục đích.
2. Kiểm tra nội dung, phiên bản và phụ thuộc theo mức rủi ro.
3. Phân phối qua kho hoặc cơ chế được quản trị.
4. Ghi nhận thay đổi và người chịu trách nhiệm.
5. Giới hạn quyền thực thi.

Không nên dùng clipboard hoặc ổ chia sẻ không kiểm soát làm kênh phân phối mặc định cho mọi script.

### 8.4. Đưa dữ liệu ra khỏi vùng quản trị

Log, ảnh chụp màn hình và bản xuất có thể chứa thông tin nhạy cảm. Cần xác định dữ liệu nào được đưa ra, qua kênh nào và ai được nhận.

Với phiên từ xa, các chức năng clipboard, drive redirection, in và truyền file nên được quyết định theo nhu cầu. Bật toàn bộ mặc định có thể làm suy yếu ranh giới dữ liệu; tắt toàn bộ mà không có đường làm việc thay thế có thể khiến người dùng tìm cách đi vòng.

## 9. Dùng trạng thái thiết bị trong quyết định PAM

### 9.1. Device posture là một đầu vào có nguồn tin cậy

PAM có thể kiểm tra thiết bị đã được quản lý, baseline hiện hành, trạng thái giám sát hoặc tín hiệu rủi ro theo kiến trúc.

Dữ liệu cần được lấy hoặc xác minh từ nguồn đáng tin cậy, với thông tin về độ mới và liên kết tới thiết bị.

Không tin các dữ liệu như:

~~~text
Một header client tự gửi: managed-device=true
Tên máy do người dùng nhập
Một ảnh chụp màn hình chứng minh đã cài agent
User-Agent của trình duyệt
Một bản báo cáo cũ không còn gắn với phiên hiện tại
~~~

Định danh thiết bị, bằng chứng sở hữu khóa và trạng thái thiết bị là những thành phần khác nhau. Cần biết mỗi thành phần chứng minh điều gì.

### 9.2. Trạng thái thiếu hoặc quá cũ

Một trạng thái “healthy” từ lâu có thể không phản ánh máy hiện tại. Chính sách nên quy định tuổi dữ liệu, điều kiện đánh giá lại và hành vi khi không có kết quả.

Đối với quyền nhạy cảm, không nên tự coi unknown là đạt. Nếu nền tảng quản lý thiết bị lỗi, cần tuyến vận hành hoặc khẩn cấp đã định nghĩa, không cho phép mọi máy không quản lý truy cập thay thế.

Phiên đang hoạt động cũng cần chính sách riêng: khi nào phải chặn thao tác mới, yêu cầu đánh giá lại hoặc thu hồi. Không tự gia hạn quyền vô hạn vì dịch vụ posture đang không phản hồi.

### 9.3. Chính sách minh họa

Mô hình dưới đây chỉ diễn tả ý định thiết kế:

~~~yaml
privileged_workstation_access:
  scope: "production-administration"

  device:
    managed_inventory_required: true
    accepted_baseline_required: true
    recent_trusted_posture_required: true
    unknown_posture_grants_new_privilege: false

  user:
    dedicated_administrative_identity: true
    suitable_mfa_required: true
    local_admin_is_not_automatically_required: true

  access:
    use_managed_pam_route: true
    require_scoped_entitlement: true
    current_approval_if_required: true
    enforce_access_window: true

  data:
    unmanaged_credential_storage: false
    controlled_tool_and_file_transfer: true

  operations:
    protect_device_management_plane: true
    monitor_security_relevant_changes: true
    maintain_tested_recovery_workstation: true
~~~

Một thuộc tính trong cấu hình không tự tạo ra kiểm soát. Cần xác định thành phần nào xác minh, thành phần nào thực thi và bằng chứng nào chứng minh kết quả.

## 10. Quy trình làm việc tham chiếu

### 10.1. Trước khi truy cập

Người vận hành cần biết mình đang dùng đúng PAW, đúng vùng quản trị và đúng danh tính.

Luồng chuẩn có thể gồm:

- Xác nhận trạng thái thiết bị theo cơ chế được quản lý.
- Đăng nhập bằng danh tính quản trị phù hợp.
- Thực hiện MFA hoặc step-up theo chính sách.
- Chọn đúng tài nguyên và môi trường.
- Tạo yêu cầu với action hoặc role tối thiểu.
- Nhận phê duyệt nếu cần và kiểm tra cửa sổ.
- Mở phiên hoặc tác vụ qua đường được kiểm soát.

Tính đủ điều kiện của thiết bị không thay thế quyền người dùng. Một PAW hợp lệ không cho phép người sử dụng quản trị mọi hệ thống.

### 10.2. Trong lúc thao tác

Chỉ thực hiện công việc trong phạm vi đã được cấp. Nếu cần quyền rộng hơn, dùng quy trình thay đổi yêu cầu.

Cần thận trọng với:

- Nội dung copy từ nguồn bên ngoài.
- Credential xuất hiện trong output.
- Chạy công cụ ở chế độ debug có thể ghi bí mật.
- Chuyển sang tài khoản hoặc context khác ngoài ý định.
- Mở thêm phiên tới môi trường khác mà không nhận ra.
- Để phiên mở khi rời máy.

Đối với công việc có action được đóng gói hoặc JEA, nên sử dụng khả năng được cấp thay vì tìm cách lấy shell toàn quyền chỉ để tiện hơn.

### 10.3. Sau khi hoàn tất

Kết thúc phiên và quyền theo vòng đời của hệ thống. Đối chiếu yêu cầu, lease hoặc entitlement nếu quy trình yêu cầu.

Dữ liệu cần giữ phải đi vào nơi lưu bằng chứng phù hợp. File tạm hoặc bản xuất không còn cần thiết được xử lý theo chính sách dữ liệu, không để tích lũy trên PAW.

Nếu có công việc nền tiếp tục chạy, phải có danh tính, trách nhiệm và cơ chế kết thúc riêng. Không giữ một phiên tương tác đặc quyền mở vô hạn để duy trì công việc đó.

## 11. Giám sát và bằng chứng

### 11.1. Liên kết thiết bị với quyền thực tế

Một chuỗi bằng chứng hữu ích:

~~~text
Thiết bị và phiên bản baseline
    → danh tính quản trị
    → bằng chứng xác thực
    → yêu cầu và phê duyệt
    → entitlement hoặc lease
    → phiên đích hoặc action
    → kết quả và thu hồi
~~~

Các dữ liệu có thể gồm device ID, thời điểm posture, principal, request ID, session ID, tài nguyên và kết quả.

Không đưa token, cookie hoặc private key vào log để tiện đối chiếu. Bản ghi phiên hoặc output có thể chứa dữ liệu nhạy cảm và cần quyền truy cập, thời gian lưu phù hợp.

### 11.2. Những thay đổi cần quan sát

Ví dụ các sự kiện đáng chú ý:

- Tắt hoặc mất liên lạc với cơ chế bảo vệ endpoint.
- Thay đổi baseline hoặc trust store.
- Cài ứng dụng hoặc extension ngoài quy trình.
- Thêm quyền quản trị cục bộ.
- Sử dụng đường điều khiển từ xa không được phép.
- Chuyển credential hoặc dữ liệu ra ngoài phạm vi.
- Truy cập trực tiếp tới đích thay vì qua đường PAM.
- Sử dụng danh tính quản trị từ một thiết bị không được chấp nhận.
- Phiên hoặc quyền còn tồn tại sau một sự kiện thu hồi.

Một chỉ số riêng lẻ không luôn đủ để kết luận xâm nhập. Cần kết hợp bằng chứng và ngữ cảnh, nhưng không nên bỏ qua tín hiệu chỉ vì công việc đang gấp.

### 11.3. Quan sát khả năng hoạt động

Ngoài an toàn, cần theo dõi khả năng vận hành:

- Tỷ lệ PAW đạt baseline.
- Cập nhật và triển khai công cụ thất bại.
- Số lần bị chặn do posture quá cũ.
- Khả năng đăng nhập và mở phiên đúng đường.
- Thiết bị dự phòng có còn sử dụng được không.
- Thời gian xây dựng lại và khôi phục công việc quản trị.

Nếu đường chuẩn thường xuyên không dùng được, người vận hành có thể tìm đường khác. Cần sửa nguyên nhân và cung cấp tuyến dự phòng phù hợp.

## 12. Khi PAW bị mất hoặc nghi xâm nhập

### 12.1. Giới hạn tác động bằng một môi trường còn đáng tin cậy

Khi có dấu hiệu máy bị kiểm soát, không nên tiếp tục dùng chính máy đó để xử lý toàn bộ bí mật và quyền của sự cố.

Theo quy trình ứng phó, có thể cần:

- Cô lập thiết bị hoặc hạn chế kết nối.
- Thu thập và bảo vệ bằng chứng.
- Chuyển việc điều phối sang một PAW khác đủ điều kiện.
- Chặn thiết bị tiếp tục nhận quyền mới.
- Đánh giá phiên, token, chứng thư và credential liên quan.
- Xác định hệ thống đích đã được truy cập.
- Theo dõi các quyền hoặc thay đổi tồn tại trên đích.

Quyết định thu thập bằng chứng, cô lập hoặc khôi phục phải phối hợp với yêu cầu vận hành. Không tự xóa toàn bộ máy trước khi xem xét bằng chứng cần giữ.

### 12.2. Thu hồi theo phạm vi thực tế

Một PAW bị ảnh hưởng có thể liên quan tới nhiều lớp:

| Lớp | Việc cần đánh giá |
|---|---|
| Đăng nhập thiết bị | Khóa hoặc vô hiệu hóa khả năng dùng thiết bị |
| Danh tính quản trị | Trạng thái tài khoản, yếu tố xác thực và quyền |
| Portal, API và CLI | Phiên, cookie, token hoặc context đã tạo |
| PAM | Yêu cầu, lease, entitlement và phiên đang hoạt động |
| Hệ thống đích | Phiên, tài khoản, tác vụ hoặc cấu hình đã phát sinh |
| Credential | Bí mật đã tiết lộ hoặc có khả năng bị sử dụng |
| Nền tảng quản lý PAW | Khả năng thay đổi chính sách hoặc phân phối phần mềm |

Không coi khóa màn hình hoặc đổi mật khẩu là đủ để xử lý mọi lớp.

Nếu thiết bị bị mất khi đã mã hóa và tắt, mức phơi nhiễm có thể khác với mất thiết bị đang mở phiên. Cần đánh giá trạng thái thực tế; mã hóa lưu trữ không thay thế thu hồi danh tính thiết bị khi cần.

### 12.3. Xây dựng lại và khôi phục tin cậy

Sau xâm nhập, chỉ chạy một lần quét rồi tiếp tục dùng có thể không đủ cơ sở để khôi phục mức tin cậy.

Có thể cần xây dựng lại từ nguồn được quản trị, cấp lại danh tính thiết bị, xử lý khóa và xác minh baseline trước khi cho nhận quyền mới.

Nếu chính nguồn triển khai hoặc nền tảng quản lý bị ảnh hưởng, xây dựng lại từ cùng nguồn đó chưa giải quyết được vấn đề. Phải xác định lại ranh giới tin cậy và phạm vi sự cố.

Việc đưa PAW trở lại sử dụng cần có bằng chứng về nguồn, cấu hình và các bước xác minh phù hợp.

## 13. Dự phòng và break-glass

PAW là một thành phần của đường quản trị, nên cũng có thể hỏng hoặc không lấy được trong sự cố.

Cần chuẩn bị phương tiện dự phòng đáp ứng kịch bản:

- Thiết bị hoặc môi trường quản trị dự phòng được quản lý.
- Người đủ điều kiện sử dụng.
- Phương tiện xác thực còn hiệu lực.
- Công cụ và đường mạng cần thiết.
- Khả năng ghi bằng chứng khi một số hệ thống trung tâm không hoạt động.
- Quy trình kết thúc và trả thiết bị về trạng thái sẵn sàng.

Không nên giải quyết bằng cách cho phép mọi laptop cá nhân dùng tài khoản quản trị khẩn cấp. Một tuyến có mức bảo đảm thấp hơn, nếu thật sự cần, phải là ngoại lệ có thẩm quyền, phạm vi và thời hạn rõ.

Thiết bị để trong kho vẫn cần kiểm tra cập nhật, chứng thư, pin, phương tiện kết nối và khả năng đăng nhập. “Có một máy dự phòng” không đồng nghĩa đường khôi phục đã dùng được.

Diễn tập nên kiểm tra cả tình huống dịch vụ quản lý hoặc xác thực chính bị lỗi, theo phạm vi được phép.

## 14. Tình huống: vận hành production từ PAW

Một kỹ sư dùng máy hằng ngày để đọc ticket và trao đổi về sự cố. Khi cần thao tác production, kỹ sư chuyển sang PAW thuộc vùng quản trị phù hợp.

Quy trình:

1. PAW được nhận diện và có trạng thái đủ mới theo chính sách.
2. Kỹ sư dùng danh tính quản trị riêng và xác thực phù hợp.
3. Yêu cầu được giới hạn vào hai instance dịch vụ và action restart.
4. Chủ hệ thống phê duyệt cửa sổ một giờ.
5. PAM mở tác vụ hoặc phiên theo phạm vi được cấp.
6. Kỹ sư không nhận quyền quản trị cục bộ trên PAW chỉ vì đang quản trị production.
7. Một script gửi trong ticket không được chạy trực tiếp; nếu cần, nó đi qua đường kiểm tra và phân phối công cụ.
8. Sau công việc, phiên và quyền được kết thúc, bằng chứng được liên kết và dữ liệu tạm được xử lý.

Nếu máy hằng ngày bị ảnh hưởng, ranh giới sử dụng giúp giảm khả năng sự cố đó trực tiếp tiếp cận phiên và credential quản trị. Tuy nhiên, ranh giới chỉ có giá trị khi không có đường đồng bộ, điều khiển hoặc chia sẻ dữ liệu làm mất sự tách biệt đã thiết kế.

Nếu kỹ sư có thể mở cùng quyền production từ máy hằng ngày bằng một đường khác, cần xem lại phạm vi thực thi của chính sách.

## 15. Kiểm chứng trước khi đưa vào vận hành

Kiểm tra phải bao phủ thiết bị, luồng PAM và khả năng phục hồi.

| Tình huống | Kết quả cần đạt |
|---|---|
| Máy không được quản lý yêu cầu quyền đặc quyền | Bị chặn theo chính sách |
| Client tự khai trạng thái managed | Không được tin như bằng chứng hợp lệ |
| Posture thiếu hoặc quá cũ | Không tự được coi là đạt |
| PAW hợp lệ nhưng người dùng không có entitlement | Không được cấp quyền |
| Danh tính hằng ngày dùng đường quản trị nhạy cảm | Bị xử lý theo chính sách tách danh tính |
| Người vận hành cài công cụ hoặc extension ngoài quy trình | Bị chặn hoặc được phát hiện theo kiểm soát |
| Người dùng tìm cách tắt bảo vệ hoặc sửa baseline | Không có quyền tùy ý thực hiện |
| Gọi API hoặc truy cập đích trực tiếp từ máy khác | Không có đường bỏ qua ngoài phạm vi được chấp nhận |
| Chuyển script, file hoặc clipboard giữa các vùng | Áp dụng đúng ranh giới dữ liệu |
| Session đang mở khi thiết bị không còn đủ điều kiện | Xử lý đúng cơ chế đã công bố |
| Khóa hoặc đăng xuất PAW | Không bị hiểu nhầm là đã thu hồi mọi phiên đích |
| Thiết bị bị báo mất | Có thể chặn, thu hồi và theo dõi các lớp liên quan |
| Nền tảng quản lý PAW thay cấu hình | Có thẩm quyền, bằng chứng và giám sát |
| Xây dựng lại thiết bị | Có nguồn, baseline và xác minh trước khi cấp quyền |
| PAW chính không sử dụng được | Phương tiện dự phòng hoạt động trong kịch bản đã thiết kế |
| Kiểm tra log và file chẩn đoán | Không chứa credential hoặc token dùng lại ngoài kiểm soát |
| Kết thúc công việc | Quyền, phiên và dữ liệu được xử lý theo vòng đời |

PAW tạo một điểm khởi đầu được bảo vệ cho công việc đặc quyền. Để ranh giới đó có hiệu lực, tổ chức cần quản lý cả thiết bị, nền tảng điều khiển thiết bị, danh tính, công cụ, đường dữ liệu và phiên PAM; đồng thời kiểm chứng được cách khôi phục khi chính máy trạm quản trị gặp sự cố.
