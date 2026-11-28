# Immutable backup

## 1. Mục tiêu và bối cảnh trong PAM

Immutable backup là bản sao lưu được bảo vệ để dữ liệu đã ghi không thể bị sửa hoặc xóa trước khi hết điều kiện lưu giữ đã đặt, trong phạm vi bảo đảm của cơ chế lưu trữ. Điểm quan trọng không chỉ là có một file backup, mà là kẻ đã chiếm quyền quản trị môi trường chính có còn phá được bản sao đó hay không.

Với hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), backup thường chứa những dữ liệu rất nhạy cảm: kho credential đã mã hóa, cấu hình quản lý tài khoản, chính sách cấp quyền, thông tin tích hợp, khóa hoặc tham chiếu khóa và bằng chứng hoạt động. Mất bản sao có thể làm doanh nghiệp không khôi phục được PAM. Lộ bản sao hoặc khôi phục thiếu kiểm soát có thể tạo thêm một đường truy cập đặc quyền ngoài quy trình.

Sau bài học, người học cần có khả năng:

- Phân biệt immutable backup với snapshot, replication, mã hóa và bản sao offline.
- Xác định những quyền và phụ thuộc có thể vô hiệu hóa khả năng phục hồi dù dữ liệu backup chưa bị xóa.
- Thiết kế quyền ghi, quyền quản lý retention và quyền restore theo nguyên tắc least privilege.
- Khôi phục PAM từ một điểm phục hồi đã được kiểm tra, đồng thời xử lý credential và chính sách đã cũ.
- Đánh giá tính bất biến bằng thử nghiệm và bằng chứng vận hành, thay vì chỉ dựa vào nhãn của sản phẩm.

Tình huống xuyên suốt: một tổ chức dùng PAM để quản lý tài khoản quản trị máy chủ, tài khoản dịch vụ và phiên truy cập vào hạ tầng quan trọng. Kẻ tấn công chiếm một tài khoản quản trị PAM, sau đó tìm cách mã hóa hệ thống chính, xóa bản sao lưu và làm mất log. Thiết kế backup phải giả định tài khoản này đã bị lộ.

## 2. Bốn thuộc tính cần tách biệt

Tính bất biến chỉ giải quyết một phần bài toán phục hồi.

| Thuộc tính | Câu hỏi phải trả lời | Cơ chế thường hỗ trợ |
|---|---|---|
| Tính bất biến | Bản sao đã chốt có bị sửa hoặc xóa trước hạn không? | WORM, retention lock, cơ chế lưu giữ có thực thi độc lập |
| Tính bí mật | Người lấy được bản sao có đọc được dữ liệu nhạy cảm không? | Mã hóa, quản lý khóa, kiểm soát quyền đọc |
| Tính toàn vẹn và nguồn gốc | Dữ liệu có đúng bản đã tạo từ nguồn được chấp nhận không? | Checksum, manifest, chữ ký và chuỗi kiểm soát nguồn |
| Khả năng phục hồi | Có giải mã, dựng lại và vận hành an toàn trong thời gian yêu cầu không? | Backup nhất quán, đủ phụ thuộc, runbook và restore drill |

Một file mã hóa vẫn có thể bị xóa. Một file bất biến vẫn có thể bị đọc nếu quyền truy cập quá rộng. Một bản sao có checksum đúng vẫn có thể chứa cấu hình do kẻ tấn công sửa trước khi backup được tạo.

Vì vậy, phát biểu “backup immutable nên đã an toàn” thiếu ít nhất ba câu hỏi: ai đọc được, có đủ khóa để phục hồi không và dữ liệu bên trong có đáng tin không.

## 3. Bất biến được thực thi ở đâu?

### 3.1. WORM và thời hạn lưu giữ

WORM là viết một lần, đọc nhiều lần (Write Once, Read Many). Trong một thiết kế backup, dữ liệu hoặc phiên bản dữ liệu được chốt với thời điểm hết hạn lưu giữ. Trước thời điểm đó, hệ thống từ chối những thao tác bị cơ chế bảo vệ cấm.

Tùy nền tảng, bảo vệ có thể áp dụng cho object, phiên bản object, tập backup hoặc thiết bị lưu trữ. Không được suy ra rằng khóa một thư mục logic sẽ tự động bảo vệ mọi thành phần bên dưới.

Cần xác minh cụ thể:

- Thời hạn được gắn khi ghi dữ liệu hay qua một tác vụ chạy sau?
- Khóa áp dụng cho mọi phiên bản cần phục hồi hay chỉ phiên bản hiện tại?
- Quyền nào có thể rút ngắn thời hạn, bỏ khóa hoặc đi vòng cơ chế?
- Bảo vệ đã có hiệu lực đối với bản sao hiện tại hay chỉ áp dụng cho các bản sao tương lai?
- Điều gì xảy ra khi thay đổi policy, tài khoản lưu trữ, đồng hồ hoặc vòng đời object?

Khoảng thời gian từ khi upload xong đến khi retention thực sự có hiệu lực là một khoảng rủi ro. Nếu nền tảng hỗ trợ, nên gắn bảo vệ ngay trong đường ghi; nếu không, phải đo và kiểm soát khoảng trống này.

### 3.2. Chế độ có quyền vượt qua và chế độ khóa chặt

Một số nền tảng cung cấp chế độ quản trị có thể cho phép một quyền đặc biệt bỏ qua retention. Chế độ khác hạn chế mạnh hơn việc sửa hoặc xóa trong thời hạn đã khóa. Tên gọi và bảo đảm cụ thể phụ thuộc sản phẩm.

