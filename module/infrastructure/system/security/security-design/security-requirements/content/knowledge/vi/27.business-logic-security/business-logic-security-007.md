# TOCTOU

## 1. TOCTOU là gì?

**TOCTOU** là viết tắt của **Time of Check to Time of Use**: trạng thái hoặc đối tượng được kiểm tra tại một thời điểm nhưng bị thay đổi trước khi hệ thống sử dụng kết quả kiểm tra đó. Quyết định thực thi vì vậy có thể dựa trên một điều kiện không còn đúng hoặc áp dụng lên một đối tượng khác với đối tượng đã được kiểm tra.

Ví dụ, hệ thống kiểm tra một mã ưu đãi chưa được sử dụng, sau đó mới ghi nhận việc sử dụng. Hai request đồng thời có thể cùng vượt qua bước kiểm tra trước khi một request kịp cập nhật trạng thái. Nếu bước ghi nhận không kiểm tra và chuyển trạng thái một cách nhất quán, cùng một quyền lợi có thể được cấp hai lần.

Một ví dụ khác là kiểm tra tệp theo đường dẫn rồi mở lại đường dẫn đó để xử lý. Nếu tham chiếu bị thay thế giữa hai bước, dữ liệu được xử lý có thể không phải dữ liệu đã được kiểm tra.

Trong chương **Business logic security** của module yêu cầu bảo mật, mục tiêu học TOCTOU là chuyển các khoảng hở về thời gian thành yêu cầu cụ thể về bất biến, danh tính đối tượng, phiên bản, quyền thao tác và ranh giới cam kết. Yêu cầu phải có thể liên kết với rủi ro, kiến trúc và tiêu chí kiểm thử trong vòng đời phát triển.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định bước kiểm tra, bước sử dụng và trạng thái có thể thay đổi giữa hai bước.
2. Viết bất biến và xác định thời điểm một quyết định có hiệu lực.
3. Phân biệt bảo đảm của cập nhật có điều kiện, khóa, giao dịch, phiên bản và định danh bất biến.
4. Đặc tả hành vi khi quyền bị thu hồi, công việc bị trì hoãn hoặc kết quả bên ngoài chưa xác định.
5. Xây dựng bài kiểm thử có lịch xen kẽ để chứng minh hệ thống giữ được yêu cầu.

## 2. Nhận diện ba thành phần của khoảng hở

Một kịch bản TOCTOU thường có ba thành phần:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Check | Hệ thống đã xác minh điều gì? | Voucher còn khả dụng và thuộc đúng người dùng |
| Khoảng thay đổi | Ai hoặc điều gì có thể làm điều kiện đổi? | Request khác sử dụng voucher, quản trị viên thu hồi hoặc worker cập nhật |
| Use | Kết quả kiểm tra được dùng để cho phép tác động nào? | Cấp giảm giá và ghi nhận voucher đã sử dụng |

Khoảng hở không nhất thiết kéo dài nhiều giây. Nó có thể chỉ là khoảng giữa hai câu lệnh, nhưng vẫn có thể bị xen kẽ bởi một luồng hoặc giao dịch khác. Ngược lại, các quy trình qua hàng đợi, phê duyệt và dịch vụ bên ngoài có thể tạo khoảng hở kéo dài hàng phút hoặc lâu hơn.

TOCTOU cũng không đòi hỏi hệ thống có nhiều luồng trong cùng tiến trình. Một tiến trình xử lý tuần tự vẫn có thể đọc trạng thái rồi chờ mạng, trong khi một tiến trình khác thay đổi dữ liệu dùng chung. Việc chỉ dùng một worker tại một điểm chưa đủ nếu còn đường ghi khác.

### Ví dụ lịch xen kẽ

```text
T0: Request A đọc voucher: AVAILABLE, version = 7.
T1: Request B đọc cùng voucher: AVAILABLE, version = 7.
T2: A quyết định cấp quyền lợi dựa trên kết quả T0.
T3: B quyết định cấp quyền lợi dựa trên kết quả T1.
T4: A và B đều ghi trạng thái REDEEMED mà không ràng buộc trạng thái cũ.
```

Trường `state` cuối cùng chỉ có một giá trị `REDEEMED`, nhưng hai quyền lợi có thể đã được cấp. Chỉ nhìn trạng thái cuối của bản ghi không chứng minh bất biến “một voucher cấp quyền lợi tối đa một lần” đã được giữ.

### Phân biệt với một số lỗi gần nhau

- **Race condition** là khái niệm rộng về hành vi phụ thuộc lịch thực thi. TOCTOU tập trung vào quan hệ giữa kết quả kiểm tra và lần sử dụng sau đó.
- **Dữ liệu cũ** chưa chắc tạo lỗi bảo mật nếu nghiệp vụ cho phép dùng một snapshot trong phạm vi xác định. Nó trở thành vấn đề khi hệ thống hứa dùng trạng thái hiện tại nhưng lại dùng snapshot đã hết hiệu lực.
- **Lost update** là một kiểu ghi đè cập nhật có thể xuất hiện cùng TOCTOU, nhưng không phải mọi TOCTOU đều là lost update.
- **Idempotency** kiểm soát các lần gửi lại của cùng thao tác. Hai thao tác khác nhau vẫn có thể cùng tiêu thụ một nguồn lực nếu thiếu ràng buộc chung.

## 3. Từ mô hình đe dọa đến bất biến bảo mật

Không nên đặc tả đơn thuần “tránh TOCTOU”. Cần nêu tài sản, điều kiện được tin và kết quả không được phép.

| Tài sản hoặc quy trình | Điều kiện có thể đổi | Kết quả không được phép | Bất biến hoặc yêu cầu cần giữ |
|---|---|---|---|
| Voucher dùng một lần | Trạng thái và chủ sở hữu | Cấp quyền lợi hai lần hoặc cho sai người | Một voucher chỉ tạo một quyền lợi hợp lệ cho đúng chủ thể |
| Tồn kho | Số lượng khả dụng | Cam kết bán vượt lượng được phép | Kiểm tra và giữ hàng không vượt ngân sách tồn kho |
| Quy trình phê duyệt | Số tiền, nơi nhận, phiên bản | Thực thi nội dung chưa được duyệt | Nội dung thực thi khớp đúng phiên bản đã duyệt |
| Phân quyền | Vai trò, tenant, quan hệ sở hữu | Thao tác sau thời điểm thu hồi theo hợp đồng | Quyết định phải tuân ngữ nghĩa thu hồi được công bố |
| Tệp hoặc đối tượng upload | Tham chiếu, nội dung, phiên bản | Sử dụng dữ liệu khác dữ liệu đã được kiểm tra | Kết quả kiểm tra gắn với đúng phiên bản dữ liệu được sử dụng |
| Job nền | Trạng thái đối tượng trong lúc chờ | Chạy một yêu cầu đã bị hủy hoặc hết điều kiện | Worker thực thi theo trạng thái và quyền có hiệu lực tại điểm đã định |

