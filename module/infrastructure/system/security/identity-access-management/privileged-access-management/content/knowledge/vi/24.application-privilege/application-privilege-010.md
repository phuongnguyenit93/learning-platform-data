# Log management permission

Log giúp điều tra lỗi, theo dõi vận hành và nối một thao tác đặc quyền với người thực hiện. Tuy nhiên, người có quyền quản lý log cũng có thể đọc dữ liệu nhạy cảm, xuất bằng chứng ra ngoài hoặc làm mất khả năng quan sát. Vì vậy, quyền quản lý log là một phần của quản lý đặc quyền ứng dụng, không chỉ là quyền sử dụng công cụ tìm kiếm.

Một kỹ sư được phép restart ứng dụng không mặc nhiên được đọc toàn bộ log production. Một service cần gửi sự kiện vào hệ thống log cũng không cần quyền xóa index hay sửa thời hạn lưu. Tương tự, người điều tra một sự cố cần đọc bằng chứng nhưng thường không cần quyền thay đổi chính nơi bảo quản bằng chứng đó.

Bài học này xây dựng cách thiết kế, cấp và kiểm tra quyền quản lý log trong phạm vi Privileged Access Management (PAM). Các vai trò, API và chính sách dưới đây là ví dụ kiến trúc, không phải cú pháp cấu hình của một sản phẩm cụ thể.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt quyền đọc log với quyền ghi, cấu hình, xuất, lưu giữ và hủy log.
- Xác định ranh giới truy cập theo ứng dụng, môi trường, tenant, loại log và thời gian.
- Cấp quyền điều tra tạm thời mà không trao quyền quản trị toàn bộ nền tảng log.
- Tách danh tính phát sinh sự kiện, bộ thu thập, người vận hành và người phê duyệt.
- Bảo vệ audit log của chính các thao tác quản trị log.
- Kiểm tra quyền hiệu lực trên API, luồng log trực tiếp, job xuất dữ liệu và nơi lưu bản sao.

## 2. Vì sao quyền log trở thành đặc quyền?

Giả sử một nhóm hỗ trợ có tài khoản chung với quyền quản trị hệ thống log. Tài khoản được dùng cho ba công việc: xem lỗi đăng nhập, tải log để gửi điều tra và dọn dữ liệu cũ.

Một credential như vậy có thể đồng thời:

1. Đọc sự kiện của nhiều ứng dụng và nhiều tenant.
2. Thu thập thông tin định danh, metadata nội bộ hoặc bí mật bị ghi nhầm.
3. Thay bộ lọc để các sự kiện đăng nhập thất bại không còn được lưu.
4. Giảm thời hạn lưu rồi khiến bằng chứng bị dọn sớm.
5. Xóa dữ liệu hoặc tắt cảnh báo trước khi thực hiện một thay đổi khác.

Nguy cơ không chỉ nằm ở lệnh xóa trực tiếp. Thay đổi tuyến gửi log, bộ biến đổi dữ liệu, quyền đọc hoặc khóa mã hóa cũng có thể khiến bằng chứng không còn sử dụng được.

Trong PAM, cần xem xét cả hai hướng:

- **Bảo mật dữ liệu:** ai có thể quan sát và mang thông tin ra khỏi hệ thống?
- **Bảo vệ bằng chứng:** ai có thể thay đổi cách tạo, thu thập, lưu giữ và kiểm tra log?

Không thể giải quyết hai hướng này bằng một vai trò chung có tên `LogAdmin`.

## 3. Phân loại dữ liệu trước khi cấp quyền

Các loại log có mục đích và độ nhạy cảm khác nhau.

| Loại dữ liệu | Ví dụ | Điều cần chú ý khi cấp quyền |
| --- | --- | --- |
| Log ứng dụng | Lỗi xử lý job, timeout, mã tương quan | Có thể chứa định danh khách hàng hoặc dữ liệu nghiệp vụ |
| Log truy cập | Chủ thể gọi API, tài nguyên, kết quả | Có thể lộ mô hình sử dụng, địa chỉ mạng và đường quản trị |
| Audit log đặc quyền | Cấp quyền, đổi cấu hình, truy cập vault | Là bằng chứng về thay đổi quyền và hoạt động quản trị |
| Log của nền tảng log | Đổi retention, sửa policy, xuất dữ liệu | Phải quan sát được người đang quản lý chính hệ thống log |
| Dữ liệu chẩn đoán chi tiết | Stack trace, payload được ghi có kiểm soát | Phạm vi đọc thường cần hẹp hơn log vận hành thông thường |
| Bản lưu và bản xuất | Archive, snapshot, kết quả điều tra | Có quyền và vòng đời riêng, dễ trở thành đường truy cập phụ |

Một trường tên `message` không làm dữ liệu bên trong trở nên ít nhạy cảm. Nội dung có thể chứa email, định danh phiên hoặc credential bị ứng dụng ghi sai.

Phân loại nên dựa trên dữ liệu thực tế và tác động của việc lộ dữ liệu. Nếu chưa xác định được nội dung, không mặc định rằng tất cả thành viên nhóm phát triển đều được đọc toàn bộ log production.

### 3.1. Giảm dữ liệu tại nguồn và phân quyền là hai lớp bổ sung

Ứng dụng cần tránh ghi password, access token, private key, session cookie và các bí mật khác. Cần hạn chế dữ liệu cá nhân hoặc nội dung nghiệp vụ không cần thiết cho mục đích quan sát.

Tuy vậy, việc lọc dữ liệu không thay thế phân quyền. Bộ lọc có thể bỏ sót một định dạng mới; dữ liệu tưởng như không nhạy cảm cũng có thể trở nên nhạy cảm khi kết hợp nhiều nguồn.

