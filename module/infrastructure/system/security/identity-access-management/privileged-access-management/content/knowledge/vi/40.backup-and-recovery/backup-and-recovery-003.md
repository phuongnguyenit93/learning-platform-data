# Encryption key backup: sao lưu khóa mã hóa cho hệ thống PAM

## 1. Mục tiêu và tình huống mở đầu

Một hệ thống Privileged Access Management (PAM) đã sao lưu cơ sở dữ liệu chứa credential, cấu hình chính sách và bản ghi phiên quản trị. Khi trung tâm dữ liệu chính gặp sự cố, đội vận hành khôi phục được toàn bộ file nhưng vault vẫn không mở được: bản sao chứa dữ liệu mã hóa và khóa dữ liệu đã được bọc, còn khóa cần để mở lớp bọc chỉ tồn tại ở miền đã mất.

Tình huống này cho thấy **sao lưu dữ liệu mã hóa chưa đủ để bảo đảm khôi phục dữ liệu**. Cần khôi phục được toàn bộ chuỗi khóa, quyền sử dụng khóa và các thành phần tin cậy liên quan.

Encryption key backup là việc tạo và bảo quản vật liệu khôi phục khóa theo cơ chế được hệ thống hỗ trợ, sao cho người có thẩm quyền có thể phục hồi khả năng giải mã khi xảy ra sự cố. Vật liệu đó có thể là khóa đã bọc, bản sao HSM được bảo vệ, các phần bí mật theo ngưỡng hoặc cơ chế khôi phục do nhà cung cấp quản lý. Không nhất thiết tồn tại một file khóa có thể tải xuống.

Sau bài học, người học cần làm được:

- Phân biệt bản sao dữ liệu, bản sao khóa và cơ chế mở khóa hệ thống.
- Xác định khóa nào bảo vệ credential, phiên ghi hình và các bản sao lưu của PAM.
- Thiết kế bản sao đủ độc lập với miền sự cố chính nhưng vẫn duy trì least privilege.
- Tổ chức phục hồi có phê duyệt, ghi bằng chứng và đối soát trạng thái credential.
- Chứng minh khả năng khôi phục bằng diễn tập, thay vì chỉ dựa vào thông báo backup thành công.

## 2. Phân biệt các đối tượng trước khi sao lưu

### 2.1. Dữ liệu, khóa và quyền sử dụng khóa

Ba đối tượng sau liên quan chặt chẽ nhưng không thay thế nhau:

| Đối tượng | Ví dụ trong PAM | Điều cần khôi phục |
|---|---|---|
| Dữ liệu được bảo vệ | Mật khẩu quản trị, secret tài khoản dịch vụ, recording phiên | Nội dung, phiên bản và metadata cần để diễn giải |
| Khóa mật mã | Khóa mã hóa dữ liệu, khóa bọc khóa, khóa của kho backup | Đúng vật liệu khóa hoặc khả năng sử dụng đúng khóa |
| Quyền và môi trường sử dụng khóa | Chính sách KMS, miền bảo mật HSM, danh tính workload | Đường xác thực và cấp quyền hoạt động trong môi trường phục hồi |

Có key ID nhưng mất vật liệu khóa thì không giải mã được. Có khóa nhưng không xác thực được vào KMS cũng có thể khiến dịch vụ ngừng hoạt động. Có cả hai nhưng sử dụng sai phiên bản hoặc sai ngữ cảnh mã hóa vẫn có thể thất bại.

Mật khẩu của một tài khoản quản trị được lưu trong vault là **dữ liệu cần bảo vệ**, không mặc nhiên là khóa dùng để mã hóa vault. Hai loại bí mật có vòng đời và phương án phục hồi riêng.

### 2.2. DEK, KEK và điểm tin cậy gốc

Trong một mô hình envelope encryption minh họa:

- **Data Encryption Key (DEK):** mã hóa nội dung, chẳng hạn một nhóm credential hoặc một recording.
- **Key Encryption Key (KEK):** bảo vệ DEK dưới dạng đã bọc; KEK có thể nằm trong KMS hoặc HSM.
- **Điểm tin cậy gốc:** thành phần cho phép sử dụng hoặc phục hồi KEK, tùy kiến trúc. Có thể liên quan đến miền bảo mật HSM, khóa cấp cao hơn hoặc cơ chế quản lý của nhà cung cấp.

~~~text
Credential / recording
        │ mã hóa bằng
        ▼
       DEK
        │ được bọc bằng
        ▼
       KEK
        │ được bảo vệ và sử dụng trong
        ▼
KMS / HSM / cơ chế tin cậy của nền tảng
~~~

Đây là mô hình khái niệm. Không áp đặt tên gọi hoặc số tầng này lên mọi sản phẩm PAM. Một số nền tảng còn có khóa barrier, khóa mở niêm phong, khóa phục hồi và khóa riêng cho backup.

