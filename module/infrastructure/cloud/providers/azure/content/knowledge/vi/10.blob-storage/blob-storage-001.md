# Container, blob và cách tổ chức dữ liệu đối tượng

Một ứng dụng hiện đại thường phải lưu ảnh sản phẩm, tài liệu PDF, tệp CSV, video, dữ liệu xuất báo cáo hoặc bản ghi sự kiện. Những dữ liệu này không nhất thiết phù hợp để lưu trực tiếp trong các cột của cơ sở dữ liệu quan hệ. **Azure Blob Storage** là dịch vụ lưu trữ đối tượng (object storage) giúp lưu và truy xuất lượng lớn dữ liệu dạng tệp hoặc dữ liệu phi cấu trúc qua các API được quản lý của Azure.

Bài học thuộc chương **Lưu trữ đối tượng với Blob Storage** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá hệ sinh thái Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Trọng tâm bài này là hiểu **storage account, container, blob và cách đặt tên/tổ chức đối tượng**, sau đó áp dụng bảo mật, quản lý vòng đời và thao tác thực hành.

Sau bài học, bạn có thể:

- Phân biệt **storage account**, **container**, **blob** và tên blob (blob name).
- Mô tả URL của một blob, phân biệt object storage với file system truyền thống.
- Hiểu **block blob**, **append blob**, **page blob** và các trường hợp sử dụng cơ bản.
- Thiết kế tên container và blob theo quy ước có thể mở rộng, dễ liệt kê theo prefix.
- Phân biệt **virtual directories** của flat namespace với **hierarchical namespace** của Data Lake Storage.
- Sử dụng **metadata**, **blob index tags**, phiên bản và access tier đúng mục đích.
- Thiết kế bảo vệ dữ liệu bằng Entra ID/RBAC, container private, mã hóa, versioning và soft delete.
- Tạo container, tải lên, liệt kê, tải xuống và dọn dẹp tài nguyên thử nghiệm bằng Azure CLI.

## 1. Object storage giải quyết bài toán gì?

Trong object storage, mỗi đối tượng gồm **nội dung dữ liệu**, **định danh/tên** và những thuộc tính đi kèm. Ứng dụng truy cập đối tượng qua API thay vì thao tác trực tiếp với một ổ đĩa gắn vào máy chủ.

Ví dụ, một trang thương mại điện tử có thể lưu:

- Ảnh sản phẩm: hàng triệu ảnh JPEG/PNG/WebP.
- File PDF hóa đơn: mỗi hóa đơn là một blob.
- File CSV xuất báo cáo: được tạo theo yêu cầu và có thời hạn lưu.
- Video hướng dẫn: được phân phối qua ứng dụng và hệ thống CDN/edge khi cần.
- Dữ liệu thô cho phân tích: file JSON, CSV hoặc Parquet được phân vùng theo ngày.

Trong cơ sở dữ liệu, ứng dụng thường chỉ cần lưu thông tin nghiệp vụ như **DocumentId**, **OwnerId**, **BlobName**, **ContentType**, trạng thái và quyền truy cập. Nội dung file nằm trong Blob Storage. Thiết kế này giúp vòng đời file và vòng đời dữ liệu giao dịch được quản lý theo đặc trưng của từng loại dữ liệu.

### Object storage khác file storage và database như thế nào?

| Tiêu chí | Blob object storage | File share | Database |
|---|---|---|---|
| Đơn vị thường thao tác | Đối tượng/blob có tên | File và thư mục trong file system | Bản ghi, bảng hoặc tài liệu dữ liệu |
| Truy cập phổ biến | HTTPS REST/SDK, công cụ Azure | SMB/NFS tùy dịch vụ | SQL/driver/API dữ liệu |
| Tối ưu cho | Tệp, ảnh, log, dữ liệu thô, backup đối tượng | Ứng dụng cần chia sẻ file theo giao thức file system | Truy vấn, giao dịch và ràng buộc dữ liệu |
| Tìm kiếm dữ liệu | Liệt kê tên/prefix, thuộc tính, tags khi được hỗ trợ | Duyệt thư mục | Chỉ mục và truy vấn nghiệp vụ |
| Cập nhật | Thường ghi/đọc blob bằng API phù hợp | Đọc/ghi theo thao tác file system | Thay đổi bản ghi theo giao dịch |

Blob Storage không thay thế một database tìm kiếm/phân tích dữ liệu nghiệp vụ tùy ý. Khi cần truy vấn theo khách hàng, trạng thái đơn hàng hoặc phân quyền trên từng tài liệu, ứng dụng thường duy trì một **catalog/index nghiệp vụ** trong database hoặc dịch vụ tìm kiếm tương ứng.

## 2. Mô hình phân cấp: storage account → container → blob

Azure Blob Storage tổ chức đối tượng theo các thành phần:

~~~text
Azure subscription
└── Resource group: rg-shop-prod
    └── Storage account: stshopassetsprod
        └── Blob service
            ├── Container: product-images
            │   ├── products/p001/main.webp
            │   └── products/p002/main.webp
            ├── Container: invoices
            │   ├── 2026/11/inv-0001.pdf
            │   └── 2026/11/inv-0002.pdf
            └── Container: exports
                └── reports/2026/11/summary.csv
~~~

**Storage account** là tài nguyên Azure có tên toàn cục duy nhất trong không gian tên của dịch vụ. Nó cung cấp điểm cuối, vùng triển khai, cấu hình redundancy, network access và nhiều tùy chọn bảo mật/lưu trữ ở cấp tài khoản.

**Container** là đơn vị nhóm các blob bên trong cùng một storage account. Container có tên duy nhất trong phạm vi account, đóng vai trò ranh giới quản lý và có thể là phạm vi cấp quyền dữ liệu hoặc thiết lập public access (nếu tài khoản và chính sách cho phép). Container không phải máy tính hoặc Docker container.

**Blob** là một đối tượng dữ liệu được lưu trong container, có tên, nội dung và thuộc tính. Mỗi blob được nhận diện bởi tổ hợp **storage account + container + blob name**. Cùng tên blob có thể xuất hiện ở hai container khác nhau mà không xung đột.

### URL của một blob

Với endpoint Blob mặc định, mẫu URL:

~~~text
https://<storage-account>.blob.core.windows.net/<container>/<blob-name>
~~~

Ví dụ:

~~~text
https://stshopassetsprod.blob.core.windows.net/product-images/products/p001/main.webp
~~~

Đây là ví dụ cấu trúc URL, không khẳng định blob công khai hoặc tài nguyên đang tồn tại. **Biết URL không đồng nghĩa có quyền đọc**: container private yêu cầu phương thức ủy quyền hợp lệ. Các ký tự đặc biệt trong tên blob cần được mã hóa theo quy tắc URL khi gọi HTTP.

