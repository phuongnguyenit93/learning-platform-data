# Review requirement: rà soát yêu cầu bảo mật trong vòng đời phát triển

## 1. Rà soát yêu cầu nhằm quyết định điều gì?

Một yêu cầu bảo mật có thể nghe hợp lý nhưng vẫn không đủ để triển khai hoặc kiểm chứng:

> Hệ thống phải phân quyền chặt chẽ, ghi log đầy đủ và thu hồi quyền nhanh chóng.

Câu này chưa xác định ai được làm gì, quyền áp dụng trên đối tượng nào, log cần trường nào, “nhanh chóng” là bao lâu và điều gì xảy ra khi một thành phần gặp lỗi. Hai nhóm có thể triển khai hai hành vi khác nhau mà đều cho rằng mình đã đáp ứng.

Review requirement là hoạt động rà soát có cấu trúc để đánh giá liệu yêu cầu có phản ánh đúng nhu cầu bảo vệ, diễn đạt đủ rõ, phù hợp với các yêu cầu khác và có thể được thực hiện, kiểm chứng hay chưa.

Đối với yêu cầu bảo mật, người rà soát cần trả lời đồng thời:

- Yêu cầu đang xử lý rủi ro hoặc nghĩa vụ nào?
- Hành vi bắt buộc có rõ trong các trường hợp hợp lệ, bị cấm và lỗi không?
- Các giả định về danh tính, dữ liệu, kiến trúc và ranh giới tin cậy có hợp lý không?
- Đã có tiêu chí và phương pháp đủ để kết luận đạt hoặc chưa đạt chưa?
- Phần chưa giải quyết được có chủ sở hữu và quyết định phù hợp chưa?

Đầu ra là một quyết định đối với phiên bản yêu cầu cụ thể, cùng các phát hiện và hành động cần thiết. Không nên kết luận “đã review” chỉ vì một cuộc họp đã diễn ra.

Sau bài học, người học có thể chuẩn bị một gói rà soát, phát hiện yêu cầu mơ hồ hoặc mâu thuẫn, ghi phát hiện có thể xử lý và chốt một phiên bản đủ cơ sở để thiết kế, triển khai và kiểm chứng.

## 2. Review requirement nằm ở đâu trong vòng đời?

Một luồng làm việc minh họa:

**Nguồn nhu cầu → đặc tả bản nháp → rà soát → sửa và giải quyết phát hiện → chốt phiên bản → triển khai và kiểm chứng → rà soát lại khi thay đổi.**

Rà soát có thể diễn ra nhiều lần:

- Khi chuyển mục tiêu bảo mật hoặc tình huống đe dọa thành yêu cầu.
- Khi kiến trúc đã rõ hơn và xuất hiện giả định mới.
- Trước khi đưa yêu cầu quan trọng vào một phạm vi phát hành.
- Khi thay đổi quyền, luồng dữ liệu, bên tích hợp hoặc cách vận hành.
- Khi sự cố hoặc kiểm thử cho thấy yêu cầu cũ thiếu hoặc sai.

Cần phân biệt các hoạt động liên quan:

| Hoạt động | Câu hỏi chính |
| --- | --- |
| Review requirement | Yêu cầu này có đúng nhu cầu, đủ rõ, nhất quán và kiểm chứng được không? |
| Rà soát thiết kế | Thiết kế có khả năng đáp ứng yêu cầu trong các điều kiện đã xác định không? |
| Rà soát mã và cấu hình | Cách triển khai có tuân theo thiết kế và yêu cầu không? |
| Kiểm chứng hành vi | Hệ thống thực tế có đáp ứng tiêu chí trên phiên bản và môi trường được kiểm tra không? |
| Quyết định rủi ro | Ai có thẩm quyền cho phép phần rủi ro còn lại tồn tại, trong điều kiện nào? |

Một yêu cầu đã được phê duyệt chưa có nghĩa là hệ thống đã đáp ứng. Tương tự, mã chạy đúng một yêu cầu mơ hồ chưa chứng minh nhu cầu bảo vệ đã được xử lý đầy đủ.

## 3. Chuẩn bị gói đầu vào đủ để rà soát

Không cần một bộ tài liệu dài cho mọi thay đổi. Tuy nhiên, người rà soát phải có đủ ngữ cảnh để hiểu điều đang được quyết định.

Một gói đầu vào hữu ích gồm:

| Đầu vào | Nội dung tối thiểu |
| --- | --- |
| Định danh yêu cầu | ID ổn định, phiên bản, tác giả và chủ sở hữu |
| Mục đích | Tài sản, mục tiêu bảo vệ và tác động cần tránh |
| Nguồn | Rủi ro, tình huống đe dọa, nghĩa vụ hoặc yêu cầu nghiệp vụ liên quan |
| Phạm vi | Thành phần, vai trò, dữ liệu, tenant, đường truy cập và môi trường liên quan |
| Nội dung bắt buộc | Điều kiện, hành vi, kết quả và ngưỡng nếu có |
| Ngữ cảnh kiến trúc | Luồng dữ liệu, ranh giới tin cậy, danh tính và phụ thuộc cần biết |
| Giả định và ngoại lệ | Điều đang được coi là đúng; trường hợp được phép khác với hành vi thông thường |
| Tiêu chí nghiệm thu | Điều quan sát được để kết luận đạt hoặc không đạt |
| Phương pháp kiểm chứng | Kiểm thử, kiểm tra cấu hình, rà soát, diễn tập hoặc quan sát phù hợp |
| Thay đổi so với bản trước | Phần thay đổi và tác động dự kiến |
| Câu hỏi còn mở | Quyết định chưa có, người xử lý và thời hạn |

Nếu yêu cầu phụ thuộc một thuật ngữ như “quản trị viên hợp lệ”, người rà soát phải biết thuật ngữ đó được định nghĩa ở đâu và trong phiên bản nào. Không dùng một khái niệm chưa được thống nhất làm nền cho nhiều yêu cầu khác.

Ở giai đoạn yêu cầu, có thể chưa có bằng chứng triển khai. Cần có kế hoạch kiểm chứng đủ khả thi; không ép tác giả tạo ra một báo cáo test chưa tồn tại để chứng minh yêu cầu đã được viết tốt.

## 4. Các chiều chất lượng cần rà soát

### 4.1. Cần thiết và có nguồn

Mỗi yêu cầu nên có lý do tồn tại. Câu “vì bảo mật” không giúp xác định tác động khi yêu cầu không được đáp ứng.

Ví dụ:

- Rủi ro: người dùng thuộc workspace B có thể sửa quyền thành viên workspace A.
- Mục tiêu: bảo vệ ranh giới phân quyền giữa các workspace.
- Yêu cầu: kiểm tra danh tính, quyền trên workspace và đối tượng thành viên ở phía máy chủ.

Nguồn có thể là nghĩa vụ bắt buộc hoặc rủi ro đặc thù. Không cần chờ có một dòng checklist tuân thủ mới được tạo yêu cầu từ rủi ro. Ngược lại, đánh giá rủi ro nội bộ không tự cho phép bỏ một nghĩa vụ đã được xác định là bắt buộc.

### 4.2. Rõ nghĩa và thống nhất thuật ngữ

Các từ như “an toàn”, “đầy đủ”, “hợp lý”, “sớm nhất”, “ngay lập tức” và “khi cần” thường cần được cụ thể hóa.

Thay vì chỉ yêu cầu “thu hồi quyền ngay”, cần làm rõ:

- Quyền nào bị thu hồi?
- Mốc bắt đầu tính là gì?
- Ngưỡng trễ cho phép là bao nhiêu?
- Bao phủ API, giao diện, công việc nền hay các đường truy cập nào?
- Có xử lý thao tác đã bắt đầu trước khi thu hồi không?
- Đo bằng cách nào và sai số được xử lý ra sao?

Không phải yêu cầu nào cũng cần con số. “Không trả nội dung tài liệu cho người không có quyền” có tiêu chí nhị phân rõ. Không nên gắn một tỷ lệ tùy ý vào yêu cầu chỉ để nó trông có vẻ đo được.

### 4.3. Có một mệnh đề kiểm chứng rõ

Một đoạn có thể gom quá nhiều hành vi:

> Người dùng phải đăng nhập an toàn, chỉ xem dữ liệu được phép, mọi truy cập được ghi log và dữ liệu phục hồi trong thời gian phù hợp.

Khi chỉ một phần thất bại, không biết nên đánh dấu toàn đoạn ra sao hoặc ai phụ trách.

Nên tách thành những yêu cầu có kết luận kiểm chứng và chủ sở hữu rõ, đồng thời giữ liên kết giữa chúng. “Tách yêu cầu” không có nghĩa là chia mọi trường dữ liệu thành một yêu cầu riêng; đơn vị phù hợp là một nghĩa vụ hành vi có thể đánh giá độc lập.

### 4.4. Đủ điều kiện và trường hợp biên

Một yêu cầu phân quyền thường cần xét:

- Người dùng chưa xác thực.
- Người dùng đúng vai trò nhưng sai tenant hoặc sai đối tượng.
- Quyền vừa bị thu hồi.
- Hai thao tác diễn ra đồng thời.
- Tài nguyên đã đổi trạng thái.
- Thành phần kiểm tra quyền không sẵn sàng.
- Đường truy cập khác ngoài giao diện chính.
- Danh tính dịch vụ thực hiện thay người dùng.

Không nhất thiết viết mọi trường hợp trong một câu. Có thể dùng bảng quyết định, trạng thái hoặc tiêu chí nghiệm thu đi kèm, miễn phạm vi và quan hệ được giữ rõ.

### 4.5. Nhất quán với các yêu cầu khác

Những yêu cầu nghe đúng riêng lẻ vẫn có thể xung đột:

| Cặp yêu cầu | Vấn đề cần làm rõ |
| --- | --- |
| Ghi toàn bộ request để điều tra và không ghi bí mật | Trường nào được phép thu, phải loại hoặc phải che? |
| Không cho thao tác đặc quyền khi thiếu audit và luôn cho thao tác thành công khi kho audit lỗi | Hành vi khi lỗi nào được chọn cho thao tác cụ thể? |
| Thu hồi quyền trong 60 giây và tin bản sao quyền không làm mới trong nhiều phút | Thiết kế hoặc yêu cầu nào cần thay đổi? |
| Khôi phục dữ liệu từ backup và không khôi phục quyền đã bị thu hồi | Nguồn đối soát quyền sau phục hồi là gì? |
| Giữ hồ sơ lâu dài và xóa dữ liệu theo vòng đời đã xác định | Phân loại, phạm vi dữ liệu và điều kiện lưu giữ là gì? |

Người rà soát cần ghi lại xung đột và quyết định giải quyết. Không để nhóm triển khai tự chọn một cách hiểu khác nhau ở mỗi thành phần.

### 4.6. Khả thi trong kiến trúc và vận hành

Một yêu cầu có thể đúng về mục tiêu nhưng chưa khả thi với phụ thuộc hiện tại.

Ví dụ, hệ thống muốn thu hồi quyền trên mọi đường truy cập trong 60 giây, trong khi một đường truy cập nhận quyền dùng độc lập trong thời gian dài mà không kiểm tra lại.

Khi đó cần xem xét thay đổi thiết kế, cách cấp quyền, phạm vi tính năng hoặc phương án được phép khác. Không âm thầm làm yếu yêu cầu để phù hợp với việc đã triển khai.

Review không cần quyết định mọi chi tiết công nghệ. Tuy nhiên, phải có cơ sở rằng có thể thực hiện và vận hành được hành vi bắt buộc, hoặc phải ghi rõ vấn đề chưa giải quyết.

### 4.7. Kiểm chứng được và truy vết được

Một yêu cầu kiểm chứng được cần có kết quả quan sát và cách đối chiếu với tiêu chí.

Đối với yêu cầu “người không có quyền không được sửa vai trò”, chỉ kiểm tra mã HTTP là chưa đủ. Cần xác nhận trạng thái quyền không đổi và không có hiệu ứng phụ trái phép.

Đối với yêu cầu logging, “có log” chưa đủ nếu không biết nguồn, trường bắt buộc, thời gian xuất hiện và quyền truy cập.

Mỗi tiêu chí nên liên kết được đến yêu cầu, phương pháp và bằng chứng dự kiến. Khi yêu cầu thay đổi, nhóm phải biết những test, cấu hình, thiết kế và tài liệu nào có thể bị ảnh hưởng.

## 5. Ai cần tham gia và tham gia đến mức nào?

Rà soát yêu cầu là công việc phối hợp. Không nên giao toàn bộ quyết định cho người viết hoặc coi nhóm bảo mật là người duy nhất hiểu được mọi nhu cầu.

| Trách nhiệm | Đóng góp trong rà soát |
| --- | --- |
| Tác giả và chủ sở hữu yêu cầu | Giải thích mục đích, đề xuất sửa và duy trì phiên bản |
| Đại diện nghiệp vụ | Xác nhận hành vi được phép, bị cấm và tác động khi sai |
| Kiến trúc và phát triển | Phát hiện phụ thuộc, điểm thực thi, giới hạn và xung đột triển khai |
| Bảo mật | Phân tích ranh giới tin cậy, tình huống lạm dụng và rủi ro còn lại |
| Kiểm thử | Đánh giá khả năng quan sát, tiêu chí và trường hợp biên |
| Vận hành | Đánh giá cấu hình thực tế, logging, lỗi phụ thuộc và phục hồi |
| Chủ sở hữu dữ liệu hoặc nghĩa vụ | Xác nhận phân loại, vòng đời, quyền xử lý và yêu cầu áp dụng |
| Người có thẩm quyền quyết định | Chốt các lựa chọn, ngoại lệ hoặc rủi ro trong phạm vi được giao |

Với thay đổi nhỏ, một người có thể đảm nhiệm nhiều trách nhiệm. Với thay đổi tác động lớn, cần mức độc lập và sự tham gia phù hợp.

Mức độ rà soát nên dựa trên tác động, phạm vi và loại thay đổi. Sửa lỗi diễn đạt không làm đổi nghĩa có thể được xử lý gọn. Thay đổi quyền quản trị, đường xuất dữ liệu hoặc cách phục hồi cần sự xem xét sâu hơn.

## 6. Quy trình rà soát từ bản nháp đến quyết định

### Bước 1: Chốt phạm vi phiên rà soát

Ghi ID và phiên bản yêu cầu, các phần đang thay đổi, mục tiêu quyết định và người cần tham gia. Xác nhận bộ đầu vào có đủ để đánh giá không.

