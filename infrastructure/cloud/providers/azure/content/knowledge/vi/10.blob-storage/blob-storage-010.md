# Blob index tag, metadata và tìm kiếm đối tượng

> **Chương:** Lưu trữ đối tượng với Blob Storage  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **thuộc tính hệ thống của blob**, **metadata** và **blob index tags**.
2. Chọn đúng cách tìm đối tượng: theo **tên/prefix**, theo **tags được lập chỉ mục**, hay theo **nội dung tài liệu**.
3. Đặt, đọc và truy vấn blob index tags bằng Azure CLI hoặc Azure Storage SDK.
4. Viết biểu thức lọc theo tags, hiểu phạm vi storage account, phân biệt tìm kiếm từ chỉ mục với đọc tags của một blob cụ thể.
5. Giải thích tính **nhất quán cuối cùng** của chỉ mục, quyền truy cập dữ liệu, lưu ý bảo mật và chi phí.
6. Thiết kế quy ước đặt tên, metadata và tags cho một luồng xử lý tài liệu trên Azure.

## 1. Bài toán: tìm tài liệu trong hàng triệu blob

Một hệ thống kế toán tải hóa đơn, hợp đồng và báo cáo lên Azure Blob Storage. Mỗi blob có tên dạng:

~~~text
storage account: stdocslab001
container:       documents

invoices/2026/01/invoice-0001.pdf
invoices/2026/01/invoice-0002.pdf
contracts/2026/contract-0071.pdf
reports/2026/quarter-1.csv
~~~

Ứng dụng cần trả lời các câu hỏi khác nhau:

- **Tên hoặc đường dẫn:** Có những blob nào dưới prefix `invoices/2026/01/`?
- **Dữ liệu mô tả:** Blob `invoice-0001.pdf` được nhập từ hệ thống nào, do quy trình nào tạo?
- **Phân loại nghiệp vụ:** Những tài liệu nào có `Project=Atlas` và `ReviewStatus=Approved`, bất kể nằm trong thư mục ảo nào?
- **Nội dung tài liệu:** Có tài liệu PDF nào chứa cụm từ “điều khoản thanh toán” không?

Bốn câu hỏi này cần những cơ chế khác nhau. **Azure Blob Storage không tự lập chỉ mục tìm kiếm toàn văn PDF**, còn metadata thông thường không cung cấp truy vấn server-side giống blob index tags.

Ví dụ tổ chức lưu:

| Blob | Metadata | Blob index tags |
| --- | --- | --- |
| `invoices/2026/01/invoice-0001.pdf` | `source=erp`, `pipeline=ingest-v2` | `Project=Atlas`, `ReviewStatus=Approved`, `Year=2026` |
| `invoices/2026/01/invoice-0002.pdf` | `source=erp`, `pipeline=ingest-v2` | `Project=Atlas`, `ReviewStatus=Pending`, `Year=2026` |
| `contracts/2026/contract-0071.pdf` | `source=crm`, `pipeline=contract-sync` | `Project=Orion`, `ReviewStatus=Approved`, `Year=2026` |

Bộ lọc `"Project" = 'Atlas' AND "ReviewStatus" = 'Approved'` trả về **invoice-0001.pdf**, vì dịch vụ có thể dùng **chỉ mục tags** để tìm đối tượng. Muốn tìm mọi blob có metadata `source=erp`, ứng dụng cần hướng khác, chẳng hạn liệt kê rồi đọc/lọc metadata hoặc xây một chỉ mục riêng.

## 2. Cấu trúc một blob và ba loại thông tin

Một **storage account** chứa các container; container chứa các **blob**. Mỗi blob có nội dung, tên và những dữ liệu đi kèm.

~~~mermaid
flowchart TD
    A["Storage account\nstdocslab001"]
    C["Container\ndocuments"]
    B["Blob\ninvoices/2026/01/invoice-0001.pdf"]
    P["System properties\nETag, Last-Modified, Content-Type"]
    M["User metadata\nsource=erp, pipeline=ingest-v2"]
    T["Blob index tags\nProject=Atlas, ReviewStatus=Approved"]
    I["Blob tag index\nFind Blobs by Tags"]
    A --> C --> B
    B --> P
    B --> M
    B --> T --> I
~~~

### 2.1. Thuộc tính hệ thống (system properties)

Azure Blob Storage quản lý nhiều thuộc tính của blob, ví dụ:

- `Content-Length`: kích thước đối tượng.
- `Content-Type`: kiểu nội dung do người tải hoặc ứng dụng khai báo, ví dụ `application/pdf`.
- `ETag`: mã phiên bản/điều kiện để hỗ trợ kiểm soát cập nhật cạnh tranh.
- `Last-Modified`: thời điểm chỉnh sửa theo ngữ nghĩa của dịch vụ.
- Access tier, lease state và những thuộc tính khác tùy loại blob/cấu hình.

Các trường này **không phải** user-defined metadata hoặc blob index tags. Một số trường có thể xem qua Get Blob Properties, liệt kê blobs hoặc API chuyên biệt. Không nên dùng `Content-Type` làm nhãn phân loại nghiệp vụ cần thay đổi liên tục.

### 2.2. Metadata do người dùng tự định nghĩa

**Blob metadata** là các cặp key–value do ứng dụng gắn vào blob. Ví dụ:

~~~text
source=erp
pipeline=ingest-v2
documentowner=finance-team
ingestedat=2026-11-20T08:30:00Z
~~~

Metadata thích hợp để mô tả **nguồn gốc, cách tạo và bối cảnh vận hành** của một đối tượng. Dữ liệu được lưu cùng blob, nhưng **không được Blob Storage tự lập chỉ mục để tìm bằng một biểu thức metadata**.

Ví dụ: không có phép truy vấn tương đương “find all blobs where metadata.pipeline = ingest-v2” trực tiếp qua dịch vụ chỉ mục tags. Có thể dùng **List Blobs** để liệt kê theo container/prefix và yêu cầu kèm metadata nếu API/SDK hỗ trợ, sau đó lọc ở ứng dụng; cách này cần đọc nhiều bản ghi khi dữ liệu lớn.

Metadata được truyền như các HTTP header dạng `x-ms-meta-<key>` trong những thao tác REST phù hợp. Metadata có giới hạn tổng dung lượng và quy tắc đặt tên; không dùng nó như nơi lưu JSON lớn hoặc văn bản dài.

### 2.3. Blob index tags

**Blob index tags** cũng là các cặp key–value gắn với từng blob, nhưng Azure Blob Storage duy trì **chỉ mục tìm kiếm** cho chúng. Ví dụ:

~~~text
Project=Atlas
ReviewStatus=Approved
Year=2026
Sensitivity=Internal
~~~

Nhờ chỉ mục, ứng dụng có thể tìm những blob có tags phù hợp **trên phạm vi storage account**, kể cả khi chúng nằm ở các container hoặc prefix khác nhau, thông qua thao tác **Find Blobs by Tags**.

Các đặc điểm thiết kế:

- Tags là **chuỗi**, không phải cột kiểu số hoặc ngày được ép kiểu tự động.
- Một blob có **tối đa 10 index tags**; key/value có giới hạn độ dài và ký tự được phép.
- Key là duy nhất trong bộ tags của một blob; tên key và giá trị phải tuân thủ quy tắc dịch vụ.
- Tên và giá trị tag có phân biệt chữ hoa/chữ thường trong so sánh; nên thống nhất quy ước.
- Tạo hoặc cập nhật tags và cập nhật chỉ mục là hai việc có thời gian hoàn tất có thể khác nhau: **kết quả tìm kiếm có thể trễ** sau một thay đổi.
- Không phải mọi tính năng của mọi loại tài khoản lưu trữ đều hỗ trợ giống nhau. Kiểm tra khả năng blob index tags với loại account, namespace, phiên bản API và dịch vụ định sử dụng.

**Quy tắc thực tế:** dùng tags cho những **thuộc tính cần tìm lọc ở quy mô lớn**; dùng metadata cho thông tin **mô tả blob nhưng không cần tìm bằng chỉ mục**.

## 3. Metadata và blob index tags: bảng so sánh

| Tiêu chí | Metadata | Blob index tags |
| --- | --- | --- |
| Mục đích | Mô tả nguồn gốc, cấu hình, bối cảnh của blob | Phân loại và tìm blob theo điều kiện |
| Lưu trữ | Cặp key–value gắn với blob | Cặp key–value gắn với blob, được lập chỉ mục riêng |
| Query server-side theo key/value | **Không** có cơ chế tìm kiếm metadata gốc tương đương Find Blobs by Tags | **Có**, qua Find Blobs by Tags |
| Đọc trên một blob đã biết | Get Blob Properties/Get Metadata | Get Blob Tags |
| Phạm vi tìm | Thường liệt kê blob trong container/prefix rồi lọc hoặc tạo index bên ngoài | Tìm trong storage account và có thể thêm điều kiện container |
| Kiểu dữ liệu | Chuỗi được lưu theo quy tắc metadata | Chuỗi; so sánh theo quy tắc tag query |
| Số lượng/kích thước | Bị giới hạn theo tổng metadata và quy tắc header | Tối đa 10 tags/blob và giới hạn từng key/value |
| Chi phí | Phụ thuộc thao tác/lưu trữ liên quan | Có thể có phí lưu trữ index, cập nhật/query tag và giao dịch liên quan |
| Quyền truy cập | Gắn với quyền đọc/ghi thuộc tính blob theo hoạt động cụ thể | Có quyền chuyên biệt cho đọc/ghi tags và tìm theo tags |
| Ví dụ phù hợp | `ingestionpipeline=etl-v3` | `Project=Atlas`, `State=Approved` |

### Không nhầm với tên blob và prefix

Tên blob có thể chứa dấu `/` để mô phỏng phân cấp thư mục, ví dụ:

~~~text
invoices/2026/01/invoice-0001.pdf
~~~

Với **flat namespace** thông thường, đây vẫn là **tên blob**; dấu `/` giúp ứng dụng lọc theo prefix và dựng cây thư mục ảo. Trong account bật **hierarchical namespace**, mô hình thư mục/path có ngữ nghĩa khác; cần kiểm tra hỗ trợ tính năng cụ thể.

- `List Blobs(prefix="invoices/2026/")`: tìm **theo tên** bắt đầu bằng prefix.
- `Find Blobs by Tags("Project" = 'Atlas')`: tìm **theo nhãn được lập chỉ mục**.
- Tìm từ “hợp đồng” bên trong file PDF: cần **dịch vụ lập chỉ mục nội dung**, ví dụ Azure AI Search hoặc hệ thống tìm kiếm do ứng dụng xây dựng.

## 4. Thiết kế bộ tags có ích cho vận hành

### 4.1. Chọn những trường có giá trị lọc cao

Vì một blob chỉ có một số lượng tags giới hạn, không nên sao chép toàn bộ JSON thuộc tính nghiệp vụ vào tags.

Gợi ý cho hệ thống tài liệu:

| Tag key | Giá trị ví dụ | Truy vấn thường gặp |
| --- | --- | --- |
| `Project` | `Atlas` | Liệt kê tất cả tài liệu dự án Atlas |
| `ReviewStatus` | `Pending` / `Approved` | Tìm tài liệu chờ duyệt |
| `DocumentType` | `Invoice` / `Contract` | Lọc theo nhóm tài liệu |
| `Year` | `2026` | Lọc năm theo quy ước chuỗi |
| `RetentionClass` | `Standard` / `LongTerm` | Tổ chức vòng đời dữ liệu |
| `Department` | `Finance` / `Legal` | Gom tài liệu theo đơn vị |

Metadata bổ trợ:

~~~text
source=erp
uploaderapp=docs-api
pipelineversion=3
importbatch=batch-20261120-a
originalfilename=invoice-supplier-001.pdf
~~~

Đừng đưa thông tin nhạy cảm như số căn cước, số tài khoản ngân hàng, token, mật khẩu, dữ liệu khách hàng cần bảo mật hoặc văn bản hợp đồng đầy đủ vào tags. Tags là nhãn vận hành để phục vụ truy vấn, không phải kho bí mật.

### 4.2. Quy ước đặt tên phải nhất quán

Ví dụ thống nhất:

- Tên keys theo **PascalCase**: `Project`, `ReviewStatus`, `DocumentType`.
- Giá trị là bộ từ vựng chuẩn: `Pending`, `Approved`, `Rejected`.
- Không trộn `approved`, `APPROVED` và `Approved` khi ý nghĩa giống nhau.
- Không đổi tên key giữa các hệ thống nếu chưa có kế hoạch di trú dữ liệu.
- Chỉ thêm tag mới khi có câu hỏi truy vấn hoặc chính sách vòng đời rõ ràng.

Một lỗi nhỏ như truy vấn `"reviewstatus" = 'Approved'` thay vì `"ReviewStatus" = 'Approved'` có thể trả về rỗng dù blob có tag đúng tên khác kiểu chữ.

