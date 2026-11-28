# Khác biệt giữa security requirement và security control

## 1. Vì sao cần phân biệt?

Một nhóm phát triển ghi trong tài liệu: “Dùng JWT, bật HTTPS, thêm MFA và cài công cụ giám sát”. Danh sách này nêu một số biện pháp bảo vệ, nhưng chưa trả lời đầy đủ:

- Tài sản nào cần được bảo vệ và trước hành vi đe dọa nào?
- Ai được phép thực hiện hành động nào, trên đối tượng nào?
- Mức bảo vệ cần đạt là gì, trong phạm vi và điều kiện nào?
- Dựa vào kết quả kiểm tra nào để chấp nhận hệ thống?

Nếu chỉ chọn công cụ, nhóm có thể triển khai đúng công cụ nhưng vẫn bỏ sót hành vi cần bảo vệ. Ví dụ, API xác minh được chữ ký JWT nhưng vẫn trả đơn hàng của người khác khi người dùng đổi `orderId`.

Nếu chỉ nêu mong muốn “dữ liệu phải an toàn”, nhóm lại thiếu căn cứ để thiết kế và kiểm thử. Cần chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành yêu cầu cụ thể, rồi chọn biện pháp đáp ứng yêu cầu ấy.

Trong chương **Nền tảng yêu cầu bảo mật**, bài này làm rõ hai khái niệm:

> **Security requirement** là điều kiện hoặc hành vi bảo mật mà hệ thống, tổ chức hay quy trình bắt buộc phải đáp ứng trong một phạm vi xác định.
>
> **Security control** là biện pháp được lựa chọn và vận hành để phòng ngừa, phát hiện, ứng phó hoặc khôi phục trước rủi ro bảo mật.

Có thể dịch tương ứng là **yêu cầu bảo mật** và **biện pháp kiểm soát bảo mật**. Quan hệ cốt lõi là: yêu cầu xác định nghĩa vụ cần đáp ứng; biện pháp giúp thực hiện nghĩa vụ đó.

## 2. Phân biệt theo vai trò của từng khái niệm

| Khía cạnh | Security requirement | Security control |
| --- | --- | --- |
| Câu hỏi chính | Điều gì bắt buộc phải đúng? | Dùng biện pháp nào để đạt và duy trì điều đó? |
| Vai trò | Làm căn cứ thiết kế, nghiệm thu và quản lý thay đổi | Tác động vào rủi ro hoặc hỗ trợ đáp ứng yêu cầu |
| Cách mô tả thường gặp | Chủ thể, hành động, tài sản, điều kiện, giới hạn, kết quả mong đợi | Cơ chế, quy trình, cấu hình, trách nhiệm vận hành |
| Ví dụ | Người dùng chỉ được đọc đơn hàng thuộc phạm vi họ được cấp quyền | Kiểm tra quyền ở máy chủ và truy vấn dữ liệu theo phạm vi được phép |
| Cách đánh giá | Đối chiếu hành vi thực tế với tiêu chí chấp nhận | Kiểm tra tính phù hợp, triển khai, cấu hình, phạm vi bao phủ và vận hành |
| Lý do thay đổi | Thay đổi rủi ro, nghiệp vụ, nghĩa vụ hoặc mức bảo vệ cần đạt | Thay đổi kiến trúc, công nghệ, cách tấn công hoặc hiệu quả vận hành |

Bảng này diễn tả vai trò, không tạo ra ranh giới tuyệt đối theo từ ngữ. Không thể kết luận một câu là requirement hay control chỉ vì nó có chữ “phải”, “mã hóa” hoặc tên một sản phẩm.

### 2.1. Requirement không chỉ là mong muốn chung

“Mọi dữ liệu phải được bảo vệ” là mục tiêu định hướng. Nó thiếu phạm vi dữ liệu, loại truy cập, điều kiện bảo vệ và căn cứ kiểm chứng.

“Người dùng chưa xác thực không được đọc nội dung đơn hàng qua các API dành cho khách hàng” là một yêu cầu cụ thể hơn: đã nêu chủ thể, tài sản, kênh truy cập và hành vi bị cấm.

Yêu cầu có thể mang tính:

- **Chức năng:** hệ thống từ chối một thao tác không được cấp quyền, ghi nhận một sự kiện hoặc thu hồi một phiên.
- **Chất lượng hay ràng buộc vận hành:** thời gian thu hồi có hiệu lực, thời gian phát hiện, giới hạn mất dữ liệu hoặc thời gian khôi phục.

Không nên mặc định mọi yêu cầu bảo mật đều là “phi chức năng”.

### 2.2. Control không chỉ là phần mềm

Biện pháp kiểm soát có thể thuộc nhiều dạng:

- **Kỹ thuật:** kiểm tra quyền truy cập, mã hóa, giới hạn tốc độ, sao lưu, cô lập mạng.
- **Quản trị và quy trình:** phê duyệt cấp quyền, rà soát quyền định kỳ, phân công người xử lý cảnh báo.
- **Vật lý:** kiểm soát ra vào khu vực chứa thiết bị hoặc bảo vệ phương tiện sao lưu.

