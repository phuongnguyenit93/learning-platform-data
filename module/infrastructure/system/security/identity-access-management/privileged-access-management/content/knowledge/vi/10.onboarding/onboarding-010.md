# Rollback onboarding lỗi trong PAM

## 1. Mục tiêu của rollback

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), **rollback onboarding lỗi** là quá trình xử lý một lần đưa tài khoản, credential, tài nguyên hoặc đường truy cập vào PAM không đạt yêu cầu, để hệ thống hội tụ về một trạng thái phục hồi đã được xác định và có thể kiểm chứng.

Trạng thái phục hồi không nhất thiết giống hoàn toàn trạng thái trước onboarding. Nếu credential cũ đã bị lộ hoặc quyền cũ quá rộng, đưa mọi thứ về như cũ có thể khôi phục cả rủi ro mà tổ chức đang muốn loại bỏ.

Mục tiêu cần được xác định theo phạm vi:

- Duy trì hoặc phục hồi công việc cần thiết.
- Giữ quyền truy cập trong giới hạn có thẩm quyền.
- Đưa credential, consumer và cấu hình về trạng thái nhất quán.
- Xử lý grant, tài khoản và phiên còn tồn tại.
- Giữ bằng chứng cho kiểm toán, điều tra và lần triển khai tiếp theo.

Ví dụ, onboarding một tài khoản dịch vụ có thể đã đổi mật khẩu tại đích nhưng chưa cập nhật consumer. Nếu chỉ xóa đối tượng khỏi vault, dịch vụ vẫn không đăng nhập được. Nếu đặt lại mật khẩu cũ mà mật khẩu đó đã bị lộ, dịch vụ có thể hoạt động trở lại nhưng đường xâm nhập cũng được khôi phục.

Vì vậy, rollback cần dựa trên **trạng thái thực tế tại từng thành phần**, không dựa chỉ trên trạng thái thành công hoặc thất bại của tác vụ PAM.

## 2. Vì sao onboarding PAM không phải một giao dịch duy nhất?

Một lần onboarding có thể tác động tới nhiều hệ thống:

| Thành phần | Thay đổi có thể đã xảy ra |
|---|---|
| Danh mục tài nguyên | Tạo asset, liên kết owner, node và môi trường |
| Vault | Tạo đối tượng, phiên bản credential và quyền sử dụng |
| Hệ thống đích | Tạo tài khoản, đổi mật khẩu, cài khóa hoặc sửa role |
| Broker hoặc connector | Thiết lập cách cấp, xác minh, rotation hoặc reconcile |
| Consumer | Đổi secret reference, cập nhật cấu hình hoặc cache |
| Directory hoặc nền tảng danh tính | Thay nhóm, grant, liên kết hoặc trạng thái tài khoản |
| Gateway | Chuyển đường truy cập, mở hoặc quản lý phiên |
| Tự động hóa | Bật lịch rotation, refresh, thu hồi hoặc triển khai cấu hình |
| Audit | Ghi sự kiện và liên kết bằng chứng |

Các thay đổi không nhất thiết nằm trong cùng một cơ chế commit. Một hệ thống có thể hoàn tất trong khi hệ thống khác timeout, không truy cập được hoặc chưa nhận dữ liệu mới.

~~~text
Vault có đối tượng mới
  ≠ đích đã chấp nhận credential
  ≠ consumer đã chuyển sang credential đó
  ≠ quyền đã đúng phạm vi
  ≠ phiên cũ đã kết thúc.
~~~

Thậm chí một thao tác riêng lẻ cũng có kết quả không xác định: đích đã áp dụng thay đổi nhưng phản hồi bị mất trước khi connector nhận được.

Không thể dùng một lệnh “undo” tại PAM để mặc định đảo ngược mọi hiệu ứng bên ngoài. Cần các hành động bù, đối soát và xác minh theo từng đối tượng.

## 3. Phân biệt các phương án phục hồi

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Rollback | Đưa một phần cấu hình hoặc trạng thái về mốc phục hồi được chọn | Khôi phục đường truy cập trước đó trong phạm vi được phép |
| Hành động bù | Thực hiện thao tác mới để xử lý hiệu ứng đã xảy ra | Thu hồi tài khoản động được tạo nhưng không bàn giao |
| Roll forward | Hoàn tất hoặc sửa phần còn thiếu để đạt thiết kế mới | Cập nhật consumer tới credential mới đã có hiệu lực |
| Reconcile | Đối soát và đưa các trạng thái liên quan về đồng bộ theo cơ chế được cho phép | Đưa vault và tài khoản tại đích về cùng phiên bản credential hợp lệ |
| Offboarding | Kết thúc quản lý hoặc loại bỏ đối tượng theo kế hoạch vòng đời | Thu hồi quyền và loại bỏ tài khoản không còn nhu cầu |
| Khôi phục thảm họa | Phục hồi nền tảng hoặc dữ liệu sau sự cố ở phạm vi lớn hơn | Khôi phục dịch vụ vault theo kế hoạch phục hồi riêng |

Tên gọi không thay thế mục tiêu. Một phương án được gọi là rollback nhưng thực tế tạo credential mới và chuyển consumer sang đó vẫn phải được mô tả theo hành động thực hiện.

Không dùng khôi phục toàn bộ nền tảng làm thao tác mặc định cho lỗi onboarding một tài khoản. Bản sao lưu cũ có thể ghi đè thay đổi hợp lệ của đối tượng khác và làm mất đồng bộ với các hệ thống đích vẫn đang hoạt động.

## 4. Chuẩn bị khả năng rollback trước khi onboard

### 4.1. Ghi trạng thái ban đầu có phạm vi

Một baseline hữu ích gồm:

- Định danh tài nguyên, tài khoản và nguồn credential.
- Owner, consumer và đường truy cập.
- Quyền hiệu lực hoặc tham chiếu bằng chứng quyền.
- Credential reference, phiên bản hoặc trạng thái quản lý.
- Cấu hình liên quan tới thay đổi.
- Grant, phiên và tự động hóa đang tồn tại.
- Phương án truy cập phục hồi.
- Những sai lệch và ngoại lệ có từ trước.

Không cần đưa giá trị secret vào baseline dạng văn bản thông thường. Credential phục hồi, nếu cần giữ, phải được bảo vệ qua cơ chế quản lý phù hợp.

Baseline cũng có thể đã cũ khi nhiều thay đổi diễn ra đồng thời. Cần gắn thời điểm, phạm vi và chủ thể xác nhận, đồng thời kiểm tra lại trước khi sử dụng.

### 4.2. Thiết kế checkpoint theo kết quả quan sát được

~~~text
Đã đăng ký đối tượng
  → đã kiểm tra kết nối
  → đã xác minh danh tính đích
  → đã xác thực credential
  → đã xác minh quyền
  → đã áp dụng thay đổi vòng đời
  → consumer đã chuyển đổi
  → đường truy cập đã được kiểm soát
  → đã nghiệm thu.
~~~

Checkpoint phải phân biệt “đã gửi yêu cầu” với “đã xác minh kết quả”. Nếu checkpoint chỉ ghi rằng một API trả thành công, nó có thể chưa đủ để xác định trạng thái cuối tại đích.

### 4.3. Giữ một đường phục hồi có thể sử dụng

Đường phục hồi có thể là một danh tính quản trị độc lập, console, một tài khoản reconcile hoặc quy trình khẩn cấp đã được thiết kế.

Cần biết đường đó phụ thuộc vào đâu. Nếu mọi cách lấy credential đều cần chính thành phần đang lỗi, phương án phục hồi có thể không dùng được khi cần.

Một phiên quản trị đang mở có thể hỗ trợ xử lý nhưng không nên là bằng chứng duy nhất về khả năng phục hồi. Phiên có thể hết hạn, đứt kết nối hoặc thiếu quyền cho bước tiếp theo.

## 5. Xác định khi nào cần dừng hoặc phục hồi

Các tín hiệu thường gặp:

| Tín hiệu | Điều cần làm rõ trước khi chọn hành động |
|---|---|
| Kiểm tra đăng nhập thất bại | Lỗi mạng, trust, tài khoản, credential hay khóa tài khoản? |
| Rotation timeout | Đích chưa đổi hay đã đổi nhưng mất phản hồi? |
| Dịch vụ lỗi sau chuyển secret reference | Consumer đọc sai đối tượng, còn cache cũ hay thiếu quyền đọc? |
| Người dùng không mở được phiên | Lỗi danh tính, policy, gateway hay quyền tại đích? |
| Role hiệu lực rộng hơn dự kiến | Mapping, quyền kế thừa hay connector đã tạo quyền sai? |
| Một node thành công, node khác thất bại | Credential theo node hay theo cụm, đồng bộ đã hoàn tất chưa? |
| Cảnh báo mất bằng chứng | Lỗi thu thập, lưu trữ hay quyết định đã diễn ra ngoài đường giám sát? |
| Có dấu hiệu credential bị lộ | Cần chuyển sang xử lý sự cố và ngừng coi secret cũ là phương án an toàn |

Không chọn rollback chỉ vì dashboard hiển thị đỏ. Có trường hợp lỗi là do kiểm tra sai hoặc dữ liệu quan sát chậm; cũng có trường hợp dashboard xanh nhưng consumer hoặc quyền tại đích đang sai.

Điều kiện dừng nên gắn với ảnh hưởng và khả năng xác minh: có nguy cơ mất quản trị, quyền vượt phạm vi, kết quả không xác định, hoặc không còn bảo đảm điều kiện vận hành đã thống nhất.

## 6. Ổn định tình huống trước khi sửa

### 6.1. Dừng phát sinh thay đổi chồng chéo

Cần xác định các tác vụ có thể tiếp tục tác động tới cùng đối tượng:

- Lịch rotation hoặc reconcile.
- Retry của connector.
- Pipeline triển khai ứng dụng.
- Controller hoặc công cụ quản lý cấu hình.
- Tác vụ refresh credential của consumer.
- Luồng cấp grant hoặc phiên mới.

Tạm dừng hoặc giới hạn theo đúng tài khoản, asset và phạm vi liên quan. Không tắt toàn bộ cơ chế quản lý của những đối tượng không bị ảnh hưởng chỉ để đơn giản hóa xử lý.

Nếu tạm dừng một tác vụ cũng làm dừng thu hồi lease hoặc quyền tạm, cần có người và cơ chế thay thế theo dõi các đối tượng đó. Không để việc ổn định tình huống tạo quyền tồn tại vô thời hạn.

### 6.2. Xác minh tác vụ trước vẫn còn chạy hay không

Client hết thời gian chờ không đồng nghĩa tiến trình phía đích đã kết thúc. Một yêu cầu mới có thể chạy cùng yêu cầu cũ và thay credential thêm lần nữa.

Cần tra cứu trạng thái trong phạm vi có thể, giữ định danh yêu cầu và xác định tác vụ nào còn khả năng tạo hiệu ứng. Không chỉ hủy cửa sổ thao tác rồi cho rằng mọi thay đổi đã bị hủy.

### 6.3. Bảo vệ bằng chứng và khả năng truy cập

Ghi thời điểm, đối tượng, tác vụ, kết quả quan sát được và phần chưa biết. Hạn chế tạo thêm lần đăng nhập sai có thể khóa tài khoản.

