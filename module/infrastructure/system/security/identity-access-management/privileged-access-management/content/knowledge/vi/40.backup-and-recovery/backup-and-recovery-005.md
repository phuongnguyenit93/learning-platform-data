# Offline recovery credential

## 1. Mục tiêu và tình huống cần giải quyết

Một nền tảng Privileged Access Management (PAM) có thể bảo vệ rất tốt tài khoản quản trị trong vận hành bình thường nhưng vẫn gây bế tắc khi chính nó không hoạt động. Mật khẩu quản trị hypervisor nằm trong vault; vault chạy trên máy ảo cần hypervisor để khởi động; tài khoản mở vault lại đăng nhập qua Identity Provider (IdP) đang lỗi. Bản sao lưu vẫn còn nhưng không ai có đường truy cập hợp lệ để bắt đầu khôi phục.

**Offline recovery credential** là thông tin hoặc phương tiện xác thực được chuẩn bị và bảo quản ngoại tuyến để hỗ trợ một đường khôi phục đã được phê duyệt khi cơ chế truy cập thông thường không sử dụng được. Đó có thể là mật khẩu tài khoản khôi phục cục bộ, khóa xác thực phần cứng, private key được bảo vệ hoặc một thành phần của cơ chế khôi phục khóa. Hình thức cụ thể phải phù hợp với hệ thống đích.

Trong chương Backup và khôi phục, bài này tập trung vào câu hỏi: **Làm thế nào lấy lại quyền truy cập cần thiết để phục hồi PAM mà vẫn kiểm soát được ai sử dụng quyền, sử dụng vào việc gì và khi nào kết thúc?**

Sau bài học, người học có thể:

- Phân biệt bản sao lưu dữ liệu, credential đăng nhập và vật liệu khôi phục khóa.
- Nhận diện vòng phụ thuộc khiến credential “dự phòng” không dùng được khi xảy ra sự cố.
- Thiết kế bộ recovery có phân quyền, người giữ, phiên bản và dấu vết bàn giao.
- Thực hiện quy trình kích hoạt, sử dụng, thay thế và tái niêm phong.
- Xác định tiêu chí kiểm thử chứng minh đường khôi phục thực sự hoạt động.

Một bộ credential đặt trong két nhưng chưa từng được kiểm thử chưa đủ để chứng minh khả năng phục hồi.

## 2. Hiểu đúng từ “offline”

### 2.1. Ngoại tuyến khi bảo quản khác với xác thực không cần mạng

Một mật khẩu được niêm phong trên giấy có thể được bảo quản hoàn toàn ngoại tuyến. Khi sử dụng, tài khoản tương ứng vẫn có thể cần kết nối tới dịch vụ đích.

Tương tự, một khóa bảo mật phần cứng được giữ trong két không biến dịch vụ cloud thành dịch vụ hoạt động khi nhà cung cấp ngừng phục vụ. Nó có thể loại bỏ phụ thuộc vào điện thoại hoặc ứng dụng xác thực thông thường, nhưng dịch vụ đích vẫn phải nhận và xử lý được yêu cầu đăng nhập.

Cần trả lời riêng hai câu:

1. Credential được lưu ở đâu và có thể lấy ra khi các dịch vụ thông thường hỏng không?
2. Hệ thống nào phải hoạt động để credential đó được chấp nhận?

Nếu câu thứ hai vẫn bao gồm đúng thành phần đang gặp sự cố thì thiết kế chưa đáp ứng kịch bản.

### 2.2. Những khái niệm dễ nhầm

| Thành phần | Vai trò | Điều không được suy diễn |
| --- | --- | --- |
| Bản sao lưu PAM | Phục hồi dữ liệu và cấu hình theo phạm vi sản phẩm | Có backup không có nghĩa đã có quyền truy cập kho backup hoặc có khóa giải mã |
| Recovery account | Danh tính được phép thực hiện tác vụ khôi phục | Tài khoản tồn tại không chứng minh credential hiện còn đúng hoặc quyền còn hiệu lực |
| Offline recovery credential | Phương tiện chứng minh quyền truy cập qua đường khôi phục | Được giữ ngoại tuyến không có nghĩa luôn xác thực được khi mất mạng |
| Khóa giải mã backup | Giải mã một bản sao lưu hoặc tập dữ liệu tương ứng | Khóa này không mặc nhiên là mật khẩu đăng nhập PAM |
| Vật liệu mở khóa hoặc khôi phục hệ thống quản lý khóa | Thực hiện chức năng theo cơ chế của sản phẩm | Mở khóa dữ liệu không tự động cấp một phiên quản trị |
| Runbook và manifest | Chỉ dẫn thao tác, nhận diện bộ recovery, kiểm soát phiên bản | Tài liệu chỉ dẫn không nên chứa secret trong bản được lưu hành rộng |

Một hệ thống có thể cần nhiều thành phần trong bảng. Không gom tất cả thành một “master password” tưởng tượng rồi coi đó là giải pháp chung.

### 2.3. Quan hệ với break-glass, JIT và JEA

Break-glass là quy trình sử dụng quyền khẩn cấp có điều kiện. Offline recovery credential là một thành phần có thể được quy trình đó sử dụng.

