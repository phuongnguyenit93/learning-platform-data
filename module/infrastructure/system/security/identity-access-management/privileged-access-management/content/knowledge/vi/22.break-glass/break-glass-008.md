# Thông báo sau sử dụng quyền break-glass

## Mục tiêu bài học

Sau khi học xong, bạn có thể:

- Giải thích vì sao thông báo sau sử dụng là một kiểm soát bắt buộc trong quy trình break-glass, dù lần truy cập đó không gây ra sự cố bảo mật.
- Xác định ai cần nhận thông báo, thông tin nào cần xuất hiện trong thông báo và thông tin nào chỉ được lưu trong hệ thống bằng chứng.
- Thiết kế luồng thông báo có khả năng chịu lỗi, theo dõi xác nhận và chuyển cấp khi không có người xử lý.
- Liên kết thông báo với việc thu hồi quyền, luân chuyển credential, đối soát hành động và rà soát sau sử dụng.
- Đánh giá một lần sử dụng break-glass dựa trên bằng chứng thay vì dựa vào lời xác nhận của người thực hiện.

## 1. Thông báo sau sử dụng nằm ở đâu trong PAM?

Break-glass là cơ chế truy cập đặc quyền khẩn cấp khi luồng cấp quyền thông thường không đáp ứng được tình huống, chẳng hạn khi hệ thống xác thực trung tâm bị lỗi hoặc khi phải khôi phục một dịch vụ quan trọng. Cơ chế này có thể cho phép sử dụng tài khoản dự phòng, lấy credential khẩn cấp hoặc kích hoạt một vai trò mạnh trong thời gian giới hạn.

Trong quản lý truy cập đặc quyền, thông báo sau sử dụng là việc chủ động chuyển thông tin về một lần sử dụng break-glass đến những người chịu trách nhiệm vận hành, bảo mật và sở hữu tài nguyên. Thông báo phải giúp người nhận biết chuyện gì đã xảy ra, xác định việc nào còn dang dở và truy cập bằng chứng phù hợp với quyền hạn của họ.

Thông báo không chỉ là câu “đã dùng tài khoản khẩn cấp”. Nó phải trả lời được các câu hỏi:

1. Ai đã sử dụng quyền, sử dụng trên tài nguyên nào và vì lý do gì?
2. Khoảng thời gian truy cập thực tế là khi nào?
3. Người thực hiện đã làm những gì và kết quả ra sao?
4. Quyền khẩn cấp, phiên truy cập và credential hiện ở trạng thái nào?
5. Ai cần xác nhận, ai cần rà soát và thời hạn xử lý là bao lâu?

Một thông báo sau sử dụng tốt tạo cầu nối giữa hành động khẩn cấp và trách nhiệm giải trình. Nó giúp tổ chức quay trở lại mô hình least privilege sau khi tình huống khẩn cấp đã qua.

### 1.1. Không chờ kết thúc mới phát hiện việc sử dụng

Trong một thiết kế hoàn chỉnh, thông báo kích hoạt quyền và cảnh báo sử dụng bất thường có thể được gửi ngay khi phát sinh sự kiện. Thông báo sau sử dụng bổ sung thông tin về kết quả, trạng thái thu hồi và nghĩa vụ rà soát; nó không thay thế các cảnh báo đó.

Ví dụ:

- Khi credential khẩn cấp được checkout: phát sự kiện sử dụng và cảnh báo theo chính sách.
- Khi phiên kết thúc: gửi thông báo tổng kết ban đầu.
- Khi thu hồi hoặc luân chuyển thất bại: gửi cập nhật khẩn và giao người xử lý.
- Khi hoàn tất đối soát: gửi kết luận rà soát cho người có trách nhiệm.

Nếu phiên vượt quá thời lượng cho phép hoặc người dùng không kết thúc phiên đúng cách, hệ thống vẫn phải phát hiện và thông báo. Không được phụ thuộc hoàn toàn vào nút “hoàn tất” do người sử dụng bấm.

### 1.2. Sự cố dịch vụ kết thúc không đồng nghĩa lần dùng quyền đã đóng

Giả sử kỹ sư dùng tài khoản khẩn cấp để khôi phục cơ sở dữ liệu. Dịch vụ đã hoạt động lại, nhưng mật khẩu khẩn cấp vẫn chưa được luân chuyển và token được tạo trong lúc sửa lỗi vẫn còn hiệu lực.

Thông báo “khôi phục thành công, đã đóng” sẽ che khuất rủi ro còn tồn tại. Cách diễn đạt đúng hơn là:

> Dịch vụ đã phục hồi. Phiên tương tác đã kết thúc. Việc vô hiệu hóa token phát sinh chưa được xác minh; người phụ trách IAM đang xử lý, hạn cập nhật tiếp theo được ghi trong hồ sơ.

Thông báo phải phân biệt trạng thái của dịch vụ với trạng thái của quyền truy cập.

## 2. Các mục tiêu kiểm soát

### 2.1. Minh bạch và quy trách nhiệm

Người sở hữu hệ thống cần biết khi nào hàng rào truy cập thông thường đã bị thay thế bằng đường khẩn cấp. Nhóm bảo mật cần có đủ dữ kiện để xác định việc sử dụng có phù hợp với tình huống hay không.

Đặc biệt, nếu nhiều người có thể lấy cùng một credential khẩn cấp, tên tài khoản đích không đủ để quy trách nhiệm. Phải liên kết được lần sử dụng với danh tính người checkout, danh tính người thao tác và các phiên thực tế.

Nếu không xác định được người thực hiện, thông báo phải ghi rõ khoảng trống này và mở công việc điều tra. Không được suy đoán danh tính chỉ từ địa chỉ IP hoặc từ tên người trực ca.

### 2.2. Khôi phục trạng thái kiểm soát

Quyền khẩn cấp cần được thu hồi đúng hạn. Tùy cơ chế, việc khôi phục có thể bao gồm:

