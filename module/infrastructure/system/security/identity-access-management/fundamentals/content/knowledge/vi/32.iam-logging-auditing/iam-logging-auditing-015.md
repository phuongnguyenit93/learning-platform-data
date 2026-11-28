# Audit retention

## 1. Retention là chính sách vòng đời, không chỉ là số ngày lưu log

**Audit retention** là việc xác định và thực thi thời gian, phạm vi, cách lưu giữ cùng điều kiện kết thúc lưu giữ đối với dữ liệu audit. Trong IAM, dữ liệu này có thể ghi nhận đăng nhập, cấp token, thay đổi mật khẩu, cấp hoặc thu hồi quyền và hoạt động quản trị đặc quyền.

Một chính sách retention cần trả lời được:

- Loại sự kiện nào được lưu, phục vụ mục đích gì?
- Tính thời gian lưu từ mốc nào?
- Trong thời gian đó, ai được truy xuất và mất bao lâu để tìm được bằng chứng?
- Dữ liệu có được giữ đầy đủ, đúng nghĩa và phát hiện sửa đổi không?
- Khi nào phải tạm dừng xóa để bảo toàn bằng chứng?
- Khi hết hạn, những bản sao nào cần được xử lý và làm sao biết việc xử lý đã hoàn tất?

Đặt một cấu hình “giữ 180 ngày” trên kho tìm kiếm chưa đủ nếu backup vẫn giữ vô hạn, file xuất được sao chép khắp nơi hoặc dữ liệu đã lưu không còn đọc được. Ngược lại, lưu rất lâu nhưng không truy ra sự kiện cần thiết cũng không đạt mục đích audit.

Thời hạn cụ thể phải được xác định từ mục đích, rủi ro và các yêu cầu thực sự áp dụng cho tổ chức. Các con số trong bài chỉ là ví dụ thiết kế, không phải thời hạn mặc định hay kết luận về nghĩa vụ áp dụng cho một hệ thống cụ thể.

## 2. Xác định phạm vi dữ liệu cần quản lý

Một sự kiện IAM có thể tồn tại ở nhiều nơi trong đường xử lý:

```text
Nguồn phát sinh
    -> bộ đệm / outbox / hàng đợi
    -> kho tiếp nhận
    -> kho tìm kiếm
    -> kho lưu trữ dài hạn
    -> bản sao / backup / file xuất
```

Retention cần bao phủ những nơi thực sự lưu dữ liệu, không chỉ giao diện truy vấn chính.

| Nơi lưu | Vai trò thường gặp | Câu hỏi retention |
| --- | --- | --- |
| Bộ đệm tại nguồn hoặc outbox | Giữ dữ liệu trong khi chờ phát | Sau khi phát thành công, giữ bao lâu và xử lý lỗi thế nào? |
| Hàng đợi | Vận chuyển, thử lại, phát lại | Sự kiện còn tồn tại ở đâu sau khi bên nhận xử lý? |
| Kho tìm kiếm | Truy vấn nhanh và phát hiện | Khi nào sự kiện hết thời gian tìm kiếm trực tiếp? |
| Kho archive | Giữ bằng chứng với chi phí phù hợp | Có thể khôi phục và đọc được dữ liệu trong thời hạn cam kết không? |
| Bản sao và backup | Khả năng phục hồi | Dữ liệu hết hạn được xử lý hoặc ngăn tái xuất hiện ra sao? |
| File xuất điều tra | Phân tích hoặc bàn giao bằng chứng | Ai sở hữu, ai nhận và khi nào kết thúc lưu giữ? |

Metrics tổng hợp, trace và cache cũng cần được xem xét nếu chúng vẫn giữ thông tin có thể liên kết với chủ thể hoặc chứa bản sao nội dung audit. Không tự coi dữ liệu đã chuyển sang một công cụ khác là nằm ngoài trách nhiệm quản lý.

## 3. Phân loại trước khi chọn thời hạn

Không phải mọi dòng log có cùng giá trị hoặc độ nhạy. Có thể phân loại theo loại sự kiện, mức đặc quyền, tài nguyên, tenant và mục đích sử dụng.

Ví dụ:

- Sự kiện xác thực thành công hoặc thất bại.
- Thay đổi tài khoản, phương thức MFA hoặc kênh khôi phục.
- Cấp, sửa và thu hồi vai trò hoặc chính sách.
- Hoạt động quản trị đặc quyền.
- Truy cập hoặc xuất chính dữ liệu audit.
- Log kỹ thuật phục vụ xử lý lỗi pipeline.

Một chính sách có cấu trúc có thể ghi nhận:

```text
policyId: iam-privileged-change-retention
policyVersion: 4
scope: sự kiện thay đổi đặc quyền trong môi trường được chỉ định
purpose: điều tra và kiểm chứng quản trị quyền
timeAnchor: mốc tiếp nhận đầu tiên được hệ thống xác lập
searchablePeriod: theo yêu cầu truy vấn đã phê duyệt
totalRetention: theo thời hạn được xác định cho nhóm này
holdHandling: kiểm tra trạng thái bảo toàn trước khi xóa
deletionScope: kho chính, archive, bản sao và các bản xuất được quản lý
owner: đơn vị chịu trách nhiệm chính sách
```

Đây là mô hình mô tả, không phải schema bắt buộc của một sản phẩm. Chính sách cần có người chịu trách nhiệm và phiên bản để giải thích vì sao một nhóm sự kiện được lưu hoặc xóa ở một thời điểm.

Lưu lâu hơn không tự làm dữ liệu tốt hơn. Nếu log chứa mật khẩu, token hay bí mật không nên ghi, kéo dài retention chỉ làm tăng thời gian tồn tại của rủi ro. Cần giảm dữ liệu không cần thiết ngay từ lúc tạo sự kiện.

## 4. Chọn mốc thời gian và xử lý sự kiện đến muộn

Một sự kiện thường có nhiều thời điểm:

| Mốc | Ý nghĩa |
| --- | --- |
| `occurredAt` | Thời điểm sự kiện được nguồn ghi nhận là đã xảy ra |
| `recordedAt` | Thời điểm nguồn hoàn tất ghi bản ghi audit |
| `firstAcceptedAt` | Thời điểm pipeline quản lý tiếp nhận sự kiện lần đầu |
| `archivedAt` | Thời điểm chuyển hoặc sao chép vào archive |
| `expiresAt` | Thời điểm đủ điều kiện xem xét kết thúc lưu giữ theo chính sách |

Chính sách phải chọn rõ mốc tính thời hạn. Tính từ thời điểm xảy ra phù hợp với một số mục đích, nhưng sự kiện đến muộn hoặc timestamp nguồn sai có thể khiến dữ liệu bị xóa ngay sau khi tiếp nhận. Tính từ thời điểm tiếp nhận có đặc tính khác và không nên bị hiểu nhầm là cùng một quy tắc.

Ví dụ một hệ thống chọn mốc tiếp nhận đầu tiên do pipeline tin cậy xác lập:

```text
expiresAt = firstAcceptedAt + totalRetention
```

Nếu sự kiện được gửi lại do retry, không tự đặt lại `firstAcceptedAt` mỗi lần rồi kéo dài thời hạn vô hạn. Cần nhận diện cùng sự kiện bằng định danh và nguồn tương ứng, giữ đúng mốc theo chính sách đã chọn.

Không dùng timestamp client tự khai báo làm căn cứ duy nhất để quyết định xóa bằng chứng. Cần có cách xử lý thời gian không hợp lệ, quá cũ, ở tương lai hoặc không phù hợp với nguồn. Việc quản lý múi giờ và đồng hồ cũng ảnh hưởng đến truy vấn và xác định hạn.

Khi thay đổi chính sách, phải xác định nó chỉ áp dụng cho dữ liệu mới hay có tác động đến dữ liệu đang giữ. Lưu phiên bản và kết quả áp dụng; không âm thầm thay ý nghĩa của những mốc đã tính mà không có khả năng giải thích.

## 5. Lưu nhanh, archive và khả năng đọc lại bằng chứng

Có thể chia dữ liệu thành nhiều lớp để cân bằng chi phí và nhu cầu:

- **Kho truy vấn nhanh:** phục vụ điều tra gần thời điểm xảy ra và các truy vấn thường xuyên.
- **Archive:** phục vụ truy xuất ít thường xuyên hơn trong thời hạn còn lại.
- **Bản sao phục hồi:** phục vụ khôi phục khi có sự cố, với vòng đời riêng đã được quản lý.

Giả sử một nhóm sự kiện có tổng retention minh họa là 180 ngày, trong đó 30 ngày đầu ở kho truy vấn nhanh và ngày 31–180 ở archive. Tổng là 180 ngày, không phải 30 cộng thêm 180 ngày. Việc chuyển lớp không tự khởi động lại thời hạn.

Archive cần giữ đủ ngữ cảnh để diễn giải dữ liệu: phiên bản schema, định danh nguồn, cách biểu diễn thời gian và những ánh xạ cần thiết. Một file vẫn còn nhưng không có bộ đọc phù hợp, mất khóa giải mã hoặc mất ý nghĩa trường dữ liệu có thể không còn sử dụng được cho audit.

