# Catalog, metadata và khám phá dữ liệu trong Dataplex

Một doanh nghiệp bán lẻ có API đơn hàng trên **Cloud Run**, hệ thống giao dịch dùng **Cloud SQL/Spanner**, sự kiện qua **Pub/Sub**, dữ liệu thô ở **Cloud Storage** và bảng phân tích trong **BigQuery**. Một nhà phân tích hỏi: “Bảng doanh thu nào là chính thức, ai sở hữu, cập nhật khi nào, `net_revenue` được định nghĩa ra sao, có chứa PII không và tôi cần xin quyền ở đâu?”. Chỉ biết tên bucket hoặc bảng không đủ để trả lời.

**Data catalog** giải quyết vấn đề *tìm đúng tài sản dữ liệu và hiểu cách dùng chúng* bằng metadata. Trên Google Cloud, dịch vụ trước đây mang tên **Dataplex Universal Catalog**, hiện được tài liệu gọi là **Knowledge Catalog**. Các cấu hình đang dùng được giữ tương thích và nhiều lệnh CLI/API/IAM **vẫn có tiền tố `dataplex`**. Bài này dùng “Dataplex/Knowledge Catalog” để người học nhận diện đúng cả tài liệu cũ và giao diện hiện hành, không nhầm với sản phẩm **Data Catalog** đời trước. Xem [chuyển đổi tên sản phẩm](https://docs.cloud.google.com/knowledge-catalog/docs/transition-dataplex-universal-catalog).

Bài thuộc chương **Quản trị và khai thác dữ liệu**, mô-đun **CLOUD_PROVIDERS_GCP**. Trọng tâm là tổ chức catalog, hiểu **entries, aspects, business glossary**, tìm kiếm tài sản và phân quyền; các phần lineage, data quality, chi phí và vận hành được giới thiệu đủ để triển khai catalog hữu ích mà không biến nó thành nơi lưu dữ liệu giao dịch.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **data asset**, **metadata**, **catalog** và **quyền truy cập dữ liệu nguồn**.
2. Giải thích **entry group, entry, entry type, aspect type, aspect, entry link** và glossary term.
3. Hiểu **system entries** được tự động thu thập từ nguồn Google Cloud so với **custom entries** cho nguồn bên ngoài.
4. Tìm dữ liệu theo tên, cột, hệ thống, vị trí, nhãn, mô tả hoặc business metadata; hiểu phạm vi IAM và giới hạn kết quả tìm kiếm.
5. Bổ sung mô tả, chủ sở hữu, mức độ nhạy cảm, thời gian cập nhật và định nghĩa thuật ngữ nghiệp vụ.
6. Kết hợp metadata với **data lineage**, **data quality**, IAM, BigQuery views và quy trình cấp quyền thực tế.
7. Thực hành lệnh `gcloud dataplex` an toàn và thiết kế quy trình giữ metadata luôn đúng sau schema changes.

## 2. Catalog là bản đồ dữ liệu, không phải kho dữ liệu

### 2.1. Data và metadata khác nhau

| Khái niệm | Ví dụ bán lẻ | Nơi quản lý |
| --- | --- | --- |
| **Dữ liệu thực** | Các dòng `order_id`, `customer_email`, `amount_vnd`. | BigQuery, Cloud SQL, Cloud Storage... |
| **Metadata kỹ thuật** | Tên bảng, schema, region, kiểu dữ liệu, thời gian tạo. | Catalog đồng bộ với metadata hệ thống nguồn. |
| **Metadata nghiệp vụ** | “Doanh thu thuần”, owner, data steward, mức độ tin cậy, SLA cập nhật. | Aspects, mô tả, glossary và governance workflow. |
| **Data lineage** | `raw.orders` → Dataflow/BigQuery transform → `mart.daily_revenue`. | Data Lineage API/tích hợp hỗ trợ. |
| **Quyền đọc dữ liệu** | Analyst được `SELECT` trên view nhưng không trên bảng PII thô. | IAM, BigQuery dataset/table policies, row/column policies và nguồn tương ứng. |

**Catalog không tự chép toàn bộ rows vào một database thứ hai** chỉ vì tạo entry. Nó lưu *ngữ cảnh và chỉ mục mô tả* để người dùng tìm, đánh giá và yêu cầu cấp quyền cho tài sản đúng. Metadata có thể chứa tên cột nhạy cảm hoặc mô tả nội bộ, nên cũng cần phân quyền và quy tắc không đưa secrets vào notes.

### 2.2. Luồng khám phá dữ liệu

~~~mermaid
flowchart LR
    SRC["BigQuery / Cloud Storage / nguồn khác"] --> ING["Đồng bộ hoặc nhập metadata"]
    ING --> CATALOG["Knowledge Catalog"]
    OWNER["Data steward"] --> ASPECT["Ownership / classification / descriptions"]
    ASPECT --> CATALOG
    GOV["Glossary / quality / lineage"] --> CATALOG
    USER["Analyst"] --> SEARCH["Tìm kiếm catalog"]
    SEARCH --> CATALOG
    CATALOG --> INFO["Xem schema, owner, freshness, policy"]
    INFO --> ACCESS["Yêu cầu quyền tại hệ thống nguồn"]
    ACCESS --> QUERY["Query/view có IAM phù hợp"]
~~~

Catalog giúp người dùng trả lời lần lượt: **tìm ở đâu → nghĩa là gì → đáng tin không → có được phép dùng không → cần liên hệ ai**. Đừng bắt đầu bằng việc cấp `BigQuery Admin` chỉ để mọi người “thấy” một bảng trong tìm kiếm.

## 3. Mô hình metadata của Dataplex/Knowledge Catalog

### 3.1. Sáu đối tượng cốt lõi

| Đối tượng | Vai trò | Ví dụ |
| --- | --- | --- |
| **Entry group** | Vùng chứa và ranh giới quản trị cho các entries/entry links. | Nhóm hệ thống `@bigquery`; nhóm custom `partner-data`. |
| **Entry** | Một tài sản có thể khám phá. | Bảng `orders`, bucket, dashboard hoặc nguồn ngoài. |
| **Entry type** | Định nghĩa loại entry và các aspects bắt buộc. | System type `bigquery-table`; custom type `external-report`. |
| **Aspect type** | Khuôn mẫu/schema tái sử dụng cho một loại metadata. | `data-steward`, `data-sensitivity`, `freshness-policy`. |
| **Aspect** | Dữ liệu metadata theo aspect type, gắn vào entry hoặc cột. | `owner_team=finance`, `classification=confidential`. |
| **Entry link** | Quan hệ giữa entries, cột hoặc các khái niệm. | Term “doanh thu thuần” được liên kết tới cột `net_revenue`. |

~~~mermaid
flowchart TB
    GROUP["Entry group: @bigquery"] --> ENTRY["Entry: mart.daily_revenue"]
    TYPE["Entry type: bigquery-table"] --> ENTRY
    ASPECTTYPE["Aspect type: governance"] --> ASPECT["Aspect: owner=finance, tier=gold"]
    ASPECT --> ENTRY
    GLOSS["Glossary term: Doanh thu thuần"] --> LINK["Entry link: definition"]
    LINK --> ENTRY
~~~

Mỗi entry có định danh tài nguyên và có thể có **fully qualified name (FQN)** để liên hệ với nguồn. Aspect thuộc về **entry hoặc cột**; nó không phải một bảng BigQuery mới. Tùy loại hệ thống, có **aspects bắt buộc** mô tả schema và **aspects tùy chọn** gắn nghiệp vụ. Một số loại aspects do dịch vụ quản lý có thể xem nhưng **không được sửa trực tiếp**.

### 3.2. System entries và custom entries

- **System entries:** Knowledge Catalog tự động nhập metadata cho các nguồn được hỗ trợ như tài sản **BigQuery**; chúng thường ở **system entry groups** với tên bắt đầu `@`, ví dụ `@bigquery`. Không tự tạo/sửa/xóa system entry groups; việc xóa tài sản gốc có thể làm entry hệ thống biến mất.
- **Custom entries:** đội nền tảng tạo để mô tả nguồn chưa được tích hợp tự động như cơ sở dữ liệu đối tác, tập dữ liệu nội bộ ngoài Google Cloud hoặc tài sản theo cấu trúc riêng.
- **Custom entry type:** định nghĩa loại tài sản custom và aspects bắt buộc để các entries cùng loại có metadata nhất quán.
- **Custom aspect type:** xác định các field cần nhập, kiểu và hạn chế; có thể ở **regional** hoặc **global**. Global giúp tái sử dụng giữa regions, nhưng không nên chọn nếu chính định nghĩa aspect type chứa thông tin nhạy cảm phải tuân thủ data residency.

Không xem catalog là nơi tự động phát hiện *mọi bảng* trên mọi hệ thống. Phạm vi đồng bộ phụ thuộc **connector/sản phẩm hỗ trợ, API, IAM, cấu hình nguồn, vị trí và trạng thái ingestion**. Với nguồn ngoài, phải thiết kế connector/import và cập nhật định kỳ.

### 3.3. Ví dụ một entry hữu ích

| Trường metadata | Giá trị minh họa |
| --- | --- |
| Tài sản | `retail-analytics.mart.daily_revenue` (BigQuery table). |
| Business name | Doanh thu thuần theo ngày. |
| Mô tả | Tổng thanh toán sau hoàn tiền, theo ngày UTC; không gồm đơn bị hủy. |
| Grain | Một hàng cho mỗi `sale_date` và `channel`. |
| Owner | `finance-data` team; steward `data-governance` team. |
| Freshness | Cập nhật trước 07:00 giờ Việt Nam mỗi ngày. |
| Classification | `internal`; không công khai PII. |
| Quality | Không âm; dữ liệu thiếu không quá ngưỡng được phê duyệt. |
| Lineage | Nguồn `raw.payments` và `raw.refunds`, qua pipeline đã định danh. |
| Chứng nhận | Đã được đội Finance xác minh theo quy trình. |

**Các giá trị này chỉ là dữ liệu giả định để minh họa**, không phải metadata của bất kỳ bảng thực tế nào. Đừng ghi email cá nhân/tokens/password vào aspect. “Gold”, “certified”, “fresh” phải có **tiêu chí kiểm chứng và người chịu trách nhiệm**, không phải nhãn trang trí.

## 4. Business metadata: aspects, mô tả và glossary

### 4.1. Metadata được quản lý như một hợp đồng

Một aspect type `business-governance` có thể gồm:

| Field | Kiểu gợi ý | Quy tắc |
| --- | --- | --- |
| `owner_team` | String | Tên nhóm chịu trách nhiệm, không dùng một người duy nhất. |
| `data_class` | Enum | `public`, `internal`, `confidential`, `restricted`. |
| `sla_hours` | Integer | Số giờ kỳ vọng trước khi dữ liệu được cập nhật. |
| `purpose` | String | Mục đích sử dụng được chấp thuận. |
| `reviewed_at` | Date/time | Thời điểm steward rà soát. |

**Aspect type là template, aspect là giá trị gắn vào entry.** Ví dụ cùng một template được dùng cho bảng `daily_revenue`, `customer_profiles` và `product_metrics`, mỗi bảng có owner và classification riêng. Không dùng cùng một field với ba cách viết `Finance`, `finance-team`, `fin_analytics` nếu muốn lọc đáng tin cậy.

Metadata cho một column có thể chứa nhãn độ nhạy, mô tả hoặc định nghĩa thuật ngữ. Với BigQuery, các field **table description** và **column description** vẫn hữu ích cho công cụ truy vấn và trợ lý AI; không mặc định rằng mọi **custom aspect** sẽ được chuyển nguyên thành ngữ cảnh cho các tác vụ SQL của Gemini.

### 4.2. Business glossary tránh “cùng tên, khác nghĩa”

Ví dụ ba nhóm gọi “doanh thu” theo ba cách:

- Finance: số tiền đã ghi nhận sau điều chỉnh.
- Growth: tổng giá trị giỏ hàng tạo mới.
- Operations: tổng tiền thanh toán thành công.

Glossary tạo **term có định nghĩa được phê duyệt** như `Net Revenue`, `Gross Merchandise Value`, `Successful Payment Value`. Các term có thể được sắp vào **glossary/category**, có synonyms, related terms, người phụ trách và **liên kết tới entry/cột**. Tìm “doanh thu thuần” dẫn tới asset được định nghĩa đúng thay vì một bảng ngẫu nhiên có chữ `revenue`.

**Glossary không tự kiểm tra công thức SQL** và không thay data quality scans; người phụ trách phải cập nhật định nghĩa, mapping và quy trình phê duyệt khi nghiệp vụ thay đổi.

## 5. Khám phá dữ liệu: từ tìm kiếm đến quyết định sử dụng

### 5.1. Quy trình tự phục vụ cho analyst

1. Mở **Knowledge Catalog Search** trên Google Cloud console và chọn project/context được cấp quyền.
2. Tìm theo **mục đích nghiệp vụ** (“doanh thu thuần theo ngày”), tên hệ thống/bảng hoặc tên cột.
3. Lọc theo **system, type, project, location, labels** và metadata có thể tìm kiếm.
4. Mở entry, kiểm tra schema, description, glossary links, owner/contacts, quality và lineage nếu có.
5. Xác minh business grain, freshness, data classification, nguồn upstream và chính sách sử dụng.
6. Nếu chưa được cấp quyền truy vấn, liên hệ owner/request access tại **hệ thống nguồn**; không tìm cách dùng một service account khác để bỏ qua.
7. Thử query nhỏ hoặc preview bằng **quyền đã được cấp**, đối soát định nghĩa với nghiệp vụ trước khi đưa vào dashboard.

Kết quả tìm kiếm là **ứng viên**, không phải phê duyệt tự động rằng dữ liệu chính xác hoặc hợp lệ để dùng.

### 5.2. Cú pháp tìm kiếm metadata

Knowledge Catalog hỗ trợ tìm kiếm theo từ khóa, **semantic search** và **qualified predicates**. Ví dụ trên giao diện hoặc với `gcloud dataplex entries search`:

| Query | Tìm gì? |
| --- | --- |
| `daily_revenue` | Tài sản có tên/mô tả liên quan. |
| `system=bigquery type=table` | Các bảng BigQuery người dùng có thể khám phá. |
| `column:customer_id` | Entries có cột chứa chuỗi `customer_id`. |
| `description:"revenue"` | Metadata mô tả có token `revenue`. |
| `projectid:retail-analytics` | Tài sản có project ID phù hợp. |
| `location=asia-southeast1` | Tài sản ở vị trí cụ thể. |
| `labels.env=prod` | Nhãn `env` có giá trị chính xác `prod`. |
| `system=bigquery (type=table OR type=view)` | Bảng hoặc view của BigQuery. |
| `system=bigquery -name:test` | Loại các entries có tên chứa `test`. |

Quy tắc cần nhớ:

- `type=`, `system=`, `location=` là **exact match**, không thay bằng `type:` hoặc `system:`.
- `name:`, `column:` hỗ trợ substring; `description:` thường là token matching.
- `AND`, `OR`, `NOT` viết **chữ hoa**; dùng ngoặc khi kết hợp logic.
- Không dùng wildcard `*`/`?` như SQL `LIKE`; search có quy tắc riêng.
- `aspect`/metadata-field search hỗ trợ lọc theo các **aspect types/fields được index**; kiểm tra format ID và các kiểu field được phép lọc.
- Semantic search cải thiện khả năng tìm theo ý nghĩa, nhưng **không bảo đảm kết quả đầy đủ và không thay được kiểm tra IAM**.

Ví dụ `name:revenue` có thể trả nhiều bảng khác nhau; cần đọc mô tả và glossary để nhận biết bảng **đã được phê duyệt**.

### 5.3. Search khác listing và kiểm kê đầy đủ

**Search** dùng cho *khám phá*; **list/get** dùng cho *liệt kê và đọc resource có địa chỉ xác định*. Search có thể không trả toàn bộ entries khớp do **relevance, phạm vi, IAM hoặc giới hạn recall**; kết quả có thể khác giữa các lần truy vấn. Do đó:

- **Không dùng** `COUNT(search results)` làm báo cáo đầy đủ “công ty có bao nhiêu bảng”.
- Để **kiểm kê đầy đủ** ở quy mô lớn, dùng tính năng export metadata và truy vấn trên dataset được tạo ra theo hướng dẫn sản phẩm, hoặc API/list có phạm vi phù hợp và xử lý pagination.
- Khi tìm không thấy một bảng, xác minh nguồn có tồn tại, IAM metadata của người dùng, **search scope**, VPC Service Controls, hệ thống ingestion và trạng thái index; không mặc định dữ liệu đã bị xóa.

Search mặc định thường ở **phạm vi organization** của project truy vấn và chỉ trả entries người dùng có quyền xem; VPC Service Controls có thể giới hạn kết quả trong perimeter. **Catalog Viewer một mình chưa chắc giúp thấy metadata BigQuery** nếu principal không có quyền metadata tại hệ thống nguồn.

## 6. Thực hành `gcloud`: khám phá và kiểm tra metadata

Các lệnh sau là **Bash**, chỉ đọc; project/entry/group IDs đều là **ví dụ**, không bảo đảm tồn tại. Bạn cần cài `gcloud` đủ mới, bật các APIs cần thiết và dùng danh tính được cấp quyền. Khi chạy lab, sử dụng project thuộc phạm vi được phép.

### 6.1. Preflight: identity và project

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"

# READ-ONLY: kiểm tra danh tính và project cấu hình.
gcloud auth list
gcloud config get-value project

# READ-ONLY: không tự bật API hoặc tạo project nếu chưa được phép.
gcloud services list --enabled \
  --project="$PROJECT_ID" \
  --filter="name:dataplex.googleapis.com"
~~~

**Lưu ý tên:** sản phẩm mới có nhãn **Knowledge Catalog**, nhưng API vẫn là `dataplex.googleapis.com` và câu lệnh CLI vẫn có `gcloud dataplex`. Nếu dịch vụ đang được quản trị theo chính sách tổ chức, hãy yêu cầu admin bật API thay vì tự xin role Owner.

### 6.2. Tìm entries theo metadata

~~~bash
# READ-ONLY: tìm bảng BigQuery trong phạm vi project lab.
gcloud dataplex entries search \
  'system=bigquery type=table' \
  --project="$PROJECT_ID" \
  --scope="projects/$PROJECT_ID" \
  --limit=20 \
  --format="table(name,displayName)"

# READ-ONLY: tìm cột theo tên.
gcloud dataplex entries search \
  'column:customer_id' \
  --project="$PROJECT_ID" \
  --scope="projects/$PROJECT_ID" \
  --limit=20

# READ-ONLY: thử tìm theo ngữ nghĩa nếu CLI/version hỗ trợ.
gcloud dataplex entries search \
  'trusted daily revenue reports' \
  --project="$PROJECT_ID" \
  --scope="projects/$PROJECT_ID" \
  --semantic-search \
  --limit=20
~~~

`--project` xác định **project thực hiện request**, còn `--scope` giới hạn **tập tài sản cần tìm**; không nhầm chúng luôn đồng nghĩa. Phạm vi organization cần đúng org ID và IAM; scope chỉ còn trong project sẽ **không thấy** tài sản ở project analytics khác. Danh sách có thể rỗng vì chưa có nguồn phù hợp hoặc thiếu quyền metadata.

### 6.3. Xem entry groups và entries

~~~bash
# READ-ONLY: liệt kê entry groups trong location đã chọn.
gcloud dataplex entry-groups list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# READ-ONLY: với custom group đã tồn tại tên "partner-data".
gcloud dataplex entries list \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --entry-group="partner-data"

# READ-ONLY: chỉ chạy nếu entry ID thực sự có trong group.
gcloud dataplex entries describe "partner-orders" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --entry-group="partner-data"

# READ-ONLY: liệt kê custom aspect types ở location.
gcloud dataplex aspect-types list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

Đừng cố mô tả BigQuery table bằng `ENTRY_ID="dataset.table"` nếu chưa kiểm tra **entry ID và entry group ID mà catalog tạo**: tên hiển thị, FQN và resource ID không nhất thiết giống nhau. Các system groups như `@bigquery` có thể hiện ở location của nguồn; với BigQuery multi-region, location có thể là `us`/`eu`, không phải region nơi developer đang làm việc.

### 6.4. Đối chiếu metadata BigQuery tại nguồn

~~~bash
# READ-ONLY: resource mẫu phải tồn tại và principal đủ quyền.
bq show --schema --format=prettyjson \
  retail-analytics:mart.daily_revenue

# READ-ONLY: xem metadata cơ bản.
bq show --format=prettyjson \
  retail-analytics:mart.daily_revenue
~~~

So sánh schema/description/last modification ở hệ thống nguồn với entry catalog. Nếu chúng mâu thuẫn, **xác minh ingestion/index delay và người sở hữu nguồn**, không tự ghi đè system aspects để “sửa” dữ liệu catalog.

## 7. Làm giàu metadata: quy trình và ví dụ cấu hình

### 7.1. Bắt đầu từ thông tin người dùng thật sự cần

Không tạo hàng trăm aspect fields khi chưa có người sử dụng. Một **minimum viable catalog** cho doanh nghiệp bán lẻ thường cần:

1. **Description và grain:** dữ liệu này phản ánh điều gì, mỗi dòng là gì?
2. **Owner và steward:** ai phê duyệt cách dùng, ai nhận sự cố?
3. **Business term:** “doanh thu thuần” theo định nghĩa nào?
4. **Classification:** có PII, thông tin thanh toán hoặc bí mật kinh doanh không?
5. **Freshness:** dữ liệu được cập nhật lúc nào và trễ bao lâu được chấp nhận?
6. **Quality:** test nào chứng minh dữ liệu đáng tin và lần đo gần nhất ra sao?
7. **Lineage:** dữ liệu được tính từ nguồn nào, thay đổi ở upstream ảnh hưởng dashboard nào?

| Field | Tác động trực tiếp |
| --- | --- |
| Owner | Người sử dụng biết liên hệ ai khi số liệu sai hoặc cần cấp quyền. |
| Grain và business definition | Ngăn cộng nhầm số liệu từ bảng item-grain với order-grain. |
| Freshness SLO | Tránh dùng báo cáo cập nhật D-1 cho dashboard realtime. |
| Classification | Hỗ trợ chọn authorized view/masking và quy trình chấp thuận. |
| Lineage | Xác định ảnh hưởng khi thay đổi schema hoặc pipeline. |

### 7.2. Tạo aspect type qua console

Trong **Knowledge Catalog → Metadata types → Aspect types**, người quản trị có thể:

1. Chọn project và **location**: `global` nếu muốn tái sử dụng đa vùng, hoặc regional cho ràng buộc vị trí.
2. Tạo aspect type `business-governance`, khai báo các field như `owner_team`, `data_class`, `sla_hours`.
3. Định nghĩa kiểu dữ liệu và required/optional theo nhu cầu thực.
4. Lưu aspect type, phân quyền cho **đội steward** được phép gắn aspect.
5. Mở một entry, gắn optional aspect ở **entry level** hoặc cột hỗ trợ, nhập dữ liệu và xem lại qua Search.

**Ranh giới cần nhớ:** với system entry như BigQuery, các system aspects do Google quản lý thường **read-only**, trong khi optional business aspects có thể gắn/chỉnh nếu có quyền. Thay đổi `CREATE OR REPLACE TABLE` trên BigQuery có thể làm các aspects gắn với bảng gốc **không được giữ nguyên**; cần đưa bước kiểm tra/khôi phục metadata vào runbook migration, không mặc định metadata tồn tại vĩnh viễn sau replace.

### 7.3. Ví dụ map aspect khi có type đã được tạo

Giả sử tổ chức **đã tạo** aspect type `business-governance` tại `asia-southeast1`, với fields `owner_team STRING`, `data_class STRING`, `sla_hours INT`. Nội dung JSON sau là **đầu vào minh họa** cho CLI, không phải một file được tạo trong repo bài học:

~~~json
{
  "retail-lab.asia-southeast1.business-governance": {
    "data": {
      "owner_team": "finance-data",
      "data_class": "internal",
      "sla_hours": 24
    }
  }
}
~~~

Sau khi lưu JSON này vào file `governance-aspect.json` trong **môi trường lab riêng**, và xác minh **đúng entry ID, entry group và location**, lệnh cập nhật có dạng:

~~~bash
# WRITE: CHỈ chạy khi có approval và resources/type có thật.
gcloud dataplex entries update-aspects "partner-orders" \
  --project="retail-lab" \
  --location="asia-southeast1" \
  --entry-group="partner-data" \
  --aspects="governance-aspect.json"

# READ-ONLY: đọc lại entry để xác minh aspect mới.
gcloud dataplex entries describe "partner-orders" \
  --project="retail-lab" \
  --location="asia-southeast1" \
  --entry-group="partner-data"
~~~

Các chuỗi tài nguyên là **giả định**; lệnh chỉ thành công nếu entry và type đã tồn tại, schema khớp và principal đủ permissions. `update-aspects` **không thay thế toàn bộ aspect map của entry**, nhưng với **mỗi aspect được nêu trong file** có thể **thay thế toàn bộ nội dung của aspect đó**, không tự merge từng field; phải đọc phiên bản hiện tại trước khi ghi để tránh xóa ngầm metadata của người khác. Tham khảo [gcloud entries update-aspects](https://docs.cloud.google.com/sdk/gcloud/reference/dataplex/entries/update-aspects).

### 7.4. Tự động hóa metadata updates

Trong CI/CD data pipelines:

~~~mermaid
flowchart LR
    CHANGE["PR thay schema / đổi pipeline"] --> TEST["Schema + contract tests"]
    TEST --> DEPLOY["Triển khai BigQuery/Dataflow"]
    DEPLOY --> CHECK["Kiểm tra catalog đồng bộ"]
    CHECK --> META["Steward review aspect/glossary"]
    META --> SEARCH["Search + access tests"]
    SEARCH --> DONE["Bàn giao thay đổi"]
~~~

Với custom source, có thể lập job định kỳ đọc metadata hệ thống nguồn, tạo/cập nhật entry/aspect theo **upsert có kiểm soát**, ghi audit log và đánh dấu metadata không còn nguồn. Với system source, ưu tiên **API nguồn** cho những thuộc tính mà nguồn sở hữu (schema, description); không duy trì một bản metadata thủ công trái ngược nguồn.

## 8. Data lineage, data profiling và data quality

### 8.1. Lineage trả lời “số liệu đi từ đâu?”

~~~mermaid
flowchart LR
    APP["Cloud Run: payments"] --> RAW["BigQuery raw.payments"]
    APP2["Refund API"] --> REF["BigQuery raw.refunds"]
    RAW --> TRANS["BigQuery/Dataflow transform"]
    REF --> TRANS
    TRANS --> MART["mart.daily_revenue"]
    MART --> DASH["Finance dashboard"]
~~~

Lineage giúp:

- **Upstream tracing:** `mart.daily_revenue` được tạo từ những bảng và công việc nào?
- **Impact analysis:** nếu đổi schema `raw.refunds`, những bảng/dashboard phía sau có thể bị ảnh hưởng?
- **Incident investigation:** kết quả sai bắt đầu từ source, transform hay dữ liệu chưa cập nhật?

Trong hệ sinh thái Google Cloud, **Data Lineage API** có thể nhận metadata tự động từ **các tích hợp được hỗ trợ** sau khi bật API, hoặc từ **OpenLineage/custom events**. Không phải mọi lệnh SQL, UDF, API bên ngoài hoặc pipeline custom đều được tự động theo dõi đầy đủ: cần kiểm tra **coverage, project/region và quyền xem lineage**. Lineage có thể phát sinh **phí xử lý và lưu metadata**.

### 8.2. Data profiling khác quality scan

| Tính năng | Ví dụ | Giới hạn |
| --- | --- | --- |
| **Data profiling** | Phân bố giá trị, null rate, min/max, cardinality của cột. | Thống kê mô tả không tự chứng minh quy tắc nghiệp vụ đúng. |
| **Data quality scan** | `order_id` không null, `amount_vnd >= 0`, uniqueness threshold, freshness rule. | Cần định nghĩa/duy trì rules và xử lý failures. |
| **Quality aspect/scorecard** | Trạng thái scan gần nhất, điểm chất lượng, thời gian chạy. | Không thay quyền query; có thể thiếu/muộn khi scan chưa chạy. |
| **Lineage** | Đường dữ liệu qua transforms. | Không bảo đảm một transform thực thi đúng công thức nghiệp vụ. |
| **Glossary/certification** | Term, owner và xác nhận độ tin cậy. | Cần governance review, không tự biến tài sản thành dữ liệu hợp pháp để dùng. |

Một bảng “certified” mà data quality scan thất bại hôm nay phải bị đánh dấu và điều tra. Tạo **quy tắc vận hành**: nếu freshness vượt SLO hoặc null rate vượt ngưỡng, alert cho owner, xem lại certification và ghi incident. Đừng xóa kết quả scan cũ để làm scorecard đẹp hơn.

## 9. IAM: quyền xem catalog tách biệt quyền đọc dữ liệu

### 9.1. Ai cần quyền gì?

| Persona | Nhu cầu | Quyền xem xét |
| --- | --- | --- |
| **Data analyst** | Tìm asset, xem metadata, đề nghị truy cập. | `roles/dataplex.catalogViewer` cùng quyền metadata nguồn (ví dụ `roles/bigquery.metadataViewer`). |
| **Data consumer** | Chạy BigQuery query trên dữ liệu đã cấp phép. | Quyền BigQuery job (`roles/bigquery.jobUser` ở project thực hiện job) và `dataViewer`/view phù hợp. |
| **Steward** | Duy trì mô tả/aspects/glossary, xác nhận owner. | Role Dataplex Entry/Aspect Type User/Editor theo scope tối thiểu, tùy operation. |
| **Platform catalog admin** | Tạo entry groups/types, cấp quyền metadata. | Role catalog admin hoặc custom role có permissions cụ thể. |
| **Data engineering pipeline** | Nhập metadata custom, cập nhật aspects. | Service account chuyên biệt với quyền create/update entry/aspect theo group/type. |
| **Auditor** | Xem policies, logs, lineage/quality. | Viewer riêng cho catalog/lineage/logs; không mặc định truy cập dữ liệu gốc. |

Tên roles cụ thể có thể khác theo loại resource và thao tác; kiểm tra [Dataplex IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/dataplex). **Không cấp `roles/owner`, `roles/editor` hoặc BigQuery Admin cho tất cả analyst chỉ để search**.

### 9.2. Metadata visibility và data visibility

- **Có quyền tìm một entry** không mặc nhiên có `SELECT` trên bảng BigQuery, quyền đọc object Cloud Storage hay xem dữ liệu nhạy cảm.
- Đối với **system entries**, kết quả search tôn trọng **quyền metadata ở nguồn**. Người dùng thiếu quyền BigQuery metadata có thể không thấy bảng, dù catalog entry đã tồn tại.
- **Custom catalog entry** cũng có IAM riêng cho entry group/type và metadata; quyền này không tạo quyền trên hệ thống ngoài được mô tả trong entry.
- **Policy tags**, column-level security, masking, row access policies và authorized views được **thực thi ở dịch vụ dữ liệu**, không phải vì entry có aspect `confidential`.
- Search chịu ảnh hưởng của **organization scope**, VPC Service Controls và IAM; một quyền catalog rộng không xuyên được mọi perimeter.

**Ví dụ:** analyst có thể được thấy bảng `mart.daily_revenue` và schema nhưng chỉ được query **view đã che thông tin khách hàng**. Nếu thấy tên cột PII trong catalog, điều đó không có nghĩa được đọc giá trị của cột đó.

## 10. Case study: xây catalog cho dữ liệu bán lẻ

### 10.1. Bối cảnh

Hệ thống có:

- `raw.payments`: dữ liệu thanh toán từ Cloud Run/Pub/Sub vào BigQuery.
- `raw.refunds`: hoàn tiền từ dịch vụ nội bộ.
- `mart.daily_revenue`: bảng tổng hợp dùng cho báo cáo tài chính.
- Một bucket Cloud Storage chứa dữ liệu ingestion cũ và logs.
- Hai đội đang báo cáo **hai số “revenue” khác nhau**.

Đội dữ liệu cần xác định bộ tài sản **được phép dùng** trước kỳ chốt sổ, không chỉ “tạo một catalog rồi hoàn tất”.

### 10.2. Kế hoạch triển khai

| Giai đoạn | Hoạt động | Tiêu chí hoàn tất |
| --- | --- | --- |
| **1. Kiểm kê** | Xác nhận BigQuery/Cloud Storage assets và metadata được nhập vào catalog. | Search được các tables, thấy đúng schema/location. |
| **2. Chuẩn hóa thuật ngữ** | Finance định nghĩa net/gross revenue, refund cutoff và timezone. | Glossary có owner và phép tính được phê duyệt. |
| **3. Gắn metadata** | Mô tả grain, owner, classification, SLA và contacts. | Mỗi bảng critical có required metadata. |
| **4. Liên kết** | Gắn glossary terms vào tables/columns; kiểm tra lineage từ nguồn. | Analyst phân biệt được raw, staging, mart. |
| **5. Chứng minh độ tin cậy** | Thiết lập profiling/quality checks, đối soát với nguồn. | Freshness và quality thresholds có kết quả gần đây. |
| **6. Cấp quyền có kiểm soát** | Authorized view hoặc quyền dataset/table theo nhu cầu. | Analyst query được đúng tài sản, PII vẫn bảo vệ. |
| **7. Vận hành** | Alert khi schema đổi, metadata lỗi thời, owner rời nhóm. | Có steward review và audit/changelog định kỳ. |

### 10.3. Trải nghiệm analyst

Analyst tìm:

~~~text
system=bigquery type=table name:revenue
~~~

Sau đó mở entry `mart.daily_revenue` và kiểm tra:

1. **Definition:** `net_revenue = payments_successful - refunds_recorded`, kỳ ngày UTC hay giờ Việt Nam?
2. **Grain:** `sale_date × channel` hay `sale_date × SKU`?
3. **Freshness:** cập nhật 07:00 ICT có đúng yêu cầu báo cáo 06:00 không?
4. **Quality:** lần scan gần nhất PASS hay FAIL, metric thiếu null/duplicate là bao nhiêu?
5. **Lineage:** cột `refund_amount` lấy từ nguồn nào và có xử lý late refunds không?
6. **Access:** view nào được Finance chứng nhận, cần ai phê duyệt nếu thiếu quyền?

Nếu hai bảng cùng tên `daily_revenue`, **không chọn tùy tiện bảng xuất hiện đầu kết quả**. So owner, glossary, lineage và certification; cần trao đổi với Finance trước khi công bố số.

## 11. Vận hành, chất lượng metadata và chi phí

### 11.1. Metadata cũng có “freshness SLO”

Một catalog tốt phải duy trì **độ đúng của metadata**:

| Chỉ số vận hành | Cách đo gợi ý | Hành động khi không đạt |
| --- | --- | --- |
| **Coverage** | Tỷ lệ bảng trọng yếu có entry và owner. | Đồng bộ nguồn, bổ sung ownership. |
| **Description completeness** | Tỷ lệ entries có mô tả/grain đã kiểm tra. | Giao steward cập nhật. |
| **Metadata freshness** | Thời gian từ schema change đến lúc entry được cập nhật. | Kiểm tra ingestion/index; phát cảnh báo. |
| **Glossary coverage** | Tỷ lệ metrics kinh doanh có term được duyệt. | Tổ chức review với Finance/Growth. |
| **Quality signal age** | Tuổi của lần data quality scan gần nhất. | Chạy lại scan, kiểm tra job và nguồn. |
| **Broken ownership** | Entries có owner team không tồn tại. | Thay owner theo roster nhóm. |
| **Discovery success** | Tỷ lệ yêu cầu tìm được tài sản đúng và được cấp quyền đúng hạn. | Cải thiện description, synonyms, workflow IAM. |

**SLO minh họa:** “100% bảng báo cáo tài chính có owner, description và business term; metadata thay đổi được xác minh trong 24 giờ”. Đây là mục tiêu nội bộ giả định, **không phải SLA Knowledge Catalog**.

### 11.2. Chi phí và giới hạn cần xem

Catalog không chỉ có chi phí “tìm kiếm”:

- **Metadata storage** có thể được tính phí theo dung lượng metadata được lưu giữ.
- **Tạo/quản lý metamodel resources** (entry types, aspect types, entry groups, entries, links) và **search calls** có thể thuộc danh mục không tính phí riêng theo tài liệu giá, nhưng vẫn có quotas và IAM.
- **Data lineage** có SKU xử lý và lưu metadata; bật API trên project có nhiều hoạt động có thể tăng chi phí.
- **Profiling/quality scans** chạy job xử lý dữ liệu nên cần dự toán riêng theo loại tài nguyên và bảng giá hiện hành.
- **BigQuery** dùng để preview, quality validation, query hoặc metadata export vẫn có thể phát sinh chi phí query/compute/storage.
- **Connector/import jobs**, Cloud Run/GKE, Pub/Sub change feeds, logs/Monitoring cũng có chi phí thực tế.

Đo **giá trị vận hành**: số giờ tiết kiệm được khi tìm data, thời gian cấp quyền, số incident do hiểu nhầm metric, cùng chi phí metadata/quality/lineage. Không lưu dữ liệu nhạy cảm hoặc toàn bộ raw rows vào custom aspects chỉ để tăng chất lượng search.

### 11.3. Quy trình xử lý thay đổi schema

Giả sử đội kỹ thuật đổi cột `amount` thành `gross_amount`:

1. Mở **change request** có danh sách downstream consumers từ lineage/biên bản kiểm kê.
2. Giữ **view tương thích** hoặc có kế hoạch migration theo phiên bản.
3. Áp schema change tại BigQuery rồi kiểm tra metadata system entry được làm mới.
4. Cập nhật descriptions, aspect field references và glossary mapping.
5. Chạy lại quality tests, xác nhận owner/certification nếu kết quả thay đổi.
6. Kiểm tra catalog search bằng cả tên cũ/mới theo mục đích, so với hệ thống nguồn.
7. Ghi audit và phương án rollback nếu thiếu dữ liệu, mất aspect hoặc dashboard lỗi.

**Không sửa tên field chỉ trong catalog để che việc source schema chưa đổi**. Catalog phản ánh và chú giải trạng thái nguồn; thay đổi nguồn phải được vận hành bằng pipeline/schema governance riêng.

## 12. Troubleshooting: vì sao không tìm được dữ liệu?

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| Không thấy bảng BigQuery trong Search | Thiếu metadata IAM ở bảng/dataset, sai scope/project/perimeter. | `bq show` với principal hiện tại; scope, VPC SC, IAM. |
| Search ra bảng nhưng query 403 | Có quyền metadata, thiếu quyền data hoặc job permission. | BigQuery IAM/Data Viewer/Job User và row/column policies. |
| Entry tồn tại nhưng schema cũ | Chậm ingestion/indexing, nguồn chưa cập nhật. | Metadata tại nguồn, thời gian sửa, trạng thái catalog. |
| Hai entries cùng tên khác nghĩa | Thiếu owner/glossary/description hoặc trùng copy. | FQN, project, glossary mapping và certified assets. |
| `system:bigquery` không lọc đúng | Dùng `:` thay vì exact `=`. | `system=bigquery type=table`. |
| Entry group `@bigquery` không sửa được | System group do dịch vụ quản lý. | Không sửa trực tiếp; quản trị nguồn và optional aspects. |
| Gắn aspect thất bại | Aspect type không tồn tại, khác location, sai field type hoặc thiếu role. | `aspect-types list`, schema template, IAM. |
| Ghi aspect làm mất một field cũ | `update-aspects` thay thế nội dung aspect đã chỉ định. | So sánh JSON trước/sau, update đầy đủ fields. |
| Glossary term không tìm ra bảng | Term chưa liên kết entry/cột hoặc index chưa cập nhật. | Entry links, term details, quyền người dùng. |
| Không thấy lineage | Data Lineage API chưa bật, thiếu quyền/nguồn không được hỗ trợ. | Project settings, run logs, lineage coverage. |
| Data quality scorecard cũ | Scan chưa chạy, đã lỗi hoặc không gắn metadata. | Scan jobs, timestamps, scorecard aspects. |
| Metadata biến mất sau replace table | `CREATE OR REPLACE TABLE` thay asset dẫn đến mất custom aspects cũ. | Audit, backup metadata, quy trình tái gắn. |
| Search trả ít hơn kết quả kiểm kê | Search không cam kết full recall và áp IAM. | Dùng metadata export/list cho inventory, không dựa `COUNT(search)`. |

**Runbook ngắn:** xác định `project/region/FQN` → kiểm tra nguồn còn tồn tại → kiểm tra principal và quyền xem metadata → kiểm tra phạm vi Search/VPC SC → xem ingestion/entry/aspects → so mô tả/owner/quality/lineage → đề xuất sửa có approval. Không “khắc phục” thiếu metadata bằng cách cấp project Owner.

## 13. Bài tập

### Bài 1 — Data hay metadata?

Phân loại: (a) `order_id=O-1001`, (b) field `amount_vnd NUMERIC`, (c) `owner_team=finance`, (d) kết quả scan “null 2%”, (e) IAM cho phép SELECT. Mục nào là metadata, mục nào là dữ liệu thực, mục nào là chính sách truy cập?

### Bài 2 — Thiết kế entry

Với bảng `daily_revenue`, hãy đề xuất ít nhất 6 thuộc tính metadata để người mới quyết định có thể dùng cho báo cáo. Nêu **grain**, owner, freshness, độ nhạy, glossary term và test chất lượng.

### Bài 3 — Entry, aspect type, aspect

Một tổ chức muốn chuẩn hóa `owner_team`, `data_class`, `sla_hours` trên 300 bảng. Đối tượng nào dùng làm **template tái sử dụng**, đối tượng nào chứa **giá trị riêng của từng bảng**, và trường hợp nào cần custom entry type?

### Bài 4 — Search syntax

Viết ba truy vấn tìm: (a) mọi bảng BigQuery có tên liên quan `revenue`; (b) entries có cột `customer_id`; (c) BigQuery views trong project `retail-analytics` ở region hỗ trợ. Giải thích vì sao `type:table` không đúng cú pháp.

### Bài 5 — Không tìm thấy bảng

Hai analyst cùng search cùng query nhưng chỉ một người thấy bảng. Hãy lần lượt kiểm tra **IAM metadata tại nguồn, phạm vi organization/project, VPC Service Controls, index/ingestion** trước khi nghi ngờ bảng bị xóa.

### Bài 6 — Quyền xem khác quyền query

Analyst đã thấy mô tả bảng `raw.customers` nhưng `SELECT` báo 403. Hãy thiết kế cách cấp quyền qua **authorized view/masking** để không cho phép đọc PII trực tiếp; giải thích vì sao `roles/dataplex.catalogViewer` không giải quyết truy vấn.

### Bài 7 — Lineage và glossary

Finance định nghĩa `Net Revenue = Successful Payments − Refunds`. Vẽ quan hệ glossary term ↔ bảng/cột `mart.daily_revenue`; nêu upstream sources và tác động khi đổi schema `raw.refunds`.

### Bài 8 — Cập nhật aspect

Một aspect `business-governance` đang có ba fields, pipeline chỉ gửi một field trong file update. Điều gì có thể xảy ra với các fields còn lại? Viết checklist đọc trước–ghi sau–xác minh, phân quyền và audit.

### Bài 9 — Quality và chứng nhận

Một bảng được gắn “certified” nhưng quality scan gần nhất cách đây 60 ngày và có 8% mã khách hàng bị null. Có nên dùng báo cáo này ngay không? Ai quyết định và cần bổ sung bằng chứng gì?

### Bài 10 — Đo thành công của catalog

Đội data governance quản lý 500 bảng, mới 320 bảng có owner, 200 có descriptions, 120 có glossary terms. Tính tỷ lệ coverage từng tiêu chí và đề xuất mục tiêu ưu tiên 30 ngày; phân biệt **bảng không có metadata** với **catalog không thể tìm thấy do IAM**.

**Gợi ý:** owner **64%**, description **40%**, glossary **24%**. Đây là coverage trên tập 500 bảng được kiểm kê từ nguồn, **không phải số đo có thể suy ra chắc chắn từ kết quả search**.

## 14. Checklist production và tài liệu chính thức

| Hạng mục | Tiêu chí kiểm chứng |
| --- | --- |
| **Product/API** | Nhận biết Knowledge Catalog (trước đây Dataplex Universal Catalog); CLI/IAM vẫn `dataplex`. |
| **Inventory** | Có scope, nguồn nhập metadata và đối chiếu với kiểm kê hệ thống nguồn. |
| **Metamodel** | Entry groups/types, aspects/links được chuẩn hóa theo domain, không dư thừa. |
| **Business context** | Owner, steward, grain, description, glossary terms và use policy có người phê duyệt. |
| **Discovery** | Search filters đúng cú pháp; hiểu result trimming, quyền metadata và recall limits. |
| **Lineage/quality** | Coverage, scan timestamps, alerts và tác động downstream được theo dõi. |
| **Security** | IAM catalog tách IAM dữ liệu; PII/masking/authorized views ở nguồn. |
| **Locations** | Global/regional aspect types, location resource và data residency được xem xét. |
| **Automation** | Schema changes/`CREATE OR REPLACE TABLE` kiểm tra metadata và glossary links. |
| **Observability** | Coverage, freshness, search success, governance change logs và metadata drift. |
| **Cost** | Metadata storage, lineage, quality scans, data queries và vận hành connector dự toán. |
| **Recovery** | Có kế hoạch khôi phục metadata custom và rollback schema/permission changes. |

Tài liệu chính thức để đối chiếu giao diện và API:

- [Knowledge Catalog — tổng quan](https://docs.cloud.google.com/knowledge-catalog/docs)
- [Chuyển đổi Dataplex Universal Catalog sang Knowledge Catalog](https://docs.cloud.google.com/knowledge-catalog/docs/transition-dataplex-universal-catalog)
- [Metadata model: entry, entry type, aspect và entry link](https://docs.cloud.google.com/knowledge-catalog/docs/metadata-overview)
- [Manage entries và ingest custom sources](https://docs.cloud.google.com/knowledge-catalog/docs/ingest-custom-sources)
- [Search assets](https://docs.cloud.google.com/knowledge-catalog/docs/search-assets)
- [Search syntax](https://docs.cloud.google.com/knowledge-catalog/docs/search-syntax)
- [Manage aspect types và aspects](https://docs.cloud.google.com/knowledge-catalog/docs/enrich-entries-metadata)
- [Manage business glossaries](https://docs.cloud.google.com/knowledge-catalog/docs/manage-glossaries)
- [About data lineage](https://docs.cloud.google.com/knowledge-catalog/docs/about-data-lineage)
- [Knowledge Catalog IAM](https://docs.cloud.google.com/knowledge-catalog/docs/iam-permissions)
- [gcloud dataplex entries search](https://docs.cloud.google.com/sdk/gcloud/reference/dataplex/entries/search)
- [gcloud dataplex entries update-aspects](https://docs.cloud.google.com/sdk/gcloud/reference/dataplex/entries/update-aspects)
- [Knowledge Catalog pricing](https://cloud.google.com/dataplex/pricing)

**Ghi nhớ:** Dataplex/Knowledge Catalog không thay BigQuery, Cloud Storage hay hệ thống nguồn: nó giúp **tìm đúng tài sản, hiểu metadata, liên kết định nghĩa nghiệp vụ và đánh giá độ tin cậy**. **Entry** là tài sản, **aspect** bổ sung ngữ cảnh, **glossary** thống nhất thuật ngữ, **lineage** cho biết nguồn gốc, còn **IAM của hệ thống nguồn** quyết định quyền đọc dữ liệu. Catalog có giá trị khi metadata được duy trì **đúng, mới, có người chịu trách nhiệm và có kiểm chứng**, không chỉ khi ô tìm kiếm trả về kết quả.



