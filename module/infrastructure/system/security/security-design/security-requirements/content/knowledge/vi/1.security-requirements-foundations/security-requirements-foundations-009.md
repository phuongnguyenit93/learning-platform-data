# Khi nào yêu cầu bảo mật cần định lượng

## 1. Từ mong muốn bảo mật đến điều kiện có thể nghiệm thu

Các câu như “thu hồi quyền nhanh chóng”, “ghi log đầy đủ” hay “khôi phục hệ thống kịp thời” thể hiện nhu cầu có thật, nhưng chưa cho biết điều kiện nào được coi là đạt. Người thiết kế, người kiểm thử và người vận hành có thể hiểu mỗi câu theo một cách khác nhau.

Định lượng giúp biến một phần những mong muốn đó thành giới hạn có thể đo, chẳng hạn thời gian tối đa để quyền bị thu hồi hết hiệu lực hoặc khoảng mất dữ liệu chấp nhận được khi phục hồi. Tuy vậy, thêm một con số chưa tự làm yêu cầu trở nên đúng, đủ hoặc hữu ích.

Trong chương **Nền tảng yêu cầu bảo mật**, vấn đề cần giải quyết là:

> Khi nào mức bảo vệ phụ thuộc vào một đại lượng, cần đặc tả đại lượng đó cùng cách đo và ngưỡng chấp nhận. Khi nghĩa vụ được xác định rõ bằng điều kiện cho phép hoặc cấm, có thể kiểm chứng trực tiếp mà không cần gắn thêm một tỷ lệ hay thời hạn tùy ý.

Bài học đặt việc định lượng trong chuỗi: **mục tiêu an toàn thông tin → mô hình đe dọa và rủi ro → yêu cầu cụ thể → quyết định kiến trúc → tiêu chí kiểm thử → bằng chứng vận hành**.

Các con số trong bài là **giả định phục vụ ví dụ**, không phải khuyến nghị mặc định hay mức bảo vệ phù hợp cho mọi hệ thống.

## 2. Phân biệt định lượng, cụ thể và có thể kiểm chứng

Ba đặc điểm này liên quan nhưng không đồng nhất.

| Đặc điểm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Cụ thể | Nêu rõ chủ thể, hành động, tài sản, phạm vi và điều kiện | Người dùng không có quyền phê duyệt không được chuyển hóa đơn sang trạng thái đã duyệt |
| Định lượng | Dùng một đại lượng có đơn vị, tập đếm hoặc quy tắc tính | Quyền phê duyệt bị thu hồi phải hết hiệu lực trong tối đa 60 giây |
| Có thể kiểm chứng | Có cách thu thập bằng chứng và quy tắc đánh giá | Thử phê duyệt bằng quyền đã thu hồi tại các thời điểm xác định và quan sát tác động nghiệp vụ |

### 2.1. Có thể kiểm chứng mà không cần một ngưỡng số riêng

Yêu cầu sau có thể kiểm thử:

> Với API đọc hóa đơn dành cho khách hàng, hệ thống phải từ chối trả nội dung hóa đơn nếu chủ thể không có quyền đọc hóa đơn đó trong tenant tương ứng.

Một **tenant** là phạm vi tổ chức khách hàng có dữ liệu và quyền truy cập riêng trong hệ thống dùng chung.

Tiêu chí chấp nhận có thể gồm người đúng quyền được đọc, người sai quyền bị từ chối và phản hồi từ chối không chứa nội dung hóa đơn. Không cần đổi yêu cầu thành “chặn 99% truy cập trái phép”. Một tỷ lệ như vậy có thể làm yếu nghĩa vụ phân quyền nếu bị hiểu là cho phép một phần truy cập sai quyền.

Nghĩa vụ áp dụng cho mọi trường hợp trong phạm vi không có nghĩa bộ kiểm thử hữu hạn đã chứng minh mọi tình huống đều an toàn. Cần phân biệt **phạm vi nghĩa vụ** với **phạm vi bằng chứng đã thu thập**.

### 2.2. Có con số nhưng vẫn chưa kiểm chứng được

“API phân quyền phải đáp ứng dưới 100 ms” còn nhiều khoảng trống:

- Đo từ khi nào đến khi nào?
- Áp dụng cho mọi yêu cầu hay một phân vị?
- Tính cả thời gian chờ mạng, cache và phụ thuộc hay không?
- Đo ở tải nào, với bao nhiêu chủ thể và chính sách?
- Yêu cầu bị lỗi hoặc hết thời gian chờ được tính thế nào?
- Hệ thống có được phép bỏ kiểm tra quyền để đạt thời gian đó không?

Một con số thiếu ngữ cảnh có thể tạo cảm giác chính xác nhưng không cho phép nghiệm thu nhất quán.

### 2.3. Từ ngữ định tính là tín hiệu cần làm rõ

| Từ ngữ | Điều có thể còn thiếu |
| --- | --- |
| Nhanh chóng, ngay lập tức | Mốc bắt đầu, mốc kết thúc, thời hạn và xử lý thao tác đang chạy |
| Đầy đủ | Tập sự kiện hoặc trường dữ liệu bắt buộc; cách xác định phần bị thiếu |
| Thường xuyên | Tần suất, thời điểm thực hiện và thời gian tối đa giữa hai lần |
| Mạnh, an toàn | Thuộc tính cần bảo vệ, kịch bản đe dọa và ràng buộc kỹ thuật cụ thể |
| Quy mô lớn | Số chủ thể, tài nguyên, tenant, tải và phân bố tải |
| Kịp thời | Thời hạn theo tác động nghiệp vụ và điểm bắt đầu tính thời gian |
| Độ tin cậy cao | Loại lỗi, giới hạn chấp nhận và cửa sổ đánh giá |

Không phải tất cả các từ này đều phải được thay bằng số. “Đầy đủ” có thể cần một danh mục sự kiện rõ ràng; “an toàn” có thể cần chính sách quyền cụ thể. Chọn loại đặc tả theo điều đang mơ hồ.

## 3. Những trường hợp cần định lượng