Trong vận hành bình thường, Just-in-Time (JIT) và Just Enough Administration (JEA) giúp giới hạn thời gian và phạm vi quyền. Tuy nhiên, đường cấp quyền JIT có thể phụ thuộc vào PAM hoặc IdP đang hỏng. Thiết kế recovery cần xác định trước cơ chế nào vẫn hoạt động trong tình huống đó.

Ngoại lệ khôi phục phải có mục đích, chủ sở hữu và kiểm soát bù đắp. Không tự động biến mọi tài khoản recovery thành tài khoản toàn quyền trên mọi hệ thống.

## 3. Thiết kế theo kịch bản hỏng và vòng phụ thuộc

### 3.1. Bắt đầu từ điều kiện mất dịch vụ

Trước khi chọn giấy niêm phong, thiết bị mã hóa hoặc khóa phần cứng, hãy mô tả sự cố cần chịu được.

| Kịch bản | Khả năng bị mất | Câu hỏi cần chứng minh |
| --- | --- | --- |
| PAM hoặc vault không hoạt động | Lấy secret, cấp quyền, proxy phiên | Có đường quản trị đích được phê duyệt mà không cần vault không? |
| IdP hoặc federation lỗi | SSO, một số phương thức xác thực | Tài khoản khôi phục có độc lập với IdP bị lỗi không? |
| Mạng quản trị gián đoạn | VPN, bastion, DNS, định tuyến | Người trực có đường console hoặc đường quản trị dự phòng thực sự dùng được không? |
| Mất trung tâm dữ liệu chính | Máy chủ, két tại chỗ, người trực tại cơ sở | Bản dự phòng, công cụ và người được phép có ở địa điểm khác không? |
| Sự cố xâm nhập | Độ tin cậy của tài khoản, máy trạm và log | Làm sao tránh nhập credential recovery vào thiết bị có thể bị kiểm soát? |
| KMS/HSM hoặc dịch vụ khóa lỗi | Giải mã backup hoặc mở dữ liệu | Có cơ chế recovery được sản phẩm hỗ trợ và đã kiểm thử không? |
| Dịch vụ cloud đích ngừng phục vụ | API, control plane, đăng nhập | Phần nào phải chờ nhà cung cấp và phần nào tổ chức còn có thể phục hồi? |

Credential chỉ giải quyết một phần của đường khôi phục. Nó không sửa được đứt cáp, mất nguồn hoặc dịch vụ xác thực đích hoàn toàn không hoạt động.

### 3.2. Minh họa một vòng phụ thuộc

~~~mermaid
flowchart LR
    A[Cần khởi động máy ảo PAM] --> B[Cần quản trị hypervisor]
    B --> C[Credential chỉ nằm trong PAM]
    C --> A
    D[Bộ recovery ngoại tuyến đã phê duyệt] --> E[Đường console và danh tính độc lập]
    E --> B
~~~

Mục tiêu của bộ recovery là tạo một điểm bắt đầu khả dụng để phá vòng này. Điểm bắt đầu vẫn phải có kiểm soát vật lý, kiểm soát danh tính và giới hạn sử dụng.

Khi phân tích, vẽ cả các phụ thuộc “nhỏ”:

- Số điện thoại người phê duyệt chỉ tra được trong danh bạ doanh nghiệp đang lỗi.
- Mã mở két được lưu trong cùng vault.
- Thiết bị đọc backup nằm tại địa điểm bị mất.
- Công cụ giải mã phải tải từ Internet trong khi cơ sở đang bị cô lập.
- Tài khoản cục bộ vẫn bị chính sách chặn đăng nhập qua đường console dự kiến.
- Máy trạm recovery không có chứng thư, driver hoặc cấu hình cần thiết.

Một bản runbook đọc được ngoại tuyến và danh sách liên hệ dự phòng có thể quan trọng không kém credential.

## 4. Lập danh mục recovery theo mục đích và ranh giới quyền

### 4.1. Chọn tập quyền tối thiểu để bắt đầu phục hồi

Không xuất toàn bộ vault thành một kho secret ngoại tuyến chỉ vì muốn “đủ mọi trường hợp”. Cách làm đó mở rộng đáng kể phạm vi lộ lọt và làm việc cập nhật rất khó kiểm soát.

Thay vào đó, xác định tập tài nguyên cần thiết cho đường khởi động phục hồi:

1. Đường truy cập quản trị độc lập hoặc console.
2. Hạ tầng chạy thành phần PAM cần phục hồi.
3. Kho backup và công cụ đọc bản sao lưu.
4. Khóa hoặc cơ chế giải mã cần thiết.
5. Danh tính quản trị phục hồi của chính sản phẩm PAM.
6. Các dịch vụ nền bắt buộc theo kiến trúc thực tế.

Thứ tự này là danh sách phân tích, không phải thứ tự khôi phục áp dụng cho mọi hệ thống. Quan hệ giữa database, dịch vụ khóa và ứng dụng phải theo tài liệu và kiểm thử của triển khai cụ thể.

