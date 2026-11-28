# Fail secure

## 1. Fail secure là gì?

**Fail secure** là nguyên tắc yêu cầu hệ thống duy trì các điều kiện bảo vệ đã xác định khi một thành phần, phụ thuộc hoặc bước xử lý bị lỗi. Lỗi không được tự biến thành quyền truy cập, làm mất ranh giới dữ liệu hoặc cho phép hoàn tất hành động nhạy cảm ngoài chính sách.

Ví dụ, một API phải kiểm tra quyền trước khi cấp quyền đọc tài liệu. Nếu dịch vụ phân quyền không phản hồi, API chưa có căn cứ để cho phép cấp quyền. Hành vi fail secure trong tình huống đó là không thực hiện việc cấp quyền, đồng thời phản hồi và ghi nhận lỗi theo hợp đồng. Việc người dùng đã đăng nhập không thay thế quyết định còn thiếu.

Trạng thái bảo vệ phải được xác định cho từng hành động. Với đọc tài liệu, đó có thể là không trả nội dung khi chưa xác lập được quyền. Với tác vụ xuất dữ liệu, đó có thể là giữ tệp ở vùng riêng tư và chưa công bố. Với thay đổi quyền, đó có thể là không ghi thay đổi mới khi điều kiện phê duyệt chưa được xác minh.

Fail secure không đòi hỏi mọi lỗi đều làm toàn bộ hệ thống dừng. Các chức năng vẫn có thể hoạt động trong phạm vi an toàn đã được thiết kế, chẳng hạn tiếp tục phục vụ nội dung công khai từ nguồn đã được phê duyệt trong khi tạm ngừng chia sẻ tài liệu riêng tư.

Nguyên tắc này chỉ trở thành yêu cầu bảo mật có ích khi trả lời được: **lỗi nào, tác động lên hành động nào, trạng thái bảo vệ là gì, điều gì bị cấm và làm sao kiểm chứng?**

## 2. Phân biệt các khái niệm gần nhau

| Khái niệm | Ý nghĩa trong thiết kế yêu cầu | Ví dụ |
|---|---|---|
| Fail open | Lỗi dẫn đến cho phép hoặc duy trì khả năng đi qua một kiểm soát vốn đang cần được đánh giá. | Không gọi được dịch vụ quyền thì tự cho phép đọc tài liệu. |
| Fail closed | Khi không đáp ứng điều kiện kiểm soát, đóng hoặc từ chối đường truy cập được bảo vệ. | Không có quyết định quyền hợp lệ thì không trả dữ liệu. |
| Fail secure | Duy trì các bất biến bảo mật cần thiết dưới những lỗi thuộc phạm vi. | Không đọc trái phép, không công bố tệp chưa đủ điều kiện, không mở lại quyền cũ khi phục hồi. |
| Fail-safe defaults | Trạng thái mặc định dựa trên điều kiện cho phép rõ ràng, thay vì mặc định được phép nếu chưa thấy điều cấm. | Chưa có chính sách cho hành động mới thì không tự cấp quyền. |
| Graceful degradation — suy giảm có kiểm soát | Tiếp tục một phần chức năng với giới hạn đã đặc tả khi phụ thuộc bị lỗi. | Tạm ngừng xuất hàng loạt nhưng vẫn cho tra cứu dữ liệu mà quyền còn được xác định hợp lệ. |
| Fail safe trong bối cảnh an toàn | Chuyển về trạng thái giảm nguy cơ gây hại theo mục tiêu an toàn đang xét. | Một hệ thống vật lý cần phân tích trạng thái an toàn cho con người khi mất điện. |

Các thuật ngữ fail secure và fail closed có thể được dùng gần nghĩa trong một số tài liệu. Trong đặc tả dự án, hành vi cụ thể quan trọng hơn nhãn gọi: đóng đường nào, giữ trạng thái gì, dữ liệu nào không được trả và điều kiện nào cho phép hoạt động trở lại.

Bảo mật thông tin và an toàn vật lý có thể có mục tiêu khác nhau. Không nên áp một quy tắc “luôn khóa mọi thứ khi lỗi” cho mọi loại hệ thống. Cần phân tích tài sản, tác động và nghĩa vụ bảo vệ trong bối cảnh thực tế.

### 2.1. Từ chối quyền khác với không đánh giá được quyền

Nên phân biệt ít nhất ba kết quả:

```text
ALLOW        Có căn cứ hợp lệ để cho phép trong phạm vi đã xác định.
DENY         Chính sách đã được đánh giá và không cho phép.
UNAVAILABLE  Chưa đánh giá được hoặc không có kết quả đáng tin.
```

Với một thao tác nhạy cảm, DENY và UNAVAILABLE đều không tạo ra quyền thực hiện, nhưng có thể dẫn tới phản hồi, retry và cảnh báo khác nhau. Lỗi phụ thuộc không nên bị ghi nhận sai thành kết luận chắc chắn rằng người dùng không có quyền.

Nếu chỉ dùng một giá trị Boolean và xử lý ngoại lệ bằng cách trả `true`, hệ thống đã biến lỗi thành cho phép. Ngay cả khi lựa chọn Boolean, thiết kế vẫn phải bảo toàn ngữ nghĩa lỗi và tránh giá trị mặc định có thể mở quyền.

