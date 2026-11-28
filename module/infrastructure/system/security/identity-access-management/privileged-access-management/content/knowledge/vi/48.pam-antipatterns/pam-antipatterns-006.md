# Không ghi session

## 1. Khi kiểm soát truy cập dừng ở thời điểm đăng nhập

Một kỹ sư được phê duyệt truy cập máy chủ sản xuất để xử lý sự cố. Người đó xác thực bằng MFA, nhận quyền tạm thời và kết nối qua cổng PAM. Hai mươi phút sau, một cấu hình quan trọng bị thay đổi, nhưng không ai xác định được thao tác nào gây ra thay đổi đó.

Nhật ký PAM chỉ cho biết ai được cấp quyền, tài khoản đích được dùng và thời điểm kết nối. Không có bản ghi phiên, không có nhật ký thao tác đủ chi tiết trên hệ thống đích, và tài khoản quản trị được nhiều người sử dụng qua những phiên khác nhau. Nhóm vận hành có bằng chứng về việc cho phép truy cập nhưng thiếu bằng chứng về những gì diễn ra sau đó.

Đó là anti-pattern **không ghi session** trong Privileged Access Management: cho phép hoạt động có đặc quyền diễn ra mà không có mức ghi nhận, đối soát và bảo vệ bằng chứng phù hợp với rủi ro.

“Session” trong bài này chủ yếu là phiên tương tác của con người, chẳng hạn terminal SSH, desktop quản trị từ xa hoặc giao diện quản trị ứng dụng. Với API và tác vụ dịch vụ, hình thức bằng chứng thường là audit event, danh tính workload và dấu vết thực thi thay vì video màn hình. Không nên ép mọi loại truy cập vào cùng một định dạng ghi hình.

Sau bài học, người học cần:

- Phân biệt log cấp quyền, log đăng nhập, bản ghi phiên và audit event tại hệ thống đích.
- Nhận ra những đường truy cập nằm ngoài cơ chế ghi nhận.
- Thiết kế chuỗi bằng chứng gắn được người thực hiện, quyền được cấp, phiên và kết quả thao tác.
- Quy định rõ cách xử lý khi recorder hoặc kho lưu trữ gặp lỗi.
- Kiểm tra bản ghi có thể tìm, đọc, bảo vệ và sử dụng trong điều tra.

## 2. Anti-pattern nằm ở đâu?

### 2.1. Không có bản ghi dù phiên có rủi ro cao

Trường hợp dễ thấy nhất là quyền quản trị sản xuất được cấp thường xuyên, nhưng hệ thống chỉ lưu sự kiện đăng nhập. Khi cần điều tra một lần sửa firewall, cập nhật cấu hình xác thực hay thay đổi dữ liệu, nhóm quản trị chỉ có danh sách người từng kết nối.

Đăng nhập thành công không chứng minh người đó đã thực hiện một thay đổi cụ thể. Ngược lại, thiếu bằng chứng cũng không chứng minh người đó vô can. Khoảng trống này làm yếu khả năng quy trách nhiệm và phục hồi sự cố.

### 2.2. Bật recorder nhưng không có bản ghi sử dụng được

Một cấu hình mang tên “recording enabled” chưa đủ. Anti-pattern vẫn tồn tại nếu:

- Recorder không hoạt động trên đúng giao thức hoặc đúng đường kết nối.
- Chỉ một phần phiên được ghi, nhưng phiên vẫn được báo là hoàn chỉnh.
- Tệp đã tạo nhưng thiếu đoạn cuối, không giải mã được hoặc không phát lại được.
- Không nối được bản ghi với danh tính cá nhân và tài khoản đích.
- Bản ghi bị xóa sớm, mất khóa giải mã hoặc không thể tìm theo mã phiên.
- Người được giám sát có thể tự xóa hoặc thay đổi bằng chứng.
- Đường truy cập trực tiếp vào đích vẫn được sử dụng mà không có kiểm soát tương ứng.

Ở đây, vấn đề không chỉ là tạo ra tệp. Hệ thống phải duy trì được một chuỗi bằng chứng đáng tin cậy từ lúc mở phiên đến khi đóng phiên và hết thời hạn lưu.

### 2.3. Ngoại lệ trở thành mặc định

Một hệ thống cũ chưa hỗ trợ ghi phiên có thể cần phương án bù tạm thời. Ngoại lệ trở thành anti-pattern khi không có người chịu trách nhiệm, không có thời hạn và không được đánh giá lại.

Ví dụ, “nhà cung cấp cần sửa gấp” được dùng lặp lại để cho phép truy cập trực tiếp bằng tài khoản quản trị chung. Sau nhiều tháng, mọi phiên bảo trì đều đi theo đường ngoại lệ, trong khi bảng theo dõi vẫn báo PAM đã bao phủ hệ thống.