Ngược lại, phân quyền chặt không phải lý do để đưa secret vào log. Khi phát hiện secret đã bị ghi, cần xử lý credential liên quan và kiểm soát các bản sao theo quy trình ứng phó, thay vì chỉ thu hẹp quyền đọc rồi coi sự cố đã kết thúc.

## 4. Lập danh mục hành động, không chỉ tên vai trò

Trước khi thiết kế role, hãy liệt kê các hành động hệ thống thực sự hỗ trợ.

| Nhóm quyền | Hành động minh họa | Rủi ro chính |
| --- | --- | --- |
| Khám phá | Liệt kê nguồn, index, schema, dashboard | Lộ tên hệ thống, tenant hoặc cấu trúc dữ liệu |
| Đọc | Tìm kiếm, đọc bản ghi, tail log trực tiếp | Truy cập dữ liệu ngoài nhiệm vụ |
| Xuất | Tạo export, tải tệp, chia sẻ kết quả | Tạo bản sao nằm ngoài cơ chế thu hồi truy cập ban đầu |
| Ghi | Gửi sự kiện, ghi batch, phát lại dữ liệu | Giả mạo, làm nhiễu hoặc gây quá tải bằng chứng |
| Biến đổi và định tuyến | Sửa parser, redaction, filter, sink | Làm mất sự kiện hoặc đưa dữ liệu sang nơi khác |
| Lưu giữ | Đổi retention, archive, lifecycle | Hủy bằng chứng sớm hoặc giữ dữ liệu quá phạm vi cần thiết |
| Phá hủy | Xóa bản ghi, index, snapshot hoặc backup | Mất dữ liệu và khả năng điều tra |
| Quản lý truy cập | Sửa role, grant, service account | Tự cấp quyền hoặc mở rộng người được tiếp cận |
| Quản lý bảo vệ | Sửa hold, policy lưu giữ, quyền khóa mã hóa | Làm vô hiệu biện pháp bảo quản bằng chứng |
| Cảnh báo và audit | Sửa rule, tắt giám sát, đổi audit destination | Che giấu việc sử dụng đặc quyền |

Tên gọi khác nhau giữa các nền tảng. Điều cần kiểm tra là tác dụng thực tế, bao gồm quyền được thừa hưởng từ nhóm, quyền quản trị cấp cao hơn và quyền đối với kho lưu trữ bên dưới.

Một tài khoản không có nút “Delete logs” vẫn có thể làm mất log nếu được xóa bucket, rút quyền truy cập khóa mã hóa hoặc sửa lifecycle của kho chứa.

## 5. Mô hình phạm vi truy cập

Một quyền đọc có ích cần mô tả nhiều hơn câu “được xem log”.

Có thể biểu diễn quyết định truy cập như sau:

```text
Chủ thể đã xác thực
  + hành động
  + ứng dụng hoặc nguồn log
  + môi trường và tenant
  + loại dữ liệu, trường dữ liệu
  + khoảng thời gian dữ liệu
  + thời hạn quyền và điều kiện sử dụng
  → cho phép hoặc từ chối
```

Ví dụ:

> Kỹ sư trực được tìm kiếm log vận hành đã che dữ liệu nhạy cảm của billing-worker ở production trong khoảng dữ liệu liên quan đến incident được giao. Quyền có hiệu lực 45 phút; không bao gồm xuất tệp, audit log định danh hay sửa cấu hình.

Các giá trị thời gian trong ví dụ chỉ minh họa một grant cụ thể, không phải thời hạn chuẩn cho mọi tổ chức.

### 5.1. Phân biệt hai loại thời gian

**Thời gian dữ liệu** là khoảng thời điểm xảy ra các sự kiện được phép đọc.

**Thời hạn quyền** là khoảng thời gian chủ thể được sử dụng grant.

Một grant còn hiệu lực không có nghĩa người dùng được mở rộng truy vấn sang nhiều năm dữ liệu. Ngược lại, được đọc các sự kiện cũ không có nghĩa credential truy cập được tồn tại lâu dài.

Nếu hệ thống thu thập có độ trễ, cần xác định chính sách sử dụng thời gian sự kiện hay thời gian tiếp nhận, và cách xử lý sự kiện tới muộn. Không để client tự đổi cách hiểu thời gian nhằm vượt giới hạn truy vấn.

### 5.2. Phạm vi phải được thực thi bằng dữ liệu tin cậy

Ứng dụng có thể gắn `tenant_id` vào sự kiện, nhưng cần xác định bên nào tạo và kiểm soát giá trị đó. Một trường tenant do client tùy ý gửi không tự tạo được ranh giới tin cậy.

Trong hệ thống nhiều tenant, có thể cần tách dataset, kho lưu hoặc cơ chế phân quyền theo tài liệu mà nền tảng hỗ trợ. Nếu không bảo đảm được ranh giới ở mức yêu cầu, không dùng một bộ lọc giao diện để tuyên bố đã cách ly dữ liệu.

Việc ánh xạ nguồn log sang tenant và môi trường phải được bảo vệ. Sửa nhãn nguồn có thể ảnh hưởng quyền đọc ngay cả khi policy không đổi.

## 6. Tách danh tính theo chức năng

Một chuỗi log thông thường có nhiều principal:

```text
Ứng dụng phát sinh sự kiện
          |
          v
Bộ thu thập / cổng tiếp nhận
          |
          v
Kho log và lớp truy vấn
          |
          +--> Người vận hành đọc theo phạm vi
          +--> Người điều tra đọc theo grant tạm thời
          +--> Job xuất dữ liệu có danh tính riêng

Audit của các thao tác quản lý
          |
          v
Đích giám sát có quyền quản trị tách biệt
```

