# Rotation compliance trong PAM

Một dashboard hiển thị “100% job rotation thành công” chưa đủ để kết luận hệ thống đã tuân thủ chính sách luân chuyển credential. Job có thể chỉ cập nhật mật khẩu trong vault, trong khi hệ thống đích vẫn dùng giá trị cũ; ứng dụng có thể chưa nhận credential mới; hoặc credential cũ vẫn còn dùng được sau hạn thu hồi.

**Rotation compliance** là mức độ đáp ứng các yêu cầu luân chuyển credential đã được định nghĩa cho một phạm vi tài sản và một thời điểm hoặc kỳ đo cụ thể. Chỉ số này phải nối được ba yếu tố: yêu cầu cần thực hiện, kết quả thực tế trên hệ thống và bằng chứng kiểm chứng kết quả.

Trong Privileged Access Management (PAM), mục tiêu của phép đo là phát hiện nơi credential đặc quyền tồn tại quá lâu, luân chuyển không hoàn tất hoặc không có đủ bằng chứng. Con số phần trăm chỉ có ích khi đội vận hành có thể truy ngược từng trường hợp không đạt để xử lý.

## 1. Phân biệt rotation, kiểm chứng rotation và tuân thủ

Rotation là quá trình thay thế một credential hoặc thế hệ credential bằng một thế hệ mới. Tùy loại credential, quá trình có thể bao gồm tạo mật khẩu mới, cấp API key mới, thay khóa SSH, cấp certificate mới hoặc phát hành một credential động có thời hạn.

Kiểm chứng rotation là xác nhận kết quả cần thiết đã thực sự xảy ra. Ví dụ, credential mới được hệ thống đích chấp nhận, các bên sử dụng cần thiết đã chuyển sang thế hệ mới và credential cũ đã bị vô hiệu hóa hoặc hết hiệu lực theo chính sách.

Tuân thủ rotation là đối chiếu kết quả đã kiểm chứng với yêu cầu về phạm vi, thời hạn và điều kiện hoàn thành. Vì vậy, có thể tồn tại cả ba tình huống sau:

- Rotation được khởi chạy nhưng thất bại: chưa có bằng chứng đáp ứng yêu cầu.
- Rotation hoàn tất nhưng trễ hạn: trạng thái hiện tại có thể đã được khắc phục, song nghĩa vụ đúng hạn của kỳ đo vẫn bị vi phạm.
- Rotation hoàn tất đúng hạn nhưng không nằm trong phạm vi đang được đo: không được cộng vào tử số của phạm vi đó.

Không lấy thời điểm cập nhật bản ghi trong vault làm mặc định cho thời điểm hoàn thành rotation. Thời điểm hoàn thành phải là lúc tất cả điều kiện bắt buộc của chính sách đã đạt và có bằng chứng xác nhận.

### Không áp một chu kỳ chung cho mọi credential

Bài học này không đặt ra một số ngày luân chuyển áp dụng cho mọi hệ thống. Chu kỳ, thời hạn và cơ chế rotation cần xuất phát từ loại credential, mức đặc quyền, mức độ phơi lộ, khả năng tích hợp và chính sách của tổ chức.

Credential đặc quyền dùng chung, secret của dịch vụ, SSH key, certificate ngắn hạn và tài khoản người dùng có các đặc điểm khác nhau. Đặc biệt, không suy từ chỉ số rotation của secret đặc quyền thành yêu cầu đổi định kỳ mọi mật khẩu người dùng.

Một chính sách chưa xác định rõ đối tượng hoặc điều kiện hoàn thành sẽ tạo ra một phép đo không rõ nghĩa, dù dashboard vẫn tính được phần trăm.

## 2. Chọn đúng đơn vị đo

Đơn vị đo cần gắn với đối tượng có thể luân chuyển và có vòng đời độc lập. Một lựa chọn thường dùng là **credential logic**: một credential thuộc một hệ thống có thẩm quyền xác thực, được nhận diện bằng mã ổn định trong inventory.

Ví dụ, credential của tài khoản dịch vụ `svc-reporting` trên một cụm cơ sở dữ liệu có thể được cấp cho nhiều ứng dụng tiêu thụ. Trong phép đo theo credential, đó vẫn là một credential logic; các ứng dụng là những dependency cần kiểm chứng khi chuyển đổi.

Cần phân biệt:

| Đối tượng | Ý nghĩa trong phép đo |
|---|---|
| Tài khoản đặc quyền | Danh tính được cấp quyền; có thể sở hữu nhiều credential |
| Credential logic | Đối tượng vòng đời mà chính sách rotation áp dụng |
| Thế hệ credential | Một phiên bản cụ thể của mật khẩu, key hoặc certificate |
| Bản sao trong vault hoặc cache | Nơi lưu hoặc phân phối một thế hệ; không tự tạo thêm một credential logic |
| Consumer | Ứng dụng, agent, tác vụ hoặc người dùng sử dụng credential |
| Nghĩa vụ rotation | Một yêu cầu cụ thể, có điều kiện đáp ứng và hạn hoàn thành |
| Lần thử rotation | Một attempt thực thi; có thể có nhiều attempt cho cùng một nghĩa vụ |