Điều cần kiểm tra không phải tên chế độ, mà là đường quyền thực tế:

> Nếu kẻ tấn công chiếm tài khoản quản trị backup, tài khoản quản trị lưu trữ hoặc danh tính ở cấp cao hơn, họ có thể xóa dữ liệu đã khóa không?

Nếu một quyền bypass tồn tại và cùng người đang giữ quyền quản trị PAM có thể tự cấp quyền đó, tính bất biến chưa tạo được ranh giới đáng kể trước kịch bản đe dọa này.

Chế độ khóa chặt cũng có hệ quả vận hành: dữ liệu đặt sai retention có thể phải được giữ đến hết hạn và tiếp tục phát sinh chi phí. Việc thử nghiệm phải dùng dữ liệu giả và dung lượng nhỏ trước khi áp dụng cho bản sao thật.

### 3.3. Legal hold không đồng nghĩa retention định kỳ

Legal hold là cơ chế giữ dữ liệu theo một trạng thái giữ lại, thường dùng khi cần bảo toàn chứng cứ hoặc phục vụ yêu cầu pháp lý. Khả năng áp dụng và gỡ hold phụ thuộc nền tảng và quyền quản trị.

Retention theo thời hạn phục vụ vòng đời backup có lịch. Hold phục vụ một nhu cầu giữ lại có thể chưa biết ngày kết thúc. Hai cơ chế có thể cùng tồn tại, nhưng không được coi là thay thế tự động cho nhau.

Không gỡ hold hoặc rút ngắn thời gian giữ chứng cứ chỉ vì muốn giảm dung lượng trong một sự cố. Quyết định đó phải qua đúng chủ sở hữu dữ liệu và quy trình liên quan.

## 4. So sánh với các cơ chế dễ bị nhầm

| Cơ chế | Giá trị chính | Điều không thể tự suy ra |
|---|---|---|
| Snapshot thông thường | Quay lại trạng thái tại một thời điểm | Snapshot không nhất thiết chống xóa bởi quản trị viên |
| Replication | Duy trì bản sao ở nơi khác | Xóa hoặc mã hóa ở nguồn có thể lan sang đích tùy thiết kế |
| Versioning | Giữ các phiên bản dữ liệu | Người có quyền vẫn có thể xóa phiên bản nếu chưa có bảo vệ phù hợp |
| Backup mã hóa | Giảm nguy cơ đọc dữ liệu khi không có khóa | Mã hóa không chặn xóa và không đảm bảo còn khóa để restore |
| Backup offline | Tách bản sao khỏi đường truy cập online trong thời gian ngắt kết nối | Dữ liệu có thể bị sửa khi kết nối lại nếu thiếu kiểm soát |
| Immutable backup | Chặn các thao tác thay đổi đã được cơ chế bảo vệ cấm trong thời hạn | Không tự chứng minh dữ liệu sạch, đủ phụ thuộc hoặc luôn sẵn sàng |
| Bản sao được thử restore | Có bằng chứng về khả năng phục hồi tại lần thử | Không tự bảo vệ bản sao khỏi bị phá sau lần thử |

Một snapshot được triển khai cùng retention lock có thể là một phần của immutable backup. Một object store có versioning có thể hỗ trợ retention bất biến. Cần đánh giá cấu hình cụ thể; không gán tính chất chỉ từ tên công nghệ.

Tương tự, “khác vùng” không nhất thiết là “khác miền quản trị”. Hai kho ở hai khu vực địa lý nhưng dùng cùng tài khoản có quyền xóa toàn bộ vẫn có thể bị cùng một danh tính phá hủy.

## 5. Mô hình đe dọa đối với backup PAM

### 5.1. Các mục tiêu mà kẻ tấn công có thể chọn

Sau khi chiếm quyền quản trị, kẻ tấn công không nhất thiết chỉ xóa file backup. Họ có thể:

1. Dừng job để không xuất hiện bản sao mới.
2. Thay nguồn dữ liệu khiến backup mới chứa cấu hình độc hại.
3. Xóa catalog hoặc metadata khiến khó tìm và lắp ghép chuỗi phục hồi.
4. Phá, vô hiệu hóa hoặc làm mất quyền truy cập khóa giải mã.
5. Thay cấu hình retention cho các lần backup tiếp theo.
6. Chiếm tài khoản restore để đọc kho credential.
7. Làm đầy dung lượng hoặc gây vượt hạn mức, khiến job mới thất bại.
8. Sửa log và báo cáo để che giấu việc hệ thống đã mất khả năng phục hồi.

Bản sao cũ có thể vẫn bất biến trong khi năng lực phục hồi tổng thể suy giảm từng ngày.

### 5.2. Ranh giới tin cậy cần tách

Một thiết kế tham khảo có thể chia thành các miền sau:

```text
Miền vận hành PAM
  | tạo bản sao nhất quán, truyền qua kênh được kiểm soát
  v
Miền ghi backup
  | chỉ tạo dữ liệu mới trong phạm vi được cấp
  v
Kho lưu giữ bất biến
  | đọc có phê duyệt để phục hồi
  v
Miền phục hồi cô lập

Miền khóa phục hồi và danh tính khẩn cấp
  -> có cơ chế truy cập riêng, được kiểm thử
  -> không phụ thuộc duy nhất vào PAM đang bị sự cố

Miền log giám sát độc lập
  <- nhận sự kiện từ PAM, backup, lưu trữ và quản lý khóa
```

