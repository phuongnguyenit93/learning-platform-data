# Anomalous velocity pattern — Mẫu tốc độ hoạt động bất thường

## 1. Bất thường về tốc độ không chỉ là gửi nhiều request

Một khách hàng tạo vài yêu cầu hoàn tiền trong nhiều ngày có thể hoàn toàn bình thường. Nếu cùng tài khoản đột ngột tạo nhiều yêu cầu trên nhiều đơn trong vài phút, hành vi đó đáng được đánh giá thêm. Tuy nhiên, số request cao cũng có thể đến từ retry sau lỗi mạng, công cụ hỗ trợ hợp lệ hoặc một đợt tăng lưu lượng bình thường.

**Anomalous velocity pattern** là mẫu hoạt động có tốc độ, mức dồn dập hoặc quy mô thay đổi đáng chú ý so với ngữ cảnh được xác định. Đối tượng đo không chỉ là số request mỗi giây. Có thể đo số ý định nghiệp vụ, số đối tượng khác nhau, tổng giá trị yêu cầu, tốc độ thất bại hoặc khoảng thời gian giữa các bước nhạy cảm.

Trong bảo vệ logic nghiệp vụ, phát hiện velocity giúp nhận ra việc chia nhỏ giao dịch, thử nhiều đối tượng, thay đổi nhanh trạng thái hoặc phân tán thao tác để né giới hạn. Tín hiệu này bổ sung cho quyền theo đối tượng, state machine, transaction, idempotency và các bất biến. Nó không thay thế những cơ chế đó.

Sau bài này, bạn có thể:

- Chọn đúng đơn vị đếm cho một hành vi nghiệp vụ.
- Xây dựng đặc trưng theo cửa sổ thời gian, danh tính và đối tượng.
- Phân biệt baseline, ngưỡng bất thường và hạn mức bắt buộc.
- Xử lý retry, sự kiện trùng, sự kiện đến muộn và hành vi phân tán.
- Chuyển tín hiệu thành phản ứng có phạm vi, có giải thích và kiểm thử được.

Ví dụ chính của bài là yêu cầu hoàn tiền trong một hệ thống nhiều tenant. Các ngưỡng, thời gian và chính sách đều là minh họa, không phải bộ quy tắc phát hiện gian lận dùng chung.

## 2. Phân biệt bất thường, vi phạm hạn mức và gian lận

### 2.1. Ba khái niệm không đồng nghĩa

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Velocity bất thường | Hành vi hiện tại khác ngữ cảnh mong đợi đến mức nào? | Một actor từ khoảng hai lên chín ý định hoàn tiền trong năm phút |
| Vi phạm hạn mức | Hành động có vượt giới hạn bắt buộc không? | Tổng tiền đã hoàn và đang giữ chỗ vượt tiền đã thu |
| Gian lận đã xác minh | Có đủ căn cứ kết luận hành vi gian lận theo quy trình không? | Kết quả điều tra độc lập xác nhận lạm dụng |

Một actor có thể hoạt động bất thường nhưng vẫn hợp lệ. Một hành động trông rất bình thường vẫn có thể vi phạm quyền hoặc trạng thái nghiệp vụ. Vì vậy, không cho phép điểm rủi ro thấp hợp thức hóa việc sửa giá đã chốt, hoàn vượt số tiền còn lại hoặc dùng phê duyệt sai đối tượng.

Hạn mức cứng cần cơ chế kiểm tra và giữ chỗ nhất quán tại điểm chấp nhận lệnh. Đặc trưng phân tích có thể được tính gần đúng hoặc đến chậm nếu chỉ phục vụ cảnh báo; không nên dùng chúng để tuyên bố bảo đảm một bất biến tài chính chính xác.

### 2.2. Những dạng velocity đáng quan sát

| Mẫu | Biểu hiện | Điều cần phân biệt |
| --- | --- | --- |
| Burst | Nhiều hành động tập trung trong thời gian ngắn | Retry, batch hợp lệ, công cụ tự động được cấp quyền |
| Fan-out | Một actor tác động nhiều đối tượng | Phân công hỗ trợ hợp lệ so với thử đối tượng ngoài quyền |
| Fan-in | Nhiều actor hội tụ vào một tài nguyên liên quan | Quan hệ dùng chung hợp lệ so với phối hợp lạm dụng |
| Tăng tổng giá trị | Nhiều yêu cầu nhỏ tạo mức tác động lớn | Số lượng thấp không có nghĩa tác động thấp |
| Tỷ lệ thất bại cao | Nhiều lần bị từ chối hoặc xung đột | Lỗi triển khai, dữ liệu cũ hoặc hành vi dò thử |
| Chuỗi bước quá nhanh | Thay đổi nhạy cảm rồi thực hiện hành động tiếp theo rất sớm | Workflow tự động hợp lệ so với chuỗi đáng nghi |
| Phân tán kéo dài | Mỗi tài khoản chậm nhưng tổng hoạt động liên quan cao | Cần cửa sổ dài và liên kết có căn cứ |

Không phải mẫu nào cũng phát hiện được bằng một giới hạn theo IP hoặc theo phút. Cần chọn đặc trưng theo cách nghiệp vụ có thể bị lạm dụng.

## 3. Chọn đúng sự kiện trước khi chọn ngưỡng

### 3.1. Lần thử, ý định và hiệu ứng là ba đơn vị khác nhau

Giả sử client gửi một yêu cầu hoàn tiền, bị mất phản hồi rồi thử lại ba lần với cùng khóa idempotency. Máy chủ chỉ tạo một ý định và cuối cùng thực hiện một lần hoàn tiền. Các con số có thể là bốn lần thử, một ý định và một hiệu ứng.

