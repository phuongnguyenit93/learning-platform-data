# Xóa key khỏi backup

Trong quản lý khóa mật mã, **xóa key khỏi backup** là quy trình tìm, gỡ bỏ hoặc làm cho các bản sao khóa trong hệ thống sao lưu không còn khả năng được khôi phục và sử dụng trái phép. Các bản sao này có thể nằm trong file backup, snapshot, bản export, bản sao HSM, kho lưu trữ offline, escrow, replica hoặc các phiên bản cũ của một backup set.

Xóa một file có tên chứa key không chứng minh rằng vật liệu khóa đã biến mất. Bản sao có thể còn trong versioning, recycle bin, snapshot, bản sao vùng khác, phương tiện offline, hệ thống lưu giữ của nhà cung cấp hoặc một backup cũ hơn. Quy trình phải xác định đầy đủ nơi chứa bản sao, phương thức xóa phù hợp với từng loại phương tiện và bằng chứng cho thấy bản sao không còn khả năng phục hồi.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, tập trung vào vòng đời khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy. Khi xóa key khỏi backup, cần xét mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Phân biệt các đối tượng cần xóa

Trong một hệ thống thực tế, từ “key trong backup” có thể chỉ nhiều đối tượng khác nhau. Cần gọi đúng tên trước khi thực hiện:

| Đối tượng | Ví dụ | Điều cần kiểm soát |
|---|---|---|
| Vật liệu khóa dạng rõ | File chứa private key, secret key hoặc DEK chưa được bọc | Đây là bí mật trực tiếp; phải gỡ bỏ khỏi mọi bản sao và xử lý phương tiện theo chính sách sanitization. |
| Khóa đã được bọc (wrapped key) | DEK được mã hóa bằng KEK, key package được mã hóa | Không phải dạng rõ nhưng vẫn là tài sản nhạy cảm; khả năng khôi phục phụ thuộc vào khóa và cơ chế mở gói. |
| HSM backup blob | Gói backup được thiết bị HSM tạo ra | Có thể cho phép phục hồi khóa trong miền bảo mật phù hợp; cần kiểm soát cả blob và các thành phần/quyền dùng để restore. |
| Recovery shares | Các phần bí mật theo cơ chế M-of-N | Cần kiểm soát số phần còn lại, mọi bản sao và quy trình tập hợp quorum. |
| Key metadata | Key ID, version, fingerprint, thuật toán, policy và quan hệ phụ thuộc | Thường cần giữ để kiểm toán hoặc chứng minh lịch sử; metadata không chứa vật liệu bí mật vẫn phải được bảo vệ tính toàn vẹn. |
| Chứng thư và khóa công khai | Certificate, public key, chain of trust | Thường không cần xóa vì không phải bí mật; có thể cần lưu để xác minh chữ ký cũ và chứng minh danh tính. |

Phải phân biệt **xóa bản sao của khóa trong backup** với **hủy chính khóa**. Nếu một bản sao trong backup bị xóa nhưng khóa gốc vẫn được giữ trong HSM để vận hành, dữ liệu được bảo vệ bởi khóa đó vẫn có thể giải mã qua HSM. Nếu tổ chức hủy toàn bộ khóa và mọi đường khôi phục, dữ liệu phụ thuộc có thể trở nên không thể giải mã. Hai mục tiêu này có tác động rất khác nhau.

## 2. Vì sao phải xóa key khỏi backup

Một bản backup có thể tồn tại lâu hơn máy chủ hoặc ứng dụng đã tạo ra nó. Khi khóa đã hết mục đích sử dụng, bị thay thế hoặc phải hủy theo chính sách, bản sao cũ có thể trở thành điểm yếu:

- **Giảm bề mặt tấn công:** mỗi bản sao private key, DEK hoặc recovery package là thêm một nơi có thể bị đánh cắp.
- **Ngăn khôi phục khóa đã hết hạn hoặc bị thu hồi:** người vận hành có thể vô tình restore khóa cũ rồi tiếp tục dùng nó.
- **Đáp ứng chính sách lưu giữ và hủy:** tổ chức có thể phải xóa vật liệu khóa sau khi hết thời hạn, kết thúc hợp đồng hoặc hoàn thành yêu cầu xử lý dữ liệu.
- **Ngăn tái sử dụng sau sự cố:** bản backup của khóa đã bị compromise có thể bị dùng lại nếu quy trình restore không phân biệt trạng thái khóa.
- **Giảm rủi ro từ backup cũ:** phương tiện offline, snapshot hoặc kho lưu trữ ít được kiểm tra có thể chứa khóa không còn trong danh mục hiện hành.
- **Chuẩn bị hủy dữ liệu có kiểm soát:** trong một số thiết kế, hủy khóa bảo vệ riêng của một backup set là bước crypto-erasure để làm dữ liệu trong backup không thể giải mã.