## 3. Bối cảnh xuyên suốt: chia sẻ và xuất tài liệu nhiều tenant

Giả sử một dịch vụ quản lý tài liệu phục vụ nhiều tổ chức. Mỗi tổ chức là một **tenant**, có người dùng, tài liệu và quyền riêng. Các luồng nhạy cảm gồm đọc tài liệu, cấp quyền chia sẻ, thu hồi quyền, tạo tệp xuất và tải tệp xuất.

Hệ thống có API, cơ chế xác thực, dịch vụ chính sách quyền, cache quyền, hàng đợi tác vụ, worker, kho tài liệu, kho tệp riêng tư, hệ thống kiểm toán và quy trình phục hồi.

Các bất biến cần duy trì trong ví dụ:

1. Không trả tài liệu hoặc metadata được bảo vệ nếu chưa có căn cứ cho phép đúng chủ thể, hành động, tài nguyên và tenant.
2. Không cấp thêm quyền khi danh tính, quyền giao quyền hoặc điều kiện phê duyệt chưa được xác minh.
3. Không công bố tệp xuất ngoài phạm vi được phép, kể cả khi tác vụ bị lỗi hoặc bị gửi lại.
4. Không thay mã hóa bằng lưu hoặc truyền bản rõ chỉ vì cơ chế bảo vệ dữ liệu không dùng được.
5. Không báo thay đổi thành công nếu trạng thái thực tế và bằng chứng bắt buộc chưa đáp ứng hợp đồng.
6. Không mở lại truy cập nhạy cảm sau phục hồi khi quyền và trạng thái cần thiết chưa được đối chiếu.

Các bất biến này là điểm xuất phát. Cần tiếp tục xác định loại lỗi, thời điểm lỗi và nghĩa vụ của từng thành phần để biết thiết kế có thực sự duy trì được chúng hay không.

## 4. Xây dựng mô hình lỗi trước khi chọn phản ứng

### 4.1. Lỗi không chỉ là timeout

Một phụ thuộc có thể phản hồi nhanh nhưng trả dữ liệu không thể tin cậy. Một quyết định quyền có thể hợp lệ về cấu trúc nhưng đã hết hạn hoặc áp dụng cho tài nguyên khác. Một thành phần có thể chỉ hoạt động một phần, khiến trạng thái giữa các nơi mâu thuẫn.

| Nhóm lỗi | Ví dụ | Câu hỏi bảo mật cần đặt |
|---|---|---|
| Không có phản hồi | Dịch vụ quyền timeout, kho khóa không truy cập được. | Có căn cứ cho phép còn hợp lệ không? Nếu không, hành động nào phải dừng? |
| Phản hồi không hợp lệ | Thiếu trường, sai định dạng, không xác minh được nguồn. | Có đang dùng giá trị mặc định hoặc bỏ qua bước xác minh không? |
| Dữ liệu cũ | Cache quyền chưa phản ánh thu hồi; bản sao phục hồi có thành viên cũ. | Độ cũ tối đa được phép là bao nhiêu, với hành động nào? |
| Trạng thái không nhất quán | Giao dịch quyền đã ghi nhưng phản hồi bị mất; tệp đã lưu nhưng hồ sơ chưa hoàn tất. | Điều gì đã thực sự xảy ra? Có thể gửi lại an toàn không? |
| Cạn tài nguyên | Hàng đợi, vùng đệm log hoặc ổ lưu tệp đầy. | Có bỏ kiểm tra hoặc bỏ dấu vết để tiếp tục không? |
| Lỗi cấu hình hoặc triển khai | Chính sách chưa tải được, khóa xác minh sai, chế độ debug mở nhầm. | Trạng thái khởi động và cấu hình thiếu có mở đường truy cập không? |
| Lỗi thời gian | Đồng hồ lệch, không xác định được hiệu lực token hoặc lần cấp quyền. | Có đủ căn cứ xác định thời hạn còn hợp lệ không? |
| Lỗi phục hồi | Dữ liệu, quyền, phiên và khóa được khôi phục ở các thời điểm khác nhau. | Có tái kích hoạt quyền hoặc công bố tệp không còn được phép không? |

Mô hình lỗi cần ghi phạm vi: dừng tiến trình, mất một nút, gián đoạn mạng, lỗi vùng lưu trữ hay loại can thiệp nào đang xét. Không thể chứng minh “fail secure với mọi lỗi” bằng vài ca timeout.

### 4.2. Kiểm tra lỗi ở từng thời điểm của hành động

Một thao tác thay đổi quyền có thể đi qua:

```text
Nhận yêu cầu
    -> xác thực
    -> kiểm tra quyền và điều kiện
    -> ghi thay đổi cùng bằng chứng bắt buộc
    -> hoàn tất giao dịch
    -> trả kết quả
```

Lỗi trước khi ghi dữ liệu khác với lỗi sau khi giao dịch đã hoàn tất nhưng trước khi client nhận phản hồi. Trong trường hợp sau, dữ liệu có thể đã thay đổi. Trả một lỗi mạng không tự hoàn tác thay đổi đó.

