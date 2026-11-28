# Migrate database credential

## 1. Mục tiêu và phạm vi

Migrate database credential là chuyển cơ chế quản lý và sử dụng thông tin xác thực cơ sở dữ liệu sang mô hình được kiểm soát, đồng thời duy trì dịch vụ và khả năng truy vết. Trong một chương trình Privileged Access Management (PAM), việc này thường bắt đầu từ mật khẩu dùng chung trong file cấu hình, biến môi trường hoặc công cụ triển khai, rồi tiến tới vault, danh tính workload, quyền tối thiểu và quy trình luân chuyển có bằng chứng.

Đưa mật khẩu hiện tại vào vault mới hoàn thành một phần công việc. Nếu ứng dụng vẫn giữ bản sao cũ, tài khoản còn quyền quản trị quá mức hoặc thay mật khẩu làm mất kết nối sau mỗi lần restart, hệ thống chưa đạt mục tiêu migration.

Sau bài này, người học có thể:

- Phân biệt chuyển nơi lưu secret, chuyển tài khoản và chuyển phương thức xác thực.
- Lập bản đồ tài khoản, quyền, ứng dụng, batch job và connection pool trước khi thay đổi.
- Chọn chiến lược chuyển đổi phù hợp với khả năng của database và ứng dụng.
- Thiết kế cutover, rollback và thu hồi credential cũ.
- Xây dựng bộ kiểm thử chứng minh ứng dụng hoạt động với đúng quyền.
- Lưu bằng chứng vận hành mà không đưa mật khẩu hoặc token vào báo cáo.

Bài học tập trung vào migration credential của ứng dụng và các tài khoản quản trị có liên quan. Việc chuyển dữ liệu, đổi database engine hoặc thiết kế lại toàn bộ schema là những dự án khác, dù chúng có thể diễn ra trong cùng một chương trình.

## 2. Xác định chính xác thứ gì đang được migrate

Một credential không tồn tại độc lập. Nó thuộc một chuỗi gồm chủ thể sử dụng, phương thức xác thực, quyền hiệu lực, đường kết nối và cơ chế cấp phát.

| Thành phần | Ví dụ trạng thái cũ | Trạng thái đích có thể chọn |
|---|---|---|
| Danh tính | Nhiều ứng dụng dùng chung một database login | Một danh tính riêng cho từng workload và môi trường |
| Phương thức xác thực | Mật khẩu tĩnh tồn tại lâu | Mật khẩu do PAM quản lý hoặc credential ngắn hạn được hỗ trợ |
| Nơi lưu | File cấu hình, pipeline variable, script vận hành | Vault hoặc cơ chế cấp credential được phê duyệt |
| Quyền | Tài khoản runtime được phép sửa schema | Runtime chỉ có quyền nghiệp vụ cần thiết |
| Cấp phát | Người vận hành sao chép mật khẩu thủ công | Workload xác thực tới secret provider bằng danh tính được kiểm soát |
| Luân chuyển | Đổi theo yêu cầu cá nhân, không kiểm tra phụ thuộc | Có owner, quy trình đồng bộ, kiểm chứng và cảnh báo |
| Truy vết | Chỉ biết một username dùng chung | Liên kết được workload, credential version, thay đổi và sự kiện database |

Có ba loại thay đổi cần tách rõ.

**Chuyển nơi lưu:** Giữ nguyên database login và mật khẩu ban đầu, nhưng đổi nguồn ứng dụng đọc từ file sang secret provider. Cách này giảm phạm vi thay đổi ở bước đầu, nhưng mật khẩu đã tồn tại ở nhiều nơi vẫn cần được thay và thu hồi.

**Chuyển tài khoản:** Tạo hoặc dùng một login mới cho workload, cấp quyền phù hợp rồi chuyển ứng dụng sang login đó. Cách này hỗ trợ tách danh tính và chuyển đổi từng nhóm consumer, nhưng phải xử lý quyền kế thừa, ownership và những ràng buộc gắn với tên tài khoản.

**Chuyển phương thức xác thực:** Từ mật khẩu sang certificate, token hoặc cơ chế liên kết danh tính mà database, driver và hạ tầng thực sự hỗ trợ. Đây là thay đổi lớn hơn vì vòng đời credential, thời gian sống và hành vi tái kết nối có thể khác.

Có thể chia dự án thành nhiều đợt: chuyển nguồn secret trước, tách tài khoản sau, rồi áp dụng credential ngắn hạn. Mỗi đợt phải có tiêu chí hoàn thành riêng; không gộp mọi trạng thái thành một nhãn “đã vào PAM”.

## 3. Phân biệt credential quản trị và credential runtime

Tài khoản quản trị database phục vụ thay đổi cấu hình, quản lý tài khoản, xử lý sự cố và những tác vụ đặc quyền. Tài khoản runtime phục vụ ứng dụng thực hiện nghiệp vụ đã xác định. Đưa cả hai vào cùng một vault không làm chúng có cùng chính sách.

