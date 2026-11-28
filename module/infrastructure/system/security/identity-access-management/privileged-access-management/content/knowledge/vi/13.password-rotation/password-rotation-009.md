# Kiểm thử password mới sau rotation trong PAM

## 1. Mục tiêu của việc kiểm thử

Sau khi thay mật khẩu, hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM) cần xác minh **password mới thực sự được đúng nguồn xác thực chấp nhận cho đúng tài khoản, qua một lần xác thực mới**.

Một phản hồi đổi mật khẩu thành công chưa đủ để kết luận điều đó. Vault có thể lưu sai phiên bản, connector có thể tác động nhầm đối tượng hoặc ứng dụng có thể tiếp tục dùng một kết nối cũ.

Kiểm thử cần trả lời riêng những câu hỏi:

1. Đã kết nối tới đúng tài nguyên và xác minh danh tính máy chủ chưa?
2. Tài khoản và nguồn xác thực có đúng phạm vi không?
3. Có thực sự dùng password mới, thay vì credential khác hoặc bản cache không?
4. Nguồn xác thực có chấp nhận lần đăng nhập mới không?
5. Tài khoản có thực hiện được tác vụ cần thiết trong giới hạn quyền không?
6. Consumer đã lấy và sử dụng phiên bản mới chưa?
7. Password cũ, phiên cũ và các đường truy cập khác đã được xử lý theo mục tiêu chưa?

Các kết quả này liên quan nhưng không thể thay thế nhau. Bài học tập trung vào cách thiết kế kiểm thử, phân loại kết quả và lưu bằng chứng, không thực hiện thay đổi trên một nền tảng cụ thể.

## 2. Phân biệt những mức bằng chứng

| Kết quả quan sát | Điều được chứng minh | Điều chưa được chứng minh |
|---|---|---|
| Tác vụ rotation đã chạy | Có một lần thực thi hoặc yêu cầu | Đích đã đổi và password mới dùng được |
| Nguồn báo đã đổi | Nguồn trả kết quả áp dụng theo cơ chế | Consumer đã sử dụng phiên bản mới |
| Vault có phiên bản mới | Dữ liệu quản lý đã được ghi | Nguồn xác thực chấp nhận giá trị đó |
| Client tạo đối tượng kết nối mới | Client đã thực hiện một bước | Có phiên xác thực mới ở tầng giao thức |
| Xác thực mới đúng phương thức thành công | Password được kiểm tra trong ngữ cảnh xác định | Quyền ứng dụng đủ hoặc password cũ hết hiệu lực |
| Tác vụ đại diện thành công | Một chức năng đạt tiêu chí trong phạm vi | Mọi consumer và mọi đường đều đạt |
| Password cũ bị từ chối có căn cứ | Một kiểm tra hoặc trạng thái nguồn xác nhận theo phạm vi | Mọi phiên cũ đã kết thúc |
| Phiên được xác nhận đã đóng | Phiên cụ thể đã kết thúc | Không còn credential hoặc grant khác |

Không nên có một cờ PASS duy nhất mà không biết nó đại diện mức nào.

Ví dụ, một kiểm tra có thể đạt ở mức xác thực password mới nhưng toàn bộ rotation vẫn chưa hoàn tất vì job theo lịch chưa cập nhật. Báo cáo phải giữ được sự khác biệt đó.

## 3. Xác định đối tượng và ngữ cảnh kiểm thử

### 3.1. Tài khoản không chỉ là tên đăng nhập

Cần ràng buộc kiểm thử với:

- Account ID và phạm vi định danh.
- Nguồn xác thực: local, directory, database, issuer hoặc cơ chế tương ứng.
- Target ID, môi trường và endpoint.
- Giao thức và đường truy cập.
- Credential object cùng phiên bản cần kiểm tra.
- Rotation ID hoặc tham chiếu thay đổi.
- Danh tính thực hiện probe và quyền được phép.

Tên đăng nhập giống nhau ở hai môi trường không đủ để chứng minh đã kiểm tra đúng tài khoản. Một endpoint logic cũng có thể dẫn tới nhiều node hoặc nhiều lớp xác thực.

### 3.2. Đường trực tiếp và đường ứng dụng trả lời câu hỏi khác nhau

Kiểm tra trực tiếp tới nguồn có thể giúp xác định password mới có hiệu lực. Kiểm tra theo đường ứng dụng giúp xác định consumer có lấy đúng password và kết nối được qua các lớp liên quan.

Nếu ứng dụng qua proxy, có thể có:

~~~text
Ứng dụng → xác thực với proxy.
Proxy → lấy hoặc giữ credential upstream.
Proxy → xác thực tới hệ thống đích.
~~~

Thành công ở lớp đầu chưa chứng minh lớp sau đã dùng password mới. Cần xác định rõ câu hỏi mà từng probe muốn trả lời.

### 3.3. Phạm vi phải có giới hạn rõ

Không dùng một credential mới để thử trên hàng loạt tài nguyên ngoài kế hoạch. Hoạt động đó có thể gây khóa tài khoản, tạo tải và làm sai phạm vi kiểm chứng.

Những endpoint, node hoặc consumer chưa được kiểm tra cần được giữ ở trạng thái tương ứng, không tự suy rộng từ một lần thành công.

## 4. Lập hợp đồng kiểm thử trước khi rotation

Một kế hoạch nên quy định đầu vào, điều kiện, bước thực hiện và tiêu chí kết quả.

| Nhóm | Nội dung cần xác định |
|---|---|
| Định danh | Account, source, target, môi trường |
| Credential | Tham chiếu phiên bản được phép dùng |
| Phương thức | Password hay luồng nhiều yếu tố có password |
| Tính mới | Cách loại trừ phiên hoặc credential cache không phù hợp |
| Trust | Cách xác minh máy chủ và kênh truyền |
| Hành động | Kiểm tra xác thực và tác vụ đại diện |
| Giới hạn | Timeout, số lần thử, tốc độ và phạm vi |
| Cleanup | Đóng phiên hoặc xử lý đối tượng tạo ra |
| Bằng chứng | Metadata cần ghi và dữ liệu phải che |
| Phục hồi | Điều kiện dừng, đối soát hoặc chuyển xử lý |