Một control còn có thể gồm nhiều thành phần phối hợp. “Ứng phó với đăng nhập bất thường” có thể cần dữ liệu sự kiện, quy tắc phát hiện, cảnh báo, người trực và quy trình xử lý. Chỉ cài bộ thu thập log chưa hoàn thành toàn bộ biện pháp đó.

### 2.3. Một cơ chế có thể được viết thành yêu cầu bắt buộc

Xét hai câu:

- “MFA là một control tăng cường xác thực.”
- “Tài khoản quản trị bắt buộc sử dụng MFA trước khi truy cập trang quản trị.”

Câu thứ nhất phân loại biện pháp. Câu thứ hai đặt nghĩa vụ triển khai và áp dụng biện pháp ấy cho một phạm vi cụ thể. Chúng có thể cùng đúng.

Một yêu cầu có thể chỉ định cơ chế vì chính sách nội bộ, hợp đồng, ràng buộc tích hợp hoặc quyết định kiến trúc đã được chấp thuận. Khi đó cần ghi rõ nguồn ràng buộc và điều kiện áp dụng. Đừng loại bỏ yêu cầu chỉ vì nó chứa tên một control.

Tuy nhiên, câu “bật MFA” vẫn có thể thiếu khả năng kiểm chứng nếu chưa biết áp dụng cho ai, ở luồng nào, xử lý tài khoản khôi phục ra sao và các đường truy cập thay thế có được bao phủ hay không.

## 3. Từ rủi ro đến yêu cầu, biện pháp và bằng chứng

Một chuỗi lập luận hữu ích là:

**Tài sản và bối cảnh → đe dọa và rủi ro → mục tiêu bảo vệ → yêu cầu → biện pháp → thiết kế và triển khai → kiểm chứng và bằng chứng.**

Các phần không đồng nghĩa với nhau:

| Thành phần | Ví dụ trong hệ thống quản lý đơn hàng |
| --- | --- |
| Tài sản | Nội dung đơn hàng và thông tin giao nhận của khách hàng |
| Đe dọa | Người dùng đã đăng nhập thay mã đơn hàng để đọc dữ liệu ngoài quyền của mình |
| Rủi ro | Rò rỉ thông tin khách hàng và mất tính bí mật của dữ liệu giao dịch |
| Mục tiêu | Duy trì cách ly truy cập giữa khách hàng và giữa các tenant |
| Yêu cầu | Máy chủ phải từ chối đọc đơn hàng nếu chủ thể không có quyền với đơn đó |
| Biện pháp | Xác thực chủ thể, đánh giá quyền theo đối tượng và giới hạn truy vấn theo phạm vi tin cậy |
| Thiết kế/triển khai | Lớp dịch vụ thực thi chính sách; lớp truy cập dữ liệu áp dụng điều kiện tenant và quyền sở hữu |
| Kiểm chứng | Thử truy cập hợp lệ, đổi mã đơn, đổi tenant, truy cập qua đường xuất dữ liệu |
| Bằng chứng | Kết quả kiểm thử và bản ghi quyết định truy cập đã loại bỏ dữ liệu nhạy cảm không cần thiết |

Yêu cầu không tự tạo ra sự bảo vệ nếu chưa được triển khai. Control cũng không tự chứng minh đã đáp ứng yêu cầu chỉ vì tên của nó xuất hiện trong tài liệu.

Ví dụ, “có hệ thống phân quyền” chưa chứng minh hệ thống đã kiểm tra quyền trên mọi đường truy cập dữ liệu. Cần biết chính sách nào được thực thi, ở đâu và kiểm thử nào xác nhận việc thực thi đó.

### Quan hệ thường là nhiều–nhiều

Một yêu cầu có thể cần nhiều control. Để ngăn đọc đơn hàng ngoài quyền, có thể cần xác thực, phân quyền theo đối tượng, xác định tenant ở máy chủ và bảo vệ các đường tải tệp.

Một control cũng có thể hỗ trợ nhiều yêu cầu. Dịch vụ quản lý danh tính có thể hỗ trợ yêu cầu xác thực, thu hồi phiên và truy vết danh tính.

Vì vậy, không nên ép mỗi yêu cầu phải ghép với đúng một control. Cần lưu được các liên kết và giải thích phần nghĩa vụ mà mỗi control thực hiện.

## 4. Cách viết một requirement đủ rõ để triển khai và kiểm chứng

Một mẫu tư duy đơn giản:

> Trong **phạm vi/điều kiện** đã xác định, **hệ thống hoặc vai trò chịu trách nhiệm** phải thực hiện **hành vi bảo vệ** đối với **tài sản/chủ thể**, với **giới hạn hoặc kết quả** được mô tả rõ.

Để yêu cầu có thể đưa vào phát triển, nên ghi thêm:

| Trường | Tác dụng |
| --- | --- |
| Mã yêu cầu | Dùng để tham chiếu nhất quán trong thiết kế, công việc và kiểm thử |
| Nguồn và lý do | Liên kết tới rủi ro, chính sách hoặc quyết định có căn cứ |
| Phạm vi | Xác định API, luồng nghiệp vụ, dữ liệu, vai trò và môi trường áp dụng |
| Nội dung bắt buộc | Nêu điều kiện phải đáp ứng |
| Tiêu chí chấp nhận | Xác định kết quả quan sát được để đánh giá đạt hoặc không đạt |
| Giả định và ngoại lệ | Làm rõ điều kiện phụ thuộc, giới hạn và quyết định chấp thuận |
| Người chịu trách nhiệm | Xác định ai triển khai, kiểm chứng và tiếp nhận thay đổi |

Không cần lặp toàn bộ bảng trong mọi câu yêu cầu; có thể quản lý những thông tin này thành các trường liên kết.

### 4.1. “Đo được” không phải lúc nào cũng cần một con số

“Người dùng của tenant A không được đọc đơn hàng của tenant B qua API dành cho khách hàng” có thể kiểm tra theo kết quả cho phép/từ chối và dữ liệu trả về.

“Quyền truy cập phải được thu hồi nhanh chóng” cần một giới hạn thời gian và điểm bắt đầu tính thời gian, chẳng hạn từ lúc thay đổi quyền được ghi nhận thành công.

Hai dạng yêu cầu đều có thể kiểm chứng. Đừng thêm số liệu tùy ý chỉ để khiến câu văn có vẻ định lượng. Khi cần ngưỡng thời gian, dung lượng hay tần suất, phải chọn theo rủi ro, tác động nghiệp vụ và năng lực hệ thống.

Các giá trị số trong bài này là **giả định để minh họa cách viết**, không phải mức mặc định cho mọi hệ thống.

### 4.2. Mô tả cả hành vi hợp lệ và hành vi bị cấm

Yêu cầu chỉ viết “phải từ chối truy cập trái phép” dễ dẫn tới kiểm thử chỉ có tình huống bị chặn. Một hệ thống từ chối mọi yêu cầu cũng vượt qua phép thử hẹp đó.

Cần bổ sung tiêu chí cho phép đúng chủ thể thực hiện đúng hành động. Mục tiêu là thực thi đúng chính sách, gồm cả cho phép và từ chối.

### 4.3. Nêu rõ điều kiện lỗi khi chúng ảnh hưởng đến nghĩa vụ

Nếu dịch vụ phân quyền không phản hồi, hệ thống có cho phép đọc dữ liệu không? Nếu gửi sự kiện kiểm toán thất bại, giao dịch nghiệp vụ được tiếp tục, xếp hàng hay bị từ chối?

Không có một câu trả lời chung phù hợp mọi luồng. Với thao tác đọc dữ liệu nhạy cảm trong ví dụ này, yêu cầu sẽ quy định từ chối khi không thể xác lập quyết định cho phép. Với logging, cần cân bằng yêu cầu kiểm toán, tính sẵn sàng và cơ chế đệm; quyết định phải được nêu rõ theo loại thao tác.

## 5. Ví dụ xuyên suốt: bảo vệ đơn hàng trong ứng dụng nhiều tenant

Giả sử một ứng dụng cung cấp API:

```http
GET /api/orders/{orderId}
```

Mỗi tenant là một tổ chức khách hàng sử dụng ứng dụng. Một người có thể được cấp quyền trong một hoặc nhiều tenant. API này dành cho khách hàng đọc đơn của chính mình trong tenant đang truy cập. Các luồng hỗ trợ vận hành có chính sách và yêu cầu riêng.

### 5.1. Mô tả rủi ro

Người dùng đã đăng nhập có thể thay `orderId`, tham số tenant hoặc thông tin do trình duyệt gửi lên để yêu cầu đơn hàng ngoài phạm vi được cấp quyền.

Điểm cần bảo vệ là **quan hệ giữa chủ thể, hành động và đơn hàng**, không chỉ trạng thái “đã đăng nhập”.

### 5.2. Đặc tả yêu cầu

**SR-ORD-01 — Kiểm soát quyền đọc đơn hàng**

Đối với API đọc đơn hàng dành cho khách hàng, máy chủ chỉ được trả nội dung đơn khi đồng thời thỏa mãn:

1. Chủ thể đã được xác thực bằng thông tin xác thực hợp lệ.
2. Chủ thể có quyền hoạt động trong tenant đang truy cập.
3. Đơn hàng thuộc tenant đó.
4. Chủ thể có quyền đọc đơn hàng theo chính sách đã định; trong ví dụ này là đơn thuộc chính chủ thể đó.
5. Máy chủ xác lập được một quyết định cho phép trước khi trả dữ liệu.

Máy chủ phải từ chối yêu cầu nếu một điều kiện không thỏa mãn hoặc không xác định được. Quyết định không được dựa riêng vào tenant, chủ sở hữu hay vai trò do máy khách tự khai báo.

Yêu cầu này nêu chính sách cần đạt. Nó chưa bắt buộc phải dùng một framework hoặc một sản phẩm phân quyền cụ thể.

