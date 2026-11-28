# Tài khoản theo tier hệ thống

## 1. Vì sao cần chia tài khoản đặc quyền theo tier?

Trong PAM — Privileged Access Management, **tier quản trị** là một lớp phân tách quyền kiểm soát và quan hệ tin cậy giữa các nhóm hệ thống. Tài khoản theo tier là tài khoản hoặc ngữ cảnh đặc quyền chỉ được sử dụng trong phạm vi quản trị phù hợp với lớp đó.

Mục tiêu là tránh để việc chiếm dụng một hệ thống ở phạm vi thấp hơn trở thành đường lấy credential hoặc sử dụng quyền quản trị của một phạm vi có ảnh hưởng lớn hơn.

Ví dụ, một kỹ sư vừa quản trị máy trạm nhân viên vừa quản trị hệ thống nhận dạng trung tâm. Nếu dùng cùng một tài khoản toàn quyền để đăng nhập cả hai nơi, máy trạm bị xâm nhập có thể trở thành nơi làm lộ hoặc lạm dụng ngữ cảnh quản trị hệ thống nhận dạng. Sự cố từ một đầu cuối khi đó có khả năng lan sang nhiều hệ thống.

Phân tier cần trả lời đồng thời:

- Tài khoản này thực sự kiểm soát được những hệ thống nào?
- Nó được phép sử dụng trên tài nguyên và từ môi trường quản trị nào?
- Credential, token hoặc phiên của nó có thể bị lộ ở đâu?
- Những nền tảng nào có thể thay đổi hoặc chiếm quyền của nó?
- Có đường gián tiếp nào vượt qua ranh giới giữa các tier?

Việc tạo các tên như `admin-t0`, `admin-t1` và `admin-t2` chỉ là cách biểu diễn. Ranh giới chỉ có giá trị khi được thực thi bằng quyền, điều kiện đăng nhập, bảo vệ credential, môi trường quản trị và các cơ chế kiểm soát liên quan.

## 2. Tier quản trị khác những cách phân loại nào?

| Cách phân loại | Câu hỏi chính | Vì sao không thể dùng thay hoàn toàn cho tier quản trị? |
|---|---|---|
| Mức quan trọng nghiệp vụ | Hệ thống ngừng hoạt động hoặc mất dữ liệu gây hậu quả gì? | Một hệ thống nhỏ nhưng có quyền cấp danh tính cho nhiều hệ thống vẫn có ảnh hưởng kiểm soát lớn |
| Development, staging, production | Tài nguyên thuộc giai đoạn hoặc môi trường vận hành nào? | Production có nhiều lớp quản trị; công cụ ngoài production vẫn có thể có quyền tác động production |
| Các lớp giao diện, ứng dụng, dữ liệu | Thành phần thực hiện chức năng gì trong kiến trúc phần mềm? | Đây là phân lớp chức năng, không mô tả đầy đủ quyền điều khiển và credential |
| Cấp hỗ trợ hoặc cấp bậc nhân sự | Ai xử lý loại yêu cầu nào? | Chức danh và thâm niên không quyết định một danh tính được phép kiểm soát hệ thống nào |
| Nhãn role trên một sản phẩm | Tập quyền trong phạm vi sản phẩm là gì? | Một role có thể có đường gián tiếp sang sản phẩm hoặc miền quản trị khác |
| Tier quản trị | Ai hoặc thành phần nào có thể kiểm soát, cấp quyền hoặc chiếm dụng thành phần nào? | Cần được xây dựng từ quan hệ quyền thực tế |

Hai hệ thống có cùng mức quan trọng nghiệp vụ chưa chắc cùng tier quản trị. Ngược lại, hai hệ thống khác chức năng có thể cần cùng mức bảo vệ nếu một hệ thống có khả năng trực tiếp chiếm quyền của hệ thống còn lại.

Cũng cần tách **tier** khỏi **phạm vi ngang**. Hai tài khoản cùng tier vẫn có thể thuộc các khách hàng, môi trường hoặc vùng mạng khác nhau và không được phép truy cập lẫn nhau.

## 3. Một mô hình ba tier để hiểu nguyên tắc

Có thể dùng mô hình minh họa sau để học cách phân tách. Đây không phải quy ước đánh số bắt buộc cho mọi tổ chức hoặc mọi nền tảng.

