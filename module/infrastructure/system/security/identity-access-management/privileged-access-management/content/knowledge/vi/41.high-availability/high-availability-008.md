# RPO của PAM

## 1. RPO trả lời câu hỏi nào?

Trong hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM), dịch vụ hoạt động trở lại chưa chắc có nghĩa là trạng thái quyền và credential đã được khôi phục đúng. Một vault có thể mở được nhưng chỉ còn mật khẩu cũ; một cổng quản trị có thể đăng nhập được nhưng chưa biết tài khoản đã bị thu hồi trước sự cố.

**Recovery Point Objective — RPO** là mục tiêu giới hạn khoảng thời gian dữ liệu có thể bị mất khi phục hồi sau một sự cố đã xác định. RPO diễn tả mức độ lùi về quá khứ có thể chấp nhận của trạng thái phục hồi, thường được biểu diễn bằng giây, phút hoặc giờ.

Ví dụ: RPO 5 phút cho dữ liệu vault trong kịch bản mất toàn bộ site chính có nghĩa là tổ chức yêu cầu khả năng phục hồi vault đến một điểm cách thời điểm sự cố không quá 5 phút. Đây là mục tiêu phải được chứng minh bằng dữ liệu phục hồi, chứ không phải lời khẳng định rằng cứ có backup mỗi 5 phút là đã đạt yêu cầu.

PAM có đặc điểm quan trọng: dữ liệu của nó điều khiển quyền truy cập tới nhiều hệ thống khác. Mất một bản ghi có thể đồng nghĩa với việc:

- Không biết mật khẩu hiện tại của một tài khoản quản trị.
- Khôi phục lại một quyền đã bị thu hồi.
- Không chứng minh được ai đã lấy credential hoặc thực hiện thao tác.
- Không phân biệt được rotation đã hoàn tất với rotation còn dang dở.
- Cấp lại quyền vượt quá thời hạn JIT đã được phê duyệt.

Vì vậy, RPO của PAM cần gắn với từng loại trạng thái, phạm vi sự cố và điều kiện phục hồi an toàn. Không nên chỉ công bố một con số cho toàn bộ sản phẩm.

Sau bài học, người học có thể xác định dữ liệu cần bảo vệ, phân biệt RPO với RTO, thiết kế bằng chứng đo RPO và lập quy trình xử lý trạng thái credential không nhất quán sau khôi phục.

## 2. Phân biệt mục tiêu, điểm phục hồi và tổn thất thực tế

Ba khái niệm thường bị gọi chung là “RPO” nhưng cần được tách rõ:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| RPO mục tiêu | Khoảng mất dữ liệu tối đa được chấp nhận trong phạm vi đã thỏa thuận | Không quá 300 giây khi mất site A |
| Điểm phục hồi thực tế | Mốc trạng thái nhất quán thực sự có thể dựng lại từ dữ liệu còn tồn tại | Commit đã kiểm chứng tại 09:56:20 |
| Khoảng lùi phục hồi quan sát | Chênh lệch giữa thời điểm sự cố và điểm phục hồi đã kiểm chứng | Sự cố 10:00:00, khoảng lùi 220 giây |
| Dữ liệu thực sự mất | Những thay đổi đã được chấp nhận trước sự cố nhưng không có trong trạng thái phục hồi hoặc nguồn bổ sung hợp lệ | Hai sự kiện thu hồi quyền và một rotation |
| Độ trễ replica | Mức replica đang chậm hơn nguồn theo một định nghĩa cụ thể | Chậm 40 giây ở bước apply |

Với một tập dữ liệu và một mốc thời gian tin cậy, có thể ước lượng khoảng lùi:

```text
T_su_co       = thời điểm sự cố theo phạm vi đo
T_phuc_hoi    = thời điểm của trạng thái nhất quán mới nhất đã kiểm chứng
Khoang_lui   = max(0, T_su_co - T_phuc_hoi)

Dat_muc_tieu_thoi_gian = Khoang_lui <= RPO_muc_tieu
```

Công thức chỉ có ý nghĩa khi biết rõ `T_phuc_hoi` đại diện cho điều gì. Thời gian tạo file backup, thời gian copy file xong hay thời gian replica gửi heartbeat không tự động là thời gian của trạng thái có thể phục hồi.

Nếu không có thay đổi dữ liệu trong 10 phút trước sự cố, một bản backup cách sự cố 10 phút vẫn có thể không làm mất giao dịch nào. Ngược lại, mất vài giây dữ liệu trong lúc đang thu hồi tài khoản khẩn cấp có thể gây hậu quả lớn. Do đó, báo cáo nên có cả khoảng lùi thời gian và danh sách hoặc số lượng thay đổi bị thiếu.

Trong hệ phân tán, một timestamp không thể thay thế việc xác minh tính đầy đủ. Commit sequence, transaction ID, generation của khóa và version của secret thường là bằng chứng tốt hơn cho thứ tự trạng thái. Đồng hồ dùng để quy đổi sang thời gian phải được giám sát sai lệch.

## 3. RPO khác RTO và tính sẵn sàng

**Recovery Time Objective — RTO** là mục tiêu về thời gian khôi phục một chức năng dịch vụ đến mức đã thỏa thuận. RTO quan tâm “bao lâu thì dùng lại được”; RPO quan tâm “dữ liệu được phục hồi mới đến đâu”.

Một PAM có thể đạt RTO nhưng không đạt RPO:

> Sau 8 phút, người vận hành đăng nhập được cổng dự phòng. Tuy nhiên, vault đã lùi về bản sao cách sự cố 45 phút, trong khi RPO được cam kết là 5 phút.

Một PAM cũng có thể đạt RPO nhưng không đạt RTO:

> Replica giữ đầy đủ giao dịch đã cam kết, nhưng việc mở khóa bằng HSM và khôi phục kết nối tới hệ thống đích kéo dài 2 giờ, vượt RTO 30 phút.

Tính sẵn sàng cao (HA) giảm gián đoạn khi một thành phần hỏng. HA không thay thế khôi phục thảm họa (DR) và không tự bảo đảm một RPO cụ thể. Hai node cùng sao chép một thao tác xóa nhầm vẫn có thể cùng mất dữ liệu. Một cụm đồng bộ trong cùng trung tâm dữ liệu cũng không chứng minh được khả năng bảo toàn dữ liệu khi mất cả trung tâm đó.

Khi nghiệm thu, cần có ba kết quả riêng:

1. Chức năng dịch vụ nào đã hoạt động lại, sau bao lâu.
2. Dữ liệu nào được khôi phục đến điểm nào.
3. Quyền truy cập và credential có an toàn, nhất quán với hệ thống đích hay chưa.

Cổng đăng nhập trả HTTP thành công chỉ chứng minh một phần rất nhỏ của ba kết quả này.

## 4. Phân loại dữ liệu PAM trước khi đặt RPO

PAM không chỉ là một cơ sở dữ liệu chứa mật khẩu. Một thiết kế RPO phải kiểm kê các trạng thái ảnh hưởng đến khả năng cấp, sử dụng, thu hồi và kiểm toán đặc quyền.

| Nhóm trạng thái | Hậu quả nếu mất thay đổi gần nhất | Điều cần xác minh khi phục hồi |
|---|---|---|
| Secret và version của secret | Vault còn credential cũ hoặc thiếu secret vừa tạo | Version có thể giải mã và có quan hệ đúng với credential đang có hiệu lực ở đích |
| Metadata rotation | Không biết bước nào đã hoàn tất | Operation ID, trạng thái chuyển tiếp, kết quả xác minh và cơ chế đối soát |
| Policy, membership, scope tài nguyên | Quyền cũ xuất hiện trở lại hoặc quyền mới bị mất | Policy hiệu lực, danh sách bị thu hồi và phạm vi least privilege |
| Phê duyệt và grant JIT | Grant hết hạn hoặc đã hủy có thể bị dùng lại | Thời hạn tuyệt đối, lý do cấp, trạng thái thu hồi và người phê duyệt |
| Checkout, lease và lock | Một credential có thể bị nhiều bên lấy ngoài dự kiến | Lease còn hợp lệ hay phải vô hiệu hóa; lock nào được dựng lại |
| Audit event và chỉ mục tìm kiếm | Thiếu bằng chứng thao tác hoặc khó truy vấn | Luồng sự kiện gốc, tính toàn vẹn, khoảng sequence bị thiếu |
| Recording phiên | Không điều tra được thao tác trong một đoạn phiên | Segment, manifest, checksum và độ đầy đủ của recording |
| Khóa mã hóa và thông tin phục hồi | Có backup nhưng không giải mã được vault | Key version, quyền dùng KMS/HSM và thủ tục phục hồi tương ứng |
| Cấu hình connector và chứng thư | Không quản lý hoặc không xác thực được kết nối | Identity của connector, trust chain, endpoint và chứng thư còn hiệu lực |

Danh sách này phải được đối chiếu với triển khai thực tế. Một hệ thống có thể lưu policy ở dịch vụ riêng, audit ở nền tảng độc lập và recording ở object storage. Mỗi nơi có cơ chế xác nhận ghi và cơ chế phục hồi khác nhau.

Khóa mã hóa là phụ thuộc đặc biệt. RPO 1 phút cho secret không có nhiều giá trị nếu bản sao phục hồi thiếu key version đã dùng để mã hóa những secret đó. Tuy nhiên, không thể giải quyết bằng cách đưa khóa giải mã và toàn bộ secret vào cùng một gói không được bảo vệ. Cần cơ chế sao lưu hoặc phục hồi khóa phù hợp với HSM/KMS, phân quyền và sự tách biệt miền sự cố.

Không cần sao chép mọi dữ liệu tạm như cache để đạt RPO. Nếu cache có thể dựng lại từ nguồn chuẩn, nên ghi rõ nó là trạng thái dẫn xuất. Ngược lại, một “cache quyền” được dùng như nguồn quyết định độc lập khi mất kết nối có thể mang rủi ro bảo mật và cần được đánh giá riêng.

## 5. Xác định phạm vi sự cố của lời cam kết

Một RPO phải đi cùng một câu mô tả sự cố. “RPO bằng 0” mà không có phạm vi thường không đủ để ra quyết định.

Những phạm vi khác nhau có thể gồm:

- Hỏng một tiến trình hoặc một node.
- Mất một availability zone.
- Mất toàn bộ site hoặc region.
- Đứt kết nối giữa site chính và site dự phòng.
- Xóa nhầm hoặc cập nhật sai dữ liệu.
- Tài khoản quản trị bị chiếm và dữ liệu bị sửa có chủ ý.
- Mất đồng thời dịch vụ khóa và kho lưu trữ.
- Không truy cập được một hệ thống đích trong lúc rotation.

