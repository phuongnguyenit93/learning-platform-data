# Cloud IAM role

## 1. Cloud IAM role trong quản lý truy cập đặc quyền

Cloud IAM role là một cách biểu diễn tập quyền trong hệ thống quản lý danh tính và truy cập của môi trường cloud. Role giúp tổ chức cấp quyền theo chức năng thay vì cấu hình rời rạc mọi thao tác cho từng tài khoản.

Tuy nhiên, từ “role” không có cùng mô hình kỹ thuật ở mọi nền tảng. Có hệ thống dùng role như một tập permission để gán cho principal tại một scope. Có hệ thống còn dùng role như một danh tính mà principal khác có thể nhận quyền sử dụng trong một phiên. Vì vậy, không được lấy cách một sản phẩm xử lý role để suy ra mọi sản phẩm khác.

Trong bài học, Cloud IAM role được phân tích qua ba câu hỏi chung:

1. Role cho phép thực hiện những hành động nào?
2. Chủ thể nào được dùng role, tại phạm vi nào và dưới điều kiện nào?
3. Những chính sách và cơ chế nào quyết định quyền hiệu lực của yêu cầu thực tế?

Đối với PAM, một role trở thành đối tượng cần kiểm soát đặc quyền khi nó cho phép quản trị tài nguyên, quản lý quyền của người khác, tiếp cận dữ liệu nhạy cảm, sử dụng credential mạnh hoặc tạo một đường truy cập có ảnh hưởng tương đương.

Ví dụ, role không có tên “Administrator” nhưng cho phép sửa mã của một workload đang giữ quyền đọc secret có thể tạo đường tiếp cận secret gián tiếp. Ngược lại, một role tên “Admin” của một chức năng hẹp không tự có quyền quản trị toàn bộ cloud.

Mục tiêu của bài là giúp bạn kiểm kê, phân tích và vận hành role theo least privilege; cấp quyền tạm thời đúng nhu cầu; phân biệt quyền con người với workload; và thu bằng chứng về sử dụng lẫn kết thúc quyền.

## 2. Những khái niệm phải phân biệt

| Khái niệm | Ý nghĩa trong bài | Ví dụ minh họa |
|---|---|---|
| Principal | Chủ thể được hệ thống nhận diện khi đánh giá truy cập | Người dùng liên kết, workload, tài khoản dịch vụ |
| Permission | Năng lực thực hiện một hành động trên một loại tài nguyên | Đọc cấu hình dịch vụ, sửa chính sách truy cập |
| Role definition | Định nghĩa tập quyền được đóng gói | Role vận hành dịch vụ |
| Role assignment hoặc binding | Quan hệ cấp role cho principal tại một scope | Nhóm Operations nhận role ở môi trường thử nghiệm |
| Trust hoặc điều kiện nhận quyền | Quy định ai được dùng hay nhận quyền từ một danh tính hoặc role | Chỉ workload từ nguồn đã được xác minh |
| Session | Ngữ cảnh truy cập tồn tại trong một khoảng thời gian | Phiên quản trị sau khi kích hoạt |
| Credential | Bằng chứng kỹ thuật được dùng để xác thực hoặc ký yêu cầu | Token, khóa truy cập, chứng thư |
| Resource scope | Tập tài nguyên mà quyền có thể áp dụng | Một dự án, account, dịch vụ hoặc tài nguyên cụ thể |
| Effective access | Khả năng thực sự thực hiện yêu cầu sau khi xét các chính sách liên quan | Có được sửa cấu hình tài nguyên production tại thời điểm này không |

Tên gọi chính xác và cách liên kết các khái niệm phụ thuộc nền tảng. Khi triển khai thật, cần ánh xạ chúng vào mô hình IAM thực tế của sản phẩm.

### 2.1. Role definition khác role assignment

Đổi người được gán role và đổi nội dung role là hai thay đổi đặc quyền khác nhau.

Nếu thêm permission quản lý secret vào một custom role đang cấp cho nhiều đội, toàn bộ principal có liên quan có thể nhận thêm năng lực mà không phát sinh phép gán role mới.

Vì vậy, kiểm toán chỉ theo dõi sự kiện “gán role cho người dùng” chưa đủ. Phải quản lý cả thay đổi định nghĩa role, điều kiện nhận quyền, chính sách tài nguyên và các cơ chế có thể làm quyền hiệu lực thay đổi.

### 2.2. Có role không đồng nghĩa luôn được thực hiện mọi thao tác trong role

Một thao tác có thể còn chịu điều kiện theo tài nguyên, môi trường, trạng thái phiên, chính sách tổ chức hoặc giới hạn của danh tính.

Ngược lại, không thấy một role gán trực tiếp cho người dùng cũng chưa chứng minh họ không có quyền. Họ có thể nhận quyền qua nhóm, kế thừa scope, liên kết danh tính, ủy quyền hoặc một workload mà họ điều khiển.

Cần phân tích đường quyền đầy đủ thay vì chỉ đọc danh sách role trên một trang giao diện.

## 3. Đọc một role theo hai phía: người được dùng và việc được làm

Một cấu hình quyền có thể chặt ở phía permission nhưng lỏng ở phía người nhận, hoặc ngược lại.

### Phía nhận quyền

Cần xác định:

- Principal nào được phép dùng role?
- Nguồn danh tính nào được tin cậy?
- Có qua nhóm hoặc một quan hệ ủy quyền nào không?
- Có cần kích hoạt, xác thực bổ sung hoặc phê duyệt không?
- Scope nhận quyền được xác lập từ dữ liệu nào?
- Credential hoặc session được cấp trong bao lâu?

### Phía hành động

Cần xác định:

