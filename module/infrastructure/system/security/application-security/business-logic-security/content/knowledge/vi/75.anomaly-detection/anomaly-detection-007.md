# Anomaly rule tuning: hiệu chỉnh quy tắc phát hiện bất thường trong nghiệp vụ

## 1. Mục tiêu và phạm vi

Trong chương **Anomaly Detection**, anomaly rule tuning là quá trình điều chỉnh điều kiện, ngưỡng, cửa sổ quan sát và cách xử lý tín hiệu để phát hiện hành vi lạm dụng nghiệp vụ với chi phí vận hành chấp nhận được.

Một yêu cầu có thể hợp lệ về định dạng, có token xác thực và đi qua đúng API nhưng vẫn nằm trong một chuỗi lạm dụng: liên tục yêu cầu hoàn tiền, thử nhiều mã khuyến mại, chia nhỏ giao dịch để né phê duyệt hoặc thao tác trên nhiều đối tượng bằng quyền được cấp quá rộng. Rule phát hiện bất thường giúp nhận ra các chuỗi này.

Trong phạm vi bảo mật logic nghiệp vụ, mục tiêu là bảo vệ quy tắc kinh doanh và giảm thiệt hại. Một hệ thống tạo nhiều cảnh báo chưa chắc bảo vệ nghiệp vụ tốt hơn.

Sau bài này, bạn có thể:

- Phân biệt điều kiện nghiệp vụ bắt buộc với ngưỡng nghi vấn được phép hiệu chỉnh.
- Xác định đúng sự kiện, đơn vị quan sát, cửa sổ thời gian và mẫu số của một rule.
- Đánh giá cấu hình bằng dữ liệu đã gán nhãn, backtest theo thời gian và năng lực xử lý cảnh báo.
- Triển khai thay đổi bằng shadow, canary, theo dõi và rollback.
- Thiết kế tình huống kiểm thử cho retry, cạnh tranh đồng thời, dữ liệu đến muộn và hành vi né ngưỡng.

Các con số trong bài là **giả định để học**, không phải ngưỡng áp dụng chung cho mọi hệ thống.

## 2. Ranh giới quan trọng: invariant và anomaly rule

**Business invariant** là điều kiện phải luôn đúng khi hệ thống chấp nhận một thao tác. **Anomaly rule** là dấu hiệu cho thấy hành vi đáng được xem xét thêm.

| Tình huống | Kiểm soát bắt buộc | Vai trò của phát hiện bất thường |
|---|---|---|
| Hoàn tiền vượt số tiền được phép hoàn | Kiểm tra số dư hoàn và cập nhật nguyên tử | Phát hiện chuỗi thử yêu cầu vượt hạn mức |
| Bỏ qua bước phê duyệt | State machine và quyền chuyển trạng thái | Phát hiện nhiều lần chuyển trạng thái thất bại |
| Sửa giá từ trình duyệt | Máy chủ xác định giá và điều kiện ưu đãi | Nhận ra chuỗi thử giá hoặc mã giảm giá bất thường |
| Truy cập đơn của người khác | Kiểm tra quyền theo đối tượng ở máy chủ | Nhận ra hoạt động dò nhiều mã đơn |
| Gửi lại cùng một yêu cầu thanh toán | Idempotency và transaction | Theo dõi retry bất thường mà không nhân đôi tác động tài chính |

Ví dụ, điều kiện:

> Số tiền hoàn mới không vượt quá số tiền đã thu trừ phần đã hoàn và phần đang được giữ chỗ cho yêu cầu hoàn khác.

phải được kiểm tra tại nơi quyết định giao dịch, với cơ chế chống cạnh tranh đồng thời phù hợp. Không được thay điều kiện này bằng “chỉ cảnh báo khi một tài khoản hoàn tiền nhiều lần”.

Ngược lại, “một tài khoản có yêu cầu hoàn trên ít nhất năm đơn trong 24 giờ” chỉ là dấu hiệu nghi vấn. Một đợt giao hàng lỗi có thể khiến nhiều khách hàng hợp lệ cùng đạt điều kiện này.

**Tuning được phép thay đổi mức nghi vấn và cách phản ứng; không được làm yếu quyền theo đối tượng, giới hạn tiền, thứ tự phê duyệt, transaction hay idempotency.**

## 3. Một rule gồm nhiều thành phần hơn một con số

Một quy tắc hữu ích cần trả lời đầy đủ các câu hỏi sau:

| Thành phần | Câu hỏi phải trả lời |
|---|---|
| Mục tiêu | Muốn phát hiện kiểu lạm dụng nào, thiệt hại xảy ra ở bước nào? |
| Sự kiện | Đếm yêu cầu HTTP, thao tác nghiệp vụ hay thay đổi trạng thái đã được lưu? |
| Đối tượng gộp | Theo tài khoản, tổ chức, đơn hàng, người phê duyệt hay nhóm có liên quan? |
| Feature | Đếm đơn khác nhau, tổng tiền, tỷ lệ hay số lần đổi trạng thái? |
| Cửa sổ | 10 phút, 24 giờ hay cả vòng đời đối tượng? Tính theo thời điểm nào? |
| Điều kiện đủ dữ liệu | Cần tối thiểu bao nhiêu mẫu, nguồn dữ liệu có đủ mới không? |
| Phân nhóm | Có tách khách hàng, sản phẩm hoặc quy trình có hành vi khác nhau không? |
| Phản ứng | Ghi nhận, tạo hồ sơ, xác minh thêm hay chuyển sang bước xét duyệt? |
| Vận hành | Ai xử lý, trong bao lâu, thay đổi được rollback thế nào? |
| Truy vết | Rule và cấu hình phiên bản nào đã tạo ra quyết định? |

Một rule được diễn đạt chỉ bằng “refund_rate > 0.8” chưa đủ để triển khai. Nó chưa cho biết refund_rate là tỷ lệ đơn hay tỷ lệ tiền, có tính yêu cầu bị từ chối không, có đếm lại retry không, hoặc xử lý trường hợp mẫu số bằng không thế nào.

