# Bảo mật trong vòng đời phát triển

## 1. Bảo mật là một phần của quá trình phát triển sản phẩm

Một tính năng có thể đáp ứng đúng yêu cầu nghiệp vụ nhưng vẫn làm lộ dữ liệu, cho phép truy cập vượt quyền hoặc khiến hệ thống khó phục hồi sau sự cố. Các vấn đề này thường bắt đầu từ những quyết định sớm: chưa xác định dữ liệu nào cần bảo vệ, chưa làm rõ ai được phép thực hiện hành động nào, hoặc chưa đặt tiêu chí kiểm chứng cho mục tiêu bảo mật.

Trong vòng đời phát triển phần mềm, yêu cầu bảo mật giúp chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành hành vi cụ thể của hệ thống, điều kiện vận hành và bằng chứng có thể kiểm tra. Yêu cầu được duy trì từ lúc hình thành ý tưởng, qua thiết kế, triển khai, kiểm thử, phát hành, vận hành, thay đổi cho đến khi ngừng cung cấp dịch vụ.

Ví dụ, mục tiêu “bảo vệ hóa đơn khách hàng” cần được làm rõ thành các yêu cầu như:

- Người dùng chỉ được đọc hóa đơn của tổ chức mình và phải có quyền đọc hóa đơn.
- Mỗi lần truy cập hóa đơn bị từ chối phải tạo được sự kiện kiểm toán theo chính sách ghi log.
- Đường dẫn tải bản xuất hóa đơn phải chịu cùng quy tắc phân quyền với API xem hóa đơn.
- Bản sao lưu chứa hóa đơn phải được giới hạn truy cập và khôi phục được trong thời gian đã thỏa thuận.

Mỗi yêu cầu còn cần người chịu trách nhiệm, phạm vi áp dụng, cách kiểm chứng và điều kiện được xem là đạt. Nhờ đó, nhóm có thể trao đổi về một hợp đồng có thể kiểm tra trong suốt quá trình phát triển.

Sau bài học này, người học có thể:

1. Giải thích vai trò của yêu cầu bảo mật ở từng giai đoạn phát triển.
2. Liên kết rủi ro, mô hình đe dọa, yêu cầu, quyết định kiến trúc và kiểm thử.
3. Viết tiêu chí chấp nhận cho xác thực, phân quyền, bảo vệ dữ liệu, logging và phục hồi.
4. Theo dõi yêu cầu khi hệ thống thay đổi, khi có ngoại lệ và khi ngừng hoạt động.

## 2. Những khái niệm cần phân biệt

### 2.1. Mục tiêu, mối đe dọa, yêu cầu và biện pháp kiểm soát

| Khái niệm | Câu hỏi cần trả lời | Ví dụ trong hệ thống quản lý hóa đơn |
|---|---|---|
| Mục tiêu bảo mật | Điều gì cần được bảo vệ? | Giữ bí mật dữ liệu hóa đơn giữa các tổ chức |
| Mối đe dọa | Điều gì có thể gây hại và bằng cách nào? | Người dùng thay mã hóa đơn để lấy hóa đơn của tổ chức khác |
| Yêu cầu bảo mật | Hệ thống bắt buộc phải làm gì? | Kiểm tra quyền của chủ thể đối với tổ chức và hóa đơn tại mọi đường truy cập |
| Biện pháp kiểm soát | Sẽ thực hiện yêu cầu bằng cách nào? | Tập trung chính sách phân quyền, lọc truy vấn theo tổ chức, kiểm tra quyền tại lớp dịch vụ |
| Tiêu chí chấp nhận | Quan sát điều gì để kết luận yêu cầu đạt? | Người dùng A không lấy được nội dung hay bản tải xuống của hóa đơn thuộc B |
| Bằng chứng | Căn cứ nào chứng minh đã kiểm tra? | Kết quả kiểm thử được liên kết với phiên bản mã và cấu hình tương ứng |

Một biện pháp kiểm soát có thể đáp ứng nhiều yêu cầu. Một yêu cầu cũng có thể cần nhiều biện pháp phối hợp. Chẳng hạn, cài đặt xác thực không tự chứng minh rằng phân quyền trên từng hóa đơn đã đúng.

### 2.2. Vòng đời yêu cầu và vòng đời sản phẩm

Vòng đời sản phẩm mô tả quá trình tạo ra, vận hành và kết thúc một hệ thống. Vòng đời yêu cầu mô tả cách một yêu cầu được đề xuất, thống nhất, thiết kế, triển khai, kiểm chứng và cập nhật.

Trong thực tế, hai vòng đời này đan xen. Một sản phẩm đang vận hành vẫn có yêu cầu mới khi bổ sung API, kết nối đối tác, thay đổi dữ liệu thu thập hoặc gặp sự cố. Mỗi thay đổi đáng kể cần được đánh giá như một vòng phát triển có phạm vi phù hợp.

Trạng thái “đã triển khai” của yêu cầu chỉ cho biết đã có phần thực hiện. Trạng thái “đã kiểm chứng” cần thêm bằng chứng. Khi chính sách, kiến trúc hoặc cấu hình thay đổi, bằng chứng cũ có thể cần được tạo lại.

### 2.3. Các dạng yêu cầu bảo mật

Để nhóm dễ phân công và kiểm chứng, có thể nhận diện ba dạng thường gặp:

- **Hành vi chức năng:** kiểm tra quyền đọc hóa đơn, thu hồi phiên đăng nhập, ghi nhận thao tác quản trị.
- **Thuộc tính chất lượng và khả năng vận hành:** giới hạn thời gian phục hồi, khả năng phát hiện bất thường, mức sẵn sàng của luồng xác thực.
- **Ràng buộc:** dùng cơ chế quản lý khóa được tổ chức phê duyệt, giới hạn vị trí lưu dữ liệu theo nghĩa vụ áp dụng, tuân theo quy trình phê duyệt truy cập đặc quyền.