| Tier minh họa | Phạm vi kiểm soát | Ví dụ cần đánh giá |
|---|---|---|
| Tier 0 | Cơ chế nhận dạng, cấp quyền hoặc nền tảng có thể chiếm quyền quản trị cao nhất trong miền đang xét | Hệ thống nhận dạng trung tâm, quyền quản trị gốc, nền tảng nắm credential hoặc khả năng điều khiển tương đương |
| Tier 1 | Máy chủ, ứng dụng và hạ tầng vận hành trong phạm vi đã xác định | Máy chủ ứng dụng, cơ sở dữ liệu, nhóm tài nguyên và thiết bị hạ tầng không có đường kiểm soát Tier 0 |
| Tier 2 | Máy trạm và các đầu cuối người dùng trong phạm vi đã xác định | Thiết bị nhân viên, công cụ hỗ trợ đầu cuối, tài khoản quản trị cục bộ phục vụ hỗ trợ |

Trong bài này, “tier cao hơn” chỉ lớp có khả năng kiểm soát nhạy cảm hơn; theo cách đánh số minh họa, Tier 0 cao hơn Tier 1 và Tier 2. Không nên suy thứ bậc chỉ từ con số nếu tổ chức sử dụng quy ước khác.

### Không phân tier chỉ theo loại máy hoặc nhãn sản phẩm

Một máy chủ thông thường thuộc Tier 1 trong sơ đồ ban đầu có thể cần được bảo vệ như Tier 0 nếu nó thực sự có quyền điều khiển hệ thống nhận dạng Tier 0.

Tương tự:

- Nền tảng ảo hóa có thể điều khiển máy ảo nhận dạng cần được đánh giá theo khả năng kiểm soát đó.
- Hệ thống sao lưu có thể khôi phục hoặc thay đổi thành phần nhận dạng nhạy cảm cần được xem xét về quyền và đường phục hồi.
- Hệ thống triển khai có thể chạy mã trên tài nguyên Tier 0 có quan hệ tin cậy rất khác với một công cụ chỉ triển khai ứng dụng thông thường.
- Thành phần quản lý chứng thư hoặc khóa có thể cấp, sử dụng hoặc thay đổi cơ chế xác thực nhạy cảm cần được đánh giá theo phạm vi tác động thực tế.
- Một hệ thống log chỉ nhận sự kiện không tự động có quyền quản trị toàn bộ nguồn gửi log. Tuy vậy, quyền sửa hoặc xóa bằng chứng vẫn cần bảo vệ tương xứng.

Không phải mọi hypervisor, kho sao lưu, công cụ triển khai hay nền tảng chứng thư đều tự động thuộc Tier 0. Cần xét quyền hiệu lực, cấu hình, đối tượng được quản lý và đường tác động cụ thể.

### Tier trong cloud và môi trường lai

Trong cloud, các ranh giới có thể nằm ở tổ chức, tenant, tài khoản, dự án, subscription, nền tảng danh tính hoặc hệ thống quản lý tập trung. Không nên chỉ sao chép nhãn tier của một môi trường máy chủ truyền thống rồi coi như đã bao phủ mọi quyền.

Một tài khoản không có quyền đăng nhập hệ điều hành vẫn có thể cấp role quản trị cloud, gán danh tính cho workload hoặc thay chính sách tin cậy. Đây là các khả năng phải có trong mô hình tier.

## 4. Phân tier từ quan hệ kiểm soát

Cách tiếp cận hữu ích là lập quan hệ giữa danh tính, nền tảng quản trị, credential và tài nguyên.

```text
Một thành phần có thể:
    - Cấp hoặc sửa quyền của thành phần khác
    - Thực thi mã với quyền cao trên thành phần khác
    - Đọc hoặc sử dụng credential của thành phần khác
    - Thay đổi trạng thái tin cậy hoặc cơ chế phục hồi của thành phần khác
        -> Cần đánh giá nó như một đường kiểm soát
```

Ví dụ:

```text
Máy quản trị nền tảng A
    -> điều khiển hypervisor B
        -> có khả năng tác động máy nhận dạng C
            -> C cấp quyền cho nhiều hệ thống
```

Nếu các khả năng trên thực sự cho phép chiếm quyền quản trị C, thì A và B không thể được bảo vệ như các thành phần thấp hơn chỉ vì tên hoặc chức năng ban đầu. Có hai hướng chính: tăng mức bảo vệ tương ứng, hoặc thay đổi kiến trúc để loại bỏ hay giới hạn đường kiểm soát đó bằng một ranh giới được thực thi.

Không phải mọi kết nối mạng hoặc phụ thuộc chức năng đều tương đương quyền kiểm soát. Ứng dụng gọi dịch vụ xác thực không vì thế tự quản trị được dịch vụ xác thực. Cần đánh giá hành động, credential, điều kiện và cơ chế tin cậy thay vì chỉ vẽ đường kết nối.

### Những đường gián tiếp dễ bị bỏ sót