### 3.1. Rủi ro tăng theo thời gian phơi nhiễm

Nếu quyền đã thu hồi vẫn còn tác dụng trong một khoảng thời gian, kẻ sử dụng phiên cũ có thể tiếp tục thực hiện thao tác. Khoảng thời gian đó là một phần của mức rủi ro.

Các trường hợp thường cần giới hạn thời gian gồm:

- Thu hồi quyền hoặc phiên đã phát hành.
- Thời hạn dùng mã xác minh hoặc liên kết khôi phục.
- Độ cũ tối đa của dữ liệu quyền được lưu trong cache.
- Thời gian từ khi sự kiện bảo mật xảy ra đến khi được ghi nhận hoặc xử lý.
- Thời gian lưu giữ dữ liệu và thời điểm xóa theo chính sách đã xác định.

Cần biết giới hạn là tối đa cho từng trường hợp hay mục tiêu thống kê. “95% quyền thu hồi có hiệu lực trong 60 giây” không đồng nghĩa “không quyền nào còn hiệu lực sau 60 giây”.

### 3.2. Chính sách cho phép một lượng hoạt động trong một khoảng

Giới hạn tốc độ, hạn mức và chống lạm dụng phụ thuộc vào số lượng, đơn vị và cửa sổ thời gian.

Ví dụ, một yêu cầu hạn chế gửi mã xác minh cần làm rõ:

- Đếm yêu cầu gửi hay số mã đã gửi thành công?
- Đếm theo tài khoản, địa chỉ nhận, thiết bị, địa chỉ mạng hay kết hợp?
- Cửa sổ cố định, trượt hay cơ chế khác?
- Điều gì xảy ra ở lần vượt ngưỡng?
- Cách xử lý yêu cầu đồng thời và các nút dịch vụ?
- Người dùng hợp lệ có đường khôi phục phù hợp nào?

“Giới hạn theo IP” có thể không đủ khi nhiều người dùng chung một mạng hoặc khi nguồn yêu cầu phân tán. Chọn chiều đếm phải dựa trên hành vi đe dọa và ảnh hưởng tới người dùng.

### 3.3. Chất lượng bảo vệ phải duy trì dưới tải xác định

Một dịch vụ kiểm tra quyền hoạt động đúng với ít người dùng có thể bị nghẽn khi lượng yêu cầu tăng. Nếu điểm thực thi quyền trở thành nút thắt, nhóm phải định lượng năng lực và độ trễ để thiết kế phù hợp.

Những đại lượng liên quan có thể là:

- Số quyết định quyền mỗi giây ở tải xác định.
- Phân vị thời gian xử lý.
- Giới hạn hàng đợi và thời gian chờ.
- Số tenant, số chính sách, số quyền trên mỗi chủ thể.
- Mức tài nguyên vận hành trong điều kiện đã nêu.

Yêu cầu hiệu năng không được ngầm cho phép bỏ nghĩa vụ bảo mật. Nếu không đánh giá được quyền, hành vi phải theo chính sách lỗi đã đặc tả; một phép đo nhanh do bỏ kiểm tra không chứng minh hệ thống đạt.

### 3.4. Tổn thất và phục hồi có giới hạn chấp nhận

Nghiệp vụ thường cần trả lời: có thể mất tối đa bao nhiêu dữ liệu và dừng dịch vụ bao lâu?

- **RPO — Recovery Point Objective:** mục tiêu về điểm dữ liệu phục hồi, thường thể hiện giới hạn mất dữ liệu theo thời gian.
- **RTO — Recovery Time Objective:** mục tiêu về thời gian khôi phục dịch vụ hoặc chức năng trong phạm vi xác định.

Hai mục tiêu này cần số đo và kịch bản. “Có sao lưu” không trả lời được chúng.

Ví dụ, giả định nghiệp vụ chấp nhận RPO 15 phút và RTO 2 giờ cho sự cố mất một kho dữ liệu. Cần xác định dữ liệu, chức năng, điều kiện phụ thuộc và tiêu chí xác nhận phục hồi an toàn, không chỉ lúc tiến trình ứng dụng khởi động lại.

### 3.5. Một nghĩa vụ đã có nguồn quy định cụ thể

Hợp đồng, chính sách nội bộ hoặc quyết định quản trị có thể đặt thời gian lưu log, hạn xử lý hay yêu cầu về chu kỳ rà soát quyền.

Khi đó, đặc tả phải ghi:

- Nguồn và phiên bản nghĩa vụ.
- Phạm vi đối tượng và điều kiện áp dụng.
- Cách chuyển nghĩa vụ thành phép đo trong hệ thống.
- Người có thẩm quyền giải thích hoặc chấp thuận ngoại lệ.

Không suy ra một ngưỡng chung chỉ vì thấy nó xuất hiện ở một hệ thống khác. Không tự gán nghĩa vụ pháp lý khi chưa xác định nguồn áp dụng.

## 4. Khi nào không nên thêm số một cách máy móc?

### 4.1. Khi yêu cầu là một quy tắc quyền hoặc một điều cấm rõ ràng

Ví dụ:

- Không trả mật khẩu hoặc token truy cập trong phản hồi lỗi.
- Không cho quản trị viên tenant A quản lý thành viên tenant B.
- Không thực hiện thanh toán khi chưa có quyết định cho phép theo chính sách.
- Chỉ trả các trường được phép cho vai trò xem báo cáo.

Những yêu cầu này cần phạm vi và điều kiện rõ. Thêm “đúng 99,9% trường hợp” có thể biến một điều cấm thành mục tiêu thống kê sai ý định.

Có thể đếm số vi phạm phát hiện được để theo dõi, nhưng **chỉ số quan sát** không tự thay đổi nghĩa vụ phải tuân thủ.

### 4.2. Khi chưa xác định được tài sản và mối đe dọa

Đặt “khóa tài khoản sau 5 lần sai” trước khi hiểu kịch bản có thể tạo cơ chế dễ bị lợi dụng để gây gián đoạn cho người khác.