Nếu thiếu định nghĩa ảnh hưởng trực tiếp đến hành vi, ghi phát hiện thiếu đầu vào. Không giả định mỗi người đang hiểu giống nhau.

### Bước 2: Rà soát độc lập trước khi thảo luận

Người tham gia đọc và ghi phát hiện theo các chiều chất lượng. Cách này giúp phát hiện vấn đề trước khi cuộc thảo luận tập trung vào một phương án có sẵn.

Phát hiện nên nói rõ vị trí, vấn đề, tình huống thể hiện vấn đề và tác động. Đề xuất sửa hữu ích nhưng không thay thế việc giải thích vì sao cần sửa.

### Bước 3: Phân loại và hợp nhất phát hiện

Gộp các phát hiện trùng, phân biệt:

- Lỗi diễn đạt không làm đổi hành vi.
- Thiếu hoặc mơ hồ có thể dẫn đến các triển khai khác nhau.
- Mâu thuẫn giữa yêu cầu.
- Thiếu cơ sở về rủi ro, nghĩa vụ hoặc tính khả thi.
- Thiếu tiêu chí kiểm chứng.
- Quyết định cần người có thẩm quyền.

Mức nghiêm trọng phụ thuộc tác động của việc hiểu sai hoặc thiếu yêu cầu. Không chỉ dựa vào số dòng cần sửa.

### Bước 4: Giải quyết vấn đề và câu hỏi quyết định

Dùng tình huống cụ thể để thảo luận: ai gọi, gọi vào đâu, dữ liệu ở trạng thái nào, điều gì phải xảy ra và điều gì không được xảy ra.

Nếu có nhiều lựa chọn hợp lệ, ghi lựa chọn được chốt cùng lý do và hệ quả. Nếu chưa thể chốt, xác định người xử lý và thời hạn; không chuyển câu hỏi mở thành một giả định ngầm.

### Bước 5: Sửa yêu cầu và liên kết tiêu chí

Tác giả cập nhật nội dung, bảng quyết định, phạm vi và tiêu chí liên quan. Nếu việc sửa làm thay đổi ý nghĩa, phải kiểm tra tác động đến các yêu cầu và bên sử dụng khác.

Người rà soát cần xem phần đã sửa trong ngữ cảnh đầy đủ. Một thay đổi làm rõ câu này vẫn có thể tạo mâu thuẫn với câu khác.

### Bước 6: Đóng phát hiện bằng cơ sở rõ ràng

Một phát hiện được đóng khi đã có bằng chứng giải quyết phù hợp, chẳng hạn nội dung mới, quyết định phạm vi hoặc phương án đã được người có thẩm quyền chấp thuận.

“Đã trao đổi” hay “sẽ xử lý khi code” chưa phải cơ sở đóng một vấn đề đang quyết định hành vi bắt buộc.

### Bước 7: Chốt phiên bản và truyền đạt

Ghi quyết định, người quyết định, phiên bản, ngày và giới hạn. Thông báo cho các bên thiết kế, triển khai, kiểm thử và vận hành về nội dung tác động đến họ theo quy trình dự án.

Việc chốt phiên bản tạo mốc để quản lý thay đổi. Nó không biến yêu cầu thành bất biến; các thay đổi sau đó cần có lịch sử và đánh giá tác động.

## 7. Ví dụ xuyên suốt: rà soát yêu cầu quản trị quyền workspace

### 7.1. Bối cảnh và bản nháp

Một ứng dụng quản lý tài liệu có nhiều workspace. Trong ví dụ này:

- `owner` được quản trị thành viên của workspace.
- `editor` được sửa tài liệu nhưng không được quản trị thành viên.
- `viewer` được đọc tài liệu nhưng không được sửa hoặc quản trị thành viên.
- Workspace đang hoạt động phải có ít nhất một owner đang hoạt động.
- Giao diện quản trị gọi API phía máy chủ; ẩn nút trên giao diện không phải cơ chế cấp quyền.
- Đường sửa tài liệu có thể dùng bản sao quyền tạm thời; đường quản trị thành viên cần kiểm tra quyền hiện hành tại điểm quyết định thay đổi.

Bản nháp:

> Quản trị viên có thể thay đổi quyền người dùng an toàn. Quyền bị thu hồi phải mất hiệu lực nhanh chóng, mọi thay đổi phải được ghi log đầy đủ và có thể phục hồi khi xảy ra lỗi.

Đoạn này chứa nhiều nghĩa vụ với các tiêu chí khác nhau. Người rà soát không nên chỉ thay “nhanh chóng” bằng một con số rồi coi công việc đã xong.

### 7.2. Phát hiện trong phiên rà soát

