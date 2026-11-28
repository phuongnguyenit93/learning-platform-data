# Atypical time: phát hiện truy cập đặc quyền vào thời điểm bất thường

## 1. Thời điểm truy cập cho biết điều gì trong PAM?

Một tài khoản quản trị đăng nhập máy chủ lúc 02:17 có thể đang xử lý sự cố, thực hiện thay đổi đã được phê duyệt hoặc bị người khác sử dụng credential. Chỉ nhìn đồng hồ không đủ để phân biệt ba trường hợp đó. Tuy nhiên, thời điểm khác hẳn lịch sử của tài khoản thường là tín hiệu đáng kiểm tra, nhất là khi tài khoản có quyền thay đổi hạ tầng nhạy cảm.

Trong giám sát Privileged Access Management (PAM), **atypical time** là thời điểm thực hiện một hành vi đặc quyền lệch đáng kể so với lịch hoạt động kỳ vọng của đúng danh tính, vai trò, hệ thống và loại tác vụ. Hành vi đó có thể là yêu cầu quyền JIT, checkout secret từ vault, mở phiên quản trị, nâng quyền hoặc thực thi thao tác trong một phiên đang mở.

Mục tiêu không phải gắn nhãn mọi hoạt động ban đêm là tấn công. Mục tiêu là trả lời: **vì sao danh tính này cần quyền này, trên tài nguyên này, vào lúc này; có bằng chứng phù hợp không?**

Sau bài học, người học có thể:

- Phân biệt hoạt động ngoài giờ, lệch thói quen và vi phạm cửa sổ cấp quyền.
- Xây dựng baseline thời gian cho người quản trị và tài khoản dịch vụ.
- Chuẩn hóa timestamp, múi giờ và ngữ cảnh phê duyệt để đánh giá một sự kiện.
- Thiết kế cảnh báo, điều tra và điều chỉnh quy tắc mà vẫn giữ bằng chứng kiểm toán.

## 2. Ba câu hỏi thời gian cần đánh giá riêng

### 2.1. Có nằm ngoài lịch hoạt động được quy định không?

Đây là câu hỏi về chính sách hoặc lịch vận hành. Ví dụ, nhóm quản trị cơ sở dữ liệu có ca thường lệ 08:00–17:00 theo múi giờ vận hành, còn tác vụ backup có cửa sổ 02:00–02:20 mỗi ngày.

Đăng nhập lúc 22:15 có thể là hoạt động ngoài ca thông thường. Nếu đội đang trực theo lịch được xác minh, hoạt động ấy vẫn có thể hợp lệ. Cần kiểm tra lịch trực thay vì chỉ áp dụng lịch hành chính chung cho toàn doanh nghiệp.

### 2.2. Có khác lịch sử của danh tính không?

Đây là câu hỏi về hành vi. Một nhân viên thường chỉ dùng quyền quản trị buổi sáng bỗng checkout credential lúc 23:40 là một thay đổi đáng chú ý, ngay cả khi tổ chức cho phép vận hành 24/7.

Ngược lại, một người thường làm ca đêm không nên bị cảnh báo lặp lại chỉ vì giờ đăng nhập nằm ngoài giờ hành chính của trụ sở. Baseline của cá nhân cần được đối chiếu với vai trò và ca làm việc đã xác nhận, không chỉ với trung bình của toàn bộ nhân viên.

### 2.3. Có nằm trong thời hạn quyền thực sự được cấp không?

Đây là câu hỏi về kiểm soát truy cập. Một grant JIT có hiệu lực từ 23:00 đến 00:00 không cho phép mở phiên mới lúc 00:05, dù tài khoản có lịch sử thường xuyên hoạt động vào giờ đó. Hành vi quen thuộc không làm một quyền đã hết hạn trở thành hợp lệ.

| Khía cạnh | Nguồn so sánh | Ví dụ | Ý nghĩa |
|---|---|---|---|
| Ngoài lịch vận hành | Chính sách, ca trực, lịch bảo trì | Quản trị ngoài ca đã phân công | Cần kiểm tra ngoại lệ hoặc nhu cầu vận hành |
| Lệch hành vi | Baseline của danh tính và nhóm tương đồng | Người chỉ làm buổi sáng truy cập lúc nửa đêm | Tín hiệu rủi ro cần thêm ngữ cảnh |
| Ngoài cửa sổ quyền | Grant JIT, TTL, quyết định cấp quyền | Mở phiên sau khi grant hết hiệu lực | Có thể là vi phạm kiểm soát, cần xác minh thực thi |

Ba kết quả nên được lưu riêng. Không gộp chúng thành một cờ `outside_business_hours` rồi sử dụng cho mọi quyết định.

## 3. Chọn đúng sự kiện và đúng đồng hồ

### 3.1. Giám sát nhiều giai đoạn của việc sử dụng đặc quyền