Mục tiêu là giảm khả năng một danh tính bị lộ điều khiển đồng thời nguồn, bản sao, khóa và bằng chứng. Không phải hệ thống nào cũng cần tách thành từng tài khoản vật lý riêng, nhưng phải chứng minh được ranh giới quyền tương đương với mô hình đe dọa.

Một phụ thuộc vòng nguy hiểm là: cần PAM để lấy credential restore PAM; cần credential đó để mở backup PAM; trong khi PAM đã ngừng hoạt động. Cơ chế truy cập khẩn cấp phải phá được vòng này mà vẫn có kiểm soát và ghi nhận.

## 6. Xác định đúng tập dữ liệu cần bảo vệ

Không nên coi “export database thành công” là đã có backup đầy đủ cho PAM.

| Nhóm dữ liệu | Vai trò trong khôi phục | Điểm cần chú ý |
|---|---|---|
| Dữ liệu vault đã mã hóa | Khôi phục đối tượng tài khoản và credential do PAM quản lý | Phải có khả năng giải mã đúng định dạng và phiên bản |
| Chính sách và phân quyền | Dựng lại luồng cấp quyền, JIT/JEA, phê duyệt | Policy cũ có thể cấp lại quyền đã bị thu hồi |
| Cấu hình tích hợp | Kết nối directory, target, ticketing, giám sát | Không bật ngay kết nối ra production khi mới restore |
| Catalog và manifest | Xác định tập file, chuỗi phụ thuộc và điểm phục hồi | Bảo vệ cùng mức cần thiết với dữ liệu backup |
| Khóa, chứng thư và phụ thuộc mật mã | Mở được dữ liệu được mã hóa | Không phải khóa nào cũng được phép export; cần cơ chế recovery được hỗ trợ |
| Log và bản ghi phiên | Điều tra và giữ bằng chứng | Có thể có lịch lưu giữ, dung lượng và quyền truy cập riêng |
| Thông tin phiên bản và triển khai | Dựng môi trường tương thích | Gồm phiên bản phần mềm, sơ đồ phụ thuộc và cách phục hồi hợp lệ |

“Bảo vệ khóa” không nhất thiết có nghĩa chép khóa thô vào cùng gói backup. Có hệ thống dùng HSM, KMS, cơ chế quorum hoặc khóa không thể export. Kế hoạch phải xác định đúng đường phục hồi được hỗ trợ, người được phép sử dụng và điều kiện để đường đó hoạt động khi môi trường chính bị mất.

Backup nhất quán ở mức ứng dụng phải bảo toàn những quan hệ cần thiết giữa database, file, metadata và khóa. Một snapshot của từng thành phần ở các thời điểm khác nhau có thể tạo ra tập dữ liệu không dùng được, dù mọi file đều nguyên vẹn.

Nếu dùng backup tăng dần, một điểm phục hồi có thể cần bản đầy đủ nền và nhiều đoạn tăng dần. Retention của từng thành phần phải bảo đảm mọi phụ thuộc còn tồn tại khi điểm phục hồi đó còn được quảng bá là sử dụng được.

## 7. Thiết kế quyền theo nhiệm vụ

Một tài khoản ghi backup không cần đồng thời có quyền xóa mọi backup, sửa retention và khôi phục vault vào một máy tùy ý.

| Vai trò | Quyền cần có theo thiết kế | Quyền nên tách khỏi vai trò |
|---|---|---|
| Danh tính thu thập backup | Đọc hoặc export nguồn qua cơ chế được hỗ trợ | Quản trị toàn bộ PAM, sửa policy cấp quyền nếu không cần |
| Danh tính ghi backup | Tạo bản sao và metadata trong phạm vi xác định | Xóa phiên bản, bỏ retention, thay policy toàn kho |
| Quản trị lưu giữ | Thiết lập retention cho dữ liệu phù hợp | Tự đọc hoặc restore toàn bộ credential nếu không cần |
| Người vận hành restore | Đọc đúng tập phục hồi theo thời gian được duyệt | Xóa backup, thay khóa gốc hoặc tự phê duyệt yêu cầu |
| Người quản lý khóa | Thực hiện thao tác khóa được phân công | Tự tải đầy đủ backup và dựng môi trường đọc bí mật |
| Người kiểm tra | Đọc cấu hình, sự kiện và kết quả thử nghiệm | Thay dữ liệu, gỡ hold hoặc cấp quyền restore |

Bảng trên là mô hình phân tách trách nhiệm. Việc một nền tảng có hỗ trợ đúng từng quyền hay không phải được kiểm tra. Nếu thao tác backup bắt buộc dùng quyền rộng, cần ghi nhận ngoại lệ, giới hạn mạng, thời gian sử dụng, cách cấp credential và giám sát bổ sung.

Quyền restore cần được xem là quyền truy cập đặc biệt. Người có thể đưa vault về một môi trường họ kiểm soát có thể tiếp cận các bí mật lịch sử hoặc hiện tại, tùy khả năng giải mã và trạng thái dữ liệu.

Có thể cấp quyền restore theo JIT, giới hạn vào một tập backup và một cửa sổ thời gian. Phê duyệt hai người giúp giảm nguy cơ tự thực hiện một thao tác nhạy cảm, nhưng chỉ có tác dụng khi một người không thể tự sửa cả luồng phê duyệt và log.

Danh tính khẩn cấp phục vụ phục hồi cần được bảo vệ riêng, có cách xác thực khả dụng khi directory chính hoặc PAM ngừng hoạt động. Không đặt credential khẩn cấp trong runbook dạng rõ và không để mọi kiểm soát truy cập chỉ phụ thuộc vào hệ thống đang cần cứu.

