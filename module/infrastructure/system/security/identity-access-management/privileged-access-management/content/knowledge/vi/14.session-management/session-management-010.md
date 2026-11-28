# Session evidence retention

## Mục tiêu bài học

Trong chương **Session management**, session evidence retention là việc quy định và thực thi vòng đời lưu giữ bằng chứng của phiên đặc quyền: thu nhận, bảo vệ, tra cứu, khôi phục, giữ lại khi cần và xóa theo chính sách.

Trong **Privileged Access Management (PAM)**, bằng chứng có thể gắn với tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Nó giúp giải thích việc sử dụng quyền, kiểm tra least privilege và JIT/JEA, liên kết credential từ vault với phiên ở đích, hỗ trợ kiểm toán và ứng phó sự cố.

**Giữ một tệp ghi hình không tự chứng minh đã giữ đủ bằng chứng.** Cần biết tệp thuộc phiên nào, danh tính và quyết định nào liên quan, nội dung có đầy đủ không, có bị thay đổi không và còn đọc được trong suốt thời gian cần thiết không.

Sau bài học, bạn có thể:

- Phân loại bằng chứng phiên và xác định phạm vi cần lưu.
- Thiết kế chính sách lưu giữ có mốc tính thời gian, owner và ngoại lệ rõ ràng.
- Bảo vệ tính bí mật, toàn vẹn và khả năng truy xuất của bằng chứng.
- Liên kết recording với yêu cầu, danh tính, credential và hệ thống đích.
- Quản lý bản sao, dữ liệu lưu trữ dài hạn, khóa và định dạng phát lại.
- Giữ bằng chứng phục vụ điều tra và xác minh xóa khi hết hạn.

## 1. Bằng chứng phiên gồm những gì?

Tùy đường truy cập và khả năng giải pháp, một hồ sơ phiên có thể gồm:

| Loại | Ví dụ | Câu hỏi có thể hỗ trợ |
| --- | --- | --- |
| Metadata phiên | ID, thời gian, đích, giao thức, broker | Phiên nào đã được thiết lập và diễn ra ở đâu? |
| Bằng chứng danh tính | Principal ban đầu, tài khoản đích, ngữ cảnh được xác minh | Ai yêu cầu và ai thực thi tại đích? |
| Quyết định truy cập | Policy, phiên bản, phê duyệt, phạm vi JIT | Vì sao phiên được phép? |
| Bản ghi nội dung | Hình ảnh, dữ liệu tương tác hoặc transcript theo khả năng | Những hoạt động nào quan sát được? |
| Audit hệ thống đích | Xác thực, thao tác, thay quyền hoặc kết quả | Đích ghi nhận điều gì? |
| Vòng đời phiên | Bắt đầu, reconnect, timeout, yêu cầu kết thúc, xác nhận | Phiên đã được xử lý như thế nào? |
| Vòng đời credential | Tham chiếu phiên bản, lần cấp, rotation hoặc thu hồi | Credential nào liên quan và đã được quản lý ra sao? |
| Hồ sơ xử lý | Cảnh báo, nhận xét, xuất dữ liệu, quyết định điều tra | Bằng chứng đã được sử dụng và bảo quản thế nào? |

Không phải mọi phiên đều có video hoặc transcript. Không nên hứa có nội dung mà giao thức và tích hợp không thực sự ghi được.

### Bằng chứng có phạm vi quan sát

Một bản ghi màn hình không tự chứng minh mọi hành động ở hệ thống đích. Một transcript có thể không bao phủ thao tác qua đường khác. Audit database có thể chỉ ghi tài khoản chung, chưa biết người dùng ban đầu.

Chính sách cần nêu cả dữ liệu có và giới hạn của nó. Lưu thật lâu một tập dữ liệu thiếu không làm tập đó trở nên đầy đủ.

## 2. Lưu giữ để phục vụ mục đích nào?

Những mục đích điển hình gồm:

- Kiểm tra truy cập có đúng phê duyệt và phạm vi không.
- Review việc dùng đặc quyền và các ngoại lệ.
- Điều tra sự kiện được phát hiện sau thời điểm phiên xảy ra.
- Đối soát hành động giữa PAM, vault và hệ thống đích.
- Xác minh timeout, thu hồi hoặc thao tác ứng phó.
- Đánh giá hiệu quả kiểm soát và khắc phục khoảng trống.

Cần chuyển mục đích thành yêu cầu dữ liệu cụ thể.

Ví dụ, nếu cần xác định ai thực hiện thay đổi, giữ video nhưng mất liên kết giữa người yêu cầu và tài khoản đích có thể không đáp ứng mục tiêu. Nếu cần kiểm tra việc kết thúc phiên, chỉ giữ thời điểm đóng cửa sổ client cũng chưa đủ.

### Không chọn thời hạn theo dung lượng còn trống

Dung lượng là một ràng buộc cần lập kế hoạch, không phải nguồn duy nhất quyết định thời gian lưu.

