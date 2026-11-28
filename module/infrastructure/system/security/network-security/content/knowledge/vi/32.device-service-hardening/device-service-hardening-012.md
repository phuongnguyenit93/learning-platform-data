# Firmware signing và kiểm tra nguồn cập nhật

Firmware của router, switch, firewall, thiết bị VPN, access point và các thiết bị mạng khác là phần mềm chạy với đặc quyền rất cao: nó có thể điều khiển luồng dữ liệu, cấu hình mạng, chức năng xác thực và khả năng quản trị từ xa. Một bản cập nhật bị thay thế, giả mạo hoặc cài nhầm có thể làm gián đoạn dịch vụ, tạo cửa hậu, làm rò rỉ dữ liệu hoặc khiến thiết bị không thể khởi động. Vì vậy, hardening thiết bị mạng phải bao gồm **xác minh chữ ký firmware** và **kiểm tra nguồn phát hành bản cập nhật**, bên cạnh phân quyền quản trị và cấu hình mạng an toàn.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vai trò của chữ ký số, hàm băm, kênh tải HTTPS và chuỗi tin cậy trong việc phân phối firmware.
- Phân biệt xác thực **ai phát hành** với kiểm tra **tệp có bị thay đổi**; nhận diện giới hạn của mỗi cơ chế.
- Mô tả cách thiết bị xác minh firmware trước khi cài đặt hoặc khởi động, bao gồm Secure Boot và chống hạ cấp phiên bản.
- Thiết lập quy trình kiểm tra nguồn, mẫu thiết bị, chữ ký, tính tương thích và kế hoạch khôi phục trước khi cập nhật.
- Xử lý tình huống chữ ký không hợp lệ, khóa ký bị thu hồi, nguồn cập nhật đáng ngờ và lỗi nâng cấp trong môi trường vận hành mạng.

## 2. Vì sao cập nhật firmware là điểm nhạy cảm về bảo mật?

Firmware có thể chứa hệ điều hành nhúng, kernel, bootloader, trình điều khiển, giao diện quản trị, dịch vụ mạng và các thành phần khởi động. Một kẻ tấn công tìm cách đưa mã độc vào thiết bị có thể lợi dụng:

| Rủi ro | Ví dụ đối với thiết bị mạng | Kiểm soát cần có |
| --- | --- | --- |
| Giả mạo bản cập nhật | Một trang web mạo danh nhà sản xuất phát tán tệp firmware đã sửa | Xác minh nguồn chính thức và chữ ký số dựa trên khóa đã tin cậy |
| Thay tệp trên đường truyền hoặc máy chủ phân phối | Máy chủ mirror/CDN bị xâm nhập, trả về tệp không đúng | Xác minh chữ ký gói và digest trong metadata đã ký |
| Hạ cấp (rollback/downgrade) | Kẻ tấn công đưa bản cũ có lỗ hổng trở lại thiết bị | Chính sách phiên bản tối thiểu, bộ đếm chống rollback hoặc metadata phiên bản |
| Cài sai dòng thiết bị | Firmware cho model hoặc revision phần cứng khác bị đưa vào switch | Ràng buộc model, hardware revision, vùng/kênh và điều kiện tương thích |
| Chiếm quyền kênh quản trị | Tài khoản quản trị bị dùng để cài gói từ nguồn không được duyệt | MFA, RBAC, ghi log, phê duyệt thay đổi và kiểm soát đường cập nhật |
| Lạm dụng khóa ký hợp lệ | Khóa ký của nhà cung cấp bị đánh cắp để ký firmware độc hại | Bảo vệ khóa, thu hồi và xoay khóa, cơ chế phục hồi chuỗi tin cậy |

Cần tách hai câu hỏi: **Bản firmware này có xuất phát từ bên được phép phát hành không?** và **Bản firmware này có phù hợp, an toàn để triển khai trên thiết bị hiện tại không?** Chữ ký số chủ yếu giúp trả lời câu hỏi đầu tiên; câu hỏi thứ hai còn cần kiểm tra bản phát hành, cấu hình, tương thích, nguy cơ bảo mật và khả năng phục hồi.