Với mất node, replica đồng bộ trong cùng cụm có thể đủ. Với mất region, bản sao trong cùng region không đáp ứng phạm vi. Với dữ liệu bị sửa sai, bản sao mới nhất có thể đã chứa lỗi; phải lùi về một điểm sạch cũ hơn và tái áp dụng các thay đổi hợp lệ nếu có đủ bằng chứng.

Trong tình huống cuối, cần công bố cả:

- Điểm phục hồi mới nhất về mặt kỹ thuật.
- Điểm sạch đã được xác minh.
- Khoảng dữ liệu hợp lệ cần dựng lại.
- Những thay đổi bảo mật phải được tái áp dụng trước khi mở truy cập.

Nếu chỉ có thể phục hồi bản sạch cách sự cố 4 giờ trong khi mục tiêu là 5 phút, phải ghi nhận chênh lệch. Không nên đổi định nghĩa RPO sau sự cố để biến kết quả này thành đạt.

## 6. Đặt RPO theo tác động nghiệp vụ và rủi ro

Tổ chức nên bắt đầu từ câu hỏi: “Nếu mất thay đổi này, điều gì xảy ra với hoạt động quản trị, ứng dụng và an toàn truy cập?”

Ví dụ, mất một chỉ mục tìm kiếm có thể được xử lý bằng cách xây lại từ audit gốc. Mất sự kiện thu hồi tài khoản của một nhân sự đã nghỉ việc có hậu quả hoàn toàn khác. Hai loại dữ liệu không nhất thiết dùng cùng RPO hoặc cùng hành vi khi thiếu dữ liệu.

Một bảng mục tiêu minh họa:

| Dữ liệu/chức năng | Mục tiêu minh họa | Điều kiện bổ sung |
|---|---|---|
| Secret quản trị hệ thống trọng yếu | RPO bằng 0 cho giao dịch đã được xác nhận trong phạm vi mất một site | Xác nhận ghi phải bao gồm bản bền vững ở miền còn sống; có đối soát hiệu lực tại đích |
| Secret dịch vụ ít trọng yếu hơn | Không quá 5 phút khi mất site chính | Có quy trình xử lý version không khớp mà không làm lộ secret |
| Policy và thu hồi quyền | Không chấp nhận cấp lại quyền đã bị thu hồi | Chặn cấp quyền khi chưa có trạng thái thu hồi đủ mới; nguồn đối soát độc lập |
| Audit sự kiện quản trị | Không quá 1 phút trong phạm vi sự cố đã chọn | Phát hiện gap, giữ sự kiện gốc và công bố phần chưa chuyển được |
| Chỉ mục audit | Có thể dựng lại từ nguồn gốc | Nêu riêng thời gian dựng lại và chức năng tìm kiếm bị ảnh hưởng |
| Recording đang ghi | Giới hạn phần đuôi chưa bền vững theo chính sách phiên | Phải xác định được segment nào đã lưu, segment nào không thể phục hồi |

Các con số trên là ví dụ để học cách lập hợp đồng, không phải mức chuẩn áp dụng cho mọi PAM. Mục tiêu cuối cùng phải được chủ hệ thống, chủ dữ liệu và bộ phận an toàn thông tin thống nhất.

Một yêu cầu như “không cấp lại quyền đã thu hồi” là bất biến bảo mật, không chỉ là một con số RPO. Nếu bản sao dự phòng có thể chậm 5 phút, thiết kế cần một cơ chế bổ sung hoặc phải ngừng cấp quyền cho đến khi xác minh được trạng thái hiện hành. Việc hệ thống ngừng cấp quyền lúc mất tính chắc chắn ảnh hưởng RTO/tính sẵn sàng; cần công khai sự đánh đổi đó.

## 7. Vì sao backup mỗi 5 phút chưa chứng minh RPO 5 phút?

Giả sử lịch backup là 5 phút một lần:

```text
09:50:00  Bắt đầu backup B1
09:52:00  B1 hoàn tất ở site chính
09:54:00  B1 được chuyển sang site dự phòng
09:55:00  Bắt đầu backup B2
09:57:00  B2 hoàn tất ở site chính
09:58:00  Site chính mất hoàn toàn; B2 chưa chuyển xong
```

Bản sao dùng được ở site dự phòng có thể vẫn là B1. Nếu điểm dữ liệu nhất quán của B1 là 09:50:00, khoảng lùi là 8 phút. Nếu công cụ backup có cơ chế snapshot khác, phải dùng mốc nhất quán mà công cụ chứng minh được, không tự lấy thời điểm hoàn tất.

Ngoài lịch chạy, RPO còn phụ thuộc:

- Backup có hoàn tất và đọc được hay không.
- Bản sao có tồn tại ngoài miền sự cố hay không.
- Có đủ chuỗi incremental và transaction log để replay hay không.
- Log đã đến đích có liên tục, không thiếu đoạn hay không.
- Có đủ key version để giải mã toàn bộ dữ liệu cần dùng hay không.
- Điểm phục hồi có nhất quán giữa các thành phần hay không.
- Bản sao có chứa sự cố logic hoặc dữ liệu đã bị xâm phạm hay không.

Nếu có backup nền tại 09:50 và chuỗi transaction log liên tục đã được bảo vệ đến 09:57:40, hệ thống có thể phục hồi mới hơn thời điểm backup nền. Ngược lại, chỉ mất một đoạn log bắt buộc cũng có thể khiến điểm phục hồi liên tục phải dừng ở một mốc cũ hơn.