Vì vậy, cần định nghĩa các trạng thái như chưa thực hiện, đã thành công, thất bại đã xác định và chưa biết kết quả. Trạng thái chưa biết không được tùy tiện biến thành thành công hoặc giả định chắc chắn chưa có tác dụng phụ.

## 5. Xác định trạng thái bảo vệ cho từng hành động

| Hành động | Điều kiện lỗi | Trạng thái bảo vệ trong ví dụ | Điều phải tránh |
|---|---|---|---|
| Đọc tài liệu riêng tư | Không xác minh được danh tính hoặc quyền hợp lệ. | Không trả nội dung và metadata được bảo vệ. | Trả dữ liệu từ cache chỉ vì cache có bản sao. |
| Cấp quyền chia sẻ | Thiếu kết quả phê duyệt hoặc quyền giao quyền. | Không tạo quyền mới. | Dùng vai trò mặc định có quyền rộng hoặc coi lỗi là đã phê duyệt. |
| Thu hồi quyền | Đường chuyển log tập trung bị lỗi. | Áp chính sách thu hồi và ghi bằng chứng bền vững đã thiết kế cho tình huống này. | Tự bỏ qua log hoặc tự ngừng mọi thu hồi mà không có quyết định về rủi ro. |
| Tạo tệp xuất | Quyền thay đổi hoặc đọc dữ liệu lỗi giữa chừng. | Không công bố tệp trái chính sách; bảo vệ tệp tạm và ghi trạng thái đúng. | Cho tải tệp một phần chứa dữ liệu ngoài phạm vi. |
| Tải kết quả xuất | Không kiểm tra được quyền hiện hành theo hợp đồng. | Không bắt đầu lượt tải mới nếu không có căn cứ hợp lệ. | Cho qua vì người dùng đã từng tạo tác vụ. |
| Lưu dữ liệu được bảo vệ | Không dùng được khóa hoặc cơ chế mã hóa cần thiết. | Không tự lưu bản rõ để “tạm tiếp tục”. | Hạ cơ chế bảo vệ mà không có chính sách được chấp nhận. |
| Mở lại sau phục hồi | Chưa xác định được trạng thái quyền hiện hành. | Giữ đường nhạy cảm chưa phục vụ cho đến khi điều kiện bảo vệ được xác nhận. | Tin toàn bộ quyền từ bản sao cũ như quyền hiện hành. |

Không có một phản ứng duy nhất đúng cho mọi hành động. Đọc dữ liệu có thể bị từ chối ngay; tác vụ chưa chạy có thể chờ trong phạm vi đã cho phép; thao tác đã ghi một phần có thể cần đối chiếu hoặc bù trừ. Trong mọi lựa chọn, bất biến bảo mật phải được nêu rõ.

### 5.1. Suy giảm có kiểm soát cần điều kiện cho phép rõ ràng

Giả sử dịch vụ quyền tạm thời không truy cập được. Hệ thống có thể được phép sử dụng một quyết định quyền đã cache nếu quyết định đó vẫn là căn cứ hợp lệ theo chính sách: đúng chủ thể, hành động, tài nguyên, tenant, thời hạn và giới hạn thu hồi.

Đây không phải quy tắc “có cache thì cho qua”. Nếu thiếu thông tin để xác định quyết định còn hợp lệ, không thể xem nó là căn cứ cho phép. Hành động cấp quyền hoặc thay cấu hình nhạy cảm cũng có thể bị cấm dùng quyết định cache dù một số thao tác đọc được phép.

Chính sách phải ghi giới hạn tuổi dữ liệu, nguồn thời gian, cách vô hiệu hóa và hành vi khi cache thiếu hoặc sai. Đổi sang một bản quyền cũ không giới hạn khi phụ thuộc lỗi là một đường mở quyền, không phải suy giảm đã được kiểm soát.

## 6. Viết yêu cầu fail secure có thể kiểm chứng

Một mẫu yêu cầu có thể dùng là:

```text
[Mã yêu cầu]
Với [hành động/tài sản], khi [loại lỗi] xảy ra tại [điểm xử lý],
hệ thống phải [phản ứng và trạng thái cần duy trì].
Không được [tiết lộ, thay đổi hoặc vượt quyền bị cấm].
Kết quả được ghi nhận bằng [trạng thái, sự kiện, mã tương quan].
Chỉ hoạt động trở lại khi [điều kiện phục hồi].
Chấp nhận khi [quan sát và phạm vi kiểm chứng].
```

Cần đặt ngưỡng khi chúng có ý nghĩa, như timeout, độ mới của cache, giới hạn thu hồi, thời hạn tệp tạm hoặc thời gian phát hiện tồn đọng. Các ngưỡng phải dựa trên rủi ro và khả năng của hệ thống; tên nguyên tắc không tự cung cấp một giá trị mặc định.

### FS-01 — Không xác lập được quyền thì không đọc dữ liệu được bảo vệ