Điểm cần kiểm kê là quan hệ thực: **vật gì cần để giải mã vật gì**, và quan hệ đó có tồn tại ở môi trường khôi phục hay không.

### 2.3. Backup, archive, replication và recovery

| Khái niệm | Mục đích chính | Giới hạn cần nhớ |
|---|---|---|
| Backup | Khôi phục từ một điểm đã lưu | Có thể thiếu khóa hoặc metadata nếu phạm vi sai |
| Archive khóa | Giữ khả năng xử lý dữ liệu lịch sử theo chính sách | Cần theo dõi dữ liệu nào vẫn phụ thuộc khóa |
| Replication | Duy trì bản sao phục vụ tính sẵn sàng | Có thể lan truyền xóa nhầm, thay đổi sai hoặc sự cố quyền |
| Recovery | Tái lập khả năng sử dụng dữ liệu an toàn | Bao gồm khóa, dữ liệu, danh tính, chính sách và kiểm chứng |

NIST phân biệt nhu cầu lưu khóa theo loại khóa và thời gian còn phải sử dụng dữ liệu được bảo vệ. Vì vậy, chính sách backup không nên áp dụng giống nhau cho mọi khóa. Xem [NIST SP 800-57 Part 1 Revision 5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf).

Một cụm KMS có tính sẵn sàng cao có thể giúp chịu lỗi hạ tầng, nhưng chưa chứng minh rằng tổ chức có thể phục hồi sau việc xóa khóa hoặc mất quyền kiểm soát tài khoản quản lý.

## 3. Kiểm kê khóa theo dữ liệu và phụ thuộc

### 3.1. Bắt đầu từ tài sản cần phục hồi

Không bắt đầu bằng câu hỏi “có thể xuất khóa nào?”. Hãy bắt đầu bằng các tài sản:

1. Credential tài khoản người quản trị.
2. Secret tài khoản dịch vụ và tác vụ tự động.
3. Cơ sở dữ liệu, cấu hình và metadata của vault.
4. Bản ghi phiên, transcript và chỉ mục phục vụ kiểm toán.
5. Dữ liệu sao lưu và archive của chính PAM.
6. Thành phần cần để khởi động môi trường phục hồi.

Với mỗi tài sản, lần theo DEK, khóa bọc DEK, nơi chứa khóa và danh tính có quyền sử dụng khóa.

Một bảng kiểm kê minh họa:

| Tài sản | Khóa hoặc cơ chế phụ thuộc | Metadata cần giữ | Người chịu trách nhiệm |
|---|---|---|---|
| Database credential | DEK và KEK của vault | Key version, định dạng snapshot, tenant | Chủ dịch vụ PAM |
| Recording phiên | Khóa của kho recording | Object ID, key reference, ngữ cảnh mã hóa | Đội vận hành phiên |
| Bản sao database | Khóa mã hóa backup, ngoài các khóa của vault | Backup set, thuật toán, phiên bản công cụ | Đội backup |
| Bản sao HSM | Cơ chế backup của HSM | Miền bảo mật, khả năng tương thích, quorum | Nhóm quản trị mật mã |
| Kho archive | Khóa lịch sử còn cần cho dữ liệu lưu giữ | Dữ liệu phụ thuộc và thời hạn lưu | Chủ dữ liệu và kiểm toán |

Bảng này không chứa giá trị khóa, mật khẩu hoặc các phần bí mật. Metadata cũng cần kiểm soát truy cập vì có thể tiết lộ cấu trúc hạ tầng.

### 3.2. Vẽ đồ thị phụ thuộc phục hồi

Giả sử:

~~~text
Snapshot vault
  ├─ cần KEK-V của vault để mở DEK
  └─ nằm trong backup package cần KEK-B để giải mã

KEK-V
  └─ cần HSM recovery package và quorum người giữ vật liệu

KEK-B
  └─ cần KMS độc lập và danh tính phục hồi

Danh tính phục hồi
  └─ cần phương thức xác thực hoạt động khi PAM chính ngừng
~~~

Nếu mật khẩu duy nhất của danh tính phục hồi nằm trong vault đang khóa, đồ thị có vòng phụ thuộc. Nếu vật liệu phục hồi HSM chỉ lưu trong backup package mà KEK-B lại nằm trong HSM đó, có một vòng phụ thuộc khác.

Mỗi đường phục hồi cần kết thúc ở một điểm tin cậy có thể sử dụng khi miền chính mất. Điểm này có thể là phần cứng, tài liệu niêm phong hoặc cơ chế xác thực dự phòng có kiểm soát; không nhất thiết là một credential lâu dài có quyền rộng.

### 3.3. Không mặc định xuất mọi khóa