Theo dõi riêng từng giai đoạn giúp nhận ra các tình huống mà chỉ ghi nhận đăng nhập sẽ bỏ sót:

| Giai đoạn | Sự kiện nên quan sát | Câu hỏi thời gian |
|---|---|---|
| Yêu cầu quyền | Tạo yêu cầu JIT, yêu cầu truy xuất secret | Yêu cầu được tạo vào thời điểm khác thường nào? |
| Cấp quyền | Phê duyệt, phát hành grant hoặc credential ngắn hạn | Quyền có hiệu lực trong khoảng nào? |
| Bắt đầu sử dụng | Checkout secret, mở phiên, nâng quyền | Lúc sử dụng có nằm trong phạm vi đã cấp không? |
| Đang sử dụng | Lệnh, thay đổi cấu hình, thao tác nhạy cảm | Có thao tác bất thường sau khi ca hoặc grant kết thúc không? |
| Kết thúc | Đóng phiên, thu hồi quyền, rotation sau sử dụng | Quyền và phiên có kết thúc theo chính sách không? |

Phiên bắt đầu lúc 16:55 nhưng chạy lệnh thay đổi lúc 02:17 cần được đánh giá ở thời điểm lệnh, không được mặc nhiên coi mọi hoạt động của phiên đều xảy ra trong giờ làm việc. Việc hết hạn grant có bắt buộc kết thúc phiên đang chạy hay chỉ chặn phiên mới phụ thuộc thiết kế kiểm soát; người điều tra phải kiểm tra chính sách và hành vi thực tế của hệ thống đó.

### 3.2. Phân biệt event time với ingestion time

**Event time** là lúc hành vi xảy ra tại nguồn; **ingestion time** là lúc hệ thống giám sát nhận được bản ghi. Hai thời điểm có thể khác nhau vì mất mạng, queue tồn, collector khởi động lại hoặc log được gửi theo lô.

Nếu một phiên bắt đầu lúc 14:00 nhưng log chỉ đến SIEM lúc 02:00 hôm sau, dùng ingestion time để phát hiện hoạt động ban đêm sẽ tạo cảnh báo sai. Dùng event time đã được kiểm tra cho phân tích hành vi; giữ ingestion time để phát hiện độ trễ và đánh giá khả năng giám sát.

Không thay event time bằng thời gian nhận log mà không ghi rõ. Nếu nguồn thiếu timestamp đáng tin cậy, kết quả cần biểu diễn tình trạng thiếu dữ liệu, chẳng hạn `time_quality=unknown`, thay vì kết luận chắc chắn là bình thường hoặc bất thường.

### 3.3. Chuẩn hóa UTC, giữ ngữ cảnh múi giờ

Mỗi thời điểm tuyệt đối nên có offset rõ ràng và được chuẩn hóa về UTC để nối dữ liệu giữa vault, máy chủ, hệ thống JIT và SIEM. Đồng thời giữ timestamp gốc, offset nguồn và múi giờ dùng để diễn giải lịch vận hành.

Ví dụ, `2026-10-06T22:15:00+07:00` và `2026-10-06T15:15:00Z` biểu diễn cùng một thời điểm. Không được so trực tiếp số giờ `22` với một lịch được lưu theo UTC.

Với lịch “08:00 theo giờ của nhóm vận hành”, cần định danh múi giờ như `Asia/Ho_Chi_Minh`, không chỉ một chuỗi địa điểm hoặc múi giờ của máy đang chạy bộ phân tích. Những vùng có đổi giờ mùa hè cần thư viện múi giờ phù hợp: có giờ địa phương không tồn tại và có giờ xuất hiện hai lần. Lịch phải quy định cách xử lý hai trường hợp đó.

Múi giờ đánh giá nên xuất phát từ hồ sơ vận hành đã quản lý, chẳng hạn ca trực hoặc vùng của nhóm chịu trách nhiệm. Không tự động đổi baseline theo vị trí IP của từng lần đăng nhập; chính vị trí IP mới có thể là tín hiệu bất thường cần điều tra.

## 4. Dữ liệu tối thiểu cho một quyết định có thể giải thích

Một cảnh báo thời gian hữu ích cần nối được **người yêu cầu**, **tài khoản đặc quyền được dùng**, **tài nguyên**, **phiên** và **cửa sổ quyền**. Với tài khoản dùng chung, lịch sử chỉ của username `root` hay `administrator` không đủ để quy trách nhiệm hoặc xây dựng thói quen của từng người.

