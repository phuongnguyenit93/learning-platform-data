# Chuẩn bị dữ liệu và quản lý môi trường huấn luyện

Trong chương **AI và học máy trên OCI** của module **Oracle Cloud Infrastructure**, chuẩn bị huấn luyện bao gồm hai phần gắn chặt với nhau: tạo dữ liệu phù hợp với bài toán và cung cấp môi trường thực thi có thể quản lý, tái lập.

Một notebook chạy được hôm nay chưa đủ làm bằng chứng rằng quy trình sẽ chạy lại trên một OCI Data Science Job, bằng một principal khác hoặc sau khi thư viện được cập nhật. Cần biết dữ liệu nào đã được dùng, mã nguồn nào xử lý dữ liệu, môi trường nào thực thi và tài nguyên OCI nào được phép truy cập.

Bài học tập trung vào các đầu ra sau:

- Một phiên bản dữ liệu có nguồn gốc, hợp đồng và cách chia tập rõ ràng.
- Quy trình tiền xử lý tránh dùng thông tin chưa tồn tại tại thời điểm dự đoán.
- Môi trường huấn luyện được lựa chọn, kiểm tra và lưu phiên bản.
- Cấu hình chuyển từ notebook sang job, có phân quyền, mạng, giám sát và kiểm soát chi phí.

## 1. Đơn vị cần tái lập là toàn bộ lần huấn luyện

Có thể mô tả một lần huấn luyện bằng bộ thông tin:

~~~text
Lần huấn luyện =
    phiên bản dữ liệu
  + phiên bản mã nguồn
  + cấu hình tiền xử lý và chia tập
  + môi trường phần mềm
  + tài nguyên và cấu hình thực thi
  + thông tin truy vết lần chạy
~~~

Hai lần chạy cùng file mã nguồn vẫn có thể khác nhau nếu cùng đọc đường dẫn dữ liệu “mới nhất”, tự cài thư viện không khóa phiên bản hoặc sử dụng cách chia tập khác.

| Thành phần | Thông tin nên ghi nhận |
| --- | --- |
| Dữ liệu | Dataset ID, manifest, nguồn, thời điểm chốt, phiên bản từng object hoặc checksum |
| Mã nguồn | Git commit hoặc định danh gói mã, entrypoint |
| Tiền xử lý | Schema, danh sách đặc trưng, quy tắc làm sạch, phiên bản pipeline |
| Chia tập | Khoảng thời gian, quy tắc theo nhóm, seed nếu có |
| Môi trường | Python, thư viện, môi trường Conda hoặc image đã được chấp nhận |
| Thực thi | Shape, CPU/GPU, vùng, cấu hình luồng xử lý và giới hạn thời gian |
| Truy vết | Run ID hoặc job run OCID, log, kết quả kiểm tra và nơi lưu đầu ra |

Không ghi mật khẩu, token hoặc private key vào bản ghi tái lập. Với dữ liệu nhạy cảm, chỉ lưu định danh và metadata cần thiết trong những nơi có quyền truy cập phù hợp.

## 2. Luồng chuẩn bị dữ liệu và môi trường trên OCI

Một cách tổ chức là tách nguồn nghiệp vụ, dữ liệu đã đóng phiên bản, môi trường phần mềm và đầu ra của từng lần chạy.

~~~mermaid
flowchart TD
    A["Oracle Database, tệp và nguồn nghiệp vụ"] --> B["Trích xuất có thời điểm chốt"]
    B --> C["Object Storage: dữ liệu gốc có phiên bản"]
    C --> D["Kiểm tra, chuẩn hóa và xác định cách chia tập"]
    D --> E["Dataset release và manifest"]
    E --> F["Data Science Notebook: khám phá và thử nghiệm"]
    G["Môi trường Conda được chọn"] --> F
    F --> H["Môi trường được publish lên Object Storage"]
    E --> I["Data Science Job: thực thi có tham số"]
    H --> I
    J["Mã nguồn và cấu hình có phiên bản"] --> I
    I --> K["Artifact, báo cáo và log theo run ID"]
~~~

Đây là kiến trúc minh họa, không phải một pipeline có sẵn tự nối các dịch vụ.

Notebook hỗ trợ khám phá; Object Storage giữ dữ liệu và gói môi trường; Job thực thi quy trình đã tách khỏi trạng thái tương tác. Nếu dữ liệu lớn vượt khả năng xử lý trên một máy, có thể cần bước xử lý phân tán, nhưng vẫn phải giữ hợp đồng dữ liệu và khả năng truy vết.

## 3. Xác định bài toán trước khi lấy dữ liệu

### 3.1. Ví dụ xuyên suốt: dự đoán đơn hàng giao trễ

Giả sử ứng dụng cần dự đoán rủi ro giao trễ **ngay tại thời điểm xác nhận đơn**.

Cần quyết định rõ:

- Một bản ghi tương ứng với một đơn hàng hay một kiện giao hàng?
- “Giao trễ” được so với mốc cam kết nào?
- Đơn bị hủy hoặc chưa đủ thời gian quan sát được xử lý thế nào?
- Những trường nào đã biết khi ứng dụng phải dự đoán?
- Kết quả mô hình phục vụ điều chỉnh vận hành hay chỉ xếp thứ tự kiểm tra?

Nếu một đơn có nhiều kiện nhưng dữ liệu được gán nhãn theo cả đơn, việc nhân bản nhãn cho mọi kiện cần được giải thích và đánh giá. Sai đơn vị quan sát có thể làm tập dữ liệu lớn lên mà không tăng lượng thông tin độc lập.

### 3.2. Tách thời điểm dự đoán, thời điểm sự kiện và thời điểm biết nhãn

Ba mốc thời gian cần phân biệt:

| Mốc | Ý nghĩa trong ví dụ |
| --- | --- |
| **Prediction time** | Thời điểm xác nhận đơn, khi phải tính điểm |
| **Event time** | Thời điểm sự kiện thực tế xảy ra, chẳng hạn hoàn tất giao |
| **Label availability time** | Thời điểm hệ thống đã có đủ thông tin để xác định nhãn |

