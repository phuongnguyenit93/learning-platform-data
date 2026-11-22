# Sensitive Data Protection và nhận diện dữ liệu nhạy cảm

Trong một hệ thống Google Cloud, dữ liệu nhạy cảm có thể nằm rải rác trong bảng BigQuery, cơ sở dữ liệu Cloud SQL, tệp Cloud Storage, nội dung do người dùng gửi lên hoặc payload đi qua API. Một phần dữ liệu đã được phân loại và quản lý, nhưng cũng có thể tồn tại bản sao thử nghiệm, bảng tạm, log hoặc dữ liệu được chia sẻ rộng hơn dự kiến. Nếu tổ chức không biết dữ liệu nhạy cảm đang nằm ở đâu và xuất hiện dưới dạng nào, việc đặt quyền truy cập, mã hóa, lưu giữ và xử lý sự cố sẽ thiếu căn cứ.

**Sensitive Data Protection** là bộ dịch vụ của Google Cloud giúp khám phá, phân loại, kiểm tra và loại bỏ hoặc biến đổi dữ liệu nhạy cảm. Sản phẩm trước đây thường được gọi là Cloud Data Loss Prevention (Cloud DLP); tên Cloud Data Loss Prevention vẫn xuất hiện trong tên API, thư viện và một số tài liệu kỹ thuật. Bài học này tập trung vào cách nhận diện dữ liệu, đọc kết quả quét và chọn cách bảo vệ phù hợp.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận biết dữ liệu định danh trực tiếp, dữ liệu định danh gián tiếp và thông tin bí mật cần bảo vệ.
- Phân biệt discovery, inspection, de-identification và risk analysis trong Sensitive Data Protection.
- Chọn built-in hoặc custom infoType detector, đọc mức likelihood và tinh chỉnh kết quả.
- Thiết kế quy trình quét dữ liệu có phạm vi, lịch chạy và nơi lưu kết quả phù hợp.
- Chọn phép biến đổi dữ liệu để cân bằng giữa bảo mật và khả năng phân tích.
- Đánh giá rủi ro tái nhận dạng và bảo vệ findings bằng IAM, logging và kiểm soát dữ liệu.

## 1. Dữ liệu nhạy cảm là gì?

Dữ liệu nhạy cảm là thông tin mà việc tiết lộ, sửa đổi hoặc sử dụng sai mục đích có thể gây tổn hại cho cá nhân, tổ chức hoặc khách hàng. Mức độ nhạy cảm phụ thuộc vào nội dung, bối cảnh, nghĩa vụ pháp lý và chính sách của tổ chức.

Một số nhóm thường gặp:

| Nhóm dữ liệu | Ví dụ | Rủi ro khi lộ |
|---|---|---|
| Thông tin định danh cá nhân (PII) | Họ tên, email, số điện thoại, địa chỉ, mã định danh | Mạo danh, lừa đảo, xâm phạm quyền riêng tư |
| Dữ liệu sức khỏe (PHI) | Hồ sơ khám bệnh, chẩn đoán, kết quả xét nghiệm | Tiết lộ thông tin sức khỏe, vi phạm nghĩa vụ bảo mật |
| Dữ liệu tài chính | Số thẻ thanh toán, tài khoản, mã giao dịch gắn với cá nhân | Gian lận, chiếm đoạt tài sản |
| Thông tin xác thực và bí mật | API key, access token, mật khẩu, private key | Chiếm quyền truy cập, di chuyển ngang trong hệ thống |
| Thông tin kinh doanh mật | Giá hợp đồng, kế hoạch sản phẩm, dữ liệu khách hàng chưa công bố | Thiệt hại thương mại và uy tín |

Cần phân biệt hai khái niệm:

- **Định danh trực tiếp:** một giá trị có thể chỉ ra cá nhân hoặc tài khoản, chẳng hạn email, số điện thoại hoặc mã khách hàng có thể tra ngược.
- **Định danh gián tiếp (quasi-identifier):** một thuộc tính riêng lẻ có thể không xác định một người, nhưng khi kết hợp với thuộc tính khác có thể thu hẹp nhóm xuống một người. Ví dụ ngày sinh, mã bưu chính và giới tính có thể giúp tái nhận dạng một bản ghi.

Việc xóa tên hoặc email không bảo đảm dữ liệu đã ẩn danh. Một tập dữ liệu vẫn có thể tiết lộ danh tính khi kết hợp các thuộc tính gián tiếp với dữ liệu công khai hoặc dữ liệu từ hệ thống khác.

## 2. Sensitive Data Protection làm gì?

Sensitive Data Protection cung cấp các khả năng liên quan nhưng có mục đích khác nhau:

| Khả năng | Câu hỏi cần trả lời | Kết quả chính |
|---|---|---|
| Discovery (khám phá) | Dữ liệu nhạy cảm đang nằm ở đâu và tài sản nào có rủi ro cao? | Data profiles ở mức tài sản, bảng hoặc cột |
| Inspection (kiểm tra chi tiết) | Có những giá trị nhạy cảm nào trong một tài nguyên cụ thể? | Findings kèm loại dữ liệu, vị trí và likelihood |
| De-identification (khử định danh) | Làm thế nào để giảm khả năng nhận diện nhưng vẫn giữ ích lợi dữ liệu? | Nội dung đã che, thay thế, tổng quát hóa hoặc token hóa |
| Risk analysis (phân tích rủi ro) | Sau khi biến đổi, dữ liệu còn dễ bị tái nhận dạng đến mức nào? | Các chỉ số như k-anonymity và l-diversity |

Các khả năng này thường được kết hợp thành một quy trình. Discovery giúp tìm khu vực cần ưu tiên; inspection cung cấp bằng chứng chi tiết; de-identification tạo bản dữ liệu phù hợp để chia sẻ hoặc phân tích; risk analysis đánh giá phần rủi ro còn lại.

Sensitive Data Protection không tự động biến mọi tài nguyên thành an toàn chỉ vì đã bật API hoặc chạy một lần quét. Tổ chức vẫn cần quyết định cách xử lý findings, thiết lập IAM, giới hạn truy cập, mã hóa, lưu giữ và giám sát dữ liệu.

## 3. Discovery: lập bản đồ dữ liệu nhạy cảm

Discovery liên tục hoặc theo lịch tạo **data profile** cho các tài nguyên nằm trong phạm vi scan configuration. Có thể cấu hình phạm vi ở cấp organization, folder hoặc project tùy loại dữ liệu và mô hình đăng ký dịch vụ.

Các nguồn dữ liệu được hỗ trợ cho discovery gồm những tài sản như BigQuery, Cloud SQL, Cloud Storage và Vertex AI; dịch vụ cũng có khả năng discovery cho một số nguồn bên ngoài Google Cloud như Amazon S3 và Azure Blob Storage. Một nhánh secrets discovery tập trung tìm bí mật bị lộ trong các vị trí được hỗ trợ, chẳng hạn biến môi trường của workload.

### Data profile chứa gì?

Tùy loại tài nguyên, profile có thể cung cấp:

- Các infoType được dự đoán trong dữ liệu, chẳng hạn email hoặc số thẻ thanh toán.
- Mức độ nhạy cảm và mức rủi ro dữ liệu.
- Kích thước, hình dạng dữ liệu, tỷ lệ giá trị rỗng và độ duy nhất ước tính.
- Metadata và tín hiệu bảo mật của tài nguyên, ví dụ trạng thái mã hóa hoặc việc chia sẻ công khai khi có hỗ trợ.
- Thời điểm profile được tạo gần nhất và các chỉ số phục vụ theo dõi thay đổi.

Với BigQuery hoặc Cloud SQL, profile có thể được tạo ở nhiều cấp như project, table và column. Nhờ vậy, đội bảo mật có thể xác định bảng nào chứa nhiều dữ liệu nhạy cảm, cột nào có giá trị định danh duy nhất cao hoặc tài sản nào cần được rà soát quyền truy cập trước.

Data profile là kết quả phân loại và thống kê ở mức tổng quan. Nó không phải danh sách đầy đủ từng giá trị nhạy cảm trong bảng. Nếu cần biết chính xác vị trí của từng số điện thoại hoặc email, hãy chạy inspection trên tài nguyên phù hợp.

### Cấu hình discovery

Một scan configuration thường xác định:

1. Phạm vi tài nguyên cần profile.
2. Các nguồn dữ liệu và loại tài sản được đưa vào phạm vi.
3. Cấu hình phát hiện hoặc inspection template liên quan.
4. Tần suất profile và hành vi khi phát hiện thay đổi.
5. Các hành động sau khi tạo profile, chẳng hạn lưu bản sao kết quả, gửi Pub/Sub hoặc đưa insight sang dịch vụ bảo mật khác.

Discovery xử lý dữ liệu tại nơi dữ liệu đang lưu và lưu metadata profile theo vùng hoặc multi-region tương ứng với tài nguyên được profile, theo mô hình hỗ trợ của dịch vụ. Khi thiết kế, vẫn phải kiểm tra location, data residency và các tùy chọn endpoint phù hợp với yêu cầu tổ chức.

### Khi nào bắt đầu bằng discovery?

Hãy dùng discovery khi tổ chức chưa có bản đồ dữ liệu đầy đủ, có nhiều project hoặc nhiều nhóm tạo tài nguyên, hoặc muốn theo dõi dữ liệu mới xuất hiện theo thời gian. Đây là cách phù hợp để tìm shadow data: bảng thử nghiệm, bucket cũ, bản sao dữ liệu hoặc tài nguyên chưa được đưa vào quy trình quản trị thông thường.

