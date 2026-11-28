# Session storage protection

## 1. Cần bảo vệ những gì khi lưu phiên?

Session storage protection là việc bảo vệ dữ liệu phục vụ quản lý phiên tại mọi nơi nó được lưu giữ: trình duyệt, ứng dụng client, bộ nhớ tiến trình, kho phiên, cache, bản sao, backup và các đầu ra vận hành.

Rủi ro không chỉ là “đọc trộm một session ID”. Nếu kẻ tấn công sửa được trạng thái phiên, họ có thể thay chủ thể, nâng mức xác thực, kéo dài thời hạn hoặc làm sống lại phiên đã bị thu hồi. Nếu dữ liệu phiên bị mất hoặc không đọc được, người dùng hợp lệ có thể bị gián đoạn hoặc hệ thống có thể xử lý lỗi theo cách bỏ qua kiểm soát.

Trong thiết kế yêu cầu bảo mật, cần bảo vệ đồng thời:

- **Tính bí mật:** credential và dữ liệu nhạy cảm không bị đọc ngoài quyền.
- **Tính toàn vẹn:** dữ kiện quyết định quyền không bị sửa trái phép.
- **Tính sẵn sàng:** phiên được xử lý theo mục tiêu vận hành và chính sách lỗi.
- **Vòng đời:** dữ liệu hết hạn, thu hồi, lưu trữ và phục hồi đúng chính sách.
- **Khả năng điều tra:** có bằng chứng truy cập và thay đổi, không làm lộ credential.

Một yêu cầu như “mã hóa session trong database” mới giải quyết một phần. Nó chưa trả lời ai đọc được dữ liệu sau giải mã, ứng dụng nào được ghi quyền, backup có chứa secret không và bản sao cũ có thể làm phiên sống lại hay không.

## 2. Phân biệt credential với trạng thái phiên

| Dữ liệu | Vai trò | Rủi ro khi lộ hoặc bị sửa |
| --- | --- | --- |
| Session credential | Client dùng để chứng minh quyền sử dụng phiên | Người giữ bản sao có thể giả mạo nếu không có ràng buộc khác |
| Mã phiên logic | Liên kết các credential và sự kiện thuộc cùng phiên | Có thể nhạy cảm; không nên mặc định an toàn để công khai |
| Chủ thể và tenant | Xác định người dùng cùng phạm vi truy cập | Sửa trái phép dẫn đến truy cập dưới danh tính hoặc tenant khác |
| Mức và thời điểm xác thực | Điều kiện cho thao tác nhạy cảm | Sửa thành “đã MFA gần đây” có thể bỏ qua xác thực lại |
| Thời điểm tạo, hết hạn, hoạt động cuối | Thực thi tuổi phiên và idle timeout | Sửa để kéo dài hoặc hồi sinh phiên |
| Trạng thái thu hồi và phiên bản | Ngăn dùng phiên cũ hoặc credential cũ | Mất hoặc ghi đè làm phiên bị thu hồi tiếp tục hoạt động |
| Refresh credential hoặc dữ liệu liên kết | Duy trì khả năng cấp access token | Lộ có thể kéo dài khả năng chiếm quyền |
| Dữ liệu nghiệp vụ kèm phiên | Hỗ trợ quy trình sử dụng | Tăng mức độ thiệt hại nếu kho phiên bị đọc |

Trong mô hình session ID opaque, client giữ một giá trị ngẫu nhiên, còn server lưu trạng thái liên quan. Trong mô hình token tự chứa, client có thể giữ cả các claim đã được bảo vệ toàn vẹn. Nhiều hệ thống kết hợp cả hai với kho refresh token hoặc dữ liệu thu hồi.

Dù dùng mô hình nào, cần lập sơ đồ dữ liệu thực tế. Không gọi một kiến trúc là “stateless” rồi bỏ qua nơi lưu token ở client, bản ghi refresh hoặc trạng thái vận hành liên quan.

### Định danh audit không nên là credential

Nếu một giá trị có thể dùng trực tiếp để truy cập, không ghi nó vào log chỉ để liên kết sự kiện. Nên có mã tham chiếu audit riêng hoặc cơ chế tham chiếu được bảo vệ phù hợp.

Một mã đã băm cũng chưa chắc phù hợp để công khai: nó vẫn có thể liên kết hành vi giữa các hệ thống hoặc bị đoán nếu đầu vào yếu. Cần đánh giá mục đích và quyền truy cập thay vì coi mọi giá trị băm là dữ liệu không nhạy cảm.

## 3. Bề mặt lưu trữ thường bị bỏ sót

~~~text
Client
  -> Cookie / bộ nhớ / vùng lưu của ứng dụng
  -> Request và các thành phần trung gian
  -> Bộ nhớ của gateway hoặc application
  -> Kho phiên chính
       -> Cache và bản sao
       -> Snapshot và backup
       -> Công cụ quản trị và luồng hỗ trợ
  -> Log, trace, dump và đầu ra chẩn đoán
~~~

Với từng vị trí cần xác định:

1. Dữ liệu nào xuất hiện.
2. Ai hoặc thành phần nào được đọc, ghi, sao chép và xóa.
3. Dữ liệu được bảo vệ khi truyền và khi lưu như thế nào.
4. Thời gian lưu và điều kiện xóa.
5. Cách xử lý khi thành phần bị xâm nhập hoặc không sẵn sàng.
6. Bằng chứng nào chứng minh kiểm soát đang có hiệu lực.

Một kho phiên được cấu hình chặt nhưng cho phép công cụ hỗ trợ xuất toàn bộ dữ liệu ra file không kiểm soát vẫn có đường rò rỉ đáng kể. Tương tự, mã hóa ổ đĩa không ngăn ứng dụng đã có quyền đọc truy xuất dữ liệu qua giao diện bình thường.

## 4. Mô hình đe dọa và yêu cầu tương ứng

| Đe dọa | Hậu quả | Hướng yêu cầu |
| --- | --- | --- |
| XSS đọc token trong vùng lưu mà JavaScript truy cập được | Chiếm phiên hoặc dùng token ngoài ứng dụng | Lựa chọn nơi lưu theo mô hình client, giảm phơi lộ và kiểm soát XSS |
| Kho phiên bị công khai trên mạng | Đọc hoặc sửa hàng loạt phiên | Cô lập mạng, xác thực kết nối và giới hạn quyền |
| Một dịch vụ có quyền ghi mọi namespace | Sửa phiên của ứng dụng khác | Tách principal và quyền theo phạm vi thực thi |
| Credential xuất hiện trong trace hoặc dump | Người có quyền quan sát lấy được phiên | Loại bỏ hoặc che dữ liệu trước đầu ra; kiểm soát dump |
| Đọc trộm backup | Lộ dữ liệu phiên và credential lịch sử | Mã hóa, kiểm soát khóa, quyền và thời hạn backup |
| Khôi phục snapshot cũ | Hồi sinh phiên đã hết hạn hoặc thu hồi | Giữ ngữ nghĩa hết hạn và xử lý trạng thái thu hồi khi phục hồi |
| Request cũ ghi đè trạng thái mới | Mất cờ thu hồi hoặc kéo dài phiên | Kiểm soát cập nhật đồng thời và phiên bản |
| Deserialization dữ liệu không tin cậy | Thay đổi trạng thái hoặc thực thi ngoài ý muốn | Schema dữ liệu rõ ràng, hạn chế kiểu và nguồn dữ liệu |
| Hết dung lượng hoặc kho phiên gián đoạn | Gián đoạn hoặc bỏ qua xác thực | Giới hạn tài nguyên và chính sách lỗi có thể kiểm chứng |

Mã hóa không thay thế kiểm soát quyền ghi. Một tác nhân có quyền hợp lệ sửa phiên thông qua ứng dụng hoặc kho dữ liệu có thể gây hại ngay cả khi dữ liệu được mã hóa trên ổ đĩa.

## 5. Bảo vệ credential phía client

### 5.1. Cookie trong ứng dụng web

Cookie có thể mang mã phiên opaque hoặc credential khác. Thiết kế nên xác định các thuộc tính tương ứng với luồng sử dụng:

- Secure để giới hạn việc gửi cookie qua kênh bảo mật theo cơ chế của trình duyệt.
- HttpOnly để hạn chế JavaScript truy cập giá trị cookie.
- SameSite phù hợp với luồng đăng nhập, điều hướng và yêu cầu chéo site.
- Domain và path giới hạn hợp lý để giảm phạm vi gửi.
- Thời hạn phù hợp với vòng đời credential và chính sách phiên.

Không mở rộng domain chỉ để thuận tiện chia sẻ cookie giữa các ứng dụng có mức tin cậy khác nhau. Path không nên được coi là ranh giới bảo mật chắc chắn giữa các ứng dụng không tin cậy trên cùng host.

HttpOnly không ngăn mọi tác động của XSS. Mã độc trong ngữ cảnh ứng dụng vẫn có thể gửi yêu cầu bằng phiên của người dùng. Cookie tự động được gửi cũng làm cần thiết việc đánh giá CSRF; thuộc tính SameSite không thay thế mọi kiểm soát ở cấp ứng dụng.

Xóa cookie khi logout là bước dọn client, không chứng minh bản sao credential đã mất hiệu lực ở server.

### 5.2. Vùng lưu JavaScript truy cập được

Web storage và các vùng lưu mà JavaScript cùng origin truy cập được không phải nơi cách ly token khỏi mã JavaScript đã bị kiểm soát trong origin đó.

Mã hóa token bằng một khóa mà cùng đoạn JavaScript có thể lấy được không tự giải quyết XSS. Kẻ tấn công có thể truy cập khóa, gọi hàm giải mã hoặc yêu cầu ứng dụng sử dụng token thay cho mình.

Sự khác biệt về thời gian tồn tại giữa local storage, session storage và bộ nhớ ảnh hưởng vòng đời dữ liệu nhưng không tự tạo khả năng bảo vệ trước mọi mã cùng origin.

