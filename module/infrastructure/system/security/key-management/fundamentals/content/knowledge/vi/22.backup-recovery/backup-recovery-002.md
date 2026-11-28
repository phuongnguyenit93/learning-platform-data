# Khi nào cần backup key

Trong quản lý khóa mật mã, **backup key** là việc tạo và bảo vệ một bản sao có thể khôi phục của khóa, hoặc thiết lập một cơ chế khôi phục tương đương được hệ thống KMS/HSM hỗ trợ. Mục tiêu là giữ khả năng giải mã dữ liệu, tiếp tục vận hành dịch vụ và duy trì danh tính mật mã khi khóa gốc bị mất, thiết bị hỏng, tài khoản bị xóa nhầm hoặc một vùng hạ tầng gặp sự cố.

Không phải khóa nào cũng cần sao lưu. Một khóa chỉ nên được backup khi việc mất khóa gây hậu quả đáng kể và tổ chức cần giữ lại chính khóa đó để khôi phục dữ liệu, danh tính hoặc hoạt động tin cậy. Nếu có thể tạo khóa mới và cấp lại chứng thư mà không ảnh hưởng dữ liệu hay nghiệp vụ, backup khóa cũ có thể không cần thiết. Mỗi bản sao cũng làm tăng số nơi chứa bí mật, vì vậy quyết định backup phải đi cùng kế hoạch bảo vệ và kiểm soát việc khôi phục.

Bài học này thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, tập trung vào vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy. Các quyết định backup cần xét đồng thời mật mã đối xứng, mật mã bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, quyền truy cập và kiểm toán.

## 1. Vì sao cần backup key

Mất khóa có thể gây ra hậu quả khác với mất một máy chủ thông thường. Nếu dữ liệu đã được mã hóa bằng một khóa ngẫu nhiên mạnh và không còn bản sao hoặc cơ chế khôi phục của khóa đó, tổ chức thường không thể suy ra lại khóa từ ciphertext. Dữ liệu vẫn còn nguyên trên đĩa hoặc trong bản backup, nhưng không thể đọc được.

Backup key thường cần thiết để xử lý các tình huống sau:

- **Mất khả năng giải mã dữ liệu:** khóa mã hóa dữ liệu hoặc khóa mã hóa khóa (KEK) bị xóa, hỏng hay không thể truy cập. Điều này có thể khiến dữ liệu giao dịch, hồ sơ khách hàng hoặc bản backup dài hạn không thể phục hồi.
- **Hỏng hoặc mất thiết bị mật mã:** HSM, thiết bị lưu trữ khóa, máy chủ KMS tự quản hoặc phương tiện lưu khóa bị hỏng, thất lạc hay không còn tương thích.
- **Sự cố hạ tầng hoặc tài khoản:** vùng cloud ngừng hoạt động, tài khoản quản trị bị khóa, cấu hình KMS bị xóa nhầm hoặc tổ chức phải chuyển nhà cung cấp.
- **Duy trì danh tính và chuỗi tin cậy:** khóa riêng của CA gốc hoặc CA trung gian cần được khôi phục để tiếp tục phát hành chứng thư theo cùng chuỗi tin cậy. Khóa ký quan trọng cũng có thể cần được giữ để tiếp tục ký bằng cùng danh tính.
- **Truy cập dữ liệu lưu trữ lâu dài:** dữ liệu cũ có thể vẫn cần được giải mã nhiều năm sau khi khóa đã ngừng dùng để mã hóa dữ liệu mới. Vì vậy, cần giữ lại các phiên bản khóa còn liên quan đến ciphertext đang được lưu giữ.

Backup dữ liệu và backup key phải được xem là hai phần của cùng kế hoạch khôi phục. Có bản backup cơ sở dữ liệu mà không còn khóa giải mã thì dữ liệu không thể sử dụng. Ngược lại, giữ được khóa nhưng không còn ciphertext hoặc bản backup dữ liệu cũng không giúp khôi phục nội dung.

## 2. Xác định loại khóa nào cần backup

Hãy bắt đầu bằng cách hỏi: **Nếu khóa này biến mất ngay bây giờ, hệ thống hoặc dữ liệu nào sẽ không thể khôi phục?** Sau đó xác định liệu khóa có thể được tạo lại, cấp lại hoặc thay thế mà không làm mất quyền truy cập vào dữ liệu hiện có hay không.