Thời hạn phải dựa trên mục tiêu đã xác nhận, mức nhạy cảm, thời gian thường cần để phát hiện và xử lý vấn đề, cùng những yêu cầu thực tế áp dụng cho tổ chức.

Không có một số ngày chung phù hợp cho mọi loại bằng chứng PAM.

## 3. Phân loại trước khi đặt retention

Có thể phân loại theo:

- Mức đặc quyền và độ nhạy cảm của tài nguyên.
- Loại phiên hoặc nhiệm vụ.
- Môi trường.
- Loại bằng chứng và khả năng tái tạo.
- Mức nhạy cảm của nội dung được ghi.
- Sự kiện hoặc hồ sơ điều tra liên quan.

Một phiên đọc trạng thái ở môi trường thử nghiệm có thể có profile khác phiên quản trị production. Metadata, recording và audit cũng có thể có thời hạn khác nhau nếu mục đích được đáp ứng.

### Giữ đủ liên kết

Nếu recording được giữ lâu hơn metadata cần để hiểu nó, tệp có thể trở thành dữ liệu khó sử dụng. Nếu metadata còn nhưng khóa giải mã đã mất, bản ghi nội dung không còn truy xuất được.

Cần xác định những thành phần phụ thuộc phải còn hiệu lực cùng bằng chứng, thay vì quản lý từng loại dữ liệu như một kho độc lập.

### Tránh gom mọi thứ vào một nhóm không thể quản lý

Nếu cùng một đối tượng lưu trữ chứa dữ liệu của nhiều profile, việc xóa một phần hoặc giữ theo một yêu cầu riêng có thể khó thực hiện.

Phân vùng, cách đóng gói, khóa và index cần hỗ trợ đơn vị quản lý đã chọn. Đừng chỉ đặt nhãn retention rồi giả định hệ thống có thể thực thi theo từng phiên.

## 4. Hợp đồng chính sách lưu giữ

Một profile retention nên trả lời:

| Nhóm | Nội dung |
| --- | --- |
| Phạm vi | Loại phiên, tài nguyên, môi trường và loại bằng chứng |
| Mục đích | Những câu hỏi hoặc quy trình cần phục vụ |
| Thời hạn | Khoảng lưu và cơ sở của quyết định |
| Mốc tính | Từ sự kiện nào và nguồn thời gian nào |
| Truy xuất | Ai được tìm, xem, phát lại và xuất |
| Bảo vệ | Mã hóa, toàn vẹn, quyền quản trị và bản sao |
| Khôi phục | Thời gian truy xuất mục tiêu và phụ thuộc cần có |
| Giữ riêng | Điều kiện, người quyết định và cách kết thúc việc giữ |
| Xóa | Phạm vi bản sao, kiểm tra điều kiện và bằng chứng |
| Trách nhiệm | Owner chính sách, owner bằng chứng và đội thực thi |

### Mốc tính phải rõ

Những mốc có thể được cân nhắc gồm thời điểm phiên kết thúc theo định nghĩa nguồn hoặc recording được hoàn tất. Mỗi lựa chọn cần xử lý tình huống bất thường.

Ví dụ:

- Nếu tính từ lúc hoàn tất recording, bản upload treo phải có cách phát hiện và xử lý.
- Nếu tính từ sự kiện kết thúc, cần biết sự kiện nói về broker hay phiên đích.
- Nếu không có sự kiện kết thúc, phải có quy tắc xử lý chứ không tự lưu mãi hoặc xóa ngay.

Một sự kiện broker đóng phiên có thể là mốc của profile, nhưng không vì vậy trở thành bằng chứng mọi tiến trình ở đích đã dừng.

### Không tự đặt lại hạn

Chuyển dữ liệu sang kho lạnh, phát lại hoặc nhận một bản gửi lại không nên âm thầm đặt lại thời hạn, trừ khi chính sách có quy tắc rõ cho trường hợp đó.

Khi profile thay đổi, cần quyết định tác động tới dữ liệu đã có. Không coi cấu hình mới tự động được phép rút ngắn mọi cam kết lưu trước đó.

## 5. Kiến trúc vòng đời bằng chứng

~~~mermaid
flowchart TD
    Capture[Thu nhận phiên và audit] --> Buffer[Bộ đệm được bảo vệ]
    Buffer --> Ingest[Tiếp nhận và kiểm tra]
    Ingest --> Store[Kho bằng chứng]
    Store --> Catalog[Metadata và liên kết]
    Store --> Archive[Lưu trữ dài hạn]
    Catalog --> Retrieve[Tra cứu và phát lại]
    Archive --> Retrieve
    Store --> Hold[Giữ phục vụ điều tra]
    Archive --> Hold
    Store --> Expiry[Đánh giá hết hạn]
    Archive --> Expiry
    Hold --> Expiry
    Expiry --> Delete[Xóa có kiểm soát]
    Delete --> Receipt[Bằng chứng xử lý]
~~~

