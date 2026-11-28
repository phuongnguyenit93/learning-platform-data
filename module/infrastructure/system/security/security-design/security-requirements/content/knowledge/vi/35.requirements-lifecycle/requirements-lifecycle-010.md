# Theo dõi thay đổi yêu cầu bảo mật

## 1. Mục tiêu bài học

Yêu cầu bảo mật tiếp tục thay đổi khi sản phẩm thêm chức năng, mô hình đe dọa được cập nhật, kiến trúc chuyển dịch hoặc kiểm thử phát hiện giả định không còn đúng. Nếu nhóm chỉ sửa câu chữ trong tài liệu hiện tại, người triển khai và người đánh giá có thể không biết điều gì đã thay đổi, tại sao thay đổi và bản phát hành nào đã đáp ứng.

**Theo dõi thay đổi yêu cầu bảo mật** là duy trì lịch sử có thể truy vết từ yêu cầu cũ tới yêu cầu mới, cùng lý do, tác động, quyết định phê duyệt, công việc triển khai và bằng chứng xác minh tương ứng.

Trong module Security Requirements, quá trình này giữ cho các yêu cầu về xác thực, phân quyền, dữ liệu, logging và phục hồi tiếp tục liên kết với rủi ro, kiến trúc và tiêu chí kiểm thử trong vòng đời phát triển.

Học xong bài này, bạn có thể:

- Quản lý định danh, phiên bản và phạm vi có hiệu lực của yêu cầu.
- Phân biệt thay đổi câu chữ với thay đổi nghĩa bảo vệ.
- Lập hồ sơ thay đổi và phân tích tác động tới các thành phần liên quan.
- Xác định bằng chứng nào còn phù hợp, bằng chứng nào cần bổ sung hoặc thực hiện lại.
- Đối chiếu yêu cầu đã phê duyệt với từng bản phát hành đang hoạt động.
- Xử lý đổi phạm vi, tách–gộp yêu cầu, quay lui triển khai và thay đổi khẩn cấp mà vẫn giữ lịch sử.

Mã định danh, trạng thái, thời hạn và cấu trúc hồ sơ trong bài đều là ví dụ nội bộ. Tổ chức cần xác định quy ước phù hợp thay vì coi chúng là một tiêu chuẩn bắt buộc.

## 2. Vì sao chỉ lưu bản mới nhất là chưa đủ?

Giả sử một yêu cầu ban đầu quy định:

> Người dùng có quyền xuất hồ sơ được phép tạo tác vụ xuất dữ liệu của tenant mình.

Sau đó, nhóm phát hiện người dùng có thể bị thu hồi quyền khi tác vụ vẫn đang chờ. Yêu cầu được bổ sung để worker kiểm tra quyền tại thời điểm thực thi và hệ thống kiểm tra quyền khi bắt đầu tải tệp.

Nếu chỉ thay đoạn văn cũ bằng đoạn mới:

- Nhóm API có thể nghĩ phần kiểm tra khi tạo tác vụ đã đủ.
- Nhóm worker không biết mình cần thay đổi.
- Kết quả kiểm thử cũ vẫn hiện màu xanh dù chưa kiểm tra tình huống thu hồi quyền.
- Bản phát hành đang chạy không được phân biệt với bản dự kiến đáp ứng yêu cầu mới.
- Người phê duyệt không biết rủi ro nào dẫn đến thay đổi.

Một lịch sử hữu ích cần nối được chuỗi:

```text
Nguồn thay đổi / phát hiện mới
             |
             v
Rủi ro và giả định bị ảnh hưởng
             |
             v
Yêu cầu cũ -> nội dung khác biệt -> yêu cầu mới
             |
             v
Thiết kế + công việc triển khai + kiểm thử
             |
             v
Bằng chứng theo phiên bản + quyết định phát hành
             |
             v
Trạng thái thực tế trên các môi trường
```

Theo dõi thay đổi không chỉ để biết “ai đã sửa dòng này”. Nó phải giúp xác định ý nghĩa bảo mật của việc sửa và những phần cần làm tiếp theo.

## 3. Đối tượng nào cần được quản lý phiên bản?

### 3.1. Định danh yêu cầu và phiên bản yêu cầu

Một yêu cầu nên có định danh ổn định, ví dụ `SEC-REQ-017`. Nội dung của nó có thể có nhiều phiên bản: `rev-1`, `rev-2`, `rev-3`.

- **Định danh** trả lời: đang nói tới yêu cầu nào?
- **Phiên bản** trả lời: đang nói tới nội dung yêu cầu ở thời điểm nào?
- **Phạm vi có hiệu lực** trả lời: nội dung đó áp dụng cho thành phần, môi trường và mốc nào?

Không tái sử dụng mã của một yêu cầu đã ngừng áp dụng cho một mục đích khác. Nếu làm vậy, kết quả kiểm thử hoặc quyết định cũ có thể bị liên kết nhầm.

Không bắt buộc dùng cách đánh số giống phiên bản phần mềm. Điều quan trọng là quy ước rõ ràng, không sửa âm thầm nội dung đã được phê duyệt và có thể truy xuất phiên bản cũ.

### 3.2. Phân biệt các loại phiên bản

| Đối tượng | Ví dụ | Ý nghĩa |
|---|---|---|
| Phiên bản một yêu cầu | SEC-REQ-017 rev-2 | Nội dung cụ thể của một yêu cầu. |
| Mốc tập yêu cầu đã duyệt | REQ-BASE-2026-11-A | Danh sách chính xác các yêu cầu và phiên bản được chọn cho một phạm vi. |
| Phiên bản thiết kế | DEC-AUTHZ-08 rev-3 | Quyết định kiến trúc được dùng để đáp ứng yêu cầu. |
| Bản xây dựng hoặc phát hành | build-218, release-12 | Đơn vị triển khai phần mềm cụ thể. |
| Lần xác minh | VERIFY-017-06 | Hoạt động kiểm thử hoặc rà soát trên phạm vi xác định. |
| Cấu hình môi trường | prod-config-42 | Cấu hình có thể ảnh hưởng tới hiệu lực kiểm soát khi vận hành. |

Một commit chứa thay đổi tài liệu không tự chứng minh ứng dụng đã triển khai nội dung mới. Một bản build chứa mã sửa cũng chưa chứng minh cấu hình đích và mọi đường truy cập đã đáp ứng.

