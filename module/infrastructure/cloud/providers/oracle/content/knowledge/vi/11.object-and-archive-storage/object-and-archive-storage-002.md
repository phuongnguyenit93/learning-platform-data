# Standard, Infrequent Access và Archive tiers

## Mục tiêu bài học

Trong OCI Object Storage, chọn storage tier là chọn cách lưu giữ và truy xuất object phù hợp với vòng đời dữ liệu. Một mức có chi phí lưu trữ thấp hơn chưa chắc có tổng chi phí thấp hơn, và dữ liệu còn nguyên chưa chắc sẵn sàng để tải xuống ngay khi ứng dụng cần.

Bài thuộc chương **Object Storage và Archive Storage**, module **CLOUD_PROVIDERS_ORACLE**. Nội dung kết nối lưu trữ object với IAM, ứng dụng, backup, tự động hóa vòng đời và kiểm soát chi phí trên OCI.

Sau bài này, bạn có thể:

- Phân biệt Standard, Infrequent Access và Archive theo cách truy xuất và mục đích sử dụng.
- Chọn tier từ yêu cầu truy cập, thời gian khôi phục và thời gian giữ dữ liệu.
- Nhận diện chi phí lưu trữ, truy xuất, thao tác, lưu tối thiểu và truyền dữ liệu.
- Giải thích vì sao restore Archive là một quy trình bất đồng bộ, có thời gian chờ và cửa sổ truy xuất.
- Phân biệt chuyển tier, lifecycle policy, Auto-Tiering, retention và versioning.
- Thiết kế ứng dụng cùng kế hoạch kiểm thử để không đưa dữ liệu bắt buộc truy cập ngay vào luồng cần chờ restore.

Bài không dùng một biểu giá, thời gian tối thiểu hoặc thời gian restore cố định làm cam kết dịch vụ. Khi triển khai, phải đối chiếu các giá trị, giới hạn và khả năng chuyển tier được OCI hỗ trợ cho đúng bucket, object và region.

## 1. Object vẫn là object, nhưng cách truy xuất thay đổi

Một object được định danh trong namespace và bucket bằng object name, cùng version khi cần phân biệt phiên bản. Storage tier là thuộc tính liên quan đến cách lưu trữ và cung cấp dữ liệu, không phải quyền truy cập hoặc một phần mở rộng của tên file.

Ví dụ:

```text
Bucket: company-documents
Object name: reports/2026/11/summary.pdf
```

Các dấu `/` trong object name giúp tổ chức theo prefix; chúng không tạo filesystem POSIX với thao tác mount và quyền thư mục như File Storage. Việc di chuyển dữ liệu sang tier khác cũng không tự thay đổi quyền IAM hoặc làm bucket trở thành public.

Cần phân biệt cấu hình storage tier của bucket với tier của object và các phép chuyển được dịch vụ hỗ trợ. Không mặc định có thể đổi loại bucket hoặc chuyển mọi object theo mọi hướng bằng cùng một thao tác. Trước khi tự động hóa, xác nhận loại bucket, cấu hình mặc định và luồng đổi tier/copy tương ứng.

## 2. So sánh ba tier

| Tiêu chí | Standard | Infrequent Access | Archive |
| --- | --- | --- | --- |
| Ý định sử dụng | Dữ liệu được dùng thường xuyên hoặc cần truy xuất trực tiếp | Dữ liệu ít dùng nhưng vẫn cần truy xuất trực tiếp khi có yêu cầu | Dữ liệu ít dùng, giữ lâu và chấp nhận chờ trước khi đọc |
| Có cần quy trình restore Archive trước khi đọc? | Không | Không | Có |
| Yếu tố chi phí nổi bật | Dung lượng lưu, thao tác và các chi phí liên quan | Dung lượng lưu, truy xuất và điều kiện lưu tối thiểu | Dung lượng lưu, restore/truy xuất và điều kiện lưu tối thiểu |
| Đường phục vụ ứng dụng | Có thể nằm trong luồng tải object trực tiếp | Có thể nằm trong luồng tải object trực tiếp | Cần luồng yêu cầu chuẩn bị dữ liệu và kiểm tra trạng thái |
| Ví dụ phù hợp | Nội dung đang sử dụng, dữ liệu xử lý hiện tại | Báo cáo cũ đôi khi cần tải ngay | Bản lưu dài hạn, hồ sơ ít được yêu cầu và có thời gian chờ phù hợp |

