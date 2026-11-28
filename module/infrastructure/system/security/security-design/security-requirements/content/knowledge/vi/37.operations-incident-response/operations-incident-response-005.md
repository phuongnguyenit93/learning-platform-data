# Eradication: đặc tả và kiểm chứng việc loại bỏ xâm nhập

## 1. Mục tiêu bài học

**Eradication** trong ứng phó sự cố là hoạt động loại bỏ sự hiện diện trái phép, cơ chế duy trì truy cập và xử lý những điểm yếu đã cho phép sự cố trong phạm vi được xác định. Kết quả cần được chứng minh bằng bằng chứng kỹ thuật và quyết định có trách nhiệm, thay vì chỉ dựa vào việc cảnh báo đã ngừng xuất hiện.

Trong module Security Requirements, trọng tâm là chuyển mục tiêu “loại bỏ xâm nhập” thành yêu cầu cụ thể cho xác thực, phân quyền, dữ liệu, logging và phục hồi. Nhờ đó, nhóm thiết kế biết hệ thống phải hỗ trợ gì trước khi có sự cố, còn nhóm ứng phó biết cần kiểm tra gì trước khi chuyển phạm vi bị ảnh hưởng sang phục hồi.

NIST SP 800-61 Rev. 3, mục RS.MI-02, đề cập việc loại bỏ cơ chế duy trì truy cập và điểm xâm nhập, đồng thời xác định các máy và dịch vụ bị ảnh hưởng để xử lý điểm yếu. Đây là căn cứ khái niệm cho bài học; các yêu cầu và ví dụ bên dưới là mô hình minh họa riêng. [Nguồn: NIST SP 800-61 Rev. 3](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf#page=41).

Học xong bài này, bạn có thể:

- Phân biệt containment, eradication và recovery theo kết quả cần đạt.
- Lập phạm vi xử lý bao gồm hệ thống, danh tính, bí mật, dữ liệu và đường triển khai liên quan.
- Viết yêu cầu loại bỏ xâm nhập có chủ sở hữu, hành vi và tiêu chí xác minh.
- Tránh để phiên, token, quyền, tác vụ hoặc artifact cũ tạo đường tái xâm nhập.
- Xây dựng bằng chứng và điều kiện chuyển sang phục hồi mà vẫn giữ rõ giới hạn đánh giá.

Mã định danh, thời hạn và tình huống trong bài đều là ví dụ nội bộ. Các thao tác kiểm chứng được mô tả cho môi trường kiểm thử và dữ liệu tổng hợp, không phải hướng dẫn thực hiện thay đổi trên một hệ thống đang có sự cố thật.

## 2. Eradication khác containment và recovery như thế nào?

| Hoạt động | Câu hỏi chính | Ví dụ kết quả |
|---|---|---|
| Containment — khoanh vùng | Làm sao hạn chế thiệt hại và lan rộng ngay lúc này? | Cô lập worker nghi bị xâm nhập, khóa đường quản trị hoặc tạm dừng xuất dữ liệu. |
| Eradication — loại bỏ xâm nhập | Đã loại bỏ hiện diện trái phép, cơ chế quay lại và xử lý điều kiện bị khai thác trong phạm vi chưa? | Loại quyền trái phép, thu hồi bí mật bị lộ, thay thành phần không còn tin cậy và kiểm chứng đường cũ không còn hiệu lực. |
| Recovery — phục hồi | Làm sao đưa chức năng về trạng thái hoạt động được chấp nhận? | Khôi phục dữ liệu, mở lại luồng nghiệp vụ và theo dõi hệ thống đã được xác minh. |

Ba nhóm hoạt động có thể chồng lấn và phải điều chỉnh theo phát hiện mới. Playbook của CISA mô tả việc tiếp tục phân tích và theo dõi sau eradication; nếu có hoạt động đối phương mới, cần khoanh vùng và đánh giá lại phạm vi. [Nguồn: CISA Incident and Vulnerability Response Playbooks, phần Eradication & Recovery](https://www.cisa.gov/sites/default/files/2024-08/Federal_Government_Cybersecurity_Incident_and_Vulnerability_Response_Playbooks_508C.pdf).

Ví dụ, tắt một tài khoản bị chiếm dụng là biện pháp khoanh vùng hữu ích. Nhưng nếu đối phương đã tạo thêm danh tính máy và sao chép khóa triển khai, chỉ tắt tài khoản ban đầu chưa loại được khả năng truy cập.

Tương tự, vá điểm yếu đã bị khai thác không tự loại bỏ phiên đang hoạt động hoặc quyền trái phép đã được cấp trước đó.

### 2.1. Kết quả không thể suy ra chỉ từ một hành động

- Xóa một tệp đáng ngờ chưa chứng minh mọi cơ chế duy trì truy cập đã được xử lý.
- Khởi động lại tiến trình chưa chứng minh cấu hình và danh tính đã trở về trạng thái được duyệt.
- Dựng lại máy chưa thu hồi được bí mật đã bị sao chép.
- Đổi mật khẩu chưa chắc làm mọi phiên và token cũ mất hiệu lực.
- Phục hồi từ bản sao lưu cũ chưa chứng minh bản sao nằm ngoài khoảng bị xâm nhập.

Eradication cũng không làm dữ liệu đã bị lấy đi trở lại bí mật. Việc đánh giá tác động và xử lý hậu quả của lộ dữ liệu vẫn cần được theo dõi riêng.

## 3. Những câu hỏi phải trả lời trước khi lập kế hoạch

Một kế hoạch có thể hành động được cần xác định:

1. Đã biết gì về đường truy cập ban đầu và những điều kiện bị khai thác?
2. Đối phương đã đạt được quyền gì, trên danh tính và tài sản nào?
3. Có thể còn đường truy cập thay thế hoặc trạng thái tồn tại nào?
4. Bằng chứng nào cần được bảo toàn trước các thay đổi làm mất trạng thái?
5. Tài sản hoặc nguồn triển khai nào vẫn có thể dùng làm điểm tin cậy?
6. Hành động nào phải phối hợp để tránh cấp lại quyền truy cập trong lúc xử lý?
7. Cần bằng chứng gì để cho phép chuyển từng phạm vi sang phục hồi?
8. Điều gì sẽ khiến nhóm mở rộng phạm vi hoặc quay lại khoanh vùng?

Không cần đợi biết mọi chi tiết mới ngăn chặn thiệt hại đang xảy ra. Tuy nhiên, những phần chưa biết phải được ghi rõ và ảnh hưởng tới quyết định về mức tin cậy, cách dựng lại và điều kiện mở lại.

## 4. Quản lý phạm vi: đừng chỉ lập danh sách máy bị cảnh báo

### 4.1. Phạm vi theo tài sản và quan hệ tin cậy

| Nhóm | Đối tượng cần xem xét |
|---|---|
| Hạ tầng và runtime | Máy, container, worker, cấu hình khởi động, lịch chạy và công cụ quản trị trong phạm vi. |
| Danh tính | Người dùng, quản trị viên, tài khoản máy, phiên, token, phương thức khôi phục và quan hệ ủy quyền. |
| Quyền | Vai trò, nhóm, chính sách, quyền tenant, quyền kho tệp, quyền triển khai và quyền quản lý bí mật. |
| Bí mật và khóa | API key, thông tin kết nối, khóa ký, chứng thư hoặc khóa mã hóa có thể đã bị tiếp cận. |
| Chuỗi triển khai | Mã nguồn, runner, cấu hình pipeline, kho artifact, image và danh tính phát hành. |
| Dữ liệu và trạng thái | Hồ sơ nghiệp vụ, tác vụ chờ, tệp xuất, liên kết tải, snapshot, backup và dữ liệu tạm. |
| Quan sát | Audit, log, cấu hình thu thập, quyền xóa và khoảng trống dữ liệu quan sát. |
| Tích hợp | Hệ thống ngoài, tài khoản nhà cung cấp và các đường trao đổi bí mật hoặc dữ liệu liên quan. |

Không mặc định tất cả đều bị xâm nhập. Mục tiêu là xác định đối tượng cần điều tra và cơ sở quyết định xử lý.

### 4.2. Phân biệt biết chắc, nghi ngờ và chưa đánh giá

Có thể ghi cho mỗi đối tượng:

- Đã xác nhận bị ảnh hưởng, kèm bằng chứng.
- Có khả năng phơi lộ do quyền hoặc quan hệ truy cập, cần đánh giá.
- Đã đánh giá trong phạm vi cụ thể, chưa thấy dấu hiệu liên quan.
- Chưa đủ dữ kiện hoặc chưa đánh giá.

“Chưa thấy dấu hiệu” khác với “đã chứng minh không bị ảnh hưởng”. Thời gian quan sát, độ phủ log và nguồn dữ liệu phải đi cùng kết luận.

Một đối tượng bị loại khỏi phạm vi cần có lý do. Ví dụ, khóa nằm ở dịch vụ tách biệt và danh tính bị chiếm dụng không có quyền đọc hoặc sử dụng; kết luận đó cần dựa trên cấu hình và bằng chứng phù hợp, không chỉ dựa vào sơ đồ cũ.

### 4.3. Theo dõi cả trạng thái đã tồn tại

Một instance mới có thể vẫn sử dụng:

- Token còn hiệu lực từ trước.
- Khóa triển khai đã bị sao chép.
- Vai trò trái phép trong hệ thống danh tính.
- Tác vụ chờ được tạo bởi chủ thể bị chiếm dụng.
- Tệp hoặc liên kết tải được phát hành trước khi khoanh vùng.
- Cấu hình độc hại từ kho triển khai dùng chung.

Phạm vi xử lý cần bao phủ các quan hệ này. Chỉ thay runtime mà giữ nguyên nguồn gây tái tạo trạng thái không đáng tin cậy sẽ để lại đường quay lại.

## 5. Bảo toàn bằng chứng và quản lý thay đổi

### 5.1. Lập kế hoạch thu thập trước thay đổi làm mất trạng thái

Tùy loại sự cố, kế hoạch có thể cần trạng thái phiên, danh tính, cấu hình quyền, tiến trình, tác vụ, log hoặc bản sao dữ liệu phục vụ phân tích.

Trước khi xóa, dựng lại hoặc thu hồi hàng loạt, cần xác định:

- Những bằng chứng nào cần thu trong thời gian cho phép.
- Ai được thu và lưu ở đâu.
- Cách bảo vệ nguồn gốc, thời điểm và tính toàn vẹn.
- Thao tác nào sẽ làm mất dữ liệu còn cần.
- Trường hợp khẩn cấp nào cho phép hành động trước và cách ghi lại lý do.

Không biến thu thập bằng chứng thành điều kiện trì hoãn vô hạn khi thiệt hại đang tiếp diễn. Quyết định đánh đổi cần đúng thẩm quyền và được ghi nhận.

### 5.2. Bằng chứng và bản dùng để thao tác

Bản dùng phân tích và bản được dùng để dựng lại hoặc kiểm thử cần được quản lý riêng theo mục đích. Không sửa trực tiếp nguồn bằng chứng chỉ để thuận tiện cho việc xử lý.

Bản băm có thể giúp đối chiếu một tệp có thay đổi hay không; tự nó không chứng minh tệp đến từ nguồn đáng tin cậy hoặc không chứa nội dung độc hại.

Hồ sơ cần ghi người thu, nguồn, thời điểm, mã sự cố, các lần chuyển giao quan trọng và quyền truy cập. Không đưa token, khóa hoặc dữ liệu khách hàng vào báo cáo phổ biến rộng chỉ để minh họa.

### 5.3. Nhật ký hành động

Mỗi hành động eradication nên có:

- Mã hành động và liên kết tới phát hiện hoặc rủi ro.
- Đối tượng, phạm vi và trạng thái trước.
- Người thực hiện, người phê duyệt theo quy trình.
- Thời điểm, thay đổi và kết quả quan sát.
- Bằng chứng xác minh và giới hạn.
- Phần chưa đạt, người chịu trách nhiệm và bước tiếp theo.

Lưu cả hành động thất bại hoặc phải đổi phương án. Việc xóa dấu vết trong hệ thống vận hành không đồng nghĩa được xóa lịch sử ứng phó.

## 6. Chuyển mục tiêu eradication thành yêu cầu

Một mẫu đặc tả:

> Với [phạm vi và điều kiện sự cố], [thành phần hoặc vai trò] phải [hành vi loại bỏ hoặc hỗ trợ], trong [mốc hoặc giới hạn], đồng thời giữ [điều kiện bảo vệ]. Xác minh bằng [thử nghiệm, đối chiếu hoặc bằng chứng] trước khi [mốc quyết định].

Bộ yêu cầu minh họa cho dịch vụ hồ sơ:

| Mã | Yêu cầu cần có |
|---|---|
| ERAD-SCOPE-01 | Mỗi tài sản, danh tính và bí mật trong phạm vi phải có trạng thái đánh giá, chủ sở hữu và quyết định xử lý liên kết với bằng chứng. |
| ERAD-ID-01 | Phiên và thông tin xác thực bị xác định cần thu hồi phải mất khả năng truy cập tại các điểm thực thi thuộc phạm vi trong tối đa 5 phút từ mốc thu hồi được ghi nhận. |
| ERAD-AZ-01 | Quyền và quan hệ ủy quyền trái phép phải được loại bỏ; dữ kiện cache và các đường truy cập thay thế không được duy trì hiệu lực ngoài giới hạn đã quy định. |
| ERAD-KEY-01 | Bí mật được đánh giá bị lộ phải được thay thế hoặc thu hồi theo kế hoạch; hệ thống sử dụng phải ngừng chấp nhận giá trị cũ ở phạm vi được cam kết. |
| ERAD-BUILD-01 | Thành phần không còn tin cậy chỉ được thay bằng artifact và cấu hình có nguồn được xác minh, không lấy lại trực tiếp từ môi trường bị xâm nhập. |
| ERAD-LOG-01 | Hành động ứng phó và quyết định chuyển giai đoạn phải có lịch sử được bảo vệ; kênh quan sát cần hoạt động và khoảng trống phải được ghi rõ. |
| ERAD-VERIFY-01 | Trước khi mở lại, phải kiểm chứng đường truy cập cũ, quyền hiện hành, dữ liệu và cơ chế quan sát theo phạm vi; phần chưa đạt phải được thể hiện trong quyết định. |

Giới hạn 5 phút ở đây là ví dụ để làm rõ phép đo, không phải thời hạn áp dụng chung. Tổ chức phải chọn theo rủi ro và khả năng thực thi toàn đường.

Một câu như “đã đổi khóa” chỉ là mô tả hành động. Yêu cầu đầy đủ cần chứng minh giá trị cũ không còn được chấp nhận tại các nơi liên quan và giá trị mới không bị đưa trở lại môi trường chưa tin cậy.


## 7. Xử lý danh tính, phiên và bí mật theo toàn bộ đường tin cậy

### 7.1. Lập danh sách điều cần thu hồi

Không chỉ ghi “đổi mật khẩu tài khoản X”. Cần xác định:

- Phiên trình duyệt và phiên quản trị.
- Access token, refresh token và thông tin cho phép cấp token mới.
- API key và danh tính máy.
- Phương thức khôi phục hoặc thiết bị xác thực được thêm trái phép.
- Quyền ủy quyền cho ứng dụng hoặc dịch vụ khác.
- Bí mật đã nằm trong môi trường mà đối phương có khả năng đọc.
- Danh tính phụ hoặc quyền truy cập được tạo trong khoảng cần điều tra.

Một tài khoản bị khóa có thể không còn đăng nhập mới được, nhưng access token đã cấp vẫn được một số dịch vụ chấp nhận nếu chúng chỉ xác minh token tại chỗ. Yêu cầu phải nêu hành vi của cả các điểm thực thi đó.

### 7.2. Xác định mốc và giới hạn thu hồi

Với ERAD-ID-01, cần định nghĩa:

- t0 là thời điểm nguồn quản lý có thẩm quyền ghi nhận thu hồi.
- Những validator, dịch vụ, gateway, worker và đường tải nào thuộc phạm vi.
- Cache, đồng bộ và phiên tồn tại ảnh hưởng ra sao.
- Cách đo thời gian và xử lý sai lệch đồng hồ.
- Điều kiện tạm chặn chức năng nếu kiến trúc chưa thể đạt giới hạn.

Kiểm thử bằng thông tin xác thực của fixture còn hiệu lực trước thu hồi. Sau mốc phải mất hiệu lực, dùng lại đúng loại thông tin đó qua các đường được kiểm kê. Token đã hết hạn từ đầu không chứng minh cơ chế thu hồi hoạt động.

Thời hạn token là một yếu tố thiết kế, nhưng chưa đủ nếu còn khả năng cấp token mới hoặc có đường truy cập dùng loại bí mật khác.

### 7.3. Thay bí mật và ngừng chấp nhận bí mật cũ

Một kế hoạch cần theo dõi ít nhất:

1. Bí mật nào bị lộ hoặc có khả năng bị tiếp cận, với căn cứ nào.
2. Hệ thống phát hành và mọi nơi sử dụng.
3. Môi trường quản trị và phân phối bí mật mới có đủ tin cậy không.
4. Thứ tự chuyển đổi để giảm gián đoạn mà vẫn giới hạn đường cũ.
5. Thời điểm các nơi ngừng chấp nhận giá trị cũ.
6. Kiểm chứng giá trị cũ thất bại và giá trị mới chỉ có quyền được phép.
7. Việc xử lý bản cấu hình, tác vụ hoặc artifact còn chứa tham chiếu cũ.

Không đưa bí mật mới vào một runtime chưa được kiểm soát rồi mặc định đã cắt quyền đối phương. Điều kiện tin cậy của nơi nhận phải nằm trong kế hoạch.

### 7.4. Phân biệt mục đích sử dụng khóa

| Loại | Điều cần làm rõ khi bị ảnh hưởng |
|---|---|
| API key | Ai phát hành, consumer nào dùng, nơi nào còn chấp nhận key cũ và quyền key mới. |
| Khóa ký token | Những điểm xác minh nào còn tin khóa cũ, cách xử lý cache và token đã cấp, điều kiện ngừng chấp nhận cho xác thực. |
| Khóa hoặc chứng thư dùng cho kết nối | Những bên nào thực sự thực thi thay đổi tin cậy; không mặc định mọi bên đều phản ứng giống nhau. |
| Khóa bảo vệ dữ liệu | Dữ liệu và bản sao nào có thể đã phơi lộ, kế hoạch chuyển khóa hoặc mã hóa lại phù hợp và khả năng phục hồi. |
| Khóa ký artifact | Artifact nào cần đánh giá lại, nguồn dựng và chuỗi phát hành có còn đáng tin cậy không. |

Tạo một khóa mới không tự làm dữ liệu đã bị đọc hoặc bí mật đã bị sao chép trở lại an toàn. Việc giữ khóa công khai để đối chiếu bằng chứng lịch sử cũng là mục đích khác với tiếp tục tin khóa đó để cấp quyền truy cập hiện tại.

Không xoay mọi khóa chỉ vì có sự cố mà không xác định phụ thuộc và căn cứ. Cũng không loại một khóa khỏi đánh giá chỉ vì chưa có cảnh báo trực tiếp về nó.

## 8. Loại quyền trái phép và cơ chế duy trì truy cập

### 8.1. Đối chiếu với quyền được duyệt

Rà soát theo phạm vi có thể gồm:

- Thành viên nhóm và vai trò.
- Chính sách cấp quyền trên tài nguyên.
- Quan hệ tin cậy hoặc ủy quyền.
- Quyền truy cập kho bí mật và triển khai.
- Quyền trực tiếp trên kho tệp hoặc đường tải.
- Tài khoản máy, khóa được thêm và cơ chế khôi phục.
- Lịch chạy hoặc cấu hình tự động có thể tái tạo trạng thái trái phép.

Mốc quyền được duyệt cần có căn cứ hiện hành. Khôi phục toàn bộ quyền từ một backup cũ có thể làm mất thay đổi hợp lệ hoặc đưa quyền đã thu hồi trở lại.

Không mặc định mọi tài khoản tạo trong khoảng sự cố đều trái phép. Cần phân loại và đối chiếu nguồn phê duyệt.

### 8.2. Kiểm tra điểm thực thi, không chỉ màn hình quản trị

Sau khi xóa một grant, kiểm tra:

1. Nguồn quyền đã cập nhật đúng.
2. Cache và bản sao phục vụ quyết định quyền phản ánh thay đổi trong giới hạn.
3. API trực tiếp từ chối hành động tương ứng.
4. Worker không chỉ tin snapshot quyền trong tác vụ cũ.
5. Đường tải và quyền kho không đi vòng cơ chế mới.
6. Một cơ chế đồng bộ hoặc lịch chạy không tự cấp lại quyền.

Kết quả “vai trò không còn hiện trên giao diện” chưa chứng minh toàn bộ đường truy cập đã mất hiệu lực.

### 8.3. Quyền phục vụ ứng phó cũng cần kết thúc

Trong xử lý sự cố, nhóm có thể dùng danh tính khẩn cấp hoặc quyền tạm thời. Chúng cần có phạm vi, người chịu trách nhiệm, thời hạn và lịch sử sử dụng.

Trước khi kết thúc phần việc tương ứng, đối chiếu quyền tạm đã được thu hồi hoặc chuyển sang trạng thái được phê duyệt rõ ràng. Một cơ chế hỗ trợ ứng phó không nên trở thành đường quản trị không được theo dõi.

## 9. Xử lý runtime, điểm yếu và nguồn triển khai

### 9.1. Chọn sửa tại chỗ hay dựng lại theo mức tin cậy

Cần xem xét:

- Mức quyền mà đối phương đã có.
- Khả năng thay đổi runtime, cấu hình và công cụ quan sát.
- Độ đầy đủ của bằng chứng.
- Có thể xác minh trạng thái sau sửa tới đâu.
- Nguồn dựng lại và thời gian cần thiết.
- Rủi ro nếu bỏ sót cơ chế duy trì truy cập.

Nếu không đủ căn cứ tin cậy runtime, dựng lại từ nguồn được xác minh có thể là phương án phù hợp. Tuy nhiên, hành động đó vẫn phải phối hợp với xử lý danh tính, bí mật và nguồn triển khai.

Không coi “máy mới” là sạch nếu nó tự tải cùng artifact bị sửa hoặc nhận cấu hình từ nguồn chưa được đánh giá.

### 9.2. Xác minh nguồn dựng lại

Hồ sơ cần chỉ ra:

- Phiên bản mã, dependency, cấu hình và artifact được chọn.
- Nguồn cung cấp và quyền thay đổi tại nguồn đó.
- Pipeline, runner và danh tính phát hành liên quan.
- Cách đối chiếu nội dung với mốc được duyệt.
- Kết quả kiểm thử và kiểm tra bảo mật phù hợp.
- Các giả định chưa được xác nhận.

Chữ ký hoặc hash chỉ có ý nghĩa trong chuỗi tin cậy cụ thể. Nếu nguồn phát hành hoặc khóa ký đã bị ảnh hưởng, việc artifact có chữ ký không tự chứng minh nó phù hợp để dựng lại.

### 9.3. Xử lý điểm yếu đã bị khai thác

Nếu điểm vào là lỗi phần mềm, cần liên kết bản sửa với hành vi đã cho phép xâm nhập và ca kiểm thử hồi quy. Nếu điểm vào là cấu hình hoặc quy trình, cần xác minh thay đổi tương ứng chứ không chỉ cài thêm bản vá không liên quan.

Ví dụ:

- Kiểm tra quyền quản trị phải diễn ra ở phía máy chủ.
- Token không được ghi vào log ở những đường đã xác định.
- Kho log không cho danh tính ngoài phạm vi đọc nội dung nhạy cảm.
- Tài khoản vận hành không có quyền triển khai hoặc đọc bí mật vượt nhu cầu được duyệt.

Một biện pháp chặn tạm vẫn có thể cần thiết khi chưa có bản sửa hoàn chỉnh. Hồ sơ phải thể hiện đó là biện pháp tạm, giới hạn, thời hạn và phần rủi ro còn lại. Không đổi tên biện pháp khoanh vùng thành “đã sửa nguyên nhân” để đóng việc.

## 10. Dữ liệu, tác vụ, tệp và bản sao lưu

### 10.1. Loại quyền truy cập không thay thế sửa tính toàn vẹn

Sau khi ngăn truy cập trái phép, vẫn cần đánh giá:

- Dữ liệu có bị sửa, xóa hoặc thêm không.
- Tác vụ có bị thay đầu vào, tenant hoặc chủ thể không.
- Kết quả xuất có đúng phạm vi và người nhận không.
- Cấu hình nghiệp vụ có bị thay để tạo hậu quả về sau không.
- Backup hoặc artifact phục hồi có nằm trong khoảng cần điều tra không.

Việc sửa dữ liệu phải dựa trên nguồn đối chiếu và quyết định phù hợp. Không xóa mọi thay đổi trong khoảng sự cố mà bỏ qua giao dịch hợp lệ.

### 10.2. Tác vụ đã nhận và liên kết đã phát hành

Với luồng bất đồng bộ, kế hoạch cần quyết định:

- Tác vụ nào bị hủy, giữ để phân tích hoặc cho phép tiếp tục.
- Worker kiểm tra lại danh tính và quyền ở những điểm nào.
- Tệp nào phải ngừng công bố hoặc khóa truy cập.
- Liên kết cũ có thể mang quyền truy cập độc lập hay không.
- Có cơ chế tạo lại tệp hoặc cấp lại quyền tải không.
- Bằng chứng và dữ liệu tạm được lưu hoặc dọn theo vòng đời nào.

Ẩn nút tải hoặc tắt API tạo tác vụ chưa tự vô hiệu hóa liên kết đã tồn tại. Kiểm chứng phải đi qua chính các đường đó.

### 10.3. Đánh giá bản phục hồi

Bản sao lưu trước thời điểm phát hiện chưa chắc nằm trước thời điểm xâm nhập. Cần xác định nguồn, mốc dữ liệu, dấu hiệu liên quan và điều kiện sử dụng.

Khi phục hồi, chú ý dữ liệu có thể chứa quyền cũ, danh tính trái phép, lịch chạy hoặc cấu hình bị sửa. Không chỉ kiểm tra cơ sở dữ liệu có mở được không.

Một bản được chọn để giữ làm bằng chứng không mặc nhiên là bản phù hợp để đưa trở lại vận hành.

## 11. Ví dụ xuyên suốt: sự cố trong dịch vụ xuất hồ sơ

### 11.1. Phát hiện và giả định đã xác nhận

Sự cố giả định INC-027 có các bằng chứng:

- Một đường log hỗ trợ đã ghi token quản trị.
- Quyền đọc kho log bị cấu hình rộng hơn phạm vi được duyệt.
- Token đó được dùng tạo lịch xuất dữ liệu không được phê duyệt và cấp thêm quyền cho danh tính dịch vụ.
- Một API key của danh tính dịch vụ đã bị đọc trong phạm vi tài khoản bị chiếm dụng.
- Worker có cấu hình ngoài mốc được duyệt; hiện chưa đủ bằng chứng tin cậy toàn bộ runtime.
- Chưa có bằng chứng xác nhận pipeline phát hành bị chiếm dụng, nhưng các hoạt động liên quan cần được đánh giá.

Các phát hiện trên không chứng minh mọi tenant đã mất dữ liệu. Phạm vi dữ liệu bị truy cập cần được phân tích bằng chứng riêng.

### 11.2. Trạng thái sau khoanh vùng

Nhóm đã cô lập worker, ngừng nhận tác vụ xuất và khóa tài khoản quản trị bị ảnh hưởng. Đây là đầu vào cho eradication, chưa phải kết luận hoàn tất.

Những câu hỏi còn mở:

- Token cũ còn được API hoặc dịch vụ nào chấp nhận?
- API key cũ đã bị vô hiệu hóa ở mọi consumer chưa?
- Grant trái phép còn tồn tại trong cache hoặc quyền kho tệp không?
- Lịch xuất có được tái tạo bởi cấu hình dùng chung không?
- Tệp và liên kết đã phát hành còn truy cập được không?
- Logger và quyền kho log đã được sửa, hay token mới vẫn có thể bị lộ?

### 11.3. Kế hoạch theo kết quả cần đạt

| Nhóm việc | Kết quả cần đạt | Bằng chứng chủ yếu |
|---|---|---|
| Danh tính | Token và phiên bị thu hồi không còn truy cập trong phạm vi, đúng giới hạn | Thử dùng lại thông tin fixture, kiểm tra các điểm thực thi và thời gian. |
| Quyền | Grant trái phép và quyền đi vòng được loại; quyền hợp lệ vẫn đúng | Đối chiếu chính sách, cache, API, worker và kho tệp. |
| Bí mật | API key mới được cấp trong môi trường được kiểm soát; key cũ bị từ chối | Danh sách consumer, mốc chuyển đổi và kiểm thử cả cũ lẫn mới. |
| Runtime | Worker được thay từ artifact và cấu hình đã xác minh | Nguồn build, mốc cấu hình, kết quả kiểm thử và đối chiếu trạng thái. |
| Điểm gây lộ | Đường log không còn ghi token; quyền kho log trở về phạm vi được duyệt | Kiểm thử dữ liệu tổng hợp và thử quyền đọc. |
| Trạng thái cũ | Lịch xuất, tác vụ, tệp và liên kết liên quan có quyết định xử lý | Danh sách đối tượng, kiểm tra khả năng truy cập và lịch sử hành động. |
| Quan sát | Audit và kênh phát hiện hoạt động, khoảng trống được ghi | Ca phát sinh sự kiện đối chứng và hồ sơ phạm vi quan sát. |

Ví dụ này minh họa vì sao “đã dựng lại worker” chưa đủ: nguồn token bị lộ, API key và quyền trái phép có thể còn cho phép đối phương quay lại trên worker mới.


## 12. Kiểm chứng kết quả eradication

### 12.1. Dùng kiểm thử chủ động và đối chiếu trạng thái

Không chỉ chờ cảnh báo. Cần kết hợp:

- Đối chiếu danh tính, quyền và cấu hình với nguồn được duyệt.
- Thử lại hành vi từng được cho phép bởi trạng thái bị ảnh hưởng.
- Kiểm tra cơ chế không tự tái tạo sau khởi động lại hoặc đồng bộ.
- Kiểm tra truy cập hợp lệ để tránh kết luận an toàn chỉ vì chức năng đã hỏng.
- Quan sát sự kiện và hành vi sau thay đổi trong phạm vi được chọn.

Trong diễn tập của INC-027, nhóm chọn giới hạn 5 phút cho thu hồi phiên và quyền liên quan. Các ca dùng fixture mô phỏng, không đưa bí mật thật của sự cố vào bộ kiểm thử.

| Ca | Điều kiện và hành động | Kết quả cần chứng minh |
|---|---|---|
| TC-ERAD-01 | Thông tin xác thực ban đầu còn hợp lệ, sau đó bị thu hồi; thử qua các điểm thực thi đã kiểm kê | Không còn truy cập sau giới hạn; không chỉ bị từ chối vì token đã hết hạn từ đầu. |
| TC-ERAD-02 | Loại grant trái phép, thử API, worker và đường tải; kiểm tra cache | Không giữ quyền ngoài giới hạn và không có đường bỏ qua. |
| TC-ERAD-03 | Chuyển API key ở các consumer | Key cũ bị từ chối; key mới hoạt động đúng quyền được duyệt. |
| TC-ERAD-04 | Tạo lỗi và hoạt động bằng dữ liệu giả có dấu nhận diện token | Log mới không chứa token; quyền đọc kho log đúng phạm vi; audit cần thiết vẫn có. |
| TC-ERAD-05 | Khởi động worker từ nguồn đã xác minh, kiểm tra cấu hình và lịch chạy | Không tái tạo cấu hình hoặc lịch trái phép; kết quả nghiệp vụ đúng. |
| TC-ERAD-06 | Thử tệp và liên kết cũ thuộc fixture | Không tiếp tục đọc dữ liệu qua đường đã bị thu hồi hoặc bị loại khỏi phạm vi hoạt động. |
| TC-ERAD-07 | Chủ thể hợp lệ thực hiện tác vụ đúng tenant | Kiểm soát không bị “đạt giả” do toàn bộ dịch vụ ngừng hoạt động. |

Mỗi ca cần phiên bản, cấu hình, mốc thời gian và nguồn quan sát. Không dùng danh tính observer có quyền cao để thay cho danh tính đang được thử.

### 12.2. Kiểm tra cả kết quả tới muộn

Một request bị từ chối có thể đã tạo tác vụ trước đó. Một worker bị dừng có thể được cơ chế tự động khởi động lại. Một liên kết cũ có thể không đi qua API mới.

Vì vậy, oracle cần xem:

- Phản hồi và dữ liệu trả về.
- Bản ghi công việc và hàng đợi liên quan.
- Trạng thái quyền và dữ liệu có thẩm quyền.
- Tệp, quyền tải và kết quả được công bố.
- Lịch chạy, cấu hình và cơ chế tự động.
- Audit theo requestId hoặc operationId.

Với xử lý bất đồng bộ, xác định điểm hoàn tất hoặc dấu mốc xử lý. Chỉ chờ một khoảng ngắn rồi không thấy kết quả chưa đủ chứng minh không còn tác dụng phụ.

### 12.3. Theo dõi sau hành động

Thời gian quan sát phải gắn với hành vi cần phát hiện, lịch chạy, chu kỳ đồng bộ và độ phủ của nguồn dữ liệu. Không có một số giờ cố định đủ để chứng minh mọi hệ thống đã loại bỏ xâm nhập.

Nếu kênh quan sát không hoạt động, không có cảnh báo mới là bằng chứng yếu. Nếu xuất hiện dấu hiệu mới, cần đánh giá lại phạm vi và biện pháp khoanh vùng, thay vì chỉ kéo dài bộ đếm “thời gian sạch”.

Theo dõi hỗ trợ quyết định; nó không thay thế kiểm chứng thu hồi quyền, nguồn triển khai và bản sửa.

## 13. Điều kiện chuyển sang phục hồi

### 13.1. Một cổng quyết định có thể kiểm tra

Trước khi mở lại một phạm vi, cần trả lời được:

1. Phạm vi bị ảnh hưởng và các giả định quan trọng đã được đánh giá tới mức nào?
2. Hiện diện và cơ chế duy trì truy cập đã xác định được xử lý ra sao?
3. Danh tính, bí mật và quyền liên quan đã mất hiệu lực theo yêu cầu chưa?
4. Điểm yếu đã bị khai thác được sửa hoặc có quyết định bảo vệ phù hợp cho đúng phạm vi chưa?
5. Runtime, cấu hình, dữ liệu và nguồn phục hồi có đủ căn cứ tin cậy không?
6. Các đường truy cập cũ và trạng thái tồn tại đã được kiểm chứng chưa?
7. Quan sát và audit cần thiết có hoạt động không?
8. Phần chưa đạt có còn tạo đường vào phạm vi định mở không?
9. Ai xác nhận bằng chứng và ai quyết định mở lại?

Không yêu cầu một tuyên bố tuyệt đối rằng đối phương không thể còn ở bất cứ đâu. Quyết định phải nêu phạm vi, bằng chứng, mức chưa chắc chắn và điều kiện theo dõi.

### 13.2. Phần chưa xử lý không được che trong trạng thái chung

Có thể tách:

- Phần đã đạt điều kiện eradication và đủ đầu vào cho phục hồi.
- Phần còn đang xử lý, tiếp tục bị cách ly hoặc không được mở.
- Phần cần đánh giá thêm do thiếu bằng chứng.
- Cải tiến dài hạn không thay thế hành động bắt buộc của sự cố hiện tại.

Nếu một tài sản vẫn có khả năng cấp lại quyền hoặc đưa cấu hình không tin cậy vào phần định mở, việc giữ nó ngoài danh sách nhưng vẫn cho tích hợp không giải quyết được rủi ro.

Một ngoại lệ, nếu quy trình cho phép, phải có phạm vi, thời hạn, biện pháp bảo vệ, người chịu trách nhiệm và thẩm quyền chấp nhận rủi ro. Ngoại lệ không biến một thiếu hụt thành bằng chứng đã xử lý.

### 13.3. Quay lui và phương án dự phòng

Quay lui triển khai không được âm thầm đưa lại:

- Bí mật đã bị lộ.
- Artifact hoặc cấu hình không còn tin cậy.
- Quyền đã xác định trái phép.
- Tệp và liên kết đã bị khóa.
- Đường log ghi token.

Phương án dự phòng cần chỉ rõ nguồn và điều kiện bảo vệ. Nếu bản cũ không đáp ứng, có thể cần giữ chức năng bị ảnh hưởng ngừng hoạt động trong khi dùng phương án khác đã được quyết định.

## 14. Hồ sơ eradication và trách nhiệm

### 14.1. Phân công theo kết quả

| Vai trò | Trách nhiệm minh họa |
|---|---|
| Điều phối sự cố | Tổng hợp phạm vi, phụ thuộc, thứ tự hành động và quyết định cần thiết. |
| Nhóm danh tính | Phiên, token, phương thức khôi phục, danh tính máy và quyền liên quan. |
| Chủ dịch vụ | Luồng nghiệp vụ, tác vụ, tệp, dữ liệu và hành vi các điểm thực thi. |
| Nhóm hạ tầng hoặc nền tảng | Runtime, cấu hình, nguồn dựng và quan hệ quản trị trong phạm vi. |
| Nhóm phát triển | Sửa điểm yếu phần mềm, cấu hình ứng dụng và kiểm thử hồi quy. |
| Nhóm quan sát hoặc ứng phó | Bằng chứng, truy vết, phát hiện và giới hạn quan sát. |
| Người có thẩm quyền | Quyết định các đánh đổi và cho phép chuyển phạm vi theo quy trình. |

Vai trò có thể do cùng người đảm nhiệm ở nhóm nhỏ, nhưng trách nhiệm không được bỏ trống. Khi dùng nhà cung cấp, cần biết hành động nào do họ thực hiện, bằng chứng nào họ cung cấp và phần nào tổ chức vẫn phải tự kiểm tra.

### 14.2. Cấu trúc hồ sơ minh họa

Ví dụ sau là nội dung tài liệu, không phải cấu hình thực thi:

```yaml
incident_id: INC-027
work_package: ERAD-EXPORT-01
scope:
  - Danh tính quản trị và danh tính dịch vụ bị ảnh hưởng
  - Worker xuất hồ sơ
  - Quyền kho log và đường ghi token
  - Tác vụ, tệp và liên kết liên quan
requirement_refs:
  - ERAD-ID-01
  - ERAD-AZ-01
  - ERAD-KEY-01
  - ERAD-BUILD-01
  - ERAD-LOG-01
  - ERAD-VERIFY-01
actions:
  - action_id: ACT-KEY-03
    objective: Ngừng chấp nhận API key cũ ở các consumer trong phạm vi
    owner: Nhóm dịch vụ
    execution_state: IMPLEMENTED
    verification_state: PENDING
    evidence_refs: []
open_questions:
  - Một đường tải cũ còn cần được xác minh
transition:
  recovery_ready: false
  reason: Chưa đủ bằng chứng về key cũ và đường tải
```

IMPLEMENTED không có nghĩa đã xác minh đạt. Hồ sơ cũng không ghi READY khi còn câu hỏi trọng yếu có thể ảnh hưởng điều kiện mở lại.

Bằng chứng thực tế cần liên kết tới đúng phiên bản ứng dụng, cấu hình, danh tính và thời điểm. Không thay danh sách thiếu dữ kiện bằng một ghi chú chung “đã xử lý”.

## 15. Thiết kế sẵn khả năng eradication trong sản phẩm

Một tổ chức sẽ khó thực hiện yêu cầu nếu kiến trúc không hỗ trợ. Các năng lực cần được đặc tả trong vòng đời phát triển gồm:

- Kiểm kê được nơi dùng một danh tính, key hoặc loại token.
- Thu hồi và kiểm chứng hiệu lực trên các điểm thực thi.
- Phân tách quyền quản trị danh tính, triển khai, log và backup phù hợp mô hình rủi ro.
- Dựng lại từ nguồn có thể xác minh thay vì phụ thuộc cấu hình chỉ có trên máy đang chạy.
- Quản lý tác vụ theo định danh ổn định, trạng thái rõ và chính sách kiểm tra quyền.
- Khóa hoặc ngừng công bố kết quả mà không chỉ dựa vào giao diện.
- Ghi audit cho thay đổi quyền, bí mật, cấu hình và quyết định ứng phó.
- Bảo vệ bằng chứng và giới hạn dữ liệu nhạy cảm trong log.
- Diễn tập đổi bí mật, dựng lại và chuyển sang phục hồi bằng fixture.

Nếu một access token không có cơ chế thu hồi đáp ứng thời hạn đã chọn, đó là khoảng thiếu giữa yêu cầu và kiến trúc. Cần giải quyết trước hoặc có phương án giới hạn phạm vi được quyết định rõ, không chờ sự cố mới phát hiện.

### 15.1. Đo tiến độ mà không tạo cảm giác hoàn tất giả

Có thể theo dõi:

- Đối tượng chưa được đánh giá trong phạm vi.
- Đường truy cập chưa xác minh thu hồi.
- Bí mật đã thay nhưng còn consumer chấp nhận giá trị cũ.
- Hành động đã triển khai nhưng chưa có bằng chứng.
- Tài sản còn dùng nguồn dựng hoặc cấu hình chưa xác minh.
- Khoảng trống quan sát và thời gian chưa được đối chiếu.
- Phần việc tạm thời, ngoại lệ sắp hết hạn và quyền ứng phó chưa kết thúc.

Nếu tính thời gian hoàn tất, phải định nghĩa điểm bắt đầu và điều kiện kết thúc. Không dùng thời điểm xóa tệp đầu tiên hoặc cảnh báo cuối cùng làm đại diện cho toàn bộ eradication.

Tỷ lệ hoàn thành chỉ hữu ích khi mẫu số và phạm vi rõ. Không biến phần trăm hành động đã đóng thành phần trăm chắc chắn rằng không còn xâm nhập.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Chỉ xóa artifact bị phát hiện | Bỏ sót danh tính, quyền hoặc cơ chế tái tạo | Lập phạm vi theo quan hệ tin cậy và kiểm chứng đường quay lại. |
| Dựng lại nhưng giữ bí mật đã lộ | Đối phương có thể truy cập môi trường mới | Phối hợp xử lý runtime với thu hồi và phân phối bí mật. |
| Đổi mật khẩu rồi coi mọi phiên mất hiệu lực | Token hoặc phiên khác có thể vẫn dùng được | Kiểm tra từng loại thông tin xác thực và điểm thực thi. |
| Chỉ xóa grant ở nguồn | Cache, quyền kho hoặc tác vụ cũ vẫn cho phép | Kiểm thử toàn đường và trạng thái tồn tại. |
| Dùng image có chữ ký mà không đánh giá nguồn ký | Chuỗi phát hành có thể đã bị ảnh hưởng | Kiểm tra căn cứ tin cậy của nguồn, pipeline và khóa. |
| Xóa log để loại token bị ghi | Mất bằng chứng mà chưa chắc ngăn truy cập | Thu hồi thông tin lộ, bảo vệ bằng chứng và sửa nguồn gây lộ. |
| Coi backup trước cảnh báo là sạch | Xâm nhập có thể xảy ra sớm hơn | Đánh giá mốc, nội dung và quyền trước khi dùng phục hồi. |
| Không có cảnh báo nên đóng việc | Kênh phát hiện có thể thiếu hoặc hỏng | Xác minh quan sát và kết hợp kiểm thử chủ động. |
| Tắt UI nhưng giữ liên kết tải | Đường truy cập độc lập vẫn hoạt động | Kiểm tra quyền tại mọi đường tải thuộc phạm vi. |
| Đưa runtime cũ trở lại khi rollback | Tái đưa điểm yếu hoặc trạng thái không tin cậy | Có phương án quay lui giữ các điều kiện bảo vệ. |

## 17. Bài tập thực hành

Dịch vụ xuất hồ sơ có một sự cố giả định. Nhóm báo cáo:

1. Worker đã được dựng lại.
2. Mật khẩu quản trị đã đổi.
3. API key mới đã tạo nhưng chưa biết consumer nào còn dùng key cũ.
4. Một grant trái phép đã xóa ở nguồn, nhưng chưa kiểm tra cache.
5. Tệp xuất cũ vẫn tải được bằng liên kết đã phát hành.
6. Không có cảnh báo mới trong 24 giờ; bộ thu log mất kết nối trong 6 giờ đầu.
7. Logger mới không ghi token, nhưng chưa xác minh quyền đọc kho log.
8. Pipeline tạo image mới chưa được đánh giá dù tài khoản bị chiếm dụng có quyền quản lý một phần cấu hình triển khai.

Hãy thực hiện:

- Phân loại điều gì đã làm, điều gì đã được xác minh và điều gì còn chưa biết.
- Lập lại phạm vi theo danh tính, quyền, runtime, bí mật, dữ liệu và quan sát.
- Chọn ít nhất năm yêu cầu có tiêu chí chấp nhận cụ thể.
- Viết một ca kiểm thử token hoặc key cũ và một ca thử đường tải cũ.
- Xác định bằng chứng cần giữ trước các hành động tiếp theo.
- Nêu điều kiện để cho phép một phần dịch vụ phục hồi.
- Ghi quyết định cho các thành phần chưa đủ tin cậy và quan hệ của chúng với phần định mở lại.
- Giải thích vì sao thông tin trên chưa đủ để tuyên bố toàn bộ eradication hoàn tất.

### Gợi ý tự đánh giá

- Dựng lại chỉ là một phần của xử lý; nguồn image và cấu hình cần có căn cứ tin cậy.
- Đổi mật khẩu không thay thế kiểm chứng phiên, token và phương thức cấp thông tin xác thực mới.
- Key mới tồn tại chưa chứng minh key cũ bị từ chối.
- Grant nguồn đã xóa chưa chứng minh toàn bộ điểm thực thi cập nhật.
- Liên kết cũ là một đường truy cập còn phải xử lý hoặc đánh giá theo chính sách, không thể bỏ qua vì chức năng mới đã tắt.
- Khoảng trống log làm giảm độ tin cậy của kết luận “không có hoạt động”.
- Sửa logger và sửa quyền kho log là hai yêu cầu liên quan nhưng riêng biệt.
- Cần quyết định theo từng phạm vi và bằng chứng; không gộp các mục đã làm thành một trạng thái hoàn tất chung.

## 18. Câu hỏi tự kiểm tra

1. Một biện pháp khoanh vùng có thể hữu ích nhưng chưa hoàn tất eradication trong trường hợp nào?
2. Vì sao phải xem cả danh tính và bí mật khi dựng lại hệ thống?
3. “Chưa thấy dấu hiệu” khác “đã đánh giá không bị ảnh hưởng” như thế nào?
4. Cần xác định gì để đo hiệu lực thu hồi trên nhiều dịch vụ?
5. Tại sao một artifact có chữ ký vẫn cần được đánh giá nguồn tin cậy?
6. Những trạng thái cũ nào có thể đưa quyền truy cập trở lại?
7. Vì sao bằng chứng cần được quản lý trước thao tác làm mất trạng thái?
8. Tại sao một cửa sổ không có cảnh báo không đủ làm tiêu chí duy nhất?
9. Điều kiện chuyển sang phục hồi khác trạng thái “đã triển khai hành động” ở điểm nào?
10. Sự cố cần tạo ra yêu cầu hoặc kiểm thử hồi quy mới trong vòng đời phát triển như thế nào?