Không xóa đối tượng PAM, lịch sử hoặc log chỉ để đưa giao diện về trạng thái sạch. Những dữ liệu đó có thể là bằng chứng cần thiết để biết credential nào đã được dùng và tài khoản nào đã được tạo.

## 7. Lập bản đồ trạng thái thực tế

### 7.1. Đánh giá theo nhiều chiều

Một mô hình trạng thái tham chiếu:

~~~text
Identity state:
  Tài khoản nào tồn tại và còn hoạt động?

Credential state:
  Credential nào có hiệu lực tại nguồn xác thực?

Vault state:
  Đối tượng và phiên bản nào đang được PAM quản lý?

Consumer state:
  Mỗi consumer đang đọc và dùng phiên bản nào?

Authorization state:
  Role, nhóm và grant nào đang có hiệu lực?

Session state:
  Những phiên hoặc kết nối nào vẫn hoạt động?

Automation state:
  Tác vụ nào còn có thể thay đổi các trạng thái trên?

Evidence state:
  Điều gì đã xác minh, điều gì mới suy đoán?
~~~

Không bắt buộc phải biết ngay giá trị của mọi chiều. Điều quan trọng là ghi rõ unknown thay vì tự chuyển thành một trạng thái có lợi cho việc tiếp tục.

### 7.2. Chọn nguồn có thẩm quyền cho từng câu hỏi

| Câu hỏi | Nguồn cần xem xét |
|---|---|
| Tài khoản tồn tại không? | Nguồn quản lý tài khoản hoặc hệ thống đích |
| Credential có dùng được không? | Cơ chế xác thực tại đúng nguồn, với phương pháp kiểm tra phù hợp |
| Vault lưu phiên bản nào? | Trạng thái đối tượng tại vault |
| Consumer dùng reference nào? | Cấu hình và trạng thái chạy của consumer |
| Grant đã bị gỡ chưa? | Nguồn ủy quyền và điểm thực thi |
| Phiên còn mở không? | Gateway hoặc đích quản lý phiên |
| Rotation đã hoàn tất chưa? | Kết hợp sự kiện tác vụ, đích, vault và consumer |

Một log “password changed” tại connector có thể chưa chứng minh vault đã lưu đúng hoặc consumer đã nhận. Ngược lại, một phiên bản mới trong vault chưa chứng minh đích chấp nhận credential đó.

### 7.3. Giới hạn kiểm tra để tránh tạo thêm sự cố

Không thử hàng loạt tất cả secret cũ và mới trên mọi đích. Cách đó có thể gây khóa tài khoản, tạo tải hoặc làm khó phân biệt sự kiện.

Dùng định danh, phiên bản, sự kiện và kiểm tra có giới hạn phù hợp khả năng nền tảng. Khi không đủ bằng chứng, có thể cần quy trình reconcile hoặc phục hồi có thẩm quyền thay vì tiếp tục đoán.

## 8. Chọn trạng thái phục hồi chấp nhận được

Trạng thái phục hồi nên mô tả cụ thể:

~~~text
Tài khoản nào tiếp tục tồn tại?
Credential nào là credential đang có hiệu lực?
Consumer nào được phép dùng credential đó?
Đường truy cập nào được phép?
Role và grant nào phải giữ hoặc thu hồi?
Phiên nào được tiếp tục hoặc kết thúc?
Tự động hóa nào được bật lại?
Ngoại lệ còn lại có owner và thời hạn nào?
~~~

Không viết mục tiêu chung như “trả hệ thống về bình thường”. Hai người có thể hiểu “bình thường” khác nhau: một người khôi phục đăng nhập trực tiếp bằng tài khoản chung, người khác giữ đường gateway và sửa consumer.

### 8.1. Đánh giá trạng thái cũ trước khi tái sử dụng

Trạng thái cũ có thể chứa:

- Credential đã bị biết rộng hoặc nghi lộ.
- Quyền quản trị thường trực vượt nhu cầu.
- Đường truy cập trực tiếp không có bằng chứng.
- Tài khoản dùng chung không còn owner.
- Cấu hình không còn phù hợp với môi trường hiện tại.

Nếu không thể chấp nhận trạng thái cũ, cần chọn roll forward hoặc một trạng thái tạm thời khác có kiểm soát.

### 8.2. Phân biệt phục hồi kỹ thuật với chấp nhận rủi ro

Dịch vụ hoạt động lại là một kết quả kỹ thuật. Việc cho phép tiếp tục hoạt động với một kiểm soát chưa đáp ứng là quyết định quản trị riêng.

Một ngoại lệ cần chỉ rõ phần sai lệch, phạm vi, owner, thời hạn và điều kiện kết thúc. Không biến hành động phục hồi thành miễn kiểm soát không có mốc kết thúc.

## 9. Ma trận lựa chọn hành động theo trạng thái

