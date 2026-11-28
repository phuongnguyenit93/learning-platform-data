# Backup và restore — Đặc tả yêu cầu sao lưu và khôi phục an toàn

## 1. Mục tiêu là khôi phục được nghiệp vụ

Backup là quá trình tạo và quản lý bản sao phục vụ khôi phục. Restore là quá trình đưa dữ liệu hoặc cấu hình từ bản sao trở lại một môi trường có thể sử dụng. Recovery có phạm vi rộng hơn: đưa dịch vụ trở lại trạng thái vận hành được chấp nhận, bao gồm dữ liệu, hạ tầng, danh tính, khóa, cấu hình và kiểm soát bảo mật.

Một job backup báo thành công chưa chứng minh hệ thống có thể phục hồi. Bản sao có thể thiếu log giao dịch, không giải mã được, chứa dữ liệu không nhất quán hoặc phụ thuộc chính tài khoản đã bị khóa trong sự cố.

Trong phạm vi module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, cần chuyển mục tiêu “không mất dữ liệu quan trọng và khôi phục nhanh” thành yêu cầu:

- Phải bảo vệ dữ liệu, cấu hình và phụ thuộc nào?
- Chấp nhận mất tối đa bao nhiêu dữ liệu và gián đoạn bao lâu?
- Bản sao phải chống được những loại sự cố hoặc hành vi phá hoại nào?
- Ai được đọc, tạo, khôi phục hoặc xóa bản sao?
- Khóa giải mã và quyền truy cập được phục hồi theo cách nào?
- Điều kiện nào chứng minh dịch vụ đã được khôi phục an toàn?

Ví dụ, một cổng quản trị lưu hồ sơ trong cơ sở dữ liệu và tệp đính kèm trong object storage. Khôi phục DB mà thiếu tệp tạo ra hồ sơ không sử dụng được. Khôi phục cả hai nhưng phục hồi lại quyền quản trị đã bị thu hồi có thể mở lại truy cập trái phép. Cả hai trường hợp đều chưa đạt mục tiêu bảo mật, dù công cụ restore báo hoàn tất.

Sau bài học, người học cần viết được yêu cầu backup/restore có phạm vi, ngưỡng, trách nhiệm, bằng chứng và liên kết tới rủi ro, kiến trúc và kiểm thử.

Các giá trị số trong bài là giả định minh họa, không phải mức bắt buộc cho mọi hệ thống hoặc tiêu chuẩn.

## 2. Phân biệt backup với các cơ chế gần nhau

| Cơ chế | Mục tiêu chính | Giới hạn cần biết |
| --- | --- | --- |
| Replication | Duy trì bản sao cập nhật để tăng khả dụng hoặc phân phối tải | Xóa nhầm, dữ liệu lỗi hoặc thao tác phá hoại có thể được sao chép theo |
| High availability | Tiếp tục phục vụ khi một thành phần hỏng | Không tự tạo lịch sử dữ liệu sạch để quay lại |
| Snapshot | Ghi nhận trạng thái tại một thời điểm theo khả năng nền tảng | Có thể cùng miền lỗi, cùng tài khoản hoặc chưa nhất quán ứng dụng |
| Backup | Lưu bản sao có chính sách bảo vệ và khôi phục | Phải chứng minh có đủ dữ liệu, khóa và chuỗi phụ thuộc |
| Archive | Lưu dữ liệu dài hạn theo mục tiêu tra cứu hoặc retention | Không mặc nhiên đáp ứng thời gian khôi phục dịch vụ |
| Disaster recovery | Tổ chức phục hồi dịch vụ sau sự cố lớn | Cần cả con người, hạ tầng, quy trình và kiểm thử |

Snapshot có thể là một phần của giải pháp backup nếu được quản lý và bảo vệ phù hợp. Không nên kết luận “snapshot luôn không phải backup” hoặc “có snapshot là đủ”. Điều quan trọng là nó đáp ứng kịch bản mất mát nào, tồn tại ở đâu, ai có thể xóa và cách khôi phục đã được kiểm chứng hay chưa.

Replication giúp giảm gián đoạn ở một số tình huống nhưng không thay thế bản sao lịch sử được bảo vệ trước lỗi logic hoặc thao tác phá hoại.

## 3. Đi từ mô hình đe dọa đến yêu cầu

Tài sản cần bảo vệ bao gồm dữ liệu nghiệp vụ, cấu hình phục vụ, danh tính và quyền, bí mật, khóa giải mã, bằng chứng audit và năng lực khôi phục.

| Kịch bản | Hậu quả | Hướng yêu cầu |
| --- | --- | --- |
| Xóa nhầm một bảng hoặc tập hồ sơ | Mất dữ liệu hợp lệ | Có điểm khôi phục trước thao tác lỗi và quy trình phục hồi có đối soát |
| Hỏng vùng triển khai | Bản chính và bản sao cùng vùng không truy cập được | Có bản sao và phụ thuộc phục hồi ngoài miền lỗi đó |
| Ransomware mã hóa dữ liệu | Bản đang vận hành không sử dụng được | Bản sao có bảo vệ chống sửa/xóa và điểm sạch được kiểm chứng |
| Tài khoản vận hành bị chiếm | Kẻ tấn công xóa backup hoặc giảm retention | Phân tách quyền, bảo vệ control plane và audit thay đổi chính sách |
| Lỗi dữ liệu phát hiện muộn | Các bản sao mới đều đã chứa lỗi | Retention và lịch sử đủ cho cửa sổ phát hiện được phê duyệt |
| Mất khóa hoặc dịch vụ khóa | Có ciphertext nhưng không thể restore | Quản lý phiên bản khóa, quyền truy cập và kiểm thử giải mã tại nơi phục hồi |
| Rò rỉ bản sao | Lộ toàn bộ dữ liệu, kể cả bản đã xóa khỏi hệ thống chính | Mã hóa, quyền tối thiểu, giới hạn môi trường restore và vòng đời dữ liệu |
| Restore lại quyền hoặc bí mật cũ | Tài khoản đã thu hồi hoặc credential đã lộ hoạt động trở lại | Đối soát quyền hiện hành và luân chuyển bí mật trước khi mở dịch vụ |
| Khôi phục làm ghi đè bằng chứng | Mất dấu vết sự cố | Giữ audit và bằng chứng ngoài đích bị ghi đè |
| Hệ thống được dựng lại nhưng chưa đủ năng lực | Dịch vụ vẫn không đạt yêu cầu nghiệp vụ | Nghiệm thu đầu cuối với dữ liệu và tải đại diện |