Storage account còn có thể có custom domain, private endpoint hoặc endpoint dịch vụ khác theo cấu hình. Không cố suy ra domain truy cập thực tế chỉ từ tên container.

## 3. Storage account và container: chọn ranh giới tổ chức

Trước khi đặt tên từng blob, hãy xác định **ranh giới quản lý**:

| Câu hỏi | Khi nên cân nhắc tách storage account | Khi một account nhiều container thường phù hợp |
|---|---|---|
| Bảo mật/network | Các workload cần chính sách network/identity/keys rất khác nhau | Cùng mô hình truy cập và tuân thủ |
| Region và redundancy | Dữ liệu buộc nằm ở region hoặc cấu hình sao chép khác | Cùng region và yêu cầu lưu trữ tương đồng |
| Quản trị và chi phí | Muốn tách rõ trách nhiệm, subscription hoặc hạn mức giám sát | Một nhóm vận hành và ngân sách chung |
| Vòng đời dữ liệu | Nhóm dữ liệu có yêu cầu account-level khác nhau | Có thể kiểm soát qua container, prefix và lifecycle |
| Khả năng mở rộng | Cần độc lập về công suất, giới hạn dịch vụ hoặc quản trị | Quy mô và giới hạn account hiện tại đáp ứng |

**Container** phù hợp để nhóm dữ liệu theo domain nghiệp vụ, mức độ bảo vệ hoặc vòng đời, ví dụ:

- **product-images**: hình ảnh được xử lý và phân phối qua ứng dụng.
- **invoices-private**: hóa đơn riêng tư, retention dài và phân quyền chặt.
- **raw-ingestion**: file mới nhận từ hệ thống nguồn, chờ kiểm tra.
- **processed-data**: dữ liệu đã kiểm định, có thể dùng cho phân tích.
- **temporary-exports**: file xuất tạm thời, có lịch dọn dẹp.

Đừng tạo một container mới cho **mỗi file** nếu không có lý do quản trị; việc này làm phức tạp quyền truy cập, automation và vòng đời. Ngược lại, nhét tất cả dữ liệu vào một container duy nhất có thể làm khó việc phân quyền, quản lý retention và giám sát.

Một quyết định thường tốt là nhóm theo **mục đích và chính sách dữ liệu**, sau đó dùng blob name/prefix để tổ chức theo tenant, loại dữ liệu và thời gian.

## 4. Quy tắc đặt tên storage account, container và blob

### Storage account name

Tên storage account dùng cho endpoint phải:

- Dài **3–24 ký tự**.
- Chỉ gồm **chữ thường a–z và số 0–9**.
- Duy nhất toàn cục trong không gian tên storage account Azure.

Ví dụ hợp lệ về định dạng: **stshopassetsprod01**. Tên này vẫn có thể đã bị người khác sử dụng; cần kiểm tra khi tạo.

### Container name

Container name thường tuân theo quy tắc DNS:

- Dài **3–63 ký tự**.
- Dùng chữ thường, số và dấu gạch nối (**-**).
- Bắt đầu và kết thúc bằng chữ hoặc số; không có hai dấu gạch nối liên tiếp.

Ví dụ: **product-images**, **invoices-private**, **raw-ingestion**. Không dùng khoảng trắng, chữ hoa hoặc dấu gạch dưới cho tên container.

### Blob name

Blob name linh hoạt hơn: có thể chứa dấu **/** để biểu diễn đường dẫn logic, ví dụ:

~~~text
tenants/t001/orders/2026/11/20/order-000001.json
~~~

Một số nguyên tắc thực tế:

1. Dùng tên có cấu trúc, nhất quán, không chứa dữ liệu nhạy cảm.
2. Chọn **một kiểu chữ** (thường là chữ thường) và cách đặt dấu phân cách.
3. Blob names **phân biệt chữ hoa/chữ thường**; **Report.pdf** và **report.pdf** là hai tên khác nhau.
4. Dùng định danh ổn định (UUID/ID nghiệp vụ) thay vì chỉ dựa trên tên file người dùng nhập.
5. Quy định rõ chính sách ghi đè: cùng tên blob mới sẽ thay thế nội dung hoặc tạo version mới nếu khả năng versioning được bật phù hợp.
6. Không giả định việc đổi tên blob trong flat namespace rẻ và nguyên tử như đổi tên file trong một file system.
7. Kiểm tra giới hạn tên, ký tự và path segments cho loại account và chế độ namespace đang dùng.

Tên chứa nhiều dấu **/** có thể tiện cho con người nhưng không phải lúc nào cũng tạo thư mục thật. Điều này được giải thích trong mục tiếp theo.

## 5. Virtual folders và prefix trong flat namespace

Trong **flat namespace** của Blob Storage, các tên:

~~~text
orders/2026/11/20/0001.json
orders/2026/11/20/0002.json
orders/2026/11/21/0003.json
customers/c001/avatar.webp
~~~

thường là **tên blob đầy đủ**, không phải cấu trúc thư mục vật lý giống NTFS/ext4. Dấu **/** là một ký tự trong blob name; Azure Portal và Storage Explorer có thể hiển thị các phần trước dấu gạch chéo như **virtual directories** để bạn dễ duyệt.

Ví dụ, Blob service có thể cung cấp cách liệt kê theo prefix:

~~~text
Prefix: orders/2026/11/20/
Kết quả:
  orders/2026/11/20/0001.json
  orders/2026/11/20/0002.json
~~~

Điều này giúp ứng dụng lấy các đối tượng theo kỳ hoặc nhóm nguồn. Nhưng **prefix không phải ranh giới bảo mật mặc định**. Một người đã được cấp quyền đọc toàn container có thể không bị giới hạn chỉ vì ứng dụng dùng prefix **customers/c001/**. Muốn phân quyền theo thư mục/đối tượng phải sử dụng đúng cơ chế được dịch vụ hỗ trợ hoặc tách container/account và kiểm tra authorization ở ứng dụng.

### List theo prefix không tương đương truy vấn SQL

Blob name có thể được liệt kê theo tên và prefix. Tuy nhiên:

- Prefix hữu ích nếu ứng dụng biết chính xác đoạn đầu của key.
- Không có nghĩa Blob Storage là công cụ tìm kiếm full-text cho nội dung tệp.
- Không nên tải danh sách mọi blob rồi lọc ở client khi dữ liệu đã rất lớn.
- Khi kết quả nhiều, SDK/REST có thể trả theo trang; phải xử lý **continuation token** cho đến khi duyệt hết.
- Các truy vấn nghiệp vụ như "mọi ảnh thuộc sản phẩm đã duyệt và chưa hết hạn" thường cần catalog hoặc index riêng.

### Khi nào nên dùng hierarchical namespace?

**Azure Data Lake Storage Gen2** bổ sung khả năng **hierarchical namespace (HNS)** cho storage account phù hợp. Khi bật, file và directory được biểu diễn với ngữ nghĩa phân cấp, hỗ trợ các thao tác quản lý thư mục hiệu quả hơn và cơ chế quyền ở mức đường dẫn như ACL theo khả năng của dịch vụ.

| Đặc điểm | Flat Blob namespace | Hierarchical namespace (Data Lake Storage Gen2) |
|---|---|---|
| Thư mục | Chủ yếu là prefix/virtual directory | Directory có ngữ nghĩa phân cấp |
| Đổi tên/di chuyển đường dẫn | Thường cần copy rồi xóa đối tượng đối với nhiều tình huống | Có thao tác rename/move directory theo API phù hợp |
| Phân quyền theo đường dẫn | Không mặc nhiên có ACL thư mục | Hỗ trợ mô hình ACL và RBAC theo thiết kế |
| Trường hợp điển hình | Ảnh, tệp ứng dụng, backup và media | Analytics lake, pipeline dữ liệu cần thao tác directory |

**HNS là quyết định kiến trúc cấp storage account**, cần kiểm tra tương thích tính năng, bảo mật, chi phí, công cụ và phương án migration trước khi bật. Không phải cứ thấy dấu **/** trong tên blob là tài khoản đã dùng Data Lake Storage Gen2.

