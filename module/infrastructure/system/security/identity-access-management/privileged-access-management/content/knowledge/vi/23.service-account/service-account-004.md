# Static service credential

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Phân biệt tài khoản dịch vụ, credential tĩnh và quyền truy cập được cấp cho tài khoản.
- Nhận diện rủi ro của mật khẩu, API key và khóa riêng được sử dụng lâu dài trong ứng dụng.
- Thiết kế cách kiểm kê, lưu trữ, phân phối và giám sát credential tĩnh trong phạm vi PAM.
- Xây dựng quy trình luân chuyển phù hợp với ứng dụng có một hoặc nhiều credential hợp lệ đồng thời.
- Xác định bằng chứng cần có trước khi kết luận credential cũ đã bị loại khỏi sử dụng.

## 1. Static service credential là gì?

**Static service credential** là thông tin xác thực của một dịch vụ được cấp và tái sử dụng qua nhiều lần chạy hoặc nhiều yêu cầu, thay vì được tạo mới cho từng phiên hay từng công việc ngắn hạn.

Ví dụ:

- Mật khẩu của tài khoản cơ sở dữ liệu mà một ứng dụng dùng để kết nối.
- API key của một hệ thống tích hợp.
- Client secret được một dịch vụ dùng để yêu cầu token.
- Khóa riêng SSH của tiến trình đồng bộ.
- Khóa riêng và chứng chỉ dùng để xác thực một dịch vụ.

Từ “static” nhấn mạnh cách cấp phát và tái sử dụng credential. Nó không có nghĩa credential không thể thay đổi hoặc không bao giờ hết hạn. Một client secret có thời hạn ba tháng vẫn có thể là credential tĩnh nếu ứng dụng dùng lại cùng giá trị trong thời gian đó.

Trong PAM, credential tĩnh cần được quản lý đặc biệt khi nó cho phép truy cập tài nguyên nhạy cảm, thực hiện thao tác quản trị hoặc mở đường tới quyền cao hơn. Một mật khẩu được dùng hoàn toàn tự động vẫn có thể mang đặc quyền tương đương tài khoản quản trị của con người.

### 1.1. Tách ba khái niệm: danh tính, credential và quyền

Giả sử ứng dụng báo cáo dùng tài khoản `svc_report_reader` để đọc dữ liệu.

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Danh tính dịch vụ | `svc_report_reader` | Chủ thể được hệ thống đích nhận diện |
| Credential | Mật khẩu hoặc khóa dùng để xác thực | Bằng chứng để chứng minh danh tính |
| Quyền | Đọc một số view báo cáo | Giới hạn hành động chủ thể được phép thực hiện |
| Consumer | Tiến trình tạo báo cáo | Thành phần sử dụng credential |
| Chủ sở hữu | Nhóm chịu trách nhiệm dịch vụ | Quyết định nhu cầu, phối hợp vận hành và xử lý sự cố |

Đổi mật khẩu không tự làm giảm quyền của tài khoản. Giảm quyền cũng không tự vô hiệu hóa mọi bản sao credential đã bị lấy đi. Xóa một bản sao khỏi kho cấu hình không tự thay đổi credential mà hệ thống đích đang chấp nhận.

Muốn quản lý đúng, phải theo dõi cả ba lớp: danh tính, credential và quyền.

### 1.2. Không phải mọi dữ liệu đi cùng credential đều là bí mật

Tên tài khoản, ID của API key, đường dẫn tham chiếu secret và public key thường không phải là bí mật xác thực. Tuy nhiên, chúng vẫn có thể là thông tin nội bộ cần giới hạn công bố.

Mật khẩu, giá trị API key, client secret và private key phải được bảo vệ như bí mật. Với cơ chế xác thực bằng khóa bất đối xứng, private key là phần cần bảo mật; public key được dùng để xác minh.

Chứng chỉ công khai không cần được bảo vệ giống private key. Dù vậy, việc chứng chỉ vẫn còn hạn không chứng minh private key tương ứng chưa bị lộ hoặc chưa bị thay thế.

## 2. Vì sao credential tĩnh tạo ra rủi ro tích lũy?

Credential tĩnh thường tồn tại lâu hơn một lần chạy ứng dụng. Trong thời gian đó, cùng một giá trị có thể đi qua nhiều nơi:

```text
Hệ thống đích chấp nhận credential
               │
               ▼
Vault hoặc kho bí mật
               │
               ▼
Cơ chế phân phối → Bộ nhớ ứng dụng → Kết nối hoặc yêu cầu
               │
               ├→ Bản cấu hình cũ
               ├→ Công cụ triển khai
               └→ Bản sao lưu hoặc dữ liệu chẩn đoán
```

Mỗi bản sao tạo thêm một vị trí cần kiểm soát. Khi không biết credential đang nằm ở đâu và ai đang dùng, việc thay đổi nó có thể gây gián đoạn; việc không thay đổi lại kéo dài cửa sổ lạm dụng.

### 2.1. Khả năng tái sử dụng sau khi bị lấy cắp

Nếu hệ thống đích chỉ kiểm tra giá trị credential và không ràng buộc đủ chặt với workload hoặc điều kiện truy cập, người có được giá trị đó có thể giả mạo dịch vụ.

Mức độ lạm dụng còn phụ thuộc vào quyền, chính sách mạng, phạm vi tài nguyên và các điều kiện xác thực khác. Không nên giả định một API key chỉ dùng được từ ứng dụng đã khai báo nếu hệ thống đích không thực sự thực thi ràng buộc đó.