- Sửa script hoặc template được chạy với quyền cao ở tier khác.
- Thay thành viên nhóm, policy hoặc điều kiện kích hoạt role.
- Đặt lại mật khẩu, yếu tố xác thực hoặc phương thức khôi phục của tài khoản ở tier khác.
- Đọc kho secret, khóa hoặc token của nhiều tier.
- Điều khiển máy trung gian, máy quản trị hoặc nơi giữ phiên đặc quyền.
- Quản lý bản sao lưu, ảnh máy hoặc cấu hình có thể được phục hồi vào hệ thống cao hơn.
- Tạo hoặc sử dụng danh tính workload có quyền trên hệ thống nhạy cảm hơn.

Kết quả phân tier phải phản ánh các đường có thể sử dụng trong thực tế, kể cả khi tài khoản không có nhãn “quản trị cấp cao”.

## 5. Tách tài khoản và ngữ cảnh sử dụng

### 5.1. Một người có thể cần nhiều tài khoản hoặc ngữ cảnh

Một kỹ sư có nhiệm vụ ở nhiều tier không nên mặc nhiên dùng cùng một principal đặc quyền cho mọi nơi. Có thể dùng tài khoản riêng theo tier, role tạm thời hoặc kết hợp các cơ chế mà nền tảng hỗ trợ.

Ví dụ minh họa:

| Ngữ cảnh | Mục đích | Phạm vi |
|---|---|---|
| Danh tính làm việc thông thường | Đọc tài liệu, trao đổi, công việc không cần đặc quyền | Không giữ sẵn quyền quản trị nhạy cảm |
| Quản trị đầu cuối | Hỗ trợ máy trạm được giao | Tier 2 và phạm vi đầu cuối tương ứng |
| Quản trị ứng dụng | Vận hành nhóm máy chủ hoặc ứng dụng được giao | Tier 1 trong miền tài nguyên xác định |
| Quản trị nhận dạng | Quản lý cơ chế cấp quyền trung tâm | Tier 0 theo policy và nhiệm vụ được giao |

Không phải ai cũng cần đủ bốn ngữ cảnh. Chỉ cấp những quyền có nhu cầu thực tế; số lượng tài khoản không phải mục tiêu tự thân.

Mỗi principal cần liên kết với người sử dụng, chủ sở hữu quyền, mục đích và vòng đời. Các tên tài khoản trong tài liệu quản lý chỉ giúp nhận diện; không phải cơ chế bảo mật.

### 5.2. Không dùng credential của tier cao trên hệ thống thấp hơn

Nếu một máy trạm có mức bảo vệ thấp hơn đã bị kiểm soát, việc nhập mật khẩu, nhận token hoặc mở phiên đặc quyền cao từ máy đó có thể tạo cơ hội lấy hoặc lạm dụng ngữ cảnh quản trị.

Vì vậy, không chỉ cấm đăng nhập tài khoản Tier 0 vào một máy chủ Tier 1. Cần xét cả nơi người quản trị khởi tạo phiên, máy trung gian, credential được đưa vào đâu và những phiên nào còn tồn tại.

Các trường hợp cần tránh gồm:

- Đăng nhập tài khoản quản trị nhận dạng trên máy trạm dùng cho thư điện tử và công việc thường ngày.
- Dùng tài khoản tier cao để cài phần mềm hoặc xử lý lỗi ở hệ thống thấp hơn.
- Lưu khóa hoặc token tier cao trong công cụ trên máy thấp hơn.
- Dùng lại mật khẩu giữa các tài khoản thuộc tier khác nhau.
- Cho trình quản lý credential hoặc công cụ triển khai của tier thấp đọc secret tier cao.

Nếu cần vận hành hệ thống thấp hơn, người quản trị sử dụng tài khoản hoặc role phù hợp với phạm vi thấp hơn qua đường đã được thiết kế, thay vì đưa credential cấp cao vào đó.

### 5.3. Role tạm thời không xóa rủi ro của môi trường sử dụng

Một danh tính cá nhân có khả năng yêu cầu quyền Tier 0 vẫn là một đường nhạy cảm, dù role chỉ được cấp theo JIT. Cần bảo vệ cả điều kiện yêu cầu, xác thực lại, quyền phê duyệt và môi trường tạo phiên.

Nếu một máy thấp hơn có thể tự do kích hoạt role cao hơn mà không có ràng buộc phù hợp, ranh giới tier vẫn có thể bị vượt qua.

## 6. Môi trường và đường quản trị theo tier

Tách tài khoản nhưng dùng tất cả trên cùng một hệ điều hành đã bị xâm nhập có thể không đạt mục tiêu. Môi trường quản trị phải đủ tin cậy cho những credential và phiên mà nó xử lý.

