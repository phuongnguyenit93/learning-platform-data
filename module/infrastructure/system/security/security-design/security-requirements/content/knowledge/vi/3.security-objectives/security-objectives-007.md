# Privacy

## 1. Privacy là mục tiêu bảo mật như thế nào?

**Privacy — quyền riêng tư**, trong thiết kế hệ thống, liên quan đến cách thông tin về con người được thu thập, sử dụng, liên kết, chia sẻ, lưu giữ và loại bỏ. Mục tiêu không chỉ là ngăn người lạ đọc dữ liệu, mà còn là giới hạn việc xử lý theo mục đích và điều kiện đã được xác định.

Một hệ thống có thể giữ dữ liệu rất kín nhưng vẫn tạo rủi ro riêng tư:

- Thu thập ngày sinh đầy đủ dù nghiệp vụ chỉ cần biết người dùng thuộc một nhóm tuổi.
- Dùng nội dung trao đổi hỗ trợ để xây dựng hồ sơ tiếp thị ngoài mục đích đã được quyết định.
- Giữ lịch sử vị trí lâu hơn nhu cầu đã xác định.
- Kết hợp các tập dữ liệu để suy ra thông tin mà cá nhân không dự kiến sẽ bị suy luận.
- Cho phép lựa chọn tắt phân tích nhưng vẫn gửi sự kiện qua một SDK khác.
- Xóa tài khoản trên giao diện nhưng giữ dữ liệu có thể liên kết trong báo cáo, chỉ mục và hàng đợi.

Những tình huống này không nhất thiết bắt đầu bằng một vụ xâm nhập. Chúng có thể xuất hiện trong luồng nghiệp vụ chạy đúng như mã đã viết.

Một cách diễn đạt mục tiêu là:

> Hệ thống chỉ xử lý dữ liệu liên quan đến cá nhân trong phạm vi mục đích, dữ liệu, người nhận, thời hạn và điều kiện đã được xác định; cung cấp thông tin và cơ chế thực hiện lựa chọn hoặc yêu cầu phù hợp với chính sách áp dụng.

Để triển khai được, câu trên phải được phân rã thành các yêu cầu cụ thể. “Tôn trọng quyền riêng tư” chưa phải tiêu chí nghiệm thu.

### 1.1. Phân biệt privacy với confidentiality

| Khía cạnh | Confidentiality — tính bí mật | Privacy — quyền riêng tư |
| --- | --- | --- |
| Câu hỏi chính | Ai được biết dữ liệu? | Vì sao, bằng cách nào và trong phạm vi nào dữ liệu được xử lý? |
| Trọng tâm | Ngăn tiết lộ ngoài quyền | Quản lý việc xử lý dữ liệu liên quan đến con người trong suốt vòng đời |
| Ví dụ vi phạm | Tài khoản tenant A đọc hội thoại tenant B | Hội thoại được giữ kín nhưng dùng cho mục đích khác chưa được cho phép |
| Biện pháp hỗ trợ | Xác thực, phân quyền, mã hóa, lọc đầu ra | Giới hạn mục đích, giảm dữ liệu, lưu giữ có thời hạn, quản lý lựa chọn, kiểm soát chia sẻ |
| Giới hạn | Có quyền đọc chưa có nghĩa được dùng cho mọi mục đích | Chính sách xử lý phù hợp vẫn cần bảo vệ khỏi đọc và sửa trái phép |

Hai mục tiêu bổ trợ nhau. Không thể bảo vệ quyền riêng tư tốt nếu dữ liệu bị phát tán ngoài quyền. Tuy nhiên, mã hóa và phân quyền đúng chưa đủ chứng minh toàn bộ hoạt động xử lý là phù hợp.

### 1.2. Phân biệt mục tiêu, nghĩa vụ và cơ chế

Cần tách ba lớp:

- **Mục tiêu:** giảm thu thập và sử dụng dữ liệu vượt nhu cầu.
- **Nghĩa vụ đã xác định:** những yêu cầu của sản phẩm, tổ chức, thỏa thuận và phạm vi áp dụng được người có trách nhiệm làm rõ.
- **Cơ chế:** thiết kế biểu mẫu, giới hạn schema, tách tập dữ liệu, quản lý lựa chọn, thực hiện lưu giữ và xóa.

Không tự suy ra mọi hoạt động đều phải dựa trên một ô “đồng ý”, hoặc mọi yêu cầu xóa đều có cùng cách xử lý. Cần xác định chính sách áp dụng cho từng mục đích, loại dữ liệu và hoàn cảnh, rồi chuyển thành hành vi hệ thống.

Các thời hạn và chính sách minh họa trong bài là quyết định giả định của một sản phẩm, không phải thời hạn chung cho mọi hệ thống.

## 2. Xác định dữ liệu và người liên quan

Trong phân tích kỹ thuật, cần xét cả thông tin nhận diện trực tiếp lẫn thông tin có thể kết hợp để nhận diện, liên kết hoặc mô tả một cá nhân.

| Nhóm dữ liệu | Ví dụ | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Nhận diện trực tiếp | Tên, email, số điện thoại | Có thực sự cần đủ các trường này không? |
| Định danh kỹ thuật | Mã tài khoản, mã thiết bị, định danh phiên | Có thể liên kết với cá nhân qua tập dữ liệu khác không? |
| Hành vi | Lịch sử truy cập, thao tác, thời điểm tương tác | Có tạo thành hồ sơ theo dõi cá nhân không? |
| Nội dung | Hội thoại, ghi chú, tệp đính kèm | Có chứa dữ liệu của người khác hoặc thông tin vượt schema dự kiến không? |
| Dữ liệu suy luận | Nhóm sở thích, mức độ quan tâm, phân loại khách hàng | Suy luận dùng vào đâu, có thể gây tác động gì? |
| Dữ liệu vận hành | Log, dấu vết lỗi, bản sao lưu | Có giữ định danh hoặc nội dung có thể liên kết không? |