Các yêu cầu này phải phù hợp nền tảng. Không mặc định một tùy chọn trong client có cùng ý nghĩa trên mọi giao thức.

### 4.1. Ràng buộc phiên bản credential

Nếu kiểm thử luôn đọc một alias như current, alias có thể đã đổi bởi tác vụ khác trước khi probe chạy.

Cần biết probe đã lấy phiên bản nào và kết quả thuộc rotation nào. Nếu hệ thống hỗ trợ đọc theo phiên bản hoặc kiểm tra generation, dùng cơ chế đó theo thiết kế.

Không ghi password hoặc hash đơn giản của password để chứng minh phiên bản. Dùng định danh và metadata được quản lý.

### 4.2. Xác định tiêu chí riêng cho từng lớp

~~~text
PASS_AUTHENTICATION:
  Đúng nguồn, đúng tài khoản, đúng phương thức,
  dùng phiên bản cần kiểm tra, có xác thực mới.

PASS_FUNCTION:
  Tác vụ đại diện trong phạm vi được phép đạt.

PASS_CONSUMER:
  Consumer được xác định đã dùng đường cập nhật và xác thực mới.

ROTATION_COMPLETE:
  Đạt những điều kiện vòng đời đã cam kết,
  bao gồm phần credential cũ, phiên và dependency nếu áp dụng.
~~~

Các tên trên là nhãn logic minh họa, không phải trạng thái sản phẩm.

## 5. Bảo vệ password trong quá trình kiểm thử

### 5.1. Lấy secret qua cơ chế được quản lý

Probe cần quyền đọc hoặc sử dụng đúng đối tượng, không phải quyền đọc mọi secret.

Có thể dùng một tham chiếu credential bảo mật, agent hoặc cơ chế mà nền tảng hỗ trợ. Giá trị rõ chỉ nên tồn tại trong phạm vi cần thiết của luồng xử lý.

Không truyền password qua tham số dòng lệnh dễ quan sát, URL, ticket, email hoặc trường log chẩn đoán.

### 5.2. Kiểm soát đầu ra của công cụ

Một client có thể in lại connection string, request, câu lệnh hoặc thông tin xác thực khi lỗi. Cần kiểm tra và cấu hình xử lý dữ liệu nhạy cảm trước khi dùng cho rotation.

Không chỉ che password trên giao diện PAM trong khi log của connector, trace hoặc audit phía dưới vẫn giữ giá trị.

Thông báo lỗi cũng nên được phân loại và lọc, thay vì lưu toàn bộ phản hồi không kiểm soát.

### 5.3. Xử lý định dạng đúng cách

Password mới có thể chứa ký tự cần được xử lý theo ngữ cảnh truyền. Lỗi mã hóa hoặc ghép chuỗi có thể khiến client gửi giá trị khác với giá trị trong vault.

Ưu tiên các cơ chế truyền trường credential được hỗ trợ. Không tự ghép một connection string hoặc biểu thức quản trị rồi giả định mọi ký tự đều được hiểu nguyên vẹn.

Không giảm chất lượng password chỉ để che một lỗi xử lý định dạng của tích hợp mà chưa đánh giá nguyên nhân.

### 5.4. Kiểm thử không tạo thêm bản sao ngoài kiểm soát

Không ghi password mới vào một tệp tạm thông thường rồi quên xử lý. Nếu nền tảng cần tệp hoặc vùng lưu tạm, quyền, vòng đời và dữ liệu chẩn đoán phải được quản lý phù hợp.

Xóa một tham chiếu trong chương trình không chứng minh mọi bản sao vật lý trong bộ nhớ đã bị xóa. Cần giảm phơi lộ và bảo vệ môi trường chạy thay vì dựa vào một cam kết xóa không được xác minh.

## 6. Bảo đảm một lần xác thực mới thật sự

### 6.1. Kết nối mới ở ứng dụng chưa chắc là phiên mới tại đích

Một lệnh gọi lấy connection có thể chỉ mượn một kết nối đang có trong pool. Một đối tượng session mới ở client có thể dùng lại cookie, token hoặc kênh đã xác thực.

Cần phương pháp tạo hoặc nhận diện một phiên xác thực mới ở lớp cần kiểm tra. Nếu không chứng minh được, kết quả phải nói rõ giới hạn.

### 6.2. Loại trừ cơ chế thay thế làm che password

Tùy hệ thống, client có thể tự dùng:

- Danh tính tích hợp của môi trường chạy.
- Vé hoặc token còn hiệu lực.
- Khóa client hoặc chứng thư.
- Cookie hoặc phiên đã đăng nhập.
- Credential helper hoặc dữ liệu lưu sẵn.
- Một phương thức fallback khác.

Nếu mục tiêu là kiểm tra password, không để các phương thức này âm thầm tạo kết quả thành công.

Tuy nhiên, không được bỏ MFA hoặc điều kiện bắt buộc chỉ để “kiểm tra riêng password”. Với luồng nhiều yếu tố, cần thiết kế kiểm chứng đúng quy trình và mô tả password được xác minh trong ngữ cảnh nào.

### 6.3. Phiên cũ có thể che lỗi sau rotation

~~~text
Trước rotation:
  Phiên được tạo bằng credential cũ.

Sau rotation:
  Phiên vẫn hoạt động.
  Một tác vụ đọc qua phiên đó thành công.

Kết luận hợp lệ:
  Phiên cũ còn phục vụ được tác vụ đã thử.

Kết luận chưa có cơ sở:
  Password mới đã được chấp nhận.
~~~

Một probe độc lập có thể giúp kiểm tra password mới mà không đóng mọi phiên production. Cách thực hiện phải phù hợp nền tảng và quyền được giao.