| Thành phần | Điều cần xác định |
|---|---|
| Thiết bị quản trị | Được phép thực hiện tác vụ của tier nào; mức bảo vệ có phù hợp không |
| Máy trung gian hoặc endpoint quản trị | Ai điều khiển, phiên và credential đi qua đâu |
| Giao diện truy cập | CLI, web, API, console và các đường thay thế |
| Nguồn kết nối | Thiết bị hoặc vùng nào được phép khởi tạo truy cập |
| Kho credential | Role nào có thể đọc hoặc sử dụng credential của từng tier |
| Nền tảng hosting | Có thành phần thấp hơn nào điều khiển được máy quản trị cao hơn không |
| Cơ chế phục hồi | Khi một thành phần lỗi, đường dự phòng có giữ đúng ranh giới không |

Có thể sử dụng thiết bị quản trị chuyên dụng hoặc môi trường cách ly đủ phù hợp với mô hình đe dọa. Chỉ đổi trình duyệt, dùng cửa sổ riêng tư hoặc mở một phiên máy ảo không tự tạo ranh giới tin cậy nếu hệ điều hành hay nền tảng hosting bên dưới có thể điều khiển ngữ cảnh cao hơn.

Một máy trung gian Tier 0 được đặt trên hạ tầng mà quản trị viên Tier 1 có thể tùy ý sửa hoặc đọc trạng thái sẽ tạo quan hệ kiểm soát ngược cần xử lý.

### Đường quản trị hợp lệ không đồng nghĩa mọi kết nối đều hợp lệ

Một hệ thống cao hơn có thể cần thực hiện chức năng quản lý đối với hệ thống thấp hơn. Điều đó không có nghĩa phải đăng nhập bằng credential quản trị của chính nền tảng cao hơn vào từng hệ thống đích.

Ví dụ, nền tảng PAM có thể sử dụng credential đích dành cho một nhóm máy chủ, trong khi quyền quản trị nội bộ của PAM không được chuyển vào phiên trên các máy chủ đó. Cần phân biệt principal quản trị nền tảng với principal dùng để thực hiện tác vụ ở đích.

Luồng thu thập log hoặc truy vấn trạng thái cũng cần quyền đúng mục đích. Nó không nên trở thành một kênh cấp quyền ngược không được kiểm soát.

## 7. Kết hợp tier với phạm vi ngang

Phân tier giải quyết một chiều của đặc quyền. Vẫn cần phân tách giữa các ứng dụng, môi trường, khách hàng và vùng trách nhiệm.

Một tài khoản Tier 1 không vì thế được quản trị tất cả máy chủ của tổ chức. Hai nhóm ứng dụng cùng tier có thể cần credential, role và đường triển khai riêng.

| Chiều giới hạn | Ví dụ |
|---|---|
| Tier | Quản trị ứng dụng không được sửa hệ thống nhận dạng trung tâm |
| Môi trường | Tài khoản development không có quyền triển khai production |
| Ứng dụng hoặc dịch vụ | Người trực ứng dụng A không mặc nhiên quản trị ứng dụng B |
| Khách hàng hoặc tenant | Quyền của tenant A không áp dụng sang tenant B |
| Khu vực hoặc site | Người bảo trì một chi nhánh chỉ có phạm vi được giao |
| Tác vụ | Xem trạng thái khác với sửa cấu hình hoặc tạo tài khoản |
| Thời gian | Quyền chỉ có hiệu lực trong cửa sổ công việc cần thiết |

Nếu một pipeline development có quyền sửa production, thì việc tách nhãn môi trường chưa tạo ra ranh giới thực tế. Tương tự, credential dùng lại giữa hai tenant có thể làm suy yếu sự phân tách dù cả hai cùng tier.

## 8. Vai trò của PAM trong thực thi ranh giới

### 8.1. Kiểm kê và phân loại quyền hiệu lực

PAM cần có thông tin về tài khoản, người hoặc workload sử dụng, tier, phạm vi tài nguyên, credential và các đường quản trị. Cần xét cả quyền cấp thêm quyền và quyền sử dụng danh tính khác.

Một role được xếp Tier 1 trên giấy nhưng có thể đọc credential Tier 0 phải được điều tra và xử lý. Không nên chỉ đổi nhãn để che đi một đường kiểm soát chưa được giới hạn.

### 8.2. Least privilege và JEA

**Least privilege** giới hạn quyền theo nhu cầu. **JEA — just-enough administration** giới hạn khả năng quản trị ở đúng tác vụ.

Bên trong từng tier, vẫn cần xác định những thao tác được phép. Người có quyền Tier 1 để khởi động lại một dịch vụ không tự cần quyền mở shell tùy ý trên mọi máy chủ Tier 1.

Tương tự, quản trị viên có nhiệm vụ xử lý một thành phần Tier 0 không mặc nhiên cần quyền thay toàn bộ policy của miền nhận dạng.

