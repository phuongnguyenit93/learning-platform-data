# Dữ liệu tài chính

## Mục tiêu bài học

Trong chương **Phân loại dữ liệu**, dữ liệu tài chính cần được đánh giá theo cả khả năng làm lộ thông tin và khả năng gây sai lệch tài sản, nghĩa vụ thanh toán hoặc quyết định kinh doanh. Một số dư bị sửa có thể gây hậu quả nghiêm trọng dù không ai đọc trộm dữ liệu. Một lệnh thanh toán bị xử lý lặp có thể làm mất tiền dù đường truyền đã được mã hóa.

Bài học tập trung vào thiết kế yêu cầu bảo mật: nhận diện dữ liệu tài chính, đánh giá rủi ro, xác định ranh giới kiến trúc và viết yêu cầu cụ thể, đo được, có thể kiểm chứng trong vòng đời phát triển. Sau bài học, người học có thể:

- Phân biệt các nhóm dữ liệu tài chính và tài sản liên quan.
- Phân loại theo bí mật, toàn vẹn, sẵn sàng và tác động nghiệp vụ.
- Đặc tả kiểm soát xác thực, phân quyền, xử lý giao dịch, bảo vệ dữ liệu, logging và phục hồi.
- Liên kết yêu cầu với rủi ro, chủ sở hữu, thành phần thực thi và tiêu chí kiểm thử.

## 1. Nhận diện đúng dữ liệu tài chính

### 1.1. Khái niệm và phạm vi

**Dữ liệu tài chính** là thông tin phản ánh hoặc hỗ trợ xác lập giá trị, tài sản, nghĩa vụ, dòng tiền và hoạt động thanh toán của cá nhân hoặc tổ chức. Dữ liệu này có thể là bản ghi nghiệp vụ, tài liệu, thông điệp trao đổi, tập báo cáo hoặc thông tin phân tích.

Các ví dụ thường gặp:

- Số dư tài khoản, hạn mức, khoản phải thu, khoản phải trả.
- Lệnh chuyển tiền, giao dịch thanh toán, hoàn tiền và kết quả xử lý.
- Hóa đơn, đơn giá, chiết khấu, hợp đồng và thông tin thanh toán.
- Bảng lương, thưởng, khấu trừ và tài khoản nhận lương.
- Doanh thu, chi phí, ngân sách, dự báo và kế hoạch tài chính.
- Bút toán, sổ giao dịch, hồ sơ đối soát và bằng chứng phê duyệt.
- Thông tin người thụ hưởng, tài khoản ngân hàng và mã tham chiếu giao dịch.

Không phải mọi dữ liệu trong hệ thống tài chính đều có cùng tính chất. Mã tiền tệ công khai khác với số dư khách hàng; báo cáo đã được phép công bố khác với dự báo chưa công bố.

Một tập dữ liệu cũng có thể đồng thời là dữ liệu tài chính, dữ liệu cá nhân và dữ liệu kinh doanh nhạy cảm. Khi các nhãn chồng lấn, cần đáp ứng những yêu cầu áp dụng cho từng khía cạnh, thay vì chọn một nhãn để bỏ qua các khía cạnh còn lại.

### 1.2. Phân biệt dữ liệu nghiệp vụ với bí mật cấp quyền

Số tài khoản và mã giao dịch thường là thông tin định danh hoặc tham chiếu. Chúng không nên được dùng như bằng chứng rằng người gọi có quyền truy cập hay yêu cầu chuyển tiền.

Mật khẩu, token truy cập, khóa API, khóa ký và bí mật xác thực của kết nối thanh toán là nhóm tài sản liên quan nhưng có chức năng khác: chúng có thể cấp quyền đọc dữ liệu hoặc thực hiện hành động tài chính. Phải phân loại và bảo vệ riêng, đồng thời ghi rõ chúng cho phép tác động tới dữ liệu nào.

Ví dụ, việc che số tài khoản trên giao diện không bù được một token quản trị có quyền xuất toàn bộ lịch sử giao dịch.

## 2. Các nhóm dữ liệu và tác động điển hình

| Nhóm dữ liệu | Ví dụ | Rủi ro nổi bật |
| --- | --- | --- |
| Giá trị và trạng thái tài chính | Số dư, hạn mức, số tiền đã thanh toán | Thay đổi trái phép làm sai tài sản hoặc quyền chi tiêu |
| Chỉ dẫn thanh toán | Số tiền, tiền tệ, người nhận, tài khoản đích | Đổi người nhận, tăng số tiền, gửi lặp hoặc gửi sai thời điểm |
| Lịch sử giao dịch | Thời gian, nội dung, đối tác, kết quả | Lộ hoạt động cá nhân hoặc kinh doanh; sửa dấu vết để che gian lận |
| Hồ sơ kế toán và đối soát | Bút toán, chênh lệch, chứng từ | Báo cáo sai, bỏ sót giao dịch, không giải thích được chênh lệch |
| Tài chính nhân sự | Lương, thưởng, khấu trừ | Lộ thu nhập cá nhân; sửa tài khoản nhận lương |
| Tài chính doanh nghiệp chưa công bố | Dự báo, ngân sách, kế hoạch mua bán | Lộ chiến lược hoặc thông tin có giá trị cạnh tranh |
| Dữ liệu báo cáo đã công bố | Báo cáo được chủ sở hữu cho phép phát hành | Cần bảo vệ bản chính thức khỏi bị thay thế hoặc giả mạo |
| Dữ liệu truy cập dịch vụ tài chính | Token, khóa kết nối, bí mật xác thực | Đọc hoặc thực hiện giao dịch trái phép trong phạm vi quyền |

Thông tin thanh toán có thể chịu yêu cầu chuyên biệt tùy phương thức thanh toán, hợp đồng và khu vực áp dụng. Nhóm thiết kế phải xác định nghĩa vụ thực tế với đơn vị phụ trách tương ứng. Không mặc định một yêu cầu pháp lý, thời hạn lưu giữ hay tiêu chuẩn cụ thể áp dụng cho mọi tập dữ liệu tài chính.