### 3.1. Mô tả mục tiêu bằng giả thuyết có thể kiểm chứng

Ví dụ:

> Một tài khoản gửi yêu cầu hoàn phần lớn giá trị của nhiều đơn khác nhau trong thời gian ngắn có thể đang lạm dụng chính sách hoàn tiền. Cần đưa các trường hợp đạt điều kiện vào quy trình xét duyệt trước khi chi tiền nếu trạng thái nghiệp vụ còn cho phép.

Giả thuyết này có:

- Một hành vi: yêu cầu hoàn phần lớn giá trị nhiều đơn.
- Một chủ thể: tài khoản gửi yêu cầu.
- Một khoảng thời gian: cửa sổ ngắn đã xác định.
- Một phản ứng có thể thực hiện: xét duyệt trước khi chi tiền.
- Một điều kiện giới hạn: quyết định phải đến trước bước không thể đảo ngược.

Một detector bất đồng bộ nhận sự kiện sau khi tiền đã chuyển chỉ có thể hỗ trợ điều tra hoặc kiểm soát thao tác tiếp theo. Không được mô tả nó là cơ chế ngăn chính giao dịch đã hoàn tất.

## 4. Ví dụ xuyên suốt: yêu cầu hoàn tiền trên nhiều đơn

Giả sử hệ thống đã thực thi các kiểm soát nền:

1. Máy chủ xác thực người gọi và kiểm tra quyền trên đơn hàng.
2. State machine chỉ cho phép yêu cầu hoàn từ trạng thái hợp lệ.
3. Máy chủ tính số tiền tối đa được hoàn từ dữ liệu tin cậy.
4. Transaction bảo vệ việc giữ chỗ số tiền và tạo yêu cầu.
5. Cùng một thao tác nghiệp vụ được retry sẽ trả lại kết quả đã lưu qua idempotency.

Sau đó, detector quan sát các yêu cầu hoàn đã được tiếp nhận hợp lệ để tìm mẫu hành vi đáng nghi.

### 4.1. Định nghĩa feature chính xác

Tại thời điểm đánh giá `t`, xét các yêu cầu hoàn có thời điểm tiếp nhận thuộc khoảng:

```text
t - 24 giờ < admitted_at <= t
```

Quy ước trong ví dụ:

- Mỗi yêu cầu được nhận diện bằng mã thao tác nghiệp vụ do máy chủ quản lý; phát lại sự kiện không tạo thêm yêu cầu.
- Chỉ lấy yêu cầu còn hiệu lực hoặc đã hoàn thành; yêu cầu bị hủy hoặc từ chối không đóng góp vào tập này.
- Trạng thái, số tiền và thông tin thanh toán được lấy theo cùng một mốc dữ liệu nhất quán.
- Mỗi lần hoàn một phần hợp lệ là một thao tác riêng. Retry của cùng lần hoàn đó vẫn là cùng một thao tác.
- Chỉ gộp các khoản tiền có cùng tiền tệ. Ví dụ này chỉ dùng VND.

Đặt:

```text
S = tập mã đơn khác nhau có yêu cầu hoàn thuộc tập quan sát

distinct_orders_24h = |S|

requested_amount_24h
  = tổng số tiền của các yêu cầu hoàn thuộc tập quan sát,
    sau khi khử trùng lặp thao tác

captured_amount_for_S
  = tổng số tiền đã thu của các đơn thuộc S,
    mỗi đơn chỉ được tính một lần

requested_share
  = requested_amount_24h / captured_amount_for_S
```

Mẫu số phải lấy **đúng tập đơn S**. Không cộng lại toàn bộ tiền đã thu của một đơn mỗi khi đơn đó có thêm một lần hoàn một phần.

`requested_share` thể hiện mức tiền được yêu cầu hoàn trên tập đơn đang quan sát. Nó **không phải** tỷ lệ tất cả đơn mua của tài khoản bị hoàn, cũng không phải xác suất tài khoản gian lận.

Một rule minh họa:

```text
distinct_orders_24h >= 5
AND captured_amount_for_S >= 2.000.000 VND
AND requested_share >= 0,80
=> tạo hoặc cập nhật hồ sơ xét duyệt
```

Điều kiện số đơn giảm ảnh hưởng của một trường hợp riêng lẻ. Điều kiện số tiền giảm cảnh báo có giá trị kinh tế rất nhỏ. Điều kiện tỷ lệ mô tả phần giá trị đang được yêu cầu hoàn.

Các điều kiện này không chứng minh gian lận. Một khách hàng nhận năm sản phẩm cùng bị lỗi vẫn có thể đạt cả ba.

### 4.2. Khi nào không được tính ra kết quả “bình thường”?

Không được ngầm thay dữ liệu thiếu bằng số không để rule trả về không khớp.

| Vấn đề dữ liệu | Cách xử lý cần thiết |
|---|---|
| Không có tiền đã thu của một đơn | Đánh dấu thiếu dữ liệu và đi theo chính sách dự phòng |
| Mẫu số bằng không | Không chia; điều tra dữ liệu hoặc luồng nghiệp vụ |
| Lẫn VND và USD | Tách tiền tệ hoặc áp dụng chính sách quy đổi đã được định nghĩa |
| Snapshot tổng tiền không cùng mốc trạng thái | Xây lại snapshot trước khi kết luận |
| Stream bị trễ quá SLO | Gắn cờ chất lượng, không coi “chưa thấy” là “không có” |
| Tổng tiền yêu cầu lớn hơn tiền đã thu trong mô hình này | Kiểm tra feature, dữ liệu hoặc vi phạm invariant; không nâng ngưỡng để che lỗi |

Kết quả “không khớp rule” và “không đủ dữ liệu để đánh giá” phải được biểu diễn riêng.

## 5. Chất lượng sự kiện quyết định chất lượng tuning

Ngưỡng đẹp không bù được dữ liệu sai.

### 5.1. Các trường nên có

