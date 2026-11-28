# Mục tiêu giảm blast radius

## 1. Vì sao PAM phải quan tâm đến phạm vi thiệt hại?

Trong quản trị truy cập đặc quyền, **blast radius** là phạm vi tài nguyên, dữ liệu, chức năng và hoạt động kinh doanh có thể bị ảnh hưởng từ một sự cố ban đầu. Sự cố đó có thể là tài khoản quản trị bị chiếm dụng, credential của dịch vụ bị lộ, một phiên đặc quyền bị điều khiển hoặc một thao tác quản trị sai.

Ví dụ, một kỹ sư chỉ cần khởi động lại dịch vụ thanh toán ở môi trường thử nghiệm nhưng đang giữ tài khoản quản trị dùng chung cho toàn bộ máy chủ. Nếu tài khoản này bị đánh cắp, hậu quả có thể vượt xa dịch vụ ban đầu: kẻ tấn công sửa cấu hình production, lấy secret của cơ sở dữ liệu và can thiệp hệ thống sao lưu. Khoảng cách giữa **nhu cầu thực tế của công việc** và **quyền có thể sử dụng** chính là một nguồn làm blast radius lớn hơn.

PAM, viết đầy đủ là Privileged Access Management, giúp kiểm soát quyền truy cập đặc biệt của con người và máy móc. Một mục tiêu quan trọng của PAM là: **khi một danh tính, credential hoặc phiên bị xâm phạm, sự cố chỉ gây ảnh hưởng trong phạm vi nhỏ nhất cần thiết và có thể được khoanh vùng kịp thời**.

PAM không bảo đảm rằng sự cố sẽ không xảy ra. Thiết kế tốt phải tính cả trường hợp kẻ tấn công đã có một credential hợp lệ hoặc người vận hành đã được cấp quyền nhưng thao tác sai.

### Phân biệt hai mục tiêu liên quan

| Mục tiêu | Câu hỏi trọng tâm | Ví dụ biện pháp |
|---|---|---|
| Giảm khả năng truy cập trái phép ban đầu | Làm sao ngăn người không hợp lệ bắt đầu phiên? | Xác thực mạnh, kiểm tra thiết bị, hạn chế đường đăng nhập |
| Giảm blast radius khi sự cố xảy ra | Nếu một phiên hoặc danh tính đã bị chiếm dụng, đối tượng đó làm được gì và đi tiếp đến đâu? | Quyền theo tài nguyên, JIT/JEA, phân tách môi trường, credential riêng, chặn đường leo thang |

Một biện pháp có thể hỗ trợ cả hai mục tiêu. Tuy nhiên, chỉ tăng độ mạnh của đăng nhập mà giữ nguyên quyền quản trị toàn hệ thống sẽ chưa giải quyết đầy đủ blast radius.

## 2. Blast radius gồm những chiều nào?

Không nên chỉ đếm số máy chủ mà một tài khoản đăng nhập được. Một danh tính chỉ quản lý một hệ thống nhận dạng trung tâm vẫn có thể gây ảnh hưởng lớn nếu nó được phép cấp quyền cho mọi người khác.

| Chiều cần đánh giá | Câu hỏi phải trả lời | Ví dụ phạm vi nên giới hạn |
|---|---|---|
| Tài nguyên | Danh tính tác động được lên những tài nguyên nào? | Một cụm hoặc một ứng dụng thay vì toàn bộ hạ tầng |
| Hành động | Nó được đọc, sửa, xóa, triển khai hay cấp quyền gì? | Khởi động lại một dịch vụ thay vì mở shell quản trị |
| Dữ liệu | Nó có thể xem, xuất, sửa hoặc hủy dữ liệu nào? | Chỉ dữ liệu vận hành cần thiết cho nhiệm vụ |
| Thời gian | Quyền hoặc phiên có thể dùng trong bao lâu? | Cấp quyền cho một cửa sổ bảo trì cụ thể |
| Môi trường và tenant | Quyền có vượt sang production, tài khoản cloud khác hoặc khách hàng khác không? | Tách danh tính và chính sách theo môi trường, phạm vi khách hàng |
| Quyền gián tiếp | Nó có thể tạo danh tính khác, lấy secret, đổi policy hoặc sửa pipeline không? | Không cho phép vai trò vận hành tự cấp thêm quyền |
| Khả năng phục hồi | Nó có thể xóa bản sao lưu, tắt log hoặc phá công cụ ứng cứu không? | Tách quyền vận hành khỏi quyền quản lý bằng chứng và khôi phục |