Mục tiêu “có bản sao ở nơi khác” vẫn chưa đủ. Nơi khác có thể dùng cùng tài khoản quản trị, khóa, mạng hoặc cơ chế xóa. Kiến trúc phải xác định miền lỗi và miền quyền thực tế, thay vì chỉ đếm số vị trí lưu.

## 4. Xác định phạm vi bảo vệ và tính nhất quán

### 4.1. Lập danh mục phục hồi

Một danh mục tối thiểu có thể gồm:

| Thành phần | Nội dung cần khôi phục | Phụ thuộc hoặc yêu cầu đặc biệt |
| --- | --- | --- |
| Cơ sở dữ liệu nghiệp vụ | Dữ liệu, schema, lịch sử giao dịch phục vụ khôi phục | Phiên bản engine, thứ tự replay và điểm nhất quán |
| Tệp đính kèm | Nội dung và metadata/phiên bản liên quan | Tham chiếu từ DB không được trỏ tới tệp thiếu hoặc sai phiên bản |
| Cấu hình ứng dụng | Cấu hình chạy, feature flag, tham số bảo mật | Không phục hồi cấu hình đã bị sửa trái phép |
| Định nghĩa hạ tầng | Mạng, chính sách, deployment và phụ thuộc | Có thể truy cập khi môi trường chính không còn hoạt động |
| Danh tính và quyền | Thông tin cần tái tạo kiểm soát truy cập | Không làm sống lại quyền hoặc tài khoản đã thu hồi |
| Bí mật và khóa | Tham chiếu, phiên bản và cơ chế truy cập hợp lệ | Không để cùng một sự cố phá cả dữ liệu và khả năng giải mã |
| Audit và bằng chứng | Dấu vết phục vụ truy vết và đối soát | Có chính sách giữ riêng, không bị restore đè mất |
| Hàng đợi và trạng thái tác vụ | Công việc chờ, kết quả và trạng thái xử lý | Tránh thực thi trùng hoặc bỏ sót tác vụ có tác dụng phụ |

Không nhất thiết sao chép mọi thứ theo cùng một cách. Một số thành phần có thể tái tạo từ nguồn cấu hình đáng tin. Yêu cầu cần nêu nguồn tái tạo, phiên bản, khả năng truy cập và thời gian thực hiện thay vì mặc định “không cần backup”.

### 4.2. Tính nhất quán ở cấp ứng dụng

Một bản sao đọc được ở cấp lưu trữ chưa chắc là trạng thái ứng dụng sử dụng được. Cần phân biệt khả năng phục hồi sau gián đoạn ghi của nền tảng với trạng thái nhất quán theo nghiệp vụ.

Ví dụ, DB đã lưu bản ghi tệp nhưng nội dung tệp chưa được đưa vào bản sao. Kiểm tra checksum của từng thành phần có thể đều đạt trong khi hồ sơ vẫn không hoàn chỉnh.

Yêu cầu cần định nghĩa các bất biến, chẳng hạn:

- Mỗi hồ sơ tham chiếu tệp phải tìm được đúng phiên bản nội dung.
- Không có giao dịch đã xác nhận nhưng thiếu phần dữ liệu bắt buộc trong phạm vi điểm phục hồi.
- Số dư hoặc tổng hợp nghiệp vụ phải khớp với các bản ghi chi tiết tương ứng.
- Trạng thái tác vụ phải cho phép tiếp tục hoặc đối soát mà không tạo tác dụng phụ trùng.

Giải pháp có thể dùng điểm cắt nhất quán, versioning, manifest hoặc quy trình đối soát tùy hệ thống. Không thể chọn kỹ thuật chính xác chỉ từ một dòng “backup DB mỗi ngày”.

### 4.3. Quan hệ với hệ thống bên ngoài

Restore dữ liệu nội bộ không hoàn tác email đã gửi, giao dịch đã chuyển ra hệ thống ngoài hoặc webhook đã được phía nhận xử lý.

Quy trình cần xác định nguồn sự thật và cách đối soát các tác dụng phụ. Việc phát lại log hoặc hàng đợi phải tuân theo yêu cầu idempotency, định danh giao dịch và chính sách xử lý trạng thái không chắc chắn.

## 5. Đặc tả RPO và RTO có thể đo

### 5.1. RPO: khoảng dữ liệu có thể mất

Recovery Point Objective — RPO là mục tiêu về khoảng thời gian mất dữ liệu có thể chấp nhận trong kịch bản đã xác định.

Trong ví dụ mất vùng triển khai:

```text
t_fault   = thời điểm nghiệp vụ bị gián đoạn
t_point   = điểm dữ liệu nhất quán mới nhất có thể khôi phục hợp lệ
cửa_sổ_mất_dữ_liệu = t_fault - t_point
```

Nếu vùng mất lúc 10:00 và chỉ khôi phục được tới 09:50, cửa sổ mất dữ liệu là 10 phút. Để chứng minh dữ liệu thực sự bị mất hoặc được giữ, cần đối chiếu giao dịch đã xác nhận với dữ liệu phục hồi, không chỉ nhìn tên tệp backup.