- Hết hiệu lực hoặc gỡ vai trò được kích hoạt tạm thời.
- Kết thúc các phiên còn mở và kiểm tra phiên chạy ngoài luồng.
- Thu hồi token, khóa truy cập hoặc chứng chỉ phát sinh.
- Luân chuyển mật khẩu đã tiết lộ, theo quy trình phù hợp với tài khoản.
- Kiểm tra tài khoản, nhóm hoặc chính sách mới được tạo trong phiên.
- Xử lý ngoại lệ có chủ sở hữu nếu chưa thể hoàn tất ngay.

Thông báo là cách làm cho các việc này có người chịu trách nhiệm và có thể được kiểm tra lại. Bản thân việc gửi thông báo không thực hiện các thao tác thu hồi.

### 2.3. Phát hiện sai lệch và bảo toàn bằng chứng

Báo cáo của người thực hiện cần được đối chiếu với log, bản ghi phiên và thay đổi thực tế. Những sai lệch như truy cập thêm máy chủ, tạo tài khoản ngoài phạm vi hoặc tiếp tục đăng nhập sau thời điểm báo kết thúc cần được rà soát.

Không phải sai lệch nào cũng chứng minh có hành vi độc hại. Tuy nhiên, một sai lệch chưa giải thích được phải có người xử lý và không được biến mất chỉ vì thông báo đã được gửi thành công.

## 3. Khi nào phải tạo thông báo sau sử dụng?

Điểm kích hoạt cần rõ ràng, có thể kiểm tra và không chỉ dựa vào lời khai của con người.

| Tình huống | Hành động thông báo | Điểm cần làm rõ |
|---|---|---|
| Phiên kết thúc bình thường | Gửi tổng kết sử dụng ban đầu | Kết quả công việc, tài nguyên đã chạm đến, trạng thái thu hồi |
| Quyền tạm thời hết hạn | Gửi tổng kết theo thời điểm hết hạn | Có bằng chứng phiên đã kết thúc hay chỉ mới hết hạn cấp quyền |
| Người dùng bị ngắt kết nối | Tạo thông báo với trạng thái chưa xác minh đầy đủ | Phiên hoặc tiến trình phía đích có còn tồn tại không |
| Credential đã được lấy nhưng chưa thấy đăng nhập | Gửi thông báo về việc tiết lộ credential | Không được kết luận credential chưa từng được dùng |
| Phát hiện sử dụng ngoài cơ chế PAM | Cảnh báo ngay và mở hồ sơ đối soát | Danh tính thực hiện, lý do đi ngoài luồng, phạm vi ảnh hưởng |
| Không có sự kiện kết thúc sau thời hạn dự kiến | Phát cảnh báo quá hạn và chuyển cấp | Ai chịu trách nhiệm kiểm tra, có cần chấm dứt truy cập không |
| Thu hồi hoặc luân chuyển thất bại | Gửi cập nhật có mức ưu tiên phù hợp | Quyền nào còn hiệu lực, biện pháp bù đắp, thời hạn cập nhật |
| Phát hiện hành động nghi vấn trong rà soát | Chuyển sang quy trình ứng phó sự cố | Bảo toàn bằng chứng và giới hạn người nhận theo nhu cầu xử lý |

### 3.1. Checkout không đồng nghĩa đã sử dụng, nhưng vẫn có rủi ro

Nếu mật khẩu khẩn cấp đã được hiển thị cho một người, tổ chức phải xử lý khả năng credential đã rời khỏi phạm vi bảo vệ, kể cả khi chưa thấy log đăng nhập.

Thông báo có thể ghi:

> Đã ghi nhận việc lấy credential. Chưa tìm thấy phiên tương ứng trong các nguồn log hiện có. Đang đối soát log hệ thống đích và thực hiện luân chuyển theo chính sách.

Không nên ghi “không sử dụng, không cần xử lý” chỉ vì hệ thống PAM không ghi nhận phiên. Người dùng có thể kết nối trực tiếp, log có thể chậm hoặc có thể đang thiếu nguồn dữ liệu.

### 3.2. Một lần dùng quyền có thể có nhiều phiên

Một quyền khẩn cấp có thể được dùng để mở nhiều phiên SSH, truy cập giao diện quản trị và gọi API. Do đó, cần có một mã lần sử dụng chung và các mã phiên con.

Thông báo tổng kết chỉ được coi là đủ phạm vi khi đã nêu rõ các phiên được biết đến và những phần chưa đối soát xong. Kết thúc một phiên đầu tiên không có nghĩa mọi phiên trong lần sử dụng đó đều đã kết thúc.

## 4. Ai cần nhận thông báo?

Danh sách người nhận phải dựa trên trách nhiệm, mức độ quan trọng của tài nguyên và tình huống thực tế.

| Vai trò | Mục đích nhận | Trách nhiệm sau khi nhận |
|---|---|---|
| Chủ sở hữu dịch vụ hoặc tài nguyên | Xác nhận nhu cầu và ảnh hưởng nghiệp vụ | Đánh giá phạm vi thay đổi và kết quả khôi phục |
| Nhóm trực vận hành | Tiếp nối xử lý kỹ thuật | Theo dõi hạng mục chưa hoàn tất và xác minh dịch vụ |
| Nhóm bảo mật hoặc SOC | Phát hiện lạm dụng và điều tra dấu hiệu bất thường | Đối soát nguồn log, phân loại cảnh báo |
| Người vận hành PAM/IAM | Khôi phục kiểm soát đặc quyền | Xác minh thu hồi, luân chuyển và vòng đời quyền |
| Người rà soát độc lập | Đánh giá tính phù hợp của lần sử dụng | Ghi kết luận, ngoại lệ và hành động khắc phục |
| Người đã sử dụng quyền | Bổ sung diễn giải và tiếp nhận yêu cầu làm rõ | Cung cấp thông tin, không tự phê duyệt kết luận của mình |
| Bộ phận kiểm toán hoặc tuân thủ | Theo dõi nghĩa vụ theo chính sách | Truy cập hồ sơ theo quyền, không nhất thiết nhận mọi cảnh báo thời gian thực |