MFA áp dụng cho người quản trị khi họ mở vault không tự động bảo vệ mọi yêu cầu mà ứng dụng gửi bằng credential đã lấy ra.

### 2.2. Quyền quá rộng và dùng chung

Một credential dùng cho nhiều ứng dụng gây khó khăn cho cả kiểm soát lẫn vận hành:

- Khó biết ứng dụng nào tạo ra một hành động.
- Một ứng dụng bị xâm nhập có thể sử dụng toàn bộ quyền của tài khoản chung.
- Không thể luân chuyển riêng cho một consumer mà không ảnh hưởng các consumer còn lại.
- Khó thu hồi quyền của một dịch vụ đã ngừng hoạt động.
- Đội vận hành dễ trì hoãn luân chuyển vì không kiểm kê đủ phụ thuộc.

Cấp một credential riêng cho từng ứng dụng giúp giảm việc chia sẻ bí mật. Nhưng nếu các credential đó vẫn cùng đại diện cho một tài khoản có quyền rộng, phạm vi ảnh hưởng vẫn có thể lớn. Cần thiết kế cả danh tính và quyền phù hợp.

### 2.3. Tồn tại ngoài vòng đời ứng dụng

Ứng dụng đã ngừng chạy nhưng API key vẫn hợp lệ là một ví dụ điển hình của credential bị bỏ quên.

Một worker chạy theo lịch mỗi tháng, môi trường khôi phục thảm họa hoặc bản triển khai dự phòng có thể không xuất hiện trong log của vài ngày gần nhất. Thiếu hoạt động gần đây chưa đủ chứng minh credential không còn người dùng.

## 3. Credential tĩnh, credential động và workload identity

| Cách tiếp cận | Đặc điểm | Điều cần quản lý |
|---|---|---|
| Credential tĩnh | Cùng giá trị được tái sử dụng cho nhiều lần xác thực | Bản sao bí mật, thời hạn, luân chuyển, phụ thuộc consumer |
| Credential động | Được cấp theo yêu cầu, thường có lease hoặc thời hạn ngắn | Chính sách cấp, ràng buộc danh tính, lease, thu hồi và quota |
| Workload identity | Workload chứng minh danh tính qua nền tảng hoặc cơ chế liên kết | Độ tin cậy của nền tảng, điều kiện liên kết, audience và quyền |
| Credential tĩnh dùng để lấy token ngắn hạn | Bí mật dài hạn đổi lấy access token | Cả bí mật gốc lẫn vòng đời token đã phát hành |

Một dịch vụ dùng client secret tĩnh để lấy token hết hạn sau một thời gian ngắn vẫn có điểm phụ thuộc dài hạn là client secret đó. Token ngắn hạn không làm biến mất rủi ro của bí mật gốc.

Workload identity có thể giúp tránh phân phối một bí mật dùng chung dài hạn, nhưng vẫn cần kiểm soát quyền, cấu hình quan hệ tin cậy và bảo vệ môi trường chạy. Đây không phải cơ chế tự động làm mọi workload an toàn.

Khi hệ thống hỗ trợ phù hợp, có thể ưu tiên cơ chế giảm credential dài hạn. Với hệ thống cũ hoặc đối tác chỉ cung cấp API key tĩnh, cần quản lý credential tĩnh như một ngoại lệ có chủ sở hữu và vòng đời rõ ràng.

## 4. Kiểm kê trước khi quản lý

Một bản kiểm kê hữu ích không chỉ là danh sách tên secret trong vault. Nó phải nối được bí mật với tài khoản đích, quyền và các consumer.

### 4.1. Các dữ liệu cần thu thập

| Nhóm dữ liệu | Nội dung cần biết |
|---|---|
| Định danh | Credential ID nội bộ, loại credential, tài khoản hoặc principal đích |
| Phạm vi | Dịch vụ, môi trường, tài nguyên, tenant hoặc miền xác thực |
| Quyền | Vai trò, nhóm, quyền hiệu lực và khả năng cấp quyền tiếp |
| Chủ sở hữu | Đội nghiệp vụ, đội vận hành, người liên hệ và người thay thế |
| Consumer | Ứng dụng, worker, job theo lịch, công cụ triển khai, nơi dự phòng |
| Phân phối | Tham chiếu vault, cơ chế lấy secret, cache, reload hoặc restart |
| Vòng đời | Thời điểm tạo, hết hạn, luân chuyển gần nhất và lần kiểm tra tiếp |
| Khôi phục | Cách phục hồi dịch vụ, điều kiện rollback và giới hạn thời gian |
| Giám sát | Log truy cập vault, log xác thực đích và nơi lưu bằng chứng |
| Ngoại lệ | Lý do chưa dùng cơ chế khác, rủi ro được chấp nhận và ngày rà soát |

Bản kiểm kê không cần chứa giá trị secret.

### 4.2. Ví dụ bản ghi kiểm kê

Ví dụ dưới đây chỉ chứa metadata minh họa:

```yaml
credentialId: cred-report-prod-01
credentialType: database-password
targetPrincipal: svc_report_reader
environment: production
ownerTeam: reporting-platform
secretReference: vault-ref/reporting/prod/database
permissionsSummary:
  - read-approved-reporting-views
consumers:
  - reporting-api
  - monthly-report-job
  - disaster-recovery-reporting
deliveryMode: runtime-fetch
refreshMode: controlled-reload
rotationOwner: pam-operations
rotationRunbookRef: runbook-reporting-db
lastRotationResult: verified
exceptionReviewRef: review-static-credential-example
```