Nếu kiến trúc cần JavaScript giữ token để gọi API, yêu cầu phải nêu rõ lý do, thời gian giữ, cách hạn chế tác động của XSS, phạm vi token và cách thu hồi. Không chọn nơi lưu chỉ vì thao tác đọc ghi đơn giản.

### 5.3. Client di động và ứng dụng cài đặt

Cần dùng cơ chế lưu phù hợp với nền tảng và quyền của ứng dụng. Những dữ liệu tồn tại lâu như refresh credential cần được xem xét riêng so với access token ngắn hạn.

Yêu cầu nên bao gồm:

- Không đưa credential vào file cấu hình hoặc vùng chia sẻ không được phép.
- Kiểm soát việc sao lưu và di chuyển dữ liệu ứng dụng theo chính sách.
- Không lộ qua clipboard, log, báo cáo lỗi hoặc màn hình chẩn đoán.
- Xử lý logout, mất thiết bị và thay đổi tài khoản.
- Rủi ro còn lại khi runtime hoặc thiết bị đã bị kiểm soát.

Lưu trong bộ nhớ hoặc kho bảo vệ của nền tảng làm giảm những kiểu phơi lộ nhất định, nhưng không bảo đảm an toàn tuyệt đối khi tiến trình đang sử dụng credential bị kiểm soát.

### 5.4. Giảm dữ liệu ở client

Không đưa dữ liệu nhạy cảm vào token chỉ vì có thể ký token. Chữ ký bảo vệ toàn vẹn theo cơ chế được chọn, không mặc nhiên che nội dung token.

Nếu client không cần biết một thuộc tính, cân nhắc giữ nó ở server. Nếu cần mã hóa dữ liệu phía client, phải xác định bên giữ khóa, nguồn tin cậy và cách kiểm tra toàn vẹn; không coi việc đổi định dạng dữ liệu là mã hóa.

## 6. Bảo vệ kho phiên phía server

### 6.1. Xác thực kết nối và quyền tối thiểu

Mỗi ứng dụng hoặc thành phần nên kết nối bằng principal được quản lý với quyền phù hợp. Không dùng một credential quản trị chung cho mọi workload chỉ để tiện cấu hình.

Cần xác định rõ ai được:

- Đọc trạng thái phiên.
- Tạo và cập nhật trạng thái.
- Thu hồi hoặc xóa.
- Liệt kê hàng loạt.
- Xuất dữ liệu.
- Thay cấu hình, backup hoặc phục hồi kho.

Nếu sản phẩm lưu trữ không hỗ trợ tách quyền chi tiết cần thiết, thiết kế có thể cần lớp dịch vụ kiểm soát truy cập hoặc tách kho theo ranh giới rủi ro. Việc đặt tiền tố khóa chỉ là quy ước đặt tên nếu không có kiểm soát thực thi tương ứng.

Quyền quản trị kho cần được tách khỏi quyền ứng dụng thông thường và được audit. Công cụ hỗ trợ nên hiển thị thông tin cần cho xử lý sự cố, không mặc định hiển thị credential.

### 6.2. Cô lập môi trường và phạm vi

Phiên production không được dùng chung miền tin cậy lưu trữ với môi trường thử nghiệm theo cách cho phép workload thử nghiệm đọc hoặc sửa.

Trong hệ thống nhiều ứng dụng hoặc tenant, cần phân biệt:

- Tách namespace để tránh đụng khóa.
- Tách quyền thực tế để ngăn truy cập chéo.
- Tách tài nguyên khi cần giới hạn ảnh hưởng sự cố.

Một ứng dụng có tên khóa riêng nhưng credential kết nối vẫn đọc được toàn kho chưa được cách ly bằng quyền.

Tenant ID đi từ request không được trực tiếp trở thành quyền chọn namespace tùy ý. Phải đối chiếu phạm vi với danh tính và chính sách tin cậy.

### 6.3. Bảo vệ đường truyền

Kết nối tới kho phiên, bản sao và luồng quản trị phải có cơ chế bảo vệ phù hợp, gồm xác thực các đầu và bảo vệ dữ liệu trong truyền.

Không chỉ bảo vệ chặng client–gateway rồi truyền session credential hoặc trạng thái nhạy cảm qua một chặng nội bộ không được đánh giá. Ranh giới nội bộ vẫn cần có mô hình tin cậy và quyền truy cập rõ ràng.

Bí mật kết nối kho phải có vòng đời riêng: cấp, lưu, rotation và thu hồi. Credential ứng dụng đọc kho phiên không nên trở thành một secret dài hạn bị nhúng trong source code.

### 6.4. Mã hóa khi lưu và giới hạn của nó

Mã hóa ổ đĩa, volume hoặc dịch vụ lưu trữ có thể bảo vệ trước một số tình huống lấy được thiết bị hoặc dữ liệu thô. Nó thường không ngăn một principal đã được hệ thống cho phép đọc dữ liệu bình thường.