| ID phát hiện | Vấn đề | Tình huống thể hiện | Hành động cần có |
| --- | --- | --- | --- |
| RV-01 | “Quản trị viên” chưa xác định phạm vi | Owner workspace A gửi mã thành viên workspace B | Đặc tả quyền trên workspace và thành viên |
| RV-02 | Chưa có quy tắc giữ owner | Hai owner đồng thời hạ quyền của chính mình | Đặc tả điều kiện sau chuyển trạng thái và thử cạnh tranh |
| RV-03 | Thu hồi “nhanh chóng” chưa kiểm chứng được | Editor dùng phiên cũ tiếp tục sửa tài liệu | Chốt phạm vi, mốc tính, ngưỡng và hành vi đang xử lý |
| RV-04 | “Log đầy đủ” chưa rõ dữ liệu và độ bền | Quyền đã đổi nhưng tiến trình lỗi trước khi ghi audit | Đặc tả quan hệ giữa thay đổi đã commit và sự kiện audit |
| RV-05 | Chính sách audit có thể làm lộ bí mật | Middleware ghi token và toàn bộ request | Đặc tả trường cho phép, trường cấm và kiểm chứng |
| RV-06 | Phục hồi chưa xét quyền đã thu hồi | Backup cũ chứa vai trò owner đã bị hạ quyền | Chọn nguồn đối soát và điều kiện mở lại thao tác nhạy cảm |

Mỗi phát hiện cho thấy một hành vi hoặc quyết định còn thiếu. Không có phát hiện nào được giải quyết chỉ bằng câu “đội phát triển sẽ xử lý đúng”.

### 7.3. SEC-WS-01: quyền thay đổi vai trò được kiểm tra phía máy chủ

**Yêu cầu minh họa:**

> Với workspace ở trạng thái hoạt động, API thay đổi vai trò thành viên chỉ chấp nhận yêu cầu từ người dùng đã xác thực có vai trò owner còn hiệu lực trong chính workspace đó tại điểm quyết định chuyển trạng thái. Thành viên đích phải thuộc cùng workspace. Người không thỏa điều kiện phải bị từ chối và không làm thay đổi quyền.

Trong ví dụ, điểm vào của thao tác là:

```text
PATCH /workspaces/{workspaceId}/members/{memberId}/role
```

Phải liệt kê thêm các điểm vào nếu sản phẩm có import, bulk API, công việc nền hoặc kênh quản trị khác thực hiện cùng hành vi. Không tự suy ra rằng kiểm tra endpoint này bao phủ các điểm vào chưa được mô tả.

**Tiêu chí nghiệm thu:**

- Owner đúng workspace đổi được vai trò khi các điều kiện nghiệp vụ khác đều thỏa.
- Editor và viewer bị từ chối khi gọi API trực tiếp.
- Owner workspace A không đổi được quyền thành viên workspace B.
- Thay đổi `workspaceId` hoặc `memberId` không vượt qua kiểm tra đối tượng.
- Một người vừa mất quyền owner không dùng được quyền cũ để đổi vai trò ở đường quản trị thành viên.
- Khi bị từ chối, dữ liệu quyền và hiệu ứng nghiệp vụ không bị thay đổi trái phép.

Ở đây, “quyền còn hiệu lực” phải dựa vào nguồn quyền có thẩm quyền của hệ thống. Một claim cũ trong phiên không tự chứng minh người dùng vẫn là owner tại điểm ra quyết định.

### 7.4. SEC-WS-02: không làm mất owner cuối cùng

**Yêu cầu minh họa:**

> Sau mỗi thay đổi vai trò thành viên được commit trên workspace đang hoạt động, workspace phải còn ít nhất một owner đang hoạt động. Điều kiện này phải được giữ khi nhiều thay đổi diễn ra đồng thời.

**Tiêu chí nghiệm thu:**

1. Workspace có một owner: hạ quyền owner đó phải bị từ chối.
2. Workspace có hai owner: một owner có thể được hạ quyền nếu điều kiện quyền gọi hợp lệ.
3. Hai yêu cầu đồng thời hạ quyền hai owner không được làm kết quả cuối cùng có số owner bằng không.
4. Sau lỗi hoặc thử lại, dữ liệu và audit phản ánh đúng thay đổi thực sự đã được commit.

Yêu cầu này xác định điều kiện phải giữ, không buộc chọn sẵn một cơ chế khóa hay một loại cơ sở dữ liệu.

Người rà soát cũng cần phân biệt trường hợp workspace đang hoạt động với quy trình đóng workspace. Ví dụ này không đặc tả quy trình đóng; không được dùng ngoại lệ chưa xác định để bỏ quy tắc trên workspace đang hoạt động.

### 7.5. SEC-WS-03: giới hạn độ trễ thu hồi quyền sửa tài liệu

Giả sử nhóm đã chấp thuận ngưỡng 60 giây cho đường sửa tài liệu có bản sao quyền tạm thời. Đây là giá trị minh họa của sản phẩm, không phải ngưỡng chung cho mọi hệ thống.

**Yêu cầu minh họa:**

