# Kiểm kê tài nguyên bằng Resource Search và tags

## Mục tiêu bài học

Một landing zone Oracle Cloud Infrastructure (OCI) thường chứa nhiều compartment, nhiều region và nhiều nhóm cùng triển khai ứng dụng. Khi cần biết ứng dụng đang dùng tài nguyên nào, ai chịu trách nhiệm hoặc tài nguyên nào chưa được phân loại, việc mở từng trang Compute, Networking, Storage và Database sẽ nhanh chóng trở nên khó kiểm soát.

Trong chủ đề **Tổ chức tài nguyên và landing zone** của module **CLOUD_PROVIDERS_ORACLE**, bài học này kết hợp Resource Search với tags để xây dựng một bản kiểm kê có phạm vi, có định danh và có thể đối chiếu. Bạn sẽ thực hành cách viết truy vấn, thu thập kết quả qua OCI CLI, phát hiện thiếu tag và biến dữ liệu kiểm kê thành đầu vào cho quản trị chi phí, giám sát và vận hành hạ tầng OCI.

Các tên namespace, compartment, ứng dụng và số liệu dưới đây là ví dụ. Những đoạn CLI dành cho người học chạy trong môi trường đã được cấp quyền; chúng không biểu thị tài nguyên thực tế của bất kỳ tenancy nào.

## 1. Bản kiểm kê cần trả lời điều gì?

Giả sử nhóm nền tảng quản lý ứng dụng `orders` gồm Compute instances, VCN, boot volumes, block volumes và một dịch vụ cơ sở dữ liệu Oracle. Production và development nằm ở các compartment khác nhau; một số tài nguyên phục hồi nằm ở region thứ hai.

Nhóm cần trả lời:

- Những tài nguyên nào được gắn với ứng dụng `orders` trong phạm vi đang khảo sát?
- Tài nguyên nằm ở region và compartment nào, có trạng thái gì?
- Nhóm nào chịu trách nhiệm khi có sự cố hoặc phát sinh chi phí?
- Tài nguyên nào thiếu thông tin môi trường, chủ sở hữu hoặc cost center?
- Những phần nào của hạ tầng chưa đủ dữ liệu để kết luận đã kiểm kê đầy đủ?

Resource Search giúp khám phá tài nguyên dựa trên dữ liệu được lập chỉ mục; tags bổ sung ý nghĩa quản trị cho từng tài nguyên. Một bản kiểm kê hữu ích kết hợp hai loại thông tin đó với **phạm vi quan sát**: tenancy, danh sách region, compartment, principal thực hiện và thời điểm thu thập.

Không nên chỉ báo “có 120 tài nguyên”. Cần diễn đạt đủ nghĩa, chẳng hạn: “Quan sát thấy 120 OCID duy nhất thuộc các loại tài nguyên được hỗ trợ, trong hai compartment và hai region đã kiểm tra, bằng principal kiểm kê tại thời điểm ghi nhận”.

## 2. Resource Search nhìn thấy những gì?

### 2.1. Phạm vi hỗ trợ của dịch vụ

Search hỗ trợ tìm tài nguyên trong tenancy và các region được chọn. Chỉ những resource type và thuộc tính được hỗ trợ lập chỉ mục mới có thể truy vấn. Danh sách hỗ trợ thay đổi theo dịch vụ; `ListResourceTypes` là đầu mối tra thông tin resource type và thuộc tính hiện hành. [Oracle: Overview of Search](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm).

Điều đó có ba hệ quả khi thiết kế inventory:

| Giới hạn quan sát | Cách xử lý trong kiểm kê |
| --- | --- |
| Có loại tài nguyên chưa được Search hỗ trợ hoặc chưa đủ thuộc tính | Bổ sung List/Get API của dịch vụ tương ứng |
| Chỉ kiểm tra một số region | Ghi rõ region đã kiểm tra và region chưa kiểm tra |
| Dữ liệu Search là dữ liệu tóm tắt | Đọc chi tiết từ dịch vụ sở hữu khi cần cấu hình hoặc trạng thái quyết định |

Ví dụ, kiểm kê dịch vụ cơ sở dữ liệu OCI không đồng nghĩa liệt kê toàn bộ bảng và schema bên trong cơ sở dữ liệu. Tương tự, danh sách bucket không thay thế một bản kiểm kê từng object hoặc từng phiên bản dữ liệu. Hãy xác định cấp tài nguyên cần quản lý trước khi chọn nguồn dữ liệu.