Nếu cần bảo vệ thêm trước người có quyền đọc lớp lưu trữ nhưng không được đọc nội dung, có thể cần mã hóa ở lớp ứng dụng. Khi đó phải quản lý khóa tách biệt phù hợp, dùng thư viện được kiểm chứng và bảo vệ tính toàn vẹn của bản mã.

Nếu thiết kế gắn bản mã với phiên, tenant hoặc phiên bản dữ liệu, cần kiểm tra ràng buộc đó để hạn chế việc chuyển bản mã sang ngữ cảnh khác. Chỉ mã hóa mà không kiểm tra toàn vẹn không đủ để chống sửa đổi.

Khóa giải mã không được đặt trong cùng file export hoặc backup không được bảo vệ với dữ liệu. Quy trình rotation và phục hồi khóa cũng phải đáp ứng mục tiêu sẵn sàng; không chỉ kiểm tra khả năng mã hóa lúc ghi.

## 7. Có nên lưu session credential nguyên giá trị?

Với credential opaque có entropy cao và chỉ cần so khớp hoặc tra cứu, có thể thiết kế lưu một giá trị dẫn xuất thay vì nguyên credential. Khi kho bị đọc, việc không có sẵn bearer credential có thể giảm khả năng tái sử dụng trực tiếp.

Ví dụ khái niệm:

~~~text
Client giữ: credential ngẫu nhiên S
Server tra cứu: lookupKey = hàm dẫn xuất được thiết kế cho S
Bản ghi: chủ thể, hạn, trạng thái, phiên bản và dữ kiện cần thiết
~~~

Nếu dùng hàm băm hoặc HMAC, cần xác định entropy đầu vào, cách tạo giá trị tra cứu, quản lý khóa nếu có và tác động khi rotation. Đây không phải bài toán giống hệt lưu mật khẩu do người dùng tự chọn.

Không coi “đã băm” là giải quyết toàn bộ rủi ro:

- Credential yếu vẫn có thể bị đoán.
- HMAC phụ thuộc vào bảo vệ khóa.
- Kẻ có quyền sửa kho vẫn có thể sửa principal hoặc trạng thái.
- Credential vẫn xuất hiện ở nơi tiếp nhận request và trong bộ nhớ lúc sử dụng.
- Dữ liệu liên quan trong bản ghi vẫn có thể nhạy cảm.

Không áp cách này máy móc cho mọi framework. Kho session do framework quản lý có thể dùng session ID theo contract riêng; thay cách định danh phải tương thích với việc tra cứu, replication, rotation và thu hồi.

Mục tiêu yêu cầu nên là giảm tác động của việc đọc trộm kho trong mô hình đe dọa đã chọn, rồi chứng minh cơ chế cụ thể đáp ứng mục tiêu đó.

## 8. Bảo vệ tính toàn vẹn khi đọc và cập nhật

### 8.1. Chỉ lưu dữ liệu cần thiết và có schema

Kho phiên không nên trở thành nơi chứa tùy ý toàn bộ đối tượng nghiệp vụ. Dữ liệu càng nhiều, chi phí bảo vệ, replication, xóa và điều tra càng lớn.

Một bản ghi khái niệm có thể gồm:

~~~yaml
audit_session_ref: audit-session-042
subject_ref: user-208
tenant_ref: tenant-17
created_at: 2026-01-10T08:00:00Z
absolute_expires_at: 2026-01-10T16:00:00Z
last_activity_at: 2026-01-10T08:12:00Z
authentication_level: verified-level-2
revoked_at: null
revision: 42
~~~

Đây là ví dụ dữ liệu trạng thái, không phải schema triển khai bắt buộc. Mã tham chiếu audit không phải credential mà client dùng để truy cập.

Mỗi field cần có nguồn và quyền sửa. Chẳng hạn, chỉ sự kiện xác thực hợp lệ được nâng mức xác thực; request cập nhật giao diện không được tự đặt authentication_level.

Quyền hoặc role lưu trong phiên có thể trở nên cũ. Nếu chọn cache quyền trong phiên, cần xác định thời hạn cập nhật, cơ chế vô hiệu hóa và nguồn quyền chuẩn. Bảo vệ bản ghi khỏi sửa trái phép không giải quyết việc dữ kiện hợp lệ nhưng đã lỗi thời.

### 8.2. Không hồi sinh phiên bằng cập nhật cũ

Một race condition thường gặp:

~~~text
Request A đọc phiên đang hoạt động, revision = 42
Request B thu hồi phiên, ghi revision = 43
Request A hoàn tất và ghi lại toàn bộ bản ghi revision = 42
Kết quả sai: trạng thái thu hồi bị mất
~~~

Yêu cầu phải bảo đảm cập nhật từ trạng thái cũ không ghi đè quyết định thu hồi hoặc làm dài hạn phiên trái chính sách. Cơ chế có thể là kiểm tra phiên bản, thao tác nguyên tử hoặc mô hình cập nhật khác phù hợp.

Cập nhật last activity không được tự tạo lại phiên đã bị xóa hoặc hết hạn. Những thư viện tự ghi lại toàn bộ đối tượng phiên ở cuối request cần được đánh giá trong tình huống logout, rotation và xử lý đồng thời.

