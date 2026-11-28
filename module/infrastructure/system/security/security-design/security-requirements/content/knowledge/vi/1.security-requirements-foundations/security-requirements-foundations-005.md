# Security requirement từ business risk

## Mục tiêu bài học

Một yêu cầu bảo mật có giá trị khi nó bảo vệ được một kết quả kinh doanh cụ thể và có cách chứng minh rằng hệ thống đã đáp ứng yêu cầu ấy. Câu “hệ thống phải an toàn” chưa cho nhóm phát triển biết phải xây gì, cũng chưa cho người kiểm thử biết khi nào được kết luận đạt.

Trong chương Nền tảng yêu cầu bảo mật, bài học này trình bày cách chuyển **rủi ro kinh doanh — business risk** thành **yêu cầu bảo mật — security requirement**. Mạch làm việc xuyên suốt là:

> Kết quả kinh doanh cần bảo vệ → kịch bản rủi ro → mục tiêu bảo mật → yêu cầu cụ thể → quyết định kiến trúc → bằng chứng kiểm thử → đánh giá rủi ro còn lại.

Sau bài học, bạn có thể:

- Mô tả rủi ro bằng một sự kiện và hậu quả đối với nghiệp vụ, thay vì chỉ ghi tên một lỗ hổng.
- Phân biệt mục tiêu, yêu cầu, biện pháp triển khai và tiêu chí chấp nhận.
- Viết yêu cầu có phạm vi, điều kiện, hành vi, ngưỡng đo và người chịu trách nhiệm.
- Liên kết yêu cầu xác thực, phân quyền, dữ liệu, logging và phục hồi với rủi ro tương ứng.
- Duy trì mối liên kết từ rủi ro đến kiểm thử trong vòng đời phát triển.

Các tên hệ thống, mã định danh và con số trong bài đều là **giả định minh họa**, không phải ngưỡng mặc định cho mọi sản phẩm. Nhóm thực tế phải xác nhận chúng với chủ quy trình, chủ dữ liệu và người có thẩm quyền chấp nhận rủi ro.

## 1. Bắt đầu từ điều doanh nghiệp có thể mất

### 1.1. Business risk là gì trong bài toán bảo mật?

Rủi ro kinh doanh là khả năng một sự kiện không mong muốn làm tổn hại mục tiêu của tổ chức. Trong thiết kế bảo mật, sự kiện đó có thể xuất phát từ tấn công, lạm dụng quyền, sai sót vận hành hoặc lỗi thiết kế làm mất tính bí mật, toàn vẹn hay khả dụng của thông tin và dịch vụ.

Không nên xem mọi rủi ro kinh doanh là một vấn đề bảo mật. Nhu cầu thị trường giảm là rủi ro kinh doanh nhưng không được giải quyết bằng phân quyền API. Ngược lại, người không được phép phê duyệt lệnh xuất kho là một vấn đề mà yêu cầu bảo mật có thể trực tiếp xử lý.

Một mô tả hữu ích cần trả lời được:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Mục tiêu nghiệp vụ | Quy trình phải đạt kết quả gì? | Chỉ xuất hàng sau khi có phê duyệt hợp lệ |
| Tài sản hoặc quy trình | Điều gì đang cần được bảo vệ? | Lệnh xuất kho, số lượng hàng, lịch sử phê duyệt |
| Sự kiện đe dọa | Điều gì có thể xảy ra trái mong muốn? | Người tạo lệnh tự phê duyệt bằng API |
| Điều kiện tạo cơ hội | Vì sao sự kiện có thể xảy ra? | Máy chủ chỉ kiểm tra vai trò, bỏ qua quan hệ người tạo |
| Hậu quả kinh doanh | Doanh nghiệp bị ảnh hưởng thế nào? | Xuất hàng không được kiểm soát, mất hàng, khó quy trách nhiệm |
| Bối cảnh | Rủi ro nằm ở đâu và trong điều kiện nào? | Lệnh giá trị cao trên cổng đặt hàng B2B nhiều khách hàng |

Một cách diễn đạt ngắn gọn là:

> Do [điều kiện], [tác nhân hoặc sự kiện] có thể tác động lên [tài sản/quy trình], dẫn đến [hậu quả kinh doanh].

Ví dụ:

> Do API phê duyệt không đối chiếu người tạo lệnh, người dùng có cả quyền tạo và quyền duyệt có thể tự duyệt lệnh xuất kho giá trị cao, dẫn đến việc xuất hàng thiếu kiểm soát độc lập.

Mô tả này cho thấy một thuộc tính cần bảo vệ: tính độc lập của phê duyệt. Nó hữu ích hơn câu “có rủi ro kiểm soát truy cập” vì chỉ ra điều kiện, hành vi và hậu quả cụ thể cần kiểm chứng.

### 1.2. Phân biệt đe dọa, điểm yếu và rủi ro

- **Đe dọa:** một hành vi hoặc sự kiện có thể gây hại, như nhân viên lạm dụng quyền duyệt lệnh.
- **Điểm yếu:** điều kiện cho phép hành vi ấy thành công, như chỉ ẩn nút trên giao diện nhưng API vẫn chấp nhận yêu cầu.
- **Rủi ro:** khả năng sự kiện xảy ra cùng mức ảnh hưởng đối với nghiệp vụ trong bối cảnh cụ thể.
- **Biện pháp kiểm soát:** cách ngăn chặn, phát hiện hoặc giảm hậu quả, như kiểm tra quyền tại máy chủ và lưu dấu vết phê duyệt.