| Loại danh tính | Cách sử dụng | Kiểm soát cần chú ý |
|---|---|---|
| DBA cá nhân | Con người đăng nhập để quản trị | Danh tính cá nhân, phê duyệt khi cần, JIT/JEA nếu phù hợp, giám sát phiên |
| Runtime ứng dụng | Dịch vụ kết nối liên tục hoặc theo tải | Cấp phát tự động, quyền tối thiểu, refresh và pool có kiểm soát |
| Job thay đổi schema | Chạy migration schema trong cửa sổ triển khai | Danh tính riêng, quyền theo tác vụ, giới hạn thời gian và lưu bằng chứng |
| Backup hoặc replication | Tác vụ nền có quyền chuyên biệt | Kiểm kê độc lập, quyền theo engine, không mặc định dùng tài khoản runtime |
| Break-glass | Phục hồi khi luồng truy cập thông thường hỏng | Chính sách khẩn cấp riêng, kiểm tra định kỳ, điều tra sau sử dụng |

Không buộc ứng dụng sản xuất chờ một người duyệt mỗi lần mở kết nối chỉ vì áp dụng cơ chế checkout cho tài khoản DBA. Ngược lại, cũng không cấp tài khoản runtime quyền quản trị để làm cho cutover “dễ thành công”.

Workload cần một cách xác thực tới vault. Nếu thay mật khẩu database trong file bằng một token vault tồn tại vô thời hạn ở chính file đó, dự án chỉ chuyển vị trí của rủi ro bootstrap. Cần xác định rõ danh tính máy, workload identity hoặc cơ chế bootstrap được bảo vệ, cùng cách thu hồi và phục hồi của nó.

## 4. Lập inventory theo consumer và đường kết nối

Đơn vị kiểm kê hữu ích là một quan hệ: **consumer nào sử dụng danh tính nào để truy cập đích nào, với quyền gì và vào thời điểm nào**.

Một tài khoản có thể được dùng bởi API, báo cáo, worker xử lý hàng đợi, cron, công cụ BI và script do DBA vận hành. Nếu chỉ tìm username trong repository của ứng dụng chính, những consumer còn lại có thể chỉ xuất hiện sau khi mật khẩu cũ đã bị vô hiệu hóa.

Bản kiểm kê tối thiểu nên có:

| Trường | Ý nghĩa |
|---|---|
| Consumer ID | Định danh ổn định của dịch vụ, batch job hoặc công cụ |
| Owner | Nhóm chịu trách nhiệm vận hành và xác nhận nghiệp vụ |
| Môi trường | Dev, test, staging hoặc production |
| Database target | Cluster, database, endpoint và vai trò primary/replica nếu có |
| Principal | Login thực tế dùng để xác thực, kể cả tài khoản dùng chung |
| Quyền hiệu lực | Quyền trực tiếp, role kế thừa và quyền nhận qua cơ chế khác |
| Nguồn credential | File, secret store, cấu hình triển khai hoặc phương thức khác |
| Cách nạp | Khi khởi động, theo TTL, theo sự kiện hoặc mỗi lần tạo kết nối |
| Chu kỳ sử dụng | Liên tục, hằng ngày, cuối tháng, khi failover hoặc khi phục hồi |
| Connection pool | Kích thước, thời gian sống kết nối, cơ chế thay pool |
| Chính sách retry | Phân biệt lỗi xác thực, thiếu quyền và lỗi mạng |
| Phụ thuộc đặc biệt | Proxy, JDBC driver, scheduler, backup, integration bên ngoài |
| Kiểm thử xác nhận | Các thao tác nghiệp vụ cần chứng minh sau cutover |

Bảng này dùng đường dẫn hoặc mã tham chiếu secret, không chứa giá trị secret.

Dùng nhiều nguồn bằng chứng để hoàn thiện inventory: cấu hình được phép kiểm tra, manifest triển khai, audit log database, lịch scheduler và xác nhận của owner. Khi tìm trong cấu hình, cần tránh để công cụ tìm kiếm hoặc bản ghi terminal phát tán mật khẩu ra một hệ thống log mới.

Không xem “không thấy truy cập trong một ngày” là bằng chứng consumer đã chết. Một báo cáo cuối tháng, tác vụ disaster recovery hoặc job chỉ chạy khi có sự kiện vẫn có thể cần credential đó.

## 5. Vẽ đồ thị phụ thuộc trước khi chọn chiến lược

Một ví dụ đơn giản:

~~~mermaid
flowchart LR
    P[Workload identity] --> V[Secret provider]
    V --> A[API pool]
    V --> W[Worker pool]
    V --> B[Batch scheduler]
    A --> X[Database endpoint]
    W --> X
    B --> X
    O[Operator qua PAM] --> D[Danh tính quản trị]
    D --> X
~~~

Sơ đồ cần làm rõ hai đường khác nhau:

1. Consumer lấy được credential từ secret provider.
2. Consumer dùng credential đó để mở kết nối tới đúng database.

Hai đường có thể hỏng độc lập. Đọc secret thành công không chứng minh database chấp nhận mật khẩu. Database chấp nhận mật khẩu cũng không chứng minh login có đủ quyền cho nghiệp vụ.

Nếu có database proxy, cần xác định principal nhìn thấy ở proxy và ở backend. Một mô hình proxy có thể gom nhiều consumer về một tài khoản backend, làm thay đổi khả năng quy trách nhiệm và cách quan sát quá trình migration. Không mặc định tên workload ở phía ứng dụng sẽ xuất hiện nguyên vẹn trong audit database.

Đồng thời kiểm tra secret provider có phụ thuộc vào chính database đang được thay credential hay không. Nếu có vòng phụ thuộc, phải có phương án phục hồi và bootstrap đã kiểm chứng trước cutover.

