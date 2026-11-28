# Khóa privileged account bị chiếm

## 1. Mục tiêu và tình huống xuất phát

Một tài khoản đặc quyền bị chiếm không chỉ là một mật khẩu bị lộ. Người tấn công có thể đang giữ phiên quản trị, token API, khóa SSH hoặc quyền truy cập vào kho bí mật. Khóa tài khoản là biện pháp ngăn việc sử dụng tiếp một danh tính có rủi ro; để cô lập sự cố, đội ứng phó còn phải xử lý những quyền và phiên đã được cấp trước đó.

Bài học này tập trung vào hành động khóa tài khoản trong quy trình ứng phó sự cố PAM, từ khi nhận tín hiệu đáng tin cậy đến khi quyết định giữ khóa, thay thế hoặc mở lại có kiểm soát. Sau bài học, người học có thể:

- Xác định chính xác danh tính cần khóa và phân biệt tài khoản người dùng với tài khoản dịch vụ.
- Chọn biện pháp cô lập phù hợp với mức độ nguy hiểm và ảnh hưởng vận hành.
- Phân biệt khóa đăng nhập, thu hồi phiên, vô hiệu hóa credential và thu hồi quyền JIT.
- Tổ chức thực hiện bằng một đường quản trị sạch, có người chịu trách nhiệm và bằng chứng.
- Kiểm tra hiệu lực ở hệ thống đích thay vì chỉ dựa vào thông báo thành công từ PAM.
- Xác định điều kiện khôi phục quyền đặc biệt sau khi đã kiểm soát nguyên nhân bị chiếm.

Xét tình huống: SOC phát hiện tài khoản quản trị `ops-an` truy cập máy chủ cơ sở dữ liệu sản xuất từ một thiết bị chưa từng thấy, sau đó xuất hiện thao tác cấp thêm quyền. Tài khoản này được quản lý qua PAM, nhưng cơ sở dữ liệu vẫn có đường đăng nhập trực tiếp. Nếu đội trực chỉ khóa quyền checkout trong vault, phiên đang mở và đường đăng nhập trực tiếp có thể vẫn hoạt động.

Câu hỏi cần trả lời không phải chỉ là “đã bấm Disable chưa”, mà là: **danh tính này còn thực hiện được hành động đặc quyền nào, qua đường nào, và bằng chứng nào xác nhận đã chặn được?**

## 2. Phân biệt các hành động thường bị gọi chung là “khóa”

### 2.1. Khóa đăng nhập khác với chấm dứt quyền đang tồn tại

| Hành động | Mục đích chính | Điều chưa thể mặc định đã giải quyết |
| --- | --- | --- |
| Vô hiệu hóa tài khoản tại nguồn danh tính | Ngăn xác thực mới theo cơ chế của hệ thống đó | Phiên cũ, token còn hiệu lực, danh tính khác đã được tạo |
| Chặn cấp quyền hoặc checkout tại PAM | Ngăn lấy bí mật hay nhận quyền quản trị mới qua PAM | Credential đã lấy trước đó và truy cập trực tiếp vào đích |
| Thu hồi grant JIT/JEA | Gỡ quyền tạm thời hoặc quyền thực thi đã cấp | Phiên đã có đặc quyền, credential tồn tại ngoài grant |
| Chấm dứt phiên quản trị | Dừng kết nối hoặc ngữ cảnh thực thi được xác định | Tác vụ chạy nền, kết nối khác, lần đăng nhập mới |
| Vô hiệu hóa credential | Ngăn tiếp tục sử dụng một khóa, mật khẩu hoặc chứng thư cụ thể | Các credential khác của cùng tài khoản, phiên được tạo trước đó |
| Xoay vòng bí mật | Thay bí mật cũ bằng giá trị mới | Khả năng kẻ tấn công đọc lại bí mật mới từ máy bị chiếm |
| Cô lập thiết bị hoặc workload | Hạn chế nguồn tấn công và đường di chuyển | Danh tính đang bị dùng từ một thiết bị khác |
| Thu hồi quyền tại tài nguyên đích | Ngăn hành động quản trị tại tài nguyên | Các tài nguyên khác và quyền được cấp theo đường khác |

Các hành động này bổ sung cho nhau. Một kế hoạch cô lập thường cần nhiều hành động, nhưng không nên áp dụng cùng một thao tác hàng loạt cho mọi loại danh tính.

### 2.2. Trạng thái khóa do ứng phó khác với account lockout

Account lockout thường là trạng thái tự động khi có quá nhiều lần xác thực thất bại. Trạng thái đó có thể tự hết hạn hoặc được mở khóa theo quy trình hỗ trợ thông thường. Trong sự cố bị chiếm tài khoản, đội ứng phó cần một trạng thái vô hiệu hóa có chủ đích, gắn với mã sự cố và chỉ được mở theo quyết định của người có thẩm quyền.

Không tạo lockout bằng cách cố tình nhập sai mật khẩu. Cách này khó kiểm soát, có thể kích hoạt cơ chế tự mở khóa và làm lẫn dấu vết điều tra. Cũng không xem việc xóa tài khoản ngay lập tức là phương án mặc định: xóa có thể làm mất quan hệ nhận diện, gây đứt phụ thuộc và làm khó việc truy nguyên quyền.

### 2.3. Tài khoản bị chiếm không đồng nghĩa mọi hành động đều bất hợp pháp

Một tài khoản có thể đồng thời được người quản trị thật và kẻ tấn công sử dụng. Vì vậy:

- Gắn kết luận với từng phiên, thiết bị, credential và thời điểm.
- Giữ bản ghi chủ sở hữu hợp pháp, người sử dụng được cấp phép và lịch cấp quyền.
- Không dùng tên hiển thị làm định danh duy nhất; ưu tiên ID ổn định của tài khoản và nguồn danh tính.
- Không đồng nhất danh tính đăng nhập với danh tính hiệu lực: một phiên có thể đã chuyển sang vai trò hoặc tài khoản khác.