Ngoại lệ cần được mô tả bằng phạm vi thực tế: tài sản nào, ai được truy cập, làm gì, trong bao lâu, bằng chứng nào còn thu được và ai chấp nhận rủi ro còn lại.

## 3. Những loại bằng chứng không thay thế hoàn toàn cho nhau

| Nguồn bằng chứng | Trả lời tốt câu hỏi nào? | Giới hạn cần nhớ |
| --- | --- | --- |
| Log yêu cầu và phê duyệt quyền | Ai xin quyền, ai duyệt, mục đích và cửa sổ thời gian là gì? | Không mô tả đầy đủ hành vi sau khi được cấp quyền |
| Log xác thực và mở kết nối | Danh tính nào xác thực, kết nối đến đâu và khi nào? | Không đủ để biết thay đổi nghiệp vụ hoặc thao tác cụ thể |
| Bản ghi terminal hoặc desktop | Những tương tác nào đã được recorder quan sát trong phiên? | Không mặc định bao phủ mọi kênh, tác vụ nền hoặc trạng thái cuối trên đích |
| Nhật ký lệnh hoặc tiến trình | Lệnh hay tiến trình nào được nguồn log ghi nhận? | Phụ thuộc vị trí thu thập; có thể thiếu hành vi trong ứng dụng, nội dung đầu vào hoặc tác vụ ngoài phạm vi |
| Audit log trên hệ thống đích | Tài nguyên nào được truy cập hoặc thay đổi theo cơ chế audit của đích? | Chỉ phản ánh các sự kiện đã được cấu hình và hỗ trợ ghi nhận |
| Bản đối chiếu cấu hình, dữ liệu và triển khai | Trạng thái trước và sau khác nhau ra sao? | Cần liên kết với danh tính và dòng thời gian để xác định nguyên nhân |

Một bản ghi desktop có thể cho thấy quản trị viên bấm nút lưu, nhưng không tự chứng minh máy chủ đã áp dụng cấu hình thành công. Cần kiểm tra audit event hoặc trạng thái sau thay đổi.

Tương tự, transcript terminal có thể ghi nội dung hiển thị mà không có cấu trúc sự kiện thực thi độc lập. Không nên gọi mọi dòng văn bản trong transcript là “lệnh đã thực thi”. Khi cần xác nhận hành vi trên đích, phải đối chiếu với nguồn phù hợp.

Shell history cá nhân cũng không phải cơ chế audit đầy đủ. Nó thường thiếu thông tin ngữ cảnh và không phải nguồn bằng chứng độc lập, được quản lý riêng cho mục đích kiểm toán.

Cách tiếp cận đúng là bổ sung các nguồn bằng chứng có vai trò khác nhau, sau đó liên kết chúng bằng mã phiên, danh tính, tài sản, thời gian và mã thay đổi.

## 4. Vì sao bỏ ghi phiên gây hậu quả lớn?

### 4.1. Mất khả năng nối người thật với thao tác

PAM có thể dùng tài khoản đích như `admin-app` hoặc `root` thay cho tài khoản cá nhân. Khi đó, phải duy trì liên kết giữa danh tính cá nhân đã xác thực và tài khoản có đặc quyền được sử dụng trong từng phiên.

Nếu hai người cùng dùng tài khoản đích trong những phiên gần nhau, chỉ log mang tên tài khoản đích có thể không đủ để phân biệt họ. Dùng khoảng thời gian gần nhau để suy đoán người thực hiện đặc biệt dễ sai khi có nhiều kết nối đồng thời.

Bản ghi phiên cần có mã định danh ổn định và thông tin liên kết rõ ràng. Nơi có thể, hệ thống đích nên ghi thêm danh tính hoặc mã tương quan được tin cậy, thay vì buộc điều tra viên chỉ dựa vào suy đoán thời gian.

### 4.2. Kéo dài điều tra và phục hồi

Khi một dịch vụ ngừng hoạt động, nhóm ứng phó cần biết điều gì đã thay đổi để chọn cách phục hồi. Nếu chỉ biết “có người đăng nhập”, họ phải rà soát nhiều giả thuyết và có thể khôi phục nhầm thành phần.

Bằng chứng tốt giúp thu hẹp cửa sổ sự cố, so sánh thao tác với kế hoạch thay đổi và tìm trạng thái cần khôi phục. Bản ghi không thay thế bản sao lưu, nhưng có thể giúp giải thích vì sao hệ thống đi từ trạng thái bình thường sang trạng thái lỗi.

### 4.3. Làm yếu kiểm tra hiệu lực của quyền tạm thời