## 6. Thiết kế danh tính và quyền đích

Mục tiêu quyền đích dựa trên thao tác cần thiết, không dựa trên việc sao chép toàn bộ quyền của tài khoản cũ.

Ví dụ một hệ thống đơn hàng có thể tách:

- API runtime: đọc và cập nhật dữ liệu nghiệp vụ được phép.
- Reporting worker: chỉ đọc những tập dữ liệu được phê duyệt.
- Schema migration job: quyền thay đổi cấu trúc trong cửa sổ triển khai.
- DBA: quyền quản trị qua luồng đặc quyền.
- Backup service: quyền chuyên biệt theo kiến trúc backup.

Trong thực tế, quyền hiệu lực còn đến từ role kế thừa, quyền mặc định, ownership, view, stored procedure và cơ chế thực thi dưới quyền của chủ thể khác. Một login mới có cùng tập quyền được liệt kê trực tiếp chưa chắc có cùng hành vi.

Những điểm cần đối chiếu gồm:

- Quyền kết nối và quyền sử dụng namespace/schema.
- Quyền đọc, thêm, sửa, xóa và gọi routine cần thiết.
- Quyền với sequence hoặc đối tượng hỗ trợ sinh khóa.
- Quyền đối với đối tượng được tạo trong tương lai.
- Row-level security và điều kiện phụ thuộc current user.
- Ownership của object và các thao tác chỉ owner thực hiện được.
- Search path, default schema hoặc context phiên.
- Chính sách hạn chế nguồn mạng và điều kiện xác thực.
- Trường hợp dùng replication, backup hoặc tài khoản cho failover.

Không cấp quyền cao hơn chỉ để làm mất lỗi trong kiểm thử. Cần xác định thao tác nào thiếu quyền, nó có thuộc vai trò của consumer hay không, rồi cấp đúng quyền hoặc sửa việc phân công tác vụ.

Nếu tài khoản cũ vừa là owner schema vừa là runtime, có thể cần một đợt tách ownership riêng. Việc đổi username ứng dụng không tự chuyển ownership hoặc cập nhật mọi chính sách gắn với principal cũ.

## 7. Chọn chiến lược chuyển đổi

| Chiến lược | Điều kiện phù hợp | Lợi thế | Rủi ro phải xử lý |
|---|---|---|---|
| Giữ login, đổi nguồn secret rồi đổi mật khẩu | Consumer có thể đọc nguồn mới; engine dùng mật khẩu được quản lý | Ít thay đổi về principal | Không chuyển từng consumer dễ dàng nếu mật khẩu đổi ngay cho tất cả |
| Dùng login mới, chuyển consumer từng nhóm | Có thể cấp đủ quyền mà vẫn tách danh tính và bảo toàn nghiệp vụ | Canary và rollback theo nhóm rõ hơn | Khác ownership, RLS, quota, mapping hoặc hành vi phiên |
| Hai credential hợp lệ cho cùng principal | Database hoặc lớp xác thực hỗ trợ rõ cơ chế này | Có cửa sổ chồng lấp được kiểm soát | Giới hạn engine, thời hạn overlap và thu hồi credential cũ |
| Credential ngắn hạn | Database, provider, driver và kiến trúc hỗ trợ | Giảm thời gian tồn tại của credential | TTL, renewal, pool, thu hồi và giới hạn số danh tính |
| Cutover trong maintenance window | Ứng dụng khó reload hoặc không có overlap phù hợp | Trình tự đơn giản hơn | Downtime, draining và phục hồi phải được kiểm chứng |

Không giả định database cho phép hai mật khẩu đồng thời cho một login. Cũng không giả định hai secret version ở vault tương đương hai credential đang hợp lệ tại database. Secret version là trạng thái của nơi lưu; việc database chấp nhận credential là trạng thái của hệ thống xác thực.

Nếu engine chỉ chấp nhận một mật khẩu tại một thời điểm, đổi mật khẩu của login dùng chung sẽ tác động đến mọi consumer khi chúng tạo kết nối mới. Những phiên đã mở có thể tiếp tục hoặc bị ảnh hưởng khác nhau tùy engine và cơ chế thực thi. Cần kiểm chứng hành vi cụ thể trong môi trường thử nghiệm.

Với login mới, có thể chuyển từng consumer mà không đổi mật khẩu login cũ ngay lập tức. Tuy nhiên cửa sổ tồn tại song song phải có owner, thời hạn và điều kiện đóng, tránh biến “tạm thời” thành hai đường truy cập vĩnh viễn.

## 8. Thiết kế hợp đồng secret và phiên bản

Ứng dụng cần biết cách lấy một bộ credential nhất quán. Những thành phần như username, password, endpoint hoặc database name không được vô tình lấy từ các phiên bản khác nhau.

Ví dụ dưới đây là hợp đồng khái niệm để thảo luận giữa nhóm ứng dụng và nhóm PAM, không phải schema của một sản phẩm:

~~~yaml
consumer: order-api
environment: production
databaseTarget: orders-primary
credentialReference: pam/database/orders/order-api
credentialMode: managed-static
credentialVersionPolicy: explicitly-promoted
deliveryMode: workload-authenticated-fetch
refreshTrigger: pool-generation-change
rollbackReference: approved-previous-generation
~~~

Mã tham chiếu không phải credential, nhưng vẫn có thể tiết lộ kiến trúc nội bộ; chỉ công bố trong phạm vi phù hợp.