Sơ đồ thể hiện trách nhiệm logic. Một giải pháp có thể gộp nhiều khối, nhưng vẫn cần biết thành phần nào chịu trách nhiệm tại mỗi giai đoạn.

### Từ thu nhận đến lưu bền vững

Bộ đệm không nên xóa dữ liệu chỉ vì đã gửi một yêu cầu upload. Cần hiểu xác nhận từ nơi nhận có nghĩa gì: đã nhận ở đầu vào, đã ghi bền vững hay đã kiểm tra đầy đủ.

Khi có lỗi, cần retry có kiểm soát và tránh tạo các bản ghi mâu thuẫn.

### Từ lưu đến sử dụng được

Một đối tượng đã được ghi vào kho nhưng chưa có metadata đúng có thể không tìm thấy. Một recording thiếu đoạn có thể vẫn hiện trên giao diện.

Cần tách trạng thái lưu, toàn vẹn, lập chỉ mục, độ đầy đủ và khả năng phát lại theo yêu cầu, không chỉ dùng một cờ “uploaded”.

## 6. Liên kết và định danh bằng chứng

Một manifest hoặc hồ sơ liên kết có thể cần:

- ID phiên PAM.
- ID yêu cầu và quyết định truy cập.
- Principal ban đầu và tài khoản đích.
- ID tài nguyên, tenant và môi trường.
- Broker, node hoặc nguồn tạo.
- Thời điểm, múi giờ hoặc chuẩn thời gian thống nhất.
- Phiên bản policy và schema.
- Danh sách thành phần recording, thứ tự và trạng thái.
- Tham chiếu audit tại đích.
- Profile retention, mốc tính và hạn tương ứng.
- Trạng thái giữ riêng hoặc việc xóa.
- Thông tin kiểm tra toàn vẹn và cách truy xuất khóa.

Không ghi password, token hoặc khóa riêng vào manifest.

### Định danh theo nguồn và thời điểm

Tên tài khoản hoặc tên người dùng có thể thay đổi. Cần ID và ngữ cảnh đủ ổn định để tránh gộp nhầm giữa môi trường hoặc những lần tồn tại khác nhau.

Cũng cần giữ khả năng giải thích vai trò và thẩm quyền tại thời điểm phiên. Owner hiện tại không nhất thiết là người chịu trách nhiệm cho một quyết định cũ.

### Tham chiếu credential không phải lưu bí mật

Audit có thể giữ ID phiên bản credential đã dùng mà không giữ giá trị. Mục tiêu là giải thích vòng đời, không tạo một cách lấy lại mật khẩu đã thu hồi.

Retention của bằng chứng không kéo dài hiệu lực của credential và không thay thế rotation.

## 7. Tính toàn vẹn và độ đầy đủ

### 7.1. Kiểm tra nội dung không bị thay đổi

Có thể dùng hash cho các đoạn và manifest, chữ ký hoặc cơ chế lưu có bảo vệ tùy thiết kế. Cần biết giá trị kiểm chứng được giữ ở đâu và ai có thể thay nó.

Nếu người sửa tệp cũng dễ dàng sửa mọi hash tham chiếu, khả năng phát hiện thay đổi có thể không đạt mục tiêu.

Chữ ký cần đi cùng quản lý khóa và quy trình xác minh. Nó không tự chứng minh nguồn ghi chưa bị kiểm soát trước khi tạo bản ghi.

### 7.2. Kiểm tra recording có đủ thành phần

Với recording chia đoạn, cần biết:

- Đoạn nào được kỳ vọng.
- Thứ tự và khoảng thời gian tương ứng.
- Đoạn nào đã được tiếp nhận.
- Có kết thúc hợp lệ hoặc manifest cuối không.
- Có khoảng trống do lỗi hoặc điều kiện ghi không.

Một tập đoạn đều có hash đúng vẫn có thể thiếu phần cuối. Cần bằng chứng về trạng thái kết thúc và phạm vi thu nhận, không chỉ tính hash từng tệp.

### 7.3. Giới hạn của nguồn

Không thể chứng minh mọi hoạt động từ một nguồn vốn chỉ ghi một phần. Có thể cần đối chiếu audit ở đích, metadata phiên và sức khỏe bộ thu.

Nếu việc ghi bị gián đoạn hoặc được tạm dừng theo một quy trình, cần thể hiện khoảng đó. Không tạo cảm giác recording liên tục đầy đủ khi thực tế không phải vậy.

## 8. Bảo vệ bí mật và dữ liệu nhạy cảm

Bản ghi phiên có thể chứa:

- Mật khẩu bị gõ hoặc hiển thị ngoài ý định.
- Token trong câu lệnh hoặc kết quả.
- Nội dung tệp cấu hình.
- Dữ liệu được truy vấn từ hệ thống đích.
- Thông tin cá nhân hoặc nội bộ.
- Sơ đồ hạ tầng, địa chỉ và đường quyền.

Vì vậy, kho bằng chứng cũng là tài nguyên nhạy cảm.

### Giảm thu thập không cần thiết