Trong bài này, **mốc tập yêu cầu đã duyệt** là ảnh chụp một tập yêu cầu cùng phiên bản tại một thời điểm cho một phạm vi cụ thể. Khái niệm này khác với **control baseline**, vốn là tập kiểm soát nền dùng làm đầu vào lựa chọn và đặc tả yêu cầu.

### 3.3. Tài liệu hiện tại và lịch sử quyết định

Có thể cung cấp một bản đọc hiện tại để người dùng dễ tra cứu. Tuy nhiên, cần giữ khả năng truy xuất:

- Nội dung từng phiên bản đã phê duyệt.
- Phần khác biệt giữa các phiên bản.
- Lý do và nguồn thay đổi.
- Người đề xuất, rà soát và quyết định.
- Mốc có hiệu lực và các trường hợp ngoại lệ.
- Bằng chứng xác minh đúng phiên bản.

Không nên bắt người đọc tự suy luận toàn bộ quyết định từ hàng trăm commit sửa dấu câu.

## 4. Phân loại thay đổi trước khi đánh giá tác động

### 4.1. Thay đổi biên tập

Sửa lỗi chính tả, chuẩn hóa thuật ngữ hoặc cải thiện trình bày có thể không thay đổi nghĩa của yêu cầu.

Ví dụ:

> “tài khoản quản tri” → “tài khoản quản trị”.

Vẫn cần có lịch sử, nhưng mức rà soát và xác minh có thể nhẹ hơn nếu người rà soát xác nhận hành vi yêu cầu không đổi.

### 4.2. Thay đổi nghĩa hoặc phạm vi bảo vệ

Các thay đổi sau có thể ảnh hưởng trực tiếp tới triển khai và bằng chứng:

- Đổi “nên” thành “phải”.
- Thêm hoặc bỏ một nhóm người dùng, endpoint, worker hay môi trường.
- Đổi thời hạn phiên, độ trễ thu hồi quyền hoặc thời hạn lưu dữ liệu.
- Đổi nguồn danh tính được tin cậy.
- Thêm hành vi phải có khi phụ thuộc bị lỗi.
- Đổi tiêu chí chấp nhận hoặc phương pháp chứng minh.
- Thêm hoặc bỏ một ngoại lệ.
- Thay đổi giả định về vị trí thực thi kiểm soát.

Ví dụ, sửa “mọi API” thành “mọi API công khai” có thể thu hẹp phạm vi bảo vệ. Không được coi đó là chỉnh câu cho rõ nếu API nội bộ vẫn có khả năng bị truy cập bởi chủ thể không đáng tin cậy.

### 4.3. Thay đổi kỹ thuật nhưng có thể giữ nguyên yêu cầu

Một dịch vụ chuyển từ một cơ chế thực thi quyền sang cơ chế khác có thể vẫn giữ cùng hành vi bắt buộc. Dù câu chữ yêu cầu không đổi, nhóm vẫn phải đánh giá lại thiết kế, tích hợp và bằng chứng.

Ngược lại, một yêu cầu đổi nội dung chưa chắc cần sửa mã nếu triển khai hiện tại đã đáp ứng. Kết luận đó phải có bằng chứng cho phạm vi mới.

Vì vậy cần phân biệt:

- **Thay đổi yêu cầu:** điều hệ thống phải đáp ứng thay đổi.
- **Thay đổi cách đáp ứng:** thiết kế, mã hoặc cấu hình thay đổi.
- **Thay đổi căn cứ đánh giá:** thông tin về rủi ro hoặc bằng chứng thay đổi.

Cả ba đều có thể kích hoạt rà soát quan hệ truy vết.

## 5. Hồ sơ thay đổi tối thiểu

Một hồ sơ thay đổi nên đủ để người không tham gia cuộc họp vẫn hiểu quyết định:

| Trường | Nội dung cần ghi |
|---|---|
| Mã thay đổi | Định danh duy nhất, ví dụ CR-042. |
| Đối tượng và phiên bản | Yêu cầu, tập yêu cầu hoặc thiết kế liên quan. |
| Nội dung trước và sau | Phần thay đổi có ý nghĩa, không chỉ tên file. |
| Nguồn và lý do | Threat modeling, sự cố, yêu cầu nghiệp vụ, kiểm thử hoặc nghĩa vụ đã xác nhận. |
| Rủi ro liên quan | Kịch bản nào xuất hiện, tăng, giảm hoặc chưa được xử lý. |
| Phạm vi | Dịch vụ, luồng dữ liệu, nhóm chủ thể, môi trường và bản phát hành. |
| Phân tích tác động | Kiến trúc, dữ liệu, mã, cấu hình, vận hành, kiểm thử và bằng chứng. |
| Quyết định | Chấp thuận, yêu cầu bổ sung, từ chối hoặc thay thế bằng phương án khác. |
| Trách nhiệm | Chủ thay đổi, nhóm thực hiện, người xác minh và người quyết định rủi ro khi cần. |
| Điều kiện có hiệu lực | Mốc áp dụng, cách chuyển đổi, ngoại lệ và điều kiện phát hành. |
| Liên kết thực hiện | Công việc, quyết định thiết kế, kiểm thử, bằng chứng và bản triển khai. |
| Điều kiện đóng | Các kết quả cần đạt trước khi kết luận thay đổi đã hoàn tất. |

“Khách hàng muốn an toàn hơn” là lý do quá rộng. Nên ghi cụ thể rằng chức năng được mở cho nhiều tenant, quyền có thể bị thu hồi trong khi tác vụ đang chờ và cơ chế cũ chưa bao phủ thời điểm thực thi.

Nếu nguồn thay đổi là nghĩa vụ bên ngoài, cần người phụ trách xác nhận nội dung, phạm vi và mốc áp dụng. Không tự suy ra rằng một nhãn “compliance” có cùng nghĩa cho mọi hệ thống.

## 6. Phân tích tác động theo chuỗi truy vết

Phân tích tác động bắt đầu từ thay đổi về hành vi và phạm vi, sau đó đi qua các liên kết. Không chỉ tìm kiếm mã yêu cầu rồi mặc định mọi nơi không nhắc mã đều không bị ảnh hưởng.

### 6.1. Những câu hỏi cần trả lời