| Loại sự kiện | Ý nghĩa | Cách sử dụng minh họa |
| --- | --- | --- |
| `ACTION_ATTEMPT` | Một lần gọi hành động được máy chủ ghi nhận theo định nghĩa thu thập | Phát hiện spam, thử liên tục hoặc tỷ lệ bị từ chối |
| `INTENT_CREATED` | Một ý định nghiệp vụ mới được tạo | Đo tốc độ tạo yêu cầu khác nhau |
| `INTENT_UPDATED` | Nội dung ý định được đổi theo quy trình | Phát hiện sửa nhiều lần hoặc đổi tham số nhạy cảm |
| `ACTION_COMMITTED` | Một chuyển tiếp nghiệp vụ đã commit | Đo tác động cục bộ đã thực sự được chấp nhận |
| `EXTERNAL_EFFECT_CONFIRMED` | Có xác nhận hiệu ứng bên ngoài | Đo số tiền hoặc giao dịch đã hoàn tất ở bên nhận |

Sự kiện phải có định nghĩa rõ. Ví dụ, `ACTION_ATTEMPT` có thể áp dụng sau khi đã xác thực actor và kiểm tra cấu trúc cơ bản; lưu lượng chưa xác thực hoặc sai định dạng được đo ở nhóm riêng. Không gán mọi request có trường `actorId` cho danh tính mà client tự khai.

Một lần retry HTTP là một lần thử mới nếu máy chủ thực sự nhận lại request. Nhưng việc broker phát lại cùng một sự kiện đã ghi không được biến thành thêm lần thử. Vì vậy, event ID do phía máy chủ quản lý và định danh ý định cần được phân biệt.

### 3.2. Schema sự kiện minh họa

```json
{
  "eventId": "evt-server-812",
  "eventType": "INTENT_CREATED",
  "tenantId": "tenant-A",
  "actorId": "actor-17",
  "canonicalAction": "refund.request",
  "intentId": "refund-71",
  "intentRevision": 1,
  "subjectType": "ORDER",
  "subjectId": "order-501",
  "amountMinor": 150000,
  "currency": "VND",
  "occurredAt": "2026-11-22T03:04:00Z",
  "recordedAt": "2026-11-22T03:04:01Z",
  "outcome": "CREATED"
}
```

Đây là dữ liệu minh họa. Actor, tenant, hành động chuẩn hóa và trạng thái phải được suy ra hoặc kiểm chứng ở phía máy chủ. `occurredAt` là mốc nghiệp vụ từ nguồn có thẩm quyền, không phải thời gian trình duyệt tự gửi; `recordedAt` phản ánh thời điểm hệ thống thu thập ghi nhận sự kiện.

`canonicalAction` giúp các endpoint tương đương hội tụ vào cùng một hành động nghiệp vụ. Nếu API web, API di động và công cụ quản trị cùng tạo hoàn tiền nhưng đếm ở ba nhóm rời nhau, kẻ lạm dụng có thể luân phiên đường gọi để làm loãng đặc trưng.

Không đưa token, mật khẩu, số thẻ gốc hoặc dữ liệu xác thực vào sự kiện. Nếu cần liên kết theo phương thức thanh toán, dùng định danh tham chiếu được kiểm soát. Băm trực tiếp dữ liệu ít khả năng lựa chọn không tự bảo đảm ẩn danh; cơ chế token hóa hoặc định danh liên kết phải phù hợp với quyền truy cập và mục đích sử dụng.

### 3.3. Tổng giá trị phải có ngữ nghĩa rõ

Tổng tiền được yêu cầu khác tổng tiền đã giữ chỗ và tổng tiền đã hoàn. Một ý định được sửa từ 100.000 lên 150.000 VND không mặc nhiên có nghĩa tổng yêu cầu hiện tại là 250.000 VND. Cần quyết định đang đo giá trị hiện tại của các ý định khác nhau hay tổng các thay đổi phát sinh.

Nếu muốn đo quy mô yêu cầu mới, có thể đếm mỗi intent một lần với quy tắc cập nhật giá trị rõ ràng. Nếu muốn phát hiện liên tục sửa tham số, đo thêm số lần sửa hoặc độ lớn thay đổi bằng đặc trưng riêng. Không cộng mọi revision rồi đặt tên chỉ số là “tổng tiền đang chờ”.

Cũng cần phân biệt tổng gộp và tổng ròng. Một chuỗi tạo rồi hủy nhiều yêu cầu có thể có giá trị ròng gần bằng không nhưng vẫn thể hiện hoạt động bất thường. Không xóa lịch sử lần thử chỉ vì ý định sau đó bị hủy.

Tiền phải được tính theo đơn vị nguyên được hệ thống quy định và tách theo đồng tiền. Ví dụ với VND có thể quy ước một đơn vị là một đồng. Không cộng trực tiếp VND với USD, cũng không dùng số thực nhị phân cho ràng buộc tiền chính xác.

## 4. Cửa sổ thời gian và cách tính đặc trưng

### 4.1. Định nghĩa biên cửa sổ

Với thời điểm đánh giá `t` và độ dài `W`, bài này dùng cửa sổ trượt:

```text
(t - W, t]
```

Sự kiện tại đúng đầu cửa sổ bị loại; sự kiện tại thời điểm đánh giá được tính. Mỗi triển khai có thể chọn quy ước khác, nhưng cần nhất quán và kiểm thử biên.

Với tập sự kiện đã chống trùng phù hợp, có thể định nghĩa:

```text
N(g, W, t) = số intent khác nhau của nhóm g trong (t-W, t]
D(g, W, t) = số đối tượng khác nhau của nhóm g trong (t-W, t]
S(g, W, t) = tổng giá trị theo ngữ nghĩa đã chọn và cùng đồng tiền
R(g, W, t) = N(g, W, t) / W
```