Một sự kiện có thể xảy ra hôm qua nhưng được đồng bộ về kho dữ liệu hôm nay. Nếu mô phỏng dự đoán tại hôm qua, không được dùng bản ghi chưa có mặt trong hệ thống lúc đó.

Với đặc trưng tổng hợp như “tỷ lệ đơn trễ của khách hàng trong 30 ngày”, chỉ sử dụng những đơn và nhãn đã khả dụng trước thời điểm dự đoán. Tính tổng hợp từ toàn bộ bảng rồi nối lại vào mọi thời điểm lịch sử có thể đưa thông tin tương lai vào mô hình.

### 3.3. Viết hợp đồng dữ liệu

Hợp đồng dữ liệu mô tả những điều đầu vào phải đáp ứng.

| Trường minh họa | Kiểu hoặc điều kiện | Vai trò |
| --- | --- | --- |
| **order_id** | Chuỗi, không rỗng, duy nhất theo đơn vị quan sát | Định danh, không mặc định là đặc trưng |
| **prediction_time** | Timestamp có quy ước múi giờ | Chia tập và đối chiếu thời gian |
| **amount** | Số, đơn vị tiền tệ nhất quán | Đặc trưng nếu đã biết khi xác nhận |
| **distance_km** | Số không âm, tính từ thông tin sẵn có lúc dự đoán | Đặc trưng |
| **warehouse_code** | Mã kho hợp lệ hoặc giá trị thiếu được quy định | Đặc trưng phân loại |
| **destination_zone** | Nhóm khu vực đã chuẩn hóa | Đặc trưng phân loại |
| **late_delivery** | Nhãn 0/1 theo quy tắc đã thống nhất | Biến mục tiêu |
| **label_available_at** | Thời điểm nhãn có thể được sử dụng | Kiểm soát nhãn và backtest |

Không đưa trực tiếp tên, điện thoại hoặc địa chỉ đầy đủ vào dữ liệu huấn luyện nếu bài toán chỉ cần khu vực giao. Nếu cần liên kết theo khách hàng, cân nhắc định danh thay thế có kiểm soát; việc thay định danh không tự làm mọi dữ liệu trở thành vô danh.

## 4. Thu thập và đóng phiên bản dữ liệu

### 4.1. Trích xuất từ Oracle Database hoặc nguồn đang thay đổi

Trước khi xuất dữ liệu, xác định:

1. Bảng hoặc view nào là nguồn có thẩm quyền.
2. Cột cần lấy và điều kiện lọc theo thời gian.
3. Cơ chế đọc nhất quán phù hợp với nguồn.
4. Trạng thái xử lý dữ liệu đến muộn hoặc bản ghi bị sửa.
5. Cách đối chiếu số bản ghi và tổng kiểm soát sau xuất.

Nếu xuất bảng đơn hàng vào một thời điểm, rồi xuất trạng thái giao sau nhiều giờ, hai phần có thể phản ánh trạng thái nghiệp vụ khác nhau. Cần thiết kế snapshot hoặc cơ chế đối chiếu nhất quán của nguồn; tên thư mục chứa ngày xuất không tạo ra tính nhất quán đó.

Dùng tài khoản cơ sở dữ liệu chỉ có quyền đọc cần thiết. Quyền OCI IAM truy cập tài nguyên không tự thay thế quyền truy vấn bên trong Oracle Database; kết nối, TLS, phương thức xác thực và quyền database cần được cấu hình riêng.

### 4.2. Phân biệt dữ liệu gốc, dữ liệu đã kiểm tra và dữ liệu huấn luyện

Ví dụ bố cục object do dự án tự thiết kế:

~~~text
datasets/delivery-delay/
  raw/extract-2026-09-30/...
  releases/ds-2026-09-r1/
    manifest.json
    train/...
    validation/...
    test/...
    quality-report.json

environments/delivery-training/env-r3/...

runs/delivery-delay/run-0042/
  run-manifest.json
  metrics.json
  preprocessing-artifact/...
  model-artifact/...
~~~

Các prefix này giúp tổ chức tên object. Chúng không tự tạo thư mục có quyền riêng hoặc ranh giới bảo mật. Phạm vi bucket, policy và điều kiện truy cập vẫn cần được thiết kế.

Dữ liệu gốc nên được giữ theo chính sách để truy lại nguồn; dữ liệu lỗi đưa vào vùng cách ly có lý do; dataset release được phát hành sau khi kiểm tra và xác định cách chia tập.

### 4.3. Dùng manifest để chỉ rõ bộ dữ liệu

Manifest là bản mô tả **do ứng dụng quy định**, không phải schema bắt buộc của OCI Data Science.

~~~json
{
  "datasetId": "delivery-delay-ds-2026-09-r1",
  "schemaVersion": "delivery-schema-v2",
  "labelRuleVersion": "late-delivery-rule-v1",
  "extractionCutoff": "2026-09-30T00:00:00Z",
  "splitRuleVersion": "time-split-v1",
  "objects": [
    {
      "split": "train",
      "objectName": "releases/ds-2026-09-r1/train/part-0001.parquet",
      "versionId": "THAY_BANG_VERSION_ID_THUC",
      "sha256": "THAY_BANG_SHA256_THUC",
      "rowCount": 120000
    }
  ]
}
~~~

Số bản ghi trong ví dụ là giả lập. Manifest thực tế cần liệt kê đầy đủ các phần của cả train, validation và test, kèm namespace, bucket hoặc thông tin định vị tương đương.

Quy trình phát hành có thể tải đủ object, kiểm tra chúng, rồi công bố manifest cuối cùng. Worker đọc dữ liệu chỉ coi release sẵn sàng khi manifest đã hoàn tất. Không giả định việc tải nhiều object tạo thành một giao dịch nguyên tử.