### 6.4. Xác nhận phương thức đã dùng

Nếu công cụ hoặc nguồn có thể cung cấp metadata an toàn về phương thức xác thực, cần dùng để đối chiếu với kế hoạch.

Nếu chỉ có cấu hình client mà không có khả năng quan sát đầy đủ, phải ghi cơ sở và giới hạn của kết luận. Không tự ghi “password verified” khi thực tế không biết phương thức nào đã tạo thành công.

## 7. Trust, network và danh tính máy chủ

### 7.1. Kết nối được không chứng minh đúng đích

Probe cần xác minh danh tính máy chủ bằng cơ chế phù hợp giao thức, như trust của chứng thư hoặc host key theo triển khai.

Một kết nối tới endpoint sai nhưng chấp nhận cùng tài khoản không xác minh được mục tiêu rotation. Cần giữ target và nguồn xác thực trong bằng chứng.

### 7.2. Không gửi password khi trust chưa đạt

Lỗi xác minh máy chủ cần được xử lý như một lớp riêng. Không bỏ qua kiểm tra trust để có một kết quả đăng nhập thành công.

Nếu host key hoặc chứng thư thay đổi hợp lệ do thay node, phải có cách xác minh và cập nhật trust theo quy trình.

### 7.3. Phân biệt lỗi mạng và lỗi mật khẩu

Không tới được endpoint, DNS sai, TLS thất bại hoặc proxy không phản hồi chưa chứng minh password sai.

Phân loại đúng giúp tránh reset hoặc rotation thêm lần nữa khi nguồn xác thực có thể đã hoạt động đúng.

Cũng không coi timeout là bằng chứng chắc chắn xác thực chưa xảy ra. Nguồn có thể đã xử lý nhưng client chưa nhận kết quả; cần đối soát theo khả năng nền tảng.

## 8. Quy trình probe xác thực mới

### Bước 1: Kiểm tra precondition

Xác nhận rotation, account, source, target và phiên bản credential cần kiểm thử. Kiểm tra quyền chạy probe, giới hạn thử và trạng thái account theo khả năng quan sát.

Nếu một tác vụ khác đang đổi cùng tài khoản, cần điều phối trước khi diễn giải kết quả.

### Bước 2: Lấy đúng phiên bản qua kênh an toàn

Giữ tham chiếu và generation phù hợp. Không lấy một giá trị tùy ý từ clipboard hoặc cấu hình cũ rồi gọi đó là password mới.

Nếu không truy cập được phiên bản cần thiết, ghi lỗi ở lớp lấy secret. Không kết luận nguồn xác thực từ chối password.

### Bước 3: Thiết lập ngữ cảnh xác thực mới

Tạo hoặc chọn luồng không dùng lại phiên đã xác thực trước đó. Giới hạn phương thức theo mục tiêu mà vẫn đáp ứng chính sách bảo mật bắt buộc.

Không mượn pool cũ để kiểm chứng password mới.

### Bước 4: Xác minh máy chủ và kết nối

Kiểm tra trust trước khi gửi credential. Ghi định danh đích và đường đã sử dụng theo phạm vi cho phép.

### Bước 5: Thực hiện xác thực

Gửi credential bằng cơ chế của giao thức và client được hỗ trợ. Chỉ sử dụng số lần thử trong ngân sách.

Ghi kết quả phân loại, không ghi password hoặc toàn bộ phản hồi nhạy cảm.

### Bước 6: Kiểm tra tác vụ đại diện nếu cần

Sau khi xác thực đạt, thực hiện hành động ít tác động và đúng nhu cầu. Tác vụ này kiểm chứng quyền hoặc chức năng, không thay thế bằng chứng xác thực.

### Bước 7: Cleanup

Đóng phiên hoặc kết nối probe. Nếu có đối tượng tạm theo thiết kế, xử lý vòng đời của nó và ghi phần chưa hoàn tất.

Một probe xác thực thành công nhưng không đóng kết nối có thể để lại phiên ngoài mục tiêu. Cleanup cũng cần được theo dõi khi timeout.

### Bước 8: Ràng buộc kết quả với trạng thái quản lý

Kiểm tra account, version và generation vẫn phù hợp trước khi cập nhật kết quả cho rotation.

Nếu có thay đổi đồng thời, kết quả vẫn có giá trị lịch sử tại thời điểm kiểm tra nhưng không được tự dùng làm bằng chứng cho phiên bản mới hơn.

~~~mermaid
flowchart TD
    P["Xác định account, target và phiên bản"] --> C["Kiểm tra quyền và precondition"]
    C --> S["Lấy credential qua cơ chế an toàn"]
    S --> F["Thiết lập xác thực mới đúng phương thức"]
    F --> T{"Trust và kết nối đạt?"}
    T -->|Chưa| N["Phân loại lỗi; chưa kết luận password sai"]
    T -->|Đạt| A["Thử xác thực có giới hạn"]
    A --> R{"Kết quả rõ?"}
    R -->|Không| U["Ghi unknown và đối soát"]
    R -->|Có| E["Ghi kết quả xác thực"]
    E --> Q["Kiểm tra chức năng theo phạm vi"]
    Q --> X["Cleanup và lưu bằng chứng"]
    X --> V["Kiểm tra phiên bản trước cập nhật rotation"]
~~~

## 9. Những điểm khác nhau theo nền tảng