| Trạng thái đã xác minh | Hướng xử lý có thể phù hợp | Điều phải xác minh thêm |
|---|---|---|
| Chỉ tạo metadata, chưa thay đổi đích hoặc consumer | Gỡ hoặc vô hiệu hóa cấu hình chưa dùng theo quy trình | Không còn tác vụ hay tham chiếu đang hoạt động |
| Vault có credential nhưng đích không chấp nhận | Sửa đăng ký hoặc reconcile theo nguồn đúng | Không nhầm endpoint, tài khoản hay nguồn xác thực |
| Đích đã đổi, vault chưa đồng bộ | Đối soát và cập nhật trạng thái quản lý qua cơ chế an toàn | Credential hợp lệ tại đích và quyền truy cập đúng |
| Đích và vault đúng, consumer còn dùng cũ | Sửa reference, quyền đọc hoặc refresh consumer | Không còn cache hoặc instance dùng phiên bản cũ |
| Một số consumer đã chuyển, số khác chưa | Chọn trạng thái chung và chuyển đổi có kiểm soát | Khả năng đồng tồn tại credential, ảnh hưởng dịch vụ |
| Role tạo ra quyền vượt phạm vi | Thu hồi hoặc thu hẹp grant sai, đánh giá hoạt động đã xảy ra | Phiên, credential và thay đổi bền vững liên quan |
| Kết quả rotation không xác định | Dừng retry, xác minh hoặc reconcile | Tác vụ cũ còn chạy và nguồn nào đã thay đổi |
| Credential cũ nghi lộ | Dùng credential mới và xử lý sự cố phù hợp | Các bản sao, phiên và đường sử dụng ngoài PAM |
| Tài khoản động được tạo nhưng không bàn giao | Thu hồi hoặc dọn theo vòng đời đã xác minh | Không có workload hợp lệ đang dùng |
| Đường qua PAM lỗi nhưng đường cũ còn phù hợp chính sách tạm thời | Phục hồi đường có giới hạn và bằng chứng | Thời hạn, quyền, giám sát và kế hoạch quay lại |

Bảng là khung ra quyết định, không phải chỉ thị thực hiện tự động. Điều kiện của từng nền tảng và phạm vi ảnh hưởng có thể làm phương án khác phù hợp hơn.

## 10. Runbook phục hồi theo từng bước

### Bước 1: Khoanh phạm vi

Xác định job onboarding, asset, tài khoản, nguồn credential, consumer và môi trường liên quan. Kiểm tra credential hoặc danh tính có được dùng ở nơi khác không.

Nếu một tài khoản tập trung phục vụ nhiều hệ thống, phạm vi thực tế có thể rộng hơn asset đang được onboard.

### Bước 2: Ổn định thay đổi

Kiểm soát retry, lịch rotation, pipeline và các actor có thể ghi cùng đối tượng. Giữ cơ chế theo dõi quyền tạm và phiên cần thu hồi.

### Bước 3: Giữ bằng chứng ban đầu

Ghi lại định danh yêu cầu, checkpoint cuối đã xác minh, thông báo lỗi, thời gian và phần chưa biết. Bảo vệ dữ liệu có thể chứa secret hoặc cấu hình nhạy cảm.

### Bước 4: Đối soát trạng thái

Xác minh theo các chiều identity, credential, vault, consumer, authorization, session và automation. Không chọn hành động chỉ từ một dashboard.

### Bước 5: Chọn phương án và điều kiện dừng

Xác định trạng thái đích, hành động cần làm, owner và điều kiện chuyển sang phục hồi khẩn cấp hoặc xử lý sự cố. Chỉ rõ phần nào được rollback, phần nào được sửa tiếp.

### Bước 6: Thực hiện theo checkpoint

Thực hiện từng hành động có phạm vi, ghi kết quả và xác minh trước khi qua bước phụ thuộc. Không lặp lại thao tác có hiệu ứng chỉ vì thiếu phản hồi.

### Bước 7: Xác minh toàn bộ luồng

Kiểm tra xác thực mới, hoạt động của consumer, quyền, phiên và tính bền vững của cấu hình trong phạm vi đã chọn.

### Bước 8: Bật lại tự động hóa có kiểm soát

Kiểm tra actor nào sẽ tiếp tục ghi và cấu hình mong muốn của chúng. Không bật lại một tác vụ còn dùng credential hoặc policy cũ.

### Bước 9: Đóng kỹ thuật và ghi phần còn lại

Ghi trạng thái cuối, bằng chứng, ngoại lệ, công việc khắc phục và điều kiện để thử onboarding lại. Không đóng chỉ vì yêu cầu hỗ trợ đã hết thời gian xử lý.

## 11. Phục hồi khi rotation credential thất bại

### 11.1. Phân biệt ba trạng thái trọng tâm

~~~text
Trường hợp A:
  Đích vẫn dùng credential cũ.
  Vault và consumer chưa thay.
  → Có thể sửa nguyên nhân trước khi thử lại.

Trường hợp B:
  Đích đã dùng credential mới.
  Vault hoặc consumer chưa đồng bộ.
  → Cần đối soát và hoàn tất chuyển đổi hoặc chọn trạng thái khác.

Trường hợp C:
  Chưa biết đích đang dùng credential nào.
  → Dừng thao tác đoán, xác minh hoặc reconcile có kiểm soát.
~~~

Các trường hợp có thể phức tạp hơn nếu hệ thống hỗ trợ nhiều credential đồng thời, có nhiều node hoặc có nhiều nguồn xác thực.

### 11.2. Không dùng rollback mật khẩu như mặc định

Đặt lại mật khẩu cũ có thể:

- Không được nền tảng cho phép theo chính sách vòng đời.
- Gây lỗi cho consumer đã chuyển sang credential mới.
- Tạo thêm một khoảng không đồng bộ.
- Tái sử dụng credential bị lộ.
- Không có tác dụng với phiên đã xác thực.

Phương án có thể phù hợp hơn là cấp một credential thay thế rồi đồng bộ các thành phần tới đó. Việc chọn phương án cần dựa trên khả năng kiểm tra và ảnh hưởng vận hành.

### 11.3. Reconcile cần đúng nguồn và đúng thẩm quyền

Một tài khoản local, tài khoản directory và token do issuer cấp có cơ chế phục hồi khác nhau.

Không reset một tài khoản trung tâm như thể nó chỉ phục vụ một máy. Tài khoản reconcile cần quyền vừa đủ cho phạm vi được quản lý, được bảo vệ và có bằng chứng sử dụng.

Nếu đang nghi có xâm nhập, cần kết hợp xử lý credential với điều tra và thu hồi đường truy cập liên quan. Đồng bộ được mật khẩu chưa đủ chứng minh sự cố đã kết thúc.