Phải đo **điểm phục hồi có thể dựng lại**. Không cộng máy móc mọi độ trễ vì có giai đoạn chạy chồng nhau, nhưng cũng không bỏ qua bước nào chỉ vì một dashboard hiển thị màu xanh.

## 8. Replication đồng bộ, bất đồng bộ và ý nghĩa của RPO bằng 0

### 8.1. Replication đồng bộ

Với thiết kế đồng bộ phù hợp, một giao dịch chỉ được báo thành công sau khi dữ liệu đã bền vững trên tập bản sao cần thiết. Khả năng RPO bằng 0 cho giao dịch đã xác nhận phụ thuộc vào việc tập bản sao đó có sống sót qua đúng sự cố đang xét hay không.

Những câu hỏi cần trả lời:

1. “Đã ghi” nghĩa là nhận vào RAM, ghi vào log bền vững hay đã apply?
2. Quorum xác nhận gồm những site hoặc zone nào?
3. Khi mất liên kết, hệ thống dừng ghi hay tự chuyển sang chế độ yếu hơn?
4. Có giao dịch nào được báo thành công trước hàng rào bền vững không?
5. Khi failover, leader cũ được fencing thế nào để không tiếp tục ghi?
6. Cơ chế này bảo vệ dữ liệu vault hay bao gồm cả các thành phần khác?

RPO bằng 0 không đồng nghĩa mọi request đều có kết quả rõ ràng. Nếu giao dịch đã commit nhưng kết nối bị đứt trước khi client nhận phản hồi, client có thể không biết kết quả. Retry phải dùng operation ID và cách xử lý idempotent phù hợp, thay vì tự giả định request thất bại và lặp lại một thao tác thay đổi credential.

Replication đồng bộ cũng không khiến việc đổi mật khẩu trên thiết bị đích trở thành một giao dịch nguyên tử với vault. Đó là hai hệ thống khác nhau; cần cơ chế điều phối và phục hồi riêng.

### 8.2. Replication bất đồng bộ

Replication bất đồng bộ cho phép nguồn báo thành công trước khi bản sao ở xa bền vững. Vì vậy, có một cửa sổ dữ liệu có thể chưa đến đích tại lúc nguồn mất.

Cần phân biệt ít nhất:

- **Receive watermark:** đích đã nhận đến đâu.
- **Durable watermark:** dữ liệu đã được lưu bền vững đến đâu.
- **Apply watermark:** trạng thái ứng dụng đã áp dụng đến đâu.
- **Verified recoverable watermark:** mốc được chứng minh có thể phục hồi với đủ phụ thuộc.

Nếu log đã bền vững tại đích nhưng chưa apply, replay có thể giúp đạt điểm phục hồi mới hơn, đổi lại thời gian phục hồi tăng. Nếu log mới chỉ nằm trong bộ nhớ của tiến trình vừa chết, không được tính nó là dữ liệu chắc chắn có thể phục hồi.

### 8.3. Không có một cơ chế duy nhất giải quyết mọi loại mất dữ liệu

| Cơ chế | Điều có thể giúp bảo vệ | Giới hạn cần xét |
|---|---|---|
| Replica đồng bộ qua miền sự cố | Giao dịch được xác nhận khi một miền bị mất | Độ trễ ghi, quorum, chế độ suy giảm và lỗi logic bị sao chép |
| Replica bất đồng bộ | Bản sao ở xa với ảnh hưởng độ trễ thấp hơn | Có khoảng dữ liệu chưa bền vững ở xa |
| Backup cùng log liên tục | Phục hồi về nhiều điểm thời gian | Phụ thuộc chuỗi log, khóa và thời gian replay |
| Bản sao bất biến/tách quyền | Giảm khả năng bản sao bị sửa hoặc xóa cùng nguồn | Không tự làm bản sao mới hơn; vẫn cần kiểm chứng phục hồi |
| Luồng audit độc lập | Đối soát sự kiện và phát hiện khoảng thiếu | Audit thường không chứa đủ dữ liệu để tái tạo secret |
| Bản cấu hình được kiểm soát phiên bản | Dựng lại policy/cấu hình đã phê duyệt | Không thay thế trạng thái thu hồi, lease hoặc secret hiện hành |

Việc chọn cơ chế cần bám mục tiêu dữ liệu cụ thể, thay vì coi số lượng node là bằng chứng đạt RPO.

## 9. Rotation là nơi RPO của PAM dễ bị hiểu sai

Giả sử vault và hệ thống đích cùng bắt đầu với credential version `v41`. Một thao tác rotation có operation ID `rot-913` thực hiện các bước khái niệm:

```text
1. Ghi ý định rotation và operation ID.
2. Chuẩn bị credential mới theo cơ chế được hỗ trợ.
3. Thay đổi credential tại hệ thống đích.
4. Xác minh credential mới có hiệu lực.
5. Chốt version mới trong vault và trạng thái hoàn tất.
```

Thứ tự kỹ thuật cụ thể tùy sản phẩm và hệ thống đích. Điều quan trọng là có trạng thái trung gian bền vững và quy trình đối soát cho mọi điểm có thể gián đoạn.

Một tình huống:

```text
11:02:00  Site dự phòng có vault version v41.
11:03:10  Hệ thống đích chấp nhận credential mới của rot-913.
11:03:12  Vault chính chốt v42.
11:03:13  Site chính mất trước khi v42 đến site dự phòng.
11:05:00  Vault dự phòng được mở với v41.
```