| Đối tượng hoặc đường | Điều cần chứng minh | Bẫy dễ gặp |
|---|---|---|
| Database | Có phiên xác thực mới bằng password ở đúng nguồn | Client mượn lại kết nối từ pool |
| Directory hoặc dịch vụ xác thực | Có lượt xác minh mới theo đúng danh tính và cơ chế | Dùng phiên đã bind hoặc token từ trước |
| Máy chủ quản trị | Password được dùng trong luồng cho phép | Khóa client hoặc danh tính tích hợp tự tạo thành công |
| Thiết bị mạng | Đúng node, tài khoản và bước xác thực | Đăng nhập được nhưng secret nâng quyền chưa được kiểm tra |
| Giao diện web | Có luồng đăng nhập mới đúng điều kiện | Cookie hoặc SSO cũ che bước password |
| Proxy hoặc gateway | Mỗi lớp xác thực cần thiết đã được kiểm tra | Chỉ xác thực client tới proxy |
| Workload lấy token từ password | Password mới được issuer chấp nhận và luồng ứng dụng đạt | Token cũ vẫn dùng được dù password đã sai |
| Cụm hoặc endpoint dự phòng | Phạm vi node và nguồn phản ánh thay đổi được hiểu | Một node thành công được suy rộng cho mọi node |

### 9.1. Password đăng nhập và secret nâng quyền có thể khác

Một tài khoản thiết bị mạng hoặc hệ thống quản trị có thể đăng nhập ở quyền thấp rồi cần bước nâng quyền riêng.

Kiểm tra login password chưa chứng minh secret nâng quyền đã được rotation hoặc dùng được. Phải ghi riêng đối tượng và kết quả.

### 9.2. Đường nhiều yếu tố

Khi policy yêu cầu thêm yếu tố, probe phải tuân theo luồng được phép. Không tự bỏ yếu tố để tạo một phép thử đơn giản hơn.

Một kết quả nhiều yếu tố cần cho biết những bước nào được xác minh. Không suy ra riêng password sai nếu thực tế yếu tố tiếp theo mới là bước bị từ chối.

### 9.3. Không áp dụng một lệnh chung cho mọi nền tảng

Tên tài khoản, miền, phạm vi database, phương thức và trạng thái lỗi có thể khác nhau.

Cần dùng client hoặc connector phù hợp và hiểu ngữ nghĩa kết quả. Một mã lỗi giống nhau trên hai hệ thống chưa chắc có cùng nguyên nhân.

## 10. Xác thực, ủy quyền và kiểm tra chức năng

### 10.1. Password đúng không đồng nghĩa được làm mọi việc

Sau khi xác thực thành công, một hành động có thể bị từ chối vì role, grant, phạm vi tài nguyên hoặc điều kiện policy.

Nếu probe định làm một việc ngoài quyền cần thiết, thất bại đó không chứng minh password sai.

Ngược lại, không nên cấp thêm quyền quản trị để một bài kiểm tra không phù hợp trở thành PASS.

### 10.2. Tác vụ đại diện phải phù hợp mục tiêu

Một tác vụ có thể kiểm chứng:

- Truy cập được đúng database hoặc phạm vi dữ liệu.
- Đọc được đối tượng trạng thái đã được cho phép.
- Thực hiện được một API không thay đổi trạng thái.
- Mở được phiên ở role dự kiến.
- Đi qua được đường kết nối mà consumer thực sự dùng.

Tác vụ chỉ đọc vẫn có thể trả dữ liệu nhạy cảm. Chọn dữ liệu và đầu ra phù hợp, không xuất toàn bộ cấu hình hoặc dữ liệu nghiệp vụ để làm bằng chứng.

Nếu nhu cầu thực tế gồm thao tác ghi, phương pháp kiểm chứng phải có phạm vi, môi trường, cơ chế cleanup và thẩm quyền tương ứng. Không tạo thay đổi production ngoài kế hoạch chỉ để kiểm tra credential.

### 10.3. Ghi kết quả theo lớp

Ví dụ:

~~~text
Fresh password authentication: PASS.
Role expected by plan: observed.
Representative read operation: PASS.
Representative write path: NOT_TESTED.
Consumer adoption: PENDING.
Old password handling: VERIFIED_SEPARATELY.
~~~

Đây là cách trình bày minh họa. Không gộp NOT_TESTED thành PASS khi tổng hợp.

## 11. Kiểm tra consumer đã dùng password mới

### 11.1. Probe độc lập và kiểm tra consumer có mục tiêu khác nhau

Probe độc lập có thể chứng minh nguồn chấp nhận password mới. Nó không chứng minh ứng dụng đã refresh.

Cần xem từng bước:

~~~text
Vault có phiên bản mới.
  → agent hoặc cơ chế phân phối đã nhận.
  → consumer đọc lại hoặc được thay thế.
  → phiên xác thực mới được tạo.
  → tác vụ đại diện của consumer đạt.
~~~

Một ACK từ agent chỉ chứng minh một phần luồng.

### 11.2. Instance và nhóm triển khai

Một instance đạt không đủ để xác nhận mọi instance. Cần định nghĩa phạm vi kiểm tra, cách triển khai và mức bằng chứng cần cho từng nhóm.

Nếu lấy mẫu, báo rõ là lấy mẫu và giới hạn. Không dùng kết quả của mẫu làm tuyên bố đã kiểm tra toàn bộ.

### 11.3. Job ít chạy và dự phòng

Job cuối tháng hoặc môi trường khởi động lạnh có thể chưa dùng credential mới trong cửa sổ triển khai.

Có thể cần một đường kiểm tra được phép đại diện, hoặc một công việc xác minh theo kế hoạch có owner cùng thời hạn. Không tự chạy tác vụ nghiệp vụ có tác động chỉ để thử password.

Trạng thái chưa kiểm tra vẫn cần nhìn thấy khi báo cáo rotation.

### 11.4. Cấu hình mong muốn

Reference runtime đã đổi nhưng template hoặc pipeline còn cũ có thể làm lần deploy sau quay về credential không còn hợp lệ.

Kiểm chứng cần bao gồm nguồn cấu hình trong phạm vi đã cam kết. Đây là bằng chứng duy trì trạng thái, khác với kết quả đăng nhập tại một thời điểm.

## 12. Có cần thử password cũ không?

### 12.1. Mục tiêu kiểm chứng phải riêng biệt

Password mới được chấp nhận không chứng minh password cũ bị từ chối. Một số thiết kế cho phép giai đoạn chồng lấn; một số khác ngừng password cũ ngay cho xác thực mới.