Với mỗi dòng, cần xác định tất cả bên có thể làm trạng thái thay đổi: người dùng, dịch vụ, quản trị viên, worker, callback và tác vụ bảo trì. Khóa chỉ bảo vệ một đường ghi trong khi đường khác bỏ qua khóa thì chưa tạo bảo đảm cho tài sản.

Một mẫu diễn đạt hữu ích:

> Khi thực hiện hành động A trên đối tượng O, hệ thống phải giữ điều kiện P tại điểm quyết định L hoặc sử dụng một quyền đã được ràng buộc hợp lệ với O và phiên bản V theo hợp đồng. Mọi thay đổi có thể làm P sai phải được sắp thứ tự hoặc được phát hiện trước khi tác động được cam kết. Nếu phát hiện xung đột, hệ thống không tạo tác động trái phép và trả trạng thái xác định.

Các ký hiệu phải được thay bằng nội dung cụ thể của sản phẩm. Không để “P hợp lệ” hay “xử lý an toàn” trở thành những chỗ không có định nghĩa.

## 4. Xác định thời điểm quyết định có hiệu lực

### 4.1. Điểm tuyến tính hóa

**Điểm tuyến tính hóa** là thời điểm logic mà một thao tác đồng thời được coi là đã có hiệu lực, như thể các thao tác tranh chấp đã được sắp thành một thứ tự nhất quán. Trong một triển khai cụ thể, điểm đó có thể gắn với việc cam kết giao dịch hoặc một thao tác cập nhật có điều kiện được hệ thống lưu trữ bảo đảm.

Khái niệm này giúp đặc tả câu hỏi “ai thắng” một cách rõ ràng. Với voucher dùng một lần, tối đa một giao dịch được phép cam kết việc tiêu thụ quyền lợi. Request thua phải nhận kết quả xung đột hoặc trạng thái đã sử dụng theo hợp đồng, không được tiếp tục cấp quyền lợi vì đã từng đọc thấy `AVAILABLE`.

Không phải mọi bước của hệ thống đều có chung một điểm cam kết. Ghi dữ liệu nội bộ và gọi một dịch vụ bên ngoài thường có các ranh giới khác nhau. Cần nêu bảo đảm cho từng ranh giới thay vì mặc nhiên coi cả chuỗi là một thao tác nguyên tử.

### 4.2. Hiệu lực của kiểm tra quyền

Đặc tả phải chọn ngữ nghĩa phù hợp, ví dụ:

| Mô hình | Quyền có hiệu lực khi nào? | Điều cần đặc tả |
|---|---|---|
| Tại lúc nhận việc | Chấp nhận công việc tạo một quyền thực thi đã được giới hạn | Đối tượng, nội dung, thời hạn, khả năng thu hồi và phạm vi quyền đã cấp |
| Tại lúc bắt đầu thực thi | Job chờ phải được kiểm tra lại trước khi tạo tác động | Cách gắn kết kiểm tra với bước thực thi để không tạo khoảng hở mới |
| Theo từng chặng nhạy cảm | Quy trình dài đánh giá lại ở các mốc xác định | Chặng nào cần dừng khi quyền đổi, và cách xử lý phần đã hoàn tất |

Không có một mô hình duy nhất đúng cho mọi sản phẩm. Một công việc đã được chấp nhận có thể được phép tiếp tục trong một hợp đồng, nhưng phải bị dừng trước thực thi trong hợp đồng khác.

Nếu yêu cầu là thu hồi quyền có hiệu lực ngay đối với mọi thao tác chưa cam kết, hệ thống phải có cơ chế sắp thứ tự quyết định thu hồi với quyết định thực thi trong phạm vi cam kết. Chỉ “kiểm tra lại ngay trước khi làm” vẫn để lại khoảng hở nếu hai bước không có liên kết nhất quán.

Thu hồi quyền không tự đảo ngược tác động đã cam kết. Các tác động cần bù trừ hoặc hủy phải có quy trình riêng và quyền thực hiện rõ ràng.

### 4.3. Thời gian cũng có thể làm điều kiện đổi

Một quyền hoặc báo giá có thể hết hạn dù không có ai cập nhật bản ghi. Vì vậy, kiểm tra phiên bản đơn thuần chưa bảo vệ mọi điều kiện phụ thuộc thời gian.

Yêu cầu phải xác định đồng hồ có thẩm quyền, múi giờ, biên hết hạn và thời điểm đánh giá. Nếu quyền hợp lệ tại lúc tiếp nhận nhưng chỉ được dùng sau một khoảng chờ dài, cần nói rõ quyền đó còn được phép dùng hay phải được xác minh lại.

Không lấy một mốc thời gian cũ trong request hoặc snapshot rồi gọi đó là “thời gian hiện tại”. Tương tự, phải kiểm tra ngữ nghĩa của hàm thời gian trong hệ thống lưu trữ đã chọn; tên gọi giống nhau không tự chứng minh nó phản ánh đúng thời điểm mà yêu cầu cần.

## 5. Ví dụ nghiệp vụ: tiêu thụ voucher một lần

### 5.1. Cách làm có khoảng hở

```text
voucher = read(voucher_id)
require voucher belongs to authenticated user
require voucher.state == AVAILABLE

grant_benefit()
write(voucher.state = REDEEMED)
```

Hai request có thể cùng vượt qua `require`, hoặc chủ sở hữu và trạng thái thay đổi sau khi được đọc. Nếu `grant_benefit()` đã tạo tác động khó đảo ngược, việc ghi trạng thái ở cuối không thể tự sửa hậu quả.

### 5.2. Cập nhật có điều kiện

Giả sử ví dụ giản lược chỉ có voucher thuộc một người dùng, không có thời hạn hoặc điều kiện chiến dịch khác. Một thao tác SQL minh họa có thể là:

```sql
UPDATE voucher
SET state = 'REDEEMED',
    redeemed_by = :verified_subject,
    redeemed_operation = :operation_id,
    version = version + 1
WHERE voucher_id = :voucher_id
  AND tenant_id = :verified_tenant
  AND owner_id = :verified_subject
  AND state = 'AVAILABLE'
  AND version = :expected_version;
```

Các tham số `verified_subject` và `verified_tenant` phải đến từ danh tính đã xác minh phía máy chủ. Cú pháp tham số ở đây mang tính minh họa, không giả định một thư viện truy cập dữ liệu cụ thể.

Với cơ chế cập nhật có điều kiện bảo đảm nhất quán phù hợp, chỉ giao dịch thực sự chuyển được bản ghi thỏa điều kiện mới được coi là thắng. Phải kiểm tra kết quả cập nhật, không giả định gọi câu lệnh thành công đồng nghĩa có một hàng được đổi.

- Nếu có đúng một hàng được chuyển và giao dịch cam kết, có thể tiếp tục theo hợp đồng cấp quyền lợi.
- Nếu không có hàng nào được chuyển, phải phân loại kết quả theo trạng thái có thẩm quyền: xung đột, không đủ quyền, phiên bản cũ hoặc thao tác đã hoàn tất trước đó.
- Không được cấp quyền lợi sau một cập nhật thất bại chỉ vì lần đọc trước đó từng hợp lệ.

Nếu việc ghi nhận voucher và cấp quyền lợi đều nằm trong cùng kho dữ liệu, chúng cần được cam kết nhất quán theo thiết kế. Nếu cấp quyền lợi là tác động bên ngoài, phải có trạng thái giữ chỗ hoặc ý định bền vững và quy trình tích hợp tương ứng; câu lệnh trên không tự làm tác động bên ngoài nguyên tử.

### 5.3. Giới hạn của ví dụ

Trong sản phẩm thật, điều kiện có thể còn phụ thuộc chiến dịch, ngân sách tổng, thời hạn, phiên bản chính sách và loại đơn hàng. Chỉ bảo vệ trường `version` của voucher không tự bảo vệ những đối tượng khác.

Mọi thay đổi có ý nghĩa đối với phiên bản phải cập nhật phiên bản theo cùng hợp đồng. Nếu một công cụ quản trị đổi chủ sở hữu nhưng không đổi phiên bản, kiểm tra phiên bản có thể không phát hiện được thay đổi đó. Điều kiện cần thiết nên được kiểm tra trực tiếp hoặc được ràng buộc bằng cơ chế phiên bản đầy đủ.

Idempotency cần được đặc tả riêng để gửi lại cùng thao tác có thể trả kết quả cũ mà không cấp quyền lợi lần nữa. Hai `operation_id` khác nhau vẫn phải tranh chấp cùng bất biến của voucher.

## 6. Chọn cơ chế theo bất biến và phạm vi

### 6.1. Giao dịch không tự giải quyết mọi TOCTOU

Đặt nhiều câu lệnh trong một giao dịch giúp xác định ranh giới cam kết, nhưng mức cô lập và cách truy cập dữ liệu quyết định các giao dịch khác có thể xen kẽ ra sao.

Ví dụ, hai giao dịch cùng đọc “còn một suất”, rồi ghi hai bản ghi khác nhau, có thể không tranh chấp cùng một hàng. Chỉ bảo vệ từng hàng được ghi chưa chắc giữ được bất biến tổng. Cần xác định tập dữ liệu, điều kiện tổng hợp và cơ chế bảo vệ các thay đổi có thể làm điều kiện đó sai.

Với từng hệ thống lưu trữ, phải xác nhận hành vi của mức cô lập và thao tác đã chọn. Những tên gọi như “transaction”, “snapshot” hoặc “lock” chưa đủ làm tiêu chí nghiệm thu.

Nếu dùng cơ chế tuần tự hóa có thể hủy một giao dịch khi xung đột, ứng dụng phải xử lý kết quả đó. Việc thử lại cần đọc lại dữ liệu và đánh giá lại các điều kiện nghiệp vụ; không chỉ gửi lại tác động dựa trên snapshot cũ.

### 6.2. Khóa phải có đúng phạm vi

Một khóa chỉ hữu ích nếu mọi thao tác có thể làm sai điều kiện đều tuân cùng giao thức bảo vệ trong phạm vi yêu cầu.

| Trường hợp | Điều dễ bị hiểu sai | Yêu cầu cần bổ sung |
|---|---|---|
| Khóa trong tiến trình | Tưởng bảo vệ cả cụm | Xác định instance khác và đường cập nhật khác được phối hợp thế nào |
| Khóa sau khi đã đọc | Dữ liệu đọc trước khóa vẫn có thể cũ | Kiểm tra lại dưới vùng bảo vệ phù hợp |
| Khóa một hàng | Bất biến liên quan nhiều hàng hoặc bản ghi chưa tồn tại | Bảo vệ đầy đủ tập đối tượng và điều kiện có liên quan |
| Khóa nhiều đối tượng | Chờ lẫn nhau hoặc giữ quá lâu | Thứ tự khóa, thời hạn chờ và xử lý thất bại |
| Gọi mạng khi đang giữ khóa | Tài nguyên bị giữ lâu khi dependency chậm | Quy trình giữ chỗ và ranh giới thực thi phù hợp |

Nếu không lấy được khóa hoặc bị timeout chờ khóa, không được tiếp tục như thể đã có quyền sử dụng tài nguyên. Phải trả trạng thái hoặc đưa công việc về bước chờ theo hợp đồng.

### 6.3. Kiểm tra phiên bản phải bao phủ điều kiện thật

Optimistic concurrency control dùng phiên bản để phát hiện đối tượng đã đổi kể từ khi được đọc. Cơ chế này cần:

- Phiên bản được kiểm tra trong chính thao tác cam kết thay đổi hoặc cơ chế tương đương.
- Mọi cập nhật có ảnh hưởng phải thay đổi phiên bản theo hợp đồng.
- Nếu điều kiện phụ thuộc nhiều đối tượng, phải bảo vệ đúng các phiên bản hoặc bất biến chung có liên quan.
- Khi xung đột, không tự nâng `expected_version` rồi tiếp tục dùng quyết định cũ.

Ví dụ, yêu cầu đã được duyệt ở phiên bản 12 không được tự đổi sang phiên bản 13 để vượt kiểm tra, nếu phiên bản 13 có số tiền hoặc nơi nhận khác. Xung đột phiên bản cần dẫn đến đánh giá lại và phê duyệt lại theo chính sách.