RPO 15 phút không đồng nghĩa “chạy job mỗi 15 phút là đạt”. Job có thể chạy lâu, thất bại, chưa chuyển ra miền lỗi khác hoặc thiếu log để tạo điểm khôi phục hoàn chỉnh.

### 5.2. RTO: thời gian tới trạng thái phục vụ được chấp nhận

Recovery Time Objective — RTO là mục tiêu thời gian để đưa nghiệp vụ trở lại mức phục vụ đã quy định sau điểm bắt đầu được xác định.

Với ví dụ mất vùng, thời điểm bắt đầu là lúc nghiệp vụ mất khả dụng đo được, không phải lúc đội vận hành bắt đầu chạy restore:

```text
t_start   = thời điểm nghiệp vụ mất khả dụng
t_accept  = thời điểm đạt toàn bộ điều kiện chấp nhận phục vụ
thời_gian_phục_hồi = t_accept - t_start
```

Ví dụ timeline:

| Mốc | Thời điểm | Ý nghĩa |
| --- | --- | --- |
| Mất vùng, nghiệp vụ ngừng phục vụ | 10:00 | Bắt đầu tính RTO trong kịch bản này |
| Phát hiện và kích hoạt quy trình | 10:05 | Năm phút phát hiện vẫn nằm trong RTO |
| Hạ tầng đích sẵn sàng | 10:35 | Chưa có nghĩa dữ liệu hoặc dịch vụ đã sẵn sàng |
| Restore dữ liệu hoàn tất | 11:05 | Còn kiểm tra và khôi phục kiểm soát |
| Đạt điều kiện mở dịch vụ | 11:30 | RTO thực tế 90 phút |

Nếu điểm dữ liệu phục hồi là 09:50, cửa sổ mất dữ liệu là 10 phút. Hai kết quả 10 phút và 90 phút đo hai mục tiêu khác nhau.

### 5.3. Chỉ tiêu phải gắn với kịch bản và phạm vi

Giả định cổng quản trị đặt mục tiêu cho tình huống mất vùng, với quyền truy cập bản sao và khóa ngoài vùng còn hợp lệ:

- RPO không quá 15 phút cho tập dữ liệu DB và tệp đã định nghĩa.
- RTO không quá 120 phút.
- Phục hồi tối thiểu chức năng đăng nhập, tra cứu và cập nhật hồ sơ.
- Chỉ mở truy cập sau khi phân quyền, tenant, audit và các bất biến dữ liệu đạt kiểm tra.

Đây không tự động là cam kết cho ransomware đã tồn tại nhiều tuần. Khi cần quay về điểm sạch cũ hơn, cửa sổ mất dữ liệu và thời gian phân tích có thể khác nhiều.

Kịch bản xâm nhập, lỗi logic phát hiện muộn và mất vùng cần mục tiêu riêng hoặc một phạm vi mục tiêu đủ rõ. Không gắn nhãn đạt RPO 15 phút chỉ vì restore được bản sao mới nhất nhưng bản đó vẫn chứa dữ liệu bị phá hoại.

### 5.4. Các giả định phải được kiểm chứng

RTO phụ thuộc dung lượng, băng thông, thời gian cấp tài nguyên, replay log, giải mã, kiểm tra và phê duyệt. Dùng thời gian restore một tập dữ liệu nhỏ để cam kết cho toàn bộ production là thiếu bằng chứng.

Nếu có điều kiện loại trừ, chẳng hạn mất đồng thời vùng chính và hệ thống khóa ngoài vùng, phải ghi rõ và phê duyệt theo rủi ro. Không phát hiện ra điều kiện loại trừ sau khi bài thử đã không đạt.

## 6. Thiết kế chuỗi backup có thể phục hồi

### 6.1. Toàn phần, gia tăng và khôi phục theo thời điểm

| Cách tổ chức | Đặc điểm | Yêu cầu kiểm chứng |
| --- | --- | --- |
| Bản toàn phần | Chứa tập dữ liệu nền theo phạm vi đã chọn | Có đủ nội dung, metadata và khả năng đọc |
| Bản gia tăng | Phụ thuộc các bản hoặc trạng thái trước đó | Chuỗi phụ thuộc liên tục và đúng thứ tự |
| Bản vi sai, nếu giải pháp hỗ trợ | Phụ thuộc bản nền theo cơ chế cụ thể | Định nghĩa đúng chuỗi cần dùng theo sản phẩm |
| Log giao dịch/PITR, nếu hệ thống hỗ trợ | Hỗ trợ replay tới điểm dữ liệu phù hợp | Có bản nền tương thích, log liên tục và điểm dừng hợp lệ |

Không nên áp một công thức restore chung cho mọi sản phẩm. Yêu cầu mô tả kết quả, chuỗi phụ thuộc và bằng chứng; thiết kế triển khai cụ thể phải theo cơ chế của hệ thống đang dùng.

Trong ví dụ, có thể tạo bản nền hàng ngày và chuyển log hoặc thay đổi mỗi 5 phút. Cấu hình này chỉ là một phương án triển khai; điều kiện đạt vẫn là tạo được điểm nhất quán ngoài miền lỗi không cũ quá RPO đã phê duyệt.

### 6.2. Manifest và catalog

Cần có thông tin đủ để chọn đúng bộ khôi phục:

- Phạm vi dữ liệu, thời điểm và phiên bản định dạng.
- Bản nền, các phần phụ thuộc và thứ tự sử dụng.
- Vị trí, kích thước, checksum hoặc dữ liệu kiểm tra toàn vẹn.
- Tham chiếu phiên bản khóa cần dùng.
- Kết quả kiểm tra và lịch sử restore đã thực hiện.
- Thông tin retention và khả năng truy cập.

Catalog cũng là tài sản phục hồi. Nếu nó chỉ nằm trong DB đã mất, người vận hành có thể không tìm được chuỗi bản sao đúng trong thời hạn.