Trạng thái hoặc dấu thu hồi cần được giữ đủ lâu theo thiết kế để credential và cache liên quan không thể làm sống lại phiên. Xóa dấu thu hồi quá sớm có thể tạo cửa sổ sử dụng lại.

### 8.3. Dữ liệu được giải mã vẫn phải được kiểm tra

Tính toàn vẹn mật mã không thay thế schema và ngữ nghĩa nghiệp vụ. Một bản ghi giải mã thành công vẫn cần được kiểm tra cấu trúc, phiên bản, thời hạn và liên kết chủ thể.

Trong hệ thống Java hoặc nền tảng có cơ chế tuần tự hóa đối tượng, không coi dữ liệu từ kho là lý do để chấp nhận mọi kiểu đối tượng. Cần lựa chọn định dạng và cơ chế đọc có giới hạn, kiểm tra schema và không deserialization tùy ý dữ liệu không đáng tin cậy.

Nếu một thành phần bị chiếm có thể ghi vào kho dùng chung, dữ liệu đó nằm trên một ranh giới tin cậy quan trọng. “Kho nội bộ” không tự làm dữ liệu an toàn để thực thi hoặc chuyển thành đối tượng có hành vi tùy ý.

## 9. TTL, cache, bản sao và phục hồi

### 9.1. Hết hạn quyền khác với xóa dữ liệu

TTL giúp dọn bản ghi và kiểm soát dung lượng. Thời điểm hệ thống thực sự xóa bản ghi có thể khác thời điểm phiên phải mất hiệu lực.

Đường xác thực phải kiểm tra hạn và trạng thái theo chính sách, không chỉ kiểm tra bản ghi có tồn tại.

Tương tự, việc bản ghi đã bị xóa trên kho chính không chứng minh cache hoặc replica đã ngừng chấp nhận nó. Cần nêu rõ điểm kiểm tra và độ trễ cho phép.

### 9.2. Replication và cache

Mọi bản sao chứa dữ liệu phiên đều cần quyền, mã hóa và thời hạn tương ứng. Một replica “chỉ dùng cho phân tích” vẫn có thể chứa credential hoặc dữ kiện nhạy cảm.

Cần xác định:

- Đường đọc nào chấp nhận dữ liệu có độ trễ.
- Những quyết định nào không được dựa vào bản sao quá cũ.
- Cache được giữ dữ liệu đến khi nào.
- Thu hồi, rotation và thay quyền lan truyền ra sao.
- Hành vi khi kết nối giữa các thành phần bị gián đoạn.

Cache không được kéo dài quyết định hợp lệ qua hạn tuyệt đối của phiên chỉ vì cache entry chưa hết TTL. Nếu yêu cầu chặn thu hồi trong 60 giây, một cache cho phép độc lập trong 10 phút cần cơ chế bổ sung hoặc chính sách khác.

### 9.3. Backup và snapshot

Trước khi sao lưu kho phiên, cần hỏi dữ liệu phiên có thật sự cần phục hồi hay không. Với một số hệ thống, chấp nhận yêu cầu đăng nhập lại sau sự cố có thể giảm việc duy trì credential trong backup.

Nếu cần backup, yêu cầu nên xác định:

- Phạm vi dữ liệu sao lưu và lý do.
- Mã hóa, khóa và principal được phép đọc hoặc phục hồi.
- Thời hạn giữ và nơi lưu.
- Quyền tải xuống hoặc xuất file.
- Cách ngăn dữ liệu production đi vào môi trường kiểm chứng không được phép.
- Ngữ nghĩa hết hạn và thu hồi sau phục hồi.

Không thể coi backup là an toàn chỉ vì chỉ nhóm vận hành biết vị trí. Backup cần được đưa vào cùng mô hình đe dọa với dữ liệu chính.

### 9.4. Không làm sống lại phiên đã mất hiệu lực

Snapshot lúc 10:00 có thể chứa một phiên bị thu hồi lúc 11:00. Khôi phục snapshot lúc 12:00 không được mặc nhiên làm phiên đó hợp lệ trở lại.

Thiết kế có thể cần một nguồn trạng thái thu hồi độc lập, một cơ chế phân biệt thế hệ phiên, hoặc vô hiệu hóa các phiên không thể xác minh sau phục hồi. Cơ chế cụ thể phụ thuộc mục tiêu phục hồi và kiến trúc.

Không đặt lại created_at hoặc hạn tuyệt đối thành thời điểm khôi phục. Phiên đã hết tuổi vẫn hết tuổi dù bản ghi vừa được ghi lại.

Quy trình phục hồi cần có bằng chứng về việc giữ đúng các điều kiện này, không chỉ bằng chứng “database đã chạy lại”.

### 9.5. Xóa và lưu giữ

Dữ liệu phiên hoạt động, audit và backup có mục đích khác nhau nên có thể có thời hạn lưu khác nhau. Cần phân biệt việc chấm dứt quyền truy cập với việc xóa lịch sử điều tra.