### 6.4. Giá trị giống cũ chưa chắc là cùng lịch sử

Một đối tượng có thể đi từ trạng thái A sang B rồi quay về A. Nếu chỉ so sánh giá trị trạng thái, hệ thống có thể không nhận ra rằng quyền hoặc điều kiện đã thay đổi giữa hai lần đọc. Đây thường được gọi là vấn đề ABA.

Phiên bản hoặc định danh thế hệ có thể giúp phân biệt lịch sử đó. Nếu đối tượng bị xóa rồi tạo lại, không nên mặc nhiên coi cùng tên và cùng số phiên bản nhỏ là cùng đối tượng cũ. Hợp đồng định danh cần phân biệt lần tồn tại hoặc thế hệ nếu yêu cầu phụ thuộc điều này.

### 6.5. Ràng buộc dữ liệu hỗ trợ giữ bất biến

Ràng buộc duy nhất, kiểm tra giá trị hoặc cập nhật có điều kiện có thể tạo lớp thực thi gần dữ liệu. Ví dụ, một sự kiện cấp quyền lợi có khóa nghiệp vụ duy nhất giúp ngăn ghi nhận trùng trong phạm vi đó.

Tuy nhiên, ràng buộc duy nhất trên `operation_id` không tự ngăn hai thao tác khác nhau cùng dùng một voucher. Mỗi ràng buộc phải được đối chiếu với bất biến thực sự cần giữ. Không suy ra bảo đảm toàn quy trình từ một ràng buộc bảo vệ phạm vi hẹp hơn.

## 7. TOCTOU với tệp và đối tượng upload

### 7.1. Đường dẫn không phải danh tính bất biến

Một chuỗi đường dẫn có thể được phân giải tới các đối tượng khác nhau ở các thời điểm khác nhau. Tên tệp có thể bị đổi, tham chiếu có thể bị thay thế và thư mục trung gian có thể thay đổi tùy môi trường.

Mẫu kiểm tra rồi mở lại dễ tạo khoảng hở:

```text
require path is allowed
require file_at(path) passed inspection

later:
    process(open(path))
```

Kiểm tra chuỗi đường dẫn hoặc chuẩn hóa cú pháp chưa chứng minh đối tượng cuối cùng nằm trong phạm vi được phép và chính là đối tượng đã được kiểm tra. Việc chỉ chặn một kiểu tham chiếu ở thành phần cuối cũng chưa tự bao phủ mọi thành phần trung gian hoặc các cách định danh khác của nền tảng.

Yêu cầu nên nói rõ tài nguyên phải được mở trong phạm vi được phép bằng cơ chế của nền tảng, xác minh đúng loại đối tượng và duy trì liên kết đáng tin cậy tới đối tượng đó. Nếu mục tiêu là tạo một tệp mới độc quyền, cần thao tác tạo có bảo đảm không ghi đè đối tượng đã tồn tại; kiểm tra “chưa tồn tại” rồi mới tạo là một khoảng hở khác.

### 7.2. Cùng handle chưa chắc cùng nội dung

Giữ một handle tới đối tượng có thể tránh việc phân giải lại tên tới đối tượng khác. Tuy nhiên, nội dung của đối tượng vẫn có thể bị sửa nếu còn bên có quyền ghi. Cần phân biệt hai yêu cầu:

1. Sử dụng đúng đối tượng đã được xác minh danh tính.
2. Sử dụng đúng phiên bản byte đã được kiểm tra.

Tùy trường hợp, cần nội dung bất biến, snapshot, vùng lưu trung gian có quyền ghi được kiểm soát hoặc cơ chế khóa phù hợp. Không kết luận một tệp đã an toàn chỉ vì ứng dụng mở nó một lần.

### 7.3. Ví dụ pipeline quét và xử lý upload

Một hợp đồng dữ liệu minh họa có thể liên kết kết quả quét với:

```text
tenant_id
artifact_id
artifact_generation_or_version
content_digest
content_size
inspection_policy_version
verdict
```

Quy trình yêu cầu:

1. Nhận dữ liệu vào một phiên bản đối tượng không bị sửa trong suốt chu kỳ kiểm tra và sử dụng.
2. Bộ kiểm tra đọc đúng phiên bản đó và tạo kết quả được xác minh nguồn.
3. Kết quả kiểm tra được gắn với định danh, phiên bản và nội dung tương ứng.
4. Worker chỉ chuyển sang xử lý khi trạng thái, quyền và phiên bản thỏa điều kiện đã công bố.
5. Worker sử dụng đúng phiên bản đã được kiểm tra, không tự phân giải lại một tên có thể trỏ sang phiên bản mới.

Digest hỗ trợ liên kết nội dung nhưng không thay thế việc bảo vệ nguồn kết quả và định danh. Không tin một digest do client tự khai là bằng chứng bộ kiểm tra đã đọc dữ liệu tương ứng.

Nếu chính sách kiểm tra hết hiệu lực hoặc bị thu hồi, cần quy định kết quả cũ còn được dùng hay phải kiểm tra lại. Nếu byte thay đổi, kết quả cho phiên bản cũ không được tự động chuyển sang phiên bản mới.

## 8. Hàng đợi và tác động bên ngoài

### 8.1. Đã xếp hàng không có nghĩa mọi điều kiện còn đúng

Một job có thể được tạo khi đối tượng ở trạng thái hợp lệ nhưng chỉ chạy sau khi quyền đã bị thu hồi, đối tượng đã bị hủy hoặc nội dung đã đổi. Payload trong hàng đợi là bằng chứng về yêu cầu đã được tạo, không tự chứng minh điều kiện thực thi hiện tại.

Hợp đồng job cần xác định:

- Danh tính người yêu cầu và quyền đại diện của worker.
- Đối tượng, tenant, phiên bản và nội dung được phép thực hiện.
- Điều kiện được chốt lúc nhận việc và điều kiện phải đánh giá lại lúc chạy.
- Thời hạn quyền thực thi, khả năng thu hồi và trạng thái khi không còn đủ điều kiện.
- Hành vi khi công việc được nhận lại, xử lý trùng hoặc không biết tác động đã xảy ra hay chưa.

Một chữ ký trên payload giúp xác minh thông tin theo cơ chế đã chọn, nhưng không tự chứng minh quyền còn hiệu lực tại thời điểm chạy. Nếu sản phẩm yêu cầu thu hồi ngay, phải có cách kiểm tra hoặc sắp thứ tự thu hồi phù hợp; chỉ giữ một payload đã ký trong thời gian dài không đáp ứng yêu cầu đó.