> Trước khi trả tài liệu riêng tư, API phải có căn cứ cho phép hợp lệ cho đúng chủ thể, hành động, tenant và tài nguyên. Timeout, phản hồi không xác minh được, thiếu thuộc tính bắt buộc hoặc không xác định được hiệu lực không được chuyển thành cho phép. Khi không có căn cứ hợp lệ khác theo chính sách, API không trả nội dung hoặc metadata được bảo vệ và ghi nhận kết quả theo hợp đồng lỗi.

**Tiêu chí chấp nhận:** mô phỏng các lỗi đã liệt kê, kiểm tra phản hồi, dữ liệu trả về, truy vấn hoặc tác dụng phụ liên quan và sự kiện bảo mật. Phải có ca chủ thể được phép thành công để tránh hệ thống “đạt” chỉ bằng cách từ chối mọi người.

### FS-02 — Không mở rộng quyền khi điều kiện cấp quyền chưa hoàn tất

> Với thao tác cấp quyền, hệ thống chỉ ghi thay đổi khi danh tính, quyền giao quyền, phạm vi người nhận/tài nguyên và điều kiện phê duyệt bắt buộc đều hợp lệ. Nếu một điều kiện chưa đánh giá được, không tạo quyền mới. Không dùng kết quả từ một yêu cầu, tài nguyên hoặc phiên bản chính sách khác làm mặc định cho yêu cầu hiện tại.

**Tiêu chí chấp nhận:** thử thiếu phê duyệt, mất kết nối nguồn quyền, thay tenant, phản hồi sai cấu trúc và gửi lại yêu cầu; không có quyền mới xuất hiện ngoài các trường hợp được cho phép rõ ràng.

### FS-03 — Lỗi cơ chế bảo vệ dữ liệu không tạo đường bản rõ

> Với dữ liệu được yêu cầu mã hóa theo chính sách, lỗi lấy khóa, xác minh cấu hình hoặc khởi tạo cơ chế bảo vệ không được dẫn tới ghi hoặc truyền bản rõ qua đường thay thế. Component phải giữ dữ liệu trong phạm vi được bảo vệ, không hoàn tất bước không đáp ứng điều kiện và xử lý dữ liệu tạm theo chính sách đã định.

**Tiêu chí chấp nhận:** làm phụ thuộc khóa hoặc cấu hình bảo vệ không dùng được; kiểm tra nơi lưu chính, tệp tạm, hàng đợi và log trong phạm vi. Không xuất hiện bản rõ ở đường không được phép; các chức năng không cần dữ liệu đó có thể tiếp tục nếu đáp ứng chính sách riêng.

### FS-04 — Không công bố kết quả xuất chưa đủ điều kiện

> Worker phải thực thi tác vụ trong phạm vi tenant và tài liệu được xác lập bởi hồ sơ có thẩm quyền. Lỗi đọc dữ liệu, quyền không còn đáp ứng theo hợp đồng hoặc thất bại xác minh trước công bố phải giữ kết quả ở trạng thái không tải được. Tệp tạm không được công khai; retry không được mở rộng phạm vi hay công bố một kết quả không còn hợp lệ.

**Tiêu chí chấp nhận:** gây lỗi trước đọc, giữa các bước xử lý, trước lưu trạng thái công bố và khi nhận thông điệp lặp. Đường tải, cache và kho tệp không trả kết quả ngoài điều kiện đã cho phép. Bằng chứng phải phân biệt tệp đã tạo với tệp đã được công bố.

### FS-05 — Lỗi kiểm toán có hành vi đã được chấp nhận theo loại thao tác

> Với các thao tác được yêu cầu có bằng chứng bền vững trước khi xác nhận, hệ thống không được bỏ sự kiện bắt buộc chỉ vì kho tập trung không phản hồi. Phải có cơ chế lưu nhất quán hoặc cơ chế thay thế đã được phê duyệt cho từng loại hành động. Khi không còn bảo đảm ghi nhận, áp hành vi đã đặc tả và cảnh báo; không tự bật chế độ bỏ logging.

**Tiêu chí chấp nhận:** gián đoạn đường chuyển log, làm vùng đệm đạt giới hạn và khởi động lại thành phần theo mô hình lỗi. Kiểm tra dữ liệu nghiệp vụ, sự kiện đã lưu, phản hồi và cảnh báo. Riêng đường thu hồi hoặc khẩn cấp phải được thử theo chính sách của nó, không suy từ hành vi của cấp quyền mới.

### FS-06 — Mở lại chức năng sau khi xác nhận điều kiện bảo vệ

> Sau lỗi hoặc phục hồi, chức năng nhạy cảm chỉ được hoạt động khi danh tính, chính sách, dữ liệu quyền, khóa và trạng thái nghiệp vụ cần thiết đáp ứng các điều kiện đã định. Một health check thành công hoặc kết nối lại phụ thuộc chưa đủ để coi mọi trạng thái đều an toàn. Quyền cũ, tác vụ chờ và liên kết tải phải được đối chiếu theo phạm vi phục hồi.

**Tiêu chí chấp nhận:** phục hồi bản sao chứa quyền đã thu hồi, khởi động khi thiếu chính sách và phục hồi tệp không khớp trạng thái tác vụ. Không mở đường truy cập trái yêu cầu; chức năng hợp lệ được phục vụ lại sau khi hoàn tất các bước xác nhận.