Không chỉ người có tài khoản mới là người liên quan. Một hội thoại hỗ trợ có thể nhắc tới người nhận hàng, đồng nghiệp hoặc người thân của khách hàng. Một tệp đính kèm có thể chứa nhiều cá nhân.

Phạm vi cần quan tâm phụ thuộc dữ liệu thực tế và nghĩa vụ áp dụng. Không kết luận rằng một trường hết liên quan đến riêng tư chỉ vì tên trường không có chữ “name” hoặc “email”.

### 2.1. Đổi định danh chưa đồng nghĩa loại bỏ khả năng nhận diện

- Thay email bằng mã khách hàng vẫn cho phép liên kết nếu còn bảng ánh xạ.
- Băm email có thể bị đối chiếu với các giá trị đoán được.
- Bỏ tên nhưng giữ vị trí, thời điểm và sự kiện hiếm vẫn có thể tạo khả năng nhận diện.
- Báo cáo tổng hợp với nhóm rất nhỏ có thể tiết lộ thông tin về một người.

Cần đánh giá dữ liệu, tập dữ liệu phụ, người có thể tiếp cận và bối cảnh sử dụng. Không dùng nhãn “ẩn danh” như một kết luận tự động sau khi bỏ một trường.

## 3. Bối cảnh xuyên suốt: nền tảng hỗ trợ khách hàng

Giả sử một nền tảng phục vụ nhiều doanh nghiệp. Mỗi doanh nghiệp là một **tenant**, có khách hàng, nhân viên và phạm vi dữ liệu riêng.

Nền tảng có các chức năng:

- Tiếp nhận yêu cầu hỗ trợ.
- Lưu hội thoại và tệp đính kèm.
- Gửi thông báo về tiến độ xử lý.
- Đo chất lượng vận hành.
- Cung cấp phân tích sử dụng sản phẩm tùy chọn.
- Xử lý yêu cầu truy cập, sửa hoặc xóa theo chính sách sản phẩm.
- Ghi log, sao lưu và phục hồi.

Trong ví dụ, phân tích sử dụng sản phẩm là một mục đích tùy chọn riêng; hỗ trợ khách hàng không bị buộc phải bật mục đích này. Đây là giả định để minh họa thiết kế lựa chọn, không phải kết luận rằng mọi hoạt động phân tích ở mọi hệ thống đều có cùng chính sách.

### 3.1. Lập bảng mục đích xử lý

| Mã mục đích | Mục đích | Dữ liệu dự kiến cần dùng | Bên cần tiếp cận |
| --- | --- | --- | --- |
| PURPOSE-01 | Tiếp nhận và xử lý yêu cầu hỗ trợ | Thông tin liên hệ cần thiết, nội dung yêu cầu, tệp liên quan | Nhân viên được giao và dịch vụ xử lý |
| PURPOSE-02 | Thông báo tiến độ | Điểm liên hệ, mã yêu cầu, trạng thái | Dịch vụ thông báo và người nhận đã xác định |
| PURPOSE-03 | Phân tích sử dụng tùy chọn | Sự kiện thuộc schema được duyệt và định danh phù hợp | Dịch vụ phân tích có phạm vi hạn chế |
| PURPOSE-04 | Phát hiện và điều tra sự cố bảo mật | Dấu vết xác thực, thao tác, kết quả và định danh cần thiết | Nhân sự hoặc dịch vụ phụ trách bảo mật |
| PURPOSE-05 | Phục hồi nghiệp vụ | Dữ liệu và cấu hình trong phạm vi sao lưu | Quy trình phục hồi được kiểm soát |

Bảng không tự cho phép mọi dữ liệu đi vào mọi mục đích. Ví dụ, PURPOSE-04 không có nghĩa được ghi toàn bộ hội thoại vào log bảo mật. PURPOSE-05 không có nghĩa giữ bản sao lưu vô thời hạn.

Cần xác định bên quyết định mục đích, bên thực hiện, bên nhận và người chịu trách nhiệm trả lời câu hỏi về dữ liệu. Không suy ra trách nhiệm chỉ từ vị trí dữ liệu được lưu.

## 4. Theo dữ liệu qua toàn bộ vòng đời

Một biểu mẫu chỉ là điểm bắt đầu. Quyền riêng tư còn phụ thuộc những gì xảy ra sau khi dữ liệu được gửi.

~~~mermaid
flowchart LR
    U["Khách hàng"] --> A["Tiếp nhận yêu cầu"]
    A --> D["Hội thoại và tệp"]
    D --> S["Xử lý hỗ trợ"]
    S --> N["Thông báo tiến độ"]
    S --> E["Bản xuất có kiểm soát"]
    A --> G["Kiểm tra chính sách và lựa chọn"]
    G --> T["Phân tích tùy chọn"]
    S --> L["Log và dấu vết tối thiểu"]
    D --> B["Sao lưu có thời hạn"]
    D --> R["Lưu giữ, hạn chế hoặc xóa"]
    T --> R
~~~

Sơ đồ minh họa các đường cần xem xét. Mỗi mũi tên phải được làm rõ về trường dữ liệu, người nhận, mục đích và điều kiện. Không mặc định dữ liệu hỗ trợ được chuyển nguyên vẹn sang phân tích.

### 4.1. Hồ sơ cho một hoạt động xử lý

Với mỗi mục đích, ghi tối thiểu:

| Thuộc tính | Nội dung cần xác định |
| --- | --- |
| Mục đích và phạm vi | Việc xử lý nhằm làm gì, áp dụng cho chức năng nào |
| Người liên quan | Dữ liệu nói về ai, có người không có tài khoản không |
| Dữ liệu | Trường, nguồn, dữ liệu suy luận và mức chi tiết |
| Điều kiện xử lý | Chính sách nào cho phép, có lựa chọn hoặc phê duyệt gì |
| Bên nhận | Dịch vụ, nhân sự, tenant, nhà cung cấp và môi trường |
| Thời hạn | Sự kiện bắt đầu tính, thời gian lưu và điều kiện kết thúc |
| Bản sao | Log, cache, chỉ mục, hàng đợi, bản xuất, sao lưu |
| Cơ chế thực hiện yêu cầu | Cách truy cập, sửa, hạn chế hoặc xóa theo chính sách |
| Trách nhiệm | Ai phê duyệt mục đích, ai triển khai, ai xác minh |
| Bằng chứng | Thiết kế, cấu hình, dữ liệu thử và kết quả kiểm chứng |

Điểm chưa biết phải được ghi là câu hỏi còn mở. Ví dụ, “SDK có thể tự gửi một số sự kiện” không đủ để kết luận dữ liệu đã được kiểm soát.

### 4.2. Những rủi ro riêng tư thường gặp

| Mã | Tình huống | Hậu quả có thể xảy ra |
| --- | --- | --- |
| R-P01 | Thu thập trường hoặc độ chi tiết không cần cho mục đích | Tăng dữ liệu có thể bị lộ hoặc bị sử dụng ngoài nhu cầu |
| R-P02 | Dữ liệu hỗ trợ được dùng cho phân tích hay mục đích khác ngoài phạm vi | Cá nhân bị theo dõi hoặc đánh giá ngoài điều kiện đã xác định |
| R-P03 | Lựa chọn của người dùng không được thực thi ở SDK, worker hoặc hàng đợi | Tiếp tục xử lý dù điều kiện tùy chọn không còn hiệu lực |
| R-P04 | Dữ liệu tồn tại quá thời hạn hoặc xuất hiện lại sau phục hồi | Giữ và sử dụng dữ liệu vượt vòng đời đã xác định |
| R-P05 | Xử lý yêu cầu dữ liệu nhầm người hoặc lộ dữ liệu người khác | Người không có quyền nhận bản xuất hoặc gây xóa nhầm |
| R-P06 | Bên nhận ngoài hệ thống có dữ liệu vượt phạm vi cần thiết | Mất kiểm soát đối với mục đích, người nhận và thời gian lưu |
| R-P07 | Log, bản thử nghiệm hoặc báo cáo giữ nội dung có thể liên kết | Tạo thêm đường quan sát cá nhân ngoài nghiệp vụ |
| R-P08 | Kết hợp dữ liệu hoặc báo cáo nhóm nhỏ để suy ra thông tin | Nhận diện hoặc mô tả một người ngoài mục tiêu dự kiến |

Đây là tình huống rủi ro để phân tích, không phải kết luận rằng một sản phẩm cụ thể đã có điểm yếu. Mức ưu tiên phụ thuộc khả năng xảy ra, tác động, quy mô, ngữ cảnh và người chịu ảnh hưởng.

## 5. Đặc tả tối thiểu hóa dữ liệu và giới hạn mục đích

### 5.1. P-REQ-01: chỉ thu thập trường cần thiết

> Mỗi điểm tiếp nhận dữ liệu phải có danh mục trường được phép, mục đích sử dụng, mức chi tiết và trạng thái bắt buộc hoặc tùy chọn. Hệ thống không được lưu hoặc chuyển tiếp các trường ngoài schema được chấp nhận cho hoạt động đó.

Trong ví dụ hỗ trợ, nếu mã đơn hàng và một điểm liên hệ đã đủ xử lý, không tự bổ sung ngày sinh, vị trí chính xác hoặc danh bạ thiết bị chỉ vì có thể thu thập.

Tối thiểu hóa áp dụng ở nhiều lớp:

- **Trường dữ liệu:** có cần trường này không?
- **Độ chi tiết:** cần ngày chính xác hay chỉ cần khoảng?
- **Tần suất:** cần thu liên tục hay tại một sự kiện?
- **Thời gian:** cần giữ bao lâu?
- **Phạm vi người:** cần toàn bộ tập khách hàng hay nhóm liên quan?
- **Số nơi nhận:** có cần gửi sang dịch vụ khác không?

Nội dung tự do và tệp đính kèm cần chính sách riêng. Một schema có ít trường không chứng minh nội dung hội thoại không chứa dữ liệu dư thừa. Có thể cần hướng dẫn, giới hạn loại tệp, lọc hoặc luồng xử lý nội dung theo mức rủi ro.

**Kiểm chứng:** thử trường lạ, trường bị loại bỏ và dữ liệu không cần thiết bằng giá trị giả; kiểm tra cơ sở dữ liệu, hàng đợi và đích nhận. Chỉ ẩn trường khỏi biểu mẫu chưa chứng minh client không gửi được trường đó.

### 5.2. P-REQ-02: kiểm soát sử dụng theo mục đích

> Dịch vụ và công việc nền chỉ được đọc, kết hợp hoặc chuyển dữ liệu theo mục đích cùng tập dữ liệu đã được phê duyệt. Dữ liệu của PURPOSE-01 không được tự chuyển sang PURPOSE-03 nếu chưa đáp ứng chính sách áp dụng cho PURPOSE-03.

Một trường “purpose” trong yêu cầu do client tự đặt không phải bằng chứng cho phép. Cần có cơ chế ràng buộc đáng tin cậy giữa:

- Chức năng được triển khai.
- Danh tính dịch vụ hoặc công việc.
- Tập dữ liệu và trường được phép sử dụng.
- Điều kiện xử lý có hiệu lực.
- Người hoặc đơn vị chịu trách nhiệm về mục đích.