Một tài khoản có hai API key đồng thời hoạt động không nhất thiết chỉ có một nghĩa vụ rotation. Chính sách cần xác định mỗi key có vòng đời riêng hay hai key là hai thế hệ trong cùng một quy trình chuyển đổi.

Ngược lại, đếm mỗi lần retry như một rotation độc lập có thể làm số lượng “thành công” tăng mà số credential thực sự được bảo vệ không thay đổi.

Đối với certificate hoặc credential động, cần xác định rõ điều gì đang được kiểm soát: tuổi của từng lease, khả năng gia hạn hoặc cấp mới, việc hết hiệu lực của lease cũ, hay rotation của credential gốc dùng để cấp lease. Không gộp các đối tượng này vào một tỷ lệ nếu chúng có điều kiện đạt khác nhau.

## 3. Định nghĩa hợp đồng đo trước khi xây dashboard

Một bản định nghĩa chỉ số rotation compliance nên trả lời tối thiểu các câu hỏi sau:

| Thành phần | Câu hỏi phải trả lời |
|---|---|
| Phạm vi | Credential nào thuộc phạm vi PAM, môi trường nào và hệ thống nào? |
| Chủ sở hữu | Ai chịu trách nhiệm credential, consumer và chính sách? |
| Yêu cầu định kỳ | Tuổi tối đa hoặc lịch rotation được tính từ mốc nào? |
| Yêu cầu theo sự kiện | Sự kiện nào bắt buộc rotation, với thời hạn bao lâu? |
| Điều kiện hoàn thành | Có cần cập nhật đích, chuyển consumer và vô hiệu hóa thế hệ cũ không? |
| Khoảng chuyển tiếp | Hai thế hệ được cùng hoạt động trong bao lâu, nếu được phép? |
| Bằng chứng | Nguồn nào xác nhận mỗi điều kiện và bằng chứng có thời hạn sử dụng không? |
| Ngoại lệ | Ai phê duyệt, áp dụng cho đối tượng nào và hết hạn khi nào? |
| Dữ liệu thiếu | Được hiển thị là chưa biết hay bị coi nhầm là đạt? |
| Thời gian | Dùng múi giờ nào, thời điểm chốt nào và có chấp nhận dữ liệu đến trễ không? |
| Thay đổi phạm vi | Credential mới phát hiện, decommission hoặc chuyển owner được ghi nhận thế nào? |

Yêu cầu theo sự kiện có thể bao gồm rotation sau khi tiết lộ credential cho một phiên truy cập, sau sự cố nghi lộ secret, sau khi kết thúc quyền truy cập của bên thứ ba hoặc sau một thay đổi ownership. Chỉ đưa sự kiện vào phép đo khi chính sách của tổ chức quy định rõ trigger và điều kiện hoàn thành.

Không dùng deadline định kỳ để thay thế deadline theo sự kiện. Một credential còn nhiều ngày trước lịch rotation thông thường vẫn có thể đang vi phạm yêu cầu rotation khẩn cấp.

Mọi ngưỡng trong bài là ví dụ minh họa, không phải chuẩn áp dụng chung hay cam kết của một sản phẩm PAM.

## 4. Xác định đúng thời điểm hoàn thành

Với một secret tĩnh được nhiều ứng dụng sử dụng, quy trình logic có thể được mô tả như sau:

```text
Yêu cầu được tạo
  -> thế hệ mới được tạo và áp dụng tại hệ thống đích
  -> consumer bắt buộc nhận thế hệ mới
  -> kiểm chứng đường truy cập cần thiết bằng thế hệ mới
  -> vô hiệu hóa thế hệ cũ theo điều kiện chuyển tiếp
  -> lưu bằng chứng và xác nhận hoàn thành
```

Thứ tự kỹ thuật cụ thể tùy hệ thống. Ví dụ, mô hình hỗ trợ hai key có thể tạo key mới trước, chuyển consumer rồi thu hồi key cũ. Hệ thống chỉ hỗ trợ một mật khẩu có thể cần một phương án cập nhật và khôi phục khác.

Phép đo phải bám vào điều kiện kiểm soát, không ép mọi hệ thống chạy cùng một sequence.

### Ví dụ: job đã thành công nhưng nghĩa vụ chưa hoàn thành

Một credential được phép tồn tại hai thế hệ trong thời gian chuyển tiếp 15 phút:

| Thời điểm | Sự kiện |
|---|---|
| 09:00 | Job tạo thế hệ mới |
| 09:02 | Vault ghi nhận giá trị mới |
| 09:04 | Hệ thống đích chấp nhận credential mới |
| 09:08 | Consumer bắt buộc chuyển sang thế hệ mới và được kiểm chứng |
| 09:12 | Thế hệ cũ bị vô hiệu hóa và có bằng chứng xác nhận |

