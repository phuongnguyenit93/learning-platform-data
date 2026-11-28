# Cập nhật inventory sau revocation

Khi một khóa mật mã bị thu hồi (*revocation*), hệ thống phải cập nhật inventory để mọi thành phần liên quan biết khóa đó còn được phép thực hiện thao tác nào, từ thời điểm nào và vì lý do gì. Nếu chỉ tắt khóa trong KMS mà không cập nhật inventory, các ứng dụng vẫn có thể giữ tham chiếu cũ, bộ nhớ đệm có thể tiếp tục dùng chính sách trước đó, còn nhóm vận hành khó xác định dữ liệu nào đang phụ thuộc vào khóa đã thu hồi. Ngược lại, nếu chỉ đổi trạng thái trong inventory nhưng khóa vẫn được phép sử dụng ở KMS/HSM, bản ghi quản trị sẽ tạo ra cảm giác an toàn giả.

Inventory khóa là danh mục có kiểm soát về danh tính, trạng thái, chủ sở hữu, mục đích, vị trí quản lý và các quan hệ phụ thuộc của từng khóa hoặc từng phiên bản khóa. Inventory không phải nơi lưu key material. Private key, symmetric key, DEK, seed, mật khẩu mở khóa hay thông tin bí mật có khả năng tái tạo khóa không được ghi vào bản ghi inventory.

## 1. Revocation làm thay đổi điều gì?

Revocation là hành động ngăn một khóa tiếp tục được tin cậy hoặc được sử dụng theo một chính sách đã xác định. Phạm vi thu hồi phải rõ ràng: toàn bộ khóa logic, một phiên bản cụ thể, chứng thư số gắn với public key, một mục đích sử dụng, hay một danh tính được phép gọi khóa. Ví dụ, thu hồi phiên bản `v7` của một KEK không đồng nghĩa phải thu hồi `v8` nếu `v8` đã được tạo độc lập và không bị ảnh hưởng.

Việc thu hồi có thể xuất phát từ nhiều nguyên nhân:

- Khóa hết thời hạn sử dụng hoặc đến lịch thay thế theo cryptoperiod.
- Khóa không còn cần thiết vì dịch vụ hoặc dữ liệu đã ngừng hoạt động.
- Khóa bị lộ, nghi bị lộ, bị sao chép trái phép hoặc quyền truy cập vào khóa bị xâm phạm.
- Khóa được tạo, cấp phát hoặc cấu hình sai; thuật toán hay tham số không còn đáp ứng chính sách.
- Chủ thể, chứng thư hoặc quan hệ tin cậy liên quan không còn hợp lệ.

Không nên gom mọi nguyên nhân vào một trạng thái chung mà không lưu lý do. Thu hồi theo lịch thường cho phép lập kế hoạch chuyển đổi và có thể giữ quyền giải mã có kiểm soát đối với dữ liệu cũ. Thu hồi do compromise cần phản ứng khẩn cấp; tùy loại khóa và mức độ ảnh hưởng, cả mã hóa, giải mã, ký hoặc xác minh đều có thể phải bị chặn hay đánh giá lại. Một khóa bị compromise không tự động trở thành an toàn chỉ vì inventory đã ghi `REVOKED`.

Trạng thái thu hồi cũng không đồng nghĩa với xóa khóa. Ciphertext được tạo trước đó có thể vẫn tồn tại trong cơ sở dữ liệu, bản sao lưu, kho lưu trữ hoặc thiết bị người dùng. Chứng thư bị thu hồi không làm biến mất chữ ký đã tạo; việc chữ ký cũ còn được chấp nhận hay không phụ thuộc thời điểm ký, bằng chứng thời gian, trạng thái chứng thư tại thời điểm đó và chính sách xác minh. Vì vậy inventory phải mô tả riêng trạng thái vòng đời, quyền thao tác và tình trạng vật liệu khóa.

## 2. Những thông tin cần cập nhật trong inventory