| Loại khóa | Nhu cầu backup thường gặp | Lý do và lưu ý |
|---|---|---|
| KEK, master key hoặc wrapping key | Cao nếu khóa bảo vệ các DEK đang dùng | Mất khóa này có thể khiến toàn bộ DEK đã được bọc không thể giải mã. Phải bảo đảm có bản backup, replica hoặc cơ chế recovery được hỗ trợ. |
| Data Encryption Key (DEK) | Phụ thuộc cách triển khai | Với envelope encryption, ciphertext và DEK đã mã hóa thường được lưu cùng nhau; cần giữ KEK có thể mở DEK. Nếu DEK không được lưu dưới dạng đã bọc hoặc không thể tái tạo, cần cơ chế backup riêng. |
| Khóa riêng CA gốc hoặc CA trung gian | Thường rất cao | Mất khóa có thể làm gián đoạn việc phát hành chứng thư theo danh tính CA hiện tại. Bản backup phải được bảo vệ bằng quy trình nhiều người kiểm soát. |
| Khóa ký mã nguồn, phần mềm hoặc tài liệu | Tùy yêu cầu duy trì danh tính | Backup có thể cần thiết nếu phải tiếp tục ký bằng cùng khóa. Khả năng xác minh chữ ký cũ chủ yếu dựa vào khóa công khai và chứng thư tương ứng, nên phải lưu giữ cả dữ liệu xác minh. |
| Khóa riêng TLS của dịch vụ | Thường có thể cấp lại; có ngoại lệ | Nếu có thể tạo cặp khóa mới và xin chứng thư mới, backup khóa cũ có thể không cần. Cần cân nhắc backup khi hệ thống pin khóa công khai, phụ thuộc danh tính khóa ổn định hoặc có yêu cầu liên tục đặc biệt. |
| Khóa phiên, khóa tạm thời hoặc khóa dùng một lần | Thường không | Các khóa này có thời hạn ngắn và không nên được phục hồi để tiếp tục sử dụng. Hãy tạo khóa mới khi thiết lập phiên hoặc tác vụ mới. |
| Khóa công khai | Không cần bảo mật như khóa riêng | Khóa công khai có thể được phân phối lại từ chứng thư hoặc kho tin cậy. Tuy vậy, cần bảo toàn tính toàn vẹn, chứng thư, chuỗi CA và thông tin định danh cần cho xác minh. |
| Khóa dẫn xuất | Thường backup vật liệu gốc và tham số dẫn xuất | Nếu có thể tái tạo an toàn, lưu khóa gốc, phiên bản thuật toán, context và tham số cần thiết. Không giả định có thể tái tạo nếu thiếu bất kỳ đầu vào nào. |

Đặc biệt, trong mô hình **envelope encryption**, dữ liệu được mã hóa bằng DEK; sau đó DEK được mã hóa bằng KEK do KMS/HSM quản lý. Ứng dụng lưu ciphertext cùng DEK đã được mã hóa. Khi khôi phục dữ liệu, hệ thống cần lấy được đúng phiên bản KEK để mở DEK, rồi dùng DEK giải mã ciphertext.

~~~mermaid
flowchart TD
    A["Bản backup dữ liệu"] --> B["Ciphertext và DEK đã mã hóa"]
    B --> C["Cần đúng KEK và phiên bản khóa"]
    C --> D["KMS/HSM hoặc cơ chế recovery"]
    D --> E["Mở DEK"]
    E --> F["Giải mã dữ liệu"]
~~~

Trong ví dụ này, không nhất thiết phải xuất và lưu riêng từng DEK ở dạng rõ. Điều quan trọng là giữ được ciphertext, DEK đã bọc, định danh phiên bản và khả năng truy cập KEK tương ứng. Nếu KEK bị mất mà không có đường khôi phục, các DEK đã bọc có thể trở nên vô dụng.

## 3. Những thời điểm cần tạo hoặc cập nhật backup

Backup cần được thiết lập trước khi khóa trở thành điểm phụ thuộc không thể thay thế của hệ thống. Các thời điểm quan trọng gồm:

1. **Sau khi tạo hoặc nhập khóa và trước khi đưa vào sản xuất:** xác nhận phương án backup hoặc recovery hoạt động trước khi mã hóa dữ liệu quan trọng hay dùng khóa để thiết lập danh tính tin cậy.
2. **Khi tạo phiên bản khóa mới:** ghi nhận phiên bản và cập nhật bản backup hoặc replica theo cơ chế của KMS/HSM. Không để phiên bản mới trở thành điểm phụ thuộc duy nhất mà chưa có đường khôi phục.
3. **Trước khi xoay vòng, ngừng kích hoạt hoặc hủy khóa cũ:** kiểm tra xem ciphertext, bản backup, chữ ký hoặc tài liệu lưu trữ nào vẫn cần phiên bản cũ. Giữ khóa giải mã cũ trong suốt thời gian dữ liệu phụ thuộc vào nó còn phải được truy cập.
4. **Trước khi di chuyển hệ thống:** chuẩn bị khả năng khôi phục khi đổi cloud, tài khoản, vùng, HSM, nhà cung cấp hoặc thiết kế phân cấp khóa.
5. **Trước thay đổi có thể làm mất quyền truy cập:** ví dụ thay đổi cấu hình KMS, chính sách IAM, miền bảo mật HSM, thông tin quản trị hoặc quy trình lưu giữ vật liệu khóa.
6. **Trước khi ngừng dịch vụ hoặc đóng tài khoản:** xác định dữ liệu lưu trữ còn thời hạn giữ, nghĩa vụ kiểm toán và nhu cầu xác minh chữ ký trong tương lai.

Với khóa bất biến, không cần tạo thêm một bản sao vật liệu khóa chỉ vì đến lịch backup dữ liệu định kỳ. Thay vào đó, nên backup theo sự kiện khi có phiên bản hoặc thay đổi quan trọng, đồng thời kiểm tra định kỳ khả năng truy cập, tính toàn vẹn và quy trình khôi phục. Metadata, cấu hình và danh mục phụ thuộc có thể cần được sao lưu theo lịch vì chúng thay đổi thường xuyên hơn vật liệu khóa.

## 4. Backup những thông tin nào

Một bản sao chỉ chứa chuỗi byte của khóa có thể chưa đủ để khôi phục hệ thống. Cần bảo toàn thông tin giúp xác định đúng khóa và sử dụng nó đúng mục đích:

- **Vật liệu khóa hoặc cơ chế recovery:** lưu vật liệu khóa theo định dạng và phương thức được chính sách cho phép; nếu khóa không thể export, dùng tính năng backup, replication hoặc recovery được KMS/HSM hỗ trợ.
- **Định danh và phiên bản:** key ID, version, fingerprint hoặc thông tin nhận diện tương ứng. Ứng dụng phải biết ciphertext được bảo vệ bởi khóa nào và phiên bản nào.
- **Thuộc tính mật mã:** thuật toán, độ dài khóa, mục đích sử dụng, loại khóa, trạng thái và thời điểm tạo, kích hoạt, hết hạn hoặc thu hồi.
- **Quan hệ trong hệ phân cấp khóa:** khóa nào bọc khóa nào, vị trí lưu DEK đã mã hóa, KMS/HSM nào quản lý KEK và các phụ thuộc liên quan.
- **Thông tin xác minh:** chứng thư, chuỗi CA, khóa công khai, thông tin định danh và dữ liệu cần thiết để kiểm tra chữ ký hoặc xác thực nguồn gốc.
- **Cấu hình và quy trình khôi phục:** chính sách truy cập, vai trò custodians, yêu cầu phê duyệt, miền bảo mật HSM, hướng dẫn phục hồi và đầu mối chịu trách nhiệm.
- **Liên kết với dữ liệu:** vị trí ciphertext, bản backup dữ liệu, thời hạn lưu trữ và phiên bản khóa cần để giải mã.

Không ghi vật liệu khóa dạng rõ vào log, ticket, email, chat hoặc tài liệu vận hành thông thường. Nếu phải chuyển vật liệu khóa, sử dụng kênh và định dạng được phê duyệt, có kiểm soát danh tính, tính toàn vẹn và dấu vết kiểm toán.

## 5. Chọn phương án backup và recovery