Việc xóa phải có lý do và phạm vi rõ ràng. Không xóa một khóa khỏi backup chỉ vì nó không còn là khóa đang hoạt động: dữ liệu lịch sử, bản backup dài hạn, chữ ký cũ hoặc yêu cầu điều tra có thể vẫn phụ thuộc vào khóa đó.

## 3. Phân biệt xóa key copy, key destruction và crypto-erasure

Ba khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Hành động | Kết quả mong muốn |
|---|---|---|
| Xóa key copy khỏi backup | Gỡ các bản sao khóa khỏi backup set, snapshot hoặc phương tiện được chỉ định | Backup không còn chứa bản sao đó; khóa gốc có thể vẫn tồn tại ở nơi quản lý chính thức. |
| Key destruction | Hủy vật liệu khóa theo quy trình được phê duyệt ở mọi nơi có trách nhiệm lưu giữ | Không còn đường hợp lệ để sử dụng hoặc phục hồi khóa đã hủy. |
| Crypto-erasure | Hủy khóa mã hóa dữ liệu hoặc khóa bọc độc quyền của một tập dữ liệu | Ciphertext còn trên phương tiện nhưng không thể giải mã nếu mọi bản sao khóa và đường khôi phục đều đã bị loại bỏ. |

Ví dụ, tổ chức có một private key đang được HSM quản lý và một bản backup HSM offline. Nếu mục tiêu chỉ là bỏ bản backup offline vì đã hết thời hạn lưu, tổ chức có thể xóa gói backup và giữ khóa trong HSM theo chính sách. Nếu mục tiêu là hủy khóa hoàn toàn, phải xử lý cả HSM, các backup blob, bản export, recovery shares, replica và mọi đường khôi phục.

Crypto-erasure chỉ có hiệu lực khi khóa bị hủy thực sự là khóa cần thiết để giải mã dữ liệu đó và không có bản sao, khóa bọc, cache hoặc đường phục hồi thay thế. Nếu DEK được bọc bởi KEK, hủy KEK dùng riêng cho bản backup có thể làm DEK không thể mở; nhưng nếu DEK hoặc KEK còn một bản sao khác có thể dùng, dữ liệu chưa được crypto-erase.

## 4. Lập danh mục toàn bộ nơi có thể chứa key

Trước khi xóa, lập inventory theo key ID, version và fingerprint. Không tìm kiếm chỉ dựa vào tên file vì cùng một khóa có thể được lưu dưới nhiều tên hoặc trong một gói backup không thể đọc trực tiếp.

Các vị trí cần kiểm tra gồm:

- Backup đầy đủ, incremental, differential và các chuỗi backup cũ.
- Snapshot của volume, máy ảo, database, container image hoặc filesystem.
- Bản export từ KMS/HSM, HSM backup blob, key package và recovery package.
- Kho lưu trữ offline, băng từ, removable media và bản sao tại địa điểm DR.
- Object storage có versioning, soft delete, retention lock hoặc recycle bin.
- Replica vùng, bản sao cross-account/cross-tenant và bản sao của nhà cung cấp.
- Kho escrow, hệ thống quản lý secrets, file share, thư mục tạm và máy trạm quản trị.
- Artifact build/deploy, image, log, crash dump, ticket hoặc tài liệu vận hành nếu từng vô tình chứa key.
- Recovery shares, bản in, phong bì niêm phong và bản sao được custodians giữ.

Nên ghi nhận chủ sở hữu, vị trí, loại phương tiện, thời gian tạo, thời hạn lưu, trạng thái immutable, người quản lý và khả năng xóa của từng bản sao. Nếu không thể xác định một vị trí có chứa khóa hay không, đánh dấu là chưa xác minh và xử lý theo mức độ nhạy cảm cho đến khi có bằng chứng.

Một manifest kiểm kê có thể dùng cấu trúc như sau; các giá trị chỉ là metadata giả định, tuyệt đối không đưa bytes của khóa hoặc secret vào manifest:

~~~json
{
  "keyId": "payments-data-kek",
  "keyVersion": "v4",
  "fingerprint": "sha256:example-fingerprint",
  "copyType": "wrapped-key-backup",
  "backupSet": "dr-archive-2026-04",
  "location": "object-store/archive-region-b",
  "retentionUntil": "2027-04-30",
  "deletionState": "pending-review",
  "owner": "payments-platform"
}
~~~

## 5. Xác định phạm vi và điều kiện được phép xóa

Trước khi gỡ key khỏi backup, xác nhận:

1. **Đúng khóa và phiên bản:** key ID, version và fingerprint khớp với yêu cầu.
2. **Đúng bản sao:** backup set, snapshot, media ID, object version hoặc HSM package được nhận diện rõ.
3. **Không còn phụ thuộc hợp lệ:** không có dữ liệu, chữ ký, bản backup hoặc quy trình DR còn cần bản sao đó.
4. **Đã kiểm tra yêu cầu lưu giữ:** retention policy, legal hold, hợp đồng, nghĩa vụ kiểm toán và yêu cầu điều tra cho phép xóa.
5. **Có phê duyệt:** key owner, data owner, backup custodian và người phê duyệt destruction đã xác nhận phạm vi.
6. **Có phương án xử lý bản không thể xóa ngay:** biết thời điểm hết hạn, cách ly hoặc phương án crypto-erasure được phê duyệt.

Không xóa nếu key ID/version mơ hồ, inventory chưa đầy đủ, đang có legal hold, chưa xác định được dữ liệu phụ thuộc hoặc chưa có quyền phê duyệt. Với khóa bị compromise, phối hợp quy trình incident response để ngăn sử dụng ngay; việc xử lý bản backup phải bảo toàn bằng chứng cần thiết và không vô tình làm hỏng điều tra.

## 6. Kiểm tra dữ liệu còn phụ thuộc vào key

Đây là bước quan trọng nhất để tránh làm mất dữ liệu hợp lệ. Với mỗi key version, xác định tất cả ciphertext, DEK đã bọc, bản backup dữ liệu, archive, snapshot và chữ ký còn phụ thuộc.

Trong envelope encryption:

1. Ứng dụng mã hóa dữ liệu bằng DEK.
2. DEK được bọc bằng KEK trong KMS/HSM.
3. Ciphertext và DEK đã bọc có thể được lưu trong database backup.
4. Khi restore, hệ thống cần đúng KEK version và context để unwrap DEK.

Nếu xóa bản sao KEK khỏi backup mà khóa gốc trong KMS vẫn sẵn sàng, khả năng giải mã có thể vẫn còn. Nếu hủy KEK gốc và mọi backup/replica của nó, DEK đã bọc có thể không còn mở được. Trước khi hủy, phải biết bản backup dữ liệu nào còn cần DEK đó.

~~~mermaid
flowchart TD
    A["Backup dữ liệu"] --> B["Ciphertext"]
    A --> C["DEK đã bọc"]
    C --> D["KEK và phiên bản tương ứng"]
    D --> E["KMS/HSM hoặc bản backup key"]
    E --> F["Khả năng unwrap DEK"]
    F --> G["Khả năng giải mã dữ liệu"]
    H["Xóa key copy khỏi backup"] --> E
~~~

Danh mục phụ thuộc nên ghi tối thiểu key ID, version, thuật toán, mục đích, thời gian dữ liệu được tạo, nơi lưu ciphertext, trạng thái migration và ngày hết hạn lưu trữ. Không chỉ kiểm tra dữ liệu đang hoạt động; snapshot cũ, backup bất biến và archive dài hạn cũng có thể cần khóa.

## 7. Chọn phương pháp xóa phù hợp với phương tiện

Không có một lệnh xóa duy nhất áp dụng cho mọi loại backup. Cần chọn phương pháp theo loại storage, tính năng retention và khả năng kiểm soát của tổ chức.