Mô hình đe dọa giúp tìm đường đi của hành vi gây hại qua giao diện, API, tiến trình nền và ranh giới tin cậy. Phân tích rủi ro giúp xác định đường đi nào cần ưu tiên xử lý và mức bảo vệ nào là phù hợp. Hai hoạt động bổ sung cho nhau; tên của một mối đe dọa chưa đủ để quyết định yêu cầu cuối cùng.

## 2. Tách rõ mục tiêu, yêu cầu, giải pháp và bằng chứng

Bốn lớp này thường bị trộn lẫn, khiến một danh sách công nghệ bị nhầm là đặc tả bảo mật.

| Lớp | Vai trò | Ví dụ |
|---|---|---|
| Mục tiêu bảo mật | Nêu kết quả cần bảo vệ | Lệnh xuất kho giá trị cao phải được kiểm soát độc lập |
| Yêu cầu bảo mật | Nêu điều kiện và hành vi bắt buộc, có thể kiểm chứng | Máy chủ từ chối phê duyệt nếu người duyệt trùng người tạo lệnh thuộc diện kiểm soát độc lập |
| Quyết định thiết kế | Chọn cách thực hiện yêu cầu | Dịch vụ phê duyệt gọi bộ đánh giá chính sách và ghi trạng thái trong giao dịch dữ liệu |
| Tiêu chí chấp nhận | Quy định bằng chứng đạt hoặc không đạt | Gọi API trực tiếp bằng danh tính người tạo phải bị từ chối và không thay đổi trạng thái lệnh |

“Dùng JWT” không chứng minh người dùng có quyền trên một lệnh xuất kho. “Có MFA” không chứng minh người duyệt độc lập với người tạo. “Ghi log đầy đủ” không cho biết cần có trường nào, ai xem được hoặc hành vi nào phải phát cảnh báo.

Yêu cầu nên mô tả thuộc tính cần đạt, giữ đủ không gian để lựa chọn thiết kế. Nếu nền tảng hoặc chính sách đã bắt buộc một thành phần kỹ thuật, yêu cầu có thể ghi rõ thành phần ấy và nguồn ràng buộc. Điều quan trọng là giải thích được nó phục vụ rủi ro hoặc nghĩa vụ nào.

Không nên mặc định rằng yêu cầu bảo mật chỉ là yêu cầu phi chức năng. Kiểm tra quyền, thu hồi phiên và phê duyệt độc lập đều quy định hành vi chức năng. Mức khả dụng hoặc thời gian phục hồi lại là các thuộc tính chất lượng. Một đặc tả hoàn chỉnh có thể cần cả hai.

## 3. Ví dụ xuyên suốt: cổng xử lý lệnh xuất kho B2B

Giả sử một hệ thống phục vụ nhiều doanh nghiệp khách hàng. Mỗi khách hàng là một tenant; tenant là phạm vi dữ liệu và quyền của một doanh nghiệp. Người dùng tạo lệnh xuất kho, người được phân công phê duyệt, sau đó kho tiếp nhận lệnh để thực hiện.

Các giả định nghiệp vụ đã được chủ quy trình chấp thuận trong ví dụ:

1. Lệnh được định giá bằng VND. Lệnh có tổng giá trị **từ 100 triệu đồng trở lên** cần người duyệt khác người tạo.
2. Người duyệt phải có quyền duyệt trong đúng tenant và đúng kho của lệnh.
3. Nội dung lệnh được duyệt phải là nội dung kho nhận để thực hiện. Nếu thay đổi mặt hàng, số lượng, nơi nhận hoặc giá trị sau duyệt, phê duyệt cũ mất hiệu lực.
4. Dữ liệu lệnh, giá bán và nơi nhận của tenant này không được tiết lộ cho tenant khác.
5. Việc gián đoạn cổng xử lý lệnh có thể làm chậm hoạt động kho; cần có mục tiêu phục hồi được thống nhất.

Ngưỡng giá trị và quy tắc ai được duyệt là quyết định nghiệp vụ; nhóm kỹ thuật phải làm chúng rõ ràng trước khi hiện thực.

### 3.1. Lập các kịch bản rủi ro đủ cụ thể

| Mã | Kịch bản | Hậu quả cần hạn chế | Chủ rủi ro trong ví dụ |
|---|---|---|---|
| RISK-01 | Người tạo tự duyệt hoặc sửa nội dung sau khi lệnh đã được duyệt | Xuất hàng thiếu phê duyệt hợp lệ, thất thoát và tranh chấp | Chủ quy trình xuất kho |
| RISK-02 | Người dùng truy cập lệnh hoặc tệp xuất của tenant khác | Lộ dữ liệu kinh doanh và mất lòng tin khách hàng | Chủ dữ liệu khách hàng |
| RISK-03 | Dữ liệu lệnh hoặc dịch vụ không khôi phục được sau sự cố | Ngừng xử lý kho, mất hoặc đối soát sai giao dịch | Chủ dịch vụ vận hành |
| RISK-04 | Không xác định được ai đã duyệt, sửa hoặc từ chối một lệnh | Không điều tra được sự cố hoặc phân định trách nhiệm | Chủ quy trình xuất kho |

Chủ rủi ro chịu trách nhiệm về hậu quả đối với hoạt động kinh doanh và quyết định xử lý trong phạm vi thẩm quyền. Người triển khai, vận hành và kiểm thử có trách nhiệm riêng; không nên mặc định lập trình viên là người được quyền chấp nhận mọi rủi ro còn lại.

### 3.2. Đánh giá mức ưu tiên mà không tạo cảm giác chính xác giả

Với mỗi kịch bản, nhóm cần ghi căn cứ cho ít nhất hai chiều:

- **Khả năng xảy ra:** có đường truy cập nào, cần loại tài khoản nào, mức phơi lộ ra sao, có kiểm soát nào đang hoạt động?
- **Mức ảnh hưởng:** có thể mất gì, phạm vi khách hàng nào bị tác động, quy trình gián đoạn bao lâu và có thể phục hồi đến đâu?

Thang định tính như thấp, vừa, cao chỉ có ý nghĩa khi có định nghĩa thống nhất. Không nên tùy tiện nhân các thứ hạng 1–5 rồi xem kết quả là xác suất hoặc tổn thất tiền tệ chính xác. Nếu tổ chức dùng ma trận rủi ro, hãy ghi rõ thang đo, quy tắc xếp hạng và những giả định còn thiếu bằng chứng.

Đồng thời cần thống nhất đang đánh giá **trước các kiểm soát nào** và **sau các kiểm soát nào**. Một nhãn “cao” sẽ khó sử dụng nếu người này đánh giá hệ thống chưa có kiểm soát, người khác lại giả định đã có kiểm tra quyền và giám sát.

Ví dụ, RISK-01 được ưu tiên sớm vì một người dùng nội bộ có thể trực tiếp gọi API và hậu quả liên quan đến hàng hóa thực. Tuy nhiên, kết luận về mức cao hay thấp vẫn phải dựa trên quyền đang cấp, khối lượng giao dịch, cơ chế kho kiểm tra và tác động thực tế của doanh nghiệp.

## 4. Quy trình chuyển rủi ro thành yêu cầu

### Bước 1: Xác định kết quả nghiệp vụ và phạm vi

Với RISK-01, kết quả cần bảo vệ là: mọi lệnh thuộc diện kiểm soát độc lập chỉ được thực hiện khi đã có người đủ thẩm quyền phê duyệt đúng nội dung.

Cần chỉ rõ phạm vi: API duyệt lệnh, luồng sửa lệnh, tác vụ nhập hàng loạt, ứng dụng di động và đường chuyển lệnh sang hệ thống kho. Một yêu cầu chỉ đề cập giao diện web sẽ bỏ sót các đường khác có cùng tác động nghiệp vụ.

### Bước 2: Chọn cách xử lý rủi ro

Những lựa chọn thường gặp gồm:

- **Tránh:** chưa cung cấp chức năng tự động xuất kho khi chưa kiểm soát được phê duyệt.
- **Giảm thiểu:** bổ sung phân quyền, kiểm soát trạng thái và kiểm thử các đường vượt quyền.
- **Chia sẻ hoặc chuyển giao một phần:** dùng một nhà cung cấp hoặc thỏa thuận dịch vụ để chia sẻ một số hậu quả; tổ chức vẫn phải xác định phần trách nhiệm còn lại.
- **Chấp nhận:** người có thẩm quyền đồng ý giữ rủi ro trong điều kiện và thời hạn xác định.

Không phải mỗi rủi ro đều cần thêm một tính năng bảo mật. Nhưng quyết định không xây một kiểm soát cũng cần căn cứ, người quyết định và điều kiện xem xét lại. Hạn chế nguồn lực không tự động biến thành sự chấp nhận rủi ro hợp lệ.

### Bước 3: Nêu thuộc tính cần giữ đúng

Một **bất biến bảo mật** là điều phải luôn đúng tại những thời điểm quyết định đã xác định. Với phê duyệt xuất kho:

> Không tồn tại lệnh từ 100 triệu đồng trở lên được chuyển sang bước thực hiện nếu người phê duyệt hợp lệ trùng người tạo hoặc nếu phê duyệt không khớp phiên bản hiện tại của lệnh.

Bất biến giúp phát hiện khoảng trống ở ranh giới giữa các dịch vụ. Kiểm tra tại lúc bấm nút duyệt chưa đủ nếu một tác vụ nền có thể chuyển lệnh đã bị sửa sang kho sau đó.

### Bước 4: Tách thành các yêu cầu có trách nhiệm rõ ràng

Một rủi ro có thể cần nhiều yêu cầu. Một yêu cầu cũng có thể giảm nhiều rủi ro. Không cần ép chúng thành quan hệ một–một.

Ví dụ, phê duyệt hợp lệ cần đồng thời:

- Xác thực được danh tính hiện tại của người thao tác.
- Kiểm tra quyền theo tenant, kho và quan hệ với lệnh.
- Gắn phê duyệt với đúng phiên bản dữ liệu.
- Bảo vệ quyết định chuyển trạng thái trước các cập nhật đồng thời.
- Lưu được dấu vết phục vụ phát hiện và điều tra.

Tách yêu cầu giúp nhóm kiểm thử chỉ ra chính xác thuộc tính nào thất bại. Tuy vậy, phải giữ liên kết chung về bất biến để tránh tình trạng từng thành phần đều “đạt” nhưng toàn bộ quy trình vẫn cho xuất lệnh sai.

### Bước 5: Chốt ngưỡng, ngoại lệ và tiêu chí đạt

Những từ như “giá trị cao”, “nhanh”, “đầy đủ” hay “đủ quyền” đều cần được định nghĩa.

Trong ví dụ, “giá trị cao” là từ 100 triệu VND và giá trị được máy chủ tính từ dữ liệu hợp lệ của lệnh. Nếu sản phẩm dùng nhiều đồng tiền, cần xác định quy tắc quy đổi và thời điểm áp dụng; chưa có quyết định ấy thì yêu cầu chưa sẵn sàng triển khai cho luồng đa tiền tệ.