## 8. Retention, RPO và RTO

### 8.1. Chọn thời gian lưu giữ từ rủi ro phục hồi

Retention quá ngắn có thể khiến mọi bản sao trước thời điểm xâm nhập đã hết hạn khi sự cố được phát hiện. Retention rất dài làm tăng dung lượng, chi phí và thời gian giữ dữ liệu nhạy cảm.

Cần cân nhắc:

- Khoảng thời gian có thể chưa phát hiện xâm nhập hoặc lỗi dữ liệu.
- Thời gian điều tra và xác định điểm phục hồi thích hợp.
- Số thế hệ backup và phụ thuộc của từng thế hệ.
- Yêu cầu giữ bằng chứng và chính sách dữ liệu.
- Khả năng giữ khóa giải mã và phần mềm tương thích trong toàn bộ thời hạn.
- Dung lượng phát sinh từ database, bản ghi phiên và log.

Ví dụ giả định: đội vận hành muốn có lịch sử tối thiểu đủ cho 35 ngày phát hiện chậm, 5 ngày lựa chọn điểm phục hồi và 10 ngày dự phòng. Họ có thể dùng 50 ngày làm một đầu vào lập kế hoạch, rồi kiểm tra cùng các yêu cầu khác.

Đây không phải công thức đảm bảo an toàn. Nếu nguồn đã bị sửa từ trước khoảng lịch sử được giữ lại, không có chính sách retention nào tự tạo ra một bản sạch. Tần suất backup và cách lựa chọn thế hệ cũng quyết định có những điểm phục hồi nào trong khoảng đó.

### 8.2. RPO phải phản ánh điểm phục hồi thực sự dùng được

Recovery Point Objective — RPO là mức mất dữ liệu theo thời gian mà nghiệp vụ chấp nhận theo định nghĩa đã thống nhất.

Nếu job chạy mỗi 15 phút nhưng bản hợp lệ gần nhất đã cách sự cố 2 giờ, không thể báo RPO thực tế là 15 phút. Bản hợp lệ phải đủ dữ liệu, đủ phụ thuộc, đã được lưu giữ đúng cách và có thể phục hồi.

Trong sự cố có xâm nhập, bản mới nhất có thể không phải bản nên sử dụng. Điểm phục hồi được chọn có thể cũ hơn, làm tăng lượng thay đổi phải đối soát sau restore. Tổ chức cần theo dõi cả độ mới của backup và mức mất dữ liệu theo điểm phục hồi an toàn đã chọn.

### 8.3. RTO phải tính cả việc đưa PAM trở lại trạng thái an toàn

Recovery Time Objective — RTO là mục tiêu thời gian khôi phục dịch vụ theo phạm vi và mốc bắt đầu đã thống nhất.

Thời gian tải backup không phải toàn bộ RTO. Quá trình còn có thể bao gồm:

1. Phê duyệt và mở quyền khẩn cấp.
2. Dựng môi trường sạch.
3. Khôi phục phụ thuộc khóa và dịch vụ.
4. Tải, kiểm tra và giải mã bản sao.
5. Khôi phục ứng dụng.
6. Đối soát quyền, credential và trạng thái đã thay đổi.
7. Kiểm thử truy cập có kiểm soát và chuyển dịch vụ.

Một phép thử restore mất 90 phút trong môi trường đã dựng sẵn không chứng minh RTO 90 phút khi sự cố thật còn phải phục hồi danh tính, mạng và khóa.

## 9. Khóa mã hóa là một phần của kế hoạch phục hồi

Bất biến dữ liệu và khả dụng khóa là hai việc riêng.

Trong mô hình mã hóa theo lớp, dữ liệu có thể được mã hóa bằng khóa dữ liệu; khóa dữ liệu lại được bảo vệ bởi khóa bao bọc. Muốn giải mã cần đủ thành phần và đúng quyền sử dụng. Giữ file backup nhưng mất khóa bao bọc hoặc mất cơ chế mở khóa vẫn có thể khiến bản sao vô dụng.

Những tình huống cần thử gồm:

- Khóa cũ còn cần để đọc các backup trước lần đổi khóa.
- Tài khoản dịch vụ backup bị thu hồi nhưng người phục hồi vẫn mở được tập được duyệt.
- KMS hoặc HSM chính không khả dụng.
- Quyền sử dụng khóa bị sửa ngoài dự kiến.
- Cơ chế recovery cần nhiều người nhưng một người được chỉ định không có mặt.
- Chứng thư hoặc vật liệu phụ trợ cần thiết không còn hợp lệ cho quy trình đang dùng.

Không mặc định việc đổi khóa hiện tại làm mọi backup cũ đọc được bằng khóa mới. Điều đó phụ thuộc cách dữ liệu và khóa được mã hóa, bao bọc lại hoặc migrate.

Cũng không mặc định việc dữ liệu còn retention sẽ ngăn được thao tác hủy khóa. Quyền hủy, vô hiệu hóa và thay policy khóa phải được kiểm soát, cảnh báo và thử riêng.

Quy trình kết thúc vòng đời cần xét đồng thời thời hạn giữ dữ liệu và thời hạn cần giữ khóa. Không hủy khóa đang cần cho bản sao phải lưu giữ; không giữ khả năng giải mã vô hạn nếu chính sách dữ liệu yêu cầu kết thúc có kiểm soát.

## 10. Luồng tạo backup bất biến tham khảo

Luồng dưới đây mô tả các cổng kiểm soát, không phải lệnh dùng cho một sản phẩm cụ thể.