`g` có thể là `(tenant, actor, canonical_action)`. Nếu `W` đo bằng phút thì `R` có đơn vị intent mỗi phút. Không so sánh trực tiếp giá trị mỗi giây với baseline mỗi năm phút.

### 4.2. Ví dụ tính bằng tay

Đánh giá lúc 10:05, cửa sổ năm phút. Có các intent hoàn tiền mới:

| Thời điểm | Intent | Đơn hàng | Số tiền VND |
| --- | --- | --- | --- |
| 10:00 | I-0 | O-0 | 50.000 |
| 10:01 | I-1 | O-A | 100.000 |
| 10:02 | I-2 | O-A | 200.000 |
| 10:04 | I-3 | O-B | 100.000 |
| 10:05 | I-4 | O-C | 300.000 |

Theo quy ước `(10:00, 10:05]`:

- Có bốn intent được tính; I-0 nằm đúng biên trái nên không được tính.
- Có ba đơn hàng khác nhau: O-A, O-B và O-C.
- Tổng giá trị các intent được tính là 700.000 VND.
- Tốc độ trung bình trong cửa sổ là 0,8 intent mỗi phút.

Đây là phép tính đặc trưng, không khẳng định các yêu cầu đều được phép hoặc đã thực thi. Hai intent trên O-A vẫn phải đi qua bất biến số tiền và chống trùng nghiệp vụ thích hợp. Nếu một intent có ba request retry, số lần thử tăng nhưng số intent của bảng không tự tăng.

### 4.3. Cửa sổ cố định, trượt và nhiều thang thời gian

Cửa sổ cố định dễ tổng hợp nhưng có hiệu ứng biên. Chẳng hạn, nhiều hoạt động ở cuối một phút và ngay đầu phút sau có thể tạo burst ngắn mà từng bucket riêng chưa vượt ngưỡng.

Cửa sổ trượt bám khoảng thời gian gần hiện tại hơn nhưng cần cấu trúc lưu và chi phí phù hợp. Các phép xấp xỉ bằng bucket hoặc trọng số có thể hữu ích cho cảnh báo, nhưng phải hiểu sai số trước khi dùng để chặn.

Kết hợp nhiều thang thời gian giúp nhận các kiểu hành vi khác nhau: một phút cho burst, vài phút cho fan-out và thời gian dài hơn cho chia nhỏ kéo dài. Không có một cửa sổ duy nhất phù hợp mọi hành động; ngưỡng và baseline phải cùng đơn vị, cùng phạm vi và cùng định nghĩa sự kiện.

## 5. Chọn chiều nhóm để nhận ra hành vi phân tán

### 5.1. Một chiều đơn lẻ thường chỉ thấy một phần

Các nhóm có thể sử dụng gồm:

| Nhóm | Câu hỏi gợi ý |
| --- | --- |
| Tenant và actor | Một danh tính có tăng tốc tạo ý định không? |
| Tenant và khách hàng sở hữu đối tượng | Nhiều actor có cùng tác động vào một khách hàng không? |
| Tenant và đơn hoặc thanh toán gốc | Một giao dịch có nhiều yêu cầu hoàn liên tiếp không? |
| Tenant và định danh phương thức thanh toán đã kiểm soát | Nhiều tài khoản có hội tụ vào cùng tài nguyên liên quan không? |
| Tenant và hành động chuẩn hóa | Một đường nghiệp vụ có tăng bất thường trên toàn tenant không? |
| Actor quản trị và tập đối tượng | Có thao tác hàng loạt vượt hành vi vận hành thông thường không? |

Nhóm theo IP có thể bổ sung tín hiệu, nhưng IP không phải danh tính duy nhất. Mạng dùng chung có thể khiến nhiều người hợp lệ xuất hiện cùng IP; đổi IP cũng không nên xóa lịch sử của một actor đã xác thực. Tương tự, device ID do client tùy ý thay không thể là căn cứ duy nhất để phân nhóm đáng tin cậy.

Đăng xuất, mở session mới hoặc đổi endpoint không nên tự đặt lại các đặc trưng theo danh tính nghiệp vụ. Nếu chỉ lưu bộ đếm trong session, người lạm dụng có thể làm loãng hoạt động qua nhiều phiên.

### 5.2. Liên kết không đồng nghĩa kết tội cả nhóm

Hai tài khoản có cùng phương thức liên quan, địa chỉ hoặc thiết bị có thể có lý do hợp lệ. Dùng quan hệ này như một tín hiệu cần ngữ cảnh, không tự gán mọi thành viên cùng hành vi gian lận.

Trong hệ thống nhiều tenant, mặc định phải giữ ranh giới dữ liệu. Việc tổng hợp xuyên tenant cần một mục đích và quyền xử lý riêng, cùng cơ chế bảo vệ dữ liệu. Không để dashboard của tenant A tiết lộ tài khoản hoặc hoạt động ở tenant B thông qua kết quả liên kết.

Dữ liệu có cardinality cao cũng tạo áp lực tài nguyên. Nếu dùng mọi chuỗi header hoặc mọi ID client cung cấp làm key, kẻ tấn công có thể tạo vô số nhóm. Cần kiểm soát schema, miền giá trị, thời gian lưu và ngân sách bộ nhớ, đồng thời giữ khả năng quan sát khi phải giảm độ chi tiết.

## 6. Baseline theo ngữ cảnh và heuristic minh họa

### 6.1. So sánh cùng loại hoạt động

Một chuyên viên xử lý theo batch có hành vi khác khách hàng tự phục vụ. Một tenant mới khác một tenant có lượng giao dịch lớn; cuối tuần, chương trình bán hàng hoặc giờ vận hành cũng có thể làm thay đổi lưu lượng hợp lệ.