Đây là mô hình minh họa, không phải cấu hình trực tiếp cho một sản phẩm. Không nên đưa giá trị mật khẩu vào cùng bản ghi để tiện quản lý.

### 4.3. Xác minh consumer thay vì chỉ hỏi người phụ trách

Có thể kết hợp thông tin từ cấu hình triển khai, log đọc secret, log xác thực hệ thống đích và lịch job để kiểm tra danh sách consumer.

Cần phân biệt:

- Consumer được khai báo nhưng không còn dùng.
- Consumer đang dùng nhưng chưa được khai báo.
- Consumer có thể hoạt động trong điều kiện ít gặp, như chuyển vùng hoặc khôi phục.
- Công cụ thử nghiệm đang vô tình dùng credential sản xuất.

Kiểm kê là một hoạt động liên tục. Nếu chỉ làm một lần khi đưa secret vào vault, danh sách phụ thuộc sẽ nhanh chóng sai lệch.

## 5. Thiết kế quyền cho tài khoản dịch vụ

PAM không chỉ cất mật khẩu của tài khoản mạnh. Nó còn phải giảm nhu cầu sử dụng tài khoản quá mạnh.

### 5.1. Tách theo dịch vụ và môi trường

Nên tránh dùng cùng một credential cho cả phát triển, kiểm thử và sản xuất. Mỗi môi trường cần danh tính và phạm vi truy cập phù hợp.

Cũng nên tách các nhiệm vụ có nhu cầu quyền khác nhau. Ví dụ:

- Tiến trình phục vụ yêu cầu chỉ cần đọc và ghi dữ liệu nghiệp vụ được phép.
- Job migration cần quyền thay đổi cấu trúc trong một cửa sổ được kiểm soát.
- Công cụ sao lưu cần quyền phục vụ sao lưu theo thiết kế của hệ thống.
- Đội vận hành có đường truy cập quản trị riêng, gắn với danh tính con người.

Nếu gộp tất cả vào một tài khoản quản trị tĩnh, một lỗi nhỏ trong ứng dụng có thể mở ra phạm vi ảnh hưởng rất lớn.

### 5.2. Kiểm tra quyền hiệu lực

Tên vai trò “reader” không chứng minh tài khoản chỉ có quyền đọc. Quyền có thể đến từ nhiều nhóm, kế thừa, grant trực tiếp hoặc quyền quản trị ở tầng khác.

Cần kiểm tra cả khả năng:

- Đọc bí mật hoặc cấu hình nhạy cảm.
- Ghi mã thực thi, plugin hoặc tác vụ tự động.
- Tạo tài khoản và cấp quyền cho chủ thể khác.
- Chuyển sang vai trò mạnh hơn.
- Truy cập tài nguyên ngoài phạm vi dịch vụ.
- Thay đổi log hoặc cấu hình giám sát.

Một tài khoản có quyền sửa tác vụ chạy bằng danh tính quản trị có thể gián tiếp đạt đặc quyền cao dù nó không mang tên “admin”.

### 5.3. Hạn chế đăng nhập tương tác khi không cần

Nếu tài khoản chỉ phục vụ tiến trình tự động, cần hạn chế các đường đăng nhập tương tác không phục vụ nhiệm vụ của nó, trong khả năng hệ thống cho phép.

Không dùng tài khoản dịch vụ làm tài khoản đăng nhập chung của đội. Con người nên có danh tính riêng để thao tác và truy vết, kể cả khi PAM cho phép lấy credential phục vụ tình huống khẩn cấp.

## 6. Lưu trong vault: điều gì thay đổi và điều gì vẫn cần giải quyết?

Vault hoặc hệ thống quản lý bí mật giúp tập trung chính sách truy cập, bảo vệ dữ liệu lưu trữ và ghi nhận việc đọc secret. Tuy nhiên, sau khi ứng dụng nhận được một credential tĩnh, hệ thống đích vẫn quyết định credential đó còn hợp lệ hay không.

### 6.1. Phân biệt các nơi lưu và nơi xác thực

```text
Kho bí mật:
  Ai được lấy credential?
  Phiên bản nào được phân phối?
  Lần đọc nào đã xảy ra?

Hệ thống đích:
  Credential nào đang hợp lệ?
  Tài khoản có quyền gì?
  Kết nối, token hoặc phiên nào vẫn hoạt động?

Consumer:
  Phiên bản nào đang được dùng?
  Secret được cache ở đâu?
  Khi nào reload hoặc kết nối lại?
```

Chỉ đổi giá trị trong vault mà không đổi phía đích có thể làm ứng dụng nhận một credential không dùng được.

Chỉ đổi phía đích mà không cập nhật luồng phân phối có thể khiến ứng dụng tiếp tục nhận giá trị cũ.

Chỉ xóa một phiên bản khỏi vault không bảo đảm bản sao đã được lấy trước đó mất tác dụng.

### 6.2. Phân quyền đọc, thay đổi và vận hành

Có thể cần tách các quyền:

- Workload đọc đúng secret cần dùng.
- Cơ chế luân chuyển tạo hoặc cập nhật credential ở hệ thống đích.
- Người vận hành kích hoạt quy trình và xem trạng thái.
- Người kiểm toán xem metadata và log mà không đọc giá trị.
- Người quản lý chính sách quyết định ai được cấp quyền.

Không mặc định mọi người quản trị kho bí mật đều cần được đọc mọi giá trị secret. Khả năng tách quyền thực tế phụ thuộc sản phẩm và kiến trúc; cần kiểm tra thay vì dựa vào tên vai trò.

### 6.3. Bảo vệ kho bí mật và quy trình khôi phục

Cần bảo vệ cả dữ liệu lưu trữ, kênh truyền, khóa bảo vệ kho, bản sao lưu và danh tính quản trị. Một bản sao lưu có thể chứa credential cũ; credential đó vẫn nguy hiểm nếu hệ thống đích chưa thu hồi.

Quy trình khôi phục kho bí mật phải tính đến sự khác biệt giữa phiên bản được phục hồi và trạng thái hiện tại của hệ thống đích. Phục hồi bản sao lưu không nên tự động khiến một credential đã bị thu hồi được tái sử dụng.

## 7. Phân phối credential cho ứng dụng

### 7.1. Giải quyết bài toán xác thực để lấy secret

Ứng dụng cần chứng minh danh tính trước khi đọc credential từ vault. Nếu đặt một vault token dài hạn ngay trong mã nguồn để lấy mật khẩu, tổ chức có thể chỉ chuyển bí mật dài hạn từ chỗ này sang chỗ khác.

Khi nền tảng hỗ trợ, có thể dùng danh tính workload hoặc một cơ chế khởi tạo có phạm vi và thời hạn phù hợp. Chính sách cần ràng buộc đúng workload, môi trường và secret được đọc.

Danh tính dùng để đọc secret không nên có quyền liệt kê hoặc lấy toàn bộ bí mật của tổ chức nếu nhiệm vụ chỉ cần một credential.

### 7.2. Các cách đưa secret vào tiến trình

| Cách phân phối | Điểm thuận lợi | Điểm phải kiểm soát |
|---|---|---|
| Ứng dụng gọi dịch vụ bí mật lúc chạy | Có thể quản lý phiên bản và lấy lại khi cần | Danh tính workload, cache, timeout, lỗi mạng |
| Agent hoặc thành phần phụ lấy secret | Giảm logic quản lý secret trong ứng dụng | Quyền của agent, kênh trao đổi nội bộ, reload |
| Tệp được cấp vào lúc chạy | Dễ tích hợp với phần mềm cũ | Quyền tệp, bản sao, vòng đời, cơ chế thay mới |
| Biến môi trường lúc khởi động | Tương thích với nhiều ứng dụng | Khả năng xuất hiện trong chẩn đoán, kế thừa và nhu cầu restart |
| Đóng gói trong image hoặc mã nguồn | Có vẻ đơn giản lúc triển khai | Tạo bản sao khó kiểm soát, khó thu hồi và dễ lan truyền |

Không nên đóng gói secret sản xuất vào mã nguồn hay image. Khi secret đã xuất hiện trong lịch sử mã nguồn, chỉ xóa dòng hiện tại không loại bỏ các bản sao đã tồn tại.

Biến môi trường không phải mặc nhiên an toàn hay mặc nhiên không dùng được. Cần đánh giá khả năng tiến trình, công cụ debug, dump và hệ thống vận hành có thể đọc hoặc ghi lại giá trị đó hay không.

### 7.3. Cache cần có chính sách

Ứng dụng có thể cache credential để giảm phụ thuộc vào vault và giảm độ trễ. Đổi lại, thời gian tồn tại của bản cache ảnh hưởng trực tiếp tới khả năng luân chuyển và thu hồi.

Cần xác định:

- Cache nằm trong bộ nhớ hay được ghi ra đĩa.
- Thời hạn cache và điều kiện làm mới.
- Có thể nhận tín hiệu reload hay phải restart.
- Credential hết hiệu lực được xử lý thế nào.
- Hành vi khi vault tạm thời không hoạt động.
- Cách tránh nhiều replica đồng loạt truy vấn lại và gây quá tải.

Nếu cho phép tiếp tục dùng bản cache khi vault lỗi, giới hạn này phải được thiết kế và theo dõi rõ ràng. Không âm thầm dùng một bản sao không thời hạn để vượt qua mọi lỗi.

### 7.4. Không để secret đi vào khả năng quan sát

Cần rà soát các đường có thể ghi lại secret:

- Log cấu hình lúc khởi động.
- Chuỗi kết nối trong thông báo lỗi.
- Log HTTP có header xác thực.
- Trace chứa payload hoặc tham số nhạy cảm.
- Core dump, heap dump và gói chẩn đoán.
- Lệnh vận hành được lưu trong lịch sử hoặc danh sách tiến trình.
- Ticket, ảnh chụp màn hình và hội thoại hỗ trợ.

Che secret ở giao diện không có nghĩa giá trị đó không xuất hiện trong log nền. Kiểm tra cần dùng dữ liệu thử nghiệm, không cố tình đưa credential thật vào công cụ quan sát để xác nhận việc lọc.

## 8. Luân chuyển credential là một thay đổi phân tán

Luân chuyển không chỉ là tạo một chuỗi mới. Ít nhất có ba trạng thái phải được phối hợp:

1. Hệ thống đích chấp nhận credential nào.
2. Kho bí mật phân phối phiên bản nào.
3. Các consumer đang thực sự sử dụng phiên bản nào.