Ngoại lệ cũng phải là một phần của đặc tả. Nếu hệ thống hỗ trợ quyền xử lý khẩn cấp, cần nêu ai được kích hoạt, trong trường hợp nào, tác vụ được phép, thời hạn, ghi nhận và hậu kiểm. Không tự ngầm hiểu quản trị viên được phép bỏ qua mọi quy tắc.

### Bước 6: Liên kết tới thiết kế, kiểm thử và đánh giá lại

Mỗi yêu cầu cần có nơi thực thi dự kiến và bằng chứng chấp nhận. Thay đổi kiến trúc có thể đổi nơi thực thi, nhưng không được làm biến mất kết quả bảo vệ đã thống nhất.

Sau triển khai, đánh giá lại rủi ro dựa trên bằng chứng thực tế. Có kiểm thử đạt giúp tăng độ tin cậy đối với phạm vi đã kiểm tra; điều đó không chứng minh hệ thống không còn mọi đường tấn công.

## 5. Cấu trúc một yêu cầu bảo mật có thể kiểm chứng

Mẫu câu cơ bản:

> Khi [điều kiện], [thành phần chịu trách nhiệm] phải [hành vi bắt buộc] đối với [đối tượng/phạm vi], đáp ứng [ngưỡng hoặc bất biến]; nếu không thể xác minh [điều kiện an toàn], hệ thống phải [hành vi lỗi được quy định].

Một bản ghi thực hành có thể dùng cấu trúc sau:

```text
ID: SEC-REQ-02
Tên: Phân quyền và tính độc lập của người duyệt
Nguồn: RISK-01; quy tắc phê duyệt của chủ quy trình xuất kho
Phạm vi: Mọi đường chuyển lệnh sang trạng thái đã duyệt
Điều kiện: Người dùng yêu cầu duyệt một lệnh đang chờ duyệt
Hành vi bắt buộc:
  - Xác thực người thao tác và kiểm tra quyền trên tenant, kho của lệnh.
  - Với lệnh từ 100 triệu VND, người duyệt phải khác người tạo.
  - Không tin tenant, quyền hoặc người tạo do client tự khai báo.
Hành vi khi từ chối:
  - Không thay đổi trạng thái, không gửi lệnh thực hiện sang kho.
  - Trả kết quả lỗi theo hợp đồng API; không tiết lộ dữ liệu tenant khác.
Tiêu chí chấp nhận: AT-02 và các tình huống trong ma trận phân quyền
Chủ yêu cầu: Chủ quy trình xuất kho
Bên triển khai: Nhóm dịch vụ lệnh xuất kho
Bằng chứng: Kết quả kiểm thử API và kiểm thử tích hợp chuyển lệnh sang kho
```

Trong mẫu này, AT-02 là kịch bản chấp nhận minh họa cho SEC-REQ-02 ở mục 7. Khi dùng thực tế, mã bằng chứng phải trỏ tới kịch bản hoặc kết quả kiểm thử cụ thể trong hệ thống quản lý của nhóm.

Không bắt buộc mọi bản ghi đều có cùng độ dài. Tuy nhiên, khi một thông tin quyết định khả năng kiểm thử hoặc trách nhiệm xử lý, nó phải xuất hiện trong yêu cầu hoặc trong tài liệu được liên kết rõ ràng.

Tránh gom nhiều mệnh đề không liên quan vào một câu dài. Ví dụ “phải mã hóa, phân quyền, sao lưu và có log” chứa nhiều hành vi với cách chứng minh khác nhau. Hãy tách thành các yêu cầu có mã riêng và liên kết về cùng rủi ro khi phù hợp.

## 6. Bộ yêu cầu minh họa gắn với rủi ro

### 6.1. SEC-REQ-01 — Xác thực trước thao tác nhạy cảm

**Nguồn:** RISK-01, RISK-04.

Mọi yêu cầu phê duyệt lệnh phải được máy chủ xác thực và gắn với một danh tính người dùng còn hiệu lực. Yêu cầu không có thông tin xác thực hợp lệ phải bị từ chối trước khi thay đổi trạng thái lệnh.

Trong giả định của ví dụ, phê duyệt lệnh từ 100 triệu VND cần bằng chứng MFA được xác minh trong vòng **5 phút** trước thời điểm phê duyệt. MFA là xác thực đa yếu tố. Máy chủ phải kiểm chứng thời điểm và kết quả MFA từ nguồn xác thực tin cậy; một cờ do client gửi như `mfaPassed=true` không phải bằng chứng. Bằng chứng đó phải gắn với danh tính và phiên đang thực hiện thao tác.

Ngưỡng 5 phút là quyết định minh họa của chủ quy trình sau khi cân nhắc rủi ro chiếm phiên và ảnh hưởng thao tác. Nó không phải đặc tính tự có của MFA. Nhóm còn phải chọn phương thức MFA phù hợp với kịch bản đe dọa; không phải mọi phương thức có cùng khả năng chống tấn công.

**Chấp nhận:** thiếu hoặc hết hạn xác thực thì không phê duyệt; bằng chứng MFA của tài khoản hay phiên khác không được chấp nhận; tại đúng ranh giới thời gian, hệ thống xử lý theo quy tắc tuổi bằng chứng đã đặc tả. Trong ví dụ này, tuổi bằng chứng không vượt quá 5 phút, thời điểm tương lai không hợp lệ và việc kiểm tra dùng thời gian phía máy chủ đã được đồng bộ.

### 6.2. SEC-REQ-02 — Quyền trên đối tượng và phân tách nhiệm vụ

**Nguồn:** RISK-01, RISK-02.

Trước khi duyệt, máy chủ phải kiểm tra người dùng có quyền duyệt tại tenant và kho của lệnh. Với lệnh từ 100 triệu VND, danh tính người duyệt phải khác người tạo. Vai trò quản trị giao diện không tự động tạo ngoại lệ đối với quy tắc này.