## 3. Phân loại theo bí mật, toàn vẹn và sẵn sàng

### 3.1. Tính bí mật

Đặt câu hỏi: nếu dữ liệu bị người không có quyền biết được, họ có thể suy ra hoặc khai thác điều gì?

- Lịch sử giao dịch có thể cho thấy thu nhập, thói quen, nhà cung cấp và quan hệ kinh doanh.
- Bảng lương có thể bộc lộ thông tin nhạy cảm của từng nhân viên.
- Dự báo doanh thu chưa công bố có thể ảnh hưởng chiến lược và đàm phán.
- Tập giao dịch đủ lớn có thể hỗ trợ lừa đảo có chủ đích ngay cả khi từng bản ghi có vẻ ít nhạy cảm.

Mã khách hàng thay cho tên chưa bảo đảm dữ liệu đã vô danh. Thời điểm, số tiền, nội dung chuyển khoản hoặc tập thuộc tính hiếm vẫn có thể giúp liên kết lại danh tính.

### 3.2. Tính toàn vẹn

Đặt câu hỏi: nếu dữ liệu bị sửa, thêm, xóa, tráo hoặc xử lý lặp, tài sản và quyết định nào bị ảnh hưởng?

Với dữ liệu tài chính, toàn vẹn bao gồm cả:

- Đúng số tiền và tiền tệ.
- Đúng người trả, người nhận và tài khoản đích.
- Đúng trạng thái và thứ tự chuyển trạng thái.
- Đúng quan hệ giữa yêu cầu, phê duyệt, thực hiện và đối soát.
- Không ghi nhận hoặc thực hiện lặp một hành động ngoài ý định nghiệp vụ.
- Truy vết được các điều chỉnh hợp lệ.

Một bản ghi có cấu trúc hợp lệ vẫn có thể sai về nghiệp vụ. Ví dụ, số tiền dương và tài khoản đích tồn tại không chứng minh người dùng được phép trả khoản đó.

### 3.3. Tính sẵn sàng

Đặt câu hỏi: khi dữ liệu hoặc dịch vụ xử lý dữ liệu không sẵn sàng, điều gì bị trì hoãn và trong bao lâu có thể chấp nhận?

- Không đọc được số dư có thể ngăn người dùng ra quyết định hoặc thực hiện giao dịch.
- Không xử lý được thanh toán có thể ảnh hưởng khách hàng và dòng tiền.
- Không truy cập được dữ liệu đối soát có thể kéo dài thời gian phát hiện chênh lệch.
- Không truy cập được báo cáo lịch sử có thể ít khẩn cấp hơn ngừng hệ thống thanh toán, tùy nghiệp vụ.

Sẵn sàng không có nghĩa phải tiếp tục thanh toán khi không biết giao dịch trước đã thành công hay chưa. Trong trạng thái bất định, giữ giao dịch chờ xử lý và đối soát có thể phù hợp hơn việc tự gửi lại.

### 3.4. Ví dụ ma trận phân loại

| Tập dữ liệu | Bí mật | Toàn vẹn | Sẵn sàng | Căn cứ chính |
| --- | --- | --- | --- | --- |
| Lệnh thanh toán đang chờ thực hiện | Cao | Rất cao theo thang nội bộ minh họa | Cao | Sai người nhận hoặc xử lý lặp có thể gây mất tiền |
| Bảng lương chi tiết | Cao | Cao | Theo kỳ trả lương | Lộ thu nhập hoặc sửa người nhận ảnh hưởng nhân viên |
| Sổ giao dịch dùng để xác lập nghĩa vụ | Cao theo phạm vi người đọc | Rất cao theo thang nội bộ minh họa | Cao | Sai lệch gây ảnh hưởng dây chuyền tới số dư và đối soát |
| Dự báo tài chính chưa công bố | Cao | Cao | Theo thời hạn ra quyết định | Lộ hoặc sai dữ liệu làm ảnh hưởng kế hoạch kinh doanh |
| Báo cáo được phép công bố | Giá trị công bố không cần giữ bí mật | Cao | Theo cam kết cung cấp | Cần bảo đảm người đọc nhận đúng bản chính thức |

Các nhãn trên là ví dụ học tập. Tổ chức cần có thang tác động và tiêu chí nhất quán, dựa trên mức thiệt hại, số đối tượng bị ảnh hưởng, khả năng sửa sai và thời gian phục hồi. Không suy mức phân loại chỉ từ tên bảng hoặc đuôi tệp.

## 4. Phân loại theo ngữ cảnh và mức tổng hợp

### 4.1. Phân loại đến mức cần thực thi

Một bảng có thể chứa cả mã tham chiếu ít nhạy cảm và nội dung thanh toán nhạy cảm. Có thể cần phân loại ở nhiều mức:

- **Tập dữ liệu:** toàn bộ sổ giao dịch, bảng lương hoặc báo cáo.
- **Bản ghi:** giao dịch của một khách hàng hoặc một đơn vị.
- **Trường dữ liệu:** tài khoản đích, số tiền, nội dung, người phê duyệt.
- **Đầu ra:** màn hình, API, tệp xuất và báo cáo tổng hợp.
- **Hành động:** xem, sửa, phê duyệt, thực hiện, tải xuống hoặc chia sẻ.

Phân loại chi tiết có ích khi nó dẫn tới quy tắc thực thi rõ ràng. Nếu chưa có cơ chế tách trường an toàn, cần bảo vệ toàn bộ đối tượng theo mức phù hợp với trường nhạy cảm trong đó.

### 4.2. Tổng hợp và suy luận

Một số tiền riêng lẻ có thể không nhận diện ai, nhưng chuỗi giao dịch theo thời gian có thể nhận diện một người hoặc phản ánh bí mật kinh doanh.

Báo cáo tổng hợp cũng không tự động an toàn. Một nhóm chỉ có một nhân viên có thể làm lộ thu nhập dù không hiển thị tên. Hai báo cáo có bộ lọc gần giống nhau có thể cho phép tính ra giá trị của một đối tượng bằng phép trừ.