| Nhóm dữ liệu | Trường minh họa | Mục đích |
|---|---|---|
| Định danh sự kiện | `event_id`, `source`, `action` | Truy vết bản ghi gốc, chống đếm trùng |
| Thời gian | `event_time_utc`, `ingested_at_utc`, timestamp gốc | Tính đúng thời điểm và nhận diện log đến muộn |
| Danh tính | `requester_id`, `privileged_account_id`, loại danh tính | Phân biệt người sử dụng với tài khoản đích |
| Tài nguyên | `resource_id`, môi trường, mức nhạy cảm | Đánh giá hậu quả tiềm tàng |
| Phiên và quyền | `session_id`, `grant_id`, thời hạn, phạm vi quyền | Nối hành vi với quyền thực sự được cấp |
| Ngữ cảnh vận hành | Ca trực, change hoặc incident, lịch tác vụ | Kiểm chứng lý do hoạt động ngoài lịch thông thường |
| Chất lượng dữ liệu | Clock health, độ trễ, trường bị thiếu | Thể hiện mức tin cậy của kết luận |

Ví dụ sự kiện đã chuẩn hóa, chỉ dùng định danh giả lập:

```json
{
  "event_id": "pam-event-7421",
  "source": "pam-session-gateway",
  "action": "privileged_session_started",
  "event_time_utc": "2026-10-06T15:15:00Z",
  "ingested_at_utc": "2026-10-06T15:15:04Z",
  "source_time": "2026-10-06T22:15:00+07:00",
  "requester_id": "operator-17",
  "privileged_account_id": "db-admin-managed-03",
  "identity_type": "human",
  "resource_id": "db-prod-03",
  "session_id": "session-7421",
  "grant_id": "grant-961",
  "operational_timezone": "Asia/Ho_Chi_Minh",
  "time_quality": "synchronized"
}
```

Không đưa mật khẩu, private key, access token hoặc nội dung secret vào sự kiện để làm giàu ngữ cảnh. Nếu cần điều tra chi tiết phiên, tham chiếu bản ghi phiên được bảo vệ bằng quyền truy cập riêng.

## 5. Xây dựng baseline theo đúng loại danh tính

### 5.1. Người quản trị: ca làm việc và phân bố hoạt động

Baseline nên kết hợp lịch đã biết với lịch sử có chất lượng. Các chiều thường hữu ích gồm giờ trong ngày, thứ trong tuần, ngày nghỉ theo lịch vận hành, loại hành vi và nhóm tài nguyên. Một người có thể mở dashboard vào buổi tối nhưng chỉ thay đổi cấu hình production trong cửa sổ bảo trì; không nên học một lịch chung cho mọi hành vi.

Có thể bắt đầu với các khoảng thời gian thô, ví dụ chia ngày thành những ô 30 phút và phân biệt ngày làm việc với ngày nghỉ. Khoảng lấy mẫu vài tuần là lựa chọn khởi đầu để thử nghiệm, không phải yêu cầu cố định. Tổ chức cần đủ chu kỳ ca trực và bảo trì để dữ liệu đại diện cho công việc thực tế.

Không cần chia dữ liệu thành quá nhiều ô khi mỗi tài khoản chỉ có ít phiên. Một biểu đồ rất chi tiết từ ba lần đăng nhập tạo cảm giác chính xác nhưng không có đủ bằng chứng. Với tài khoản mới hoặc ít hoạt động, ưu tiên lịch vai trò và chính sách, đồng thời ghi rõ baseline cá nhân chưa đủ dữ liệu.

### 5.2. Tài khoản dịch vụ: lịch tác vụ và độ lệch được phép

Đối với workload hoặc tài khoản dịch vụ, lịch đã cấu hình thường quan trọng hơn giờ hành chính. Một lần lấy secret lúc 02:05 có thể hoàn toàn bình thường nếu job được xác nhận chạy lúc 02:00 và thời gian khởi động thay đổi vài phút.

Baseline cần trả lời thêm:

- Lịch chạy được định nghĩa theo UTC hay theo một múi giờ địa phương?
- Có nhiều instance hoặc nhiều vùng chạy cùng tài khoản không?
- Retry và backoff có thể kéo hoạt động ra khỏi cửa sổ nào?
- Sau khi scheduler dừng hoặc job bị hủy, tài khoản có còn hoạt động không?
- Sự kiện là truy cập tự động theo thiết kế hay đăng nhập tương tác của con người?

Đăng nhập tương tác vào một tài khoản chỉ dành cho dịch vụ là một chiều rủi ro riêng; không bỏ qua chỉ vì timestamp khớp lịch job. Tương tự, một job chạy đúng giờ nhưng dùng quyền vượt phạm vi vẫn cần được xử lý theo kiểm soát tương ứng.

### 5.3. Tài khoản khẩn cấp và tài khoản ít dùng

Tài khoản break-glass có thể được dùng rất hiếm và vào bất cứ giờ nào. Lịch sử ít dùng không đủ để xác định một “giờ bình thường” có ý nghĩa. Với loại tài khoản này, trọng tâm là phát hiện mọi lần sử dụng, xác minh người chịu trách nhiệm và lý do khẩn cấp, theo dõi phiên, thu hồi hoặc rotation theo quy trình.