Các nguyên tắc quan trọng:

- Phân biệt version hiện có trong provider với version đã được promote cho ứng dụng.
- Cập nhật những trường phụ thuộc nhau như một bộ dữ liệu nhất quán.
- Chỉ promote sau khi kiểm tra credential tương ứng với database target.
- Không dùng thứ tự ghi vào vault làm bằng chứng database đã thay đổi thành công.
- Ghi nhận trạng thái trung gian nếu database và provider không hỗ trợ giao dịch chung.
- Xác định một controller hoặc owner điều phối rotation; tránh nhiều hệ thống cùng tự đổi mật khẩu.
- Có quyền riêng cho đọc secret, thay đổi secret và thay đổi credential tại database.
- Không cho workload liệt kê hoặc đọc credential của dịch vụ khác chỉ vì dùng chung provider.

Đối với credential động, còn phải quản lý lease hoặc định danh cấp phát, thời điểm hết hạn, renewal và hành vi thu hồi. Không dùng một quy trình mật khẩu tĩnh rồi chỉ thay nhãn thành “dynamic”.

## 9. Chuẩn bị ứng dụng và connection pool

Connection pool là điểm thường gây hiểu nhầm nhất trong migration. Đổi cấu hình secret chưa chắc thay credential mà pool dùng để tạo kết nối. Tương tự, một pool còn đầy kết nối đang hoạt động có thể che giấu lỗi xác thực cho đến khi scale-out hoặc restart.

Cần trả lời rõ:

- Ứng dụng lấy secret lúc nào?
- Pool lưu bản sao credential ở đâu?
- Thay secret có làm thay cấu hình pool không?
- Kết nối cũ được giữ đến khi nào?
- Một transaction đang chạy có bị cắt khi thay pool không?
- Pool mới có thể được tạo và kiểm tra trước khi nhận lưu lượng không?
- Replica mới khởi động sẽ dùng version nào?
- Khi provider tạm thời không khả dụng, ứng dụng có chính sách nào đã được phê duyệt?

Một mẫu chuyển đổi là tạo pool thế hệ mới, kiểm tra nó rồi chuyển lưu lượng tạo transaction mới. Pool cũ được drain theo giới hạn đã định. Khả năng thực hiện phụ thuộc framework và thư viện; không mặc định mọi pool hỗ trợ đổi username/password trực tiếp.

~~~text
prepare(newCredentialVersion):
    xác thực workload với secret provider
    lấy bộ credential nhất quán của version đã chỉ định
    tạo candidate pool tới đúng database target
    kiểm tra xác thực và những thao tác được phép
    nếu không đạt: đóng candidate pool, giữ cấu hình đang phục vụ

promote(candidate):
    chuyển transaction mới sang pool mới
    ngừng cấp kết nối mới từ pool cũ
    để transaction đang chạy kết thúc trong thời hạn đã duyệt
    đóng và xác minh pool cũ sau khi drain
    phát metric thế hệ pool và kết quả cutover, không phát secret
~~~

Đây là giả mã mô tả thứ tự, không phải API của một JDBC pool cụ thể.

Không đổi pool giữa chừng trong cùng một transaction. Với transaction dài, cần lựa chọn rõ: chờ hoàn tất, dừng nhận công việc mới, chuyển cửa sổ bảo trì hoặc xử lý bằng cơ chế được ứng dụng hỗ trợ. Việc cưỡng bức đóng kết nối có thể gây rollback transaction hoặc làm client không biết chắc kết quả của thao tác vừa gửi.

Khi retry sau lỗi kết nối, cần xem xét tính idempotent của nghiệp vụ. Một request lỗi ở client không đồng nghĩa thao tác ghi chưa commit. Không biến lỗi credential thành lý do lặp lại vô hạn một thao tác thanh toán hoặc tạo đơn hàng.

## 10. Runbook migration theo từng trạng thái

Một runbook tốt mô tả điều kiện vào, hành động, bằng chứng và điều kiện thoát cho từng trạng thái.

~~~mermaid
flowchart TD
    I[Inventory và owner đã xác nhận] --> T[Chuẩn bị danh tính và secret đích]
    T --> V[Kiểm thử trong môi trường đại diện]
    V --> C[Canary một nhóm consumer]
    C --> E[Mở rộng cutover]
    E --> O[Quan sát đủ chu kỳ]
    O --> R[Thu hồi credential và đường truy cập cũ]
    R --> F[Kiểm tra rotation và đóng migration]
    C -->|Không đạt| B[Rollback đã phê duyệt]
    E -->|Không đạt| B
~~~

### Giai đoạn A — Chốt baseline

Ghi nhận consumer, phiên bản triển khai, quyền hiệu lực, luồng truy cập và những metric hiện tại. Xác định ai ra quyết định go/no-go và ai có quyền thao tác tại database, provider và nền tảng triển khai.

Đặt tiêu chí lỗi trước khi thực hiện. Ví dụ: xuất hiện lỗi xác thực tại candidate pool, thiếu quyền đối với transaction trọng yếu, hoặc p95 latency vượt ngưỡng của dịch vụ trong cửa sổ đánh giá đã chọn. Ngưỡng phải phù hợp với baseline của hệ thống, không lấy một con số chung cho mọi ứng dụng.

### Giai đoạn B — Chuẩn bị đích