Checksum giúp phát hiện một số lỗi thay đổi nội dung; nó không chứng minh bản sao không chứa mã độc hoặc dữ liệu nghiệp vụ đã sai. Nếu kẻ tấn công có thể sửa cả nội dung lẫn manifest, checksum không được bảo vệ cũng không đủ làm bằng chứng chống sửa đổi có chủ đích.

### 6.3. Retention phải theo rủi ro phát hiện

Thời gian giữ bản sao cần dựa trên cửa sổ phát hiện lỗi, nhu cầu quay lại lịch sử, dung lượng, bảo vệ dữ liệu và nghĩa vụ đã được xác định.

Ví dụ, retention 35 ngày không bảo đảm quay về trước một thao tác phá hoại chỉ được phát hiện sau 45 ngày. Muốn bao phủ tình huống đó cần một thiết kế lưu lịch sử phù hợp hơn hoặc chấp nhận rủi ro được phê duyệt.

Không suy luận rằng giữ càng lâu càng tốt. Bản sao kéo dài thời gian tồn tại dữ liệu nhạy cảm, tăng phạm vi cần kiểm soát truy cập và làm phức tạp xử lý yêu cầu xóa. Chính sách phải nêu thời hạn, cách hết hạn và xử lý dữ liệu khi restore.

## 7. Bảo vệ backup như một hệ thống riêng

### 7.1. Phân tách quyền và miền quản trị

Tài khoản ứng dụng không nên có quyền xóa toàn bộ lịch sử backup. Quyền tạo, đọc, restore, thay đổi retention và xóa nên được phân tách theo trách nhiệm.

Cần xem xét cả control plane. Một kho lưu không cho ghi đè trực tiếp vẫn có thể bị mất nếu tài khoản có quyền đổi policy, xóa khóa hoặc đóng môi trường chứa bản sao.

Đối với hành động phá hủy diện rộng, có thể yêu cầu phê duyệt bổ sung, cơ chế trì hoãn hoặc bảo vệ bất biến theo khả năng nền tảng. Điều kiện cụ thể cần được kiểm thử bằng đúng nhóm quyền có trong mô hình đe dọa.

### 7.2. Bản sao bất biến hoặc tách kết nối

Bản sao bất biến trong một khoảng thời gian giúp giảm nguy cơ bị sửa/xóa. Bản sao tách kết nối hoặc tách miền quản trị có thể giảm khả năng kẻ tấn công truy cập từ hệ thống chính.

Tuy nhiên, cần trả lời:

- Ai có thể đổi thời hạn bảo vệ hoặc cấu hình liên quan?
- Quyền quản trị cao hơn có thể xóa hoặc làm mất khả năng truy cập không?
- Mất khóa có làm bản sao không sử dụng được không?
- Bản sao có còn truy cập được khi hệ thống danh tính chính ngừng hoạt động không?
- Việc lấy bản sao về và giải mã có nằm trong ngân sách RTO không?

Không dùng một nhãn “immutable” để thay cho kiểm thử quyền và miền lỗi thực tế. Tính bất biến của bản sao cũng không chứng minh nội dung tại thời điểm tạo là sạch.

### 7.3. Mã hóa và phục hồi khóa

Backup có thể chứa dữ liệu, mật khẩu băm, cấu hình và bí mật có giá trị cao. Cần bảo vệ trên đường truyền và tại nơi lưu theo chính sách mật mã đã được phê duyệt.

Yêu cầu về khóa phải bao gồm:

- Phiên bản khóa tương ứng với từng tập bản sao.
- Thời hạn giữ khóa còn cần để giải mã bản sao chưa hết hạn.
- Quyền truy cập khóa tại môi trường khôi phục.
- Hành vi khi dịch vụ khóa hoặc vùng chứa khóa mất khả dụng.
- Bằng chứng restore giải mã được sau luân chuyển khóa.

Không đặt bản sao khóa hoặc credential phục hồi dưới dạng rõ ngay cạnh bản dữ liệu để “dễ restore”. Cũng không xây chu trình phụ thuộc mà muốn đọc hướng dẫn, catalog hoặc credential phục hồi lại phải khôi phục chính dịch vụ đang cần chúng.

### 7.4. Quyền truy cập khẩn cấp

Nếu cần tài khoản phục hồi khẩn cấp, phải nêu ai giữ, cách xác thực, cách cấp quyền tạm thời, audit và cách thu hồi sau sử dụng.

Quyền này cần dùng được trong tình huống hệ thống chính bị mất nhưng vẫn phải được kiểm soát. Không để một tài khoản dùng chung không truy vết trở thành cách khôi phục mặc định.

## 8. Restore phải đưa hệ thống về trạng thái an toàn

### 8.1. Khôi phục vào môi trường cô lập trước

Môi trường restore nên được kiểm soát kết nối và quyền truy cập, tránh để ứng dụng phục hồi lập tức gửi email, webhook hoặc thực thi tác vụ ra hệ thống bên ngoài.

Nếu nghi xâm nhập, cần dựng nền tảng từ nguồn đáng tin và kiểm tra dữ liệu/cấu hình theo quy trình sự cố. Restore nguyên trạng cả máy bị xâm nhập có thể khôi phục luôn cơ chế tồn tại của kẻ tấn công.

Bản sao cần được chọn theo bằng chứng về thời điểm và phạm vi ảnh hưởng, không chỉ theo mốc mới nhất. Khái niệm “điểm sạch” phải có tiêu chí và người chịu trách nhiệm, đồng thời ghi lại phần không chắc chắn còn tồn tại.

### 8.2. Không làm sống lại quyền đã thu hồi

Bản sao cũ có thể chứa tài khoản đang hoạt động tại thời điểm backup nhưng đã bị khóa sau đó. Khôi phục cả trạng thái cũ mà không đối soát sẽ tạo một dạng rollback của kiểm soát truy cập.