Trước hết cần xác định đang chống đoán mật khẩu, gửi mã hàng loạt hay chiếm tài khoản bằng thông tin bị lộ; mỗi tình huống có cách đo và biện pháp khác nhau. Một biện pháp cũng có thể gây tác động phụ cần được tính vào yêu cầu.

### 4.3. Khi đại lượng chỉ là chi tiết triển khai

“Đặt thời gian cache bằng 30 giây” là một quyết định kỹ thuật có thể giúp đáp ứng yêu cầu về độ cũ của quyền. Nó chưa chứng minh mọi đường sử dụng quyền đều hết hiệu lực đúng hạn.

Phân biệt:

> **Yêu cầu:** Sau thời hạn thu hồi đã xác định, máy chủ không được chấp nhận thao tác dựa trên quyền bị thu hồi.
>
> **Thiết kế có thể chọn:** Giới hạn cache, truyền sự kiện vô hiệu hóa, kiểm tra phiên bản quyền hoặc tra cứu trạng thái quyền phù hợp.

Nếu nguồn nghĩa vụ bắt buộc một cấu hình cụ thể, cấu hình ấy có thể được ghi thành ràng buộc. Nhưng vẫn cần kiểm chứng kết quả bảo vệ mà nó phục vụ.

### 4.4. Khi con số chỉ đo hoạt động làm việc

“Số buổi đào tạo”, “số lần quét” và “số bản sao lưu” có thể hữu ích cho việc quản lý quy trình. Riêng chúng chưa chứng minh nhân viên xử lý đúng tình huống, không còn lỗ hổng trong phạm vi quan tâm hoặc dữ liệu phục hồi được.

Chỉ số hoạt động nên được liên kết với nghĩa vụ và bằng chứng phù hợp. Không đổi tên số lần thực hiện thành mức an toàn đạt được.

## 5. Một yêu cầu định lượng cần những thành phần nào?

Có thể dùng mẫu:

> Trong **phạm vi và điều kiện** đã nêu, khi **sự kiện bắt đầu** xảy ra, **thành phần chịu trách nhiệm** phải đạt **kết quả bảo vệ**, với **đại lượng, đơn vị và ngưỡng** được xác định; việc đánh giá dùng **nguồn đo, cửa sổ và quy tắc xử lý lỗi** đã mô tả.

| Thành phần | Câu hỏi phải trả lời |
| --- | --- |
| Mã yêu cầu và nguồn | Yêu cầu giảm rủi ro nào hoặc xuất phát từ nghĩa vụ nào? |
| Phạm vi | Áp dụng cho chức năng, dữ liệu, vai trò, tenant và môi trường nào? |
| Kết quả bảo vệ | Hành vi nào phải được phép, bị chặn hoặc được khôi phục? |
| Đại lượng | Thời gian, số lần, tỷ lệ, độ cũ dữ liệu hay năng lực xử lý? |
| Đơn vị | ms, giây, yêu cầu/phút, sự kiện hoặc tỷ lệ theo tập nào? |
| Mốc đo | Bắt đầu và kết thúc tại sự kiện quan sát nào? |
| Ngưỡng và toán tử | Nhỏ hơn, không vượt quá, ít nhất hay nằm trong khoảng nào? |
| Điều kiện đo | Tải, dữ liệu, kiến trúc, trạng thái cache và kịch bản lỗi nào? |
| Cửa sổ và thống kê | Từng thao tác, khoảng 5 phút, một đợt kiểm thử hay một chu kỳ vận hành? |
| Nguồn bằng chứng | Dữ liệu từ máy chủ, công cụ kiểm thử, kho sự kiện hay diễn tập? |
| Quy tắc thiếu dữ liệu | Thiếu mẫu, sai đồng hồ hoặc mất sự kiện được phân loại thế nào? |
| Trách nhiệm | Ai triển khai, đánh giá kết quả và quyết định ngoại lệ? |

Không nhất thiết nhồi toàn bộ thông tin vào một câu. Có thể tách nội dung yêu cầu, điều kiện phép đo và tiêu chí chấp nhận thành các mục liên kết bằng mã.

### 5.1. Ranh giới phải được diễn đạt chính xác

“Tối đa 60 giây” thường được hiểu là không vượt quá 60 giây. “Dưới 60 giây” có ranh giới khác.

Với số lần thử, cần nói rõ lần thứ N vẫn được xử lý hay đã bị hạn chế. Với thời gian hết hạn, cần quy định yêu cầu được đánh giá theo thời điểm máy chủ tiếp nhận, thời điểm quyết định hay thời điểm tạo tác động.

Kiểm thử nên bao gồm giá trị trước, tại và sau ranh giới trong khả năng đo của môi trường. Nếu đồng hồ hoặc công cụ có sai số, phải ghi nhận sai số và thiết kế biên đo phù hợp; không âm thầm cộng một khoảng dung sai lớn để đổi kết luận.

### 5.2. Tính khả thi của phép đo là một phần của thiết kế

Một yêu cầu hết hiệu lực quyền trong 60 giây khó đánh giá nếu hệ thống không có mốc ghi nhận thu hồi thành công, không xác định được phiên bản quyền và không truy vết quyết định cho phép.

Nhóm cần thiết kế điểm quan sát từ sớm. Khi đo thời lượng trong một tiến trình, ưu tiên nguồn thời gian phù hợp để tránh sai lệch do đồng hồ lịch bị điều chỉnh. Khi đo qua nhiều máy, phải xét đồng bộ thời gian, sai số và cách tương quan các sự kiện.

Thời gian do máy khách tự khai báo không nên là căn cứ duy nhất cho phép đo một nghĩa vụ bảo mật ở máy chủ.

## 6. Ví dụ đầy đủ: định lượng thời gian thu hồi quyền

### 6.1. Bối cảnh và rủi ro

Dịch vụ hóa đơn cho phép người có quyền `invoice.approve` phê duyệt hóa đơn trong tenant được cấp quyền.

Rủi ro: sau khi quyền bị thu hồi, phiên đang tồn tại hoặc cache quyền cũ vẫn cho phép người đó phê duyệt. Thời gian quyền cũ còn được chấp nhận là cửa sổ phơi nhiễm cần giới hạn.