### 11.4. Bảo vệ credential trong quá trình phục hồi

Không đưa secret vào log debug, tham số dòng lệnh dễ quan sát, ticket hoặc báo cáo rollback. Chỉ dùng tham chiếu, phiên bản và định danh khi mô tả trạng thái.

Nếu một secret đã bị lộ trong lúc chẩn đoán, phải coi đó là một sự kiện cần xử lý vòng đời credential, không chỉ xóa dòng log rồi tiếp tục.

## 12. Khác biệt theo loại tài khoản và tài nguyên

| Đối tượng | Điều cần chú ý khi phục hồi |
|---|---|
| Tài khoản quản trị local | Tài khoản, mật khẩu, khóa và quyền có thể nằm trực tiếp tại đích |
| Tài khoản directory | Thay đổi có thể ảnh hưởng nhiều hệ thống và có độ trễ truyền dữ liệu |
| Tài khoản dịch vụ | Consumer, cache và kết nối đang chạy quyết định ảnh hưởng |
| Tài khoản cơ sở dữ liệu | Phiên đã mở có thể tiếp tục dù credential bị đổi hoặc grant thay đổi |
| Thiết bị mạng | Cần hiểu cấu hình đang chạy, lưu bền vững, node và controller |
| Khóa SSH | Thay private key trong vault chưa gỡ public key cũ tại đích |
| Token API | Có thể không đọc lại được giá trị sau khi tạo; có thể cần cấp mới và thu hồi cũ |
| Credential tạm thời | Lease tại PAM và hiệu lực tại đích có thể là hai cơ chế khác nhau |
| Grant JIT | Cần xử lý cả quan hệ cấp quyền và phiên hoặc token đã hình thành |
| Tài khoản khẩn cấp | Cần quản lý việc sử dụng, bằng chứng và vòng đời sau phục hồi |

Không có một chuỗi thao tác rollback đúng cho mọi đối tượng.

Đặc biệt, một thay đổi đã được lưu trong controller có thể ghi đè cấu hình phục hồi tại node. Một credential đã đổi ở nguồn trung tâm có thể tiếp tục được cache ở hệ thống khác. Mỗi nguồn ghi và bản sao có liên quan cần được nhận diện.

## 13. Xử lý đối tượng PAM mà không làm mất dấu vết

### 13.1. Vô hiệu hóa cấp mới khác với xóa đối tượng

Khi cần dừng sử dụng một cấu hình onboarding lỗi, có thể cần ngừng cấp mới, dừng rotation hoặc hạn chế policy. Các trạng thái đó khác với xóa credential hoặc lịch sử.

Trước khi loại bỏ đối tượng, cần biết:

- Có consumer còn tham chiếu tới nó không.
- Có tác vụ đang chạy hoặc lease cần xử lý không.
- Có credential cần phục hồi hoặc thu hồi không.
- Có phiên còn mở không.
- Bằng chứng phải được lưu theo yêu cầu nào.

Xóa đối tượng quá sớm có thể làm mất khả năng tìm credential hợp lệ hoặc ánh xạ giữa tài khoản tại đích và lần cấp.

### 13.2. Không phục hồi snapshot rộng để sửa một đối tượng

Một snapshot có thể chứa credential, policy và trạng thái lease ở thời điểm cũ. Trong khi đó, các hệ thống đích đã tiếp tục thay đổi.

Khôi phục snapshot rộng có thể làm vault lưu lại secret cũ, làm mất sự kiện mới hoặc tạo đối tượng mồ côi. Nếu thật sự cần khôi phục nền tảng, phải dùng quy trình phục hồi riêng và đối soát với trạng thái bên ngoài.

### 13.3. Giữ lịch sử quyết định

Không sửa lùi thời điểm hoặc thay kết quả cũ để báo cáo trông như onboarding chưa từng xảy ra.

Lịch sử nên thể hiện rõ điều đã xảy ra, phần được phục hồi, trạng thái còn tồn tại và ai xác nhận. Một job thất bại nhưng được phục hồi tốt vẫn là thông tin có giá trị vận hành.

## 14. Phục hồi consumer và dữ liệu cache

### 14.1. Liệt kê consumer thực tế

Không chỉ nhìn cấu hình triển khai. Cần xem các instance, worker, job theo lịch, công cụ backup và thành phần dự phòng trong phạm vi.

Một consumer có thể:

- Dùng trực tiếp secret được inject.
- Đọc secret reference khi khởi động.
- Refresh theo lịch.
- Cache trong bộ nhớ.
- Giữ kết nối đã xác thực nhiều giờ.

Khôi phục reference chưa chắc cập nhật tiến trình đang chạy. Ngược lại, khởi động lại mọi tiến trình có thể tạo gián đoạn không cần thiết và gây đồng loạt yêu cầu credential.

### 14.2. Chuyển đổi theo khả năng ứng dụng

Có ứng dụng hỗ trợ refresh an toàn hoặc hai credential trong giai đoạn chuyển tiếp; có ứng dụng cần tái tạo kết nối hoặc khởi động lại có phối hợp.

Phương án cần xác định thứ tự, tiêu chí thành công và ảnh hưởng dịch vụ. Không giả định luôn có khả năng dùng song song credential cũ và mới.

### 14.3. Kiểm tra hành vi sau phục hồi

Cần quan sát:

- Kết nối mới dùng đúng credential hoặc danh tính.
- Tác vụ nghiệp vụ đại diện hoàn tất trong phạm vi kiểm tra.
- Không có instance tiếp tục dùng reference sai.
- Tỷ lệ lỗi xác thực và retry trở về mức chấp nhận được.
- Consumer không ghi secret ra log.
- Thay đổi được giữ khi triển khai lại theo cấu hình mong muốn.