## 3. Cơ chế firmware signing

### 3.1. Hash, chữ ký số và HTTPS khác nhau thế nào?

- **Hash mật mã (digest)** như SHA-256 tạo một giá trị đại diện cho nội dung. Thay đổi một bit thường làm giá trị hash thay đổi mạnh. Hash giúp phát hiện tệp sai khác so với giá trị tham chiếu, nhưng **không tự xác nhận ai cung cấp giá trị tham chiếu**.
- **Chữ ký số (digital signature)** sử dụng khóa riêng của bên phát hành để ký trực tiếp dữ liệu hoặc hash/metadata mô tả dữ liệu. Thiết bị dùng khóa công khai tin cậy để kiểm tra chữ ký. Nếu xác minh thành công, dữ liệu được xác thực theo danh tính/quyền của khóa ký tương ứng và không bị thay đổi sau khi ký.
- **HTTPS/TLS** giúp xác thực máy chủ theo cơ chế chứng chỉ và bảo vệ dữ liệu đang truyền. TLS không thay thế xác minh chữ ký gói firmware: tệp trên một máy chủ được truy cập qua HTTPS vẫn có thể là tệp sai, bản cũ hoặc nội dung đã bị sửa trước khi tải.
- **Mã hóa** che giấu nội dung với người không có khóa giải mã; mã hóa firmware không mặc nhiên chứng minh firmware được phát hành hợp lệ.

Ví dụ: Nếu nhà cung cấp công bố tệp firmware và chuỗi SHA-256 trên cùng một trang web bị kẻ tấn công kiểm soát, kẻ đó có thể thay **cả tệp lẫn chuỗi hash**. Hash lúc này vẫn khớp. Xác minh chữ ký bằng khóa đã được thiết bị hoặc tổ chức tin cậy **từ trước và qua kênh độc lập** mới tạo thêm rào cản xác thực nguồn phát hành.

### 3.2. Luồng ký và xác minh

~~~text
NHÀ CUNG CẤP
  Mã nguồn / quy trình build được kiểm soát
             |
             v
         firmware.bin
             |
             v
  Tạo metadata: model, revision, phiên bản, hash, chính sách
             |
             v
  Ký metadata hoặc gói bằng khóa riêng được bảo vệ
             |
             v
  Phát hành firmware + metadata + chữ ký qua kênh phân phối
             |
             v
THIẾT BỊ / HỆ THỐNG QUẢN TRỊ CẬP NHẬT
  1. Có khóa công khai/gốc tin cậy được cấp trước?
  2. Chữ ký metadata/gói có hợp lệ?
  3. Hash của firmware có khớp nội dung đã ký?
  4. Model, revision, phiên bản và chính sách có phù hợp?
  5. Có đủ điều kiện cài đặt và khởi động?
             |
       Có tất cả -> Cho phép cập nhật
       Sai bất kỳ -> Từ chối, ghi log, điều tra
~~~

Có hai cách triển khai thường gặp: nhà cung cấp **ký trực tiếp tệp firmware**, hoặc **ký manifest/metadata** chứa hash của tệp firmware. Với phương án thứ hai, phải kiểm tra **cả chữ ký manifest lẫn hash của firmware**. Chỉ kiểm tra một trong hai là chưa đủ.

### 3.3. Một manifest cần ràng buộc những gì?

Bên cạnh digest của image, metadata có thể mang những thông tin sau:

| Trường | Mục đích |
| --- | --- |
| Product/model và hardware revision | Ngăn firmware của thiết bị khác được chấp nhận |
| Firmware version và release channel | Xác định phiên bản và kênh phát hành cho phép, ví dụ stable |
| SHA-256 của image và kích thước tệp | Phát hiện sai khác hoặc tải không đủ nội dung |
| Phiên bản tối thiểu / rollback index | Chặn nâng cấp hoặc hạ cấp không đáp ứng chính sách |
| Signing key ID, thuật toán, chữ ký | Xác định khóa được dùng để xác minh metadata |
| Thông tin hiệu lực / thời điểm phát hành | Hỗ trợ phát hiện metadata cũ hoặc đã hết hiệu lực |
| Dependency và yêu cầu bootloader | Kiểm tra điều kiện triển khai trước khi ghi flash |