Tạo hoặc cấu hình principal đích, cấp quyền tối thiểu và thiết lập policy đọc secret cho đúng workload. Kiểm tra network, TLS, xác minh danh tính máy chủ và driver authentication.

Nếu dùng mật khẩu, việc sinh và đặt mật khẩu phải qua kênh quản trị được phê duyệt. Không dán giá trị vào ticket, tham số command line, lịch sử terminal hoặc script được commit.

Đảm bảo bên vận hành biết hệ thống nào là nguồn quản lý credential và ai chịu trách nhiệm reconcile khi trạng thái database và provider khác nhau.

### Giai đoạn C — Kiểm thử trước production

Dùng môi trường đại diện để kiểm chứng đường cấp phát và những điểm phụ thuộc principal. Môi trường thử cần đủ giống về engine, cơ chế xác thực, driver, pool và policy để có giá trị, nhưng không sao chép credential production sang môi trường đó.

Thử cả restart, scale-out, hết vòng đời kết nối và provider unavailable theo kịch bản đã được phép. Một bài kiểm tra chỉ sử dụng các kết nối cũ không xác nhận credential mới.

### Giai đoạn D — Canary

Chọn consumer hoặc nhóm replica có thể quan sát và phục hồi. Chuyển sang credential đích, buộc mở kết nối mới bằng cách được kiểm soát và chạy kiểm thử nghiệp vụ.

Theo dõi đồng thời lỗi ứng dụng, sự kiện cấp secret và xác thực database. Khi cùng username được giữ lại và log không ghi version mật khẩu, không suy ra version chỉ từ username; cần thêm bằng chứng triển khai, thế hệ pool và kiểm thử kết nối mới.

### Giai đoạn E — Mở rộng

Chuyển dần các consumer còn lại, bao gồm batch và công cụ tích hợp. Ghi nhận từng consumer đã chuyển, version hoặc generation đã dùng, thời điểm xác nhận và người chịu trách nhiệm.

Không xoay mật khẩu cũ hoặc đóng login cũ chỉ vì API đã ổn nếu một batch quan trọng chưa được thử. Nếu không thể chờ lịch chạy tự nhiên, owner phải xác định cách chạy thử đại diện và mức rủi ro còn lại.

### Giai đoạn F — Thu hồi và đóng

Sau khi đạt điều kiện quan sát, vô hiệu hóa credential cũ bằng thao tác tương ứng với chiến lược đã chọn. Xử lý các phiên cũ theo chính sách; ngăn kết nối mới không luôn đồng nghĩa đóng mọi phiên đang tồn tại.

Kiểm tra consumer đã chuyển vẫn hoạt động sau khi credential cũ không còn dùng để mở kết nối. Thực hiện một lần rotation theo mô hình đích có kiểm soát. Chỉ khi cả cutover và vòng đời mới hoạt động thì migration mới có bằng chứng hoàn thành.

## 11. Bộ kiểm thử phải bao phủ cả thành công và từ chối

Chỉ chạy một truy vấn health check không đủ chứng minh quyền nghiệp vụ.

| Nhóm kiểm thử | Ví dụ kiểm tra | Kết quả cần xác nhận |
|---|---|---|
| Danh tính | Mở kết nối mới và đọc session identity | Đúng principal, đúng môi trường và đúng database |
| Nghiệp vụ đọc | Truy vấn dữ liệu đại diện | Có quyền và hành vi dữ liệu đúng mong đợi |
| Nghiệp vụ ghi | Transaction thử trên dữ liệu được phép | Đọc/ghi/commit hoặc rollback đúng thiết kế |
| Đối tượng phụ trợ | Sequence, routine, view cần thiết | Không thiếu quyền chỉ xuất hiện ở nhánh ít dùng |
| Từ chối quyền | Thử một thao tác ngoài vai trò trong môi trường cho phép | Bị từ chối mà không gây thay đổi ngoài ý muốn |
| Pool | Mở kết nối sau khi thay generation | Không tiếp tục dựa vào credential cũ |
| Khởi động | Restart hoặc tạo replica mới có kiểm soát | Tự lấy credential đích và đạt readiness |
| Rotation | Đổi credential theo quy trình mới | Kết nối mới dùng credential mới thành công |
| Thu hồi | Credential cũ thử mở kết nối qua đường được kiểm soát | Bị từ chối theo mục tiêu thu hồi |
| Phụ thuộc nền | Job định kỳ, backup hoặc báo cáo trong scope | Hoàn tất đúng lịch và đúng quyền |
| Hỏng provider | Tình huống mất kết nối provider đã phê duyệt | Hành vi đúng chính sách, không truy cập ngoài kiểm soát |

Ví dụ với PostgreSQL, truy vấn sau có thể hỗ trợ kiểm tra danh tính phiên trong một môi trường thử đã được cấp phép:

~~~sql
SELECT
    session_user AS authenticated_identity,
    current_user AS effective_identity,
    current_database() AS database_name;
~~~

Kết quả là bằng chứng về danh tính và database của phiên đó. Nó không tự chứng minh quyền ghi nghiệp vụ, nguồn mật khẩu, version secret hoặc việc mọi replica đã chuyển.

Không chạy kiểm thử âm nguy hiểm trên dữ liệu thật để chứng minh “không được quyền xóa”. Có thể dùng đối tượng thử được thiết kế trước hoặc môi trường riêng. Phép thử phải có owner và kết quả mong đợi rõ ràng.