| Loại phương tiện | Phương pháp thường dùng | Điều cần xác minh |
|---|---|---|
| File backup trên filesystem | Xóa object/file, sau đó xử lý snapshot, bản sao và phương tiện chứa file theo chính sách | File có hard link, bản snapshot, journal, bản copy hoặc backup khác không? |
| Object storage có versioning | Xóa đúng object version và xử lý delete marker, noncurrent versions, soft delete | Xóa phiên bản hiện hành có để lại phiên bản cũ không? |
| Database/VM snapshot | Xóa snapshot theo API và xử lý snapshot clone hoặc image dẫn xuất | Snapshot có được giữ trong chuỗi incremental hoặc replication không? |
| Backup bất biến/WORM | Chờ hết retention, dùng ngoại lệ được kiểm soát nếu nền tảng hỗ trợ | Có được phép xóa trước hạn không? Ai phê duyệt và audit thế nào? |
| Băng từ hoặc removable media | Thu hồi, xóa an toàn hoặc tiêu hủy phương tiện theo quy trình media sanitization | Có thể xóa chọn lọc không? Nếu không, phải xử lý cả media và bản sao. |
| HSM backup blob | Dùng quy trình quản lý backup chính thức, xóa gói và bản sao theo hướng dẫn thiết bị | Blob, quorum, domain backup key hoặc recovery shares còn ở đâu? |
| Cloud-managed backup | Dùng chức năng xóa/retention của nhà cung cấp và kiểm tra semantics của dịch vụ | Xóa có bất đồng bộ không? Có soft delete, vault lock hoặc bản sao do provider giữ không? |

Với SSD, flash storage và storage phân tán, ghi đè file không nhất thiết xóa mọi bản vật lý do wear leveling, copy-on-write hoặc cơ chế snapshot. Sử dụng chức năng sanitize/crypto-erase phù hợp với thiết bị và chính sách đã phê duyệt; khi không thể xác minh xóa chọn lọc, xử lý cả phương tiện theo quy trình hủy media.

## 8. Xử lý backup bất biến và bản sao không thể xóa chọn lọc

Backup bất biến được thiết kế để ngăn sửa hoặc xóa trong thời gian retention. Điều này hữu ích chống ransomware và phá hoại, nhưng có nghĩa tổ chức có thể không xóa riêng một key copy trước hạn.

Các lựa chọn cần được đánh giá:

- **Chờ retention hết hạn:** đánh dấu bản sao cần xóa, hạn chế truy cập, theo dõi ngày hết hạn và xác minh xóa sau khi hệ thống tự purge.
- **Ngoại lệ được nhà cung cấp hỗ trợ:** chỉ dùng nếu chính sách và hợp đồng cho phép; cần phê duyệt nhiều bên và audit đầy đủ.
- **Cách ly bản backup:** ngăn restore hoặc truy cập thông thường trong thời gian chờ hết hạn, với kiểm soát đặc biệt đối với người có quyền quản trị.
- **Crypto-erasure:** nếu backup được mã hóa bằng một khóa riêng dành riêng cho backup set, có thể hủy khóa đó để làm dữ liệu không thể giải mã. Phải xác nhận không có bản sao khóa và không ảnh hưởng dữ liệu khác.
- **Hủy phương tiện khi được phép:** với media offline, thực hiện quy trình tiêu hủy hoặc sanitize có chứng từ.

Không tìm cách phá retention lock hoặc sửa trực tiếp cấu trúc backup bất biến. Nếu khóa nằm trong backup có retention chưa hết hạn, ghi rõ ngoại lệ và ngày xử lý dự kiến; báo cáo rằng bản sao vẫn tồn tại và được kiểm soát cho đến thời điểm đó.

## 9. Crypto-erasure bằng khóa riêng cho backup

Crypto-erasure có thể hữu ích khi không thể xóa từng block dữ liệu trong một backup lớn. Cách thiết kế an toàn thường là mã hóa backup bằng một khóa bảo vệ riêng (backup wrapping key hoặc backup encryption key) dành cho một backup set hoặc một phạm vi dữ liệu rõ ràng.

Quy trình khái quát:

1. Backup được mã hóa bằng khóa riêng của backup set.
2. Khóa này được quản lý độc lập với khóa dùng cho dữ liệu đang hoạt động.
3. Danh mục ghi nhận chính xác backup set nào phụ thuộc vào khóa đó.
4. Sau khi retention, legal hold và nhu cầu restore kết thúc, người có thẩm quyền phê duyệt hủy khóa backup.
5. Xác minh mọi bản sao và đường phục hồi của khóa đã bị loại bỏ.
6. Giữ metadata và bằng chứng hủy mà không giữ lại vật liệu bí mật.

Không dùng chung một backup key cho các tập dữ liệu có thời hạn lưu giữ hoặc yêu cầu xóa khác nhau nếu mục tiêu là crypto-erase riêng từng tập. Nếu một KEK dùng chung cho cả production lẫn backup, hủy KEK có thể làm gián đoạn dữ liệu đang hoạt động. Nếu key backup được bọc bởi một recovery key khác, phải xem xét cả chuỗi khóa: hủy lớp ngoài chưa chắc làm mất mọi bản sao nếu vẫn còn một bản export dạng rõ hoặc một bản đã bọc bởi khóa khác.