1. Tài sản, chủ thể và kịch bản đe dọa nào thay đổi?
2. Ranh giới tin cậy hoặc giả định kiến trúc nào không còn đúng?
3. Thành phần nào thực thi kiểm soát và thành phần nào có thể đi vòng?
4. Dữ liệu, phiên, token, tác vụ hoặc tệp đã tồn tại có bị ảnh hưởng không?
5. Kiểm soát dùng chung và nhà cung cấp có hỗ trợ hành vi mới không?
6. Kiểm thử nào giữ nguyên, kiểm thử nào cần sửa hoặc thêm?
7. Bằng chứng nào vẫn phù hợp với phạm vi cũ, bằng chứng nào chưa đủ cho phạm vi mới?
8. Chuyển đổi và quay lui có tạo ra khoảng thời gian thiếu bảo vệ không?
9. Ai cần biết, phê duyệt hoặc thực hiện thay đổi?

### 6.2. Ma trận tác động minh họa

| Nhóm yêu cầu thay đổi | Các đối tượng thường cần xem xét |
|---|---|
| Xác thực | Nhà cung cấp danh tính, loại token, khóa xác minh, phiên đang tồn tại, luồng phục hồi tài khoản và đường đăng nhập dự phòng. |
| Phân quyền | Ma trận quyền, nguồn tenant, cache quyền, API, worker, tác vụ chờ, tệp xuất và đường tải dữ liệu. |
| Dữ liệu | Luồng truyền, cơ sở dữ liệu, kho tệp, snapshot, bản sao lưu, dữ liệu tạm, quyền dùng khóa và vòng đời xóa. |
| Logging | Thành phần phát sinh sự kiện, schema sự kiện, nơi thu thập, quyền đọc, thời hạn lưu, truy vấn điều tra và cảnh báo. |
| Phục hồi | Tần suất sao lưu, tính dùng được của bản sao, khóa và cấu hình cần khôi phục, phụ thuộc dịch vụ, kịch bản diễn tập và phép đo. |

Không phải mọi thay đổi đều tác động tới tất cả đối tượng. Với những phần không bị ảnh hưởng, ghi căn cứ đủ rõ để người rà soát hiểu vì sao.

### 6.3. Chú ý trạng thái đã tồn tại

Một yêu cầu mới có thể được triển khai đúng cho yêu cầu tạo mới nhưng vẫn để lại lối đi qua trạng thái cũ:

- Phiên cấp trước khi đổi chính sách vẫn truy cập được.
- Worker xử lý tác vụ cũ bằng snapshot quyền đã lỗi thời.
- Liên kết tải tệp đã phát hành vẫn hoạt động ngoài đường kiểm tra mới.
- Bản sao lưu cũ chưa đáp ứng cơ chế bảo vệ dữ liệu được yêu cầu.
- Quy tắc thu thập log mới không xử lý dữ liệu nhạy cảm đã ghi từ trước.

Hồ sơ thay đổi cần quyết định giữ, chuyển đổi, thu hồi hoặc loại bỏ từng loại trạng thái liên quan. Không mặc định rằng triển khai mã mới đã xử lý hết dữ liệu và quyền truy cập đang tồn tại.

## 7. Quy trình theo dõi thay đổi từ đề xuất tới đóng

### Bước 1: Tiếp nhận và định danh

Tạo mã thay đổi, liên kết nguồn phát hiện và xác định chủ sở hữu. Ghi phiên bản yêu cầu hiện tại trước khi chỉnh sửa.

### Bước 2: Mô tả khác biệt và phân loại

Viết rõ hành vi trước và sau. Xác định thay đổi biên tập, thay đổi nghĩa, thay đổi phạm vi hay thay đổi cách đáp ứng. Phân loại là đầu vào cho mức rà soát, không phải cách né kiểm tra.

### Bước 3: Phân tích tác động và rủi ro

Rà soát chuỗi từ tài sản, đe dọa và yêu cầu tới thiết kế, triển khai, kiểm thử và vận hành. Ghi cả phần chưa biết; khi cần, làm khảo sát có thời hạn trước khi cam kết phương án.

### Bước 4: Quyết định và xác định mốc áp dụng

Người có thẩm quyền quyết định nội dung mới, phạm vi, điều kiện chuyển đổi và phần rủi ro còn lại. Nội dung được phê duyệt không có nghĩa mọi môi trường đã đáp ứng.

### Bước 5: Tạo phiên bản và cập nhật liên kết

Lưu phiên bản mới của yêu cầu, cập nhật các quan hệ thiết kế–kiểm thử–bản phát hành. Giữ phiên bản cũ để tra cứu. Nếu tập yêu cầu đã được chốt cho một bản phát hành, tạo mốc mới hoặc ghi thay đổi có kiểm soát theo quy ước.

### Bước 6: Triển khai và xác minh

Thực hiện thay đổi ở mã, cấu hình và quy trình liên quan. Xác minh cả hành vi mới, các đường thay thế và khả năng hồi quy ở hành vi cũ cần được giữ.

### Bước 7: Đối chiếu với trạng thái triển khai thực tế

Ghi bản nào đã triển khai, cấu hình nào đang bật và phạm vi nào còn dùng cơ chế cũ. Khi triển khai từng phần, không gộp mọi môi trường vào một trạng thái “đã xong”.

### Bước 8: Đóng theo điều kiện đã xác định

Chỉ đóng khi kết quả cần đạt trong phạm vi thay đổi đã được chứng minh, các phần tồn đọng có chủ sở hữu và quyết định hợp lệ, thông tin liên quan đã cập nhật.

Thay đổi bị từ chối hoặc bị thay thế vẫn cần được giữ lịch sử cùng lý do. Không xóa hồ sơ chỉ vì nó không đi tới triển khai.


## 8. Ví dụ xuyên suốt: thu hồi quyền đối với chức năng xuất dữ liệu

### 8.1. Yêu cầu ban đầu và phát hiện mới

Dịch vụ hồ sơ có API tạo tác vụ xuất dữ liệu, worker xử lý hàng đợi và đường tải tệp.

Phiên bản `SEC-REQ-017 rev-1` quy định:

> Chỉ người dùng có quyền xuất hồ sơ trong tenant của mình mới được tạo tác vụ xuất.

Kiểm thử cũ đã chứng minh điều kiện khi tạo tác vụ. Sau đó, threat modeling bổ sung kịch bản:

> Người dùng tạo tác vụ khi còn quyền, bị thu hồi quyền trong lúc chờ, nhưng worker vẫn xuất dữ liệu theo thông tin quyền chụp lúc tạo tác vụ. Người dùng tiếp tục tải tệp bằng liên kết đã phát hành.

Nguồn thay đổi được ghi là `RISK-REVOKE-04`, với hồ sơ đề xuất `CR-042`.

Điểm quan trọng: bằng chứng cũ không nhất thiết sai. Nó chứng minh một phạm vi hẹp hơn điều hệ thống hiện cần bảo vệ.

### 8.2. Nội dung phiên bản mới

Phiên bản `SEC-REQ-017 rev-2` bổ sung:

1. Kiểm tra quyền theo chủ thể, hành động, tenant và tài nguyên khi tạo tác vụ.
2. Worker kiểm tra quyền của chủ thể yêu cầu trước khi đọc dữ liệu để xuất và trước khi công bố kết quả.
3. Mỗi lần bắt đầu tải tệp phải được kiểm tra quyền theo chính sách được áp dụng.
4. Quyết định quyền phải phản ánh việc thu hồi trong tối đa 60 giây từ lúc nguồn quản lý quyền có thẩm quyền ghi nhận thành công sự kiện thu hồi.
5. Nếu không có căn cứ hợp lệ để cho phép theo chính sách, thao tác phải bị từ chối.
6. Không duy trì đường tải thay thế cho phép vượt quá giới hạn thu hồi đã cam kết.

Giới hạn 60 giây là giả định thiết kế trong ví dụ, phải được đánh giá với độ trễ đồng bộ, cache và cơ chế tải. Nó không có nghĩa quyền bị thu hồi tức thời ở mọi nơi.

Phạm vi ở đây là quyết định cho các thao tác mới tại những điểm kiểm tra đã nêu, gồm lúc bắt đầu một lần tải. Yêu cầu chưa khẳng định sẽ thu hồi được dữ liệu đã chuyển hoặc dừng ngay một luồng tải đã bắt đầu hợp lệ. Nếu cần hành vi đó, phải đặc tả thêm phạm vi và cơ chế tương ứng.

Việc làm rõ giới hạn giúp tránh tuyên bố bảo vệ rộng hơn điều kiến trúc có thể chứng minh.

### 8.3. Khác biệt có ý nghĩa bảo mật

| Nội dung | rev-1 | rev-2 |
|---|---|---|
| Thời điểm kiểm tra | Khi tạo tác vụ | Tạo tác vụ, worker trước khi đọc và công bố, bắt đầu tải. |
| Quyền được dùng | Quyền tại lúc tạo tác vụ | Quyền phản ánh thu hồi trong giới hạn đã quy định. |
| Trạng thái tác vụ chờ | Chưa được đặc tả đầy đủ | Không tin snapshot quyền thay cho kiểm tra bắt buộc. |
| Đường tải tệp | Chưa bao phủ rõ | Không được tạo đường đi vòng vượt giới hạn thu hồi. |
| Kiểm thử trọng tâm | Tạo tác vụ hợp lệ và bị từ chối | Thêm thu hồi quyền, cache, tác vụ cũ và đường tải. |

Đây là thay đổi nghĩa và phạm vi, nên không thể xử lý như sửa thuật ngữ.

### 8.4. Phân tích tác động

| Thành phần hoặc trạng thái | Công việc cần xem xét |
|---|---|
| API tạo tác vụ | Giữ kiểm tra quyền hiện có; ràng buộc danh tính, tenant và phạm vi dữ liệu trong tác vụ. |
| Hàng đợi và worker | Không dùng vai trò lưu trong tác vụ làm căn cứ duy nhất; thêm điểm kiểm tra và xử lý tác vụ không còn được phép. |
| Nguồn quyền và cache | Chứng minh thời gian phản ánh thu hồi đáp ứng giới hạn 60 giây; xem xét khi mất kết nối hoặc dữ liệu quá cũ. |
| Kho tệp và đường tải | Ngăn tải trực tiếp bỏ qua kiểm tra; đánh giá mọi liên kết có thể mang quyền truy cập. |
| Tác vụ đang chờ | Xác định cách kiểm tra lại khi thực thi và cách ghi kết quả bị từ chối. |
| Tệp, liên kết đã phát hành | Chặn đường truy cập cũ hoặc có kế hoạch chuyển đổi trước khi tuyên bố đáp ứng rev-2. |
| Audit | Liên kết sự kiện thu hồi, quyết định quyền và tác vụ mà không ghi token hoặc liên kết bí mật. |
| Kiểm thử | Thêm kiểm tra theo thời gian, trạng thái cũ, nhiều điểm thực thi và tình huống lỗi. |

Một liên kết tải mang quyền truy cập có thể tiếp tục hoạt động mà không hỏi lại hệ thống quyền. Chỉ rút ngắn thời hạn liên kết không tự chứng minh giới hạn thu hồi 60 giây; cần kiểm tra thời hạn thực tế, thời điểm phát hành và khả năng có đường truy cập khác.

Tương tự, tắt nút xuất hoặc ngừng tạo tác vụ mới không tự vô hiệu hóa tệp và liên kết đã tồn tại.

### 8.5. Tiêu chí kiểm thử mới

Có thể bổ sung các ca:

- **TC-017-01:** Chủ thể hợp lệ tạo và hoàn tất tác vụ đúng tenant.
- **TC-017-02:** Chủ thể đổi mã tài nguyên sang tenant khác bị từ chối.
- **TC-017-03:** Thu hồi quyền trước khi worker bắt đầu; tại thời điểm vượt giới hạn thu hồi, worker không được đọc dữ liệu để tạo kết quả mới cho tác vụ đó.
- **TC-017-04:** Thu hồi quyền khi worker đang xử lý; tại điểm công bố kết quả sau giới hạn thu hồi, kết quả không được công bố cho chủ thể đã mất quyền.
- **TC-017-05:** Bắt đầu lần tải mới sau thời điểm thu hồi quá 60 giây phải bị từ chối.
- **TC-017-06:** Tác vụ tạo theo phiên bản cũ vẫn đi qua các điểm kiểm tra bắt buộc khi được xử lý trong phạm vi rev-2.
- **TC-017-07:** Đường tải trực tiếp và liên kết cũ không vượt được chính sách mới sau khi chuyển đổi được tuyên bố hoàn tất.
- **TC-017-08:** Khi không có quyết định quyền hợp lệ, thao tác không được âm thầm dùng snapshot cũ để cho phép.