Với hệ thống ghi dữ liệu, ưu tiên transaction và dữ liệu thử có thể nhận diện, cùng cơ chế dọn dẹp phù hợp. Không giả định rollback có thể đảo mọi side effect bên ngoài database.

## 12. Ví dụ: chuyển hệ thống đơn hàng khỏi login dùng chung

Giả sử hệ thống có:

- 12 replica API, 4 worker xử lý hàng đợi và 2 job báo cáo.
- Tất cả dùng login cũ là order_shared.
- Mật khẩu được phân phối qua cấu hình triển khai.
- API và worker có thể thay pool theo generation; job báo cáo đọc secret khi bắt đầu chạy.
- Runtime đang thừa quyền thay đổi schema.

Kiến trúc đích chọn ba danh tính riêng theo workload: order_api_runtime, order_worker_runtime và order_report_reader. Danh tính chạy schema migration được tách khỏi runtime. Đây là các tên minh họa, không phải khuyến nghị tên cố định cho mọi tổ chức.

Trình tự có thể thực hiện:

1. Kiểm kê các thao tác thật sự của từng consumer và xử lý quyền đang gắn với order_shared.
2. Chuẩn bị ba login đích và policy secret theo workload.
3. Chạy bộ kiểm thử trên staging, đặc biệt các thao tác ghi dùng sequence hoặc routine.
4. Chuyển một replica API, kiểm tra kết nối mới và transaction đại diện.
5. Mở rộng API, rồi chuyển worker theo nhịp xử lý công việc an toàn.
6. Chạy thử hai job báo cáo với credential đích theo cách owner chấp thuận.
7. Xác nhận không còn consumer đã biết dùng login cũ; đối chiếu các phiên còn sống và chu kỳ sử dụng ít gặp.
8. Đóng khả năng xác thực mới bằng login cũ theo runbook; xử lý phiên còn lại có kiểm soát.
9. Kiểm tra lại toàn bộ consumer và thử rotation cho từng credential đích.
10. Gỡ quyền, cấu hình và bản sao secret cũ trong phạm vi đã xác định; lưu bằng chứng.

Các con số replica trong ví dụ chỉ giúp lập kế hoạch. Không tính “18/18 tiến trình đã deploy” thành “18/18 consumer đã chuyển” nếu một tiến trình có nhiều pool hoặc một job còn đọc một nguồn cấu hình khác.

Trong giai đoạn overlap, theo dõi tiến độ bằng những thuộc tính quan sát được:

| Consumer | Generation mong đợi | Kết nối mới | Nghiệp vụ | Trạng thái |
|---|---|---|---|---|
| API canary | api-g2 | Thành công với principal đích | Đạt | Có thể mở rộng |
| Worker nhóm A | worker-g2 | Thành công | Đạt | Đang drain nhóm cũ |
| Báo cáo cuối ngày | report-g2 | Thành công | Đạt | Đã xác nhận |
| Báo cáo cuối tháng | report-g2 | Chưa kiểm tra | Chưa xác nhận | Chưa đủ điều kiện đóng |

Generation ở đây là nhãn triển khai hoặc pool do hệ thống định nghĩa. Nó chỉ có giá trị khi liên kết được với credential reference và quá trình tạo kết nối thực tế.

## 13. Rollback cần bảo toàn cả khả năng phục hồi và kiểm soát truy cập

Rollback là một nhánh đã chuẩn bị của runbook, không phải quyết định quay lại mọi cấu hình cũ khi xuất hiện lỗi.

Cần phân biệt nguyên nhân:

| Tình huống | Hướng xử lý |
|---|---|
| Candidate pool không xác thực được | Không promote; kiểm tra mapping database/provider và quyền lấy secret |
| Login mới thiếu quyền nghiệp vụ hợp lệ | Dừng mở rộng, đối chiếu quyền; rollback consumer nếu cần |
| Provider gián đoạn | Áp dụng chính sách sẵn có cho credential cache và kết nối đang sống |
| Mật khẩu cũ đã bị thay với cùng login | Muốn quay lại phải có thao tác đồng bộ trạng thái được phê duyệt |
| Credential cũ nghi bị lộ | Không khôi phục việc sử dụng secret đã bị lộ; chuyển sang đường phục hồi an toàn |
| Dữ liệu đã bị thay đổi sai | Kích hoạt quy trình xử lý dữ liệu; đổi credential không tự sửa dữ liệu |

Với chiến lược login mới, rollback consumer về login cũ có thể khả thi trong cửa sổ overlap nếu login cũ còn hợp lệ và không bị coi là compromised. Phải đặt thời hạn rõ cho cửa sổ này.

Với chiến lược cùng login và một mật khẩu hợp lệ, việc chọn một secret version cũ trong vault chưa đủ. Database có thể đã đổi sang mật khẩu mới. Runbook phải mô tả thao tác điều phối, kiểm chứng lại và giới hạn ai được thực hiện.

Nếu mật khẩu bị lộ là nguyên nhân migration khẩn cấp, phục hồi bằng credential đó sẽ tái mở đường truy cập cho bên không được phép. Khi đó có thể cần credential mới khác, cô lập consumer lỗi hoặc dùng cơ chế break-glass được kiểm soát.