### Bước 1: Tạo tập backup nhất quán

Dùng cơ chế backup hoặc export được hệ thống hỗ trợ. Ghi nhận điểm dữ liệu, phiên bản ứng dụng và những phụ thuộc cần cho phục hồi.

Không lấy việc tiến trình kết thúc với mã thành công làm bằng chứng duy nhất. Cần xác nhận tập đầu ra tồn tại, không rỗng và đủ thành phần được kỳ vọng.

### Bước 2: Mã hóa và ghi sang miền lưu giữ

Truyền dữ liệu qua kênh được bảo vệ. Danh tính ghi chỉ có quyền cần thiết cho đường ghi và thao tác xác minh mà nền tảng yêu cầu.

Không đặt khóa hoặc mật khẩu giải mã ở dạng rõ cạnh dữ liệu mã hóa. Nếu có vật liệu recovery đi kèm, nó phải được bảo vệ theo đúng mô hình khóa đã thiết kế.

### Bước 3: Chốt retention và xác nhận hiệu lực

Xác minh bằng trạng thái thực tế của tập dữ liệu hoặc phiên bản lưu trữ:

- Retention nào đã được áp dụng?
- Thời điểm bắt đầu và kết thúc là gì?
- Chế độ bảo vệ nào đang có hiệu lực?
- Ai có thể thực hiện ngoại lệ, nếu có?
- Mọi thành phần của điểm phục hồi có cùng mức bảo vệ cần thiết chưa?

Cấu hình mặc định của kho chỉ là một đầu vào. Bằng chứng hoàn thành phải liên hệ được với bản sao cụ thể vừa tạo.

### Bước 4: Bảo vệ manifest và catalog

Manifest có thể ghi mã tập backup, điểm dữ liệu, danh sách thành phần, kích thước, checksum và tham chiếu khóa. Nó không nên chứa credential rõ.

Checksum giúp phát hiện thay đổi khi so với một giá trị tham chiếu đáng tin. Nếu kẻ tấn công sửa được cả file và manifest, việc so hai giá trị do cùng kẻ đó kiểm soát không chứng minh được nguồn gốc. Chữ ký, lưu giữ độc lập và kiểm soát quyền ghi có thể giúp tăng độ tin cậy.

### Bước 5: Đưa sự kiện ra miền giám sát độc lập

Ghi nhận kết quả job, trạng thái retention, các lỗi và độ mới của điểm phục hồi. Cảnh báo khi không có backup hợp lệ trong cửa sổ mong đợi.

Không để tài khoản vận hành backup tự xóa được toàn bộ log chứng minh backup đã bị vô hiệu hóa.

### Bước 6: Định kỳ thử khả năng sử dụng

Thử đọc và phục hồi trong môi trường cô lập theo kế hoạch. Thử nghiệm phải bao gồm dữ liệu, khóa, quyền, thời gian và các bước vận hành cần thiết; chỉ kiểm tra checksum là chưa đủ.

## 11. Ví dụ yêu cầu kiểm soát dưới dạng dữ liệu

Ví dụ sau dùng để diễn đạt ý định thiết kế. Đây không phải cấu hình có thể đưa trực tiếp vào một nền tảng backup hay PAM.

```yaml
backup_design_example:
  workload: pam-production
  data_classification: highly-sensitive
  backup_interval_minutes: 15

  retention:
    example_days: 60
    enforcement: storage-side
    lock_applied_during_write: required
    existing_copy_protection_verified: required

  separation:
    storage_administration: separate-from-pam-administration
    restore_approval: separate-from-requester
    key_recovery: available-without-primary-pam
    audit_destination: independent

  writer:
    create_new_backups: allowed
    delete_existing_versions: denied
    shorten_existing_retention: denied

  restore:
    destination: isolated-recovery-environment
    production_connectors_enabled_initially: false
    reconcile_current_revocations: required
    validate_credentials_before_cutover: required

  evidence:
    record_backup_set_and_dependencies: true
    record_effective_retention: true
    record_restore_test_result: true
```

Các giá trị 15 phút và 60 ngày chỉ là giả định của ví dụ. Chúng cần được thay bằng yêu cầu nghiệp vụ, khả năng hệ thống và kết quả đo.

Một bản thiết kế không được coi là hoàn thành chỉ vì YAML thể hiện `denied`. Phải ánh xạ từng yêu cầu sang cơ chế thực thi của nền tảng, kiểm tra quyền hiệu lực và lưu kết quả thử.

## 12. Khôi phục PAM mà không đưa trạng thái nguy hiểm trở lại

### 12.1. Chọn điểm phục hồi bằng nhiều nguồn bằng chứng

Một bản sao tạo trước lúc phát hiện ransomware có thể đã chứa cửa hậu hoặc policy độc hại. Thời điểm phát hiện không nhất thiết là thời điểm xâm nhập.

Việc lựa chọn cần kết hợp log độc lập, lịch sử thay đổi, kết quả điều tra và hiểu biết về tài sản bị ảnh hưởng. Bất biến giúp giữ lại những điểm dữ liệu để lựa chọn; nó không tự quyết định điểm nào sạch.

### 12.2. Khôi phục vào vùng cô lập trước

Môi trường phục hồi ban đầu nên hạn chế kết nối ra các hệ thống thật. Đặc biệt cần kiểm soát:

- Connector đến target production.
- Job luân chuyển mật khẩu tự động.
- Đồng bộ directory và cấp quyền.
- Gửi thông báo hoặc cập nhật ticket.
- Kết nối đến kho log và tích hợp có khả năng ghi dữ liệu.

