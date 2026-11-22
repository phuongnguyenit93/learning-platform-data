# OCI Audit và truy vết thao tác quản trị

## 1. Mục tiêu và bối cảnh

Trong chương **An toàn thông tin và kiểm toán** của module **CLOUD_PROVIDERS_ORACLE**, bài học này tập trung vào cách dùng OCI Audit để giải thích một thay đổi trên hạ tầng Oracle Cloud Infrastructure: danh tính nào gửi yêu cầu, thao tác gì được gọi, tác động đến tài nguyên nào, vào thời điểm nào và API phản hồi ra sao.

Sau bài học, người học có thể:

- Phân biệt bằng chứng về thao tác quản trị với bằng chứng về truy cập dữ liệu hoặc hoạt động bên trong máy chủ.
- Đọc các trường quan trọng của một Audit event và liên kết những sự kiện liên quan.
- Khoanh vùng tra cứu theo tenancy, compartment, region, thời gian và OCID.
- Tra cứu bằng Console, OCI CLI và Logging Search với quyền phù hợp.
- Lập dòng thời gian điều tra, lưu bằng chứng và thiết kế việc chuyển tiếp log để phục vụ giám sát.

Tình huống xuyên suốt là một Security List của VCN bị thay đổi, làm xuất hiện quy tắc cho phép SSH từ Internet. Yêu cầu điều tra gồm hai phần riêng biệt: xác định thao tác đã sửa cấu hình và xác minh có kết nối thực tế nào lợi dụng cấu hình đó hay chưa.

## 2. OCI Audit ghi nhận điều gì?