### 6.1. Danh tính ghi của ứng dụng

Ứng dụng chỉ cần gửi dữ liệu tới nguồn hoặc luồng được giao. Nó thường không cần liệt kê toàn bộ index, đọc log ứng dụng khác, đổi retention hay quản lý role.

Nếu collector chịu trách nhiệm tạo dataset, không vì vậy mà cấp quyền tạo và quản trị dataset cho mọi ứng dụng.

Credential ghi cần gắn với workload hoặc nhóm nguồn được xác định, có chủ sở hữu và cơ chế luân chuyển. Tránh một secret ghi chung cho mọi môi trường: một workload thử nghiệm bị xâm nhập không nên ghi vào nguồn audit production.

### 6.2. Danh tính của collector

Collector có thể cần quyền đọc nguồn, gửi tới đích hoặc tạo cấu trúc lưu trữ cụ thể. Những quyền này phải được xem xét riêng.

Collector được phép nhận dữ liệu từ một nguồn không có nghĩa được sửa mọi sự kiện lịch sử. Nếu collector làm redaction hoặc định tuyến, quyền đổi cấu hình collector cũng là quyền nhạy cảm cần audit.

### 6.3. Danh tính của con người

Người sử dụng log cần danh tính cá nhân hoặc cơ chế liên kết có thể quy trách nhiệm. Một tài khoản chung tên `ops-log` làm yếu khả năng phân biệt ai đã đọc hoặc thay đổi dữ liệu.

Credential workload không nên trở thành đường tắt để con người vượt quy trình cấp quyền tạm thời. Nếu phải có ngoại lệ vận hành, ngoại lệ cần có phạm vi, thời hạn, người chịu trách nhiệm và bằng chứng sử dụng.

### 6.4. Credential trong vòng đời PAM

Danh tính workload được nền tảng hỗ trợ có thể giảm nhu cầu giữ secret dài hạn. Khi phải sử dụng credential tĩnh, lưu ở kho bí mật phù hợp, hạn chế bên được đọc và thiết kế luân chuyển có kiểm tra.

Luân chuyển cần xác minh workload đã dùng credential mới, credential cũ được thu hồi theo kế hoạch và không có secret xuất hiện trong log triển khai. Không cấp thêm quyền quản trị log chỉ để một job dễ lấy credential hơn.

## 7. Ma trận quyền tham khảo

Bảng dưới đây mô tả các vai trò chức năng. Nó không yêu cầu mỗi tổ chức phải tạo đúng số lượng role này.

| Chức năng | Quyền cần thiết | Quyền cần tách hoặc cấp riêng |
| --- | --- | --- |
| Application log writer | Gửi sự kiện vào đúng nguồn | Đọc lịch sử, sửa retention, xóa dữ liệu |
| Người vận hành ứng dụng | Đọc log vận hành trong phạm vi được giao | Đọc dữ liệu nhạy cảm, xuất hàng loạt, sửa pipeline |
| Người điều tra được phân công | Đọc nguồn và khoảng thời gian của vụ việc | Tự mở rộng grant, xóa bằng chứng, tự duyệt export |
| Người thực hiện export | Tạo bản xuất theo phạm vi đã duyệt | Chọn nơi lưu tùy ý, chia sẻ công khai, xóa nguồn |
| Người vận hành nền tảng log | Thay cấu hình kỹ thuật được giao | Đọc mọi nội dung, tự cấp quyền điều tra, tự bỏ hold |
| Người quản lý lưu giữ | Thực thi chính sách retention đã duyệt | Tự quyết định xóa dữ liệu đang được bảo toàn |
| Người kiểm toán | Đọc policy, grant và bằng chứng phù hợp | Sửa role, sửa audit, thay kết quả điều tra |

Một nền tảng có thể gắn quyền đọc dữ liệu vào vai trò quản trị kỹ thuật. Khi đó, cần ghi nhận quyền hiệu lực này và chọn biện pháp phù hợp: tách miền quản trị, dùng công cụ quản trị hẹp hơn, giới hạn thời hạn hoặc giám sát bổ sung.

Không ghi trong tài liệu rằng quản trị viên “không đọc được dữ liệu” nếu quyền trên hệ thống thực tế cho phép họ tự cấp hoặc sử dụng quyền đọc.

## 8. Quyền đọc log: nhiều hơn thao tác tìm kiếm

### 8.1. Áp dụng phạm vi ở phía server

Một dashboard chỉ hiển thị nguồn billing không ngăn người dùng gọi API tìm kiếm nguồn payroll.

Quyết định phân quyền phải áp dụng tại ranh giới xử lý truy vấn hoặc hệ thống lưu trữ có khả năng thực thi tương ứng. Khi dùng một dịch vụ trung gian truy vấn bằng credential rộng, chính dịch vụ đó phải bảo đảm không biến thành công cụ đọc thay người không có quyền.

Ví dụ API minh họa:

```text
POST /log-search
{
  "source": "billing-prod",
  "from": "2026-01-10T02:00:00Z",
  "to": "2026-01-10T02:15:00Z",
  "query": {
    "correlation_id": "req-example-17"
  }
}
```

Server phải ánh xạ `source` tới dataset thực, đối chiếu principal, grant, khoảng dữ liệu và các trường được phép. Không chỉ tin tên nguồn mà client gửi.

Nếu dùng ngôn ngữ truy vấn linh hoạt, cần kiểm soát những cấu trúc có thể đọc nguồn khác, truy vấn con hoặc hàm truy cập dữ liệu bên ngoài phạm vi. Khi công cụ không bảo đảm được ranh giới bằng policy, nên cung cấp mẫu truy vấn hoặc giao diện hẹp hơn cho nhóm người dùng tương ứng.