**Infrequent Access không có nghĩa là phải chờ restore như Archive.** Khác biệt quan trọng của nó là mô hình chi phí và mục đích truy cập ít thường xuyên, không phải biến mọi lần tải thành một tác vụ phục hồi ngoại tuyến.

**Archive không phải một phiên bản Standard có giá lưu thấp hơn nhưng mọi hành vi giữ nguyên.** Ứng dụng phải xử lý bước restore và khoảng thời gian object được cung cấp để truy xuất.

## 3. Khi nào chọn Standard?

Standard phù hợp khi dữ liệu nằm trong luồng sử dụng hiện tại hoặc việc truy cập không thể phụ thuộc vào một bước chuẩn bị Archive.

Các ví dụ:

- Tài liệu người dùng thường xuyên xem hoặc tải xuống.
- Dữ liệu đầu vào cho pipeline đang hoạt động.
- Kết quả xử lý vừa tạo và sẽ được nhiều thành phần sử dụng.
- Một phần dữ liệu backup cần sẵn sàng cho phương án phục hồi nhanh.

Tần suất truy cập không phải tiêu chí duy nhất. Một object rất hiếm khi được đọc nhưng phải sẵn sàng ngay khi xảy ra sự cố vẫn không phù hợp với Archive nếu thời gian chờ restore vượt yêu cầu.

Standard cũng là một ứng viên để bắt đầu quan sát khi chưa có đủ dữ liệu về hành vi truy cập. Sau khi có bằng chứng, có thể đánh giá tier khác theo cơ chế được hỗ trợ. Không đổi tier chỉ vì object đã cũ mà chưa biết nó còn nằm trong luồng nghiệp vụ nào.

## 4. Khi nào chọn Infrequent Access?

### 4.1. Ít truy cập nhưng cần lấy dữ liệu trực tiếp

Infrequent Access, viết tắt IA, phù hợp với dữ liệu được đọc ít hơn, nhưng khi cần vẫn phải truy xuất trực tiếp thay vì chờ restore Archive.

Ví dụ:

- Báo cáo tháng trước thỉnh thoảng được tải để đối chiếu.
- Tài liệu dự án đã kết thúc nhưng vẫn có yêu cầu truy cập tức thời.
- Dữ liệu dự phòng có tỷ lệ đọc thấp nhưng cần cho một luồng xử lý không thể chờ chuẩn bị Archive.

Không nên diễn giải IA là “chậm hơn một chút” rồi tự giả định mức latency cụ thể. Cần đối chiếu đặc tính dịch vụ và đo luồng ứng dụng; tiêu chí phân biệt trong thiết kế là truy xuất trực tiếp cùng cấu trúc chi phí phù hợp với truy cập ít.

### 4.2. Chi phí truy xuất có thể làm mất lợi ích lưu trữ

Một object ít được mở nhưng mỗi lần được đọc toàn bộ với kích thước lớn vẫn có thể phát sinh lượng truy xuất đáng kể. Ngược lại, nhiều lần đọc một phần nhỏ tạo ra hồ sơ chi phí khác.

Cần quan sát:

- Tổng dung lượng đọc theo thời gian.
- Số thao tác đọc và cách ứng dụng chia request.
- Có tác vụ quét dữ liệu, kiểm tra định kỳ hoặc phân tích nền không.
- Có cache làm giảm lượng truy xuất thực xuống Object Storage không.
- Các đợt tải lại hàng loạt khi ứng dụng khởi động hoặc khi mất cache.

Đừng chỉ đếm số người dùng nhấn nút tải. Các tác vụ nội bộ cũng là nguồn truy xuất.

### 4.3. Lưu tối thiểu là điều kiện tính phí, không mặc nhiên là khóa xóa

IA có điều kiện về thời gian lưu tối thiểu theo quy định dịch vụ. Việc xóa hoặc chuyển dữ liệu sớm có thể phát sinh chi phí tương ứng theo chính sách áp dụng.