## 7. Thiết kế luồng quyết định không biến lỗi thành cho phép

### 7.1. Tách đánh giá, thực thi và ghi nhận

Một luồng ở mức khái niệm có thể là:

```text
1. Xác minh danh tính và ngữ cảnh yêu cầu.
2. Đánh giá quyền cho đúng chủ thể, hành động và tài nguyên.
3. Phân loại kết quả:
   - ALLOW hợp lệ: tiếp tục với đúng phạm vi và thời hạn.
   - DENY: không thực hiện; phản hồi từ chối theo hợp đồng.
   - UNAVAILABLE hoặc kết quả sai hợp đồng: không mở quyền;
     phản hồi/chờ có giới hạn theo chính sách của hành động.
4. Thực hiện hành động với các điều kiện nhất quán cần thiết.
5. Ghi kết quả và bằng chứng theo cam kết.
6. Trả trạng thái phản ánh điều thực sự đã xảy ra.
```

Danh tính hợp lệ chưa đủ cho bước 3. Quyết định quyền hợp lệ cũng không tự bảo đảm bước 4 đã thành công. Các điều kiện phải được thực thi trước hành động được bảo vệ, không chỉ được ghi vào một bản log.

Nếu một component dùng kết quả quyền do component khác tạo, hợp đồng phải ràng buộc nguồn, chủ thể, hành động, tài nguyên, tenant và hiệu lực. Nhận được một đối tượng dữ liệu tên `decision` không đủ để biết đó là quyết định có thể dùng cho request hiện tại.

### 7.2. Các mặc định dễ làm mất trạng thái bảo vệ

| Mặc định hoặc cách xử lý | Nguy cơ | Yêu cầu nên đặt |
|---|---|---|
| Thiếu tenant thì dùng tenant mặc định có dữ liệu thật. | Request không đủ ngữ cảnh có thể đi vào phạm vi không được phép. | Tenant phải được xác lập từ ngữ cảnh có thẩm quyền và đối chiếu với quyền. |
| Lỗi tải chính sách thì cho mọi hành động chạy. | Khởi động hoặc reload lỗi trở thành đường mở quyền. | Chức năng nhạy cảm chưa phục vụ khi chưa có chính sách hợp lệ cần thiết. |
| Không hiểu giá trị quyết định mới thì coi là cho phép. | Thay đổi phiên bản hợp đồng làm mất kiểm soát. | Kết quả không nhận diện được được xử lý như chưa có căn cứ hợp lệ. |
| Hết hạn token hoặc lỗi xác minh thì chỉ ghi cảnh báo. | Thông tin không còn đáng tin vẫn được dùng làm danh tính hợp lệ. | Chỉ chấp nhận bằng chứng đáp ứng đầy đủ hợp đồng xác thực. |
| Retry bỏ bước kiểm tra để giảm thời gian chờ. | Một đường xử lý lại có quyền rộng hơn lần đầu. | Retry phải giữ cùng nghĩa bảo vệ và đánh giá lại điều kiện theo chính sách. |
| Thông báo lỗi chứa dữ liệu đã đọc. | Từ chối cuối cùng nhưng vẫn tiết lộ thông tin. | Phản hồi và logging lỗi phải tuân theo chính sách dữ liệu. |
| Dùng ngữ cảnh người dùng còn sót từ lần xử lý trước. | Lỗi trạng thái tạo nhầm danh tính hoặc tenant. | Ngữ cảnh phải gắn rõ với từng request/tác vụ và không tái sử dụng sai phạm vi. |

Các tình huống này có thể xuất hiện ngay cả khi luồng thành công đã đúng. Vì vậy, yêu cầu fail secure phải bao phủ cả nhánh ngoại lệ, cấu hình thiếu, phiên bản không tương thích và khởi động lại.

### 7.3. Timeout, retry và circuit breaker

Timeout giúp giới hạn chờ; nó không tạo kết quả quyền. Retry chỉ nên thực hiện trong ngân sách và điều kiện đã định, không lặp vô hạn hoặc bỏ điều kiện vì lần thử trước lỗi.

Circuit breaker có thể ngừng gọi một phụ thuộc đang lỗi để bảo vệ tài nguyên. Khi mạch đang mở, component vẫn phải áp chính sách bảo mật: dùng căn cứ còn hợp lệ đã được cho phép hoặc chưa thực hiện hành động nhạy cảm. Trạng thái mạch mở không phải bằng chứng cho phép truy cập.

Cần định nghĩa thời điểm phản hồi, giới hạn hàng đợi, cách quan sát và điều kiện thử hoạt động lại. Các lựa chọn này hỗ trợ sẵn sàng nhưng không được âm thầm thay đổi nghĩa của cho phép, từ chối hoặc hiệu lực quyền.

## 8. Lỗi giữa chừng và kết quả chưa xác định

### 8.1. Không đồng nhất lỗi phản hồi với chưa có tác dụng phụ

Giả sử API cấp quyền đã hoàn tất giao dịch, nhưng kết nối tới client bị đứt trước khi gửi kết quả. Client thấy lỗi trong khi quyền đã được cấp hợp lệ. Nếu client gửi lại và server coi đó là một thao tác hoàn toàn mới, hệ thống có thể tạo lịch sử hoặc tác dụng phụ lặp.