| Trường | Ý nghĩa |
|---|---|
| `event_id` | Nhận diện một sự kiện để chống xử lý lặp khi nhận lại |
| `operation_id` | Nhận diện thao tác nghiệp vụ qua nhiều lần retry |
| `account_id`, `tenant_id` | Xác định đúng chủ thể và ranh giới tổ chức |
| `order_id` | Gộp đơn và tránh nhân mẫu số |
| `occurred_at`, `ingested_at` | Phân biệt thời điểm nghiệp vụ với thời điểm hệ thống nhận |
| `amount`, `currency` | Giá trị do máy chủ xác định, có tiền tệ rõ ràng |
| `state`, `entity_version` | Hỗ trợ dựng trạng thái và bỏ qua cập nhật cũ |
| `schema_version` | Giải thích đúng cấu trúc sự kiện qua các lần thay đổi |
| `correlation_id` | Liên kết xử lý và điều tra theo quyền truy cập phù hợp |

`event_id` và `operation_id` giải quyết hai vấn đề khác nhau. Một thao tác có thể phát nhiều sự kiện trạng thái; một sự kiện có thể được chuyển đến nhiều lần.

Chỉ dựa vào idempotency key do người gọi gửi là chưa đủ. Hệ thống phải gắn key với chủ thể, loại thao tác và nội dung yêu cầu theo hợp đồng API; dùng lại key với nội dung khác phải được xử lý rõ ràng. Khi cần chống lặp ở cấp nghiệp vụ, phải có định danh hoặc ràng buộc nghiệp vụ tương ứng ở máy chủ.

### 5.2. Nguồn sự thật và độ tin cậy

Không lấy giá, chủ sở hữu đơn hoặc vai trò phê duyệt từ payload trình duyệt làm sự thật. Những trường này phải được xác định hoặc kiểm chứng từ hệ thống có thẩm quyền.

Nếu phát sự kiện từ giao dịch cơ sở dữ liệu, có thể dùng transactional outbox để gắn thay đổi nghiệp vụ với việc ghi sự kiện cần phát. Consumer vẫn cần xử lý nhận lại và cập nhật sai thứ tự.

Thiết kế truy vết cần đủ để giải thích quyết định nhưng hạn chế dữ liệu nhạy cảm. Không đưa token, thông tin thẻ hoặc toàn bộ payload khách hàng vào cảnh báo. Quyền xem hồ sơ và thời hạn giữ dữ liệu phải phù hợp mục đích xử lý.

### 5.3. Event time, cửa sổ và sự kiện đến muộn

Nếu yêu cầu xảy ra lúc 10:00 nhưng đến detector lúc 10:07, dùng `ingested_at` thay `occurred_at` có thể làm thay đổi cửa sổ và kết quả.

Cần quy định:

- Cửa sổ tính theo event time hay processing time.
- Độ trễ được chấp nhận trước khi đóng kết quả.
- Sự kiện đến muộn sẽ cập nhật hồ sơ, tạo bổ sung hay chỉ dùng cho đối soát.
- Cách giữ lịch sử phiên bản quyết định khi tính lại.

Watermark chỉ thể hiện giả định tiến độ của luồng theo cấu hình; nó không bảo đảm rằng mọi sự kiện trong thực tế đã đến.

Với tác vụ chặn tức thời, không thể chờ vô hạn để đủ dữ liệu. Vì vậy, kiểm soát bắt buộc phải dựa vào trạng thái giao dịch có thẩm quyền; detector bổ sung tín hiệu theo ngân sách độ trễ của hệ thống.

## 6. Chọn đúng đơn vị gộp và baseline

### 6.1. Một ngưỡng toàn hệ thống thường quá thô

Các nhóm có hành vi hợp lệ khác nhau:

- Người mua cá nhân và tài khoản mua hàng cho doanh nghiệp.
- Khách hàng mới và khách hàng có lịch sử ổn định.
- Ngành hàng có tỷ lệ trả hàng thấp và ngành hàng cho phép đổi nhiều.
- Ngày thường và đợt thu hồi sản phẩm.
- Người tự thao tác và nhân viên được ủy quyền xử lý hàng loạt.

Phân nhóm, hay cohort, giúp so sánh những hành vi tương đồng. Tuy nhiên, chỉ nên tách nhóm khi có lý do nghiệp vụ, đủ dữ liệu và khả năng duy trì.

Một cohort quá nhỏ có thể tạo baseline thiếu ổn định. Khi thiếu dữ liệu, dùng cấu hình dự phòng đã được thẩm định và đánh dấu mức tin cậy; không mặc định coi tài khoản mới là an toàn.

### 6.2. Đừng để đối tượng tự chọn cohort có đặc quyền

Nếu “tài khoản doanh nghiệp” được áp ngưỡng cao hơn, thuộc tính đó cần đến từ dữ liệu được kiểm soát. Không dùng trường tự khai trong request để quyết định ngưỡng.

Tương tự, một người đã chiếm tài khoản lâu năm không trở nên an toàn chỉ vì tuổi tài khoản lớn. Các tín hiệu về thay đổi quyền, phương thức nhận tiền hoặc thông tin xác thực có thể cần được kết hợp ở các rule khác.

### 6.3. Baseline cần có nguồn và phiên bản

Khi dùng phân vị như P95 hoặc P99:

1. Chọn quần thể tham chiếu và khoảng thời gian rõ ràng.
2. Loại hoặc đánh dấu sự cố, chiến dịch và dữ liệu đã biết có lạm dụng.
3. Kiểm tra phân phối theo cohort và theo mùa vụ.
4. Đặt giới hạn cho mức tăng ngưỡng tự động.
5. Theo dõi việc ngưỡng thay đổi và yêu cầu xét duyệt khi vượt biên.

Phân vị cao không có nghĩa là “xác suất gian lận cao”. Trong dữ liệu nhiều giá trị bằng nhau, nó cũng không bảo đảm một tỷ lệ cảnh báo cố định.

Nếu liên tục học từ toàn bộ dữ liệu mới mà không kiểm soát, một đợt lạm dụng kéo dài có thể làm baseline tăng lên và khiến rule bớt nhạy.

## 7. Đánh giá bằng nhãn và chi phí nghiệp vụ