- Được thực hiện những thao tác nào?
- Trên tài nguyên và môi trường nào?
- Có được sửa chính sách IAM, trust hoặc danh tính không?
- Có thể đọc dữ liệu hay chỉ quản lý tài nguyên?
- Có thể làm workload khác hành động thay mình không?
- Có thể tạo credential hoặc quyền tồn tại lâu hơn phiên hiện tại không?

Một role chỉ có permission hẹp vẫn có thể bị sử dụng trái phép nếu điều kiện nhận quyền tin cậy một nguồn quá rộng. Một role có điều kiện nhận quyền chặt vẫn nguy hiểm nếu người sử dụng hợp lệ nhận nhiều permission hơn nhu cầu.

### Sơ đồ quan hệ

~~~mermaid
flowchart LR
    A[Người hoặc workload] --> B[Xác minh danh tính và nguồn tin cậy]
    B --> C[Quan hệ cấp quyền hoặc kích hoạt]
    C --> D[Role và phạm vi]
    D --> E[Đánh giá yêu cầu cụ thể]
    F[Chính sách tổ chức và tài nguyên] --> E
    G[Ngữ cảnh phiên và điều kiện] --> E
    E --> H[Cho phép hoặc từ chối]
~~~

Đây là mô hình khái niệm, không mô tả thứ tự đánh giá bắt buộc của mọi nhà cung cấp.

## 4. Phân tích quyền hiệu lực

Một kết luận quyền phải gắn với yêu cầu cụ thể:

> Principal P có được thực hiện hành động A lên tài nguyên R, trong ngữ cảnh C, tại thời điểm T hay không?

Việc biết P giữ role X chỉ là một phần đầu vào.

Các nguồn cần đối soát có thể gồm:

| Nguồn quyền hoặc giới hạn | Câu hỏi cần kiểm tra |
|---|---|
| Gán trực tiếp | Principal được cấp role nào tại scope nào? |
| Nhóm và quan hệ kế thừa | Có nhóm lồng, nhóm liên kết hoặc gán từ scope cha không? |
| Chính sách trên tài nguyên | Tài nguyên có cấp quyền cho một principal hoặc nguồn ngoài không? |
| Cơ chế nhận role hoặc ủy quyền | Principal có thể dùng danh tính mạnh hơn không? |
| Chính sách cấp tổ chức | Có giới hạn hoặc điều kiện áp dụng từ cấp quản lý cao hơn không? |
| Giới hạn của phiên hoặc danh tính | Quyền được cấp cho phiên có bị thu hẹp thêm không? |
| Điều kiện yêu cầu | Tài nguyên, nguồn, nhãn và trạng thái xác thực có thỏa mãn không? |
| Chính sách tại dịch vụ đích | Dịch vụ có lớp quyền riêng ngoài IAM chung không? |
| Cache và trạng thái token | Thay đổi quyền được nhận biết vào thời điểm nào? |

Không dùng một công thức hợp hoặc giao đơn giản để khẳng định quyền hiệu lực trên mọi cloud. Các nền tảng có mô hình kế thừa, từ chối, chính sách tài nguyên và xử lý phiên khác nhau.

Cách làm đáng tin cậy là xác định các cơ chế có liên quan trong nền tảng cụ thể, rồi kiểm chứng bằng phân tích chính sách và yêu cầu thực tế trong môi trường được phép.

### Ví dụ: quyền từ scope cha

Minh được gán role đọc tại một dự án, nhưng một nhóm của Minh lại giữ role quản trị từ scope cha có ảnh hưởng tới dự án đó.

Nếu chỉ rà soát gán quyền ở dự án, người kiểm toán có thể kết luận Minh chỉ được đọc. Cần truy vết cả nguồn quyền kế thừa và xác định nó có thật sự áp dụng cho tài nguyên đang xét hay không.

Xóa phép gán đọc cục bộ không giải quyết được role quản trị từ scope cha.

## 5. Xác định scope trước khi chọn role

Một yêu cầu “cần cloud admin” chưa đủ để cấp quyền. Hãy chuyển nó thành tập tác vụ có thể kiểm chứng.

Ví dụ nhu cầu:

> Kỹ sư cần cập nhật cấu hình cân bằng tải của ứng dụng Orders tại staging và đọc trạng thái để xác minh.

Từ đó cần xác định:

1. Tài nguyên đích và các tài nguyên phụ thuộc.
2. Thao tác đọc cần để tìm hoặc xác minh tài nguyên.
3. Thao tác ghi thực sự cần thiết.
4. Môi trường và scope nhỏ nhất hệ thống hỗ trợ phù hợp nhu cầu.
5. Điều kiện kích hoạt và thời hạn.
6. Các quyền không được phép phát sinh từ tác vụ.

| Mô tả | Đánh giá |
|---|---|
| Quản trị cloud | Quá rộng để hiểu nhu cầu |
| Quản trị account thử nghiệm | Đã có scope nhưng vẫn thiếu giới hạn hành động |
| Sửa cấu hình dịch vụ Orders tại staging | Gần với tác vụ, cần định danh tài nguyên và thao tác |
| Sửa tập thuộc tính đã duyệt của tài nguyên Orders trong cửa sổ bảo trì | Rõ hơn, cần xác minh nền tảng có thực thi được giới hạn thuộc tính hay không |

Không phải mọi permission đều hỗ trợ giới hạn tới từng tài nguyên hoặc từng thuộc tính. Nếu nền tảng không biểu đạt được giới hạn mong muốn, phải ghi nhận phần quyền rộng hơn và thiết kế quy trình hoặc cơ chế thực thi bổ sung.

Không mô tả một role là “chỉ sửa trường X” nếu cấu hình thực tế cho phép sửa toàn bộ đối tượng.