Baseline nên được xác định theo ngữ cảnh đủ liên quan, chẳng hạn loại actor, hành động, nhóm tenant và khoảng thời gian. Tuy nhiên, chia nhóm quá nhỏ có thể khiến dữ liệu thưa và baseline không đáng tin cậy. Cần biết số mẫu, độ mới và mức ổn định của dữ liệu, không chỉ lưu một giá trị trung bình.

Không miễn kiểm tra mọi thứ cho tài khoản dịch vụ hoặc quản trị viên vì họ thường có lưu lượng cao. Họ có thể cần baseline và thẩm quyền khác, nhưng các bất biến về tenant, số tiền, trạng thái và phê duyệt vẫn giữ nguyên.

### 6.2. Công thức tỷ lệ đơn giản

Gọi `N` là số intent hoàn tiền khác nhau trong năm phút, `B` là số intent kỳ vọng trong cùng loại cửa sổ của ngữ cảnh được chọn. Một tỷ lệ minh họa:

```text
velocity_ratio = N / max(B, 1)
```

Số 1 là mức sàn minh họa để tránh chia cho 0 và tỷ lệ bùng nổ khi baseline rất nhỏ. Nó không phải lựa chọn tối ưu cho mọi dữ liệu. Nếu baseline bị thiếu thì không tự thay bằng 0 rồi áp dụng công thức; trạng thái thiếu dữ liệu phải được xử lý riêng.

Ví dụ, một actor có `B = 2`, hiện tại có `N = 9`, thì tỷ lệ là 4,5. Một actor khác có `B = 20`, hiện tại có `N = 30`, tỷ lệ là 1,5. Số đếm tuyệt đối của người thứ hai cao hơn nhưng mức tăng tương đối thấp hơn.

Tỷ lệ này không phải xác suất gian lận và cũng không tự cho biết ý nghĩa thống kê. Nó là một đặc trưng dễ giải thích trong một heuristic minh họa.

### 6.3. Kết hợp mức tăng, số tuyệt đối và độ phân tán

Một rule minh họa có thể là:

```text
N = unique_refund_intents_5m
D = distinct_orders_5m
B = expected_unique_refund_intents_5m

Nếu dữ liệu đủ tin cậy và baseline phù hợp:
  burst = N >= 8 và N / max(B, 1) >= 4
  spread = D >= 4
  nếu burst và spread:
    yêu cầu xét duyệt theo chính sách
```

Các con số 8, 4 và năm phút chỉ dùng để minh họa. Rule yêu cầu cả số tuyệt đối và mức tăng để tránh chỉ một thay đổi nhỏ trên baseline gần 0 tạo tỷ lệ lớn. Điều kiện nhiều đơn cho biết phạm vi hoạt động đang mở rộng, nhưng không tự chứng minh lạm dụng.

Pseudocode theo phong cách Java:

```java
// Giả định các giá trị đã được kiểm tra miền hợp lệ và cùng ngữ nghĩa.
static VelocitySignal evaluate(VelocityFeatures features) {
    if (!features.hasTrustedData() || !features.hasUsableBaseline()) {
        return VelocitySignal.INSUFFICIENT_DATA;
    }

    double ratio = features.uniqueRefundIntents5m()
            / Math.max(features.expectedRefundIntents5m(), 1.0);
    boolean burst = features.uniqueRefundIntents5m() >= 8
            && ratio >= 4.0;
    boolean spread = features.distinctOrders5m() >= 4;

    return burst && spread
            ? VelocitySignal.REVIEW_CANDIDATE
            : VelocitySignal.NO_RULE_MATCH;
}
```

Các kiểu dữ liệu trong ví dụ là minh họa, không phải thư viện có sẵn. `NO_RULE_MATCH` chỉ nói rule này không khớp, không kết luận giao dịch an toàn. `INSUFFICIENT_DATA` không được tự diễn giải thành “velocity bằng 0”. Mọi kết quả vẫn đi qua chính sách quyền, trạng thái, hạn mức và phản ứng phù hợp.

### 6.4. Cold start và baseline bị làm lệch

Với actor hoặc tenant mới, có thể chưa đủ lịch sử. Hệ thống có thể dùng baseline của nhóm tương đồng, chính sách khởi đầu bảo thủ hoặc yêu cầu bổ sung phù hợp. Phải ghi rõ nguồn baseline và độ tin cậy để người vận hành hiểu quyết định.

Nếu cập nhật baseline quá nhanh bằng chính hoạt động đang bị đánh giá, một chuỗi lạm dụng kéo dài có thể dần trở thành “bình thường”. Có thể dùng khoảng trễ, tập dữ liệu đã kiểm chứng hoặc giới hạn tốc độ thay đổi baseline. Ngược lại, loại bỏ mọi giao dịch bị cảnh báo mà không xem kết quả cũng có thể làm lệch mẫu. Cần kiểm tra ảnh hưởng của cách chọn dữ liệu thay vì chỉ tăng hoặc giảm ngưỡng khi thấy nhiều cảnh báo.

## 7. Đưa velocity vào đường xử lý nghiệp vụ

### 7.1. Phân biệt phát hiện sau sự kiện và kiểm soát trước hành động

Một pipeline phân tích thường gồm:

```text
Sự kiện đáng tin cậy
  -> kiểm tra schema và chống trùng sự kiện
  -> nhóm theo danh tính, hành động và cửa sổ
  -> tính đặc trưng, baseline và tín hiệu
  -> tạo cảnh báo hoặc cập nhật hồ sơ rủi ro
```

Pipeline này có thể phát hiện sau khi hành động đã xảy ra. Nếu yêu cầu phải giữ một giao dịch trước khi thực hiện, cần điểm kiểm tra đồng bộ hoặc giao thức admission phù hợp ở đường nghiệp vụ. Không thể phát sự kiện sau thanh toán rồi coi cảnh báo đến muộn như cơ chế đã chặn thanh toán.