Dù thuộc dạng nào, yêu cầu cần đủ cụ thể để xác định điều kiện đạt. Các từ “an toàn”, “nhanh”, “đầy đủ”, “phù hợp” cần được giải thích bằng phạm vi và thước đo.

## 3. Một mạch liên kết xuyên suốt vòng đời

Luồng thông tin cơ bản có thể biểu diễn như sau:

```text
Tài sản + mục tiêu nghiệp vụ + nghĩa vụ áp dụng
                    |
                    v
Luồng dữ liệu + ranh giới tin cậy + mô hình đe dọa
                    |
                    v
Rủi ro được ưu tiên
                    |
                    v
Yêu cầu có mã định danh và tiêu chí chấp nhận
                    |
                    v
Quyết định kiến trúc + công việc triển khai
                    |
                    v
Kiểm thử + bằng chứng + quyết định phát hành
                    |
                    v
Giám sát + ứng phó + phục hồi + phản hồi thay đổi
                    |
                    +----> Cập nhật mô hình đe dọa và yêu cầu
```

Mối liên kết cần truy được theo cả hai chiều. Từ một rủi ro, nhóm tìm được các yêu cầu đang xử lý nó. Từ một kiểm thử thất bại, nhóm tìm được yêu cầu bị vi phạm và rủi ro có thể xuất hiện.

Ví dụ:

| Thành phần | Định danh và nội dung |
|---|---|
| Rủi ro | RISK-01: lộ hóa đơn giữa các tổ chức do truy cập trực tiếp theo mã tài nguyên |
| Yêu cầu | SEC-AUTHZ-01: kiểm tra quyền đọc trên tài nguyên thuộc đúng tổ chức |
| Quyết định thiết kế | ADR-07: ngữ cảnh tổ chức được xác lập từ danh tính đã xác thực và quan hệ thành viên đáng tin cậy |
| Công việc | DEV-143: bổ sung chính sách cho API chi tiết và đường tải bản xuất |
| Kiểm thử | TEST-21: kiểm tra truy cập chéo tổ chức trên API chi tiết |
| Kiểm thử bổ sung | TEST-22: kiểm tra quyền tải bản xuất khi đã mất quyền |
| Bằng chứng | Báo cáo kiểm thử gắn với phiên bản ứng dụng, cấu hình và môi trường |
| Theo dõi vận hành | Cảnh báo khi có mẫu truy cập bị từ chối bất thường; bảo vệ dữ liệu trong sự kiện |

Các mã chỉ là ví dụ. Điểm quan trọng là mối quan hệ được lưu ở nơi nhóm sử dụng và được cập nhật cùng thay đổi.

## 4. Giai đoạn khởi tạo: xác định điều cần bảo vệ

### 4.1. Bắt đầu từ nghiệp vụ và tài sản

Trước khi lựa chọn công nghệ, nhóm cần hiểu hệ thống phục vụ ai, xử lý dữ liệu gì và hậu quả của việc mất bí mật, sai lệch hoặc gián đoạn.

Với dịch vụ hóa đơn nhiều tổ chức, tài sản có thể gồm nội dung hóa đơn, tệp đính kèm, dữ liệu thanh toán, danh tính người dùng, khóa tích hợp, sự kiện kiểm toán và bản sao lưu. Khả năng phát hành hóa đơn đúng hạn cũng là một tài sản về mặt vận hành.

Những thông tin cần làm rõ gồm:

- Các loại chủ thể: người dùng thường, quản trị tổ chức, nhân viên hỗ trợ, tài khoản dịch vụ và đối tác.
- Các hành động có tác động cao: thay đổi quyền, xuất hàng loạt, xóa dữ liệu, khôi phục bản sao lưu.
- Dữ liệu nhạy cảm, nơi lưu trữ, thời hạn giữ và nhu cầu xóa.
- Những hệ thống bên ngoài được tin cậy và mức phụ thuộc vào chúng.
- Nghĩa vụ hợp đồng, chính sách và quy định thực sự áp dụng cho sản phẩm.
- Các mức gián đoạn và mất dữ liệu mà nghiệp vụ có thể chấp nhận.

Chủ sở hữu sản phẩm, dữ liệu và vận hành cần tham gia vì họ có thông tin để xác định tác động và ưu tiên. Nhóm bảo mật hỗ trợ diễn giải thành rủi ro và yêu cầu có thể kiểm chứng.

### 4.2. Đặt phạm vi và giả định rõ ràng

Một yêu cầu chỉ hữu ích khi người đọc biết nó áp dụng ở đâu. “Mọi truy cập dữ liệu phải được kiểm tra quyền” cần làm rõ phạm vi gồm API công khai, công cụ quản trị, tác vụ nền, bộ nhớ đệm, xuất dữ liệu và tích hợp đối tác.

Giả định cũng cần được ghi lại. Ví dụ: “Danh tính tổ chức trong ngữ cảnh xử lý chỉ được tạo từ thông tin đã được máy chủ xác minh”. Nếu thiết kế sau này cho phép trình duyệt gửi tùy ý mã tổ chức để quyết định quyền, giả định đó đã bị phá vỡ và cần xem xét lại yêu cầu liên quan.

Đầu ra của giai đoạn này là phạm vi bảo vệ, danh sách tài sản, mục tiêu ban đầu và người chịu trách nhiệm. Những phần còn chưa biết phải có người làm rõ trước quyết định phụ thuộc vào chúng.

## 5. Giai đoạn phân tích: chuyển rủi ro thành yêu cầu

### 5.1. Dùng mô hình đe dọa để tìm tình huống lạm dụng