JIT giới hạn thời gian được cấp quyền. JEA hoặc các cơ chế tương tự giới hạn phạm vi tác vụ. Tuy nhiên, một quyền được cấp đúng thời hạn vẫn có thể bị dùng sai mục đích trong chính khoảng thời gian đó.

Không có bằng chứng hành vi, tổ chức khó xác nhận người dùng đã làm đúng phạm vi phê duyệt hoặc tác vụ có đặc quyền đã kết thúc theo dự kiến. Vì vậy, giới hạn quyền và ghi nhận hành vi giải quyết những câu hỏi khác nhau.

### 4.4. Che khuất cả hành vi sai lẫn lỗi vận hành

Khoảng trống ghi nhận không chỉ liên quan đến chủ ý xấu. Một kỹ sư có thể chạy đúng thao tác trên nhầm máy chủ hoặc thực hiện thiếu một bước trong quy trình. Bản ghi giúp tái hiện bối cảnh để sửa quy trình và đào tạo.

Không nên dùng bản ghi để kết luận lỗi cá nhân trước khi đối chiếu với kế hoạch, trạng thái hệ thống và các nguồn độc lập. Bằng chứng hỗ trợ điều tra; cách diễn giải vẫn phải có cơ sở.

## 5. Thiết kế chuỗi bằng chứng cho một phiên quản trị

### 5.1. Liên kết các giai đoạn của phiên

Một chuỗi bằng chứng có thể được mô tả như sau:

```text
Danh tính cá nhân
    -> yêu cầu quyền và phê duyệt
    -> quyền tạm thời trên tài sản cụ thể
    -> phiên PAM có session_id
    -> tương tác được ghi nhận
    -> audit event và thay đổi trên đích
    -> kết thúc phiên, kiểm tra độ đầy đủ
    -> lưu trữ, truy xuất và hết hạn có kiểm soát
```

Đây là quan hệ logic, không phải yêu cầu mọi hệ thống phải triển khai thành từng dịch vụ riêng biệt.

Các thông tin liên kết nên đủ để trả lời:

- Ai đã xác thực và qua cơ chế nào?
- Quyền nào được cấp, cho mục đích gì và bởi ai?
- Tài khoản có đặc quyền nào được dùng trên tài sản nào?
- Mã phiên là gì, bắt đầu và kết thúc khi nào?
- Những nguồn bằng chứng nào gắn với phiên?
- Bản ghi đầy đủ, thiếu một phần hay không có?
- Ai đã xem, xuất, bảo toàn hoặc xóa bản ghi?

Không đưa mật khẩu, khóa riêng, token phiên hay credential vào metadata chỉ để “đủ thông tin”.

### 5.2. Phân biệt vòng đời phiên và vòng đời bản ghi

Phiên đã kết thúc không có nghĩa bản ghi đã được chuyển đến kho lưu trữ. Ngược lại, có tệp trong kho không có nghĩa toàn bộ hoạt động của phiên đã được ghi.

Nên theo dõi ít nhất ba chiều độc lập:

| Chiều trạng thái | Ví dụ giá trị mô tả | Ý nghĩa |
| --- | --- | --- |
| Phiên truy cập | đang mở, kết thúc bình thường, bị ngắt | Cho biết vòng đời kết nối |
| Độ đầy đủ của việc thu nhận | đầy đủ theo phạm vi đã kiểm tra, thiếu đoạn, không thu được, chưa xác định | Cho biết recorder có thu được dữ liệu dự kiến hay không |
| Việc chuyển và lưu bản ghi | đang đệm, đang chuyển, đã nhận, lỗi, chưa xác minh | Cho biết dữ liệu đang ở đâu và đã được kiểm tra đến mức nào |

Một lần mất mạng giữa recorder và kho lưu trữ có thể chỉ gây chậm chuyển dữ liệu nếu bộ đệm vẫn hoạt động đầy đủ. Không nên tự động gọi đó là mất nội dung.

Ngược lại, nếu recorder ngừng thu nhận giữa phiên, việc tải thành công tệp còn lại không biến bản ghi thành đầy đủ. Trạng thái “đã lưu” phải đi cùng thông tin về độ đầy đủ.

### 5.3. Ví dụ metadata bằng dữ liệu giả lập

```yaml
# Ví dụ thiết kế dữ liệu; không phải cấu hình cho một sản phẩm PAM cụ thể.
sessionId: lab-session-006
requestId: lab-change-042
humanPrincipal: lab-operator-a
targetAsset: lab-server-a
targetAccount: lab-admin
accessType: interactive-terminal
startedAt: "2026-01-15T09:00:00Z"
endedAt: "2026-01-15T09:12:00Z"
sessionState: ended
recording:
  captureState: complete
  deliveryState: verified
  objectId: lab-recording-006
  coverageProfile: terminal-visible-stream-v1
evidence:
  targetAuditCorrelationId: lab-audit-006
  integrityManifestId: lab-manifest-006
exceptionId: null
```