## 6. Ba loại blob: block, append và page

Azure Blob Storage hỗ trợ các loại blob chính với hành vi ghi khác nhau:

| Loại | Cách hoạt động | Khi phù hợp |
|---|---|---|
| **Block blob** | Nội dung gồm các block; tối ưu upload và lưu dữ liệu dạng file/đối tượng | Ảnh, tài liệu, video, bản export, dữ liệu phân tích |
| **Append blob** | Hỗ trợ thêm dữ liệu vào phần cuối theo mô hình append | Một số workload log/append-only chuyên biệt |
| **Page blob** | Lưu các page với khả năng cập nhật ngẫu nhiên theo đơn vị được hỗ trợ | Workload cần random read/write như một số kịch bản VHD |

**Block blob** là lựa chọn phổ biến nhất cho dữ liệu ứng dụng. SDK có thể chia file lớn thành block rồi commit danh sách block; ứng dụng không phải tự hiện thực giao thức này nếu dùng SDK phù hợp.

**Append blob** có ngữ nghĩa thêm cuối nhưng không tự tạo hệ thống log phân tán với thứ tự toàn cục, indexing hoặc retention thông minh. Với log ứng dụng cần tìm kiếm/truy vấn, hãy đánh giá thêm Azure Monitor/Log Analytics, Event Hubs hay dịch vụ xử lý log thích hợp.

**Page blob** hướng tới cách truy cập khác block blob. Không chọn page blob chỉ vì dữ liệu có dung lượng lớn; hãy dựa trên kiểu I/O và giới hạn/tier hỗ trợ của account.

## 7. Tổ chức dữ liệu theo domain, tenant và thời gian

Thiết kế tên tốt giúp lưu trữ dễ quản lý và xử lý, nhưng không nên biến blob name thành nơi chứa toàn bộ dữ liệu nghiệp vụ.

### Phương án A: ứng dụng thương mại điện tử

~~~text
product-images/
  products/p001/v3/main.webp
  products/p001/v3/thumb.webp
  products/p002/v1/main.webp

invoices-private/
  year=2026/month=11/invoice-000001.pdf
  year=2026/month=11/invoice-000002.pdf

temporary-exports/
  job-8e2f/report.csv
  job-9c1b/report.csv
~~~

Trong ví dụ này, những dòng sau dấu tên container là **blob names**. Nhóm theo sản phẩm và phiên bản giúp tránh ghi đè không mong muốn. Nhóm theo thời gian giúp ứng dụng dễ duyệt/đối chiếu, đặc biệt với dữ liệu khối lượng lớn.

### Phương án B: SaaS nhiều khách hàng

~~~text
Container: uploads-private
  tenants/t001/documents/2026/11/doc-9a81.pdf
  tenants/t002/documents/2026/11/doc-4b26.pdf

Container: processed-private
  tenants/t001/results/job-101.json
  tenants/t002/results/job-205.json
~~~