### 8.2. Giữ chỗ thay cho việc dựa vào một lần đọc cũ

Khi cần chuyển từ dữ liệu nội bộ sang tác động bên ngoài, có thể cần trạng thái giữ chỗ. Ví dụ, ngân sách được giữ bằng quyết định nội bộ nhất quán, rồi một công việc có định danh thực hiện tác động tương ứng.

Giữ chỗ phải có chủ sở hữu, phạm vi, trạng thái và cách giải phóng. Nếu bên ngoài chưa trả kết quả, không tự coi việc chờ quá hạn là bằng chứng tác động chưa xảy ra. Giải phóng sớm có thể cho một công việc khác dùng lại ngân sách trong khi công việc cũ vẫn hoàn tất.

Một cơ chế lưu ý định gửi cùng giao dịch nội bộ giúp tránh mất công việc đã cam kết. Nó không tự giải quyết việc nội dung hoặc quyền thay đổi trước khi worker gửi đi. Quy trình phải chọn rõ quyền nào đã được chốt và điều kiện nào cần được đánh giá lại.

### 8.3. Lease và fencing có phạm vi bảo đảm

Nếu một worker giữ lease để thực thi, lease hết hạn không tự chứng minh worker đã dừng. Worker cũ có thể mất liên lạc với bộ điều phối nhưng vẫn gọi được tài nguyên đích.

Fencing token có thể hỗ trợ khi tài nguyên đích kiểm tra thứ tự hoặc thế hệ của chủ sở hữu và từ chối thao tác từ chủ sở hữu cũ theo đúng hợp đồng. Token chỉ được ghi vào log, nhưng không được thực thi tại nơi tạo tác động, không tạo ra bảo đảm này.

Ngay cả khi có fencing, cần xác định tác động đã bắt đầu được xử lý ra sao. Một token mới không tự đảo ngược công việc đã cam kết hoặc dừng một tác động không hỗ trợ thu hồi. Nếu tài nguyên đích không có cơ chế cần thiết, phải mô tả giới hạn và chọn quy trình đối soát, hạn chế cấp mới hoặc giữ chỗ phù hợp.

### 8.4. Điều kiện ở hệ thống đích

Nếu quyết định phụ thuộc trạng thái ở một dịch vụ khác, kiểm tra tại nguồn rồi gọi API đích có thể tạo một TOCTOU xuyên dịch vụ. API đích có thể cần hỗ trợ điều kiện phiên bản, chuyển trạng thái nguyên tử hoặc một quyền thực thi bị ràng buộc.

Đặc tả phải xác định nơi có thẩm quyền quyết định và nơi cưỡng chế điều kiện. Không giả định khóa trong dịch vụ A ngăn được mọi thay đổi tại dịch vụ B khi B không tham gia cùng giao thức.

## 9. Cache phân quyền và ngữ nghĩa thu hồi

### 9.1. Tuổi cache là một phần của hợp đồng

Nếu quyền hoặc quan hệ sở hữu được cache, phải định nghĩa cửa sổ cũ tối đa và phạm vi chấp nhận. Ví dụ, một sản phẩm có thể cho phép quyết định dựa trên quyền cũ trong tối đa 5 giây sau khi quyết định thu hồi được cam kết tại nguồn có thẩm quyền. Đây là một cam kết khác với thu hồi tức thì.

Với ví dụ cửa sổ 5 giây, cần xác định:

- Mốc bắt đầu là thời điểm nào ở nguồn có thẩm quyền.
- Hành động nào không được bắt đầu hoặc không được cam kết sau mốc giới hạn.
- Cách xử lý job đã nhận và tác động đã cam kết trước đó.
- Ngân sách truyền thay đổi, tuổi cache và sai lệch thời gian được tính ra sao.
- Hành vi khi không xác minh được dữ liệu còn nằm trong cửa sổ cho phép.

Con số 5 giây là ví dụ đặc tả, không phải khuyến nghị chung. Những thao tác khác nhau có thể cần hợp đồng khác nhau theo tác động và khả năng của kiến trúc.

### 9.2. Vô hiệu hóa cache cũng có race

Một request có thể đọc dữ liệu cũ, sau đó sự kiện thu hồi làm xóa cache, rồi request đầu tiên lại ghi dữ liệu cũ vào cache. Vì vậy, chỉ phát sự kiện “xóa cache” chưa chứng minh quyền cũ không được dùng lại.

Cần cơ chế phiên bản, thế hệ chính sách, kiểm tra tuổi hoặc cách đồng bộ phù hợp với cam kết. Các giá trị trong cache phải liên kết với đúng tenant, chủ thể, đối tượng và phạm vi quyền; khóa cache thiếu ngữ cảnh có thể tạo thêm lỗi cách ly dữ liệu.

Nếu không thể xác minh quyền theo mức bảo đảm yêu cầu, cần hành vi cụ thể như từ chối thao tác nhạy cảm hoặc đưa về trạng thái chờ xác minh. Không âm thầm chuyển sang cho phép vì hệ thống danh tính tạm thời không truy cập được.

## 10. Đặc tả xử lý xung đột, lỗi và quan sát

### 10.1. Phân biệt kết quả

Các kết quả cần được phân biệt khi có ý nghĩa với API hoặc quy trình:

| Kết quả | Ý nghĩa | Hành vi cần quy định |
|---|---|---|
| Xung đột phiên bản | Dữ liệu đã đổi từ lần đọc | Đọc lại, đánh giá lại hoặc yêu cầu phê duyệt lại |
| Điều kiện không còn thỏa | Hết ngân sách, bị hủy, hết hạn hoặc đã dùng | Không tiếp tục tác động theo quyết định cũ |
| Không đủ quyền | Chủ thể không được thực hiện ở phạm vi hiện tại | Từ chối theo chính sách, tránh tiết lộ đối tượng nhạy cảm |
| Chưa biết kết quả | Tác động bên ngoài có thể đã xảy ra | Giữ trạng thái và đối soát, không gửi lại mù quáng |
| Cùng thao tác đã hoàn tất | Request gửi lại thuộc hợp đồng idempotency | Trả hoặc tham chiếu kết quả cũ theo quyền hiện hành |
| Không thể xác minh điều kiện | Nguồn có thẩm quyền không khả dụng | Áp dụng chính sách lỗi đã được chọn và có giới hạn |