Một số khóa không cho xuất ra ngoài miền mật mã. Trong trường hợp đó, kiểm tra cơ chế backup, sao chép hoặc phục hồi chính thức của nền tảng.

Không thay thế bằng cách tìm cách đọc khóa từ bộ nhớ, chụp debug hoặc sao chép file nội bộ không được hỗ trợ. Một file có vẻ chứa khóa chưa chắc là bản sao có thể phục hồi, và việc lấy nó có thể phá vỡ ranh giới bảo vệ đã thiết kế.

Đối với khóa ký, khóa xác thực hoặc khóa phiên tạm thời, mục tiêu phục hồi có thể là cấp khóa mới, thu hồi khóa cũ hoặc lưu bằng chứng xác minh. Không suy từ nhu cầu giải mã dữ liệu sang yêu cầu lưu mọi khóa riêng vô thời hạn.

## 4. Mô hình đe dọa của bản sao khóa

Bản sao khóa là một đường truy cập đặc quyền. Nếu bảo vệ yếu hơn hệ thống chính, người tấn công có thể chọn đường backup để lấy credential mà không đi qua quy trình yêu cầu quyền của PAM.

Cần xét đồng thời ít nhất năm tình huống:

| Tình huống | Rủi ro | Biện pháp thiết kế |
|---|---|---|
| Mất thiết bị hoặc trung tâm dữ liệu | Không còn khóa để mở dữ liệu | Bản sao phục hồi ở miền sự cố khác |
| Tài khoản backup bị chiếm | Lấy hoặc xóa vật liệu phục hồi | Tách quyền đọc, phục hồi, xóa và quản trị khóa |
| Quản trị viên nội bộ lạm quyền | Tự phục hồi vault ngoài kiểm soát | Phê duyệt độc lập, dual control, bằng chứng |
| Ransomware hoặc xóa nhầm | Mất cả dữ liệu và bản sao cùng lúc | Bản sao có cơ chế chống sửa/xóa phù hợp, quyền quản trị độc lập |
| Thay thế package hoặc manifest | Khôi phục sai dữ liệu, sai khóa hoặc dữ liệu bị sửa | Kiểm tra tính xác thực, tính toàn vẹn và nguồn gốc |

Không có vị trí nào tự động giải quyết cả năm tình huống. Một thiết bị offline vẫn có thể bị mất, hỏng hoặc bị sao chép. Một kho lưu giữ bất biến vẫn cần bảo vệ người có quyền đổi chính sách và quản lý khóa mã hóa kho.

Mục tiêu không chỉ là “có thêm một bản”. Mục tiêu là bản sao còn dùng được sau sự cố đã xác định và không tạo đường vượt quyền cho một cá nhân.

## 5. Bảo vệ khóa khi sao lưu

### 5.1. Giữ khóa trong dạng được bảo vệ

Các cách triển khai có thể gồm:

- Backup gốc của HSM, có bảo vệ mật mã và điều kiện phục hồi của HSM.
- Xuất khóa dưới dạng đã bọc sang miền đích được nền tảng hỗ trợ.
- Bản sao do KMS quản lý hoặc cơ chế khôi phục được dịch vụ hỗ trợ.
- Vật liệu phục hồi theo ngưỡng được sản phẩm triển khai chính thức.

Không coi Base64, mã QR hoặc nén file là mã hóa. Một file chứa khóa thô trong thư mục chỉ có quyền đọc hạn chế vẫn là khóa thô.

Cũng không tự sáng tạo quy trình bọc khóa bằng một đoạn script chưa được kiểm chứng. Cần sử dụng cơ chế mật mã và định dạng được nền tảng hỗ trợ, bao gồm bảo vệ tính toàn vẹn khi cần.

### 5.2. Phân biệt mã hóa package và bọc khóa

Mã hóa toàn bộ backup package bảo vệ phương tiện lưu trữ. Bọc khóa bảo vệ chính vật liệu khóa và ràng buộc cách mở khóa. Một triển khai có thể cần cả hai lớp.

Ví dụ, bản sao vault có DEK đã bọc bằng KEK-V, rồi cả package được mã hóa bằng KEK-B. Muốn phục hồi cần cả đường sử dụng KEK-B và đường sử dụng KEK-V. Có thêm lớp bảo vệ cũng có nghĩa là có thêm phụ thuộc phải thử.

Không gộp mọi lớp bảo vệ vào một câu “backup đã mã hóa” rồi bỏ qua việc ai có thể giải mã, từ đâu và bằng danh tính nào.

### 5.3. Quorum, dual control và split knowledge

- **Dual control:** một hoạt động nhạy cảm cần sự tham gia hoặc chấp thuận của nhiều người theo chính sách.
- **Split knowledge:** vật liệu khóa được chia để một phần riêng lẻ không tiết lộ khóa.
- **Quorum:** cần đủ số người, thiết bị hoặc phần bí mật hợp lệ để thực hiện hành động.

