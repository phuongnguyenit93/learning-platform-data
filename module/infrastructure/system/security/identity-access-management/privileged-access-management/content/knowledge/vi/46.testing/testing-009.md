# Test vault restore

## 1. Mục tiêu của phép thử khôi phục vault

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), vault lưu giữ hoặc bảo vệ credential của tài khoản quản trị, tài khoản dịch vụ và các hệ thống nhạy cảm. Khi vault mất dữ liệu hoặc không thể hoạt động, ảnh hưởng không chỉ là một giao diện quản trị bị gián đoạn: người vận hành có thể không lấy được credential, ứng dụng không nhận được secret, quy trình luân chuyển bị dừng và hoạt động ứng phó sự cố thiếu bằng chứng.

**Test vault restore** là một phép thử có kiểm soát nhằm chứng minh rằng từ một tập bản sao lưu và các phụ thuộc đã xác định, đội vận hành có thể khôi phục dịch vụ vault đến trạng thái sử dụng được, trong giới hạn thời gian và mất dữ liệu cho phép, đồng thời giữ đúng các ràng buộc bảo mật.

Khôi phục thành công phải trả lời được cả ba câu hỏi:

1. Có dựng lại và giải mã được dữ liệu cần thiết không?
2. Những chủ thể được phép có thực hiện đúng công việc của họ, với quyền tối thiểu không?
3. Những chủ thể bị cấm, credential đã thu hồi và các đường truy cập không được phê duyệt có tiếp tục bị chặn không?

Một tiến trình chạy được, một cổng TCP mở hoặc một API health trả kết quả tốt chỉ chứng minh một phần của quá trình. Chúng chưa chứng minh vault có thể phục vụ tài khoản quản trị, ứng dụng và người kiểm toán một cách an toàn.

Sau bài học, người học cần có khả năng xây dựng phạm vi diễn tập; chuẩn bị môi trường cô lập; kiểm tra dữ liệu, khóa mã hóa và các phụ thuộc; thiết kế ca kiểm thử dương tính và âm tính; đo RTO/RPO; xử lý credential không còn đồng bộ; và tạo hồ sơ bằng chứng đủ để người khác xem xét kết quả.

## 2. Phân biệt restore với những hoạt động gần giống

| Hoạt động | Điều được chứng minh | Điều chưa được chứng minh |
|---|---|---|
| Tạo backup thành công | Công cụ đã tạo ra một artifact theo cấu hình | Artifact có đủ dữ liệu, giải mã được hoặc phục hồi được không |
| Sao chép dữ liệu sang nút dự phòng | Một đường nhân bản dữ liệu hoạt động | Có quay lại trạng thái sạch trước lỗi logic hoặc xóa nhầm không |
| Kiểm tra checksum của backup | Artifact đang có khớp với giá trị kiểm tra được đối chiếu | Dữ liệu có nhất quán về nghiệp vụ hoặc nguồn checksum có đáng tin không |
| Restore dữ liệu và khởi động vault | Phần phục hồi đã được thực hiện đến mức dịch vụ chạy được | Chính sách, thu hồi quyền, credential và audit đã đúng chưa |
| Diễn tập khôi phục đầy đủ | Chuỗi người, công cụ, dữ liệu và phụ thuộc đã được thử trong phạm vi khai báo | Các môi trường, tải và tình huống ngoài phạm vi có cùng kết quả không |

Nhân bản không thay thế bản sao lưu độc lập. Một thao tác xóa nhầm, thay đổi chính sách sai hoặc dữ liệu đã bị phá hoại có thể được nhân bản rất nhanh. Ngược lại, một backup cũ có thể khôi phục dữ liệu nhưng không đáp ứng giới hạn mất dữ liệu của doanh nghiệp.

Phạm vi cũng cần phân biệt rõ: khôi phục toàn bộ vault, khôi phục một kho logic, khôi phục metadata hay phục hồi một phiên bản secret là những năng lực khác nhau. Không suy diễn việc phục hồi được một secret thử nghiệm thành bằng chứng cho khôi phục toàn hệ thống.

## 3. Xác định đối tượng khôi phục và chuỗi phụ thuộc

Một vault thường có nhiều thành phần tạo thành một tập phục hồi. Tùy sản phẩm, một số thành phần nằm trong snapshot, một số được quản lý riêng và một số do nhà cung cấp dịch vụ vận hành.

| Thành phần | Cần kiểm chứng | Lỗi thường bộc lộ khi restore |
|---|---|---|
| Dữ liệu secret và phiên bản | Đủ đối tượng, đúng điểm phục hồi và đọc được bản cần thiết | Có tên secret nhưng thiếu payload hoặc sai phiên bản |
| Metadata và cấu trúc kho | Đường dẫn, owner, phân loại, nhãn và liên kết đúng | Secret được phục hồi nhưng ứng dụng tìm sai đường dẫn |
| Khóa mã hóa, cơ chế mở khóa | Khôi phục truy cập đến đúng khóa và đúng cơ chế được hỗ trợ | Backup hợp lệ nhưng vault không giải mã được |
| Chính sách phân quyền | Vai trò, phạm vi tài nguyên, điều kiện truy cập và từ chối đúng | Restore làm xuất hiện quyền quá rộng hoặc hồi sinh quyền cũ |
| Cấu hình xác thực | IdP, MFA, chứng thư, ánh xạ nhóm và tài khoản máy phù hợp | Người dùng đăng nhập được nhưng nhận sai vai trò |
| Cấu hình luân chuyển | Đúng plugin, lịch, quyền cập nhật và hệ thống đích | Tác vụ phục hồi chạy ngay và đổi credential ngoài dự kiến |
| Cấu hình tích hợp | API, proxy phiên, agent, connector và ứng dụng thử nghiệm hoạt động | Vault khỏe nhưng các bên sử dụng không kết nối được |
| Audit và bằng chứng phiên | Có ghi nhận mới và truy xuất được dữ liệu lịch sử theo phạm vi | Không chứng minh được ai đã lấy secret sau phục hồi |
| Hạ tầng hỗ trợ | DNS, thời gian, TLS, storage, mạng và phiên bản phần mềm phù hợp | Lỗi chứng thư, lease hết hạn hoặc storage không tương thích |