Trong ví dụ, `complete` chỉ nên được gán sau khi thỏa điều kiện kiểm tra của hồ sơ thu nhận. Nó không có nghĩa recorder biết mọi hoạt động có thể xảy ra trên máy chủ.

`coverageProfile` mô tả phạm vi đã được xác nhận, chẳng hạn luồng tương tác terminal đi qua cổng PAM. Nếu có kênh chuyển tệp hoặc tác vụ nền khác, chúng cần bằng chứng phù hợp riêng.

## 6. Bao phủ các đường truy cập thực tế

### 6.1. SSH và terminal

Với phiên terminal, cần xác định recorder quan sát dữ liệu tại đâu, ghi được luồng nào và có bao phủ toàn bộ khoảng thời gian quản trị hay không. Một sự kiện mở kết nối SSH không tự chứng minh luồng tương tác đã được ghi.

Các phiên chỉ mở shell, phiên chạy lệnh không tương tác, việc chuyển tệp và tác vụ được để chạy sau khi ngắt kết nối có thể có đặc điểm ghi nhận khác nhau. Chỉ công bố phạm vi bao phủ sau khi kiểm tra các kiểu sử dụng được phép trong môi trường.

Nếu thao tác tiếp tục chạy sau khi phiên kết thúc, cần audit tại hệ thống đích hoặc dấu vết thực thi khác để theo dõi phần công việc còn lại.

### 6.2. Desktop quản trị từ xa

Bản ghi hình ảnh hoặc sự kiện giao diện giúp tái hiện thao tác, nhưng vẫn cần kiểm tra những kênh có thể mang dữ liệu ngoài hình ảnh, chẳng hạn clipboard hay truyền tệp nếu chúng được cho phép.

Không mặc định video màn hình bao phủ nội dung chuyển tệp. Khi kênh không nằm trong phạm vi thu nhận, lựa chọn có thể là bổ sung audit, hạn chế kênh theo nhu cầu hoặc áp dụng kiểm soát khác đã được chấp thuận.

Cũng cần kiểm tra chất lượng phát lại: độ phân giải, tốc độ cập nhật, mốc thời gian và khả năng đọc nội dung quản trị có quan trọng đối với tình huống sử dụng.

### 6.3. Giao diện quản trị web, cloud console và database

Một phiên truy cập trang quản trị có thể cần kết hợp bằng chứng trên trình duyệt với audit của ứng dụng hoặc nền tảng. Chỉ ghi màn hình mà bỏ qua audit thay đổi quyền hay cấu hình sẽ làm yếu khả năng đối chiếu kết quả.

Với database, thông tin đăng nhập không thể thay thế audit các hoạt động quan trọng trong phạm vi đã chọn. Không nên ghi toàn bộ dữ liệu truy vấn và kết quả theo mặc định nếu việc đó thu thập quá mức dữ liệu nhạy cảm.

Phạm vi audit cần đủ phục vụ mục tiêu truy vết, đồng thời được giới hạn theo nhu cầu vận hành và bảo vệ dữ liệu.

### 6.4. API, service account và automation

Đối với automation, “không có video session” không tự động là sai. Cần có dạng bằng chứng phù hợp với cách tác vụ thực thi, ví dụ:

- Danh tính workload hoặc job được xác thực.
- Run ID của pipeline hoặc mã tác vụ.
- Vai trò, phạm vi quyền và thời điểm cấp quyền.
- Audit event tại dịch vụ đích.
- Kết quả triển khai hoặc đối chiếu thay đổi.

Đừng dùng “đây là service account” để bỏ ghi nhận. Đồng thời, đừng dùng tiêu chí có video để đánh giá một quy trình API vốn không có giao diện tương tác.

### 6.5. Truy cập trực tiếp và kênh khẩn cấp

Nếu một máy chủ vẫn nhận phiên quản trị trực tiếp từ nhiều nguồn, tỷ lệ ghi nhận tại cổng PAM có thể rất đẹp nhưng chỉ phản ánh phần lưu lượng đi qua cổng.

Cần đối chiếu nhật ký trên đích và dữ liệu kết nối với danh sách phiên PAM. Một phiên đặc quyền xuất hiện trên đích mà không tìm được phiên hoặc ngoại lệ tương ứng là dấu hiệu cần điều tra.