Phép đo cần liên kết được thời điểm nguồn quyền ghi nhận thu hồi với thời điểm ra quyết định tại các thành phần. Nếu dùng đồng hồ của nhiều hệ thống, phải xem xét sai lệch thời gian và cách đo phù hợp.

Các ca trên là đầu vào cho kế hoạch xác minh, chưa phải bằng chứng đã đạt.

### 8.6. Hồ sơ thay đổi rút gọn

Ví dụ cấu trúc dưới đây là nội dung tài liệu, không phải cấu hình thực thi của hệ thống:

```yaml
change_id: CR-042
requirement_id: SEC-REQ-017
from_revision: rev-1
to_revision: rev-2
change_type: SECURITY_SEMANTICS_AND_SCOPE
source:
  risk_id: RISK-REVOKE-04
  activity: Threat modeling luồng xuất dữ liệu
reason: Quyền có thể bị thu hồi khi tác vụ và liên kết tải còn tồn tại
affected_scope:
  - API tạo tác vụ
  - Worker xuất dữ liệu
  - Dịch vụ tải tệp
  - Cache quyền
  - Tác vụ và liên kết đã tồn tại
target_release: release-11
verification_refs:
  - TC-017-01
  - TC-017-02
  - TC-017-03
  - TC-017-04
  - TC-017-05
  - TC-017-06
  - TC-017-07
  - TC-017-08
decision_state: APPROVED
delivery_state: IMPLEMENTING
evidence_state: PENDING
```

Trạng thái APPROVED chỉ nói nội dung thay đổi đã được chấp thuận. IMPLEMENTING và PENDING cho thấy hệ thống chưa được xác nhận đáp ứng phiên bản mới.

## 9. Quản lý bằng chứng khi yêu cầu thay đổi

### 9.1. Bằng chứng phải được hiểu trong đúng ngữ cảnh

Một kết quả xác minh cần chỉ ra:

- Yêu cầu và phiên bản được đánh giá.
- Bản phần mềm hoặc tài liệu thiết kế được kiểm tra.
- Môi trường, cấu hình và các phụ thuộc liên quan.
- Phương pháp, ca kiểm thử và dữ liệu thử.
- Thời điểm, kết quả, giới hạn và người thực hiện hoặc rà soát.

Không chỉ gắn một tệp có tên “security-test-pass” vào mọi phiên bản yêu cầu.

### 9.2. Quyết định giữ, bổ sung hay làm lại

| Loại bằng chứng | Cách xem xét sau thay đổi |
|---|---|
| Bằng chứng rev-1 kiểm tra quyền khi tạo tác vụ | Giữ làm lịch sử cho phạm vi đã kiểm tra; không dùng một mình để chứng minh rev-2. |
| Bảng mô hình quyền không thay đổi nội dung | Có thể dùng lại nếu phân tích tác động xác nhận vẫn phù hợp; ghi căn cứ và phần cần kiểm tra bổ sung. |
| Kiểm thử trên bản build cũ | Có giá trị cho bản đó; muốn dùng hỗ trợ đánh giá bản mới phải xác định phần bất biến và lý do chấp nhận. |
| Kiểm thử worker chưa có ca thu hồi quyền | Cần bổ sung ca phù hợp, không chỉ đổi nhãn phiên bản trên báo cáo cũ. |
| Cấu hình cache đã thay đổi | Xem lại bằng chứng về độ trễ thu hồi và hành vi khi lỗi. |
| Diễn tập phục hồi | Đánh giá lại khi mục tiêu, dữ liệu, khóa hoặc kiến trúc phục hồi thay đổi. |

Không cần hủy mọi bằng chứng cũ sau mỗi lần sửa chính tả. Cũng không được mặc định bằng chứng vẫn còn đủ chỉ vì tên yêu cầu giữ nguyên.

Phạm vi xác minh lại phải được chọn theo tác động và phụ thuộc. Với một cơ chế quyền dùng chung, thay đổi nhỏ ở thư viện có thể ảnh hưởng nhiều luồng, nên không thể chỉ kiểm thử endpoint vừa sửa.

### 9.3. Trạng thái bằng chứng là một chiều riêng

Có thể dùng các trạng thái như:

- Phù hợp cho phiên bản và phạm vi đang xét.
- Chưa đủ cho phần yêu cầu mới.
- Cần đánh giá lại do thay đổi phụ thuộc.
- Đã được thay thế cho đánh giá hiện tại nhưng vẫn giữ lịch sử.
- Không đạt.

Một kết quả PASS cũ không bị viết lại thành FAIL chỉ vì yêu cầu mới có thêm tiêu chí. Cần giữ kết quả lịch sử và ghi rõ nó chưa chứng minh tiêu chí mới. Nếu phát hiện bằng chứng cũ thực sự sai hoặc bị tạo không đúng, phải ghi việc đính chính và lý do thay vì sửa âm thầm.

## 10. Đối chiếu yêu cầu với bản phát hành và môi trường

Tại một thời điểm, nhiều phiên bản phần mềm có thể cùng hoạt động. Theo dõi thay đổi phải biểu diễn được thực tế đó.

| Phạm vi | Phiên bản yêu cầu được đối chiếu | Trạng thái cần hiển thị |
|---|---|---|
| Production release-10 trước chuyển đổi | SEC-REQ-017 rev-1 | Bằng chứng cũ chỉ bao phủ rev-1; rủi ro mới được ghi nhận và có quyết định xử lý. |
| Staging release-11 | SEC-REQ-017 rev-2 | Đang xác minh các tiêu chí mới và trạng thái chuyển đổi. |
| Production sau khi chuyển đổi thành công | SEC-REQ-017 rev-2 | Gắn bằng chứng của bản và cấu hình thực tế, không chỉ kết quả staging. |
| Thành phần chưa chuyển đổi | Phiên bản và giới hạn thực tế | Ghi thiếu hụt, phạm vi bị khóa hoặc ngoại lệ còn hiệu lực. |

Thời điểm yêu cầu mới phải có hiệu lực là quyết định riêng cần được xác định từ rủi ro và ràng buộc áp dụng. Không tự động coi tất cả bản đang chạy đều không đáp ứng ngay lúc một bản dự thảo được tạo; cũng không dùng ngày phát hành dự kiến để trì hoãn một rủi ro cần xử lý sớm hơn.