Khóa phục hồi phải được hiểu theo kiến trúc cụ thể. Có hệ thống dùng phần chia mở khóa, có hệ thống dùng HSM hoặc dịch vụ quản lý khóa, và có hệ thống có recovery key với quyền khác unseal key. Không mặc định các cơ chế này thay thế được cho nhau.

Việc tạo lại một khóa mới cùng tên không đồng nghĩa khôi phục được khóa cũ. Khả năng giải mã còn phụ thuộc vào vật liệu khóa, phiên bản khóa, định danh và cơ chế ràng buộc của hệ thống. Quyền đọc backup cũng không tự động mang lại quyền sử dụng khóa.

Một lỗi kiến trúc quan trọng là đặt credential duy nhất để truy cập nơi chứa backup hoặc khóa giải mã ngay trong vault đang cần phục hồi. Diễn tập phải phát hiện vòng phụ thuộc đó và chứng minh có đường bootstrap độc lập, được kiểm soát và có audit.

Với vault do nhà cung cấp quản lý, đội sử dụng có thể không được phục hồi storage hoặc khóa nền. Khi đó, phép thử tập trung vào năng lực được cung cấp: phục hồi tài nguyên logic, kích hoạt quy trình hỗ trợ, nhận lại dữ liệu, xác minh quyền và kiểm tra ứng dụng. Không dùng quy trình tự quản trị cho một dịch vụ không cho phép can thiệp tầng đó.

## 4. Lập hợp đồng diễn tập trước khi thao tác

Một hợp đồng diễn tập biến yêu cầu “thử restore” thành tập điều kiện có thể quan sát và đánh giá. Tài liệu cần được thống nhất trước khi bắt đầu bấm giờ hoặc chọn backup.

### 4.1. Phạm vi và tình huống

Ví dụ: giả lập mất cụm vault trong một vùng, phục hồi vào môi trường lab đã chuẩn bị, sử dụng một backup cụ thể và credential tổng hợp. Phạm vi kiểm tra gồm đọc secret, ánh xạ vai trò, quyền bị từ chối, luân chuyển credential đến hệ thống giả lập và chuyển log audit đến nơi thu thập thử nghiệm.

Cần chỉ rõ những phần không được diễn tập, chẳng hạn khôi phục HSM vật lý, kết nối IdP thật hoặc chuyển lưu lượng sản xuất. Các loại trừ này là giới hạn của kết luận, không phải điều được xem như đã đạt.

### 4.2. Trách nhiệm và quyền thực hiện

Tách tối thiểu các vai trò vận hành, kiểm chứng bảo mật và phê duyệt kết quả. Người có quyền tạo môi trường không nhất thiết có quyền đọc toàn bộ secret. Người giữ phần khóa không nên tự mình nắm đủ mọi điều kiện giải mã nếu thiết kế yêu cầu nhiều người phối hợp.

Quyền phục hồi có thể được cấp theo JIT cho một khoảng thời gian, gắn mã diễn tập và hết hiệu lực sau khi hoàn thành. Với thao tác hệ điều hành, dùng phạm vi lệnh và quyền phù hợp theo nguyên tắc JEA nếu nền tảng hỗ trợ. Quyền khẩn cấp cần có người phê duyệt, thời hạn và log riêng.

### 4.3. Tiêu chí đạt, dừng và quay lui

Ví dụ tiêu chí đạt:

- Toàn bộ ca kiểm thử bắt buộc có bằng chứng và kết quả đúng.
- RTO không quá 90 phút và RPO không quá 30 phút theo cách đo đã thống nhất.
- Không có luồng mạng hoặc tác vụ luân chuyển đến hệ thống sản xuất.
- Không có tài khoản đã thu hồi nhận lại quyền.
- Audit ghi nhận được truy cập thành công, truy cập bị từ chối và hoạt động phục hồi trong phạm vi.
- Có kết quả đối soát credential và phương án xử lý mọi sai lệch trước khi cân nhắc kết nối thật.

Ví dụ điều kiện dừng ngay: phát hiện môi trường lab gọi đến hệ thống sản xuất, giải mã bằng vật liệu khóa ngoài phạm vi được phép, lộ secret vào log hoặc xuất hiện dấu hiệu backup không đáng tin. Khi dừng, giữ bằng chứng cần thiết, cô lập môi trường và xử lý theo người phụ trách đã ghi trong hợp đồng.

Quay lui trong diễn tập cô lập thường là dừng cụm đã phục hồi và giữ vault sản xuất tiếp tục phục vụ như trước. Trong khôi phục thật, phương án quay lui phức tạp hơn vì có thể đã phát sinh ghi mới hoặc thay đổi credential. Không giả định chỉ cần trỏ DNS về địa chỉ cũ là mọi trạng thái sẽ trở lại nhất quán.

## 5. Chọn điểm phục hồi và kiểm tra nguồn backup

### 5.1. Chọn theo mục tiêu dữ liệu

Không chọn backup chỉ vì đó là file mới nhất. Cần xác định thời điểm nghi ngờ dữ liệu bắt đầu hỏng, thời điểm thay đổi quan trọng cuối cùng và điểm phục hồi được doanh nghiệp chấp nhận.

Nếu giả lập xóa nhầm lúc 10:00, một backup lúc 10:05 có thể đã chứa kết quả xóa. Nếu giả lập mất hạ tầng lúc 10:00 mà dữ liệu trước đó vẫn sạch, backup mới nhất nhất quán trước sự cố thường là ứng viên phù hợp hơn.

Ghi lại ít nhất:

- Định danh backup và nguồn tạo.
- Thời điểm bắt đầu, hoàn thành và điểm nhất quán dữ liệu được công cụ xác nhận.
- Phiên bản vault và backend storage liên quan.
- Danh mục thành phần được bảo vệ và những thành phần nằm ngoài backup.
- Khóa, quyền hoặc dịch vụ ngoài cần thiết để sử dụng backup.
- Cách kiểm tra tính toàn vẹn, nguồn gốc và quyền truy cập artifact.