Kênh break-glass cần có thiết kế bằng chứng riêng. Trong tình huống khẩn cấp, có thể không duy trì đầy đủ đường thông thường, nhưng phải ghi rõ thời điểm kích hoạt, người sử dụng, phạm vi quyền, nguồn log còn hoạt động và việc hậu kiểm sau sự cố.

## 7. Khi recorder gặp lỗi: quyết định trước, thực hiện nhất quán

Không nên đợi đến lúc recorder ngừng hoạt động mới quyết định có cho phép tiếp tục truy cập hay không. Quyết định cần dựa trên mức độ quan trọng của tài sản, khả năng giữ bằng chứng và nhu cầu duy trì dịch vụ.

Bảng sau là một ví dụ chính sách nội bộ để thiết kế và kiểm thử, không phải quy tắc bắt buộc cho mọi môi trường:

| Tình huống | Cách xử lý được thiết kế | Bằng chứng cần giữ |
| --- | --- | --- |
| Phiên mới vào tài sản quan trọng nhưng recorder không thu nhận được | Từ chối mở theo chính sách; chuyển yêu cầu khẩn cấp sang quy trình riêng nếu cần | Sự kiện từ chối, nguyên nhân và yêu cầu liên quan |
| Kho lưu trữ tạm mất kết nối, recorder vẫn ghi vào bộ đệm được bảo vệ | Chỉ tiếp tục nếu cơ chế đệm đã được hỗ trợ, kiểm thử và còn đủ dung lượng | Thời điểm gián đoạn, trạng thái đệm và kết quả chuyển lại |
| Recorder mất dữ liệu giữa phiên | Cảnh báo ngay; xử lý phiên theo chính sách và khả năng kỹ thuật đã kiểm tra | Khoảng trống thu nhận, quyết định vận hành và bằng chứng bù |
| Bộ đệm sắp đầy hoặc không còn bảo đảm toàn vẹn | Kích hoạt ngưỡng hành động đã định; không coi đường ghi nhận vẫn khỏe | Dung lượng, cảnh báo, hành động đã thực hiện |
| Cần cứu dịch vụ trong khi đường ghi thông thường không dùng được | Dùng ngoại lệ khẩn cấp có người chịu trách nhiệm, giới hạn quyền và hậu kiểm | Danh tính, thời gian, mục đích, nguồn audit thay thế |

“Fail-closed” nghĩa là không cho phép một hành vi truy cập khi điều kiện kiểm soát bắt buộc không đạt. Việc áp dụng cho **phiên mới** và việc xử lý **phiên đang chạy** phải được quy định riêng.

Không phải nền tảng nào cũng có khả năng ngắt an toàn phiên đang chạy khi recorder lỗi. Hơn nữa, việc ngắt một thao tác quản trị giữa chừng có thể gây ảnh hưởng vận hành. Chính sách phải mô tả hành vi thực sự được hỗ trợ, cách cảnh báo và người chịu trách nhiệm quyết định trong tình huống vượt khả năng tự động.

Một tuyên bố “luôn fail-closed” nhưng không được kiểm chứng trên từng kiểu kết nối dễ tạo cảm giác an toàn sai. Cần kiểm tra cả khi mở phiên, trong phiên, khi đóng phiên và khi chuyển bản ghi vào kho.

## 8. Bản ghi phiên cũng là dữ liệu nhạy cảm

### 8.1. Giới hạn nội dung được thu thập

Bản ghi có thể chứa cấu hình nội bộ, dữ liệu khách hàng, đường dẫn hệ thống, token hoặc thông tin được hiển thị trong lúc sửa lỗi. Vì vậy, tăng ghi nhận phải đi cùng giới hạn dữ liệu và quyền xem.

Nên tránh để secret xuất hiện trong luồng thao tác: dùng cơ chế đưa credential vào kết nối phù hợp, hạn chế hiển thị secret và thiết kế tác vụ không yêu cầu sao chép chúng ra màn hình.

Nếu sử dụng cơ chế che hoặc loại trừ dữ liệu, cần kiểm thử phạm vi thực tế. Không nên giả định một chế độ che mật khẩu sẽ tự bảo vệ mọi token hoặc chuỗi nhạy cảm được ứng dụng hiển thị.

Các khoảng loại trừ phải được mô tả trong hồ sơ thu nhận để điều tra viên biết phần nào không có bằng chứng. Một vùng được che vì mục tiêu bảo vệ dữ liệu không được báo thành nội dung đã quan sát đầy đủ.

### 8.2. Tách quyền vận hành khỏi quyền truy cập bằng chứng

Người vận hành máy chủ không nên mặc nhiên được đọc toàn bộ bản ghi của đồng nghiệp hoặc xóa bản ghi phiên của mình. Người quản trị PAM cũng không nhất thiết cần quyền giải mã mọi nội dung.