Trước khi mở dịch vụ, phải đối chiếu với nguồn quyền hiện hành đáng tin hoặc cơ chế đối soát được phê duyệt. Nguồn này cũng cần có kế hoạch sống sót qua sự cố; không thể chỉ nói “đối chiếu với hệ thống chính” khi hệ thống chính đã mất.

Nếu chưa xác minh được trạng thái quyền của thao tác nhạy cảm, cần hành vi hạn chế theo chính sách. Không giả định mọi quyền trong bản sao đều còn hợp lệ.

### 8.3. Bí mật, dữ liệu đã xóa và audit

Các credential nghi bị lộ cần luân chuyển hoặc thay mới trước khi sử dụng. Những tham chiếu bí mật được phục hồi phải trỏ tới phiên bản được cho phép, không tự động quay lại giá trị cũ đã bị thu hồi.

Bản sao cũng có thể chứa hồ sơ đã được xóa sau thời điểm backup. Quy trình phải có cách áp lại các quyết định xóa hoặc giới hạn xử lý theo chính sách dữ liệu hiện hành. Không tự động công khai lại dữ liệu chỉ vì nó xuất hiện trong bản phục hồi.

Audit phát sinh trong quá trình phục hồi cần lưu tại nơi không bị đè bởi thao tác restore. Giữ bằng chứng gốc của sự cố trước khi thay thế tài nguyên nếu tình huống cho phép.

### 8.4. Định nghĩa hoàn tất restore

Một điều kiện chấp nhận có thể gồm:

- Đúng tập dữ liệu và điểm phục hồi đã được phê duyệt.
- Chuỗi backup đọc được, giải mã được và không thiếu phần phụ thuộc.
- Các bất biến DB/tệp và kiểm tra nghiệp vụ đạt.
- Xác thực, phân quyền, tenant và audit hoạt động đúng.
- Không khôi phục credential hoặc quyền đã bị thu hồi ngoài chính sách.
- Chức năng nghiệp vụ trọng yếu đạt kiểm tra đầu cuối và tải tối thiểu.
- Có người phê duyệt chuyển lưu lượng cùng phương án dừng nếu phát hiện lỗi.

“Database đã start” chỉ là một mốc kỹ thuật trong quá trình này.

## 9. Bộ yêu cầu minh họa có thể nghiệm thu

Các yêu cầu dưới đây sử dụng kịch bản mất vùng và mục tiêu ở mục 5.3. Kịch bản ransomware hoặc lỗi phát hiện muộn cần bổ sung mục tiêu riêng trước khi được tuyên bố bao phủ.

| ID | Yêu cầu | Chủ sở hữu | Bằng chứng và điều kiện đạt |
| --- | --- | --- | --- |
| BKR-01 | Danh mục phục hồi phải bao phủ DB, tệp, cấu hình, khóa/tham chiếu, danh tính, audit và phụ thuộc cần cho ba chức năng trọng yếu. | Chủ dịch vụ | Đối chiếu kiến trúc với danh mục; không có phụ thuộc chưa xác định nguồn phục hồi. |
| BKR-02 | Tại mỗi thời điểm kiểm tra, hệ thống phải đánh giá được tuổi điểm dữ liệu nhất quán mới nhất có thể phục hồi ngoài vùng chính; trong trạng thái đáp ứng mục tiêu, tuổi không quá 15 phút. | Nền tảng dữ liệu | Dấu vết giao dịch và chuỗi backup chứng minh điểm khôi phục; không chỉ dựa vào giờ chạy job. |
| BKR-03 | Khi mất vùng trong phạm vi giả định, dịch vụ phải đạt điều kiện chấp nhận trong 120 phút từ lúc nghiệp vụ mất khả dụng. | Chủ dịch vụ | Diễn tập đầu cuối có timeline, điểm phục hồi và các điều kiện mục 8.4. |
| BKR-04 | Phải tồn tại bản sao ngoài miền lỗi vùng chính, cùng quyền truy cập catalog và cơ chế giải mã sử dụng được khi vùng chính mất. | Nền tảng | Diễn tập không dựa vào tài nguyên chỉ còn ở vùng bị giả lập mất. |
| BKR-05 | Tài khoản ứng dụng và tài khoản vận hành thông thường không được xóa lịch sử được bảo vệ hoặc giảm thời hạn bảo vệ ngoài quy trình được duyệt. | Bảo mật/nền tảng | Thử hành động bằng từng vai trò; từ chối đúng và có audit tại nơi độc lập phù hợp. |
| BKR-06 | Bản sao có dữ liệu nhạy cảm phải được mã hóa theo chính sách; phiên bản khóa phải còn dùng được trong toàn bộ thời gian giữ bản sao liên quan. | Quản lý khóa | Restore sau luân chuyển khóa; kiểm tra quyền và giải mã được ở môi trường đích. |
| BKR-07 | Chính sách retention phải nêu các mốc lịch sử, cửa sổ phát hiện lỗi được bao phủ và phương án khi vượt cửa sổ đó. | Chủ dữ liệu | Chọn và khôi phục mẫu ở các mốc đại diện, gồm bản gần hết hạn. |
| BKR-08 | Chuỗi restore phải kiểm tra toàn vẹn, tính liên tục và tính nhất quán DB/tệp trước khi mở dịch vụ. | Dữ liệu/ứng dụng | Thử chuỗi thiếu một phần, dữ liệu bị lỗi và tham chiếu tệp không hợp lệ; không kết luận hoàn tất khi kiểm tra không đạt. |
| BKR-09 | Trước khi chuyển lưu lượng, phải đối soát quyền, tài khoản thu hồi, bí mật và quyết định xóa dữ liệu theo nguồn đáng tin đã xác định. | Bảo mật/ứng dụng | Test quyền cũ, credential cũ và dữ liệu đã xóa không tự được kích hoạt lại trái chính sách. |
| BKR-10 | Mọi thao tác chọn bản, cấp quyền restore, thay policy, giải mã và chuyển lưu lượng phải có audit với chủ thể và kết quả, tránh bị restore đè mất. | Vận hành | Truy xuất được chuỗi phê duyệt và hành động trong bài diễn tập. |
| BKR-11 | Mỗi tháng phải diễn tập restore đầu cuối trên dữ liệu đại diện; sau thay đổi lớn về định dạng, khóa, kiến trúc hoặc dung lượng phải đánh giá và thử lại phần ảnh hưởng. | Chủ dịch vụ | Báo cáo RPO/RTO, kiểm tra bảo mật, lỗi còn mở và người xác nhận; không thay bằng kiểm tra job thành công. |
| BKR-12 | Mất job, thiếu chuỗi log, không truy cập khóa hoặc không xác định được điểm phục hồi phải tạo trạng thái không đạt/unknown cùng cảnh báo; không giữ nhãn xanh từ kết quả cũ. | Vận hành | Tiêm từng lỗi; xác minh trạng thái, thời điểm phát hiện và thông báo theo ngân sách giám sát đã quy định. |