Thông tin tenant, kho, giá trị và người tạo phải được lấy từ dữ liệu có thẩm quyền phía máy chủ. Việc giấu nút trên UI chỉ hỗ trợ trải nghiệm; nó không thay thế quyết định quyền tại đường xử lý thay đổi trạng thái.

Nếu không lấy được dữ liệu cần thiết để đánh giá quyền, hệ thống không được chuyển lệnh sang đã duyệt hoặc gửi lệnh thực hiện sang kho. Đối với bước quyết định này, không thể kiểm tra quyền phải dẫn đến từ chối thao tác. Hành vi suy giảm của các chức năng khác cần đặc tả riêng theo ảnh hưởng nghiệp vụ.

**Chấp nhận:** kiểm thử người tạo tự duyệt, người có vai trò ở sai tenant, người có quyền ở sai kho, người đã mất quyền và người đủ quyền. Mỗi trường hợp bị từ chối phải được kiểm tra cả phản hồi API lẫn việc không phát sinh chuyển trạng thái hoặc thông điệp xuất kho.

### 6.3. SEC-REQ-03 — Tính toàn vẹn của lệnh đã phê duyệt

**Nguồn:** RISK-01.

Phê duyệt phải gắn với một phiên bản cụ thể của lệnh. Thay đổi mặt hàng, số lượng, nơi nhận hoặc giá trị sau phê duyệt phải làm mất hiệu lực phê duyệt cũ và đưa lệnh về quy trình duyệt lại trước khi được thực hiện.

Tại thời điểm cam kết chuyển sang bước thực hiện, hệ thống phải xác minh phiên bản đang được chuyển chính là phiên bản được phê duyệt hợp lệ. Các cập nhật đồng thời không được tạo ra trạng thái mà nội dung mới kế thừa phê duyệt của nội dung cũ.

**Chấp nhận:** kiểm thử luồng sửa sau duyệt và luồng sửa đồng thời với duyệt/chuyển kho. Kết quả đạt phải giữ được bất biến: không thực hiện phiên bản chưa được duyệt hợp lệ, kể cả khi các yêu cầu hoàn thành theo thứ tự khác nhau.

Một quyết định kiến trúc có thể dùng kiểm soát phiên bản, điều kiện cập nhật hoặc giao dịch phù hợp. Yêu cầu không mặc định rằng chỉ thêm một trường `version` là đủ; toàn bộ đường chuyển trạng thái phải thực sự kiểm tra và duy trì điều kiện ấy.

### 6.4. SEC-REQ-04 — Cách ly dữ liệu giữa các tenant

**Nguồn:** RISK-02.

Mọi đường đọc, tìm kiếm, sửa, xuất và tải xuống dữ liệu lệnh phải giới hạn kết quả theo tenant mà danh tính đã xác thực được phép truy cập. Quy tắc phải áp dụng cho cả API, tác vụ nền tạo tệp, cache và đường tải tệp kết quả.

Một định danh khó đoán không thay thế kiểm tra quyền. Tương tự, lọc tenant tại giao diện không bảo vệ API nếu máy chủ vẫn đọc đối tượng chỉ bằng mã lệnh.

**Chấp nhận:** chuẩn bị ít nhất hai tenant với dữ liệu phân biệt và thử dùng danh tính tenant A truy cập đối tượng của tenant B qua từng đường được liệt kê. Kiểm tra nội dung phản hồi, số lượng kết quả, tệp xuất và nội dung cache theo phạm vi đã đặc tả. Phản hồi không được tiết lộ nội dung hoặc xác nhận sự tồn tại của đối tượng tenant khác; mã lỗi phải nhất quán với hợp đồng API đã thống nhất.

### 6.5. SEC-REQ-05 — Dấu vết phục vụ điều tra và phát hiện

**Nguồn:** RISK-01, RISK-04.

Hệ thống phải tạo sự kiện audit cho yêu cầu phê duyệt, kết quả cho phép hoặc từ chối, thay đổi nội dung sau duyệt và việc chuyển lệnh sang kho. Audit ở đây là dấu vết phục vụ truy vết và kiểm tra hoạt động. Sự kiện phải có mã sự kiện, thời điểm phía máy chủ, danh tính tác nhân, tenant, mã lệnh, hành động, kết quả, mã lý do và mã liên kết giao dịch/yêu cầu. Sự kiện liên quan tới phê duyệt phải ghi phiên bản lệnh và phiên bản chính sách áp dụng.

Người dùng nghiệp vụ không được sửa hoặc xóa sự kiện audit. Quyền đọc và quản trị kho audit phải được cấp riêng, có ghi nhận hoạt động quản trị. Không ghi mật khẩu, token phiên, bí mật MFA hoặc toàn bộ nội dung nhạy cảm không cần thiết vào log.

Trong ví dụ, chủ rủi ro thống nhất rằng không được hoàn tất phê duyệt nếu chưa có một bản ghi sự kiện thành công được lưu bền vững cùng kết quả nghiệp vụ. Nhóm có thể chọn cơ chế ghi đồng bộ hoặc lưu một sự kiện bền vững để chuyển tiếp; phải chứng minh không có trạng thái “đã duyệt nhưng mất hoàn toàn dấu vết”. Nếu chỉ có log một lần thử bị ngắt giữa chừng, cơ chế đối soát phải phân biệt được với phê duyệt đã cam kết.