Điều kiện hoàn tất còn bao gồm việc credential cũ không xác thực mới được nữa và các phiên tồn dư đã được xử lý theo yêu cầu.

### 8.1. Những câu hỏi cần trả lời trước khi đổi

- Hệ thống đích cho phép một hay nhiều credential đồng thời?
- Có thể tạo credential mới trước khi thu hồi cái cũ không?
- Ứng dụng tự reload, đọc lại khi kết nối hay chỉ lấy một lần lúc khởi động?
- Connection pool giữ các kết nối cũ trong bao lâu?
- Có replica, job theo lịch, hệ thống dự phòng hoặc consumer ngoài danh sách không?
- Cách xác minh ứng dụng đã chuyển phiên bản là gì?
- Nếu thay đổi thất bại, phương án phục hồi nào không tái kích hoạt credential bị nghi lộ?
- Ai quyết định dừng triển khai, chuyển hướng lưu lượng hoặc thu hồi khẩn cấp?

Một lịch luân chuyển chỉ có ngày thực hiện nhưng thiếu các câu trả lời này chưa phải runbook đủ dùng.

### 8.2. Trường hợp hỗ trợ hai credential hợp lệ

Nếu hệ thống đích hỗ trợ hai key hoặc hai phiên bản hợp lệ, có thể dùng khoảng chuyển tiếp:

```text
Chỉ A hợp lệ
    ↓ tạo B
A và B hợp lệ
    ↓ phân phối B, chuyển consumer, xác minh
A và B hợp lệ trong khoảng chuyển tiếp có giới hạn
    ↓ thu hồi A, kiểm tra xác thực mới
Chỉ B hợp lệ
```

Các bước minh họa:

1. Xác minh danh sách consumer và tiêu chí sức khỏe.
2. Tạo B bằng cơ chế phù hợp; lưu vào kho bí mật dưới phiên bản mới.
3. Thử xác thực bằng B với quyền dự kiến.
4. Chuyển một nhóm consumer trước, theo dõi lỗi xác thực và nghiệp vụ.
5. Chuyển các consumer còn lại, bao gồm job và nơi dự phòng.
6. Xác nhận các nhóm cần thiết đã dùng B hoặc có kế hoạch chuyển được kiểm chứng.
7. Thu hồi A ở hệ thống đích.
8. Kiểm tra A không còn được chấp nhận cho xác thực mới bằng phương thức thử được cho phép.
9. Xử lý kết nối, token hoặc phiên còn tồn tại theo cơ chế của hệ thống.
10. Ghi bằng chứng và đóng công việc.

Khoảng A và B cùng hợp lệ làm giảm rủi ro gián đoạn khi chuyển đổi nhưng cũng kéo dài thời gian A còn có thể bị lạm dụng. Khoảng này cần được giới hạn, có chủ sở hữu và có cảnh báo khi quá hạn.

### 8.3. Trường hợp chỉ có một mật khẩu hợp lệ

Một số hệ thống chỉ chấp nhận một mật khẩu cho tài khoản tại một thời điểm. Khi đổi phía đích, consumer giữ giá trị cũ có thể thất bại ngay ở lần xác thực tiếp theo.

Có thể cần:

- Cửa sổ bảo trì.
- Tạm dừng một số job.
- Drain hoặc điều phối kết nối.
- Cập nhật phía đích và kho bí mật theo runbook.
- Reload hoặc restart có kiểm soát.
- Kiểm tra toàn bộ nhóm consumer trước khi mở lại lưu lượng.

Không hứa hẹn “không downtime” nếu ứng dụng và hệ thống đích không hỗ trợ cơ chế chuyển đổi phù hợp.

Một lựa chọn khác trong một số môi trường là chuẩn bị danh tính thay thế với quyền tương đương đã được kiểm tra. Cách này thay đổi mô hình danh tính và quyền, nên cần đánh giá tác động, kiểm soát tài khoản cũ và tránh để hai danh tính tồn tại vô hạn.

### 8.4. Đổi mật khẩu không chắc kết thúc phiên đang mở

Hệ thống đích có thể kiểm tra credential khi tạo kết nối, còn kết nối đã xác thực tiếp tục tồn tại sau khi mật khẩu đổi. Hành vi cụ thể phụ thuộc hệ thống.

Tương tự, thay client secret có thể ngăn việc lấy token mới nhưng không tự làm mọi access token đã phát hành mất hiệu lực.

Do đó, cần tách:

- Không thể dùng credential cũ để xác thực mới.
- Không còn kết nối hoặc phiên được xác thực trước đó.
- Không còn token, khóa hoặc quyền phái sinh còn hiệu lực.
- Không còn cơ chế duy trì truy cập do tài khoản đã tạo ra.

Trong sự cố bảo mật, những khác biệt này ảnh hưởng trực tiếp tới kết luận đã thu hồi truy cập hay chưa.

## 9. Rollback và xử lý thất bại

### 9.1. Phân biệt lỗi vận hành với nghi ngờ lộ bí mật

Nếu một thay đổi định kỳ thất bại do consumer chưa cập nhật, runbook có thể cho phép một phương án phục hồi giới hạn tùy theo hệ thống.