Thiết kế có thể tách danh tính dịch vụ, tập dữ liệu, quyền truy vấn hoặc pipeline. Không phải mọi vấn đề về mục đích đều giải quyết được chỉ bằng một điều kiện trong mã; có thể cần quy trình phê duyệt, kiểm tra sử dụng dữ liệu và giới hạn khả năng xuất.

**Kiểm chứng:** dùng danh tính của dịch vụ phân tích thử đọc nội dung hội thoại hoặc tệp ngoài schema. Đối chiếu đường xuất dữ liệu và các công việc nền, không chỉ API người dùng.

### 5.3. P-REQ-03: thông tin xử lý và lựa chọn phải khớp hành vi

> Trước hoặc tại điểm thu thập theo thiết kế đã chọn, sản phẩm phải cung cấp thông tin dễ tìm về dữ liệu cần dùng, mục đích, bên nhận và cơ chế thực hiện lựa chọn hoặc yêu cầu. Phiên bản thông tin và hành vi hệ thống phải được quản lý nhất quán.

Thông tin hiển thị không thay thế kiểm soát. Nếu giao diện nói “không gửi nội dung hội thoại để phân tích”, kiểm thử phải xác nhận pipeline thực tế không gửi nội dung đó.

Không ghép lựa chọn tùy chọn vào một thao tác bắt buộc nếu chính sách sản phẩm đã tách hai mục đích. Nhãn, giá trị mặc định và kết quả sau thao tác phải giúp người dùng hiểu mình đã chọn gì.

## 6. Thực thi lựa chọn trong hệ thống phân tán

### 6.1. P-REQ-04: phân tích tùy chọn chỉ chạy khi đủ điều kiện

Với PURPOSE-03 trong ví dụ:

> Hệ thống không được tạo hoặc chuyển sự kiện phân tích tùy chọn trước khi có lựa chọn hợp lệ theo chính sách của mục đích đó. Khi trạng thái chưa được xác định hoặc không thể xác nhận, không thực hiện xử lý tùy chọn. Việc tắt mục đích tùy chọn không được làm mất chức năng hỗ trợ cơ bản.

Phải kiểm tra cả SDK phía client, API, hàng đợi, worker, đường thử lại và cách khởi tạo định danh. Không nên để SDK gửi dữ liệu trước rồi mới đọc trạng thái lựa chọn.

“Không phân tích tùy chọn” không tự đồng nghĩa ngừng mọi dấu vết bảo mật hoặc thông báo nghiệp vụ. Các mục đích khác phải có chính sách, schema và giới hạn riêng; không được dùng tên “bảo mật” để hợp thức hóa việc thu thập không liên quan.

### 6.2. Chọn mốc hiệu lực và cách xử lý dữ liệu đang chờ

Giả sử chính sách sản phẩm minh họa yêu cầu thay đổi lựa chọn có hiệu lực tại mọi điểm xử lý trong tối đa năm phút từ khi ghi nhận thành công.

Cần đặc tả rõ:

- Client và dịch vụ đọc trạng thái mới bằng cách nào?
- Sự kiện phát sinh trước thay đổi nhưng còn trong hàng đợi được xử lý ra sao?
- Lượt xử lý đang chạy có dừng hay hoàn tất phần nào?
- Cache lựa chọn được làm mới hoặc hết hiệu lực khi nào?
- Khi không liên lạc được với nguồn trạng thái, xử lý tùy chọn có bị chặn không?

Trong ví dụ, chọn quy tắc: sau thời hạn năm phút, worker không được dùng các sự kiện còn chờ cho mục đích tùy chọn đã bị tắt. Thông điệp không đủ điều kiện phải được loại khỏi đường xử lý hoặc cách ly theo chính sách không tiếp tục sử dụng.

Con số năm phút là giả định học tập, không phải thời hạn mặc định. Cần thống nhất nếu sản phẩm yêu cầu hiệu lực ngay hoặc có cửa sổ khác.

### 6.3. Không hứa đảo ngược điều hệ thống không thực hiện được

Tắt một mục đích không tự xóa kết quả đã tạo hoặc rút lại mọi bản đã chia sẻ. Phải định nghĩa riêng:

- Dừng thu thập mới.
- Dừng sử dụng dữ liệu còn chờ.
- Xóa hoặc hạn chế dữ liệu đã lưu.
- Xử lý kết quả dẫn xuất.
- Thông báo hoặc yêu cầu bên nhận thực hiện hành động.
- Giữ những bằng chứng tối thiểu cần thiết về thay đổi lựa chọn.

Một bằng chứng lựa chọn chỉ nên chứa thông tin cần thiết: mục đích, phiên bản thông tin liên quan, trạng thái, thời điểm và định danh phù hợp. Không ghi toàn bộ nội dung cá nhân vào bằng chứng chỉ để chứng minh đã có thao tác.

## 7. Lưu giữ, xóa và ngăn dữ liệu xuất hiện lại

### 7.1. P-REQ-05: mỗi tập dữ liệu có chính sách vòng đời

> Mỗi tập dữ liệu có thể liên kết với cá nhân phải gắn với mục đích, sự kiện bắt đầu tính thời hạn, thời điểm hết nhu cầu sử dụng và hành động khi hết hạn. Chính sách phải bao phủ các bản sao trong phạm vi, không chỉ bản ghi chính.

Một chính sách cần phân biệt:

- Không còn được dùng cho mục đích đang xét.
- Không còn được người dùng hoặc dịch vụ truy cập.
- Đã loại khỏi kho đang hoạt động.
- Còn trong bản sao lưu có kiểm soát.
- Còn được giữ theo ngoại lệ đã được người có trách nhiệm xác nhận.

Không dùng một cờ “deleted” để kết luận dữ liệu đã biến mất khỏi mọi nơi nếu các bản sao vẫn được sử dụng.