Để phát hiện hành vi đáng ngờ, ví dụ đặt thêm yêu cầu cảnh báo khi một danh tính có ít nhất **5 lần bị từ chối phê duyệt trong cửa sổ trượt 10 phút**. Cảnh báo phải đến hàng đợi của nhóm vận hành trong **2 phút** kể từ sự kiện đủ ngưỡng được ghi nhận. Giá trị này cần được hiệu chỉnh theo lưu lượng và năng lực xử lý thực tế.

**Chấp nhận:** đối chiếu thao tác thành công/thất bại với sự kiện tương ứng; thử gián đoạn đường chuyển tiếp audit; xác minh việc phân quyền sửa/xóa; kiểm tra ranh giới ngưỡng và độ trễ cảnh báo. Kiểm thử thời gian cảnh báo phải nêu điều kiện tải và cách đo, không chỉ kiểm tra có một thông báo xuất hiện.

### 6.6. SEC-REQ-06 — Phục hồi được quy trình và dữ liệu

**Nguồn:** RISK-03.

Giả sử chủ dịch vụ đã thống nhất **RPO không quá 15 phút** và **RTO không quá 60 phút** cho kịch bản mất cơ sở dữ liệu chính nhưng môi trường phục hồi và bản sao lưu còn sử dụng được.

- **RPO — Recovery Point Objective:** mức mất dữ liệu tối đa có thể chấp nhận, biểu diễn bằng khoảng thời gian. Trong kịch bản này, dữ liệu được khôi phục không được thiếu quá 15 phút cập nhật đã cam kết trước thời điểm sự cố.
- **RTO — Recovery Time Objective:** thời gian mục tiêu để khôi phục dịch vụ tới mức vận hành đã thống nhất. Trong ví dụ, đo từ thời điểm gián đoạn đến khi người dùng thử nghiệm có thể tạo, duyệt và chuyển lệnh hợp lệ sang kho, đồng thời các kiểm tra tính toàn vẹn đã đạt.

Bản sao lưu phải được bảo vệ khỏi sửa/xóa bởi tài khoản vận hành ứng dụng thông thường. Quyền phục hồi phải được kiểm soát và ghi nhận. Nếu doanh nghiệp cần chịu được cả kịch bản tài khoản quản trị sao lưu bị chiếm, phải phân tích và đặc tả bổ sung; không suy rằng yêu cầu hiện tại đã bao phủ kịch bản đó.

**Chấp nhận:** thực hiện diễn tập phục hồi trong môi trường đại diện, ghi thời điểm bắt đầu sự cố, điểm dữ liệu khôi phục và thời điểm đạt tiêu chí phục hồi. Đối chiếu trạng thái lệnh với hệ thống kho hoặc nhật ký giao dịch có thẩm quyền để xử lý các giao dịch đã chuyển kho nhưng chưa có trong bản phục hồi.

Lịch chạy sao lưu mỗi 15 phút chưa tự chứng minh đạt RPO 15 phút: sao lưu có thể lỗi, không nhất quán hoặc không khôi phục được. Tương tự, “máy chủ đã chạy lại” chưa chứng minh đạt RTO nếu người dùng chưa thực hiện được quy trình thiết yếu. Chu kỳ diễn tập và phạm vi sự cố phải được thống nhất riêng trong kế hoạch vận hành.

## 7. Từ yêu cầu đến tiêu chí kiểm thử có thể lặp lại

Một tiêu chí tốt mô tả được dữ liệu ban đầu, hành động, kết quả mong đợi và bằng chứng quan sát. Nó phải chứa trường hợp hợp lệ, trường hợp bị cấm và các ranh giới quan trọng.

Ví dụ AT-02 cho SEC-REQ-02:

```gherkin
Feature: Phê duyệt lệnh xuất kho cần kiểm soát độc lập

  Scenario: Người tạo không được tự duyệt lệnh đạt ngưỡng
    Given lệnh L-001 thuộc tenant A và kho K1
      And tổng giá trị do máy chủ tính là 100000000 VND
      And người dùng U1 là người tạo lệnh
      And U1 đã xác thực và có quyền duyệt tại tenant A, kho K1
      And bằng chứng MFA của phiên U1 còn hợp lệ
    When U1 gọi trực tiếp API phê duyệt L-001
    Then yêu cầu bị từ chối vì vi phạm tính độc lập
      And lệnh vẫn ở trạng thái chờ duyệt
      And không có thông điệp thực hiện lệnh được phát sang kho
      And sự kiện audit ghi kết quả từ chối với mã lý do tương ứng
```

Các tình huống bổ sung cần liên kết với đúng yêu cầu:

| Tình huống | Thuộc tính cần chứng minh | Yêu cầu |
|---|---|---|
| U2 khác người tạo, đủ quyền, đúng phiên bản và MFA hợp lệ | Luồng hợp lệ vẫn hoạt động | SEC-REQ-01, 02, 03 |
| Người tạo tự duyệt lệnh đúng 100 triệu VND | Ranh giới ngưỡng không bị bỏ sót | SEC-REQ-02 |
| Người tạo duyệt lệnh dưới ngưỡng | Chỉ áp dụng quy tắc độc lập khi đạt ngưỡng; mọi điều kiện quyền khác vẫn bắt buộc | SEC-REQ-02 |
| U2 có vai trò duyệt nhưng ở tenant hoặc kho khác | Quyền gắn với đối tượng và phạm vi nghiệp vụ | SEC-REQ-02, 04 |
| Client sửa trường tổng giá trị gửi lên | Quyết định dựa trên dữ liệu phía máy chủ | SEC-REQ-02 |
| Hai yêu cầu sửa và chuyển kho chạy đồng thời | Không dùng phê duyệt cũ cho dữ liệu mới | SEC-REQ-03 |
| Tác vụ xuất dữ liệu chạy bằng tài khoản dịch vụ | Công việc nền vẫn giữ ranh giới tenant | SEC-REQ-04 |
| Đường chuyển tiếp audit bị gián đoạn | Bản ghi cần thiết vẫn tồn tại bền vững | SEC-REQ-05 |
| Khôi phục bản sao lưu trong diễn tập | Dữ liệu và quy trình đạt RPO/RTO theo kịch bản | SEC-REQ-06 |