### 4.3. Tags luôn là chuỗi: lưu ngày và số thế nào?

Vì tag query không phải engine phân tích kiểu dữ liệu phong phú, **so sánh lớn/nhỏ là so sánh chuỗi**, không tự chuyển sang số hoặc ngày.

Ví dụ:

~~~text
"Priority" = "2"
"Priority" = "10"
~~~

Nếu so sánh chuỗi, `"10"` và `"2"` không có thứ tự giống so sánh số. Muốn dùng khoảng, cân nhắc mã hóa độ dài cố định, chẳng hạn `Priority=02`, `Priority=10`, hoặc sử dụng chỉ mục ứng dụng có kiểu dữ liệu thật.

Với ngày, chọn chuẩn có thứ tự từ năm tới ngày:

~~~text
ReviewDate=2026-11-20
~~~

Và giữ định dạng đồng nhất (ISO 8601 theo thiết kế). Không dùng lẫn `20/11/2026`, `2026/11/20` và `Nov-20-2026` rồi mong so sánh thứ tự cho kết quả đúng.

### 4.4. Tags không phải chính sách phân quyền

Tag `Sensitivity=Confidential` **không tự biến blob thành bí mật**. Muốn hạn chế ai xem/sửa nội dung, cần thiết lập authentication, Azure RBAC/ACL theo khả năng account, SAS, network controls, encryption và chính sách thực tế.

Tags có thể được một ứng dụng hoặc chính sách quản trị dùng làm **tín hiệu** để phân loại và xử lý, nhưng không phải tường lửa hay ACL độc lập.

## 5. Find Blobs by Tags hoạt động thế nào?

Azure Blob Storage cung cấp thao tác tìm theo biểu thức lọc **blob index tags**. Chỉ mục thuộc phạm vi **storage account**. Một truy vấn có thể quét logic trên nhiều container của cùng account mà không bắt ứng dụng tự liệt kê mọi blob.

### 5.1. Cú pháp biểu thức lọc cơ bản

Ví dụ:

~~~text
"Project" = 'Atlas'
"Project" = 'Atlas' AND "ReviewStatus" = 'Approved'
"Year" >= '2025' AND "Year" <= '2026'
@container = 'documents' AND "DocumentType" = 'Invoice'
~~~

Ý nghĩa:

1. Tìm tất cả blob có `Project=Atlas`.
2. Tìm blob vừa thuộc dự án Atlas vừa đã được phê duyệt.
3. Lọc theo giá trị chuỗi `Year` trong khoảng có dạng được quy ước nhất quán.
4. Giới hạn kết quả ở container `documents` và có `DocumentType=Invoice`.

Quy ước cú pháp quan trọng:

- **Tên tag** trong biểu thức được viết trong **dấu ngoặc kép**, ví dụ `"Project"`.
- **Giá trị** được viết trong **dấu nháy đơn**, ví dụ `'Atlas'`.
- `AND` kết hợp các điều kiện cần cùng đúng; dịch vụ có thể hỗ trợ các tổ hợp logic khác theo cú pháp và giới hạn phiên bản API.
- `@container` là trường đặc biệt để lọc container, không phải một tag do người dùng đặt.
- Giá trị/keys phân biệt chữ hoa và chữ thường theo cơ chế so sánh tags.
- Nếu có ký tự đặc biệt trong biểu thức, phải tuân thủ đúng quy tắc escape/encoding của REST, SDK hoặc Azure CLI.

**Ví dụ không hợp lệ về ý nghĩa:** muốn lọc `metadata.source = erp` bằng `"source" = 'erp'` nhưng blob chỉ có **metadata** `source=erp` và không có **tag** `source=erp`. Kết quả tìm theo tags sẽ không tìm thấy blob đó.

### 5.2. Lấy tags của một blob khác với tìm qua chỉ mục

Có hai tình huống:

- **Biết container và blob name:** dùng **Get Blob Tags** để lấy bộ tag của đúng đối tượng.
- **Chưa biết blob nào phù hợp:** dùng **Find Blobs by Tags** để truy vấn chỉ mục trong account.

Sự khác biệt này đặc biệt quan trọng khi vừa sửa tags xong: thao tác đọc tags của blob cụ thể có thể phản ánh bộ tag mới, trong khi **chỉ mục tìm kiếm chưa kịp cập nhật**.

### 5.3. Chỉ mục có tính nhất quán cuối cùng

Các cập nhật chỉ mục blob tags có thể được xử lý **bất đồng bộ**. Vì vậy:

1. Ứng dụng vừa đặt `ReviewStatus=Approved`.
2. `Get Blob Tags` cho đúng blob có thể trả ngay giá trị mới.
3. `Find Blobs by Tags` trong thời gian ngắn có thể vẫn trả kết quả cũ hoặc chưa tìm thấy blob.
4. Sau khi chỉ mục bắt kịp, truy vấn mới phản ánh thay đổi.

**Không thiết kế một giao dịch nghiệp vụ yêu cầu “đặt tag xong, truy vấn index phải thấy ngay lập tức” nếu chưa xử lý khoảng trễ.** Khi cần đọc ngay đối tượng vừa cập nhật, giữ blob name/container và dùng Get Blob Tags hoặc dữ liệu giao dịch ứng dụng.

### 5.4. Kết quả được phân trang

Ở tài khoản nhiều blob, kết quả tìm thường được API/SDK **phân trang**. Không nên lấy một trang đầu rồi kết luận đó là toàn bộ kết quả. SDK thường cung cấp iterator/pager; cần xử lý tiếp continuation token hoặc phân trang theo cơ chế của thư viện.

Chỉ mục tags không phải database có thể tùy ý join, group-by hoặc tìm kiếm gần đúng theo nội dung PDF. Khi cần tìm kiếm phức tạp, hãy dùng hệ thống chỉ mục phù hợp.

## 6. Thực hành Azure CLI: đọc và ghi metadata/tags

Các lệnh dưới đây là **ví dụ để học cách thao tác**, không phải yêu cầu tạo dữ liệu thật trong môi trường production. Những lệnh `show`/`list`/`filter` đọc dữ liệu; `update` và `set` **thay đổi blob** và cần được phê duyệt tại môi trường thực hành.

Giả sử blob sau **đã tồn tại**:

~~~text
Storage account: stdocslab001
Container:       documents
Blob:            invoices/2026/01/invoice-0001.pdf
~~~