Nếu nhóm tạm ngừng chức năng xuất trên release-10, cần kiểm tra cả đường tạo tác vụ, worker và liên kết đã tồn tại. Nếu liên kết cũ vẫn đọc được dữ liệu, chưa thể kết luận toàn bộ rủi ro đã được loại bằng việc tắt chức năng.

### 10.1. Triển khai từng phần

Khi API và worker được cập nhật ở các thời điểm khác nhau, phải kiểm tra:

- Thành phần mới có tương thích với trạng thái hoặc thông điệp cũ không.
- Thành phần cũ có bỏ qua trường hoặc quy tắc mới không.
- Có khoảng thời gian nào một đường truy cập không được kiểm soát không.
- Cần thứ tự triển khai, chuyển đổi dữ liệu hoặc khóa chức năng nào.
- Khi nào có đủ bằng chứng để tuyên bố cả luồng đáp ứng.

Trạng thái “đã triển khai 80% instance” chưa nói được 20% còn lại có tiếp nhận lưu lượng hoặc tác vụ nhạy cảm hay không.

### 10.2. Quay lui triển khai

Quay lui mã không tự quay lui quyết định về yêu cầu bảo mật.

Nếu phiên bản mới đã đặt ra điều kiện cần đạt mà bản cũ không đáp ứng, kế hoạch quay lui phải có phương án bảo vệ: khóa chức năng bị ảnh hưởng, duy trì lớp kiểm soát độc lập hoặc sử dụng phương án khác được quyết định đúng thẩm quyền.

Không xóa phiên bản yêu cầu mới để làm cho một bản quay lui trông như đã đáp ứng. Hồ sơ cần thể hiện chính xác trạng thái, lý do và phần rủi ro còn lại.

## 11. Tách các chiều trạng thái để tránh báo cáo sai

Một nhãn “Done” dễ che khuất nhiều bước khác nhau.

| Chiều trạng thái | Ví dụ | Câu hỏi được trả lời |
|---|---|---|
| Quyết định thay đổi | Proposed, Approved, Rejected, Superseded | Có đồng ý với nội dung đề xuất không? |
| Triển khai | Planned, Implementing, Deployed | Phần thay đổi kỹ thuật đã tới đâu? |
| Xác minh | Pending, Passed, Failed, Partial | Đã có bằng chứng đủ cho phạm vi chưa? |
| Áp dụng | Future scope, Effective, Retired | Yêu cầu áp dụng cho phạm vi và mốc nào? |
| Ngoại lệ | Không có, còn hiệu lực, hết hạn | Có phần chưa đạt được chấp nhận theo điều kiện nào không? |

Tên trạng thái có thể khác, nhưng cần định nghĩa và quy tắc chuyển trạng thái rõ ràng.

Ví dụ, một thay đổi có thể Approved, Deployed ở staging, Passed một phần và chưa Effective cho production. Đưa tất cả thành “Done” sẽ khiến người vận hành hiểu nhầm rằng production đã được bảo vệ.

Điều kiện đóng hồ sơ thay đổi phải chỉ rõ phạm vi. Nếu chỉ đóng phần đặc tả, cần ghi như vậy và tiếp tục liên kết tới công việc triển khai còn mở; không báo hoàn tất toàn bộ thay đổi bảo mật.


## 12. Tách, gộp, thay thế và ngừng áp dụng yêu cầu

### 12.1. Tách một yêu cầu quá rộng

Giả sử SEC-REQ-030 yêu cầu “ghi audit cho mọi thao tác nhạy cảm”, nhưng phạm vi phát triển và kiểm thử quá rộng. Nhóm tách thành:

- SEC-REQ-031: audit thay đổi quyền.
- SEC-REQ-032: audit xuất dữ liệu.
- SEC-REQ-033: audit thay đổi cấu hình bảo mật.

Cần giữ liên kết từ mỗi yêu cầu mới tới yêu cầu gốc, đồng thời ánh xạ lại rủi ro, thiết kế, kiểm thử và bằng chứng. Không chỉ đánh dấu yêu cầu gốc đã được thay thế rồi bỏ qua các đường truy vết cũ.

Việc thay thế có thể chỉ áp dụng cho tập yêu cầu mới. Các bản phát hành cũ vẫn cần giữ quan hệ với phiên bản SEC-REQ-030 mà chúng từng được đánh giá.

### 12.2. Gộp yêu cầu trùng lặp

Khi gộp, cần kiểm tra các khác biệt dễ bị mất:

- Phạm vi và đối tượng áp dụng.
- Ngưỡng số hoặc thời hạn.
- Hành vi khi lỗi.
- Nguồn nghĩa vụ và người chịu trách nhiệm.
- Tiêu chí kiểm thử.

Hai yêu cầu cùng có chữ “xác thực mạnh” chưa chắc trùng nếu một yêu cầu áp dụng cho quản trị viên và một yêu cầu áp dụng cho tài khoản máy.

Giữ mã yêu cầu cũ dưới dạng tham chiếu tới yêu cầu thay thế. Không chuyển toàn bộ bằng chứng sang yêu cầu mới nếu chưa đánh giá mức bao phủ.

### 12.3. Ngừng áp dụng

Một yêu cầu có thể không còn áp dụng khi chức năng hoặc tài sản liên quan thực sự được loại khỏi phạm vi. Cần có căn cứ, mốc và bằng chứng.

Ví dụ, ngừng giao diện xuất dữ liệu chưa đủ để ngừng yêu cầu bảo vệ tệp nếu kho vẫn chứa tệp tải được. Tương tự, bỏ cơ sở dữ liệu chính không tự làm mất yêu cầu đối với bản sao lưu và dữ liệu còn lưu giữ.

Ngừng áp dụng cho phạm vi hiện tại không có nghĩa xóa lịch sử. Nếu chức năng được mở lại, phải xác định phiên bản yêu cầu áp dụng trước khi cho phép hoạt động.

## 13. Thay đổi khẩn cấp và ghi nhận sau sự cố

Khi có sự cố hoặc đường khai thác đang hoạt động, nhóm có thể cần khóa endpoint, thu hồi phiên hoặc chặn một đường truy cập trước khi hoàn tất hồ sơ đầy đủ.