### 6.2. Yêu cầu về hành vi và yêu cầu về thời gian

**SR-AUTHZ-01 — Kiểm tra quyền phê duyệt**

Trước khi tạo tác động phê duyệt, máy chủ phải xác lập rằng chủ thể có quyền phê duyệt hóa đơn đích trong tenant tương ứng. Nếu không có quyền hoặc không xác định được quyền, máy chủ phải từ chối và không chuyển trạng thái hóa đơn sang đã duyệt.

**SR-REVOKE-01 — Giới hạn hiệu lực của quyền cũ**

Giả định nghiệp vụ chấp nhận giới hạn 60 giây. Với mọi yêu cầu phê duyệt được máy chủ tiếp nhận từ thời điểm `t0 + 60 giây` trở đi, máy chủ không được cho phép dựa trên quyền đã bị thu hồi tại `t0`.

Trong đó:

- `t0` là lúc thay đổi thu hồi được lưu bền vững ở nguồn quyền có thẩm quyền và được xác nhận thành công.
- Phạm vi gồm phiên đã phát hành, cache quyền và các bản sao dữ liệu quyền dùng cho API phê duyệt.
- Quyền được cấp lại hợp lệ sau thu hồi phải được phân biệt bằng lịch sử hoặc phiên bản thay đổi.
- Yêu cầu được tiếp nhận trước mốc trên nhưng vẫn đang chạy cần chính sách riêng về thời điểm kiểm tra lại trước khi ghi nhận phê duyệt.
- Ví dụ này chọn kiểm tra lại quyền trước khi tạo tác động đối với yêu cầu đang chạy qua mốc hết hiệu lực.
- Khi không xác lập được quyền hợp lệ, không được sử dụng quyền cũ quá giới hạn để tiếp tục phê duyệt.

Hai yêu cầu liên kết với nhau: một yêu cầu nêu nghĩa vụ phân quyền, một yêu cầu giới hạn độ trễ của thay đổi quyền.

### 6.3. Hệ quả đối với kiến trúc

Thiết kế cần xét nhiều đường lan truyền quyền:

```text
Nguồn quyền có thẩm quyền
  -> thông báo hoặc đồng bộ thay đổi
  -> bản sao / cache quyền
  -> điểm quyết định quyền
  -> điểm tạo tác động phê duyệt
```

Chỉ đặt thời gian sống cache bằng 60 giây có thể chưa đủ nếu còn độ trễ đồng bộ trước lúc cache được nạp, cache trung gian khác hoặc đường kiểm tra bỏ qua nguồn đã cập nhật.

Phải đánh giá giới hạn từ đầu đến cuối. Không cộng các phân vị p95 của từng bước rồi coi kết quả là giới hạn tối đa cho toàn bộ đường đi.

### 6.4. Tiêu chí kiểm chứng

```text
Chuẩn bị:
  Chủ thể U đang có quyền phê duyệt trong tenant T.
  U có phiên đang hoạt động.
  Cache tại các nút cần kiểm tra đã chứa quyền cũ.
  Các hóa đơn thử nghiệm độc lập và đủ điều kiện phê duyệt.

Thực hiện:
  Thu hồi quyền, ghi lại t0 và phiên bản thay đổi.
  Gửi yêu cầu phê duyệt qua các nút thuộc phạm vi.
  Quan sát trước, tại và sau ranh giới bằng nguồn thời gian đã thống nhất.
  Lặp lại với kịch bản chậm đồng bộ hoặc mất phụ thuộc đã định.

Đánh giá:
  Yêu cầu tiếp nhận từ t0 + 60 giây không được tạo tác động
  dựa trên quyền đã thu hồi.
  Không chỉ kiểm tra mã lỗi; phải đối chiếu trạng thái hóa đơn.
  Kết quả phải phân biệt quyền cũ với quyền được cấp lại hợp lệ.
```

Việc kiểm tra trước thời hạn giúp quan sát quá trình hội tụ; yêu cầu này không bắt buộc hệ thống phải tiếp tục cho phép đến sát thời hạn. Từ chối quyền cũ sớm hơn có thể vẫn đáp ứng nghĩa vụ.

Một lần thử thành công không chứng minh mọi nút và mọi điều kiện đều đạt. Báo cáo phải nêu phiên bản, cấu hình, dữ liệu, nút và kịch bản thực sự được kiểm chứng.

## 7. Chọn đúng loại số đo và tránh kết luận vượt quá dữ liệu

### 7.1. Giới hạn tối đa khác phân vị

Giả sử có 10.000 phép đo thời gian đánh giá quyền. Yêu cầu “p95 không vượt quá 50 ms” nói về phân bố thời gian: ít nhất khoảng 95% mẫu theo cách tính phân vị đã chọn nằm trong ngưỡng đó. Nó không giới hạn thời gian của mọi mẫu còn lại.

Nếu một nghĩa vụ bảo vệ yêu cầu quyền cũ tuyệt đối không còn được sử dụng sau một thời hạn, một mục tiêu p95 không thể thay thế nghĩa vụ ấy.

Nên tách rõ:

- **Bất biến bảo mật:** không cho phép thao tác khi không có quyền hợp lệ.
- **Mục tiêu chất lượng:** thời gian đánh giá quyền đạt phân vị đã xác định trong điều kiện tải cụ thể.
- **Giới hạn chờ và hành vi lỗi:** hết thời gian chờ thì hệ thống xử lý thế nào mà vẫn giữ nghĩa vụ bảo vệ.

### 7.2. Không dùng trung bình để che giấu phần đuôi

Thời gian trung bình thấp vẫn có thể đi cùng một số yêu cầu rất chậm. Nếu tác động nghiệp vụ nằm ở các trường hợp chậm đó, cần xem phân vị cao hoặc giới hạn phù hợp, cùng tỷ lệ lỗi.

Một đặc tả hiệu năng minh họa:

> Trong đợt thử tải ổn định 30 phút, với 200 yêu cầu đánh giá quyền mỗi giây và bộ dữ liệu đã mô tả, p95 thời gian đánh giá quyền tại máy chủ không vượt quá 50 ms. Đồng thời, số lỗi đánh giá quyền và yêu cầu hết thời gian chờ phải được báo cáo riêng theo ngưỡng chấp nhận đã phê duyệt. Mọi quyết định trả về vẫn phải tuân thủ chính sách quyền.

Phép đo cần định nghĩa điểm bắt đầu/kết thúc, thuật toán tính phân vị, trạng thái cache, phân bố yêu cầu và loại lỗi. Các con số trên chỉ minh họa cấu trúc, chưa tự tạo thành đặc tả nghiệm thu đầy đủ.

### 7.3. Tỷ lệ cần tử số, mẫu số và quy tắc phân loại

Một tỷ lệ thường có dạng:

```text
Tỷ lệ = số phần tử đáp ứng điều kiện / số phần tử đủ điều kiện
```

Tuy nhiên, hai nhóm có thể cho kết quả khác nhau nếu chọn mẫu số khác nhau.

Ví dụ, tỷ lệ sự kiện kiểm toán xuất hiện đúng hạn cần làm rõ:

- Mẫu số là các thao tác bắt buộc phải có sự kiện trong cửa sổ đo.
- Tử số là các thao tác đó có sự kiện hợp lệ xuất hiện trước thời hạn tương ứng.
- Thao tác đang chờ hết thời hạn phải được xử lý theo quy tắc đã nêu.
- Sự kiện trùng không được làm tăng số thao tác đã được ghi nhận.
- Thao tác đã thành công nhưng mất dấu vết không được âm thầm loại khỏi mẫu số.
- Không có thao tác đủ điều kiện thì báo “không có dữ liệu để tính”, không tự coi là bằng chứng đạt.

Chỉ đếm các sự kiện đã tới kho log rồi tính “100% đã nhận được” không phát hiện được những sự kiện chưa từng tới.

### 7.4. Cửa sổ tổng hợp có thể che khuất sự cố cục bộ

Tỷ lệ đạt cao trên toàn hệ thống có thể che một tenant hoặc một vùng triển khai bị lỗi liên tục.

Cần chọn mức phân tách theo rủi ro: theo chức năng nhạy cảm, tenant, vùng hoặc loại chủ thể khi phù hợp. Cũng cần đủ dữ liệu để diễn giải; tỷ lệ từ vài mẫu không có cùng sức nặng với một tập lớn và đa dạng.

Không chọn cửa sổ chỉ vì nó làm số liệu đẹp. Cửa sổ cần phản ánh thời gian tác động mà nghiệp vụ quan tâm.

### 7.5. Thiếu bằng chứng không phải bằng chứng đạt

Nếu mất dữ liệu đo, đồng hồ sai hoặc không ghép được sự kiện, kết quả nên được phân loại là chưa đủ bằng chứng hoặc không hợp lệ theo quy tắc đã định.

“Không quan sát thấy vi phạm” chỉ có ý nghĩa trong phạm vi khả năng quan sát thực tế. Nó không đồng nghĩa “không có vi phạm”.

## 8. Ví dụ về xác thực và chống lạm dụng

Một yêu cầu xác thực có phần hành vi:

> Không tạo phiên sử dụng được cho khu vực quản trị trước khi hoàn tất các bước xác thực bắt buộc.

Yêu cầu này có thể kiểm chứng bằng việc thử truy cập trước và sau từng bước; không cần một tỷ lệ cho phép bỏ qua bước xác thực.

Một yêu cầu chống gửi mã xác minh lại có thể cần định lượng. Giả sử nhóm chọn một giới hạn minh họa:

> Với mỗi định danh nhận mã đã được chuẩn hóa, dịch vụ chỉ được chấp nhận tối đa 5 yêu cầu gửi mã trong một cửa sổ trượt 5 phút. Yêu cầu vượt ngưỡng không được tạo thêm công việc gửi mã.

Để có thể thực hiện và kiểm tra, còn phải định nghĩa:

- “Chấp nhận” là ghi nhận công việc gửi tại máy chủ, không phải người nhận đã nhận được tin.
- Cửa sổ được tính theo thời điểm máy chủ chấp nhận yêu cầu.
- Sự kiện ở đúng ranh giới cửa sổ được đưa vào hay loại ra theo quy tắc thống nhất.
- Giới hạn áp dụng trên toàn các nút phục vụ cùng định danh.
- Yêu cầu đồng thời không được vượt ngưỡng do kiểm tra và cập nhật bộ đếm không nhất quán.
- Gửi lại cùng một yêu cầu có định danh chống lặp được tính thế nào.
- Cách phản hồi không làm lộ không cần thiết việc một tài khoản tồn tại.
- Cách xử lý khi thành phần đếm không hoạt động và khi người dùng hợp lệ cần khôi phục truy cập.

Ngưỡng theo định danh nhận mã có thể cần phối hợp với giới hạn ở chiều khác để giảm lạm dụng phân tán. Quyết định đó phải xuất phát từ mô hình đe dọa; không có một con số duy nhất bảo đảm chống lạm dụng cho mọi dịch vụ.

Kiểm thử nên có trường hợp dưới ngưỡng, đúng ngưỡng, vượt ngưỡng, hết cửa sổ và gửi đồng thời qua nhiều nút. Cũng phải kiểm tra tác động thực tế: trả lỗi nhưng vẫn tạo công việc gửi mã là chưa đáp ứng nghĩa vụ.

## 9. Ví dụ về dữ liệu và logging: số lượng không thay thế nội dung

### 9.1. Nghĩa vụ nội dung trước, đại lượng sau

Một yêu cầu bảo vệ log có thể gồm:

> Mỗi thay đổi quyền quản trị thành công phải có sự kiện kiểm toán chứa chủ thể thực hiện, đối tượng, loại thay đổi, thời gian, kết quả và mã tương quan. Sự kiện không được chứa mật khẩu hoặc token truy cập.