### 4.1. Có người chịu trách nhiệm, không chỉ có nhóm nhận tin

Một danh sách gửi thư như `security@example.invalid` chưa đủ để bảo đảm sẽ có người xử lý. Cần một chủ sở hữu công việc cụ thể hoặc một hàng đợi có lịch trực và quy tắc nhận việc.

Thông báo phải liên kết đến hồ sơ có thể hiện:

- Người hoặc đội đang sở hữu việc rà soát.
- Người xử lý các lỗi thu hồi quyền.
- Thời hạn phản hồi và thời điểm chuyển cấp.
- Người thay thế khi người nhận chính vắng mặt.

Địa chỉ và tài nguyên trong bài đều là dữ liệu minh họa.

### 4.2. Rà soát cần có mức độc lập phù hợp

Người thực hiện phải giải trình được hành động của mình, nhưng không nên là người duy nhất quyết định lần sử dụng đó đã hợp lệ và đã đóng.

Với hệ thống nhạy cảm, có thể cần cả chủ sở hữu dịch vụ xác nhận nhu cầu lẫn người rà soát bảo mật đánh giá hành động đặc quyền. Đây là các trách nhiệm khác nhau; một phản hồi “đã nhận” không thay thế hai đánh giá đó.

### 4.3. Phân phối theo phạm vi cần biết

Nhóm rộng có thể nhận thông báo ngắn về việc đã xảy ra một lần dùng quyền khẩn cấp. Người xử lý được phân quyền mới xem chi tiết tên tài khoản, tài nguyên, hành động hoặc bằng chứng nhạy cảm.

Nếu nội dung liên quan đến điều tra nội bộ, cần phối hợp danh sách người nhận với người phụ trách sự cố. Không mặc định gửi toàn bộ chi tiết điều tra cho mọi người có tên trong ca trực.

## 5. Nội dung thông báo: đủ hành động, đủ truy vết

Một thông báo hữu ích nên có các nhóm dữ liệu sau.

### 5.1. Định danh và bối cảnh

- Mã lần sử dụng break-glass.
- Mã sự kiện thông báo và số phiên bản.
- Mã incident, yêu cầu thay đổi hoặc hồ sơ khẩn cấp liên quan.
- Dịch vụ, môi trường và phạm vi tài nguyên bị tác động.
- Danh tính người thực hiện và tài khoản đặc quyền được sử dụng.
- Lý do dùng đường khẩn cấp, kèm trạng thái đã hoặc chưa được đối soát.

Nếu không có mã incident lúc khẩn cấp, quy trình cần tạo hồ sơ liên kết sau đó và giữ lại sự kiện gốc. Việc bổ sung hồ sơ không được làm sai lệch thời điểm sử dụng thực tế.

### 5.2. Thời gian và kết quả

- Thời điểm kích hoạt hoặc checkout.
- Thời điểm bắt đầu và kết thúc các phiên đã biết.
- Thời điểm phát hiện, tạo thông báo và gửi thông báo.
- Múi giờ hoặc độ lệch UTC rõ ràng.
- Kết quả công việc và ảnh hưởng còn tồn tại.
- Những hành động chính, trình bày ở mức đủ để người rà soát biết cần xem bằng chứng nào.

Ví dụ, `2026-11-26T02:15:00Z` và `2026-11-26T09:15:00+07:00` là hai cách biểu diễn cùng một thời điểm. Tránh chỉ ghi “09:15” khi các đội hoạt động ở nhiều múi giờ.

Nếu chưa biết thời điểm kết thúc, để trạng thái chưa xác định; không tự dùng thời điểm gửi thông báo làm thời điểm kết thúc phiên.

### 5.3. Trạng thái khôi phục kiểm soát

Thông báo cần tách riêng từng kết quả thay vì dùng một nhãn chung “đã xong”.

| Kiểm soát | Ví dụ trạng thái | Bằng chứng cần tham chiếu |
|---|---|---|
| Vai trò tạm thời | Đã thu hồi hoặc đang chờ xác minh | Sự kiện gỡ vai trò và kiểm tra quyền hiệu lực |
| Phiên truy cập | Đã đóng, còn mở hoặc chưa đối soát đủ | Mã phiên và nguồn log hệ thống đích |
| Credential đã tiết lộ | Đã luân chuyển hoặc đang xử lý | Mã công việc luân chuyển và kết quả xác minh |
| Token hoặc khóa phát sinh | Đã thu hồi hoặc chưa kiểm kê đủ | Danh sách định danh và kết quả thu hồi |
| Thay đổi ngoài phạm vi dự kiến | Không phát hiện, có ngoại lệ hoặc chưa rà soát | Hồ sơ thay đổi và kết luận người rà soát |
| Bằng chứng | Sẵn sàng, thiếu một phần hoặc chưa thu thập xong | Chỉ mục bằng chứng có kiểm soát truy cập |

“Đã gửi lệnh thu hồi” chưa chắc là “đã thu hồi có hiệu lực”. Với một số cơ chế, phiên hoặc token đã phát hành vẫn cần được xử lý riêng. Thông báo phải phản ánh điều đã xác minh được, không suy diễn từ một phản hồi kỹ thuật đơn lẻ.

### 5.4. Yêu cầu hành động

Người nhận cần biết rõ họ phải làm gì:

- Xác nhận đã tiếp nhận hồ sơ.
- Rà soát phạm vi hành động.
- Xác minh một kiểm soát chưa hoàn tất.
- Giải trình sai lệch hoặc bổ sung bằng chứng.
- Chấp nhận ngoại lệ theo thẩm quyền hoặc yêu cầu xử lý tiếp.