### 4.4. Object versioning hỗ trợ truy vết nhưng không thay thế quản trị release

Object Storage có versioning ở cấp bucket và version ID cho từng phiên bản object. Các phiên bản cũ cũng có thể phát sinh phí lưu trữ. [Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Nếu chỉ ghi object name, lần chạy sau có thể đọc bản mới nhất khác với bản đã huấn luyện. Khi cần đúng phiên bản, lưu version ID và dùng thao tác đọc hỗ trợ phiên bản đó, hoặc sử dụng quy ước tên release không ghi đè kết hợp kiểm tra checksum.

Versioning không bảo đảm người có quyền không thể xóa vĩnh viễn một phiên bản. Nó cũng không làm một tập nhiều object trở thành snapshot nghiệp vụ nhất quán. Chính sách bảo vệ dữ liệu và chính sách phát hành dataset là các quyết định bổ sung.

## 5. Kiểm tra dữ liệu trước khi cấp tài nguyên huấn luyện lớn

Nên thực hiện kiểm tra rẻ trước để phát hiện đầu vào sai sớm.

| Nhóm kiểm tra | Ví dụ | Cách xử lý gợi ý |
| --- | --- | --- |
| Cấu trúc | Thiếu cột bắt buộc, sai kiểu | Dừng phát hành release |
| Khóa | Một order_id xuất hiện nhiều lần | Kiểm tra đơn vị quan sát hoặc quy tắc hợp nhất |
| Giá trị thiếu | Thiếu nhãn hoặc thời điểm dự đoán | Cách ly; không tự suy diễn nhãn |
| Miền giá trị | Khoảng cách âm, mã vùng không hợp lệ | Báo lỗi hoặc xử lý theo quy tắc có phiên bản |
| Thời gian | Feature chỉ xuất hiện sau prediction time | Loại khỏi đặc trưng hoặc sửa cách xây dựng |
| Quan hệ | Đơn không có kho nguồn trong danh mục | Đối chiếu nguồn và thời điểm hiệu lực |
| Phân bố | Tỷ lệ nhãn hoặc giá trị thiếu thay đổi mạnh | Cảnh báo và xem xét trước khi tiếp tục |
| Dữ liệu nhạy cảm | Xuất hiện số điện thoại ngoài hợp đồng | Chặn phát hành và xử lý theo chính sách |

Phân biệt **lỗi cứng** với **cảnh báo**. Thiếu toàn bộ cột nhãn là lỗi cấu trúc; tỷ lệ một khu vực tăng có thể là thay đổi kinh doanh hợp lệ. Không tự loại mọi giá trị hiếm hoặc ngoại lệ vì chúng có thể là đối tượng mô hình cần nhận biết.

Một báo cáo chất lượng nên lưu số bản ghi đầu vào, số bị loại theo từng lý do, phân bố nhãn và các kiểm tra đã chạy. Không ghi toàn bộ dòng lỗi nhạy cảm vào log chung.

Nếu chọn ngưỡng cảnh báo, cần dựa trên dữ liệu lịch sử và yêu cầu nghiệp vụ. Một tỷ lệ phần trăm trong ví dụ học tập không phải ngưỡng mặc định cho mọi dự án.

## 6. Chia train, validation và test theo tình huống triển khai

### 6.1. Vai trò của ba tập

- **Train:** học tham số của bước tiền xử lý và mô hình.
- **Validation:** chọn cấu hình, ngưỡng quyết định và phương án ứng viên.
- **Test:** đánh giá cuối theo quy trình đã chốt, hạn chế dùng lặp lại để chọn mô hình.

Nếu liên tục chọn đặc trưng hoặc cấu hình dựa trên điểm test, tập test dần trở thành dữ liệu phục vụ lựa chọn.

### 6.2. Không mặc định chia ngẫu nhiên

| Tình huống | Cách chia cần xem xét |
| --- | --- |
| Bản ghi gần độc lập, không có trật tự thời gian quan trọng | Chia ngẫu nhiên, cân nhắc stratification cho phân loại |
| Nhiều ảnh hoặc bản ghi từ cùng đối tượng | Chia theo nhóm để phản ánh khả năng tổng quát hóa cần đo |
| Dự đoán các thời điểm tương lai | Chia theo thời gian |
| Nhãn có độ trễ hoặc cửa sổ quan sát chồng lấn | Chia theo thời gian kèm khoảng cách hoặc điều kiện loại phù hợp |
| Muốn kiểm tra trên khách hàng hoặc thiết bị chưa từng gặp | Giữ riêng các nhóm thực thể đó |

Các công cụ như TimeSeriesSplit hỗ trợ chia dữ liệu theo thứ tự thời gian, nhưng vẫn phải thiết kế cửa sổ, độ trễ nhãn và đặc trưng đúng bài toán. [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

Trong ví dụ đơn hàng, một cách mô tả ban đầu là train trên giai đoạn cũ, validation trên giai đoạn sau và test trên giai đoạn mới hơn. Tuy nhiên, nếu mô phỏng “huấn luyện tại ngày X rồi dự đoán từ ngày X”, train chỉ được chứa những nhãn đã khả dụng tại ngày X. Có thể cần khoảng cách giữa các cửa sổ hoặc loại những đơn chưa biết nhãn tại mốc đó.

Một khách hàng xuất hiện ở cả giai đoạn cũ và mới có thể phù hợp nếu hệ thống sẽ dự đoán tiếp cho khách hàng đang có. Nếu mục tiêu là dự đoán cho khách hàng hoàn toàn mới, cách chia phải thể hiện yêu cầu khác đó.

### 6.3. Xử lý bản sao và mất cân bằng nhãn đúng vị trí

Các bản sao của cùng một ảnh, tài liệu hoặc sự kiện cần được gán cùng nhóm chia khi phù hợp. Giữ một bản ở train và bản gần như giống hệt ở test có thể tạo kết quả quá lạc quan.

Oversampling hoặc tạo mẫu tổng hợp chỉ thực hiện trong phần train của từng lần đánh giá. Validation và test nên giữ phân bố phản ánh môi trường sử dụng. Trọng số lớp hoặc kỹ thuật cân bằng cũng là cấu hình cần ghi lại.

Seed giúp lặp lại một thao tác ngẫu nhiên, nhưng không thay thế việc lưu quy tắc chia và danh sách hoặc định danh bản ghi thuộc từng tập.

## 7. Xây tiền xử lý tránh rò rỉ dữ liệu

### 7.1. Phân biệt quy tắc cố định với phép biến đổi học từ dữ liệu

Quy tắc chuẩn hóa đã được xác định trước, như đổi đơn vị từ mét sang kilômét, khác với tính trung vị từ dữ liệu để điền giá trị thiếu.

Những bước học thống kê từ dữ liệu phải được fit trên train, sau đó dùng cùng trạng thái để transform validation, test và dữ liệu suy luận. Pipeline giúp giữ tiền xử lý và mô hình đi cùng nhau. [Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html).

Các thao tác cần chú ý gồm điền thiếu, scaling, chọn đặc trưng, PCA và mã hóa dùng nhãn. Khi cross-validation, các bước học từ dữ liệu phải nằm trong từng fold huấn luyện.

Không coi việc “chỉ dùng các cột X, chưa dùng y” là bằng chứng không có leakage. Phân bố của tập đánh giá cũng có thể bị đưa vào bước tiền xử lý.

### 7.2. Ví dụ pipeline với dữ liệu bảng

Đoạn Python dưới đây dành cho môi trường có pandas và scikit-learn tương thích. Biến **train** và **validation** là các DataFrame đã được đọc từ release, kiểm tra và chia đúng quy tắc. Ví dụ minh họa cách giữ bước tiền xử lý cùng mô hình; không phải dự án huấn luyện hoàn chỉnh.

~~~python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric_columns = ["amount", "distance_km"]
category_columns = ["warehouse_code", "destination_zone"]
feature_columns = numeric_columns + category_columns
target_column = "late_delivery"

numeric_pipeline = Pipeline([
    ("impute", SimpleImputer(strategy="median")),
    ("scale", StandardScaler()),
])

category_pipeline = Pipeline([
    ("impute", SimpleImputer(strategy="most_frequent")),
    ("encode", OneHotEncoder(handle_unknown="ignore")),
])

preprocess = ColumnTransformer([
    ("numeric", numeric_pipeline, numeric_columns),
    ("category", category_pipeline, category_columns),
])

training_pipeline = Pipeline([
    ("preprocess", preprocess),
    ("classifier", LogisticRegression(max_iter=1000)),
])

training_pipeline.fit(
    train[feature_columns],
    train[target_column],
)

validation_probability = training_pipeline.predict_proba(
    validation[feature_columns]
)[:, 1]
~~~

Các điểm cần nhận ra:

- Chỉ lời gọi fit trên train học trung vị, giá trị phổ biến, thống kê scaling và danh mục mã hóa.
- Khi gọi predict_proba, pipeline sử dụng trạng thái đã học để xử lý validation.
- Danh sách đặc trưng loại định danh, nhãn và thời điểm biết nhãn ra khỏi đầu vào mô hình.
- Nhãn phải được kiểm tra là 0/1 và train có đủ lớp cho ví dụ này.
- Chính sách giá trị thiếu và cột phân loại cần phù hợp dữ liệu thực tế; không mặc định điền theo giá trị phổ biến luôn đúng.

Khi lưu artifact, cần giữ pipeline đã fit hoặc các thành phần tiền xử lý tương đương cùng schema đầu vào. Nếu chỉ lưu classifier rồi viết lại mã xử lý ở ứng dụng, hai luồng có thể lệch nhau.

### 7.3. Với dữ liệu khác, hợp đồng vẫn cần cụ thể

| Dữ liệu | Điều cần chốt trước huấn luyện |
| --- | --- |
| Văn bản | Encoding, quy tắc làm sạch, ngôn ngữ, nhãn và bộ tokenizer có phiên bản |
| Ảnh | Định dạng, kích thước, quy tắc nhãn, ảnh trùng và augmentation chỉ ở train |
| Chuỗi thời gian | Tần suất, múi giờ, dữ liệu đến muộn, cửa sổ quá khứ và horizon |
| Dữ liệu fine-tuning mô hình ngôn ngữ | Cấu trúc mẫu, quyền sử dụng, dữ liệu nhạy cảm, độ dài và mẫu trùng giữa các tập |

Không áp dụng cùng một phép “làm sạch” cho mọi nguồn. Xóa dấu tiếng Việt hoặc dấu câu có thể làm mất thông tin cần thiết cho một tác vụ văn bản.

## 8. Môi trường huấn luyện gồm nhiều lớp

Cần phân biệt phần mềm Python với toàn bộ môi trường thực thi.

| Lớp | Ví dụ | Rủi ro nếu chỉ ghi tên thư viện |
| --- | --- | --- |
| Runtime | Python và các thư viện native | Không tương thích phiên bản hoặc ABI |
| Dependency | pandas, scikit-learn, framework, OCI SDK | API thay đổi, kết quả khác |
| Hệ thống | Hệ điều hành, kiến trúc CPU, thư viện hệ thống | Gói cài trên Windows không chạy trên Linux |
| Tăng tốc | GPU, driver, CUDA và thư viện liên quan | Framework không sử dụng được GPU |
| Tài nguyên | OCPU, RAM, bộ nhớ GPU, disk | Out-of-memory hoặc hết dung lượng |
| Tích hợp OCI | Principal, policy, subnet, route | Có thể import thư viện nhưng không đọc được dữ liệu |
| Cấu hình | Seed, số luồng, tham số tác vụ | Khó giải thích khác biệt giữa các lần chạy |

Conda đóng gói dependency, không cấp IAM policy và không tạo đường mạng. Một gói môi trường cũng không tự thay thế driver GPU của hạ tầng.

Mục tiêu tái lập cần được định nghĩa. Tái lập được quy trình và chất lượng trong sai số chấp nhận được không luôn đồng nghĩa kết quả số học giống từng bit trên mọi CPU/GPU.

## 9. Chọn và sử dụng Conda trong OCI Data Science Notebook

### 9.1. Ba khái niệm thường bị nhầm

OCI Data Science có môi trường Conda do dịch vụ cung cấp, môi trường đã cài trong notebook và môi trường đã publish trong Object Storage. Environment Explorer hỗ trợ xem các nhóm này. [Viewing the Conda Environments](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_viewing.htm).

| Khái niệm | Ý nghĩa thực hành |
| --- | --- |
| **Data Science Conda environment** | Môi trường do dịch vụ cung cấp để lựa chọn |
| **Installed environment** | Bản đang được cài trong notebook session |
| **Published environment** | Bản đã được đóng gói và lưu trong bucket để tái sử dụng |

Cài một môi trường không có nghĩa notebook hiện tại đã dùng đúng kernel của nó. Cập nhật bản installed cũng không tự sửa bản published hoặc cấu hình của một job.

### 9.2. Bắt đầu từ môi trường phù hợp

Ưu tiên môi trường CPU cho thử nghiệm dữ liệu bảng nhỏ. Chỉ chọn GPU khi framework và workload có thể sử dụng hiệu quả tài nguyên đó.

Oracle cung cấp công cụ **odsc conda** trong notebook để quản lý môi trường. Mỗi môi trường có thể gắn với kernel JupyterLab riêng. [Conda Environments](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_understand_environments.htm).

Các lệnh minh họa sau chạy trong **terminal của OCI Data Science Notebook**, với slug lấy từ Environment Explorer hoặc danh sách thực tế:

~~~bash
odsc conda -h
odsc conda list

OCI_DS_ENV_SLUG='THAY_BANG_SLUG_DA_XAC_NHAN'
odsc conda install --slug "$OCI_DS_ENV_SLUG"
~~~

Không suy đoán slug từ tên thư viện hoặc một ví dụ cũ. Sau cài đặt, chọn đúng kernel và khởi động lại kernel nếu quá trình thay đổi dependency yêu cầu.

Môi trường cài bằng luồng được hỗ trợ nằm trên block volume dưới **/home/datascience/conda** và có thể còn sau deactivate/reactivate. Oracle khuyến cáo tránh cài thêm vào môi trường Python cơ sở vì thay đổi ở đó có thể không được giữ sau reactivation. [Installing Conda Environments](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_installing.htm).

### 9.3. Xác nhận interpreter đang dùng

Trong kernel đã chọn, có thể kiểm tra metadata được phép công khai:

~~~python
import platform
import sys
from importlib.metadata import version

print({
    "python": platform.python_version(),
    "interpreter": sys.executable,
    "machine": platform.machine(),
    "scikit_learn": version("scikit-learn"),
    "oci_sdk": version("oci"),
})
~~~

Ví dụ yêu cầu các package được liệt kê đã cài. Nếu thiếu package, lỗi metadata cũng là tín hiệu cần xử lý trước khi huấn luyện.

Khi một lệnh cài thành công trong terminal nhưng notebook vẫn báo thiếu thư viện, hãy đối chiếu interpreter của terminal với kernel trước. Việc cài lại nhiều lần bằng các công cụ khác nhau có thể làm môi trường khó quản lý hơn.

### 9.4. Tạo môi trường riêng khi cần

Nếu môi trường có sẵn không đáp ứng, có thể tạo môi trường từ file đặc tả Conda bằng odsc conda create. Công cụ mặc định bổ sung các thành phần tích hợp cần thiết; tùy chọn tạo môi trường rỗng cần được cân nhắc vì có thể thiếu kernel JupyterLab. [Creating a Custom Conda Environment](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_create_conda_env.htm).

Nên thử thay đổi trên một bản môi trường riêng, ghi lại dependency và kiểm tra trước khi dùng cho các lần chạy chính thức. Không tự nâng cấp toàn bộ thư viện chỉ để giải quyết một package thiếu.

## 10. Đóng phiên bản và publish môi trường huấn luyện

### 10.1. Giữ cả đặc tả và bản đã giải quyết dependency

Có hai loại bằng chứng bổ sung cho nhau:

- **Đặc tả mong muốn:** các thư viện trực tiếp, phiên bản hoặc ràng buộc và nguồn package.
- **Trạng thái thực tế:** dependency đã được giải quyết, build, kiến trúc và gói môi trường hoặc image được sử dụng.

Một file chỉ ghi tên package mà không giới hạn phiên bản có thể được giải quyết ra môi trường khác vào tháng sau. Ngược lại, đặc tả quá gắn với một nền tảng có thể không chuyển sang nền tảng khác.

Conda hỗ trợ nhiều định dạng export; định dạng explicit thường gắn với nền tảng, trong khi đặc tả môi trường phục vụ chia sẻ có đặc tính khác. Chọn định dạng theo mục tiêu và phiên bản công cụ đang cài. [Conda export](https://docs.conda.io/projects/conda/en/stable/commands/export.html).

Một danh sách pip đơn thuần không mô tả toàn bộ package Conda, thư viện hệ thống hoặc driver. Nếu sử dụng cả pip và Conda, phải ghi lại hai phần và cách dựng môi trường.

### 10.2. Publish lên Object Storage

Publishing đóng gói môi trường installed và tải lên bucket được cấu hình. Có thể sử dụng resource principal với quyền phù hợp. [Publishing a Conda Environment](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_publishs_object.htm).

Ví dụ lệnh trong terminal notebook, sau khi đã thay giá trị minh họa bằng bucket, namespace và slug thực tế:

~~~bash
OCI_DS_ENV_BUCKET='ml-environments'
OCI_DS_NAMESPACE='THAY_BANG_NAMESPACE'
OCI_DS_ENV_SLUG='THAY_BANG_SLUG_DA_XAC_NHAN'

odsc conda init -b "$OCI_DS_ENV_BUCKET" -n "$OCI_DS_NAMESPACE" -a resource_principal
odsc conda publish -s "$OCI_DS_ENV_SLUG"
~~~

Sau publish, ghi lại **đúng object name hoặc URI kết quả**, phiên bản release, metadata package và checksum nếu quy trình sử dụng. Không suy ra tên file đóng gói chỉ từ slug.

Một quy trình release môi trường nên có các bước:

1. Tạo hoặc cài môi trường ứng viên.
2. Thêm dependency cần thiết từ nguồn được chấp thuận.
3. Kiểm tra import, đọc dữ liệu mẫu và chạy một luồng nhỏ.
4. Publish bản ứng viên.
5. Cài hoặc dùng bản published trong ngữ cảnh sạch.
6. Ghi nhận bản được chấp nhận và giữ nguyên nó cho các run tham chiếu.

Nếu tiếp tục sửa môi trường trong notebook, cần phát hành phiên bản mới. Bản published là ảnh chụp của trạng thái đã đóng gói, không phải liên kết đồng bộ với kernel đang chạy.

### 10.3. Khi nào cân nhắc container?

Container phù hợp khi cần quản lý rõ hơn thư viện hệ thống, công cụ native hoặc runtime đặc thù. Với OCI Data Science Jobs, Bring Your Own Container có cấu hình riêng; nên tham chiếu image bằng digest được hỗ trợ thay vì chỉ dựa vào tag có thể đổi. [Creating a Job](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-create.htm).

Container không tự cung cấp quyền đọc dataset và cũng không bảo đảm tương thích GPU. Kiểm tra nền tảng, driver, registry, quyền kéo image và region theo cấu hình dịch vụ.

## 11. Cấp quyền và mạng cho dữ liệu, môi trường và đầu ra

### 11.1. Notebook và Job có danh tính tài nguyên khác nhau

Linux user trong notebook không tự có quyền OCI IAM. Resource principal cho phép notebook xác thực bằng danh tính tài nguyên mà không phải lưu API key cá nhân trong mã. Vẫn cần policy để tài nguyên truy cập dịch vụ khác. [Using Notebook Sessions to Build and Train Models](https://docs.oracle.com/en-us/iaas/Content/data-science/using/use-notebook-sessions.htm).

Một notebook đọc được bucket không chứng minh job run cũng đọc được. Dynamic group phải bao gồm đúng loại tài nguyên và compartment được cho phép; phạm vi thành viên cần được giới hạn theo môi trường.

Ví dụ policy chỉ minh họa quyền đọc cho một dynamic group đã được cấu hình:

~~~text
Allow dynamic-group MlTrainingRuns to read objects in compartment ml-data where target.bucket.name='training-datasets'

Allow dynamic-group MlTrainingRuns to read objects in compartment ml-platform where target.bucket.name='ml-environments'
~~~

Hai statement này không cấp quyền ghi đầu ra, không cấp quyền đọc mọi bucket và không cấp quyền truy vấn bên trong database. Quyền cho job run tải published Conda từ Object Storage được mô tả trong [Data Science Policies](https://docs.oracle.com/en-us/iaas/Content/data-science/using/policies.htm).

Nên tách quyền đọc dataset, đọc môi trường, ghi kết quả và quản lý tài nguyên. Nếu job cần ghi artifact, cấp đúng quyền ghi ở nơi xuất kết quả; không vì một lỗi ghi mà mở quyền quản lý toàn tenancy.

### 11.2. Kiểm tra kết nối theo từng đích

| Đích | Điều cần xác minh |
| --- | --- |
| Object Storage | IAM, endpoint, DNS và route phù hợp |
| Database private | Kết nối từ subnet, NSG/security list, TLS và quyền database |
| Nguồn package bên ngoài | Egress được phép, proxy hoặc nguồn package nội bộ |
| Container Registry | Quyền đọc repo, kết nối và vị trí registry phù hợp |
| Vault hoặc nơi quản lý bí mật | Principal được phép lấy đúng bí mật cần thiết |

Với custom networking, phải cung cấp đường mạng phù hợp cho việc truy cập môi trường Conda và dữ liệu. NAT và service gateway có vai trò khác nhau: service gateway phục vụ các OCI service được hỗ trợ; NAT phục vụ luồng ra Internet theo cấu hình. [Conda Environments — Networking](https://docs.oracle.com/en-us/iaas/Content/data-science/using/conda_understand_environments.htm).

Một private subnet không tự có khả năng tải package từ Internet. Ngược lại, kết nối mạng thông không thay thế policy cho Object Storage.

### 11.3. Không đóng gói bí mật vào artifact

Giữ mật khẩu, wallet hoặc thông tin nhạy cảm ngoài gói huấn luyện khi có thể; lấy theo cơ chế được môi trường hỗ trợ với quyền tối thiểu. Với wallet cần cho database, bảo vệ cả nơi lưu, quyền đọc và bản sao tạm.

Không in toàn bộ biến môi trường hoặc tệp cấu hình xác thực để chẩn đoán lỗi. Chỉ log metadata đã được duyệt như phiên bản thư viện, run ID, số bản ghi và trạng thái kiểm tra.

## 12. Chuyển quy trình từ notebook sang OCI Data Science Job

### 12.1. Loại bỏ phụ thuộc vào trạng thái tương tác

Trước khi đóng gói:

- Tách mã đọc dữ liệu, kiểm tra, tiền xử lý và huấn luyện thành các hàm hoặc module.
- Đưa đường dẫn, seed và tham số vào cấu hình.
- Không dựa vào biến chỉ tồn tại do một cell cũ đã chạy.
- Không hard-code đường dẫn riêng của notebook cho dataset hoặc artifact.
- Để lỗi đầu vào làm lần chạy thất bại rõ ràng, thay vì âm thầm huấn luyện trên dữ liệu rỗng.

Một entrypoint nên đọc cấu hình, xác thực đầu vào, thực thi quy trình và lưu kết quả theo run ID. Nếu chạy lại cùng đầu vào, không ghi đè âm thầm các kết quả đã dùng làm bằng chứng.

### 12.2. Chọn rõ môi trường cho Job

Job có thể dùng Data Science Conda của dịch vụ hoặc custom Conda đã publish. Không mặc định job tự kế thừa môi trường notebook. Luồng dùng Conda cần khai báo môi trường tương ứng; tài liệu Oracle nêu rằng không có Conda mặc định nếu không cấu hình. [Other Ways to Run Jobs](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-other.htm).

Ví dụ các cặp biến môi trường cho **published Conda**, trình bày bằng YAML để dễ đọc:

~~~yaml
CONDA_ENV_TYPE: published
CONDA_ENV_BUCKET: ml-environments
CONDA_ENV_NAMESPACE: THAY_BANG_NAMESPACE
CONDA_ENV_OBJECT_NAME: THAY_BANG_OBJECT_NAME_CHINH_XAC
CONDA_ENV_REGION: THAY_BANG_REGION_CHUA_MOI_TRUONG
JOB_RUN_ENTRYPOINT: src/train.py

TRAINING_DATA_MANIFEST_URI: THAY_BANG_URI_MANIFEST
TRAINING_OUTPUT_PREFIX: runs/delivery-delay/run-0042/
TRAINING_SEED: "42"
~~~

Đây là ví dụ cấu hình, không phải lệnh tạo tài nguyên. Các tên **CONDA_ENV_...** và **JOB_RUN_ENTRYPOINT** thuộc cơ chế dịch vụ; ba biến **TRAINING_...** cuối do ứng dụng tự quy định và phải được mã huấn luyện đọc.

Với artifact zip hoặc tar, entrypoint phải khớp cấu trúc thực tế bên trong archive. Các thuộc tính môi trường được mô tả trong [Job Environment Variables](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-env-vars.htm).

Nếu chọn service Conda, sử dụng loại **service** cùng slug đã xác minh theo tài liệu, thay cho bộ thuộc tính published. Không trộn tùy ý hai loại cấu hình.

### 12.3. Ghi nhận cấu hình có hiệu lực của từng job run

Job run có thể override một số cấu hình của Job. Vì vậy, tên Job không đủ xác định môi trường và tham số đã dùng.

Cần ghi lại môi trường, manifest dữ liệu, đối số, giới hạn thời gian, shape, vị trí đầu ra và job run OCID. OCI cung cấp thông tin mặc định và override trong chi tiết job run. [Managing Job Runs](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-manage-runs.htm).

Mẫu logic thực thi:

~~~text
đọc cấu hình của lần chạy
xác nhận định danh dữ liệu, mã nguồn và môi trường
đọc manifest và kiểm tra các object đầu vào
kiểm tra schema, nhãn và cách chia tập
fit pipeline trên train
đánh giá theo quy trình đã chốt
lưu artifact, metadata và báo cáo vào vị trí riêng của run
chỉ công bố kết quả hoàn tất sau khi các đầu ra bắt buộc đã lưu
~~~

Thư mục tạm trong máy chạy không nên là bản duy nhất giữ mô hình hoặc bằng chứng. Lưu đầu ra bền vững trước khi coi lần chạy hoàn tất.

## 13. Chọn tài nguyên và kiểm soát chi phí

### 13.1. Đo nút thắt trước khi tăng shape

| Hiện tượng | Hướng kiểm tra trước |
| --- | --- |
| Hết RAM khi đọc dữ liệu | Chỉ đọc cột cần thiết, xử lý theo lô, kiểu dữ liệu và kích thước sau giải nén |
| CPU nhàn nhưng chờ lâu | Tốc độ đọc nguồn, nhiều object nhỏ, database hoặc mạng |
| GPU ít sử dụng | Pipeline nạp dữ liệu, framework, batch size và khả năng tăng tốc của thuật toán |
| Hết disk | Bản sao dữ liệu, cache, giải nén môi trường và checkpoint |
| One-hot quá lớn | Số lượng giá trị phân loại, biểu diễn thưa và chiến lược đặc trưng |
| Khởi tạo Job lâu | Tải và giải nén môi trường, kích thước artifact, nguồn package |

Dung lượng file nén không tương đương RAM cần thiết. Ngoài dữ liệu gốc, bộ nhớ còn chứa các bản trung gian, ma trận đặc trưng và trạng thái mô hình.

Dùng một mẫu đại diện để ước lượng, nhưng không kết luận từ vài dòng rằng toàn bộ dữ liệu sẽ vừa RAM. Nếu phải chuyển sang phân tán, giữ nguyên quy tắc thời gian, schema và định danh release.

### 13.2. Giới hạn thời gian và vòng đời tài nguyên

Cấu hình maximum runtime cho job run để tránh chạy ngoài dự kiến; dịch vụ có cơ chế hủy khi vượt thời gian đã đặt. [Creating a Job — Maximum runtime](https://docs.oracle.com/en-us/iaas/Content/data-science/using/jobs-create.htm).

Sau thử nghiệm:

- Deactivate notebook khi không cần Compute và kiểm tra phần lưu trữ còn giữ lại.
- Kiểm tra job còn chạy, retry lặp hoặc nhiều run trùng đầu vào.
- Quản lý vòng đời dữ liệu tạm, log, các bản Conda và phiên bản object.
- Giữ những artifact cần truy vết theo chính sách, thay vì xóa toàn bộ để giảm phí.
- Theo dõi chi phí theo compartment hoặc tag của dự án.

Notebook deactivate dừng phần Compute theo cơ chế dịch vụ nhưng block storage còn được giữ có thể tiếp tục phát sinh phí. [Overview of Data Science — Provisioning and Pricing](https://docs.oracle.com/en-us/iaas/data-science/using/overview.htm).

Tối ưu chi phí không chỉ là chọn máy nhỏ: một môi trường quá lớn, quá nhiều lần tải lại dữ liệu hoặc retry không giới hạn cũng làm tăng chi phí mà không cải thiện mô hình.

## 14. Chẩn đoán lỗi chuẩn bị huấn luyện

| Triệu chứng | Nguyên nhân cần xem xét | Bước kiểm tra |
| --- | --- | --- |
| Notebook có package nhưng Job báo thiếu | Job dùng môi trường khác hoặc chưa cấu hình | Kiểm tra environment có hiệu lực của job run |
| Cài package xong, cell vẫn import lỗi | Kernel khác interpreter đã cài | Xem sys.executable và chọn lại kernel |
| Notebook đọc được bucket, Job không đọc được | Principal hoặc dynamic group khác | Đối chiếu danh tính tài nguyên và policy |
| Không tải được môi trường | Sai object name, quyền hoặc đường mạng | Kiểm tra metadata bản publish, IAM và kết nối |
| Cùng mã nhưng điểm khác đáng kể | Dữ liệu, split, dependency hoặc cấu hình đã đổi | So sánh run manifest, checksum và môi trường |
| Điểm đánh giá quá cao | Trùng bản ghi, leakage hoặc chia tập sai | Đối chiếu thời gian, nhóm và cách tạo đặc trưng |
| Chạy lại sau deactivate bị thiếu thư viện | Cài vào base hoặc chọn sai kernel | Kiểm tra installed Conda và interpreter |
| Hết RAM sau mã hóa | Đặc trưng phân loại nhiều giá trị, dữ liệu trung gian lớn | Kiểm tra cardinality và biểu diễn dữ liệu |
| Job hoàn tất nhưng không có artifact | Chỉ ghi local hoặc lỗi lưu bị bỏ qua | Kiểm tra vị trí bền vững và điều kiện công bố hoàn tất |
| GPU không được dùng | Runtime, driver, package hoặc thuật toán không phù hợp | Kiểm tra tương thích theo framework và shape |

Không giải quyết mọi lỗi quyền bằng cách mở quyền rộng. Cũng không giải quyết mọi lỗi import bằng cách nâng cấp hàng loạt dependency. Chẩn đoán theo lớp giúp giữ môi trường có thể giải thích được.

## 15. Thực hành: chuẩn bị một lần huấn luyện có thể chạy lại

Thực hành trong compartment học tập với dữ liệu giả lập hoặc đã được cho phép. Mục tiêu là tạo bằng chứng về dữ liệu và môi trường, chưa cần mô hình phức tạp.

### 15.1. Chuẩn bị dataset release

1. Xác định đơn vị quan sát, prediction time và quy tắc nhãn.
2. Viết schema và danh sách trường được phép dùng.
3. Lấy một snapshot dữ liệu, loại thông tin không cần thiết.
4. Kiểm tra cấu trúc, khóa, nhãn và thời gian.
5. Chia tập theo mục tiêu triển khai, gồm điều kiện nhãn đã khả dụng.
6. Lưu dữ liệu, manifest và báo cáo chất lượng vào nơi được quản lý.

**Bằng chứng cần có:** định danh release, danh sách object, cách chia tập và lý do chấp nhận dữ liệu.

### 15.2. Chuẩn bị environment release

1. Chọn môi trường Conda phù hợp trong notebook.
2. Xác nhận kernel, Python, dependency và tài nguyên.
3. Chạy một luồng nhỏ từ đọc dữ liệu đến tạo đầu ra.
4. Publish môi trường ứng viên.
5. Ghi lại vị trí chính xác và metadata của gói.
6. Dùng lại bản published trong một ngữ cảnh sạch để xác nhận không phụ thuộc thay đổi cục bộ.

**Bằng chứng cần có:** định danh môi trường, metadata phần mềm và kết quả kiểm tra luồng nhỏ.

### 15.3. Chạy Job từ đầu vào có định danh

1. Đóng gói mã có entrypoint rõ ràng.
2. Cấu hình dataset manifest, môi trường, output prefix và seed.
3. Cấp quyền cho job run và kiểm tra mạng theo từng đích.
4. Đặt giới hạn thời gian, bật log phù hợp và chạy quy trình.
5. Lưu cấu hình có hiệu lực, artifact và báo cáo.
6. Chạy lại với cùng đầu vào đã khóa và đối chiếu theo sai số đã xác định.

Nếu khác biệt vượt mức chấp nhận, kiểm tra dữ liệu, dependency, số luồng, phần cứng và nguồn ngẫu nhiên. Không tự coi việc dùng cùng seed là bằng chứng mọi lớp đều giống nhau.

### 15.4. Điều kiện hoàn tất phần chuẩn bị

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Có biết chính xác dữ liệu nào được dùng? | Dataset manifest và định danh object |
| Có giải thích được nhãn và đặc trưng tại thời điểm dự đoán? | Schema, quy tắc nhãn và điều kiện thời gian |
| Có chia tập phù hợp cách triển khai? | Split rule và bản ghi phân tập |
| Có giữ tiền xử lý đi cùng mô hình? | Pipeline hoặc artifact tương đương |
| Có dựng lại môi trường mà không dựa vào notebook hiện tại? | Published Conda hoặc image cùng metadata |
| Job có đủ quyền và đường mạng? | Cấu hình principal, policy và kiểm tra kết nối |
| Có tìm lại kết quả và cấu hình từng lần chạy? | Run manifest, log và đầu ra bền vững |
| Có giới hạn tài nguyên và vòng đời dữ liệu? | Maximum runtime và chính sách lưu giữ |

Khi các bằng chứng này đầy đủ, đội ngũ có cơ sở để chuyển sang huấn luyện và lựa chọn mô hình trên OCI, đồng thời giải thích được một kết quả đến từ dữ liệu, mã nguồn và môi trường nào.