Thời điểm hoàn thành tải file lên kho backup không tự động là điểm dữ liệu được bảo vệ. Một snapshot có thể hoàn tất lúc 08:40 nhưng điểm dữ liệu nhất quán của nó là 08:39.

### 5.2. Toàn vẹn, nguồn gốc và tính nhất quán

Đối chiếu checksum có thể phát hiện artifact bị thay đổi so với giá trị chuẩn. Giá trị chuẩn phải đến từ nguồn được bảo vệ độc lập hoặc manifest được xác thực. Nếu một người có thể sửa cả backup lẫn file checksum đi cùng, phép đối chiếu đó chưa chứng minh nguồn gốc đáng tin.

Dùng cơ chế chữ ký hoặc xác thực manifest nếu quy trình backup có hỗ trợ. Kiểm tra quyền lưu trữ, lịch sử thao tác và cơ chế chống sửa/xóa theo thiết kế của tổ chức.

Checksum đúng cũng chưa đảm bảo snapshot nhất quán. Đối với hệ thống có nhiều thành phần, cần kiểm tra chúng có thuộc một tập phục hồi được hỗ trợ hay không. Ghép tùy ý database từ một thời điểm với file cấu hình, khóa hoặc object storage từ thời điểm khác có thể tạo ra trạng thái không phục vụ được.

Không tự sao chép thư mục storage đang hoạt động rồi coi đó là backup hợp lệ. Phương pháp backup và trình tự restore phải tuân theo cơ chế được hỗ trợ của nền tảng đang dùng.

## 6. Chuẩn bị môi trường phục hồi cô lập

Khôi phục một bản sao vault có thể tạo ra một bản sao quyền lực của hệ thống thật. Vì vậy, cô lập phải có trước khi khởi động các thành phần có khả năng thực hiện tác vụ nền.

Một mô hình diễn tập phù hợp:

```text
Kho backup được phép đọc
          |
          v
Vùng phục hồi cô lập -----> Kho bằng chứng và bộ thu audit thử nghiệm
          |
          +---------------> IdP/nhóm thử nghiệm
          |
          +---------------> Ứng dụng thử nghiệm
          |
          +---------------> Máy đích tổng hợp để thử rotation

Kết nối đến hệ thống sản xuất: bị chặn theo chính sách diễn tập
```

Các biện pháp cần xác minh bằng quan sát thực tế:

1. Mạng mặc định từ chối kết nối ra ngoài, chỉ mở những đích cần thiết.
2. DNS và endpoint của lab tách biệt, không ghi đè tên hoặc cân bằng tải thật.
3. TLS vẫn được kiểm tra bằng chuỗi tin cậy được cấu hình cho lab.
4. Các connector luân chuyển, cấp credential động, đồng bộ và điều khiển phiên chưa được bật đến hệ thống thật.
5. Log đi đến bộ thu của diễn tập; tránh làm nhiễu cảnh báo và hồ sơ vận hành thật.
6. Tài khoản thực hiện có quyền tối thiểu, giới hạn thời gian và được ghi nhận.
7. Đồng hồ hệ thống đồng bộ; không chỉnh lùi thời gian để làm token hoặc lease cũ có vẻ còn hiệu lực.

Ưu tiên dữ liệu và credential tổng hợp để thử chức năng. Nếu mục tiêu là chứng minh backup sản xuất thực sự khôi phục được, có thể cần sử dụng bản sao dữ liệu nhạy cảm trong vùng được bảo vệ theo phạm vi đã phê duyệt. Khi đó, giữ kiểm soát truy cập, mã hóa, audit và quy trình xử lý dữ liệu tương ứng; việc gắn nhãn “lab” không làm secret mất tính nhạy cảm.

Không tắt MFA, kiểm tra TLS hoặc cơ chế từ chối quyền chỉ để làm diễn tập nhanh hơn. Nếu một thành phần phải dùng bản thay thế trong lab, ghi rõ thành phần thay thế và giới hạn kết luận.

## 7. Chuẩn bị bộ dữ liệu kiểm chứng có ý nghĩa

Một bộ dữ liệu kiểm chứng tốt phải phân biệt được các điểm phục hồi và kiểm tra được cả quyền cho phép lẫn quyền từ chối.

### 7.1. Dữ liệu mốc và trạng thái mong đợi

Trước khi tạo backup thử nghiệm, chuẩn bị các đối tượng tổng hợp:

| Đối tượng | Trạng thái tại điểm backup | Trạng thái sau điểm backup | Điều cần quan sát sau restore |
|---|---|---|---|
| Secret A | Phiên bản 3 đang dùng | Tạo phiên bản 4 | Khôi phục đúng phiên bản thuộc điểm dữ liệu được chọn |
| Secret B | Chưa tồn tại | Được tạo mới | Không tự xuất hiện nếu nằm ngoài điểm phục hồi |
| Secret C | Đã bị thu hồi trước backup | Không đổi | Không trở lại trạng thái được cấp phát |
| Người dùng D | Được đọc một kho thử nghiệm | Bị thu hồi sau backup | Có nguy cơ quyền cũ xuất hiện; phải đối soát trước khi mở truy cập |
| Credential E | Đang khớp máy đích tổng hợp | Được luân chuyển sau backup | Phát hiện vault và máy đích không còn đồng bộ |

Các trường hợp sau backup không nhất thiết phải xuất hiện trong bản phục hồi cũ. Sự vắng mặt có thể là kết quả đúng của điểm phục hồi đã chọn. Điều quan trọng là phải nhận diện được phần dữ liệu thiếu và biết phần nào ảnh hưởng đến an toàn vận hành.

### 7.2. Kiểm tra secret mà không làm lộ giá trị

Với secret tổng hợp, có thể kiểm tra giá trị mong đợi trong bộ kiểm thử được bảo vệ. Với secret thật, ưu tiên một thao tác xác thực có kiểm soát đến đích thử nghiệm được phép, hoặc cơ chế xác minh mà chỉ trả kết quả đạt/không đạt.