Với BKR-12, dự án cần định nghĩa tần suất kiểm tra và thời hạn cảnh báo. Ví dụ: kiểm tra tuổi điểm phục hồi mỗi phút, cảnh báo đầu cuối không quá hai phút từ lúc phép kiểm tra phát hiện vượt 15 phút; mất bản thân luồng kiểm tra phải được cơ chế ngoài miền lỗi phát hiện. Khoảng trễ quan sát không được che giấu thành tuyên bố “luôn đạt RPO”.

BKR-02 là mục tiêu phải theo dõi và chứng minh trong phạm vi thiết kế; cảnh báo vượt ngưỡng thể hiện mục tiêu đang không được đáp ứng. Việc có cảnh báo đúng không biến trạng thái mất bảo vệ thành đạt.

### Mẫu đặc tả chi tiết

```text
ID: BKR-03
Mục tiêu: phục hồi nghiệp vụ sau mất vùng triển khai
Rủi ro: R-REC-02 — bản chính và năng lực phục vụ không còn truy cập
Phạm vi: đăng nhập, tra cứu, cập nhật hồ sơ; DB và tệp liên quan
Giả định: nguồn backup, catalog và cơ chế khóa ngoài vùng còn hợp lệ
Bắt đầu tính: thời điểm nghiệp vụ mất khả dụng được đo trong diễn tập
Kết thúc tính: toàn bộ điều kiện chấp nhận phục vụ đã đạt
Mục tiêu: không quá 120 phút
Điểm dữ liệu: nhất quán, không cũ quá RPO 15 phút của kịch bản
Chủ sở hữu: chủ dịch vụ
Phối hợp: dữ liệu, nền tảng, bảo mật và vận hành
Kiểm thử: T-BKR-02, T-BKR-03, T-BKR-06
Bằng chứng: timeline, manifest, đối soát và kết quả kiểm tra đầu cuối
```

Trong dự án thật, thay tên vai trò chung bằng nhóm và người chịu trách nhiệm cụ thể. Các trường hợp ngoài phạm vi cần có quyết định chấp nhận rủi ro hoặc yêu cầu bổ sung.

## 10. Runbook khôi phục phải đủ để thực hiện

Một runbook có thể tổ chức theo các bước:

1. **Kích hoạt:** xác nhận kịch bản, phạm vi và người chỉ huy; ghi mốc bắt đầu theo định nghĩa mục tiêu.
2. **Kiểm soát sự cố:** cô lập phần bị ảnh hưởng, hạn chế thao tác tiếp tục phá dữ liệu và giữ bằng chứng cần thiết.
3. **Chọn điểm:** xác định bộ backup và điểm nhất quán; nếu nghi xâm nhập thì đánh giá tiêu chí sạch.
4. **Chuẩn bị đích:** dựng mạng, compute, runtime, quyền và nơi giữ audit từ nguồn đáng tin.
5. **Xác minh phụ thuộc:** kiểm tra catalog, chuỗi bản sao, khóa, phiên bản và quyền đọc.
6. **Khôi phục:** thực hiện theo thứ tự đã kiểm chứng; ghi lại điểm bắt đầu/kết thúc từng phần.
7. **Đối soát:** kiểm tra DB/tệp, giao dịch, hàng đợi và tác dụng phụ liên hệ thống.
8. **Khôi phục bảo mật:** đối chiếu quyền hiện hành, thay bí mật cần thiết, kiểm tra audit và ranh giới tenant.
9. **Nghiệm thu và chuyển lưu lượng:** chạy kiểm tra nghiệp vụ, kiểm tra tải tối thiểu và phê duyệt mở dịch vụ.
10. **Theo dõi sau phục hồi:** quan sát lỗi, mở lại backup cho môi trường mới, đối soát phần dữ liệu mất và lập hành động khắc phục.

Mỗi bước cần chỉ ra người thực hiện, đầu vào, quyền cần có, điều kiện hoàn tất và xử lý khi thất bại. Không ghi credential rõ trong runbook.

Nếu phải chờ phê duyệt hoặc cấp quyền, thời gian đó vẫn thuộc RTO khi định nghĩa bắt đầu/kết thúc đã bao gồm. Không dừng đồng hồ trong diễn tập để chờ một bước mà sự cố thật vẫn cần làm.

Runbook cũng phải có điều kiện dừng: sai điểm dữ liệu, không giải mã được, không xác minh quyền hiện hành hoặc kiểm tra toàn vẹn không đạt. Dừng có kiểm soát và báo chưa đạt tốt hơn mở dịch vụ với trạng thái chưa được chấp nhận.

## 11. Ma trận kiểm thử nghiệm thu