Phương án phụ thuộc vào loại khóa, khả năng export, yêu cầu sẵn sàng và mô hình triển khai.

| Phương án | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Backup gốc của KMS/HSM | Dùng chức năng backup/restore do dịch vụ hoặc thiết bị hỗ trợ | Khi cần giữ khóa trong miền bảo mật được quản lý và nhà cung cấp có quy trình khôi phục phù hợp. |
| Replication giữa vùng hoặc thiết bị | Duy trì bản sao khóa ở một vùng hoặc HSM khác | Khi cần tiếp tục vận hành khi một vùng hoặc thiết bị gặp sự cố. Replica trực tuyến không thay thế hoàn toàn bản backup bất biến vì thao tác xóa hoặc lỗi có thể lan truyền. |
| Export khóa đã được bọc | Xuất vật liệu khóa dưới dạng ciphertext, được bảo vệ bởi khóa backup độc lập | Khi chính sách cho phép export và hệ thống có thể quản lý an toàn khóa dùng để mở bản backup. |
| Backup offline hoặc phương tiện tách biệt | Lưu bản backup trong môi trường tách khỏi hệ thống vận hành | Khi cần chống lại sự cố diện rộng, xâm nhập hoặc thao tác phá hoại lan qua hệ thống trực tuyến. |
| Escrow khóa | Gửi bản sao hoặc cơ chế khôi phục cho bên lưu giữ được ủy quyền | Khi có yêu cầu nghiệp vụ, hợp đồng hoặc pháp lý về khả năng khôi phục có kiểm soát. Phải quy định rõ ai được yêu cầu và phê duyệt việc mở escrow. |

Ba khái niệm cần phân biệt:

- **Backup** tạo bản sao có thể dùng để phục hồi sau mất mát hoặc hỏng hóc.
- **Replication** duy trì bản sao để tăng tính sẵn sàng. Vì replication thường đồng bộ thao tác, nó có thể sao chép cả lỗi cấu hình hoặc thao tác xóa.
- **Escrow** xác lập một cơ chế lưu giữ và bàn giao có điều kiện, thường có thêm bên lưu giữ hoặc quy trình phê duyệt.

Nếu KMS/HSM đánh dấu khóa là **non-exportable**, không tìm cách vượt qua giới hạn bằng cách trích xuất vật liệu khóa. Hãy dùng chức năng backup, clone, replication hoặc disaster recovery chính thức của nền tảng, đồng thời kiểm tra các điều kiện về miền bảo mật, phiên bản thiết bị và quyền quản trị. Nếu nền tảng không hỗ trợ khôi phục khóa, phải tính giới hạn đó vào thiết kế dữ liệu và kế hoạch liên tục kinh doanh trước khi đưa khóa vào sử dụng.

## 6. Bảo vệ bản backup

Backup key vẫn là tài sản mật mã nhạy cảm. Một bản sao được bảo vệ yếu có thể trở thành con đường để kẻ tấn công lấy khóa và giải mã toàn bộ dữ liệu.

- **Mã hóa bằng khóa bảo vệ độc lập:** không dùng chính khóa đang được backup làm khóa duy nhất để mã hóa bản backup của nó. Thiết kế một đường tin cậy riêng để khôi phục khóa bảo vệ backup; nếu không, sự cố của khóa gốc có thể khiến cả bản backup không mở được.
- **Tách miền lỗi:** lưu bản backup ở tài khoản, vùng địa lý, thiết bị hoặc môi trường quản trị khác với hệ thống chính khi mức độ quan trọng yêu cầu. Tránh để cùng một tài khoản quản trị có thể xóa cả khóa đang hoạt động lẫn mọi bản backup.
- **Giới hạn quyền:** chỉ cấp quyền backup và restore cho vai trò cần thiết. Tách người quản trị hệ thống, người giữ khóa và người phê duyệt khôi phục khi phù hợp.
- **Kiểm soát nhiều người:** với khóa gốc hoặc khóa có ảnh hưởng lớn, dùng dual control hoặc cơ chế M-of-N để không một cá nhân nào có thể tự ý lấy lại và sử dụng khóa.
- **Bảo vệ tính toàn vẹn:** dùng checksum, chữ ký hoặc cơ chế kiểm tra toàn vẹn được phê duyệt; lưu dấu vết về thời điểm tạo, người thực hiện và vị trí bản backup.
- **Cách ly và chống sửa đổi:** cân nhắc phương tiện offline, immutable storage hoặc vùng lưu trữ có quyền xóa riêng biệt để giảm nguy cơ ransomware và thao tác phá hoại.
- **Quản lý vòng đời bản sao:** lập danh mục, phân loại, quy định thời hạn giữ, kiểm kê định kỳ và hủy an toàn bản backup hết hạn theo chính sách.