Yêu cầu bảo vệ báo cáo cần xác định:

- Ai được xem nhóm dữ liệu nào.
- Những bộ lọc và chiều phân tích được phép.
- Điều kiện che nhóm quá nhỏ hoặc hạn chế truy vấn.
- Cách đánh giá khả năng liên kết và suy luận từ nhiều đầu ra.

Không nên chỉ dựa vào thao tác xóa tên rồi coi dữ liệu đã được phép chia sẻ rộng rãi.

## 5. Lập hồ sơ dữ liệu phục vụ yêu cầu bảo mật

Một hồ sơ dữ liệu tài chính cần đủ để xác định phạm vi kiểm soát mà không đưa dữ liệu thật vào tài liệu thiết kế.

| Thông tin | Câu hỏi cần trả lời |
| --- | --- |
| Tên và mục đích | Tập dữ liệu hỗ trợ nghiệp vụ gì? |
| Chủ sở hữu | Ai quyết định mục đích, quyền truy cập và mức tác động? |
| Chủ thể và phạm vi | Dữ liệu thuộc khách hàng, nhân viên, pháp nhân hay đơn vị nào? |
| Trường nhạy cảm | Có số tiền, tài khoản đích, nội dung thanh toán, dữ liệu cá nhân không? |
| Nguồn và nguồn có thẩm quyền | Dữ liệu đến từ đâu, bản nào xác lập trạng thái chính thức? |
| Nhãn và lý do | Tác động bí mật, toàn vẹn, sẵn sàng là gì? |
| Luồng và bản sao | Đi qua API, hàng đợi, kho dữ liệu, báo cáo và bản sao lưu nào? |
| Quyền và hành động | Ai được xem, sửa, phê duyệt, thực hiện và xuất? |
| Lưu giữ và xử lý cuối đời | Giữ vì mục đích gì, khi nào đánh giá, xóa hoặc chuyển lưu trữ? |
| Phục hồi và đối soát | Phục hồi trạng thái nhất quán như thế nào, ai xử lý chênh lệch? |
| Rủi ro và bằng chứng | Yêu cầu nào xử lý rủi ro nào, kiểm chứng ở đâu? |

Ví dụ hồ sơ rút gọn:

```yaml
dataAssetId: payment-instructions-production
purpose: approved-supplier-payment
businessOwner: treasury-owner
technicalOwner: payment-platform-team
scope:
  organization: example-company
  environment: production
sensitiveFields:
  - beneficiaryAccount
  - amount
  - currency
  - paymentReference
authoritativeRecord: payment-ledger
impact:
  confidentiality: high
  integrity: critical
  availability: high
permittedActions:
  preparer: [create-draft, submit]
  approver: [review, approve]
  executorService: [execute-approved-instruction]
retentionPolicyReference: FIN-DATA-RETENTION
riskReferences:
  - R-FIN-01
  - R-FIN-02
  - R-FIN-03
```

Đây là mẫu mô tả, không phải cấu hình của một sản phẩm. Tham chiếu chính sách lưu giữ phải được giải quyết thành quy tắc thực tế trước triển khai, thay vì để thành một tên không có người chịu trách nhiệm.

## 6. Theo dõi dữ liệu qua toàn bộ vòng đời

Một kiểm soát chỉ có tác dụng tại nơi nó thực thi. Mã hóa cơ sở dữ liệu không ngăn được người có quyền ứng dụng tải một tệp CSV chứa toàn bộ giao dịch.

```text
Người dùng hoặc hệ thống nguồn
             |
             v
API tiếp nhận -> Xác thực, phân quyền, kiểm tra nghiệp vụ
             |
             v
Bản ghi giao dịch -> Phê duyệt -> Thực hiện thanh toán
             |                         |
             |                         v
             +-----------------> Đối soát kết quả
             |
             +-> Hàng đợi, sự kiện, hàng đợi lỗi
             +-> Báo cáo, kho phân tích, tệp xuất
             +-> Log, trace, công cụ hỗ trợ
             +-> Bản sao lưu và môi trường phục hồi
```

Tại mỗi điểm, cần hỏi:

1. Trường dữ liệu nào thực sự cần thiết?
2. Danh tính nào có thể đọc hoặc thay đổi?
3. Có bản sao mới nào được tạo ra?
4. Mức bảo vệ có tương xứng với dữ liệu gốc không?
5. Bản sao được giữ bao lâu và xóa bằng cách nào?
6. Có đủ bằng chứng khi xảy ra lộ dữ liệu hoặc sai giao dịch không?

Các vị trí dễ bị bỏ sót gồm tệp xuất trên máy người dùng, nội dung thông báo lỗi, tham số URL, dữ liệu trong hệ thống hỗ trợ, hàng đợi xử lý lỗi và bản sao dùng cho phân tích.

Môi trường phát triển hoặc kiểm thử không tự làm giảm độ nhạy cảm của dữ liệu production được chép sang. Nên dùng dữ liệu tổng hợp hoặc bộ dữ liệu đã được xử lý và đánh giá phù hợp với mục đích kiểm thử.

## 7. Xác thực, phân quyền và tách nhiệm vụ

### 7.1. Phân quyền theo đối tượng và hành động

Một vai trò chung như “nhân viên tài chính” thường chưa đủ. Quyền có thể phụ thuộc vào:

- Pháp nhân, đơn vị, khách hàng hoặc danh mục tài khoản.
- Hành động cụ thể: xem, tạo, sửa, duyệt, thực hiện, đối soát, xuất dữ liệu.
- Số tiền, tiền tệ, loại giao dịch và trạng thái.
- Quan hệ giữa người lập và người duyệt.
- Mức xác thực và điều kiện phiên làm việc.
- Thời điểm hiệu lực hoặc thời gian ủy quyền.

Kiểm tra phải diễn ra ở phía thực thi tin cậy. Ẩn nút “phê duyệt” trên giao diện không thay thế kiểm tra quyền tại API.

Với hệ thống nhiều khách hàng, việc biết mã giao dịch không cho phép đọc giao dịch đó. Truy vấn và thao tác phải được ràng buộc với phạm vi chủ thể đã xác thực.