## 4. Inspection: tìm từng vị trí chứa dữ liệu nhạy cảm

Inspection thực hiện quét chi tiết một tài nguyên hoặc payload để tạo **finding** cho các nội dung khớp với cấu hình phát hiện. Một finding có thể chứa:

- **infoType:** loại dữ liệu được phát hiện.
- **likelihood:** mức độ chắc chắn rằng nội dung khớp với infoType.
- **location:** vị trí của nội dung trong văn bản, trường, hàng hoặc tệp.
- **quote:** đoạn giá trị được phát hiện, nếu cấu hình cho phép trả về.

Quote có thể chứa chính dữ liệu nhạy cảm. Trong môi trường production, chỉ bật lưu quote khi có nhu cầu rõ ràng và đã bảo vệ nơi lưu kết quả.

Có ba cách gọi inspection thường gặp:

| Cách thực hiện | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| Inspection job | Tạo job bất đồng bộ để quét một tài nguyên được hỗ trợ | Quét bảng BigQuery, bucket Cloud Storage hoặc Datastore kind |
| Hybrid inspection job | Gửi payload từ nguồn bất kỳ vào job để kiểm tra và lưu findings | Tích hợp dữ liệu từ ứng dụng, hệ thống ngoài Google Cloud hoặc pipeline riêng |
| **content.inspect** | Gửi nội dung trực tiếp qua DLP API và nhận kết quả đồng bộ | Kiểm tra một request, đoạn văn bản hoặc nội dung cần phản hồi ngay |

Inspection job có thể được lên lịch lặp lại bằng job trigger. Khi job hoàn tất, có thể cấu hình hành động như lưu findings vào BigQuery hoặc gửi thông báo qua Pub/Sub. Với yêu cầu quét một lượng lớn tài nguyên ở nhiều project, hãy dùng discovery để lập bản đồ trước rồi chọn tài nguyên cần inspection chi tiết.

### Ví dụ: kiểm tra nội dung đầu vào của API

Một ứng dụng hỗ trợ khách hàng nhận đoạn văn bản do người dùng nhập. Trước khi lưu nội dung vào hệ thống ticket, ứng dụng có thể gửi payload đến **content.inspect** để tìm email và số điện thoại.

Tệp **inspect-request.json**:

~~~json
{
  "inspectConfig": {
    "infoTypes": [
      { "name": "EMAIL_ADDRESS" },
      { "name": "PHONE_NUMBER" }
    ],
    "minLikelihood": "POSSIBLE",
    "includeQuote": false
  },
  "item": {
    "value": "Vui lòng liên hệ an.nguyen@example.com hoặc 0900000000."
  }
}
~~~

Gửi yêu cầu đến DLP API:

~~~bash
curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" "https://dlp.googleapis.com/v2/projects/PROJECT_ID/content:inspect" --data-binary @inspect-request.json
~~~

Trước khi chạy ví dụ, hãy bật API phù hợp trong project, cấu hình thông tin xác thực và cấp quyền cần thiết cho danh tính gọi API. Giá trị trong ví dụ chỉ là dữ liệu giả lập. **includeQuote: false** giúp hạn chế trả lại nguyên văn chuỗi được phát hiện; ứng dụng vẫn cần xử lý findings và vị trí theo cách phù hợp với logic nghiệp vụ.

Inspection chỉ phát hiện và báo cáo theo cấu hình. Nếu muốn nội dung đầu vào được che trước khi lưu, ứng dụng phải gọi quy trình de-identification hoặc tự thực hiện bước xử lý đã được kiểm soát.

## 5. InfoType detector: xác định cần tìm loại dữ liệu nào

Sensitive Data Protection sử dụng **infoType detector** để nhận diện các loại thông tin. Có hàng trăm detector tích hợp sẵn. Một số detector phổ biến gồm:

| InfoType | Ví dụ nội dung cần nhận diện |
|---|---|
| **EMAIL_ADDRESS** | Địa chỉ email |
| **PHONE_NUMBER** | Số điện thoại |
| **CREDIT_CARD_NUMBER** | Số thẻ thanh toán |
| **IP_ADDRESS** | Địa chỉ IP |
| **PERSON_NAME** | Tên người |
| **DATE_OF_BIRTH** | Ngày sinh |
| **US_SOCIAL_SECURITY_NUMBER** | Số an sinh xã hội Hoa Kỳ |
| **AUTH_TOKEN** | Một số dạng token xác thực được hỗ trợ |

Danh sách detector có tính đặc thù theo quốc gia, định dạng và loại dữ liệu. Không nên giả định detector dành cho một quốc gia sẽ nhận diện đúng định dạng của mọi quốc gia. Với mã định danh nội bộ hoặc dữ liệu riêng của doanh nghiệp, hãy kiểm tra built-in detector có phù hợp hay cần tạo custom infoType.

### Built-in detector và ngữ cảnh