Nếu mục tiêu rotation yêu cầu ngừng chấp nhận password cũ, cần bằng chứng tương ứng. Bằng chứng có thể đến từ trạng thái nguồn và phương pháp kiểm tra được hỗ trợ, không nhất thiết luôn là một lần đăng nhập sai có chủ ý.

### 12.2. Không thử mù các phiên bản lịch sử

Không lấy mọi password từng lưu rồi thử lần lượt trên nhiều endpoint. Cách đó có thể gây khóa tài khoản, tạo tải và làm tăng phơi lộ.

Cần xem ngân sách thử, số lần thất bại từ consumer còn dùng cũ và trạng thái account. Các lần thử phân tán vẫn có thể cùng tác động một tài khoản.

### 12.3. Nếu thực hiện kiểm tra âm tính

Cần xác minh:

1. Đúng nguồn và tài khoản.
2. Trust và đường kết nối đạt.
3. Phương thức thực sự là password cần kiểm tra.
4. Không có phiên hoặc credential thay thế che kết quả.
5. Giới hạn thử và nguy cơ khóa tài khoản đã được xử lý.
6. Kết quả từ chối đủ rõ để diễn giải.
7. Không giữ hoặc log password cũ ngoài cơ chế được phép.

Nếu lỗi là account locked, không tới được nguồn hoặc MFA thất bại, chưa thể kết luận password cũ đã bị vô hiệu hóa.

### 12.4. Không dùng phiên cũ để kiểm tra password cũ

Một phiên được tạo trước rotation có thể còn hoạt động dù password cũ không còn dùng để đăng nhập mới.

Ngược lại, đóng phiên cũ không chứng minh password cũ đã mất hiệu lực. Hai yêu cầu phải được kiểm tra riêng.

## 13. Phân loại kết quả thay vì gộp thành “password sai”

| Kết quả hoặc quan sát | Cách diễn giải cần giữ |
|---|---|
| Không đọc được phiên bản secret | Lỗi lấy credential, chưa có kết luận tại nguồn |
| Không xác minh được máy chủ | Lỗi trust, không tiếp tục gửi credential |
| Không tới được endpoint | Lỗi kết nối, chưa chứng minh password sai |
| Nguồn xác nhận từ chối credential | Có bằng chứng xác thực thất bại trong ngữ cảnh đã ghi |
| Tài khoản bị khóa hoặc vô hiệu hóa | Trạng thái account ngăn truy cập, không tự suy ra giá trị password |
| Password hết hạn hoặc cần đổi thêm | Có điều kiện vòng đời chưa đáp ứng nhu cầu vận hành |
| Xác thực bằng phương thức khác | Chưa kiểm tra được password theo mục tiêu |
| Xác thực đạt nhưng hành động bị từ chối | Cần đánh giá quyền hoặc phạm vi tác vụ |
| Timeout sau gửi yêu cầu | Kết quả có thể chưa xác định |
| Thành công qua phiên có sẵn | Không đủ bằng chứng xác thực mới |
| Đúng password mới qua phiên mới | Đạt điều kiện xác thực trong phạm vi được ghi |

Nhãn và mã lỗi thực tế phụ thuộc nền tảng. Cần ánh xạ từ nguồn bằng chứng, không tự đoán nguyên nhân chỉ từ một chuỗi thông báo chung.

### 13.1. Giữ trạng thái UNKNOWN hoặc NOT_TESTED

UNKNOWN nghĩa chưa có đủ bằng chứng kết luận. NOT_TESTED nghĩa bước đó chưa được thực hiện theo kế hoạch.

Hai trạng thái đều khác thất bại password và khác PASS. Chúng cần owner hoặc bước xử lý tiếp theo khi ảnh hưởng tới tiêu chí đóng rotation.

### 13.2. Trạng thái vận hành có thể khác kết quả xác thực

Password có thể đúng nhưng tài khoản buộc đổi password ở lần sử dụng đầu. Điều đó có thể không phù hợp với một workload không tương tác.

Cần ghi xác thực và điều kiện sử dụng riêng, thay vì coi một bước trung gian chấp nhận password là ứng dụng đã sẵn sàng.

## 14. Retry, timeout và thay đổi đồng thời

### 14.1. Ngân sách thử phải tính theo tài khoản

Nhiều instance probe và consumer có thể cùng thử một password lỗi. Giới hạn cục bộ trên từng worker chưa chắc bảo vệ được tài khoản nếu không có điều phối phù hợp.

Cần tính tốc độ, số lần, khoảng chờ và điều kiện dừng theo phạm vi thật. Không retry không giới hạn chỉ vì lỗi được gọi là tạm thời.

### 14.2. Phân biệt thử xác thực lại với đổi password lại

Nếu probe timeout, không tự sinh password khác rồi rotation lại để “sửa” kết quả.

Nguồn có thể đã đổi đúng, trong khi lỗi nằm ở trust, network, consumer hoặc công cụ kiểm thử. Cần phân loại và đối soát trước.

### 14.3. Kết quả thành công có thể trở nên cũ

Một tác vụ khác có thể thay account ngay sau probe. Vì vậy, bằng chứng cần thời điểm, version và generation.

Khi cập nhật trạng thái quản lý, kiểm tra kết quả vẫn thuộc phiên bản đang xét. Nếu generation đã đổi, không dùng PASS của version trước để xác nhận version mới.

### 14.4. Dừng tác vụ không đồng nghĩa không có hiệu ứng

Một yêu cầu xác thực có thể đã tạo phiên dù client không nhận đủ phản hồi. Cần cleanup hoặc đối soát theo khả năng giao thức và hệ thống.

Giữ tham chiếu an toàn để tìm phiên liên quan. Không lưu raw credential để khắc phục sự không chắc chắn.

## 15. Kế hoạch và giả mã kiểm thử