Tài khoản của bạn phải có quyền data-plane phù hợp với từng thao tác. Azure portal “Contributor” ở cấp quản lý tài nguyên không tự chứng minh bạn có quyền tìm hoặc sửa mọi blob tags.

### 6.1. Chọn đúng subscription và storage account

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Chỉ đổi ngữ cảnh khi đã xác nhận đúng subscription được giao.
az account set --subscription "<SUBSCRIPTION_ID>"

# Kiểm tra storage account (đọc cấu hình management plane).
az storage account show \
  --resource-group rg-docs-lab \
  --name stdocslab001 \
  --query "{name:name, kind:kind, sku:sku.name, location:location}" \
  --output json
~~~

Các tên tài nguyên là giả định. Nếu account/blob chưa tồn tại, đừng tạo dữ liệu sản xuất ngoài phạm vi bài thực hành; có thể dùng mô phỏng ở mục 12.

### 6.2. Xem blob và metadata hiện tại

~~~bash
az storage blob show \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json

az storage blob metadata show \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json
~~~

Chỉ sử dụng `--auth-mode login` khi danh tính Microsoft Entra hiện tại đã được cấp quyền dữ liệu tương ứng. Nếu không, hãy kiểm tra quyền cấp tại đúng scope thay vì chuyển sang việc chia sẻ account key một cách tùy tiện.

### 6.3. Cập nhật metadata

~~~bash
az storage blob metadata update \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --metadata source=erp pipeline=ingest-v2 \
  --auth-mode login
~~~

**Điểm cần nhớ:** thao tác đặt metadata theo bộ giá trị gửi lên có thể **thay thế toàn bộ metadata hiện tại**. Nếu cần giữ những key cũ, đọc trước, hợp nhất tập key–value và cập nhật có kiểm soát. Không chạy ví dụ trên blob đang có metadata quan trọng mà chưa kiểm tra.

### 6.4. Xem blob index tags của một đối tượng

~~~bash
az storage blob tag list \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json
~~~

Lệnh lấy **tags của một blob có tên đã biết**. Nếu nhận lỗi quyền, cần kiểm tra **quyền đọc tags**, vốn là quyền phân biệt với việc chỉ đọc nội dung blob.

### 6.5. Ghi blob index tags

~~~bash
az storage blob tag set \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --tags Project=Atlas ReviewStatus=Approved Year=2026 \
  --auth-mode login
~~~

Sau đó đọc lại:

~~~bash
az storage blob tag list \
  --account-name stdocslab001 \
  --container-name documents \
  --name invoices/2026/01/invoice-0001.pdf \
  --auth-mode login \
  --output json
~~~

**Cảnh báo nghiệp vụ quan trọng:** thao tác Set Blob Tags gửi một **bộ tags mới**, có thể **thay thế các tags hiện hữu** chứ không phải tự động merge. Nếu blob đang có `RetentionClass=LongTerm` và bạn gọi set chỉ với `Project=Atlas`, tag cũ có thể bị mất. Quy trình cập nhật cần đọc bộ tags trước, hợp nhất và xử lý cập nhật đồng thời theo khả năng API/SDK.

### 6.6. Tìm blobs theo tags trên storage account

Trong Bash, bao biểu thức bằng dấu nháy đơn ngoài cùng và escape dấu nháy đơn cho giá trị bằng cách khác nếu cần. Cách dễ đọc hơn là dùng dấu ngoặc kép ngoài cùng, escape dấu ngoặc kép bên trong:

~~~bash
az storage blob filter \
  --account-name stdocslab001 \
  --tag-filter "\"Project\" = 'Atlas' AND \"ReviewStatus\" = 'Approved'" \
  --auth-mode login \
  --output json
~~~

Thêm giới hạn container:

~~~bash
az storage blob filter \
  --account-name stdocslab001 \
  --tag-filter "@container = 'documents' AND \"Project\" = 'Atlas'" \
  --auth-mode login \
  --output json
~~~

Kết quả là danh sách những blob **đang khớp chỉ mục tại thời điểm truy vấn**, có thể bao gồm container và blob name. Không coi kết quả rỗng ngay sau `tag set` là lỗi chắc chắn; cần lưu ý độ trễ index.

### 6.7. Tìm theo prefix để so sánh

~~~bash
az storage blob list \
  --account-name stdocslab001 \
  --container-name documents \
  --prefix invoices/2026/01/ \
  --auth-mode login \
  --output table
~~~

Khác biệt:

- `blob list --prefix`: dựa vào **blob name**, không kiểm tra `ReviewStatus`.
- `blob filter --tag-filter`: dựa vào **index tags**, không tự tìm nội dung file PDF.
- `blob metadata show`: đọc **metadata** khi đã biết tên blob.

## 7. Ví dụ Python SDK: đọc, cập nhật và tìm tags

Azure Storage SDK hỗ trợ các chức năng tags, metadata và truy vấn index. Ví dụ sau sử dụng **Azure Identity** để lấy credential theo cơ chế đăng nhập được cấu hình cho môi trường (local hoặc workload identity/managed identity phù hợp).

Cài thư viện ở môi trường phát triển phù hợp:

~~~bash
pip install azure-storage-blob azure-identity
~~~

**Ví dụ mã minh họa**; không tự chạy lên blob production vì phần đặt tags/metadata là thao tác ghi:

~~~python
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

account_url = "https://stdocslab001.blob.core.windows.net"
container_name = "documents"
blob_name = "invoices/2026/01/invoice-0001.pdf"

service = BlobServiceClient(
    account_url=account_url,
    credential=DefaultAzureCredential(),
)
blob_client = service.get_blob_client(
    container=container_name,
    blob=blob_name,
)

# Đọc các thuộc tính và metadata của đúng blob.
properties = blob_client.get_blob_properties()
print("Metadata:", properties.metadata)

# Đọc index tags của blob đã biết tên.
tags = blob_client.get_blob_tags()
print("Tags:", tags)

# LƯU Ý: đặt cả bộ tags mới. Trước khi dùng thực tế,
# cần xử lý cạnh tranh và giữ các tags muốn bảo toàn.
new_tags = dict(tags)
new_tags["Project"] = "Atlas"
new_tags["ReviewStatus"] = "Approved"
blob_client.set_blob_tags(new_tags)

# Tìm blob theo index tags trên phạm vi storage account.
expression = '"Project" = \'Atlas\' AND "ReviewStatus" = \'Approved\''
for item in service.find_blobs_by_tags(filter_expression=expression):
    print(item.container_name, item.name)
~~~

Ở ứng dụng thật, nên có thêm:

- **Kiểm soát quyền data-plane** cho identity: chỉ xem/ghi những gì cần.
- **Retry có giới hạn** cho lỗi mạng hoặc quá tải; không lặp vô hạn khi thiếu quyền.
- **Cơ chế cập nhật đồng thời** phù hợp API/SDK. Đọc–merge–set bằng hai lệnh đơn giản vẫn có nguy cơ ghi đè thay đổi của tiến trình khác.
- **Pagination/streaming** để xử lý tập kết quả lớn.
- **Kiểm tra kết quả** sau ghi, đồng thời chấp nhận Find Blobs by Tags có độ trễ index.

### 7.1. Nếu muốn cập nhật metadata qua SDK

~~~python
# Ví dụ minh họa; thao tác này thay bộ metadata của blob.
metadata = dict(blob_client.get_blob_properties().metadata or {})
metadata["source"] = "erp"
metadata["pipeline"] = "ingest-v2"
blob_client.set_blob_metadata(metadata=metadata)
~~~

Tags và metadata là **hai tập dữ liệu riêng**. Gọi `set_blob_metadata` không tự biến các giá trị metadata thành blob index tags để có thể tìm qua `find_blobs_by_tags`.

### 7.2. Tìm nhiều blob bằng prefix qua SDK

~~~python
container_client = service.get_container_client("documents")

for blob in container_client.list_blobs(
    name_starts_with="invoices/2026/01/"
):
    print(blob.name)
~~~

Đây là **liệt kê theo tên**, hữu ích khi cấu trúc tên ổn định. Nếu mục tiêu là tìm `ReviewStatus=Approved` bất kể prefix thì nên dùng index tags hoặc một hệ thống chỉ mục ứng dụng.

## 8. REST API và các loại thao tác cần hiểu

Không cần nhớ toàn bộ HTTP request để dùng SDK, nhưng nên biết chúng là **những chức năng riêng biệt** của Blob Storage:

| Nhu cầu | Nhóm thao tác REST/SDK | Kết quả |
| --- | --- | --- |
| Đọc nội dung blob | Get Blob / download | Nội dung đối tượng |
| Đọc thuộc tính + metadata | Get Blob Properties hoặc Get Blob Metadata | HTTP headers, metadata |
| Ghi metadata | Set Blob Metadata | Bộ metadata mới |
| Đọc tags của blob cụ thể | Get Blob Tags | Các index tags hiện gắn với blob |
| Ghi tags | Set Blob Tags | Bộ tags mới |
| Tìm tất cả blob khớp tags | Find Blobs by Tags | Các tên blob/containers khớp điều kiện |
| Liệt kê theo prefix | List Blobs | Đối tượng có tên bắt đầu bằng prefix |

Nhóm thao tác tags có thể dùng **quyền khác** so với thao tác đọc nội dung. Trong các luồng kiểm toán, cần ghi nhận ai có thể thay đổi tag phân loại và vì sao.

### 8.1. Điều kiện cập nhật và tính nhất quán

Cập nhật metadata và tags không nên được đối xử như một “transaction” duy nhất trên hai tập trường. Nếu nghiệp vụ yêu cầu cùng thay đổi `ReviewStatus` trong database, metadata và tags, phải thiết kế **quy trình điều phối/đối soát**.

Ví dụ:

1. Ứng dụng ghi kết quả duyệt vào hệ thống nghiệp vụ.
2. Worker cập nhật blob tags bằng một thao tác được kiểm soát.
3. Worker xác minh Get Blob Tags.
4. Bộ xử lý tìm kiếm chấp nhận độ trễ của chỉ mục tags.
5. Khi thất bại, ghi vào retry queue/incident để xử lý và đối soát.

Nếu yêu cầu tra cứu ngay khi duyệt xong, nên dùng **database nghiệp vụ** làm nguồn trạng thái tức thời; chỉ mục Blob tags là một đường truy vấn bổ trợ.

## 9. Phân quyền và bảo mật khi dùng tags

### 9.1. Microsoft Entra, RBAC và SAS

Azure Blob Storage hỗ trợ nhiều cách cấp quyền, ví dụ OAuth qua Microsoft Entra ID kết hợp Azure RBAC và **Shared Access Signature (SAS)**. Một số thao tác dùng Shared Key trong những môi trường còn cho phép, nhưng không nên mặc định chia sẻ account key là cách dễ nhất.

Quyền cần phân biệt:

- **Đọc blob/data** chưa chắc đồng nghĩa **được sửa tags**.
- **Đọc tags** và **ghi tags** là hai mục đích phân quyền khác nhau.
- **Tìm trên index tags toàn account** có yêu cầu cấp quyền riêng đối với thao tác Find Blobs by Tags.
- Nếu dùng SAS, các quyền chuyên biệt cho **tag operations** và **find/query tags** cần được cấp đúng loại SAS và tài nguyên được hỗ trợ; không suy ra một SAS chỉ cho download sẽ thực hiện được tìm kiếm tags.

Khi dùng Entra ID/RBAC, xác minh quyền data action tương ứng với thao tác `tags/read`, `tags/write` hoặc truy vấn filter theo tài liệu dịch vụ, và scope mà principal được cấp. Chọn vai trò dựng sẵn hoặc custom role phù hợp sau khi kiểm tra thực tế; tránh gán Owner toàn subscription để “sửa lỗi 403”.

### 9.2. Tags không thay thế cơ chế bảo vệ dữ liệu

Ví dụ gắn `Sensitivity=Confidential` cho blob nhưng để container công khai hoặc cung cấp SAS quá rộng: tag không ngăn người khác đọc nội dung.

Cần phối hợp:

- Tắt anonymous public access khi dữ liệu không được công bố.
- Sử dụng RBAC/ACL hoặc SAS tối thiểu theo loại account và nghiệp vụ.
- Hạn chế network access, sử dụng Private Endpoint khi kiến trúc yêu cầu.
- Mã hóa dữ liệu theo khả năng mặc định và chính sách khóa/Key Vault thích hợp.
- Ghi nhật ký và theo dõi thao tác truy cập, thay đổi tags nếu yêu cầu kiểm toán.
- Tránh lưu **bí mật, dữ liệu định danh nhạy cảm hoặc dữ liệu pháp lý mật** vào giá trị tags.

### 9.3. Đừng tin tags là sự thật tuyệt đối nếu người ghi không được kiểm soát

Nếu người dùng cuối có thể tự sửa `ReviewStatus=Approved`, một ứng dụng lấy tag đó để “cấp quyền tải file đã duyệt” sẽ có lỗi thiết kế quyền truy cập.