Cần xác định loại dữ liệu cần cho mục đích, khả năng che hoặc loại dữ liệu và giới hạn của kỹ thuật đó.

Không mặc định mọi giao thức đều che được mọi bí mật. Dữ liệu có thể xuất hiện trong đầu ra, màn hình, tham số hoặc thông báo lỗi.

Nếu phải tạo một bản đã che để chia sẻ, nên quản lý nó như bản dẫn xuất với liên kết tới nguồn, quy trình biến đổi và quyền phù hợp. Không ghi đè nguồn rồi làm mất khả năng giải thích thay đổi.

### Mã hóa và khóa

Bằng chứng cần được bảo vệ khi truyền và lưu theo thiết kế. Khóa giải mã phải còn dùng được trong thời gian cần truy xuất, đồng thời được giới hạn quyền.

Đổi khóa mã hóa của kho không đồng nghĩa thu hồi mật khẩu đã vô tình xuất hiện trong recording. Nếu phát hiện bí mật bị lộ, cần xử lý vòng đời credential và sự cố riêng.

### Quyền xem không tự theo quyền quản trị đích

Người từng có quyền mở một phiên không tự có quyền đọc mọi recording. Chủ sở hữu tài nguyên cũng không nên mặc định được xem mọi dữ liệu thuộc các phiên khác.

Quyền tra cứu, xem nội dung, xuất và quản trị kho cần gắn với mục đích cụ thể.

## 9. Truy cập, phát lại và xuất bằng chứng

| Hành động | Điều cần kiểm soát |
| --- | --- |
| Tìm kiếm metadata | Phạm vi tài nguyên, danh tính và thông tin được hiển thị |
| Phát lại nội dung | Mục đích, quyền xem và mức dữ liệu nhạy cảm |
| Tải hoặc xuất | Người nhận, nơi lưu, bản sao và vòng đời |
| Ghi nhận nhận xét | Danh tính, thời gian và không làm thay đổi nguồn |
| Thay policy hoặc quyền | Thẩm quyền, kiểm soát thay đổi và audit |
| Xóa | Điều kiện hết hạn, trạng thái giữ riêng và phạm vi thực thi |

Những quyền này có thể thuộc các vai trò khác nhau. Một người được tra metadata không nhất thiết được xuất toàn bộ nội dung.

### Dấu vết tiếp cận bằng chứng

Nên ghi ai đã truy vấn, xem, xuất hoặc thay quyền đối với bằng chứng nhạy cảm. Log không cần sao chép chính nội dung recording.

Việc xuất cần tạo được định danh bộ bằng chứng, phạm vi, bộ lọc, thời điểm, người thực hiện và người hoặc kênh nhận được chấp nhận.

### Bản xuất là một bản sao cần quản lý

Retention tại kho chính không tự xóa bản đã tải xuống hoặc được chuyển sang nơi khác.

Cần biết những bản xuất nào thuộc phạm vi kiểm soát, ai giữ và chính sách nào áp dụng. Không tuyên bố đã xóa mọi bản sao nếu chỉ xóa đối tượng gốc.

Với bản sao nằm ngoài khả năng quản lý, phải ghi giới hạn và xử lý theo quy trình, không giả định thao tác thu hồi quyền xem sẽ làm bản sao biến mất.

## 10. Giữ riêng phục vụ điều tra

Một sự kiện có thể được phát hiện khi bằng chứng gần hết hạn. Cần cơ chế giữ lại theo quyết định có thẩm quyền để tránh xóa theo lịch trong lúc đang cần phân tích.

Một hồ sơ giữ nên có:

- Mã hồ sơ hoặc mục đích.
- Người quyết định và phạm vi thẩm quyền.
- Tập phiên, tài nguyên, thời gian và loại bằng chứng.
- Thời điểm có hiệu lực.
- Người chịu trách nhiệm review.
- Điều kiện và quyết định kết thúc.
- Những bản sao, khóa và liên kết cần bảo vệ.

### Giữ có phạm vi

Không nên mặc định giữ toàn bộ kho vô thời hạn vì một phiên có liên quan. Cần phạm vi đủ cho công việc và khả năng mở rộng khi có bằng chứng mới.

Metadata phục vụ tìm kiếm, manifest và khóa cần thiết cũng phải được giữ cùng nội dung. Giữ video nhưng để liên kết hoặc khóa hết hạn có thể làm mất giá trị sử dụng.

### Xung đột với công việc xóa

Trước bước xóa không thể đảo ngược, hệ thống cần kiểm tra trạng thái giữ và phiên bản policy còn hiệu lực.

Cần cơ chế phối hợp để tránh một worker xóa đang dùng quyết định cũ trong khi lệnh giữ mới đã có hiệu lực. Một lần kiểm tra rất sớm rồi để công việc chạy độc lập có thể không đủ.

Nếu dữ liệu đã bị xóa trước quyết định giữ, cần ghi rõ thực tế; không có cơ chế nào tạo lại bằng chứng chưa được bảo toàn chỉ bằng việc đổi nhãn.