### 7.2. Tách người lập và người duyệt

Tách nhiệm vụ giúp giảm rủi ro một người tự tạo rồi hợp thức hóa một khoản chi. Đặc tả cần nêu:

- Những loại giao dịch hoặc ngưỡng nào cần người duyệt độc lập.
- Những vai trò nào không được đồng thời thực hiện một chuỗi hành động.
- Cách xử lý ủy quyền, thay người và tài khoản khẩn cấp.
- Cách ngăn một cá nhân dùng nhiều tài khoản để tự đáp ứng điều kiện.
- Bằng chứng cho thấy đúng nội dung đã được phê duyệt.

Không chỉ so sánh hai tên đăng nhập rồi mặc định có hai người độc lập. Quan hệ giữa danh tính và người chịu trách nhiệm cần được quản lý.

### 7.3. Phê duyệt phải gắn với nội dung cụ thể

Giả sử người duyệt chấp thuận 12 triệu đồng cho người nhận A. Nếu người lập có thể đổi thành 120 triệu đồng hoặc người nhận B mà vẫn giữ trạng thái “đã duyệt”, quy trình đã mất ý nghĩa bảo mật.

Yêu cầu nên quy định:

- Phê duyệt gắn với một phiên bản chỉ dẫn thanh toán.
- Phiên bản chứa các trường trọng yếu như số tiền, tiền tệ, người nhận và tài khoản đích.
- Thay trường trọng yếu làm mất hiệu lực phê duyệt cũ và yêu cầu phê duyệt lại.
- Thành phần thực hiện chỉ dùng phiên bản đã được phê duyệt.
- Kiểm tra trạng thái và thực hiện chuyển trạng thái phải chống tình huống thay đổi đồng thời.

Có thể dùng định danh phiên bản và cơ chế kiểm soát đồng thời phù hợp. Chỉ lưu mã băm của dữ liệu không tự tạo ra phê duyệt hợp lệ nếu người có quyền sửa dữ liệu cũng có thể thay mã băm và dấu vết phê duyệt.

## 8. Bảo vệ toàn vẹn xử lý giao dịch

### 8.1. Biểu diễn số tiền đúng

Yêu cầu cần chỉ rõ:

- Số tiền luôn gắn với tiền tệ.
- Dùng kiểu biểu diễn có độ chính xác và phạm vi phù hợp với nghiệp vụ.
- Xác định quy tắc làm tròn tại từng bước cần làm tròn.
- Xác định đơn vị lưu, đơn vị hiển thị và cách quy đổi.
- Từ chối giá trị ngoài miền cho phép.

Số thực nhị phân dấu phẩy động thường không phù hợp để biểu diễn chính xác các giá trị tiền thập phân cần đối chiếu. Có thể dùng số nguyên theo đơn vị nhỏ nhất hoặc kiểu thập phân chính xác, tùy mô hình. Không mặc định mọi tiền tệ đều có hai chữ số thập phân.

Thời gian cũng cần được đặc tả: thời điểm sự kiện, múi giờ, ngày nghiệp vụ và kỳ đối soát không luôn đồng nghĩa. Một giao dịch đi qua thời điểm chốt ngày cần được xếp đúng kỳ theo quy tắc đã công bố.

### 8.2. Chống xử lý lặp

Khách hàng có thể gửi lại yêu cầu khi mất kết nối. Hàng đợi cũng có thể giao lại thông điệp. Một lần gọi bị timeout không chứng minh giao dịch chưa được thực hiện.

Yêu cầu về tính lũy đẳng cần quy định:

- Cách định danh một ý định nghiệp vụ.
- Phạm vi của khóa lũy đẳng, chẳng hạn theo tổ chức và loại hành động.
- Thời hạn giữ thông tin chống lặp.
- Cách xử lý cùng khóa nhưng khác nội dung.
- Tính nhất quán khi nhiều yêu cầu trùng đến đồng thời.

Ví dụ: cùng một ý định thanh toán hợp lệ được gửi lại phải trả về cùng tham chiếu xử lý hoặc trạng thái hiện tại, thay vì tạo thêm khoản thanh toán. Nếu cùng khóa lũy đẳng nhưng thay người nhận hoặc số tiền, hệ thống phải từ chối theo quy tắc đã định.

Không nên hứa “đúng một lần” cho toàn bộ hệ thống phân tán chỉ vì có một trường chống lặp. Cam kết cần gắn với từng bước, kho lưu trạng thái, cơ chế gửi lại và giao diện của bên thanh toán.

### 8.3. Trạng thái và đối soát

Một luồng minh họa:

```text
Nháp -> Đã gửi duyệt -> Đã duyệt -> Đang thực hiện
                                        |
                                        +-> Thành công
                                        +-> Thất bại xác định
                                        +-> Chưa xác định kết quả -> Đối soát
```

Không cho phép mọi trạng thái chuyển tự do sang mọi trạng thái khác. Nếu chưa biết kết quả từ đối tác, việc tự đánh dấu thất bại rồi tạo giao dịch mới có thể gây chi hai lần.

Đối soát phải phát hiện chênh lệch giữa ý định nội bộ, bản ghi thực hiện và kết quả bên ngoài. Việc sửa chênh lệch cần có người chịu trách nhiệm, lý do và dấu vết. Không tự sửa số dư để “khớp báo cáo” mà không có nghiệp vụ điều chỉnh được phê duyệt.

Các bản ghi tài chính đã chốt thường cần được điều chỉnh qua nghiệp vụ có truy vết thay vì sửa trực tiếp không để dấu vết. Cách điều chỉnh cụ thể phụ thuộc mô hình nghiệp vụ; không phải mọi hệ thống đều là một sổ kế toán tổng hợp.

## 9. Bảo vệ tính bí mật và giảm bản sao

### 9.1. Mã hóa và quản lý quyền dùng khóa

Cần xác định dữ liệu nào được bảo vệ khi truyền, khi lưu và ở các bản sao. Mã hóa phải đi cùng quản lý khóa và phân quyền; người có quyền giải mã vẫn có thể đọc dữ liệu.