### 4.2. Một bản ghi quản lý credential nên thể hiện gì?

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Recovery ID | Mã quản lý ổn định, không chứa secret |
| Hệ thống và môi trường | Đích chính xác; phân biệt production, dự phòng và lab |
| Mục đích | Tác vụ được phép, chẳng hạn khởi động hạ tầng hoặc khôi phục cấu hình |
| Danh tính liên quan | Tài khoản hoặc đối tượng xác thực tương ứng |
| Quyền được cấp | Phạm vi quyền và lý do cần thiết |
| Phụ thuộc còn lại | Mạng, console, IdP độc lập, thiết bị, dịch vụ khóa |
| Người chịu trách nhiệm | Chủ hệ thống và người quản lý vòng đời |
| Người giữ vật liệu | Những vai trò có trách nhiệm bảo quản, có người thay thế |
| Phiên bản bộ recovery | Dùng để phát hiện bộ cũ hoặc bản phân phối thiếu cập nhật |
| Bằng chứng kiểm thử | Lần kiểm thử, kịch bản, kết quả và vấn đề còn mở |
| Điều kiện thay thế | Sau sử dụng, nghi lộ, thay người giữ hoặc thay cấu hình có liên quan |

Danh mục vận hành có thể ghi mã két hoặc mã địa điểm theo phân loại nội bộ, nhưng không nên công khai toàn bộ thông tin giúp một người tìm và mở mọi bộ recovery.

Tài khoản dịch vụ thông thường không nên được tái sử dụng làm tài khoản recovery chỉ vì nó có sẵn quyền. Trộn hai mục đích sẽ làm phạm vi sử dụng, phụ thuộc ứng dụng và trách nhiệm truy vết trở nên khó xác định.

## 5. Bảo quản: bảo mật, khả dụng và khả năng quy trách nhiệm

### 5.1. Chọn hình thức theo loại credential

**Giấy niêm phong** có thể phù hợp với một mật khẩu hoặc mã khôi phục có thể nhập thủ công. Cần kiểm soát in ấn, bản nháp, máy in, người chứng kiến, phong bì và dấu hiệu mở. Giấy không phù hợp để chứa mọi loại dữ liệu nhị phân hoặc thay thế quy trình khôi phục khóa phức tạp.

**Vật mang tin được mã hóa** có thể chứa bundle cần công cụ đọc. Phải kiểm thử khả năng giải mã trên thiết bị recovery; kiểm soát phần mềm cần dùng, cổng kết nối, pin và tình trạng vật mang tin. Khóa mở vật mang tin không được phụ thuộc duy nhất vào hệ thống đang cần khôi phục.

**Thiết bị xác thực phần cứng** có thể bảo vệ khóa không cần xuất ra dạng plaintext. Cần chuẩn bị thiết bị dự phòng hoặc đường thay thế theo cơ chế hệ thống đích hỗ trợ. Một số khóa không thể sao chép; “backup thiết bị” không luôn đồng nghĩa sao chép cùng private key.

**Vật liệu khôi phục khóa theo ngưỡng** chỉ áp dụng khi cơ chế sản phẩm hoặc công cụ đã được phê duyệt hỗ trợ. Phải hiểu rõ vật liệu đó khôi phục chức năng nào và không nhầm với credential đăng nhập.

### 5.2. Dual control và split knowledge không giống nhau

Dual control yêu cầu nhiều người tham gia một hành động nhạy cảm, ví dụ hai người cùng xác nhận và mở bộ recovery.

Split knowledge phân chia kiến thức hoặc vật liệu bí mật để một người riêng lẻ không có đủ thông tin cần thiết. Nếu hệ thống hỗ trợ cơ chế theo ngưỡng, có thể thiết kế yêu cầu một số lượng tối thiểu trong tập người giữ.

Không cắt một mật khẩu thành hai nửa rồi mặc nhiên coi đó là cơ chế chia sẻ bí mật mật mã. Cách làm thủ công dễ gây lỗi ghép, giảm khả năng khôi phục khi mất người giữ và không có các thuộc tính bảo vệ như một cơ chế theo ngưỡng được thiết kế đúng.

Mô hình minh họa “cần hai trong ba người giữ” chỉ có ý nghĩa khi:

- Cơ chế thực tế hỗ trợ ngưỡng tương ứng hoặc quy trình dual control được xác định rõ.
- Mỗi người giữ thuộc phạm vi trách nhiệm phù hợp.
- Không có một người hoặc một dịch vụ nắm tất cả thành phần.
- Đã kiểm thử cả trường hợp một người không liên lạc được.
- Tổ chức có quy trình thay người giữ và thay vật liệu liên quan.

Đây là lựa chọn thiết kế của tổ chức, không phải ngưỡng bắt buộc chung cho mọi PAM.

### 5.3. Bản dự phòng phải chịu được sự cố chung

Hai phong bì đặt trong cùng một ngăn kéo không cung cấp khả năng chịu mất địa điểm. Hai bộ ở hai cơ sở cũng chưa độc lập nếu chỉ một người có quyền lấy cả hai hoặc mọi liên hệ đều phụ thuộc vào cùng hệ thống email.

Cần xem xét độc lập về địa điểm, người giữ, đường liên lạc, nguồn điện và đường tiếp cận. Đồng thời giới hạn số bản sao: mỗi bản thêm vào đều tạo thêm trách nhiệm kiểm kê, cập nhật và thu hồi.