### 8.2. Kết quả dẫn xuất cũng có thể lộ dữ liệu

Quyền thống kê, xem số lượng, xem schema hoặc xem danh sách giá trị có thể tiết lộ thông tin ngay cả khi bản ghi gốc bị ẩn.

Ví dụ, quyền đếm theo email hoặc tên tenant có thể cho thấy một tài khoản đang tồn tại hay một sự kiện nhạy cảm đã xảy ra. Phạm vi dữ liệu cần áp dụng nhất quán cho truy vấn tổng hợp, gợi ý tìm kiếm và metadata có liên quan.

### 8.3. Phân trang không phải quyền mới

Trang tiếp theo phải tiếp tục chịu ràng buộc của principal và phạm vi truy vấn ban đầu. Không để một cursor có thể dùng lại bởi người khác để đọc kết quả ngoài quyền.

Đối với cache kết quả, cần phân tách theo ngữ cảnh quyền phù hợp và xử lý khi quyền thay đổi. Một kết quả được tạo bằng quyền cao không nên được trả cho người có cùng câu truy vấn nhưng quyền thấp hơn.

### 8.4. Tail log và kết nối dài hạn

Một kết nối mở trước khi grant hết hạn có thể tiếp tục truyền dữ liệu nếu hệ thống chỉ kiểm tra quyền lúc bắt đầu.

Cần xác định cách thực thi thời hạn cho kết nối dài hạn: giới hạn thời lượng phiên, tái xác minh theo cơ chế hỗ trợ hoặc chủ động kết thúc khi quyền bị thu hồi. Nếu có độ trễ thu hồi, phải biết giới hạn thực tế và không mô tả nó là tức thời.

Đồng thời kiểm tra quyền với những nguồn mới được thêm vào luồng. Quyền theo dõi một nguồn không tự mở rộng sang tất cả nguồn xuất hiện sau đó.

## 9. Quyền ghi: bảo vệ nguồn gốc và chất lượng bằng chứng

Quyền gửi log không chứng minh mọi nội dung được gửi đều đúng.

Một ứng dụng bị xâm nhập có thể phát ra sự kiện giả, bỏ ghi hành động thật hoặc đặt thời gian sai. Vì vậy, log ứng dụng cần được đối chiếu với audit tại các ranh giới khác khi có thể, chẳng hạn hệ thống xác thực, cổng PAM hoặc tài nguyên đích.

### 9.1. Phân biệt dữ liệu do producer khai và dữ liệu do collector xác nhận

Có thể giữ riêng:

- Định danh producer do kênh tiếp nhận đã xác thực xác định.
- Thời điểm collector nhận sự kiện.
- Thời điểm xảy ra do ứng dụng khai.
- Principal thực hiện hành động theo ngữ cảnh của nguồn.
- Mã tương quan với nguồn audit khác.

Không cho producer tùy ý thay các trường được hệ thống coi là metadata tin cậy. Nếu ứng dụng gửi một trường `actor`, cần biết đó là lời khai của ứng dụng hay danh tính đã được một ranh giới độc lập xác thực.

### 9.2. Hạn chế ghi giả và làm nhiễu log

Áp dụng schema, giới hạn kích thước và quota phù hợp. Theo dõi lượng dữ liệu bị từ chối, mất hoặc trễ để phát hiện sự cố thu thập.

Định dạng có cấu trúc giúp phân biệt trường dữ liệu với cấu trúc bản ghi. Dữ liệu không tin cậy cần được mã hóa hoặc escape theo định dạng và giao diện hiển thị, tránh làm một chuỗi đầu vào trông như nhiều sự kiện hoặc một thông báo quản trị giả.

Việc chuẩn hóa không nên âm thầm làm mất thông tin cần điều tra. Nếu giữ dữ liệu gốc ở một tầng riêng, tầng đó cũng cần quyền đọc và chính sách lưu giữ tương ứng.

Quota giúp kiểm soát quá tải; nó không thay thế việc xác thực nguồn. Khi phải loại bỏ sự kiện, cần có tín hiệu về việc mất dữ liệu, không chỉ một dashboard tiếp tục hiển thị trạng thái bình thường.

## 10. Quyền xuất dữ liệu

Xuất log tạo một đối tượng mới với vòng đời quyền riêng. Thu hồi quyền tìm kiếm trên nguồn không thu hồi được tệp mà người dùng đã tải về.

Một quy trình xuất nên xác định:

1. Chủ thể yêu cầu và lý do.
2. Dataset, trường dữ liệu và khoảng thời gian.
3. Số lượng hoặc giới hạn dữ liệu được phép.
4. Người phê duyệt khi mức nhạy cảm yêu cầu.
5. Danh tính thực thi job.
6. Đích lưu được phép, người được tải và thời hạn tồn tại.
7. Bằng chứng về việc tạo, tải, chia sẻ và hủy bản xuất.

### 10.1. Không để job xuất mở rộng phạm vi

Job không nên nhận một truy vấn tùy ý rồi chạy bằng credential toàn quyền.

Yêu cầu đã được duyệt cần được ràng buộc với nội dung xuất cụ thể. Khi job bắt đầu sau một khoảng chờ, cần áp dụng chính sách rõ về thời hạn grant, việc thu hồi và hiệu lực phê duyệt; không mặc định quyền lúc gửi yêu cầu còn đúng tại mọi thời điểm sau đó.

Nếu người dùng sửa bộ lọc, nơi lưu hoặc loại dữ liệu, hệ thống phải xác định liệu đó có còn là yêu cầu đã duyệt hay cần duyệt lại.

### 10.2. Kiểm soát endpoint tải và đối tượng lưu

Người biết mã job không mặc nhiên được xem trạng thái hay tải tệp. API kết quả cần kiểm tra quyền trên đối tượng tương ứng.