Cú pháp manifest thực tế phụ thuộc nhà cung cấp; không có một định dạng hay một câu lệnh kiểm tra chung cho mọi router, firewall và access point. Hãy sử dụng cơ chế xác minh do nhà sản xuất tài liệu hóa, đặc biệt khi thiết bị dùng định dạng image riêng, nhiều chữ ký hoặc certificate chain.

## 4. Gốc tin cậy, Secure Boot và chống rollback

### 4.1. Khóa công khai đáng tin đến từ đâu?

Chữ ký số chỉ có giá trị khi **khóa công khai được xác minh là thuộc bên phát hành có thẩm quyền**. Nếu kẻ tấn công cung cấp cả firmware độc hại, chữ ký và khóa công khai do chính họ tạo ra, phép kiểm tra toán học vẫn có thể báo thành công nhưng không chứng minh nguồn phát hành là chính hãng.

Các cách thiết lập gốc tin cậy gồm:

- Khóa công khai hoặc hash của khóa được đưa vào ROM, OTP/eFuse, phần cứng bảo mật hoặc bộ nạp khởi động tin cậy khi sản xuất.
- Chứng chỉ/khóa phát hành được quản trị tập trung, cài đặt qua quy trình có xác thực và kiểm soát thay đổi.
- Chuỗi chứng chỉ được kiểm tra đến một gốc tin cậy đã biết, kèm chính sách mục đích sử dụng, thời hạn và trạng thái khóa nếu hệ thống hỗ trợ.
- Khi xoay khóa, khóa mới được ủy quyền bằng khóa/metadata đang tin cậy hoặc qua quy trình phục hồi được kiểm soát. Không tự động tin khóa mới chỉ vì nó nằm cùng tệp tải về.

Khóa riêng dùng để ký cần được giới hạn quyền truy cập, bảo vệ bằng HSM hoặc cơ chế tương đương nếu phù hợp, có quy trình phê duyệt phát hành và nhật ký kiểm toán. Thiết bị nhận bản cập nhật chỉ cần **khóa công khai** để xác minh; tuyệt đối không phân phối khóa riêng cùng firmware.

### 4.2. Cập nhật đã ký và Secure Boot

**Signed update** kiểm tra tính hợp lệ của bản cập nhật tại thời điểm nhận/cài. **Secure Boot** xác minh các thành phần trong chuỗi khởi động, ví dụ ROM tin cậy → bootloader → kernel → firmware/system image, trước khi chuyển quyền thực thi. Hai cơ chế bổ trợ nhau:

1. Bộ nạp ban đầu dựa trên gốc tin cậy không dễ bị thay đổi.
2. Mỗi giai đoạn chỉ tải thành phần tiếp theo nếu đáp ứng chính sách chữ ký hoặc đo lường tin cậy.
3. Firmware được cài vào vùng lưu trữ và có thể được xác minh lại trong quá trình khởi động.
4. Nếu xác minh thất bại, thiết bị chuyển sang chế độ cứu hộ được bảo vệ hoặc từ chối khởi động thành phần không tin cậy.

Không phải thiết bị nào cũng hỗ trợ Secure Boot, và tên tính năng có thể khác nhau. Cần kiểm tra khả năng thực tế của từng model trong tài liệu nhà sản xuất.

### 4.3. Chống hạ cấp phiên bản

Một bản firmware cũ vẫn có thể mang **chữ ký hợp lệ** nhưng chứa lỗ hổng đã được vá. Chống rollback bảo đảm thiết bị không chấp nhận image có chỉ số bảo mật thấp hơn mức đã được ghi nhận, ngoại trừ quy trình phục hồi được kiểm soát.

Các cách triển khai gồm **security version/rollback index**, bộ đếm tăng đơn điệu lưu trong phần cứng, hoặc metadata phiên bản có chữ ký và chính sách không cho phép quay về bản cũ. Cần phân biệt phiên bản hiển thị của sản phẩm với *security version*: một số nhà cung cấp cho phép quay lại bản chức năng cũ nhưng không được hạ thấp mức bảo mật tối thiểu.