Thử lại phải có giới hạn và đánh giá lại toàn bộ điều kiện liên quan. Không lặp vô hạn khi xung đột và không thay phiên bản mong đợi chỉ để làm request được chấp nhận.

### 10.2. Bằng chứng cần giữ

Audit hoặc dấu vết nghiệp vụ cần đủ để dựng lại quyết định: danh tính và tenant, thao tác, định danh và thế hệ đối tượng, phiên bản được kiểm tra, điều kiện quyết định, phiên bản đã cam kết, kết quả, mã liên kết và thời điểm theo nguồn đã định.

Với tác động bên ngoài, cần tham chiếu tới ý định thực thi, lần gửi, phản hồi, callback và kết quả đối soát. Với tệp, cần liên kết kết quả kiểm tra với đúng phiên bản nội dung.

Không ghi bí mật, token hoặc toàn bộ payload nhạy cảm để thay thế thiết kế audit. Quyền đọc, sửa, xuất và thời hạn lưu bằng chứng phải được đặc tả theo nhu cầu.

### 10.3. Chỉ số không thay thế cưỡng chế

Các chỉ số hữu ích gồm số xung đột có điều kiện, số lần từ chối vì phiên bản cũ, số job bị hủy trước thực thi, số quyền cũ bị phát hiện, số trạng thái chưa xác định và tuổi tồn đọng đối soát.

Chỉ số xung đột cao không tự chứng minh có tấn công; nó có thể đến từ tải hợp lệ hoặc thiết kế gây tranh chấp. Ngược lại, không có log xung đột không chứng minh không có TOCTOU nếu một đường gọi chưa được bảo vệ.

Việc phát hiện sau đó rằng quyền lợi đã cấp hai lần là cơ chế quan sát và khắc phục. Nếu yêu cầu là ngăn cấp trùng tại thời điểm thực thi, chỉ có cảnh báo sau sự kiện chưa đáp ứng yêu cầu đó.

## 11. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây là những mẫu cho các phạm vi khác nhau. Khi áp dụng, cần chọn đúng mô hình quyền và thay các tham chiếu bằng tài sản, chính sách, điểm cam kết và tham số của dự án.

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| TC-01 | Mỗi thao tác nhạy cảm phải xác định điều kiện quyết định, nguồn có thẩm quyền, đối tượng, phạm vi và điểm có hiệu lực; mọi đường làm thay đổi điều kiện phải được đưa vào thiết kế | Ma trận thao tác, đường ghi và điểm cam kết |
| TC-02 | Voucher dùng một lần chỉ được tạo tối đa một quyền lợi đã cam kết; việc kiểm tra khả dụng và ghi nhận tiêu thụ phải có bảo đảm nhất quán trong phạm vi cam kết | Hai thao tác khác nhau tranh chấp cùng voucher |
| TC-03 | Một quyết định dựa trên phiên bản chỉ được cam kết khi đúng đối tượng, thế hệ và các phiên bản liên quan còn thỏa; xung đột không được tự đổi phiên bản rồi dùng quyết định cũ | Đổi nội dung, đổi thế hệ và nhiều đối tượng phụ thuộc |
| TC-04 | Phê duyệt phải gắn với nội dung và phiên bản cụ thể; thay trường nhạy cảm phải vô hiệu hóa hoặc yêu cầu phê duyệt lại theo chính sách | Thay số tiền hoặc nơi nhận giữa phê duyệt và thực thi |
| TC-05 | Với thao tác có hợp đồng thu hồi tức thì, thu hồi và thực thi phải được sắp thứ tự tại phạm vi cam kết; thao tác chưa cam kết sau quyết định thu hồi không được dùng quyền cũ | Lịch xen kẽ và bằng chứng thứ tự cam kết |
| TC-06 | Job nền phải mang tham chiếu tới đối tượng, phiên bản và quyền thực thi; worker phải thực hiện đúng mô hình quyền đã chọn khi trạng thái thay đổi trong lúc chờ | Hủy, sửa đối tượng và thu hồi quyền trước khi chạy |
| TC-07 | Kết quả kiểm tra upload chỉ được dùng cho đúng tenant, đối tượng, phiên bản nội dung và chính sách tương ứng; worker không tự chuyển sang dữ liệu mới theo một tên có thể thay đổi | Thay tham chiếu hoặc nội dung giữa kiểm tra và xử lý |
| TC-08 | Cơ chế mở hoặc tạo tệp phải đáp ứng phạm vi truy cập và tính duy nhất yêu cầu bằng bảo đảm của nền tảng; kiểm tra tên trước rồi thao tác tên sau không được coi là đủ | Thay đối tượng, thay thành phần đường dẫn và tranh chấp tạo tệp |
| TC-09 | Timeout hoặc lease hết hạn không tự chứng minh tác động bên ngoài chưa xảy ra; phần tài nguyên giữ chỗ chỉ được giải phóng theo bằng chứng và quy trình đã định | Worker mất liên lạc nhưng bên ngoài vẫn thực hiện |
| TC-10 | Thử lại phải có giới hạn, đọc và đánh giá lại điều kiện khi cần; gửi lại cùng thao tác không tạo thêm tác động theo hợp đồng idempotency | Xung đột, phản hồi bị mất và xử lý công việc trùng |
| TC-11 | Cache phải có ngữ nghĩa hiệu lực và thu hồi đo được; mất dữ liệu có thẩm quyền không được tự chuyển sang cho phép vượt mức bảo đảm đã chọn | Cache cũ, điền lại cache sau vô hiệu hóa và mất kết nối |
| TC-12 | Audit phải liên kết quyết định kiểm tra với phiên bản và tác động đã cam kết, đồng thời bảo vệ dữ liệu nhạy cảm và quyền truy cập | Đối chiếu một thao tác qua các thành phần và kiểm tra quyền audit |

TC-05 là mẫu cho mô hình thu hồi tức thì. Nếu sản phẩm chấp nhận cửa sổ cũ như ví dụ 5 giây, phải thay yêu cầu đó bằng cam kết có giới hạn thời gian rõ ràng và kiểm thử theo đúng mô hình. Không giữ đồng thời hai yêu cầu có ngữ nghĩa mâu thuẫn rồi để đội triển khai tự chọn.

Các yêu cầu về thời hạn, số lần retry, thời gian đối soát và khả năng tiếp tục của job phải có giá trị cụ thể trong đặc tả triển khai. Các giá trị phụ thuộc rủi ro và kiến trúc nên không được suy từ một ví dụ trong bài thành chuẩn chung.

