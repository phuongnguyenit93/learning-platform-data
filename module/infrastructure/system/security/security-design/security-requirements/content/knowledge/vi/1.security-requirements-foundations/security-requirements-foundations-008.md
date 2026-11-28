# Tính bảo mật, toàn vẹn và sẵn sàng

## 1. Bộ ba CIA là gì và dùng để làm gì?

**Confidentiality, Integrity, Availability**, thường viết tắt là **CIA**, là ba mục tiêu nền tảng khi bảo vệ thông tin và hệ thống xử lý thông tin:

| Thành phần | Cách gọi trong bài | Câu hỏi trọng tâm |
|---|---|---|
| Confidentiality | Tính bảo mật, hay tính bí mật | Thông tin có chỉ được tiết lộ cho các chủ thể được phép không? |
| Integrity | Tính toàn vẹn | Dữ liệu và trạng thái có được bảo vệ trước thay đổi hoặc phá hủy trái phép, đồng thời tuân theo quy tắc đã đặt ra không? |
| Availability | Tính sẵn sàng | Chủ thể được phép có truy cập và sử dụng được thông tin, chức năng cần thiết đúng lúc không? |

Trong tên bài, “tính bảo mật” được dùng theo nghĩa **confidentiality**. Còn **bảo mật hệ thống** theo nghĩa rộng bao gồm cả ba mục tiêu trên cùng các khía cạnh liên quan như xác thực, trách nhiệm giải trình và khả năng phát hiện sự cố. Cần phân biệt hai cách dùng để tránh hiểu rằng chỉ giữ kín dữ liệu là đủ.

CIA là khung đặt câu hỏi, không phải danh sách công nghệ. Mã hóa, phân quyền, kiểm tra dữ liệu, logging và sao lưu là những cơ chế có thể phục vụ các mục tiêu này. Một cơ chế xuất hiện trong kiến trúc chưa chứng minh mục tiêu đã được đáp ứng.

Ví dụ, một hệ thống mã hóa cơ sở dữ liệu vẫn có thể trả hồ sơ của người khác qua API. Một bản sao lưu còn nguyên tệp vẫn có thể chứa điểm số đã bị sửa trái phép từ trước. Một máy chủ trả HTTP 200 vẫn có thể không cho người học nộp bài thành công.

Khi đặc tả yêu cầu, cần chuyển từng mục tiêu CIA thành phát biểu có **tài sản, chủ thể, hành động, điều kiện, phản ứng và bằng chứng kiểm chứng**. Chính bước chuyển này nối mục tiêu an toàn thông tin với mô hình đe dọa, thiết kế kiến trúc và kiểm thử.

## 2. Bối cảnh xuyên suốt: nền tảng đào tạo cho doanh nghiệp

Giả sử một nền tảng đào tạo phục vụ nhiều tổ chức. Mỗi tổ chức là một **tenant**, tức một phạm vi khách hàng có thành viên, khóa học và dữ liệu riêng. Người học tham gia khóa học, làm bài đánh giá và xem kết quả. Giảng viên chấm điểm trong các lớp được phân công. Quản trị viên tổ chức quản lý thành viên; quyền quản trị tổ chức không mặc nhiên bao gồm quyền sửa mọi điểm số.

Các tài sản cần bảo vệ gồm:

| Tài sản hoặc luồng nghiệp vụ | Yêu cầu về tính bảo mật | Yêu cầu về tính toàn vẹn | Yêu cầu về tính sẵn sàng |
|---|---|---|---|
| Hồ sơ người học | Chỉ chủ thể có quyền được đọc các trường trong phạm vi cho phép. | Thông tin được cập nhật bởi đúng người, theo quy tắc xác nhận và kiểm tra dữ liệu. | Người dùng hợp lệ truy cập được khi cần cho học tập và quản lý. |
| Đề, đáp án và bài làm | Đáp án chưa công bố không bị lộ; bài làm chỉ được người có quyền xem. | Bài đã tiếp nhận không bị thay thế, xóa hoặc gắn sang người học khác trái phép. | Luồng nộp bài hoạt động trong thời gian đánh giá đã cam kết. |
| Điểm số và lịch sử chấm | Kết quả cá nhân không bị tiết lộ ngoài phạm vi được phép. | Chỉ người được phân công có thể ghi điểm; thay đổi phải đúng quy tắc và có dấu vết. | Người học và giảng viên tra cứu được theo lịch công bố. |
| Tệp xuất kết quả | Chỉ người có quyền xuất và tải được tệp trong phạm vi được cấp. | Nội dung tệp khớp với dữ liệu và thời điểm xuất đã xác định. | Tệp được tạo và tải trong điều kiện dịch vụ đã cam kết. |
| Nhật ký và bản sao lưu | Không tạo đường đọc dữ liệu nhạy cảm ngoài kiểm soát. | Không bị sửa hoặc thay thế trái phép; có cơ sở kiểm tra nguồn và trạng thái. | Có thể dùng để điều tra hoặc phục hồi khi xảy ra sự cố. |

Không phải tài sản nào cũng có cùng mức ưu tiên. Với một bài thi có hạn chót, sẵn sàng và toàn vẹn của việc nộp bài rất quan trọng. Với đáp án chưa công bố, nguy cơ tiết lộ có thể là rủi ro nổi bật. Không nên tự gán mọi tài sản mức “cao” cho cả ba mục tiêu mà không phân tích tác động.