### 8.3. JIT và khả năng yêu cầu quyền

**JIT — just-in-time access** giảm thời gian tồn tại của đặc quyền. Cần gắn việc yêu cầu quyền với tier, tài nguyên, nhiệm vụ, nguồn truy cập và điều kiện phê duyệt phù hợp.

JIT không thay thế ranh giới tier. Một role cao được cấp ngắn hạn từ môi trường không phù hợp vẫn có thể bị lạm dụng trong thời gian đó. Quyền hết hạn cũng chưa chắc kết thúc phiên hoặc token đã được phát hành.

### 8.4. Vault và quản lý credential theo ranh giới

Credential của từng tier cần được bảo vệ bằng policy phù hợp. Người dùng hoặc công cụ quản trị tier thấp không nên có khả năng đọc, sử dụng hoặc tự cấp quyền lấy credential tier cao.

Một số điểm cần xem xét:

- Tách phạm vi credential và quyền quản trị policy có ý nghĩa.
- Tránh tái sử dụng secret giữa các tier và các miền độc lập.
- Hạn chế hiển thị credential cho người dùng khi cơ chế tích hợp cho phép.
- Quản lý luân chuyển cùng các phụ thuộc và khả năng phục hồi.
- Bảo vệ bản sao lưu, khóa bảo vệ và quyền quản trị của vault.
- Xem cả credential cấp động, token và khả năng cấp lại quyền.

Chia thành nhiều thư mục trong vault chưa đủ nếu cùng một role vẫn được đọc tất cả hoặc có thể sửa policy để tự mở rộng quyền.

Nền tảng PAM quản lý credential rất mạnh có thể trở thành một phần nhạy cảm của miền kiểm soát cao. Tuy nhiên, cần phân loại từng thành phần, đường dữ liệu và quyền quản trị theo khả năng thực tế; không nhất thiết mọi dữ liệu vận hành của PAM đều có cùng mức ảnh hưởng.

### 8.5. Giám sát và phát hiện vượt ranh giới

Các tín hiệu cần xem xét gồm:

- Tài khoản tier cao đăng nhập từ môi trường không được phép.
- Tài khoản tier thấp yêu cầu secret, role hoặc tài nguyên tier cao.
- Thay đổi policy cho phép vượt tier.
- Tạo token, nhóm hoặc đường tin cậy mới mở rộng phạm vi.
- Một công cụ triển khai thấp hơn bắt đầu tác động tài nguyên cao hơn.
- Sự kiện tại đích không có phiên hoặc yêu cầu tương ứng trong đường PAM dự kiến.

Ghi nhận giúp phát hiện và điều tra, nhưng không thay thế việc chặn các hành động ngoài phạm vi. Cần có điểm thực thi và khả năng phản ứng phù hợp.

## 9. Kiểm kê một tài khoản theo tier

Một hồ sơ nên mô tả cả tier được thiết kế và các bằng chứng về quyền hiệu lực.

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| Chủ thể | Người nào hoặc workload nào sử dụng? |
| Principal | Tài khoản hoặc role nào, trong miền danh tính nào? |
| Tier được phân loại | Dựa trên khả năng kiểm soát nào? |
| Tài nguyên và tác vụ | Được làm gì, ở đâu, trong môi trường nào? |
| Nguồn truy cập | Được dùng từ thiết bị hoặc ngữ cảnh quản trị nào? |
| Credential và phiên | Được cấp, lưu, sử dụng và thu hồi ra sao? |
| Quyền gián tiếp | Có thể sửa policy, script, nhóm, bản sao lưu hoặc danh tính nào? |
| Phụ thuộc quản trị | Ai có thể điều khiển nền tảng đang giữ quyền này? |
| Ngoại lệ | Đường vượt tier nào còn tồn tại, lý do và điều kiện kết thúc? |
| Bằng chứng | Kết quả rà soát, nguồn log và kiểm chứng ranh giới nào đã có? |

Ví dụ bản ghi khái niệm:

```json
{
  "principalRef": "idp:payments-operator-021",
  "subjectType": "human",
  "personRef": "person-021",
  "administrativeTier": "tier-1",
  "resourceScope": ["payments-production-service-group"],
  "allowedTasks": ["read-service-status", "restart-designated-service"],
  "allowedAccessContext": "approved-tier-1-administration",
  "grantMode": "time-bound",
  "credentialRef": "managed-reference-only",
  "canManageTier0": false
}
```

Đây là ví dụ hồ sơ, không phải policy của một nền tảng. Trường `canManageTier0` không tự chặn được bất cứ hành động nào. Cần kiểm tra role, policy, đường truy cập và quan hệ tin cậy để xác nhận giá trị đó phản ánh thực tế.