Mỗi bản ghi nên có định danh ổn định cho khóa logic và định danh riêng cho phiên bản. Không dùng alias có thể đổi tên làm định danh duy nhất, vì alias có thể trỏ sang phiên bản khác sau một lần rotation. Với khóa bất đối xứng hoặc chứng thư, có thể lưu fingerprint, key identifier, subject hoặc serial number của chứng thư để đối chiếu; không lưu private key.

Các nhóm trường thường cần có gồm:

| Nhóm | Trường nên quản lý | Mục đích |
|---|---|---|
| Định danh | `key_id`, `version`, fingerprint hoặc certificate serial | Xác định chính xác khóa và phạm vi thu hồi |
| Phân loại | Thuật toán, kích thước/tham số, loại khóa, mục đích sử dụng | Biết khóa dùng cho mã hóa, ký, xác minh hay dẫn xuất khóa |
| Quản trị | Owner, custodian, ứng dụng/dịch vụ chịu trách nhiệm | Xác định người xử lý và người phê duyệt |
| Vị trí | KMS/HSM, cloud account, region, key store hoặc CA | Xác định nơi cần áp dụng lệnh thu hồi |
| Vòng đời | Created, activated, cryptoperiod, revoked, destroyed timestamps | Theo dõi các mốc và trạng thái vòng đời |
| Quyền thao tác | Cho phép/chặn encrypt, decrypt, sign, verify, wrap hoặc unwrap | Biểu diễn chính sách sử dụng sau thu hồi |
| Sự kiện | Event ID, lý do, người thực hiện, thời điểm hiệu lực, ticket/incident | Giải thích và kiểm toán thay đổi |
| Phụ thuộc | Khóa thay thế, DEK được bọc, chứng thư, workload và tập dữ liệu liên quan | Lập kế hoạch chuyển đổi và đánh giá ảnh hưởng |
| Kiểm soát | Phiên bản bản ghi, nguồn sự kiện, lần đồng bộ gần nhất, xác nhận từ provider | Phát hiện dữ liệu cũ hoặc cập nhật chưa hoàn tất |

Không phải hệ thống nào cũng cần mọi trường trong cùng một bảng. Có thể tách inventory thành các thực thể khóa, phiên bản, chứng thư, sự kiện vòng đời và quan hệ phụ thuộc. Điều quan trọng là có thể truy vấn từ một khóa đã thu hồi đến các workload và dữ liệu chịu ảnh hưởng, đồng thời truy ngược từ một đối tượng được bảo vệ đến đúng phiên bản khóa đã dùng.

Trạng thái cần được định nghĩa rõ trong quy ước của tổ chức. Một tập trạng thái tham khảo:

| Trạng thái | Ý nghĩa |
|---|---|
| `ACTIVE` | Đang được phép sử dụng theo chính sách hiện hành |
| `REVOCATION_PENDING` | Đã nhận yêu cầu thu hồi nhưng các bước chặn và đồng bộ chưa hoàn tất |
| `DECRYPT_ONLY` | Không được mã hóa dữ liệu mới; chỉ được giải mã dữ liệu cũ theo quyền hạn được duyệt |
| `REVOKED` | Đã thu hồi theo chính sách; các thao tác bị cấm được chặn tại nơi thực thi |
| `COMPROMISED` | Có bằng chứng hoặc nghi vấn đáng tin cậy rằng bí mật hay quyền kiểm soát khóa đã bị xâm phạm |
| `DESTROY_PENDING` | Đang chờ đáp ứng điều kiện trước khi hủy vật liệu khóa |
| `DESTROYED` | Vật liệu khóa đã được hủy và có bằng chứng xác nhận phù hợp |

Đây là ví dụ về từ vựng trạng thái, không phải một state machine bắt buộc cho mọi nền tảng. Một số hệ thống nên quản lý riêng `lifecycle_state`, `compromise_status`, `material_status` và `usage_policy`. Cách tách này tránh việc một nhãn duy nhất phải diễn đạt nhiều sự thật khác nhau. Ví dụ, khóa có thể đã bị thu hồi để mã hóa dữ liệu mới nhưng vẫn được phép giải mã có kiểm soát trong thời gian di chuyển dữ liệu.

## 3. Quy trình cập nhật sau khi thu hồi