Ranh giới tin cậy cũng cần rõ: trình duyệt, tham số request và tệp do người dùng tải lên không phải nguồn đáng tin để xác định người sở hữu dữ liệu hoặc quyền chấm điểm. Tác vụ nền, API xuất tệp, kho log và môi trường phục hồi đều thuộc phạm vi cần xem xét, không chỉ màn hình chính.

## 3. Tính bảo mật: kiểm soát việc tiết lộ thông tin

### 3.1. Bí mật đối với ai, dữ liệu nào, trong hoàn cảnh nào?

Thông tin không cần được giấu với tất cả mọi người để đạt confidentiality. Giảng viên có thể cần đọc bài làm của lớp mình, trong khi một người học khác không được đọc. Vì vậy, yêu cầu phải xác định quan hệ giữa **chủ thể, dữ liệu, hành động và ngữ cảnh**.

Một chính sách đọc kết quả có thể quy định:

- Người học chỉ xem được kết quả của chính mình sau thời điểm công bố.
- Giảng viên xem được kết quả thuộc lớp đang được phân công phụ trách.
- Người quản lý tổ chức được xem báo cáo theo quyền được cấp; quyền xem báo cáo tổng hợp không tự tạo quyền xem mọi dữ liệu cá nhân.
- Nhân sự hỗ trợ chỉ truy cập dữ liệu theo quy trình cấp quyền hỗ trợ có phạm vi, thời hạn và ghi nhận rõ ràng.

**Xác thực** trả lời chủ thể là ai theo cơ chế tin cậy đã chọn. **Phân quyền** quyết định chủ thể đó có được thực hiện hành động trên tài nguyên cụ thể hay không. Đăng nhập thành công không đồng nghĩa được đọc mọi dữ liệu.

Ngay cả việc công bố dữ liệu tổng hợp cũng cần xem xét khả năng suy ra thông tin cá nhân, chẳng hạn báo cáo chỉ có một người trong nhóm. Việc bỏ tên khỏi một báo cáo không tự động chứng minh rằng dữ liệu đã không còn khả năng nhận diện.

### 3.2. Xem xét toàn bộ vòng đời và các bản sao dữ liệu

Yêu cầu tính bảo mật cần bao phủ các nơi dữ liệu đi qua:

```text
Thu thập -> Truyền -> Xử lý -> Lưu trữ -> Xuất/chia sẻ -> Lưu giữ/xóa
                          |          |
                          v          v
                      Cache/log    Bản sao lưu
```

Một API được phân quyền tốt vẫn có thể bị vô hiệu hóa bởi tệp xuất công khai. Một giao diện che thông tin vẫn có thể gửi đầy đủ dữ liệu về trình duyệt. Một thông báo lỗi hoặc số lượng kết quả tìm kiếm cũng có thể tiết lộ thông tin thuộc phạm vi được bảo vệ.

Các biện pháp liên quan thường gồm phân loại dữ liệu, tối thiểu hóa dữ liệu, kiểm tra quyền ở máy chủ, bảo vệ đường truyền và nơi lưu, quản lý khóa, kiểm soát tệp xuất và giới hạn dữ liệu trong log. Thời hạn lưu và quy trình xóa cũng cần xác định phạm vi bản chính, bản sao và bản sao lưu; không hứa “xóa khỏi mọi nơi ngay lập tức” khi thiết kế thực tế không đáp ứng được.

Mã hóa bảo vệ dữ liệu trong những điều kiện nhất định. Nó không ngăn một dịch vụ có quyền giải mã trả dữ liệu cho sai người. Quản lý khóa và quyền sử dụng khóa vì vậy là một phần của yêu cầu, thay vì chỉ ghi “dữ liệu được mã hóa”.

### 3.3. Ví dụ yêu cầu và tiêu chí chấp nhận

**C-01 — Không tiết lộ kết quả học tập ngoài phạm vi được phép**

> Với mọi yêu cầu đọc kết quả cá nhân qua API chi tiết, danh sách, tìm kiếm, xuất và tải tệp, hệ thống phải kiểm tra danh tính đã xác minh, phạm vi tenant, quyền đối với người học hoặc lớp và trạng thái công bố. Khi không đáp ứng điều kiện, hệ thống không trả nội dung hay metadata kết quả được bảo vệ và không tạo tệp xuất chứa dữ liệu đó. Không dùng riêng mã người học hoặc `tenantId` do client gửi làm căn cứ cho phép truy cập.

Tiêu chí chấp nhận cho hệ thống giả định gồm:

1. Người học A không nhận được kết quả của người học B khi thay mã đối tượng, kể cả khi cả hai cùng tenant.
2. Thành viên tenant A không nhận được kết quả thuộc tenant B trên các đường truy cập thuộc phạm vi, với cache được bật và tắt.
3. Người có quyền đọc kết quả vẫn không nhận được kết quả chưa công bố nếu chính sách chỉ cho xem sau công bố.
4. Người có quyền hợp lệ nhận được đúng dữ liệu được phép, tránh cách triển khai từ chối tất cả.
5. Tệp xuất và đường tải tệp tuân theo cùng phạm vi quyền; phản hồi lỗi và log không chứa dữ liệu bị cấm theo hợp đồng đã định nghĩa.

Các mã yêu cầu trong bài chỉ dùng cho ví dụ. Trong dự án thực tế, cần quản lý phiên bản, người chịu trách nhiệm và liên kết bằng chứng tương ứng.

