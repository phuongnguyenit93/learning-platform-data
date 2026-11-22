# De-identification, masking và tokenization dữ liệu

Các hệ thống trên Google Cloud thường cần dùng dữ liệu thật để phân tích, kiểm thử, hỗ trợ khách hàng hoặc huấn luyện mô hình. Tuy nhiên, dữ liệu thật có thể chứa tên, email, số điện thoại, địa chỉ, mã định danh, thông tin tài chính hoặc dữ liệu sức khỏe. Nếu mọi người dùng và mọi môi trường đều truy cập trực tiếp các giá trị này, nguy cơ rò rỉ và sử dụng sai mục đích sẽ tăng lên.

**De-identification**, **masking** và **tokenization** là những kỹ thuật giảm khả năng liên kết dữ liệu với một cá nhân hoặc giảm mức độ nhạy cảm của giá trị được chia sẻ. Chúng có cách hoạt động và mức độ bảo vệ khác nhau. Một số kỹ thuật làm mất thông tin gốc, một số giữ lại một phần để người dùng vẫn làm việc được, và một số cho phép khôi phục giá trị khi có khóa hoặc bảng ánh xạ được bảo vệ.

Trong module CLOUD_PROVIDERS_GCP, chủ đề này gắn với IAM, Cloud Storage, BigQuery, Dataflow, Cloud KMS và quy trình quản trị dữ liệu. Google Cloud cung cấp Sensitive Data Protection (tên trước đây là Cloud Data Loss Prevention hoặc Cloud DLP) để phát hiện và biến đổi dữ liệu nhạy cảm. BigQuery còn có các chính sách kiểm soát truy cập cột và data masking ở thời điểm truy vấn. Lựa chọn đúng kỹ thuật cần bắt đầu từ mục đích sử dụng dữ liệu, khả năng cần khôi phục, rủi ro tái nhận dạng và quyền truy cập của từng nhóm người dùng.

Sau bài học này, bạn có thể:

- Phân biệt de-identification, anonymization, pseudonymization, masking và tokenization.
- Chọn phép biến đổi phù hợp với email, số điện thoại, ngày sinh, số tài khoản và dữ liệu phân tích.
- Dùng Sensitive Data Protection để kiểm tra và biến đổi nội dung có thông tin nhạy cảm.
- Thiết kế token ổn định hoặc token có thể khôi phục bằng khóa hay kho ánh xạ.
- Áp dụng data masking và column-level security trong BigQuery.
- Xây dựng luồng xử lý dữ liệu đã giảm định danh, quản lý khóa, kiểm soát IAM và kiểm tra nguy cơ tái nhận dạng.

## 1. Phân biệt các khái niệm

### De-identification

De-identification là quá trình biến đổi dữ liệu để giảm hoặc loại bỏ những thuộc tính có thể nhận diện trực tiếp một người. Ví dụ, một tập dữ liệu hỗ trợ phân tích có thể thay tên bằng mã giả, che bớt số điện thoại, chuyển ngày sinh thành nhóm tuổi và bỏ địa chỉ chi tiết.

De-identification thường là một tập hợp kỹ thuật. Kết quả có thể vẫn giữ một số đặc điểm hữu ích như nhóm tuổi, khu vực rộng hoặc loại giao dịch. Vì vậy, de-identification không tự động đồng nghĩa với dữ liệu đã ẩn danh hoàn toàn. Một người vẫn có thể được suy ra từ tổ hợp thuộc tính còn lại hoặc bằng cách đối chiếu với nguồn dữ liệu khác.

### Anonymization và pseudonymization

- **Anonymization (ẩn danh hóa):** biến đổi dữ liệu sao cho cá nhân không còn có thể được nhận diện bằng những phương tiện có thể được sử dụng hợp lý trong bối cảnh xử lý. Đây là mục tiêu mạnh; cần đánh giá cả dữ liệu phụ trợ, khả năng liên kết và môi trường truy cập.
- **Pseudonymization (giả danh hóa):** thay định danh trực tiếp bằng mã giả hoặc giá trị thay thế. Dữ liệu vẫn có thể được liên kết lại với cá nhân nếu còn khóa, bảng ánh xạ hoặc thông tin bổ sung.

Ví dụ, thay `customer@example.com` bằng `CUST-8F21` là giả danh hóa nếu một hệ thống khác còn lưu bảng ánh xạ từ `CUST-8F21` về email gốc. Việc bỏ tên và email vẫn chưa bảo đảm ẩn danh nếu bản ghi còn ngày sinh chính xác, mã bưu chính nhỏ và lịch sử giao dịch hiếm gặp.

### Masking

Masking (che dữ liệu) thay thế toàn bộ hoặc một phần giá trị bằng ký tự che, giá trị cố định hoặc giá trị đã biến đổi. Ví dụ:

| Giá trị gốc | Cách masking | Kết quả minh họa |
|---|---|---|
| `lan.nguyen@example.com` | Thay bằng nhãn loại dữ liệu | `[EMAIL_ADDRESS]` |
| `0901234567` | Che một phần số | `******4567` |
| `Nguyen Thi Lan` | Che tên | `N*************` |
| `1988-04-23` | Giữ năm | `1988-01-01` hoặc `1988` tùy quy tắc |
| `123456789012` | Chỉ giữ bốn số cuối | `********9012` |

Masking thường phù hợp với giao diện hỗ trợ, log, báo cáo hoặc môi trường mà người dùng chỉ cần một phần thông tin. Che dữ liệu trong kết quả hiển thị không đồng nghĩa dữ liệu gốc đã được thay đổi hoặc xóa khỏi nguồn.

### Tokenization

Tokenization (mã hóa thành token thay thế) thay giá trị nhạy cảm bằng một token dùng trong hệ thống khác. Ví dụ, số thẻ thanh toán được thay bằng `tok_7d91a2`. Ứng dụng phân tích có thể dùng token làm khóa liên kết bản ghi mà không cần biết số thẻ thật.

Tokenization có hai mô hình phổ biến:

1. **Token vault:** hệ thống tạo token ngẫu nhiên và lưu cặp token–giá trị gốc trong kho ánh xạ riêng. Muốn khôi phục phải truy cập vault với quyền được kiểm soát.
2. **Cryptographic tokenization:** dùng phép biến đổi mật mã có khóa để tạo giá trị thay thế. Một số cách tạo token cho cùng đầu vào luôn cho cùng kết quả; người có quyền và khóa phù hợp có thể khôi phục bằng quy trình giải mã được hỗ trợ.

Token có thể được tạo ngẫu nhiên hoặc xác định. Token xác định giúp nối các bản ghi của cùng một khách hàng qua nhiều hệ thống, nhưng cũng làm lộ khả năng liên kết hoạt động của khách hàng. Token ngẫu nhiên giảm khả năng liên kết nếu mỗi lần tạo ra một giá trị khác nhau, nhưng cần vault hoặc cơ chế định danh riêng để nối dữ liệu.

## 2. Chọn kỹ thuật theo mục tiêu

Không có một phép biến đổi phù hợp cho mọi trường dữ liệu. Hãy xác định trước người nhận dữ liệu cần làm gì và có cần khôi phục giá trị gốc hay không.

| Kỹ thuật | Kết quả | Có thể khôi phục? | Tình huống phù hợp |
|---|---|---|---|
| Redaction / thay bằng nhãn | Bỏ giá trị nhạy cảm hoặc thay bằng loại dữ liệu | Không | Chia sẻ dữ liệu mẫu, loại bỏ trường không cần thiết |
| Character masking | Che một phần ký tự | Không từ kết quả đã che | Giao diện hỗ trợ, xác nhận một tài khoản |
| Generalization / bucketing | Chuyển giá trị chính xác thành nhóm hoặc khoảng | Không thể khôi phục chính xác | Phân tích theo nhóm tuổi, mức thu nhập, vùng địa lý |
| Date shifting | Dịch ngày theo một khoảng được kiểm soát | Không nếu không giữ thông tin dịch; có thể duy trì quan hệ ngày | Bảo toàn khoảng cách thời gian trong dữ liệu thử nghiệm hoặc phân tích |
| Hash một chiều | Tạo dấu vân tay cố định từ giá trị | Không giải mã được; giá trị ít entropy có thể bị dò | So khớp hoặc loại trùng khi thiết kế chống dò phù hợp |
| Deterministic encryption | Cùng đầu vào và ngữ cảnh cho cùng ciphertext | Có, khi có khóa và quy trình giải mã | Liên kết bản ghi ổn định và cần khôi phục có kiểm soát |
| Format-preserving encryption (FPE) | Ciphertext giữ bảng ký tự và độ dài theo cấu hình | Có, với khóa phù hợp | Hệ thống cũ yêu cầu định dạng hoặc độ dài nhất định |
| Token vault | Token ngẫu nhiên trỏ tới giá trị gốc trong kho ánh xạ | Có, qua vault | Thanh toán, định danh khách hàng và tích hợp nhiều hệ thống |

### Quy tắc lựa chọn nhanh

- Nếu người dùng chỉ cần biết có dữ liệu nhạy cảm ở đó, hãy thay bằng nhãn loại dữ liệu hoặc xóa giá trị.
- Nếu chỉ cần xác nhận một phần thông tin, hãy che các ký tự không cần thiết.
- Nếu phân tích chỉ cần xu hướng, hãy tổng quát hóa giá trị thành nhóm, khoảng hoặc thời điểm rộng hơn.
- Nếu cần nối bản ghi nhưng không cần đọc giá trị gốc, hãy cân nhắc token xác định hoặc hash có khóa.
- Nếu quy trình nghiệp vụ bắt buộc khôi phục, hãy dùng token vault hoặc phép mã hóa có khóa, kèm kiểm soát quyền và nhật ký truy cập.