Các yêu cầu cần làm rõ:

- Thành phần nào được phép giải mã và vì mục đích gì.
- Cách tách môi trường, khách hàng hoặc miền dữ liệu khi cần.
- Nơi bản rõ xuất hiện, bao gồm bộ nhớ, tệp tạm và công cụ chẩn đoán.
- Cách phục hồi khóa cùng dữ liệu trong thời hạn giữ.
- Cách phát hiện hoặc điều tra truy cập bất thường.

Không tự thiết kế thuật toán mã hóa. Yêu cầu thiết kế nên chỉ ra cơ chế được phê duyệt và cách kiểm chứng việc tích hợp.

### 9.2. Che hiển thị, thay thế định danh và dữ liệu tổng hợp

| Biện pháp | Mục đích | Giới hạn cần nhớ |
| --- | --- | --- |
| Che hiển thị | Chỉ hiện một phần tài khoản hoặc trường nhạy cảm | Không bảo vệ bản đầy đủ nếu API vẫn trả về |
| Phân quyền theo trường | Chỉ cung cấp trường cần cho hành động | Phải áp dụng trên đường API và xuất dữ liệu |
| Token hóa | Thay giá trị gốc bằng tham chiếu được kiểm soát | Kho ánh xạ hoặc dịch vụ đổi ngược vẫn là tài sản nhạy cảm |
| Mã hóa | Bảo vệ nội dung đối với người không có khả năng giải mã | Không thay thế kiểm soát người dùng và quyền ứng dụng |
| Tổng hợp | Giảm mức chi tiết theo mục đích báo cáo | Vẫn có thể làm lộ qua nhóm nhỏ hoặc nhiều truy vấn |
| Dữ liệu tổng hợp cho kiểm thử | Giảm việc dùng dữ liệu thật | Phải bảo đảm không vô tình tái tạo hoặc chứa dữ liệu thật |

Băm một số tài khoản hoặc một tập giá trị dễ đoán không tự làm nó vô danh. Nếu kẻ tấn công có thể thử các giá trị ứng viên hoặc liên kết với nguồn khác, khả năng nhận diện vẫn có thể còn.

### 9.3. Kiểm soát xuất dữ liệu

Quyền xem một giao dịch không mặc nhiên bao gồm quyền tải mọi giao dịch. Với tệp xuất cần đặc tả:

- Phạm vi bản ghi và trường cho từng vai trò.
- Điều kiện phê duyệt với xuất hàng loạt khi phù hợp.
- Danh tính và thời hạn truy cập tệp.
- Cơ chế thu hồi hoặc hết hạn đường tải.
- Nhật ký ai xuất, phạm vi nào và bao nhiêu bản ghi.
- Quy tắc giữ và xóa bản sao được quản lý.

Đường tải có thời hạn không đủ nếu ai lấy được liên kết đều có thể tải. Cần xác định rõ khả năng chia sẻ và điều kiện xác thực tương ứng.

## 10. Logging và bằng chứng kiểm toán

### 10.1. Tách nội dung giao dịch khỏi log kỹ thuật

Một sự kiện kiểm toán giao dịch có thể cần:

- Chủ thể thực hiện, vai trò và phạm vi được cấp.
- Mã giao dịch, phiên bản và mã liên kết yêu cầu.
- Hành động, trạng thái trước và sau, kết quả.
- Thời gian và nguồn hệ thống.
- Người phê duyệt, lý do điều chỉnh và tham chiếu nghiệp vụ.

Không cần ghi toàn bộ tài khoản ngân hàng, nội dung chuyển khoản hoặc token vào mọi dòng log để đạt khả năng truy vết. Có thể dùng định danh tham chiếu để người được ủy quyền tra cứu dữ liệu gốc qua đường kiểm soát riêng.

Sổ giao dịch dùng làm nguồn nghiệp vụ và log kỹ thuật có mục đích khác nhau. Một dòng “HTTP 200” không chứng minh đã thanh toán thành công; một bản ghi nghiệp vụ cũng không tự cung cấp đầy đủ bằng chứng về người đã đổi chính sách truy cập.

### 10.2. Bảo vệ dấu vết

Yêu cầu cần chỉ rõ ai được đọc, ai được ghi và ai có thể quản trị nơi lưu bằng chứng. Ứng dụng xử lý giao dịch không nên tự ý xóa dấu vết để che hành động của chính nó.

Cần xác định:

- Những sự kiện bắt buộc phải có và cách đối chiếu tính đầy đủ.
- Mức bảo vệ khỏi sửa hoặc xóa trái phép.
- Cách quản lý thời gian và liên kết sự kiện giữa các thành phần.
- Cảnh báo khi log bị gián đoạn hoặc xuất dữ liệu bất thường.
- Thời hạn lưu giữ theo mục đích và nghĩa vụ thực tế.
- Hành vi khi không ghi được bằng chứng bắt buộc đối với từng hành động.

Không áp dụng một câu “luôn tiếp tục” hoặc “luôn dừng” cho mọi lỗi log. Với một thao tác tài chính trọng yếu, cần quyết định rõ có chặn, đưa vào hàng chờ hay dùng cơ chế lưu bằng chứng dự phòng; tiêu chí phải được kiểm thử theo mức tác động.

## 11. Chuyển rủi ro thành yêu cầu có thể kiểm chứng

### 11.1. Công thức đặc tả

Một yêu cầu tốt có thể viết theo cấu trúc:

> Đối tượng + điều kiện áp dụng + hành vi bắt buộc + giới hạn hoặc quy tắc + bằng chứng chấp nhận.

Câu chưa đủ rõ:

> Dữ liệu tài chính phải được bảo vệ nghiêm ngặt.

Câu rõ hơn:

> API đọc giao dịch phải xác định phạm vi tổ chức từ danh tính đã xác thực, kiểm tra quyền trên giao dịch và chỉ trả các trường được vai trò đó cho phép. Thay mã giao dịch hoặc tham số tổ chức không được làm mở rộng phạm vi truy cập.