Thời điểm khác thường vẫn là ngữ cảnh bổ sung, nhưng không nên là điều kiện duy nhất để phát hiện sử dụng break-glass. Cũng không chặn đường truy cập khẩn cấp chỉ vì mô hình giờ hoạt động của nhân viên cho điểm cao; cơ chế kiểm soát khẩn cấp cần được thiết kế và thử nghiệm riêng.

### 5.4. Tránh để baseline học sai

Lịch sử không đồng nghĩa với hoạt động hợp lệ. Nếu đưa mọi hoạt động vào quá trình học, hành vi lạm dụng kéo dài có thể dần trở thành “bình thường”. Cần quản lý nguồn dữ liệu huấn luyện và các khoảng thời gian đang điều tra, giữ phiên bản baseline và chỉ thay đổi sau khi có đủ bằng chứng.

Các thay đổi như chuyển ca, chuyển đội, trực hỗ trợ vùng khác hoặc thay đổi scheduler cần được cập nhật có quản lý. Không biến một lần người dùng xác nhận “đó là tôi” thành ngoại lệ vĩnh viễn cho mọi truy cập ngoài giờ.

## 6. Thiết kế quy tắc phát hiện

### 6.1. Bắt đầu bằng điều kiện có thể giải thích

Một quy tắc ban đầu có thể đánh dấu sự kiện nếu hành vi xảy ra ngoài lịch vận hành đã xác minh hoặc ở một ô thời gian hiếm gặp trong baseline phù hợp. Kết quả nên kèm lý do cụ thể, chẳng hạn:

```text
TIME_OUTSIDE_ASSIGNED_SHIFT
TIME_RARE_FOR_IDENTITY
TIME_OUTSIDE_SERVICE_SCHEDULE
TIME_OUTSIDE_ACTIVE_GRANT
TIME_CONTEXT_INCOMPLETE
```

Việc có reason code giúp người trực hiểu cảnh báo xuất phát từ lịch chính sách, mô hình hành vi hay thông tin quyền. Một số điểm rủi ro đơn lẻ không thể thay thế phần giải thích đó.

Nếu dùng tần suất lịch sử, có thể ước lượng mức phổ biến của một ô giờ bằng tỷ lệ sự kiện trong ô đó trên tổng số sự kiện của tập so sánh. Cần nêu rõ tập so sánh là ai, loại hành vi nào và khoảng thời gian nào; có xử lý dữ liệu thưa và mức tin cậy phù hợp.

Ví dụ, 2 trong 120 phiên nằm ở khoảng 00:00–04:00 cho thấy hoạt động ban đêm ít gặp trong tập mẫu đó. Nó không có nghĩa xác suất phiên tiếp theo là tấn công bằng một giá trị suy ra trực tiếp từ tỷ lệ này. Muốn đánh giá tấn công còn cần nhãn điều tra và các tín hiệu khác.

Thời gian trong ngày có tính vòng tròn: 23:55 gần 00:05 hơn 12:00. Không lấy trung bình tuyến tính của 23 và 1 rồi kết luận giờ thường dùng là 12 giờ trưa. Có thể dùng các ô giờ hoặc phương pháp phù hợp với dữ liệu chu kỳ.

### 6.2. Cửa sổ phê duyệt phải khớp phạm vi

Một change đang mở không tự động giải thích mọi hoạt động của người liên quan. Cần đối chiếu người thực hiện, tài nguyên, quyền, loại hành vi, trạng thái phê duyệt và thời hạn có hiệu lực. Ticket được tạo sau sự kiện không phải bằng chứng rằng quyền đã được phê duyệt trước khi truy cập.

Quy ước khoảng nửa mở `[start, end)` giúp xác định ranh giới rõ ràng: có hiệu lực tại thời điểm bắt đầu và hết hiệu lực tại thời điểm kết thúc. Cửa sổ 23:00–00:00 đi qua hai ngày lịch; nên biểu diễn bằng hai timestamp đầy đủ, không chỉ hai con số giờ.

Nếu cho phép dung sai đồng hồ hoặc thời gian khởi động job, dung sai phải được quy định, giới hạn và ghi trong kết quả. Dung sai cho phân tích không được âm thầm kéo dài TTL của credential hoặc quyền JIT ở hệ thống cấp quyền.

### 6.3. Luồng xử lý minh họa