### 7.2. Ví dụ chính sách có mốc đo

Giả sử sản phẩm chọn chính sách minh họa cho dữ liệu phân tích tùy chọn:

| Thuộc tính | Quyết định minh họa |
| --- | --- |
| Tập dữ liệu | Sự kiện phân tích có thể liên kết với người dùng |
| Mốc bắt đầu | Thời điểm sự kiện phát sinh theo quy tắc thời gian đã thống nhất |
| Hạn sử dụng | Tối đa 30 ngày, trừ khi một điều kiện khác buộc kết thúc sớm hơn |
| Khi hết hạn | Chặn khỏi đường truy vấn và xử lý cho mục đích phân tích |
| Dọn kho hoạt động | Hoàn tất trong tối đa 24 giờ sau mốc hết hạn |
| Bản sao lưu | Có chính sách riêng và không được dùng như kho phân tích |
| Dữ liệu dẫn xuất | Đánh giá khả năng liên kết và quyết định xử lý riêng |

Các giá trị là giả định để minh họa cách đo. Không sao chép sang dữ liệu hỗ trợ, log hoặc sao lưu mà không đánh giá nhu cầu.

Tiêu chí chấp nhận phải có phép thử quanh mốc hết hạn, kiểm tra truy vấn, công việc nền và kết quả dọn dữ liệu. Cần nêu cách xử lý sai lệch đồng hồ, sự kiện đến muộn và tác vụ dọn bị lỗi.

### 7.3. Theo dõi xóa qua nhiều nơi lưu

Một yêu cầu xóa có thể phải đi qua:

- Kho chính và bản sao phục vụ truy vấn.
- Cache, chỉ mục tìm kiếm và kho phân tích.
- Hàng đợi, hàng đợi lỗi và tệp tạm.
- Bản xuất, phiên bản tệp và liên kết tải.
- Bên nhận dữ liệu ngoài hệ thống.
- Bản sao lưu theo chính sách đã xác định.

Mỗi đích cần có trạng thái, bằng chứng hoặc lỗi rõ ràng. Gửi được một lệnh xóa không đồng nghĩa nơi nhận đã thực hiện.

Thiết kế phải xử lý việc gửi lại và thất bại một phần. Ví dụ, kho chính đã xóa nhưng chỉ mục tìm kiếm chưa cập nhật thì chưa thể báo hoàn tất toàn bộ phạm vi đó.

Nếu có trường hợp cần tiếp tục giữ một phần dữ liệu, phải ghi phạm vi, lý do, người quyết định, giới hạn sử dụng và thời điểm xem xét. Không dùng một nhãn ngoại lệ để cho phép mọi dữ liệu tiếp tục được dùng.

### 7.4. P-REQ-08: phục hồi không làm sống lại dữ liệu đã bị hạn chế

> Quy trình phục hồi phải áp dụng lại các thay đổi về xóa, hạn chế sử dụng và lựa chọn sau điểm sao lưu trước khi mở các đường xử lý liên quan. Dữ liệu từ bản sao lưu không được tự động quay lại pipeline tùy chọn nếu điều kiện xử lý hiện tại không còn hiệu lực.

Cần có nguồn đối soát đáng tin cậy hoặc phương án khác để xác lập trạng thái hiện hành. Nếu chưa có nguồn đó, đây là khoảng trống thiết kế, không phải một bước đã được giải quyết bằng tài liệu.

Bản ghi phục vụ đối soát cũng cần tối thiểu hóa, giới hạn quyền và thời hạn. Không giữ toàn bộ dữ liệu đã xóa chỉ để ghi rằng dữ liệu đó đã được xóa.

Trong diễn tập, tạo thay đổi lựa chọn hoặc yêu cầu xóa sau điểm sao lưu, phục hồi rồi thử lại các đường đọc và xử lý. Chỉ kiểm tra dịch vụ khởi động thành công chưa đủ.

## 8. Xử lý yêu cầu liên quan đến dữ liệu của cá nhân

Sản phẩm có thể cung cấp cơ chế truy cập, sửa, xuất, hạn chế hoặc xóa theo chính sách và nghĩa vụ đã được xác định. Không mặc định mọi loại yêu cầu có cùng phạm vi, điều kiện hoặc thời hạn.

### 8.1. P-REQ-06: xác minh đúng người và thực hiện đúng phạm vi

> Hệ thống phải tiếp nhận, xác minh và xử lý yêu cầu theo loại thao tác cùng chính sách áp dụng. Không trả dữ liệu hoặc thực hiện thay đổi trước khi xác định đủ căn cứ về người yêu cầu và phạm vi được phép. Kết quả phải phản ánh đúng phần đã thực hiện, phần còn chờ và ngoại lệ được xác nhận.

Một quy trình có thể gồm:

1. Tiếp nhận loại yêu cầu và thông tin cần thiết.
2. Xác minh người yêu cầu bằng mức bảo đảm phù hợp.
3. Xác định mối liên hệ giữa người đó và các bản ghi.
4. Xác định tenant, phạm vi dữ liệu và bên chịu trách nhiệm.
5. Kiểm tra dữ liệu của người khác hoặc thông tin cần hạn chế.
6. Thực hiện thao tác ở các nơi trong phạm vi.
7. Trả kết quả qua kênh được kiểm soát.
8. Giữ dấu vết tối thiểu về cách xử lý.

Không thu thập thêm nhiều dữ liệu nhận diện chỉ vì thuận tiện xác minh. Cần chọn phương pháp phù hợp với rủi ro; yêu cầu một tài liệu nhận diện nhạy cảm cho mọi thao tác có thể tạo thêm rủi ro riêng tư.

### 8.2. Những trường hợp dễ thiết kế sai