Nếu một bản PAM cũ tự chạy job rotation vào production ngay sau khi bật lên, nó có thể gây gián đoạn hoặc ghi đè trạng thái mà đội ứng cứu đang kiểm soát.

Cô lập không có nghĩa môi trường không bao giờ được dùng phụ thuộc bên ngoài. Các kết nối cần thiết cho giải mã, kiểm thử hoặc lấy bản sao phải được cho phép có chủ đích và theo dõi, thay vì mở toàn bộ mạng.

### 12.3. Đối soát credential sau restore

Giả sử:

```text
Ngày D, 00:00: backup ghi credential phiên bản P1
Ngày D, 09:00: PAM luân chuyển target sang P2
Ngày D, 12:00: xảy ra sự cố
Sau đó: restore backup lúc 00:00
```

Vault được restore có thể biết P1, còn target đang chấp nhận P2. Dùng lại P1 có thể thất bại và gây khóa tài khoản. Nếu P1 từng bị lộ, việc khôi phục bản sao cũng không khiến P1 trở nên đáng tin.

Cần một quy trình đối soát cho từng nhóm tài khoản:

1. Xác định trạng thái hiện tại của target qua đường truy cập được phê duyệt.
2. Kiểm tra mối liên hệ giữa credential trong vault và target theo cách an toàn.
3. Khôi phục quyền quản lý hoặc thực hiện đổi credential theo runbook.
4. Cập nhật những ứng dụng phụ thuộc bằng luồng được hỗ trợ.
5. Xác nhận truy cập và công việc dịch vụ hoạt động.
6. Ghi bằng chứng, xử lý giá trị từng bị nghi lộ và kết thúc quyền khẩn cấp.

Không tự đặt lại credential target về giá trị có trong backup chỉ để làm cho hai bên khớp nhau. Cách đó có thể tái sử dụng bí mật cũ, làm mất dấu điều tra hoặc phá các dịch vụ đang sử dụng credential mới.

### 12.4. Đối soát quyền và trạng thái thu hồi

PAM được phục hồi có thể đưa trở lại:

- Người dùng đã nghỉ việc.
- Quyền quản trị thường trực đã bị loại bỏ.
- Mapping nhóm đã thay đổi.
- Token, chứng thư hoặc khóa SSH đã bị thu hồi.
- Ngoại lệ truy cập và cấu hình MFA cũ.
- Lịch hoặc trạng thái lease đã hết hạn.

Trước khi cho phép truy cập lại, phải đối chiếu với nguồn hiện hành đã được xác nhận: danh tính, phê duyệt quyền, danh sách thu hồi và quyết định ứng cứu.

Nguồn đối soát này cũng phải có phương án khả dụng trong sự cố. Nếu toàn bộ lịch sử thu hồi chỉ nằm trong chính bản database cũ, đội phục hồi có thể không biết những thay đổi nào cần áp lại.

### 12.5. Chuyển dịch vụ có kiểm soát

Chỉ kết nối lại production sau khi đạt các cổng đã đặt: môi trường sạch, dữ liệu đọc được, quyền đã đối soát, credential quan trọng đã xử lý và log hoạt động.

Tránh để hai phiên bản PAM cùng điều khiển một target nếu hệ thống không hỗ trợ mô hình đó. Cần xác định phiên bản có thẩm quyền và chặn các job của bản còn lại trước khi chuyển.

Bản backup nguyên gốc nên được giữ nguyên trong thời hạn lưu giữ. Các điều chỉnh phục hồi được thực hiện trên bản làm việc, có nhật ký và có thể truy vết về điểm phục hồi đã chọn.

## 13. Kiểm thử tính bất biến và khả năng phục hồi

Thử nghiệm nên thực hiện trên tập dữ liệu giả, trong phạm vi được duyệt. Không thử xóa hoặc hủy khóa của backup production để chứng minh một giả định.

| Phép thử | Kết quả cần quan sát | Bằng chứng cần giữ |
|---|---|---|
| Danh tính ghi thử xóa một phiên bản đang được bảo vệ | Bị từ chối đúng phạm vi thiết kế | Danh tính, tài nguyên thử, thời điểm, phản hồi và sự kiện audit |
| Vai trò quản trị thử rút ngắn retention đang có hiệu lực | Bị chặn hoặc chỉ đi qua ngoại lệ đã được mô hình hóa | Quyền hiệu lực, chế độ khóa và kết quả thao tác |
| Thay default retention cho bản sao tương lai trên môi trường thử | Không làm mất bảo vệ của bản sao đã khóa nếu nền tảng cam kết như vậy | Trạng thái trước và sau của chính phiên bản thử |
| Mất môi trường PAM chính | Vẫn lấy được quyền phục hồi qua đường khẩn cấp hợp lệ | Các bước thực hiện, người tham gia và thời gian |
| Mất đường truy cập khóa chính | Cơ chế recovery khóa hoạt động trong phạm vi thiết kế | Kết quả mở dữ liệu thử và những phụ thuộc đã dùng |
| Khôi phục một điểm tăng dần | Có đủ bản nền và chuỗi phụ thuộc | Danh sách thành phần, kết quả ghép và kiểm tra ứng dụng |
| Khôi phục credential cũ trong môi trường thử | Phát hiện chênh lệch và xử lý theo runbook | Trạng thái giả lập, quyết định đối soát và kết quả |
| Job backup bị dừng | Có cảnh báo vì độ mới vượt ngưỡng | Thời điểm job dừng, cảnh báo và thời gian phản hồi |