Không thiết kế ứng dụng tự thử lần lượt mật khẩu mới, mật khẩu cũ rồi tài khoản DBA cho đến khi kết nối được. Cơ chế đó làm khó thu hồi, có thể gây lockout và che giấu lỗi cấu hình.

## 14. Quan sát và bằng chứng

Các metric hữu ích gồm lỗi xác thực khi tạo kết nối, lỗi thiếu quyền, số kết nối mới, trạng thái pool generation, tỷ lệ lỗi nghiệp vụ và thời gian xử lý. Chọn nhãn sao cho không đưa password, token, connection string chứa secret hoặc dữ liệu nghiệp vụ nhạy cảm vào metric.

Audit và log nên giúp trả lời:

- Workload nào yêu cầu credential?
- Policy nào cho phép hoặc từ chối yêu cầu?
- Credential reference hoặc version nào được cấp, nếu provider hỗ trợ ghi nhận an toàn?
- Thay đổi nào tại database làm credential đích có hiệu lực?
- Consumer nào đã tạo kết nối mới và chạy kiểm thử thành công?
- Khi nào khả năng sử dụng credential cũ đã bị thu hồi?
- Ai xác nhận go/no-go và đóng migration?

Một bộ bằng chứng có thể gồm:

~~~text
migration_id: DB-CRED-CHANGE-EXAMPLE
scope: orders / production / runtime consumers
strategy: replacement-principals
inventory_revision: approved-revision
target_policy_revision: approved-policy
deployment_generation: approved-generation
fresh_connection_checks: passed-for-recorded-consumers
business_checks: passed-for-recorded-scenarios
old_credential_revocation: verified
post_cutover_rotation: verified
exceptions: explicitly-recorded
~~~

Đây là mẫu nội dung báo cáo, không phải file bắt buộc phải tạo. Không ghi giá trị credential, checksum của mật khẩu hoặc bản dump secret vào bằng chứng. Mã version, ID sự kiện và kết quả kiểm chứng thường hữu ích hơn việc cố tạo một “dấu vân tay mật khẩu”.

Log không ghi version mật khẩu thì không được dựng kết luận version từ dữ liệu không có. Trường hợp giữ nguyên login, bằng chứng mạnh hơn cần kết hợp sự kiện rotation, thế hệ ứng dụng, tạo kết nối mới và phép thử thu hồi đúng cơ chế.

Việc không còn log sử dụng login cũ chỉ có ý nghĩa trong phạm vi nguồn log, độ đầy đủ và cửa sổ quan sát đã biết. Nó không chứng minh mọi bản sao mật khẩu cũ đã biến mất.

## 15. Xử lý các lỗi thường gặp

### Secret provider và database không đồng bộ

Biểu hiện: ứng dụng đọc secret bình thường nhưng tạo kết nối mới bị từ chối.

Cần kiểm tra đúng database target, đúng principal, credential version đã promote và kết quả thao tác đổi credential tại database. Đừng mặc định mạng lỗi chỉ vì thông báo lỗi ở ứng dụng không đủ chi tiết.

Khi có lỗi giữa chừng, giữ trạng thái thay đổi rõ ràng và dùng cơ chế reconcile được phê duyệt. Không cho hai operator cùng đặt những mật khẩu khác nhau trong hai hệ thống.

### Chỉ hỏng sau restart hoặc scale-out

Nguyên nhân có thể là tiến trình cũ vẫn giữ kết nối đã xác thực, còn replica mới dùng secret sai, không có quyền đọc provider hoặc dùng một cấu hình khác.

Kiểm tra luồng cold start và kết nối mới. Cần có phép thử này trước khi kết luận canary thành công.

### Login mới kết nối được nhưng một nghiệp vụ thất bại

Nguyên nhân thường nằm ở quyền đối tượng phụ trợ, RLS, ownership hoặc context phiên. Thu thập thao tác thất bại trong phạm vi được phép, đối chiếu quyền hiệu lực và yêu cầu nghiệp vụ.

Không cấp quyền quản trị toàn cục để chữa nhanh một lỗi cần quyền trên một đối tượng cụ thể.

### Job chạy định kỳ vẫn dùng mật khẩu cũ

Kiểm tra scheduler, cấu hình đóng gói trong image, script bên ngoài pipeline chính và những bản triển khai không được quản lý cùng cách.

Bổ sung consumer vào inventory, giao owner và xác nhận lại thời điểm đóng overlap. Nếu credential cũ đã thu hồi, cấp luồng đích đúng chính sách thay vì phát tán mật khẩu thay thế qua chat.

### Rotation tạo ra bão retry

Nhiều replica có thể đồng thời mất khả năng tạo kết nối và retry liên tục. Thiết kế backoff có giới hạn, jitter và xử lý riêng lỗi xác thực. Đồng thời cân nhắc nhịp refresh để tránh mọi tiến trình cùng truy vấn provider trong một thời điểm.

Chỉ retry không sửa được một credential sai. Phải có cảnh báo và đường xử lý trạng thái sai, tránh làm quá tải database hoặc provider.

### Thu hồi login nhưng phiên cũ vẫn còn

Tùy engine, ngăn xác thực mới và chấm dứt phiên hiện tại là hai thao tác khác nhau. Kiểm tra rõ loại thu hồi đã làm và những phiên cần xử lý.

Không chấm dứt mọi session của một username dùng chung khi chưa biết những workload đang sử dụng. Migration cần xử lý chính rủi ro quy trách nhiệm này trước hoặc trong quá trình tách danh tính.