Điều này khác retention rule dùng để hạn chế thay đổi/xóa dữ liệu. Một object có thể được phép xóa về mặt quyền nhưng vẫn có chi phí do chưa đáp ứng thời gian lưu tối thiểu.

Trước khi áp dụng lifecycle, xác nhận thời điểm bắt đầu tính thời gian tối thiểu và tác động của chuyển tier, ghi đè hoặc xóa đối với cấu hình đang dùng. Không suy ra mọi bộ đếm đều bắt đầu từ cùng thời điểm tạo object ban đầu.

## 5. Khi nào chọn Archive?

### 5.1. Dữ liệu dài hạn và có thể chờ

Archive phù hợp khi nhu cầu đọc thấp, thời gian giữ đủ dài và nghiệp vụ chấp nhận một giai đoạn chuẩn bị trước khi lấy nội dung.

Ví dụ:

- Hồ sơ lịch sử chỉ được yêu cầu trong các đợt kiểm tra có kế hoạch.
- Những bản backup cũ không thuộc tập phục hồi nhanh hằng ngày.
- Dữ liệu gốc được giữ lâu để có thể xử lý lại trong một tình huống hiếm gặp.

Không phải mọi dữ liệu có tên “backup” hoặc “audit” đều phù hợp Archive. Nếu yêu cầu điều tra cần tải dữ liệu trong vài phút hoặc mục tiêu phục hồi không đủ thời gian chờ, phải thiết kế một lớp dữ liệu sẵn sàng hơn hoặc chọn phương án khác.

### 5.2. Restore Archive không phải khôi phục một phiên bản bị xóa

Trong ngữ cảnh này, restore là yêu cầu làm object đang lưu Archive có thể truy xuất trong một khoảng thời gian theo cơ chế dịch vụ. Nó không có nghĩa tự quay về phiên bản trước, sửa dữ liệu hỏng hoặc phục hồi một object đã bị xóa mà không còn nguồn phục hồi.

Versioning, backup và retention giải quyết các mục tiêu khác nhau. Một hệ thống cần đủ cả cách giữ bản dữ liệu đúng và cách lấy dữ liệu từ tier đang lưu.

### 5.3. Quy trình truy xuất Archive

Một luồng khái niệm:

```text
Xác định đúng bucket, object và version cần dùng
  -> kiểm tra tier và trạng thái archival
  -> gửi yêu cầu restore với khoảng truy xuất được hỗ trợ
  -> theo dõi tác vụ/trạng thái bằng cơ chế phù hợp
  -> khi object sẵn sàng, tải dữ liệu trong cửa sổ cho phép
  -> kiểm tra nội dung và lưu kết quả tại nơi cần dùng
```

Tên trạng thái, trường API và thời hạn cụ thể phải dùng theo giao diện OCI tương ứng. Sơ đồ trên mô tả hành vi, không phải schema request có thể gửi trực tiếp.

Yêu cầu restore được chấp nhận chưa có nghĩa object đã sẵn sàng tải. Ứng dụng cần phân biệt ít nhất ba tình huống: chưa yêu cầu chuẩn bị, đang chuẩn bị và đã có thể đọc.

### 5.4. Cửa sổ truy xuất có giới hạn

Khi restore hoàn tất, dữ liệu được cung cấp trong khoảng thời gian truy xuất theo yêu cầu và giới hạn dịch vụ. Luồng xử lý phải đủ thời gian để tải, kiểm tra và hoàn tất công việc trước khi khoảng đó hết hạn.

Restore không tự chuyển object Archive thành Standard vĩnh viễn. Khi cửa sổ hết, việc truy xuất lại có thể cần một yêu cầu restore mới.

Nếu dữ liệu vừa phục hồi sẽ tiếp tục được sử dụng thường xuyên, đánh giá luồng copy/ghi thành object ở tier phù hợp theo khả năng hỗ trợ. Đừng dựa vào việc liên tục gia hạn hoặc lặp restore như một cách thay thế mặc định cho chuyển mô hình lưu trữ.

Không xóa bản nguồn chỉ vì thao tác copy đã bắt đầu. Cần xác minh bản đích, nội dung, quyền và yêu cầu giữ dữ liệu trước khi quyết định vòng đời bản cũ.

## 6. Chọn tier theo thời gian phục hồi của toàn hệ thống