Mục tiêu trước mắt là ngăn gây hại tiếp diễn. Kết luận ai thực hiện hành động nào cần dựa vào bằng chứng sau khi đã ổn định tình hình.

## 3. Xác định phạm vi trước khi khóa

### 3.1. Lập bản đồ danh tính tối thiểu

Trong vài phút đầu, người trực cần tập hợp đủ thông tin để tránh khóa nhầm hoặc khóa thiếu:

| Nhóm thông tin | Nội dung cần biết |
| --- | --- |
| Danh tính | ID ổn định, nguồn quản lý, tên tài khoản, tài khoản cục bộ hay tập trung |
| Loại tài khoản | Cá nhân, dùng chung, dịch vụ, workload, khẩn cấp hoặc quản trị PAM |
| Quyền | Nhóm quản trị, vai trò cloud, grant JIT, quyền sudo, quyền cơ sở dữ liệu |
| Credential | Mật khẩu, SSH key, API key, chứng thư, token, phương thức MFA |
| Truy cập hiện có | Phiên PAM, phiên trực tiếp, phiên federation, tác vụ chạy nền |
| Phụ thuộc | Dịch vụ sử dụng, chủ sở hữu, hệ thống quan trọng, đường khôi phục |
| Dấu hiệu bị chiếm | Cảnh báo, thời gian, nguồn truy cập, thao tác nguy hiểm, độ tin cậy |
| Khả năng thay thế | Tài khoản sạch, kênh quản trị ngoài băng, quyền khẩn cấp đã kiểm tra |

Đây là tập thông tin phục vụ quyết định, không phải điều kiện buộc phải hoàn thiện mọi trường mới được hành động. Nếu đang xảy ra phá hoại dữ liệu, đội ứng phó cần chặn hành động gây hại ngay theo thẩm quyền khẩn cấp, đồng thời ghi nhận những thông tin chưa biết.

### 3.2. Nhìn theo chuỗi quyền thay vì một username

Một chuỗi điển hình có thể là:

```text
Danh tính quản trị tại IdP
  -> yêu cầu JIT
  -> nhận quyền trên PAM
  -> checkout tài khoản đích
  -> mở phiên vào máy chủ
  -> chuyển sang root hoặc vai trò quản trị cơ sở dữ liệu
```

Khóa danh tính ở đầu chuỗi không tự động chứng minh các quyền ở cuối chuỗi đã mất. Ngược lại, khóa tài khoản đích mà để danh tính IdP bị chiếm hoạt động có thể cho phép người tấn công xin quyền vào tài nguyên khác.

Nếu tài khoản bị chiếm đã tạo thêm API key, tài khoản quản trị mới hoặc cơ chế truy cập khác, đó là phạm vi phải điều tra và cô lập tiếp. Không kết thúc sự cố ở một username chỉ vì username đó đã bị vô hiệu hóa.

### 3.3. Xác minh tín hiệu và xác định mức khẩn cấp

Một lần đăng nhập ngoài giờ chưa đủ để khẳng định tài khoản bị chiếm. Có thể đối chiếu lịch trực, thay đổi đã phê duyệt, nguồn thiết bị, yếu tố xác thực và hành vi sau đăng nhập. Tuy nhiên, các tín hiệu như tạo quản trị viên trái phép, vô hiệu hóa ghi log hoặc truy cập bí mật vượt nhiệm vụ cần được xử lý theo mức nguy hiểm tương ứng.

Liên hệ chủ tài khoản qua kênh tin cậy độc lập nếu cần xác minh. Tránh gửi yêu cầu xác nhận chỉ qua hộp thư hoặc phiên chat có thể đã nằm trong phạm vi bị chiếm. Không yêu cầu người dùng gửi mật khẩu, token hay mã MFA để “xác minh”.

## 4. Chọn cách cô lập theo rủi ro thực tế

### 4.1. Cân bằng tác hại an ninh và tác hại vận hành

| Tình huống | Ưu tiên cô lập | Điểm phải kiểm soát |
| --- | --- | --- |
| Tài khoản quản trị cá nhân có phiên trái phép đang hoạt động | Chặn quyền mới, kết thúc phiên nguy hiểm và vô hiệu hóa tài khoản theo kế hoạch | Người trực còn đường quản trị sạch để xử lý tiếp |
| Tài khoản dịch vụ nghi bị lộ nhưng chưa thấy hoạt động gây hại | Hạn chế đường truy cập, chuẩn bị danh tính thay thế, vô hiệu hóa bí mật cũ theo trình tự | Phụ thuộc và khả năng triển khai credential mới |
| Tài khoản dịch vụ đang bị dùng để phá hoại | Cô lập tức thời phạm vi gây hại, kể cả cần tạm dừng dịch vụ theo quyết định khẩn cấp | Người chỉ huy sự cố ghi nhận ảnh hưởng và phương án duy trì dịch vụ |
| Tài khoản quản trị PAM hoặc IdP bị chiếm | Bảo vệ mặt phẳng điều khiển và dùng kênh quản trị độc lập đã kiểm chứng | Không dựa toàn bộ vào hệ thống có thể đã mất độ tin cậy |
| Tài khoản break-glass bị lộ | Vô hiệu hóa credential bị lộ, kích hoạt đường khẩn cấp thay thế được kiểm soát | Tránh mất toàn bộ quyền quản trị dự phòng |
| Tài khoản dùng chung bị chiếm | Chặn credential và phiên liên quan, xác định các người dùng và tác vụ phụ thuộc | Không coi việc người dùng hợp pháp vẫn truy cập được là bằng chứng an toàn |

Không có thứ tự duy nhất đúng cho mọi tình huống. Nếu phiên đang xóa dữ liệu, chấm dứt phiên hoặc cô lập mạng có thể phải làm trước khi thu thập đủ hồ sơ. Nếu là một dịch vụ sống còn và chưa có hoạt động phá hoại, có thể cần chuẩn bị danh tính thay thế trước khi khóa hoàn toàn.