Không đưa secret vào command line, ảnh chụp, ticket hoặc log kiểm thử. Không lưu hash thông thường của mật khẩu thật như một “bằng chứng an toàn”: secret có không gian đoán nhỏ vẫn có thể bị dò ngoại tuyến. Nếu cần đối chiếu fingerprint, phải chọn cơ chế và cách giữ khóa xác minh phù hợp, chẳng hạn HMAC với khóa tách biệt và phạm vi truy cập chặt chẽ.

Hồ sơ kết quả nên lưu mã đối tượng, phiên bản, thao tác và kết luận, không lưu payload nhạy cảm. Việc log chứa tên đường dẫn hoặc định danh tài khoản cũng cần xét theo chính sách phân loại dữ liệu.

## 8. Thực hiện restore theo các cổng kiểm chứng

Trình tự kỹ thuật cụ thể phụ thuộc nền tảng. Chuỗi dưới đây là khung kiểm thử, không phải tập lệnh có thể áp dụng trực tiếp cho mọi sản phẩm.

### Cổng 1 — Chốt đầu vào và bắt đầu đo

Xác nhận backup, manifest, phạm vi quyền và người thực hiện. Ghi mốc bắt đầu theo định nghĩa RTO đã chọn. Với diễn tập, ghi rõ đó là thời điểm công bố sự cố giả lập; nếu môi trường đã được dựng sẵn, phải ghi việc chuẩn bị đó nằm trong hay ngoài thời gian đo.

Lưu định danh phiên bản phần mềm, cấu hình hạ tầng và dấu thời gian của nguồn dữ liệu. Không ghi khóa mở vault hoặc token bootstrap vào biên bản.

### Cổng 2 — Dựng nền và kiểm tra cô lập

Kiểm tra storage, dung lượng, DNS, TLS, thời gian và các dịch vụ cần thiết. Chứng minh đường kết nối sản xuất bị chặn trước khi mở connector hoặc scheduler.

Nếu quy trình yêu cầu tắt một số thành phần trước restore, thực hiện đúng trình tự được hỗ trợ. Không restore đè vào một cụm đang phục vụ chỉ để tiết kiệm thời gian diễn tập.

### Cổng 3 — Nạp tập phục hồi

Thực hiện thao tác restore bằng cơ chế của nền tảng, với phiên bản và backend phù hợp. Thu mã kết quả và log đã kiểm soát dữ liệu nhạy cảm.

Không mặc định snapshot của phiên bản mới có thể nạp vào phiên bản cũ. Nếu cần nâng cấp hoặc chuyển backend, đó là một kịch bản riêng có ma trận tương thích và tiêu chí kiểm chứng riêng.

### Cổng 4 — Khôi phục khả năng giải mã

Thực hiện quy trình mở khóa hoặc truy cập dịch vụ khóa với đúng phân quyền và điều kiện nhiều người nếu áp dụng. Xác minh vault đọc được một đối tượng tổng hợp đại diện.

Nếu thất bại ở đây, không tạo khóa mới rồi tiếp tục đánh dấu đạt. Phải xác định nguyên nhân: thiếu quyền, thiếu khóa, sai phiên bản khóa, sai danh tính môi trường hay tập phục hồi không tương thích.

### Cổng 5 — Kiểm tra dữ liệu và trạng thái an toàn

Đối chiếu số lượng đối tượng theo manifest, phiên bản và các dữ liệu mốc. Kiểm tra đầy đủ không chỉ qua đếm số lượng mà cả nội dung hoặc hành vi của mẫu đại diện và những đối tượng quan trọng.

Trước khi cho phép sử dụng rộng hơn, đối soát quyền đã thu hồi, token, lease, connector và credential thay đổi sau điểm backup. Giữ các kết nối nhạy cảm đóng cho đến khi xử lý xong.

### Cổng 6 — Kiểm tra chức năng và audit

Cho phép từng luồng thử nghiệm theo kế hoạch: đăng nhập, đọc secret, truy cập bị từ chối, cấp quyền JIT, hết hạn quyền, rotation và ghi audit. Mỗi phép thử có mã, kết quả mong đợi và liên kết bằng chứng.

Không mở toàn bộ kết nối chỉ vì luồng đọc secret đầu tiên thành công.

### Cổng 7 — Kết luận và kết thúc diễn tập

Chốt thời điểm dịch vụ đạt điều kiện phục hồi theo hợp đồng. Tổng hợp RTO, RPO, các ca không đạt và giới hạn phạm vi.

Kết thúc quyền tạm thời; thu hồi credential bootstrap; xử lý bản sao dữ liệu và giữ lại bằng chứng theo chính sách. Phân biệt rõ “hoàn thành diễn tập trong lab” với “đủ điều kiện chuyển lưu lượng sản xuất”.

## 9. Ma trận kiểm thử chức năng và bảo mật

Ma trận dưới đây là một khởi điểm. Đội vận hành bổ sung theo loại tài khoản đặc quyền, mô hình vault và tích hợp của mình.