```text
evaluate_time(event):
    t = parse_and_normalize_source_timestamp(event)
    if t is invalid or source_clock_is_untrusted(event.source):
        return INDETERMINATE with TIME_CONTEXT_INCOMPLETE

    schedule = resolve_managed_schedule(
        event.requester_id, event.identity_type, event.resource_id
    )
    baseline = get_versioned_baseline(
        event.requester_id, event.action, event.resource_id
    )

    schedule_result = compare_with_schedule(t, schedule)
    behavior_result = compare_with_baseline(t, baseline)

    if action_requires_grant(event.action):
        grant_result = validate_grant_at_event_time(
            event.grant_id, event.requester_id,
            event.resource_id, event.action, t
        )
    else:
        grant_result = NOT_APPLICABLE

    context = verify_change_or_incident_at_event_time(event, t)
    reasons = collect_reasons(
        schedule_result, behavior_result, grant_result
    )

    return decision_with_evidence(
        reasons, context, data_quality,
        baseline.version, schedule.version
    )
```

Đây là giả mã mô tả các bước, không phải API hoặc cấu hình của một sản phẩm PAM. `data_quality` trong kết quả là tập kiểm tra chất lượng thu được khi xử lý timestamp và tra cứu ngữ cảnh. Khi thiếu lịch hoặc baseline, các hàm so sánh cần trả về trạng thái chưa xác định phù hợp thay vì tự hiểu là có khớp.

Việc thiếu một `grant_id` trong log cũng chưa đủ chứng minh có truy cập trái phép: có thể đường truy cập đó không yêu cầu grant hoặc pipeline đang làm mất trường. Cần xác minh yêu cầu kiểm soát và log nguồn. Nếu kiểm tra chứng minh một grant bắt buộc đã hết hạn nhưng phiên mới vẫn được mở, đó là phát hiện khác về hiệu lực kiểm soát, không chỉ một cảnh báo thời gian hiếm gặp.

### 6.4. Kết hợp tín hiệu để ưu tiên điều tra

Thời điểm bất thường thường có giá trị hơn khi đi cùng các dấu hiệu độc lập: thiết bị chưa từng thấy, tài nguyên production mới, quyền cao hơn nhu cầu, cách xác thực khác thường hoặc thao tác có ảnh hưởng lớn. Các dấu hiệu này cần được xác minh; chúng không tự động chứng minh cùng một nguyên nhân.

| Tình huống | Đánh giá ban đầu | Hướng xử lý |
|---|---|---|
| Ngoài lịch cá nhân, đúng ca trực được xác nhận, đúng grant và tài nguyên | Có lời giải thích vận hành | Ghi nhận ngữ cảnh, giảm ưu tiên theo chính sách |
| Ngoài lịch, đổi thiết bị và truy cập tài nguyên nhạy cảm mới | Nhiều chiều rủi ro | Ưu tiên kiểm tra người dùng, grant và phiên |
| Đúng giờ quen thuộc nhưng dùng quyền ngoài phạm vi | Vấn đề quyền vẫn tồn tại | Điều tra theo kiểm soát quyền, không miễn trừ vì thời gian |
| Ngoài lịch, log đến muộn và đồng hồ nguồn không đáng tin | Chưa đủ cơ sở | Xác minh thời gian, mở vấn đề telemetry nếu cần |
| Dùng break-glass có incident đang xử lý | Hoạt động cần giám sát chặt | Xác minh danh tính và incident, theo dõi theo quy trình khẩn cấp |

Cửa sổ bảo trì hợp lệ có thể giảm mức bất thường do thời gian nhưng không loại bỏ bằng chứng gốc, không tắt các quy tắc khác và không cho phép mở rộng sang mọi tài nguyên.

## 7. Một tình huống xuyên suốt

Nhóm quản trị cơ sở dữ liệu có ca thường lệ 08:00–17:00 theo `Asia/Ho_Chi_Minh`. Người vận hành `operator-17` thường làm ca này. Tối ngày 06/10, người đó được phân công một thay đổi trên `db-prod-03` trong khoảng:

```text
start = 2026-10-06T23:00:00+07:00
end   = 2026-10-07T00:00:00+07:00
scope = operator-17, db-prod-03, database-maintenance
```

Grant JIT cho công việc có cùng phạm vi và cùng khoảng hiệu lực. Xét các sự kiện sau, với giờ được hiển thị theo cùng múi giờ vận hành:

| Sự kiện | Thời điểm | Ngữ cảnh | Nhận định |
|---|---|---|---|
| A | 06/10 22:15 | Mở phiên trước cửa sổ change và grant | Ngoài ca, ngoài cửa sổ; cần xác minh vì sao phiên được cho phép |
| B | 06/10 23:10 | Đúng người, tài nguyên, tác vụ và grant | Hiếm theo lịch sử nhưng có ngữ cảnh đã xác minh |
| C | 07/10 00:05 | Mở phiên mới với grant cũ đã hết hạn | Ngoài cửa sổ; không được xem là hợp lệ nhờ change trước đó |
| D | 07/10 02:17 | Tài khoản dịch vụ backup truy cập đúng job và phạm vi 02:00–02:20 | Giờ đêm nhưng phù hợp lịch dịch vụ |