## 11. Lưu trữ dài hạn và khả năng phát lại

Chuyển sang kho lạnh có thể giảm một phần chi phí nhưng tạo thêm yêu cầu vận hành.

Cần giữ:

- Định dạng và phiên bản dữ liệu.
- Manifest và thứ tự thành phần.
- Metadata để tìm đúng đối tượng.
- Khóa và cấu hình giải mã.
- Công cụ hoặc khả năng phát lại tương thích.
- Quyền và quy trình khôi phục.
- Bằng chứng kiểm tra toàn vẹn.

Một đối tượng còn tồn tại nhưng không có cách giải mã hoặc đọc định dạng chưa đáp ứng mục tiêu truy xuất.

### Không tự đổi thời hạn khi chuyển tầng

Bản ghi cần giữ mốc và policy ban đầu hoặc quyết định thay đổi được chấp nhận. Chuyển tầng không nên khởi động lại đồng hồ retention một cách ngầm định.

### Chuyển định dạng

Nếu cần chuyển định dạng để duy trì khả năng đọc, phải giữ bằng chứng về nguồn, công cụ hoặc phiên bản biến đổi, kiểm tra kết quả và policy cho bản nguồn lẫn bản dẫn xuất.

Hash của hai định dạng khác nhau không giống nhau là điều bình thường. Cần liên kết và xác minh quá trình, không kết luận dữ liệu hỏng chỉ vì hash thay đổi sau một phép biến đổi có chủ ý.

Mức giữ bản nguồn phụ thuộc mục tiêu và quyết định chính sách, không tự xóa nguồn sau chuyển đổi mà chưa xác nhận.

## 12. Backup và khôi phục

Backup bảo vệ khả năng phục hồi, còn retention xác định dữ liệu nào cần tồn tại và đến khi nào. Hai cơ chế phải phối hợp nhưng không phải một.

### Những mục tiêu cần xác định

- **RPO:** mức mất dữ liệu có thể chấp nhận trong kịch bản phục hồi.
- **RTO:** thời gian mục tiêu để khôi phục khả năng truy xuất cần thiết.
- Phạm vi được bảo vệ bởi backup hoặc nhân bản.
- Khóa, catalog, manifest và quyền cần có.
- Khả năng phát lại sau phục hồi.
- Cách nhận diện dữ liệu thiếu, lặp hoặc xung đột.

Mở được kho dữ liệu chưa chứng minh người điều tra tìm và phát lại được phiên cần thiết trong thời gian yêu cầu.

### Khôi phục không làm sống lại dữ liệu đã phải xóa

Một backup cũ có thể chứa bằng chứng đã hết hạn và được xóa khỏi kho chính.

Quy trình khôi phục cần áp dụng lại trạng thái xóa, giữ riêng và quyền liên quan trước khi công bố dữ liệu cho sử dụng theo thiết kế. Có thể cần hồ sơ tối thiểu về những đối tượng đã xử lý để đối soát.

Không dùng restore làm cách vô tình đặt lại retention.

### Kiểm tra khôi phục

Cần xác minh cả dữ liệu, metadata, khóa và player hoặc công cụ đọc. Có thể kiểm tra mẫu đại diện theo profile và rủi ro, cùng kiểm tra toàn vẹn theo đơn vị dữ liệu đã thiết kế.

Không cần phát lại mọi bản ghi trong mỗi lần kiểm tra, nhưng phải có cơ sở cho phạm vi và độ bao phủ kết luận.

## 13. Xóa khi hết hạn

Một luồng xóa có kiểm soát có thể gồm:

1. Xác định đối tượng đã đủ điều kiện theo policy.
2. Kiểm tra trạng thái giữ và những phụ thuộc còn cần.
3. Xác nhận thẩm quyền hoặc cơ chế tự động được chấp nhận.
4. Thực hiện trên đúng phạm vi.
5. Theo dõi từng nơi lưu và lỗi.
6. Kiểm tra kết quả.
7. Ghi bằng chứng tối thiểu về quyết định và thao tác.

### Xác định phạm vi bản sao

| Thành phần | Câu hỏi |
| --- | --- |
| Kho chính | Nội dung và phiên bản cũ đã được xử lý chưa? |
| Nhân bản | Dữ liệu còn ở node hoặc vùng khác không? |
| Kho lạnh | Đối tượng lưu trữ dài hạn còn tồn tại không? |
| Index và cache | Có còn nội dung hoặc metadata nhạy cảm ngoài ý định không? |
| Bản xuất được quản lý | Ai chịu trách nhiệm xử lý và xác nhận? |
| Backup | Khi nào dữ liệu hết khỏi vòng đời backup, và restore xử lý thế nào? |
| Khóa | Việc giữ hoặc xóa khóa có phù hợp với các dữ liệu khác không? |

Không nên báo “đã xóa mọi nơi” khi thực tế chỉ gửi một yêu cầu xóa khỏi catalog.

### Dữ liệu dùng chung và deduplication