Các chiều này phải được xem cùng nhau. Một credential chỉ sống năm phút nhưng có quyền xóa toàn bộ bản sao lưu vẫn có blast radius nghiêm trọng. Ngược lại, quyền chỉ đọc cũng có thể làm lộ dữ liệu nhạy cảm trên diện rộng.

### Phạm vi được khai báo và phạm vi thực tế

Phạm vi được khai báo là giới hạn nhìn thấy trong một role hoặc policy. Phạm vi thực tế bao gồm các đường đi mà người giữ quyền có thể tận dụng để đạt quyền mới.

Ví dụ, role mang tên `app-operator` chỉ có quyền sửa cấu hình ứng dụng. Nếu cấu hình đó cho phép thay đổi đoạn mã chạy dưới một service account có quyền đọc mọi secret, role này có đường gián tiếp đến nhiều quyền hơn tên gọi của nó. Tương tự, khả năng thay đổi thành viên nhóm quản trị, gán danh tính cho workload hoặc sửa cấu hình cấp credential có thể mở rộng blast radius.

Vì vậy, hãy đánh giá **khả năng hiệu lực**, không chỉ nhãn role hay số quyền được liệt kê.

## 3. Từ một điểm xâm nhập đến chuỗi lan rộng

Một sự cố đặc quyền thường có thể được mô tả theo chuỗi:

```text
Credential hoặc phiên bị chiếm dụng
    -> Thực hiện hành động đang được phép
    -> Tìm thêm secret, quyền hoặc quan hệ tin cậy
    -> Di chuyển sang tài nguyên khác hoặc nâng quyền
    -> Tác động lên dữ liệu và hoạt động kinh doanh
```

Không phải sự cố nào cũng đi qua đủ các bước. Một tài khoản đã có quyền rất cao có thể gây thiệt hại ngay ở bước đầu.

Xét một máy chủ ứng dụng bị xâm nhập. Nếu trên máy có credential quản trị dùng lại ở nhiều nơi, kẻ tấn công có thể sử dụng credential đó để truy cập các máy khác. Nếu máy chủ được quyền lấy secret cơ sở dữ liệu của nhiều ứng dụng từ vault, việc đưa secret vào vault chưa tạo ra ranh giới đủ hẹp: danh tính của máy vẫn được phép lấy quá nhiều secret.

Muốn giảm blast radius, cần cắt các đường đi cụ thể:

- Không tái sử dụng credential quản trị giữa các nhóm tài nguyên độc lập.
- Chỉ cho workload lấy đúng secret hoặc credential cần cho chức năng của nó.
- Không cho vai trò vận hành tự thay đổi chính sách cấp quyền của chính mình.
- Tách quyền kiểm soát ứng dụng khỏi quyền kiểm soát hệ thống nhận dạng, bản sao lưu và log bảo mật.
- Hạn chế kết nối quản trị và quan hệ tin cậy để một điểm bị chiếm dụng không tự trở thành bàn đạp sang vùng khác.

Các ranh giới cần được thực thi bằng chính sách trên hệ thống đích, cấu hình danh tính và kiểm soát kết nối phù hợp. Một quy ước đặt tên hoặc yêu cầu trong tài liệu vận hành tự nó không ngăn được truy cập.

## 4. Các cơ chế PAM làm nhỏ blast radius như thế nào?

### 4.1. Kiểm kê đặc quyền để biết cần khoanh vùng cái gì

Không thể giới hạn đầy đủ các quyền chưa được nhận diện. Kiểm kê cần bao gồm tài khoản quản trị của con người, tài khoản dịch vụ, danh tính workload, credential trong công cụ triển khai và các cơ chế truy cập khẩn cấp.

Với mỗi danh tính đặc quyền, tối thiểu cần biết:

- Chủ sở hữu và mục đích nghiệp vụ.
- Tài nguyên, môi trường, dữ liệu và hành động được phép.
- Cách xác thực, nơi lưu hoặc nơi cấp credential.
- Những đường có thể cấp thêm quyền, truy cập secret hoặc chuyển sang danh tính khác.
- Cách thu hồi, các phụ thuộc và người chịu trách nhiệm khi có sự cố.