Nếu backup bất biến hoặc chu kỳ sao lưu không hỗ trợ xóa từng bản ghi ngay, yêu cầu phải phản ánh khả năng thực tế: giới hạn quyền đọc, thời hạn giữ, quy trình hết hạn và không phục hồi quyền phiên cũ.

Không ghi một cam kết “xóa tức thì ở mọi bản sao” nếu kiến trúc không thực hiện được và chưa xác định cách kiểm chứng.

## 10. Log, trace, dump và công cụ hỗ trợ

Các thành phần quan sát thường có nhiều người truy cập hơn kho phiên chính. Chỉ một lần ghi nguyên header Cookie hoặc Authorization có thể làm credential đi vào hệ thống có vòng đời khác.

Yêu cầu nên bao gồm cả:

- Access log ở proxy và gateway.
- Application log và trace.
- Báo cáo exception.
- Log của pipeline và môi trường kiểm chứng.
- Heap dump, core dump và file chẩn đoán.
- Export của công cụ hỗ trợ.
- Dữ liệu gửi tới hệ thống quan sát bên ngoài phạm vi ứng dụng.

Nên loại bỏ hoặc che dữ liệu trước khi phát sinh đầu ra, không chỉ dựa vào thao tác dọn sau đó. Một bộ lọc ở application không bảo vệ access log của proxy nếu proxy đã ghi credential trước.

Dump có thể cần cho điều tra lỗi, nhưng phải có quyền tạo, quyền đọc, nơi lưu, thời hạn và quy trình xử lý. Credential trong bộ nhớ có thể đi vào dump dù không được lưu nguyên giá trị trong database.

Đội hỗ trợ có thể cần xem phiên được tạo khi nào, ở thiết bị nào và đã thu hồi chưa; thường không cần lấy được credential để đăng nhập như người dùng.

Audit thao tác quản trị cần nêu actor, hành động, phạm vi, thời gian và kết quả. Các sự kiện đó cũng không được chứa secret của phiên bị tác động.

## 11. Tính sẵn sàng và hành vi khi kho phiên lỗi

Mất dữ liệu hoặc độ trễ kho phiên có thể ảnh hưởng mọi request. Tuy vậy, không được tự động chuyển từ “không kiểm tra được” thành “coi như đã xác thực”.

Cần xác định theo loại truy cập:

- Hành động nào bị từ chối khi không xác minh được phiên.
- Có cho phép dùng kết quả cache hay không.
- Nếu có, cache tối đa bao lâu và không được vượt hạn nào.
- Cách tránh kéo dài phiên hoặc cấp quyền mới trong trạng thái lỗi.
- Cách thông báo và phục hồi phiên hợp lệ.

Ví dụ, một API quản trị có thể bị yêu cầu từ chối khi không xác minh được trạng thái bắt buộc. Một đường đọc rủi ro thấp có thể có chính sách dùng cache giới hạn đã được phê duyệt. Cả hai phải được ghi rõ; không để từng service tự chọn.

Cần giới hạn kích thước bản ghi phiên và lượng dữ liệu client được phép đưa vào. Nếu mọi request có thể làm phiên tăng vô hạn, một lỗi ứng dụng hoặc hành vi lạm dụng có thể gây hết bộ nhớ và ảnh hưởng nhiều người dùng.

Giới hạn dung lượng, timeout kết nối và cơ chế retry phải phối hợp với mục tiêu sẵn sàng. Retry vô hạn không làm kho an toàn hơn và có thể khuếch đại sự cố.

## 12. Bộ yêu cầu minh họa có thể kiểm chứng