Niêm phong chống mở giúp phát hiện một số dấu hiệu can thiệp; nó không chứng minh tuyệt đối rằng secret chưa bị sao chép. Nếu niêm phong bất thường hoặc vật liệu thất lạc, xử lý theo quy trình nghi lộ credential.

### 5.4. Không biến tài liệu bằng chứng thành nơi chứa secret

Biên bản bàn giao chỉ ghi mã bộ, người giao nhận, thời gian, trạng thái niêm phong và kết quả kiểm tra cần thiết. Không chụp ảnh nội dung credential để chứng minh đã giao.

Tránh ghi secret vào ticket, ứng dụng chat, command line, lịch sử shell, ảnh màn hình hoặc bản ghi phiên. Nếu công cụ ghi hình có thể ghi lại credential trong quá trình nhập, phải thiết kế cách bảo vệ phần nhập nhạy cảm được phê duyệt mà vẫn lưu được dấu vết hành động.

Không lưu hash trực tiếp của mật khẩu trong manifest như một cách “không lộ mật khẩu”. Hash của secret có thể hỗ trợ đoán ngoại tuyến, đặc biệt khi secret có entropy thấp. Theo dõi phiên bản và bằng chứng kiểm thử xác thực thay cho việc công bố fingerprint của mật khẩu.

## 6. Đóng gói bộ recovery và quản lý phiên bản

### 6.1. Tách chỉ dẫn vận hành khỏi vật liệu bí mật

Một bộ recovery có thể gồm ba lớp quản lý:

1. **Tài liệu điều phối:** điều kiện kích hoạt, người có thẩm quyền, liên hệ và tiêu chí kết thúc.
2. **Manifest kỹ thuật:** đích, mã bộ, phiên bản cấu hình liên quan, công cụ cần thiết và bằng chứng kiểm thử.
3. **Vật liệu bí mật:** credential, khóa hoặc thiết bị được bảo vệ theo cơ chế riêng.

Không nhất thiết ba lớp phải là ba file. Điều cần bảo đảm là người đọc runbook không tự động đọc được secret, còn người được phép sử dụng secret có đủ chỉ dẫn để không dùng sai đích.

Ví dụ manifest minh họa dưới đây chỉ chứa metadata, không phải schema bắt buộc của sản phẩm:

~~~yaml
recovery_id: PAM-REC-BOOTSTRAP-A
bundle_version: 7
environment: production
purpose: "Khởi động đường quản trị phục hồi hạ tầng PAM"
target: "hypervisor-management-console"
identity_reference: "local-recovery-account-A"
secret_location_reference: "SEALED-PACKAGE-A7"
approval_policy_reference: "RECOVERY-POLICY-01"
required_custodians: 2
dependencies:
  - "Console quản trị độc lập đã kiểm thử"
  - "Máy trạm recovery được kiểm soát"
permitted_actions:
  - "Kiểm tra tình trạng hạ tầng"
  - "Khởi động thành phần thuộc runbook phục hồi PAM"
last_test_reference: "DRILL-REC-042"
reissue_required_after:
  - "Sử dụng hoặc nghi lộ credential"
  - "Thay credential trên hệ thống đích"
  - "Thay đổi người giữ cần tái cấp vật liệu"
~~~

Các tên và mã trong ví dụ là dữ liệu giả. Không chèn secret thật vào mẫu này khi đưa vào kho tài liệu chung.

### 6.2. Có bản sao lưu chưa đủ nếu thiếu khả năng giải mã

Phải quản lý mối liên hệ giữa bản sao lưu, khóa tương ứng, phiên bản sản phẩm và công cụ phục hồi. Không phải mọi vật liệu khóa đều có thể export hoặc được phép sao lưu theo cùng cách.

Khi phục hồi dữ liệu đã mã hóa từ thời điểm cũ, khóa đang dùng hôm nay có thể không phải vật liệu cần thiết để giải mã dữ liệu đó. Ngược lại, không giữ mọi khóa lịch sử vô thời hạn mà không có chính sách: thời gian lưu phải gắn với dữ liệu còn cần phục hồi và giới hạn truy cập.

Với HSM/KMS hoặc cơ chế gắn khóa vào phần cứng, xác minh quy trình di chuyển, thay thiết bị, khôi phục backup và điều kiện của nhà cung cấp. Một file ghi “đã backup khóa” không chứng minh rằng môi trường đích có thể sử dụng được khóa đó.

### 6.3. Cập nhật phải là một quy trình có đối soát

Vòng đời một bộ recovery có thể mô tả như sau:

~~~mermaid
flowchart LR
    A[Chuẩn bị] --> B[Kiểm thử]
    B --> C[Niêm phong và lưu giữ]
    C --> D[Được phép kích hoạt]
    D --> E[Sử dụng có ghi nhận]
    E --> F[Thay thế và kiểm thử]
    F --> C
    C --> G[Thu hồi khi thay đổi]
    G --> A
~~~

Khi thay credential trên hệ thống đích, không chỉ cập nhật một bản trong kho lưu trữ. Phải kiểm kê mọi bản recovery được quản lý và mọi vị trí được phép lưu credential đó.