Không lưu mật khẩu, token hoặc khóa riêng trong hồ sơ. Các ngoại lệ cũng cần chủ sở hữu và phạm vi rõ ràng thay vì chỉ một ghi chú không có người chịu trách nhiệm.

## 10. Ví dụ xuyên suốt: một kỹ sư làm việc ở nhiều tier

Hà quản trị hệ thống nhận dạng, vận hành một ứng dụng và hỗ trợ máy trạm khi trực. Ban đầu, Hà dùng một tài khoản quản trị mạnh trên mọi hệ thống, từ máy tính làm việc hằng ngày đến máy chủ và bảng điều khiển nhận dạng.

### Các đường rủi ro

- Credential hoặc phiên quản trị nhận dạng có thể xuất hiện trên máy dùng cho công việc thường ngày.
- Quyền của một principal bao phủ nhiều tier và nhiều nhiệm vụ.
- Nếu một máy trạm hoặc máy chủ bị chiếm dụng, ngữ cảnh đặc quyền cao có thể bị lấy hoặc lạm dụng.
- Việc ghi log chỉ thấy một tài khoản rộng, khó phân biệt phạm vi quyền cần cho từng tác vụ.
- Thu hồi một nhiệm vụ không dễ nếu tất cả quyền gắn vào cùng ngữ cảnh.

### Thiết kế minh họa sau phân tier

| Công việc của Hà | Ngữ cảnh sử dụng | Ranh giới cần thực thi |
|---|---|---|
| Công việc thường ngày | Danh tính thông thường | Không giữ sẵn đặc quyền quản trị |
| Hỗ trợ đầu cuối | Tài khoản hoặc role Tier 2 | Chỉ đầu cuối được giao; không có quyền trên ứng dụng và nhận dạng trung tâm |
| Vận hành ứng dụng | Tài khoản hoặc role Tier 1 | Chỉ ứng dụng và tác vụ được giao; không lấy credential Tier 0 |
| Quản trị nhận dạng | Tài khoản hoặc role Tier 0 | Chỉ từ môi trường phù hợp; không dùng để đăng nhập xử lý lỗi ở tier thấp hơn |

Các ngữ cảnh có thể cùng liên kết với một người nhưng khác principal, policy và điều kiện sử dụng. Nếu nền tảng dùng cấp role tạm thời thay tài khoản riêng, cần bảo vệ tương đương các bước chuyển ngữ cảnh và môi trường giữ phiên.

### Phát hiện một phụ thuộc làm sai mô hình

Sau khi phân tier, nhóm nhận ra hệ thống triển khai ứng dụng Tier 1 có thể chạy script trên một máy nhận dạng Tier 0. Dù các tài khoản đã tách, đường kiểm soát gián tiếp này vẫn tồn tại.

Có thể xem xét tách luồng triển khai cho hệ thống nhận dạng, loại bỏ quyền vượt phạm vi hoặc đưa thành phần thực sự có quyền kiểm soát vào miền bảo vệ phù hợp. Việc chọn cách nào phụ thuộc kiến trúc, nhưng không thể coi ranh giới đã đạt chỉ vì tài khoản mang hậu tố đúng tier.

### Khi máy ứng dụng bị xâm nhập

Nhóm ứng cứu cần xác định tài khoản và phiên nào đã hiện diện trên máy, credential nào có thể đã bị đọc và có đường đi sang tier cao hơn không.

Nếu tài khoản Tier 0 từng được dùng trên máy đó, cần xem xét phạm vi liên đới theo bằng chứng và khả năng tiếp xúc, thay vì chỉ xử lý tài khoản Tier 1 của ứng dụng. Nếu không có đường được biết đến, vẫn cần phân biệt “chưa phát hiện” với kết luận chắc chắn không tồn tại.

## 11. Thay đổi vòng đời và ngoại lệ

### 11.1. Khi một người đổi nhiệm vụ

Người chuyển từ quản trị đầu cuối sang vận hành máy chủ cần được xem xét quyền mới và thu hồi quyền cũ không còn cần. Không nên để việc chuyển nhóm dẫn đến tích lũy quyền ở mọi tier.

Cần rà soát cả tài khoản, nhóm lồng nhau, khả năng yêu cầu role, token, credential đã được hiển thị và quyền tại hệ thống đích.

### 11.2. Khi một hệ thống thay chức năng

Một nền tảng trước chỉ quản lý ứng dụng có thể được giao thêm quyền triển khai vào hệ thống nhận dạng. Khi đó, phân loại tier và điều kiện quản trị của chính nền tảng cần được xem xét lại.

Tương tự, việc thêm credential nhạy cảm vào vault, thay hạ tầng hosting hoặc mở rộng khả năng khôi phục có thể làm xuất hiện quan hệ kiểm soát mới.

