# IAM, authorized views và kiểm soát truy cập dataset

Một nền tảng học trực tuyến lưu sự kiện ghi danh, doanh thu và thông tin học viên trong **BigQuery**. Nhóm vận hành cần đọc toàn bộ dữ liệu để đối soát, nhưng nhóm phân tích chỉ cần số lượt ghi danh theo khóa học; đối tác bên ngoài thậm chí chỉ được xem báo cáo tổng hợp. Nếu cấp `BigQuery Data Viewer` ở **project** cho tất cả mọi người, quyền truy cập có thể lan tới nhiều dataset khác chứa email, học phí và dữ liệu nhạy cảm.

Bài học thuộc chương **BigQuery** của module **CLOUD_PROVIDERS_GCP**. Ta sẽ dùng **Google Cloud IAM**, quyền ở **dataset/table/view**, và **authorized views** để chia sẻ dữ liệu theo nguyên tắc tối thiểu; đồng thời kết nối với kiến thức project, service account của Cloud Run/GKE, kiểm toán và chi phí truy vấn.

**Mục tiêu:** sau bài học, bạn có thể:

1. Phân biệt quyền **tạo query job** với quyền **đọc bảng/view**, và phạm vi kế thừa của IAM.
2. Chọn role phù hợp cho owner, pipeline ghi dữ liệu, analyst và service account.
3. Tạo authorized view từ một dataset riêng, ủy quyền nó đọc bảng nguồn mà không cấp quyền đọc bảng nguồn cho analyst.
4. Giải thích khác nhau giữa **authorized view**, **authorized dataset**, row-level access policy và column-level policy tags/masking.
5. Kiểm thử cả truy cập được phép lẫn bị từ chối, rà soát audit logs, quyền kế thừa và cơ chế thu hồi.
6. Thực hiện lab với dữ liệu giả, không cần truy cập dữ liệu thật.

## 1. Mô hình phân quyền của BigQuery

BigQuery có **resource hierarchy**: organization/folder → project → dataset → table/view/routine. IAM role được gán ở cấp cao có thể **kế thừa xuống tài nguyên con**. Chỉ thu hồi một binding ở dataset không làm mất quyền đã được cấp từ project hay organization.

~~~mermaid
flowchart TB
    ORG["Organization / Folder"] --> P["Project: learning-prod"]
    P --> RAW["Dataset: raw_private"]
    P --> PUB["Dataset: reports_shared"]
    RAW --> T["Table: enrollments<br/>có email, học phí"]
    PUB --> V["View: enrollment_counts<br/>chỉ báo cáo"]
    ANALYST["Nhóm analyst"] -->|"dataViewer trên view<br/>+ jobs.create trên billing project"| V
    V -. "Authorized view<br/>trên source dataset" .-> RAW
    ANALYST -. "Không có quyền<br/>đọc bảng gốc" .-> T
~~~

**Một query qua authorized view được phép** không đồng nghĩa principal được đọc trực tiếp bảng `raw_private.enrollments`. Quyền ủy quyền được gắn cho **view trên source dataset**, còn người dùng chỉ được quyền đọc **view**.

### 1.1. Quyền thực thi và quyền dữ liệu là hai phần khác nhau

| Nhu cầu | Permission/role thường dùng | Phạm vi nên cấp |
| --- | --- | --- |
| Tạo/query job | `bigquery.jobs.create` qua `roles/bigquery.jobUser` | **Project chạy/billed query job**; không phải chỉ cấp trên dataset |
| Đọc bảng hoặc view | `bigquery.tables.getData` qua `roles/bigquery.dataViewer` | **Dataset hoặc một table/view cụ thể**, tùy phạm vi cần |
| Tạo/chỉnh bảng hoặc view | `roles/bigquery.dataEditor` | Dataset dành cho pipeline/nhóm tạo view |
| Quản lý dataset và quyền truy cập của nó | `roles/bigquery.dataOwner` | Chỉ dataset do chủ dữ liệu quản lý |
| Quản trị BigQuery rộng | `roles/bigquery.admin` | Chỉ tài khoản quản trị thật sự cần; tránh cấp để chạy SELECT |

Ví dụ analyst có `roles/bigquery.dataViewer` trên view mà **không có** `bigquery.jobs.create` tại project chạy job có thể đọc metadata nhưng **không tự chạy query job**. Ngược lại, có Job User ở project **không cho phép** đọc mọi dataset trong project đó.

Job có thể chạy và bị tính phí ở **project khác** với project chứa dữ liệu; quyền Job User cần trên **execution/billing project**, quyền xem table/view cần trên tài nguyên dữ liệu tương ứng. Với Cloud Run/GKE, dùng **runtime service account** riêng và cấp đúng hai loại quyền này, không dùng service account key JSON trong container.

### 1.2. Phạm vi cấp quyền và blast radius

| Binding | Principal được gì? | Rủi ro |
| --- | --- | --- |
| `roles/bigquery.dataViewer` tại project dữ liệu | Có thể đọc bảng/view trên **nhiều dataset** kế thừa role | Vô tình truy cập dữ liệu nhạy cảm ngoài nhiệm vụ |
| `roles/bigquery.dataViewer` tại dataset `reports_shared` | Đọc tài nguyên của dataset đó | Nếu dataset chứa thêm view/table khác về sau, quyền có thể mở rộng |
| `roles/bigquery.dataViewer` tại **một view** | Đọc đúng view (và metadata cần thiết theo chính sách) | Tối thiểu nhất, nhưng cần quản lý nhiều bindings hơn |
| `roles/bigquery.dataEditor` tại dataset nguồn | Sửa dữ liệu/đối tượng trong dataset đó | Không phù hợp cho analyst chỉ đọc |
| `roles/bigquery.dataOwner` tại dataset nguồn | Quản lý dữ liệu và quyền của dataset | Chỉ cấp cho data owner/steward được phê duyệt |

