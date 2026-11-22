# Biểu diễn trạng thái đồng ý, mục đích sử dụng và thời gian hiệu lực

## 1. Vì sao một cột đồng ý dạng Boolean là không đủ?

Trong module **DATABASE_DATA_MODELING**, bài toán chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu phải trả lời được các câu hỏi về thực thể, quan hệ, ràng buộc, khóa, chỉ mục và dữ liệu lịch sử. Ở chương **Bảo vệ dữ liệu**, một yêu cầu thường gặp là lưu sự đồng ý của chủ thể dữ liệu đối với những hoạt động xử lý cụ thể.

Giả sử một sàn thương mại điện tử có khách hàng **501**. Doanh nghiệp muốn thực hiện các hoạt động:

- Gửi email quảng cáo sản phẩm.
- Gửi thông báo khuyến mại qua ứng dụng.
- Cá nhân hóa gợi ý sản phẩm dựa trên lịch sử truy cập.
- Gửi thông báo vận hành về đơn hàng.
- Chia sẻ một tập thông tin đã định với đối tác phục vụ một mục đích cụ thể.

Nếu bảng khách hàng chỉ chứa:

~~~sql
marketing_consent boolean
~~~

thì khi giá trị là TRUE, hệ thống không thể tự trả lời:

1. Khách đã đồng ý **mục đích nào**: email, push, cá nhân hóa hay tất cả?
2. Đồng ý cho **đơn vị xử lý hoặc phạm vi thương hiệu nào**?
3. Đồng ý từ **thời điểm nào** và có **hết hạn** không?
4. Khách đã xem **nội dung thông báo và phiên bản chính sách nào**?
5. Ai hoặc kênh nào ghi nhận lựa chọn; có bằng chứng hành động chủ động không?
6. Khách đã rút lại đồng ý vào lúc nào?
7. Một chiến dịch chạy ngày 10/03 có dựa trên trạng thái được biết vào ngày ấy không?
8. Khi nhận thông tin rút lại muộn do thiết bị mất mạng, cần giải thích quyết định đã thực hiện trước đó thế nào?

Một Boolean có thể là **projection hiện tại** để đọc nhanh, nhưng nó không đủ thay thế toàn bộ mô hình đồng ý có phạm vi, bằng chứng và lịch sử.

**Đề bài chính:** biểu diễn rõ **chủ thể**, **mục đích sử dụng**, **phạm vi**, **trạng thái lựa chọn**, **thời gian có hiệu lực**, **thời gian ghi nhận** và **bằng chứng**. Từ đó phải xác định được hoạt động nào được cho phép theo chính sách áp dụng, đồng thời giữ khả năng giải thích và kiểm chứng.

Bài học không coi mọi hoạt động xử lý dữ liệu đều dựa trên sự đồng ý: tùy bối cảnh và quy định áp dụng, một hoạt động có thể dựa vào **cơ sở xử lý khác**. Mô hình consent phải được sử dụng **chỉ khi sự đồng ý là cơ sở cần thiết hoặc có liên quan**, không thay thế toàn bộ hệ thống chính sách về xử lý dữ liệu.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt trạng thái đồng ý với quyền xử lý tổng thể và với hành động truy cập dữ liệu.
2. Thiết kế một sự lựa chọn theo **chủ thể – mục đích – phạm vi – phiên bản thông báo – thời gian**.
3. Xác định **GRANTED, DENIED, WITHDRAWN, EXPIRED, UNKNOWN** và ngữ nghĩa chuyển trạng thái.
4. Dùng khoảng hiệu lực **[from, to)** để lưu lựa chọn có hiệu lực ở từng thời điểm.
5. Phân biệt **valid time**, **accepted/recorded time** và khả năng tái dựng kiến thức lịch sử.
6. Thiết kế bảng bằng chứng, nhật ký quyết định và projection hiện tại trong PostgreSQL.
7. Đặt ràng buộc chống chồng lấn, xử lý ghi đồng thời, retry và rút lại đồng ý.
8. Xây truy vấn as-of và quy trình kiểm tra trước hoạt động xử lý.
9. Kết hợp bảo vệ dữ liệu với phân tán, document, graph và mô hình phân tích khi cần.

## 2. “Đồng ý” không phải một thuộc tính bất biến của khách hàng

Một khách có thể đồng ý nhận email quảng cáo nhưng từ chối push notification. Họ có thể đồng ý cá nhân hóa gợi ý cho thương hiệu A nhưng không cho thương hiệu B. Ngày hôm nay họ đồng ý, tháng sau họ rút lại.

Vì vậy **consent không nên được mô hình hóa như thuộc tính vĩnh viễn của thực thể Customer**.

Một lựa chọn đồng ý cần ngữ cảnh:

~~~text
Consent choice =
    Subject
  + Purpose
  + Processing scope
  + Choice / decision
  + Effective time
  + Evidence and notice version
~~~

Ví dụ:

~~~text
Chủ thể:       Customer 501
Mục đích:      MARKETING_EMAIL
Phạm vi:       Brand A / địa chỉ email thuộc tài khoản
Lựa chọn:      GRANTED
Hiệu lực từ:   2026-02-01 09:00 UTC
Bằng chứng:    Web form, notice v3, request R-100
~~~

Một lựa chọn khác cho chính khách này:

~~~text
Chủ thể:       Customer 501
Mục đích:      PERSONALIZATION
Phạm vi:       Brand A / hành vi duyệt sản phẩm
Lựa chọn:      DENIED
Hiệu lực từ:   2026-02-01 09:00 UTC
~~~

Không có mâu thuẫn giữa hai hàng vì chúng áp dụng cho **mục đích khác nhau**.

### 2.1. Những thực thể cốt lõi

| Thực thể | Vai trò |
|---|---|
| **DataSubject** | Chủ thể dữ liệu hoặc định danh được hệ thống sử dụng có kiểm soát |
| **ProcessingPurpose** | Mục đích xử lý được quản trị bằng mã, mô tả và phiên bản |
| **ConsentScope** | Phạm vi lựa chọn: controller, thương hiệu, kênh, nhóm dữ liệu, hoạt động liên quan |
| **ConsentNotice** | Nội dung đã được trình bày khi xin lựa chọn; bản lưu hoặc tham chiếu có thể kiểm chứng |
| **ConsentDecision** | Một hành động lựa chọn đã được ghi nhận: cấp, từ chối, rút lại, cấp lại |
| **ConsentStateHistory** | Projection trạng thái có hiệu lực theo khoảng thời gian |
| **ProcessingPolicy** | Quy tắc quyết định hoạt động có được phép thực hiện hay không, gồm cơ sở xử lý phù hợp |
| **ProcessingRecord** | Bằng chứng một hoạt động xử lý đã diễn ra hoặc đã bị chặn, nếu cần kiểm toán |

Những thực thể này có thể là các bảng khác nhau, hoặc một phần nằm trong dịch vụ chính sách. Việc tách trách nhiệm giúp tránh nhầm **bằng chứng đồng ý** với **trạng thái hiện tại** hoặc **kết quả quyết định quyền xử lý**.

## 3. Phân biệt mục đích sử dụng với kênh và loại dữ liệu

**Mục đích xử lý (purpose)** trả lời câu hỏi: **“Dùng dữ liệu để làm gì?”**

Ví dụ:

- **MARKETING_EMAIL:** gửi nội dung tiếp thị qua email.
- **MARKETING_PUSH:** gửi quảng cáo qua ứng dụng.
- **PERSONALIZED_RECOMMENDATION:** cá nhân hóa gợi ý dựa trên hành vi.
- **PARTNER_OFFER_SHARING:** chia sẻ dữ liệu theo phạm vi để đối tác gửi ưu đãi.
- **ORDER_FULFILLMENT:** xử lý đơn hàng và giao hàng theo cơ sở xử lý được xác định.

Tên kỹ thuật phải đi cùng **mô tả nghiệp vụ dễ hiểu**, không chỉ một mã bí ẩn.

**Kênh (channel)** trả lời “thực hiện bằng gì?”: email, push, SMS, web.

**Danh mục dữ liệu (data category)** trả lời “dùng dữ liệu nào?”: lịch sử mua, sự kiện duyệt trang, địa chỉ liên hệ.

**Đơn vị kiểm soát/phạm vi nhận dữ liệu** trả lời “ai đang xử lý hoặc nhận dữ liệu trong phạm vi thỏa thuận?”.

Ba trục này có thể liên quan nhưng không đồng nhất. Một mục đích marketing có thể dùng nhiều kênh, và mỗi kênh có thể đòi lựa chọn riêng theo chính sách. Không thiết kế một cột **purpose = email** nếu “email” vừa có thể là loại dữ liệu liên hệ vừa là kênh vận chuyển.

### 3.1. Danh mục purpose phải được quản trị

| Thuộc tính | Ví dụ | Yêu cầu thiết kế |
|---|---|---|
| purpose_code | MARKETING_EMAIL | Mã ổn định, có định nghĩa |
| display_name | Nhận email ưu đãi | Dễ hiểu với chủ thể |
| purpose_description | Gửi nội dung quảng cáo... | Phù hợp nội dung đã được công bố |
| processing_activity | SEND_MARKETING_CAMPAIGN | Liên kết hoạt động thực tế |
| data_categories | EMAIL_ADDRESS, PURCHASE_SEGMENT | Chỉ những loại dữ liệu được dùng |
| controller_scope | BRAND_A | Phạm vi tổ chức áp dụng |
| policy_version | POLICY-2026-02 | Phiên bản quy tắc đang có hiệu lực |