Điều cần tránh là trì hoãn vô thời hạn vì “sợ ảnh hưởng production”. Mọi quyết định chờ phải có người chịu trách nhiệm, biện pháp giảm rủi ro trong lúc chờ, điều kiện buộc phải hành động và thời điểm xem lại.

### 4.2. Kiểm tra đường khôi phục trước khi thao tác

Đội ứng phó cần xác nhận một danh tính quản trị sạch đủ quyền thực hiện các hành động cần thiết. Danh tính sạch phải được dùng từ thiết bị và kênh phù hợp, không chỉ là một tài khoản khác trên chính máy nghi bị chiếm.

Với tài nguyên trọng yếu, xác định trước:

- Người nào có quyền thực hiện và ai quyết định ảnh hưởng đến dịch vụ.
- Có thể quản trị đích qua kênh nào khi tài khoản chính bị khóa.
- Ai giữ quyền truy cập khẩn cấp và cách kiểm soát việc sử dụng.
- Điều kiện quay lại phương án dự phòng nếu tác vụ cô lập không thực hiện được.

Phương án dự phòng không đồng nghĩa mở lại tài khoản bị chiếm. Có thể cần chuyển dịch vụ sang instance khác, dùng danh tính thay thế hoặc tạm ngừng một chức năng để giữ an toàn cho phần còn lại.

## 5. Quy trình khóa tài khoản đặc quyền bị chiếm

### Bước 1 — Mở sự cố và chỉ định người điều phối

Tạo mã sự cố, ghi thời điểm phát hiện cùng múi giờ, nguồn cảnh báo, phạm vi ban đầu và người chỉ huy. Chỉ định người thao tác danh tính, người thao tác hệ thống đích, người theo dõi dịch vụ và người giữ bằng chứng. Trong nhóm nhỏ, một người có thể kiêm vai trò nhưng vẫn phải ghi rõ ai quyết định và ai thực hiện.

Gắn thay đổi khẩn cấp với mã sự cố để bộ phận hỗ trợ không tự mở khóa tài khoản theo một ticket mật khẩu thông thường. Quy trình hỗ trợ cần nhận biết trạng thái đang bị giữ vì sự cố an ninh.

### Bước 2 — Bảo toàn bằng chứng cần thiết, không trì hoãn chặn nguy hiểm

Thu nhận những bằng chứng có thể mất khi khóa hoặc kết thúc phiên: ID phiên, thời gian tạo, người yêu cầu, vai trò hiệu lực, nguồn thiết bị và log lệnh liên quan nếu có. Ghi tình trạng bản ghi phiên PAM trước khi chấm dứt.

Lưu bằng chứng vào nơi hạn chế truy cập, giữ thông tin nguồn và thời điểm thu thập. Nếu xuất file, có thể tính mã băm để kiểm tra tính toàn vẹn về sau. Mã băm không tự chứng minh nguồn đáng tin cậy hay thay thế lịch sử ai thu nhận và ai truy cập.

Không sao chép bí mật thô vào ticket, bảng chat hoặc ảnh chụp màn hình. Định danh credential bằng ID hoặc dấu vân tay không nhạy cảm khi cơ chế đó phù hợp.

Khi có hành động phá hoại đang diễn ra, ưu tiên cô lập; ghi lại bằng chứng nào chưa thể thu nhận và lý do. Không giữ phiên nguy hiểm hoạt động chỉ để hoàn thiện hồ sơ.

### Bước 3 — Ngăn phát sinh quyền mới

Tùy kiến trúc, thực hiện các biện pháp phù hợp:

- Vô hiệu hóa hoặc chặn đăng nhập cho danh tính gốc bị chiếm.
- Tạm dừng quyền yêu cầu, phê duyệt và nhận grant JIT của danh tính đó.
- Thu hồi grant chưa hết hạn tại nơi thực thi quyền.
- Chặn checkout và quyền đọc bí mật liên quan trong PAM.
- Hủy yêu cầu truy cập đang chờ mà kẻ tấn công có thể tận dụng.
- Chặn đường truy cập trực tiếp nếu nó bỏ qua lớp PAM được dùng để cô lập.

Đặc biệt kiểm tra khả năng tự phê duyệt, thay đổi policy hoặc nhận quyền qua nhóm khác. Một lệnh chặn chỉ áp dụng cho giao diện người dùng có thể không bao phủ API, agent và federation.

Ghi nhận kết quả từng biện pháp riêng. “Đã chặn tại PAM” và “đã chặn tại hệ thống đích” là hai bằng chứng khác nhau.

### Bước 4 — Xử lý phiên và quyền đã cấp

Liệt kê phiên trong PAM đồng thời đối chiếu nguồn độc lập ở đích, IdP, cloud hoặc cơ sở dữ liệu. Cần phân biệt:

- Phiên được PAM proxy và có thể kết thúc qua PAM.
- Phiên trực tiếp không đi qua proxy.
- Phiên đã chuyển quyền sang danh tính khác.
- Kết nối ứng dụng hoặc connection pool còn giữ ngữ cảnh xác thực.
- Tác vụ chạy nền đã được tạo từ phiên cũ.

Kết thúc những phiên thuộc phạm vi cần cô lập và xác minh ở đích. Nếu PAM báo kết thúc nhưng trên máy đích vẫn còn phiên hoặc tác vụ có đặc quyền, cần xử lý phần tồn tại đó bằng cơ chế phù hợp của đích.

Không mặc định “thu hồi phiên” đồng nghĩa dừng mọi tiến trình. Cũng không xóa mọi tiến trình của một tài khoản dịch vụ mà chưa đánh giá dữ liệu đang xử lý, cơ chế failover và ảnh hưởng tính nhất quán.

### Bước 5 — Vô hiệu hóa credential và cơ chế duy trì truy cập