Diễn tập trong môi trường được kiểm soát, hạn chế tác dụng phụ ra ngoài và dùng dữ liệu tổng hợp hoặc dữ liệu được bảo vệ phù hợp. Không cần xóa bản chính thật để kiểm tra một kịch bản mất vùng; có thể cô lập quyền truy cập trong bài thử theo thiết kế đã phê duyệt.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-BKR-01 | Tạo giao dịch và tệp có marker kiểm chứng, chọn điểm phục hồi, restore toàn bộ tập liên quan. | Đối chiếu được dữ liệu đã xác nhận; không có tham chiếu tệp sai; tính được cửa sổ mất dữ liệu. | BKR-01, 02, 08 |
| T-BKR-02 | Giả lập vùng chính không sử dụng được, gồm cả phụ thuộc chỉ nằm trong vùng đó. | Đọc được catalog, bản sao và khóa từ phương án ngoài vùng; không âm thầm dựa lại vùng chính. | BKR-03, 04 |
| T-BKR-03 | Chạy khôi phục đầu cuối với dung lượng và tải đại diện. | Đạt RPO ≤ 15 phút, RTO ≤ 120 phút và điều kiện bảo mật; báo riêng thời gian từng bước. | BKR-02, 03, 11 |
| T-BKR-04 | Thử xóa bản sao, giảm retention hoặc đổi policy bằng các vai trò trong mô hình đe dọa. | Quyền không được phép bị chặn; thay đổi hợp lệ tuân thủ quy trình và có audit. | BKR-05, 10 |
| T-BKR-05 | Luân chuyển khóa rồi restore bản cũ; thử mất quyền dùng một phiên bản khóa cần thiết. | Bản cũ còn giải mã được khi hợp lệ; mất quyền được nhận diện và không bị báo thành công. | BKR-06, 12 |
| T-BKR-06 | Restore bản có tài khoản sau đó đã bị thu hồi, bí mật cũ và dữ liệu đã có quyết định xóa. | Đối soát hiện hành ngăn kích hoạt trái phép; dịch vụ không mở trước khi chính sách đạt. | BKR-03, 09 |
| T-BKR-07 | Làm thiếu một phần chuỗi gia tăng/log hoặc làm sai nội dung một bản thử. | Kiểm tra phát hiện; điểm phục hồi được tính lại hoặc đánh dấu không xác định; không tuyên bố đạt theo lịch job. | BKR-02, 08, 12 |
| T-BKR-08 | Mô phỏng lỗi logic đã tồn tại trong các bản mới; chọn bản lịch sử theo bằng chứng. | Xác định được phạm vi retention bao phủ; không gọi bản mới nhất là sạch chỉ vì checksum đúng. | BKR-07, 08 |
| T-BKR-09 | Trong môi trường restore, kích hoạt tác vụ có email/webhook hoặc hàng đợi cũ. | Kết nối ngoài được kiểm soát; có đối soát và idempotency phù hợp, không tạo tác dụng phụ ngoài kế hoạch. | BKR-01, 08, 09 |
| T-BKR-10 | Dừng backup, dừng kiểm tra tuổi điểm phục hồi hoặc làm mất truy cập catalog trong các lượt riêng. | Trạng thái không đạt/unknown và cảnh báo đúng hạn; audit không bị ghi đè bởi restore. | BKR-10, 12 |
| T-BKR-11 | Khôi phục một bản gần cuối retention và kiểm tra cách hết hạn bản sao thử. | Lịch sử còn trong hạn sử dụng được; hết hạn theo policy, giữ đúng khóa và dấu vết cần thiết. | BKR-06, 07 |
| T-BKR-12 | Sau restore, tạo dữ liệu mới rồi kiểm tra vòng backup của môi trường vừa phục hồi. | Môi trường mới không trở thành điểm mù; bản sao tiếp theo và giám sát được thiết lập đúng. | BKR-01, 11, 12 |

Nếu test không đạt, báo mục tiêu nào bị vi phạm, nguyên nhân, chủ sở hữu và thời hạn khắc phục. Một báo cáo đã ghi nhận lỗi không thay thế việc đáp ứng yêu cầu.

Các phép đo cần nguồn thời gian nhất quán và dữ liệu chứng minh. Nếu thời điểm mất khả dụng thực tế không xác định chính xác, phải ghi độ không chắc chắn thay vì chọn mốc thuận lợi để đạt RTO.

## 12. Truy vết từ rủi ro đến vận hành

Chuỗi truy vết tối thiểu:

```text
Mục tiêu bảo mật và mức gián đoạn chấp nhận được
    → Kịch bản mất mát hoặc phá hoại
    → Yêu cầu BKR-xx
    → Thiết kế lưu bản sao, khóa, quyền và môi trường phục hồi
    → Runbook và test T-BKR-xx
    → Bằng chứng RPO/RTO, tính nhất quán và kiểm soát bảo mật
    → Giám sát, diễn tập lại và quản lý ngoại lệ
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Hạn chế mất dữ liệu sau mất vùng | Bản sao chưa chuyển đủ hoặc thiếu log | BKR-02, 04, 08 | Điểm phục hồi nhất quán ngoài vùng; T-BKR-01, 02, 07 |
| Chống phá hủy bản sao | Tài khoản vận hành bị chiếm | BKR-05, 10 | Phân tách quyền, bảo vệ retention, audit; T-BKR-04 |
| Giữ khả năng giải mã | Mất hoặc thu hồi khóa quá sớm | BKR-06 | Quản lý phiên bản và thử bản cũ; T-BKR-05, 11 |
| Không hồi sinh truy cập trái phép | Restore quyền, bí mật và dữ liệu cũ | BKR-09 | Nguồn đối soát đáng tin và cổng nghiệm thu; T-BKR-06 |
| Phục hồi nghiệp vụ đúng hạn | Dựng được DB nhưng chưa mở dịch vụ an toàn | BKR-03, 11 | Diễn tập đầu cuối với tải/dung lượng đại diện; T-BKR-03 |

Khi tăng dung lượng, thay DB, đổi cơ chế lưu tệp, khóa, identity provider hoặc vùng triển khai, cần đánh giá lại đường phục hồi. Một thay đổi chỉ mất vài phút để triển khai có thể làm bản sao lịch sử không còn tương thích.

Ngoại lệ phải có phạm vi, thời hạn, rủi ro còn lại, biện pháp bù và người phê duyệt. Không loại dữ liệu quan trọng khỏi báo cáo chỉ vì nó khó phục hồi.

## 13. Những lỗi đặc tả thường gặp

| Cách viết hoặc suy luận | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Backup hàng ngày.” | Không nêu mức mất dữ liệu, phạm vi và restore | Đặc tả RPO/RTO theo kịch bản và tập dữ liệu |
| “Replication thay cho backup.” | Lỗi logic có thể lan sang mọi replica | Có lịch sử phục hồi và bảo vệ khỏi cùng miền quyền |
| “Job xanh là đã an toàn.” | Có thể thiếu chuỗi, khóa hoặc dữ liệu liên quan | Chứng minh điểm phục hồi và thử restore đầu cuối |
| “Mã hóa rồi thì không còn rủi ro.” | Mất khóa hoặc quyền truy cập vẫn làm restore thất bại | Quản lý vòng đời khóa và diễn tập giải mã |
| “Có immutable là chống được mọi ransomware.” | Bản sao có thể đã chứa dữ liệu bị phá, hoặc còn đường phá control plane | Kiểm tra quyền, miền quản trị và tiêu chí chọn điểm sạch |
| “Restore xong DB là hết RTO.” | Nghiệp vụ và kiểm soát bảo mật có thể chưa hoạt động | Kết thúc tại điều kiện chấp nhận phục vụ |
| “Bản càng mới càng tốt.” | Bản mới có thể chứa lỗi hoặc xâm nhập | Chọn điểm theo kịch bản, bằng chứng và tính nhất quán |
| “Khôi phục nguyên quyền cũ cho nhanh.” | Có thể mở lại tài khoản đã thu hồi | Đối soát hiện hành trước khi chuyển lưu lượng |
| “Giữ bản sao mãi mãi.” | Tăng dữ liệu nhạy cảm và chi phí, khó quản lý xóa | Retention có căn cứ, cơ chế hết hạn và xử lý khi restore |
| “Thử một tập nhỏ là đủ.” | Không chứng minh được thời gian trên dung lượng thật | Dùng tải/dữ liệu đại diện và ghi rõ giới hạn suy luận |

## 14. Bài tập áp dụng

Một nền tảng quản lý hồ sơ dùng DB, object storage, hàng đợi gửi thông báo và dịch vụ danh tính. DB được backup mỗi đêm; tệp được replication sang vùng khác. Đội vận hành chưa từng restore toàn bộ. Mục tiêu nghiệp vụ là mất dữ liệu không quá 30 phút và khôi phục chức năng tra cứu trong 3 giờ khi mất vùng chính.

Hãy thực hiện:

1. Xác định các điểm còn thiếu giữa cơ chế hiện tại với mục tiêu RPO/RTO.
2. Lập danh mục dữ liệu và phụ thuộc, gồm khóa, quyền, catalog và nguồn cấu hình đáng tin.
3. Viết sáu yêu cầu có ID, phạm vi, ngưỡng, chủ sở hữu và bằng chứng nghiệm thu.
4. Đề xuất cách kiểm chứng tính nhất quán DB/tệp và đối soát hàng đợi khi phục hồi.
5. Thiết kế test cho mất vùng, thiếu log, mất khóa, quyền đã thu hồi và lỗi phát hiện muộn.
6. Chỉ ra vì sao mục tiêu mất vùng không tự bao phủ ransomware tồn tại nhiều tuần.
7. Viết điều kiện mở dịch vụ và điều kiện phải dừng quá trình chuyển lưu lượng.

Đáp án tốt cần chứng minh khả năng phục hồi bằng dữ liệu và kiểm thử, đồng thời giữ nguyên các mục tiêu xác thực, phân quyền, bảo vệ dữ liệu và audit.

## 15. Checklist chấp nhận yêu cầu

- Phạm vi dữ liệu, cấu hình, khóa và phụ thuộc đã đầy đủ chưa?
- RPO/RTO có kịch bản, mốc bắt đầu/kết thúc và giả định rõ ràng không?
- Có đo điểm phục hồi hợp lệ thay vì chỉ lịch chạy job không?
- Tính nhất quán liên hệ thống và tác dụng phụ có được đối soát không?
- Bản sao có sống sót qua miền lỗi và nhóm quyền trong mô hình đe dọa không?
- Catalog, hướng dẫn và quyền khẩn cấp có dùng được khi hệ thống chính mất không?
- Khóa của bản sao cũ có được giữ và giải mã thử trong toàn bộ retention không?
- Quyền, credential và dữ liệu đã xóa có được xử lý trước khi mở dịch vụ không?
- Audit và bằng chứng có tránh bị restore ghi đè không?
- Có diễn tập đầu cuối với dung lượng/tải đại diện và điều kiện nghiệm thu bảo mật không?
- Hệ thống có cảnh báo khi điểm phục hồi quá cũ, chuỗi thiếu hoặc trạng thái không xác định không?
- Sau restore, vòng backup và giám sát của môi trường mới có tiếp tục hoạt động không?

Backup và restore chỉ đáp ứng yêu cầu bảo mật khi tổ chức chứng minh được dữ liệu nào có thể phục hồi, mất bao nhiêu, mất bao lâu và dịch vụ trở lại với các kiểm soát an toàn vẫn có hiệu lực.