Đối với A, chưa nên kết luận một lỗi kiểm soát chỉ từ bảng chuẩn hóa. Người điều tra phải kiểm tra có grant hợp lệ khác không, sự kiện là mở phiên thành công hay một lần thử bị từ chối, thời gian có chính xác không và đường truy cập có thuộc PAM không.

Đối với B, sự phù hợp của change giải thích việc truy cập vào giờ hiếm gặp. Tuy nhiên, nếu phiên dùng một quyền khác hoặc chuyển sang tài nguyên khác, cần đánh giá lại phạm vi thay vì áp dụng ngoại lệ cho toàn bộ phiên.

Đối với C, cần phân biệt phiên mới với phiên đang tồn tại. Nếu là phiên mới thành công và không có quyền hợp lệ khác, phải điều tra cả hành vi người dùng lẫn hiệu lực chặn sau hết hạn. Nếu chỉ là một lệnh trong phiên cũ, kiểm tra chính sách hết hạn đối với phiên đang mở rồi đánh giá hành vi theo chính sách đó.

Đối với D, phải xác nhận đúng workload và job; tên tài khoản giống nhau không đủ. Một người đăng nhập tương tác bằng tài khoản backup vào cùng phút đó vẫn cần được xem xét theo quy tắc danh tính và loại truy cập.

## 8. Tạo cảnh báo để người trực có thể xử lý

Một cảnh báo chỉ có nội dung “đăng nhập ngoài giờ” thường buộc người trực tìm lại toàn bộ dữ liệu. Cảnh báo nên cung cấp thời điểm UTC và giờ vận hành, hành vi, danh tính thực, tài khoản đặc quyền, tài nguyên, lý do lệch lịch, kết quả kiểm tra grant và các bằng chứng ngữ cảnh.

Ví dụ thông báo ngắn gọn:

```text
Danh tính: operator-17
Hành vi: mở phiên quản trị tới db-prod-03
Thời điểm: 2026-10-06 15:15:00 UTC
Giờ vận hành: 2026-10-06 22:15:00 Asia/Ho_Chi_Minh
Lý do: ngoài ca đã phân công; sớm hơn cửa sổ change
Grant liên quan: grant-961; cần kiểm chứng hiệu lực tại event time
Chất lượng thời gian: nguồn đồng bộ; ingestion trễ 4 giây
Tham chiếu: event pam-event-7421, session session-7421
```

Nếu một phiên phát sinh nhiều sự kiện tương tự, có thể gom cảnh báo theo danh tính, tài nguyên, phiên và khoảng thời gian. Gom cảnh báo chỉ giảm thông báo lặp, không xóa sự kiện và không bỏ qua hành vi mới có mức ảnh hưởng cao hơn trong cùng phiên. Cần tránh gộp mọi tài nguyên của một tài khoản dùng chung thành một cảnh báo quá rộng.

## 9. Quy trình điều tra và phản ứng

### Bước 1: Xác nhận sự kiện và chất lượng thời gian

Đọc bản ghi nguồn để xác định hành động, kết quả thành công hoặc thất bại, event time và thời gian nhận log. Kiểm tra clock health, chuyển đổi múi giờ và các bản ghi trùng. Khi chưa chắc timestamp, giữ trạng thái chưa xác định và dùng nguồn đối chiếu phù hợp thay vì bỏ cảnh báo.

### Bước 2: Xác minh người hoặc workload thực sự sử dụng quyền

Nối phiên với người yêu cầu, luồng xác thực, thiết bị hoặc workload identity. Đối với tài khoản đặc quyền dùng chung, cần bằng chứng của PAM hoặc hệ thống cấp quyền để xác định người sử dụng; không quy kết chỉ dựa vào username trên máy chủ.

Nếu cần liên hệ người quản trị, dùng kênh xác minh đã được tổ chức quản lý, không chỉ dựa vào chính phiên đang bị nghi ngờ. Xác nhận của người dùng là một bằng chứng cần đối chiếu với phạm vi công việc và log.

### Bước 3: Đối chiếu lịch, quyền và công việc

Kiểm tra ca trực, change, incident và grant tại thời điểm sự kiện. Xác nhận ai phê duyệt, phê duyệt lúc nào, tài nguyên nào, quyền gì và thời hạn nào. Bằng chứng cần phản ánh trạng thái có hiệu lực lúc truy cập; việc ticket hiện tại đã được chỉnh sửa không đủ để tái tạo trạng thái quá khứ.

### Bước 4: Xem chuỗi hành vi liên quan

Đặt sự kiện vào timeline: xác thực, yêu cầu quyền, checkout secret, mở phiên, nâng quyền, thao tác, kết thúc và thu hồi. Tìm thay đổi tài nguyên, cách truy cập, quyền hoặc thiết bị. Xác định có đường truy cập trực tiếp bỏ qua PAM hay không nếu log cho thấy sự khác biệt giữa gateway và hệ thống đích.