### 2.2. Quyền IAM quyết định kết quả có thể thấy

Search không yêu cầu một policy riêng để được gọi các API tìm kiếm, nhưng kết quả phụ thuộc quyền trên tài nguyên đích. Thông thường quyền `inspect` của resource type cho phép nhìn thấy metadata trong Search; một số dịch vụ cần `read` thay vì chỉ `inspect`. [Oracle: Details for Search](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/searchpolicyreference.htm).

Vì vậy, **kết quả rỗng không chứng minh tài nguyên không tồn tại**. Một principal chỉ được xem Compute có thể không nhìn thấy hệ thống cơ sở dữ liệu dù chúng cùng thuộc một ứng dụng.

Nhóm nền tảng nên xác định principal kiểm kê ổn định, cấp đúng quyền đọc cần thiết và ghi lại phạm vi quyền. Việc mở rộng quyền để kiểm kê phải bám yêu cầu quan sát; không cần cấp quyền tạo, xóa hay thay đổi tài nguyên chỉ để đọc danh sách.

### 2.3. Chỉ mục không phản ánh mọi thay đổi tức thì

Search có tính nhất quán cuối cùng: tài nguyên vừa tạo hoặc metadata vừa cập nhật có thể chưa xuất hiện ngay. Đôi khi trang danh sách của dịch vụ đã thấy tài nguyên trong khi Search chưa thấy. Khi kết quả khác kỳ vọng, cần kiểm tra quyền, resource type, điều kiện truy vấn và chờ chỉ mục cập nhật trước khi kết luận. [Oracle: Query or Search Results are Not as Expected](https://docs.oracle.com/en-us/iaas/Content/Search/Troubleshooting/noresults.htm).

Đối với quyết định vận hành như thay đổi tag hàng loạt hoặc xác nhận một tài nguyên đã được thu hồi, hãy đọc lại tài nguyên qua API của dịch vụ sở hữu. Bản kiểm kê từ Search phục vụ khám phá và đối chiếu; nó không phải một ảnh chụp giao dịch đồng thời của toàn tenancy.

## 3. Thiết kế tags để kiểm kê có ý nghĩa

### 3.1. Free-form tags và defined tags

| Thuộc tính | Free-form tags | Defined tags |
| --- | --- | --- |
| Cấu trúc | Key và value | Namespace, key và value |
| Ví dụ | `environment=prod` | `Governance.Environment=prod` |
| Quản lý định nghĩa | Người dùng nhập trực tiếp trên tài nguyên | Quản trị viên tạo namespace và key definition |
| Tính nhất quán | Cần tự xử lý biến thể tên và giá trị | Có thể quản lý schema và danh sách giá trị cho phép |
| Vai trò phù hợp | Metadata đơn giản, thử nghiệm hoặc tương thích dữ liệu cũ | Metadata dùng chung để quản trị lâu dài |

Defined tags cho phép tổ chức quản lý định nghĩa tập trung và tách quyền tạo định nghĩa khỏi quyền sử dụng tag. Chúng phù hợp làm nền tảng cho dữ liệu kiểm kê nhất quán. [Oracle: Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Free-form tag không có namespace; key và value phân biệt chữ hoa, chữ thường. Chúng không hỗ trợ các tính năng như predefined values, tag variables hoặc làm điều kiện tag trong IAM policy. [Oracle: Understanding Free-form Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingfreeformtags.htm).

### 3.2. Bộ tag tối thiểu cho ví dụ landing zone

Một schema minh họa:

| Defined tag | Ví dụ | Ý nghĩa khi kiểm kê |
| --- | --- | --- |
| `Governance.Application` | `orders` | Nhóm tài nguyên theo ứng dụng |
| `Governance.Environment` | `dev`, `test`, `prod`, `recovery` | Phân biệt môi trường |
| `Governance.OwnerTeam` | `team-orders` | Đầu mối vận hành |
| `Governance.CostCenter` | `CC-210` | Đối chiếu trách nhiệm chi phí |
| `Governance.ManagedBy` | `terraform`, `manual` | Nguồn quản lý cấu hình |

Đây là quy ước của tổ chức trong ví dụ, không phải các tag bắt buộc của OCI. Nên thống nhất cách viết và tập giá trị trước khi dùng chúng làm tiêu chí báo cáo.

Dữ liệu defined tags trong mô hình API có dạng:

```json
{
  "Governance": {
    "Application": "orders",
    "Environment": "prod",
    "OwnerTeam": "team-orders",
    "CostCenter": "CC-210",
    "ManagedBy": "terraform"
  }
}
```

Một key tồn tại nhưng có giá trị rỗng chưa đáp ứng yêu cầu “xác định được chủ sở hữu”. Giá trị `unknown` cũng cần được quy định rõ: đó là một ngoại lệ đang xử lý, không mặc nhiên là dữ liệu đầy đủ.

Tag `OwnerTeam` nên chỉ đến một nhóm chịu trách nhiệm ổn định; đừng coi người đã tạo tài nguyên đương nhiên là người đang vận hành. Tag ứng dụng cũng không mô tả đầy đủ quan hệ phụ thuộc: VCN dùng chung có thể phục vụ nhiều ứng dụng.

Metadata dùng để điều khiển tự động hóa cần có người quản lý schema và quyền thay đổi phù hợp. Không đưa mật khẩu, private key hoặc nội dung dữ liệu nghiệp vụ vào tag.

### 3.3. Tag trên compartment khác với tag thực tế trên tài nguyên

Tag gắn trên một compartment không nên được dùng làm bằng chứng rằng cùng tag đó đã xuất hiện trong metadata của mọi tài nguyên bên trong. Khi cần kiểm tra resource tags, phải đọc resource tags thực tế.

**Tag defaults** là một cơ chế riêng dành cho defined tags: áp dụng tag khi tạo tài nguyên trong compartment và các compartment con theo quy tắc kế thừa. Chúng không bổ sung hồi tố cho tài nguyên có sẵn; sửa hoặc xóa tag default cũng không tự sửa hay xóa những giá trị đã áp dụng trước đó. [Oracle: Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

Do đó, sau khi triển khai tag defaults, vẫn cần kiểm kê để phát hiện tài nguyên cũ thiếu tag hoặc tài nguyên đã bị sửa tag. Khi di chuyển compartment, tags cũng không tự cập nhật theo vị trí mới; cần đối chiếu lại quy ước quản trị sau di chuyển. [Oracle: Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

## 4. Viết truy vấn Resource Search

Resource Search sử dụng ngôn ngữ truy vấn riêng. Đây không phải SQL; hãy dùng tên resource type và thuộc tính mà Search hỗ trợ.

### 4.1. Bắt đầu bằng tập tài nguyên quan sát được

```text
query all resources
```

Đây là truy vấn nền, tìm các tài nguyên được hỗ trợ mà principal được phép thấy trong phạm vi region đang áp dụng. Từ khóa `all` không mở rộng quyền IAM hoặc tự bao phủ những region chưa chọn.

Để xem một nhóm loại tài nguyên:

```text
query instance, volume resources
```

Để tìm trực tiếp tài nguyên thuộc một compartment:

```text
query all resources
where compartmentId = '<compartment-ocid>'
```

Điều kiện bằng `compartmentId` khớp compartment được chỉ định; không tự diễn đạt việc lấy toàn bộ cây con. Nếu phạm vi gồm cha và con, hãy xác định danh sách OCID tương ứng rồi truy vấn hoặc ghép điều kiện cho từng compartment.

Các mẫu truy vấn chính thức minh họa cách chọn resource type và lọc theo compartment. [Oracle: Sample Queries](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/samplequeries.htm).

### 4.2. Tìm theo defined tag

Giả sử cần tìm tài nguyên có `Governance.Application=orders`:

```text
query all resources
where
  (definedTags.namespace = 'Governance' &&
   definedTags.key = 'Application' &&
   definedTags.value = 'orders')
```

Nhóm điều kiện diễn đạt đầy đủ namespace, key và value. Không thay cú pháp này bằng đường dẫn JSON như `definedTags.Governance.Application` khi viết truy vấn Search.

Để giới hạn đồng thời vào một compartment:

```text
query all resources
where
  compartmentId = '<production-compartment-ocid>' &&
  (definedTags.namespace = 'Governance' &&
   definedTags.key = 'Application' &&
   definedTags.value = 'orders')
```

Cách viết bộ điều kiện tag được Oracle minh họa trong hướng dẫn truy vấn bằng Console, CLI và API. [Oracle: Running a Custom, Free-Form Query](https://docs.oracle.com/en-us/iaas/Content/Search/Tasks/queryingresources_topic-To_run_a_custom_freeform_query_to_find_a_resource.htm).

### 4.3. Tìm free-form tag của dữ liệu cũ

Nếu một số tài nguyên cũ đang dùng `application=orders` dưới dạng free-form tag:

```text
query all resources
where
  (freeformTags.key = 'application' &&
   freeformTags.value = 'orders')
```

Tập này cần được đối chiếu với schema defined tags. Không suy ra hai tài nguyên thuộc cùng tiêu chuẩn quản trị chỉ vì chúng có chuỗi `orders` ở đâu đó trong metadata.

Tìm kiếm bằng `matching 'orders'` có thể khớp nhiều thuộc tính được lập chỉ mục. Nó hữu ích để khám phá ban đầu nhưng không tương đương điều kiện chính xác “tag Application có giá trị orders”.

### 4.4. Lọc trạng thái và sắp xếp

Ví dụ tìm các instance đang chạy trong một compartment:

```text
query instance resources
where
  compartmentId = '<production-compartment-ocid>' &&
  lifeCycleState = 'RUNNING'
sorted by timeCreated desc
```

Không dùng điều kiện `RUNNING` cho mọi resource type: lifecycle state là khái niệm phụ thuộc dịch vụ. Để kiểm kê đầy đủ tài nguyên có thể phát sinh chi phí hoặc cần thu hồi, thường phải quan sát cả các trạng thái khác.

Search hỗ trợ `where`, `matching`, `sorted by` và các toán tử theo ngữ pháp của dịch vụ. Phép so sánh chuỗi `=` trong Search không phân biệt hoa thường. Vì vậy, kết quả tìm kiếm không đủ chứng minh cách viết tag đã đúng quy ước; muốn phát hiện `Prod` thay vì `prod`, hãy kiểm tra giá trị nguyên gốc từ API hoặc CLI. [Oracle: Search Language Syntax](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/querysyntax.htm).

## 5. Thực hiện trên Console và đọc chi tiết đúng lúc

Trong thanh tìm kiếm OCI Console, chuyển sang **Advanced resource query**, nhập truy vấn rồi xác nhận các region áp dụng. Khi số region cần khảo sát vượt khả năng lựa chọn của giao diện tại một lần tìm kiếm, hãy chia thành nhiều lượt có ghi nhận phạm vi hoặc dùng API/CLI để điều phối.

Quy trình kiểm kê trên Console:

1. Chọn region và truy vấn một tài nguyên đã biết bằng OCID hoặc phạm vi cụ thể để xác nhận khả năng quan sát.
2. Chạy truy vấn nền cho compartment cần kiểm kê.
3. Chạy truy vấn theo tag ứng dụng hoặc môi trường.
4. Mở chi tiết một số tài nguyên đại diện để đối chiếu tag, compartment và trạng thái.
5. Ghi lại query text, phạm vi region và thời điểm; không chỉ lưu một ảnh danh sách không có ngữ cảnh.

Kết quả Search là metadata tóm tắt. API/CLI có thể cung cấp tags và những thông tin phục vụ xử lý dữ liệu thuận tiện hơn giao diện kết quả. Khi cần thông tin chuyên biệt như cấu hình VM, quan hệ đính kèm volume hay cấu hình database, lấy thêm từ dịch vụ sở hữu tài nguyên. [Oracle: Overview of Search](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm).

## 6. Thu thập inventory bằng OCI CLI

### 6.1. Truy vấn một trang để kiểm tra phạm vi

Sau khi cấu hình OCI CLI và principal có quyền đọc thích hợp, người học có thể chạy đoạn PowerShell sau:

```powershell
$ociInventoryRegion = '<region-id>'
$ociInventoryCompartment = '<compartment-ocid>'
$ociInventoryQuery = "query all resources where compartmentId = '$ociInventoryCompartment'"

oci --region $ociInventoryRegion search resource structured-search --query-text $ociInventoryQuery --limit 100 --output json
```

`--query-text` là ngôn ngữ của Search; bộ lọc `--query` của OCI CLI, nếu dùng, là một lớp xử lý đầu ra khác. Đừng dùng phép lọc đầu ra để thay thế việc xác định đúng phạm vi truy vấn phía dịch vụ.

Lệnh `structured-search` có các tham số `--limit` và `--page`. Một trang có nhiều kết quả không đồng nghĩa đã lấy hết; phải tiếp tục theo page token đến khi hết token. Tham khảo đúng bộ tùy chọn của lệnh đang dùng thay vì giả định mọi lệnh OCI CLI đều có cùng tùy chọn phân trang. [Oracle: OCI CLI structured-search](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/search/resource/structured-search.html).

### 6.2. Thu thập nhiều trang và nhiều region

Đoạn dưới dùng **PowerShell 7**, đọc kết quả JSON vào bộ nhớ và giữ nguyên tags. `ConvertFrom-Json -AsHashtable` giúp tránh ép các key tag thành tên thuộc tính của đối tượng PowerShell. Ví dụ chỉ khảo sát **một compartment chính xác** tại các region đã khai báo:

```powershell
$ociInventoryRegions = @('<region-id-1>', '<region-id-2>')
$ociInventoryCompartment = '<compartment-ocid>'
$ociInventoryQuery = "query all resources where compartmentId = '$ociInventoryCompartment'"
$ociInventoryRows = [System.Collections.Generic.List[object]]::new()
$ociScanStartedAt = [DateTime]::UtcNow.ToString('o')

foreach ($ociRegion in $ociInventoryRegions) {
    $ociNextPage = $null
    do {
        $ociArguments = @(
            '--region', $ociRegion,
            'search', 'resource', 'structured-search',
            '--query-text', $ociInventoryQuery,
            '--limit', '100', '--output', 'json'
        )
        if (-not [string]::IsNullOrEmpty($ociNextPage)) {
            $ociArguments += @('--page', $ociNextPage)
        }

        $ociJsonLines = & oci @ociArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Không hoàn tất kiểm kê tại region $ociRegion"
        }
        $ociResponse = ($ociJsonLines -join "`n") |
            ConvertFrom-Json -AsHashtable
        if ($null -eq $ociResponse['data'] -or
            -not $ociResponse['data'].Contains('items')) {
            throw "Thiếu collection items tại region $ociRegion"
        }

        foreach ($ociItem in $ociResponse['data']['items']) {
            $ociInventoryRows.Add([pscustomobject]@{
                ObservedRegion = $ociRegion
                CapturedAtUtc = [DateTime]::UtcNow.ToString('o')
                Resource = $ociItem
            })
        }
        $ociNextPage = $ociResponse['opc-next-page']
    } while (-not [string]::IsNullOrEmpty($ociNextPage))
}

$ociScanFinishedAt = [DateTime]::UtcNow.ToString('o')
$ociInventoryRows.Count
```

OCI dùng response header `opc-next-page` để chỉ trang tiếp theo; CLI biểu diễn token này trong phần metadata của kết quả JSON. Kết thúc phân trang dựa trên token, không dựa vào việc một trang trả ít hơn số lượng mong đợi. [Oracle: REST APIs — List Pagination](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm), [Oracle: Get Started with the CLI](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/gettingstartedwiththeCLI.htm).

Ví dụ dừng bằng lỗi nếu một lượt đọc không thành công. Những hàng đã thu thập trước lỗi vẫn có thể còn trong bộ nhớ, nhưng không được báo chúng là bản kiểm kê hoàn chỉnh. Khi phát triển thành tác vụ vận hành, bổ sung retry có giới hạn, ghi nhận request ID, trạng thái từng region và theo dõi thời gian thực hiện.

### 6.3. Chuẩn hóa mà không làm mất dữ liệu gốc

Tên field trong JSON REST và JSON do CLI hiển thị có thể khác cách viết. Chẳng hạn, CLI thường xuất `compartment-id`, `display-name`, `defined-tags`, trong khi mô hình API dùng camelCase. Đoạn kiểm tra tiếp theo sử dụng JSON CLI của ví dụ trên; cần đối chiếu cấu trúc đầu ra khi chuyển sang SDK.

Một bản ghi inventory nên giữ:

| Trường | Mục đích |
| --- | --- |
| Tenancy OCID | Phân biệt môi trường kiểm kê |
| `identifier` | OCID để nhận diện tài nguyên |
| Resource type | Phân nhóm dịch vụ và chọn API đọc chi tiết |
| Compartment OCID và đường dẫn tra cứu được | Xác định nơi tổ chức tài nguyên |
| Region quan sát và AD nếu có | Giữ ngữ cảnh vị trí |
| Display name | Hỗ trợ người vận hành nhận biết |
| Lifecycle state và time created | Phục vụ phân loại vòng đời |
| Defined tags và free-form tags nguyên gốc | Phát hiện thiếu, sai chuẩn hoặc mâu thuẫn |
| Thời gian bắt đầu/kết thúc và trạng thái thu thập | Đánh giá độ mới cùng mức đầy đủ |

Dùng OCID làm định danh đối chiếu, không dùng display name. Hai tài nguyên có thể cùng tên. Khi ghép nhiều lượt region hoặc nhiều nguồn, một tài nguyên global có thể được quan sát nhiều lần; đếm theo khóa định danh đã chuẩn hóa, đồng thời giữ lại các region và nguồn đã quan sát.

Các hàng trong `$ociInventoryRows` là kết quả quan sát thô. Giá trị `.Count` của collection này chưa chắc bằng số tài nguyên duy nhất. Trước khi tính tỷ lệ bao phủ tag, phải khử trùng lặp theo tenancy và OCID trong đúng phạm vi báo cáo.

## 7. Tìm tài nguyên thiếu tag bằng tập nền đầy đủ

### 7.1. Vì sao chỉ truy vấn tag hợp lệ sẽ gây sai lệch?

Nếu chỉ chạy query `Governance.Application=orders`, bạn chỉ thấy tài nguyên đã có tag khớp. Một volume thiếu tag ứng dụng sẽ không xuất hiện dù thực tế nó phục vụ `orders`.

Với yêu cầu kiểm tra tag `OwnerTeam`, có thể mô tả:

```text
A = tập OCID quan sát được trong phạm vi kiểm kê
B = tập OCID trong A có OwnerTeam hợp lệ theo quy ước
Tài nguyên cần xử lý tag = A trừ B
```

Phải xác định **A độc lập với tag đang kiểm tra**. Khi kiểm kê một ứng dụng chưa được gắn tag đầy đủ, có thể bắt đầu từ compartment đã biết, trạng thái IaC và các API quan hệ tài nguyên để bổ sung bằng chứng về thành phần ứng dụng.

Không nên suy ra “thiếu OwnerTeam” chỉ từ điều kiện giá trị khác `team-orders`. Một tài nguyên có thể thuộc nhóm khác, có key rỗng, thiếu namespace hoặc chưa có dữ liệu tag trong nguồn đang đọc. Các trường hợp đó cần được phân loại riêng.

### 7.2. Ví dụ phân loại dữ liệu tag trong bộ nhớ

Đoạn dưới chạy tiếp với `$ociInventoryRows` đã thu thập thành công. Nó kiểm tra `Governance.OwnerTeam` theo schema của ví dụ và chỉ tạo kết quả phân loại; không sửa tài nguyên:

```powershell
$ociOwnerFindings = foreach ($ociRow in $ociInventoryRows) {
    $ociResource = $ociRow.Resource
    $ociOwnerState = 'VALID'
    $ociOwnerValue = $null

    if (-not $ociResource.Contains('defined-tags') -or
        $null -eq $ociResource['defined-tags']) {
        $ociOwnerState = 'TAG_DATA_UNAVAILABLE'
    } else {
        $ociTags = $ociResource['defined-tags']
        if (-not $ociTags.Contains('Governance')) {
            $ociOwnerState = 'MISSING_NAMESPACE'
        } elseif ($null -eq $ociTags['Governance'] -or
                  -not $ociTags['Governance'].Contains('OwnerTeam')) {
            $ociOwnerState = 'MISSING_KEY'
        } else {
            $ociOwnerValue = $ociTags['Governance']['OwnerTeam']
            if ([string]::IsNullOrWhiteSpace([string]$ociOwnerValue)) {
                $ociOwnerState = 'EMPTY_VALUE'
            }
        }
    }

    [pscustomobject]@{
        Region = $ociRow.ObservedRegion
        OCID = $ociResource['identifier']
        OwnerTeam = $ociOwnerValue
        Check = $ociOwnerState
    }
}

$ociOwnerFindings | Where-Object { $_.Check -ne 'VALID' }
```

`VALID` trong đoạn này chỉ nghĩa là **đúng namespace/key và có giá trị không rỗng**. Muốn xác nhận nhóm tồn tại, cần đối chiếu danh mục nhóm mà tổ chức chấp nhận. Ví dụ không tự chứng minh `team-orders` đang có người trực, cũng không kiểm tra mọi tag bắt buộc khác.

Đối với những key phân biệt hoa thường, cần giữ cách viết nguyên gốc khi so với schema. Đừng chuyển tất cả tag về chữ thường rồi làm mất bằng chứng về `OwnerTeam` và `ownerteam`.

### 7.3. Tính tỷ lệ với mẫu số rõ ràng

Giả sử sau khi khử trùng lặp có 12 tài nguyên thuộc phạm vi cần gắn OwnerTeam; 9 có giá trị hợp lệ, 2 thiếu key và 1 có giá trị rỗng:

```text
Tỷ lệ có OwnerTeam hợp lệ = 9 / 12 × 100% = 75%
```

Nếu một region chưa thu thập thành công, không được dùng 75% để mô tả toàn bộ tenancy. Nếu một loại tài nguyên chưa có dữ liệu tags, báo phần chưa xác định riêng thay vì tự cho đạt hoặc tự loại khỏi mẫu số mà không giải thích.

Nên tách hai chỉ số:

- **Mức bao phủ kiểm kê:** những region, compartment, resource type và nguồn đã được thu thập thành công.
- **Mức tuân thủ tags:** tỷ lệ tài nguyên trong tập đánh giá thỏa quy tắc đã công bố.

Hai chỉ số này giải quyết những câu hỏi khác nhau. Một tỷ lệ tag đẹp không bù được việc còn thiếu hẳn một region production.

## 8. Đối chiếu và sửa metadata theo trách nhiệm

Một kết quả kiểm kê nên dẫn đến việc xử lý có chủ sở hữu:

| Phát hiện | Bằng chứng cần bổ sung | Hành động dự kiến |
| --- | --- | --- |
| Volume thiếu Application | Attachment, cấu hình IaC, xác nhận nhóm ứng dụng | Bổ sung tag đúng nguồn quản lý |
| OwnerTeam không còn hợp lệ | Danh mục nhóm và người tiếp nhận dịch vụ | Cập nhật đầu mối chịu trách nhiệm |
| Tag production nằm trong compartment development | Lịch sử thay đổi và mục đích tài nguyên | Sửa tag hoặc xem lại việc tổ chức tài nguyên |
| Hai bản inventory cùng OCID | Region quan sát và nguồn thu thập | Hợp nhất định danh, giữ bằng chứng quan sát |
| Tài nguyên có trên List API nhưng chưa có trên Search | Quyền, hỗ trợ resource type và thời điểm thay đổi | Ghi nhận khoảng trống quan sát, kiểm tra lại |

Người được phép kiểm kê chưa chắc được phép sửa tags. Với defined tags, ngoài quyền cập nhật tài nguyên còn cần quyền sử dụng tag namespace thích hợp. Quyền quản lý định nghĩa namespace/key là trách nhiệm riêng. [Oracle: Tags and Tag Namespace Concepts](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm).

Search có hỗ trợ các hành động quản lý tags hàng loạt trên kết quả, nhưng phải xác định rõ tập OCID và giá trị đích trước khi thay đổi. Sau thay đổi, đọc lại tài nguyên và quan sát Search sau khi chỉ mục cập nhật. [Oracle: Managing Tags from Search Results](https://docs.oracle.com/en-us/iaas/Content/Search/Tasks/manage-tags.htm).

Nếu tài nguyên được quản lý bằng Terraform hoặc công cụ IaC khác, cập nhật nguồn cấu hình tương ứng để tránh lần triển khai sau đưa tags về giá trị cũ. Tag defaults và tags của tài nguyên phụ cũng cần được đối chiếu với hành vi provider đang dùng; Oracle có ghi nhận các tình huống drift liên quan đến những thành phần này. [Oracle: Known Issues for Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/knownissues_tagging.htm).

Tài nguyên thiếu tag không tự trở thành tài nguyên có thể xóa. Việc xác nhận không còn sử dụng phải dựa thêm vào người chịu trách nhiệm, quan hệ phụ thuộc, tải sử dụng và yêu cầu giữ dữ liệu.

## 9. Dùng kết quả kiểm kê cho chi phí và tính sẵn sàng

Inventory kết hợp tags có thể giúp tập hợp tài nguyên theo cost center, tìm môi trường không rõ chủ sở hữu hoặc xác định thành phần cần kiểm tra trước một đợt bảo trì. Tuy nhiên, số lượng tài nguyên không phải tổng chi phí: hai VM có thể khác shape, thời gian chạy, storage hoặc mô hình dịch vụ cơ sở dữ liệu.

Để quản trị chi phí, đối chiếu định danh và tag với dữ liệu Cost Analysis hoặc báo cáo chi phí/sử dụng của OCI theo đúng khoảng thời gian. Tags trên tài nguyên ở hiện tại không tự giải thích toàn bộ lịch sử chi phí.

Đối với tính sẵn sàng, tag `Environment=recovery` chỉ phản ánh phân loại quản trị. Cần xác minh riêng region, cấu hình mạng, bản sao dữ liệu, tài nguyên dự phòng và khả năng khôi phục. Một bản kiểm kê có thể chỉ ra rằng volume phục hồi chưa có OwnerTeam, nhưng không chứng minh bản sao dữ liệu đáp ứng mục tiêu khôi phục.

Khi đưa kiểm kê vào giám sát hoặc automation, nên giữ một bảng trạng thái cho mỗi lượt thu thập:

```text
Phạm vi dự kiến: tenancy + region + compartment + resource types
Nguồn: Resource Search và các List/Get API bổ sung
Kết quả thu thập: thành công / một phần / lỗi
Khoảng thời gian quan sát: bắt đầu và kết thúc theo UTC
Dữ liệu: raw records + tài nguyên đã hợp nhất theo OCID
Phát hiện: thiếu tag, sai giá trị, mâu thuẫn hoặc chưa xác định
Đầu mối: nhóm tiếp nhận từng phát hiện
```

So sánh hai lượt kiểm kê cũng phải xét thay đổi phạm vi và quyền. Một OCID biến mất khỏi Search có thể do thay đổi query, IAM, region hoặc độ trễ chỉ mục; cần đọc lại từ nguồn dịch vụ trước khi ghi nhận tài nguyên đã bị xóa.

## 10. Bài thực hành và tiêu chí hoàn thành

### Phần A — Xác định tập quan sát

1. Chọn một compartment lab và một region được phép đọc.
2. Xác định ít nhất hai resource type phù hợp với môi trường, chẳng hạn instance và volume.
3. Chạy query theo compartment, ghi lại principal, thời điểm và phạm vi.
4. Đối chiếu ít nhất một tài nguyên đã biết với trang chi tiết hoặc Get API của dịch vụ.
5. Ghi rõ resource type hay region nào chưa nằm trong lần khảo sát.

Không cần tạo thêm tài nguyên nếu đã có dữ liệu lab phù hợp. Nếu dùng dữ liệu giả lập, phải đánh dấu đó là mô phỏng thay vì kết quả lấy từ tenancy.

### Phần B — Truy vấn theo tags

1. Chọn namespace và key đang được phép dùng trong lab; không giả định namespace `Governance` đã tồn tại.
2. Viết query cho một bộ namespace/key/value cụ thể.
3. So sánh tập theo tag với tập nền theo compartment.
4. Xem tag nguyên gốc để phân biệt thiếu key, giá trị rỗng và sai cách viết.
5. Kiểm tra một tài nguyên đã biết có thể không xuất hiện vì quyền hoặc chỉ mục chưa cập nhật.

### Phần C — Kiểm kê có phân trang

Chạy ví dụ thu thập với PowerShell 7 sau khi thay placeholder. Dùng page size nhỏ nếu cần quan sát việc chuyển trang, nhưng luôn đi hết token. Ghi số bản ghi thô, số OCID duy nhất và trạng thái từng region. Chỉ gọi lượt kiểm kê hoàn tất khi mọi phạm vi dự kiến đều được thu thập thành công hoặc được báo rõ là ngoại lệ chưa giải quyết.

### Phần D — Lập danh sách xử lý

Với từng phát hiện, ghi OCID, loại vấn đề, bằng chứng, nhóm tiếp nhận và nguồn cấu hình cần sửa. Nếu được phép thay đổi tags trong lab, sửa một tài nguyên, đọc lại bằng API của dịch vụ rồi kiểm tra Search sau khi chỉ mục cập nhật. Không thay đổi tài nguyên production hoặc dùng sửa tag hàng loạt chỉ để hoàn thành bài thực hành.

Kết quả đạt yêu cầu khi người đọc báo cáo có thể biết **đã kiểm kê ở đâu, bằng quyền nào, quan sát thấy gì và còn thiếu gì**; đồng thời tái tạo được truy vấn, nhận diện tài nguyên bằng OCID và giải thích được cách xác định thiếu tag. Đó là nền tảng để duy trì một landing zone OCI có trách nhiệm vận hành rõ ràng và dữ liệu quản trị đáng tin cậy.