Một đường dẫn có chữ ký có thể cho phép người cầm đường dẫn truy cập trong thời hạn và điều kiện của nó. Nếu cần truy cập ràng buộc chặt với danh tính hoặc thu hồi theo từng người, phải chọn cơ chế phù hợp thay vì giả định đường dẫn có chữ ký đã đáp ứng điều đó.

Kiểm tra cả bucket, thư mục chia sẻ, bản sao tải cục bộ và kênh chuyển giao. Không gửi log nhạy cảm qua nơi chia sẻ không nằm trong phạm vi đã được phép chỉ vì việc xuất ban đầu đã được duyệt.

## 11. Quyền cấu hình pipeline và cảnh báo

Pipeline quyết định sự kiện nào đi đến đâu và dưới hình thức nào. Sửa pipeline có thể:

- Loại bỏ những sự kiện có mã lỗi cụ thể.
- Chuyển log sang kho do một bên khác kiểm soát.
- Bỏ redaction khiến dữ liệu nhạy cảm xuất hiện trong nguồn đọc rộng.
- Gán sai nguồn hoặc tenant, từ đó ảnh hưởng phân quyền.
- Thay timestamp hay parser khiến truy vấn điều tra bỏ sót sự kiện.
- Làm giảm chất lượng hoặc dừng hoàn toàn cảnh báo.

Do đó, quyền cấu hình pipeline cần được quản lý như đặc quyền thay đổi ứng dụng hoặc hạ tầng.

Thay đổi nên có chủ sở hữu, nội dung trước và sau, lý do, phê duyệt theo tác động và cách khôi phục. Kiểm tra bằng sự kiện thử nghiệm có kiểm soát để xác nhận tuyến mới thực sự nhận được log và không làm lộ dữ liệu.

Với rule cảnh báo, cần phân biệt quyền xem, quyền sửa điều kiện, quyền đổi nơi nhận và quyền tắt rule. Một người được xử lý cảnh báo không nhất thiết được thay đổi rule phát hiện hành vi của chính mình.

Nếu cần tạm im lặng cảnh báo trong bảo trì, giới hạn phạm vi và thời hạn; giữ audit về người thực hiện và tự khôi phục hoặc có cơ chế kiểm tra kết thúc theo thiết kế.

## 12. Retention, xóa dữ liệu và bảo toàn bằng chứng

### 12.1. Retention là chính sách, không chỉ là dung lượng

Thời hạn lưu cần gắn với mục đích sử dụng, độ nhạy cảm, nhu cầu điều tra và các yêu cầu áp dụng cho tổ chức. Không có một số ngày phù hợp cho mọi loại log.

Một thời hạn quá ngắn có thể khiến bằng chứng biến mất trước khi phát hiện sự cố. Giữ mọi dữ liệu vô thời hạn cũng tạo thêm chi phí và phạm vi dữ liệu cần bảo vệ.

Tách người quyết định chính sách khỏi principal thực thi dọn dữ liệu khi mức tác động yêu cầu. Job dọn dữ liệu chỉ nên có quyền cần thiết đối với tập dữ liệu và điều kiện được giao.

### 12.2. Quyền xóa phải được xem xét qua mọi đường

Không chỉ kiểm tra API xóa của ứng dụng. Cần xem xét:

- Xóa dataset, index, bucket hoặc volume.
- Sửa lifecycle để dữ liệu bị dọn sớm.
- Xóa archive, snapshot hoặc backup.
- Đổi quyền truy cập khiến dữ liệu không còn đọc được.
- Tác động khóa mã hóa làm mất khả năng giải mã.
- Xóa hoặc thay đổi metadata cần để truy vết dữ liệu.

Một lớp chặn xóa ở giao diện log không bảo vệ được dữ liệu nếu cùng principal có quyền phá hủy kho lưu bên dưới.

### 12.3. Cơ chế lưu bất biến có giới hạn cụ thể

Một số hệ thống hỗ trợ lưu một lần, đọc nhiều lần hoặc khóa lưu giữ theo cấu hình. Cần kiểm tra cơ chế thực tế: đối tượng nào được bảo vệ, thời gian nào áp dụng, ai có quyền quản trị ngoại lệ và cấp quản trị nào còn tác động được.

Không suy ra rằng bật một tính năng “immutable” khiến mọi bản sao không thể bị mất trong mọi tình huống.

Cũng cần kiểm tra tính đầy đủ của thu thập. Kho lưu không sửa được vẫn có thể chứa thiếu sự kiện nếu pipeline phía trước bị tắt.

### 12.4. Giữ dữ liệu phục vụ điều tra

Khi có yêu cầu bảo toàn dữ liệu, cần xác định tập dữ liệu, phạm vi thời gian, chủ sở hữu, cơ chế giữ và thẩm quyền kết thúc việc giữ.

Job retention thông thường phải tôn trọng trạng thái bảo toàn theo cơ chế được thiết kế. Tránh quy trình trong đó người bị điều tra có thể tự bỏ hold rồi xóa log.

Việc xóa dữ liệu nhạy cảm bị ghi sai trong khi có yêu cầu bảo toàn cần được xử lý theo quy trình được ủy quyền. Không cho người vận hành tùy ý sửa bằng chứng để “làm sạch log”.

## 13. Cấp quyền JIT/JEA cho điều tra

Just-in-Time (JIT) giới hạn thời gian có đặc quyền. Just-Enough-Administration (JEA), trong phạm vi bài này, hướng đến chức năng quản trị vừa đủ cho nhiệm vụ.

Một grant điều tra minh họa có thể được mô tả như sau:

```json
{
  "requester": "engineer-example",
  "case": "INC-example-204",
  "action": "logs.search",
  "source": "billing-prod",
  "dataWindow": {
    "from": "2026-01-10T02:00:00Z",
    "to": "2026-01-10T03:00:00Z"
  },
  "dataProfile": "operations-redacted",
  "grantExpiresAt": "2026-01-10T04:00:00Z",
  "exportAllowed": false
}
```

Đây là mô tả grant, không phải body mà client được tự khai rồi server tin.

Server cần xác minh danh tính, hồ sơ phân công, phạm vi phê duyệt và policy hiện hành. Thời hạn phải được tính theo nguồn thời gian và cơ chế tin cậy của hệ thống, không theo đồng hồ do client quyết định.

Quy trình có thể gồm:

1. Người điều tra yêu cầu quyền cho một vụ việc cụ thể.
2. Hệ thống xác minh quyền yêu cầu và lấy phê duyệt nếu cần.
3. Cấp grant hẹp hoặc phiên truy cập tạm thời.
4. Kiểm tra grant khi sử dụng trên API thực tế.
5. Hết hạn hoặc thu hồi quyền và xử lý phiên, job còn tồn tại.
6. Đối chiếu hoạt động thực tế với mục đích đã được cấp.

Một ticket hợp lệ không thay thế quyền truy cập. Cũng không nên chỉ tìm chuỗi mã ticket trong phần lý do rồi coi yêu cầu đã được phê duyệt.

Nếu hệ thống không thể xác minh grant, không tự mở rộng sang quyền quản trị chung. Cần có hành vi lỗi và đường khẩn cấp đã được thiết kế.

## 14. Audit quyền quản lý log

Chính hệ thống quản lý log cần ghi nhận những sự kiện như:

- Cấp, gia hạn, thu hồi quyền hoặc thay đổi thành viên nhóm đặc quyền.
- Thay policy, pipeline, nguồn thu thập hoặc đích lưu.
- Đổi retention, trạng thái bảo toàn hoặc quyền khóa mã hóa.
- Tạo và tải bản xuất.
- Thực hiện thao tác xóa, kể cả yêu cầu bị từ chối.
- Tắt, sửa hoặc đổi nơi nhận cảnh báo.
- Sử dụng đường truy cập khẩn cấp.
- Thay đổi cấu hình audit của chính nền tảng log.

Một bản ghi audit hữu ích cần nối được principal yêu cầu, principal thực thi, hành động, tài nguyên, thời điểm, kết quả và mã tham chiếu cấp quyền hoặc thay đổi.

Không lấy `actor` trong body làm danh tính đáng tin. Với tự động hóa, giữ cả danh tính workload và liên kết tới người hoặc quy trình đã khởi phát khi có thể.

### 14.1. Tách nơi giám sát khỏi quyền đang được giám sát

Nếu một người có thể sửa cả dữ liệu log và toàn bộ audit về việc sửa log, khả năng phát hiện can thiệp sẽ yếu.

Có thể gửi audit quản trị tới miền lưu trữ hoặc quản trị tách biệt, với quyền đọc và quyền thay đổi được thiết kế riêng. Mức tách biệt phải xét cả quyền cấp cao, credential, tài khoản nền tảng và hệ thống khóa; chỉ đổi tên bucket chưa đủ chứng minh độc lập.

Không có thiết kế nào được xem là đáng tin chỉ vì sơ đồ có hai hộp. Cần kiểm tra principal thực tế có thể làm gì ở từng nơi.

### 14.2. Không ghi audit bằng cách tạo thêm dữ liệu nhạy cảm

Truy vấn có thể chứa email, định danh khách hàng hoặc dữ liệu vụ việc. Audit truy vấn cần đủ để điều tra nhưng không nhất thiết sao chép nguyên mọi giá trị vào nguồn đọc rộng.

Có thể ghi nguồn, loại thao tác, khoảng thời gian, số lượng kết quả và tham chiếu tới hồ sơ truy vấn được bảo vệ. Việc lưu truy vấn đầy đủ hay bản biểu diễn đã lọc cần phù hợp mục đích và thiết kế điều tra.

### 14.3. Audit gặp lỗi

Xác định trước hành vi cho từng nhóm thao tác. Ví dụ, thay role hoặc xóa bằng chứng có thể yêu cầu bản ghi bền vững trước khi tiếp tục; đọc log phục vụ một tình huống khẩn cấp có thể cần đường truy cập và cách bù audit được quản trị riêng.

Không áp dụng một quy tắc “bất kỳ log nào lỗi thì dừng toàn bộ ứng dụng” một cách máy móc. Cần phân biệt log nghiệp vụ, audit bắt buộc của hành động đặc quyền, cơ chế đệm, dung lượng còn lại và rủi ro của từng hành vi lỗi.

Điều cần tránh là cho phép thay đổi đặc quyền không giới hạn trong khi mất toàn bộ dấu vết mà không ai biết.

## 15. Tình huống thực hành: điều tra lỗi thanh toán

Một doanh nghiệp có:

- Ứng dụng billing và payroll ở production.
- Log vận hành và audit cấp quyền trên cùng nền tảng tìm kiếm.
- Collector riêng cho từng ứng dụng.
- Một kho archive và một job dọn dữ liệu.
- Nhóm trực hỗ trợ cần điều tra lỗi billing.

Thiết kế ban đầu cấp cho nhóm trực role quản trị toàn bộ nền tảng log. Role này được đọc payroll, sửa collector, xuất dữ liệu và xóa index.

### 15.1. Xác định nhiệm vụ thật

Nhiệm vụ là tìm các lỗi của billing trong cửa sổ sự cố và liên kết chúng với request liên quan. Phần lớn hoạt động chỉ cần log vận hành đã che dữ liệu nhạy cảm.