Nếu hợp đồng yêu cầu tất cả các điều kiện trên, thời điểm hoàn thành là 09:12. Không lấy 09:02 chỉ vì đó là lúc job trả về thành công.

Nếu deadline là 09:10, rotation hoàn tất trễ hai phút. Nếu deadline là 09:15, rotation hoàn tất đúng hạn. Việc khoảng chuyển tiếp vẫn hợp lệ không tự động nới deadline của nghĩa vụ; chính sách phải nói rõ quan hệ giữa hai giới hạn này.

### Không kiểm chứng bằng cách đưa secret vào hệ thống đo

Kho bằng chứng có thể lưu mã credential, mã thế hệ, mã rotation, thời điểm, nguồn sự kiện và kết quả kiểm chứng. Nó không cần lưu mật khẩu, private key, token hay nội dung secret.

Để xác nhận credential cũ không còn hiệu lực, ưu tiên bằng chứng thu hồi, trạng thái vòng đời hoặc một phép kiểm tra được kiểm soát theo thiết kế của hệ thống. Không thử đăng nhập liên tục bằng credential cũ trên production vì có thể gây khóa tài khoản, nhiễu giám sát hoặc gián đoạn dịch vụ.

## 5. Tính deadline và đánh giá tại một thời điểm

Gọi thời điểm chốt dữ liệu là `T`. Mọi trạng thái trong báo cáo phải được hiểu là trạng thái tại `T`, không phải kết quả của một truy vấn đang thay đổi liên tục.

Với yêu cầu định kỳ, một mô hình đơn giản là:

```text
periodic_due_at = policy_age_baseline_at + max_credential_age
```

`policy_age_baseline_at` phải là mốc được chính sách chấp nhận, chẳng hạn thời điểm thế hệ hiện tại được kích hoạt và kiểm chứng. Không tự dùng `discovered_at` hoặc `imported_into_vault_at` nếu không có bằng chứng về tuổi credential.

Với yêu cầu theo sự kiện:

```text
event_due_at = triggering_event_at + allowed_response_time
```

Một credential có thể có nhiều nghĩa vụ đồng thời. Deadline cần xử lý trước là deadline sớm nhất trong các nghĩa vụ còn mở, nhưng dashboard vẫn phải giữ từng nghĩa vụ để tránh mất lịch sử.

Khi một rotation được chấp nhận là đã đáp ứng nhiều nghĩa vụ, phải có liên kết rõ ràng từ bằng chứng tới từng nghĩa vụ. Một rotation xảy ra trước sự kiện nghi lộ credential không thể tự động đáp ứng nghĩa vụ rotation được kích hoạt bởi sự kiện đó.

### Các trường hợp cần xử lý rõ

**Credential mới phát hiện, chưa biết lần rotation gần nhất:** hiển thị `UNKNOWN` hoặc một trạng thái onboarding được định nghĩa rõ. Không mặc định tuổi bằng không. Nếu có thời gian onboarding được phê duyệt, cần hiển thị riêng để người đọc biết đây chưa phải bằng chứng đạt chính sách thông thường.

**Credential chưa tới hạn:** chỉ được tính đạt tại thời điểm chốt nếu baseline và bằng chứng cần thiết hợp lệ, đồng thời không có nghĩa vụ theo sự kiện đang vi phạm. “Chưa thấy lỗi” không tương đương “đã xác minh đạt”.

**Credential decommission:** chỉ rời phạm vi đang hoạt động sau khi có bằng chứng phù hợp rằng quyền xác thực đã được vô hiệu hóa. Xóa bản ghi trong vault không chứng minh credential tại hệ thống đích đã ngừng sử dụng.

**Đổi chính sách:** phải lưu phiên bản và thời điểm hiệu lực. Nếu tuổi tối đa bị rút ngắn, không chỉnh sửa âm thầm deadline lịch sử để làm thay đổi kết quả đã công bố.

**Không có dữ liệu từ connector:** trạng thái cần phản ánh việc mất khả năng kiểm chứng. Không kéo dài vô hạn trạng thái đạt chỉ vì lần đồng bộ cuối cùng từng thành công.

## 6. Ba phép đo cốt lõi

### 6.1. Tỷ lệ đạt tại thời điểm chốt

Phép đo này trả lời: trong các credential thuộc phạm vi tại `T`, bao nhiêu credential đang đáp ứng chính sách cơ sở và có bằng chứng hợp lệ?

```text
Snapshot rotation compliance(T)
  = số credential đạt chính sách tại T
    / tổng credential thuộc phạm vi tại T
    × 100%
```

Một credential đạt phải đáp ứng toàn bộ điều kiện liên quan theo hợp đồng đo. Chẳng hạn, không quá tuổi tối đa, không vi phạm nghĩa vụ theo sự kiện và có bằng chứng kiểm chứng còn được chấp nhận.