| Mã | Phép thử | Kết quả mong đợi | Bằng chứng phù hợp |
|---|---|---|---|
| VR-01 | Khôi phục từ backup được chọn | Dịch vụ nạp đúng tập dữ liệu và đọc được đối tượng tổng hợp | Mã backup, log restore và phiên bản |
| VR-02 | Kiểm tra dữ liệu mốc | Phiên bản có/không có đúng với điểm phục hồi | Danh sách ID và kết luận đối chiếu |
| VR-03 | Chủ thể đúng quyền đọc secret | Chỉ đọc được kho và thao tác được cấp | Kết quả kiểm thử và audit tương ứng |
| VR-04 | Chủ thể không có quyền đọc cùng secret | Bị từ chối, không trả payload | Mã kết quả và sự kiện từ chối |
| VR-05 | Đăng nhập qua cơ chế xác thực của lab | Vai trò và điều kiện MFA đúng theo cấu hình thử nghiệm | ID phiên và ánh xạ vai trò |
| VR-06 | Cấp quyền JIT và chờ hết hạn | Quyền có hiệu lực đúng khoảng thời gian, hết hạn thì bị chặn | Mốc cấp/hết hạn và kết quả truy cập |
| VR-07 | Truy cập theo phạm vi JEA nếu áp dụng | Thao tác được phép thành công, thao tác ngoài phạm vi bị chặn | Mã thao tác và log phiên đã lọc |
| VR-08 | Luân chuyển credential trên máy đích tổng hợp | Vault và máy đích nhất quán, giá trị cũ không còn dùng theo thiết kế | ID rotation và kết quả xác thực |
| VR-09 | Ứng dụng lấy và dùng secret | Ứng dụng thực hiện được tác vụ tổng hợp cần thiết | Trace ID và kết quả tác vụ |
| VR-10 | Phát sinh truy cập thành công và bị từ chối | Cả hai được ghi và chuyển đến bộ thu diễn tập | Event ID, thời gian và ID diễn tập |
| VR-11 | Truy cập bằng chủ thể đã thu hồi | Bị chặn sau bước đối soát an toàn | Kết quả từ chối và nguồn trạng thái thu hồi |
| VR-12 | Kiểm tra kết nối đến đích sản xuất | Bị chặn trong diễn tập cô lập | Log chính sách mạng hoặc phép thử kết nối |
| VR-13 | Kiểm tra tài khoản khẩn cấp thử nghiệm | Đúng quy trình phê duyệt, đúng quyền và có audit | ID phê duyệt và sự kiện sử dụng |
| VR-14 | Đo thời gian và dữ liệu mất | Nằm trong giới hạn đã thống nhất | Timeline và đối chiếu dữ liệu mốc |

Đối với token, lease và credential động, cần đọc đúng ý nghĩa của trạng thái phục hồi trên nền tảng. Một bản ghi lease xuất hiện trong database không chứng minh credential tương ứng còn tồn tại hoặc còn hợp lệ ở dịch vụ đích.

Một ca kiểm thử chỉ được đánh dấu đạt khi có kết quả quan sát. “Không thấy lỗi trong log” không thay thế phép kiểm tra trực tiếp quyền bị từ chối hoặc xác thực vào đích thử nghiệm.

## 10. Thiết kế các ca âm tính cho quy trình restore

Ca âm tính kiểm tra hệ thống phản ứng đúng khi thiếu điều kiện hoặc đầu vào không hợp lệ. Chỉ thực hiện trên dữ liệu và môi trường thử nghiệm, không làm hỏng bản backup duy nhất.

| Tình huống thử nghiệm | Hành vi mong đợi | Dấu hiệu phải điều tra |
|---|---|---|
| Artifact thử nghiệm bị thay đổi | Kiểm tra toàn vẹn phát hiện và chặn sử dụng | Vẫn tiếp tục restore mà không có cảnh báo |
| Thiếu quyền sử dụng khóa | Không giải mã được; có thông báo lỗi và audit phù hợp | Quyền rộng khác âm thầm được dùng thay |
| Không đủ điều kiện nhiều người mở khóa | Không vượt qua được cổng mở khóa | Một người có thể thay thế toàn bộ điều kiện |
| Phiên bản hoặc backend không được hỗ trợ | Dừng có kiểm soát hoặc bị preflight chặn | Đội vận hành bỏ qua cảnh báo rồi đánh dấu đạt |
| IdP thử nghiệm không sẵn sàng | Hành vi đúng với thiết kế, không tự mở truy cập rộng | Cơ chế fallback cấp quyền vượt phạm vi |
| Bộ thu audit không sẵn sàng | Phản ứng đúng với chính sách: chặn, đệm hoặc cảnh báo như đã thiết kế | Mất log im lặng hoặc lưu vượt sức chứa |
| Credential tại máy đích đã đổi sau backup | Phát hiện lệch và không tự luân chuyển vào đích thật | Tác vụ nền thay đổi credential ngoài phạm vi |
| Chủ thể bị thu hồi sau backup | Trước khi mở truy cập, trạng thái thu hồi được áp dụng lại | Người dùng nhận lại quyền chỉ vì backup cũ |
| Backup vượt giới hạn RPO | Bị đánh dấu không đạt tiêu chí dữ liệu | Được ghi đạt chỉ vì dịch vụ vẫn khởi động |

Không mặc định mọi vault có cùng hành vi khi audit lỗi. Điều cần kiểm thử là cấu hình thực tế có đúng chính sách và có bảo vệ hoạt động đặc quyền trong giới hạn đã phê duyệt hay không. Nếu chính sách cho phép đệm log, phải kiểm tra sức chứa, thời gian chịu lỗi và cách phát hiện mất dữ liệu.

## 11. Xử lý credential và quyền đã thay đổi sau backup

Đây là phần dễ bị bỏ sót nhất. Khôi phục đưa dữ liệu vault về quá khứ, trong khi hệ thống đích, IdP và ứng dụng có thể vẫn ở hiện tại.

Ví dụ:

```text
08:00  Backup chứa credential C1 cho tài khoản dịch vụ thử nghiệm.
08:20  Rotation đổi credential ở vault và máy đích thành C2.
09:00  Giả lập sự cố; khôi phục backup 08:00 vào lab.

Sau restore:
  Vault phục hồi: C1
  Máy đích thử nghiệm hiện tại: C2
  Kết quả: dữ liệu restore đọc được nhưng xác thực bằng C1 thất bại.
```

Đây không nhất thiết là lỗi giải mã hay lỗi backup. Nó là sự lệch trạng thái giữa các hệ thống. Cách xử lý phải là một phần của runbook.

### 11.1. Phân loại và đối soát

Tạo danh sách theo ID credential, thời điểm thay đổi và hệ thống đích. Đối chiếu với nguồn lịch sử thay đổi hoặc nhật ký độc lập nằm ngoài miền sự cố nếu có. Không giả định log trong chính backup đã chứa mọi thay đổi diễn ra sau backup.

Có thể phân nhóm:

- Secret tĩnh chưa thay đổi: kiểm chứng bằng thao tác phù hợp.
- Credential đã luân chuyển: xác định phương án cập nhật hoặc reset có kiểm soát.
- Credential động hoặc lease: đối chiếu vòng đời ở dịch vụ đích, thu hồi hoặc cấp lại theo cơ chế được hỗ trợ.
- Token và tài khoản đã thu hồi: áp dụng trạng thái thu hồi hiện hành trước khi mở truy cập.
- Chứng thư: kiểm tra thời hạn, trạng thái thu hồi và ràng buộc danh tính, không chỉ kiểm tra file còn tồn tại.
- Connector hoặc lịch tác vụ: bật lại có chọn lọc sau khi xác minh đúng đích và quyền.

### 11.2. Không nối cụm cũ và cụm phục hồi tùy ý

Nếu cả cụm cũ lẫn cụm phục hồi cùng điều khiển một tập tài khoản, chúng có thể luân chuyển credential theo hai trạng thái khác nhau. Hệ quả là mất đồng bộ, gián đoạn ứng dụng hoặc khó xác định nguồn thay đổi.

Trước khi kết nối phục hồi thật, phải xác định rõ cụm nào có quyền ghi và thực hiện cơ chế ngăn cụm cũ tiếp tục tác động theo thiết kế phục hồi. Một thay đổi DNS không tự ngăn scheduler, agent hoặc connector cũ hoạt động.

Không đưa một nút vừa nạp snapshot vào cụm sống như một thao tác tùy ý. Việc tái gia nhập, đổi danh tính cụm hoặc phục hồi quorum phải theo quy trình được nền tảng hỗ trợ.

### 11.3. Khôi phục dữ liệu không có nghĩa khôi phục mọi quyền cũ

Backup có thể chứa chính sách cho người đã nghỉ việc hoặc token chưa bị thu hồi tại thời điểm đó. Do vậy, một cổng quan trọng trước mở truy cập là hợp nhất các thay đổi thu hồi từ nguồn tin cậy hiện hành.

Nếu không xác định được đầy đủ thay đổi sau backup, cần giữ phạm vi truy cập hạn chế và thực hiện các biện pháp giảm rủi ro đã thống nhất, chẳng hạn thu hồi/cấp lại nhóm credential liên quan. Không ghi kết quả “không có quyền hồi sinh” nếu chưa có nguồn đối soát đủ tin cậy.

## 12. Đo RTO và RPO đúng với điều đã thử

### 12.1. RTO: thời gian đến trạng thái phục vụ được chấp nhận

Recovery Time Objective — RTO là mục tiêu thời gian phục hồi. Giá trị quan sát trong diễn tập được tính bằng:

```text
Thời gian phục hồi quan sát =
    thời điểm đạt điều kiện dịch vụ đã thống nhất
    - mốc bắt đầu đo đã thống nhất
```

Điều kiện kết thúc có thể bao gồm đăng nhập đúng quyền, ứng dụng dùng được secret, kiểm tra quyền từ chối đạt và audit hoạt động. Nếu runbook yêu cầu những điều đó, không dừng đồng hồ ngay khi tiến trình vault khởi động.

Một timeline ví dụ với mục tiêu 90 phút:

| Khoảng từ lúc công bố sự cố | Công việc | Thời lượng |
|---|---|---:|
| Phút 0–8 | Tiếp nhận sự cố và phê duyệt phục hồi | 8 phút |
| Phút 8–20 | Chuẩn bị hạ tầng và kiểm tra cô lập | 12 phút |
| Phút 20–35 | Nạp dữ liệu phục hồi | 15 phút |
| Phút 35–42 | Khôi phục khả năng giải mã | 7 phút |
| Phút 42–50 | Đối soát quyền và trạng thái nhạy cảm | 8 phút |
| Phút 50–58 | Kiểm tra chức năng, quyền từ chối và audit | 8 phút |

Thời gian phục hồi quan sát là 58 phút trong phạm vi đã thử. Nếu môi trường hạ tầng thực tế mất thêm 45 phút để cấp phát nhưng lab dùng hạ tầng sẵn, cần báo cáo giới hạn này; không dùng số 58 phút để kết luận mọi tình huống đều đạt mục tiêu 90 phút.

Tách thời gian đợi người giữ khóa, lấy quyền kho backup, dựng hạ tầng và kiểm thử. Phân rã như vậy giúp biết cần cải thiện khâu nào thay vì chỉ tối ưu tốc độ nạp snapshot.

### 12.2. RPO: khoảng dữ liệu thực sự không phục hồi được

Recovery Point Objective — RPO là mục tiêu về mất dữ liệu theo thời gian. Để đo, cần biết điểm dữ liệu yêu cầu bảo vệ và điểm dữ liệu đã phục hồi được, dựa trên các ghi nhận hoặc mốc dữ liệu có thể xác minh.

Ví dụ quy ước đo của diễn tập lấy mốc ghi thành công cuối cùng cần bảo vệ:

```text
Ghi thành công cuối cùng cần bảo vệ:        08:59
Điểm ghi thành công cuối được phục hồi:    08:39
Khoảng mất dữ liệu quan sát:               20 phút
Mục tiêu cho phép:                         không quá 30 phút
```

Nếu tổ chức định nghĩa cửa sổ RPO tính đến thời điểm sự cố 09:00, phải dùng 09:00 làm mốc và báo 21 phút trong ví dụ này. Cần thống nhất định nghĩa trước diễn tập, ghi cả thời điểm sự cố và các mốc ghi dữ liệu, không chọn cách tính thuận lợi hơn sau khi biết kết quả.

Ngoài số phút, liệt kê các thay đổi bị thiếu: tạo secret, rotation, thu hồi quyền, cập nhật policy hoặc phiên bản credential. Hai bản phục hồi cùng mất 20 phút có thể có mức rủi ro khác nhau nếu một bản thiếu sự kiện thu hồi quyền quản trị.

Không tính RPO chỉ bằng tuổi tên file hoặc lịch cron backup. Phải xác minh dữ liệu cần bảo vệ thực sự có trong tập đã phục hồi.