Tài khoản không còn chủ sở hữu, credential dùng chung giữa nhiều ứng dụng hoặc quyền cấp tạm nhưng không có hạn kết thúc là những dấu hiệu cần xem xét trước. Mục tiêu không chỉ là giảm số lượng tài khoản; mục tiêu là giảm các khả năng vượt quá công việc cần thực hiện.

### 4.2. Least privilege: thu hẹp quyền thường trực

**Least privilege** là chỉ cấp các quyền tối thiểu cần thiết cho một nhiệm vụ trong phạm vi phù hợp. Với blast radius, điều này giới hạn những hành động kẻ tấn công có thể thực hiện ngay sau khi lấy được danh tính.

Ví dụ, một tác vụ kiểm tra sức khỏe ứng dụng có thể cần xem trạng thái và đọc một phần log vận hành. Nó không vì thế cần quyền sửa cấu hình mạng, đọc secret ứng dụng khác hay thêm thành viên vào nhóm quản trị.

Khi phân rã quyền, cần kiểm tra cả quyền trực tiếp lẫn quyền gián tiếp. Quyền sửa một script sẽ được chạy với quyền cao có thể tương đương khả năng thực thi mã dưới quyền cao đó. Việc chỉ loại bỏ quyền đăng nhập trực tiếp chưa chắc đã cắt đường leo thang này.

### 4.3. JIT: thu hẹp cửa sổ có đặc quyền

**Just-in-time access — JIT** là cấp quyền hoặc cho phép truy cập tại thời điểm có nhu cầu, với thời hạn rõ ràng, thay vì duy trì đặc quyền liên tục.

Một kỹ sư được phép yêu cầu role vận hành production trong 20 phút sau khi đáp ứng điều kiện truy cập. Ngoài cửa sổ đó, danh tính làm việc hằng ngày không giữ sẵn role này. Điều đó làm giảm thời gian mà credential hằng ngày có thể trực tiếp sử dụng đặc quyền.

JIT cần kiểm soát cả **khả năng yêu cầu quyền**. Nếu một danh tính bị chiếm dụng có thể tự yêu cầu mọi role, tự phê duyệt và kéo dài vô hạn, hệ thống vẫn có đường mở rộng blast radius. Tùy mức rủi ro, điều kiện cấp quyền có thể bao gồm nhiệm vụ hợp lệ, phạm vi tài nguyên, xác thực lại hoặc người phê duyệt độc lập.

Đặc biệt, phải phân biệt thời hạn của quyền với vòng đời của phiên và token. Quyền hết hạn chưa chắc làm phiên đang mở kết thúc hoặc vô hiệu hóa credential đã được sao chép. Cơ chế thực tế của hệ thống đích phải hỗ trợ việc kết thúc quyền sử dụng tại các điểm cần thiết.

### 4.4. JEA: thu hẹp điều được làm trong phiên

**Just-enough administration — JEA** giới hạn khả năng quản trị ở đúng các tác vụ cần thiết. Ví dụ, người trực vận hành được chạy thao tác khởi động lại một dịch vụ được chỉ định và xem trạng thái của nó, thay vì nhận shell quản trị toàn máy.

Giới hạn phải xét cả tham số và đường vòng. Một lệnh được cho phép nhưng nhận đường dẫn tùy ý, tải plugin tùy ý hoặc gọi tiến trình con có thể mở ra khả năng rộng hơn dự kiến. Khi dùng endpoint quản trị hạn chế, cần bảo vệ cả cấu hình endpoint và các script mà nó thực thi.

JIT trả lời “khi nào có quyền”, còn JEA trả lời “có thể thực hiện đúng những việc gì”. Kết hợp hai cơ chế giúp giới hạn đồng thời thời gian và khả năng tác động.

### 4.5. Vault và credential riêng: hạn chế secret có thể bị lấy và dùng lại

Vault giúp quản lý tập trung việc lưu, cấp và kiểm soát secret. Trong thiết kế phù hợp, người dùng có thể mở phiên qua cơ chế trung gian mà không cần biết trực tiếp mật khẩu của tài khoản đích. Điều này giảm việc sao chép credential vào máy cá nhân, tệp cấu hình hoặc hội thoại.