Nếu credential cũ đã bị nghi lộ, khôi phục nó để ứng dụng chạy lại có thể khôi phục luôn khả năng truy cập của kẻ tấn công. Khi đó nên ưu tiên tạo một giá trị mới khác hoặc dùng đường phục hồi đã chuẩn bị, với quyết định của người chịu trách nhiệm sự cố.

Không áp dụng cùng một quy tắc rollback cho mọi lý do luân chuyển.

### 9.2. Một số điểm lỗi thường gặp

| Điểm lỗi | Tình trạng có thể xảy ra | Hướng xử lý |
|---|---|---|
| Tạo mới ở đích thành công nhưng lưu vault thất bại | Có credential chưa được quản lý đầy đủ | Đối soát trạng thái, lưu hoặc vô hiệu hóa theo runbook |
| Vault đã cập nhật nhưng một consumer chưa reload | Một phần hệ thống dùng giá trị cũ | Xác định consumer, giới hạn khoảng chuyển tiếp, xử lý reload |
| Thu hồi cũ thất bại | Hai credential vẫn cùng hợp lệ | Giữ công việc mở, chuyển cấp và hạn chế truy cập khi cần |
| Hệ thống đích đã đổi nhưng vault vẫn giữ giá trị cũ | Consumer lấy secret không hợp lệ | Phục hồi tính nhất quán và theo dõi lỗi xác thực |
| Controller bị dừng giữa quy trình | Không rõ bước nào đã hoàn tất | Đọc trạng thái thực tế, không chạy lại mù quáng |
| Job chạy ít thường xuyên chưa được thử | Lỗi xuất hiện sau khi tưởng đã hoàn tất | Kiểm tra chủ động hoặc có diễn tập tương đương được chấp nhận |
| Kết nối cũ che lỗi credential mới | Health check vẫn xanh | Thử tạo kết nối mới và kiểm tra nghiệp vụ phù hợp |

Cơ chế tự động hóa cần giữ mã công việc, trạng thái từng bước và kết quả kiểm tra. Thử lại một bước không được vô tình tạo nhiều credential bỏ quên hoặc thu hồi sai phiên bản.

### 9.3. Tránh luân chuyển chồng chéo

Hai tiến trình cùng luân chuyển một tài khoản có thể làm kho bí mật và hệ thống đích lệch nhau.

Cần có cơ chế điều phối để một lần thay đổi có quyền thực hiện tại một thời điểm, đồng thời ghi nhận phiên bản đang xử lý. Nếu công việc bị gián đoạn, lần tiếp theo phải đối soát trạng thái thực tế trước khi tiếp tục.

Việc khóa xử lý phải có cơ chế phục hồi; một khóa bị bỏ quên không được khiến credential không bao giờ luân chuyển được nữa.

## 10. Giám sát và bằng chứng

### 10.1. Log đọc secret và log sử dụng là hai nguồn khác nhau

Log vault có thể cho biết workload nào đã đọc phiên bản nào. Nó không chứng minh mọi hành động tiếp theo tại hệ thống đích đều do workload hợp lệ đó tạo ra.

Log hệ thống đích có thể cho biết tài khoản đã đăng nhập và thực hiện thao tác. Nếu nhiều consumer dùng chung một tài khoản, nguồn log này có thể chưa đủ để phân biệt từng ứng dụng.

Cần liên kết metadata phù hợp như danh tính workload, credential ID, phiên bản, thời gian, nguồn kết nối và tài nguyên. Không ghi giá trị secret để tạo mã liên kết.

### 10.2. Tín hiệu đáng chú ý

- Credential được đọc từ workload hoặc môi trường không nằm trong danh sách.
- Có xác thực tại hệ thống đích nhưng không phù hợp với lịch hoạt động dự kiến.
- Credential cũ tiếp tục được dùng sau thời điểm dự kiến thu hồi.
- Tài khoản dịch vụ mở phiên tương tác không phục vụ nhiệm vụ.
- Tài khoản truy cập tài nguyên ngoài phạm vi đã phê duyệt.
- Có thay đổi quyền, tạo khóa mới hoặc tạo tài khoản khác.
- Số lỗi xác thực tăng sau một lần luân chuyển.
- Secret được đọc hàng loạt hoặc từ danh tính quản trị bất thường.
- Phiên bản secret thay đổi ngoài quy trình vận hành.

Một cảnh báo cần có chủ sở hữu và hướng xử lý. Chỉ đẩy log vào nơi tập trung chưa bảo đảm có người phát hiện và phản ứng.

### 10.3. Bằng chứng cho một lần luân chuyển

Hồ sơ nên thể hiện:

- Lý do và mã công việc.
- Tài khoản đích, credential ID, phiên bản cũ và mới.
- Danh sách consumer đã xác nhận.
- Kết quả thử xác thực và kiểm tra chức năng.
- Thời điểm cập nhật kho và chuyển từng nhóm consumer.
- Kết quả thu hồi credential cũ.
- Cách xử lý phiên hoặc token tồn dư.
- Lỗi, ngoại lệ, người quyết định và thời hạn xử lý tiếp.
- Người hoặc cơ chế xác minh hoàn tất.

Không đưa mật khẩu cũ và mới vào ticket để chứng minh đã đổi. Metadata và kết quả kiểm tra phải đủ để truy vết mà không làm lộ bí mật.

## 11. Tình huống thực tế: một mật khẩu cho ba consumer

Một dịch vụ báo cáo dùng credential tĩnh của `svc_report_reader`. Ban đầu đội vận hành chỉ biết đến API báo cáo. Khi kiểm kê, họ phát hiện thêm job tạo báo cáo tháng và một bản triển khai dự phòng.