Một kết nối cũ còn hoạt động không chứng minh consumer sẽ sống sót qua lần tái kết nối tiếp theo.

## 15. Thu hồi quyền và xử lý phiên còn tồn tại

### 15.1. Rollback policy không tự thu hồi mọi hiệu ứng

Trong lúc onboarding, có thể đã tạo tài khoản, thêm thành viên nhóm, cấp role, mở phiên hoặc trả secret cho người dùng.

Gỡ mapping ở PAM thường chỉ chặn một đường quyết định mới. Cần kiểm tra tại đích:

- Grant có còn hiệu lực không.
- Token hoặc credential đã cấp còn dùng được không.
- Phiên có còn hoạt động không.
- Quyền kế thừa hoặc đường truy cập trực tiếp có tồn tại không.
- Chủ thể đã tạo thay đổi bền vững nào khác không.

### 15.2. Phiên và hoạt động đã xảy ra cần cách xử lý riêng

Kết thúc phiên ngăn một phần hoạt động tiếp diễn, nhưng không đảo ngược lệnh hoặc thay đổi đã thực hiện.

Nếu onboarding cấp quyền quá rộng hoặc có truy cập không được phép, cần đánh giá hoạt động trong khoảng đó. Việc phục hồi cấu hình không làm mất nghĩa vụ xử lý tác động và lưu bằng chứng.

### 15.3. Không hạ kiểm soát để làm kiểm tra thành công

Không dùng các cách như bỏ xác minh máy chủ, mở toàn bộ quyền, tắt audit hoặc cho phép xuất secret rộng chỉ để tác vụ trở lại màu xanh.

Nếu cần một thay đổi tạm thời để phục hồi, phải xác định rõ mục tiêu, phạm vi, điều kiện, thời hạn và cơ chế kiểm chứng. Thay đổi đó không nên bị ẩn trong một profile connector mới.

## 16. Mô hình trạng thái và giả mã điều phối

~~~mermaid
flowchart TD
    F["Phát hiện onboarding không đạt yêu cầu"] --> S["Ổn định và khoanh phạm vi"]
    S --> O["Đối soát trạng thái thực tế"]
    O --> U{"Đủ bằng chứng chọn phương án?"}
    U -->|Chưa| E["Xác minh bổ sung hoặc phục hồi theo thẩm quyền"]
    E --> O
    U -->|Đủ| D["Chọn trạng thái phục hồi"]
    D --> R["Rollback, hành động bù hoặc roll forward"]
    R --> V["Xác minh đích, consumer, quyền và phiên"]
    V --> P{"Đạt tiêu chí?"}
    P -->|Chưa| O
    P -->|Đạt| A["Bật lại tự động hóa có kiểm soát"]
    A --> C["Đóng kỹ thuật và ghi phần còn lại"]
~~~

Vòng xử lý không có nghĩa được thử vô hạn. Runbook cần điều kiện dừng, giới hạn thao tác và chuyển cấp khi không thể xác minh hoặc ảnh hưởng vượt phạm vi.

Giả mã:

~~~text
recover_onboarding(job):
    scope = resolve_exact_scope(job)
    stabilize_concurrent_changes(scope)
    evidence = collect_state_without_exposing_secrets(scope)

    if evidence.has_signs_of_compromise:
        engage_incident_handling_for_scope(scope)

    if not enough_evidence_for_safe_action(evidence):
        return NEEDS_CONTROLLED_RECOVERY_OR_MORE_EVIDENCE

    plan = choose_recovery_target(evidence, authorized_constraints)
    record_plan_and_stop_conditions(plan)

    for action in plan.actions:
        verify_action_preconditions(action)

        result = execute_with_tracking_reference(action)

        if result is ambiguous:
            record_unknown_state(action)
            return RECONCILE_BEFORE_RETRY

        verify_postcondition(action)

    verify_target_consistency()
    verify_consumers()
    verify_grants_credentials_and_sessions()
    verify_evidence_and_remaining_exceptions()

    resume_automation_only_if_preconditions_hold()
    return TECHNICALLY_RECOVERED_FOR_DEFINED_SCOPE
~~~

Đây là mô hình logic, không phải script thực thi. Đặc biệt, tính lặp an toàn của từng hành động phải được thiết kế; cùng một request ID không tự làm mọi hệ thống bên ngoài hỗ trợ chống lặp.

## 17. Tình huống xuyên suốt: onboarding tài khoản dịch vụ bị lệch credential

### 17.1. Bối cảnh

Một dịch vụ xử lý thanh toán dùng tài khoản kỹ thuật trên cơ sở dữ liệu. Mục tiêu onboarding là đưa credential vào vault, giảm quyền của tài khoản và chuyển consumer sang lấy secret qua cơ chế được quản lý.

Có ba instance ứng dụng và một job đối soát. Một công cụ triển khai duy trì secret reference trong cấu hình mong muốn.

Trong lần thay đổi:

1. Đối tượng vault được tạo.
2. Credential tại cơ sở dữ liệu được đổi.
3. Connector timeout trước khi hoàn tất ghi nhận.
4. Một instance đã cập nhật reference; hai instance và job đối soát chưa cập nhật.
5. Các kết nối cũ vẫn hoạt động, nhưng kết nối mới bắt đầu lỗi.

### 17.2. Sai lầm dễ mắc

- Xóa đối tượng vault vì job báo lỗi.
- Đặt mật khẩu cũ trở lại mà không biết instance nào đã chuyển.
- Khởi động lại mọi consumer ngay lập tức.
- Cho connector retry rotation liên tục.
- Đánh dấu đã phục hồi vì một truy vấn qua kết nối cũ thành công.