### 11.3. Khi phải có ngoại lệ vượt tier

Ngoại lệ có thể phát sinh do giới hạn nền tảng hoặc nhu cầu chuyển đổi. Cần mô tả rõ:

- Đường truy cập hoặc quyền nào vượt ranh giới.
- Tài nguyên, chủ thể và thời hạn áp dụng.
- Lý do chưa thể loại bỏ.
- Biện pháp giảm khả năng lạm dụng và bằng chứng cần theo dõi.
- Người chịu trách nhiệm và điều kiện xem xét lại hoặc kết thúc.

Không nên cấp ngoại lệ vô thời hạn chỉ để thuận tiện. Đồng thời, các biện pháp bù đắp phải phản ánh khả năng thực tế; phê duyệt thủ công không tự loại bỏ nguy cơ lộ credential trên một máy không tin cậy.

### 11.4. Truy cập khẩn cấp

Cơ chế break-glass cần được thiết kế theo miền kiểm soát và kịch bản phục hồi. Một tài khoản khẩn cấp có quyền ở nhiều tier có thể tạo phạm vi ảnh hưởng rất lớn nếu bị lộ.

Cần xác định ai được kích hoạt, sử dụng từ đâu, cách ghi nhận khi thành phần trung tâm lỗi, và cách xử lý quyền, credential, phiên sau sử dụng. Đường khôi phục phải đủ độc lập để đáp ứng tình huống dự kiến mà vẫn được bảo vệ tương xứng.

## 12. Thu hồi và ứng phó khi nghi vượt tier

Nếu một tài khoản hoặc môi trường quản trị bị chiếm dụng, phạm vi ứng cứu phải xét những gì nó thực sự kiểm soát được.

Các bước cần xem xét gồm:

1. Xác định principal, role, quyền yêu cầu và các phiên đang tồn tại.
2. Xác định nguồn truy cập, máy trung gian và credential có thể đã tiếp xúc.
3. Khoanh vùng quyền mới và hoạt động còn tiếp diễn theo cơ chế của hệ thống.
4. Xử lý credential, token, khóa và các principal hoặc policy mới bị tạo.
5. Kiểm tra đường gián tiếp qua script, nền tảng hosting, công cụ triển khai và phục hồi.
6. Bảo toàn bằng chứng, xác định tài nguyên đã bị tác động và khôi phục trạng thái tin cậy.
7. Xác nhận ranh giới đã hoạt động lại trước khi cấp lại đặc quyền.

Khóa tài khoản không tự kết thúc mọi phiên, thay mật khẩu không tự thu hồi mọi token, và đóng phiên không hoàn tác thay đổi đã thực hiện. Kế hoạch cần bao quát từng loại đối tượng theo khả năng của hệ thống.

Nếu chính nền tảng nhận dạng hoặc PAM có quyền rất cao bị mất kiểm soát, không nên mặc nhiên tin rằng một thao tác sửa role trong cùng nền tảng đã khôi phục toàn bộ độ tin cậy. Phạm vi phục hồi cần dựa trên mức độ chiếm dụng, bằng chứng và các đường kiểm soát liên quan.

## 13. Kiểm chứng ranh giới tier

Trong môi trường hoặc đợt diễn tập có phạm vi được cho phép, có thể đánh giá:

| Tình huống | Kết quả mong đợi |
|---|---|
| Tài khoản đúng tier thực hiện tác vụ hợp lệ trên tài nguyên được giao | Thành công và có chuỗi bằng chứng |
| Tài khoản Tier 2 yêu cầu quyền hoặc credential Tier 0 | Bị từ chối theo policy |
| Tài khoản tier cao được sử dụng từ môi trường không phù hợp | Không thể thực hiện luồng truy cập ngoài điều kiện cho phép |
| Tài khoản đúng tier truy cập ứng dụng hoặc tenant ngoài phạm vi ngang | Bị từ chối |
| Công cụ tier thấp cố sửa script, policy hoặc nền tảng của tier cao | Bị chặn tại ranh giới quyền tương ứng |
| Role tạm thời hết hạn khi còn phiên hoặc token | Hành vi khớp với mục tiêu đã công bố cho từng loại truy cập |
| Thành phần AAA, PAM hoặc mạng gặp lỗi | Đường khôi phục hoạt động theo kịch bản, không mở truy cập vượt tier vô điều kiện |
| Một thành phần được phân loại thấp hơn thực sự điều khiển được thành phần cao hơn | Phát hiện sai lệch và điều chỉnh quyền hoặc kiến trúc |

Đây là gợi ý kiểm chứng cho người học, không phải tuyên bố đã thực hiện kiểm thử trên một hệ thống thực tế.