Mỗi yêu cầu cần có người sở hữu và thời hạn. Nếu chỉ gửi “để mọi người nắm”, hệ thống khó phân biệt một lần dùng quyền đã được kiểm tra với một email đã bị bỏ qua.

## 6. Những gì không được đưa vào kênh thông báo

Không đưa các nội dung sau vào email, kênh chat hoặc phần mô tả rộng của ticket:

- Mật khẩu, khóa riêng, token, recovery code hoặc credential khác.
- Đường dẫn ký sẵn cho phép xem bản ghi phiên mà không cần xác thực phù hợp.
- Toàn bộ đầu ra lệnh có thể chứa bí mật, dữ liệu cá nhân hoặc dữ liệu khách hàng.
- Toàn bộ bản ghi phiên dưới dạng tệp đính kèm gửi cho danh sách rộng.
- Chi tiết điều tra nhạy cảm vượt quá phạm vi cần biết của người nhận.

Chỉ nên đưa mã tham chiếu và đường dẫn đến hệ thống bằng chứng yêu cầu xác thực, phân quyền và ghi nhận truy cập. Không sao chép bí mật vào thông báo ngay cả khi bí mật đó đã được luân chuyển.

### 6.1. Làm sạch trường nhập tự do

Lý do sử dụng quyền và ghi chú thao tác thường do người dùng nhập. Chúng có thể vô tình chứa mật khẩu, hoặc chứa ký tự điều khiển, HTML và chuỗi `@everyone` gây tác dụng ngoài ý muốn.

Khi tạo thông báo:

1. Giữ bản gốc trong nguồn bằng chứng được bảo vệ phù hợp.
2. Tạo bản tóm tắt đã loại bỏ dữ liệu nhạy cảm.
3. Mã hóa hoặc escape theo định dạng đầu ra.
4. Giới hạn độ dài và không diễn giải nội dung nhập tự do như lệnh hay đánh dấu hệ thống.

Nếu phát hiện bí mật đã bị gửi vào kênh rộng, cần xử lý việc lộ bí mật theo quy trình tương ứng. Xóa một tin nhắn không chứng minh mọi bản sao đã biến mất.

## 7. Phân biệt gửi tin, xác nhận và kết luận

Một lỗi thiết kế thường gặp là dùng một trường `notification_status=done` để đại diện cho toàn bộ quy trình.

Ít nhất cần phân biệt:

- **Đã tạo:** sự kiện cần thông báo đã được lưu bền vững.
- **Đã chuyển tới kênh:** nhà cung cấp hoặc hệ thống đích đã tiếp nhận yêu cầu gửi.
- **Đã có người tiếp nhận:** người có trách nhiệm đã xác nhận nhận việc.
- **Đã rà soát:** người được giao đã xem xét hồ sơ và ghi kết luận.
- **Đã khắc phục và đóng:** các điều kiện đóng đã được đáp ứng hoặc ngoại lệ đã được xử lý đúng thẩm quyền.

Phản hồi thành công của API gửi email thường chỉ chứng minh một bước kỹ thuật trong chuỗi gửi tin. Nó không chứng minh người nhận đã đọc hay chấp nhận nội dung.

### 7.1. Theo dõi hai luồng trạng thái riêng

Luồng thông báo và luồng rà soát có quan hệ nhưng không nên gộp thành một.

```text
Luồng thông báo:
Đã tạo → Đang gửi → Kênh đã tiếp nhận → Người xử lý đã nhận
                    ↘ Gửi lỗi → Thử lại / kênh dự phòng / chuyển cấp

Luồng rà soát:
Chờ rà soát → Đang rà soát → Có hành động khắc phục → Đã kiểm tra lại → Đóng
                              ↘ Dấu hiệu sự cố → Quy trình ứng phó sự cố
```

Hồ sơ có thể đã được tiếp nhận nhưng chưa được rà soát. Cũng có thể việc rà soát đã bắt đầu trong khi một kênh gửi phụ vẫn đang lỗi. Lưu hai luồng riêng giúp tránh hiểu sai tình trạng thực tế.

### 7.2. Xác nhận phải gắn với danh tính

Một nút “đã nhận” trong hệ thống hồ sơ nên yêu cầu xác thực và ghi lại người xác nhận, thời gian, vai trò và phạm vi việc họ nhận.

Không nên coi việc hệ thống quét liên kết trong email truy cập một URL là hành động xác nhận của con người. Thao tác làm thay đổi trạng thái cần được thiết kế để tránh việc mở liên kết tự động tạo ra xác nhận sai.

## 8. Thời hạn, ưu tiên và chuyển cấp

Không có một thời hạn duy nhất phù hợp cho mọi tổ chức. Cần đặt mục tiêu theo mức độ quan trọng của tài nguyên, khả năng còn quyền tồn dư và lịch trực thực tế.

Ví dụ chính sách nội bộ minh họa:

| Loại tình huống | Mục tiêu thông báo | Mục tiêu tiếp nhận | Xử lý khi quá hạn |
|---|---|---|---|
| Phiên kết thúc bình thường trên tài nguyên quan trọng | Trong 5 phút từ sự kiện kết thúc | Trong 30 phút | Chuyển cho người trực thay thế |
| Thu hồi quyền thất bại hoặc còn phiên chưa rõ | Cảnh báo ngay khi phát hiện | Trong 10 phút | Gọi người trực, đồng thời cập nhật hồ sơ |
| Credential đã lộ nhưng không ghép được phiên | Thông báo ngay khi phát hiện khoảng trống | Trong 15 phút | Giao PAM/IAM và bảo mật đối soát |
| Rà soát lần sử dụng không có dấu hiệu bất thường | Hoàn tất theo lịch đã định | Có người nhận việc trước hạn | Chuyển cấp cho chủ sở hữu trách nhiệm |

