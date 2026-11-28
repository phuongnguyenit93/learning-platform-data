# Vault data backup

## 1. Mục tiêu và phạm vi

Trong hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), vault giữ hoặc quản lý mật khẩu quản trị, khóa, tài khoản dịch vụ và thông tin điều khiển việc cấp quyền. Mất vault có thể khiến đội vận hành không lấy được credential để xử lý chính sự cố đang xảy ra. Khôi phục vault sai cách còn có thể đưa quyền đã thu hồi trở lại hoặc làm mật khẩu trong vault lệch với mật khẩu trên hệ thống đích.

**Vault data backup** là tạo và bảo vệ bản sao dữ liệu vault tại một thời điểm, kèm các điều kiện cần để khôi phục dữ liệu đó thành một dịch vụ PAM có thể sử dụng an toàn. Một file sao lưu tồn tại trên storage chưa chứng minh được điều này.

Sau bài học, người học có thể:

- Xác định dữ liệu nào thuộc bản sao vault và phụ thuộc nào cần bảo vệ riêng.
- Phân biệt backup với HA, replication, export secret và bản sao máy ảo.
- Thiết kế đường đi của bản sao theo nguyên tắc least privilege và phân tách trách nhiệm.
- Đánh giá RPO, RTO bằng khả năng phục hồi thực tế.
- Xây dựng quy trình tạo bản sao, xác minh, lưu giữ và diễn tập restore.
- Nhận diện các vấn đề đặc thù PAM: credential rollback, policy cũ, tài khoản đã nghỉ việc và tác động của automation sau phục hồi.

Trong bài, “vault” là kho bí mật của một giải pháp PAM nói chung. Ví dụ HashiCorp Vault được dùng để minh họa một cơ chế snapshot cụ thể; không suy rộng tên lệnh, định dạng hay phạm vi snapshot đó cho mọi sản phẩm PAM.

## 2. Backup bảo vệ trước sự cố nào?

Giả sử một doanh nghiệp quản lý tài khoản quản trị máy chủ, tài khoản dịch vụ cơ sở dữ liệu và khóa truy cập thiết bị mạng qua vault. Cụm vault có ba node và sao chép dữ liệu giữa các node.

Nếu một node hỏng, HA có thể duy trì dịch vụ. Nhưng nếu quản trị viên xóa nhầm một nhóm credential và thao tác xóa được sao chép thành công, cả ba node có thể cùng mang trạng thái không mong muốn. Nếu một tài khoản quản trị bị chiếm quyền rồi sửa policy, replica cũng có thể nhận policy độc hại đó.

Backup cung cấp điểm phục hồi lịch sử để xử lý các tình huống như:

- Hỏng hoặc mất storage làm mất dữ liệu trên cụm chính.
- Xóa nhầm secret, policy, metadata hoặc dữ liệu cấu hình được lưu trong vault.
- Thay đổi sai trong một đợt nâng cấp hoặc migration.
- Ransomware, phá hoại hoặc chiếm quyền quản trị tác động đến dữ liệu vận hành.
- Mất toàn bộ khu vực hạ tầng, tùy kiến trúc lưu giữ và phụ thuộc giải mã.

Backup không tự xử lý mọi hậu quả. Nếu credential đã bị lộ trước khi sao lưu, khôi phục bản sao không làm credential đó hết bị lộ. Nếu mật khẩu trên máy chủ đã đổi sau thời điểm snapshot, restore vault không tự đưa máy chủ về cùng thời điểm.

### 2.1. Phân biệt các cơ chế thường bị nhầm

| Cơ chế | Mục tiêu chính | Điểm cần hiểu khi thiết kế backup |
|---|---|---|
| HA hoặc cluster nhiều node | Tiếp tục phục vụ khi một thành phần lỗi | Không mặc định có lịch sử để quay lại trước một thao tác xóa sai |
| Replication sang cụm khác | Duy trì bản sao phục vụ vận hành hoặc DR theo sản phẩm | Có thể sao chép cả thay đổi sai; phải biết độ trễ và phạm vi không được replicate |
| Snapshot nhất quán của storage vault | Ghi lại trạng thái được storage hỗ trợ tại một điểm | Cần đúng công cụ, định dạng, phiên bản và phụ thuộc giải mã |
| Sao lưu VM hoặc volume | Bảo vệ hạ tầng và dữ liệu ở lớp máy/đĩa | Không mặc định là bản sao application-consistent của vault |
| Export secret qua API | Trích xuất một tập đối tượng cụ thể | Có thể thiếu policy, identity, phiên bản và metadata; có nguy cơ tạo plaintext |
| Lưu cấu hình bằng Git/IaC | Tái dựng các cấu hình đã quản lý bằng mã | Không thay thế dữ liệu runtime và không phải chỗ cất credential thật |

Một sản phẩm có replication và snapshot vẫn cần chính sách backup riêng: bản nào được giữ, ai có quyền xóa, khóa nào cần cho restore và ai kiểm chứng phục hồi được.

## 3. Xác định tập dữ liệu cần phục hồi

Thiết kế backup nên bắt đầu từ câu hỏi: “Cần những thành phần nào để cấp lại đúng quyền quản trị, với đúng bằng chứng kiểm toán?” Không bắt đầu bằng việc chọn một thư mục rồi nén tất cả file trong đó.

### 3.1. Dữ liệu trong vault

Tùy sản phẩm và cách triển khai, trạng thái cần bảo vệ có thể gồm:

- Credential và các phiên bản được lưu trong vault.
- Metadata liên kết tài khoản với hệ thống đích, chủ sở hữu, môi trường và mức độ nhạy cảm.
- Policy truy cập, role và mapping identity nằm trong kho dữ liệu của vault.
- Cấu hình auth method, secret engine hoặc cơ chế tích hợp được sản phẩm lưu trong storage.
- Trạng thái quản lý vòng đời credential, lease hoặc rotation được lưu tại thời điểm sao lưu.
- Các cấu hình điều khiển workflow approval, checkout hoặc session nếu chúng thực sự nằm trong thành phần đang được backup.

Không được kết luận rằng một snapshot chứa tất cả các mục trên chỉ vì chúng xuất hiện trong giao diện PAM. Một giải pháp có thể tách vault, máy chủ ứng dụng, kho session recording và cơ sở dữ liệu workflow thành nhiều hệ thống độc lập.