Ngoài việc kiểm tra file tồn tại, cần kiểm chứng:

- Tìm được đúng tenant, chủ thể, tài nguyên và khoảng thời gian.
- Khôi phục được dữ liệu theo mục tiêu thời gian đã xác định.
- Đọc được sự kiện ở phiên bản schema cũ.
- Kiểm tra được tính toàn vẹn theo cơ chế đã triển khai.
- Không vô tình cấp quyền đọc toàn bộ tenant khi chỉ cần trích một phạm vi điều tra.

Quyền truy cập archive không nên rộng hơn kho hoạt động chỉ vì archive ít được dùng. Bằng chứng cũ vẫn có thể tiết lộ cấu trúc danh tính và hoạt động nhạy cảm.

## 6. Tính toàn vẹn và giới hạn của cơ chế chống sửa đổi

Retention chỉ có giá trị nếu dữ liệu được giữ vẫn đáng tin trong phạm vi cơ chế bảo vệ. Cần quản lý quyền ghi, sửa, xóa, thay chính sách và quản trị khóa.

Các biện pháp có thể gồm lưu trữ chỉ bổ sung, hạn chế sửa/xóa trong khoảng bảo vệ, bản sao ở miền quản trị độc lập và cơ chế phát hiện thay đổi bằng mật mã. Việc lựa chọn phụ thuộc yêu cầu của hệ thống.

Cần hiểu những giới hạn:

- Một checksum đặt cùng file và cùng quyền sửa không tự chống được người có thể thay cả hai.
- Một chữ ký có thể hỗ trợ kiểm tra dữ liệu đã ký, nhưng không chứng minh mọi sự kiện đều đã được nguồn tạo ra và gửi đầy đủ.
- Chỉ bổ sung hoặc khóa xóa không tự bảo đảm nội dung ban đầu là đúng hoặc không chứa bí mật.
- Mã hóa giúp bảo vệ tính bí mật nhưng không thay thế phân quyền, kiểm tra tính toàn vẹn và khả năng truy xuất.

Khóa giải mã, khóa kiểm tra và metadata liên quan có vòng đời cần tương thích với thời gian giữ bằng chứng. Không xóa khóa còn cần để đọc dữ liệu đang được yêu cầu giữ; cũng không giữ dữ liệu vô hạn chỉ vì chưa quản lý được vòng đời khóa.

Chính sách bất biến ở cấp object hoặc partition cũng ảnh hưởng khả năng xóa chọn lọc. Nếu trộn dữ liệu có thời hạn và điều kiện bảo toàn khác nhau trong cùng một đơn vị không thể tách, việc thực thi retention có thể khó hoặc không đáp ứng được thiết kế. Cần xét điều này khi chọn cấu trúc lưu trữ.

## 7. Bảo toàn bằng chứng và tạm dừng xóa

Trong một cuộc điều tra hoặc một yêu cầu bảo toàn có thẩm quyền, một tập dữ liệu có thể cần được giữ vượt lịch xóa thông thường. Có thể quản lý điều đó bằng **hold**, tức trạng thái tạm dừng việc xóa đối với phạm vi đã xác định.

Một hold cần mô tả ít nhất:

- Ai có quyền tạo, sửa và kết thúc hold.
- Căn cứ hoặc tham chiếu công việc.
- Phạm vi sự kiện, chủ thể, tenant, nguồn và thời gian liên quan.
- Thời điểm có hiệu lực và cơ chế rà soát.
- Nơi lưu trạng thái và cách các tác vụ xóa kiểm tra trạng thái đó.

Không gắn hold toàn bộ kho theo mặc định nếu chỉ cần giữ một phạm vi nhỏ. Nhưng cũng không giả định giữ một file xuất là đủ nếu bằng chứng cần bao gồm sự kiện ở các nguồn hoặc giai đoạn khác.

Khi kết thúc hold, dữ liệu không nhất thiết được giữ lại trọn một chu kỳ mới. Cần áp dụng chính sách đã định nghĩa: có thể xem xét xóa ngay nếu đã hết hạn thông thường và không còn điều kiện giữ nào khác.

Nếu các yêu cầu áp dụng có vẻ mâu thuẫn về lưu giữ hoặc xóa, hệ thống cần có đường chuyển xử lý cho người chịu trách nhiệm chính sách. Không tự coi hold là lý do hợp lệ cho mọi trường hợp giữ vô hạn hoặc tự xóa để giải quyết mâu thuẫn chưa được xác định.

## 8. Xóa hết hạn là một quy trình có thể kiểm chứng