Một luồng trước hành động có thể là:

1. Xác thực actor, kiểm tra schema và quyền cơ bản.
2. Nhận diện ý định hiện có theo idempotency và định danh nghiệp vụ.
3. Lấy đặc trưng phù hợp, biết thời điểm cập nhật và mức tin cậy.
4. Đánh giá tác động của ý định hiện tại theo quy tắc không đếm trùng.
5. Áp dụng chính sách: tiếp tục, yêu cầu xác thực bổ sung, giữ xét duyệt hoặc từ chối.
6. Khi tiếp tục, chấp nhận command bằng transaction bảo vệ trạng thái, số tiền và hạn mức.
7. Ghi sự kiện bền vững để phân tích và đối soát.

Nếu yêu cầu bị giữ, việc giữ cổng thực thi và tạo hồ sơ xét duyệt phải nhất quán. Một hàng đợi cảnh báo không có quyền ngăn thực thi thì chỉ là quan sát, không phải cổng kiểm soát nghiệp vụ.

### 7.2. Có tính ý định hiện tại hay chưa?

Một lỗi dễ gặp là cộng thêm 1 vào đặc trưng ở mọi lần retry, trong khi intent đó đã nằm trong dữ liệu. Cần biết snapshot đã bao gồm ý định hiện tại hay chưa, hoặc dùng một ledger theo intent để cập nhật một lần.

Ví dụ, feature hiện có bảy intent; một intent mới làm giá trị dự kiến thành tám. Nếu client gửi lại cùng ý định, không được biến thành chín chỉ vì tính lại rule. Ngược lại, một ý định khác có định danh khác không được gộp nhầm chỉ vì đến từ cùng session.

Nếu ghi ý định ngay khi tiếp nhận đề nghị hợp lệ rồi đặt trạng thái chờ hoặc từ chối, cần định nghĩa rõ đặc trưng `INTENT_CREATED` có bao gồm những trạng thái đó hay không. Không đổi nghĩa chỉ số giữa các dịch vụ. Số lần thử vẫn là đặc trưng riêng và có thể tăng khi request được gửi lại.

### 7.3. Cuộc đua giữa nhiều request

Hai request có thể cùng đọc snapshot có bảy intent rồi đều kết luận mình là intent thứ tám. Nếu ngưỡng chỉ là tín hiệu phân tích mềm, cần biết và đo giới hạn quan sát này. Nếu quy tắc yêu cầu chính xác không nhận quá một số lượng nhất định, nó là hạn mức và cần admission nguyên tử.

Có thể dùng khóa, cập nhật có điều kiện hoặc ledger giữ chỗ theo ý định. Giữ chỗ phải có định danh ổn định, thời hạn, trạng thái và cách xác nhận hoặc giải phóng đúng một lần. Nếu nhiều chiều hạn mức cần cùng thỏa mãn, việc kiểm tra rời rạc từng bộ đếm có thể nhận lệnh vượt giới hạn hoặc giữ chỗ dở dang.

Đặc biệt, một bộ đếm velocity không tự bảo vệ số tiền hoàn. Transaction nghiệp vụ vẫn cần bảo đảm:

```text
refunded_minor >= 0
refund_reserved_minor >= 0
refunded_minor + refund_reserved_minor <= captured_minor
```

Một cập nhật phân tích thành công không đồng nghĩa transaction tiền đã commit; một transaction thất bại không đồng nghĩa lần thử chưa xảy ra. Phải tách những trạng thái đó trong dữ liệu và quy trình khôi phục.

### 7.4. Kho đặc trưng lỗi thì xử lý thế nào?

Thiếu dữ liệu, dữ liệu quá cũ, lỗi đọc và giá trị bằng 0 là các trạng thái khác nhau. Chính sách có thể yêu cầu giữ để xét duyệt đối với hành động nhạy cảm hoặc chỉ quan sát với hành động ít tác động. Lựa chọn phải được định nghĩa theo rủi ro và khả năng vận hành, không phát sinh ngầm từ một exception bị nuốt.

Dù chọn phản ứng nào, không được bỏ qua các kiểm tra bắt buộc như quyền theo tenant, trạng thái hợp lệ và số tiền còn lại. Không tự chuyển một giới hạn cứng thành cho phép khi kho đếm tạm thời không sẵn sàng.

## 8. Sự kiện trùng, đến muộn và replay

### 8.1. Chống trùng không làm mất dấu lần thử thật

Chống trùng sự kiện dùng event ID từ nguồn đáng tin cậy. Broker phát lại cùng event không được tăng số đếm. Trong khi đó, một request mới thực sự đến máy chủ có thể là một lần thử mới dù dùng cùng khóa idempotency. Tách hai lớp giúp vừa giữ đúng số ý định vừa nhìn thấy hành vi spam.

Phạm vi và thời gian lưu receipt chống trùng phải đáp ứng thời gian replay mà hệ thống hỗ trợ. Nếu receipt đã bị dọn nhưng sự kiện rất cũ được phát lại, cần chính sách tránh đưa nó vào cửa sổ hiện tại như một sự kiện mới.

### 8.2. Event time và processing time

`Event time` là mốc hoạt động ở nguồn; `processing time` là mốc hệ thống phân tích xử lý nó. Dùng mốc nào phải rõ ràng. Nếu broker bị nghẽn một giờ rồi phát nhiều sự kiện cùng lúc, đếm theo processing time có thể tạo burst do hạ tầng thay vì do người dùng.

Tính theo event time cần quy tắc cho dữ liệu đến muộn, giới hạn chờ và sửa kết quả lịch sử. Dữ liệu quá muộn có thể phục vụ điều tra nhưng không nên tự biến thành lệnh chặn mới trên một ý định đã hoàn tất nếu không có quy trình phù hợp.