Nếu nhiều phiên tham chiếu chung một thành phần lưu trữ, xóa tham chiếu của một phiên không tự xóa nội dung vật lý.

Ngược lại, xóa chunk dùng chung có thể làm hỏng bằng chứng còn trong hạn hoặc đang được giữ.

Cần theo dõi các tham chiếu và điều kiện lưu của chúng. Phải phân biệt xóa logic, mất khả năng truy cập và xóa vật lý theo cơ chế thực tế.

### Xóa bằng khóa có giới hạn

Hủy khóa có thể được dùng trong một số thiết kế để làm dữ liệu không còn giải mã được, nhưng phải hiểu phạm vi khóa, bản sao khóa và những bản dữ liệu đã xuất ở dạng khác.

Nếu khóa dùng chung, hủy nó có thể làm mất dữ liệu vẫn cần giữ. Nếu còn bản rõ hoặc khóa ngoài phạm vi, không thể suy ra mọi bản sao đều không thể truy cập.

Không coi một thao tác quản lý khóa là bằng chứng tuyệt đối cho mọi dạng xóa.

## 14. Ước lượng dung lượng theo profile

Một mô hình đơn giản:

~~~text
Dung lượng nội dung mỗi ngày
    = số phiên mỗi ngày
    × thời lượng trung bình
    × tốc độ dữ liệu đầu ra trung bình

Dung lượng cơ sở theo retention
    = dung lượng mỗi ngày
    × số ngày giả định
~~~

Cần dùng dữ liệu đo từ loại recording thực tế. Phiên đồ họa, terminal, metadata và audit có đặc tính khác nhau.

### Ví dụ tính toán

Giả sử một nhóm recording có:

- 2.000 phiên mỗi ngày.
- Trung bình 20 phút mỗi phiên.
- Đầu ra sau cơ chế ghi và nén trung bình 50 kB mỗi giây.
- Thời gian lưu giả định 90 ngày.

Dùng đơn vị thập phân:

~~~text
2.000 × 1.200 giây × 50.000 byte
    = 120.000.000.000 byte mỗi ngày
    = 120 GB mỗi ngày

120 GB × 90
    = 10.800 GB
    = 10,8 TB
~~~

Đây là ví dụ giả định để tính dung lượng, không phải khuyến nghị thời hạn lưu hoặc tốc độ dữ liệu chuẩn.

Nếu có hai bản đầy đủ, phần nội dung tương ứng là khoảng 21,6 TB trước những phần bổ sung. Còn phải tính metadata, index, manifest, overhead, backup, bản xuất, dữ liệu giữ riêng và tăng trưởng.

Không mặc định chuyển sang kho lạnh hoặc dùng deduplication luôn đạt một tỷ lệ giảm cố định. Cần đo và xét ảnh hưởng tới truy xuất, xóa và phạm vi lỗi.

## 15. Ví dụ xuyên suốt: phiên bảo trì production

Một kỹ sư mở phiên bảo trì qua broker. Bằng chứng gồm metadata yêu cầu, quyết định JIT, recording chia đoạn và audit đích.

### 15.1. Tiếp nhận

Broker gửi các đoạn vào kho. Một đoạn bị gửi lại sau lỗi mạng. Nơi nhận đối soát ID và nội dung để tránh đếm trùng, đồng thời kiểm tra manifest cuối.

Nếu cùng ID nhưng nội dung khác, không im lặng bỏ một bản. Cần ghi nhận xung đột và xử lý.

Recording chỉ được đánh dấu đủ thành phần khi đạt tiêu chí đã định nghĩa. Metadata cần giữ trạng thái phần nào chưa xác minh.

### 15.2. Lưu và truy xuất

Kho giữ recording theo profile, đồng thời duy trì liên kết với người yêu cầu, tài khoản đích và quyết định.

Khi cần chuyển sang kho lạnh, profile và hạn không tự đổi. Công cụ phát lại, manifest và khóa vẫn phải truy xuất được theo mục tiêu.

### 15.3. Phát hiện bất thường gần hết hạn

Một cảnh báo liên quan xuất hiện gần thời điểm dự kiến xóa. Người có thẩm quyền yêu cầu giữ một tập phiên cùng audit liên quan.

Công việc xóa kiểm tra trạng thái mới trước bước không thể đảo ngược và không xử lý những đối tượng đang thuộc phạm vi giữ.

Nhóm điều tra phát hiện một khoảng thiếu dữ liệu. Kết luận phải nêu khoảng trống, không gọi recording là đầy đủ chỉ vì phần còn lại phát được.

### 15.4. Kết thúc việc giữ

Sau quyết định kết thúc, hệ thống đánh giá lại điều kiện lưu. Không mặc định tạo thêm một chu kỳ retention đầy đủ nếu policy không quy định.

Việc xóa cần đi qua các lớp lưu thuộc phạm vi, ghi lỗi hoặc phần chờ xử lý. Bản xuất cho điều tra cũng có owner và vòng đời riêng.