Kiểm kê credential đã biết của tài khoản, không chỉ bí mật được quản lý trong vault. Với mỗi loại, xác định hành động vô hiệu hóa thực tế:

| Loại | Hành động cần xem xét | Điều cần xác minh thêm |
| --- | --- | --- |
| Mật khẩu | Reset hoặc xoay vòng tại nguồn có thẩm quyền | Bản sao tại đích, phụ thuộc, phiên cũ và quyền đọc lại từ vault |
| SSH key | Gỡ quyền chấp nhận khóa bị lộ tại các đích liên quan | Khóa khác, chứng thư SSH, phiên đang mở và đường phân phối cấu hình |
| API key | Vô hiệu hóa key bị lộ, kiểm kê key còn lại | Token tạm đã được phát hành từ key và các tài nguyên bị truy cập |
| Refresh token | Thu hồi theo cơ chế của hệ thống phát hành | Access token đã phát hành và phiên ứng dụng riêng |
| Chứng thư | Thu hồi hoặc chặn chấp nhận theo cơ chế của hệ thống | Thành phần xác minh có kiểm tra thu hồi hay không |
| Phương thức MFA | Loại bỏ hoặc tạm vô hiệu phương thức không còn tin cậy | Người tấn công có thêm phương thức mới hoặc mã khôi phục hay không |
| Bí mật ứng dụng | Cấp giá trị mới cho thành phần sạch và vô hiệu hóa giá trị cũ | Tất cả consumer đã chuyển và môi trường cũ không đọc được giá trị mới |

Nếu chưa biết toàn bộ credential, ghi rõ phần chưa bao phủ và áp dụng lớp chặn tại tài nguyên hoặc mạng trong lúc kiểm kê tiếp. Không tuyên bố cô lập hoàn toàn bằng cách suy diễn danh sách credential trong vault là toàn bộ danh sách có thật.

### Bước 6 — Kiểm tra cơ chế tái cấp quyền và phạm vi lan rộng

Một tài khoản có thể được hệ thống quản lý danh tính đồng bộ lại, một automation có thể thêm lại nhóm, hoặc một tác vụ triển khai có thể phân phối lại khóa cũ. Vì vậy, cần tìm nguồn có thẩm quyền thay vì chỉ sửa bản sao cục bộ.

Kiểm tra các thay đổi trong khoảng thời gian nghi bị chiếm:

- Tài khoản, nhóm hoặc vai trò quản trị được thêm mới.
- Credential, phương thức MFA hoặc ứng dụng được đăng ký thêm.
- Policy cấp quyền và luật phê duyệt bị sửa.
- Tác vụ định kỳ, dịch vụ hoặc cơ chế tự động hóa được tạo.
- Cấu hình ghi log, ghi phiên hoặc cảnh báo bị giảm.
- Quyền truy cập kho bí mật và đường đồng bộ credential bị thay đổi.

Những dấu hiệu này mở rộng phạm vi xử lý. Khóa tài khoản ban đầu không thay thế việc xóa bỏ đường truy cập trái phép sau khi đã thu nhận bằng chứng cần thiết.

### Bước 7 — Xác minh hiệu lực và theo dõi sau khóa

Dùng nguồn quan sát độc lập để trả lời từng câu hỏi:

1. Trạng thái vô hiệu hóa đã xuất hiện tại nguồn danh tính và các điểm thực thi cần thiết chưa?
2. Yêu cầu quyền mới của danh tính đó có bị từ chối theo chính sách sự cố không?
3. Credential bị vô hiệu hóa còn dùng được qua đường truy cập nào đã biết không?
4. Phiên cũ và quyền tại đích đã được thu hồi đến đâu?
5. Có hành động đặc quyền nào tiếp tục xuất hiện sau thời điểm cô lập không?
6. Dịch vụ hợp pháp còn hoạt động theo tiêu chí đã đặt ra không?

Kiểm thử phải có phạm vi rõ ràng, được cho phép và không phát tán bí mật. Có thể dựa vào log từ chối, trạng thái credential, kiểm thử có kiểm soát hoặc bằng chứng của điểm thực thi. Không cần cố đăng nhập liên tục bằng credential nghi bị lộ để chứng minh trạng thái khóa.

Nếu hành vi tiếp diễn, điều tra phiên tồn tại, token chưa hết hiệu lực, danh tính thứ cấp, trễ đồng bộ hoặc nguồn phát hành vẫn bị chiếm. Tăng mức cô lập theo bằng chứng thay vì lặp lại thao tác Disable.

## 6. Những điểm khác nhau giữa các nền tảng

Phần này là hướng dẫn nhận diện phạm vi kiểm tra. Tác vụ cụ thể phải dùng runbook đã xác nhận cho nền tảng triển khai; không coi một tên nút hoặc một lệnh của hệ thống này là tương đương với hệ thống khác.

### 6.1. Windows và nguồn danh tính tập trung

Vô hiệu hóa tài khoản tại directory có thể ngăn các lần xác thực mới sau khi thay đổi có hiệu lực, nhưng không bảo đảm đóng ngay phiên đăng nhập tương tác, phiên từ xa hoặc kết nối đã xác thực. Ticket hoặc ngữ cảnh xác thực hiện có cần được đánh giá theo cơ chế và chính sách của môi trường.

Đội ứng phó cần kiểm tra sự lan truyền của thay đổi, các máy đích có thể truy cập, kết nối quản trị còn tồn tại và tác vụ dùng tài khoản đó. Một tài khoản quản trị domain bị chiếm cũng đặt ra câu hỏi liệu các thành phần danh tính hoặc credential khác đã bị tác động hay chưa.

Không khóa hàng loạt mọi tài khoản có tên giống nhau. Tài khoản cục bộ trên từng máy và tài khoản domain có thể là các danh tính khác nhau; cần xác định đúng nguồn và ID.

### 6.2. Linux và SSH