Các cấu trúc dưới đây là mô hình minh họa, không phải cú pháp của một sản phẩm hoặc script có thể chạy trực tiếp.

### 15.1. Kế hoạch logic

~~~yaml
verification_plan:
  rotation_id: rotation-042
  account_id: payment-service-account
  authentication_source_id: payment-db-identity
  target_id: payment-database-production
  credential_reference: managed-payment-secret
  credential_version_reference: version-13
  expected_managed_generation: 12

  authentication:
    intended_method: password
    preserve_required_factors: true
    require_fresh_authentication: true
    prohibit_unapproved_fallback: true

  probe:
    action_reference: approved-low-impact-probe
    target_scope_reference: recorded-endpoint-scope
    retry_policy_reference: account-safe-retry-policy

  evidence:
    record_secret_values: false
    record_method_and_freshness_basis: true
    record_cleanup_result: true
~~~

Các trường chỉ biểu diễn yêu cầu. Viết require_fresh_authentication=true không tự khiến một thư viện bỏ pool hoặc cookie. Phải có cơ chế thực thi và bằng chứng phù hợp.

### 15.2. Giả mã

~~~text
verify_new_password(plan):
    verify_authority_and_scope(plan)
    verify_generation_and_version_reference(plan)
    check_account_retry_budget(plan.account)

    secret_handle = obtain_secret_through_approved_channel(plan)
    context = create_probe_context(plan)

    verify_target_trust(context, plan.target)
    configure_permitted_authentication_flow(context, plan)

    authentication_result = attempt_fresh_authentication(
        context, secret_handle, within_retry_budget
    )

    if authentication_result is ambiguous:
        record_safe_result(UNKNOWN)
        cleanup_or_track_pending_context(context)
        return UNKNOWN

    if not evidence_matches_expected_method_and_freshness(
        authentication_result, plan
    ):
        record_safe_result(AUTHENTICATION_NOT_VERIFIED_AS_PLANNED)
        cleanup_or_track_pending_context(context)
        return NOT_VERIFIED

    function_result = run_only_approved_probe(context, plan)
    cleanup_result = cleanup_or_track_pending_context(context)

    recheck_generation_before_publishing_result(plan)

    record_separate_results(
        authentication_result,
        function_result,
        cleanup_result,
        credential_version_reference
    )
~~~

Mô hình không giả định mọi client trả cùng metadata. Nếu không có đủ cơ sở chứng minh phương thức hoặc tính mới, cần ghi giới hạn thay vì tự tạo dữ liệu.

Kết quả chức năng hoặc cleanup không được che mất kết quả xác thực. Đồng thời, xác thực PASS không được xóa một cleanup còn pending.

### 15.3. Quyền cho probe

Probe cần quyền dùng đúng credential và thực hiện đúng hành động kiểm tra. Có thể dùng quyền vận hành JIT hoặc role giới hạn theo tác vụ khi nền tảng hỗ trợ.

Không giao quyền đọc mọi secret, sửa mọi account và tắt audit cho một danh tính chỉ cần xác minh password. Giới hạn JEA phải tồn tại ở điểm thực thi, không chỉ trong tên role.

## 16. Audit và bằng chứng kiểm thử

### 16.1. Những trường nên có

Một bản ghi cần đủ thông tin để hiểu kết quả mà không chứa secret:

- Verification ID và rotation ID.
- Account, source, target và phạm vi endpoint.
- Credential object cùng version reference.
- Thời điểm bắt đầu, kết thúc và trạng thái quản lý được đối chiếu.
- Phương thức mong đợi và cơ sở xác nhận phương thức thực tế.
- Cơ sở xác nhận một lần xác thực mới.
- Kết quả xác thực, chức năng và cleanup riêng.
- Số lần thử hoặc tham chiếu tới ngân sách thử.
- Nguồn bằng chứng và những giới hạn còn lại.

Không dùng suffix của password, ảnh chụp secret hoặc hash đơn giản để “chứng minh đã dùng đúng mật khẩu”.

### 16.2. Sự kiện minh họa

~~~json
{
  "event_type": "password_verification_completed",
  "verification_id": "verification-081",
  "rotation_id": "rotation-042",
  "account_id": "payment-service-account",
  "target_id": "payment-database-production",
  "credential_version_reference": "version-13",
  "authentication_method_basis": "recorded-approved-client-and-source-evidence",
  "freshness_basis": "recorded-new-authentication-evidence",
  "authentication_outcome": "passed-for-recorded-scope",
  "function_outcome": "passed-for-approved-probe",
  "cleanup_outcome": "completed",
  "consumer_adoption": "verified-separately",
  "evidence_reference": "evidence-081"
}
~~~

Đây là dữ liệu giả định. Bản ghi thực tế cần thời điểm và metadata phù hợp hệ thống; không được ghi PASS nếu các trường basis chỉ là giả định.

### 16.3. Bằng chứng tại PAM và tại đích

PAM có thể chứng minh đã lấy version-13 và thực hiện probe theo kế hoạch. Log tại đích có thể giúp xác nhận một phiên mới hoặc phương thức theo khả năng.

Cần liên kết bằng định danh, thời gian và ngữ cảnh phù hợp. Không coi log hiện tại của account là bằng chứng toàn bộ hành động trong quá khứ nếu không có liên kết đủ rõ.

### 16.4. Phạm vi của một kết quả

Bằng chứng xác nhận tại một thời điểm và ngữ cảnh. Nó không bảo đảm password sẽ tiếp tục có hiệu lực sau khi một actor khác thay account, policy hoặc endpoint.

Giữ lịch sử đúng thời điểm. Nếu kiểm tra lại sau phục hồi, ghi một sự kiện mới thay vì sửa kết quả cũ cho khớp trạng thái hiện tại.

## 17. Tình huống xuyên suốt: probe thành công nhờ pool cũ

### 17.1. Bối cảnh

Một ứng dụng thanh toán dùng tài khoản database. Sau rotation, vault quản lý version-13. Ứng dụng vẫn đang hoạt động với pool được tạo trước đó.