Credential thiếu bằng chứng vẫn nằm trong mẫu số của chỉ số tổng thể nếu nó thuộc phạm vi. Tách số lượng `UNKNOWN` để biết phần không đạt do không tuân thủ đã xác định và phần chưa thể đánh giá.

Nếu mẫu số bằng không, kết quả là `N/A`, kèm lý do không có đối tượng trong phạm vi. Không hiển thị 100% cho một phạm vi trống.

### 6.2. Tỷ lệ hoàn thành đúng hạn theo kỳ

Phép đo này trả lời: trong các nghĩa vụ có deadline thuộc kỳ đo, bao nhiêu nghĩa vụ được đáp ứng đúng hạn?

```text
On-time rotation compliance
  = số nghĩa vụ được kiểm chứng hoàn thành không muộn hơn deadline
    / tổng nghĩa vụ đến hạn trong kỳ
    × 100%
```

Đơn vị ở đây là nghĩa vụ, không phải credential. Một credential có thể tạo nhiều nghĩa vụ trong kỳ; một lần rotation có thể đáp ứng nhiều nghĩa vụ nếu các điều kiện cho phép.

Phải công bố rõ quy tắc ranh giới, ví dụ kỳ đo là `[period_start, period_end)`, còn hoàn thành đúng hạn là `completed_at <= due_at`.

Một nghĩa vụ hoàn tất sau deadline vẫn là `LATE_COMPLETED` trong báo cáo đúng hạn. Không chuyển nó thành đúng hạn chỉ vì đã được khắc phục trước khi lập dashboard.

Đối với kỳ chưa kết thúc, chỉ so sánh những nghĩa vụ đã đến hạn tính tới `T`, và ghi rõ kết quả tạm thời. Không tính các nghĩa vụ còn deadline trong tương lai là đã thất bại.

### 6.3. Backlog quá hạn tại thời điểm chốt

Phép đo này trả lời: còn bao nhiêu nghĩa vụ đã qua deadline nhưng chưa được kiểm chứng hoàn thành?

```text
Overdue backlog(T)
  = số nghĩa vụ chưa đáp ứng có due_at < T
```

Nên phân nhóm backlog theo thời gian quá hạn, mức rủi ro, owner và nguyên nhân. Ví dụ:

- Dưới một ngày.
- Từ một ngày đến dưới ba ngày.
- Từ ba ngày trở lên.
- Chưa xác định được tuổi do thiếu deadline đáng tin cậy.

Nhóm cuối là vấn đề dữ liệu; không đưa nó vào một bucket tuổi ngẫu nhiên. Ngưỡng phân nhóm phải phù hợp thời hạn trong chính sách, nhất là đối với nghĩa vụ khẩn cấp có deadline tính bằng phút hoặc giờ.

Ba phép đo bổ sung cho nhau. Snapshot có thể đã hồi phục sau một đợt xử lý backlog, trong khi tỷ lệ đúng hạn của kỳ vẫn thấp. Đây là hai cách nhìn hợp lệ về hiện tại và lịch sử.

## 7. Ngoại lệ và chất lượng bằng chứng

### 7.1. Ngoại lệ được phê duyệt không đồng nghĩa đã rotation

Một hệ thống cũ có thể chưa hỗ trợ rotation tự động hoặc một dịch vụ có thể cần trì hoãn để tránh gián đoạn. Ngoại lệ phải có đối tượng cụ thể, lý do, người phê duyệt, biện pháp bù trừ, thời điểm hết hạn và kế hoạch xử lý.

Để tránh hiểu nhầm, nên công bố đồng thời:

```text
Strict compliance
  = số credential đạt chính sách cơ sở / toàn bộ credential trong phạm vi

Exception-adjusted compliance
  = số credential đạt chính sách cơ sở
    / (toàn bộ credential trong phạm vi - credential có ngoại lệ hợp lệ)
```

Công thức thứ hai chỉ có ý nghĩa khi tập ngoại lệ được định nghĩa nhất quán, nằm trong phạm vi và không trùng với tập đạt dùng ở tử số. Nếu tổ chức dùng một định nghĩa khác, phải công bố chính xác công thức thay vì giữ cùng tên chỉ số.

Ngoại lệ hết hạn phải trở lại cơ chế đánh giá thông thường. Không gia hạn tự động hoặc chuyển thành “không áp dụng” để tránh tạo backlog.

### 7.2. Ví dụ snapshot với 100 credential

Giả sử tại thời điểm chốt có 100 credential trong phạm vi. Các nhóm sau được phân loại loại trừ lẫn nhau để trình bày:

| Nhóm | Số lượng | Đóng góp vào tử số strict |
|---|---:|---:|
| Đạt chính sách cơ sở và đủ bằng chứng | 82 | 82 |
| Không đạt chính sách cơ sở nhưng có ngoại lệ còn hiệu lực | 5 | 0 |
| Quá hạn, chưa hoàn thành, không thuộc nhóm khác | 4 | 0 |
| Thiếu dữ liệu để xác định trạng thái | 6 | 0 |
| Có kết quả rotation lỗi chưa khắc phục, không thuộc nhóm khác | 3 | 0 |
| Tổng | 100 | 82 |

Khi đó:

```text
Strict compliance             = 82 / 100 × 100% = 82%
Exception-adjusted compliance  = 82 / 95 × 100%  ≈ 86,32%
Known-state coverage          = 94 / 100 × 100% = 94%
```

Coverage 94% chỉ có nghĩa 94 credential có đủ dữ liệu để phân loại theo mô hình này. Nó không có nghĩa 94 credential đã tuân thủ hoặc 94 credential có bằng chứng rotation thành công.

Trong dữ liệu vận hành, một credential có thể vừa rotation lỗi vừa quá hạn. Cần giữ các nhãn nguyên nhân riêng và có quy tắc chọn nhóm hiển thị chính, để bảng tổng không đếm trùng.

### 7.3. Tách độ phủ kiểm chứng thành công

Nếu cần đo bằng chứng rotation thành công, dùng một chỉ số riêng, chẳng hạn:

```text
Verified-rotation evidence coverage
  = số credential có bằng chứng rotation được chấp nhận theo chính sách
    / số credential cần loại bằng chứng đó
```

Không đổi tên chỉ số này thành compliance nếu chưa đối chiếu deadline, scope và nghĩa vụ theo sự kiện.

## 8. Thiết kế dữ liệu có thể truy vết

Một pipeline đo rotation compliance cần giữ được liên kết giữa inventory, chính sách, nghĩa vụ, lần thực thi và bằng chứng.

Ví dụ dưới đây là một cấu trúc minh họa, không phải schema của một sản phẩm PAM:

```json
{
  "obligation_id": "obl-demo-0184",
  "credential_id": "cred-demo-reporting-prod",
  "policy_version": "rotation-policy-v3",
  "trigger_type": "SCHEDULED",
  "not_before_at": "2026-10-10T00:00:00Z",
  "due_at": "2026-10-11T00:00:00Z",
  "rotation_id": "rot-demo-0901",
  "generation_ref": "generation-demo-42",
  "new_generation_verified_at": "2026-10-10T22:02:00Z",
  "required_consumers_verified_at": "2026-10-10T22:06:00Z",
  "old_generation_disabled_at": "2026-10-10T22:12:00Z",
  "completed_at": "2026-10-10T22:12:00Z",
  "evidence_state": "ACCEPTED",
  "evaluated_at": "2026-10-11T00:00:00Z"
}
```

`not_before_at` là thời điểm sớm nhất mà một kết quả được phép đáp ứng nghĩa vụ theo định nghĩa kiểm soát. Với nghĩa vụ sau sự kiện, mốc này ngăn việc dùng rotation trước sự kiện để đáp ứng yêu cầu mới.

Các trường kiểm chứng chỉ là ví dụ của một loại secret tĩnh. Nếu một chính sách không yêu cầu chuyển consumer theo cách này hoặc credential cũ hết hiệu lực tự động, cần dùng bằng chứng tương ứng thay vì bịa các timestamp cho đủ schema.

Những dữ liệu quan trọng khác gồm:

- Mức rủi ro và độ nhạy của hệ thống đích.
- Owner của credential và owner của consumer.
- Loại credential và cơ chế rotation.
- Mã các attempt, kết quả và nguyên nhân lỗi.
- Nguồn bằng chứng, thời gian sự kiện và thời gian thu thập.
- Mã ngoại lệ cùng thời điểm hiệu lực và hết hạn.
- Trạng thái decommission và bằng chứng vô hiệu hóa.
- Phiên bản thuật toán đánh giá và thời điểm snapshot.

Mã thế hệ là định danh không chứa secret, được cấp từ hệ thống vòng đời hoặc inventory. Không tự lấy hash của một mật khẩu yếu để làm mã công khai, vì cách đó có thể tạo thêm dữ liệu hỗ trợ đoán mật khẩu.

### Thời gian sự kiện và thời gian ingest

Một sự kiện có thể xảy ra trước deadline nhưng được thu thập sau deadline. Vì vậy, cần phân biệt:

```text
event_at     = thời điểm hành động kiểm soát thực sự xảy ra
ingested_at  = thời điểm pipeline nhận được sự kiện
```

Báo cáo có thể dùng khoảng chờ dữ liệu đến trễ trước khi chốt. Khi bổ sung dữ liệu sau khi đã công bố, phải lưu phiên bản điều chỉnh và lý do; không viết lại báo cáo mà không để lại dấu vết.

Timestamp từ nguồn không đồng bộ đồng hồ hoặc không có provenance không nên tự động được chấp nhận. Việc đưa dữ liệu về UTC giúp so sánh nhất quán nhưng không sửa được một đồng hồ nguồn sai.