Khóa mật khẩu hoặc đổi shell không đủ để mặc định mọi phương thức SSH đều bị chặn. Kết quả phụ thuộc cấu hình xác thực, cơ chế quản lý tài khoản và cách máy chủ thực thi chính sách. Khóa công khai, chứng thư, đăng nhập qua danh tính tập trung và phiên cũ cần được kiểm tra riêng.

Một kết nối SSH đã xác thực có thể còn cung cấp các kênh đang mở. Việc gỡ khóa khỏi nơi chấp nhận khóa không tự đóng kết nối cũ. Sau khi chặn khóa, kiểm tra phiên, quyền sudo, tài khoản root được truy cập thông qua phiên và tác vụ đã chạy nền.

Nếu cấu hình khóa được một hệ thống khác phân phối, sửa đúng nguồn phân phối hoặc chặn việc tái cấp trong phạm vi sự cố. Sửa riêng một file tại đích có thể bị đồng bộ ghi lại sau đó.

### 6.3. Cloud, federation và token

Danh tính quản trị cloud có thể nhận quyền qua federation, role hoặc token tạm thời. Vô hiệu hóa danh tính đầu vào không tự chứng minh token đã phát hành mất hiệu lực tại mọi dịch vụ.

Đặc biệt, hệ thống xác minh access token tự chứa theo cách cục bộ có thể tiếp tục chấp nhận token đến khi hết hạn, trừ khi có cơ chế khác để từ chối. Thu hồi refresh token thường nhằm ngăn phát hành token tiếp; cần kiểm tra riêng khả năng vô hiệu access token và phiên tài nguyên.

Biện pháp bổ sung có thể nằm ở chính sách ủy quyền của tài nguyên, điều kiện truy cập, điểm trung gian hoặc mạng, tùy nền tảng. Không tự suy luận rằng một chính sách deny áp dụng cho mọi token và mọi dịch vụ; phải xác minh phạm vi thực thi.

### 6.4. Cơ sở dữ liệu và ứng dụng

Khóa tài khoản cơ sở dữ liệu có thể tác động khác nhau đến kết nối đã mở. Connection pool của ứng dụng có thể giữ kết nối trong thời gian dài. Đội ứng phó cần kiểm tra cơ chế kết thúc phiên, giao dịch đang chạy và cách ứng dụng nhận credential mới.

Với ứng dụng có phiên riêng, logout ở IdP không nhất thiết làm mất ngay phiên tại ứng dụng. Cần xác định nơi quản lý session, thời hạn và hành động thu hồi thực sự.

Nếu tài khoản dùng cho cả công việc quản trị tương tác và kết nối ứng dụng, sự cố cho thấy một phụ thuộc nguy hiểm. Trước mắt phải cô lập theo tình hình thực tế; sau đó tách danh tính và quyền để giảm ảnh hưởng của lần xử lý tiếp theo.

## 7. Xử lý riêng tài khoản dịch vụ

### 7.1. Vì sao khóa ngay có thể làm sự cố phức tạp hơn

Tài khoản dịch vụ có thể được nhiều consumer sử dụng: ứng dụng, tác vụ sao lưu, agent triển khai hoặc bộ giám sát. Khóa tài khoản ở nguồn có thể làm hỏng lần kết nối tiếp theo trong khi các kết nối cũ vẫn hoạt động, khiến ảnh hưởng xuất hiện rải rác và khó chẩn đoán.

Không lấy việc dịch vụ “vẫn xanh” ngay sau thao tác làm bằng chứng mọi thứ ổn định. Cần quan sát cả thời điểm làm mới token, khởi động lại instance và tái kết nối.

### 7.2. Trình tự thay thế có kiểm soát

Trong tình huống cho phép chuyển đổi trước khi khóa hoàn toàn, có thể tổ chức như sau:

1. Xác định chủ sở hữu dịch vụ và danh sách consumer thực tế từ cấu hình cùng log sử dụng.
2. Hạn chế quyền và đường mạng mà credential bị lộ có thể dùng trong thời gian chuyển đổi.
3. Tạo danh tính thay thế với quyền tối thiểu, có thời hạn nếu thích hợp.
4. Cấp bí mật mới cho consumer sạch qua kênh quản lý bí mật được kiểm soát.
5. Chuyển consumer, kiểm tra các thao tác nghiệp vụ thiết yếu và lần tái xác thực.
6. Vô hiệu hóa credential cũ, kết thúc các kết nối thuộc phạm vi cô lập.
7. Xác minh không còn consumer hợp pháp và hoạt động trái phép dùng danh tính cũ.
8. Giữ danh tính cũ ở trạng thái phục vụ điều tra theo chính sách lưu giữ, thay vì vội xóa.

Nếu môi trường không hỗ trợ chồng lấn credential, phải lập kế hoạch chuyển đổi phù hợp hoặc chấp nhận gián đoạn có điều phối. Không tự giả định luôn có hai key đồng thời hoặc có thể xoay mật khẩu mà không cần khởi động lại dịch vụ.

Nếu đang có hành động phá hoại hoặc nguy cơ rõ ràng vượt khả năng giảm thiểu, không dùng trình tự chuyển đổi dài để trì hoãn cô lập. Người chỉ huy quyết định phương án ngừng hoặc hạn chế dịch vụ trong phạm vi khẩn cấp.

### 7.3. Không đưa bí mật mới vào nơi chưa tin cậy

Giả sử workload đã bị kiểm soát. Đổi mật khẩu trong vault nhưng vẫn cho workload đó đọc bí mật mới có thể chỉ chuyển từ một credential bị lộ sang một credential mới cũng bị lộ.

Kế hoạch phải kết hợp xử lý môi trường chạy: cô lập, khôi phục từ nguồn tin cậy hoặc thay workload, kiểm tra quyền đọc vault và hạn chế bootstrap credential. Cần xác định điểm nào đã đủ tin cậy để nhận credential mới trước khi cấp phát.

