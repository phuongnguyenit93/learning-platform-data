# Normal behavior baseline — Xây dựng đường cơ sở hành vi bình thường

## Mục tiêu và phạm vi

Normal behavior baseline là mô hình tham chiếu mô tả hành vi thường gặp trong một ngữ cảnh xác định. Hệ thống so sánh hành vi đang quan sát với đường cơ sở này để phát hiện những thay đổi cần chú ý.

Trong bảo mật logic nghiệp vụ, đường cơ sở có thể giúp phát hiện một nhân viên hỗ trợ đột ngột sửa nhiều đơn hàng, tài khoản sử dụng ưu đãi với nhịp độ khác thường hoặc một nhóm tài khoản phối hợp tạo giá trị ngoài dự kiến.

Tuy nhiên, “thường xảy ra” không đồng nghĩa “được phép”. Một thao tác sai quyền vẫn phải bị chặn dù trông giống lịch sử. Một thao tác khác lịch sử có thể hoàn toàn hợp lệ, chẳng hạn xử lý tồn đọng sau sự cố.

Sau bài học, bạn có thể:

- Chọn hành vi, đơn vị quan sát và nhóm tham chiếu phù hợp.
- Phân biệt dữ liệu bằng 0 với thiếu quan sát hoặc không có cơ hội thực hiện.
- Xây dựng baseline theo actor, cohort, tenant và thời điểm.
- Sử dụng các thống kê đơn giản, hiểu giới hạn của điểm bất thường.
- Xử lý cold start, mùa vụ, drift và hành vi đầu độc dữ liệu.
- Gắn tín hiệu bất thường với quyền theo đối tượng, state machine, transaction và idempotency.
- Kiểm thử tính đúng đắn của dữ liệu, baseline và phản ứng nghiệp vụ.

Các khoảng thời gian và ngưỡng trong bài chỉ là minh họa thiết kế, không phải mức chuẩn áp dụng cho mọi hệ thống.

## 1. Baseline mô tả hành vi, không cấp quyền nghiệp vụ

Giả sử một nền tảng có nhân viên hỗ trợ được phép sửa địa chỉ giao hàng trước khi đơn được bàn giao. Hệ thống muốn biết khi nào số lần sửa địa chỉ của một nhân viên tăng mạnh so với nhịp làm việc thường thấy.

Có ba câu hỏi khác nhau:

| Câu hỏi | Cơ chế phù hợp |
| --- | --- |
| Nhân viên có quyền sửa đơn hàng này không? | Authorization theo tenant, đối tượng và hành động |
| Đơn đã bàn giao có còn được sửa không? | Bất biến nghiệp vụ và state machine |
| Nhân viên đang sửa nhiều hoặc theo cách khác thường không? | Baseline và phát hiện bất thường |

Không dùng câu trả lời cho câu hỏi thứ ba để thay thế hai câu hỏi đầu.

Ví dụ:

- Nhân viên thường sửa 20 đơn mỗi ca nhưng sửa một đơn thuộc tenant khác: phải chặn vì sai quyền.
- Nhân viên thường sửa 2 đơn mỗi nửa giờ nhưng hôm nay sửa 8 đơn sau đợt nhập địa chỉ lỗi: cần ngữ cảnh bổ sung.
- Nhân viên thực hiện hành vi lạm dụng đều đặn trong nhiều tuần: hành vi có thể đã trở nên “quen thuộc” trong dữ liệu nhưng vẫn sai nghiệp vụ.

OWASP khuyến nghị kiểm soát workflow, quyền và các thao tác nhạy cảm ngay tại tầng nghiệp vụ. Trong thiết kế này, anomaly detection bổ sung tín hiệu quan sát; các bất biến bắt buộc vẫn được thực thi độc lập. [OWASP Business Logic Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html).

### 1.1. Phân biệt baseline, ngưỡng và hạn mức

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Baseline | Phân bố tham chiếu của hành vi | Median và độ phân tán của số lần sửa mỗi 30 phút |
| Ngưỡng phát hiện | Điều kiện đánh dấu lệch khỏi tham chiếu | Điểm vượt ngưỡng đã hiệu chỉnh |
| Hạn mức nghiệp vụ | Giới hạn bắt buộc độc lập với lịch sử | Một đơn không được sửa sau khi bàn giao |
| Chính sách phản ứng | Hành động khi có tín hiệu | Ghi nhận, xác minh, review hoặc chặn theo quyền và bằng chứng |

Baseline có thể thay đổi khi sản phẩm hoặc cách làm việc thay đổi. Điều đó không tự nới hạn mức nghiệp vụ.

### 1.2. Chọn rõ phát hiện sau sự kiện hay ngăn trước thao tác

Bài này dùng ví dụ chính là:

~~~text
Số lần thay đổi địa chỉ đã commit,
theo từng actor trong từng cửa sổ 30 phút đã đóng.
~~~

Đây là tín hiệu phát hiện sau khi cửa sổ kết thúc. Nó không thể tự ngăn các thay đổi đã xảy ra trong cửa sổ đó.

Nếu cần ra quyết định trước thao tác, phải định nghĩa feature online riêng, chẳng hạn số lần thử logic trong cửa sổ trượt có tính cả lần hiện tại. Baseline và cơ chế đếm của feature online phải được xây tương ứng.

Không lấy phân bố của các cửa sổ cố định đã đóng rồi mặc định áp dụng nguyên xi cho cửa sổ trượt, cửa sổ đang chạy hoặc giá trị dự đoán sau thao tác.

## 2. Định nghĩa hành vi trước khi tính thống kê

### 2.1. Một metric cần contract đầy đủ

Với ví dụ sửa địa chỉ:

~~~text
metricName: address_changes_committed_per_30m
metricVersion: 1
entity: tenantId + actorId
action: CHANGE_DELIVERY_ADDRESS
unit: số operationId thành công khác nhau
window: 30 phút cố định, biên [start, end)
eligibility: actor thuộc nhóm hỗ trợ phù hợp và có ca làm được xác định
outcome: thay đổi đã commit
source: sự kiện nghiệp vụ do backend tạo
~~~

Mốc 10:00:00 thuộc cửa sổ 10:00–10:30, không thuộc cửa sổ 09:30–10:00 theo định nghĩa trên.

Cần xác định thêm:

- Một thao tác sửa nhiều trường trong cùng đơn là một operation hay nhiều operation?
- Retry cùng thao tác có được đếm thêm không?
- Một đơn bị sửa hai lần có tính hai thay đổi không?
- Tính theo người trực tiếp thao tác hay tài khoản dịch vụ thực thi thay?
- Actor đang chuyển vai trò hoặc tenant thì gắn hành vi vào ngữ cảnh nào?

Trong ví dụ, mỗi thay đổi nghiệp vụ đã commit có một `operationId` riêng. Retry của cùng operation không tăng số đếm. Hai lần thay đổi có chủ đích khác nhau được tính riêng dù cùng một đơn hàng.

### 2.2. Tách danh tính, nguồn dữ liệu và phạm vi

Actor và tenant phải đến từ ngữ cảnh được xác thực và bản ghi nghiệp vụ. Không cho client tự gửi:

~~~json
{
  "tenantId": "tenant-other",
  "actorRole": "senior-support",
  "historicalAverage": 1000,
  "currentCount": 0,
  "baselineId": "more-permissive-baseline"
}
~~~

Client không được chọn cohort ít chặt chẽ hơn hoặc tự khai dữ liệu lịch sử để làm hành vi hiện tại trông bình thường.

Nếu thao tác qua tài khoản dịch vụ, nên lưu cả chủ thể được ủy quyền và chủ thể thực thi theo contract. Nếu chỉ gộp mọi hoạt động vào một service account, hành vi của từng nhân viên có thể bị che khuất.

### 2.3. Số 0 không giống thiếu dữ liệu

| Trạng thái | Ý nghĩa |
| --- | --- |
| `OBSERVED(0)` | Hệ thống quan sát đầy đủ một cửa sổ đủ điều kiện và không có hành động |
| `MISSING` | Không biết có bao nhiêu hành động |
| `PARTIAL` | Chỉ quan sát được một phần cửa sổ hoặc một phần nguồn |
| `NOT_ELIGIBLE` | Cửa sổ không thuộc tập cơ hội thực hiện đã định nghĩa |
| `STALE` | Dữ liệu chưa cập nhật đến thời điểm cần thiết |

Nếu pipeline mất dữ liệu 3 giờ, không tạo sáu cửa sổ giá trị 0 rồi đưa vào baseline. Điều đó có thể làm đường cơ sở thấp giả tạo và gây hàng loạt cảnh báo khi dữ liệu trở lại.

Ngược lại, nếu chỉ lưu những cửa sổ có sự kiện mà bỏ mọi cửa sổ 0 được quan sát đầy đủ, baseline có thể bị đẩy cao. Cần tạo tập cửa sổ đủ điều kiện trước, rồi gắn giá trị và chất lượng dữ liệu.

### 2.4. Cơ hội thực hiện là một phần của ngữ cảnh

Nhân viên có 200 đơn được phân công và người có 5 đơn không có cùng mức tiếp xúc với hành vi sửa địa chỉ.

Ngoài số đếm tuyệt đối, có thể xét:

~~~text
tỷ lệ sửa = số đơn được sửa / số đơn đủ điều kiện được phân công
~~~

Phải xác định tử số, mẫu số, cửa sổ và tiêu chí đủ điều kiện. Với mẫu số bằng 0, tỷ lệ là không xác định hoặc không áp dụng, không mặc định bằng 0.

Mẫu số nhỏ làm tỷ lệ biến động mạnh. Một lần sửa trên một đơn không thể được diễn giải giống 100 lần sửa trên 100 đơn chỉ vì cùng tỷ lệ 100%. Khi dùng tỷ lệ, lưu cả tử số, mẫu số và mức hỗ trợ dữ liệu.

## 3. Chọn đúng nhóm tham chiếu

### 3.1. Baseline cá nhân và baseline nhóm

| Loại baseline | Điểm hữu ích | Giới hạn |
| --- | --- | --- |
| Theo actor | Phát hiện thay đổi so với chính người đó | Thiếu lịch sử, đổi nhiệm vụ, có thể học theo hành vi lạm dụng |
| Theo cohort | So với nhóm cùng vai trò và bối cảnh | Nhóm không đồng nhất có thể tạo so sánh sai |
| Theo tenant | Phản ánh quy mô và cách vận hành riêng | Tenant mới ít dữ liệu, dễ bị một actor chi phối |
| Theo hệ thống | Dễ có nhiều mẫu | Có thể che khuất khác biệt quy mô và bối cảnh |
| Kết hợp phân cấp | Có fallback khi dữ liệu riêng chưa đủ | Cần ghi rõ baseline thực sự được dùng |

Một cohort có thể dựa trên tenant, vai trò, kênh hỗ trợ, loại đơn và ca làm việc. Không tạo quá nhiều chiều đến mức mỗi nhóm chỉ còn vài mẫu.

Các thuộc tính phân nhóm phải có nguồn và thời điểm hiệu lực rõ ràng. Một người đổi vai trò không nên được gán toàn bộ lịch sử cũ sang cohort mới như thể đã luôn làm cùng nhiệm vụ.

### 3.2. Fallback cần công khai trong kết quả

Một chuỗi fallback minh họa:

~~~text
baseline cá nhân đủ dữ liệu
    -> nếu không đủ: cohort cùng tenant và nhiệm vụ
    -> nếu không đủ: baseline rộng hơn đã được phê duyệt
    -> nếu vẫn không đủ: INSUFFICIENT_BASELINE
~~~

Baseline rộng hơn không tự được phép trộn dữ liệu tenant khác. Nếu sản phẩm dùng thống kê tổng hợp liên tenant, phải thiết kế riêng cách phân vùng, quyền truy cập và độ phù hợp; nó không phải fallback ngầm.

Kết quả cần ghi `baselineScope`, lý do fallback và lượng dữ liệu hỗ trợ. Không trả cùng một điểm nhưng giấu việc một người được so với chính mình, còn người khác được so với toàn hệ thống.

### 3.3. Mùa vụ và thay đổi khối lượng công việc

Ca sáng, ca đêm, ngày trong tuần và đợt phát hành sản phẩm có thể có nhịp khác nhau. Có thể:

- Tách nhóm theo ca hoặc khung giờ nghiệp vụ.
- So sánh cùng loại ngày hoặc cùng giai đoạn chiến dịch.
- Chuẩn hóa theo số đơn đủ điều kiện xử lý.
- Đánh dấu các sự kiện vận hành đã biết, như xử lý tồn đọng.