`expiresAt` thường chỉ là điều kiện đầu vào để xét xóa, không phải bằng chứng dữ liệu đã được xóa. Một bộ lọc làm sự kiện biến mất khỏi kết quả tìm kiếm cũng chưa chứng minh bản sao vật lý hoặc archive đã hết tồn tại.

Một quy trình khái quát:

```text
Tìm dữ liệu đến hạn theo chính sách
                |
                v
Kiểm tra phạm vi, phiên bản chính sách và hold hiện tại
                |
                v
Lập tác vụ xóa đúng các nơi lưu được quản lý
                |
                v
Thực hiện với kiểm soát đồng thời và xử lý lỗi
                |
                v
Xác nhận kết quả từng nơi lưu
                |
                v
Ghi bằng chứng hoàn tất hoặc phần còn tồn đọng
```

Mã giả cho bước xét điều kiện:

```text
evaluateDeletionCandidate(candidate, trustedNow):
    policy = policies.resolveApplicableVersion(candidate)
    require policy is known
    require candidate.expiryAccordingTo(policy) <= trustedNow
    require requiredRetentionConditionsSatisfied(candidate, policy)

    holdState = holds.readCurrentFor(candidate.scope)
    require holdState.isSufficientlyCurrent
    require not holdState.blocksDeletion

    return deletionCoordinator.createScopedOperation(
        candidate.reference,
        expectedPolicyVersion = policy.version,
        expectedHoldVersion = holdState.version
    )
```

Đây là mã giả thiết kế, không phải lệnh xóa dữ liệu. Tạo tác vụ không có nghĩa xóa đã hoàn tất. Nơi thực hiện cần kiểm soát khả năng chính sách hoặc hold thay đổi giữa lúc lập kế hoạch và lúc xóa, theo cơ chế đồng thời của hệ thống.

Nếu một nơi lưu thất bại, trạng thái tổng không được ghi thành hoàn tất toàn bộ. Cần biết dữ liệu còn ở đâu, tác vụ nào cần thử lại và sự cố ảnh hưởng phạm vi nào.

Bằng chứng xóa có thể gồm policy/version, phạm vi, khoảng thời gian, định danh tác vụ, kết quả và thời điểm. Không cần sao chép lại toàn bộ sự kiện vừa xóa vào một log mới, vì điều đó tạo bản sao khác của chính dữ liệu cần kết thúc lưu giữ.

## 9. Backup, bản xuất và khả năng tái xuất hiện dữ liệu

### 9.1. Backup có vòng đời riêng

Một kho backup bất biến có thể không hỗ trợ xóa ngay từng bản ghi. Thiết kế retention phải tính trước khả năng này, chu kỳ hết hạn backup, giới hạn truy cập và cách xử lý khi phục hồi. Không tuyên bố đã xóa mọi bản sao nếu backup vẫn còn giữ dữ liệu.

Khi khôi phục backup, cần đối soát chính sách và trạng thái xóa/hold hiện tại trước khi đưa dữ liệu trở lại phục vụ. Nếu không, một bản khôi phục có thể làm dữ liệu đã hết hạn xuất hiện lại trong kho tìm kiếm hoặc được phát lại vào pipeline.

Nhật ký hoặc metadata phục vụ đối soát cần được thiết kế vừa đủ để ngăn tái xuất hiện ngoài chính sách, với vòng đời riêng. Không lưu nguyên nội dung nhạy cảm vô hạn dưới tên gọi “danh sách đã xóa”.

### 9.2. File xuất cũng là dữ liệu audit

File xuất phục vụ điều tra cần có chủ sở hữu, người nhận, phạm vi sử dụng và thời hạn. Việc chuyển sang máy cá nhân hoặc công cụ phân tích không làm mất nhu cầu quản lý quyền và xóa.

Một bộ bằng chứng điều tra có thể cần giữ lâu hơn log thông thường theo điều kiện đã xác định. Khi đó phải quản lý nó như một tập dữ liệu có mục đích và phạm vi riêng, không phải file tạm bị bỏ quên.

### 9.3. Mã hóa và xóa khóa

Trong một số thiết kế, việc xóa khóa có thể được sử dụng như một phần cơ chế làm dữ liệu không thể giải mã. Điều này chỉ có ý nghĩa nếu vòng đời và mọi bản sao khóa thực sự được kiểm soát.

Không mặc định xóa một khóa dùng chung là cách xóa chọn lọc an toàn: nó có thể làm mất cả dữ liệu còn phải giữ. Cũng không coi thao tác khóa quyền đọc tạm thời tương đương việc xóa dữ liệu hoặc xóa khóa không thể phục hồi.