## 16. Hồ sơ retention minh họa

Ví dụ sau là **mô tả thiết kế, không phải cấu hình chạy trực tiếp của một sản phẩm**. Thời hạn cụ thể được tham chiếu từ profile đã được tổ chức chấp nhận.

~~~yaml
evidence_package:
  reference: session-evidence-example
  pam_session_reference: pam-session-example
  target_session_reference: protected-target-session-reference
  requester_reference: verified-identity-reference
  policy_version_reference: approved-policy-version

artifacts:
  - type: session-recording
    manifest_reference: protected-recording-manifest
  - type: access-decision
    reference: protected-decision-reference
  - type: target-audit
    reference: protected-audit-reference

retention:
  profile_reference: approved-production-maintenance-profile
  basis: finalized-recording-time
  incomplete_capture_rule_reference: approved-exception-process
  archive_move_resets_deadline: false

protection:
  encryption_reference: managed-evidence-encryption
  integrity_reference: protected-manifest-verification
  access_policy_reference: evidence-access-by-purpose

preservation:
  status: active
  case_reference: protected-investigation-reference
  review_owner_reference: assigned-investigation-owner

disposal:
  revalidate_policy_and_preservation: required
  managed_copy_inventory: required
  restore_reconciliation: required

evidence:
  credential_values_in_metadata: prohibited
  deletion_result_reference: not-created-while-preservation-active
~~~

Trạng thái giữ đang active nên dữ liệu không được xóa chỉ vì hạn thông thường đã tới.

Mọi trường tham chiếu phải phân giải được và có thẩm quyền. Một nhãn do client tùy ý gửi không tự tạo hoặc kết thúc quyết định giữ.

## 17. Phân công trách nhiệm và xác minh

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Chủ sở hữu chính sách PAM | Xác định phạm vi và mục tiêu bằng chứng |
| Chủ sở hữu tài nguyên hoặc dịch vụ | Giải thích mức nhạy cảm, tác động và nhu cầu vận hành |
| Đội vận hành PAM | Thu nhận và liên kết phiên theo phạm vi được giao |
| Đội quản lý kho | Vận hành lưu, bảo vệ, chuyển tầng, backup và xóa |
| Đội bảo mật hoặc điều tra | Đánh giá bằng chứng và đề xuất phạm vi giữ |
| Người có thẩm quyền quyết định | Chấp nhận profile, ngoại lệ hoặc quyết định giữ theo phân công |
| Người xem xét độc lập | Kiểm tra kết quả và giới hạn với mức độc lập phù hợp |

Phải có đầu mối khi upload thiếu, mất khóa, phát lại lỗi hoặc một bản sao không xóa được. Chỉ gửi cảnh báo không bảo đảm công việc đã được nhận.

### Ma trận xác minh gợi ý

| Kịch bản | Kết quả cần kiểm tra |
| --- | --- |
| Một phiên hoàn tất bình thường | Nội dung, metadata, manifest và liên kết đúng |
| Mất kết nối trong upload | Retry, độ đầy đủ và trạng thái chưa rõ được xử lý |
| Một đoạn bị thay đổi hoặc thiếu | Có tín hiệu toàn vẹn hoặc thiếu thành phần |
| Người ngoài phạm vi xem hoặc xuất | Bị hạn chế đúng policy, có bằng chứng phù hợp |
| Khôi phục từ backup | Tìm, giải mã và phát lại được phần thuộc phạm vi |
| Dữ liệu tới hạn nhưng đang được giữ | Không bị xóa theo lịch thông thường |
| Policy thay đổi khi công việc xóa chờ chạy | Có kiểm tra trạng thái có hiệu lực |
| Xóa một đối tượng dùng chunk chung | Không làm hỏng bằng chứng khác còn phải giữ |
| Restore chứa dữ liệu đã xóa | Áp dụng lại trạng thái trước khi công bố theo thiết kế |

Những phép kiểm tra cần dùng dữ liệu và môi trường phù hợp. Không xóa thử bằng chứng production đang cần giữ.

## 18. Chỉ số theo dõi và giới hạn kết luận

Có thể theo dõi:

- Phiên có đủ gói bằng chứng theo profile.
- Recording thiếu đoạn hoặc chưa có manifest cuối.
- Độ trễ từ kết thúc thu nhận tới khả năng truy xuất.
- Lỗi toàn vẹn, khóa hoặc công cụ phát lại.
- Yêu cầu truy xuất đạt mục tiêu khôi phục.
- Dữ liệu quá hạn chưa xử lý và nguyên nhân.
- Quyết định giữ chưa được review.
- Bản xuất chưa rõ owner hoặc vòng đời.
- Công việc xóa chưa xác nhận đủ phạm vi.

Cần định nghĩa mẫu số và trạng thái. Số tệp lưu thành công không bằng số phiên có bằng chứng đủ. Số yêu cầu xóa đã gửi không bằng số gói đã xử lý đầy đủ.