Mô hình đe dọa mô tả thành phần, luồng dữ liệu, ranh giới tin cậy và những cách hệ thống có thể bị lạm dụng. Độ chi tiết cần tương xứng với quy mô và mức rủi ro của thay đổi.

Với chức năng tải hóa đơn, có thể đặt các tình huống:

- Người dùng đoán hoặc thu thập mã hóa đơn của tổ chức khác.
- Một đường tải tệp bỏ qua kiểm tra quyền đã có ở API chi tiết.
- Tác vụ nền xuất dữ liệu sử dụng quyền quá rộng hoặc lấy sai ngữ cảnh tổ chức.
- Kết quả trong bộ nhớ đệm được trả cho người dùng thuộc tổ chức khác.
- URL tải tạm thời tiếp tục dùng được quá lâu sau khi quyền truy cập bị thu hồi.

Mỗi tình huống cần được đánh giá về tác động, khả năng xảy ra, điều kiện khai thác và biện pháp hiện có. Nhóm dùng kết quả đó để ưu tiên yêu cầu và quyết định cách xử lý rủi ro.

### 5.2. Viết yêu cầu có thể kiểm chứng

Một mẫu thực hành đơn giản:

```text
ID:
Mục tiêu và rủi ro liên quan:
Chủ thể, tài nguyên, hành động:
Phạm vi và điều kiện kích hoạt:
Hành vi bắt buộc:
Trường hợp bị từ chối hoặc xử lý lỗi:
Tiêu chí chấp nhận:
Cách kiểm chứng và bằng chứng:
Người chịu trách nhiệm:
Giả định, phụ thuộc và phiên bản:
```

Ví dụ:

```text
ID: SEC-AUTHZ-01
Rủi ro: RISK-01 - Lộ dữ liệu hóa đơn giữa các tổ chức.
Phạm vi: API đọc chi tiết, tải tệp và xuất hóa đơn.

Hành vi bắt buộc:
Máy chủ chỉ trả dữ liệu hóa đơn khi danh tính đã xác thực có quan hệ
thành viên còn hiệu lực với tổ chức sở hữu hóa đơn và có quyền đọc
hóa đơn tương ứng. Ngữ cảnh quyền phải được xác định từ nguồn tin cậy.

Nếu không xác lập được quyền, hệ thống phải từ chối cung cấp dữ liệu.
Lỗi trả về không chứa nội dung hóa đơn hoặc thông tin nội bộ nhạy cảm.

Tiêu chí chấp nhận:
- Người dùng có quyền trong tổ chức A đọc được hóa đơn hợp lệ của A.
- Người dùng A không đọc hoặc tải được hóa đơn thuộc tổ chức B.
- Người dùng đã mất quyền không nhận được dữ liệu qua các đường
  truy cập thuộc phạm vi, theo chính sách hiệu lực quyền đã thống nhất.
- Tác vụ xuất dữ liệu và bộ nhớ đệm tuân theo cùng phạm vi tổ chức.

Bằng chứng:
Kết quả kiểm thử tích hợp và kiểm tra thiết kế cho từng đường truy cập,
gắn với phiên bản mã, cấu hình và chính sách hiệu lực quyền.

Chủ sở hữu: Nhóm phụ trách dịch vụ hóa đơn.
```

Chính sách hiệu lực quyền cần có giới hạn thời gian rõ ràng nếu hệ thống sử dụng token hoặc bộ nhớ đệm có thể giữ thông tin quyền cũ. Một câu như “thu hồi có hiệu lực trong thời gian hợp lý” chưa đủ để triển khai và kiểm chứng.

### 5.3. Chốt tiêu chí trước khi triển khai

Nhóm nên thỏa thuận các con số và điều kiện còn mở trước khi công việc phụ thuộc bắt đầu. Ví dụ: thời gian hiệu lực của phiên, độ trễ thu hồi quyền, ngưỡng cảnh báo hoặc thời hạn lưu log.

Một yêu cầu còn chờ quyết định có thể tồn tại trong danh sách công việc, nhưng phải thể hiện rõ nó chưa sẵn sàng để nghiệm thu. Các giá trị ví dụ trong bài học cần được thay bằng quyết định phù hợp với hệ thống cụ thể.

## 6. Giai đoạn thiết kế: phân bổ yêu cầu vào kiến trúc

### 6.1. Chỉ rõ nơi thực thi và phạm vi tin cậy

Thiết kế cần trả lời: thành phần nào thực thi yêu cầu, dữ liệu nào được tin cậy, lỗi được xử lý ra sao và đường đi nào có thể bỏ qua kiểm soát.

Với yêu cầu phân quyền, cần xác định ít nhất:

- Nguồn xác lập danh tính và quan hệ thành viên tổ chức.
- Nơi đánh giá quyền trước khi đọc hoặc thay đổi tài nguyên.
- Cách truyền ngữ cảnh danh tính sang tác vụ nền.
- Cách tách dữ liệu trong truy vấn, bộ nhớ đệm và tệp xuất.
- Cách xử lý khi dịch vụ quyết định quyền bị lỗi hoặc không phản hồi.
- Chính sách hiệu lực và thu hồi quyền trên token, phiên, liên kết tải và kết quả đã lưu.

Kiểm soát ở giao diện giúp trải nghiệm người dùng rõ ràng hơn; quyền truy cập dữ liệu vẫn cần được thực thi ở phía máy chủ và tại các thành phần có thể trả dữ liệu.

### 6.2. Xem xét yêu cầu cùng các đánh đổi