Kiểm thử chỉ kiểm tra mã HTTP là chưa đủ đối với thao tác có tác dụng phụ. Một API có thể trả lỗi nhưng giao dịch đã thay đổi trạng thái hoặc đã phát thông điệp. Cần kiểm tra trạng thái dữ liệu và tác động liên quan tại ranh giới được yêu cầu bảo vệ.

Không dùng số lượng kiểm thử đạt làm thước đo duy nhất cho mức an toàn. Một kiểm thử đúng đường vượt quyền quan trọng có thể cung cấp bằng chứng cần thiết hơn nhiều kiểm thử lặp lại luồng hợp lệ.

## 8. Giữ liên kết giữa rủi ro, kiến trúc và bằng chứng

Một ma trận truy vết tối thiểu giúp trả lời: rủi ro này được xử lý ở đâu và bằng chứng nào hỗ trợ kết luận?

| Rủi ro | Mục tiêu bảo vệ | Yêu cầu | Điểm thực thi dự kiến | Bằng chứng |
|---|---|---|---|---|
| RISK-01 | Chỉ thực hiện lệnh được phê duyệt hợp lệ | SEC-REQ-01, 02, 03, 05 | Dịch vụ danh tính, dịch vụ lệnh, đường chuyển kho, kho audit | Kiểm thử xác thực, ma trận quyền, kiểm thử đồng thời và đối chiếu sự kiện |
| RISK-02 | Cách ly dữ liệu khách hàng | SEC-REQ-02, 04 | API, lớp truy cập dữ liệu, tác vụ nền, cache, tải tệp | Kiểm thử truy cập chéo tenant trên từng đường |
| RISK-03 | Phục hồi vận hành trong mức chấp nhận | SEC-REQ-06 | Sao lưu, hạ tầng phục hồi, quy trình đối soát | Biên bản diễn tập và số đo RPO/RTO |
| RISK-04 | Xác định được hành vi và kết quả | SEC-REQ-01, 05 | Danh tính, điểm ghi sự kiện, kho audit | Đối chiếu giao dịch với dấu vết và kiểm tra quyền audit |

Đây là điểm thực thi dự kiến, chưa phải thiết kế chi tiết bắt buộc. Khi kiến trúc thay đổi, nhóm phải rà lại tất cả đường có thể gây cùng hậu quả nghiệp vụ. Ví dụ, bổ sung API nhập lệnh hàng loạt có thể tạo ra một đường thực thi mới cần giữ nguyên quy tắc phân quyền và phê duyệt.

Mỗi liên kết nên đi kèm phiên bản yêu cầu, người phụ trách, trạng thái triển khai và nơi lưu bằng chứng. Một yêu cầu đã viết, đã lập trình và đã kiểm thử là ba trạng thái khác nhau. Báo cáo “đã có yêu cầu” không được hiểu thành “rủi ro đã được giảm tới mức chấp nhận”.

## 9. Đánh giá rủi ro còn lại và quản lý thay đổi

**Rủi ro còn lại — residual risk** là rủi ro vẫn tồn tại sau khi xét các biện pháp đã áp dụng và hiệu quả thực tế của chúng.

Trong ví dụ, quy tắc người tạo khác người duyệt làm khó hành vi tự phê duyệt, nhưng không ngăn tuyệt đối hai người thông đồng. MFA có thể giảm một số đường chiếm tài khoản, nhưng không thay thế đánh giá độ tin cậy của phiên, thiết bị hoặc hành vi người dùng. Audit hỗ trợ phát hiện và điều tra; nó không tự thu hồi được hàng đã xuất.

Một bản ghi chấp nhận rủi ro còn lại nên nêu:

- Kịch bản nào còn tồn tại và hậu quả dự kiến.
- Kiểm soát nào đã có, cùng bằng chứng và giới hạn hiệu lực.
- Ai có thẩm quyền chấp nhận, quyết định vào thời điểm nào.
- Thời hạn hoặc sự kiện bắt buộc đánh giá lại.
- Hành động tiếp theo nếu giả định không còn đúng.

Những thay đổi như thêm kênh tích hợp, tăng quyền cho tài khoản dịch vụ, đổi ngưỡng duyệt, mở thêm tenant hoặc thay đổi quy trình kho phải kích hoạt xem xét lại các yêu cầu liên quan. Việc xem xét bắt đầu từ hậu quả nghiệp vụ, rồi lần theo liên kết đến các điểm thực thi và kiểm thử.

Nếu một ngoại lệ tạm thời cho phép bỏ qua yêu cầu, không được để nó tồn tại vô thời hạn dưới dạng một cờ cấu hình không có chủ sở hữu. Cần có phạm vi, lý do, người chịu trách nhiệm, điều kiện kiểm soát thay thế và ngày hết hạn hoặc mốc xem xét lại.

## 10. Các lỗi thường gặp khi chuyển business risk thành requirement