Đặc biệt chú ý giai đoạn chuyển đổi:

- Nếu thay trên đích trước nhưng đóng gói thất bại, bộ trong két có thể đã hết hiệu lực.
- Nếu đóng gói bản mới trước khi hệ thống đích chấp nhận, bộ mới chưa sử dụng được.
- Nếu loại bỏ bản cũ quá sớm trong khi bản mới chưa kiểm thử, có thể mất đường recovery duy nhất.

Runbook thay đổi cần có cửa sổ thực hiện, bằng chứng đích chấp nhận credential mới, đối soát bản phân phối và phương án phục hồi khi cập nhật dở dang. Cách chuyển đổi cụ thể phải tuân theo khả năng sản phẩm; không tự tạo nhiều credential hoạt động song song nếu hệ thống không hỗ trợ an toàn.

## 7. Quy trình kích hoạt và sử dụng trong sự cố

### 7.1. Bước 1 — Xác nhận nhu cầu và phạm vi

Người điều phối sự cố ghi nhận dịch vụ bị ảnh hưởng, đường truy cập thông thường đã thất bại và mục tiêu cần đạt bằng recovery.

Phân biệt hai tình huống:

- **Sự cố khả dụng:** hệ thống ngừng hoạt động nhưng chưa có bằng chứng bị xâm nhập.
- **Sự cố có nghi vấn xâm nhập:** danh tính, thiết bị hoặc cấu hình có thể không đáng tin.

Với tình huống thứ hai, sử dụng credential trên máy hoặc mạng nghi bị kiểm soát có thể làm lộ luôn đường phục hồi. Cần phối hợp quy trình ứng phó sự cố để chọn môi trường thao tác đáng tin và bảo toàn bằng chứng phù hợp.

### 7.2. Bước 2 — Phê duyệt bằng cơ chế còn hoạt động

Xác minh danh tính người yêu cầu và người phê duyệt qua kênh đã chuẩn bị. Không dựa duy nhất vào một tin nhắn “rất khẩn cấp” từ tài khoản email có thể bị chiếm.

Nếu hệ thống ticket ngừng hoạt động, sử dụng biểu mẫu hoặc sổ sự cố dự phòng với mã tạm duy nhất. Sau đó đồng bộ bằng chứng về hệ thống chính khi hoạt động trở lại.

Nếu không liên lạc được một người phê duyệt, áp dụng người thay thế hoặc nhánh xử lý đã được chính sách phê duyệt trước. Không tự bỏ yêu cầu nhiều người chỉ vì đang chịu áp lực thời gian.

### 7.3. Bước 3 — Nhận và kiểm tra bộ recovery

Người giữ và người chứng kiến kiểm tra:

- Recovery ID, phiên bản và đích khớp sự cố.
- Tình trạng niêm phong hoặc vật mang tin.
- Công cụ, thiết bị và runbook có thể sử dụng.
- Không có dấu hiệu bộ đã bị thu hồi hoặc thay thế.
- Đường thao tác đáp ứng điều kiện tin cậy đã xác định.

Chỉ mở vật liệu cần cho bước hiện tại; hạn chế việc lấy mọi credential ra cùng lúc.

### 7.4. Bước 4 — Xác thực và thực hiện tác vụ giới hạn

Trước khi nhập credential, xác minh mình đang kết nối đúng đích bằng cơ chế phù hợp: danh tính hệ thống, chứng thư, dấu vân tay khóa máy chủ đã được quản lý hoặc đường console vật lý đúng thiết bị.

Thực hiện các tác vụ đã được phép, ghi lại người thao tác, thời gian, đích, thay đổi và kết quả. Nếu hệ thống hỗ trợ tài khoản định danh riêng cho người vận hành, sử dụng để tăng khả năng quy trách nhiệm. Nếu buộc dùng tài khoản recovery dùng chung, ghép log kỹ thuật với hồ sơ phê duyệt và chứng kiến để xác định người thực hiện.

Không dùng cùng credential đó để truy cập thêm hệ thống ngoài phạm vi chỉ vì nó cũng đăng nhập được.

### 7.5. Bước 5 — Khôi phục đường quản trị thông thường

Khi PAM hoạt động trở lại, phải kiểm tra chức năng thật sự cần thiết, không chỉ thấy tiến trình chạy:

- Có thể xác thực quản trị qua đường thông thường.
- Policy và phạm vi quyền đúng.
- Secret cần thiết có thể được cung cấp cho đúng người hoặc workload.
- Phiên truy cập và log được xử lý theo thiết kế.
- Công việc luân chuyển credential và kết nối tới hệ thống đích có trạng thái rõ ràng.

Một giao diện đăng nhập hoạt động chưa chứng minh toàn bộ dịch vụ PAM đã phục hồi.

### 7.6. Bước 6 — Kết thúc quyền khẩn cấp và tái cấp bộ recovery

Kết thúc phiên, thu hồi quyền tạm và xử lý token hoặc phiên còn hiệu lực theo khả năng hệ thống. Với password/private key đã được lộ cho người vận hành, thay thế hoặc thu hồi theo quy trình. Với thiết bị không xuất khóa, quyết định có phải tái đăng ký hoặc thay thế dựa trên việc thiết bị có bị mất kiểm soát hay nghi lộ hay không.