**Lưu ý vận hành:** cơ chế chống rollback có thể khiến bản backup firmware cũ không còn khởi động được. Phải kiểm tra chính sách này **trước khi** lên kế hoạch rollback hoặc chuyển đổi giữa hai phân vùng A/B.

## 5. Kiểm tra nguồn bản cập nhật

Nguồn tải hợp lệ là một mắt xích độc lập với chữ ký. Trong mạng doanh nghiệp, cần có danh sách kênh được phép và quy trình phê duyệt bản phát hành.

1. **Bắt đầu từ cổng hỗ trợ chính thức** của hãng, hệ thống cập nhật tích hợp trong thiết bị hoặc kênh đối tác được hãng xác nhận. Không dựa vào tên file, logo, quảng cáo tìm kiếm hoặc đường link trong email để kết luận nguồn hợp lệ.
2. **Đối chiếu domain và kết nối TLS**: kiểm tra đúng tên miền, không bỏ qua lỗi chứng chỉ, không thay đổi cài đặt tin cậy chỉ để tải được. CDN hoặc mirror có thể được phép, nhưng phải được nhà sản xuất chỉ định; HTTPS chỉ là một lớp kiểm soát.
3. **Đối chiếu advisory, release notes và mã sản phẩm**: model, revision, vùng địa lý, bootloader tối thiểu, đường nâng cấp hỗ trợ, tính tương thích HA/cluster, giấy phép và trạng thái còn hỗ trợ (EOL/EOS).
4. **Lấy chữ ký và metadata theo hướng dẫn chính thức**: dùng khóa công khai/chứng chỉ đã được xác thực trước; xác minh chữ ký và hash trước khi cho phép image được cài.
5. **Kiểm tra tính mới và chính sách**: phiên bản đã phê duyệt, thông tin về bản bị thu hồi, thời hạn metadata nếu có, chống rollback và yêu cầu cập nhật theo từng bước.
6. **Ghi nhận bằng chứng**: URL nguồn, thời điểm tải, mã image, hash đã tính, kết quả kiểm tra chữ ký, phiên bản đích, thiết bị đích và người phê duyệt.

Đối với thiết bị chỉ có giao diện cập nhật tự động, cần xác định nó **tự kiểm tra chữ ký hay chỉ kiểm tra TLS/checksum**. Đừng ghi trong biên bản rằng “đã xác minh chữ ký” khi tài liệu thiết bị hoặc log không cho biết điều đó. Nếu hãng không cung cấp chữ ký/khả năng xác minh độc lập, hãy áp dụng kiểm soát bù trừ (kênh chính thức, quyền truy cập giới hạn, staging, hash từ kênh đáng tin, backup) và ghi rõ giới hạn xác thực nguồn.

## 6. Thực hành trong phòng lab: kiểm tra manifest có chữ ký

Ví dụ sau mô phỏng phương án **ký tệp SHA256SUMS** chứa digest của firmware. Dùng OpenSSL và công cụ sha256sum trên hệ thống có sẵn các lệnh đó. Tệp mẫu là nội dung thử nghiệm, không phải firmware có thể flash lên thiết bị thật.

~~~bash
# 1. Tạo tệp giả lập và danh sách hash
printf 'firmware-lab-v1\n' > firmware-lab.bin
sha256sum firmware-lab.bin > SHA256SUMS

# 2. Phía nhà phát hành (lab): tạo cặp khóa và ký danh sách hash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out lab-signing-private.pem
openssl pkey -in lab-signing-private.pem -pubout \
  -out lab-signing-public.pem
openssl dgst -sha256 -sign lab-signing-private.pem \
  -out SHA256SUMS.sig SHA256SUMS

# 3. Phía nhận: xác minh chữ ký bằng khóa công khai đã tin cậy
openssl dgst -sha256 -verify lab-signing-public.pem \
  -signature SHA256SUMS.sig SHA256SUMS