Một thay đổi **căn bản** về mục đích không nên âm thầm đổi mô tả của cùng purpose_code rồi coi mọi lựa chọn cũ là hợp lệ cho mục đích mới. Có thể cần purpose_code mới, notice mới và quy trình xin lựa chọn mới theo chính sách áp dụng.

### 3.2. Không gộp tất cả thành một hộp kiểm

Ví dụ mẫu giao diện:

~~~text
[ ] Tôi đồng ý nhận email tiếp thị.
[ ] Tôi đồng ý nhận thông báo quảng cáo qua ứng dụng.
[ ] Tôi đồng ý cho phép cá nhân hóa gợi ý từ hành vi duyệt.
~~~

Ba lựa chọn riêng dễ phản ánh trạng thái và phạm vi hơn một checkbox **“Tôi đồng ý với mọi điều khoản”**. Thiết kế giao diện và điều kiện đồng ý cụ thể còn phải đáp ứng quy định pháp lý phù hợp; bài này tập trung vào việc **mô hình dữ liệu có thể giữ đúng các lựa chọn đã được thu thập**.

## 4. Ranh giới giữa sự đồng ý và quyền xử lý dữ liệu

Một hệ thống có thể có:

~~~text
ConsentState(subject, purpose) = GRANTED
~~~

nhưng điều đó **chưa đủ** để kết luận mọi hoạt động xử lý đều được phép. Còn phải xét:

- Có đúng mục đích đã được mô tả không?
- Dữ liệu cần dùng có nằm trong phạm vi cho phép và cần thiết không?
- Người thực hiện và hệ thống xử lý có quyền truy cập không?
- Thời hạn và điều kiện đã hết hiệu lực chưa?
- Có giới hạn riêng về chủ thể, nhóm dữ liệu hoặc người đại diện không?
- Chính sách xử lý và nghĩa vụ pháp lý hiện áp dụng là gì?
- Có yêu cầu dừng xử lý, xóa, hạn chế hoặc phản đối nào khác không?

Ngược lại, **không có consent GRANTED** không chứng minh rằng **mọi** hoạt động xử lý đều bị cấm: một hoạt động có thể được cho phép trên một cơ sở xử lý khác, nếu điều đó thực sự phù hợp luật và chính sách. Ví dụ thông báo trạng thái đơn hàng không nên tự động bị đồng nhất với gửi email quảng cáo.

Vì vậy cần tách:

~~~text
ConsentEvidence     = điều chủ thể đã lựa chọn và bằng chứng
ProcessingPolicy    = cơ sở và điều kiện xử lý
AuthorizationResult = quyết định cho một hoạt động cụ thể tại thời điểm T
~~~

**Quy tắc an toàn:** nếu một hoạt động **bắt buộc phải có đồng ý**, mà hệ thống không tìm thấy bằng chứng GRANTED hợp lệ cho đúng mục đích/phạm vi, hãy **không thực hiện hoạt động ấy** cho đến khi được xác minh. Đây là cách **fail closed cho tuyến xử lý dựa trên consent**, không phải một kết luận pháp lý cho mọi hoạt động dữ liệu.

## 5. Trạng thái lựa chọn: phân biệt cấp, từ chối và rút lại

Một trạng thái đơn lẻ TRUE/FALSE làm mất nhiều ngữ nghĩa quan trọng.

| Trạng thái hoặc kết quả | Nghĩa | Có được coi là đồng ý hiện hành? |
|---|---|---|
| **GRANTED** | Có sự lựa chọn chấp thuận hợp lệ trong phạm vi và thời điểm | Có, nếu mọi điều kiện khác đáp ứng |
| **DENIED** | Chủ thể đã chủ động từ chối một yêu cầu lựa chọn | Không |
| **WITHDRAWN** | Chủ thể rút lại một lựa chọn đã cấp trước đó | Không, từ mốc rút lại có hiệu lực |
| **EXPIRED** | Một grant hết thời hạn theo quy tắc được công bố | Không, sau khi hết hạn |
| **UNKNOWN / NO_RECORD** | Không có bản ghi đủ tin cậy hoặc chưa từng hỏi | Không được suy ra GRANTED |
| **INVALIDATED** | Bằng chứng bị xác định không hợp lệ hoặc bị hủy theo quy trình | Không, khi việc vô hiệu hóa có hiệu lực |

Không nhất thiết lưu **EXPIRED** thành một sự kiện riêng nếu đã có **valid_to** hoặc **expires_at** trên grant. Khi truy vấn ở sau thời hạn, kết quả có thể là **EXPIRED** được suy ra từ khoảng thời gian.

Tương tự, **UNKNOWN** là **trạng thái tri thức của hệ thống**, không nhất thiết là một quyết định từ chối của chủ thể. Nếu chưa từng xin lựa chọn, không nên tạo một event **DENIED** giả chỉ để tiện truy vấn.

### 5.1. Một máy trạng thái đơn giản

~~~mermaid
flowchart LR
    U["UNKNOWN"] -->|chấp thuận| G["GRANTED"]
    U -->|từ chối| D["DENIED"]
    G -->|rút lại| W["WITHDRAWN"]
    G -->|hết thời hạn| E["EXPIRED"]
    D -->|chấp thuận mới| G
    W -->|chấp thuận mới| G
    E -->|chấp thuận mới| G
~~~

Sơ đồ chỉ mô tả **ý nghĩa lựa chọn**, không thay thế workflow xác minh bằng chứng, điều kiện pháp lý, năng lực của người đại diện hoặc kiểm tra quyền. Một sự kiện như **WITHDRAW** khi không có grant trước đó có thể được ghi là hành động yêu cầu rút, nhưng không được sửa lịch sử thành “đã từng đồng ý” nếu không có chứng cứ.

### 5.2. Không xóa bản ghi GRANTED khi chủ thể rút lại

Nếu ngày 01/02 có consent GRANTED, ngày 10/03 bị rút lại, việc xóa hàng grant hoặc cập nhật thành FALSE mất đi câu trả lời:

> “Tại thời điểm gửi email ngày 05/03, hệ thống có bằng chứng đồng ý nào?”

Cần giữ **lịch sử lựa chọn và bằng chứng** theo retention hợp lý, đồng thời ngăn xử lý tiếp sau khi rút lại có hiệu lực. Điều này khác với việc giữ mọi dữ liệu cá nhân vô thời hạn.

## 6. Thời gian hiệu lực khác với thời gian hệ thống biết

Một hành động có thể chứa nhiều mốc:

| Trường | Ý nghĩa |
|---|---|
| **source_action_at** | Thời điểm client cho biết chủ thể đã bấm chọn/rút lại |
| **received_at** | Server nhận yêu cầu lúc nào |
| **accepted_at** | Hệ thống có thẩm quyền chấp nhận quyết định lúc nào |
| **effective_at** | Quyết định bắt đầu ảnh hưởng đến phạm vi xử lý lúc nào |
| **expires_at** | Grant hết hiệu lực theo điều kiện nào |
| **recorded_at** | Bản ghi được đưa vào hệ thống hoặc log khi nào |
| **known_period** | Hệ thống coi một phiên bản thông tin là đã biết trong khoảng nào |
| **processed_at** | Một tác vụ sử dụng consent đã được thực thi lúc nào |

Đặc biệt **source_action_at** từ thiết bị ngoại tuyến có thể không đáng tin tuyệt đối vì đồng hồ sai. **accepted_at** do server cấp đáng tin hơn cho điều tra vận hành nhưng chưa chắc là thời điểm **COMMIT chính xác** của transaction.

**effective_at** phải có quy tắc rõ: ví dụ grant có hiệu lực khi hệ thống chấp nhận và xác minh bằng chứng; withdrawal được áp dụng từ thời điểm phù hợp chính sách và nghĩa vụ đáp ứng yêu cầu. Không để client tùy ý điền một ngày quá khứ để hợp thức hóa một grant chưa tồn tại khi xử lý đã xảy ra.

### 6.1. Ví dụ qua ba giai đoạn

Giả sử khách 501 lựa chọn về **MARKETING_EMAIL** cho Brand A:

~~~text
01/02/2026 09:00 UTC: GRANTED
10/03/2026 10:00 UTC: WITHDRAWN
02/04/2026 08:00 UTC: GRANTED lại (notice mới)

Timeline hiệu lực:

[01/02 09:00, 10/03 10:00) GRANTED
[10/03 10:00, 02/04 08:00) WITHDRAWN
[02/04 08:00, +∞)         GRANTED
~~~

Câu hỏi:

- **05/03:** được coi là GRANTED trong timeline này.
- **10/03 đúng 10:00:** không còn GRANTED; thuộc khoảng WITHDRAWN.
- **20/03:** WITHDRAWN.
- **05/04:** GRANTED lại nếu có bằng chứng và điều kiện hợp lệ.

**Grant mới không làm cho khoảng bị rút lại trong tháng 3 trở thành grant.** Lịch sử phải giữ nguyên để giải thích.

### 6.2. Khoảng nửa mở [from, to)

Quy ước:

~~~text
A <= time < B

[2026-02-01 09:00, 2026-03-10 10:00) GRANTED
[2026-03-10 10:00, 2026-04-02 08:00) WITHDRAWN
~~~

Biên **10/03 10:00** chỉ thuộc trạng thái WITHDRAWN. Tránh dùng hai khoảng đều bao gồm biên, hoặc dùng 09:59:59.999 làm biên kết thúc, vì precision timestamp có thể thay đổi.

## 7. Đơn vị thời gian: UTC, timezone và quy tắc hết hạn