### 3.2. Các thành phần thường cần bảo vệ riêng

| Thành phần | Vì sao quan trọng | Cách xác nhận phạm vi |
|---|---|---|
| Cấu hình khởi động, storage và cluster | Dữ liệu đúng nhưng cấu hình sai vẫn có thể không khởi động được | Đối chiếu tài liệu backup của backend và cấu hình triển khai |
| KMS/HSM hoặc vật liệu unseal phù hợp | Cần để mở khóa các lớp mã hóa liên quan | Có sơ đồ phụ thuộc khóa và thủ tục custody riêng |
| TLS, trust store và cấu hình tên miền | Client và thành phần quản trị cần kết nối đúng, xác minh đúng dịch vụ | Kiểm tra cơ chế cấp lại/khôi phục và thời hạn chứng thư |
| Plugin và phiên bản phần mềm | Dữ liệu có thể tham chiếu chức năng không còn trên máy mới | Lưu bản phát hành được kiểm soát và thông tin kiểm chứng artifact |
| IdP, DNS, NTP và mạng quản trị | Xác thực, tên miền và thời gian ảnh hưởng đến quyền truy cập | Diễn tập với tình huống từng phụ thuộc không sẵn sàng |
| Audit log và session recording | Là bằng chứng về hoạt động đặc quyền | Có pipeline và retention độc lập, không mặc định nằm trong snapshot vault |
| Tài liệu vận hành và đường truy cập khẩn cấp | Đội phục hồi cần sử dụng được khi vault chính đã mất | Thử truy cập bằng cơ chế khẩn cấp đã phê duyệt |

Bản sao dữ liệu và các tài nguyên bổ trợ không nhất thiết nằm trong cùng một archive. Mục tiêu là có **bộ phục hồi được mô tả đầy đủ**, không gom dữ liệu mã hóa, khóa giải mã và quyền mở khóa vào cùng một nơi.

### 3.3. Ranh giới quan trọng: dữ liệu bên trong và trạng thái bên ngoài

Một vault PAM có thể quản lý mật khẩu trên Windows, Linux, database hoặc thiết bị mạng. Các hệ thống này có trạng thái riêng. Snapshot của vault chỉ chụp phần nằm trong phạm vi snapshot; không tự chụp đồng bộ toàn bộ mật khẩu và tài khoản trên các đích.

Ví dụ:

~~~text
09:00  Snapshot vault ghi nhận credential ở phiên bản C1.
09:08  Rotation thành công trên máy chủ đích, mật khẩu chuyển sang C2.
09:09  Vault đã ghi nhận C2.
09:20  Sự cố làm mất vault hiện tại.
10:00  Khôi phục snapshot 09:00: vault lại có C1, đích vẫn dùng C2.
~~~

Bản sao có thể hoàn toàn nguyên vẹn nhưng credential sau restore vẫn không đăng nhập được. Đây là vấn đề đối soát trạng thái, không phải bằng chứng rằng checksum snapshot sai.

## 4. Tính nhất quán và lựa chọn phương pháp backup

### 4.1. Dùng cơ chế được storage và sản phẩm hỗ trợ

Vault thường ghi dữ liệu qua transaction, journal hoặc cơ chế đồng thuận. Sao chép các file đang mở bằng một công cụ filesystem thông thường có thể lấy một phần dữ liệu trước transaction và một phần sau transaction.

Do đó, ưu tiên:

1. Cơ chế backup/snapshot do sản phẩm hỗ trợ cho đúng storage backend.
2. Cơ chế backup của backend bên ngoài khi tài liệu sản phẩm yêu cầu.
3. Quy trình quiesce hoặc dừng dịch vụ có kiểm soát nếu phương pháp được hỗ trợ cần điều đó.

Không tự áp một thao tác “dừng toàn bộ cluster” cho mọi trường hợp. Một số cơ chế snapshot hoạt động khi dịch vụ đang chạy; một số phương pháp khác có điều kiện riêng. Chọn cách làm theo backend thực tế, đồng thời đo tác động đến thời gian phục vụ.