Khoảng lùi dữ liệu có thể nhỏ hơn RPO được đặt ra, nhưng `v41` không còn dùng được ở đích. Đây là hậu quả phải nằm trong thiết kế, không phải một lỗi “ngoài phạm vi” chỉ vì vault đã phục hồi thành công.

Quy trình xử lý nên dựa vào trạng thái rotation, khả năng của connector và chính sách phục hồi:

1. Tạm chặn checkout hoặc rotation tự động đối với tài khoản có trạng thái chưa xác định.
2. Đối chiếu operation ID, version metadata, nguồn audit và trạng thái tại đích qua cơ chế được cấp quyền.
3. Nếu có credential mới được bảo vệ và khôi phục hợp lệ, xác minh rồi cập nhật quan hệ version theo quy trình của sản phẩm.
4. Nếu không có cách xác định credential hiện hành, dùng quy trình reconciliation/reset được phê duyệt với một danh tính phục hồi độc lập, giới hạn quyền.
5. Xác minh credential cuối cùng, khả năng truy cập cần thiết và việc vô hiệu hóa credential không còn hợp lệ.
6. Ghi sự kiện phục hồi, người thực hiện, tài nguyên bị ảnh hưởng và kết quả.

Không ghi mật khẩu thật vào audit để “bù” cho nguy cơ mất dữ liệu. Không đưa thiết bị đích về một mật khẩu cũ hàng loạt chỉ để khớp bản backup. Việc đó có thể làm sống lại credential đã lộ hoặc cắt dịch vụ đang sử dụng credential mới.

Đối với tài khoản dịch vụ, còn phải xét ứng dụng tiêu thụ secret. Vault, tài khoản ở đích và cấu hình/runtime của ứng dụng có thể ở ba version khác nhau. Việc ứng dụng còn chạy nhờ một kết nối cũ không chứng minh rằng lần kết nối tiếp theo sẽ thành công.

## 10. Mất trạng thái thu hồi quyền khác mất một thay đổi thông thường

Ví dụ, một quyền quản trị được thu hồi lúc 14:58; sự cố xảy ra lúc 15:00; bản phục hồi dừng ở 14:56. Nếu mở lại policy từ bản phục hồi mà không đối soát, tài khoản có thể được cấp quyền trở lại.

RPO 5 phút không phải giấy phép để chấp nhận mọi thay đổi bảo mật trong 5 phút đó bị đảo ngược. Nếu yêu cầu nghiệp vụ là “thu hồi đã xác nhận không được mất hiệu lực”, phải có thiết kế đáp ứng bất biến này trong phạm vi sự cố đã chọn.

Các hướng xử lý có thể gồm:

- Đảm bảo bản ghi thu hồi đã được lưu bền vững ở miền sống sót trước khi xác nhận hoàn tất.
- Có nguồn trạng thái thu hồi độc lập, được bảo vệ và đủ mới để đối soát trước khi cấp quyền.
- Từ chối cấp grant mới khi trạng thái policy hoặc thu hồi chưa đủ tin cậy.
- Áp dụng lại các thu hồi hợp lệ trước khi cho phép truy cập tài nguyên liên quan.
- Dùng thời hạn tuyệt đối và ràng buộc kiểm tra hiệu lực đối với grant JIT.

TTL ngắn chỉ giới hạn một phần cửa sổ rủi ro, không biến thu hồi thành tức thời. Nếu grant hết hạn lúc 15:01 thì bản phục hồi không được tính lại TTL từ thời điểm khởi động để kéo dài nó đến 15:06.

Cũng phải phân biệt thu hồi grant trong PAM với vô hiệu hóa quyền hoặc token ở hệ thống đích. Một phiên đã tồn tại có thể tiếp tục có hiệu lực nếu đích không nhận hoặc không hỗ trợ cơ chế kết thúc tương ứng. Đánh giá phục hồi cần kiểm tra cả đường cấp quyền mới và các quyền đang sống bên ngoài PAM.

## 11. Đo RPO bằng bằng chứng có thể kiểm tra

### 11.1. Xác định watermark cho từng nguồn

Mỗi tập dữ liệu quan trọng nên có một định nghĩa watermark rõ ràng. Ví dụ:

```text
Vault:
  generation, last_contiguous_durable_commit, secret_version_coverage

Policy:
  policy_revision, revocation_watermark

Audit:
  producer_id, epoch, last_contiguous_event_sequence

Recording:
  session_id, last_durable_segment, manifest_version

Key dependency:
  key_generation, available_key_versions
```

Đây là tên khái niệm minh họa, không phải field chuẩn của một sản phẩm.

“Contiguous” nghĩa là liên tục, không có đoạn thiếu chưa được xử lý. Nhìn thấy event sequence 9000 không chứng minh đã có đầy đủ event 1 đến 9000. Trong hệ có nhiều producer, cần watermark theo partition/producer hoặc cơ chế hợp nhất được thiết kế rõ, không tự lấy một sequence lớn nhất làm số liệu chung.

### 11.2. Phân biệt số đo vận hành và bằng chứng diễn tập

Số đo vận hành cho biết khả năng bảo vệ đang suy giảm, chẳng hạn log shipping bị chậm. Diễn tập phục hồi cho biết một tập bản sao cụ thể thực sự phục hồi được đến đâu.

Có thể theo dõi các chỉ số khái niệm:

| Chỉ số | Mục đích |
|---|---|
| Tuổi của điểm phục hồi đã được xác minh | Biết dữ liệu có thể phục hồi đang cũ đến mức nào |
| Độ trễ bền vững ở miền dự phòng | Phát hiện dữ liệu chưa được bảo vệ ngoài miền chính |
| Số gap trong chuỗi log/sự kiện | Tránh coi mốc mới nhất là mốc liên tục |
| Tuổi của backup hợp lệ gần nhất | Phát hiện backup dừng hoặc không sử dụng được |
| Độ mới của trạng thái thu hồi | Kiểm soát quyết định cấp quyền sau failover |
| Số rotation chưa đối soát | Khoanh tài khoản có thể lệch credential |
| Mức bao phủ key version | Phát hiện secret có bản sao nhưng thiếu khóa dùng được |

Không nên gọi tất cả các chỉ số này là RPO. Độ trễ apply 30 giây có thể không đồng nghĩa mất 30 giây dữ liệu nếu log tương ứng đã bền vững và replay được. Ngược lại, receive lag thấp không đủ nếu dữ liệu chưa được lưu bền vững.

### 11.3. Thiết kế cảnh báo có khoảng dự phòng

Với mục tiêu RPO 300 giây, có thể đặt cảnh báo sớm ở 180 giây và ngưỡng nghiêm trọng ở 240 giây. Những mức này chỉ là ví dụ; cần tính thêm chu kỳ lấy mẫu, độ trễ cảnh báo và thời gian người trực phản ứng.

Nếu lần đo cuối đã cũ hoặc nguồn số liệu bị mất, trạng thái phải là “không đủ bằng chứng” hoặc “không xác định”. Không giữ mãi màu xanh từ lần đo thành công trước đó.

Nếu hệ thống cho phép tiếp tục ghi trong khi mất replication, tuổi điểm phục hồi sẽ tăng theo thời gian. Khi vượt mục tiêu, phải ghi nhận vi phạm hoặc trạng thái vận hành suy giảm. Việc tự ngừng một số thao tác thay đổi có thể giảm tổn thất thêm, nhưng không làm những giao dịch đã mất bảo vệ trước đó trở nên an toàn.

## 12. Ví dụ tính RPO và đánh giá kết quả phục hồi

Một doanh nghiệp đặt RPO 5 phút cho vault khi mất site chính. Sự cố xảy ra lúc 10:00:00. Tại site dự phòng:

- Backup nền có điểm nhất quán 09:45:00.
- Chuỗi log liên tục, bền vững và giải mã được đến commit tại 09:56:20.
- File log mang timestamp 09:59:00 có tồn tại nhưng thiếu một đoạn bắt buộc trước đó.
- Hai rotation sau 09:56:20 đã thay đổi credential ở các hệ thống đích.
- Một sự kiện thu hồi đặc quyền lúc 09:58:40 có bằng chứng trong nguồn audit độc lập.

Khoảng lùi phục hồi được chứng minh cho vault là:

```text
10:00:00 - 09:56:20 = 3 phút 40 giây = 220 giây
220 <= 300
```

Xét riêng mục tiêu thời gian của vault, kết quả nằm trong RPO. Không được dùng timestamp 09:59:00 để báo khoảng lùi 60 giây vì chuỗi phục hồi chưa liên tục đến đó.

Nhưng kết quả tổng thể chưa đủ điều kiện mở toàn bộ đặc quyền:

| Hạng mục | Kết quả ban đầu | Hành động cần hoàn tất |
|---|---|---|
| Vault | Phục hồi được đến 09:56:20 | Xác nhận mốc, phụ thuộc khóa và phạm vi dữ liệu |
| Hai tài khoản đã rotation | Có nguy cơ vault/đích khác version | Chặn checkout liên quan, đối soát hoặc reconciliation được phê duyệt |
| Thu hồi lúc 09:58:40 | Chưa nằm trong policy phục hồi | Xác minh bằng chứng và tái áp dụng thu hồi trước khi cấp quyền |
| Log 09:59:00 | Chưa dùng được do thiếu đoạn | Ghi gap, không tính vào watermark |
| Dịch vụ truy cập | Chỉ được mở theo phạm vi đã an toàn | Công bố chức năng hoặc tài nguyên còn bị hạn chế |

Nếu audit chỉ cho biết “đã rotation” mà không chứa secret mới, không thể tái tạo secret mới từ audit. Nguồn đó giúp xác định tài khoản cần đối soát, không thay thế bản sao vault.

Một báo cáo đúng có thể ghi: “Vault đạt mục tiêu khoảng lùi 220/300 giây; hai tài khoản cần reconciliation; quyền bị thu hồi đã được tái áp dụng; chưa mở checkout cho các tài khoản chưa xác minh.” Báo cáo này hữu ích hơn một nhãn “DR PASS” chung cho mọi thành phần.

## 13. Quy trình diễn tập chứng minh RPO

Diễn tập nên thực hiện trong phạm vi được phê duyệt, với tài khoản và dữ liệu thử nghiệm. Không cần sử dụng mật khẩu thật trong báo cáo hay bản chụp màn hình.

### Bước 1 — Khai báo hợp đồng kiểm tra

Ghi rõ kịch bản sự cố, nhóm dữ liệu, mục tiêu RPO, chức năng cần phục hồi, nguồn timestamp và điều kiện an toàn trước khi mở truy cập. Chọn cách thu thập bằng chứng không phụ thuộc hoàn toàn vào site giả lập bị mất.