### 7.1. Chọn đơn vị đánh giá trước khi tính chỉ số

Ví dụ, đơn vị đánh giá là một **hồ sơ tài khoản cần điều tra**. Khi đó, mười cảnh báo của cùng hồ sơ không được tính thành mười lần phát hiện độc lập.

Ngược lại, nếu đánh giá theo giao dịch, phải nói rõ vì sao cùng một tài khoản có thể xuất hiện ở nhiều đơn vị và cách tính thiệt hại để không cộng trùng.

Các khái niệm:

- **True positive (TP):** rule phát hiện một đơn vị được xác minh có lạm dụng.
- **False positive (FP):** rule phát hiện nhưng đơn vị được xác minh là hợp lệ.
- **False negative (FN):** đơn vị có lạm dụng nhưng rule bỏ sót.
- **True negative (TN):** đơn vị hợp lệ và rule không phát hiện.

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
FPR       = FP / (FP + TN)
```

FPR không bằng `1 - Precision`: hai chỉ số có mẫu số khác nhau.

### 7.2. Ví dụ so sánh hai cấu hình

Giả sử tập đánh giá có 10.000 hồ sơ đã có nhãn đủ tin cậy, gồm 100 hồ sơ lạm dụng và 9.900 hồ sơ hợp lệ. Nhãn được xác định từ bằng chứng độc lập với việc rule có cảnh báo hay không.

| Chỉ số | Cấu hình A: nhạy hơn | Cấu hình B: chặt hơn |
|---|---:|---:|
| TP | 80 | 60 |
| FP | 320 | 60 |
| FN | 20 | 40 |
| TN | 9.580 | 9.840 |
| Tổng hồ sơ cảnh báo | 400 | 120 |
| Precision | 20% | 50% |
| Recall | 80% | 60% |
| FPR | khoảng 3,23% | khoảng 0,61% |

B có precision tốt hơn nhưng bỏ sót thêm 20 hồ sơ lạm dụng. Không thể quyết định chỉ từ một chỉ số.

Giả sử:

- Mỗi hồ sơ cần 5 phút xét duyệt.
- Mỗi hồ sơ lạm dụng bị bỏ sót gây thiệt hại trung bình 500.000 VND.
- Chi phí nhân sự quy đổi là 2.000 VND/phút.

Ước tính đơn giản cho cùng tập đánh giá:

```text
A:
  Chi phí xét duyệt = 400 × 5 × 2.000 = 4.000.000 VND
  Thiệt hại bỏ sót  = 20 × 500.000    = 10.000.000 VND
  Tổng             = 14.000.000 VND

B:
  Chi phí xét duyệt = 120 × 5 × 2.000 = 1.200.000 VND
  Thiệt hại bỏ sót  = 40 × 500.000    = 20.000.000 VND
  Tổng             = 21.200.000 VND