## 8. Tài khoản quản trị PAM, IdP và break-glass

### 8.1. Khi mặt phẳng điều khiển cũng nằm trong phạm vi bị chiếm

Nếu tài khoản quản trị PAM bị chiếm, log và kết quả thao tác do PAM cung cấp có thể chưa đủ làm nguồn xác nhận duy nhất. Kẻ tấn công có thể có khả năng sửa policy, tạo người dùng, xuất bí mật hoặc thay đổi cấu hình ghi phiên tùy quyền đã nắm giữ.

Đội ứng phó cần dùng kênh quản trị độc lập đã được chuẩn bị và đối chiếu với bằng chứng ở đích hoặc nơi thu log riêng. Có thể phải giảm kết nối của thành phần PAM bị ảnh hưởng, bảo toàn dữ liệu và ngăn nó tiếp tục phân phối credential cho đến khi khôi phục được độ tin cậy.

Phạm vi xoay vòng không thể xác định chỉ từ tên tài khoản quản trị PAM: cần đánh giá nó có thể đọc, phê duyệt hoặc lấy những bí mật nào trong cửa sổ sự cố.

### 8.2. Tài khoản khẩn cấp bị chiếm

Tài khoản break-glass phải được xử lý như một danh tính đặc quyền có rủi ro cao. Không miễn khóa chỉ vì nó phục vụ tình huống khẩn cấp. Đồng thời, trước khi vô hiệu hóa đường cuối cùng, cần xác nhận đường thay thế sạch hoặc phương án truy cập ngoài băng phù hợp.

Sau khi dùng một credential khẩn cấp trong xử lý sự cố, tổ chức phải đánh giá việc thay bí mật, thu hồi phiên, ghi nhận người sử dụng và trả trạng thái về chế độ bảo quản bình thường. Việc có mặt nhiều người không thay thế bằng chứng kỹ thuật về hành động đã thực hiện.

## 9. Mẫu hồ sơ quyết định và bằng chứng

Mẫu dưới đây chỉ minh họa dữ liệu nghiệp vụ; đây không phải cấu hình cho một sản phẩm PAM và không chứa lệnh thực thi. Các ID đều là dữ liệu giả.

```yaml
incident:
  id: IR-DEMO-042
  state: CONTAINMENT_IN_PROGRESS
  detectedAt: "2026-11-27T09:10:00+07:00"
  commander: ir-lead-demo
  trigger: "Phiên quản trị ngoài lịch và thay đổi quyền chưa được phê duyệt"
identity:
  authority: corporate-directory-demo
  stableId: user-demo-7f31
  accountName: ops-an
  kind: HUMAN_PRIVILEGED
scope:
  knownTargets:
    - db-prod-demo-01
  credentialRefs:
    - vault-item-demo-221
  activeSessionRefs:
    - session-demo-908
decision:
  approvedAction: DISABLE_AND_REVOKE
  approvedBy: ir-lead-demo
  reason: "Nguy cơ thay đổi quyền trái phép đang tiếp diễn"
  operationalImpact: "Tạm dừng thao tác quản trị của một người dùng"
  cleanRecoveryPathRef: recovery-path-demo-03
actions:
  - type: BLOCK_NEW_ACCESS
    targetRef: user-demo-7f31
    result: CONFIRMED
    evidenceRef: evidence-demo-101
  - type: TERMINATE_SESSION
    targetRef: session-demo-908
    result: CONFIRMED_AT_TARGET
    evidenceRef: evidence-demo-102
  - type: INVALIDATE_CREDENTIAL
    targetRef: vault-item-demo-221
    result: IN_PROGRESS
verification:
  accountState: DISABLED
  knownActiveSessions: 0
  directAccessChecked: true
  downstreamTokens: UNKNOWN
  containmentConclusion: PARTIAL
next:
  owner: identity-responder-demo
  action: "Xác minh token và quyền đã được cấp trước thời điểm khóa"
```

Điểm đáng chú ý là `accountState: DISABLED` nhưng kết luận vẫn là `PARTIAL` do token chưa được kiểm chứng. Hồ sơ tốt thể hiện được khoảng trống; không biến “chưa biết” thành “đã an toàn”.

Với mỗi thao tác, nên lưu người thực hiện, thời gian bắt đầu và xác nhận, đích tác động, kết quả trả về, bằng chứng độc lập, lỗi và ảnh hưởng quan sát được. Tham chiếu bằng chứng nên trỏ tới nơi được bảo vệ; không đặt credential thô trong hồ sơ.

## 10. Ví dụ diễn tiến và cách kết luận

### 10.1. Ví dụ tài khoản cá nhân có đường truy cập trực tiếp

| Thời điểm minh họa | Quan sát hoặc hành động | Kết luận đúng tại thời điểm đó |
| --- | --- | --- |
| 09:10 | Cảnh báo thay đổi quyền trái phép từ tài khoản quản trị | Có sự kiện cần xử lý, phạm vi còn đang xác minh |
| 09:12 | Chỉ huy quyết định cô lập; xác nhận đường quản trị sạch | Có thẩm quyền và phương tiện thực hiện |
| 09:13 | Chặn đăng nhập và cấp JIT mới | Đã giảm khả năng tạo truy cập mới qua các điểm vừa chặn |
| 09:14 | PAM xác nhận đóng phiên proxy | Cần đối chiếu đích và tìm phiên trực tiếp |
| 09:16 | Đích vẫn có một phiên trực tiếp cùng danh tính | Cô lập chưa hoàn tất |
| 09:18 | Kết thúc phiên trực tiếp, thu hồi quyền tạm, vô hiệu hóa credential bị lộ | Các đường đã biết được xử lý, tiếp tục kiểm tra quyền thứ cấp |
| 09:22 | Chưa thấy hành động tiếp diễn; phát hiện một key được tạo trong cửa sổ sự cố | Phải mở rộng xử lý key, chưa đóng sự cố |
| 09:28 | Key bị vô hiệu hóa và kiểm tra hiệu lực đạt yêu cầu | Có thể ghi nhận cô lập phạm vi đã xác định, vẫn tiếp tục điều tra |