Các ngưỡng dưới đây là quyết định giả định cho một ứng dụng web quản trị, không phải thông số bắt buộc cho mọi hệ thống.

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| SP-01 | Có inventory mọi nơi lưu credential và trạng thái phiên trong phạm vi ứng dụng | Đối chiếu được client, kho chính, cache, replica, backup và đầu ra chẩn đoán với owner, dữ liệu và thời hạn |
| SP-02 | Principal ứng dụng chỉ được truy cập phạm vi phiên đã cấp, không có quyền quản trị hoặc export hàng loạt ngoài nhu cầu | Gọi thao tác ngoài quyền và truy cập phạm vi ứng dụng khác đều bị từ chối tại điểm thực thi |
| SP-03 | Workload không được phép của staging không đọc hoặc sửa phiên production | Kiểm tra cả đường mạng và credential kết nối; đổi namespace không vượt được quyền |
| SP-04 | Cookie phiên của luồng web được cấu hình bảo vệ theo chính sách đã chọn | Kiểm tra thuộc tính tại response thực tế, phạm vi gửi và luồng đăng nhập liên quan |
| SP-05 | Không có credential nguyên giá trị trong log, trace, báo cáo lỗi và export hỗ trợ thuộc phạm vi | Dùng credential thử nghiệm qua đường thành công và lỗi; không tìm thấy nó trong đầu ra được thu thập |
| SP-06 | Dữ liệu phiên trong kho, replica và backup được bảo vệ khi lưu theo lớp mã hóa và phạm vi đe dọa đã định | Người chỉ có bản sao dữ liệu được bảo vệ nhưng không có quyền khóa không đọc được nội dung; đường truy cập hợp lệ được kiểm soát riêng |
| SP-07 | Thay đổi từ request cũ không được ghi đè trạng thái thu hồi mới hơn | Mô phỏng đọc trước, thu hồi sau, ghi muộn; phiên vẫn bị thu hồi và credential cũ bị từ chối |
| SP-08 | Cache và replica không làm chấp nhận phiên đã bị thu hồi quá 60 giây | Đo mọi điểm thực thi, kể cả cache nóng và thay tuyến |
| SP-09 | Mọi request tại hoặc sau hạn tuyệt đối bị từ chối theo chính sách thời gian dù bản ghi chưa bị xóa | Giữ bản ghi quá TTL dọn dữ liệu trong môi trường kiểm chứng; server vẫn từ chối đúng hạn |
| SP-10 | Phục hồi không tái kích hoạt phiên đã hết hạn hoặc thu hồi | Khôi phục snapshot cũ theo quy trình; credential liên quan không dùng được ngoài chính sách |
| SP-11 | Dữ liệu phiên chỉ được đọc theo schema và phiên bản được hỗ trợ; không chấp nhận kiểu đối tượng tùy ý | Dữ liệu sai kiểu, sai schema và trạng thái không hợp lệ bị xử lý an toàn, không tạo quyền |
| SP-12 | API quản trị từ chối khi không xác minh được trạng thái phiên bắt buộc | Gián đoạn kho và cache không dẫn đến fallback cho phép; có thông tin lỗi và audit phù hợp |

SP-06 cần chỉ rõ lớp mã hóa. Một ổ đĩa được mã hóa nhưng vẫn cho principal ứng dụng đọc dữ liệu bình thường không mâu thuẫn với mục tiêu của mã hóa ổ đĩa; nó chỉ chưa đáp ứng một mục tiêu khác như chống người có quyền đọc logic kho.

SP-08 phải đi kèm thiết kế lan truyền hoặc thời hạn cache đáp ứng được 60 giây. Không thể chứng minh bằng việc thấy lệnh thu hồi đã được ghi ở kho chính.

### Mẫu đặc tả về truy cập kho

~~~yaml
requirement_id: SP-02
subject: Principal của ứng dụng quản trị tài khoản
resource: Dữ liệu phiên thuộc phạm vi ứng dụng
allowed_operations:
  - Đọc và cập nhật trạng thái qua đường đã được phê duyệt
  - Thu hồi phiên theo quyền nghiệp vụ được xác minh
prohibited_operations:
  - Đọc hoặc sửa phiên của ứng dụng khác
  - Thay cấu hình bảo mật của kho
  - Xuất toàn bộ kho qua quyền ứng dụng thông thường
enforcement:
  - Quyền tại kho hoặc lớp dịch vụ kiểm soát tương ứng
  - Ràng buộc phạm vi có kiểm tra, không chỉ quy ước tên khóa
verification:
  - Dùng principal ứng dụng thực hiện thao tác hợp lệ
  - Thử thao tác quản trị và truy cập chéo phạm vi
  - Đối chiếu kết quả từ chối và audit
owner: Nhóm ứng dụng và nhóm nền tảng lưu trữ
~~~

Đây là ví dụ nội dung yêu cầu. Sản phẩm hoặc kiến trúc cụ thể phải có cơ chế thực thi tương ứng; không coi đoạn YAML là cấu hình quyền đã có hiệu lực.

## 13. Xây dựng bằng chứng kiểm chứng

### 13.1. Phân biệt đọc trái phép với đọc hợp lệ bị lạm dụng

Cần kiểm tra quyền của từng nhóm: workload ứng dụng, công cụ hỗ trợ, vận hành, backup và principal ngoài phạm vi. Một ca kết nối không có credential bị từ chối chưa chứng minh principal có quyền hạn chế không đọc được toàn kho.

Với dữ liệu mã hóa, cần tách:

- Bản sao thô không có quyền khóa.
- Principal kho có quyền đọc logic.
- Ứng dụng có quyền giải mã.
- Người quản trị có thể thay quyền hoặc lấy khóa.

Mỗi tình huống là một mô hình đe dọa khác nhau. Bằng chứng phải khớp với điều yêu cầu muốn bảo vệ.

### 13.2. Kiểm tra rò rỉ bằng dữ liệu thử nghiệm

Dùng credential thử nghiệm không liên quan người dùng thật để đi qua đăng nhập, refresh, logout và các đường lỗi được xác định. Thu thập đầu ra trong phạm vi rồi đối chiếu xem credential có xuất hiện không.

Cần kiểm tra cả đầu ra của thành phần trung gian và công cụ hỗ trợ. Không đưa credential production vào một file tìm kiếm hoặc báo cáo kiểm chứng để vô tình tạo thêm bản sao.