Tuy nhiên, vault chỉ làm giảm blast radius khi quyền lấy secret hoặc mở phiên cũng được thu hẹp. Một role đọc toàn bộ secret trong vault vẫn có phạm vi ảnh hưởng rất lớn nếu bị chiếm dụng.

Các nguyên tắc cần gắn với nhau:

- Tách credential theo ứng dụng, môi trường hoặc ranh giới quản trị có ý nghĩa.
- Cho phép mỗi danh tính truy cập đúng tập secret cần thiết.
- Dùng credential ngắn hạn hoặc cấp động nếu hệ thống đích hỗ trợ phù hợp.
- Luân chuyển credential theo chính sách và sau các sự kiện cần thu hồi.
- Kiểm tra các phụ thuộc để việc thay credential không làm gián đoạn dịch vụ ngoài dự kiến.

Luân chuyển mật khẩu không tự động thu hồi mọi phiên đã đăng nhập hoặc mọi token được phát hành từ trước. Việc thu hồi phải bao quát đúng loại credential, token, phiên và cơ chế lưu đệm liên quan.

### 4.6. Giám sát phiên: phát hiện và hỗ trợ khoanh vùng sớm

Nhật ký và ghi hình phiên có thể giúp phát hiện hành vi bất thường, xác định thao tác đã thực hiện và hỗ trợ điều tra. Khi có cơ chế phản ứng phù hợp, hệ thống có thể ngắt một phiên nghi vấn hoặc chặn yêu cầu tiếp theo để hạn chế ảnh hưởng tiếp diễn.

Ghi lại phiên tự nó không ngăn được lệnh phá hoại. Một thao tác xóa dữ liệu có thể hoàn thành trước khi người giám sát kịp phản ứng. Vì vậy, giám sát phải đi cùng giới hạn quyền, kiểm soát thao tác nguy hiểm và quy trình ứng cứu đủ nhanh.

Việc ghi nhận cũng cần có phạm vi rõ ràng: những giao thức, đường truy cập và loại thao tác nào được bao phủ? Nếu đường quản trị trực tiếp vẫn tồn tại bên ngoài PAM, chỉ quan sát các phiên đi qua PAM sẽ để lại khoảng trống.

### 4.7. Phân tách miền quản trị và bảo vệ chính PAM

Một hệ thống PAM hoặc vault có thể tập trung quyền truy cập đến rất nhiều tài nguyên. Nếu tài khoản quản trị của nền tảng này bị chiếm dụng, phạm vi ảnh hưởng có thể lớn hơn một tài khoản quản trị ứng dụng đơn lẻ.

Cần phân tách hợp lý các quyền quản lý nền tảng, sửa policy, duyệt yêu cầu, sử dụng credential và truy cập bằng chứng. Các thao tác rủi ro cao như mở rộng phạm vi secret, tắt giám sát hoặc thay đổi quyền khẩn cấp cần được kiểm soát tương xứng.

Tách môi trường chỉ có ý nghĩa khi cả danh tính, đường kết nối và quan hệ tin cậy đều phù hợp với ranh giới đó. Dùng một credential quản trị chung cho development và production có thể làm mất tác dụng của sự phân tách về tên gọi.

## 5. Ví dụ: khoanh vùng tác vụ khởi động lại dịch vụ

Giả sử hệ thống có ba ứng dụng: thanh toán, báo cáo và quản lý khách hàng. Mỗi ứng dụng có môi trường thử nghiệm và production. Nhóm vận hành cần khởi động lại dịch vụ thanh toán production khi xử lý một lỗi đã xác định.

### Trạng thái ban đầu

- Một tài khoản quản trị dùng chung được sử dụng trên các máy chủ của cả ba ứng dụng.
- Mật khẩu tồn tại trong tệp ghi chú của nhiều người trực.
- Người vận hành mở shell có quyền cao để khởi động lại dịch vụ.
- Tài khoản này có thể đọc các tệp cấu hình chứa credential kết nối cơ sở dữ liệu.
- Chưa liên kết rõ thao tác với danh tính cá nhân và nhiệm vụ vận hành.

Nếu mật khẩu bị lộ, người giữ mật khẩu có thể vượt khỏi tác vụ khởi động lại dịch vụ, dùng lại credential trên nhiều máy và tìm thêm secret. Thiệt hại tiềm tàng không còn giới hạn ở ứng dụng thanh toán.

### Thiết kế sau khi áp dụng các ranh giới