Các con số trên chỉ để minh họa cách xây dựng chính sách, không phải yêu cầu chuẩn hay cam kết áp dụng cho mọi môi trường.

Thời hạn cần có điểm bắt đầu rõ ràng. Chẳng hạn, độ trễ thông báo sau kết thúc được tính từ thời điểm kết thúc phiên đã được ghi nhận, còn độ trễ cảnh báo thu hồi thất bại tính từ lúc phát hiện thất bại.

Nếu sự kiện đến trễ, cần giữ cả thời gian sự kiện và thời gian hệ thống nhận được nó. Không đổi thời gian gốc để làm số liệu độ trễ trông tốt hơn.

## 9. Thiết kế luồng thông báo có khả năng chịu lỗi

### 9.1. Ghi nhận bền vững trước khi gửi

Một mô hình triển khai phổ biến là ghi sự kiện kết thúc vào kho bền vững rồi để thành phần riêng xử lý thông báo.

```text
Nguồn PAM / hệ thống đích
          │
          ▼
Ghi sự kiện sử dụng và mã liên kết
          │
          ▼
Tạo yêu cầu thông báo bền vững
          │
          ▼
Định tuyến người nhận → Gửi → Ghi kết quả → Theo dõi xác nhận
          │                    │
          │                    └→ Thất bại: thử lại, kênh dự phòng, chuyển cấp
          ▼
Liên kết hồ sơ rà soát và bằng chứng
```

Nếu việc lưu kết quả sử dụng và tạo yêu cầu thông báo được thực hiện trong cùng một hệ thống giao dịch, có thể dùng mẫu outbox để giảm nguy cơ lưu thành công nhưng bỏ sót thông báo. Nếu các thành phần nằm ở nhiều hệ thống, cần cơ chế đối soát để phát hiện sự kiện chưa có yêu cầu gửi.

Không nên thiết kế sao cho sự cố email khiến hệ thống bỏ qua việc thu hồi quyền. Các kiểm soát phải được theo dõi riêng, có chủ sở hữu xử lý lỗi.

### 9.2. Chấp nhận khả năng gửi lặp và xử lý trùng

Khi dịch vụ gửi bị timeout, hệ thống có thể không biết yêu cầu trước đã được tiếp nhận hay chưa. Thử lại có thể tạo thông báo trùng.

Có thể dùng một khóa xử lý như:

```text
usage_id + notification_type + revision + recipient_route
```

Khóa này giúp nhận diện cùng một thông báo gửi lại. Không dùng khóa chỉ gồm `usage_id` cho mọi trường hợp, vì cập nhật về thu hồi thất bại hoặc kết luận rà soát là nội dung mới cần được chuyển đi.

Cần phân biệt:

- Gửi lại cùng phiên bản do lỗi vận chuyển.
- Gửi phiên bản mới vì có thêm dữ kiện.
- Gửi chuyển cấp cho người nhận khác.
- Hợp nhất các thông báo giống nhau để giảm nhiễu.

Một người dùng trả lời hai lần không nên tạo hai lần đóng hồ sơ. Các thao tác tiếp nhận và đóng cũng cần kiểm tra trạng thái hiện tại.

### 9.3. Thử lại có giới hạn và có đường thoát

Luồng thử lại cần có:

- Khoảng chờ tăng dần và giới hạn số lần hoặc thời gian.
- Phân loại lỗi tạm thời và lỗi cấu hình.
- Hàng đợi lỗi hoặc danh sách công việc không gửi được.
- Cảnh báo cho người vận hành khi thông báo quan trọng bị kẹt.
- Khả năng gửi lại sau khi khắc phục mà vẫn giữ lịch sử thất bại.

Một hàng đợi lỗi không có người theo dõi chỉ chuyển việc bỏ sót từ hộp thư sang một vị trí khác.

### 9.4. Có kênh dự phòng khi hạ tầng chính bị ảnh hưởng

Tình huống cần break-glass có thể đồng thời làm hỏng hệ thống danh tính, công cụ chat hoặc cổng ticket thông thường.

Với tài nguyên quan trọng, nên chuẩn bị đường thông báo dự phòng có thể sử dụng khi các phụ thuộc chính không hoạt động. Ví dụ là quy trình gọi trực qua số liên hệ được quản lý hoặc hệ thống cảnh báo độc lập.

Kênh dự phòng vẫn phải có giới hạn nội dung. Cuộc gọi có thể chỉ yêu cầu người trực tiếp nhận một mã hồ sơ; không đọc mật khẩu hoặc gửi bản ghi phiên qua kênh cá nhân.

Nếu buộc phải ghi nhận thủ công trong lúc gián đoạn, sau khi khôi phục cần nhập lại hồ sơ với thời gian gốc, nguồn xác nhận và lý do ghi nhận trễ. Không giả lập như thể hệ thống đã gửi tự động đúng hạn.

### 9.5. Kiểm tra sự kiện bị bỏ sót

Cần đối soát định kỳ giữa:

- Lần checkout credential.
- Lần kích hoạt vai trò khẩn cấp.
- Log đăng nhập của tài khoản break-glass trên hệ thống đích.
- Các phiên được PAM ghi nhận.
- Thông báo và hồ sơ rà soát tương ứng.

Mục tiêu là tìm các trường hợp “có sử dụng nhưng chưa có thông báo”, “đã thông báo nhưng thiếu phiên” và “đã báo đóng nhưng vẫn còn truy cập”.

Nguồn đối soát cần có mức độc lập phù hợp. Nếu mọi dữ liệu đều chỉ đến từ một proxy PAM, việc đi vòng proxy có thể không được phát hiện.

## 10. Ví dụ sự kiện và mẫu thông báo

### 10.1. Sự kiện tối thiểu có cấu trúc

Ví dụ JSON dưới đây minh họa dữ liệu nội bộ sau khi kết thúc phiên. Đây không phải định dạng chuẩn của một nhà cung cấp cụ thể.