OCI Audit tự động ghi nhận lời gọi đến các public API endpoint được hỗ trợ. Lời gọi có thể xuất phát từ Console, CLI, SDK, chương trình tự viết hoặc dịch vụ OCI khác. Vì vậy, một người chỉnh tài nguyên qua trình duyệt và một pipeline chỉnh tài nguyên qua SDK đều có thể để lại bằng chứng API. Audit không yêu cầu cài agent trong máy ảo để ghi nhận những lời gọi này. [Tổng quan OCI Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

Điểm cần xác định trước khi tìm kiếm là **câu hỏi đang nói về lớp quản trị nào**.

| Câu hỏi điều tra | Bằng chứng cần ưu tiên |
| --- | --- |
| Ai gọi API sửa Security List của VCN? | OCI Audit của thao tác quản trị mạng |
| Ai gọi API đổi cấu hình một Compute instance? | OCI Audit của API Compute |
| Có kết nối SSH nào đến máy ảo sau thay đổi không? | Flow log, log hệ điều hành hoặc log truy cập phù hợp |
| Ai đọc một object cụ thể trong bucket? | Log truy cập Object Storage được cấu hình phù hợp |
| Ai chạy một câu SQL trong Oracle Database? | Cơ chế kiểm toán của cơ sở dữ liệu |
| Vì sao một request nghiệp vụ thất bại? | Log ứng dụng, trace và các log hạ tầng liên quan |

Theo phạm vi được Oracle mô tả, Audit của Object Storage ghi nhận các sự kiện liên quan đến bucket, không bao phủ thao tác trên từng object. Không suy ra rằng tải object, đọc object hay xóa object đều xuất hiện trong OCI Audit. [Phạm vi ghi nhận của Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

Bảng trên là cách chọn nguồn bằng chứng cho cuộc điều tra. Các nguồn bổ sung vẫn phải được bật, phân quyền và lưu trữ theo cấu hình của từng môi trường.

Một lời gọi API được ghi lại cũng không đồng nghĩa mọi thay đổi bên trong tài nguyên đều được mô tả đầy đủ. Ví dụ, API khởi động lại máy ảo và một lệnh sửa file do người dùng chạy trong hệ điều hành là hai hoạt động ở hai lớp khác nhau.

## 3. Mô hình truy vết: từ danh tính đến tác động

Có thể hình dung đường đi của một thao tác như sau:

~~~mermaid
flowchart LR
    A["Người dùng hoặc workload"] --> B["Console / CLI / SDK"]
    B --> C["Xác thực và phân quyền IAM"]
    C --> D["API của dịch vụ OCI"]
    D --> E["Tài nguyên đích"]
    D --> F["OCI Audit"]
    F --> G["Tra cứu và lập dòng thời gian"]
    G --> H["Đối chiếu log mạng, máy chủ, ứng dụng"]
~~~

Sơ đồ diễn tả các thành phần cần đối chiếu khi điều tra; không mô tả thứ tự ghi log nội bộ của mọi dịch vụ.

### 3.1. Danh tính kỹ thuật và người chịu trách nhiệm

Audit giúp xác định principal xuất hiện trong yêu cầu. Principal có thể là người dùng, máy ảo sử dụng instance principal, workload sử dụng resource principal hoặc một danh tính kỹ thuật khác.

Nếu principal thuộc pipeline triển khai, cần tìm thêm lần chạy pipeline, phiên bản mã nguồn và người phê duyệt. Nếu principal là một API user dùng chung, bản ghi chỉ xác định được tài khoản đó; việc quy trách nhiệm đến một cá nhân cần thêm bằng chứng.

Địa chỉ IP và user agent giúp bổ sung ngữ cảnh nhưng không tự chứng minh ai đang ngồi trước bàn phím. Nhiều người có thể đi qua cùng NAT, VPN hoặc proxy; một công cụ cũng có thể thay đổi user agent.

### 3.2. Yêu cầu, phản hồi và trạng thái cuối cùng

Khi đọc một sự kiện, hãy tách ba câu hỏi:

1. Yêu cầu nào đã được gửi?
2. API đã trả lời thế nào?
3. Tài nguyên cuối cùng đã ở trạng thái nào?

Phản hồi `202` thường biểu thị yêu cầu đã được chấp nhận để xử lý. Với thao tác bất đồng bộ, cần đối chiếu work request hoặc trạng thái tài nguyên trước khi khẳng định kết quả cuối cùng. Ngay cả một phản hồi thành công của API cập nhật cấu hình cũng chưa chứng minh dịch vụ nghiệp vụ đã hoạt động đúng sau thay đổi.

Ngược lại, phản hồi lỗi chỉ mô tả kết quả của yêu cầu cụ thể. Không dùng một request bị từ chối để kết luận rằng toàn bộ phiên làm việc không có thay đổi thành công nào khác.

## 4. Đọc một Audit event

### 4.1. Các trường cần lấy trước

Trong dạng JSON Audit thường dùng, các trường sau giúp tạo bộ khóa điều tra ban đầu:

| Trường | Công dụng |
| --- | --- |
| `eventId`, `eventTime` | Nhận diện sự kiện, mốc thời gian |
| `data.eventName` | Tên thao tác API |
| `data.compartmentId`, `data.resourceId` | Phạm vi, tài nguyên đích |
| `data.identity.principalId` | Principal thực hiện |
| `data.identity.ipAddress` | IP nguồn |
| `data.request.id`, `data.request.action` | Request ID, phương thức HTTP |
| `data.response.status` | Mã phản hồi |
| `data.eventGroupingId` | Liên kết sự kiện cùng thao tác |
| `data.stateChange.previous/current` | Trạng thái trước và sau nếu có |

`eventGroupingId` có thể liên kết nhiều sự kiện của một API kéo dài. Các trường có thể rỗng hoặc khác nhau theo dịch vụ và phiên bản schema; `stateChange` không phải bản sao cấu hình hoàn chỉnh được bảo đảm cho mọi thao tác. [Cấu trúc Audit log event](https://docs.oracle.com/en-us/iaas/Content/Audit/Reference/logeventreference.htm).

### 4.2. Ví dụ rút gọn

JSON sau là **dữ liệu giả lập phục vụ giải thích**, đã lược bỏ nhiều thuộc tính. Các giá trị trong dấu `<...>` là chỗ giữ chỗ. Không dùng mẫu này làm hợp đồng schema cho chương trình xử lý log.

~~~json
{
  "eventId": "8f46c630-5d95-4ea1-bca1-64cb08e8a621",
  "eventTime": "2026-11-20T02:10:00Z",
  "data": {
    "eventName": "UpdateSecurityList",
    "compartmentId": "<COMPARTMENT_OCID>",
    "resourceId": "<SECURITY_LIST_OCID>",
    "eventGroupingId": null,
    "identity": {
      "principalId": "<PRINCIPAL_OCID>",
      "principalName": "network-deployer",
      "ipAddress": "198.51.100.27",
      "userAgent": "example-deployment-client"
    },
    "request": {
      "id": "example-request-001",
      "action": "PUT"
    },
    "response": {
      "status": "200"
    },
    "stateChange": {
      "previous": null,
      "current": null
    }
  }
}
~~~

Cách diễn giải phù hợp là: vào mốc ghi trong `eventTime`, principal có OCID đã nêu gửi thao tác `UpdateSecurityList` đến Security List đích và API trả về `200`.

Chưa thể kết luận từ mẫu này rằng:

- Người đứng sau principal chắc chắn là chủ tài khoản hợp lệ.
- Nội dung cập nhật chính là quy tắc SSH từ `0.0.0.0/0`.
- Có lưu lượng SSH đã đi qua.
- Không còn thao tác liên quan nào trước hoặc sau sự kiện.

Trong ví dụ, `stateChange` không cung cấp chi tiết thay đổi. Để xác định quy tắc nào được sửa, cần đối chiếu cấu hình trước đó, nội dung triển khai, bản ghi đầy đủ nếu có và trạng thái tài nguyên.

Địa chỉ `198.51.100.27` là địa chỉ minh họa; không đại diện cho nguồn truy cập thật.

### 4.3. Không đồng nhất ba loại mã định danh

- **Event ID** nhận diện một sự kiện trong quá trình thu thập và đối chiếu.
- **Request ID** hỗ trợ nối bản ghi với yêu cầu API, log của công cụ gọi hoặc thông tin gửi cho bộ phận hỗ trợ.
- **Resource OCID** giúp theo dõi tài nguyên qua nhiều thao tác và thời điểm.

Không dùng tên hiển thị làm khóa duy nhất: tên có thể trùng hoặc bị đổi. Cũng không giả định một thao tác nghiệp vụ chỉ tạo đúng một event. Một lần chạy Terraform hoặc một lần thao tác Console có thể phát sinh nhiều API đọc, cập nhật và kiểm tra trạng thái.

Khi đưa log qua một công cụ khác, phải xem JSON thực tế trước khi viết bộ lọc. Tên trường và lớp bao ngoài của kết quả CLI hoặc Logging Search có thể khác cách trình bày của sự kiện gốc. Tránh viết parser bằng cách sao chép tên cột trên giao diện.

## 5. Phân quyền đọc Audit theo phạm vi

Nhóm điều tra nên có quyền đọc Audit trong phạm vi được giao. Ví dụ sau giả định identity domain tên `Default`, group `AuditReaders` và compartment `AuditLab` đã tồn tại:

~~~text
Allow group 'Default'/'AuditReaders' to read audit-events in compartment AuditLab
~~~

Thay domain, group và compartment bằng tên thực tế. Quản trị viên cần đặt policy ở vị trí phù hợp với phạm vi cấp quyền và mô hình IAM của tenancy.

Tài nguyên phân quyền dành cho Audit là `audit-events`. Quyền `read` cấp `AUDIT_EVENT_READ` cho thao tác `ListEvents`; `inspect` chưa cấp quyền này. Dùng `manage` thay `read` trên chính `audit-events` không bổ sung API quản trị hay API xóa log. [Tham chiếu policy của Audit](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/auditpolicyreference.htm).

Nếu giao diện cần cho người điều tra duyệt cây compartment, quản trị viên có thể cấp thêm quyền khám phá compartment theo nhu cầu, chẳng hạn:

~~~text
Allow group 'Default'/'AuditReaders' to inspect compartments in tenancy
~~~

Đây là quyền khám phá phạm vi, tách với quyền đọc Audit. Không cấp quyền Administrator chỉ để xử lý lỗi không thấy log.

Với Logging Search, truy vấn chỉ nhắm `"<COMPARTMENT_OCID>/_Audit"` cần quyền Audit tương ứng. Khi tìm thêm service log hoặc custom log, cần kiểm tra quyền đối với log group và nội dung log; quyền đọc Audit không tự cấp quyền đọc mọi log trong tenancy. [Quyền cần có khi tìm kiếm log](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/searchinglogs.htm).

Trong vận hành, nên tách vai trò người thay đổi hạ tầng và người rà soát bằng chứng. Một người có thể được cấp cả hai vai trò khi thực hành, nhưng báo cáo phải ghi rõ danh tính đã dùng cho từng hành động.

## 6. Khoanh vùng điều tra trước khi viết bộ lọc

Một truy vấn không có kết quả chỉ có ý nghĩa trong phạm vi thực sự đã tìm kiếm. Trước mỗi lượt tra cứu, ghi lại:

| Chiều tra cứu | Thông tin cần xác định |
| --- | --- |
| Tenancy | Đang dùng đúng tenancy và profile chưa? |
| Region | API/tài nguyên hoặc identity domain liên quan ở đâu? |
| Compartment | Tài nguyên thuộc compartment nào tại thời điểm thao tác? |
| Thời gian | Múi giờ, khoảng bắt đầu/kết thúc, độ trễ quan sát |
| Danh tính | Principal OCID, công cụ hoặc pipeline dự kiến |
| Tài nguyên | OCID của đối tượng bị ảnh hưởng |
| Quyền | Người tìm kiếm được đọc những phạm vi nào? |

### 6.1. Region và compartment là hai chiều riêng

Không mặc định rằng chọn root compartment là đã tìm toàn bộ tenancy hoặc đã tìm mọi region. Cần xác nhận phạm vi compartment con và các region được chọn trên công cụ đang dùng. Khi gọi `ListEvents` bằng CLI, hãy coi mỗi cặp compartment/region là một phạm vi truy vấn rõ ràng.

Đối với IAM, kiểm tra compartment chứa identity domain và region liên quan đến domain hoặc thao tác cần điều tra. Đừng áp dụng máy móc region của một Compute instance cho toàn bộ sự kiện IAM. Hướng dẫn Oracle về báo cáo IAM cũng yêu cầu chọn đúng compartment chứa domain và kiểm tra region khi không thấy dữ liệu. [Tra cứu sự kiện IAM từ OCI Audit](https://docs.oracle.com/en/learn/generating-iam-reports-from-oci-audit/).

Nếu tài nguyên đã chuyển compartment, phải xét cả phạm vi cũ và mới theo dòng thời gian thay đổi. Tên và vị trí hiện tại không đủ để suy ngược vị trí của mọi bản ghi lịch sử.

### 6.2. Chuẩn hóa thời gian

Trong báo cáo điều tra, nên lưu thời gian chuẩn UTC và ghi thêm thời gian địa phương khi cần trao đổi với đội vận hành.

Ví dụ:

~~~text
Thời gian địa phương: 2026-11-20 09:10:00 +07:00
Thời gian UTC:        2026-11-20 02:10:00 Z
~~~

Một người báo “sự cố lúc 9 giờ 10” có thể đang nói thời điểm nhận cảnh báo, không phải thời điểm API thay đổi cấu hình. Hãy mở rộng cửa sổ về trước và sau mốc được báo, sau đó thu hẹp khi đã có sự kiện làm điểm neo.

Audit có độ trễ xử lý; tài liệu tra cứu của Oracle nêu sự kiện gần thời điểm hiện tại có thể cần tới khoảng 15 phút để xuất hiện. Vì thế, sau một thao tác lab, nên chờ và truy vấn lại cùng phạm vi trước khi kết luận thiếu log. [Tìm kiếm Audit log events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/searching-log-events.htm).

Độ trễ này không nên được dùng như cam kết thời gian phát hiện sự cố cho một hệ thống giám sát. Hãy đo độ trễ thực tế của cả chuỗi thu thập, xử lý và thông báo.

## 7. Tra cứu trên Console và Logging Search

### 7.1. Quy trình bằng giao diện

Có thể mở Audit từ nhóm **Observability & Management → Logging → Audit**. Giao diện Audit tích hợp với Logging cho phép khám phá sự kiện và xuất dữ liệu JSON; Audit cũng có thể được tìm qua log group đặc biệt `_Audit` trong Logging Search. [Giao diện Audit trong Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/audit_logs.htm).

Thực hiện theo thứ tự sau:

1. Xác nhận tenancy và region đang chọn.
2. Chọn compartment liên quan, rồi đặt cửa sổ thời gian.
3. Bắt đầu bằng tài nguyên hoặc một mốc thời gian đã biết.
4. Mở một sự kiện và xem JSON chi tiết.
5. Ghi lại principal OCID, resource OCID, request ID, thao tác và mã phản hồi.
6. Tìm tiếp các sự kiện trước và sau theo tài nguyên hoặc principal.
7. Xuất dữ liệu cần thiết cùng mô tả phạm vi truy vấn.

Khi truy vết thay đổi Security List, đừng chỉ lọc `PUT` ngay từ đầu. Các request đọc cấu hình, truy vấn tài nguyên hoặc các thao tác thuộc một chuỗi triển khai có thể giải thích bối cảnh của cập nhật.

Nếu màn hình chỉ hiển thị một phần kết quả, phải kiểm tra phân trang và bộ lọc trước khi dựng dòng thời gian. Ảnh chụp màn hình giúp trao đổi nhanh, nhưng bản JSON và phạm vi truy vấn mới giúp người khác kiểm tra lại chi tiết.

### 7.2. Truy vấn theo tài nguyên

Mẫu sau dùng ngôn ngữ truy vấn của OCI Logging Search. Thay các giá trị giữ chỗ bằng OCID thật, rồi chọn thời gian và region trong giao diện:

~~~text
search "<COMPARTMENT_OCID>/_Audit"
| where data.resourceId = '<SECURITY_LIST_OCID>'
| sort by datetime asc
~~~

Truy vấn này phục vụ câu hỏi: **trong phạm vi đã chọn, tài nguyên đó có những sự kiện nào theo thứ tự thời gian?**

Nếu chưa biết chính xác OCID được đặt ở đâu trong event của một dịch vụ, hãy tìm rộng hơn và kiểm tra bản ghi thực tế. Một event tạo tài nguyên, xóa tài nguyên hoặc thao tác trên tài nguyên cha có thể cần cách đối chiếu khác.

### 7.3. Truy vấn theo principal và thao tác

Sau khi đã có principal cần xem xét, có thể thu hẹp:

~~~text
search "<COMPARTMENT_OCID>/_Audit"
| where data.identity.principalId = '<PRINCIPAL_OCID>'
  and data.eventName = 'UpdateSecurityList'
| sort by datetime asc
~~~

Hai mẫu truy vấn trên là mẫu thực hành cho những trường có trong JSON quan sát được; không thay thế bước xác nhận schema. Chúng dựa trên cách tìm theo trường của Logging Search. Mỗi lượt tìm kiếm có giới hạn dải thời gian, được tài liệu Oracle mô tả là 14 ngày; cần chia khoảng phù hợp khi điều tra dài hơn. [Logging Search và truy vấn nâng cao](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/searchinglogs.htm).

Khi đã xác định sự kiện nghi vấn, hãy bỏ bộ lọc tên thao tác và mở rộng sang các compartment/region liên quan nếu cần. Một principal có thể vừa sửa policy, vừa thay đổi mạng, rồi thực hiện thao tác trên Compute trong cùng một chuỗi hoạt động.

## 8. Tra cứu bằng OCI CLI và giữ nguyên kết quả gốc

### 8.1. Điều kiện thực hành

Máy thực hành cần OCI CLI đã cấu hình xác thực hợp lệ. Ví dụ dưới đây dùng PowerShell và profile `AUDIT_LAB`. Danh tính của profile có quyền đọc Audit trong compartment đích; profile này không cần quyền sửa hạ tầng chỉ để chạy truy vấn.

Các lệnh là ví dụ để người học chạy trong môi trường của mình. Thay các giá trị giữ chỗ; khoảng thời gian mẫu phải được đổi theo sự kiện thực tế.

### 8.2. Lấy một cửa sổ sự kiện có phân trang đầy đủ

~~~powershell
$auditRegion = 'ap-singapore-1'
$auditCompartment = '<COMPARTMENT_OCID>'
$auditStart = '2026-11-20T01:50:00Z'
$auditEnd = '2026-11-20T02:40:00Z'

$auditArguments = @(
    'audit', 'event', 'list',
    '--profile', 'AUDIT_LAB',
    '--region', $auditRegion,
    '--compartment-id', $auditCompartment,
    '--start-time', $auditStart,
    '--end-time', $auditEnd,
    '--all',
    '--output', 'json'
)

$auditOutput = & oci @auditArguments
if ($LASTEXITCODE -ne 0) {
    throw 'Tra cứu Audit thất bại; không lưu kết quả như bằng chứng thành công.'
}

$auditJson = [string]::Join(
    [Environment]::NewLine,
    [string[]]$auditOutput
)
$auditParsed = $auditJson | ConvertFrom-Json -ErrorAction Stop
if ($null -eq $auditParsed.data) {
    throw 'Không tìm thấy trường data trong kết quả; cần kiểm tra đầu ra.'
}

$auditFile = Join-Path (Get-Location) 'audit-window.json'
[System.IO.File]::WriteAllText(
    $auditFile,
    $auditJson,
    [System.Text.UTF8Encoding]::new($false)
)

Get-FileHash -LiteralPath $auditFile -Algorithm SHA256
~~~

`--all` lấy tất cả các trang của truy vấn; nó không tự duyệt mọi compartment, region hay toàn bộ lịch sử. Đối số thời gian của lệnh dùng RFC 3339, chính xác đến phút; đặt giây và phần lẻ giây bằng `0`. Theo mô tả CLI, điểm đầu bao gồm và điểm cuối loại trừ dựa trên thời gian sự kiện được xử lý. [Tham chiếu `oci audit event list`](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/audit/event/list.html).

Lệnh trên kiểm tra mã thoát và khả năng đọc JSON trước khi lưu. Điều đó tránh việc coi thông báo lỗi hoặc đầu ra không hợp lệ là một bản xuất Audit thành công.

### 8.3. Phân biệt thời gian truy vấn và thời gian dựng dòng sự kiện

Khi phân tích, dùng timestamp phù hợp trong event để mô tả thời điểm hoạt động, đồng thời giữ lại nguyên khoảng thời gian đã dùng để lấy dữ liệu. Không giả định thời gian xử lý, thời gian sự kiện và thời gian người điều tra tải log luôn trùng nhau.

Với tác vụ trích xuất lặp lại do đội vận hành tự xây dựng, nên cân nhắc:

- Duyệt danh sách compartment/region đã được phê duyệt.
- Chia cửa sổ theo dung lượng và giới hạn hiện hành của công cụ.
- Dùng phần giao nhau giữa các lần lấy để giảm nguy cơ bỏ sót dữ liệu xuất hiện muộn.
- Khử trùng lặp theo khóa sự kiện đã kiểm chứng trong schema thực tế.
- Chỉ cập nhật mốc thu thập sau khi kết quả đã lưu thành công.
- Ghi nhận lỗi xác thực, phân trang, giới hạn gọi API và khoảng trống thu thập.

Đây là đề xuất thiết kế quy trình, không phải bảo đảm rằng một script polling đơn giản sẽ đáp ứng mọi yêu cầu lưu trữ. Oracle nêu `ListEvents` không dành cho bulk export; với luồng xuất quy mô lớn, cần dùng cơ chế phù hợp của Logging và Connector Hub. [Giới hạn sử dụng API tra cứu](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/listing-log-events.htm).

## 9. Thực hành truy vết thay đổi Security List

### 9.1. Bối cảnh giả định

Đội vận hành phát hiện SSH có thể truy cập từ Internet lúc **09:15 ngày 20/11/2026, UTC+7**. Security List đích thuộc compartment `Prod-Network`. Dữ liệu giả định thu thập được gồm:

| Thời gian UTC | Dữ kiện quan sát |
| --- | --- |
| 02:06 | Một pipeline bắt đầu đợt triển khai cấu hình mạng |
| 02:10 | Audit có `UpdateSecurityList`, principal `P`, phản hồi `200` |
| 02:12 | Công cụ kiểm tra cấu hình phát hiện quy tắc nguồn `0.0.0.0/0` đến cổng 22 |
| 02:15 | Đội vận hành nhận cảnh báo |
| 02:24 | Một thao tác cập nhật khác đưa quy tắc về phạm vi nội bộ |

Mọi thời điểm trong bảng là dữ liệu của tình huống giả định. Chúng không phải kết quả đã truy vấn từ một tenancy thật.

### 9.2. Các bước điều tra

**Bước 1 — Chốt đối tượng và lưu cấu hình đang thấy.**

Ghi lại tenancy, region, compartment và OCID Security List. Lưu cấu hình được quan sát tại thời điểm điều tra, nhưng đặt tên đúng là “cấu hình tại thời điểm thu thập”, tránh gọi đó là cấu hình ngay sau sự kiện nếu chưa chứng minh được.

**Bước 2 — Tìm chuỗi sự kiện của tài nguyên.**

Bắt đầu với cửa sổ rộng hơn mốc cảnh báo, chẳng hạn 01:50–02:40 UTC. Đối chiếu mọi thao tác liên quan, bao gồm cập nhật nghi vấn và cập nhật khắc phục. Giữ request ID của từng sự kiện.

**Bước 3 — Xác định principal và đường thực thi.**

Với principal `P`, tìm thông tin công việc triển khai tương ứng. So sánh thời gian pipeline, danh tính workload, request ID nếu được ghi ở phía công cụ và thay đổi mã nguồn.

Nếu log chỉ cho biết principal kỹ thuật, viết đúng mức kết luận đó. Đừng tự thay principal bằng tên một kỹ sư chỉ vì kỹ sư đó thường quản lý pipeline.

**Bước 4 — Chứng minh nội dung thay đổi.**

Nếu event có trạng thái trước/sau đủ chi tiết, đối chiếu quy tắc ingress và các trường liên quan. Nếu không, dùng bản cấu hình trước triển khai, thay đổi IaC hoặc snapshot cấu hình đã lưu.

Một thao tác `UpdateSecurityList` thành công chưa tự chứng minh đó là thao tác mở cổng 22. Mối liên hệ này cần bằng chứng về nội dung cấu hình.

**Bước 5 — Đánh giá khả năng truy cập và truy cập thực tế.**

Kiểm tra những thành phần có thể ảnh hưởng đường đi như route, địa chỉ IP, NSG, các Security List liên quan và firewall của hệ điều hành. Một quy tắc mở rộng trên Security List có thể làm tăng rủi ro, nhưng khả năng kết nối cuối cùng phụ thuộc cấu hình tổng thể.

Sau đó đối chiếu flow log và log máy chủ sẵn có trong khoảng liên quan. Nếu chưa có log phù hợp, ghi rõ giới hạn này thay vì kết luận chắc chắn rằng không ai kết nối.

**Bước 6 — Gắn với quản lý thay đổi.**

Đối chiếu ticket phê duyệt, cửa sổ bảo trì và phiên bản cấu hình. Ghi nhận riêng hành động khắc phục, người thực hiện và cách xác nhận cấu hình đã trở lại trạng thái mong muốn.

### 9.3. Cách viết kết luận có thể kiểm tra lại

Một kết luận phù hợp với dữ kiện giả định có thể là:

> Trong region và compartment được kiểm tra, Audit ghi nhận principal P gọi UpdateSecurityList cho tài nguyên R lúc 02:10 UTC và API trả về 200. Đối chiếu phiên bản cấu hình triển khai cho thấy quy tắc SSH có nguồn 0.0.0.0/0 được đưa vào trong lần triển khai tương ứng. Chưa có đủ bằng chứng trong tập log hiện có để xác định có phiên SSH thành công từ bên ngoài trong khoảng phơi lộ.

Cách viết này phân biệt rõ sự kiện đã ghi nhận, kết quả đối chiếu và phần chưa thể xác minh. Nếu chỉ mới có Audit event, phải bỏ khẳng định về nội dung quy tắc cho đến khi có bằng chứng bổ sung.

## 10. Bài thực hành trong compartment riêng

Mục tiêu thực hành là chứng minh người học có thể tìm lại một thao tác đã biết, không cần mở cổng mạng ra Internet.

### 10.1. Chuẩn bị

Dùng một compartment thực hành và một tài nguyên mạng dùng riêng cho lab đã được quản trị viên cung cấp. Ghi lại region, compartment OCID, resource OCID và tên hiển thị ban đầu.

Người thực hiện thao tác cần quyền cập nhật thuộc tính tương ứng. Người tra cứu cần quyền đọc Audit. Nếu dùng cùng một tài khoản cho cả hai vai trò trong lab, hãy ghi điều đó trong kết quả.

Không cần tạo thêm Compute instance, database hoặc dịch vụ tính phí chỉ để tạo một Audit event.

### 10.2. Tạo một thay đổi dễ nhận biết

1. Ghi thời gian UTC trước khi thao tác.
2. Dùng công cụ quản trị được phép đổi display name của Security List thực hành sang một tên có dấu mốc, ví dụ `audit-lab-after`.
3. Giữ nguyên các quy tắc mạng.
4. Ghi lại principal thực hiện, thời gian hoàn tất và request ID nếu công cụ cung cấp.
5. Sau khi xác nhận đã đổi tên, ghi thời gian kết thúc cửa sổ thực hành.

Chọn thay đổi tên giúp tạo dấu vết quản trị mà không thay đổi chính sách lưu lượng. Đây là thao tác với tài nguyên lab đã được giao, không phải hướng dẫn thử thay đổi tài nguyên sản xuất.

### 10.3. Tìm lại sự kiện

Chờ log được xử lý, rồi tìm theo đúng compartment, region và khoảng thời gian đã ghi. Bắt đầu bằng resource OCID; sau đó đối chiếu:

- Có thao tác cập nhật phù hợp với lần đổi tên không?
- Principal có khớp danh tính thực hiện không?
- Mã phản hồi có phù hợp với kết quả quan sát không?
- Event có cung cấp thông tin trạng thái trước/sau hay không?
- Có những API đọc hoặc cập nhật khác trong cùng cửa sổ không?

Xuất bản ghi phù hợp và một phần ngữ cảnh đủ để giải thích chuỗi thao tác. Khi đọc JSON bằng công cụ riêng, giữ bản xuất ban đầu và tạo bản phân tích tách biệt.

### 10.4. Khôi phục và ghi kết quả

Đổi display name về giá trị ban đầu bằng cùng quy trình được phép. Tìm lại sự kiện khôi phục và phân biệt nó với sự kiện đầu tiên.

Kết quả thực hành cần có một bảng ngắn gồm: mốc UTC, region, compartment OCID, resource OCID, principal OCID, tên thao tác, mã phản hồi, event ID và request ID nếu có. Nếu không thấy trường nào, ghi “không có trong bản ghi quan sát được”.

Bài thực hành đạt mục tiêu khi người học chỉ ra được sự kiện tương ứng với thao tác đã thực hiện và giải thích đúng giới hạn của bằng chứng. Không bắt buộc event phải có đầy đủ `stateChange`.

## 11. Lưu trữ, chuyển tiếp và giám sát Audit

### 11.1. Retention của Audit và thời hạn lưu bằng chứng

Audit logs được giữ **365 ngày**. Oracle mô tả retention ở cấp tenancy, áp dụng cho các region và compartment; giá trị này hiện không thay đổi được. [Thời gian lưu Audit log](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm).

Đừng nhầm thời hạn giữ dữ liệu với độ dài dải thời gian của một truy vấn. Cũng cần phân biệt báo cáo tích hợp sẵn trong IAM identity domains: tài liệu Oracle mô tả các báo cáo này có dữ liệu 14 ngày, còn dữ liệu cũ hơn có thể được tra cứu qua OCI Audit trong thời hạn của Audit. [Các loại báo cáo IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/understand-types-reports.htm).

Nếu tổ chức cần giữ bằng chứng lâu hơn, thiết kế một kho lưu trữ riêng và xác minh việc chuyển log vào kho đó. Đừng đợi sát ngày hết thời hạn mới bắt đầu thu thập.

### 11.2. Kiến trúc chuyển tiếp tham khảo

~~~mermaid
flowchart LR
    A["Audit trong Logging / _Audit"] --> B["Connector Hub"]
    B --> C["Object Storage lưu trữ"]
    B --> D["Đích tích hợp được hỗ trợ"]
    D --> E["Xử lý và tương quan tại SIEM"]
    C --> F["Điều tra và kiểm tra lưu trữ"]
~~~

Đây là kiến trúc tham khảo; mỗi tuyến cần được cấu hình và cấp quyền theo đích thực tế. Logging tích hợp Connector Hub để chuyển log, trong đó có kịch bản lưu trữ sang Object Storage. [Kịch bản lưu log vào Object Storage](https://docs.oracle.com/en-us/iaas/Content/connector-hub/archivelogs.htm).

Đối với nguồn Audit, kiểm tra lựa chọn `_Audit` và điều kiện lọc của connector. [Cấu hình connector cho Audit](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/connectors.htm).

Trong triển khai thực tế, cần xác định ít nhất:

- Nguồn nào được thu thập: tenancy, compartment, region và loại sự kiện.
- Ai có thể sửa hoặc dừng connector.
- Quyền đọc nguồn và ghi đích có đúng phạm vi không.
- Làm sao phát hiện khi luồng chuyển tiếp dừng hoặc có khoảng trống.
- Làm sao xử lý dữ liệu trùng, xuất hiện muộn hoặc thay đổi schema.
- Làm sao kiểm tra có thể đọc lại dữ liệu lưu trữ khi cần điều tra.

Không mặc định một connector vừa tạo sẽ tự chuyển toàn bộ dữ liệu lịch sử đang còn trong Audit. Nhu cầu backfill phải được xác minh và tổ chức thành công việc riêng.

Tài liệu bulk export của Oracle hướng các yêu cầu mới sang Logging và Service Connector Hub, thay cho quy trình yêu cầu hỗ trợ cũ. [Bulk export của Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/bulkexport.htm).

### 11.3. Kiểm soát kho bằng chứng

Đối với bản xuất và bản lưu trữ, nên áp dụng các nguyên tắc sau:

- Giữ bản gốc, tạo bản rút gọn hoặc chuẩn hóa phục vụ phân tích riêng.
- Ghi người thu thập, thời điểm thu thập, câu truy vấn và phạm vi dữ liệu.
- Tính hash khi cần kiểm tra file có thay đổi sau khi thu thập hay không.
- Giới hạn quyền đọc, sửa, xóa và thay đổi cấu hình lưu trữ.
- Xác định thời hạn lưu, lifecycle và yêu cầu chống sửa/xóa theo chính sách của tổ chức.
- Kiểm tra khả năng phục hồi, đọc lại và giải thích dữ liệu định kỳ.

Hash giúp phát hiện thay đổi so với bản đã tính hash; một mình nó không chứng minh dữ liệu ban đầu đầy đủ hoặc có nguồn gốc đáng tin. Bằng chứng còn cần ngữ cảnh thu thập và kiểm soát truy cập.

Audit log có thể chứa tên người dùng, địa chỉ IP, OCID, đường dẫn và metadata nhạy cảm. Chỉ chia sẻ phần cần thiết cho người được phép; khi tạo bản minh họa hoặc gửi ra ngoài, giữ bản gốc trong nơi kiểm soát và dùng bản đã xử lý phù hợp.

### 11.4. Phát hiện bất thường và kiểm soát chi phí

Có thể đề xuất quy tắc phát hiện quanh những tín hiệu như thay đổi policy, cập nhật cấu hình mạng nhạy cảm, thao tác xóa tài nguyên quan trọng hoặc nhiều lỗi phân quyền từ cùng một principal.

Một điều kiện chỉ dựa trên tên API thường chưa đủ. Ví dụ `UpdateSecurityList` có thể là thay đổi hợp lệ, đổi tên hoặc cập nhật quy tắc rủi ro. Cần kết hợp tài nguyên, principal, thời gian, nội dung thay đổi nếu có và lịch triển khai.

Kênh giám sát phải được kiểm tra bằng sự kiện thử có kiểm soát. Quan sát cả trường hợp có sự kiện đáng ngờ và trường hợp đường thu thập bị ngắt. Một dashboard không có cảnh báo chưa chứng minh rằng không có vấn đề.

Khi dự trù chi phí, tính đến lưu trữ bản xuất, bản sao, truy vấn phân tích và đích tích hợp. Điều chỉnh mức lưu chi tiết theo mục tiêu điều tra; tránh nhân bản toàn bộ log sang nhiều nơi mà không có nhu cầu sử dụng. Không áp dụng một thời hạn xóa ngắn chỉ vì muốn giảm dung lượng khi thời hạn đó mâu thuẫn với yêu cầu giữ bằng chứng.

## 12. Xử lý khi không thấy sự kiện hoặc chưa đủ bằng chứng

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Không có kết quả sau thao tác lab | Kiểm tra region, compartment, UTC và chờ xử lý |
| Có quyền quản lý tài nguyên nhưng không đọc được Audit | Kiểm tra quyền `audit-events` của danh tính tra cứu |
| Có log nhưng không thấy toàn bộ chuỗi | Kiểm tra phân trang, bộ lọc và phạm vi thời gian |
| Chỉ thấy sự kiện ở một compartment | Xác minh việc duyệt compartment con và vị trí lịch sử của tài nguyên |
| Tìm theo tên không ra hoặc ra nhiều tài nguyên | Dùng OCID, rồi kiểm tra tên tại thời điểm sự kiện |
| Không thấy thay đổi chi tiết | Kiểm tra `stateChange` và bổ sung cấu hình/IaC lịch sử |
| Không tìm được thao tác trên object hoặc câu SQL | Chuyển sang nguồn log thuộc lớp dữ liệu tương ứng |
| Principal là danh tính pipeline | Đối chiếu job, commit và thông tin phê duyệt |
| Cùng sự kiện xuất hiện nhiều lần trong kho tổng hợp | Kiểm tra phần giao giữa lần lấy và quy tắc khử trùng lặp |
| Truy vấn cũ chạy lỗi hoặc không khớp trường | Xem JSON thực tế và kiểm tra schema của nguồn đầu vào |

Khi chuyển giao kết quả cho người khác, ghi đủ để họ tái hiện cuộc điều tra:

~~~text
Mã sự việc:
Câu hỏi điều tra:
Tenancy / profile:
Region đã kiểm tra:
Compartment đã kiểm tra:
Cửa sổ thời gian UTC:
Thời điểm thu thập UTC:
Nguồn và câu truy vấn:
Resource OCID:
Principal OCID:
Event ID / request ID / grouping ID nếu có:
Kết quả API:
Bằng chứng bổ sung:
Kết luận được chứng minh:
Điểm chưa xác minh:
Vị trí bản gốc và hash nếu đã tính:
~~~

Một báo cáo có giá trị phải phân biệt được “không có sự kiện trong phạm vi đã tìm”, “chưa có đủ dữ liệu để quan sát” và “đã có bằng chứng cho kết luận”. Khi phạm vi, danh tính, thời gian và nguồn bằng chứng được ghi rõ, OCI Audit trở thành nền tảng để truy vết thay đổi hạ tầng và kiểm tra trách nhiệm vận hành.