**Luôn kiểm tra IAM kế thừa** trước khi khẳng định người dùng “không có quyền” trên bảng nguồn. Ví dụ một người vẫn là `project Editor` hoặc đã có BigQuery Data Viewer ở project có thể đọc trực tiếp bảng dù bạn đã cấp quyền đúng cho view.

### 1.3. Access control được quản lý theo hai hình thức

BigQuery hỗ trợ **IAM policies** trên dataset/table/view và các **dataset access entries (ACL)**, trong đó có các thực thể đặc biệt như **authorized view**/**authorized dataset**. Các entries ủy quyền view không phải một service account để gắn role thông thường; chúng biểu diễn quyền đọc bảng nguồn **thông qua view**.

Lưu ý thay đổi ở một số môi trường: khi bật tùy chọn **fine-grained dataset ACL permission enforcement**, việc đọc/sửa access control cần `bigquery.datasets.getIamPolicy` và `bigquery.datasets.setIamPolicy` tương ứng, ngoài những quyền liên quan theo loại API/thao tác. Vì vậy một script chỉ dựa trên `bigquery.datasets.update` có thể thất bại sau khi cơ chế enforcement được bật. Kiểm tra quyền, phiên bản API và cấu hình tổ chức trước khi tự động hóa; không mở rộng thành Owner để chữa một lỗi 403.

## 2. Authorized view: chia sẻ kết quả mà không chia sẻ bảng nguồn

**Logical view** là câu truy vấn `SELECT` được lưu dưới một tên, bình thường người truy vấn cần quyền đến những bảng được tham chiếu. **Authorized view** là view được **source dataset ủy quyền** để đọc bảng nguồn thay cho principal gọi, trong phạm vi SQL view định nghĩa.

~~~mermaid
sequenceDiagram
    participant U as Analyst
    participant J as BigQuery query job
    participant V as reports_shared.enrollment_counts
    participant R as raw_private.enrollments
    U->>J: SELECT * FROM view
    J->>J: Kiểm tra jobs.create + quyền đọc view
    J->>V: Chạy SQL đã lưu
    V->>R: Truy cập bảng qua authorized view entry
    R-->>V: Dữ liệu theo truy vấn
    V-->>U: Chỉ các cột/hàng view cho phép
    Note over U,R: SELECT trực tiếp bảng nguồn của U phải bị từ chối
~~~

### 2.1. Ba quyền phải đi cùng nhau

1. **Data owner** tạo view ở **dataset chia sẻ riêng** và ủy quyền view trên **source dataset**.
2. **Consumer** được `roles/bigquery.dataViewer` **trên view** hoặc dataset chứa view; **không** được Data Viewer trên dataset nguồn.
3. **Consumer** có `bigquery.jobs.create` trên project dùng để chạy query; kiểm soát quota/billing phù hợp.

Hai dataset chứa source và authorized view cần ở **cùng location**. Không dùng một dataset vừa chứa toàn bộ dữ liệu thô vừa chứa view chia sẻ rồi cấp Data Viewer trên dataset đó: role kế thừa sẽ cho phép đọc **cả bảng thô**.

### 2.2. Điều gì không được bảo đảm bởi authorized view?

- View chỉ tiết lộ những dữ liệu **truy vấn được thiết kế để trả**; nó không tự áp k-anonymity, privacy budget hay chống tái nhận diện từ nhóm rất nhỏ.
- Dùng `SELECT *` trong view dễ rò rỉ cột mới được thêm ở bảng nguồn; nên chọn **danh sách cột tường minh**, có review khi sửa SQL.
- Nếu consumer đã có quyền rộng trên source dataset từ IAM project, authorized view **không thu hồi** quyền đó.
- SQL view phải được review và quản trị thay đổi: chỉnh view để trả thêm cột hoặc bỏ filter có thể mở rộng dữ liệu tiếp cận.
- Với dataset được **ủy quyền cả dataset** (authorized dataset), mọi view hiện tại và tương lai ở đó có thể truy cập source theo quyền ủy quyền; vì thế quyền **tạo/chỉnh view** trong dataset đó là đặc quyền nhạy cảm.

Đối với authorized view thông thường, khả năng chỉnh SQL của view có kiểm tra quyền chặt chẽ từ source data owner. Đừng coi Data Editor trên dataset view là quyền để tự ý đổi nội dung view đã authorized; việc kiểm soát thay đổi vẫn cần được xác minh theo chính sách BigQuery.

## 3. Lab: hai dataset và một authorized view

**Mục tiêu:** người phân tích được phép xem **số lượt ghi danh theo khóa học**, nhưng không được đọc email, học phí hoặc bảng gốc. Tất cả các thao tác ghi sau đây chỉ dành cho **project lab được duyệt**; BigQuery có thể tính phí query, storage và job. Không dùng dữ liệu học viên thật.

### 3.1. Tài nguyên và danh tính

| Tài nguyên | Chức năng | Quyền |
| --- | --- | --- |
| `bq_iam_raw_lab` | Dataset riêng chứa bảng `enrollments` | Data owner và pipeline ETL được phê duyệt |
| `bq_iam_shared_lab` | Dataset chỉ chia sẻ view `active_by_course` | Analyst có quyền đọc view; owner quản lý SQL |
| `analyst@example.com` | Principal giả định để thử quyền | Job User tại project chạy job + Data Viewer **trên view** |
| View authorization | Entry trên access controls của `bq_iam_raw_lab` | Cho view truy vấn bảng nguồn, không cấp cho analyst quyền bảng |

Người làm lab cần được cấp quyền **tạo datasets/tables/views**, đọc source table và **ủy quyền view trên source dataset**. Bước cấp IAM/view authorization cần thực hiện bởi data owner được phép; analyst chỉ dùng tài khoản riêng để kiểm thử. Không tự tạo service account key.

### 3.2. Tạo dataset tại cùng location

Trong Cloud Shell/Bash, dùng **project lab riêng**, kiểm tra chưa có các tên này và chọn location theo yêu cầu residency:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export LOCATION="US"
export RAW_DS="bq_iam_raw_lab"
export SHARED_DS="bq_iam_shared_lab"

gcloud config set project "$PROJECT_ID"

# CHỈ ĐỌC: xác minh project và các dataset đã tồn tại.
gcloud config get-value project
bq ls --project_id="$PROJECT_ID"

# CÓ GHI: chỉ thực hiện nếu tên dataset chưa có trong project LAB.
bq --location="$LOCATION" mk --dataset "$PROJECT_ID:$RAW_DS"
bq --location="$LOCATION" mk --dataset "$PROJECT_ID:$SHARED_DS"
~~~

Nếu tên dataset đã tồn tại, **dừng** và chọn tên riêng được phê duyệt; không thay quyền/xóa dataset của nhóm khác. Cả source và view phải cùng **location**; ví dụ `US` là multi-region, **không** đồng nghĩa với region `us-central1`.

### 3.3. Tạo bảng chứa cả dữ liệu nhạy cảm và dữ liệu được chia sẻ

Chạy bằng BigQuery Studio (GoogleSQL) trong **project lab**; thay `YOUR_PROJECT` bằng project ID thực:

~~~sql
CREATE TABLE `YOUR_PROJECT.bq_iam_raw_lab.enrollments` (
  enrollment_id STRING NOT NULL,
  learner_id STRING NOT NULL,
  course_id STRING NOT NULL,
  status STRING NOT NULL,
  email STRING,
  tuition_usd NUMERIC
);

INSERT INTO `YOUR_PROJECT.bq_iam_raw_lab.enrollments`
  (enrollment_id, learner_id, course_id, status, email, tuition_usd)
VALUES
  ('e1', 'u1', 'java-basic', 'ACTIVE', 'u1@example.invalid', 30),
  ('e2', 'u2', 'java-basic', 'ACTIVE', 'u2@example.invalid', 20),
  ('e3', 'u3', 'java-basic', 'ACTIVE', 'u3@example.invalid', 25),
  ('e4', 'u4', 'java-basic', 'ACTIVE', 'u4@example.invalid', 20),
  ('e5', 'u5', 'python-basic', 'ACTIVE', 'u5@example.invalid', 35),
  ('e6', 'u6', 'python-basic', 'CANCELLED', 'u6@example.invalid', 35);
~~~

**Ghi chú:** `example.invalid` là miền giả dành cho dữ liệu thử; câu lệnh không chứa dữ liệu thật. Dataset lab không được bật public. Lệnh `CREATE TABLE` và `INSERT` thực sự ghi dữ liệu nếu chạy; phải dùng project/chi phí được duyệt.

### 3.4. Tạo logical view giới hạn cột và hàng

Trong **dataset chia sẻ riêng**, tạo view:

~~~sql
CREATE VIEW `YOUR_PROJECT.bq_iam_shared_lab.active_by_course` AS
SELECT
  course_id,
  COUNT(*) AS active_enrollments
FROM `YOUR_PROJECT.bq_iam_raw_lab.enrollments`
WHERE status = 'ACTIVE'
GROUP BY course_id
HAVING COUNT(*) >= 3;
~~~

Điều kiện `HAVING COUNT(*) >= 3` chỉ nhằm tránh hiện nhóm có quá ít hàng trong **ví dụ**. Ngưỡng 3 **không** là bảo đảm quyền riêng tư: kết hợp nhiều báo cáo, thay đổi filter hoặc kiến thức bên ngoài vẫn có thể làm lộ người học. Mục tiêu chính là **view không chọn các cột `email`, `learner_id` và `tuition_usd`**.

Với dữ liệu mẫu, kết quả dự kiến có **một hàng** cho `java-basic` với `active_enrollments = 4`. View `python-basic` không xuất hiện vì chỉ có một bản ghi ACTIVE.

### 3.5. Cấp quyền theo đúng thứ tự

**Bước A — Ủy quyền view trên source dataset.**

1. Đăng nhập bằng **data owner** được phép sửa access controls trên `bq_iam_raw_lab`.
2. BigQuery Console → chọn source dataset `bq_iam_raw_lab` → **Sharing → Authorize views**.
3. Nhập `YOUR_PROJECT.bq_iam_shared_lab.active_by_course` và chọn **Add authorization**.
4. Xác minh entry xuất hiện ở source dataset và chỉ đúng view đã review.

Đây là bước biến một **logical view thông thường** thành **authorized view**. Không thêm analyst làm Data Viewer ở `bq_iam_raw_lab`; nếu làm vậy thì analyst có thể truy vấn dữ liệu thô, làm hỏng mục tiêu thiết kế.

**Bước B — Cho consumer quyền đọc view.**

5. Trên **view `active_by_course`** (hoặc dataset chia sẻ chỉ có đúng view được phép), vào **Sharing → Permissions** và cấp `BigQuery Data Viewer` cho nhóm analyst được duyệt.
6. Tại **project chạy job**, cấp `BigQuery Job User` (`roles/bigquery.jobUser`) cho analyst. Project job có thể khác project lưu view, nhưng phải có location/quota và chính sách liên quan phù hợp.
7. Kiểm tra analyst **không có** quyền đọc source qua IAM kế thừa ở project/organization hoặc nhóm khác.

**Bước C — Kiểm thử bằng chính danh tính consumer.**

~~~sql
-- Kỳ vọng: thành công; chỉ course_id và active_enrollments.
SELECT *
FROM `YOUR_PROJECT.bq_iam_shared_lab.active_by_course`;

-- Kỳ vọng: Access Denied đối với analyst KHÔNG có quyền nguồn.
SELECT email, tuition_usd
FROM `YOUR_PROJECT.bq_iam_raw_lab.enrollments`
LIMIT 1;
~~~

Không chạy phép thử âm tính bằng tài khoản data owner vì kết quả sẽ không chứng minh được phân quyền analyst. Nếu thử trực tiếp bảng nguồn **vẫn thành công**, cần rà soát binding kế thừa, nhóm/role khác hoặc đường truy cập thông qua đối tượng được chia sẻ; không coi lab đã đạt.

### 3.6. Quan sát quyền và dọn tài nguyên

Lệnh **chỉ đọc** sau giúp xem metadata và ACL của dataset mà người chạy có quyền:

~~~bash
bq show --format=prettyjson "$PROJECT_ID:$RAW_DS"
bq show --format=prettyjson "$PROJECT_ID:$SHARED_DS"
bq show --format=prettyjson "$PROJECT_ID:$SHARED_DS.active_by_course"
~~~

Kết quả có thể chứa thông tin nội bộ về dataset và principals; **không dán toàn bộ JSON vào ticket công khai**. Quyền IAM được cấp ở project có thể **không hiện đầy đủ** trong ACL trực tiếp của dataset — cần xem chính sách IAM ở tổ tiên.

**Dọn lab:** data owner thu hồi quyền đọc view của analyst, gỡ **authorized view entry** trên source dataset rồi xóa đúng view, hai dataset và bảng giả **do lab đã tạo** sau khi xác nhận không ai khác sử dụng. Không dùng lệnh `bq rm -r -f` với project/dataset chưa kiểm chứng, không xóa dataset production. Logs và hóa đơn có thể xuất hiện sau khi dọn xong.

## 4. Authorized view và authorized dataset khác nhau thế nào?

| Cơ chế | Đơn vị được source dataset ủy quyền | Phù hợp khi | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Authorized view** | **Một view cụ thể** | Chia sẻ vài báo cáo/đường truy vấn đã được owner duyệt | SQL view thay đổi; consumer được grant thêm ngoài dự kiến |
| **Authorized dataset** | **Dataset chứa các views** | Nhiều views được quản lý theo cùng một chính sách và nhóm chủ sở hữu | View **mới hoặc được sửa** trong dataset được ủy quyền có thể truy cập dữ liệu nguồn |
| **Authorized routine** | Routine được ủy quyền | Cần cung cấp truy vấn/hàm qua interface đã kiểm soát | Logic routine và quyền thay đổi phải được review |
| **Data Viewer trên source dataset** | **Principal** đọc trực tiếp bảng nguồn | Nội bộ cần đọc dữ liệu thô, có phê duyệt | Không đáp ứng yêu cầu che bảng nguồn khỏi consumer |

### 4.1. Vì sao authorized dataset đòi quản lý chặt người tạo view?

Nếu `reports_shared` được authorized **ở cấp dataset** đối với `raw_private`, người có quyền tạo/chỉnh views tại `reports_shared` có thể làm lộ dữ liệu nguồn bằng view mới/SQL được mở rộng (trong phạm vi và điều kiện ủy quyền). Vì vậy **không cho mọi analyst quyền Data Editor** trên dataset đã được source tin cậy.

Quy trình phù hợp:

1. Data owner xác định nhóm **trusted view publishers**, tách khỏi nhóm consumer chỉ đọc.
2. Chỉ người/CI đáng tin có quyền tạo hoặc cập nhật view trong authorized dataset.
3. Áp code review với SQL, filter, aggregation, danh sách cột và nguồn tham chiếu; kiểm thử dữ liệu có thể lộ.
4. Kiểm tra dataset access entries và tất cả views khi audit; giám sát những view mới hoặc thay đổi SQL.
5. Thu hồi authorization khi dataset không còn được quản trị an toàn.

Với một vài báo cáo, ưu tiên **ủy quyền từng view** để thu hẹp phạm vi. Authorized dataset giúp giảm công cấu hình nhiều view nhưng **tăng trách nhiệm quản trị publishing**.

### 4.2. Vị trí và các ràng buộc khác

- Source dataset và dataset chứa authorized view phải ở **cùng BigQuery location**. Project khác nhau vẫn có thể tham gia nếu IAM, location và tổ chức cho phép.
- Authorized view là **logical view**: truy vấn nó thường đọc bảng nguồn tại thời điểm chạy, không tự tạo một bản copy vật lý để làm sạch dữ liệu.
- Nếu source là dữ liệu nhạy cảm, các policy như **column-level security**, row-level policies, data masking, IAM deny và **VPC Service Controls** cần được đánh giá cùng nhau. Không giả định view bỏ qua mọi lớp chính sách, cũng không tự thiết kế filter để vượt lớp bảo vệ bên dưới.
- Khi view cần tham chiếu dữ liệu ngoài vùng/chia sẻ qua perimeter, có thêm giới hạn dịch vụ/quy định; kiểm tra đúng cấu hình và phiên bản tài liệu.

## 5. Quyền theo hàng và cột: khi authorized view chưa đủ

Authorized view rất hữu ích khi **phần dữ liệu chia sẻ được diễn đạt bằng một truy vấn SQL đã kiểm duyệt**. Nhưng với hàng trăm tenants, nhiều role và dữ liệu nhạy cảm phải quản lý xuyên suốt nhiều đường truy cập, cần kết hợp thêm các cơ chế khác.

### 5.1. Row-level access policies

**Row-level access policy** cho phép dùng điều kiện SQL để kiểm soát **những hàng nào** một principal/nhóm có thể đọc từ bảng. Ví dụ nhóm báo cáo khu vực chỉ được truy cập các bản ghi thuộc region đã định nghĩa.

| Cơ chế | Dùng khi | Chú ý |
| --- | --- | --- |
| Filter trong **authorized view** | Ít góc nhìn cố định được owner review | Không tự bảo vệ các đường truy vấn khác đến bảng nguồn |
| **Row-level access policy** trên bảng | Cần quy tắc lọc hàng gắn với bảng và principals | Cần kiểm thử theo từng danh tính, role và sự kết hợp nhiều chính sách |
| **Application authorization** | Quyền theo từng học viên/đơn hàng hoặc kết quả giao dịch trực tiếp | BigQuery không thay thế kiểm tra quyền nghiệp vụ ở backend |

**Không dùng một view tổng hợp để cấp “mỗi user chỉ xem đơn của chính mình” nếu quyền đó phụ thuộc user identity mà query không thể chứng minh.** Khi dùng multi-tenant data, cân nhắc dataset per tenant, row-level security hoặc backend service có logic ủy quyền đúng nhu cầu.

### 5.2. Column-level policy tags và data masking

Với bảng `enrollments`, hai cột `email` và `tuition_usd` có thể cần bảo vệ **ngay cả khi người dùng có quyền đọc dataset nguồn**:

1. Data steward phân loại những cột nhạy cảm.
2. Tạo **taxonomy/policy tags** hoặc cơ chế data governance tag phù hợp, gắn lên schema columns.
3. Bật chính sách thực thi theo sản phẩm, cấp **Fine-Grained Reader** cho principal thực sự được phép đọc giá trị gốc.
4. Nếu nghiệp vụ cần xem dữ liệu che bớt, dùng **data masking** và cấp Masked Reader theo chính sách.
5. Thử cùng câu query dưới danh tính có full reader, masked reader và không có quyền.

**Column policy tags là lớp bổ sung so với dataset IAM**. Có Data Viewer trên dataset **không mặc nhiên** cho phép đọc mọi cột gắn policy tag. Với view, cần xác minh **quyền liên quan tới cột nguồn** theo quy tắc thực thi; một view `SELECT email` không phải cách vượt chính sách dữ liệu cột.

Mặt khác, một authorized view không chứa email và học phí là giải pháp thu hẹp **hợp đồng chia sẻ** rõ ràng; policy tags/masking hỗ trợ thực thi xuyên nhiều truy vấn/consumers. Không đánh đồng view che bớt cột với việc dữ liệu gốc đã được mã hóa hoặc ẩn danh không thể đảo ngược.

### 5.3. Mô hình kết hợp cho tổ chức có nhiều nhóm

| Nhóm | Job execution | Data access | Lưu ý |
| --- | --- | --- | --- |
| **ETL ingestion** | Job User trên project pipeline | Data Editor đúng dataset nguồn | Không cấp quyền đọc toàn project nếu pipeline chỉ ghi một dataset |
| **Bộ phận tài chính** | Job User trên project được duyệt | Data Viewer dataset nguồn + quyền policy tag cần thiết | Audit những cột nhạy cảm và export |
| **Nhà phân tích khóa học** | Job User tại execution project | Data Viewer trên authorized report views | Không có đường truy cập trực tiếp source |
| **Đối tác ngoài** | Chỉ cấp quyền khi có hợp đồng | View riêng, dữ liệu tổng hợp, quota và perimeter phù hợp | Kiểm thử chống tái nhận diện/khai thác dữ liệu |
| **Cloud Run báo cáo** | Runtime SA có quyền tạo job nếu cần | Chỉ đọc view được phê duyệt | Quyền user cuối vẫn kiểm tra ở ứng dụng |

Hãy dùng **Google Groups** để quản lý người dùng có cùng nhu cầu, phân tách admin/deployer/data consumer, rà soát quyền định kỳ. Đừng cấp `roles/bigquery.admin` hoặc `Owner` chỉ để chạy dashboard.

## 6. Kiểm toán, thu hồi quyền và kiểm soát chi phí

### 6.1. Quy trình rà soát quyền định kỳ

Một checklist theo thứ tự giúp tránh bỏ sót quyền gián tiếp:

1. Xác định **principal thật** dùng để chạy query (user, group hoặc runtime service account) và **project chạy job**.
2. Kiểm tra IAM **kế thừa** từ organization/folder/project, rồi bindings trực tiếp tại dataset/table/view.
3. Kiểm tra **authorized view/dataset/routine entries** trên dataset nguồn; ghi owner và mục đích từng entry.
4. Liệt kê những **views** đã chia sẻ, SQL hiện tại, quyền người tạo/chỉnh view và các cột/nguồn được tham chiếu.
5. Kiểm tra policy tags, masking, row policies, IAM deny và VPC Service Controls nếu đang dùng.
6. Kiểm thử **negative access** bằng danh tính đại diện không có quyền, không chỉ nhìn bảng IAM.
7. Gỡ bindings/authorization không còn cần, xác nhận không làm hỏng pipelines và báo cáo hợp lệ.

**Một view bị xóa hoặc đổi tên không đồng nghĩa mọi đường tới dữ liệu đã bị đóng.** Analyst có thể còn quyền đọc source qua nhóm khác, materialized/copy table đã tạo hoặc kết quả truy vấn được lưu ở nơi khác. Khi thu hồi quyền do sự cố dữ liệu, phải rà soát **các bản sao, exports và query results** theo chính sách, không chỉ sửa một ACL.

### 6.2. Audit logs và điều tra thay đổi

BigQuery phát sinh thông tin kiểm toán về thao tác quản trị và hoạt động query/data access theo khả năng sản phẩm và cấu hình Logging. Khi điều tra, tìm:

- **Ai** cấp `dataViewer`, `dataEditor`, sửa dataset ACL hoặc authorized view entry?
- **Ai** tạo/chỉnh `CREATE VIEW` và SQL definition của view chia sẻ?
- **Principal nào** chạy query, tại project/location nào, truy cập view hoặc bảng nào?
- **Query job** có export/copy dữ liệu sang dataset hoặc Cloud Storage bucket khác không?

Ví dụ bộ lọc bắt đầu trong Logs Explorer:

~~~text
protoPayload.serviceName="bigquery.googleapis.com"
~~~

Sau đó thu hẹp theo resource, principal, method, thời gian và loại log đã được bật/cho phép. **Không** giả định mọi sự kiện xuất hiện ở cùng log type hoặc ngay lập tức; BigQuery có cấu trúc audit metadata riêng và quyền xem Data Access logs có thể hạn chế. Tránh đưa query text chứa literals nhạy cảm vào báo cáo công khai.

### 6.3. Authorized view không phải bảng sao chép miễn phí

Logical view thực hiện truy vấn trên bảng nguồn khi được gọi. Điều này có nghĩa:

| Thao tác | Hệ quả |
| --- | --- |
| Analyst lặp lại query view nhiều lần | Có thể phát sinh **query processing cost** theo mô hình on-demand/capacity/edition |
| View SELECT nhiều cột hoặc không filter partition | Có thể quét nhiều dữ liệu nguồn hơn cần thiết |
| View chỉ tổng hợp nhưng source rất lớn | Vẫn có chi phí xử lý phần nguồn dùng để tổng hợp |
| Dùng `LIMIT 10` trên view | Không bảo đảm giảm **bytes scanned** của câu truy vấn nguồn |
| Tạo materialized view/bảng snapshot riêng | Có thể tăng storage/refresh cost và thay đổi cách cấp quyền; phải thiết kế lại |

**Bảo mật và chi phí là hai chiều riêng.** Một authorized view rất an toàn về cột/hàng được trả nhưng vẫn có thể chạy truy vấn đắt. Dùng query **dry run**, partition pruning, clustering, billing budgets/quotas và giám sát job metrics. Billing budget alert **không phải hard cap**.

### 6.4. Quy trình thay đổi view có kiểm soát

Với một view đang dùng bởi nhiều analyst:

1. Review SQL diff, danh sách cột thêm/bớt, filter, joins, aggregation, khả năng tái nhận diện và nguồn dữ liệu mới.
2. Thử trong dataset/view **staging** tại đúng location, dùng dữ liệu giả và tài khoản consumer.
3. Kiểm tra **permission-denied** của bảng nguồn và độ đúng của view, số bytes quét và latency.
4. Người có quyền được phép triển khai SQL và bảo đảm source authorization không mở rộng ngoài dự kiến.
5. Ghi change log, owner, rollback plan và kết quả negative tests; theo dõi query cost sau phát hành.

Với **authorized dataset**, phải áp quy trình này cho **mọi view mới**, không chỉ view ban đầu. Không cấp quyền Data Editor trên dataset đã authorized cho nhóm consumer.

## 7. Chẩn đoán lỗi truy cập

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra an toàn |
| --- | --- | --- |
| `Access Denied: User does not have bigquery.jobs.create` | Principal thiếu Job User tại **project chạy job** | Kiểm tra execution project và IAM project đó |
| Analyst xem metadata view nhưng không truy vấn được | Thiếu quyền đọc view, quyền job, hoặc nguồn chưa authorize | Kiểm tra từng lớp: job → view → source authorization |
| Query trực tiếp bảng nguồn bị từ chối | Thiết kế least privilege đang hoạt động | Đây là kết quả **mong đợi** của negative test |
| Analyst đọc được bảng nguồn dù chỉ định cấp view | Quyền kế thừa hoặc nhóm/role khác đang cấp trực tiếp | Kiểm tra IAM tổ tiên và membership, thu hồi theo phê duyệt |
| Authorized view báo lỗi nguồn sau khi đổi dataset/table | Source path, location hoặc authorized entry không còn đúng | Kiểm tra view SQL và source dataset authorization |
| `Permission denied` với một cột cụ thể | Policy tag/column-level security hoặc masking role | Kiểm tra taxonomy/tag policy, nguồn column và quyền principal |
| Truy vấn bị chặn bởi VPC Service Controls | Project/perimeter/ingress-egress rules | Xem VPC SC violation logs và perimeter policy; không tắt perimeter để “sửa nhanh” |
| Đã cấp IAM nhưng app Cloud Run vẫn lỗi | Runtime SA khác account người triển khai, hoặc project job sai | Kiểm tra service identity thực tế và job destination project |
| Role vừa thu hồi nhưng người dùng vẫn xem kết quả cũ | Cached query results, exports hoặc bản sao độc lập | Rà soát result/cache/data copies và chính sách thu hồi |
| View query thành công nhưng hóa đơn tăng | Query lặp, full scan, không partition filter hoặc concurrency cao | Xem bytes processed/billed, dry run, jobs và query plan |

**Mẹo phân lớp 403:** trước tiên xác định request thất bại khi **tạo job**, **đọc view**, **ủy quyền tới source** hay **kiểm tra cột/hàng**. Không thêm `BigQuery Admin` vào project để vượt qua 403: cách đó có thể phá toàn bộ mục tiêu chia sẻ an toàn.

### 7.1. Ba câu hỏi kiểm tra nhanh

~~~text
1. Ai đang thực thi?
   -> email của user hoặc service account; group và quyền kế thừa
2. Job chạy ở đâu?
   -> project/region dùng để chạy query, jobs.create và quota
3. Dữ liệu đang đọc là gì?
   -> view/table; Data Viewer; authorized view trên source;
      thêm policy tag/row policy/perimeter nếu có
~~~

Một thay đổi IAM/view authorization có thể cần thời gian phản ánh. Sau khi triển khai, kiểm thử lại bằng một **query mới** dưới đúng principal; không dùng cached query kết quả cũ làm bằng chứng quyền hiện tại.

## 8. Bài tập tình huống và hướng giải

### Tình huống A — Analyst vẫn đọc được email

Đội dữ liệu tạo authorized view chỉ có `course_id` và `COUNT(*)`, cấp Data Viewer trên view. Tuy nhiên analyst vẫn chạy được:

~~~sql
SELECT email
FROM `PROJECT_ID.raw_private.enrollments`
LIMIT 10;
~~~

**Câu hỏi:** view có bị lỗi không? Cần kiểm tra gì?

**Hướng giải:** chưa chắc view bị lỗi. Analyst có thể đang có **Data Viewer ở project nguồn**, là thành viên nhóm được cấp role tại folder, hoặc có quyền trực tiếp trên dataset/table. Kiểm tra quyền kế thừa và nhóm thực tế, thu hồi quyền quá rộng theo approval; **không** chỉ sửa SQL của view.

### Tình huống B — Authorized dataset và quyền tạo view

Dataset `reports_shared` được source `raw_private` ủy quyền ở cấp dataset. Một người dùng có `roles/bigquery.dataEditor` trên `reports_shared` tạo view mới `SELECT email, tuition_usd FROM raw_private.enrollments`.

**Câu hỏi:** rủi ro ở đâu, nên khắc phục thế nào?

**Hướng giải:** khi ủy quyền **cả dataset**, người tạo/chỉnh views trong đó giữ một quyền rất nhạy cảm: có thể thay đổi giao diện truy cập dữ liệu nguồn. Chỉ cho nhóm **trusted publishers** quyền tạo/chỉnh view, review SQL và test negative access. Nếu không cần cấp quyền rộng cho nhiều views, dùng **authorized views riêng lẻ**.

### Tình huống C — Cloud Run chỉ có Job User

Service `reports-api` trên Cloud Run dùng service account `reports-runtime`. Tài khoản này có `roles/bigquery.jobUser` tại project chạy job, nhưng query view trả 403.

**Câu hỏi:** nên cấp thêm quyền gì?

**Hướng giải:** cấp **Data Viewer trên view** hoặc dataset chia sẻ phù hợp cho **runtime service account thật**, không cấp `BigQuery Admin` hoặc Data Viewer toàn project. Xác minh source dataset đã authorize view. Nếu app chạy qua service account khác với người deploy, phải kiểm tra đúng identity của revision/container.

### Tình huống D — View tổng hợp nhưng vẫn lộ thông tin

Một view trả số lượt hoàn thành khóa học theo lớp. Có lớp chỉ có **một học viên**; đối tác biết học viên duy nhất là ai và suy ra trạng thái hoàn thành.

**Câu hỏi:** chỉ loại bỏ tên/email khỏi SQL đã đủ bảo vệ chưa?

**Hướng giải:** chưa đủ. Cần đánh giá **kích thước nhóm, suppression thresholds, dữ liệu bổ trợ, truy vấn lặp/cắt lát** và hợp đồng chia sẻ. Một điều kiện `HAVING COUNT(*) >= n` có thể giúp giảm một số rủi ro nhưng không bảo đảm ẩn danh. Có thể dùng dataset/report đã tổng hợp và được review, hạn chế truy vấn linh hoạt, policy tags và kiểm soát export tùy mức rủi ro.

### Tình huống E — Quyền đọc view có nhưng job không chạy

Analyst có `BigQuery Data Viewer` trên view của project `data-prod`; họ chạy job ở project `analysis-sandbox` nhưng nhận thông báo thiếu `bigquery.jobs.create`.

**Câu hỏi:** cấp ở đâu để đúng least privilege?

**Hướng giải:** cấp `roles/bigquery.jobUser` ở **analysis-sandbox**, nơi job được tạo/billed; giữ Data Viewer ở view thuộc `data-prod`. Xác minh cả hai resource locations và chính sách tổ chức; không cần cấp Job User hoặc Data Viewer toàn `data-prod` nếu không phải nơi tạo job.

### Bài tập định lượng — Chi phí logical view

Một báo cáo qua authorized view mỗi lượt quét khoảng **1 GiB dữ liệu nguồn** theo kế hoạch đo ban đầu. Có 100 analysts, mỗi người chạy bốn lần/ngày.

1. Ước lượng khối lượng xử lý trong ngày nếu **không có cache hoặc tối ưu nào**. — `100 × 4 × 1 GiB = 400 GiB/ngày`.
2. Nếu thiết kế partition filter giảm bytes quét trung bình còn 0,25 GiB/lượt, mô hình ước lượng thành bao nhiêu? — **100 GiB/ngày**.
3. Tại sao không lấy 400 GiB nhân trực tiếp một đơn giá mà hứa chắc chi phí? — Mô hình tính giá có thể là **on-demand hoặc capacity**, còn có cache, minimum billing, free tier/edition và thay đổi truy vấn.
4. Việc giảm bytes quét có cấp thêm hoặc thu hồi quyền không? — **Không**, IAM và cost optimization là hai quyết định độc lập.

### Tự kiểm tra

1. **Quyền `bigquery.jobs.create` có thay thế quyền đọc view không?** — Không; phải có quyền dữ liệu riêng.
2. **Data Viewer cấp ở project có thể kế thừa xuống nhiều dataset không?** — Có, vì vậy phạm vi này dễ quá rộng.
3. **Ủy quyền authorized view được thực hiện ở đâu?** — Trên **source dataset** mà view cần đọc.
4. **Analyst có cần Data Viewer trên bảng nguồn khi chỉ truy vấn authorized view không?** — Không.
5. **Có nên đặt view và bảng nguồn chung dataset rồi cấp viewer cả dataset?** — Không nếu cần giấu bảng nguồn.
6. **Authorized dataset có ủy quyền cả views tạo trong tương lai không?** — Có, trong phạm vi chính sách đó; người tạo view cần rất đáng tin.
7. **Authorized view có tự ẩn danh tuyệt đối dữ liệu tổng hợp không?** — Không; phải đánh giá tái nhận diện.
8. **Policy tag có thể hạn chế một cột dù user có Data Viewer trên dataset không?** — Có, nếu policy được cấu hình/thực thi.
9. **Xóa binding trên dataset có hủy role được cấp từ project không?** — Không.
10. **Một logical view query ít cột có chắc miễn phí không?** — Không; vẫn có query processing cost theo nguồn và mô hình giá.

## 9. Checklist triển khai cho data owner

| Hạng mục | Điều kiện hoàn thành |
| --- | --- |
| **Chủ sở hữu** | Dataset nguồn/view có owner, người phê duyệt SQL và lịch review. |
| **Phân vùng tài nguyên** | Bảng thô nằm **khác dataset** với view chia sẻ; location tương thích. |
| **IAM kế thừa** | Kiểm tra organization/folder/project/dataset/table/view và Google Groups. |
| **Quyền job** | Consumer có `bigquery.jobs.create` tại đúng execution project, không được quyền thừa. |
| **Quyền dữ liệu** | Consumer chỉ đọc những view/table cần thiết, không đọc source. |
| **Authorization entry** | Source dataset chỉ authorize view/dataset đã review. |
| **Quyền sửa SQL** | Trusted publishers tách với consumers; mọi thay đổi có code review. |
| **Bảo vệ hàng/cột** | Policy tags/masking/row policies được xem xét cho dữ liệu nhạy cảm. |
| **Kiểm thử** | Positive query qua view, negative query trực tiếp source và export/copy nếu phù hợp. |
| **Audit** | Có logs, người trực, quy trình thu hồi, rà soát bản sao và quyền kế thừa. |
| **Chi phí/SLO** | Query plan/dry run, filter/partition, quota, billing và latency được theo dõi. |

## 10. Tài liệu Google Cloud chính thức

- [BigQuery — Control access to resources with IAM](https://cloud.google.com/bigquery/docs/control-access-to-resources-iam): IAM cấp project/dataset/table/view và quyền kế thừa.
- [BigQuery — Access control with IAM](https://cloud.google.com/bigquery/docs/access-control): roles, permissions, dataset sharing và các nguyên tắc bảo vệ.
- [BigQuery — Create an authorized view](https://cloud.google.com/bigquery/docs/create-authorized-views): hướng dẫn thực hành hai dataset, cấp quyền analyst và authorize view.
- [BigQuery — Authorized views](https://cloud.google.com/bigquery/docs/authorized-views): phạm vi ủy quyền, SQL view và các lưu ý quyền.
- [BigQuery — Authorized datasets](https://cloud.google.com/bigquery/docs/authorized-datasets): ủy quyền một dataset chứa nhiều views và những quyền cần thiết.
- [BigQuery — Changes to dataset-level access controls](https://cloud.google.com/bigquery/docs/dataset-access-control): `getIamPolicy`/`setIamPolicy` và fine-grained ACL enforcement.
- [BigQuery — Row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro): kiểm soát đọc theo hàng.
- [BigQuery — Column-level access control](https://cloud.google.com/bigquery/docs/column-level-security-intro): policy tags và kiểm tra quyền cột.
- [BigQuery — Data masking](https://cloud.google.com/bigquery/docs/column-data-masking-intro): quyền xem giá trị masked/unmasked.
- [BigQuery — Audit logs](https://cloud.google.com/bigquery/docs/reference/auditlogs): hoạt động BigQuery và dữ liệu audit metadata.
- [BigQuery — Estimate query costs](https://cloud.google.com/bigquery/docs/best-practices-costs): dry run, bytes processed, kiểm soát chi phí.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing): giá query, storage và editions tại thời điểm triển khai.

**Kết luận:** bảo vệ BigQuery hiệu quả cần **quyền đúng principal, đúng phạm vi và đúng loại thao tác**. Consumer thường cần **Job User ở project chạy job** cộng **Data Viewer trên view/dataset được phép**; authorized view được source dataset ủy quyền để truy vấn bảng nguồn mà **không mở quyền đọc trực tiếp** cho consumer. Chỉ xem là hoàn thành khi đã kiểm tra quyền kế thừa, SQL view, khả năng truy cập bị từ chối, quy trình audit/thu hồi và chi phí truy vấn thực tế.