Một yêu cầu có thể ảnh hưởng tới hiệu năng, độ sẵn sàng và trải nghiệm. Ví dụ, kiểm tra quyền mới nhất ở mỗi yêu cầu giúp giảm độ trễ thu hồi quyền nhưng có thể tăng phụ thuộc vào dịch vụ phân quyền. Dùng bộ nhớ đệm cần quy định thời gian hết hạn, cách vô hiệu hóa và mức chậm trễ được chấp nhận.

Quyết định kiến trúc cần ghi lại lựa chọn, lý do, rủi ro còn lại và điều kiện cần xem xét lại. Nếu thiết kế không đáp ứng yêu cầu đã thống nhất, nhóm phải giải quyết chênh lệch bằng thay đổi thiết kế hoặc quy trình chấp nhận rủi ro có thẩm quyền.

### 6.3. Thiết kế cả tình huống lỗi

Yêu cầu bảo mật cần bao phủ các trường hợp phụ thuộc không hoạt động:

- Không xác minh được danh tính hoặc quyền thì xử lý thế nào?
- Kho bí mật hoặc dịch vụ quản lý khóa không sẵn sàng thì luồng nào dừng?
- Kênh gửi sự kiện kiểm toán bị gián đoạn thì lưu đệm ở đâu, trong bao lâu?
- Khôi phục dữ liệu thất bại giữa chừng thì có đưa trạng thái chưa nhất quán vào phục vụ không?

Quyết định dừng, thử lại, xếp hàng hay giảm chức năng cần dựa vào rủi ro của từng nghiệp vụ. Hành vi khi lỗi phải có tiêu chí kiểm thử cụ thể.

## 7. Giai đoạn triển khai: đưa yêu cầu vào công việc hằng ngày

### 7.1. Mỗi công việc có liên kết với yêu cầu

Một công việc triển khai nên chỉ rõ mã yêu cầu, phạm vi thay đổi và kiểm chứng đi kèm. Khi người phát triển sửa đường tải hóa đơn, họ cần biết đường đó chịu cùng chính sách với API xem chi tiết.

Trong rà soát mã, nhóm xem xét các câu hỏi có liên quan trực tiếp:

- Dữ liệu đầu vào nào có thể do người dùng kiểm soát?
- Kiểm tra quyền xảy ra trước thao tác nhạy cảm hay sau khi đã đọc dữ liệu?
- Tác vụ nền có giữ đúng ngữ cảnh chủ thể và tổ chức không?
- Log, thông báo lỗi và công cụ chẩn đoán có chứa dữ liệu bị cấm ghi không?
- Cấu hình mặc định và hành vi khi thiếu cấu hình có đáp ứng yêu cầu không?

Quy tắc dùng chung giúp giảm sai khác giữa các tính năng, nhưng vẫn cần kiểm tra nơi áp dụng. Một thư viện phân quyền tốt chỉ có tác dụng khi mọi đường truy cập cần bảo vệ thực sự sử dụng đúng nó.

### 7.2. Bảo vệ mã nguồn, phụ thuộc và đường phát hành

Vòng đời phát triển cũng tạo ra tài sản cần bảo vệ: mã nguồn, thông tin xác thực của CI/CD, gói phụ thuộc, bản build và quyền phát hành.

Nhóm có thể cụ thể hóa thành các yêu cầu như:

- Quyền sửa mã và phát hành được cấp theo trách nhiệm và được thu hồi khi không còn cần.
- Bí mật dùng trong pipeline được cấp qua cơ chế quản lý bí mật, có phạm vi quyền rõ ràng.
- Bản phát hành truy được về phiên bản mã và cấu hình tạo ra nó.
- Phát hiện rủi ro trong phụ thuộc được xử lý theo mức độ ảnh hưởng và thời hạn đã thống nhất.
- Thay đổi cấu hình bảo mật được xem xét và ghi nhận như thay đổi mã có tác động tương đương.

Đây là những yêu cầu cho quá trình tạo và đưa phần mềm vào vận hành. Chúng bổ sung cho các yêu cầu về hành vi của sản phẩm.

## 8. Giai đoạn kiểm chứng: thu thập bằng chứng đúng mục tiêu

### 8.1. Chọn phương pháp theo bản chất yêu cầu

| Nhóm yêu cầu | Ví dụ phương pháp kiểm chứng | Bằng chứng cần giữ |
|---|---|---|
| Xác thực | Kiểm thử đăng nhập, kết thúc phiên, thu hồi và các luồng khôi phục tài khoản thuộc phạm vi | Kịch bản, kết quả và cấu hình phiên được kiểm tra |
| Phân quyền | Kiểm thử theo ma trận vai trò, tài nguyên, tổ chức và trạng thái quyền | Trường hợp được phép và bị từ chối trên các đường truy cập |
| Dữ liệu | Kiểm tra cấu hình lưu trữ, đường truyền, quyền truy cập và dữ liệu xuất | Phạm vi dữ liệu, cấu hình đã xác minh và kết quả kiểm tra |
| Logging | Kích hoạt sự kiện mẫu, kiểm tra trường dữ liệu và quyền đọc log | Sự kiện đã che dữ liệu nhạy cảm và kết quả kiểm tra kênh thu thập |
| Phục hồi | Diễn tập khôi phục trong môi trường cô lập | Mốc thời gian, điểm dữ liệu phục hồi và kết quả kiểm tra toàn vẹn |
| Đường phát hành | Kiểm tra quyền pipeline, nguồn bản build và cấu hình phát hành | Dấu vết phiên bản, phê duyệt và bằng chứng cấu hình |

Kiểm thử đơn vị phù hợp với một số quy tắc cục bộ. Kiểm thử tích hợp cần thiết khi quyền, dữ liệu hoặc ngữ cảnh đi qua nhiều thành phần. Kiểm tra thiết kế, cấu hình và diễn tập vận hành cung cấp bằng chứng cho các yêu cầu không thể xác minh đầy đủ chỉ bằng việc gọi một hàm.