## 9. Ví dụ tính tỷ lệ đúng hạn bằng SQL

Giả sử pipeline đã tạo bảng đánh giá `rotation_obligation_evaluation` với đúng một dòng cho mỗi nghĩa vụ trong một snapshot. Bảng có các trường:

| Trường | Ý nghĩa |
|---|---|
| `snapshot_id` | Mã snapshot cố định |
| `obligation_id` | Định danh nghĩa vụ duy nhất trong snapshot |
| `due_at` | Deadline được chính sách áp dụng |
| `not_before_at` | Mốc sớm nhất chấp nhận kết quả cho nghĩa vụ |
| `completed_at` | Mốc hoàn thành đầy đủ theo bằng chứng |
| `accepted_evidence` | Pipeline đã chấp nhận bằng chứng theo chính sách |
| `risk_tier` | Nhóm rủi ro phục vụ phân tích |

Ví dụ SQL sau dùng cú pháp PostgreSQL và dữ liệu mô hình minh họa. Nó không phải lệnh chạy trực tiếp trên một hệ thống PAM cụ thể. Snapshot `demo-2026-11-08` được giả định đã chốt tại 00:00 UTC ngày 08/11/2026, sau khi toàn bộ deadline trong kỳ đo đã trôi qua.

```sql
WITH params AS (
    SELECT
        'demo-2026-11-08'::text AS snapshot_id,
        TIMESTAMPTZ '2026-11-01 00:00:00+00' AS period_start,
        TIMESTAMPTZ '2026-11-08 00:00:00+00' AS period_end,
        TIMESTAMPTZ '2026-11-08 00:00:00+00' AS as_of
),
cohort AS (
    SELECT
        e.obligation_id,
        e.due_at,
        CASE
            WHEN e.accepted_evidence IS TRUE
             AND e.completed_at >= e.not_before_at
             AND e.completed_at <= p.as_of
            THEN e.completed_at
            ELSE NULL
        END AS accepted_completion_at
    FROM rotation_obligation_evaluation e
    CROSS JOIN params p
    WHERE e.snapshot_id = p.snapshot_id
      AND e.due_at >= p.period_start
      AND e.due_at < p.period_end
      AND p.as_of >= p.period_end
),
totals AS (
    SELECT
        COUNT(*) AS due_obligations,
        COUNT(*) FILTER (
            WHERE accepted_completion_at <= due_at
        ) AS on_time,
        COUNT(*) FILTER (
            WHERE accepted_completion_at > due_at
        ) AS late_completed,
        COUNT(*) FILTER (
            WHERE accepted_completion_at IS NULL
        ) AS unresolved_at_snapshot
    FROM cohort
)
SELECT
    due_obligations,
    on_time,
    late_completed,
    unresolved_at_snapshot,
    ROUND(
        100.0 * on_time / NULLIF(due_obligations, 0),
        2
    ) AS on_time_compliance_pct
FROM totals;
```

Điều kiện `as_of >= period_end` thể hiện đây là báo cáo cho kỳ đã kết thúc. Nếu dùng cho kỳ đang mở, cần một định nghĩa khác chỉ lấy nghĩa vụ đã đến hạn, thay vì giữ nguyên truy vấn rồi diễn giải kết quả như báo cáo hoàn chỉnh.

Truy vấn này dựa trên một tiền đề quan trọng: `accepted_evidence` đã được đánh giá từ đầy đủ điều kiện kiểm soát. Không gán cờ đó bằng cách chỉ kiểm tra `job_status = 'SUCCESS'`.

Ngoài ra, cần kiểm tra tính duy nhất của `(snapshot_id, obligation_id)` trước khi tổng hợp. Nếu join mỗi nghĩa vụ với tất cả attempt hoặc tất cả consumer rồi đếm dòng, mẫu số sẽ bị nhân lên.

### Đọc kết quả minh họa

Một kỳ có:

```text
due_obligations        = 480
on_time                = 432
late_completed         = 24
unresolved_at_snapshot = 24
```

Tỷ lệ đúng hạn là:

```text
432 / 480 × 100% = 90%
```

Có 456 nghĩa vụ đã hoàn thành tính tới snapshot, tương ứng 95%. Tuy nhiên, 95% là tỷ lệ hoàn thành tại thời điểm chốt, không phải tỷ lệ hoàn thành đúng hạn. Hai con số phải có tên và ý nghĩa riêng.

Khi 24 nghĩa vụ còn mở được xử lý trong kỳ tiếp theo, backlog hiện tại giảm. Tỷ lệ đúng hạn của kỳ đã đóng vẫn là 90%, trừ trường hợp có điều chỉnh bằng chứng hợp lệ theo quy trình công bố.

Truy vấn theo deadline trong kỳ không bao gồm backlog cũ có deadline trước đầu kỳ. Dashboard phải có truy vấn riêng cho backlog tại `T`; nếu không, một khoản nợ kiểm soát lâu ngày có thể biến mất khỏi màn hình báo cáo kỳ mới.