Detector có thể dựa trên nhiều tín hiệu: mẫu ký tự, checksum, tiền tố, giới hạn chữ số hoặc từ ngữ xung quanh. Ví dụ, một chuỗi số có cấu trúc giống số định danh chưa chắc là số định danh hợp lệ; checksum và ngữ cảnh có thể giúp tăng độ chính xác.

Một số detector phụ thuộc ngữ cảnh. Nếu hệ thống không tìm thấy loại dữ liệu mong muốn do thiếu từ khóa gần đó, có thể cần điều chỉnh detector hoặc dùng custom detector. Luôn khai báo rõ danh sách infoTypes cần quét để tránh kiểm tra quá nhiều loại không liên quan, gây tăng độ trễ và tạo findings không cần thiết.

### Likelihood không phải xác suất pháp lý

Sensitive Data Protection gán mức likelihood cho finding:

- **VERY_UNLIKELY**
- **UNLIKELY**
- **POSSIBLE**
- **LIKELY**
- **VERY_LIKELY**

Likelihood thể hiện độ chắc chắn của detector đối với một kết quả dựa trên mẫu và ngữ cảnh. Nó không phải điểm sensitivity của dữ liệu, không phải xác suất một cá nhân bị lộ danh tính và cũng không thay thế đánh giá của chuyên gia bảo mật.

Cấu hình **minLikelihood** cho phép lọc các findings thấp hơn ngưỡng mong muốn. Ngưỡng cao có thể giảm false positive nhưng cũng có thể bỏ sót dữ liệu thực. Ngưỡng thấp tăng khả năng phát hiện nhưng thường tạo thêm kết quả cần rà soát. Hãy thử cấu hình trên tập dữ liệu đại diện và kiểm tra cả false positive lẫn false negative trước khi áp dụng diện rộng.

### Custom infoType detector

Khi dữ liệu có định dạng riêng, có thể tạo detector tùy chỉnh:

- **Regex detector:** nhận diện chuỗi theo biểu thức chính quy, phù hợp với mã hồ sơ, mã hợp đồng hoặc mã nhân viên có cấu trúc.
- **Small custom dictionary:** so khớp với danh sách giá trị nhỏ, ví dụ tên hệ thống hoặc danh sách tên dự án mật.
- **Large custom dictionary / stored infoType:** xử lý danh sách từ khóa lớn được lưu và quản lý riêng.

Ví dụ, mã hồ sơ hỗ trợ có dạng **CASE-** theo sau bởi tám chữ số. Có thể tạo custom regex detector:

~~~regex
CASE-[0-9]{8}
~~~

Regex chỉ xác định cấu trúc. Nếu một chuỗi ngẫu nhiên cũng có cấu trúc tương tự, detector vẫn có thể nhận diện nhầm. Hãy đặt likelihood hợp lý và bổ sung quy tắc ngữ cảnh như từ khóa **ticket**, **case_id** hoặc tên cột.

### Inspection rules: tinh chỉnh kết quả

Có thể kết hợp detector với các rule set:

- **Hotword rule:** tăng hoặc điều chỉnh likelihood khi từ khóa xuất hiện gần giá trị cần phát hiện. Ví dụ, mã có cấu trúc **123-4-56789** có thể đáng tin hơn khi nằm cạnh từ **MRN**.
- **Exclusion rule:** loại kết quả không mong muốn, chẳng hạn địa chỉ email thử nghiệm hoặc chuỗi mẫu cố định.
- **Adjustment rule:** điều chỉnh likelihood theo ngữ cảnh hoặc detector liên quan.

Rule được áp dụng theo thứ tự cấu hình. Hãy kiểm tra rule set bằng dữ liệu đại diện vì một rule loại trừ quá rộng có thể che mất dữ liệu thật, còn hotword quá chung có thể làm tăng false positive.

## 6. Templates và quy trình quét có thể lặp lại

Sensitive Data Protection hỗ trợ inspection template và de-identification template để tái sử dụng cấu hình. Template giúp các nhóm dùng chung danh sách infoTypes, mức likelihood, rule set và phép biến đổi đã được rà soát.

Một quy trình vận hành nên có các bước:

1. **Xác định mục tiêu:** tìm dữ liệu ở đâu, loại dữ liệu nào cần bảo vệ và ai sẽ dùng kết quả.
2. **Chọn phạm vi:** bắt đầu với một project, dataset hoặc bucket đại diện; mở rộng lên folder hoặc organization khi đã xác nhận chi phí và quyền.
3. **Chọn detector:** khai báo infoTypes cụ thể, custom detector và rule set phù hợp với dữ liệu.
4. **Chọn phương pháp:** discovery để profile diện rộng; inspection job để lấy findings chi tiết; **content.inspect** cho nội dung đồng bộ; hybrid job cho nguồn tùy ý.
5. **Chọn lịch và sampling:** đặt tần suất quét phù hợp với tốc độ thay đổi dữ liệu; dùng sampling hoặc giới hạn phạm vi khi cần kiểm tra thử.
6. **Bảo vệ kết quả:** giới hạn ai đọc findings, tránh lưu quote nếu không cần và chọn nơi lưu có IAM phù hợp.
7. **Xử lý phát hiện:** cập nhật phân loại, quyền truy cập, quy tắc lưu giữ hoặc tạo bản dữ liệu đã khử định danh.
8. **Theo dõi:** gửi sự kiện qua Pub/Sub, tích hợp Security Command Center hoặc hệ thống vận hành khi phù hợp; định kỳ rà soát profile và kết quả.