Không nên dùng hash thuần cho email, số điện thoại hoặc mã định danh có không gian giá trị nhỏ. Kẻ tấn công có thể tạo trước danh sách giá trị thường gặp, băm chúng và đối chiếu kết quả. Hash có khóa (HMAC) hoặc token hóa bằng khóa giúp giảm rủi ro dò từ điển, nhưng vẫn cần bảo vệ khóa và giới hạn quyền so khớp.

## 3. Nhận diện dữ liệu nhạy cảm với Sensitive Data Protection

Sensitive Data Protection là dịch vụ quản lý dữ liệu nhạy cảm của Google Cloud, trước đây thường được gọi là Cloud DLP. Dịch vụ có thể kiểm tra nội dung, phát hiện thông tin theo các `infoType` dựng sẵn hoặc do tổ chức định nghĩa, đánh giá mức độ có khả năng là dữ liệu nhạy cảm và áp dụng phép biến đổi.

Một số infoType phổ biến:

- `EMAIL_ADDRESS`: địa chỉ email.
- `PHONE_NUMBER`: số điện thoại.
- `PERSON_NAME`: tên người.
- `CREDIT_CARD_NUMBER`: số thẻ thanh toán.
- `US_SOCIAL_SECURITY_NUMBER`: số an sinh xã hội Hoa Kỳ.
- Các infoType về ngày tháng, địa chỉ, tài khoản và dữ liệu định danh khác tùy danh mục hỗ trợ.

Danh mục infoType phụ thuộc ngôn ngữ và loại dữ liệu. Với dữ liệu nội bộ như mã khách hàng, mã hợp đồng hoặc mã nhân viên, có thể cần custom infoType bằng regular expression, dictionary hoặc quy tắc phù hợp. Không nên mặc định một infoType dựng sẵn nhận diện chính xác mọi định dạng dữ liệu của tổ chức.

### Quy trình inspect và de-identify

1. Xác định nguồn dữ liệu, loại thông tin cần phát hiện và mục đích xử lý.
2. Cấu hình `inspectConfig`: infoType, likelihood tối thiểu, quy tắc loại trừ và điều kiện ngữ cảnh nếu cần.
3. Gửi nội dung cần kiểm tra tới Sensitive Data Protection hoặc tạo inspection job cho nguồn dữ liệu được hỗ trợ.
4. Đánh giá finding, số lượng phát hiện và tỷ lệ false positive/false negative trên mẫu đại diện.
5. Cấu hình `deidentifyConfig` để chọn phép biến đổi theo từng infoType hoặc theo trường dữ liệu.
6. Ghi kết quả đã biến đổi vào vùng dữ liệu có quyền truy cập phù hợp và xác minh dữ liệu gốc không bị đưa vào log hoặc đầu ra ngoài ý muốn.

Sensitive Data Protection hỗ trợ hai nhóm thao tác quan trọng:

- **Inspect:** tìm và phân loại dữ liệu nhạy cảm. Thao tác này không tự thay đổi dữ liệu nguồn.
- **De-identify:** áp dụng phép biến đổi đã cấu hình lên nội dung hoặc trường dữ liệu.

Đối với nội dung nhỏ, API `content:inspect` và `content:deidentify` có thể được gọi trong luồng ứng dụng. Với dữ liệu lớn trong Cloud Storage hoặc BigQuery, có thể dùng inspection job, job trigger, template và các tích hợp xử lý dữ liệu phù hợp. Chọn cách chạy đồng bộ hay theo job dựa trên kích thước dữ liệu, yêu cầu độ trễ, quota và chi phí.

### Các phép biến đổi thường dùng

| Phép biến đổi | Hành vi | Lưu ý |
|---|---|---|
| `replaceWithInfoTypeConfig` | Thay giá trị bằng nhãn như `[EMAIL_ADDRESS]` | Hữu ích khi cần giữ thông tin loại dữ liệu |
| `redactConfig` | Xóa nội dung được phát hiện | Giảm dữ liệu đầu ra, có thể làm mất ngữ cảnh |
| `characterMaskConfig` | Che một số ký tự | Phải xác định số ký tự và hướng che phù hợp |
| `cryptoHashConfig` | Tạo hash bằng khóa | Không thể giải mã; vẫn cần đánh giá khả năng liên kết và dò giá trị |
| `cryptoDeterministicConfig` | Mã hóa xác định bằng khóa | Có thể hỗ trợ khôi phục; cùng đầu vào/ngữ cảnh tạo kết quả ổn định |
| `cryptoReplaceFfxFpeConfig` | Mã hóa bảo toàn định dạng theo cấu hình | Chỉ dùng khi thực sự cần giữ định dạng và đã đánh giá miền giá trị |
| `dateShiftConfig` | Dịch ngày theo khoảng cấu hình | Cần chọn ngữ cảnh nhất quán nếu muốn giữ quan hệ ngày của một cá nhân |
| `bucketingConfig` | Chuyển số thành khoảng | Giảm độ chính xác nhưng vẫn giữ giá trị phân tích |
| `timePartConfig` | Giữ lại thành phần thời gian được chọn | Phù hợp khi chỉ cần năm, tháng hoặc ngày trong tuần |