Hợp đồng cần cho phép xác định lại kết quả bằng mã thao tác hoặc cơ chế tương đương. Nếu hỗ trợ khóa chống xử lý lặp, phải xác định nó gắn với chủ thể, tenant, nội dung yêu cầu và thời hạn nào. Cùng khóa nhưng khác nội dung không được âm thầm dùng kết quả cũ cho một ý định mới.

Fail secure trong tình huống này không có nghĩa hứa rằng quyền chắc chắn chưa đổi. Nghĩa vụ là không mở rộng quyền ngoài ý định đã được cho phép, giữ trạng thái cùng bằng chứng nhất quán và cung cấp cách xác định điều đã xảy ra.

### 8.2. Tác vụ nền cần trạng thái công bố tách biệt

Một mô hình khái niệm cho tệp xuất:

```text
Đã nhận -> Đang xử lý -> Đã tạo tệp riêng tư
                               |
                               v
                  Kiểm tra điều kiện công bố
                       |                 |
                       v                 v
                   Được công bố     Không công bố
```

Các nhánh lỗi phải xác định tệp đang ở đâu, ai đọc được, tác vụ có được chạy lại không và khi nào dữ liệu tạm được xóa. Việc một tệp có tên hoàn chỉnh hoặc đã có checksum không chứng minh người dùng được phép tải.

Trong mô hình của bài, nếu chính sách yêu cầu toàn bộ hoặc không công bố, một lỗi giữa chừng không được trả tệp một phần cho người dùng. Sản phẩm khác có thể chấp nhận kết quả một phần nếu yêu cầu nêu rõ phạm vi, trạng thái và bảo đảm không chứa dữ liệu trái phép.

### 8.3. Dữ liệu đã gửi không tự quay trở lại

Nếu API đã gửi một phần nội dung nhạy cảm rồi mới phát hiện không có quyền, việc trả lỗi ở cuối không khắc phục được tiết lộ trước đó. Kiểm tra bắt buộc phải diễn ra trước các lần đọc hoặc trả dữ liệu được bảo vệ theo hợp đồng.

Với tải tệp dài hoặc streaming, cần xác định chính sách khi quyền thay đổi hoặc phụ thuộc lỗi trong lúc truyền: dừng ở điểm nào, dữ liệu đã gửi nằm ngoài khả năng thu hồi nào và sự kiện nào được ghi. Không thể dùng tên fail secure để hứa thu hồi các byte đã đến người nhận.

### 8.4. Bù trừ cũng cần bảo vệ

Trong luồng nhiều bước, có thể không hoàn tác nguyên tử được mọi tác dụng phụ. Hệ thống có thể cần bù trừ, giữ trạng thái chờ đối chiếu hoặc yêu cầu xử lý có kiểm soát.

Các bước này cũng cần danh tính, quyền, tính lặp an toàn và dấu vết. Không dùng một tài khoản có quyền không giới hạn để “sửa mọi thứ” mà không gắn phạm vi nhiệm vụ. Nếu bù trừ thất bại, phải giữ được trạng thái cùng đầu mối xử lý, không xóa bằng chứng để làm tác vụ trông như chưa từng tồn tại.

## 9. Logging, cảnh báo và truy cập khẩn cấp

### 9.1. Ghi đúng loại kết quả

Sự kiện nên phân biệt từ chối theo chính sách, chưa đánh giá được do phụ thuộc, lỗi thực hiện và kết quả chưa xác định. Cần nối được chủ thể khởi tạo, danh tính thực thi, tenant, tài nguyên hoặc tác vụ, hành động, mã lỗi được kiểm soát và mã tương quan phù hợp.

Không ghi token, khóa, mật khẩu hay nội dung tài liệu để chẩn đoán nhanh. Lỗi của cơ chế bảo vệ không được tạo thêm nguồn rò rỉ qua stack trace, thông báo lỗi, tệp tạm hoặc hàng đợi xử lý lỗi.

Cảnh báo cần giúp phát hiện phụ thuộc đang tạo nhiều trường hợp chưa đánh giá được, vùng đệm gần đầy, cấu hình fallback bị thay đổi hoặc nguồn phát sự kiện bị mất. Mỗi cảnh báo cần đầu mối, thời hạn xử lý và quy trình chuyển cấp theo mức tác động.

### 9.2. Không sửa sự cố bằng một công tắc mở mọi quyền

Một cấu hình “tạm bỏ phân quyền khi dịch vụ quyền lỗi” có thể tạo đường lạm dụng và tồn tại lâu hơn sự cố. Cấu hình thay đổi hành vi bảo vệ phải có phạm vi, quyền thay đổi, thời hạn, dấu vết và điều kiện kết thúc rõ ràng.

Nếu cần truy cập khẩn cấp, hãy đặc tả trước: ai dùng được, xác thực thế nào khi phụ thuộc chính không hoạt động, quyền nào được cấp, tài nguyên nào nằm trong phạm vi, ai được thông báo và làm sao rà soát sau sự cố.