### 6.1. Tính cả quá trình, không chỉ một thao tác

Đối với dữ liệu Archive:

```text
Thời gian lấy dữ liệu sử dụng được
  = thời gian phát hiện/xác định dữ liệu
  + thời gian chờ restore
  + thời gian tải xuống
  + thời gian kiểm tra
  + thời gian nhập/khôi phục vào ứng dụng, nếu có
```

Đây là mô hình lập kế hoạch. Các bước có thể song song một phần tùy giải pháp, nhưng không được bỏ qua chúng khi đánh giá thời gian khôi phục.

Ví dụ, một bản backup cơ sở dữ liệu còn nguyên trên Archive vẫn chưa thể phục vụ truy vấn ngay sau restore object. Có thể còn cần tải nhiều phần, chuẩn bị môi trường database, áp dụng log và kiểm tra tính nhất quán.

### 6.2. RPO khác RTO

- **RPO** phản ánh mức mất dữ liệu chấp nhận được theo thời gian.
- **RTO** phản ánh thời gian khôi phục dịch vụ cần đáp ứng.

Chọn tier không tự bảo đảm hai mục tiêu này. RPO còn phụ thuộc chu kỳ backup/sao chép và dữ liệu đã lưu thành công. RTO còn phụ thuộc restore, mạng, Compute, phần mềm và quy trình vận hành.

Với cơ sở dữ liệu Oracle, phải kiểm tra cả chuỗi phục hồi: backup nền, các phần tăng dần, log và metadata cần thiết theo công cụ đang dùng. Không đưa một thành phần bắt buộc của chuỗi vào Archive rồi chỉ tính thời gian lấy phần còn ở Standard.

### 6.3. Mô hình nhiều lớp dữ liệu

Một phương án minh họa:

| Nhóm dữ liệu | Yêu cầu | Tier ứng viên |
| --- | --- | --- |
| Dữ liệu hoạt động | Truy xuất thường xuyên, trực tiếp | Standard |
| Dữ liệu cũ nhưng có thể bị yêu cầu ngay | Ít đọc, không chờ restore | Infrequent Access nếu tổng chi phí phù hợp |
| Dữ liệu lịch sử dài hạn | Hiếm đọc, có quy trình chờ | Archive |

Đây là cách phân nhóm để đánh giá, không phải luật tuổi dữ liệu áp dụng cho mọi hệ thống. Cần xác định thời điểm chuyển dựa vào bằng chứng truy cập và nghĩa vụ lưu giữ.

## 7. Đánh giá tổng chi phí

### 7.1. Những thành phần cần tính

Một mô hình khái niệm:

```text
Tổng chi phí
  = lưu trữ theo dung lượng và thời gian
  + truy xuất/restore theo tier và hoạt động thực tế
  + thao tác API
  + truyền dữ liệu theo đường đi áp dụng
  + điều chỉnh do thời gian lưu tối thiểu, nếu có
  + tài nguyên phục vụ xử lý và bản sao liên quan
```

Không phải mọi hạng mục đều phát sinh giống nhau trong mọi tier hoặc đường truy cập. Dùng biểu giá thực tế để xác định phần nào áp dụng, tránh tính trùng một khoản đã được bao gồm.

Cũng cần tính các bản version, bản copy và dữ liệu phục vụ phục hồi. Một bản tải về hoặc copy sang nơi khác có thể tạo chi phí lưu trữ/Compute riêng mà bảng giá tier nguồn không thể hiện hết.

### 7.2. Ví dụ điểm hòa vốn với số liệu giả lập

Giả sử một mô hình toán học đã tính được:

- Chuyển một tập dữ liệu sang tier ít truy cập giúp giảm 100 đơn vị chi phí lưu mỗi tháng.
- Phần chi phí truy xuất tăng thêm là 0,02 đơn vị cho mỗi GiB đọc.
- Các khoản khác được giả định không đổi chỉ để minh họa.

Khi đó:

```text
Lượng đọc tại điểm hòa vốn
  = 100 / 0,02
  = 5.000 GiB mỗi tháng
```

Nếu lượng đọc tăng thêm vượt mức đó, khoản tiết kiệm lưu trữ không còn đủ bù trong mô hình giả định. Đây không phải biểu giá OCI và không dùng để dự toán thực tế; nó minh họa cách đặt câu hỏi với dữ liệu chi phí thật.