### 5.3. Tiêu chí chấp nhận

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Người dùng có quyền đọc đơn của mình trong tenant hợp lệ | Trả đúng dữ liệu được phép |
| Chưa xác thực hoặc thông tin xác thực không hợp lệ | Từ chối và không trả nội dung đơn |
| Người dùng A yêu cầu đơn của người dùng B trong cùng tenant | Từ chối và không trả nội dung đơn |
| Người dùng tenant A yêu cầu đơn thuộc tenant B | Từ chối và không trả nội dung đơn |
| Máy khách sửa header tenant nhưng không có quyền với tenant đó | Không mở rộng được phạm vi truy cập |
| Không xác lập được quyết định phân quyền | Từ chối và không trả nội dung đơn |

Hợp đồng API cần chọn cách phản hồi lỗi phù hợp, bao gồm mã trạng thái và nội dung phản hồi. Việc dùng 403 hay cách che giấu sự tồn tại bằng 404 cần được quy định nhất quán cho luồng tương ứng; một mã lỗi riêng lẻ không đủ chứng minh dữ liệu đã được bảo vệ.

Cũng cần xác định phạm vi “nội dung đơn”: không để thông tin bị từ chối xuất hiện trong phần thân lỗi, trường phụ hoặc đường trả dữ liệu khác. Phép thử cho một endpoint chỉ cung cấp bằng chứng trong phạm vi endpoint và tình huống đã thử, không chứng minh mọi đường truy cập đều an toàn.

### 5.4. Chọn các control đáp ứng yêu cầu

Nhóm có thể lựa chọn một tập biện pháp:

- Xác minh thông tin xác thực và xây dựng ngữ cảnh chủ thể đáng tin cậy ở máy chủ.
- Kiểm tra quan hệ giữa chủ thể và tenant, kể cả khi máy khách gửi tenant muốn truy cập.
- Đánh giá quyền `read` trên đơn hàng cụ thể trước khi trả dữ liệu.
- Giới hạn truy vấn dữ liệu theo tenant và chủ sở hữu theo chính sách của API này.
- Áp dụng cùng chính sách cho tải tệp đính kèm, xuất dữ liệu và những đường đọc liên quan nếu chúng thuộc phạm vi yêu cầu.

Truy vấn giới hạn phạm vi có thể được minh họa như sau:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE order_id = :requested_order_id
  AND tenant_id = :authorized_tenant_id
  AND customer_id = :authenticated_customer_id;
```

Các tham số phải được bind an toàn. `authorized_tenant_id` phải được máy chủ xác minh theo quyền của chủ thể; `authenticated_customer_id` phải đến từ ngữ cảnh xác thực tin cậy.

Điều kiện truy vấn trên là một chi tiết triển khai control cho chính sách hẹp của ví dụ. Nó chưa bao quát các vai trò được ủy quyền, quyền đọc thay mặt, bộ nhớ đệm, tệp xuất hoặc những kiến trúc khác. Nếu chính sách thay đổi, thiết kế phải thay đổi tương ứng.

Sử dụng truy vấn tham số hóa hỗ trợ phòng ngừa SQL injection. Riêng việc bind tham số không giải quyết truy cập sai quyền nếu truy vấn vẫn chỉ lọc theo `order_id`. Hai biện pháp phục vụ các nghĩa vụ khác nhau dù cùng nằm trong một đoạn truy cập dữ liệu.

### 5.5. Minh họa phép kiểm chứng

```text
Given:
  Khách hàng A thuộc tenant T1 và sở hữu đơn O1.
  Khách hàng B thuộc tenant T1 và sở hữu đơn O2.
  Khách hàng C thuộc tenant T2 và sở hữu đơn O3.

When / Then:
  A đọc O1 trong T1 -> cho phép, trả nội dung O1.
  A đọc O2 trong T1 -> từ chối, không trả nội dung O2.
  A đọc O3 trong T1 -> từ chối, không trả nội dung O3.
  A tự khai tenant T2 để đọc O3 -> từ chối.
  Chủ thể chưa xác thực đọc O1 -> từ chối.