# 4. Chỉ sau khi chữ ký hợp lệ, xác minh nội dung tệp firmware
sha256sum -c SHA256SUMS
~~~

Khi mọi thứ hợp lệ, lệnh xác minh chữ ký thường in **Verified OK**, và lệnh kiểm tra digest in **firmware-lab.bin: OK**. Thử sửa một byte trong tệp firmware rồi chạy lại bước 4: kiểm tra hash sẽ thất bại. Thử sửa nội dung SHA256SUMS rồi chạy lại bước 3: chữ ký sẽ thất bại.

**Điều kiện quan trọng:** khóa công khai được tạo tại bước 2 chỉ được tin cậy **trong lab này**. Trong thực tế, người nhận phải có khóa/chứng chỉ của nhà cung cấp đã xác thực qua một gốc tin cậy độc lập. Nhận file khóa công khai từ chính máy chủ đáng ngờ rồi xác minh tệp do máy chủ đó cung cấp không tạo ra bằng chứng về tính chính hãng. Lab dùng RSA/SHA-256 để minh họa; hệ thống thực tế cần tuân thủ thuật toán và định dạng chữ ký do hãng hỗ trợ, ưu tiên bộ thuật toán hiện đại với chính sách khóa phù hợp.

Quy trình của hệ thống triển khai còn phải kiểm tra **model, hardware revision, version, chính sách chống rollback và nguồn phát hành**. Ví dụ lab chỉ minh họa tính liên kết giữa chữ ký và hash, chưa cung cấp cơ chế đó.

### 6.1. Quy tắc khi chạy công cụ kiểm tra

- Luôn kiểm tra **exit code** của lệnh, không chỉ dò một chuỗi trong output; ngừng quy trình khi chữ ký hoặc hash sai.
- Tính hash trên **đúng tệp sẽ được cài đặt**. Nếu tệp đã được sao chép sang kho triển khai, xác minh lại tại điểm nhận/điểm triển khai khi cần.
- Không tự tạo lại SHA256SUMS từ file vừa tải rồi coi đó là đối chiếu độc lập; giá trị tham chiếu phải nằm trong metadata đã được xác thực.
- Không tin chuỗi MD5/SHA-1 làm bằng chứng bảo mật hiện đại khi cơ chế SHA-256 hoặc chữ ký mạnh hơn có sẵn.
- Nếu dùng công cụ tự động đọc manifest, phải giới hạn đường dẫn, tên tệp, kích thước và quyền ghi; dữ liệu trong manifest vẫn là đầu vào cần xử lý an toàn.
- Không suy diễn “Verified OK” thành “firmware không có mã độc”: phép kiểm tra chỉ xác nhận sự phù hợp với khóa và nội dung đã ký.

## 7. Quy trình cập nhật an toàn cho hạ tầng mạng

### Giai đoạn A — Chuẩn bị và đánh giá

1. **Lập danh sách mục tiêu:** tên thiết bị, role, model, hardware revision, serial/asset ID, phiên bản đang chạy, phân vùng khởi động, vị trí và mức độ quan trọng.
2. **Xác định lý do cập nhật:** lỗ hổng cần vá, bản khuyến nghị từ hãng, tương thích với controller hoặc yêu cầu kỹ thuật đã được kiểm chứng. Đọc release notes, advisory và các lỗi đã biết.
3. **Kiểm tra đường nâng cấp:** có yêu cầu bản trung gian hay bootloader mới không, tính tương thích với cấu hình VPN, routing, ACL, HA, stack và license ra sao.
4. **Xác định nguồn chính thức và bằng chứng xác thực:** URL/kênh được phê duyệt, chứng chỉ hoặc public key tin cậy, chữ ký/manifest, hash, model và version dự kiến.
5. **Lập kế hoạch khôi phục:** backup cấu hình và dữ liệu quan trọng; xác minh có thể khôi phục backup. Kiểm tra HA/failover, nguồn điện, flash trống, kênh quản trị ngoài băng và mức rollback được Secure Boot cho phép.

### Giai đoạn B — Nhận và kiểm tra gói