### Bước 1: Ghi nhận sự kiện và xác định phạm vi

Tiếp nhận yêu cầu từ quy trình rotation, chủ sở hữu khóa, hệ thống giám sát, KMS/HSM, PKI hoặc quy trình ứng phó sự cố. Mỗi yêu cầu cần có mã sự kiện duy nhất, người hoặc hệ thống khởi tạo, lý do, thời điểm phát hiện và thời điểm hiệu lực. Nếu là sự cố compromise, ghi cả mức độ tin cậy của phát hiện và mã incident để liên kết với bằng chứng điều tra.

Trước khi thay đổi inventory, xác định chính xác `key_id` và `version`, provider đang quản lý khóa, các alias trỏ đến khóa, chứng thư liên quan và phạm vi workload. Không suy ra phiên bản chỉ từ tên alias. Nếu sự kiện chỉ áp dụng cho một phiên bản, việc đánh dấu toàn bộ các phiên bản là thu hồi có thể làm gián đoạn dịch vụ không cần thiết; nếu phạm vi không rõ, cần xử lý như một sự kiện chưa được phân loại và chuyển cho người có thẩm quyền xác nhận.

### Bước 2: Chặn thao tác tại nơi thực thi

Áp dụng lệnh disable, revoke hoặc policy deny tại KMS/HSM, CA/PKI, dịch vụ quản lý khóa và lớp phân quyền đang thực thi thao tác. Với sự cố compromise, ưu tiên giảm ngay khả năng tiếp tục sử dụng khóa và thu hồi các quyền truy cập hoặc credential có liên quan. Việc đổi inventory đơn thuần không chặn được một ứng dụng đang gọi trực tiếp provider.

Phải xác định riêng từng thao tác. Với khóa mã hóa đối xứng, cần xem xét `encrypt`, `decrypt`, `wrap` và `unwrap`. Với khóa ký, cần chặn `sign`; quyền `verify` đối với chữ ký lịch sử phải theo chính sách tin cậy và bằng chứng thời gian. Với khóa mã hóa bất đối xứng, chặn mã hóa bằng public key đã bị thay thế có thể khác với việc giữ quyền giải mã bằng private key cũ. Khi private key bị compromise, cho phép giải mã tiếp có thể làm tăng rủi ro và phải có quyết định ứng phó rõ ràng.

Nếu provider không phản hồi hoặc không thể xác nhận lệnh chặn, bản ghi phải thể hiện trạng thái chưa hoàn tất, ví dụ `REVOCATION_PENDING`, cùng lỗi và lần thử gần nhất. Không ghi nhận `REVOKED` như thể đã chặn thành công khi chưa có xác nhận. Trong thời gian chưa xác định được trạng thái thực thi, hệ thống gọi khóa cần có chính sách fail closed phù hợp với mức độ rủi ro.

### Bước 3: Cập nhật inventory bằng sự kiện có thể kiểm toán

Sau khi gửi lệnh chặn, cập nhật bản ghi đúng phiên bản. Lưu trạng thái trước và sau, thời điểm hiệu lực, lý do, actor, event ID, provider response hoặc mã tham chiếu xác nhận, và liên kết đến ticket/incident. Giữ lịch sử thay đổi bất biến hoặc chỉ cho phép bổ sung sự kiện; không xóa dấu vết trạng thái cũ bằng cách ghi đè không kiểm soát.

Ví dụ một bản ghi inventory cho phiên bản KEK đã bị thu hồi do nghi ngờ compromise:

```yaml
key_id: customer-data-kek
version: "v7"
key_type: symmetric
algorithm: AES-256
purpose: envelope-encryption
provider:
  type: cloud-kms
  key_reference: customer-data-kek-v7
lifecycle_state: COMPROMISED
usage_policy:
  encrypt: DENY
  decrypt: DENY
  wrap: DENY
  unwrap: DENY
revocation:
  event_id: INC-2026-0418-KEY-02
  reason: suspected-key-compromise
  effective_at: "2026-11-28T02:15:00Z"
  actor: security-incident-response
  provider_confirmation: "disable-operation-accepted"
replacement:
  key_id: customer-data-kek
  version: "v8"
dependencies:
  wrapped_dek_inventory: customer-data-dek-references
  migration_status: investigation-required
```