| Thành phần | Giới hạn được thiết kế | Tác dụng đối với blast radius |
|---|---|---|
| Danh tính người vận hành | Xác thực bằng tài khoản cá nhân, tách khỏi tài khoản quản trị đích | Liên kết yêu cầu và phiên với người thực hiện; hỗ trợ thu hồi đúng đối tượng |
| Phạm vi tài nguyên | Chỉ nhóm dịch vụ thanh toán production được chỉ định | Hạn chế tác động trực tiếp sang ứng dụng và môi trường khác |
| Vai trò tác vụ | Xem trạng thái và khởi động lại dịch vụ đã xác định | Giảm khả năng đọc secret, sửa tài khoản hoặc thay cấu hình tùy ý |
| Thời gian | Yêu cầu quyền cho cửa sổ 20 phút, có điều kiện cấp quyền | Giảm thời gian duy trì đặc quyền ngoài nhu cầu |
| Credential đích | Do PAM quản lý, không hiển thị cho người vận hành khi cơ chế tích hợp cho phép | Giảm cơ hội sao chép và tái sử dụng credential ngoài phiên |
| Đường truy cập | Đi qua điểm kiểm soát được giám sát; hạn chế đường quản trị thay thế | Giúp các giới hạn của PAM được áp dụng nhất quán |
| Thu hồi | Có khả năng dừng phiên và vô hiệu hóa các quyền, credential liên quan theo cơ chế của hệ thống | Hạn chế hoạt động mới sau khi phát hiện sự cố |
| Bằng chứng | Ghi nhận yêu cầu, người duyệt nếu có, phiên và thao tác; lưu tại nơi được bảo vệ | Hỗ trợ xác định phạm vi ảnh hưởng và kiểm toán |

Sơ đồ phạm vi mong muốn:

```text
Danh tính người trực
    |
    | yêu cầu hợp lệ, giới hạn 20 phút
    v
PAM / endpoint quản trị hạn chế
    |
    +-- ĐƯỢC PHÉP: xem trạng thái, khởi động lại dịch vụ thanh toán đã chỉ định
    |
    +-- BỊ CHẶN: mở shell quản trị tùy ý hoặc đọc secret ngoài nhiệm vụ
    |
    +-- BỊ CHẶN: quản trị ứng dụng báo cáo, ứng dụng khách hàng hoặc môi trường khác
```

Các dòng “bị chặn” là yêu cầu thiết kế cần được thực thi và xác minh, không phải khả năng tự động có ở mọi sản phẩm PAM.

### Rủi ro còn lại của ví dụ

Ngay cả quyền khởi động lại một dịch vụ cũng có thể gây gián đoạn, nhất là khi thao tác lặp lại hoặc thực hiện sai thời điểm. Vì thế, còn cần cân nhắc điều kiện vận hành, tần suất thao tác, khả năng chịu lỗi và cách phục hồi của ứng dụng.

Nếu endpoint giới hạn vẫn chạy trên máy đã bị kiểm soát hoàn toàn, việc không hiển thị mật khẩu cho người vận hành cũng không đồng nghĩa mọi credential trên máy đều được bảo vệ. PAM cần phối hợp với bảo vệ máy chủ, phân đoạn kết nối và kiểm soát danh tính workload.

Con số 20 phút trong ví dụ là một lựa chọn minh họa. Thời hạn thực tế phải dựa trên nhiệm vụ, hậu quả có thể xảy ra và khả năng thu hồi của hệ thống.

## 6. Áp dụng cho tài khoản dịch vụ và hạ tầng nhạy cảm

Tài khoản dịch vụ thường chạy liên tục và không có người tương tác để xác thực lại mỗi lần. Vì vậy, không nên sao chép nguyên quy trình cấp quyền dành cho con người rồi coi như đã xử lý xong.

Ví dụ, một tiến trình sao lưu cơ sở dữ liệu cần đọc dữ liệu nguồn và ghi bản sao vào kho lưu trữ được chỉ định. Nếu nó đồng thời được phép xóa toàn bộ lịch sử sao lưu, thay chính sách lưu giữ và sửa log kiểm toán, việc chiếm dụng tiến trình có thể phá cả dữ liệu lẫn khả năng phục hồi.

Thiết kế giảm blast radius có thể bao gồm:

- Gắn danh tính riêng với tác vụ và phạm vi dữ liệu cần sao lưu.
- Tách quyền ghi bản sao mới khỏi quyền thay đổi chính sách bảo vệ hoặc xóa lịch sử khi nền tảng hỗ trợ.
- Cho workload nhận credential qua cơ chế danh tính phù hợp, thay vì dùng secret quản trị chung nhúng trong mã nguồn.
- Giới hạn quyền lấy credential và khả năng gán hoặc giả lập danh tính có quyền cao hơn.
- Phối hợp luân chuyển và thu hồi với lịch chạy, cơ chế kết nối lại và yêu cầu liên tục của dịch vụ.

Đối với hạ tầng như hệ thống nhận dạng, công cụ triển khai, nền tảng ảo hóa, kho secret và hệ thống sao lưu, cần đánh giá quyền điều khiển gián tiếp. Quyền thay một pipeline triển khai có thể dẫn đến thực thi mã ở production; quyền sửa cơ chế cấp danh tính có thể ảnh hưởng đến nhiều ứng dụng cùng lúc.

Điểm cần kiểm tra không chỉ là “tài khoản này truy cập được mấy máy”, mà còn là “nó có thể thay đổi quyền của bao nhiêu danh tính và làm mất bao nhiêu khả năng phục hồi”.

## 7. Khoanh vùng sự cố: thu hồi phải khớp với loại quyền bị lộ

Khi có dấu hiệu một tài khoản đặc quyền bị chiếm dụng, thao tác khóa tài khoản là một bước quan trọng nhưng chưa chắc đủ để dừng mọi khả năng truy cập.

| Đối tượng có thể bị lộ hoặc bị chiếm dụng | Điều cần xem xét khi khoanh vùng |
|---|---|
| Mật khẩu hoặc khóa dài hạn | Vô hiệu hóa hoặc luân chuyển tại đúng hệ thống; cập nhật phụ thuộc hợp lệ |
| Phiên đang hoạt động | Khả năng ngắt phiên tại PAM và hệ thống đích; các kết nối tiếp tục tồn tại |
| Token hoặc credential ngắn hạn | Khả năng thu hồi, thời điểm hết hạn, cơ chế xác thực lại và lưu đệm |
| Quyền được cấp qua role hoặc nhóm | Loại bỏ quyền và xác định khi nào thay đổi có hiệu lực ở hệ thống đích |
| Secret thứ cấp đã được đọc | Xác định secret nào có thể đã bị lấy và thu hồi theo phạm vi liên quan |
| Danh tính hoặc quyền mới do kẻ tấn công tạo | Kiểm tra đường duy trì truy cập, thay đổi policy và các cơ chế tự cấp lại quyền |

Thời hạn ngắn giúp giảm một phần cửa sổ lạm dụng nhưng không đảo ngược thao tác đã hoàn tất. Dữ liệu đã bị xuất ra ngoài không tự trở lại an toàn khi token hết hạn. Dữ liệu bị xóa cũng cần cơ chế khôi phục riêng.

Một quy trình ứng cứu hữu ích cần liên kết được danh tính người dùng, tài khoản đích, phiên, quyền được cấp và sự kiện trên tài nguyên. Khi bằng chứng không đủ để loại trừ việc truy cập một tài nguyên, cần ghi nhận rõ mức độ chưa xác định thay vì khẳng định tài nguyên đó không bị ảnh hưởng.

## 8. Làm sao biết blast radius đã giảm?

Không thể kết luận chỉ từ số tài khoản đã đưa vào vault hoặc số phiên đã ghi hình. Cần kiểm tra các khả năng mà một danh tính bị chiếm dụng thực sự có thể sử dụng.

### 8.1. Viết mục tiêu có thể kiểm chứng

Một mục tiêu quá chung như “tăng bảo mật PAM” khó đánh giá. Một mục tiêu cụ thể hơn là:

> Nếu danh tính vận hành của ứng dụng thanh toán bị chiếm dụng, đối tượng đó chỉ có thể thực hiện tác vụ đã cấp trên nhóm tài nguyên được chỉ định trong cửa sổ cho phép; không được dùng danh tính này để lấy secret của ứng dụng khác, tự nâng quyền hoặc xóa bằng chứng trung tâm.

Mục tiêu trên phải đi kèm giả định. Chẳng hạn, hệ thống nhận dạng và điểm thực thi PAM chưa bị chiếm dụng; nếu một trong hai cũng mất kiểm soát, cần một kịch bản đánh giá khác.