```

Theo giả định này, A có tổng chi phí thấp hơn dù precision kém hơn. Nhưng A cũng cần 2.000 phút xét duyệt, so với 600 phút của B. Nếu hàng đợi không đủ năng lực, hiệu quả ngăn thiệt hại của A có thể giảm vì hồ sơ được xử lý quá muộn.

Mô hình trên chưa tính tổn thất của trường hợp đã phát hiện nhưng vẫn không ngăn được, thời gian chờ của khách hợp lệ, khiếu nại, tổn thất uy tín hoặc sự khác biệt về giá trị từng vụ. Khi triển khai thật, cần đưa các yếu tố liên quan vào mục tiêu lựa chọn.

### 7.3. Cảnh báo thiên lệch nhãn

Nếu chỉ điều tra các trường hợp có cảnh báo, ta không biết đầy đủ FN. Không thể lấy số trường hợp gian lận đã phát hiện làm toàn bộ gian lận thực tế để tính recall.

Các cách cải thiện:

- Lấy mẫu kiểm tra trong nhóm không cảnh báo theo kế hoạch có kiểm soát.
- Kết hợp kết quả hậu kiểm, khiếu nại và đối soát đã xác minh.
- Chờ đủ thời gian để nhãn trưởng thành theo loại nghiệp vụ.
- Tách “chưa xác minh” khỏi “hợp lệ”.
- Ghi nhận xác suất lấy mẫu nếu cần ước lượng cho toàn quần thể.

Kết quả “nhân viên đã đóng cảnh báo” cũng không tự động đồng nghĩa với nhãn hợp lệ. Cần có lý do kết luận và bằng chứng.

## 8. Quy trình tuning có thể lặp lại

### Bước 1: Chốt mục tiêu và giới hạn vận hành

Ví dụ:

> Giảm thiệt hại do lạm dụng hoàn tiền, với giới hạn 150 hồ sơ mới mỗi ngày và thời gian chờ xét duyệt nằm trong SLO đã thống nhất.

Chỉ đặt “tăng precision” có thể khiến người vận hành nâng ngưỡng đến mức gần như không phát hiện gì. Chỉ đặt “tăng recall” có thể làm hàng đợi không xử lý nổi.

### Bước 2: Lưu cấu hình hiện tại làm mốc so sánh

Ghi lại:

- Phiên bản rule, định nghĩa feature và cohort.
- Khoảng thời gian đánh giá.
- Tình trạng dữ liệu và phiên bản nhãn.
- Chỉ số phát hiện, khối lượng hồ sơ, thời gian xử lý và tác động khách hàng.

Nếu feature đã đổi nghĩa, không nên coi kết quả là thay đổi ngưỡng đơn thuần.

### Bước 3: Tạo một số cấu hình ứng viên có lý do

Ví dụ:

| Ứng viên | Số đơn tối thiểu | Mức tiền tối thiểu | Tỷ lệ tối thiểu | Giả thuyết |
|---|---:|---:|---:|---|
| C0 | 5 | 2.000.000 VND | 0,80 | Cấu hình tham chiếu |
| C1 | 7 | 2.000.000 VND | 0,80 | Giảm cảnh báo do vài đơn nhỏ |
| C2 | 5 | 2.000.000 VND | 0,90 | Tập trung trường hợp gần hoàn toàn bộ |
| C3 | 5 | 5.000.000 VND | 0,80 | Ưu tiên hồ sơ có giá trị kinh tế lớn |

Có thể khảo sát nhiều chiều trên dữ liệu ngoại tuyến, nhưng khi đưa vào vận hành nên giữ thay đổi đủ hẹp để giải thích được nguyên nhân.

### Bước 4: Backtest theo thời gian

Chia dữ liệu thành giai đoạn xác lập baseline, giai đoạn chọn cấu hình và giai đoạn kiểm tra giữ lại theo thứ tự thời gian.

Không chia ngẫu nhiên từng dòng nếu dữ liệu có chuỗi theo tài khoản, các sự kiện cùng hồ sơ hoặc nhiều bản ghi của cùng giao dịch. Cách chia đó có thể làm rò rỉ thông tin và khiến kết quả lạc quan.

Replay phải mô phỏng điều kiện detector đã biết tại từng thời điểm:

- Trạng thái và dữ liệu sẵn có lúc đó.
- Độ trễ, nhận lại và sai thứ tự của sự kiện.
- Lịch sử đủ dài trước điểm bắt đầu để làm ấm cửa sổ.
- Phiên bản rule, danh sách ngoại lệ và cohort có hiệu lực lúc đó.
- Chính sách nhóm cảnh báo và thời gian hạn chế thông báo lặp.

Có thể dùng nhãn hậu kiểm để chấm kết quả, nhưng không được dùng nhãn tương lai hoặc trạng thái được cập nhật trong tương lai để xây feature quá khứ.

### Bước 5: Đọc các trường hợp sai cụ thể

Với FP, phân biệt:

- Khác biệt hành vi hợp lệ của một cohort.
- Sự cố nghiệp vụ như hàng lỗi hàng loạt.
- Retry hoặc sự kiện bị tính trùng.
- Thiếu mẫu số hoặc gộp sai đơn.
- Rule đúng tín hiệu nhưng phản ứng quá mạnh.

Với FN, xem:

- Hành vi chỉ nằm dưới ngưỡng hiện tại.
- Chia nhỏ thao tác qua nhiều cửa sổ.
- Chuyển qua nhiều tài khoản hoặc đối tượng.
- Tận dụng bước phê duyệt chưa được bảo vệ đúng.
- Detector nhận dữ liệu sau thời điểm còn có thể ngăn thiệt hại.

Lỗi invariant, quyền hoặc transaction phải được sửa tại kiểm soát tương ứng. Không cố giải quyết bằng việc tinh chỉnh detector.

### Bước 6: Kiểm tra trên giai đoạn chưa dùng để chọn ngưỡng

Đánh giá cấu hình đã chọn trên phần dữ liệu giữ lại. Nếu tiếp tục sửa theo phần này, cần một phần kiểm tra độc lập mới hoặc đánh giá triển khai có kiểm soát.

Báo cáo theo cohort và nhóm giá trị thiệt hại. Chỉ số tổng thể tốt có thể che việc bỏ sót nhiều ở nhóm giao dịch lớn.

## 9. Điều chỉnh phản ứng và quản lý nhiễu

### 9.1. Phân tầng hành động

| Mức xử lý | Ví dụ sử dụng |
|---|---|
| Ghi nhận | Rule mới cần quan sát chất lượng tín hiệu |
| Tạo hoặc bổ sung hồ sơ | Cần người điều tra chuỗi hành vi |
| Xác minh bổ sung | Cần chứng minh thêm quyền hoặc ý định thao tác |
| Chuyển sang xét duyệt | Tác động tài chính còn đang chờ quyết định |
| Từ chối theo chính sách | Có điều kiện và thẩm quyền từ chối đã được xác lập |

Chuyển sang xét duyệt phải là một chuyển trạng thái nghiệp vụ hợp lệ, có quyền thực hiện và có audit. Một cảnh báo không được tùy ý ghi đè trạng thái giao dịch.

Nếu detector và hệ thống hoàn tiền chạy tách biệt, lệnh yêu cầu xét duyệt có thể đến lặp hoặc đến sau khi trạng thái đã đổi. Bên nhận phải thực thi idempotency và kiểm tra trạng thái hiện tại trước khi chuyển.

### 9.2. Nhóm cảnh báo và hạn chế thông báo lặp

Một tài khoản đã có hồ sơ mở không nhất thiết cần thêm một hồ sơ cho mỗi sự kiện mới. Có thể nhóm theo:

```text
tenant_id + account_id + rule_family + review_episode
```

`review_episode` phải có quy tắc mở, đóng và mở lại rõ ràng. Trong cùng đợt điều tra, vẫn lưu và cập nhật bằng chứng mới.

Phân biệt:

- **Khử trùng lặp xử lý:** cùng một sự kiện hoặc thao tác không làm feature tăng hai lần.
- **Nhóm hồ sơ:** nhiều tín hiệu liên quan được đưa về một hồ sơ.
- **Cooldown:** giảm số lần gửi thông báo.
- **Dừng đánh giá:** ngừng nhìn thấy tín hiệu mới; đây thường là hậu quả không mong muốn.

Cooldown không được che một đợt tăng mạnh về giá trị, một đối tượng mới có rủi ro cao hoặc hành vi vi phạm kiểm soát bắt buộc.

### 9.3. Hysteresis

Nếu hồ sơ được mở khi điểm vượt ngưỡng rồi đóng ngay khi điểm giảm rất ít, trạng thái có thể dao động liên tục.

Ví dụ, đối với một chỉ số đã được định nghĩa:

- Mở hồ sơ khi chỉ số đạt từ 0,80.
- Chỉ coi tín hiệu đã hạ khi xuống dưới 0,60 và không có bằng chứng nghiêm trọng mới trong khoảng thời gian đã quy định.

Đó là hysteresis: điều kiện vào và ra khác nhau. Việc tự đóng hồ sơ hay gỡ xét duyệt vẫn phải tuân theo quy trình nghiệp vụ; chỉ số giảm không có nghĩa vụ việc đã được giải quyết.

### 9.4. Ngoại lệ có kiểm soát

Một ngoại lệ hợp lý cần có chủ sở hữu, lý do, phạm vi, thời hạn và lịch sử thay đổi.

Ví dụ, một đợt thu hồi sản phẩm có thể cần quy trình xử lý riêng cho các đơn bị ảnh hưởng. Không nên đưa mọi tài khoản liên quan vào danh sách miễn kiểm tra vĩnh viễn.

Ngoại lệ chỉ được tác động đến rule hoặc cách xử lý đã xác định. Nó không cấp quyền truy cập đơn của người khác và không cho phép hoàn vượt tiền.

## 10. Minh họa evaluator bằng Java

Ví dụ sau tập trung vào phần đánh giá một snapshot đã được chuẩn bị. Nó không xây stream processor, không cập nhật giao dịch và không chuyển tiền.

`windowReady` biểu thị snapshot đạt hợp đồng về độ mới và tiến độ dữ liệu đã thống nhất. Nó không phải bằng chứng tuyệt đối rằng sẽ không có sự kiện đến muộn.

```java
import java.math.BigDecimal;
import java.util.Objects;