Sau đó kiểm thử bộ thay thế, phân phối lại các bản được quản lý, thu hồi bản cũ và tái niêm phong. Không ghi “đã đóng sự cố” trong khi bộ recovery duy nhất vẫn chứa credential đã bị thay trên đích.

## 8. Bằng chứng khi hệ thống giám sát cũng đang hỏng

Thiết kế bằng chứng có thể gồm:

| Bằng chứng | Nội dung cần có | Nội dung cần tránh |
| --- | --- | --- |
| Hồ sơ kích hoạt | Lý do, người yêu cầu, phê duyệt, phạm vi, mã sự cố | Secret hoặc mã phục hồi |
| Biên bản mở bộ | Mã bộ, phiên bản, người giữ, chứng kiến, tình trạng niêm phong | Ảnh chụp nội dung phong bì |
| Nhật ký thao tác | Người thực hiện, đích, hành động, kết quả, thời gian | Password trong lệnh, token trong URL |
| Log kỹ thuật | Đăng nhập, thay đổi đặc quyền, cấu hình hoặc credential | Xuất log toàn bộ mà không xem nguy cơ lộ dữ liệu nhạy cảm |
| Hồ sơ kết thúc | Kết thúc phiên, thu hồi/thay thế, kiểm thử, tái niêm phong | Chỉ ghi “xong” mà không đối soát |

Nếu SIEM không hoạt động, ghi nhận cục bộ trên phương tiện được kiểm soát và bảo toàn log của hệ thống đích khi khả thi. Khi dịch vụ trở lại, đối soát và nhập bằng chứng, ghi rõ dữ liệu nào chưa thể thu được.

Chênh lệch đồng hồ giữa thiết bị cần được ghi nhận để giải thích thứ tự sự kiện. Không sửa lịch sử để làm các mốc thời gian trông khớp nhau.

Checksum của một gói bằng chứng có thể giúp kiểm tra thay đổi nếu giá trị đối chiếu được bảo vệ riêng. Nó không tự chứng minh ai đã tạo bằng chứng hoặc ngăn người sửa cả dữ liệu lẫn checksum. Cơ chế chữ ký, lưu trữ và phân quyền cần phù hợp với mức bảo đảm tổ chức yêu cầu.

## 9. Tình huống thực hành: PAM và SSO cùng mất khả dụng

### 9.1. Bối cảnh giả định

Một tổ chức dùng PAM để cung cấp credential quản trị hạ tầng và ghi nhận phiên đặc quyền. PAM chạy trên hạ tầng ảo hóa. Đăng nhập vận hành thông thường dùng SSO.

Sau lỗi hạ tầng, PAM và đường SSO quản trị không sử dụng được. Tổ chức có bản sao lưu tại kho riêng, nhưng cần quyền quản trị hạ tầng để dựng môi trường phục hồi.

Trước sự cố, tổ chức đã chuẩn bị:

- Một danh tính recovery cục bộ cho đường quản trị hạ tầng được xác định.
- Bộ vật liệu xác thực được niêm phong, có bản quản lý tại địa điểm dự phòng.
- Đường console và máy trạm recovery đã kiểm thử.
- Quyền truy cập kho backup và vật liệu giải mã được quản lý riêng.
- Runbook có người phê duyệt thay thế và biểu mẫu sự cố ngoại tuyến.

### 9.2. Thực hiện

1. Điều phối viên xác nhận đường quản trị bình thường không hoạt động và khai báo phạm vi khôi phục.
2. Hai người theo chính sách nội bộ xác minh yêu cầu và bàn giao bộ recovery đúng phiên bản.
3. Người vận hành xác minh console đích, đăng nhập bằng danh tính recovery và khôi phục phần hạ tầng được phép.
4. Đội phục hồi sử dụng đúng bản sao lưu cùng vật liệu khóa tương thích, theo trình tự của sản phẩm.
5. Đội kiểm tra PAM hoạt động, xác thực, quyền truy cập, log và kết nối với các đích quản trị.
6. Đội đối soát credential có thể lệch giữa backup và hệ thống đang chạy.
7. Kết thúc phiên khẩn cấp, xử lý credential đã sử dụng, kiểm thử bộ mới và tái niêm phong.
8. Hoàn tất đối soát bằng chứng và ghi nhận cải tiến.

### 9.3. Điểm khó: credential trong backup có thể đã cũ

Giả sử bản sao lưu PAM được tạo trước một lần luân chuyển password trên máy chủ đích. Sau khi restore, PAM có thể giữ password cũ trong khi máy chủ đích đang chấp nhận password mới.

Khôi phục thành công database PAM không tự giải quyết sai lệch này. Cần quy trình đối soát và tái thiết lập trạng thái credential theo sản phẩm, bằng một danh tính hoặc đường quản trị được phép còn hoạt động.

Không thử hàng loạt password để “đoán bản đúng”, và không rollback password của toàn bộ đích chỉ để khớp backup mà chưa đánh giá ảnh hưởng tới workload.

Vì vậy, kiểm thử phục hồi phải bao gồm trường hợp có rotation sau thời điểm backup. Đây là vấn đề đồng bộ trạng thái, khác với việc file backup có đọc được hay không.