## 10. Những sai lệch thường gặp

### Chỉ lấy credential đã được onboard vào vault làm mẫu số

Dashboard có thể đạt 100% dù còn nhiều credential đặc quyền ngoài PAM. Tỷ lệ này chỉ chứng minh kết quả trên tập đã được quản lý.

Cần ghi tên phạm vi rõ ràng và hiển thị độ phủ quản lý hoặc độ phủ phát hiện ở cạnh chỉ số. Không dùng kết quả của tập đã onboard để đại diện cho toàn bộ credential đặc quyền của tổ chức.

### Đếm job thay vì nghĩa vụ hoặc credential

Một credential lỗi có thể tạo hàng chục retry. Nếu đếm các attempt thành công và thất bại, hệ thống có nhiều retry sẽ thay đổi tỷ lệ theo cách không phản ánh mức độ tuân thủ.

Giữ attempt để phân tích độ tin cậy tự động hóa; tổng hợp compliance theo đơn vị đã định nghĩa.

### Cộng trung bình các phần trăm của từng nhóm

Nhóm A đạt 9/10, nhóm B đạt 50/100. Trung bình số học của 90% và 50% là 70%, nhưng tỷ lệ gộp đúng theo số đối tượng là:

```text
(9 + 50) / (10 + 100) × 100% ≈ 53,64%
```

Muốn có tỷ lệ toàn module hoặc toàn tổ chức, cộng tử số và mẫu số của các nhóm không chồng lấn rồi tính lại. Nếu dùng trọng số rủi ro, phải công bố một chỉ số khác với trọng số và cách tính rõ ràng.

### Đổi ngày phát hiện thành ngày rotation

Import một secret cũ vào vault không làm secret đó trở thành mới. Nếu chưa có baseline đáng tin cậy, cần đánh dấu dữ liệu chưa biết và xử lý theo chính sách onboarding.

### Chỉ kiểm tra thế hệ mới

Credential mới dùng được không chứng minh credential cũ đã hết hiệu lực. Với chính sách yêu cầu thu hồi, thiếu bằng chứng thu hồi là thiếu một điều kiện hoàn thành.

### Xóa credential lỗi khỏi inventory

Credential còn được hệ thống đích chấp nhận vẫn tạo rủi ro dù đã bị xóa khỏi công cụ quản lý. Cần bằng chứng decommission thực tế trước khi loại khỏi phạm vi đang hoạt động; giữ lịch sử trong báo cáo kỳ.

### Dùng ngoại lệ để cải thiện chỉ số

Tăng số lượng ngoại lệ có thể làm tỷ lệ đã điều chỉnh tăng mà không có thêm rotation nào hoàn tất. Luôn hiển thị strict compliance, số ngoại lệ, tuổi ngoại lệ và ngày hết hạn.

### Làm xanh dashboard khi mất telemetry

Nếu connector ngừng gửi sự kiện, kết quả phải bộc lộ độ trễ và mức độ không chắc chắn. Không giữ trạng thái xanh vô hạn dựa trên thành công cũ.

## 11. Từ dashboard tới hành động vận hành

Một báo cáo hữu ích nên cho phép đi từ con số tổng tới credential hoặc nghĩa vụ cần xử lý mà không hiển thị secret.

Các cột cần thiết cho danh sách xử lý gồm `credential_id`, hệ thống đích, owner, mức rủi ro, loại nghĩa vụ, deadline, thời gian quá hạn, kết quả gần nhất, bằng chứng còn thiếu và mã ngoại lệ nếu có.

Có thể ưu tiên theo ba chiều:

1. Mức đặc quyền và hậu quả nếu credential bị lạm dụng.
2. Loại trigger, đặc biệt các sự kiện nghi lộ credential hoặc thu hồi quyền khẩn cấp.
3. Thời gian quá hạn và khả năng credential cũ vẫn hoạt động.

Không nên chỉ ưu tiên những credential dễ xử lý để làm phần trăm tăng nhanh. Một credential đặc quyền rất cao có thể quan trọng hơn nhiều credential thử nghiệm dù đóng góp vào tử số như nhau.

### Khi rotation lỗi

Đội vận hành cần xác định lỗi nằm ở đâu: tạo thế hệ, cập nhật hệ thống đích, phân phối cho consumer, xác thực thế hệ mới, thu hồi thế hệ cũ hay ghi nhận bằng chứng.

Trước khi retry, kiểm tra trạng thái thực tế của cả hai thế hệ và các consumer liên quan. Retry mù có thể tạo thêm thế hệ credential, làm lệch trạng thái giữa vault và hệ thống đích hoặc khiến ứng dụng mất truy cập.

Với lỗi liên quan ứng dụng, phối hợp owner của consumer và dùng quy trình thay đổi đã được phê duyệt. Nếu cần ngoại lệ tạm thời, ghi nhận rủi ro và thời hạn cụ thể; không chuyển trạng thái lỗi thành đạt.