Tác vụ kiểm thử gọi một hàm lấy connection rồi thực hiện một thao tác đọc ít tác động. Hàm trả kết quả thành công, nên dashboard muốn đánh dấu password mới đã được xác minh.

### 17.2. Điều còn thiếu

Connection được lấy có thể là kết nối cũ. Tác vụ đọc chứng minh kết nối đó còn hoạt động, chưa chứng minh version-13 đã được nguồn chấp nhận.

Cần biết:

- Probe có dùng lại pool không.
- Credential được lấy theo version hay alias hiện hành.
- Phương thức xác thực thực tế là gì.
- Đích và account có đúng phạm vi không.
- Có phiên xác thực mới hoặc bằng chứng tương đương không.

### 17.3. Thiết kế lại kiểm chứng theo lớp

Một probe độc lập được phép sử dụng version-13, đi tới đúng nguồn qua kênh đã xác minh và tạo một lần xác thực mới theo cơ chế được hỗ trợ.

Probe thành công ở bước này xác nhận password mới tại nguồn trong phạm vi đã ghi.

Sau đó, consumer được kiểm tra theo cơ chế refresh hoặc chuyển instance. Một kết nối mới từ đường consumer xác nhận ứng dụng đã áp dụng phiên bản theo kế hoạch.

Hai kết quả được lưu riêng; không lấy kết quả probe độc lập thay cho bằng chứng consumer.

### 17.4. Một lỗi quyền không phải lỗi password

Giả sử probe đã xác thực nhưng tác vụ kiểm tra cố đọc một vùng quản trị mà tài khoản runtime không cần truy cập.

Nếu bị từ chối, kết quả đúng là authentication PASS, hành động kiểm tra không phù hợp hoặc chưa đạt điều kiện quyền theo kế hoạch.

Không cấp quyền quản trị để “sửa password”. Cần điều chỉnh probe về hành động đại diện cho nhu cầu hợp lệ hoặc xử lý quyền bằng quyết định riêng.

### 17.5. Báo cáo kết quả

| Phần | Kết quả minh họa |
|---|---|
| Xác thực mới bằng version-13 tại nguồn | Đã xác minh trong phạm vi |
| Probe đọc qua pool cũ | Không dùng làm bằng chứng password mới |
| Đường consumer sau refresh | Được xác minh riêng |
| Job đối soát ít chạy | Còn chờ kiểm tra theo kế hoạch |
| Password cũ | Được xử lý bằng bằng chứng riêng |
| Phiên cũ | Theo dõi theo policy, không suy ra từ rotation |

Trạng thái tổng phải giữ phần chờ của job. Nếu có thay đổi version trong lúc kiểm thử, cần đánh giá lại cơ sở cập nhật trạng thái hiện hành.

## 18. Xử lý khi password mới chưa kiểm chứng được

### 18.1. Bắt đầu từ lớp lỗi

Nếu không lấy được secret, sửa đường lấy hoặc quyền tương ứng. Nếu trust thất bại, xử lý trust. Nếu source từ chối, xem lại account, version, định dạng và trạng thái nguồn.

Không tự đổi password thêm lần nữa cho mọi loại lỗi.

### 18.2. Kiểm tra đồng bộ sau timeout rotation

Có thể nguồn đã đổi nhưng vault chưa cập nhật hoặc client chưa nhận kết quả.

Cần đối soát trạng thái đã biết, dùng phiên bản được bảo vệ và phương án reconcile được cho phép. Không thử lần lượt mọi password lịch sử để tìm một giá trị còn dùng.

Một phản hồi source chưa rõ cần được ghi là chưa rõ, không chuyển thành thất bại chắc chắn của candidate.

### 18.3. Không công bố credential chưa đạt điều kiện

Nếu quy trình yêu cầu kiểm chứng tại nguồn trước khi công bố cho consumer, không bỏ gate đó chỉ vì muốn khép tác vụ.

Nếu hệ thống đã ở trạng thái thay đổi từng phần, cần kế hoạch phục hồi theo trạng thái thực tế. Có thể là hoàn tất cập nhật vault, chuyển consumer hoặc dùng danh tính phục hồi theo thẩm quyền.

### 18.4. Không mặc định quay về password cũ

Password cũ có thể đã bị lộ, không còn được phép tái sử dụng hoặc có consumer đã chuyển sang bản mới.

Rollback, reconcile và roll forward phải xét nguồn, vault, consumer cùng phạm vi ảnh hưởng. Một lần probe lỗi chưa đủ để lựa chọn phương án.

### 18.5. Cleanup và bằng chứng sau phục hồi

Đóng những phiên probe còn tồn tại nếu cần và trong phạm vi có thể. Ghi phần cleanup chưa xác minh.

Sau khi sửa, chạy lại kiểm chứng theo kế hoạch và lưu sự kiện mới. Không đánh dấu mọi endpoint hoặc consumer đạt chỉ vì một đường đã phục hồi.

## 19. Kiểm chứng triển khai và chỉ số

### 19.1. Những tình huống nên được kiểm chứng

| Tình huống | Kết quả cần quan sát |
|---|---|
| Vault lưu đúng version nhưng target chưa đổi | Probe không ghi nhầm source đã chấp nhận |
| Client có token hoặc phiên cũ | Không dùng thành công đó làm bằng chứng password |
| Client mượn pool cũ | Freshness không bị suy ra từ API bề mặt |
| Có phương thức fallback | Phân biệt hoặc chặn fallback theo kế hoạch được phép |
| Trust của máy chủ không đạt | Không tiếp tục gửi password |
| Đúng password nhưng thiếu quyền tác vụ | Tách xác thực và chức năng |
| Account bị khóa | Không kết luận candidate sai chỉ từ trạng thái khóa |
| Password cần đổi thêm | Ghi điều kiện vận hành chưa đạt |
| Alias hoặc generation đổi giữa chừng | Không công bố PASS cho sai phiên bản |
| Timeout sau gửi xác thực | Có trạng thái unknown và cleanup theo khả năng |
| Nhiều probe cùng thử | Ngân sách tài khoản được điều phối |
| Consumer ít chạy | Phần chưa kiểm tra được giữ rõ |