### Bước 2 — Tạo các thay đổi có thể nhận diện

Dùng operation ID cho các sự kiện thử nghiệm, chẳng hạn:

```text
dr-test-101  tạo secret thử nghiệm
dr-test-102  thay đổi policy giới hạn cho tài nguyên thử nghiệm
dr-test-103  cấp grant JIT có thời hạn tuyệt đối
dr-test-104  thu hồi grant JIT
dr-test-105  rotation tài khoản thử nghiệm
dr-test-106  tạo audit event và recording phiên thử nghiệm
```

Không dùng giá trị secret làm marker. Ghi nhận acknowledgement và version metadata qua nguồn bằng chứng được bảo vệ.

### Bước 3 — Mô phỏng sự cố đúng phạm vi

Nếu bài kiểm tra là mất site, không được tiếp tục dùng dữ liệu chưa được bảo vệ từ site đó rồi coi như site đã mất. Nếu chỉ dừng một node, kết quả không thể tự suy rộng thành chứng minh cho mất toàn bộ region.

Tránh để primary và môi trường khôi phục đồng thời điều khiển cùng tài khoản đích. Cần fencing và giới hạn kết nối tương ứng với thiết kế.

### Bước 4 — Khôi phục vào môi trường được kiểm soát

Dựng lại dữ liệu, khóa, cấu hình và các phụ thuộc cần thiết. Giữ các tác vụ có side effect như rotation, provisioning, mở lại lease hoặc kết nối connector ở trạng thái kiểm soát cho đến khi xác nhận được nguồn ghi có thẩm quyền.

Môi trường diễn tập cô lập không nên tự động kết nối và đổi credential của production do kế thừa lịch chạy từ bản backup.

### Bước 5 — Xác minh trạng thái và hiệu lực

Đối chiếu từng operation ID, commit/version và khoảng log liên tục. Kiểm tra credential bằng quy trình được hỗ trợ với tài khoản thử nghiệm, giới hạn số lần thử để tránh lockout.

Kiểm tra grant đã thu hồi vẫn bị từ chối, grant hết hạn không được gia hạn lại và dữ liệu recording/audit có mức đầy đủ đúng như báo cáo. Chỉ cần ghi kết quả kiểm tra, không ghi secret.

### Bước 6 — Tính kết quả và ghi ngoại lệ

Tính khoảng lùi theo từng nguồn. Ghi rõ giao dịch bị thiếu, nguồn không đủ bằng chứng, tài khoản cần đối soát và thời gian hoàn tất các bước an toàn.

Nếu một dữ liệu quan trọng chưa có watermark tin cậy, ghi “chưa chứng minh được”, thay vì tự gán bằng 0.

### Bước 7 — Đóng diễn tập

Thu hồi quyền và secret thử nghiệm theo kế hoạch; bảo vệ bằng chứng và xác nhận môi trường thử không còn quyền ghi vào production ngoài phạm vi. Mỗi vấn đề phát hiện cần có người phụ trách và tiêu chí kiểm tra lại.

## 14. Một mẫu hợp đồng RPO có thể review

Mẫu dưới đây chỉ minh họa tài liệu thiết kế; không phải cấu hình có thể nạp trực tiếp vào PAM:

```yaml
rpo_contract:
  scope: "Mất toàn bộ site A, site B và dịch vụ khóa phục hồi còn khả dụng"
  clock_reference: "UTC, có giám sát sai lệch"
  datasets:
    - name: "vault"
      target_seconds: 300
      recoverable_point:
        requires:
          - "Chuỗi commit liên tục và bền vững tại site B"
          - "Đủ key version để giải mã"
          - "Snapshot và log cùng một lịch sử hợp lệ"
      acceptance:
        - "Đo được khoảng lùi không quá 300 giây"
        - "Liệt kê rotation thiếu hoặc chưa xác định kết quả"
        - "Không mở checkout cho tài khoản chưa đối soát"

    - name: "revocations"
      security_invariant: "Không cấp lại grant đã được xác nhận thu hồi"
      recovery_gate:
        - "Có trạng thái thu hồi đủ mới theo nguồn đã phê duyệt"
        - "Nếu chưa xác minh thì từ chối cấp quyền liên quan"

    - name: "audit_events"
      target_seconds: 60
      acceptance:
        - "Định danh producer, epoch và sequence liên tục"
        - "Công bố khoảng thiếu và trạng thái bảo toàn bằng chứng"

  evidence:
    include:
      - "Thời điểm sự cố và phạm vi giả lập"
      - "Snapshot ID, commit watermark, key generation"
      - "Operation ID thử nghiệm và kết quả đối chiếu"
      - "Khoảng lùi theo từng tập dữ liệu"
      - "Tài nguyên chưa đủ điều kiện mở truy cập"
    exclude:
      - "Mật khẩu, private key và token có thể sử dụng"
```

Mẫu này giúp người review thấy được mục tiêu, cách chứng minh và điều kiện ra quyết định. Nếu chỉ có `rpo: 5m`, những phần quan trọng nhất vẫn chưa được xác định.

## 15. Những sai lầm thường gặp

### “Có ba node nên RPO bằng 0”

Số lượng node không cho biết giao dịch được xác nhận ở đâu, dữ liệu có bền vững hay không và các node có chung miền sự cố hay không. Cần kiểm tra cơ chế commit và tập bản sao sống sót trong kịch bản đã chọn.

### “Replica còn kết nối nên dữ liệu đã đủ mới”