Các giá trị trên chỉ minh họa cấu trúc và không đại diện cho một hệ thống thật. `key_reference` phải là định danh không bí mật do provider cấp. Không đưa key material, credential, token truy cập hoặc nội dung dữ liệu nhạy cảm vào YAML hay log. Nếu trạng thái provider mới chỉ là “đã nhận yêu cầu”, phải ghi rõ mức xác nhận đó và tiếp tục kiểm tra trạng thái thực tế.

### Bước 4: Cập nhật các hệ thống phụ thuộc

Inventory thường là một nguồn dữ liệu quản trị, trong khi quyết định cho phép thao tác còn được áp dụng ở nhiều nơi: KMS/HSM, dịch vụ cấp chứng thư, policy engine, secret/configuration service, workload, cache và hệ thống xác minh chữ ký. Phát sự kiện thu hồi tới các thành phần cần biết, ghi nhận kết quả từng nơi và theo dõi các thành phần chưa xác nhận.

Nếu hệ thống dùng cache cho key metadata hoặc authorization, phải xác định thời hạn cache, cơ chế invalidation và cách xử lý khi không nhận được sự kiện. Một cache còn giữ trạng thái `ACTIVE` có thể khiến yêu cầu sử dụng khóa vẫn được gửi đi. Với thao tác nhạy cảm, provider cần là điểm kiểm soát cuối cùng; ứng dụng không được xem bản sao inventory cũ là quyền cho phép vĩnh viễn.

### Bước 5: Lập bản đồ ảnh hưởng và di chuyển dữ liệu

Truy vấn các quan hệ phụ thuộc để tìm dữ liệu, workload, chứng thư, bản sao lưu, bản sao vùng, thiết bị ngoại tuyến hoặc quy trình batch đang dùng phiên bản bị thu hồi. Với envelope encryption, inventory nên cho phép xác định DEK nào được bọc bởi KEK nào. Nếu chỉ KEK bị thay thế và DEK vẫn an toàn, có thể xem xét unwrap DEK bằng KEK cũ trong môi trường được kiểm soát rồi wrap lại bằng KEK mới. Nếu DEK bị lộ hoặc nghi bị lộ, chỉ rewrap DEK là không đủ; dữ liệu cần được mã hóa lại bằng DEK mới theo kế hoạch ứng phó.

Đối với dữ liệu được mã hóa trực tiếp bằng khóa cũ, cần giải mã và mã hóa lại bằng khóa mới nếu chính sách và tình trạng khóa cho phép. Không giả định mọi dữ liệu đều có thể di chuyển ngay: bản sao lưu dài hạn, thiết bị mất kết nối hoặc yêu cầu lưu giữ có thể cần một quy trình truy cập ngoại lệ có phê duyệt, thời hạn và kiểm toán. Nếu khóa compromise, việc dùng lại khóa cũ để giải mã cần được đánh giá như một quyết định rủi ro của incident response.

### Bước 6: Xác minh và đóng sự kiện

Kiểm tra provider đã chặn đúng phiên bản, các workload không còn tạo thao tác bị cấm, policy và cache đã nhận trạng thái mới, inventory có đủ bằng chứng, và các quan hệ phụ thuộc đã có người chịu trách nhiệm. Khi thay thế khóa, ghi liên kết giữa phiên bản cũ và mới; cập nhật tiến độ rewrap hoặc re-encryption theo từng nhóm dữ liệu.

Chỉ chuyển sang `DESTROY_PENDING` khi đã đánh giá các yêu cầu lưu giữ, khả năng phục hồi, bản sao lưu và phụ thuộc còn lại. Chỉ ghi `DESTROYED` khi có bằng chứng hủy vật liệu khóa từ provider hoặc quy trình hủy được kiểm soát. Hủy khóa quá sớm có thể làm dữ liệu hợp lệ không thể khôi phục; giữ khóa quá lâu sau compromise lại kéo dài rủi ro. Quyết định phải dựa trên phân loại khóa, dữ liệu và chính sách lưu giữ.