```

Đây là mô tả kiểm thử, không phải control dùng để quyết định quyền trong môi trường vận hành. Nó cung cấp bằng chứng về một số hành vi yêu cầu.

Kiểm thử trong quy trình phát triển cũng có thể được tổ chức như một biện pháp kiểm soát phòng ngừa lỗi. Nhưng vai trò đó khác với control thực thi quyền tại thời điểm người dùng gọi API. Cần nói rõ đang xét biện pháp ở vòng đời phát triển hay cơ chế bảo vệ khi hệ thống chạy.

## 6. Các ví dụ theo nhóm yêu cầu bảo mật

Bảng sau cho thấy cách tách nghĩa vụ, biện pháp và bằng chứng. Mỗi dòng là điểm khởi đầu cho đặc tả chi tiết hơn, không phải danh sách đầy đủ để nghiệm thu một hệ thống.

| Nhóm | Requirement minh họa | Control có thể lựa chọn | Cách kiểm chứng phù hợp |
| --- | --- | --- | --- |
| Xác thực | Mọi đường truy cập quản trị trong phạm vi phải yêu cầu MFA; ngoại lệ phải được xác định và chấp thuận rõ | Tích hợp nhà cung cấp danh tính, chính sách MFA, cơ chế quản lý ngoại lệ | Thử đăng nhập qua các đường truy cập đã liệt kê, phiên mới và luồng khôi phục |
| Phân quyền | Khách hàng chỉ được đọc đơn hàng thuộc phạm vi quyền đã cấp | Kiểm tra quyền theo đối tượng, giới hạn truy vấn theo tenant và chủ sở hữu | Thử đúng quyền, sai chủ sở hữu, sai tenant và đường đọc liên quan |
| Dữ liệu | Bản sao lưu chứa dữ liệu khách hàng phải được mã hóa; quyền đọc bản sao lưu không tự cấp quyền sử dụng khóa giải mã | Mã hóa sao lưu, quản lý khóa tách quyền, kiểm soát danh tính vận hành | Kiểm tra bản sao lưu, cấu hình quyền và khả năng giải mã bằng từng vai trò thử nghiệm |
| Logging | Thay đổi quyền quản trị phải tạo sự kiện kiểm toán chứa người thao tác, đối tượng, thời gian, kết quả và mã tương quan; không ghi mật khẩu hay token | Sự kiện kiểm toán có cấu trúc, danh sách trường cho phép, kiểm soát truy cập log | Thực hiện thay đổi quyền, đối chiếu sự kiện, thử dữ liệu chứa bí mật và kiểm tra đầu ra |
| Phục hồi | Sau sự cố thuộc kịch bản đã định, dịch vụ phải được khôi phục trong RTO và đáp ứng RPO đã phê duyệt | Sao lưu, lưu bản sao phù hợp, quy trình phục hồi, diễn tập | Thực hiện phục hồi thử, đo thời gian, đối chiếu điểm dữ liệu và kiểm tra chức năng |

### 6.1. Xác thực không thay thế phân quyền

Xác thực giúp xác định chủ thể theo mức tin cậy của cơ chế đang dùng. Phân quyền xác định chủ thể có được thực hiện một hành động trên một tài nguyên hay không.

JWT có thể là một phần của cơ chế xác thực hoặc mang thông tin phục vụ phân quyền. Việc nhận được một token không tự chứng minh quyền đọc mọi tài nguyên. Kiểm tra chữ ký cũng chưa đủ nếu các điều kiện xác thực cần thiết khác không được kiểm tra theo thiết kế.

Tương tự, MFA làm tăng mức bảo vệ cho xác thực nhưng không tự sửa lỗi API đọc đơn hàng sai chủ sở hữu.

### 6.2. “Mã hóa dữ liệu” cần được tách theo phạm vi

Một yêu cầu về bảo vệ dữ liệu cần nói rõ đang áp dụng cho:

- Dữ liệu truyền giữa các thành phần.
- Dữ liệu lưu trong cơ sở dữ liệu, tệp hoặc bộ nhớ đệm.
- Bản sao lưu và bản xuất.
- Khóa và quyền thực hiện giải mã.

Mã hóa bản sao lưu không ngăn API trả dữ liệu cho người không có quyền sau khi ứng dụng đã giải mã hợp lệ. Mỗi control có phạm vi và giả định riêng.

Nếu chỉ nói “dùng mã hóa mạnh”, nhóm vẫn chưa biết dữ liệu nào được bảo vệ, ai có thể giải mã và cần đưa ra bằng chứng gì.

### 6.3. Logging cần nghĩa vụ về nội dung lẫn vận hành

“Có log” có thể chỉ nghĩa là có tệp ghi lỗi. Yêu cầu kiểm toán cần xác định sự kiện cần ghi, các trường cần thiết, ai được xem, cách bảo vệ tính toàn vẹn và thời gian lưu.

Nếu đặt thời gian lưu 90 ngày trong một ví dụ nghiệp vụ, cần giải thích đó là quyết định của bối cảnh đó. Không được biến nó thành một mặc định cho mọi loại dữ liệu. Việc lưu giữ cũng cần cân nhắc lượng dữ liệu nhạy cảm và quyền truy cập.

Log không tự trở thành khả năng phát hiện nếu chưa có quy tắc theo dõi và người xử lý. Muốn phát hiện hoặc phản ứng trong một khoảng thời gian thì cần viết thêm nghĩa vụ và biện pháp tương ứng.

### 6.4. Có bản sao lưu chưa chứng minh khả năng phục hồi

- **RPO — Recovery Point Objective:** giới hạn mất dữ liệu chấp nhận được, thường biểu diễn bằng khoảng thời gian giữa điểm dữ liệu khôi phục và sự cố.
- **RTO — Recovery Time Objective:** mục tiêu về thời gian khôi phục dịch vụ hoặc chức năng trong phạm vi đã định.

Ví dụ minh họa: RPO 15 phút và RTO 2 giờ. Một yêu cầu sử dụng hai giá trị này cần chỉ rõ loại sự cố, dữ liệu và chức năng áp dụng, thời điểm bắt đầu/kết thúc phép đo và điều kiện phụ thuộc.

“Sao lưu hằng đêm” là một quyết định biện pháp. Riêng biện pháp này không đủ cơ sở để đáp ứng RPO 15 phút. Ngay cả khi lịch sao lưu phù hợp, vẫn cần kiểm chứng khả năng đọc bản sao, truy cập khóa, khôi phục dữ liệu và đưa chức năng cần thiết hoạt động trở lại.

## 7. Liên kết yêu cầu với kiến trúc và tiêu chí kiểm thử

Một bảng truy vết giúp tránh hai khoảng trống: yêu cầu không có biện pháp thực hiện, và biện pháp đã cài nhưng không rõ phục vụ nghĩa vụ nào.

| Mã rủi ro | Mã yêu cầu | Biện pháp/điểm thực thi | Bằng chứng dự kiến |
| --- | --- | --- | --- |
| R-ORD-01: đọc đơn sai quyền | SR-ORD-01 | Kiểm tra chủ thể, tenant và quyền đọc tại dịch vụ đơn hàng | Kết quả thử các trường hợp cho phép và từ chối |
| R-AUD-01: không truy được thay đổi quyền | SR-AUD-01 | Phát sự kiện kiểm toán tại thao tác cấp/thu hồi quyền | Sự kiện mẫu và kết quả kiểm tra trường bắt buộc |
| R-REC-01: mất dữ liệu sau sự cố | SR-REC-01 | Sao lưu và phục hồi trong phạm vi sự cố xác định | Biên bản phục hồi có số đo RPO/RTO thực tế |

Các mã trong bảng là mã minh họa. Trong dự án, cần liên kết chúng tới mô tả yêu cầu và rủi ro thật.

### 7.1. Yêu cầu cần được phân bổ vào các thành phần thực thi

Với SR-ORD-01, cần biết thành phần nào:

- Xác thực chủ thể.
- Xác minh tenant và quyền của chủ thể.
- Chặn trả dữ liệu khi không có quyết định cho phép.
- Áp dụng chính sách cho truy vấn, cache và tệp xuất nếu nằm trong phạm vi.

Nếu mọi thành phần đều giả định thành phần khác đã kiểm tra quyền, yêu cầu có thể không được thực thi ở đâu.

Ngược lại, nếu có nhiều lớp bảo vệ, cần xác định lớp nào chịu trách nhiệm chính và lớp nào bổ sung. Có nhiều control không có nghĩa là nghĩa vụ đã rõ hoặc các lớp luôn độc lập với nhau.

### 7.2. Tiêu chí chấp nhận quyết định bằng chứng cần thu thập

| Câu hỏi cần trả lời | Bằng chứng phù hợp |
| --- | --- |
| Chính sách có bao phủ đúng chủ thể và tài sản không? | Rà soát yêu cầu, ma trận quyền, mô hình luồng truy cập |
| Mã nguồn có thực thi quyết định đúng chỗ không? | Rà soát thiết kế và mã tại điểm trả dữ liệu hoặc thực hiện thao tác |
| Hệ thống có thực sự từ chối truy cập sai quyền không? | Kiểm thử tích hợp hoặc kiểm thử hành vi trên môi trường phù hợp |
| Control có hoạt động khi có lỗi không? | Kết quả kiểm thử điều kiện lỗi đã định |
| Khả năng phục hồi có đáp ứng mục tiêu không? | Kết quả diễn tập phục hồi và số đo |

Không có một loại bằng chứng nào thay thế được mọi loại khác. Ảnh chụp cấu hình bật phân quyền chưa chứng minh không tồn tại đường truy cập bỏ qua. Một báo cáo quét không có phát hiện cũng không chứng minh mọi yêu cầu đã đạt.

## 8. Theo dõi riêng trạng thái yêu cầu và trạng thái control

Các trạng thái sau trả lời những câu hỏi khác nhau:

- **Đã đặc tả yêu cầu:** đã ghi rõ nghĩa vụ và tiêu chí chấp nhận.
- **Đã chọn biện pháp:** đã có phương án đáp ứng cùng phạm vi, giả định.
- **Đã triển khai biện pháp:** cơ chế hoặc quy trình đã tồn tại.
- **Đã kiểm chứng yêu cầu:** đã có bằng chứng phù hợp với tiêu chí chấp nhận.
- **Đang vận hành hiệu quả:** có bằng chứng control tiếp tục hoạt động trong điều kiện thực tế.

Ví dụ, ứng dụng đã tích hợp nhà cung cấp danh tính nhưng vẫn còn một đường quản trị cũ không yêu cầu MFA. Khi đó một control đã được triển khai, còn yêu cầu MFA cho mọi đường quản trị trong phạm vi chưa được chứng minh là đạt.

Cũng không nên kết luận “đã kiểm thử một lần” đồng nghĩa “sẽ luôn đạt”. Thay đổi cấu hình, quyền, kiến trúc hoặc cách vận hành có thể làm control mất hiệu quả. Bằng chứng cần gắn với phiên bản và bối cảnh kiểm chứng.

## 9. Xử lý khi control không đáp ứng requirement

Giả sử yêu cầu là quyền quản trị bị thu hồi phải hết hiệu lực trong 60 giây kể từ khi thao tác thu hồi được ghi nhận thành công. Thiết kế chỉ dùng token tự chứa có hiệu lực 60 phút, và hệ thống không kiểm tra trạng thái thu hồi trong khoảng đó.

Khi ấy, chỉ giảm quyền trong cơ sở dữ liệu có thể chưa đủ để đáp ứng yêu cầu. Cần đánh giá đường thực thi quyền thực tế.

Có ba hướng xử lý:

1. **Bổ sung hoặc thay đổi control:** kiểm tra trạng thái quyền phù hợp, hỗ trợ thu hồi hoặc điều chỉnh thiết kế phiên.
2. **Làm rõ hoặc sửa yêu cầu có căn cứ:** nếu điểm bắt đầu tính thời gian, phạm vi thao tác hay giả định đang mơ hồ, sửa qua người có thẩm quyền và đánh giá tác động.
3. **Ghi nhận ngoại lệ và chấp nhận rủi ro:** nếu chưa đáp ứng được, cần người có thẩm quyền quyết định, phạm vi, thời hạn và biện pháp bù đắp nếu có.

Không được tự sửa yêu cầu cho khớp với công cụ rồi đánh dấu đã đạt. Một biện pháp bù đắp như cảnh báo thao tác sau thu hồi cũng không tự tương đương với ngăn chặn thao tác; phải đánh giá phần rủi ro còn lại.

Chấp nhận rủi ro là một quyết định quản trị. Nó không làm cho hành vi hệ thống tự nhiên thỏa mãn yêu cầu ban đầu.

## 10. Những nhầm lẫn thường gặp và cách sửa

| Cách diễn đạt hoặc kết luận | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Hệ thống phải bảo mật tốt” | Không biết nghĩa vụ, phạm vi và điều kiện nghiệm thu | Chia thành yêu cầu theo tài sản, hành động và tình huống đe dọa |
| “Dùng JWT nên đã đáp ứng yêu cầu xác thực và phân quyền” | Gộp công nghệ, cơ chế xác thực và chính sách quyền thành một kết luận | Chỉ rõ việc xác minh danh tính và quyết định quyền trên từng hành động |
| “Ẩn nút xóa là đã phân quyền” | Giao diện không kiểm soát được yêu cầu gọi trực tiếp | Máy chủ thực thi quyền xóa trước khi thay đổi dữ liệu |
| “Có HTTPS nên dữ liệu đã an toàn” | Chưa xác định các chặng truyền, dữ liệu lưu và quyền đọc dữ liệu | Viết yêu cầu theo phạm vi cần bảo vệ, chọn control cho từng phạm vi |
| “Mã hóa bằng thuật toán X” là yêu cầu đầy đủ | Có thể thiếu dữ liệu áp dụng, quản lý khóa và quyền giải mã | Bổ sung phạm vi, nguồn ràng buộc, điều kiện vận hành và bằng chứng |
| “Đã cài công cụ logging nên đáp ứng kiểm toán” | Chưa biết có đủ sự kiện, trường dữ liệu và khả năng truy xuất hay không | Kiểm tra nghĩa vụ về sự kiện, dữ liệu, quyền đọc và lưu giữ |
| “Có lịch backup nên đạt yêu cầu phục hồi” | Lịch thực hiện không chứng minh khôi phục thành công | Phục hồi thử và đo kết quả theo kịch bản cùng RPO/RTO |
| “Có test phân quyền nên hệ thống luôn đúng” | Bằng chứng bị giới hạn bởi phạm vi, dữ liệu và phiên bản đã thử | Liên kết test với yêu cầu và bổ sung bằng chứng phù hợp khi thay đổi |

## 11. Áp dụng sự phân biệt trong vòng đời phát triển

### Khi phân tích

Bắt đầu từ tài sản, luồng nghiệp vụ, ranh giới tin cậy và tình huống đe dọa. Chuyển rủi ro cần xử lý thành nghĩa vụ cụ thể, thống nhất chủ thể và tiêu chí chấp nhận.

Ví dụ: từ “người dùng đổi mã để đọc đơn khác” chuyển thành yêu cầu về quyền đọc theo đối tượng và tenant. Không dừng ở việc đưa tên một thư viện phân quyền vào backlog.

### Khi thiết kế

Chọn control dựa trên nghĩa vụ, kiến trúc và các ràng buộc đã có. Ghi rõ điểm thực thi, dữ liệu tin cậy, phụ thuộc và hành vi khi lỗi.

Ví dụ: nếu quyền được quyết định ở tầng dịch vụ, cần bảo đảm các đường trả dữ liệu trong phạm vi thực sự đi qua quyết định đó.

### Khi triển khai và kiểm chứng

Liên kết công việc triển khai với mã yêu cầu. Kiểm thử hành vi cho phép, từ chối, trường hợp biên và điều kiện lỗi có liên quan. Thu thập bằng chứng phù hợp với tiêu chí đã thống nhất.

Không dùng kết quả “cài đặt thành công” làm kết luận nghiệm thu cho một yêu cầu về hành vi.

### Khi vận hành và thay đổi

Theo dõi hiệu quả của control, xử lý thay đổi quyền và cấu hình, kiểm tra lại những nghĩa vụ bị ảnh hưởng.

Ví dụ, thêm chức năng xuất đơn hàng có thể mở một đường đọc dữ liệu mới. Yêu cầu cách ly tenant vẫn còn, nhưng phạm vi triển khai và kiểm chứng cần được cập nhật cho đường xuất dữ liệu.

## 12. Bài tập tự kiểm tra

### Bài 1: Phân loại theo vai trò

Hãy phân loại các câu sau theo vai trò chính:

1. “Khách hàng không được đọc đơn hàng của khách hàng khác.”
2. “Thêm điều kiện tenant và chủ sở hữu vào truy vấn đọc đơn.”
3. “Rò rỉ dữ liệu giao nhận gây ảnh hưởng tới khách hàng.”
4. “Kiểm thử A đọc đơn của B phải bị từ chối.”
5. “Tài khoản quản trị bắt buộc dùng MFA trước khi vào trang quản trị.”

**Gợi ý đáp án:**

1. Requirement về phân quyền; cần bổ sung phạm vi và chính sách nếu hệ thống có các vai trò được ủy quyền.
2. Một control và quyết định triển khai; hiệu quả phụ thuộc nguồn tham số và độ bao phủ.
3. Mô tả tác động của rủi ro; chưa phải nghĩa vụ cụ thể.
4. Một phép kiểm chứng; cần đối chiếu thêm nội dung phản hồi và kiểm thử truy cập hợp lệ.
5. Requirement quy định áp dụng một control cụ thể. Cần làm rõ các đường truy cập, khôi phục và ngoại lệ.

### Bài 2: Viết lại câu mơ hồ

Câu ban đầu:

> “Phải có logging bảo mật.”

Một cách viết rõ hơn:

> Mỗi thao tác cấp hoặc thu hồi quyền quản trị phải tạo sự kiện kiểm toán chứa mã chủ thể thực hiện, mã đối tượng, loại thay đổi, thời gian, kết quả và mã tương quan. Sự kiện không được chứa mật khẩu hoặc token truy cập.

**Control có thể chọn:** phát sự kiện có cấu trúc tại điểm thay đổi quyền, cho phép một tập trường xác định, phân quyền ghi/đọc kho kiểm toán.

**Tiêu chí chấp nhận ban đầu:** thực hiện cấp và thu hồi quyền; kiểm tra sự kiện tương ứng, trường bắt buộc và việc loại bỏ bí mật.

Đặc tả vẫn cần bổ sung thời gian sự kiện phải xuất hiện, cách xử lý lỗi ghi, quyền truy xuất, bảo vệ tính toàn vẹn và thời gian lưu theo bối cảnh. Việc nhận ra các khoảng trống này giúp tách yêu cầu cần hoàn thiện khỏi công cụ đã chọn.

### Bài 3: Đánh giá một giải pháp

Một nhóm nói: “Đã bật HTTPS và MFA, vì vậy khách hàng không thể đọc đơn của người khác.”

**Đánh giá:** hai control này chưa đủ căn cứ cho kết luận. Cần một yêu cầu về quyền đọc đơn và các control thực thi quan hệ giữa chủ thể với đơn hàng. Bằng chứng phù hợp gồm kiểm thử đúng quyền, sai chủ sở hữu, sai tenant và các đường đọc thuộc phạm vi.

## 13. Câu hỏi rà soát nhanh khi làm việc

Khi gặp một phát biểu bảo mật, lần lượt hỏi:

1. Đây là mục tiêu, nghĩa vụ, biện pháp, chi tiết triển khai hay bằng chứng?
2. Nó bảo vệ tài sản nào trước tình huống nào?
3. Phạm vi, chủ thể và điều kiện đã rõ chưa?
4. Nếu là requirement, điều gì quan sát được giúp xác định đạt hoặc không đạt?
5. Nếu là control, nó thực hiện phần nào của requirement, ở đâu và phụ thuộc vào điều gì?
6. Đã kiểm tra cả hành vi được phép lẫn hành vi bị cấm chưa?
7. Khi control lỗi hoặc kiến trúc thay đổi, nghĩa vụ nào có thể không còn được đáp ứng?

Yêu cầu rõ giúp nhóm chọn và đánh giá biện pháp. Biện pháp phù hợp biến yêu cầu thành hành vi bảo vệ cụ thể. Liên kết hai phần với rủi ro, kiến trúc và bằng chứng giúp quyết định bảo mật có thể giải thích, kiểm chứng và cập nhật trong suốt vòng đời phát triển.