Các bằng chứng hữu ích gồm policy hiệu lực, sự kiện cho phép và từ chối, nguồn tạo phiên, lịch sử thay đổi quyền, quan hệ cấp credential và quyền điều khiển nền tảng. Chỉ đếm số tài khoản đã đổi tên hoặc số thư mục vault theo tier sẽ không cho biết ranh giới có được thực thi hay không.

## 14. Những lỗi thường gặp

| Cách làm | Vấn đề |
|---|---|
| Chỉ gắn hậu tố tier vào tên tài khoản | Không thay đổi quyền hiệu lực hoặc đường sử dụng |
| Phân tier chỉ theo máy trạm, máy chủ và tên sản phẩm | Bỏ sót quyền điều khiển gián tiếp và hạ tầng hỗ trợ |
| Dùng credential giống nhau cho các tài khoản khác tier | Mất sự phân tách khi một credential bị lộ |
| Tách tài khoản nhưng dùng tất cả trên cùng môi trường thấp hơn | Credential hoặc phiên cao hơn vẫn có thể bị tiếp cận |
| Cho rằng JIT cho phép bỏ điều kiện nguồn truy cập | Quyền cao ngắn hạn vẫn nhạy cảm trong thời gian được cấp |
| Coi mọi tài khoản cùng tier có quyền với nhau | Bỏ qua ranh giới ứng dụng, tenant, môi trường và tác vụ |
| Đặt máy quản trị cao trên nền tảng bị tier thấp điều khiển | Tạo đường kiểm soát ngược |
| Chỉ bảo vệ tài khoản người dùng | Bỏ sót workload, pipeline, vault và công cụ phục hồi |
| Đóng mọi đường dự phòng mà không có kế hoạch phục hồi | Có thể mất khả năng quản trị khi thành phần trung tâm lỗi |
| Xếp tier một lần rồi không cập nhật | Quyền mới và thay đổi kiến trúc làm mô hình lỗi thời |

## 15. Tình huống tự luyện

Một tổ chức có hệ thống nhận dạng trung tâm, cụm máy chủ ứng dụng, máy trạm nhân viên và một nền tảng tự động hóa. Mỗi kỹ sư đã có ba tài khoản mang hậu tố theo tier. Tuy nhiên:

- Các tài khoản dùng chung mật khẩu.
- Kỹ sư đăng nhập mọi tài khoản từ máy tính làm việc hằng ngày.
- Nền tảng tự động hóa được xếp Tier 1 nhưng có thể chạy tác vụ trên máy nhận dạng.
- Vault chia thư mục theo tier, song nhóm quản trị ứng dụng có thể sửa policy của toàn bộ thư mục.
- Một tài khoản khẩn cấp có quyền quản trị toàn bộ các môi trường.

Hãy phân tích:

1. Những ranh giới nào mới chỉ tồn tại ở tên gọi hoặc cấu trúc thư mục?
2. Thành phần nào có đường kiểm soát trực tiếp hoặc gián tiếp đến Tier 0?
3. Vì sao chỉ đổi sang mật khẩu riêng vẫn chưa xử lý hết vấn đề?
4. Cần thay đổi gì ở môi trường tạo phiên, quyền vault và nền tảng tự động hóa?
5. Làm sao giới hạn tài khoản Tier 1 theo từng ứng dụng và môi trường?
6. Cần bằng chứng nào để xác nhận tài khoản tier thấp không lấy được quyền hoặc credential tier cao?
7. Cơ chế khẩn cấp cần được thiết kế lại theo phạm vi và kịch bản nào?

Gợi ý: vẽ quan hệ giữa người, principal, máy quản trị, kho credential, nền tảng triển khai và hệ thống đích. Đánh dấu những cạnh cho phép cấp quyền, lấy secret, thực thi mã hoặc điều khiển nền tảng. Sau đó quyết định nơi cần tăng mức bảo vệ và nơi cần cắt đường kiểm soát.

## 16. Ghi nhớ

Tài khoản theo tier là cách giới hạn đặc quyền theo các miền kiểm soát và quan hệ tin cậy. Mục tiêu là ngăn một điểm bị xâm nhập ở phạm vi thấp hơn trở thành đường chiếm quyền cao hơn hoặc làm lộ ngữ cảnh quản trị nhạy cảm.

Một thiết kế hiệu quả phải kết hợp phân loại theo quyền thực tế, tách principal và ngữ cảnh sử dụng, bảo vệ môi trường quản trị, giới hạn credential, JIT/JEA, phân tách phạm vi ngang, giám sát và thu hồi. Nhãn tier chỉ hữu ích khi phản ánh các ranh giới đang được thực thi và được cập nhật khi hệ thống thay đổi.