Việc kiểm chứng có thể dùng môi trường và phương pháp phù hợp. Không cần gây khóa account production hoặc đóng hàng loạt phiên để tạo một bằng chứng.

### 19.2. Chỉ số có ích

- Rotation có bằng chứng xác thực mới theo đúng phiên bản.
- Probe không đủ cơ sở về phương thức hoặc freshness.
- Kết quả UNKNOWN, NOT_TESTED và thời gian xử lý.
- Lỗi theo lớp lấy secret, trust, network, authentication và authorization.
- Số lần thử theo account và phạm vi.
- Cleanup còn pending.
- Consumer đã xác minh xác thực mới trong tập được quản lý.
- Kết quả bị cũ do thay đổi generation.
- Phần endpoint, job hoặc dự phòng chưa kiểm tra.

Không dùng tổng số probe trả mã thành công làm số password đã được kiểm chứng. Một probe có thể thành công nhờ cache hoặc không đi qua bước xác thực cần kiểm tra.

### 19.3. Mẫu số và giới hạn

Tỷ lệ đạt trong tập endpoint đã biết không chứng minh đã bao phủ toàn bộ hạ tầng.

Báo cáo cần phạm vi, thời điểm và cơ sở bằng chứng. Không đưa secret hoặc dữ liệu nhạy cảm không cần thiết vào nhãn metric.

## 20. Lỗi thường gặp và bài tập áp dụng

### 20.1. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nguồn báo đổi thành công là coi đã kiểm thử | Candidate có thể chưa dùng được | Xác thực mới đúng nguồn |
| Thao tác qua session cũ là PASS password mới | Kết quả giả do phiên còn hiệu lực | Thiết kế freshness và bằng chứng |
| Đối tượng connection mới là kết nối mới | Pool có thể tái sử dụng phiên | Kiểm tra ở lớp xác thực thật |
| Đăng nhập bằng khóa hoặc SSO nhưng ghi password PASS | Không kiểm tra phương thức cần thiết | Ràng buộc và xác nhận phương thức |
| Bỏ MFA để probe dễ chạy | Thay đổi điều kiện bảo mật | Kiểm chứng theo luồng được phép |
| Bỏ trust khi gặp lỗi chứng thư | Có thể gửi credential tới sai đích | Sửa trust trước khi gửi |
| Gộp thiếu quyền thành password sai | Rotation hoặc reset không cần thiết | Tách authentication và authorization |
| Thử password cũ liên tục | Gây khóa tài khoản | Kiểm tra âm tính có giới hạn |
| Lưu password hoặc hash đơn giản trong evidence | Tạo điểm lộ | Dùng version và tham chiếu |
| Ghi PASS theo alias sau khi alias đã đổi | Xác nhận sai version | Ràng buộc generation và thời điểm |
| Probe độc lập đạt là coi mọi consumer đã chuyển | Bỏ sót cache, job và dự phòng | Xác minh consumer riêng |
| Timeout là coi xác thực chưa xảy ra | Có thể bỏ sót phiên hoặc hiệu ứng | Ghi unknown và đối soát |
| Cấp thêm quyền rộng để probe xanh | Tăng đặc quyền ngoài nhu cầu | Chọn tác vụ đúng phạm vi |
| Sửa lịch sử sau phục hồi | Mất khả năng điều tra | Ghi sự kiện kiểm tra mới |

### 20.2. Bài tập

Một đội thay password của tài khoản quản trị thiết bị mạng. Gateway vẫn giữ phiên cũ. Probe dùng một client có khóa đăng nhập được lưu sẵn, nhận kết quả thành công và thực hiện một thao tác đọc. Dashboard ghi password mới PASS. Đội định thử password cũ nhiều lần để bảo đảm đã bị thu hồi, trong khi không biết các consumer khác đang tạo bao nhiêu lần đăng nhập lỗi.

Hãy trả lời:

1. Vì sao kết quả hiện tại chưa đủ chứng minh password mới?
2. Cần xác định những phương thức và phiên nào?
3. Có phải mọi lỗi đọc đều là password sai không?
4. Rủi ro của việc thử password cũ trong điều kiện này là gì?
5. Bằng chứng nào cần cho kết quả xác thực, consumer và thu hồi riêng?
6. Sau khi sửa probe, báo cáo nên giữ lịch sử cũ như thế nào?

Hướng phân tích:

- Thành công có thể đến từ phiên cũ hoặc khóa client, không phải password mới.
- Cần xác định nguồn, account, phương thức thật, freshness và bước nâng quyền nếu có.
- Tác vụ có thể bị từ chối bởi role hoặc phạm vi dù xác thực đã đạt.
- Ngân sách thử cần tính theo account và những lần thử khác; không biết trạng thái chưa đủ cơ sở thử lặp.
- Cần bằng chứng riêng cho password mới, đường consumer, password cũ và phiên.
- Kết quả trước cần được giữ đúng giới hạn hoặc phân loại lại có lịch sử; lần kiểm tra mới là sự kiện riêng.

## 21. Các điểm cần nắm

Kiểm thử password mới phải chứng minh đúng credential được đúng nguồn chấp nhận qua một lần xác thực mới. Kết nối, phiên hoặc thao tác còn hoạt động chưa đủ để kết luận điều đó.

Xác thực, quyền chức năng, consumer adoption, thu hồi password cũ và đóng phiên là các kết quả riêng. Mỗi phần cần phương pháp và bằng chứng phù hợp.

Giữ password khỏi log, giới hạn retry theo account, ràng buộc kết quả với phiên bản và báo rõ UNKNOWN hoặc NOT_TESTED. Chỉ khẳng định phạm vi đã thực sự được xác minh.