Việc không tìm thấy trong các luồng đã kiểm tra là bằng chứng trong phạm vi đó, không phải khẳng định mọi đường chưa quan sát đều an toàn.

### 13.3. Kiểm tra toàn vẹn và cập nhật đồng thời

Một kịch bản tiêu biểu:

1. Request A đọc phiên đang hoạt động.
2. Thực hiện thu hồi qua đường hợp lệ.
3. Cho request A hoàn tất cập nhật.
4. Gửi request mới bằng credential cũ tới các node.
5. Kiểm tra phiên không hồi sinh và audit không mất sự kiện.

Có thể thêm ca thay hạn, thay chủ thể hoặc mức xác thực qua đầu vào client. Mục tiêu là chứng minh dữ liệu quyết định quyền không bị điều khiển qua các đường không được phép.

### 13.4. Kiểm tra phục hồi

Tạo phiên, lấy snapshot trong môi trường kiểm chứng, sau đó thu hồi hoặc để hết hạn rồi thực hiện quy trình phục hồi. Kiểm tra credential cũ tại điểm thực thi.

Nếu chính sách phục hồi là vô hiệu hóa mọi phiên không xác minh được, bằng chứng phải cho thấy điều đó thực sự xảy ra và người dùng có đường đăng nhập lại hợp lệ.

Khả năng đọc lại backup không đồng nghĩa quy trình phục hồi đáp ứng bảo mật phiên.

## 14. Áp dụng vào một ứng dụng cụ thể

Giả sử cổng quản trị dùng cookie chứa credential opaque và lưu trạng thái trên một kho phiên tập trung.

Thiết kế yêu cầu có thể được tổ chức như sau:

- Client giữ credential trong cookie với thuộc tính được chọn cho luồng web; không sao chép thêm vào vùng JavaScript truy cập được nếu không có nhu cầu.
- Application xác thực credential, đọc trạng thái, kiểm tra hạn và quyền trước hành động.
- Principal kết nối chỉ truy cập được phạm vi ứng dụng; tài khoản quản trị kho được quản lý riêng.
- Kho và bản sao có bảo vệ đường truyền, dữ liệu khi lưu và quyền truy cập.
- Thao tác cập nhật bảo đảm request cũ không làm mất thu hồi hoặc thay mốc hết hạn.
- Cache tuân thủ hạn phiên và thời gian chặn thu hồi.
- Công cụ hỗ trợ chỉ hiển thị dữ kiện cần thiết, có audit và không xuất credential.
- Backup chỉ được giữ nếu có mục đích đã xác định; phục hồi không làm phiên cũ được cấp lại quyền.
- Sự cố xác minh trạng thái được xử lý theo chính sách lỗi cho từng loại API.

Nếu yêu cầu bổ sung là chống tái sử dụng credential khi chỉ bị đọc kho, có thể đánh giá cơ chế lưu giá trị dẫn xuất tương thích với framework. Nếu mối đe dọa là ứng dụng đã bị chiếm và có quyền đọc, sửa toàn bộ phiên, chỉ đổi cách lưu session ID không đủ; cần xem xét phân quyền, ranh giới dịch vụ và giới hạn ảnh hưởng.

## 15. Những cách diễn đạt dễ gây hiểu nhầm

| Cách viết mơ hồ | Điều còn thiếu | Cách làm rõ |
| --- | --- | --- |
| Kho phiên ở mạng nội bộ nên an toàn | Không có principal, quyền và ranh giới thực thi | Nêu nguồn được kết nối, xác thực và thao tác được phép |
| Mọi session đều mã hóa | Không rõ lớp, khóa và mô hình tấn công | Nêu dữ liệu, nơi mã hóa, bên giải mã và tình huống cần chống |
| Đã bật HttpOnly nên token không thể bị lạm dụng | Nhầm đọc cookie với khả năng gửi thao tác | Giữ yêu cầu XSS, CSRF và xác thực lại phù hợp |
| Chia namespace là đã cách ly | Quyền kết nối có thể vẫn toàn kho | Kiểm chứng truy cập chéo bị từ chối |
| Xóa key là logout ngay | Bỏ qua cache, replica và cập nhật muộn | Nêu thời hạn từ chối tại mọi điểm và chống hồi sinh |
| Backup chỉ dùng khi sự cố | Dữ liệu vẫn tồn tại và có thể phục hồi quyền cũ | Nêu quyền, mã hóa, lưu giữ và ngữ nghĩa phục hồi |
| Không log password là đủ | Session credential cũng có thể cho phép truy cập | Bao gồm cookie, token, trace, dump và export |
| Lưu hash là hết rủi ro | Không chống sửa trạng thái hoặc chiếm runtime | Liên kết biện pháp với đúng mô hình đe dọa |

Đầu ra của thiết kế là một tập yêu cầu liên kết được dữ liệu phiên, nơi lưu, tác nhân được phép, nguy cơ và tiêu chí chấp nhận. Nhờ đó, bảo vệ session storage trở thành một phần của vòng đời xác thực, phân quyền, thu hồi và phục hồi thay vì một tùy chọn mã hóa đơn lẻ.