## 4. Tính toàn vẹn: bảo vệ dữ liệu và trạng thái trước thay đổi sai phép

### 4.1. Toàn vẹn không có nghĩa dữ liệu không bao giờ được thay đổi

Một giảng viên có thể cần sửa điểm sau khi giải quyết phúc khảo. Dữ liệu thay đổi nhưng vẫn có thể toàn vẹn nếu đúng người thực hiện, đúng điều kiện, đúng phạm vi và có lịch sử theo chính sách.

Ngược lại, dữ liệu có định dạng hợp lệ vẫn có thể bị thay đổi trái phép. Điểm 8 nằm trong khoảng từ 0 đến 10, nhưng nếu người học tự sửa điểm của mình thành 8 thì việc kiểm tra kiểu dữ liệu và khoảng giá trị không đủ bảo vệ tính toàn vẹn.

Khi đặc tả, cần tách các câu hỏi:

| Câu hỏi | Ví dụ kiểm soát cần xem xét |
|---|---|
| Ai được thay đổi? | Phân quyền giảng viên theo lớp, vai trò và loại thao tác. |
| Được thay đổi dữ liệu nào? | Không cho phép client gán lại chủ sở hữu bài làm hoặc tenant. |
| Khi nào được thay đổi? | Sửa điểm sau khóa sổ chỉ theo quy trình mở lại được phép. |
| Trạng thái nào được chuyển sang trạng thái nào? | Bài nộp chỉ được công nhận sau khi nội dung đã được lưu theo cam kết tiếp nhận. |
| Điều gì xảy ra khi có hai thay đổi đồng thời? | Phát hiện phiên bản cũ, tránh âm thầm ghi đè thay đổi mới. |
| Chứng minh thay đổi bằng gì? | Lưu chủ thể, phiên bản, thời điểm và lý do theo chính sách kiểm toán. |

Tính toàn vẹn thường liên quan cả dữ liệu đơn lẻ lẫn quan hệ giữa các dữ liệu. Một bản ghi điểm đúng định dạng nhưng gắn nhầm bài làm hoặc nhầm người học vẫn sai. Một thông báo “đã nộp bài” được trả trước khi lưu bền vững có thể làm trạng thái nghiệp vụ mâu thuẫn với dữ liệu thực.

### 4.2. Bảo vệ trước lỗi thao tác, cạnh tranh và lạm dụng

Các mối đe dọa toàn vẹn không chỉ đến từ người cố ý tấn công. Chúng còn gồm nhập liệu nhầm, tệp import sai phạm vi, request được gửi lại, xử lý đồng thời và lỗi trong tác vụ nền.

Ví dụ hai giảng viên cùng mở phiên bản 17 của một bản ghi điểm. Người thứ nhất lưu phiên bản 18. Nếu người thứ hai vẫn lưu dữ liệu dựa trên phiên bản 17 và hệ thống âm thầm ghi đè, thay đổi thứ nhất có thể bị mất.

Một hành vi cần đặc tả là:

```text
Yêu cầu sửa điểm mang phiên bản dự kiến 17
    -> kiểm tra quyền và quy tắc nghiệp vụ
    -> chỉ cập nhật nếu phiên bản hiện tại vẫn là 17
    -> nếu đã là 18: báo xung đột, không ghi đè
```

Kiểm tra phiên bản và cập nhật phải tạo thành thao tác có tính nguyên tử phù hợp, để hai request không cùng vượt qua một bước kiểm tra rời rạc. Yêu cầu nên nêu kết quả mong muốn; thiết kế lựa chọn cơ chế giao dịch, khóa hoặc kiểm soát đồng thời phù hợp.

Với nộp bài, gửi lại request sau khi mất kết nối cũng cần quy tắc. Nếu hệ thống hỗ trợ khóa chống xử lý lặp, cùng một khóa và cùng nội dung trong phạm vi đã định phải trả về cùng kết quả tiếp nhận; cùng khóa nhưng khác nội dung phải được xử lý theo hợp đồng xung đột. Cần ghi rõ khóa gắn với người nào, bài nào và được giữ bao lâu.

### 4.3. Hash, xác thực nguồn và nhật ký có vai trò khác nhau

Một giá trị hash có thể giúp phát hiện dữ liệu khác với bản tham chiếu **nếu bản tham chiếu được bảo vệ hoặc lấy từ nguồn đáng tin**. Nếu kẻ sửa tệp cũng sửa được hash lưu bên cạnh, việc tính lại và thấy khớp không chứng minh tệp là bản hợp lệ.

Tùy mô hình đe dọa, thiết kế có thể cần cơ chế xác thực tính toàn vẹn và nguồn như MAC hoặc chữ ký số, cùng quản lý khóa và điểm xác minh phù hợp. Các cơ chế này không tự chứng minh nội dung đúng nghiệp vụ hoặc người ký đã được phép thực hiện mọi hành động.

Nhật ký kiểm toán hỗ trợ phát hiện và điều tra thay đổi; nó không thay thế kiểm tra quyền trước khi sửa dữ liệu. Bản thân nhật ký cũng cần được bảo vệ trước truy cập, sửa, xóa trái phép và mất dữ liệu. Không nên gọi mọi tệp log là “bất biến” khi chưa xác định cơ chế và giới hạn bảo vệ.

### 4.4. Ví dụ yêu cầu và tiêu chí chấp nhận