## 4. Đồng bộ inventory trong hệ thống phân tán

Một sự kiện thu hồi thường phải cập nhật nhiều dịch vụ. Không nên giả định có một transaction cơ sở dữ liệu duy nhất bao trùm KMS, PKI, ứng dụng và inventory. Hãy thiết kế cập nhật theo sự kiện và có thể thử lại:

1. Tạo event ID duy nhất và ghi nhận yêu cầu thu hồi.
2. Gửi lệnh chặn đến provider, lưu phản hồi và mã tham chiếu.
3. Cập nhật inventory bằng cùng event ID.
4. Phát sự kiện cho các consumer cần đồng bộ.
5. Ghi nhận acknowledgment của từng consumer và thử lại các consumer lỗi.
6. Chạy reconciliation để đối chiếu trạng thái mong đợi với trạng thái thực tế.

Consumer phải xử lý idempotent: nhận lại cùng một event không được tạo ra nhiều lần chuyển trạng thái hoặc ghi đè một trạng thái mới hơn. Có thể lưu `event_id` đã xử lý, số phiên bản bản ghi hoặc sequence tăng đơn điệu. Timestamp hữu ích cho kiểm toán nhưng không nên là cơ chế duy nhất để quyết định thứ tự, vì đồng hồ giữa các hệ thống có thể lệch.

Nếu dùng transactional outbox, hệ thống có thể ghi thay đổi inventory và thông điệp cần phát trong cùng transaction cục bộ; một tiến trình riêng gửi thông điệp đến broker và đánh dấu đã gửi. Nếu không dùng outbox, phải có cơ chế phát hiện sự kiện đã ghi nhưng chưa phát. Trong cả hai trường hợp, cần có retry có giới hạn, dead-letter hoặc hàng đợi xử lý lỗi, cảnh báo khi quá hạn và quy trình xử lý thủ công.

Inventory nên phân biệt ít nhất ba mốc: thời điểm yêu cầu thu hồi được ghi nhận, thời điểm provider xác nhận chặn, và thời điểm mọi hệ thống phụ thuộc xác nhận đã đồng bộ. Ba mốc này không nhất thiết trùng nhau. Trường `revoked_at` chỉ nên biểu thị theo định nghĩa đã thống nhất, chẳng hạn thời điểm provider thực sự chặn; không dùng một timestamp chung để che đi độ trễ phân phối.

## 5. Đối chiếu định kỳ và phát hiện sai lệch

Sau cập nhật, cần chạy reconciliation giữa inventory và các nguồn thực thi. Các phép đối chiếu hữu ích gồm:

- Inventory ghi `REVOKED` hoặc `COMPROMISED` nhưng KMS/HSM vẫn cho phép thao tác bị cấm.
- Provider đã disable khóa nhưng inventory vẫn ghi `ACTIVE` hoặc không có sự kiện tương ứng.
- Chứng thư đã bị thu hồi nhưng danh mục PKI hoặc dịch vụ xác minh chưa đồng bộ.
- Một ứng dụng vẫn tham chiếu alias cũ hoặc gọi phiên bản khóa đã thu hồi.
- Khóa không còn owner, không có mục đích sử dụng rõ ràng hoặc không có lần sử dụng hợp lệ trong thời gian dài.
- Khóa đã `DESTROYED` nhưng vẫn còn được tham chiếu như một khóa có thể sử dụng; hoặc khóa còn vật liệu nhưng inventory ghi đã hủy.
- Bản sao lưu hay workload ngoại tuyến chưa được đưa vào bản đồ phụ thuộc.

Kết quả reconciliation cần tạo ra sai lệch có chủ sở hữu, mức độ ưu tiên, thời hạn xử lý và bằng chứng đóng. Đừng tự động sửa mọi sai lệch bằng cách chọn một nguồn dữ liệu làm đúng tuyệt đối. Ví dụ, trạng thái provider có thể phản ánh thao tác thực tế, còn inventory có thể chứa lý do, phê duyệt và phạm vi nghiệp vụ mà provider không biết. Cần quy định nguồn có thẩm quyền cho từng trường và xử lý xung đột theo quy trình.