Không nên dùng một cấu hình mặc định cho mọi dữ liệu. Ví dụ, dữ liệu khách hàng ở BigQuery có thể cần **EMAIL_ADDRESS**, **PHONE_NUMBER** và **CREDIT_CARD_NUMBER**, trong khi log ứng dụng có thể cần detector cho token, địa chỉ IP và mã nội bộ.

## 7. De-identification: biến đổi dữ liệu nhạy cảm

De-identification biến đổi giá trị nhạy cảm để giảm khả năng nhận diện hoặc giảm mức độ lộ thông tin. Phép biến đổi phải phù hợp với mục tiêu sử dụng dữ liệu sau xử lý.

| Phép biến đổi | Cách hoạt động | Ví dụ |
|---|---|---|
| Redaction | Xóa toàn bộ hoặc một phần giá trị | Xóa địa chỉ email khỏi nội dung ticket |
| Replacement | Thay bằng giá trị thay thế cố định hoặc surrogate | Thay tên bằng [PERSON] |
| Masking | Thay một số ký tự bằng ký tự che | 0901234567 thành ******4567 |
| Bucketing / generalization | Thay giá trị chính xác bằng khoảng hoặc nhóm | Tuổi 27 thành nhóm 25–34 |
| Date shifting | Dịch ngày theo một khoảng ngẫu nhiên có kiểm soát | Dịch ngày khám để bảo toàn tương quan thời gian |
| Time extraction | Giữ lại phần thời gian cần phân tích | Giữ giờ trong ngày và bỏ ngày cụ thể |
| Crypto-based tokenization | Thay giá trị bằng token được tạo bằng mật mã | Email được thay bằng token ổn định |

### Chọn phép biến đổi theo nhu cầu

- Nếu dữ liệu chỉ cần hiển thị cho nhân viên hỗ trợ, masking có thể đủ để họ nhận ra vài ký tự cuối.
- Nếu không cần giữ thông tin định danh, redaction hoặc replacement có thể giảm dữ liệu nhạy cảm còn lại.
- Nếu cần phân tích nhóm tuổi hoặc khu vực, bucketing giúp giữ xu hướng tổng quát mà không lộ giá trị chính xác.
- Nếu cần liên kết nhiều bản ghi cùng một người mà không lưu plaintext identifier, pseudonymization tạo token ổn định có thể phù hợp.
- Nếu cần phân tích xu hướng theo thời gian nhưng không cần ngày thực, date shifting hoặc time extraction có thể giữ lại một phần cấu trúc dữ liệu.

### Pseudonymization và token hóa bằng mật mã

Sensitive Data Protection hỗ trợ nhiều kỹ thuật token hóa, trong đó có:

- **Deterministic encryption bằng AES-SIV:** cùng một đầu vào và context tweak tương ứng tạo token ổn định; có thể giải mã lại khi có khóa phù hợp. Phương pháp này không cần giữ nguyên bộ ký tự của đầu vào.
- **Format-preserving encryption (FPE-FFX):** tạo giá trị mã hóa có cùng độ dài và thuộc bảng ký tự được chỉ định; hữu ích khi hệ thống đích cần giữ định dạng. Phạm vi ký tự và độ dài có giới hạn, nên phải kiểm tra yêu cầu đầu vào.
- **Crypto hash:** tạo giá trị băm một chiều, phù hợp khi cần so sánh hoặc liên kết theo giá trị băm và không cần khôi phục giá trị gốc.

Với phương pháp có thể đảo ngược, khóa mã hóa trở thành tài sản nhạy cảm. Có thể dùng Cloud KMS để bọc (wrap) khóa mã hóa của Sensitive Data Protection. Cần giới hạn quyền sử dụng và quản trị khóa, lưu trữ khóa an toàn, kiểm soát khả năng re-identify và có quy trình xoay vòng/khôi phục. Việc token hóa không tự động đồng nghĩa với ẩn danh tuyệt đối.

### Biến đổi dữ liệu có cấu trúc

Với dữ liệu dạng bảng, cần quyết định biến đổi theo hai hướng:

- **InfoType transformation:** áp dụng khi giá trị của một cột hoặc nội dung khớp với detector đã chọn.
- **Record transformation:** áp dụng cho một hoặc nhiều trường/cột cụ thể theo cấu trúc bản ghi, kể cả khi không dựa vào một infoType detector.