**I-01 — Sửa điểm đúng quyền và không làm mất thay đổi đồng thời**

> Chỉ giảng viên còn được phân công chấm lớp tương ứng mới được sửa điểm trong giai đoạn cho phép. Mỗi cập nhật phải kiểm tra quy tắc điểm, phiên bản dự kiến và phạm vi tenant. Cập nhật dựa trên phiên bản cũ phải bị từ chối mà không thay đổi điểm. Mỗi cập nhật thành công phải gắn với bản ghi kiểm toán chứa chủ thể, đối tượng, giá trị trước/sau, thời điểm và lý do theo chính sách dữ liệu đã phê duyệt.

Yêu cầu về giá trị trước/sau chỉ áp dụng cho nhật ký kiểm toán điểm được kiểm soát riêng trong ví dụ, không phải cho log ứng dụng chung. Cần xác định quyền đọc và thời hạn lưu vì điểm số là dữ liệu cá nhân trong bối cảnh này.

Tiêu chí chấp nhận gồm kiểm thử người không có quyền, người sai lớp, giai đoạn bị khóa, dữ liệu vượt quy tắc và hai cập nhật đồng thời. Với hai request cùng phiên bản dự kiến, nhiều nhất một thay đổi được ghi thành công theo chính sách đã chọn; request còn lại nhận kết quả xung đột và có thể tải lại dữ liệu.

Phải kiểm tra cả quan hệ giữa dữ liệu và dấu vết. Nếu hệ thống đã ghi nhận thay đổi điểm thành công nhưng không có đường bảo đảm phát sinh bản ghi kiểm toán tương ứng, yêu cầu chưa được đáp ứng. Thiết kế cần nêu cách xử lý khi thành phần ghi hoặc chuyển nhật ký bị lỗi, chẳng hạn lưu sự kiện bền vững cùng giao dịch rồi chuyển tiếp theo cam kết. Không mặc định mọi hệ thống phải dùng cùng một cơ chế.

## 5. Tính sẵn sàng: dùng được đúng lúc bởi chủ thể hợp lệ

### 5.1. Dịch vụ đang chạy chưa đủ để gọi là sẵn sàng

Sẵn sàng phải gắn với hành trình nghiệp vụ. Máy chủ còn phản hồi nhưng không đọc được đề, không lưu được bài nộp hoặc luôn trả lỗi từ phụ thuộc thì chức năng liên quan chưa sẵn sàng cho người dùng.

Cần xác định:

- Chức năng nào cần dùng: xem khóa học, tải đề, nộp bài hay chấm điểm.
- Ai là người dùng hợp lệ và yêu cầu đầu vào nào đủ điều kiện phục vụ.
- Khi nào cần dùng: liên tục, trong giờ làm việc hay trong một đợt đánh giá.
- Tải, dung lượng và phụ thuộc nào thuộc phạm vi cam kết.
- Kết quả nào được tính là thành công và trong giới hạn thời gian nào.

Việc chặn một yêu cầu trái phép là hành vi bảo vệ, không phải lỗi sẵn sàng của chức năng được bảo vệ. Tuy nhiên, nếu người dùng hợp lệ bị chặn do cấu hình sai, lỗi xác thực hoặc giới hạn lưu lượng không phù hợp thì tác động đó phải được phản ánh trong cách đánh giá dịch vụ. Không được tùy ý loại bỏ các lần thất bại chỉ để số liệu đẹp hơn.

### 5.2. Những mối đe dọa thường gặp

Mất sẵn sàng có thể do lạm dụng hoặc do sự cố thông thường: lưu lượng đột biến, truy vấn quá tốn tài nguyên, hàng đợi đầy, hết dung lượng lưu trữ, lỗi triển khai, mất kết nối tới dịch vụ định danh hoặc một tenant chiếm phần lớn tài nguyên dùng chung.

Các biện pháp như giới hạn lưu lượng, hạn mức tài nguyên, phân vùng tải, thời gian chờ, dự phòng và phục hồi cần xuất phát từ kịch bản cụ thể. Chẳng hạn:

- Giới hạn theo tenant để một tổ chức không làm cạn tài nguyên của tổ chức khác.
- Đặt ngân sách xử lý cho xuất báo cáo để bảo vệ tài nguyên dành cho nộp bài.
- Kiểm soát retry để một lỗi phụ thuộc không gây ra làn sóng gọi lại không giới hạn.
- Có quan sát và cảnh báo khi dung lượng, độ trễ hoặc tỷ lệ lỗi tiến gần giới hạn.

Không có một ngưỡng giới hạn lưu lượng mặc định phù hợp cho mọi hệ thống. Ngưỡng phải tính đến nhu cầu hợp lệ, hành vi phân phối tải, cách nhận diện chủ thể và phản ứng khi vượt hạn mức. Chỉ giới hạn theo địa chỉ IP có thể ảnh hưởng nhiều người dùng chung một mạng.

### 5.3. Đo sẵn sàng theo kết quả có ý nghĩa

Một chỉ số minh họa là:

```text
Tỷ lệ thành công đúng hạn =
    Số yêu cầu hợp lệ đạt kết quả nghiệp vụ trong thời hạn
    ---------------------------------------------------
                  Tổng số yêu cầu hợp lệ
```

Với 100.000 yêu cầu đủ điều kiện, nếu 99.900 yêu cầu hoàn tất đúng hạn thì tỷ lệ là 99,9%. Công thức chỉ có ý nghĩa khi định nghĩa được “đủ điều kiện”, “hoàn tất”, thời hạn, cửa sổ đo và điểm quan sát.