Các phép biến đổi có thể áp dụng theo infoType hoặc theo trường trong record. Với dữ liệu có cấu trúc, nên ánh xạ chính xác từng trường và đặt quy tắc riêng cho các cột có ý nghĩa khác nhau. Một số trường như mã giao dịch có thể cần giữ nguyên để đối soát, trong khi tên và số điện thoại phải được loại bỏ hoặc token hóa.

## 4. Thực hành: che email và số điện thoại trong nội dung

Ví dụ sau dùng `content:deidentify` để thay email bằng nhãn `[EMAIL_ADDRESS]` và che một phần số điện thoại. Đây là ví dụ nội dung văn bản nhỏ; với bảng dữ liệu hoặc tệp lớn, hãy dùng cơ chế xử lý phù hợp cho nguồn dữ liệu.

### Bước 1: Bật API và xác định project

~~~bash
export PROJECT_ID="data-protection-prod"

gcloud services enable dlp.googleapis.com --project="$PROJECT_ID"
~~~

Tài khoản gọi API cần quyền sử dụng Sensitive Data Protection trong project. Trong môi trường production, nên dùng service account của workload với IAM tối thiểu cần thiết và không lưu access token trong mã nguồn.

### Bước 2: Chuẩn bị request

Request JSON dưới đây minh họa việc phát hiện email và số điện thoại, thay email bằng nhãn loại dữ liệu và che sáu ký tự đầu của số điện thoại:

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
  "deidentifyConfig": {
    "infoTypeTransformations": {
      "transformations": [
        {
          "infoTypes": [{ "name": "EMAIL_ADDRESS" }],
          "primitiveTransformation": {
            "replaceWithInfoTypeConfig": {}
          }
        },
        {
          "infoTypes": [{ "name": "PHONE_NUMBER" }],
          "primitiveTransformation": {
            "characterMaskConfig": {
              "maskingCharacter": "*",
              "numberToMask": 6,
              "reverseOrder": false
            }
          }
        }
      ]
    }
  },
  "item": {
    "value": "Lien he Lan qua lan.nguyen@example.com hoac 0901234567."
  }
}
~~~

Lưu request vào một tệp được bảo vệ, ví dụ `request.json`. Không đưa dữ liệu thật của khách hàng vào shell history, ví dụ công khai hoặc hệ thống log. Giá trị `minLikelihood` cần được hiệu chỉnh bằng mẫu dữ liệu thực tế; ngưỡng quá thấp có thể tạo nhiều false positive, còn ngưỡng quá cao có thể bỏ sót dữ liệu.

### Bước 3: Gọi API

~~~bash
curl -X POST \
  "https://dlp.googleapis.com/v2/projects/${PROJECT_ID}/locations/global/content:deidentify" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @request.json
~~~

Trong phản hồi, trường `item.value` chứa nội dung đã biến đổi. Kết quả minh họa có dạng:

~~~text
Lien he Lan qua [EMAIL_ADDRESS] hoac ******4567.
~~~

Đây là ví dụ minh họa cho một payload. Hãy kiểm tra API response, các finding và dữ liệu đầu ra thực tế trước khi đưa cấu hình vào pipeline. Nếu cần giữ lại một phần email hoặc số điện thoại, hãy điều chỉnh phép masking và kiểm thử với nhiều định dạng khác nhau.

### Bước 4: Kiểm tra kết quả và bảo vệ dữ liệu

- Xác nhận email và số điện thoại được xử lý đúng, không còn giá trị gốc trong kết quả.
- Kiểm tra các định dạng có dấu cách, mã quốc gia, dấu gạch nối và dữ liệu bị thiếu.
- Kiểm tra trường hợp dữ liệu nhạy cảm không được phát hiện và trường hợp văn bản bình thường bị nhận diện nhầm.
- Chỉ ghi kết quả đã xử lý vào vùng chia sẻ; giới hạn quyền truy cập vùng raw.
- Không ghi request chứa dữ liệu gốc hoặc response nhạy cảm vào log ứng dụng.

## 5. Tokenization có thể khôi phục và token ổn định

Tokenization hữu ích khi nhiều hệ thống cần dùng chung một định danh thay thế. Ví dụ, hệ thống hỗ trợ, phân tích và báo cáo có thể cùng sử dụng `customer_token` để nối các giao dịch mà không lưu email hoặc số tài khoản thật.

### Token vault

Trong mô hình vault, một dịch vụ chuyên trách tạo token ngẫu nhiên và lưu ánh xạ:

~~~text
Hệ thống nguồn
   |
   | số tài khoản thật
   v
Tokenization service
   |--------------------> Token vault (token <-> giá trị gốc)
   |
   v
tok_7d91a2
   |
   v
BigQuery / báo cáo / ứng dụng phân tích
~~~