## 6. Least privilege và lựa chọn role dựng sẵn hoặc tùy chỉnh

### 6.1. Role dựng sẵn

Role dựng sẵn có thể giúp giảm công bảo trì và phù hợp với nhóm tác vụ phổ biến. Tuy nhiên, tên role không đủ để chứng minh phù hợp least privilege.

Cần kiểm tra:

- Permission thực tế và phạm vi áp dụng.
- Khả năng thay đổi tập quyền theo vòng đời sản phẩm.
- Những thao tác quản lý danh tính hoặc chính sách đi kèm.
- Quyền đọc dữ liệu, secret hoặc khóa.
- Các permission phụ trợ rộng hơn nhu cầu.

Nếu role được nhà cung cấp duy trì, cần có cách phát hiện thay đổi quan trọng của role đang sử dụng. Một quyết định cấp quyền hợp lý hôm nay vẫn cần được rà soát khi nội dung role thay đổi.

### 6.2. Custom role

Custom role có thể biểu đạt tác vụ hẹp hơn nhưng tạo trách nhiệm bảo trì:

- Theo dõi permission mới hoặc bị thay đổi.
- Giữ đủ quyền phụ trợ để tác vụ vận hành.
- Quản lý revision và đánh giá tác động.
- Tránh sao chép role rộng rồi chỉ đổi tên.
- Kiểm thử cả ca được phép và bị từ chối.

Không nên giải quyết lỗi thiếu quyền bằng cách liên tục thêm permission rộng mà không tìm nguyên nhân. Có thể lỗi đến từ scope, điều kiện, nguồn danh tính hoặc lớp quyền tại dịch vụ đích.

### 6.3. Role chỉ đọc không mặc nhiên vô hại

Quyền đọc có thể tiếp cận dữ liệu nhạy cảm, cấu hình chứa thông tin bí mật hoặc metadata giúp hiểu hệ thống.

Cần phân biệt:

- Đọc cấu hình quản trị.
- Đọc nội dung dữ liệu.
- Đọc giá trị secret.
- Sử dụng khóa để giải mã hoặc ký.
- Liệt kê tài nguyên và thông tin danh tính.

Không coi một role là ít rủi ro chỉ vì không có thao tác ghi.

## 7. Các đường nâng quyền gián tiếp

Đặc quyền không chỉ nằm ở permission gán role.

| Năng lực | Đường tác động có thể có | Giới hạn cần đánh giá |
|---|---|---|
| Sửa định nghĩa custom role | Mở rộng quyền cho principal đang giữ role | Ai sửa được, ai duyệt và ai bị ảnh hưởng? |
| Sửa trust hoặc điều kiện liên kết | Cho nguồn mới nhận quyền | Nguồn danh tính và thuộc tính nào được tin cậy? |
| Tạo credential cho danh tính khác | Truy cập dưới quyền danh tính đó | Có được tạo, tải xuống hoặc sử dụng credential không? |
| Sử dụng hoặc giả lập danh tính workload | Thực hiện thao tác với quyền workload | Được dùng danh tính nào, trong tác vụ nào? |
| Gắn danh tính vào compute | Làm mã trên compute sử dụng danh tính mạnh | Có kiểm soát danh tính được gắn và mã được chạy không? |
| Sửa mã hoặc cấu hình triển khai | Điều khiển workload đang giữ quyền mạnh | Chuỗi review, build và deploy có bảo vệ không? |
| Sửa chính sách trên tài nguyên | Cấp quyền truy cập cho chính mình hoặc bên khác | Có kiểm soát principal, scope và điều kiện không? |
| Sửa quyền khóa hoặc secret | Mở đường đến dữ liệu hoặc credential khác | Quản trị khóa và sử dụng khóa có được phân tách thực tế không? |
| Sửa hệ thống audit | Giảm khả năng phát hiện và quy trách nhiệm | Bằng chứng có được bảo vệ ở phạm vi độc lập không? |

Bảng mô tả khả năng cần phân tích. Một permission riêng lẻ chưa chắc thực hiện được toàn bộ đường nâng quyền; có thể cần thêm quyền, tài nguyên hoặc điều kiện.

Ví dụ, khả năng gắn một danh tính workload chỉ tạo đường tác động đáng kể khi chủ thể còn có cách điều khiển mã hoặc tác vụ sử dụng danh tính đó. Phải xem tổ hợp quyền hiệu lực, không kết luận chỉ từ một tên permission.

### Tách quyền sử dụng và quyền quản trị danh tính

Một workload cần gọi API không có nghĩa nó cần sửa role của chính mình. Người vận hành một dịch vụ không mặc nhiên cần tạo credential cho danh tính runtime.

Nếu một principal vừa được thay mã workload, vừa được chọn bất kỳ danh tính mạnh nào cho workload, nó có thể vượt xa phạm vi “vận hành ứng dụng”. Đây là tổ hợp cần được nhận diện khi phân tách trách nhiệm.

## 8. Quyền con người: liên kết danh tính và JIT

### 8.1. Tách đăng nhập khỏi cấp đặc quyền

Xác thực thành công chỉ chứng minh danh tính theo cơ chế được dùng. Nó không tự chứng minh người dùng cần quyền quản trị production.

Một quy trình cho con người nên làm rõ:

- Nguồn danh tính và trạng thái nhân sự.
- Tài khoản cá nhân có thể quy trách nhiệm.
- Quyền thường ngày cần thiết.
- Quyền đủ điều kiện kích hoạt khi có nhu cầu.
- Xác thực bổ sung và phê duyệt theo rủi ro.
- Scope, mục đích và thời hạn kích hoạt.
- Điều kiện kết thúc hoặc thu hồi.