Từ yêu cầu này cần lập ca kiểm thử cho người hợp lệ, người không có quyền, giao dịch khác tổ chức và trường dữ liệu bị hạn chế.

### 11.2. Bộ yêu cầu minh họa

Bối cảnh: hệ thống thanh toán nhà cung cấp có người lập, người duyệt độc lập, dịch vụ thực hiện và kết nối đối tác. Các ngưỡng thời gian dưới đây là **giả định học tập**, cần được chủ sở hữu chấp thuận và điều chỉnh theo thiết kế thực tế.

| ID | Rủi ro | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- | --- |
| FIN-REQ-01 | R-FIN-01: đọc giao dịch ngoài phạm vi | Mọi API đọc, tìm kiếm và xuất giao dịch phải kiểm tra tổ chức từ danh tính tin cậy và quyền trên tài sản | Đổi ID, tham số tổ chức hoặc bộ lọc không trả dữ liệu của tổ chức khác; ca hợp lệ vẫn thành công |
| FIN-REQ-02 | R-FIN-02: tự tạo và tự duyệt khoản chi | Giao dịch thuộc diện kiểm soát phải được người độc lập với người lập phê duyệt; quyền duyệt gắn với phạm vi và hạn mức | Người lập không tự duyệt được; người không đủ hạn mức và danh tính không hợp lệ bị từ chối |
| FIN-REQ-03 | R-FIN-03: sửa nội dung sau phê duyệt | Phê duyệt phải gắn với phiên bản; thay số tiền, tiền tệ hoặc tài khoản đích làm mất hiệu lực phê duyệt | Thay trường trọng yếu rồi gọi thực hiện bị chặn cho đến khi duyệt lại; thử cả hai yêu cầu đồng thời |
| FIN-REQ-04 | R-FIN-04: xử lý lặp | Một ý định thanh toán có định danh lũy đẳng phải chỉ tạo một bản ghi thực hiện nội bộ trong phạm vi và thời hạn thiết kế; nội dung khác với cùng định danh bị từ chối | Gửi tuần tự, đồng thời và gửi lại sau timeout không tạo thêm ý định thực hiện; hành vi bên ngoài được kiểm tra riêng |
| FIN-REQ-05 | R-FIN-05: sai giá trị tiền | Số tiền và tiền tệ phải được kiểm tra miền giá trị, độ chính xác, giới hạn và quy tắc làm tròn trước khi chuyển sang trạng thái có thể thực hiện | Ca biên, tiền tệ có độ chính xác khác nhau, giá trị quá lớn và sai định dạng được xử lý đúng quy tắc |
| FIN-REQ-06 | R-FIN-06: lộ dữ liệu qua đường phụ | Log, trace và lỗi API không được chứa token, tài khoản đầy đủ hoặc nội dung thanh toán ngoài danh sách trường được duyệt | Dùng dữ liệu đánh dấu trong ca thành công và lỗi; kiểm tra các đầu ra thuộc phạm vi không có giá trị bị cấm |
| FIN-REQ-07 | R-FIN-07: xuất hàng loạt trái phép | Tệp xuất chỉ chứa bản ghi và trường trong quyền được duyệt; đường tải ràng buộc với người yêu cầu và hết hạn sau 15 phút | Người khác, yêu cầu ngoài phạm vi và liên kết hết hạn không tải được; log có phạm vi và số bản ghi |
| FIN-REQ-08 | R-FIN-08: thiếu hoặc bị sửa dấu vết | Tạo, sửa, duyệt, thực hiện, điều chỉnh và đổi quyền phải có sự kiện kiểm toán; danh tính runtime không có quyền sửa hoặc xóa sự kiện đã lưu | Đối chiếu ca kiểm thử với sự kiện; thử quyền runtime không sửa hoặc xóa được bằng chứng |
| FIN-REQ-09 | R-FIN-09: bỏ sót trạng thái bất định | Giao dịch chưa rõ kết quả từ đối tác phải có trạng thái riêng, không tự gửi một khoản mới, và được đưa vào đối soát trong 5 phút | Mô phỏng đối tác xử lý thành công nhưng phản hồi bị mất; không phát sinh khoản mới và xuất hiện mục đối soát đúng hạn |
| FIN-REQ-10 | R-FIN-10: phục hồi gây sai hoặc lặp giao dịch | Sau phục hồi, hệ thống phải đối chiếu trạng thái đã gửi và kết quả đối tác trước khi cho phép gửi lại giao dịch bất định | Diễn tập với giao dịch dở dang chứng minh không tự trả lại trạng thái có thể gửi mới khi chưa xử lý chênh lệch |
| FIN-REQ-11 | R-FIN-10: dịch vụ ngừng quá lâu | Trong kịch bản mất vùng đã thiết kế, phục hồi khả năng truy cập bộ dữ liệu ưu tiên trong RTO 60 phút, RPO 5 phút; xử lý phần chênh lệch theo quy trình trước khi mở lại chức năng chi tiền | Đo thời gian, mốc dữ liệu và kết quả đối soát; không suy rằng phục hồi bản sao là đủ để mở thanh toán |
| FIN-REQ-12 | R-FIN-11: quyền tồn dư | Khi nhận sự kiện thu hồi quyền đã được xác nhận, quyền duyệt và xuất dữ liệu của chủ thể bị thu hồi phải hết hiệu lực trong 10 phút trên các đường thuộc phạm vi | Thử phiên đang tồn tại, token và tác vụ xuất chưa hoàn tất theo chính sách; không tiếp tục hành động ngoài quyền sau thời hạn |

Để FIN-REQ-04 đầy đủ khi triển khai, phải xác định thời hạn giữ thông tin chống lặp và cách xử lý gửi lại ngoài thời hạn. Với FIN-REQ-11, RPO 5 phút không phải cam kết rằng có thể bỏ qua 5 phút giao dịch tài chính; giao dịch có thể đã hoàn tất bên ngoài phải được đối chiếu và xử lý trước khi tiếp tục.