```json
{
  "schema_version": 1,
  "event_id": "bg-event-0081",
  "usage_id": "bg-use-0042",
  "notification_type": "POST_USE_SUMMARY",
  "revision": 1,
  "occurred_at": "2026-11-26T02:15:00Z",
  "recorded_at": "2026-11-26T02:15:08Z",
  "actor_id": "person-017",
  "privileged_account_ref": "account-bg-db-01",
  "resource_refs": ["db-prod-example"],
  "incident_ref": "INC-EXAMPLE-42",
  "session_refs": ["session-example-01"],
  "outcome": "SERVICE_RESTORED",
  "control_state": {
    "session_termination": "VERIFIED",
    "temporary_role_revocation": "NOT_APPLICABLE",
    "credential_rotation": "PENDING",
    "derived_credentials_review": "PENDING"
  },
  "review": {
    "queue": "security-duty",
    "ack_due_at": "2026-11-26T02:45:00Z",
    "review_state": "OPEN"
  },
  "evidence_ref": "evidence-index-example-42"
}
```

Các định danh ở đây là tham chiếu. Khi dựng thông báo cho một kênh cụ thể, hệ thống chỉ đưa ra những trường mà nhóm người nhận được phép xem.

Trạng thái `NOT_APPLICABLE` cần có lý do phù hợp trong hồ sơ: ví dụ lần sử dụng này dùng credential cố định và không kích hoạt vai trò tạm thời. Không dùng trạng thái này chỉ vì chưa thu thập được dữ liệu.

### 10.2. Mẫu thông báo sau sử dụng

```text
Tiêu đề: [Break-glass][Cần rà soát] bg-use-0042 — dịch vụ cơ sở dữ liệu ví dụ

Lý do sử dụng:
Khôi phục dịch vụ khi luồng truy cập quản trị thông thường không khả dụng.

Người thực hiện:
person-017; danh tính đã liên kết với lần checkout và phiên session-example-01.

Phạm vi:
db-prod-example; tài khoản đặc quyền account-bg-db-01.

Thời gian:
Bắt đầu: 2026-11-26T02:00:00Z
Kết thúc phiên đã ghi nhận: 2026-11-26T02:15:00Z

Kết quả:
Dịch vụ đã phục hồi. Phạm vi thay đổi chi tiết được lưu trong hồ sơ.

Khôi phục kiểm soát:
- Kết thúc phiên: đã xác minh.
- Luân chuyển credential: đang xử lý.
- Kiểm tra token/khóa phát sinh: chưa hoàn tất đối soát.

Yêu cầu:
- Nhóm trực bảo mật tiếp nhận trước 2026-11-26T02:45:00Z.
- Nhóm PAM xử lý luân chuyển theo công việc được liên kết.
- Chủ sở hữu dịch vụ xác nhận ảnh hưởng và phạm vi thay đổi.
- Người rà soát độc lập ghi kết luận trước hạn trong hồ sơ.

Hồ sơ và bằng chứng:
INC-EXAMPLE-42 / evidence-index-example-42
Truy cập qua cổng nội bộ có xác thực và phân quyền.

Lưu ý:
Hồ sơ đang mở. Thông báo này không xác nhận đã thu hồi toàn bộ quyền.
```

Một bản cập nhật tiếp theo cần chỉ ra điều gì thay đổi, chẳng hạn “revision 2: luân chuyển credential đã xác minh; kiểm kê token vẫn đang xử lý”. Tránh gửi một bản tổng kết mới không có số phiên bản khiến người nhận nhầm bản cũ với trạng thái hiện tại.

## 11. Quy trình vận hành từ kết thúc đến đóng hồ sơ

### Bước 1: Xác định sự kiện và phạm vi

Hệ thống ghi nhận sự kiện kết thúc hoặc quá hạn, gắn mã lần sử dụng và liên kết các phiên đã biết.

Nếu thông tin chưa đầy đủ, ghi rõ phần chưa biết. Việc thiếu một bản ghi phiên không phải lý do để trì hoãn mọi thông báo cho đến khi có đủ dữ liệu.

### Bước 2: Thực hiện và xác minh khôi phục quyền

PAM/IAM và người vận hành xử lý việc kết thúc truy cập, thu hồi quyền và luân chuyển credential theo cơ chế thực tế.

Nếu thao tác có thể ảnh hưởng dịch vụ, cần điều phối với người sở hữu để thực hiện có kiểm soát. Không đánh dấu hoàn tất chỉ vì đã giao công việc cho đội khác. Trong thời gian chờ, hồ sơ phải thể hiện quyền còn tồn tại và người chịu trách nhiệm.

### Bước 3: Gửi tổng kết ban đầu

Hệ thống dựng thông báo từ dữ liệu có cấu trúc, làm sạch nội dung tự do và chọn người nhận theo dịch vụ, môi trường và mức rủi ro.

Thông báo ban đầu nêu kết quả đã biết, hạng mục còn mở và thời hạn cập nhật tiếp theo.

### Bước 4: Tiếp nhận và chuyển cấp

Người trực nhận việc bằng danh tính của mình. Nếu quá hạn, hệ thống chuyển cấp theo lịch trực và ghi lại toàn bộ nỗ lực gửi.

Lỗi kênh thông báo và lỗi người nhận không phản hồi là hai vấn đề khác nhau; cần phân biệt để xử lý đúng nguyên nhân.

### Bước 5: Rà soát độc lập

Người rà soát đối chiếu:

- Lý do khẩn cấp với sự cố thực tế.
- Thời lượng và phạm vi truy cập với nhu cầu xử lý.
- Diễn giải của người thực hiện với log và bản ghi phiên.
- Những thay đổi trực tiếp với các tài khoản, token, tác vụ hoặc cấu hình phát sinh.
- Bằng chứng thu hồi với quyền hiệu lực sau xử lý.
- Khoảng trống log và những ngoại lệ chưa giải thích được.