### Bước 5: Phản ứng theo bằng chứng và mức ảnh hưởng

Tùy kết quả, hành động có thể là yêu cầu xác minh bổ sung, tăng giám sát, yêu cầu phê duyệt tiếp, thu hồi grant, kết thúc phiên hoặc đưa credential vào quy trình xử lý lộ lọt. Việc kết thúc phiên hay rotation phải xét tác động tới dịch vụ và thực hiện theo runbook đã được cấp thẩm quyền.

Không tự động khóa mọi tài khoản chỉ vì hoạt động vào một giờ hiếm gặp. Tự động hóa có thể áp dụng cho những điều kiện đã xác định rõ, chẳng hạn một yêu cầu ngoài thời hạn quyền phải bị cơ chế cấp quyền từ chối; còn kết luận lạm dụng từ hành vi lệch giờ cần mức bằng chứng phù hợp.

### Bước 6: Kết luận và phản hồi vào hệ thống giám sát

Lưu kết luận như hoạt động hợp lệ đã giải thích, hoạt động nghi ngờ cần điều tra tiếp, hành vi lạm dụng đã xác nhận hoặc không đủ dữ liệu. Nếu là ca trực mới, cập nhật lịch được quản lý; nếu là lỗi telemetry, sửa nguồn dữ liệu; nếu là một ngoại lệ một lần, đặt thời hạn cho ngoại lệ thay vì mở rộng baseline vĩnh viễn.

## 10. Bằng chứng và khả năng tái hiện quyết định

Để phục vụ kiểm toán hoặc ứng phó sự cố, cần có khả năng giải thích vì sao cùng một timestamp được đánh giá như vậy tại thời điểm phát hiện. Một bộ bằng chứng nên gồm:

- Bản ghi gốc hoặc tham chiếu có kiểm soát tới nguồn, event ID và session ID.
- Timestamp gốc, giá trị UTC đã chuẩn hóa, múi giờ vận hành và tình trạng đồng hồ.
- Phiên bản lịch, baseline và quy tắc đã được dùng; mức đầy đủ của mẫu lịch sử.
- Phạm vi và trạng thái grant, change hoặc incident tại event time.
- Reason code, các tín hiệu liên quan, kết luận và người hoặc hệ thống đã xử lý.
- Hành động phản ứng, thời điểm thực hiện và kết quả kiểm tra sau phản ứng.

Quản lý quyền đọc bằng chứng theo least privilege. Nội dung phiên quản trị có thể chứa dữ liệu nhạy cảm; không sao chép toàn bộ nội dung đó vào ticket hay kênh cảnh báo rộng. Giữ lịch sử thay đổi quyết định và cấu hình, áp dụng thời hạn lưu trữ phù hợp với chính sách của tổ chức.

## 11. Bài thực hành mô phỏng

### 11.1. Chuẩn bị dữ liệu giả lập

Không cần dùng credential hay truy cập production. Tạo một tập sự kiện giả với cùng quy ước UTC, gồm hai loại danh tính: người quản trị có ca 08:00–17:00 và dịch vụ backup có cửa sổ 02:00–02:20 theo `Asia/Ho_Chi_Minh`. Khai báo một change và grant của người quản trị từ 23:00 đến 00:00 sang ngày kế tiếp.

Cho mỗi sự kiện, tính riêng bốn kết quả: khớp lịch vận hành, lệch baseline, hiệu lực grant nếu có yêu cầu, và chất lượng thời gian. Sau đó ghi lý do, ngữ cảnh giải thích và hành động đề xuất.

### 11.2. Các trường hợp cần kiểm thử

| Dữ liệu kiểm thử | Kết quả mong đợi |
|---|---|
| Phiên người quản trị lúc 10:00 đúng ca và quyền | Không có lý do bất thường về giờ từ lịch ca |
| Phiên người quản trị lúc 23:10 có change và grant khớp | Giữ dấu hiệu lệch baseline; ghi nhận lời giải thích đã xác minh |
| Phiên cùng giờ nhưng trên tài nguyên khác | Change cũ không giải thích phạm vi mới |
| Phiên mới đúng thời điểm `end` của grant | Nằm ngoài khoảng `[start, end)` |
| Sự kiện trước và sau nửa đêm trong cùng cửa sổ | Xử lý bằng timestamp đầy đủ, không đảo thứ tự giờ |
| Sự kiện 14:00 nhận lúc 02:00 hôm sau | Đánh giá hành vi theo 14:00; ghi riêng độ trễ |
| Timestamp không có offset và không có cấu hình múi giờ nguồn | Chưa đủ cơ sở chuẩn hóa, không tự gán múi giờ máy phân tích |
| Tài khoản mới chỉ có hai phiên lịch sử | Không kết luận mạnh từ baseline cá nhân chưa đủ mẫu |
| Job backup lúc 02:05, đúng workload và phạm vi | Khớp lịch dịch vụ dù ngoài giờ hành chính |
| Đăng nhập tương tác bằng tài khoản backup lúc 02:05 | Lịch đúng không miễn trừ bất thường về loại truy cập |
| Bản ghi bị gửi lại cùng event ID | Không tạo thêm cảnh báo trùng; vẫn truy vết được sự kiện |