Đồng hồ nguồn bị sai hoặc timestamp bất hợp lý cần được nhận diện. Không cho client đẩy thời gian sang tương lai để giữ sự kiện ngoài cửa sổ hoặc kéo về quá khứ để né đặc trưng hiện tại. Với nhiều nguồn máy chủ, cần giả định đồng bộ thời gian và mức sai lệch được xử lý.

### 8.3. Replay để tính lại khác thực thi lại

Khi thay rule hoặc khôi phục kho đặc trưng, có thể replay sự kiện để xây lại đặc trưng và đánh giá lịch sử. Chế độ này phải tách khỏi tạo hiệu ứng nghiệp vụ trực tiếp. Không để một lần backfill tự tạo thêm yêu cầu xác thực, thêm case trùng hoặc gửi lại command tiền.

Cảnh báo có thể nhóm theo subject, hành động, cửa sổ hoặc incident fingerprint và phiên bản chính sách. Việc nhóm giảm thông báo lặp nhưng không được làm mất số sự kiện, mức độ nghiêm trọng hoặc diễn biến mới. Một cảnh báo đang mở không phải lý do ngừng đánh giá các ý định tiếp theo.

## 9. Phản ứng có phạm vi và có thể giải thích

Tùy hành động và tín hiệu, có thể lựa chọn:

| Phản ứng | Mục đích | Điều kiện cần giữ |
| --- | --- | --- |
| Chỉ quan sát | Thu thập thêm dữ liệu và đánh giá rule | Không mô tả như đã chặn hành vi |
| Throttle | Giảm tốc độ gửi hoặc tạo ý định | Phạm vi đúng, không phạt cả nhóm chỉ vì IP dùng chung |
| Xác thực bổ sung | Kiểm chứng tốt hơn ai đang thực hiện | Không cấp thêm quyền đối tượng hoặc bỏ qua phê duyệt |
| Giữ để xét duyệt | Chờ đánh giá trước hiệu ứng được bảo vệ | Cổng nghiệp vụ thực sự ngăn thực thi, có thời hạn và đường xử lý |
| Từ chối hành động | Ngăn tác động theo chính sách rõ ràng | Lưu lý do, không ghi dữ liệu dở dang |
| Điều tra sau sự kiện | Xem chuỗi liên quan hoặc hiệu ứng đã xảy ra | Không giả vờ đảo ngược giao dịch bằng cách đổi nhãn |

Một lý do nội bộ tốt có thể ghi: actor tạo chín intent khác nhau trên bốn đơn trong năm phút, baseline của ngữ cảnh là hai, rule phiên bản nào đã khớp và dữ liệu được cập nhật khi nào. Không chỉ ghi một điểm số không có nguồn.

Đối với phản hồi công khai, cung cấp trạng thái và bước tiếp theo phù hợp mà không tiết lộ chi tiết các ngưỡng hoặc dữ liệu người khác. Với người vận hành có quyền, phải đủ bằng chứng để hiểu và xem lại quyết định.

## 10. Những cách làm loãng tín hiệu cần kiểm thử

| Cách làm loãng | Vì sao một rule đơn giản có thể bỏ sót? | Hướng bảo vệ |
| --- | --- | --- |
| Hoạt động sát hai phía biên bucket | Từng bucket cố định chưa vượt ngưỡng | Cửa sổ trượt hoặc kết hợp nhiều cửa sổ với sai số đã biết |
| Chia thành nhiều yêu cầu nhỏ | Mỗi yêu cầu dưới ngưỡng tiền | Đo số lượng, tổng giá trị và giữ hạn mức cộng dồn chính xác |
| Luân phiên endpoint | Bộ đếm chia theo URL | Chuẩn hóa hành động nghiệp vụ |
| Đổi session hoặc đăng nhập lại | Dữ liệu chỉ gắn với session | Dùng danh tính nghiệp vụ đã xác thực theo mục đích phù hợp |
| Phân tán qua nhiều actor liên quan | Mỗi actor có tốc độ thấp | Nhóm thêm theo tài nguyên liên quan có căn cứ và quyền xử lý |
| Tạo rồi hủy liên tục | Tổng ròng giảm về gần 0 | Đo lần thử, intent mới và tổng gộp riêng |
| Thay thông tin trước khi thao tác | Bộ đếm từng bước chưa nổi bật | Theo dõi chuỗi sự kiện và revision của đối tượng |
| Duy trì thay đổi trong thời gian dài | Baseline thích nghi coi đó là bình thường | Kiểm soát cập nhật baseline và theo dõi cửa sổ dài |
| Tạo key nhóm tùy ý | Cạn bộ nhớ hoặc làm loãng theo ID giả | Xác minh thuộc tính, kiểm soát cardinality và nguồn sự kiện |

Những biện pháp này bổ sung nhau, không tạo bảo đảm phát hiện mọi hành vi. Không nên mở rộng phạm vi chặn cả một nhóm liên quan chỉ để bù cho đặc trưng thiếu chính xác. Phản ứng cần tương xứng với độ tin cậy, tác động và quyền của hệ thống.

## 11. Vận hành, dữ liệu và đánh giá chất lượng

### 11.1. Đo sức khỏe của đặc trưng trước khi tin điểm số

Các chỉ số cần theo dõi gồm:

- Độ trễ từ sự kiện nguồn đến khi đặc trưng được cập nhật.
- Tỷ lệ sự kiện trùng, đến muộn, sai schema hoặc thiếu danh tính đáng tin cậy.
- Tỷ lệ đọc đặc trưng lỗi, quá cũ hoặc không có baseline.
- Số nhóm đang lưu, dung lượng và lượng dữ liệu bị loại theo chính sách giữ lại.
- Độ lệch giữa đặc trưng online và phép tính lại trên dữ liệu tham chiếu đã chống trùng.
- Số cảnh báo, ý định bị giữ, thời gian chờ và tác động đến người dùng hợp lệ.