Nếu phát hiện dấu hiệu sự cố, cần chuyển sang quy trình ứng phó tương ứng. Thông báo sau sử dụng vẫn tiếp tục làm nhiệm vụ truy vết, nhưng không thay thế hồ sơ điều tra.

### Bước 6: Ghi kết luận và điều kiện đóng

Chỉ đóng khi người có thẩm quyền đã ghi kết luận, các việc khắc phục đã được kiểm tra hoặc ngoại lệ còn lại đã được chấp nhận theo chính sách với phạm vi và thời hạn rõ ràng.

Đánh giá sau sử dụng không biến một lần truy cập trái phép thành hợp lệ về mặt hồi tố. Nếu hành vi không đáp ứng điều kiện break-glass, kết luận phải thể hiện đúng điều đó và dẫn đến hành động phù hợp.

### Bước 7: Cập nhật bên liên quan và lưu bằng chứng

Thông báo kết luận nêu tình trạng cuối, người rà soát và các công việc còn theo dõi nếu có. Hồ sơ được lưu theo chính sách tổ chức, với quyền truy cập và khả năng kiểm tra tính toàn vẹn phù hợp.

Không xóa lịch sử thông báo lỗi, chỉnh sửa hoặc chuyển cấp chỉ để giữ hồ sơ gọn.

## 12. Tình huống thực tế: dịch vụ phục hồi nhưng luân chuyển thất bại

Một kỹ sư trực dùng tài khoản break-glass để sửa cấu hình cơ sở dữ liệu khi hệ thống cấp quyền thông thường bị gián đoạn.

Diễn biến minh họa:

| Thời điểm UTC | Sự kiện | Ý nghĩa đối với thông báo |
|---|---|---|
| 02:00 | Checkout credential khẩn cấp | Đã phát sinh lần sử dụng cần truy vết |
| 02:03 | Mở phiên quản trị | Liên kết phiên với người thực hiện |
| 02:12 | Dịch vụ hoạt động trở lại | Kết quả nghiệp vụ đã đạt |
| 02:15 | Phiên kết thúc | Tạo tổng kết sau sử dụng |
| 02:16 | Luân chuyển mật khẩu thất bại | Tạo cập nhật ưu tiên, hồ sơ tiếp tục mở |
| 02:20 | Nhóm trực tiếp nhận xử lý | Ghi nhận danh tính người sở hữu việc khắc phục |
| 02:35 | Hoàn tất luân chuyển và xác minh | Cập nhật trạng thái kiểm soát |
| 03:00 | Rà soát phát hiện một token quản trị được tạo | Bổ sung phạm vi thu hồi, chưa đóng |
| 03:15 | Token được thu hồi, kiểm tra lại hoàn tất | Đủ dữ kiện để người rà soát kết luận |

Trong tình huống này, có ba cách xử lý sai:

1. Gửi “đã hoàn tất” ngay lúc 02:15 vì phiên đã kết thúc.
2. Không gửi gì cho đến 03:15 để chờ mọi việc đều xong.
3. Gửi cảnh báo lúc 02:16 nhưng không giao người xử lý hoặc theo dõi xác nhận.

Cách xử lý phù hợp là gửi tổng kết kịp thời, nêu rõ các phần đang mở, cập nhật khi có thay đổi và chỉ đóng sau rà soát. Người nhận nhìn thấy được cả thành công trong khôi phục dịch vụ lẫn rủi ro truy cập còn lại.

## 13. Các lỗi thường gặp và cách khắc phục

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ gửi cho người đã dùng quyền | Thiếu giám sát độc lập | Bổ sung chủ sở hữu, người trực và người rà soát theo trách nhiệm |
| Chỉ dựa vào thao tác tự báo kết thúc | Có thể bỏ sót phiên quá hạn hoặc đi ngoài luồng | Kết hợp thời hạn, log đích và đối soát |
| Chỉ thông báo “đã dùng break-glass” | Người nhận không biết cần làm gì | Thêm phạm vi, trạng thái kiểm soát, chủ sở hữu và thời hạn |
| Gộp gửi tin với đã rà soát | Đóng sớm dù chưa có người kiểm tra | Theo dõi trạng thái thông báo và rà soát riêng |
| Gửi mật khẩu hoặc bản ghi phiên vào chat | Mở rộng phạm vi lộ dữ liệu | Dùng tham chiếu bằng chứng có kiểm soát truy cập |
| Retry tạo nhiều hồ sơ trùng | Phân tán trách nhiệm và làm nhiễu cảnh báo | Dùng mã liên kết, phiên bản và khóa xử lý phù hợp |
| Dùng tài khoản break-glass để sửa cả lịch sử thông báo | Người sử dụng có thể che giấu hành động | Giới hạn quyền xóa/sửa và lưu dấu vết ở nơi có mức độc lập phù hợp |
| Chỉ kiểm tra hệ thống PAM | Không thấy đăng nhập trực tiếp ngoài PAM | Đối soát nguồn log hệ thống đích |
| Không thử kênh dự phòng | Quy trình thất bại trong đúng lúc khẩn cấp | Diễn tập lỗi danh tính, email hoặc cổng ticket |
| Rà soát kéo dài nhưng không cập nhật | Bên liên quan hiểu nhầm đã xử lý xong | Đặt chủ sở hữu và mốc cập nhật tiếp theo |

## 14. Kiểm thử quy trình thông báo

Kiểm thử nên dùng môi trường và tài khoản diễn tập phù hợp, tránh sử dụng credential sản xuất chỉ để thử gửi tin.

### 14.1. Các kịch bản cần kiểm tra