### 11.1. Thiết kế ban đầu

```text
Mật khẩu A
    ├→ API báo cáo: lấy secret lúc khởi động
    ├→ Job báo cáo tháng: đọc tệp cấu hình cục bộ
    └→ Nơi dự phòng: dùng bản cấu hình đã sao chép
```

Nếu chỉ đổi A rồi restart API:

- API có thể chạy tốt.
- Job tháng có thể thất bại nhiều tuần sau.
- Nơi dự phòng có thể không kết nối được khi cần chuyển vùng.
- Bản sao A vẫn còn trong tệp và bản sao lưu.

Sự thành công của một health check API không chứng minh toàn bộ vòng đời credential đã được quản lý.

### 11.2. Cách cải thiện

Đội phụ trách thực hiện các việc:

1. Ghi đủ ba consumer vào kiểm kê và gắn chủ sở hữu.
2. Chuyển các consumer sang tham chiếu kho bí mật phù hợp.
3. Kiểm tra quyền đọc secret riêng cho từng workload.
4. Đánh giá tách danh tính cho API, job và nơi dự phòng nếu nhu cầu quyền hoặc trách nhiệm khác nhau.
5. Thiết kế cách reload và kiểm tra kết nối mới.
6. Thử job bằng dữ liệu kiểm thử hoặc quy trình tương đương được phép.
7. Diễn tập việc lấy phiên bản mới tại nơi dự phòng.
8. Luân chuyển và xác minh giá trị cũ không còn được chấp nhận.
9. Xử lý bản sao cấu hình và điều chỉnh quy trình sao lưu, triển khai.
10. Lưu bằng chứng và lập lịch rà soát tiếp.

Nếu hệ thống đích chỉ hỗ trợ một mật khẩu, đội cần điều phối một cửa sổ thay đổi phù hợp. Nếu có thể dùng nhiều credential hoặc tách danh tính, quá trình chuyển đổi có thể linh hoạt hơn, nhưng vẫn phải thu hồi phần cũ.

### 11.3. Điều kiện kết luận hoàn tất

Không kết luận “đã an toàn” chỉ vì secret đã nằm trong vault. Kết luận phải dựa trên việc xác minh consumer, quyền, phân phối, thu hồi và bằng chứng.

Nếu còn một consumer chưa thể chuyển, hồ sơ cần nêu rõ ngoại lệ, biện pháp tạm thời, người sở hữu và thời hạn. Không âm thầm giữ credential cũ vô hạn.

## 12. Ứng phó khi nghi ngờ credential bị lộ

Khi một API key hoặc mật khẩu dịch vụ xuất hiện trong log, mã nguồn hay một nguồn không được phép, cần phối hợp giữa xử lý bí mật và bảo đảm hoạt động dịch vụ.

Một trình tự tham khảo:

1. Xác định credential, tài khoản đích, quyền và phạm vi tài nguyên.
2. Phân loại khả năng bị khai thác và mức ảnh hưởng.
3. Bảo toàn log và bằng chứng phù hợp mà không sao chép secret sang nhiều nơi.
4. Hạn chế đường truy cập hoặc cô lập workload khi tình huống yêu cầu.
5. Tạo credential thay thế theo đường vận hành tin cậy.
6. Chuyển consumer và thu hồi credential bị nghi lộ theo mức khẩn cấp.
7. Xử lý phiên, token, khóa mới hoặc thay đổi quyền có thể đã phát sinh.
8. Điều tra cách secret bị lộ và xác định các credential liên quan.
9. Sửa nguồn gây lộ, chẳng hạn log cấu hình hoặc pipeline triển khai.
10. Ghi kết quả, thông báo bên chịu trách nhiệm và theo dõi sau xử lý.

Nếu workload đã bị xâm nhập, đưa secret mới vào chính môi trường đó có thể làm lộ tiếp secret mới. Việc thay giá trị phải đi cùng xử lý nguồn xâm nhập và thiết lập lại môi trường tin cậy khi cần.

Xóa secret khỏi trang hiện tại của kho mã không thay thế việc thu hồi. Người khác có thể đã lấy bản sao hoặc truy cập lịch sử trước khi xóa.

## 13. Ngừng sử dụng và loại bỏ credential

Khi ứng dụng hoặc tích hợp không còn hoạt động:

- Xác minh cả job theo lịch, nơi dự phòng và consumer phụ.
- Thu hồi credential ở hệ thống đích.
- Xử lý phiên và quyền còn tồn tại theo yêu cầu.
- Gỡ quyền đọc secret của workload.
- Loại bỏ tham chiếu khỏi cấu hình và pipeline.
- Lưu metadata và bằng chứng theo chính sách.
- Xem xét vô hiệu hóa hoặc xóa tài khoản nếu không còn mục đích hợp lệ.

Không xóa secret khỏi vault trước rồi coi công việc đã hoàn tất. Hành động quan trọng để ngăn tái sử dụng là làm credential mất hiệu lực tại nơi chấp nhận nó.

Thời gian giữ lịch sử và bản sao lưu cần theo chính sách tổ chức. Trong thời gian đó, phải bảo vệ bản sao; việc giữ lịch sử không có nghĩa được tiếp tục chấp nhận credential cũ.

## 14. Sai lầm thường gặp