Vault phải được bảo vệ như một kho dữ liệu nhạy cảm: tách project hoặc ranh giới bảo mật, mã hóa, IAM chặt chẽ, audit log, kiểm soát truy cập theo mục đích và giới hạn tốc độ tra cứu. Chỉ dịch vụ có nhu cầu nghiệp vụ mới được gọi chức năng đổi token về giá trị gốc. Không chia sẻ bản sao vault cho nhóm phân tích.

Ưu điểm của token ngẫu nhiên là không để lộ trực tiếp mối quan hệ toán học với giá trị gốc. Đổi lại, vault trở thành thành phần quan trọng về tính sẵn sàng, sao lưu, phục hồi và kiểm soát truy cập. Nếu mất ánh xạ, việc khôi phục giá trị gốc có thể không còn khả thi.

### Token hóa bằng mật mã

Sensitive Data Protection hỗ trợ các phép biến đổi mật mã như deterministic encryption và format-preserving encryption. Khóa có thể được quản lý thông qua Cloud KMS và cấu hình khóa tương ứng của dịch vụ. Khi dùng khóa được Cloud KMS bảo vệ, service agent của Sensitive Data Protection cần quyền sử dụng CryptoKey theo yêu cầu của phép biến đổi.

**Deterministic encryption** tạo ciphertext ổn định cho cùng giá trị đầu vào và cùng ngữ cảnh. Điều này giúp nối bản ghi qua nhiều tập dữ liệu, nhưng cũng cho phép người có quyền xem token biết các bản ghi nào có cùng giá trị. Nếu cùng một khóa được dùng cho nhiều mục đích hoặc nhiều miền dữ liệu, nguy cơ liên kết ngoài ý muốn sẽ tăng.

**Format-preserving encryption (FPE)** giữ cấu trúc ký tự hoặc độ dài theo alphabet đã chọn. Ví dụ, một mã chỉ gồm chữ số có thể được biến đổi thành một chuỗi chữ số cùng độ dài. FPE không tự động làm dữ liệu an toàn: miền giá trị nhỏ, dữ liệu có cấu trúc dễ đoán hoặc nhiều bản rõ đã biết có thể làm giảm mức bảo vệ. Chỉ dùng khi hệ thống đích thật sự cần định dạng đó và thuật toán được dịch vụ hỗ trợ.

Hash một chiều không phải token có thể khôi phục. Nếu cần liên kết ổn định nhưng không cần giải mã, có thể cân nhắc hash có khóa. Nếu cần khôi phục, phải chọn vault hoặc phép mã hóa có khóa và xây dựng quy trình cấp quyền giải mã rõ ràng.

### Ngữ cảnh (context) và phạm vi liên kết

Với một số phép mã hóa xác định, có thể sử dụng context để giới hạn miền mà token có ý nghĩa. Chẳng hạn, cùng một email có thể tạo token khác nhau cho từng tenant hoặc từng mục đích xử lý. Điều này giảm khả năng liên kết dữ liệu xuyên hệ thống, nhưng cần thống nhất context ở các bước mã hóa và giải mã.

Không đưa thông tin nhận diện trực tiếp vào context nếu nó sẽ xuất hiện trong log hoặc metadata. Hãy xác định rõ ai quản lý context, cách phiên bản hóa và cách ứng dụng dùng lại context để tránh lỗi giải mã.

## 6. Masking dữ liệu trong BigQuery

BigQuery hỗ trợ kiểm soát truy cập ở cấp cột và data masking. Có thể kết hợp:

- **Column-level security với policy tags:** giới hạn nhóm người dùng được đọc cột nhạy cảm.
- **Data masking policies:** trả về giá trị đã được che hoặc biến đổi cho người dùng được cấp quyền xem dữ liệu masked.
- **Authorized views hoặc views thông thường:** công bố một tập trường và biểu thức đã xử lý cho một nhóm người dùng cụ thể.
- **Row-level access policies:** giới hạn những hàng mà người dùng được xem; đây là kiểm soát theo hàng, không thay thế masking theo cột.

Data masking policy được áp dụng khi truy vấn. Người dùng có quyền phù hợp có thể thấy giá trị đã mask trong khi người được cấp quyền đọc dữ liệu gốc có thể thấy giá trị nguyên bản theo chính sách. Dữ liệu lưu trong bảng nguồn không bị ghi đè bởi phép masking động.

### Ví dụ tạo view hiển thị dữ liệu đã che

View là một lựa chọn đơn giản để minh họa cách công bố dữ liệu đã xử lý. Ví dụ sau chỉ hiển thị một phần email và bốn số cuối của số điện thoại:

~~~sql
CREATE OR REPLACE VIEW `analytics.customer_support_view` AS
SELECT
  customer_id,
  CONCAT(
    SUBSTR(email, 1, 1),
    '***@',
    SPLIT(email, '@')[SAFE_OFFSET(1)]
  ) AS email_masked,
  CONCAT('******', RIGHT(phone_number, 4)) AS phone_masked,
  DATE_TRUNC(date_of_birth, YEAR) AS birth_year_group