Ví dụ, trong bảng khách hàng, có thể token hóa **customer_id**, masking **phone_number**, xóa **email** và bucketing **age**. Hãy giữ nguyên khóa liên kết cần thiết cho phân tích, nhưng phải đánh giá xem tổ hợp các cột còn lại có thể tái nhận dạng cá nhân hay không.

De-identification có thể thực hiện qua **content.deidentify** cho nội dung gửi trực tiếp tới API hoặc qua quy trình xử lý dữ liệu lưu trữ được hỗ trợ. Với dữ liệu production, nên ghi kết quả ra bản sao hoặc vùng dữ liệu đích, xác minh chất lượng rồi mới chuyển consumer sang dùng dữ liệu đã biến đổi.

## 8. Risk analysis: kiểm tra khả năng tái nhận dạng

Một tập dữ liệu không còn tên, email hoặc số điện thoại vẫn có thể tiết lộ cá nhân qua các quasi-identifier. Sensitive Data Protection hỗ trợ các chỉ số phân tích rủi ro trên dữ liệu có cấu trúc trong BigQuery.

| Chỉ số | Ý nghĩa |
|---|---|
| k-anonymity | Mỗi tổ hợp quasi-identifier của một bản ghi xuất hiện ở ít nhất k bản ghi trong tập dữ liệu |
| l-diversity | Mỗi nhóm bản ghi có cùng quasi-identifier có đủ sự đa dạng của thuộc tính nhạy cảm |
| k-map | So sánh khả năng tái nhận dạng với một tập dữ liệu tham chiếu lớn hơn |
| δ-presence | Ước lượng khả năng một cá nhân có mặt trong tập dữ liệu |

Ví dụ, nếu một bản ghi có tuổi 34, mã bưu chính và giới tính chỉ trùng với một người trong tập dữ liệu, nguy cơ tái nhận dạng có thể cao. Tổng quát hóa tuổi thành nhóm và giảm độ chi tiết địa lý có thể làm tăng số bản ghi tương tự. Tuy nhiên, việc tăng k-anonymity không tự bảo đảm dữ liệu không thể bị suy luận; l-diversity và các kiểm tra khác có thể cần thiết để đánh giá thuộc tính nhạy cảm.

Risk analysis nên được dùng trước khi khử định danh để chọn chiến lược và sau khi khử định danh để kiểm tra lại. Mỗi lần giảm chi tiết dữ liệu đều có thể làm giảm giá trị phân tích; cần cân bằng yêu cầu riêng tư và utility của tập dữ liệu.

## 9. Tích hợp kết quả vào quy trình bảo mật

Data profiles và findings chỉ tạo giá trị khi được đưa vào quy trình xử lý:

- **BigQuery:** lưu kết quả quét, tạo báo cáo và phân tích xu hướng dữ liệu nhạy cảm.
- **Pub/Sub:** phát sự kiện để kích hoạt workflow xử lý hoặc thông báo.
- **Security Command Center:** tập trung phát hiện và ưu tiên xử lý rủi ro bảo mật khi tích hợp phù hợp.
- **Google Security Operations:** đưa insight discovery vào luồng phân tích bảo mật theo phạm vi hỗ trợ.
- **Knowledge Catalog:** gắn metadata profile vào tài sản dữ liệu để người dùng biết mức độ nhạy cảm trước khi sử dụng.

Ví dụ, discovery phát hiện một bảng BigQuery có cột email và số thẻ thanh toán. Workflow có thể tạo ticket cho chủ sở hữu dữ liệu, yêu cầu kiểm tra quyền IAM, áp dụng chính sách phân loại và chạy inspection trên bảng. Sau khi xác nhận, nhóm dữ liệu tạo bản sao đã khử định danh để phục vụ phân tích.

Không nên tự động xóa dữ liệu hoặc thu hồi quyền chỉ dựa trên một finding có likelihood thấp. Hãy xác định mức độ nghiêm trọng, chủ sở hữu, nguồn dữ liệu và quy trình phê duyệt remediation. Các hành động tự động cần có điều kiện rõ ràng, log và khả năng truy vết.

## 10. IAM, data residency và bảo vệ kết quả quét

Sensitive Data Protection cần quyền gọi API và quyền truy cập vào tài nguyên nguồn hoặc đích tương ứng. Người tạo job, người quản lý template, người đọc findings và service agent có thể cần những quyền khác nhau.

Một số role có sẵn gồm:

- **roles/dlp.admin:** quản trị Sensitive Data Protection, bao gồm jobs và templates.
- **roles/dlp.user:** thực hiện các thao tác sử dụng dịch vụ theo quyền được cấp.
- **roles/dlp.reader:** đọc các tài nguyên và kết quả được cho phép.
- **roles/dlp.jobsEditor:** quản lý các job theo phạm vi quyền của role.
- **roles/dlp.orgdriver** và **roles/dlp.projectdriver:** cung cấp quyền cần thiết cho DLP service account tạo data profile ở phạm vi organization/folder hoặc project tương ứng.