Truy cập khẩn cấp là một đường kiểm soát riêng có điều kiện, không phải tự cho phép mọi request khi một component không trả lời. Nếu đường khẩn cấp vẫn phụ thuộc hoàn toàn vào chính thành phần đang bị lỗi mà không có phương án tương ứng, nó chưa đáp ứng kịch bản đã đặt ra.

## 10. Quan hệ với sẵn sàng và phục hồi

Fail secure có thể làm một chức năng tạm thời không phục vụ được khi thiếu căn cứ bảo vệ. Điều đó không làm mục tiêu sẵn sàng mất ý nghĩa. Kiến trúc vẫn phải giảm xác suất và tác động lỗi bằng dự phòng, phân vùng tài nguyên, tối ưu phụ thuộc và suy giảm có kiểm soát.

Cần đánh giá hai mặt đồng thời:

| Câu hỏi bảo mật | Câu hỏi sẵn sàng tương ứng |
|---|---|
| Có cho phép sai khi dịch vụ quyền lỗi không? | Người dùng hợp lệ bị ảnh hưởng bao lâu, phạm vi nào và được phục vụ lại ra sao? |
| Cache có giữ đúng phạm vi và hiệu lực không? | Cache giúp tiếp tục chức năng nào trong bao lâu theo chính sách? |
| Lỗi log có làm mất bằng chứng bắt buộc không? | Vùng lưu bền vững chịu được mức tải và thời gian gián đoạn nào? |
| Sau restore có mở lại quyền cũ không? | Cần bao lâu để đối chiếu quyền và mở lại chức năng hợp lệ? |

Nếu hệ thống dễ bị làm mất phụ thuộc để gây từ chối dịch vụ, chỉ có hành vi từ chối an toàn chưa đủ đáp ứng toàn bộ mục tiêu. Cần bổ sung yêu cầu chống lạm dụng, năng lực chịu lỗi và phục hồi; không khắc phục bằng cách tự bỏ kiểm soát.

Mốc hoàn tất phục hồi phải bao gồm điều kiện bảo vệ cần thiết. “Cơ sở dữ liệu đã khởi động” chưa có nghĩa dịch vụ sẵn sàng an toàn nếu chính sách chưa tải, khóa chưa dùng được hoặc quyền khôi phục còn cũ.

RTO là mục tiêu thời gian phục hồi; RPO là mục tiêu về khoảng mất dữ liệu tối đa tính theo thời gian. Cả hai cần có phạm vi dữ liệu, loại sự cố và mốc đo. Chúng không tự cho phép bỏ qua việc đối chiếu quyền hoặc công bố tệp chưa hợp lệ để đạt một con số thời gian.

## 11. Kiểm chứng bằng các kịch bản lỗi có chủ đích

### 11.1. Ma trận kiểm chứng minh họa

| Kịch bản | Quan sát bắt buộc | Yêu cầu liên quan |
|---|---|---|
| Dịch vụ quyền timeout hoặc trả kết quả không hiểu được | Không trả dữ liệu được bảo vệ, không tạo quyền; phân loại lỗi và phản hồi đúng hợp đồng. | FS-01, FS-02 |
| Cache chứa quyết định cũ hoặc sai tài nguyên | Không sử dụng ngoài hiệu lực và phạm vi được phép. | FS-01, FS-02 |
| Kho khóa không dùng được | Không xuất hiện bản rõ ở nơi lưu hoặc kênh thay thế không được phép. | FS-03 |
| Worker lỗi sau khi tạo tệp nhưng trước công bố | Tệp vẫn riêng tư; không có đường tải vượt kiểm tra. | FS-04 |
| Thông điệp lặp sau khi quyền đã thay đổi | Không mở rộng tác vụ hoặc công bố kết quả trái chính sách. | FS-04 |
| Đường chuyển log lỗi, vùng đệm đạt giới hạn | Dữ liệu và bằng chứng đáp ứng chính sách theo loại thao tác; có cảnh báo. | FS-05 |
| Giao dịch hoàn tất nhưng mất phản hồi | Xác định lại được kết quả; gửi lại không gây thay đổi ngoài ý định được phép. | FS-02, FS-05 |
| Restore dữ liệu có quyền cũ hoặc trạng thái tệp lệch | Chưa mở đường nhạy cảm cho đến khi điều kiện bảo vệ được xác nhận. | FS-06 |

Các kịch bản cần thực hiện trong môi trường có kiểm soát và gắn với mô hình lỗi đã chọn. Bảng là ví dụ thiết kế bằng chứng, không phải tuyên bố rằng một triển khai cụ thể đã được kiểm thử.

### 11.2. Ví dụ tiêu chí chấp nhận cho đọc tài liệu

```text
Cho trước:
  U đã được xác thực.
  Tài liệu D thuộc tenant T-A.
  API bắt buộc có quyết định quyền hợp lệ trước khi trả nội dung.
  Không có quyết định cache nào còn hợp lệ cho U đọc D.

Khi:
  U gọi API đọc D.
  Dịch vụ quyền không cung cấp được kết quả hợp lệ trong hợp đồng chờ.

Thì:
  API không trả nội dung hoặc metadata được bảo vệ của D.
  API không chuyển lỗi thành quyền đọc mặc định.
  Phản hồi biểu thị đúng tình trạng theo hợp đồng mà không lộ chi tiết nhạy cảm.
  Có bằng chứng liên kết yêu cầu với lỗi phụ thuộc và kết quả xử lý.
```