Các mốc thời gian này phục vụ bài tập, không phải SLA áp dụng chung. Thời gian xử lý và mức độ thu nhận bằng chứng phải phù hợp nguy hiểm thực tế.

### 10.2. Ví dụ tài khoản dịch vụ trong ứng dụng thanh toán

Một ứng dụng dùng tài khoản dịch vụ để gọi hệ thống đối soát. API key của tài khoản xuất hiện trong vị trí không được phép. Chưa có bằng chứng phá hoại, nhưng có truy cập từ nguồn lạ.

Nếu khóa toàn bộ tài khoản ngay, hoạt động đối soát có thể dừng. Nếu chỉ đổi key và giữ workload bị nghi nhiễm quyền đọc vault, key mới có thể bị lấy tiếp.

Phương án có thể gồm: chặn nguồn không hợp lệ ở điểm thực thi phù hợp, chuẩn bị một consumer sạch, cấp danh tính mới chỉ có quyền cần thiết, chuyển lưu lượng được kiểm soát, vô hiệu hóa key cũ và theo dõi cả lỗi nghiệp vụ lẫn dấu hiệu tiếp tục sử dụng key bị lộ. Biện pháp giới hạn nguồn chỉ là một lớp giảm thiểu; không biến key đã lộ thành bí mật an toàn trở lại.

Nếu sau đó xuất hiện hành vi xóa dữ liệu, tiêu chí quyết định thay đổi: đội ứng phó có thể cần chặn ngay quyền gây hại và chấp nhận gián đoạn theo thẩm quyền khẩn cấp.

## 11. Điều kiện giữ khóa, khôi phục và đóng phần cô lập

### 11.1. Khi nào tiếp tục giữ khóa

Giữ khóa nếu chưa xác định được môi trường sử dụng sạch, còn hoạt động trái phép, chưa kiểm soát được cơ chế cấp credential hoặc còn khoảng trống quan trọng trong thu hồi phiên. Nhu cầu công việc của chủ tài khoản không tự làm mất những điều kiện này.

Nếu người dùng hợp pháp cần tiếp tục công việc, cân nhắc danh tính thay thế có phạm vi và thời hạn ngắn, được giám sát, thay vì mở lại toàn bộ quyền cũ.

### 11.2. Mở lại tài khoản là một quyết định phục hồi riêng

Trước khi khôi phục, cần có bằng chứng phù hợp cho các điều kiện sau:

- Danh tính người sử dụng và quyền cần thiết đã được xác minh.
- Nguyên nhân bị chiếm đã được xử lý ở mức đủ để tái sử dụng danh tính.
- Credential cũ và phương thức xác thực không còn tin cậy đã được vô hiệu hóa.
- Thiết bị hoặc workload nhận quyền mới đạt yêu cầu tin cậy.
- Những quyền hoặc cơ chế truy cập trái phép đã được xử lý.
- Quyền khôi phục đã được rà lại theo least privilege, ưu tiên JIT/JEA khi phù hợp.
- Có người phê duyệt, thời điểm thực hiện và giám sát tăng cường sau khôi phục.

Không khôi phục nguyên trạng chỉ vì đã đổi mật khẩu. Nếu chưa thể chứng minh danh tính cũ an toàn hoặc việc giữ lại không phù hợp, tổ chức có thể chọn thay thế danh tính theo quy trình riêng.

### 11.3. Tiêu chí kết thúc phần cô lập

Phần cô lập có thể được ghi nhận đạt yêu cầu khi các đường truy cập trong phạm vi đã xác định bị chặn hoặc bị kiểm soát theo quyết định có thẩm quyền, bằng chứng hiệu lực đã được lưu và những rủi ro còn lại có người xử lý cùng thời điểm xem lại.

Điều đó không đồng nghĩa toàn bộ sự cố đã đóng. Điều tra nguồn gốc, đánh giá phạm vi dữ liệu, khôi phục hệ thống và cải tiến kiểm soát vẫn có thể tiếp tục.

Nếu còn một access token chưa vô hiệu hóa được, phải mô tả thời hạn, tài nguyên có thể truy cập và biện pháp hạn chế trong lúc chờ. Không ghi “cô lập hoàn toàn” khi một đường có khả năng gây hại vẫn chưa được xử lý.

## 12. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao không đủ hoặc gây hại | Cách sửa |
| --- | --- | --- |
| Chỉ khóa checkout trong vault | Bí mật đã lấy ra và truy cập trực tiếp có thể còn dùng được | Xử lý credential, phiên và điểm thực thi tại đích |
| Chỉ đổi mật khẩu | Token, key và phiên cũ có thể không bị ảnh hưởng | Kiểm kê từng loại credential cùng quyền đã cấp |
| Tin thông báo “session terminated” duy nhất từ PAM | Đích có thể còn kết nối hoặc tác vụ khác | Đối chiếu nguồn độc lập tại tài nguyên |
| Khóa sai tài khoản vì trùng tên | Tài khoản cục bộ và tập trung có thể khác nhau | Dùng ID ổn định và nguồn có thẩm quyền |
| Xóa tài khoản để xử lý nhanh | Mất quan hệ nhận diện và có thể làm đứt phụ thuộc | Ưu tiên vô hiệu hóa, bảo toàn định danh và bằng chứng |
| Cấp bí mật mới cho workload chưa sạch | Kẻ tấn công có thể đọc lại bí mật mới | Xử lý môi trường và quyền truy cập vault trước cấp phát |
| Mở khóa theo yêu cầu hỗ trợ thông thường | Có thể tái mở đường cho người tấn công | Gắn trạng thái giữ khóa với mã sự cố và thẩm quyền phục hồi |
| Chờ thu đủ log trong khi phá hoại đang diễn ra | Tăng tác hại và phạm vi sự cố | Cô lập ưu tiên, ghi phần bằng chứng chưa thu được |
| Tự mở lại khi credential mới gây lỗi dịch vụ | Đưa quyền bị chiếm hoạt động trở lại | Dùng phương án dự phòng sạch và quyết định của chỉ huy |
| Ghi mật khẩu mới vào ticket | Tạo thêm điểm lộ bí mật và người có quyền truy cập | Chỉ ghi ID tham chiếu, dùng kênh phân phối bí mật phù hợp |
| Xem không có log mới là bằng chứng chắc chắn | Pipeline log có thể trễ, mất hoặc bị sửa | Kiểm tra sức khỏe log và kết hợp trạng thái tại đích |
| Bỏ qua nguồn đồng bộ quyền | Nhóm hoặc credential cũ có thể được cấp lại | Chặn hoặc sửa nguồn có thẩm quyền trong phạm vi sự cố |