Hai phần này xác định tập sự kiện, trường bắt buộc và dữ liệu bị cấm. “Ghi càng nhiều log càng tốt” không phải một đặc tả phù hợp vì có thể tăng rò rỉ dữ liệu và vẫn thiếu sự kiện cần điều tra.

Sau đó mới đặt các đại lượng cần thiết, chẳng hạn:

- Thời gian tối đa từ lúc thay đổi được ghi nhận đến lúc dấu vết được lưu bền vững.
- Thời gian sự kiện phải có thể truy vấn tại kho kiểm toán.
- Thời gian lưu và thời hạn xóa theo chính sách đã xác định.
- Dung lượng đệm và hành vi khi chưa gửi được sự kiện.

Phải phân biệt **đã lưu bền vững** với **đã có thể tìm kiếm**. Hệ thống có thể bảo đảm không mất sự kiện nhưng cần thêm thời gian để lập chỉ mục.

### 9.2. Tách nghĩa vụ bắt buộc khỏi mục tiêu vận hành

Ví dụ, giả sử có hai yêu cầu liên kết:

- **SR-AUD-01:** Không xác nhận thay đổi quyền thành công nếu chưa có dấu vết kiểm toán được lưu bền vững theo cơ chế nhất quán đã thiết kế.
- **SR-AUD-LAT-01:** Trong cửa sổ đánh giá, ít nhất 99,9% thao tác đủ điều kiện phải có sự kiện truy vấn được ở kho kiểm toán trong 10 giây kể từ lúc thay đổi được ghi nhận.

Mục tiêu 99,9% trong ví dụ chỉ nói về **độ trễ truy vấn được**. Nó không cho phép bỏ dấu vết của phần còn lại. Cần thêm quy tắc xử lý sự kiện đến muộn, cảnh báo và kiểm tra đối soát.

Nếu chỉ viết “99,9% sự kiện được ghi”, nhóm có thể hiểu thành một mức mất dữ liệu được cho phép, khác với nghĩa vụ ban đầu.

### 9.3. Kiểm chứng tính đầy đủ cần nguồn đối chiếu phù hợp

Để biết thao tác nào thiếu sự kiện, cần một nguồn xác định tập thao tác bắt buộc có dấu vết, chẳng hạn dữ liệu nghiệp vụ đã ghi nhận hoặc sổ sự kiện bền vững phù hợp với thiết kế.

Nếu cả tập thao tác và sự kiện đều chỉ được suy ra từ cùng một luồng log có thể mất dữ liệu, phép đo có thể bỏ sót mất mát ở nguồn. Thiết kế đối soát phải xét giới hạn đó.

Kiểm thử cần cả điều kiện bình thường và tình huống lỗi đã chọn: kho nhận log gián đoạn, gửi lại sự kiện, ứng dụng dừng ở thời điểm nhạy cảm hoặc bộ đệm gần đầy. Bằng chứng phải cho thấy nghĩa vụ nào còn được bảo đảm ở từng tình huống.

## 10. Ví dụ về phục hồi: đo kết quả nghiệp vụ

Giả định một dịch vụ hóa đơn có:

- RPO 15 phút.
- RTO 2 giờ.
- Kịch bản áp dụng là mất kho dữ liệu chính, còn các phụ thuộc được nêu trong kế hoạch phục hồi.
- Phạm vi phục hồi gồm dữ liệu hóa đơn, trạng thái quyền liên quan và cấu hình cần cho luồng đọc/phê duyệt.

### 10.1. Định nghĩa mốc RTO

Cần nêu mốc bắt đầu và kết thúc rõ ràng. Ví dụ này chọn:

- Bắt đầu khi dịch vụ mất khả năng phục vụ phạm vi nghiệp vụ đã định.
- Kết thúc khi các chức năng trong phạm vi đã hoạt động và vượt qua điều kiện xác minh phục hồi.

Nếu chỉ bắt đầu tính từ lúc người vận hành nhấn nút phục hồi, khoảng phát hiện và huy động trước đó có thể bị che khỏi phép đo. Có thể đo thời gian thao tác kỹ thuật riêng, nhưng không thay tên nó thành toàn bộ thời gian gián đoạn.

Điều kiện kết thúc cần gồm kiểm tra dữ liệu và quyền. Một ứng dụng trả được trang chủ nhưng cho phép quyền đã bị thu hồi hoạt động trở lại chưa đáp ứng điều kiện phục hồi an toàn của ví dụ.

### 10.2. Định nghĩa mốc RPO

RPO không chỉ là “lịch sao lưu cách nhau 15 phút”. Cần xác minh điểm dữ liệu thực sự có thể khôi phục trong kịch bản.

Ví dụ, khi dữ liệu được ghi liên tục và có thể nhận diện điểm phục hồi nhất quán:

```text
Khoảng mất dữ liệu theo thời gian
  = thời điểm sự cố
    - mốc dữ liệu nhất quán cuối cùng thực sự khôi phục được
```

Cách đánh giá phải xét dữ liệu đã được hệ thống xác nhận ghi nhận và phạm vi nhất quán giữa các thành phần. Với hệ thống không có một mốc thời gian chung đáng tin cậy, cần cách đối chiếu giao dịch hoặc điểm tiến triển dữ liệu phù hợp.

Ngoài thời gian, có thể cần giới hạn số giao dịch hoặc loại dữ liệu được phép mất. Mười phút mất dữ liệu vào giờ cao điểm và giờ ít tải có thể có tác động khác nhau.

### 10.3. Bằng chứng nghiệm thu

Một đợt diễn tập nên ghi lại:

1. Kịch bản và trạng thái ban đầu.
2. Thời điểm gián đoạn cùng cách xác định.
3. Các bản sao và khóa thực sự được dùng.
4. Điểm dữ liệu khôi phục được.
5. Thời điểm chức năng nghiệp vụ đáp ứng điều kiện mở lại.
6. Kết quả kiểm tra tính nhất quán, quyền và dữ liệu.
7. Phụ thuộc không có sẵn hoặc giả định chưa được thử.