Crypto-erasure không thể được tuyên bố chỉ vì key object đã bị xóa khỏi một KMS. Cần xác nhận bản sao ở HSM, backup, escrow, replica, cache và các recovery package không còn cung cấp đường khôi phục.

## 10. Xử lý wrapped key, HSM blob và recovery shares

Vật liệu khóa đã được bọc vẫn cần được kiểm soát. Kẻ tấn công có thể tìm cách lấy cả wrapped blob lẫn khóa bảo vệ nó hoặc lợi dụng một quy trình restore được cấp quyền quá rộng.

- **Wrapped DEK:** tìm mọi bản sao blob, metadata và KEK version cần để mở. Xóa blob khỏi backup nếu mục tiêu là loại bỏ bản sao đó; nếu muốn crypto-erase dữ liệu, phải xử lý cả khả năng khôi phục KEK.
- **Wrapped private key:** gỡ các gói chứa khóa riêng khỏi backup, kho artifact và bản sao offline theo phạm vi được phê duyệt. Giữ certificate/public key nếu cần xác minh chữ ký.
- **HSM backup blob:** xử lý cả bản sao blob và quyền/quorum có thể restore nó. Một blob đã xóa khỏi catalog vẫn có thể còn trên media hoặc bản sao vùng khác.
- **M-of-N recovery shares:** kiểm kê từng share, bản sao, người giữ và phương tiện. Nếu mục tiêu là làm mất khả năng khôi phục, phải bảo đảm số share còn có thể tập hợp thấp hơn ngưỡng M; việc mất một share không đủ nếu vẫn còn ít nhất M share hợp lệ.
- **Key package của nhà cung cấp:** xác minh trạng thái xóa, retention và bản sao được quản lý bởi dịch vụ; lưu xác nhận theo cơ chế audit của provider.

Không ghi share, PIN, passphrase hoặc nội dung key package vào ticket hay log để chứng minh đã xóa. Dùng định danh, fingerprint, serial, version và mã giao dịch đã được phân loại phù hợp.

## 11. Thực hiện xóa theo quy trình có kiểm soát

Một quy trình vận hành nên có các bước tuần tự:

1. **Mở yêu cầu:** ghi mục đích xóa, key ID/version, backup set và chủ sở hữu.
2. **Xác minh danh tính:** người yêu cầu, người phê duyệt và custodian phải được xác thực.
3. **Đánh giá phụ thuộc:** kiểm tra ciphertext, archive, restore test, retention và legal hold.
4. **Chốt phương pháp:** xóa object, purge version, sanitize media, chờ retention hoặc crypto-erase.
5. **Thực hiện theo phạm vi:** thao tác trên đúng object/media/version đã duyệt; tránh wildcard hoặc lệnh xóa hàng loạt thiếu ràng buộc.
6. **Kiểm tra kết quả:** tìm lại theo key ID/fingerprint, kiểm tra version, replica, snapshot và trạng thái provider.
7. **Đánh giá khả năng khôi phục:** thực hiện kiểm tra được phê duyệt trên bản thử nghiệm hoặc bản sao cô lập để xác nhận đường restore không còn hiệu lực theo mục tiêu.
8. **Ghi bằng chứng:** lưu người thực hiện, người phê duyệt, thời gian, phương thức, kết quả và ngoại lệ.
9. **Cập nhật inventory:** đánh dấu từng bản sao đã xóa, chờ retention, không thể xác minh hoặc được phép giữ lại.

~~~mermaid
flowchart TD
    A["Yêu cầu xóa key khỏi backup"] --> B["Xác minh key ID, version và backup set"]
    B --> C["Kiểm tra phụ thuộc, retention và legal hold"]
    C --> D{"Được phép xóa?"}
    D -- "Không" --> E["Cách ly hoặc chờ hết retention"]
    D -- "Có" --> F["Chọn xóa object, sanitize hoặc crypto-erasure"]
    F --> G["Xử lý mọi replica và bản sao"]
    G --> H["Xác minh không còn đường restore"]
    H --> I["Ghi audit và cập nhật inventory"]
~~~

## 12. Phân quyền và kiểm soát hai người