Liên kết đăng nhập từ một hệ thống danh tính tập trung giúp quản lý vòng đời, nhưng không tự làm mọi role trong cloud tuân thủ least privilege.

### 8.2. Đủ điều kiện không đồng nghĩa đang có quyền

Một người có thể nằm trong tập được phép yêu cầu role nhưng chỉ nhận quyền hiệu lực khi kích hoạt hợp lệ.

~~~text
Đủ điều kiện
    -> Yêu cầu gắn với tác vụ
    -> Kiểm tra scope và xung đột
    -> Phê duyệt nếu chính sách yêu cầu
    -> Kích hoạt có thời hạn
    -> Thực hiện, ghi bằng chứng
    -> Kết thúc và kiểm chứng
~~~

Nếu quyền đã được cấp thường trực bằng một đường khác, cơ chế kích hoạt mới không loại bỏ quyền thường trực đó. Trước khi công bố JIT, phải đối soát các phép gán và đường nhận quyền song song.

### 8.3. Kiểm soát xung đột trách nhiệm

Người yêu cầu quyền không nên tự tạo điều kiện đủ để duyệt yêu cầu của mình đối với tác vụ cần sự độc lập.

Cần xét cả người có thể:

- Đổi thành viên nhóm phê duyệt.
- Sửa mapping từ nhóm sang role.
- Đổi chính sách kích hoạt.
- Tạo một role thay thế.
- Sửa nguồn danh tính được tin cậy.

Nếu cùng một người có thể làm các bước này không qua kiểm soát, việc hiển thị hai vai trò “người yêu cầu” và “người duyệt” chưa tạo ra phân tách thực tế.

## 9. Quyền workload và credential ngắn hạn

Workload thường không có người ngồi xác thực từng lần chạy. Cần thiết kế danh tính máy phù hợp thay vì đưa tài khoản quản trị của con người vào ứng dụng.

### 9.1. Một danh tính cho một ranh giới trách nhiệm phù hợp

Có thể cần tách danh tính theo:

- Ứng dụng hoặc nhóm chức năng.
- Môi trường thử nghiệm và production.
- Runtime, triển khai và migration.
- Nguồn chạy tin cậy và nguồn xử lý mã chưa tin cậy.
- Miền tổ chức hoặc đơn vị sở hữu.

Không nhất thiết tạo một danh tính cho từng tiến trình nhỏ. Mục tiêu là giới hạn tác động và quản lý được chủ sở hữu, quyền cùng vòng đời.

Một danh tính dùng chung cho mọi ứng dụng khiến việc thu hồi một workload gặp sự cố có thể ảnh hưởng cả hệ thống. Nó cũng làm khó xác định nguồn thực hiện thao tác nếu bằng chứng không phân biệt được từng workload.

### 9.2. Liên kết danh tính workload

Nếu môi trường hỗ trợ liên kết danh tính, workload có thể dùng bằng chứng từ một nguồn được tin cậy để nhận credential phù hợp.

Chính sách cần xác minh đúng:

- Nguồn phát hành bằng chứng.
- Đối tượng mà bằng chứng được phát hành cho.
- Định danh workload hoặc chủ thể được phép.
- Điều kiện ngữ cảnh được nền tảng hỗ trợ và bảo vệ.
- Role và scope được phép cấp.
- Thời hạn và cách ràng buộc phiên với nguồn workload.

Không coi một trường trong request do workload tự khai là thuộc tính đã được xác minh. Ngay cả thuộc tính nằm trong token có chữ ký cũng cần được hiểu đúng: ai kiểm soát nguồn tạo thuộc tính đó, và nó có đủ phân biệt nguồn được phép hay không?

Ví dụ, một tên môi trường production không có giá trị bảo vệ nếu mọi người tạo job đều tự đặt được tên đó rồi nhận cùng credential.

### 9.3. Credential ngắn hạn không thay cho permission hẹp

Một credential chỉ sống vài phút vẫn có thể tạo quyền tồn tại lâu hơn nếu được phép sửa IAM, tạo khóa mới hoặc đổi trust.

Ngược lại, permission hẹp nhưng credential dài hạn bị phát tán có thể bị sử dụng liên tục trong thời gian dài.

Cần quản lý cả:

1. Ai hoặc workload nào nhận được credential.
2. Credential có quyền và scope gì.
3. Credential được dùng trong bao lâu.
4. Có thể nhận thêm credential mới bằng đường nào.
5. Có thể tạo hiện vật nào tồn tại sau khi credential hết hạn.

### 9.4. Vai trò của vault

Vault có thể hỗ trợ lưu trữ, cấp phát, rotate và kiểm soát credential khi kiến trúc cần bí mật được quản lý tập trung.

Tuy nhiên, việc một credential được lưu trong vault không làm role tại cloud tự trở nên hẹp. Nếu credential có quyền quản trị rộng, người hoặc workload được lấy credential vẫn có thể nhận phạm vi tác động đó.

Khi có cơ chế danh tính workload phù hợp, cần đánh giá việc giảm bí mật dài hạn. Khi vẫn phải dùng credential lưu trữ, phải có chủ sở hữu, kiểm soát truy xuất, rotation, thu hồi và đối soát việc sử dụng tại cloud.

Không ghi credential vào log, file cấu hình công khai, cache build hoặc artifact. Cơ chế che chuỗi log chỉ là một lớp hỗ trợ, không chứng minh bí mật chưa bị truyền qua đường khác.

## 10. Quyền xuyên scope và xuyên miền danh tính

Trong tổ chức nhiều account, dự án, subscription hoặc miền quản lý, người dùng có thể nhận quyền tại scope khác qua một quan hệ tin cậy hoặc gán quyền liên miền.