FROM `restricted_raw.customers`;
~~~

View trên chỉ là ví dụ minh họa và giả định email, phone_number có định dạng hợp lệ. Trong production, cần xử lý giá trị NULL, email sai định dạng và số điện thoại có mã quốc gia. Cấp quyền truy cập view và dataset nguồn theo nguyên tắc least privilege; nếu dùng authorized view, chỉ cấp quyền cần thiết để view đọc bảng nguồn.

View tự viết không tương đương với tính năng dynamic data masking policy của BigQuery. Khi cần quản trị masking tập trung theo cột và vai trò, hãy cấu hình data policy và policy tag theo tài liệu BigQuery. Kiểm thử cả người dùng chỉ được xem dữ liệu masked lẫn người có quyền xem raw data. Không cấp quyền trên dataset nguồn cho nhóm chỉ cần truy cập view.

### Chọn masking trong BigQuery hay de-identification trước khi lưu?

| Nhu cầu | Hướng tiếp cận |
|---|---|
| Người dùng khác nhau cần thấy mức chi tiết khác nhau trong cùng bảng | Data masking policy và column-level security |
| Muốn tạo bộ dữ liệu chia sẻ đã bỏ hoặc biến đổi định danh | De-identify trước khi ghi sang dataset hoặc bucket đích |
| Cần dữ liệu giả lập để phát triển và kiểm thử | Tạo dữ liệu tổng hợp hoặc bản sao đã de-identify; không mặc định view mask là đủ |
| Cần liên kết khách hàng giữa nhiều bảng mà không lộ định danh | Token hóa bằng vault hoặc phép mã hóa xác định có quản lý khóa |
| Cần giới hạn người dùng theo khu vực, tổ chức hoặc nhóm bản ghi | Row-level access policies, kết hợp masking nếu cần |

## 7. Kiến trúc xử lý dữ liệu trên Google Cloud

Một pipeline de-identification nên tách dữ liệu gốc, dữ liệu đã biến đổi và vùng tiêu thụ:

~~~mermaid
flowchart LR
    A[Ứng dụng / Cloud Storage / BigQuery] --> B[Vùng raw hạn chế truy cập]
    B --> C[Sensitive Data Protection]
    C --> D[Inspect và đánh giá findings]
    D --> E[De-identify / masking / tokenization]
    E --> F[Vùng curated đã giảm định danh]
    F --> G[BigQuery / báo cáo / Dataflow / ML]
    H[Cloud KMS và IAM] --> C
    H --> I[Token vault nếu cần khôi phục]
    E --> I
~~~

Các thành phần cần được thiết kế cùng nhau:

1. **Nguồn raw:** Cloud Storage, BigQuery hoặc hệ thống nghiệp vụ. Hạn chế người và service account được đọc dữ liệu gốc.
2. **Inspection:** Sensitive Data Protection kiểm tra infoType và ghi nhận kết quả phù hợp với yêu cầu audit.
3. **Transformation:** áp dụng quy tắc theo trường, infoType và mục đích sử dụng. Không dùng cùng một phép biến đổi cho mọi trường.
4. **Khu vực curated:** chỉ lưu dữ liệu cần thiết cho phân tích hoặc chia sẻ. Áp dụng IAM, retention và phân vùng phù hợp.
5. **Consumer:** BigQuery, Dataflow, dashboard hoặc workload ML chỉ nhận dữ liệu đã xử lý ở mức phù hợp.
6. **Key management:** Cloud KMS bảo vệ khóa dùng cho phép biến đổi mật mã; token vault quản lý ánh xạ nếu cần khôi phục.

Với pipeline lớn hoặc gần thời gian thực, Dataflow có thể điều phối việc đọc, biến đổi và ghi dữ liệu, đồng thời gọi API Sensitive Data Protection theo cách phù hợp với thông lượng và quota. Cần thiết kế retry, dead-letter handling, giới hạn đồng thời và idempotency để dữ liệu không bị mất hoặc xử lý lặp ngoài ý muốn.

## 8. Quản lý khóa, IAM và audit

### Phân tách vai trò

- **Data owner:** quyết định trường nào được xử lý, mục đích sử dụng và mức dữ liệu cần giữ.
- **Privacy/security administrator:** phê duyệt quy tắc, ngưỡng phát hiện, phép biến đổi và thời hạn lưu giữ.
- **Pipeline service account:** chỉ đọc vùng raw cần thiết, gọi API và ghi vùng curated.
- **Key administrator:** quản lý CryptoKey, phiên bản khóa, rotation và quyền IAM.
- **Data consumer:** chỉ truy cập tập dữ liệu đã xử lý hoặc được mask theo vai trò.

Không cấp quyền đọc dữ liệu raw cho toàn bộ nhóm phân tích chỉ để thuận tiện triển khai. Cần giới hạn quyền ở cấp project, dataset, bucket, bảng hoặc cột tùy loại tài nguyên.

### Bảo vệ khóa tokenization