Giá trị tag phục vụ **lọc và tổ chức**, không nên trực tiếp làm quyết định phê duyệt hoặc phân quyền khi chưa có **nguồn dữ liệu tin cậy** và quy trình kiểm tra thay đổi.

## 10. Vòng đời đối tượng, automation và quy tắc bảo trì

### 10.1. Tags trong quản lý vòng đời

Azure Blob Storage hỗ trợ những quy tắc quản lý vòng đời (*lifecycle management*) dựa trên các điều kiện phù hợp, trong đó **blob index tags** có thể được dùng làm tiêu chí lọc theo tính năng và loại blob được hỗ trợ.

Ví dụ về thiết kế nghiệp vụ:

- Blob có `DocumentType=Invoice` và `RetentionClass=Standard`.
- Sau mốc thời gian/tuổi dữ liệu đáp ứng điều kiện, một chính sách chuyển access tier hoặc xóa theo quy trình lưu giữ được phê duyệt có thể áp dụng.
- Với tài liệu có `RetentionClass=LongTerm`, cần quy tắc và kiểm soát khác.

**Thận trọng:** Không suy từ tag `RetentionClass=LongTerm` rằng blob được đặt **legal hold**, immutability policy hay khóa xóa. Những cơ chế bảo vệ dữ liệu pháp lý là tính năng riêng và cần cấu hình độc lập.

### 10.2. Tags không tự cập nhật khi metadata thay đổi

Nếu ứng dụng đổi metadata `pipeline=ingest-v3`, các tag như `Project=Atlas` vẫn là bộ giá trị riêng. Cần có quy trình cập nhật nếu dữ liệu phân loại phụ thuộc metadata.

Trong một pipeline nạp dữ liệu, tốt hơn nên quyết định cùng lúc:

1. Tên blob và container.
2. Content-Type và các system properties cần khai báo.
3. Metadata mô tả nguồn gốc.
4. Tags cần cho tìm kiếm/lifecycle.
5. Bản ghi nghiệp vụ lưu trạng thái quan trọng và mã định danh đối tượng.

Khi một bước thất bại, pipeline nên ghi sự kiện và có khả năng chạy lại an toàn.

### 10.3. Kiểm soát việc thay thế toàn bộ tags

Giả sử blob đang có:

~~~json
{
  "Project": "Atlas",
  "ReviewStatus": "Pending",
  "RetentionClass": "LongTerm"
}
~~~

Ứng dụng chỉ muốn đổi `ReviewStatus=Approved`. Nếu gọi Set Blob Tags với đúng một tag:

~~~json
{
  "ReviewStatus": "Approved"
}
~~~

nó có nguy cơ **làm mất** `Project` và `RetentionClass`. Ứng dụng phải lập ra toàn bộ bộ tags cần duy trì. Trong hệ thống nhiều worker, cần bảo vệ tính nhất quán bằng điều kiện cập nhật/đồng bộ hoặc qua một nguồn phân loại trung tâm theo thiết kế API được hỗ trợ.

Đặt tags không đồng nghĩa sửa nội dung file PDF. Tuy nhiên thao tác quản trị tags vẫn có thể ảnh hưởng tìm kiếm, quy tắc lifecycle và sự kiện ứng dụng; phải được kiểm soát như thay đổi dữ liệu có ý nghĩa.

## 11. Chọn công cụ tìm kiếm phù hợp

Một kiến trúc tốt chọn giải pháp dựa trên **loại câu hỏi** mà người dùng muốn đặt ra.

| Câu hỏi | Giải pháp thường phù hợp | Vì sao |
| --- | --- | --- |
| “Liệt kê mọi hóa đơn của tháng 01/2026 theo đường dẫn đã quy ước.” | List Blobs theo prefix | Tên chứa cấu trúc thời gian |
| “Tìm mọi blob thuộc Atlas đã duyệt, không biết nằm ở đâu.” | Find Blobs by Tags | Có chỉ mục tags server-side |
| “Xem pipeline nào nạp blob đã biết tên.” | Get Blob Metadata | Truy cập metadata của đối tượng cụ thể |
| “Tìm mọi blob có metadata pipeline=ingest-v3.” | Chỉ mục bên ngoài hoặc list/filter phù hợp quy mô | Metadata không có truy vấn index gốc |
| “Tìm PDF chứa từ khóa về hợp đồng.” | Azure AI Search hoặc công cụ tìm kiếm nội dung | Blob index tags không đọc nội dung PDF |
| “Tìm theo khoảng tiền và kết hợp thông tin khách hàng.” | Database nghiệp vụ/search index có schema phù hợp | Blob tags chỉ là chuỗi và bộ điều kiện đơn giản |
| “Xóa/chuyển tier đối tượng đã hết hạn theo chính sách.” | Blob lifecycle management với điều kiện được hỗ trợ | Tự động hóa vòng đời, cần kiểm soát retention |

### Mô hình kết hợp Blob Storage và Azure AI Search

Một ứng dụng có thể lưu **file gốc ở Blob Storage**, đồng thời xây **search index** chứa trường tên, ngày, khách hàng, văn bản trích xuất và liên kết blob. Azure AI Search có các khả năng lập chỉ mục nội dung và metadata tùy pipeline, cấu hình data source/indexer và bộ xử lý tài liệu.

~~~mermaid
flowchart LR
    APP["Ứng dụng upload"]
    B["Blob Storage\nfile + metadata + tags"]
    TAG["Blob tag index\nFind Blobs by Tags"]
    PIPE["Indexer / ETL\nđược cấu hình"]
    SEARCH["Search index\ntext + các trường nghiệp vụ"]
    CLIENT["API tìm kiếm"]
    APP --> B --> TAG
    B --> PIPE --> SEARCH
    CLIENT -->|"Lọc Project, State"| TAG
    CLIENT -->|"Tìm nội dung/semantic"| SEARCH
~~~

Không mặc định mọi trường metadata/tag sẽ tự xuất hiện trong Azure AI Search nếu chưa cấu hình mapping/pipeline tương ứng. Hai chỉ mục giải quyết nhu cầu khác nhau và có chi phí/vòng đời cập nhật riêng.

## 12. Bài thực hành mô phỏng: tìm chứng từ theo tags

### 12.1. Dữ liệu giả lập

Một container `documents` có bốn blob:

| Blob name | Metadata `source` | Tag `Project` | Tag `ReviewStatus` | Tag `Year` |
| --- | --- | --- | --- | --- |
| `invoices/2026/invoice-001.pdf` | `erp` | `Atlas` | `Approved` | `2026` |
| `invoices/2026/invoice-002.pdf` | `erp` | `Atlas` | `Pending` | `2026` |
| `contracts/2026/contract-003.pdf` | `crm` | `Orion` | `Approved` | `2026` |
| `reports/2025/report-004.csv` | `etl` | `Atlas` | `Approved` | `2025` |

Không cần tạo storage account thật để giải bài.

### 12.2. Yêu cầu A — Lọc theo tags

Cho biểu thức:

~~~text
"Project" = 'Atlas' AND "ReviewStatus" = 'Approved'
~~~

**Dự đoán kết quả:** `invoices/2026/invoice-001.pdf` và `reports/2025/report-004.csv`.

Nếu thêm:

~~~text
"Year" = '2026'
~~~

**Kết quả còn lại:** `invoices/2026/invoice-001.pdf`.

Cả hai câu hỏi không cần biết prefix từ trước nếu tag index có dữ liệu và đồng bộ đủ.

### 12.3. Yêu cầu B — Tìm theo prefix

Liệt kê blob có tên bắt đầu bằng:

~~~text
invoices/2026/
~~~

**Kết quả:** `invoice-001.pdf` và `invoice-002.pdf`, bất kể `ReviewStatus` là gì. Điều này cho thấy prefix và tags giải quyết các câu hỏi khác nhau.

### 12.4. Yêu cầu C — Tìm theo metadata

Người dùng hỏi: “Tìm mọi blob có metadata `source=erp`”.

**Trả lời đúng:** không có truy vấn blob index tags trực tiếp cho metadata này nếu nó chỉ tồn tại trong metadata. Có thể:

- Liệt kê tập đối tượng trong phạm vi thích hợp và lấy metadata để lọc (cần cân nhắc quy mô/chi phí).
- Khi đây là nhu cầu thường xuyên, thiết kế thêm tag phù hợp (nếu giới hạn cho phép), hoặc xây search index/database.
- Nếu thêm tag mới cho dữ liệu cũ, cần một quy trình **backfill** bảo đảm không mất tags hiện có và theo dõi độ trễ index.

### 12.5. Yêu cầu D — Một blob vừa đổi từ Pending sang Approved

Ngay sau khi cập nhật `invoice-002.pdf`:

- Get Blob Tags trả `ReviewStatus=Approved`.
- Find Blobs by Tags vẫn chưa trả `invoice-002.pdf`.

**Giải thích:** đây có thể là khoảng trễ của chỉ mục. Nếu cần trả trạng thái tức thì, dùng nguồn giao dịch hoặc Get Blob Tags theo blob cụ thể. Không viết vòng lặp truy vấn vô hạn và không kết luận việc ghi thất bại chỉ từ một kết quả tìm rỗng.

### 12.6. Yêu cầu E — Bảo vệ tags quan trọng

Một worker cần đổi `ReviewStatus` nhưng blob đang có `RetentionClass=LongTerm`. Hãy thiết kế bước cập nhật.

**Đáp án tham khảo:**

1. Xác thực worker có quyền phù hợp và thao tác trên đúng blob.
2. Đọc bộ tags hiện tại, bao gồm `RetentionClass`.
3. Kiểm tra trạng thái duyệt trong database nghiệp vụ.
4. Hợp nhất bộ tags cần giữ và giá trị `ReviewStatus` mới.
5. Ghi bộ tags mới với cơ chế bảo vệ cập nhật đồng thời nếu được triển khai.
6. Đọc lại và ghi audit event; chấp nhận chỉ mục tìm kiếm có thể cập nhật sau.

## 13. Khắc phục lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `Find Blobs by Tags` trả rỗng dù vừa set tag | Chỉ mục cập nhật bất đồng bộ | Get Blob Tags để xác minh ghi, kiểm tra lại sau khoảng trễ hợp lý |
| Truy vấn `"status" = 'Approved'` không tìm thấy | Key thực tế là `ReviewStatus`, khác cả tên lẫn chữ hoa/thường | Đọc tags thật, dùng quy ước nhất quán |
| Lệnh filter trả lỗi biểu thức | Sai cặp dấu nháy, escape, toán tử hoặc tên trường | Kiểm tra query string truyền tới API/CLI |
| Lấy được blob content nhưng không query được tags | Quyền data-plane dành cho tags/filter chưa được cấp | Kiểm tra RBAC data actions hoặc SAS quyền phù hợp |
| Ghi `ReviewStatus` làm mất `RetentionClass` | Set Blob Tags thay cả bộ tags | Đọc, merge, kiểm soát concurrent update |
| Muốn tìm `source=erp` nhưng query tags không trả blob | `source` chỉ có trong metadata | Dùng phương án list/filter hoặc xây index/tags |
| Chỉ một container có kết quả | Điều kiện `@container`, account đích hoặc dữ liệu tag không đúng | Kiểm tra scope account và filter |
| Tìm `Year >= '2025'` cho kết quả khó hiểu | Giá trị lưu dưới định dạng khác nhau | Chuẩn hóa chuỗi năm/ngày trước khi so sánh |
| Tags có giá trị không hợp lệ | Vượt số lượng/độ dài/ký tự cho phép | Kiểm tra giới hạn dịch vụ, validate trước khi upload |
| Search tài liệu theo nội dung trả rỗng | Tag index không đọc text/PDF | Dùng Azure AI Search hoặc công cụ indexing nội dung |
| Lệnh CLI lấy sai storage account | Chọn nhầm subscription/account hoặc thông tin xác thực | Kiểm tra `az account show`, URL/account, quyền và network |
| Chi phí tăng sau khi bật tagging hàng loạt | Cập nhật tags, chỉ mục/query và giao dịch tăng | Theo dõi Cost Management và log hoạt động |
| Truy vấn tìm nhãn đúng nhưng người dùng không tải được file | Quyền tìm tags khác quyền đọc blob hoặc mạng chặn | Kiểm tra cấp quyền tải blob và network rules riêng |

## 14. Thiết kế production và chi phí

### 14.1. Tách mục đích của từng trường

Đối với hệ thống tài liệu lớn:

- **Blob name/prefix:** dùng cho cấu trúc nghiệp vụ ổn định như năm/tháng/dự án, dễ lọc theo tên.
- **Metadata:** dùng cho thông tin vận hành, nguồn nhập, pipeline, nguyên bản tệp.
- **Blob index tags:** chỉ giữ các nhãn có nhu cầu truy vấn hoặc lifecycle rõ ràng.
- **Database nghiệp vụ:** trạng thái giao dịch, lịch sử phê duyệt, tham chiếu đến người dùng.
- **Azure AI Search:** tìm kiếm nội dung tài liệu hoặc truy vấn đa trường phong phú hơn.