### 8.2. Kiểm thử cả đường được phép và đường bị từ chối

Với phân quyền hóa đơn, có thể dùng ma trận sau:

| Chủ thể | Tài nguyên hoặc trạng thái | Kết quả mong đợi |
|---|---|---|
| Người dùng A có quyền đọc | Hóa đơn thuộc A | Trả đúng dữ liệu được phép |
| Người dùng A có quyền đọc | Hóa đơn thuộc B | Từ chối, không lộ dữ liệu hóa đơn |
| Người dùng A thiếu quyền đọc | Hóa đơn thuộc A | Từ chối |
| Người dùng vừa bị thu hồi quyền | Hóa đơn thuộc A | Từ chối trong giới hạn hiệu lực quyền đã thống nhất |
| Yêu cầu chưa xác thực | Hóa đơn bất kỳ | Không trả dữ liệu được bảo vệ |
| Tác vụ xuất dữ liệu của A | Dữ liệu từ nhiều tổ chức | Chỉ xuất dữ liệu trong phạm vi quyền của A |
| Người dùng B sau khi A tạo bộ nhớ đệm | Cùng mẫu truy vấn | Không nhận nội dung riêng của A |

Cần áp dụng các trường hợp thích hợp cho API, tải tệp, xuất dữ liệu và các đường truy cập thực tế. Việc dùng mã tài nguyên khó đoán chỉ giảm khả năng dò tìm; quy tắc phân quyền vẫn phải được kiểm chứng.

### 8.3. Bằng chứng phải gắn với phiên bản

Một báo cáo đạt ở phiên bản trước có thể không còn áp dụng sau khi thay đổi cơ chế phiên, truy vấn dữ liệu hoặc chính sách quyền. Bằng chứng cần ghi ít nhất yêu cầu được kiểm tra, phiên bản mã, cấu hình liên quan, môi trường, thời điểm và kết quả.

Các công cụ phân tích mã, quét phụ thuộc hoặc kiểm thử động cung cấp những loại tín hiệu khác nhau. Kết quả quét sạch không đủ để kết luận mọi yêu cầu đã đạt. Nhóm cần đối chiếu trực tiếp với tiêu chí chấp nhận và những phạm vi chưa được kiểm chứng.

## 9. Giai đoạn phát hành: quyết định dựa trên điều kiện đã thống nhất

### 9.1. Đặt điều kiện phát hành theo rủi ro

Trước khi phát hành, nhóm cần biết những yêu cầu nào là điều kiện bắt buộc, bằng chứng nào cần có và ai có quyền quyết định khi còn rủi ro tồn đọng.

Ví dụ, nhóm sản phẩm có thể thống nhất rằng lỗi truy cập chéo tổ chức phải được xử lý trước phát hành. Những yêu cầu ít nghiêm trọng hơn có thể được giải quyết theo kế hoạch được phê duyệt, nếu chính sách tổ chức cho phép.

Điều kiện phát hành nên kiểm tra:

- Các yêu cầu áp dụng cho thay đổi đã có kết quả kiểm chứng phù hợp.
- Cấu hình môi trường đích, quyền triển khai và bí mật đã được chuẩn bị.
- Kế hoạch giám sát, ứng phó và người trực vận hành đã rõ.
- Cách quay lui hoặc chuyển tiếp an toàn đã được đánh giá với thay đổi dữ liệu.
- Các ngoại lệ còn hiệu lực có người chịu trách nhiệm và ngày xem xét lại.

Tự động hóa trong CI/CD giúp thực hiện những kiểm tra lặp lại. Các quyết định cần đánh giá rủi ro hoặc xác nhận nghiệp vụ vẫn cần người có thẩm quyền.

### 9.2. Kiểm tra cấu hình tại môi trường đích

Cùng một bản ứng dụng có thể có mức bảo vệ khác nhau giữa các môi trường. Quyền truy cập kho dữ liệu, cấu hình phiên, nơi gửi log và chính sách sao lưu cần được kiểm tra ở môi trường triển khai thực tế.

Một bản phát hành đủ mã nguồn nhưng thiếu cấu hình ghi log hoặc cấp quyền quá rộng vẫn có thể vi phạm yêu cầu. Trách nhiệm giữa nhóm phát triển và vận hành cần được phân chia cụ thể theo từng yêu cầu.

## 10. Giai đoạn vận hành: duy trì hiệu lực của yêu cầu

### 10.1. Xác thực và phân quyền tiếp tục thay đổi

Trong vận hành, người dùng gia nhập hoặc rời tổ chức, vai trò thay đổi, tài khoản dịch vụ được tạo mới và phiên đăng nhập tồn tại qua nhiều lần phát hành. Yêu cầu cần bao phủ cấp quyền, điều chỉnh quyền, rà soát, thu hồi và xử lý tài khoản không còn chủ sở hữu.

Những dấu hiệu cần theo dõi có thể gồm truy cập bị từ chối tăng bất thường, sử dụng đặc quyền ngoài quy trình hoặc thao tác hàng loạt khác mẫu thông thường. Mỗi cảnh báo cần chỉ rõ người tiếp nhận và hành động dự kiến, tránh thu thập nhiều sự kiện mà không có khả năng xử lý.

### 10.2. Logging cần phục vụ điều tra và bảo vệ dữ liệu

Yêu cầu logging có thể quy định sự kiện phải ghi, thời điểm, chủ thể, hành động, tài nguyên, kết quả và mã tương quan. Đồng thời phải quy định dữ liệu không được ghi, quyền đọc log, thời hạn giữ và cách phát hiện việc gián đoạn thu thập.

Ví dụ:

```text
SEC-LOG-01:
Mọi thay đổi quyền quản trị phải tạo sự kiện kiểm toán gồm thời gian,
chủ thể thực hiện, đối tượng bị thay đổi, loại thay đổi và kết quả.

Không ghi mật khẩu, token phiên hoặc nội dung hóa đơn vào sự kiện.
Chỉ vai trò được phê duyệt mới được truy cập kho kiểm toán.

Kiểm chứng:
Thực hiện thay đổi quyền thành công và thất bại; xác minh sự kiện,
quyền truy cập và hành vi khi kênh gửi sự kiện bị gián đoạn.
```

Nếu yêu cầu cần thời gian ghi nhận tối đa hoặc thời hạn giữ log, các giá trị đó phải được chốt cùng nhu cầu điều tra, khả năng vận hành và nghĩa vụ áp dụng.

### 10.3. Sao lưu phải đi cùng khả năng phục hồi

Hai thước đo thường dùng:

- **RPO:** giới hạn mất dữ liệu được chấp nhận, thường biểu diễn bằng khoảng thời gian giữa điểm dữ liệu khôi phục được và thời điểm gián đoạn.
- **RTO:** thời gian mục tiêu để khôi phục dịch vụ đến mức hoạt động đã thống nhất sau sự cố, với mốc bắt đầu và kết thúc được định nghĩa rõ.

Ví dụ minh họa: một dịch vụ đặt RPO không quá 15 phút và RTO không quá 2 giờ. Các con số này cần được nghiệp vụ phê duyệt và chứng minh bằng diễn tập phù hợp với các kịch bản sự cố đã chọn.

Có bản sao lưu không tự chứng minh đạt RPO hoặc RTO. Nhóm cần thử khôi phục, kiểm tra tính toàn vẹn, kiểm tra dữ liệu giữa các thành phần và xác nhận chức năng phục vụ. Nếu dữ liệu bị phá hoại trước khi phát hiện, điểm khôi phục sạch gần nhất có thể cũ hơn nhiều so với bản sao lưu mới nhất.

Yêu cầu phục hồi còn cần chỉ rõ ai được quyền khôi phục, khóa giải mã được bảo vệ và truy cập thế nào, khôi phục vào môi trường nào và cách tránh phục vụ dữ liệu chưa xác minh.

### 10.4. Sự cố tạo ra đầu vào cho vòng phát triển tiếp theo

Sau sự cố hoặc diễn tập, nhóm cần xác định yêu cầu nào thiếu, tiêu chí nào chưa đủ, kiểm soát nào không hoạt động và giả định nào đã sai. Kết quả cần trở thành thay đổi cụ thể trong mô hình đe dọa, yêu cầu, thiết kế, kiểm thử hoặc quy trình vận hành.

Ví dụ, nếu xuất dữ liệu qua tác vụ nền làm lộ hóa đơn, chỉ sửa API chi tiết sẽ để lại đường rủi ro. Cần cập nhật phạm vi yêu cầu, bổ sung kiểm thử cho tác vụ và rà soát cách truyền ngữ cảnh tổ chức.

## 11. Quản lý thay đổi và ngoại lệ trong suốt vòng đời

### 11.1. Khi nào phải xem xét lại yêu cầu?

Những thay đổi thường tạo ra yêu cầu mới hoặc làm bằng chứng cũ mất hiệu lực gồm:

- Mở thêm API, kiểu người dùng, vai trò hoặc hành động quản trị.
- Thu thập thêm dữ liệu hoặc thay đổi nơi lưu, thời hạn giữ, bên được chia sẻ.
- Đưa xử lý sang tác vụ nền, bổ sung bộ nhớ đệm hoặc tích hợp đối tác.
- Thay đổi cơ chế xác thực, token, chính sách phiên hoặc quản lý khóa.
- Di chuyển hạ tầng, kho dữ liệu hoặc cách sao lưu và phục hồi.
- Xuất hiện kỹ thuật tấn công, sự cố hoặc nghĩa vụ mới có liên quan.

Đánh giá thay đổi bắt đầu bằng phạm vi ảnh hưởng: tài sản nào bị tác động, ranh giới tin cậy nào thay đổi, yêu cầu nào liên quan và kiểm chứng nào phải thực hiện lại. Phạm vi rà soát tăng theo mức rủi ro và độ lan rộng của thay đổi.

### 11.2. Ngoại lệ cần có thời hạn và người chịu trách nhiệm

Khi chưa thể đáp ứng một yêu cầu, hồ sơ ngoại lệ cần chỉ rõ:

1. Yêu cầu chưa đạt và hệ thống bị ảnh hưởng.
2. Lý do, tác động và mức rủi ro còn lại.
3. Biện pháp bù trừ cùng bằng chứng về hiệu lực của chúng.
4. Người có thẩm quyền chấp nhận rủi ro.
5. Chủ sở hữu và kế hoạch khắc phục.
6. Ngày hết hạn hoặc điều kiện buộc phải xem xét lại.

Nhóm kỹ thuật cần trình bày trung thực phạm vi chưa đạt. Việc chấp nhận rủi ro phải tuân theo thẩm quyền của tổ chức và các nghĩa vụ bắt buộc; một hồ sơ ngoại lệ nội bộ không tự làm mất hiệu lực các nghĩa vụ đó.

Khi ngoại lệ hết hạn, nhóm phải khắc phục hoặc thực hiện lại quyết định theo quy trình áp dụng. Trạng thái ngoại lệ cũng cần hiển thị trong quyết định phát hành và vận hành có liên quan.

## 12. Giai đoạn ngừng hoạt động: kết thúc có kiểm soát

Kết thúc một tính năng hoặc dịch vụ vẫn có thể để lại dữ liệu, danh tính và quyền truy cập. Yêu cầu cho giai đoạn này nên bao phủ:

- Chuyển giao hoặc xuất dữ liệu cho bên có thẩm quyền theo phạm vi đã thống nhất.
- Thu hồi tài khoản dịch vụ, token, chứng thư và tích hợp không còn cần thiết.
- Dừng tuyến truy cập, tác vụ định kỳ và luồng đồng bộ liên quan.
- Xử lý dữ liệu đang lưu, bản sao, log và bản sao lưu theo chính sách giữ, xóa và nghĩa vụ áp dụng.
- Lưu bằng chứng cần thiết và chỉ rõ ai tiếp tục chịu trách nhiệm với dữ liệu còn giữ.

Dữ liệu trong bản sao lưu có thể có chu kỳ giữ khác dữ liệu đang phục vụ. Chính sách cần xác định cách hết hạn, xóa hoặc hạn chế phục hồi dữ liệu đã được yêu cầu xóa, phù hợp với khả năng kỹ thuật và nghĩa vụ áp dụng.

Tiêu chí hoàn tất phải có thể kiểm tra: những đường truy cập nào đã dừng, bí mật nào đã thu hồi, dữ liệu nào còn giữ và căn cứ giữ đến thời điểm nào.

## 13. Ví dụ xuyên suốt: bổ sung chức năng xuất hóa đơn

Giả sử hệ thống đã cho phép xem từng hóa đơn và nay bổ sung chức năng xuất tệp qua tác vụ nền. Bản xuất được lưu tạm để người dùng tải xuống. Thay đổi này mở rộng thời gian tồn tại của dữ liệu và thêm đường truy cập ngoài API hiện tại.

### 13.1. Phân tích rủi ro và đặc tả yêu cầu

| Rủi ro hoặc tình huống | Yêu cầu cần đặc tả | Tiêu chí kiểm chứng tiêu biểu |
|---|---|---|
| Tác vụ chạy dưới quyền quá rộng | Phạm vi xuất phải giới hạn theo tổ chức, quyền và tập dữ liệu đã được cho phép | Tạo yêu cầu xuất từ A; dữ liệu và tệp kết quả không chứa hóa đơn B |
| Người dùng mất quyền trong lúc tác vụ đang chạy | Quy định thời điểm kiểm tra lại quyền khi xử lý và khi tải kết quả | Thu hồi quyền giữa các mốc; kết quả đúng theo chính sách đã chốt |
| Tệp bị chia sẻ ngoài ý muốn | Cách tải, thời gian tồn tại và thu hồi quyền tải phải được xác định | Kiểm tra người khác truy cập, liên kết hết hạn và trường hợp bị thu hồi |
| Tệp chứa dữ liệu vượt nhu cầu | Chỉ đưa trường dữ liệu đã được phê duyệt vào bản xuất | Đối chiếu nội dung tệp với danh sách trường được phép |
| Không điều tra được ai xuất dữ liệu | Ghi nhận người yêu cầu, phạm vi, thời điểm và kết quả theo chính sách logging | Tìm được sự kiện của lần xuất mà không lộ nội dung hóa đơn trong log |
| Tệp tạm tồn tại quá lâu | Đặt thời hạn lưu và cơ chế dọn dữ liệu có giám sát | Kiểm tra tệp hết hạn, quyền tải sau hết hạn và lỗi của tác vụ dọn |

Một liên kết tải mà ai sở hữu cũng có thể sử dụng mang tính chất một thông tin trao quyền. Nếu yêu cầu bắt buộc kiểm tra quyền hiện tại tại mỗi lần tải, thiết kế chỉ dựa vào liên kết như vậy có thể không đáp ứng. Nhóm phải chọn cách phân phối tệp phù hợp và ghi rõ giới hạn thu hồi.

### 13.2. Theo dõi thực hiện qua các giai đoạn

1. **Phân tích:** bổ sung tác vụ nền, kho tệp tạm và đường tải vào mô hình đe dọa; thống nhất chính sách quyền và thời hạn lưu.
2. **Thiết kế:** xác định nguồn ngữ cảnh tổ chức, các mốc kiểm tra quyền, quyền truy cập kho tệp và cơ chế hết hạn.
3. **Triển khai:** tạo các công việc có mã yêu cầu, thêm xử lý lỗi và sự kiện kiểm toán phù hợp.
4. **Kiểm chứng:** chạy ma trận truy cập, thử thu hồi quyền giữa các giai đoạn, kiểm tra tệp và lỗi dọn dữ liệu.
5. **Phát hành:** xác minh cấu hình kho tệp, thời hạn lưu, quyền tài khoản dịch vụ và người tiếp nhận cảnh báo.
6. **Vận hành:** theo dõi xuất bất thường, tác vụ lỗi, tệp quá hạn và thay đổi quyền; dùng kết quả để cập nhật yêu cầu.
7. **Ngừng chức năng:** dừng tiếp nhận yêu cầu xuất, xử lý tác vụ còn lại, xóa hoặc giữ tệp theo chính sách và thu hồi quyền không còn cần.

Ví dụ này cho thấy một tính năng nhỏ về mặt giao diện có thể thay đổi đáng kể yêu cầu phân quyền, dữ liệu, logging và vận hành.

## 14. Trách nhiệm, điều kiện hoàn thành và thước đo

### 14.1. Giao trách nhiệm theo từng yêu cầu

| Vai trò | Trách nhiệm điển hình |
|---|---|
| Chủ sở hữu sản phẩm hoặc dữ liệu | Xác định tác động nghiệp vụ, nhu cầu bảo vệ và ưu tiên |
| Kiến trúc sư và nhóm phát triển | Chuyển yêu cầu thành thiết kế, mã và cấu hình có thể kiểm chứng |
| Nhóm bảo mật | Hỗ trợ mô hình đe dọa, đánh giá yêu cầu và các rủi ro còn lại |
| Nhóm kiểm thử | Xây dựng và thực hiện kiểm chứng phù hợp với tiêu chí chấp nhận |
| Nhóm vận hành | Duy trì cấu hình, giám sát, ứng phó và diễn tập phục hồi |
| Người có thẩm quyền chấp nhận rủi ro | Quyết định đối với rủi ro còn lại theo quy trình tổ chức |