**Nhầm tài khoản với cá nhân.** Một người có thể xuất hiện trong nhiều bản ghi hoặc nhiều tenant, trong khi một hội thoại có thể nói về nhiều người. Không chỉ tìm theo khóa tài khoản rồi kết luận đã bao phủ mọi dữ liệu.

**Trả nguyên toàn bộ hội thoại.** Bản xuất có thể chứa dữ liệu người khác, ghi chú nội bộ hoặc bí mật xác thực. Cần quy tắc lọc và xem xét phạm vi phù hợp trước khi chuyển kết quả.

**Xóa dựa vào một email tự khai.** Kẻ khác có thể gây xóa nhầm hoặc lấy dữ liệu. Phải xác minh quan hệ với dữ liệu và quyền thực hiện thao tác.

**Báo hoàn tất ngay khi nhận yêu cầu.** Trạng thái tiếp nhận, đang xử lý, thất bại một phần và hoàn tất phải được phân biệt. Một phản hồi thành công của API tiếp nhận không chứng minh mọi kho đã xử lý.

**Tạo bản xuất rồi để lâu.** Kết quả yêu cầu dữ liệu cũng là dữ liệu nhạy cảm. Phải kiểm soát người tải, thời hạn và cách dọn bản xuất.

**Dùng trạng thái yêu cầu làm kênh tiết lộ.** Người không có quyền không được tra cứu thông tin về tài khoản hoặc yêu cầu của người khác chỉ bằng mã đoán được.

Thời hạn xử lý cần được chọn từ chính sách áp dụng, có mốc bắt đầu, điều kiện tạm dừng nếu có và cách đo. Không tự đặt một số ngày rồi coi đó là yêu cầu chung.

## 9. Kiểm soát chia sẻ, vận hành và dữ liệu suy luận

### 9.1. P-REQ-07: giới hạn dữ liệu gửi tới bên nhận

> Mỗi bên nhận phải có danh mục mục đích, trường dữ liệu, điều kiện gửi, phạm vi sử dụng và trách nhiệm liên quan đến lưu giữ hoặc xử lý yêu cầu. Hệ thống chỉ gửi tập dữ liệu đã được xác định cho bên nhận đó.

Ví dụ, dịch vụ thông báo tiến độ có thể chỉ cần điểm liên hệ, mã yêu cầu và trạng thái; không cần toàn bộ hội thoại hay mọi tệp đính kèm.

Phải kiểm tra cả dữ liệu trong URL, header, metadata và thông báo lỗi. Một tích hợp có schema tối thiểu vẫn có thể làm lộ dữ liệu qua tên tệp hoặc đường dẫn.

Với dữ liệu đã ra ngoài phạm vi quản lý trực tiếp, cần phân biệt:

- Hệ thống đã ngừng gửi.
- Đã gửi yêu cầu hạn chế hoặc xóa.
- Bên nhận đã xác nhận tiếp nhận.
- Đã có bằng chứng hoàn tất theo cơ chế được thống nhất.
- Còn phần không thể xác nhận hoặc có ngoại lệ.

Không báo “đã xóa ở mọi nơi” chỉ vì một yêu cầu mạng đã gửi thành công.

### 9.2. Log, hỗ trợ kỹ thuật và môi trường thử

Log bảo mật có mục đích riêng nhưng vẫn phải giảm nội dung và quyền đọc. Ưu tiên trường cần thiết như loại thao tác, kết quả, thời điểm và định danh phù hợp thay vì nội dung hội thoại.

Môi trường thử, công cụ hỗ trợ, bản chụp màn hình và tệp đính kèm trong hệ thống theo dõi lỗi đều có thể tạo thêm bản sao. Dữ liệu thử giả thường giúp tránh nhu cầu sao chép dữ liệu thật; nếu cần dữ liệu khác, phải có phạm vi và kiểm soát đã xác định.

Yêu cầu xử lý bản sao vận hành phải liên kết với P-REQ-01, P-REQ-05 và P-REQ-08. Không coi log hoặc bản sao lưu là vùng miễn trừ khỏi phân tích riêng tư.

### 9.3. P-REQ-09: đánh giá liên kết và suy luận trước khi dùng dữ liệu dẫn xuất

> Trước khi cung cấp báo cáo hoặc kết hợp tập dữ liệu có thể mô tả cá nhân, nhóm chịu trách nhiệm phải đánh giá mục đích, người nhận, khả năng nhận diện và khả năng suy luận. Các giới hạn đã chọn phải được hiện thực và kiểm chứng tại đường truy vấn hoặc xuất.

Không có một ngưỡng số lượng nhóm phù hợp cho mọi tập dữ liệu. Chỉ cấm nhóm nhỏ cũng có thể chưa đủ nếu người dùng kết hợp nhiều truy vấn hoặc đã biết dữ liệu phụ.

Nếu sản phẩm có chấm điểm, phân nhóm hay hồ sơ hành vi, cần ghi dữ liệu đầu vào, mục đích sử dụng, người được xem và tác động dự kiến. Không kết luận rằng một kết quả suy luận nằm ngoài phạm vi riêng tư chỉ vì nó do hệ thống tạo ra.

## 10. Kiểm chứng mục tiêu privacy

Cần kết hợp kiểm thử hành vi, kiểm tra schema và quyền, quan sát luồng dữ liệu, diễn tập vòng đời cùng xem xét thông tin hiển thị. Một biểu mẫu có ô lựa chọn chưa chứng minh các đường xử lý tôn trọng lựa chọn.

### 10.1. Ma trận truy vết