Từ đó tách các nhu cầu:

| Nhu cầu | Cách cấp quyền phù hợp với nhiệm vụ |
| --- | --- |
| Xem lỗi billing | Quyền đọc đúng nguồn và khoảng dữ liệu |
| Kiểm tra hành động đổi quyền | Grant riêng cho audit liên quan khi có căn cứ |
| Lấy bản xuất phục vụ điều tra | Quy trình xuất riêng với đích lưu được kiểm soát |
| Sửa cấu hình collector | Quy trình thay đổi của người vận hành pipeline |
| Giữ bằng chứng khỏi bị dọn | Yêu cầu bảo toàn do người có thẩm quyền xử lý |
| Dọn dữ liệu hết hạn | Job có quyền theo chính sách lưu giữ |

### 15.2. Thiết kế đường thực thi

Người trực đăng nhập bằng danh tính cá nhân và được cấp grant tạm thời cho billing. Query service áp dụng ràng buộc ở server và chỉ dùng quyền tới dataset cần thiết theo kiến trúc.

Nếu cần export, hệ thống tạo một yêu cầu khác. Người dùng không được sửa dataset hoặc chuyển tệp tới bucket tùy ý sau khi duyệt.

Collector billing dùng principal gửi log riêng. Người trực không nhận credential này. Job retention cũng dùng principal khác và không được tự bỏ trạng thái bảo toàn.

Audit quản trị được đưa tới nơi mà role vận hành thông thường không thể tự xóa bằng chứng sử dụng quyền của mình.

### 15.3. Xử lý khi grant kết thúc

Hết thời hạn, truy vấn mới bị từ chối theo policy. Kết nối tail được kết thúc hoặc xử lý theo giới hạn phiên đã thiết kế.

Job export đang chờ được xử lý theo chính sách đã xác định, thay vì ngầm chạy tiếp bằng credential quản trị chung. Tệp đã tạo có quyền truy cập và vòng đời riêng; thu hồi grant đọc nguồn không được báo cáo nhầm là đã thu hồi mọi bản sao.

## 16. Kiểm thử quyền hiệu lực

Kiểm thử phải đi qua API và đường thực thi thực tế. Việc giao diện chỉ hiển thị một số nguồn là chưa đủ.

| Tình huống kiểm tra | Kết quả cần chứng minh |
| --- | --- |
| Người đọc billing truy vấn payroll bằng API | Bị từ chối hoặc không thể truy cập dữ liệu ngoài phạm vi |
| Người có quyền staging chọn nguồn production | Không được sử dụng quyền staging để đọc production |
| Admin tenant A đổi tenant trong request | Không đọc được dữ liệu tenant B |
| Thay query để dùng nguồn khác hoặc truy vấn lồng | Ranh giới dữ liệu vẫn có hiệu lực |
| Xem schema, aggregate hoặc gợi ý ngoài phạm vi | Không lộ dữ liệu qua đường dẫn xuất |
| Dùng cursor hoặc mã job của người khác | Không chiếm được quyền đọc kết quả |
| Grant hết hạn khi đang tail | Kết nối tuân thủ cơ chế hết hạn đã thiết kế |
| Grant bị thu hồi khi export đang chờ | Job được kiểm tra hoặc hủy theo policy đã xác định |
| Người đọc yêu cầu export qua endpoint trực tiếp | Không vượt được quyền xuất riêng |
| Producer tự khai nguồn hoặc tenant khác | Không được dùng trường tự khai để vượt ranh giới ghi |
| Producer gửi payload giống một bản ghi audit | Không được coi là audit của principal khác |
| Người vận hành sửa filter để bỏ sự kiện nhạy cảm | Thay đổi cần quyền phù hợp và có audit |
| Người đọc gọi API retention hoặc xóa index | Bị từ chối |
| Job dọn dữ liệu gặp tập đang được bảo toàn | Tôn trọng cơ chế giữ dữ liệu |
| Người quản trị sửa đích audit hoặc cảnh báo | Có kiểm soát và bằng chứng ngoài phạm vi tự che giấu tương ứng |
| Dùng quyền kho lưu hoặc khóa để phá hủy gián tiếp | Quyền hiệu lực phù hợp với thiết kế bảo vệ |
| Kho audit hoặc bộ kiểm tra grant lỗi | Không tự chuyển thành quyền quản trị rộng |
| Người có đúng grant thực hiện truy vấn hợp lệ | Hoàn thành nhiệm vụ và có bằng chứng sử dụng |

Kiểm tra thêm đường truy cập qua CLI, API key, service account, công cụ hỗ trợ và phiên quản trị khẩn cấp nếu chúng tồn tại. Một API được bảo vệ tốt có thể bị bỏ qua nếu người dùng vẫn giữ credential trực tiếp tới kho dữ liệu.

Các phép thử làm mất dữ liệu, đổi khóa hoặc thay retention phải sử dụng môi trường và đối tượng thử nghiệm được phép. Không xóa bằng chứng thật để chứng minh quyền xóa đã bị giới hạn.

## 17. Triển khai từ quyền rộng sang quyền hẹp

### 17.1. Kiểm kê quyền hiệu lực

Lập danh sách principal, group, role, nguồn log, đường truy cập trực tiếp, nơi export và quyền đối với archive, backup, khóa mã hóa.

Phân biệt quyền được cấp trực tiếp, được thừa hưởng và có thể tự cấp qua vai trò quản trị. Một role có tên “read-only” không chứng minh principal chỉ đọc nếu còn có quyền ở lớp khác.

### 17.2. Gắn quyền với công việc đang làm

Đối chiếu quyền với các nhiệm vụ: hỗ trợ ứng dụng, điều tra bảo mật, quản lý pipeline, vận hành lưu trữ và kiểm toán.