## 10. Dung lượng, chi phí và quyền riêng tư

Một ước lượng thô về dung lượng chưa tính nén hoặc chỉ mục là:

```text
rawBytes = số sự kiện mỗi ngày × kích thước trung bình × số ngày
```

Ví dụ minh họa có 2.000.000 sự kiện/ngày, trung bình 800 byte/sự kiện:

```text
Mỗi ngày: 2.000.000 × 800 = 1.600.000.000 byte, khoảng 1,6 GB thập phân
30 ngày đầu: khoảng 48 GB dữ liệu thô
150 ngày còn lại: khoảng 240 GB dữ liệu thô
Tổng 180 ngày: khoảng 288 GB dữ liệu thô
```

Đây không phải ước lượng chi phí cuối cùng. Cần tính thêm tăng trưởng, cao điểm, chỉ mục, bản sao, backup, metadata, nén, chi phí truy vấn và phục hồi archive. Một sự cố có thể làm tăng mạnh số sự kiện thất bại, nên trung bình thường ngày chưa đủ để thiết kế dung lượng.

Giảm dữ liệu không cần thiết thường có ích hơn việc chỉ tăng dung lượng: không ghi token, loại bỏ payload dư thừa, giữ metadata có mục đích và phân quyền đúng phạm vi. Tuy nhiên, không lấy mẫu tùy ý những sự kiện cần đầy đủ để chứng minh chuỗi thay đổi đặc quyền hoặc kết quả kiểm soát.

Ẩn bớt email hoặc thay user ID bằng một mã có thể giảm lộ trực tiếp, nhưng nếu vẫn có thể liên kết lại với người dùng thì dữ liệu chưa tự trở thành vô danh. Cần xét cả bảng ánh xạ, quyền truy vấn và khả năng liên kết qua nhiều nguồn.

## 11. Giám sát retention và kiểm chứng định kỳ

Các chỉ số hữu ích có thể gồm dữ liệu quá hạn chưa xử lý, tác vụ xóa thất bại, hold chưa được rà soát, độ trễ chuyển archive, lỗi khôi phục và các bản xuất chưa có chủ sở hữu rõ ràng.

Tác vụ retention cũng cần audit: ai đổi chính sách, phạm vi nào bị tác động, phiên bản nào được dùng và kết quả xóa đến đâu. Quyền sửa chính sách hoặc gỡ hold có thể ảnh hưởng trực tiếp đến bằng chứng điều tra, nên không nên rộng hơn nhu cầu công việc.

Các tình huống kiểm chứng quan trọng:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Sự kiện đến muộn hoặc timestamp nguồn sai | Không bị xử lý theo mốc chưa được tin cậy ngoài chính sách |
| Cùng sự kiện được gửi lại | Không vô tình kéo dài retention mỗi lần retry |
| Chuyển từ kho nhanh sang archive | Không khởi động lại thời hạn hoặc mất ngữ cảnh đọc |
| Truy xuất một sự kiện schema cũ | Có thể tìm, đọc và kiểm tra theo thiết kế |
| Hold có hiệu lực khi tác vụ xóa đang chờ | Điểm thực thi xử lý thay đổi theo cơ chế đồng thời đã xác định |
| Kết thúc hold khi dữ liệu đã quá hạn | Áp dụng đúng quy tắc sau hold, không mặc định giữ lại vô hạn |
| Kho chính đã xóa nhưng archive thất bại | Không báo hoàn tất toàn bộ, có khả năng theo dõi và thử lại |
| Khôi phục từ backup cũ | Không tái đưa dữ liệu hết hạn vào phục vụ ngoài chính sách |
| File xuất phục vụ điều tra | Có chủ sở hữu, quyền truy cập và vòng đời rõ ràng |
| Khóa cần để đọc archive bị xoay vòng | Bằng chứng còn trong thời hạn vẫn đọc được theo cơ chế quản lý khóa |
| Chính sách áp dụng khác nhau giữa tenant | Thực thi đúng phạm vi, không xóa hoặc giữ nhầm dữ liệu tenant khác |
| Hệ thống lọc log khỏi giao diện | Không nhầm ẩn kết quả với xóa mọi nơi lưu |

Audit retention đạt mục đích khi bằng chứng cần thiết còn truy xuất được trong đúng thời gian, được bảo vệ đúng phạm vi và được kết thúc lưu giữ theo một quy trình có thể chứng minh. Quản lý đầy đủ vòng đời này giúp IAM vừa hỗ trợ điều tra, vừa tránh tích lũy dữ liệu nhạy cảm không còn mục đích sử dụng.