Với HashiCorp Vault dùng Integrated Storage, tài liệu mô tả tạo snapshot bằng `vault operator raft snapshot save <file>`. Điều kiện của hướng dẫn gồm cụm Integrated Storage hợp lệ, quyền phù hợp và nơi lưu an toàn tách khỏi hạ tầng cụm. Đây là ví dụ riêng của sản phẩm, không phải lệnh chung cho một password vault PAM bất kỳ. [Tài liệu tạo snapshot HashiCorp Vault](https://developer.hashicorp.com/vault/docs/sysadmin/snapshots/save).

### 4.2. Nhất quán trong vault chưa phải nhất quán toàn hệ thống PAM

Một snapshot nhất quán về storage giúp phục hồi trạng thái nội bộ có ý nghĩa. Nhưng các thành phần bên ngoài như IdP, target account, SIEM và hệ thống phê duyệt có thể ở thời điểm khác.

Nếu cần phục hồi nhiều thành phần, phải ghi rõ:

- Điểm thời gian hoặc checkpoint của từng bản sao.
- Quan hệ giữa các bản sao có cùng đợt phục hồi.
- Thứ tự phục hồi.
- Những giao dịch không thể khôi phục đồng bộ và cách đối soát.
- Hành động tự động nào phải tạm giữ trước khi kết nối lại.

Không có timestamp chung nào tự biến các snapshot độc lập thành một transaction phân tán.

### 4.3. Full, incremental và chuỗi phụ thuộc

Nếu nền tảng hỗ trợ full/incremental, cần hiểu chính xác chuỗi khôi phục. Một bản incremental có thể chỉ sử dụng được khi còn bản full nền và đủ các thành phần phụ thuộc.

Lưu giữ file cuối cùng nhưng xóa mất bản nền có thể làm mất khả năng phục hồi của cả chuỗi. Retention phải xét tính hợp lệ của **tập khôi phục**, không chỉ tuổi của từng file.

Nếu sản phẩm chỉ cung cấp snapshot theo cơ chế riêng, không tự chia file để tạo “incremental” không được hỗ trợ. Việc deduplication ở storage cũng không thay đổi yêu cầu về tính đầy đủ của một bản phục hồi ở tầng ứng dụng.

## 5. Mã hóa và phụ thuộc khóa

Backup vault chứa tập trung dữ liệu đặc quyền có giá trị cao. Ngay cả bản mã cũng phải được bảo vệ như dữ liệu nhạy cảm vì việc chiếm thêm khóa hoặc quyền giải mã về sau có thể khiến nhiều credential bị lộ cùng lúc.

### 5.1. Phân biệt các lớp bảo vệ

Có thể tồn tại nhiều lớp độc lập:

~~~text
Dữ liệu credential
    ↓ mã hóa theo cơ chế của vault
Snapshot dữ liệu vault
    ↓ tùy thiết kế, thêm lớp mã hóa backup
Artifact được lưu tại repository
    ↓ mã hóa của storage và kiểm soát truy cập
Bản sao lưu giữ theo retention
~~~

Các lớp này có thể dùng những khóa và quyền khác nhau. Giải mã được lớp storage không đồng nghĩa mở được dữ liệu bên trong vault. Ngược lại, mã hóa sẵn trong vault không loại bỏ nhu cầu TLS, quyền truy cập repository và bảo vệ file tạm.

Không loại bỏ các cấu trúc keyring đã được mã hóa mà sản phẩm cần lưu trong snapshot. Quy tắc phân tách custody chủ yếu nhằm tránh để đủ **vật liệu hoặc quyền giải mã có thể sử dụng** bên cạnh bản sao dữ liệu theo cách một chủ thể đơn lẻ chiếm được cả hai.

### 5.2. Lập bản đồ phụ thuộc khóa

Với mỗi tập backup, cần có câu trả lời cho các câu hỏi sau:

- Dữ liệu này gắn với seal, khóa hoặc phiên bản khóa nào?
- Khóa có thể được sử dụng từ khu vực và môi trường phục hồi không?
- Tài khoản phục hồi có quyền gọi KMS/HSM phù hợp không?
- Những quyền đó có còn lấy được khi IdP hoặc vault chính không hoạt động?
- Người giữ key share có thể được liên hệ và tham gia đúng thời gian không?
- Một đợt rekey, seal migration hoặc thay KMS có ảnh hưởng đến bản sao cũ không?
- Khi nào được ngừng khóa cũ mà không phá hỏng các bản sao còn thời hạn?

Thông tin định vị khóa không phải chính giá trị khóa. Có thể lưu reference được kiểm soát trong catalog; không ghi private key, key share, mật khẩu hay root token vào manifest, ticket hoặc log của job backup.

Với HashiCorp Vault dùng auto-unseal, recovery key không thay thế được cơ chế KMS/HSM để giải mã root key. Nếu cơ chế seal cần thiết không còn sử dụng được, chỉ giữ recovery key và snapshot chưa đủ để unseal. Cần thiết kế vòng đời và quyền sử dụng seal theo khả năng phục hồi thực tế. [Tài liệu Seal/Unseal của HashiCorp Vault](https://developer.hashicorp.com/vault/docs/concepts/seal).

### 5.3. Tránh phụ thuộc vòng tròn

Một thiết kế lỗi phổ biến:

~~~text
Muốn lấy backup → cần credential trong vault chính.
Muốn mở KMS → cần credential trong vault chính.
Muốn đọc runbook → phải đăng nhập hệ thống phụ thuộc vault chính.
Muốn phục hồi vault chính → cần cả ba thứ ở trên.
~~~

Cách xử lý là cung cấp đường phục hồi độc lập đã phê duyệt: identity khẩn cấp có phạm vi hẹp, tài liệu truy cập được trong sự cố, cơ chế giữ khóa riêng và kiểm soát nhiều người khi cần.

Đường khẩn cấp vẫn phải có giới hạn quyền, thời gian sử dụng và audit. Không biến nó thành một tài khoản quản trị thường trực được chia sẻ rộng rãi.

### 5.4. Retention dữ liệu và retention khóa phải đi cùng nhau

Nếu giữ backup 90 ngày nhưng ngừng sử dụng khóa cần thiết sau 30 ngày, các bản sao còn lại có thể chỉ còn giá trị hình thức. Ngược lại, giữ khóa và backup vô thời hạn làm tăng lượng dữ liệu lịch sử có thể bị lộ.

Chính sách nên liên kết:

- Thời hạn giữ từng nhóm bản sao.
- Thời hạn sử dụng được của khóa tương ứng.
- Điều kiện legal hold nếu có.
- Diễn tập restore các thế hệ khóa còn được hỗ trợ.
- Phê duyệt hủy dữ liệu và hủy khóa sau khi hết mọi nghĩa vụ liên quan.

Không dùng “xóa khóa để hủy một backup” nếu cùng khóa đó vẫn bảo vệ bản sao khác hoặc dữ liệu vận hành còn cần thiết.

## 6. RPO và RTO phải đo từ bản sao sử dụng được

### 6.1. RPO — chấp nhận mất bao nhiêu thay đổi?

Recovery Point Objective (RPO) diễn đạt mức mất dữ liệu tối đa chấp nhận được theo thời gian. Với PAM, khoảng mất dữ liệu có thể chứa credential mới, thay đổi policy, rotation hoặc thao tác thu hồi quyền.

Nếu sự cố xảy ra tại thời điểm `T_sự_cố`, còn điểm dữ liệu mới nhất của bản sao được xác nhận sử dụng được là `T_điểm_phục_hồi`, có thể tính khoảng mất dữ liệu thực tế:

~~~text
Khoảng mất dữ liệu = T_sự_cố - T_điểm_phục_hồi
~~~

Phải dùng thời điểm dữ liệu mà snapshot đại diện, không thay bằng thời điểm upload xong. Trong sự cố an ninh, bản mới nhất có thể đã chứa thay đổi độc hại; điểm sạch được chọn có thể cũ hơn và làm khoảng mất dữ liệu lớn hơn.

Ví dụ mục tiêu RPO là 15 phút:

| Mốc | Trạng thái |
|---|---|
| 10:00 | Snapshot A đại diện trạng thái tại 10:00 |
| 10:05 | A đã được truyền, xác minh và bảo vệ tại repository |
| 10:15 | Job B thất bại |
| 10:22 | Sự cố xảy ra; A là điểm sử dụng được mới nhất |

Khoảng mất dữ liệu là 22 phút. Lịch chạy “15 phút/lần” không chứng minh đạt RPO 15 phút khi một job thất bại hoặc bản mới nhất chưa được bảo vệ đầy đủ.

Không cần restore mọi snapshot sau mỗi job nếu điều đó không khả thi. Tuy nhiên, phải có kiểm tra từng artifact phù hợp, theo dõi chuỗi phụ thuộc và chương trình diễn tập đại diện đủ để không nhầm “upload thành công” với “phục hồi đã được chứng minh”.

### 6.2. RTO — cần bao lâu để phục vụ an toàn trở lại?

Recovery Time Objective (RTO) là mục tiêu về thời gian khôi phục dịch vụ sau gián đoạn. Tổ chức cần định nghĩa rõ điểm bắt đầu và tiêu chí kết thúc phép đo.

Trong ví dụ sau, đo từ lúc dịch vụ mất tại 10:22 đến lúc luồng truy cập quản trị đã qua kiểm chứng lúc 11:47: tổng cộng 85 phút.

~~~text
Phát hiện và xác nhận sự cố        5 phút
Phê duyệt, huy động người giữ khóa 10 phút
Dựng môi trường phục hồi           15 phút
Lấy và xác minh bộ backup           8 phút
Nạp dữ liệu                         12 phút
Mở khóa và xác thực                  8 phút
Đối soát credential/identity        20 phút
Kiểm tra luồng PAM và audit          7 phút
Tổng                               85 phút
~~~

Một công cụ báo “restore 12 phút” chỉ phản ánh một phần của chuỗi. Nếu phải chờ người giữ khóa 60 phút, hoặc reconcile credential mất nhiều giờ, RTO thực tế vẫn có thể không đạt.

### 6.3. Phân tầng theo mức độ quan trọng

Không phải mọi credential có cùng yêu cầu. Tài khoản phục hồi hạ tầng, tài khoản quản trị hệ thống lõi và tài khoản lab có thể được phân nhóm khác nhau.

Tuy nhiên, nếu storage snapshot là toàn cụm, không được giả định có thể restore riêng một nhóm mà sản phẩm không hỗ trợ. Phân tầng có thể áp dụng ở thứ tự kiểm chứng dịch vụ, mức ưu tiên đối soát và kiến trúc vault; không tự thay đổi tính chất của cơ chế snapshot.

## 7. Thiết kế quyền và vị trí lưu

### 7.1. Đường đi của một bản sao

~~~mermaid
flowchart LR
    V["Vault đang vận hành"] --> B["Backup runner có quyền giới hạn"]
    B --> Q["Vùng tạm được bảo vệ"]
    Q --> R["Repository backup độc lập"]
    R --> T["Môi trường restore cô lập"]
    K["Custody khóa và quyền giải mã riêng"] --> T
    B --> E["Audit và catalog độc lập"]
    R --> E
    T --> E
~~~

Các mũi tên biểu diễn trách nhiệm và luồng dữ liệu, không ngụ ý mọi thành phần phải có kết nối mạng thường trực với nhau. Ví dụ, môi trường diễn tập chỉ được mở các kết nối cần thiết trong cửa sổ đã duyệt.

### 7.2. Phân tách nhiệm vụ

| Vai trò | Quyền phù hợp | Quyền không nên mặc định đi kèm |
|---|---|---|
| Backup runner | Yêu cầu snapshot theo API được hỗ trợ, ghi artifact mới, ghi trạng thái job | Đọc secret tùy ý, sửa policy, xóa toàn bộ lịch sử backup |
| Quản trị repository | Vận hành storage, dung lượng và cơ chế lưu giữ | Mặc định sở hữu đủ khóa giải mã dữ liệu vault |
| Người giữ khóa | Thực hiện phần việc mở khóa được phê duyệt | Tự chọn bản sao và tự khôi phục sản xuất ngoài quy trình |
| Điều phối phục hồi | Chọn mục tiêu, điều phối runbook, thu thập phê duyệt | Toàn quyền không giới hạn trên cả vault, backup và KMS |
| Người kiểm chứng | Đọc bằng chứng và kết quả kiểm tra phù hợp | Cần xem giá trị credential thật để xác nhận thành công |

Một quyền chỉ đọc snapshot có thể vẫn rất nhạy cảm vì cho phép lấy tập dữ liệu toàn vault. “Không có quyền đọc từng secret qua API” không đồng nghĩa quyền backup có rủi ro thấp.

Cấp credential cho runner qua cơ chế workload identity hoặc credential có vòng đời phù hợp khi nền tảng hỗ trợ. Nếu runner cần lấy quyền từ vault chính lúc tạo backup, vẫn phải có đường riêng để lấy các bản sao đã lưu khi vault chính không còn.

### 7.3. Tách failure domain và quyền phá hủy

Bản sao nằm trên cùng ổ đĩa với vault không bảo vệ được trước việc mất ổ đó. Bản sao ở bucket khác nhưng cùng tài khoản có thể vẫn bị xóa bởi cùng một quyền quản trị bị chiếm.

Thiết kế cần xem xét cả:

- Failure domain vật lý: host, storage, datacenter hoặc region.
- Failure domain quản trị: account, tenant, identity và tổ chức quản lý.
- Khả năng xóa hoặc ghi đè: versioning, retention lock, bản sao offline hoặc cơ chế tương đương.
- Khả năng sử dụng khóa trong miền phục hồi.
- Chính sách vị trí dữ liệu, chi phí và tốc độ lấy lại bản sao.

Immutable retention giúp giảm một số đường xóa hoặc sửa artifact trong thời hạn được thực thi. Nó không đảm bảo artifact ban đầu sạch, không bảo vệ trước việc mất khóa và không tự chặn hành vi đọc trộm dữ liệu.

### 7.4. Bảo vệ metadata và file tạm

Tên file có thể để lộ tên khách hàng, hệ thống lõi hoặc tài khoản đặc quyền. Catalog cũng có thể tiết lộ cấu trúc hạ tầng. Vì vậy cần kiểm soát quyền đọc cả artifact lẫn metadata.

Runner nên dùng vùng tạm riêng với quyền filesystem giới hạn, tránh thư mục đồng bộ cá nhân, không bật log nội dung payload và không đính kèm snapshot vào ticket. Việc dọn file tạm phải theo cơ chế của nền tảng; với SSD hoặc storage phân tán, không mặc định rằng ghi đè một file sẽ bảo đảm xóa mọi bản sao vật lý.

## 8. Catalog và manifest của bộ backup

Catalog giúp tìm được đúng bộ phục hồi, biết nó cần gì và đã được kiểm tra đến đâu. Không nên chỉ có danh sách tên file như `backup-final-2.snap`.

Một bản ghi nên có:

- ID bất biến của job và ID cụm nguồn.
- Môi trường nguồn, loại storage, bản phát hành phần mềm và revision cấu hình.
- Thời điểm snapshot đại diện, thời điểm bắt đầu và hoàn tất truyền.
- Phương pháp tạo bản sao và phạm vi dữ liệu.
- Định danh artifact, version storage, kích thước và digest.
- Tham chiếu các phụ thuộc khóa, cấu hình và plugin.
- Retention, vị trí bản sao khác và trạng thái bảo vệ.
- Kết quả kiểm tra artifact và tham chiếu diễn tập liên quan.

Ví dụ dưới đây là schema minh họa do bài học đề xuất, không phải file cấu hình được một sản phẩm cụ thể chấp nhận:

~~~yaml
schema: "pam-backup-example/v1"
backup_id: "lab-vault-20261127T020000Z"
source:
  cluster_ref: "lab-pam-a"
  environment: "training"
  product_release_ref: "approved-release-record"
  storage_profile_ref: "lab-storage-profile"
recovery_point:
  data_time_utc: "2026-11-27T02:00:00Z"
  checkpoint_ref: "provider-checkpoint-reference"
artifact:
  repository_ref: "lab-backup-repository"
  object_ref: "lab-pam-a/20261127/snapshot"
  object_version_ref: "immutable-object-version-reference"
  size_bytes: 12345678
  sha256: "<digest-computed-from-the-artifact>"
dependencies:
  vault_seal_profile_ref: "lab-seal-profile"
  backup_encryption_key_ref: "lab-backup-key-reference"
  config_revision_ref: "approved-config-revision"
  plugin_bundle_ref: "approved-plugin-bundle"
protection:
  retention_policy_ref: "lab-retention-policy"
  retention_verified: true
checks:
  transfer_integrity: "PASS"
  provenance: "PASS"
  restore_test_evidence_ref: null
~~~

Các giá trị trên đều là dữ liệu giả. `restore_test_evidence_ref: null` thể hiện chưa có bằng chứng diễn tập gắn với bản ghi này; không được tự điền PASS để làm báo cáo đẹp hơn.

### 8.1. Checksum không tự chứng minh nguồn gốc

Digest giúp phát hiện sự khác biệt giữa hai chuỗi byte khi có giá trị chuẩn đáng tin cậy để so sánh. Nếu kẻ tấn công thay được cả snapshot lẫn manifest chứa digest, checksum khớp vẫn không chứng minh snapshot đến từ nguồn hợp lệ.

Để tăng độ tin cậy, có thể dùng chữ ký số của manifest, catalog có kiểm soát sửa đổi hoặc log độc lập. Phải xác minh chữ ký bằng khóa công khai đáng tin cậy và kiểm tra định danh nguồn, không chỉ thấy có file `.sig` là coi như hợp lệ.

Giá trị hash và chữ ký cũng không chứng minh nội dung tại thời điểm sao lưu không bị sửa sai từ trước. Khi phục hồi sau một sự cố xâm nhập, cần kết hợp lịch sử thay đổi và mốc thời gian của sự cố để chọn điểm sạch.

## 9. Quy trình tạo backup

Quy trình sau là khung thao tác chung. Lệnh thực thi phải được thay bằng API hoặc công cụ được hỗ trợ của nền tảng đang sử dụng.

### 9.1. Trước khi tạo bản sao

1. Xác nhận đúng cụm, môi trường, storage backend và phạm vi.
2. Kiểm tra sức khỏe cần thiết của cụm theo phương pháp backup.
3. Xác nhận runner có quyền cần thiết, không dùng root token chỉ vì tiện.
4. Kiểm tra dung lượng vùng tạm, repository và quota.
5. Xác nhận định danh khóa, trạng thái KMS/HSM liên quan và retention.
6. Ghi job ID, mốc thời gian và revision cấu hình; không ghi credential vào log.
7. Kiểm tra không có xung đột với restore hoặc migration cần điều phối độc quyền.

### 9.2. Tạo và truyền artifact

Dùng công cụ hỗ trợ snapshot nhất quán. Artifact đang ghi nên ở trạng thái tạm, chưa được catalog công bố là điểm phục hồi hoàn tất.

Sau khi tạo:

- Kiểm tra công cụ kết thúc thành công và artifact có cấu trúc hợp lệ theo khả năng công cụ.
- Ghi digest, kích thước và thông tin điểm dữ liệu thực sự.
- Truyền qua kênh được bảo vệ vào repository.
- Xác minh lại artifact đã nhận bằng cơ chế toàn vẹn phù hợp.
- Kiểm tra version và retention thực tế đã được áp dụng.
- Chỉ công bố bản sao “đã bảo vệ” sau khi các điều kiện bắt buộc đều đạt.

Không diễn giải mọi ETag của object storage là MD5 hoặc checksum nội dung. Ý nghĩa trường này phụ thuộc nhà cung cấp và phương thức upload.

### 9.3. Kết thúc job có kiểm soát

Sau khi artifact đích được xác minh, ghi catalog và audit. Thu hồi hoặc để hết hạn credential tạm theo thiết kế, dọn vùng tạm và đánh giá tuổi của điểm phục hồi mới nhất.

Nếu job lỗi, không xóa bản tốt gần nhất để tiết kiệm dung lượng. Artifact chưa hoàn tất cần được phân loại rõ, xử lý theo quy trình và không xuất hiện như lựa chọn phục hồi hợp lệ.

### 9.4. Pseudocode điều phối

~~~text
job = begin_job(expected_cluster, expected_environment)
temporary_artifact = null

try:
    verify_source_identity(job)
    verify_supported_backup_method(job)
    verify_repository_and_key_dependencies(job)

    temporary_artifact = create_consistent_snapshot(job)
    verify_local_artifact(temporary_artifact)

    digest = compute_digest(temporary_artifact)
    destination = upload_new_object(temporary_artifact)

    verify_received_content(destination, digest)
    verify_required_retention(destination)
    publish_completed_catalog_record(job, destination, digest)
    emit_success_without_secret_payload(job)

catch error:
    record_failed_stage(job, redact_sensitive_fields(error))
    alert_if_recovery_point_objective_at_risk(job)

finally:
    release_temporary_identity_if_applicable(job)
    cleanup_or_quarantine_temporary_artifact(temporary_artifact)
    record_cleanup_result(job)
~~~

Đây là pseudocode, không phải script để chạy trên production. “Quarantine” chỉ có nghĩa giữ artifact lỗi trong vùng được bảo vệ khi quy trình cần điều tra; không cho phép để file chứa dữ liệu nhạy cảm tồn tại vô thời hạn ngoài retention.

## 10. Kiểm chứng bằng restore trong môi trường cô lập

### 10.1. Các mức kiểm tra khác nhau

| Mức kiểm tra | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| File tồn tại và có kích thước | Job đã tạo ra một artifact | Artifact đầy đủ hoặc giải mã được |
| Digest khớp giá trị tin cậy | Artifact không khác bản được tham chiếu | Dữ liệu sạch, quyền đúng hoặc dịch vụ hoạt động |
| Công cụ đọc được cấu trúc snapshot | Định dạng phù hợp ở mức công cụ kiểm tra | Toàn bộ phụ thuộc và luồng PAM phục hồi được |
| Restore và mở khóa thành công | Có thể dựng dữ liệu trong điều kiện diễn tập | Credential hiện vẫn khớp mọi target thật |
| Kiểm tra quyền, credential mẫu, audit và workflow | Luồng được thử đáp ứng tiêu chí đã định | Mọi luồng chưa thử đều đạt |

Một chương trình backup tốt cần kết hợp các mức trên. Không đánh đồng phép kiểm tra nhanh mỗi job với diễn tập phục hồi toàn bộ dịch vụ.

### 10.2. Cô lập trước khi nạp dữ liệu

Bản restore có thể chứa token, lease, lịch rotation, cấu hình cluster và endpoint sản xuất. Khi khởi động, automation có thể tác động tới hệ thống thật.

Trước restore, cần xác nhận:

- Client sản xuất không thể truy cập môi trường thử.
- Node thử không thể tự gia nhập cluster sản xuất.
- Automation không tự đăng ký lại vào DNS, service discovery hay load balancer sản xuất.
- Egress mặc định bị chặn; chỉ mở chính xác phụ thuộc cần thiết đã duyệt.
- Lịch rotation, revoke, sync hoặc connector có tác động ra ngoài được kiểm soát.
- Audit vẫn được ghi vào đích thử đã kiểm soát, tránh trộn sai bằng chứng với môi trường sản xuất.

HashiCorp cũng yêu cầu môi trường restore thử được cô lập để tránh giao tiếp cụm ngoài ý muốn hoặc thu hồi credential bên thứ ba đang dùng thật. Tài liệu còn lưu ý artifact plugin bên ngoài cần được chuẩn bị riêng và việc lệnh restore trả về không đồng nghĩa mọi bước phục hồi nền đã hoàn tất. [Tài liệu restore snapshot HashiCorp Vault](https://developer.hashicorp.com/vault/docs/sysadmin/snapshots/restore).

Nếu cần KMS/HSM để mở khóa, môi trường thử phải có đường truy cập tối thiểu được phê duyệt hoặc phương án seal phục hồi được sản phẩm hỗ trợ. Không tự đổi seal hay dùng một khóa mới rồi giả định bản mã cũ sẽ đọc được.

### 10.3. Các bước diễn tập

1. Chọn bộ backup, xác minh nguồn gốc, digest và dependencies.
2. Dựng phiên bản phần mềm/cấu hình tương thích theo thủ tục được hỗ trợ.
3. Xác nhận cô lập mạng và kiểm soát automation trước khi khởi động bản phục hồi.
4. Nạp dữ liệu theo đúng quy trình sản phẩm.
5. Thực hiện phần việc mở khóa với người giữ khóa phù hợp.
6. Chờ trạng thái hoạt động cần thiết; không chỉ dựa vào mã thoát của lệnh.
7. Kiểm tra đăng nhập bằng identity thử, quyền được phép và quyền phải bị từ chối.
8. Kiểm tra dữ liệu canary, metadata và một workflow truy cập đặc quyền trong lab.
9. Xác nhận audit ghi được ai đã thực hiện thao tác nào.
10. Ghi thời gian, điểm thất bại, chênh lệch so với mục tiêu và dọn môi trường thử.

Không xuất hàng loạt secret ra file để “kiểm tra nhanh”. Có thể dùng canary giả được chuẩn bị trước, phép so sánh trong tiến trình hoặc tác vụ xác thực không hiển thị credential; bằng chứng nên chỉ chứa PASS/FAIL và định danh được phép công bố.

### 10.4. Bằng chứng của một lần restore test

Báo cáo nên ghi backup ID, môi trường thử, người tham gia, mốc bắt đầu/kết thúc, phiên bản, phương pháp, các kiểm tra đã chạy và các kiểm tra bị chặn.

Nếu không thể kiểm tra tích hợp thật vì cô lập mạng, ghi rõ giới hạn đó. Ví dụ: “Mở khóa và đọc canary PASS; kết nối target production không nằm trong phạm vi diễn tập.” Không chuyển kết quả giới hạn thành tuyên bố “khôi phục hoàn chỉnh tất cả tài khoản”.

## 11. Rủi ro PAM sau khi khôi phục snapshot cũ

### 11.1. Credential rollback và sai lệch với hệ thống đích

Trong ví dụ C1/C2, không nên thử C1 liên tục trên target để xác minh. Việc đó có thể gây lockout hoặc tạo cảnh báo giả.

Quy trình đối soát nên:

1. Khoanh vùng những target có credential thay đổi sau điểm snapshot.
2. Dùng nguồn bằng chứng độc lập như log rotation, audit target và lịch thay đổi.
3. Kiểm tra có kiểm soát với tài khoản và target được cho phép.
4. Reconcile hoặc rotation theo cơ chế được sản phẩm hỗ trợ.
5. Cập nhật credential trong vault và xác nhận ứng dụng phụ thuộc dùng được.
6. Mở lại automation theo từng nhóm sau khi có kết quả.

Reconcile có thể cần một identity có quyền thay đổi credential trên target. Identity đó phải được bảo vệ, giới hạn và audit riêng. Không giả định luôn lấy lại được mật khẩu hiện tại từ target; nhiều hệ thống không cung cấp khả năng đọc lại mật khẩu.

### 11.2. Policy và identity đã bị thu hồi

Snapshot cũ có thể mang:

- Mapping của nhân viên đã nghỉ việc.
- Quyền quản trị rộng hơn policy hiện tại.
- Tài khoản khẩn cấp từng được cấp tạm.
- Token hoặc session record đã cũ.
- Cấu hình bỏ qua approval được sử dụng trong một đợt bảo trì trước đó.

Việc những đối tượng này có còn sử dụng được hay không phụ thuộc loại credential, thời hạn và cơ chế xác thực. Không giả định tất cả token cũ đều sống lại, cũng không giả định IdP sẽ tự chặn được mọi đường đăng nhập cục bộ.

Trước khi đưa vào phục vụ, đối chiếu baseline quyền hiện hành, danh sách thu hồi và sự kiện sau điểm snapshot. Kiểm tra cả tình huống được phép lẫn tình huống phải bị từ chối. Luồng JIT/JEA phải giữ đúng phạm vi và thời gian cấp quyền, thay vì phục hồi thành quyền thường trực.

### 11.3. Lease, certificate và tài khoản động

Phục hồi dữ liệu quản lý lease không bảo đảm tài khoản động trên database vẫn tồn tại hoặc certificate chưa hết hạn. Đồng hồ thời gian vẫn tiến về trước trong khi trạng thái vault quay về quá khứ.

Không kéo lùi đồng hồ production để làm credential cũ có vẻ còn hạn. Cần xác minh thời gian, TTL, trạng thái đích và quy trình cấp lại/thu hồi được hỗ trợ. Automation xử lý lease phải được kiểm soát để không thu hồi nhầm tài khoản vẫn đang phục vụ tải thật.

### 11.4. Snapshot từ giai đoạn bị xâm nhập

Một bản sao có thể có cấu trúc đúng nhưng chứa policy do kẻ tấn công tạo. Chọn bản gần nhất theo thời gian mà bỏ qua timeline sự cố có thể tái đưa cấu hình độc hại vào hệ thống.

Khi có dấu hiệu xâm nhập:

- Xác định khoảng thời gian có thể bị ảnh hưởng.
- Chọn điểm phục hồi theo bằng chứng sạch, chấp nhận đánh đổi RPO nếu cần.
- Kiểm tra policy, identity và cấu hình tích hợp trước khi kết nối lại.
- Đánh giá credential có thể đã bị lộ, sau đó rotation/revoke theo ưu tiên và phụ thuộc.
- Bảo toàn bằng chứng sự cố theo quy trình điều tra.

Backup hỗ trợ phục hồi dữ liệu; việc khôi phục niềm tin vào credential và quyền truy cập là phần việc bổ sung của ứng phó sự cố.

## 12. Giám sát, retention và xử lý lỗi

### 12.1. Chỉ số cần theo dõi

Không chỉ đếm số job thành công. Nên theo dõi:

- Tuổi của điểm phục hồi hợp lệ mới nhất.
- Số lần thất bại liên tiếp và thời gian artifact chưa được bảo vệ.
- Thời gian tạo, truyền và xác minh; xu hướng kích thước bất thường.
- Số bản sao đáp ứng retention và tình trạng phiên bản object.
- Ngày diễn tập gần nhất, phạm vi kiểm thử và RTO đo được.
- Tình trạng phụ thuộc khóa và ngày hết hạn của thành phần liên quan.
- Thay đổi quyền đọc/xóa repository, thay đổi retention và hành vi tải xuống bất thường.
- Kết quả dọn vùng tạm và các artifact bị quarantine quá hạn.

Cảnh báo nên phản ánh khả năng mất mục tiêu phục hồi. Ví dụ: “Điểm phục hồi hợp lệ mới nhất đã 24 phút trong khi RPO mục tiêu là 15 phút” có ý nghĩa hơn một email chung “job backup failed”.

### 12.2. Một số lỗi và hướng xử lý

| Hiện tượng | Giả thuyết cần kiểm tra | Hành động đầu tiên |
|---|---|---|
| Job báo thành công nhưng artifact rất nhỏ | Snapshot chưa được tạo đúng, response lỗi bị lưu thành file, nguồn sai | Kiểm tra công cụ, định dạng và định danh cụm; chưa công bố bản sao hợp lệ |
| Digest khác sau truyền | Truyền lỗi, chọn sai object version hoặc artifact bị sửa | Dừng công bố, giữ bằng chứng và xác minh nguồn |
| Có snapshot nhưng mở khóa thất bại | Sai seal profile, thiếu quyền KMS, mất key share hoặc lineage khóa không khớp | Đối chiếu manifest và thủ tục khóa; không tự thay khóa |
| Vault chạy nhưng credential không dùng được | Snapshot cũ hơn rotation ở target | Khoanh vùng và đối soát, tránh thử đăng nhập hàng loạt |
| Restore test làm target thật bị ảnh hưởng | Cô lập/egress/automation chưa đúng | Ngắt đường tác động, xử lý sự cố và đánh giá lại môi trường thử |
| Bản sao còn retention nhưng không restore được | Mất khóa, thiếu artifact bổ trợ hoặc chuỗi phụ thuộc bị xóa | Xác định tập bị ảnh hưởng, bảo toàn bản còn dùng được và sửa chính sách vòng đời |
| Có nhiều backup nhưng không có điểm sạch | Lỗi hoặc xâm nhập đã tồn tại qua nhiều chu kỳ | Phân tích timeline và quyết định phương án phục hồi cùng đội ứng phó |

Không dùng retry vô hạn cho mọi lỗi. Lỗi quyền hoặc seal mismatch cần được phân tích; lặp lại có thể tạo nhiễu, làm đầy storage hoặc che khuất thời gian RPO đã bị vượt.

### 12.3. Retention phải cân bằng khả năng phục hồi và mức phơi lộ

Bản sao lịch sử giúp xử lý lỗi phát hiện muộn nhưng giữ nhiều phiên bản credential làm tăng phạm vi dữ liệu cần bảo vệ. Chính sách cần có chủ sở hữu, thời hạn, cơ chế legal hold và thủ tục hủy.

Xóa một secret trong vault không mặc định xóa nó khỏi mọi snapshot còn retention. Quy trình quản lý dữ liệu cần ghi nhận điều này và kiểm soát quyền phục hồi bản cũ.

Khi hết thời hạn, hủy theo chính sách đã phê duyệt và xác nhận catalog không còn quảng bá tập đã hủy như một điểm phục hồi sử dụng được. Không xóa tự động bản nền hoặc khóa vẫn cần cho các tập khác.

## 13. Bài thực hành với vault lab

### 13.1. Chuẩn bị

Dùng môi trường lab tách biệt và secret giả. Chuẩn bị ba identity minh họa:

- `backup-runner-lab`: chỉ có quyền cần để tạo bản sao theo sản phẩm và ghi repository.
- `restore-operator-lab`: nhận quyền có thời hạn cho lần diễn tập.
- `auditor-lab`: đọc báo cáo và bằng chứng đã loại bỏ dữ liệu nhạy cảm.

Tạo một canary giả có hai phiên bản và một policy chỉ cho identity thử đọc canary. Chuẩn bị thêm một identity không được phép đọc để kiểm tra chiều từ chối.

Nếu cần target, dùng một database hoặc máy chủ lab với tài khoản riêng; không dùng credential thật của production.

### 13.2. Kịch bản A — tạo và phục hồi một điểm dữ liệu

1. Tạo canary ở phiên bản V1, ghi lại dấu hiệu kiểm tra không tiết lộ giá trị.
2. Tạo snapshot A bằng công cụ được hỗ trợ.
3. Lưu artifact vào repository lab, xác minh toàn vẹn và ghi catalog.
4. Đổi canary sang V2 sau khi A đã hoàn tất.
5. Dựng môi trường restore lab đã cô lập.
6. Phục hồi A và mở khóa theo thủ tục của lab.
7. Kiểm tra canary ở trạng thái tương ứng V1.
8. Xác nhận identity được phép truy cập thành công và identity bị cấm vẫn bị từ chối.
9. Xác nhận audit có đủ dấu vết, rồi dọn môi trường thử.

Kết quả mong đợi là chứng minh bản sao đại diện đúng điểm dữ liệu, có thể mở khóa và giữ hành vi kiểm soát quyền đã thiết kế trong phạm vi lab.

### 13.3. Kịch bản B — credential lệch sau rotation

Dùng target lab để tái hiện timeline C1/C2:

1. Chụp backup khi vault và target cùng dùng C1.
2. Rotation sang C2, xác nhận vault và target cùng ghi nhận trạng thái mới.
3. Phục hồi backup cũ vào mạng thử; giữ automation chưa tác động target.
4. Chỉ mở kết nối tới target lab đã chọn cho bước kiểm tra được duyệt.
5. Ghi nhận chênh lệch phiên bản và xử lý bằng quy trình reconcile/rotation của lab.
6. Xác minh luồng quản trị hoạt động và audit ghi đầy đủ.

Nếu không có cơ chế reconcile được hỗ trợ, dừng tại bước mô tả sai lệch và đề xuất thủ tục được chủ hệ thống phê duyệt. Không bịa một thao tác “đồng bộ mật khẩu” chung cho mọi nền tảng.

### 13.4. Kịch bản C — kiểm tra giả định phụ thuộc

Lần lượt mô phỏng một điều kiện không đáp ứng, chẳng hạn repository không truy cập được hoặc identity restore không có quyền dùng KMS. Không xóa khóa thật hay phá bản sao tốt để thử nghiệm.

Ghi:

~~~text
BACKUP_ID:
SCENARIO:
RESTORE_POINT:
ARTIFACT_INTEGRITY:
KEY_DEPENDENCY:
IDENTITY_ALLOW_TEST:
IDENTITY_DENY_TEST:
TARGET_RECONCILIATION:
AUDIT_EVIDENCE:
ELAPSED_TIME:
LIMITATIONS:
CLEANUP_RESULT:
~~~

Bài thực hành đạt khi báo cáo phản ánh đúng những gì đã kiểm chứng, ghi rõ giới hạn và không chứa secret, token, private key hay key share.

## 14. Tự kiểm tra và ghi nhớ

**Vì sao có ba node vault vẫn cần backup?** Vì HA xử lý tính sẵn sàng của cụm, trong khi thay đổi sai có thể được nhân bản đến mọi node. Cần điểm phục hồi lịch sử được bảo vệ độc lập.

**Vì sao snapshot mã hóa vẫn cần hạn chế quyền tải xuống?** Vì đó là tập dữ liệu đặc quyền tập trung; khả năng lộ khóa hoặc quyền giải mã về sau vẫn tồn tại. Metadata trong bản sao cũng có thể nhạy cảm.

**Vì sao checksum đúng chưa đủ?** Vì nó cần một giá trị tham chiếu đáng tin cậy và không chứng minh dữ liệu sạch, phụ thuộc khóa đầy đủ hoặc luồng PAM dùng được.

**Vì sao restore xong vault vẫn chưa phục vụ an toàn?** Vì cần kiểm tra quyền hiện hành, identity đã thu hồi, credential trên target, TTL, automation và audit. Khôi phục trạng thái quá khứ không tự đồng bộ thế giới bên ngoài.

**Khi nào một bản sao có giá trị vận hành?** Khi có thể tìm được, xác minh được, lấy được đúng phụ thuộc, khôi phục bằng thủ tục được hỗ trợ và có bằng chứng kiểm tra phù hợp với mục tiêu dịch vụ.

Điểm cốt lõi của vault data backup là bảo vệ đồng thời ba khả năng: **còn dữ liệu**, **mở được dữ liệu** và **sử dụng lại dữ liệu với đúng kiểm soát đặc quyền**. Mỗi khả năng cần thiết kế, chủ sở hữu và bằng chứng riêng.