Không nên nghĩ rằng đăng nhập một nơi chỉ có thể tác động tài nguyên tại nơi đó.

### Các câu hỏi cần trả lời

- Miền nguồn xác thực principal nào?
- Miền đích tin cậy principal hoặc thuộc tính nào từ miền nguồn?
- Nhóm hoặc mapping nào biến danh tính thành quyền?
- Ai được sửa cấu hình tin cậy ở mỗi phía?
- Scope nào thực sự áp dụng tại đích?
- Bằng chứng có liên kết được phiên tại đích với chủ thể nguồn không?
- Khi thu hồi ở nguồn, quyền và phiên tại đích thay đổi như thế nào?

Một cấu hình tin cậy quá rộng có thể làm tất cả người dùng hoặc workload trong miền nguồn trở thành ứng viên nhận quyền, trong khi nhu cầu thực tế chỉ dành cho một nhóm nhỏ.

### Chuỗi nhận quyền

Một principal có thể đi qua nhiều bước ủy quyền hoặc nhận danh tính, nếu nền tảng hỗ trợ:

~~~text
Người dùng
  -> Quyền vận hành trung gian
  -> Danh tính triển khai
  -> Thao tác lên tài nguyên production
~~~

Phải phân tích cả đường đi và khả năng nối tiếp. Không giả định thời hạn, thuộc tính nhận diện nguồn hoặc điều kiện bảo vệ tự giữ nguyên qua mọi bước.

Cũng không dùng tên phiên do người gọi tự đặt làm bằng chứng duy nhất về người thực hiện. Cần các định danh nguồn và bản ghi liên kết có thể xác minh.

## 11. Hồ sơ kiểm kê một Cloud IAM role

Một inventory hữu ích cần mô tả cả ý nghĩa nghiệp vụ và cấu hình kỹ thuật.

| Nhóm | Nội dung nên quản lý |
|---|---|
| Định danh | Role, phiên bản hoặc revision, nền tảng và miền quản lý |
| Mục đích | Tác vụ mà role phục vụ, lý do cần đặc quyền |
| Chủ sở hữu | Đội chịu trách nhiệm và người quyết định thay đổi |
| Permission | Hành động, tài nguyên, giới hạn và phụ thuộc |
| Nguồn nhận quyền | Principal, nhóm, trust, ủy quyền và liên kết |
| Scope | Môi trường, đơn vị tổ chức và tập tài nguyên |
| Vòng đời | Gán thường trực hay kích hoạt, thời hạn và điều kiện kết thúc |
| Xung đột | Tổ hợp quyền có thể tự cấp hoặc tự duyệt |
| Bằng chứng | Nguồn audit, mã yêu cầu và lịch sử review |
| Ngoại lệ | Quyền rộng hơn nhu cầu, lý do, thời hạn và kế hoạch xử lý |

Mẫu dưới đây chỉ là hồ sơ quản trị minh họa. Đây không phải cấu hình IAM nhập trực tiếp vào một cloud.

~~~yaml
role_governance_record:
  role_reference: example-orders-operations
  definition_revision: revision-4
  platform_reference: "<nền tảng cần ánh xạ>"
  administrative_domain: "<miền quản lý>"
  accountable_owner: team-orders
  purpose: update-approved-service-configuration

  scope:
    application: orders
    environment: production
    resource_set_reference: "<tập tài nguyên được duyệt>"

  intended_capabilities:
    - read-service-status
    - update-approved-operational-configuration

  excluded_capabilities:
    - manage-iam-policy
    - change-identity-trust
    - create-long-lived-credentials
    - change-runtime-identity
    - read-secret-values
    - disable-audit

  human_access:
    eligible_group_reference: "<nhóm được phép yêu cầu>"
    activation_required: true
    independent_approval: true
    request_reference_required: true
    end_time_required: true

  workload_access:
    separate_identity_required: true
    trusted_source_reference: "<nguồn workload đã xác minh>"

  revocation:
    new_credential_issuance: "<cơ chế ngăn cấp mới>"
    existing_sessions: "<cơ chế xử lý theo nền tảng>"
    verification_plan_reference: VERIFY-EX-017

  evidence:
    review_reference: REVIEW-EX-017
    audit_destination_reference: "<nơi bảo vệ bằng chứng>"
~~~

Các mục loại trừ trong hồ sơ không phải một chính sách từ chối đã được hệ thống thực thi. Cần chuyển chúng thành cấu hình nền tảng phù hợp và kiểm chứng những đường gián tiếp có thể vượt ý định.

Ví dụ, “không đọc secret trực tiếp” chưa đủ nếu role đồng thời được sửa mã workload có quyền đọc secret.

## 12. Quy trình cấp quyền theo tác vụ

### Bước 1: làm rõ nhu cầu

Yêu cầu phải chỉ ra ứng dụng, tài nguyên, hành động, môi trường và khoảng thời gian. Không chấp nhận chỉ dựa vào chức danh như “trưởng nhóm cần administrator”.

### Bước 2: chọn hoặc thiết kế role

So sánh role sẵn có với nhu cầu. Nếu phải dùng role rộng hơn, xác định phần chênh lệch và kiểm soát phù hợp.

Đừng thêm permission quản lý IAM chỉ vì một thao tác triển khai hiện tại đang làm cả việc tạo hạ tầng lẫn cấp quyền. Có thể cần tách tác vụ và danh tính thực thi.

### Bước 3: kiểm tra principal và đường nhận quyền

Xác minh đúng principal, nhóm, nguồn liên kết và điều kiện nhận quyền. Kiểm tra principal có đang giữ quyền rộng qua đường khác không.

### Bước 4: phê duyệt và kích hoạt