Một thao tác xóa bị từ chối vì tài khoản không có quyền IAM chưa tự chứng minh retention đang hoạt động. Nếu muốn kiểm tra cơ chế khóa lưu trữ, thiết kế phép thử phải phân biệt được nguyên nhân từ chối, trong môi trường an toàn.

Tương tự, thử bằng danh tính ghi không chứng minh quản trị viên cấp cao hơn cũng bị chặn. Ma trận thử phải bám theo những danh tính đã đưa vào mô hình đe dọa.

Không cần cố phá mọi giới hạn của nền tảng trong mỗi lần diễn tập. Cần kiểm tra các bảo đảm quan trọng, quyền hiệu lực, tài liệu nền tảng áp dụng và những thay đổi cấu hình có thể làm kết quả cũ hết giá trị.

## 14. Giám sát những gì?

Đừng chỉ theo dõi “job màu xanh”. Một dashboard hữu ích cần phản ánh ít nhất bốn lớp.

### Độ mới và mức bao phủ

- Tuổi của điểm phục hồi hợp lệ gần nhất.
- Thành phần PAM nào chưa được backup.
- Số thế hệ phục hồi còn đủ chuỗi phụ thuộc.
- Tình trạng copy sang miền lưu giữ độc lập.

### Bảo vệ lưu giữ

- Bản sao mới thiếu retention hoặc sai thời hạn.
- Thay đổi policy, quyền bypass, lifecycle và hold.
- Các yêu cầu xóa hoặc sửa dữ liệu bị từ chối.
- Sự khác biệt giữa thời hạn dự kiến và thời hạn thực tế.

### Khóa và danh tính

- Thao tác vô hiệu hóa, lên lịch hủy hoặc đổi quyền dùng khóa.
- Cấp mới quyền đọc backup hoặc restore.
- Sử dụng danh tính khẩn cấp.
- Lỗi xác thực làm ngừng job hoặc ngăn đường phục hồi.

### Khả năng thực thi phục hồi

- Thời gian từ lần restore drill thành công gần nhất.
- Tổng thời gian khôi phục so với mục tiêu RTO.
- Số lỗi đối soát credential và quyền sau restore.
- Các bước runbook chưa thực hiện được khi thiếu hệ thống chính.
- Dung lượng, hạn mức và dự báo chi phí ảnh hưởng đến các lần ghi tiếp theo.

Việc bị từ chối xóa một object có thể là thử nghiệm hợp lệ hoặc dấu hiệu tấn công. Cần liên hệ với người thực hiện, cửa sổ thay đổi và ticket thay vì mặc định mọi sự kiện đều có cùng mức nghiêm trọng.

Log nên chứa định danh backup và tham chiếu khóa cần thiết, nhưng không chứa mật khẩu, token giải mã hay nội dung vault rõ.

## 15. Những lỗi thiết kế thường gặp

### Lỗi 1: Cùng một tài khoản quản trị tất cả

Quản trị PAM, backup, lưu trữ, khóa và log cùng phụ thuộc vào một danh tính. Khi danh tính đó bị chiếm, nhiều lớp bảo vệ có thể cùng mất tác dụng.

Cách xử lý: phân tích đường quyền hiệu lực, tách những quyền có thể kết hợp để phá phục hồi và thử kịch bản mất danh tính chính.

### Lỗi 2: Gọi replication là backup bất biến

Một bản sao đồng bộ có thể truyền rất nhanh cả thay đổi không mong muốn. Nó phục vụ một mục tiêu khác nếu không có lịch sử và lưu giữ phù hợp.

Cách xử lý: xác định điểm phục hồi độc lập và kiểm tra hành vi khi nguồn bị xóa, sửa hoặc mã hóa.

### Lỗi 3: Giữ dữ liệu lâu nhưng làm mất khóa sớm

Object vẫn tồn tại đúng retention nhưng không còn đường giải mã.

Cách xử lý: quản lý vòng đời khóa cùng vòng đời tập backup, bao gồm các bản sao cũ và cơ chế recovery được hỗ trợ.

### Lỗi 4: Backup có retention nhưng catalog có thể mất

Dữ liệu nằm trong kho nhưng đội phục hồi không xác định được bản nền, các đoạn tăng dần hoặc phiên bản phần mềm cần dùng.

Cách xử lý: đưa metadata cần thiết vào phạm vi bảo vệ và thử khôi phục khi catalog vận hành chính không còn.

### Lỗi 5: Kiểm tra hash rồi kết luận dữ liệu sạch

Hash khớp chỉ cho biết quan hệ với giá trị tham chiếu đã dùng. Nó không loại bỏ cấu hình độc hại đã nằm trong nguồn.

Cách xử lý: tách kiểm tra toàn vẹn khỏi đánh giá điểm phục hồi và điều tra xâm nhập.

### Lỗi 6: Mở hết connector ngay khi PAM chạy lại

Bản cũ tác động vào target trước khi credential, quyền và trạng thái thu hồi được đối soát.

Cách xử lý: phục hồi cô lập, bật tích hợp theo thứ tự, có cổng nghiệm thu và xác định rõ bên nào đang quản lý target.

### Lỗi 7: Đặt retention dài mà không dự báo dung lượng

Dữ liệu đã khóa có thể chưa được phép xóa để giải phóng chỗ. Job mới thất bại dù các bản cũ vẫn còn nguyên.

Cách xử lý: thử với quy mô nhỏ, đo tốc độ tăng dữ liệu, quản lý hạn mức và có kế hoạch dung lượng đáp ứng thời gian giữ bắt buộc.