## 16. Thu dọn credential cũ và những bản sao

Thu hồi ở database là hàng rào quyết định đối với việc xác thực bằng credential cũ. Sau đó vẫn phải xử lý các bản sao để giảm lộ thông tin và ngăn cấu hình cũ được đưa trở lại.

Các nơi thường cần rà soát trong phạm vi được giao gồm:

- Secret store cũ và những version giữ lại theo policy.
- Pipeline variable, cấu hình scheduler và hệ thống triển khai.
- File cấu hình trên máy hoặc image.
- Script vận hành và công cụ tích hợp.
- Cấu hình dự phòng dùng khi failover hoặc disaster recovery.
- Tài liệu nội bộ, ticket hoặc kênh trao đổi từng chứa secret.
- Backup cấu hình, artifact hoặc lịch sử repository nếu từng có credential.

Nếu secret từng được commit, xóa nó khỏi file hiện tại không làm lịch sử mất secret. Trước hết phải vô hiệu hóa credential đó; xử lý lịch sử và các bản sao theo quy trình sự cố, quyền hạn và chính sách lưu trữ của tổ chức.

Không xóa backup hoặc bằng chứng kiểm toán ngoài phạm vi chỉ để đạt một nhãn “không còn secret”. Với bản sao phải giữ vì policy, cần kiểm soát truy cập và bảo đảm credential trong đó không còn dùng được để xác thực.

Kiểm tra thêm việc phục hồi từ backup có tái đưa cấu hình cũ vào hoạt động hay không. Một runbook restore phải lấy credential hiện hành theo nguồn đích, không mặc nhiên tiếp tục sử dụng giá trị đã có trong bản backup.

## 17. Điều kiện hoàn thành migration

Một migration có thể được đóng khi có bằng chứng phù hợp cho những điểm sau:

1. Consumer trong phạm vi đã có owner và được kiểm kê theo chu kỳ sử dụng.
2. Danh tính đích có quyền nghiệp vụ cần thiết, đồng thời những quyền ngoài vai trò đã được xử lý.
3. Workload tự lấy credential qua cơ chế được phê duyệt.
4. Kết nối mới, restart, scale-out và những batch quan trọng đã được kiểm chứng.
5. Phiên cũ và pool cũ được xử lý theo runbook.
6. Credential cũ không còn mở được kết nối theo mục tiêu thu hồi.
7. Bản sao và cấu hình cũ được gỡ hoặc kiểm soát theo policy.
8. Ít nhất một vòng rotation hoặc vòng đời credential đích đã được kiểm chứng theo mô hình đã chọn.
9. Rollback hoặc đường phục hồi sau đóng migration được xác định rõ.
10. Log, metric và bằng chứng đủ để vận hành tiếp mà không lưu secret.

Mọi ngoại lệ phải có owner, lý do, phạm vi, thời hạn và phương án xử lý. Một consumer chưa thể chuyển không được biến mất khỏi báo cáo chỉ để tổng tỷ lệ đạt 100%.

## 18. Bài tập tình huống

Một ứng dụng có 8 replica dùng login chung với một job cuối tuần. Ứng dụng đọc secret khi khởi động. Database trong tình huống chỉ chấp nhận một mật khẩu tại một thời điểm cho login đó. Nhóm vận hành cập nhật mật khẩu trong database rồi cập nhật vault, nhưng không restart ứng dụng. Hệ thống vẫn phục vụ trong 20 phút, sau đó bắt đầu có lỗi khi mở kết nối mới.

Hãy xác định:

- Vì sao 20 phút hoạt động chưa chứng minh migration thành công?
- Nếu restart toàn bộ replica ngay, hệ thống có những rủi ro nào?
- Làm thế nào xác nhận bộ username/password và database target đang đồng bộ?
- Job cuối tuần cần được xử lý trước khi đóng migration như thế nào?
- Nếu không hỗ trợ hot reload, có thể chọn những chiến lược cutover nào?
- Trong trường hợp mật khẩu cũ đã bị lộ, giới hạn của rollback là gì?

Gợi ý phân tích:

Các kết nối cũ có thể che giấu lỗi tại thời điểm tạo kết nối mới. Restart đồng loạt có thể làm mọi replica đồng thời phải xác thực lại, từ đó biến một lỗi đang diễn ra từng phần thành gián đoạn rộng. Cần kiểm tra một candidate consumer qua đường cấp phát thật, tạo kết nối mới và xác nhận nghiệp vụ trước khi mở rộng.

Vì tình huống chỉ có một mật khẩu hợp lệ cho login, hai secret version ở vault không tạo ra một cửa sổ hai mật khẩu tại database. Nhóm phải điều phối trạng thái database và provider, hoặc chuẩn bị chiến lược login mới nếu phù hợp. Job cuối tuần là consumer thật và cần phép thử đại diện cùng owner xác nhận. Khi secret cũ đã bị lộ, hướng phục hồi phải dùng credential an toàn thay vì khôi phục secret đó.

Migrate database credential thành công là chuyển được toàn bộ vòng đời truy cập: từ nhận diện consumer, cấp quyền và cấp phát secret, đến tạo kết nối, luân chuyển, thu hồi và phục hồi. Vault là một thành phần của vòng đời này; sự ổn định của ứng dụng và bằng chứng kiểm soát mới cho thấy quá trình chuyển đổi đã hoàn tất.