### 9.4. Đo khả năng phục hồi

Ví dụ một bài diễn tập có mục tiêu nội bộ hoàn tất trong 90 phút:

| Công đoạn | Thời gian minh họa |
| --- | --- |
| Xác nhận sự cố và phê duyệt | 10 phút |
| Lấy bộ recovery và chuẩn bị console | 15 phút |
| Khôi phục hạ tầng, dữ liệu và thành phần phụ thuộc | 40 phút |
| Kiểm tra đường quản trị và chức năng PAM | 15 phút |
| Tổng tới mốc khôi phục đã định nghĩa | 80 phút |

Các số trên chỉ là ví dụ, không phải chuẩn thời gian của PAM. Tổ chức phải định nghĩa rõ mốc đạt RTO: có thể là phục hồi một chức năng trọng yếu hoặc toàn bộ dịch vụ theo kế hoạch.

Việc thay thế credential, đối soát bằng chứng và tái niêm phong vẫn là điều kiện đóng quy trình dù có thể diễn ra sau mốc khôi phục dịch vụ. Không bỏ thời gian lấy credential ra khỏi phép đo chỉ vì đó là thao tác vật lý.

RPO phản ánh mức mất dữ liệu chấp nhận được theo thời điểm phục hồi. Độ mới của bộ recovery liên quan đến credential và cấu hình hiện hành; hai chỉ tiêu có liên hệ nhưng không thay thế nhau.

## 10. Kiểm thử đường recovery một cách có kiểm soát

### 10.1. Kiểm tra tài liệu và diễn tập kỹ thuật khác nhau

Tabletop giúp đội vận hành nhận biết ai làm gì và thiếu phê duyệt nào. Diễn tập kỹ thuật mới giúp xác nhận credential còn được chấp nhận, công cụ đọc được dữ liệu và đường console thực sự hoạt động.

Một bài kiểm thử nên có phạm vi được phê duyệt, điều kiện dừng, người phụ trách và biện pháp tránh ảnh hưởng production. Có thể kiểm thử từng phần trong môi trường phù hợp, sau đó đánh giá rõ phần nào chưa được chứng minh trên hệ thống thật.

Không chủ động làm gián đoạn IdP production chỉ để kiểm tra một tài khoản recovery. Có thể mô phỏng hoặc giới hạn phụ thuộc trong môi trường thử nghiệm đã được phép.

### 10.2. Ma trận thử lỗi

| Điều kiện thử | Kết quả mong đợi | Dấu hiệu thất bại cần ghi nhận |
| --- | --- | --- |
| Không lấy secret từ PAM | Lấy được bộ recovery qua quy trình dự phòng | Runbook hoặc mã mở két chỉ nằm trong PAM |
| Đường SSO thông thường không dùng được | Danh tính recovery vẫn đi qua cơ chế xác thực đã thiết kế | Đăng nhập chuyển về đúng IdP đang lỗi |
| Một người giữ không có mặt | Nhánh thay thế hợp lệ vẫn đạt yêu cầu kiểm soát | Phải bỏ dual control hoặc không ai thay được |
| Địa điểm chính không tiếp cận được | Lấy được bộ và công cụ tại địa điểm dự phòng | Bản dự phòng chỉ có secret, thiếu thiết bị đọc |
| Bộ cũ bị đưa nhầm | Phiên bản được phát hiện trước khi sử dụng | Không có mã bộ hoặc danh sách thu hồi |
| Có rotation sau backup | Phát hiện và xử lý sai lệch theo runbook | Chỉ kiểm tra giao diện PAM, bỏ qua kết nối đích |
| SIEM tạm mất khả dụng | Có bằng chứng dự phòng và đối soát sau đó | Không biết ai đã dùng tài khoản chung |
| Nghi credential bị lộ | Có đường thu hồi và tái cấp bộ mới | Credential dùng chung quá nhiều đích, không thể thay có kiểm soát |

Tần suất thử nghiệm do mức rủi ro, yêu cầu vận hành và chính sách quyết định. Ngoài lịch định kỳ, xem xét thử lại khi thay cơ chế xác thực, cấu hình truy cập, người giữ, địa điểm lưu hoặc kiến trúc phục hồi.

### 10.3. Tiêu chí PASS có ý nghĩa

Một kết quả PASS cần chỉ ra được:

- Bộ recovery được lấy bởi đúng người trong thời gian phù hợp.
- Danh tính và đích được xác minh.
- Credential hoạt động trong kịch bản mất phụ thuộc đã chọn.
- Quyền đủ để thực hiện tác vụ cần thiết và phạm vi được kiểm soát.
- Có bằng chứng phê duyệt, sử dụng và kết quả.
- Các credential hoặc vật liệu cần thay sau kiểm thử đã được xử lý.
- Bộ recovery trở về trạng thái sẵn sàng, đúng phiên bản.

Nếu credential đã bị mở trong bài diễn tập, cần xử lý trạng thái phơi lộ theo chính sách. Chỉ đặt lại vào phong bì cũ không chứng minh vòng đời đã hoàn tất.