Một bản sao lưu tồn tại hoặc một lần khôi phục thành công trên bộ dữ liệu nhỏ chưa tự chứng minh đáp ứng các ngưỡng ở quy mô vận hành.

## 11. Chọn ngưỡng dựa trên rủi ro và khả năng thực hiện

Để chọn một ngưỡng có căn cứ, có thể đi theo trình tự sau.

### Bước 1: Nêu tổn thất cần giới hạn

Ví dụ: nhân sự đã bị thu hồi quyền còn có thể phê duyệt hóa đơn; log tới muộn làm chậm điều tra; mất dữ liệu sau sự cố khiến không đối soát được giao dịch.

Nếu chưa nói rõ điều gì xấu xảy ra, việc chọn số dễ trở thành sao chép cấu hình.

### Bước 2: Xác định mức chấp nhận của nghiệp vụ

Chủ sở hữu nghiệp vụ và người chịu trách nhiệm rủi ro cần thống nhất giới hạn có thể chấp nhận. Với một số nghĩa vụ, không được thay điều cấm bằng tỷ lệ vi phạm.

Cần tách điều kiện bình thường và kịch bản sự cố. Nếu mức bảo vệ thay đổi khi suy giảm, phải mô tả phạm vi và hành vi suy giảm rõ ràng, thay vì để hệ thống tự chọn.

### Bước 3: Đo hiện trạng để đánh giá khoảng cách

Số liệu hiện tại giúp biết cần thay đổi gì, nhưng không tự quyết định ngưỡng nên là bao nhiêu.

Nếu quyền cũ hiện còn tác dụng 10 phút, không vì thế mà 10 phút trở thành mức chấp nhận. Ngược lại, yêu cầu 1 giây không có căn cứ cũng có thể tạo chi phí lớn mà chưa giảm đúng rủi ro quan tâm.

### Bước 4: Đánh giá thiết kế từ đầu đến cuối

Với thu hồi quyền, xét nguồn quyền, đồng bộ, cache, phiên và điểm tạo tác động. Với logging, xét việc tạo sự kiện, lưu bền vững, vận chuyển và khả năng truy vấn. Với phục hồi, xét dữ liệu, khóa, quyền và các phụ thuộc.

Nếu phân bổ ngân sách thời gian cho các bước, phải làm rõ ngân sách là giới hạn thiết kế hay mục tiêu thống kê. Một tổng độ trễ cần được kiểm chứng trực tiếp trong điều kiện áp dụng.

### Bước 5: Thống nhất phép đo trước khi nghiệm thu

Chọn nguồn dữ liệu, mốc đo, tải, cửa sổ, quy tắc tính và điều kiện lỗi. Bảo đảm kết quả có thể tái hiện đủ để các nhóm đưa ra cùng một kết luận.

Không thay cách lấy mẫu hoặc loại các mẫu lỗi sau khi đã thấy kết quả chỉ để làm yêu cầu có vẻ đạt.

### Bước 6: Ghi quyết định và xem xét khi bối cảnh thay đổi

Lưu lý do chọn ngưỡng, người chịu trách nhiệm và giả định. Khi tải, kiến trúc, dữ liệu hoặc mô hình đe dọa thay đổi, kiểm tra lại mức phù hợp.

Nếu chưa đáp ứng, ghi rõ phần thiếu và phương án xử lý. Ngoại lệ cần có phạm vi, thời hạn và quyết định của người có thẩm quyền; không chỉ giảm ngưỡng trong báo cáo.

## 12. Liên kết yêu cầu định lượng với thiết kế và kiểm thử

| Rủi ro | Nghĩa vụ cần giữ | Phần cần định lượng | Quyết định kiến trúc liên quan | Bằng chứng |
| --- | --- | --- | --- | --- |
| Sử dụng quyền cũ | Không cho phê duyệt bằng quyền đã hết hiệu lực | Thời gian lan truyền thu hồi | Đồng bộ quyền, cache, phiên, điểm kiểm tra | Kiểm thử theo mốc thu hồi trên các đường thực thi |
| Lạm dụng gửi mã | Không tạo công việc gửi vượt chính sách | Số lần, chiều đếm, cửa sổ | Bộ đếm, xử lý đồng thời, chống lặp | Thử tại ranh giới và qua nhiều nút |
| Thiếu dấu vết điều tra | Có dấu vết hợp lệ cho thao tác bắt buộc | Độ trễ, thời gian lưu, khả năng truy vấn | Lưu bền vững, vận chuyển, đối soát | So sánh thao tác gốc với sự kiện nhận được |
| Lộ bí mật qua log | Không ghi các loại bí mật bị cấm | Có thể cần thời hạn lưu/xóa liên quan | Chọn trường, lọc dữ liệu, kiểm soát truy cập | Kiểm tra đầu ra bằng dữ liệu thử có chứa bí mật |
| Mất dữ liệu và gián đoạn | Phục hồi đúng dữ liệu và quyền trong phạm vi | RPO, RTO, quy mô dữ liệu | Sao lưu, quản lý khóa, quy trình mở lại | Diễn tập phục hồi và đối chiếu dữ liệu |

Một yêu cầu có thể cần nhiều loại bằng chứng. Kiểm thử hiệu năng không thay thế kiểm thử quyền; kiểm tra cấu hình không thay thế diễn tập phục hồi; không có vi phạm trong log không chứng minh các sự kiện bắt buộc đều được ghi.

Kết quả nên được ghi theo từng yêu cầu: đạt, không đạt, chưa đủ bằng chứng hoặc có ngoại lệ được chấp thuận. Tránh một nhãn “đã bảo mật” chung cho cả hệ thống.

## 13. Các lỗi thường gặp khi định lượng