6. **Tải từ nguồn được phép:** ưu tiên công cụ/hệ thống quản trị có hỗ trợ xác minh image; chặn việc dùng firmware tự tìm kiếm hoặc đính kèm không rõ nguồn.
7. **Xác thực trước khi triển khai:** kiểm tra chain/khóa công khai tin cậy, chữ ký, hash, model/revision, kênh phát hành, thông tin thu hồi và chống rollback. Thất bại bất kỳ bước bắt buộc nào thì dừng.
8. **Ghi bằng chứng:** lưu hash, kết quả xác minh và bản phát hành cùng ticket thay đổi; hạn chế quyền truy cập kho image và theo dõi thay đổi nội dung.

### Giai đoạn C — Triển khai và theo dõi

9. **Thử trên thiết bị đại diện:** staging hoặc một nhóm canary có cùng revision/role, kiểm tra kết nối quản trị, routing, VPN, DHCP/DNS, wireless và chính sách firewall.
10. **Triển khai có kiểm soát:** trong cửa sổ bảo trì, bảo đảm điện và đường quản trị ổn định. Với HA/cluster, tuân thủ thứ tự cập nhật và tương thích phiên bản do hãng quy định.
11. **Xác nhận sau khi reboot:** firmware đang chạy đúng phiên bản đích; không có lỗi xác minh boot, lỗi filesystem hoặc crash; dịch vụ và chính sách hoạt động như baseline.
12. **Đóng thay đổi và giám sát:** ghi lại kết quả, sự kiện bảo mật, hiệu suất, cấu hình, trạng thái HA và kế hoạch xử lý khi phát hiện lỗi muộn.

Một lần nâng cấp được coi là thành công khi **image được xác thực, thiết bị khởi động tin cậy và các dịch vụ mạng thực tế hoạt động đúng**. “Thiết bị đã reboot” hoặc “màn hình báo phiên bản mới” chưa đủ để xác nhận triển khai.

## 8. Xử lý khi xác minh thất bại

| Dấu hiệu | Khả năng nguyên nhân | Hành động phù hợp |
| --- | --- | --- |
| Chữ ký không hợp lệ | File hoặc manifest bị sửa, tải lỗi, dùng sai khóa hoặc định dạng | Dừng triển khai; giữ bản gốc, kiểm tra nguồn và khóa tin cậy; tải lại qua kênh được xác nhận |
| Hash không khớp dù manifest hợp lệ | Tệp firmware bị hỏng, bị thay hoặc nhận nhầm phiên bản | Không flash; kiểm tra file đích và kho phân phối; điều tra đường chuyển file |
| Chữ ký hợp lệ nhưng sai model/revision | Nhận nhầm image hoặc thiếu ràng buộc thiết bị | Từ chối; chọn đúng gói tương thích và kiểm tra lại metadata |
| Chữ ký hợp lệ nhưng firmware quá cũ | Downgrade/replay hoặc áp dụng bản không được phê duyệt | Kiểm tra anti-rollback, advisory và phiên bản tối thiểu; không hạ cấp tùy tiện |
| Không kiểm tra được chuỗi chứng chỉ/khóa | Khóa chưa tin cậy, key rotation, chứng chỉ hết hạn hoặc sự cố chính sách | Xác minh thông báo chính thức của hãng; dùng quy trình cập nhật trust anchor được phê duyệt |
| Tệp được quảng cáo trên domain lạ | Phishing, mirror ngoài danh sách, chuyển hướng không được phép | Không sử dụng; kiểm tra lại kênh chính thức và báo nhóm bảo mật |
| Thiết bị không boot sau nâng cấp | Sự cố tương thích, nguồn, bootloader hoặc image hỏng | Kích hoạt recovery theo hướng dẫn hãng, dùng image cứu hộ được xác thực, bảo toàn log phục vụ điều tra |

**Không khắc phục lỗi bằng cách tắt kiểm tra chữ ký, bỏ qua lỗi TLS hoặc hạ thấp chính sách Secure Boot.** Nếu cần chế độ cứu hộ, phải dùng đường recovery được nhà sản xuất hỗ trợ với kiểm soát truy cập vật lý/quản trị phù hợp.