Cần thêm ca thành công khi có quyền hợp lệ, ca DENY thật sự và ca cache còn hiệu lực nếu chính sách cho phép. Kiểm tra mã phản hồi đơn lẻ chưa đủ: phải quan sát dữ liệu, trạng thái nghiệp vụ, tệp, thông điệp và dấu vết liên quan.

### 11.3. Giới hạn của bằng chứng

“Không mở quyền trong các ca lỗi đã thử” là kết quả của một phạm vi hữu hạn. Nó không chứng minh hệ thống duy trì bảo mật với mọi lỗi chưa biết.

Bằng chứng cần ghi phiên bản phần mềm, cấu hình, chính sách, dữ liệu, tải, điểm gây lỗi và thời điểm quan sát. Khi thêm đường truy cập, đổi cache, tách worker, thay cơ chế khóa hoặc điều chỉnh fallback, phải xem lại các yêu cầu và ca kiểm chứng bị ảnh hưởng.

Nên liên kết rủi ro, yêu cầu, component thực thi và bằng chứng. Ví dụ rủi ro mở quyền khi phụ thuộc lỗi nối với FS-01/FS-02, điểm thực thi API, dịch vụ chính sách và các ca timeout/phản hồi sai; rủi ro công bố tệp lỗi nối với FS-04 và đường tải/kho tệp.

## 12. Những nhầm lẫn thường gặp

| Nhận định | Vấn đề | Hướng đặc tả rõ hơn |
|---|---|---|
| “Có try/catch là fail secure.” | Nhánh bắt lỗi vẫn có thể mở quyền, trả dữ liệu hoặc ghi trạng thái sai. | Xác định trạng thái bảo vệ và tác dụng phụ bị cấm cho từng lỗi. |
| “Đã đăng nhập nên lúc lỗi có thể bỏ kiểm tra quyền.” | Xác thực không chứng minh quyền trên tài nguyên cụ thể. | Chỉ thực hiện khi có căn cứ cho phép đúng phạm vi. |
| “Fail secure nghĩa là dừng mọi chức năng.” | Bỏ qua khả năng suy giảm có điều kiện. | Chỉ rõ chức năng nào còn đủ căn cứ để hoạt động an toàn. |
| “Trả lỗi nghĩa là chưa có thay đổi.” | Giao dịch có thể đã hoàn tất trước khi phản hồi thất bại. | Mô hình hóa kết quả chưa xác định và cách đối chiếu/gửi lại. |
| “Có cache thì luôn tiếp tục được.” | Dữ liệu có thể cũ, sai phạm vi hoặc không đáp ứng thu hồi. | Ghi điều kiện hiệu lực, độ mới và hành động được phép dùng cache. |
| “Đường khẩn cấp có thể bỏ mọi kiểm soát.” | Tạo đường truy cập rộng không được quản lý. | Thiết kế cơ chế khẩn cấp có danh tính, phạm vi, thời hạn và bằng chứng. |
| “Health check xanh là đủ mở lại.” | Thành phần có thể chạy nhưng chính sách, quyền hoặc khóa chưa nhất quán. | Đặt điều kiện phục hồi cho chức năng nhạy cảm, không chỉ trạng thái tiến trình. |

## 13. Bài tập áp dụng

Một công ty bổ sung chức năng xóa tài liệu hàng loạt. Người dùng tạo yêu cầu, người khác phê duyệt theo chính sách và worker chạy sau đó. Hệ thống cần lưu bằng chứng, hỗ trợ gửi lại an toàn và có thể gặp lỗi dịch vụ quyền, kho khóa hoặc đường logging.

Hãy thực hiện các bước sau:

1. Xác định tài sản, hành động nhạy cảm và các bất biến phải giữ khi lỗi.
2. Liệt kê ít nhất sáu kịch bản lỗi tại các thời điểm trước quyết định quyền, trước ghi dữ liệu, sau ghi nhưng trước phản hồi và khi phục hồi.
3. Viết yêu cầu cho thiếu phê duyệt, quyền bị thu hồi khi đang chờ và kết quả thao tác chưa xác định.
4. Quy định hành vi khi logging lỗi, cơ chế gửi lại, trạng thái dữ liệu bị xử lý một phần và trách nhiệm xử lý tiếp.
5. Chỉ rõ điều kiện cache hoặc suy giảm được phép, nếu có; không đưa ra một cơ chế fallback không giới hạn.
6. Viết ca được phép, bị từ chối, chưa đánh giá được và phục hồi; nêu dữ liệu cùng dấu vết phải quan sát.

Một đặc tả tốt giải thích được hệ thống giữ điều kiện bảo vệ nào, phản ứng ra sao ở từng điểm lỗi và chỉ tiếp tục khi có căn cứ gì. Từ đó, fail secure trở thành yêu cầu có thể thiết kế, triển khai và kiểm chứng thay vì một khẩu hiệu “an toàn khi có lỗi”.