Danh sách permission thay đổi theo tính năng và tài nguyên. Hãy xem bảng IAM role/permission hiện hành để cấp quyền tối thiểu cần thiết. Quyền đọc BigQuery, Cloud Storage hoặc quyền ghi kết quả vẫn cần được xét riêng theo nguồn và đích.

**Service agent role chỉ cấp cho service agent tương ứng.** Không cấp **roles/dlp.serviceAgent** cho người dùng hoặc service account ứng dụng thông thường. Khi bật tính năng cần service agent, hãy để Google Cloud thiết lập principal dịch vụ và cấp đúng quyền theo hướng dẫn của tính năng đó.

Hai role **roles/dlp.orgdriver** và **roles/dlp.projectdriver** cũng phục vụ tài khoản dịch vụ của Sensitive Data Protection trong quy trình discovery. Hãy cấp chúng cho đúng service agent theo hướng dẫn thiết lập discovery, không dùng chúng như role thông thường cho người đọc findings.

Findings có thể chứa vị trí dữ liệu, tên cột, metadata và đôi khi cả quote. Vì vậy:

- Lưu kết quả trong project/dataset/bucket có IAM hạn chế.
- Chỉ bật **includeQuote** khi có lý do nghiệp vụ và bảo vệ quote như dữ liệu gốc.
- Không ghi nội dung nhạy cảm vào log ứng dụng hoặc thông báo Pub/Sub nếu không cần.
- Phân tách quyền tạo job, xem kết quả và xử lý dữ liệu gốc.
- Theo dõi truy cập vào findings và thay đổi scan configuration.
- Xác định thời gian lưu giữ kết quả, bản sao đã khử định danh và khóa tokenization.

Với yêu cầu lưu trú dữ liệu, kiểm tra location của nguồn, scan configuration, nơi lưu profile/findings và regional endpoint được hỗ trợ. Không suy luận rằng chỉ chọn endpoint khu vực là đủ để đáp ứng mọi yêu cầu residency; hãy đối chiếu tài liệu của từng tính năng và dịch vụ nguồn.

## 11. Giới hạn và lưu ý khi vận hành

Sensitive Data Protection hỗ trợ nhiều loại dữ liệu và detector, nhưng kết quả vẫn phụ thuộc vào định dạng, ngôn ngữ, ngữ cảnh và cấu hình. Một detector có thể bỏ sót giá trị không theo định dạng dự kiến hoặc nhận diện nhầm chuỗi có cấu trúc tương tự. Hãy dùng dữ liệu mẫu đã biết để đo precision và recall trước khi triển khai diện rộng.

Khi quét dữ liệu lớn:

- Ưu tiên tài sản có độ nhạy cảm cao, được truy cập rộng hoặc chưa rõ chủ sở hữu.
- Bắt đầu bằng discovery để xác định khu vực đáng kiểm tra.
- Chỉ định infoTypes cần thiết; hạn chế detector không liên quan.
- Dùng sampling, giới hạn thời gian hoặc phạm vi khi phù hợp.
- Ước tính chi phí theo loại tác vụ và lượng dữ liệu xử lý trước khi mở rộng.
- Theo dõi thời gian chạy, số lượng findings và chi phí theo từng nhóm tài nguyên.

Sensitive Data Protection cũng không thay thế Secret Manager, Cloud KMS, IAM, VPC Service Controls, mã hóa lưu trữ hay chính sách quản trị dữ liệu. Secret Manager quản lý vòng đời giá trị bí mật mà ứng dụng cần dùng; Sensitive Data Protection giúp phát hiện hoặc biến đổi nội dung nhạy cảm. Cloud KMS quản lý khóa mật mã; IAM quyết định principal nào có thể truy cập tài nguyên. Các dịch vụ này bổ sung cho nhau trong kiến trúc bảo vệ dữ liệu.

## 12. Tình huống thực tế: bảo vệ dữ liệu khách hàng trước khi chia sẻ cho nhóm phân tích

Một công ty thương mại điện tử lưu thông tin khách hàng trong BigQuery. Bảng giao dịch chứa mã khách hàng, email, số điện thoại, địa chỉ giao hàng, thời điểm mua hàng và giá trị đơn hàng. Nhóm phân tích cần dữ liệu để tính tỷ lệ mua lại và phân tích xu hướng theo khu vực.

**Bước 1 — Discovery:** nhóm bảo mật cấu hình discovery trên phạm vi project dữ liệu. Profile cho thấy một bảng giao dịch có email và số điện thoại, đồng thời một số cột có mức độ duy nhất cao.