| Rủi ro | Yêu cầu liên quan | Kiểm chứng dự kiến |
| --- | --- | --- |
| R-P01: thu thập quá nhu cầu | P-REQ-01 | Gửi trường ngoài schema; kiểm tra kho chính, thông điệp và đích nhận |
| R-P02: sử dụng ngoài mục đích | P-REQ-02, P-REQ-03 | Thử quyền của dịch vụ phân tích; đối chiếu dữ liệu gửi với thông tin sản phẩm |
| R-P03: bỏ qua lựa chọn | P-REQ-04 | Thử trước lựa chọn, sau khi bật, sau khi tắt, trạng thái chưa biết và mất kết nối |
| R-P04: lưu quá hạn hoặc phục hồi lại | P-REQ-05, P-REQ-08 | Thử hết hạn, xóa thất bại một phần và phục hồi sau thay đổi |
| R-P05: xử lý nhầm yêu cầu dữ liệu | P-REQ-06 | Thử người không có quan hệ với dữ liệu, khác tenant và bản xuất chứa nhiều người |
| R-P06: chia sẻ quá phạm vi | P-REQ-07 | Quan sát nội dung gửi ra, kiểm tra điều kiện gửi và quy trình phản hồi từ bên nhận |
| R-P07: bản sao vận hành không được kiểm soát | P-REQ-01, P-REQ-05, P-REQ-08 | Kiểm tra log, công cụ thu lỗi, cache, hàng đợi lỗi và dữ liệu phục hồi |
| R-P08: liên kết hoặc suy luận ngoài mục đích | P-REQ-09 | Kiểm tra truy vấn, nhóm báo cáo, khả năng kết hợp và quyền xuất dữ liệu |

Bảng là kế hoạch minh họa, không phải kết quả kiểm thử của một hệ thống đang chạy. Mỗi hàng cần được phân rã theo thành phần và tiêu chí trong phạm vi.

### 10.2. Ca minh họa: tắt phân tích tùy chọn

~~~text
Yêu cầu: P-REQ-04
Chính sách minh họa: hiệu lực tại mọi điểm trong tối đa năm phút.

Tiền điều kiện:
- Người dùng đang bật phân tích tùy chọn.
- Có sự kiện thử trong hàng đợi chưa được worker xử lý.
- Có dữ liệu giả và mã tương quan để theo dõi.
- Đã xác định các điểm tạo, gửi và xử lý sự kiện.

Thao tác:
1. Kiểm tra luồng phân tích hợp lệ trước khi thay đổi.
2. Tắt mục đích tùy chọn, ghi nhận thời điểm hệ thống xác nhận.
3. Tạo thao tác sử dụng sản phẩm sau thay đổi.
4. Giữ một client hoặc worker có cache trạng thái cũ.
5. Cho xử lý thông điệp đã chờ và nhánh thử lại.
6. Quan sát tại các đích sau mốc năm phút.
7. Tiếp tục dùng chức năng hỗ trợ cơ bản.

Kết quả mong đợi:
- Sau mốc hiệu lực, không tạo, gửi hoặc dùng sự kiện cho mục đích
  đã tắt trái với chính sách, kể cả ở đường cache và thử lại.
- Thông điệp còn chờ không tiếp tục được dùng cho mục đích đó.
- Chức năng hỗ trợ cơ bản vẫn hoạt động theo phạm vi đã xác định.
- Dấu vết lựa chọn đủ để truy vết, không chứa nội dung dư thừa.
~~~

Cần thêm phép thử cho người chưa có lựa chọn. Nếu SDK gửi sự kiện trước khi trạng thái được tải, chỉ kiểm tra sau khi giao diện đã hiện “tắt” có thể bỏ sót đường tiết lộ.

Dữ liệu mong đợi phải được xác định độc lập với logic đang kiểm tra. Không để cùng một lỗi chính sách quyết định cả hành vi hệ thống lẫn kết quả mong đợi của phép thử.

### 10.3. Ca minh họa: xóa thất bại một phần

Tạo dữ liệu giả tại kho chính, chỉ mục tìm kiếm và kho phân tích. Xác nhận một yêu cầu xóa hợp lệ, rồi làm một đích nhận lệnh không hoạt động.

Kết quả cần quan sát:

- Phần đã xóa không được tiếp tục phục vụ qua đường khác.
- Phần chưa hoàn tất có trạng thái và cơ chế thử lại rõ ràng.
- Giao diện hoặc API không báo hoàn tất toàn bộ khi còn phần chưa xử lý.
- Gửi lại không xóa nhầm dữ liệu người khác hoặc làm mất dấu trạng thái.
- Sau khi phục hồi đích lỗi, kết quả cuối được đối chiếu.
- Khi phục hồi từ bản sao lưu cũ, thay đổi xóa được áp dụng lại theo thiết kế.

Phải biết phạm vi nào nằm trong phép thử và phạm vi nào còn phụ thuộc bằng chứng bên nhận. Không suy rộng một lượt thử kho chính thành kết luận đã xóa mọi bản sao.

### 10.4. Quản lý bằng chứng

Mỗi lần kiểm chứng cần giữ bản dựng, phiên bản chính sách, schema, môi trường, dữ liệu thử, cấu hình và kết quả. Bằng chứng phải cho thấy đường nào đã được quan sát, không chỉ một ảnh màn hình.

Dùng dữ liệu giả và lọc nội dung trước khi lưu báo cáo. Không tạo một kho dữ liệu cá nhân mới dưới tên “bằng chứng kiểm thử”.

## 11. Đo lường và xử lý đánh đổi

Các chỉ số có thể hỗ trợ theo dõi:

| Chỉ số | Ý nghĩa | Điều không thể suy ra |
| --- | --- | --- |
| Trường có mục đích và thời hạn trên tổng số trường trong phạm vi | Độ đầy đủ của danh mục đã biết | Mọi việc xử lý đều phù hợp |
| Điểm xử lý đã kiểm chứng lựa chọn trên tổng số điểm liên quan | Độ bao phủ đường client, dịch vụ và worker | Không còn điểm xử lý chưa được phát hiện |
| Thời gian thay đổi lựa chọn có hiệu lực | Độ trễ lan truyền thực tế | Dữ liệu cũ đã được xóa |
| Yêu cầu hoàn tất đúng phạm vi và thời hạn đã chọn | Khả năng vận hành quy trình | Mọi bản sao ngoài hệ thống đều đã được kiểm soát |
| Tập dữ liệu quá hạn hoặc lỗi xóa còn mở | Khoảng trống vòng đời | Tập dữ liệu không báo lỗi chắc chắn đã được xóa |
| Thay đổi mục đích đã được đánh giá trước triển khai | Chất lượng quản lý thay đổi | Đánh giá ban đầu sẽ đúng mãi sau khi dữ liệu thay đổi |

Không lấy tỷ lệ trung bình cao để bỏ qua một đường xử lý dữ liệu nhạy cảm ngoài chính sách. Khi báo cáo tỷ lệ, phải giữ rõ mẫu số, phần chưa kiểm chứng, lỗi và ngoại lệ.

### 11.1. Privacy và khả năng điều tra

Xóa hết log có thể làm mất khả năng phát hiện sự cố; ghi quá nhiều lại tạo rủi ro riêng tư. Cần chọn trường đủ để điều tra, quyền đọc, thời hạn và quy trình truy cập đặc biệt. Không dùng nhu cầu điều tra như lý do mặc định để giữ mọi nội dung.

### 11.2. Privacy và khả năng phục hồi

Sao lưu tạo thêm bản sao nhưng có vai trò phục hồi. Cần giới hạn quyền, thời hạn, mục đích sử dụng và điều kiện khi phục hồi. Không biến bản sao lưu thành cách lách việc hết hạn hoặc xóa ở hệ thống đang hoạt động.

### 11.3. Privacy và giá trị phân tích

Dữ liệu chi tiết có thể hữu ích, nhưng mỗi trường và mỗi lần kết hợp làm tăng khả năng mô tả cá nhân. Cần đánh giá dữ liệu ít chi tiết hơn, thời gian ngắn hơn, kết quả tổng hợp hoặc phương án khác có đáp ứng mục tiêu không.

Khi không thể đạt đồng thời yêu cầu, ghi rõ phương án, tác động và quyết định của người có thẩm quyền. Việc chấp nhận rủi ro không tự thay thế các nghĩa vụ đã được xác định.

## 12. Những lỗi tư duy thường gặp

| Cách nói hoặc cách làm | Vấn đề | Hướng sửa |
| --- | --- | --- |
| “Đã mã hóa nên bảo đảm privacy” | Bỏ qua mục đích và vòng đời | Kiểm soát cả thu thập, sử dụng, chia sẻ và lưu giữ |
| “Có ô đồng ý là được dùng cho mọi việc” | Không phân biệt mục đích và điều kiện | Định nghĩa chính sách theo từng hoạt động xử lý |
| “Bỏ tên là dữ liệu ẩn danh” | Có thể còn định danh gián tiếp hoặc khả năng liên kết | Đánh giá toàn tập dữ liệu và bối cảnh người nhận |
| “Tắt trên giao diện là đã dừng” | Worker, SDK hoặc hàng đợi có thể tiếp tục | Kiểm chứng mọi điểm tạo, gửi và xử lý |
| “Xóa bản ghi chính là hoàn tất” | Bỏ sót chỉ mục, phân tích, tệp và phục hồi | Theo dõi trạng thái từng nơi trong phạm vi |
| “Người dùng yêu cầu thì gửi toàn bộ dữ liệu” | Có thể lộ dữ liệu người khác hoặc bí mật | Xác minh, xác định quan hệ và lọc phạm vi |
| “Dữ liệu dẫn xuất không liên quan đến cá nhân” | Suy luận có thể mô tả hoặc tác động tới người cụ thể | Đánh giá đầu vào, khả năng nhận diện và mục đích sử dụng |
| “Log và backup không cần xét” | Vẫn có dữ liệu cùng người có thể tiếp cận | Đưa vào danh mục bản sao và chính sách vòng đời |
| “Nhà cung cấp đã nhận lệnh nên đã xóa” | Nhầm gửi thành công với hoàn tất | Lưu trạng thái và bằng chứng theo cơ chế đã thống nhất |

## 13. Đưa mục tiêu privacy vào vòng đời phát triển

Khi làm rõ nhu cầu, bắt đầu từ mục đích và dữ liệu cần thiết, rồi xác định người liên quan, bên nhận và trách nhiệm. Không bắt đầu bằng việc thu thập mọi thứ để “sau này có thể dùng”.

Khi thiết kế, gắn yêu cầu với biểu mẫu, schema, pipeline, quyền dịch vụ, trạng thái lựa chọn, vòng đời và luồng yêu cầu dữ liệu. Thể hiện cả nơi phát sinh bản sao và cách xử lý khi lỗi.

Khi triển khai, mỗi thay đổi thêm trường, SDK, công việc phân tích hoặc bên nhận phải được xem là khả năng thay đổi phạm vi xử lý. Không coi việc tái sử dụng một tập dữ liệu sẵn có là tự động đáp ứng mục đích mới.

Trước khi phát hành, kiểm tra bằng chứng cho các luồng quan trọng, phần chưa hoàn tất và ngoại lệ. Trong vận hành, theo dõi lỗi lan truyền lựa chọn, dữ liệu quá hạn, yêu cầu thất bại và kết quả phục hồi.

Một đặc tả privacy có thể triển khai phải trả lời được: **xử lý dữ liệu về ai, để làm gì, cần đến mức nào, ai được nhận, giữ bao lâu, thay đổi hoặc dừng bằng cách nào, và dựa vào bằng chứng nào để xác nhận hệ thống thực hiện đúng**.