Với hoạt động xử lý thực hiện tại thời điểm tuyệt đối, dùng **timestamptz** trong PostgreSQL và trao đổi theo timestamp có offset rõ. Một lựa chọn hết hạn theo **ngày lịch địa phương** cần quy tắc chuyển đổi:

- Hết hạn ở đầu ngày hay cuối ngày?
- Ngày theo timezone của chủ thể, quốc gia hay controller?
- Nếu chủ thể chuyển múi giờ, thời hạn có thay đổi không?
- Nếu vùng có daylight saving time, độ dài ngày không cố định.
- Nếu hạn là “sau 90 ngày”, là **90 × 24 giờ** hay **90 ngày lịch** theo timezone chỉ định?

Ví dụ chính sách “hết hạn lúc bắt đầu ngày 01/05 theo giờ Việt Nam” tương ứng:

~~~text
valid_to = 2026-05-01 00:00:00+07
         = 2026-04-30 17:00:00 UTC
~~~

Không tự lấy **DATE(timestamp_utc)** để suy ngày địa phương hoặc đặt thời gian “vô hạn” khi notice thực tế nêu thời hạn hữu hạn.

### 7.1. Thời gian của quyết định có thể khác thời gian tác vụ

Một chiến dịch marketing được lên lịch lúc 08:00 nhưng thực sự gửi lúc 09:00. Nếu khách rút đồng ý lúc 08:30, **kiểm tra lúc tạo lịch** không đủ cho việc gửi lúc 09:00.

Cần xác định **thời điểm kiểm tra hợp lệ** theo hoạt động: trước khi đưa vào hàng chờ, ngay trước khi gửi và khi consumer thực hiện, tùy yêu cầu. Một decision cache cần TTL, invalidation và khả năng áp thay đổi withdrawal kịp thời.

## 8. Chọn grain cho consent: một hàng đại diện cho gì?

Grain của **ConsentDecision**:

> Một hành động lựa chọn đã được chấp nhận (hoặc được ghi nhận là không hợp lệ/từ chối tùy luồng) của một chủ thể, đối với một mục đích và một phạm vi cụ thể, gắn với thời điểm và bằng chứng.

Grain của **ConsentStateHistory**:

> Một đoạn trạng thái có hiệu lực liên tục cho đúng tổ hợp (tenant, subject, purpose, scope).

Hai loại dữ liệu có grain **khác nhau**. Một hành động rút lại có thể dẫn đến việc đóng một đoạn trạng thái GRANTED và mở một đoạn WITHDRAWN. Một request giao diện có thể cập nhật ba purpose cùng lúc, tạo **ba quyết định** riêng, nhưng cùng request/correlation ID.

### 8.1. Khóa nghiệp vụ của một luồng lựa chọn

Một luồng có thể được nhận diện bởi:

~~~text
(tenant_id, subject_id, purpose_code, scope_key)
~~~

Trong đó **scope_key** là mã đã chuẩn hóa và quản trị, ví dụ:

~~~text
BRAND_A:EMAIL
BRAND_A:PUSH
BRAND_A:PERSONALIZATION
BRAND_B:EMAIL
~~~

Đây chỉ là cách minh họa mã phạm vi; trong hệ thống lớn có thể tách controller_id, channel_code, data_category, processing_activity thành các cột hoặc bảng tham chiếu có quy tắc hơn.

Không để người dùng gửi một chuỗi tùy ý rồi coi mỗi biến thể chữ hoa/khoảng trắng là phạm vi mới.

### 8.2. Tại sao phải tách subject và source identity?

Chủ thể có thể dùng web, app và CRM với ba ID nguồn. Nếu consent chỉ lưu user_id của từng ứng dụng, hệ thống khó bảo đảm quyết định rút lại được áp dụng cho cùng chủ thể khi đi qua các kênh.

Có thể dùng **canonical_subject_id** được cấp có kiểm soát, cùng bảng ánh xạ các ID nguồn. Nhưng việc hợp nhất tài khoản phải được xác minh; không tự gộp hai hồ sơ chỉ vì email hoặc tên giống nhau. Với thiết bị chưa đăng nhập, phạm vi lựa chọn có thể chỉ áp dụng cho **device/browser identifier**, không được mặc định gắn vào mọi tài khoản có thể liên quan.

## 9. Bằng chứng đồng ý cần lưu những gì?

Một bảng trạng thái GRANTED không chứng minh đủ **chủ thể đã thấy gì và đã thao tác như thế nào**.

Những thông tin có thể cần giữ:

- **notice_id / notice_version**: phiên bản nội dung được trình bày.
- **notice_content_ref**: tham chiếu tới nội dung được lưu bền.
- **content hash**: dấu băm kiểm tra tính toàn vẹn nội dung, nếu áp dụng.
- **locale**: ngôn ngữ nội dung.
- **capture_channel**: web, mobile, tổng đài hoặc biểu mẫu.
- **interaction_type**: checkbox chọn chủ động, xác nhận từ tài khoản đã xác thực, quy trình văn bản, v.v.
- **actor/representative**: ai thực hiện, có đại diện hợp lệ hay không.
- **source_decision_key**: ID của lựa chọn từ nguồn, dùng chống retry.
- **accepted_at và effective_at**: phân biệt ghi nhận và hiệu lực.
- **scope/purpose**: lựa chọn thực sự áp dụng cho gì.
- **evidence_ref**: tham chiếu tới bằng chứng được phép giữ.
- **policy/processing version**: hệ thống diễn giải quyền xử lý theo phiên bản quy tắc nào.

Không nên lưu mật khẩu, token xác thực, dữ liệu thẻ thanh toán, toàn bộ nội dung HTTP request hoặc dữ liệu cá nhân không cần thiết chỉ để “chứng minh đồng ý”.

**Hash không thay cho nội dung thực sự đã trình bày.** Nếu chỉ giữ một hash mà không còn nội dung/phiên bản có thể phục hồi, hệ thống khó giải thích chủ thể đã đọc điều gì. Cũng không được mặc nhiên coi một hash đơn lẻ là bảo đảm chống giả mạo nếu quyền quản trị, lưu trữ và đường ghi chưa được bảo vệ.

### 9.1. Lịch sử notice phải bất biến về nội dung được công bố

Nếu notice v3 được dùng để lấy lựa chọn tháng 2, không được sửa đè text của v3 thành nội dung mới tháng 4 rồi vẫn ghi cùng version.

Thiết kế có thể:

~~~text
notice_id=N3
version=3
locale=vi-VN
purpose=MARKETING_EMAIL
content_ref=immutable://privacy/notice/N3/vi-VN
digest=...
published_at=...
~~~

Khi có thay đổi mang ý nghĩa mới, tạo version mới. Quy trình xin đồng ý lại phụ thuộc thay đổi đó có làm vượt phạm vi lựa chọn cũ hay không, theo chính sách pháp lý được xác định.

## 10. Mô hình ER: sự kiện quyết định, trạng thái và bằng chứng