### 8.2. Dùng chỉ số gắn với từng chiều ảnh hưởng

| Chỉ số hoặc bằng chứng | Ý nghĩa | Giới hạn khi diễn giải |
|---|---|---|
| Số tài nguyên và miền quản trị một danh tính có thể tác động | Đo độ rộng của quyền và quan hệ tin cậy | Một tài nguyên điều khiển trung tâm có thể quan trọng hơn nhiều máy chủ thông thường |
| Các hành động nhạy cảm có thể thực hiện | Cho thấy khả năng đọc dữ liệu, phá hủy, cấp quyền hoặc tắt bảo vệ | Cần xét tổ hợp quyền và đường leo thang gián tiếp |
| Tỷ lệ danh tính còn đặc quyền thường trực | Phản ánh cơ hội chuyển sang JIT | Chuyển sang JIT chưa bảo đảm phạm vi role đã phù hợp |
| Số danh tính hoặc tài nguyên dùng chung một credential | Cho thấy mức độ liên đới khi credential lộ | Credential riêng vẫn có thể có policy quá rộng |
| Thời gian từ phát hiện đến chặn hoạt động đặc quyền mới | Đánh giá khả năng khoanh vùng thực tế | Phải chỉ rõ loại phiên, token và hệ thống được đo |
| Các đường quản trị đi vòng PAM đã biết | Phản ánh độ bao phủ của điểm kiểm soát | Không phát hiện đường đi vòng chưa có nghĩa là không tồn tại |
| Khả năng bảo toàn log và khôi phục sau thao tác trái phép | Đánh giá sức chịu đựng của vùng bị tác động | Có bản sao lưu chưa đồng nghĩa đã khôi phục thành công |

Không nên nhân tùy ý số tài nguyên với thời gian tồn tại của quyền để công bố một phần trăm giảm rủi ro. Độ nhạy cảm dữ liệu, hậu quả nghiệp vụ, quyền gián tiếp và khả năng phục hồi không được phản ánh đầy đủ trong phép tính đơn giản đó.

### 8.3. Kiểm chứng bằng kịch bản được cho phép

Trong một môi trường kiểm thử hoặc một đợt diễn tập có phạm vi được phê duyệt, có thể xây dựng các tình huống sau để đánh giá ranh giới:

| Tình huống kiểm chứng | Kết quả mong đợi | Bằng chứng cần giữ |
|---|---|---|
| Thực hiện tác vụ được giao trên đúng tài nguyên | Thành công theo điều kiện cấp quyền | Yêu cầu truy cập, quyền hiệu lực, sự kiện thực thi |
| Dùng cùng danh tính để truy cập ứng dụng hoặc môi trường khác | Bị từ chối tại điểm thực thi phù hợp | Sự kiện từ chối và policy liên quan |
| Tìm cách lấy secret ngoài phạm vi hoặc tự gán role cao hơn | Bị từ chối, có dấu vết truy vết | Nhật ký truy cập secret hoặc thay đổi quyền |
| Quyền hết hạn hoặc bị thu hồi khi còn phiên hoạt động | Hành vi phù hợp với mục tiêu đã công bố cho từng loại phiên | Mốc thời gian, trạng thái phiên và thao tác sau thu hồi |
| Danh tính vận hành cố thay đổi log hoặc chính sách sao lưu | Không vượt qua ranh giới quản trị đã đặt | Sự kiện từ chối, cấu hình bảo vệ liên quan |

Bảng này mô tả cách đánh giá thiết kế, không phải tuyên bố các kiểm thử đã được thực hiện. Nếu kết quả thực tế khác mong đợi, cần ghi lại đường vượt ranh giới và điều chỉnh kiểm soát trước khi coi mục tiêu đã đạt.

## 9. Những cách hiểu dễ dẫn đến blast radius lớn

### “Đã có MFA thì không cần thu hẹp quyền”

MFA làm mạnh thêm xác thực nhưng không tự hạn chế hành động sau đăng nhập. Phiên hợp lệ bị chiếm dụng hoặc người quản trị thao tác sai vẫn có thể gây hậu quả trong toàn bộ phạm vi quyền đang có.

### “Mọi secret ở trong vault là đã được khoanh vùng”