- Một lần sử dụng bình thường tạo đúng mã liên kết và đúng nhóm người nhận.
- Hai sự kiện kết thúc giống nhau không tạo hai hồ sơ rà soát độc lập.
- Một cập nhật mới về thu hồi thất bại không bị loại nhầm là sự kiện trùng.
- Sự kiện kết thúc đến trước sự kiện bắt đầu vẫn được giữ và đối soát đúng.
- Email hoặc chat bị lỗi thì thông báo được thử lại, chuyển cấp và lưu lịch sử.
- Không có người xác nhận thì người trực thay thế được giao việc.
- Kích hoạt quyền nhưng không có sự kiện kết thúc vẫn phát sinh công việc kiểm tra.
- Checkout credential nhưng thiếu log đăng nhập được báo là chưa xác minh, không tự đóng.
- Truy cập trực tiếp tài khoản break-glass được phát hiện qua nguồn log đích.
- Người không có quyền không xem được bản ghi phiên từ liên kết trong thông báo.
- Nội dung tự do chứa bí mật hoặc ký tự đánh dấu không làm lộ dữ liệu hay gây gửi diện rộng.
- Khi hệ thống danh tính chính gián đoạn, kênh dự phòng vẫn có thể tiếp nhận trách nhiệm theo thiết kế.

### 14.2. Bằng chứng một lần thử thành công

Một lần diễn tập cần để lại chuỗi liên kết giữa sự kiện nguồn, yêu cầu thông báo, kết quả gửi, xác nhận của người nhận, hồ sơ rà soát và kết quả đóng.

Đối với thử nghiệm lỗi, thành công không có nghĩa mọi lần gửi đều thành công. Thành công là lỗi được phát hiện, không mất hồ sơ, có người tiếp nhận và quy trình khôi phục hoạt động như dự kiến.

## 15. Chỉ số theo dõi

Các chỉ số nên phản ánh khả năng kiểm soát thay vì chỉ đếm số tin đã gửi.

- **Độ bao phủ thông báo:** số lần sử dụng đã có thông báo so với số lần sử dụng được phát hiện và đối soát trong kỳ.
- **Độ trễ tạo và gửi:** thời gian từ sự kiện đến lúc tạo yêu cầu và đến lúc kênh tiếp nhận; tách hai phần để thấy nguồn chậm.
- **Thời gian tiếp nhận:** từ lúc cần có người xử lý đến khi người có trách nhiệm nhận việc.
- **Tỷ lệ rà soát quá hạn:** hồ sơ chưa có kết luận khi đến hạn theo chính sách.
- **Số trường hợp chưa xác minh thu hồi:** quyền, phiên hoặc credential vẫn đang chờ kiểm tra.
- **Số lần sử dụng không ghép được danh tính:** chỉ ra khoảng trống quy trách nhiệm.
- **Tỷ lệ phải chuyển cấp:** giúp đánh giá lịch trực và định tuyến người nhận.
- **Thông báo thất bại chưa xử lý:** số công việc tồn đọng ở hàng đợi lỗi hoặc kênh dự phòng.

Mẫu số độ bao phủ không nên chỉ lấy từ chính hệ thống thông báo; cách đó không phát hiện lần sử dụng chưa được đưa vào luồng gửi. Cần so với tập sự kiện sử dụng đã đối soát.

Khi báo cáo độ trễ, nên xem cả các trường hợp chậm nhất hoặc phân vị phù hợp thay vì chỉ nhìn trung bình. Một số ít thông báo về quyền tồn dư bị chậm có thể đáng quan tâm hơn nhiều thông báo bình thường được gửi nhanh.

## 16. Bài tập tự thực hành

### Bài tập 1: Sửa một thông báo thiếu thông tin

Thông báo ban đầu:

> Đã dùng tài khoản khẩn cấp để sửa lỗi. Hệ thống đã chạy lại. Nhờ mọi người lưu ý.

Hãy bổ sung mã lần sử dụng, người thực hiện, phạm vi, thời gian, trạng thái thu hồi, bằng chứng và yêu cầu hành động. Nếu chưa biết token phát sinh đã được thu hồi hay chưa, phải thể hiện rõ điều chưa biết và giao người xử lý.

### Bài tập 2: Xử lý việc không có xác nhận

Một thông báo đã được dịch vụ email tiếp nhận nhưng không có người nhận việc sau thời hạn.

Hãy thiết kế nhánh xử lý có lịch trực thay thế, kênh dự phòng và lịch sử chuyển cấp. Giải thích tại sao gửi lại cùng một email liên tục chưa đủ để giải quyết vấn đề.

### Bài tập 3: Quyết định có được đóng hồ sơ hay không

Hồ sơ có các dữ kiện:

- Dịch vụ đã phục hồi.
- Phiên được PAM ghi nhận đã kết thúc.
- Mật khẩu đã luân chuyển.
- Có một lần đăng nhập trực tiếp chưa liên kết được với danh tính.
- Người sử dụng tự xác nhận mọi việc đã xong.

Chưa đủ điều kiện để kết luận đã hoàn tất rà soát. Cần làm rõ lần đăng nhập trực tiếp, đối soát phạm vi phiên và để người có trách nhiệm độc lập ghi kết luận. Nếu phải chấp nhận ngoại lệ, cần tuân theo thẩm quyền, thời hạn và cách theo dõi ngoại lệ của tổ chức.

## 17. Điểm cần ghi nhớ

Thông báo sau sử dụng break-glass phải làm cho một lần truy cập khẩn cấp trở thành hồ sơ có thể truy vết, có người chịu trách nhiệm và có điều kiện đóng rõ ràng.

Thông báo cần phản ánh trạng thái đã xác minh, kể cả những phần chưa hoàn tất. Việc gửi thành công, người nhận xác nhận và người rà soát kết luận là những mốc khác nhau. Khi gắn được các mốc đó với bằng chứng thu hồi quyền, tổ chức mới kiểm tra được rằng quyền đặc biệt đã được sử dụng đúng phạm vi và được xử lý đầy đủ sau tình huống khẩn cấp.