Một tỷ lệ toàn vẹn tốt trên những tệp đã nhận cũng không chứng minh không có tệp chưa từng được gửi. Phải kết hợp sức khỏe thu nhận và danh sách thành phần kỳ vọng.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ lưu video | Có thể mất danh tính, quyết định và liên kết | Quản lý gói bằng chứng theo mục đích |
| Mọi dữ liệu dùng chung một thời hạn | Lưu thiếu hoặc giữ quá nhiều không cần thiết | Phân loại và xác định profile |
| Upload xong là báo đầy đủ | Có thể thiếu đoạn hoặc metadata | Kiểm tra manifest và trạng thái thu nhận |
| Có hash là coi bằng chứng tuyệt đối tin cậy | Bỏ qua nguồn, khóa và dữ liệu chưa ghi | Xác định giả định và đối chiếu nguồn |
| Chuyển kho lạnh đặt lại retention | Vòng đời lệch chính sách | Giữ mốc hoặc quyết định thay đổi rõ |
| Không giữ khóa và công cụ đọc | Dữ liệu còn nhưng không sử dụng được | Quản lý phụ thuộc phục hồi |
| Người từng mở phiên được xem mọi recording | Lộ dữ liệu ngoài nhiệm vụ | Phân quyền tiếp cận bằng chứng riêng |
| Xóa tài khoản là xóa bằng chứng | Mất lịch sử cần giải thích | Tách vòng đời tài khoản và bằng chứng |
| Xóa catalog rồi báo xóa mọi bản | Bản sao và backup có thể còn | Theo dõi phạm vi xử lý thực tế |
| Restore làm xuất hiện dữ liệu đã hết hạn | Chính sách xóa bị vô hiệu hóa | Đối soát trạng thái sau khôi phục |
| Giữ toàn kho vô thời hạn cho một vụ việc | Tăng dữ liệu và khó quản trị | Giữ có phạm vi, owner và review |
| Ghi bí mật vào manifest điều tra | Tạo thêm nơi lộ credential | Dùng tham chiếu và xử lý bí mật riêng |

## 20. Bài tập tự đánh giá

Một tổ chức giữ recording trong kho lạnh nhưng xóa metadata sớm hơn. Khóa giải mã do một nhóm cũ quản lý và chưa được kiểm tra khôi phục. Gần ngày hết hạn, một hồ sơ điều tra được mở nhưng công việc xóa đã đọc danh sách từ hôm trước. Nhóm vận hành cho rằng có thể khôi phục từ backup nếu lỡ xóa.

Hãy trả lời:

1. Vì sao còn tệp recording chưa đủ đáp ứng mục tiêu bằng chứng?
2. Những phụ thuộc nào cần có để tìm và phát lại?
3. Vì sao công việc xóa cần đánh giá lại quyết định giữ?
4. Backup có thay thế được cơ chế giữ đúng thời điểm không?
5. Restore cần xử lý dữ liệu đã hết hạn hoặc đã xóa ra sao?
6. Cần báo trạng thái thế nào nếu một phần bằng chứng đã mất?

### Gợi ý phân tích

**Giá trị sử dụng:** thiếu metadata có thể làm mất liên kết với người, tài nguyên và quyết định. Thiếu khóa hoặc công cụ đọc khiến nội dung không truy xuất được.

**Phụ thuộc:** cần catalog, manifest, quyền, khóa, định dạng, công cụ và ngữ cảnh thời gian phù hợp.

**Quyết định giữ:** danh sách cũ có thể không còn hợp lệ. Cần cơ chế phối hợp trước bước không thể đảo ngược.

**Backup:** không bảo đảm có đúng phần dữ liệu, đủ mới hoặc truy xuất kịp; không phải lý do bỏ kiểm soát xóa.

**Restore:** phải đối soát trạng thái giữ, xóa và quyền trước khi công bố dữ liệu theo thiết kế.

**Thiếu bằng chứng:** ghi rõ phạm vi mất, nguồn còn lại và giới hạn kết luận. Không coi một bản phát lại được là bằng chứng toàn bộ phiên còn đầy đủ.

## 21. Những điểm cần ghi nhớ

- Retention quản lý một gói bằng chứng có ngữ cảnh, không chỉ một tệp ghi hình.
- Thời hạn, mốc tính, profile và trách nhiệm phải rõ; không có số ngày chung cho mọi trường hợp.
- Tính toàn vẹn phải đi cùng độ đầy đủ, nguồn tin cậy và khả năng truy xuất.
- Nội dung phiên và metadata đều có thể nhạy cảm; không biến bằng chứng thành kho bí mật thứ hai.
- Kho lạnh, khóa, công cụ đọc và backup cần được quản lý như những phụ thuộc của bằng chứng.
- Giữ phục vụ điều tra phải phối hợp với công việc xóa; restore không được âm thầm làm sống lại dữ liệu đã phải xử lý.
- Chỉ kết luận theo phạm vi đã xác minh, gồm bản sao, lỗi và những giới hạn còn tồn tại.