Ba khái niệm có thể kết hợp, nhưng không đồng nghĩa. Hai người cùng biết toàn bộ mật khẩu là một dạng kiểm soát vận hành, không phải split knowledge.

Ví dụ minh họa cơ chế ngưỡng 3 trong 5: cần ba phần hợp lệ để phục hồi. Không thực hiện bằng cách cắt chuỗi khóa thành năm đoạn văn bản. [Định nghĩa split knowledge của NIST](https://csrc.nist.gov/glossary/term/split_knowledge) nhấn mạnh rằng từng phần không cung cấp hiểu biết về giá trị khóa.

Cần xác minh sản phẩm thực sự hỗ trợ cơ chế nào. Không mặc định rằng bộ “recovery keys” của một sản phẩm có thể thay thế khóa KMS bên ngoài hoặc mở dữ liệu khi mất hoàn toàn khóa gốc.

Các phần bí mật phải được giữ ở các vị trí và bởi các chủ thể đủ độc lập. Năm phần trong cùng một password manager hoặc cùng một két có thể không tạo được khả năng chịu lỗi như dự định.

### 5.4. Tách quyền theo hành động

Một mô hình phân quyền có thể là:

| Vai trò | Được phép | Không tự có quyền |
|---|---|---|
| Backup operator | Tạo và kiểm tra bản sao theo job | Giải mã toàn bộ credential |
| Recovery operator | Thực hiện restore đã duyệt trong môi trường chỉ định | Phê duyệt yêu cầu của chính mình |
| Key custodian | Tham gia bước mật mã được giao | Tự truy cập dữ liệu vault sau restore |
| Approver | Duyệt mục đích, phạm vi và thời hạn | Sở hữu đủ vật liệu khóa để tự phục hồi |
| Auditor | Xem sự kiện, hash, biên bản và kết quả | Đọc khóa hoặc secret thực tế |

Áp dụng JIT/JEA cho quyền phục hồi khi nền tảng hỗ trợ: quyền có thời hạn, giới hạn môi trường và hành động cụ thể. Cơ chế khẩn cấp phải hoạt động khi PAM chính ngừng, đồng thời vẫn có xác thực mạnh và cách ghi bằng chứng độc lập.

## 6. Bảo đảm bản sao khóa khớp với bản sao dữ liệu

### 6.1. Khóa mới không tự giải mã dữ liệu cũ

Giả sử vault chuyển từ KEK-V phiên bản 7 sang phiên bản 8. Có thể xảy ra hai cách xử lý, tùy nền tảng:

1. Dữ liệu mới dùng DEK hoặc lớp bọc mới, còn dữ liệu cũ vẫn phụ thuộc phiên bản 7.
2. Các DEK hiện có được bọc lại bằng phiên bản 8, nhưng snapshot trước đó vẫn chứa lớp bọc phiên bản 7.

Trong cả hai trường hợp, bản sao lịch sử có thể cần khóa cũ. Tạo khóa mới với tên hoặc alias giống khóa cũ không tạo lại cùng giá trị mật mã.

Thời điểm ngừng dùng khóa để mã hóa mới không tự động là thời điểm được xóa khóa. Cần xác định mọi dữ liệu, snapshot và archive còn phải giải mã bằng khóa đó.

### 6.2. Lập recovery set

Một recovery set là tập dữ liệu, khóa và metadata được chứng minh có thể khôi phục cùng nhau. Khái niệm này giúp tránh việc chọn ngẫu nhiên “bản database mới nhất” và “bản khóa mới nhất”.

Manifest minh họa, chỉ chứa dữ liệu giả định:

~~~yaml
recoverySetId: pam-dr-example-042
environment: production
dataSnapshotId: vault-snapshot-example-042
snapshotFormatVersion: "vendor-format-example"
keyDependencies:
  - purpose: vault-data
    keyReference: "hsm-key-reference-example"
    requiredVersion: "7"
    recoveryArtifactId: "hsm-package-example-017"
  - purpose: backup-package
    keyReference: "kms-key-reference-example"
    requiredVersion: "3"
    recoveryArtifactId: "provider-recovery-reference-example"
encryptionContextReference: "context-manifest-example-042"
integrityManifestReference: "integrity-manifest-example-042"
restoreRunbookVersion: "rb-pam-dr-6"
lastRestoreTestId: "drill-example-021"
~~~

Đây không phải schema cấu hình của một sản phẩm. Không đưa khóa, phần bí mật, token, passphrase hoặc credential vào manifest.

Manifest cần thể hiện đủ tham chiếu để tìm được dependency. Việc chỉ ghi key alias có thể không đủ nếu alias được chuyển sang khóa khác. Dùng định danh ổn định và quy tắc phiên bản đúng với nền tảng.

### 6.3. Tính toàn vẹn không đồng nghĩa tính xác thực

Hash giúp phát hiện khác biệt nếu có giá trị chuẩn đáng tin cậy. Nếu kẻ tấn công có thể thay cả package lẫn file hash, so sánh hai file đó không chứng minh nguồn gốc.

Bảo vệ manifest và bằng chứng bằng cơ chế xác thực phù hợp, chẳng hạn chữ ký hoặc kho lưu có quyền và lịch sử thay đổi được kiểm soát. Chuỗi tin cậy xác minh manifest cũng cần khả dụng trong môi trường phục hồi.

Nếu mã hóa sử dụng ngữ cảnh hoặc associated data, cần bảo toàn các giá trị cần thiết như tenant, object ID và mục đích sử dụng. Không sửa tùy tiện metadata để “thử cho giải mã được”; lỗi có thể báo sai bộ dữ liệu hoặc bị thay thế.

## 7. Quy trình tạo và bảo quản bản sao

### Bước 1: Xác định kịch bản và mục tiêu

Ghi rõ cần chịu được lỗi nào: hỏng một node, mất site, mất tài khoản quản trị, xóa khóa hay compromise toàn miền chính. Mỗi kịch bản yêu cầu mức độc lập khác nhau.

Đặt mục tiêu:

- **RPO:** lượng thay đổi chấp nhận mất, xét cả dữ liệu và khả năng truy cập khóa tương ứng.
- **RTO:** thời gian tái lập dịch vụ, bao gồm triệu tập quorum, dựng môi trường, phục hồi khóa, dữ liệu và kiểm chứng.

Không lấy thời gian sao chép file làm toàn bộ RTO.

### Bước 2: Chuẩn bị phạm vi và quyền

Xác nhận loại khóa, chính sách xuất/backup, nền tảng đích và người thực hiện. Cấp đúng quyền cần cho job; kiểm tra danh tính dùng khi sự cố mà không cần lấy credential từ PAM đang khóa.

Chuẩn bị môi trường không ghi khóa thô vào shell history, log debug, ticket hoặc recording phiên. Bằng chứng nên lưu hành động và kết quả, không lưu nội dung bí mật.

### Bước 3: Tạo bản sao bằng cơ chế được hỗ trợ

Thực hiện theo runbook và phiên bản sản phẩm đã được kiểm chứng. Tạo hoặc cập nhật manifest liên kết bản dữ liệu với các dependency.

Nếu có rotation hoặc thay đổi miền bảo mật trong lúc backup, dùng cơ chế nhất quán của nền tảng hoặc một cửa sổ có điều phối. Không mặc định hai job chạy gần nhau theo thời gian là nhất quán.

### Bước 4: Xác minh và lưu ở miền phù hợp

Kiểm tra artifact có đọc được, đủ thành phần, đúng định danh và được bảo vệ theo chính sách. Chuyển tới vị trí phục hồi đã xác định; ghi nhận chain of custody khi có thiết bị hoặc vật liệu vật lý.

Tính độc lập có thể cần xét vùng địa lý, tài khoản quản trị, hệ thống danh tính, khóa bảo vệ backup và người có quyền xóa. Lưu khác thư mục trên cùng máy không tạo miền sự cố riêng.

### Bước 5: Thử khả năng sử dụng

Kiểm tra metadata hoặc lệnh kiểm tra package chỉ là bước sơ bộ. Cần phục hồi thử theo lịch và sau các thay đổi trọng yếu.

Chỉ đánh dấu recovery set có thể dùng sau khi tiêu chí kỹ thuật của quy trình được đáp ứng. Ghi riêng “job tạo backup thành công” và “restore đã kiểm chứng”; hai trạng thái không nên bị nhập làm một.

## 8. Khôi phục khóa và dữ liệu PAM có kiểm soát

### 8.1. Khởi tạo phiên phục hồi

Một yêu cầu phục hồi nên ghi:

- Sự cố hoặc mục đích diễn tập.
- Recovery set, phạm vi tenant và dữ liệu được phép xử lý.
- Môi trường đích cùng mức cô lập.
- Người thực hiện, người phê duyệt và key custodian.
- Khoảng thời gian quyền có hiệu lực.
- Nơi lưu bằng chứng và tiêu chí kết thúc.

Xác định sự cố là mất khả dụng hay nghi lộ khóa. Nếu nghi lộ khóa, phục hồi khả năng truy cập chưa đủ để khôi phục độ tin cậy; cần phối hợp ứng phó sự cố và kế hoạch chuyển sang khóa mới.

### 8.2. Dựng môi trường sạch và kiểm tra tương thích

Chuẩn bị KMS/HSM, phiên bản phần mềm, miền bảo mật và đường xác thực theo runbook. Một artifact tạo từ thiết bị này không mặc nhiên phục hồi được lên mọi thiết bị cùng hãng hoặc mọi phiên bản.

Cô lập mạng của vault phục hồi trước khi mở dữ liệu. Vô hiệu hoặc chặn các tác vụ tự động có thể tác động tới hệ thống thật, như rotation, discovery, connector và cấp credential cho workload.

Nếu bản backup nghi bị can thiệp, kiểm tra nguồn gốc và trạng thái tin cậy trước khi nhập vào môi trường đích.

### 8.3. Khôi phục theo thứ tự phụ thuộc

Thứ tự minh họa:

~~~text
Phê duyệt và xác thực độc lập
  → cơ sở tin cậy KMS/HSM
  → khả năng sử dụng khóa backup
  → giải mã package
  → khả năng sử dụng khóa vault
  → mở dữ liệu và kiểm tra
  → đối soát credential, chính sách, audit
  → quyết định đưa dịch vụ trở lại
~~~

Thứ tự thực tế do đồ thị phụ thuộc và sản phẩm quyết định. Không thực hiện bước xuất khóa thô chỉ để làm quy trình dễ hơn.

Key custodian tham gia đúng bước cần thiết; không chuyển phần bí mật qua chat để một operator gom đủ và giữ lâu dài. Thu hồi quyền tạm sau khi hoàn thành.

### 8.4. Kiểm chứng cả mật mã lẫn nghiệp vụ

Bài kiểm tra nên chứng minh:

1. Mở được recovery set đúng phiên bản.
2. Giải mã được các đối tượng mẫu thuộc nhiều nhóm dữ liệu và các thế hệ khóa cần hỗ trợ.
3. Giải mã thất bại khi cố tình thiếu quyền hoặc dùng sai ngữ cảnh trong bài thử đã thiết kế.
4. Chính sách tenant và quyền đọc secret còn được thực thi.
5. Ghi nhận được hành động phục hồi và truy cập sau phục hồi.
6. Recording và metadata liên quan còn đối chiếu được.

Sử dụng dữ liệu tổng hợp khi có thể. Nếu cần kiểm tra dữ liệu thật, giới hạn mẫu, người xem, đầu ra và thời gian lưu theo phê duyệt.

Không chỉ kiểm tra trang đăng nhập của PAM: giao diện hoạt động có thể cùng tồn tại với lỗi giải mã ở một nhóm credential hoặc một tập recording lịch sử.

### 8.5. Đối soát credential sau khi mở vault

Snapshot cũ có thể chứa mật khẩu trước lần rotation gần nhất, trong khi hệ thống đích đã dùng mật khẩu mới. Giải mã thành công chỉ chứng minh vault đọc được giá trị đã lưu.

Trước khi nối lại connector và automation:

- Xác định tài khoản nào đã rotation sau thời điểm snapshot.
- Đối soát theo quy trình được hỗ trợ, có giới hạn thử đăng nhập để tránh khóa tài khoản.
- Kiểm tra tài khoản đã thu hồi, thay đổi chủ sở hữu và chính sách vừa cập nhật.
- Bảo toàn bằng chứng lịch sử, rồi lập kế hoạch reconcile hoặc rotation phù hợp.

Một vault phục hồi từ snapshot không nên tự động lấy lại quyền tác động production chỉ vì bước giải mã đã thành công.

## 9. Rotation, compromise và hủy khóa

### 9.1. Sau rotation

Mỗi thay đổi khóa cần trả lời:

- Dữ liệu nào dùng phiên bản mới?
- Dữ liệu hoặc snapshot nào vẫn cần phiên bản cũ?
- Artifact phục hồi đã bao phủ phiên bản mới chưa?
- Quyền phục hồi và runbook có đổi không?
- Bài diễn tập gần nhất đã kiểm tra đường mới chưa?

Chỉ hủy khóa cũ khi chứng minh không còn dữ liệu cần sử dụng, hoặc khi có quyết định hủy dữ liệu được phê duyệt. Thời hạn giữ khóa phải gắn với nhu cầu dữ liệu, không chỉ lịch backup gần nhất.

### 9.2. Khi nghi lộ khóa

Khôi phục một khóa từ bản sao không làm khóa đó trở lại bí mật. Cần đánh giá phạm vi dữ liệu và thời gian có thể bị ảnh hưởng, các bản sao khóa đã phân phối và credential có nguy cơ lộ.

Tùy lớp bị ảnh hưởng, có thể cần bọc lại DEK, mã hóa lại dữ liệu bằng DEK mới và rotation credential trên hệ thống đích. Bọc lại DEK không xóa được việc đối phương đã lấy DEK hoặc plaintext trước đó.

Giữ bằng chứng và các bản dữ liệu lịch sử theo quyết định ứng phó sự cố. Không xóa ngay khóa cũ khi hành động đó có thể làm mất khả năng điều tra hoặc khôi phục dữ liệu cần thiết.

### 9.3. Khi hết thời hạn lưu

Quy trình hủy cần xét khóa chính, bản sao được bọc, artifact HSM, bản sao offline và các phần bí mật liên quan. Nếu còn một đường phục hồi hợp lệ, tuyên bố “đã hủy khóa” có thể chưa đúng.

Ngược lại, không giả định xóa một alias hoặc một bản sao cục bộ đã thực hiện cryptographic erasure. Cần hiểu cơ chế xóa thực tế, các bản sao còn tồn tại và khả năng khôi phục của nền tảng.

Việc hủy phải có thẩm quyền, bằng chứng và đối chiếu phạm vi dữ liệu được phép mất khả năng giải mã.

## 10. Diễn tập và bằng chứng phục vụ kiểm toán

### 10.1. Bộ tình huống diễn tập

| Bài thử | Điều muốn chứng minh | Tiêu chí đạt minh họa |
|---|---|---|
| Mất site chính | Đường phục hồi không phụ thuộc site đó | Mở được mẫu dữ liệu ở môi trường DR trong RTO |
| IdP hoặc PAM chính ngừng | Danh tính phục hồi vẫn dùng được | Có xác thực mạnh và audit độc lập |
| Một custodian vắng mặt | Quorum khả thi trong thực tế | Đủ người/phần hợp lệ trong thời gian mục tiêu |
| Khôi phục snapshot trước rotation | Khóa lịch sử được bảo toàn | Giải mã đúng các phiên bản cần giữ |
| Package bị sửa | Cơ chế kiểm tra phát hiện can thiệp | Chặn trước khi sử dụng dữ liệu không tin cậy |
| Thiếu khóa hoặc bị từ chối quyền | Lỗi có thể phân loại và xử lý | Xác định đúng dependency, không nới quyền tùy tiện |
| Nâng cấp phần mềm hoặc HSM | Bản sao còn tương thích | Restore thử đạt trên cấu hình đích đã định |
| Vault mở được nhưng secret lỗi thời | Có kiểm chứng nghiệp vụ | Phát hiện chênh lệch trước khi bật automation |

Tần suất diễn tập dựa trên rủi ro, thay đổi và yêu cầu vận hành của tổ chức. Thay đổi KMS/HSM, cơ chế seal, danh tính phục hồi hoặc định dạng backup là lý do cụ thể để thử lại.

### 10.2. Bằng chứng nên lưu

Một báo cáo diễn tập hữu ích ghi recovery set, định danh artifact, phiên bản công cụ, môi trường đích, người phê duyệt, mốc thời gian, sự kiện sử dụng khóa và kết quả từng kiểm tra.

Không đưa plaintext credential, khóa thô, toàn bộ phần bí mật hoặc ảnh chụp chứa token vào báo cáo. Với phép thử giải mã, có thể ghi kết quả kiểm tra dữ liệu tổng hợp hoặc digest dự kiến đã được quản lý, thay vì nội dung bí mật.

Các chỉ số nên theo dõi gồm:

- Tỷ lệ recovery set còn thời hạn đã được restore thử.
- Thời gian thực tế cho từng chặng, nhất là triệu tập quorum và tái lập xác thực.
- Số dependency chưa có đường phục hồi độc lập.
- Số khóa lịch sử không đối chiếu được với dữ liệu phụ thuộc.
- Các thay đổi production xảy ra sau lần diễn tập gần nhất.

Một tỷ lệ “100% backup job thành công” không thay thế được các chỉ số này.

## 11. Ví dụ thiết kế và bài tập

### 11.1. Ví dụ: khôi phục PAM sau khi mất miền chính

Một tổ chức có vault production tại site A. Vault dùng HSM cho lớp khóa gốc, còn backup package được mã hóa qua một KMS. Kho recording có vòng đời khóa riêng. Yêu cầu là phục hồi ở site B khi site A không thể sử dụng.

Thiết kế minh họa gồm:

1. Snapshot vault và recording có manifest riêng, được liên kết thành recovery set.
2. Artifact phục hồi HSM lưu ngoài site A, theo cơ chế và khả năng tương thích đã thử.
3. Vật liệu quorum phân cho các custodian ở những vị trí phù hợp với kịch bản sự cố.
4. Đường sử dụng khóa mã hóa backup và danh tính DR không chỉ tồn tại trong PAM production.
5. Vai trò đọc backup không tự có quyền phục hồi khóa và đọc secret.
6. Môi trường DR cô lập, chặn connector trước khi mở snapshot.
7. Diễn tập kiểm tra cả dữ liệu mới, snapshot cũ và recording lịch sử.
8. Đối soát các lần rotation credential sau snapshot trước khi nối lại hệ thống thật.

Thiết kế chỉ đạt khi bài thử chứng minh các dependency hoạt động. Việc mua thêm HSM hoặc lưu thêm bản sao chưa tự tạo bằng chứng này.

### 11.2. Bài tập phân tích

Cho hiện trạng:

- Database vault được backup mỗi đêm.
- DEK đã bọc nằm trong snapshot.
- KEK nằm trong KMS của cùng tài khoản hạ tầng.
- Quyền xóa backup và xóa KEK do cùng một nhóm quản trị nắm.
- Credential của tài khoản DR chỉ nằm trong vault.
- Đội vận hành đã thử restore database nhưng chưa mở credential.
- Sau lần thử gần nhất, KEK đã rotation.

Hãy đề xuất kế hoạch cải thiện và một bài diễn tập có tiêu chí đạt.

Hướng giải:

- Bổ sung kiểm kê phiên bản khóa và xác định snapshot nào còn cần khóa cũ.
- Thiết lập đường xác thực DR độc lập có kiểm soát, xử lý vòng phụ thuộc vào vault.
- Tách quyền và miền sự cố theo kịch bản mất tài khoản quản trị; kiểm tra cơ chế phục hồi KMS thực tế.
- Liên kết dữ liệu, metadata và artifact khóa thành recovery set.
- Phục hồi vào môi trường cô lập, thử giải mã và kiểm tra quyền từ chối.
- Đối soát credential đã rotation; chưa bật connector cho tới khi xác nhận trạng thái.
- Ghi RPO/RTO thực tế, bằng chứng sử dụng khóa và công việc khắc phục còn lại.

Không thể giải bằng cách chỉ tăng tần suất backup database.

## 12. Những lỗi thường gặp và cách nhận biết

| Lỗi | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Có ciphertext nhưng thiếu khóa gốc | Restore file đạt, mở vault thất bại | Kiểm kê đầy đủ chuỗi khóa và đường phục hồi |
| Chỉ giữ khóa hiện hành | Snapshot cũ không giải mã được | Quản lý phiên bản theo dữ liệu còn lưu |
| Lưu mọi thứ cùng miền quản trị | Một tài khoản có thể xóa dữ liệu lẫn khóa | Thiết kế quyền và bản sao theo miền sự cố |
| Hiểu nhầm recovery key | Đủ phần phục hồi nhưng vẫn thiếu KMS ngoài | Đọc đúng cơ chế của sản phẩm và thử mất dependency |
| Dùng hash không có nguồn tin cậy | Package và hash bị thay mà vẫn “PASS” | Bảo vệ tính xác thực của manifest và artifact |
| Lộ khóa qua bằng chứng | Ticket, log hoặc recording chứa bí mật | Chỉ ghi metadata và kết quả cần thiết |
| Quorum chỉ tồn tại trên giấy | Không triệu tập đủ người trong RTO | Diễn tập vắng mặt và quản lý thay đổi nhân sự |
| Kết nối vault cũ vào production quá sớm | Rotation tự động gây lỗi tài khoản | Cô lập rồi đối soát trước khi bật tích hợp |
| Chỉ thử đường thành công | Sai tenant hoặc sai quyền chưa từng được thử | Bổ sung phép thử từ chối có kiểm soát |
| Hủy khóa khi dữ liệu vẫn cần | Archive còn file nhưng mất khả năng đọc | Đối chiếu dependency và phê duyệt trước hủy |

## 13. Điểm cần ghi nhớ

Sao lưu khóa mã hóa trong PAM là bảo đảm **đường khôi phục khả năng giải mã có kiểm soát**, không đơn thuần là sao chép một file bí mật. Đường đó phải bao phủ dữ liệu, phiên bản khóa, ngữ cảnh mật mã, danh tính, chính sách và các điểm tin cậy.

Một thiết kế có thể chấp nhận khi đã chứng minh: recovery set đúng và đủ, miền sự cố được xử lý, quyền phục hồi được giới hạn, không lộ vật liệu khóa trong quá trình thao tác, và dữ liệu mở được trong một bài diễn tập phù hợp. Với PAM, cần thêm bước đối soát credential và quyền trước khi dịch vụ trở lại production.

### Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Revision 5 — Recommendation for Key Management: General](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf): nguyên tắc vòng đời và bảo vệ vật liệu khóa.
- [NIST CSRC Glossary — Split knowledge](https://csrc.nist.gov/glossary/term/split_knowledge): phân biệt chia bí mật với việc chia chuỗi ký tự hoặc chỉ có nhiều người phê duyệt.