| Cách viết hoặc cách đo | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Thu hồi ngay lập tức” | Không rõ thời hạn và mốc tính | Định nghĩa sự kiện thu hồi, giới hạn thời gian và xử lý yêu cầu đang chạy |
| “Chặn 99% truy cập sai quyền” | Có thể cho phép vi phạm chính sách phân quyền | Giữ nghĩa vụ từ chối trong phạm vi; dùng tỷ lệ để mô tả bằng chứng đúng vai trò |
| “Độ trễ trung bình dưới 50 ms” | Có thể che các yêu cầu rất chậm | Chọn thống kê phù hợp, nêu tải và báo tỷ lệ lỗi |
| “p95 tốt nên thời gian tối đa đạt” | Nhầm mục tiêu thống kê với giới hạn mọi trường hợp | Đặc tả riêng từng loại nghĩa vụ |
| “Đạt hiệu năng vì đã loại timeout” | Bỏ phần thất bại khỏi kết luận tổng thể | Báo đầy đủ lỗi, timeout và quy tắc tính |
| “Ghi 100% log đã nhận” | Mẫu số không chứa các sự kiện bị mất trước khi nhận | Đối chiếu với tập thao tác bắt buộc tạo sự kiện |
| “Không có mẫu nên tỷ lệ đạt 100%” | Không có bằng chứng thực hiện | Báo không có dữ liệu và bổ sung phép kiểm chứng |
| “Sao lưu 15 phút/lần nên RPO 15 phút” | Chưa xác minh bản sao thực sự dùng được | Phục hồi thử và xác định điểm dữ liệu khôi phục |
| “Cache 60 giây nên thu hồi trong 60 giây” | Bỏ qua độ trễ và đường sử dụng khác | Đánh giá toàn bộ luồng từ thu hồi tới tạo tác động |
| “Số vi phạm quan sát bằng 0 nên tuyệt đối an toàn” | Suy rộng quá mức quan sát | Nêu giới hạn của dữ liệu, kiểm thử và phiên bản được đánh giá |

## 14. Bài tập vận dụng

### Bài 1: Chọn phần cần định lượng

Xét các phát biểu:

1. Người dùng không được đọc dữ liệu tenant khác khi không có quyền.
2. Quyền quản trị phải được thu hồi nhanh.
3. Không đưa token truy cập vào log.
4. Dịch vụ phải phục hồi kịp thời sau sự cố mất kho dữ liệu.
5. Log phải đầy đủ.

**Gợi ý:**

1. Cần chính sách và phạm vi truy cập rõ; không cần thêm tỷ lệ cho phép vi phạm.
2. Cần thời hạn, mốc bắt đầu/kết thúc và phạm vi phiên/cache.
3. Cần xác định loại token và các đường ghi log; không biến điều cấm thành tỷ lệ.
4. Cần kịch bản, RTO, RPO và điều kiện phục hồi an toàn.
5. Trước hết cần tập sự kiện và trường bắt buộc; sau đó xác định độ trễ, lưu giữ hoặc tỷ lệ truy vấn đúng hạn nếu nghiệp vụ cần.

### Bài 2: Bổ sung điều kiện cho một con số

Câu ban đầu:

> “Kiểm tra quyền không quá 50 ms.”

Hãy đặt câu hỏi về điểm đo, tải, phân bố dữ liệu, cache, thống kê, cửa sổ, lỗi và hành vi khi không đánh giá được quyền.

Một cách viết tốt hơn sẽ tách:

- Nghĩa vụ luôn có quyết định quyền hợp lệ trước thao tác.
- Mục tiêu độ trễ với điều kiện đo và cách tính cụ thể.
- Quy tắc timeout và suy giảm.
- Bằng chứng để đánh giá cả tính đúng và chất lượng.

Chỉ đổi câu thành “p95 không quá 50 ms” vẫn chưa trả lời đủ các câu hỏi còn lại.

### Bài 3: Phát hiện mẫu số sai

Một báo cáo nói: “Trong hôm nay, 100% sự kiện đã tới kho kiểm toán đều được lưu, nên mọi thao tác thay đổi quyền đều có dấu vết.”

**Đánh giá:** kết luận vượt quá phép đo. Báo cáo chưa biết số thao tác bắt buộc tạo sự kiện và chưa phát hiện sự kiện mất trước khi tới kho. Cần nguồn đối chiếu phù hợp, mã tương quan và quy tắc xử lý trùng/thiếu.

### Bài 4: Xác định kết luận được phép rút ra

Một phép thử cho thấy 50 lần thu hồi quyền đều hết hiệu lực trong 60 giây trên một nút.

**Kết luận phù hợp:** các trường hợp đã thử đáp ứng tiêu chí trong điều kiện của phép thử.

**Việc còn cần xác định:** các nút khác, độ trễ đồng bộ, phiên cũ, yêu cầu đang chạy, tình huống lỗi và mức đại diện của dữ liệu. Không suy ra ngay rằng mọi lần thu hồi ở mọi điều kiện đều đạt.

## 15. Câu hỏi trước khi chốt một yêu cầu

1. Nghĩa vụ bảo vệ và tình huống đe dọa đã rõ chưa?
2. Mức rủi ro có phụ thuộc vào thời gian, số lượng, tỷ lệ hoặc quy mô không?
3. Có đang thêm số vào một điều cấm vốn đã kiểm chứng được không?
4. Đại lượng, đơn vị, mốc đo và toán tử ngưỡng đã thống nhất chưa?
5. Nếu dùng tỷ lệ, tử số, mẫu số và dữ liệu thiếu được xử lý thế nào?
6. Nếu dùng phân vị, phần đuôi và lỗi có được báo cáo đúng vai trò không?
7. Điều kiện tải, dữ liệu, lỗi và phạm vi kiến trúc có đại diện cho mục đích kiểm chứng không?
8. Ngưỡng có căn cứ từ rủi ro, nghiệp vụ hoặc nghĩa vụ áp dụng không?
9. Thiết kế có tạo được bằng chứng cần thiết mà vẫn bảo vệ dữ liệu không?
10. Ai chịu trách nhiệm khi yêu cầu chưa đạt hoặc bối cảnh thay đổi?

Định lượng hữu ích khi nó làm rõ mức bảo vệ cần đạt và giúp phân biệt đạt với chưa đạt. Một đặc tả tốt giữ được nghĩa vụ bảo mật, chọn đúng đại lượng, giải thích ngưỡng và gắn phép đo với điều kiện thực tế của hệ thống.