Ví dụ nộp bài phải được coi là thành công khi có nội dung bài được lưu theo cam kết bền vững và có mã xác nhận tương ứng, không chỉ khi API trả mã HTTP 2xx. Phản hồi thành công giả có thể làm chỉ số kỹ thuật trông tốt nhưng đồng thời vi phạm toàn vẹn và sẵn sàng của nghiệp vụ.

**SLI** là chỉ số quan sát mức dịch vụ; **SLO** là mục tiêu đặt cho chỉ số đó. Tỷ lệ gộp cả tháng có thể che khuất một đợt đánh giá bị lỗi nặng. Vì vậy, cần xem xét thêm cửa sổ quan trọng, chức năng và nhóm tenant khi rủi ro yêu cầu.

### 5.4. Ví dụ yêu cầu và tiêu chí chấp nhận

**A-01 — Tiếp nhận bài nộp trong đợt đánh giá**

> Trong mỗi đợt đánh giá dài 60 phút của hệ thống giả định, với tối đa 2.000 người dùng hoạt động đồng thời, lưu lượng tối đa 100 yêu cầu nộp bài mỗi giây và nội dung mỗi yêu cầu không vượt 256 KiB, ít nhất 99,9% yêu cầu nộp bài hợp lệ phải được tiếp nhận bền vững và trả mã xác nhận trong 5 giây. Phân vị p95 của thời gian hoàn tất các yêu cầu thành công không vượt 2 giây trong cùng cửa sổ đo.

Tất cả con số trong yêu cầu này là **giả định để học cách đặc tả**, không phải khuyến nghị mặc định cho một sản phẩm thực tế. “Tiếp nhận bền vững” cần được dự án định nghĩa theo loại sự cố phải chịu được; việc chỉ ghi vào bộ nhớ tiến trình không đáp ứng một cam kết phải giữ bài khi tiến trình bị dừng.

Hợp đồng đo cho ví dụ cần ghi thêm:

- Yêu cầu hợp lệ là yêu cầu có chủ thể đủ quyền, nội dung đúng cấu trúc, chưa quá hạn và thuộc đợt đánh giá đang mở. Quy tắc với request gửi lại phải phù hợp chính sách chống xử lý lặp.
- Thời gian đo bắt đầu khi cổng dịch vụ nhận đủ request, gồm thời gian xác thực, phân quyền, xử lý và lưu bài, kết thúc khi cổng gửi xong phản hồi xác nhận. Thời gian truyền trên mạng của người dùng nằm ngoài phép đo này và cần chỉ số riêng nếu sản phẩm cam kết trải nghiệm từ thiết bị.
- Lỗi phụ thuộc nội bộ hoặc lỗi kiểm tra danh tính khiến một yêu cầu vốn hợp lệ không được xử lý phải được ghi nhận theo quy tắc đo đã thống nhất; không tự biến chúng thành đầu vào không hợp lệ để loại khỏi mẫu.
- Kiểm thử tải cần định nghĩa cách phân bố tenant, nhịp tăng tải, trạng thái cache, kích thước dữ liệu và tải nền như xuất báo cáo.
- Cần đo tỷ lệ thành công đúng hạn và độ trễ cùng nhau. p95 tốt trên số ít request thành công không bù được việc phần lớn request thất bại.

### 5.5. Sao lưu, độ bền và phục hồi có quan hệ nhưng không đồng nhất

Sẵn sàng liên quan khả năng phục hồi nhưng không đồng nghĩa chỉ cần có bản sao lưu. Một tệp sao lưu có thể hỏng, thiếu khóa giải mã, không tương thích phiên bản hoặc chứa trạng thái đã bị sửa sai. Cần diễn tập để kiểm tra thực sự khôi phục được dịch vụ và các tính chất bảo vệ.

Hai mục tiêu hay dùng là:

| Khái niệm | Ý nghĩa | Điều phải định nghĩa khi viết yêu cầu |
|---|---|---|
| RTO — Recovery Time Objective | Mục tiêu về thời gian phục hồi sau gián đoạn. | Bắt đầu tính từ mốc nào, kết thúc khi chức năng nào dùng được, loại sự cố và phạm vi nào áp dụng. |
| RPO — Recovery Point Objective | Mục tiêu về khoảng mất dữ liệu tối đa tính theo thời gian. | Dữ liệu nào có thể mất, so với mốc nào, loại sự cố và cách chứng minh điểm phục hồi. |

Ví dụ RTO 30 phút và RPO 5 phút có nghĩa khác nhau: một giá trị nói về thời gian trở lại phục vụ, giá trị kia nói về khoảng dữ liệu có thể không phục hồi được. Đây là ví dụ độc lập để phân biệt khái niệm, không mặc nhiên là mức chấp nhận cho bài nộp đã xác nhận.

Nếu nghiệp vụ yêu cầu không mất bài đã được xác nhận trong một kịch bản lỗi cụ thể, yêu cầu về độ bền phải ghi rõ điều đó và kiến trúc phải đáp ứng. Không thể dùng một mục tiêu RPO cho phép mất 5 phút dữ liệu để khẳng định đồng thời rằng mọi bài đã xác nhận đều an toàn trong cùng phạm vi sự cố.