> Khi vai trò của một thành viên chuyển từ editor sang viewer, mọi yêu cầu sửa tài liệu mới đi tới điểm kiểm tra quyền từ thời điểm t0 + 60 giây trở đi phải bị từ chối theo vai trò viewer. t0 là thời điểm thay đổi vai trò được commit tại nguồn quyền có thẩm quyền.

Phạm vi của yêu cầu này là các đường sửa tài liệu đã liệt kê cho sản phẩm. Nó không cho phép tiếp tục dùng quyền owner cũ trên API quản trị thành viên của SEC-WS-01.

Trong ví dụ, nhóm cũng chốt: yêu cầu sửa đã qua điểm kiểm tra quyền trước hạn có thể hoàn tất theo quyết định đã cấp. Nếu nghiệp vụ cần hủy cả thao tác đang xử lý, phải có yêu cầu bổ sung về điểm kiểm tra lại và hành vi khi hủy.

**Tiêu chí nghiệm thu:**

- Dùng phiên đã tồn tại trước khi hạ quyền để thử sửa tài liệu.
- Thực hiện trên từng đường sửa trong phạm vi, gồm các nút dịch vụ có bản sao quyền nếu có.
- Đối chiếu t0 và thời điểm quyết định quyền bằng phép đo kiểm soát được sai số.
- Từ hạn đã chốt, yêu cầu mới bị từ chối và không sửa nội dung tài liệu.
- Quyền đọc của viewer vẫn hoạt động đúng; không nhầm thu hồi quyền sửa với thu hồi mọi quyền.
- Kiểm tra cả khi nguồn làm mới quyền bị lỗi theo hành vi lỗi đã đặc tả.

Nếu phép đo phải ghép đồng hồ từ nhiều hệ thống, cần biết sai lệch và cách xử lý sai số. Một kết quả sát ngưỡng nhưng không kiểm soát được sai số chưa đủ cơ sở để kết luận đạt.

Tình huống lỗi làm mới quyền không được để mở. Nhóm phải xác định liệu việc kiểm tra dùng bản sao nào còn được phép, đến thời điểm nào phải từ chối và tác động đến khả dụng.

### 7.6. SEC-WS-04: audit gắn với thay đổi quyền đã commit

**Yêu cầu minh họa:**

> Mỗi thay đổi vai trò đã commit phải có một sự kiện audit bền vững tương ứng, chứa actor, workspace, thành viên đích, vai trò trước và sau, thời điểm, kết quả và correlation ID. Hệ thống không được commit thay đổi quyền nếu không bảo đảm được ràng buộc này.

Trong ví dụ, độ bền tối thiểu phải bao phủ lỗi dừng tiến trình ứng dụng: sau khi tiến trình khởi động lại, cả thay đổi đã commit và sự kiện tương ứng vẫn đối chiếu được. Các mức lỗi hạ tầng khác cần được xác định trong yêu cầu vận hành liên quan.

Bản ghi không được chứa password, token phiên, bí mật tích hợp hoặc nội dung tài liệu. Quyền đọc và thay đổi kho audit phải được đặc tả riêng.

**Tiêu chí nghiệm thu:**

- Với mỗi thay đổi thành công, đối chiếu đủ các trường và đúng vai trò trước/sau.
- Gây lỗi tại các điểm trước và sau commit, rồi kiểm tra lại sau khi khởi động tiến trình.
- Xác nhận không có thay đổi đã commit bị thiếu sự kiện tương ứng.
- Dùng marker tổng hợp để phát hiện trường dữ liệu bị cấm trong các nguồn log thuộc phạm vi.
- Xác nhận nơi tiếp nhận audit tập trung có thể chậm hoặc gián đoạn mà không làm mất sự kiện đã được lưu bền vững.

Ràng buộc này không bắt buộc hệ thống phải gọi đồng bộ một kho log tập trung trong mỗi request. Thiết kế có thể chọn cách lưu và chuyển tiếp phù hợp, miễn đáp ứng hành vi và độ bền đã được chốt.

Yêu cầu audit cho các lần bị từ chối, thời hạn chuyển tiếp, quyền xem và thời hạn lưu giữ cần có tiêu chí riêng trong đặc tả đầy đủ. Bốn yêu cầu minh họa ở đây không phải toàn bộ đặc tả của tính năng.

### 7.7. Phát hiện phục hồi chưa đủ cơ sở để đóng

Sau khi sửa các yêu cầu quyền và audit, nhóm vẫn chưa xác định nguồn nào đáng tin cậy để đối soát vai trò sau khi khôi phục backup cũ.

Không nên đóng RV-06 chỉ bằng câu “sẽ kiểm tra lại quyền sau restore”. Cần chốt:

- Nguồn lịch sử hoặc trạng thái nào còn tồn tại độc lập với dữ liệu đang phục hồi.
- Ai chịu trách nhiệm đối soát và cách xác định quyền hiệu lực.
- Điểm nào phải giữ đóng trước khi xác nhận dữ liệu quyền đủ tin cậy.
- Hành vi khi không có đủ thông tin để tái lập quyền.
- Kịch bản diễn tập chứng minh quyền đã thu hồi không tự trở lại.