NIST mô tả seasonality là biến động có tính chu kỳ và nhấn mạnh cần đưa yếu tố này vào mô hình chuỗi thời gian khi nó hiện diện. Với hành vi nghiệp vụ, điều đó gợi ý so sánh các khoảng có bối cảnh tương ứng thay vì dùng một mức trung bình chung. [NIST, Seasonality](https://www.itl.nist.gov/div898/handbook/pmc/section4/pmc443.htm).

Khi cohort phụ thuộc lịch địa phương, lưu múi giờ nghiệp vụ và quy tắc phân nhóm. Timestamp sự kiện vẫn nên biểu diễn thời điểm tuyệt đối; thay đổi múi giờ hiển thị không được đổi baseline một cách tùy ý.

## 4. Xây dựng baseline từ dữ liệu lịch sử đủ chất lượng

### 4.1. Xác định tập huấn luyện

Một cấu hình xây dựng baseline có thể quy định:

~~~text
trainingRange: một giai đoạn lịch sử đã đóng
windowSpec: cửa sổ 30 phút cố định
cohortDefinitionVersion: phiên bản phân nhóm
featureSchemaVersion: phiên bản metric
eligibilityPolicy: cửa sổ nào được tham gia
qualityPolicy: độ đầy đủ và độ trễ cho phép
minimumSupport: số cửa sổ, số ngày và mức đa dạng cần thiết
exclusionPolicy: xử lý sự cố, dữ liệu lỗi và hành vi đã xác nhận lạm dụng
~~~

Không đánh đồng nhiều bản ghi với nhiều bằng chứng độc lập. Hàng nghìn cửa sổ trượt chồng lấn có thể cùng chứa một nhóm sự kiện; chúng không tạo mức hỗ trợ giống hàng nghìn quan sát độc lập.

Một lịch sử dài cũng chưa chắc phù hợp nếu sản phẩm vừa thay đổi workflow hoặc cách ghi sự kiện.

### 4.2. Đếm trùng và sự kiện đến muộn phải được xử lý

Sự kiện nghiệp vụ nên có tối thiểu:

~~~text
eventId, operationId
tenantId, actorId
objectId, action, outcome
occurredAt, ingestedAt
sourceVersion, schemaVersion
~~~

- Deduplicate theo định danh phù hợp, không chỉ theo timestamp.
- Xác định cách xử lý sự kiện đến sau khi cửa sổ đã đóng.
- Phân biệt thời điểm xảy ra và thời điểm tiếp nhận.
- Không tin timestamp tùy ý do client gửi.
- Ghi nhận bản chỉnh sửa hoặc version khi kết quả cửa sổ thay đổi.

Nếu dữ liệu lịch sử được sửa, tạo artifact baseline mới hoặc version mới. Không thay âm thầm mẫu số hoặc thống kê của baseline đang phục vụ mà vẫn giữ cùng ID.

### 4.3. Tránh học từ hiện tại và nhìn thấy tương lai

Để chấm một cửa sổ kết thúc tại `t`, baseline tham chiếu không được học từ chính cửa sổ đó hoặc các cửa sổ tương lai.

Một nguyên tắc minh họa:

~~~text
trainingEnd <= observationStart

mọi dữ liệu, nhãn và mapping dùng khi replay
phải có sẵn theo thời điểm mà phép đánh giá giả định
~~~

Có thể thêm khoảng cách an toàn để đợi dữ liệu ổn định hoặc nhãn kiểm tra. Khoảng cách đó cần được ghi trong contract.

Khi backtest, không dùng kết luận điều tra thu được tuần sau như thể hệ thống đã biết tại thời điểm sự kiện. Có thể dùng nhãn về sau để đánh giá chất lượng dự báo, nhưng không đưa chúng vào feature hoặc lựa chọn baseline của lần chấm trong quá khứ.

### 4.4. Dữ liệu được chấp nhận chưa chắc là dữ liệu lành tính

Một thao tác đã commit chỉ chứng minh hệ thống đã chấp nhận nó theo các kiểm soát lúc đó. Nó chưa chứng minh người thực hiện không lạm dụng.

Cần có quy tắc xử lý dữ liệu:

- Hành vi đã xác nhận lạm dụng được loại hoặc gắn cờ theo chính sách có audit.
- Dữ liệu lỗi kỹ thuật được sửa hoặc loại với lý do cụ thể.
- Khoảng sự cố và chiến dịch bất thường được phân loại theo bối cảnh.
- Dữ liệu chưa có kết luận được xử lý theo chính sách rõ ràng, không tự gọi là “trusted”.

Không loại mọi điểm cao chỉ vì mô hình hiện tại cho là bất thường. Cách làm đó có thể tạo vòng lặp tự xác nhận và xóa mất những thay đổi hợp lệ cần được học.

## 5. Chọn mô hình đơn giản nhưng hiểu giới hạn

### 5.1. Một số lựa chọn thường gặp

| Phương pháp | Phù hợp khi | Cần chú ý |
| --- | --- | --- |
| Mean và standard deviation | Dữ liệu tương đối ổn định, phân bố phù hợp | Dễ bị ảnh hưởng bởi các giá trị rất lớn |
| Median và MAD | Cần tham chiếu ít nhạy hơn với đuôi phân bố | MAD có thể bằng 0, nhất là dữ liệu số đếm thưa |
| Quantile thực nghiệm | Muốn so với các phân vị lịch sử | Phân vị cao cần đủ dữ liệu hỗ trợ |
| Mô hình số đếm có ngữ cảnh | Số sự kiện phụ thuộc mức tiếp xúc, thời gian | Phải kiểm tra giả định và chất lượng ước lượng |
| Trung bình thích nghi | Hành vi có thay đổi dần cần theo dõi | Dễ học theo lạm dụng nếu cập nhật không kiểm soát |

Không cần bắt đầu bằng mô hình phức tạp. Một metric có contract rõ và baseline được kiểm soát thường dễ kiểm chứng hơn mô hình mạnh nhưng dữ liệu mơ hồ.

Đừng diễn giải “phân vị 99” là có thể ước lượng tin cậy chỉ từ vài chục mẫu. Phải lưu kích thước mẫu, cách tính quantile và đánh giá độ ổn định theo cohort.

### 5.2. Median và MAD

Với các giá trị lịch sử `x_i`:

~~~text
m   = median(x_i)
MAD = median(|x_i - m|)
~~~

MAD đo độ phân tán quanh median. Nó thường ít bị các giá trị cực đoan chi phối hơn standard deviation, nhưng không biến dữ liệu nhiễm bẩn thành dữ liệu đáng tin cậy. [NIST, Measures of Scale](https://www.itl.nist.gov/div898/handbook/eda/section3/eda356.htm).

Một modified Z-score được biểu diễn:

~~~text
M = 0.6745 × (x - m) / MAD
~~~

NIST trình bày cách đánh dấu các điểm có `|M| > 3.5` như những ngoại lệ tiềm năng trong hướng dẫn về outlier. Đây không phải ngưỡng chặn gian lận phổ quát; cần kiểm tra phân bố và hiệu chỉnh theo dữ liệu nghiệp vụ. [NIST, Detection of Outliers](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm).

Với bài toán chỉ quan tâm số lần sửa tăng cao, chính sách minh họa dùng phía trên:

~~~text
M > threshold => tín hiệu tăng bất thường
~~~

Nếu muốn phát hiện cả mức giảm, cần chính sách hai phía hoặc detector riêng. Không tự coi nhân viên nghỉ phép là một sự cố gian lận vì số lần sửa giảm về 0.

### 5.3. Ví dụ tính tay

Dùng một tập nhỏ để minh họa phép tính:

~~~text
0, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 4

median = 2
MAD    = 1
~~~

Nếu một cửa sổ tương ứng có 8 thay đổi:

~~~text
M = 0.6745 × (8 - 2) / 1
  = 4.047
~~~

Với ngưỡng minh họa 3.5, cửa sổ được đánh dấu để xử lý tiếp theo. Nó chưa chứng minh nhân viên lạm dụng.

Tập 12 giá trị trên phục vụ kiểm tra số học. Nó không tự đáp ứng yêu cầu minimum support của một baseline sản xuất.

### 5.4. MAD bằng 0 không có nghĩa mọi thứ bình thường

Ví dụ:

~~~text
0, 0, 0, 0, 0, 0, 1, 1
~~~

Median và MAD đều bằng 0. Không thể tính modified Z-score bằng phép chia thông thường.

Những cách sai:

- Catch lỗi chia rồi trả điểm 0.
- Gán mọi trường hợp MAD bằng 0 thành “không bất thường”.
- Thêm một epsilon cực nhỏ nhưng không hiệu chỉnh, khiến một thay đổi nhỏ tạo điểm khổng lồ.
- Tự dùng mean của toàn hệ thống mà không ghi nhận fallback.

Các lựa chọn có thể chấp nhận tùy chính sách:

- Chuyển sang baseline cohort đủ hỗ trợ.
- Dùng phương pháp phù hợp với dữ liệu số đếm hoặc ngưỡng tuyệt đối đã hiệu chỉnh.
- Trả `UNSCORABLE_BASELINE` và dùng chính sách xử lý thiếu baseline.
- Kết hợp số đếm với mức tiếp xúc để phân biệt hoạt động hiếm nhưng hợp lệ.

Trong ví dụ mã nguồn ở phần sau, MAD bằng 0 tạo kết quả không chấm được, không tạo một điểm bình thường giả.

## 6. Cold start, drift và hành vi đầu độc baseline

### 6.1. Cold start là thiếu thông tin, không phải rủi ro bằng 0

Actor mới, tenant mới hoặc hành động vừa được ra mắt có thể chưa có lịch sử phù hợp.

Kết quả nên diễn đạt được:

~~~text
status: INSUFFICIENT_BASELINE
reason: INSUFFICIENT_HISTORY
fallbackScope: APPROVED_COHORT hoặc NONE
support: số cửa sổ và số ngày thực tế
~~~

Một chính sách có thể áp dụng giới hạn ban đầu, xác minh bổ sung hoặc review cho hành động nhạy cảm. Cần tránh vừa coi mọi người mới là gian lận, vừa cho mọi người mới quyền vượt kiểm soát vì không có dữ liệu.

Khi chuyển từ cohort sang baseline cá nhân, ghi lại version và đánh giá ảnh hưởng. Không đổi cách chấm liên tục ở mỗi request mà thiếu dấu vết.

### 6.2. Concept drift cần được xác nhận bằng ngữ cảnh

Nhịp hành vi có thể thay đổi vì:

- Nhân viên được chuyển nhóm hoặc nhận thêm nhiệm vụ.
- Một workflow mới giảm hoặc tăng số thao tác cần thực hiện.
- Chiến dịch kinh doanh làm tăng khối lượng.
- Hệ thống khác bị lỗi tạo tồn đọng.
- Kẻ lạm dụng tăng dần hoạt động để kéo baseline đi lên.

Theo dõi thay đổi phân bố và chất lượng dữ liệu giúp nhận ra drift. Nhưng drift không tự cho biết nguyên nhân là hợp lệ hay độc hại.

Khi có thay đổi nghiệp vụ được xác nhận, có thể tạo cohort mới, metric version mới hoặc baseline mới. Không đơn giản tắt detector vô thời hạn cho mọi đối tượng.

### 6.3. Chấm trước, học sau và có kiểm soát

Một quy trình nguy hiểm:

~~~text
nhận x hiện tại
cập nhật baseline bằng x
so sánh x với baseline vừa cập nhật
~~~

Giá trị bất thường có thể kéo mức tham chiếu về phía chính nó.

Quy trình nên tách:

~~~text
chấm bằng baseline bất biến đã được chọn
ghi quyết định và dữ liệu quan sát
phân loại chất lượng, bối cảnh và kết quả kiểm tra
chỉ đưa dữ liệu đủ điều kiện vào phiên xây dựng tiếp theo
~~~

Nếu dùng mô hình thích nghi, cần giới hạn tốc độ cập nhật, ảnh hưởng của một actor và điều kiện tiếp nhận mẫu. Dữ liệu bị cách ly không được âm thầm quay lại chỉ vì đã cũ hơn một số ngày.

Median/MAD không chống được mọi kiểu poisoning. Nếu phần lớn dữ liệu bị chi phối bởi một nguồn lạm dụng hoặc cohort đã chọn sai, thống kê robust cũng có thể tạo tham chiếu sai.

### 6.4. Chống tạo nhiều danh tính và chia nhỏ hành vi

Chỉ dùng baseline cá nhân có thể bỏ sót hành vi phân tán:

- Mỗi tài khoản thực hiện ít thao tác.
- Nhiều tài khoản cùng nhắm một nhóm đối tượng.
- Nhân viên chia hoạt động giữa nhiều tài khoản.
- Một actor tăng dần nhưng giữ mỗi cửa sổ dưới ngưỡng.

Có thể bổ sung tham chiếu theo tenant, đối tượng, loại tài nguyên hoặc liên hệ được hệ thống xác thực. Các tín hiệu liên kết phải có chất lượng và ngữ cảnh; không coi IP dùng chung là bằng chứng chắc chắn nhiều tài khoản thuộc cùng một người.

Các giới hạn tuyệt đối và bất biến vẫn cần độc lập. Một baseline thích nghi không được tự nâng hạn mức cấp ưu đãi hoặc quyền phê duyệt.

## 7. Vòng đời và version của baseline

### 7.1. Baseline là một artifact có contract

Một bản ghi có thể gồm:

~~~text
baselineId, baselineVersion, status
tenantId, baselineScope, cohortDefinitionVersion
metricName, metricVersion, windowSpecVersion
timeContext, timezone
trainingStart, trainingEnd
builtAt, validatedAt, validFrom, validUntil
sampleCount, distinctDays, contributingActors
coverageSummary, exclusionPolicyVersion
estimatorType, estimatorParameters
center, scale, quantiles nếu có
trainingDataReference, artifactDigest
~~~

Tách các tham số mô tả dữ liệu khỏi chính sách phản ứng. Ví dụ, baseline lưu median và MAD; policy version quyết định mức điểm nào cần review trong ngữ cảnh đó.

Không đổi nội dung baseline đã sử dụng mà giữ nguyên ID và version. Nếu cần tái lập một quyết định, phải biết chính artifact nào đã được dùng.

### 7.2. State machine cho phát hành

~~~mermaid
stateDiagram-v2
    [*] --> CANDIDATE
    CANDIDATE --> VALIDATED: Kiểm tra dữ liệu và tiêu chí hỗ trợ
    VALIDATED --> SHADOW: Chấm thử không tác động nghiệp vụ
    SHADOW --> ACTIVE: Được phê duyệt phát hành
    CANDIDATE --> REJECTED: Không đạt điều kiện
    VALIDATED --> REJECTED: Phát hiện lỗi hoặc không phù hợp
    SHADOW --> REJECTED: Kết quả không đạt
    ACTIVE --> SUSPENDED: Dữ liệu hoặc artifact có vấn đề
    ACTIVE --> RETIRED: Có bản thay thế hoặc hết vòng đời
    SUSPENDED --> RETIRED: Kết thúc sử dụng bản cũ
~~~

Hết `validUntil` phải làm baseline ngừng được dùng cho chấm mới theo contract, dù job cập nhật trạng thái chưa chạy.

Khi thay baseline, cập nhật tham chiếu đang phục vụ một cách nguyên tử. Một lần chấm ghim một version; không lấy median từ bản cũ và MAD từ bản mới.

Việc replay quyết định cũ dùng đường riêng có kiểm soát và artifact lịch sử. Nó không chứng minh artifact đã retire được dùng cho quyết định mới.

### 7.3. Shadow và kiểm tra trước phát hành

Đánh giá ít nhất:

- Mức hỗ trợ theo từng cohort, không chỉ tổng số mẫu.
- Tỷ lệ không chấm được và fallback.
- Tỷ lệ cảnh báo theo vai trò, ca, tenant và mức tiếp xúc.
- Các tình huống vận hành hợp lệ từng tạo đột biến.
- Các tình huống lạm dụng đã biết hoặc được mô phỏng.
- Khả năng tái lập điểm và giải thích.
- Độ nhạy khi có mất dữ liệu, duplicate và sự kiện đến muộn.

Shadow không được sửa quyền, phát challenge thật, tạo nghiệp vụ bồi hoàn hay tăng lại bộ đếm. Nó chỉ đánh giá và ghi nhận theo quyền truy cập được cấp.

## 8. Ví dụ Java: không chấm điểm khi điều kiện tham chiếu không đủ

Đoạn mã sau minh họa chấm cửa sổ đã đóng, dùng modified Z-score phía trên. Nó không phải hệ thống anomaly detection hoàn chỉnh.

Giả định selector đã kiểm tra đúng tenant, actor hoặc cohort, metric, phiên bản cửa sổ và artifact được phép phục vụ. Các kiểu và import được rút gọn.

~~~java
enum DataQuality {
    COMPLETE, PARTIAL, MISSING
}

enum ScoreStatus {
    WITHIN_BASELINE,
    ANOMALOUS_HIGH,
    INSUFFICIENT_BASELINE,
    INVALID_OBSERVATION,
    INCOMPATIBLE_BASELINE,
    UNSCORABLE_BASELINE
}

record Observation(
        long value,
        Instant windowStart,
        Instant windowEnd,
        DataQuality quality) {}

record Baseline(
        String id,
        Instant trainingEnd,
        Instant validFrom,
        Instant validUntil,
        long sampleCount,
        int distinctDays,
        double median,
        double mad) {}

record ScorePolicy(
        long minimumWindows,
        int minimumDays,
        double upperThreshold) {}

record ScoreResult(
        ScoreStatus status,
        Double score,
        String baselineId,
        String reasonCode) {}

ScoreResult score(
        Observation observation,
        Baseline baseline,
        ScorePolicy policy,
        Instant evaluatedAt) {

    if (observation.quality() != DataQuality.COMPLETE
            || observation.value() < 0
            || !observation.windowStart().isBefore(observation.windowEnd())
            || evaluatedAt.isBefore(observation.windowEnd())) {
        return new ScoreResult(
                ScoreStatus.INVALID_OBSERVATION,
                null, null, "OBSERVATION_NOT_READY");
    }

    if (baseline == null
            || baseline.sampleCount() < policy.minimumWindows()
            || baseline.distinctDays() < policy.minimumDays()) {
        return new ScoreResult(
                ScoreStatus.INSUFFICIENT_BASELINE,
                null,
                baseline == null ? null : baseline.id(),
                "INSUFFICIENT_SUPPORT");
    }

    if (baseline.trainingEnd().isAfter(observation.windowStart())
            || evaluatedAt.isBefore(baseline.validFrom())
            || !evaluatedAt.isBefore(baseline.validUntil())) {
        return new ScoreResult(
                ScoreStatus.INCOMPATIBLE_BASELINE,
                null, baseline.id(), "BASELINE_TIME_CONTRACT_MISMATCH");
    }

    if (!Double.isFinite(baseline.median())
            || baseline.median() < 0
            || !Double.isFinite(baseline.mad())
            || baseline.mad() <= 0) {
        return new ScoreResult(
                ScoreStatus.UNSCORABLE_BASELINE,
                null, baseline.id(), "INVALID_OR_ZERO_SCALE");
    }

    double modifiedZ =
            0.6745 * (observation.value() - baseline.median())
            / baseline.mad();

    if (!Double.isFinite(modifiedZ)) {
        return new ScoreResult(
                ScoreStatus.UNSCORABLE_BASELINE,
                null, baseline.id(), "NON_FINITE_SCORE");
    }

    return new ScoreResult(
            modifiedZ > policy.upperThreshold()
                    ? ScoreStatus.ANOMALOUS_HIGH
                    : ScoreStatus.WITHIN_BASELINE,
            modifiedZ,
            baseline.id(),
            "UPPER_TAIL_COMPARISON");
}
~~~

Các điểm cần giữ khi hiện thực:

- `score = null` biểu diễn không có điểm, khác với điểm 0.
- `WITHIN_BASELINE` chỉ có nghĩa không vượt ngưỡng phía trên đã chọn.
- Các giá trị policy phải được kiểm tra trước: minimum support dương, threshold hữu hạn và phù hợp.
- Metadata, timestamp và schema cần được kiểm tra đầy đủ khi nạp artifact.
- Cửa sổ đúng 30 phút, quy tắc alignment và scope phải được selector xác minh; hàm trên chỉ minh họa một phần kiểm tra.
- Dùng nguồn thời gian backend đáng tin cậy và ghim artifact cho cả lần chấm.
- Không catch lỗi rồi trả `WITHIN_BASELINE`.

`double` ở đây phục vụ thống kê số đếm. Nếu bổ sung feature tiền, không dùng nó thay cho biểu diễn tiền chính xác trong các kiểm tra giá, số dư hoặc transaction.

## 9. Đưa tín hiệu baseline vào quyết định nghiệp vụ

### 9.1. Tách quan sát, điểm và hành động

Một kết quả phân tích có thể gồm:

~~~text
observationId, observationVersion
tenantId, entityId, action
metricName, metricVersion
windowStart, windowEnd
dataQuality
baselineId, baselineVersion, baselineScope
supportSummary
scoreStatus, score, direction
policyVersion, evaluatedAt
reasonCodes
~~~

Kết quả này mô tả một quan sát trong quá khứ. Nếu dùng nó để điều chỉnh xử lý một yêu cầu mới, cần tạo quyết định nghiệp vụ riêng gắn với yêu cầu mới đó.

Ví dụ chính sách có thể quy định: sau một cửa sổ tăng bất thường đã được xác nhận đủ chất lượng, các yêu cầu sửa địa chỉ tiếp theo của actor phải qua xác minh hoặc review trong một khoảng hữu hạn.

Quyết định cho yêu cầu mới cần gắn với:

~~~text
tenantId + actorId + objectId + action
operationId + requestFingerprint
objectVersion
observationReference + baselineVersion
requiredObligations
validUntil
~~~

Không coi điểm của cửa sổ vừa đóng là bằng chứng đã đánh giá chính xác mọi chi tiết của yêu cầu mới.

### 9.2. Một bảng phản ứng minh họa

| Tình huống | Phản ứng có thể chọn |
| --- | --- |
| Trong baseline, quyền và bất biến đều đúng | Tiếp tục luồng nghiệp vụ bình thường |
| Tăng bất thường, dữ liệu đầy đủ, chưa có bằng chứng khác | Ghi nhận, bổ sung ngữ cảnh hoặc review theo mức nhạy cảm |
| Bất thường đi kèm vi phạm quyền hay trạng thái bắt buộc | Chặn vì điều kiện bắt buộc bị vi phạm |
| Không đủ baseline cá nhân nhưng cohort phù hợp | Chấm bằng fallback, ghi rõ phạm vi và hỗ trợ |
| Không có baseline hoặc dữ liệu không đầy đủ | Dùng chính sách thiếu dữ liệu, không giả điểm an toàn |
| Sự kiện vận hành hợp lệ đã được phê duyệt | Dùng ngữ cảnh hoặc phiên chính sách riêng có hạn, vẫn giữ bất biến |

Một điểm không vượt ngưỡng không được đặt lại trạng thái `REVIEW_REQUIRED` do một nguồn khác tạo ra. Phải có quy tắc hợp nhất các quyết định và nghĩa vụ.

Tương tự, tín hiệu bất thường không tự cấp quyền cho nhân viên điều tra đọc tất cả dữ liệu tenant. Quyền quan sát và quyền phản ứng cũng cần được giới hạn.

### 9.3. State machine giữ các bước review và xác minh

Một luồng xử lý yêu cầu mới có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> CONTEXT_CHECKED: Kiểm tra quyền và bất biến
    CONTEXT_CHECKED --> READY: Chính sách không yêu cầu bước bổ sung
    CONTEXT_CHECKED --> REVIEW_REQUIRED: Có nghĩa vụ xem xét
    CONTEXT_CHECKED --> VERIFICATION_REQUIRED: Có nghĩa vụ xác minh
    CONTEXT_CHECKED --> DATA_UNAVAILABLE: Không đủ dữ liệu cần thiết
    REVIEW_REQUIRED --> READY: Kết quả xem xét hợp lệ
    VERIFICATION_REQUIRED --> READY: Bằng chứng đúng scope
    DATA_UNAVAILABLE --> CONTEXT_CHECKED: Đánh giá lại có kiểm soát
    READY --> CONTEXT_CHECKED: Dữ liệu liên quan đổi hoặc quyết định hết hạn
    READY --> EXECUTING: Chấp nhận thao tác nguyên tử
    EXECUTING --> COMPLETED: Thành công
~~~

Các chuyển tiếp sang READY chỉ thỏa nghĩa vụ tương ứng. Cổng thực thi vẫn kiểm tra scope, thời hạn, quyền hiện tại và trạng thái đối tượng.

Không cho client gửi `baselineNormal = true` hoặc `reviewDone = true` để chuyển trạng thái. Kết quả review và xác minh phải là bằng chứng server có thể đối chiếu.

Một yêu cầu chờ review cần deadline và đường xử lý kết thúc. Không để trạng thái chờ tồn tại vô hạn hoặc tự chuyển thành READY chỉ vì quá lâu chưa có người xem.

### 9.4. Transaction và idempotency vẫn bảo vệ hiệu ứng thật

Với thay đổi địa chỉ:

1. Xác thực và kiểm tra quyền trên đơn.
2. Xử lý khóa idempotency theo tenant, actor và hành động.
3. Đọc hoặc khóa đơn và quyết định cần dùng theo mô hình cạnh tranh đã chọn.
4. Kiểm tra đơn chưa bàn giao, phiên bản còn đúng và nghĩa vụ đã hoàn tất.
5. Cập nhật địa chỉ và trạng thái thao tác.
6. Ghi sự kiện nghiệp vụ và outbox trong cùng transaction.
7. Commit.

Event consumer xây cửa sổ quan sát từ sự kiện đã commit, với deduplication phù hợp. Việc giao outbox nhiều lần không được biến một thay đổi thành nhiều lần trong baseline.

Một khóa deduplication có thể dựa trên `tenantId + operationId + action + effectType` theo contract. Chỉ dựa vào event ID là chưa đủ nếu nguồn có thể tạo nhiều event ID cho cùng một hiệu ứng.

Một kết quả “trong baseline” không giải quyết việc hai request cạnh tranh cùng sửa đơn hoặc dùng một quyền một lần. Vẫn cần khóa, version có điều kiện, unique constraint hoặc cơ chế nguyên tử thích hợp.

Nếu hiệu ứng được giao sang hệ thống ngoài, transaction nội bộ không làm nó nguyên tử với hệ thống đích. Dùng idempotency hoặc đối soát theo contract của kênh đó.

### 9.5. Phát hiện muộn không tự hoàn tác

Với detector cửa sổ đã đóng, khi một cửa sổ bị đánh dấu, các thay đổi bên trong có thể đã hoàn tất.

Phản ứng có thể là kiểm tra các operation liên quan, thu hồi quyền cho thao tác tương lai theo thẩm quyền, yêu cầu review hoặc khởi tạo quy trình khắc phục. Không giả định đánh dấu bất thường sẽ rollback được giao dịch đã commit.

Hoàn tác, nếu được nghiệp vụ cho phép, là hành động mới với quyền và kiểm tra hiện tại. Ví dụ đơn đã được giao vận có thể không còn cho phép sửa về địa chỉ trước đó bằng cùng một API.

## 10. Kiểm thử đường cơ sở bằng tình huống nghiệp vụ

### 10.1. Kiểm thử phép tính và điều kiện đủ

Với baseline minh họa có median 2, MAD 1 và ngưỡng phía trên 3.5:

| Quan sát hoặc điều kiện | Kết quả mong đợi |
| --- | --- |
| x = 2, dữ liệu và hỗ trợ đầy đủ | Điểm 0, không vượt ngưỡng phía trên |
| x = 8, cùng ngữ cảnh | Điểm 4.047, tín hiệu tăng bất thường |
| Điểm đúng bằng threshold | Không vượt nếu contract chọn điều kiện `>` |
| MAD = 0 | Không chấm được bằng công thức này; áp dụng fallback |
| Thiếu baseline hoặc chưa đủ ngày hỗ trợ | INSUFFICIENT_BASELINE |
| Cửa sổ chưa kết thúc | Không được coi là quan sát hoàn chỉnh |
| Dữ liệu PARTIAL hoặc MISSING | Không chấm như số 0 |
| `evaluatedAt = validUntil` | Baseline không còn hợp lệ cho chấm mới |
| Training bao gồm chính cửa sổ cần chấm | Bị chặn vì rò rỉ dữ liệu |
| Baseline khác metric version hoặc scope | Không được chọn làm tham chiếu |

Đối với hàm chấm, dùng các thời điểm cố định hoặc inject clock. Không chờ thật 30 phút để kiểm thử một cửa sổ.

### 10.2. Ma trận lạm dụng và sai lệch dữ liệu

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Retry thao tác đã commit | Chỉ một hiệu ứng và một lần đếm nghiệp vụ |
| Consumer nhận cùng event nhiều lần | Không tăng số đếm trùng |
| Hai event ID khác nhau cùng chỉ một hiệu ứng | Xử lý theo khóa nghiệp vụ đã định nghĩa |
| Sự kiện đến sau khi cửa sổ đã đóng | Có quy tắc version hoặc hiệu chỉnh; không sửa baseline âm thầm |
| Client tự khai timestamp, role hoặc tenant | Không đổi ngữ cảnh tin cậy |
| Nhân viên chọn baseline của nhóm khác | Selector từ chối |
| Pipeline mất dữ liệu một khoảng | Không tạo các cửa sổ 0 giả |
| Không có sự kiện nhưng pipeline hoạt động đầy đủ | Tạo 0 nếu cửa sổ đủ điều kiện |
| Nhân viên ngoài ca hoặc không được giao việc | Không nhập nhằng với hành vi ít hoạt động trong ca |
| Mẫu số tỷ lệ bằng 0 hoặc rất nhỏ | Không tạo tỷ lệ an toàn giả; giữ thông tin hỗ trợ |
| Cửa sổ đang chạy được so với baseline cửa sổ đầy đủ | Bị phát hiện không tương thích |
| Baseline đang phục vụ được thay giữa lúc chấm | Một lần chấm dùng một version nhất quán |
| Actor tạo nhiều hoạt động để đẩy baseline lên | Không tự tiếp nhận tất cả vào tham chiếu đang dùng |
| Nhiều actor chia nhỏ hành vi trên cùng tài nguyên | Có kiểm thử các chiều tham chiếu và giới hạn bổ sung |
| Vai trò hoặc workflow đổi | Cohort và schema không tái diễn giải lịch sử sai |
| Backtest dùng nhãn có sau thời điểm chấm | Không đưa nhãn tương lai vào feature hoặc chọn baseline |
| Nới baseline nhưng đối tượng đã sai quyền | Authorization vẫn chặn |
| Hai request đồng thời đều có điểm thấp | Bất biến và idempotency vẫn được giữ |
| Quyết định review cũ được dùng cho payload mới | Binding hoặc object version làm nó mất hiệu lực |
| Shadow được chạy lại nhiều lần | Không tạo hiệu ứng hay cập nhật dữ liệu nguồn thật |

### 10.3. Kiểm thử theo thời gian thay vì trộn ngẫu nhiên mọi mẫu

Một cách đánh giá có thể là:

~~~text
giai đoạn A: xây baseline
giai đoạn B: chọn hoặc hiệu chỉnh chính sách
giai đoạn C: kiểm tra trên dữ liệu thời gian về sau
~~~

Khi tiến dần thời gian, mỗi phiên chỉ sử dụng dữ liệu đã có ở thời điểm tương ứng. Không đưa các cửa sổ trùng hoặc chồng lấn mạnh vào cả tập xây baseline và tập đánh giá rồi xem đó là bằng chứng độc lập.

Giữ riêng các giai đoạn có thay đổi sản phẩm, sự cố và chiến dịch để thấy detector hoạt động ra sao trong từng bối cảnh. Một số trung bình toàn hệ thống có thể che mất việc một cohort nhỏ bị cảnh báo liên tục.

### 10.4. Một số thuộc tính cần giữ

~~~text
Một hiệu ứng nghiệp vụ không bị đếm nhiều lần vì retry.

Dữ liệu thiếu không tạo kết quả WITHIN_BASELINE giả.

Một lần chấm chỉ dùng một artifact và một metric contract.

Dữ liệu tương lai không tác động tới lần chấm quá khứ
trong mô phỏng điều kiện thời điểm đó.

Tín hiệu bất thường không mở rộng quyền.

Tín hiệu bình thường không xóa bất biến bắt buộc.

Replay cùng snapshot, baseline và policy
tạo cùng kết quả theo ngữ nghĩa đã công bố.
~~~

Các thuộc tính này kiểm tra giá trị nghiệp vụ của detector, không chỉ kiểm tra một hàm tính median.

## 11. Quan sát vận hành và bảo vệ dữ liệu baseline

### 11.1. Theo dõi chất lượng trước khi tin điểm

Các nhóm chỉ số hữu ích:

| Nhóm | Ví dụ |
| --- | --- |
| Coverage | Tỷ lệ cửa sổ đầy đủ, thiếu, đến muộn, không đủ điều kiện |
| Hỗ trợ baseline | Số cửa sổ, số ngày, số actor, tỷ lệ fallback |
| Hiệu lực artifact | Hết hạn, suspended, sai schema, version đang dùng |
| Phân bố tín hiệu | Theo cohort, ca, mức tiếp xúc và phiên chính sách |
| Drift | Thay đổi trung tâm, độ phân tán và tỷ lệ không tương thích |
| Tác động nghiệp vụ | Số review, thời gian xử lý, gián đoạn thao tác hợp lệ |
| Kết quả kiểm tra | Bất thường hợp lệ, lỗi dữ liệu, lạm dụng được xác nhận |

Một baseline đột nhiên ít cảnh báo hơn có thể do hành vi ổn định, nhưng cũng có thể do mất dữ liệu, đổi cohort hoặc ngưỡng bị nâng sai. Quan sát cả dữ liệu đầu vào và kết quả.

Không xem mọi cảnh báo là true positive, cũng không xem mọi giao dịch được thực hiện là dữ liệu lành tính. Cần quy trình phản hồi có nhãn và thời điểm kết luận.

### 11.2. Baseline có thể tiết lộ thông tin nhạy cảm

Thống kê hành vi có thể suy ra lịch làm việc, khối lượng xử lý và quan hệ với đối tượng nghiệp vụ.

Áp dụng:

- Quyền đọc theo vai trò và tenant.
- Tối thiểu hóa dữ liệu cá nhân trong artifact, trace và log.
- Hạn lưu phù hợp cho sự kiện, cửa sổ và thống kê tổng hợp.
- Tách quyền xây baseline với quyền thay chính sách phản ứng.
- Kiểm toán việc sửa dữ liệu huấn luyện, exclusions và cohort mapping.
- Bảo vệ tham chiếu dữ liệu để người xem điểm không tự truy cập mọi sự kiện gốc.

Không đưa ID cá nhân hoặc object ID có độ đa dạng cao vào metric label công khai. Hash định danh đơn thuần không làm dữ liệu tự trở thành vô danh.

### 11.3. Xử lý khi baseline không còn đáng tin

Khi phát hiện nguồn dữ liệu lỗi hoặc nghi ngờ poisoning:

1. Ngừng tiếp nhận dữ liệu liên quan vào vòng xây baseline tiếp theo.
2. Đánh dấu artifact bị ảnh hưởng và ngừng dùng theo chính sách.
3. Chuyển sang fallback đã được phê duyệt hoặc trạng thái không đủ baseline.
4. Giữ các kiểm soát quyền, trạng thái và hạn mức bắt buộc.
5. Điều tra các observation và quyết định chịu ảnh hưởng.
6. Xây artifact mới, chạy shadow và xác minh trước khi phát hành.

Không xóa dấu vết rồi xây lại một bản có cùng ID. Cũng không tự cho tất cả thao tác qua chỉ vì detector đang tạm ngừng.

Cần thông báo nội bộ rõ phần nào là lỗi dữ liệu, phần nào là phát hiện hành vi và phần nào đã tác động tới quyết định nghiệp vụ. Điều đó giúp tránh xử lý một nhân viên như đã vi phạm chỉ vì pipeline bị lỗi.

## 12. Những quyết định cần chốt trước khi sử dụng baseline

Một thiết kế có thể kiểm chứng phải trả lời được:

1. Đang mô tả hành vi nào, đơn vị đếm nào và cửa sổ nào?
2. Dữ liệu nào chứng minh một cửa sổ được quan sát đầy đủ?
3. Actor được so với chính mình hay cohort nào, theo phiên định nghĩa nào?
4. Dữ liệu lịch sử đủ hỗ trợ chưa và có dùng thông tin tương lai không?
5. Khi MAD bằng 0, cold start hoặc drift xuất hiện thì kết quả là gì?
6. Dữ liệu hiện tại được chấm trước khi đưa vào vòng học tiếp theo như thế nào?
7. Tín hiệu được dùng sau sự kiện hay tại cổng quyết định cho thao tác mới?
8. Transaction, idempotency và quyền theo đối tượng bảo vệ hiệu ứng thật ở đâu?
9. Có thể giải thích và replay kết quả bằng đúng artifact đã dùng không?

Đường cơ sở tốt mô tả hành vi trong đúng bối cảnh và biểu đạt trung thực mức thông tin hệ thống đang có. Nó hỗ trợ phát hiện lạm dụng khi được kết hợp với các quy tắc nghiệp vụ có thể cưỡng chế, thay vì biến lịch sử quan sát thành một nguồn cấp quyền.