Nếu có lưu tối thiểu, API, network hoặc restore phát sinh thêm, phải đưa chúng vào mô hình trước khi kết luận.

### 7.3. Đọc nhiều hơn dự báo là rủi ro thực tế

Những tình huống làm chi phí truy xuất thay đổi:

- Quét toàn bộ dữ liệu để phân tích hoặc kiểm tra.
- Chuyển ứng dụng sang môi trường mới và nạp lại cache.
- Sự cố khiến nhiều instance cùng tải lại cùng một tập dữ liệu.
- Tổ chức nhận yêu cầu đối chiếu hàng loạt.
- Restore Archive lặp lại do cửa sổ truy xuất không đủ dài.

Dự toán nên có cả kịch bản thông thường và kịch bản phục hồi hoặc truy xuất tăng mạnh, không chỉ một tháng ít hoạt động.

## 8. Lifecycle policy và Auto-Tiering

### 8.1. Lifecycle policy tự động hóa theo quy tắc

Lifecycle policy có thể tự động hóa các hành động được dịch vụ hỗ trợ như chuyển tier hoặc xử lý vòng đời object. Trước khi áp dụng, xác nhận bộ lọc, cách tính tuổi và đối tượng mà rule tác động.

Các câu hỏi cần trả lời:

- Rule áp dụng bucket nào, prefix nào và các version nào?
- Thời điểm nào được dùng để đánh giá điều kiện?
- Có dữ liệu bắt buộc truy xuất trực tiếp nằm trong cùng phạm vi không?
- Chuyển tier có phù hợp thời gian lưu tối thiểu không?
- Retention rule hoặc chính sách giữ dữ liệu có hạn chế hành động không?
- Có rule khác tạo tác động trái với mục tiêu hiện tại không?

Các hành động lifecycle được xử lý theo cơ chế nền của dịch vụ; không dùng một mốc lifecycle như cam kết chuyển tier đúng một giây xác định.

### 8.2. Prefix là phạm vi kỹ thuật, không tự là phân loại nghiệp vụ đúng

Ví dụ:

```text
active-documents/...
closed-projects/...
long-term-records/...
```

Các prefix dễ đọc giúp thiết kế rule, nhưng một file bị ghi nhầm vào `long-term-records/` vẫn có thể bị xử lý theo rule ở đó. Cần kiểm soát cách ứng dụng đặt object name và sự thay đổi yêu cầu theo thời gian.

Đừng dùng cùng một prefix cho cả nội dung người dùng cần tải ngay và bản lưu chấp nhận chờ nếu không có cơ chế phân biệt đủ rõ.

### 8.3. Auto-Tiering không thay thế quyết định đưa dữ liệu vào Archive

Auto-Tiering của OCI dùng cho việc tự động tối ưu giữa Standard và Infrequent Access theo cơ chế được hỗ trợ. Không coi đây là cơ chế tự đưa dữ liệu vào Archive và tự thiết kế luôn quy trình restore cho ứng dụng.

Trước khi bật, xác nhận điều kiện áp dụng, hành vi theo dõi truy cập và khả năng phối hợp với lifecycle đang có. Tránh hai cơ chế hoặc quy tắc đưa ra ý định trái nhau mà không hiểu điều kiện ưu tiên.

Auto-Tiering cũng không thay thế việc đo mục tiêu ứng dụng, kiểm tra chi phí hoặc hiểu yêu cầu lưu giữ của tổ chức.

### 8.4. Last-Modified không phải lần đọc cuối

Thời điểm sửa object và thời điểm tải nội dung là hai khái niệm khác nhau. Một object không đổi nhiều tháng vẫn có thể được tải mỗi ngày.

Không lấy `Last-Modified` làm bằng chứng dữ liệu không còn được truy cập. Dùng nguồn quan sát phù hợp như số liệu ứng dụng, báo cáo hoạt động hoặc cơ chế theo dõi được dịch vụ hỗ trợ, với phạm vi và giới hạn đã hiểu rõ.

## 9. Thiết kế ứng dụng cho dữ liệu Archive

### 9.1. Tách yêu cầu chuẩn bị khỏi tải nội dung