## 6. Hai tình huống cần xử lý khác nhau

| Tình huống | Cập nhật inventory | Quyền còn lại và bước tiếp theo |
|---|---|---|
| Rotation theo lịch | Ghi phiên bản cũ đã ngừng nhận dữ liệu mới, liên kết phiên bản thay thế, lưu thời điểm và tiến độ di chuyển | Có thể cho phép `DECRYPT_ONLY` trong thời gian chuyển đổi nếu khóa không bị nghi compromise và chính sách cho phép; sau khi hết phụ thuộc thì xem xét hủy |
| Khóa bị compromise | Ghi `COMPROMISED`, phạm vi ảnh hưởng, incident, thời điểm phát hiện/hiệu lực, provider confirmation và các quyền bị chặn | Chặn ngay thao tác có rủi ro; đánh giá DEK/KEK, dữ liệu đã mã hóa, chữ ký/chứng thư và credential liên quan; mọi ngoại lệ giải mã phải được phê duyệt và kiểm toán |

Ví dụ, khi KEK phiên bản `v7` hết cryptoperiod, tổ chức có thể tạo `v8`, chuyển các DEK sang `v8`, giữ `v7` ở chế độ giải mã trong một khoảng thời gian được phê duyệt rồi hủy. Nhưng nếu `v7` bị lộ, việc giữ quyền unwrap để thuận tiện di chuyển có thể cho phép kẻ tấn công tiếp tục khai thác. Khi đó phải đánh giá khả năng chuyển đổi bằng bản sao an toàn, giới hạn quyền, môi trường cô lập và giám sát tăng cường; không tự động áp dụng quy trình rotation thông thường.

## 7. Lỗi thường gặp khi cập nhật inventory

- **Chỉ sửa một trường trạng thái:** Không lưu event ID, lý do, actor, thời điểm hiệu lực hoặc bằng chứng từ provider khiến quyết định khó kiểm toán.
- **Thu hồi alias thay vì phiên bản:** Alias có thể đã trỏ sang khóa mới; phải xác minh định danh thực tế trước khi thay đổi.
- **Đánh dấu đã thu hồi trước khi provider chặn:** Inventory và quyền thực thi không nhất quán, có thể che giấu một khóa vẫn hoạt động.
- **Cho phép giải mã mặc định:** `DECRYPT_ONLY` chỉ phù hợp khi rủi ro và chính sách cho phép; không nên áp dụng cho khóa bị compromise mà chưa đánh giá.
- **Bỏ sót bản sao lưu và hệ thống ngoại tuyến:** Dữ liệu phụ thuộc vẫn có thể cần khóa cũ sau khi dịch vụ chính đã chuyển đổi.
- **Xóa bản ghi sau khi hủy khóa:** Xóa dấu vết làm mất khả năng chứng minh vòng đời. Nên giữ tombstone và bằng chứng hủy theo thời hạn lưu giữ.
- **Không có cơ chế retry và reconciliation:** Một consumer lỗi có thể giữ trạng thái cũ vô thời hạn mà không ai phát hiện.
- **Ghi bí mật vào inventory hoặc log:** Metadata phải giúp định danh và quản trị khóa, không được trở thành nơi rò rỉ chính key material.

## 8. Ví dụ kiểm tra sau revocation

Giả sử hệ thống thanh toán thu hồi khóa ký `payment-signing-v3` sau khi phát hiện credential quản trị của workload ký có dấu hiệu bị lộ. Nhóm ứng phó sự cố cần xác nhận phiên bản bị ảnh hưởng, chặn thao tác `sign` ở HSM, thu hồi chứng thư theo quy trình PKI, vô hiệu hóa credential liên quan và ghi sự kiện compromise vào inventory. Sau đó nhóm kiểm tra các workload, hàng đợi xử lý, bản ghi audit và hệ thống xác minh chữ ký để xác định chữ ký nào được tạo trong khoảng thời gian có nguy cơ.