## 11. Lỗi thiết kế thường gặp và cách sửa

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ lưu credential khôi phục trong chính vault | Không có điểm bắt đầu khi vault hỏng | Chuẩn bị đường bootstrap độc lập, được bảo vệ và kiểm thử |
| Đặt khóa giải mã cùng bản backup không có phân tách phù hợp | Người lấy backup có thể lấy luôn khả năng giải mã | Phân tách truy cập, bảo vệ khóa theo cơ chế phù hợp |
| In toàn bộ secret của doanh nghiệp | Phạm vi lộ lớn, cập nhật khó và nhiều bản cũ | Chọn tập quyền phục hồi tối thiểu, quản lý từng bản |
| Mặc định recovery nghĩa là tắt MFA | Tạo đường truy cập yếu hoặc không phù hợp nền tảng | Thiết kế phương thức xác thực độc lập và kiểm thử; ngoại lệ phải có chính sách |
| Đổi password đích nhưng quên bộ ngoại tuyến | Bộ recovery không đăng nhập được lúc cần | Gắn cập nhật bộ vào quy trình thay đổi và đối soát |
| Chỉ có một người biết mọi thứ | Mất khả dụng hoặc thiếu phân tách trách nhiệm | Có người thay thế và cơ chế phối hợp phù hợp |
| Dùng credential recovery hằng ngày | Mất mục đích khẩn cấp, tăng nguy cơ lộ | Tách đường vận hành thường ngày và giám sát mọi lần sử dụng recovery |
| Coi thiết bị offline là chống malware tuyệt đối | Credential có thể bị lấy khi cắm hoặc sử dụng | Kiểm soát môi trường nhập, vật mang tin và máy trạm |
| Chỉ kiểm tra còn phong bì trong két | Không chứng minh credential, quyền và đường truy cập hoạt động | Diễn tập cả xác thực và tác vụ phục hồi có kiểm soát |
| Khôi phục xong nhưng không tái cấp bộ | Secret đã dùng còn tồn tại hoặc bộ mới thiếu | Hoàn tất thu hồi, thay thế, kiểm thử và niêm phong trước khi đóng quy trình |

## 12. Câu hỏi tự kiểm tra

### Câu 1: Password nằm trên giấy và không kết nối mạng. Có đủ để nói hệ thống phục hồi được khi IdP hỏng không?

Chưa đủ. Phải kiểm tra tài khoản đó được xác thực ở đâu, có bị chuyển về IdP hay không, quyền có còn hiệu lực và đường truy cập tới đích có sử dụng được không.

### Câu 2: Vì sao không gom khóa giải mã backup và toàn bộ credential vào cùng một USB?

Việc gom có thể tạo một điểm mất dữ liệu và lộ quyền rất lớn. Ngoài bảo vệ vật mang tin, cần phân tích ai được lấy từng thành phần, ai có thể giải mã, khả năng thay thế và ảnh hưởng khi USB bị mất. Thiết kế cụ thể phải cân bằng khả dụng với phân tách trách nhiệm.

### Câu 3: Có thể dùng hash password làm bằng chứng bản trong két còn đúng không?

Hash không chứng minh hệ thống đích hiện chấp nhận credential và có thể tạo thêm nguy cơ đoán ngoại tuyến. Quản lý phiên bản và kiểm thử xác thực có kiểm soát phù hợp hơn cho mục tiêu này.

### Câu 4: PAM đã restore thành công nhưng kết nối tới máy chủ báo sai password. Vì sao?

Backup có thể chứa credential trước lần rotation gần nhất trên máy chủ. Cần đối soát trạng thái và phục hồi quan hệ quản lý credential theo quy trình, không chỉ kiểm tra tính toàn vẹn file backup.

### Câu 5: Người phê duyệt chính không liên lạc được thì bỏ yêu cầu hai người có hợp lý không?

Chỉ thực hiện nhánh thay thế đã được phê duyệt trong chính sách. Kế hoạch phải chuẩn bị vai trò dự phòng và phương thức xác minh danh tính; áp lực thời gian không tự tạo quyền bỏ kiểm soát.

### Câu 6: Khi nào một lần sử dụng recovery được coi là kết thúc?

Khi mục tiêu phục hồi đã được kiểm tra, phiên và quyền khẩn cấp đã được xử lý, credential cần thay đã thay, bộ recovery sẵn sàng trở lại và bằng chứng đã được đối soát. Mốc này cần được theo dõi riêng với thời điểm dịch vụ bắt đầu hoạt động lại.

## 13. Tài liệu tham khảo

Các quy trình, bảng kiểm và ví dụ trong bài là thiết kế minh họa; phải ánh xạ vào khả năng của sản phẩm và chính sách tổ chức.

- [Microsoft Learn — Manage emergency access accounts in Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access): ví dụ theo nền tảng về tài khoản khẩn cấp, đa dạng phương thức xác thực, bảo quản và kiểm thử. Không áp nguyên cấu hình Entra cho mọi sản phẩm PAM.
- [NIST SP 800-57 Part 1 Revision 5 — Recommendation for Key Management: General](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf): nền tảng tham khảo về quản lý khóa và kế hoạch phục hồi khả năng sử dụng khóa. Bài này không quy định mọi credential là khóa mật mã.