Heartbeat chỉ chứng minh một dạng kết nối. Replication có thể vẫn kết nối nhưng log chưa đến, chưa bền vững hoặc không replay được. Cần watermark dữ liệu và tuổi số liệu đo.

### “Backup mới nhất luôn là bản phục hồi tốt nhất”

Backup mới nhất có thể chứa lỗi logic, thiếu key version hoặc không hoàn chỉnh. Cần bản mới nhất đáp ứng cả khả năng phục hồi và mức tin cậy của tình huống, đồng thời công bố khoảng lùi phát sinh khi phải chọn bản cũ hơn.

### “Audit có đủ thì dựng lại được toàn bộ vault”

Audit không nên chứa secret thật và thường không có toàn bộ trạng thái cần để dựng lại vault. Nó hỗ trợ đối soát, xác định gap và điều tra, không mặc nhiên là transaction log phục hồi.

### “Khôi phục database xong thì có thể mở lại mọi quyền”

Policy, thu hồi, grant, lease và credential ở đích có thể không đồng nhất với database đã phục hồi. Phải qua các cổng xác minh liên quan trước khi cấp lại đặc quyền.

### “Chấp nhận mất 5 phút dữ liệu nghĩa là chấp nhận mọi quyền cũ sống lại”

Mục tiêu thời gian không xóa bỏ bất biến bảo mật. Nếu yêu cầu không cho phép quyền đã thu hồi xuất hiện trở lại, thiết kế phải giữ hoặc xác minh được trạng thái đó; nếu không, chặn cấp quyền trong thời gian chưa chắc chắn.

### “RPO nhỏ hơn luôn tốt hơn trong mọi hoàn cảnh”

RPO nhỏ thường cần thêm cơ chế bền vững, băng thông, lưu trữ và kiểm thử. Replication đồng bộ qua khoảng cách xa có thể tăng độ trễ và ảnh hưởng khả năng ghi khi mất kết nối. Mục tiêu phù hợp là mức đáp ứng tác động nghiệp vụ và an toàn, có cơ chế đo và nguồn lực duy trì.

## 16. Bài tập thực hành

### Tình huống A — Khoảng lùi và rotation

Sự cố lúc 16:00:00. Vault phục hồi được liên tục đến 15:57:30. Mục tiêu RPO là 180 giây. Một rotation hoàn tất tại đích lúc 15:58:10 nhưng không nằm trong bản vault phục hồi.

Hãy xác định:

1. Khoảng lùi phục hồi và kết quả so với mục tiêu.
2. Tài khoản vừa rotation có đủ điều kiện checkout ngay không.
3. Bằng chứng và quy trình cần dùng để xử lý.

**Gợi ý đối chiếu:** Khoảng lùi là 150 giây, nằm trong mục tiêu 180 giây. Điều đó chưa chứng minh credential trong vault còn hiệu lực. Tài khoản phải được khoanh lại và đối soát/reconciliation theo quy trình được phê duyệt trước khi cấp credential.

### Tình huống B — Thu hồi quyền bị mất trong bản phục hồi

Bản phục hồi policy dừng ở 08:50. Quyền quản trị của tài khoản thử nghiệm bị thu hồi lúc 08:53. Sự cố lúc 08:54. Hệ thống có mục tiêu RPO 5 phút.

Hãy giải thích vì sao không được dùng kết quả “4 phút, đạt RPO” để cho tài khoản tiếp tục truy cập.

**Gợi ý đối chiếu:** Kết quả thời gian của policy không chứng minh tuân thủ bất biến thu hồi. Phải lấy trạng thái thu hồi đủ tin cậy từ nguồn đã phê duyệt hoặc từ chối cấp quyền liên quan cho đến khi xác minh. Nếu không có cơ chế này, thiết kế còn một khoảng trống bảo mật dù mục tiêu thời gian có vẻ đạt.

### Tình huống C — Log đã đến nhưng chưa apply

Sự cố lúc 12:00. Replica đã apply đến 11:55 nhưng có log liên tục, bền vững và giải mã được đến 11:59:30. Mục tiêu RPO là 60 giây.

Hãy phân biệt kết quả khi chỉ dùng trạng thái đã apply với kết quả khi khôi phục và replay được log còn lại.

**Gợi ý đối chiếu:** Trạng thái đã apply có khoảng lùi 300 giây. Nếu thực sự replay thành công và xác minh nhất quán đến 11:59:30, khoảng lùi được chứng minh là 30 giây. Thời gian replay cần được tính trong quá trình khôi phục dịch vụ, không được bỏ qua khi đánh giá RTO.

## 17. Các điểm cần ghi nhớ

RPO của PAM là mục tiêu về độ mới của trạng thái có thể phục hồi trong một phạm vi sự cố cụ thể. Một lịch backup hay một replica đang chạy chưa đủ để chứng minh mục tiêu đó.

Phải đánh giá riêng secret, rotation, policy, thu hồi, grant, audit, recording và khóa giải mã theo phụ thuộc thực tế. Đặc biệt, trạng thái trong PAM có thể khác với credential hoặc quyền còn hiệu lực ở hệ thống đích.

Một kết quả phục hồi có giá trị cần nêu được điểm dữ liệu liên tục đã xác minh, khoảng lùi so với sự cố, thay đổi bị thiếu và điều kiện mở lại đặc quyền. Đạt con số RPO là một phần của kết quả; khả năng truy cập an toàn và nhất quán phải được chứng minh cùng với nó.