## 13. Ví dụ đặc tả diễn tập và bộ điều phối giả lập

Ví dụ YAML dưới đây chỉ minh họa cách ghi hợp đồng kiểm thử, không phải cấu hình của một sản phẩm vault cụ thể:

```yaml
exercise:
  id: pam-vault-restore-lab-01
  scenario: loss_of_vault_cluster
  environment: isolated_lab
  data_class: synthetic
  production_traffic_allowed: false

recovery_set:
  backup_id: lab-backup-0042
  integrity_manifest_id: lab-manifest-0042
  source_version: lab-version-A
  restore_version: lab-version-A
  key_dependency_id: lab-key-service-01

targets:
  rto_minutes: 90
  rpo_minutes: 30
  rto_start: incident_declared
  rto_end: mandatory_service_checks_passed
  rpo_reference: last_required_acknowledged_write

controls:
  production_egress: deny
  target_rotation: synthetic_targets_only
  temporary_privilege: time_bound
  evidence_contains_secret_values: false

mandatory_checks:
  - restore_integrity
  - decrypt_synthetic_secret
  - allowed_reader_succeeds
  - unauthorized_reader_is_denied
  - revoked_subject_is_denied_after_reconciliation
  - synthetic_rotation_is_consistent
  - application_smoke_test
  - audit_success_and_denial_are_observable
  - production_egress_is_denied

stop_conditions:
  - production_endpoint_contacted
  - secret_value_exposed
  - untrusted_recovery_set
```

Bộ điều phối có thể kiểm soát thứ tự và thu bằng chứng, nhưng không nên tự động bỏ qua các cổng phê duyệt hoặc tìm credential thay thế khi gặp lỗi. Pseudocode minh họa:

```text
function exerciseRestore(plan):
    context = beginExercise(plan.id)
    startRecoveryTimer(context)

    require verifyIsolation(plan.environment)
    require verifyBackupProvenance(plan.recovery_set)
    require verifySupportedRestoreCombination(plan.recovery_set)

    restoreResult = restoreIntoIsolatedEnvironment(plan.recovery_set)
    require restoreResult.succeeded

    require unlockThroughApprovedKeyProcedure()
    require verifyRecoveryMarkers()
    require reconcileRevocationsAndCredentialChanges()

    for check in plan.mandatory_checks:
        result = runAuthorizedSyntheticCheck(check)
        recordRedactedEvidence(context, check, result)

        if result.matchesStopCondition:
            containRestoredEnvironment()
            finalizeAsFailed(context)
            return

        require result.passed

    stopRecoveryTimer(context)
    require observedDataLossWithinObjective(plan.targets)
    require observedRecoveryTimeWithinObjective(plan.targets)

    finalizeAsPassedWithinDeclaredScope(context)
    endTemporaryPrivileges()
```

Trong triển khai thật, nhánh lỗi cũng phải kết thúc quyền tạm thời và giữ môi trường ở trạng thái kiểm soát được. Cần có xử lý tương đương khối “finally” cho việc thu hồi quyền, kết thúc phiên, niêm phong bằng chứng và thông báo kết quả; không chỉ thực hiện cleanup trên nhánh thành công.

Không đưa khóa giải mã, token bootstrap hoặc giá trị secret vào đặc tả này. Các ID chỉ tham chiếu đến nguồn và quy trình kiểm soát riêng.

## 14. Thu thập bằng chứng phục vụ kiểm toán và ứng phó sự cố

Hồ sơ diễn tập cần cho phép người không trực tiếp thao tác trả lời: đã thử cái gì, với đầu vào nào, ai làm, quyền nào được sử dụng và kết quả có thể kiểm chứng ở đâu.

Một bộ hồ sơ tối thiểu gồm:

- Mã diễn tập, phạm vi, người thực hiện và người phê duyệt.
- Backup/manifest được chọn, nguồn gốc và kết quả kiểm tra toàn vẹn.
- Phiên bản phần mềm, mô hình hạ tầng và các thành phần thay thế trong lab.
- Timeline có múi giờ thống nhất và định nghĩa RTO/RPO.
- Kết quả từng ca kiểm thử bắt buộc kèm mã bằng chứng.
- Danh sách sai lệch về dữ liệu, credential, thu hồi quyền và tích hợp.
- Kết quả audit của thao tác phục hồi, truy cập thành công và truy cập bị từ chối.
- Kết luận đạt/không đạt, giới hạn phạm vi và việc cần khắc phục.
- Bằng chứng thu hồi quyền tạm thời và xử lý bản sao nhạy cảm khi kết thúc.

Có thể dùng bảng kết quả:

| Check ID | Expected | Actual | Result | Evidence ID |
|---|---|---|---|---|
| VR-03 | Reader tổng hợp đọc được Secret A | Thành công trong phạm vi cho phép | PASS | EV-103 |
| VR-04 | Reader khác kho bị từ chối | Bị từ chối; không trả payload | PASS | EV-104 |
| VR-08 | Rotation nhất quán ở đích tổng hợp | Vault cập nhật nhưng đích từ chối giá trị mới | FAIL | EV-108 |
| VR-10 | Có sự kiện thành công và từ chối | Đã tìm được cả hai theo ID diễn tập | PASS | EV-110 |

Trong ví dụ này, kết quả toàn diễn tập không được ghi đạt nếu VR-08 là ca bắt buộc. Không lấy tỷ lệ phần trăm cao để che một lỗi ở khả năng phục vụ credential đặc quyền.

Log lịch sử của vault sản xuất cần được giữ theo cơ chế bằng chứng của tổ chức. Nếu backup khôi phục đưa theo một phần lịch sử cũ, không coi bản sao đó là bản thay thế đầy đủ cho kho audit độc lập. Gắn nhãn rõ sự kiện diễn tập để người điều tra không nhầm chúng với hoạt động thật.

## 15. Phân tích lỗi và sửa runbook sau diễn tập

Sau khi ghi nhận kết quả, phân biệt lỗi kỹ thuật của công cụ, lỗi phụ thuộc và thiếu sót của quy trình. Ví dụ:

| Quan sát | Nguyên nhân có thể kiểm tra | Hướng cải thiện runbook |
|---|---|---|
| Backup nạp được nhưng không mở khóa | Thiếu quyền KMS/HSM, sai khóa hoặc sai ràng buộc danh tính | Ghi rõ phụ thuộc khóa và cách cấp quyền phục hồi |
| Mất nhiều thời gian chờ người giữ khóa | Lịch trực và cơ chế liên hệ không đủ | Diễn tập luân phiên, kiểm tra người thay thế |
| Secret đúng nhưng ứng dụng thất bại | Đường dẫn, vai trò, TLS hoặc cache chưa đúng | Bổ sung kiểm tra từ phía bên sử dụng |
| Tài khoản bị khóa sau thử credential | Thử lặp giá trị cũ hoặc không kiểm soát retry | Giới hạn số lần thử và xác minh trước rotation |
| Người đã thu hồi có quyền trở lại | Chính sách trong backup cũ chưa được đối soát | Thêm cổng áp dụng trạng thái thu hồi hiện hành |
| Vault khỏe nhưng thiếu audit | Cấu hình audit ngoài backup hoặc endpoint sai | Bổ sung phục hồi cấu hình và kiểm tra event đầu cuối |
| Kết quả RTO tốt nhưng không lặp lại được | Dùng hạ tầng có sẵn hoặc quyền admin cá nhân | Ghi rõ giả định, thử lại bằng quyền và quy trình thực tế |

Mỗi phát hiện cần có mức ảnh hưởng, người phụ trách, hạn xử lý và ca kiểm thử lại. Khi một lỗi làm ca bắt buộc không đạt, sau khi sửa cần chạy lại đủ phần bị ảnh hưởng; không đổi kết quả cũ thành PASS chỉ vì đã sửa tài liệu.

Các thay đổi về khóa, backend, phiên bản vault, mô hình mạng, IdP, connector và quy mô dữ liệu là lý do xem xét diễn tập lại. Tần suất cần phù hợp mức quan trọng của dịch vụ và tốc độ thay đổi, không chỉ dựa vào lịch cố định.

## 16. Bài thực hành: chứng minh phục hồi không hồi sinh quyền cũ

### Bối cảnh

Một vault lab quản lý hai credential tổng hợp và một kho secret cho ứng dụng. Có ba danh tính thử nghiệm: quản trị viên diễn tập, ứng dụng và người đọc giới hạn. Môi trường chỉ kết nối đến IdP, máy đích và bộ thu audit của lab.

### Thực hiện

1. Tạo các secret tổng hợp cùng dữ liệu mốc và ghi trạng thái quyền.
2. Tạo backup bằng cơ chế được hỗ trợ; lưu ID backup và điểm nhất quán.
3. Sau backup, luân chuyển một credential ở máy đích lab và thu hồi quyền của người đọc giới hạn.
4. Khôi phục backup vào một môi trường lab khác đã cô lập.
5. Trước khi mở luồng người dùng, nhận diện hai thay đổi sau backup và áp dụng quy trình đối soát.
6. Kiểm tra quản trị viên chỉ có quyền được phê duyệt; ứng dụng chỉ lấy được secret của nó.
7. Kiểm tra người đọc đã thu hồi bị từ chối và sự kiện từ chối được ghi audit.
8. Kiểm tra credential đã luân chuyển được xử lý nhất quán với máy đích lab, theo runbook.
9. Đo thời gian và khoảng dữ liệu mất; kết thúc quyền tạm thời và xử lý môi trường diễn tập.

### Sản phẩm cần nộp

Nộp hợp đồng diễn tập, ma trận kết quả, timeline, đối chiếu dữ liệu mốc và báo cáo sai lệch đã che dữ liệu nhạy cảm. Không nộp giá trị secret, vật liệu khóa hoặc token.

Kết quả chỉ đạt khi có bằng chứng cho cả chức năng được phép và truy cập phải bị chặn. Nếu chỉ đăng nhập thành công và đọc được một secret, bài thực hành chưa chứng minh được khôi phục vault an toàn.

### Câu hỏi tự kiểm tra

1. Vì sao checksum đúng chưa đủ chứng minh một tập backup phục hồi được?
2. Nếu vault phục hồi chứa mật khẩu cũ nhưng máy đích đang dùng mật khẩu mới, lỗi nằm ở đâu và cần đối soát gì?
3. Vì sao phải chặn connector trước khi khởi động đầy đủ môi trường phục hồi?
4. Có nên dùng thời điểm tiến trình chạy để kết thúc đo RTO không?
5. Làm sao biết người bị thu hồi quyền sau backup không được cấp lại quyền?
6. Nếu diễn tập dùng IdP giả lập, kết luận nào vẫn cần kiểm chứng với tích hợp thật?

Đáp án định hướng: phải kiểm chứng toàn bộ chuỗi phụ thuộc và trạng thái nghiệp vụ; phân biệt snapshot quá khứ với hệ thống đích hiện tại; cô lập trước các tác vụ có tác động; đo đến điều kiện dịch vụ đã thống nhất; đối soát thu hồi từ nguồn hiện hành; và giữ đúng giới hạn kết luận của từng thành phần được mô phỏng.

## 17. Những điều cần nhớ khi đánh giá một lần restore

Một phép thử vault restore có giá trị khi nó chứng minh được khả năng phục vụ các thao tác PAM cần thiết và duy trì các điều kiện kiểm soát quyền. Nạp lại dữ liệu chỉ là một cổng trong chuỗi đó.

Điểm dữ liệu phục hồi, khóa giải mã, quyền truy cập, trạng thái credential ở đích và audit phải được xem cùng nhau. Một bản backup tốt vẫn có thể cần quy trình đối soát để trở thành một dịch vụ có thể sử dụng an toàn.

Kết luận cuối cùng phải bám vào phạm vi và bằng chứng đã thử: mất bao nhiêu dữ liệu, mất bao lâu, ai có thể làm gì sau phục hồi, những truy cập nào bị chặn và những giới hạn nào còn chưa được kiểm chứng.