Nếu một role được đọc toàn bộ secret, việc chiếm role đó vẫn có thể mở đường đến nhiều hệ thống. Cần thu hẹp quyền sử dụng vault và bảo vệ tài khoản quản trị vault.

### “Credential hết hạn nhanh thì tác động chắc chắn nhỏ”

Một hành động nguy hiểm có thể hoàn tất rất nhanh. Phải giảm cả quyền được phép và tài nguyên có thể tác động, đồng thời hiểu vòng đời phiên, token và khả năng thu hồi thực tế.

### “Có ghi hình phiên là đủ ngăn hành vi xấu”

Ghi hình hỗ trợ quan sát và điều tra. Muốn hạn chế thiệt hại còn cần giới hạn thao tác, phát hiện phù hợp và phản ứng có hiệu lực trên hệ thống đích.

### “Chỉ cần chặn đăng nhập trực tiếp của con người”

Credential của dịch vụ, pipeline triển khai, workload và các tích hợp quản trị cũng có thể là đường đặc quyền. Nếu những đường này vẫn dùng quyền rộng, blast radius vẫn lớn.

### “Tài khoản khẩn cấp có thể dùng chung cho mọi việc”

Truy cập khẩn cấp cần đủ khả năng phục hồi hệ thống trong tình huống đã dự kiến, đồng thời có điều kiện sử dụng, giám sát, trách nhiệm rõ ràng và xử lý credential sau sử dụng. Một đường khẩn cấp thường trực, ít được quan sát và có quyền quá rộng có thể phá vỡ các giới hạn của luồng truy cập thông thường.

## 10. Tình huống tự luyện

Một công ty có tài khoản dịch vụ `deploy-prod` dùng chung cho năm ứng dụng. Credential được lưu trong vault, tự luân chuyển định kỳ và được pipeline lấy khi triển khai. Tài khoản có quyền cập nhật ứng dụng, đọc tất cả secret production và sửa danh sách thành viên nhóm quản trị. Các phiên đăng nhập của con người đều được ghi nhận qua PAM.

Hãy phân tích:

1. Nếu một pipeline bị chiếm dụng, những tài nguyên và danh tính nào có thể bị ảnh hưởng?
2. Vault và luân chuyển credential đã giải quyết phần nào của vấn đề? Những quyền nào vẫn làm blast radius lớn?
3. Việc ghi nhận phiên của con người có bao phủ hành vi của pipeline hay không?
4. Nếu chỉ tách `deploy-prod` thành năm tài khoản nhưng giữ nguyên quyền đọc mọi secret và sửa nhóm quản trị, ranh giới đã thay đổi đến đâu?
5. Cần những bằng chứng nào để kết luận một pipeline chỉ triển khai được đúng ứng dụng của nó?

Gợi ý phân tích: bắt đầu từ đường cấp credential, quyền hiệu lực trên ứng dụng, quyền truy cập secret và khả năng thay đổi danh tính. Ưu tiên cắt đường tự nâng quyền, giới hạn credential và role theo từng phạm vi triển khai, đồng thời bảo vệ nơi sửa mã pipeline và chính sách cấp credential. Việc tách tài khoản chỉ có giá trị khoanh vùng khi policy và quan hệ tin cậy cũng được giới hạn tương ứng.

## 11. Ghi nhớ khi thiết kế PAM

Giảm blast radius nghĩa là thiết kế cho tình huống một điểm đặc quyền đã bị mất kiểm soát. Với mỗi tài khoản, workload hoặc phiên, cần trả lời được bốn câu hỏi: **tác động được vào đâu, làm được gì, trong bao lâu và có thể đi tiếp bằng đường nào**.

Least privilege và JEA giới hạn khả năng hành động; JIT giới hạn cửa sổ sử dụng; vault cùng quản lý vòng đời credential giảm khả năng lộ và tái sử dụng secret; giám sát cùng thu hồi hỗ trợ khoanh vùng sự cố. Các cơ chế này cần được gắn với ranh giới tài nguyên, môi trường, danh tính và khả năng phục hồi.

Một thiết kế PAM đạt mục tiêu khi có bằng chứng cho thấy tác vụ hợp lệ vẫn thực hiện được, các đường vượt phạm vi bị kiểm soát và đội ứng cứu biết cách dừng khả năng truy cập còn tồn tại khi sự cố xảy ra.