Inventory cần liên kết khóa cũ với khóa ký thay thế, chứng thư cũ với chứng thư mới, incident với bằng chứng provider và kết quả phân tích chữ ký. Việc xác minh chữ ký lịch sử phải tuân theo chính sách: một chữ ký có timestamp đáng tin cậy trước thời điểm compromise có thể được đánh giá khác chữ ký không có bằng chứng thời gian hoặc được tạo trong khoảng khóa có thể đã bị kiểm soát trái phép. Không nên tự động coi tất cả chữ ký cũ là hợp lệ hoặc vô hiệu chỉ dựa vào trạng thái hiện tại của chứng thư.

Một quy trình có thể biểu diễn bằng giả mã như sau:

```text
function processRevocation(event):
    assert event.event_id is unique
    target = inventory.find(event.key_id, event.version)
    assert target exists

    if inventory.hasProcessed(event.event_id):
        return previousResult(event.event_id)

    inventory.appendEvent(event, state="REVOCATION_PENDING")

    providerResult = keyProvider.blockOperations(
        target.providerReference,
        operations = policyFor(event.reason, target.purpose)
    )

    if not providerResult.confirmed:
        inventory.recordFailure(event.event_id, providerResult.error)
        alertOwnerAndIncidentTeam(event)
        return "PENDING_PROVIDER_CONFIRMATION"

    inventory.updateVersion(
        target,
        state = stateFor(event.reason),
        providerConfirmation = providerResult.reference,
        eventId = event.event_id
    )

    publishRevocationEvent(event)
    startDependencyAssessment(target, event)
    return "REVOCATION_RECORDED"
```

Đây là mô hình luồng xử lý, không phải API có thể chạy trực tiếp. Trong triển khai thực tế, cần xác thực quyền gọi, kiểm tra phạm vi và trạng thái hiện tại, bảo vệ tính idempotent, xử lý race condition với rotation hoặc một sự kiện thu hồi khác, và lưu mọi kết quả vào audit log. Hàm `policyFor` phải dựa trên loại khóa, mục đích, nguyên nhân và quyết định ứng phó; không thể dùng một danh sách thao tác cố định cho mọi trường hợp.

## 9. Checklist vận hành

Trước khi đóng một sự kiện revocation, người phụ trách nên xác nhận:

- [ ] Đúng `key_id`, phiên bản, provider và phạm vi bị thu hồi.
- [ ] Có event ID, lý do, actor, thời điểm phát hiện và thời điểm hiệu lực.
- [ ] Provider đã xác nhận chặn đúng các thao tác cần chặn.
- [ ] Inventory thể hiện đúng trạng thái, quyền còn lại và bằng chứng provider.
- [ ] Các alias, workload, chứng thư, cache và policy phụ thuộc đã được cập nhật hoặc có trạng thái chờ xử lý rõ ràng.
- [ ] Đã xác định dữ liệu, DEK, bản sao lưu và hệ thống ngoại tuyến chịu ảnh hưởng.
- [ ] Khóa thay thế và kế hoạch rewrap/re-encryption đã được liên kết với phiên bản cũ.
- [ ] Các ngoại lệ sử dụng khóa cũ có phê duyệt, phạm vi, thời hạn và giám sát.
- [ ] Reconciliation không còn sai lệch nghiêm trọng chưa có chủ sở hữu.
- [ ] Bằng chứng hủy chỉ được ghi khi việc hủy vật liệu khóa đã được xác nhận; bản ghi lịch sử vẫn được lưu theo chính sách.

Inventory được cập nhật tốt giúp tổ chức trả lời được bốn câu hỏi sau mỗi lần thu hồi: khóa nào bị ảnh hưởng, thao tác nào đã bị chặn, dữ liệu và hệ thống nào còn phụ thuộc, và bằng chứng nào cho thấy các bước xử lý đã hoàn tất. Khi những câu trả lời này có thể truy xuất và đối chiếu, revocation trở thành một quy trình quản lý vòng đời có kiểm soát thay vì chỉ là một thay đổi trạng thái rời rạc.