Thiết kế này tránh sử dụng tags như cơ sở dữ liệu quan hệ hoặc metadata như engine tìm kiếm.

### 14.2. Dự toán chi phí

Khi mở rộng từ vài trăm lên hàng triệu blob, hãy xem:

1. **Số lượng blobs được gắn tags** và chi phí lưu trữ/index theo bảng giá đang áp dụng.
2. **Số lần Set/Get Blob Tags**, Find Blobs by Tags và các hoạt động list/read liên quan.
3. **Tần suất cập nhật**: thay nhiều tags liên tục có thể phát sinh thêm giao dịch và tải xử lý.
4. **Nhu cầu lưu giữ/tier** và chính sách vòng đời có thể làm thay đổi chi phí.
5. **Phí tìm kiếm bên ngoài** nếu sử dụng Azure AI Search hoặc database riêng.
6. **Dung lượng dữ liệu di chuyển** và các yêu cầu về region, tài khoản, network.

Dùng **Azure Pricing Calculator** và **Cost Management** với thông tin giá hiện hành cho region, account type và khối lượng dự kiến. Không giả định index tags hoàn toàn miễn phí hoặc mọi loại thao tác đều có cùng mức tính phí.

### 14.3. Theo dõi chất lượng dữ liệu phân loại

Nên có báo cáo định kỳ:

| Kiểm tra | Mục đích |
| --- | --- |
| Tỷ lệ blob thiếu `Project` hoặc `ReviewStatus` | Phát hiện pipeline nạp thiếu tags |
| Danh sách giá trị tag ngoài bộ từ vựng chuẩn | Phát hiện `approved`/`Approved`/`APPROVED` |
| Tần suất cập nhật tags thất bại | Phát hiện lỗi quyền hoặc cạnh tranh |
| Chênh lệch database–tags trên mẫu kiểm tra | Phát hiện sai trạng thái tìm kiếm |
| Số blobs kết quả theo thời gian | Xem chỉ mục/hệ thống phân loại có bất thường |
| Chi phí tag operations và queries | Tối ưu thiết kế truy vấn, backfill, retention |

Nếu dùng kết quả tìm kiếm để xóa hoặc chuyển tier hàng loạt, phải có bước phê duyệt/kiểm tra mục tiêu và cơ chế khôi phục theo chính sách dữ liệu.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một blob có metadata `source=crm` nhưng không có tag `source`. Truy vấn `"source" = 'crm'` bằng Find Blobs by Tags có tìm được blob không?

**Đáp án:** Không, vì Find Blobs by Tags chỉ tìm trong các **index tags**. Metadata không tự được đưa vào chỉ mục này.

**Câu 2.** Tên blob là `invoices/2026/01/a.pdf`. Bạn cần liệt kê tất cả blob trong `invoices/2026/`; nên dùng gì?

**Đáp án:** List Blobs với prefix `invoices/2026/`. Đây là lọc theo tên, không đòi tags.

**Câu 3.** Sau khi Set Blob Tags thành công, truy vấn Find vẫn chưa thấy blob. Đây có chắc là lỗi không?

**Đáp án:** Không. Chỉ mục tags có độ trễ do cập nhật bất đồng bộ; kiểm tra Get Blob Tags, account/scope và các điều kiện lọc.

**Câu 4.** Tại sao không dùng `ReviewStatus=Approved` do người dùng tự đặt làm bằng chứng duy nhất để cấp quyền tải tài liệu?

**Đáp án:** Tag là thông tin phân loại có thể bị thay đổi bởi các principal được cấp quyền. Quyết định phê duyệt/phân quyền cần dựa trên nguồn nghiệp vụ tin cậy và cơ chế authorization phù hợp.

**Câu 5.** Vì sao không nên lưu `Priority=1`, `Priority=2`, `Priority=10` rồi sử dụng so sánh chuỗi để suy ra ưu tiên bằng số?

**Đáp án:** Tags là chuỗi và so sánh theo thứ tự chuỗi, không tự ép kiểu số. Muốn truy vấn thứ tự đáng tin cậy cần encoding chuẩn, ví dụ `01`, `02`, `10` hoặc index có kiểu số.

**Câu 6.** Cập nhật tags chỉ với `ReviewStatus=Approved` có thể gây lỗi gì nếu blob đang có `RetentionClass=LongTerm`?

**Đáp án:** Set Blob Tags có thể thay toàn bộ tập tags, khiến `RetentionClass` biến mất. Cần giữ và gửi lại các tags phải bảo toàn, cùng xử lý cập nhật đồng thời.

**Câu 7.** Muốn tìm tài liệu PDF có nội dung “phí vận chuyển”, chọn Find Blobs by Tags hay Azure AI Search?

**Đáp án:** Với tìm kiếm nội dung PDF, chọn pipeline lập chỉ mục nội dung như Azure AI Search hoặc công cụ tương đương. Find Blobs by Tags chỉ lọc nhãn đã được đặt trên đối tượng.

**Câu 8.** Có thể tìm tags trên nhiều container không?

**Đáp án:** Có, trong phạm vi **một storage account** mà thao tác Find Blobs by Tags được phép thực hiện; dùng `@container` để giới hạn nếu cần. Truy vấn không tự đi qua nhiều storage account khác nhau.

## Ghi nhớ

- **Metadata** dùng để mô tả đối tượng; **blob index tags** là nhãn được Azure Blob Storage lập chỉ mục để lọc đối tượng trên phía dịch vụ.
- **Blob name/prefix**, **metadata**, **tags** và **nội dung file** là bốn hướng tra cứu có khả năng khác nhau.
- `Get Blob Tags` đọc bộ tags của **một blob đã biết**; `Find Blobs by Tags` tìm **những blob chưa biết tên** theo điều kiện.
- Chỉ mục tags **có thể cập nhật trễ**, và tags là **chuỗi**, cần chuẩn hóa key/value/định dạng ngày số.
- **Set Blob Tags** có thể thay **toàn bộ tập tags**: bảo toàn các trường quan trọng và kiểm soát thao tác đồng thời.
- Giới hạn tags, quyền đọc/ghi/tìm chuyên biệt, bảo mật dữ liệu, chi phí và nghiệp vụ phê duyệt đều phải được xem xét khi triển khai production.