Xóa key khỏi backup có thể làm mất khả năng khôi phục dữ liệu hoặc danh tính mật mã. Vì vậy, quyền xóa cần được giới hạn và tách biệt:

- Người yêu cầu mô tả lý do, phạm vi và thời hạn.
- Key owner xác nhận đúng key ID/version và trạng thái vòng đời.
- Data owner xác nhận dữ liệu không còn phụ thuộc hoặc đã có phương án thay thế.
- Backup custodian xác nhận vị trí và khả năng xóa trên từng phương tiện.
- Người phê duyệt destruction cho phép thực hiện theo chính sách.
- Người thực hiện chỉ có quyền thao tác trên phạm vi đã phê duyệt.
- Auditor hoặc người rà soát độc lập kiểm tra bằng chứng sau thao tác.

Với khóa gốc, khóa CA, khóa ký quan trọng hoặc backup HSM, cân nhắc dual control hoặc M-of-N. Không để cùng một người vừa yêu cầu, phê duyệt, thực hiện và tự xác nhận kết quả xóa. Cơ chế khẩn cấp vẫn phải ghi nhận đầy đủ và được rà soát sau đó.

## 13. Kiểm tra xóa thành công

Thông báo “delete accepted” từ API chưa chắc đồng nghĩa dữ liệu đã bị xóa vật lý hoặc mọi phiên bản đã biến mất. Cần xác định mức xác minh phù hợp với phương tiện:

| Mức kiểm tra | Bằng chứng |
|---|---|
| Kiểm tra catalog | Không còn entry trong catalog hoặc key reference thuộc phạm vi xóa. |
| Kiểm tra object/version | API liệt kê không còn object/version cần xóa; delete marker và noncurrent version đã được xử lý. |
| Kiểm tra replication/snapshot | Không còn bản sao trong vùng, account, snapshot hoặc vault thuộc phạm vi quản lý. |
| Kiểm tra media | Có kết quả sanitize hoặc chứng từ tiêu hủy theo chính sách phương tiện. |
| Kiểm tra khả năng restore | Quy trình khôi phục thử không thể lấy lại bản sao đã xóa từ backup target; nếu khóa gốc được giữ riêng, xác minh đường truy cập đó vẫn tách biệt và đúng quyền. Thử nghiệm được thực hiện trong môi trường cô lập và có phê duyệt. |
| Kiểm tra provider | Có trạng thái purge/retention hoàn tất hoặc xác nhận của nhà cung cấp theo semantics dịch vụ. |

Với crypto-erasure, bằng chứng phải cho thấy khóa bảo vệ duy nhất và mọi đường khôi phục của nó đã bị hủy. Một thử nghiệm giải mã thất bại đơn lẻ có thể do sai quyền hoặc lỗi dịch vụ; cần kết hợp kiểm kê, trạng thái key lifecycle và kiểm thử có kiểm soát để kết luận.

Không cố khôi phục khóa đã hủy chỉ để chứng minh nó không thể khôi phục. Hãy dùng bản thử nghiệm, mô phỏng hoặc phương pháp xác minh được nhà cung cấp và chính sách chấp thuận.

## 14. Lưu bằng chứng và audit trail

Bằng chứng cần đủ để kiểm toán lại quyết định và hành động, nhưng không được tạo thêm bản sao của bí mật. Một bản ghi destruction có thể gồm:

- Request ID, lý do, thời gian yêu cầu và thời gian thực hiện.
- Key ID, version, fingerprint hoặc serial đã được phê duyệt.
- Danh sách backup set, object version, media ID, replica và location đã kiểm tra.
- Người yêu cầu, key owner, data owner, người phê duyệt và người thực hiện.
- Phương pháp xóa, công cụ/API, mã giao dịch và kết quả trả về.
- Kết quả kiểm tra version, snapshot, retention, replica và khả năng restore.
- Các bản sao chưa thể xóa, lý do, người chịu trách nhiệm và ngày xử lý tiếp theo.
- Liên kết đến audit log bất biến và biên bản kiểm tra độc lập.

Không lưu vật liệu khóa, password, PIN, recovery share hoặc secret trong bản ghi. Fingerprint và key ID cũng cần được phân loại theo chính sách vì chúng có thể tiết lộ cấu trúc hệ thống hoặc liên kết các hoạt động.

## 15. Quản lý bản sao chưa thể xóa

Một số bản backup không thể xóa ngay do WORM, retention lock, media offline hoặc nhà cung cấp giữ theo chu kỳ. Trong trường hợp đó:

1. Ghi rõ vị trí, số lượng bản sao và thời điểm hết hạn.
2. Giới hạn quyền đọc, restore, export và quyền thay đổi retention.
3. Cách ly backup khỏi đường vận hành thông thường; cảnh báo khi có truy cập.
4. Đánh dấu key version là pending destruction hoặc prohibited for restore trong inventory phù hợp.
5. Nếu có cơ chế crypto-erasure được phê duyệt, xác minh khóa bảo vệ dành riêng cho backup set và mọi bản sao của khóa đó.
6. Lập lịch kiểm tra lại sau khi retention kết thúc và lưu bằng chứng purge.

Không tuyên bố “đã xóa hoàn toàn” nếu còn bản sao đang chờ retention hoặc không có quyền kiểm tra. Báo cáo cần phân biệt các trạng thái **DELETED**, **CRYPTO_ERASED**, **PENDING_RETENTION**, **MEDIA_DESTROYED**, **PROVIDER_PURGE_PENDING** và **UNVERIFIED** theo trạng thái thực tế.

## 16. Những tình huống cần xử lý khác nhau

| Tình huống | Hướng xử lý |
|---|---|
| Khóa đã được thay thế, dữ liệu cũ vẫn cần giải mã | Giữ đường giải mã được kiểm soát cho phiên bản cũ; xóa các bản sao dư thừa theo retention và chính sách. |
| Bản backup key hết thời hạn lưu giữ | Xác minh không còn phụ thuộc, phê duyệt và xóa toàn bộ bản sao thuộc phạm vi. |
| Key bị compromise | Cô lập và xử lý incident; bảo toàn bằng chứng cần thiết, ngăn restore bản sao bị lộ và thay thế khóa theo kế hoạch. |
| Backup immutable chưa hết retention | Cách ly, hạn chế truy cập, ghi nhận ngày purge; dùng ngoại lệ hoặc crypto-erasure chỉ khi được phép. |
| Một bản HSM backup blob không còn dùng | Xóa blob, bản sao và recovery shares liên quan theo quy trình HSM; xác minh không còn bản restore hợp lệ. |
| Chỉ có wrapped DEK trong backup dữ liệu | Xác định KEK/version cần để unwrap; không xóa KEK dùng chung nếu dữ liệu khác vẫn phụ thuộc. |
| Private key đã hết hạn nhưng chữ ký cũ còn cần xác minh | Có thể xóa bản sao private key theo chính sách sau khi xác nhận; giữ public key, certificate và trust evidence cần thiết. |
| Bản sao ở nhà cung cấp không có API xóa tức thời | Ghi nhận semantics, retention và xác nhận provider; giữ trạng thái pending cho đến khi có bằng chứng hoàn tất. |

## 17. Ví dụ: xóa bản backup của private key đã ngừng sử dụng

Một dịch vụ ký phần mềm đã chuyển sang key pair mới. Private key cũ từng được backup dưới dạng gói mã hóa trong kho lưu trữ offline. Chữ ký cũ vẫn cần xác minh trong thời hạn lưu trữ.

Quy trình có thể thực hiện:

1. Xác định key ID/version cũ, fingerprint, HSM package và tất cả media chứa gói backup.
2. Xác nhận khóa cũ không còn được dùng để ký mới và không còn yêu cầu khôi phục để tiếp tục danh tính ký.
3. Kiểm tra chính sách lưu giữ, yêu cầu pháp lý và nhu cầu điều tra.
4. Xác nhận certificate, public key, certificate chain và dữ liệu xác minh chữ ký cũ được lưu riêng.
5. Xin phê duyệt từ key owner, chủ sở hữu phần mềm và backup custodian.
6. Xóa các gói backup và bản sao thuộc phạm vi; xử lý media theo chính sách nếu không thể xóa chọn lọc.
7. Kiểm tra catalog, offline inventory và quy trình restore thử nghiệm.
8. Lưu bằng chứng xóa private key copy; giữ public verification material theo thời hạn cần thiết.

Ví dụ này cho thấy việc xóa private key khỏi backup không nhất thiết yêu cầu xóa certificate hoặc public key. Hai loại vật liệu có vai trò và yêu cầu bảo mật khác nhau.

## 18. Ví dụ: crypto-erasure một backup set

Một hệ thống lưu trữ đã mã hóa các backup hàng tháng bằng một backup KEK riêng cho từng năm. Dữ liệu của năm 2022 đã hết thời hạn lưu giữ, không còn legal hold và chủ sở hữu dữ liệu xác nhận có thể hủy.