Với ứng dụng Java cung cấp tài liệu lịch sử, luồng tải Archive không nên giữ một HTTP request đồng bộ chờ toàn bộ quá trình chuẩn bị.

Một thiết kế có thể đánh giá:

1. Người dùng yêu cầu truy cập tài liệu.
2. Backend xác thực người dùng và kiểm tra quyền với tài liệu.
3. Backend kiểm tra tier/trạng thái của đúng object hoặc version.
4. Nếu cần restore, tạo hoặc dùng lại một tác vụ chuẩn bị đã có.
5. Trả trạng thái đang xử lý cùng định danh tác vụ.
6. Worker kiểm tra tiến trình có giãn nhịp, giới hạn retry và thời hạn.
7. Khi sẵn sàng, cung cấp luồng tải có kiểm soát trong cửa sổ truy xuất.
8. Theo dõi lỗi, hết hạn và việc có cần yêu cầu lại hay chuyển sang tier khác.

Đây là kiến trúc minh họa, không phải yêu cầu triển khai một API theo schema cố định.

### 9.2. Tránh restore lặp do nhiều request cùng đến

Nếu nhiều người cùng yêu cầu một object, ứng dụng nên phối hợp theo định danh bucket/object/version và trạng thái tác vụ. Không gửi yêu cầu restore mới vô hạn cho mỗi lần người dùng bấm tải.

Cần xử lý trường hợp worker khởi động lại, request bị timeout nhưng tác vụ đã được chấp nhận, hoặc cửa sổ truy xuất đã hết. Retry phải nhận diện trạng thái hiện tại thay vì giả định lần trước chưa thực hiện gì.

### 9.3. Quyền và bảo vệ dữ liệu vẫn phải áp dụng

Service chuẩn bị dữ liệu cần quyền phù hợp để đọc thông tin, yêu cầu restore và lấy nội dung theo chức năng được giao. Không dùng quyền quản trị toàn tenancy làm mặc định.

Các URL hoặc phương thức chia sẻ có thời hạn, nếu được dùng, không thay thế bước restore và không cho phép bỏ kiểm tra quyền người dùng nghiệp vụ. Không chuyển bucket sang public chỉ để đơn giản hóa tải một tài liệu đã restore.

Nếu dùng khóa mã hóa do khách hàng quản lý, cần giữ khả năng sử dụng khóa và quyền liên quan trong suốt thời gian lưu dữ liệu. Giữ object dài hạn mà mất khả năng giải mã không đáp ứng mục tiêu phục hồi.

## 10. Kế hoạch thử nghiệm và chuyển tier

### 10.1. Dùng tập dữ liệu đại diện

Chọn các object thử có đặc điểm giống dữ liệu thật về kích thước, cách truy cập và yêu cầu bảo vệ. Lưu một manifest chứa định danh, version khi cần, kích thước và giá trị kiểm tra nội dung theo cơ chế phù hợp.

Không mặc định ETag luôn là cùng một loại checksum cho mọi cách upload và cấu hình. Dùng cơ chế xác minh được hỗ trợ và hiểu ý nghĩa giá trị đang so sánh.

### 10.2. Các tình huống cần thử

| Tình huống | Điều cần quan sát | Mục đích |
| --- | --- | --- |
| Đọc Standard | Thời gian, lỗi, lượng dữ liệu truyền | Có baseline cho luồng truy cập trực tiếp |
| Đọc Infrequent Access | Khả năng tải và lượng truy xuất phát sinh | Kiểm chứng yêu cầu truy cập cùng mô hình chi phí |
| Đọc Archive khi chưa restore | Trạng thái/lỗi mà dịch vụ trả về | Ứng dụng nhận diện đúng nhu cầu chuẩn bị |
| Restore rồi tải | Thời gian đến sẵn sàng, cửa sổ và tốc độ tải | Đánh giá có đáp ứng RTO không |
| Hết cửa sổ truy xuất | Hành vi tải và cách yêu cầu lại | Tránh coi restore là chuyển tier vĩnh viễn |
| Nhiều request đồng thời | Số tác vụ/yêu cầu và trạng thái chia sẻ | Kiểm soát restore lặp và trải nghiệm người dùng |
| Quyền thiếu hoặc khóa không dùng được | Lỗi rõ ràng, cảnh báo và khả năng xử lý | Phân biệt quyền với lỗi tier hoặc mất dữ liệu |
| Lifecycle trên tập thử | Đúng phạm vi và hành động thực tế | Tránh chuyển nhầm dữ liệu cần trực tiếp |
| Phục hồi toàn ứng dụng | Thời gian tải, kiểm tra, nhập dữ liệu và khởi động | Không chỉ đo riêng bước restore object |