Quyền truy cập bản backup phải được kiểm toán giống quyền truy cập khóa đang hoạt động. Cần ghi nhận ai yêu cầu, ai phê duyệt, khóa hoặc phiên bản nào được khôi phục, thời điểm thực hiện và mục đích nghiệp vụ. Log không được chứa vật liệu khóa dạng rõ.

## 7. Kiểm thử khả năng khôi phục

Một bản backup chỉ có giá trị khi tổ chức có thể khôi phục và sử dụng nó. Việc thấy file tồn tại hoặc trạng thái backup thành công trong giao diện KMS chưa chứng minh rằng hệ thống có thể giải mã dữ liệu sau thảm họa.

Một bài kiểm thử recovery nên xác nhận:

1. Người có thẩm quyền có thể truy cập phương tiện hoặc dịch vụ backup theo đúng quy trình phê duyệt.
2. Bản backup còn nguyên vẹn và có đủ metadata để xác định khóa, thuật toán, mục đích và phiên bản.
3. KMS/HSM có thể khôi phục khóa hoặc thiết lập lại miền bảo mật theo hướng dẫn chính thức.
4. Ứng dụng có thể truy cập đúng khóa và giải mã một mẫu dữ liệu thử nghiệm; với khóa ký, có thể thực hiện thao tác ký thử và xác minh chữ ký bằng khóa công khai tương ứng.
5. Thời gian khôi phục đáp ứng mục tiêu RTO và mức mất dữ liệu chấp nhận được đáp ứng RPO đã thống nhất.
6. Toàn bộ quá trình có log kiểm toán và không làm lộ vật liệu khóa ra môi trường kiểm thử.

Nên thực hiện kiểm thử trong môi trường cô lập, dùng dữ liệu thử nghiệm và quy trình được phê duyệt. Kiểm thử lại sau khi thay đổi KMS/HSM, miền bảo mật, nhà cung cấp, chính sách truy cập hoặc quy trình lưu giữ. Tần suất định kỳ cần dựa trên mức độ quan trọng của khóa, tốc độ thay đổi hạ tầng và yêu cầu phục hồi.

Khi phục hồi dữ liệu đã mã hóa, thứ tự thường là khôi phục danh tính và quyền quản trị cần thiết, khôi phục hoặc truy cập KMS/HSM, mở khóa DEK, rồi mới giải mã dữ liệu. Kế hoạch phải ghi rõ các bước và người chịu trách nhiệm; nếu thiếu quyền quản trị hoặc thông tin cấu hình, bản backup khóa có thể vẫn không sử dụng được.

## 8. Phân biệt mất khóa với lộ khóa

Backup giải quyết vấn đề **khả dụng** khi khóa bị mất hoặc hỏng. Nó không giải quyết vấn đề **bí mật** khi khóa bị lộ.

Nếu khóa bị nghi ngờ xâm phạm, không tự động khôi phục bản backup của chính khóa đó rồi tiếp tục sử dụng. Bản backup chứa cùng vật liệu khóa nên cũng có thể đã bị lộ. Quy trình xử lý thường cần cô lập quyền truy cập, đánh giá phạm vi ảnh hưởng, thu hồi hoặc vô hiệu hóa khóa theo chính sách, tạo khóa thay thế, cập nhật hệ thống phụ thuộc và re-encrypt hoặc re-wrap dữ liệu khi cần. Việc giữ bản sao phục vụ điều tra phải tuân theo quy trình ứng phó sự cố và được cách ly có kiểm soát.