Có thể tách các quyền:

- Cấu hình kết nối và chính sách PAM.
- Vận hành recorder và kho lưu trữ.
- Tìm kiếm metadata.
- Xem hoặc phát lại nội dung.
- Xuất bản ghi phục vụ điều tra.
- Quản lý khóa và thời hạn lưu.
- Phê duyệt bảo toàn hoặc hủy dữ liệu.

Mức tách quyền phụ thuộc quy mô tổ chức, nhưng mọi lần xem, xuất hoặc thay đổi chính sách quan trọng cần được ghi nhận qua nguồn đủ độc lập với người đang bị kiểm tra.

### 8.3. Lưu trữ và bảo vệ tính toàn vẹn

Mã hóa giúp bảo vệ nội dung khi lưu hoặc truyền, nhưng không tự chứng minh ai đã tạo bản ghi hay bản ghi có đầy đủ hay không. Hash giúp kiểm tra thay đổi dữ liệu so với giá trị đối chiếu, nhưng nếu cùng một người có thể thay cả tệp và hash thì mức bảo đảm rất hạn chế.

Cần xem xét việc bảo vệ metadata, manifest toàn vẹn, nguồn thời gian, cơ chế ký hoặc xác thực khi có, và quyền thay đổi các giá trị đối chiếu. Những cơ chế này bổ sung cho nhau; không cơ chế nào tự bảo đảm toàn bộ chuỗi bằng chứng.

Thời hạn lưu nên gắn với nhu cầu điều tra, yêu cầu nội bộ, khả năng lưu trữ và nghĩa vụ áp dụng của tổ chức. Không có một số ngày duy nhất phù hợp cho mọi hệ thống.

Khi một bản ghi được bảo toàn cho vụ việc đang mở, việc hết hạn tự động cần được xử lý theo quy trình bảo toàn tương ứng. Các bản sao đã xuất cũng phải có người quản lý và thời hạn, tránh tình trạng kho chính được kiểm soát nhưng bản tải về lại tồn tại vô thời hạn.

## 9. Tìm kiếm và sử dụng bằng chứng trong ứng phó sự cố

Một kho có hàng nghìn video nhưng không tra được theo người, tài sản hoặc thời gian vẫn gây trở ngại lớn. Metadata và khả năng truy xuất cần được kiểm tra cùng với cơ chế ghi.

Một quy trình điều tra có thể thực hiện theo thứ tự:

1. Xác định sự kiện cần điều tra và khoảng thời gian ban đầu từ nguồn giám sát.
2. Bảo toàn các nguồn liên quan, tránh để hết hạn hoặc bị thay đổi trong khi điều tra.
3. Tìm phiên theo tài sản, danh tính, tài khoản đích và mã yêu cầu thay đổi.
4. Xác minh trạng thái thu nhận, chuyển dữ liệu và tính toàn vẹn của bản ghi.
5. Dựng dòng thời gian bằng mốc thời gian đã chuẩn hóa; ghi rõ sai lệch hoặc độ chính xác thời gian còn chưa xác định.
6. Đối chiếu tương tác quan sát được với audit event và trạng thái trước, sau trên hệ thống đích.
7. Ghi nhận cả điều đã chứng minh và phần chưa có đủ bằng chứng.
8. Lưu lịch sử người tiếp cận, bản xuất và việc bàn giao bằng chứng.

Nếu phiên không có bản ghi, cần đánh dấu rõ phần còn thiếu. Đừng dựng lại một transcript giả định từ trí nhớ hoặc biến kế hoạch thay đổi thành bằng chứng thực thi.

Một kết luận phù hợp có thể là: “Audit đích ghi nhận thay đổi tại thời điểm này; phiên PAM liên quan đang hoạt động nhưng thiếu đoạn thu nhận tương ứng; chưa đủ bằng chứng để xác định tương tác cụ thể.” Cách diễn đạt này chính xác hơn việc tự gán thao tác cho người có thời gian đăng nhập gần nhất.

## 10. Đo độ bao phủ để tránh báo cáo đẹp nhưng sai

### 10.1. Chọn mẫu số từ phạm vi cần kiểm soát

Giả sử hệ thống đích ghi nhận 100 phiên tương tác có đặc quyền trong một ngày, tất cả thuộc phạm vi phải ghi. PAM quan sát được 90 phiên; 86 phiên có bản ghi đầy đủ và truy xuất được.

Nếu báo cáo 86/90, nhóm vận hành chỉ đang đo mức hoàn chỉnh trong phần phiên PAM đã biết. Để đánh giá độ bao phủ toàn bộ phạm vi, cần xem thêm 86/100 và điều tra 10 phiên không khớp với PAM cùng 4 phiên thiếu bản ghi hợp lệ.