Ghi các giá trị thực tế cùng điều kiện đo. Một lần restore thành công chứng minh luồng hoạt động trong tình huống đó, chưa phải bảo đảm mọi kích thước hoặc mọi đợt tải đều có cùng thời gian.

### 10.3. Mở rộng phạm vi sau khi có bằng chứng

Trước khi chuyển nhiều dữ liệu, xác nhận ứng dụng và người vận hành biết tier nào cần chờ, rule áp dụng vào đâu và cách lấy lại dữ liệu.

Theo dõi số liệu sau chuyển: dung lượng từng nhóm, lượng đọc, tác vụ restore, thời gian phục hồi và chi phí thực. Đối chiếu với dự báo để điều chỉnh phân loại thay vì mặc định “đã chuyển sang tier rẻ hơn” là công việc hoàn tất.

Không xóa các nguồn còn cần cho rollback, retention hoặc chuỗi phục hồi chỉ vì tập thử tải được một vài object.

## 11. Phiếu lựa chọn và tự kiểm tra

Hoàn thành phiếu sau cho mỗi nhóm dữ liệu:

| Nội dung | Kết quả cần ghi |
| --- | --- |
| Phạm vi | Namespace, bucket, prefix, object/version liên quan |
| Vai trò dữ liệu | Dữ liệu chính, bản sao, cache, backup hay hồ sơ lưu giữ |
| Truy cập | Lượng đọc, tần suất, kích thước, batch và truy xuất đột biến |
| Mục tiêu thời gian | Có cần đọc trực tiếp không, thời gian phục hồi toàn luồng |
| Thời gian giữ | Yêu cầu nghiệp vụ, retention và điều kiện lưu tối thiểu |
| Tier đề xuất | Standard, IA hoặc Archive cùng lý do |
| Cơ chế chuyển | Thao tác được hỗ trợ, lifecycle hoặc Auto-Tiering phù hợp |
| Quyền và khóa | Danh tính đọc/restore, chia sẻ và khả năng giải mã |
| Tổng chi phí | Lưu, truy xuất/restore, API, network, bản sao và điều chỉnh tối thiểu |
| Bằng chứng | Kết quả đọc, restore, hết cửa sổ và phục hồi ứng dụng |
| Chủ sở hữu | Người quản lý rule, theo dõi chi phí và xử lý yêu cầu lấy dữ liệu |

Tự kiểm tra:

1. Vì sao Infrequent Access không đồng nghĩa phải restore trước mỗi lần đọc?
2. Một object rất ít dùng nhưng phải sẵn sàng ngay có phù hợp Archive không? Cần biết thêm gì?
3. Restore Archive có tự chuyển object thành Standard vĩnh viễn không?
4. Thời gian lấy bản backup từ Archive khác thời gian phục hồi cơ sở dữ liệu thế nào?
5. Điều kiện lưu tối thiểu và retention rule khác nhau ở điểm nào?
6. Vì sao tổng lượng dữ liệu đọc quan trọng hơn việc chỉ đếm số lần người dùng mở tài liệu?
7. Auto-Tiering có thay thế việc quyết định và thiết kế quy trình Archive không?
8. Tại sao không thể dùng Last-Modified làm bằng chứng về lần truy cập cuối?
9. Nếu cửa sổ truy xuất hết trước khi hoàn tất tải, ứng dụng cần nhận diện và xử lý những trạng thái nào?
10. Trước khi chuyển một tập dữ liệu lớn, cần bằng chứng gì về quyền, nội dung, thời gian phục hồi và chi phí?

Đầu ra của bài thực hành là một lựa chọn tier có căn cứ cho từng nhóm dữ liệu, kèm quy trình lấy dữ liệu đáp ứng thời gian nghiệp vụ và mô hình chi phí đã được kiểm chứng.