Quy trình thay đổi khẩn cấp nên cho phép xử lý nhanh theo thẩm quyền đã xác định, đồng thời giữ tối thiểu:

- Thời điểm, người thực hiện và phạm vi hành động.
- Rủi ro hoặc sự kiện dẫn đến hành động.
- Mã, cấu hình hoặc quyền truy cập đã thay đổi.
- Cách xác minh tác dụng ngăn chặn.
- Tác động nghiệp vụ, giới hạn và phương án tiếp theo.

Sau khi tình hình ổn định, cần hoàn thiện phân tích tác động, phiên bản yêu cầu, kiểm thử hồi quy và quyết định dài hạn. Hành động tạm thời không được âm thầm trở thành thiết kế chính thức.

Ví dụ, tạm khóa xuất dữ liệu có thể ngăn tạo thêm tác vụ, nhưng cần đánh giá riêng các liên kết tải đã tồn tại. Bằng chứng ngăn chặn phải phản ánh đúng phần đã kiểm soát.

Không tạo lịch sử giả như thể một thay đổi khẩn cấp đã được rà soát đầy đủ từ trước. Ghi đúng thứ tự sự kiện, người quyết định và phần rà soát bổ sung sau đó.

## 14. Công cụ hỗ trợ và bảo vệ tính toàn vẹn lịch sử

Có thể kết hợp kho quản lý phiên bản, công cụ quản lý công việc, hệ thống quản lý kiểm thử và hồ sơ phát hành. Không bắt buộc mọi thông tin nằm trong một công cụ.

### 14.1. Quy ước liên kết

Một cách tổ chức hữu ích:

```text
CR-042
  -> SEC-REQ-017 rev-2
  -> RISK-REVOKE-04
  -> DEC-AUTHZ-08 rev-3
  -> WORK-API-18 / WORK-WORKER-09 / WORK-DOWNLOAD-12
  -> TC-017-01 ... TC-017-08
  -> VERIFY-017-06
  -> release-11 + cấu hình triển khai tương ứng
```

Các mã là ví dụ. Giá trị nằm ở khả năng đi từ một đối tượng tới đối tượng liên quan theo cả hai chiều.

Liên kết cần trỏ tới phiên bản cụ thể khi đối tượng có thể thay đổi. Một đường dẫn luôn mở “bản mới nhất” sẽ không đủ để biết nội dung được phê duyệt tại một mốc cũ.

### 14.2. Kiểm tra tự động có ích

Có thể tự động phát hiện:

- Yêu cầu đã duyệt nhưng thiếu chủ sở hữu hoặc phiên bản.
- Thay đổi nghĩa chưa có hồ sơ quyết định.
- Liên kết kiểm thử trỏ tới yêu cầu không còn tồn tại.
- Bản phát hành chưa gắn tập yêu cầu và cấu hình cần đối chiếu.
- Thay đổi ở thành phần dùng chung chưa có đánh giá tác động.
- Ngoại lệ hết hạn hoặc thiếu bằng chứng đóng.
- Yêu cầu đã thay thế nhưng vẫn có công việc đang triển khai theo nội dung cũ.

Các kiểm tra này giúp phát hiện thiếu hồ sơ. Chúng không tự chứng minh nội dung yêu cầu đúng hoặc hệ thống đã an toàn.

Nếu dùng quy tắc cảnh báo khi mã thay đổi chạm vào vùng thực thi quyền, cảnh báo nên dẫn tới đánh giá tác động. Không tự động kết luận mọi thay đổi trong vùng đó đều làm mất hiệu lực toàn bộ bằng chứng.

### 14.3. Quyền sửa và lịch sử quyết định

Cần quản lý ai được đề xuất, phê duyệt và sửa thông tin quyết định. Với thay đổi quan trọng, vai trò thực hiện và rà soát nên được phân công theo quy trình và mức rủi ro.

Lịch sử đã phê duyệt cần được bảo vệ khỏi sửa hoặc xóa tùy tiện. Khi có sai sót, ghi đính chính có liên kết tới bản cũ, lý do và người thực hiện; không thay thế âm thầm để người đọc không nhận ra.

Hồ sơ có thể chứa thông tin nhạy cảm về kiến trúc hoặc điểm yếu. Chỉ lưu dữ liệu cần thiết, kiểm soát quyền truy cập và dùng thời hạn lưu phù hợp. Không đưa mật khẩu, token, khóa bí mật hay dữ liệu khách hàng thật vào diff hoặc bằng chứng nếu không có nhu cầu và cơ chế xử lý phù hợp.

Mục tiêu là lịch sử có thể tin cậy và sử dụng được, không phải lưu mọi chi tiết vô thời hạn.

## 15. Đánh giá chất lượng theo dõi thay đổi

Có thể theo dõi các dấu hiệu:

- Thay đổi đã phê duyệt nhưng chưa có phân tích tác động đủ phạm vi.
- Yêu cầu mới chưa được gắn với thiết kế và kế hoạch xác minh.
- Bản phát hành đang chạy chưa xác định được tập yêu cầu được áp dụng.
- Bằng chứng được dùng cho phiên bản mới nhưng chưa có quyết định về mức phù hợp.
- Thành phần dùng chung đã đổi nhưng hệ thống phụ thuộc chưa được rà soát.
- Hồ sơ đóng trong khi phần triển khai hoặc xác minh còn tồn đọng không có quyết định.
- Yêu cầu bị ngừng áp dụng nhưng trạng thái, tệp hoặc quyền truy cập liên quan vẫn tồn tại.

Các chỉ dấu phải gắn với mức rủi ro và phạm vi. Số hồ sơ thay đổi nhiều không tự chứng minh chất lượng quản lý tốt; có thể chỉ phản ánh quy trình chia việc hoặc số lần chỉnh sửa tài liệu.

Một phép kiểm tra thực tế hữu ích là chọn ngẫu nhiên một yêu cầu trong production và trả lời:

> Phiên bản nào đang áp dụng, vì sao nội dung đó được chọn, thành phần nào thực thi và bằng chứng nào cho thấy bản triển khai hiện tại đáp ứng?

Nếu cần hỏi lại nhiều người để ghép lịch sử hoặc chỉ tìm thấy bản tài liệu mới nhất, chuỗi truy vết còn thiếu.