Mỗi yêu cầu cần có chủ sở hữu và thành phần thực thi. Ví dụ, FIN-REQ-01 liên quan tới cổng API và dịch vụ nghiệp vụ; FIN-REQ-03 liên quan tới kho trạng thái và dịch vụ thực hiện; FIN-REQ-10 liên quan cả vận hành, dữ liệu và kết nối đối tác.

## 12. Lưu giữ, xóa và phục hồi

### 12.1. Chính sách lưu giữ theo mục đích

Không nên chọn một thời hạn cho mọi dữ liệu chỉ vì cùng thuộc nhóm tài chính. Cần phân biệt:

- Chứng từ và bản ghi cần để xác lập, đối soát hoặc điều tra giao dịch.
- Tệp xuất tạm, bản cache và dữ liệu trung gian.
- Log kỹ thuật và sự kiện kiểm toán.
- Dữ liệu dùng cho phân tích.
- Bản sao lưu và bản sao phục hồi.

Mỗi nhóm cần có mục đích, thời hạn hoặc điều kiện kết thúc, người chịu trách nhiệm và cách xử lý ngoại lệ. Nghĩa vụ giữ dữ liệu hoặc yêu cầu tạm giữ phục vụ một vụ việc phải được xác định qua quy trình có thẩm quyền.

Tệp xuất tạm không cần được giữ lâu chỉ vì nguồn gốc là dữ liệu tài chính. Ngược lại, không được xóa bản ghi cần giữ chỉ để đơn giản hóa yêu cầu xóa ở một hệ thống khác.

### 12.2. Xóa phải xét các bản sao

Xóa bản ghi chính không tự xóa dữ liệu trong kho phân tích, tệp xuất, hệ thống hỗ trợ và bản sao lưu. Đặc tả cần chỉ rõ:

- Những bản sao nào có thể xóa ngay.
- Những bản sao nào hết hạn theo chu kỳ có kiểm soát.
- Cách hạn chế truy cập trong thời gian còn giữ.
- Cách xử lý dữ liệu đã xóa khi phục hồi bản sao cũ.
- Bằng chứng hoàn thành trong phạm vi quản lý.

Nếu dùng kỹ thuật xóa bằng mật mã, phải đánh giá đầy đủ quan hệ khóa, bản sao khóa và bản rõ còn lại. Không coi việc xóa một tham chiếu khóa là chứng minh mọi dữ liệu đã không thể khôi phục.

### 12.3. Phục hồi nhất quán theo nghiệp vụ

**RTO** là mục tiêu thời gian khôi phục; **RPO** là mục tiêu mức mất dữ liệu chấp nhận được, thường biểu diễn bằng khoảng thời gian. Các mục tiêu này phải gắn với kịch bản, phạm vi và mốc đo.

Đối với thanh toán, phục hồi cơ sở dữ liệu chưa đủ. Cần phục hồi hoặc đối chiếu:

- Ý định đã phê duyệt và phiên bản được phép thực hiện.
- Giao dịch đã gửi nhưng chưa có phản hồi.
- Kết quả ở bên thanh toán.
- Sự kiện còn trong hàng đợi và thông tin chống lặp.
- Bằng chứng kiểm toán, khóa giải mã và quyền cần cho phục hồi.

Mở lại dịch vụ với trạng thái cũ có thể khiến giao dịch đã hoàn tất bên ngoài bị gửi lại. Quy trình phục hồi phải bao gồm điều kiện mở lại chức năng thay đổi tài sản, không chỉ điều kiện ứng dụng khởi động thành công.

## 13. Tình huống thực hành: đổi tài khoản sau khi duyệt

Một hệ thống cho phép nhân viên lập khoản thanh toán cho nhà cung cấp. Người quản lý đã duyệt số tiền và người nhận. Sau đó, người lập sửa tài khoản đích trong hồ sơ nhà cung cấp. Dịch vụ thực hiện đọc tài khoản mới nhất và chuyển tiền mà không yêu cầu duyệt lại.

### 13.1. Phân tích rủi ro

- Dữ liệu trọng yếu là tài khoản đích, phiên bản chỉ dẫn và bằng chứng phê duyệt.
- Ranh giới bị vi phạm là giữa nội dung đã duyệt và nội dung thực sự được thực hiện.
- Xác thực mạnh và mã hóa đường truyền không ngăn lỗi này vì người dùng có thể vẫn dùng quyền hợp lệ.
- Nhật ký chỉ ghi “đã thanh toán” không đủ để giải thích tài khoản nào đã được duyệt.

### 13.2. Yêu cầu cần bổ sung

1. Tài khoản đích của khoản chi phải được xác định trong phiên bản chỉ dẫn trình duyệt.
2. Thay đổi hồ sơ nhà cung cấp không tự thay nội dung của khoản chi đã duyệt.
3. Nếu nghiệp vụ cần cập nhật tài khoản đích của khoản chi, phê duyệt cũ phải hết hiệu lực.
4. Dịch vụ thực hiện phải kiểm tra phiên bản và trạng thái tại thời điểm nhận quyền thực hiện.
5. Dấu vết phải liên kết người lập, người duyệt, phiên bản và tài khoản đích thực tế bằng tham chiếu được bảo vệ.
6. Các thay đổi thông tin thụ hưởng phải có kiểm soát riêng theo mức rủi ro.

### 13.3. Tiêu chí kiểm thử

- Duyệt khoản chi rồi đổi tài khoản nhà cung cấp: khoản chi không âm thầm chuyển sang tài khoản mới.
- Sửa trực tiếp phiên bản khoản chi sau duyệt: phải yêu cầu duyệt lại hoặc bị từ chối.
- Gửi đồng thời yêu cầu sửa và thực hiện: không thực hiện nội dung chưa được duyệt.
- Kiểm tra bằng chứng: truy được nội dung đã duyệt và nội dung thực hiện mà không công khai tài khoản đầy đủ cho mọi người đọc log.