Nếu hệ thống phục vụ vùng có đổi giờ mùa hè, bổ sung tình huống giờ bị lặp hoặc bị bỏ qua. Kiểm tra rằng cách xử lý phù hợp với lịch đã công bố, không phụ thuộc ngẫu nhiên vào timezone của máy chạy thử.

### 11.3. Tiêu chí hoàn thành thực hành

Người học cần giải thích được từng kết quả bằng dữ liệu cụ thể, tái hiện được chuyển đổi thời gian và nêu được thông tin còn thiếu. Một kết quả “chưa xác định vì thiếu timestamp đáng tin” là đúng nếu dữ liệu không đủ; tự chọn một múi giờ để tạo kết luận dứt khoát là sai phương pháp.

## 12. Đo hiệu quả và tránh các lỗi thường gặp

Theo dõi khối lượng cảnh báo, tỷ lệ cảnh báo có đủ ngữ cảnh, thời gian xử lý và mức độ bao phủ nguồn log. Với các cảnh báo đã điều tra và có kết luận rõ, có thể tính tỷ lệ cảnh báo thực sự cần xử lý theo định nghĩa của đội vận hành. Cần tách những trường hợp chưa có kết luận; không coi chúng mặc nhiên là đúng hoặc sai để làm đẹp số liệu.

Để đánh giá khả năng phát hiện, dùng các kịch bản giả lập đã biết và các sự cố đã xác nhận. Chỉ quan sát một dashboard không có cảnh báo không chứng minh hệ thống phát hiện tốt; có thể collector đang ngừng gửi dữ liệu hoặc nguồn chưa được tích hợp.

| Lỗi thiết kế | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Một lịch giờ hành chính cho mọi tài khoản | Nhiễu ở đội trực và dịch vụ tự động | Phân theo loại danh tính, ca và lịch job |
| Dùng ingestion time làm giờ truy cập | Cảnh báo sai khi log đến muộn | Giữ và kiểm tra event time, đo độ trễ riêng |
| Tin mọi change đang mở | Ngoại lệ quá rộng | Khớp người, tài nguyên, tác vụ và thời hạn |
| Lấy lịch sử làm bằng chứng cho phép | Bình thường hóa hành vi không hợp lệ | Tách baseline khỏi kiểm tra quyền và chính sách |
| Bỏ hết cảnh báo trong maintenance | Mất tín hiệu ngoài phạm vi thay đổi | Chỉ điều chỉnh lý do liên quan tới cửa sổ đã xác minh |
| Khóa tự động theo một tín hiệu giờ | Gián đoạn vận hành hợp lệ | Dùng phản ứng có điều kiện và mức bằng chứng phù hợp |
| Không lưu phiên bản baseline | Không giải thích được quyết định cũ | Ghi phiên bản và bằng chứng tại lúc đánh giá |

## 13. Tự kiểm tra kiến thức

**Một người thường làm ca đêm có nên luôn bị cảnh báo vì truy cập lúc 02:00 không?** Không. Cần so với ca đã xác minh và baseline phù hợp. Quyền, tài nguyên và hành vi vẫn phải được kiểm tra độc lập.

**Change từ 23:00 đến 00:00 có hợp thức hóa phiên mới lúc 00:05 không?** Không. Cần có quyền hợp lệ tại thời điểm mở phiên; lịch sử của người dùng hoặc change đã kết thúc không tự gia hạn quyền.

**Một sự kiện đúng giờ quen thuộc có thể nguy hiểm không?** Có. Kẻ lạm dụng có thể hoạt động trong giờ bình thường; thời gian chỉ là một chiều giám sát, không thay thế least privilege, xác thực, kiểm tra grant hay giám sát thao tác.

**Thông tin quan trọng nhất khi cảnh báo “khác giờ thường lệ” là gì?** Là mốc thời gian đáng tin, danh tính thực, baseline hoặc lịch đang so sánh, quyền có hiệu lực, phạm vi công việc và bằng chứng giải thích sự khác biệt. Thiếu các yếu tố này, cảnh báo khó được xử lý đúng.

Phát hiện atypical time có giá trị khi nó tạo được một câu hỏi điều tra cụ thể và có thể kiểm chứng. Trong PAM, kết quả cần nối thời điểm với người sử dụng, quyền được cấp và công việc thực tế, để vừa nhận ra lạm dụng đặc quyền vừa hỗ trợ vận hành hợp lệ.