## 13. Bài tập tự kiểm tra

### Tình huống 1 — Đã disable nhưng thao tác vẫn tiếp diễn

SOC xác nhận tài khoản quản trị bị vô hiệu hóa tại IdP. Mười phút sau, log cơ sở dữ liệu vẫn có truy vấn thay đổi quyền dưới cùng tài khoản đích.

Hãy xác định ít nhất bốn giả thuyết và bằng chứng cần kiểm tra.

**Gợi ý phân tích:** Có thể còn kết nối cơ sở dữ liệu đã xác thực; phiên trực tiếp không thuộc PAM; credential đích khác với danh tính IdP; hoặc một dịch vụ dùng chung tài khoản đang tiếp tục chạy. Cũng cần kiểm tra độ trễ và mốc thời gian của log để không nhầm thời điểm sự kiện với thời điểm thu nhận. Với từng giả thuyết, tìm ID phiên, thời điểm xác thực, nguồn kết nối và nguồn cấp quyền tương ứng.

### Tình huống 2 — Tài khoản sao lưu bị lộ

Tài khoản sao lưu có quyền rộng trên nhiều hệ thống. Chủ dịch vụ đề nghị chờ hết cuối tuần mới đổi mật khẩu vì sợ lỗi tác vụ.

Hãy đề xuất cách quyết định mà vẫn kiểm soát nguy cơ.

**Gợi ý phân tích:** Xác định hành vi đang xảy ra, phạm vi quyền, thời điểm backup tiếp theo và phương án thay thế. Nếu cho phép chuyển đổi có kiểm soát, phải có giới hạn truy cập trong lúc chờ, chủ sở hữu từng consumer, thời hạn rõ và điều kiện chuyển sang cô lập ngay. Không chấp nhận thời điểm chờ chỉ dựa trên sự thuận tiện. Tránh coi bản sao lưu là an toàn nếu cùng danh tính có thể sửa hoặc xóa chúng.

### Tình huống 3 — Khóa key nhưng token còn hiệu lực

Một key quản trị cloud đã bị vô hiệu hóa. Đội ứng phó biết trước đó key được dùng để nhận quyền tạm.

Hãy giải thích vì sao chưa thể kết luận hoàn tất cô lập.

**Gợi ý phân tích:** Cần xác định token hoặc phiên tạm đã được phát hành, quyền thực tế, thời hạn và khả năng thu hồi tại dịch vụ đích. Nếu không thu hồi ngay được, phải kiểm soát quyền hoặc đường truy cập bằng cơ chế có hiệu lực với token đó và theo dõi đến khi hết rủi ro. Đồng thời kiểm tra các danh tính hoặc key mới được tạo trong cửa sổ sự cố.

### Tình huống 4 — Yêu cầu mở lại gấp

Người quản trị hợp pháp xác nhận đã đổi mật khẩu và muốn mở lại đầy đủ quyền để xử lý production. Máy làm việc của họ vẫn đang bị điều tra.

Hãy đưa ra phương án phục hồi tạm thời.

**Gợi ý phân tích:** Giữ trạng thái khóa của danh tính hoặc đường sử dụng chưa đáng tin cậy, bố trí thiết bị quản trị sạch và quyền thay thế tối thiểu có thời hạn. Ghi phê duyệt, theo dõi phiên và điều kiện thu hồi. Việc xác nhận của chủ tài khoản là một phần thông tin, chưa thay thế kiểm tra môi trường và credential.

## 14. Checklist vận hành ngắn

Trước khi ghi nhận hoàn tất hành động khóa, người điều phối cần trả lời được:

- Đã xác định đúng ID tài khoản, nguồn danh tính và các vai trò hiệu lực chưa?
- Đã có đường quản trị sạch cùng người quyết định ảnh hưởng vận hành chưa?
- Đã chặn cấp quyền mới qua IdP, PAM, JIT và đường trực tiếp thuộc phạm vi chưa?
- Đã xử lý phiên đang mở, credential và quyền đã cấp đến mức nào?
- Đã kiểm tra phụ thuộc dịch vụ và ngăn cấp lại credential bị lộ chưa?
- Đã xác minh bằng chứng tại điểm thực thi cùng nguồn quan sát độc lập chưa?
- Đã ghi rõ khoảng trống, người chịu trách nhiệm và điều kiện mở rộng cô lập chưa?
- Đã ngăn quy trình hỗ trợ thông thường tự mở lại tài khoản đang giữ vì sự cố chưa?
- Đã tách quyết định mở lại tài khoản khỏi việc hoàn tất thao tác Disable chưa?

Khóa tài khoản đặc quyền có hiệu quả khi nó làm mất khả năng tiếp tục gây hại trong phạm vi đã xác định, có bằng chứng kiểm chứng và có đường phục hồi được kiểm soát. Trạng thái khóa là điểm bắt đầu để kiểm tra quyền thực tế, không phải bằng chứng tự đủ về việc sự cố đã chấm dứt.