## 12. Kiểm thử bằng lịch xen kẽ có kiểm soát

### 12.1. Không chỉ kiểm thử bằng tải ngẫu nhiên

Kiểm thử tải có thể phát hiện race nhưng không bảo đảm một lịch xen kẽ quan trọng đã xảy ra. Nên dùng điểm đồng bộ, hàng rào giữa các luồng hoặc thành phần thử nghiệm để chủ động dừng thao tác sau bước đọc và trước điểm cam kết.

Không nên phụ thuộc duy nhất vào một khoảng `sleep` cố định. Tốc độ môi trường thay đổi có thể khiến các thao tác chạy lần lượt và bài thử vẫn báo thành công dù chưa kích hoạt khoảng hở.

Bằng chứng cần bao gồm kết quả các thao tác, trạng thái bền vững và tác động nghiệp vụ. Với quyền lợi hoặc lời gọi bên ngoài, phải đếm tác động thật chứ không chỉ đếm dòng trạng thái cuối.

### 12.2. Hai thao tác tiêu thụ một voucher

```gherkin
Given voucher thuộc tenant A và người dùng U
And voucher ở trạng thái AVAILABLE, version = 7
And không có lỗi hạ tầng trong bài thử
When hai thao tác khác nhau cùng đọc trạng thái này
And cả hai được cho tiếp tục cạnh tranh việc cam kết tiêu thụ
Then chỉ một giao dịch cam kết việc tiêu thụ voucher
And chỉ một quyền lợi nghiệp vụ được cấp
And thao tác còn lại nhận kết quả theo hợp đồng xung đột
And audit liên kết được từng thao tác với kết quả tương ứng
```

Dùng hai định danh thao tác khác nhau để bài thử không chỉ kiểm tra idempotency. Thêm trường hợp gửi lại chính thao tác thắng để chứng minh kết quả cũ không tạo quyền lợi bổ sung.

### 12.3. Thu hồi quyền giữa kiểm tra và thực thi

Với mô hình thu hồi tức thì, cho thao tác A đọc quyền hợp lệ, sau đó yêu cầu B thu hồi quyền. Quan sát thứ tự cam kết thực tế:

- Nếu B cam kết trước điểm hiệu lực của A, A không được tạo tác động bằng quyền cũ.
- Nếu cơ chế bảo vệ sắp thứ tự để A cam kết trước rồi B mới hoàn tất, kết quả của A phải phù hợp với thứ tự đó.

Harness kiểm thử phải cho phép quan sát việc B bị chặn do tuần tự hóa và giải phóng điểm đồng bộ đúng cách. Không tạo bài thử chờ B hoàn tất vĩnh viễn trong khi chính bài thử đang giữ A tại vùng khóa mà B cần.

Đối với mô hình cửa sổ cũ có giới hạn, kiểm tra ở các mốc trước, tại và sau biên hiệu lực theo quy tắc thời gian đã công bố. Kết quả phải được đo từ nguồn có thẩm quyền, không chỉ từ lúc giao diện người quản trị hiển thị thông báo.

### 12.4. Đổi nội dung hoặc thế hệ đối tượng

Tạo một yêu cầu đã duyệt ở phiên bản 12, tạm dừng trước thực thi và đổi trường nhạy cảm để tạo phiên bản 13. Thao tác cũ phải bị từ chối hoặc đưa về quy trình duyệt lại theo hợp đồng, không tự chấp nhận phiên bản mới.

Thêm hai biến thể:

1. Trạng thái thay đổi từ A sang B rồi quay lại A nhưng phiên bản đã tăng. Quyết định ràng buộc với phiên bản cũ phải được phát hiện là cũ.
2. Đối tượng bị xóa rồi tạo một thế hệ mới dưới cùng tên hoặc mã được phép tái sử dụng. Tham chiếu gắn với thế hệ cũ không được tự chuyển sang thế hệ mới.

### 12.5. Đổi dữ liệu sau kiểm tra upload

```gherkin
Given phiên bản nội dung V1 có kết quả kiểm tra hợp lệ
And worker chưa bắt đầu xử lý
When một tên tham chiếu được đổi để trỏ tới V2
And V2 chưa có kết quả kiểm tra tương ứng
Then worker chỉ có thể xử lý V1 nếu mọi điều kiện khác vẫn hợp lệ
Or từ chối và yêu cầu kiểm tra V2 theo chính sách đã chọn
And worker không dùng kết quả của V1 để cho phép xử lý V2
```

Kiểm tra riêng khả năng sửa nội dung tại chỗ. Nếu thiết kế dựa vào tính bất biến, thao tác sửa phải bị ngăn hoặc tạo phiên bản mới có định danh khác. Một kết quả chỉ đúng khi không có ai sửa nội dung chưa đủ nếu quyền ghi thực tế vẫn cho phép sửa.

### 12.6. Trạng thái chưa xác định ở hệ thống ngoài

Cho worker gửi một tác động có định danh, để bên ngoài thực hiện nhưng giữ hoặc làm mất phản hồi. Sau khi worker timeout, gửi lại công việc hoặc để lease hết hạn.

Xác minh hệ thống không giải phóng rồi cấp lại cùng tài nguyên chỉ vì mất phản hồi; mọi lần thử lại tuân idempotency và hợp đồng với tài nguyên đích. Khi có kết quả đối soát, trạng thái nội bộ phải phản ánh đúng tác động đã xảy ra mà không ghi nhận hai lần.

### 12.7. Điều kiện trên nhiều đối tượng và đường ghi khác

Tạo hai thao tác sửa các hàng khác nhau nhưng cùng ảnh hưởng một bất biến tổng, như ngân sách chiến dịch hoặc số suất còn lại. Kiểm tra cơ chế bảo vệ cả tổng, thay vì chỉ chứng minh không có hai thao tác ghi cùng một hàng.

Lặp các lịch quan trọng qua API công khai, công cụ quản trị, worker và tác vụ bảo trì thuộc phạm vi. Nếu một đường cập nhật bỏ qua phiên bản hoặc giao thức khóa, phải xem đó là vi phạm yêu cầu, không coi là ngoại lệ kỹ thuật tự động được phép.

## 13. Truy vết yêu cầu tới kiến trúc và vòng đời phát triển