Với phép biến đổi mật mã, khóa cần được quản lý trong Cloud KMS theo chính sách vòng đời phù hợp. Cấp quyền sử dụng khóa cho service agent hoặc workload identity cần thiết ở đúng CryptoKey. Không đưa raw key vào mã nguồn, biến môi trường công khai, tệp cấu hình trong repository hoặc log.

Nếu luân chuyển khóa, cần hiểu ảnh hưởng tới token cũ. Token được tạo bằng key version cũ có thể vẫn cần phiên bản đó để khôi phục. Kế hoạch rotation phải giữ khả năng đọc dữ liệu cũ, hỗ trợ chuyển đổi token nếu cần và có kiểm thử khôi phục. Vô hiệu hóa hoặc phá hủy phiên bản khóa khi dữ liệu vẫn phụ thuộc có thể làm mất khả năng giải mã.

### Audit và giám sát

Theo dõi tối thiểu:

- Ai đọc dữ liệu raw, ai gọi inspect/de-identify và ai đọc vùng curated.
- Thay đổi template, infoType, phép biến đổi và ngưỡng likelihood.
- Ai tạo token, ai yêu cầu re-identify hoặc tra cứu token vault.
- Thay đổi IAM trên bucket, dataset, data policy, policy tag và CryptoKey.
- Lỗi API, quota, thời gian xử lý, số finding và tỷ lệ dữ liệu bị biến đổi.
- Các trường hợp dữ liệu gốc xuất hiện trong log, bản sao tạm hoặc vùng chia sẻ.

Không ghi toàn bộ nội dung finding hoặc bản rõ vào log ứng dụng nếu không cần thiết. Có thể lưu thống kê, loại finding, số lượng và mã tương quan để điều tra mà không làm lộ dữ liệu nhạy cảm.

## 9. Đánh giá nguy cơ tái nhận dạng

Một tập dữ liệu đã loại tên và email vẫn có thể nhận diện được người nếu còn các thuộc tính kết hợp đủ đặc trưng. Ví dụ, ngày sinh chính xác, giới tính, mã bưu chính nhỏ và ngày khám bệnh có thể tạo ra một tổ hợp hiếm. Người có dữ liệu phụ trợ từ nguồn công khai hoặc hệ thống khác có thể đối chiếu và suy ra danh tính.

Các biện pháp giảm rủi ro:

- **Data minimization:** chỉ giữ các trường thực sự cần cho mục đích đã xác định.
- **Generalization:** giảm độ chi tiết của tuổi, ngày, vị trí và nhóm nghề nghiệp.
- **Suppression:** bỏ những bản ghi hoặc thuộc tính quá hiếm để không thể bảo vệ bằng cách tổng quát hóa.
- **Aggregation:** công bố số liệu tổng hợp thay vì từng bản ghi khi mục đích không cần dữ liệu cấp cá nhân.
- **K-anonymity:** đánh giá mỗi tổ hợp quasi-identifier có xuất hiện trong ít nhất k bản ghi hay không.
- **L-diversity và kiểm tra phân phối:** đánh giá thêm mức đa dạng của thuộc tính nhạy cảm trong mỗi nhóm, tránh nhóm có nhiều bản ghi nhưng cùng tiết lộ một thuộc tính.
- **Linkage testing:** thử đối chiếu dữ liệu đã xử lý với nguồn dữ liệu phụ trợ mà người nhận có thể tiếp cận.

K-anonymity và l-diversity là công cụ phân tích rủi ro, không phải bảo đảm tuyệt đối. Cần xem xét bối cảnh phát hành, kích thước nhóm, dữ liệu phụ trợ, khả năng truy vấn lặp và thông tin đã công bố trước đó.

### Ví dụ: bộ dữ liệu khách hàng cho nhóm phân tích

| Trường gốc | Mục đích phân tích | Phép xử lý đề xuất |
|---|---|---|
| customer_id | Nối các giao dịch của cùng khách hàng | Token ổn định theo tenant hoặc mục đích |
| full_name | Không cần cho phân tích | Loại bỏ hoặc thay bằng nhãn |
| email | Chỉ cần phân nhóm người dùng | Bỏ hoặc token hóa nếu cần nối bản ghi |
| phone_number | Nhân viên hỗ trợ cần xác nhận tài khoản | Mask trong giao diện; không đưa số đầy đủ vào dataset phân tích |
| date_of_birth | Phân tích theo nhóm tuổi | Chuyển thành nhóm tuổi hoặc năm sinh |
| postal_code | Phân tích theo vùng | Tổng quát hóa thành vùng rộng hơn |
| transaction_amount | Phân tích doanh thu | Giữ số tiền nếu cần, hoặc bucketing khi chỉ cần phân bố |
| transaction_timestamp | Phân tích xu hướng | Làm tròn theo ngày/tuần nếu thời gian chính xác không cần thiết |