Phục hồi cũng phải bảo toàn phân quyền. Khôi phục bản sao cũ có thể đưa trở lại quyền giảng viên đã bị thu hồi hoặc tài khoản đã bị khóa. Quy trình phải xử lý trạng thái quyền và phiên theo chính sách hiện hành trước khi mở lại quyền truy cập nhạy cảm. Thời gian xử lý này phải được tính theo định nghĩa hoàn tất phục hồi đã công bố.

## 6. Ba mục tiêu tương tác và có thể xung đột

CIA không phải ba cột độc lập. Một sự cố hoặc quyết định thiết kế có thể ảnh hưởng nhiều mục tiêu cùng lúc.

| Tình huống | Tác động CIA | Quyết định cần làm rõ |
|---|---|---|
| API trả nhầm kết quả cho người khác | Vi phạm tính bảo mật; có thể dẫn đến sửa trái phép nếu dùng chung lỗi phân quyền. | Phạm vi kiểm tra chủ thể, tenant, tài nguyên và hành động trên từng đường xử lý. |
| Dữ liệu điểm bị xóa trái phép | Mất toàn vẹn và có thể làm chức năng tra cứu không còn sẵn sàng. | Quyền xóa, phát hiện thay đổi, khả năng phục hồi và kiểm tra sau phục hồi. |
| Lưu lượng xuất báo cáo làm nộp bài bị treo | Mất sẵn sàng của một hành trình dù toàn hệ thống còn phản hồi. | Hạn mức và mức ưu tiên tài nguyên giữa các loại công việc. |
| Log ghi toàn bộ bài làm để điều tra | Có thể tăng khả năng điều tra nhưng tạo thêm nguy cơ tiết lộ. | Dữ liệu tối thiểu cần ghi, quyền đọc, thời hạn lưu và cách che dữ liệu. |
| Dịch vụ phân quyền lỗi | Nguy cơ mất sẵn sàng; cho qua mặc định lại đe dọa bảo mật và toàn vẹn. | Chính sách khi chưa xác lập được quyền, cơ chế dự phòng và giới hạn dùng quyền đã cache. |
| Mất khóa giải mã bản sao lưu | Dữ liệu có thể vẫn bí mật nhưng không phục hồi được. | Quản lý vòng đời khóa, phân quyền và diễn tập phục hồi khóa cùng dữ liệu. |

### 6.1. Không tự động bỏ kiểm soát để tăng sẵn sàng

Khi dịch vụ quyền không phản hồi, “cho mọi request đi qua để người dùng tiếp tục làm việc” có thể biến sự cố sẵn sàng thành sự cố tiết lộ hoặc sửa dữ liệu trái phép. Với đọc kết quả và sửa điểm, cần quy định không thực hiện hành động khi không có căn cứ hợp lệ để cho phép.

Một hệ thống có thể dùng trạng thái quyền đã cache nếu thiết kế và yêu cầu cho phép. Khi đó phải ghi rõ phạm vi hành động, tuổi tối đa của dữ liệu quyền, độ trễ thu hồi và tình huống vô hiệu hóa. Đây là một quyết định rủi ro cần được chấp nhận rõ ràng, không phải ngoại lệ ngầm trong mã xử lý lỗi.

### 6.2. Không tối ưu một mục tiêu bằng cách làm mất ý nghĩa nghiệp vụ

Từ chối mọi người có thể ngăn lộ dữ liệu nhưng không đáp ứng sẵn sàng. Cho phép mọi người sửa điểm có thể làm thao tác ít bị chặn nhưng mất toàn vẹn. Lưu mọi dữ liệu mãi mãi có thể thuận tiện điều tra nhưng tăng phạm vi tiết lộ và gánh nặng quản lý dữ liệu.

Giải pháp cần bảo vệ hành động hợp lệ trong các điều kiện đã thỏa thuận. Khi có xung đột, hãy ghi tác động, lựa chọn, người chịu trách nhiệm và bằng chứng cần thu. Nếu chưa giải quyết được xung đột giữa hai yêu cầu, phải làm rõ hoặc điều chỉnh yêu cầu có căn cứ trước khi coi thiết kế là đáp ứng.

## 7. Chuyển CIA thành yêu cầu bảo mật có thể kiểm chứng

### 7.1. Quy trình từ tài sản đến bằng chứng

Một quy trình thực hành gồm sáu bước:

1. **Chọn tài sản hoặc hành trình.** Ví dụ nộp bài, sửa điểm hay tải báo cáo.
2. **Mô tả tác động khi mất từng mục tiêu CIA.** Ai bị ảnh hưởng, ảnh hưởng đến hoạt động nào và có thể kéo dài bao lâu?
3. **Xác định đe dọa và ranh giới tin cậy.** Ai có thể tác động, qua đường nào, với quyền và giả định nào?
4. **Viết phản ứng phải có.** Cho phép, từ chối, phát hiện, ghi nhận, giới hạn hay phục hồi trong điều kiện cụ thể.
5. **Đặt tiêu chí chấp nhận.** Kết quả quan sát được, ngưỡng, môi trường, dữ liệu và phạm vi kiểm thử.
6. **Nối với kiến trúc và bằng chứng.** Điểm thực thi, cấu hình, kiểm thử, diễn tập và người chịu trách nhiệm.

Một mẫu phát biểu ngắn có thể dùng là:

```text
[Mã yêu cầu]
Với [tài sản/hành động], khi [chủ thể hoặc sự kiện] xảy ra
trong [điều kiện và phạm vi], hệ thống phải [phản ứng].
Chấp nhận khi [kết quả và thước đo] được xác minh bằng [bằng chứng].
Giả định/ngoại lệ: [...]
Chủ sở hữu: [...]
```

Không phải mọi yêu cầu đều cần số phần trăm. “Không thay đổi điểm khi kiểm tra quyền thất bại” là một tính chất kiểm chứng được. Ngược lại, “sửa điểm phải an toàn 100%” chưa nêu điều gì có thể quan sát hoặc kiểm tra.

### 7.2. Ma trận truy vết minh họa

| Rủi ro | Mục tiêu chính | Yêu cầu | Điểm kiến trúc liên quan | Bằng chứng |
|---|---|---|---|---|
| R-01: xem kết quả của người khác | Bảo mật | C-01 | Kiểm tra quyền ở máy chủ, truy vấn giới hạn phạm vi, cache và đường tải tệp | Kiểm thử trực tiếp API, xuất và tải tệp bằng chủ thể được phép/không được phép |
| R-02: sửa điểm sai quyền hoặc ghi đè mất thay đổi | Toàn vẹn | I-01 | Chính sách chấm điểm, cập nhật có kiểm soát phiên bản, đường phát sinh kiểm toán | Kiểm thử quyền, quy tắc và cập nhật đồng thời; đối chiếu dấu vết |
| R-03: tải tăng làm không tiếp nhận được bài | Sẵn sàng | A-01 | Phân bổ tài nguyên, giới hạn lưu lượng, lưu bài và phụ thuộc định danh | Kiểm thử tải theo hợp đồng đo; xác minh dữ liệu lưu và mã xác nhận |
| R-04: khôi phục dữ liệu nhưng đưa quyền cũ trở lại | Cả ba | Yêu cầu phục hồi riêng cần được đặc tả | Sao lưu, quản lý khóa, phục hồi dữ liệu và đối chiếu trạng thái quyền | Diễn tập có kiểm tra dữ liệu, quyền và thời gian trước khi mở dịch vụ |

Dòng cuối cố ý cho thấy một rủi ro chưa có yêu cầu đầy đủ. Nhận ra khoảng trống tốt hơn là gán một mã yêu cầu có vẻ hoàn chỉnh nhưng thiếu phạm vi sự cố, mục tiêu phục hồi và tiêu chí kiểm tra. Dự án phải hoàn thiện yêu cầu đó trước khi chấp nhận thiết kế phục hồi.

Các nhóm xác thực, phân quyền, bảo vệ dữ liệu, logging và phục hồi không tương ứng một đối một với CIA. Xác thực có thể bảo vệ cả bí mật lẫn toàn vẹn; logging hỗ trợ phát hiện và điều tra nhưng cũng cần bảo vệ bí mật; phục hồi phải xét cả dữ liệu và quyền. Có thể gắn nhiều mục tiêu cho cùng một yêu cầu nếu quan hệ được giải thích rõ.

## 8. Chọn bằng chứng phù hợp với từng mục tiêu

### 8.1. Kiểm thử cả trường hợp bị cấm và được phép

Với C-01, cần thử chủ thể không có quyền, sai tenant, sai lớp, kết quả chưa công bố, cache hit và đường xuất dữ liệu. Đồng thời phải chứng minh người có quyền lấy được đúng dữ liệu theo phạm vi.

Với I-01, cần kiểm tra không có thay đổi nghiệp vụ khi bị từ chối, không chỉ quan sát mã lỗi. Cần thử dữ liệu biên, chuyển trạng thái sai, gửi lại request và xử lý đồng thời. Nếu cập nhật được phép, điểm, phiên bản và dấu vết phải nhất quán theo cam kết.

Với A-01, cần quan sát cả kết quả tiếp nhận lẫn thời gian và tỷ lệ lỗi. Nên kiểm tra dữ liệu đã lưu sau tải, tác động của tải xuất báo cáo và sự phân bố thất bại giữa các tenant. Thử nghiệm lỗi phải có phạm vi kiểm soát và điều kiện an toàn cho môi trường thực hiện.

### 8.2. Ví dụ ca chấp nhận cho tính toàn vẹn

```text
Cho trước:
  Giảng viên G có quyền sửa điểm của lớp L.
  Bản ghi điểm S thuộc L đang ở phiên bản 17.

Khi:
  Hai yêu cầu cập nhật hợp lệ được gửi với phiên bản dự kiến 17.

Thì:
  Chỉ một yêu cầu được ghi thành công theo chính sách kiểm soát phiên bản.
  Yêu cầu còn lại nhận kết quả xung đột, không ghi đè dữ liệu.
  Điểm lưu tương ứng với yêu cầu thành công.
  Phiên bản và bản ghi kiểm toán khớp với thay đổi đã chấp nhận.
```

Cần có thêm ca không đủ quyền và ca phụ thuộc kiểm toán gặp lỗi theo chính sách đã định. Ca trên chỉ kiểm chứng một khía cạnh của yêu cầu, không đại diện cho toàn bộ mức bảo mật hệ thống.

### 8.3. Giới hạn của kết quả kiểm thử

“Không thấy dữ liệu bị lộ trong bộ kiểm thử” là bằng chứng của phạm vi đã thử, không phải chứng minh mọi khả năng tiết lộ đều không tồn tại. Tương tự, một lần phục hồi thành công không bảo đảm mọi loại thảm họa đều được xử lý.