public final class RefundAnomalyRule {
    public enum Outcome {
        NO_MATCH,
        REVIEW,
        DATA_ISSUE
    }

    public record Config(
            String version,
            int minDistinctOrders,
            BigDecimal minCapturedVnd,
            BigDecimal minRequestedShare) {

        public Config {
            Objects.requireNonNull(version);
            Objects.requireNonNull(minCapturedVnd);
            Objects.requireNonNull(minRequestedShare);

            if (version.isBlank()
                    || minDistinctOrders < 1
                    || minCapturedVnd.signum() <= 0
                    || minRequestedShare.signum() <= 0
                    || minRequestedShare.compareTo(BigDecimal.ONE) > 0) {
                throw new IllegalArgumentException("Invalid rule config");
            }
        }
    }

    public record WindowFacts(
            boolean windowReady,
            String currency,
            int distinctOrders,
            BigDecimal capturedForObservedOrders,
            BigDecimal requestedAmount) {
    }

    public record Decision(
            Outcome outcome,
            String ruleVersion,
            String reason) {
    }

    public static Decision evaluate(Config config, WindowFacts facts) {
        Objects.requireNonNull(config);

        if (facts == null
                || !facts.windowReady()
                || !"VND".equals(facts.currency())
                || facts.distinctOrders() < 0
                || facts.capturedForObservedOrders() == null
                || facts.requestedAmount() == null) {
            return new Decision(
                    Outcome.DATA_ISSUE,
                    config.version(),
                    "INCOMPLETE_OR_UNSUPPORTED_SNAPSHOT");
        }

        BigDecimal captured = facts.capturedForObservedOrders();
        BigDecimal requested = facts.requestedAmount();

        if (captured.signum() <= 0
                || requested.signum() < 0
                || requested.compareTo(captured) > 0) {
            return new Decision(
                    Outcome.DATA_ISSUE,
                    config.version(),
                    "INCONSISTENT_AMOUNT_SNAPSHOT");
        }

        if (facts.distinctOrders() < config.minDistinctOrders()
                || captured.compareTo(config.minCapturedVnd()) < 0) {
            return new Decision(
                    Outcome.NO_MATCH,
                    config.version(),
                    "BELOW_MINIMUM_EXPOSURE");
        }

        // requested / captured >= threshold
        // So sanh bang phep nhan de khong lam tron ty le.
        BigDecimal requiredAmount =
                captured.multiply(config.minRequestedShare());

        boolean matched = requested.compareTo(requiredAmount) >= 0;

        return new Decision(
                matched ? Outcome.REVIEW : Outcome.NO_MATCH,
                config.version(),
                matched ? "HIGH_REFUND_CONCENTRATION" : "BELOW_SHARE_THRESHOLD");
    }
}
```

Cấu hình minh họa:

```java
var config = new RefundAnomalyRule.Config(
        "refund-concentration-v3",
        5,
        new BigDecimal("2000000"),
        new BigDecimal("0.80"));

var facts = new RefundAnomalyRule.WindowFacts(
        true,
        "VND",
        5,
        new BigDecimal("3000000"),
        new BigDecimal("2700000"));