## 14. Những lỗi phân loại và đặc tả thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ coi dữ liệu tài chính là vấn đề bí mật | Bỏ sót gian lận, sửa số dư và thanh toán lặp | Đánh giá độc lập bí mật, toàn vẹn, sẵn sàng |
| Gắn nhãn theo tên bảng | Bỏ sót trường nhạy cảm trong bảng dùng chung | Theo dõi dữ liệu, đầu ra và hành động thực tế |
| Dùng mã giao dịch làm quyền truy cập | Người biết hoặc đoán ID đọc được dữ liệu khác | Kiểm tra chủ thể và quyền trên từng đối tượng |
| Chỉ kiểm soát nút giao diện | Có thể gọi API trực tiếp để vượt quy trình | Thực thi phân quyền và trạng thái ở phía tin cậy |
| Mã hóa nhưng cấp quyền đọc quá rộng | Người dùng hoặc dịch vụ hợp lệ vẫn lấy quá nhiều dữ liệu | Giới hạn quyền theo phạm vi và mục đích |
| Coi mọi timeout là thất bại | Gửi lại giao dịch đã hoàn tất | Có trạng thái bất định và cơ chế đối soát |
| Duyệt rồi cho sửa nội dung tùy ý | Thanh toán khác với ý định được duyệt | Gắn phê duyệt với phiên bản và trường trọng yếu |
| Ghi toàn bộ yêu cầu vào log | Tạo thêm kho dữ liệu tài chính không được kiểm soát | Lọc trường và kiểm tra cả đường lỗi |
| Sao chép production để kiểm thử | Mở rộng phạm vi lộ dữ liệu | Dùng dữ liệu tổng hợp hoặc bộ dữ liệu được xử lý phù hợp |
| Khôi phục dữ liệu rồi mở ngay thanh toán | Có thể gửi lặp hoặc bỏ sót giao dịch | Đối soát trạng thái nội bộ và bên ngoài trước khi mở lại |

## 15. Bài tập tự kiểm tra

### Bài tập 1: phân loại một tập dữ liệu

Một báo cáo gồm mã nhân viên, phòng ban, lương thực nhận, tài khoản ngân hàng và tổng chi phí theo phòng. Hãy xác định:

- Trường nào cần giữ bí mật và với ai.
- Trường nào có mức toàn vẹn cao.
- Đầu ra nào được phép cung cấp cho quản lý từng phòng.
- Rủi ro khi một phòng chỉ có một nhân viên.
- Những bản sao cần đưa vào phạm vi kiểm soát.

**Gợi ý:** tổng hợp theo phòng không tự loại bỏ khả năng suy ra lương cá nhân. Tài khoản nhận lương và số tiền cần được kiểm soát cả khi xem và khi thay đổi. Tệp xuất và log tạo báo cáo cũng phải được xét.

### Bài tập 2: viết lại yêu cầu chung chung

Viết lại câu:

> Chỉ người có quyền mới được sử dụng dữ liệu thanh toán.

Một câu trả lời có thể kiểm chứng cần chỉ ra người nào, phạm vi tổ chức nào, hành động nào, trường dữ liệu nào, trạng thái nào và bằng chứng từ chối.

**Gợi ý:** tách quyền xem, xuất, sửa người nhận, phê duyệt và thực hiện. Một người được xem dữ liệu không mặc nhiên có tất cả các quyền còn lại.

### Bài tập 3: xử lý kết quả bất định

Ứng dụng gửi lệnh chuyển tiền, sau đó hết thời gian chờ. Đối tác có thể đã xử lý nhưng ứng dụng chưa biết. Có nên tự tạo một giao dịch mới không?

**Gợi ý:** cần dựa vào tham chiếu giao dịch, cơ chế chống lặp và giao diện tra cứu của đối tác. Giữ trạng thái bất định, truy vấn hoặc đối soát theo quy trình; không suy từ timeout rằng tiền chưa được chuyển.

## 16. Mẫu hồ sơ yêu cầu sau phân loại

```text
Tài sản dữ liệu:
  Chỉ dẫn thanh toán nhà cung cấp trong production.

Mục tiêu:
  Chỉ thực hiện đúng nội dung đã được người có thẩm quyền phê duyệt.
  Không làm lộ chi tiết thanh toán ngoài phạm vi cần thiết.
  Phục hồi và đối soát được khi trạng thái xử lý bất định.

Phân loại:
  Bí mật: cao theo phạm vi tổ chức.
  Toàn vẹn: trọng yếu vì có thể thay đổi tài sản.
  Sẵn sàng: theo thời hạn thanh toán và kịch bản phục hồi.

Rủi ro:
  R-FIN-01: đọc dữ liệu ngoài phạm vi.
  R-FIN-03: đổi nội dung sau phê duyệt.
  R-FIN-04: thực hiện lặp.
  R-FIN-10: phục hồi trạng thái không nhất quán.

Thành phần thực thi:
  API và dịch vụ phân quyền.
  Kho phiên bản chỉ dẫn và bằng chứng phê duyệt.
  Dịch vụ thực hiện, hàng đợi và kết nối đối tác.
  Hệ thống kiểm toán và quy trình đối soát.

Yêu cầu liên kết:
  FIN-REQ-01, FIN-REQ-03, FIN-REQ-04, FIN-REQ-08, FIN-REQ-10.

Bằng chứng:
  Kiểm thử truy cập khác tổ chức.
  Kiểm thử sửa sau duyệt và yêu cầu đồng thời.
  Kiểm thử gửi lại và mất phản hồi.
  Diễn tập phục hồi có đối soát với bên ngoài.

Chủ sở hữu:
  Chủ sở hữu nghiệp vụ thanh toán và nhóm nền tảng liên quan.

Điều kiện chấp nhận:
  Đạt tiêu chí của từng yêu cầu.
  Các giới hạn và rủi ro còn lại được ghi nhận, có người chịu trách nhiệm.
```

Một kết quả phân loại hữu ích phải dẫn tới quyết định thực thi: ai được làm gì với dữ liệu nào, những bất biến nào phải được giữ, hệ thống phải hành xử ra sao khi lỗi và bằng chứng nào chứng minh các yêu cầu đó được đáp ứng.