**Bước 2 — Inspection:** nhóm tạo inspection job cho bảng cần xử lý, chọn **EMAIL_ADDRESS**, **PHONE_NUMBER** và detector phù hợp với mã khách hàng nội bộ. Findings được lưu vào BigQuery bảo vệ riêng, không bật quote nếu không cần.

**Bước 3 — Chọn phép biến đổi:** email và số điện thoại được token hóa để vẫn có thể liên kết bản ghi theo khách hàng; địa chỉ chi tiết được tổng quát hóa thành khu vực; thời điểm giao dịch được xử lý theo độ chi tiết cần cho phân tích. Các trường không cần thiết cho mục tiêu phân tích được loại bỏ khỏi bản chia sẻ.

**Bước 4 — Risk analysis:** nhóm đánh giá k-anonymity và l-diversity trên tập dữ liệu đã biến đổi. Nếu một nhóm nhỏ vẫn dễ bị nhận diện do kết hợp khu vực và thời điểm giao dịch, nhóm tăng mức tổng quát hóa hoặc giảm độ chi tiết.

**Bước 5 — Kiểm soát phát hành:** bản dữ liệu đã xử lý được lưu trong dataset riêng, quyền chỉ cấp cho nhóm phân tích. Nhóm bảo mật kiểm tra chất lượng số liệu và khả năng liên kết trước khi cho phép sử dụng.

Quy trình này giữ lại thuộc tính cần cho phân tích, giảm việc chia sẻ plaintext identifier và tạo bằng chứng về cách dữ liệu được xử lý. Khóa tokenization và bản dữ liệu gốc vẫn được quản lý theo chính sách riêng.

## 13. Checklist triển khai Sensitive Data Protection

- [ ] Đã xác định loại dữ liệu cần bảo vệ và chính sách phân loại của tổ chức.
- [ ] Đã lập danh sách nguồn dữ liệu, project, chủ sở hữu và phạm vi quét.
- [ ] Đã chọn discovery hay inspection theo mục tiêu và mức chi tiết cần thiết.
- [ ] Đã khai báo rõ built-in/custom infoTypes và kiểm thử detector trên dữ liệu đại diện.
- [ ] Đã rà soát likelihood, hotword, exclusion và adjustment rules để kiểm soát false positive/false negative.
- [ ] Đã xác định lịch quét, sampling, giới hạn phạm vi và ngân sách.
- [ ] Đã chọn phép biến đổi phù hợp với nhu cầu sử dụng dữ liệu sau xử lý.
- [ ] Đã đánh giá rủi ro tái nhận dạng trên dữ liệu đã khử định danh.
- [ ] Findings, quotes, templates và scan configurations được bảo vệ bằng IAM phù hợp.
- [ ] Regional endpoint, location và data residency đáp ứng yêu cầu tổ chức.
- [ ] Có chủ sở hữu và quy trình xử lý findings, theo dõi remediation và kiểm tra định kỳ.

## Kết luận

Sensitive Data Protection giúp tổ chức hiểu dữ liệu nhạy cảm đang ở đâu, loại dữ liệu nào xuất hiện và cần bảo vệ ra sao. Discovery cung cấp bản đồ và profile tổng quan; inspection tìm từng vị trí; infoType detector xác định loại dữ liệu; de-identification giảm khả năng nhận diện; risk analysis kiểm tra phần rủi ro còn lại. Để triển khai hiệu quả, cần kết hợp cấu hình detector phù hợp, phạm vi quét có kiểm soát, IAM tối thiểu, bảo vệ findings và quy trình remediation có thể kiểm chứng.

## Tài liệu tham khảo

- [Sensitive Data Protection overview](https://docs.cloud.google.com/sensitive-data-protection/docs/sensitive-data-protection-overview)
- [Learn about your data through discovery and inspection](https://docs.cloud.google.com/sensitive-data-protection/docs/learn-about-your-data)
- [Overview of sensitive data discovery](https://docs.cloud.google.com/sensitive-data-protection/docs/data-profiles)
- [InfoTypes and infoType detectors](https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-infotypes)
- [Creating and scheduling inspection jobs](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-job-triggers)
- [Inspect Google Cloud storage and databases](https://docs.cloud.google.com/sensitive-data-protection/docs/inspecting-storage)
- [De-identifying sensitive data](https://docs.cloud.google.com/sensitive-data-protection/docs/deidentify-sensitive-data)
- [Transformation reference](https://docs.cloud.google.com/sensitive-data-protection/docs/transformations-reference)
- [Pseudonymization](https://docs.cloud.google.com/sensitive-data-protection/docs/pseudonymization)
- [Measuring re-identification and disclosure risk](https://docs.cloud.google.com/sensitive-data-protection/docs/compute-risk-analysis)
- [Sensitive Data Protection roles and permissions](https://docs.cloud.google.com/sensitive-data-protection/docs/access-control/roles-permissions)