Một burst có thể xuất hiện do broker hồi phục sau nghẽn; một mức giảm đột ngột có thể do pipeline mất sự kiện. Cần quan sát cả chất lượng thu thập và hoạt động nghiệp vụ để tránh giải thích mọi thay đổi như hành vi người dùng.

Nếu dùng xấp xỉ cho số đối tượng khác nhau hoặc cửa sổ, cần kiểm chứng sai số trên dữ liệu phù hợp. Một ước lượng hữu ích cho xếp ưu tiên chưa chắc phù hợp để chặn ngay đúng ngưỡng. Các giá trị không hợp lệ như số âm, giá trị không hữu hạn hoặc đồng tiền không xác định cần được xử lý rõ ràng, không đi qua rule như dữ liệu bình thường.

### 11.2. Đánh giá đúng mục tiêu phát hiện

“Khác baseline” và “lạm dụng nghiệp vụ đã xác minh” là hai nhãn khác nhau. Một detector có thể tìm đúng hành vi hiếm nhưng tạo nhiều công việc vô ích nếu những hành vi đó đều hợp lệ. Cần xác định đang tối ưu phát hiện mẫu bất thường, giảm tác động lạm dụng hay hỗ trợ reviewer.

Trên một tập đánh giá có nhãn độc lập đủ tin cậy cho mục tiêu cần đo, có thể dùng:

```text
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
```

Trong đó TP là trường hợp thuộc mục tiêu và được phát hiện; FP là trường hợp không thuộc mục tiêu nhưng bị phát hiện; FN là trường hợp thuộc mục tiêu nhưng bị bỏ sót. Khi mẫu số bằng 0, chỉ số không có giá trị xác định theo công thức này; không tùy ý coi là 100%.

Tập nhãn và cách lấy mẫu rất quan trọng. Nếu chỉ điều tra trường hợp đã bị cảnh báo, chưa có đủ căn cứ để ước lượng phần bị bỏ sót trên toàn lưu lượng. Kết quả `REJECT` của reviewer cũng không tự là nhãn gian lận độc lập. Cần xét nguồn xác minh, trường hợp chưa có kết quả và độ trễ của kết quả.

Ngoài precision và recall, cần đo tác động thực tế: thời gian giữ giao dịch hợp lệ, số người cần xác thực bổ sung, chi phí xét duyệt và hiệu ứng nghiệp vụ được ngăn ở đúng thời điểm. Một cảnh báo rất chính xác nhưng đến sau hiệu ứng không có cùng giá trị với một kiểm soát trước hành động.

### 11.3. Thay đổi rule và baseline có kiểm soát

Rule, cửa sổ, nguồn dữ liệu và baseline nên có phiên bản để giải thích quyết định. Trước khi bật phản ứng ảnh hưởng người dùng, có thể chạy ở chế độ quan sát, replay trên dữ liệu phù hợp và xem các nhóm bị ảnh hưởng. Chế độ quan sát phải không tạo hiệu ứng chặn ngầm.

Khi cảnh báo tăng, không tự nâng ngưỡng chỉ để giảm số lượng. Trước hết cần kiểm tra thay đổi schema, retry do lỗi hạ tầng, chiến dịch kinh doanh, nhóm actor mới và khả năng có hoạt động lạm dụng thật. Việc thay chính sách phải đi qua quyền và quy trình tương ứng, không để người đang bị đánh giá tự sửa baseline của mình.

Audit cho một quyết định nên lưu actor và scope phù hợp, action, intent ID và revision, thời điểm đánh giá, đặc trưng cần thiết, nguồn baseline, thời điểm cập nhật dữ liệu, rule version, phản ứng và liên kết command hoặc case. Không sao chép bí mật hoặc dữ liệu khách hàng không cần thiết vào log.

## 12. Kiểm thử tình huống tấn công logic và lỗi dữ liệu

Kiểm thử cần đánh giá cả giá trị đặc trưng lẫn hành vi nghiệp vụ. Một rule trả đúng nhãn nhưng command vẫn chạy khi phải chờ review là lỗi kiểm soát.