Một người có thể kiêm nhiều vai trò trong nhóm nhỏ. Mỗi yêu cầu vẫn cần một chủ sở hữu rõ ràng và những người phối hợp cụ thể.

### 14.2. Đưa yêu cầu vào điều kiện sẵn sàng và hoàn thành

Một công việc có thể được coi là sẵn sàng khi đã xác định yêu cầu liên quan, phạm vi bảo vệ, tiêu chí chấp nhận và các quyết định còn thiếu. Những điểm chưa rõ nhưng ảnh hưởng trực tiếp đến thiết kế cần được giải quyết trước khi triển khai phần phụ thuộc.

Điều kiện hoàn thành có thể bao gồm mã và cấu hình đã được xem xét, kiểm chứng đã đạt, bằng chứng đã liên kết, hướng dẫn vận hành đã cập nhật và rủi ro tồn đọng đã được xử lý theo thẩm quyền.

Cách tích hợp này phù hợp cả với quy trình phát triển tuần tự và phát triển lặp. Trong nhóm phát triển theo các vòng ngắn, yêu cầu bảo mật được thực hiện trong từng thay đổi và được rà soát khi có tác động lớn đến kiến trúc.

### 14.3. Đo mức bao phủ và hiệu lực

Các chỉ số có ích gồm:

- Tỷ lệ yêu cầu bắt buộc có bằng chứng còn phù hợp với phiên bản phát hành.
- Số yêu cầu quan trọng chưa có người chịu trách nhiệm hoặc tiêu chí chấp nhận.
- Số ngoại lệ quá hạn và thời gian xử lý theo mức rủi ro.
- Kết quả diễn tập phục hồi so với RPO, RTO đã thống nhất.
- Mức bao phủ các đường truy cập nhạy cảm trong ma trận kiểm thử quyền.
- Thời gian phát hiện và xử lý các sự kiện thuộc kịch bản giám sát đã chọn.

Mẫu số và phạm vi đo cần rõ ràng. “100% yêu cầu đạt” không có nhiều ý nghĩa nếu bỏ sót đường xuất dữ liệu hoặc chỉ đếm những yêu cầu đã có kiểm thử.

## 15. Những sai lệch thường gặp

| Sai lệch | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Chỉ kiểm tra bảo mật sát ngày phát hành | Phát hiện muộn những vấn đề cần đổi kiến trúc | Đưa tài sản, mô hình đe dọa và tiêu chí chấp nhận vào giai đoạn đầu |
| Ghi yêu cầu “hệ thống phải an toàn” | Nhóm không thống nhất điều kiện đạt | Viết theo chủ thể, hành động, tài nguyên, điều kiện và bằng chứng |
| Đồng nhất đăng nhập với phân quyền | Người dùng hợp lệ vẫn lấy được dữ liệu ngoài phạm vi | Kiểm tra quyền trên tài nguyên và từng đường truy cập |
| Chỉ kiểm thử hành vi được phép | Bỏ sót truy cập trái phép và trạng thái lỗi | Bổ sung trường hợp bị từ chối, thay đổi quyền và lỗi phụ thuộc |
| Xem pipeline đạt là đủ | Bỏ sót logic nghiệp vụ, cấu hình và vận hành | Đối chiếu từng yêu cầu với phương pháp kiểm chứng phù hợp |
| Chỉ kiểm tra việc tạo bản sao lưu | Chưa biết dữ liệu có khôi phục được hay không | Diễn tập phục hồi và đo kết quả theo mục tiêu đã thống nhất |
| Giữ ngoại lệ vô thời hạn | Rủi ro tồn đọng mất người theo dõi | Gắn chủ sở hữu, thời hạn và điều kiện xem xét lại |
| Ngừng dịch vụ nhưng giữ nguyên quyền và dữ liệu | Để lại đường truy cập hoặc tài sản không được quản lý | Có yêu cầu và bằng chứng hoàn tất giai đoạn ngừng hoạt động |

## 16. Bài tập áp dụng

Chọn chức năng “khôi phục quyền truy cập tài khoản” hoặc “xuất báo cáo khách hàng” trong một hệ thống giả định. Chuẩn bị các đầu ra sau:

1. Liệt kê tài sản, chủ thể, luồng dữ liệu và ít nhất hai ranh giới tin cậy.
2. Mô tả ba tình huống lạm dụng có tác động cụ thể.
3. Viết năm yêu cầu bao phủ xác thực, phân quyền, dữ liệu, logging và phục hồi; mỗi yêu cầu có mã, chủ sở hữu và tiêu chí chấp nhận.
4. Chọn một yêu cầu, liên kết nó với quyết định thiết kế và các kiểm thử cho trường hợp được phép, bị từ chối và lỗi phụ thuộc.
5. Nêu bằng chứng cần có trước phát hành và cách duy trì yêu cầu trong vận hành.
6. Đề xuất một thay đổi làm bằng chứng cũ cần được xem xét lại.
7. Xác định dữ liệu và quyền truy cập phải xử lý khi ngừng chức năng.

Tự kiểm tra bằng câu hỏi: một người khác có thể dựa vào đặc tả để xây dựng, kiểm thử và vận hành chức năng mà không phải tự đoán chính sách bảo mật hay không? Nếu còn phải đoán, hãy làm rõ phạm vi, hành vi hoặc tiêu chí tương ứng.