Ví dụ này giả định đã loại trùng và thống nhất định nghĩa phiên giữa các nguồn. Trong thực tế, một phiên PAM có thể gắn với nhiều kết nối trên đích, nên không được trừ hai số đếm thô khi chưa đối soát quan hệ.

Một phiên chưa phân loại nên được báo riêng là chưa xác định. Không đưa nó ra khỏi mẫu số chỉ để tăng tỷ lệ đạt.

### 10.2. Các chỉ số có ích

| Chỉ số | Cách hiểu | Điều cần tránh |
| --- | --- | --- |
| Độ bao phủ phiên cần ghi | Tỷ lệ phiên trong phạm vi có bằng chứng thu nhận hợp lệ | Chỉ lấy các phiên đã đi qua recorder làm mẫu số |
| Tỷ lệ bản ghi phát lại được | Tỷ lệ đạt trong tập được kiểm tra theo tiêu chí đã công bố | Suy rộng một vài mẫu thành toàn bộ kho đã được xác minh |
| Tỷ lệ phiên thiếu hoặc có khoảng trống | Phiên không có bản ghi hoặc thiếu dữ liệu dự kiến | Gộp trễ chuyển dữ liệu với mất nội dung |
| Thời gian đưa bản ghi vào trạng thái truy xuất được | Khoảng từ kết thúc hoặc mốc thu nhận đến khi sử dụng được | Chỉ đo tốc độ tạo tệp tại recorder |
| Thời gian phát hiện lỗi ghi | Khoảng từ lúc lỗi xảy ra đến khi có cảnh báo có thể xử lý | Chỉ kiểm tra khi điều tra viên báo không tìm thấy bản ghi |
| Ngoại lệ chưa khắc phục | Số lượng, tuổi ngoại lệ và mức rủi ro còn lại | Chỉ đếm số phiếu đã được ký duyệt |

Chỉ số cần đi cùng hành động: ai xử lý phiên không khớp, ai khôi phục recorder, khi nào phải hạn chế truy cập và cách đóng ngoại lệ.

## 11. Lộ trình sửa anti-pattern

### Bước 1: Kiểm kê truy cập và nguồn bằng chứng

Liệt kê các tài sản nhạy cảm, giao thức, danh tính người dùng, tài khoản dịch vụ, đường kết nối và kênh khẩn cấp. Với từng đường, ghi rõ đang có nguồn nào và nguồn đó quan sát được gì.

Đừng chỉ hỏi “PAM có hỗ trợ ghi không?”. Câu hỏi cần trả lời là “kiểu truy cập được sử dụng thực tế trên tài sản này có bằng chứng gì và khoảng trống ở đâu?”.

### Bước 2: Chọn kiểm soát theo rủi ro

Ưu tiên phiên quản trị vào hệ thống nhạy cảm, thay đổi quyền, cấu hình xác thực và các hoạt động có ảnh hưởng lớn. Với tương tác con người, xem xét ghi phiên và audit đích. Với automation, ưu tiên danh tính workload, run ID và audit thao tác.

Xác định phạm vi dữ liệu cần thu, thời hạn lưu, quyền xem và điều kiện xử lý lỗi trước khi triển khai rộng.

### Bước 3: Thử nghiệm bằng tác vụ lành tính

Dùng môi trường lab và tài khoản thử được phép. Mở phiên, thực hiện thao tác nhỏ có thể đối chiếu, đóng phiên rồi kiểm tra việc tìm kiếm, phát lại và liên kết với audit đích.

Ví dụ, sửa một tệp cấu hình giả lập trong thư mục lab và đọc lại nội dung. Không cần thực hiện thay đổi đặc quyền nguy hiểm chỉ để chứng minh recorder hoạt động.

### Bước 4: Kiểm tra lỗi và ngoại lệ

Trong môi trường thử có quyền kiểm soát, mô phỏng những điều kiện vận hành đã được cho phép như trễ chuyển bản ghi, recorder không sẵn sàng hoặc giới hạn dung lượng.

Đối chiếu hành vi quan sát với chính sách. Nếu sản phẩm không hỗ trợ hành vi mong muốn, cần điều chỉnh thiết kế, bổ sung kiểm soát hoặc thu hẹp phạm vi truy cập; không ghi nhận đạt bằng một tuyên bố cấu hình.

### Bước 5: Đối soát và duy trì

Sau triển khai, tiếp tục so khớp phiên trên đích với PAM, kiểm tra mẫu bản ghi và theo dõi ngoại lệ. Cập nhật kiểm thử khi thay đổi kiểu kết nối, phiên bản triển khai, đường truy cập hoặc chính sách.