Nhóm vận hành cần:

- Xác nhận backup set 2022 chỉ phụ thuộc vào backup KEK tương ứng.
- Kiểm tra không có dữ liệu năm khác hoặc môi trường production dùng chung KEK.
- Kiểm kê mọi bản sao KEK, bản export, wrapped copy, recovery package và escrow.
- Phê duyệt hủy khóa theo dual control.
- Hủy khóa và mọi đường recovery được hỗ trợ.
- Kiểm tra backup 2022 không thể giải mã trong môi trường thử nghiệm có kiểm soát; đồng thời xác nhận backup các năm khác vẫn hoạt động.
- Lưu audit và cập nhật inventory thành **CRYPTO_ERASED**.

Nếu backup KEK dùng chung với dữ liệu năm 2023 hoặc dữ liệu production, không được hủy khóa đó trong thao tác này. Cần thiết kế lại phạm vi khóa hoặc thực hiện re-encrypt/rewrap để tách các tập dữ liệu trước khi crypto-erase.

## 19. Các lỗi thường gặp

- Xóa object hiện hành nhưng bỏ sót object version cũ hoặc delete marker.
- Xóa entry trong catalog nhưng bản backup vẫn còn trên media.
- Xóa key alias mà không hủy key material hoặc backup blob tương ứng.
- Hủy KEK dùng chung làm mất khả năng giải mã dữ liệu vẫn còn thời hạn lưu.
- Cho rằng wrapped key không nhạy cảm và bỏ qua nó khỏi inventory.
- Xóa một recovery share nhưng vẫn còn đủ M share để phục hồi.
- Bỏ qua snapshot, replica, escrow, bản sao offline hoặc bản do provider quản lý.
- Tuyên bố crypto-erasure dù còn một bản export hoặc khóa bọc có thể mở dữ liệu.
- Không kiểm tra legal hold, dẫn đến xóa bằng chứng hoặc dữ liệu phải lưu.
- Ghi key bytes hoặc recovery share vào log để chứng minh đã xóa.
- Không ghi nhận bản sao chưa thể xóa và ngày cần xử lý lại.
- Chỉ kiểm tra API trả về thành công mà không xác minh trạng thái cuối cùng.

## 20. Checklist xóa key khỏi backup

Trước khi đóng yêu cầu, xác nhận:

- [ ] Đã xác định chính xác key ID, version, fingerprint và mục tiêu xóa.
- [ ] Đã phân biệt xóa bản sao khỏi backup với hủy toàn bộ khóa hoặc crypto-erasure.
- [ ] Đã kiểm kê backup full/incremental, snapshot, version, replica, offline media, escrow và HSM blob.
- [ ] Đã xác định wrapped key, recovery shares và mọi khóa bảo vệ có liên quan.
- [ ] Đã lập bản đồ ciphertext, DEK, KEK và dữ liệu còn phụ thuộc.
- [ ] Đã kiểm tra retention, legal hold, hợp đồng và yêu cầu điều tra.
- [ ] Đã có phê duyệt của key owner, data owner và backup custodian.
- [ ] Đã chọn phương pháp xóa phù hợp với filesystem, object storage, snapshot, WORM hoặc media.
- [ ] Đã xác minh không ảnh hưởng khóa dùng chung hoặc dữ liệu khác.
- [ ] Đã xử lý mọi replica, version, soft delete và bản sao provider theo semantics thực tế.
- [ ] Đã kiểm tra khả năng restore bằng phương pháp được phê duyệt.
- [ ] Đã ghi nhận các bản sao đang chờ retention hoặc chưa xác minh.
- [ ] Đã lưu audit trail không chứa vật liệu khóa hoặc recovery secret.
- [ ] Đã cập nhật inventory và lên lịch kiểm tra lại nếu còn bản sao chờ xử lý.

Chỉ kết luận đã xóa hoàn tất khi phạm vi được xác định rõ, mọi bản sao thuộc phạm vi đã được xử lý theo phương pháp phù hợp và có bằng chứng kiểm tra. Nếu còn bản sao do retention hoặc nhà cung cấp giữ, báo cáo đúng trạng thái và thời điểm xử lý tiếp theo. Cách làm này bảo vệ khả năng khôi phục hợp lệ trong khi giảm nguy cơ khóa cũ bị lộ hoặc bị tái sử dụng ngoài ý muốn.