| Tình huống | Hướng xử lý chính |
|---|---|
| Khóa bị xóa nhầm, không có dấu hiệu lộ | Dùng bản backup hoặc cơ chế recovery đã kiểm thử; xác minh phiên bản và phạm vi dữ liệu phụ thuộc. |
| HSM hoặc một vùng bị hỏng | Chuyển sang replica hoặc khôi phục từ backup ở miền lỗi độc lập; kiểm tra tính toàn vẹn trước khi đưa vào sử dụng. |
| Khóa bị lộ hoặc nghi bị lộ | Thực hiện quy trình ứng phó sự cố, thu hồi/thay thế và đánh giá dữ liệu bị ảnh hưởng; không dùng bản backup cũ làm khóa hoạt động. |
| Khóa cũ đã ngừng mã hóa dữ liệu mới nhưng ciphertext vẫn còn | Giữ đường giải mã an toàn cho phiên bản cũ đến hết thời hạn lưu trữ và nghĩa vụ truy cập dữ liệu. |

## 9. Ví dụ thực tế

**Cơ sở dữ liệu dùng envelope encryption:** mỗi bản ghi hoặc lô dữ liệu được mã hóa bằng DEK. DEK được bọc bằng KEK trong KMS, còn ciphertext và DEK đã bọc nằm trong backup cơ sở dữ liệu. Khi thiết kế DR, nhóm vận hành phải bảo đảm có thể truy cập đúng KEK và phiên bản của nó từ vùng khôi phục. Chỉ backup cơ sở dữ liệu mà không có recovery path cho KEK sẽ không đủ.

**CA gốc lưu offline:** khóa riêng CA gốc có thể là nền tảng của chuỗi tin cậy nội bộ. Tổ chức cần một quy trình backup được kiểm soát chặt, có thể dùng HSM backup và phân chia quyền khôi phục cho nhiều custodians. Bản backup phải được cất giữ tách biệt, kiểm kê và kiểm thử theo quy trình; không đưa khóa gốc vào máy chủ phát hành chứng thư hoạt động hằng ngày.

**Chứng thư TLS cho dịch vụ web:** nếu khóa riêng bị mất nhưng tổ chức vẫn kiểm soát tên miền và có thể xin chứng thư mới, tạo cặp khóa mới rồi cấp lại chứng thư thường là phương án phù hợp. Backup khóa cũ chỉ cần thiết khi có ràng buộc như pinning, phụ thuộc danh tính khóa ổn định hoặc yêu cầu vận hành cụ thể. Việc giữ khóa cũ phải được cân nhắc với rủi ro tăng thêm do có nhiều bản sao khóa riêng.

**Khóa phiên của kết nối:** khóa phiên chỉ dùng trong thời gian ngắn và được tạo mới khi thiết lập phiên. Không cần backup để phục hồi phiên cũ; khi kết nối bị mất, hai bên thiết lập phiên mới và sinh khóa mới.

## 10. Checklist ra quyết định

Trước khi đưa một khóa vào kế hoạch backup, hãy trả lời các câu hỏi sau:

- Nếu mất khóa, dữ liệu, chữ ký, danh tính hoặc dịch vụ nào bị ảnh hưởng?
- Khóa có thể được tạo lại hoặc cấp lại mà vẫn truy cập được dữ liệu cũ không?
- Ciphertext, DEK đã bọc và phiên bản KEK có được liên kết rõ ràng không?
- Có dữ liệu lưu trữ hoặc chữ ký cũ còn phụ thuộc vào phiên bản khóa này không?
- KMS/HSM có hỗ trợ backup, restore hoặc replication chính thức cho loại khóa này không?
- Bản backup nằm ngoài miền lỗi của hệ thống chính và được bảo vệ bằng quyền truy cập phù hợp không?
- Có yêu cầu dual control, M-of-N, escrow, lưu giữ hoặc hủy theo chính sách không?
- Nhóm vận hành đã thực sự thử khôi phục và xác nhận thời gian phục hồi chưa?
- Nếu khóa bị lộ, quy trình thu hồi và thay thế có thể được thực hiện độc lập với quy trình backup không?

Chỉ đánh dấu phương án backup là sẵn sàng khi đã xác định được khóa và phiên bản cần giữ, nơi lưu, người được phép khôi phục, đường tin cậy để mở bản backup và kết quả kiểm thử recovery. Cách làm này giúp cân bằng tính sẵn sàng với yêu cầu bảo mật trong toàn bộ vòng đời khóa.