Khi nghi ngờ bị chèn firmware độc hại hoặc khóa ký bị lộ: tạm dừng cập nhật trong phạm vi ảnh hưởng, cô lập nguồn phân phối đáng ngờ, lưu bằng chứng (image, manifest, hash, chữ ký, log, URL, thời gian), đối chiếu advisory của hãng và kích hoạt quy trình ứng cứu sự cố. Một chữ ký “hợp lệ” từ **khóa đã bị xâm phạm** không còn là bằng chứng đủ để tin tưởng bản cập nhật.

## 9. Mô hình bảo vệ nâng cao trong hệ thống cập nhật

Ở môi trường có nhiều thiết bị, bản cập nhật đi qua nhiều lớp: hãng → máy chủ phân phối → kho doanh nghiệp → bộ điều phối → thiết bị. Việc có một file ký hợp lệ chưa tự giải quyết được mọi rủi ro như replay, metadata hết hạn, thay đổi danh sách bản phát hành hay khóa ký bị lộ.

- **The Update Framework (TUF)** đưa ra mô hình metadata được ký, phân tách vai trò tin cậy (ví dụ root, targets, snapshot, timestamp), kiểm soát phiên bản và thời hạn để giảm rủi ro tấn công kho cập nhật. Các trường và cơ chế thực tế phụ thuộc triển khai; đây là mô hình tham khảo, không mặc nhiên có trên mọi thiết bị.
- **Uptane** mở rộng các nguyên tắc bảo vệ cập nhật cho hệ thống có nhiều thiết bị/ECU, phân biệt metadata từ bên phát hành image và bên điều phối cho thiết bị đích. Đây là ví dụ hữu ích về ràng buộc bản cập nhật với đúng thiết bị trong một đội hình lớn.
- **Phân quyền ký:** khóa gốc được bảo vệ chặt; khóa ký phát hành và khóa metadata hoạt động có phạm vi, thời hạn và khả năng thu hồi được xác định.
- **Ngăn phát lại/đóng băng cập nhật (replay/freeze):** chính sách về metadata mới, version, thời hạn và thời gian tin cậy giúp phát hiện khi máy chủ liên tục trả về metadata cũ hợp lệ. Thiết bị không có đồng hồ tin cậy phải có cơ chế phù hợp để kiểm soát tính mới.
- **A/B partitions và phục hồi:** phân vùng dự phòng có thể giảm thời gian gián đoạn khi cập nhật lỗi, nhưng image dự phòng vẫn cần được xác minh và tuân thủ chính sách anti-rollback.

TUF/Uptane không phải tên tính năng có thể bật tùy ý trên mọi thiết bị: chỉ áp dụng khi sản phẩm hay hệ thống phân phối thực sự hỗ trợ hoặc khi tổ chức tự xây dựng pipeline cập nhật theo chuẩn tương ứng.

## 10. Tình huống vận hành

### Tình huống 1: Bản firmware tải qua HTTPS có hash khớp

Một quản trị viên tải firmware từ trang có giao diện giống hãng. Trang này có HTTPS và cung cấp cả giá trị SHA-256; kết quả tính hash khớp. Tuy nhiên, domain không thuộc danh sách nguồn được hãng xác nhận và không có chữ ký có thể kiểm tra bằng khóa tin cậy.

**Đánh giá:** HTTPS và hash khớp chưa chứng minh được firmware chính hãng. **Quyết định:** không triển khai; truy ngược kênh phát hành chính thức và xác minh chữ ký/nguồn.

### Tình huống 2: Firewall chấp nhận chữ ký của firmware cũ

Một image của hãng có chữ ký hợp lệ nhưng thấp hơn security version hiện tại, chứa lỗ hổng cho phép truy cập quản trị trái phép.

**Đánh giá:** chữ ký kiểm tra nguồn và tính toàn vẹn, nhưng không loại bỏ lỗ hổng của bản cũ. **Quyết định:** áp dụng chính sách anti-rollback, không hạ cấp; nếu cần phục hồi, dùng image hoặc cách khôi phục được hãng hỗ trợ.