| Cách viết hoặc cách làm | Vấn đề | Cách cải thiện |
|---|---|---|
| “Hệ thống phải bảo mật tốt” | Không xác định hành vi hay bằng chứng | Nêu đối tượng, điều kiện, hành vi và tiêu chí đạt |
| “Dùng JWT và mã hóa” | Danh sách công nghệ chưa gắn với hậu quả cần ngăn | Bắt đầu từ kết quả bảo vệ, rồi giải thích vai trò của từng thành phần |
| “Chỉ người có quyền được duyệt” | Chưa định nghĩa quyền theo tenant, kho, người tạo và trạng thái | Lập ma trận quyền và quy tắc trên đối tượng |
| “Có log mọi thao tác” | Không rõ sự kiện, trường, quyền truy cập hoặc xử lý khi ghi lỗi | Đặc tả sự kiện cần thiết, độ bền, phân quyền và giới hạn dữ liệu |
| “Có backup nên đã đáp ứng phục hồi” | Chưa chứng minh bản sao dùng được và nghiệp vụ hoạt động lại | Kiểm chứng bằng diễn tập theo RPO/RTO và kịch bản đã thống nhất |
| Chỉ kiểm tra UI | API hoặc tiến trình nền có thể vượt quy tắc | Bao phủ mọi đường gây cùng tác động nghiệp vụ |
| Chỉ kiểm tra phản hồi từ chối | Có thể bỏ sót tác dụng phụ đã xảy ra | Kiểm tra dữ liệu, thông điệp và sự kiện liên quan |
| Đánh dấu hết rủi ro sau khi viết yêu cầu | Nhầm đặc tả với kiểm soát có hiệu lực | Theo dõi riêng viết, triển khai, kiểm chứng và chấp nhận rủi ro còn lại |

## 11. Bài tập vận dụng

Một cổng chăm sóc khách hàng cho phép nhân viên xuất danh sách yêu cầu hỗ trợ thành tệp. Dữ liệu của nhiều doanh nghiệp được lưu chung hệ thống. Một tài khoản nhân viên có thể chọn tenant trên giao diện, còn tác vụ xuất tệp chạy bất đồng bộ bằng tài khoản dịch vụ.

Thông tin ban đầu:

- Doanh nghiệp muốn tránh việc một khách hàng nhận được yêu cầu hỗ trợ của khách hàng khác.
- Tệp kết quả được tải xuống bằng một liên kết do hệ thống cung cấp.
- Nhóm hiện chỉ kiểm tra quyền khi người dùng bấm nút xuất.

Hãy thực hiện lần lượt:

1. Viết một kịch bản rủi ro có điều kiện, hành vi và hậu quả kinh doanh.
2. Chỉ ra các ranh giới cần xem xét: lúc tạo tác vụ, lúc tác vụ đọc dữ liệu và lúc tải tệp.
3. Viết ít nhất ba yêu cầu đo được, bao phủ phạm vi dữ liệu, quyền tải kết quả và audit.
4. Đề xuất kiểm thử bằng hai tenant, bao gồm trường hợp người dùng bị thu hồi quyền trước khi tải tệp.
5. Nêu một rủi ro còn lại và người cần quyết định cách xử lý.

**Gợi ý tự đối chiếu:** tác vụ nền phải giữ được ngữ cảnh quyền có thẩm quyền và không nhận tenant tùy ý từ client; tệp phải chỉ chứa dữ liệu đúng phạm vi; quyền truy cập kết quả phải được kiểm tra tại thời điểm theo chính sách đã thống nhất. Nếu chính sách yêu cầu việc thu hồi quyền có hiệu lực trước khi tải, phải kiểm chứng cả cơ chế tải trực tiếp và mọi liên kết đã phát hành. Chỉ kiểm tra quyền ở lúc tạo tác vụ sẽ không đủ để chứng minh điều kiện đó.

Không cần chọn ngay một sản phẩm quản lý danh tính, một loại token hay một nền tảng lưu trữ. Trước hết phải đặc tả kết quả cần bảo vệ, xác định thời điểm quyết định quyền và cách quan sát bằng chứng. Khi những điều này rõ ràng, lựa chọn kiến trúc mới có cơ sở để đánh giá.

## 12. Checklist trước khi bàn giao yêu cầu

- [ ] Yêu cầu có nguồn rủi ro, mục tiêu nghiệp vụ hoặc ràng buộc được xác định rõ.
- [ ] Kịch bản rủi ro nêu được sự kiện, điều kiện, tài sản và hậu quả.
- [ ] Phạm vi bao phủ các giao diện, API, tác vụ và tích hợp liên quan.
- [ ] Chủ thể, đối tượng, điều kiện và hành vi bắt buộc không mơ hồ.
- [ ] Ngưỡng định lượng có đơn vị, điểm bắt đầu/kết thúc đo và người xác nhận.
- [ ] Hành vi khi bị từ chối, thiếu dữ liệu kiểm tra hoặc lỗi phụ thuộc đã được nêu.
- [ ] Ngoại lệ có phạm vi, thẩm quyền, thời hạn và cách theo dõi.
- [ ] Có tiêu chí cho luồng hợp lệ, luồng bị cấm, ranh giới và tác dụng phụ.
- [ ] Mỗi yêu cầu liên kết được tới điểm thực thi dự kiến và bằng chứng chấp nhận.
- [ ] Rủi ro còn lại có người chịu trách nhiệm và điều kiện đánh giá lại.

Một yêu cầu bảo mật tốt cho phép chủ nghiệp vụ nhận ra điều gì đang được bảo vệ, nhóm phát triển biết hành vi phải xây, nhóm kiểm thử biết bằng chứng phải thu thập và người chấp nhận rủi ro hiểu giới hạn còn tồn tại. Đó là cơ sở để đưa mục tiêu an toàn thông tin vào các quyết định cụ thể trong thiết kế, phát triển và vận hành.