| Rủi ro | Yêu cầu liên quan | Thành phần có trách nhiệm | Kiểm chứng chính |
|---|---|---|---|
| Cấp trùng quyền lợi | TC-02, TC-03, TC-10 | Dịch vụ nghiệp vụ, kho dữ liệu và tích hợp | Cập nhật cạnh tranh, ledger và tác động thật |
| Dùng quyền sau thu hồi trái hợp đồng | TC-05, TC-06, TC-11 | Nguồn quyền, cache, hàng đợi và điểm thực thi | Thứ tự thu hồi, tuổi quyền và điểm cam kết |
| Thực thi nội dung chưa được duyệt | TC-03, TC-04 | Dịch vụ phê duyệt và worker | Phiên bản nội dung duyệt so với nội dung thực thi |
| Xử lý đối tượng khác đối tượng đã kiểm tra | TC-07, TC-08 | Lưu trữ, bộ kiểm tra và bộ xử lý | Định danh, thế hệ và phiên bản byte |
| Worker cũ tiếp tục sau mất liên lạc | TC-09, TC-10 | Bộ điều phối và tài nguyên đích | Tác động cũ, quyền thực thi mới và đối soát |
| Không giải thích được quyết định | TC-01, TC-12 | Chủ yêu cầu và hệ thống audit | Chuỗi bằng chứng từ kiểm tra tới tác động |

Ở giai đoạn phân tích, mô tả use case hợp lệ và biến thể trong đó điều kiện thay đổi giữa các bước. Chốt bất biến và mô hình hiệu lực quyền với chủ nghiệp vụ; không suy chúng chỉ từ thứ tự màn hình.

Ở giai đoạn thiết kế, chỉ rõ điểm quyết định, nguồn có thẩm quyền, tập đối tượng tranh chấp và ranh giới giao dịch. Với dữ liệu bên ngoài hoặc tệp, xác định định danh và phiên bản được kiểm tra, được giữ và được sử dụng.

Ở giai đoạn triển khai và nghiệm thu, liên kết mã yêu cầu với các thao tác có điều kiện, cấu hình quyền, giao thức khóa hoặc trạng thái giữ chỗ. Bài thử cần có lịch xen kẽ, lỗi mạng, worker khởi động lại và các đường cập nhật khác nhau.

Ở giai đoạn vận hành, theo dõi xung đột, quyền cũ, job chưa xác định kết quả và sai lệch đối soát. Khi thêm instance, API, cache, tác vụ nền hoặc công cụ sửa dữ liệu, đánh giá lại phạm vi bảo đảm. Một đường ghi mới có thể phá vỡ giả định mọi bên cùng tuân giao thức cũ.

## 14. Những lỗi đặc tả thường gặp

| Cách đặc tả dễ gây lỗi | Khoảng hở còn lại | Cách làm rõ |
|---|---|---|
| “Kiểm tra lại ngay trước khi ghi” | Vẫn có thay đổi giữa hai bước | Gắn điều kiện với thao tác cam kết hoặc bảo vệ cùng phạm vi |
| “Đã bọc transaction nên không có race” | Mức cô lập và tập dữ liệu có thể chưa bảo vệ bất biến | Chỉ rõ tranh chấp cần bị tuần tự hóa hoặc phát hiện |
| “Có lock là đủ” | Lock local hoặc một đường ghi khác bỏ qua | Xác định phạm vi, mọi bên ghi và hành vi khi không lấy được lock |
| “Có version của bản ghi chính” | Điều kiện phụ thuộc đối tượng khác hoặc thời gian | Bảo vệ đầy đủ các điều kiện có thể làm quyết định sai |
| “Xung đột thì lấy version mới rồi thử tiếp” | Quyết định hoặc phê duyệt cũ bị chuyển sang nội dung mới | Đánh giá lại điều kiện và yêu cầu duyệt lại khi cần |
| “Đường dẫn đã kiểm tra nên mở lại được” | Tên có thể trỏ tới đối tượng khác | Ràng buộc đối tượng và phạm vi truy cập bằng cơ chế nền tảng |
| “Giữ handle là giữ nguyên byte” | Nội dung vẫn có thể được sửa | Đặc tả tính bất biến hoặc snapshot và quyền ghi |
| “Lease hết hạn nghĩa là worker đã chết” | Worker cũ vẫn có thể tạo tác động | Cưỡng chế tại tài nguyên hoặc giữ trạng thái chờ đối soát |
| “Token còn hạn nên quyền chưa bị thu hồi” | Thời hạn token và chính sách thu hồi có thể khác nhau | Chọn và thực thi ngữ nghĩa hiệu lực cụ thể |
| “Trạng thái cuối đúng nên không có lỗi” | Hai tác động đã xảy ra trước khi ghi cùng một trạng thái | Đếm tác động thật và dựng lại lịch cam kết |

## 15. Bài tập tự kiểm tra

Một hệ thống kiểm tra người dùng còn quyền xuất báo cáo, ghi một job gồm đường dẫn tệp và số tiền được duyệt, rồi trả phản hồi chấp nhận. Sau đó quản trị viên thu hồi quyền, nhân viên sửa số tiền và một tiến trình khác thay nội dung dưới cùng đường dẫn. Worker chỉ kiểm tra job có chữ ký hợp lệ, mở đường dẫn và thực thi. Khi gọi bên ngoài timeout, worker giải phóng giữ chỗ và cho phép một job mới chạy.

Hãy thực hiện các việc sau:

1. Xác định từng bước check, use và trạng thái có thể thay đổi giữa chúng.
2. Chọn ngữ nghĩa hiệu lực quyền và thời điểm quyết định cho job này.
3. Viết bất biến gắn nội dung thực thi với đúng phê duyệt và phiên bản dữ liệu.
4. Đặc tả cơ chế bảo vệ dữ liệu nội bộ, tệp và tác động bên ngoài theo đúng phạm vi.
5. Chỉ ra điều chữ ký payload chứng minh được và điều nó không tự chứng minh.
6. Viết một lịch kiểm thử thu hồi quyền, một lịch đổi nội dung và một lịch mất phản hồi bên ngoài.
7. Xác định bằng chứng cần có trước khi cho phép dùng lại phần tài nguyên đã giữ.

Một lời giải đầy đủ phải nói rõ điều kiện nào được chốt, điều kiện nào phải được đánh giá lại và nơi nào thực sự cưỡng chế quyết định. Yêu cầu chống TOCTOU có thể kiểm chứng khi kết quả kiểm tra được gắn với đúng đối tượng, phiên bản và thời điểm có hiệu lực của tác động, thay vì chỉ yêu cầu các bước kiểm tra xuất hiện gần nhau trong mã.