### Lỗi 8: Không thử hết hạn và kết thúc vòng đời

Thiết kế chỉ chứng minh giữ được dữ liệu, chưa chứng minh dữ liệu được loại bỏ đúng lúc khi mọi điều kiện cho phép.

Cách xử lý: trên dữ liệu thử, kiểm tra hành vi sau hết hạn, quan hệ với hold và quy trình tiêu hủy có phê duyệt. Không tự động coi hết retention là bắt buộc xóa ngay nếu còn yêu cầu giữ khác.

## 16. Bài tập tình huống

### Đề bài

Một tổ chức có cấu hình sau:

- Backup PAM mỗi giờ vào một kho có versioning.
- Tài khoản quản trị PAM đồng thời quản lý IAM của kho.
- Mỗi tối một job gắn retention 30 ngày cho dữ liệu đã upload trong ngày.
- Khóa giải mã nằm trong một dịch vụ khóa cùng miền quản trị.
- Runbook và credential restore chỉ truy cập được qua PAM.
- Lần thử gần nhất mới kiểm tra tải file và so checksum.
- Sau restore, mọi connector mặc định tự hoạt động.

Hãy xác định những điểm chưa đủ bằng chứng để gọi đây là thiết kế phục hồi chống phá hoại.

### Hướng phân tích

**Thứ nhất, versioning chưa chứng minh bất biến.** Cần xem phiên bản nào đã có retention thực sự và quyền nào có thể xóa chúng.

**Thứ hai, có khoảng trống trước job ban đêm.** Các bản sao vừa tạo có thể chưa được bảo vệ. Nếu xảy ra tấn công trước lúc gắn retention, chúng có thể bị phá.

**Thứ ba, miền quyền chưa được tách.** Người quản trị PAM có thể thay IAM của kho và có thể tác động đến khóa. Cần kiểm tra những đường phá phục hồi còn tồn tại.

**Thứ tư, đường khẩn cấp có phụ thuộc vòng.** Khi PAM mất, đội phục hồi có thể không lấy được credential hoặc runbook để phục hồi chính PAM.

**Thứ năm, chưa có bằng chứng ứng dụng phục hồi được.** Tải file và checksum chưa kiểm tra giải mã, tính nhất quán, chuỗi phụ thuộc, quyền hiện hành và RTO.

**Thứ sáu, connector tự bật có thể tác động lên production quá sớm.** Cần một trạng thái khởi động phục hồi được kiểm soát.

### Một phương án cải thiện

1. Xác định cơ chế lưu giữ được thực thi ở lớp lưu trữ và gắn bảo vệ ngay trong đường ghi nếu nền tảng hỗ trợ.
2. Tách quyền ghi, thay retention, sử dụng khóa và restore theo mô hình đe dọa.
3. Bổ sung đường phục hồi khẩn cấp không cần PAM chính đang hoạt động.
4. Bảo vệ dữ liệu, catalog và phụ thuộc mật mã cần thiết.
5. Thử restore trong vùng cô lập, bao gồm chênh lệch credential và quyền.
6. Đặt cảnh báo cho backup thiếu bảo vệ, khóa bị thay đổi và điểm phục hồi quá cũ.
7. Chọn lại retention, tần suất và dung lượng theo yêu cầu nghiệp vụ đã xác nhận.

Không thể khẳng định con số 30 ngày là đủ hoặc thiếu chỉ từ đề bài. Cần biết thời gian phát hiện chậm, lịch sử cần giữ, yêu cầu dữ liệu và khả năng vận hành.

## 17. Tự kiểm tra mức hiểu

**Nếu mọi object đều được khóa, vì sao vẫn có thể không restore được?**

Có thể thiếu khóa giải mã, thiếu catalog, thiếu bản nền, sai phiên bản ứng dụng, mất quyền truy cập hoặc bản sao chứa dữ liệu không nhất quán. Bất biến object không bảo đảm đầy đủ những điều kiện đó.

**Người có quyền restore có nhất thiết cần quyền sửa retention không?**

Không. Đây là hai nhiệm vụ khác nhau. Thiết kế nên tách chúng khi nền tảng cho phép và kiểm tra quyền hiệu lực thay vì chỉ kiểm tra tên vai trò.

**Bản sao mới nhất có phải luôn là điểm phục hồi tốt nhất không?**

Không. Nó có thể đã chứa thay đổi độc hại hoặc lỗi nguồn. Việc lựa chọn phải dựa trên điều tra, yêu cầu mất dữ liệu và khả năng đối soát sau phục hồi.

**Có nên đổi target về mật khẩu trong backup để PAM đăng nhập lại được không?**

Không nên coi đó là thao tác mặc định. Cần đối soát trạng thái hiện tại và phục hồi quyền quản lý theo runbook; bí mật cũ có thể đã bị thu hồi hoặc bị lộ.

**Một lần thử xóa thất bại đã đủ chưa?**

Chưa. Phải biết danh tính thử có quyền gì, lớp nào từ chối, tài nguyên nào được bảo vệ và những vai trò trong mô hình đe dọa đã được kiểm tra đến đâu.

**Khi nào có thể nói immutable backup đang đóng góp thực sự cho khả năng phục hồi PAM?**

Khi có bản sao cụ thể được bảo vệ đúng thời hạn, đường quyền phá phục hồi đã được đánh giá, dữ liệu và khóa đủ dùng, đường khẩn cấp hoạt động và phép thử restore cho thấy có thể đưa PAM về trạng thái vận hành an toàn trong mục tiêu đã đặt.