Quy tắc này tạo ra bộ dữ liệu có ích cho phân tích mà giảm số định danh trực tiếp. Trước khi chia sẻ, cần kiểm tra xem tổ hợp age_group, region và transaction_date có làm một khách hàng trở nên duy nhất hay không.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Sensitive Data Protection bỏ sót dữ liệu | InfoType không phù hợp, định dạng riêng hoặc likelihood threshold quá cao | Tạo custom infoType, bổ sung quy tắc ngữ cảnh và kiểm thử bằng mẫu đại diện |
| Quá nhiều false positive | Ngưỡng quá thấp hoặc quy tắc nhận diện quá rộng | Tăng ngưỡng, dùng hotword/exclusion rule và kiểm tra mẫu |
| Gọi API bị từ chối | API chưa bật hoặc principal thiếu IAM | Kiểm tra API, project, location và quyền của service account |
| Phép mã hóa báo lỗi khóa | Key resource sai, key version không hoạt động hoặc thiếu quyền KMS | Kiểm tra CryptoKey, trạng thái phiên bản và quyền của service agent |
| Không khôi phục được token | Dùng hash một chiều, mất vault hoặc context không khớp | Xác định loại biến đổi; khôi phục vault/phiên bản khóa hoặc dùng đúng context |
| Token giống nhau ở nhiều hệ thống ngoài dự kiến | Dùng chung khóa hoặc context cho nhiều miền | Phân tách khóa/context theo tenant, môi trường hoặc mục đích |
| Người dùng vẫn thấy dữ liệu gốc trong BigQuery | Có quyền đọc dataset/bảng nguồn hoặc masking policy chưa áp dụng | Kiểm tra IAM, policy tag, data policy và đường truy cập trực tiếp |
| Bộ dữ liệu đã xử lý vẫn có thể nhận diện người | Còn quasi-identifier hoặc dữ liệu phụ trợ cho phép liên kết | Tổng quát hóa, suppression, aggregation và thực hiện linkage testing |

## 11. Checklist trước khi chia sẻ dữ liệu

- [ ] Xác định mục đích, người nhận và thời hạn sử dụng dữ liệu.
- [ ] Phân loại trường định danh trực tiếp, quasi-identifier và thuộc tính nhạy cảm.
- [ ] Chọn masking, generalization, hashing, tokenization hoặc redaction theo nhu cầu.
- [ ] Kiểm thử Sensitive Data Protection trên dữ liệu đại diện và đo false positive/false negative.
- [ ] Kiểm tra định dạng ngoại lệ, giá trị NULL và dữ liệu nhiều ngôn ngữ.
- [ ] Tách vùng raw và curated; chỉ cấp quyền raw cho principal thực sự cần.
- [ ] Bảo vệ khóa bằng Cloud KMS hoặc token vault; quản lý rotation và khôi phục.
- [ ] Xác minh BigQuery policy tags, data policies, views và quyền truy cập trực tiếp.
- [ ] Kiểm tra log, bản sao tạm, export và dữ liệu trong môi trường phát triển.
- [ ] Đánh giá nguy cơ tái nhận dạng bằng dữ liệu phụ trợ và linkage testing.
- [ ] Ghi lại phiên bản template, cấu hình và người phê duyệt để có thể tái lập quy trình.

## 12. Kết luận

De-identification, masking và tokenization giúp tổ chức sử dụng dữ liệu hữu ích mà giảm việc phơi bày thông tin nhạy cảm. Masking phù hợp khi người dùng chỉ cần xem một phần giá trị; tokenization phù hợp khi cần định danh thay thế hoặc liên kết bản ghi; các phép biến đổi không thể đảo ngược phù hợp khi không cần khôi phục dữ liệu gốc. Sensitive Data Protection hỗ trợ phát hiện và biến đổi dữ liệu, BigQuery cung cấp các lớp kiểm soát truy cập và masking khi truy vấn, còn Cloud KMS bảo vệ khóa cho những phép biến đổi mật mã.

Một quy trình tốt cần xác định mục đích trước khi chọn kỹ thuật, giới hạn quyền truy cập dữ liệu gốc, kiểm thử khả năng phát hiện, bảo vệ khóa và đánh giá nguy cơ tái nhận dạng. Dữ liệu đã được de-identify vẫn cần được quản trị theo bối cảnh sử dụng và yêu cầu bảo vệ dữ liệu của tổ chức.

## Tài liệu tham khảo

- [Sensitive Data Protection documentation](https://cloud.google.com/sensitive-data-protection/docs)
- [Inspect and de-identify sensitive data](https://cloud.google.com/sensitive-data-protection/docs/inspecting-and-risk-analysis)
- [De-identification transformations](https://cloud.google.com/sensitive-data-protection/docs/deidentify-sensitive-data)
- [De-identify and re-identify content](https://cloud.google.com/sensitive-data-protection/docs/deidentify-reidentify)
- [BigQuery data masking introduction](https://cloud.google.com/bigquery/docs/column-data-masking-intro)
- [BigQuery column-level security](https://cloud.google.com/bigquery/docs/column-level-security-intro)
- [Cloud KMS documentation](https://cloud.google.com/kms/docs)