Phê duyệt phải gắn với role, scope, chủ thể, mục đích và thời hạn. Nếu thay scope hoặc role sau khi duyệt, cần đánh giá lại theo chính sách thay vì dùng một mã phê duyệt chung.

### Bước 5: thực hiện và ghi bằng chứng

Liên kết người yêu cầu, phiên nhận quyền, credential được cấp và thao tác tại đích. Ghi nhận cả thành công, thất bại và yêu cầu bị từ chối có ý nghĩa điều tra.

### Bước 6: kết thúc và kiểm chứng

Xử lý phép gán, kích hoạt, khả năng nhận credential mới, phiên cũ và hiện vật có thể tạo truy cập tồn dư. Kết luận dựa trên quyền hiệu lực, không chỉ trạng thái biểu mẫu.

## 13. Thu hồi role, phiên và credential

### 13.1. Có nhiều đồng hồ vòng đời

Các thời điểm sau không nhất thiết trùng nhau:

- Thời điểm quyền đủ điều kiện bị gỡ.
- Thời điểm kích hoạt JIT kết thúc.
- Thời điểm ngừng cấp credential mới.
- Thời điểm credential đã cấp hết hiệu lực.
- Thời điểm dịch vụ đích nhận biết chính sách mới.
- Thời điểm phiên ứng dụng hoặc tác vụ nền kết thúc.

Kiến trúc cần xác định từng thời điểm và giới hạn chấp nhận. Không kết luận thu hồi tức thì chỉ vì một phép gán đã biến mất khỏi giao diện.

### 13.2. Những đối tượng cần đối soát

| Đối tượng | Kiểm tra sau thu hồi |
|---|---|
| Gán role trực tiếp | Đã bỏ đúng principal tại đúng scope chưa? |
| Nhóm và scope cha | Có đường cấp tương đương còn tồn tại không? |
| Trust và ủy quyền | Có còn khả năng nhận lại danh tính mạnh không? |
| Cấp credential mới | Nguồn bị thu hồi có còn lấy được credential không? |
| Credential và phiên cũ | Hệ thống đích xử lý theo cơ chế nào và trong bao lâu? |
| Role hoặc tài khoản được tạo | Có tạo quyền tồn dư trong thời gian được cấp không? |
| Workload và tác vụ nền | Có hành động đã gửi hoặc mã vẫn chạy dưới danh tính khác không? |
| Quyền trên tài nguyên | Có phép cấp trực tiếp không phụ thuộc role vừa gỡ không? |

Một số hệ thống đánh giá lại chính sách trên từng yêu cầu; một số cơ chế giữ thông tin quyền trong token hoặc cache với đặc điểm khác. Phải kiểm chứng theo nền tảng và đường truy cập thực tế.

Không mặc định xóa mọi credential của toàn tổ chức khi chỉ một role bị thu hồi. Chọn đối tượng dựa trên phạm vi sự cố và khả năng thu hồi của hệ thống.

### 13.3. Kế hoạch kiểm chứng thu hồi

Trong môi trường được phép, chuẩn bị danh tính thử nghiệm và hành động quản trị ít tác động. Sau đó kiểm tra:

1. Yêu cầu nhận quyền hoặc credential mới bị từ chối.
2. Phiên tồn tại trước thu hồi có kết quả đúng với thiết kế.
3. Thao tác qua API và công cụ dòng lệnh chịu cùng ranh giới.
4. Quyền từ nhóm, scope cha và ủy quyền không tạo đường thay thế ngoài ý định.
5. Quyền không đặc quyền còn hợp lệ vẫn hoạt động nếu chính sách yêu cầu.
6. Audit ghi được các sự kiện cần đối chiếu.

Nếu có khoảng trễ, ghi nhận thời điểm bắt đầu, quan sát và kết thúc. Không tự đặt một con số đảm bảo chung cho mọi dịch vụ cloud.

## 14. Audit: từ chủ thể nguồn đến hành động tài nguyên

Một sự kiện cấp token không tự chứng minh token đã được sử dụng, và một sự kiện thao tác tài nguyên chưa chắc cho biết người thật phía sau một danh tính trung gian.

Bằng chứng nên liên kết được:

~~~text
Chủ thể nguồn
  -> Yêu cầu và phê duyệt
  -> Gán role hoặc kích hoạt
  -> Nhận danh tính hay credential
  -> Thao tác tại tài nguyên đích
  -> Kết quả và kết thúc quyền
~~~

Những trường hữu ích gồm:

- Định danh principal nguồn và principal thực thi.
- Định danh role, scope và phiên có thể đối soát.
- Mã yêu cầu, mã kích hoạt và mã tương quan.
- Hành động, tài nguyên và kết quả.
- Thời gian với thông tin múi giờ hoặc chuẩn thời gian thống nhất.
- Nguồn workload hoặc nguồn danh tính đã được xác minh.
- Revision chính sách hoặc bản chụp cần thiết để hiểu quyết định.
- Sự kiện thay đổi role, trust, nhóm và chính sách audit.

Khả năng ghi log của thao tác quản trị và thao tác dữ liệu có thể khác nhau. Cần xác định những loại sự kiện nào thực sự được thu thập trong kiến trúc đang dùng, thay vì mặc định tất cả đã có.

Không ghi token, khóa riêng, mật khẩu hoặc toàn bộ giá trị secret vào log để tạo “bằng chứng đầy đủ”.

### Bảo vệ bằng chứng

Nếu người quản trị tài nguyên có thể xóa hoặc sửa log tại cùng phạm vi, cần một đích thu thập được bảo vệ độc lập phù hợp.

Cần xem xét quyền:

- Thay cấu hình thu thập.
- Đổi đích xuất log.
- Xóa dữ liệu lưu trữ.
- Sửa chính sách lưu giữ.
- Thay khóa bảo vệ hoặc quyền đọc bằng chứng.

Một role “không được xóa log” vẫn có thể làm thiếu bằng chứng nếu nó đổi đích xuất hoặc vô hiệu hóa nguồn thu thập.

### Tín hiệu cần điều tra

- Thêm permission nhạy cảm vào một role đã cấp rộng.
- Mở trust sang principal hoặc nguồn danh tính mới.
- Tạo credential cho danh tính có quyền mạnh.
- Dùng role ngoài scope hoặc thời gian gắn với yêu cầu.
- Sửa workload rồi thực hiện thao tác nhạy cảm bằng danh tính workload.
- Thay chính sách audit gần thời điểm sử dụng đặc quyền.
- Có thao tác tại đích nhưng không đối chiếu được chủ thể nguồn.

Các tín hiệu này cần được đánh giá cùng bối cảnh. Một thay đổi hợp lệ vẫn có thể tạo cùng sự kiện; mục tiêu là đủ bằng chứng để phân biệt.

## 15. Tình huống thực tế: vận hành Orders trên cloud

### Bối cảnh

Một đội quản lý Orders tại staging và production. Ban đầu, mọi kỹ sư trong nhóm Operations đều được gán một role quản trị rộng từ scope cha.

Đội muốn chuyển sang quyền vận hành tạm thời cho production. Một kỹ sư cần sửa một cấu hình vận hành đã được phê duyệt và xem trạng thái sau thay đổi.

### Những vấn đề cần phát hiện

Nếu chỉ thêm một role JIT mới mà giữ role quản trị từ scope cha, quyền production thực tế vẫn thường trực.

Nếu người dùng có thể sửa định nghĩa role JIT, họ có thể tự mở rộng permission trước khi kích hoạt.

Nếu role vận hành được đổi runtime identity hoặc sửa mã ứng dụng, nó có thể có đường tác động lớn hơn tác vụ cấu hình.

Nếu người dùng bị bỏ khỏi nhóm nguồn nhưng vẫn có phiên hoặc gán trực tiếp tại đích, quy trình thu hồi chưa chắc hoàn tất.

### Thiết kế minh họa

Đội thực hiện kiểm kê các nguồn quyền trước. Họ tách quyền staging thường ngày khỏi quyền production và xử lý gán quản trị rộng theo kế hoạch đã duyệt.

Role vận hành production chỉ chứa các thao tác thật sự cần cho tập tài nguyên Orders, trong giới hạn nền tảng hỗ trợ. Role không được quản lý IAM, trust, runtime identity hay cấu hình audit.

Người dùng đủ điều kiện phải tạo yêu cầu gắn với tác vụ. Quyền được kích hoạt có thời hạn; principal nguồn được liên kết với phiên thực thi và thao tác tại đích.

Quản trị role definition và chính sách kích hoạt do một luồng riêng kiểm soát. Đội chuẩn bị quy trình break-glass cho tình huống không dùng được luồng bình thường.

### Ma trận kiểm thử

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Đọc trạng thái Orders trong scope được phép | Thành công nếu role cho phép |
| Sửa cấu hình trước kích hoạt | Bị từ chối |
| Sửa cấu hình đúng scope sau kích hoạt | Thành công |
| Sửa tài nguyên Payments | Bị từ chối |
| Mở rộng role definition | Bị từ chối |
| Thay điều kiện trust | Bị từ chối |
| Đổi runtime identity | Bị từ chối |
| Tạo credential cho danh tính mạnh hơn | Bị từ chối |
| Gọi thao tác ngoài thời hạn bằng đường cấp mới | Bị từ chối |
| Sử dụng phiên cũ sau thu hồi | Có kết quả đúng cơ chế đã thiết kế và được ghi nhận |
| Truy vết thao tác tại đích | Đối chiếu được với người nguồn và yêu cầu |

Ca thành công chứng minh tác vụ làm được. Các ca từ chối chứng minh giới hạn mà tổ chức đang tuyên bố.

Nếu role vẫn có quyền rộng do một phép gán khác, bài kiểm thử phải phát hiện và xử lý nguồn đó; không chỉ chỉnh role mới cho đến khi giao diện hiển thị đúng tên.

## 16. Quyền khẩn cấp và khôi phục khả năng quản trị

Quản lý đặc quyền cần xét trường hợp hệ thống danh tính, PAM hoặc luồng phê duyệt bình thường không hoạt động.

Một đường khẩn cấp cần có:

- Mục đích và điều kiện sử dụng rõ ràng.
- Danh tính hoặc cơ chế nhận diện riêng.
- Bảo vệ credential phù hợp.
- Phạm vi và thời hạn theo tình huống.
- Cơ chế ghi nhận và phát hiện sử dụng.
- Rà soát, rotation hoặc thu hồi sau sử dụng.
- Kiểm thử có kiểm soát để xác nhận có thể dùng khi cần.

Không vô hiệu hóa mọi đường khôi phục trước khi kiểm chứng phương án thay thế. Đồng thời, không để tài khoản khẩn cấp trở thành cách đăng nhập thường ngày để bỏ qua JIT.

Sau sự kiện, cần đối soát role, trust, credential, workload và chính sách đã thay đổi. Hết phiên khẩn cấp không tự khôi phục cấu hình trước đó.

## 17. Những lỗi thường gặp

### Tin tên role thay cho permission thực tế

Một role tên “Operator” vẫn có thể chứa thao tác quản lý danh tính. Phải xem định nghĩa và đường tác động thực tế.

### Chỉ kiểm kê role gán trực tiếp