## 16. Lỗi thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Chỉ lưu bản hiện tại | Không tái dựng được quyết định và phạm vi cũ | Giữ phiên bản đã duyệt, diff và nguồn thay đổi. |
| Coi mọi chỉnh sửa là biên tập | Thay đổi nghĩa không được đánh giá tác động | So sánh hành vi, đối tượng, ngưỡng và điều kiện lỗi trước–sau. |
| Dùng commit làm toàn bộ hồ sơ | Có lịch sử chữ nhưng thiếu lý do và quyết định rủi ro | Liên kết commit với hồ sơ thay đổi và yêu cầu. |
| Chỉ kiểm tra thành phần vừa sửa | Bỏ sót đường đi vòng và phụ thuộc dùng chung | Phân tích theo luồng dữ liệu và điểm thực thi kiểm soát. |
| Đổi nhãn báo cáo cũ sang phiên bản mới | Bằng chứng không thực sự bao phủ tiêu chí mới | Đánh giá lại mức phù hợp và bổ sung xác minh. |
| Gộp Approved, Deployed và Passed | Người đọc hiểu nhầm hệ thống đã đáp ứng | Tách trạng thái quyết định, triển khai, xác minh và hiệu lực. |
| Bỏ qua tác vụ, phiên và liên kết cũ | Kiểm soát mới bị đi vòng qua trạng thái tồn tại | Có kế hoạch chuyển đổi, thu hồi hoặc chặn phù hợp. |
| Quay lui mã rồi xóa yêu cầu mới | Che giấu phần rủi ro chưa được đáp ứng | Giữ yêu cầu và ghi quyết định bảo vệ khi quay lui. |
| Xóa yêu cầu đã thay thế | Mất liên kết với bản phát hành và bằng chứng cũ | Giữ tham chiếu thay thế và phạm vi lịch sử. |
| Đóng hồ sơ khi chưa kiểm tra môi trường đích | Kết quả trong tài liệu khác trạng thái vận hành | Đối chiếu bản, cấu hình và bằng chứng thực tế. |

## 17. Bài tập thực hành: thay đổi mục tiêu phục hồi

Một dịch vụ đang áp dụng SEC-REQ-040 rev-1:

> Trong kịch bản mất cơ sở dữ liệu chính, điểm dữ liệu khôi phục cách thời điểm sự cố không quá 24 giờ.

Dịch vụ có sao lưu hằng ngày và báo cáo diễn tập của một bản phát hành cũ. Sau thay đổi nghiệp vụ, người có thẩm quyền phê duyệt mục tiêu mới: RPO 1 giờ cho phạm vi dữ liệu xác định, có hiệu lực tại một mốc chuyển đổi được lập kế hoạch.

RPO là mục tiêu mức mất dữ liệu chấp nhận được biểu diễn theo thời gian. Đổi từ 24 giờ xuống 1 giờ là thay đổi nghĩa và tham số bảo vệ, không phải cập nhật câu chữ.

Hãy thực hiện:

1. Tạo mã thay đổi và mô tả rõ nội dung trước–sau.
2. Liệt kê nguồn quyết định, dữ liệu thuộc phạm vi, mốc áp dụng và giả định cần xác nhận.
3. Phân tích tác động tới cơ chế sao lưu, thời gian hoàn tất, bản sao lỗi, quyền bảo vệ bản sao và khả năng sử dụng khóa khi phục hồi.
4. Xác định bằng chứng cũ vẫn chứng minh được điều gì và phần chưa chứng minh mục tiêu mới.
5. Đề xuất tiêu chí xác minh cho RPO 1 giờ, gồm cách đo điểm dữ liệu khôi phục và kịch bản kiểm tra.
6. Lập kế hoạch chuyển đổi, liên kết tới bản triển khai và xác định điều kiện đóng hồ sơ.
7. Giả sử cấu hình sao lưu được đổi thành mỗi giờ nhưng một lần sao lưu thất bại: giải thích vì sao chưa thể kết luận mục tiêu đã đạt.
8. Giả sử phải quay lui cấu hình: ghi trạng thái thực tế, rủi ro và quyết định cần có trước khi tiếp tục hoạt động.

### Gợi ý đánh giá

- Cần giữ SEC-REQ-040 rev-1 cùng bằng chứng lịch sử, tạo phiên bản mới cho nội dung đã đổi.
- Lịch sao lưu mỗi giờ không tự chứng minh RPO 1 giờ: độ trễ, lần lỗi và tính dùng được của bản sao đều ảnh hưởng điểm khôi phục.
- Bằng chứng diễn tập cũ có thể hỗ trợ hiểu quy trình nhưng chưa đủ chứng minh mục tiêu mới trên bản và cấu hình mới.
- Cần xác minh dữ liệu phục hồi thực tế, không chỉ trạng thái “backup thành công”.
- Phạm vi dữ liệu, khóa và các phụ thuộc phải khớp với điều hệ thống cần phục hồi.
- Trước khi công bố chuyển đổi hoàn tất, phải có bằng chứng phù hợp với mục tiêu, bản triển khai và môi trường được xét.
- Nếu quay lui làm mất khả năng đáp ứng mục tiêu đang có hiệu lực, không thể giải quyết bằng cách đổi lại phiên bản trên giấy.

## 18. Câu hỏi tự kiểm tra

1. Định danh yêu cầu khác phiên bản yêu cầu như thế nào?
2. Một mốc tập yêu cầu đã duyệt khác phiên bản phần mềm ở điểm nào?
3. Khi nào sửa một từ có thể trở thành thay đổi nghĩa bảo mật?
4. Vì sao thay đổi kiến trúc có thể đòi hỏi xác minh lại dù câu chữ yêu cầu giữ nguyên?
5. Tại sao bằng chứng PASS của phiên bản cũ có thể vẫn đúng nhưng chưa đủ cho phiên bản mới?
6. Những trạng thái tồn tại nào cần xem xét khi đổi yêu cầu thu hồi quyền?
7. Làm sao biểu diễn việc staging đã đạt nhưng production chưa chuyển đổi?
8. Cần giữ những liên kết nào khi tách hoặc gộp yêu cầu?
9. Vì sao quay lui triển khai không tự quay lui yêu cầu đã có hiệu lực?
10. Điều kiện đóng hồ sơ thay đổi cần phân biệt với điều kiện phê duyệt nội dung ra sao?