Không thu hồi hàng loạt mà không biết đường thay thế cho tác vụ định kỳ hoặc ứng phó sự cố. Thiết kế grant hẹp, công cụ hỗ trợ và quy trình khẩn cấp trước khi đóng đường quyền rộng tương ứng.

### 17.3. Thử nghiệm và quan sát

Thử trên phạm vi có kiểm soát, gồm cả tình huống hợp lệ và bị từ chối. Theo dõi tác vụ không hoàn thành, yêu cầu nâng quyền bất thường và sự cố mất dữ liệu thu thập.

Nếu có ngoại lệ chuyển đổi, ghi chủ sở hữu, phạm vi, ngày hết hiệu lực và điều kiện đóng. Không để ngoại lệ trở thành một tài khoản toàn quyền không có kế hoạch xử lý.

### 17.4. Rà soát định kỳ

Rà soát người đổi nhóm, workload ngừng hoạt động, quyền không còn dùng, nguồn log mới và dữ liệu thay đổi độ nhạy cảm.

Theo dõi cả chất lượng bằng chứng: độ trễ, khoảng trống thu thập, lỗi parser, log bị loại bỏ và khác biệt giữa nguồn với kho đích. Có quyền đúng nhưng mất sự kiện vẫn khiến điều tra thất bại.

## 18. Dấu hiệu cần điều tra

Những hành vi sau có thể cần đối chiếu với lịch vận hành và vụ việc hợp lệ:

- Một principal bắt đầu đọc nhiều nguồn chưa từng sử dụng.
- Truy vấn mở rộng mạnh về khoảng thời gian hoặc số lượng kết quả.
- Nhiều lần thử đổi tenant, source hoặc mã job.
- Export hàng loạt tới đích mới.
- Thay retention ngay trước một thay đổi đặc quyền khác.
- Tắt collector, parser, redaction hoặc cảnh báo ngoài lịch.
- Thay quyền trên archive, backup hoặc khóa mã hóa.
- Một workload chỉ ghi lại bắt đầu gọi API đọc hay quản trị.
- Sử dụng tài khoản khẩn cấp nhưng thiếu hồ sơ hoặc đối chiếu sau sử dụng.

Các tín hiệu này không tự chứng minh có tấn công. Chúng là điểm khởi đầu để kiểm tra danh tính, phạm vi được cấp, thay đổi liên quan và bằng chứng tại nhiều nguồn.

Khi nghi credential ghi hoặc truy vấn bị lộ, cần xem cả những nơi credential đã được dùng, dữ liệu có thể đã xuất và các job còn chờ. Thu hồi credential là một bước; nó không khôi phục bằng chứng đã xóa hay kéo lại tệp đã tải.

## 19. Bài tập tự áp dụng

Bạn được giao thiết kế quyền log cho một ứng dụng có ba môi trường và nhiều tenant. Nhóm hỗ trợ cần tìm lỗi của tenant được phân công; nhóm bảo mật cần điều tra theo vụ việc; nhóm nền tảng quản lý pipeline.

Hãy mô tả:

1. Những dữ liệu và hành động cần phân loại.
2. Danh tính nào được ghi, đọc, xuất, đổi cấu hình và dọn dữ liệu.
3. Cách server xác định tenant và môi trường đáng tin cậy.
4. Hai giới hạn thời gian của một grant điều tra.
5. Cách kiểm soát tail log, cursor và job export sau khi thu hồi.
6. Người có thể thay retention, bỏ trạng thái bảo toàn và tác động khóa.
7. Nơi ghi audit việc sử dụng đặc quyền quản lý log.
8. Các phép thử trực tiếp có thể phát hiện đường vượt quyền.

Một đáp án tốt không chỉ có bảng role. Nó cần nối mỗi quyền với nhiệm vụ, ranh giới thực thi và bằng chứng kiểm tra.

Ví dụ, “nhóm hỗ trợ chỉ xem tenant được giao” chưa đủ. Cần giải thích nguồn ánh xạ phân công, nơi áp dụng phạm vi, cách xử lý aggregate và điều gì ngăn một request API sửa tenant.

## 20. Tiêu chí hoàn thành

Thiết kế quyền quản lý log đạt mục tiêu khi có thể chứng minh:

- Dữ liệu log và tác động quản trị đã được phân loại.
- Quyền đọc, ghi, xuất, cấu hình, lưu giữ và phá hủy được xem xét riêng.
- Principal có quyền vừa đủ cho ứng dụng, môi trường, tenant và nhiệm vụ.
- Danh tính con người và workload có thể quy trách nhiệm, credential được quản lý theo vòng đời.
- Phạm vi được thực thi tại API hoặc tầng dữ liệu phù hợp, bao phủ cả kết quả dẫn xuất.
- Quyền tạm thời có cơ chế hết hạn và thu hồi được kiểm chứng với phiên dài hạn và job bất đồng bộ.
- Bản xuất, archive và backup có quyền cùng vòng đời riêng.
- Thay pipeline, retention, khóa, cảnh báo và audit không trở thành đường che giấu hoạt động.
- Bằng chứng quản trị được bảo vệ trước chính những quyền đang được giám sát trong giới hạn thiết kế thực tế.
- Kiểm thử chứng minh cả nhiệm vụ hợp lệ lẫn những yêu cầu vượt phạm vi.

Quản lý log trong PAM là quản lý khả năng quan sát và khả năng tác động vào bằng chứng. Quyền tốt giúp người được giao nhiệm vụ tìm được thông tin cần thiết, đồng thời giữ rõ ai đã tiếp cận dữ liệu, ai đã thay đổi hệ thống và bằng chứng nào còn lại để kiểm tra.

