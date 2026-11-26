Một API trả số thẻ thanh toán đã che bốn chữ số đầu và chỉ giữ bốn số cuối; với BIN phổ biến và dữ liệu giao dịch đi kèm, kẻ xem response vẫn có thể thu hẹp danh tính chủ thẻ.
Trang hồ sơ che email thành dạng a***@domain nhưng không che tên miền phụ hoặc thông tin tổ chức; ở doanh nghiệp nhỏ, phần còn lại đủ để suy ra địa chỉ đầy đủ.
Màn hình hỗ trợ chỉ hiển thị bốn số cuối của số điện thoại nhưng cho phép tìm kiếm bằng toàn bộ số; quyền truy vấn không được kiểm soát khiến masking UI không bảo vệ dữ liệu phía server.
Log formatter che chuỗi giống số thẻ bằng regex nhưng không nhận biết trường dữ liệu; một mã đơn hàng có cấu trúc tương tự bị che nhầm trong khi thẻ nằm trong trường khác không bị phát hiện.
Nhóm redaction chỉ xóa trường password khỏi JSON log nhưng request body lồng sâu có refresh token trong object session; secret vẫn được ghi vào log vì bộ lọc không duyệt cấu trúc đệ quy.
Ứng dụng mask dữ liệu sau khi ghi log; log collector và forwarder đã nhận bản ghi nguyên gốc trước đó nên bản sao nhạy cảm vẫn tồn tại trong hệ thống tập trung.
Gateway redaction che Authorization header nhưng không che cookie phiên và custom header chứa API key; credential tiếp tục xuất hiện trong access log.
Distributed trace ghi email, số điện thoại và query parameter vào span attributes; dashboard tracing có lượng người truy cập rộng hơn hệ thống hồ sơ nhưng không áp dụng redaction tương ứng.
Ứng dụng che PII trong response JSON nhưng GraphQL resolver phụ trả thêm trường rawEmail; client chỉ cần yêu cầu field lồng nhau để bỏ qua quy tắc masking của REST endpoint.
API export CSV áp dụng serializer riêng và không dùng chính sách masking của API thông thường; file tải xuống chứa dữ liệu định danh đầy đủ dù màn hình chỉ hiển thị bản che.
Ứng dụng chỉ che dữ liệu trên frontend bằng CSS hoặc JavaScript; response network vẫn chứa giá trị gốc và người dùng có thể đọc qua developer tools.
Dynamic data masking trong database chỉ tác động tới truy vấn của một role; tài khoản báo cáo khác có quyền SELECT trực tiếp và nhận dữ liệu gốc.
Đội vận hành nhầm mã hóa ổ đĩa với masking; nhân viên có quyền đọc bảng vẫn thấy PII nguyên bản sau khi truy vấn vì encryption at rest không thay đổi giá trị được trả về.
Một hệ thống dùng redaction thay cho masking và xóa toàn bộ số điện thoại khỏi dữ liệu phân tích; nhóm vận hành mất khả năng đối chiếu các cuộc gọi liên quan dù chỉ cần giữ mã giả danh ổn định.
Tokenization thay số thẻ bằng token ngẫu nhiên nhưng token vault không tách biệt mạng và quyền với database nghiệp vụ; attacker chiếm database ứng dụng rồi truy cập luôn dịch vụ ánh xạ ngược.
Token vault dùng token tuần tự để dễ tra cứu; attacker suy ra số lượng bản ghi và có thể thử token lân cận để truy vấn dữ liệu của khách hàng khác.
Hai dịch vụ tokenization tạo token ngẫu nhiên độc lập cho cùng một khách hàng; dữ liệu giao dịch và hỗ trợ không thể join nhất quán dù cùng tham chiếu một chủ thể.
Nhóm dùng tokenization xác định bằng HMAC để join dữ liệu giữa các hệ thống nhưng dùng chung secret cho mọi môi trường; token từ staging có thể liên kết trực tiếp với production.
Deterministic token giúp phân tích lịch sử nhưng cho phép quan sát tần suất lặp; attacker có auxiliary data có thể suy đoán giá trị gốc từ mẫu xuất hiện.
Tokenization giữ nguyên định dạng số thẻ để tương thích hệ thống cũ; nhóm quên phân biệt token với PAN và token bị đưa nhầm vào cổng thanh toán như dữ liệu thẻ thật.
Token vault có bản sao backup cũ nhưng khóa mã hóa vault đã rotate; nhóm không thử phục hồi mapping và phát hiện token lịch sử không thể ánh xạ sau disaster recovery.
Quyền detokenize được cấp cho toàn bộ service account để giảm độ trễ; dịch vụ chỉ cần thống kê giao dịch có thể lấy dữ liệu định danh gốc không cần thiết.
Nhân viên hỗ trợ có quyền reveal dữ liệu khách hàng nhưng thao tác không yêu cầu lý do, không ghi audit và không giới hạn số lần; quyền xem tạm thời trở thành khả năng trích xuất hàng loạt.
API trả token thay vì dữ liệu gốc nhưng token có thể được gửi tới bên thứ ba như một định danh ổn định; đối tác liên kết được hoạt động của cùng người dùng qua nhiều dịch vụ.
Pseudonymization thay tên bằng mã cố định nhưng giữ ngày sinh chính xác, mã bưu chính và giới tính; tổ hợp quasi-identifiers vẫn có thể tái nhận diện cá nhân.
Dataset được gọi là anonymized sau khi xóa tên và email; các cột tuổi, khu vực, nghề nghiệp và thời gian sự kiện vẫn cho phép nối với dữ liệu công khai để nhận diện người cụ thể.
Nhóm chỉ kiểm tra k-anonymity trên toàn bộ dataset nhưng không đánh giá từng nhóm nhạy cảm; một equivalence class nhỏ vẫn tiết lộ thuộc tính sức khỏe hoặc tài chính.
Dữ liệu đạt k-anonymity nhưng tất cả người trong một nhóm đều có cùng diagnosis; l-diversity không được xem xét nên người phân tích suy ra thuộc tính nhạy cảm dù không biết danh tính.
Phân phối thuộc tính trong từng nhóm khác xa toàn bộ dân số; chỉ số t-closeness không được đánh giá và thông tin nhạy cảm vẫn bị suy luận từ nhóm tương đương.
Nhóm bỏ tên và ID trực tiếp nhưng giữ timestamp chính xác của các lần khám; dữ liệu công khai về lịch hẹn hoặc sự kiện cho phép liên kết bản ghi với cá nhân.
Địa chỉ được generalize xuống cấp quận nhưng một số quận chỉ có một cơ sở chuyên khoa; kết hợp loại dịch vụ và ngày truy cập vẫn làm lộ danh tính.
Ngày sinh được thay bằng tuổi nhưng giữ tuổi chính xác và ngày giao dịch; nhóm người cao tuổi hiếm trong một khu vực nhỏ vẫn dễ bị nhận diện.
Dataset phân tích thay email bằng hash SHA-256 không salt; danh sách email phổ biến có thể được hash trước và dò ngược để khôi phục định danh.
Pseudonym được tạo bằng hash có salt công khai nhưng không có secret; attacker có thể tính lại mapping cho tập giá trị email hoặc số điện thoại có miền ứng viên nhỏ.
Nhóm dùng HMAC để pseudonymize customer ID nhưng lưu secret cạnh dataset đã biến đổi; người lấy được cả hai có thể tính lại định danh gốc.
Secret dùng cho deterministic tokenization bị rotate mà không giữ key version; cùng một khách hàng tạo token khác nhau giữa các giai đoạn và làm đứt liên kết lịch sử.
Ứng dụng dùng format-preserving encryption cho số tài khoản nhưng không giới hạn miền đầu vào hoặc không quản lý tweak; token có cấu trúc hợp lệ nhưng rủi ro phân tích tần suất và miền nhỏ vẫn cao.
Masking số tài khoản giữ nguyên tiền tố và hậu tố; một số tài khoản có độ dài ngắn hoặc tiền tố đặc thù nên phần còn lại gần như tiết lộ toàn bộ giá trị.
Quy tắc che tên chỉ thay ký tự giữa bằng dấu sao; tên rất ngắn hoặc tên hiếm vẫn dễ suy ra khi kết hợp phòng ban và chức danh.
Ảnh giấy tờ được làm mờ vùng số định danh nhưng OCR layer trong PDF vẫn chứa text gốc; người nhận file có thể copy hoặc tìm kiếm dữ liệu đã tưởng là bị xóa.
Redaction tài liệu PDF chỉ vẽ vùng đen lên trang mà không xóa text, annotation và metadata; tìm kiếm hoặc copy nội dung vẫn lấy được thông tin nhạy cảm.
Tệp xuất dữ liệu đã mask nội dung chính nhưng metadata EXIF còn GPS, tên tác giả và thiết bị; dữ liệu vị trí hoặc danh tính bị lộ qua metadata.
Audio ghi âm được beep đoạn số thẻ nhưng bản transcript và bản ghi gốc vẫn lưu ở kho khác; redaction một artifact không xử lý toàn bộ bản sao dữ liệu.
Video làm mờ khuôn mặt nhưng biển số xe và phản chiếu trên kính vẫn nhận diện được cá nhân hoặc địa điểm.
Log pipeline chỉ redaction message text nhưng structured fields như labels, attributes và exception context không được duyệt; PII tiếp tục tồn tại ở metadata.
Masking chạy sau bước enrichment thêm customer profile vào event; dữ liệu gốc đã được sao chép sang field mới không nằm trong danh sách redaction.
Ứng dụng có nhiều phiên bản schema event; rule redaction chỉ nhận tên trường cũ nên sau rollout, trường mới chứa số định danh lọt qua.
Regex redaction xử lý chuỗi một dòng nhưng không xử lý multiline stack trace; secret nằm ở dòng tiếp theo không bị che.
Streaming redaction chia payload thành nhiều chunk; số thẻ nằm vắt qua ranh giới chunk nên bộ lọc không nhận diện được chuỗi hoàn chỉnh.
Rule masking dùng locale mặc định để nhận dạng số điện thoại; định dạng quốc tế, mã quốc gia và dấu phân cách khác nhau làm dữ liệu bị bỏ sót.
Pipeline redaction thay mọi chuỗi dài giống account ID; mã giao dịch và correlation ID bị thay đổi khiến điều tra sự cố không thể liên kết các log.
Data warehouse áp dụng masking khi query nhưng materialized view được tạo trước khi chính sách thay đổi; bản view cũ vẫn lưu dữ liệu nhạy cảm dạng rõ.
Cache API lưu response đã unmask từ request của nhân viên hỗ trợ; cache key không bao gồm role hoặc trạng thái reveal nên người dùng thường có thể nhận response nhạy cảm.
Search index lưu cả giá trị gốc và giá trị đã mask để hỗ trợ tìm kiếm; quyền truy cập index không tương đương quyền đọc database nên PII bị lộ qua search.
Database replication và CDC truyền row trước khi masking ở tầng báo cáo; dữ liệu gốc được sao chép sang analytics cluster ngoài phạm vi kiểm soát.
Backup và snapshot được tạo trước khi redaction; khi dữ liệu gốc bị yêu cầu xóa, bản sao lưu vẫn chứa PII và không có chính sách hết hạn hoặc cryptographic erasure.
Quy trình xóa dữ liệu khách hàng chỉ xóa bảng chính mà không xóa token vault mapping, cache, search index, log và data lake; danh tính vẫn có thể được khôi phục.
Test environment được tạo từ production dump rồi chỉ che dữ liệu trong một số bảng; bảng liên quan, file đính kèm và event log vẫn chứa thông tin thật.
Dữ liệu test được mask độc lập từng cột nên foreign key và quan hệ giữa khách hàng, đơn hàng, thanh toán bị mất; test tích hợp không còn phản ánh hành vi thực.
Nhóm dùng cùng mapping pseudonym cho mọi bộ test và chia sẻ file mapping trong repository; dữ liệu giả có thể được đảo ngược để tìm khách hàng production.
Tokenization trong test tạo mã mới mỗi lần refresh dataset; các lần chạy test không thể so sánh kết quả và lỗi liên kết dữ liệu khó tái hiện.
Masking giảm độ chính xác số tiền và ngày giao dịch để bảo vệ riêng tư nhưng không đánh giá tác động tới mô hình phát hiện gian lận; chất lượng phân tích giảm ngoài dự kiến.
Nhóm đánh giá hiệu quả masking chỉ bằng số trường được che; không đo rủi ro re-identification (tái nhận diện) qua join với dữ liệu ngoài, tần suất hiếm hoặc nhóm có kích thước nhỏ.
Chính sách masking được cấu hình ở nhiều service bằng các regex riêng; thay đổi một trường PII không đồng bộ và tạo ra nơi che, nơi lộ.
Nhân viên được phép xem dữ liệu đầy đủ trong một thời gian ngắn nhưng hệ thống không ghi ai unmask, trường nào, mục đích gì và dữ liệu được xuất đi đâu.