Các hành động này có thể làm mất thêm thông tin hoặc biến lỗi từng phần thành gián đoạn toàn bộ.

### 17.3. Đối soát và lựa chọn phương án

Đội xử lý dừng retry theo tài khoản liên quan, giữ bằng chứng và xác định trạng thái nguồn xác thực bằng phương pháp được cho phép.

Giả sử xác minh được credential mới đã có hiệu lực và có thể đưa vault về đồng bộ qua cơ chế phục hồi an toàn. Credential cũ không được chọn lại vì đã được phân phối rộng và không còn phù hợp mục tiêu.

Trạng thái phục hồi được chọn là:

~~~text
Đích dùng credential mới đã xác minh.
Vault quản lý đúng credential và phiên bản.
Mọi consumer dùng cùng reference được duyệt.
Role giữ trong phạm vi đã xác minh.
Không còn tác vụ retry chồng chéo.
Các kết nối và job được kiểm tra theo tiêu chí đã định.
~~~

Phương án thực chất là roll forward phần còn thiếu, đồng thời xử lý cấu hình và consumer sai lệch.

### 17.4. Thực hiện và kiểm chứng

Đội xử lý cập nhật trạng thái quản lý, sửa cấu hình mong muốn và chuyển consumer theo khả năng refresh của ứng dụng.

Việc kiểm chứng gồm kết nối mới của các instance, job đối soát trong phạm vi, lỗi xác thực, role tại đích và các consumer phụ thuộc.

Tự động hóa chỉ được bật lại khi đã dùng đúng reference và không tiếp tục áp dụng cấu hình cũ. Hồ sơ ghi riêng kết quả rotation, cập nhật consumer và quyền, thay vì một nhãn “rollback done” duy nhất.

### 17.5. Phần cần theo dõi tiếp

Có thể còn công việc như loại bỏ bản sao credential cũ, kiểm tra đường truy cập ngoài luồng mới hoặc cải thiện connector để xử lý timeout.

Các công việc đó cần owner và trạng thái rõ. Phục hồi dịch vụ không tự đồng nghĩa toàn bộ mục tiêu onboarding ban đầu đã được nghiệm thu.

## 18. Hồ sơ phục hồi và bằng chứng kết thúc

Một hồ sơ logic có thể gồm:

~~~yaml
recovery:
  recovery_id: recovery-042
  onboarding_job_id: onboard-service-017
  scope:
    asset_id: payment-database-prod
    account_id: payment-service-account
    affected_consumers:
      - application-group
      - reconciliation-job

  failure:
    category: credential-state-divergence
    last_verified_checkpoint: target-credential-change-confirmed
    ambiguous_steps:
      - connector-result-persistence

  selected_strategy: roll-forward-consumer-transition
  target_state_reference: approved-recovery-target-042
  credential_reference: managed-secret-017
  credential_value_in_report: prohibited

  verification:
    target_authentication: verified-with-new-connection
    consumer_transition: verified-for-listed-consumers
    effective_privileges: verified-for-defined-role
    sessions_and_grants: reviewed-with-recorded-scope
    automation_resumption: verified

  remaining_work_reference: follow-up-042
  final_state: technically-recovered-for-defined-scope
~~~

Các định danh và giá trị chỉ minh họa; không phải kết quả của một sự cố thật hay cú pháp của sản phẩm cụ thể.

### 18.1. Những bằng chứng cần phân biệt

| Tuyên bố | Bằng chứng phù hợp |
|---|---|
| Đã dừng thay đổi chồng chéo | Trạng thái tác vụ, scheduler và actor trong phạm vi |
| Đã đồng bộ credential | Bằng chứng nguồn xác thực, đối tượng quản lý và phiên bản liên quan |
| Consumer đã phục hồi | Kiểm tra kết nối mới và tác vụ đại diện |
| Quyền đã đúng | Cấu hình hoặc kết quả đánh giá quyền tại điểm thực thi |
| Grant đã thu hồi | Trạng thái grant đọc lại từ nguồn có thẩm quyền |
| Phiên đã đóng | Xác nhận từ gateway hoặc đích tương ứng |
| Tự động hóa dùng trạng thái đúng | Cấu hình và kết quả khi tiếp tục xử lý |
| Ngoại lệ đã được quản trị | Phạm vi, thẩm quyền, owner, thời hạn và điều kiện kết thúc |

Bằng chứng phải tương xứng với phạm vi tuyên bố. Một consumer hoạt động không chứng minh mọi consumer đã chuyển; một phiên đã đóng không chứng minh không còn phiên khác.

### 18.2. Tiêu chí đóng kỹ thuật

Có thể đóng phần phục hồi kỹ thuật khi:

1. Trạng thái cuối đã được xác minh trong phạm vi xác định.
2. Không còn thao tác không xác định chưa có hướng xử lý.
3. Credential và cấu hình quản lý nhất quán theo thiết kế.
4. Consumer cần thiết hoạt động theo tiêu chí.
5. Quyền, grant và phiên liên quan đã được xử lý hoặc ghi rõ giới hạn.
6. Tự động hóa được tiếp tục đúng điều kiện.
7. Ngoại lệ và công việc còn lại có trách nhiệm rõ ràng.
8. Bằng chứng được lưu và liên kết.

Đóng kỹ thuật, đóng sự cố, hoàn tất onboarding và chấp nhận rủi ro là các quyết định khác nhau. Không dùng một trạng thái để thay thế tất cả.

## 19. Chuẩn bị thử onboarding lại

Không nên chạy lại cùng luồng chỉ vì dịch vụ đã hoạt động.

Cần xác định nguyên nhân và thay đổi điều kiện gây lỗi, chẳng hạn:

- Connector không xử lý được phản hồi hoặc timeout.
- Thiếu quyền đúng chức năng.
- Không có cơ chế đối soát sau thay đổi credential.
- Consumer không hỗ trợ refresh như giả định.
- Controller ghi đè cấu hình.
- Phạm vi credential dùng chung chưa được nhận diện.
- Thiếu bằng chứng hoặc cơ chế theo dõi bước đã hoàn tất.

Lần thử lại cần dùng trạng thái hiện tại làm điểm bắt đầu. Không mặc định hệ thống vẫn ở baseline của lần trước.

Có thể chia triển khai thành nhóm nhỏ, kiểm tra bước có rủi ro chính và chỉ mở rộng sau khi có bằng chứng. Nếu một khả năng chưa được kiểm chứng, phải giữ rõ trạng thái đó trong hồ sơ.

Các chỉ số có ích gồm thời gian xác định trạng thái thực tế, số bước không xác định, tỷ lệ phục hồi consumer đầy đủ, độ trễ thu hồi quyền và số lỗi lặp lại cùng nguyên nhân. Thời gian đóng ticket ngắn không phải thước đo duy nhất của phục hồi tốt.

## 20. Lỗi thường gặp và bài tập áp dụng

### 20.1. Các lỗi thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Thất bại trên PAM nghĩa là đích chưa đổi | Lặp thao tác và tạo lệch trạng thái | Đối soát trước khi retry |
| Xóa đối tượng vault để rollback | Mất tham chiếu hoặc khả năng phục hồi | Kiểm tra dependency, vòng đời và bằng chứng |
| Luôn đặt lại mật khẩu cũ | Tái tạo rủi ro hoặc làm consumer mới lỗi | Chọn credential và trạng thái đích theo bằng chứng |
| Dùng phiên cũ để xác nhận thành công | Bỏ sót lỗi ở lần xác thực tiếp theo | Kiểm tra bằng kết nối mới |
| Chỉ sửa vault, bỏ consumer | Dịch vụ tiếp tục dùng secret sai | Xác minh toàn bộ consumer trong phạm vi |
| Chỉ sửa consumer, bỏ cấu hình mong muốn | Lần triển khai sau tái tạo lỗi | Cập nhật đúng nguồn ghi cấu hình |
| Dừng mọi scheduler kể cả ngoài phạm vi | Ảnh hưởng không cần thiết, có thể chậm thu hồi | Khoanh phạm vi và theo dõi tác vụ bị dừng |
| Gỡ role ở PAM là coi hết quyền | Grant, token và phiên còn tồn tại | Xác minh tại điểm thực thi |
| Khôi phục snapshot rộng cho lỗi nhỏ | Ghi đè thay đổi hợp lệ, tạo lệch trạng thái | Phục hồi theo đối tượng hoặc quy trình thảm họa riêng |
| Bỏ trust hoặc audit để kết nối được | Hạ kiểm soát trong quá trình phục hồi | Sửa nguyên nhân và quản trị ngoại lệ rõ ràng |
| Sửa lịch sử để coi chưa từng onboarding | Mất khả năng điều tra | Giữ đúng thời điểm và kết quả |
| Đóng ngay khi dịch vụ hoạt động lại | Bỏ sót quyền và credential còn tồn tại | Đóng theo tiêu chí và phạm vi bằng chứng |

### 20.2. Bài tập

Một đội onboard tài khoản quản trị cho một cặp thiết bị mạng. Vault đã tạo đối tượng, một node báo đổi mật khẩu thành công, node còn lại timeout. Endpoint logic vẫn cho đăng nhập bằng một phiên đang mở. Công cụ quản lý cấu hình còn giữ thiết lập cũ. Đội đề xuất xóa đối tượng vault và chạy onboarding lại ngay.

Hãy phân tích:

1. Những trạng thái nào hiện chưa biết?
2. Vì sao phiên đang mở không chứng minh credential nào có hiệu lực?
3. Xóa đối tượng vault có thể làm mất điều gì?
4. Cần kiểm soát những actor nào trước khi sửa?
5. Khi nào chọn rollback, khi nào chọn roll forward hoặc reconcile?
6. Những bằng chứng nào đủ để đóng phục hồi trong phạm vi hai node?

Hướng phân tích:

- Cần biết trạng thái từng node, mô hình đồng bộ, credential nguồn, vault, controller và các phiên liên quan.
- Phiên cũ có thể tồn tại độc lập với việc credential đã đổi.
- Vault có thể giữ tham chiếu, phiên bản và lịch sử cần để đối soát.
- Retry, rotation, controller và thao tác thủ công có thể ghi chồng.
- Phương án phụ thuộc trạng thái đã xác minh, độ an toàn của credential cũ và khả năng đồng bộ consumer.
- Cần kết quả tại từng phạm vi liên quan, xác thực mới, tính bền vững cấu hình, trạng thái quyền/phiên và điều kiện bật lại tự động hóa.

## 21. Các điểm cần nắm

Rollback onboarding lỗi là một quá trình phục hồi trạng thái có kiểm chứng trên nhiều thành phần. Nó có thể gồm đảo cấu hình, hành động bù, reconcile hoặc hoàn tất phần còn thiếu của thiết kế mới.

Điểm xuất phát là trạng thái thực tế, đặc biệt khi thay đổi credential hoặc cấp quyền đã diễn ra nhưng phản hồi không rõ. Không xóa dấu vết, lặp thao tác hoặc dùng trạng thái của một thành phần để suy ra toàn bộ hệ thống.

Kết quả phục hồi cần làm rõ credential nào có hiệu lực, consumer nào đã chuyển, quyền và phiên nào còn tồn tại, tự động hóa nào được tiếp tục và bằng chứng nào xác nhận từng phần.