| Sai lầm | Vì sao không đủ | Hướng cải thiện |
|---|---|---|
| Đưa mật khẩu vào vault rồi ngừng kiểm kê | Không biết consumer và quyền hiện tại | Duy trì liên kết danh tính, secret, quyền và consumer |
| Dùng chung credential cho mọi môi trường | Mở rộng phạm vi ảnh hưởng | Tách danh tính và secret theo môi trường, nhiệm vụ |
| Chỉ đổi bản lưu trong vault | Không thay thứ hệ thống đích chấp nhận | Phối hợp trạng thái đích, kho và consumer |
| Tin rằng token ngắn hạn loại bỏ mọi bí mật dài hạn | Client secret gốc có thể vẫn tĩnh | Quản lý cả bí mật gốc lẫn token phát hành |
| Đổi mật khẩu và coi mọi phiên đã bị cắt | Phiên cũ có thể tiếp tục tồn tại | Kiểm tra cơ chế phiên và thu hồi riêng khi cần |
| Health check dùng kết nối cũ | Không kiểm tra được credential mới | Tạo kết nối mới và kiểm tra nghiệp vụ phù hợp |
| Giữ hai key mãi để tránh rủi ro | Không hoàn tất thu hồi | Giới hạn khoảng chuyển tiếp và chuyển cấp khi quá hạn |
| Rollback về secret đã nghi lộ | Khôi phục đường truy cập của kẻ tấn công | Dùng secret mới khác và phương án phục hồi tin cậy |
| Ghi secret vào ticket khi xử lý lỗi | Mở thêm điểm lộ | Chỉ dùng ID, phiên bản và tham chiếu bằng chứng |
| Tắt tài khoản mà không kiểm kê job | Gây lỗi muộn, khó truy nguyên | Kiểm tra consumer ít chạy và nơi dự phòng |
| Chỉ đánh giá tuổi của mật khẩu | Bỏ qua quyền, bản sao và dấu hiệu lạm dụng | Đánh giá toàn bộ vòng đời và phạm vi tác động |

## 15. Kiểm tra thiết kế bằng tình huống lỗi

Có thể diễn tập trong môi trường phù hợp với credential thử nghiệm:

- Vault không phản hồi khi ứng dụng khởi động.
- Vault lỗi sau khi ứng dụng đã có cache.
- Một replica không reload secret.
- Job theo lịch chỉ hoạt động sau khi credential cũ đã bị thu hồi.
- Kho bí mật cập nhật thành công nhưng hệ thống đích thất bại.
- Hệ thống đích thay đổi thành công nhưng controller bị dừng trước khi ghi kết quả.
- Hai yêu cầu luân chuyển xuất hiện gần nhau.
- Credential cũ bị thu hồi nhưng một phiên cũ vẫn hoạt động.
- Công cụ chẩn đoán được kích hoạt khi ứng dụng đang giữ secret.
- Nơi dự phòng khởi động với cấu hình cũ.
- Workload không còn quyền đọc secret sau khi thay đổi chính sách.
- Credential bị nghi lộ đúng lúc một lần luân chuyển định kỳ đang diễn ra.

Một lần thử đạt yêu cầu khi phát hiện đúng tình trạng, giữ được khả năng truy vết và thực hiện được phương án phục hồi đã thiết kế. Không chỉ kiểm tra rằng “đường thành công” chạy được.

## 16. Bài tập thực hành

### Bài tập 1: Vẽ bản đồ credential

Chọn một tích hợp giả định dùng API key tĩnh. Xác định danh tính đích, quyền, nơi lưu, consumer, cách phân phối, cache, người sở hữu và nguồn log.

Hãy chỉ ra ít nhất một consumer ít hoạt động có thể bị bỏ quên và cách kiểm chứng nó trước khi thu hồi key cũ.

### Bài tập 2: Thiết kế hai runbook

Viết hai quy trình cho cùng một dịch vụ:

- Hệ thống đích hỗ trợ hai key cùng hợp lệ.
- Hệ thống đích chỉ hỗ trợ một mật khẩu.

Mỗi quy trình cần nêu cách xác minh consumer đã chuyển, điều kiện dừng, cách phục hồi và cách chứng minh credential cũ không xác thực mới được nữa.

### Bài tập 3: Phân tích một kết luận sai

Một báo cáo ghi:

> Đã cập nhật mật khẩu trong vault. API vẫn trả lời health check. Luân chuyển hoàn tất.

Chưa đủ dữ kiện để kết luận hoàn tất. Cần biết phía đích đã đổi chưa, health check có tạo kết nối mới không, còn consumer nào khác không, credential cũ đã bị thu hồi chưa và có phiên hoặc token nào cần xử lý riêng không.

## 17. Điểm cần ghi nhớ

Credential tĩnh là một bí mật được tái sử dụng, không phải một bí mật không thể thay đổi. Rủi ro của nó phụ thuộc vào quyền của tài khoản, số bản sao, thời gian hợp lệ và khả năng kiểm soát nơi sử dụng.

Quản lý bằng PAM cần nối được tài khoản đích, credential, quyền, consumer, chủ sở hữu và bằng chứng. Vault hỗ trợ bảo vệ và phân phối bí mật, còn một lần luân chuyển chỉ hoàn tất khi trạng thái phía đích, kho bí mật và consumer đã được đối soát, credential cũ đã bị xử lý và các ngoại lệ có trách nhiệm rõ ràng.