Kết quả cần gắn với phiên bản phần mềm, cấu hình, dữ liệu, mô hình tải, loại lỗi và các giả định. Nên kết hợp xem xét yêu cầu, thiết kế, kiểm thử, cấu hình và diễn tập tùy bản chất yêu cầu. Kiểm tra có bật mã hóa hoặc có hàm phân quyền không thay thế quan sát kết quả bảo vệ thực tế.

Khi hệ thống thay đổi, cần xem lại bằng chứng liên quan. Thêm API mới có thể mở đường tiết lộ; đổi cơ chế lưu bài có thể thay đổi độ bền; chuyển nơi lưu khóa có thể ảnh hưởng phục hồi. Liên kết truy vết giúp xác định chính xác yêu cầu nào cần được kiểm chứng lại.

## 9. Những nhầm lẫn thường gặp

| Nhận định | Vì sao chưa đúng hoặc chưa đủ? | Cách diễn đạt có ích hơn |
|---|---|---|
| “Bảo mật nghĩa là dữ liệu không bị lộ.” | Chưa xét thay đổi trái phép và khả năng phục vụ người dùng hợp lệ. | Phân tích cả bí mật, toàn vẹn và sẵn sàng theo tài sản. |
| “Đã đăng nhập thì được xem dữ liệu.” | Danh tính không quyết định toàn bộ quyền trên đối tượng. | Kiểm tra quyền theo hành động, tài nguyên, tenant và ngữ cảnh. |
| “Mã hóa giải quyết cả CIA.” | Không tự bảo vệ quyền API, tính đúng nghiệp vụ hoặc khả năng phục hồi. | Chỉ rõ mối đe dọa và điều kiện mà mã hóa bảo vệ, cùng các kiểm soát bổ sung. |
| “Hash khớp nên dữ liệu chắc chắn hợp lệ.” | Bản tham chiếu có thể bị sửa cùng dữ liệu; dữ liệu sai nghiệp vụ cũng có hash. | Xác định nguồn tham chiếu tin cậy và phân biệt xác minh thay đổi với xác minh nghiệp vụ. |
| “HTTP 200 nghĩa là nộp bài thành công.” | Phản hồi có thể không phản ánh trạng thái lưu bền vững. | Định nghĩa thành công theo bài nộp được tiếp nhận và mã xác nhận tương ứng. |
| “Có backup là đủ sẵn sàng.” | Chưa biết phục hồi mất bao lâu, mất gì và quyền sau phục hồi ra sao. | Đặt mục tiêu phục hồi theo sự cố và diễn tập với dữ liệu, khóa, quyền. |
| “SLO tốt thì mọi tenant đều được phục vụ tốt.” | Số liệu gộp có thể che lỗi của một nhóm hoặc một thời điểm quan trọng. | Chọn thêm góc quan sát theo hành trình, tenant và cửa sổ rủi ro. |
| “Log càng nhiều càng an toàn.” | Có thể làm lộ bí mật, tốn tài nguyên và tạo thêm dữ liệu phải bảo vệ. | Ghi đủ mục đích với trường, quyền đọc và thời hạn lưu rõ ràng. |

## 10. Bài tập áp dụng

Nền tảng muốn bổ sung chức năng nhập điểm hàng loạt từ tệp do giảng viên tải lên. Tác vụ có thể chạy nền, trả kết quả từng dòng và cho phép tải báo cáo lỗi.

Hãy xây dựng đặc tả theo các bước sau:

1. Liệt kê tài sản trong tệp đầu vào, dữ liệu điểm bị tác động, báo cáo lỗi, log và các bản sao tạm.
2. Với từng mục tiêu CIA, nêu ít nhất một rủi ro có nguồn tác động và hậu quả cụ thể.
3. Viết một yêu cầu không tiết lộ dữ liệu ngoài lớp hoặc tenant được cấp quyền, một yêu cầu bảo vệ cập nhật điểm và một yêu cầu về tiếp nhận/xử lý tác vụ đúng hạn.
4. Xác định cách xử lý khi tệp chứa dòng không hợp lệ, tác vụ được gửi lại, quyền giảng viên bị thu hồi trong lúc chờ hoặc hệ thống dừng giữa chừng.
5. Chọn tiêu chí kiểm chứng cho trường hợp thành công, bị từ chối, thành công một phần nếu được phép và phục hồi sau lỗi. Ghi rõ việc nhập có phải nguyên khối hay có thể chấp nhận từng dòng.
6. Liên kết các yêu cầu với kiểm tra quyền, quản lý tác vụ, giao dịch cập nhật, logging và phục hồi. Nêu một quyết định đánh đổi cùng điều kiện chấp nhận.

Một lời giải tốt phải làm rõ rằng tệp có cấu trúc hợp lệ chưa chứng minh người tải lên có quyền sửa mọi dòng; báo cáo lỗi cũng có thể tiết lộ dữ liệu; và việc nhận tác vụ vào hàng đợi chưa đồng nghĩa điểm đã cập nhật thành công.

Kết thúc bài học, người học cần phân biệt được ba mục tiêu CIA, phân tích tác động theo tài sản và diễn đạt chúng thành nghĩa vụ cụ thể của hệ thống. Yêu cầu chỉ trở nên hữu ích cho phát triển khi có phạm vi, phản ứng, tiêu chí kiểm chứng và liên kết với rủi ro, kiến trúc cùng bằng chứng phù hợp.