Nhóm, scope cha, chính sách tài nguyên và cơ chế ủy quyền có thể giữ nguyên quyền sau khi gán trực tiếp đã bị xóa.

### Coi trust chặt là đã least privilege

Trust quyết định ai được nhận quyền. Permission và scope quyết định những việc họ có thể làm. Cả hai phía đều cần được thiết kế.

### Dùng tài khoản người cho workload

Danh tính con người và workload có vòng đời, nguồn bằng chứng cùng cơ chế xác thực khác nhau. Dùng chung làm khó thu hồi và quy trách nhiệm.

### Cấp quyền IAM để sửa mọi lỗi truy cập

Lỗi có thể do scope, điều kiện hoặc lớp quyền dịch vụ. Cấp quyền quản trị rộng có thể che nguyên nhân và tạo thêm đường nâng quyền.

### Thêm JIT nhưng không bỏ đường thường trực

Người dùng vẫn có thể đi qua một gán quyền khác. JIT phải được kiểm chứng trên toàn bộ quyền hiệu lực.

### Coi credential hết hạn là đã xử lý mọi hậu quả

Credential có thể đã tạo role, tài khoản, khóa hoặc thay đổi mã. Cần đối soát hiện vật và thay đổi còn tồn tại.

### Nhầm quản trị khóa với khả năng giải mã

Khả năng quản trị và khả năng sử dụng khóa có thể được mô hình hóa khác nhau. Cần kiểm tra chính sách thực tế, bao gồm ai có thể sửa chính sách để tự nhận thêm quyền.

### Chỉ dựa vào mô phỏng chính sách

Phân tích hoặc mô phỏng có ích nhưng có thể không bao phủ mọi lớp quyền và điều kiện thực tế. Cần kết hợp kiểm thử được phép và quan sát tại đích.

## 18. Bài thực hành

Thiết kế Cloud IAM role cho hai ứng dụng Orders và Payments, mỗi ứng dụng có staging và production.

Nhu cầu:

- Đội phát triển được đọc trạng thái tại cả hai môi trường của ứng dụng mình phụ trách.
- Đội vận hành được sửa một tập cấu hình tại staging.
- Production cần quyền kích hoạt theo tác vụ.
- Workload runtime và workload triển khai dùng danh tính riêng.
- Người kiểm toán được đọc bằng chứng cần thiết.
- Một sự cố danh tính nguồn phải có kế hoạch thu hồi tại các scope đích.

Sản phẩm cần có:

1. Danh mục principal con người, nhóm và workload.
2. Ma trận hành động theo ứng dụng, môi trường và scope.
3. Bản phân tích ít nhất hai tổ hợp quyền có thể nâng quyền gián tiếp.
4. Hồ sơ role và nguồn nhận quyền, phân biệt definition với assignment.
5. Luồng JIT cùng người phê duyệt, thời hạn và điều kiện kết thúc.
6. Mô hình cấp credential workload và các thuộc tính được tin cậy.
7. Bảng kiểm thử được phép, từ chối, vượt scope và sau thu hồi.
8. Chuỗi bằng chứng từ chủ thể nguồn tới hành động tài nguyên.
9. Phương án break-glass và đối soát sau sử dụng.

Chỉ thực hành trên môi trường và danh tính được phép. Các ca từ chối nên dùng thao tác ít tác động; không cần truy cập hoặc thay đổi dữ liệu production để chứng minh một permission rộng.

Một phương án đạt phải chỉ ra nơi thực thi từng giới hạn. Nếu cloud không hỗ trợ một điều kiện, hãy ghi rõ phần chưa thực thi và biện pháp xử lý thay vì mô tả hồ sơ quản trị như một chính sách đã chạy.

## 19. Câu hỏi tự kiểm tra

**Cloud IAM role có luôn là một danh tính có thể nhận phiên không?**

Không. Từ role có thể chỉ một tập permission hoặc tham gia một mô hình nhận danh tính, tùy nền tảng. Phải ánh xạ vào cơ chế thực tế.

**Vì sao sửa custom role là thay đổi đặc quyền?**

Vì nó có thể mở rộng khả năng của những principal đang giữ role mà không cần gán quyền mới cho từng principal.

**Có thể kết luận quyền hiệu lực chỉ từ một phép gán trực tiếp không?**

Không. Cần xét nhóm, kế thừa scope, chính sách tài nguyên, ủy quyền, điều kiện phiên và các lớp quyền liên quan.

**Trust policy và permission giải quyết cùng một câu hỏi không?**

Không. Một phía xác định ai và trong điều kiện nào được dùng hoặc nhận quyền; phía còn lại xác định hành động và tài nguyên có thể tác động.

**Role không được đọc secret có chắc không thể tiếp cận secret không?**

Không. Cần xét khả năng sửa workload, dùng danh tính khác hoặc đổi chính sách để tạo đường truy cập gián tiếp.

**Credential ngắn hạn có loại bỏ nhu cầu quản lý vòng đời role không?**

Không. Chủ thể có thể tiếp tục nhận credential mới hoặc tạo quyền tồn dư nếu cơ chế cấp và permission vẫn cho phép.

**Bỏ người dùng khỏi nhóm nguồn có làm mọi phiên tại cloud hết hiệu lực ngay không?**

Không thể mặc định. Phải kiểm tra mô hình liên kết, trạng thái gán quyền, token, phiên và độ trễ theo nền tảng.

**Audit cần giữ gì để quy trách nhiệm qua một danh tính trung gian?**

Cần định danh nguồn đã xác minh và chuỗi sự kiện liên kết yêu cầu, kích hoạt, nhận quyền cùng hành động tại tài nguyên, không chỉ tên phiên do người gọi tự đặt.