Kết quả rà soát có thể xác nhận một số yêu cầu đã rõ, nhưng gói đầy đủ vẫn cần sửa nếu vấn đề phục hồi ảnh hưởng trực tiếp đến mục tiêu bảo vệ.

Đây là quyết định về chất lượng và độ đầy đủ của đặc tả. Nó không phải kết luận hệ thống đã được kiểm thử hoặc phục hồi thành công.

## 8. Ghi phát hiện để người khác có thể xử lý

Một phát hiện tốt mô tả được vấn đề mà không cần người đọc nhớ nội dung cuộc họp.

Mẫu minh họa:

```yaml
reviewFindingId: RV-03
requirementId: SEC-WS-03
reviewedVersion: "0.2"
category: "Thiếu tiêu chí và hành vi lỗi"
problem: "Chưa định nghĩa hành vi khi không làm mới được bản sao quyền"
scenario: "Editor bị hạ quyền nhưng một nút dịch vụ không kết nối được nguồn quyền"
impact: "Nút dịch vụ có thể cho sửa tài liệu quá thời hạn thu hồi"
requiredDecision:
  - "Giới hạn sử dụng bản sao quyền"
  - "Hành vi khi quá giới hạn mà chưa làm mới được"
owner: "Chủ sở hữu yêu cầu quyền"
status: OPEN
resolution: null
closureBasis: null
```

Các trạng thái ở đây chỉ là quy ước minh họa cho hồ sơ rà soát yêu cầu.

Khi đóng phát hiện, cần bổ sung quyết định và cơ sở:

```text
Resolution:
  Đã bổ sung thời hạn sử dụng bản sao và hành vi từ chối khi quá hạn.
  Tiêu chí nghiệm thu có kịch bản mất kết nối nguồn quyền.

Closure basis:
  Phiên bản SEC-WS-03 v0.3 và tiêu chí AC-WS-03-FAILURE
  đã được các bên chịu trách nhiệm xác nhận.
```

Nếu có người phản đối hoặc giới hạn chưa xử lý, hồ sơ phải phản ánh điều đó. Không ghi “đồng thuận” khi chỉ có tác giả phản hồi mà chưa có xác nhận cần thiết.

## 9. Quyết định rà soát và quản lý phiên bản

Dự án có thể chọn trạng thái riêng. Một mô hình đơn giản:

| Trạng thái | Ý nghĩa |
| --- | --- |
| DRAFT | Đang soạn, chưa đủ cơ sở chốt |
| IN_REVIEW | Phiên bản cụ thể đang được rà soát |
| CHANGES_REQUESTED | Có phát hiện phải giải quyết trước khi chốt |
| ACCEPTED | Nội dung đã được chấp thuận trong phạm vi ghi nhận |
| BASELINED | Phiên bản đã được đưa vào mốc quản lý thay đổi |
| SUPERSEDED | Đã có phiên bản thay thế, cần giữ lịch sử |

ACCEPTED hoặc BASELINED là trạng thái của đặc tả trong ví dụ này. Trạng thái hệ thống đã đáp ứng yêu cầu phải được quản lý bằng kết quả kiểm chứng riêng.

Không nên dùng “chấp thuận có điều kiện” để làm mờ một vấn đề đang quyết định hành vi bảo mật cốt lõi. Nếu dự án dùng loại quyết định này, phải ghi rõ điều kiện, phần việc được phép tiếp tục, người phụ trách, thời hạn và điểm phải kiểm tra lại.

Đối với ví dụ workspace, nếu nguồn đối soát sau phục hồi chưa được chọn và mục tiêu bảo vệ vẫn yêu cầu xử lý tình huống đó, không được tuyên bố toàn bộ gói đã đủ. Có thể cho phép một phần thiết kế tiếp tục trong phạm vi được quyết định, đồng thời giữ phát hiện mở.

Một bản ghi quyết định nên có:

- Danh sách yêu cầu và phiên bản được xét.
- Người tham gia, người quyết định và thẩm quyền tương ứng.
- Kết quả, lý do và giới hạn.
- Phát hiện đã đóng, còn mở hoặc được xử lý qua quyết định khác.
- Các hành động, chủ sở hữu và thời hạn.
- Liên kết tới phiên bản thay thế hoặc điều kiện rà soát lại.

## 10. Rà soát lại khi thay đổi

Một thay đổi nhỏ về câu chữ có thể làm đổi phạm vi bảo vệ. Cần xem tác động về nghĩa, không chỉ số dòng thay đổi.

Ví dụ:

| Thay đổi | Câu hỏi cần rà soát lại |
| --- | --- |
| “Mọi yêu cầu sửa” thành “yêu cầu từ giao diện web” | API trực tiếp, client khác hoặc công việc nền có bị bỏ ngoài không? |
| “Quyền hiện hành” thành “quyền trong phiên” | Vai trò đã bị thu hồi còn được dùng bao lâu? |
| Tăng thời hạn bản sao quyền | Có xung đột với ngưỡng thu hồi không? |
| Thêm thao tác thay đổi hàng loạt | Quy tắc owner cuối cùng và audit áp dụng từng phần hay toàn bộ? |
| Thêm danh tính dịch vụ | Ai cấp quyền, giới hạn theo đối tượng và ai chịu trách nhiệm? |
| Chuyển audit sang bất đồng bộ | Sự kiện có được lưu bền vững trước khi báo thành công không? |
| Thay luồng phục hồi | Có làm quyền cũ hoặc bí mật cũ hoạt động trở lại không? |

Sau khi xác định tác động, cập nhật liên kết đến rủi ro, thiết kế, tiêu chí, kiểm thử, kế hoạch bằng chứng và tài liệu vận hành liên quan.

Các kết quả kiểm chứng cũ không tự áp dụng cho hành vi mới. Cần xác định phần nào vẫn còn giá trị và phần nào phải kiểm tra lại.

## 11. Những lỗi làm review trở thành hình thức

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ kiểm tra chính tả và mẫu trình bày | Bỏ qua hành vi mơ hồ hoặc thiếu | Dùng tình huống hợp lệ, bị cấm, lỗi và đồng thời |
| Chốt công nghệ trước khi rõ mục tiêu | Chứng minh có công cụ thay vì có bảo vệ | Làm rõ hành vi và tiêu chí trước, rồi đánh giá phương án |
| Chỉ hỏi “có làm được không?” | Yêu cầu có thể khả thi nhưng không xử lý đúng rủi ro | Kiểm tra nguồn, tác động và tình huống đe dọa |
| Dùng một ngưỡng cho mọi hệ thống | Không phù hợp mức rủi ro và kiến trúc | Chốt giá trị có cơ sở và phạm vi đo |
| Để kiểm thử tự suy ra tiêu chí | Triển khai và kiểm thử dùng hai cách hiểu | Viết tiêu chí trong quá trình rà soát |
| Đóng phát hiện vì có ticket | Chưa có quyết định hoặc nội dung sửa | Yêu cầu cơ sở đóng gắn với phiên bản |
| Đồng nhất phê duyệt yêu cầu với nghiệm thu hệ thống | Kết luận vượt mức bằng chứng | Quản lý riêng trạng thái đặc tả và kết quả kiểm chứng |
| Giao vấn đề phục hồi cho “vận hành xử lý” | Không có nguồn hoặc quy tắc tái lập an toàn | Chốt điều kiện và trách nhiệm ngay trong yêu cầu liên quan |
| Tự bỏ nghĩa vụ vì khó triển khai | Tạo khoảng trống không có thẩm quyền | Đưa ra quyết định đúng cấp và phương án được phép |
| Không ghi lý do quyết định | Nhóm sau phải tranh luận lại hoặc sửa sai | Lưu cơ sở, giới hạn và phiên bản |

Số lượng bình luận không phản ánh trực tiếp chất lượng rà soát. Một phát hiện đúng về ranh giới quyền có thể quan trọng hơn nhiều chỉnh sửa hình thức. Cũng không nên dùng số phát hiện ít để kết luận quy trình tốt nếu người rà soát chưa có đủ đầu vào.

## 12. Checklist trước khi chốt phiên bản yêu cầu

- [ ] Có ID, phiên bản, chủ sở hữu và nguồn nhu cầu rõ.
- [ ] Mục tiêu bảo vệ và tác động cần tránh được giải thích.
- [ ] Thuật ngữ, vai trò, dữ liệu và trạng thái quan trọng được định nghĩa.
- [ ] Phạm vi gồm các đường truy cập và thành phần thực sự liên quan.
- [ ] Mỗi yêu cầu có mệnh đề hành vi đủ rõ để đánh giá.
- [ ] Trường hợp được phép và bị cấm đều có tiêu chí phù hợp.
- [ ] Điều kiện lỗi, đồng thời, thử lại và chuyển trạng thái được xét theo kiến trúc.
- [ ] Ngưỡng có đơn vị, mốc đo, phạm vi và cách xử lý sai số khi cần.
- [ ] Không có mâu thuẫn chưa giải quyết với logging, dữ liệu, khả dụng hoặc phục hồi.
- [ ] Giả định quan trọng có cơ sở và người chịu trách nhiệm.
- [ ] Có phương pháp kiểm chứng khả thi cùng bằng chứng dự kiến.
- [ ] Các phát hiện có cơ sở đóng hoặc được giữ mở theo quyết định rõ.
- [ ] Quyết định đúng thẩm quyền và không thay thế kết quả kiểm chứng hệ thống.
- [ ] Lịch sử, tác động thay đổi và điều kiện rà soát lại được giữ.