var decision = RefundAnomalyRule.evaluate(config, facts);
// outcome = REVIEW; requested_share = 0.90
```

Những điểm cần giữ khi tích hợp:

- `NO_MATCH` chỉ nghĩa là không khớp rule này; không phải lệnh cho phép hoàn tiền.
- `REVIEW` là yêu cầu đi theo chính sách xét duyệt, không phải kết luận gian lận.
- `DATA_ISSUE` phải đi theo chính sách dự phòng riêng, có đo lường.
- Snapshot trống cần được biểu diễn rõ ở tầng dựng feature. Trong ví dụ, snapshot không có khoản thu dương được trả về `DATA_ISSUE`, không thực hiện phép chia.
- `BigDecimal` nhận giá trị từ chuỗi hoặc kiểu số tiền chính xác; tránh tạo số tiền qua `double`.
- Hàm giả định việc lọc trạng thái, chọn cửa sổ, gộp đúng tập đơn và khử trùng lặp đã được thực hiện đúng.
- Kiểm tra nhất quán của snapshot không thay thế invariant trong transaction hoàn tiền.

Ví dụ dùng cú pháp record của Java 17. Một triển khai thực tế cần giới hạn kích thước và độ phức tạp của dữ liệu đầu vào trước khi thực hiện tổng hợp.

## 11. Triển khai cấu hình và rollback

### 11.1. Cấu hình phải có phiên bản

Có thể mô tả cấu hình triển khai như sau:

```yaml
rule_id: refund-concentration
version: 3
feature_definition_version: 2
cohort_policy_version: 1
window: PT24H
currency: VND
min_distinct_orders: 5
min_captured_amount: "2000000"
min_requested_share: "0.80"
action_policy: manual-review-v2
owner: refund-risk-team
```

Đây là ví dụ cấu hình detector, không phải metadata của bài học.

Mỗi quyết định nên truy được rule, feature và chính sách hành động đã dùng. Trước khi kích hoạt, kiểm tra miền giá trị, field bắt buộc và sự tương thích giữa các phiên bản.

Nếu đổi cách định nghĩa feature, chỉ rollback ngưỡng có thể không khôi phục hành vi cũ. Kế hoạch rollback phải tính cả schema, trạng thái cửa sổ và khả năng đọc feature phiên bản trước.

### 11.2. Shadow

Chạy ứng viên trên dữ liệu thực nhưng chỉ ghi kết quả so sánh. Các kiểm soát đang hoạt động vẫn thực thi như hiện tại.

Quan sát:

- Số hồ sơ mới sau khi nhóm.
- Các trường hợp chỉ rule cũ phát hiện hoặc chỉ ứng viên phát hiện.
- Phân bố theo cohort và giá trị tiền.
- Tỷ lệ snapshot thiếu hoặc trễ.
- Ước tính khối lượng xét duyệt và ảnh hưởng đến khách hàng.

Shadow không tự tạo được nhãn phản thực tế: nếu ứng viên có hành động khác, hành vi sau đó của khách hàng cũng có thể khác. Cần kết hợp đánh giá bằng chứng và triển khai có kiểm soát.

### 11.3. Canary

Chọn một tập nhỏ bằng tiêu chí ổn định, ví dụ băm `tenant_id + account_id`, để một chủ thể không đổi cấu hình giữa các lần retry.

Chọn đơn vị canary phù hợp phạm vi tác động. Nếu tài khoản liên quan chặt chẽ trong cùng tổ chức, việc chia riêng từng tài khoản có thể gây nhiễu; cần cân nhắc gán theo tổ chức.

Chỉ bật hành động mới trong phạm vi canary đã xác định. Các kiểm soát bắt buộc luôn có hiệu lực.

Điều kiện dừng hoặc rollback có thể gồm:

- Khối lượng hồ sơ vượt năng lực xử lý.
- Thời gian chờ hoặc khiếu nại của khách hợp lệ tăng vượt giới hạn.
- Mức bỏ sót hoặc thiệt hại vượt phạm vi chấp nhận.
- Độ trễ detector, tỷ lệ lỗi hoặc chất lượng feature không đạt SLO.

### 11.4. Rollback không tự đảo ngược nghiệp vụ

Đổi lại cấu hình cũ chỉ ảnh hưởng các đánh giá tiếp theo theo thiết kế. Nó không tự trả tiền đã giữ, đóng hồ sơ đang mở hoặc đảo giao dịch đã thực hiện.

Các hồ sơ và trạng thái chịu tác động cần quy trình xử lý riêng, có quyền và audit. Không được tự giải phóng toàn bộ giao dịch đang xét duyệt chỉ vì cấu hình vừa rollback.

## 12. Bộ tình huống kiểm thử cần thiết

Kiểm thử cần xác nhận cả kết quả rule và tác động nghiệp vụ xung quanh.

| Tình huống | Kết quả mong đợi |
|---|---|
| 4 đơn, đủ tiền, tỷ lệ 0,90 | Không khớp vì chưa đủ số đơn |
| 5 đơn, đủ tiền, tỷ lệ đúng 0,80 | Khớp vì điều kiện dùng lớn hơn hoặc bằng |
| 5 đơn, đủ tiền, tỷ lệ 0,7999 | Không khớp; không làm tròn lên thành 0,80 |
| Đủ đơn và tỷ lệ nhưng dưới mức tiền tối thiểu | Không khớp rule minh họa |
| Nhận lại cùng `event_id` | Feature và hồ sơ không bị nhân đôi |
| Retry cùng thao tác với nhiều lần gửi HTTP | Không tạo thêm lần hoàn hoặc tăng số đơn |
| Hai lần hoàn một phần hợp lệ trên cùng đơn | Cộng đúng tiền yêu cầu, chỉ đếm đơn một lần |
| Hai request đồng thời dùng cùng số dư hoàn | Transaction bảo vệ invariant độc lập với detector |
| Một yêu cầu bị hủy đến sau sự kiện tạo yêu cầu | Dựng lại trạng thái đúng bằng version và thời điểm |
| Sự kiện đến sai thứ tự | Không để trạng thái cũ ghi đè trạng thái mới |
| Sự kiện sát biên 24 giờ | Tuân thủ chính xác quy ước biên cửa sổ |
| Thiếu khoản thu hoặc stream quá trễ | Đi vào nhánh chất lượng dữ liệu |
| Gộp dữ liệu khác tiền tệ | Bị ngăn hoặc tách nhóm trước khi tính |
| Khách hợp lệ trong đợt thu hồi sản phẩm | Được đánh giá theo chính sách có bằng chứng |
| Chia yêu cầu sát ngưỡng hoặc qua nhiều tài khoản | Đánh giá khoảng trống phát hiện và rule bổ sung |
| Detector không khả dụng | Không bỏ qua quyền, state machine hoặc giới hạn tiền |
| Lệnh xét duyệt đến sau khi giao dịch đã hoàn tất | Không chuyển trạng thái trái phép; ghi nhận để xử lý |
| Đổi phiên bản giữa các lần retry | Không lặp tác động tài chính; có lịch sử quyết định |

Không cần cố nhét mọi kiểu lạm dụng vào một rule. Ví dụ, hành vi dùng nhiều tài khoản có thể cần tín hiệu liên kết có cơ sở và quyền sử dụng phù hợp. Địa chỉ IP dùng chung tự nó chưa đủ để kết luận các tài khoản cùng một người.

Ngoài kiểm thử từng trường hợp, nên có replay một chuỗi hoàn chỉnh: tạo đơn, thanh toán, yêu cầu hoàn, retry, xét duyệt, hủy hoặc chi tiền, nhận lại sự kiện và đánh giá lại.

## 13. Theo dõi sau triển khai

### 13.1. Chỉ số nên theo dõi

| Nhóm | Chỉ số gợi ý |
|---|---|
| Phát hiện | TP, FP, FN khi có nhãn; precision và recall kèm phạm vi đánh giá |
| Tác động kinh tế | Giá trị lạm dụng xác nhận, thiệt hại, giá trị thực sự ngăn được |
| Vận hành | Hồ sơ mới, backlog, thời gian chờ và thời gian xử lý |
| Khách hàng | Tỷ lệ yêu cầu hợp lệ bị giữ xét duyệt, thời gian trì hoãn, khiếu nại |
| Dữ liệu | Độ trễ, sự kiện trùng, thiếu field, snapshot không nhất quán |
| Hệ thống | Độ trễ đánh giá, lỗi, độ mới cấu hình, chi phí lưu trữ cửa sổ |
| Ổn định | Phân bố feature, tỷ lệ khớp theo cohort, mức sử dụng ngoại lệ |

Với tỷ lệ cảnh báo, luôn ghi mẫu số: số request HTTP, thao tác nghiệp vụ, tài khoản hoạt động hay hồ sơ sau nhóm. Hai dashboard dùng hai mẫu số khác nhau có thể đưa ra kết luận trái ngược.

Tỷ lệ cảnh báo giảm có thể do ít lạm dụng hơn, nhưng cũng có thể do mất sự kiện, cửa sổ chưa làm ấm hoặc cấu hình không được nạp. Cần đối chiếu nhiều tín hiệu.

### 13.2. Runbook khi cảnh báo tăng đột biến

Một trình tự xử lý thực tế:

1. Kiểm tra luồng sự kiện, khử trùng lặp, tiền tệ và độ mới dữ liệu.
2. Kiểm tra thay đổi cấu hình, feature hoặc quy trình nghiệp vụ gần nhất.
3. Xem một số hồ sơ đại diện và phân bố theo cohort.
4. Xác định đây là lạm dụng thật, sự cố nghiệp vụ hay lỗi detector.
5. Áp dụng điều chỉnh có phạm vi và có thời hạn nếu cần.
6. Đối soát các quyết định đã bị ảnh hưởng và bổ sung kiểm thử cho nguyên nhân đã tìm thấy.

Nếu detector gặp lỗi, chính sách dự phòng cần cân bằng thiệt hại và khả năng phục vụ. Một luồng chi tiền giá trị lớn có thể giữ lại để xét duyệt; một tín hiệu chỉ phục vụ quan sát có thể tạm ngừng cảnh báo. Quyết định này phải được xác lập trước và không được làm mất các invariant bắt buộc.

## 14. Những lỗi tuning thường gặp

| Lỗi | Vì sao nguy hiểm | Hướng sửa |
|---|---|---|
| Tăng ngưỡng chỉ để giảm số cảnh báo | Có thể che cả lạm dụng thật | Đọc mẫu FP/FN và đánh giá thiệt hại |
| Tính mỗi HTTP retry thành một nghiệp vụ | Tạo FP khi mạng hoặc client lỗi | Gộp theo định danh thao tác phù hợp |
| Dùng cùng một ngưỡng cho mọi cohort | Nhầm hành vi phổ biến của nhóm này với bất thường | Tách nhóm có lý do và đủ dữ liệu |
| Gán không có nhãn thành hợp lệ | Làm precision và recall thiếu tin cậy | Giữ trạng thái chưa xác minh |
| Tối ưu accuracy trên dữ liệu hiếm gian lận | Bỏ qua toàn bộ gian lận vẫn có thể có accuracy cao | Dùng chỉ số phát hiện và chi phí |
| Dùng trạng thái tương lai trong backtest | Đánh giá quá tốt so với vận hành thật | Dựng feature theo thông tin có tại thời điểm đó |
| Allowlist vĩnh viễn | Tạo vùng mù cho tài khoản bị chiếm hoặc quyền bị lạm dụng | Giới hạn phạm vi, thời hạn và kiểm tra lại |
| Đổi rule mà không lưu phiên bản | Không giải thích được quyết định cũ | Version hóa cấu hình, feature và hành động |
| Xem giảm cảnh báo là thành công | Có thể do detector mất dữ liệu | Theo dõi chất lượng dữ liệu và kết quả nghiệp vụ |
| Dùng detector thay kiểm tra quyền hoặc tiền | Cửa sổ phát hiện có thể bỏ lọt vi phạm tức thời | Giữ kiểm soát bắt buộc tại nơi thực thi |

## 15. Bài tập áp dụng

Bạn phụ trách luồng hoàn tiền có ba nhóm khách hàng: cá nhân, doanh nghiệp mua số lượng lớn và khách hàng tham gia một đợt thu hồi sản phẩm.

Hãy thiết kế đề xuất tuning bằng cách trả lời:

1. Tập sự kiện nào được dùng để tính rule? Retry và hoàn một phần được nhận diện thế nào?
2. Đơn vị gộp và mẫu số là gì? Cần tách cohort nào, dựa trên thuộc tính do ai quản lý?
3. Cần tối thiểu bao nhiêu dữ liệu trước khi đánh giá? Khi thiếu dữ liệu, luồng đi đâu?
4. Ba cấu hình ứng viên khác nhau ở đâu và mỗi thay đổi kiểm chứng giả thuyết gì?
5. Có thể thu thập nhãn cho nhóm không cảnh báo bằng cách nào?
6. Chọn cấu hình dựa trên precision, recall, thiệt hại và năng lực xét duyệt ra sao?
7. Shadow và canary sẽ theo dõi chỉ số nào? Điều kiện rollback là gì?
8. Nếu phát hiện yêu cầu hoàn vượt số dư do hai request đồng thời, phải sửa ở đâu?

Một đề xuất tốt cần giải thích được vì sao mỗi ngưỡng tồn tại, dữ liệu nào tạo ra quyết định và ai xử lý tác động tiếp theo. Nếu chưa chứng minh được tính đúng của feature, bước tiếp theo là sửa dữ liệu hoặc định nghĩa nghiệp vụ trước khi chọn lại ngưỡng.