| Tình huống | Cách thử | Kết quả cần bảo đảm |
| --- | --- | --- |
| Biên trái cửa sổ | Đặt sự kiện đúng `t-W` | Không được tính theo quy ước `(t-W, t]` |
| Biên phải cửa sổ | Đặt sự kiện đúng `t` | Được tính đúng một lần |
| Broker phát trùng | Phát lại cùng event ID | Không tăng thêm đặc trưng tương ứng |
| Retry HTTP thật | Gửi lại cùng ý định nhiều lần | Lần thử được đo theo định nghĩa; intent và hiệu ứng không nhân đôi |
| Ý định hiện tại đã có | Đánh giá lại sau khi intent đã vào feature | Không cộng thêm 1 mỗi lần đánh giá |
| Hai ý định khác nhau | Gửi hai intent có nội dung gần giống nhưng hợp lệ khác nhau | Không gộp chỉ vì chung session hoặc thời điểm |
| Ý định được sửa | Đổi giá trị từ 100.000 lên 150.000 | Tổng hiện tại không vô tình thành 250.000; số lần sửa được đo riêng |
| Nhiều đồng tiền | Trộn sự kiện VND và USD | Không cộng trực tiếp vào một tổng tiền không có ngữ nghĩa |
| Hủy sau tạo | Tạo rồi hủy nhiều ý định | Không xóa dấu vết tốc độ tạo và lần thử |
| Đổi endpoint | Luân phiên web, mobile và công cụ nội bộ | Hội tụ vào hành động chuẩn hóa thích hợp |
| Đổi session | Đăng nhập lại giữa chuỗi hoạt động | Không đặt lại lịch sử theo actor nếu chính sách nhóm theo actor |
| IP dùng chung | Nhiều người hợp lệ cùng IP | Không mặc định quy thành một danh tính gian lận |
| Phân tán actor | Nhiều actor tác động cùng tài nguyên được phép liên kết | Đặc trưng nhóm phản ánh quan hệ mà không lộ dữ liệu trái scope |
| Tenant khác nhau | Truy vấn hoặc hiển thị đặc trưng B bằng quyền A | Không tiết lộ dữ liệu hoặc áp dụng scope sai |
| Sát biên bucket | Tập trung sự kiện trước và sau ranh giới | Kiểm tra được giới hạn của bucket và khả năng phát hiện qua cửa sổ bổ sung |
| Sự kiện đến muộn | Dồn backlog cũ vào cùng thời điểm xử lý | Không nhầm toàn bộ thành burst hiện tại khi rule dùng event time |
| Timestamp giả | Client gửi giờ quá khứ hoặc tương lai | Không điều khiển được mốc đáng tin cậy dùng để tính |
| Baseline thiếu | Actor mới chưa có lịch sử | Trả trạng thái thiếu dữ liệu hoặc fallback rõ ràng, không giả baseline bằng 0 |
| Dữ liệu feature lỗi | Timeout, quá cũ, số âm hoặc không hữu hạn | Phản ứng đúng chính sách; không ngầm cho phép bằng dữ liệu mặc định |
| Hai request cạnh tranh | Cùng đọc giá trị trước ngưỡng | Hạn mức cứng vẫn được admission nguyên tử; giới hạn tín hiệu mềm được biết rõ |
| Feature thấp nhưng sai bất biến | Gửi hoàn vượt số tiền còn lại | Dịch vụ nghiệp vụ vẫn chặn |
| Review gate | Rule yêu cầu chờ nhưng gọi thẳng API thực thi | Không thực hiện hành động đang bị giữ |
| Replay lịch sử | Chạy backfill sau đổi rule | Không tạo hiệu ứng tiền hoặc case trùng ngoài chính sách |
| Alert đang mở | Phát thêm hoạt động nghiêm trọng hơn | Vẫn cập nhật mức độ và đánh giá ý định mới |
| Nhiều nhóm giả | Gửi thuộc tính client tạo cardinality lớn | Không để key tùy ý làm cạn tài nguyên ngoài kiểm soát |

Dùng đồng hồ có thể điều khiển để kiểm tra các biên thời gian mà không cần chờ thật. Với cạnh tranh, tạo điểm chồng lấn bằng barrier hoặc cơ chế đồng bộ của công cụ kiểm thử. Hai request chạy tuần tự không kiểm chứng được admission nguyên tử.

Sau kiểm thử, đối chiếu số lần thử, số intent, số command, số hiệu ứng xác nhận, giữ chỗ, audit và outbox nếu có. Những số này không nhất thiết bằng nhau; điều quan trọng là mỗi số đúng định nghĩa và không có hiệu ứng trái bất biến.

## 13. Bài tập áp dụng

Thiết kế phát hiện tốc độ yêu cầu hoàn tiền cho một nền tảng nhiều tenant. Có khách hàng tự phục vụ, nhân viên hỗ trợ và công cụ xử lý batch. Request có thể retry; sự kiện có thể đến muộn hoặc được chuyển nhiều lần.

Hãy tạo các đầu ra sau:

1. Định nghĩa sự kiện và đơn vị đếm cho lần thử, intent mới, sửa intent và hiệu ứng đã xác nhận.
2. Bộ đặc trưng ít nhất gồm số intent, số đơn khác nhau, tổng giá trị cùng đồng tiền và tỷ lệ thất bại, với cửa sổ và scope rõ ràng.
3. Baseline cho các nhóm actor phù hợp; cách xử lý cold start và dữ liệu quá cũ.
4. Một heuristic dễ giải thích, phân biệt `NO_RULE_MATCH`, `REVIEW_CANDIDATE` và `INSUFFICIENT_DATA` hoặc các trạng thái tương đương.
5. Cách xử lý idempotency và ý định hiện tại để không đếm trùng khi đánh giá lại.
6. Ranh giới giữa tín hiệu phân tích và admission nguyên tử cho hạn mức cứng.
7. Phản ứng khi cần review, khi kho đặc trưng lỗi và khi kết quả chỉ đến sau hiệu ứng.
8. Audit, chỉ số chất lượng dữ liệu và tối thiểu tám kiểm thử bao phủ thời gian, concurrency, retry và phân tán danh tính.

Áp dụng rule minh họa của bài cho ba trường hợp sau:

| Trường hợp | N trong 5 phút | Số đơn khác nhau | Baseline B | Kết quả riêng của rule minh họa |
| --- | --- | --- | --- | --- |
| Actor A | 9 | 4 | 2 | REVIEW_CANDIDATE vì số tuyệt đối, tỷ lệ và độ phân tán cùng đạt |
| Actor B | 30 | 8 | 20 | NO_RULE_MATCH vì tỷ lệ 1,5 chưa đạt điều kiện burst |
| Actor C | 1 | 1 | Chưa có | INSUFFICIENT_DATA nếu chưa có fallback đủ điều kiện |

Các kết quả trên không thay thế quyết định nghiệp vụ cuối. Actor B vẫn có thể vi phạm hạn mức hoặc quyền; actor A vẫn có thể là người dùng hợp lệ. Một thiết kế đạt yêu cầu phải vừa phát hiện đúng mẫu cần quan sát, vừa giữ các bất biến về đối tượng, trạng thái, số tiền và hiệu ứng khi dữ liệu đến trễ hoặc nhiều request chạy đồng thời.