**Cảnh báo quan trọng:** Đặt **tenants/t001/** và **tenants/t002/** trong tên blob **không cô lập quyền truy cập theo khách hàng**. Backend phải:

1. Xác thực token/phiên của người gọi.
2. Xác định tenant/customer từ danh tính đã xác thực.
3. Kiểm tra quyền đọc, ghi hoặc xóa **từng đối tượng** theo chính sách nghiệp vụ.
4. Ánh xạ customer sang đúng container/prefix từ phía server.
5. Chỉ phát hành URL hoặc SAS có phạm vi tối thiểu khi đã ủy quyền.

Nếu yêu cầu tách biệt mạnh, cân nhắc **container riêng**, **storage account riêng**, network/security boundary riêng hoặc HNS ACL theo khả năng dịch vụ. Không chỉ dựa vào chuỗi customer ID do client tự gửi trong request.

### Phương án C: dữ liệu phân tích phân vùng theo ngày

~~~text
Container: events-raw
  source=web/year=2026/month=11/day=20/part-0001.json
  source=web/year=2026/month=11/day=20/part-0002.json
  source=mobile/year=2026/month=11/day=20/part-0001.json
~~~

Kiểu **key=value** trong path thường hữu ích cho công cụ phân tích khi pipeline được thiết kế để nhận diện partition. Tuy nhiên, việc có tên **year=2026** không tự tạo partition database hoặc index truy vấn; tính năng đó phụ thuộc công cụ đọc dữ liệu.

### Chọn thứ tự prefix

Nếu ứng dụng thường truy vấn "tất cả file của tenant t001 trong ngày 20", một mẫu như **tenants/t001/events/2026/11/20/** giúp thực hiện list bằng prefix đầy đủ. Nếu thường xử lý tổng hợp theo ngày trên mọi tenant, cần cân nhắc cách tổ chức khác hoặc duy trì manifest/index để tránh phải duyệt quá nhiều prefix.

Đừng tối ưu chỉ theo sự dễ đọc. Hãy dựa vào **kiểu truy cập, khối lượng, lifecycle, phân quyền và quy trình xử lý**.

## 8. Metadata, HTTP properties và blob index tags

Ngoài nội dung, blob có thể mang những thông tin mô tả khác nhau. Ba nhóm hay bị nhầm lẫn:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| **System/HTTP properties** | Thông tin về đối tượng và cách phục vụ HTTP | Content-Type, Content-Length, ETag, Last-Modified |
| **User-defined metadata** | Các cặp key-value mô tả blob do ứng dụng thêm | source=mobile, uploadedBy=service-a |
| **Blob index tags** | Key-value được lập chỉ mục để tìm blob theo tag bằng tính năng hỗ trợ | department=finance, state=approved |

### HTTP properties: phục vụ file đúng định dạng

Một ảnh WebP nên có **Content-Type: image/webp**, còn PDF thường dùng **application/pdf**. Nếu upload blob mà không gán Content-Type đúng, browser/client có thể xử lý hoặc tải file không như mong đợi.

**ETag** hỗ trợ kiểm soát cập nhật đồng thời. Ứng dụng có thể dùng điều kiện **If-Match** để chỉ ghi thay đổi khi blob vẫn ở phiên bản đã đọc. Điều này hữu ích khi nhiều worker hoặc người dùng có thể cập nhật một đối tượng.

### Metadata

Metadata phù hợp cho mô tả nhỏ, giúp hệ thống ghi dấu nguồn dữ liệu hoặc pipeline. Nhưng metadata **không mặc nhiên được lập chỉ mục để truy vấn toàn bộ container như SQL**. Để tìm blob theo một thuộc tính nghiệp vụ, dùng catalog/index hoặc tính năng index tags khi phù hợp.

Không đặt password, token, thông tin nhạy cảm hoặc dữ liệu cá nhân không cần thiết trong metadata hay blob name. Chính sách bảo vệ và khả năng đọc metadata phải được xem xét cùng quyền truy cập dữ liệu.

### Blob index tags

Blob index tags cho phép gắn và tìm các blob dựa trên điều kiện tag được dịch vụ hỗ trợ. Ví dụ, bạn muốn tìm các tệp có **state=approved** và **docType=invoice** mà không phải tự duyệt mọi tên blob.

Tuy nhiên, tag indexing có giới hạn về số lượng tag, kiểu giá trị, API, mức hỗ trợ và chi phí. Không coi nó là database quan hệ hoặc công cụ full-text search. Một số cấu hình account/tier/namespace có khác biệt về tính năng; cần kiểm tra khả năng hỗ trợ trước khi chọn tags làm nền tảng cho nghiệp vụ.

## 9. Tên blob có phải là ID nghiệp vụ không?

Một blob name có thể đủ để truy xuất đối tượng, nhưng không phải lúc nào nên dùng làm định danh nghiệp vụ duy nhất.

Ví dụ, người dùng tải lên file tên **contract.pdf**. Nếu ứng dụng dùng thẳng tên này làm key, hai người dùng có thể vô tình tạo trùng tên; người dùng đổi tên file cũng làm tham chiếu thay đổi.

Thiết kế tốt hơn:

~~~text
DocumentId (database): doc-83b9
OwnerCustomerId: c001
DisplayFileName: contract.pdf
BlobContainer: documents-private
BlobName: customers/c001/doc-83b9/original.pdf
ContentType: application/pdf
Status: uploaded
~~~

Khi phục vụ download:

1. Client yêu cầu **GET /documents/doc-83b9**.
2. API xác thực người dùng và kiểm tra quyền đối với **DocumentId**.
3. Backend lấy container/blob name từ catalog.
4. Backend trả stream hoặc URL ủy quyền ngắn hạn, phù hợp yêu cầu bảo mật.

Nhờ vậy, đổi tên file hiển thị không buộc thay đổi blob name. Bạn cũng có thể quản lý việc xóa dữ liệu và audit theo ID nghiệp vụ ổn định.

Đối với nội dung bất biến, có thể cân nhắc tên dựa trên **hash nội dung** để khử trùng lặp. Nhưng hash không tự giải quyết phân quyền, retention, mã hóa hay nhu cầu một đối tượng thuộc nhiều khách hàng; cần thiết kế reference counting và quyền theo nghiệp vụ.

## 10. Bảo mật: container private và quyền truy cập dữ liệu

Blob URL không mặc nhiên công khai. Với dữ liệu ứng dụng, hãy ưu tiên **container private**, sau đó cấp quyền đúng chủ thể.

### Các phương thức ủy quyền thường gặp

| Cách | Khi phù hợp | Lưu ý |
|---|---|---|
| **Microsoft Entra ID + Azure RBAC** | Ứng dụng/workload dùng managed identity hoặc người vận hành | Ưu tiên phân quyền tối thiểu, dùng đúng data role |
| **User delegation SAS** | Cần cấp quyền tạm thời tới blob/container dựa trên danh tính Entra | Giới hạn permission, resource, thời gian và HTTPS |
| **Service/account SAS** | Kịch bản tích hợp cần SAS ký bằng account key | Quản lý key và rủi ro lộ token chặt chẽ; dùng khi thực sự cần |
| **Shared Key** | Tình huống tương thích cũ hoặc yêu cầu đặc biệt | Quyền rất rộng, khó kiểm soát theo người; tránh dùng nếu không cần |
| **Anonymous public access** | Chỉ dữ liệu thật sự công khai và được chính sách cho phép | Cân nhắc CDN, URL public và nguy cơ lộ dữ liệu |

Để **đọc nội dung blob** bằng Azure CLI/SDK theo Entra ID, người dùng thường cần vai trò như **Storage Blob Data Reader**; để upload, sửa hoặc xóa có thể cần **Storage Blob Data Contributor**, theo phạm vi và khả năng vai trò. **Owner/Contributor ở management plane không tự động cấp quyền đọc nội dung blob** bằng OAuth data plane.

Trên môi trường Azure, nên dùng **managed identity** cho App Service, VM, Functions hoặc workload được hỗ trợ thay vì hard-code account key trong cấu hình ứng dụng. Khi một client cần tải trực tiếp một blob riêng tư, backend có thể cấp **SAS thời hạn ngắn** sau khi kiểm tra quyền nghiệp vụ, thay vì phát key của toàn storage account.

### Mạng và mã hóa

- Dùng HTTPS/TLS phiên bản được chính sách cho phép; bật yêu cầu secure transfer.
- Cân nhắc **firewall/network rules** hoặc **Private Endpoint** nếu chỉ workload trong mạng riêng được truy cập.
- Khi sử dụng Private Endpoint, kiểm tra DNS cho endpoint Blob và đường kết nối từ ứng dụng.
- Blob Storage mã hóa dữ liệu khi lưu trữ theo mô hình dịch vụ; đánh giá customer-managed key nếu có yêu cầu quản lý khóa nâng cao.
- Giữ secret và SAS khỏi log, URL chia sẻ công khai, repository hoặc môi trường không tin cậy.
- Giám sát truy cập dữ liệu và thay đổi cấu hình bằng các dịch vụ log/audit phù hợp.

### Ngăn rò rỉ dữ liệu qua tên và link

Đừng dùng tên blob kiểu **patients/NguyenVanA/medical-result.pdf** hoặc **users/email@example.com/...**. Dù dữ liệu được bảo vệ, URL và log có thể vô tình lộ danh tính hoặc thông tin nghiệp vụ. Dùng ID ngẫu nhiên/opaque và lưu tên gốc trong catalog có kiểm soát.

## 11. Bảo vệ trước ghi đè, xóa nhầm và thay đổi không mong muốn

Tổ chức dữ liệu tốt phải đi kèm chiến lược khôi phục:

| Cơ chế | Mục tiêu | Lưu ý |
|---|---|---|
| **Blob versioning** | Giữ các phiên bản cũ của blob khi nội dung thay đổi | Cân nhắc chi phí lưu nhiều version và chính sách cleanup |
| **Blob soft delete** | Có cơ hội khôi phục blob bị xóa theo retention | Phải bật và đặt retention phù hợp trước khi có sự cố |
| **Container soft delete** | Bảo vệ khỏi xóa nhầm cả container | Khác blob soft delete, cấu hình và cách restore riêng |
| **Snapshots** | Ghi nhận trạng thái blob tại thời điểm tạo snapshot | Cần chính sách bảo trì/xóa và chi phí |
| **Immutable storage / legal hold** | Hạn chế sửa/xóa trong thời hạn hoặc theo yêu cầu pháp lý | Dùng đúng chính sách WORM, cân nhắc rủi ro vận hành |
| **Backup/DR** | Phục hồi sau lỗi dữ liệu, vùng hoặc thao tác quản trị | Khả năng phục hồi phụ thuộc dịch vụ, loại account và thiết kế |

Versioning không biến blob thành database có giao dịch xuyên nhiều đối tượng. Soft delete cũng không bảo đảm chống mọi tình huống mất dữ liệu nếu retention hết hoặc account bị xử lý sai. Với dữ liệu quan trọng, kiểm thử **restore** định kỳ và ghi nhận **RPO/RTO** thực tế.

### Tránh ghi đè vô tình

Giả sử ứng dụng tải lên cùng tên **reports/monthly.csv** mỗi tháng. Lần upload mới có thể thay nội dung cũ. Có hai chiến lược:

1. **Tên bất biến:** **reports/2026/11/report-20261120-001.csv**; giữ riêng mỗi lần tạo.
2. **Tên logic cố định + versioning/ETag:** vẫn dùng **reports/latest.csv**, nhưng bật versioning và dùng conditional write khi nhiều actor cập nhật.

Chọn theo nhu cầu. Đối với hóa đơn và tài liệu cần truy vết, tên bất biến và versioning có thể thuận tiện; đối với ảnh đại diện người dùng, có thể cần cơ chế thay phiên bản kèm invalidate cache.

## 12. Access tiers: tổ chức theo tần suất sử dụng

Với những loại block blob và storage account được hỗ trợ, Azure cung cấp các tier như **Hot, Cool, Cold và Archive**. Tier ảnh hưởng đến cách tính phí lưu trữ, thao tác đọc và yêu cầu khôi phục.

| Tier | Mẫu dữ liệu phù hợp | Điều cần lưu ý |
|---|---|---|
| **Hot** | Ảnh và tài liệu thường xuyên truy cập | Phí lưu trữ và thao tác theo mô hình hot |
| **Cool** | Dữ liệu ít đọc nhưng vẫn cần online | Truy cập/khôi phục và thời gian lưu tối thiểu cần được tính toán |
| **Cold** | Dữ liệu truy cập rất hiếm nhưng vẫn yêu cầu online theo tính năng hỗ trợ | Kiểm tra loại account, hỗ trợ khu vực và phí |
| **Archive** | Dữ liệu lưu dài hạn, hầu như không truy cập | Blob ở trạng thái offline, cần rehydrate trước khi đọc; có độ trễ và phí |

Không phải tier nào cũng có sẵn cho mọi loại blob, SKU, redundancy, vùng hay tính năng. **Archive không dành cho file cần được ứng dụng đọc ngay sau khi người dùng nhấp tải**.

Chi phí tổng phải tính cả:

- Dung lượng lưu trữ theo tier và redundancy.
- Số lượng thao tác (ghi, đọc, list, đổi tier...).
- Phí đọc/truy xuất, rehydration và thời gian lưu tối thiểu khi áp dụng.
- Data transfer/egress, replication và các chi phí liên quan.
- Dung lượng version/snapshot/soft-deleted data vẫn được lưu.

### Lifecycle management

**Lifecycle management policies** có thể chuyển tier hoặc xóa đối tượng theo điều kiện được dịch vụ hỗ trợ, ví dụ tuổi dữ liệu hoặc prefix. Thiết kế mẫu:

~~~text
Container: temporary-exports
  Sau thời gian lưu nghiệp vụ: xóa blob tạm

Container: invoices-private
  Dữ liệu mới: Hot
  Khi tần suất truy cập giảm: xem xét Cool/Cold
  Khi tới thời hạn lưu trữ: xử lý theo retention/compliance
~~~

Đây là **ý tưởng chính sách**, không phải rule JSON chạy trực tiếp. Khi thiết kế lifecycle, phải kiểm tra hành vi với version, snapshot, soft delete, immutability và thời gian lưu tối thiểu để tránh chi phí không dự kiến hoặc xóa trước thời hạn được phép.

## 13. Tổ chức dữ liệu để ứng dụng dễ mở rộng

Đặt tên tốt không chỉ giúp con người nhìn. Nó ảnh hưởng đến **cách liệt kê, xử lý batch, kiểm soát truy cập và quản lý chi phí**.

### Tránh tạo một tên hotspot không cần thiết

Với workload ghi đồng thời rất lớn, hãy đánh giá kiểu key, phân bố truy cập và giới hạn scale hiện hành. Blob Storage hỗ trợ scale lớn nhưng không phải mọi mẫu request tập trung vào cùng một blob đều hoạt động giống phân bố trên nhiều blob độc lập.

**Không** để hàng nghìn worker cùng ghi đè một blob **latest.json** như một cơ chế queue. Dùng nhiều blob bất biến và một manifest/index phù hợp hoặc dịch vụ messaging chuyên dụng. Không nên tự thêm prefix ngẫu nhiên vào mọi tên nếu điều đó phá khả năng list theo tenant/ngày; hãy đo workload thực tế và làm theo hướng dẫn hiệu năng hiện hành.

### Thiết kế ingestion → processing → serving

~~~text
Client / nguồn dữ liệu
       |
       v
Container: incoming-private
  uploads/<opaque-id>.bin
       |
       | Virus scan / validate / parse / transform
       v
Container: processed-private
  customers/<id>/documents/<doc-id>.pdf
       |
       | Business authorization
       v
App API / signed download / internal processing
~~~

File người dùng tải lên cần được coi là dữ liệu **chưa tin cậy**. Đặt tách biệt incoming và processed giúp pipeline kiểm tra MIME thực tế, malware, giới hạn file và trạng thái xử lý trước khi phục vụ cho người dùng khác.

### Catalog và manifest

Khi ứng dụng cần theo dõi:

- Ai sở hữu blob?
- Blob được gán trạng thái duyệt nào?
- Dữ liệu đã xử lý chưa?
- Mỗi blob thuộc batch nào?
- Có thể xóa blob theo yêu cầu khách hàng không?

Hãy dùng database catalog hoặc manifest được thiết kế tương ứng. Prefix/tags hỗ trợ phân loại nhưng không thay thế mọi chỉ mục nghiệp vụ hay transaction.

## 14. Xem container và blob trong Azure Portal

Các bước thực hành trên giao diện:

1. Đăng nhập [Azure Portal](https://portal.azure.com/), xác định subscription và resource group.
2. Mở một storage account loại phù hợp với Blob Storage.
3. Trong phần **Data storage**, chọn **Containers**.
4. Tạo container mới, ví dụ **documents-private**, và giữ **Private (no anonymous access)**.
5. Mở container và upload file thử nghiệm không chứa thông tin nhạy cảm.
6. Đặt blob name dạng **samples/2026/11/demo.txt** nếu giao diện upload hỗ trợ tên/prefix tương ứng.
7. Kiểm tra Properties, Content type, ETag, access tier, metadata hoặc tags nếu có.
8. Thử duyệt theo cấu trúc prefix để quan sát các **virtual folders**.
9. Kiểm tra Access control (IAM), versioning, soft delete và các cấu hình bảo vệ theo phạm vi cần thiết.

Tên menu hoặc tính năng hiển thị có thể khác tùy loại storage account, namespace và phiên bản Portal. Nếu không xem được dữ liệu dù thấy storage account, hãy kiểm tra quyền **data plane**, không mặc định đó là lỗi giao diện.

## 15. Thực hành bằng Azure CLI: tạo container và tổ chức blob

Đây là bài lab dành cho **subscription và resource group học tập** được phép sử dụng. Có thể phát sinh chi phí storage, thao tác và network; hãy đặt budget hoặc kiểm soát chi phí theo chính sách tổ chức. Ví dụ shell dùng **Bash trong Azure Cloud Shell** hoặc môi trường Bash có Azure CLI; PowerShell có cú pháp biến và nối dòng khác.

### Chuẩn bị

- Có Azure CLI, đăng nhập bằng tài khoản có quyền quản lý tài nguyên theo yêu cầu bài lab.
- Được phép tạo storage account ở region được chọn và có quyền tạo blob data tương ứng.
- Chọn một storage account name **duy nhất toàn cục**, đúng mẫu chữ thường và số.
- Dữ liệu mẫu không chứa PII, token hay tài liệu thật.

### Bước 1: xác nhận subscription và khai báo biến

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-blob-storage-lab"
LOCATION="southeastasia"
STORAGE_ACCOUNT="stbloblabreplace123"
CONTAINER="documents-private"
~~~

**Bắt buộc thay** **stbloblabreplace123** bằng tên storage account còn trống, dài 3–24 ký tự chỉ gồm chữ thường/số. Không sử dụng nguyên tên trong production, và xác nhận **SUBSCRIPTION_ID** trước khi tạo tài nguyên. Nếu chính sách tổ chức không cho tạo storage account mới, dùng một account lab có sẵn được cấp quyền thay vì tự thay cấu hình của account dùng chung.

### Bước 2: tạo resource group và storage account

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION" \
  --tags environment=learning purpose=blob-lesson

az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2
~~~

**Standard_LRS** dùng local redundancy cho bài tập; không coi đó là lựa chọn DR phù hợp mọi dữ liệu production. Ở môi trường thực, chọn ZRS/GRS/GZRS hoặc cấu hình khác dựa trên yêu cầu khả dụng, vùng hỗ trợ và ngân sách. Việc tạo account trong ví dụ không tự bật versioning hoặc soft delete; bạn cần cấu hình riêng nếu muốn thử cơ chế phục hồi.

### Bước 3: tạo container private bằng Entra ID

~~~bash
az storage container create \
  --account-name "$STORAGE_ACCOUNT" \
  --name "$CONTAINER" \
  --auth-mode login \
  --public-access off
~~~

Tùy tài khoản/role, có thể gặp lỗi **AuthorizationPermissionMismatch** hoặc **AuthorizationFailure**. Cần được cấp đúng data plane permission, chẳng hạn **Storage Blob Data Contributor**, hoặc vai trò/phạm vi tương đương. Vai trò Azure Owner/Contributor thông thường ở management plane không tự động cung cấp toàn bộ quyền OAuth để thao tác blob. Đợi quyền được áp dụng trước khi thử lại, không vội dùng account key để vượt chính sách tổ chức.

### Bước 4: tạo dữ liệu mẫu và upload dưới tên phân cấp logic

~~~bash
printf '{"orderId":"order-001","status":"demo"}\n' > order-001.json

az storage blob upload \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "orders/raw/2026/11/20/order-001.json" \
  --file "./order-001.json" \
  --content-type "application/json" \
  --auth-mode login \
  --overwrite false
~~~

Blob name đã chứa **orders/raw/2026/11/20/**. Với namespace phẳng, không cần tạo folder vật lý trước khi upload. Tên đầy đủ của blob là **orders/raw/2026/11/20/order-001.json** trong container **documents-private**.

### Bước 5: liệt kê các blob theo prefix

~~~bash
az storage blob list \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --prefix "orders/raw/2026/11/" \
  --auth-mode login \
  --output table
~~~

Bạn cần thấy blob đã upload nếu quyền list phù hợp và thao tác trước hoàn tất. Prefix lọc theo **đoạn đầu của blob name**. Nếu có nhiều kết quả, ứng dụng sử dụng SDK/REST cần xử lý phân trang theo continuation token; đừng mặc định một lần trả về tất cả dữ liệu.

### Bước 6: xem thuộc tính và tải về

~~~bash
az storage blob show \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "orders/raw/2026/11/20/order-001.json" \
  --auth-mode login \
  --output json

az storage blob download \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "orders/raw/2026/11/20/order-001.json" \
  --file "./downloaded-order-001.json" \
  --auth-mode login
~~~

Kiểm tra nội dung file tải về, Content-Type và ETag nếu muốn. Không gửi account key hoặc SAS dài hạn vào log chỉ để chẩn đoán.

### Bước 7: quan sát quyền truy cập

Thử mở URL blob trong trình duyệt riêng tư khi **không có token/SAS**. Nếu container và account private đúng cấu hình, request không được trả nội dung blob chỉ vì URL đã biết. Hành vi HTTP cụ thể còn tùy loại request và dịch vụ; không suy luận rằng một mã lỗi duy nhất có thể thay cho kiểm tra permission và network access.

### Bước 8: dọn dẹp tài nguyên lab

Trước khi xóa, kiểm tra **RG** đúng là nhóm riêng của lab và storage account không chứa dữ liệu cần giữ. Xóa cả resource group:

~~~bash
az group delete \
  --name "$RG" \
  --yes

az group exists --name "$RG"
~~~

Khi kết quả là **false**, resource group không còn tồn tại theo ARM. Chi phí có thể hiển thị trễ; kiểm tra Cost Management nếu đã phát sinh giao dịch hoặc các tài nguyên tính phí khác.

**Không chạy lệnh xóa nhóm** trên resource group dùng chung hoặc production. Nếu dùng account có sẵn thay cho account lab mới, chỉ dọn blob/container do chính bài thực hành tạo và theo quy trình được phê duyệt.

## 16. Tình huống thiết kế: hệ thống lưu tài liệu nhiều khách hàng

Giả sử bạn xây dựng SaaS lưu hợp đồng cho 300 doanh nghiệp. Mỗi khách hàng có người dùng đăng nhập qua Microsoft Entra ID và có các yêu cầu:

- Tài liệu của khách hàng A không được lộ cho B.
- Người dùng có thể upload, xem danh sách và tải xuống hợp đồng mình được phép đọc.
- Có quy trình duyệt hợp đồng và lưu phiên bản.
- Dữ liệu xóa nhầm phải có khả năng khôi phục trong thời hạn quản trị.
- Tài liệu cũ ít truy cập cần được tối ưu chi phí.

### Đề xuất tổ chức dữ liệu

~~~text
Storage account: stcontractsprod
  Container: contract-uploads-private
    tenants/<tenant-id>/incoming/<document-id>/original.pdf

  Container: contract-docs-private
    tenants/<tenant-id>/approved/<document-id>/v1.pdf
    tenants/<tenant-id>/approved/<document-id>/v2.pdf

  Container: contract-exports-private
    jobs/<job-id>/export.csv
~~~

Đây là một phương án logic, không phải cấu hình đủ để cô lập khách hàng. Nếu yêu cầu compliance cao, cần đánh giá tách account/container, network boundary và encryption keys phù hợp.

### Luồng upload an toàn

~~~mermaid
sequenceDiagram
  participant U as Người dùng
  participant API as App API
  participant DB as Catalog DB
  participant B as Blob Storage
  U->>API: Xin tải hợp đồng lên
  API->>API: Xác thực, xác định tenant và quyền
  API->>DB: Tạo document ID và trạng thái pending
  API-->>U: Quyền upload giới hạn hoặc upload qua API
  U->>B: Upload tới blob được chỉ định (nếu có quyền)
  API->>B: Xác minh blob và kiểm tra dữ liệu đầu vào
  API->>DB: Đánh dấu uploaded/approved theo quy trình
  U->>API: Xin tải tài liệu xuống
  API->>DB: Kiểm tra tài liệu thuộc tenant và quyền
  API-->>U: Stream hoặc URL tải có hạn và phạm vi hẹp
~~~

Trong một số kiến trúc, backend upload trực tiếp thay vì cấp URL cho client. Dù chọn cách nào, **ứng dụng phải xác thực quyền trước khi phát hành token tải lên/tải xuống**, giới hạn destination và kiểm tra nội dung không tin cậy.

### Chọn metadata và catalog

| Thuộc tính | Nên để ở đâu? | Lý do |
|---|---|---|
| Document ID, customer ID, owner ID | Catalog database | Phân quyền và truy vấn nghiệp vụ |
| Blob container/name, version ID | Catalog database | Xác định bản lưu vật lý |
| Content-Type, size, ETag | Blob properties; có thể đồng bộ vào catalog | Phục vụ HTTP, kiểm tra integrity/cạnh tranh |
| Source service, pipeline stage | Metadata nếu phù hợp | Truy vết kỹ thuật |
| Tag được hỗ trợ để tìm đối tượng | Blob index tags khi phù hợp | Truy vấn theo tập thuộc tính đơn giản |
| Trạng thái duyệt, hợp đồng, retention nghiệp vụ | Catalog, policy và quy trình compliance | Không nhờ một trường metadata tự quyết định xóa/đọc |

### Phương án vòng đời

1. Blob mới được upload vào container incoming private.
2. Worker kiểm tra file, xác thực định dạng và quét bảo mật nếu cần.
3. Dữ liệu hợp lệ được đưa vào nhóm processed/approved; catalog cập nhật trạng thái.
4. Versioning/soft delete hoặc phương án tương đương được cấu hình theo chính sách.
5. Dữ liệu ít truy cập được xét chuyển tier bằng lifecycle policy.
6. Khi hết retention và được phép xóa, hệ thống xóa có kiểm soát và ghi audit.

Một vòng đời tốt giải quyết cả **bảo mật, truy vết, phục hồi và chi phí**, không chỉ cách đặt tên.

## 17. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Azure Portal thấy storage account nhưng không thấy blob | Chưa có data plane role, lỗi network hoặc chưa có quyền list | Kiểm tra Storage Blob Data Reader/Contributor, IAM scope, firewall, role propagation |
| Blob upload bị 403 | Data RBAC chưa đủ, shared key/SAS bị chặn, SAS hết hạn hoặc network rule | Xem auth mode, quyền, scope và logs theo chính sách |
| URL blob không mở công khai được | Container private | Đây là hành vi mong đợi; dùng Entra ID/SAS phù hợp |
| Tạo container lỗi vì tên | Có chữ hoa, dấu gạch dưới, tên quá ngắn hoặc không hợp lệ | Đối chiếu naming rules và container đang tồn tại |
| Không thấy thư mục sau upload | Flat namespace dùng virtual folder; prefix sai hoặc blob name khác | Xem tên blob chính xác, liệt kê theo prefix |
| Tìm metadata theo điều kiện không hiệu quả | Metadata không phải index truy vấn chung | Dùng blob index tags khi hỗ trợ hoặc catalog riêng |
| Upload đè mất nội dung cũ | Trùng blob name, overwrite được cho phép, chưa bật versioning | Dùng tên bất biến, conditional writes, versioning |
| Client tải PDF thành file lạ | Content-Type chưa đúng | Kiểm tra Content-Type/Content-Disposition và ứng dụng |
| File cũ chuyển Archive rồi download thất bại | Blob offline và cần rehydrate | Xem trạng thái tier, quy trình rehydration và thời gian chờ |
| Chi phí tăng dù ứng dụng ít truy cập | Nhiều version/snapshot/soft delete, tier và retrieval/transactions | Kiểm tra metrics, lifecycle, retention và cost details |
| Khách hàng A đọc được file B | Authorization backend dựa vào prefix từ client, hoặc phân quyền container quá rộng | Kiểm tra mapping tenant, data RBAC, SAS scope và API object authorization |
| Xóa blob nhưng vẫn còn bị tính dung lượng | Version/snapshot/soft deleted data còn trong retention | Kiểm tra chính sách và trạng thái các phiên bản |
| Dùng endpoint private không truy cập được | DNS/Private Endpoint/network rule không đúng | Kiểm tra DNS vùng riêng, đường mạng và firewall |

Khi xử lý sự cố, ghi lại account, container, **blob name không nhạy cảm**, thời gian, operation, HTTP status, request ID và identity/permission context. Không ghi access key, SAS token, credential hoặc nội dung file thật vào log/ticket.

## 18. Checklist thiết kế Blob Storage trước production

- [ ] Xác định rõ dữ liệu cần dùng object storage thay vì database hoặc file share.
- [ ] Chọn storage account theo region, redundancy, network/security boundary và yêu cầu chi phí.
- [ ] Thiết kế container theo domain, phân quyền và lifecycle; tránh tạo container tùy tiện.
- [ ] Blob names nhất quán, ổn định, không chứa thông tin nhạy cảm và hỗ trợ prefix listing.
- [ ] Phân biệt virtual folder với HNS directory; chọn namespace phù hợp nhu cầu.
- [ ] Chọn đúng block/append/page blob theo mẫu I/O.
- [ ] Có catalog nghiệp vụ cho owner, quyền, trạng thái và tham chiếu blob.
- [ ] Container private; dùng Entra ID/managed identity và data RBAC tối thiểu khi khả thi.
- [ ] Nếu cấp SAS, giới hạn resource, permissions, thời gian, giao thức và bảo vệ token.
- [ ] Kiểm soát public access, TLS, network rules, Private Endpoint và DNS theo yêu cầu.
- [ ] Xem xét versioning, blob/container soft delete, backup, immutability và thử restore.
- [ ] Thiết kế tier/lifecycle theo tần suất truy cập và retention thực tế.
- [ ] Giám sát lưu trữ, số thao tác, lỗi truy cập, log, chi phí và hạn mức.
- [ ] Kiểm thử upload/download, listing theo prefix, overwrite, phục hồi và cách ly tenant.
- [ ] Có quy trình dọn dữ liệu thử nghiệm và xử lý dữ liệu khi khách hàng rời dịch vụ.

## 19. Câu hỏi tự kiểm tra

1. Sự khác nhau giữa storage account, container và blob là gì? Tên blob có duy nhất trên toàn Azure không?
2. Vì sao Blob Storage thường phù hợp với ảnh sản phẩm hơn lưu ảnh trực tiếp trong bảng dữ liệu giao dịch?
3. Trong flat namespace, đường dẫn **reports/2026/11/a.csv** có tạo ba thư mục thật không?
4. Khi nào chọn HNS thay cho virtual folders của flat namespace?
5. Block blob, append blob và page blob phù hợp kiểu workload nào?
6. Prefix listing có thể thay thế một truy vấn SQL lọc theo trạng thái phê duyệt không?
7. Metadata và blob index tags khác nhau như thế nào?
8. Vì sao người dùng có quyền Contributor trên resource group vẫn có thể không đọc được nội dung blob qua OAuth?
9. Với SaaS nhiều khách hàng, tại sao prefix **tenants/t001/** không đủ để cô lập dữ liệu?
10. Chọn Hot, Cool, Cold và Archive dựa vào những đặc điểm chi phí/vận hành nào?
11. Versioning và soft delete giúp khôi phục ra sao? Vì sao vẫn cần chiến lược backup/DR?
12. Khi tạo URL tải file cho khách hàng, tại sao không gửi account key hoặc SAS rộng, dài hạn?
13. Nếu muốn giữ tất cả report theo ngày, bạn sẽ chọn blob name và lifecycle như thế nào?

## 20. Tài liệu tham khảo

- [Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction) — mô hình object storage, container và các loại blob.
- [List blobs with Azure Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-list) — liệt kê blob, prefix và phân trang.
- [Manage blob properties and metadata](https://learn.microsoft.com/azure/storage/blobs/storage-blob-properties-metadata) — Content-Type, ETag và metadata.
- [Find blobs by tags](https://learn.microsoft.com/azure/storage/blobs/storage-manage-find-blobs) — blob index tags và cách tìm đối tượng.
- [Azure Data Lake Storage hierarchical namespace](https://learn.microsoft.com/azure/storage/blobs/data-lake-storage-namespace) — thư mục phân cấp và khả năng liên quan.
- [Access tiers for blob data](https://learn.microsoft.com/azure/storage/blobs/access-tiers-overview) — Hot/Cool/Cold/Archive và chi phí.
- [Authorize access to blobs with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory) — data plane authentication/RBAC.
- [Soft delete for blobs](https://learn.microsoft.com/azure/storage/blobs/soft-delete-blob-overview) — phục hồi blob bị xóa.
- [Lifecycle management overview](https://learn.microsoft.com/azure/storage/blobs/lifecycle-management-overview) — tự động chuyển tier và xử lý dữ liệu theo tuổi.
- [Azure CLI: az storage blob](https://learn.microsoft.com/cli/azure/storage/blob) — upload, list, show và download.

**Kết luận:** Cách tổ chức Blob Storage tốt bắt đầu từ **ranh giới storage account/container**, tiếp đến là **blob names/prefix**, quyền truy cập và vòng đời dữ liệu. Folder hiển thị không nhất thiết là folder thật; prefix không phải cơ chế phân quyền; metadata không phải database tìm kiếm. Hãy sử dụng container private, tên blob ổn định, catalog nghiệp vụ, dữ liệu được bảo vệ và lifecycle phù hợp để kiến trúc ứng dụng Azure vừa dễ mở rộng vừa có thể quản trị, phục hồi và kiểm soát chi phí.