### Tình huống 3: Cập nhật thiết bị HA có chữ ký hợp lệ

Hai firewall HA nhận đúng image đã ký. Tuy nhiên, release notes yêu cầu nâng cấp bootloader theo thứ tự và chỉ cho phép cặp phiên bản nhất định cùng hoạt động.

**Đánh giá:** chữ ký đúng không bảo đảm quá trình cập nhật không làm đứt dịch vụ. **Quyết định:** theo đúng upgrade path, kiểm tra tính tương thích HA, kế hoạch failover, backup và maintenance window.

### Tình huống 4: Kho phân phối nội bộ bị sửa

Kho update nội bộ báo có bản vá mới, nhưng checksum của image không khớp với digest trong manifest đã được hãng ký.

**Đánh giá:** nội dung đã thay đổi sau khi ký hoặc bị chuyển nhầm tệp. **Quyết định:** chặn phát hành xuống toàn bộ thiết bị, bảo toàn chứng cứ, rà soát quyền ghi và audit log kho, chỉ cấp phát lại gói được xác minh thành công.

## 11. Checklist dùng trong phiếu thay đổi

| Kiểm tra | Bằng chứng nên lưu | Đạt khi |
| --- | --- | --- |
| Nguồn cập nhật | URL/kênh của hãng hoặc đối tác được chỉ định | Nguồn được xác nhận chính thức |
| Phạm vi thiết bị | Model, revision, serial/asset và firmware hiện tại | Image phù hợp chính xác thiết bị đích |
| Khóa ký | Fingerprint/ID và cách thiết lập trust anchor | Khóa thuộc bên phát hành được ủy quyền |
| Chữ ký và hash | Log công cụ xác minh, digest gói nhận được | Chữ ký hợp lệ, digest khớp |
| Chính sách phiên bản | Release notes, đường nâng cấp và rollback index | Không vi phạm anti-rollback hoặc dependency |
| Bảo đảm vận hành | Backup được kiểm chứng, kế hoạch HA và recovery | Có thể khôi phục theo đường hỗ trợ |
| Kết quả sau nâng cấp | Version, boot log, kiểm tra các dịch vụ chính | Boot tin cậy và dịch vụ đạt baseline |
| Truy vết | Ticket, phê duyệt, người triển khai và thời điểm | Có đủ dữ liệu điều tra khi xảy ra sự cố |

## 12. Ghi nhớ và tự kiểm tra

Ba nguyên tắc thực hành:

1. **Tin gốc trước, kiểm tra chữ ký sau:** khóa/chứng chỉ dùng để xác minh phải có nguồn tin cậy độc lập; khóa do nguồn đáng ngờ vừa cung cấp không đủ.
2. **Kiểm tra toàn bộ điều kiện trước khi flash:** chữ ký, digest, model/revision, kênh, phiên bản, anti-rollback, upgrade path và khả năng khôi phục đều cần đạt.
3. **Bảo vệ trọn vòng đời:** bảo vệ tài khoản quản trị, kho firmware, tiến trình phân phối, Secure Boot, log và bước kiểm thử sau cập nhật.

Tự trả lời: (a) Vì sao hash công bố cùng gói tải không đủ xác thực nguồn? (b) Vì sao firmware có chữ ký hợp lệ vẫn có thể nguy hiểm? (c) Hệ thống nên làm gì khi signature hợp lệ nhưng security version quá thấp? (d) Bằng chứng nào cho thấy bản cập nhật đã triển khai thành công và dịch vụ mạng hoạt động bình thường?

**Kết luận kỹ thuật:** firmware signing tạo bằng chứng mật mã về nguồn phát hành theo khóa tin cậy và sự toàn vẹn của nội dung đã ký. Để hardening thiết bị mạng hiệu quả, cần kết hợp nó với kiểm tra nguồn cập nhật, chính sách tương thích và phiên bản, Secure Boot/chống rollback khi được hỗ trợ, kiểm soát quản trị và quy trình vận hành có thể kiểm chứng.