Bản ghi chỉ có giá trị lâu dài khi cơ chế quản lý của nó được vận hành như một phần của hệ thống PAM.

## 12. Bài thực hành: tìm phần bằng chứng bị thiếu

Một nhóm quản trị sử dụng tài sản lab `lab-server-a`. Tất cả dữ liệu dưới đây đều là giả lập:

| Phiên hoặc tác vụ | Bằng chứng hiện có | Vấn đề cần đánh giá |
| --- | --- | --- |
| A: quản trị viên mở terminal qua PAM | Có danh tính cá nhân, yêu cầu quyền, transcript đầy đủ và audit đích liên kết được | Có đủ dữ liệu để truy vết trong phạm vi terminal đã xác định |
| B: nhà cung cấp kết nối trực tiếp đến đích | Chỉ có log đăng nhập bằng tài khoản dùng chung | Không gắn chắc được người thực hiện; thiếu bằng chứng hành vi |
| C: phiên desktop qua PAM | Video chỉ có nửa đầu; không có cảnh báo | Có khoảng trống thu nhận và cơ chế phát hiện lỗi chưa đạt |
| D: pipeline đổi cấu hình dịch vụ | Có workload identity, run ID, audit thao tác và kết quả thay đổi | Đánh giá theo bằng chứng automation, không theo tiêu chí video |
| E: phiên khẩn cấp khi cổng PAM lỗi | Có danh tính, phiếu khẩn cấp, audit đích và thời hạn hậu kiểm | Kiểm tra mức bằng chứng bù và người chấp nhận rủi ro |
| F: phiên terminal đã ghi đầy đủ tại recorder | Chuyển vào kho trễ, bộ đệm còn nguyên, có cảnh báo | Phân biệt trễ lưu trữ với mất thu nhận; xác minh chuyển lại |

Hãy thực hiện ba việc.

Thứ nhất, với từng dòng, ghi điều có thể kết luận và điều chưa thể kết luận. Với B, không kết luận một cá nhân đã thay đổi cấu hình chỉ từ tài khoản dùng chung. Với C, không gọi bản ghi là đầy đủ chỉ vì phát lại được phần đầu.

Thứ hai, đề xuất hành động khắc phục có người chịu trách nhiệm. B có thể cần chặn đường ngoài phạm vi hoặc đưa vào đường kiểm soát đã được thiết kế; C cần sửa việc thu nhận và cảnh báo; E cần hoàn tất hậu kiểm đúng hạn; F cần xác minh dữ liệu đã được chuyển và đối chiếu toàn vẹn.

Thứ ba, xác định điều kiện đóng vấn đề bằng bằng chứng. “Đã bật tùy chọn recording” không đủ. Cần một phiên thử có thể tra cứu, phát lại, liên kết với audit và thể hiện đúng trạng thái vòng đời.

## 13. Tiêu chí nghiệm thu

Một triển khai giải quyết được anti-pattern khi nhóm phụ trách chứng minh được các điều sau trong phạm vi đã xác định:

- Mỗi đường truy cập có đặc quyền được phân loại và có cơ chế ghi nhận hoặc ngoại lệ được quản lý.
- Danh tính cá nhân hoặc workload nối được với quyền cấp, tài sản đích và phiên hay tác vụ tương ứng.
- Nội dung thu nhận phù hợp giao thức; giới hạn quan sát được mô tả rõ.
- Lỗi recorder, thiếu dữ liệu và trễ chuyển được phát hiện, phân biệt và xử lý theo chính sách.
- Hành vi khi điều kiện ghi nhận không đạt đã được kiểm thử cho cả phiên mới và phiên đang chạy trong phạm vi hỗ trợ.
- Bản ghi có thể tìm, đọc hoặc phát lại với quyền được cấp; nguồn kiểm tra toàn vẹn được bảo vệ.
- Việc xem, xuất, thay đổi thời hạn lưu và hủy dữ liệu có dấu vết phù hợp.
- Bản ghi được bảo vệ như dữ liệu nhạy cảm và không thu secret quá mức cần thiết.
- Đối soát với hệ thống đích giúp phát hiện phiên ngoài đường PAM.
- Ngoại lệ khẩn cấp có người chịu trách nhiệm, thời hạn và bằng chứng hậu kiểm.

Kết quả mong muốn là khi có câu hỏi về một hoạt động đặc quyền, tổ chức có thể tìm đúng bằng chứng, hiểu phạm vi của nó và nêu rõ phần còn thiếu. Chỉ có log “đăng nhập thành công” không đáp ứng được mục tiêu đó.