~~~mermaid
erDiagram
    DATA_SUBJECT ||--o{ CONSENT_SCOPE : "có các phạm vi lựa chọn"
    PROCESSING_PURPOSE ||--o{ CONSENT_SCOPE : "được xét theo mục đích"
    CONSENT_SCOPE ||--o{ CONSENT_DECISION : "ghi nhận hành động"
    CONSENT_SCOPE ||--o{ CONSENT_STATE_HISTORY : "phiên bản trạng thái"
    CONSENT_NOTICE ||--o{ CONSENT_DECISION : "căn cứ thông báo"
    CONSENT_DECISION ||--o{ CONSENT_STATE_HISTORY : "nguồn quyết định"
    DATA_SUBJECT {
        bigint tenant_id PK
        uuid subject_id PK
    }
    PROCESSING_PURPOSE {
        text purpose_code PK
        text description
    }
    CONSENT_SCOPE {
        bigint tenant_id PK
        uuid subject_id PK
        text purpose_code PK
        text scope_key PK
        bigint revision
    }
    CONSENT_NOTICE {
        uuid notice_id PK
        text purpose_code
        text notice_version
        text locale
    }
    CONSENT_DECISION {
        uuid decision_id PK
        text action_code
        timestamptz effective_at
        timestamptz accepted_at
        text evidence_ref
    }
    CONSENT_STATE_HISTORY {
        bigint state_version_id PK
        text state_code
        tstzrange valid_period
        uuid source_decision_id
    }
~~~

Mô hình sử dụng **decision log** làm bằng chứng hành động, còn **state history** là biểu diễn tối ưu cho truy vấn trạng thái as-of. Hai bảng có thể ghi trong một transaction khi cùng database.

Một dự án có thể chọn event sourcing làm nguồn sự thật rồi dựng state history bằng projection. Dự án khác có thể dùng state history làm nguồn để quyết định trạng thái, đồng thời ghi decision event cho kiểm toán. Phải nêu rõ **nguồn có thẩm quyền** và cơ chế đối soát, không để hai bảng tự thay đổi độc lập rồi cho ra kết quả khác nhau.

## 11. PostgreSQL: bảng chủ thể, mục đích và phạm vi

Ví dụ dùng **timestamptz** và **tstzrange** của PostgreSQL. Cần extension **btree_gist** để hỗ trợ các toán tử bình đẳng trong GiST exclusion constraint ở phần sau.

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE data_subject (
    tenant_id  bigint NOT NULL,
    subject_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, subject_id)
);

CREATE TABLE processing_purpose (
    purpose_code text PRIMARY KEY,
    display_name text NOT NULL,
    description text NOT NULL,

    CONSTRAINT ck_purpose_code_not_blank
        CHECK (length(btrim(purpose_code)) > 0)
);

CREATE TABLE consent_scope (
    tenant_id    bigint NOT NULL,
    subject_id   uuid NOT NULL,
    purpose_code text NOT NULL
                 REFERENCES processing_purpose(purpose_code),
    scope_key    text NOT NULL,
    revision     bigint NOT NULL DEFAULT 0
                 CHECK (revision >= 0),

    PRIMARY KEY (tenant_id, subject_id, purpose_code, scope_key),

    FOREIGN KEY (tenant_id, subject_id)
        REFERENCES data_subject(tenant_id, subject_id),

    CONSTRAINT ck_scope_key_not_blank
        CHECK (length(btrim(scope_key)) > 0)
);
~~~

**consent_scope** lưu một hàng ổn định cho tổ hợp chủ thể–mục đích–phạm vi. Ngoài tác dụng làm FK, nó là **điểm khóa giao dịch** khi cập nhật nhiều phiên bản trạng thái: có thể SELECT ... FOR UPDATE trên đúng hàng scope trước khi đóng/mở khoảng.

Các hệ thống production cần kiểm tra quyền truy cập theo tenant, quản trị danh mục scope và tích hợp policy version. DDL này cố ý là mô hình trọng tâm, không phải toàn bộ hệ thống tuân thủ.

### 11.1. Mục đích khác cơ sở xử lý

Bảng **processing_purpose** ghi mục đích. Nó chưa tuyên bố mọi purpose cần consent. Hệ thống nên có **processing policy** riêng xác định mục đích, loại hành động, controller, nguồn dữ liệu và cơ sở xử lý theo thời điểm.

Không tạo một cột **consent_required boolean** bất biến trên purpose_code rồi dùng nó làm lời giải pháp lý trong mọi thị trường, mọi loại chủ thể và mọi thời kỳ, nếu các điều kiện ấy có thể thay đổi.

## 12. PostgreSQL: lưu notice và decision append-only

### 12.1. Bản thông báo

~~~sql
CREATE TABLE consent_notice (
    notice_id      uuid PRIMARY KEY,
    purpose_code   text NOT NULL
                   REFERENCES processing_purpose(purpose_code),
    notice_version text NOT NULL,
    locale_code    text NOT NULL,
    content_ref    text NOT NULL,
    content_sha256 char(64) NOT NULL,
    published_at   timestamptz NOT NULL,

    UNIQUE (purpose_code, notice_version, locale_code)
);
~~~

**content_sha256** là dấu băm của nội dung thực tế, không phải chuỗi ngẫu nhiên do ứng dụng tự chế. Cần định nghĩa định dạng canonical của nội dung được băm và cách lưu bản gốc. Chỉ lưu hash là chưa đủ nếu muốn phục hồi nội dung đã công bố.

### 12.2. Nhật ký quyết định

~~~sql
CREATE TABLE consent_decision (
    decision_id     uuid PRIMARY KEY,
    tenant_id       bigint NOT NULL,
    subject_id      uuid NOT NULL,
    purpose_code    text NOT NULL,
    scope_key       text NOT NULL,

    action_code     text NOT NULL
                    CHECK (
                        action_code IN (
                            'GRANT', 'DENY', 'WITHDRAW'
                        )
                    ),

    effective_at    timestamptz NOT NULL,
    source_action_at timestamptz,
    accepted_at     timestamptz NOT NULL
                    DEFAULT statement_timestamp(),

    notice_id       uuid REFERENCES consent_notice(notice_id),
    capture_source  text NOT NULL,
    source_decision_key text NOT NULL,
    evidence_ref    text,

    FOREIGN KEY (
        tenant_id, subject_id, purpose_code, scope_key
    ) REFERENCES consent_scope (
        tenant_id, subject_id, purpose_code, scope_key
    ),

    UNIQUE (
        tenant_id, capture_source, source_decision_key
    ),

    CONSTRAINT ck_grant_has_evidence
        CHECK (
            action_code <> 'GRANT'
            OR (notice_id IS NOT NULL AND evidence_ref IS NOT NULL)
        )
);
~~~

Trong mô hình này **source_decision_key** phải là ID riêng cho **mỗi lựa chọn theo purpose/scope** do nguồn capture phát, không phải ID chung của toàn form có ba checkbox. Nếu một form có nhiều lựa chọn, dùng cùng **correlation_id** (có thể bổ sung) để ghép các decision, nhưng mỗi decision phải có danh tính riêng để chống retry.

Ràng buộc UNIQUE bảo vệ theo namespace **tenant + capture_source + source_decision_key**. Nếu ID nguồn chỉ duy nhất theo một phần khác, phải điều chỉnh khóa theo hợp đồng nguồn.

**notice_id** được yêu cầu khi GRANT, nhưng chỉ có FK chưa chứng minh notice ấy đúng purpose, locale, phạm vi và nội dung đã hiển thị. Đường ghi phải xác minh điều đó; có thể bổ sung khóa tham chiếu composite hoặc policy validator nếu cần bảo đảm mạnh hơn.

### 12.3. Không sửa lịch sử bằng UPDATE tùy tiện

Decision log nên được xem như **bằng chứng hành động**. Khi phát hiện một quyết định bị ghi sai hoặc cần đính chính, ghi **decision/correction mới** với liên kết đến quyết định trước thay vì âm thầm sửa mọi trường của bản cũ.

Điều đó không có nghĩa dữ liệu audit được giữ mãi mãi bất chấp yêu cầu xóa/hạn chế dữ liệu. Cần cơ chế retention, tối thiểu hóa và quyền sửa/xóa được kiểm soát theo quy định áp dụng.

## 13. PostgreSQL: projection trạng thái theo khoảng hiệu lực

~~~sql
CREATE TABLE consent_state_history (
    state_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tenant_id    bigint NOT NULL,
    subject_id   uuid NOT NULL,
    purpose_code text NOT NULL,
    scope_key    text NOT NULL,

    state_code   text NOT NULL
                 CHECK (
                     state_code IN (
                         'GRANTED', 'DENIED', 'WITHDRAWN'
                     )
                 ),

    valid_period tstzrange NOT NULL,
    source_decision_id uuid NOT NULL
                       REFERENCES consent_decision(decision_id),

    FOREIGN KEY (
        tenant_id, subject_id, purpose_code, scope_key
    ) REFERENCES consent_scope (
        tenant_id, subject_id, purpose_code, scope_key
    ),

    CONSTRAINT ck_consent_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_one_consent_state_per_instant
        EXCLUDE USING gist (
            tenant_id WITH =,
            subject_id WITH =,
            purpose_code WITH =,
            scope_key WITH =,
            valid_period WITH &&
        )
);
~~~

Grain của bảng: **một trạng thái có hiệu lực trong một khoảng liên tục cho một scope cụ thể**.

Ràng buộc **EXCLUDE** từ chối hai hàng cùng tổ hợp tenant/subject/purpose/scope mà **valid_period giao nhau**. Nó bảo vệ câu hỏi “tại thời điểm B có tối đa một trạng thái”.

**Ràng buộc không tự bảo đảm luôn có một trạng thái**. Nếu chưa có record, hoặc có khoảng trống giữa hai quyết định, truy vấn sẽ không trả hàng. Đối với xử lý yêu cầu consent, trường hợp thiếu trạng thái phải được diễn giải **không có grant hợp lệ**, chứ không được mặc định GRANTED.

### 13.1. Expiration nằm ở biên của grant

Nếu grant hết hạn lúc T:

~~~text
GRANTED: [t0, T)
Sau T:   không còn GRANTED
~~~

Có thể đóng grant ở T mà **không cần INSERT EXPIRED** nếu hệ thống chỉ cần biết grant còn hiệu lực không. Nếu cần báo trạng thái EXPIRED để hiển thị hoặc kiểm toán, có thể suy từ lý do kết thúc của grant hoặc lưu event/state phù hợp. Nhưng không tạo những event “chủ thể đã chủ động rút” khi thực tế chỉ có thời hạn tự hết.

### 13.2. Decision và state phải khớp cùng scope

FK đến decision_id đơn lẻ chỉ bảo đảm **decision tồn tại**, không chứng minh một hàng state tham chiếu đến decision đúng **tenant, subject, purpose, scope**. Đường ghi và data-quality tests phải kiểm tra khớp các trường này; có thể tăng thành composite foreign key nếu cần thực thi ngay tại database.

Không để hàng GRANTED của Brand A tham chiếu nhầm decision cấp cho Brand B chỉ vì UUID decision có thật.

## 14. Dữ liệu mẫu: một khách, một purpose, ba giai đoạn

Giả sử:

~~~text
tenant_id    = 1
subject_id   = 501 (ký hiệu nghiệp vụ)
purpose_code = MARKETING_EMAIL
scope_key    = BRAND_A:EMAIL

01/02 09:00 UTC: khách chấp thuận notice v3
10/03 10:00 UTC: khách rút lại
02/04 08:00 UTC: khách đồng ý lại theo notice v4
~~~

Timeline được projection:

| Từ (UTC) | Đến (UTC, loại trừ) | Trạng thái | Căn cứ |
|---|---|---|---|
| 01/02/2026 09:00 | 10/03/2026 10:00 | GRANTED | Decision D1, notice v3 |
| 10/03/2026 10:00 | 02/04/2026 08:00 | WITHDRAWN | Decision D2 |
| 02/04/2026 08:00 | Không giới hạn | GRANTED | Decision D3, notice v4 |

Bảng trên dùng subject 501 để dễ đọc, còn SQL DDL dùng **subject_id uuid** do hệ thống cấp. Đây là hai cách biểu diễn ví dụ, không phải câu lệnh INSERT nguyên xi.

### 14.1. Không chia sẻ grant sang purpose khác

Nếu cùng khách có:

~~~text
MARKETING_EMAIL: GRANTED
PERSONALIZATION:  DENIED
MARKETING_PUSH:   UNKNOWN
~~~

thì truy vấn email marketing có thể dựa trên GRANTED nếu các điều kiện khác đều đúng. Nhưng push quảng cáo và cá nhân hóa **không được mặc nhiên hưởng quyền đó**.

Nếu Brand B muốn gửi email, GRANTED ở **BRAND_A:EMAIL** không tự chuyển thành GRANTED ở **BRAND_B:EMAIL** trừ khi phạm vi được công bố và lựa chọn ban đầu thực sự bao gồm Brand B theo quy tắc đã xác minh.

### 14.2. Một lựa chọn được cấp lại là quyết định mới

D3 không nên sửa D1 thành “đồng ý liên tục từ 01/02”. Chính khoảng WITHDRAWN tháng 3 là một phần quan trọng của lịch sử, vì đã có những hoạt động cần dừng trong giai đoạn đó.

## 15. Truy vấn consent as-of tại một thời điểm

Trong PostgreSQL, toán tử **@>** kiểm tra một khoảng chứa timestamp.

Ví dụ lấy trạng thái tại 05/03/2026:

~~~sql
SELECT
    state_code,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to,
    source_decision_id
FROM consent_state_history
WHERE tenant_id = :tenant_id
  AND subject_id = :subject_id
  AND purpose_code = 'MARKETING_EMAIL'
  AND scope_key = 'BRAND_A:EMAIL'
  AND valid_period @> TIMESTAMPTZ '2026-03-05 12:00:00+00';
~~~

Các tham số **:tenant_id** và **:subject_id** do ứng dụng bind, không phải biến có sẵn của PostgreSQL. Với timeline ví dụ, truy vấn trả **GRANTED**.

### 15.1. Một cờ kiểm tra cho tuyến xử lý cần consent

~~~sql
SELECT COALESCE((
    SELECT state_code = 'GRANTED'
    FROM consent_state_history
    WHERE tenant_id = :tenant_id
      AND subject_id = :subject_id
      AND purpose_code = :purpose_code
      AND scope_key = :scope_key
      AND valid_period @> :operation_at
), FALSE) AS has_active_grant;
~~~

Vì exclusion bảo đảm tối đa một hàng khớp tại một thời điểm, scalar subquery không bị nhiều hàng nếu constraint hoạt động. Khi không có hàng, **COALESCE(..., FALSE)** trả FALSE.

**Đây chỉ là một bước kiểm tra grant.** Kết quả TRUE chưa thay thế kiểm tra mục đích thực tế, cơ sở xử lý, quyền truy cập, loại dữ liệu, điều kiện notice và chính sách hạn chế khác.

### 15.2. Kết quả mong đợi

| Operation time | Kết quả grant hiện hiệu lực |
|---|---|
| 05/03/2026 12:00 UTC | TRUE |
| 10/03/2026 09:59 UTC | TRUE |
| 10/03/2026 10:00 UTC | FALSE |
| 20/03/2026 12:00 UTC | FALSE |
| 05/04/2026 12:00 UTC | TRUE |
| Ngày trước 01/02 khi không có bản ghi | FALSE |

Nếu grant có thời điểm hết hạn riêng, phần khoảng phía trên phải phản ánh chính xác thời hạn ấy. Không được tiếp tục trả TRUE chỉ vì trạng thái cuối cùng từng là GRANTED.

## 16. Cập nhật giao dịch: cấp, rút và cấp lại phải nguyên tử

Một lựa chọn mới tác động tới cả:

- Decision log (bằng chứng hành động).
- State projection (quyền có hiệu lực).
- Có thể thêm outbox để truyền thay đổi sang dịch vụ email, analytics hoặc data warehouse.
- Revision của scope phục vụ concurrency.

Nếu ghi decision rồi cập nhật state thất bại mà không rollback/đối soát, hai nguồn có thể mâu thuẫn.

### 16.1. Giao thức khi chỉ cập nhật phiên bản cuối

Giả sử chỉ xử lý những quyết định có **effective_at muộn hơn đầu khoảng đang mở**, không có quyết định tương lai hoặc correction hồi tố:

~~~text
BEGIN TRANSACTION

1. Tìm CONSENT_SCOPE đúng tenant + subject + purpose + scope.
2. SELECT ... FOR UPDATE khóa hàng scope.
3. Xác thực request idempotency, quyền và bằng chứng.
4. Kiểm tra effective_at hợp lệ và trình tự với trạng thái đang mở.
5. INSERT CONSENT_DECISION mới.
6. Đóng valid_period của trạng thái cũ tại effective_at.
7. INSERT CONSENT_STATE_HISTORY mới bắt đầu tại effective_at.
8. Tăng revision của scope.
9. INSERT outbox event nếu cần gửi thay đổi.
10. COMMIT.

Nếu bất kỳ bước nào lỗi: ROLLBACK và không xác nhận thành công.
~~~

Khóa hàng scope ổn định giúp hai request của cùng chủ thể/mục đích/phạm vi không cùng chia khoảng dựa trên trạng thái cũ. **Exclusion constraint** là lớp bảo vệ bổ sung, ngăn kết quả overlap ngay cả khi một luồng bỏ qua quy tắc cập nhật.

### 16.2. Không được đóng khoảng khi effective_at bằng điểm đầu

Nếu hệ thống vừa có GRANTED bắt đầu 10:00 mà request WITHDRAW mới cũng được áp dụng đúng 10:00, việc đặt **[10:00, 10:00)** tạo khoảng rỗng và phải bị từ chối. Cần xác định **thứ tự quyết định tại cùng mốc**, có thể hợp nhất trạng thái cuối theo logic nghiệp vụ trong transaction và giữ cả decision event.

Không tự cộng một microsecond vào effective_at để né ràng buộc, vì hành động đó làm sai thời điểm nghiệp vụ.

### 16.3. Hồi tố hoặc quyết định tương lai phức tạp hơn

Nếu đang có:

~~~text
GRANTED [01/02, 01/05)
WITHDRAWN [01/05, +∞)
~~~

rồi ngày 10/04 nhận một quyết định có hiệu lực từ 15/03, không thể chỉ “đóng hàng cuối và mở hàng mới”. Phải:

1. Xác định **đoạn chứa điểm hiệu lực**.
2. Kiểm tra quyết định có thẩm quyền và cách xử lý hồi tố.
3. Chia timeline tại các mốc cần thiết.
4. Giữ những quyết định tương lai còn hợp lệ.
5. Kiểm tra các khoảng không overlap.
6. Lưu vì sao lịch sử hiệu lực được thay đổi.
7. Xem xét tác động tới quyết định xử lý đã được thực hiện trong quá khứ.

Đừng backdate grant chỉ để hợp thức hóa hoạt động mà hệ thống đã làm trước khi có chứng cứ.

### 16.4. Idempotency của một lựa chọn

Nếu web app gửi lại decision D2 do timeout sau commit, phải phát hiện đó là **cùng lựa chọn** và trả kết quả cũ, không tạo thêm một lần rút lại làm rối timeline.

Khóa UNIQUE của source_decision_key trong bảng decision hỗ trợ dedup. Nhưng nếu cùng key được gửi với purpose, scope, action hoặc evidence khác, phải báo **conflict**, không coi đó là retry giống hệt.

## 17. Rút lại đồng ý: kết thúc quyền cho tương lai, giữ chứng cứ lịch sử

Rút lại đồng ý không phải xóa Boolean GRANTED thành FALSE rồi coi là xong.

Một quy trình đầy đủ cần:

1. Cho chủ thể gửi yêu cầu qua những kênh được hỗ trợ.
2. Xác định chủ thể và thẩm quyền đại diện phù hợp.
3. Xác định **purpose và scope** bị rút lại.
4. Ghi nhận thời điểm action, received và accepted; áp dụng effective_at theo chính sách.
5. Đóng khoảng grant hiện hành.
6. Ghi decision withdrawal với request_id và bằng chứng tối thiểu.
7. Cập nhật projection/cache/segment được dùng cho xử lý mới.
8. Truyền sự kiện ngừng sử dụng tới downstream liên quan.
9. Bảo đảm các tác vụ gửi/chia sẻ dữ liệu đang chờ được kiểm tra lại.
10. Theo dõi việc áp dụng rút lại và các xử lý ngoại lệ.

### 17.1. Rút lại không mặc nhiên xóa hết mọi bản ghi trước đó

Một số dữ liệu có thể đã được xử lý hợp lệ trước khi withdrawal có hiệu lực; một số record có thể cần giữ theo nghĩa vụ độc lập hoặc cho chứng cứ, tùy luật/chính sách. Đồng thời, mục đích xử lý dựa vào consent đã bị rút **không được tiếp tục sử dụng dữ liệu chỉ dựa vào grant cũ**.

Do đó tách:

~~~text
Consent withdrawn
  ≠ delete all historical evidence automatically
  ≠ continue future processing because data already exists
  ≠ instantly purge all backups regardless of obligations
~~~

Cần chính sách retention, hạn chế, xóa/ẩn danh và quyền của chủ thể riêng, có kiểm tra thực thi.

### 17.2. Quyền đồng ý không được tái tạo từ cache quá hạn

Một hệ gửi email đã lấy danh sách đủ điều kiện hôm trước. Sáng nay khách rút lại. Nếu worker vẫn gửi vì dựa trên snapshot cũ, hệ thống không đáp ứng mục tiêu dừng xử lý kịp thời.

Giải pháp có thể gồm:

- **Final consent check** ngay trước hành động gửi.
- Danh sách suppression được đồng bộ nhanh.
- Invalidation hoặc TTL thấp cho cache consent.
- Event WITHDRAW với xử lý idempotent.
- Giám sát độ trễ propagation và queue chưa xử lý.
- Fail closed nếu không kiểm tra được trạng thái mà tuyến xử lý yêu cầu consent.

Không có một giải pháp duy nhất đủ cho mọi SLA; phải chọn và kiểm thử theo rủi ro của hoạt động.

## 18. Bitemporal: đã có hiệu lực khi nào và hệ thống từng biết gì?

Giả sử mobile ghi nhận một lần rút lại lúc **10:00 ngày 10/03** nhưng offline và chỉ đồng bộ vào server lúc **12:00**.

Có hai câu hỏi khác nhau:

1. **“Theo quyết định hiện được chấp nhận, withdrawal có hiệu lực từ thời điểm B nào?”**
2. **“Lúc 11:00, hệ thống server đã biết và có thể áp dụng withdrawal hay chưa?”**

Nếu application sau đó chọn valid_from = 10:00 để phản ánh yêu cầu của khách, timeline theo **valid time** có thể nói WITHDRAWN tại 11:00. Nhưng điều đó không có nghĩa một consumer lúc 11:00 đã nhận được thông tin này.

Muốn giải thích cả hai trục cần:

- **valid_period**: thông tin được coi có hiệu lực ở khoảng nghiệp vụ nào.
- **known_period**: phiên bản thông tin được hệ thống chấp nhận/lưu là đang biết trong khoảng nào.

### 18.1. Ví dụ hai lớp thời gian

~~~text
Trước 12:00 server ghi nhận:
  GRANTED, valid [01/02, +∞), known [01/02, 10/03 12:00)

Từ 12:00 server ghi nhận:
  GRANTED,   valid [01/02, 10/03 10:00), known [10/03 12:00, +∞)
  WITHDRAWN, valid [10/03 10:00, +∞), known [10/03 12:00, +∞)
~~~

Bảng này phân biệt hai phát biểu:

- Tại **K = 11:00**, hệ thống từng tin grant còn hiệu lực cho **B = 11:00**.
- Tại **K = 13:00**, theo thông tin đã nhận và chính sách hiệu lực, hệ thống có thể coi withdrawal đã áp dụng cho **B = 11:00**.

**Không nên lấy việc backdate valid time làm kết luận tự động về tính hợp pháp của một hoạt động đã thực hiện lúc 11:00**. Điều đó còn phụ thuộc quy định thời điểm rút có hiệu lực, thời điểm hệ thống có thể biết và xử lý, nghĩa vụ phản hồi, bằng chứng và chính sách tương ứng.

### 18.2. Ràng buộc bitemporal

Nếu dùng một bảng projection bitemporal, mỗi hàng có cả **valid_period** và **known_period**. Một ràng buộc ý tưởng trong PostgreSQL:

~~~sql
-- Trích phần CONSTRAINT minh họa;
-- cần đặt trong CREATE TABLE có đầy đủ các cột.
EXCLUDE USING gist (
    tenant_id WITH =,
    subject_id WITH =,
    purpose_code WITH =,
    scope_key WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

Nó ngăn hai trạng thái của cùng scope giao nhau **đồng thời trên cả valid time và known time**. Hai phiên bản có valid_period chồng lấn nhưng known_period không chồng nhau là điều hợp lệ, vì phản ánh nhận thức hệ thống ở hai giai đoạn.

**Known time do ứng dụng cấp chưa chắc là commit time chính xác.** Nếu yêu cầu bằng chứng trạng thái tại transaction commit, phải thiết kế điểm cắt, ghi nhận và thứ tự commit phù hợp, không chỉ thêm cột updated_at.

### 18.3. Event log có thay thế bitemporal không?

Một decision event log đầy đủ và được sắp thứ tự có thể giúp replay trạng thái đã được chấp nhận tại từng phiên bản. Nhưng replay để trả lời “hệ thống từng biết gì lúc K” cần ánh xạ phiên bản với thời điểm có thẩm quyền, quy tắc diễn giải ổn định và đầy đủ mọi correction.

Bitemporal history là **projection thuận tiện cho truy vấn hai trục**, không phải tính năng tự xuất hiện chỉ vì dữ liệu có event_id.

## 19. Thuộc tính và quan hệ có hiệu lực cũng cần đúng mốc thời gian

Một consent có thể phụ thuộc:

- Chủ thể đang thuộc tenant nào.
- Thương hiệu hoặc controller đang có quyền đối với kênh đó.
- Một địa chỉ email nào là phương tiện liên hệ đang được xác minh.
- Thiết bị đã được liên kết với tài khoản nào.
- Người đại diện có thẩm quyền hợp lệ trong khoảng nào.

Nếu quan hệ **subject – email address** có lịch sử, một sự đồng ý gửi email cho địa chỉ cũ không đương nhiên áp dụng cho mọi địa chỉ mới. Quy tắc có thể là consent thuộc **chủ thể + purpose + channel**, hoặc thuộc **cụ thể địa chỉ liên hệ**; cần chọn theo nội dung lựa chọn đã được công bố.

### 19.1. Tránh JOIN phiên bản hiện tại vào sự kiện quá khứ

Giả sử khách đổi email ngày 01/05. Một chiến dịch tháng 3 đã gửi tới địa chỉ cũ. Không thể JOIN log gửi tháng 3 với email hiện tại rồi báo rằng thông điệp đã được gửi tới địa chỉ mới.

Bản ghi hoạt động xử lý hoặc thông điệp đã chốt cần có **contact endpoint/định danh được sử dụng** (lưu an toàn, tối thiểu) và timestamp, hoặc FK tới phiên bản contact có hiệu lực.

### 19.2. Quan hệ đại diện theo thời gian

Nếu người đại diện X chỉ có quyền quyết định thay chủ thể trong khoảng [A, B), một grant được X thực hiện ở thời điểm C phải được kiểm tra **C thuộc [A, B)**. Không dùng quyền đại diện hiện tại để xác nhận mọi quyết định cũ.

Đây là một **temporal join** giữa decision và lịch sử quan hệ đại diện, cùng với các bằng chứng thẩm quyền cần thiết.

## 20. Phân tán: đồng bộ withdrawal tới nhiều dịch vụ

Một tổ chức có thể có:

~~~mermaid
flowchart TD
    UI["Web/App: chủ thể lựa chọn"] --> CS["Consent service có thẩm quyền"]
    CS --> DB["Decision log + State history"]
    CS --> OB["Transactional outbox"]
    OB --> MQ["Message broker / event stream"]
    MQ --> EM["Email marketing"]
    MQ --> RE["Recommendation service"]
    MQ --> DW["Kho phân tích / activation"]
    CS --> AP["API kiểm tra quyền xử lý"]
    AP --> EM
    AP --> RE
~~~

Với consent thay đổi, downstream có thể nhận event:

~~~json
{
  "eventId": "evt-withdraw-501",
  "subjectId": "subject-501",
  "purposeCode": "MARKETING_EMAIL",
  "scopeKey": "BRAND_A:EMAIL",
  "decisionId": "D2",
  "action": "WITHDRAW",
  "effectiveAt": "2026-03-10T10:00:00Z",
  "revision": 12
}
~~~

Đây là **payload minh họa ngữ nghĩa**, không phải bản ghi JSON có UUID thật theo DDL. Một event phải giữ **eventId cố định khi publisher retry**; consumer dedup và áp dụng version/revision phù hợp.

### 20.1. Outbox ngăn khoảng hở giữa DB và broker

Nếu chỉ commit history rồi gửi broker trực tiếp, có thể database commit nhưng broker không nhận. Nếu gửi broker trước khi commit, consumer có thể nhận thay đổi chưa thực sự được chấp nhận.

Transactional outbox ghi bản ghi trạng thái/decision và thông điệp cần phát trong cùng transaction database, rồi publisher xử lý sau. Cơ chế này giảm rủi ro mất thông điệp, nhưng có thể **gửi trùng**; consumer vẫn cần idempotency.

### 20.2. Không nhầm event đã phát với withdrawal đã được áp dụng ở mọi nơi

Một message WITHDRAW được broker nhận không chứng minh email worker đã xử lý và dừng gửi. Cần theo dõi:

- Revision đã xử lý ở từng consumer.
- Thời gian propagation.
- Các job đang chờ hoặc đang chạy.
- Số thao tác đã bị chặn.
- Lỗi, retry và trường hợp dữ liệu không đồng bộ.

Những tuyến có rủi ro cao có thể yêu cầu **kiểm tra đồng bộ tại điểm xử lý** thay vì chỉ dựa vào event bất đồng bộ.

### 20.3. Replay event không có nghĩa replay hành động

Khi rebuild một projection bằng cách replay lịch sử GRANT/WITHDRAW, hệ thống không được tự **gửi lại email marketing** từ các event cũ. Phải tách các consumer **dựng trạng thái** khỏi consumer **thực thi side effect** và thiết kế cơ chế idempotency/điều kiện thời gian.

## 21. Mô hình quan hệ, document, graph và phân tích

Các lựa chọn database khác nhau cần giữ cùng hợp đồng ngữ nghĩa:

| Công nghệ/mô hình | Cách thể hiện có thể chọn | Rủi ro phải kiểm soát |
|---|---|---|
| **Relational** | ConsentScope, DecisionLog, StateHistory, Notice | FK, EXCLUDE, giao dịch, version và query as-of |
| **Document** | Consent decision documents, current projection | Concurrent update, không overlap, cấu trúc scope, retention |
| **Graph** | Subject → Purpose/Controller/Channel có effective edges | Truy vấn quan hệ đúng thời điểm, tránh suy quyền qua cạnh hiện tại |
| **Event store** | GRANT/WITHDRAW decision stream, replay projection | Thứ tự, idempotency, schema evolution, snapshot |
| **Data warehouse/lakehouse** | Lịch sử đồng ý và tập dữ liệu activation theo thời gian | Dữ liệu muộn, thời điểm kiểm tra, phân đoạn quá hạn, PII |
| **Cache/search index** | Current consent status hoặc suppression projection | Độ trễ đồng bộ, invalidation, fail-safe |

### 21.1. Document không tự bảo đảm tính đúng theo khoảng

Một collection có tài liệu:

~~~json
{
  "subjectId": "subject-501",
  "purpose": "MARKETING_EMAIL",
  "scope": "BRAND_A:EMAIL",
  "status": "GRANTED",
  "validFrom": "2026-02-01T09:00:00Z",
  "validTo": "2026-03-10T10:00:00Z"
}
~~~

Một unique index theo **(subject, purpose, validFrom)** không tự ngăn hai khoảng bắt đầu ở các thời điểm khác nhau nhưng chồng lấn. Cần transaction, khóa luồng hoặc validation có độ tin cậy phù hợp với database document được chọn.

### 21.2. Graph phải kiểm tra cả các cạnh liên quan

Một chủ thể có thể có quan hệ với thương hiệu và một mục đích có điều kiện. Truy vấn “chủ thể có grant cho Brand A tại thời điểm T không?” phải kiểm tra **thời gian của consent edge**, và nếu cần cả **thời gian của quan hệ subject–brand/contact**. Truy vấn một cạnh hiện hành có thể suy quyền sai cho một sự kiện quá khứ.

### 21.3. Warehouse chỉ là projection, không nhất thiết là nguồn quyết định

Một warehouse dùng cho phân tích chiến dịch có thể lưu trạng thái consent tại thời điểm nạp. Nếu dữ liệu đến trễ, bảng snapshot ngày trước có thể chưa phản ánh withdrawal vừa có hiệu lực. Không dùng một phân đoạn marketing được xuất vào hôm qua làm căn cứ duy nhất cho hoạt động gửi hôm nay.

Consent service hoặc policy engine có thẩm quyền nên cung cấp **quy tắc kiểm tra tại thời điểm thực thi** theo SLA được định nghĩa.

## 22. Chỉ mục, partitioning, retention và quyền riêng tư

### 22.1. Các truy vấn cần tối ưu

| Mẫu truy vấn | Cấu trúc hỗ trợ |
|---|---|
| Một subject + purpose + scope tại T | Composite scope key + GiST range |
| Toàn bộ quyết định của subject | Index tenant, subject, accepted_at |
| Decision theo request ID | UNIQUE tenant, capture_source, source_decision_key |
| Grant cần hết hạn | Index theo upper(valid_period) hoặc job deadline phù hợp |
| Lịch sử theo tenant và thời gian | Partition/archival có kiểm soát |
| Kiểm toán notice theo decision | FK notice_id và object lưu nội dung bất biến |

Ví dụ chỉ mục audit:

~~~sql
CREATE INDEX ix_consent_decision_subject_time
ON consent_decision (
    tenant_id, subject_id, accepted_at DESC
);
~~~

GiST exclusion của state history đã tạo index hỗ trợ các điều kiện bằng và overlap theo scope. Cần đo truy vấn thực tế trước khi thêm nhiều index khác; một số workload có thể cần B-tree riêng cho current-state projection.

### 22.2. Không partition thời gian mà làm mất constraint chống overlap

Nếu tách state_history thành các bảng tháng theo effective_at, một khoảng valid_period có thể đi qua nhiều tháng. Hai khoảng chồng nhau nhưng ở hai partition khác nhau không tự bị một UNIQUE/EXCLUDE cục bộ phát hiện.

PostgreSQL có giới hạn đối với ràng buộc uniqueness/exclusion xuyên partition tùy cấu trúc và phiên bản. Với consent, **tính đúng trạng thái là ưu tiên**: cân nhắc giữ bảng state history có constraint tập trung, partition decision log theo accepted_at, hoặc dùng điểm khóa luồng/registry để kiểm soát toàn bộ timeline trước khi ghi.

Không cho phép chọn partitioning chỉ vì muốn DROP dữ liệu nhanh nếu nó khiến hai trạng thái GRANTED/WITHDRAWN cùng có hiệu lực một thời điểm.

### 22.3. Lưu giữ bằng chứng không đồng nghĩa lưu tất cả PII mãi mãi

Decision log cần đủ khả năng chứng minh các lựa chọn đã được thu thập và thay đổi. Nhưng lưu giữ phải có **mục đích, thời hạn, quyền đọc và cơ chế xóa/ẩn danh theo yêu cầu áp dụng**.

Phương pháp:

- Sử dụng **subject_id giả danh** thay cho sao chép email/địa chỉ trực tiếp.
- Tách bảng ánh xạ danh tính thật khỏi consent log.
- Hạn chế payload bằng danh sách trường cho phép.
- Bảo vệ notice, evidence, logs và bản export.
- Kiểm soát truy cập theo vai trò và tenant.
- Xác định retention cho bằng chứng, state history, hoạt động xử lý và backup.
- Theo dõi yêu cầu xóa, hạn chế và pháp lý độc lập với withdrawal.
- Không tự xóa mọi bằng chứng khi withdrawal nếu vẫn có nghĩa vụ chứng minh; đồng thời không giữ dữ liệu quá mức cần thiết.

**Append-only là quy tắc kiểm toán logic, không phải giấy phép lưu thông tin cá nhân vô hạn.**

## 23. Những sai lầm thường gặp

| Cách làm | Vì sao sai hoặc thiếu? | Cách cải thiện |
|---|---|---|
| Một cột marketing_consent | Không biết purpose, scope, thời gian, notice | Consent theo subject–purpose–scope |
| Lựa chọn mới ghi đè trạng thái cũ | Mất khả năng chứng minh lịch sử | Decision log và state intervals |
| Không phân biệt DENIED và UNKNOWN | Ghi sai quyết định của chủ thể | Trạng thái thiếu bằng chứng riêng |
| Không ghi phiên bản notice | Không biết nội dung đã trình bày | Immutable notice version + reference |
| Tự coi mọi consent là hợp lệ mãi | Bỏ qua expiry, correction, withdrawal | Khoảng hiệu lực và policy |
| Dùng received_at thay valid_from mọi nơi | Sai nếu quyết định có hiệu lực khác lúc nhận | Định nghĩa từng trục thời gian |
| Dùng timestamp client để backdate grant | Có thể hợp thức hóa hoạt động trước bằng chứng | Xác minh mốc hiệu lực có thẩm quyền |
| Coi thiếu hàng là TRUE | Fail-open trong tuyến cần consent | Unknown → không có grant hợp lệ |
| Lấy grant email áp cho push | Vượt phạm vi đồng ý | Tách purpose/channel/scope |
| Cache grant cả ngày không invalidation | Gửi sau withdrawal | Final check/suppression/version |
| JOIN lịch sử theo subject mà thiếu purpose | Fanout và suy quyền sai | Composite scope key đầy đủ |
| Cho hai phiên bản state overlap | Không rõ trạng thái tại T | EXCLUDE/transaction và test |
| Ghi event rồi không cập nhật projection | Downstream lệch nguồn | Outbox, version, reconciliation |
| Coi withdrawal là xóa toàn bộ dữ liệu | Bỏ qua nghĩa vụ/chứng cứ khác | Retention và rights workflow riêng |
| Replay event làm gửi lại email | Side effect lặp ngoài ý định | Tách replay projection khỏi action |
| Dựa hoàn toàn vào warehouse chậm | Trạng thái activation cũ | Kiểm tra tại điểm thực thi |
| Một request nhiều purpose dùng cùng decision key | Unique conflict hoặc mất lựa chọn | Key riêng cho mỗi choice, correlation chung |

## 24. Kiểm thử trạng thái, thời gian và quyền xử lý

Một bộ kiểm thử cần dùng **tình huống xác định được kết quả** thay vì chỉ kiểm tra INSERT thành công.

### 24.1. Kiểm thử timeline mẫu

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Grant MARKETING_EMAIL Brand A từ 01/02 | GRANTED ở 05/03 |
| Withdrawal đúng 10/03 10:00 | Không còn GRANTED tại biên |
| Query 20/03 | WITHDRAWN |
| Grant lại từ 02/04 08:00 | GRANTED ở 05/04 |
| Query trước grant đầu | Không có bản ghi/UNKNOWN, không suy GRANTED |
| Query MARKETING_PUSH | Không được dùng grant MARKETING_EMAIL |
| Query cùng purpose nhưng Brand B | Không được dùng grant Brand A ngoài phạm vi đã xác nhận |
| Có expiry 01/05 | Sau 01/05 không còn grant |
| Hai state cùng scope overlap | Database/validator từ chối |
| Hai scope khác nhau có cùng thời gian | Được phép nếu purpose và phạm vi hợp lệ |

### 24.2. Kiểm thử đồng thời và idempotency

1. Hai worker cùng cập nhật consent của một scope tại cùng thời điểm không tạo hai state overlap.
2. Một request GRANT bị timeout sau commit và gửi lại: không tạo decision/version thứ hai.
3. Cùng source_decision_key nhưng action hoặc evidence khác: báo conflict.
4. Transaction ghi decision thành công nhưng ghi projection lỗi: rollback cùng.
5. Không có scope row khi hai request cùng bắt đầu: creation path có PK/unique, retry có kiểm soát.
6. Dữ liệu đến muộn có effective_at trong quá khứ không phá timeline và không tự hợp thức hóa một xử lý đã xảy ra.
7. Hai quyết định cùng effective_at có thứ tự/precedence rõ và không tạo khoảng rỗng.
8. Bitemporal query theo K trước và sau accepted_at trả hai hiểu biết khác nhau khi có correction.

### 24.3. Kiểm thử thực thi và propagation

1. Email được lên lịch trước withdrawal nhưng gửi sau withdrawal phải được kiểm tra lại theo chính sách áp dụng.
2. Consumer nhận WITHDRAW hai lần không làm mất hoặc tạo lại grant.
3. Consumer nhận event ngoài thứ tự phải dùng revision hoặc nguồn có thẩm quyền, không cập nhật current state lùi thời gian.
4. Khi consent service không sẵn sàng, tuyến xử lý bắt buộc có consent phải xử lý theo **fail-safe policy** được phê duyệt.
5. Replay event lịch sử không phát lại chiến dịch hay chia sẻ dữ liệu.
6. Subject bị tách/merge ID có kiểm tra phạm vi và bằng chứng, không tự hợp nhất grant không đúng chủ thể.
7. Các API kiểm tra tenant và quyền: một dịch vụ của tenant khác không được tự lấy consent record.
8. Sự kiện withdrawal có thể được kiểm toán từ yêu cầu, quyết định, outbox đến xác nhận downstream.

### 24.4. Kiểm thử chất lượng dữ liệu và bằng chứng

- GRANT không có notice hoặc evidence phải bị từ chối nếu contract yêu cầu.
- Notice ID phải đúng purpose và phiên bản thực tế đã trình bày.
- Không lưu token/password hoặc PII vượt phạm vi trong evidence.
- Date/time phải có offset, không so sánh ngày nghiệp vụ với timestamp UTC thiếu quy tắc.
- Một bản ghi state tham chiếu decision sai tenant/purpose/scope phải bị phát hiện.
- Khi đã hết retention, API lịch sử phải báo không còn dữ liệu được bảo đảm thay vì suy GRANTED.
- Đối soát current projection với replay decision log trong cửa sổ được giữ.

## 25. Bài thực hành: quản lý lựa chọn cho sàn thương mại điện tử

Một nền tảng có khách **C-501**, hai thương hiệu **A** và **B**, các mục đích:

- MARKETING_EMAIL: nhận email quảng cáo.
- MARKETING_PUSH: nhận push quảng cáo.
- PERSONALIZATION: cá nhân hóa từ hành vi.
- ORDER_NOTICE: thông báo trạng thái đơn trên cơ sở xử lý được policy xác định riêng.

Diễn biến:

~~~text
01/02/2026 09:00 UTC:
  Brand A, MARKETING_EMAIL: GRANTED, notice v3
  Brand A, MARKETING_PUSH: DENIED
  Brand A, PERSONALIZATION: GRANTED, notice v2

10/03/2026 10:00 UTC:
  Brand A, MARKETING_EMAIL: WITHDRAWN

10/03/2026 11:00 UTC:
  Worker email có 1 chiến dịch đang chờ gửi.

02/04/2026 08:00 UTC:
  Brand A, MARKETING_EMAIL: GRANTED lại, notice v4

05/04/2026:
  Brand B muốn dùng email của C-501 để gửi ưu đãi.
~~~

### 25.1. Nhiệm vụ thiết kế

1. Viết grain của ConsentDecision và ConsentStateHistory.
2. Thiết kế các mã purpose và scope theo tenant/brand/channel.
3. Chọn PK, FK và UNIQUE cho subject, notice, decision, scope.
4. Vẽ sơ đồ trạng thái GRANTED → WITHDRAWN → GRANTED cho email Brand A.
5. Viết DDL valid_period theo **[from, to)** và constraint chống overlap.
6. Tạo timeline cho email Brand A, push Brand A và personalization Brand A mà không nhầm nhau.
7. Viết truy vấn as-of tại 05/03, 20/03 và 05/04.
8. Giải thích vì sao Brand B không tự hưởng grant của Brand A.
9. Giải thích vì sao ORDER_NOTICE có thể cần một policy riêng thay vì dựa vào marketing consent.
10. Đề xuất cơ chế xử lý worker email đang chờ lúc 11:00, gồm kiểm tra trạng thái cuối trước gửi.
11. Nếu app gửi withdrawal offline lúc 10:00 nhưng server chỉ nhận lúc 12:00, mô tả valid time và known time; không tự suy kết luận pháp lý từ backdate.
12. Mô tả transaction ghi decision, state và outbox, cùng phương án concurrency control.
13. Thiết kế idempotency khi app gửi lại cùng withdrawal request ba lần.
14. Nêu chiến lược lưu bằng chứng notice v3/v4 mà không giữ dữ liệu nhạy cảm không cần thiết.
15. Thiết kế kiểm thử cho expiry, thiếu record, overlap, sai scope, event đến muộn và downstream xử lý trùng.
16. Nêu retention của proof, state, raw event và khả năng trả lời truy vấn trong quá khứ.

### 25.2. Đáp án định hướng

- Email Brand A có các khoảng GRANTED, WITHDRAWN, GRANTED như bảng phần 14.
- Push Brand A có DENIED riêng; personalization Brand A có GRANTED riêng.
- Brand B chưa có grant trong phạm vi thích hợp, nên không được suy quyền từ Brand A.
- Worker gửi email cần kiểm tra lại consent trước thực thi hoặc có suppression/invalidation đáp ứng SLA.
- ORDER_NOTICE không được tự đồng nhất với marketing consent; chính sách cơ sở xử lý là một lớp riêng.
- Bitemporal hoặc replay có mốc kiến thức giúp giải thích xử lý xảy ra trước khi server nhận withdrawal offline.
- Retention phải giữ chứng cứ cần thiết trong giới hạn đã được xác định, không mặc định giữ mọi PII vô hạn.

**Tiêu chí đạt:** một thay đổi consent không làm mất lịch sử; quyền không lan sang mục đích/phạm vi khác; truy vấn as-of có biên đúng; action đã commit có bằng chứng; withdrawal được truyền và kiểm tra lại ở nơi xử lý; dữ liệu thiếu không bị coi là đã đồng ý.

## 26. Checklist phê duyệt thiết kế

- **Chủ thể:** đã có subject_id có thẩm quyền và phạm vi tenant rõ ràng chưa?
- **Mục đích:** mỗi purpose có mã, mô tả và chính sách thay đổi ổn định chưa?
- **Phạm vi:** controller, brand, channel, data category và recipient có được biểu diễn đúng như lựa chọn đã công bố không?
- **Trạng thái:** GRANTED, DENIED, WITHDRAWN, EXPIRED và UNKNOWN có được phân biệt đúng không?
- **Bằng chứng:** notice version, locale, nội dung thực, interaction và decision ID có thể kiểm tra được không?
- **Thời gian:** event/client time, accepted/recorded time, effective time, expires_at và known time đã có ngữ nghĩa riêng chưa?
- **Biên:** tất cả khoảng hiệu lực dùng [from, to) và không chồng lấn trong cùng scope chứ?
- **Ràng buộc:** PK, FK, UNIQUE, EXCLUDE và tính nhất quán scope–decision đã đủ chưa?
- **Ghi đồng thời:** có khóa ổn định/revision và giao dịch nguyên tử để tránh lost update không?
- **Retry:** cùng source decision gửi lại không tạo quyết định mới; payload khác được phát hiện xung đột chứ?
- **Withdrawal:** dừng xử lý tương lai trong phạm vi cần consent, có kiểm tra lại ở điểm thực thi không?
- **Downstream:** outbox, event ID, consumer idempotency, propagation lag và reconciliation có được theo dõi không?
- **Hồi tố:** hệ thống có giữ trạng thái từng biết ở K nếu cần chứng minh quyết định lịch sử không?
- **Cơ sở xử lý:** consent không bị đánh đồng với toàn bộ quyền xử lý; policy có kiểm tra riêng không?
- **Riêng tư:** proof và log được tối thiểu hóa, phân quyền, retention/xóa và bảo vệ khỏi sửa đổi trái phép chưa?
- **Đa mô hình:** khi chuyển relational sang document/graph/lakehouse, phạm vi và bất biến temporal có còn được giữ không?
- **Kiểm thử:** đã thử biên timestamp, expiry, missing record, scope mismatch, race condition, offline delay và cache stale chưa?

**Kết luận:** mô hình đồng ý đáng tin không phải một trường TRUE/FALSE trên bảng khách hàng. Nó là **quan hệ có điều kiện và có thời gian giữa chủ thể, mục đích, phạm vi, quyết định và bằng chứng**. Bảng quyết định giữ lịch sử hành động; bảng trạng thái theo khoảng hiệu lực cho truy vấn as-of; policy engine xác định hoạt động cụ thể có được phép hay không. Thiết kế tốt bảo đảm **không suy rộng quyền từ một lựa chọn**, **không đánh mất dấu vết khi rút lại** và **không biến thông tin đến muộn thành một câu chuyện lịch sử sai**. Khi kết hợp khóa, ràng buộc, thời gian và kiểm soát truy cập rõ ràng, dữ liệu đồng ý mới có thể tiến hóa và được kiểm chứng trong một hệ thống phân tán.