### Khi thiếu bằng chứng

Khôi phục nguồn telemetry, đối soát sự kiện hoặc thực hiện bước kiểm chứng được cho phép. Không tự suy ra thành công từ việc ứng dụng vẫn đang chạy: ứng dụng có thể vẫn đang dùng credential cũ từ cache.

### Khi có dấu hiệu lộ credential

Áp dụng quy trình ứng phó sự cố và nghĩa vụ rotation theo sự kiện. Chỉ số compliance cung cấp danh sách và bằng chứng, còn quyết định cô lập, thu hồi phiên hoặc điều tra phải theo phạm vi xử lý sự cố của tổ chức.

## 12. Kiểm tra tính đúng của phép đo với dữ liệu giả lập

Trước khi dùng chỉ số cho báo cáo điều hành, nên kiểm tra bằng một bộ dữ liệu nhỏ có kết quả đã tính tay. Không cần dùng credential thật để xác minh công thức.

Giả sử có sáu nghĩa vụ có deadline trong một kỳ đã kết thúc:

| Nghĩa vụ | Kết quả tại snapshot | Phân loại đúng hạn |
|---|---|---|
| O1 | Bằng chứng hợp lệ, hoàn thành trước deadline | Đạt |
| O2 | Bằng chứng hợp lệ, hoàn thành đúng deadline | Đạt |
| O3 | Bằng chứng hợp lệ, hoàn thành sau deadline | Không đạt; đã khắc phục trễ |
| O4 | Job báo thành công, chưa có bằng chứng thu hồi credential cũ theo yêu cầu | Không đạt; còn mở |
| O5 | Chưa hoàn thành, có ngoại lệ tạm thời | Không đạt theo chính sách cơ sở; theo dõi ngoại lệ riêng |
| O6 | Kết quả rotation được ghi trước mốc sớm nhất chấp nhận của nghĩa vụ theo sự kiện | Không đạt; bằng chứng không đáp ứng nghĩa vụ |

Nếu chỉ xét chính sách cơ sở trong ví dụ này:

```text
Tổng nghĩa vụ đến hạn = 6
Đúng hạn             = 2
Hoàn thành trễ       = 1
Chưa đáp ứng         = 3
Tỷ lệ đúng hạn       = 2 / 6 × 100% ≈ 33,33%
```

Ngoại lệ của O5 cần được công bố cạnh kết quả. Nó không làm O5 trở thành một rotation hoàn thành đúng hạn trong chỉ số strict.

Bổ sung các tình huống biên để kiểm tra pipeline:

- Hai attempt thành công cùng tham chiếu một nghĩa vụ: tử số chỉ tăng một.
- Một credential có hai nghĩa vụ độc lập: giữ cả hai trong phép đo theo nghĩa vụ.
- Bằng chứng đến trễ nhưng thời gian sự kiện đáng tin cậy: áp dụng đúng quy tắc điều chỉnh báo cáo.
- Không có nghĩa vụ trong kỳ: tỷ lệ là `N/A`.
- Credential đổi owner: không mất deadline hoặc lịch sử nghĩa vụ.
- Ngoại lệ hết hạn ngay tại mốc chốt: áp dụng quy tắc hiệu lực đã công bố.
- Có backlog từ kỳ trước: xuất hiện trong backlog hiện tại dù không nằm trong cohort deadline của kỳ mới.
- Không có bằng chứng baseline của credential hiện tại: không tự tính là mới hoặc đạt.

Các kiểm tra này xác minh logic của phép đo. Chúng không thay thế việc kiểm chứng tích hợp rotation trên hệ thống đích.

## 13. Cách trình bày kết quả để người đọc hiểu đúng

Một bản báo cáo rotation compliance nên ghi rõ phạm vi, đơn vị đo, thời điểm chốt, phiên bản chính sách và tình trạng dữ liệu. Ví dụ:

> Tại thời điểm chốt, 82/100 credential thuộc phạm vi đang đáp ứng chính sách cơ sở. Có 5 ngoại lệ còn hiệu lực và 6 credential thiếu dữ liệu để phân loại. Trong kỳ đo, 432/480 nghĩa vụ đến hạn hoàn thành đúng hạn, tương ứng 90%. Backlog quá hạn được theo dõi riêng, bao gồm cả nghĩa vụ từ kỳ trước.

Báo cáo này cho biết cả điều đã xác minh lẫn phần chưa biết, đồng thời phân biệt trạng thái hiện tại với kết quả đúng hạn.

Rotation compliance đáng tin cậy dựa trên inventory đầy đủ, deadline rõ ràng và bằng chứng gắn với kết quả kiểm soát thực tế. Khi một giá trị không đạt xuất hiện, đội vận hành phải trả lời được credential nào, nghĩa vụ nào, thiếu điều kiện gì, ai xử lý và khi nào cần hoàn tất.
